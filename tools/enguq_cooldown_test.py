"""BATTERY V -- re-entry cooldown on the #226 ETH config. Owner item 896.

PRE-REGISTERED 2026-08-26, BEFORE any result was read.

THE COMPLAINT. Owner, on paper row 896: "no strategy should be messing up by taking 5
trades in a row like that." ENGU-Q can re-enter within a bar or two of an exit, so a
choppy stretch produces a cluster of near-identical trades that each pay full cost.

THE KNOB. augur_strategies/ENGUQ_1M_ETH_1_0.py gained `cooldown_bars` (default 0 = the
deployed behaviour): after a trade closes, ignore entry signals for that many 1m bars.
Strictly causal -- it reads only the bar index of an exit that already happened.

WHY THIS MIGHT STILL FAIL, stated up front. ENGUQ.md section 1.1: the top 10 winners are 83%
of all net profit. Any filter that removes trades risks removing one of those, and every
filter tried so far (battery U's regime gate, 13 risk-tightening variants, risk-parity
sizing) has cut the winners faster than the losers. A cooldown is not obviously different.
The honest prior is that this fails. It is worth running because it targets something
specific and observed -- clustering -- rather than trying to be generally safer.

THE BAR (judge on PF + lockbox, NOT net/DD -- ENGUQ.md, memory edgelog-netdd-unreliable):
  W1  PF        >= 1.332      the control's
  W2  lockbox PF>= 1.493      the control's
  W3  lockbox net >= $80,000  house bar
  W4  drawdown falls by a LARGER fraction than net does
  W5  stuck guard: longest hold <= 120d AND >= 40 lockbox trades
  ADOPT only on 4 of 5 or better, consistent with battery U's scoring.

Window pinned to the certified basis (memory edgelog-rerun-window-pinning):
2010-06-07 .. 2026-06-30, NQ 1m ETH, cost 0.533 x $20, 1 contract.
Control = cooldown 0 and must reproduce n=2843 / $434,721.12 exactly, else abort.

GRID: 5, 15, 30, 60, 120, 240 bars (5 minutes .. 4 hours on a 1m tape).
"""
import sys
import json

import numpy as np
import pandas as pd

import os
import importlib.util

# TWO DIFFERENT ROOTS, ON PURPOSE.
#
# The STRATEGY under test must come from THIS checkout -- that is the whole point of
# running the sweep from a worktree. The first attempt hardcoded the desktop repo, so it
# imported the UNPATCHED engine and every cooldown cell returned numbers byte-identical
# to control. That reads exactly like "the knob does nothing", which is a wrong answer
# delivered confidently rather than an error. A sweep that silently tests the wrong code
# is far worse than one that crashes -- hence the explicit abort below.
#
# The DATA (optimizer_history.db + augur_uploads/) lives only in the main checkout: a git
# worktree does not carry it, and augur_engine.paths derives ROOT from the package
# location, so augur_engine must be imported from there. Pointing both at the worktree
# fails with "no such table: csv_files".
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_ROOT = os.environ.get("EDGELOG_DATA_ROOT") or os.path.join(
    os.path.expanduser("~"), "OneDrive", "Desktop", "EDGE-LOG")
sys.path.insert(0, DATA_ROOT)
from augur_engine.data import find_master, load_master_arrays          # noqa: E402

_SP = os.path.join(REPO, "augur_strategies", "ENGUQ_1M_ETH_1_0.py")
_spec = importlib.util.spec_from_file_location("_enguq_eth_under_test", _SP)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
run_backtest = _mod.run_backtest
print("strategy under test :", _SP)
print("data root           :", DATA_ROOT)
if "cooldown_bars" not in run_backtest.__code__.co_varnames:
    sys.exit("ABORT: the loaded engine has no cooldown_bars -- wrong file.")

MULT, COST, LB_START = 20.0, 0.533, "2025-06-30"
CERT = dict(buf_atr=0.9, ema_len=1380, tl_len=170, stop_mult=1.0, trail_frac=2.5,
            min_brk=1.3, vol_mult=0.8, atr_len=106, act_R=2.5, breakeven_R=1.5,
            regime_len=0)
CTRL = dict(pf=1.332, lb_pf=1.493, net=434721.12, dd=50420.22, n=2843)
GRID = [5, 15, 30, 60, 120, 240]
OUT = (r"C:\Users\xride\AppData\Local\Temp\claude"
       r"\C--Users-xride-OneDrive-Desktop\bfc7c1dc-0156-4800-8f19-9f6b9ab85722"
       r"\scratchpad\cooldown_results.json")

