r"""tools/book_asif_series.py -- AS-IF daily P&L for every leg of every book config (owner 11-21, v91.71).

WHY. The owner wants every book in the book table (C:/EdgeLog/manager/open_board/book_legs.json) as a dropdown on the
NT8 PAPER and WEBULL PAPER ledgers, each leg with a switch that draws "how it would have done" on the paper chart.
Most legs are not traded anywhere (no paper, no box shadow), so their as-if series is a SIMULATION: the leg's pinned
champion parameters (the run number the book table names), the repo engine and that run's own cost, on current data,
over the paper window. Never the account.

WHAT IT DOES
  1. reads the book table, dedupes the legs (19 distinct ids across 24 books on 11-21);
  2. for each leg resolves its spec (strategy file, champion params, instrument / timeframe / session / source, cost,
     multiplier, book weight) from LEG_SPECS + the cached run docs (C:/EdgeLog/_anatomy_cache/runs, luckbar/runs,
     bookshadow_rundocs.json; a missing one is read from Firestore ONCE and cached);
  3. runs it through augur_engine.book._leg_trades (the code path a BOOK job uses) from WARM days before the window,
     keeps the trades that CLOSED on or after WINDOW_FROM, stamps them on the New York session day, and writes
       {d: [dates], p: [usd a day], n: [trades a day]}
     A trade whose exit is the master's LAST bar may still be open: it is left out of the days and reported as
     last_bar_usd (it lands on its real day on a later run);
  4. writes C:/EdgeLog/shadow_asif/book_asif.json and publishes Firestore users/<uid>/meta/book_asif (the page reads it).
A leg that cannot be simulated (no strategy file, no data, the run doc missing) gets {"reason": "..."} instead of a
series, and the page shows that reason.

INCREMENTAL. Each leg is cached under C:/EdgeLog/shadow_asif/cache/<ID>.json keyed by its spec + the master's last bar;
an unchanged leg is not re-run. A run with nothing new does not publish (a book-table change or --force does).
The page may also ask for legs it has no series for (meta/book_asif_req, written when a switch is flipped on a leg the
doc does not carry); those are built on the next run.

    python tools/book_asif_series.py               # build what changed, publish
    python tools/book_asif_series.py --no-publish  # local file only
    python tools/book_asif_series.py --force       # rebuild every leg
    python tools/book_asif_series.py --legs NOISE422,ORB234

Run from anywhere: the engine and its master registry are imported from the SHARED checkout (the worktree registry
trap). Read-only on the registry; never touches optimizer_history.db writes, orders or api/.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import sys
import time
import traceback

SHARED = r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, SHARED)          # the shared checkout's augur_engine + registry first

BOOK_TABLE = r"C:/EdgeLog/manager/open_board/book_legs.json"
OUT_DIR = os.environ.get("EDGELOG_BOOK_ASIF_DIR", r"C:\EdgeLog\shadow_asif")
RUNS_CACHE = r"C:\EdgeLog\_anatomy_cache\runs"
LUCK_CACHE = r"C:\EdgeLog\_anatomy_cache\luckbar\runs"
EXTRA_CACHE = r"C:\EdgeLog\_anatomy_cache\bookshadow_rundocs.json"
UID = "IO0K35JpLIcH9YK4C0pMNYUzZOM2"
# the paper window: NT8 PAPER starts 2026-08-11, WEBULL PAPER earlier legs from the summer; the page clips to each
# board's own first ledger day, so the series starts early enough for both
WINDOW_FROM = "2026-06-01"
WARM_DAYS = 330                      # NOISE's 104-day lookback, EODREV's 180-day beta, ENGU-Q's 1340-bar EMA
SCHEMA = 1

# Book-table leg id -> which run's champion it is, and anything the run doc does not say. `run` is the run the book
# table names (its pinned champion); `weight` is the book's size (TTMx3 = 3 ES, OPUS58c_h = half size).
LEG_SPECS = {
    "ENGUQ335":  {"run": 335},
    "NOISE422":  {"run": 422},
    "ORB234":    {"run": 234, "note": "book seat = run #547 walk-forward of the #234 exit; the #234 champion is replayed"},
    "TTMx3":     {"run": 369, "weight": 3.0, "note": "3 ES, the #369 seat"},
    "NOISE406":  {"run": 406},
    "NOISE304":  {"run": 304},
    "NOISE398":  {"run": 398, "note": "engine PASS run #528 holds the same file"},
    "NOISE382":  {"run": 382},
    "ORB546":    {"run": 546},
    "ORB314":    {"run": 314},
    "ORB421":    {"run": 421, "note": "= #257 seat"},
    "TTIBS300":  {"run": 300},
    "OPUS55a":   {"run": 524},
    "OPUS107a":  {"run": 518},
    "OPUS58c":   {"run": 543},
    "OPUS58c_h": {"run": 543, "weight": 0.5, "note": "half size"},
    "OPUS86a":   {"run": 526},
    "PICK6":     {"run": 511},
    "GLDNIGHT":  {"run": 541},
}
SOURCE_MAP = {   # a run doc's source_name -> (session, registry source)
    "rth - no-adj": ("rth", "db_noadj_rth"), "eth - no-adj": ("eth", "db_noadj_eth"),
    "rth - back-adjusted": ("rth", "db_adj_rth"), "eth - back-adjusted": ("eth", "db_adj_eth"),
    "(alpaca rth)": ("rth", "alpaca_split_rth"),
}
MULT = {"NQ": 20.0, "ES": 50.0, "YM": 5.0, "RTY": 50.0, "ZN": 1000.0, "MNQ": 2.0, "MES": 5.0}
STOCKS = {"SPY", "QQQ", "GLD", "IWM", "DIA"}


def _now_utc():
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load_json(p, default=None):
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _write_json(p, obj):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=1, default=str)
    os.replace(tmp, p)


def _db():
    import firebase_admin
    from firebase_admin import credentials, firestore
    cred = os.path.join(SHARED, "serviceAccount.json")
    if not firebase_admin._apps:
        firebase_admin.initialize_app(credentials.Certificate(cred))
    return firestore.client()


# ── run docs ─────────────────────────────────────────────────────────────────────────────────────────────
_EXTRA = None


def run_doc(rid, allow_fetch=True):
    """The run's doc (strategy, source_name, cost_pts, multiplier, champion) from the local caches, else Firestore once."""
    global _EXTRA
    for d in (RUNS_CACHE, LUCK_CACHE):
        p = os.path.join(d, "%d.json" % rid)
        if os.path.exists(p):
            doc = _load_json(p)
            if isinstance(doc, dict) and doc.get("strategy"):
                return doc
    if _EXTRA is None:
        _EXTRA = _load_json(EXTRA_CACHE, {}) or {}
    doc = _EXTRA.get(str(rid))
    if isinstance(doc, dict) and doc.get("strategy"):
        return doc
    if not allow_fetch:
        return None
    sys.path.insert(0, SHARED)
    import tools.runboard_watch as rw   # noqa: E402  (UID, real_client, run_ref)
    snap = rw.run_ref(rw.real_client(), rid).get(field_paths=[
        "id", "strategy", "scope", "best_params", "instrument", "timeframe", "session", "source_name", "cost_pts",
        "multiplier", "date_from", "date_to", "validate.champion"])
    doc = snap.to_dict() if getattr(snap, "exists", False) else None
    _EXTRA[str(rid)] = doc
    _write_json(EXTRA_CACHE, _EXTRA)
    return doc


