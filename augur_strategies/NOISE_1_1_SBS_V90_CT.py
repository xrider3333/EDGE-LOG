"""
NOISE 1.1 SBS+V90 x HOURLY-COMPRESSION SIZE TILT — the fenced neighbourhood validate.

WHERE THIS COMES FROM
  Run #321 (NOISE_1_1_SBS_V90_SQ.py, 2026-09-07) PASSED every house gate with the hourly-
  compression check as a FILTER: PBO 0.10, walk-forward 7 of 8, lockbox 63 trades $38,383 at
  PF 2.02. It also showed the filter is the wrong live form - it keeps ~35% of the trades and
  earns 40% less money at a LOWER annualised MAR than the raw leg. The round-6 scan
  (tools/ttmsqz_round6_parts.py, PART C) said the right form is a SIZE TILT: every trade the
  leg takes is taken, and only the size moves. 2x on coiled-hour trades read $519,613 vs
  $395,169 raw at drawdown $18,377 vs $18,425 - more money, same drawdown - and the 1.5x
  version has been in the paper forward test as NOISE_SBS_V90_C15 since 2026-09-08.

  That scan is a re-weighting of a saved trade list. This file is the tilt as a STRATEGY, so
  Auto-Validate can judge it with its own walk-forward, lockbox, overfit and luck gates.

WHAT IT DOES
  The NOISE paper leg, core FROZEN exactly as deployed. Every trade is kept. A trade decided
  while the higher-timeframe squeeze was compressed is sized `tilt_mult` contracts; every
  other trade is sized 1. Four gate/size knobs vary over a small pre-registered set and
  nothing about NOISE itself moves.

THE COST CONVENTION - READ THIS BEFORE TRUSTING ANY NUMBER
  The engine subtracts `cost_pts` ONCE per trade, whatever its size. A trade at size s
  honestly nets s*(pnl - cost). So this file returns, as the trade's points,
        s*pnl - (s - 1)*cost
  which after the engine's own subtraction lands on exactly s*(pnl - cost). That is the
  round-6 scan's convention (it multiplied dollars that were already net of cost), so the
  two agree to the dollar - checked, not assumed, before this file was queued. The house
  NQ cost is baked in below; the job that runs this file MUST pass cost_pts = 0.533, and
  the parity check asserts it.

THE COMPRESSION STATE
  Shared with run #321's file by import - the same function, so a PASS there and a read
  here are of the same signal. It is the LAST COMPLETE higher-timeframe bar as of the
  decision bar (the bar before the fill), which is also what the deployed C15 paper leg
  reads (augur_engine/ml_keel._squeeze60 reads the previous complete 60m group at the fill
  bar - the two coincide on every bar; the group-boundary cases were walked by hand).

WHY RE-WEIGHTING TRADES IS LEGITIMATE HERE
  Scaling a trade cannot change any other only if nothing downstream depends on it. Checked
  for this leg before run #321: trades never overlap (0 of 4,416), and every NOISE filter
  reads the prior session, never the trade history. A tilt adds and removes nothing, so it
  is even safer than the filter was.

FENCED
  Auto-Validate widens declared ranges when the optimum sits near an edge, so a declared
  neighbourhood is NOT binding unless the strategy enforces it (TTM runs 290/293 were lost
  that way, 57-63 thousand dollars of lockbox each). An out-of-set configuration here is
  REFUSED, never clamped - clamping would run one thing and report another.

PRE-REGISTERED BAR (set before the job was queued, judged on the run doc, never re-cut)
  verdict PASS, or WEAK where the overfit check is the ONLY failing gate; AND the lockbox
  earns at least the raw leg's ($60,001 on this window) at a lockbox drawdown no more than
  25% above the raw leg's; AND annualised MAR at least the raw leg's. A tilt that only
  scales money AND drawdown together is leverage, not an edge, and fails this bar.
"""
import importlib.util as _ilu
import inspect as _inspect
import os as _os

import numpy as _np

_HERE = _os.path.dirname(_os.path.abspath(__file__))


def _load(fn, alias):
    sp = _ilu.spec_from_file_location(alias, _os.path.join(_HERE, fn))
    m = _ilu.module_from_spec(sp)
    sp.loader.exec_module(m)
    return m


_base = _load("NOISE_1_1_SBS_V90.py", "_noise_sbs_v90_tilt_base")
_sq = _load("NOISE_1_1_SBS_V90_SQ.py", "_noise_sbs_v90_sq_for_tilt")   # run #321's gate, by import

