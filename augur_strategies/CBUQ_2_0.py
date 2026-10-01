"""CBU-Q 2.0 -- CBU rules v1, written from the owner's CBU history (SETUPS_PREREG_R3_CBU_V1.md section 2).

Pre-registered on main in 918059d5 before this file or any result for it existed; the outcome cells were
fixed in a later commit (section 4a) before the first run. Long only, one-minute bars, the decision is made
at the close of bar i:

  context   close above the 200 EMA of the 5-minute AND the 30-minute bars (24-hour series, the bar BEFORE
            the one holding bar i, 600 bars of warm-up - the point-score definition), and above yesterday's
            regular-session high (the latest earlier regular session that is not a listed holiday and ran to
            13:14 or later).
  level     close above the highest high of today's regular-session bars before i (a new high of the day);
            on the session's first regular bar (09:30), above the premarket (04:00-09:29) high instead.
  candle    green, range >= range_atr x ATR14, body >= body_atr x ATR14 (ATR14 = the mean true range of the
            14 bars before i; setup_kit's).
  volume    >= vol_mult x the mean volume of the 10 bars before i.
  base      any  - no base requirement;
            held - the highest high of the 30 bars before i was set (its earliest bar) at least 10 bars
                   before i, and that high minus the lowest low after it (to i-1) is <= 5 ATR14.
  window    am 09:30-10:59 or day 09:30-15:44 (the signal bar's start); never on a listed holiday, never
            when i or i+1 is the session's last regular bar.
  entry     the open of bar i+1; stop = low(i) - 1 tick; no trade when the open is at or below the stop.
            One position at a time (a new signal must close at or after the previous trade's exit bar) and
            at most 2 trades a session.
  exit      ride - the stop moves to breakeven after a bar CLOSES at +1 R (from the next bar), flat at the
                   session's last regular bar's close;
            be2r - the same, plus a 2 R target (filled at the target price, stop first within a bar).

P&L is in points per contract, gross (costs are applied by the engine / the triage driver). Everything that
does not depend on the knobs is built once per frame and cached.
"""


import numpy as np
import pandas as pd

from augur_engine import setup_kit as SK

STRATEGY_NAME = "CBU-Q 2.0"
DESCRIPTION = ("CBU rules v1, written from the owner's CBU journal: in an up day above the 5- and 30-minute "
               "200 EMA and yesterday's high, a big green one-minute candle on 1.5x volume closes at a new high "
               "of the day. Stop under the candle; breakeven at +1 R, then ride or take 2 R. "
               "Pre-registered in SETUPS_PREREG_R3_CBU_V1.md.")
VERSION = "2.0"
DIRECTION = "LONG"
TIMEFRAME = "1m"

_BASES = ("any", "held")
_WINDOWS = {"am": (9 * 60 + 30, 10 * 60 + 59), "day": (9 * 60 + 30, 15 * 60 + 44)}
_EXITS = ("ride", "be2r")
_TICK = 0.25                   # NQ and ES (and the micros)
_EMA_SPAN = 200
_EMA_WARM = 600                # point-score MIN_BARS: buckets of its own timeframe before the reference
_VOL_N = 10
_HELD_LOOK, _HELD_MIN, _BASE_MAX_ATR = 30, 10, 5.0
_REG_END_MIN = 13 * 60 + 14    # a regular session's last regular bar starts at 13:14 or later
_MAX_PER_SESSION = 2
_BE_R, _TARGET_R = 1.0, 2.0

DEFAULT_PARAMS = {
    'base': {'default': 'any', 'type': 'str', 'options': list(_BASES), 'label': 'Base',
             'tooltip': "any = a fresh new high of the day counts. held = the broken high must have held for "
                        "10+ minutes over a base no taller than 5 ATR."},
    'window': {'default': 'am', 'type': 'str', 'options': list(_WINDOWS), 'label': 'Time window',
               'tooltip': "am = signal candles 09:30-10:59. day = 09:30-15:44."},
    'exit_mode': {'default': 'ride', 'type': 'str', 'options': list(_EXITS), 'label': 'Management',
                  'tooltip': "ride = breakeven after a close at +1 R, then hold to the session close. "
                             "be2r = the same breakeven, plus a 2 R target."},
    'vol_mult': {'default': 1.5, 'min': 1.25, 'max': 2.0, 'step': 0.25, 'type': 'float',
                 'label': 'Volume (x 10-bar mean)',
                 'tooltip': "The signal candle's volume must be at least this many times the mean of the 10 "
                            "bars before it."},
    'range_atr': {'default': 1.2, 'min': 1.0, 'max': 1.4, 'step': 0.2, 'type': 'float',
                  'label': 'Candle range (x ATR14)',
                  'tooltip': "The signal candle's high-low range, in ATR14 of the 14 bars before it."},
    'body_atr': {'default': 0.7, 'min': 0.5, 'max': 0.9, 'step': 0.2, 'type': 'float',
                 'label': 'Candle body (x ATR14)',
                 'tooltip': "The signal candle's green body (close - open), in ATR14."},
}

