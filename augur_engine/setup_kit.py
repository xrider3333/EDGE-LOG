"""augur_engine/setup_kit.py -- shared machinery for SETUPS round 1 (SETUPS_PREREG.md).

One session engine, one level engine, one trade walk, one short-mirror helper, used by
augur_strategies/CBUQ_1M_1_0.py, CBDQ_1M_1_0.py, EBUQ_1M_1_0.py, ENGU_2_0.py and
ENGU_2_0_D.py -- so the long/short trade mechanics (SETUPS_PREREG.md section 3) cannot
drift between the five files. The rule-specific tests (section 4) live in each file;
everything else -- sessions, ATR14, the RTH/premarket/prior-day levels, roll days, the
per-bar volume baseline, the decision-bar mask, the risk check and the exit walk -- lives
here exactly once.

Works on any bar size: bar length in minutes is derived from the median timestamp gap
(wave 2, SETUPS_PREREG.md section 8, runs this on 5-minute bars unchanged).

SPEED. `prep()` does ONE Python loop over sessions (a few thousand for a 15-year 1-minute
tape), each iteration a handful of vectorised numpy calls over that session's own bars --
never a per-bar Python loop over the whole tape. The result is cached in-process (module
cache, <= 2 entries) keyed by a cheap fingerprint of the frame (+ side, so a long run and
its mirrored short run never collide). Knob-dependent rolling arrays (brk_n, eng_n,
base_bars, trail_bars) are cached per (frame, knob value) in a small LRU so a knob sweep
over the same frame does not recompute them every trial. The per-session signal search in
`run()` only visits sessions that have at least one rule-passing bar, and the trade walk
itself (`walk_trade`) is vectorised with numpy over that one session's <= 390 bars, not a
bar-by-bar Python loop.
"""
from collections import deque

import numpy as np
import pandas as pd

RTH_START_MIN = 570          # 09:30 ET, in minutes-since-midnight
RTH_END_MIN = 960            # 16:00 ET (exclusive) -- last RTH bar's own minute is 959
PM_START_MIN = 240           # 04:00 ET -- premarket window is [240, 570)
_ATR_LEN = 14
_VOL_BASE_LOOKBACK = 10
_VOL_FIRSTBAR_SESSIONS = 20

# ─────────────────────────────────────────────────────────────────────────────
# module-level caches
# ─────────────────────────────────────────────────────────────────────────────
_PREP_CACHE_MAX = 2
_PREP_CACHE = []             # [(fp, P), ...] index 0 = least recently used

_ROLL_CACHE = {}
_ROLL_ORDER = []
_ROLL_MAX = 8            # ~40 MB per full-history 1m array; validate runs 3 fold processes


def _prep_cache_get(fp):
    for j, (k, v) in enumerate(_PREP_CACHE):
        if k == fp:
            _PREP_CACHE.append(_PREP_CACHE.pop(j))
            return v
    return None


def _prep_cache_put(fp, value):
    _PREP_CACHE.append((fp, value))
    del _PREP_CACHE[:-_PREP_CACHE_MAX]
    return value


def _roll_cached(key, fn):
    if key in _ROLL_CACHE:
        try:
            _ROLL_ORDER.remove(key)
        except ValueError:
            pass
        _ROLL_ORDER.append(key)
        return _ROLL_CACHE[key]
    val = fn()
    val.setflags(write=False)
    _ROLL_CACHE[key] = val
    _ROLL_ORDER.append(key)
    if len(_ROLL_ORDER) > _ROLL_MAX:
        old = _ROLL_ORDER.pop(0)
        _ROLL_CACHE.pop(old, None)
    return val


