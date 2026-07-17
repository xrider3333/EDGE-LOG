"""
ICHIHULL 1.0 — TV round-13 port #11: "Ichimoku + Daily-Candle_X + HULL-MA_X + MacD" by
SeaSide420.

Source: https://www.tradingview.com/script/RJBjyl2W-Ichimoku-Daily-Candle-X-HULL-MA-X-MacD/
(Pine v2, 10.3K boosts). Ported for EDGE-LOG challenger round 13 (see TV_SWEEP.md). This
file is a re-implementation of the published logic, not a copy of the Pine text.

Published rules (defaults):
  Hull pair: keh=14. n1 = WMA(2*WMA(close,round(keh/2)) - WMA(close,keh), round(sqrt(keh)))
  -- a Hull MA. n2 is the SAME construct built from close[1] (i.e. computed one bar in the
  past), which is algebraically identical to n1 shifted forward one bar: n2[t] = n1[t-1].
  Ported as a literal shift -- this is not one of the two honesty deviations below, just an
  algebraic simplification of exactly what the Pine computes (diff1 is diff evaluated on
  close[1], so wma(diff1, sqn) at bar t equals wma(diff, sqn) at bar t-1).
  Ichimoku: donchian(len) = (lowest(low,len)+highest(high,len))/2. conversionLine=
  donchian(9), baseLine=donchian(26), leadLine1=avg(conversionLine,baseLine), leadLine2=
  donchian(52) -- compared UNDISPLACED (the `displacement=26` input only offsets the
  on-chart cloud plot; it is never used in longCondition/shortCondition/closelong/
  closeshort). Ported literally, no displacement in the trading logic.
  MACD: MACD=EMA(close,12)-EMA(close,26), aMACD=EMA(MACD,9). Fixed lengths -- Pine inputs,
  but not part of the author's published knob set (only keh/dt/SL/TP are "the" settings).
  LONG entry:  n1>n2 AND flat AND confidence>dt AND close>n2 AND leadLine1>leadLine2 AND
               open<close (green bar) AND MACD>aMACD.
  SHORT entry: n1<n2 AND flat AND confidence<dt AND close<n2 AND leadLine1<leadLine2 AND
               open>close (red bar) AND MACD<aMACD.
  (dt is the SAME threshold on both sides -- long needs confidence ABOVE +0.001, short
  needs confidence BELOW +0.001, so with the published default the short trigger is
  structurally easier to satisfy than the long one. Ported literally; it's what shipped.)
  EXIT: closelong = (n1<n2 AND close<n2 AND confidence<dt) OR openprofit<SL OR
  openprofit>TP -> strategy.close("Long"). closeshort is the mirror -> strategy.close
  ("Short"). No stop-and-reverse: strategy.entry requires opentrades<1 (flat), so the ONLY
  way out of a position is one of the exit conditions above -- entries and exits are
  disjoint order streams, never competing for the same bar's order slot.

HONESTY DEVIATIONS (both make our numbers MORE CONSERVATIVE than a naive Pine replay --
flagged prominently per round-13 convention):

  #1 -- confidence uses YESTERDAY vs DAY-BEFORE-YESTERDAY closes, not "today vs yesterday".
  The Pine line is:
      confidence = (security(tickerid,'D',close) - security(tickerid,'D',close[1]))
                   / security(tickerid,'D',close[1])
  On an intraday chart, Pine v2's security() call (no barmerge.lookahead_off, no
  gaps=barmerge.gaps_off -- both unavailable/undefaulted in this v2 script) resolves the
  'D'-context close[0] to the CURRENT, still-forming daily bar's latest intraday trade --
  it updates all day and is only "final" retroactively once the session ends. Every
  intraday bar in the published script sees a daily-change ratio computed in part from a
  close that hasn't happened yet: textbook look-ahead / repaint. We refuse to port that.
  Instead: confidence for every bar of session D = (close of session D-1 - close of
  session D-2) / close of session D-2 -- constant across all of session D's bars, built
  only from sessions that had FULLY CLOSED before session D opened.

  #2 -- $ stop/target checked at bar CLOSE, filled at the NEXT bar's OPEN, not intrabar.
  The strategy declares calc_on_every_tick=true, so real Pine checks strategy.openprofit
  continuously and strategy.close() can fire (and fill) intrabar, the instant SL/TP is
  touched. We only have OHLC bars, not a tick feed. We compute openprofit = (close-entry)
  * side * usd_mult once per bar at that bar's CLOSE and, if it breaches SL or TP, queue a
  market exit that fills at the FOLLOWING bar's OPEN. That can only be as-good-or-worse
  than a real intrabar fill, never better -- SL/TP outcomes here are conservative relative
  to the published script.

Other port semantics:
  - Every fill (entry or exit, signal-based or $-based) is a plain market order evaluated
    at bar close, filled at the NEXT bar's open -- no resting stop levels (contrast
    BBRSI_1_0's stop-entry model; this Pine script uses strategy.entry/strategy.close, not
    a stop-priced strategy.entry).
  - pyramiding=0, one position at a time; a new position can only be queued while flat.
    NOT stop-and-reverse (contrast HULL_1_0/BBRSI_1_0) -- the only way out is an exit
    condition above; entries and exits never compete for the same bar's order slot.
  - direction="long"/"short" suppresses entries on the other side entirely; that side's
    exit logic is then moot since it can never hold a position to exit. "both" (default)
    is the published behaviour.
  - Multi-day holds are intrinsic; positions are FORCE-FLATTENED at the close of the day
    before each detected NOADJ quarterly roll seam and no fill may occur on that day (same
    guard + calibration as TTIBS_1_0.detect_roll_seams, reused verbatim). A trade still
    open when the loaded data ends is DROPPED, never truncated (lockbox-honest).
  - PNL = points only, costs applied downstream by the engine (0.533 pts/RT NQ, 0.363 ES),
    same as every library strategy.

Needs day_id AND index (roll-seam calendar + confidence's session boundaries); returns
None without.
"""
import math

