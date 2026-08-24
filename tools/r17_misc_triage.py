"""
ROUND 17 — MISC hunt part 2: multi-day holds + two leftover intraday ideas.

Everything the library has tested so far (except ENGU-Q ETH) is flat by each close.
This round tests the classic HOLD-FOR-DAYS playbook, plus gap continuation and the
10 o'clock reversal.

Pre-registered BEFORE any results (2026-08-24):
- Window: 2010-06-07 -> 2025-06-29 hard cutoff. Lockbox year never loaded.
- Data: daily bars built from the NQ 5m RTH master (open/high/low/close per session).
  Costs 0.533 pts per round trip, $20/pt.
- Multi-day holds and the roll problem: the tape is NOT back-adjusted, so holding
  across a quarterly contract roll would book a fake overnight jump. Fix: seam days
  are detected (same calibrated detector as GAPFADE/round 16); while a position is
  open, a seam day's overnight jump (prior close -> open) is REMOVED from the trade's
  PnL and one extra 0.25-pt roll cost is charged instead. Entries/exits never happen
  ON a seam day.
- Overnight honesty: multi-day trades carry NO overnight stop (we cannot manage one,
  and pretending we could is the exact mistake that cost the old ENGU-Q champion
  $178k on paper). All exits fire on a daily close signal -> filled at the NEXT
  day's open. Gap risk is therefore in the numbers for real.
- Gates (all must pass): PF >= 1.25, MAR >= 8, n >= 300. For the multi-day cells the
  trade-count floor is 150 instead of 300 (a 15-year daily-bar strategy simply
  cannot produce 300 trades; the floor still rejects tiny-sample flukes) — this
  substitution is pre-registered here, before results.
- The grid below is the whole grid.

Concepts:
  RSI2   - Connors RSI(2): buy a 2-day oversold dip while above the 200-day average,
           exit when the close is back above the 5-day average. Short mirror below.
  DBL7   - Connors double-7s: buy a 7-day closing low in an uptrend, exit on a
           7-day closing high.
  DONCH  - Donchian/turtle: enter on a 20-day (or 55-day) breakout, exit on a
           10-day (or 20-day) reverse breakout. Both directions.
  PB20   - pullback-to-trend: in an uptrend (close > 200-day avg), buy the first
           touch of the 20-day average, exit on a close above the prior swing high
           or after 10 days. Short mirror in downtrends.
  GAPGO  - gap continuation: open gaps UP at least X% -> buy the open, ride to the
           close (mirror short on gap down). The opposite of the failed gap fade.
  R1030  - the 10 o'clock reversal: fade the 9:30-10:00 move at 10:00, exit noon
           or the close.
"""
import os, sys, csv
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from augur_engine.data import find_master, load_master_arrays

DATE_TO = "2025-06-29"
RT, MULT, ROLL_PT = 0.533, 20.0, 0.25
RESULTS = []


def _sessions(day_id):
    out = []; a = 0; n = len(day_id)
    while a < n:
        b = a
        while b < n and day_id[b] == day_id[a]:
            b += 1
        out.append((a, b)); a = b
    return out


def _score(pnl, concept, cell, n_floor=300, note=""):
    p = np.asarray(pnl, float)
    if len(p) == 0:
        RESULTS.append(dict(concept=concept, cell=cell, n=0, net=0, pf=0, dd=0, mar=0, note="no trades"))
        return
    gw = p[p > 0].sum(); gl = -p[p < 0].sum()
    pf = gw / gl if gl > 1e-9 else float("inf")
    cum = np.cumsum(p); dd = float((cum - np.maximum.accumulate(cum)).min())
    net = float(p.sum()); mar = net / -dd if dd < -1e-9 else float("inf")
    RESULTS.append(dict(concept=concept, cell=cell, n=int(len(p)), net=net, pf=float(pf),
                        dd=float(-dd), mar=float(mar), note=note or f"floor n>={n_floor}"))


def _seams(do, dc):
    gaps = np.abs(np.concatenate([[0.0], do[1:] - dc[:-1]]))
    s = set()
    for d in range(1, len(gaps)):
        lo = max(0, d - 60)
        if d - lo >= 20:
            med = np.median(gaps[lo:d])
            if gaps[d] >= 15.0 and gaps[d] >= 2.5 * med:
                s.add(d)
    return s


