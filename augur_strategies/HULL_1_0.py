"""
HULL 1.0 — TV round-13 port #6: "Hull Suite Strategy" (by DashTrader).

Source: https://www.tradingview.com/script/Q9OQye4C-Hull-Suite-Strategy/
(Pine v4, "Basic Hull Ma Pack" indicator by InSilico, converted to a strategy by
DashTrader; 14.2K boosts). Ported for EDGE-LOG challenger round 13 (see TV_SWEEP.md).
This file is a re-implementation, not a copy of the Pine text.

Published rules (defaults):
  Hull moving average of close, length 55, variant "Hma" (classic Hull MA). Three
  selectable variants, all built from Pine's linearly-weighted wma() and/or ema():
    HMA (src,L)  = wma(2*wma(src, floor(L/2)) - wma(src, L), round(sqrt(L)))
    EHMA(src,L)  = ema(2*ema(src, floor(L/2)) - ema(src, L), round(sqrt(L)))
    THMA(src,L)  called as THMA(src, floor(L/2)) -- i.e. with L' = floor(L/2):
                 = wma(wma(src, floor(L'/3))*3 - wma(src, floor(L'/2)) - wma(src, L'), L')
  (Pine integer division on int inputs truncates -> floor; round(sqrt(55)) = 7.)
  Signal = the Hull line's own 2-bar slope: HULL[t] > HULL[t-2] -> rising,
  HULL[t] < HULL[t-2] -> falling. No band/threshold, no other filter.

  Pine mechanics: strategy.entry("buy") fires every bar while rising, "sell" every bar
  while falling, pyramiding=1, default direction filter = LONG-ONLY via
  strategy.risk.allow_entry_in(). Net effect, implemented here as an explicit state
  machine (equivalent outcome; no need to model Pine's raw order-merge mechanics):
    direction="long"  (published default): rising & pos==0 -> BUY (fills next open);
                       falling & pos==+1 -> SELL to flat (fills next open). No shorts.
    direction="all"                      : always-in flip -- rising & pos<=0 -> go/
                       reverse long at next open; falling & pos>=0 -> go/reverse short.
    direction="short"                    : mirror of "long".
  All fills are plain market orders at the NEXT bar's open (orders placed at the signal
  bar's close); no stop-loss, no target, no session logic -- multi-day holds are
  intrinsic. TradingView's default backtest-date-range inputs (testStartYear/Month/Day
  etc.) and all plot/color/visual inputs (switchColor, candleCol, visualSwitch, band
  transparency, line thickness) are TV-chart boilerplate, not trading rules, and are
  intentionally not ported -- the caller's own data window is the backtest range.

Port semantics (house-honest, TV-parity):
  - Signals evaluate on bar t's CLOSE using bar-t indicator values only (HULL[t] vs
    HULL[t-2], both already-closed bars).
  - Every fill is a plain market order at the very next bar's open -- no level/stop
    check (unlike BBRSI's stop-entry model): a signal at bar t's close always fills at
    bar t+1's open unless that bar falls on a roll-seam-eve blocked day, in which case
    the order is dropped outright (never delayed to a later bar).
  - Position is NET +/-1 or 0; a reversal (direction="all") books the old trade and
    opens the new one at the same fill price (same convention as BBRSI/TTIBS).
  - Multi-day holds are intrinsic; positions are FORCE-FLATTENED at the close of the day
    before each detected NOADJ quarterly roll seam and no fill may occur on that day
    (same guard + calibration as TTIBS_1_0.detect_roll_seams). A trade still open when
    the loaded data ends is DROPPED, never truncated (lockbox-honest).
  - PNL = points only, costs applied downstream by the engine (0.533 pts/RT NQ,
    0.363 ES), same as every library strategy.

Needs day_id AND index (roll-seam calendar + session boundaries); returns None without.
"""
import math

import numpy as np
import pandas as pd

STRATEGY_NAME = 'HULL 1.0 · TV#6 Hull Suite slope flip (DashTrader)'
DESCRIPTION = ("Round-13 port of TradingView's Hull Suite Strategy: a Hull moving "
               "average (Hma/Ehma/Thma variant, length 55 published) whose own 2-bar "
               "slope flip drives entries -- rising = long, falling = short/exit. "
               "Plain market fills at the next open, no stops/targets, roll-seam "
               "guarded, multi-day holds.")

