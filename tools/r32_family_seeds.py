"""
ROUND 32 — FAMILY SEEDS. Owner 2026-09-08: "find something that can potentially branch out
into its own strategy family and I'll point another Claude at it."

Two mechanisms the library has never traded, pre-registered here before any result.
Both use the house risk engine (close-confirmed entry -> next-bar fill, stop, breakeven
armed on a close and acted on the NEXT bar, gap-honest stop fills) and both are judged on
the FULL house read: PF, raw net/DD, EV R, R / YR, 8-slice consistency, AND the
concentration test (top-10 share of net, ex-top-10 net) - the test the round-28 "record"
failed after passing a 6-gate validate.

A. RELEASE - scheduled economic-release momentum (NQ 1m, 24-hour tape).
   Events: 08:30 ET (the pre-market data drop: CPI/NFP/claims/retail sales/GDP...) and
   10:00 ET (ISM/confidence/home sales...). No release calendar is used: EVERY weekday is
   traded and the data decides whether release days carry the family. Pre-event range =
   the 5 one-minute bars ending at the event minute. Entry = first 1m CLOSE beyond that
   range within `win` minutes after the event -> next bar open. Stop = the other side of
   the range (risk = range) x stop_mult. Breakeven at 1R. Exit at a time limit or at the
   RTH close. Cost: 0.783 for 08:30 trades (Globex liquidity), 0.533 for 10:00 trades.
   Cells: event {0830, 1000} x exit {60m, 120m, close} x pre-filter {none, coiled: range
   <= 0.5 x median range of the prior 20 events} = 12.
B. VALUE AREA - prior-day 70% volume value area (market profile) on NQ 5m RTH.
   Profile = the prior RTH session's volume by price bin (bin = 0.25 x ATR20 of daily
   ranges, capped 1..10 pts); POC = the modal bin; value area = the smallest set of bins
   around the POC holding 70% of the volume -> VAH / VAL. Entry (after 10:00 ET): first 5m
   CLOSE above VAH -> long at next open; below VAL -> short; one trade per direction per
   day. Stop = entry -/+ stop_mult x (VAH - VAL). Breakeven at 1R. Exit at the close.
   Cells: stop_mult {0.5, 1.0} x open-location filter {none, open INSIDE value (a true
   break out of balance)} x acceptance {1 close, 2 consecutive closes} = 8.
Window 2010-06-07 .. 2025-06-29 (lockbox never loaded). Roll nights skipped on the 24h
tape via the house calendar detector. Whole grid; one look.
"""
import os, sys, csv
import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT); os.chdir(ROOT)
from augur_engine.data import find_master, load_master_arrays
import importlib.util as _ilu
_sp = _ilu.spec_from_file_location("ond", os.path.join(ROOT, "augur_strategies", "ONDRIFT_1_0.py"))
_ond = _ilu.module_from_spec(_sp); _sp.loader.exec_module(_ond)
detect_roll_seams = _ond.detect_roll_seams

DATE_TO = "2025-06-29"; MULT = 20.0
RESULTS = []


def score(pnl, fam, cell, floor=300):
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
    RESULTS.append(dict(fam=fam, cell=cell, n=len(p), net=round(net), pf=round(pf, 3), dd=round(-dd),
                        mar=round(net / -dd, 2) if dd < 0 else 99, win=round(100 * w, 1), evr=round(evr, 3),
                        ryr=round(evr * tpy, 1), tpy=round(tpy, 1), folds8=folds,
                        top10_pct=round(100 * top10 / net) if net > 0 else 999, exnet=round(exnet),
                        expf=round(exgw / exgl, 3) if exgl > 0 else 99, floor=floor))


def ride(o, h, l, c, i_open, i_end, entry, stop0, side):
    """enter at o[i_open]; BE at +1R armed on close -> acts next bar; exit at c[i_end-1] if alive."""
    R = side * (entry - stop0); stop = stop0; be = False; be_next = False
    for i in range(i_open, i_end):
        if be_next:
            stop = entry if (side == 1 and entry > stop) or (side == -1 and entry < stop) else stop; be_next = False
        if side == 1:
            if o[i] <= stop: return o[i]
            if l[i] <= stop: return stop
            if not be and c[i] >= entry + R: be = True; be_next = True
        else:
            if o[i] >= stop: return o[i]
            if h[i] >= stop: return stop
            if not be and c[i] <= entry - R: be = True; be_next = True
    return c[i_end - 1]


