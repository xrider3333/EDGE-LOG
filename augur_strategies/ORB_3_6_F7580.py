"""
ORB 3.6 — PINNED CANDIDATE F7580: the run #234 crown with both filters tightened, 0.75 / 0.80.

Round-5 filter sweep (tools/orb_hunt5.py, 2026-08-26). The crown carries
atr_filter=0.7 / vpace_filter=0.7 and had never been asked whether those are the right
numbers — they simply came along with the config that won. They are not free: the
vol-regime filter stood the paper leg down for ten straight sessions from 2026-08-13.

    offline: net $378,648 - maxDD $30,275 - LB $93,209 - roll12 win 76.0%, worst -$16,206
    (crown #234: $389,874 - $29,142 - $88,943 - 72.7%, -$22,050)

It cleared the PRE-REGISTERED gate carried unchanged from rounds 3-5 (beat #234 on
rolling-12 win rate AND worst rolling year AND lockbox at once), which is what earns a
validation slot and nothing more.

CAUTION, stated up front: THIRTEEN cells cleared this gate, all of them variations on
"filter harder". A whole ridge clearing at once is weaker evidence than a lone cell
would be — the honest reading is that trading less kept the better trades over this
particular lockbox year, which the walk-forward may or may not confirm. Every one of
these buys its improvement with FEWER trades, so a real WF verdict matters more here
than the offline table. The crown does not move on this file's numbers either way.

LIVE-LEGAL: both filters are the crown's own, unchanged in mechanism — the vol-regime
read is trailing-only and the volume-pace gate sees only bars that closed before the
entry bar. Only the thresholds move.
"""
import importlib.util as _ilu
import os as _os

_SRC = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "ORB_3_6.py")
_spec = _ilu.spec_from_file_location("_orb36_f7580", _SRC)
_base = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_base)

STRATEGY_NAME = 'ORB 3.6 - candidate F7580: both filters tightened, 0.75 / 0.80, pinned'
DESCRIPTION   = ("The #234 crown with both filters tightened, 0.75 / 0.80. Round-5 filter sweep candidate: "
                 "fewer trades, better lockbox and worse-year, less total money. "
                 "Judge on WF folds vs #234's 7/8 and on the ES transfer leg.")

_AUGUR_MARKET = {"instrument": "NQ", "timeframe": "5m"}
_AUGUR_PARENT = "ORB_3_6.py"

# PINNED: min == max on every numeric knob, one option on every categorical. Bools need
#   an explicit single-entry "options" list — a plain bool default is ignored by the
#   validate path (this voided runs 206-208).
DEFAULT_PARAMS = {
    "or_bars":        {"default": 2,    "min": 2,    "max": 2,    "step": 1,    "type": "int",   "label": "Opening range (bars) - PINNED"},
    "trade_mode":     {"default": "First-candle dir", "type": "str", "options": ["First-candle dir"], "label": "Direction - PINNED"},
    "stop_frac":      {"default": 2.0,  "min": 2.0,  "max": 2.0,  "step": 0.25, "type": "float", "label": "Stop (x range width) - PINNED"},
    "breakout_buf":   {"default": 0.25, "min": 0.25, "max": 0.25, "step": 0.05, "type": "float", "label": "Breakout buffer - PINNED"},
    "close_confirm":  {"default": True,  "type": "bool", "options": [True], "label": "Confirm at bar close - PINNED ON (this is what makes it live-legal)"},
    "partial_exit_R": {"default": 0.0,  "min": 0.0,  "max": 0.0,  "step": 0.5,  "type": "float", "label": "Partial exit - PINNED OFF"},
    "trail_bars":     {"default": 0,    "min": 0,    "max": 0,    "step": 1,    "type": "int",   "label": "Trailing stop - PINNED OFF"},
    "be_after_R":     {"default": 1.0,  "min": 1.0,  "max": 1.0,  "step": 0.1,  "type": "float", "label": "Breakeven after (x risk) - PINNED"},
    "target_R":       {"default": 5.5,  "min": 5.5,  "max": 5.5,  "step": 0.5,  "type": "float", "label": "Target (x risk) - PINNED"},
    "atr_filter":     {"default": 0.75,  "min": 0.75,  "max": 0.75,  "step": 0.05, "type": "float", "label": "Vol-regime filter (trailing) - PINNED (under test)"},
    "vpace_filter":   {"default": 0.80,  "min": 0.80,  "max": 0.80,  "step": 0.05, "type": "float", "label": "Volume-pace gate (pre-fill bars only) - PINNED (under test)"},
    "flat_eod":       {"default": True,  "type": "bool", "options": [True], "label": "Flat at the close - PINNED on"},
    "skip_holidays":  {"default": True,  "type": "bool", "options": [True], "label": "Skip holidays - PINNED on"},
}

# the mechanism is ORB_3_6's, untouched - this file only narrows the search to one point.
run_backtest = _base.run_backtest
