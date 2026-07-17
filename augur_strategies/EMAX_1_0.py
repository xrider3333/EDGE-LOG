"""
EMAX 1.0 — TV round-13 port #10: "BUY and SELL - Backtest single EMA cross" (by Che_Trader).

Source: https://www.tradingview.com/script/j9rq1wQq-BUY-and-SELL-Backtest-single-EMA-cross-By-che-trader/
(Pine v4, 10.7K boosts). Ported verbatim for EDGE-LOG challenger round 13 (see TV_SWEEP.md).
MPL-2.0 attribution retained in the port notes; this file is a re-implementation, not a
copy of the Pine text.

Published rules (defaults):
  ema1 = EMA(close, 10)  ("Select EMA 1"),  ema2 = EMA(close, 20)  ("Select EMA 2").
  LONG  signal: crossover(ema1, ema2)  -- ema1 crosses from <= ema2 up through > ema2.
  SHORT signal: crossunder(ema1, ema2) -- ema1 crosses from >= ema2 down through < ema2.
  strategy.entry("Long", strategy.long, when=longCondition) and the mirrored Short entry
  are plain MARKET orders (no price argument) -- Pine fills a market order at the NEXT
  bar's open. NO stop-loss, NO target, NO real exit logic: the opposite signal is the
  only exit. Default pyramiding 0 -> an opposite signal reverses the position in a single
  fill -- a stop-and-reverse system that is ALWAYS IN THE MARKET after the first entry
  (author's own title: "Backtest single EMA cross" -- the plainest momentum baseline of
  the round-13 sweep, no money management of any kind).
  The script also carries a cosmetic testStartYear..testStopYear "backtest window" input
  (default 2019-01-01 .. 2099-01-30) and a "Buy quantity" input (100000) -- both are
  chart/demo conveniences, not part of the EMA-cross signal itself, and are dropped here
  (see judgment-call note below); the port trades across the full loaded history like
  every other EDGE-LOG strategy.

Port semantics (house-honest, TV-parity):
  - Signals evaluate on bar t's CLOSE using bar-t EMA values only. Pine ema(): alpha =
    2/(len+1), recursively seeded with the first close -- implemented here with pandas
    ewm(span=len, adjust=False), which is the identical recursion.
  - Market-order fill during bar u = t+1: fills unconditionally at open[u]. There is no
    stop/limit price to test (unlike BBRSI_1_0's band-level stop entries) -- the order
    either fills at next bar's open or is suppressed by the roll-seam guard; it never
    rests waiting for a level.
  - Position is NET +/-1 contract; an opposite fill books the old trade and opens the
    new one at the same price (Pine strategy.entry reversal, pyramiding 0).
  - direction="long"/"short" is an EDGE-LOG grid-breadth addition (the published script
    is always "both"): the suppressed side's signal becomes a plain market EXIT (next
    bar's open fill) instead of a reversal, entries only on the allowed side. Mirrors
    the house long-only read used across the other round-13 ports.
  - Multi-day holds are intrinsic; positions are FORCE-FLATTENED at the close of the
    day before each detected NOADJ quarterly roll seam and no fill may occur on that
    day (same guard + calibration as TTIBS_1_0.detect_roll_seams / BBRSI_1_0). A trade
    still open when the loaded data ends is DROPPED, never truncated (lockbox-honest).
  - PNL = points only, costs applied downstream by the engine (0.533 pts/RT NQ,
    0.363 ES), same as every library strategy.

Judgment call: the Pine script's testPeriod() date gate (default 2019..2099) and its
"Buy quantity" input are TradingView chart/demo scaffolding, not the EMA-cross logic
being ported -- honoring the date gate literally would zero out any pre-2019 backtest
window for no strategic reason. Every other round-13 port reads "published defaults" as
the indicator parameters only; this file does the same and always trades.

Needs day_id AND index (roll-seam calendar + session boundaries); returns None without.
"""
import numpy as np
import pandas as pd

STRATEGY_NAME = 'EMAX 1.0 · TV#10 EMA 10/20 cross flip (Che_Trader)'
DESCRIPTION = ("Round-13 port of TradingView's single EMA-cross flip strategy: EMA(10)/"
               "EMA(20) crossover|crossunder, stop-and-reverse, plain market fills at the "
               "next open, no stops/targets. Roll-seam guarded, multi-day holds.")

_AUGUR_MARKET = {"instrument": "NQ", "timeframe": "5m"}
# Round-13 challenger family (TV top-boosts sweep) — not a fork of any house family.

