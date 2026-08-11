"""
OPENING RANGE BREAKOUT 3.1 — RUN #125 CONFIG, CLOSE-CONFIRMED — the LIVE-LEGAL twin (NinjaTrader match).

Every knob is nailed to the certified #125 deployable, so an Auto-Validate on this file
explores a SINGLE point and the champion it crowns IS #125 — no search, no drift. That
is the whole purpose: run_validate has no "use these params" argument, so pinning the
file is the only way to get the full validate report (walk-forward folds, lockbox,
blotter, OHLC) for one exact configuration.

    or_bars 1 · Both · stop 0.75 · vol 1.25 · buf 0.0 · partial 0.0 · trail 5
    atr 0.0 · target 0.0 · flat EOD · close_confirm ON

Certified reference (whole history, NQ 5m RTH): n=4064 · $360,640.26 · PF 1.611 ·
DD −$9,351.60 (BACKTESTING_STACK.md).

THIS is the one a platform can reproduce. Same #125 knobs, but the entry decision
moves to the BAR CLOSE, where that bar's volume is legitimately known — so the volume
filter stops being look-ahead and the rule becomes implementable. Entry price is that
close instead of the breakout level, which costs some edge; that cost is the honest
price of the filter (tools/orb_live_legal_variants.py).

Use ORB_3_1_125.py for the paper-history figures, and THIS file when reconciling
against NinjaTrader, TradingView or any live/demo platform.
"""
import importlib.util as _ilu
import os as _os

_SRC = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "ORB_3_1.py")
_spec = _ilu.spec_from_file_location("_orb31_base_125c", _SRC)
_base = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_base)

STRATEGY_NAME = 'ORB 3.1 · run 125 config, close-confirmed (live-legal)'
DESCRIPTION   = ("#125's knobs with the entry decision moved to the BAR CLOSE, where the "
                 "volume filter is legitimately known — the live-legal form of the same rule. "
                 "Entry is the confirming bar's close, not the breakout level. This is the file "
                 "to reconcile against NinjaTrader or TradingView.")

_AUGUR_MARKET = {"instrument": "NQ", "timeframe": "5m"}
_AUGUR_PARENT = "ORB_3_1_125.py"

# PINNED: min == max on every numeric knob, one option on every categorical, so the
#   search space is a single point and the crowned config is #125 by construction.
DEFAULT_PARAMS = {
    "or_bars":        {"default": 1,    "min": 1,    "max": 1,    "step": 1,    "type": "int",   "label": "Opening range (bars) — PINNED"},
    "trade_mode":     {"default": "Both", "type": "str", "options": ["Both"],                     "label": "Direction — PINNED"},
    "stop_frac":      {"default": 0.75, "min": 0.75, "max": 0.75, "step": 0.25, "type": "float", "label": "Stop (× range width) — PINNED"},
    "vol_filter":     {"default": 1.25, "min": 1.25, "max": 1.25, "step": 0.25, "type": "float", "label": "Volume filter — PINNED (honest here: the bar is over)"},
    "breakout_buf":   {"default": 0.0,  "min": 0.0,  "max": 0.0,  "step": 0.05, "type": "float", "label": "Breakout buffer — PINNED"},
    "close_confirm":  {"default": True, "type": "bool", "options": [True],                                           "label": "Confirm at bar close — PINNED ON (this is what makes it live-legal)"},
    "partial_exit_R": {"default": 0.0,  "min": 0.0,  "max": 0.0,  "step": 0.5,  "type": "float", "label": "Partial exit (× risk) — PINNED off (single lot)"},
    "trail_bars":     {"default": 5,    "min": 5,    "max": 5,    "step": 1,    "type": "int",   "label": "Trailing stop (bars) — PINNED"},
    "atr_filter":     {"default": 0.0,  "min": 0.0,  "max": 0.0,  "step": 0.1,  "type": "float", "label": "Vol-regime filter — PINNED off"},
    "target_R":       {"default": 0.0,  "min": 0.0,  "max": 0.0,  "step": 0.5,  "type": "float", "label": "Target (× risk) — PINNED off (ride to close)"},
    "flat_eod":       {"default": True,  "type": "bool", "options": [True],                                          "label": "Flat at the close — PINNED on"},
    "skip_holidays":  {"default": False, "type": "bool", "options": [False],                                          "label": "Skip holidays — PINNED off"},
}

# arm math is ORB_3_1's, unchanged — this file only narrows the search space.
run_backtest = _base.run_backtest
