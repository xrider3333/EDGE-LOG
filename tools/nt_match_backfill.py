"""tools/nt_match_backfill.py -- re-run the NinjaTrader fill match on past paper reports.

The NT8 PAPER ledger's NT chip reads users/{uid}/paper_reports/{day}.reconcile.legs[leg].matched
(index.html _ntSeen / _ntMatch, keyed leg|entryIso). Reports written while paper_reconcile.TOL_MIN
was 3 minutes filed one-bar-off NinjaTrader fills as live-only + shadow-only (2026-11-13: NZ 15:30 /
15:40 against book 15:35 / 15:45). This recomputes the NT legs' blocks with today's matcher.

QUOTA-AWARE. Only days on which fills.csv holds a paper-account (Sim101) round trip are looked at,
never a collection scan: per day 1 report read + one small paper_trades query (that day's NT-leg
rows). Only the NT legs' blocks are rewritten, with one update() per CHANGED day, in one batch.
Read-only on NinjaTrader (it reads the local fills.csv only).

  python tools/nt_match_backfill.py                 dry run: print what would change
  python tools/nt_match_backfill.py --apply         write the changed days
  python tools/nt_match_backfill.py --since 2026-11-01 --apply
"""
import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from api import paper_reconcile as pr     # noqa: E402

FILLS_CSV = r"C:\EdgeLog\fills.csv"
SHARED_KEY = r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG\serviceAccount.json"


def live_by_day(fills_path, account):
    """{YYYY-MM-DD: [live round trips]} for the paper account, NY dates (nt_sync)."""
    from api import nt_sync
    fills = [f for f in nt_sync.parse_fills(fills_path) if f.get("account") == account]
    out = {}
    for t in nt_sync.build_trades(fills):
        out.setdefault(t.get("date"), []).append(t)
    return out


def shadow_row(x):
    """The projection paper.py's _emit hands Layer 3 (todays_trades)."""
    return {"side": x.get("side"), "entryIso": x.get("entryIso"), "exitIso": x.get("exitIso"),
            "entry_px": x.get("entry_px"), "exit_px": x.get("exit_px"),
            "pnl_usd": x.get("pnl_usd"), "raw_pts": x.get("raw_pts"), "size": x.get("size")}


def _matched_keys(blk):
    return sorted(str(m.get("shadow_entry")) for m in ((blk or {}).get("matched") or []))


def plan_day(day, live, report, shadow_rows, live_expected=True):
    """(new_legs_patch, verdict) for one day, or (None, None) when nothing changes.

    shadow_rows: paper_trades docs of that day's NT legs (entry date == day)."""
    legs = sorted(pr.nt_legs(day))
    by_leg = {k: [] for k in legs}
    for x in shadow_rows:
        if x.get("leg") in by_leg and str(x.get("entryIso") or "")[:10] == day:
            by_leg[x["leg"]].append(shadow_row(x))
    rec = pr.match_day(by_leg, live)
    old = dict(((report or {}).get("reconcile") or {}).get("legs") or {})
    patch = {}
    for k in legs:
        # Only a leg whose MATCHED set moves is rewritten: that is what the chip reads, and a day from
        # before the paper account switched (no book rows for it here) must not be churned.
        new = rec["legs"].get(k) or {}
        if _matched_keys(new) != _matched_keys(old.get(k)):
            patch[k] = new
    if not patch:
        return None, None
    merged = dict(old)
    merged.update(patch)
    v = pr.verdict({"legs": merged, "unattributed": rec.get("unattributed")},
                   live_expected=live_expected, only_legs=set(legs))
    return patch, v


def _db():
    import firebase_admin
    from firebase_admin import credentials, firestore
    if not firebase_admin._apps:
        key = next(k for k in (os.path.join(ROOT, "serviceAccount.json"), SHARED_KEY) if os.path.exists(k))
        firebase_admin.initialize_app(credentials.Certificate(key))
    return firestore.client()


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default="2026-11-01")
    ap.add_argument("--fills", default=FILLS_CSV)
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args(argv)
    from api import nt_account
    from api.paper import NT_STRATEGIES_ENABLED
    from tools.paper_review_routine import UID
    from google.cloud.firestore_v1.base_query import FieldFilter
    live = live_by_day(a.fills, nt_account.paper_account())
    days = sorted(d for d in live if d and d >= a.since)
    db = _db()
    u = db.collection("users").document(UID)
    reads = writes = 0
    batch = db.batch()
    for day in days:
        legs = sorted(pr.nt_legs(day))
        snap = u.collection("paper_reports").document(day).get()
        reads += 1
        if not snap.exists:
            print(f"{day}: no report doc, skipped")
            continue
        q = (u.collection("paper_trades").where(filter=FieldFilter("run_date", "==", day))
             .where(filter=FieldFilter("leg", "in", legs)))
        rows = [s.to_dict() for s in q.stream()]
        reads += max(1, len(rows))
        patch, v = plan_day(day, live[day], snap.to_dict(), rows, live_expected=NT_STRATEGIES_ENABLED)
        if not patch:
            print(f"{day}: unchanged ({len(rows)} book rows, {len(live[day])} NT trades)")
            continue
        for k, blk in patch.items():
            print(f"{day}: {k} matched {len(blk['matched'])}, shadow-only {len(blk['shadow_only'])}, "
                  f"live-only {len(blk['live_only'])}")
        upd = {f"reconcile.legs.{k}": blk for k, blk in patch.items()}
        upd["reconcile.verdict"] = v
        upd["reconcile.tol_min"] = pr.TOL_MIN
        upd["reconcile.rematched_at"] = __import__("datetime").datetime.now().isoformat(timespec="seconds")
        if a.apply:
            batch.update(snap.reference, upd)
            writes += 1
    if a.apply and writes:
        batch.commit()
    print(f"days looked at {len(days)}, Firestore reads ~{reads}, writes {writes}"
          + ("" if a.apply else " (dry run: nothing written)"))


if __name__ == "__main__":
    main()
