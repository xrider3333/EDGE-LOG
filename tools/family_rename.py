"""ONE FAMILY VOCABULARY - re-stamp stored family run ids (owner 2026-09-24: "family names consistent, 1-2 words max").

Every run carries a stable family run id (famKey + famSeq, e.g. ORB-8 = run #175). The runner, the web
app and the research board each kept their own family list, so the same family was stored under
several keys. This maps every stored key onto the one vocabulary in api/runner.py `_family_of`:

    TTMSQZ -> TTM   VWAP-FADE -> VWAP   NQDIP + ETFDIP -> DIP   COMBINED -> BOOK   ORB-FADE -> ORB
    (no key at all) -> whatever the resolver says for the run's strategy

NUMBERS, under the stable-v1 promise that a family number never moves:
  * a pure RENAME keeps every number (TTMSQZ-25 becomes TTM-25);
  * a MERGE keeps the numbers of the family that ran first (DIP keeps NQDIP's 1..5) and appends the
    absorbed family's runs after it, in run-id order. Those appended runs get new numbers - it is the
    one unavoidable move, and every re-numbered run keeps its old id in famKeyOld / famSeqOld.
meta/familyCounters is rewritten to each family's highest number so the runner continues from there.

Idempotent: a run already on the new vocabulary is left alone, so it is safe to re-run after the runner
has been restarted onto the new resolver.
    python tools/family_rename.py --dry      # print the plan, write nothing
    python tools/family_rename.py            # apply
"""
import argparse, collections, os, re, sys
os.chdir(r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG")
import firebase_admin
from firebase_admin import credentials, firestore

UID = "IO0K35JpLIcH9YK4C0pMNYUzZOM2"
RENAME = {"TTMSQZ": "TTM", "VWAP-FADE": "VWAP", "NQDIP": "DIP", "ETFDIP": "DIP", "COMBINED": "BOOK",
          "ORB-FADE": "ORB"}


def resolve(strategy):
    """Mirror of api/runner.py _family_of (kept in step by hand; tests compare the two)."""
    s0 = str(strategy or "").upper()
    if s0.startswith("BOOK") or s0.startswith("COMBINED"): return "BOOK"
    if s0.startswith("ORB") or s0.startswith("OPENING RANGE"): return "ORB"
    if s0.startswith("ENGUQ") or s0.startswith("ENGUDQ") or s0.startswith("ENGU-Q"): return "ENGU-Q"
    if s0.startswith("NOISE"): return "NOISE"
    if s0.startswith("TTMSQZ") or s0.startswith("TTM"): return "TTM"
    if s0.startswith("NQDIP") or s0.startswith("ETFDIP"): return "DIP"
    if s0.startswith("TTIBS") or s0.startswith("TBISS"): return "TTIBS"
    if s0.startswith("REVERT"): return "REVERT"
    if "SUPERTREND" in s0 or s0.startswith("STRICT"): return "SUPERTREND"
    if s0.startswith("VWAP"): return "VWAP"
    if s0.startswith("OVERNIGHT"): return "OVERNIGHT"
    if s0.startswith("RSIDIV"): return "RSIDIV"
    base = re.sub(r"\.PY$", "", s0)
    m = re.match(r"[A-Z][A-Z0-9]*", base)
    return m.group(0) if m else "MISC"


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--dry", action="store_true"); ap.add_argument("--max", type=int, default=600)
    a = ap.parse_args()
    if not firebase_admin._apps:
        firebase_admin.initialize_app(credentials.Certificate("serviceAccount.json"))
    db = firestore.client(); u = db.collection("users").document(UID)
    runs = []
    for lo in range(1, a.max + 1, 100):
        refs = [u.collection("runs").document(str(i)) for i in range(lo, min(lo + 100, a.max + 1))]
        for d in db.get_all(refs, field_paths=["strategy", "famKey", "famSeq"]):
            if d.exists:
                y = d.to_dict() or {}
                runs.append(dict(id=int(d.id), strat=y.get("strategy"), key=y.get("famKey"), seq=y.get("famSeq")))
    runs.sort(key=lambda r: r["id"])
    # the stored counters, not just the numbers still on runs: a deleted run leaves a gap, and its
    # number must never be handed out again
    stored = (u.collection("meta").document("familyCounters").get().to_dict() or {}).get("counters") or {}
    for r in runs:
        r["new"] = RENAME.get(r["key"], r["key"]) if r["key"] else resolve(r["strat"])

    # which OLD key keeps its numbers inside each NEW family: the new key itself if already in use,
    # else the old key whose first run is earliest
    by_new = collections.defaultdict(list)
    for r in runs:
        by_new[r["new"]].append(r)
    plan, counters = [], {}
    for new, rs in sorted(by_new.items()):
        olds = [r["key"] for r in rs if r["key"]]
        keeper = new if new in olds else (min(olds, key=lambda k: min(r["id"] for r in rs if r["key"] == k)) if olds else None)
        top = max([r["seq"] for r in rs if r["key"] == keeper and r["seq"] is not None] + [int(stored.get(keeper) or 0)] + [0])
        for r in rs:
            if r["key"] == new and r["seq"] is not None:
                continue                                      # already on the vocabulary
            if r["key"] == keeper and r["seq"] is not None:
                plan.append((r, new, r["seq"]))               # rename, number kept
            else:
                top += 1
                plan.append((r, new, top))                    # absorbed or never stamped: appended
        counters[new] = max([top, int(stored.get(new) or 0)] + [r["seq"] or 0 for r in rs if r["key"] == new])
    moved = [(r, k, s) for r, k, s in plan if s != r["seq"]]
    print("runs read %d | re-stamps %d | numbers that move %d" % (len(runs), len(plan), len(moved)))
    for r, k, s in plan:
        tag = "" if s == r["seq"] else "   <- number moves"
        print("  #%-4d %-34s %s-%s -> %s-%s%s" % (r["id"], str(r["strat"])[:34], r["key"], r["seq"], k, s, tag))
    print("counters ->", dict(sorted(counters.items())))
    if a.dry:
        return
    batch = db.batch(); nb = 0
    for r, k, s in plan:
        upd = {"famKey": k, "famSeq": int(s)}
        if r["key"] is not None:
            upd["famKeyOld"] = r["key"]; upd["famSeqOld"] = r["seq"]
        batch.update(u.collection("runs").document(str(r["id"])), upd); nb += 1
        if nb >= 400:
            batch.commit(); batch = db.batch(); nb = 0
    if nb:
        batch.commit()
    u.collection("meta").document("familyCounters").set({"counters": counters, "scheme": "stable-v1",
                                                           "vocabulary": "2026-09-24"})
    print("APPLIED")


if __name__ == "__main__":
    main()