def _session_source(doc):
    sn = str(doc.get("source_name") or "").lower()
    for k, v in SOURCE_MAP.items():
        if k in sn:
            return v
    return (str(doc.get("session") or "rth").lower(), None)


def leg_spec(leg_id, book_leg):
    """{strategy, params, instrument, timeframe, session, source, cost_pts, mult, weight, run} or raise ValueError(why)."""
    s = LEG_SPECS.get(leg_id)
    if not s:
        raise ValueError("no replay spec for this leg yet (add it to LEG_SPECS in tools/book_asif_series.py)")
    doc = run_doc(s["run"])
    if not doc:
        raise ValueError("run #%d doc not found" % s["run"])
    champ = ((doc.get("validate") or {}).get("champion")) or doc.get("best_params") or {}
    if not isinstance(champ, dict):
        champ = {}
    inst = str(doc.get("instrument") or "").upper()
    sess, src = _session_source(doc)
    mult = doc.get("multiplier")
    try:
        mult = float(mult) if mult and float(mult) > 0 else None
    except (TypeError, ValueError):
        mult = None
    if mult is None:
        mult = MULT.get(inst, 1.0)
    return {"run": s["run"], "strategy": doc["strategy"], "params": dict(champ), "instrument": inst,
            "timeframe": doc.get("timeframe") or "5m", "session": sess, "source": src,
            "cost_pts": float(doc.get("cost_pts") or 0), "mult": mult, "weight": float(s.get("weight", 1.0)),
            "params_from": "champion" if champ else "strategy defaults (the run stored no champion)",
            "note": s.get("note", "")}


def leg_kind(book_leg, spec=None):
    ins = str((book_leg or {}).get("instrument") or (spec or {}).get("instrument") or "").upper()
    if "STOCK" in ins or "ETF" in ins or ins in STOCKS or (spec and spec.get("instrument") in STOCKS):
        return "stock"
    return "futures"


