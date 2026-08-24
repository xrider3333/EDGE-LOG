"""
ROUND 16 — MISC hunt triage: six classic mechanisms the library has never tested.

Pre-registered BEFORE any results were computed (2026-08-24):
- Window: 2010-06-07 -> 2025-06-29 hard cutoff (date_to slicing). The lockbox year
  (2025-06-30 -> ) is NEVER loaded here.
- Deciding dataset: NQ 5m RTH (SESSBRK: NQ 1m ETH by construction). Costs: NQ RTH
  0.533 pts/RT, NQ ETH 0.783, ES RTH 0.363. PAIRS pays BOTH legs.
- Gates (all must pass to survive triage): PF >= 1.25, MAR (net/maxDD) >= 8, n >= 300.
- Fills: signals evaluate on a bar's CLOSE -> market entry at the NEXT bar's OPEN.
  Resting stop-entry orders (OOPS/NR7/SESSBRK) fill at the level with gap-through at
  the bar's open (open beyond level -> fill at open). Stop-first pessimism inside a
  bar. Roll-seam days are skipped for gap-referencing concepts (OOPS) using the
  calibrated detector from GAPFADE_1_0.
- Grid: the cells below are the WHOLE grid. No window-shopping past them.

Concepts (none in the library per the 2026-08-24 inventory):
  OOPS    - Larry Williams gap-reversal: open gaps beyond prior day's extreme, resting
            stop back at that extreme, trade the failure of the gap.
  NR7     - Crabel volatility-contraction: NR7/NR4/inside day -> next-day breakout
            stops at prior high/low.
  PIVOT   - floor-trader pivots off prior day HLC: fade R1/S1 toward P, and the
            breakout mirror.
  MOC     - last-hour drift: enter late-day in the direction of (or against) the
            day-so-far move, exit on the close.
  SESSBRK - overnight-session range breakout on the 24h tape (Asia range -> London/NY
            morning; London range -> US day).
  PAIRS   - ES/NQ log-ratio z-score mean reversion, 1 contract each leg, both legs
            costed.
"""
import os, sys, csv
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from augur_engine.data import find_master, load_master_arrays

DATE_TO = "2025-06-29"
NQ_RT, NQ_ETH_RT, ES_RT = 0.533, 0.783, 0.363
NQ_MULT, ES_MULT = 20.0, 50.0

RESULTS = []   # dicts: concept, cell, n, net$, pf, dd$, mar, note


def _sessions(day_id):
    out = []
    a, n = 0, len(day_id)
    while a < n:
        b = a
        while b < n and day_id[b] == day_id[a]:
            b += 1
        out.append((a, b)); a = b
    return out


def _score(pnl_dollars, concept, cell, note=""):
    p = np.asarray(pnl_dollars, float)
    if len(p) == 0:
        RESULTS.append(dict(concept=concept, cell=cell, n=0, net=0.0, pf=0.0,
                            dd=0.0, mar=0.0, note="no trades"))
        return
    wins = p[p > 0]; losses = p[p < 0]
    gw, gl = wins.sum(), -losses.sum()
    pf = gw / gl if gl > 1e-9 else float("inf")
    cum = np.cumsum(p); dd = float((cum - np.maximum.accumulate(cum)).min())
    net = float(p.sum())
    mar = (net / -dd) if dd < -1e-9 else float("inf")
    RESULTS.append(dict(concept=concept, cell=cell, n=int(len(p)), net=net, pf=float(pf),
                        dd=float(-dd), mar=float(mar), note=note))


def _daily(o, h, l, c, sess):
    """per-session open/high/low/close arrays."""
    do = np.array([o[a] for a, b in sess]); dh = np.array([h[a:b].max() for a, b in sess])
    dl = np.array([l[a:b].min() for a, b in sess]); dc = np.array([c[b - 1] for a, b in sess])
    return do, dh, dl, dc


