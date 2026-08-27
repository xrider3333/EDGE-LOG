"""
ENGU-Q 1m ETH — frozen #149 config with the re-entry cooldown PINNED at 5 bars.

Single point. No search space at all, exactly like ENGUQ_1M_ETH_FROZEN_1_0.py, so an
Auto-Validate on this file grades ONE configuration and is directly comparable to the
frozen control's report card.

WHY THIS EXISTS (2026-08-27). The 3..8 cooldown sweep (ENGUQ_1M_ETH_COOLDOWN_1_0.py) came
back **WEAK**, and the control (frozen, no cooldown) came back **PASS** — but reading that
as "the cooldown is worse" is wrong, and the reason is worth writing down:

    sweep 3..8  : PF 1.3601 | lockbox 5,256.99 pts, PF 1.521, 201 trades, PASS
    control (0) : PF 1.3573 | lockbox 4,516.90 pts, PF 1.417, 212 trades, PASS

The cooldown version is BETTER on the held-out year — +740 points (~+$14,800) and lockbox
PF 1.417 -> 1.521. It passed 5 of the 6 checks. The single failure was **PBO 0.77**
("likely overfit selection"), and PBO asks one specific question: *given that you chose the
best of several configs, how likely is it that you chose by luck?*

**The control cannot fail that check, because the control never chose anything.** It is one
config; PBO is not even computed for it (pbo: None). So the sweep was carrying a penalty
that its comparator was structurally exempt from, and the two verdicts were never
comparable. On a 3..8 plateau where every cell scores within a whisker of the others
(tools/enguq_cooldown_robust.py: net +$16.7k..+$21.9k, PF 1.350-1.355, lockbox PF
1.604-1.612), a high PBO is the EXPECTED result and means "which value you picked is
arbitrary" — not "waiting after a trade does not help".

Pinning removes the choice, which removes the penalty, which makes the comparison fair:
this file vs ENGUQ_1M_ETH_FROZEN_1_0.py, one config each, same window, same folds, same
lockbox, both gradeable on the same six checks.

WHY 5 AND NOT 3. The sweep's champion was 3, but 3 sits on the EDGE of the tested plateau
— if the true optimum were below 3 we would not know, and edge picks are exactly what PBO
is warning about. 5 was the value pre-registered in tools/enguq_cooldown_test.py before any
result was seen, and it sits mid-plateau with 3/4 below it and 6/7/8 above. Choosing the
pre-registered mid-plateau value over the post-hoc argmax is the whole point.

Engine math is ENGUQ_1M_ETH_1_0.py's, imported unchanged. This file only pins parameters.
"""
import importlib.util as _ilu
import os as _os

_SRC = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "ENGUQ_1M_ETH_1_0.py")
_spec = _ilu.spec_from_file_location("_enguq_eth_base_cd5", _SRC)
_base = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_base)

STRATEGY_NAME = "ENGU-Q 1m ETH COOLDOWN-5 1.0"
DESCRIPTION = ("The deployed frozen clock-scaled #149 ETH config plus a 5-bar re-entry "
               "cooldown (owner item 896), every knob pinned so Auto-Validate grades ONE "
               "configuration. Exists to be compared like-for-like against "
               "ENGUQ_1M_ETH_FROZEN_1_0.py: the 3-8 sweep beat the control on the held-out "
               "year (lockbox PF 1.521 vs 1.417) but scored WEAK on PBO, a check the "
               "single-config control is structurally exempt from. Pinning makes both "
               "sides answer the same questions.")
VERSION   = "1.0"
DIRECTION = "LONG"
TIMEFRAME = "1m"

_AUGUR_MARKET = {"instrument": "NQ", "timeframe": "1m"}
_AUGUR_PARENT = "ENGUQ_1M_ETH_1_0.py"

DEFAULT_PARAMS = {
    "tl_len":        {"default": 170,  "min": 170,  "max": 170,  "step": 4,   "type": "int",   "label": "Trendline Length (bars) — PINNED"},
    "vol_mult":      {"default": 0.8,  "min": 0.8,  "max": 0.8,  "step": 0.1, "type": "float", "label": "Volume Spike (x avg) — PINNED"},
    "stop_mult":     {"default": 1.0,  "min": 1.0,  "max": 1.0,  "step": 0.1, "type": "float", "label": "Stop (x risk-to-swing-low) — PINNED"},
    "act_R":         {"default": 2.5,  "min": 2.5,  "max": 2.5,  "step": 0.5, "type": "float", "label": "Trail Activation (R) — PINNED"},
    "trail_frac":    {"default": 2.5,  "min": 2.5,  "max": 2.5,  "step": 0.5, "type": "float", "label": "Trail Width (x risk) — PINNED"},
    "buf_atr":       {"default": 0.9,  "min": 0.9,  "max": 0.9,  "step": 0.05,"type": "float", "label": "Breakout Buffer (x ATR) — PINNED"},
    "min_brk":       {"default": 1.3,  "min": 1.3,  "max": 1.3,  "step": 0.1, "type": "float", "label": "Breakout Decisiveness (x ATR) — PINNED"},
    "ema_len":       {"default": 1380, "min": 1380, "max": 1380, "step": 40,  "type": "int",   "label": "Trend EMA Length — PINNED"},
    "atr_len":       {"default": 106,  "min": 106,  "max": 106,  "step": 4,   "type": "int",   "label": "ATR Length — PINNED"},
    "regime_len":    {"default": 0,    "min": 0,    "max": 0,    "step": 5,   "type": "int",   "label": "Regime SMA (days, 0=off) — PINNED off"},
    "breakeven_R":   {"default": 1.5,  "min": 1.5,  "max": 1.5,  "step": 0.5, "type": "float", "label": "Breakeven (R, 0=off) — PINNED"},
    "cooldown_bars": {"default": 5,    "min": 5,    "max": 5,    "step": 1,   "type": "int",   "label": "Re-entry cooldown (bars) — PINNED 5"},
}

PARAM_GRID_PRESETS = {
    "PINNED - frozen 149 + 5-bar cooldown": {
        "tl_len":        [170],
        "vol_mult":      [0.8],
        "stop_mult":     [1.0],
        "act_R":         [2.5],
        "trail_frac":    [2.5],
        "buf_atr":       [0.9],
        "min_brk":       [1.3],
        "ema_len":       [1380],
        "atr_len":       [106],
        "regime_len":    [0],
        "breakeven_R":   [1.5],
        "cooldown_bars": [5],
    }
}

# engine math is ENGUQ_1M_ETH_1_0's, unchanged — this file only pins the search space.
run_backtest = _base.run_backtest
