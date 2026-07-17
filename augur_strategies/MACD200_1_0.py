"""
MACD200 1.0 — TV round-13 port #2: "MACD + SMA 200 Strategy (by ChartArt)".

Source: https://www.tradingview.com/script/yMCa3XZD-MACD-SMA-200-Strategy-by-ChartArt/
(Pine v2, Nov-2015, 30.4K boosts). Ported verbatim for EDGE-LOG challenger round 13
(see TV_SWEEP.md). Original license/House Rules apply; this file is a re-implementation,
not a copy of the Pine text.

Published rules (defaults):
  fastMA = SMA(close,12); slowMA = SMA(close,26); macd = fastMA - slowMA;
  signal = SMA(macd,9); hist = macd - signal; veryslowMA = SMA(close,200).
  NOTE: this is a SIMPLE-moving-average "MACD" (sma() throughout), NOT the standard
  EMA MACD -- ported as-written, quirks included.
  LONG  signal: hist crosses ABOVE 0  AND macd>0  AND fastMA>slowMA  AND
                close[26 bars ago] > veryslowMA (CURRENT sma200 value -- the Pine
                `close[slowLength] > veryslowMA` literal-lag quirk; slowLength=26).
  SHORT signal: mirror (hist crosses below 0, macd<0, fastMA<slowMA,
                close[26 bars ago] < veryslowMA).
  Entry is a Pine STOP order at the signal bar's LOW (long) / HIGH (short) -- usually
  already marketable so it fills at the next bar's open; if price gaps past the level
  it rests AT the level and fills intrabar the first time that bar's high/low reaches
  it. UNLIKE a 1-bar stop order, this pending order is PERSISTENT: it stays live across
  many bars until (a) filled, (b) replaced by a fresh same-side signal (new level), or
  (c) the trend-cancel condition (slowMA<veryslowMA for longs, slowMA>veryslowMA for
  shorts) evaluates true at some later bar's close (the script's strategy.cancel()
  branch, checked every bar). Long and short pending orders are independent (their own
  ids, their own cancel rule) and CAN coexist. No stop-loss, no target: the opposite
  signal's fill is the only exit -- a stop-and-reverse system, always in the market
  after the first fill.
  Pine's strategy.risk.max_intraday_loss(50%) is OMITTED here: it is an account-equity
  circuit breaker (percent-of-equity halt), meaningless at this engine's fixed
  1-contract futures scale -- there is no equity curve to measure "50% of equity"
  against, and every other library strategy omits this same class of Pine risk-module
  call.

Port semantics (house-honest, TV-parity):
  - Signals evaluate on bar t's CLOSE using bar-t indicator values only.
  - A stop order placed/updated at signal bar t's close is evaluated starting bar t+1
    and on every subsequent bar until filled, replaced, or cancelled: fills at that
    bar's open if the open is already past the level, else AT the level the first time
    that bar's high (long) / low (short) reaches it. Never uses information from the
    fill bar's close.
  - Position is NET +/-1 contract; an opposite-side fill books the old trade and opens
    the new one at the same fill price (Pine strategy.entry reversal, pyramiding 0). A
    same-direction signal while already positioned that way does not place a new order
    at all -- a fill could never add size under pyramiding 0, so arming the order would
    be a no-op; skipping it is the simplest faithful equivalent.
  - direction="long"/"short" generalizes the published both-sides system: the
    suppressed side's signal no longer arms a stop-and-reverse order -- it becomes a
    plain market EXIT (next bar's open fill) of the current position instead, mirroring
    BBRSI_1_0's direction-gating approach.
  - Multi-day holds are intrinsic; positions are FORCE-FLATTENED at the close of the
    day before each detected NOADJ quarterly roll seam and no fill may occur on that
    day (same guard + calibration as TTIBS_1_0.detect_roll_seams). A trade still open
    when the loaded data ends is DROPPED, never truncated (lockbox-honest).
  - PNL = points only, costs applied downstream by the engine (0.533 pts/RT NQ,
    0.363 ES), same as every library strategy.

Needs day_id AND index (roll-seam calendar + session boundaries); returns None without.
"""
import numpy as np
import pandas as pd

