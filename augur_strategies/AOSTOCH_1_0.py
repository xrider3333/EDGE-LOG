"""
AOSTOCH 1.0 — TV round-13 port #7: "Buy&Sell Strategy depends on AO+Stoch+RSI+ATR (by
SerdarYILMAZ)".

Source: https://www.tradingview.com/script/RpYoQCVJ-Buy-Sell-Strategy-depends-on-AO-Stoch-RSI-ATR-by-SerdarYILMAZ/
(Pine v4, 13.5K boosts). Ported verbatim for EDGE-LOG challenger round 13 (see
TV_SWEEP.md). Original license/House Rules apply; this file is a re-implementation, not
a copy of the Pine text. The author's own in-script comment flags this as a training
exercise, not a trading recommendation ("this strategy is just for training ... don't
make buy or sell decisions with this strategy") — noted here because it is exactly the
kind of script that reaches top-10 boosts on volume of people studying the code, not on
any claimed edge; it is tested anyway because the boost count put it in this sweep.

Published rules (defaults):
  Awesome Oscillator: AO = (SMA(hl2,5) - SMA(hl2,34)) x 1000 (the x1000 is cosmetic; it
  does not change the rising/falling comparison the entry conditions use).
  Stochastic: raw = 100 x (close - lowest(low,14)) / (highest(high,14) - lowest(low,14));
  k = SMA(raw, 3). (Pine also computes d = SMA(k,3) but no condition ever reads d --
  dropped here, nothing lost.)
  RSI(10), Wilder-smoothed, on close.
  ATR(14), Wilder RMA of true range.
  LONG  signal: k < 20  AND  rsi < 30  AND  AO rising  (AO[t] > AO[t-1]).
  SHORT signal: k > 80  AND  rsi > 70  AND  AO falling (AO[t] < AO[t-1]).
  On a signal at bar t: strategy.entry (market) -- fills at bar t+1's open, TV's default
  order-fill model. In the SAME script execution as the signal, strategy.exit sets a
  stop and a limit computed from bar t's OWN values: long stop = low[t] - ATR[t], long
  limit = close[t] + ATR[t] (short mirrors: stop = high[t] + ATR[t], limit = close[t] -
  ATR[t]) -- both FROZEN at that instant, never recalculated or trailed for the life of
  the trade. No time-stop, no session flatten anywhere in the Pine: every trade's only
  exits are its own stop, its own limit, or a reversal fill.

Port semantics (house-honest, TV-parity):
  - Signals evaluate on bar t's CLOSE using bar-t indicator values only; the resulting
    market entry fills at bar t+1's open (unconditional -- it's a market order, not a
    resting stop, so it always fills, unlike BBRSI_1_0/MACD200_1_0's stop-entry orders).
  - Once filled, the position is managed intrabar EVERY bar starting with and including
    the fill bar itself (the position exists from that bar's open onward, so the rest of
    its range is fair game): STOP-FIRST pessimism if both the stop and the limit sit
    inside the same bar's range; a stop that the bar's OPEN already gapped through fills
    AT THAT OPEN, not at the stop price (ORB_3_1's gap-realism, copied); a limit fills at
    the limit level, or AT THE OPEN if the bar opened beyond it in the trade's favor (the
    same open-vs-level comparison as the stop, mirrored for a favorable gap). On a bar
    where the entry's own fill (at that bar's open) already sits beyond its frozen stop
    or limit -- a violent single-bar gap right after entry -- this degenerates to an
    immediate scratch / instant-target exit at that same open price: a rare, honest
    consequence of the frozen-level + gap-fill rules, not a special case.
  - Position is NET +/-1 contract, pyramiding 0. A signal while already positioned in
    that SAME direction is ignored outright -- no re-arm, the original bracket stays in
    force. An OPPOSITE signal reverses: the old trade books and the new one opens, both
    at the reversal bar's open, with a FRESH bracket frozen from the reversal's own
    signal bar (Pine strategy.entry reversal semantics, same as BBRSI_1_0/MACD200_1_0).
  - direction="long"/"short" suppresses one side's signal ENTIRELY -- unlike
    BBRSI_1_0/MACD200_1_0 (where the suppressed side becomes a plain market exit), here
    the suppressed side's signal is simply dropped: it cannot enter and it cannot exit
    either. This strategy already carries a real stop/target bracket on every open
    trade, so the bracket alone does the exiting; there is nothing useful for the other
    side's signal to do.
  - Multi-day holds are intrinsic (no flat-EOD anywhere in the Pine); positions are
    FORCE-FLATTENED at the close of the day before each detected NOADJ quarterly roll
    seam and no fill (entry, reversal, OR stop/limit) may occur on that day (same guard
    + calibration as TTIBS_1_0.detect_roll_seams); a position straddling that day simply
    rides, unresolved, into the mandatory close-out. A trade still open when the loaded
    data ends is DROPPED, never truncated (lockbox-honest).
  - PNL = points only, costs applied downstream by the engine (0.533 pts/RT NQ, 0.363
    ES), same as every library strategy.

Needs day_id AND index (roll-seam calendar + session boundaries); returns None without.
"""
import numpy as np
import pandas as pd