DEFAULT_PARAMS = {
    "ema_fast": {
        "default": 10, "min": 2, "max": 60, "step": 1, "type": "int",
        "label": "EMA 1 (fast) length",
        "tooltip": "Published default 10 ('Select EMA 1'). Pine ema(): alpha = 2/(len+1).",
    },
    "ema_slow": {
        "default": 20, "min": 3, "max": 200, "step": 1, "type": "int",
        "label": "EMA 2 (slow) length",
        "tooltip": "Published default 20 ('Select EMA 2'). Must be > ema_fast -- grid "
                   "cells with ema_fast >= ema_slow self-skip (run_backtest -> None).",
    },
    "direction": {
        "default": "both", "type": "str",
        "options": ["both", "long", "short"],
        "label": "Trade direction",
        "tooltip": "both = published stop-and-reverse (strategy.entry Long + Short). "
                   "long = suppressed-short variant (short cross just exits at the next "
                   "open instead of reversing). short = mirror.",
    },
}

PARAM_GRID_PRESETS = {
    "Short  (published defaults)": {
        "ema_fast": [10], "ema_slow": [20], "direction": ["both"],
    },
    # Classic EMA pairs commonly paired with this script in the wild: (5,20) (9,21)
    # (10,20 published) (20,50) (20,100) (50,100). The grid engine wants independent
    # per-param value lists rather than paired tuples, so this is expressed as the
    # cartesian product of fast in [5,9,10,20,50] x slow in [20,21,50,100] x
    # direction[both,long] -- a superset of the six pairs above. run_backtest returns
    # None whenever ema_fast >= ema_slow, so every inverted/degenerate cell (e.g.
    # fast=50/slow=20) self-skips; only the valid fast<slow cells actually run.
    "Medium (classic-pairs grid)": {
        "ema_fast": [5, 9, 10, 20, 50], "ema_slow": [20, 21, 50, 100],
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
    ema_fast: int = 10, ema_slow: int = 20,
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

    ema_fast = int(ema_fast); ema_slow = int(ema_slow)
    if ema_fast >= ema_slow:
        return None                    # degenerate/inverted pair -- grid cell self-skips

    # ── indicators (Pine parity: ema() alpha = 2/(len+1)) ───────────────────────
    s = pd.Series(c)
    fast = s.ewm(span=ema_fast, adjust=False).mean().to_numpy()
    slow = s.ewm(span=ema_slow, adjust=False).mean().to_numpy()

    # crossover(a, b): a[t] > b[t] and a[t-1] <= b[t-1]   (Pine definition)
    long_sig = np.zeros(n, bool); short_sig = np.zeros(n, bool)
    long_sig[1:]  = (fast[1:] > slow[1:]) & (fast[:-1] <= slow[:-1])
    short_sig[1:] = (fast[1:] < slow[1:]) & (fast[:-1] >= slow[:-1])

    warm = max(5 * ema_slow, 60)
    long_sig[:warm] = False
    short_sig[:warm] = False

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

    # ── event loop ────────────────────────────────────────────────────────────
    pos = 0
    entry_px = 0.0
    entry_bar = -1
    pending = None            # +1/-1 = entry-or-reversal, 0 = market exit, None = no order
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

        # 1) pending market order, fills at THIS bar's open (order placed at u-1's
        #    close). Che_Trader's strategy.entry carries no price -> unconditional
        #    market fill, it never rests waiting for a level (unlike BBRSI_1_0).
        if pending is not None:
            if di not in blocked_days:
                fill = o[u]
                if pending == 0:                       # market exit (long/short-only mode)
                    if pos != 0:
                        _book(u, fill, pos, entry_px, entry_bar)
                        pos = 0
                elif pos == 0:
                    pos = pending; entry_px = fill; entry_bar = u
                elif pos != pending:                   # reversal: book old, open new
                    _book(u, fill, pos, entry_px, entry_bar)
                    pos = pending; entry_px = fill; entry_bar = u
            pending = None                              # fills or is suppressed, either way

        # 2) signal evaluation at u's close -> arm the next bar's order
        ls, ss = long_sig[u], short_sig[u]
        new_pending = None
        if ls and allow_long and pos <= 0:
            new_pending = 1
        elif ss and allow_short and pos >= 0:
            new_pending = -1
        elif ls and not allow_long and pos < 0:
            new_pending = 0                            # short-only mode: long cross = exit
        elif ss and not allow_short and pos > 0:
            new_pending = 0                            # long-only mode: short cross = exit
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
# Smoke test — tiny window, sane-output check. Run: python augur_strategies/EMAX_1_0.py
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

    print("EMAX 1.0 smoke test — NQ 5m RTH, 2015-2017 (%d bars, %d sessions)"
          % (len(df), len(set(day_id))))
    print("%-52s %7s %5s %6s %13s %11s" % ("config", "trades", "WR%", "PF", "net $", "maxDD$ (gross)"))
    print("-" * 100)
    for label, kw in [
        ("published: EMA 10/20, both", dict()),
        ("EMA 10/20, long-only", dict(direction="long")),
        ("EMA 20/100, both (grid corner)", dict(ema_fast=20, ema_slow=100)),
        ("EMA 9/21, both (grid corner)", dict(ema_fast=9, ema_slow=21)),
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
