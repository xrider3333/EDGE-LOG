"""CBU-Q PTS 1.0 -- SETUPS round 2: the point-score leads (largest body AND largest volume since
today's low, trend, first half hour, EMA, yesterday's high) as an algorithm, long side.

Pre-registered: SETUPS_PREREG_R2.md (section 3), committed before this file or any result for
it existed. Shared mechanics -- sessions, ATR14, the trade walk, the one-trade-per-session
scan -- come from augur_engine/setup_kit.py exactly as in round 1; CBDQ_PTS_1_0.py is the
short mirror by price inversion (setup_kit.mirror_short), loading this file's `_core` by path.

Rule (SETUPS_PREREG_R2.md section 3). The decision is made at the close of a regular-session
one-minute bar i (start 09:30-15:58 ET); entry is the open of bar i+1; one trade per session,
the first bar that passes.

  trigger   bar i is green (C > O), its body |C - O| is >= the body of every bar in the
            window, and its volume is >= the volume of every bar in the window. The window
            runs from the LATEST bar that holds today's lowest low (today = regular-session
            bars from 09:30; a tie for the low goes to the later bar) through bar i, and must
            hold at least `min_win` bars.
  filt      one of five, all read only from bars closed by bar i:
            none    the trigger alone (the raw twin);
            trend   the prior regular session's high AND low are both above the session
                    before it (a "regular session" is a date whose regular-session bars end
                    at 13:14 or later -- holiday 09:30-13:00 stubs and cut-off days are
                    skipped, an early close ending 13:14 is kept);
            open30  bar i starts 09:30-09:59;
            ema3    C is above the 200 EMA (pandas ewm span 200, adjust False, over the whole
                    24-hour series) of the 1-minute bars (through bar i) and of the 5-minute
                    and 30-minute bars resampled from that series, where the 5m/30m
                    reference is the bar BEFORE the one containing bar i;
            yhigh   C is above the prior regular session's high.
  stop      low(i) - stop_buf_atr x ATR14 (setup_kit's ATR14); no trade when risk <= 0.
  exit      ride    breakeven armed when a bar closes at entry + 1 R, flat at the 15:59 close;
            target  a fixed target at 1 R, stop or target, flat at the 15:59 close.
            (be_R and target_R are fixed at 1.0 by the pre-registration, so they are not
            knobs.) Walk, fills, stop-first and costs are setup_kit's, as in round 1.

The prior-session levels are computed here from the regular-session bars of the data as given
(the round-2 masters are roll-corrected FADJ_ bars, so no seam blanking: the 200 EMAs cross
rolls, which is why round 2 uses them). Everything is vectorised over the whole tape and
cached per frame, so a knob sweep on one set of arrays only re-runs the per-session trade scan.
"""
import numpy as np
import pandas as pd

from augur_engine import setup_kit as SK

STRATEGY_NAME = "CBU-Q PTS 1.0"
DESCRIPTION = ("SETUPS round 2: the point-score leads as a rule -- a green candle with the "
              "largest body and the largest volume since today's low, optionally filtered by "
              "trend, the first half hour, a triple 200-EMA test or yesterday's high. "
              "Pre-registered in SETUPS_PREREG_R2.md; no results assumed. Long only -- "
              "CBDQ_PTS_1_0.py is its short mirror.")
VERSION = "1.0"
DIRECTION = "LONG"
TIMEFRAME = "1m"

_FILTS = ("none", "trend", "open30", "ema3", "yhigh")
_EXITS = ("ride", "target")
_BE_R = 1.0                  # pre-registered, not a knob
_TARGET_R = 1.0              # pre-registered, not a knob
_TRAIL_BARS = 15             # unused by ride/target; SK.run's signature wants a value
_STUB_END_MIN = 13 * 60 + 14  # a regular session's last bar starts at 13:14 or later
_EMA_SPAN = 200

