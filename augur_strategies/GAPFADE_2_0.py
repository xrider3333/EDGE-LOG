"""
GAPFADE 2.0 - opening-gap FADE on NQ when the overnight session has NOT already retraced it (E1b revival, 2026-11-03).

WHERE IT CAME FROM: docs/anatomy/LEG_SCAN_IDEAS.md mechanism M1(a), ledger 2.5 (tools/leg_scan_ideas.py, pre-registered
grid, 60/40 calendar split, lockbox 2025-07-01+ never loaded). Its best cell, "M1 FADE g=0.3 not_retraced", was PF 1.43 on
discovery (110 trades) and PF 1.46 on holdout (103 trades) - held out of sample but only 12-17 trades a year, so the leg scan
closed it as thin. The E3 power retro (MANAGER #162, tools/noise_e3_power_retro.py) classed it UNDERPOWERED rather than dead:
the only revivable entry of 289. MANAGER #165 GO: write it as a ranged file for a full Auto-Validate (E1b). Hand-written by
Claude (NOISE lane); not LLM-generated, so the plugin gate does not apply.

MECHANISM (every decision on finished data, live-legal):
  1. gap = today's 09:30 RTH open - yesterday's last RTH close, in units of ADR20 (mean RTH daily range of the PREVIOUS 20
     sessions). Trade only if |gap| >= gap_min.
  2. The first 5-minute bar must close back toward the prior close (it does NOT extend the gap: gap up and bar0 close <= open,
     or gap down and bar0 close > open - the leg scan's own test).
  3. Overnight filter (retrace_filter="not_retraced"): skip the day if the overnight session (NQ 5m ETH master, prior 18:00 ->
     09:25 bar) already traded back past HALF of the gap. "all" = no filter (the scan's control cell).
  4. Enter at the 09:35 bar's OPEN toward the gap fill. Target = the prior RTH close. Stop = entry -/+ stop_atr_mult x the
     14-bar ATR of the 5-minute chart AT THE BAR BEFORE ENTRY (the scan used the entry bar's own ATR, which includes that bar's
     range - a one-bar look; this file uses the previous bar, so a couple of trades can differ from the scan).
  5. Stop wins any same-bar race with the target; a bar that opens through the stop fills at that open. Flat at the close of the
     10:55 bar (the scan's 11:00 time exit) if nothing fired; an early-close session falls back to its last bar.
  6. Quarterly roll-seam days are skipped (augur_engine.rolls.seam_days) - the gap IS the quantity the NOADJ roll stitch
     corrupts. The scan did not skip them; this is a house guard, and it can drop a few trades vs the scan.

The ETH master is read inside run_backtest (precedent: GAPGO_1_0 / MISC_SUPERSCALPER read masters), cut at the last RTH date the
engine handed in - so it never reaches past the run's own window (lockbox-safe by construction). If the ETH master is missing,
retrace_filter="not_retraced" trades nothing rather than guessing.

Run with cost_pts=0.533 (intraday RT), NQ 5m RTH, db_noadj_rth. Needs day_id + index.
"""
import numpy as np
import pandas as pd

STRATEGY_NAME = 'GAPFADE 2.0 · opening-gap fade, overnight not retraced'
DESCRIPTION = ("Fade an opening gap of at least gap_min x ADR20 toward yesterday's close when the first 5-minute bar turns "
               "back and the overnight session had NOT already retraced half of it. Enter 09:35, target prior close, ATR "
               "stop, flat by 11:00. E1b revival of leg-scan M1 (PF 1.43 disc / 1.46 holdout, thin).")

_AUGUR_MARKET = {"instrument": "NQ", "timeframe": "5m"}
# From-scratch revival of a leg-scan cell, not a variant of GAPFADE_1_0 (a different gap unit, entry, exit and filter) -
# deliberately no _AUGUR_PARENT.

DEFAULT_PARAMS = {
    "gap_min": {
        "default": 0.3, "min": 0.2, "max": 1.0, "step": 0.1, "type": "float",
        "label": "Gap threshold (x ADR20)",
        "tooltip": "Trade only gaps at least this many 20-day average daily ranges. The leg scan read 0.3 / 0.5 / 0.8; all "
                   "three not-retraced cells held on holdout (PF 1.46 / 1.64 / 1.74) with falling trade counts.",
    },
    "retrace_filter": {
        "default": "not_retraced", "type": "str", "options": ["not_retraced", "all"],
        "label": "Overnight retrace filter",
        "tooltip": "not_retraced = skip days whose overnight session already traded back half the gap (the scan's edge). "
                   "all = no filter (the control: PF 1.03-1.15 in the scan).",
    },
    "stop_atr_mult": {
        "default": 1.5, "min": 1.0, "max": 2.5, "step": 0.25, "type": "float",
        "label": "Stop (x 5m ATR14)",
        "tooltip": "Protective stop distance as a multiple of the 14-bar ATR of the 5-minute chart at the bar before entry. "
                   "1.5 = the leg scan's fixed stop.",
    },
}

