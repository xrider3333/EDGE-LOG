"""
CLAUDE ENGU (I) v25 -- Consolidation Breakout Strategy Plugin for Augur
--------------------------------------------------------------------------
Ported from the Pine Script v5 strategy "CLAUDE ENGU (I) v25".

Logic summary
=============
A breakout fires when price closes beyond a prior consolidation range
(highest high / lowest low of the last `lookback_bars`) with a candle body
large enough relative to that range, AND it passes the enabled filters:

  * Opposite Momentum : no large opposing candle in the recent scan window
  * ATR Expansion     : body must exceed ATR x multiplier
  * Volume            : volume must exceed its average x multiplier
  * Trend (EMA)       : close on the correct side of the EMA

Direction control (Long Only / Short Only / Both) and an Invert Signals
toggle are supported.  Exits use a stop / target sized as a multiple of the
consolidation range, with optional trailing stop, matching the Pine logic.

Notes vs the Pine version
=========================
* Chart-only features (tables, labels, boxes, colours, S/D pivot scoring,
  session-quality scorecard) are omitted -- they don't affect backtest P&L.
* VWAP trend option is omitted (needs intraday session anchoring + volume
  that isn't reliably available bar-only); EMA trend is used.  This matches
  the Pine default (trendType = "EMA").
* Volume filter is auto-skipped when no volume series is supplied.

Author: Augur auto-translation
--------------------------------------------------------------------------
"""

import numpy as np

# -- Identity -----------------------------------------------------------------
STRATEGY_NAME = 'ENGU 1.3.4 · tight-consolidation (CLAUDE)'
DESCRIPTION   = (
    "Range-consolidation breakout. Price must close beyond the prior "
    "lookback range with a body large vs the range, passing optional "
    "opposite-momentum, ATR, volume and EMA-trend filters. Trades long "
    "and/or short with range-multiple stop/target and optional trailing."
)
VERSION   = "25.0"
DIRECTION = "BOTH"   # LONG / SHORT / BOTH

