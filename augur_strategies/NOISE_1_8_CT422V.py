"""
NOISE 1.8 CT422V -- NOISE #422's cell with the volatility-skip MEMORY opened: 68, 160 or 252 prior sessions.

ROUND 62 (2026-09-27, NOISE.md). The volatility skip ranks yesterday's range against the sessions before it. Every
backtest ranks against up to 252; the live Webull engine can only hold ~70 sessions of QQQ 5-minute history, so live
ranks against ~68 (round 61; commit 771feccb now asks for 262 and logs TRUNCATED until a year of history exists).
Round 61 re-ran #382's cell at 68 and found 5% of trading days change and the 68 version did slightly BETTER on the
same years - a post-hoc read, never validated. This file asks the question properly: the memory length is a fenced
knob beside the skip threshold, everything else is NOISE #422's crowned configuration.

OPEN (9 cells): vol_skip_pct 92.5 / 95 / 97.5  x  vol_ref_sessions 68 / 160 / 252.
FROZEN: run #304's crown core, and #422's hourly compression tilt (60-minute squeeze, length 20, threshold 1.15,
compressed-hour trades sized 1.75x). The centre (95, 252) reproduces #422's crowned cell trade for trade.

PRE-REGISTERED BAR (written before the job was queued; NOISE.md round 62):
  The question is NON-INFERIORITY of the live memory, not a new crown. The 68-session cell at the crown's 95 skip is
  ACCEPTABLE for live if (a) the validate is not FAIL, and (b) replayed continuously on one tape it keeps profit
  factor within 0.02 of the 252-session cell, or above it, in BOTH the walk-forward and the sealed year. If met, the
  live engine's short window is not a defect and the year-of-history backfill is optional. If not, the backfill (or a
  daily-range bridge) is required before the live leg trusts its skip. Whatever cell the search crowns is REPORTED,
  never adopted from this round - the skip threshold is not what is being asked.

Each memory length gets its OWN private copy of NOISE_1_0.py with only the volatility function's reference-length
default changed, so no setting leaks between cells or processes. FENCED: out-of-set cells are refused, never clamped.
The house cost 0.533 is baked into the size fold (pts = s*raw - (s-1)*cost; the engine subtracts cost once).
READ THE LOCKBOX CONTINUOUSLY - the saved strip is a cold-restart reload for NOISE.
"""
import importlib.util as _ilu
import os as _os

import numpy as _np

_HERE = _os.path.dirname(_os.path.abspath(__file__))


def _load(fn, alias):
    sp = _ilu.spec_from_file_location(alias, _os.path.join(_HERE, fn))
    m = _ilu.module_from_spec(sp)
    sp.loader.exec_module(m)
    return m


_sq = _load("NOISE_1_1_SBS_V90_SQ.py", "_noise_sq_for_ct422v")
_N10 = {}


def _base(ref):
    """A private NOISE_1_0 whose volatility skip ranks against `ref` prior sessions."""
    ref = int(ref)
    if ref not in _N10:
        m = _load("NOISE_1_0.py", "_n10_ct422v_ref%d" % ref)
        d = list(m._vol_percentile.__defaults__)
        d[0] = ref
        m._vol_percentile.__defaults__ = tuple(d)
        _N10[ref] = m
    return _N10[ref]


STRATEGY_NAME = "NOISE 1.8 #422 cell x volatility-skip memory (68 / 160 / 252 sessions)"
DESCRIPTION = ("NOISE #422's crowned configuration (live crown core + hourly squeeze 1.75x) with the volatility "
               "skip's ranking memory opened beside its threshold - does the ~68-session memory the live engine "
               "can hold trade as well as the validated 252?")

_AUGUR_MARKET = {"instrument": "NQ", "timeframe": "5m"}
_AUGUR_PARENT = "NOISE_1_8_CT304H.py"

