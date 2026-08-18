"""
NOISE 1.1 BASE -- the run-#231 champion core, PINNED (control run).

The CONTROL. This is the crowned NOISE champion configuration and nothing else:
no entry filter of any kind. It exists so the four filter variants can be compared
against a run produced by the SAME machinery over the SAME window, instead of
against run #231, whose search space was different (#231 let the auto-sampler roam
the whole parameter space, and it reports champion metrics on a different
convention). Read this run as the yardstick, not as new evidence.

WHAT THIS FILE IS: a PINNED single-config fork of NOISE_1_0.py. Every knob is
locked to one value, so running it through Auto-Validate validates exactly ONE
configuration -- the run-#231 champion core. Nothing is searched. This is
the answer to "does the champion core PLUS this one filter beat the champion core
alone, under identical machinery?"; a plain validate on NOISE_1_0.py cannot answer
it, because the auto-sampler wanders off the champion core once the filter knobs
are in the search space (that is what happened on run #237: it picked lookback 64
with a fixed stop and came out WEAK, PBO 0.599).

CHAMPION CORE (all five pinned files share it): lookback 44, upper band 0.75x,
lower band 1.5x (asymmetric), VWAP exit, bandwidth stop k=1.75, both sides, all
day, flat at the close, holidays traded.

LOCALLY MEASURED, 2026-08-17 variant campaign (harness tools/noise_variant_
research.py; parity vs the real engine re-proven to the cent on 2026-08-18 by
running THIS pinned file through augur_engine.engine.run_backtest). NQ 5m RTH,
source db_noadj_rth, cost_pts 0.533, multiplier 20, 1 contract.

  SELECTION WINDOW 2010-06-07 -> 2025-02-10 (run #231's optimize window; the ONLY
  window the pick was made on):
    BASE     n=5113  net=$277,123.31  PF 1.241  maxDD -$19,482.27 MAR 14.22 
             2010-17 +$11,524 . worst year 2010 -$2,278

  CONFIRMATORY ONE-LOOK, full window 2010-06-07 -> 2026-08-12 (never used for
  selection):
    BASE     n=5633  net=$335,980.83  PF 1.221  maxDD -$32,793.97 MAR 10.24 
             LB slice (2025-02-11 on) n=520 +$58,858 PF 1.159

ATTRIBUTION: nothing is added here. This is the baseline the other four are measured against.

LOCKBOX HONESTY: the NOISE family lockbox is SPENT. It has been read many times
(runs 202/203, the 2026-08-11 gate test, runs #225/#231, and the campaign's own
confirmatory one-look). Treat every lockbox number above, and every LB slice this
run produces, as CONFIRMATORY ONLY -- it can never promote NOISE. The walk-forward
folds and future forward data are the real judges.

CARRIED CAVEATS: (1) NOISE has never cleared its own pre-registered ES-transfer
promotion bar of PF >= 1.2 (the engine's generic transfer gate is a looser PF >= 1.0
check -- do not read a generic "transfer pass" as clearing NOISE's own bar).
(2) The production PAPER / NinjaTrader leg runs a DIFFERENT config (14 / 1.5 / 1.5 /
k=1.0), not this champion core. (3) Run #231's headline n/net convention differs
from the raw-engine path -- compare pinned runs to each other, and to #231 only on
the validate pipeline's own fields.
"""
import importlib.util as _ilu
import inspect as _inspect
import os as _os

_SRC = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "NOISE_1_0.py")
_spec = _ilu.spec_from_file_location("_noise10_base_base", _SRC)
_base = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_base)

STRATEGY_NAME = 'NOISE 1.1 - champion core, pinned (control)'
DESCRIPTION   = ("The crowned #231 NOISE config with every knob pinned and no entry filter. "
                 "The control run for the 2026-08-17 filter campaign - it exists so "
                 "the filter variants get a machinery-identical yardstick.")

_AUGUR_MARKET = {"instrument": "NQ", "timeframe": "5m"}
_AUGUR_PARENT = "NOISE_1_0.py"

# PINNED: min == max on every numeric knob, ONE option on every categorical. Bools
#   need an explicit single-entry "options" list -- a plain bool default is ignored
#   by the validate path (that is what voided runs 206-208).
DEFAULT_PARAMS = {
    "lookback":        {"default": 44,   "min": 44,   "max": 44,   "step": 1,    "type": "int",   "label": "Noise lookback (sessions) - PINNED"},
    "band_mult_long":  {"default": 0.75, "min": 0.75, "max": 0.75, "step": 0.25, "type": "float", "label": "Upper band width (x noise) - PINNED"},
    "band_mult_short": {"default": 1.5,  "min": 1.5,  "max": 1.5,  "step": 0.25, "type": "float", "label": "Lower band width (x noise) - PINNED (asymmetric)"},
    "exit_mode":       {"default": "vwap", "type": "str", "options": ["vwap"],                    "label": "Exit rule - PINNED to the VWAP cross"},
    "side":            {"default": "Both", "type": "str", "options": ["Both"],                    "label": "Direction - PINNED"},
    "window":          {"default": "all_day", "type": "str", "options": ["all_day"],              "label": "Entry window - PINNED"},
    "flat_eod":        {"default": True,  "type": "bool", "options": [True],                      "label": "Flat by session close - PINNED on"},
    "skip_holidays":   {"default": False, "type": "bool", "options": [False],                     "label": "Skip holiday half-days - PINNED off"},
    "stop_mode":       {"default": "bandwidth", "type": "str", "options": ["bandwidth"],          "label": "Protective stop - PINNED to bandwidth"},
    "stop_k":          {"default": 1.75, "min": 1.75, "max": 1.75, "step": 0.25, "type": "float", "label": "Stop size (x band excursion) - PINNED"},
    "confirm_bars":    {"default": 1,    "min": 1,    "max": 1,    "step": 1,    "type": "int",   "label": "Entry confirmation - PINNED off (one close outside the band enters)"},
    "daytype_mode":    {"default": "off", "type": "str", "options": ["off"],                    "label": "Prior-day close-position filter - PINNED off"},
    "daytype_lo":      {"default": 0.2,  "min": 0.2,  "max": 0.2,  "step": 0.05, "type": "float", "label": "Bottom close-position threshold - PINNED"},
    "daytype_hi":      {"default": 0.8,  "min": 0.8,  "max": 0.8,  "step": 0.05, "type": "float", "label": "Top close-position threshold - PINNED (unused here)"},
    "vol_skip_pct":    {"default": 0.0, "min": 0.0, "max": 0.0, "step": 1.0,  "type": "float", "label": "Skip entries above prior-day vol percentile - PINNED off"},
}

# One cell, so a grid job on this file is the same single config as the validate.
PARAM_GRID_PRESETS = {
    "Pinned (single config)": {k: [v["default"]] for k, v in DEFAULT_PARAMS.items()},
}

_PINNED = {k: v["default"] for k, v in DEFAULT_PARAMS.items()}
_BASE_ARGS = set(_inspect.signature(_base.run_backtest).parameters)


def run_backtest(opens, highs, lows, closes, **kw):
    """Entry/exit math is NOISE_1_0's, unchanged -- this file only narrows the
    search space to one point. Every pinned value is applied here too, so calling
    this file with NO params reproduces the pinned config exactly (the plain
    `run_backtest = _base.run_backtest` alias would silently fall back to
    NOISE_1_0's own signature defaults, which are a different config)."""
    p = dict(_PINNED)
    p.update({k: v for k, v in kw.items() if k in _BASE_ARGS})
    return _base.run_backtest(opens, highs, lows, closes, **p)