# ── one leg ──────────────────────────────────────────────────────────────────────────────────────────────
def master_end(spec):
    from augur_engine.data import find_master
    m = find_master(spec["instrument"], spec["timeframe"], spec["session"], spec["source"])
    if m is None and spec["source"]:
        m = find_master(spec["instrument"], spec["timeframe"], spec["session"], None)
    if m is None:
        return None, None
    return m, str(m.get("date_to") or "")


def simulate(spec, date_to=None):
    """Closed trades by New York session day from WINDOW_FROM: (days {d: [usd, n]}, info)."""
    import numpy as np
    from augur_engine.book import _leg_trades
    warm = (dt.date.fromisoformat(WINDOW_FROM) - dt.timedelta(days=WARM_DAYS)).isoformat()
    leg = {k: spec[k] for k in ("strategy", "params", "instrument", "timeframe", "session", "source", "cost_pts",
                                "mult", "weight")}
    _out, info = _leg_trades(leg, warm, date_to, keep_state=True)
    st = info.get("_state") or {}
    sess_idx, last = st.get("sess_idx"), st.get("last")
    days, last_bar_usd, last_bar_n = {}, 0.0, 0
    for t, size in st.get("sized") or []:
        i = min(int(t[1]), last)
        usd = float(t[2]) * float(st["mult"]) * float(st["weight"]) * float(size)
        if i >= last:                       # exits on the master's last bar: may still be open
            last_bar_usd += usd
            last_bar_n += 1
            continue
        d = str(np.datetime_as_string(sess_idx[i], unit="D")) if sess_idx is not None else str(st["days_idx"][i])
        if d < WINDOW_FROM:
            continue
        a = days.setdefault(d, [0.0, 0])
        a[0] += usd
        a[1] += 1
    last_day = None
    try:
        last_day = str(np.datetime_as_string(sess_idx[last], unit="D")) if sess_idx is not None else None
    except Exception:
        pass
    return days, {"master": info.get("master"), "last_bar_usd": round(last_bar_usd, 2), "last_bar_n": last_bar_n,
                  "data_end": last_day}


def spec_key(spec, mend):
    blob = json.dumps({"s": spec, "end": mend, "w": WINDOW_FROM, "v": SCHEMA}, sort_keys=True, default=str)
    return hashlib.sha1(blob.encode()).hexdigest()[:16]


def build_leg(leg_id, book_leg, force=False, say=print):
    rec = {"id": leg_id, "name": book_leg.get("name") or leg_id, "run": book_leg.get("run") or "",
           "instrument": book_leg.get("instrument") or "", "size": book_leg.get("size") or "",
           "usd_per_year": book_leg.get("usd_per_year"), "src": "replay"}
    try:
        spec = leg_spec(leg_id, book_leg)
    except Exception as e:
        rec.update(kind=leg_kind(book_leg), reason=str(e))
        return rec, False
    rec["kind"] = leg_kind(book_leg, spec)
    rec.update(strategy=spec["strategy"], params_run=spec["run"], cost_pts=spec["cost_pts"], mult=spec["mult"],
               weight=spec["weight"], params_from=spec["params_from"], tf=spec["timeframe"], session=spec["session"])
    if spec.get("note"):
        rec["note"] = spec["note"]
    m, mend = master_end(spec)
    if m is None:
        rec["reason"] = "no %s %s %s master in the registry" % (spec["instrument"], spec["timeframe"], spec["session"].upper())
        return rec, False
    key = spec_key(spec, mend)
    cpath = os.path.join(OUT_DIR, "cache", "%s.json" % leg_id)
    cached = _load_json(cpath)
    if not force and isinstance(cached, dict) and cached.get("key") == key and "series" in cached:
        rec.update(cached["series"])
        return rec, False
    t0 = time.time()
    try:
        days, info = simulate(spec)
    except Exception as e:
        rec["reason"] = "replay failed: %s: %s" % (type(e).__name__, str(e)[:240])
        say("  %s FAILED %s" % (leg_id, rec["reason"]))
        traceback.print_exc()
        return rec, True
    ds = sorted(days)
    series = {"d": ds, "p": [round(days[d][0], 2) for d in ds], "n": [int(days[d][1]) for d in ds],
              "net": round(sum(days[d][0] for d in ds), 2), "trades": int(sum(days[d][1] for d in ds)),
              "data_end": info.get("data_end") or mend[:10], "master": info.get("master"),
              "last_bar_usd": info.get("last_bar_usd"), "last_bar_n": info.get("last_bar_n"),
              "built_at": _now_utc(), "secs": round(time.time() - t0, 1)}
    if not ds:
        series["empty"] = "no trades closed since %s" % WINDOW_FROM
    try:
        lag = (dt.date.today() - dt.date.fromisoformat(series["data_end"][:10])).days
    except Exception:
        lag = None
    if lag is not None and lag > 7:
        series["stale"] = "the %s %s master ends %s, so this series stops there (the data needs a refresh)" % (
            spec["instrument"], spec["timeframe"], series["data_end"][:10])
    rec.update(series)
    _write_json(cpath, {"key": key, "series": series})
    say("  %-10s %s  %3d trades  net %+10.2f  data to %s  (%.1fs)" % (
        leg_id, spec["strategy"], series["trades"], series["net"], series["data_end"], series["secs"]))
    return rec, True