# SETUPS_PREREG_R3_CBU_V1.md section 4 / 4a: triage = base x window x exit at the written thresholds (8 cells
# per root); the neighbours add vol_mult 1.25 / 2.0 and range_atr 1.0 / 1.4; the validate grid opens the three
# thresholds by one step each way. Auto-Validate searches DEFAULT_PARAMS (uniform steps), so its vol range also
# holds 1.75 (deviations log, 2026-10-01).
PARAM_GRID_PRESETS = {
    'Triage (pre-registered)': {
        'base': list(_BASES), 'window': list(_WINDOWS), 'exit_mode': list(_EXITS),
        'vol_mult': [1.5], 'range_atr': [1.2], 'body_atr': [0.7],
    },
    'Validate (pre-registered)': {
        'base': list(_BASES), 'window': list(_WINDOWS), 'exit_mode': list(_EXITS),
        'vol_mult': [1.25, 1.5, 2.0], 'range_atr': [1.0, 1.2, 1.4], 'body_atr': [0.5, 0.7, 0.9],
    },
}


# ─────────────────────────────────────────────────────────────────────────────
# holidays: a listed exchange holiday is never a regular session (calendar knowledge, known in advance)
# ─────────────────────────────────────────────────────────────────────────────
def _holiday_dates():
    """US equity-market full closures 2010-2027: the rule-based holidays (New Year, MLK, Presidents, Good Friday,
    Memorial, Juneteenth from 2022, Independence, Labor, Thanksgiving, Christmas, weekend-observed) plus the
    one-off closures. For 2025-27 this is the same set as the point score's CME full-holiday list (a test checks)."""
    from pandas.tseries.holiday import (AbstractHolidayCalendar, Holiday, nearest_workday, USMartinLutherKingJr,
                                        USPresidentsDay, GoodFriday, USMemorialDay, USLaborDay, USThanksgivingDay)

    class _Cal(AbstractHolidayCalendar):
        rules = [Holiday('NewYear', month=1, day=1, observance=nearest_workday), USMartinLutherKingJr,
                 USPresidentsDay, GoodFriday, USMemorialDay,
                 Holiday('Juneteenth', month=6, day=19, start_date='2022-01-01', observance=nearest_workday),
                 Holiday('July4', month=7, day=4, observance=nearest_workday), USLaborDay, USThanksgivingDay,
                 Holiday('Christmas', month=12, day=25, observance=nearest_workday)]

    d = set(str(x.date()) for x in _Cal().holidays('2010-01-01', '2027-12-31'))
    d -= {'2010-12-31', '2021-12-31', '2027-12-31'}     # NYSE does not observe a Saturday New Year on the Friday
    d |= {'2012-10-29', '2012-10-30', '2018-12-05', '2025-01-09'}   # Sandy, two national days of mourning
    return np.array(sorted(np.datetime64(x, 'D').astype('int64') for x in d), dtype='int64')


_HOLIDAY_ORD = None


def _holidays():
    global _HOLIDAY_ORD
    if _HOLIDAY_ORD is None:
        _HOLIDAY_ORD = _holiday_dates()
    return _HOLIDAY_ORD


# ─────────────────────────────────────────────────────────────────────────────
# per-frame features (knob-free), cached
# ─────────────────────────────────────────────────────────────────────────────
_FEAT_CACHE_MAX = 2
_FEAT_CACHE = []


def _clear_caches():
    """Test hook: forget this module's cached frames (and the kit's)."""
    del _FEAT_CACHE[:]
    del SK._PREP_CACHE[:]


def _wall_ns(index):
    ix = pd.DatetimeIndex(index)
    if ix.tz is not None:
        ix = ix.tz_convert('America/New_York').tz_localize(None)
    return ix.asi8


