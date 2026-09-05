"""
NQDIP 1.1 — NQDIP 1.0 plus three more dip legs (IBS, losing streak, gap-down), long-only.
Frequency lever for R / YR: same tape, more independent dip triggers. With use_ibs /
use_streak / use_gapdn OFF this file reproduces NQDIP_1_0 (run #307) to the dollar.
  IBS    : (close-low)/(high-low) of the daily bar < ibs_thr while close > trend
           -> buy next open; exit when IBS > ibs_exit or after ibs_hold days
  STREAK : streak_n consecutive lower closes while close > trend -> buy next open;
           exit on the first up close or after streak_hold days
  GAPDN  : open >= gap_atr x ATR20 below the prior close with prior close > trend ->
           signal on that day close, buy next open; exit on a close above the gap-day
           high or after gap_hold days

Provenance: the autonomous MISC hunt's walk-forward phase (rounds 25-26, 2026-08-25,
STUDIES rows 1027-1051 and 1141-1158, BOOKMARKS.md B11-B13). Out-of-sample only,
per-fold re-tuned, the eight-leg Nasdaq book (this file on QQQ + this file on NQ)
scored n=1250 / $706,799 / PF 1.95 / MAR 10.11 / 12-of-14 years, corr 0.04 to the
live champion book, and lifted the champion book's MAR 8.31 -> 11.20 when stacked.
This file exists so the app's Auto-Validate can search the same space with full
discovery (WF folds, sealed lockbox, PBO/DSR, surfaces) and put every detail on a
run card.

── What it trades ────────────────────────────────────────────────────────────────
Daily bars are aggregated from whatever master is loaded via `day_id` (an intraday
RTH master collapses to one bar per session; a daily master is already one bar per
day). Four independent mechanisms run side by side, each with its own position slot
(so up to 4 units can be on at once), all LONG-ONLY behind a trend filter
(day close > SMA(trend_len) of daily closes):
  RSI  : RSI(rsi_len) of daily closes < rsi_thr        -> exit when close > SMA(rsi_exit)
  DBL  : today's close is the lowest close of the last dbl_n days -> exit on an
         dbl_n-day closing high
  PB   : the day's low touches EMA(pb_ema) while yesterday closed above it
         -> exit on a close above the entry-day's prior high, or after pb_hold days
  CAP  : a down day whose range >= cap_mult x ATR20 and which closes in the bottom
         cap_q of its range (no trend filter: capitulation is bought regardless)
         -> exit after cap_hold days
Every signal is evaluated on the day's CLOSE and filled at the NEXT day's OPEN;
every exit signal is evaluated on a close and filled at the next open. No stop:
the round-18b/22 studies measured stops as strictly harmful to this hold-for-days
edge; the gap risk is real and is in the numbers.

── Sizing and costs (INSIDE the plugin — set the job's cost_pts to 0) ──────────────
`asset` selects the model (auto-detected: one bar per session = ETF, else NQ;
not a searchable knob, so Auto-Validate never sweeps it):
  "NQ" : contracts = notional / (entry price x 20), rounded to whole MNQ micros
         (MNQ = $2/pt, so contracts_mnq = round(notional / (price x 2))); cost =
         cost_pts_rt (0.783 = overnight NQ round trip) x $2 x micros, plus 0.25 pt
         per quarterly roll crossed. Roll seams come from the house calendar-anchored
         detector (copied verbatim from ONDRIFT_1_0.py / GAPFADE_1_0.py); a seam
         night's jump is excluded from PnL because it is the contract stitch.
  "ETF": shares = notional / entry price; cost = cost_bps of notional per round trip.
PnL is returned in DOLLARS (the plugin contract allows SHARES*(EXIT-ENTRY)+FEE), so
the job must use mult = 1. Constant-notional sizing is the point: a 1-contract NQ
book has a notional that grew 5x over 2010-2025 and its drawdown lands in the last
years; at constant notional the same legs score MAR 6-10 instead of 3-4.

── Auto-Validate ranges ─────────────────────────────────────────────────────────────
The ranged knobs are the ones the walk-forward phase actually re-tuned (trend
length, RSI threshold/exit, N-day low, pullback EMA/hold, capitulation size/hold).
Sizing/cost knobs are fixed (min = max) so the search space is about the edge, not
the leverage. Requires day_id AND index (roll seams, dates).
"""
import numpy as np
import pandas as pd

