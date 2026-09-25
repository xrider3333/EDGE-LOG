"""SETUPS round 1 - the overlap test (SETUPS_PREREG.md section 7, third verdict leg).

Is CBU-Q its own edge, or a copy of a crown's factor? Re-runs ORB #314 and NOISE #382 from their
run docs (strategy, params, instrument, data, cost - the queue_guard loader) and CBU-Q with the
params given, all over the validate window 2010-06-07..2026-04-06, and reports per crown:
  - shared days: sessions on which both took a trade (ET calendar date of the entry bar),
  - same-direction share of those shared days,
  - CBU-Q's net on days the crown did NOT trade (the crown is flat), and that net as a share
    of CBU-Q's own net.
Pre-registered pass: on BOTH crowns' flat days CBU-Q nets > 0 and >= 30% of its own net.

    python tools/setups_r1_overlap.py '{"level_mode":"pdh",...}'      (run from the shared checkout)
"""
import os, sys, json
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA_REPO = ROOT if os.path.exists(os.path.join(ROOT, "optimizer_history.db")) else r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"
sys.path.insert(0, DATA_REPO)
sys.path.insert(0, os.path.join(DATA_REPO, "tools"))
from augur_engine.data import find_master, load_master_arrays      # noqa: E402
from augur_engine.engine import run_backtest                        # noqa: E402
import queue_guard as QG                                            # noqa: E402

WIN = ("2010-06-07", "2026-04-06")
SPLIT = "2025-07-07"
CRED = os.path.join(DATA_REPO, "serviceAccount.json")


def day_trades(strategy, params, instrument, timeframe, session, source, cost_pts, mult):
    m = find_master(instrument, timeframe, session, source)
    arr = load_master_arrays(m, date_from=WIN[0], date_to=WIN[1])
    idx = pd.DatetimeIndex(arr["index"])
    resolved, _, _ = QG.resolve_params(strategy, params)
    r = run_backtest(strategy, arrays=arr, params=dict(resolved), cost_pts=cost_pts, return_trades=True)
    rows = []
    for t in (r or {}).get("trades") or []:
        side = t[3] if len(t) > 3 else 0
        rows.append((idx[int(t[0])].date(), int(side), float(t[2]) * mult))
    df = pd.DataFrame(rows, columns=["day", "side", "usd"])
    return df


def main():
    params = json.loads(sys.argv[1]) if len(sys.argv) > 1 else {}
    cbu = day_trades("CBUQ_1M_1_0.py", params, "NQ", "1m", "eth", "db_noadj_eth", 0.533, 20.0)
    print("CBU-Q  %d trades, net $%s, params %s" % (len(cbu), format(round(cbu.usd.sum()), ","), json.dumps(params, sort_keys=True)))
    ok_all = True
    for run_id in (314, 382):
        kw, d = QG._guard_kwargs_from_run(run_id, CRED)
        crown = day_trades(kw["strategy_file"], kw["params"], kw["instrument"], kw["timeframe"], kw["session"], kw["source"],
                           kw["cost_pts"], kw["mult"])
        cdays = set(crown.day)
        cside = crown.groupby("day").side.first().to_dict()
        shared = cbu[cbu.day.isin(cdays)]
        same = sum(1 for _, r in shared.iterrows() if cside.get(r.day) == r.side)
        flat = cbu[~cbu.day.isin(cdays)]
        own = cbu.usd.sum()
        share = flat.usd.sum() / own if own > 0 else float("nan")
        ok = flat.usd.sum() > 0 and share >= 0.30
        ok_all &= ok
        for lbl, sub in (("selection", flat[flat.day < pd.Timestamp(SPLIT).date()]),
                         ("sealed", flat[flat.day >= pd.Timestamp(SPLIT).date()])):
            print("   #%d flat-day %-9s n=%4d net=$%s" % (run_id, lbl, len(sub), format(round(sub.usd.sum()), ",")))
        print("#%d %s: %d trades on %d days | shared days %d (%.0f%% of CBU-Q trades), same direction %d of %d | "
              "CBU-Q on crown-flat days: %d trades, net $%s = %.0f%% of its own net -> %s" % (
                  run_id, d.get("strategy"), len(crown), len(cdays), len(shared), 100 * len(shared) / max(1, len(cbu)),
                  same, len(shared), len(flat), format(round(flat.usd.sum()), ","), 100 * share, "PASS" if ok else "FAIL"))
    print("OVERLAP VERDICT:", "PASS" if ok_all else "FAIL")


if __name__ == "__main__":
    main()
