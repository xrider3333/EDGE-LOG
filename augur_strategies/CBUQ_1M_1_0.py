"""CBU-Q 1m 1.0 -- automated version of the owner's discretionary CBU setup: the session's
close breaks out to a new regular-session high above a premarket or prior-day level.

Pre-registered: SETUPS_PREREG.md (sections 3-6), committed before any result for this file
existed. This file implements sections 3 (shared mechanics) and 4A (the CBU rule) exactly
as written there; the trade walk, sessions, ATR14, RTH/premarket/prior-day levels, the
volume baseline and the roll-day handling all live in augur_engine/setup_kit.py, shared
with CBDQ_1M_1_0.py (the short mirror), EBUQ_1M_1_0.py and the two ENGU 2.0 files, so the
long/short mechanics cannot drift between them.

Rule (SETUPS_PREREG.md section 4A): at bar i, close > the highest high of today's
regular-session bars before i (skipped at the session's first RTH bar -- there is no
earlier bar to compare against, but the level test below still applies there); close >
`level` (level_mode: pm = premarket high, pdh = prior-day regular-session high, both =
above both); the signal bar i closes no later than `end_min` minutes after 09:30;
`first_bar` allow/skip controls whether the session's first RTH bar may even be a decision
bar; volume >= vol_mult x its baseline (0 = off); if base_bars > 0, the high-low span of
the base_bars bars before i must be <= base_k x ATR14 (a tight base before the break).

CBDQ_1M_1_0.py is the exact short mirror, by price inversion
(augur_engine.setup_kit.mirror_short), loading this file's `_core` by path.
"""
import numpy as np

from augur_engine import setup_kit as SK

STRATEGY_NAME = "CBU-Q 1m 1.0"
DESCRIPTION = ("Automated version of the owner's discretionary CBU setup: the session's "
              "close breaks out to a new regular-session high above a premarket or "
              "prior-day level. Pre-registered test plan in SETUPS_PREREG.md; no results "
              "assumed yet. Long only -- CBDQ_1M_1_0.py is its short mirror.")
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
                           "(the session's first RTH bar instead compares to the last 20 sessions' "
                           "own first-bar volume)."},
    'level_mode': {'default': 'both', 'type': 'str', 'options': ['pm', 'pdh', 'both'],
                   'label': 'Level',
                   'tooltip': 'pm = premarket high, pdh = prior regular-session high, both = above '
                              'both.'},
    'first_bar': {'default': 'allow', 'type': 'str', 'options': ['allow', 'skip'],
                  'label': "09:30 bar",
                  'tooltip': "allow = the session's first RTH bar can signal (only the level test "
                             "applies there). skip = never decide on the first RTH bar."},
    'base_bars': {'default': 0, 'min': 0, 'max': 6, 'step': 3, 'type': 'int',
                 'label': 'Base length (bars, 0=off)',
                 'tooltip': 'Require a tight consolidation this many bars before the signal.'},
    'base_k': {'default': 2.0, 'min': 1.5, 'max': 3.0, 'step': 0.5, 'type': 'float',
              'label': 'Base width (x ATR14)',
              'tooltip': "The base's high-low span must fit within this many ATR14."},
}

# SETUPS_PREREG.md section 6, cell A (each side): level_mode x end_min x vol_mult x the 3
# exits = 3x3x2x3 = 54 cells; first_bar allow, base off, buffer 0, min risk 0. be_R/
# trail_bars/target_R each carry ONE fixed value alongside exit_mode -- the grid runner
# (augur_engine.optimize.grid_from_preset) takes the cartesian product of every listed
# value, so a single-element list does not multiply the cell count; it just rides along
# with whichever exit_mode is active (and is simply unused by the other two exit modes).
PARAM_GRID_PRESETS = {
    'Triage (pre-registered)': {
        'level_mode':   ['pm', 'pdh', 'both'],
        'end_min':      [30, 120, 360],
        'vol_mult':     [0.0, 2.0],
        'exit_mode':    ['ride', 'trail', 'target'],
        'be_R':         [1.0],
        'trail_bars':   [15],
        'target_R':     [2.0],
        'first_bar':    ['allow'],
        'base_bars':    [0],
        'base_k':       [2.0],
        'stop_buf_atr': [0.0],
        'min_risk_atr': [0.0],
    },
}


def _core(opens, highs, lows, closes, volumes, index, *,
         exit_mode='ride', be_R=1.0, trail_bars=15, target_R=2.0,
         stop_buf_atr=0.0, min_risk_atr=0.0, end_min=120, vol_mult=0.0,
         level_mode='both', first_bar='allow', base_bars=0, base_k=2.0):
    """The long-side core: everything except turning trades into a stats dict. Returns a
    list of (fill_bar, exit_bar, pnl_pts, entry_px) 4-tuples (no side -- run_backtest below
    adds side=1; CBDQ_1M_1_0.py calls this SAME function on inverted arrays via
    setup_kit.mirror_short, which adds side=-1 and flips the entry price back positive)."""
    o = np.asarray(opens, float); h = np.asarray(highs, float)
    l = np.asarray(lows, float);  c = np.asarray(closes, float)
    v = None if volumes is None else np.asarray(volumes, float)

    P = SK.prep(o, h, l, c, v, index, side=1)
    dmask = SK.decision_mask(P, end_min, first_bar=first_bar)

    with np.errstate(invalid="ignore"):
        new_high = P['is_first_rth'] | (c > P['rth_hi_before'])   # skipped (passes) at 09:30
        if level_mode == 'pm':
            level_ok = c > P['premarket_hi']
        elif level_mode == 'pdh':
            level_ok = c > P['priorday_hi']
        else:
            level_ok = (c > P['premarket_hi']) & (c > P['priorday_hi'])
        cand = dmask & new_high & level_ok

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
                 level_mode='both', first_bar='allow', base_bars=0, base_k=2.0,
                 return_trades=False, _stop_event=None, _pause_event=None, **_ignore):
    if index is None or len(index) != len(closes):
        raise ValueError("CBUQ_1M_1_0: run_backtest needs `index` (bar timestamps) matching "
                         "the price arrays' length")
    if vol_mult and float(vol_mult) > 0 and volumes is None:
        raise ValueError("CBUQ_1M_1_0: vol_mult>0 needs `volumes`")
    trades4 = _core(opens, highs, lows, closes, volumes, index,
                    exit_mode=exit_mode, be_R=be_R, trail_bars=trail_bars, target_R=target_R,
                    stop_buf_atr=stop_buf_atr, min_risk_atr=min_risk_atr, end_min=end_min,
                    vol_mult=vol_mult, level_mode=level_mode, first_bar=first_bar,
                    base_bars=base_bars, base_k=base_k)
    trades = [(fb, xb, pnl, 1, entry) for (fb, xb, pnl, entry) in trades4]
    return SK.stats(trades, return_trades=return_trades)
