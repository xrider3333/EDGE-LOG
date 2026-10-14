"""
NOISE 1.8 CT304H TP -- NOISE #422 (NOISE_1_8_CT304H.py) with ONE more open knob: a PROFIT TARGET (NOISE lane, 2026-10-14).

Owner order 10-14 via MANAGER #91: "autovalidate on EL the top 3 results from the last few weeks". NOISE's cell: run #422
with a profit-target knob opened (off / 1R / 1.5R / 2R / 3R) on top of its normal ranges. NOISE TARGET r1 (ledger 2.151)
ran +1R on #422's walk-forward: ROC@30k 83.2 -> 96.9, but one episode carried it (Sortino fell, month-block bootstrap
P(gain) 0.27, the 2R neighbour 83.0). This file is that knob with #422's full search surface around it.
Pre-registration: docs/PREREG_noise_422_tp_validate_2026-10-14.md.

  OPEN    gate_len 16 / 20 / 24, gate_ratio 0.85 / 1.0 / 1.15, tilt_mult 1.25 / 1.5 / 1.75 (#422's own 27 cells, unchanged)
          tp off / 1.0 / 1.5 / 2.0 / 3.0 (x R, R = fill to the initial stop)  ->  27 x 5 = 135 cells
  PINNED  run #304's core, written out literally (CT304H's _FROZEN), the 60-minute verification frame, cost 0.533
  BASE    NOISE_1_10_TP.py = NOISE_1_0.py unchanged plus tp_r (a resting limit, checked after the stop, never on the fill
          bar, gap-through filled at the open). tp = off reproduces NOISE_1_8_CT304H trade for trade (parity-gated).
  DEFAULT run #422's crown (20 / 1.15 / 1.75) with tp off, so a call with no params IS run #422 - not CT304H's file
          defaults (1.0 / 1.5), which were never the run.

The parent file's docstring follows.

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


_base = _load("NOISE_1_10_TP.py", "_noise_tp_ct304h_base")   # NOISE_1_0 + tp_r (NBHD's _CHAMP keys are all in _FROZEN)
_sq = _load("NOISE_1_1_SBS_V90_SQ.py", "_noise_sq_for_ct304")   # run #321 gate, by import

STRATEGY_NAME = "NOISE 1.8 CT304H TP - #422 with a profit-target knob"
DESCRIPTION = ("The LIVE NOISE crown (run #304), core frozen, every trade kept; trades decided "
               "while the higher-timeframe squeeze was compressed are sized tilt_mult contracts "
               "and the rest one. Run #333 validated tilt, re-based off the retired #243 core.")

_AUGUR_MARKET = {"instrument": "NQ", "timeframe": "5m"}
_AUGUR_PARENT = "NOISE_1_8_CT304H.py"

# Re-exported so api/cloud_signal.py's required_lookback_sessions can read this straight
# off "NOISE_1_8_CT304H.py" -- the file name SHADOW_LEGS names for the three NOISE #422
# shadow legs (owner 2026-09-28) -- without needing to know it delegates through
# NOISE_1_1_NBHD.py down to NOISE_1_0.py's vol_skip_pct filter, where the number (252,
# VOL_SKIP_REF_SESSIONS) actually comes from. Same hook, same wording, as NOISE_1_8_CT304.py's (go-live audit
# item 3.8). _FROZEN below pins vol_skip_pct=95.0 on always, so this leg's requirement
# is never "off" the way a vol_skip_pct=0.0 config's would be.
REQUIRED_LOOKBACK_SESSIONS = getattr(_base, "REQUIRED_LOOKBACK_SESSIONS", None)

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
        "default": 1.15, "min": 0.85, "max": 1.15, "step": 0.15, "type": "float",
        "label": "Compression threshold on the verification timeframe",
        "tooltip": "Bollinger width over Keltner width. 1.15 = the crowned setting of run 333; "
                   "1.0 = the Carter squeeze exactly.",
    },
    "tilt_mult": {
        "default": 1.75, "min": 1.25, "max": 1.75, "step": 0.25, "type": "float",
        "label": "Size on compressed-hour trades (others are 1.0)",
        "tooltip": "1.5 = the deployed size and the crowned one; 2.0 = the setting of run 331; "
                   "1.0 = the tilt switched off, which is the live crown and the parity control.",
    },
    "tp": {
        "default": "off", "type": "str", "options": ["off", "1.0", "1.5", "2.0", "3.0"],
        "label": "Profit target (x R, R = fill to the initial stop) - OPEN off/1/1.5/2/3",
        "tooltip": "A resting limit at entry + tp x R, checked after the stop and never on the fill bar. "
                   "off = run #422 exactly.",
    },
}

# 3 x 3 x 3 = 27 configurations, hourly frame only, x 5 profit targets = 135. Enforced below; nothing outside runs.
_ADMISSIBLE = {"gate_len": [16, 20, 24], "gate_ratio": [0.85, 1.0, 1.15],
               "tilt_mult": [1.25, 1.5, 1.75]}
_GATE_TF_MIN = 60                     # the verification frame is frozen at an hour
_TP_OPTIONS = {"off": 0.0, "1.0": 1.0, "1.5": 1.5, "2.0": 2.0, "3.0": 3.0}

PARAM_GRID_PRESETS = {"Short  (the fenced 27-cell hourly tilt neighbourhood x 5 targets)":
                      dict(_ADMISSIBLE, tp=list(_TP_OPTIONS))}


def _in_neighbourhood(kw):
    for k, allowed in _ADMISSIBLE.items():
        if k not in kw:
            continue
        if not any(abs(float(kw[k]) - float(a)) < 1e-9 for a in allowed):
            return False
    return True


def run_backtest(opens, highs, lows, closes, volumes=None, day_id=None, index=None,
                 gate_len=20, gate_ratio=1.15, tilt_mult=1.75, tp="off",
                 return_trades=False, **kw):
    gate_tf_min = _GATE_TF_MIN
    if not _in_neighbourhood(dict(gate_len=gate_len,
                                  gate_ratio=gate_ratio, tilt_mult=tilt_mult)):
        return None          # outside the pre-registered set - refused, never clamped
    if str(tp) not in _TP_OPTIONS:
        return None          # outside the pre-registered targets - refused, never clamped
    if day_id is None:
        return None

    call = dict(_FROZEN)
    sp = _inspect.signature(_base.run_backtest).parameters
    hk = any(p.kind == p.VAR_KEYWORD for p in sp.values())
    call = {k: v for k, v in call.items() if k in sp or hk}
    call["tp_r"] = _TP_OPTIONS[str(tp)]
    if volumes is not None and ("volumes" in sp or hk):
        call["volumes"] = volumes
    if "day_id" in sp or hk:
        call["day_id"] = day_id
    if index is not None and ("index" in sp or hk):
        call["index"] = index
    # vol_prior_ranges (go-live audit item 3.8, same as NOISE_1_8_CT304.py): opt-in runtime
    # kwarg, not a DEFAULT_PARAMS knob -- see NOISE_1_0.py's run_backtest/_vol_percentile.
    # Forwarded through unchanged so a live caller (api/cloud_signal.py) reaches NOISE_1_0.py's
    # vol_skip_pct filter through this wrapper the same way it would through NBHD alone;
    # absent from kw (the normal backtest path), this is a no-op.
    if "vol_prior_ranges" in kw and ("vol_prior_ranges" in sp or hk):
        call["vol_prior_ranges"] = kw["vol_prior_ranges"]
    # return_decisions (2026-10-05, NOISE lane audit): opt-in runtime kwarg, forwarded the
    # same way -- NOISE_1_0.py's DECISION RECORD (the bar, VWAP and band each trade was
    # decided on). Read-only: it changes no trade, size or metric below; absent or False
    # (every backtest) it is never forwarded at all.
    want_decisions = bool(kw.get("return_decisions")) and return_trades \
        and ("return_decisions" in sp or hk)
    if want_decisions:
        call["return_decisions"] = True
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
        # DECISION RECORD, passed through untouched: one per trade, the same order as
        # out_trades (the loop above keeps r["trades"]' order); dropped if it does not line up.
        dec = r.get("decisions") if want_decisions else None
        if isinstance(dec, list) and len(dec) == len(out_trades):
            out["decisions"] = dec
    return out
