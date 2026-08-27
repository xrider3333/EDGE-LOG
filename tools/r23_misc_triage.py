"""
ROUND 23 (local half) — trend-riding at daily scale with the crown risk engine.
Pre-registered 2026-08-25 before any results.

The no-stop turtle died (r17: PF 1.36 / MAR 3.2). This is the modern form:
- Entry: day t CLOSES beyond the prior {20, 55}-day extreme (close confirmation,
  not an intrabar touch) -> enter at day t+1's 09:30 open. Both directions.
- Initial stop: entry -/+ 1.0 x ATR20 (20-day average daily range).
- Trail: chandelier - highest (lowest) DAILY CLOSE since entry -/+ {2, 3} x ATR20
  (ATR frozen at entry), recomputed at each close, applies from the NEXT session,
  ratchet-only. Breakeven implied by the ratchet.
- Stop monitoring: intraday on the 5m RTH bars, gap-honest (a bar opening through
  the stop fills at its open; the morning open itself is checked first). Overnight
  the position is naked (r18b: resting overnight stops only hurt) - the morning
  gap is taken honestly.
- Roll seams (house calendar detector): the seam night's jump is excluded from
  PnL, 0.25 pt roll cost charged, AND entry/stop/extreme reference levels are
  SHIFTED by the seam jump so a resting stop is never hit by the contract stitch.
- Cost: 0.783 pts/RT (all trades hold overnight) + 0.25 per seam crossed.
Cells: entry {20, 55} x trail {2, 3} = 4. Floor n >= 150. PF >= 1.25, MAR >= 8.
Window 2010-06-07 -> 2025-06-29; lockbox never loaded. Whole grid; one look.
"""
import os, sys, csv
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
from augur_engine.data import find_master, load_master_arrays
import importlib.util as _ilu
_sp = _ilu.spec_from_file_location("ond", os.path.join(ROOT, "augur_strategies", "ONDRIFT_1_0.py"))
_ond = _ilu.module_from_spec(_sp); _sp.loader.exec_module(_ond)
detect_roll_seams = _ond.detect_roll_seams

DATE_TO = "2025-06-29"; MULT = 20.0; RT = 0.783; ROLL = 0.25
RESULTS = []


def score(pnl, cell, floor=150):
    p = np.asarray(pnl, float) * MULT
    if len(p) == 0:
        RESULTS.append(dict(cell=cell, n=0, net=0, pf=0, dd=0, mar=0)); return
    gw = p[p > 0].sum(); gl = -p[p < 0].sum(); pf = gw / gl if gl > 1e-9 else float('inf')
    cum = np.cumsum(p); dd = float((cum - np.maximum.accumulate(cum)).min())
    net = float(p.sum()); mar = net / -dd if dd < -1e-9 else float('inf')
    RESULTS.append(dict(cell=cell, n=int(len(p)), net=round(net), pf=round(float(pf), 3),
                        dd=round(float(-dd)), mar=round(float(mar), 2)))


def main():
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
    atr20 = np.full(nd, np.nan)
    for d in range(20, nd):
        atr20[d] = (dh[d - 20:d] - dl[d - 20:d]).mean()

    for ein in (20, 55):
        for trail_k in (2.0, 3.0):
            pnl = []
            d = 210
            while d < nd - 1:
                side = 0
                if dc[d] >= dh[d - ein:d].max():
                    side = 1
                elif dc[d] <= dl[d - ein:d].min():
                    side = -1
                if side == 0 or (d + 1) in seams:
                    d += 1; continue
                atr = atr20[d]
                entry = do[d + 1]
                stop = entry - side * 1.0 * atr
                extreme = None
                cost = RT
                adj = 0.0            # cumulative seam adjustment applied to levels
                trade_pnl = None
                dd_ = d + 1
                while dd_ < nd:
                    if dd_ > d + 1:
                        gap = do[dd_] - dc[dd_ - 1]
                        if dd_ in seams:
                            cost += ROLL
                            entry += gap; stop += gap
                            if extreme is not None:
                                extreme += gap
                            adj += gap
                    a1, b1 = sess[dd_]
                    exited = False
                    for k in range(a1, b1):
                        if side == 1:
                            if o5[k] <= stop:
                                trade_pnl = side * (o5[k] - entry) - cost; exited = True; break
                            if l5[k] <= stop:
                                trade_pnl = side * (stop - entry) - cost; exited = True; break
                        else:
                            if o5[k] >= stop:
                                trade_pnl = side * (o5[k] - entry) - cost; exited = True; break
                            if h5[k] >= stop:
                                trade_pnl = side * (stop - entry) - cost; exited = True; break
                    if exited:
                        break
                    close_now = dc[dd_]
                    if extreme is None or (side == 1 and close_now > extreme) or (side == -1 and close_now < extreme):
                        extreme = close_now
                    new_stop = extreme - side * trail_k * atr
                    if (side == 1 and new_stop > stop) or (side == -1 and new_stop < stop):
                        stop = new_stop
                    dd_ += 1
                if trade_pnl is None:      # ran out of data - exclude (lockbox-honest)
                    break
                pnl.append(trade_pnl)
                d = dd_ + 1
            score(pnl, f"e{ein}/trail{trail_k}")
    print(f"{'cell':14}{'n':>6}{'net$':>11}{'PF':>7}{'DD$':>10}{'MAR':>7}  gate")
    for r_ in RESULTS:
        g = "PASS" if (r_['pf'] >= 1.25 and r_['mar'] >= 8 and r_['n'] >= 150) else "fail"
        print(f"{r_['cell']:14}{r_['n']:>6}{r_['net']:>11,}{r_['pf']:>7.3f}{r_['dd']:>10,}{r_['mar']:>7.2f}  {g}")
    with open(os.path.join(ROOT, "tools", "r16_results", "r23_triage.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(RESULTS[0].keys()))
        w.writeheader(); w.writerows(RESULTS)
    print("saved tools/r16_results/r23_triage.csv")


if __name__ == "__main__":
    main()
