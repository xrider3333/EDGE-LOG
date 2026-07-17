"""
GOLDX 1.0 — TV round-13 port #8: "Golden Cross, SMA 200 Long Only, Moving Average
Strategy (by ChartArt)".

Source: https://www.tradingview.com/script/6ZReHYKn-Golden-Cross-SMA-200-Moving-Average-Strategy-by-ChartArt/
(Pine v2, idea dated June 19 2016, 10.9K boosts). Ported for EDGE-LOG challenger round 13
(see TV_SWEEP.md). Original license/House Rules apply; this file is a re-implementation,
not a copy of the Pine text. This is the simplest port in the sweep -- one signal, one
crossing pair, no bands/filters/stops -- kept minimal on purpose.

Published rules (defaults, verbatim):
  fast = SMA(close, 50); slow = SMA(close, 200).
  LONG entry: crossover(fast, slow) -- fast crosses from <= slow up through > slow.
  EXIT (to flat): crossunder(fast, slow) -- fast crosses from >= slow down through < slow.
  strategy.entry("long", strategy.long) on the bullish cross and strategy.close("long",
  when=bearish_cross) are both plain Pine market orders (no price argument) -> each
  fills at the NEXT bar's open (Pine's standard non-realtime fill model). The script
  never shorts -- there is no short-entry code at all; long-only is the published
  design, not a suppressed-side reading. No stop-loss, no take-profit, no session logic.
  switch1/switch2/switch3 (bar-color toggle, fast/slow plot visibility), the plot()/
  barcolor() calls and the two alertcondition() calls are TradingView chart cosmetics,
  not trading rules -- dropped, matching every other round-13 port's treatment of
  chart-only inputs.

IMPORTANT -- intraday vs. the author's daily chart: ChartArt built and illustrated this
on a DAILY chart, where a 50/200-bar SMA cross is the classic multi-month "Golden
Cross" trend signal. Ported LITERALLY onto intraday bars, 50/200 is a much faster
signal -- on 5m bars (78 bars/session) it is closer to a 50/200-BAR (not day) cross and
fires every few days, not every few months. Both readings are deliberately in scope
here: the as-literal 50/200 intraday cross is tested directly (published defaults), and
the author's actual daily-chart-scale intent is approximated by upscaling both lengths
together (the sma_fast/sma_slow grid below) so the pair keeps its shape while covering
more "days" of look-back on 5m bars. Expect a G1 sample-floor tension at the large end
of that grid (TV_SWEEP.md G1: n >= 300 trades) -- a signal built to fire a few times a
YEAR, even summed across the full multi-year triage window and both directions, may
simply not clear 300 trades; that is the strategy behaving as designed, not a porting
defect.

Port semantics (house-honest, TV-parity):
  - Signals evaluate on bar t's CLOSE using bar-t SMA values only (fast[t] vs slow[t],
    the standard Pine two-bar crossover/crossunder definition -- same as every other
    round-13 port).
  - Every fill is a plain market order at the very next bar's open -- no level/stop to
    test (unlike BBRSI_1_0's band-level stop entries): a signal at bar t's close always
    fills at bar t+1's open unless that bar falls on a roll-seam-eve blocked day, in
    which case the order is dropped outright (never delayed to a later bar).
  - direction="long" (published, default): long/flat only -- crossunder is a plain exit
    to flat (Pine strategy.close), never a short entry. direction="both": EDGE-LOG
    grid-breadth add-on that turns the exit into a stop-and-reverse (crossunder while
    long/flat opens/flips short; the mirrored crossover flips back) -- not part of the
    published script, included only to see whether the "let it also short" corner does
    any work in the grid.
  - Position is NET +/-1 or 0; a reversal (direction="both") books the old trade and
    opens the new one at the same fill price (same convention as every other round-13
    port).
  - Multi-day (indeed multi-week/month at the upscaled lengths) holds are intrinsic --
    the whole point of a 200-length SMA cross is to ride one trend for a long stretch;
    positions are FORCE-FLATTENED at the close of the day before each detected NOADJ
    quarterly roll seam and no fill may occur on that day (same guard + calibration as
    TTIBS_1_0.detect_roll_seams). A trade still open when the loaded data ends is
    DROPPED, never truncated (lockbox-honest).
  - PNL = points only, costs applied downstream by the engine (0.533 pts/RT NQ, 0.363
    ES), same as every library strategy.

Judgment calls:
  - The published script is long-only via its own code (no short-entry logic exists at
    all) -- direction="long" is therefore the single published reading, not a
    suppressed-side generalization like BBRSI/MACD200/EMAX's long-only mode. "both" is
    a pure EDGE-LOG-added grid corner, per the round-13 brief's author-knob grid.
  - sma_fast/sma_slow are treated as ONE knob, not two independent ones: run_backtest
    returns None unless sma_slow == 4 x sma_fast, so only the pre-registered upscaled
    pairs (50/200, 200/800, 390/1560, 975/3900) ever produce trades -- see
    PARAM_GRID_PRESETS below.

Needs day_id AND index (roll-seam calendar + session boundaries); returns None without.
"""
import numpy as np
import pandas as pd

