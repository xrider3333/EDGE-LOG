"""
VWAP FADE 2.0 — REGIME-AWARE session-VWAP fade.

Why this exists: re-validating VWAP FADE 1.0 on the session-correct build showed the
"edge" was almost entirely the LONG side on an up-trending sample — a symmetric two-sided
fade was ~breakeven (ES +$2.7k, NQ -$0.8k), while Long-Only carried it (ES +$10.7k, NQ
+$47.1k). That's long beta timed by VWAP, not robust two-sided reversion.

v2 turns that accident into a deliberate design: fade dips/rips **in the direction of the
higher-timeframe trend**. A causal trend MA (length `regime_len`, in bars) splits the tape
into up vs down regimes:

  • regime_mode = "with_trend"  (default, the thesis): when price > trend MA → only BUY
    dips below VWAP; when price < trend MA → only SELL rips above VWAP. So in a downtrend
    the SHORT side finally gets to work (the missing half in v1), and in an uptrend you get
    the long-dip behaviour that already worked — but now it's intentional and regime-gated.
  • regime_mode = "against_trend": the pure counter-trend fade (buy dips only in
    downtrends, etc.) — kept so the optimizer can prove whether trend-alignment actually
    matters or it's just exposure.
  • regime_mode = "off": identical to VWAP FADE 1.0 (no regime gate) for A/B comparison.

Everything else is v1: session VWAP anchor (reset per session, volume-weighted), entry
when price is `band_mult`·vwσ from VWAP, TARGET = the live VWAP, stop = entry ∓
`stop_mult`·vwσ, warmup, max-hold time-stop, post-loss cooldown, flat-by-close. The dead
`bias_mode` param from v1 is dropped (the optimizer never chose anything but off).

Needs per-session data (day_id) + volume; falls back to one big session / equal weight if
missing (research only). PNL convention SHARES*(EXIT-ENTRY); engine adds multiplier+costs.
"""
import numpy as np
import math

STRATEGY_NAME = "VWAP FADE 2.0 · regime-aware VWAP fade"
DESCRIPTION   = ("Session-VWAP fade gated by a higher-timeframe trend MA: fade dips with "
                 "an uptrend / rips with a downtrend (or against, or off). Turns v1's "
                 "long-beta into a deliberate two-sided regime design.")

_AUGUR_MARKET = {"instrument": "ES", "timeframe": "5m"}

DEFAULT_PARAMS = {
    "band_mult": {
        "default": 2.0, "min": 1.0, "max": 4.0, "step": 0.25, "type": "float",
        "label": "Stretch trigger (x VWAP σ)",
        "tooltip": "Enter once price is this many volume-weighted std-devs from VWAP.",
    },
    "stop_mult": {
        "default": 2.5, "min": 1.0, "max": 5.0, "step": 0.5, "type": "float",
        "label": "Stop (x VWAP σ)",
        "tooltip": "Stop distance beyond entry, further from VWAP. Keep wider than the trigger.",
    },
    "regime_mode": {
        "default": "with_trend", "type": "str",
        "options": ["with_trend", "against_trend", "off"],
        "label": "Regime gate",
        "tooltip": "with_trend = buy dips only in uptrends / sell rips only in downtrends "
                   "(the v2 thesis). against_trend = the opposite. off = plain v1 fade.",
    },
    "regime_len": {
        "default": 120, "min": 20, "max": 400, "step": 10, "type": "int",
        "label": "Trend MA length (bars)",
        "tooltip": "Length of the causal EMA that defines the up/down regime. ~78 bars ≈ "
                   "one RTH day on 5m; bigger = slower, more structural trend.",
        "depends_on": {"regime_mode": ["with_trend", "against_trend"]},
    },
    "warmup_bars": {
        "default": 6, "min": 0, "max": 30, "step": 1, "type": "int",
        "label": "Warmup (bars into session)",
        "tooltip": "Skip the first N bars of each session so VWAP/bands are meaningful.",
    },
    "max_hold": {
        "default": 0, "min": 0, "max": 60, "step": 2, "type": "int",
        "label": "Max hold (bars, 0=off)",
        "tooltip": "Time-stop: exit at market if the fade hasn't reverted within N bars.",
    },
    "trade_mode": {
        "default": "Both", "type": "str",
        "options": ["Long Only", "Short Only", "Both"],
        "label": "Direction cap",
        "tooltip": "Hard cap on direction, applied ON TOP of the regime gate.",
    },
    "cooldown_bars": {
        "default": 0, "min": 0, "max": 20, "step": 1, "type": "int",
        "label": "Post-loss cooldown (bars)",
        "tooltip": "After a losing trade, wait this many bars before re-entering.",
    },
    "flat_eod": {
        "default": True, "type": "bool",
        "label": "Flat by session close",
        "tooltip": "Close at each session's last bar (VWAP resets daily; no overnight).",
    },
}

