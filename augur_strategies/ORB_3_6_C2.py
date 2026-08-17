"""
ORB 3.6 — HUNT CANDIDATE 2, PINNED: RIDE + BREAKEVEN (no partial, no trail).

2026-08-17 hunt, second find. Porting the old 2-lot ensemble to the legal base showed
its two exit plans were both WORSE than just riding: on the #230 entries, the trailed
leg barely makes money and the partial+trail champion exit LOSES to a plain
ride-to-target once breakeven is on. Dropping BOTH runner levers — two fewer active
knobs than the #230 crown — improves every window:

    (NQ 5m RTH no-adj, 0.533 pts/RT, 1 contract; identical 2,607 trades all rows)
                          net        PF     maxDD     MAR      LB net   LB PF
    #230 champion       $348,129   1.263   $35,474    9.81    $64,575   1.31
    C1 (champ + be1.0)  $363,867   1.286   $28,501   12.77    $72,790   1.37
    C2 (THIS: ride+be)  $389,874   1.307   $29,142   13.38    $88,943   1.45

Config = run #230's entry machinery unchanged (OR 2, first-candle dir, close-confirm,
buf 0.25, stop 2.0, ATR 0.7, v-pace 0.7, skip holidays) + target 5.5R + breakeven at
1.0R, with partial_exit_R=0 and trail_bars=0.

Robustness (tools/orb_hunt.py `ridebe`): BE plateau 0.8-1.2 (FULL MAR 13.36-13.44),
target plateau 4.5-5.5 (13.19-13.38), stop neighbors sane. The exit is a pure
simplification — same entries, fewer moving parts, more money, and the whole $41.7k
gap vs #230 shows up in-sample too (not a lockbox artifact).

Caveats to carry: (1) the shared 2025-08-13..2026-08-13 lockbox has been read MANY
times across this research program — treat LB rows as encouraging, not confirmatory;
the validate's own WF folds + future forward data are the real judges. (2) REGIME
CAVEAT unchanged from #230: 2010-2017 flat, the money is post-2018.

LIVE-LEGAL BY CONSTRUCTION: entry at a finished bar's close; BE armed on a finished
bar's close and acting from the next bar; stop-first + gap-through fills; every gate
reads only prior bars. Nothing on any fill bar is read before it exists.
"""
import importlib.util as _ilu
import os as _os

_SRC = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "ORB_3_6.py")
_spec = _ilu.spec_from_file_location("_orb36_base_c2", _SRC)
_base = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_base)

STRATEGY_NAME = 'ORB 3.6 · hunt candidate 2 (ride+BE), pinned'
DESCRIPTION   = ("The #230 entries with the SIMPLEST exit that wins: ride to a 5.5R "
                 "target with breakeven at 1.0R - no partial, no trail (two fewer "
                 "knobs than the crown). Net +12%, drawdown -18%, MAR +36% vs #230, "
                 "and the gain shows in-sample, not just the lockbox. Every knob "
                 "pinned; validating this file IS validating that one config.")

_AUGUR_MARKET = {"instrument": "NQ", "timeframe": "5m"}
_AUGUR_PARENT = "ORB_3_6.py"

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
    "flat_eod":       {"default": True,  "type": "bool", "options": [True],                                      "label": "Flat at the close — PINNED on"},
    "skip_holidays":  {"default": True,  "type": "bool", "options": [True],                                      "label": "Skip holidays — PINNED on"},
}

# arm math is ORB_3_6's, unchanged — this file only narrows the search space to one point.
run_backtest = _base.run_backtest
