"""
ROUND 38 (2026-09-08) - THE SCALP HUNT, part C: is the NOISE band special, or does ANY 2-minute
momentum trigger work under a tail-keeping exit?

Round 37's lesson: on NQ 1m every fixed-target scalp dies, and the only thing that pays on
short bars is the NOISE band on 2m with an exit that keeps the tail (VWAP cross / band boundary).
This round puts round 37's four TRIGGERS on the same 2m bars and gives each one the same exit
families, so the exit is held constant and the trigger is what is being judged.

PRE-REGISTRATION (fixed before any cell ran)
  data     NQ 2m RTH, db_noadj_rth (the registered resample of the 1m tape), 2010-06-07 ..
           2025-06-29; lockbox NEVER loaded. Cost 0.533 pts/RT, $20/pt (the house number; the
           round-37 zero-cost rerun showed cost is not what killed the 1m cells).
  fills    finished-bar decisions, next-bar-open entry, stop-first pessimism, gap-through stop
           fills at the open, targets fill at the target price, flat at the session close.
  exits    VWAPX = exit at the next open after a CLOSE crosses the session VWAP against the
                   trade (the NOISE exit), protective stop stays live;
           RIDE  = breakeven at 1R armed on a close, ride to the close;
           T1/T2 = fixed 1R / 2R target with a 30-minute (15-bar) time stop (the round-37 control).
  bar      unchanged: PF >= 1.25, MAR >= 8, n >= 300, >= 6/8 slices, top-10 < 90% with a positive
           ex-top-10 net, $/trade >= $21.32. Hold reported, never gated.
  control  the NOISE 2m search leader (row 1321): n 5,340 / PF 1.477 / MAR 19.6 / R/YR 140.6.

TRIGGERS (all on 2m bars)
  M1 MICRO-OR   opening range of the first {3, 5} bars (6 / 10 min), first CLOSE beyond it inside
                the first hour, first-candle direction only, stop = the other side of the range.
  M2 OPEN-DRIVE the 09:30 2m bar's direction at the 09:32 open, stop = that bar's other extreme.
  M3 PDH/PDL    first CLOSE beyond the prior session's RTH high/low after 09:32, before 15:00,
                stop {0.10, 0.20} x ATR20d beyond the entry, one per level per day.
  M4 RANGE-BURST a bar with >= {3, 4} x its trailing 20-bar mean range, closing in the outer
                quarter, in the direction of (close - session open), 09:36-15:30, stop = the
                bar's other extreme, at most 3 a day.
  Cells: (2 + 1 + 2 + 2) triggers x 4 exits = 28.

    python tools/r38_scalp2m_triage.py   -> tools/r37_results/r38_scalp2m_triage.csv
"""
import os, sys, csv, time
import numpy as np
import pandas as pd
import importlib.util as ilu

HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
DATA_REPO = ROOT if os.path.exists(os.path.join(ROOT, "optimizer_history.db")) else r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"
sys.path.insert(0, DATA_REPO)
from augur_engine.data import find_master, load_master_arrays   # noqa: E402
_sp = ilu.spec_from_file_location("gapgo", os.path.join(DATA_REPO, "augur_strategies", "GAPGO_1_0.py"))
_gg = ilu.module_from_spec(_sp); _sp.loader.exec_module(_gg)
detect_roll_seams = _gg.detect_roll_seams

COST, MULT, BAR_MIN = 0.533, 20.0, 2
WIN = dict(date_from="2010-06-07", date_to="2025-06-29")
OUT = os.path.join(HERE, "r37_results", "r38_scalp2m_triage.csv")
EXITS = ("T1", "T2", "RIDE", "VWAPX")
TIME_STOP_BARS = 15
RESULTS = []


