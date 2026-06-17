"""
REVERT 1.2 — REVERT 1.0 (mean-reversion + daily bias) + an intraday TIME-OF-DAY window.

Why: intraday index futures mean-revert MOST in the middle of the session. The open
(first ~20% of bars) gaps and trends as overnight positioning unwinds; the close
(last ~15%) carries position-squaring momentum into the bell. Those two windows are
exactly where a naive "fade the stretch" bleeds. REVERT 1.2 keeps 1.0's logic verbatim
and adds ONE gate: only take fades when the bar sits inside [tod_lo, tod_hi] of its
session. Single-variable change so the walk-forward tells us cleanly whether the
time-of-day edge is real on this data (it didn't help via the regime filter in 1.1).

  • mean        = EMA(close, mean_len)
  • stretched   = |close - mean| > ext_mult * ATR(atr_len)
  • daily bias  = above/below prior-session close OR today's open (gap-immune)
  • TIME WINDOW = only enter when tod_lo <= (bar's fraction through its session) <= tod_hi
  • LONG  when stretched BELOW the mean AND the day is bullish AND in-window
  • SHORT when stretched ABOVE the mean AND the day is bearish AND in-window
  • exit  = back to the mean (optional) or an ATR-multiple target; ATR stop; optional
            trailing; optional flat-by-session-close.

PNL convention SHARES*(EXIT-ENTRY)+FEE (fees handled by AUGUR cost-netting).
"""
import numpy as np

# -- Identity -----------------------------------------------------------------
STRATEGY_NAME = 'REVERT 1.2 · mean-reversion + time-of-day window'
DESCRIPTION   = ("REVERT 1.0 plus an intraday time-of-day filter: only fade in the "
                 "middle of the session, skipping the open (gaps/trend) and the close "
                 "(position-squaring). One added gate vs 1.0, for a clean A/B.")

_AUGUR_MARKET = {'instrument': 'ES', 'timeframe': '5m'}

# -- Parameters ---------------------------------------------------------------
DEFAULT_PARAMS = {
    "mean_len": {
        "default": 20, "min": 5, "max": 100, "step": 5, "type": "int",
        "label": "Mean EMA length",
        "tooltip": "The short-term mean price reverts toward. Smaller = twitchier.",
    },
    "atr_len": {
        "default": 14, "min": 5, "max": 40, "step": 1, "type": "int",
        "label": "ATR length", "tooltip": "Volatility unit for the stretch + stops.",
    },
    "ext_mult": {
        "default": 1.5, "min": 0.5, "max": 4.0, "step": 0.25, "type": "float",
        "label": "Stretch trigger (x ATR)",
        "tooltip": "Enter once price is this many ATRs away from the mean. Higher = "
                   "rarer, deeper fades.",
    },
    "trade_mode": {
        "default": "Both", "type": "str",
        "options": ["Long Only", "Short Only", "Both"],
        "label": "Direction",
    },
    "bias_mode": {
        "default": "prior_close", "type": "str",
        "options": ["off", "prior_close", "session_open"],
        "label": "Daily bias (core)",
        "tooltip": "Only buy dips when ABOVE a daily anchor, only sell rips when "
                   "BELOW it. prior_close = yesterday's close; session_open = today's "
                   "open (gap-immune); off = pure mean-reversion. Needs session data.",
    },
    # -- the new idea: only fade in the middle of the session ------------------
    "use_tod": {
        "default": True, "type": "bool",
        "label": "Time-of-day window",
        "tooltip": "Only enter when the bar sits inside [open%, close%] of its session. "
                   "Skips the open (gaps/trend) and the bell (squaring). Needs session data.",
    },
    "tod_lo": {
        "default": 0.20, "min": 0.0, "max": 0.5, "step": 0.05, "type": "float",
        "label": "Skip first … of session", "depends_on": {"use_tod": True},
        "tooltip": "Fraction of the session to skip at the open. 0.20 = ignore the first "
                   "fifth of the day's bars.",
    },
    "tod_hi": {
        "default": 0.85, "min": 0.5, "max": 1.0, "step": 0.05, "type": "float",
        "label": "Stop entries after …", "depends_on": {"use_tod": True},
        "tooltip": "No new entries past this fraction of the session. 0.85 = no fades in "
                   "the last 15% before the close.",
    },
    "exit_to_mean": {
        "default": True, "type": "bool",
        "label": "Target = the mean",
        "tooltip": "Exit when price reverts back to the EMA. Off = use an ATR target.",
    },
    "tp_mult": {
        "default": 1.5, "min": 0.5, "max": 4.0, "step": 0.25, "type": "float",
        "label": "Target (x ATR)", "depends_on": {"exit_to_mean": False},
        "tooltip": "Profit target distance when not exiting to the mean.",
    },
    "stop_mult": {
        "default": 1.5, "min": 0.5, "max": 4.0, "step": 0.25, "type": "float",
        "label": "Stop (x ATR)",
        "tooltip": "Stop distance beyond the entry (further from the mean).",
    },
    "trail_stop": {
        "default": False, "type": "bool", "label": "Trailing stop",
        "tooltip": "Trail the stop by the ATR stop distance as price moves your way.",
    },
    "cooldown_bars": {
        "default": 0, "min": 0, "max": 20, "step": 1, "type": "int",
        "label": "Post-loss cooldown (bars)",
        "tooltip": "After a losing trade, wait this many bars before re-entering.",
    },
    "flat_eod": {
        "default": True, "type": "bool",
        "label": "Flat by session close",
        "tooltip": "Close at each session's last bar (no overnight holds). Needs session data.",
    },
}