def fingerprint(o, h, l, c, side=1):
    """(n, first ts, last ts, a few prices, a strided sum of closes, side). Cheap and
    collision-resistant enough to key the prep()/rolling-array caches; `side` keeps a
    long run and its inverted-array short mirror from ever sharing an entry."""
    c = np.asarray(c, float)
    n = len(c)
    stride = max(1, n // 997)
    s = float(np.sum(c[::stride]))
    return (n, float(c[0]), float(c[n // 2]), float(c[-1]), s, int(side))


# ─────────────────────────────────────────────────────────────────────────────
# sessions (ENGUQ_1M_ETH_SEL._sessions idiom: 18:00 ET roll)
# ─────────────────────────────────────────────────────────────────────────────
def sessions(index):
    """(sess, minute, starts, ends, barlen_min). `sess` is a 0-based, contiguous session
    id per bar, rolling at 18:00 ET. `minute` is ET minute-of-day. `barlen_min` is the bar
    length in minutes, from the median timestamp gap (works for 1m and 5m tapes alike)."""
    ix = pd.DatetimeIndex(index)
    n = len(ix)
    if n == 0:
        raise ValueError("setup_kit.sessions: empty index")
    sh = ix + pd.Timedelta(hours=6)
    if sh.tz is not None:
        sh = sh.tz_localize(None)
    sess = pd.factorize(sh.normalize().asi8)[0].astype(np.int64)
    minute = (np.asarray(ix.hour, np.int64) * 60 + np.asarray(ix.minute, np.int64))
    starts = np.flatnonzero(np.r_[True, sess[1:] != sess[:-1]])
    ends = np.r_[starts[1:], n]
    if len(starts) != int(sess.max()) + 1:
        raise ValueError("setup_kit.sessions: session keys are not contiguous (index not sorted?)")
    if n >= 2:
        diffs = np.diff(ix.asi8).astype(np.float64)
        barlen = int(round(float(np.median(diffs)) / 6.0e10))   # ns -> minutes
    else:
        barlen = 1
    return sess, minute, starts, ends, max(1, barlen)


# ─────────────────────────────────────────────────────────────────────────────
# contract switches (roll days). The no-adj 24-hour masters switch contracts at 00:00 UTC
# (19:00 or 20:00 ET) on the vendor's roll day -- mostly INSIDE an 18:00 session, not at a
# session boundary (ES sometimes at the Sunday 18:00 reopen). The house detect_roll_seams (session open vs prior session close, used by
# AOSTOCH/TTIBS on RTH day bars) therefore misses them on this tape: 3 of 61 NQ rolls and 1
# of 61 ES rolls 2010-2025, while blanking ~20 ordinary Monday news gaps instead (independent
# verification 2026-09-25; SETUPS_PREREG.md section 10). Replaced before any triage result.
# ─────────────────────────────────────────────────────────────────────────────
def _third_weekday(year, month, weekday=2):
    d0 = pd.Timestamp(year=year, month=month, day=1)
    offset = (weekday - d0.weekday()) % 7
    first = d0 + pd.Timedelta(days=offset)
    return first + pd.Timedelta(weeks=2)


def contract_switch_sessions(o, c, index, sess, pre_days=14, post_days=4):
    """Set of session ids that hold a contract switch. Per quarterly window (third Wednesday
    of Mar/Jun/Sep/Dec, minus pre_days .. plus post_days), the bar stamped 00:00 UTC or
    opening a session with the largest |open - prior bar close| is the switch; its session's prior-day level comes from
    the OLD contract (100-300 NQ points off in 2022-25) and is blanked by prep().
    Look-ahead note: taking the largest jump in the window reads up to post_days ahead, but
    it only decides which ONE session per quarter loses its prior-day level (a live trader
    always sees the new contract's own prior-day levels), never a price or a signal."""
    ix = pd.DatetimeIndex(index)
    if ix.tz is None:
        ix = ix.tz_localize("US/Eastern")
    utc = ix.tz_convert("UTC")
    at0 = np.flatnonzero((np.asarray(utc.hour) == 0) & (np.asarray(utc.minute) == 0))
    # ES sometimes switches at the Sunday 18:00 reopen instead (2022-12, 2023-06/09, 2024-06):
    # every session's first bar is a candidate too
    first = np.flatnonzero(np.r_[False, np.asarray(sess[1:]) != np.asarray(sess[:-1])])
    at0 = np.union1d(at0, first)
    at0 = at0[at0 > 0]
    if len(at0) == 0:
        return set()
    jump = np.abs(o[at0] - c[at0 - 1])
    wall = ix.tz_localize(None)
    t0 = wall[at0]
    out = set()
    for y in sorted(set(wall.year)):
        for m in (3, 6, 9, 12):
            wed3 = _third_weekday(y, m)
            sel = np.flatnonzero((t0 >= wed3 - pd.Timedelta(days=pre_days)) &
                                 (t0 <= wed3 + pd.Timedelta(days=post_days)))
            if len(sel) == 0:
                continue
            k = int(at0[sel[int(np.argmax(jump[sel]))]])
            out.add(int(sess[k]))
    return out


# ─────────────────────────────────────────────────────────────────────────────
# true range / ATR14 / volume baseline (global, vectorised once per frame)
# ─────────────────────────────────────────────────────────────────────────────
def _true_range(h, l, c):
    n = len(c)
    tr = np.empty(n)
    tr[0] = h[0] - l[0]
    if n > 1:
        prev_c = c[:-1]
        tr[1:] = np.maximum(h[1:] - l[1:], np.maximum(np.abs(h[1:] - prev_c), np.abs(l[1:] - prev_c)))
    return tr


# ─────────────────────────────────────────────────────────────────────────────
# prep(): the one per-session loop. Everything a rule test needs, computed once,
# cached (<= 2 frames) and reused across every knob combination on that frame.
# ─────────────────────────────────────────────────────────────────────────────
def prep(opens, highs, lows, closes, volumes, index, side=1):
    o = np.asarray(opens, float); h = np.asarray(highs, float)
    l = np.asarray(lows, float);  c = np.asarray(closes, float)
    n = len(c)
    if index is None or len(index) != n:
        raise ValueError("setup_kit.prep: index missing or wrong length (%s vs %d bars)" %
                         ("None" if index is None else len(index), n))
    v = None if volumes is None else np.asarray(volumes, float)

    # volumes presence is part of the key: a frame first seen without volumes must never
    # hand its all-NaN volume baseline to a later call that has them (silent no-trade)
    fp = fingerprint(o, h, l, c, side) + (v is not None,)
    hit = _prep_cache_get(fp)
    if hit is not None:
        return hit

    sess, minute, starts, ends, barlen = sessions(index)
    n_sess = len(starts)

    tr = _true_range(h, l, c)
    atr14 = pd.Series(tr).rolling(_ATR_LEN, min_periods=_ATR_LEN).mean().shift(1).to_numpy()
    if v is not None:
        vol_base = pd.Series(v).rolling(_VOL_BASE_LOOKBACK, min_periods=_VOL_BASE_LOOKBACK).mean().shift(1).to_numpy()
    else:
        vol_base = np.full(n, np.nan)

    rth_mask = (minute >= RTH_START_MIN) & (minute < RTH_END_MIN)
    rth_hi_before = np.full(n, np.nan)
    rth_lo_before = np.full(n, np.nan)
    premarket_hi = np.full(n, np.nan)
    premarket_lo = np.full(n, np.nan)
    priorday_hi = np.full(n, np.nan)
    priorday_lo = np.full(n, np.nan)
    is_first_rth = np.zeros(n, dtype=bool)
    is_last_rth = np.zeros(n, dtype=bool)
    last_rth_idx = np.full(n_sess, -1, dtype=np.int64)

    seam_sessions = contract_switch_sessions(o, c, index, sess)

    first_rth_vol_hist = deque(maxlen=_VOL_FIRSTBAR_SESSIONS)
    have_prior = False
    prior_hi = prior_lo = np.nan

    for s in range(n_sess):
        a, b = int(starts[s]), int(ends[s])
        m_s = minute[a:b]
        rloc = np.flatnonzero((m_s >= RTH_START_MIN) & (m_s < RTH_END_MIN))
        if len(rloc) == 0:
            continue                                  # no RTH bars this session -- skip; the
                                                        # prior-day pointer is simply not updated
        ridx = a + rloc
        h_r = h[ridx]; l_r = l[ridx]
        cmax = np.maximum.accumulate(h_r)
        cmin = np.minimum.accumulate(l_r)
        rth_hi_before[ridx] = np.r_[np.nan, cmax[:-1]]
        rth_lo_before[ridx] = np.r_[np.nan, cmin[:-1]]
        is_first_rth[ridx[0]] = True
        is_last_rth[ridx[-1]] = True
        last_rth_idx[s] = ridx[-1]

        pmloc = np.flatnonzero((m_s >= PM_START_MIN) & (m_s < RTH_START_MIN))
        if len(pmloc):
            pm_hi = float(h[a + pmloc].max()); pm_lo = float(l[a + pmloc].min())
        else:
            pm_hi = pm_lo = np.nan
        premarket_hi[ridx] = pm_hi
        premarket_lo[ridx] = pm_lo

        if have_prior and s not in seam_sessions:
            priorday_hi[ridx] = prior_hi
            priorday_lo[ridx] = prior_lo
        # else: stays NaN (no earlier RTH session yet, or a contract switch sits between)

        fidx = ridx[0]
        if v is not None:
            if len(first_rth_vol_hist) == _VOL_FIRSTBAR_SESSIONS:
                vol_base[fidx] = float(np.mean(first_rth_vol_hist))
            else:
                vol_base[fidx] = np.nan
            first_rth_vol_hist.append(float(v[fidx]))

        prior_hi = float(cmax[-1]); prior_lo = float(cmin[-1]); have_prior = True

    P = dict(fp=fp, n=n, barlen=barlen, sess=sess, minute=minute, starts=starts, ends=ends,
             rth_mask=rth_mask, atr14=atr14, vol_base=vol_base,
             rth_hi_before=rth_hi_before, rth_lo_before=rth_lo_before,
             premarket_hi=premarket_hi, premarket_lo=premarket_lo,
             priorday_hi=priorday_hi, priorday_lo=priorday_lo,
             is_first_rth=is_first_rth, is_last_rth=is_last_rth,
             last_rth_idx=last_rth_idx, seam_sessions=seam_sessions)
    for val in P.values():
        if isinstance(val, np.ndarray):
            val.setflags(write=False)
    return _prep_cache_put(fp, P)


# ─────────────────────────────────────────────────────────────────────────────
# knob-dependent rolling arrays (cached per (frame, knob value)). Built with
# numpy.lib.stride_tricks.sliding_window_view rather than pandas .rolling(): on a
# 15-year 1-minute tape (~5.1M bars) this is 2-13x faster (pandas' generic rolling
# median in particular: ~2.0s vs ~1.1s here for a 10-bar window; max/min: ~0.2-0.3s
# vs ~0.13s) with byte-identical output to pandas .rolling(w, min_periods=w).X().
# shift(1) -- verified bar-for-bar, including NaN placement, before this shipped.
# ─────────────────────────────────────────────────────────────────────────────
def _swv_before(arr, w, agg):
    """agg(window_array, axis=-1) over the w bars STRICTLY BEFORE each i (NaN for the
    first w bars) -- equivalent to pandas .rolling(w, min_periods=w).agg().shift(1)."""
    a = np.asarray(arr, float)
    n = len(a)
    out = np.full(n, np.nan)
    if w <= n and w >= 1:
        v = np.lib.stride_tricks.sliding_window_view(a, w)
        out[w:] = agg(v, axis=-1)[:-1]
    return out


def _arr_tag(arr):
    """Which array (not only which frame) a rolling cache entry was built from."""
    a = np.asarray(arr, float)
    n = len(a)
    return (float(a[0]), float(a[n // 3]), float(a[(2 * n) // 3]), float(a[-1])) if n else ()


def rolling_max_before(arr, n_bars, fp):
    n_bars = int(n_bars)
    return _roll_cached(('rmaxb', fp, _arr_tag(arr), n_bars), lambda: _swv_before(arr, n_bars, np.max))


def rolling_min_before(arr, n_bars, fp):
    n_bars = int(n_bars)
    return _roll_cached(('rminb', fp, _arr_tag(arr), n_bars), lambda: _swv_before(arr, n_bars, np.min))


def rolling_median_abs_body_before(o, c, n_bars, fp):
    n_bars = int(n_bars)

    def _compute():
        body = np.abs(np.asarray(c, float) - np.asarray(o, float))
        return _swv_before(body, n_bars, np.median)
    return _roll_cached(('rmedbody', fp, n_bars), _compute)


def rolling_min_incl(arr, n_bars, fp):
    """Lowest value of the n_bars bars ENDING AT (and including) each bar -- the trail
    exit's own window, not a "before i" lookback. Matches pandas
    .rolling(n_bars, min_periods=1).min() exactly, including the short-window ramp-up
    at the start of the tape."""
    n_bars = int(n_bars)

    def _compute():
        a = np.asarray(arr, float)
        n = len(a)
        w = int(n_bars)
        if w >= n:
            return np.minimum.accumulate(a)
        out = np.empty(n)
        v = np.lib.stride_tricks.sliding_window_view(a, w)
        out[w - 1:] = v.min(axis=-1)
        if w > 1:
            out[:w - 1] = np.minimum.accumulate(a[:w - 1])
        return out
    return _roll_cached(('rminincl', fp, _arr_tag(arr), n_bars), _compute)


def base_ok(h, l, atr14, base_bars, base_k, fp):
    """SETUPS_PREREG.md section 4A/B base test, or None when base_bars<=0 (off)."""
    if base_bars <= 0:
        return None
    hi = rolling_max_before(h, base_bars, fp)
    lo = rolling_min_before(l, base_bars, fp)
    with np.errstate(invalid="ignore"):
        return np.isfinite(hi) & np.isfinite(lo) & ((hi - lo) <= base_k * atr14)


def volume_ok(vol_base, v, vol_mult):
    """SETUPS_PREREG.md section 3 volume test, or None when vol_mult<=0 (off). Caller is
    responsible for raising when vol_mult>0 and v is None -- this never runs silently
    inert; it is only called after that check."""
    if vol_mult <= 0:
        return None
    with np.errstate(invalid="ignore"):
        return np.isfinite(vol_base) & (v >= vol_mult * vol_base)


# ─────────────────────────────────────────────────────────────────────────────
# decision-bar mask (shared: RTH window, end_min, first_bar, "not the last RTH bar")
# ─────────────────────────────────────────────────────────────────────────────
def decision_mask(P, end_min, first_bar='allow'):
    """Bars eligible as a DECISION bar i: in the RTH window, bar i itself closes no later
    than end_min minutes after 09:30 (section 4A), neither i nor i+1 is the session's last RTH bar
    (SETUPS_PREREG.md section 3), and, if first_bar=='skip',
    i is not the session's first RTH bar."""
    minute = P['minute']; rth = P['rth_mask']; barlen = P['barlen']
    close_from_open = (minute - RTH_START_MIN) + barlen        # minutes 09:30 -> this bar's CLOSE
    # the ENTRY bar i+1 must not be the session's last RTH bar either (latest entry 15:58 on
    # 1-minute bars; matters on early-close days and for end_min near the close)
    next_is_last = np.r_[P['is_last_rth'][1:], False]
    m = rth & (close_from_open <= end_min) & (~P['is_last_rth']) & (~next_is_last)
    if first_bar == 'skip':
        m = m & (~P['is_first_rth'])
    return m


# ─────────────────────────────────────────────────────────────────────────────
# the trade walk (SETUPS_PREREG.md section 3, exact mechanics). Long only; short is
# done by inversion (mirror_short below). Vectorised with numpy over this one session's
# bars -- no per-bar Python loop.
# ─────────────────────────────────────────────────────────────────────────────
def walk_trade(o, h, l, c, k0, entry, stop, risk, exit_mode, be_R, trail_bars, target_R,
               kend, lo_roll_trail=None):
    """One trade, long side. Returns (exit_bar, pnl_pts). k0 is the entry bar (fill at
    o[k0]); kend is the session's last RTH bar (flat-at-close fallback)."""
    idx = np.arange(k0, kend + 1)
    oo = o[idx]; hh = h[idx]; ll = l[idx]; cc = c[idx]
    n = len(idx)

    if exit_mode == 'target':
        target = entry + target_R * risk
        stop_hit = (oo <= stop) | (ll <= stop)
        targ_hit = hh >= target
        sh = int(np.argmax(stop_hit)) if stop_hit.any() else n
        th = int(np.argmax(targ_hit)) if targ_hit.any() else n
        if sh <= th and sh < n:
            fill = oo[sh] if oo[sh] <= stop else stop
            return int(idx[sh]), float(fill - entry)
        if th < n:
            return int(idx[th]), float(target - entry)     # capped at target, even on a gap
        return int(idx[-1]), float(cc[-1] - entry)

    # ride / trail share the pre-breakeven stop search and the arming search
    arm_level = entry + be_R * risk
    stop_hit_unarmed = (oo <= stop) | (ll <= stop)
    arm_hit = cc >= arm_level
    su = int(np.argmax(stop_hit_unarmed)) if stop_hit_unarmed.any() else n
    ab = int(np.argmax(arm_hit)) if arm_hit.any() else n

    if su <= ab:
        if su < n:
            fill = oo[su] if oo[su] <= stop else stop
            return int(idx[su]), float(fill - entry)
        return int(idx[-1]), float(cc[-1] - entry)

    # armed at local index `ab` (bar idx[ab]'s CLOSE); the new floor applies from ab+1
    if ab + 1 >= n:
        return int(idx[-1]), float(cc[-1] - entry)

    if exit_mode == 'ride':
        arm_stop = entry
        seg_o = oo[ab + 1:]; seg_l = ll[ab + 1:]
        hit2 = (seg_o <= arm_stop) | (seg_l <= arm_stop)
        if hit2.any():
            t2 = ab + 1 + int(np.argmax(hit2))
            fill = oo[t2] if oo[t2] <= arm_stop else arm_stop
            return int(idx[t2]), float(fill - entry)
        return int(idx[-1]), float(cc[-1] - entry)

    # trail: once armed, after each bar close stop = max(stop, entry, lowest low of the
    # trail_bars bars ending at that bar) for the NEXT bar -- a running max from arm_bar.
    if lo_roll_trail is None:
        raise ValueError("setup_kit.walk_trade: exit_mode='trail' needs lo_roll_trail")
    M = lo_roll_trail[idx[ab]: idx[-1] + 1]           # M[j] for bar idx[ab+j], j=0..n-ab-1
    cm = np.maximum.accumulate(np.maximum(M, entry))  # cm[j] = floor applicable AFTER bar idx[ab+j]
    stop_seg = cm[: n - ab - 1]                        # floor for bars idx[ab+1 .. n-1]
    seg_o = oo[ab + 1:]; seg_l = ll[ab + 1:]
    hit2 = (seg_o <= stop_seg) | (seg_l <= stop_seg)
    if hit2.any():
        k = int(np.argmax(hit2))
        t2 = ab + 1 + k
        slvl = float(stop_seg[k])
        fill = oo[t2] if oo[t2] <= slvl else slvl
        return int(idx[t2]), float(fill - entry)
    return int(idx[-1]), float(cc[-1] - entry)


def run(o, h, l, c, P, candidate_mask, exit_mode, be_R, trail_bars, target_R,
       stop_buf_atr, min_risk_atr):
    """Session scan + risk check + walk. One trade per session: the FIRST candidate bar
    whose risk check ALSO passes (a candidate that only fails the risk check does not use
    up the session -- SETUPS_PREREG.md section 3/6 clarification, deviations log).
    Returns a list of (fill_bar, exit_bar, pnl_pts, entry_px) 4-tuples (side is added by
    the caller: 1 for the long files, or via mirror_short for the short ones)."""
    atr14 = P['atr14']; sess = P['sess']; last_rth_idx = P['last_rth_idx']
    n = len(c)
    lo_roll_trail = rolling_min_incl(l, trail_bars, P['fp']) if exit_mode == 'trail' else None

    cand_idx_all = np.flatnonzero(candidate_mask)
    trades = []
    if len(cand_idx_all) == 0:
        return trades
    cand_sess = sess[cand_idx_all]
    boundaries = np.flatnonzero(np.r_[True, cand_sess[1:] != cand_sess[:-1]])
    seg_ends = np.r_[boundaries[1:], len(cand_idx_all)]

    for a, b in zip(boundaries, seg_ends):
        for j in range(a, b):
            i = int(cand_idx_all[j])
            k0 = i + 1
            if k0 >= n:
                continue
            a_atr = atr14[i]
            if (stop_buf_atr > 0 or min_risk_atr > 0) and not np.isfinite(a_atr):
                continue
            buf = stop_buf_atr * a_atr if stop_buf_atr > 0 else 0.0
            stop = l[i] - buf
            entry = o[k0]
            risk = entry - stop
            floor = min_risk_atr * a_atr if min_risk_atr > 0 else 0.0
            if not (risk > max(0.0, floor)):
                continue                                  # risk check fails -- try the NEXT
                                                            # candidate bar in this session
            s = int(sess[i])
            kend = int(last_rth_idx[s])
            if kend < k0:
                continue
            exit_bar, pnl = walk_trade(o, h, l, c, k0, entry, stop, risk, exit_mode, be_R,
                                       trail_bars, target_R, kend, lo_roll_trail=lo_roll_trail)
            trades.append((k0, exit_bar, float(pnl), float(entry)))
            break                                          # one trade per session
    return trades


def mirror_short(long_fn, opens, highs, lows, closes, volumes, index, **kwargs):
    """Runs `long_fn` (a file's own long-side core, returning 4-tuples (fill, exit, pnl,
    entry) same as run()'s output) on (o,h,l,c) -> (-o,-l,-h,-c). Volume is unchanged.
    The long walk's points P&L on the inverted tape IS the real short P&L already
    (exit2-entry2 = (-real_exit)-(-real_entry) = real_entry-real_exit), so only the entry
    price needs to flip back to positive and side is tagged -1."""
    o = np.asarray(opens, float); h = np.asarray(highs, float)
    l = np.asarray(lows, float);  c = np.asarray(closes, float)
    o2, h2, l2, c2 = -o, -l, -h, -c
    trades = long_fn(o2, h2, l2, c2, volumes, index, **kwargs)
    return [(fb, xb, pnl, -1, -entry) for (fb, xb, pnl, entry) in trades]


# ─────────────────────────────────────────────────────────────────────────────
# stats (house template, GROSS points -- cost_pts is applied by the ENGINE from the
# trade list, never by a strategy file)
# ─────────────────────────────────────────────────────────────────────────────
def stats(trades, return_trades=False):
    if not trades:
        return None
    p = np.array([t[2] for t in trades], dtype=float)
    wins = p[p > 0]; losses = p[p < 0]
    cum = np.cumsum(p)
    out = {
        "total_pnl":     round(float(p.sum()), 2),
        "num_trades":    int(len(p)),
        "win_rate":      round(len(wins) / len(p) * 100, 1),
        "profit_factor": round(float(wins.sum()) / max(abs(float(losses.sum())), 1e-9), 2),
        "max_drawdown":  round(float((cum - np.maximum.accumulate(cum)).min()), 2),
        "avg_pnl":       round(float(p.mean()), 2),
        "wins":          int(len(wins)), "losses": int(len(losses)),
    }
    if return_trades:
        out["trades"] = trades
    return out
