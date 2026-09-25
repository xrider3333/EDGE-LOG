"""ENGU 2.0 -- automated version of the owner's discretionary ENGU setup: an engulfing
candle that breaks a short local high while staying inside today's regular-session range,
after a pullback.

Pre-registered: SETUPS_PREREG.md (sections 3-6), committed before any result for this file
existed. Rebuilt on the shared setup-kit walk (augur_engine/setup_kit.py -- the same module
CBUQ_1M_1_0.py, CBDQ_1M_1_0.py and EBUQ_1M_1_0.py use), NOT on the legacy 2010s-era ENGU
family (ENGU_1_1_*.py etc.) or the data-derived ENGU-Q trendline family (ENGUQ_*.py). Same
family name as the legacy ENGU files (`ENGU`, per CLAUDE.md's vocabulary) since it is the
same discretionary idea automated, not a new family.

Rule (SETUPS_PREREG.md section 4C): at bar i (never the session's first RTH bar), a green
candle (close>open); body=close-open, range=high-low (skipped if range==0); body >=
body_frac x range; body >= body_mult x the median body of the 10 bars before i; close >
the highest high of the eng_n bars before i (the engulf); volume >= vol_mult x baseline
(0=off); close < today's regular-session high so far (inside the range, not a new high --
that is CBU's job); a pullback: today's high-so-far minus the lowest low of the 10 bars
before i must be >= pb_atr x ATR14.

ENGU_2_0_D.py is the exact short mirror, by price inversion
(augur_engine.setup_kit.mirror_short), loading this file's `_core` by path.
"""
import numpy as np

from augur_engine import setup_kit as SK

STRATEGY_NAME = "ENGU 2.0"
DESCRIPTION = ("Automated version of the owner's discretionary ENGU setup: an engulfing "
              "candle that breaks a short local high while staying inside today's "
              "regular-session range, after a pullback. Pre-registered test plan in "
              "SETUPS_PREREG.md; no results assumed yet. Long only -- ENGU_2_0_D.py is "
              "its short mirror.")
VERSION = "2.0"
DIRECTION = "LONG"
TIMEFRAME = "1m"

_BODY_LOOKBACK = 10       # fixed, not a knob (SETUPS_PREREG.md section 4C)
_PULLBACK_LOOKBACK = 10   # fixed, not a knob

DEFAULT_PARAMS = {
    'exit_mode': {'default': 'ride', 'type': 'str', 'options': ['ride', 'trail', 'target'],
                  'label': 'Exit style',
                  'tooltip': "ride = move the stop to breakeven once be_R in profit, flat at the "
                             "session close. trail = ride, plus a trailing stop once armed. "
                             "target = a fixed profit target, no breakeven."},
    'be_R': {'default': 1.0, 'min': 0.5, 'max': 2.0, 'step': 0.5, 'type': 'float',
             'label': 'Breakeven trigger (R)',
             'tooltip': 'Arm breakeven once a bar CLOSES this many risk units above entry.'},
    'trail_bars': {'default': 15, 'min': 5, 'max': 30, 'step': 5, 'type': 'int',
                   'label': 'Trail width (bars)',
                   'tooltip': 'Trail mode only: once armed, the stop trails the lowest low of this '
                              'many bars.'},
    'target_R': {'default': 2.0, 'min': 1.0, 'max': 5.0, 'step': 1.0, 'type': 'float',
                 'label': 'Target (R)',
                 'tooltip': 'Target mode only: fixed profit target, in risk units.'},
    'stop_buf_atr': {'default': 0.0, 'min': 0.0, 'max': 0.5, 'step': 0.25, 'type': 'float',
                     'label': 'Stop buffer (x ATR14)',
                     'tooltip': "Extra room below the signal bar's low, in ATR14 (0=none)."},
    'min_risk_atr': {'default': 0.0, 'min': 0.0, 'max': 1.0, 'step': 0.5, 'type': 'float',
                     'label': 'Minimum risk (x ATR14)',
                     'tooltip': 'Skip a signal whose stop distance is this tight or tighter (0=off).'},
    'end_min': {'default': 360, 'min': 30, 'max': 360, 'step': 30, 'type': 'int',
               'label': 'Latest entry (minutes after 09:30)',
               'tooltip': 'No new signal from a bar that closes later than this many minutes after 09:30.'},
    'vol_mult': {'default': 0.0, 'min': 0.0, 'max': 4.0, 'step': 1.0, 'type': 'float',
                'label': 'Volume filter (x baseline, 0=off)',
                'tooltip': "Signal bar volume must clear this multiple of the 10-bar baseline "
                           "(the session's first RTH bar never signals -- see above)."},
    'body_frac': {'default': 0.6, 'min': 0.5, 'max': 0.8, 'step': 0.1, 'type': 'float',
                 'label': 'Minimum body (x range)',
                 'tooltip': "The candle's body must be at least this share of its own high-low "
                            "range."},
    'body_mult': {'default': 2.0, 'min': 1.5, 'max': 3.0, 'step': 0.5, 'type': 'float',
                 'label': 'Body vs recent median (x)',
                 'tooltip': 'Body must also be at least this many times the median body of the 10 '
                            'bars before it.'},
    'eng_n': {'default': 1, 'min': 1, 'max': 3, 'step': 1, 'type': 'int',
             'label': 'Engulf length (bars)',
             'tooltip': 'Close must clear the highest high of this many prior bars (1 = engulfs '
                        'just the previous bar).'},
    'pb_atr': {'default': 0.0, 'min': 0.0, 'max': 4.0, 'step': 1.0, 'type': 'float',
              'label': 'Required pullback (x ATR14, 0=off)',
              'tooltip': "Today's high so far minus the lowest low of the 10 bars before the "
                         "signal must be at least this many ATR14."},
}

