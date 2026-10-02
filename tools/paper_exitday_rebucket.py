"""One-shot: re-bucket the stored PAPER report docs from ENTRY-day to EXIT-day money.

OWNER GO 2026-10-02 (via MANAGER): the board and the BOOK figure count a trade on the day it CLOSES.
The nightly run (api/paper.py + api/paper_exitday.py) does that from the first night after this
shipped, and re-merges the previous 7 report days each night. Report docs older than that still hold
the old ENTRY-day figures. This script rebuilds every stored paper_reports doc's per-leg, blend, BOOK,
the weighted-sum shadow books and the VT shadow from the paper_trades docs, by exit day, using the one
rule in api/paper_exitday.py.

  python tools/paper_exitday_rebucket.py              # DRY RUN (default): reads, prints, writes nothing
  python tools/paper_exitday_rebucket.py --apply      # merge-writes ONLY the changed pnl_usd fields
  python tools/paper_exitday_rebucket.py --days 10    # how many recent report days to print (default 10)

Safety:
  * Read-only unless --apply. --apply writes `set(payload, merge=True)` with only pnl_usd fields; no
    doc is created or deleted, no other field is touched.
  * Only legs that HAVE trade docs are re-bucketed; a leg with none keeps its stored figure.
  * A trade doc written before the exit-day change has no `open` field. For those, an ETH leg's trade
    whose exit is within two minutes of that leg's newest report `data_fresh_thru` is treated as OPEN
    (the strategy files close a held position at the last bar); everything else is closed. Run it after
    the first nightly run following the ship and every doc carries the real flag - the inference is only
    for a run before that, and the output says how many it inferred.
  * It reads every paper_trades doc once (a few thousand reads) - run it by hand, not on a timer.
"""
import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
sys.path.insert(0, ROOT)

from api import paper_exitday as xd  # noqa: E402

UID = "IO0K35JpLIcH9YK4C0pMNYUzZOM2"
PAPER_START = "2026-08-11"
_OPEN_SLACK_S = 120


def _db():
    import firebase_admin
    from firebase_admin import credentials, firestore
    if not firebase_admin._apps:
        cred_path = next((p for p in (
            os.path.join(ROOT, "serviceAccount.json"),
            os.path.expanduser(r"~\OneDrive\Desktop\EDGE-LOG\serviceAccount.json"),
        ) if os.path.exists(p)), None)
        if not cred_path:
            raise SystemExit("serviceAccount.json not found (checked this checkout and the shared one)")
        firebase_admin.initialize_app(credentials.Certificate(cred_path))
    return firestore.client()


def _eth_legs():
    """Leg keys that run the ETH session (api/paper.py PAPER_LEGS); ENGUQ by name if that cannot load."""
    try:
        from api import paper
        out = {l["key"] for l in paper.PAPER_LEGS if str(l.get("session", "rth")).lower() != "rth"}
        out |= {l["emit_ungated_as"] for l in paper.PAPER_LEGS
                if l.get("emit_ungated_as") and str(l.get("session", "rth")).lower() != "rth"}
        return out
    except Exception:
        return None


def close_day_of(doc, *, is_open):
    """(close day iso or None, exit date iso) of one trade doc, old or new."""
    if is_open:
        return None
    if doc.get("close_day"):
        return doc["close_day"]
    iso = str(doc.get("exitIso") or "")[:10]
    if len(iso) != 10:
        return None
    import datetime as dt
    return xd.roll_weekend(dt.date.fromisoformat(iso)).isoformat()


def build_by_day(trade_docs, reports, eth_legs):
    """({leg: {close day: pnl}}, stats) from paper_trades docs. Open trades count on no day."""
    fresh = {}
    for rid in sorted(reports):
        for k, blk in (reports[rid].get("legs") or {}).items():
            if isinstance(blk, dict) and blk.get("data_fresh_thru"):
                fresh[k] = float(blk["data_fresh_thru"])           # newest report wins (sorted ascending)
    by_day, n_closed, inferred, open_docs = {}, 0, 0, []
    for d in trade_docs:
        k = d.get("leg")
        if not k:
            continue
        if "open" in d:
            op = bool(d["open"])
        else:
            inferred += 1
            isl = (eth_legs is None and str(k).startswith("ENGUQ")) or (eth_legs is not None and k in eth_legs)
            ft = fresh.get(k)
            op = bool(isl and ft and float(d.get("exitTime") or 0) >= ft - _OPEN_SLACK_S)
        if op:
            open_docs.append(d)
            by_day.setdefault(k, {})
            continue
        cd = close_day_of(d, is_open=False)
        if cd is None:
            continue
        by_day.setdefault(k, {})
        by_day[k][cd] = by_day[k].get(cd, 0.0) + float(d.get("pnl_usd") or 0.0)
        n_closed += 1
    return by_day, {"closed": n_closed, "open": len(open_docs), "inferred_open_flag": inferred,
                    "open_docs": open_docs}


