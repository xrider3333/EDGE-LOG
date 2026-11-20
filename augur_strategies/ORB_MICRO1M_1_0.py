"""
ORB MICRO1M 1.0 - the ORB #314 mechanism on NQ 1-MINUTE bars with a 5-minute (5-bar) opening range. Family ORB.

ORIGIN (w132 alpha hunt, lane ORB, 2026-11-20): W132_ALPHA.md leg RR_SCREEN1106_MICRO_OR_1m_5_bars_close_entry_market
("SCREEN1106 MICRO 1m close entry"), one of the 5 legs FRONTIER's 2016-19 prefilter kept, as a SWAP for ORB #314.
Harness: C:/EdgeLog/_anatomy_cache/t242_orb/w132r2/screen_r2.py, cell "MICRO-OR 1m 5 bars, close entry (market)"
(pre-WF original: C:/EdgeLog/_anatomy_cache/t242_orb/screen1106/screen.py). Leg CSV:
C:/EdgeLog/manager/reports/w132_orb_legs/RR_SCREEN1106_MICRO_OR_1m_5_bars_close_entry_market.csv.
Prereg C:/EdgeLog/manager/prereg/PREREG_orb_micro1m_validate_2026-11-20.md.

WHAT THIS IS
  ORB_3_6.py's core loop UNCHANGED (the #314 mechanism), run on the NQ 1m RTH no-adj master. The harness walk is that
  loop re-typed: first-candle direction, close-confirmed entry at the breaking bar's close beyond OR edge +/- buf x range,
  stop = stop_frac x range, breakeven armed on a bar CLOSE beyond be_after_R x risk (acts from the next bar), hard target
  target_R x risk, flat at the session's last bar; skip sessions < 70% of median length, skip sessions whose prior-5
  session range mean < atr_filter x prior-60 median, skip a break bar while the session's volume pace (bars BEFORE it)
  is below vpace_filter x the prior-20-session same-length prefix. No partial, no trail.
  Harness point = #314's champion knobs with or_bars 5 (1m) instead of 2 (5m):
      or_bars 5, stop_frac 2.5, breakout_buf 0.25, be_after_R 0.5, target_R 5.0, atr_filter 0.75, vpace_filter 0.8.
  DEFAULT_PARAMS defaults = that point; six knobs carry ranges around it so the 900-trial search maps the plateau.

NO LOOK-AHEAD: inherited from ORB_3_6 (entry on a finished bar's close; v-pace reads bars before the break bar and
prior sessions only; vol-regime and holiday gates use prior sessions / session length; BE arms on a close and acts next
bar; stop checked before target on every bar, gap-through fills). No ADJ levels are used (pure range/point logic on the
session's own bars), so no ROLL_SIGNAL is declared - same as ORB_3_6_R6.py.
"""
# AUGUR-SOURCE: claude-review
import importlib.util as _ilu
import os as _os

_SRC = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "ORB_3_6.py")
_spec = _ilu.spec_from_file_location("_orb36_micro1m", _SRC)
_base = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_base)

STRATEGY_NAME = "ORB MICRO1M 1.0 - #314 mechanism on NQ 1m, 5-minute opening range"
DESCRIPTION = ("ORB #314's legal close-confirm breakout (first-candle direction, breakeven after R, hard target, "
               "v-pace + vol-regime gates) on 1-minute bars with a 5-bar opening range. Defaults = the w132 harness "
               "leg SCREEN1106 MICRO 1m; six knobs ranged around it for the validate.")

_AUGUR_MARKET = {"instrument": "NQ", "timeframe": "1m"}
_AUGUR_PARENT = "ORB_3_6.py"

DEFAULT_PARAMS = {
    "or_bars":        {"default": 5,    "min": 3,    "max": 10,   "step": 1,    "type": "int",   "label": "Opening range (1m bars) - RANGE 3-10"},
    "trade_mode":     {"default": "First-candle dir", "type": "str", "options": ["First-candle dir"],            "label": "Direction - PINNED"},
    "stop_frac":      {"default": 2.5,  "min": 1.5,  "max": 3.0,  "step": 0.25, "type": "float", "label": "Stop (x range width) - RANGE 1.5-3.0"},
    "breakout_buf":   {"default": 0.25, "min": 0.25, "max": 0.25, "step": 0.05, "type": "float", "label": "Breakout buffer - PINNED"},
    "close_confirm":  {"default": True,  "type": "bool", "options": [True],                                      "label": "Confirm at bar close - PINNED ON (live-legal)"},
    "partial_exit_R": {"default": 0.0,  "min": 0.0,  "max": 0.0,  "step": 0.5,  "type": "float", "label": "Partial exit - PINNED OFF"},
    "trail_bars":     {"default": 0,    "min": 0,    "max": 0,    "step": 1,    "type": "int",   "label": "Trailing stop - PINNED OFF"},
    "be_after_R":     {"default": 0.5,  "min": 0.25, "max": 1.0,  "step": 0.25, "type": "float", "label": "Breakeven after (x risk) - RANGE 0.25-1.0"},
    "target_R":       {"default": 5.0,  "min": 3.0,  "max": 6.5,  "step": 0.5,  "type": "float", "label": "Target (x risk) - RANGE 3.0-6.5"},
    "atr_filter":     {"default": 0.75, "min": 0.65, "max": 0.85, "step": 0.05, "type": "float", "label": "Vol-regime filter - RANGE 0.65-0.85"},
    "vpace_filter":   {"default": 0.8,  "min": 0.7,  "max": 0.9,  "step": 0.05, "type": "float", "label": "Volume-pace gate - RANGE 0.70-0.90"},
    "flat_eod":       {"default": True,  "type": "bool", "options": [True],                                      "label": "Flat at the close - PINNED on"},
    "skip_holidays":  {"default": True,  "type": "bool", "options": [True],                                      "label": "Skip holidays - PINNED on"},
}

# the mechanism is ORB_3_6's, untouched - this file only sets the 1m market and the search space.
run_backtest = _base.run_backtest
