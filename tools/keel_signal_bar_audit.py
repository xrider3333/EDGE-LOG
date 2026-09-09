"""SIGNAL-BAR AUDIT of everything this session concluded.

A hard rule was recorded today: trade tuples are (fill_bar, exit, pnl, side, entry_px), so t[0] is
the bar the trade FILLS in and the decision was made one bar earlier. Any per-trade condition read
at t[0] sees a bar the rule never had - and a NOISE candidate flipped from -$44k to +$6.7k when
moved one bar back, so this is not theoretical.

Every mask this session used was built at t[0]. So: rebuild each one at t[0]-1, count how many tags
move, and re-run the guard. Reasoning about it is not enough - the check is cheap and decisive.

Prediction, stated first so it can be wrong: the squeeze should be immune, because it is defined as
the last COMPLETE 60-minute group BEFORE the bar, so it cannot see the fill bar's close and can only
change when t[0] and t[0]-1 straddle an hour boundary. The clock masks should move only for fills on
the exact boundary bar (14:00 for the statement, 08:30 for the releases). If either moves more than
that, something is wrong with the reasoning and the numbers decide.
"""
import os, sys, numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = r"C:/Users/xride/OneDrive/Desktop/EDGE-LOG"
os.chdir(ROOT); sys.path.insert(0, ROOT); sys.path.insert(0, os.path.join(ROOT, "tools"))
from tilt_guard import guard                                       # noqa: E402
from keel_event_check import P243, P304, naive_et                  # noqa: E402
from augur_engine import ml_keel                                   # noqa: E402
from augur_engine.data import find_master, load_master_arrays      # noqa: E402
from augur_engine.engine import run_backtest                       # noqa: E402

WF0, LB0, END = "2016-05-02", "2025-02-11", "2026-08-12"
S = np.load(os.path.join(HERE, "v12_state.npz"), allow_pickle=True)
arr = load_master_arrays(find_master("NQ", "5m", "rth", "db_noadj_rth"), date_from="2010-06-07", date_to=END)
idx = naive_et(arr["index"])
F, names = ml_keel.keel_features(arr)
sq = names.index("sq60_on")
fomc = ml_keel.fomc_decision_days()
verdicts = {}

for rid, params, fname in (("243", P243, "NOISE_1_1_SBS_V90.py"), ("304", P304, "NOISE_1_1_NBHD.py")):
    P = S[f"{rid}_P"]; E = np.asarray(S[f"{rid}_E"], int)
    Em1 = np.clip(E - 1, 0, len(idx) - 1)
    ts_fill = idx[np.clip(E, 0, len(idx) - 1)]
    ts_sig = idx[Em1]
    wf = (ts_fill >= pd.Timestamp(WF0)) & (ts_fill < pd.Timestamp(LB0))
    lb = ts_fill >= pd.Timestamp(LB0)

    on_fill = F[np.clip(E, 0, len(F) - 1), sq] > 0
    on_sig = F[Em1, sq] > 0
    pre_fill = np.array([(t.date() in fomc) and t.hour < 14 for t in ts_fill])
    pre_sig = np.array([(t.date() in fomc) and t.hour < 14 for t in ts_sig])

    print("=" * 100)
    print(f"#{rid}: {len(P)} trades")
    print(f"  squeeze tag moves on {int((on_fill != on_sig).sum())} trades "
          f"({100*(on_fill != on_sig).mean():.2f}%)   [fill-bar {int(on_fill.sum())} vs signal-bar {int(on_sig.sum())} tagged]")
    print(f"  statement tag moves on {int((pre_fill != pre_sig).sum())} trades "
          f"({100*(pre_fill != pre_sig).mean():.2f}%)   [fill-bar {int(pre_fill.sum())} vs signal-bar {int(pre_sig.sum())} tagged]")

    # 1. the adoption, re-tagged at the signal bar
    am_sig = np.array([t.hour < 14 for t in ts_sig])
    alld = np.array([t.date() for t in ts_sig]); u = np.array(sorted(set(alld)))
    nxt = {u[i]: u[i + 1] for i in range(len(u) - 1)}
    plc = np.array([nxt.get(t.date()) in fomc for t in ts_sig]) & am_sig
    r = guard(P, ts_fill, S[f"{rid}_size_v11"], pre_sig, 0.5, wf, lb, window=am_sig,
              subgroup=(ts_sig.dayofweek.values == 2), placebo_mask=plc, perm=2000,
              label=f"#{rid} v12 statement half-size, TAGGED AT THE SIGNAL BAR")
    print(r["report"]); verdicts[f"#{rid} v12 (signal bar)"] = r["passed"]

    # 2. compression standalone on raw, re-tagged
    r2 = guard(P, ts_fill, np.ones(len(P)), on_sig, 1.5, wf, lb, permute="shift", perm=2000,
               label=f"#{rid} compression 1.5x on raw, TAGGED AT THE SIGNAL BAR")
    print(r2["report"]); verdicts[f"#{rid} compression raw (signal bar)"] = r2["passed"]

    # 3. compression inside v12, re-tagged
    v12 = S[f"{rid}_size_v12"]
    without = np.where(on_fill, v12 / 1.5, v12)
    r3 = guard(P, ts_fill, without, on_sig, 1.5, wf, lb, permute="shift", perm=2000,
               label=f"#{rid} compression inside v12, TAGGED AT THE SIGNAL BAR")
    print(r3["report"]); verdicts[f"#{rid} compression in v12 (signal bar)"] = r3["passed"]

print("\n" + "=" * 100)
WAS = {"#243 v12 (signal bar)": True, "#304 v12 (signal bar)": True,
       "#243 compression raw (signal bar)": True, "#304 compression raw (signal bar)": None,
       "#243 compression in v12 (signal bar)": False, "#304 compression in v12 (signal bar)": True}
for k in sorted(verdicts):
    w = WAS.get(k)
    tag = "same" if w is None or w == verdicts[k] else "*** CHANGED ***"
    print(f"  {k:42s} at the fill bar {str(w):5s} -> at the signal bar "
          f"{'PASS' if verdicts[k] else 'FAIL'}   {tag}")
