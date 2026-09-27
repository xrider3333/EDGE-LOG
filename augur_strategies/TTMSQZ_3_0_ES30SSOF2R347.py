"""
TTMSQZ 3.0 ES30SSOF2R347 - the roll-guarded TTM book leg, ALREADY SIZED 3 / 4 / 7 ES contracts.

A BOOK-LEG FILE, NOT A RESEARCH FILE (2026-09-28, staged for the owner confirm via MANAGER).
A BOOK job multiplies each leg by one flat weight, and the staged schedule is not flat: the leg's own
size ladder (1.0 / 1.5 / 2.25 from the deep-squeeze and open-bar tilts, which multiply) is traded as
3 / 4 / 7 whole ES contracts, round 18a's answer to "there is no half contract". So this file does the
sizing itself and the book carries it at WEIGHT 1.0 - never 3, which would size it nine times over.

Everything else is TTMSQZ_3_0_ES30SSOF2R.py (run #428, the roll guard), imported unchanged. Each trade's
size is recovered from its own numbers - the parent returns s*raw - (s-1)*cost, and raw is the exit
price less the entry price - snapped to the ladder, and re-priced at c contracts as c*raw - (c-1)*cost,
which the engine's single cost subtraction turns into c*(raw - cost).

MEASURED (tools/ttmsqz_r18b_stage_numbers.py), pinned window, at run #428's cell (entry cutoff 5):
246 trades, $358,610, PF 3.58, drawdown $16,007, annualised MAR 1.39; lockbox 12 trades, $67,628.
The flat alternative (the parent at weight 3) is $358,764 at MAR 1.29 - the same money at 8% less
drawdown, and it can actually be traded.

HOW TO CARRY IT IN A BOOK: strategy TTMSQZ_3_0_ES30SSOF2R347.py, ES 30m RTH, source db_noadj_rth PINNED
(the file removes the rolls itself - on a back-adjusted master it would remove them twice), params
kc_mult 1.5 / eod_cutoff 5, cost_pts 0.363, multiplier 50, WEIGHT 1.0.
"""
import os
from importlib import util as _u

_HERE = os.path.dirname(os.path.abspath(__file__))
_sp = _u.spec_from_file_location("TTMSQZ_3_0_ES30SSOF2R", os.path.join(_HERE, "TTMSQZ_3_0_ES30SSOF2R.py"))
_guard = _u.module_from_spec(_sp); _sp.loader.exec_module(_guard)
_ss = _guard._base._so._ss            # the structural-stop file: its _rescore and _COST_PTS

_LADDER = {1.0: 3, 1.5: 4, 2.25: 7}   # the trade's own size -> whole ES contracts (round 18a)


def run_backtest(opens, highs, lows, closes, volumes=None, day_id=None, index=None,
                 return_trades=False, **kw):
    """Run #428's roll-guarded leg, each trade re-priced at 3, 4 or 7 contracts by its own size."""
    res = _guard.run_backtest(opens, highs, lows, closes, volumes=volumes, day_id=day_id,
                              index=index, return_trades=True, **kw)
    if not res or not res.get("trades"):
        return res
    cost = float(_ss._COST_PTS)
    out = []
    for t in res["trades"]:
        g, side, epx, xpx = float(t[2]), int(t[3]), float(t[4]), float(t[5])
        raw = side * (xpx - epx)
        if abs(raw - cost) < 1e-9:
            s = 1.0                              # worth nothing at any size
        else:
            s = (g - cost) / (raw - cost)
        c = _LADDER[min(_LADDER, key=lambda k: abs(k - s))]
        out.append((int(t[0]), int(t[1]), c * raw - (c - 1.0) * cost) + tuple(t[3:]))
    return _ss._rescore(out)


squeeze_indicators = _guard.squeeze_indicators
_ADMISSIBLE = _guard._ADMISSIBLE
_in_neighbourhood = _guard._in_neighbourhood

STRATEGY_NAME = 'TTMSQZ 3.0 ES30SSOF2R347 - roll-guarded TTM book leg at 3 / 4 / 7 ES contracts'
DESCRIPTION = ("Book-leg file: run 428 (the roll-guarded TTM leg) with each trade already sized 3, 4 or 7 "
               "whole ES contracts by its own tilt ladder. Carry it in a book at weight 1.0.")
_AUGUR_MARKET = {"instrument": "ES", "timeframe": "30m"}
_AUGUR_PARENT = "TTMSQZ_3_0_ES30SSOF2R.py"

DEFAULT_PARAMS = dict(_guard.DEFAULT_PARAMS)
PARAM_GRID_PRESETS = {
    "Short  (roll-guarded TTM book leg, 3/4/7 contracts)": dict(list(_guard.PARAM_GRID_PRESETS.values())[0]),
}
