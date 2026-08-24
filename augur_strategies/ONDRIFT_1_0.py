"""
ONDRIFT 1.0 — overnight drift, uptrend-filtered (NQ, long-only). STATUS: DEAD
(retracted 2026-08-24, same day as the triage "pass" — see below).

The round-18 MISC-hunt pass (STUDIES rows 534-546, 2026-08-24): buy the RTH close
when the close is above its N-day daily SMA, sell the next RTH open. That is the
entire strategy — no stop (round 18b measured every resting Globex stop level as
strictly worse: stops sell the low of the night and the drawdown improves by zero),
no target, flat every day from 09:30 to 16:00.

Mechanics per daily bar d (daily aggregates of the 5m RTH master):
  - signal: day_close[d] > SMA(day_close, sma_len)[d]   (filter_mode="uptrend")
            or unconditional                            (filter_mode="always")
  - entry:  day d's LAST 5m bar CLOSE (live = a market-on-close order armed in the
            final minute; the signal uses that same closing print)
  - exit:   day d+1's FIRST 5m bar OPEN (market-on-open)
  - the overnight jump d -> d+1 is skipped entirely when d+1 is a detected
    quarterly roll seam (the jump would be the contract stitch, not the market)

COST: run with cost_pts=0.783 (the overnight NQ round-trip: $5.66 commission +
0.5 pt Globex slip at $20/pt) — NOT the 0.533 RTH figure.

RETRACTION (2026-08-24): the triage harness (tools/r18_misc_triage.py) skipped
roll nights by flagging any night whose OWN jump was >=15 pts and >=2.5x the
trailing median — but a night's jump size is only knowable the next morning, so
the skip was accidental FORESIGHT that quietly removed 441 of the worst nights
(triage read: $282,478 / PF 1.498 / MAR 14.59 / n=2541). This plugin uses the
house calendar-anchored roll detector (copied verbatim from GAPFADE_1_0.py /
TTIBS_1_0.py) and is the honest form: window 2010-06-07 -> 2025-06-29,
cost 0.783: n=2982 / $218,592 / PF 1.205 / DD $41,696 / MAR 5.24 — UNDER the
triage bar (PF>=1.25, MAR>=8). A pre-registered causal volatility filter (skip
the night after a big-range day, knowable at the close; k in {1.0,1.5,2.0} x
ATR20) recovers nothing: best cell MAR 4.6. The 18b stop study (every resting
Globex stop level strictly worse) was measured honestly on the 1m ETH tape and
stands. Kept in the library as the honest reference implementation. DO NOT
resurrect from the triage numbers.

Trades never span more than one overnight; every trade entered on or before a
lockbox seal date exits the next morning, so entry-time slicing stays honest.
"""
import numpy as np
import pandas as pd

STRATEGY_NAME = 'ONDRIFT 1.0 · overnight drift, uptrend-filtered (long-only)'
DESCRIPTION = ("Buy the RTH close when the close is above its N-day daily SMA, sell "
               "the next RTH open. No stop (measured optimal on the 1m ETH tape), no "
               "target. Roll-seam nights skipped. Run with cost_pts=0.783 (overnight "
               "RT), not 0.533.")

_AUGUR_MARKET = {"instrument": "NQ", "timeframe": "5m"}

DEFAULT_PARAMS = {
    "sma_len": {
        "default": 200, "min": 100, "max": 300, "step": 25, "type": "int",
        "label": "Uptrend SMA (days)",
        "tooltip": "Daily-close SMA length for the uptrend filter. 200 = the "
                   "triage-passing cell; 150/250 held in the neighbor check.",
    },
    "filter_mode": {
        "default": "uptrend", "type": "str",
        "options": ["uptrend", "always"],
        "label": "Filter",
        "tooltip": "uptrend = only hold nights when close > SMA (the pass: MAR 14.6). "
                   "always = hold every night (triage: 3x the drawdown, MAR 4.2).",
    },
}

PARAM_GRID_PRESETS = {
    "Short  (pinned cell)": {"sma_len": [200], "filter_mode": ["uptrend"]},
    "Medium (neighbors)": {"sma_len": [150, 200, 250], "filter_mode": ["uptrend", "always"]},
    "Long   (full surface)": {"sma_len": [100, 125, 150, 175, 200, 225, 250, 275, 300],
                              "filter_mode": ["uptrend", "always"]},
}


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
    """Date of the 3rd occurrence of `weekday` (0=Mon..6=Sun) in (year, month).
    weekday=2 -> 3rd Wednesday (the standard quarterly futures-roll reference)."""
    d0 = pd.Timestamp(year=year, month=month, day=1)
    offset = (weekday - d0.weekday()) % 7
    first = d0 + pd.Timedelta(days=offset)
    return first + pd.Timedelta(weeks=2)


def detect_roll_seams(day_open, day_close, day_ts, ratio_th=2.5, abs_th=15.0,
                       base_win=60, pre_days=12, post_days=2):
    """Return a sorted list of daily-bar indices `s` such that the jump
    close[s-1] -> open[s] is a detected quarterly roll seam. Copied verbatim from
    TTIBS_1_0.py (calibrated on the 2010-2025-06-30 NQ window; see that file's docstring
    and scratchpad/ttibs/ttibs_triage_prereg.md for the calibration detail) -- kept as an
    exact copy rather than a cross-import so this plugin stays self-contained per house
    convention (no strategy file imports another strategy file at runtime).
    """
    n = len(day_close)
    if n < base_win + 5:
        return []
    ts = pd.DatetimeIndex(day_ts)
    if ts.tz is not None:
        ts = ts.tz_localize(None)             # compare tz-naive vs. tz-naive 3rd-Wed refs
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


def run_backtest(
    opens, highs, lows, closes,
    volumes=None, day_id=None, index=None,
    sma_len: int = 200, filter_mode: str = "uptrend",
    return_trades: bool = False, _stop_event=None, _pause_event=None,
    **_ignore,
):
    o = np.asarray(opens, float); c = np.asarray(closes, float)
    n = len(c)
    if n < 20 or day_id is None or index is None or len(day_id) != n:
        return None
    bounds = _session_bounds(np.asarray(day_id), n)
    D = len(bounds)
    sma_len = int(sma_len)
    if D < sma_len + 2:
        return None

    idx = pd.DatetimeIndex(index)
    day_open = np.array([o[a] for a, b in bounds])
    day_close = np.array([c[b - 1] for a, b in bounds])
    day_ts = [idx[a] for a, b in bounds]

    sma = np.full(D, np.nan)
    kern = np.concatenate([[0.0], np.cumsum(day_close)])
    for d in range(sma_len - 1, D):
        sma[d] = (kern[d + 1] - kern[d + 1 - sma_len]) / sma_len

    seam_days = set(detect_roll_seams(day_open, day_close, day_ts))

    pnl_list = []; trade_log = []
    for d in range(sma_len, D - 1):
        if (d + 1) in seam_days:
            continue
        if filter_mode == "uptrend" and not (day_close[d] > sma[d]):
            continue
        entry_bar = bounds[d][1] - 1
        exit_bar = bounds[d + 1][0]
        entry_px = float(c[entry_bar]); exit_px = float(o[exit_bar])
        pnl = exit_px - entry_px
        pnl_list.append(pnl)
        if return_trades:
            trade_log.append((int(entry_bar), int(exit_bar), float(pnl), 1,
                              entry_px, exit_px))
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