# -- Default parameters (drive the Custom scope UI) ---------------------------
DEFAULT_PARAMS = {
    "lookback_bars": {
        "default": 20, "min": 3, "max": 60, "step": 1, "type": "int",
        "label": "Range Lookback (bars)",
        "tooltip": "Bars used to measure the prior consolidation range "
                   "(highest high / lowest low).",
    },
    "body_multiplier": {
        "default": 0.7, "min": 0.1, "max": 3.0, "step": 0.1, "type": "float",
        "label": "Min Body Size (x range)",
        "tooltip": "Breakout candle body must be at least this fraction of "
                   "the consolidation range.",
    },

    # ---- Opposite-momentum filter ----
    "use_opp_filter": {
        "default": True, "type": "bool",
        "label": "Opposite Momentum Filter",
        "tooltip": "Veto a breakout if a large opposing candle appeared "
                   "in the recent scan window.",
    },
    "opp_lookback": {
        "default": 20, "min": 1, "max": 60, "step": 1, "type": "int",
        "label": "Opp. Scan Bars",
        "tooltip": "How many prior bars to scan for opposing momentum.",
        "depends_on": {"use_opp_filter": True},
    },
    "opp_threshold": {
        "default": 0.6, "min": 0.1, "max": 2.0, "step": 0.05, "type": "float",
        "label": "Opp. Max Size (x body)",
        "tooltip": "An opposing candle bigger than this fraction of the "
                   "breakout body vetoes the signal.",
        "depends_on": {"use_opp_filter": True},
    },

    # ---- ATR-expansion filter ----
    "use_atr": {
        "default": True, "type": "bool",
        "label": "ATR Expansion Filter",
        "tooltip": "Require the breakout body to exceed ATR x multiplier.",
    },
    "atr_length": {
        "default": 20, "min": 1, "max": 60, "step": 1, "type": "int",
        "label": "ATR Period",
        "tooltip": "Lookback period for the Average True Range.",
        "depends_on": {"use_atr": True},
    },
    "atr_multiplier": {
        "default": 1.7, "min": 0.1, "max": 5.0, "step": 0.1, "type": "float",
        "label": "ATR Min Size (x)",
        "tooltip": "Breakout body must exceed ATR x this multiplier.",
        "depends_on": {"use_atr": True},
    },

    # ---- Volume filter ----
    "use_volume": {
        "default": True, "type": "bool",
        "label": "Volume Filter",
        "tooltip": "Require breakout volume above its average x multiplier. "
                   "Auto-skipped if no volume data is available.",
    },
    "vol_length": {
        "default": 20, "min": 1, "max": 60, "step": 1, "type": "int",
        "label": "Volume Avg Period",
        "tooltip": "Lookback period for the average volume.",
        "depends_on": {"use_volume": True},
    },
    "vol_multiplier": {
        "default": 1.3, "min": 0.1, "max": 5.0, "step": 0.1, "type": "float",
        "label": "Volume Min (x avg)",
        "tooltip": "Breakout volume must exceed average x this multiplier.",
        "depends_on": {"use_volume": True},
    },

    # ---- Trend filter (EMA) ----
    "use_trend": {
        "default": True, "type": "bool",
        "label": "EMA Trend Filter",
        "tooltip": "Require close on the breakout side of the EMA "
                   "(bull: above, bear: below).",
    },
    "ema_length": {
        "default": 20, "min": 1, "max": 200, "step": 1, "type": "int",
        "label": "EMA Length",
        "tooltip": "Length of the trend EMA.",
        "depends_on": {"use_trend": True},
    },

    # ---- Direction / exits ----
    "trade_mode": {
        "default": "Both", "type": "str", "options": ["Long Only", "Short Only", "Both"],
        "label": "Trade Direction",
        "tooltip": "Restrict entries to longs, shorts, or allow both.",
    },
    "invert_signal": {
        "default": False, "type": "bool",
        "label": "Invert Signals",
        "tooltip": "Take the opposite side of every signal "
                   "(bull->short, bear->long).",
    },
    "stop_mult": {
        "default": 1.0, "min": 0.1, "max": 5.0, "step": 0.1, "type": "float",
        "label": "Stop Loss (x range)",
        "tooltip": "Stop distance as a multiple of the consolidation range.",
    },
    "tp_mult": {
        "default": 2.0, "min": 0.1, "max": 10.0, "step": 0.1, "type": "float",
        "label": "Take Profit (x range)",
        "tooltip": "Target distance as a multiple of the consolidation range. "
                   "Ignored when Exit Mode = 'Stop Only'.",
    },
    "exit_mode": {
        "default": "Stop / Target", "type": "str",
        "options": ["Stop / Target", "Stop Only", "Next Opposite Signal"],
        "label": "Exit Method",
        "tooltip": "Stop/Target = exit on stop OR target.\n"
                   "Stop Only = stop, no target.\n"
                   "Next Opposite Signal = hold until an opposing breakout.",
    },
    "trail_stop": {
        "default": False, "type": "bool",
        "label": "Trailing Stop",
        "tooltip": "Replace the fixed stop with a trailing stop "
                   "(distance = Stop Loss x range).",
    },
    "breakout_buffer": {
        "default": 0.0, "min": 0.0, "max": 0.5, "step": 0.05, "type": "float",
        "label": "Breakout Buffer (x range)",
        "tooltip": "Require the close to clear the prior range by this fraction of "
                   "the range before a breakout counts — filters marginal/false "
                   "breakouts. 0 = off (original behaviour).",
    },
    "cooldown_bars": {
        "default": 0, "min": 0, "max": 20, "step": 1, "type": "int",
        "label": "Post-loss Cooldown (bars)",
        "tooltip": "After a losing trade, wait this many bars before taking a new "
                   "entry — curbs whipsaw re-entries in chop. 0 = off.",
    },
    "use_tight": {
        "default": False, "type": "bool",
        "label": "Tight-Consolidation Filter",
        "tooltip": "Only take breakouts from a consolidation that is TIGHT relative "
                   "to the recent average range (a coiled spring) — filters breakouts "
                   "out of wide / choppy ranges that tend to fail.",
    },
    "tight_lb": {
        "default": 50, "min": 10, "max": 150, "step": 10, "type": "int",
        "label": "Tightness Lookback", "depends_on": {"use_tight": True},
        "tooltip": "Bars used for the baseline average range.",
    },
    "tight_k": {
        "default": 1.0, "min": 0.4, "max": 1.6, "step": 0.1, "type": "float",
        "label": "Tightness Threshold (x avg range)", "depends_on": {"use_tight": True},
        "tooltip": "Setup range must be below this multiple of the baseline average "
                   "range. Lower = tighter / more selective.",
    },
}