def score(pnl, holds, fam, cell):
    p = np.asarray(pnl, float) * MULT
    if len(p) == 0:
        RESULTS.append(dict(fam=fam, cell=cell, n=0)); return
    gw = p[p > 0].sum(); gl = -p[p < 0].sum(); pf = gw / gl if gl > 1e-9 else 99.0
    cum = np.cumsum(p); dd = float((cum - np.maximum.accumulate(cum)).min())
    net = float(p.sum()); w = float((p > 0).mean()); evr = (1 - w) * (pf - 1)
    yrs = 15.06; tpy = len(p) / yrs; k = len(p) // 8
    folds = sum(1 for i in range(8) if p[i * k:(i + 1) * k if i < 7 else len(p)].sum() > 0) if k else 0
    srt = sorted(p, reverse=True); top10 = sum(srt[:10]); ex = np.array(srt[10:])
    exnet = float(ex.sum()); exgw = ex[ex > 0].sum(); exgl = -ex[ex < 0].sum()
    h = np.asarray(holds, float) * BAR_MIN; per = net / len(p)
    mar = round(net / -dd, 2) if dd < 0 else 99; top = round(100 * top10 / net) if net > 0 else 999
    ok = (pf >= 1.25 and mar >= 8 and len(p) >= 300 and folds >= 6 and top < 90 and exnet > 0 and per >= 2 * COST * MULT)
    RESULTS.append(dict(fam=fam, cell=cell, n=len(p), net=round(net), pf=round(pf, 3), dd=round(-dd), mar=mar,
                        win=round(100 * w, 1), evr=round(evr, 3), ryr=round(evr * tpy, 1), tpy=round(tpy, 1),
                        folds8=folds, top10_pct=top, exnet=round(exnet), expf=round(exgw / exgl, 3) if exgl > 0 else 99,
                        per_trade=round(per, 2), hold_med=round(float(np.median(h)), 1), hold_mean=round(float(h.mean()), 1),
                        PASS=int(ok)))
    r = RESULTS[-1]
    print("%-13s %-22s n=%5d net=%9s PF=%5.3f DD=%7s MAR=%5.2f win=%4.1f EVR=%5.3f R/YR=%6.1f f8=%d top10=%3d%% ex=%8s $/tr=%6.2f hold=%4.0f/%5.1f %s"
          % (fam, cell, r["n"], format(r["net"], ","), r["pf"], format(r["dd"], ","), min(r["mar"], 99), r["win"], r["evr"],
             r["ryr"], r["folds8"], min(r["top10_pct"], 999), format(r["exnet"], ","), r["per_trade"], r["hold_med"], r["hold_mean"],
             "PASS" if ok else ""), flush=True)


def ride(o, h, l, c, vw, i_open, i_end, entry, stop0, side, mode):
    """Returns (exit price, bars held). VWAPX: on a CLOSE across the VWAP against the trade the
    position exits at the NEXT bar's open (stop still checked first on that bar)."""
    R = side * (entry - stop0); stop = stop0
    tgt = entry + side * R * (1.0 if mode == "T1" else 2.0) if mode in ("T1", "T2") else None
    be = False; be_next = False; leave_next = False
    for i in range(i_open, i_end):
        if leave_next:
            # stop-first pessimism on the exit bar, then the open
            if side == 1 and o[i] <= stop: return o[i], i - i_open + 1
            if side == -1 and o[i] >= stop: return o[i], i - i_open + 1
            return o[i], i - i_open + 1
        if be_next:
            if (side == 1 and entry > stop) or (side == -1 and entry < stop): stop = entry
            be_next = False
        if side == 1:
            if o[i] <= stop: return o[i], i - i_open + 1
            if l[i] <= stop: return stop, i - i_open + 1
            if tgt is not None and h[i] >= tgt: return tgt, i - i_open + 1
            if mode == "RIDE" and not be and c[i] >= entry + R: be = True; be_next = True
            if mode == "VWAPX" and i > i_open and not np.isnan(vw[i]) and c[i] < vw[i]: leave_next = True
        else:
            if o[i] >= stop: return o[i], i - i_open + 1
            if h[i] >= stop: return stop, i - i_open + 1
            if tgt is not None and l[i] <= tgt: return tgt, i - i_open + 1
            if mode == "RIDE" and not be and c[i] <= entry - R: be = True; be_next = True
            if mode == "VWAPX" and i > i_open and not np.isnan(vw[i]) and c[i] > vw[i]: leave_next = True
    return c[i_end - 1], i_end - i_open


