"""
GAPGO TRAVEL 1.0 — distance-from-open continuation (NQ 5m RTH). Second trigger of the GAPGO
(opening-momentum) family, round 36 (tools/r36_family_seeds5.py, tools/r36b_travel_vs_gapgo.py).

MECHANISM (finished bars only; live-legal):
  1. At a fixed clock time (clock_min, minutes after midnight ET; 600 = 10:00) read the last
     FINISHED bar's close. Travel = close - session open.
  2. If |travel| >= k_atr x ATR20 (mean daily range of the previous 20 sessions), enter at the
     next bar's open in the travel direction. One trade per day.
  3. Stop = session open when stop_frac = 1.0 (the whole travel is the risk); stop_frac 0.5 =
     half-way between entry and the open. Pessimistic fills.
  4. Breakeven at be_after_R x risk, armed on a close, acting next bar. PINNED at 1.0.
  5. Flat at the session close. Quarterly roll-seam days skipped by the calendar detector.

WHY IT IS A FAMILY MEMBER AND NOT A TWIN: it shares only 26% of GAPGO's trade days, earns its
money on the days GAPGO does NOT trade (+$157,283 on non-GAPGO days, -$10,896 on shared days),
daily-PnL correlation 0.24, and pooled 1:1 with GAPGO the net-over-drawdown rises to 9.8
against 9.1 and 8.1 alone. Same factor (the direction the market is already moving at the open
continues), different read of it (a distance threshold, not a gap).

TRIAGE (2010-06-07..2025-06-29, 0.533/RT, $20/pt, lockbox never loaded):
  10:00 / 0.3 ATR / stop at open : n=1050  $146,387  PF 1.345  DD $18,115  n/DD 8.08
                                   6-of-8 slices, top-10 share 54%, ex-top-10 +$67,064 PF 1.16
  the edge decays with the clock (10:30 PF 1.23, 11:00 PF 1.16) and 0.5 ATR at 10:00 is 90% top-10.
Parity target for this file's defaults = the 10:00 / 0.3 cell (asserted in __main__).
"""
import numpy as np
import pandas as pd

STRATEGY_NAME = 'GAPGO TRAVEL 1.0 · distance-from-open continuation'
DESCRIPTION = ("At a fixed morning clock time, if price has already travelled a fraction of the "
               "20-day average daily range from the session open, go with it: stop at the open, "
               "breakeven at 1R (pinned), flat at the close. Second trigger of the opening-momentum "
               "(GAPGO) family - it trades the days GAPGO does not.")

_AUGUR_MARKET = {"instrument": "NQ", "timeframe": "5m"}

DEFAULT_PARAMS = {
    "clock_min": {
        "default": 600, "min": 585, "max": 630, "step": 15, "type": "int",
        "label": "Decision time (minutes after midnight ET)",
        "tooltip": "585 = 09:45, 600 = 10:00 (triage pass), 615 = 10:15, 630 = 10:30. Later "
                   "decisions decayed in triage (11:00 was PF 1.16).",
    },
    "k_atr": {
        "default": 0.3, "min": 0.2, "max": 0.5, "step": 0.1, "type": "float",
        "label": "Travel threshold (x ATR20 of daily ranges)",
        "tooltip": "How far price must already have moved from the open. 0.3 = the pass; 0.5 "
                   "trades a third as often and was 90 percent top-ten in triage.",
    },
    "stop_frac": {
        "default": 1.0, "min": 0.5, "max": 1.0, "step": 0.5, "type": "float",
        "label": "Stop distance (fraction of entry-to-open)",
        "tooltip": "1.0 = the stop sits at the session open (whole travel at risk). 0.5 = half-way.",
    },
    "be_after_R": {
        "default": 1.0, "min": 1.0, "max": 1.0, "step": 0.5, "type": "float",
        "label": "Breakeven after (x risk) - PINNED",
        "tooltip": "Pinned at 1.0 on purpose: searching the breakeven games EV R.",
    },
}

PARAM_GRID_PRESETS = {
    "Short  (triage centre)": {"clock_min": [600], "k_atr": [0.3], "stop_frac": [1.0], "be_after_R": [1.0]},
    "Medium (neighbours)": {"clock_min": [585, 600, 615], "k_atr": [0.2, 0.3, 0.4], "stop_frac": [1.0], "be_after_R": [1.0]},
    "Long   (full surface)": {"clock_min": [585, 600, 615, 630], "k_atr": [0.2, 0.3, 0.4, 0.5],
                              "stop_frac": [0.5, 1.0], "be_after_R": [1.0]},
}

ATR_LEN = 20


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


def _third_weekday(year, month, weekday=2):
    d0 = pd.Timestamp(year=year, month=month, day=1)
    offset = (weekday - d0.weekday()) % 7
    first = d0 + pd.Timedelta(days=offset)
    return first + pd.Timedelta(weeks=2)