STRATEGY_NAME = 'AOSTOCH 1.0 · TV#7 AO+Stoch+RSI confluence w/ ATR bracket (SerdarYILMAZ)'
DESCRIPTION = ("Round-13 verbatim port of TradingView's AO+Stoch+RSI+ATR strategy: "
               "oversold/overbought confluence (Stoch k, RSI(10), Awesome Oscillator "
               "turning) triggers a market entry with a frozen ATR stop/limit bracket. "
               "Next-open fills (TV parity), stop-first pessimism + gap realism on the "
               "bracket, roll-seam guarded, multi-day holds. Author labels the original "
               "script educational; tested anyway because it hit 13.5K boosts.")

_AUGUR_MARKET = {"instrument": "NQ", "timeframe": "5m"}
# Round-13 challenger family (TV top-boosts sweep) — not a fork of any house family.

DEFAULT_PARAMS = {
    "ao_fast": {
        "default": 5, "min": 2, "max": 20, "step": 1, "type": "int",
        "label": "Awesome Oscillator fast SMA length",
        "tooltip": "Published default 5. AO = (SMA(hl2,fast) - SMA(hl2,slow)) x 1000 "
                   "(the x1000 is cosmetic; it does not affect the rising/falling "
                   "comparison the entry conditions actually use).",
    },
    "ao_slow": {
        "default": 34, "min": 10, "max": 80, "step": 1, "type": "int",
        "label": "Awesome Oscillator slow SMA length",
        "tooltip": "Published default 34.",
    },
    "stoch_len": {
        "default": 14, "min": 4, "max": 40, "step": 1, "type": "int",
        "label": "Stochastic %K lookback",
        "tooltip": "Published default 14 (the Pine 'K' input). Raw stoch = "
                   "100*(close-lowest(low,len))/(highest(high,len)-lowest(low,len)).",
    },
    "stoch_smooth": {
        "default": 3, "min": 1, "max": 10, "step": 1, "type": "int",
        "label": "Stochastic k smoothing (SMA)",
        "tooltip": "Published default 3 (the Pine 'D' input -- confusingly named; it "
                   "smooths the raw stoch into k, the line the conditions actually use). "
                   "The Pine also computes a further-smoothed 'd' line from its own "
                   "'smooth' input, but d is never read by LongCondition/ShortCondition "
                   "-- dropped here, nothing lost.",
    },
    "k_low": {
        "default": 20, "min": 5, "max": 40, "step": 1, "type": "int",
        "label": "Stoch oversold level (long trigger)",
        "tooltip": "Published default 20: long requires k < this.",
    },
    "k_high": {
        "default": 80, "min": 60, "max": 95, "step": 1, "type": "int",
        "label": "Stoch overbought level (short trigger)",
        "tooltip": "Published default 80: short requires k > this.",
    },
    "rsi_len": {
        "default": 10, "min": 4, "max": 30, "step": 1, "type": "int",
        "label": "RSI period",
        "tooltip": "Published default 10, Wilder-smoothed on close.",
    },
    "rsi_low": {
        "default": 30, "min": 10, "max": 45, "step": 1, "type": "int",
        "label": "RSI oversold level (long trigger)",
        "tooltip": "Published default 30: long requires rsi < this.",
    },
    "rsi_high": {
        "default": 70, "min": 55, "max": 90, "step": 1, "type": "int",
        "label": "RSI overbought level (short trigger)",
        "tooltip": "Published default 70: short requires rsi > this.",
    },
    "atr_len": {
        "default": 14, "min": 4, "max": 40, "step": 1, "type": "int",
        "label": "ATR period (Wilder RMA)",
        "tooltip": "Published default 14. Feeds the stop/limit bracket -- frozen at the "
                   "signal bar, never recalculated or trailed during the trade.",
    },
    "atr_stop_mult": {
        "default": 1.0, "min": 0.5, "max": 4.0, "step": 0.25, "type": "float",
        "label": "Stop distance (x ATR)",
        "tooltip": "Published Pine uses a bare ATR distance (mult=1.0): long stop = "
                   "low[t]-ATR, short stop = high[t]+ATR. Generalized to a multiplier "
                   "here for the author-knob grid.",
    },
    "atr_tp_mult": {
        "default": 1.0, "min": 0.5, "max": 5.0, "step": 0.25, "type": "float",
        "label": "Target distance (x ATR)",
        "tooltip": "Published Pine uses a bare ATR distance (mult=1.0): long limit = "
                   "close[t]+ATR, short limit = close[t]-ATR.",
    },
    "direction": {
        "default": "both", "type": "str",
        "options": ["both", "long", "short"],
        "label": "Trade direction",
        "tooltip": "both = published (long and short confluence + reversal). long/short "
                   "= the OTHER side's signal is fully ignored -- not converted into an "
                   "exit (unlike BBRSI_1_0/MACD200_1_0): this strategy already has a "
                   "real stop/target bracket, so the bracket alone does the exiting.",
    },
}