def _feat_key(P, v, index):
    n = len(v)
    stride = max(1, n // 997)
    w = _wall_ns(index)
    return (P['fp'], float(np.nansum(v[::stride])), float(v[n // 2]), int(w[0]), int(w[-1]))


def _ema_ref(c, wall, minutes):
    """The 200 EMA of the `minutes` bars (wall-clock ET buckets of the 24-hour series, over the buckets that exist)
    as of the bucket BEFORE the one holding each bar; NaN until that bucket is the 600th."""
    b = wall // (int(minutes) * 60_000_000_000)
    change = b[1:] != b[:-1]
    bucket_of_bar = np.cumsum(np.r_[0, change.astype(np.int64)])
    last_in_bucket = np.flatnonzero(np.r_[change, True])
    e = pd.Series(c[last_in_bucket]).ewm(span=_EMA_SPAN, adjust=False).mean().to_numpy()
    e[:_EMA_WARM - 1] = np.nan                          # the reference bucket needs 600 buckets of history
    prev = np.r_[np.nan, e[:-1]]
    return prev[bucket_of_bar]


def _yesterday_high(h, P, dord):
    """Per bar: the regular-session high of the latest EARLIER session that is a regular session (has regular
    bars, is not a listed holiday, and its last regular bar starts at 13:14 or later). NaN where none."""
    sess = P['sess']; minute = P['minute']
    n_sess = len(P['starts'])
    ridx = np.flatnonzero(P['rth_mask'])
    hi_s = np.full(n_sess, np.nan)
    date_s = np.full(n_sess, -1, dtype=np.int64)
    if len(ridx):
        rs = sess[ridx]
        b = np.flatnonzero(np.r_[True, rs[1:] != rs[:-1]])
        hi_s[rs[b]] = np.maximum.reduceat(h[ridx], b)
        date_s[rs[b]] = dord[ridx[b]]
    last = P['last_rth_idx']
    ok = (last >= 0) & (minute[np.maximum(last, 0)] >= _REG_END_MIN) & ~np.isin(date_s, _holidays())
    vs = np.flatnonzero(ok)
    p = np.searchsorted(vs, np.arange(n_sess), side='left') - 1
    y = np.where(p >= 0, hi_s[vs[np.maximum(p, 0)]], np.nan) if len(vs) else np.full(n_sess, np.nan)
    return y[sess]


def _features(o, h, l, c, v, index, P):
    key = _feat_key(P, v, index)
    for j, (k, F) in enumerate(_FEAT_CACHE):
        if k == key:
            _FEAT_CACHE.append(_FEAT_CACHE.pop(j))
            return F
    wall = _wall_ns(index)
    dord = (wall // 86_400_000_000_000).astype(np.int64)        # ET calendar date (days since 1970-01-01)
    minute = P['minute']
    ref5 = _ema_ref(c, wall, 5)
    ref30 = _ema_ref(c, wall, 30)
    yh = _yesterday_high(h, P, dord)
    lvl = np.where(P['is_first_rth'], P['premarket_hi'], P['rth_hi_before'])
    vm = pd.Series(v).rolling(_VOL_N, min_periods=_VOL_N).mean().shift(1).to_numpy()
    atr = P['atr14']
    with np.errstate(invalid='ignore', divide='ignore'):
        ctx = (c > ref5) & (c > ref30) & (c > yh)
        level = c > lvl
        rng_a = (h - l) / atr
        body_a = (c - o) / atr
        vol_x = np.where(vm > 0, v / vm, np.where(v > 0, np.inf, np.nan))
    next_is_last = np.r_[P['is_last_rth'][1:], False]
    dmask = (P['rth_mask'] & ~P['is_last_rth'] & ~next_is_last & ~np.isin(dord, _holidays())
             & (minute >= _WINDOWS['day'][0]) & (minute <= _WINDOWS['day'][1]))
    base0 = np.flatnonzero(dmask & ctx & level & (c > o) & np.isfinite(atr) & (atr > 0))
    held = np.zeros(len(base0), dtype=bool)
    for q, i in enumerate(base0):
        held[q] = _held(h, l, int(i), float(atr[i]))[0]
    F = dict(cand=base0, held=held, rng_a=rng_a[base0], body_a=body_a[base0], vol_x=vol_x[base0],
             minute=minute[base0])
    _FEAT_CACHE.append((key, F))
    del _FEAT_CACHE[:-_FEAT_CACHE_MAX]
    return F


def _held(h, l, i, atr_i):
    """(held, bars_held, base_atr): the 30-bar high's EARLIEST bar is >= 10 bars before i and the base under it
    (that high minus the lowest low after it, to i-1) is <= 5 ATR14."""
    lo = i - _HELD_LOOK
    if lo < 0 or not (atr_i > 0):
        return False, None, None
    j = lo + int(np.argmax(h[lo:i]))
    after = l[j + 1:i]
    base = (h[j] - after.min()) / atr_i if len(after) else 0.0
    return (i - j >= _HELD_MIN) and (base <= _BASE_MAX_ATR), i - j, base


def _signals(o, h, l, c, v, index, base='any', window='am', vol_mult=1.5, range_atr=1.2, body_atr=0.7):
    """(P, sorted decision-bar indices that pass every rule). Element i reads only bars up to i."""
    if base not in _BASES:
        raise ValueError("CBUQ_2_0: base must be one of %s, got %r" % (", ".join(_BASES), base))
    if window not in _WINDOWS:
        raise ValueError("CBUQ_2_0: window must be one of %s, got %r" % (", ".join(_WINDOWS), window))
    P = SK.prep(o, h, l, c, v, index, side=1)
    F = _features(o, h, l, c, v, index, P)
    a, z = _WINDOWS[window]
    with np.errstate(invalid='ignore'):
        keep = ((F['rng_a'] >= range_atr) & (F['body_a'] >= body_atr) & (F['vol_x'] >= vol_mult)
                & (F['minute'] >= a) & (F['minute'] <= z))
    if base == 'held':
        keep &= F['held']
    return P, F['cand'][keep]


def _walk(o, h, l, c, k0, kend, entry, stop, risk, exit_mode):
    """One long trade from the open of bar k0 to at most the close of bar kend: (exit_bar, pnl_pts).
    Within a bar the stop is checked first (a gap through it fills at the open), then the 2 R target (be2r),
    then the breakeven arming on the bar's CLOSE, which moves the stop to entry from the NEXT bar."""
    target = entry + _TARGET_R * risk if exit_mode == 'be2r' else np.inf
    arm = entry + _BE_R * risk
    s = stop
    armed = False
    for k in range(k0, kend + 1):
        if o[k] <= s:
            return k, float(o[k] - entry)
        if l[k] <= s:
            return k, float(s - entry)
        if h[k] >= target:
            return k, float(target - entry)
        if not armed and c[k] >= arm:
            armed = True
            s = max(s, entry)
    return kend, float(c[kend] - entry)


def _core(opens, highs, lows, closes, volumes, index, *, base='any', window='am', exit_mode='ride',
          vol_mult=1.5, range_atr=1.2, body_atr=0.7):
    """[(fill_bar, exit_bar, pnl_pts, entry_px)], long only."""
    if exit_mode not in _EXITS:
        raise ValueError("CBUQ_2_0: exit_mode must be one of %s, got %r" % (", ".join(_EXITS), exit_mode))
    o = np.asarray(opens, float); h = np.asarray(highs, float)
    l = np.asarray(lows, float);  c = np.asarray(closes, float)
    v = np.asarray(volumes, float)
    P, sig = _signals(o, h, l, c, v, index, base=base, window=window, vol_mult=float(vol_mult),
                      range_atr=float(range_atr), body_atr=float(body_atr))
    sess = P['sess']; last = P['last_rth_idx']
    n = len(c)
    trades = []
    cur_s, count, free_from = -1, 0, -1
    for i in sig:
        i = int(i)
        s = int(sess[i])
        if s != cur_s:
            cur_s, count = s, 0
        if count >= _MAX_PER_SESSION or i < free_from:
            continue
        k0 = i + 1
        kend = int(last[s])
        if k0 >= n or kend < k0:
            continue
        stop = l[i] - _TICK
        entry = o[k0]
        risk = entry - stop
        if not (risk > 0):
            continue
        xb, pnl = _walk(o, h, l, c, k0, kend, entry, stop, risk, exit_mode)
        trades.append((k0, xb, pnl, float(entry)))
        count += 1
        free_from = xb
    return trades


def run_backtest(opens, highs, lows, closes, volumes=None, day_id=None, index=None,
                 base='any', window='am', exit_mode='ride', vol_mult=1.5, range_atr=1.2, body_atr=0.7,
                 return_trades=False, _stop_event=None, _pause_event=None, **_ignore):
    if index is None or len(index) != len(closes):
        raise ValueError("CBUQ_2_0: run_backtest needs `index` (bar timestamps) matching the price arrays' length")
    if volumes is None:
        raise ValueError("CBUQ_2_0: the volume rule needs `volumes`")
    t4 = _core(opens, highs, lows, closes, volumes, index, base=base, window=window, exit_mode=exit_mode,
               vol_mult=vol_mult, range_atr=range_atr, body_atr=body_atr)
    return SK.stats([(fb, xb, pnl, 1, e) for (fb, xb, pnl, e) in t4], return_trades=return_trades)