# -- Optimisation grid presets ------------------------------------------------
# Conditional params (depends_on) collapse automatically in Augur's combo
# counter, so toggles set to a single value don't multiply the grid.
PARAM_GRID_PRESETS = {
    "Short  (fast scan)": {
        "lookback_bars":   [15, 20, 25],
        "body_multiplier": [0.5, 0.7, 0.9],
        "use_opp_filter":  [True],
        "opp_lookback":    [20],
        "opp_threshold":   [0.6],
        "use_atr":         [True],
        "atr_length":      [20],
        "atr_multiplier":  [1.3, 1.7, 2.1],
        "use_volume":      [True],
        "vol_length":      [20],
        "vol_multiplier":  [1.3],
        "use_trend":       [True],
        "ema_length":      [20],
        "trade_mode":      ["Both"],
        "invert_signal":   [False],
        "stop_mult":       [1.0],
        "tp_mult":         [1.5, 2.0, 2.5],
        "exit_mode":       ["Stop / Target"],
        "trail_stop":      [False],
    },
    "Medium (balanced)": {
        "lookback_bars":   [10, 15, 20, 25],
        "body_multiplier": [0.5, 0.7, 0.9],
        "use_opp_filter":  [True],
        "opp_lookback":    [15, 25],
        "opp_threshold":   [0.6],
        "use_atr":         [True],
        "atr_length":      [14, 20],
        "atr_multiplier":  [1.3, 1.7, 2.1],
        "use_volume":      [True],
        "vol_length":      [20],
        "vol_multiplier":  [1.1, 1.3, 1.5],
        "use_trend":       [True],
        "ema_length":      [20, 50],
        "trade_mode":      ["Both"],
        "invert_signal":   [False],
        "stop_mult":       [0.7, 1.0],
        "tp_mult":         [1.5, 2.0, 2.5],
        "exit_mode":       ["Stop / Target"],
        "trail_stop":      [False],
    },
    "Long   (deep sweep)": {
        "lookback_bars":   [10, 15, 20, 25, 30],
        "body_multiplier": [0.4, 0.6, 0.8, 1.0],
        "use_opp_filter":  [True, False],
        "opp_lookback":    [15, 25],
        "opp_threshold":   [0.5, 0.7],
        "use_atr":         [True],
        "atr_length":      [14, 20],
        "atr_multiplier":  [1.3, 1.7, 2.1],
        "use_volume":      [True, False],
        "vol_length":      [20],
        "vol_multiplier":  [1.1, 1.3, 1.5],
        "use_trend":       [True],
        "ema_length":      [20, 50],
        "trade_mode":      ["Long Only", "Short Only", "Both"],
        "invert_signal":   [False],
        "stop_mult":       [0.7, 1.0, 1.3],
        "tp_mult":         [1.5, 2.0, 2.5, 3.0],
        "exit_mode":       ["Stop / Target", "Stop Only"],
        "trail_stop":      [False, True],
    },
}


# -- Indicator helpers (vectorised) -------------------------------------------
def _ema(arr, length):
    length = max(1, int(length))
    alpha = 2.0 / (length + 1.0)
    out = np.empty_like(arr, dtype=float)
    out[0] = arr[0]
    for i in range(1, len(arr)):
        out[i] = alpha * arr[i] + (1 - alpha) * out[i - 1]
    return out


