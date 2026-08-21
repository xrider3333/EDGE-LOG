"""
ORB 3.6 — PINNED CANDIDATE E1B08: run 257 entry with breakeven 0.8.

The open question from round 3: run 257 wins every walk-forward measure but carries
more drawdown than crown #234. On 257's base, breakeven 0.8 reads net/DD 13.80 with
drawdown back at the crown's level — potentially both halves of the debate at once.

Offline (NQ 5m RTH no-adj, 0.533 pts/RT, 1 contract, run #230's window):
    full net $409,294  ·  maxDD $29,667  ·  lockbox $87,172
    (crown #234: $389,874 · $29,142 · $88,943)

Owner 2026-08-19: validate alongside an OPEN Auto-Validate of ORB_3_6.py (the
ML-features run). Judge on WF folds vs #234's 7/8 / wfe 4.649, never the offline net.
The shared lockbox is heavily reused — encouraging, not confirmatory. REGIME CAVEAT:
money is post-2018.

LIVE-LEGAL BY CONSTRUCTION: entry at a finished bar's close; BE armed on a finished
bar's close, acting next bar; stop-first + gap-through fills; every gate reads only
prior bars.
"""
import importlib.util as _ilu
import os as _os

_SRC = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "ORB_3_6.py")
_spec = _ilu.spec_from_file_location("_orb36_base_e1b08", _SRC)
_base = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_base)

STRATEGY_NAME = 'ORB 3.6 · candidate E1B08 — 257 entry + breakeven 0.8, pinned'
DESCRIPTION   = ("Run 257's re-opened entry (atr 0.5, buffer 0.30, stop 2.50) with the "
                 "breakeven moved to 0.8R. Offline it keeps 257's money with the crown's "
                 "drawdown. Judge on WF folds vs #234's 7/8, never the offline net.")

_AUGUR_MARKET = {"instrument": "NQ", "timeframe": "5m"}
_AUGUR_PARENT = "ORB_3_6.py"

# PINNED: min == max on every numeric knob, one option on every categorical. Bools need
#   an explicit single-entry "options" list — a plain bool default is ignored by the
#   validate path (this voided runs 206-208).
DEFAULT_PARAMS = {
    "or_bars":        {"default": 2,    "min": 2,    "max": 2,    "step": 1,    "type": "int",   "label": "Opening range (bars) — PINNED"},
    "trade_mode":     {"default": "First-candle dir", "type": "str", "options": ["First-candle dir"],            "label": "Direction — PINNED"},
    "stop_frac":      {"default": 2.50,  "min": 2.50,  "max": 2.50,  "step": 0.25, "type": "float", "label": "Stop (× range width) — PINNED"},
    "breakout_buf":   {"default": 0.30, "min": 0.30, "max": 0.30, "step": 0.05, "type": "float", "label": "Breakout buffer — PINNED"},
    "close_confirm":  {"default": True,  "type": "bool", "options": [True],                                      "label": "Confirm at bar close — PINNED ON (this is what makes it live-legal)"},
    "partial_exit_R": {"default": 0.0,  "min": 0.0,  "max": 0.0,  "step": 0.5,  "type": "float", "label": "Partial exit — PINNED OFF (the simplification)"},
    "trail_bars":     {"default": 0,    "min": 0,    "max": 0,    "step": 1,    "type": "int",   "label": "Trailing stop — PINNED OFF (the simplification)"},
    "be_after_R":     {"default": 0.8,  "min": 0.8,  "max": 0.8,  "step": 0.1,  "type": "float", "label": "Breakeven after (× risk) — PINNED at the plateau center"},
    "target_R":       {"default": 5.5,  "min": 5.5,  "max": 5.5,  "step": 0.5,  "type": "float", "label": "Target (× risk) — PINNED"},
    "atr_filter":     {"default": 0.5,  "min": 0.5,  "max": 0.5,  "step": 0.1,  "type": "float", "label": "Vol-regime filter (trailing) — PINNED"},
    "vpace_filter":   {"default": 0.7,  "min": 0.7,  "max": 0.7,  "step": 0.1,  "type": "float", "label": "Volume-pace gate (pre-fill bars only) — PINNED"},
    "flat_eod":       {"default": True,  "type": "bool", "options": [True],                                      "label": "Flat at the close — PINNED on"},
    "skip_holidays":  {"default": True,  "type": "bool", "options": [True],                                      "label": "Skip holidays — PINNED on"},
}

# arm math is ORB_3_6's, unchanged — this file only narrows the search space to one point.
run_backtest = _base.run_backtest
