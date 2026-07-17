"""
RSIDIV 1.0 -- TV round-13 port #12: "RSI Divergence Indicator strategy" (by eemani123).

Source: https://www.tradingview.com/script/qSLcZSyw-RSI-Divergence-Indicator-strategy/
(Pine v4, 9.8K boosts). Ported verbatim for EDGE-LOG challenger round 13 (see TV_SWEEP.md).
This file is a re-implementation, not a copy of the Pine text.

Published rules (defaults):
  osc = RSI(close, len=9). A pivot LOW is confirmed lb_right=3 bars after a candidate bar
  whose osc beats (strictly) its lb_left=1 left neighbor AND all lb_right right neighbors;
  a pivot HIGH is the mirror (strict >). Confirmation always lags the actual pivot bar by
  lb_right bars -- Pine's pivotlow/pivothigh cannot know a bar is a pivot until it has that
  many bars of "right shoulder" -- so there is no lookahead.
  Regular bull divergence: at a pivot-low confirmation, osc at the new pivot is HIGHER than
  osc at the PREVIOUS confirmed pivot low (higher low in the oscillator) while price made a
  LOWER low, and bars-since-that-previous-pivot falls in [range_lower, range_upper] =
  [5, 60]. Hidden bull divergence (use_hidden_bull, published on): osc LOWER low + price
  HIGHER low, same range gate -- a continuation signal, not a reversal one.
  Long entry on regular-bull OR hidden-bull, strategy.entry with pyramiding=2 (up to 2
  stacked entries under one order id). The author's default_qty_value=2 (each entry sized
  2 contracts) is NOT replicated -- normalized to 1 contract per entry here, so the net
  position this port can reach is 1 or 2 lots, not 2 or 4 (see max_pyramid).
  Exit (published sl_type="NONE"): crossover(osc, tp_rsi_level=80) OR a regular BEAR
  divergence at a pivot-HIGH confirmation (exact mirror of the bull case: osc lower high +
  price higher high, same range gate) -> strategy.close ALL open lots together.
  Exit (sl_type="PERC"/"ATR"): a ratchet-up trailing stop REPLACES the RSI/divergence exit
  entirely (the Pine script's own if/else -- the two exit branches are mutually exclusive
  on sl_type). trailing_sl[t] = max(low[t] - sl_val[t], trailing_sl[t-1]) while long, reset
  whenever flat; sl_val = close[t]*stop_loss/100 for PERC, or stop_loss*ATR(atr_length) for
  ATR. Exit fires on crossunder(close, trailing_sl) -> close ALL.
  QUIRK (ported literally): the Pine script declares a separate "atrMultiplier" input
  (default 3.5) but never references it in the sl_val formula -- the "Stop Loss%" input
  (stop_loss, default 5) silently doubles as the ATR multiplier in ATR mode. atrMultiplier
  is dead code in the original and is not exposed as a param here.
  Longs only -- the published script has no short side at all, so there is no direction
  knob in this port (the one round-13 file without one, by design).
  plotBull / plotBear (regular divergence display toggles) are published-default TRUE and
  gate the regular-divergence entry/exit paths in the original script; they are hardcoded
  on here (not exposed) since disabling them isn't a meaningful "author knob" -- only
  plotHiddenBull is exposed, as use_hidden_bull. plotHiddenBear is cosmetic only (feeds no
  strategy.entry/close in the Pine) and is omitted entirely.

Port semantics (house-honest, TV-parity):
  - Pivots, valuewhen(cond, source, 1) [previous-pivot lookup] and barssince(cond[1])
    [in-range gate] are reproduced with explicit state tracking (prev_pl / prev_ph below)
    rather than Pine's built-ins, but match their bar-for-bar semantics exactly: "the
    previous CONFIRMED pivot before this one," and "bars between that previous pivot's
    confirmation and the bar just before this one."
  - Every fill (entry AND exit, in every sl_type mode) is a plain next-bar-open market
    fill: a signal evaluated at bar t's close fills at bar t+1's open. There is no
    intrabar stop-level price check anywhere in this script (unlike BBRSI's stop-entry
    model) -- Pine's strategy.entry/strategy.close here are both ordinary market orders.
  - On the rare bar where a fresh bull-pivot entry signal and an exit signal (RSI
    take-profit cross, or a trailing-stop crossunder) are BOTH queued from the same prior
    bar, this port resolves the EXIT first, then the entry: the exit closes an unrelated,
    already-open position while the entry is a brand-new signal, so keeping the new lot
    open (rather than having it same-bar-closed by the old position's exit) is the more
    sensible reading. Regular bear divergence can never coincide with a bull signal on the
    same bar (pivot-low and pivot-high masks are mutually exclusive by construction, same
    osc series/offset), so this ordering only matters for the RSI-cross / trailing-stop
    exit paths. A documented judgment call, not an inference from Pine's fill engine.
  - Multi-day holds are intrinsic; positions are FORCE-FLATTENED (all open lots) at the
    close of the day before each detected NOADJ quarterly roll seam, and no fill may occur
    on that day (same guard + calibration as TTIBS_1_0.detect_roll_seams). A trade still
    open when the loaded data ends is DROPPED, never truncated (lockbox-honest).
  - PNL = points only, costs applied downstream by the engine (0.533 pts/RT NQ, 0.363 ES),
    same as every library strategy. A 2-lot exit books 2 trade tuples sharing one exit bar
    (entry_bar, exit_bar, pnl_pts, side=1, entry_px, exit_px) -- one tuple per lot.

Needs day_id AND index (roll-seam calendar + session boundaries); returns None without.
"""
import numpy as np
import pandas as pd

