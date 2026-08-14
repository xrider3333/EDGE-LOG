"""
ORB 3.4 — RUN #221 CHAMPION, PINNED. The best LEGAL ORB found (grail hunt, 2026-08-13).

Every knob nailed shut, so an Auto-Validate explores a SINGLE point and the crowned config
is #221's by construction — no search, no drift, and the report is this one config's own.

    or_bars 2 · first-candle direction · stop 2.00 · buffer 0.25 · CLOSE-CONFIRMED entry
    partial 3.0R · trail 3 · target 5.5R · ATR 0.70 · v-pace 0.70 · flat EOD · skip holidays

LIVE-LEGAL BY CONSTRUCTION — every input exists before the decision that uses it:
  * entry is a BAR-CLOSE decision (close_confirm on): the bar must CLOSE beyond the level
    and the fill is that close. There is no intrabar touch, so no same-bar quantity is
    ever unknowable — this is precisely the defect that voided the #125 touch-entry family
    (ORB.md, tools/orb_live_emulation_cost.py).
  * v-pace gate reads session volume from bars strictly BEFORE the entry bar, against a
    prior-20-session norm.
  * ATR vol-regime gate is trailing-only; skip_holidays is a calendar known years ahead.
  * trailing stop uses prior bars' extremes (excludes the current bar).
  * stops are tested BEFORE targets on a shared bar, and a gap-through fills at the open,
    not the stop price — both pessimistic.
MILD modelling note to state when reporting: the fill is the confirming bar's closing
price. Live you cross the spread just after that close; the 0.25 pt slippage + $5.66
commission charged per round turn is what pays for it.

Honest full-history numbers (NQ 5m RTH no-adj, 2010-06-07 -> 2026-08, 1 contract,
0.533 pts/RT all-in): n=2607 · net $348,129 · PF 1.263 · max DD $35,474 · MAR 9.81.
Certified as run #221: PASS 7/7, lockbox HELD $62,173, ES transfer PASS.
READ THE REGIME CAVEAT: 2010-2017 is flat (about -$2.5k across eight years). Every dollar
is post-2018, and 2022 alone is +$108k. This is a high-volatility-regime strategy.
"""
import importlib.util as _ilu
import os as _os

_SRC = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "ORB_3_4.py")
_spec = _ilu.spec_from_file_location("_orb34_base_c221", _SRC)
_base = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_base)

STRATEGY_NAME = 'ORB 3.4 · run 221 champion, pinned'
DESCRIPTION   = ("The best legal ORB found — OR 2, first-candle direction, close-confirmed "
                 "entry, stop 2.0, buffer 0.25, partial 3R, trail 3, target 5.5R, ATR 0.70, "
                 "v-pace 0.70, skip holidays. Every knob pinned, so this file IS run #221. "
                 "Live-legal: the entry is a bar-close decision, never an intrabar touch.")

_AUGUR_MARKET = {"instrument": "NQ", "timeframe": "5m"}
_AUGUR_PARENT = "ORB_3_4.py"

# PINNED: min == max on every numeric knob, one option on every categorical. Bools need an
#   explicit single-entry "options" list — a plain bool default is ignored by the validate
#   path and silently falls back to the parent's default (this voided runs 206-208).
DEFAULT_PARAMS = {
    "or_bars":        {"default": 2,    "min": 2,    "max": 2,    "step": 1,    "type": "int",   "label": "Opening range (bars) — PINNED"},
    "trade_mode":     {"default": "First-candle dir", "type": "str", "options": ["First-candle dir"],            "label": "Direction — PINNED"},
    "stop_frac":      {"default": 2.0,  "min": 2.0,  "max": 2.0,  "step": 0.25, "type": "float", "label": "Stop (× range width) — PINNED"},
    "breakout_buf":   {"default": 0.25, "min": 0.25, "max": 0.25, "step": 0.05, "type": "float", "label": "Breakout buffer — PINNED"},
    "close_confirm":  {"default": True,  "type": "bool", "options": [True],                                      "label": "Confirm at bar close — PINNED ON (this is what makes it live-legal)"},
    "partial_exit_R": {"default": 3.0,  "min": 3.0,  "max": 3.0,  "step": 0.5,  "type": "float", "label": "Partial exit (× risk) — PINNED"},
    "trail_bars":     {"default": 3,    "min": 3,    "max": 3,    "step": 1,    "type": "int",   "label": "Trailing stop (bars) — PINNED"},
    "target_R":       {"default": 5.5,  "min": 5.5,  "max": 5.5,  "step": 0.5,  "type": "float", "label": "Target (× risk) — PINNED"},
    "atr_filter":     {"default": 0.7,  "min": 0.7,  "max": 0.7,  "step": 0.1,  "type": "float", "label": "Vol-regime filter (trailing) — PINNED"},
    "vpace_filter":   {"default": 0.7,  "min": 0.7,  "max": 0.7,  "step": 0.1,  "type": "float", "label": "Volume-pace gate (pre-fill bars only) — PINNED"},
    "flat_eod":       {"default": True,  "type": "bool", "options": [True],                                      "label": "Flat at the close — PINNED on"},
    "skip_holidays":  {"default": True,  "type": "bool", "options": [True],                                      "label": "Skip holidays — PINNED on"},
}

# arm math is ORB_3_4's, unchanged — this file only narrows the search space to one point.
run_backtest = _base.run_backtest
