"""
NOISE 1.1 SBS+V90 + HOURLY-COMPRESSION 2x SIZE TILT — the pre-registered live form.

WHERE THIS COMES FROM
  Run #321 (NOISE_1_1_SBS_V90_SQ.py, 2026-09-07) put the round-6 compression finding to a
  real Auto-Validate as a FILTER: PASS 6 of 6, walk-forward 7 of 8, PBO 0.099, lockbox 63
  trades $38,383 at PF 2.02. The edge is real per trade. But as a filter it keeps 13% of the
  trades, so it earns about 40% LESS than the ungated paper leg over the full window
  ($236,975 vs $395,169) and its annualised MAR is lower (1.13 vs 1.34). The round-6 writeup
  said this before the validate did: the live form of a per-trade edge that fires on a
  minority of trades is a SIZE TILT, not a filter. Scanned at 2x on the paper leg it read
  +$124k, PF 1.41 -> 1.49, drawdown unchanged. That scan is not a backtest. This is.

WHAT IT DOES
  The NOISE paper leg, core frozen exactly as deployed, EVERY trade taken. A trade decided
  while the higher-timeframe squeeze was compressed is taken at TWICE the size. Nothing about
  NOISE itself moves; the three gate knobs vary over the SAME fenced 27-cell set as #321, so
  the two validates read like for like, and the tilt factor is FIXED at 2.0 - it is not a
  knob, because a searchable tilt is a leverage search and would be found at its maximum.

HOW THE SECOND CONTRACT IS COSTED
  Strategies return gross trades in points; the engine subtracts the job's cost_pts from
  each trade ONCE afterwards. A tilted trade is therefore emitted as
      2 x gross  -  cost_pts
  so that after the engine's own subtraction it stands at 2 x gross - 2 x cost: two
  contracts, each paying its round trip. cost_pts is read from the call when the engine
  supplies it and otherwise taken as the house figure below, which the queue script pins
  the job to. A tilt that skipped the second contract's cost would flatter itself by
  $10.66 a trade on a fifth of the trades.

PRE-REGISTERED DECISION RULE (written before the run, judge in this order)
  1. House gates: PASS, walk-forward at least 6 of 8, lockbox positive. Anything less and
     the tilt is not adopted, whatever the money says.
  2. Full-window drawdown no worse than 1.10 x the ungated paper leg's ($18,425 local read;
     the run doc's own ungated figure is the reference). The tilt's claim is "richer at the
     same risk" - a bigger drawdown means it is just leverage.
  3. Full-window PF at least 1.45 (ungated 1.41) and net above the ungated $395,169.
  4. Lockbox PF at least the ungated lockbox PF (1.36).
  Meets all four: adopt as the NOISE paper leg's size rule (2 contracts when coiled, 1 when
  not). Meets 1 but fails 2: leverage, not edge - record and stop. Fails 1: the compression
  read does not survive as a tilt; record, and the filter result in #321 stands alone.

CAUSALITY AND CONSTRUCTION
  Identical to the gate file: the higher-timeframe state is read at the DECISION bar, only
  from COMPLETE higher-timeframe bars; trades never overlap and no NOISE filter reads the
  trade history, so scaling one trade cannot change any other (checked in the gate file,
  not assumed). Out-of-set gate configurations are REFUSED, never clamped.
"""
import importlib.util as _ilu
import os as _os
import inspect as _inspect

import numpy as _np
import pandas as _pd

_HERE = _os.path.dirname(_os.path.abspath(__file__))


def _load(fn, alias):
    sp = _ilu.spec_from_file_location(alias, _os.path.join(_HERE, fn))
    m = _ilu.module_from_spec(sp)
    sp.loader.exec_module(m)
    return m


_base = _load("NOISE_1_1_SBS_V90.py", "_noise_sbs_v90_tilt_base")
_ttm = _load("TTMSQZ_1_0.py", "_ttm_for_noise_tilt")

STRATEGY_NAME = 'NOISE 1.1 SBS+V90 + hourly-compression 2x size tilt'
DESCRIPTION = ("The NOISE paper leg, core frozen as deployed, every trade taken, and a trade "
               "decided while the higher-timeframe squeeze was compressed taken at TWICE the "
               "size. Three gate knobs vary over the same fenced set as run #321; the tilt is "
               "fixed at 2.0; NOISE itself does not move.")

# The tilt is FIXED, not searched. A searchable size multiplier is a leverage search.
TILT = 2.0
# House round-trip cost in points for the NQ 5m leg (commission + slippage). Used to charge
# the second contract when the engine does not hand cost_pts to the strategy. The queue
# script pins the job to this same figure so the two can never disagree.
_HOUSE_COST_PTS = 0.533

_AUGUR_MARKET = {"instrument": "NQ", "timeframe": "5m"}
_AUGUR_PARENT = "NOISE_1_1_SBS_V90.py"

# NOISE core, frozen at the deployed paper-leg configuration. Nothing here is searched.
_FROZEN = {k: v["default"] for k, v in _base.DEFAULT_PARAMS.items()}

DEFAULT_PARAMS = {
    "gate_tf_min": {
        "default": 60, "min": 30, "max": 120, "step": 30, "type": "int",
        "label": "Verification timeframe, minutes",
        "tooltip": "The higher timeframe whose compression must verify each entry. 60 is the "
                   "hourly frame the round-6 scan measured.",
    },
    "gate_len": {
        "default": 20, "min": 16, "max": 24, "step": 4, "type": "int",
        "label": "Verification squeeze length",
        "tooltip": "Length of the squeeze computed on the verification timeframe.",
    },
    "gate_ratio": {
        "default": 1.0, "min": 0.85, "max": 1.15, "step": 0.15, "type": "float",
        "label": "Compression threshold on the verification timeframe",
        "tooltip": "Bollinger width over Keltner width. 1.0 is Carter's published squeeze "
                   "exactly - band inside channel. Below demands a tighter coil, above admits "
                   "nearly-coiled bars.",
    },
}

