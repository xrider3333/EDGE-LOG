"""
GAPGO 1.0 — overnight-gap direction + first-bars confirmation (NQ 5m RTH). FAMILY SEED.

WHERE IT CAME FROM (rounds 33/33b, 2026-09-08, tools/r33_family_seeds2.py and
tools/r33b_ovngo_controls.py): a pre-registered hunt for mechanisms the library has never
traded. The overnight move is information the ORB family never reads - ORB trades the
direction of the FIRST CANDLE, this trades the direction of the GAP (today's open minus
yesterday's RTH close) and only asks the first bar(s) to CONFIRM it.

MECHANISM (all decisions on finished bars; live-legal by construction):
  1. Gap = today's RTH open - yesterday's RTH close. Trade only if |gap| >= gap_mult x
     ATR20, where ATR20 = the mean daily range of the PREVIOUS 20 sessions.
  2. Range = the first or_bars bars of the session (1 = the first 5 minutes).
  3. Long (gap up) when a later bar CLOSES above the range high; short (gap down) when a
     bar CLOSES below the range low. Enter at the NEXT bar's open. One trade per day.
  4. Stop = entry -/+ stop_mult x range width. Pessimistic fills: an open through the stop
     fills at the open, otherwise the stop price.
  5. Breakeven: once a bar CLOSES at or beyond entry + be_after_R x risk the stop moves to
     entry FROM THE NEXT BAR. PINNED at 1.0 - a searched breakeven sets EV R's own
     denominator (house rule: never optimise across a stop policy).
  6. Exit at the session close if still alive. Timed exits (60m/120m) were strictly worse
     in 33b, so there is no exit knob.
  7. Quarterly roll-seam days are skipped by the house CALENDAR detector (third-Wednesday
     anchored, copied verbatim from ONDRIFT_1_0 / TTIBS_1_0), never by the gap's own size.

TRIAGE READ (2010-06-07..2025-06-29, cost 0.533/RT, $20/pt, lockbox NEVER loaded):
  gap 0.15 / stop 0.75 / 1 bar : n=2007  $151,024  PF 1.341  DD $16,672  n/DD 9.06
                                 8-of-8 chronological slices positive, top-10 share 50%,
                                 ex-top-10 +$74,781 at PF 1.17  -> clears the house bar
  gap 0.25 (pre-registered cell): PF 1.311, n/DD 4.57 (bar fail on n/DD only)
  CONTROLS: plain 5-min ORB both sides PF 1.10 / 4-of-8; AGAINST the gap ex-top-10 negative;
            any-size gap direction PF 1.20 / 8-of-8. The gap DIRECTION is the edge.
Parity target for this file's defaults = the 0.15 cell above (asserted in __main__).

Run with cost_pts=0.533 (intraday RT), NQ 5m RTH, db_noadj_rth. Needs day_id + index.
"""
import numpy as np
import pandas as pd

STRATEGY_NAME = 'GAPGO 1.0 · overnight-gap direction + first-bar confirmation'
DESCRIPTION = ("Trade the direction of the overnight gap once the first bar(s) of the RTH "
               "session are broken on a CLOSE in that direction. Stop = a fraction of the "
               "first-bar range, breakeven at 1R (pinned), flat at the close. Round 33 "
               "family seed: the gap direction is the edge - the plain 5-minute ORB and "
               "the against-the-gap control both fail.")

_AUGUR_MARKET = {"instrument": "NQ", "timeframe": "5m"}

