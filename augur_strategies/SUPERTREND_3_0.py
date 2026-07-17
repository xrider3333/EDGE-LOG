"""
SUPERTREND 3.0 — TV round-13 port #3: "SuperTrend STRATEGY" by KivancOzbilgic.

Source: https://www.tradingview.com/script/P5Gu6F8k/
(Pine v4, 24.4K boosts). Ported verbatim for EDGE-LOG challenger round 13 (see
TV_SWEEP.md). MPL-2.0 attribution retained in the port notes; this file is a
re-implementation, not a copy of the Pine text.

This is a NEW, independent file. SUPERTREND_1_0.py and SUPERTREND_2_0.py already in
this folder are older, loose adaptations (SMA-of-true-range "ATR", multiplier
3.5/4.5, an added EMA filter, non-house fill conventions) -- they are NOT Pine ports
of this script, their logic was not consulted while writing this file, and they are
left completely untouched. SUPERTREND_3_0 supersedes them ONLY for the round-13
verbatim-port test; it does not replace them in the strategy library.

Published rules (defaults):
  src = hl2 = (high+low)/2.  ATR period 10, multiplier 3.0.
  changeATR (published default true): true -> atr = Pine atr(10) = Wilder RMA of true
  range; false -> atr = SMA(true range, 10) (the script's own robustness toggle).
  SuperTrend bands are the classic RECURSIVE form, not a stateless band:
    up = src - mult*atr; ratchets UP  (up := max(up, up[1])) whenever close[1] > up[1]
    dn = src + mult*atr; ratchets DOWN (dn := min(dn, dn[1])) whenever close[1] < dn[1]
    trend flips -1->+1 when close > dn[1]; flips +1->-1 when close < up[1]; else holds
    (trend initialized to +1, matching the Pine `trend = 1` default).
  buySignal = trend flips -1->+1 this bar; sellSignal = trend flips +1->-1 this bar.
  strategy.entry on each signal, pyramiding 0 -> a plain ALWAYS-IN stop-and-reverse
  system: default order execution (process_orders_on_close=false) fills at the NEXT
  bar's open, market, no price level. The script's own From/To date-window inputs are
  just a backtest-range control in the Pine strategy tester; ignored here -- EDGE-LOG
  controls the data window upstream, not the strategy. showsignals / highlighting /
  barcoloring inputs are plot-only and have zero effect on strategy logic; omitted.
  The "Source" input defaults to (and, in this port, is fixed at) hl2 -- changing the
  source is a chart-study nicety, not part of the published strategy's identity.

Port semantics (house-honest, TV-parity):
  - The up/dn ratchet and the trend flip are mutually recursive series (each bar's
    ratchet depends on the PREVIOUS bar's already-ratcheted band, and the flip test
    reads that same previous-bar band -- Pine's nz(up[1]), nz(dn[1])). This cannot be
    vectorized; implemented as a single sequential loop over bars carrying
    (up_prev, dn_prev, trend_prev), trend initialized to +1.
  - Entries are plain market fills at the next bar's open (no price level, unlike
    BBRSI_1_0's band-level stop order): a pending order armed at bar u's close always
    resolves at bar u+1's open, or dies unfilled if u+1 falls on a blocked roll-seam-
    eve day. It never rests longer than one bar -- there is no price condition to
    wait on, so "resting" isn't a concept here the way it is for a stop order.
  - Position is NET +/-1 contract; an opposite signal books the old trade and opens
    the new one at the same fill (Pine strategy.entry reversal, pyramiding 0).
  - direction="long"/"short" (house round-13 convention, same as BBRSI_1_0): the
    suppressed side's flip becomes a plain market EXIT at the next open instead of a
    new position. "both" (default) = the published always-in system.
  - Multi-day holds are intrinsic; positions are FORCE-FLATTENED at the close of the
    day before each detected NOADJ quarterly roll seam and no fill may occur on that
    day (same guard + calibration as TTIBS_1_0.detect_roll_seams / BBRSI_1_0). A trade
    still open when the loaded data ends is DROPPED, never truncated (lockbox-honest).
  - PNL = points only, costs applied downstream by the engine (0.533 pts/RT NQ,
    0.363 ES), same as every library strategy.

Needs day_id AND index (roll-seam calendar + session boundaries); returns None without.
"""
import numpy as np
import pandas as pd

