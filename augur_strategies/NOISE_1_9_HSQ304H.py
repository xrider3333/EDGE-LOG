"""
NOISE 1.9 HSQ304H -- the LIVE crown keeping only trades taken during an HOURLY squeeze (hourly frame fixed).

ROUND 58 (2026-09-14, NOISE.md). Owner: "auto validate anything that needs the auto validation." The live crown
with the textbook hourly squeeze filter (60-minute frame, length 20, ratio 1.0) reads profit factor 2.351 over
615 trades on a continuous replay and is on EL only as a single validate (#390), which saves no walk-forward
years, so it cannot sit beside the other NOISE rows on COMPARE > EXPLORE. Three neighbourhood Auto-Validates that
contained it (#385, #387 on the live crown; #386 on #243) all crowned a 30-MINUTE squeeze instead, where more
trades qualify.

This file keeps the question inside the hourly frame: the verification timeframe is FROZEN at 60 minutes and only
the squeeze length (16 / 20 / 24) and threshold (0.85 / 1.0 / 1.15) are open - 9 cells, the textbook setting at
the centre and as every default. The fence was drawn after the hourly frame was seen to beat the 30-minute one on
these same years, so this validate cannot un-see that selection; its walk-forward folds and overfit test still
judge the choice among hourly settings. Parity-checked: the centre reproduces 615 trades / $139,997.

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


_base = _load("NOISE_1_0.py", "_n10_for_noise_1_9_hsq304")
_sq = _load("NOISE_1_1_SBS_V90_SQ.py", "_sq_for_hsq")   # run #321 compression function, by import

STRATEGY_NAME = "NOISE 1.9 live crown x hourly squeeze filter (hourly frame fixed)"
DESCRIPTION = ("The live NOISE crown (run 304) frozen; a trade is kept only when the squeeze on the verification timeframe was compressed at its decision bar. Centred on the textbook hourly squeeze.")

_AUGUR_MARKET = {"instrument": "NQ", "timeframe": "5m"}
_AUGUR_PARENT = "NOISE_1_0.py"

_FROZEN = {'lookback': 40, 'band_mult_long': 0.75, 'band_mult_short': 1.5, 'exit_mode': 'vwap', 'side': 'Both', 'window': 'all_day', 'flat_eod': True, 'skip_holidays': False, 'stop_mode': 'bandwidth', 'stop_k': 1.75, 'confirm_bars': 1, 'daytype_mode': 'skip_bot_short', 'daytype_lo': 0.2, 'daytype_hi': 0.8, 'vol_skip_pct': 95.0}

_CENTER = {'gate_len': 20, 'gate_ratio': 1.0}

_ADMISSIBLE = {'gate_len': [16, 20, 24], 'gate_ratio': [0.85, 1.0, 1.15]}

DEFAULT_PARAMS = {
    "gate_len": {"default": 20, "min": 16, "max": 24, "step": 4, "type": "int", "label": "Squeeze length"},
    "gate_ratio": {"default": 1.0, "min": 0.85, "max": 1.15, "step": 0.15, "type": "float", "label": "Compression threshold (Bollinger width over Keltner width)"},
}

PARAM_GRID_PRESETS = {"Short  (the fenced 9-cell hourly neighbourhood)": dict(_ADMISSIBLE)}


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
                            60, int(round(float(p["gate_len"]))),
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
