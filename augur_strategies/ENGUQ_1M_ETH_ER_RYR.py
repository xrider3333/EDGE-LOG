"""
ENGU-Q 1m ETH ER — R / YR NEIGHBOURHOOD (fenced search around the EV R 1.40 plateau).

WHY THIS FILE EXISTS. The owner ranks strategies on EV R = (1 - win%) x (PF - 1) and
R / YR = EV R x trades per year (app v73.460). Auto-Validate crowns on the house MAR
rule, so the configurations that lead on the OWNER's metric are not the ones the runs
crowned - `tools/mine_ryr_frontier.py` showed exactly that across the whole Past Runs
population. An R / YR-objective random search over this file's parent's own declared
ranges (`tools/ryr_search.py`, 200 configs, NQ 1m ETH, 2010-06-07..2025-06-29, cost
0.783) then found a region the crowned searches never picked:

    n = 833 · PF 2.553 · win 9.8% · net $257,557 · DD $17,583 · MAR 14.65
    EV R 1.40 · 55 trades/yr · R / YR 77.4 · 7 of 8 chronological slices positive

EV R 1.40 is the highest of ANY configuration in the library with a real trade count
(the best validated single strategy before this was ENGU-Q ETH #198 at 1.03), and it
keeps R / YR 77 - close to the NOISE crown (77) - while doing it at 55 trades a year
instead of 232. Very few, very asymmetric trades.

IT IS A PLATEAU, NOT A SPIKE, and that was checked before this file was written
(`tools/ryr_neighbourhood.py`, one grid step either side of every ranged knob, 26
neighbours): median neighbour R / YR 77.3 against the leader's 77.4, **26 of 26
neighbours keep PF >= 1.25, and 26 of 26 keep 6+ of 8 slices positive**. The worst
neighbour (er_len 40) still runs PF 2.46. Two neighbours are better than the centre
(stop_mult 0.3 -> R / YR 93.5; breakeven_R 0.5 -> 92.1), which is why those knobs are
left OPEN below rather than pinned to the centre.

WHAT IS OPEN AND WHY. Five knobs, each spanning the measured plateau (3 values each,
3^5 = 243 cells): the two that beat the centre, plus the three whose one-step
neighbours moved R / YR most. Everything else is PINNED at the plateau centre, so the
search shapes only the geometry that was actually measured to matter and the report
still carries a real landscape (points, PDP, parallel coordinates, surfaces, knob
importance, PBO over a pool this configuration genuinely belongs to).

READ THE PBO HONESTLY: a tight neighbourhood of near-identical configurations should
read a LOWER overfit probability than a wide-open search, because the in-sample best
is far less likely to be a lucky outlier. That is a statement about THIS selection
(did the R / YR geometry hold among its own neighbours?), not a figure to quote
against a free-discovery run. Report both.

LOCKBOX HONESTY: the ENGU-Q family lockbox has been read many times (runs 198, 226,
227, 309, 310, 313). Every lockbox figure this run prints is CONFIRMATORY ONLY and
can never promote this configuration on its own. The walk-forward folds and forward
paper data are the real judges.

Entry/exit math is ENGUQ_1M_ETH_ER_1_0.py's, unchanged. This file only shapes the
search space - it adds no rule and changes no calculation.
"""
import importlib.util as _ilu
import inspect as _inspect
import os as _os

_SRC = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "ENGUQ_1M_ETH_ER_1_0.py")
_spec = _ilu.spec_from_file_location("_enguq_er_base_ryr", _SRC)
_base = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_base)

STRATEGY_NAME = 'ENGU-Q 1m ETH ER - R / YR neighbourhood (EV R 1.40 plateau)'
DESCRIPTION = ("The EV R / R-per-year frontier region of ENGU-Q ER on the 24-hour NQ tape: "
               "very few, very asymmetric trades (PF 2.55 at a 10 percent win rate). Five "
               "geometry knobs open across the measured plateau, the rest pinned.")

_AUGUR_MARKET = {"instrument": "NQ", "timeframe": "1m"}
_AUGUR_PARENT = "ENGUQ_1M_ETH_ER_1_0.py"

