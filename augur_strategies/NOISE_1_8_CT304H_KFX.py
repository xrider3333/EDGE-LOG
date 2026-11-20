# AUGUR-SOURCE: claude-review
"""NOISE 1.8 CT304H KFX - the book's NOISE leg (NOISE_1_8_CT304H.py, #463 params) with the KEEL v12 FIXED size
package written out as plain rules: a wider hourly-squeeze tilt and a Friday tilt. No model, no learned gate.

Provenance: CUSTOM-ML 11-20 re-score of the 10-05 fixed-sizing ablation (tools/noise_fixed_ablation.py,
docs/PREREG_noise_fixed_ablation_2026-10-05.md) under the owner's loose screen (11-14). Book #463 rebuilt basis
WF 2016-07..2025-06: the full fixed package (sq60 x1.5, Friday x1.5, FOMC-afternoon x0.5) on the book's NOISE leg adds
+$20,797/yr at book DD $52,238 unchanged (its size-matched plain-extra-NOISE twin adds +$8,453/yr); squeeze alone
+$10,961/yr (twin +$4,162), Friday alone +$7,066/yr (twin +$4,499). Legs: C:/EdgeLog/custom_ml/w132_rescan/r1120/.
Warnings carried from the 10-05 test: Friday lost the untuned 2011-16 block and sat at the 96.5th pct of its own-size
shuffle; the squeeze lead is carried by its top 20 trades, about half in March 2020; standalone squeeze tilt LOWERS
the NOISE leg's own ROC (the gain is a book-only gain) - judge this validate's standalone numbers with that in mind.
FOMC (0.5x after 14:00 on FOMC days, 7 trades a year) is left out: below the 20-trade line and needs a calendar.

Rules: the CT304H trades are untouched; size = (tilt_mult if the hourly squeeze was compressed at the decision bar
else 1) x (fri_mult if the fill bar is a Friday else 1); cost folded the CT304H way (pts = s*raw - (s-1)*cost).
Parity: tilt_mult 1.75, fri_mult 1.0, gate 20 / 1.15 reproduces CT304H at the #463 params trade for trade.
NEEDS A SECOND-LANE READ before its result is used.
"""
import importlib.util as _ilu
import os as _os

import numpy as _np
import pandas as _pd

_HERE = _os.path.dirname(_os.path.abspath(__file__))


def _load(fn, alias):
    sp = _ilu.spec_from_file_location(alias, _os.path.join(_HERE, fn))
    m = _ilu.module_from_spec(sp)
    sp.loader.exec_module(m)
    return m


_ct = _load("NOISE_1_8_CT304H.py", "_ct304h_for_kfx")

STRATEGY_NAME = "NOISE 1.8 CT304H x KEEL fixed package (squeeze + Friday tilt, plain rules)"
DESCRIPTION = ("The book's NOISE leg; trades sized up while the hourly squeeze is compressed and on Fridays. "
               "Plain fixed rules from the KEEL v12 fixed package; no model.")

_AUGUR_MARKET = {"instrument": "NQ", "timeframe": "5m"}
_AUGUR_PARENT = "NOISE_1_8_CT304H.py"

_PROBE_TILT = 1.25                    # an admissible CT304H tilt, used only to read which trades were compressed

DEFAULT_PARAMS = {
    "gate_len": {"default": 20, "min": 16, "max": 24, "step": 4, "type": "int",
                 "label": "Verification squeeze length (hourly frame)"},
    "gate_ratio": {"default": 1.15, "min": 0.85, "max": 1.15, "step": 0.15, "type": "float",
                   "label": "Compression threshold (Bollinger over Keltner width); 1.15 = #463"},
    "tilt_mult": {"default": 1.75, "min": 1.5, "max": 2.75, "step": 0.25, "type": "float",
                  "label": "Size on compressed-hour trades; 1.75 = #463, 2.625 ~ #463 x KEEL sq60 1.5"},
    "fri_mult": {"default": 1.5, "min": 1.0, "max": 2.0, "step": 0.25, "type": "float",
                 "label": "Size on Friday entries (KEEL v12 dow = 1.5); 1.0 = off"},
}

_ADMISSIBLE = {"gate_len": [16, 20, 24], "gate_ratio": [0.85, 1.0, 1.15],
               "tilt_mult": [1.5, 1.75, 2.0, 2.25, 2.5, 2.75], "fri_mult": [1.0, 1.25, 1.5, 1.75, 2.0]}

PARAM_GRID_PRESETS = {"Short  (the fenced 270-cell neighbourhood)": dict(_ADMISSIBLE)}


def _in_set(p):
    for k, allowed in _ADMISSIBLE.items():
        if not any(abs(float(p[k]) - float(a)) < 1e-9 for a in allowed):
            return False
    return True


def run_backtest(opens, highs, lows, closes, volumes=None, day_id=None, index=None,
                 gate_len=20, gate_ratio=1.15, tilt_mult=1.75, fri_mult=1.5,
                 return_trades=False, **kw):
    p = dict(gate_len=gate_len, gate_ratio=gate_ratio, tilt_mult=tilt_mult, fri_mult=fri_mult)
    if not _in_set(p):
        return None          # outside the pre-registered set - refused, never clamped
    if day_id is None or index is None:
        return None
    r = _ct.run_backtest(opens, highs, lows, closes, volumes=volumes, day_id=day_id, index=index,
                         gate_len=int(round(float(gate_len))), gate_ratio=float(gate_ratio),
                         tilt_mult=_PROBE_TILT, return_trades=True)
    if not r or not r.get("trades"):
        return None
    cost = float(r["size_cost_pts"])
    dow = _pd.DatetimeIndex(_pd.to_datetime(_np.asarray(index))).dayofweek
    n = len(closes)
    out_trades, pnls, sizes = [], [], []
    for t, s0 in zip(r["trades"], r["trade_sizes"]):
        raw = (float(t[2]) + (s0 - 1.0) * cost) / s0          # undo CT304H's fold
        on = abs(s0 - _PROBE_TILT) < 1e-9
        e = int(t[0])
        fri = 0 <= e < n and dow[e] == 4
        s = (float(tilt_mult) if on else 1.0) * (float(fri_mult) if fri else 1.0)
        pts = s * raw - (s - 1.0) * cost
        tt = list(t)
        tt[2] = pts
        out_trades.append(tuple(tt))
        pnls.append(pts)
        sizes.append(s)
    pnls = _np.array(pnls, float)
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
        out["trades"] = out_trades
        out["trade_sizes"] = sizes
        out["size_cost_pts"] = cost
    return out