PARAM_GRID_PRESETS = {
    "Short  (fast scan)": {
        "mean_len": [15, 25], "atr_len": [14], "ext_mult": [1.0, 1.5, 2.0],
        "trade_mode": ["Both"], "bias_mode": ["prior_close"],
        "use_tod": [True], "tod_lo": [0.15, 0.25], "tod_hi": [0.85],
        "exit_to_mean": [True], "stop_mult": [1.5, 2.0],
        "trail_stop": [False], "cooldown_bars": [0], "flat_eod": [True],
    },
    "Medium (balanced)": {
        "mean_len": [10, 20, 30], "atr_len": [10, 14], "ext_mult": [1.0, 1.5, 2.0, 2.5],
        "trade_mode": ["Both"], "bias_mode": ["off", "prior_close", "session_open"],
        "use_tod": [False, True], "tod_lo": [0.15, 0.25], "tod_hi": [0.80, 0.90],
        "exit_to_mean": [True, False], "tp_mult": [1.5], "stop_mult": [1.0, 1.5, 2.0],
        "trail_stop": [False], "cooldown_bars": [0, 4], "flat_eod": [True],
    },
    "Long   (deep sweep)": {
        "mean_len": [10, 15, 20, 30, 50], "atr_len": [10, 14, 20],
        "ext_mult": [0.75, 1.0, 1.5, 2.0, 2.5, 3.0],
        "trade_mode": ["Long Only", "Short Only", "Both"],
        "bias_mode": ["off", "prior_close", "session_open"],
        "use_tod": [False, True], "tod_lo": [0.10, 0.20, 0.30], "tod_hi": [0.75, 0.85, 0.95],
        "exit_to_mean": [True, False], "tp_mult": [1.0, 1.5, 2.0], "stop_mult": [1.0, 1.5, 2.0, 2.5],
        "trail_stop": [False, True], "cooldown_bars": [0, 4, 8], "flat_eod": [True, False],
    },
}


# -- Indicator helpers (vectorised) -------------------------------------------
def _ema(arr, length):
    length = max(1, int(length)); a = 2.0 / (length + 1.0)
    out = np.empty_like(arr, dtype=float); out[0] = arr[0]
    for i in range(1, len(arr)):
        out[i] = a * arr[i] + (1 - a) * out[i - 1]
    return out

def _atr(highs, lows, closes, length):
    length = max(1, int(length)); n = len(closes)
    tr = np.empty(n, dtype=float); tr[0] = highs[0] - lows[0]
    for i in range(1, n):
        tr[i] = max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1]))
    atr = np.full(n, np.nan, dtype=float)
    if n >= length:
        atr[length - 1] = tr[:length].mean()
        for i in range(length, n):
            atr[i] = (atr[i - 1] * (length - 1) + tr[i]) / length
    return atr

def _session_fraction(day_id, n):
    """Per-bar fraction [0,1] through its (contiguous) session id. 0=open, 1=close."""
    did = np.asarray(day_id)
    frac = np.full(n, 0.5, dtype=float)
    j = 0
    while j < n:
        k = j
        while k + 1 < n and did[k + 1] == did[j]:
            k += 1
        span = k - j
        if span > 0:
            frac[j:k + 1] = (np.arange(j, k + 1) - j) / float(span)
        j = k + 1
    return frac