# The R / YR search leader (plateau centre). Every knob below either equals one of
#   these values (pinned) or is centred on it (open).
_CENTRE = {
    "er_len": 30, "er_th": 0.5, "limit_atr": 0.35, "tl_len": 198, "vol_mult": 0.4,
    "stop_mult": 0.4, "act_R": 1.0, "trail_frac": 4.0, "buf_atr": 0.85, "min_brk": 0.3,
    "ema_len": 1300, "atr_len": 136, "breakeven_R": 1.0, "regime_len": 85,
}

_OPEN_VALS = {
    "stop_mult": [0.3, 0.4, 0.5],          # 0.3 measured BETTER than centre (R / YR 93.5)
    "breakeven_R": [0.5, 1.0, 1.5],        # 0.5 measured BETTER than centre (R / YR 92.1)
    "trail_frac": [3.5, 4.0, 4.5],         # 3.5 was the sharpest one-step drop (63.6)
    "er_len": [20, 30, 40],                # both sides drop hard - the knob that matters most
    "tl_len": [194, 198, 202],             # +/- one step, both mildly lower
}

DEFAULT_PARAMS = {
    "er_len":      {"default": 30,   "min": 20,   "max": 40,   "step": 10,   "type": "int",   "label": "Efficiency-ratio lookback - OPEN 20/30/40"},
    "er_th":       {"default": 0.5,  "min": 0.5,  "max": 0.5,  "step": 0.05, "type": "float", "label": "Efficiency-ratio floor - PINNED (plateau centre)"},
    "limit_atr":   {"default": 0.35, "min": 0.35, "max": 0.35, "step": 0.05, "type": "float", "label": "Limit offset (x ATR) - PINNED"},
    "tl_len":      {"default": 198,  "min": 194,  "max": 202,  "step": 4,    "type": "int",   "label": "Trendline lookback - OPEN 194/198/202"},
    "vol_mult":    {"default": 0.4,  "min": 0.4,  "max": 0.4,  "step": 0.1,  "type": "float", "label": "Volume filter - PINNED"},
    "stop_mult":   {"default": 0.4,  "min": 0.3,  "max": 0.5,  "step": 0.1,  "type": "float", "label": "Initial stop (x ATR) - OPEN 0.30/0.40/0.50"},
    "act_R":       {"default": 1.0,  "min": 1.0,  "max": 1.0,  "step": 0.5,  "type": "float", "label": "Trail activation (R) - PINNED"},
    "trail_frac":  {"default": 4.0,  "min": 3.5,  "max": 4.5,  "step": 0.5,  "type": "float", "label": "Trail distance - OPEN 3.5/4.0/4.5"},
    "buf_atr":     {"default": 0.85, "min": 0.85, "max": 0.85, "step": 0.05, "type": "float", "label": "Break buffer (x ATR) - PINNED"},
    "min_brk":     {"default": 0.3,  "min": 0.3,  "max": 0.3,  "step": 0.1,  "type": "float", "label": "Minimum break size - PINNED"},
    "ema_len":     {"default": 1300, "min": 1300, "max": 1300, "step": 20,   "type": "int",   "label": "Trend EMA - PINNED"},
    "atr_len":     {"default": 136,  "min": 136,  "max": 136,  "step": 4,    "type": "int",   "label": "ATR length - PINNED"},
    "breakeven_R": {"default": 1.0,  "min": 0.5,  "max": 1.5,  "step": 0.5,  "type": "float", "label": "Breakeven at (R) - OPEN 0.5/1.0/1.5"},
    "regime_len":  {"default": 85,   "min": 85,   "max": 85,   "step": 5,    "type": "int",   "label": "Regime lookback - PINNED (plateau centre)"},
}

PARAM_GRID_PRESETS = {
    "Short  (R / YR neighbourhood, 243 cells)": dict(
        {k: [v] for k, v in _CENTRE.items() if k not in _OPEN_VALS}, **_OPEN_VALS
    ),
}

_BASE_ARGS = set(_inspect.signature(_base.run_backtest).parameters)


def run_backtest(opens, highs, lows, closes, **kw):
    """Entry/exit math is the parent's, unchanged - this file only shapes the search
    space. The plateau centre is applied here too, so calling this file with NO params
    reproduces the R / YR search leader exactly rather than falling back to the
    parent's own signature defaults, which are a different configuration."""
    p = dict(_CENTRE)
    p.update({k: v for k, v in kw.items() if k in _BASE_ARGS})
    return _base.run_backtest(opens, highs, lows, closes, **p)
