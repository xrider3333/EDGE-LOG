"""
ROUND 37 (2026-09-08) - THE SCALP HUNT, part B: short-hold mechanisms on NQ 1m RTH.

Owner ask: "try to develop something that beats it. focus more on the shorter side like
scalping if possible." Part A of this round is the NOISE family pushed onto 2m and 1m bars
(tools/ryr_search.py on NOISE_1_0.py, tags noise2m / noise1m). This file is part B: five
never-traded SHORT-HOLD mechanisms, every cell pre-registered here before anything ran.

PRE-REGISTRATION (fixed before any cell ran)
  data     NQ 1m RTH, db_noadj_rth, 2010-06-07 .. 2025-06-29. The lockbox after that is
           NEVER loaded by this file. Costs 0.533 pts per round trip, $20 a point.
  fills    every decision on a FINISHED bar, entry at the NEXT bar's open, stop-first
           pessimism inside a bar (a bar that touches both the stop and the target is a
           stop), a gap through the stop fills at the open, targets fill AT the target price.
  exits    three exit families on every mechanism - T1 (target 1R, time stop), T2 (target
           2R, time stop), RIDE (breakeven at 1R armed on a close, ride to the session close).
           Time stops: 30 minutes for M1/M2/M4/M5, 60 for M3. Flat at the session close always.
  seams    quarterly roll-seam days skipped by the house calendar detector (GAPGO_1_0).
  bar      the house triage bar, all legs: PF >= 1.25, MAR >= 8, n >= 300, >= 6 of 8
           chronological slices positive, top-10 share < 90% with a positive ex-top-10 net,
           and $/trade >= 2x the round-turn cost ($21.32) - a scalp that cannot pay twice its
           own cost is not a scalp. Hold time is REPORTED (median / mean minutes), never a gate.
  verdict  a cell that clears every leg goes to a plugin file, parity, concentration_check,
           queue_guard and an Auto-Validate. Anything else is DEAD on this tape and written
           down so nobody re-tests it.

MECHANISMS (39 cells)
  M1 MICRO-ORB   opening range = first {2,3,5} one-minute bars; first CLOSE beyond it inside
                 the first 60 minutes enters next open; direction {first-candle, both};
                 stop = the range's other side. 3 x 2 x 3 exits = 18 cells.
  M2 OPEN-DRIVE  the 09:30 bar's direction, entered at the 09:31 open unconditionally; stop =
                 the 09:30 bar's other extreme; filter {none, first-bar range >= 0.05 x ATR20d}.
                 2 x 3 exits = 6 cells.
  M3 PDH/PDL     first 1m CLOSE beyond the PRIOR session's RTH high (low) after 09:31 and
                 before 15:00; stop {0.10, 0.20} x ATR20d below (above) the entry; one trade
                 per level per day. 2 x 3 exits = 6 cells.
  M4 RANGE-BURST a 1m bar whose range >= {3,4} x its trailing 20-bar mean range, closing in the
                 outer 25% of its own range, in the direction of (close - session open);
                 entries 09:35-15:30, stop = the bar's other extreme, at most 3 a day, one
                 position at a time. 2 x 3 exits = 6 cells.
  M5 VWAP-CROSS  after at least 30 consecutive closes on one side of the session VWAP, the
                 first close on the other side enters next open in the crossing direction;
                 stop = 0.10 x ATR20d beyond the VWAP; one position at a time. 3 cells.

    python tools/r37_scalp_triage.py            -> tools/r37_results/r37_scalp_triage.csv
"""
import os, sys, csv, time
import numpy as np
import pandas as pd
import importlib.util as ilu

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
# a worktree carries the code but not the (gitignored) masters/registry: import the engine from
# whichever checkout actually holds the data (same trick as tools/queue_guard.py)
DATA_REPO = ROOT if os.path.exists(os.path.join(ROOT, "optimizer_history.db")) else r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"
sys.path.insert(0, DATA_REPO)
from augur_engine.data import find_master, load_master_arrays   # noqa: E402

