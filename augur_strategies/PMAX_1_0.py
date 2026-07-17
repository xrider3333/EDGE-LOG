"""
PMAX 1.0 — TV round-13 port #5: "PMax Explorer STRATEGY & SCREENER" by KivancOzbilgic.

Source: https://www.tradingview.com/script/nHGK4Qtp/
(Pine v4, 16.6K boosts). Ported verbatim for EDGE-LOG challenger round 13 (see
TV_SWEEP.md). MPL-2.0 attribution retained in the port notes; this file is a
re-implementation, not a copy of the Pine text.

SCOPE — STRATEGY half only: this file ports the moving-average-trailed PMax
stop-and-reverse system and its two strategy.entry calls. The published script also
carries a SCREENER half (t1..t20 symbol inputs -- EURUSD, XAUUSD, AMZN, TSLA, BTCUSDT,
... down to SISE -- each re-running Pmax() via 20 separate security() calls, feeding a
single text label that lists confirmed/potential reversals and uptrend/downtrend
membership across all 20 tickers). That half is pure chart display (label text only,
zero strategy.entry/alertcondition wiring of its own) and is OMITTED entirely from
this port, as instructed. Also omitted as plot/label-only, zero effect on strategy
logic: showsupport, showsignalsk, showsignalsc, highlighting, the ohlc4 mPlot circles,
and (as part of the screener) showscr/posX_scr/posY_scr/colinput. Note in particular
that showsignalsc gates a SECOND, unrelated signal pair -- buySignalc/sellSignallc =
crossover/crossunder of raw `src` (not MAvg) against PMax -- used only for an optional
plotshape label; the strategy never trades on it. Only buySignalk/sellSignallk (the
MAvg/PMax cross) drive strategy.entry.

Family kinship: PMax is structurally "SuperTrend applied to a moving average instead
of to price" -- the same recursive ratchet-and-flip construction as SUPERTREND_3_0.py.
The two are siblings, NOT the same recursion with different inputs, though: Pine's own
Pmax_Func compares MAvg > longStopPrev / MAvg < shortStopPrev throughout (band ratchet
AND direction flip both keyed off MAvg), whereas SUPERTREND_3_0's construction ratchets
bands off hl2 but flip-tests against actual `close`. Swapping "close" for "MAvg"
everywhere is the whole difference. See the ma_type=SMA/ma_length=1 cross-check in the
smoke test below for a from-scratch verification of this loop.

Published rules (defaults):
  src = hl2 = (high+low)/2 (Pine "Source" input; fixed here -- see below).
  ATR period 10 (Pine "Periods"), multiplier 3.0 (Pine "Multiplier"). changeATR
  (published default true): true -> atr = Pine atr(10) = Wilder RMA of true range;
  false -> atr = SMA(true range, 10) (identical TR/ATR construction to SUPERTREND_3_0).
  MAvg = getMA(src, length) -- a moving average selectable among 8 types (Pine "mav"
  input, published default "EMA"; length default 10, Pine "length" input, minval 1):
    SMA   -- plain rolling mean.
    EMA   -- Pine ema(): alpha = 2/(length+1) via pandas .ewm(span=length,
             adjust=False) (bar-0 seeded at the raw value, not alpha-weighted; this is
             also how Pine's own ema() seeds -- na(sum[1]) -> sum := x).
    WMA   -- linearly weighted rolling mean, weights 1..length (weight `length`, the
             max, on the most recent bar; weight 1 on the oldest bar in the window).
    TMA   -- triangular MA: sma(sma(src, ceil(length/2)), floor(length/2)+1).
    VAR   -- Kivanc's own "VIDYA"-style adaptive average (Var_Func in the Pine): a
             Chande CMO built from vud1/vdd1 per-bar up/down moves summed over a FIXED
             9-bar window (Pine hardcodes `sum(vud1,9)` -- NOT scaled by `length`, an
             odd quirk of the original script, kept verbatim). valpha = 2/(length+1);
             vCMO = nz((vUD-vDD)/(vUD+vDD)); VAR[t] = valpha*|vCMO[t]|*src[t] +
             (1-valpha*|vCMO[t]|)*VAR[t-1]. The smoothing constant is itself
             time-varying -- genuinely sequential, implemented as a bar-by-bar loop.
    WWMA  -- Wilder-style fixed-alpha recursive average: alpha=1/length,
             WWMA[t] = alpha*src[t] + (1-alpha)*WWMA[t-1] (nz(WWMA[-1])->0 on bar 0,
             which differs from a plain ewm seed -- implemented as an explicit loop to
             match that bar-0 convention exactly rather than approximate it).
    ZLEMA -- zero-lag EMA: lag = floor(length/2); ema(src + (src - src[lag]), length).
    TSF   -- "Time Series Forecast": linreg(src,length,0) + slope, where slope =
             linreg(src,length,0) - linreg(src,length,1) (both linreg calls read the
             SAME length-bar OLS fit ending at the current bar; offset merely walks
             back along that one fitted line). Vectorized via closed-form rolling OLS
             sums (Sx/Sxx are fixed constants for a fixed window size; Sxy is built
             from (length-1) shifted-cumsum differences) -- no per-bar polyfit/lstsq
             call, no Python-level loop.
  PMax stop-and-reverse (Pine Pmax_Func, sequential -- longStop/shortStop each ratchet
  against their OWN previous already-ratcheted value, and the direction flip test reads
  that same previous-bar ratcheted stop; not vectorizable):
    longStop_raw[t]  = MAvg[t] - mult*atr[t]
    longStop[t]      = MAvg[t] > longStop[t-1] ? max(longStop_raw[t], longStop[t-1])
                                                : longStop_raw[t]
    shortStop_raw[t] = MAvg[t] + mult*atr[t]
    shortStop[t]     = MAvg[t] < shortStop[t-1] ? min(shortStop_raw[t], shortStop[t-1])
                                                 : shortStop_raw[t]
    dir[t] = dir[t-1]; dir==-1 and MAvg[t] > shortStop[t-1] -> dir=1;
                        dir==1  and MAvg[t] < longStop[t-1]  -> dir=-1  (init dir=+1;
    bar-0 "previous" stop = bar-0's own raw value, Pine's nz(x[1], x) convention).
    PMax[t] = dir[t]==1 ? longStop[t] : shortStop[t].
  buySignalk = crossover(MAvg, PMax); sellSignallk = crossunder(MAvg, PMax) -- by
  construction these fire exactly on a dir flip (-1->+1 / +1->-1); implemented here via
  the dir-flip array directly (cheaper, unambiguous, matches SUPERTREND_3_0's identical
  trend[]-flip signal pattern) rather than re-deriving crossover from the MAvg/PMax
  float series. strategy.entry("Long"/"Short", ..., when=Timerange()) on each signal,
  pyramiding 0, default order fill (process_orders_on_close=false) -> a plain ALWAYS-IN
  stop-and-reverse system, market orders filling at the NEXT bar's open, no price
  level, no stop-loss, no target. The script's own From/To date-window inputs
  (FromDay/FromMonth/.../ToYear, Timerange()) are just a Pine strategy-tester range
  control; ignored here -- EDGE-LOG controls the data window upstream, not the
  strategy.

Port semantics (house-honest, TV-parity):
  - Signals evaluate using bar-t indicator values (MAvg/PMax computed through bar t's
    close); a fill is armed at bar t's close and resolves as a plain market order at
    bar t+1's open (or dies unfilled if bar t+1 falls on a blocked roll-seam-eve day --
    it never rests longer than one bar; there is no price condition to wait on, unlike
    BBRSI_1_0's band-level stop orders).
  - Position is NET +/-1 contract; an opposite signal books the old trade and opens the
    new one at the same fill (Pine strategy.entry reversal, pyramiding 0).
  - direction="long"/"short" (house round-13 convention, same as BBRSI_1_0 /
    SUPERTREND_3_0): the suppressed side's flip becomes a plain market EXIT at the next
    open instead of a new position. "both" (default) = the published always-in system.
  - Multi-day holds are intrinsic; positions are FORCE-FLATTENED at the close of the
    day before each detected NOADJ quarterly roll seam and no fill may occur on that
    day (same guard + calibration as TTIBS_1_0.detect_roll_seams / BBRSI_1_0 /
    SUPERTREND_3_0 -- detect_roll_seams below is verbatim from BBRSI_1_0). A trade
    still open when the loaded data ends is DROPPED, never truncated (lockbox-honest).
  - PnL = points only, costs applied downstream by the engine (0.533 pts/RT NQ,
    0.363 ES), same as every library strategy.

Needs day_id AND index (roll-seam calendar + session boundaries); returns None without.
"""
import math
import numpy as np
import pandas as pd

