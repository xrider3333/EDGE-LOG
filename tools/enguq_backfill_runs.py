"""BACKFILL the run-record JSONL from the run registry (MANAGER #116, the past month on one scatter).

The owner wants every run of the past month on one scatter with the four numbers beside it. The run
docs do NOT carry the four numbers: they store a cumulative curve that is per TRADE, and
`four_numbers` on a per-trade curve gives a Sortino on the wrong convention - the exact mistake that
function exists to stop. So this tool does not read numbers out of the doc. It takes each run's
CHAMPION parameters, re-runs them through the engine on that run's own master and window, builds the
DAILY mark-to-market curve the house values drawdown on, and computes the four numbers from that.

WHAT THE LINES ARE, and what they are NOT. One line per run per STAGE, where a stage is the run's own
window split at the lockbox boundary:
  preWF  the optimize window before the first walk-forward fold   (the champion over it)
  WF     the walk-forward window                                  (the champion over it)
  LB     the lockbox                                              (the champion over it)
Every line is **the champion over that stretch**, NOT the walk-forward chain, which stitches a
different parameter set per fold. A chain's daily curve could not be rebuilt for any run before
2026-10-18, because the chain's trade bar indices were not stored - that is what the store-the-trades
change (`analytics.wf_oos_block`, shipped today) fixes for every run from here on. Each line says so
in its note, so nobody reads a champion-over-WF figure as a walk-forward result.

    python tools/enguq_backfill_runs.py --since 2026-09-18 --family ENGU-Q [--dry-run]
"""
import argparse
import datetime as _dt
import os
import sys

REPO = r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"
UID = "IO0K35JpLIcH9YK4C0pMNYUzZOM2"
SESSION_OF = {"db_adj_eth": "eth", "db_noadj_eth": "eth", "db_adj_rth": "rth", "db_noadj_rth": "rth",
              "alpaca_split_rth": "rth", "tv": "eth"}