_sp = ilu.spec_from_file_location("gapgo", os.path.join(DATA_REPO, "augur_strategies", "GAPGO_1_0.py"))
_gg = ilu.module_from_spec(_sp); _sp.loader.exec_module(_gg)
detect_roll_seams = _gg.detect_roll_seams

COST, MULT = 0.533, 20.0
WIN = dict(date_from="2010-06-07", date_to="2025-06-29")
OUT = os.path.join(HERE, "r37_results", "r37_scalp_triage.csv")
RESULTS = []


def score(pnl, holds, fam, cell):
    p = np.asarray(pnl, float) * MULT
    if len(p) == 0:
        RESULTS.append(dict(fam=fam, cell=cell, n=0)); return
    gw = p[p > 0].sum(); gl = -p[p < 0].sum(); pf = gw / gl if gl > 1e-9 else 99.0
    cum = np.cumsum(p); dd = float((cum - np.maximum.accumulate(cum)).min())
    net = float(p.sum()); w = float((p > 0).mean()); evr = (1 - w) * (pf - 1)
    yrs = 15.06; tpy = len(p) / yrs
    k = len(p) // 8
    folds = sum(1 for i in range(8) if p[i * k:(i + 1) * k if i < 7 else len(p)].sum() > 0) if k else 0
    srt = sorted(p, reverse=True); top10 = sum(srt[:10]); ex = np.array(srt[10:])
    exnet = float(ex.sum()); exgw = ex[ex > 0].sum(); exgl = -ex[ex < 0].sum()
    h = np.asarray(holds, float)
    per = net / len(p)
    mar = round(net / -dd, 2) if dd < 0 else 99
    top = round(100 * top10 / net) if net > 0 else 999
    ok = (pf >= 1.25 and mar >= 8 and len(p) >= 300 and folds >= 6 and top < 90 and exnet > 0
          and per >= 2 * COST * MULT)
    RESULTS.append(dict(fam=fam, cell=cell, n=len(p), net=round(net), pf=round(pf, 3), dd=round(-dd),
                        mar=mar, win=round(100 * w, 1), evr=round(evr, 3), ryr=round(evr * tpy, 1),
                        tpy=round(tpy, 1), folds8=folds, top10_pct=top, exnet=round(exnet),
                        expf=round(exgw / exgl, 3) if exgl > 0 else 99, per_trade=round(per, 2),
                        hold_med=round(float(np.median(h)), 1), hold_mean=round(float(h.mean()), 1),
                        PASS=int(ok)))
    r = RESULTS[-1]
    print("%-12s %-28s n=%5d net=%9s PF=%5.3f DD=%7s MAR=%5.2f win=%4.1f EVR=%5.3f R/YR=%6.1f f8=%d top10=%3d%% ex=%8s $/tr=%6.2f hold=%4.0f/%5.1f %s"
          % (fam, cell, r["n"], format(r["net"], ","), r["pf"], format(r["dd"], ","), min(r["mar"], 99), r["win"],
             r["evr"], r["ryr"], r["folds8"], min(r["top10_pct"], 999), format(r["exnet"], ","), r["per_trade"],
             r["hold_med"], r["hold_mean"], "PASS" if ok else ""), flush=True)


def ride(o, h, l, c, i_open, i_end, entry, stop0, side, mode):
    """Enter at o[i_open]. mode 'T1'/'T2' = fixed target at 1R/2R (stop-first pessimism), 'RIDE' =
    breakeven armed on a close at +1R acting from the next bar, exit at c[i_end-1] if alive.
    Returns (exit price, bars held)."""
    R = side * (entry - stop0); stop = stop0
    tgt = entry + side * R * (1.0 if mode == "T1" else 2.0) if mode != "RIDE" else None
    be = False; be_next = False
    for i in range(i_open, i_end):
        if be_next:
            if (side == 1 and entry > stop) or (side == -1 and entry < stop):
                stop = entry
            be_next = False
        if side == 1:
            if o[i] <= stop: return o[i], i - i_open + 1
            if l[i] <= stop: return stop, i - i_open + 1
            if tgt is not None and h[i] >= tgt: return tgt, i - i_open + 1
            if tgt is None and not be and c[i] >= entry + R: be = True; be_next = True
        else:
            if o[i] >= stop: return o[i], i - i_open + 1
            if h[i] >= stop: return stop, i - i_open + 1
            if tgt is not None and l[i] <= tgt: return tgt, i - i_open + 1
            if tgt is None and not be and c[i] <= entry - R: be = True; be_next = True
    return c[i_end - 1], i_end - i_open


