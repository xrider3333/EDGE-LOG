"""
VWAP FADE 1.0 — session-VWAP reversion (a structurally different fade).

After three EMA-stretch variants (REVERT 1.0/1.1/1.2) showed no robust intraday edge,
this abandons the EMA entirely and anchors on the session VWAP — the volume-weighted
average price institutions benchmark their fills against. VWAP exerts real intraday
"gravity": when price stretches far from it (measured in volume-weighted standard
deviations), it tends to revert. Crucially the reversion *target is the VWAP itself*,
which is usually a big enough move to clear the ~$11-18 round-turn cost that strangled
the small EMA fades.

  • anchor  = session VWAP   = Σ(typical·vol) / Σ(vol), RESET every session
  • bands   = VWAP ± band_mult · vwσ   (vwσ = volume-weighted stdev of typical-vs-VWAP)
  • LONG  when close < VWAP − band_mult·vwσ  → target = the (live) VWAP
  • SHORT when close > VWAP + band_mult·vwσ  → target = the (live) VWAP
  • stop   = entry ∓ stop_mult·vwσ(at entry)   (wider than the band)
  • warmup = don't trade until N bars into the session (VWAP must establish first)
  • optional daily bias, post-loss cooldown, max-hold time-stop, flat-by-close.

Needs per-session data: the app passes a per-bar session id (day_id) + volume. With no
session id it falls back to one big session (research only); with no/zero volume it
falls back to an equal-weight VWAP. PNL convention SHARES*(EXIT-ENTRY)+FEE.
"""
import numpy as np
import math

# -- Identity -----------------------------------------------------------------
STRATEGY_NAME = 'VWAP FADE 1.0 · session-VWAP reversion'
DESCRIPTION   = ("Fade stretches away from the session VWAP back to the VWAP itself. "
                 "Volume-weighted bands, per-session reset, warmup before trading. A "
                 "different anchor than the EMA-stretch REVERT family.")

_AUGUR_MARKET = {'instrument': 'ES', 'timeframe': '5m'}

# -- Parameters ---------------------------------------------------------------
DEFAULT_PARAMS = {
    "band_mult": {
        "default": 2.0, "min": 1.0, "max": 4.0, "step": 0.25, "type": "float",
        "label": "Stretch trigger (x VWAP σ)",
        "tooltip": "Enter once price is this many volume-weighted std-devs from VWAP. "
                   "Higher = rarer, deeper fades.",
    },
    "stop_mult": {
        "default": 2.5, "min": 1.0, "max": 5.0, "step": 0.5, "type": "float",
        "label": "Stop (x VWAP σ)",
        "tooltip": "Stop distance beyond the entry, further from VWAP. Keep it wider "
                   "than the trigger so the fade has room.",
    },
    "warmup_bars": {
        "default": 6, "min": 0, "max": 30, "step": 1, "type": "int",
        "label": "Warmup (bars into session)",
        "tooltip": "Skip the first N bars of each session so VWAP and its bands are "
                   "meaningful before fading. Needs session data.",
    },
    "max_hold": {
        "default": 0, "min": 0, "max": 60, "step": 2, "type": "int",
        "label": "Max hold (bars, 0=off)",
        "tooltip": "Time-stop: exit at market if the fade hasn't reverted within N bars. "
                   "0 disables it.",
    },
    "trade_mode": {
        "default": "Both", "type": "str",
        "options": ["Long Only", "Short Only", "Both"],
        "label": "Direction",
    },
    "bias_mode": {
        "default": "off", "type": "str",
        "options": ["off", "prior_close", "session_open"],
        "label": "Daily bias",
        "tooltip": "Optional: only buy dips when ABOVE a daily anchor / sell rips when "
                   "BELOW it. off = pure VWAP reversion (the optimizer kept choosing off "
                   "in the REVERT family). Needs session data.",
    },
    "cooldown_bars": {
        "default": 0, "min": 0, "max": 20, "step": 1, "type": "int",
        "label": "Post-loss cooldown (bars)",
        "tooltip": "After a losing trade, wait this many bars before re-entering.",
    },
    "flat_eod": {
        "default": True, "type": "bool",
        "label": "Flat by session close",
        "tooltip": "Close at each session's last bar (VWAP resets daily; no overnight). "
                   "Needs session data.",
    },
}