import numpy as np
import pandas as pd

STRATEGY_NAME = 'ICHIHULL 1.0 · TV#11 Ichimoku+Hull+MACD confluence (SeaSide420)'
DESCRIPTION = ("Round-13 port of a 6-condition confluence: Hull-MA pair cross, Ichimoku "
               "leadLine1/leadLine2 (undisplaced), MACD(12,26,9) direction, candle color, "
               "and a daily-change confidence filter. Two honesty deviations from the "
               "published Pine (both conservative): confidence uses completed sessions "
               "only (no repaint), $ stop/target fills next open (no intrabar). Roll-seam "
               "guarded, multi-day holds, not stop-and-reverse.")

_AUGUR_MARKET = {"instrument": "NQ", "timeframe": "5m"}
# Round-13 challenger family (TV top-boosts sweep) — not a fork of any house family.

DEFAULT_PARAMS = {
    "keh": {
        "default": 14, "min": 4, "max": 60, "step": 1, "type": "int",
        "label": "Double-Hull length (keh)",
        "tooltip": "Published default 14. n1 = WMA(2*WMA(close,round(keh/2)) - "
                   "WMA(close,keh), round(sqrt(keh))) -- a Hull MA. n2 is the identical "
                   "construct delayed one bar (n2[t] = n1[t-1]).",
    },
    "dt": {
        "default": 0.0010, "min": 0.0, "max": 0.0100, "step": 0.0001, "type": "float",
        "label": "Decision threshold (daily-change confidence)",
        "tooltip": "Published default 0.0010. Long needs confidence > dt, short needs "
                   "confidence < dt (SAME dt both sides -- with dt=+0.001 the short "
                   "trigger is easier to satisfy than the long trigger; ported literally, "
                   "it's what the author shipped).",
    },
    "sl_usd": {
        "default": -500.0, "min": -5000.0, "max": 0.0, "step": 50.0, "type": "float",
        "label": "Stop loss $ (open-trade)",
        "tooltip": "Published default -$500. Exit next open once (close-entry)*side*"
                   "usd_mult falls below this (evaluated at bar close -- see HONESTY "
                   "DEVIATION #2 in the module docstring).",
    },
    "tp_usd": {
        "default": 25000.0, "min": 0.0, "max": 100000.0, "step": 500.0, "type": "float",
        "label": "Target $ (open-trade)",
        "tooltip": "Published default $25,000. Exit next open once open-trade profit "
                   "exceeds this (evaluated at bar close).",
    },
    "usd_mult": {
        "default": 20.0, "min": 1.0, "max": 100.0, "step": 1.0, "type": "float",
        "label": "$ per point (instrument multiplier)",
        "tooltip": "Default 20.0 = NQ big contract. Pass 50.0 for ES runs (driver "
                   "override) so the $-based SL/TP scale to the instrument under test.",
    },
    "conv_len": {
        "default": 9, "min": 2, "max": 60, "step": 1, "type": "int",
        "label": "Ichimoku conversion-line periods",
        "tooltip": "Published default 9.",
    },
    "base_len": {
        "default": 26, "min": 5, "max": 120, "step": 1, "type": "int",
        "label": "Ichimoku base-line periods",
        "tooltip": "Published default 26.",
    },
    "span2_len": {
        "default": 52, "min": 10, "max": 200, "step": 1, "type": "int",
        "label": "Ichimoku lagging-span-2 (leadLine2) periods",
        "tooltip": "Published default 52.",
    },
    "direction": {
        "default": "both", "type": "str",
        "options": ["both", "long", "short"],
        "label": "Trade direction",
        "tooltip": "both = published (the v2 script trades either side). long/short "
                   "suppress entries on the other side; that side's exit logic is then "
                   "moot since it can never hold a position.",
    },
}

