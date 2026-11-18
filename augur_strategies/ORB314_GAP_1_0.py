"""
ORB314 GAP 1.0 - ORB #314 (ORB_3_6_R6.py) traded ONLY on big-gap days. Family ORB.

ORIGIN (w132 alpha hunt, lane ORB, 2026-11-18): W132_ALPHA.md leg NEW_ORB314_gap_gt0p60_ATR
($12,854/yr, book +1 corr 0.27). Harness: C:/EdgeLog/_anatomy_cache/t242_orb/w132r2/orb314_overlays.py, which ran
#314's fixed champion through ORB_3_6_R6.py and kept a trade only when its entry day had gatr > 0.60.
Prereg C:/EdgeLog/manager/prereg/PREREG_orb314_gap_validate_2026-11-18.md.

WHAT THIS IS
  ORB_3_6_R6.py unchanged (same core loop, same DEFAULT_PARAMS = same five open knobs and ranges as run #314), plus ONE
  FIXED gate that is not a parameter and is never tuned:

    trade the session only if |RTH open - prior RTH close| > 0.60 x ATR14

  per session s (sessions = the day_id blocks the core walks; #314 runs on the RTH master, so a session = 09:30-16:00):
    open_s   = open of the session's first bar (known at 09:30, before any ORB entry, which needs the opening range)
    pc_s     = close of the last bar of session s-1
    TR_s     = max(H_s - L_s, |H_s - pc_s|, |L_s - pc_s|)   (session high / low; first session: H - L)
    ATR14_s  = mean(TR_{s-14} .. TR_{s-1})                  (14 PRIOR sessions only; today never used)
    gate_s   = |open_s - pc_s| / ATR14_s > 0.60             (sessions with fewer than 14 prior sessions: no trade)
  This is the harness's gatr exactly (tr.rolling(14).mean().shift(1)).

ADJ PRICES: ROLL_SIGNAL = "difference" -> on the no-adj master the engine hands this file the Panama difference-adjusted
series (the db_adj series), which is what the harness built the gate from. The ORB core is point logic (ranges), so it
is unchanged by the shift; fills and P&L are re-priced to raw by the engine as for #314.

The gate removes trades from #314's own walk (a post-filter on the entry session), exactly as the harness weighted
#314's trade list; stats are rebuilt from the kept trades with the core's own formulas.
"""
# AUGUR-SOURCE: claude-review
import importlib.util as _ilu
import os as _os

import numpy as np

_HERE = _os.path.dirname(_os.path.abspath(__file__))
_sp = _ilu.spec_from_file_location("_orb36_r6_for_gap", _os.path.join(_HERE, "ORB_3_6_R6.py"))
_r6 = _ilu.module_from_spec(_sp)
_sp.loader.exec_module(_r6)

GAP_ATR_MIN = 0.60      # FIXED gate (prereg); not a knob
ATR_N = 14

STRATEGY_NAME = "ORB314 GAP 1.0 - ORB #314, big-gap days only"
DESCRIPTION = ("ORB #314's file (same five open knobs) traded only when |RTH open - prior RTH close| is above 0.60 x the "
               "daily ATR14 of the 14 prior sessions. The gate is fixed, not tuned.")
_AUGUR_MARKET = {"instrument": "NQ", "timeframe": "5m"}
_AUGUR_PARENT = "ORB_3_6_R6.py"
ROLL_SIGNAL = "difference"

DEFAULT_PARAMS = dict(_r6.DEFAULT_PARAMS)   # identical param space to run #314


def _session_gate(o, h, l, c, did):
    """bar-index -> session number, and a bool per session: True = the gap gate is open. Causal."""
    n = len(c)
    starts = np.r_[0, np.flatnonzero(did[1:] != did[:-1]) + 1]
    ends = np.r_[starts[1:], n]
    s_hi = np.maximum.reduceat(h, starts); s_lo = np.minimum.reduceat(l, starts)
    s_op = o[starts]; s_cl = c[ends - 1]
    pc = np.r_[np.nan, s_cl[:-1]]
    tr = np.fmax(s_hi - s_lo, np.fmax(np.abs(s_hi - pc), np.abs(s_lo - pc)))
    atr = np.full(len(starts), np.nan)
    if len(starts) > ATR_N:
        cs = np.r_[0.0, np.cumsum(tr)]
        k = np.arange(ATR_N, len(starts))
        atr[k] = (cs[k] - cs[k - ATR_N]) / ATR_N
    with np.errstate(invalid="ignore", divide="ignore"):
        ratio = np.abs(s_op - pc) / atr
    gate = np.isfinite(ratio) & (atr > 0) & (ratio > GAP_ATR_MIN)
    sess_of_bar = np.repeat(np.arange(len(starts)), ends - starts)
    return sess_of_bar, gate


def run_backtest(opens, highs, lows, closes, volumes=None, day_id=None,
                 return_trades=False, return_levels=False, _stop_event=None, _pause_event=None, **params):
    o = np.asarray(opens, float); h = np.asarray(highs, float)
    l = np.asarray(lows, float); c = np.asarray(closes, float)
    n = len(c)
    if n < 10 or day_id is None or len(day_id) != n:
        return None
    did = np.asarray(day_id)
    res = _r6.run_backtest(o, h, l, c, volumes=volumes, day_id=day_id, return_trades=True,
                           return_levels=return_levels, _stop_event=_stop_event, _pause_event=_pause_event, **params)
    if not res or not res.get("trades"):
        return None
    sess_of_bar, gate = _session_gate(o, h, l, c, did)
    keep = [bool(gate[sess_of_bar[int(t[0])]]) for t in res["trades"]]
    trades = [t for t, k in zip(res["trades"], keep) if k]
    if not trades:
        return None
    pnls = np.array([float(t[2]) for t in trades], float)
    wins = pnls[pnls > 0]; losses = pnls[pnls < 0]
    gw = float(wins.sum()); gl = float(-losses.sum())
    cum = np.cumsum(pnls); peak = np.maximum.accumulate(cum)
    out = {
        "total_pnl": float(pnls.sum()), "num_trades": int(len(pnls)),
        "win_rate": float(100.0 * len(wins) / len(pnls)),
        "profit_factor": (gw / gl) if gl > 1e-9 else (float("inf") if gw > 0 else 0.0),
        "max_drawdown": float((cum - peak).min()),
        "avg_pnl": float(pnls.mean()), "wins": int(len(wins)), "losses": int(len(losses)),
    }
    if return_trades:
        out["trades"] = trades
    if return_levels and "levels" in res:
        out["levels"] = [v for v, k in zip(res["levels"], keep) if k]
    return out