STRATEGY_NAME = 'RSIDIV 1.0 · TV#12 RSI divergence long w/ pyramiding (eemani123)'
DESCRIPTION = ("Round-13 verbatim port of TradingView's RSI Divergence Indicator strategy: "
               "RSI(9) pivot-confirmed regular/hidden bull divergence entries (pyramiding "
               "up to 2 lots), exit on RSI take-profit cross or bear divergence -- or an "
               "optional ATR/percent trailing stop that replaces both exits entirely. "
               "Next-bar-open market fills throughout, roll-seam guarded, multi-day holds, "
               "longs only.")

_AUGUR_MARKET = {"instrument": "NQ", "timeframe": "5m"}
# Round-13 challenger family (TV top-boosts sweep) — not a fork of any house family.

DEFAULT_PARAMS = {
    "rsi_len": {
        "default": 9, "min": 2, "max": 30, "step": 1, "type": "int",
        "label": "RSI period",
        "tooltip": "Published default 9 (author's own GOOGL/SPY notes also cite 5 and 8).",
    },
    "lb_left": {
        "default": 1, "min": 1, "max": 5, "step": 1, "type": "int",
        "label": "Pivot lookback left",
        "tooltip": "Published default 1 -- bars to the left a pivot candidate must beat.",
    },
    "lb_right": {
        "default": 3, "min": 1, "max": 10, "step": 1, "type": "int",
        "label": "Pivot lookback right",
        "tooltip": "Published default 3 -- also the confirmation delay: a pivot at bar p "
                   "is only known at bar p+lb_right (no lookahead).",
    },
    "tp_rsi_level": {
        "default": 80, "min": 70, "max": 95, "step": 1, "type": "int",
        "label": "Take-profit RSI level",
        "tooltip": "Published default 80 (author's own input has minval=70). Long exits "
                   "on crossover(RSI, level) when sl_type=NONE.",
    },
    "range_lower": {
        "default": 5, "min": 1, "max": 30, "step": 1, "type": "int",
        "label": "Divergence range -- min bars",
        "tooltip": "Published default 5 -- minimum bars-since-previous-pivot for a "
                   "divergence to qualify.",
    },
    "range_upper": {
        "default": 60, "min": 20, "max": 150, "step": 1, "type": "int",
        "label": "Divergence range -- max bars",
        "tooltip": "Published default 60 -- maximum bars-since-previous-pivot.",
    },
    "use_hidden_bull": {
        "default": True, "type": "bool",
        "label": "Include hidden bullish divergence",
        "tooltip": "Published default true (plotHiddenBull). Adds continuation-style "
                   "entries (osc lower low, price higher low) alongside regular bull.",
    },
    "sl_type": {
        "default": "NONE", "type": "str",
        "options": ["NONE", "PERC", "ATR"],
        "label": "Trailing stop-loss type",
        "tooltip": "Published default NONE (exit only on RSI take-profit / bear "
                   "divergence). PERC/ATR add a ratchet-up trailing stop that REPLACES "
                   "the RSI/divergence exit entirely (the Pine script's own if/else).",
    },
    "stop_loss": {
        "default": 5.0, "min": 1.0, "max": 20.0, "step": 0.5, "type": "float",
        "label": "Stop loss % (or ATR multiplier)",
        "tooltip": "Published default 5. PERC mode: close*stop_loss/100 below price. ATR "
                   "mode: this SAME number multiplies ATR (the Pine script's own "
                   "'atrMultiplier' input is declared but never actually used in the "
                   "sl_val formula -- stopLoss silently doubles as the ATR multiplier; "
                   "ported literally, quirk and all).",
    },
    "atr_length": {
        "default": 14, "min": 5, "max": 50, "step": 1, "type": "int",
        "label": "ATR length (trailing-stop ATR mode)",
        "tooltip": "Published default 14. Only used when sl_type=ATR.",
    },
    "max_pyramid": {
        "default": 2, "min": 1, "max": 4, "step": 1, "type": "int",
        "label": "Max stacked entries",
        "tooltip": "Published strategy() pyramiding=2. Each entry is normalized to 1 "
                   "contract in this port (author's default_qty_value=2 per entry is not "
                   "replicated -- see file docstring); net position is 1..max_pyramid lots.",
    },
}