def _roll_seam_days(do, dc):
    """calibrated seam detector (GAPFADE_1_0 convention): |overnight gap| >= 15 pts AND
    >= 2.5x trailing 60-session median |gap|."""
    gaps = np.abs(np.concatenate([[0.0], do[1:] - dc[:-1]]))
    seam = set()
    for d in range(1, len(gaps)):
        lo = max(0, d - 60)
        med = np.median(gaps[lo:d]) if d - lo >= 20 else None
        if med is not None and gaps[d] >= 15.0 and gaps[d] >= 2.5 * med:
            seam.add(d)
    return seam


# ── OOPS ─────────────────────────────────────────────────────────────────────
def run_oops(o, h, l, c, sess, stop_atr, exit_mode):
    do, dh, dl, dc = _daily(o, h, l, c, sess)
    seam = _roll_seam_days(do, dc)
    # daily ATR20 (true range on the daily aggregates), shifted: value known at day d
    # uses days <= d-1 only.
    tr = np.maximum(dh[1:] - dl[1:], np.maximum(np.abs(dh[1:] - dc[:-1]),
                                                np.abs(dl[1:] - dc[:-1])))
    pnl = []
    for d in range(21, len(sess)):
        if d in seam:
            continue
        atr = tr[d - 21:d - 1].mean()
        a, b = sess[d]
        side = 0
        if do[d] < dl[d - 1]:
            side, lvl = +1, dl[d - 1]        # gapped below prior low -> buy stop there
        elif do[d] > dh[d - 1]:
            side, lvl = -1, dh[d - 1]        # gapped above prior high -> sell stop there
        if side == 0:
            continue
        entry_k = None
        for k in range(a, b):
            if side > 0 and h[k] >= lvl:
                entry_px = max(o[k], lvl); entry_k = k; break
            if side < 0 and l[k] <= lvl:
                entry_px = min(o[k], lvl); entry_k = k; break
        if entry_k is None:
            continue                          # gap never came back -> no fill
        stop = entry_px - side * stop_atr * atr
        tgt = dc[d - 1] if exit_mode == "pc" else None   # prior close target
        exit_px = None
        for k in range(entry_k + 1, b):
            if side > 0:
                if l[k] <= stop:
                    exit_px = o[k] if o[k] < stop else stop; break
                if tgt is not None and h[k] >= tgt:
                    exit_px = tgt; break
            else:
                if h[k] >= stop:
                    exit_px = o[k] if o[k] > stop else stop; break
                if tgt is not None and l[k] <= tgt:
                    exit_px = tgt; break
        if exit_px is None:
            exit_px = c[b - 1]
        pnl.append((side * (exit_px - entry_px) - NQ_RT) * NQ_MULT)
    return pnl


# ── NR7 / volatility contraction ─────────────────────────────────────────────
def run_nrx(o, h, l, c, sess, cond, exit_mode):
    do, dh, dl, dc = _daily(o, h, l, c, sess)
    rng = dh - dl
    pnl = []
    for d in range(8, len(sess)):
        y = d - 1
        if cond == "nr7":
            ok = rng[y] == rng[y - 6:y + 1].min()
        elif cond == "nr4":
            ok = rng[y] == rng[y - 3:y + 1].min()
        else:                                  # inside day
            ok = dh[y] < dh[y - 1] and dl[y] > dl[y - 1]
        if not ok or rng[y] <= 0:
            continue
        up, dn = dh[y] + 0.25, dl[y] - 0.25
        a, b = sess[d]
        side = 0
        for k in range(a, b):
            hit_up = h[k] >= up; hit_dn = l[k] <= dn
            if hit_up and hit_dn:
                side = 0; break               # ambiguous first-touch bar -> skip day
            if hit_up:
                side, entry_px, entry_k = +1, max(o[k], up), k; break
            if hit_dn:
                side, entry_px, entry_k = -1, min(o[k], dn), k; break
        if side == 0:
            continue
        stop = dn if side > 0 else up          # opposite trigger
        risk = abs(entry_px - stop)
        tgt = entry_px + side * 2.0 * risk if exit_mode == "2R" else None
        exit_px = None
        for k in range(entry_k + 1, b):
            if side > 0:
                if l[k] <= stop:
                    exit_px = o[k] if o[k] < stop else stop; break
                if tgt is not None and h[k] >= tgt:
                    exit_px = tgt; break
            else:
                if h[k] >= stop:
                    exit_px = o[k] if o[k] > stop else stop; break
                if tgt is not None and l[k] <= tgt:
                    exit_px = tgt; break
        if exit_px is None:
            exit_px = c[b - 1]
        pnl.append((side * (exit_px - entry_px) - NQ_RT) * NQ_MULT)
    return pnl


