"""
REVERT 1.0 — intraday mean-reversion, faded WITH the daily bias.

Thesis (opposite of the ENGU breakout family): intraday index futures spend most
of their time mean-reverting. So instead of buying strength (breakouts), we FADE
overextensions back toward a short-term mean — but only in the direction of the
day's bias, so we buy dips in up-days and sell rips in down-days (never catching
a falling knife). Built for AUGUR's walk-forward + realism caps.

  • mean        = EMA(close, mean_len)
  • stretched   = |close - mean| > ext_mult * ATR(atr_len)
  • daily bias  = above/below the prior-session close OR today's open (gap-immune)
  • LONG  when price is stretched BELOW the mean AND the day is bullish
  • SHORT when price is stretched ABOVE the mean AND the day is bearish
  • exit  = back to the mean (optional) or an ATR-multiple target; ATR-distance
            stop; optional trailing; optional flat-by-session-close.

PNL convention SHARES*(EXIT-ENTRY)+FEE (fees handled by AUGUR cost-netting).
"""
import numpy as np

# -- Identity -----------------------------------------------------------------
STRATEGY_NAME = 'REVERT 1.0 · mean-reversion (fade with daily bias)'
DESCRIPTION   = ("Intraday mean-reversion: fade overextensions back toward a short "
                 "EMA, but only WITH the day's directional bias (buy dips in up-days, "
                 "sell rips in down-days). The anti-ENGU.")

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
        "trade_mode": ["Both"], "bias_mode": ["prior_close"], "exit_to_mean": [True],
        "stop_mult": [1.5, 2.0], "trail_stop": [False], "cooldown_bars": [0], "flat_eod": [True],
    },
    "Medium (balanced)": {
        "mean_len": [10, 20, 30], "atr_len": [10, 14], "ext_mult": [1.0, 1.5, 2.0, 2.5],
        "trade_mode": ["Both"], "bias_mode": ["off", "prior_close", "session_open"],
        "exit_to_mean": [True, False], "tp_mult": [1.5], "stop_mult": [1.0, 1.5, 2.0],
        "trail_stop": [False], "cooldown_bars": [0, 4], "flat_eod": [True],
    },
    "Long   (deep sweep)": {
        "mean_len": [10, 15, 20, 30, 50], "atr_len": [10, 14, 20], "ext_mult": [0.75, 1.0, 1.5, 2.0, 2.5, 3.0],
        "trade_mode": ["Long Only", "Short Only", "Both"],
        "bias_mode": ["off", "prior_close", "session_open"], "exit_to_mean": [True, False],
        "tp_mult": [1.0, 1.5, 2.0], "stop_mult": [1.0, 1.5, 2.0, 2.5],
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


def run_backtest(
    opens: np.ndarray, highs: np.ndarray, lows: np.ndarray, closes: np.ndarray,
    volumes: np.ndarray = None,
    mean_len: int = 20, atr_len: int = 14, ext_mult: float = 1.5,
    trade_mode: str = "Both", bias_mode: str = "prior_close",
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