DEFAULT_PARAMS = {
    'filt': {'default': 'none', 'type': 'str', 'options': list(_FILTS),
             'label': 'Filter',
             'tooltip': "none = the trigger alone. trend = the prior regular session's high and low "
                        "are both above the session before it. open30 = the signal bar starts "
                        "09:30-09:59. ema3 = the close is above the 200 EMA of the 1-minute, "
                        "5-minute and 30-minute bars. yhigh = the close is above the prior "
                        "regular session's high."},
    'exit_mode': {'default': 'ride', 'type': 'str', 'options': list(_EXITS),
                  'label': 'Exit style',
                  'tooltip': "ride = move the stop to breakeven once a bar closes 1 R above entry, "
                             "flat at the session close. target = a fixed 1 R profit target, flat "
                             "at the session close."},
    'min_win': {'default': 5, 'min': 5, 'max': 10, 'step': 5, 'type': 'int',
                'label': 'Minimum window (bars)',
                'tooltip': "The signal bar's window (from the latest bar holding today's lowest "
                           "low through the signal bar) must hold at least this many bars, so the "
                           "first bars after a new low cannot qualify."},
    'stop_buf_atr': {'default': 0.0, 'min': 0.0, 'max': 0.25, 'step': 0.25, 'type': 'float',
                     'label': 'Stop buffer (x ATR14)',
                     'tooltip': "Extra room below the signal bar's low, in ATR14 (0 = none)."},
}

# SETUPS_PREREG_R2.md section 4: triage = 5 filters x 2 exits per file (min_win 5, buffer 0) =
# 10 cells per file and root, i.e. 20 per side over NQ and ES; 40 cells over both sides and
# both roots. Section 5: the validate grid = filter x exit x min_win {5, 10} x buffer {0, 0.25}.
PARAM_GRID_PRESETS = {
    'Triage (pre-registered)': {
        'filt':         list(_FILTS),
        'exit_mode':    list(_EXITS),
        'min_win':      [5],
        'stop_buf_atr': [0.0],
    },
    'Validate (pre-registered)': {
        'filt':         list(_FILTS),
        'exit_mode':    list(_EXITS),
        'min_win':      [5, 10],
        'stop_buf_atr': [0.0, 0.25],
    },
}


# ─────────────────────────────────────────────────────────────────────────────
# per-frame feature cache (same idea as setup_kit's prep cache: <= 2 frames, keyed by the
# kit's fingerprint plus the volumes and timestamps, which prep()'s key does not cover)
# ─────────────────────────────────────────────────────────────────────────────
_FEAT_CACHE_MAX = 2
_FEAT_CACHE = []                 # [(key, F), ...] index 0 = least recently used


def _clear_caches():
    """Test hook: forget this module's cached frames (and the kit's)."""
    del _FEAT_CACHE[:]
    del SK._PREP_CACHE[:]