# ── the whole table ──────────────────────────────────────────────────────────────────────────────────────
def distinct_legs(table):
    legs = {}
    for _k, b in (table.get("books") or {}).items():
        for l in b.get("legs") or []:
            if l.get("id") and l["id"] not in legs:
                legs[l["id"]] = l
    return legs


def requested_legs(db):
    try:
        snap = db.collection("users").document(UID).collection("meta").document("book_asif_req").get()
        d = snap.to_dict() if snap.exists else None
        return [str(x) for x in ((d or {}).get("legs") or [])]
    except Exception:
        return []


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--src", default=BOOK_TABLE)
    ap.add_argument("--legs", default="", help="comma list of leg ids (default: every leg of every book)")
    ap.add_argument("--force", action="store_true", help="rebuild every leg and publish")
    ap.add_argument("--no-publish", action="store_true")
    a = ap.parse_args(argv)
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    table = _load_json(a.src)
    if not isinstance(table, dict) or not table.get("books"):
        print("book table missing or empty: %s" % a.src)
        return 2
    legs = distinct_legs(table)
    db = None
    if not a.no_publish:
        try:
            db = _db()
            for r in requested_legs(db):
                if r not in legs:
                    print("requested leg %s is not in the book table - skipped" % r)
        except Exception as e:
            print("Firestore not reachable (%s) - local file only" % e)
            db = None
    want = [x.strip() for x in a.legs.split(",") if x.strip()] or list(legs)
    prev = _load_json(os.path.join(OUT_DIR, "book_asif.json"), {}) or {}
    out_legs = dict(prev.get("legs") or {})
    changed = False
    print("book as-if: %d distinct legs in %d books, window from %s" % (len(legs), len(table["books"]), WINDOW_FROM))
    for lid in want:
        if lid not in legs:
            print("  %s not in the book table" % lid)
            continue
        rec, ch = build_leg(lid, legs[lid], force=a.force)
        if out_legs.get(lid) != rec:
            changed = True
        out_legs[lid] = rec
    for lid in list(out_legs):          # a leg no longer in any book drops out
        if lid not in legs:
            del out_legs[lid]
            changed = True
    th = hashlib.sha1(json.dumps(table.get("books"), sort_keys=True, default=str).encode()).hexdigest()[:12]
    if th != prev.get("book_table_hash"):
        changed = True
    ends = sorted(r.get("data_end") for r in out_legs.values() if r.get("data_end"))
    doc = {"schema": SCHEMA, "generated_at": _now_utc() if changed or a.force else prev.get("generated_at", _now_utc()),
           "window_from": WINDOW_FROM, "data_end": ends[-1] if ends else None,
           "data_end_min": ends[0] if ends else None, "book_table_hash": th,
           "note": "simulated as-if: each leg's pinned champion on current data with its run's cost, closed trades by "
                   "New York day; never the account",
           "legs": out_legs}
    _write_json(os.path.join(OUT_DIR, "book_asif.json"), doc)
    ok = sum(1 for r in out_legs.values() if r.get("d") is not None)
    bad = {k: r.get("reason") for k, r in out_legs.items() if r.get("reason")}
    print("wrote %s: %d legs with a series, %d without%s" % (os.path.join(OUT_DIR, "book_asif.json"), ok, len(bad),
          "".join("\n  %s: %s" % kv for kv in bad.items())))
    if db is not None and (changed or a.force):
        ref = db.collection("users").document(UID).collection("meta")
        ref.document("book_asif").set(doc)
        try:
            ref.document("book_asif_req").set({"legs": [], "cleared_at": _now_utc()})
        except Exception:
            pass
        print("published users/<uid>/meta/book_asif (%d bytes)" % len(json.dumps(doc, default=str)))
    elif db is not None:
        print("nothing changed - not published")
    return 0


if __name__ == "__main__":
    sys.exit(main())