PARAM_GRID_PRESETS = {
    "Short  (published defaults)": {
        "ao_fast": [5], "ao_slow": [34], "stoch_len": [14], "stoch_smooth": [3],
        "k_low": [20], "k_high": [80], "rsi_len": [10], "rsi_low": [30], "rsi_high": [70],
        "atr_len": [14], "atr_stop_mult": [1.0], "atr_tp_mult": [1.0], "direction": ["both"],
    },
    # Pre-registered round-13 refinement grid (author knobs only; TV_SWEEP.md 13.7).
    # k_low/k_high must move together (a real oversold/overbought PAIR), so instead of
    # cross-producting two independent params (which would also try mismatched pairs
    # like 20/75), the grid uses a single k_band param -- run_backtest maps it back to
    # k_low/k_high internally (see the k_band handling at the top of run_backtest).
    "Medium (author-knob grid)": {
        "atr_stop_mult": [1.0, 2.0], "atr_tp_mult": [1.0, 2.0, 3.0],
        "k_band": ["20/80", "25/75"], "direction": ["both", "long"],
        "ao_fast": [5], "ao_slow": [34], "stoch_len": [14], "stoch_smooth": [3],
        "rsi_len": [10], "rsi_low": [30], "rsi_high": [70], "atr_len": [14],
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


def _wilder_rsi(close, length):
    """Pine rsi(): Wilder smoothing (rma). ewm(alpha=1/len, adjust=False) converges to
    Pine's recursive rma after warm-up; signals are masked during warm-up anyway."""
    s = pd.Series(close)
    delta = s.diff()
    up = delta.clip(lower=0.0)
    dn = (-delta).clip(lower=0.0)
    ru = up.ewm(alpha=1.0 / length, adjust=False).mean()
    rd = dn.ewm(alpha=1.0 / length, adjust=False).mean()
    rs = ru / rd.replace(0.0, np.nan)
    rsi = 100.0 - 100.0 / (1.0 + rs)
    rsi = rsi.where(rd > 1e-12, 100.0).where(ru > 1e-12, rsi)  # Pine edge conventions
    return rsi.to_numpy()


def run_backtest(
    opens, highs, lows, closes,
    volumes=None, day_id=None, index=None,
    ao_fast: int = 5, ao_slow: int = 34,
    stoch_len: int = 14, stoch_smooth: int = 3,
    k_low: int = 20, k_high: int = 80,
    rsi_len: int = 10, rsi_low: int = 30, rsi_high: int = 70,
    atr_len: int = 14, atr_stop_mult: float = 1.0, atr_tp_mult: float = 1.0,
    direction: str = "both",
    k_band: str = None,   # grid-only override, e.g. "25/75" -> k_low=25, k_high=75
    return_trades: bool = False, _stop_event=None, _pause_event=None,
    **_ignore,
):
    if k_band is not None:
        try:
            lo_s, hi_s = str(k_band).split("/")
            k_low = float(lo_s); k_high = float(hi_s)
        except Exception:
            pass  # malformed -> fall back to the explicit k_low/k_high args

    o = np.asarray(opens, float); h = np.asarray(highs, float)
    l = np.asarray(lows, float);  c = np.asarray(closes, float)
    n = len(c)
    if n < 300:
        return None
    did = np.asarray(day_id) if (day_id is not None and len(day_id) == n) else None
    if did is None or index is None:
        return None                    # needs real dates (roll seams / session ends)

    ao_fast = int(ao_fast); ao_slow = int(ao_slow)
    stoch_len = int(stoch_len); stoch_smooth = int(stoch_smooth)
    k_low = float(k_low); k_high = float(k_high)
    rsi_len = int(rsi_len); rsi_low = float(rsi_low); rsi_high = float(rsi_high)
    atr_len = int(atr_len)
    atr_stop_mult = float(atr_stop_mult); atr_tp_mult = float(atr_tp_mult)

    # ── indicators (Pine parity) ──────────────────────────────────────────────
    hl2 = (h + l) / 2.0
    s_hl2 = pd.Series(hl2)
    sma_fast = s_hl2.rolling(ao_fast).mean()
    sma_slow = s_hl2.rolling(ao_slow).mean()
    awesome = ((sma_fast - sma_slow) * 1000.0).to_numpy()

    sH = pd.Series(h); sL = pd.Series(l); sC = pd.Series(c)
    ll = sL.rolling(stoch_len).min()
    hh = sH.rolling(stoch_len).max()
    raw_stoch = 100.0 * (sC - ll) / (hh - ll).replace(0.0, np.nan)
    k_line = raw_stoch.rolling(stoch_smooth).mean().to_numpy()

    rsi_val = _wilder_rsi(c, rsi_len)

    tr = pd.concat([sH - sL, (sH - sC.shift(1)).abs(), (sL - sC.shift(1)).abs()],
                    axis=1).max(axis=1)
    atr_val = tr.ewm(alpha=1.0 / atr_len, adjust=False).mean().to_numpy()

    with np.errstate(invalid="ignore"):
        awesome_rising = np.zeros(n, bool); awesome_falling = np.zeros(n, bool)
        awesome_rising[1:] = awesome[1:] > awesome[:-1]
        awesome_falling[1:] = awesome[1:] < awesome[:-1]
        long_sig = (k_line < k_low) & (rsi_val < rsi_low) & awesome_rising
        short_sig = (k_line > k_high) & (rsi_val > rsi_high) & awesome_falling

    warm = max(120, 60)
    long_sig[:warm] = False
    short_sig[:warm] = False

    # ── session / roll-seam scaffolding (identical to BBRSI_1_0) ────────────────
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

    # ── event loop ────────────────────────────────────────────────────────────
    pos = 0
    entry_px = 0.0
    entry_bar = -1
    stop_px = 0.0
    limit_px = 0.0
    pending = None   # (side, frozen_stop_px, frozen_limit_px), armed at u-1's close,
                      # fills unconditionally (market order) at u's open
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
        blocked = di in blocked_days

        # 1) pending entry fill (armed at u-1's close) -> fills at u's open. Market
        #    order, so it always fills unless this bar's day is blocked (seam eve),
        #    in which case the fill is suppressed and the order is simply dropped
        #    (never carried to a later bar).
        if pending is not None:
            side, new_stop, new_limit = pending
            pending = None
            if not blocked:
                fill = o[u]
                if pos != 0 and pos != side:            # reversal: book the old trade
                    _book(u, fill, pos, entry_px, entry_bar)
                    pos = 0
                if pos == 0:
                    pos = side; entry_px = fill; entry_bar = u
                    stop_px = new_stop; limit_px = new_limit
                # pos == side already cannot happen here: a same-direction signal
                # never arms a pending while already positioned that way (step 3).

        # 2) intrabar bracket management for an open position -- INCLUDING the bar
        #    the entry itself just filled on (the position exists from that bar's
        #    open onward, so the rest of its range is fair game). STOP-FIRST
        #    pessimism when both levels sit inside the same bar; gap-through fills
        #    the stop at the bar's OPEN (ORB_3_1 realism); a favorable gap fills the
        #    limit at the OPEN too (better than the limit level). Suppressed on a
        #    blocked (seam-eve) day -- the position rides, unresolved, to the forced
        #    close-out in step 4.
        if pos != 0 and not blocked:
            if pos > 0:
                stop_hit = l[u] <= stop_px
                limit_hit = h[u] >= limit_px
            else:
                stop_hit = h[u] >= stop_px
                limit_hit = l[u] <= limit_px
            if stop_hit:                                # stop-first pessimism
                if pos > 0:
                    ex_px = o[u] if o[u] < stop_px else stop_px
                else:
                    ex_px = o[u] if o[u] > stop_px else stop_px
                _book(u, ex_px, pos, entry_px, entry_bar)
                pos = 0
            elif limit_hit:
                if pos > 0:
                    ex_px = o[u] if o[u] > limit_px else limit_px
                else:
                    ex_px = o[u] if o[u] < limit_px else limit_px
                _book(u, ex_px, pos, entry_px, entry_bar)
                pos = 0

        # 3) signal evaluation at u's close -> arm pending for u+1's open. A
        #    same-direction signal while already positioned that way is ignored
        #    (no re-arm); an opposite-direction signal arms a reversal; a
        #    direction-suppressed signal never arms anything at all (no synthetic
        #    exit -- the bracket alone exits, see docstring).
        ls, ss = bool(long_sig[u]), bool(short_sig[u])
        new_pending = None
        if ls and allow_long and pos != 1:
            new_pending = (1, l[u] - atr_stop_mult * atr_val[u],
                              c[u] + atr_tp_mult * atr_val[u])
        elif ss and allow_short and pos != -1:
            new_pending = (-1, h[u] + atr_stop_mult * atr_val[u],
                               c[u] - atr_tp_mult * atr_val[u])
        pending = new_pending

        # 4) roll-seam eve: force flat at this day's final bar close, kill pending
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
# Smoke test — tiny window, sane-output check. Run: python augur_strategies/AOSTOCH_1_0.py
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

    print("AOSTOCH 1.0 smoke test — NQ 5m RTH, 2015-2017 (%d bars, %d sessions)"
          % (len(df), len(set(day_id))))
    print("%-52s %7s %5s %6s %13s %11s" % ("config", "trades", "WR%", "PF", "net $", "maxDD$ (gross)"))
    print("-" * 100)
    for label, kw in [
        ("published: 5/34 AO, stoch 14/3, k20/80, rsi10 30/70, atr14x1/1, both", dict()),
        ("long-only variant", dict(direction="long")),
        ("wider bracket: atr_stop 2.0 / atr_tp 3.0", dict(atr_stop_mult=2.0, atr_tp_mult=3.0)),
        ("looser k-band 25/75", dict(k_low=25, k_high=75)),
    ]:
        r = run_backtest(df["open"].values, df["high"].values, df["low"].values,
                         df["close"].values, day_id=day_id, index=df.index,
                         return_trades=True, **kw)
        if r is None:
            print("%-52s  NO TRADES" % label); continue
        net_usd = (r["total_pnl"] - FEE * r["num_trades"]) * MULT
        print("%-52s %7d %4.0f%% %6.2f %13s %11s" % (
            label, r["num_trades"], r["win_rate"], min(r["profit_factor"], 99),
            "${:+,.0f}".format(net_usd), "${:,.0f}".format(r["max_drawdown"] * MULT)))

    # ── diagnostic: per-condition bar counts on the published long-side thresholds,
    #    to prove the oversold-confluence logic actually fires -- the published AND is
    #    a rare event on index futures, so a low/zero trade count alone wouldn't say
    #    whether the logic is broken or just correctly picky. ─────────────────────────
    o = df["open"].values; h = df["high"].values; l = df["low"].values; c = df["close"].values
    hl2 = (h + l) / 2.0
    sma5 = pd.Series(hl2).rolling(5).mean()
    sma34 = pd.Series(hl2).rolling(34).mean()
    awesome = ((sma5 - sma34) * 1000.0).to_numpy()
    ll14 = pd.Series(l).rolling(14).min(); hh14 = pd.Series(h).rolling(14).max()
    raw_stoch = 100.0 * (pd.Series(c) - ll14) / (hh14 - ll14).replace(0.0, np.nan)
    k_line = raw_stoch.rolling(3).mean().to_numpy()
    rsi_val = _wilder_rsi(c, 10)
    with np.errstate(invalid="ignore"):
        ao_rising = np.zeros(len(c), bool)
        ao_rising[1:] = awesome[1:] > awesome[:-1]
        cnt_k = int(np.nansum(k_line < 20))
        cnt_rsi = int(np.nansum(rsi_val < 30))
        cnt_ao = int(ao_rising.sum())
        cnt_and = int(np.nansum((k_line < 20) & (rsi_val < 30) & ao_rising))
    print()
    print("Per-condition bar counts (published LONG side, %d bars total, pre-warmup mask):" % len(c))
    print("  k<20 alone:            %6d" % cnt_k)
    print("  rsi<30 alone:          %6d" % cnt_rsi)
    print("  AO rising alone:       %6d" % cnt_ao)
    print("  ALL THREE (AND):       %6d  <- LongCondition bar count" % cnt_and)
    print()
    print("Points-based engine output; house cost_pts/mult applied by the caller "
          "(this table folds fee into net only). Sane-output check, not a result.")
