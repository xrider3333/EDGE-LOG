"""EBU-Q 1m 1.0 -- automated version of the owner's discretionary EBU setup: a local
breakout inside the day's own range (close breaks the recent brk_n-bar high but stays
below today's regular-session high so far).

Pre-registered: SETUPS_PREREG.md (sections 3-6), committed before any result for this file
existed. Implements section 3 (shared mechanics, via augur_engine/setup_kit.py -- the same
module CBUQ_1M_1_0.py, CBDQ_1M_1_0.py and the two ENGU 2.0 files use) and section 4B (the
EBU rule) exactly as written there.

Rule (SETUPS_PREREG.md section 4B): at bar i (never the session's first RTH bar -- there is
no earlier bar to break), close > the highest high of the brk_n bars before i AND close <=
the highest high of today's regular-session bars before i (a local break that stays inside
the day's range); volume, base, window (end_min) and exits exactly as CBU-Q.

Long only. There is no short mirror in round 1 -- SETUPS_PREREG.md section 1 lists CBU-Q,
CBD-Q, EBU-Q, ENGU 2.0 and ENGU 2.0 D; EBU has no D file.
"""
import numpy as np

from augur_engine import setup_kit as SK

STRATEGY_NAME = "EBU-Q 1m 1.0"
DESCRIPTION = ("Automated version of the owner's discretionary EBU setup: a local "
              "breakout above the recent bars' high that stays inside today's own "
              "regular-session range. Pre-registered test plan in SETUPS_PREREG.md; no "
              "results assumed yet. Long only.")
VERSION = "1.0"
DIRECTION = "LONG"
TIMEFRAME = "1m"

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
    'end_min': {'default': 120, 'min': 30, 'max': 360, 'step': 30, 'type': 'int',
               'label': 'Latest entry (minutes after 09:30)',
               'tooltip': 'No new signal from a bar that closes later than this many minutes after 09:30.'},
    'vol_mult': {'default': 0.0, 'min': 0.0, 'max': 4.0, 'step': 1.0, 'type': 'float',
                'label': 'Volume filter (x baseline, 0=off)',
                'tooltip': "Signal bar volume must clear this multiple of the 10-bar baseline "
                           "(the session's first RTH bar never signals -- see above)."},
    'brk_n': {'default': 10, 'min': 5, 'max': 20, 'step': 5, 'type': 'int',
             'label': 'Local break length (bars)',
             'tooltip': 'Close must clear the highest high of this many prior bars.'},
    'base_bars': {'default': 0, 'min': 0, 'max': 6, 'step': 3, 'type': 'int',
                 'label': 'Base length (bars, 0=off)',
                 'tooltip': 'Require a tight consolidation this many bars before the signal.'},
    'base_k': {'default': 2.0, 'min': 1.5, 'max': 3.0, 'step': 0.5, 'type': 'float',
              'label': 'Base width (x ATR14)',
              'tooltip': "The base's high-low span must fit within this many ATR14."},
}

# SETUPS_PREREG.md section 6, cell B: brk_n x end_min x vol_mult x the 3 exits =
# 3x3x2x3 = 54 cells. See CBUQ_1M_1_0.py's PARAM_GRID_PRESETS comment for why the
# single-valued be_R/trail_bars/target_R do not multiply the cell count.
PARAM_GRID_PRESETS = {
    'Triage (pre-registered)': {
        'brk_n':        [5, 10, 20],
        'end_min':      [30, 120, 360],
        'vol_mult':     [0.0, 2.0],
        'exit_mode':    ['ride', 'trail', 'target'],
        'be_R':         [1.0],
        'trail_bars':   [15],
        'target_R':     [2.0],
        'base_bars':    [0],
        'base_k':       [2.0],
        'stop_buf_atr': [0.0],
        'min_risk_atr': [0.0],
    },
}


def _core(opens, highs, lows, closes, volumes, index, *,
         exit_mode='ride', be_R=1.0, trail_bars=15, target_R=2.0,
         stop_buf_atr=0.0, min_risk_atr=0.0, end_min=120, vol_mult=0.0,
         brk_n=10, base_bars=0, base_k=2.0):
    o = np.asarray(opens, float); h = np.asarray(highs, float)
    l = np.asarray(lows, float);  c = np.asarray(closes, float)
    v = None if volumes is None else np.asarray(volumes, float)

    P = SK.prep(o, h, l, c, v, index, side=1)
    dmask = SK.decision_mask(P, end_min, first_bar='skip')   # never the first RTH bar

    brk_hi = SK.rolling_max_before(h, brk_n, P['fp'])
    with np.errstate(invalid="ignore"):
        local_break = c > brk_hi
        inside_day = c <= P['rth_hi_before']
        cand = dmask & local_break & inside_day

    vok = SK.volume_ok(P['vol_base'], v, vol_mult)
    if vok is not None:
        cand = cand & vok
    bok = SK.base_ok(h, l, P['atr14'], base_bars, base_k, P['fp'])
    if bok is not None:
        cand = cand & bok

    return SK.run(o, h, l, c, P, cand, exit_mode, be_R, trail_bars, target_R,
                 stop_buf_atr, min_risk_atr)


def run_backtest(opens, highs, lows, closes, volumes=None, day_id=None, index=None,
                 exit_mode='ride', be_R=1.0, trail_bars=15, target_R=2.0,
                 stop_buf_atr=0.0, min_risk_atr=0.0, end_min=120, vol_mult=0.0,
                 brk_n=10, base_bars=0, base_k=2.0,
                 return_trades=False, _stop_event=None, _pause_event=None, **_ignore):
    if index is None or len(index) != len(closes):
        raise ValueError("EBUQ_1M_1_0: run_backtest needs `index` (bar timestamps) matching "
                         "the price arrays' length")
    if vol_mult and float(vol_mult) > 0 and volumes is None:
        raise ValueError("EBUQ_1M_1_0: vol_mult>0 needs `volumes`")
    trades4 = _core(opens, highs, lows, closes, volumes, index,
                    exit_mode=exit_mode, be_R=be_R, trail_bars=trail_bars, target_R=target_R,
                    stop_buf_atr=stop_buf_atr, min_risk_atr=min_risk_atr, end_min=end_min,
                    vol_mult=vol_mult, brk_n=brk_n, base_bars=base_bars, base_k=base_k)
    trades = [(fb, xb, pnl, 1, entry) for (fb, xb, pnl, entry) in trades4]
    return SK.stats(trades, return_trades=return_trades)
