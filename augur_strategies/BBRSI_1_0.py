"""
BBRSI 1.0 — TV round-13 port #1: "Bollinger + RSI, Double Strategy (by ChartArt)".

Source: https://www.tradingview.com/script/zopumZ8a-Bollinger-RSI-Double-Strategy-by-ChartArt/
(Pine v2, Jan-2016, 46.7K boosts — the most-boosted strategy script on TradingView).
Ported verbatim for EDGE-LOG challenger round 13 (see TV_SWEEP.md). MPL-2.0 attribution
retained in the port notes; this file is a re-implementation, not a copy of the Pine text.

Published rules (defaults):
  RSI(16) on close with a symmetric band setting 45 (oversold 45 / overbought 100-45=55).
  Bollinger Bands: SMA(20) of close +/- 2.0 x population stdev(20).
  LONG  signal: RSI crosses ABOVE 45  AND close crosses ABOVE the LOWER band (same bar).
  SHORT signal: RSI crosses UNDER 55  AND close crosses UNDER the UPPER band (same bar).
  Entry is a Pine STOP order at the signal bar's band level (long: lower band, short:
  upper band), which is normally already marketable -> fills at the NEXT bar's open;
  if the next bar gaps past the level, it rests at the level for that one bar and is
  cancelled at that bar's close unless the signal re-fires (the script's else-branch
  strategy.cancel). NO stop-loss, NO target, NO session logic: the opposite signal is
  the only exit -- a stop-and-reverse system that is always in the market after the
  first fill (author's own description: "no money management").

Port semantics (house-honest, TV-parity):
  - Signals evaluate on bar t's CLOSE using bar-t indicator values only.
  - Stop-entry fill during bar u = t+1: long fills at open[u] if open[u] >= level,
    else AT the level if high[u] >= level, else the order dies at u's close (unless
    re-signalled at u). Short mirrored. This is exactly TradingView's fill model for
    these orders and never uses information from bar u's close.
  - Position is NET +/-1 contract; an opposite fill books the old trade and opens the
    new one at the same price (Pine strategy.entry reversal, pyramiding 0).
  - direction="long"/"short" = the author's own v1.2 long-only variant generalized:
    the suppressed side's signal becomes a plain market EXIT (next bar's open fill),
    entries only on the allowed side. "both" (default) = the published v1.0.
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

STRATEGY_NAME = 'BBRSI 1.0 · TV#1 Bollinger+RSI double reversal (ChartArt)'
DESCRIPTION = ("Round-13 verbatim port of TradingView's most-boosted strategy: RSI(16) "
               "45/55 cross + close re-crossing the 2-sigma BB(20) band, stop-and-reverse, "
               "no stops/targets. Stop-entry fills at next open (TV parity), roll-seam "
               "guarded, multi-day holds.")

_AUGUR_MARKET = {"instrument": "NQ", "timeframe": "5m"}
# Round-13 challenger family (TV top-boosts sweep) — not a fork of any house family.

DEFAULT_PARAMS = {
    "rsi_len": {
        "default": 16, "min": 4, "max": 40, "step": 1, "type": "int",
        "label": "RSI period",
        "tooltip": "Published default 16 (author deliberately uses a slower-than-14 RSI).",
    },
    "rsi_band": {
        "default": 45, "min": 20, "max": 50, "step": 1, "type": "int",
        "label": "RSI band (oversold = band, overbought = 100-band)",
        "tooltip": "Published default 45 -> long trigger at 45, short trigger at 55.",
    },
    "bb_len": {
        "default": 20, "min": 5, "max": 60, "step": 1, "type": "int",
        "label": "Bollinger SMA length",
        "tooltip": "Published default 20.",
    },
    "bb_mult": {
        "default": 2.0, "min": 0.5, "max": 4.0, "step": 0.25, "type": "float",
        "label": "Bollinger stdev multiplier",
        "tooltip": "Published default 2.0 (population stdev, Pine parity).",
    },
    "direction": {
        "default": "both", "type": "str",
        "options": ["both", "long", "short"],
        "label": "Trade direction",
        "tooltip": "both = published v1.0 stop-and-reverse. long = author's v1.2-style "
                   "long-only (short signal just exits at the next open). short = mirror.",
    },
    "entry_mode": {
        "default": "stop", "type": "str",
        "options": ["stop", "next_open"],
        "label": "Entry fill model",
        "tooltip": "stop = TV-parity stop order at the band level (published). "
                   "next_open = plain market fill at the next bar's open — robustness "
                   "read that removes the band-level fill nuance.",
    },
}

PARAM_GRID_PRESETS = {
    "Short  (published defaults)": {
        "rsi_len": [16], "rsi_band": [45], "bb_len": [20], "bb_mult": [2.0],
        "direction": ["both"], "entry_mode": ["stop"],
    },
    # Pre-registered round-13 refinement grid (author knobs only; TV_SWEEP.md 13.1):
    "Medium (author-knob grid)": {
        "rsi_len": [8, 16, 24], "rsi_band": [40, 45, 50],
        "bb_len": [20], "bb_mult": [1.5, 2.0, 2.5],
        "direction": ["both", "long"], "entry_mode": ["stop"],
    },
    "Long   (adds bb_len + fill robustness)": {
        "rsi_len": [8, 16, 24], "rsi_band": [35, 40, 45, 50],
        "bb_len": [14, 20, 26], "bb_mult": [1.5, 2.0, 2.5],
        "direction": ["both", "long"], "entry_mode": ["stop", "next_open"],
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
    rsi_len: int = 16, rsi_band: int = 45,
    bb_len: int = 20, bb_mult: float = 2.0,
    direction: str = "both", entry_mode: str = "stop",
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

    rsi_len = int(rsi_len); rsi_band = int(rsi_band)
    bb_len = int(bb_len); bb_mult = float(bb_mult)
    os_lvl = float(rsi_band); ob_lvl = float(100 - rsi_band)

    # ── indicators (Pine parity) ──────────────────────────────────────────────
    vrsi = _wilder_rsi(c, rsi_len)
    s = pd.Series(c)
    basis = s.rolling(bb_len).mean()
    dev = bb_mult * s.rolling(bb_len).std(ddof=0)          # Pine stdev = population
    upper = (basis + dev).to_numpy()
    lower = (basis - dev).to_numpy()

    # crossover(a, K): a[t] > K and a[t-1] <= K   (Pine definition)
    xo_rsi = np.zeros(n, bool); xu_rsi = np.zeros(n, bool)
    xo_bb  = np.zeros(n, bool); xu_bb  = np.zeros(n, bool)
    xo_rsi[1:] = (vrsi[1:] > os_lvl) & (vrsi[:-1] <= os_lvl)
    xu_rsi[1:] = (vrsi[1:] < ob_lvl) & (vrsi[:-1] >= ob_lvl)
    with np.errstate(invalid="ignore"):
        xo_bb[1:] = (c[1:] > lower[1:]) & (c[:-1] <= lower[:-1])
        xu_bb[1:] = (c[1:] < upper[1:]) & (c[:-1] >= upper[:-1])
    long_sig = xo_rsi & xo_bb
    short_sig = xu_rsi & xu_bb

    warm = max(bb_len + 1, rsi_len * 6, 60)
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
    pending = None            # (side, level_or_None)  level None => market @ open
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

        # 1) pending order fill attempt, intrabar u (order was placed at u-1's close)
        if pending is not None:
            side, lvl = pending
            fill = None
            if lvl is None:
                fill = o[u]
            elif side > 0:
                if o[u] >= lvl:
                    fill = o[u]
                elif h[u] >= lvl:
                    fill = lvl
            else:
                if o[u] <= lvl:
                    fill = o[u]
                elif l[u] <= lvl:
                    fill = lvl
            if fill is not None and di not in blocked_days:
                if side == 0:                          # market exit (long/short-only mode)
                    if pos != 0:
                        _book(u, fill, pos, entry_px, entry_bar)
                        pos = 0
                elif pos == 0:
                    pos = side; entry_px = fill; entry_bar = u
                elif pos != side:                      # reversal: book old, open new
                    _book(u, fill, pos, entry_px, entry_bar)
                    pos = side; entry_px = fill; entry_bar = u
                pending = None
            elif fill is not None:
                pending = None                          # fill suppressed on blocked day
            # unfilled resting order: dies below unless re-signalled this bar

        # 2) signal evaluation at u's close -> replace/cancel pending
        ls, ss = long_sig[u], short_sig[u]
        new_pending = None
        if ls and allow_long and pos <= 0:
            new_pending = (1, lower[u] if entry_mode == "stop" else None)
        elif ss and allow_short and pos >= 0:
            new_pending = (-1, upper[u] if entry_mode == "stop" else None)
        elif ls and not allow_long and pos < 0:
            new_pending = (0, None)                    # short-only mode: long sig = exit
        elif ss and not allow_short and pos > 0:
            new_pending = (0, None)                    # long-only mode: short sig = exit
        pending = new_pending if new_pending is not None else None

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
# Smoke test — tiny window, sane-output check. Run: python augur_strategies/BBRSI_1_0.py
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

    print("BBRSI 1.0 smoke test — NQ 5m RTH, 2015-2017 (%d bars, %d sessions)"
          % (len(df), len(set(day_id))))
    print("%-52s %7s %5s %6s %13s %11s" % ("config", "trades", "WR%", "PF", "net $", "maxDD$ (gross)"))
    print("-" * 100)
    for label, kw in [
        ("published: 16/45, BB 20x2.0, both, stop-entry", dict()),
        ("published, next_open fills (robustness)", dict(entry_mode="next_open")),
        ("long-only variant (author v1.2 style)", dict(direction="long")),
        ("faster RSI 8 / band 40 (grid corner)", dict(rsi_len=8, rsi_band=40)),
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
