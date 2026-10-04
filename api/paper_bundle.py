"""paper_bundle.py - every NT8 PAPER trade in a few documents, so the board can load ALL of them cheaply.

WHY (LEDGER unify step 3, owner GO 2026-10-03). The board read users/<uid>/paper_trades with
orderBy(entryTime desc).limit(500), so "All" covered only the newest ~3 weeks of ~1000 trades. Reading
every trade doc on every board open is not an option: the Firestore free quota is 50,000 reads a day shared
by everything. So the nightly run writes ONE compact copy of every trade into users/<uid>/paper_bundle/<n>
(a handful of documents) and the board reads those instead: one read per ~1,200 trades, plus a small
direct read of the newest trades for freshness.

SHAPE. Each chunk document is {gen, part, parts, n_total, n, fields, rows, written_at}:
  * rows is ONE JSON string holding a list of positional arrays in the order of `fields`. A string, not a
    Firestore array, because Firestore refuses an array nested inside an array and a string also keeps every
    field name out of the 1 MiB document size (CHUNK_CHARS keeps each chunk far under it).
  * gen is the same on every chunk of one write; the reader refuses a mix of generations (a read that
    straddled a write) and falls back to the old direct read.
  * chunk 0 is written LAST, so a reader that finds chunk 0 finds a finished set.
  * n_total is the number of trade docs that were stored when the bundle was written - the number the
    board checks its own loaded count against.

Only the fields the board draws are kept (BOARD_FIELDS). Pure functions except write_bundle / read_bundle,
which take the db handle. Fail-soft at the call site: a bundle problem must never cost the nightly report.
"""
import json
import time

COLLECTION = "paper_bundle"
# the fields the NT8 board reads off a trade doc (index.html, the paper2 branch); the doc id rides as `id`
FIELDS = ["id", "leg", "strategy", "side", "entryTime", "exitTime", "entryIso", "exitIso",
          "entry_px", "exit_px", "pnl_pts", "pnl_usd", "backfill", "live_from", "open",
          "close_day", "flags", "roll_artifact", "roll_note"]
CHUNK_CHARS = 450_000        # JSON text per chunk document; the Firestore cap is 1 MiB per document
SHRINK_GUARD = 0.9           # refuse to replace a bundle with one holding under this share of its trades


def encode_row(doc_id, doc):
    """One trade as a positional list in FIELDS order (None where the doc has no such field)."""
    d = dict(doc or {})
    d["id"] = doc_id
    out = []
    for f in FIELDS:
        v = d.get(f)
        if f == "roll_artifact" and not v:
            v = None                       # only the few flagged trades carry it
        out.append(v)
    return out


def build_chunks(items, chunk_chars=None):
    """items = [(doc_id, doc_dict)] -> list of JSON strings, each a list of rows, split by size.
    Oldest entry first so a chunk boundary is stable from night to night."""
    chunk_chars = chunk_chars or CHUNK_CHARS      # read at call time so a test can shrink it
    rows = sorted((encode_row(i, d) for i, d in items),
                  key=lambda r: (r[FIELDS.index("entryTime")] or 0, str(r[0])))
    chunks, cur, size = [], [], 2
    for r in rows:
        s = json.dumps(r, separators=(",", ":"), default=str)
        if cur and size + len(s) + 1 > chunk_chars:
            chunks.append(cur)
            cur, size = [], 2
        cur.append(r)
        size += len(s) + 1
    if cur or not chunks:
        chunks.append(cur)
    return [json.dumps(c, separators=(",", ":"), default=str) for c in chunks], len(rows)


def decode_chunks(chunk_docs):
    """chunk docs (dicts) -> list of trade dicts shaped like the stored docs. Raises ValueError on a mix of
    generations or a missing part, so the caller can fall back."""
    if not chunk_docs:
        raise ValueError("no bundle chunks")
    gens = {c.get("gen") for c in chunk_docs}
    parts = max(int(c.get("parts") or 0) for c in chunk_docs)
    if len(gens) != 1 or len(chunk_docs) != parts or {int(c.get("part", -1)) for c in chunk_docs} != set(range(parts)):
        raise ValueError("bundle chunks are from different writes or incomplete")
    out = []
    for c in sorted(chunk_docs, key=lambda c: int(c.get("part", 0))):
        fields = c.get("fields") or FIELDS
        for row in json.loads(c.get("rows") or "[]"):
            o = {}
            for f, v in zip(fields, row):
                if v is not None:
                    o[f] = v
            out.append(o)
    return out


def write_bundle(db, uid, *, log=None, note_reads=None, now=None):
    """Read every paper_trades doc once and rewrite the bundle. Returns a stats dict, or None when it
    declined to write. One read per stored trade (the nightly prune already streams the same docs per
    leg, so this is one more pass) and one write per chunk."""
    log = log or (lambda m: None)
    base = db.collection("users").document(uid)
    snaps = list(base.collection("paper_trades").stream())
    if note_reads:
        note_reads(len(snaps))
    items = [(s.id, s.to_dict() or {}) for s in snaps]
    col = base.collection(COLLECTION)
    old0 = col.document("0").get()
    old = old0.to_dict() if old0.exists else None
    if note_reads:
        note_reads(1)
    if old and items and len(items) < SHRINK_GUARD * int(old.get("n_total") or 0):
        log(f"uid={uid} paper_bundle NOT written: {len(items)} trade docs read against {old.get('n_total')} "
            f"in the standing bundle (a short read must not shrink it)")
        return None
    chunks, n_total = build_chunks(items)
    gen = str(int(time.time() if now is None else now))
    parts = len(chunks)
    for part in range(parts - 1, -1, -1):          # chunk 0 last = the commit marker
        col.document(str(part)).set({
            "gen": gen, "part": part, "parts": parts, "n_total": n_total,
            "n": len(json.loads(chunks[part])), "fields": FIELDS, "rows": chunks[part],
            "written_at": gen})
    for part in range(parts, int((old or {}).get("parts") or 0)):   # a shrunk bundle leaves no stale tail
        col.document(str(part)).delete()
    log(f"uid={uid} paper_bundle: {n_total} trades in {parts} chunk(s), "
        f"{sum(len(c) for c in chunks):,} chars")
    return {"n_total": n_total, "parts": parts, "chars": sum(len(c) for c in chunks), "gen": gen}


def read_bundle(db, uid):
    """(trades, meta) from the standing bundle, or (None, None) when there is none / it is torn."""
    col = db.collection("users").document(uid).collection(COLLECTION)
    d0 = col.document("0").get()
    if not d0.exists:
        return None, None
    m0 = d0.to_dict() or {}
    docs = [m0] + [(col.document(str(p)).get().to_dict() or {}) for p in range(1, int(m0.get("parts") or 1))]
    try:
        return decode_chunks(docs), {"n_total": m0.get("n_total"), "parts": m0.get("parts"), "gen": m0.get("gen")}
    except ValueError:
        return None, None