STRATEGY_NAME = 'NQDIP 1.1 · Nasdaq dip book (7 long-only dip mechanisms, one file)'
_AUGUR_PARENT = "NQDIP_1_0.py"
DESCRIPTION = ("Four dip-buying mechanisms (2-day RSI, N-day low, pullback to a short EMA, "
               "capitulation day) traded side by side, long-only behind a trend filter, "
               "hold-for-days, no stop. Constant-notional sizing in whole MNQ micros (NQ) "
               "or shares (ETF); costs inside the plugin -> job cost_pts 0, mult 1.")

_AUGUR_MARKET = {"instrument": "NQ", "timeframe": "5m"}

DEFAULT_PARAMS = {
    "notional": {"default": 100000, "min": 100000, "max": 100000, "step": 1, "type": "int",
                 "label": "Notional per trade ($)", "tooltip": "Fixed. Each mechanism sizes to this exposure."},
    "cost_pts_rt": {"default": 0.783, "min": 0.783, "max": 0.783, "step": 0.001, "type": "float",
                    "label": "NQ round-trip cost (pts)", "tooltip": "Fixed: overnight NQ RT (commission + 0.5 pt Globex slip)."},
    "cost_bps": {"default": 2.0, "min": 2.0, "max": 2.0, "step": 0.5, "type": "float",
                 "label": "ETF round-trip cost (bps)", "tooltip": "Fixed: 2 basis points of notional per round trip."},
    "trend_len": {"default": 200, "min": 100, "max": 300, "step": 50, "type": "int",
                  "label": "Trend filter SMA (days)", "tooltip": "Longs only when the close is above this SMA of daily closes. WF drifted 150-300."},
    "rsi_len": {"default": 2, "min": 2, "max": 5, "step": 1, "type": "int", "label": "RSI length (days)",
                "tooltip": "Connors-style short RSI."},
    "rsi_thr": {"default": 10, "min": 5, "max": 30, "step": 5, "type": "int", "label": "RSI buy below",
                "tooltip": "Oversold trigger."},
    "rsi_exit": {"default": 5, "min": 3, "max": 10, "step": 1, "type": "int", "label": "RSI exit SMA (days)",
                 "tooltip": "Exit when the close is back above this short SMA."},
    "dbl_n": {"default": 7, "min": 3, "max": 15, "step": 1, "type": "int", "label": "N-day low / high",
              "tooltip": "Buy the lowest close of N days, sell the highest close of N days. WF drifted 4-15."},
    "pb_ema": {"default": 20, "min": 5, "max": 50, "step": 5, "type": "int", "label": "Pullback EMA (days)",
               "tooltip": "Buy the first touch of this EMA while yesterday closed above it."},
    "pb_hold": {"default": 10, "min": 3, "max": 20, "step": 1, "type": "int", "label": "Pullback max hold (days)"},
    "cap_mult": {"default": 1.5, "min": 1.0, "max": 2.5, "step": 0.25, "type": "float",
                 "label": "Capitulation range (x ATR20)", "tooltip": "Day range must be at least this many ATR20s."},
    "cap_q": {"default": 0.25, "min": 0.15, "max": 0.4, "step": 0.05, "type": "float",
              "label": "Capitulation close quantile", "tooltip": "Close must sit in the bottom fraction of the day's range."},
    "cap_hold": {"default": 5, "min": 1, "max": 8, "step": 1, "type": "int", "label": "Capitulation hold (days)"},
    "use_rsi": {"default": True, "type": "bool", "label": "Run the RSI leg"},
    "use_dbl": {"default": True, "type": "bool", "label": "Run the N-day-low leg"},
    "use_pb": {"default": True, "type": "bool", "label": "Run the pullback leg"},
    "use_cap": {"default": True, "type": "bool", "label": "Run the capitulation leg"},
    "ibs_thr": {"default": 0.2, "min": 0.1, "max": 0.3, "step": 0.05, "type": "float", "label": "IBS buy below",
                "tooltip": "Daily internal bar strength (close-low)/(high-low) below this = closed near the low."},
    "ibs_exit": {"default": 0.7, "min": 0.5, "max": 0.9, "step": 0.1, "type": "float", "label": "IBS exit above"},
    "ibs_hold": {"default": 5, "min": 2, "max": 8, "step": 1, "type": "int", "label": "IBS max hold (days)"},
    "streak_n": {"default": 3, "min": 2, "max": 5, "step": 1, "type": "int", "label": "Down-close streak length"},
    "streak_hold": {"default": 5, "min": 2, "max": 8, "step": 1, "type": "int", "label": "Streak max hold (days)"},
    "gap_atr": {"default": 0.5, "min": 0.25, "max": 1.0, "step": 0.25, "type": "float", "label": "Gap-down size (x ATR20)"},
    "gap_hold": {"default": 3, "min": 1, "max": 5, "step": 1, "type": "int", "label": "Gap-down max hold (days)"},
    "use_ibs": {"default": True, "type": "bool", "label": "Run the IBS leg"},
    "use_streak": {"default": True, "type": "bool", "label": "Run the losing-streak leg"},
    "use_gapdn": {"default": True, "type": "bool", "label": "Run the gap-down leg"},
}

