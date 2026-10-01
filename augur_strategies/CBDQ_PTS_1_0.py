"""CBD-Q PTS 1.0 -- SETUPS round 2, the exact short mirror of CBU-Q PTS 1.0: a red candle with the
largest body and the largest volume since today's HIGH, optionally filtered by a down-trend, the
first half hour, a triple 200-EMA test (close BELOW) or yesterday's low.

Pre-registered: SETUPS_PREREG_R2.md (section 3: "the short mirrors every comparison"). Loads
CBUQ_PTS_1_0.py's `_core` by file path (the CBDQ_1M_1_0.py sibling-loading idiom --
augur_strategies/ has no __init__.py) and runs it through augur_engine.setup_kit.mirror_short:
prices are mapped (o,h,l,c) -> (-o,-l,-h,-c), the SAME long rule and walk run on that inverted
tape, and the resulting points P&L is already the correct short P&L; mirror_short only flips
the entry price back positive and tags side=-1. Same knob names, same defaults, same rule,
opposite side. Volume is not inverted.

This file does NOT set `_AUGUR_PARENT` -- that marks a fenced single-hypothesis variant of an
existing crown, which this is not; it is a first-class member of the CBU-Q family.
"""
import importlib.util as _ilu
import os as _os

from augur_engine import setup_kit as SK

_SRC = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "CBUQ_PTS_1_0.py")
_spec = _ilu.spec_from_file_location("_cbuq_pts_1_0_base_for_cbdq", _SRC)
_base = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_base)

STRATEGY_NAME = "CBD-Q PTS 1.0"
DESCRIPTION = ("SETUPS round 2: the exact short mirror of CBU-Q PTS 1.0 -- a red candle with the "
              "largest body and the largest volume since today's high, optionally filtered by a "
              "down-trend, the first half hour, a triple 200-EMA test or yesterday's low. "
              "Pre-registered in SETUPS_PREREG_R2.md; no results assumed. Short only, exact "
              "price-inversion of CBUQ_PTS_1_0.py.")
VERSION = "1.0"
DIRECTION = "SHORT"
TIMEFRAME = "1m"

DEFAULT_PARAMS = _base.DEFAULT_PARAMS
PARAM_GRID_PRESETS = _base.PARAM_GRID_PRESETS


def _clear_caches():
    """Test hook: forget the long core's cached frames (and the kit's)."""
    _base._clear_caches()


def run_backtest(opens, highs, lows, closes, volumes=None, day_id=None, index=None,
                 filt='none', exit_mode='ride', min_win=5, stop_buf_atr=0.0,
                 return_trades=False, _stop_event=None, _pause_event=None, **_ignore):
    if index is None or len(index) != len(closes):
        raise ValueError("CBDQ_PTS_1_0: run_backtest needs `index` (bar timestamps) matching "
                         "the price arrays' length")
    if volumes is None:
        raise ValueError("CBDQ_PTS_1_0: the trigger needs `volumes`")
    trades = SK.mirror_short(_base._core, opens, highs, lows, closes, volumes, index,
                             filt=filt, exit_mode=exit_mode, min_win=min_win,
                             stop_buf_atr=stop_buf_atr)
    return SK.stats(trades, return_trades=return_trades)
