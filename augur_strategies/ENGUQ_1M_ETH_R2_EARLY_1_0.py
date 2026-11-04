"""ENGU-Q 1m ETH R2 + EARLY-WINDOW size tilt (GAUNTLET w93 DISC feed, prereg
C:/EdgeLog/manager/prereg/PREREG_disc_early_window_2026-11-03.md, owner GO 11-03).
--------------------------------------------------------------------------------
Parent: ENGUQ_1M_ETH_R2_1_0.py (the #335 leg). The parent's walk is called UNCHANGED; this file
only re-sizes its trades afterwards, so every entry and exit is the parent's own.

RULE. A trade whose entry bar starts in RTH (09:30 ET or later) and before t_end_min (minutes
after ET midnight) is sized x W_EARLY (1.5, fixed by the prereg); every other trade x 1. Sizes are
then normalised so their mean over the trades of THIS call is 1, so the tilt moves risk between
trades instead of adding it. t_end_min = 0 turns the tilt off (parity with the parent).

CO-TUNED (scope C3): t_end_min sits in the search space next to all fourteen parent knobs, so
the trail / risk / regime dials re-tune around it.

CAVEATS, stated before any number:
  - The prereg reads the SIGNAL bar; with limit_atr > 0 the parent's trade starts at the FILL bar,
    up to 10 minutes later. The entry bar is used here (it is what the trade list carries); a
    signal at 09:58 that fills at 10:03 is counted as late.
  - Cost: the engine charges its round trip once per trade, so each trade is handed back as
    s*raw - (s-1)*0.783 (NOISE_1_8_CT304's convention) and pays cost per unit of size. Queue it
    at cost_pts 0.783 only.
"""
import importlib.util as _ilu
import os as _os

import numpy as np

_SRC = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "ENGUQ_1M_ETH_R2_1_0.py")
_spec = _ilu.spec_from_file_location("_enguq_r2_for_early", _SRC)
_P = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_P)

_AUGUR_PARENT = "ENGUQ_1M_ETH_R2_1_0.py"
STRATEGY_NAME = "ENGU-Q 1m ETH R2 - early-window size tilt"
DESCRIPTION = ("The #335 leg with RTH entries before t_end_min sized x1.5 (mean size 1). "
               "t_end_min=0 = parity with ENGUQ_1M_ETH_R2_1_0.")
VERSION = "1.0"
DIRECTION = "LONG"
TIMEFRAME = "1m"

W_EARLY = 1.5
_COST_PTS = 0.783          # the house NQ 24-hour round trip (api/book_shadow BOOK463_LEGS)
_RTH_OPEN_MIN = 9 * 60 + 30

DEFAULT_PARAMS = dict(_P.DEFAULT_PARAMS)
DEFAULT_PARAMS['t_end_min'] = {
    'default': 600, 'min': 600, 'max': 660, 'step': 30, 'type': 'int',
    'label': 'Early Window End (min after ET midnight)',
    'tooltip': '600 = 10:00, 630 = 10:30, 660 = 11:00 ET. RTH entries before this are sized '
               'x1.5, then all sizes are scaled to mean 1. 0 = off (parity).'}

PARAM_GRID_PRESETS = {
    'Early window end (prereg)': {'t_end_min': [600, 630, 660]},
}


def run_backtest(opens, highs, lows, closes, volumes=None, day_id=None, index=None,
                 t_end_min=600, return_trades=False, **params):
    want = bool(return_trades)
    params.pop("return_levels", None)
    out = _P.run_backtest(opens, highs, lows, closes, volumes=volumes, day_id=day_id,
                          return_trades=True, **params)
    if out is None or int(t_end_min) <= 0 or index is None or len(index) != len(closes):
        if out is not None and not want:
            out.pop("trades", None)
        return out
    tr = out["trades"]
    ts = index.tz_convert("US/Eastern") if getattr(index, "tz", None) is not None else index
    mins = np.asarray(ts.hour * 60 + ts.minute)
    eb = np.array([int(t[0]) for t in tr])
    early = (mins[eb] >= _RTH_OPEN_MIN) & (mins[eb] < int(t_end_min))
    size = np.where(early, W_EARLY, 1.0)
    size = size / size.mean()
    # NOISE_1_8_CT304's cost convention: the engine subtracts cost once per trade, so a size-s
    # trade is handed back as s*raw - (s-1)*cost and lands on s*(raw-cost) after the engine
    p = np.array([float(t[2]) for t in tr]) * size - (size - 1.0) * _COST_PTS
    new_tr = [(t[0], t[1], float(p[k]), t[3], t[4]) + tuple(t[5:]) for k, t in enumerate(tr)]
    wins = p[p > 0]; losses = p[p < 0]
    cum = np.cumsum(p)
    res = {
        "total_pnl":     round(float(p.sum()), 2),
        "num_trades":    int(len(p)),
        "win_rate":      round(len(wins) / len(p) * 100, 1),
        "profit_factor": round(float(wins.sum()) / max(abs(float(losses.sum())), 1e-9), 2),
        "max_drawdown":  round(float((cum - np.maximum.accumulate(cum)).min()), 2),
        "avg_pnl":       round(float(p.mean()), 2),
        "wins":          int(len(wins)), "losses": int(len(losses)),
        "early_trades":  int(early.sum()),
    }
    if want:
        res["trades"] = new_tr
    return res
