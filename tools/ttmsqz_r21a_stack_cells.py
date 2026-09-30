"""TTM round 21a - the honest stack on TTM's other cells (tools/TTM_R20_PREREG.txt addendum 4).

Frozen stack on every cell: TTMSQZ_3_0.py at the #299 crown with fade_bars 2, deep-squeeze 1.5x
(TTMSQZ_3_0_ES30T._deep_state at the decision bar) x open-bar 1.5x (fill on the session's ordinal-1 bar).
A trade sized s is worth s*(raw - cost). Raw twin = the crown unchanged (fade 1, size 1). ADJ masters
pinned, 2010-06-07..2026-06-30, LB from 2025-07-01. Yardstick = round 19's stretch_stats.
Parity first: ES 30m stacked must equal round 19b row F (WF 342 / $68,585, LB 15 / $10,381).
Log: tools/data/ttmsqz_r21a_stack_cells.txt
"""
import os
import sys
import importlib.util

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHARED = r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"
os.chdir(SHARED)
sys.path.insert(0, SHARED)
from augur_engine.data import find_master, load_master_arrays   # noqa: E402


def _imp(name, path):
    sp = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(sp)
    sp.loader.exec_module(m)
    return m


T3 = _imp("TTMSQZ_3_0_r21a", os.path.join(SHARED, "augur_strategies", "TTMSQZ_3_0.py"))
ES30T = _imp("TTMSQZ_3_0_ES30T_r21a", os.path.join(SHARED, "augur_strategies", "TTMSQZ_3_0_ES30T.py"))
R19 = _imp("r19a", os.path.join(HERE, "tools", "ttmsqz_r19a_multicell_sleeve.py"))
CROWN = dict(R19.CROWN)
CELLS = [("ES", "30m"), ("ES", "15m"), ("NQ", "30m"), ("NQ", "15m")]
COST = {"ES": 0.363, "NQ": 0.533}
MULT = {"ES": 50.0, "NQ": 20.0}
D0, WF_END, LB0, D1 = "2010-06-07", "2025-06-30", "2025-07-01", "2026-06-30"
OUT = os.path.join(HERE, "tools", "data", "ttmsqz_r21a_stack_cells.txt")
L = []


def emit(x=""):
    L.append(x)
    print(x, flush=True)


def ordinal(day_id):
    did = np.asarray(day_id)
    out = np.zeros(len(did), int)
    a = 0
    while a < len(did):
        b = a
        while b < len(did) and did[b] == did[a]:
            b += 1
        out[a:b] = np.arange(b - a)
        a = b
    return out


def cell(inst, tf, stacked):
    a = load_master_arrays(find_master(inst, tf, "rth", "db_adj_rth"), date_from=D0, date_to=D1)
    p = dict(CROWN, fade_bars=2 if stacked else 1)
    r = T3.run_backtest(a["open"], a["high"], a["low"], a["close"], day_id=a["day_id"],
                        index=a["index"], return_trades=True, **p)
    idx = pd.DatetimeIndex(a["index"]).tz_localize(None)
    n = len(idx)
    if stacked:
        deep = ES30T._deep_state(a["high"], a["low"], a["close"], a["day_id"], a["index"])
        od = ordinal(a["day_id"])
    out = []
    for t in (r or {}).get("trades", []):
        eb, xb, pts = int(t[0]), int(t[1]), float(t[2])
        s = 1.0
        if stacked:
            s = ((1.5 if bool(deep[min(max(eb - 1, 0), n - 1)]) else 1.0)
                 * (1.5 if od[min(eb, n - 1)] == 1 else 1.0))
        out.append((idx[xb].normalize(), s * (pts - COST[inst]) * MULT[inst]))
    return out, idx


def line(label, wf, lb):
    emit("  %-24s WF n %5d net $%9s ROC@30k %6.1f Sortino %5.2f | LB n %4d net $%8s ROC@30k %6.1f Sortino %5.2f ex-big $%8s" % (
        label, wf["n"], "{:,.0f}".format(wf["net"]), wf["roc"], wf["sortino"],
        lb["n"], "{:,.0f}".format(lb["net"]), lb["roc"], lb["sortino"], "{:,.0f}".format(lb["net_ex_biggest"])))


def main():
    emit("TTM round 21a - the honest stack on TTM's other cells (prereg addendum 4)")
    res, idxs = {}, []
    for inst, tf in CELLS:
        for stk in (False, True):
            td, idx = cell(inst, tf, stk)
            res[(inst, tf, stk)] = td
        idxs.append(idx)
    cal = R19.full_calendar(idxs, D0, D1)

    def sc(td):
        return R19.stretch_stats(td, cal, D0, WF_END), R19.stretch_stats(td, cal, LB0, D1)

    wf, lb = sc(res[("ES", "30m", True)])
    emit("PARITY ES 30m stacked: WF %d / $%s, LB %d / $%s (round 19b row F = 342 / $68,585, 15 / $10,381)" % (
        wf["n"], "{:,.0f}".format(wf["net"]), lb["n"], "{:,.0f}".format(lb["net"])))
    emit("")
    emit("PER CELL (information): raw twin vs stacked")
    for inst, tf in CELLS:
        rw, rl = sc(res[(inst, tf, False)])
        sw, sl = sc(res[(inst, tf, True)])
        line("%s %s raw" % (inst, tf), rw, rl)
        line("%s %s STACKED" % (inst, tf), sw, sl)
        ok = (sw["roc"] >= rw["roc"] and sl["roc"] >= rl["roc"]
              and sw["sortino"] >= rw["sortino"] and sl["sortino"] >= rl["sortino"])
        emit("    -> stacked beats raw on ROC@30k and Sortino in WF and LB: %s" % ("YES" if ok else "no"))
    emit("")
    raw4 = sum((res[(i, t, False)] for i, t in CELLS), [])
    stk4 = sum((res[(i, t, True)] for i, t in CELLS), [])
    rw, rl = sc(raw4)
    sw, sl = sc(stk4)
    emit("THE SLEEVE (the decision)")
    line("raw 4-cell sleeve", rw, rl)
    line("STACKED 4-cell sleeve", sw, sl)
    cl = [("ROC@30k >= raw WF", sw["roc"] >= rw["roc"]), ("ROC@30k >= raw LB", sl["roc"] >= rl["roc"]),
          ("Sortino >= raw WF", sw["sortino"] >= rw["sortino"]), ("Sortino >= raw LB", sl["sortino"] >= rl["sortino"]),
          (">=100 WF / 50 LB trades", sw["n"] >= 100 and sl["n"] >= 50), ("LB ex-biggest > 0", sl["net_ex_biggest"] > 0)]
    emit("VERDICT: %s -> %s" % ("; ".join("%s %s" % (k, "yes" if v else "NO") for k, v in cl),
                               "PASS -> Frontier book test" if all(v for _, v in cl) else "FAIL"))
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    open(OUT, "w", encoding="utf-8").write("\n".join(L) + "\n")
    print("log ->", OUT)


if __name__ == "__main__":
    main()