STRATEGY_NAME = 'SUPERTREND 3.0 · TV#3 Kivanc verbatim flip (round-13)'
DESCRIPTION = ("Round-13 verbatim port of TradingView's SuperTrend STRATEGY (KivancOzbilgic, "
               "24.4K boosts): recursive hl2 +/- mult*ATR bands that ratchet against their own "
               "prior value, trend-flip buy/sell signals, stop-and-reverse, no stops/targets. "
               "Market fills at next open (TV parity), roll-seam guarded, multi-day holds.")

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
        "tooltip": "Published default 3.0 (Pine 'Multiplier' input, author's own step 0.1).",
    },
    "change_atr": {
        "default": True, "type": "bool",
        "label": "Wilder RMA ATR (vs SMA of true range)",
        "tooltip": "Published default True: atr = Pine atr() = Wilder RMA(TR, period). "
                   "False = atr2 = SMA(TR, period) -- the script's own 'changeATR' "
                   "robustness switch.",
    },
    "direction": {
        "default": "both", "type": "str",
        "options": ["both", "long", "short"],
        "label": "Trade direction",
        "tooltip": "both = published stop-and-reverse (always in the market once a first "
                   "position is entered). long/short = house round-13 convention: the "
                   "suppressed side's flip becomes a plain market exit at the next open "
                   "instead of a new position (same convention as BBRSI_1_0).",
    },
}

