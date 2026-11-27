# AUGUR-SOURCE: claude-review
"""
NOISE 1.8 CT304H_FTL -- run #555 (NOISE_1_8_CT304H_FT.py) with the LONG BAND WIDTH opened. Board test 122 (2026-11-27).
Prereg: C:/EdgeLog/manager/prereg/PREREG_noise_v2_longband_2026-11-27.md (locked before the validate is queued).

WHY (owner 11-26 "find a NOISE that beats #555"; owner 11-27 "yes validate it")
  Round 4 of the NOISE v2 hunt: a wider long band (0.875 x noise instead of #304's frozen 0.75) kept #555's $/yr and cut
  the worst drawdown ($14.1k vs $21.1k). It is a HINDSIGHT pick from a 12-cell grid, wins 5 of 8 folds, and the whole
  drawdown cut sits in one episode (March-June 2025). This file lets the walk-forward choose it or not.

KNOBS
  gate_len / gate_ratio / tilt_mult   #555's own fenced 27 cells, unchanged.
  band_mult_long   0.75 / 0.875 / 1.0   long-side band width in units of the noise estimate. 0.75 = run #555 exactly.
                                         Everything else in #304's frozen core is untouched (short band stays 1.5).

NO LOOK-AHEAD
  The band is the core's own a-priori band (noise estimate from prior sessions); only its long-side multiplier changes.
  Cost: s-sized trade = s*raw - (s-1)*0.533, the engine subtracts cost once (the parent's convention, unchanged).
"""
import importlib.util as _ilu
import os as _os

_HERE = _os.path.dirname(_os.path.abspath(__file__))
_sp = _ilu.spec_from_file_location("_noise_ft_for_ftl", _os.path.join(_HERE, "NOISE_1_8_CT304H_FT.py"))
_ft = _ilu.module_from_spec(_sp)
_sp.loader.exec_module(_ft)                                           # run #555 (its own private copy of CT304H)

STRATEGY_NAME = "NOISE 1.8 #555 + long band width opened"
DESCRIPTION = ("Run #555 (NOISE #422 x frozen v12 fixed tilts) with the long-side band multiplier opened to "
               "0.75 / 0.875 / 1.0. 0.75 = #555 exactly.")
_AUGUR_MARKET = {"instrument": "NQ", "timeframe": "5m"}
_AUGUR_PARENT = "NOISE_1_8_CT304H_FT.py"
REQUIRED_LOOKBACK_SESSIONS = _ft.REQUIRED_LOOKBACK_SESSIONS
_COST_PTS = _ft._COST_PTS
_BML = [0.75, 0.875, 1.0]

DEFAULT_PARAMS = dict(_ft.DEFAULT_PARAMS)
DEFAULT_PARAMS.update({
    "band_mult_long": {"default": 0.75, "min": 0.75, "max": 1.0, "step": 0.125, "type": "float",
                       "label": "Long band width (x noise)",
                       "tooltip": "0.75 = run #555 exactly. Wider = fewer, later long entries."},
})
_ADMISSIBLE = dict(_ft._ADMISSIBLE, band_mult_long=list(_BML))
PARAM_GRID_PRESETS = {"Short  (#555's 27 cells x long band 0.75/0.875/1.0)": dict(_ADMISSIBLE)}


def run_backtest(opens, highs, lows, closes, volumes=None, day_id=None, index=None,
                 gate_len=20, gate_ratio=1.0, tilt_mult=1.5, band_mult_long=0.75,
                 return_trades=False, return_levels=False, **kw):
    b = float(band_mult_long)
    if not any(abs(b - v) < 1e-9 for v in _BML):
        return None                                                   # outside the pre-registered set: refused
    held = _ft._p._FROZEN                                             # CT304H's frozen #304 core (this file's copy)
    _ft._p._FROZEN = dict(held, band_mult_long=b)
    try:
        return _ft.run_backtest(opens, highs, lows, closes, volumes=volumes, day_id=day_id, index=index,
                                gate_len=gate_len, gate_ratio=gate_ratio, tilt_mult=tilt_mult,
                                return_trades=return_trades, return_levels=return_levels, **kw)
    finally:
        _ft._p._FROZEN = held