PARAM_GRID_PRESETS = {
    "Short  (fast scan)": {
        "band_mult": [1.5, 2.0, 2.5], "stop_mult": [2.5, 3.5, 4.5],
        "regime_mode": ["with_trend"], "regime_len": [78, 160],
        "warmup_bars": [6], "max_hold": [0], "trade_mode": ["Both"],
        "cooldown_bars": [0], "flat_eod": [True],
    },
    "Medium (balanced)": {
        "band_mult": [1.5, 2.0, 2.5, 3.0], "stop_mult": [2.0, 3.0, 4.0, 5.0],
        "regime_mode": ["with_trend", "off"], "regime_len": [40, 78, 160, 240],
        "warmup_bars": [3, 6, 12], "max_hold": [0, 16, 32],
        "trade_mode": ["Both"], "cooldown_bars": [0, 4], "flat_eod": [True],
    },
    "Long   (deep sweep)": {
        "band_mult": [1.0, 1.5, 2.0, 2.5, 3.0, 3.5], "stop_mult": [1.5, 2.5, 3.5, 4.5],
        "regime_mode": ["with_trend", "against_trend", "off"],
        "regime_len": [40, 78, 120, 200, 300],
        "warmup_bars": [0, 6, 12, 18], "max_hold": [0, 8, 16, 32],
        "trade_mode": ["Long Only", "Short Only", "Both"],
        "cooldown_bars": [0, 4, 8], "flat_eod": [True, False],
    },
}


def _session_vwap(highs, lows, closes, vol, did, n):
    tp = (highs + lows + closes) / 3.0
    vwap = np.empty(n, dtype=float)
    vwsd = np.zeros(n, dtype=float)
    bis  = np.zeros(n, dtype=np.int64)
    last = np.zeros(n, dtype=bool)
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


def _ema(x, length):
    """Causal EMA (no look-ahead): ema[i] depends only on x[:i+1]."""
    n = len(x)
    out = np.empty(n, dtype=float)
    a = 2.0 / (length + 1.0)
    out[0] = x[0]
    for i in range(1, n):
        out[i] = a * x[i] + (1.0 - a) * out[i - 1]
    return out