_AUGUR_MARKET = {"instrument": "NQ", "timeframe": "5m"}
# Round-13 challenger family (TV top-boosts sweep) — not a fork of any house family.

DEFAULT_PARAMS = {
    "mode": {
        "default": "Hma", "type": "str",
        "options": ["Hma", "Ehma", "Thma"],
        "label": "Hull variation",
        "tooltip": "Hma = classic Hull MA (published default). Ehma = EMA-based "
                   "variant (smoother, more lag). Thma = triangular Hull variant "
                   "(smoothest, most lag).",
    },
    "length": {
        "default": 55, "min": 5, "max": 300, "step": 1, "type": "int",
        "label": "Hull length",
        "tooltip": "Published default 55 (\"swing entry\"). Author's note: 180-200 "
                   "for a floating support/resistance read instead.",
    },
    "direction": {
        "default": "long", "type": "str",
        "options": ["long", "short", "all"],
        "label": "Trade direction",
        "tooltip": "long = published default (long-only; falling signal just exits "
                   "to flat). short = mirror (short-only). all = always-in "
                   "stop-and-reverse on every slope flip.",
    },
}

PARAM_GRID_PRESETS = {
    "Short  (published defaults)": {
        "mode": ["Hma"], "length": [55], "direction": ["long"],
    },
    # Pre-registered round-13 refinement grid (author knobs only; TV_SWEEP.md 13.1):
    "Medium (author-knob grid)": {
        "mode": ["Hma", "Ehma", "Thma"], "length": [34, 55, 89, 180],
        "direction": ["long", "all"],
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


def _wma(x, length):
    """Pine wma(): linearly-weighted MA, weights 1..length (the newest bar in the
    window gets weight `length`, the oldest gets weight 1). Implemented via
    convolution -- fast on 1M+ bar arrays; pandas .rolling().apply() with a python
    weight loop is far too slow for the challenger sweep's data sizes."""
    x = np.asarray(x, dtype=float)
    n = len(x)
    length = int(length)
    out = np.full(n, np.nan)
    if length <= 0 or n < length:
        return out
    weights = np.arange(length, 0, -1, dtype=float)      # [L, L-1, ..., 1]
    norm = weights.sum()                                 # L*(L+1)/2
    conv = np.convolve(x, weights, mode="valid") / norm
    out[length - 1:] = conv
    return out


def _ema(x, length):
    """Pine ema(): recursive EMA seeded by the first defined src value (alpha =
    2/(length+1)); a plain pandas .ewm(span=length, adjust=False) matches this
    exactly once any leading NaN run (from a nested wma/ema not yet warmed up) is
    trimmed off first -- otherwise pandas' own na-handling doesn't reproduce Pine's
    na(sum[1]) reseed-on-first-valid-bar behaviour."""
    x = np.asarray(x, dtype=float)
    n = len(x)
    length = int(length)
    out = np.full(n, np.nan)
    if length <= 0:
        return out
    finite = np.isfinite(x)
    if not finite.any():
        return out
    start = int(np.argmax(finite))
    seg = x[start:]
    out[start:] = pd.Series(seg).ewm(span=length, adjust=False).mean().to_numpy()
    return out


def _pine_round(x):
    """Pine round(): half rounds away from zero (not Python's banker's rounding).
    Only ever called here on non-negative sqrt() results."""
    return int(math.floor(x + 0.5))


def _hma(src, length):
    half = length // 2                                    # Pine int division
    diff = 2.0 * _wma(src, half) - _wma(src, length)
    k = _pine_round(math.sqrt(length))
    return _wma(diff, k)


def _ehma(src, length):
    half = length // 2
    diff = 2.0 * _ema(src, half) - _ema(src, length)
    k = _pine_round(math.sqrt(length))
    return _ema(diff, k)


def _thma(src, length):
    lp = length // 2                       # Mode() calls THMA(src, length/2)
    diff = 3.0 * _wma(src, lp // 3) - _wma(src, lp // 2) - _wma(src, lp)
    return _wma(diff, lp)


def _hull_ma(mode, src, length):
    if mode == "Hma":
        return _hma(src, length)
    if mode == "Ehma":
        return _ehma(src, length)
    if mode == "Thma":
        return _thma(src, length)
    return np.full(len(src), np.nan)


def run_backtest(
    opens, highs, lows, closes,
    volumes=None, day_id=None, index=None,
    mode: str = "Hma", length: int = 55, direction: str = "long",
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

    mode = str(mode)
    length = int(length)
    direction = str(direction)
    if mode not in ("Hma", "Ehma", "Thma") or length < 3:
        return None

    # ── indicator (Pine parity) ─────────────────────────────────────────────────
    HULL = _hull_ma(mode, c, length)

    rising = np.zeros(n, bool); falling = np.zeros(n, bool)
    with np.errstate(invalid="ignore"):
        rising[2:] = HULL[2:] > HULL[:-2]
        falling[2:] = HULL[2:] < HULL[:-2]

    warm = max(3 * length, 60)
    rising[:warm] = False
    falling[:warm] = False

    # ── session / roll-seam scaffolding (identical to BBRSI/TTIBS) ──────────────
    bounds = _session_bounds(did, n)
    idx = pd.DatetimeIndex(index)
    day_open = np.array([o[a] for a, b in bounds])
    day_close = np.array([c[b - 1] for a, b in bounds])
    day_ts = [idx[a] for a, b in bounds]
    seam_days = set(detect_roll_seams(day_open, day_close, day_ts))
    force_exit_days = {sd - 1 for sd in seam_days if sd - 1 >= 0}   # daily index
    day_of_bar = np.empty(n, int)
    last_bar_of_day = {}
    for di, (a, b) in enumerate(bounds):
        day_of_bar[a:b] = di
        last_bar_of_day[di] = b - 1
    blocked_days = set(force_exit_days)                              # no fills on seam eve

    # ── event loop ─────────────────────────────────────────────────────────────
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
        #    Plain market order -> always fills at this bar's open unless the day
        #    is roll-seam-eve blocked, in which case it is dropped (never delayed).
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
        r, f = rising[u], falling[u]
        new_pending = None
        if direction == "long":
            if r and pos == 0:
                new_pending = 1
            elif f and pos == 1:
                new_pending = 0
        elif direction == "short":
            if f and pos == 0:
                new_pending = -1
            elif r and pos == -1:
                new_pending = 0
        else:  # direction == "all": always-in stop-and-reverse
            if r and pos <= 0:
                new_pending = 1
            elif f and pos >= 0:
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
# Smoke test — tiny window, sane-output check. Run: python augur_strategies/HULL_1_0.py
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import os, sys

    ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    MASTER = os.path.join(ROOT, "augur_uploads", "NOADJ_NQ_5m_RTH.csv")
    MULT, FEE = 20.0, 0.533
    if not os.path.exists(MASTER):
        print("NQ master not found at", MASTER); sys.exit(1)

    # WMA correctness check (required) -------------------------------------------
    _wma_test = _wma(np.array([1.0, 2.0, 3.0, 4.0, 5.0]), 3)
    _wma_expected = (3 * 1 + 4 * 2 + 5 * 3) / 6.0
    assert abs(_wma_test[-1] - _wma_expected) < 1e-9, (
        "WMA mismatch: got %r, expected %r" % (_wma_test[-1], _wma_expected))
    print("WMA sanity check: WMA([1,2,3,4,5], 3) last = %.6f  (expected %.6f)  OK"
          % (_wma_test[-1], _wma_expected))

    df = pd.read_csv(MASTER)
    dt = pd.to_datetime(df["time"], unit="s", utc=True).dt.tz_convert("US/Eastern")
    df.index = dt
    df = df[(df.index >= pd.Timestamp("2015-01-01", tz="US/Eastern")) &
            (df.index < pd.Timestamp("2018-01-01", tz="US/Eastern"))].sort_index()
    day_id = pd.factorize(pd.Series(df.index).dt.date)[0].astype("int64")

    print("\nHULL 1.0 smoke test — NQ 5m RTH, 2015-2017 (%d bars, %d sessions)"
          % (len(df), len(set(day_id))))
    print("%-52s %7s %5s %6s %13s %11s" % ("config", "trades", "WR%", "PF", "net $", "maxDD$ (gross)"))
    print("-" * 100)
    for label, kw in [
        ("published: Hma/55/long", dict(mode="Hma", length=55, direction="long")),
        ("Hma/55/all (always-in flip)", dict(mode="Hma", length=55, direction="all")),
        ("Ehma/55/long", dict(mode="Ehma", length=55, direction="long")),
        ("Hma/180/long (S/R length)", dict(mode="Hma", length=180, direction="long")),
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