def _atr(highs, lows, closes, length):
    length = max(1, int(length))
    n = len(closes)
    tr = np.empty(n, dtype=float)
    tr[0] = highs[0] - lows[0]
    for i in range(1, n):
        hl = highs[i] - lows[i]
        hc = abs(highs[i] - closes[i - 1])
        lc = abs(lows[i] - closes[i - 1])
        tr[i] = max(hl, hc, lc)
    # Wilder-style RMA approximation via simple rolling mean (matches ta.atr closely)
    atr = np.full(n, np.nan, dtype=float)
    if n >= length:
        atr[length - 1] = tr[:length].mean()
        for i in range(length, n):
            atr[i] = (atr[i - 1] * (length - 1) + tr[i]) / length
    return atr


def _rolling_max(arr, length):
    n = len(arr); out = np.full(n, np.nan)
    for i in range(n):
        lo = max(0, i - length + 1)
        out[i] = arr[lo:i + 1].max()
    return out


def _rolling_min(arr, length):
    n = len(arr); out = np.full(n, np.nan)
    for i in range(n):
        lo = max(0, i - length + 1)
        out[i] = arr[lo:i + 1].min()
    return out


def _sma(arr, length):
    length = max(1, int(length))
    n = len(arr); out = np.full(n, np.nan)
    csum = np.cumsum(np.insert(arr, 0, 0.0))
    for i in range(n):
        if i >= length - 1:
            out[i] = (csum[i + 1] - csum[i + 1 - length]) / length
    return out


