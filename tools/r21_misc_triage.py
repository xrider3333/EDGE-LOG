"""
ROUND 21 — pre-registered 2026-08-24 before any results.

A. ES-ETH RELOCATION of the validated ENGU-Q ETH mechanism: ENGUQ_1M_ETH_1_0.py,
   params FROZEN at file defaults (the #226-certified clock-scaled config), run on
   the ES 1m ETH master with ES overnight costs (5.66/50 + 0.5 = 0.613 pts/RT).
   ONE cell — a pure transfer test, the exact move that produced the NQ winner.
   Gate: the house transfer standard — profitable with PF >= 1.15 counts as
   TRANSFER-CONFIRMING evidence for the mechanism (it is not a new champion bar);
   PF >= 1.25 & MAR >= 8 & n >= 300 would make it a candidate in its own right.
B. TURTLE SOUP (failed-breakout fade, NQ daily off the 5m RTH master):
   short: day t trades above the prior 20-day high but CLOSES back below it;
   day t+1, sell a stop at day t's low (fill at level or the open if gapped
   through). Long mirror at 20-day lows. Exits: close of entry day (1d) or close
   two days later (3d). No overnight stop; house calendar roll detector; same-day
   cost 0.533, overnight-held 0.783 + 0.25/roll crossed. Floor n >= 150.
C. PRIOR-DAY-LEVEL REACTION (NQ 5m RTH, intraday with a REAL stop):
   long: uptrend (prior close > SMA200); today price touches YESTERDAY'S LOW ->
   buy limit at that level (if a bar opens through the level, the fill is the
   open - favorable side of a limit, honest); stop = fill - k x ATR20 checked
   bar-by-bar gap-honestly; exit at session close. Short mirror at yesterday's
   high in downtrends. Cells: k in {0.5, 0.75} x {long, short} = 4. Cost 0.533.
Gates: as stated per family; window ends 2025-06-29 (A: 2025-06-29 too), lockbox
never loaded. This grid is the whole grid; one look.
"""
import os, sys, csv
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
from augur_engine.data import find_master, load_master_arrays
from augur_engine.engine import run_backtest
import importlib.util as _ilu
_sp = _ilu.spec_from_file_location("ond", os.path.join(ROOT, "augur_strategies", "ONDRIFT_1_0.py"))
_ond = _ilu.module_from_spec(_sp); _sp.loader.exec_module(_ond)
detect_roll_seams = _ond.detect_roll_seams

DATE_TO = "2025-06-29"
RESULTS = []


def score(pnl, fam, cell, floor, mult):
    p = np.asarray(pnl, float) * mult
    if len(p) == 0:
        RESULTS.append(dict(fam=fam, cell=cell, n=0, net=0, pf=0, dd=0, mar=0, floor=floor)); return
    gw = p[p > 0].sum(); gl = -p[p < 0].sum(); pf = gw / gl if gl > 1e-9 else float('inf')
    cum = np.cumsum(p); dd = float((cum - np.maximum.accumulate(cum)).min())
    net = float(p.sum()); mar = net / -dd if dd < -1e-9 else float('inf')
    RESULTS.append(dict(fam=fam, cell=cell, n=int(len(p)), net=round(net), pf=round(float(pf), 3),
                        dd=round(float(-dd)), mar=round(float(mar), 2), floor=floor))