# ── PIVOT ────────────────────────────────────────────────────────────────────
def run_pivot(o, h, l, c, sess, mode, stop_frac):
    do, dh, dl, dc = _daily(o, h, l, c, sess)
    pnl = []
    for d in range(1, len(sess)):
        P = (dh[d - 1] + dl[d - 1] + dc[d - 1]) / 3.0
        R1, S1 = 2 * P - dl[d - 1], 2 * P - dh[d - 1]
        band = R1 - P
        if band <= 0:
            continue
        a, b = sess[d]
        entered = False
        for k in range(a, b - 1):
            if entered:
                break
            if mode == "fade":
                if c[k] >= R1:
                    side, entry_px, entry_k = -1, o[k + 1], k + 1
                elif c[k] <= S1:
                    side, entry_px, entry_k = +1, o[k + 1], k + 1
                else:
                    continue
                tgt = P
                stop = entry_px + (stop_frac * band if side < 0 else -stop_frac * band)
            else:                              # breakout through the level, with trend
                if c[k] >= R1:
                    side, entry_px, entry_k = +1, o[k + 1], k + 1
                elif c[k] <= S1:
                    side, entry_px, entry_k = -1, o[k + 1], k + 1
                else:
                    continue
                tgt = None
                stop = entry_px - side * stop_frac * band
            entered = True
            exit_px = None
            for j in range(entry_k + 1, b):
                if side > 0:
                    if l[j] <= stop:
                        exit_px = o[j] if o[j] < stop else stop; break
                    if tgt is not None and h[j] >= tgt:
                        exit_px = tgt; break
                else:
                    if h[j] >= stop:
                        exit_px = o[j] if o[j] > stop else stop; break
                    if tgt is not None and l[j] <= tgt:
                        exit_px = tgt; break
            if exit_px is None:
                exit_px = c[b - 1]
            pnl.append((side * (exit_px - entry_px) - NQ_RT) * NQ_MULT)
    return pnl


# ── MOC late-day drift ───────────────────────────────────────────────────────
def run_moc(o, h, l, c, sess, entry_bar_from_end, mode, thr_atr):
    do, dh, dl, dc = _daily(o, h, l, c, sess)
    rng20 = None
    pnl = []
    for d in range(21, len(sess)):
        a, b = sess[d]
        m = b - a
        if m < entry_bar_from_end + 2:
            continue
        atr = (dh[d - 20:d] - dl[d - 20:d]).mean()
        ke = b - entry_bar_from_end          # signal = close of bar ke-1, enter open of ke
        move = c[ke - 1] - o[a]
        if thr_atr > 0 and abs(move) < thr_atr * atr:
            continue
        if move == 0:
            continue
        side = (1 if move > 0 else -1) * (1 if mode == "mom" else -1)
        entry_px = o[ke]
        exit_px = c[b - 1]
        pnl.append((side * (exit_px - entry_px) - NQ_RT) * NQ_MULT)
    return pnl