STRATEGY_NAME = 'GOLDX 1.0 · TV#8 Golden Cross 50/200 long (ChartArt)'
DESCRIPTION = ("Round-13 port of TradingView's Golden Cross strategy: SMA(50)/SMA(200) "
               "crossover|crossunder drives entries and exits, long/flat only as "
               "published (an added 'both' direction turns it into a stop-and-reverse "
               "grid corner). Plain market fills at the next open, no stops/targets, "
               "roll-seam guarded, multi-day holds.")

_AUGUR_MARKET = {"instrument": "NQ", "timeframe": "5m"}
# Round-13 challenger family (TV top-boosts sweep) — not a fork of any house family.

DEFAULT_PARAMS = {
    "sma_fast": {
        "default": 50, "min": 10, "max": 1000, "step": 5, "type": "int",
        "label": "Fast SMA length",
        "tooltip": "Published default 50. Paired with sma_slow as one knob (must "
                   "satisfy sma_slow == 4 x sma_fast -- run_backtest returns no trades "
                   "otherwise); upscaling both together approximates the author's "
                   "daily-chart-scale intent on intraday bars.",
    },
    "sma_slow": {
        "default": 200, "min": 40, "max": 4000, "step": 10, "type": "int",
        "label": "Slow SMA length",
        "tooltip": "Published default 200 (the 'Golden Cross' level). Must equal "
                   "4 x sma_fast, e.g. 200/800/1560/3900 for fast 50/200/390/975.",
    },
    "direction": {
        "default": "long", "type": "str",
        "options": ["long", "both"],
        "label": "Trade direction",
        "tooltip": "long = published (long/flat only; crossunder just exits to flat, "
                   "the script never shorts). both = EDGE-LOG grid-breadth add-on: "
                   "crossunder flips to short instead of exiting (stop-and-reverse) -- "
                   "not part of the published script.",
    },
}