def detect_roll_seams(day_open, day_close, day_ts, ratio_th=2.5, abs_th=15.0,
                      base_win=60, pre_days=12, post_days=2):
    """Calendar-anchored quarterly roll-seam detector (verbatim copy, house convention)."""
    n = len(day_close)
    if n < base_win + 5:
        return []
    ts = pd.DatetimeIndex(day_ts)
    if ts.tz is not None:
        ts = ts.tz_localize(None)
    gap = np.empty(n); gap[:] = np.nan
    gap[1:] = day_open[1:] - day_close[:-1]
    abs_gap = np.abs(gap)
    baseline = np.full(n, np.nan)
    for i in range(base_win, n):
        window = abs_gap[i - base_win:i]
        window = window[~np.isnan(window)]
        if len(window) >= max(10, base_win // 3):
            baseline[i] = np.median(window)
    quarters = sorted({(t.year, t.month) for t in ts if t.month in (3, 6, 9, 12)})
    seams = []
    for (y, m) in quarters:
        wed3 = _third_weekday(y, m)
        win_start = wed3 - pd.Timedelta(days=pre_days)
        win_end = wed3 + pd.Timedelta(days=post_days)
        idx_in_win = [i for i in range(n) if win_start <= ts[i] <= win_end
                      and not np.isnan(gap[i]) and not np.isnan(baseline[i])]
        if not idx_in_win:
            continue
        best = max(idx_in_win, key=lambda i: abs_gap[i])
        if abs_gap[best] >= abs_th and baseline[best] > 0 and \
           (abs_gap[best] / baseline[best]) >= ratio_th:
            seams.append(best)
    return sorted(seams)


def _ride(o, h, l, c, i_open, i_end, entry, stop0, side, be_R):
    R = side * (entry - stop0); stop = stop0; be = False; be_next = False
    for i in range(i_open, i_end):
        if be_next:
            if (side == 1 and entry > stop) or (side == -1 and entry < stop):
                stop = entry
            be_next = False
        if side == 1:
            if o[i] <= stop: return o[i]
            if l[i] <= stop: return stop
            if not be and be_R > 0 and c[i] >= entry + be_R * R: be = True; be_next = True
        else:
            if o[i] >= stop: return o[i]
            if h[i] >= stop: return stop
            if not be and be_R > 0 and c[i] <= entry - be_R * R: be = True; be_next = True
    return c[i_end - 1]


def run_backtest(
    opens, highs, lows, closes,
    volumes=None, day_id=None, index=None,
    clock_min: int = 600, k_atr: float = 0.3, stop_frac: float = 1.0, be_after_R: float = 1.0,
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
    if D < ATR_LEN + 3:
        return None
    clock_min = int(clock_min); k_atr = float(k_atr); stop_frac = float(stop_frac)
    be_after_R = float(be_after_R)

    idx = pd.DatetimeIndex(index)
    mins = (idx.hour * 60 + idx.minute).values
    day_open = np.array([o[a] for a, b in bounds])
    day_close = np.array([c[b - 1] for a, b in bounds])
    day_high = np.array([h[a:b].max() for a, b in bounds])
    day_low = np.array([l[a:b].min() for a, b in bounds])
    day_ts = [idx[a] for a, b in bounds]
    seam_days = set(detect_roll_seams(day_open, day_close, day_ts))
    rng_d = day_high - day_low
    kern = np.concatenate([[0.0], np.cumsum(rng_d)])
    atr = np.full(D, np.nan)
    for d in range(ATR_LEN, D):
        atr[d] = (kern[d] - kern[d - ATR_LEN]) / ATR_LEN

    pnl_list = []; trade_log = []
    for d in range(ATR_LEN + 1, D):
        if d in seam_days or np.isnan(atr[d]):
            continue
        a, b = bounds[d]
        ks = np.nonzero(mins[a:b - 1] >= clock_min)[0]
        if len(ks) == 0:
            continue
        i = a + ks[0] - 1 if ks[0] > 0 else a         # last FINISHED bar before the clock time
        trav = c[i] - day_open[d]
        if abs(trav) < k_atr * atr[d]:
            continue
        side = 1 if trav > 0 else -1
        entry = float(o[i + 1])
        stop0 = entry - stop_frac * (entry - day_open[d])
        if side * (entry - stop0) <= 0:
            continue
        px = _ride(o, h, l, c, i + 1, b, entry, stop0, side, be_after_R)
        pnl = side * (px - entry)
        pnl_list.append(pnl)
        if return_trades:
            trade_log.append((int(i + 1), int(b - 1), float(pnl), int(side), entry))
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
    # Parity against the round-36 harness cell "1000/k0.3/stop=open": n=1050, $146,387, PF 1.345, DD $18,115
    import os, sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from augur_engine.engine import run_backtest as _rb
    from augur_engine.data import find_master, load_master_arrays
    A = load_master_arrays(find_master("NQ", "5m", "rth", "db_noadj_rth"),
                           date_from="2010-06-07", date_to="2025-06-29")
    r = _rb(os.path.abspath(__file__), arrays=A, params={k: v["default"] for k, v in DEFAULT_PARAMS.items()},
            cost_pts=0.533, return_trades=True)
    print("n=%d net=$%s PF=%.3f DD=$%s" % (r["num_trades"], format(round(r["total_pnl"] * 20), ","),
                                           r["profit_factor"], format(round(-r["max_drawdown"] * 20), ",")))
    print("parity target: n=1050 net=$146,387 PF 1.345 DD $18,115")
