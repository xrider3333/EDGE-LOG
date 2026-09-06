"""
NOISE 1.1 SBS+V90 + HOURLY-COMPRESSION GATE — a fenced neighbourhood validate.

WHERE THIS CAME FROM
  Five rounds of TTM Squeeze work closed that family as a standalone (crown run #299 is real
  but earns about 2,900 dollars a year, the lowest ceiling of any family here). Round 6
  (tools/ttmsqz_round6_parts.py, studies rows 1262-1282) found that the one durable thing the
  family discovered is not its entry at all - it is the CHECK: only trade while the hourly
  chart is still coiled. Split a crowned strategy's OWN trades by that state and the coiled
  ones earn two to three times the expectancy per unit of risk, on three different families,
  and the direction repeats in the untouched lockbox year. On this leg - the one running in
  the paper forward test - the separation is the only one that clears a permutation test
  outright (p = 0.0022, which survives correcting for having looked at three families).

  That scan is not a backtest. This file is the real test of it.

WHAT IT DOES
  The NOISE paper leg, core frozen exactly as deployed, taking ONLY the trades decided while
  the higher-timeframe squeeze was compressed. Three gate knobs vary over a small
  pre-registered set; nothing about NOISE itself moves.

WHY DROPPING TRADES IS LEGITIMATE HERE, AND WHEN IT WOULD NOT BE
  This wraps the parent and removes the trades the gate rejects, rather than reaching into
  NOISE's entry loop. That is only equivalent to gating the entries if removing one trade
  cannot change any other, and that was CHECKED before this file was written, not assumed:
    * the trades never overlap - the next entry never starts before the previous exit
      (measured: 0 of 4,416), so no removal frees or blocks a later signal; and
    * every NOISE filter reads the PRIOR SESSION (weak close, wild day), never the trade
      history, so no removal changes a later decision.
  If either were false this construction would be wrong and the gate would have to go inside
  the entry loop instead.

CAUSALITY
  A higher-timeframe bar is usable on bar u only once COMPLETE - its last member bar ends at
  or before u's end - and the state is read at the DECISION bar, the one before the fill.
  Same construction the audited TTM round-4 harness uses. When bar timestamps are supplied
  the wall clock builds the frame; when they are not (the grid code path does not pass them)
  the frame falls back to a fixed number of 5-minute bars, which is what this market is.

FENCED
  Auto-Validate widens a strategy's declared min/max when the optimum sits near an edge, so a
  pre-registered neighbourhood is NOT binding unless the strategy enforces it. TTM runs 290
  and 293 were lost that way - the search left the declared set and crowned configurations
  the study never proposed, costing 57 to 63 thousand dollars of lockbox. An out-of-set
  configuration here is REFUSED, not clamped: clamping would run one thing and report another.

LOCAL PRE-READ (tools/ttmsqz_round6_parts.py, NQ 5m RTH, 2010-06-07..2026-06-30, house costs)
  ungated paper leg : n=4,416  $395,169  PF 1.41  DD $18,425  EV R 0.259  | LB $60,001 PF 1.36
  gated (this file) : n=586    $124,444  PF 2.23  DD $12,565  EV R 0.709  | LB $21,474 PF 1.87
  The gate keeps 13.3% of the trades and roughly triples the expectancy per unit of risk.
  It also cuts R / YR from 72 to 26, which is the honest cost and the reason the round-6
  writeup recommends a SIZE TILT over a filter for live use. This validate asks the narrower
  question the house gates can actually answer: is the gated edge real?
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


_base = _load("NOISE_1_1_SBS_V90.py", "_noise_sbs_v90_gated_base")
_ttm = _load("TTMSQZ_1_0.py", "_ttm_for_noise_gate")

STRATEGY_NAME = 'NOISE 1.1 SBS+V90 + hourly-compression gate'
DESCRIPTION = ("The NOISE paper leg, core frozen as deployed, taking only the trades decided "
               "while the higher-timeframe squeeze was still compressed. Three gate knobs vary "
               "over a fenced pre-registered set; NOISE itself does not move.")

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

PARAM_GRID_PRESETS = {"Short  (the fenced 27-cell gate neighbourhood)": dict(_ADMISSIBLE)}


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
    kept = []
    for t in r["trades"]:
        dec = int(t[0]) - 1                       # the decision bar is the one before the fill
        if 0 <= dec < n and comp[dec]:
            kept.append(t)
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
    }
    if return_trades:
        out["trades"] = kept
    return out