PARAM_GRID_PRESETS = {
    "Short  (WF-phase defaults)": {"trend_len": [200], "rsi_len": [2], "rsi_thr": [10], "rsi_exit": [5],
                                   "dbl_n": [7], "pb_ema": [20], "pb_hold": [10],
                                   "cap_mult": [1.5], "cap_q": [0.25], "cap_hold": [5]},
    "Medium (the WF drift range)": {"trend_len": [150, 200, 250, 300], "rsi_len": [2, 3], "rsi_thr": [10, 20, 30],
                                    "rsi_exit": [5], "dbl_n": [6, 7, 10, 15], "pb_ema": [5, 20], "pb_hold": [10],
                                    "cap_mult": [1.25, 1.5], "cap_q": [0.2, 0.25], "cap_hold": [4, 5]},
}


def _session_bounds(day_id, n):
    bounds = []; a = 0
    while a < n:
        b = a
        while b < n and day_id[b] == day_id[a]:
            b += 1
        bounds.append((a, b)); a = b
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


def _wilder_rsi(x, per):
    d = np.diff(x, prepend=x[0]); up = np.where(d > 0, d, 0.0); dn = np.where(d < 0, -d, 0.0)
    au = np.zeros_like(x); ad = np.zeros_like(x)
    if len(x) <= per:
        return np.full_like(x, 50.0)
    au[per] = up[1:per + 1].mean(); ad[per] = dn[1:per + 1].mean()
    for i in range(per + 1, len(x)):
        au[i] = (au[i - 1] * (per - 1) + up[i]) / per
        ad[i] = (ad[i - 1] * (per - 1) + dn[i]) / per
    rs = np.divide(au, ad, out=np.full_like(x, np.inf), where=ad > 1e-12)
    return 100 - 100 / (1 + rs)


def _sma(x, L):
    k = np.concatenate([[0.0], np.cumsum(x)]); s = np.full(len(x), np.nan)
    for d in range(L - 1, len(x)):
        s[d] = (k[d + 1] - k[d + 1 - L]) / L
    return s


def _ema(x, L):
    e = np.full(len(x), np.nan)
    if len(x) < L:
        return e
    e[L - 1] = x[:L].mean(); kk = 2.0 / (L + 1)
    for d in range(L, len(x)):
        e[d] = e[d - 1] + kk * (x[d] - e[d - 1])
    return e


