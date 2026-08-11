"""Can a PRE-KNOWN filter recover what the illegal volume filter faked? (ORB.md salvage brief)

The fill at the level is legal and it carried the money. What was illegal was gating it on
the SAME bar's volume. So: sweep filters whose value exists strictly BEFORE the touch, and
measure them against the honest no-filter baseline -- never against the leaked figure.

Every feature here is computed from bars that close BEFORE the entry bar. The entry bar
itself is excluded from every input, which is the whole point.

    1 or_pct      today's opening-range width vs the last N sessions' OR widths
    2 gap         |session open - prior session close| in prior-ATR units, known at 09:30
    3 prange      prior session's high-low range vs the trailing median
    4 noise_sig   NOISE-style prior-14-day sigma for THIS bar-of-day slot
    5 vpace       mean volume of the session's bars BEFORE the entry bar vs its own
                  trailing-20-session norm  (legal: the fill bar is excluded)

Baseline = touch entry, vol_filter OFF, everything else at #125. Costs 0.533 pts/RT.
Lockbox = the last 365 days, held out; a filter must beat baseline in BOTH windows.

Run:  python3.13.exe tools/orb_prelegal_filters.py
"""
import sys
import pathlib
import importlib.util as _I

import numpy as np

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
from augur_engine import data as D  # noqa: E402

COST = 0.533          # pts per round trip, NQ
MULT = 20             # $ per point
LOCKBOX_DAYS = 365


def _load_orb():
    sp = _I.spec_from_file_location("orb31", REPO / "augur_strategies" / "ORB_3_1.py")
    m = _I.module_from_spec(sp)
    sp.loader.exec_module(m)
    return m


def _stats(pnl_pts):
    """net $ after costs, PF, max drawdown $, MAR, n -- on a points array."""
    n = len(pnl_pts)
    if not n:
        return dict(n=0, net=0.0, pf=0.0, dd=0.0, mar=0.0)
    net_pts = pnl_pts.sum() - n * COST
    after = pnl_pts - COST
    eq = np.cumsum(after)
    dd = float(np.min(eq - np.maximum.accumulate(eq))) or -1e-9
    gw = after[after > 0].sum()
    gl = -after[after < 0].sum()
    return dict(n=n, net=float(net_pts) * MULT, pf=float(gw / gl) if gl > 1e-9 else 99.0,
                dd=abs(float(dd)) * MULT, mar=float(net_pts / abs(dd)) if abs(dd) > 1e-9 else 0.0)


