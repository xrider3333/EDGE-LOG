"""
NOISE 1.8 CT304H_FT -- NOISE #422 (NOISE_1_8_CT304H.py) x the v12 FIXED TILTS, no model. Board test 112 (2026-11-22).

PRE-REGISTERED BEFORE ANY NEW LOOK (docs/PREREG_noise422_fixed_tilts_2026-11-22.md). The fixed tilts are FROZEN exactly as
on 2026-09-27 (augur_engine.ml_keel.fixed_tilt_sizes_v12 = arm A3 of PREREG_keel_422_parts_2026-09-27):
  compression (last complete 60-min squeeze on) 1.5x, Friday 1.5x, product capped at 3, then 0.5x before an FOMC statement.
They are NOT knobs here and are never tuned. Each trade's size = #422's own tilt size (1.0 / tilt_mult) x the fixed-tilt
multiplier read at the trade's ENTRY bar (a-priori rules; nothing learned, nothing read after the entry bar).
The open ranges are #422's parent ranges, unchanged (gate_len 16/20/24, gate_ratio 0.85/1.0/1.15, tilt_mult 1.25/1.5/1.75).
Cost: same convention as the parent - size-s trade = s*raw - (s-1)*0.533, the engine subtracts cost once.
"""
import importlib.util as _ilu
import os as _os

import numpy as _np

_HERE = _os.path.dirname(_os.path.abspath(__file__))
_sp = _ilu.spec_from_file_location("_noise_ct304h_for_ft", _os.path.join(_HERE, "NOISE_1_8_CT304H.py"))
_p = _ilu.module_from_spec(_sp)
_sp.loader.exec_module(_p)

STRATEGY_NAME = "NOISE 1.8 #422 x frozen v12 fixed tilts (no model)"
DESCRIPTION = ("NOISE #422 with the v12 fixed size tilts frozen on: compression 1.5x, Friday 1.5x, cap 3, "
               "half size before an FOMC statement. Pre-registered board test 112; the tilts are not tuned.")
_AUGUR_MARKET = {"instrument": "NQ", "timeframe": "5m"}
_AUGUR_PARENT = "NOISE_1_8_CT304H.py"
REQUIRED_LOOKBACK_SESSIONS = _p.REQUIRED_LOOKBACK_SESSIONS
_COST_PTS = _p._COST_PTS
DEFAULT_PARAMS = _p.DEFAULT_PARAMS
PARAM_GRID_PRESETS = _p.PARAM_GRID_PRESETS
_ADMISSIBLE = _p._ADMISSIBLE


def _fixed(opens, highs, lows, closes, volumes, day_id, index, entry_bars):
    from augur_engine import ml_keel as _K
    A = {"open": _np.asarray(opens, float), "high": _np.asarray(highs, float), "low": _np.asarray(lows, float),
         "close": _np.asarray(closes, float), "day_id": _np.asarray(day_id), "index": index,
         "volume": _np.asarray(volumes if volumes is not None else _np.zeros(len(closes)), float)}
    return _K.fixed_tilt_sizes_v12(A, entry_bars)


def run_backtest(opens, highs, lows, closes, volumes=None, day_id=None, index=None,
                 gate_len=20, gate_ratio=1.0, tilt_mult=1.5,
                 return_trades=False, return_levels=False, **kw):
    r = _p.run_backtest(opens, highs, lows, closes, volumes=volumes, day_id=day_id, index=index,
                        gate_len=gate_len, gate_ratio=gate_ratio, tilt_mult=tilt_mult,
                        return_trades=True, return_levels=return_levels, **kw)
    if not r or not r.get("trades") or index is None:
        return None
    T = r["trades"]; s0 = _np.asarray(r["trade_sizes"], float); c = _COST_PTS
    k = _fixed(opens, highs, lows, closes, volumes, day_id, index, [int(t[0]) for t in T])
    out_trades, pnls, sizes = [], [], []
    for t, s, m in zip(T, s0, k):
        raw = (float(t[2]) + (s - 1.0) * c) / s          # undo the parent's fold
        S = float(s * m)
        pts = S * raw - (S - 1.0) * c
        tt = list(t); tt[2] = pts; out_trades.append(tuple(tt)); pnls.append(pts); sizes.append(S)
    pnls = _np.array(pnls, float); wins = pnls[pnls > 0]; losses = pnls[pnls < 0]
    gw = float(wins.sum()); gl = float(-losses.sum()); cum = _np.cumsum(pnls); peak = _np.maximum.accumulate(cum)
    out = {"total_pnl": float(pnls.sum()), "num_trades": int(len(pnls)), "win_rate": float(100.0 * len(wins) / len(pnls)),
           "profit_factor": (gw / gl) if gl > 1e-9 else (float("inf") if gw > 0 else 0.0),
           "max_drawdown": float((cum - peak).min()), "avg_pnl": float(pnls.mean()), "wins": int(len(wins)), "losses": int(len(losses))}
    if return_trades:
        out["trades"] = out_trades; out["trade_sizes"] = sizes; out["size_cost_pts"] = c
        for key in ("decisions", "levels"):
            if key in r:
                out[key] = r[key]
    return out