PARAM_GRID_PRESETS = {
    "Short  (published defaults)": {
        "rsi_len": [9], "lb_left": [1], "lb_right": [3], "tp_rsi_level": [80],
        "range_lower": [5], "range_upper": [60], "use_hidden_bull": [True],
        "sl_type": ["NONE"], "stop_loss": [5.0], "atr_length": [14], "max_pyramid": [2],
    },
    # Pre-registered round-13 refinement grid (author knobs only; TV_SWEEP.md 13.12) --
    # the script's own GOOGL example cited rsi_len 5 / take-profit 75 as a strong corner.
    "Medium (author-knob grid)": {
        "rsi_len": [5, 9], "lb_left": [1], "lb_right": [3],
        "tp_rsi_level": [75, 80], "range_lower": [5], "range_upper": [60],
        "use_hidden_bull": [True], "sl_type": ["NONE", "PERC"], "stop_loss": [5.0],
        "atr_length": [14], "max_pyramid": [1, 2],
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


def _wilder_atr(high, low, close, length):
    """Pine atr(): rma(tr, length), tr = max(h-l, |h-c[1]|, |l-c[1]|). Same ewm-rma
    convention as _wilder_rsi. Bar 0 has no prior close; falls back to h-l (this is deep
    in the warm-up window and never affects a live signal)."""
    h = np.asarray(high, float); l = np.asarray(low, float); c = np.asarray(close, float)
    prev_c = np.empty_like(c); prev_c[0] = np.nan; prev_c[1:] = c[:-1]
    tr = np.maximum(h - l, np.maximum(np.abs(h - prev_c), np.abs(l - prev_c)))
    tr[0] = h[0] - l[0]
    return pd.Series(tr).ewm(alpha=1.0 / length, adjust=False).mean().to_numpy()


def _pivot_mask(osc, lb_left, lb_right, is_low):
    """bar p is a pivot (low if is_low else high) when osc[p] strictly beats every one of
    the lb_left bars to its left AND every one of the lb_right bars to its right -- Pine's
    own pivotlow()/pivothigh() definition. Returned mask is indexed by the RAW pivot bar p
    (the caller shifts it forward by lb_right to get the confirmation-bar index, since
    Pine cannot know bar p is a pivot until lb_right bars later)."""
    n = len(osc)
    ok = np.ones(n, dtype=bool)
    with np.errstate(invalid="ignore"):
        for k in range(1, lb_left + 1):
            cmp = np.full(n, np.nan)
            cmp[k:] = osc[:n - k]                       # cmp[p] = osc[p-k]
            ok &= (osc < cmp) if is_low else (osc > cmp)
        for k in range(1, lb_right + 1):
            cmp = np.full(n, np.nan)
            cmp[:n - k] = osc[k:]                        # cmp[p] = osc[p+k]
            ok &= (osc < cmp) if is_low else (osc > cmp)
    ok[:lb_left] = False
    if lb_right > 0:
        ok[n - lb_right:] = False
    return ok


def run_backtest(
    opens, highs, lows, closes,
    volumes=None, day_id=None, index=None,
    rsi_len: int = 9, lb_left: int = 1, lb_right: int = 3,
    tp_rsi_level: float = 80, range_lower: int = 5, range_upper: int = 60,
    use_hidden_bull: bool = True,
    sl_type: str = "NONE", stop_loss: float = 5.0, atr_length: int = 14,
    max_pyramid: int = 2,
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

    rsi_len = int(rsi_len); lb_left = int(lb_left); lb_right = int(lb_right)
    tp_rsi_level = float(tp_rsi_level)
    range_lower = int(range_lower); range_upper = int(range_upper)
    use_hidden_bull = bool(use_hidden_bull)
    sl_type = str(sl_type).upper()
    stop_loss = float(stop_loss); atr_length = int(atr_length)
    max_pyramid = max(1, int(max_pyramid))

    # ── indicators (Pine parity) ──────────────────────────────────────────────
    osc = _wilder_rsi(c, rsi_len)

    is_pl = _pivot_mask(osc, lb_left, lb_right, is_low=True)
    is_ph = _pivot_mask(osc, lb_left, lb_right, is_low=False)
    pl_found = np.zeros(n, dtype=bool)
    ph_found = np.zeros(n, dtype=bool)
    if lb_right < n:
        pl_found[lb_right:] = is_pl[:n - lb_right]
        ph_found[lb_right:] = is_ph[:n - lb_right]

    tp_cross = np.zeros(n, dtype=bool)
    with np.errstate(invalid="ignore"):
        tp_cross[1:] = (osc[1:] > tp_rsi_level) & (osc[:-1] <= tp_rsi_level)

    if sl_type == "ATR":
        sl_val = stop_loss * _wilder_atr(h, l, c, atr_length)
    elif sl_type == "PERC":
        sl_val = c * stop_loss / 100.0
    else:
        sl_val = np.zeros(n)

    warm = max(10 * rsi_len, 80)

    # ── session / roll-seam scaffolding ──────────────────────────────────────
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

    # ── event loop ────────────────────────────────────────────────────────────
    lots = []                    # open long lots: [[entry_bar, entry_px], ...]
    prev_pl = None                # (confirm_bar, osc_at_pivot, low_at_pivot)
    prev_ph = None                # (confirm_bar, osc_at_pivot, high_at_pivot)
    trailing_sl_prev = None
    pending_entry = None          # pivot-info dict, or None
    pending_exit = False
    pnl_list, trade_log, pivot_log = [], [], {}

    def _book(exit_bar_i, exit_price, ep, eb):
        pnl = exit_price - ep
        pnl_list.append(pnl)
        if return_trades:
            trade_log.append((int(eb), int(exit_bar_i), float(pnl), 1,
                              float(ep), float(exit_price)))

    for u in range(warm, n):
        if _stop_event is not None and _stop_event.is_set():
            break
        di = day_of_bar[u]
        blocked = di in blocked_days

        # 1) fills queued at u-1's close, applied at u's open. If both an exit and a
        #    fresh entry are pending (rare coincidence), close first then open -- see
        #    docstring judgment-call note. A blocked (seam-eve) day kills the order
        #    outright rather than deferring it (there is no resting/stop order in this
        #    script -- every fill is an unconditional next-open market order).
        if not blocked:
            if pending_exit and lots:
                for eb, ep in lots:
                    _book(u, o[u], ep, eb)
                lots = []
            if pending_entry is not None and len(lots) < max_pyramid:
                lots.append([u, o[u]])
                if return_trades:
                    pivot_log[u] = pending_entry
        pending_entry = None
        pending_exit = False

        # 2) trailing-stop update -- uses THIS bar's low/close and the post-fill position
        #    state, matching Pine (position_size already reflects the open-of-bar fill by
        #    the time the rest of the script runs).
        is_long = len(lots) > 0
        if is_long:
            candidate = l[u] - sl_val[u]
            trailing_sl_u = candidate if trailing_sl_prev is None else max(candidate, trailing_sl_prev)
        else:
            trailing_sl_u = None
        crossunder_now = (trailing_sl_u is not None and trailing_sl_prev is not None and
                          c[u] < trailing_sl_u and c[u - 1] >= trailing_sl_prev)

        # 3) pivot bookkeeping + divergence signals, evaluated at u's close
        bull_cond = False
        hidden_bull_cond = False
        if pl_found[u]:
            p = u - lb_right
            cur_osc, cur_low = osc[p], l[p]
            if prev_pl is not None:
                pbar, posc, plow = prev_pl
                bars_since = (u - 1) - pbar
                in_range = range_lower <= bars_since <= range_upper
                osc_hl = cur_osc > posc and in_range          # regular: osc higher low
                price_ll = cur_low < plow                      # regular: price lower low
                bull_cond = price_ll and osc_hl
                osc_ll = cur_osc < posc and in_range            # hidden: osc lower low
                price_hl = cur_low > plow                       # hidden: price higher low
                hidden_bull_cond = use_hidden_bull and price_hl and osc_ll
                if bull_cond or hidden_bull_cond:
                    pending_entry = dict(
                        kind=("regular" if bull_cond else "hidden"),
                        pivot_bar=p, pivot_osc=float(cur_osc), pivot_low=float(cur_low),
                        prev_pivot_bar=pbar - lb_right,
                        prev_osc=float(posc), prev_low=float(plow),
                    )
            prev_pl = (u, cur_osc, cur_low)

        bear_cond = False
        if ph_found[u]:
            p = u - lb_right
            cur_osc, cur_high = osc[p], h[p]
            if prev_ph is not None:
                pbar, posc, phigh = prev_ph
                bars_since = (u - 1) - pbar
                in_range = range_lower <= bars_since <= range_upper
                osc_lh = cur_osc < posc and in_range            # regular: osc lower high
                price_hh = cur_high > phigh                      # regular: price higher high
                bear_cond = price_hh and osc_lh
            prev_ph = (u, cur_osc, cur_high)

        # 4) exit signal for the NEXT bar's open (sl_type gates which exit path is live --
        #    the Pine script's own if/else, mutually exclusive)
        if lots:
            if sl_type == "NONE":
                pending_exit = bool(tp_cross[u] or bear_cond)
            else:
                pending_exit = bool(crossunder_now)

        if len(lots) >= max_pyramid:
            pending_entry = None            # no pyramiding room -- Pine rejects the order

        # 5) roll-seam eve: force flat (all lots) at this day's final bar close; pending
        #    orders for the seam day itself are always killed, whether or not there was
        #    an open position to flatten (mirrors BBRSI/TTIBS's guard exactly).
        if di in force_exit_days and u == last_bar_of_day[di]:
            if lots:
                for eb, ep in lots:
                    _book(u, c[u], ep, eb)
                lots = []
            pending_entry = None
            pending_exit = False

        trailing_sl_prev = trailing_sl_u

    # end of data: any still-open lots are DROPPED (never truncated)

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
        out["pivot_log"] = pivot_log
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Smoke test — tiny window, sane-output check. Run: python augur_strategies/RSIDIV_1_0.py
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

    print("RSIDIV 1.0 smoke test — NQ 5m RTH, 2015-2017 (%d bars, %d sessions)"
          % (len(df), len(set(day_id))))
    print("%-52s %7s %5s %6s %13s %11s" % ("config", "trades", "WR%", "PF", "net $", "maxDD$ (gross)"))
    print("-" * 100)

    configs = [
        ("published: RSI9 1/3, tp80, pyramid2, sl NONE", dict()),
        ("rsi_len 5 / tp_rsi_level 75 (author GOOGL corner)", dict(rsi_len=5, tp_rsi_level=75)),
        ("sl_type PERC (5% trail, replaces RSI/bear exit)", dict(sl_type="PERC")),
        ("max_pyramid 1 (no stacking)", dict(max_pyramid=1)),
    ]
    published_result = None
    for label, kw in configs:
        r = run_backtest(df["open"].values, df["high"].values, df["low"].values,
                         df["close"].values, day_id=day_id, index=df.index,
                         return_trades=True, **kw)
        if label.startswith("published"):
            published_result = r
        if r is None:
            print("%-52s  NO TRADES" % label); continue
        net_usd = (r["total_pnl"] - FEE * r["num_trades"]) * MULT
        print("%-52s %7d %4.0f%% %6.2f %13s %11s" % (
            label, r["num_trades"], r["win_rate"], min(r["profit_factor"], 99),
            "${:+,.0f}".format(net_usd), "${:,.0f}".format(r["max_drawdown"] * MULT)))
    print("\nPoints-based engine output; house cost_pts/mult applied by the caller "
          "(this table folds fee into net only). Sane-output check, not a result.")

    if published_result and published_result.get("trades"):
        print("\nFirst 2 trades (published config) -- pivot bars for eyeballing:")
        pivlog = published_result.get("pivot_log", {})
        for i, tr in enumerate(published_result["trades"][:2]):
            eb, xb, pnl, side, ep, xp = tr
            print("  trade %d: entry bar %-6d @ %s  px=%.2f   ->   exit bar %-6d @ %s  "
                  "px=%.2f   pnl=%+.2f pts" % (
                i + 1, eb, df.index[eb], ep, xb, df.index[xb], xp, pnl))
            piv = pivlog.get(eb)
            if piv:
                cur_ts = df.index[piv["pivot_bar"]]
                prev_ts = df.index[piv["prev_pivot_bar"]]
                print("    %-8s divergence -- new  pivot bar %-6d @ %s  osc=%.2f  low=%.2f"
                      % (piv["kind"], piv["pivot_bar"], cur_ts, piv["pivot_osc"], piv["pivot_low"]))
                print("                        prev pivot bar %-6d @ %s  osc=%.2f  low=%.2f"
                      % (piv["prev_pivot_bar"], prev_ts, piv["prev_osc"], piv["prev_low"]))
            else:
                print("    (no pivot_log entry for entry bar %d)" % eb)
