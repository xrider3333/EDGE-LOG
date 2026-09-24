"""
NOISE 1.8 CT304H -- the compression SIZE TILT on the live crown, at an hourly frame and a sane size.

ROUND 60 (2026-09-24, NOISE.md). Runs #382, #409 and #410 all searched this tilt with the 30-minute frame
and 2.0x in the set, and all three crowned 30-minute / length 16 / threshold 1.15 at 2.0x -- which round 55
then measured continuously and REJECTED: drawdown +43% against the crown, one trade 61% of the gain, and it
loses to flat leverage in the sealed year. The cell round 55 actually recommended -- the textbook HOURLY
squeeze at 1.5x -- has never been an Auto-Validate champion, because a dollar-ranked search always prefers
the 30-minute gate, which fires on about 34% of trades against the hourly 13%.

This file removes that fork. The verification frame is FROZEN at 60 minutes and the tilt sizes are fenced
to 1.25 / 1.5 / 1.75: 2.0x is out of the set because it was measured and rejected, and 1.0x is out because
it is the crown itself. Open: squeeze length 16/20/24, threshold 0.85/1.0/1.15, tilt 1.25/1.5/1.75 -- 27
cells. The core is run #304's champion, written out literally.

THE COST CONVENTION: the engine subtracts cost_pts ONCE per trade whatever its size, so a size-s trade is
handed back as s*pnl - (s-1)*cost. The house NQ cost 0.533 is baked in; any other cost_pts is refused.
PRE-REGISTERED BAR (written before the job was queued): PASS, or WEAK where the overfit check is the only
failing gate; AND the sealed year earns at least the live crown's dollars at a sealed-year drawdown no more
than 25% above the crown's; AND annualised MAR at least the crown's. A tilt that scales money and drawdown
together is leverage and fails this bar. READ THE LOCKBOX CONTINUOUSLY - the saved strip is a cold restart.
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
    "gate_len": {
        "default": 20, "min": 16, "max": 24, "step": 4, "type": "int",
        "label": "Verification squeeze length",
        "tooltip": "16 = the crowned setting of run 333; 20 = published.",
    },
    "gate_ratio": {
        "default": 1.0, "min": 0.85, "max": 1.15, "step": 0.15, "type": "float",
        "label": "Compression threshold on the verification timeframe",
        "tooltip": "Bollinger width over Keltner width. 1.15 = the crowned setting of run 333; "
                   "1.0 = the Carter squeeze exactly.",
    },
    "tilt_mult": {
        "default": 1.5, "min": 1.25, "max": 1.75, "step": 0.25, "type": "float",
        "label": "Size on compressed-hour trades (others are 1.0)",
        "tooltip": "1.5 = the deployed size and the crowned one; 2.0 = the setting of run 331; "
                   "1.0 = the tilt switched off, which is the live crown and the parity control.",
    },
}

# 3 x 3 x 3 = 27 configurations, hourly frame only. Enforced below; nothing outside runs.
_ADMISSIBLE = {"gate_len": [16, 20, 24], "gate_ratio": [0.85, 1.0, 1.15],
               "tilt_mult": [1.25, 1.5, 1.75]}
_GATE_TF_MIN = 60                     # the verification frame is frozen at an hour

PARAM_GRID_PRESETS = {"Short  (the fenced 27-cell hourly tilt neighbourhood)": dict(_ADMISSIBLE)}


def _in_neighbourhood(kw):
    for k, allowed in _ADMISSIBLE.items():
        if k not in kw:
            continue
        if not any(abs(float(kw[k]) - float(a)) < 1e-9 for a in allowed):
            return False
    return True


def run_backtest(opens, highs, lows, closes, volumes=None, day_id=None, index=None,
                 gate_len=20, gate_ratio=1.0, tilt_mult=1.5,
                 return_trades=False, **kw):
    gate_tf_min = _GATE_TF_MIN
    if not _in_neighbourhood(dict(gate_len=gate_len,
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
    sizes = []
    for t in r["trades"]:
        dec = int(t[0]) - 1                       # the decision bar is the one before the fill
        on = 0 <= dec < n and bool(comp[dec])
        s = s_on if on else 1.0
        raw = float(t[2])
        pts = s * raw - (s - 1.0) * _COST_PTS     # engine then subtracts cost once -> s*(raw-cost)
        pnls.append(pts)
        sizes.append(s)
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
        # ADDITIVE SIZE CONTRACT (2026-09-23): trade_sizes is the per-trade multiplier
        # `s` the loop above already computed and folded into pts as
        # pts = s*raw - (s-1)*_COST_PTS, same length/order as out_trades; size_cost_pts
        # is the cost constant it folded in. Both keys are new and purely additive --
        # nothing in this file reads them back, and every metric above (total_pnl,
        # num_trades, win_rate, profit_factor, max_drawdown, avg_pnl, wins, losses) is
        # computed exactly as before from `pnls`, which is unchanged by this addition.
        # A caller that knows this contract (api/cloud_signal.py's run_leg_trades) can
        # invert the fold to recover the real per-trade price; one that does not is
        # unaffected -- see augur_engine/engine.py's _apply_costs, which already
        # preserves unknown extra keys via `out = dict(m)`.
        out["trade_sizes"] = sizes
        out["size_cost_pts"] = _COST_PTS
    return out