arr = load_master_arrays(find_master("NQ", "1m", "eth", "db_noadj_eth"),
                         date_from=None, date_to="2026-06-30")
o, h, l, c = arr["open"], arr["high"], arr["low"], arr["close"]
v, day, idx = arr["volume"], arr["day_id"], arr["index"]


def stats(res):
    tr = res["trades"]
    d = np.array([(t[2] - COST) * MULT for t in tr])
    ent = pd.to_datetime([idx[int(t[0])] for t in tr]).tz_localize(None)
    ext = pd.to_datetime([idx[int(t[1])] for t in tr]).tz_localize(None)
    cum = np.cumsum(d)
    dd = abs(float((cum - np.maximum.accumulate(cum)).min()))
    pf = d[d > 0].sum() / max(abs(d[d < 0].sum()), 1e-9)
    lb = d[ent >= pd.Timestamp(LB_START)]
    lbpf = lb[lb > 0].sum() / max(abs(lb[lb < 0].sum()), 1e-9) if len(lb) else float("nan")
    hold = (ext - ent).total_seconds() / 86400.0
    d18 = d[ent >= pd.Timestamp("2018-01-01")]
    top10 = float(np.sort(d18)[::-1][:10].sum() / d18.sum()) if len(d18) and d18.sum() > 0 else float("nan")
    # THE THING THE OWNER ACTUALLY COMPLAINED ABOUT: how often do trades cluster?
    gaps = (ent[1:] - ext[:-1]).total_seconds() / 60.0 if len(d) > 1 else np.array([])
    within5 = float((np.asarray(gaps) <= 5).mean()) if len(gaps) else float("nan")
    return dict(n=len(d), net=float(d.sum()), dd=dd, pf=float(pf),
                lb_n=int(len(lb)), lb_net=float(lb.sum()), lb_pf=float(lbpf),
                hold=float(hold.max()), top10_2018=round(top10, 3),
                pct_reentry_within_5min=round(within5, 4))


def run(**kw):
    return stats(run_backtest(o, h, l, c, volumes=v, day_id=day, index=idx,
                              return_trades=True, **{**CERT, **kw}))


print("CONTROL (cooldown off) -- parity gate")
ctl = run(cooldown_bars=0)
print(" ", ctl)
ok = ctl["n"] == CTRL["n"] and abs(ctl["net"] - CTRL["net"]) < 1.0
print("  PARITY:", "PASS" if ok else "FAIL -- engine drifted, results not comparable")
if not ok:
    sys.exit(1)

rows = {"control": ctl}
print("\nCOOLDOWN SWEEP")
hdr = "%6s %6s %11s %7s %10s %7s %6s %11s %7s %8s %6s"
print(hdr % ("bars", "n", "net", "dnet%", "maxDD", "dDD%", "PF", "LBnet", "LBPF", "clust%", "score"))
for b in GRID:
    s = run(cooldown_bars=b)
    dd_cut = 1 - s["dd"] / ctl["dd"]
    net_cut = 1 - s["net"] / ctl["net"]
    w = [s["pf"] >= CTRL["pf"], s["lb_pf"] >= CTRL["lb_pf"], s["lb_net"] >= 80000.0,
         dd_cut > net_cut, (s["hold"] <= 120 and s["lb_n"] >= 40)]
    rows["b%d" % b] = dict(s, wins=sum(w), gates=[bool(x) for x in w])
    print(hdr % (b, s["n"], "%.0f" % s["net"], "%+.0f%%" % (-net_cut * 100),
                 "%.0f" % s["dd"], "%+.0f%%" % (-dd_cut * 100), "%.3f" % s["pf"],
                 "%.0f" % s["lb_net"], "%.3f" % s["lb_pf"],
                 "%.1f" % (100 * s["pct_reentry_within_5min"]), "%d/5" % sum(w)))

best = max((k for k in rows if k != "control"), key=lambda k: rows[k]["wins"])
print("\nbest cell: %s with %d/5" % (best, rows[best]["wins"]))
print("VERDICT:", "ADOPT-CANDIDATE" if rows[best]["wins"] >= 4 else
      "FAIL -- no cell clears 4/5, cooldown family closed")
print("control clustering: %.1f%% of trades re-enter within 5 min"
      % (100 * ctl["pct_reentry_within_5min"]))
json.dump(rows, open(OUT, "w"), indent=1)
print("saved ->", OUT)
