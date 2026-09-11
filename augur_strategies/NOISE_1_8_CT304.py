"""
NOISE 1.8 -- THE VALIDATED COMPRESSION SIZE TILT, RE-BASED ONTO THE LIVE CROWN.

WHY THIS FILE EXISTS
  Run #333 validated the hourly-compression size tilt on NOISE and it is the only size tilt in
  the family that survived the shift null (0.0-0.5%; the same tilt FAILS on ORB and on ENGU-Q).
  It PASSED all six house checks, PBO 0.222, and its sealed year read 214 trades at profit
  factor 1.600 against the crown's 1.340 on the least concentrated top-ten share in the family.

  But run #333 -- and both deployed paper legs, NOISE_SBS_V90_C15 and NOISE_SBS_V90_C15G --
  freeze their core to NOISE_1_1_SBS_V90.py's defaults, which are lookback 44 and volatility
  skip 90. That is run #243: the crown the family RETIRED on 2026-09-05 when run #304 moved
  those two knobs to 40 and 95. Nobody re-based the tilt, so the best validated improvement to
  NOISE is being forward-tested on top of a base that is no longer traded, while the base that
  IS traded forward-tests without it. This is the same staleness the KEEL overlay had (found
  2026-09-10, round 53) and it was found the same way: by reading which base a leg actually
  pins rather than which base its name suggests.

WHAT CHANGES FROM #333
  The core, and nothing else. The champion dictionary of run #304 is written out literally
  below rather than read from any file's defaults -- NOISE_1_1_NBHD.py's defaults are still
  44/90 and only its RANGES span the crown, so reading defaults would silently rebuild #243
  a second time. The compression state is imported from run #321's file, the same function
  #333 read, so a PASS there and a read here are of the same signal.

THE COST CONVENTION -- READ THIS BEFORE TRUSTING ANY NUMBER
  The engine subtracts cost_pts ONCE per trade whatever its size, so a size-s trade must be
  handed back as s*pnl - (s-1)*cost for the engine's own subtraction to land on s*(pnl-cost).
  The house NQ cost is baked in below and the queue check refuses any other cost_pts.

FENCED
  Auto-Validate widens a declared range when the optimum sits near its edge, so a declared
  neighbourhood is not binding unless the file enforces it. An out-of-set configuration here
  is REFUSED, never clamped.

PRE-REGISTERED BAR (written before the job was queued, judged on the run doc, never re-cut)
  Verdict PASS, or WEAK where the overfit check is the only failing gate; AND the sealed year
  earns at least the live crown's $84,580 at a sealed-year drawdown no more than 25% above the
  crown's; AND annualised MAR at least the crown's. A tilt that scales money and drawdown
  together is leverage and fails this bar. Because run #331 and run #333 both showed a realised
  drawdown shallower than 94-98% of their own resampled paths, the drawdown clause is judged
  against the resampled 95th percentile as well as against the realised one.
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


_base = _load("NOISE_1_1_NBHD.py", "_noise_nbhd_ct304_base")
_sq = _load("NOISE_1_1_SBS_V90_SQ.py", "_noise_sq_for_ct304")   # run #321 gate, by import

STRATEGY_NAME = "NOISE 1.8 live crown x hourly-compression size tilt"
DESCRIPTION = ("The LIVE NOISE crown (run #304), core frozen, every trade kept; trades decided "
               "while the higher-timeframe squeeze was compressed are sized tilt_mult contracts "
               "and the rest one. Run #333 validated tilt, re-based off the retired #243 core.")

_AUGUR_MARKET = {"instrument": "NQ", "timeframe": "5m"}
_AUGUR_PARENT = "NOISE_1_1_NBHD.py"

_COST_PTS = 0.533

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
        "default": 30, "min": 30, "max": 60, "step": 30, "type": "int",
        "label": "Verification timeframe, minutes",
        "tooltip": "30 = the crowned setting of run 333; 60 = the hourly frame the deployed "
                   "paper leg reads.",
    },
    "gate_len": {
        "default": 16, "min": 16, "max": 20, "step": 4, "type": "int",
        "label": "Verification squeeze length",
        "tooltip": "16 = the crowned setting of run 333; 20 = published.",
    },
    "gate_ratio": {
        "default": 1.15, "min": 1.0, "max": 1.15, "step": 0.15, "type": "float",
        "label": "Compression threshold on the verification timeframe",
        "tooltip": "Bollinger width over Keltner width. 1.15 = the crowned setting of run 333; "
                   "1.0 = the Carter squeeze exactly.",
    },
    "tilt_mult": {
        "default": 1.5, "min": 1.0, "max": 2.0, "step": 0.5, "type": "float",
        "label": "Size on compressed-hour trades (others are 1.0)",
        "tooltip": "1.5 = the deployed size and the crowned one; 2.0 = the setting of run 331; "
                   "1.0 = the tilt switched off, which is the live crown and the parity control.",
    },
}

# 2 x 2 x 2 x 3 = 24 configurations. Enforced below; nothing outside runs.
_ADMISSIBLE = {"gate_tf_min": [30, 60], "gate_len": [16, 20],
               "gate_ratio": [1.0, 1.15], "tilt_mult": [1.0, 1.5, 2.0]}

PARAM_GRID_PRESETS = {"Short  (the fenced 24-cell tilt neighbourhood)": dict(_ADMISSIBLE)}


def _in_neighbourhood(kw):
    for k, allowed in _ADMISSIBLE.items():
        if k not in kw:
            continue
        if not any(abs(float(kw[k]) - float(a)) < 1e-9 for a in allowed):
            return False
    return True


def run_backtest(opens, highs, lows, closes, volumes=None, day_id=None, index=None,
                 gate_tf_min=30, gate_len=16, gate_ratio=1.15, tilt_mult=1.5,
                 return_trades=False, **kw):
    if not _in_neighbourhood(dict(gate_tf_min=gate_tf_min, gate_len=gate_len,
                                  gate_ratio=gate_ratio, tilt_mult=tilt_mult)):
        return None          # outside the pre-registered set - refused, never clamped
    if day_id is None:
        return None

    call = dict(_FROZEN)
    sp = _inspect.signature(_base.run_backtest).parameters
    hk = any(p.kind == p.VAR_KEYWORD for p in sp.values())
    call = {k: v for k, v in call.items() if k in sp or hk}
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
