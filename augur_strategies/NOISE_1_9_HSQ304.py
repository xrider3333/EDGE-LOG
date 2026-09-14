"""
NOISE 1.9 HSQ304 -- the LIVE crown keeping only trades taken during an hourly squeeze.

ROUND 57 (2026-09-13, NOISE.md). Owner: "some of these configs are in an auto validate, and some aren't -
start auto validating them." Round 56's scorecard ranked every NOISE configuration on one continuous tape.
This configuration was measured there but has never been the CHAMPION of an Auto-Validate:
  it was one of run #385's 27 grid cells, and #385's search crowned the 30-minute cell instead.

WHAT THIS FILE IS
  A fenced neighbourhood: every setting that defines the configuration is frozen, and 3 knobs are open
  one step either side of the configuration's own value, which is each knob's default. 27 cells.
  An Auto-Validate needs open ranges to have a landscape (a pinned file has no overfit test, no plateau,
  no neighbours), and the fence keeps the search inside this configuration's neighbourhood: an out-of-set
  cell is REFUSED, never clamped. The validate judges whichever cell its search crowns; whether that is
  the configuration itself is read off the run.

  Scorecard reading at the centre cell (continuous 2010-06-07 to 2026-07-16, house cost 0.533):
  615 trades, profit factor 2.351, 2024 onward 2.184, sealed year 1.985.

READ THE LOCKBOX CONTINUOUSLY. The validate grades its lockbox on a cold-restart reload that for NOISE drops
a large share of the sealed year (run #382: 239 reloaded vs 314 continuous). Judge the sealed year on a
continuous replay sliced by entry time.
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


_base = _load("NOISE_1_0.py", "_n10_for_noise_1_9_hsq304")
_sq = _load("NOISE_1_1_SBS_V90_SQ.py", "_sq_for_hsq")   # run #321 compression function, by import

STRATEGY_NAME = "NOISE 1.9 live crown x hourly squeeze filter (neighbourhood)"
DESCRIPTION = ("The live NOISE crown (run 304) frozen; a trade is kept only when the squeeze on the verification timeframe was compressed at its decision bar. Centred on the textbook hourly squeeze.")

_AUGUR_MARKET = {"instrument": "NQ", "timeframe": "5m"}
_AUGUR_PARENT = "NOISE_1_0.py"

_FROZEN = {'lookback': 40, 'band_mult_long': 0.75, 'band_mult_short': 1.5, 'exit_mode': 'vwap', 'side': 'Both', 'window': 'all_day', 'flat_eod': True, 'skip_holidays': False, 'stop_mode': 'bandwidth', 'stop_k': 1.75, 'confirm_bars': 1, 'daytype_mode': 'skip_bot_short', 'daytype_lo': 0.2, 'daytype_hi': 0.8, 'vol_skip_pct': 95.0}

_CENTER = {'gate_tf_min': 60, 'gate_len': 20, 'gate_ratio': 1.0}

_ADMISSIBLE = {'gate_tf_min': [30, 60, 90], 'gate_len': [16, 20, 24], 'gate_ratio': [0.85, 1.0, 1.15]}

DEFAULT_PARAMS = {
    "gate_tf_min": {"default": 60, "min": 30, "max": 90, "step": 30, "type": "int", "label": "Squeeze verification timeframe, minutes"},
    "gate_len": {"default": 20, "min": 16, "max": 24, "step": 4, "type": "int", "label": "Squeeze length"},
    "gate_ratio": {"default": 1.0, "min": 0.85, "max": 1.15, "step": 0.15, "type": "float", "label": "Compression threshold (Bollinger width over Keltner width)"},
}

PARAM_GRID_PRESETS = {"Short  (the fenced 27-cell neighbourhood)": dict(_ADMISSIBLE)}


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
    r = _base.run_backtest(opens, highs, lows, closes, volumes=volumes, day_id=day_id,
                           return_trades=True, _stop_event=_stop_event, _pause_event=_pause_event,
                           **_FROZEN)
    if not r or not r.get("trades"):
        return None
    comp = _sq._compression(_np.asarray(highs, float), _np.asarray(lows, float),
                            _np.asarray(closes, float), day_id, index,
                            int(round(float(p["gate_tf_min"]))), int(round(float(p["gate_len"]))),
                            float(p["gate_ratio"]))
    n = len(closes)
    kept = [t for t in r["trades"] if 0 <= int(t[0]) - 1 < n and comp[int(t[0]) - 1]]
    if not kept:
        return None
    pnls = _np.array([float(t[2]) for t in kept], float)
    wins = pnls[pnls > 0]
    losses = pnls[pnls < 0]
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
        out["trades"] = kept
    return out
