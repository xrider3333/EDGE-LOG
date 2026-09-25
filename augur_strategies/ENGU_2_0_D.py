"""ENGU 2.0 D -- automated version of the owner's discretionary ENGD setup: the exact short
mirror of ENGU 2.0 (an engulfing-down candle breaking a short local low while staying
inside today's regular-session range, after a pullback).

Pre-registered: SETUPS_PREREG.md (sections 3-6), committed before any result for this file
existed. Loads ENGU_2_0.py's `_core` by file path (the ENGUQ_1M_ETH_CD5_1_0.py sibling-
loading idiom -- augur_strategies/ has no __init__.py, so this cannot be a normal package
import) and runs it through augur_engine.setup_kit.mirror_short: prices are mapped
(o,h,l,c) -> (-o,-l,-h,-c), the SAME long rule and walk run on that inverted tape, and the
resulting points P&L is already the correct short P&L -- mirror_short only flips the entry
price back positive and tags side=-1. Same knob names, same defaults, same rule, opposite
side.

Family: `ENGU` (CLAUDE.md vocabulary -- the pre-ENGU-Q legacy family name), same as
ENGU_2_0.py; NOT a new family. This file does NOT set `_AUGUR_PARENT`.
"""
import importlib.util as _ilu
import os as _os

from augur_engine import setup_kit as SK

_SRC = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "ENGU_2_0.py")
_spec = _ilu.spec_from_file_location("_engu_2_0_base_for_d", _SRC)
_base = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_base)

STRATEGY_NAME = "ENGU 2.0 D"
DESCRIPTION = ("Automated version of the owner's discretionary ENGD setup: the exact "
              "short mirror of ENGU 2.0 -- an engulfing-down candle breaking a short "
              "local low while staying inside today's regular-session range, after a "
              "pullback. Pre-registered test plan in SETUPS_PREREG.md; no results assumed "
              "yet. Short only, exact price-inversion of ENGU_2_0.py.")
VERSION = "2.0"
DIRECTION = "SHORT"
TIMEFRAME = "1m"

DEFAULT_PARAMS = _base.DEFAULT_PARAMS
PARAM_GRID_PRESETS = _base.PARAM_GRID_PRESETS


def run_backtest(opens, highs, lows, closes, volumes=None, day_id=None, index=None,
                 exit_mode='ride', be_R=1.0, trail_bars=15, target_R=2.0,
                 stop_buf_atr=0.0, min_risk_atr=0.0, end_min=360, vol_mult=0.0,
                 body_frac=0.6, body_mult=2.0, eng_n=1, pb_atr=0.0,
                 return_trades=False, _stop_event=None, _pause_event=None, **_ignore):
    if index is None or len(index) != len(closes):
        raise ValueError("ENGU_2_0_D: run_backtest needs `index` (bar timestamps) matching "
                         "the price arrays' length")
    if vol_mult and float(vol_mult) > 0 and volumes is None:
        raise ValueError("ENGU_2_0_D: vol_mult>0 needs `volumes`")
    trades = SK.mirror_short(_base._core, opens, highs, lows, closes, volumes, index,
                             exit_mode=exit_mode, be_R=be_R, trail_bars=trail_bars,
                             target_R=target_R, stop_buf_atr=stop_buf_atr,
                             min_risk_atr=min_risk_atr, end_min=end_min, vol_mult=vol_mult,
                             body_frac=body_frac, body_mult=body_mult, eng_n=eng_n,
                             pb_atr=pb_atr)
    return SK.stats(trades, return_trades=return_trades)