# -- Core backtest engine -----------------------------------------------------
def run_backtest(
    opens: np.ndarray, highs: np.ndarray,
    lows:  np.ndarray, closes: np.ndarray,
    volumes: np.ndarray = None,
    lookback_bars: int       = 20,
    body_multiplier: float   = 0.7,
    use_opp_filter: bool     = True,
    opp_lookback: int        = 20,
    opp_threshold: float     = 0.6,
    use_atr: bool            = True,
    atr_length: int          = 20,
    atr_multiplier: float    = 1.7,
    use_volume: bool         = True,
    vol_length: int          = 20,
    vol_multiplier: float    = 1.3,
    use_trend: bool          = True,
    ema_length: int          = 20,
    trade_mode: str          = "Both",
    invert_signal: bool      = False,
    stop_mult: float         = 1.0,
    tp_mult: float           = 2.0,
    exit_mode: str           = "Stop / Target",
    trail_stop: bool         = False,
    breakout_buffer: float   = 0.0,
    cooldown_bars: int       = 0,
    use_tight: bool          = False,
    tight_lb: int            = 50,
    tight_k: float           = 1.0,
    return_trades: bool      = False,
    _stop_event=None, _pause_event=None,
) -> dict | None:
    """
    Bar-by-bar simulation. Signal is evaluated on the close of bar i using the
    prior range (highest high / lowest low of bars i-lookback .. i-1), exactly
    like the Pine `ta.highest(high[1], lookbackBars)`.

    Fills (pessimistic/optimistic, matching the original engu.py convention):
      * long  : stop on bar low, target on bar high
      * short : stop on bar high, target on bar low
    """
    opens  = np.asarray(opens,  dtype=float)
    highs  = np.asarray(highs,  dtype=float)
    lows   = np.asarray(lows,   dtype=float)
    closes = np.asarray(closes, dtype=float)
    n = len(closes)
    if n < 5:
        return None

    have_vol = volumes is not None and len(volumes) == n and np.nansum(volumes) > 0
    if have_vol:
        volumes = np.asarray(volumes, dtype=float)

    bodies = np.abs(closes - opens)

    # Prior range: shift by 1 so bar i uses bars i-lookback..i-1
    hh_prev = np.full(n, np.nan)
    ll_prev = np.full(n, np.nan)
    rmax = _rolling_max(highs, lookback_bars)
    rmin = _rolling_min(lows,  lookback_bars)
    hh_prev[1:] = rmax[:-1]
    ll_prev[1:] = rmin[:-1]

    atr_arr = _atr(highs, lows, closes, atr_length) if use_atr else None
    ema_arr = _ema(closes, ema_length) if use_trend else None
    vol_avg = _sma(volumes, vol_length) if (use_volume and have_vol) else None
    avg_range = (_sma(np.asarray(highs, dtype=float) - np.asarray(lows, dtype=float), tight_lb)
                 if use_tight else None)

    allow_long  = trade_mode in ("Long Only", "Both")
    allow_short = trade_mode in ("Short Only", "Both")

    start_idx = max(lookback_bars + 1, atr_length if use_atr else 0,
                    vol_length if (use_volume and have_vol) else 0,
                    ema_length if use_trend else 0, opp_lookback + 1,
                    tight_lb if use_tight else 0) + 1

    pnl_list, trade_log = [], []
    pos = None   # dict: side(+1/-1), bar, ep, sl, tp
    last_loss_bar = -10**9   # for the optional post-loss re-entry cooldown

    for i in range(start_idx, n):

        # -- POSITION MANAGEMENT ------------------------------------------
        if pos is not None:
            side = pos["side"]

            # Trailing stop adjust (distance = range_at_entry * stop_mult)
            if trail_stop:
                if side > 0:
                    new_sl = highs[i] - pos["trail_dist"]
                    if new_sl > pos["sl"]:
                        pos["sl"] = new_sl
                else:
                    new_sl = lows[i] + pos["trail_dist"]
                    if new_sl < pos["sl"]:
                        pos["sl"] = new_sl

            if side > 0:   # long
                if lows[i] <= pos["sl"]:
                    pnl = pos["sl"] - pos["ep"]
                    pnl_list.append(pnl)
                    if return_trades: trade_log.append((pos["bar"], i, pnl))
                    last_loss_bar = (i if pnl < 0 else last_loss_bar)
                    pos = None; continue
                if pos["tp"] is not None and highs[i] >= pos["tp"]:
                    pnl = pos["tp"] - pos["ep"]
                    pnl_list.append(pnl)
                    if return_trades: trade_log.append((pos["bar"], i, pnl))
                    last_loss_bar = (i if pnl < 0 else last_loss_bar)
                    pos = None; continue
            else:          # short
                if highs[i] >= pos["sl"]:
                    pnl = pos["ep"] - pos["sl"]
                    pnl_list.append(pnl)
                    if return_trades: trade_log.append((pos["bar"], i, pnl))
                    last_loss_bar = (i if pnl < 0 else last_loss_bar)
                    pos = None; continue
                if pos["tp"] is not None and lows[i] <= pos["tp"]:
                    pnl = pos["ep"] - pos["tp"]
                    pnl_list.append(pnl)
                    if return_trades: trade_log.append((pos["bar"], i, pnl))
                    last_loss_bar = (i if pnl < 0 else last_loss_bar)
                    pos = None; continue

        # -- SIGNAL DETECTION ---------------------------------------------
        hh = hh_prev[i]; ll = ll_prev[i]
        if np.isnan(hh) or np.isnan(ll):
            continue
        rng = hh - ll
        if rng <= 0:
            continue

        body = bodies[i]
        body_ok = body > rng * body_multiplier
        if not body_ok:
            continue

        bull = closes[i] > opens[i]
        bear = closes[i] < opens[i]

        # Breakout buffer: require the close to clear the level by buffer x range
        # (filters marginal / false breakouts). 0.0 = original behaviour.
        _bo = rng * breakout_buffer
        raw_bull = bull and closes[i] > hh + _bo
        raw_bear = bear and closes[i] < ll - _bo
        if not (raw_bull or raw_bear):
            continue

        # Opposite-momentum filter
        opp_pass_bull = opp_pass_bear = True
        if use_opp_filter:
            for k in range(1, opp_lookback + 1):
                pb = abs(closes[i - k] - opens[i - k])
                if closes[i - k] < opens[i - k] and pb > body * opp_threshold:
                    opp_pass_bull = False
                if closes[i - k] > opens[i - k] and pb > body * opp_threshold:
                    opp_pass_bear = False
                if not opp_pass_bull and not opp_pass_bear:
                    break

        # ATR filter
        atr_pass = True
        if use_atr:
            a = atr_arr[i]
            atr_pass = (not np.isnan(a)) and body > a * atr_multiplier

        # Volume filter (skipped automatically when no volume data)
        vol_pass = True
        if use_volume and have_vol:
            va = vol_avg[i]
            vol_pass = (not np.isnan(va)) and volumes[i] > va * vol_multiplier

        # Trend filter (EMA)
        trend_bull = trend_bear = True
        if use_trend:
            e = ema_arr[i]
            trend_bull = closes[i] > e
            trend_bear = closes[i] < e

        # Tight-consolidation filter: the setup's prior range must be tight vs the
        # recent average range (a coiled spring), filtering breakouts from wide / choppy
        # ranges that tend to fail. Off (use_tight=False) = original behaviour.
        tight_pass = True
        if use_tight:
            ar = avg_range[i]
            tight_pass = (not np.isnan(ar)) and ar > 0 and rng <= ar * tight_k

        bull_sig = raw_bull and opp_pass_bull and atr_pass and vol_pass and trend_bull and tight_pass
        bear_sig = raw_bear and opp_pass_bear and atr_pass and vol_pass and trend_bear and tight_pass

        if not (bull_sig or bear_sig):
            continue

        # Resolve direction (with optional inversion)
        if invert_signal:
            go_long  = bear_sig
            go_short = bull_sig
        else:
            go_long  = bull_sig
            go_short = bear_sig

        # Next-opposite-signal exit: close existing pos on an opposing signal
        if exit_mode == "Next Opposite Signal" and pos is not None:
            if pos["side"] > 0 and go_short:
                pnl = closes[i] - pos["ep"]
                pnl_list.append(pnl)
                if return_trades: trade_log.append((pos["bar"], i, pnl))
                pos = None
            elif pos["side"] < 0 and go_long:
                pnl = pos["ep"] - closes[i]
                pnl_list.append(pnl)
                if return_trades: trade_log.append((pos["bar"], i, pnl))
                pos = None

        if pos is not None:
            continue  # no pyramiding

        # Post-loss re-entry cooldown: after a losing exit, skip new entries for
        # cooldown_bars bars (curbs revenge/whipsaw entries in chop). 0 = off.
        if cooldown_bars > 0 and (i - last_loss_bar) < cooldown_bars:
            continue

        ep = closes[i]
        want_tp = (exit_mode == "Stop / Target")

        if go_long and allow_long:
            sl = ep - rng * stop_mult
            tp = ep + rng * tp_mult if want_tp else None
            pos = {"side": +1, "bar": i, "ep": ep, "sl": sl, "tp": tp,
                   "trail_dist": rng * stop_mult}
        elif go_short and allow_short:
            sl = ep + rng * stop_mult
            tp = ep - rng * tp_mult if want_tp else None
            pos = {"side": -1, "bar": i, "ep": ep, "sl": sl, "tp": tp,
                   "trail_dist": rng * stop_mult}

    # Force-close any open trade at the last bar
    if pos is not None:
        if pos["side"] > 0:
            pnl = closes[-1] - pos["ep"]
        else:
            pnl = pos["ep"] - closes[-1]
        pnl_list.append(pnl)
        if return_trades: trade_log.append((pos["bar"], n - 1, pnl))

    if not pnl_list:
        return None

    pnls   = np.array(pnl_list, dtype=float)
    wins   = pnls[pnls > 0]
    losses = pnls[pnls < 0]
    cum    = np.cumsum(pnls)
    max_dd = float((cum - np.maximum.accumulate(cum)).min())

    out = {
        "total_pnl":     round(float(pnls.sum()), 2),
        "num_trades":    len(pnls),
        "win_rate":      round(len(wins) / len(pnls) * 100, 1),
        "profit_factor": round(float(wins.sum()) / max(abs(float(losses.sum())), 1e-9), 2),
        "max_drawdown":  round(max_dd, 2),
        "avg_pnl":       round(float(pnls.mean()), 2),
        "wins":          int(len(wins)),
        "losses":        int(len(losses)),
    }
    if return_trades:
        out["trades"] = trade_log
    return out