# The pre-registered set, enforced below. 3 x 3 x 3 = 27 configurations, no more.
_ADMISSIBLE = {"gate_tf_min": [30, 60, 120], "gate_len": [16, 20, 24],
               "gate_ratio": [0.85, 1.0, 1.15]}

PARAM_GRID_PRESETS = {"Short  (the fenced 27-cell tilt neighbourhood, tilt fixed 2.0)": dict(_ADMISSIBLE)}


def _in_neighbourhood(kw):
    for k, allowed in _ADMISSIBLE.items():
        if k not in kw:
            continue
        if not any(abs(float(kw[k]) - float(a)) < 1e-9 for a in allowed):
            return False
    return True


def _compression(highs, lows, closes, day_id, index, gate_tf_min, gate_len, gate_ratio):
    """Per-bar: was the verification-timeframe squeeze compressed as of the last COMPLETE
    higher-timeframe bar? Compression is the Bollinger width over the Keltner width, so a
    threshold of exactly 1.0 reproduces Carter's published squeeze."""
    n = len(closes)
    if index is not None and len(index) == n:
        idx = _pd.DatetimeIndex(index)
        df = _pd.DataFrame({"h": highs, "l": lows, "c": closes, "d": _np.asarray(day_id)})
        first = _pd.Series(idx).groupby(df["d"].values).transform("first")
        off = ((_pd.Series(idx) - first).dt.total_seconds() // 60).astype("int64").values
        bucket = off // int(gate_tf_min)
    else:
        # No clock (the grid code path never passes one). This market is 5-minute bars, so a
        # verification bar is a fixed count of them; ordinal within the session, not the clock.
        per = max(int(gate_tf_min) // 5, 1)
        d = _np.asarray(day_id)
        ordinal = _np.zeros(n, int)
        a = 0
        while a < n:
            b = a
            while b < n and d[b] == d[a]:
                b += 1
            ordinal[a:b] = _np.arange(b - a)
            a = b
        bucket = ordinal // per
    key = _np.asarray(day_id).astype(_np.int64) * 100000 + _np.asarray(bucket, dtype=_np.int64)
    change = _np.empty(n, bool)
    change[0] = True
    change[1:] = key[1:] != key[:-1]
    gs = _np.flatnonzero(change)
    ge = _np.append(gs[1:], n) - 1                 # last base bar of each verification bar
    hh = _np.array([_np.max(highs[a:b + 1]) for a, b in zip(gs, ge)])
    ll = _np.array([_np.min(lows[a:b + 1]) for a, b in zip(gs, ge)])
    cc = _np.asarray(closes)[ge]

    L = int(gate_len)
    s = _pd.Series(cc)
    dev = s.rolling(L).std(ddof=0)
    prev = _np.concatenate([[_np.nan], cc[:-1]])
    tr = _np.maximum.reduce([hh - ll, _np.abs(hh - prev), _np.abs(ll - prev)])
    atr = _pd.Series(tr).rolling(L).mean()
    with _np.errstate(invalid="ignore", divide="ignore"):
        ratio = ((2.0 * dev) / (1.5 * atr)).to_numpy()   # Carter's published 2.0 / 1.5

    warm = L * 2 + 5
    j = _np.searchsorted(ge, _np.arange(n), side="left")
    # a verification bar is usable only once COMPLETE, i.e. from its last base bar onward
    j = _np.where(ge[_np.clip(j, 0, len(ge) - 1)] <= _np.arange(n), j, j - 1)
    ok = j >= warm
    jj = _np.clip(j, 0, len(ratio) - 1)
    out = _np.zeros(n, bool)
    with _np.errstate(invalid="ignore"):
        out[ok] = ratio[jj][ok] <= float(gate_ratio)
    return out


def run_backtest(opens, highs, lows, closes, volumes=None, day_id=None, index=None,
                 gate_tf_min=60, gate_len=20, gate_ratio=1.0,
                 return_trades=False, **kw):
    if not _in_neighbourhood(dict(gate_tf_min=gate_tf_min, gate_len=gate_len,
                                  gate_ratio=gate_ratio)):
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

    comp = _compression(_np.asarray(highs, float), _np.asarray(lows, float),
                        _np.asarray(closes, float), day_id, index,
                        gate_tf_min, gate_len, gate_ratio)
    n = len(closes)
    cost = kw.get("cost_pts")
    cost = float(cost) if isinstance(cost, (int, float)) else _HOUSE_COST_PTS
    kept = []
    n_tilt = 0
    for t in r["trades"]:
        dec = int(t[0]) - 1                       # the decision bar is the one before the fill
        nt = list(t)
        if 0 <= dec < n and comp[dec]:
            # second contract: same gross, pays its own round trip (see the docstring)
            nt[2] = float(t[2]) * TILT - cost * (TILT - 1.0)
            n_tilt += 1
        kept.append(tuple(nt))
    if not kept:
        return None

    pnls = _np.array([float(t[2]) for t in kept], float)
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
        "n_tilted": int(n_tilt),
    }
    if return_trades:
        out["trades"] = kept
    return out