def family_release():
    m = find_master("NQ", "1m", "eth", "db_noadj_eth")
    E = load_master_arrays(m, date_to=DATE_TO)
    o, h, l, c = E["open"], E["high"], E["low"], E["close"]
    idx = E["index"]; mins = (idx.hour * 60 + idx.minute).values
    dates = np.array([d for d in idx.date])
    # daily (RTH-ish) aggregation for seams: use calendar day close/open on the ETH tape
    ud, first = np.unique(dates, return_index=True)
    last = np.r_[first[1:] - 1, len(c) - 1]
    do = o[first]; dc = c[last]; dts = [idx[i] for i in first]
    seams = set(detect_roll_seams(do, dc, dts))
    seam_dates = {ud[s] for s in seams}
    day_of = {d: k for k, d in enumerate(ud)}
    # index of the first bar at/after minute M on each date
    for ev_min, ev_name, cost in ((510, "0830", 0.783), (600, "1000", 0.533)):
        hist_rng = []
        cells = {(ex, filt): [] for ex in ("60m", "120m", "close") for filt in ("none", "coiled")}
        for k, d in enumerate(ud):
            if d in seam_dates or pd.Timestamp(d).weekday() >= 5:
                continue
            a, b = first[k], last[k] + 1
            seg = np.where(mins[a:b] >= ev_min)[0]
            if len(seg) == 0: continue
            ie = a + seg[0]                       # first bar at/after the event minute
            if ie - 5 < a or mins[ie] != ev_min: continue
            rh = h[ie - 5:ie].max(); rl = l[ie - 5:ie].min(); rng = rh - rl
            if rng <= 0: continue
            med = np.median(hist_rng[-20:]) if len(hist_rng) >= 20 else None
            hist_rng.append(rng)
            coiled = (med is not None and rng <= 0.5 * med)
            # entry scan: first close beyond range within 15 min
            side = 0
            for i in range(ie, min(ie + 15, b - 1)):
                if c[i] > rh: side = 1; break
                if c[i] < rl: side = -1; break
            if side == 0: continue
            i_open = i + 1; entry = o[i_open]
            stop0 = rl if side == 1 else rh
            if side * (entry - stop0) <= 0: continue
            # exits
            closebar = np.where(mins[a:b] >= 960)[0]      # 16:00 ET
            i_close = a + closebar[0] if len(closebar) else b
            for ex in ("60m", "120m", "close"):
                i_end = min(i_open + (60 if ex == "60m" else 120), i_close) if ex != "close" else i_close
                if i_end <= i_open: continue
                px = ride(o, h, l, c, i_open, i_end, entry, stop0, side)
                pnl = side * (px - entry) - cost
                cells[(ex, "none")].append(pnl)
                if coiled: cells[(ex, "coiled")].append(pnl)
        for (ex, filt), pnl in cells.items():
            score(pnl, "A-RELEASE", f"{ev_name}/{ex}/{filt}")
        print(f"RELEASE {ev_name} done", flush=True)