def main():
    # ---------- A: ES ETH ENGU-Q relocation ----------
    _sp2 = _ilu.spec_from_file_location("eq", os.path.join(ROOT, "augur_strategies", "ENGUQ_1M_ETH_1_0.py"))
    eq = _ilu.module_from_spec(_sp2); _sp2.loader.exec_module(eq)
    P = {k: v["default"] for k, v in eq.DEFAULT_PARAMS.items()}
    r = run_backtest("ENGUQ_1M_ETH_1_0.py", instrument="ES", timeframe="1m", session="eth",
                     source="db_noadj_eth", date_from="2010-06-07", date_to=DATE_TO,
                     params=P, cost_pts=0.613, return_trades=False)
    if r:
        net = r["total_pnl"] * 50.0
        dd = -r["max_drawdown"] * 50.0
        RESULTS.append(dict(fam="A-ESETH", cell="frozen#226cfg", n=r["num_trades"],
                            net=round(net), pf=round(r["profit_factor"], 3),
                            dd=round(dd), mar=round(net / dd, 2) if dd > 0 else 0, floor=300))
    else:
        RESULTS.append(dict(fam="A-ESETH", cell="frozen#226cfg", n=0, net=0, pf=0, dd=0, mar=0, floor=300))
    print("A done", flush=True)

    # ---------- shared NQ daily context ----------
    m5 = find_master("NQ", "5m", "rth", "db_noadj_rth")
    R = load_master_arrays(m5, date_to=DATE_TO)
    o5, h5, l5, c5, did5 = R["open"], R["high"], R["low"], R["close"], R["day_id"]
    idx5 = R["index"]
    sess = []; a = 0; n5 = len(c5)
    while a < n5:
        b = a
        while b < n5 and did5[b] == did5[a]:
            b += 1
        sess.append((a, b)); a = b
    do = np.array([o5[x] for x, y in sess]); dh = np.array([h5[x:y].max() for x, y in sess])
    dl = np.array([l5[x:y].min() for x, y in sess]); dc = np.array([c5[y - 1] for x, y in sess])
    nd = len(sess)
    day_ts = [idx5[x] for x, y in sess]
    seams = set(detect_roll_seams(do, dc, day_ts))
    sma200 = np.full(nd, np.nan)
    for d in range(199, nd):
        sma200[d] = dc[d - 199:d + 1].mean()
    atr20 = np.full(nd, np.nan)
    for d in range(20, nd):
        atr20[d] = (dh[d - 20:d] - dl[d - 20:d]).mean()

    def chain_exit(d_entry_day, entry_px, d_exit_day, side):
        raw = dc[d_entry_day] - entry_px
        cost = 0.533 if d_exit_day == d_entry_day else 0.783
        for dd_ in range(d_entry_day + 1, d_exit_day + 1):
            g = do[dd_] - dc[dd_ - 1]
            if dd_ in seams:
                cost += 0.25
            else:
                raw += g
            raw += dc[dd_] - do[dd_]
        return side * raw - cost

    # ---------- B: turtle soup ----------
    for side_name, side in (("short", -1), ("long", 1)):
        for hold in (0, 2):
            pnl = []
            for t in range(210, nd - 1 - hold):
                if side == -1:
                    lvl = dh[t - 20:t].max()
                    if not (dh[t] > lvl and dc[t] < lvl):
                        continue
                    trig = dl[t]
                else:
                    lvl = dl[t - 20:t].min()
                    if not (dl[t] < lvl and dc[t] > lvl):
                        continue
                    trig = dh[t]
                a1, b1 = sess[t + 1]
                fill = None
                for k in range(a1, b1):
                    if side == -1 and l5[k] <= trig:
                        fill = min(trig, o5[k]); break
                    if side == 1 and h5[k] >= trig:
                        fill = max(trig, o5[k]); break
                if fill is None:
                    continue
                if any((t + 1 + j) in seams for j in range(1, hold + 1)):
                    continue
                pnl.append(chain_exit(t + 1, fill, t + 1 + hold, side))
            score(pnl, "B-SOUP", side_name + "/" + ("1d" if hold == 0 else "3d"), 150, 20.0)
    print("B done", flush=True)

    # ---------- C: prior-day-level reaction ----------
    for k_stop in (0.5, 0.75):
        for side_name, side in (("long", 1), ("short", -1)):
            pnl = []
            for t in range(210, nd):
                if side == 1:
                    if not dc[t - 1] > sma200[t - 1]:
                        continue
                    lvl = dl[t - 1]
                else:
                    if not dc[t - 1] < sma200[t - 1]:
                        continue
                    lvl = dh[t - 1]
                a1, b1 = sess[t]
                fill = None
                for k in range(a1, b1 - 1):
                    if side == 1 and l5[k] <= lvl:
                        fill = min(lvl, o5[k]); ei = k; break
                    if side == -1 and h5[k] >= lvl:
                        fill = max(lvl, o5[k]); ei = k; break
                if fill is None:
                    continue
                stop = fill - side * k_stop * atr20[t]
                ex = None
                for k in range(ei + 1, b1):
                    if side == 1:
                        if o5[k] <= stop: ex = o5[k]; break
                        if l5[k] <= stop: ex = stop; break
                    else:
                        if o5[k] >= stop: ex = o5[k]; break
                        if h5[k] >= stop: ex = stop; break
                if ex is None:
                    ex = c5[b1 - 1]
                pnl.append(side * (ex - fill) - 0.533)
            score(pnl, "C-REACT", f"{side_name}/stop{k_stop}", 300, 20.0)
    print("C done", flush=True)

    print(f"\n{'fam':9}{'cell':16}{'n':>6}{'net$':>11}{'PF':>7}{'DD$':>10}{'MAR':>7}  gate")
    for r_ in RESULTS:
        g = "PASS" if (r_['pf'] >= 1.25 and r_['mar'] >= 8 and r_['n'] >= r_['floor']) else "fail"
        if r_["fam"] == "A-ESETH" and r_['pf'] >= 1.15 and r_['net'] > 0 and g == "fail":
            g = "transfer-ok"
        print(f"{r_['fam']:9}{r_['cell']:16}{r_['n']:>6}{r_['net']:>11,}{r_['pf']:>7.3f}{r_['dd']:>10,}{r_['mar']:>7.2f}  {g}")
    with open(os.path.join(ROOT, "tools", "r16_results", "r21_triage.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(RESULTS[0].keys()))
        w.writeheader(); w.writerows(RESULTS)
    print("saved tools/r16_results/r21_triage.csv")


if __name__ == "__main__":
    main()