PARAM_GRID_PRESETS = {
    "Short  (published defaults)": {
        "keh": [14], "dt": [0.0010], "sl_usd": [-500.0], "tp_usd": [25000.0],
        "usd_mult": [20.0], "conv_len": [9], "base_len": [26], "span2_len": [52],
        "direction": ["both"],
    },
    # Pre-registered round-13 refinement grid (author knobs only; TV_SWEEP.md 13.1):
    "Medium (author-knob grid)": {
        "keh": [10, 14, 21], "dt": [0.0, 0.0010, 0.0025],
        "sl_usd": [-500.0], "tp_usd": [25000.0], "usd_mult": [20.0],
        "conv_len": [9], "base_len": [26], "span2_len": [52],
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


def _wma(x, length):
    """Pine wma(): linearly-weighted MA, weights 1..length (the newest bar in the
    window gets weight `length`, the oldest gets weight 1). Convolution-based -- fast
    on large bar arrays (same implementation as HULL_1_0._wma)."""
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


def _pine_round(x):
    """Pine round(): half rounds away from zero (Python's round() is banker's
    rounding and would silently diverge on exact .5 ties -- e.g. keh=21 makes
    keh/2==10.5, where Pine round(10.5)=11 but Python round(10.5)=10). Only ever
    called here on half-lengths and sqrt() results, but kept sign-correct anyway."""
    return int(math.floor(x + 0.5)) if x >= 0 else -int(math.floor(-x + 0.5))


def _donchian(h, l, length):
    """Pine donchian(len) = avg(lowest(len), highest(len)); the single-arg forms
    default to low/high respectively: (lowest(low,len)+highest(high,len))/2."""
    length = int(length)
    lo = pd.Series(l).rolling(length).min()
    hi = pd.Series(h).rolling(length).max()
    return ((lo + hi) / 2.0).to_numpy()


def _build_indicators(o, h, l, c, did, keh, conv_len, base_len, span2_len):
    """All non-price-action indicator series, shared verbatim between run_backtest and
    the __main__ smoke test's per-condition diagnostic (single source of truth)."""
    n = len(c)

    # Hull pair: n1 = HMA(close, keh); n2[t] = n1[t-1] (see module docstring).
    half_len = max(1, _pine_round(keh / 2.0))
    sq_len = max(1, _pine_round(math.sqrt(keh)))
    diff = 2.0 * _wma(c, half_len) - _wma(c, keh)
    n1 = _wma(diff, sq_len)
    n2 = np.full(n, np.nan)
    n2[1:] = n1[:-1]

    # Ichimoku (undisplaced compare).
    conv_line = _donchian(h, l, conv_len)
    base_line = _donchian(h, l, base_len)
    lead1 = (conv_line + base_line) / 2.0
    lead2 = _donchian(h, l, span2_len)

    # MACD(12,26,9) -- fixed lengths, ema() has no leading-NaN warmup for a full src.
    ema_fast = pd.Series(c).ewm(span=12, adjust=False).mean().to_numpy()
    ema_slow = pd.Series(c).ewm(span=26, adjust=False).mean().to_numpy()
    macd = ema_fast - ema_slow
    amacd = pd.Series(macd).ewm(span=9, adjust=False).mean().to_numpy()

    # confidence (HONESTY DEVIATION #1): last two COMPLETED sessions' closes, constant
    # across a session's bars.
    bounds = _session_bounds(did, n)
    day_close = np.array([c[b - 1] for a, b in bounds])
    n_days = len(bounds)
    conf_by_day = np.full(n_days, np.nan)
    with np.errstate(invalid="ignore", divide="ignore"):
        conf_by_day[2:] = (day_close[1:-1] - day_close[:-2]) / day_close[:-2]
    day_of_bar = np.empty(n, int)
    last_bar_of_day = {}
    for di, (a, b) in enumerate(bounds):
        day_of_bar[a:b] = di
        last_bar_of_day[di] = b - 1
    confidence = conf_by_day[day_of_bar]

    return dict(n1=n1, n2=n2, lead1=lead1, lead2=lead2, macd=macd, amacd=amacd,
                confidence=confidence, bounds=bounds, day_of_bar=day_of_bar,
                last_bar_of_day=last_bar_of_day)


def run_backtest(
    opens, highs, lows, closes,
    volumes=None, day_id=None, index=None,
    keh: int = 14, dt: float = 0.0010,
    sl_usd: float = -500.0, tp_usd: float = 25000.0, usd_mult: float = 20.0,
    conv_len: int = 9, base_len: int = 26, span2_len: int = 52,
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
        return None                    # needs real dates (roll seams / daily confidence)

    keh = int(keh); dt_thr = float(dt)
    sl_usd = float(sl_usd); tp_usd = float(tp_usd); usd_mult = float(usd_mult)
    conv_len = int(conv_len); base_len = int(base_len); span2_len = int(span2_len)
    direction = str(direction)
    if keh < 2 or conv_len < 1 or base_len < 1 or span2_len < 1:
        return None

    # ── indicators (Pine parity) ────────────────────────────────────────────────
    ind = _build_indicators(o, h, l, c, did, keh, conv_len, base_len, span2_len)
    n1, n2 = ind["n1"], ind["n2"]
    lead1, lead2 = ind["lead1"], ind["lead2"]
    macd, amacd = ind["macd"], ind["amacd"]
    confidence = ind["confidence"]
    bounds = ind["bounds"]; day_of_bar = ind["day_of_bar"]
    last_bar_of_day = ind["last_bar_of_day"]

    with np.errstate(invalid="ignore"):
        green = o < c
        red = o > c
        hull_up = n1 > n2
        hull_dn = n1 < n2
        conf_gt = confidence > dt_thr
        conf_lt = confidence < dt_thr
        close_gt_n2 = c > n2
        close_lt_n2 = c < n2
        lead_up = lead1 > lead2
        lead_dn = lead1 < lead2
        macd_up = macd > amacd
        macd_dn = macd < amacd

        long_entry_sig = hull_up & conf_gt & close_gt_n2 & lead_up & green & macd_up
        short_entry_sig = hull_dn & conf_lt & close_lt_n2 & lead_dn & red & macd_dn
        long_exit_sig = hull_dn & close_lt_n2 & conf_lt
        short_exit_sig = hull_up & close_gt_n2 & conf_gt

    warm = max(160, 60)
    long_entry_sig[:warm] = False
    short_entry_sig[:warm] = False
    long_exit_sig[:warm] = False
    short_exit_sig[:warm] = False

    # ── session / roll-seam scaffolding (identical to BBRSI/HULL/TTIBS) ─────────
    idx = pd.DatetimeIndex(index)
    day_open = np.array([o[a] for a, b in bounds])
    day_close = np.array([c[b - 1] for a, b in bounds])
    day_ts = [idx[a] for a, b in bounds]
    seam_days = set(detect_roll_seams(day_open, day_close, day_ts))
    force_exit_days = {sd - 1 for sd in seam_days if sd - 1 >= 0}   # daily index
    blocked_days = set(force_exit_days)                              # no fills on seam eve

    allow_long = direction in ("both", "long")
    allow_short = direction in ("both", "short")

    # ── event loop ────────────────────────────────────────────────────────────
    pos = 0
    entry_px = 0.0
    entry_bar = -1
    pending = None            # +1 open long / -1 open short / 0 close current / None
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

        # 1) pending order fill, intrabar u (order placed at u-1's close). Plain
        #    market order -> fills at this bar's open unless the day is roll-seam
        #    -eve blocked, in which case it's dropped outright (never delayed).
        if pending is not None:
            if di not in blocked_days:
                fill = o[u]
                if pending == 0:                       # market exit
                    if pos != 0:
                        _book(u, fill, pos, entry_px, entry_bar)
                        pos = 0
                elif pos == 0:                          # market entry (only while flat)
                    pos = pending; entry_px = fill; entry_bar = u
                # pos!=0 and pending!=0: can't happen -- entries only queued while flat
            pending = None

        # 2) signal evaluation at u's close, using pos AFTER this bar's open-fill.
        #    Exits and entries are disjoint: a position can only be exited, a flat
        #    book can only be entered -- never both on the same bar (matches the
        #    Pine's opentrades<1 entry gate; no intrabar tick data to sequence a
        #    same-bar close-then-reopen).
        new_pending = None
        if pos > 0:
            openprofit = (c[u] - entry_px) * usd_mult
            if long_exit_sig[u] or openprofit < sl_usd or openprofit > tp_usd:
                new_pending = 0
        elif pos < 0:
            openprofit = (entry_px - c[u]) * usd_mult
            if short_exit_sig[u] or openprofit < sl_usd or openprofit > tp_usd:
                new_pending = 0
        else:
            if allow_long and long_entry_sig[u]:
                new_pending = 1
            elif allow_short and short_entry_sig[u]:
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
# Smoke test — tiny window, sane-output check. Run: python augur_strategies/ICHIHULL_1_0.py
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import os, sys

    ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    MASTER = os.path.join(ROOT, "augur_uploads", "NOADJ_NQ_5m_RTH.csv")
    MULT, FEE = 20.0, 0.533
    if not os.path.exists(MASTER):
        print("NQ master not found at", MASTER); sys.exit(1)

    # Sanity checks (required) ----------------------------------------------------
    _wma_test = _wma(np.array([1.0, 2.0, 3.0, 4.0, 5.0]), 3)
    _wma_expected = (3 * 1 + 4 * 2 + 5 * 3) / 6.0
    assert abs(_wma_test[-1] - _wma_expected) < 1e-9, (
        "WMA mismatch: got %r, expected %r" % (_wma_test[-1], _wma_expected))
    print("WMA sanity check: WMA([1,2,3,4,5], 3) last = %.6f  (expected %.6f)  OK"
          % (_wma_test[-1], _wma_expected))
    assert _pine_round(10.5) == 11 and _pine_round(2.5) == 3 and _pine_round(7.4) == 7, (
        "pine_round tie-break mismatch (Pine rounds .5 away from zero, not banker's)")
    print("pine_round sanity check: round(10.5)=%d round(2.5)=%d round(7.4)=%d  OK"
          % (_pine_round(10.5), _pine_round(2.5), _pine_round(7.4)))

    df = pd.read_csv(MASTER)
    ts_index = pd.to_datetime(df["time"], unit="s", utc=True).dt.tz_convert("US/Eastern")
    df.index = ts_index
    df = df[(df.index >= pd.Timestamp("2015-01-01", tz="US/Eastern")) &
            (df.index < pd.Timestamp("2018-01-01", tz="US/Eastern"))].sort_index()
    day_id = pd.factorize(pd.Series(df.index).dt.date)[0].astype("int64")

    print("\nICHIHULL 1.0 smoke test — NQ 5m RTH, 2015-2017 (%d bars, %d sessions)"
          % (len(df), len(set(day_id))))
    print("%-52s %7s %5s %6s %13s %11s" % ("config", "trades", "WR%", "PF", "net $", "maxDD$ (gross)"))
    print("-" * 100)
    configs = [
        ("published: both, keh=14, dt=0.0010", dict()),
        ("long-only (direction=long)", dict(direction="long")),
        ("dt=0 (relaxed decision threshold)", dict(dt=0.0)),
        ("keh=21 (odd -> Pine round(10.5)=11 tie-break)", dict(keh=21)),
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

    # Per-condition diagnostic (published params) if the confluence looks too tight --
    # proves the 6-way AND is doing what the docstring says instead of hiding a bug
    # behind "no trades".
    published = results.get("published: both, keh=14, dt=0.0010")
    pub_trades = published["num_trades"] if published else 0
    if pub_trades < 20:
        print("\nPublished config produced %d trades (<20) -- per-condition pass counts, "
              "LONG side, keh=14/dt=0.0010/conv=9/base=26/span2=52:" % pub_trades)
        oo = df["open"].values; cc = df["close"].values
        ind = _build_indicators(df["open"].values, df["high"].values, df["low"].values,
                                 cc, day_id, 14, 9, 26, 52)
        warm = max(160, 60)
        total = len(cc) - warm
        with np.errstate(invalid="ignore"):
            conds = [
                ("1) n1>n2 (hull up)", ind["n1"] > ind["n2"]),
                ("2) confidence>dt (0.0010)", ind["confidence"] > 0.0010),
                ("3) close>n2", cc > ind["n2"]),
                ("4) leadLine1>leadLine2", ind["lead1"] > ind["lead2"]),
                ("5) open<close (green bar)", oo < cc),
                ("6) MACD>aMACD", ind["macd"] > ind["amacd"]),
            ]
            allmask = np.ones(len(cc), bool)
            for cond_label, mask in conds:
                m = mask.copy(); m[:warm] = False
                allmask &= mask
                print("  %-30s %7d   (%5.1f%% of %d evaluable bars)"
                      % (cond_label, int(m.sum()), 100.0 * m.sum() / total, total))
            allmask[:warm] = False
            print("  %-30s %7d   (%5.1f%%)   <- ALL 6 simultaneously (long_entry_sig)"
                  % ("AND (confluence)", int(allmask.sum()), 100.0 * allmask.sum() / total))
