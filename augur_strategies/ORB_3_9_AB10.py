"""
ORB 3.9 — PINNED CANDIDATE AB10: crown #234 + arm breakeven after 10 bars (50 minutes).

Round-4 exit-management sweep (tools/orb_hunt4.py, 2026-08-22). Arming the breakeven by
TIME as well as by R re-shapes the crown into a defensive variant: roughly half the
drawdown and half the worst rolling year, for about a third less money.

    offline: net $251,699 · maxDD $20,800 · net/DD 12.10 · LB $91,267 · roll12 win 74.9%, worst -$9,210
    (crown #234: $389,874 · $29,142 · 13.38 · $88,943 · 72.7%, -$22,050)

It cleared the round-3 PRE-REGISTERED gate (beat #234 on rolling-12 win rate AND worst
rolling year AND lockbox), which is what earns a validation slot. CAUTION, stated up
front: the bar-count neighbourhood is SPIKY (11 and 13 bars fail the gate while 10 and
12 pass), and this program has killed three spike-picks before. The WF verdict decides
whether the risk-shape claim holds; the crown does not move on an offline table either
way, and net -31% means this is a RISK lever, not a crown challenger.

LIVE-LEGAL: the bar-count trigger arms on a finished bar and acts from the next bar,
exactly like the R trigger. Nothing on any fill bar is read before it exists.
"""
import importlib.util as _ilu
import os as _os

_SRC = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "ORB_3_9.py")
_spec = _ilu.spec_from_file_location("_orb39_ab10", _SRC)
_base = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_base)

STRATEGY_NAME = 'ORB 3.9 · candidate AB10 — breakeven armed at 10 bars, pinned'
DESCRIPTION   = ("The #234 crown with breakeven ALSO armed once the trade is 10 bars "
                 "(50 minutes) old. A defensive re-shape: about half the drawdown and "
                 "worst-year for about a third less money. Judge on WF folds vs #234's 7/8.")

_AUGUR_MARKET = {"instrument": "NQ", "timeframe": "5m"}
_AUGUR_PARENT = "ORB_3_9.py"

# PINNED: min == max on every numeric knob, one option on every categorical. Bools need
#   an explicit single-entry "options" list — a plain bool default is ignored by the
#   validate path (this voided runs 206-208).
DEFAULT_PARAMS = {
    "or_bars":        {"default": 2,    "min": 2,    "max": 2,    "step": 1,    "type": "int",   "label": "Opening range (bars) — PINNED"},
    "trade_mode":     {"default": "First-candle dir", "type": "str", "options": ["First-candle dir"],            "label": "Direction — PINNED"},
    "stop_frac":      {"default": 2.0,  "min": 2.0,  "max": 2.0,  "step": 0.25, "type": "float", "label": "Stop (× range width) — PINNED"},
    "breakout_buf":   {"default": 0.25, "min": 0.25, "max": 0.25, "step": 0.05, "type": "float", "label": "Breakout buffer — PINNED"},
    "close_confirm":  {"default": True,  "type": "bool", "options": [True],                                      "label": "Confirm at bar close — PINNED ON (this is what makes it live-legal)"},
    "partial_exit_R": {"default": 0.0,  "min": 0.0,  "max": 0.0,  "step": 0.5,  "type": "float", "label": "Partial exit — PINNED OFF (the simplification)"},
    "trail_bars":     {"default": 0,    "min": 0,    "max": 0,    "step": 1,    "type": "int",   "label": "Trailing stop — PINNED OFF (the simplification)"},
    "be_after_R":     {"default": 1.0,  "min": 1.0,  "max": 1.0,  "step": 0.1,  "type": "float", "label": "Breakeven after (× risk) — PINNED at the plateau center"},
    "target_R":       {"default": 5.5,  "min": 5.5,  "max": 5.5,  "step": 0.5,  "type": "float", "label": "Target (× risk) — PINNED"},
    "atr_filter":     {"default": 0.7,  "min": 0.7,  "max": 0.7,  "step": 0.1,  "type": "float", "label": "Vol-regime filter (trailing) — PINNED"},
    "vpace_filter":   {"default": 0.7,  "min": 0.7,  "max": 0.7,  "step": 0.1,  "type": "float", "label": "Volume-pace gate (pre-fill bars only) — PINNED"},
    "reenter_stop":   {"default": 0,    "min": 0,    "max": 0,    "step": 1,    "type": "int",   "label": "Re-enter after stop — PINNED OFF"},
    "be_after_bars":  {"default": 10,   "min": 10,   "max": 10,   "step": 2,    "type": "int",   "label": "Arm breakeven after N bars — PINNED (the lever under test)"},
    "be_lock_frac":   {"default": 0.0,  "min": 0.0,  "max": 0.0,  "step": 0.05, "type": "float", "label": "Breakeven lock — PINNED OFF"},
    "flat_eod":       {"default": True,  "type": "bool", "options": [True],                                      "label": "Flat at the close — PINNED on"},
    "skip_holidays":  {"default": True,  "type": "bool", "options": [True],                                      "label": "Skip holidays — PINNED on"},
}

# arm math is ORB_3_9's, unchanged — this file only narrows the search space to one point.
run_backtest = _base.run_backtest