def _wilder_rsi(x, per):
    d = np.diff(x, prepend=x[0])
    up = np.where(d > 0, d, 0.0); dn = np.where(d < 0, -d, 0.0)
    au = np.zeros_like(x); ad = np.zeros_like(x)
    au[per] = up[1:per + 1].mean(); ad[per] = dn[1:per + 1].mean()
    for i in range(per + 1, len(x)):
        au[i] = (au[i - 1] * (per - 1) + up[i]) / per
        ad[i] = (ad[i - 1] * (per - 1) + dn[i]) / per
    rs = np.divide(au, ad, out=np.full_like(x, np.inf), where=ad > 1e-12)
    return 100 - 100 / (1 + rs)


def _signed(do, dc, seams, d_entry, d_exit, pos):
    """signed PnL points net of costs for a long (+1) or short (-1)."""
    raw = dc[d_entry] - do[d_entry]
    cost = RT
    for d in range(d_entry + 1, d_exit):
        gap = do[d] - dc[d - 1]
        if d in seams:
            cost += ROLL_PT
        else:
            raw += gap
        raw += dc[d] - do[d]
    gap = do[d_exit] - dc[d_exit - 1]
    if d_exit in seams:
        cost += ROLL_PT
    else:
        raw += gap
    return pos * raw - cost