PARAM_GRID_PRESETS = {
    "Short  (published defaults)": {
        "sma_fast": [50], "sma_slow": [200], "direction": ["long"],
    },
    # Pre-registered round-13 refinement grid (author-knob upscale only; TV_SWEEP.md
    # 13.8): the four intended (fast, slow) pairs approximate the daily 50/200 cross on
    # 5m bars at increasing look-back scale (1x, 4x, 7.8x, 19.5x the published lengths).
    # The grid engine wants independent per-param value lists rather than paired
    # tuples, so this is expressed as the cartesian product of sma_fast x sma_slow x
    # direction; run_backtest returns None whenever sma_slow != 4 * sma_fast, so only
    # the 8 intended diagonal cells (4 length pairs x 2 directions) actually run --
    # every off-diagonal cell self-skips.
    "Medium (author-knob grid)": {
        "sma_fast": [50, 200, 390, 975], "sma_slow": [200, 800, 1560, 3900],
        "direction": ["long", "both"],
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
    sma_fast: int = 50, sma_slow: int = 200,
    direction: str = "long",
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

    sma_fast = int(sma_fast); sma_slow = int(sma_slow)
    direction = str(direction)
    if sma_fast < 1 or sma_slow < 1 or sma_slow != 4 * sma_fast:
        return None                    # only the intended upscaled pairs are meaningful

    # ── indicators (Pine parity: sma()) ─────────────────────────────────────────
    s = pd.Series(c)
    fast = s.rolling(sma_fast).mean().to_numpy()
    slow = s.rolling(sma_slow).mean().to_numpy()

    # crossover/crossunder(fast, slow): Pine two-bar definition. NaN during the
    # rolling-mean warmup (first sma_slow-1 bars) triggers benign invalid-compare
    # warnings, silenced here (same pattern as BBRSI_1_0/HULL_1_0's rolling indicators).
    long_sig = np.zeros(n, bool); short_sig = np.zeros(n, bool)
    with np.errstate(invalid="ignore"):
        long_sig[1:]  = (fast[1:] > slow[1:]) & (fast[:-1] <= slow[:-1])
        short_sig[1:] = (fast[1:] < slow[1:]) & (fast[:-1] >= slow[:-1])

    warm = sma_slow + 10
    long_sig[:warm] = False
    short_sig[:warm] = False

    # ── session / roll-seam scaffolding (identical to BBRSI/EMAX/HULL) ──────────
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

    # ── event loop ────────────────────────────────────────────────────────────
    pos = 0
    entry_px = 0.0
    entry_bar = -1
    pending = None            # target position after next fill: -1 / 0 / +1, or None
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

        # 1) pending market order fill, intrabar u (order placed at u-1's close).
        #    Plain market order (Pine strategy.entry/strategy.close, no price arg) ->
        #    always fills at this bar's open unless the day is roll-seam-eve blocked,
        #    in which case it is dropped outright (never delayed to a later bar).
        if pending is not None:
            if di not in blocked_days:
                fill = o[u]
                target = pending
                if target == 0:
                    if pos != 0:
                        _book(u, fill, pos, entry_px, entry_bar)
                        pos = 0
                elif pos == 0:
                    pos = target; entry_px = fill; entry_bar = u
                elif pos != target:                    # reversal: book old, open new
                    _book(u, fill, pos, entry_px, entry_bar)
                    pos = target; entry_px = fill; entry_bar = u
                # pos == target already: no-op (signal guards below prevent this)
            pending = None

        # 2) signal evaluation at u's close -> set next bar's pending order
        ls, ss = long_sig[u], short_sig[u]
        new_pending = None
        if direction == "long":
            if ls and pos == 0:
                new_pending = 1
            elif ss and pos == 1:
                new_pending = 0                        # published exit-to-flat
        else:  # direction == "both": always-in stop-and-reverse (grid-breadth add-on)
            if ls and pos <= 0:
                new_pending = 1
            elif ss and pos >= 0:
                new_pending = -1
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
# Smoke test — tiny window, sane-output check. Run: python augur_strategies/GOLDX_1_0.py
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

    print("GOLDX 1.0 smoke test — NQ 5m RTH, 2015-2017 (%d bars, %d sessions)"
          % (len(df), len(set(day_id))))
    print("%-52s %7s %5s %6s %13s %11s" % ("config", "trades", "WR%", "PF", "net $", "maxDD$ (gross)"))
    print("-" * 100)
    for label, kw in [
        ("published: 50/200, long (as-shipped)", dict()),
        ("200/800, long (4x upscale)", dict(sma_fast=200, sma_slow=800)),
        ("390/1560, long (~daily-scale upscale)", dict(sma_fast=390, sma_slow=1560)),
        ("50/200, both (grid-breadth short mirror)", dict(direction="both")),
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
