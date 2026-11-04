"""NOISE #382 + OVEREXTENSION VETO (GAUNTLET w93 DISC feed, prereg
C:/EdgeLog/manager/prereg/PREREG_disc_overext_veto_2026-11-03.md, owner GO 11-03).
--------------------------------------------------------------------------------
Parent: NOISE_1_8_CT304.py (the #382 crown). Its walk is called UNCHANGED; this file only drops
trades afterwards, so every kept trade is the crown's own, size and cost included.

RULE. At the crown's SIGNAL bar (the bar before the fill, the parent's own decision-bar rule)
count how many of four context items agree with the trade's side:
  1. close vs the prior RTH session's last close,
  2. close vs the 5m 200-bar SMA,
  3. close vs the 200-bar SMA of COMPLETED 30m closes (a 30m close = a 5m bar ending on :00/:30,
     at or before the signal bar - never the forming 30m bar),
  4. the 5m 20 EMA's slope (signal bar minus the bar before).
"Agree" = above / rising for a long, below / falling for a short. A trade is SKIPPED when the
count is >= veto_k. veto_k = 5 can never trigger = the crown (parity control).

CO-TUNED (scope C3): veto_k sits in the search space next to the crown's own four knobs.

CAVEAT, stated before any number: a vetoed trade is dropped after the walk, so an entry the crown
skipped because it was already in that (vetoed) position is not re-created. This makes the veto
arm slightly conservative (fewer trades than a true live veto would take).
"""
import importlib.util as _ilu
import os as _os

import numpy as _np

_HERE = _os.path.dirname(_os.path.abspath(__file__))
_sp = _ilu.spec_from_file_location("_noise_ct304_for_oxv", _os.path.join(_HERE, "NOISE_1_8_CT304.py"))
_P = _ilu.module_from_spec(_sp)
_sp.loader.exec_module(_P)

STRATEGY_NAME = "NOISE 1.8 #382 + overextension veto"
DESCRIPTION = ("The #382 crown with entries skipped when >= veto_k of four context items "
               "already agree with the trade side. veto_k=5 = parity with NOISE_1_8_CT304.")
_AUGUR_MARKET = dict(_P._AUGUR_MARKET)
_AUGUR_PARENT = "NOISE_1_8_CT304.py"
REQUIRED_LOOKBACK_SESSIONS = _P.REQUIRED_LOOKBACK_SESSIONS

DEFAULT_PARAMS = dict(_P.DEFAULT_PARAMS)
DEFAULT_PARAMS["veto_k"] = {
    "default": 4, "min": 3, "max": 5, "step": 1, "type": "int",
    "label": "Overextension veto (skip when this many of 4 agree)",
    "tooltip": "4 = the prereg's first-named cut; 3 = the report cut; 5 = off (the crown)."}

PARAM_GRID_PRESETS = {"Short  (veto cut x crown tilt)": dict(_P._ADMISSIBLE, veto_k=[3, 4, 5])}


def _sma(a, n):
    out = _np.full(len(a), _np.nan)
    if len(a) >= n:
        cs = _np.cumsum(_np.insert(a, 0, 0.0))
        out[n - 1:] = (cs[n:] - cs[:-n]) / n
    return out


def _ema(a, n):
    k = 2.0 / (n + 1.0)
    out = _np.empty(len(a))
    out[0] = a[0]
    for i in range(1, len(a)):
        out[i] = k * a[i] + (1 - k) * out[i - 1]
    return out


def aligned_counts(closes, day_id, index):
    """Per bar: (above prior RTH close, above 5m SMA200, above completed-30m SMA200, EMA20 rising)
    as +1 / -1 / 0 (0 = not yet defined). Exposed for tests and the power screen."""
    c = _np.asarray(closes, float)
    n = len(c)
    did = _np.asarray(day_id)
    # prior session's last close
    last_of_day = _np.r_[did[1:] != did[:-1], True]
    prev_close = _np.full(n, _np.nan)
    day_close = {}
    for i in _np.flatnonzero(last_of_day):
        day_close[did[i]] = c[i]
    days = list(dict.fromkeys(did.tolist()))
    prior = {days[j]: day_close[days[j - 1]] for j in range(1, len(days))}
    for i in range(n):
        prev_close[i] = prior.get(did[i], _np.nan)
    s200 = _sma(c, 200)
    # completed 30m closes: 5m bars that END on :00 / :30 (bar start minute + 5)
    ts = index.tz_convert("US/Eastern") if getattr(index, "tz", None) is not None else index
    mins = _np.asarray(ts.minute)
    is30 = ((mins + 5) % 30) == 0
    pos30 = _np.flatnonzero(is30)
    s30 = _sma(c[pos30], 200)
    last30 = _np.searchsorted(pos30, _np.arange(n), side="right") - 1
    sma30 = _np.where(last30 >= 0, s30[_np.clip(last30, 0, None)], _np.nan)
    e20 = _ema(c, 20)
    slope = _np.r_[0.0, _np.diff(e20)]

    def sg(x):
        return _np.where(_np.isnan(x), 0, _np.sign(x))
    return _np.stack([sg(c - prev_close), sg(c - s200), sg(c - sma30), _np.sign(slope)], 1)


def run_backtest(opens, highs, lows, closes, volumes=None, day_id=None, index=None,
                 veto_k=4, return_trades=False, **kw):
    out = _P.run_backtest(opens, highs, lows, closes, volumes=volumes, day_id=day_id,
                          index=index, return_trades=True, **kw)
    if out is None or int(veto_k) >= 5 or index is None or len(index) != len(closes):
        if out is not None and not return_trades:
            for k in ("trades", "trade_sizes", "decisions", "levels"):
                out.pop(k, None)
        return out
    ag = aligned_counts(closes, day_id, index)
    n = len(closes)
    keep = []
    for q, t in enumerate(out["trades"]):
        d = int(t[0]) - 1
        side = 1 if int(t[3]) >= 0 else -1
        cnt = int((ag[d] * side > 0).sum()) if 0 <= d < n else 0
        keep.append(cnt < int(veto_k))
    keep = _np.array(keep, bool)
    if not keep.any():
        return None
    pnls = _np.array([float(t[2]) for t in out["trades"]])[keep]
    wins = pnls[pnls > 0]; losses = pnls[pnls < 0]
    gw = float(wins.sum()); gl = float(-losses.sum())
    cum = _np.cumsum(pnls)
    res = {
        "total_pnl": float(pnls.sum()), "num_trades": int(len(pnls)),
        "win_rate": float(100.0 * len(wins) / len(pnls)),
        "profit_factor": (gw / gl) if gl > 1e-9 else (float("inf") if gw > 0 else 0.0),
        "max_drawdown": float((cum - _np.maximum.accumulate(cum)).min()),
        "avg_pnl": float(pnls.mean()), "wins": int(len(wins)), "losses": int(len(losses)),
        "vetoed_trades": int((~keep).sum()),
    }
    if return_trades:
        res["trades"] = [t for t, k in zip(out["trades"], keep) if k]
        for key in ("trade_sizes", "decisions", "levels"):
            v = out.get(key)
            if isinstance(v, list) and len(v) == len(keep):
                res[key] = [x for x, k in zip(v, keep) if k]
        if "size_cost_pts" in out:
            res["size_cost_pts"] = out["size_cost_pts"]
    return res