PARAM_GRID_PRESETS = {
    "Short  (scan cell)": {"gap_min": [0.3], "retrace_filter": ["not_retraced"], "stop_atr_mult": [1.5]},
    "Medium (gap x filter)": {"gap_min": [0.3, 0.5, 0.8], "retrace_filter": ["not_retraced", "all"],
                              "stop_atr_mult": [1.5]},
    "Long   (full surface)": {"gap_min": [0.2, 0.3, 0.4, 0.5, 0.6, 0.8, 1.0], "retrace_filter": ["not_retraced", "all"],
                              "stop_atr_mult": [1.0, 1.25, 1.5, 2.0, 2.5]},
}

ADR_LEN = 20
ATR_LEN = 14
_ETH_CACHE = {}

from augur_engine.rolls import seam_days as detect_roll_seams  # the ONE audited seam calendar


def _session_bounds(day_id, n):
    bounds = []
    a = 0
    while a < n:
        b = a
        while b < n and day_id[b] == day_id[a]:
            b += 1
        bounds.append((a, b))
        a = b
    return bounds


def _ny(ix):
    ix = pd.DatetimeIndex(ix)
    return ix.tz_convert("America/New_York").tz_localize(None) if ix.tz is not None else ix


def _overnight_hilo(d_first, d_last):
    """{date: (low, high)} of the NQ ETH bars from the prior 18:00 to the 09:25 bar, dates d_first..d_last only."""
    key = (str(d_first), str(d_last))
    if key in _ETH_CACHE:
        return _ETH_CACHE[key]
    out = None
    try:
        from augur_engine.data import find_master, load_master_arrays
        m = find_master("NQ", "5m", "eth", "db_noadj_eth")
        if m is not None:
            A = load_master_arrays(m, date_from=str(pd.Timestamp(d_first) - pd.Timedelta(days=4))[:10],
                                   date_to=str(d_last)[:10])
            t = _ny(A["index"])
            e = pd.DataFrame({"h": np.asarray(A["high"], float), "l": np.asarray(A["low"], float)}, index=t)
            e = e[e.index.strftime("%H:%M") < "09:30"]
            sess = (e.index + pd.Timedelta(hours=6)).normalize()        # the ETH day rolls at 18:00 ET
            g = e.groupby(sess)
            lo, hi = g["l"].min(), g["h"].max()
            keep = (lo.index >= pd.Timestamp(d_first)) & (lo.index <= pd.Timestamp(d_last))
            out = {d: (float(a), float(b)) for d, a, b in zip(lo.index[keep], lo.values[keep], hi.values[keep])}
    except Exception:
        out = None
    _ETH_CACHE[key] = out
    return out