# ── Augur AI-evolved profile — baked-in defaults (original: ENGU_3_evo.py) ──
_AUGUR_TUNED = {'lookback_bars': 18, 'body_multiplier': 0.4, 'use_opp_filter': False, 'opp_lookback': 15, 'opp_threshold': 0.6, 'use_atr': False, 'atr_length': 20, 'atr_multiplier': 1.3, 'use_volume': False, 'vol_length': 20, 'vol_multiplier': 1.0, 'use_trend': True, 'ema_length': 100, 'trade_mode': 'Both', 'invert_signal': False, 'stop_mult': 1.3, 'tp_mult': 1.3, 'exit_mode': 'Stop / Target', 'trail_stop': True, 'breakout_buffer': 0.45, 'cooldown_bars': 4}
try:
    for _k, _v in _AUGUR_TUNED.items():
        if _k in DEFAULT_PARAMS:
            DEFAULT_PARAMS[_k]['default'] = _v
except Exception:
    pass
_AUGUR_TUNED_METRICS = {'in_sample_pnl_usd': 12044, 'in_sample_pf': 2.31, 'in_sample_trades': 35, 'out_of_sample_pnl_usd': 3416, 'out_of_sample_pf': 2.69, 'out_of_sample_trades': 11, 'rounds': 5, 'instrument': 'ES', 'timeframe': '5m', 'source': 'ES 5min csv', 'code_changes': ['+breakout_buffer (filter marginal breakouts)', '+cooldown_bars (post-loss re-entry cooldown)'], 'robustness_score_orig': 1.768, 'robustness_score_evolved': 2.313}