def run_backtest(
    opens, highs, lows, closes,
    volumes=None, day_id=None, index=None,
    asset: str = "auto", notional: int = 100000, cost_pts_rt: float = 0.783, cost_bps: float = 2.0,
    trend_len: int = 200, rsi_len: int = 2, rsi_thr: int = 10, rsi_exit: int = 5,
    dbl_n: int = 7, pb_ema: int = 20, pb_hold: int = 10,
    cap_mult: float = 1.5, cap_q: float = 0.25, cap_hold: int = 5,
    use_rsi: bool = True, use_dbl: bool = True, use_pb: bool = True, use_cap: bool = True,
    ibs_thr: float = 0.2, ibs_exit: float = 0.7, ibs_hold: int = 5,
    streak_n: int = 3, streak_hold: int = 5, gap_atr: float = 0.5, gap_hold: int = 3,
    use_ibs: bool = True, use_streak: bool = True, use_gapdn: bool = True,
    return_trades: bool = False, _stop_event=None, _pause_event=None, **_ignore,
):
    o = np.asarray(opens, float); h = np.asarray(highs, float)
    l = np.asarray(lows, float); c = np.asarray(closes, float)
    n = len(c)
    if n < 50 or day_id is None or index is None or len(day_id) != n:
        return None
    bounds = _session_bounds(np.asarray(day_id), n)
    D = len(bounds)
    if asset == "auto":
        # a daily master has exactly one bar per session -> ETF model; an intraday
        # futures master has many bars per session -> NQ/MNQ model.
        asset = "ETF" if n == D else "NQ"
    trend_len, rsi_len, rsi_thr, rsi_exit = int(trend_len), int(rsi_len), int(rsi_thr), int(rsi_exit)
    dbl_n, pb_ema, pb_hold, cap_hold = int(dbl_n), int(pb_ema), int(pb_hold), int(cap_hold)
    if D < trend_len + 30:
        return None
    idx = pd.DatetimeIndex(index)
    do = np.array([o[a] for a, b in bounds]); dh = np.array([h[a:b].max() for a, b in bounds])
    dl = np.array([l[a:b].min() for a, b in bounds]); dc = np.array([c[b - 1] for a, b in bounds])
    open_bar = np.array([a for a, b in bounds]); close_bar = np.array([b - 1 for a, b in bounds])
    day_ts = [idx[a] for a, b in bounds]
    seams = set(detect_roll_seams(do, dc, day_ts)) if asset == "NQ" else set()

    trend = _sma(dc, trend_len)
    rsi = _wilder_rsi(dc, rsi_len); rsi_x = _sma(dc, rsi_exit)
    ema = _ema(dc, pb_ema)
    atr20 = np.full(D, np.nan)
    for d in range(20, D):
        atr20[d] = (dh[d - 20:d] - dl[d - 20:d]).mean()

    def size(entry_px):
        if asset == "NQ":
            k = max(1, int(round(float(notional) / (entry_px * 2.0))))     # whole MNQ micros
            return k * 2.0, cost_pts_rt * 2.0 * k                          # $/pt, $ cost per RT
        sh = float(notional) / entry_px
        return sh, float(notional) * cost_bps / 10000.0

    def chain(de, dx, entry_px):
        """dollar PnL for a long entered at day de's open, exited at day dx's open."""
        dollars_per_pt, cost = size(entry_px)
        raw = dc[de] - entry_px
        for dd_ in range(de + 1, dx + 1):
            gap = do[dd_] - dc[dd_ - 1]
            if dd_ in seams:
                cost += 0.25 * dollars_per_pt
            else:
                raw += gap
            if dd_ < dx:
                raw += dc[dd_] - do[dd_]
        return raw * dollars_per_pt - cost

    ibs_hold, streak_n, streak_hold, gap_hold = int(ibs_hold), int(streak_n), int(streak_hold), int(gap_hold)
    rng_d = dh - dl
    ibs = np.where(rng_d > 1e-9, (dc - dl) / np.where(rng_d > 1e-9, rng_d, 1.0), 0.5)
    legs = [("RSI", use_rsi), ("DBL", use_dbl), ("PB", use_pb), ("CAP", use_cap),
            ("IBS", use_ibs), ("STREAK", use_streak), ("GAPDN", use_gapdn)]
    trade_log = []
    for mech, on in legs:
        if not on:
            continue
        pos = 0; de = 0; d = max(trend_len, 30)
        while d < D - 1:
            if _stop_event is not None and _stop_event.is_set():
                return None
            if pos == 0:
                s = False
                if mech == "RSI":
                    s = dc[d] > trend[d] and rsi[d] < rsi_thr
                elif mech == "DBL":
                    s = d >= dbl_n and dc[d] > trend[d] and dc[d] == dc[d - dbl_n + 1:d + 1].min()
                elif mech == "PB":
                    s = dc[d] > trend[d] and dl[d] <= ema[d] and dc[d - 1] > ema[d - 1]
                elif mech == "CAP":
                    rng = dh[d] - dl[d]
                    s = (dc[d] < do[d] and rng > 0 and not np.isnan(atr20[d]) and rng >= cap_mult * atr20[d]
                         and (dc[d] - dl[d]) / rng <= cap_q)
                elif mech == "IBS":
                    s = dc[d] > trend[d] and rng_d[d] > 0 and ibs[d] < ibs_thr
                elif mech == "STREAK":
                    s = (d >= streak_n and dc[d] > trend[d]
                         and all(dc[d - j] < dc[d - j - 1] for j in range(streak_n)))
                else:  # GAPDN
                    s = (not np.isnan(atr20[d]) and dc[d - 1] > trend[d - 1]
                         and (dc[d - 1] - do[d]) >= gap_atr * atr20[d])
                if s and (d + 1) not in seams:
                    pos, de = 1, d + 1; d += 1; continue
            else:
                ex = False
                if mech == "RSI":
                    ex = dc[d] > rsi_x[d]
                elif mech == "DBL":
                    ex = dc[d] == dc[d - dbl_n + 1:d + 1].max()
                elif mech == "PB":
                    ex = (dc[d] > dh[de - 1]) or (d - de >= pb_hold)
                elif mech == "CAP":
                    ex = (d - de >= cap_hold)
                elif mech == "IBS":
                    ex = (rng_d[d] > 0 and ibs[d] > ibs_exit) or (d - de >= ibs_hold)
                elif mech == "STREAK":
                    ex = (dc[d] > dc[d - 1]) or (d - de >= streak_hold)
                else:  # GAPDN: gap day = de - 1
                    ex = (dc[d] > dh[de - 1]) or (d - de >= gap_hold)
                if d >= de and ex and (d + 1) not in seams:
                    entry_px = float(do[de]); exit_px = float(do[d + 1])
                    pnl = chain(de, d + 1, entry_px)
                    # always keep the full log: the equity curve (and so the drawdown)
                    # must be built in EXIT-time order across the four legs, never in
                    # per-mechanism order.
                    trade_log.append((int(open_bar[de]), int(open_bar[d + 1]), float(pnl), 1,
                                      entry_px, exit_px))
                    pos = 0
            d += 1
    if not trade_log:
        return None
    trade_log.sort(key=lambda t: (t[1], t[0]))          # realization (exit) order
    pnls = np.array([t[2] for t in trade_log], float)
    wins = pnls[pnls > 0]; losses = pnls[pnls < 0]
    gw = float(wins.sum()); gl = float(-losses.sum())
    cum = np.cumsum(pnls); peak = np.maximum.accumulate(cum)
    out = {
        "total_pnl": float(pnls.sum()), "num_trades": int(len(pnls)),
        "win_rate": float(100.0 * len(wins) / len(pnls)),
        "profit_factor": (gw / gl) if gl > 1e-9 else (float("inf") if gw > 0 else 0.0),
        "max_drawdown": float((cum - peak).min()),
        "avg_pnl": float(pnls.mean()), "wins": int(len(wins)), "losses": int(len(losses)),
    }
    if return_trades:
        out["trades"] = trade_log
    return out