def run_backtest(
    opens: np.ndarray, highs: np.ndarray, lows: np.ndarray, closes: np.ndarray,
    volumes: np.ndarray = None,
    mean_len: int = 20, atr_len: int = 14, ext_mult: float = 1.5,
    trade_mode: str = "Both", bias_mode: str = "prior_close",
    use_tod: bool = True, tod_lo: float = 0.20, tod_hi: float = 0.85,
    exit_to_mean: bool = True, tp_mult: float = 1.5, stop_mult: float = 1.5,
    trail_stop: bool = False, cooldown_bars: int = 0, flat_eod: bool = True,
    day_id: np.ndarray = None,
    return_trades: bool = False, _stop_event=None, _pause_event=None,
) -> dict | None:
    opens = np.asarray(opens, float); highs = np.asarray(highs, float)
    lows = np.asarray(lows, float);   closes = np.asarray(closes, float)
    n = len(closes)
    if n < 10:
        return None

    mean = _ema(closes, mean_len)
    atr  = _atr(highs, lows, closes, atr_len)

    # Session anchors from a per-bar session id the app passes (no timestamps here).
    _pclose = _sopen = _send = None
    if day_id is not None and len(day_id) == n and (bias_mode != "off" or flat_eod):
        did = np.asarray(day_id)
        _pclose = np.full(n, np.nan); _sopen = np.full(n, np.nan); _send = np.zeros(n, dtype=bool)
        _prev_last = np.nan; _cur_open = np.nan
        for j in range(n):
            if j == 0 or did[j] != did[j - 1]:
                if j > 0:
                    _prev_last = closes[j - 1]
                _cur_open = opens[j]
            _pclose[j] = _prev_last; _sopen[j] = _cur_open
            _send[j] = (j == n - 1) or (did[j + 1] != did[j])

    # Time-of-day fraction (only needed when the window filter is on).
    _frac = None
    if use_tod and day_id is not None and len(day_id) == n:
        _frac = _session_fraction(day_id, n)

    allow_long  = trade_mode in ("Long Only", "Both")
    allow_short = trade_mode in ("Short Only", "Both")
    start_idx = max(mean_len, atr_len) + 2

    pnl_list, trade_log = [], []
    pos = None
    last_loss_bar = -10**9

    for i in range(start_idx, n):
        a = atr[i]
        if np.isnan(a) or a <= 0:
            continue

        # -- position management --------------------------------------------
        if pos is not None:
            side = pos["side"]
            if trail_stop:
                if side > 0:
                    pos["sl"] = max(pos["sl"], highs[i] - a * stop_mult)
                else:
                    pos["sl"] = min(pos["sl"], lows[i] + a * stop_mult)
            if side > 0:
                if lows[i] <= pos["sl"]:
                    pnl = pos["sl"] - pos["ep"]; pnl_list.append(pnl)
                    if return_trades: trade_log.append((pos["bar"], i, pnl))
                    last_loss_bar = i if pnl < 0 else last_loss_bar; pos = None; continue
                if pos["tp"] is not None and highs[i] >= pos["tp"]:
                    pnl = pos["tp"] - pos["ep"]; pnl_list.append(pnl)
                    if return_trades: trade_log.append((pos["bar"], i, pnl))
                    last_loss_bar = i if pnl < 0 else last_loss_bar; pos = None; continue
            else:
                if highs[i] >= pos["sl"]:
                    pnl = pos["ep"] - pos["sl"]; pnl_list.append(pnl)
                    if return_trades: trade_log.append((pos["bar"], i, pnl))
                    last_loss_bar = i if pnl < 0 else last_loss_bar; pos = None; continue
                if pos["tp"] is not None and lows[i] <= pos["tp"]:
                    pnl = pos["ep"] - pos["tp"]; pnl_list.append(pnl)
                    if return_trades: trade_log.append((pos["bar"], i, pnl))
                    last_loss_bar = i if pnl < 0 else last_loss_bar; pos = None; continue
            # flat by session close
            if flat_eod and _send is not None and _send[i]:
                pnl = (closes[i] - pos["ep"]) if side > 0 else (pos["ep"] - closes[i])
                pnl_list.append(pnl)
                if return_trades: trade_log.append((pos["bar"], i, pnl))
                last_loss_bar = i if pnl < 0 else last_loss_bar; pos = None; continue
            continue  # already in a position — no pyramiding

        # -- signal (mean-reversion, faded WITH the daily bias) -------------
        if cooldown_bars > 0 and (i - last_loss_bar) < cooldown_bars:
            continue
        if flat_eod and _send is not None and _send[i]:
            continue
        # time-of-day window: only fade mid-session
        if use_tod and _frac is not None and not (tod_lo <= _frac[i] <= tod_hi):
            continue

        dev = closes[i] - mean[i]
        stretched_dn = dev < -ext_mult * a     # below mean → buy candidate
        stretched_up = dev >  ext_mult * a     # above mean → sell candidate

        bias_long = bias_short = True
        if bias_mode != "off" and _pclose is not None:
            ref = _pclose[i] if bias_mode == "prior_close" else _sopen[i]
            if not np.isnan(ref):
                bias_long = closes[i] > ref
                bias_short = closes[i] < ref

        go_long  = stretched_dn and bias_long
        go_short = stretched_up and bias_short

        ep = closes[i]
        if go_long and allow_long:
            sl = ep - a * stop_mult
            tp = mean[i] if exit_to_mean else ep + a * tp_mult
            pos = {"side": +1, "bar": i, "ep": ep, "sl": sl, "tp": tp}
        elif go_short and allow_short:
            sl = ep + a * stop_mult
            tp = mean[i] if exit_to_mean else ep - a * tp_mult
            pos = {"side": -1, "bar": i, "ep": ep, "sl": sl, "tp": tp}

    if pos is not None:
        pnl = (closes[-1] - pos["ep"]) if pos["side"] > 0 else (pos["ep"] - closes[-1])
        pnl_list.append(pnl)
        if return_trades: trade_log.append((pos["bar"], n - 1, pnl))

    if not pnl_list:
        return None
    pnls = np.array(pnl_list, dtype=float)
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