def main():
    t0 = time.time()
    A = load_master_arrays(find_master("NQ", "2m", "rth", "db_noadj_rth"), **WIN)
    o, h, l, c, v, did = A["open"], A["high"], A["low"], A["close"], A["volume"], A["day_id"]
    idx = pd.DatetimeIndex(A["index"]); mins = (idx.hour * 60 + idx.minute).values; n = len(c)
    sess = []; a = 0
    while a < n:
        b = a
        while b < n and did[b] == did[a]: b += 1
        sess.append((a, b)); a = b
    nd = len(sess)
    do = np.array([o[x] for x, y in sess]); dc = np.array([c[y - 1] for x, y in sess])
    dh = np.array([h[x:y].max() for x, y in sess]); dl = np.array([l[x:y].min() for x, y in sess])
    seams = set(detect_roll_seams(do, dc, [idx[x] for x, y in sess]))
    atr20 = np.full(nd, np.nan)
    for d in range(20, nd): atr20[d] = (dh[d - 20:d] - dl[d - 20:d]).mean()
    # session VWAP per bar
    tp = (h + l + c) / 3.0; vw = np.full(n, np.nan)
    for a, b in sess:
        pv = np.cumsum(tp[a:b] * v[a:b]); vv = np.cumsum(v[a:b])
        vw[a:b] = np.where(vv > 0, pv / np.maximum(vv, 1e-9), np.nan)
    print("bars %d sessions %d seams %d loaded in %.1fs" % (n, nd, len(seams), time.time() - t0), flush=True)

    def end_for(ex, k_open, b):
        return b if ex in ("RIDE", "VWAPX") else min(k_open + TIME_STOP_BARS, b)

    # M1 MICRO-OR
    for orb in (3, 5):
        for ex in EXITS:
            pnl = []; holds = []
            for d in range(21, nd):
                if d in seams: continue
                a, b = sess[d]
                if b - a < orb + 5 or mins[a] != 570: continue
                rh = h[a:a + orb].max(); rl = l[a:a + orb].min()
                fc = 1 if c[a] > o[a] else (-1 if c[a] < o[a] else 0)
                if rh - rl <= 0 or fc == 0: continue
                for k in range(a + orb, min(a + 30, b - 1)):
                    side = 1 if c[k] > rh else (-1 if c[k] < rl else 0)
                    if side == 0 or side != fc: continue
                    entry = o[k + 1]; stop0 = rl if side == 1 else rh
                    if side * (entry - stop0) <= 0: break
                    px, hb = ride(o, h, l, c, vw, k + 1, end_for(ex, k + 1, b), entry, stop0, side, ex)
                    pnl.append(side * (px - entry) - COST); holds.append(hb); break
            score(pnl, holds, "M1-MICROOR", "or%d/%s" % (orb, ex))

    # M2 OPEN-DRIVE
    for ex in EXITS:
        pnl = []; holds = []
        for d in range(21, nd):
            if d in seams: continue
            a, b = sess[d]
            if b - a < 10 or mins[a] != 570: continue
            side = 1 if c[a] > o[a] else (-1 if c[a] < o[a] else 0)
            if side == 0: continue
            entry = o[a + 1]; stop0 = l[a] if side == 1 else h[a]
            if side * (entry - stop0) <= 0: continue
            px, hb = ride(o, h, l, c, vw, a + 1, end_for(ex, a + 1, b), entry, stop0, side, ex)
            pnl.append(side * (px - entry) - COST); holds.append(hb)
        score(pnl, holds, "M2-OPENDRIVE", ex)

    # M3 PDH/PDL
    for sk in (0.10, 0.20):
        for ex in EXITS:
            pnl = []; holds = []
            for d in range(21, nd):
                if d in seams or np.isnan(atr20[d]) or (d - 1) in seams: continue
                a, b = sess[d]; pdh, pdl = dh[d - 1], dl[d - 1]
                done = {1: False, -1: False}; busy = a
                for k in range(a + 1, b - 1):
                    if mins[k] >= 900 or k < busy: continue
                    side = 1 if (c[k] > pdh and not done[1]) else (-1 if (c[k] < pdl and not done[-1]) else 0)
                    if side == 0: continue
                    entry = o[k + 1]; stop0 = entry - side * sk * atr20[d]
                    px, hb = ride(o, h, l, c, vw, k + 1, end_for(ex, k + 1, b), entry, stop0, side, ex)
                    pnl.append(side * (px - entry) - COST); holds.append(hb)
                    done[side] = True; busy = k + 1 + hb
                    if done[1] and done[-1]: break
            score(pnl, holds, "M3-PDHL", "stop%.2f/%s" % (sk, ex))

    # M4 RANGE-BURST
    rng = h - l; cs = np.concatenate([[0.0], np.cumsum(rng)])
    avg20 = np.full(n, np.nan); avg20[20:] = (cs[20:n] - cs[:n - 20]) / 20.0
    for thr in (3.0, 4.0):
        for ex in EXITS:
            pnl = []; holds = []
            for d in range(21, nd):
                if d in seams: continue
                a, b = sess[d]; cnt = 0; busy = a
                for k in range(a + 1, b - 1):
                    if k < busy or mins[k] < 576 or mins[k] > 930: continue
                    if np.isnan(avg20[k]) or rng[k] < thr * avg20[k] or rng[k] <= 0: continue
                    pos = (c[k] - l[k]) / rng[k]
                    daydir = 1 if c[k] > o[a] else (-1 if c[k] < o[a] else 0)
                    side = 1 if (pos >= 0.75 and daydir == 1) else (-1 if (pos <= 0.25 and daydir == -1) else 0)
                    if side == 0: continue
                    entry = o[k + 1]; stop0 = l[k] if side == 1 else h[k]
                    if side * (entry - stop0) <= 0: continue
                    px, hb = ride(o, h, l, c, vw, k + 1, end_for(ex, k + 1, b), entry, stop0, side, ex)
                    pnl.append(side * (px - entry) - COST); holds.append(hb)
                    cnt += 1; busy = k + 1 + hb
                    if cnt >= 3: break
            score(pnl, holds, "M4-RANGEBURST", "x%.0f/%s" % (thr, ex))

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    keys = list(max(RESULTS, key=len).keys())
    with open(OUT, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys); w.writeheader()
        for r in RESULTS: w.writerow(r)
    print("\n%d cells, %d PASS, %.1f min -> %s" % (len(RESULTS), sum(r.get("PASS", 0) for r in RESULTS), (time.time() - t0) / 60, OUT), flush=True)


if __name__ == "__main__":
    main()