PARAM_GRID_PRESETS = {
    "Short  (fast scan)": {
        "band_mult": [1.5, 2.0, 2.5], "stop_mult": [2.5, 3.0], "warmup_bars": [6],
        "max_hold": [0], "trade_mode": ["Both"], "bias_mode": ["off"],
        "cooldown_bars": [0], "flat_eod": [True],
    },
    "Medium (balanced)": {
        "band_mult": [1.5, 2.0, 2.5, 3.0], "stop_mult": [2.0, 2.5, 3.0, 3.5],
        "warmup_bars": [3, 6, 12], "max_hold": [0, 12, 24],
        "trade_mode": ["Both"], "bias_mode": ["off", "prior_close"],
        "cooldown_bars": [0, 4], "flat_eod": [True],
    },
    "Long   (deep sweep)": {
        "band_mult": [1.0, 1.5, 2.0, 2.5, 3.0, 3.5], "stop_mult": [1.5, 2.0, 2.5, 3.0, 4.0],
        "warmup_bars": [0, 3, 6, 12, 18], "max_hold": [0, 8, 16, 32],
        "trade_mode": ["Long Only", "Short Only", "Both"],
        "bias_mode": ["off", "prior_close", "session_open"],
        "cooldown_bars": [0, 4, 8], "flat_eod": [True, False],
    },
}


# -- Session VWAP + volume-weighted dispersion (reset per session) -------------
def _session_vwap(highs, lows, closes, vol, did, n):
    tp = (highs + lows + closes) / 3.0
    vwap = np.empty(n, dtype=float)
    vwsd = np.zeros(n, dtype=float)
    bis  = np.zeros(n, dtype=np.int64)   # bar index within session
    last = np.zeros(n, dtype=bool)       # session's last bar
    cumPV = cumV = cumPV2 = 0.0
    k = 0
    for i in range(n):
        new_sess = (i == 0) or (did is not None and did[i] != did[i - 1])
        if new_sess:
            cumPV = cumV = cumPV2 = 0.0; k = 0
        w = vol[i]
        cumPV  += tp[i] * w
        cumV   += w
        cumPV2 += tp[i] * tp[i] * w
        if cumV > 0:
            vw = cumPV / cumV
            var = cumPV2 / cumV - vw * vw
            vwap[i] = vw
            vwsd[i] = math.sqrt(var) if var > 1e-12 else 0.0
        else:
            vwap[i] = tp[i]; vwsd[i] = 0.0
        bis[i] = k; k += 1
        last[i] = (i == n - 1) or (did is not None and did[i + 1] != did[i])
    return vwap, vwsd, bis, last


