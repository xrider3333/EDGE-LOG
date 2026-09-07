"""
NOISE 1.1 SBS+V90 + MOMENTUM SIZE TILT - a fenced, pre-registered neighbourhood validate.

WHERE THIS CAME FROM (tools/trade_anatomy.py, 2026-09-07, docs/anatomy/NOISE_243.md)
  The owner asked for a look at the structure of each trade BEFORE entry. The anatomy tool
  scored ~75 pre-entry readings on the NOISE paper leg's own trades, mining only the first 60%
  of the pre-lockbox span (2010-06-07 .. 2019-03-30) and keeping the rest (.. 2025-02-11) as a
  holdout that was looked at exactly once; the lockbox was never loaded. Twenty skip rules that
  looked good in discovery all LOST total money in the holdout - regime artifacts. One reading
  carried both windows: how far price had ALREADY MOVED IN THE TRADE'S DIRECTION over the two
  hours (24 five-minute bars) before the decision bar, in ATR units.
    top third (>= ~4.3 ATR) vs bottom third, dollars per trade:
      discovery  $51 vs -$10   (9 of 10 years the top third earned more)
      holdout   $245 vs  $90   (5 of 7 years)
  As a FILTER it loses total money (it drops two thirds of a profitable strategy). As a 2x
  SIZE TILT on the top third it lifted annualised MAR 0.97 -> 1.37 in discovery and 2.50 -> 2.86
  in the holdout, profit factor up in both, drawdown about 30% higher. That is a sizing rule,
  not a new entry condition, and this file is its honest test.

WHAT IT DOES
  The NOISE paper leg, core frozen exactly as deployed (NOISE_1_1_SBS_V90.py), every trade
  taken. A trade whose prior mom_bars-bar move in its own direction, measured at the DECISION
  bar (the bar before the fill) in units of the 14-bar ATR, is at least mom_atr is sized
  tilt_x contracts instead of one. Nothing about NOISE itself moves.

HOW A TILT IS EXPRESSED
  The engine prices one contract per trade and subtracts the job's cost once per trade. A
  tilted trade here reports pnl_points * tilt_x minus (tilt_x - 1) * HOUSE_COST_PTS, so the
  extra contract(s) pay their own round-trip cost too (NQ house cost 0.533 pts; this file is
  NQ-only). Drawdown, PF and every other statistic are then computed by the engine on the
  tilted stream, the same way it scores an ML size tilt.

CAUSALITY
  The move is read at the decision bar from closes at or before it. The trade's direction is
  the position sign the parent already decided on that bar. No bar at or after the fill is
  touched.

FENCED
  Auto-Validate widens declared ranges when the optimum sits near an edge; a pre-registered
  neighbourhood is NOT binding unless the strategy enforces it. An out-of-set configuration is
  REFUSED (returns None), never clamped. 3 x 3 x 2 = 18 configurations.
  The tilt_x=1.0 case is deliberately NOT in the set: the untilted control is run #243 itself
  (same window, same costs), and the judgement is "does the tilted leg beat #243 on MAR and PF
  in walk-forward AND the lockbox".

PRE-REGISTERED READ (written before this validate ran)
  Adopt only if: PASS on the gates, PBO robust, lockbox PF >= the untilted leg's (1.36), MAR on
  the full window above the untilted 1.34, and the crowned cell is interior (not on a fence).
  The anatomy holdout (2019-2025) overlaps this validate's walk-forward window, so the WF folds
  are a re-test, not fresh evidence; the lockbox year is the only untouched slice.
"""
import importlib.util as _ilu
import os as _os
import inspect as _inspect

import numpy as _np

_HERE = _os.path.dirname(_os.path.abspath(__file__))
HOUSE_COST_PTS = 0.533          # NQ round-trip, points; the extra contract's own cost


def _load(fn, alias):
    sp = _ilu.spec_from_file_location(alias, _os.path.join(_HERE, fn))
    m = _ilu.module_from_spec(sp)
    sp.loader.exec_module(m)
    return m


_base = _load("NOISE_1_1_SBS_V90.py", "_noise_sbs_v90_momtilt_base")

STRATEGY_NAME = 'NOISE 1.1 SBS+V90 + momentum size tilt'
DESCRIPTION = ("The NOISE paper leg, core frozen as deployed, every trade taken; a trade that "
               "already had a strong prior move in its own direction is sized up. Three tilt "
               "knobs vary over a fenced pre-registered set; NOISE itself does not move.")

_AUGUR_MARKET = {"instrument": "NQ", "timeframe": "5m"}
_AUGUR_PARENT = "NOISE_1_1_SBS_V90.py"

# NOISE core, frozen at the deployed paper-leg configuration. Nothing here is searched.
_FROZEN = {k: v["default"] for k, v in _base.DEFAULT_PARAMS.items()}

