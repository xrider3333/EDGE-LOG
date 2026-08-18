"""
NOISE 1.1 SBA -- skip BOTH sides after a weak close, PINNED.

The stricter sibling of SBS. On any day whose PRIOR day closed in the bottom 20%
of its own range, this file takes NO trades at all -- long or short -- instead of
only suppressing the shorts. It also cleared the campaign bar, but it gives up the
long trades on those days, and the long side is where NOISE makes its money.

WHAT THIS FILE IS: a PINNED single-config fork of NOISE_1_0.py. Every knob is
locked to one value, so running it through Auto-Validate validates exactly ONE
configuration -- the run-#231 champion core plus this one filter. Nothing is searched. This is
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
    SBA      n=3991  net=$308,783.01  PF 1.379  maxDD -$15,933.92 MAR 19.38 
             2010-17 +$8,115

  CONFIRMATORY ONE-LOOK, full window 2010-06-07 -> 2026-08-12 (never used for
  selection):
    SBA      n=4404  net=$366,855.02  PF 1.337  maxDD -$29,041.01 MAR 12.63 
             LB slice n=413 +$58,072 PF 1.212

ATTRIBUTION: blocking both sides cuts the drawdown hardest of the four ($19,482 -> $15,934, the
best MAR in the campaign) but it also throws away profitable longs, so it finishes
$11,747 behind the short-only version on net.

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
_spec = _ilu.spec_from_file_location("_noise10_base_sba", _SRC)
_base = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_base)

STRATEGY_NAME = 'NOISE 1.1 - core + skip all trades after weak close (pinned)'
DESCRIPTION   = ("The #231 NOISE champion core with one filter: no trades at all the day "
                 "after a close in the bottom 20% of the prior day range. Best "
                 "drawdown and best MAR of the campaign, but less net than the "
                 "short-only version.")

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
    "daytype_mode":    {"default": "skip_bot_all", "type": "str", "options": ["skip_bot_all"],                    "label": "Prior-day close-position filter - PINNED to skip_bot_all"},
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