def plan(trade_docs, reports, eth_legs=None):
    """{report day: payload} for every report doc that changes, plus the stats. Pure."""
    by_day, stats = build_by_day(trade_docs, reports, eth_legs)
    out = {}
    for day in sorted(reports):
        pl = xd.rebucket_payload(reports[day], by_day, day)
        if pl:
            out[day] = pl
    return out, by_day, stats


def _after(old, payload):
    """The stored doc with the payload merged in (what the doc will read after --apply)."""
    new = {k: (dict(v) if isinstance(v, dict) else v) for k, v in old.items()}
    new["legs"] = {k: dict(v) if isinstance(v, dict) else v for k, v in (old.get("legs") or {}).items()}
    for k, v in payload.items():
        if k == "legs":
            for lk, lv in v.items():
                new["legs"][lk].update(lv)
        else:
            new[k] = {**(old.get(k) or {}), **v}
    return new


def _g(doc, *path):
    for p in path:
        doc = (doc or {}).get(p) if isinstance(doc, dict) else None
    try:
        return float(doc)
    except (TypeError, ValueError):
        return None


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true", help="write the re-bucketed figures (default: dry run)")
    ap.add_argument("--days", type=int, default=10, help="recent report days to print")
    ap.add_argument("--uid", default=UID)
    a = ap.parse_args()

    db = _db()
    base = db.collection("users").document(a.uid)
    reports = {s.id: (s.to_dict() or {}) for s in base.collection("paper_reports").stream()
               if s.id >= PAPER_START}
    trade_docs = [s.to_dict() or {} for s in base.collection("paper_trades").stream()]
    changes, by_day, st = plan(trade_docs, reports, _eth_legs())

    print(f"{'APPLY' if a.apply else 'DRY RUN'} - {len(reports)} report docs, {len(trade_docs)} trade docs "
          f"({st['closed']} closed, {st['open']} open; open flag inferred for {st['inferred_open_flag']} legacy docs)")
    days = sorted(reports)[-a.days:]
    print(f"\nBOOK and ENGU-Q #335, last {len(days)} report days: ENTRY-day (stored) -> EXIT-day (new)")
    print(f"{'day':<11}{'BOOK before':>13}{'BOOK after':>13}{'delta':>11}{'ENGUQ_335 before':>19}{'after':>11}")
    for d in days:
        old = reports[d]
        new = _after(old, changes.get(d) or {})
        bb, ba = _g(old, "book", "pnl_usd"), _g(new, "book", "pnl_usd")
        eb, ea = _g(old, "legs", "ENGUQ_335", "pnl_usd"), _g(new, "legs", "ENGUQ_335", "pnl_usd")
        f = lambda v: "-" if v is None else f"{v:,.0f}"
        print(f"{d:<11}{f(bb):>13}{f(ba):>13}{(f((ba or 0) - (bb or 0))):>11}{f(eb):>19}{f(ea):>11}")
    tb = sum(_g(r, "book", "pnl_usd") or 0.0 for r in reports.values())
    ta = sum(_g(_after(r, changes.get(d) or {}), "book", "pnl_usd") or 0.0 for d, r in reports.items())
    print(f"\nBOOK summed over every report day: {tb:,.0f} -> {ta:,.0f} (difference {ta - tb:+,.0f})")
    if st["open_docs"]:
        print(f"{len(st['open_docs'])} open trade(s) excluded from every day (unrealised marks):")
        for d in st["open_docs"]:
            print(f"   {d.get('leg')}  entered {str(d.get('entryIso'))[:16]}  mark {float(d.get('pnl_usd') or 0):,.0f}")
    # closed money that lands on a day with no report doc would be invisible to the report docs
    orphan = {}
    for k, m in by_day.items():
        for day, v in m.items():
            if day not in reports and day >= PAPER_START:
                orphan[day] = orphan.get(day, 0.0) + v
    if orphan:
        print("closed money on days with NO report doc (not in any report figure; the board still shows it):")
        for day in sorted(orphan):
            print(f"   {day}: {orphan[day]:,.0f} (all legs, unweighted)")
    print(f"\n{len(changes)} of {len(reports)} report docs would change.")
    if not a.apply:
        print("Dry run only - nothing written. Re-run with --apply to merge-write the pnl fields.")
        return
    col = base.collection("paper_reports")
    for day, pl in changes.items():
        col.document(day).set(pl, merge=True)
    print(f"Wrote {len(changes)} docs.")


if __name__ == "__main__":
    main()
