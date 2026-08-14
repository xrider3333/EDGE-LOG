"""
OPENING RANGE BREAKOUT 3.1 — RUN #125 CONFIG, PINNED (NinjaTrader match harness).

Every knob is nailed to the certified #125 deployable, so an Auto-Validate on this file
explores a SINGLE point and the champion it crowns IS #125 — no search, no drift. That
is the whole purpose: run_validate has no "use these params" argument, so pinning the
file is the only way to get the full validate report (walk-forward folds, lockbox,
blotter, OHLC) for one exact configuration.

    or_bars 1 · Both · stop 0.75 · vol 1.25 · buf 0.0 · partial 0.0 · trail 5
    atr 0.0 · target 0.0 · flat EOD · close_confirm OFF

Certified reference (whole history, NQ 5m RTH): n=4064 · $360,640.26 · PF 1.611 ·
DD −$9,351.60 (BACKTESTING_STACK.md).

⚠ NOT LIVE-LEGAL AS WRITTEN. #125 filters a breakout on the breakout bar's FINISHED
volume while entering on a resting stop INTRABAR. Those cannot both be true in real
time — the stop fills before the bar closes, so its volume is unknowable at the entry
decision. tools/orb_live_emulation_cost.py prices the naive workaround (enter, then
eject if the bar turns out thin) and it is fatal: ~97% of fills become ejections, each
paying a round turn. If you are reconciling against a live or demo platform, expect
this file NOT to match — see ORB_3_1_125C.py for the close-confirmed variant, which is
live-legal and IS reproducible on a platform.
"""
import importlib.util as _ilu
import os as _os

_SRC = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "ORB_3_1.py")
_spec = _ilu.spec_from_file_location("_orb31_base_125", _SRC)
_base = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_base)

STRATEGY_NAME = 'ORB 3.1 · run 125 config, pinned'
DESCRIPTION   = ("The certified #125 deployable with every knob nailed shut — OR 1, both "
                 "sides, stop 0.75, vol 1.25, ride to close, flat EOD, 5-bar trailing stop. "
                 "Auto-Validate this to get #125's own report, folds, lockbox and blotter "
                 "with no search. NOT live-legal: the volume filter reads the breakout bar's "
                 "finished volume while entering intrabar.")

_AUGUR_MARKET = {"instrument": "NQ", "timeframe": "5m"}
_AUGUR_PARENT = "ORB_3_1.py"

# PINNED: min == max on every numeric knob, one option on every categorical, so the
#   search space is a single point and the crowned config is #125 by construction.
DEFAULT_PARAMS = {
    "or_bars":        {"default": 1,    "min": 1,    "max": 1,    "step": 1,    "type": "int",   "label": "Opening range (bars) — PINNED"},
    "trade_mode":     {"default": "Both", "type": "str", "options": ["Both"],                     "label": "Direction — PINNED"},
    "stop_frac":      {"default": 0.75, "min": 0.75, "max": 0.75, "step": 0.25, "type": "float", "label": "Stop (× range width) — PINNED"},
    "vol_filter":     {"default": 1.25, "min": 1.25, "max": 1.25, "step": 0.25, "type": "float", "label": "Volume filter — PINNED (not live-legal)"},
    "breakout_buf":   {"default": 0.0,  "min": 0.0,  "max": 0.0,  "step": 0.05, "type": "float", "label": "Breakout buffer — PINNED"},
    "close_confirm":  {"default": False, "type": "bool", "options": [False],                                          "label": "Confirm at bar close — PINNED OFF (this is what makes it not live-legal)"},
    "partial_exit_R": {"default": 0.0,  "min": 0.0,  "max": 0.0,  "step": 0.5,  "type": "float", "label": "Partial exit (× risk) — PINNED off (single lot)"},
    "trail_bars":     {"default": 5,    "min": 5,    "max": 5,    "step": 1,    "type": "int",   "label": "Trailing stop (bars) — PINNED"},
    "atr_filter":     {"default": 0.0,  "min": 0.0,  "max": 0.0,  "step": 0.1,  "type": "float", "label": "Vol-regime filter — PINNED off"},
    "target_R":       {"default": 0.0,  "min": 0.0,  "max": 0.0,  "step": 0.5,  "type": "float", "label": "Target (× risk) — PINNED off (ride to close)"},
    "flat_eod":       {"default": True,  "type": "bool", "options": [True],                                          "label": "Flat at the close — PINNED on"},
    "skip_holidays":  {"default": False, "type": "bool", "options": [False],                                          "label": "Skip holidays — PINNED off"},
}

# arm math is ORB_3_1's, unchanged — this file only narrows the search space.
run_backtest = _base.run_backtest