def main():
    t0 = time.time()
    A = load_master_arrays(find_master("NQ", "1m", "rth", "db_noadj_rth"), **WIN)
    o, h, l, c, v, did = A["open"], A["high"], A["low"], A["close"], A["volume"], A["day_id"]
    idx = pd.DatetimeIndex(A["index"]); mins = (idx.hour * 60 + idx.minute).values
    n = len(c)
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
    print("bars %d sessions %d seams %d loaded in %.1fs" % (n, nd, len(seams), time.time() - t0), flush=True)
    EXITS = ("T1", "T2", "RIDE")

    def sess_close_idx(a, b):
        return b                       # RTH master: last bar of the session is the close

    # ---------- M1 MICRO-ORB ----------
    for orb in (2, 3, 5):
        for dirmode in ("first", "both"):
            for ex in EXITS:
                pnl = []; holds = []
                for d in range(21, nd):
                    if d in seams: continue
                    a, b = sess[d]
                    if b - a < orb + 5: continue
                    rh = h[a:a + orb].max(); rl = l[a:a + orb].min()
                    if rh - rl <= 0: continue
                    fc = 1 if c[a] > o[a] else (-1 if c[a] < o[a] else 0)
                    if dirmode == "first" and fc == 0: continue
                    for k in range(a + orb, min(a + 60, b - 1)):
                        side = 1 if c[k] > rh else (-1 if c[k] < rl else 0)
                        if side == 0 or (dirmode == "first" and side != fc): continue
                        entry = o[k + 1]; stop0 = rl if side == 1 else rh
                        if side * (entry - stop0) <= 0: break
                        i_end = b if ex == "RIDE" else min(k + 1 + 30, b)
                        px, hb = ride(o, h, l, c, k + 1, i_end, entry, stop0, side, ex)
                        pnl.append(side * (px - entry) - COST); holds.append(hb)
                        break
                score(pnl, holds, "M1-MICROORB", "or%d/%s/%s" % (orb, dirmode, ex))

    # ---------- M2 OPEN-DRIVE ----------
    for filt in ("none", "rng05"):
        for ex in EXITS:
            pnl = []; holds = []
            for d in range(21, nd):
                if d in seams or np.isnan(atr20[d]): continue
                a, b = sess[d]
                if b - a < 10 or mins[a] != 570: continue
                side = 1 if c[a] > o[a] else (-1 if c[a] < o[a] else 0)
                if side == 0: continue
                if filt == "rng05" and (h[a] - l[a]) < 0.05 * atr20[d]: continue
                entry = o[a + 1]; stop0 = l[a] if side == 1 else h[a]
                if side * (entry - stop0) <= 0: continue
                i_end = b if ex == "RIDE" else min(a + 1 + 30, b)
                px, hb = ride(o, h, l, c, a + 1, i_end, entry, stop0, side, ex)
                pnl.append(side * (px - entry) - COST); holds.append(hb)
            score(pnl, holds, "M2-OPENDRIVE", "%s/%s" % (filt, ex))

    # ---------- M3 PDH/PDL ----------
    for sk in (0.10, 0.20):
        for ex in EXITS:
            pnl = []; holds = []
            for d in range(21, nd):
                if d in seams or np.isnan(atr20[d]) or (d - 1) in seams: continue
                a, b = sess[d]
                pdh, pdl = dh[d - 1], dl[d - 1]
                done = {1: False, -1: False}; busy_until = a
                for k in range(a + 1, b - 1):
                    if mins[k] >= 900 or k < busy_until: continue
                    side = 1 if (c[k] > pdh and not done[1]) else (-1 if (c[k] < pdl and not done[-1]) else 0)
                    if side == 0: continue
                    entry = o[k + 1]; stop0 = entry - side * sk * atr20[d]
                    i_end = b if ex == "RIDE" else min(k + 1 + 60, b)
                    px, hb = ride(o, h, l, c, k + 1, i_end, entry, stop0, side, ex)
                    pnl.append(side * (px - entry) - COST); holds.append(hb)
                    done[side] = True; busy_until = k + 1 + hb
                    if done[1] and done[-1]: break
            score(pnl, holds, "M3-PDHL", "stop%.2f/%s" % (sk, ex))

    # ---------- M4 RANGE-BURST ----------
    rng = h - l
    cs = np.concatenate([[0.0], np.cumsum(rng)])
    avg20 = np.full(n, np.nan); avg20[20:] = (cs[20:n] - cs[:n - 20]) / 20.0   # trailing 20, excluding bar i
    for thr in (3.0, 4.0):
        for ex in EXITS:
            pnl = []; holds = []
            for d in range(21, nd):
                if d in seams: continue
                a, b = sess[d]; cnt = 0; busy_until = a
                for k in range(a + 1, b - 1):
                    if k < busy_until or mins[k] < 575 or mins[k] > 930: continue
                    if np.isnan(avg20[k]) or rng[k] < thr * avg20[k] or rng[k] <= 0: continue
                    pos = (c[k] - l[k]) / rng[k]
                    daydir = 1 if c[k] > o[a] else (-1 if c[k] < o[a] else 0)
                    side = 1 if (pos >= 0.75 and daydir == 1) else (-1 if (pos <= 0.25 and daydir == -1) else 0)
                    if side == 0: continue
                    entry = o[k + 1]; stop0 = l[k] if side == 1 else h[k]
                    if side * (entry - stop0) <= 0: continue
                    i_end = b if ex == "RIDE" else min(k + 1 + 30, b)
                    px, hb = ride(o, h, l, c, k + 1, i_end, entry, stop0, side, ex)
                    pnl.append(side * (px - entry) - COST); holds.append(hb)
                    cnt += 1; busy_until = k + 1 + hb
                    if cnt >= 3: break
            score(pnl, holds, "M4-RANGEBURST", "x%.0f/%s" % (thr, ex))

    # ---------- M5 VWAP-CROSS ----------
    tp = (h + l + c) / 3.0
    for ex in EXITS:
        pnl = []; holds = []
        for d in range(21, nd):
            if d in seams or np.isnan(atr20[d]): continue
            a, b = sess[d]
            pv = np.cumsum(tp[a:b] * v[a:b]); vv = np.cumsum(v[a:b])
            vw = np.where(vv > 0, pv / np.maximum(vv, 1e-9), np.nan)
            above = c[a:b] > vw
            run = 0; prev = None; busy_until = a
            for j in range(b - a - 1):
                k = a + j
                cur = bool(above[j])
                if prev is None or cur == prev:
                    run += 1
                else:
                    crossed = run >= 30; run = 1
                    if crossed and k >= busy_until and mins[k] < 930:
                        side = 1 if cur else -1
                        entry = o[k + 1]; stop0 = vw[j] - side * 0.10 * atr20[d]
                        if side * (entry - stop0) > 0:
                            i_end = b if ex == "RIDE" else min(k + 1 + 30, b)
                            px, hb = ride(o, h, l, c, k + 1, i_end, entry, stop0, side, ex)
                            pnl.append(side * (px - entry) - COST); holds.append(hb)
                            busy_until = k + 1 + hb
                prev = cur
        score(pnl, holds, "M5-VWAPCROSS", "run30/%s" % ex)

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    keys = list(max(RESULTS, key=len).keys())
    with open(OUT, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys); w.writeheader()
        for r in RESULTS: w.writerow(r)
    print("\n%d cells, %d PASS, %.1f min -> %s" % (len(RESULTS), sum(r.get("PASS", 0) for r in RESULTS),
                                                   (time.time() - t0) / 60, OUT), flush=True)


if __name__ == "__main__":
    main()