def family_value_area():
    m = find_master("NQ", "5m", "rth", "db_noadj_rth")
    R = load_master_arrays(m, date_to=DATE_TO)
    o, h, l, c, v, did = R["open"], R["high"], R["low"], R["close"], R["volume"], R["day_id"]
    idx = R["index"]; mins = (idx.hour * 60 + idx.minute).values
    sess = []; a = 0; n = len(c)
    while a < n:
        b = a
        while b < n and did[b] == did[a]: b += 1
        sess.append((a, b)); a = b
    do = np.array([o[x] for x, y in sess]); dh = np.array([h[x:y].max() for x, y in sess])
    dl = np.array([l[x:y].min() for x, y in sess]); dc = np.array([c[y - 1] for x, y in sess])
    nd = len(sess)
    seams = set(detect_roll_seams(do, dc, [idx[x] for x, y in sess]))
    cells = {(sm, of, acc): [] for sm in (0.5, 1.0) for of in ("none", "inside") for acc in (1, 2)}
    for d in range(21, nd):
        if d in seams: continue
        atr = (dh[d - 20:d] - dl[d - 20:d]).mean(); binw = min(10.0, max(1.0, 0.25 * atr))
        pa, pb = sess[d - 1]
        # prior-day volume profile from 5m bars: spread each bar's volume evenly over its range
        lo = dl[d - 1]; hi = dh[d - 1]; nb = int(np.ceil((hi - lo) / binw)) + 1
        prof = np.zeros(nb)
        for k in range(pa, pb):
            b0 = int((l[k] - lo) // binw); b1 = int((h[k] - lo) // binw)
            b1 = max(b0, min(b1, nb - 1)); prof[b0:b1 + 1] += v[k] / (b1 - b0 + 1)
        if prof.sum() <= 0: continue
        poc = int(np.argmax(prof)); tot = prof.sum(); acc_v = prof[poc]; ia = ib = poc
        while acc_v < 0.70 * tot and (ia > 0 or ib < nb - 1):
            up = prof[ib + 1] if ib < nb - 1 else -1; dn = prof[ia - 1] if ia > 0 else -1
            if up >= dn: ib += 1; acc_v += up
            else: ia -= 1; acc_v += dn
        vah = lo + (ib + 1) * binw; val = lo + ia * binw; width = vah - val
        if width <= 0: continue
        a, b = sess[d]
        open_inside = val <= do[d] <= vah
        for sm in (0.5, 1.0):
            for of in ("none", "inside"):
                if of == "inside" and not open_inside: continue
                for acc in (1, 2):
                    done = {1: False, -1: False}; run = {1: 0, -1: 0}
                    for k in range(a, b - 1):
                        if mins[k] < 600: continue
                        for side, lvl in ((1, vah), (-1, val)):
                            if done[side]: continue
                            beyond = (c[k] > lvl) if side == 1 else (c[k] < lvl)
                            run[side] = run[side] + 1 if beyond else 0
                            if run[side] >= acc:
                                entry = o[k + 1]; stop0 = entry - side * sm * width
                                px = ride(o, h, l, c, k + 1, b, entry, stop0, side)
                                cells[(sm, of, acc)].append(side * (px - entry) - 0.533)
                                done[side] = True
    for (sm, of, acc), pnl in cells.items():
        score(pnl, "B-VALUEAREA", f"stop{sm}/open-{of}/acc{acc}")
    print("VALUE AREA done", flush=True)


if __name__ == "__main__":
    family_release()
    family_value_area()
    print(f"\n{'fam':12}{'cell':22}{'n':>6}{'net$':>11}{'PF':>7}{'DD$':>10}{'n/DD':>6}{'win':>6}{'EVR':>7}{'R/YR':>7}{'f8':>3}{'top10%':>7}{'exnet$':>10}{'exPF':>6}  verdict")
    for r in RESULTS:
        if not r.get("n"):
            print(f"{r['fam']:12}{r['cell']:22}  no trades"); continue
        g = "PASS" if (r["pf"] >= 1.25 and r["mar"] >= 8 and r["n"] >= r["floor"] and r["top10_pct"] < 90 and r["exnet"] > 0) else "fail"
        print(f"{r['fam']:12}{r['cell']:22}{r['n']:>6}{r['net']:>11,}{r['pf']:>7.3f}{r['dd']:>10,}{r['mar']:>6.2f}{r['win']:>6.1f}{r['evr']:>7.3f}{r['ryr']:>7.1f}{r['folds8']:>3}{r['top10_pct']:>7}{r['exnet']:>10,}{r['expf']:>6.2f}  {g}")
    with open("tools/r16_results/r32_family_seeds.csv", "w", newline="") as f:
        keys = [k for k in RESULTS[0].keys()]
        for r in RESULTS: keys = keys if all(k in r for k in keys) else keys
        w = csv.DictWriter(f, fieldnames=list(max(RESULTS, key=len).keys())); w.writeheader()
        for r in RESULTS: w.writerow(r)
    print("saved tools/r16_results/r32_family_seeds.csv")
