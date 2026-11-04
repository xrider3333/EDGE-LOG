"""
ORB 3.6 R6 + M4 OR-EDGE LOCK, FROZEN arm (test 244 E2 pair, MANAGER #148). Pair note: E2_orb314_m4_pair_2026-11-03.md.

#314's own knobs keep their validate ranges (copied from ORB_3_6_R6.py DEFAULT_PARAMS, so the search space is #314's).
On top sits test 244's M4 structure lock, OR-edge level, with its two knobs IN the search space:
    arm: once the trade's best open profit (bar highs for a long, lows for a short, through bar j) reaches m4_arm_R x risk,
    exit: the first bar j whose CLOSE is back through the opening-range edge the move cleared (long: close < OR high of the
          session's first m4_or_bars bars; short: close > OR low) -> filled at the NEXT bar's open.
Never acts on a trade's exit bar; on a leg that exits at bar x's open it acts only up to bar x-2 (fill at x-1's open).
Risk = the leg's own risk from return_levels. Everything read is known at bar j's close (no look-ahead).
The FROZEN arm is ORB_3_6_R6_M4F.py: the same file with m4 pinned at test 244's best cell (A 1.0R, OR 6 bars).
"""
import importlib.util as _ilu
import os as _os

import numpy as np

_SRC = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "ORB_3_6_R6.py")
_spec = _ilu.spec_from_file_location("_orb36_r6_m4f", _SRC)
_base = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_base)

STRATEGY_NAME = "ORB 3.6 R6 + M4 OR-edge lock (frozen 1.0R / OR 6)"
DESCRIPTION = ("ORB #314's search space plus test 244's M4 lock (close back through the opening-range edge after the trade "
               "reached A x risk, exit next open), with the lock's arm and OR length searched alongside #314's knobs.")

_AUGUR_MARKET = {"instrument": "NQ", "timeframe": "5m"}
_AUGUR_PARENT = "ORB_3_6_R6.py"
_BASE_KEYS = tuple(_base.DEFAULT_PARAMS)

DEFAULT_PARAMS = dict(_base.DEFAULT_PARAMS)
DEFAULT_PARAMS.update({
    "m4_arm_R":   {"default": 1.0, "min": 1.0, "max": 1.0, "step": 0.25, "type": "float", "label": "Lock arms at (x risk) - FROZEN at test 244 best"},
    "m4_or_bars": {"default": 6,   "min": 6,   "max": 6,   "step": 2,    "type": "int",   "label": "Lock OR length (bars) - FROZEN at test 244 best"},
})

PARAM_GRID_PRESETS = {
    "Short - test 244 best cell (1.0R, OR 6)": {"m4_arm_R": [1.0], "m4_or_bars": [6]},
    }


def overlay(trades, levels, o, h, l, c, did, arm_R, or_n):
    """[(entry_bar, exit_bar, raw_pts, side, entry_px, ...)] -> same list with the lock's exits (raw pts, before cost)."""
    n = len(c)
    start = np.zeros(n, dtype=int)
    for i in range(1, n):
        start[i] = start[i - 1] if did[i] == did[i - 1] else i
    out = []
    for t, lv in zip(trades, levels):
        e, x, raw, sd, ep = int(t[0]), int(t[1]), float(t[2]), int(t[3]), float(t[4])
        risk = float(lv.get("risk") or 0.0)
        at_open = abs((ep + sd * raw) - o[x]) < 1e-9
        last = x - 1 if at_open else x
        s0 = start[e]
        orh, orl = h[s0:s0 + int(or_n)].max(), l[s0:s0 + int(or_n)].min()   # read only once bar s0+or_n-1 has closed
        res, xb, run = raw, x, 0.0
        if risk > 0:
            for j in range(e, last):
                run = max(run, sd * ((h[j] if sd > 0 else l[j]) - ep))
                if j < s0 + int(or_n) - 1 or run < arm_R * risk:
                    continue
                if (sd > 0 and c[j] < orh) or (sd < 0 and c[j] > orl):
                    res, xb = sd * (o[j + 1] - ep), j + 1
                    break
        out.append((e, xb, res, sd, ep) + tuple(t[5:]))
    return out


def run_backtest(opens, highs, lows, closes, volumes=None, day_id=None, return_trades=False,
                 m4_arm_R=1.0, m4_or_bars=6, **kw):
    p = {k: v for k, v in kw.items() if k in _BASE_KEYS}
    r = _base.run_backtest(opens, highs, lows, closes, volumes=volumes, day_id=day_id, return_trades=True,
                           return_levels=True, **p)
    if r is None:
        return None
    o, h, l, c = (np.asarray(x, float) for x in (opens, highs, lows, closes))
    T0 = r.get("trades") or []
    T = overlay(T0, r.get("levels") or [{}] * len(T0), o, h, l, c, np.asarray(day_id), float(m4_arm_R), int(m4_or_bars))
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
