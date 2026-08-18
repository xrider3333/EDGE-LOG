"""
ORB 3.6 — ENTRY VARIANT E2: best lockbox of the survivors.

Owner 2026-08-18: "try new things". Rounds 1-2 changed ONLY the exit — all 65+ configs
tested carried run #230's entry verbatim. But that entry was chosen when the exit was
partial-3R + trail-3, and the exit has since changed completely (ride to 5.5R with
breakeven at 1.0R). So the entry surface was re-opened under the NEW exit for the first
time: a one-at-a-time scan, then a 192-config focused grid on the four knobs that moved
(atr_filter / breakout_buf / stop_frac / vpace_filter), with or_bars=2 and first-candle
direction held fixed (both re-confirmed dominant; or_bars 3 posted the best in-sample
number in its column and a NEGATIVE lockbox for the third time in this program).

Selection used a PRE-REGISTERED gate, written before the grid was run, on ROBUSTNESS
rather than total dollars — a config had to beat run #234 on all three of: rolling-12mo
win rate (>=72.7%), worst rolling 12mo (>=-$22,050), and lockbox net (>=$88,942).
6 of 192 survived. This file is one of the three distinct survivors.

    entry: OR 2 - first-candle dir - close-confirm - buf 0.30 - v-pace 0.7 - ATR 0.0
    stop:  1.75 x range width        exit: ride to 5.5R, breakeven at 1.0R

Offline (NQ 5m RTH no-adj, 0.533 pts/RT, 1 contract, run #230's window; lockbox measured
with a REAL windowed run, not a slice):
    full net $376,576  -  maxDD $34,381  -  net/DD 10.95
    lockbox $101,745 at PF 1.608  -  rolling-12mo win 73.2%, worst -$14,259
    (run #234: $389,874 - $29,142 - 13.38 - LB $88,942 PF 1.453 - win 72.7%, worst -$22,050)

NONE OF THAT IS A WALK-FORWARD. The offline screen cannot produce one, and WF is the
owner's judge (2026-08-17: "WF is our judge"). The verdict on this file is the WF fold
count + wfe this validate returns, read against run #234's 7/8 and wfe 4.649. A caution
worth carrying: the 192-config grid is a much larger search surface than the one-knob
neighbour runs, so a strong offline number here deserves MORE scepticism, not less.

CAVEAT unchanged: the 2025-08-13..2026-08-13 lockbox has been read many times across this
program — encouraging, not confirmatory. REGIME CAVEAT: 2010-2017 flat, money is post-2018.

LIVE-LEGAL BY CONSTRUCTION: entry at a finished bar's close; BE armed on a finished bar's
close and acting from the next bar; stop-first + gap-through fills; every gate reads only
prior bars. Nothing on any fill bar is read before it exists.
"""
import importlib.util as _ilu
import os as _os

_SRC = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "ORB_3_6.py")
_spec = _ilu.spec_from_file_location("_orb36_base_e2", _SRC)
_base = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_base)

STRATEGY_NAME = 'ORB 3.6 · entry variant E2 — best lockbox of the survivors, pinned'
DESCRIPTION   = ("First re-optimisation of the ENTRY under the new ride+BE exit. "
                 "Survivor of a pre-registered robustness gate over a 192-config grid "
                 "(best lockbox of the survivors). Judge on WF folds vs run #234's 7/8, not the offline net.")

_AUGUR_MARKET = {"instrument": "NQ", "timeframe": "5m"}
_AUGUR_PARENT = "ORB_3_6.py"

# PINNED: min == max on every numeric knob, one option on every categorical. Bools need
#   an explicit single-entry "options" list — a plain bool default is ignored by the
#   validate path (this voided runs 206-208).
DEFAULT_PARAMS = {
    "or_bars":        {"default": 2,    "min": 2,    "max": 2,    "step": 1,    "type": "int",   "label": "Opening range (bars) — PINNED"},
    "trade_mode":     {"default": "First-candle dir", "type": "str", "options": ["First-candle dir"],            "label": "Direction — PINNED"},
    "stop_frac":      {"default": 1.75,  "min": 1.75,  "max": 1.75,  "step": 0.25, "type": "float", "label": "Stop (× range width) — PINNED"},
    "breakout_buf":   {"default": 0.30, "min": 0.30, "max": 0.30, "step": 0.05, "type": "float", "label": "Breakout buffer — PINNED"},
    "close_confirm":  {"default": True,  "type": "bool", "options": [True],                                      "label": "Confirm at bar close — PINNED ON (this is what makes it live-legal)"},
    "partial_exit_R": {"default": 0.0,  "min": 0.0,  "max": 0.0,  "step": 0.5,  "type": "float", "label": "Partial exit — PINNED OFF (the simplification)"},
    "trail_bars":     {"default": 0,    "min": 0,    "max": 0,    "step": 1,    "type": "int",   "label": "Trailing stop — PINNED OFF (the simplification)"},
    "be_after_R":     {"default": 1.0,  "min": 1.0,  "max": 1.0,  "step": 0.1,  "type": "float", "label": "Breakeven after (× risk) — PINNED at the plateau center"},
    "target_R":       {"default": 5.5,  "min": 5.5,  "max": 5.5,  "step": 0.5,  "type": "float", "label": "Target (× risk) — PINNED"},
    "atr_filter":     {"default": 0.0,  "min": 0.0,  "max": 0.0,  "step": 0.1,  "type": "float", "label": "Vol-regime filter (trailing) — PINNED"},
    "vpace_filter":   {"default": 0.7,  "min": 0.7,  "max": 0.7,  "step": 0.1,  "type": "float", "label": "Volume-pace gate (pre-fill bars only) — PINNED"},
    "flat_eod":       {"default": True,  "type": "bool", "options": [True],                                      "label": "Flat at the close — PINNED on"},
    "skip_holidays":  {"default": True,  "type": "bool", "options": [True],                                      "label": "Skip holidays — PINNED on"},
}

# arm math is ORB_3_6's, unchanged — this file only narrows the search space to one point.
run_backtest = _base.run_backtest