def run_backtest(
    opens, highs, lows, closes,
    volumes=None, day_id=None, index=None,
    gap_min: float = 0.3, retrace_filter: str = "not_retraced", stop_atr_mult: float = 1.5,
    return_trades: bool = False, _stop_event=None, _pause_event=None,
    **_ignore,
):
    o = np.asarray(opens, float); h = np.asarray(highs, float)
    l = np.asarray(lows, float); c = np.asarray(closes, float)
    n = len(c)
    if n < 50 or day_id is None or index is None or len(day_id) != n:
        return None
    bounds = _session_bounds(np.asarray(day_id), n)
    D = len(bounds)
    if D < ADR_LEN + 3:
        return None
    gap_min = float(gap_min); stop_atr_mult = float(stop_atr_mult)
    t = _ny(index)
    hm = t.strftime("%H:%M")
    day_open = np.array([o[a] for a, b in bounds])
    day_close = np.array([c[b - 1] for a, b in bounds])
    rng_d = np.array([h[a:b].max() - l[a:b].min() for a, b in bounds])
    day_ts = [t[a] for a, b in bounds]
    seams = set(detect_roll_seams(day_open, day_close, day_ts))
    kern = np.concatenate([[0.0], np.cumsum(rng_d)])
    pc = np.concatenate([[c[0]], c[:-1]])
    tr = np.maximum(h - l, np.maximum(np.abs(h - pc), np.abs(l - pc)))
    atr5 = pd.Series(tr).rolling(ATR_LEN, min_periods=ATR_LEN).mean().values
    on = None
    if retrace_filter == "not_retraced":
        on = _overnight_hilo(day_ts[0].normalize(), day_ts[-1].normalize())
        if on is None:
            return None

    pnl_list = []; trade_log = []
    for d in range(ADR_LEN + 1, D):
        if d in seams:
            continue
        a, b = bounds[d]
        if b - a < 3 or hm[a] != "09:30" or hm[a + 1] != "09:35":
            continue
        adr = (kern[d] - kern[d - ADR_LEN]) / ADR_LEN            # previous 20 sessions only
        if adr <= 0:
            continue
        prior = day_close[d - 1]
        gap = day_open[d] - prior
        if abs(gap) < gap_min * adr or abs(gap) < 1e-9:
            continue
        gap_up = gap > 0
        if (c[a] > o[a]) == gap_up:                               # first bar extends the gap: no fade
            continue
        if on is not None:
            hl = on.get(day_ts[d].normalize())
            if hl is None:
                continue
            half = prior + 0.5 * gap
            retraced = (hl[0] <= half) if gap_up else (hl[1] >= half)
            if retraced:
                continue
        side = -1 if gap_up else 1
        ei = a + 1
        atr = atr5[ei - 1]
        if not atr == atr or atr <= 0:
            continue
        entry = float(o[ei]); target = float(prior)
        stop = entry - side * stop_atr_mult * atr
        xi = next((j - 1 for j in range(ei, b) if hm[j] == "11:00"), b - 1)
        if xi < ei:
            continue
        px, xb = float(c[xi]), xi
        for j in range(ei, xi + 1):
            if side > 0:
                if o[j] <= stop: px, xb = float(o[j]), j; break
                if l[j] <= stop: px, xb = float(stop), j; break
                if h[j] >= target: px, xb = target, j; break
            else:
                if o[j] >= stop: px, xb = float(o[j]), j; break
                if h[j] >= stop: px, xb = float(stop), j; break
                if l[j] <= target: px, xb = target, j; break
        pnl = side * (px - entry)
        pnl_list.append(pnl)
        if return_trades:
            trade_log.append((int(ei), int(xb), float(pnl), int(side), entry))
        if _stop_event is not None and _stop_event.is_set():
            return None

    if not pnl_list:
        return None
    pnls = np.array(pnl_list, float)
    wins = pnls[pnls > 0]; losses = pnls[pnls < 0]
    gw = float(wins.sum()); gl = float(-losses.sum())
    cum = np.cumsum(pnls); peak = np.maximum.accumulate(cum)
    out = {
        "total_pnl": float(pnls.sum()), "num_trades": int(len(pnls)),
        "win_rate": float(100.0 * len(wins) / len(pnls)),
        "profit_factor": (gw / gl) if gl > 1e-9 else (float("inf") if gw > 0 else 0.0),
        "max_drawdown": float((cum - peak).min()),
        "avg_pnl": float(pnls.mean()),
        "wins": int(len(wins)), "losses": int(len(losses)),
    }
    if return_trades:
        out["trades"] = trade_log
    return out


if __name__ == "__main__":
    # Smoke vs the leg scan's "M1 FADE g=0.3 not_retraced" cell: 110 + 103 = 213 trades over 2010-06-07..2025-06-30,
    # PF 1.43 / 1.46 (the seam skip and the prior-bar ATR can move a few trades).
    import os, sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from augur_engine.engine import run_backtest as _rb
    from augur_engine.data import find_master, load_master_arrays
    A = load_master_arrays(find_master("NQ", "5m", "rth", "db_noadj_rth"), date_from="2010-06-07", date_to="2025-06-30")
    for rf in ("not_retraced", "all"):
        p = {k: v["default"] for k, v in DEFAULT_PARAMS.items()}
        p["retrace_filter"] = rf
        r = _rb(os.path.abspath(__file__), arrays=A, params=p, cost_pts=0.533, return_trades=True)
        print("%-12s n=%d net=$%s PF=%.3f" % (rf, r["num_trades"], format(round(r["total_pnl"] * 20), ","), r["profit_factor"]))
    print("scan: not_retraced 213 trades PF 1.43/1.46 ; all 996 trades PF 1.12/1.03")
