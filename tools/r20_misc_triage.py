"""
ROUND 20 — three untested families. Pre-registered 2026-08-24 before any results.

A. ORB-AT-OTHER-OPENS: the crown mechanism (short opening range, close-confirmed
   breakout, 0.75x-range stop, breakeven armed on close + acted next bar, ride to
   segment end) relocated to the Asia open (18:00 ET) and London open (03:00 ET)
   on the NQ 1m ETH tape. Cells: {Asia, London} x OR {10, 15} minutes = 4.
   Cost 0.783/RT. Entry window = 120 min after the OR completes. First breakout
   direction wins. Gap-honest stop fills (bar opens through stop -> fill at open).
B. REVERSAL TRIGGERS (NQ 5m RTH + daily chaining): buying weakness only AFTER a
   confirmed trigger.
   SMASH long: uptrend (close>SMA200), day t closes below day t-1's LOW; on day
   t+1 buy a stop at day t's HIGH (fill at level or worse open). Exit close of
   entry day (1d) or 2 days later (3d). Short mirror in downtrends.
   CAPITULATION: down day, range >= 1.5x ATR20, close in bottom quartile of the
   day's range -> buy next open. Exit close +1d or +4d.
   Multi-day chaining uses the HOUSE calendar-anchored roll detector (seam-day
   jumps excluded, 0.25 pt roll cost). No overnight stop. Overnight-held trades
   pay 0.783, same-day trades 0.533. Floor n>=150 (multi-day, as r17).
C. OVERNIGHT SEGMENTS (NQ 1m ETH): the dead close->open hold split into five
   sub-sessions: 16-18, 18-24, 00-03, 03-06, 06-09:30 ET. Long only, each
   segment its own round trip at 0.783. Cells: 5 segments x uptrend {on, off}
   = 10. Roll overnights skipped entirely.
Gates: PF>=1.25, MAR>=8, n>=300 (A, C) / 150 (B). Window ends 2025-06-29,
lockbox never loaded. The grid above is the whole grid; one look.
"""
import os, sys, csv
import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
from augur_engine.data import find_master, load_master_arrays
import importlib.util as _ilu
_sp = _ilu.spec_from_file_location("ond", os.path.join(ROOT, "augur_strategies", "ONDRIFT_1_0.py"))
_ond = _ilu.module_from_spec(_sp); _sp.loader.exec_module(_ond)
detect_roll_seams = _ond.detect_roll_seams

DATE_TO = "2025-06-29"; MULT = 20.0; RT_D = 0.533; RT_ON = 0.783
RESULTS = []


