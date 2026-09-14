"""
NOISE 1.9 -- RUN #321's SQUEEZE FILTER, RE-BASED ONTO THE LIVE CROWN (#304).

WHY THIS FILE EXISTS (round 56, 2026-09-13, NOISE.md)
  Run #321 validated the higher-timeframe squeeze as a FILTER -- keep a NOISE trade only when the
  verification timeframe was compressed at the trade's decision bar -- and PASSED 6 of 6 with the
  lowest overfit score in the family (PBO 0.099). It froze its core to NOISE_1_1_SBS_V90.py's
  defaults, which are run #243's settings: the crown the family retired on 2026-09-05. Nobody has
  validated the filter on the base that actually trades.

  Round 56 replayed every NOISE configuration on one continuous tape (2010-06-07 to 2026-07-16,
  house cost) and the filter family tops it on every quality number:
      live crown raw                     4,824 trades  PF 1.357  2024+ PF 1.357  sealed-year PF 1.274
      live crown + #321's 30-min pick    1,661 trades  PF 1.496  2024+ PF 1.391  sealed-year PF 1.277
      live crown + textbook hourly gate    615 trades  PF 2.351  2024+ PF 2.184  sealed-year PF 1.985
  Across #321's own 27-cell grid on the live crown, 25 cells beat the raw crown's profit factor and
  all nine hourly cells sit between 1.68 and 2.35. The textbook cell (60-minute frame, length 20,
  ratio 1.0) is the TOP of that plateau, so its own number is inflated by being the best of 27; the
  neighbourhood's level is the honest expectation.

WHAT CHANGES FROM #321
  The core, and nothing else. Run #304's champion is written out literally below -- the crown file
  NOISE_1_1_NBHD.py still DEFAULTS to #243's lookback 44 / volatility skip 90, and reading defaults
  would rebuild the retired base a second time. The compression function is imported from #321's
  file, so this reads the same signal #321 validated. The admissible set is #321's pre-registered
  27-cell grid, unchanged -- NOT re-fenced around the cell round 56 noticed, so the search is free to
  pick exactly as #321's did.

READ THE LOCKBOX CONTINUOUSLY
  The validate grades its lockbox by reloading the tape from the lockbox's first day with no
  history. NOISE needs forty prior sessions and the squeeze needs up to 53 verification bars, so the
  reload drops a large share of the sealed year (run #382: 239 trades reloaded vs 314 continuous).
  Judge the sealed year on a continuous replay sliced by entry time, never on the saved strip.

PRE-REGISTERED BAR (written before the job was queued, never re-cut)
  Verdict PASS, or WEAK where the overfit check is the only failing gate; AND, on the continuous
  replay of the validate's own lockbox window, the chosen cell's profit factor beats the raw crown's
  AND its net per resampled 95th-percentile drawdown is at least the raw crown's.

FENCED
  An out-of-set configuration is REFUSED, never clamped.
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


_base = _load("NOISE_1_1_NBHD.py", "_noise_nbhd_sq304_base")
_sq = _load("NOISE_1_1_SBS_V90_SQ.py", "_noise_sq_for_sq304")   # run #321 gate, by import

STRATEGY_NAME = "NOISE 1.9 live crown x higher-timeframe squeeze filter"
DESCRIPTION = ("The LIVE NOISE crown (run #304), core frozen; a trade is kept only when the "
               "verification-timeframe squeeze was compressed at its decision bar. Run #321's "
               "validated filter and its 27-cell grid, re-based off the retired #243 core.")

_AUGUR_MARKET = {"instrument": "NQ", "timeframe": "5m"}
_AUGUR_PARENT = "NOISE_1_1_NBHD.py"

# Run #304 champion, written out literally. NOT read from any file defaults.
_FROZEN = {
    "lookback": 40, "band_mult_long": 0.75, "band_mult_short": 1.5, "exit_mode": "vwap",
    "side": "Both", "window": "all_day", "flat_eod": True, "skip_holidays": False,
    "stop_mode": "bandwidth", "stop_k": 1.75, "confirm_bars": 1,
    "daytype_mode": "skip_bot_short", "daytype_lo": 0.2, "daytype_hi": 0.8,
    "vol_skip_pct": 95.0,
}

DEFAULT_PARAMS = {
    "gate_tf_min": {
        "default": 60, "min": 30, "max": 120, "step": 30, "type": "int",
        "label": "Verification timeframe, minutes",
        "tooltip": "30 / 60 / 120 - run 321's pre-registered set. 60 is the textbook hourly frame.",
    },
    "gate_len": {
        "default": 20, "min": 16, "max": 24, "step": 4, "type": "int",
        "label": "Verification squeeze length",
        "tooltip": "16 / 20 / 24. 20 is the published length.",
    },
    "gate_ratio": {
        "default": 1.0, "min": 0.85, "max": 1.15, "step": 0.15, "type": "float",
        "label": "Compression threshold on the verification timeframe",
        "tooltip": "Bollinger width over Keltner width. 1.0 is Carter's published squeeze exactly; "
                   "below demands a tighter coil, above admits nearly-coiled bars.",
    },
}

# Run 321's pre-registered set, unchanged. 3 x 3 x 3 = 27 configurations.
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


def run_backtest(opens, highs, lows, closes, volumes=None, day_id=None, index=None,
                 gate_tf_min=60, gate_len=20, gate_ratio=1.0, return_trades=False, **kw):
    if not _in_neighbourhood(dict(gate_tf_min=gate_tf_min, gate_len=gate_len, gate_ratio=gate_ratio)):
        return None          # outside the pre-registered set - refused, never clamped
    if day_id is None:
        return None

    sp = _inspect.signature(_base.run_backtest).parameters
    hk = any(p.kind == p.VAR_KEYWORD for p in sp.values())
    call = {k: v for k, v in _FROZEN.items() if k in sp or hk}
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
    kept = [t for t in r["trades"] if 0 <= int(t[0]) - 1 < n and comp[int(t[0]) - 1]]
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