# SETUPS_PREREG.md section 6, cell C (each side): body_mult x pb_atr x end_min x vol_mult
# x the 3 exits = 2x2x2x2x3 = 48 cells; body_frac 0.6, eng_n 1 fixed. See
# CBUQ_1M_1_0.py's PARAM_GRID_PRESETS comment for why the single-valued be_R/trail_bars/
# target_R do not multiply the cell count.
PARAM_GRID_PRESETS = {
    'Triage (pre-registered)': {
        'body_mult':    [2.0, 3.0],
        'pb_atr':       [0.0, 2.0],
        'end_min':      [60, 360],
        'vol_mult':     [0.0, 2.0],
        'exit_mode':    ['ride', 'trail', 'target'],
        'be_R':         [1.0],
        'trail_bars':   [15],
        'target_R':     [2.0],
        'body_frac':    [0.6],
        'eng_n':        [1],
        'stop_buf_atr': [0.0],
        'min_risk_atr': [0.0],
    },
}


def _core(opens, highs, lows, closes, volumes, index, *,
         exit_mode='ride', be_R=1.0, trail_bars=15, target_R=2.0,
         stop_buf_atr=0.0, min_risk_atr=0.0, end_min=360, vol_mult=0.0,
         body_frac=0.6, body_mult=2.0, eng_n=1, pb_atr=0.0):
    o = np.asarray(opens, float); h = np.asarray(highs, float)
    l = np.asarray(lows, float);  c = np.asarray(closes, float)
    v = None if volumes is None else np.asarray(volumes, float)

    P = SK.prep(o, h, l, c, v, index, side=1)
    dmask = SK.decision_mask(P, end_min, first_bar='skip')   # never the first RTH bar

    body = c - o
    rng = h - l
    eng_hi = SK.rolling_max_before(h, eng_n, P['fp'])
    med_body = SK.rolling_median_abs_body_before(o, c, _BODY_LOOKBACK, P['fp'])
    low10 = SK.rolling_min_before(l, _PULLBACK_LOOKBACK, P['fp'])

    with np.errstate(invalid="ignore", divide="ignore"):
        green = body > 0
        has_range = rng > 0
        body_ok = has_range & (body >= body_frac * rng)
        body_vs_med = np.isfinite(med_body) & (body >= body_mult * med_body)
        engulf = c > eng_hi
        inside_day = np.isfinite(P['rth_hi_before']) & (c < P['rth_hi_before'])
        pullback_ok = (pb_atr <= 0) | (np.isfinite(low10) & np.isfinite(P['rth_hi_before']) &
                                       ((P['rth_hi_before'] - low10) >= pb_atr * P['atr14']))
        cand = dmask & green & body_ok & body_vs_med & engulf & inside_day & pullback_ok

    vok = SK.volume_ok(P['vol_base'], v, vol_mult)
    if vok is not None:
        cand = cand & vok

    return SK.run(o, h, l, c, P, cand, exit_mode, be_R, trail_bars, target_R,
                 stop_buf_atr, min_risk_atr)


def run_backtest(opens, highs, lows, closes, volumes=None, day_id=None, index=None,
                 exit_mode='ride', be_R=1.0, trail_bars=15, target_R=2.0,
                 stop_buf_atr=0.0, min_risk_atr=0.0, end_min=360, vol_mult=0.0,
                 body_frac=0.6, body_mult=2.0, eng_n=1, pb_atr=0.0,
                 return_trades=False, _stop_event=None, _pause_event=None, **_ignore):
    if index is None or len(index) != len(closes):
        raise ValueError("ENGU_2_0: run_backtest needs `index` (bar timestamps) matching the "
                         "price arrays' length")
    if vol_mult and float(vol_mult) > 0 and volumes is None:
        raise ValueError("ENGU_2_0: vol_mult>0 needs `volumes`")
    trades4 = _core(opens, highs, lows, closes, volumes, index,
                    exit_mode=exit_mode, be_R=be_R, trail_bars=trail_bars, target_R=target_R,
                    stop_buf_atr=stop_buf_atr, min_risk_atr=min_risk_atr, end_min=end_min,
                    vol_mult=vol_mult, body_frac=body_frac, body_mult=body_mult, eng_n=eng_n,
                    pb_atr=pb_atr)
    trades = [(fb, xb, pnl, 1, entry) for (fb, xb, pnl, entry) in trades4]
    return SK.stats(trades, return_trades=return_trades)