def run_backtest(
    opens, highs, lows, closes, volumes=None,
    band_mult: float = 2.0, stop_mult: float = 2.5,
    regime_mode: str = "with_trend", regime_len: int = 120,
    warmup_bars: int = 6, max_hold: int = 0, trade_mode: str = "Both",
    cooldown_bars: int = 0, flat_eod: bool = True,
    day_id=None, return_trades: bool = False, _stop_event=None, _pause_event=None,
):
    opens = np.asarray(opens, float); highs = np.asarray(highs, float)
    lows = np.asarray(lows, float);   closes = np.asarray(closes, float)
    n = len(closes)
    if n < max(20, int(regime_len) + 5):
        return None

    did = None
    if day_id is not None and len(day_id) == n:
        did = np.asarray(day_id)

    if volumes is not None and len(volumes) == n:
        vol = np.asarray(volumes, float)
        if not np.isfinite(vol).all() or vol.sum() <= 0:
            vol = np.ones(n, dtype=float)
    else:
        vol = np.ones(n, dtype=float)

    vwap, vwsd, bis, last = _session_vwap(highs, lows, closes, vol, did, n)

    # regime: causal trend EMA → up when close > MA
    use_regime = regime_mode in ("with_trend", "against_trend")
    trend_up = None
    if use_regime:
        ma = _ema(closes, max(2, int(regime_len)))
        trend_up = closes > ma

    cap_long  = trade_mode in ("Long Only", "Both")
    cap_short = trade_mode in ("Short Only", "Both")

    pnl_list, trade_log = [], []
    pos = None
    last_loss_bar = -10 ** 9

    for i in range(1, n):
        if pos is not None:
            side = pos["side"]; vw = vwap[i]
            if side > 0:
                if lows[i] <= pos["sl"]:
                    pnl = pos["sl"] - pos["ep"]; pnl_list.append(pnl)
                    if return_trades: trade_log.append((pos["bar"], i, float(pnl)))
                    last_loss_bar = i if pnl < 0 else last_loss_bar; pos = None; continue
                if highs[i] >= vw:
                    pnl = vw - pos["ep"]; pnl_list.append(pnl)
                    if return_trades: trade_log.append((pos["bar"], i, float(pnl)))
                    last_loss_bar = i if pnl < 0 else last_loss_bar; pos = None; continue
            else:
                if highs[i] >= pos["sl"]:
                    pnl = pos["ep"] - pos["sl"]; pnl_list.append(pnl)
                    if return_trades: trade_log.append((pos["bar"], i, float(pnl)))
                    last_loss_bar = i if pnl < 0 else last_loss_bar; pos = None; continue
                if lows[i] <= vw:
                    pnl = pos["ep"] - vw; pnl_list.append(pnl)
                    if return_trades: trade_log.append((pos["bar"], i, float(pnl)))
                    last_loss_bar = i if pnl < 0 else last_loss_bar; pos = None; continue
            if max_hold > 0 and (i - pos["bar"]) >= max_hold:
                pnl = (closes[i] - pos["ep"]) if side > 0 else (pos["ep"] - closes[i])
                pnl_list.append(pnl)
                if return_trades: trade_log.append((pos["bar"], i, float(pnl)))
                last_loss_bar = i if pnl < 0 else last_loss_bar; pos = None; continue
            if flat_eod and last[i]:
                pnl = (closes[i] - pos["ep"]) if side > 0 else (pos["ep"] - closes[i])
                pnl_list.append(pnl)
                if return_trades: trade_log.append((pos["bar"], i, float(pnl)))
                last_loss_bar = i if pnl < 0 else last_loss_bar; pos = None; continue
            continue

        sd = vwsd[i]
        if sd <= 0 or bis[i] < warmup_bars:
            continue
        if cooldown_bars > 0 and (i - last_loss_bar) < cooldown_bars:
            continue
        if flat_eod and last[i]:
            continue

        dist = closes[i] - vwap[i]
        stretched_dn = dist < -band_mult * sd     # below VWAP → candidate BUY
        stretched_up = dist >  band_mult * sd     # above VWAP → candidate SELL

        # regime gate: which side is allowed right now
        allow_long, allow_short = cap_long, cap_short
        if use_regime:
            up = bool(trend_up[i])
            if regime_mode == "with_trend":
                allow_long  = allow_long  and up           # buy dips only in uptrend
                allow_short = allow_short and (not up)      # sell rips only in downtrend
            else:  # against_trend
                allow_long  = allow_long  and (not up)
                allow_short = allow_short and up

        ep = closes[i]
        if stretched_dn and allow_long:
            pos = {"side": +1, "bar": i, "ep": ep, "sl": ep - stop_mult * sd}
        elif stretched_up and allow_short:
            pos = {"side": -1, "bar": i, "ep": ep, "sl": ep + stop_mult * sd}

    if pos is not None:
        pnl = (closes[-1] - pos["ep"]) if pos["side"] > 0 else (pos["ep"] - closes[-1])
        pnl_list.append(pnl)
        if return_trades: trade_log.append((pos["bar"], n - 1, float(pnl)))

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
