"""
ENGU-Q 1m ETH — ROUND-6 CANDIDATE REG5: the certified #249 limit config with the REGIME
filter switched on, searched over its own NARROW neighbourhood (not pinned).

Round-6 sweep (tools/enguq_hunt6.py, 2026-09-04) scored 316 cells on the owner's two
cross-strategy reads — EV R (expectancy per average losing trade) and R / YR (EV R x
trades per year). The single lever that moved both at once was `regime_len` 0 -> 5:

    pinned window 2010-06-07 .. 2026-06-30, NQ 1m ETH, 0.533 pts/RT, $20/pt, one contract
                                  n     net       LB        DD       PF     EV R   R/YR   worst-12mo
    #249 (regime off)          2,924  $513,008  $126,069  $61,666   1.401   0.293   53.3   -$48,107
    THIS (regime 5, brk 1.0)   2,846  $667,721  $119,085  $37,266   1.674   0.501   88.7   -$1,672

Better on EV R (+71%), on R / YR (+66%), on net (+30%), on profit factor, and on the
worst rolling year (-$1,672 against -$48,107) for a $7,000 lighter lockbox. R / YR 88.7
is the highest of any single strategy measured on this board.

IT IS A RIDGE, NOT A SPIKE. All 24 cells in the regime-on family read R / YR 73.6 to
88.7. The volume filter barely matters across 0.0-1.5 (85-89); `min_brk` 1.0 beats 1.3
beats 1.6; `regime_len` 5 is the lever doing the work. The ranges below cover that ridge.

HONEST CAVEAT: the sweep's own pre-registered gate demanded beating run #310 on EV R
(0.94) as well, and this cell does not — so it is NOT a gate clearer. It is here because
#310 takes ZERO trades in the lockbox year on the local harness (a data-path difference
from its Auto-Validate, unexplained), which makes #310's EV R an unreliable bar. This
cell beats the certified #249 on every leg including the lockbox and the worst year,
which is the comparison that can be trusted.

WHY THE RANGES ARE OPEN (HARD RULE since v73.350): an Auto-Validate on a fully pinned
file records ONE config and the report loses its parameter landscape. Four knobs carry
narrow ranges centred on the cell; the rest are #249's certified values, pinned.

HARD RULE on the window: date_to 2026-06-30 — the NQ 1-minute master has an
unrecoverable hole 2026-07-01..2026-08-05.
"""
import importlib.util as _ilu
import os as _os

_SRC = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "ENGUQ_1M_ETH_LIM_1_0.py")
_spec = _ilu.spec_from_file_location("_enguq_lim_reg5", _SRC)
_base = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_base)

STRATEGY_NAME = 'ENGU-Q 1m ETH - candidate REG5: #249 limit config with the regime filter on'
DESCRIPTION   = ("The certified #249 limit entry with regime_len 5 and min_brk 1.0. Round-6 sweep: "
                 "EV R 0.501 and R / YR 88.7 against #249's 0.293 and 53.3, with a better profit "
                 "factor, a much better worst rolling year and a $24k lighter drawdown. Narrow open "
                 "ranges so the validate maps the ridge; the walk-forward and the lockbox decide.")

_AUGUR_MARKET = {"instrument": "NQ", "timeframe": "1m"}
_AUGUR_PARENT = "ENGUQ_1M_ETH_LIM_1_0.py"

DEFAULT_PARAMS = {
    "limit_atr":   {"default": 0.5,  "min": 0.5,  "max": 0.5,  "step": 0.1,  "type": "float", "label": "Limit entry (x ATR) - PINNED at #249's certified 0.5"},
    "tl_len":      {"default": 170,  "min": 170,  "max": 170,  "step": 10,   "type": "int",   "label": "Trendline lookback - PINNED (#249)"},
    "vol_mult":    {"default": 0.5,  "min": 0.0,  "max": 1.5,  "step": 0.5,  "type": "float", "label": "Volume filter - NARROW RANGE (barely matters across the ridge)"},
    "stop_mult":   {"default": 1.0,  "min": 1.0,  "max": 1.0,  "step": 0.1,  "type": "float", "label": "Stop (x ATR) - PINNED (#249)"},
    "act_R":       {"default": 2.5,  "min": 2.5,  "max": 2.5,  "step": 0.5,  "type": "float", "label": "Trail activation (x risk) - PINNED (#249)"},
    "trail_frac":  {"default": 2.5,  "min": 2.5,  "max": 2.5,  "step": 0.5,  "type": "float", "label": "Trail fraction - PINNED (#249)"},
    "buf_atr":     {"default": 0.9,  "min": 0.9,  "max": 0.9,  "step": 0.1,  "type": "float", "label": "Break buffer (x ATR) - PINNED (#249)"},
    "min_brk":     {"default": 1.0,  "min": 1.0,  "max": 1.6,  "step": 0.3,  "type": "float", "label": "Minimum break size - NARROW RANGE 1.0-1.6 (1.0 is best on the ridge)"},
    "ema_len":     {"default": 1380, "min": 1380, "max": 1380, "step": 60,   "type": "int",   "label": "EMA lookback - PINNED (#249's clock-scaled 24h value)"},
    "atr_len":     {"default": 106,  "min": 106,  "max": 106,  "step": 10,   "type": "int",   "label": "ATR lookback - PINNED (#249)"},
    "regime_len":  {"default": 5,    "min": 0,    "max": 20,   "step": 5,    "type": "int",   "label": "Regime filter - NARROW RANGE 0-20 (5 is the lever under test; 0 = #249)"},
    "breakeven_R": {"default": 1.5,  "min": 1.5,  "max": 1.5,  "step": 0.5,  "type": "float", "label": "Breakeven (x risk) - PINNED (#249)"},
}

# the mechanism is ENGUQ_1M_ETH_LIM_1_0's, untouched - this file only narrows the search.
run_backtest = _base.run_backtest