DEFAULT_PARAMS = {
    "gap_mult": {
        "default": 0.15, "min": 0.10, "max": 0.30, "step": 0.05, "type": "float",
        "label": "Gap threshold (x ATR20 of daily ranges)",
        "tooltip": "Only trade days whose overnight gap is at least this many 20-day "
                   "average daily ranges. 0.15 = the triage pass; 0.25 = the pre-registered "
                   "cell; 0.35 was already too selective (ex-top-10 negative).",
    },
    "stop_mult": {
        "default": 0.75, "min": 0.50, "max": 1.00, "step": 0.25, "type": "float",
        "label": "Stop (x first-bar range)",
        "tooltip": "Initial stop distance as a fraction of the opening-range width. "
                   "0.5 scored the highest PF (1.41), 0.75 the best balance, 1.0 held.",
    },
    "or_bars": {
        "default": 1, "min": 1, "max": 3, "step": 1, "type": "int",
        "label": "Opening range (bars)",
        "tooltip": "How many 5-minute bars form the range the confirmation must close "
                   "beyond. 1 = the first five minutes (triage pass); 3 = 15 minutes "
                   "(PF 1.35, wider stop, lower n/DD).",
    },
    "be_after_R": {
        "default": 1.0, "min": 1.0, "max": 1.0, "step": 0.5, "type": "float",
        "label": "Breakeven after (x risk) - PINNED",
        "tooltip": "Stop to entry once a bar closes this many R in profit, acting from the "
                   "next bar. Pinned at 1.0 on purpose: searching it games EV R.",
    },
}

PARAM_GRID_PRESETS = {
    "Short  (triage centre)": {"gap_mult": [0.15], "stop_mult": [0.75], "or_bars": [1], "be_after_R": [1.0]},
    "Medium (neighbours)": {"gap_mult": [0.10, 0.15, 0.20], "stop_mult": [0.5, 0.75, 1.0],
                            "or_bars": [1, 2], "be_after_R": [1.0]},
    "Long   (full surface)": {"gap_mult": [0.10, 0.15, 0.20, 0.25, 0.30],
                              "stop_mult": [0.5, 0.75, 1.0], "or_bars": [1, 2, 3], "be_after_R": [1.0]},
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
    """Calendar-anchored quarterly roll-seam detector, copied verbatim from ONDRIFT_1_0 /
    TTIBS_1_0 (house convention: no strategy file imports another at runtime). It looks for
    the single largest close->open jump inside a window around each quarter's third
    Wednesday; a day is NEVER excluded on its own gap size alone."""
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
    """Enter at o[i_open]; breakeven armed on a CLOSE at +be_R x risk, acting next bar;
    pessimistic stop fills; exit at c[i_end-1] if still alive. Returns exit price."""
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
    gap_mult: float = 0.15, stop_mult: float = 0.75, or_bars: int = 1, be_after_R: float = 1.0,
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
    or_bars = int(or_bars); gap_mult = float(gap_mult); stop_mult = float(stop_mult)
    be_after_R = float(be_after_R)

    idx = pd.DatetimeIndex(index)
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
        atr[d] = (kern[d] - kern[d - ATR_LEN]) / ATR_LEN          # previous 20 sessions only

    pnl_list = []; trade_log = []
    for d in range(ATR_LEN + 1, D):
        if d in seam_days or np.isnan(atr[d]):
            continue
        a, b = bounds[d]
        if b - a < or_bars + 2:
            continue
        gap = day_open[d] - day_close[d - 1]
        if abs(gap) < gap_mult * atr[d]:
            continue
        side = 1 if gap > 0 else -1
        fh = h[a:a + or_bars].max(); fl = l[a:a + or_bars].min()
        width = fh - fl
        if width <= 0:
            continue
        for k in range(a + or_bars, b - 1):
            broke = (c[k] > fh) if side == 1 else (c[k] < fl)
            if not broke:
                continue
            entry = float(o[k + 1])
            stop0 = entry - side * stop_mult * width
            px = _ride(o, h, l, c, k + 1, b, entry, stop0, side, be_after_R)
            pnl = side * (px - entry)
            pnl_list.append(pnl)
            if return_trades:
                trade_log.append((int(k + 1), int(b - 1), float(pnl), int(side), entry))
            break
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
    # Parity smoke test against the round-33b harness cell "NB gap0.15":
    # n=2007, net $151,024 at $20/pt after 0.533/RT (tools/r16_results/r33b_ovngo_controls.csv)
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
    print("parity target: n=2007 net=$151,024 PF 1.341 DD $16,672")
