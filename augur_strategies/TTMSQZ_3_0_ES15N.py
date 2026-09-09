"""
TTMSQZ 3.0 ES15N — the ES 15-minute Carter cell, fenced, as a leg-level test.

WHY THIS EXISTS (round 9 -> BOOK run #342, 2026-09-09)
  Round 9 asked whether the book wants a second TTM cell and found one candidate: the ES 15-minute
  Carter cell, run at the 30-minute crown's settings with nothing retuned. Added to the book on top
  of the validated size tilt it produced BOOK run #342, which cleared every clause of its
  pre-registered bar - annualised MAR times 1.10 against a bar of times 1.05, whole-run drawdown
  times 1.007, lockbox times 1.08 with a LOWER lockbox drawdown, eight of eight slices held.

  That result came with a caveat written into the job note before the run, and this file is the
  caveat: THE 15-MINUTE CELL HAS NEVER BEEN VALIDATED ON ITS OWN. Alone it is a thin thing -
  profit factor 1.31, 525 trades, $22,460 at a drawdown of $8,240, lockbox +$3,417 - and a book
  result cannot certify a leg. Until this run comes back the 15-minute cell is a LEAD, not a leg.

WHAT IS SEARCHED, AND WHAT IS INHERITED
  The four knobs and the admissible set are INHERITED from TTMSQZ_3_0_ES30N.py (run #299's file)
  rather than chosen here. That is deliberate: the round-9 scan ran this cell at the 30-minute
  crown's settings, so inheriting the fence keeps the tested thing and the validated thing the
  same, and it means the set was fixed before anyone looked at 15-minute results. The mechanism,
  the entry style, the exit and the hourly verification are frozen in the wrapper exactly as they
  are for the 30-minute file.

  gate_bars is 4 here, not 2: it is the fallback the grid code path uses when a strategy is handed
  no bar timestamps, and four 15-minute bars make the hour that two 30-minute bars make. The
  validate path passes the clock and never uses it.

Engine = TTMSQZ_3_0.py, imported unchanged. Sibling of TTMSQZ_3_0_ES30N.py (run #299) and
TTMSQZ_3_0_ES30T.py (run #340).
"""
import os
from importlib import util as _u

_sp = _u.spec_from_file_location(
    "TTMSQZ_3_0", os.path.join(os.path.dirname(os.path.abspath(__file__)), "TTMSQZ_3_0.py"))
_t3 = _u.module_from_spec(_sp); _sp.loader.exec_module(_t3)

_FROZEN = {'length': 20, 'bb_mult': 2.0, 'min_sq_bars': 1, 'entry_fill': 'open', 'exit_mode': 'fade',
           'fade_bars': 1, 'gate_tf_min': 60, 'gate_mode': 'sq_on', 'gate_fired_k': 3,
           'gate_bars': 4, 'direction': 'both'}


def run_backtest(opens, highs, lows, closes, volumes=None, day_id=None, index=None, **kw):
    """The inherited neighbourhood on 15-minute bars. `index` is named explicitly because the engine
    only hands bar timestamps to a strategy that declares them, and the hourly verification prefers
    the wall clock. An out-of-set configuration is REFUSED, never clamped."""
    if not _in_neighbourhood(kw):
        return None
    kw.update(_FROZEN)
    return _t3.run_backtest(opens, highs, lows, closes, volumes=volumes, day_id=day_id,
                            index=index, **kw)


# Admissibility is enforced here, where Auto-Validate's range widening cannot reach it (runs 290
# and 293 are why). Same set as TTMSQZ_3_0_ES30N.py.
_ADMISSIBLE = {'kc_mult': [1.25, 1.5, 1.75], 'stop_atr': [1.5, 2.0, 2.5],
               'eod_cutoff': [1, 3, 5], 'gate_len': [16, 20, 24]}


def _in_neighbourhood(kw):
    for k, allowed in _ADMISSIBLE.items():
        if k not in kw:
            continue
        v = kw[k]
        if not any(abs(float(v) - float(a)) < 1e-9 for a in allowed):
            return False
    return True


squeeze_indicators = _t3.squeeze_indicators

STRATEGY_NAME = 'TTMSQZ 3.0 ES15N · ES 15m Carter neighbourhood (60m squeeze-on verified)'
DESCRIPTION = ("The ES 15-minute Carter cell inside the same four-knob fence run #299 uses on 30-minute "
               "bars: enter next open on the squeeze fire in the momentum direction, exit on the first "
               "fading bar, only while the hourly squeeze is still on. The fence is inherited, not fitted.")
_AUGUR_MARKET = {"instrument": "ES", "timeframe": "15m"}

DEFAULT_PARAMS = {
    'kc_mult': {'default': 1.5, 'min': 1.25, 'max': 1.75, 'step': 0.25, 'type': 'float',
                'label': 'Keltner ATR multiplier',
                'tooltip': 'Inherited from the 30-minute file; 1.5 is the value the round-9 scan used.'},
    'stop_atr': {'default': 1.5, 'min': 1.5, 'max': 2.5, 'step': 0.5, 'type': 'float',
                 'label': 'Protective stop, ATR multiples',
                 'tooltip': 'Inherited set; 1.5 is the value the round-9 scan used.'},
    'eod_cutoff': {'default': 1, 'min': 1, 'max': 5, 'step': 2, 'type': 'int',
                   'label': 'No entries inside the last N bars of the session',
                   'tooltip': 'Inherited set; 1 is the value the round-9 scan used.'},
    'gate_len': {'default': 20, 'min': 16, 'max': 24, 'step': 4, 'type': 'int',
                 'label': 'Verification squeeze length',
                 'tooltip': 'Length of the hourly squeeze that verifies each entry.'},
}

PARAM_GRID_PRESETS = {
    "Short  (ES 15m Carter neighbourhood)": {
        'kc_mult': [1.25, 1.5, 1.75], 'stop_atr': [1.5, 2.0, 2.5],
        'eod_cutoff': [1, 3, 5], 'gate_len': [16, 20, 24]},
}