DEFAULT_PARAMS = {
    "mom_bars": {
        "default": 24, "min": 18, "max": 30, "step": 6, "type": "int",
        "label": "Prior move window, bars",
        "tooltip": "How many bars back the prior move is measured (24 five-minute bars = two "
                   "hours, the window the anatomy study used).",
    },
    "mom_atr": {
        "default": 4.25, "min": 3.5, "max": 5.0, "step": 0.75, "type": "float",
        "label": "Prior move needed, in ATR",
        "tooltip": "The move in the trade's direction over the window, in units of the 14-bar "
                   "ATR, at or above which the trade is sized up. 4.25 is the study's top-third "
                   "cut-off (4.35) on the fence lattice.",
    },
    "tilt_x": {
        "default": 2.0, "min": 1.5, "max": 2.0, "step": 0.5, "type": "float",
        "label": "Size multiplier when the move is strong",
        "tooltip": "Contracts on a qualifying trade; every other trade stays at one.",
    },
}

# The pre-registered set, enforced below. 3 x 3 x 2 = 18 configurations, no more.
_ADMISSIBLE = {"mom_bars": [18, 24, 30], "mom_atr": [3.5, 4.25, 5.0], "tilt_x": [1.5, 2.0]}

PARAM_GRID_PRESETS = {"Short  (the fenced 18-cell tilt neighbourhood)": dict(_ADMISSIBLE)}


def _in_neighbourhood(kw):
    for k, allowed in _ADMISSIBLE.items():
        if k not in kw:
            continue
        if not any(abs(float(kw[k]) - float(a)) < 1e-9 for a in allowed):
            return False
    return True


def _atr14(highs, lows, closes):
    """Simple 14-bar mean of the true range (the anatomy study's definition). NaN until warm."""
    n = len(closes)
    tr = _np.full(n, _np.nan)
    if n > 1:
        hl = highs[1:] - lows[1:]
        hc = _np.abs(highs[1:] - closes[:-1])
        lc = _np.abs(lows[1:] - closes[:-1])
        tr[1:] = _np.maximum(hl, _np.maximum(hc, lc))
    out = _np.full(n, _np.nan)
    if n >= 15:
        c = _np.cumsum(_np.nan_to_num(tr))
        out[14:] = (c[14:] - c[:-14]) / 14.0
    return out


def _side_of(t):
    """Position sign from the parent's trade tuple (entry, exit, pnl, pos, entry_px)."""
    if len(t) > 3:
        s = t[3]
        if isinstance(s, str):
            return -1 if s.lower().startswith("s") else 1
        try:
            return -1 if float(s) < 0 else 1
        except (TypeError, ValueError):
            return 1
    return 1


def run_backtest(opens, highs, lows, closes, volumes=None, day_id=None, index=None,
                 mom_bars=24, mom_atr=4.25, tilt_x=2.0,
                 return_trades=False, **kw):
    if not _in_neighbourhood(dict(mom_bars=mom_bars, mom_atr=mom_atr, tilt_x=tilt_x)):
        return None          # outside the pre-registered set - refused, never clamped

    call = dict(_FROZEN)
    sp = _inspect.signature(_base.run_backtest).parameters
    hk = any(p.kind == p.VAR_KEYWORD for p in sp.values())
    if volumes is not None and ("volumes" in sp or hk):
        call["volumes"] = volumes
    if day_id is not None and ("day_id" in sp or hk):
        call["day_id"] = day_id
    if index is not None and ("index" in sp or hk):
        call["index"] = index
    r = _base.run_backtest(opens, highs, lows, closes, return_trades=True, **call)
    if not r or not r.get("trades"):
        return None

    h = _np.asarray(highs, float); l = _np.asarray(lows, float); c = _np.asarray(closes, float)
    atr = _atr14(h, l, c)
    n = len(c)
    mb = int(mom_bars)
    tilted = []
    n_tilt = 0
    for t in r["trades"]:
        dec = int(t[0]) - 1                       # the decision bar is the one before the fill
        pnl = float(t[2])
        size = 1.0
        if dec - mb >= 0 and dec < n and atr[dec] > 0 and _np.isfinite(atr[dec]):
            move = (c[dec] - c[dec - mb]) / atr[dec] * _side_of(t)
            if move >= float(mom_atr):
                size = float(tilt_x)
        if size != 1.0:
            n_tilt += 1
            pnl = pnl * size - (size - 1.0) * HOUSE_COST_PTS
        tilted.append((t[0], t[1], pnl) + tuple(t[3:]))

    pnls = _np.array([float(t[2]) for t in tilted], float)
    wins = pnls[pnls > 0]
    losses = pnls[pnls < 0]
    gw = float(wins.sum())
    gl = float(-losses.sum())
    cum = _np.cumsum(pnls)
    peak = _np.maximum.accumulate(cum)
    out = {
        "total_pnl": float(pnls.sum()), "num_trades": int(len(pnls)),
        "win_rate": float(100.0 * len(wins) / len(pnls)),
        "profit_factor": (gw / gl) if gl > 1e-9 else (float("inf") if gw > 0 else 0.0),
        "max_drawdown": float((cum - peak).min()),
        "avg_pnl": float(pnls.mean()), "wins": int(len(wins)), "losses": int(len(losses)),
        "n_tilted": int(n_tilt),
    }
    if return_trades:
        out["trades"] = tilted
    return out