def score(pnl, fam, cell, floor):
    p = np.asarray(pnl, float)
    if len(p) == 0:
        RESULTS.append(dict(fam=fam, cell=cell, n=0, net=0, pf=0, dd=0, mar=0, floor=floor)); return
    gw = p[p > 0].sum(); gl = -p[p < 0].sum(); pf = gw / gl if gl > 1e-9 else float('inf')
    cum = np.cumsum(p); dd = float((cum - np.maximum.accumulate(cum)).min())
    net = float(p.sum()); mar = net / -dd if dd < -1e-9 else float('inf')
    RESULTS.append(dict(fam=fam, cell=cell, n=int(len(p)), net=round(net), pf=round(float(pf), 3),
                        dd=round(float(-dd)), mar=round(float(mar), 2), floor=floor))


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
    dates = [t.date() for t in day_ts]
    seams = set(detect_roll_seams(do, dc, day_ts))
    sma200 = np.full(nd, np.nan)
    for d in range(199, nd):
        sma200[d] = dc[d - 199:d + 1].mean()
    atr20 = np.full(nd, np.nan)
    for d in range(20, nd):
        atr20[d] = (dh[d - 20:d] - dl[d - 20:d]).mean()
    print(f"days={nd} seams={len(seams)}", flush=True)

    me = find_master("NQ", "1m", "eth", "db_noadj_eth")
    E = load_master_arrays(me, date_to=DATE_TO)
    eo, eh, el, ec = E["open"], E["high"], E["low"], E["close"]
    eidx = E["index"]; ets = eidx.values.astype("int64")
    print(f"eth bars={len(eo)}", flush=True)

    def ts(d, minute):
        t = pd.Timestamp(dates[d]).tz_localize(idx5.tz) + pd.Timedelta(minutes=int(minute))
        return t.value

    # ================= A: ORB at other opens =================
    for seg_name, (w0, m_open, w1, m_close) in {
            "asia": ("d", 1080, "d1", 180), "london": ("d1", 180, "d1", 565)}.items():
        for orm in (10, 15):
            pnl = []
            for d in range(210, nd - 1):
                if (d + 1) in seams:
                    continue
                t0 = ts(d, m_open) if w0 == "d" else ts(d + 1, m_open)
                t1 = ts(d, m_close) if w1 == "d" else ts(d + 1, m_close)
                i0 = np.searchsorted(ets, t0); i1 = np.searchsorted(ets, t1)
                if i1 - i0 < orm + 5:
                    continue
                orh = eh[i0:i0 + orm].max(); orl = el[i0:i0 + orm].min(); rng = orh - orl
                if rng <= 0:
                    continue
                side = 0
                for i in range(i0 + orm, min(i0 + orm + 120, i1)):
                    if ec[i] > orh:
                        side = 1; entry = ec[i]; ei = i; break
                    if ec[i] < orl:
                        side = -1; entry = ec[i]; ei = i; break
                if side == 0:
                    continue
                stop = entry - side * 0.75 * rng
                be_armed = False; be_next = False; ex = None
                for i in range(ei + 1, i1):
                    if be_next:
                        stop = entry; be_next = False
                    if side == 1:
                        if eo[i] <= stop: ex = eo[i]; break
                        if el[i] <= stop: ex = stop; break
                        if not be_armed and ec[i] >= entry + 1.0 * rng:
                            be_armed = True; be_next = True
                    else:
                        if eo[i] >= stop: ex = eo[i]; break
                        if eh[i] >= stop: ex = stop; break
                        if not be_armed and ec[i] <= entry - 1.0 * rng:
                            be_armed = True; be_next = True
                if ex is None:
                    ex = ec[i1 - 1]
                pnl.append((side * (ex - entry) - RT_ON) * MULT)
            score(pnl, "A-ORB", f"{seg_name}/or{orm}", 300)
    print("A done", flush=True)

    # ================= B: reversal triggers =================
    def chain_exit(d_entry_day, entry_px, d_exit_day, side):
        raw = dc[d_entry_day] - entry_px
        cost = RT_D if d_exit_day == d_entry_day else RT_ON
        for dd_ in range(d_entry_day + 1, d_exit_day + 1):
            g = do[dd_] - dc[dd_ - 1]
            if dd_ in seams:
                cost += 0.25
            else:
                raw += g
            raw += dc[dd_] - do[dd_]
        return side * raw - cost

    for hold in (0, 2):
        pnl = []
        for t in range(210, nd - 1 - hold):
            if not (dc[t] > sma200[t] and dc[t] < dl[t - 1]):
                continue
            a1, b1 = sess[t + 1]
            trig = dh[t]; fill = None
            for k in range(a1, b1):
                if h5[k] >= trig:
                    fill = max(trig, o5[k]); break
            if fill is None:
                continue
            if any((t + 1 + j) in seams for j in range(1, hold + 1)):
                continue
            pnl.append(chain_exit(t + 1, fill, t + 1 + hold, 1) * MULT)
        score(pnl, "B-SMASH", "long/" + ("1d" if hold == 0 else "3d"), 150)
    for hold in (0, 2):
        pnl = []
        for t in range(210, nd - 1 - hold):
            if not (dc[t] < sma200[t] and dc[t] > dh[t - 1]):
                continue
            a1, b1 = sess[t + 1]
            trig = dl[t]; fill = None
            for k in range(a1, b1):
                if l5[k] <= trig:
                    fill = min(trig, o5[k]); break
            if fill is None:
                continue
            if any((t + 1 + j) in seams for j in range(1, hold + 1)):
                continue
            pnl.append(chain_exit(t + 1, fill, t + 1 + hold, -1) * MULT)
        score(pnl, "B-SMASH", "short/" + ("1d" if hold == 0 else "3d"), 150)
    for hold in (1, 4):
        pnl = []
        for t in range(210, nd - 1 - hold):
            rng_t = dh[t] - dl[t]
            if not (dc[t] < do[t] and rng_t >= 1.5 * atr20[t] and rng_t > 0
                    and (dc[t] - dl[t]) / rng_t <= 0.25):
                continue
            if (t + 1) in seams or any((t + 1 + j) in seams for j in range(1, hold + 1)):
                continue
            pnl.append(chain_exit(t + 1, do[t + 1], t + 1 + hold, 1) * MULT)
        score(pnl, "B-CAP", "buy/" + ("2d" if hold == 1 else "5d"), 150)
    print("B done", flush=True)

    # ================= C: overnight segments =================
    SEGS = {"16-18": ("d", 960, "d", 1080), "18-24": ("d", 1080, "d1", 0),
            "00-03": ("d1", 0, "d1", 180), "03-06": ("d1", 180, "d1", 360),
            "06-0930": ("d1", 360, "d1", 570)}
    for seg, (w0, mm0, w1, mm1) in SEGS.items():
        for up in (True, False):
            pnl = []
            for d in range(210, nd - 1):
                if (d + 1) in seams:
                    continue
                if up and not dc[d] > sma200[d]:
                    continue
                t0 = ts(d, mm0) if w0 == "d" else ts(d + 1, mm0)
                t1 = ts(d, mm1) if w1 == "d" else ts(d + 1, mm1)
                i0 = np.searchsorted(ets, t0); i1 = np.searchsorted(ets, t1)
                if i1 - i0 < 5:
                    continue
                pnl.append(((ec[i1 - 1] - ec[i0]) - RT_ON) * MULT)
            score(pnl, "C-SEG", seg + ("/up" if up else "/all"), 300)
    print("C done", flush=True)

    print(f"\n{'fam':8}{'cell':16}{'n':>6}{'net$':>11}{'PF':>7}{'DD$':>10}{'MAR':>7}  gate")
    for r in RESULTS:
        g = "PASS" if (r['pf'] >= 1.25 and r['mar'] >= 8 and r['n'] >= r['floor']) else "fail"
        print(f"{r['fam']:8}{r['cell']:16}{r['n']:>6}{r['net']:>11,}{r['pf']:>7.3f}{r['dd']:>10,}{r['mar']:>7.2f}  {g}")
    with open(os.path.join(ROOT, "tools", "r16_results", "r20_triage.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(RESULTS[0].keys()))
        w.writeheader(); w.writerows(RESULTS)
    print("saved tools/r16_results/r20_triage.csv")


if __name__ == "__main__":
    main()
