"""
ORB 3.6 R6 + BAR TRAIL ARMED AT +0.25R (MANAGER #149, owner 11-04). One cell, pre-WF read. Note: PREWF_orb314_trail025_2026-11-04.md.

Every knob is #314's champion. #314 itself has NO trail (trail_bars 0), so the distance is this strategy's own trail_bars rule at
the function's default N = 3: stop = lowest low (long) / highest high (short) of the last N bars before this one, from the entry bar.
Arm: the first close after entry at or beyond entry + 0.25 x risk; acts from the NEXT bar (the breakeven's own timing).
Each bar the leg's stop (initial, then breakeven) and the trail combine as the tighter, checked first, gap through = fill at the open.
Set ta_arm_R to 99 and the file is #314, trade for trade.
GAUNTLET (11-06, PREWF_orb314_trail025_2026-11-04.md + addendum): the gauntlet door co-tunes, so ta_arm_R is ranged
0.25..1.0 and ta_bars 2..5; the PREWF cell (0.25R, 3 bars) is the default. The crown knobs keep #314's validate ranges.
"""
# AUGUR-SOURCE: claude-review
import importlib.util as _ilu
import os as _os

import numpy as np

_SRC = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "ORB_3_6_R6.py")
_spec = _ilu.spec_from_file_location("_orb36_r6_ta", _SRC)
_base = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_base)

STRATEGY_NAME = "ORB 3.6 R6 + 3-bar trail armed at +0.25R"
DESCRIPTION = "ORB #314's champion with its bar-trail rule (N = 3) switched on only after a close at +0.25R."

_AUGUR_MARKET = {"instrument": "NQ", "timeframe": "5m"}
_AUGUR_PARENT = "ORB_3_6_R6.py"

_CHAMP = {"or_bars": 2, "trade_mode": "First-candle dir", "stop_frac": 2.5, "breakout_buf": 0.25, "close_confirm": True,
          "partial_exit_R": 0.0, "trail_bars": 0, "be_after_R": 0.5, "target_R": 5.0, "atr_filter": 0.75,
          "vpace_filter": 0.8, "flat_eod": True, "skip_holidays": True}

DEFAULT_PARAMS = {k: dict(_base.DEFAULT_PARAMS[k], default=v) for k, v in _CHAMP.items()}
DEFAULT_PARAMS.update({
    "ta_arm_R": {"hard_max": 1, "default": 0.25, "min": 0.25, "max": 1.0,  "step": 0.25, "type": "float", "label": "Trail arms at a close of (x risk)"},
    "ta_bars":  {"default": 3,    "min": 2,    "max": 5,    "step": 1,    "type": "int",   "label": "Trail distance (prior bars)"},
})
# hard ceiling (owner GO 11-09, #195): runs #499/#504 widened stop_frac past the file range to 2.75
DEFAULT_PARAMS["stop_frac"] = dict(DEFAULT_PARAMS["stop_frac"], hard_max=2.5)

PARAM_GRID_PRESETS = {"Short - the one cell (0.25R, 3 bars)": {"ta_arm_R": [0.25], "ta_bars": [3]}}


def overlay(trades, levels, o, h, l, c, arm_R, n_bars, be_R):
    """[(entry_bar, exit_bar, raw_pts, side, entry_px, ...)] -> same list with the trail's exits (raw pts, before cost)."""
    out = []
    for t, lv in zip(trades, levels):
        e, x, raw, sd, ep = int(t[0]), int(t[1]), float(t[2]), int(t[3]), float(t[4])
        risk = float(lv.get("risk") or 0.0)
        stop, armed, be, res, xb = ep - sd * risk, False, False, raw, x
        for j in range(e + 1, x + 1):
            lvl = (max(stop, ep) if be else stop) if sd > 0 else (min(stop, ep) if be else stop)
            if armed:
                a = max(e, j - n_bars)
                tr = l[a:j].min() if sd > 0 else h[a:j].max()
                lvl = max(lvl, tr) if sd > 0 else min(lvl, tr)
            hit = l[j] <= lvl if sd > 0 else h[j] >= lvl
            if hit:
                if armed:                      # with the trail off the leg's own exit stands untouched
                    px = o[j] if sd * (o[j] - lvl) < 0 else lvl
                    res, xb = sd * (px - ep), j
                break
            if j < x:
                gain = sd * (c[j] - ep)
                armed = armed or gain >= arm_R * risk
                be = be or (be_R > 0 and gain >= be_R * risk)
        out.append((e, xb, res, sd, ep) + tuple(t[5:]))
    return out


def run_backtest(opens, highs, lows, closes, volumes=None, day_id=None, return_trades=False,
                 ta_arm_R=0.25, ta_bars=3, **kw):
    p = dict(_CHAMP)
    p.update({k: v for k, v in kw.items() if k in _CHAMP})
    r = _base.run_backtest(opens, highs, lows, closes, volumes=volumes, day_id=day_id, return_trades=True,
                           return_levels=True, **p)
    if r is None:
        return None
    o, h, l, c = (np.asarray(x, float) for x in (opens, highs, lows, closes))
    T = overlay(r.get("trades") or [], r.get("levels") or [], o, h, l, c, float(ta_arm_R), int(ta_bars), float(p["be_after_R"]))
    pn = np.asarray([float(t[2]) for t in T], float)
    wins, losses = pn[pn > 0], pn[pn < 0]
    gw, gl = float(wins.sum()), float(-losses.sum())
    cum = np.cumsum(pn) if len(pn) else np.zeros(1)
    out = {"total_pnl": float(pn.sum()), "num_trades": int(len(pn)),
           "win_rate": float(100.0 * len(wins) / len(pn)) if len(pn) else 0.0,
           "profit_factor": (gw / gl) if gl > 1e-9 else (float("inf") if gw > 0 else 0.0),
           "max_drawdown": float((cum - np.maximum.accumulate(cum)).min()) if len(pn) else 0.0,
           "avg_pnl": float(pn.mean()) if len(pn) else 0.0, "wins": int(len(wins)), "losses": int(len(losses))}
    if return_trades:
        out["trades"] = T
    return out
