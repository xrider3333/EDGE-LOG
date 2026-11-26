# AUGUR-SOURCE: claude-review
"""
NOISE 1.8 CT304H_FTC -- run #555 (NOISE_1_8_CT304H_FT.py) + RE-ENTRY CONFIRM + LATE PEAK-AGE EXIT. Board test 119 (2026-11-26).
Prereg: C:/EdgeLog/manager/prereg/PREREG_noise_v2_ftc_2026-11-26.md (locked before the validate is queued).

WHY (owner 11-26: low win rate, stalls, give-back, repeated small-loss re-entries; tiger team read on #555's stitched WF)
  - No in-trade state has negative continuation value: stall and give-back exits have nothing to act on.
  - ONE pre-entry state flags: a signal close on the wrong side of session VWAP (557 trades, 541 of them re-entries,
    84% one-bar round trips). That is the owner's "enters repeatedly, small losses" pattern.
  - Peak-age (stalled runner) at a late arm is harmless-to-slightly-positive on #555; never tested on this core, and
    never together with the re-entry rule.

KNOBS (each has OFF inside the range, so run #555 itself is in the search space)
  gate_len / gate_ratio / tilt_mult   #555's own fenced 27 cells, unchanged.
  reentry_confirm   0 = off; 1 = after the first entry of the session, a new entry needs the signal bar's close on the
                    trade's side of session VWAP (the churn r2 rule, same patched core as NOISE_1_8_CT304_CHURN.py).
  pa_mode           off / peak_age. peak_age = once the best open profit has reached 2.0 x the trade's own risk, exit
                    when pa_n closed 5m bars pass with no new best (NOISE_1_8_CT304_PA.py's rule, arm frozen at 2R).
  pa_n              14 / 18 bars (read only when pa_mode = peak_age).

NO LOOK-AHEAD
  reentry_confirm reads the signal bar's close and that bar's VWAP only. peak_age reads bar j's high/low at j's close
  and fills at the open of j+1; it only acts before the leg's own exit. Fixed tilts are read at the entry bar.

KNOWN LIMIT (same as tests 74 / 82 / #494): the peak-age overlay rewrites a trade's exit; it does not let NOISE
re-enter in the bars it frees. Cost: s-sized trade = s*raw - (s-1)*0.533, the engine subtracts cost once.
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


_ft = _load("NOISE_1_8_CT304H_FT.py", "_noise_ft_for_ftc")            # run #555
_churn = _load("NOISE_1_8_CT304_CHURN.py", "_noise_churn_for_ftc")    # patched NOISE_1_0 core (re-entry confirm)
_pa = _load("NOISE_1_8_CT304_PA.py", "_noise_pa_for_ftc")             # peak_age_exit()

STRATEGY_NAME = "NOISE 1.8 #555 + re-entry confirm + late peak-age exit"
DESCRIPTION = ("Run #555 (NOISE #422 x frozen v12 fixed tilts) with two optional rules: a re-entry must close on the "
               "trade's side of VWAP, and a runner that reached 2R exits after N bars with no new best. All off = #555.")
_AUGUR_MARKET = {"instrument": "NQ", "timeframe": "5m"}
_AUGUR_PARENT = "NOISE_1_8_CT304H_FT.py"
REQUIRED_LOOKBACK_SESSIONS = _ft.REQUIRED_LOOKBACK_SESSIONS
_COST_PTS = _ft._COST_PTS
_PA_ARM_R = 2.0                                                       # frozen, not a knob

DEFAULT_PARAMS = dict(_ft.DEFAULT_PARAMS)
DEFAULT_PARAMS.update({
    "reentry_confirm": {"default": 0, "min": 0, "max": 1, "step": 1, "type": "int",
                        "label": "Re-entry needs the signal close on the trade's side of VWAP (0 = off)",
                        "tooltip": "0 = run #555 exactly. 1 = entries after the first of the session need the signal "
                                   "bar to close on the trade's side of session VWAP."},
    "pa_mode": {"default": "off", "type": "str", "options": ["off", "peak_age"],
                "label": "Stalled-runner exit", "tooltip": "off = run #555 exactly; peak_age = after the trade reached "
                                                           "2R, exit when N bars pass with no new best."},
    "pa_n": {"default": 14, "min": 14, "max": 18, "step": 4, "type": "int",
             "label": "Peak age, bars", "tooltip": "Bars with no new best before the stalled-runner exit fires."},
})
_ADMISSIBLE = dict(_ft._ADMISSIBLE, reentry_confirm=[0, 1], pa_mode=["off", "peak_age"], pa_n=[14, 18])
PARAM_GRID_PRESETS = {"Short  (#555's 27 cells x confirm 0/1 x peak-age off/14/18)": dict(_ADMISSIBLE)}


class _Core:
    """NBHD filters kwargs by the core's signature, so the re-entry knob is bound here (as in CT304_CHURN)."""

    def __init__(self, n):
        self._kw = dict(max_entries=0, reentry_confirm=int(n), vwap_buf_k=0.0, entry_vwap=False, exit_closes=1)

    def __getattr__(self, k):
        return getattr(_churn._core, k)

    def run_backtest(self, *a, **k):
        return _churn._core.run_backtest(*a, **dict(k, **self._kw))