STRATEGY_NAME = 'NOISE 1.1 SBS+V90 x hourly-compression size tilt'
DESCRIPTION = ("The NOISE paper leg, core frozen as deployed, every trade kept; trades decided "
               "while the higher-timeframe squeeze was compressed are sized tilt_mult contracts, "
               "the rest one. Four gate/size knobs vary over a fenced pre-registered set.")

_AUGUR_MARKET = {"instrument": "NQ", "timeframe": "5m"}
_AUGUR_PARENT = "NOISE_1_1_SBS_V90.py"

# House NQ round-trip cost in points. The engine subtracts this once per trade; the tilt
# pre-subtracts the (s-1) extra shares so a size-s trade nets s*(pnl-cost). A job that passes
# a different cost_pts would double-count - the parity check refuses to queue on any other.
_COST_PTS = 0.533

_FROZEN = {k: v["default"] for k, v in _base.DEFAULT_PARAMS.items()}

DEFAULT_PARAMS = {
    "gate_tf_min": {
        "default": 60, "min": 30, "max": 60, "step": 30, "type": "int",
        "label": "Verification timeframe, minutes",
        "tooltip": "60 = the hourly frame the round-6 scan and the paper C15 leg read; 30 = "
                   "run #321's crowned setting.",
    },
    "gate_len": {
        "default": 20, "min": 16, "max": 20, "step": 4, "type": "int",
        "label": "Verification squeeze length",
        "tooltip": "20 = published; 16 = run #321's crowned setting.",
    },
    "gate_ratio": {
        "default": 1.0, "min": 1.0, "max": 1.15, "step": 0.15, "type": "float",
        "label": "Compression threshold on the verification timeframe",
        "tooltip": "Bollinger width over Keltner width. 1.0 = Carter's squeeze exactly and "
                   "the paper C15 leg; 1.15 = run #321's crowned setting.",
    },
    "tilt_mult": {
        "default": 1.5, "min": 1.5, "max": 2.0, "step": 0.5, "type": "float",
        "label": "Size on compressed-hour trades (others are 1.0)",
        "tooltip": "1.5 = the deployed C15 paper leg; 2.0 = the round-6 scan's headline cell.",
    },
}

# 2 x 2 x 2 x 2 = 16 configurations. Enforced below; nothing outside runs.
_ADMISSIBLE = {"gate_tf_min": [30, 60], "gate_len": [16, 20],
               "gate_ratio": [1.0, 1.15], "tilt_mult": [1.5, 2.0]}

PARAM_GRID_PRESETS = {"Short  (the fenced 16-cell tilt neighbourhood)": dict(_ADMISSIBLE)}


def _in_neighbourhood(kw):
    for k, allowed in _ADMISSIBLE.items():
        if k not in kw:
            continue
        if not any(abs(float(kw[k]) - float(a)) < 1e-9 for a in allowed):
            return False
    return True


def run_backtest(opens, highs, lows, closes, volumes=None, day_id=None, index=None,
                 gate_tf_min=60, gate_len=20, gate_ratio=1.0, tilt_mult=1.5,
                 return_trades=False, **kw):
    if not _in_neighbourhood(dict(gate_tf_min=gate_tf_min, gate_len=gate_len,
                                  gate_ratio=gate_ratio, tilt_mult=tilt_mult)):
        return None          # outside the pre-registered set - refused, never clamped
    if day_id is None:
        return None

    call = dict(_FROZEN)
    sp = _inspect.signature(_base.run_backtest).parameters
    hk = any(p.kind == p.VAR_KEYWORD for p in sp.values())
    if volumes is not None and ("volumes" in sp or hk):
        call["volumes"] = volumes
    if "day_id" in sp or hk:
        call["day_id"] = day_id
    if index is not None and ("index" in sp or hk):
        call["index"] = index
    r = _base.run_backtest(opens, highs, lows, closes, return_trades=True, **call)
    if not r or not r.get("trades"):
        return None

    comp = _sq._compression(_np.asarray(highs, float), _np.asarray(lows, float),
                            _np.asarray(closes, float), day_id, index,
                            gate_tf_min, gate_len, gate_ratio)
    n = len(closes)
    s_on = float(tilt_mult)
    out_trades = []
    pnls = []
    for t in r["trades"]:
        dec = int(t[0]) - 1                       # the decision bar is the one before the fill
        on = 0 <= dec < n and bool(comp[dec])
        s = s_on if on else 1.0
        raw = float(t[2])
        pts = s * raw - (s - 1.0) * _COST_PTS     # engine then subtracts cost once -> s*(raw-cost)
        pnls.append(pts)
        tt = list(t)
        tt[2] = pts
        out_trades.append(tuple(tt))

    pnls = _np.array(pnls, float)
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
    }
    if return_trades:
        out["trades"] = out_trades
    return out