_COST_PTS = 0.533
_FROZEN = {
    "lookback": 40, "band_mult_long": 0.75, "band_mult_short": 1.5, "exit_mode": "vwap",
    "side": "Both", "window": "all_day", "flat_eod": True, "skip_holidays": False,
    "stop_mode": "bandwidth", "stop_k": 1.75, "confirm_bars": 1,
    "daytype_mode": "skip_bot_short", "daytype_lo": 0.2, "daytype_hi": 0.8,
}
_TILT = {"tf_min": 60, "len": 20, "ratio": 1.15, "mult": 1.75}      # NOISE #422 crowned, frozen

_CENTER = {"vol_skip_pct": 95.0, "vol_ref_sessions": 252}
_ADMISSIBLE = {"vol_skip_pct": [92.5, 95.0, 97.5], "vol_ref_sessions": [68, 160, 252]}

DEFAULT_PARAMS = {
    "vol_skip_pct": {"default": 95.0, "min": 92.5, "max": 97.5, "step": 2.5, "type": "float",
                     "label": "Skip days whose prior range ranks above this percentile"},
    "vol_ref_sessions": {"default": 252, "min": 68, "max": 252, "step": 92, "type": "int",
                         "label": "Volatility-skip memory (prior sessions ranked against)",
                         "tooltip": "252 = every backtest to date; 68 = what the live engine can hold today; "
                                    "160 = about eight months. Only these three run."},
}

PARAM_GRID_PRESETS = {"Short  (the fenced 9-cell skip x memory neighbourhood)": dict(_ADMISSIBLE)}


def _in_set(p):
    for k, allowed in _ADMISSIBLE.items():
        if not any(abs(float(p[k]) - float(a)) < 1e-9 for a in allowed):
            return False
    return True


def run_backtest(opens, highs, lows, closes, volumes=None, day_id=None, index=None,
                 return_trades=False, _stop_event=None, _pause_event=None, **kw):
    p = {k: kw.get(k, v) for k, v in _CENTER.items()}
    if not _in_set(p):
        return None          # outside the pre-registered set - refused, never clamped
    if day_id is None or index is None:
        return None
    call = dict(_FROZEN, vol_skip_pct=float(p["vol_skip_pct"]))
    r = _base(int(round(float(p["vol_ref_sessions"])))).run_backtest(
        opens, highs, lows, closes, volumes=volumes, day_id=day_id, return_trades=True,
        _stop_event=_stop_event, _pause_event=_pause_event, **call)
    if not r or not r.get("trades"):
        return None
    comp = _sq._compression(_np.asarray(highs, float), _np.asarray(lows, float), _np.asarray(closes, float),
                            day_id, index, _TILT["tf_min"], _TILT["len"], _TILT["ratio"])
    n = len(closes)
    out_trades, pnls, sizes = [], [], []
    for t in r["trades"]:
        dec = int(t[0]) - 1                       # the decision bar is the one before the fill
        s = _TILT["mult"] if (0 <= dec < n and bool(comp[dec])) else 1.0
        pts = s * float(t[2]) - (s - 1.0) * _COST_PTS
        tt = list(t)
        tt[2] = pts
        out_trades.append(tuple(tt))
        pnls.append(pts)
        sizes.append(s)
    pnls = _np.array(pnls, float)
    wins, losses = pnls[pnls > 0], pnls[pnls < 0]
    gw, gl = float(wins.sum()), float(-losses.sum())
    cum = _np.cumsum(pnls)
    out = {
        "total_pnl": float(pnls.sum()), "num_trades": int(len(pnls)),
        "win_rate": float(100.0 * len(wins) / len(pnls)),
        "profit_factor": (gw / gl) if gl > 1e-9 else (float("inf") if gw > 0 else 0.0),
        "max_drawdown": float((cum - _np.maximum.accumulate(cum)).min()),
        "avg_pnl": float(pnls.mean()), "wins": int(len(wins)), "losses": int(len(losses)),
    }
    if return_trades:
        out["trades"] = out_trades
        out["trade_sizes"] = sizes
        out["size_cost_pts"] = _COST_PTS
    return out