# ── Augur v1.3.3 profile — baked-in defaults (original: ENGU_1_3_2.py) ──
_AUGUR_TUNED = {'lookback_bars': 15, 'body_multiplier': 0.4, 'use_opp_filter': False, 'opp_lookback': 15, 'opp_threshold': 0.4, 'use_atr': True, 'atr_length': 20, 'atr_multiplier': 1.0, 'use_volume': True, 'vol_length': 20, 'vol_multiplier': 1.0, 'use_trend': False, 'ema_length': 150, 'trade_mode': 'Both', 'invert_signal': False, 'stop_mult': 1.3, 'tp_mult': 1.3, 'exit_mode': 'Stop / Target', 'trail_stop': True, 'breakout_buffer': 0.4, 'cooldown_bars': 0}
try:
    for _k, _v in _AUGUR_TUNED.items():
        if _k in DEFAULT_PARAMS:
            DEFAULT_PARAMS[_k]['default'] = _v
except Exception:
    pass
_AUGUR_TUNED_METRICS = {'version': '1.3.3', 'parent': '1.3.2', 'train_pf': 2.62, 'gate_folds_held': '2/3', 'gate_avg_oos_pf': np.float64(1.18), 'gate_oos_pnl_usd': 371, 'gate_oos_trades': 36, 'data': 'ES 5m master (TV+Yahoo)', 'instrument': 'ES', 'timeframe': '5m'}


_AUGUR_LINEAGE = {'version': '1.3.3', 'parent_version': '1.3.2', 'parent_file': 'ENGU_1_3_2.py', 'model': 'ENGU', 'base': 3, 'iteration': 3, 'data': 'ES 5m master (TV+Yahoo)', 'gate': 'walk-forward 3 held-out windows on the longer master', 'gate_folds_held': '2/3', 'gate_avg_oos_pf': np.float64(1.18), 'reasoning': 'Resumed 1.3.2 (breakout_buffer+cooldown code); re-optimized on the train 60% of the Mar-Jun master, then walk-forward gated the top candidates on the held-out 40%. Kept the highest-ranked config that survived the gate.'}
