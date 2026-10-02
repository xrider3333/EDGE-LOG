"""TTM round 22 - breakeven at +1R, then ride, on TTM #459 (tools/TTM_R22_PREREG.txt, d3ddddc4).

The #459 file (TTMSQZ_3_0_ES30SSOF2.py) runs its trades through the structural-stop module's `_simulate`.
This driver loads its own copy of the #459 chain and swaps that function for `be_simulate` below - the
same loop line for line, plus the breakeven rule - so the sizing ladder, gate, fire, fade and costs are
the file's own. With mode "off" the copy must reproduce the twin to the trade (checked first).

Rule (bar-close only): R = |entry - initial structural stop|. When a bar CLOSES with the open trade
>= +1R in its favour, the stop moves to the entry price from the NEXT bar (never loosened). 22A keeps the
normal exits; 22B also switches the fade exit off once the stop is at breakeven (ride to stop or close).
Log: tools/data/ttmsqz_r22a_breakeven.txt
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


L459 = _imp("TTMSQZ_3_0_ES30SSOF2_r22", os.path.join(SHARED, "augur_strategies", "TTMSQZ_3_0_ES30SSOF2.py"))
SS = L459._so._ss                     # the structural-stop module THIS chain uses
ORIG = SS._simulate
R19 = _imp("r19a", os.path.join(HERE, "tools", "ttmsqz_r19a_multicell_sleeve.py"))
PARAMS = dict(kc_mult=1.5, eod_cutoff=1, gate_len=20)
COST, MULT = 0.363, 50.0
D0, WF_END, LB0, D1 = "2010-06-07", "2025-06-30", "2025-07-01", "2026-06-30"
OUT = os.path.join(HERE, "tools", "data", "ttmsqz_r22a_breakeven.txt")
L = []
STATS = {}


def emit(x=""):
    L.append(x)
    print(x, flush=True)


def make_sim(mode):
    """mode: 'off' (copy, no rule), 'A' (breakeven, normal exits), 'B' (breakeven, then ride)."""
    def be_simulate(o, h, l, c, n, warm, mom, atr, fire, rng_hi, rng_lo, gate_long, gate_short,
                    last_bar, fade_bars, eod_cutoff, struct_buf, direction):
        pos = 0; entry_px = 0.0; entry_bar = -1; side = 0
        stop_px = None
        fade_cnt = 0
        pending = None
        trade_log = []
        risk = 0.0; armed = False
        be_exits = STATS.setdefault(mode, {"be_exit_bars": set(), "armed": 0})

        def _book(exit_i, px, sd, ep, eb):
            p = (px - ep) if sd > 0 else (ep - px)
            trade_log.append((int(eb), int(exit_i), float(p), int(sd), float(ep), float(px)))

        for u in range(warm, n):
            eod = u == last_bar[u]
            if pending is not None:
                kind = pending[0]
                if kind == "exit":
                    if pos != 0:
                        _book(u, o[u], pos, entry_px, entry_bar)
                        pos = 0; stop_px = None
                    pending = None
                else:
                    if pos == 0:
                        side = pending[1]; rh, rl = pending[2], pending[3]
                        pos = side; entry_px = o[u]; entry_bar = u; fade_cnt = 0
                        stop_px = (rl - struct_buf) if side > 0 else (rh + struct_buf)
                        risk = abs(entry_px - stop_px); armed = False
                        if stop_px is not None and ((side > 0 and l[u] <= stop_px) or
                                                   (side < 0 and h[u] >= stop_px)):
                            px = min(o[u], stop_px) if side > 0 else max(o[u], stop_px)
                            _book(u, px, pos, entry_px, entry_bar)
                            pos = 0; stop_px = None
                    pending = None

            if pos != 0 and u > entry_bar and stop_px is not None:
                if (pos > 0 and l[u] <= stop_px) or (pos < 0 and h[u] >= stop_px):
                    px = min(o[u], stop_px) if pos > 0 else max(o[u], stop_px)
                    if armed:
                        be_exits["be_exit_bars"].add(int(u))
                    _book(u, px, pos, entry_px, entry_bar)
                    pos = 0; stop_px = None

            if eod:
                if pos != 0:
                    _book(u, c[u], pos, entry_px, entry_bar)
                    pos = 0; stop_px = None
                pending = None
                continue

            # THE RULE: this bar has CLOSED; if the trade is >= +1R, the stop goes to entry from u+1 on.
            if mode != "off" and pos != 0 and not armed and risk > 0 and pos * (c[u] - entry_px) >= risk:
                stop_px = max(stop_px, entry_px) if pos > 0 else min(stop_px, entry_px)
                armed = True
                be_exits["armed"] += 1

            m, m1 = mom[u], mom[u - 1]
            if not (np.isfinite(m) and np.isfinite(m1)):
                continue

            if pos != 0 and not (mode == "B" and armed):
                fading = (m < m1) if pos > 0 else (m > m1)
                fade_cnt = fade_cnt + 1 if fading else 0
                if fade_cnt >= fade_bars:
                    pending = ("exit",)
                    continue

            if pos == 0 and pending is None and fire[u] and m != 0:
                sd = 1 if m > 0 else -1
                if direction == "long" and sd < 0:
                    continue
                if direction == "short" and sd > 0:
                    continue
                if sd > 0 and not gate_long[u]:
                    continue
                if sd < 0 and not gate_short[u]:
                    continue
                if last_bar[u] - u <= eod_cutoff:
                    continue
                pending = ("mkt", sd, rng_hi[u], rng_lo[u])
        return trade_log
    return be_simulate


def run(arr, sim):
    SS._simulate = sim
    try:
        r = L459.run_backtest(arr["open"], arr["high"], arr["low"], arr["close"], day_id=arr["day_id"],
                              index=arr["index"], return_trades=True, **PARAMS)
    finally:
        SS._simulate = ORIG
    return r["trades"]


def dollars(trades, idx):
    return [(idx[int(t[1])].normalize(), (float(t[2]) - COST) * MULT) for t in trades]


def line(label, wf, lb):
    emit("  %-30s WF n %4d net $%9s ROC@30k %6.1f Sortino %5.2f | LB n %3d net $%8s ROC@30k %6.1f Sortino %5.2f ex-big $%8s" % (
        label, wf["n"], "{:,.0f}".format(wf["net"]), wf["roc"], wf["sortino"],
        lb["n"], "{:,.0f}".format(lb["net"]), lb["roc"], lb["sortino"], "{:,.0f}".format(lb["net_ex_biggest"])))


def main():
    emit("TTM round 22 - breakeven at +1R on TTM #459 (prereg tools/TTM_R22_PREREG.txt, d3ddddc4)")
    arr = load_master_arrays(find_master("ES", "30m", "rth", "db_adj_rth"), date_from=D0, date_to=D1)
    idx = pd.DatetimeIndex(arr["index"]).tz_localize(None)
    cal = R19.full_calendar([idx], D0, D1)
    twin = run(arr, ORIG)
    off = run(arr, make_sim("off"))
    same = len(twin) == len(off) and all(tuple(a) == tuple(b) for a, b in zip(twin, off))
    emit("PARITY: twin %d trades $%s (expect 355 / $72,716); copy with the rule off identical to the trade: %s" % (
        len(twin), "{:,.0f}".format(sum(u for _, u in dollars(twin, idx))), "YES" if same else "NO - STOP"))
    if not same:
        open(OUT, "w", encoding="utf-8").write("\n".join(L) + "\n")
        return
    rows = {"TWIN #459 unchanged": twin, "22A breakeven, normal exits": run(arr, make_sim("A")),
            "22B breakeven, then ride": run(arr, make_sim("B"))}
    sc = {}
    emit("")
    for lab, tr in rows.items():
        td = dollars(tr, idx)
        sc[lab] = (R19.stretch_stats(td, cal, D0, WF_END), R19.stretch_stats(td, cal, LB0, D1))
        line(lab, *sc[lab])
    emit("")
    emit("REPORTED, NO VERDICT (the R-stat trap check; R = net points per contract-size unit / initial risk is not")
    emit("recoverable after sizing, so per-trade WIN RATE and mean $ per trade are shown instead)")
    tw_win = {int(t[0]): (float(t[2]) - COST) for t in twin}
    for lab, tr in rows.items():
        u = np.array([(float(t[2]) - COST) * MULT for t in tr])
        scratched = sum(1 for t in tr if tw_win.get(int(t[0]), 0) > 0 and abs(float(t[2]) - COST) <= COST * 2.25 + 1e-9
                        and lab != "TWIN #459 unchanged")
        st = STATS.get({"22A breakeven, normal exits": "A", "22B breakeven, then ride": "B"}.get(lab, ""), {})
        emit("  %-30s trades %d  win rate %.1f%%  mean $/trade %+.0f  armed %s  breakeven-stop exits %s  twin winners scratched %d" % (
            lab, len(u), 100.0 * (u > 0).mean(), u.mean(), st.get("armed", "-"), len(st.get("be_exit_bars", [])) if st else "-",
            scratched))
    emit("")
    tw, tl = sc["TWIN #459 unchanged"]
    for lab in ("22A breakeven, normal exits", "22B breakeven, then ride"):
        w, l = sc[lab]
        cl = [("(a) ROC@30k >= twin WF", w["roc"] >= tw["roc"]), ("(a) ROC@30k >= twin LB", l["roc"] >= tl["roc"]),
              ("(b) Sortino >= twin WF", w["sortino"] >= tw["sortino"]), ("(b) Sortino >= twin LB", l["sortino"] >= tl["sortino"]),
              ("(c) >=100 WF trades", w["n"] >= 100), ("(d) LB ex-biggest > 0", l["net_ex_biggest"] > 0)]
        emit("VERDICT %s: %s -> %s" % (lab, "; ".join("%s %s" % (k, "yes" if v else "NO") for k, v in cl),
                                       "PASS (triage) -> Auto-Validate" if all(v for _, v in cl) else "FAIL"))
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    open(OUT, "w", encoding="utf-8").write("\n".join(L) + "\n")
    print("log ->", OUT)


if __name__ == "__main__":
    main()
