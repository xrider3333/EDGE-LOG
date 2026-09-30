"""TTM round 20d - the candle half of 20b, on 16 years (tools/TTM_R20_PREREG.txt addendum 1, a85a666f).

A fire is taken only when the FIRE bar's candle agrees with the trade side (close > open long, close < open
short, doji = no trade). The filter is applied INSIDE the engine (the hourly-gate arrays are ANDed with the
candle), so a skipped fire leaves the leg flat for the next one - not a post-hoc drop of trades.
  20d-U = ungated + candle;  20d-G = gated + candle.  Twin = the gated six-cell crown book; also the ungated book.
Frozen #299 crown, TTMSQZ_3_0.py, ES/NQ x 5m/15m/30m RTH, db_noadj_rth, 2010-06-07 .. 2026-06-30, LB from
2025-07-01, one contract per cell, ES 0.363 / NQ 0.533 pts. Yardstick = round 19's stretch_stats (daily P&L,
daily-valued drawdown from flat, ROC@$30k = 30 x MAR, Sortino). Parity first: ES 30m gated = run #299.

Log: tools/data/ttmsqz_r20d_candle_proxy.txt
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


MOD = _imp("TTMSQZ_3_0_r20d", os.path.join(SHARED, "augur_strategies", "TTMSQZ_3_0.py"))
R19 = _imp("r19a", os.path.join(HERE, "tools", "ttmsqz_r19a_multicell_sleeve.py"))
_GATE = MOD._htf_gate

CROWN = dict(R19.CROWN)
CELLS = [(i, tf) for i in ("ES", "NQ") for tf in ("5m", "15m", "30m")]
COST = {"ES": 0.363, "NQ": 0.533}
MULT = {"ES": 50.0, "NQ": 20.0}
D0, WF_END, LB0, D1 = "2010-06-07", "2025-06-30", "2025-07-01", "2026-06-30"
OUT = os.path.join(HERE, "tools", "data", "ttmsqz_r20d_candle_proxy.txt")
L = []


def emit(x=""):
    L.append(x)
    print(x, flush=True)


ARR = {}


def arrays(inst, tf):
    if (inst, tf) not in ARR:
        ARR[(inst, tf)] = load_master_arrays(find_master(inst, tf, "rth", "db_noadj_rth"), date_from=D0, date_to=D1)
    return ARR[(inst, tf)]


def run_cell(inst, tf, gated, candle):
    a = arrays(inst, tf)
    o = np.asarray(a["open"], float); c = np.asarray(a["close"], float)
    up, dn = c > o, c < o

    def gate(*args, **kw):
        gl, gs = _GATE(*args, **kw)
        if candle:
            gl, gs = gl & up, gs & dn
        return gl, gs

    MOD._htf_gate = gate
    try:
        p = dict(CROWN, gate_mode="sq_on" if gated else "none")
        r = MOD.run_backtest(a["open"], a["high"], a["low"], a["close"], day_id=a["day_id"],
                             index=a["index"], return_trades=True, **p)
    finally:
        MOD._htf_gate = _GATE
    idx = pd.DatetimeIndex(a["index"]).tz_localize(None)
    return [(idx[int(t[1])].normalize(), (float(t[2]) - COST[inst]) * MULT[inst]) for t in (r or {}).get("trades", [])]


def score(td, cal):
    wf = R19.stretch_stats(td, cal, D0, WF_END)
    lb = R19.stretch_stats(td, cal, LB0, D1)
    return wf, lb


def line(label, wf, lb):
    emit("  %-30s WF n %5d net $%9s ROC@30k %6.1f Sortino %5.2f | LB n %4d net $%8s ROC@30k %6.1f Sortino %5.2f ex-big $%8s" % (
        label, wf["n"], "{:,.0f}".format(wf["net"]), wf["roc"], wf["sortino"],
        lb["n"], "{:,.0f}".format(lb["net"]), lb["roc"], lb["sortino"], "{:,.0f}".format(lb["net_ex_biggest"])))


def main():
    emit("TTM round 20d - candle proxy on 16 years (prereg addendum 1, a85a666f)")
    emit("frozen crown %s" % CROWN)
    par = run_cell("ES", "30m", True, False)
    emit("PARITY ES 30m gated, no candle: %d trades, $%s (run #299 = 359 / $51,709)" % (
        len(par), "{:,.0f}".format(sum(u for _, u in par))))
    cal = R19.full_calendar([pd.DatetimeIndex(arrays(i, tf)["index"]).tz_localize(None) for i, tf in CELLS], D0, D1)
    variants = [("TWIN gated", True, False), ("ungated (plain twin of U)", False, False),
                ("20d-G gated + candle", True, True), ("20d-U ungated + candle", False, True)]
    books = {}
    for lab, g, cnd in variants:
        emit("")
        emit(lab)
        allt = []
        for inst, tf in CELLS:
            td = run_cell(inst, tf, g, cnd)
            allt += td
            wf, lb = score(td, cal)
            line("%s %s" % (inst, tf), wf, lb)
        books[lab] = score(allt, cal)
        line("SIX-CELL BOOK", *books[lab])
    emit("")
    tw, tl = books["TWIN gated"]
    uw, ul = books["ungated (plain twin of U)"]
    for lab in ("20d-G gated + candle", "20d-U ungated + candle"):
        w, l = books[lab]
        cl = [("ROC@30k >= twin WF", w["roc"] >= tw["roc"]), ("ROC@30k >= twin LB", l["roc"] >= tl["roc"]),
              ("Sortino >= twin WF", w["sortino"] >= tw["sortino"]), ("Sortino >= twin LB", l["sortino"] >= tl["sortino"]),
              (">=100 WF / 50 LB trades", w["n"] >= 100 and l["n"] >= 50), ("LB ex-biggest > 0", l["net_ex_biggest"] > 0)]
        if lab.startswith("20d-U"):
            cl += [("ROC@30k >= ungated WF", w["roc"] >= uw["roc"]), ("ROC@30k >= ungated LB", l["roc"] >= ul["roc"])]
        emit("VERDICT %s: %s -> %s" % (lab, "; ".join("%s %s" % (k, "yes" if v else "NO") for k, v in cl),
                                       "PASS (triage)" if all(v for _, v in cl) else "FAIL"))
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    open(OUT, "w", encoding="utf-8").write("\n".join(L) + "\n")
    print("log ->", OUT)


if __name__ == "__main__":
    main()
