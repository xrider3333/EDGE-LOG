"""
ORB 3.5 — RUN #228 CHAMPION, PINNED (head-to-head harness vs run #221).

Runs #228 and #221 both certified PASS 7/7, but on DIFFERENT windows: #228's lockbox is
2025-08-13 -> 2026-08-13, #221's is 2025-07-16 -> 2026-07-16. Their lockbox dollars are
therefore not comparable, and the lockbox is the whole point of the comparison. This file
nails every #228 knob shut so an Auto-Validate explores a SINGLE point and crowns #228's
config by construction — re-run it with date_to 2026-07-16 and the two runs share one
window, one lockbox, one verdict basis.

    or_bars 2 · First-candle dir · stop 1.25 · buf 0.0 · close_confirm ON
    partial 1.5R · trail 6 · target 3.5R · atr 0.5 · v-pace 0.7 · gap 0.25
    orw 0.0 · entry cutoff 0 (all day) · flat EOD · holidays on

LIVE-LEGAL BY CONSTRUCTION. Every filter input closes strictly before the entry decision:
close_confirm ON means the entry is a bar-close decision, not an intrabar touch, so there
is no unknowable same-bar quantity anywhere in the chain — the failure mode that voided
the whole #125 family (see ORB.md). v-pace reads only bars BEFORE the entry bar; gap_min
is fixed at 09:30; atr_filter is trailing-only.
"""
import importlib.util as _ilu
import os as _os

_SRC = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "ORB_3_5.py")
_spec = _ilu.spec_from_file_location("_orb35_base_c228", _SRC)
_base = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_base)

STRATEGY_NAME = 'ORB 3.5 · run 228 champion, pinned'
DESCRIPTION   = ("Run #228's crowned config with every knob nailed shut — OR 2, first-candle "
                 "direction, close-confirmed entry, stop 1.25, partial 1.5R, trail 6, target "
                 "3.5R, v-pace 0.7, gap 0.25, ATR 0.5. Auto-Validate this on #221's window "
                 "(date_to 2026-07-16) for a like-for-like lockbox head-to-head.")

_AUGUR_MARKET = {"instrument": "NQ", "timeframe": "5m"}
_AUGUR_PARENT = "ORB_3_5.py"

# PINNED: min == max on every numeric knob, one option on every categorical (bools need an
#   explicit single-entry "options" list — a plain bool default is ignored by the validate
#   path and silently falls back to the parent's default).
DEFAULT_PARAMS = {
    "or_bars":        {"default": 2,    "min": 2,    "max": 2,    "step": 1,    "type": "int",   "label": "Opening range (bars) — PINNED"},
    "trade_mode":     {"default": "First-candle dir", "type": "str", "options": ["First-candle dir"],            "label": "Direction — PINNED"},
    "stop_frac":      {"default": 1.25, "min": 1.25, "max": 1.25, "step": 0.25, "type": "float", "label": "Stop (× range width) — PINNED"},
    "breakout_buf":   {"default": 0.0,  "min": 0.0,  "max": 0.0,  "step": 0.05, "type": "float", "label": "Breakout buffer — PINNED"},
    "close_confirm":  {"default": True,  "type": "bool", "options": [True],                                      "label": "Confirm at bar close — PINNED ON (this is what makes it live-legal)"},
    "partial_exit_R": {"default": 1.5,  "min": 1.5,  "max": 1.5,  "step": 0.5,  "type": "float", "label": "Partial exit (× risk) — PINNED"},
    "trail_bars":     {"default": 6,    "min": 6,    "max": 6,    "step": 1,    "type": "int",   "label": "Trailing stop (bars) — PINNED"},
    "target_R":       {"default": 3.5,  "min": 3.5,  "max": 3.5,  "step": 0.5,  "type": "float", "label": "Target (× risk) — PINNED"},
    "atr_filter":     {"default": 0.5,  "min": 0.5,  "max": 0.5,  "step": 0.1,  "type": "float", "label": "Vol-regime filter (trailing) — PINNED"},
    "vpace_filter":   {"default": 0.7,  "min": 0.7,  "max": 0.7,  "step": 0.1,  "type": "float", "label": "Volume-pace gate (pre-fill bars only) — PINNED"},
    "gap_min":        {"default": 0.25, "min": 0.25, "max": 0.25, "step": 0.05, "type": "float", "label": "Min overnight gap (trailing-ATR units) — PINNED"},
    "orw_min":        {"default": 0.0,  "min": 0.0,  "max": 0.0,  "step": 0.1,  "type": "float", "label": "OR-width gate — PINNED off"},
    "entry_cutoff":   {"default": 0,    "min": 0,    "max": 0,    "step": 2,    "type": "int",   "label": "Entry window — PINNED off (all day)"},
    "flat_eod":       {"default": True,  "type": "bool", "options": [True],                                      "label": "Flat at the close — PINNED on"},
    "skip_holidays":  {"default": False, "type": "bool", "options": [False],                                     "label": "Skip holidays — PINNED off"},
}

# arm math is ORB_3_5's, unchanged — this file only narrows the search space to one point.
run_backtest = _base.run_backtest