def run_backtest(opens, highs, lows, closes, volumes=None, day_id=None, index=None,
                 gate_len=20, gate_ratio=1.0, tilt_mult=1.5, reentry_confirm=0, pa_mode="off", pa_n=14,
                 return_trades=False, return_levels=False, **kw):
    rc = int(reentry_confirm)
    if rc not in (0, 1) or pa_mode not in ("off", "peak_age") or int(pa_n) not in (14, 18):
        return None                                                   # outside the pre-registered set: refused
    pa_on = pa_mode == "peak_age"
    g = _ft._p._base.run_backtest.__globals__                         # NBHD's module globals (its _base = NOISE_1_0)
    held = g["_base"]
    if rc:
        g["_base"] = _Core(rc)
    try:
        r = _ft.run_backtest(opens, highs, lows, closes, volumes=volumes, day_id=day_id, index=index,
                             gate_len=gate_len, gate_ratio=gate_ratio, tilt_mult=tilt_mult,
                             return_trades=True, return_levels=(return_levels or pa_on), **kw)
    finally:
        g["_base"] = held
    if not r or not r.get("trades"):
        return None
    if pa_on:
        lv = r.get("levels")
        if not isinstance(lv, list) or len(lv) != len(r["trades"]):
            return None                                               # no stop levels = no R; never guess
        O, H, L = (_np.asarray(v, float) for v in (opens, highs, lows))
        c, trades, pnls = _COST_PTS, [], []
        for t, s, l in zip(r["trades"], r["trade_sizes"], lv):
            e, x, sd, ep, s = int(t[0]), int(t[1]), int(t[3]), float(t[4]), float(s)
            raw = (float(t[2]) + (s - 1.0) * c) / s                   # undo the size fold
            nraw, nx = _pa.peak_age_exit(O, H, L, e, x, sd, ep, raw, float(l.get("risk") or 0.0), int(pa_n), _PA_ARM_R)
            tt = list(t)
            tt[1], tt[2] = nx, s * nraw - (s - 1.0) * c
            trades.append(tuple(tt))
            pnls.append(tt[2])
        p = _np.asarray(pnls, float)
        wn, lo = p[p > 0], p[p < 0]
        gw, gl = float(wn.sum()), float(-lo.sum())
        cum = _np.cumsum(p)
        r = dict(r, trades=trades, total_pnl=float(p.sum()), num_trades=int(len(p)),
                 win_rate=float(100.0 * len(wn) / len(p)),
                 profit_factor=(gw / gl) if gl > 1e-9 else (float("inf") if gw > 0 else 0.0),
                 max_drawdown=float((cum - _np.maximum.accumulate(cum)).min()), avg_pnl=float(p.mean()),
                 wins=int(len(wn)), losses=int(len(lo)))
    if not return_levels:
        r.pop("levels", None)
    if not return_trades:
        for k in ("trades", "trade_sizes", "size_cost_pts", "decisions", "levels"):
            r.pop(k, None)
    return r