def _feat_key(P, v, index):
    n = len(v)
    stride = max(1, n // 997)
    ix = pd.DatetimeIndex(index)
    return (P['fp'], float(np.nansum(v[::stride])), float(v[n // 2]), int(ix[0].value), int(ix[-1].value))


def _ema_refs(c, index):
    """(ema1, ref5, ref30): the 200 EMA of the 1m bars THROUGH each bar, and of the 5m and 30m
    bars of the same 24-hour series as of the bar BEFORE the one holding each bar (NaN before
    the second bucket). Buckets are wall-clock (ET) 5- and 30-minute slots built from bar
    timestamps; an EMA is taken over the buckets that exist (the daily break has none). Causal:
    ewm at a bucket uses only that bucket and earlier ones, and the previous bucket is complete
    before bar i opens."""
    ix = pd.DatetimeIndex(index)
    if ix.tz is not None:
        ix = ix.tz_localize(None)
    wall = ix.asi8
    ema1 = pd.Series(c).ewm(span=_EMA_SPAN, adjust=False).mean().to_numpy()

    def _ref(minutes):
        b = wall // (int(minutes) * 60_000_000_000)
        change = b[1:] != b[:-1]
        bucket_of_bar = np.cumsum(np.r_[0, change.astype(np.int64)])
        last_in_bucket = np.flatnonzero(np.r_[change, True])
        e = pd.Series(c[last_in_bucket]).ewm(span=_EMA_SPAN, adjust=False).mean().to_numpy()
        prev = np.r_[np.nan, e[:-1]]                    # the bucket BEFORE the one holding bar i
        return prev[bucket_of_bar]

    return ema1, _ref(5), _ref(30)


def _ema_above(c, index):
    """Close above all three EMAs of _ema_refs (the ema3 filter)."""
    ema1, ref5, ref30 = _ema_refs(c, index)
    with np.errstate(invalid="ignore"):
        return (c > ema1) & (c > ref5) & (c > ref30)


def _prior_session_levels(h, l, P):
    """Per session id: the prior regular session's high / low and whether its high and low are
    both above the regular session before it. A regular session is a session whose
    regular-session bars end at 13:14 or later; 'prior' is strictly earlier. NaN where there is
    no such session."""
    sess = P['sess']; minute = P['minute']
    n_sess = len(P['starts'])
    ridx = np.flatnonzero(P['rth_mask'])
    hi_s = np.full(n_sess, np.nan); lo_s = np.full(n_sess, np.nan)
    if len(ridx):
        rs = sess[ridx]
        b = np.flatnonzero(np.r_[True, rs[1:] != rs[:-1]])
        hi_s[rs[b]] = np.maximum.reduceat(h[ridx], b)
        lo_s[rs[b]] = np.minimum.reduceat(l[ridx], b)
    last = P['last_rth_idx']
    valid = (last >= 0) & (minute[np.maximum(last, 0)] >= _STUB_END_MIN)
    vs = np.flatnonzero(valid)                           # regular sessions, ascending
    p = np.searchsorted(vs, np.arange(n_sess), side='left') - 1   # latest regular session < s
    has1 = p >= 0
    has2 = p >= 1
    hi1 = np.where(has1, hi_s[vs[np.maximum(p, 0)]], np.nan) if len(vs) else np.full(n_sess, np.nan)
    lo1 = np.where(has1, lo_s[vs[np.maximum(p, 0)]], np.nan) if len(vs) else np.full(n_sess, np.nan)
    hi2 = np.where(has2, hi_s[vs[np.maximum(p - 1, 0)]], np.nan) if len(vs) else np.full(n_sess, np.nan)
    lo2 = np.where(has2, lo_s[vs[np.maximum(p - 1, 0)]], np.nan) if len(vs) else np.full(n_sess, np.nan)
    with np.errstate(invalid="ignore"):
        trend = (hi1 > hi2) & (lo1 > lo2)
    return hi1, lo1, trend


def _frame_features(o, h, l, c, v, index, P):
    """Everything that does not depend on the knobs, built once per frame."""
    key = _feat_key(P, v, index)
    for j, (k, F) in enumerate(_FEAT_CACHE):
        if k == key:
            _FEAT_CACHE.append(_FEAT_CACHE.pop(j))
            return F
    n = len(c)
    ar = np.arange(n)
    rth = P['rth_mask']
    with np.errstate(invalid="ignore"):
        # a bar that sets or ties today's regular-session low so far opens a new window (the
        # LATEST bar holding the low wins ties); the session's first regular bar always does
        is_new = rth & (P['is_first_rth'] | (l <= P['rth_lo_before']))
    start = np.maximum.accumulate(np.where(is_new, ar, -1))
    winlen = np.where(start >= 0, ar - start + 1, 0).astype(np.int32)
    seg = np.cumsum(is_new, dtype=np.int64)              # window id; restarts at every new low
    body = np.abs(c - o)
    with np.errstate(invalid="ignore"):
        max_body = pd.Series(body).groupby(seg).cummax().to_numpy()
        max_vol = pd.Series(v).groupby(seg).cummax().to_numpy()
        trig = (c > o) & (body >= max_body) & (v >= max_vol)
    dmask = rth & ~P['is_last_rth']                      # decision bars: 09:30 .. last bar - 1
    cand0 = np.flatnonzero(trig & dmask)
    F = dict(cand0=cand0, winlen_c=winlen[cand0], filt={}, n=n)
    _FEAT_CACHE.append((key, F))
    del _FEAT_CACHE[:-_FEAT_CACHE_MAX]
    return F


def _filter_bars(name, o, h, l, c, v, index, P, F):
    """Bool array (len n) for one filter, cached in the frame's features."""
    if name in F['filt']:
        return F['filt'][name]
    if name == 'none':
        arr = None
    elif name == 'open30':
        m = P['minute']
        arr = (m >= SK.RTH_START_MIN) & (m < SK.RTH_START_MIN + 30)
    elif name == 'ema3':
        arr = _ema_above(c, index)
    else:                                                # trend / yhigh share the session levels
        hi1, lo1, trend = _prior_session_levels(h, l, P)
        sess = P['sess']
        if name == 'trend':
            arr = trend[sess]
        else:
            with np.errstate(invalid="ignore"):
                arr = c > hi1[sess]
    F['filt'][name] = arr
    return arr


def _candidates(opens, highs, lows, closes, volumes, index, filt='none', min_win=5):
    """(P, bool candidate mask): decision bars that pass the trigger, the window length and the
    filter. Causal: element i reads only bars up to i."""
    o = np.asarray(opens, float); h = np.asarray(highs, float)
    l = np.asarray(lows, float);  c = np.asarray(closes, float)
    v = np.asarray(volumes, float)
    P = SK.prep(o, h, l, c, v, index, side=1)
    F = _frame_features(o, h, l, c, v, index, P)
    keep = F['winlen_c'] >= int(min_win)
    fa = _filter_bars(filt, o, h, l, c, v, index, P, F)
    if fa is not None:
        keep = keep & fa[F['cand0']]
    mask = np.zeros(len(c), dtype=bool)
    mask[F['cand0'][keep]] = True
    return P, mask


def _core(opens, highs, lows, closes, volumes, index, *, filt='none', exit_mode='ride',
          min_win=5, stop_buf_atr=0.0):
    """The long-side core: a list of (fill_bar, exit_bar, pnl_pts, entry_px) 4-tuples (no side --
    run_backtest below adds side=1; CBDQ_PTS_1_0.py calls this SAME function on inverted arrays
    via setup_kit.mirror_short, which adds side=-1 and flips the entry price back positive)."""
    if filt not in _FILTS:
        raise ValueError("CBUQ_PTS_1_0: filt must be one of %s, got %r" % (", ".join(_FILTS), filt))
    if exit_mode not in _EXITS:
        raise ValueError("CBUQ_PTS_1_0: exit_mode must be one of %s, got %r" % (", ".join(_EXITS), exit_mode))
    if volumes is None:
        raise ValueError("CBUQ_PTS_1_0: the trigger needs `volumes`")
    P, mask = _candidates(opens, highs, lows, closes, volumes, index, filt=filt, min_win=min_win)
    o = np.asarray(opens, float); h = np.asarray(highs, float)
    l = np.asarray(lows, float);  c = np.asarray(closes, float)
    return SK.run(o, h, l, c, P, mask, exit_mode, _BE_R, _TRAIL_BARS, _TARGET_R,
                  float(stop_buf_atr), 0.0)


def run_backtest(opens, highs, lows, closes, volumes=None, day_id=None, index=None,
                 filt='none', exit_mode='ride', min_win=5, stop_buf_atr=0.0,
                 return_trades=False, _stop_event=None, _pause_event=None, **_ignore):
    if index is None or len(index) != len(closes):
        raise ValueError("CBUQ_PTS_1_0: run_backtest needs `index` (bar timestamps) matching "
                         "the price arrays' length")
    if volumes is None:
        raise ValueError("CBUQ_PTS_1_0: the trigger needs `volumes`")
    trades4 = _core(opens, highs, lows, closes, volumes, index, filt=filt, exit_mode=exit_mode,
                    min_win=min_win, stop_buf_atr=stop_buf_atr)
    trades = [(fb, xb, pnl, 1, entry) for (fb, xb, pnl, entry) in trades4]
    return SK.stats(trades, return_trades=return_trades)
