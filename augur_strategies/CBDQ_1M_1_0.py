"""CBD-Q 1m 1.0 -- automated version of the owner's discretionary CBD setup: the exact
short mirror of CBU-Q (a new regular-session LOW below a premarket or prior-day low).

Pre-registered: SETUPS_PREREG.md (sections 3-6), committed before any result for this file
existed. Loads CBUQ_1M_1_0.py's `_core` by file path (the ENGUQ_1M_ETH_CD5_1_0.py sibling-
loading idiom -- augur_strategies/ has no __init__.py, so this cannot be a normal package
import) and runs it through augur_engine.setup_kit.mirror_short: prices are mapped
(o,h,l,c) -> (-o,-l,-h,-c), the SAME long rule and walk run on that inverted tape, and the
resulting points P&L is already the correct short P&L (exit2-entry2 on the inverted tape
equals real_entry-real_exit) -- mirror_short only flips the entry price back positive and
tags side=-1. Same knob names, same defaults, same rule, opposite side: CBD fires on a
close below the premarket/prior-day LOW at a new regular-session low.

This file does NOT set `_AUGUR_PARENT` -- that marks a fenced single-hypothesis variant of
an existing crown, which this is not; it is a first-class member of the new CBU-Q family
(SETUPS_PREREG.md section 1), registered alongside CBUQ_1M_1_0.py and EBUQ_1M_1_0.py.
"""
import importlib.util as _ilu
import os as _os

from augur_engine import setup_kit as SK

_SRC = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "CBUQ_1M_1_0.py")
_spec = _ilu.spec_from_file_location("_cbuq_1m_1_0_base_for_cbdq", _SRC)
_base = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_base)

STRATEGY_NAME = "CBD-Q 1m 1.0"
DESCRIPTION = ("Automated version of the owner's discretionary CBD setup: the exact short "
              "mirror of CBU-Q -- the session's close breaks down to a new regular-session "
              "low below a premarket or prior-day low. Pre-registered test plan in "
              "SETUPS_PREREG.md; no results assumed yet. Short only, exact price-inversion "
              "of CBUQ_1M_1_0.py.")
VERSION = "1.0"
DIRECTION = "SHORT"
TIMEFRAME = "1m"

DEFAULT_PARAMS = _base.DEFAULT_PARAMS
PARAM_GRID_PRESETS = _base.PARAM_GRID_PRESETS


def run_backtest(opens, highs, lows, closes, volumes=None, day_id=None, index=None,
                 exit_mode='ride', be_R=1.0, trail_bars=15, target_R=2.0,
                 stop_buf_atr=0.0, min_risk_atr=0.0, end_min=120, vol_mult=0.0,
                 level_mode='both', first_bar='allow', base_bars=0, base_k=2.0,
                 return_trades=False, _stop_event=None, _pause_event=None, **_ignore):
    if index is None or len(index) != len(closes):
        raise ValueError("CBDQ_1M_1_0: run_backtest needs `index` (bar timestamps) matching "
                         "the price arrays' length")
    if vol_mult and float(vol_mult) > 0 and volumes is None:
        raise ValueError("CBDQ_1M_1_0: vol_mult>0 needs `volumes`")
    trades = SK.mirror_short(_base._core, opens, highs, lows, closes, volumes, index,
                             exit_mode=exit_mode, be_R=be_R, trail_bars=trail_bars,
                             target_R=target_R, stop_buf_atr=stop_buf_atr,
                             min_risk_atr=min_risk_atr, end_min=end_min, vol_mult=vol_mult,
                             level_mode=level_mode, first_bar=first_bar, base_bars=base_bars,
                             base_k=base_k)
    return SK.stats(trades, return_trades=return_trades)