PARAM_GRID_PRESETS = {
    "Short  (published defaults)": {
        "atr_period": [10], "mult": [3.0], "change_atr": [True], "direction": ["both"],
    },
    # Pre-registered round-13 refinement grid (author knobs only; TV_SWEEP.md 13.3):
    "Medium (author-knob grid)": {
        "atr_period": [7, 10, 14, 20], "mult": [2.0, 3.0, 4.0],
        "change_atr": [True], "direction": ["both", "long"],
    },
    "Long   (adds SMA-ATR robustness)": {
        "atr_period": [7, 10, 14, 20], "mult": [2.0, 3.0, 4.0],
        "change_atr": [True, False], "direction": ["both", "long"],
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


def _supertrend_trend(src, atr, close, mult):
    """Sequential SuperTrend ratchet + trend flip, exactly as the Pine script's
    recursive up/dn/trend series (see module docstring). Bar-by-bar loop by
    necessity: the up/dn bands ratchet against their OWN previous (already-
    ratcheted) value conditioned on close[t-1], and the trend flip test reads that
    same previous-bar band (Pine's nz(up[1]), nz(dn[1])) -- not vectorizable
    without carrying that look-back state explicitly. Returns trend[] (int8,
    +1/-1) aligned to the input arrays. Scalars are cast to plain Python float
    inside the loop so NaN comparisons (possible during SMA-ATR warm-up, before
    `atr_period` bars of true range have accumulated) behave as ordinary Python
    `nan > x` -> False, never raising -- and the mask applied by the caller's
    `warm` cutoff means no such NaN ever reaches a real signal anyway.
    """
    n = len(close)
    trend = np.empty(n, dtype=np.int8)
    up_prev = None
    dn_prev = None
    trend_prev = 1
    prev_close = None
    for t in range(n):
        s = float(src[t]); a = float(atr[t])
        up_raw = s - mult * a
        dn_raw = s + mult * a
        up1 = up_raw if up_prev is None else up_prev
        dn1 = dn_raw if dn_prev is None else dn_prev

        if prev_close is not None and prev_close > up1:
            up_t = max(up_raw, up1)
        else:
            up_t = up_raw
        if prev_close is not None and prev_close < dn1:
            dn_t = min(dn_raw, dn1)
        else:
            dn_t = dn_raw

        c_t = float(close[t])
        if trend_prev == -1 and c_t > dn1:
            trend_t = 1
        elif trend_prev == 1 and c_t < up1:
            trend_t = -1
        else:
            trend_t = trend_prev

        trend[t] = trend_t
        up_prev, dn_prev, trend_prev = up_t, dn_t, trend_t
        prev_close = c_t
    return trend


def run_backtest(
    opens, highs, lows, closes,
    volumes=None, day_id=None, index=None,
    atr_period: int = 10, mult: float = 3.0,
    change_atr: bool = True, direction: str = "both",
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
    change_atr = bool(change_atr)

    # ── indicators (Pine parity) ──────────────────────────────────────────────
    src = (h + l) / 2.0                              # hl2
    tr = np.empty(n, float)
    tr[0] = h[0] - l[0]
    tr[1:] = np.maximum(h[1:] - l[1:],
                         np.maximum(np.abs(h[1:] - c[:-1]), np.abs(l[1:] - c[:-1])))
    if change_atr:
        # Pine atr(Periods) = rma(tr, Periods); ewm(alpha=1/len, adjust=False) converges
        # to Pine's recursive rma after warm-up (same house convention as
        # BBRSI_1_0._wilder_rsi -- signals are warm-up masked regardless).
        atr = pd.Series(tr).ewm(alpha=1.0 / atr_period, adjust=False).mean().to_numpy()
    else:
        atr = pd.Series(tr).rolling(atr_period).mean().to_numpy()   # atr2 = sma(tr, Periods)

    trend = _supertrend_trend(src, atr, c, mult)

    buy_sig = np.zeros(n, bool); sell_sig = np.zeros(n, bool)
    buy_sig[1:] = (trend[1:] == 1) & (trend[:-1] == -1)
    sell_sig[1:] = (trend[1:] == -1) & (trend[:-1] == 1)

    warm = max(5 * atr_period, 60)
    buy_sig[:warm] = False
    sell_sig[:warm] = False

    # ── session / roll-seam scaffolding ──────────────────────────────────────
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

        # 1) fill any pending order at u's open (order was armed at u-1's close). ST
        #    orders are plain next-bar market orders -- always resolved this bar,
        #    no resting/level logic (unlike BBRSI_1_0's stop-at-band-level orders).
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
# Smoke test — tiny window, sane-output check. Run: python augur_strategies/SUPERTREND_3_0.py
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

    print("SUPERTREND 3.0 smoke test — NQ 5m RTH, 2015-2017 (%d bars, %d sessions)"
          % (len(df), len(set(day_id))))
    print("%-52s %7s %5s %6s %13s %11s" % ("config", "trades", "WR%", "PF", "net $", "maxDD$ (gross)"))
    print("-" * 100)

    configs = [
        ("published: 10/3.0, Wilder RMA ATR, both", dict()),
        ("10/3.0, long-only", dict(direction="long")),
        ("10/3.0, SMA-ATR (change_atr=False)", dict(change_atr=False)),
        ("20/4.0, both (grid corner)", dict(atr_period=20, mult=4.0)),
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

    print("\nHand-check -- first 3 trades of the published config (verify the flip "
          "logic visually against a SuperTrend(10,3) chart):")
    r0 = results.get("published: 10/3.0, Wilder RMA ATR, both")
    if r0 and r0.get("trades"):
        for t in r0["trades"][:3]:
            eb, xb, pnl, side, ep, xp = t
            print("  %-5s entry %s @ %10.2f  ->  exit %s @ %10.2f   pnl %+8.2f pts" % (
                "LONG" if side > 0 else "SHORT",
                df.index[eb].strftime("%Y-%m-%d %H:%M %Z"), ep,
                df.index[xb].strftime("%Y-%m-%d %H:%M %Z"), xp, pnl))
    else:
        print("  (no trades to show)")