STRATEGY_NAME = 'PMAX 1.0 · TV#5 Profit Maximizer MA-trail flip (KivancOzbilgic)'
DESCRIPTION = ("Round-13 verbatim port of TradingView's PMax Explorer STRATEGY "
               "(KivancOzbilgic, 16.6K boosts): SuperTrend-style ratchet applied to a "
               "selectable moving average of hl2 (8 MA types) instead of raw price, "
               "stop-and-reverse, no stops/targets. Market fills at next open (TV "
               "parity), roll-seam guarded, multi-day holds. Screener half (20-ticker "
               "security() display table) omitted -- strategy logic only.")

_AUGUR_MARKET = {"instrument": "NQ", "timeframe": "5m"}
# Round-13 challenger family (TV top-boosts sweep) — not a fork of any house family.

DEFAULT_PARAMS = {
    "atr_period": {
        "default": 10, "min": 3, "max": 50, "step": 1, "type": "int",
        "label": "ATR period",
        "tooltip": "Published default 10 (Pine 'Periods' input).",
    },
    "mult": {
        "default": 3.0, "min": 0.5, "max": 8.0, "step": 0.1, "type": "float",
        "label": "ATR multiplier",
        "tooltip": "Published default 3.0 (Pine 'Multiplier' input).",
    },
    "ma_type": {
        "default": "EMA", "type": "str",
        "options": ["SMA", "EMA", "WMA", "TMA", "VAR", "WWMA", "ZLEMA", "TSF"],
        "label": "Moving average type (Pine 'mav')",
        "tooltip": "Published default EMA. PMax runs the SuperTrend ratchet against "
                   "this moving average of hl2 instead of raw price -- all 8 author "
                   "options ported (see module docstring for each type's "
                   "construction). VAR = Kivanc's own VIDYA-style adaptive average.",
    },
    "ma_length": {
        "default": 10, "min": 1, "max": 60, "step": 1, "type": "int",
        "label": "Moving average length (Pine 'length')",
        "tooltip": "Published default 10.",
    },
    "change_atr": {
        "default": True, "type": "bool",
        "label": "Wilder RMA ATR (vs SMA of true range)",
        "tooltip": "Published default True: atr = Pine atr() = Wilder RMA(TR, period). "
                   "False = SMA(TR, period) -- the script's own 'changeATR' switch.",
    },
    "direction": {
        "default": "both", "type": "str",
        "options": ["both", "long", "short"],
        "label": "Trade direction",
        "tooltip": "both = published stop-and-reverse (always in the market once a "
                   "first position is entered). long/short = house round-13 "
                   "convention: the suppressed side's flip becomes a plain market "
                   "exit at the next open instead of a new position (same convention "
                   "as BBRSI_1_0 / SUPERTREND_3_0).",
    },
}