def main():
    orb = _load_orb()
    mm = [x for x in D.list_masters()
          if x.get("instrument") == "NQ" and x.get("timeframe") == "5m"
          and x.get("source") == "db_noadj_rth"][0]
    a = D.load_master_arrays(mm)
    o, h, l, c, v, day = (a["open"], a["high"], a["low"], a["close"], a["volume"], a["day_id"])
    nb = len(o)

    # session index -> [start, end) bar range, in chronological order
    bounds, starts = [], np.flatnonzero(np.diff(day) != 0) + 1
    edges = np.concatenate(([0], starts, [nb]))
    for i in range(len(edges) - 1):
        bounds.append((int(edges[i]), int(edges[i + 1])))
    nsess = len(bounds)
    sess_of = np.zeros(nb, dtype=int)
    for si, (s, e) in enumerate(bounds):
        sess_of[s:e] = si

    # ── PRE-KNOWN per-session features ────────────────────────────────────────────────
    or_w = np.array([h[s] - l[s] for s, e in bounds])                      # OR bar width
    s_open = np.array([o[s] for s, e in bounds])
    s_hi = np.array([h[s:e].max() for s, e in bounds])
    s_lo = np.array([l[s:e].min() for s, e in bounds])
    s_close = np.array([c[e - 1] for s, e in bounds])
    s_rng = s_hi - s_lo

    def _trail_pct(arr, win):
        """percentile of arr[i] within the PRIOR `win` values (0..1); nan for warm-up."""
        out = np.full(len(arr), np.nan)
        for i in range(win, len(arr)):
            w = arr[i - win:i]
            out[i] = (w < arr[i]).mean()
        return out

    f_or_pct = _trail_pct(or_w, 20)                                        # 1
    prior_rng = np.concatenate(([np.nan], s_rng[:-1]))
    prior_atr = np.full(nsess, np.nan)
    for i in range(20, nsess):
        prior_atr[i] = np.nanmean(s_rng[i - 20:i])
    f_gap = np.abs(s_open - np.concatenate(([np.nan], s_close[:-1]))) / prior_atr   # 2
    f_prange = _trail_pct(prior_rng, 20)                                   # 3

    # 4 NOISE-style: prior-14-session sigma of |log return| for each bar-of-day slot
    slot = np.zeros(nb, dtype=int)
    for s, e in bounds:
        slot[s:e] = np.arange(e - s)
    nslot = int(slot.max()) + 1
    ret = np.zeros(nb)
    ret[1:] = np.abs(np.diff(c)) / np.maximum(c[:-1], 1e-9)
    sig = np.full((nsess, nslot), np.nan)
    for si, (s, e) in enumerate(bounds):
        for k in range(e - s):
            sig[si, k] = ret[s + k]
    f_noise = np.full((nsess, nslot), np.nan)
    for si in range(14, nsess):
        w = sig[si - 14:si, :]
        f_noise[si, :] = np.nanmean(w, axis=0)          # typical move size for this slot

    # ── the honest baseline: touch entry, NO volume filter ────────────────────────────
    base_kw = dict(or_bars=1, trade_mode="Both", stop_frac=0.75, breakout_buf=0.0,
                   partial_exit_R=0.0, trail_bars=5, target_R=0.0, flat_eod=True,
                   skip_holidays=False, close_confirm=False)
    r = orb.run_backtest(o, h, l, c, volumes=v, day_id=day, vol_filter=0.0,
                         atr_filter=0.0, return_trades=True, **base_kw)
    tr = r["trades"]
    ek = np.array([t[0] for t in tr], dtype=int)          # global entry bar
    pnl = np.array([float(t[2]) for t in tr])
    tsess = sess_of[ek]
    tslot = slot[ek]
    lb_start = nsess - int(LOCKBOX_DAYS * nsess / max(1, (nsess)))  # placeholder, set below

    # lockbox = last 365 calendar days -> last N sessions (~252)
    lb_sessions = 252
    is_mask = tsess < (nsess - lb_sessions)
    lb_mask = ~is_mask

    def show(tag, keep):
        w = _stats(pnl[keep & is_mask])
        x = _stats(pnl[keep & lb_mask])
        print(f"{tag:<28} IS  n{w['n']:>5} net ${w['net']:>9,.0f} PF {w['pf']:>5.3f} "
              f"DD ${w['dd']:>8,.0f} MAR {w['mar']:>6.1f}   |   "
              f"LB n{x['n']:>4} net ${x['net']:>8,.0f} PF {x['pf']:>5.3f} MAR {x['mar']:>5.1f}")

    allkeep = np.ones(len(pnl), dtype=bool)
    print(f"sessions {nsess} · trades {len(pnl)} · lockbox = last {lb_sessions} sessions\n")
    print("=== BASELINE (no filter, touch entry) — the honest number to beat ===")
    show("baseline", allkeep)

    # ── ATR filter: the existing trailing-only knob, swept as the PRIMARY lever ───────
    print("\n=== 1. atr_filter (engine knob, trailing-only) ===")
    for af in (0.1, 0.2, 0.3, 0.5, 0.75, 1.0):
        rr = orb.run_backtest(o, h, l, c, volumes=v, day_id=day, vol_filter=0.0,
                              atr_filter=af, return_trades=True, **base_kw)
        t2 = rr["trades"]
        p2 = np.array([float(t[2]) for t in t2])
        s2 = sess_of[np.array([t[0] for t in t2], dtype=int)]
        m2 = s2 < (nsess - lb_sessions)
        w, x = _stats(p2[m2]), _stats(p2[~m2])
        print(f"{'atr_filter='+str(af):<28} IS  n{w['n']:>5} net ${w['net']:>9,.0f} PF {w['pf']:>5.3f} "
              f"DD ${w['dd']:>8,.0f} MAR {w['mar']:>6.1f}   |   "
              f"LB n{x['n']:>4} net ${x['net']:>8,.0f} PF {x['pf']:>5.3f} MAR {x['mar']:>5.1f}")

    # ── post-hoc session gates (exact: ORB takes ~1 trade/session) ────────────────────
    feats = [
        ("2. or_width pct >", f_or_pct[tsess], (0.3, 0.4, 0.5, 0.6, 0.7)),
        ("3. or_width pct <", -f_or_pct[tsess], (-0.7, -0.6, -0.5, -0.4, -0.3)),
        ("4. gap (ATRs) >", f_gap[tsess], (0.05, 0.1, 0.2, 0.3, 0.5)),
        ("5. gap (ATRs) <", -f_gap[tsess], (-0.5, -0.3, -0.2, -0.1)),
        ("6. prior-range pct >", f_prange[tsess], (0.3, 0.4, 0.5, 0.6)),
        ("7. prior-range pct <", -f_prange[tsess], (-0.7, -0.6, -0.5, -0.4)),
    ]
    for name, val, cuts in feats:
        print(f"\n=== {name} ===")
        for cut in cuts:
            keep = np.nan_to_num(val, nan=-np.inf) >= cut
            if keep.sum() < 200:
                continue
            show(f"  cut {abs(cut):.2f}", keep)

    # 8 NOISE slot-sigma: is this bar-of-day typically active?
    nz = np.array([f_noise[si, sl] if sl < nslot else np.nan for si, sl in zip(tsess, tslot)])
    nz_pct = np.full(len(nz), np.nan)
    ok = ~np.isnan(nz)
    for i in np.flatnonzero(ok):
        row = f_noise[tsess[i], :]
        row = row[~np.isnan(row)]
        if len(row):
            nz_pct[i] = (row < nz[i]).mean()
    print("\n=== 8. NOISE slot-sigma percentile (prior 14 sessions, per bar-of-day) ===")
    for cut in (0.2, 0.3, 0.4, 0.5, 0.6, 0.7):
        keep = np.nan_to_num(nz_pct, nan=-1) >= cut
        if keep.sum() < 200:
            continue
        show(f"  slot-sigma >= {cut:.2f}", keep)
    print("\n=== 8b. NOISE slot-sigma percentile — QUIET slots only ===")
    for cut in (0.3, 0.4, 0.5, 0.6):
        keep = (np.nan_to_num(nz_pct, nan=2) <= cut)
        if keep.sum() < 200:
            continue
        show(f"  slot-sigma <= {cut:.2f}", keep)

    # 9 session volume pace BEFORE the fill bar vs its own trailing norm
    pace = np.full(len(pnl), np.nan)
    for i, (e, si) in enumerate(zip(ek, tsess)):
        s, _ = bounds[si]
        if e - s < 1:
            continue
        pre = v[s:e]                       # strictly BEFORE the fill bar
        if not len(pre):
            continue
        cur = pre.mean()
        hist = []
        for j in range(max(0, si - 20), si):
            s2, e2 = bounds[j]
            seg = v[s2:min(e2, s2 + (e - s))]
            if len(seg):
                hist.append(seg.mean())
        if hist:
            hm = float(np.mean(hist))
            if hm > 0:
                pace[i] = cur / hm
    print("\n=== 9. session volume pace before the fill bar (x its 20-session norm) ===")
    for cut in (0.8, 0.9, 1.0, 1.1, 1.25, 1.5):
        keep = np.nan_to_num(pace, nan=-1) >= cut
        if keep.sum() < 200:
            continue
        show(f"  pace >= {cut:.2f}x", keep)


if __name__ == "__main__":
    main()