def run_backtest(
    opens: np.ndarray, highs: np.ndarray, lows: np.ndarray, closes: np.ndarray,
    volumes: np.ndarray = None,
    band_mult: float = 2.0, stop_mult: float = 2.5, warmup_bars: int = 6,
    max_hold: int = 0, trade_mode: str = "Both", bias_mode: str = "off",
    cooldown_bars: int = 0, flat_eod: bool = True,
    day_id: np.ndarray = None,
    return_trades: bool = False, _stop_event=None, _pause_event=None,
) -> dict | None:
    opens = np.asarray(opens, float); highs = np.asarray(highs, float)
    lows = np.asarray(lows, float);   closes = np.asarray(closes, float)
    n = len(closes)
    if n < 10:
        return None

    did = None
    if day_id is not None and len(day_id) == n:
        did = np.asarray(day_id)

    # volume (fall back to equal weight if missing / degenerate)
    if volumes is not None and len(volumes) == n:
        vol = np.asarray(volumes, float)
        if not np.isfinite(vol).all() or vol.sum() <= 0:
            vol = np.ones(n, dtype=float)
    else:
        vol = np.ones(n, dtype=float)

    vwap, vwsd, bis, last = _session_vwap(highs, lows, closes, vol, did, n)

    # prior-session close / session open for the optional daily bias
    _pclose = _sopen = None
    if bias_mode != "off" and did is not None:
        _pclose = np.full(n, np.nan); _sopen = np.full(n, np.nan)
        _prev_last = np.nan; _cur_open = np.nan
        for j in range(n):
            if j == 0 or did[j] != did[j - 1]:
                if j > 0: _prev_last = closes[j - 1]
                _cur_open = opens[j]
            _pclose[j] = _prev_last; _sopen[j] = _cur_open

    allow_long  = trade_mode in ("Long Only", "Both")
    allow_short = trade_mode in ("Short Only", "Both")

    pnl_list, trade_log = [], []
    pos = None
    last_loss_bar = -10**9

    for i in range(1, n):
        # -- position management --------------------------------------------
        if pos is not None:
            side = pos["side"]
            vw = vwap[i]
            if side > 0:
                # stop first (pessimistic), then revert-to-VWAP target
                if lows[i] <= pos["sl"]:
                    pnl = pos["sl"] - pos["ep"]; pnl_list.append(pnl)
                    if return_trades: trade_log.append((pos["bar"], i, pnl))
                    last_loss_bar = i if pnl < 0 else last_loss_bar; pos = None; continue
                if highs[i] >= vw:
                    pnl = vw - pos["ep"]; pnl_list.append(pnl)
                    if return_trades: trade_log.append((pos["bar"], i, pnl))
                    last_loss_bar = i if pnl < 0 else last_loss_bar; pos = None; continue
            else:
                if highs[i] >= pos["sl"]:
                    pnl = pos["ep"] - pos["sl"]; pnl_list.append(pnl)
                    if return_trades: trade_log.append((pos["bar"], i, pnl))
                    last_loss_bar = i if pnl < 0 else last_loss_bar; pos = None; continue
                if lows[i] <= vw:
                    pnl = pos["ep"] - vw; pnl_list.append(pnl)
                    if return_trades: trade_log.append((pos["bar"], i, pnl))
                    last_loss_bar = i if pnl < 0 else last_loss_bar; pos = None; continue
            # max-hold time stop
            if max_hold > 0 and (i - pos["bar"]) >= max_hold:
                pnl = (closes[i] - pos["ep"]) if side > 0 else (pos["ep"] - closes[i])
                pnl_list.append(pnl)
                if return_trades: trade_log.append((pos["bar"], i, pnl))
                last_loss_bar = i if pnl < 0 else last_loss_bar; pos = None; continue
            # flat by session close
            if flat_eod and last[i]:
                pnl = (closes[i] - pos["ep"]) if side > 0 else (pos["ep"] - closes[i])
                pnl_list.append(pnl)
                if return_trades: trade_log.append((pos["bar"], i, pnl))
                last_loss_bar = i if pnl < 0 else last_loss_bar; pos = None; continue
            continue  # in a position — no pyramiding

        # -- entry signal ---------------------------------------------------
        sd = vwsd[i]
        if sd <= 0 or bis[i] < warmup_bars:
            continue
        if cooldown_bars > 0 and (i - last_loss_bar) < cooldown_bars:
            continue
        if flat_eod and last[i]:
            continue

        dist = closes[i] - vwap[i]
        stretched_dn = dist < -band_mult * sd     # below VWAP → buy
        stretched_up = dist >  band_mult * sd     # above VWAP → sell

        bias_long = bias_short = True
        if bias_mode != "off" and _pclose is not None:
            ref = _pclose[i] if bias_mode == "prior_close" else _sopen[i]
            if not np.isnan(ref):
                bias_long = closes[i] > ref
                bias_short = closes[i] < ref

        ep = closes[i]
        if stretched_dn and bias_long and allow_long:
            pos = {"side": +1, "bar": i, "ep": ep, "sl": ep - stop_mult * sd}
        elif stretched_up and bias_short and allow_short:
            pos = {"side": -1, "bar": i, "ep": ep, "sl": ep + stop_mult * sd}

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