PARAM_GRID_PRESETS = {
    "Short  (published defaults)": {
        "atr_period": [10], "mult": [3.0], "ma_type": ["EMA"], "ma_length": [10],
        "change_atr": [True], "direction": ["both"],
    },
    # Pre-registered round-13 refinement grid (author knobs only; TV_SWEEP.md 13.5):
    # 3 ma_type x 2 ma_length x 2 mult x 2 direction = 24 cells.
    "Medium (author-knob grid)": {
        "atr_period": [10], "change_atr": [True],
        "ma_type": ["EMA", "VAR", "SMA"], "ma_length": [10, 20],
        "mult": [2.0, 3.0], "direction": ["both", "long"],
    },
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
    d0 = pd.Timestamp(year=year, month=month, day=1)
    offset = (weekday - d0.weekday()) % 7
    first = d0 + pd.Timedelta(days=offset)
    return first + pd.Timedelta(weeks=2)


def detect_roll_seams(day_open, day_close, day_ts, ratio_th=2.5, abs_th=15.0,
                      base_win=60, pre_days=12, post_days=2):
    """Identical method + calibration to TTIBS_1_0.detect_roll_seams (see that
    docstring): calendar-scoped local-outlier search around each quarter's 3rd
    Wednesday; returns daily indices s where close[s-1]->open[s] is a roll seam."""
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


# ── ATR (identical TR/atr()/SMA(tr) duality to SUPERTREND_3_0) ────────────────────
def _true_range(h, l, c):
    n = len(c)
    tr = np.empty(n, float)
    tr[0] = h[0] - l[0]
    tr[1:] = np.maximum(h[1:] - l[1:],
                         np.maximum(np.abs(h[1:] - c[:-1]), np.abs(l[1:] - c[:-1])))
    return tr


def _atr(h, l, c, period, change_atr):
    tr = _true_range(h, l, c)
    if change_atr:
        # Pine atr(Periods) = rma(tr, Periods); ewm(alpha=1/len, adjust=False)
        # converges to Pine's recursive rma (same house convention as
        # BBRSI_1_0._wilder_rsi / SUPERTREND_3_0 -- signals are warm-up masked).
        return pd.Series(tr).ewm(alpha=1.0 / period, adjust=False).mean().to_numpy()
    return pd.Series(tr).rolling(period).mean().to_numpy()      # atr2 = sma(tr, Periods)


# ── getMA: the 8 Pine "mav" options (Var_Func / Wwma_Func / Zlema_Func / Tsf_Func) ──
def _ma_sma(src, length):
    return pd.Series(src, dtype=float).rolling(int(length)).mean().to_numpy()


def _ma_ema(src, length):
    return pd.Series(src, dtype=float).ewm(span=int(length), adjust=False).mean().to_numpy()


def _ma_wma(src, length):
    y = np.asarray(src, dtype=float)
    n = len(y); L = int(length)
    w = np.arange(1, L + 1, dtype=float)               # weight 1..L, L on newest bar
    out = np.full(n, np.nan)
    if n >= L:
        # correlate('valid')[k] = sum_i y[k+i]*w[i]; i=0 is the oldest bar in the
        # window (weight 1), i=L-1 the newest/current bar (weight L) -- Pine wma().
        out[L - 1:] = np.correlate(y, w, mode="valid") / w.sum()
    return out


def _ma_tma(src, length):
    L = int(length)
    L1 = math.ceil(L / 2.0)
    L2 = math.floor(L / 2.0) + 1
    s1 = pd.Series(src, dtype=float).rolling(L1).mean()
    return s1.rolling(L2).mean().to_numpy()


def _ma_var(src, length):
    """Kivanc's VIDYA-style adaptive average (Pine Var_Func). Genuinely recursive
    (the smoothing constant valpha*|vCMO[t]| is itself time-varying) -- sequential
    loop by necessity, matching the module docstring."""
    y = np.asarray(src, dtype=float)
    n = len(y)
    length = int(length)
    valpha = 2.0 / (length + 1)
    delta = np.empty(n); delta[0] = 0.0
    delta[1:] = y[1:] - y[:-1]
    vud1 = np.where(delta > 0, delta, 0.0)
    vdd1 = np.where(delta < 0, -delta, 0.0)
    # Pine `sum(x, 9)`: fixed 9-bar rolling sum -- NOT scaled by `length` (verbatim
    # quirk of the original script).
    vUD = pd.Series(vud1).rolling(9, min_periods=1).sum().to_numpy()
    vDD = pd.Series(vdd1).rolling(9, min_periods=1).sum().to_numpy()
    denom = vUD + vDD
    with np.errstate(invalid="ignore", divide="ignore"):
        vcmo = np.where(denom != 0.0, (vUD - vDD) / denom, 0.0)   # nz(0/0) -> 0
    out = np.empty(n)
    prev = 0.0
    for t in range(n):
        a = valpha * abs(vcmo[t])
        cur = a * y[t] + (1.0 - a) * prev
        out[t] = cur
        prev = cur
    return out


def _ma_wwma(src, length):
    """Wilder-style fixed-alpha recursive average (Pine Wwma_Func): alpha=1/length,
    nz(WWMA[-1])->0 on bar 0. Implemented as an explicit loop to match that bar-0
    zero-seed exactly (a plain ewm seed would instead seed bar 0 at the raw value)."""
    y = np.asarray(src, dtype=float)
    n = len(y)
    alpha = 1.0 / float(length)
    out = np.empty(n)
    prev = 0.0
    for t in range(n):
        cur = alpha * y[t] + (1.0 - alpha) * prev
        out[t] = cur
        prev = cur
    return out


def _ma_zlema(src, length):
    y = pd.Series(src, dtype=float)
    length = int(length)
    lag = length // 2                     # Pine: even L -> L/2; odd L -> (L-1)/2 (same)
    zx = 2.0 * y - y.shift(lag)           # src + (src - src[lag])
    return zx.ewm(span=length, adjust=False).mean().to_numpy()


def _ma_tsf(src, length):
    """Time Series Forecast (Pine Tsf_Func): linreg(src,L,0) + slope, slope =
    linreg(src,L,0) - linreg(src,L,1) -- both linreg calls read the SAME length-bar
    OLS fit ending at the current bar. Closed-form rolling OLS: for a fixed window
    size L, x = 0..L-1 (0 = oldest bar in the window), Sx and Sxx are CONSTANTS; Sxy
    is built from (L-1) shifted-cumsum differences (sum_{m=1}^{L-1} (C[t]-C[t-m]),
    C = cumsum(src)) -- no per-bar polyfit/lstsq call, no Python-level loop."""
    y = pd.Series(src, dtype=float)
    n = len(y)
    L = int(length)
    if L < 2:
        return y.to_numpy()               # degenerate single-point window: no slope
    Sy = y.rolling(L).sum()
    C = y.cumsum()
    Sxy = pd.Series(0.0, index=y.index)
    for m in range(1, L):
        Sxy = Sxy + (C - C.shift(m))
    Sx = L * (L - 1) / 2.0
    Sxx = (L - 1) * L * (2 * L - 1) / 6.0
    denom = L * Sxx - Sx * Sx
    slope = (L * Sxy - Sx * Sy) / denom
    endpoint = Sy / L + slope * ((L - 1) - Sx / L)      # fitted value at x = L-1 (now)
    return (endpoint + slope).to_numpy()


_MA_FUNCS = {
    "SMA": _ma_sma, "EMA": _ma_ema, "WMA": _ma_wma, "TMA": _ma_tma,
    "VAR": _ma_var, "WWMA": _ma_wwma, "ZLEMA": _ma_zlema, "TSF": _ma_tsf,
}


def _get_ma(src, length, ma_type):
    fn = _MA_FUNCS.get(ma_type)
    if fn is None:
        raise ValueError("PMAX_1_0: unknown ma_type %r" % (ma_type,))
    return fn(src, length)


def _pmax_core(mavg, atr, mult):
    """Sequential PMax ratchet + direction flip -- Pine's Pmax_Func verbatim (see
    module docstring): longStop/shortStop each ratchet against their OWN previous
    (already-ratcheted) value conditioned on MAvg itself (never price), and the
    direction flip test reads that same previous-bar ratcheted stop (Pine's
    nz(longStop[1], longStop), nz(shortStop[1], shortStop)). Mutually recursive --
    not vectorizable. dir initialized +1; bar-0 "previous" stop = bar-0's own raw
    value (Pine's nz(x[1], x) bar-0 convention). Scalars cast to plain Python float
    inside the loop so NaN comparisons (possible during warm-up) behave as ordinary
    Python `nan > x` -> False, never raising -- the caller's `warm` cutoff means no
    such NaN ever reaches a real signal anyway. Returns (pmax[], direction[] int8).
    """
    n = len(mavg)
    pmax = np.empty(n)
    direction = np.empty(n, dtype=np.int8)
    long_prev = None
    short_prev = None
    dir_prev = 1
    for t in range(n):
        m = float(mavg[t])
        rng = float(mult) * float(atr[t])
        raw_long = m - rng
        raw_short = m + rng
        long1 = raw_long if long_prev is None else long_prev
        short1 = raw_short if short_prev is None else short_prev

        cur_long = max(raw_long, long1) if m > long1 else raw_long
        cur_short = min(raw_short, short1) if m < short1 else raw_short

        d = dir_prev
        if d == -1 and m > short1:
            d = 1
        elif d == 1 and m < long1:
            d = -1

        pmax[t] = cur_long if d == 1 else cur_short
        direction[t] = d
        long_prev, short_prev, dir_prev = cur_long, cur_short, d
    return pmax, direction


def run_backtest(
    opens, highs, lows, closes,
    volumes=None, day_id=None, index=None,
    atr_period: int = 10, mult: float = 3.0,
    ma_type: str = "EMA", ma_length: int = 10, change_atr: bool = True,
    direction: str = "both",
    return_trades: bool = False, _stop_event=None, _pause_event=None,
    **_ignore,
):
    o = np.asarray(opens, float); h = np.asarray(highs, float)
    l = np.asarray(lows, float);  c = np.asarray(closes, float)
    n = len(c)
    if n < 300:
        return None
    did = np.asarray(day_id) if (day_id is not None and len(day_id) == n) else None
    if did is None or index is None:
        return None                    # needs real dates (roll seams / session ends)

    atr_period = int(atr_period); mult = float(mult)
    ma_length = int(ma_length); change_atr = bool(change_atr)
    ma_type = str(ma_type)

    # ── indicators (Pine parity) ──────────────────────────────────────────────
    src = (h + l) / 2.0                              # hl2
    atr = _atr(h, l, c, atr_period, change_atr)
    mavg = _get_ma(src, ma_length, ma_type)
    pmax, trend = _pmax_core(mavg, atr, mult)

    buy_sig = np.zeros(n, bool); sell_sig = np.zeros(n, bool)
    buy_sig[1:] = (trend[1:] == 1) & (trend[:-1] == -1)     # crossover(MAvg, PMax)
    sell_sig[1:] = (trend[1:] == -1) & (trend[:-1] == 1)    # crossunder(MAvg, PMax)

    warm = max(10 * ma_length, 60)
    buy_sig[:warm] = False
    sell_sig[:warm] = False

    # ── session / roll-seam scaffolding (identical to BBRSI_1_0 / SUPERTREND_3_0) ──
    bounds = _session_bounds(did, n)
    idx = pd.DatetimeIndex(index)
    day_open = np.array([o[a] for a, b in bounds])
    day_close = np.array([c[b - 1] for a, b in bounds])
    day_ts = [idx[a] for a, b in bounds]
    seam_days = set(detect_roll_seams(day_open, day_close, day_ts))
    force_exit_days = {sd - 1 for sd in seam_days if sd - 1 >= 0}   # daily index
    # map: bar -> daily index; last bar of each day
    day_of_bar = np.empty(n, int)
    last_bar_of_day = {}
    for di, (a, b) in enumerate(bounds):
        day_of_bar[a:b] = di
        last_bar_of_day[di] = b - 1
    blocked_days = set(force_exit_days)                              # no fills on seam eve

    allow_long = direction in ("both", "long")
    allow_short = direction in ("both", "short")

    # ── event loop (plain market fills, next bar's open; stop-and-reverse) ───
    pos = 0
    entry_px = 0.0
    entry_bar = -1
    pending = None            # +1 long entry / -1 short entry / 0 market exit / None
    pnl_list, trade_log = [], []

    def _book(exit_bar_i, exit_price, side, ep, eb):
        pnl = (exit_price - ep) if side > 0 else (ep - exit_price)
        pnl_list.append(pnl)
        if return_trades:
            trade_log.append((int(eb), int(exit_bar_i), float(pnl), int(side),
                              float(ep), float(exit_price)))

    for u in range(warm, n):
        if _stop_event is not None and _stop_event.is_set():
            break
        di = day_of_bar[u]

        # 1) fill any pending order at u's open (order was armed at u-1's close). PMax
        #    orders are plain next-bar market orders -- always resolved this bar, no
        #    resting/level logic (unlike BBRSI_1_0's stop-at-band-level orders).
        if pending is not None:
            if di not in blocked_days:
                fill = o[u]
                side = pending
                if side == 0:                          # market exit (long/short-only mode)
                    if pos != 0:
                        _book(u, fill, pos, entry_px, entry_bar)
                        pos = 0
                elif pos == 0:
                    pos = side; entry_px = fill; entry_bar = u
                elif pos != side:                      # reversal: book old, open new
                    _book(u, fill, pos, entry_px, entry_bar)
                    pos = side; entry_px = fill; entry_bar = u
            pending = None                              # resolved: filled, or dead on blocked day

        # 2) signal evaluation at u's close -> arm next bar's order
        bs, ss = buy_sig[u], sell_sig[u]
        new_pending = None
        if bs and allow_long and pos <= 0:
            new_pending = 1
        elif ss and allow_short and pos >= 0:
            new_pending = -1
        elif bs and not allow_long and pos < 0:
            new_pending = 0                            # short-only mode: buy flip = exit
        elif ss and not allow_short and pos > 0:
            new_pending = 0                            # long-only mode: sell flip = exit
        pending = new_pending

        # 3) roll-seam eve: force flat at this day's final bar close, kill pending
        if di in force_exit_days and u == last_bar_of_day[di]:
            if pos != 0:
                _book(u, c[u], pos, entry_px, entry_bar)
                pos = 0
            pending = None

    # end of data: open trade DROPPED (never truncated)

    if not pnl_list:
        return None
    pnls = np.array(pnl_list, float)
    wins = pnls[pnls > 0]; losses = pnls[pnls < 0]
    gw = float(wins.sum()); gl = float(-losses.sum())
    cum = np.cumsum(pnls); peak = np.maximum.accumulate(cum)
    out = {
        "total_pnl": float(pnls.sum()), "num_trades": int(len(pnls)),
        "win_rate": float(100.0 * len(wins) / len(pnls)) if len(pnls) else 0.0,
        "profit_factor": (gw / gl) if gl > 1e-9 else (float("inf") if gw > 0 else 0.0),
        "max_drawdown": float((cum - peak).min()) if len(cum) else 0.0,
        "avg_pnl": float(pnls.mean()), "wins": int(len(wins)), "losses": int(len(losses)),
    }
    if return_trades:
        out["trades"] = trade_log
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Smoke test — tiny window, sane-output check. Run: python augur_strategies/PMAX_1_0.py
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import os, sys

    ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    MASTER = os.path.join(ROOT, "augur_uploads", "NOADJ_NQ_5m_RTH.csv")
    MULT, FEE = 20.0, 0.533
    if not os.path.exists(MASTER):
        print("NQ master not found at", MASTER); sys.exit(1)

    df = pd.read_csv(MASTER)
    dt = pd.to_datetime(df["time"], unit="s", utc=True).dt.tz_convert("US/Eastern")
    df.index = dt
    df = df[(df.index >= pd.Timestamp("2015-01-01", tz="US/Eastern")) &
            (df.index < pd.Timestamp("2018-01-01", tz="US/Eastern"))].sort_index()
    day_id = pd.factorize(pd.Series(df.index).dt.date)[0].astype("int64")

    print("PMAX 1.0 smoke test — NQ 5m RTH, 2015-2017 (%d bars, %d sessions)"
          % (len(df), len(set(day_id))))
    print("%-52s %7s %5s %6s %13s %11s" % ("config", "trades", "WR%", "PF", "net $", "maxDD$ (gross)"))
    print("-" * 100)

    configs = [
        ("published: EMA/10, ATR 10/3.0, both", dict()),
        ("VAR/10, ATR 10/3.0, both (Kivanc VIDYA)", dict(ma_type="VAR")),
        ("published EMA/10, long-only", dict(direction="long")),
        ("EMA/20, mult 2.0, both (grid corner)", dict(ma_length=20, mult=2.0)),
    ]
    results = {}
    for label, kw in configs:
        r = run_backtest(df["open"].values, df["high"].values, df["low"].values,
                         df["close"].values, day_id=day_id, index=df.index,
                         return_trades=True, **kw)
        results[label] = r
        if r is None:
            print("%-52s  NO TRADES" % label); continue
        net_usd = (r["total_pnl"] - FEE * r["num_trades"]) * MULT
        print("%-52s %7d %4.0f%% %6.2f %13s %11s" % (
            label, r["num_trades"], r["win_rate"], min(r["profit_factor"], 99),
            "${:+,.0f}".format(net_usd), "${:,.0f}".format(r["max_drawdown"] * MULT)))

    print("\nPoints-based engine output; house cost_pts/mult applied by the caller "
          "(this table folds fee into net only). Sane-output check, not a result.")

    # ── correctness cross-check ────────────────────────────────────────────────
    # ma_type=SMA, ma_length=1 -> MAvg == hl2 exactly (rolling mean, window 1), so
    # PMax reduces to a classic SuperTrend applied directly to hl2 -- using hl2
    # uniformly for BOTH the ratchet condition and the flip test, matching Pine's
    # Pmax_Func (this is NOT the same as SUPERTREND_3_0's construction, which
    # flip-tests against actual close -- see module docstring). Checked against a
    # fresh, independently written implementation of that recursion (not calling
    # _pmax_core) to catch loop/indexing bugs the production path might share with
    # itself.
    print("\nCross-check: ma_type=SMA, ma_length=1 (MAvg==hl2) vs a from-scratch "
          "classic-SuperTrend-on-hl2 recursion, first 500 bars:")

    h_ = df["high"].values.astype(float)[:2000]
    l_ = df["low"].values.astype(float)[:2000]
    c_ = df["close"].values.astype(float)[:2000]
    hl2_ = (h_ + l_) / 2.0
    atr_ = _atr(h_, l_, c_, 10, True)

    mavg_check = _get_ma(hl2_, 1, "SMA")
    assert np.allclose(mavg_check, hl2_, atol=1e-9), "SMA(hl2,1) != hl2"
    pmax_prod, _ = _pmax_core(mavg_check, atr_, 3.0)

    def _fresh_classic_supertrend(src, atr_arr, mult):
        # Independent re-derivation of Pine's Pmax_Func with MAvg replaced by `src`
        # directly, uniformly, in both the ratchet condition and the flip test --
        # written from scratch (no call into _pmax_core) so this is a real check.
        n_ = len(src)
        out = np.empty(n_)
        lp = sp = None
        d = 1
        for i in range(n_):
            s = float(src[i]); r = float(mult) * float(atr_arr[i])
            up_raw = s - r
            dn_raw = s + r
            up_prev = up_raw if lp is None else lp
            dn_prev = dn_raw if sp is None else sp
            up_t = max(up_raw, up_prev) if s > up_prev else up_raw
            dn_t = min(dn_raw, dn_prev) if s < dn_prev else dn_raw
            if d == -1 and s > dn_prev:
                d = 1
            elif d == 1 and s < up_prev:
                d = -1
            out[i] = up_t if d == 1 else dn_t
            lp, sp = up_t, dn_t
        return out

    pmax_check = _fresh_classic_supertrend(hl2_, atr_, 3.0)
    diff = np.abs(pmax_prod[:500] - pmax_check[:500])
    ok = bool(np.all(diff < 1e-6))
    print("  MAvg==hl2 (first 2000 bars):            PASS")
    print("  max abs diff, PMax vs reference (500 bars): %.3e  ->  %s" %
          (float(diff.max()), "PASS" if ok else "FAIL"))
    assert ok, "PMax(SMA,1) does not match the from-scratch classic-SuperTrend-on-hl2 reference"

    # ── supplementary robustness pass: all 8 MA types must produce finite output ──
    all_ok = True
    for mt in ["SMA", "EMA", "WMA", "TMA", "VAR", "WWMA", "ZLEMA", "TSF"]:
        rr = run_backtest(df["open"].values, df["high"].values, df["low"].values,
                          df["close"].values, day_id=day_id, index=df.index,
                          ma_type=mt)
        mv = _get_ma(src=(df["high"].values + df["low"].values) / 2.0,
                     length=10, ma_type=mt)
        finite_tail = np.all(np.isfinite(mv[200:]))
        if not finite_tail:
            all_ok = False
        print("  ma_type=%-5s getMA finite after warm-up: %-5s  run_backtest: %s"
              % (mt, finite_tail, "None (no trades)" if rr is None else "%d trades" % rr["num_trades"]))
    print("  all 8 MA types finite + run cleanly: %s" % ("PASS" if all_ok else "FAIL"))
    assert all_ok, "one or more MA types produced non-finite output past warm-up"