def main():
    m = find_master("NQ", "5m", "rth", "db_noadj_rth")
    A = load_master_arrays(m, date_to=DATE_TO)
    o, h, l, c, did = A["open"], A["high"], A["low"], A["close"], A["day_id"]
    idx = A["index"]; mins = (idx.hour * 60 + idx.minute).values
    sess = _sessions(did)
    do = np.array([o[a] for a, b in sess]); dh = np.array([h[a:b].max() for a, b in sess])
    dl = np.array([l[a:b].min() for a, b in sess]); dc = np.array([c[b - 1] for a, b in sess])
    nd = len(sess)
    seams = _seams(do, dc)
    print(f"daily bars: {nd}, seam days: {len(seams)}")

    sma200 = np.full(nd, np.nan); sma5 = np.full(nd, np.nan)
    ema20 = np.full(nd, np.nan)
    for d in range(199, nd):
        sma200[d] = dc[d - 199:d + 1].mean()
    for d in range(4, nd):
        sma5[d] = dc[d - 4:d + 1].mean()
    k = 2 / 21
    ema20[19] = dc[:20].mean()
    for d in range(20, nd):
        ema20[d] = ema20[d - 1] + k * (dc[d] - ema20[d - 1])
    rsi2 = _wilder_rsi(dc, 2)

    # ── RSI2 ──
    for thr in (5.0, 10.0):
        for both in (False, True):
            def ent(d, thr=thr, both=both):
                if dc[d] > sma200[d] and rsi2[d] < thr:
                    return 1
                if both and dc[d] < sma200[d] and rsi2[d] > 100 - thr:
                    return -1
                return 0
            def ex(d, pos, de):
                return (dc[d] > sma5[d]) if pos > 0 else (dc[d] < sma5[d])
            pnl = _run(do, dc, seams, ent, ex, None)
            _score(pnl, "RSI2", f"thr{int(thr)}/{'both' if both else 'long'}", 150)

    # ── DBL7 ──
    for both in (False, True):
        def ent(d, both=both):
            if d < 7: return 0
            if dc[d] > sma200[d] and dc[d] == dc[d - 6:d + 1].min():
                return 1
            if both and dc[d] < sma200[d] and dc[d] == dc[d - 6:d + 1].max():
                return -1
            return 0
        def ex(d, pos, de):
            return (dc[d] == dc[d - 6:d + 1].max()) if pos > 0 else (dc[d] == dc[d - 6:d + 1].min())
        _score(_run(do, dc, seams, ent, ex, None), "DBL7", f"7d/{'both' if both else 'long'}", 150)

    # ── DONCH ──
    for (ein, eout) in ((20, 10), (55, 20)):
        def ent(d, ein=ein):
            if d < ein: return 0
            if dc[d] >= dh[d - ein:d].max():
                return 1
            if dc[d] <= dl[d - ein:d].min():
                return -1
            return 0
        def ex(d, pos, de, eout=eout):
            if d < eout: return False
            return (dc[d] <= dl[d - eout:d].min()) if pos > 0 else (dc[d] >= dh[d - eout:d].max())
        _score(_run(do, dc, seams, ent, ex, None), "DONCH", f"{ein}/{eout}", 150)

    # ── PB20 ──
    for both in (False, True):
        def ent(d, both=both):
            if dc[d] > sma200[d] and dl[d] <= ema20[d] and dc[d - 1] > ema20[d - 1]:
                return 1
            if both and dc[d] < sma200[d] and dh[d] >= ema20[d] and dc[d - 1] < ema20[d - 1]:
                return -1
            return 0
        def ex(d, pos, de):
            return (dc[d] > dh[de - 1]) if pos > 0 else (dc[d] < dl[de - 1])
        _score(_run(do, dc, seams, ent, ex, 10), "PB20", f"ema20/{'both' if both else 'long'}", 150)

    # ── GAPGO (intraday, seam days skipped) ──
    for thr in (0.3, 0.5):
        pnl = []
        for d in range(1, nd):
            if d in seams: continue
            g = 100 * (do[d] - dc[d - 1]) / dc[d - 1]
            if abs(g) < thr: continue
            side = 1 if g > 0 else -1
            pnl.append((side * (dc[d] - do[d]) - RT) * MULT)
        _score(pnl, "GAPGO", f"gap{thr}%", 300)

    # ── R1030 (intraday) ──
    for ex_mode in ("noon", "close"):
        for thr in (0.0, 0.3):
            atr20 = None
            pnl = []
            for d in range(21, nd):
                a, b = sess[d]
                atr = (dh[d - 20:d] - dl[d - 20:d]).mean()
                k10 = None; kex = None
                for k in range(a, b):
                    if k10 is None and mins[k] >= 600: k10 = k
                    if kex is None and mins[k] >= 720: kex = k
                if k10 is None or k10 <= a or k10 >= b - 1: continue
                move = c[k10 - 1] - o[a]
                if move == 0 or (thr > 0 and abs(move) < thr * atr): continue
                side = -1 if move > 0 else 1
                ep = o[k10]
                xp = c[b - 1] if ex_mode == "close" or kex is None or kex >= b else o[kex]
                pnl.append((side * (xp - ep) - RT) * MULT)
            _score(pnl, "R1030", f"{ex_mode}/thr{thr}", 300)

    print()
    print(f"{'concept':7} {'cell':16} {'n':>5} {'net$':>12} {'PF':>6} {'DD$':>10} {'MAR':>7}  gate")
    for r in RESULTS:
        floor = 150 if r["concept"] in ("RSI2", "DBL7", "DONCH", "PB20") else 300
        g = "PASS" if (r["pf"] >= 1.25 and r["mar"] >= 8 and r["n"] >= floor) else "fail"
        print(f"{r['concept']:7} {r['cell']:16} {r['n']:>5} {r['net']:>12,.0f} "
              f"{r['pf']:>6.3f} {r['dd']:>10,.0f} {r['mar']:>7.2f}  {g}")

    outdir = os.path.join(ROOT, "tools", "r16_results")
    os.makedirs(outdir, exist_ok=True)
    with open(os.path.join(outdir, "r17_triage.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(RESULTS[0].keys()))
        w.writeheader(); w.writerows(RESULTS)
    print("\nsaved tools/r16_results/r17_triage.csv")


def _run(do, dc, seams, ent, ex, max_hold):
    n = len(dc); pnl = []; pos = 0; de = 0
    d = 210
    while d < n - 1:
        if pos == 0:
            s = ent(d)
            if s != 0 and (d + 1) not in seams:
                pos, de = s, d + 1
                d += 1
                continue
        else:
            if d >= de and (ex(d, pos, de) or (max_hold and d - de >= max_hold)):
                if (d + 1) not in seams:
                    pnl.append(_signed(do, dc, seams, de, d + 1, pos) * MULT)
                    pos = 0
        d += 1
    return pnl


if __name__ == "__main__":
    main()