# ── SESSBRK on the 24h tape ──────────────────────────────────────────────────
def run_sessbrk(o, h, l, c, mins, day_id, rng_lo, rng_hi, trd_hi, stop_mode):
    """rng window [rng_lo, rng_hi) minutes-of-day ET; trade window [rng_hi, trd_hi).
    Sessions on the ETH tape are keyed by the 18:00 rollover day_id already in the
    master; we instead walk calendar structure directly off minutes-of-day."""
    n = len(c)
    pnl = []
    i = 0
    # walk contiguous blocks where mins is inside [rng_lo, trd_hi) handling midnight wrap
    def in_win(mn, lo, hi):
        return (lo <= mn < hi) if lo < hi else (mn >= lo or mn < hi)
    k = 0
    while k < n:
        # find start of a range window
        if not in_win(mins[k], rng_lo, rng_hi):
            k += 1; continue
        j = k
        while j < n and in_win(mins[j], rng_lo, rng_hi):
            j += 1
        if j >= n or j - k < 30:
            k = j; continue
        hi_lvl = h[k:j].max() + 0.25
        lo_lvl = l[k:j].min() - 0.25
        rng = hi_lvl - lo_lvl
        # trade window follows immediately
        t0 = j
        t1 = t0
        while t1 < n and in_win(mins[t1], rng_hi, trd_hi):
            t1 += 1
        if t1 - t0 < 10:
            k = j; continue
        side = 0
        for q in range(t0, t1):
            hit_up = h[q] >= hi_lvl; hit_dn = l[q] <= lo_lvl
            if hit_up and hit_dn:
                side = 0; break
            if hit_up:
                side, entry_px, entry_k = +1, max(o[q], hi_lvl), q; break
            if hit_dn:
                side, entry_px, entry_k = -1, min(o[q], lo_lvl), q; break
        if side != 0:
            stop = (lo_lvl if side > 0 else hi_lvl) if stop_mode == "opp" \
                else entry_px - side * 0.5 * rng
            exit_px = None
            for q in range(entry_k + 1, t1):
                if side > 0 and l[q] <= stop:
                    exit_px = o[q] if o[q] < stop else stop; break
                if side < 0 and h[q] >= stop:
                    exit_px = o[q] if o[q] > stop else stop; break
            if exit_px is None:
                exit_px = c[t1 - 1]
            pnl.append((side * (exit_px - entry_px) - NQ_ETH_RT) * NQ_MULT)
        k = t1 if t1 > j else j
    return pnl


# ── PAIRS ES/NQ ──────────────────────────────────────────────────────────────
def run_pairs(nq, es, z_in, win):
    """align on shared timestamps; spread = log(NQ) - log(ES); z over `win` bars.
    Close-confirmed |z|>=z_in -> next shared bar open, 1 contract each leg, exit when
    z crosses 0 or after 10 sessions. Both legs pay costs."""
    tnq = nq["index"].astype("int64"); tes = es["index"].astype("int64")
    common, ia, ib = np.intersect1d(tnq, tes, return_indices=True)
    cn, ce = nq["close"][ia], es["close"][ib]
    on_, oe = nq["open"][ia], es["open"][ib]
    dn = nq["day_id"][ia]
    sp = np.log(cn) - np.log(ce)
    n = len(sp)
    pnl = []
    pos = 0
    for k in range(win, n - 1):
        if pos == 0:
            mu = sp[k - win:k].mean(); sd = sp[k - win:k].std()
            if sd <= 0:
                continue
            z = (sp[k] - mu) / sd
            if abs(z) >= z_in:
                pos = -1 if z > 0 else +1     # rich NQ vs ES -> short NQ / long ES
                e_nq, e_es = on_[k + 1], oe[k + 1]
                e_day = dn[k + 1]; mu0, sd0 = mu, sd
        else:
            z = (sp[k] - mu0) / sd0
            done = (pos > 0 and z >= 0) or (pos < 0 and z <= 0) or (dn[k] - e_day >= 10)
            if done:
                x_nq, x_es = on_[k + 1], oe[k + 1]
                gross = pos * (x_nq - e_nq) * NQ_MULT - pos * (x_es - e_es) * ES_MULT
                cost = NQ_RT * NQ_MULT + ES_RT * ES_MULT
                pnl.append(gross - cost)
                pos = 0
    return pnl