STRATEGY_NAME = 'MACD200 1.0 · TV#2 MACD(sma)+SMA200 stop-and-reverse (ChartArt)'
DESCRIPTION = ("Round-13 verbatim port of TradingView's MACD+SMA200 strategy: an "
               "SMA-built MACD histogram crossing zero, trend-filtered by SMA200 and a "
               "26-bar-lagged close check, stop-and-reverse, no stops/targets. Stop-entry "
               "orders persist across bars until filled/replaced/cancelled (TV parity), "
               "roll-seam guarded, multi-day holds.")

_AUGUR_MARKET = {"instrument": "NQ", "timeframe": "5m"}
# Round-13 challenger family (TV top-boosts sweep) — not a fork of any house family.

DEFAULT_PARAMS = {
    "fast_len": {
        "default": 12, "min": 4, "max": 30, "step": 1, "type": "int",
        "label": "MACD fast SMA length",
        "tooltip": "Published default 12. This 'MACD' is built from SIMPLE moving "
                   "averages (sma), not the standard EMA MACD -- ChartArt's script "
                   "uses sma() throughout, ported as-written.",
    },
    "slow_len": {
        "default": 26, "min": 10, "max": 60, "step": 1, "type": "int",
        "label": "MACD slow SMA length",
        "tooltip": "Published default 26. Also reused verbatim as the close[] lookback "
                   "in the veryslowMA filter (the close[slowLength] > veryslowMA quirk).",
    },
    "sig_len": {
        "default": 9, "min": 3, "max": 30, "step": 1, "type": "int",
        "label": "MACD signal SMA length",
        "tooltip": "Published default 9. signal = SMA(macd, sig_len); hist = macd - signal.",
    },
    "sma_len": {
        "default": 200, "min": 50, "max": 300, "step": 10, "type": "int",
        "label": "Very slow (trend) SMA length",
        "tooltip": "Published default 200. The macro trend filter: both cancel "
                   "conditions and the close[slowLength] filter reference this SMA.",
    },
    "direction": {
        "default": "both", "type": "str",
        "options": ["both", "long", "short"],
        "label": "Trade direction",
        "tooltip": "both = published v1.0 stop-and-reverse. long = long-only (short "
                   "signal exits at the next open instead of arming a reversal). "
                   "short = mirror.",
    },
}