LB_START = "2025-07-01"          # the house lockbox boundary for the 2010-2026 window


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default="2026-09-18")
    ap.add_argument("--family", default="ENGU-Q")
    ap.add_argument("--lane", default="ENGUQ")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    sys.path.insert(0, REPO)
    sys.path.insert(0, os.path.join(REPO, "tools"))
    os.chdir(REPO)
    import numpy as np
    import pandas as pd
    import firebase_admin
    from firebase_admin import credentials, firestore
    from augur_engine.data import find_master, load_master_arrays
    from augur_engine.drawdowns import four_numbers
    from augur_engine.engine import run_backtest
    from run_record import write_record            # ELWA's writer on main (MANAGER #129/#130):
    # ONE writer, one schema. It takes the DAILY series and measures the four numbers itself
    # through augur_engine.drawdowns.four_numbers, so this tool hands it the curve, not figures.

    sa = os.path.join(REPO, "serviceAccount.json")
    if not firebase_admin._apps:
        firebase_admin.initialize_app(credentials.Certificate(sa))
    db = firestore.client()
    u = db.collection("users").document(UID)
    runs = []
    for d in u.collection("runs").where(filter=firestore.FieldFilter("famKey", "==", a.family)).stream():
        r = d.to_dict() or {}
        if str(r.get("timestamp") or "") >= a.since:
            runs.append(r)
    runs.sort(key=lambda r: str(r.get("timestamp")))
    print("%d %s runs since %s" % (len(runs), a.family, a.since))

    for r in runs:
        rid = r.get("id")
        strat, inst, tf = r.get("strategy"), r.get("instrument"), r.get("timeframe")
        src = r.get("data_source")
        params = r.get("best_params") or {}
        cost = float(r.get("cost_pts") or 0.0)
        mult = float(r.get("multiplier") or 1.0)
        d0, d1 = r.get("date_from"), r.get("date_to")
        print("\n#%s %s %s %s %s cost %.4f mult %s %s..%s" % (rid, strat, inst, tf, src, cost, mult, d0, d1))
        if not params:
            print("  SKIPPED: no best_params stored - nothing to re-run")
            continue
        sess = SESSION_OF.get(src)
        try:
            m = find_master(inst, tf, sess, src)
            arr = load_master_arrays(m, date_from=d0, date_to=d1)
            res = run_backtest(strat, arrays=arr, params=params, cost_pts=cost, return_trades=True)
        except Exception as e:                                    # noqa: BLE001
            print("  SKIPPED: %s" % e)
            continue
        trades = sorted((int(t[0]), int(t[1]), float(t[2])) for t in res["trades"])
        ix = pd.DatetimeIndex(arr["index"])
        n = len(ix)
        close = np.asarray(arr["close"], float)
        day = ix.tz_localize(None).normalize() if ix.tz is not None else ix.normalize()
        marks = np.r_[np.nonzero(np.diff(day.view("i8")))[0], n - 1]
        md = day[marks]
        # DAILY MARK TO MARKET: an open position is valued at every session close it is still open
        # through, so a multi-week hold's drawdown is seen on the days it happens (BOOK round 56).
        eq = np.zeros(len(marks))
        for i0, i1, pts in trades:
            pnl = pts * mult
            x0, x1 = float(close[min(i0, n - 1)]), float(close[min(i1, n - 1)])
            mv = (x1 - x0) * mult
            side = 1.0 if (mv == 0 or (mv > 0) == (pnl > 0)) else -1.0
            om = (marks > i0) & (marks < i1)
            eq[om] += side * (close[marks[om]] - x0) * mult
            eq[marks >= i1] += pnl
        daily = pd.Series(eq, index=md).groupby(level=0).last().diff()
        daily.iloc[0] = eq[0]
        n_tr = {}
        for i0, _i1, _p in trades:
            n_tr[str(day[i0].date())] = n_tr.get(str(day[i0].date()), 0) + 1

        wf0 = _wf_start(r, ix)
        stages = [("preWF", daily.index[0], pd.Timestamp(wf0) - pd.Timedelta(days=1)),
                  ("WF", pd.Timestamp(wf0), pd.Timestamp(LB_START) - pd.Timedelta(days=1)),
                  ("LB", pd.Timestamp(LB_START), daily.index[-1])]
        for stage, s0, s1 in stages:
            sl = daily[(daily.index >= s0) & (daily.index <= s1)]
            if len(sl) < 2:
                print("  %-5s %s..%s  too short (%d days)" % (stage, s0.date(), s1.date(), len(sl)))
                continue
            f = four_numbers(list(sl), years=(s1 - s0).days / 365.25)
            ntr = sum(v for k, v in n_tr.items() if s0 <= pd.Timestamp(k) <= s1)
            print("  %-5s %s..%s  ROC@30k %8s  DD5 %10s  DD%% %6s  Sortino %6s  trades %5d" %
                  (stage, s0.date(), s1.date(),
                   "%.2f" % f["roc30"] if f["roc30"] is not None else "-",
                   "%.0f" % f["dd5_usd"], "%.2f" % f["dd_pct_peak"],
                   "%.3f" % f["sortino"] if f["sortino"] is not None else "-", ntr))
            if a.dry_run:
                continue
            write_record(a.lane, "runner", stage, strategy=strat, family=a.family,
                         instrument=inst, timeframe=tf, run_id=rid, ts=str(r.get("timestamp")),
                         daily=list(sl), dates=[d.date().isoformat() for d in sl.index],
                         years=(s1 - s0).days / 365.25, trades=ntr, cost_pt=cost,
                         note="BACKFILL #116: the run's CHAMPION over this stretch on %s, daily "
                              "mark-to-market - NOT the walk-forward chain (no run before "
                              "2026-10-18 stored the chain's bar indices)" % m.get("filename"))


def _wf_start(r, ix):
    """The first walk-forward fold's start date, from the run's own stored fold geometry."""
    import pandas as pd
    t = r.get("top10_results") or []
    tb = [x.get("train_bars") for x in t if x.get("train_bars")]
    if tb and len(ix) > tb[0]:
        return pd.Timestamp(ix[int(tb[0])]).tz_localize(None).normalize()
    return pd.Timestamp("2016-10-12")          # #335's own first fold, the house default


if __name__ == "__main__":
    sys.exit(main())