def main():
    print("loading masters...")
    m5 = find_master("NQ", "5m", "rth", "db_noadj_rth") or find_master("NQ", "5m", "rth", None)
    nq5 = load_master_arrays(m5, date_from=None, date_to=DATE_TO)
    o, h, l, c = nq5["open"], nq5["high"], nq5["low"], nq5["close"]
    did = nq5["day_id"]; sess = _sessions(did)
    print("NQ 5m RTH bars:", len(c), "sessions:", len(sess))

    # B0 drift baseline: always-long, enter each session open, exit close, costed.
    do, dh, dl, dc = _daily(o, h, l, c, sess)
    _score((dc - do - NQ_RT) * NQ_MULT, "B0", "always-long RTH", "drift yardstick")

    for sf in (0.5, 1.0):
        for ex in ("close", "pc"):
            _score(run_oops(o, h, l, c, sess, sf, ex), "OOPS", f"stop{sf}xATR/{ex}")
    for cond in ("nr7", "nr4", "inside"):
        for ex in ("close", "2R"):
            _score(run_nrx(o, h, l, c, sess, cond, ex), "NR7", f"{cond}/{ex}")
    for mode in ("fade", "brk"):
        for sf in (0.5, 1.0):
            _score(run_pivot(o, h, l, c, sess, mode, sf), "PIVOT", f"{mode}/stop{sf}")
    for ebar in (12, 6):                       # 12 bars=60min, 6=30min before close
        for mode in ("mom", "fade"):
            for thr in (0.0, 0.3):
                _score(run_moc(o, h, l, c, sess, ebar, mode, thr),
                       "MOC", f"{'60m' if ebar == 12 else '30m'}/{mode}/thr{thr}")

    m1e = find_master("NQ", "1m", "eth", None)
    if m1e is not None:
        nq1 = load_master_arrays(m1e, date_from=None, date_to=DATE_TO)
        idx = nq1["index"]
        mins = (idx.hour * 60 + idx.minute).astype("int64") if hasattr(idx, "hour") \
            else np.array([t.hour * 60 + t.minute for t in idx], dtype="int64")
        for (rl, rh, th, tag) in ((1080, 180, 570, "asia"), (180, 510, 960, "london")):
            for sm in ("opp", "half"):
                _score(run_sessbrk(nq1["open"], nq1["high"], nq1["low"], nq1["close"],
                                   mins, nq1["day_id"], rl, rh, th, sm),
                       "SESSBRK", f"{tag}/{sm}",
                       "NQ 1m ETH, 0.783 costs")
    else:
        print("!! no NQ 1m ETH master found — SESSBRK skipped")

    mes = find_master("ES", "5m", "rth", "db_noadj_rth") or find_master("ES", "5m", "rth", None)
    if mes is not None:
        es5 = load_master_arrays(mes, date_from=None, date_to=DATE_TO)
        for z in (2.0, 2.5):
            for w in (390, 1170):
                _score(run_pairs(nq5, es5, z, w), "PAIRS", f"z{z}/w{w}",
                       "both legs costed $28.81/RT")
    else:
        print("!! no ES 5m master — PAIRS skipped")

    print()
    print(f"{'concept':8} {'cell':22} {'n':>6} {'net$':>12} {'PF':>6} {'DD$':>10} {'MAR':>7}  gates")
    for r in RESULTS:
        g = "PASS" if (r["pf"] >= 1.25 and r["mar"] >= 8 and r["n"] >= 300) else "fail"
        print(f"{r['concept']:8} {r['cell']:22} {r['n']:>6} {r['net']:>12,.0f} "
              f"{r['pf']:>6.3f} {r['dd']:>10,.0f} {r['mar']:>7.2f}  {g}")

    outdir = os.path.join(ROOT, "tools", "r16_results")
    os.makedirs(outdir, exist_ok=True)
    with open(os.path.join(outdir, "r16_triage.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(RESULTS[0].keys()))
        w.writeheader(); w.writerows(RESULTS)
    print("\nsaved tools/r16_results/r16_triage.csv")


if __name__ == "__main__":
    main()