PARAM_GRID_PRESETS = {
    "Short  (published defaults)": {
        "fast_len": [12], "slow_len": [26], "sig_len": [9], "sma_len": [200],
        "direction": ["both"],
    },
    # Pre-registered round-13 refinement grid (author knobs only; TV_SWEEP.md 13.2):
    "Medium (author-knob grid)": {
        "fast_len": [8, 12], "slow_len": [21, 26], "sig_len": [9], "sma_len": [100, 200],
        "direction": ["both", "long"],
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


def run_backtest(
    opens, highs, lows, closes,
    volumes=None, day_id=None, index=None,
    fast_len: int = 12, slow_len: int = 26, sig_len: int = 9, sma_len: int = 200,
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

    fast_len = int(fast_len); slow_len = int(slow_len)
    sig_len = int(sig_len); sma_len = int(sma_len)

    # ── indicators (Pine parity: an sma-built "MACD", NOT the standard EMA MACD) ──
    s = pd.Series(c)
    fastMA = s.rolling(fast_len).mean().to_numpy()
    slowMA = s.rolling(slow_len).mean().to_numpy()
    veryslowMA = s.rolling(sma_len).mean().to_numpy()
    macd = fastMA - slowMA
    signal = pd.Series(macd).rolling(sig_len).mean().to_numpy()
    hist = macd - signal

    # close[slowLength]: close shifted back slow_len bars (NaN-padded at the start)
    close_lag_slow = np.full(n, np.nan)
    if slow_len < n:
        close_lag_slow[slow_len:] = c[:-slow_len]

    # crossover/crossunder(hist, 0): current vs 0, previous vs 0 (Pine two-bar definition)
    xo_hist = np.zeros(n, bool); xu_hist = np.zeros(n, bool)
    xo_hist[1:] = (hist[1:] > 0) & (hist[:-1] <= 0)
    xu_hist[1:] = (hist[1:] < 0) & (hist[:-1] >= 0)

    with np.errstate(invalid="ignore"):
        long_sig = xo_hist & (macd > 0) & (fastMA > slowMA) & (close_lag_slow > veryslowMA)
        short_sig = xu_hist & (macd < 0) & (fastMA < slowMA) & (close_lag_slow < veryslowMA)
        cancel_long = slowMA < veryslowMA          # strategy.cancel("MACDLE") condition
        cancel_short = slowMA > veryslowMA         # strategy.cancel("MACDSE") condition

    # need t>=226 bars for close[t-26] (slow_len default) and a full sma200 window
    warm = max(230, 60)
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
    pending_long = None       # resting BUY STOP level ("MACDLE"), or None
    pending_short = None      # resting SELL STOP level ("MACDSE"), or None
    pending_flat = False      # one-shot market exit (direction-suppressed side), next open
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

        # 1) pending fill attempts, intrabar u (orders placed/updated at an earlier
        #    bar's close and may have been resting for many bars). Long is attempted
        #    before short -- see the docstring/port-notes on this rare same-bar-both
        #    edge case (long and short pendings are independent and can coexist).
        if pending_long is not None:
            lvl = pending_long
            fill = None
            if o[u] >= lvl:
                fill = o[u]
            elif h[u] >= lvl:
                fill = lvl
            if fill is not None:
                if di not in blocked_days:
                    if pos == 0:
                        pos = 1; entry_px = fill; entry_bar = u
                    elif pos != 1:                     # reversal: book old, open new
                        _book(u, fill, pos, entry_px, entry_bar)
                        pos = 1; entry_px = fill; entry_bar = u
                    # pos == 1 already: pyramiding 0, no-op (should not occur --
                    # same-direction signals never re-arm while already positioned)
                pending_long = None

        if pending_short is not None:
            lvl = pending_short
            fill = None
            if o[u] <= lvl:
                fill = o[u]
            elif l[u] <= lvl:
                fill = lvl
            if fill is not None:
                if di not in blocked_days:
                    if pos == 0:
                        pos = -1; entry_px = fill; entry_bar = u
                    elif pos != -1:                    # reversal: book old, open new
                        _book(u, fill, pos, entry_px, entry_bar)
                        pos = -1; entry_px = fill; entry_bar = u
                pending_short = None

        if pending_flat:
            fill = o[u]
            if di not in blocked_days and pos != 0:
                _book(u, fill, pos, entry_px, entry_bar)
                pos = 0
            pending_flat = False

        # 2) signal evaluation at u's close -> replace/cancel pending. Pine source
        #    order preserved: cancelLong, entry-long, cancelShort, entry-short.
        if allow_long:
            if cancel_long[u]:
                pending_long = None
            if long_sig[u] and pos != 1:
                pending_long = l[u]                    # buy stop at this bar's low
        elif long_sig[u] and pos < 0:
            pending_flat = True                        # short-only mode: long sig = exit

        if allow_short:
            if cancel_short[u]:
                pending_short = None
            if short_sig[u] and pos != -1:
                pending_short = h[u]                   # sell stop at this bar's high
        elif short_sig[u] and pos > 0:
            pending_flat = True                        # long-only mode: short sig = exit

        # 3) roll-seam eve: force flat at this day's final bar close, kill all pendings
        if di in force_exit_days and u == last_bar_of_day[di]:
            if pos != 0:
                _book(u, c[u], pos, entry_px, entry_bar)
                pos = 0
            pending_long = None
            pending_short = None
            pending_flat = False

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
# Smoke test — tiny window, sane-output check. Run: python augur_strategies/MACD200_1_0.py
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

    print("MACD200 1.0 smoke test — NQ 5m RTH, 2015-2017 (%d bars, %d sessions)"
          % (len(df), len(set(day_id))))
    print("%-52s %7s %5s %6s %13s %11s" % ("config", "trades", "WR%", "PF", "net $", "maxDD$ (gross)"))
    print("-" * 100)
    for label, kw in [
        ("published: 12/26/9, SMA200, both", dict()),
        ("long-only variant", dict(direction="long")),
        ("fast 8 / slow 21, SMA100 (grid corner)", dict(fast_len=8, slow_len=21, sma_len=100)),
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
    print("\nPoints-based engine output; house cost_pts/mult applied by the caller "
          "(this table folds fee into net only). Sane-output check, not a result.")
