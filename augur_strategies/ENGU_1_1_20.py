"""
ENGU Strategy Plugin for Augur
--------------------------------------------------------------------
Strategy: GROK ENGU/ES (I) v20
Logic:    Bullish engulfing candle that breaks out of a prior bearish
          consolidation phase.  Long-only.  Works on futures (ES, NQ)
          and stocks at 1m-1h timeframes.

Ported from Pine Script v6 by Augur auto-translation.
--------------------------------------------------------------------
"""

import numpy as np

# -- Identity -----------------------------------------------------------------
STRATEGY_NAME = 'ENGU 1.1.20 (GROK)'
DESCRIPTION   = (
    "Detects a strong bullish engulfing candle that appears after a bearish "
    "consolidation window. The breakout candle must be significantly larger "
    "than recent candles, signalling a momentum burst against the short-term trend."
)
VERSION       = "1.0"
DIRECTION     = "LONG"   # LONG / SHORT / BOTH

# -- Default parameters (used for the Custom scope UI) ------------------------
DEFAULT_PARAMS = {
    "lookback_len": {
        "default": 13, "min": 3, "max": 30, "step": 1, "type": "int",
        "label": "Trend Lookback (Candles)",
        "tooltip": "How many candles back to classify the prior trend.",
    },
    "min_red_dominance": {
        "default": 0.60, "min": 0.50, "max": 0.90, "step": 0.05, "type": "float",
        "label": "Min Red % in Lookback",
        "tooltip": "Fraction of lookback candles that must be bearish.",
    },
    "min_breakout_pts": {
        "default": 9.0, "min": 0.5, "max": 50.0, "step": 0.5, "type": "float",
        "label": "Min Breakout Size (Points)",
        "tooltip": "Breakout candle body must be at least this many price points.",
        "depends_on": {"use_percent": False},
    },
    "use_percent": {
        "default": False, "type": "bool",
        "label": "Use % Instead of Points",
        "tooltip": "Switch breakout sizing from absolute points to a % of price.",
    },
    "min_breakout_pct": {
        "default": 0.25, "min": 0.01, "max": 5.0, "step": 0.05, "type": "float",
        "label": "Min Breakout Size (%)",
        "tooltip": "Breakout body as % of price (only active when Use % = True).",
        "depends_on": {"use_percent": True},
    },
    "prev_body_lookback": {
        "default": 4, "min": 1, "max": 10, "step": 1, "type": "int",
        "label": "Prev Candles for Body Comparison",
        "tooltip": "How many prior candles to check for small bodies.",
    },
    "max_body_ratio": {
        "default": 0.50, "min": 0.10, "max": 1.0, "step": 0.05, "type": "float",
        "label": "Max Prev Body / Breakout Body Ratio",
        "tooltip": "Prior candle bodies must be this fraction of the breakout body or smaller.",
    },
    "rr_input": {
        "default": 2.0, "min": 0.5, "max": 10.0, "step": 0.1, "type": "float",
        "label": "Risk / Reward Ratio",
        "tooltip": "Sets take-profit distance: entry + body x R:R.",
    },
    "be_bars": {
        "default": 2, "min": 0, "max": 20, "step": 1, "type": "int",
        "label": "Bars Before Breakeven",
        "tooltip": "After this many bars in a profitable trade, move stop to entry.",
    },
}

# -- Optimisation grid presets ------------------------------------------------
PARAM_GRID_PRESETS = {
    "Short  (~216 combos  . ~5 sec)": {
        "lookback_len":       [8, 13, 18],
        "min_red_dominance":  [0.60, 0.70],
        "min_breakout_pts":   [5.0, 9.0, 13.0],
        "use_percent":        [False],
        "min_breakout_pct":   [0.25],
        "max_body_ratio":     [0.40, 0.60],
        "prev_body_lookback": [3, 5],
        "rr_input":           [1.5, 2.0, 2.5],
        "be_bars":            [2],
    },
    "Medium (~1,458 combos . ~30 sec)": {
        "lookback_len":       [8, 13, 18],
        "min_red_dominance":  [0.55, 0.65, 0.75],
        "min_breakout_pts":   [5.0, 9.0, 13.0],
        "use_percent":        [False],
        "min_breakout_pct":   [0.25],
        "max_body_ratio":     [0.35, 0.50, 0.65],
        "prev_body_lookback": [3, 5],
        "rr_input":           [1.5, 2.0, 2.5],
        "be_bars":            [1, 2, 3],
    },
    "Long   (~5,400 combos . ~2 min)": {
        "lookback_len":       [5, 8, 13, 18, 23],
        "min_red_dominance":  [0.55, 0.65, 0.75],
        "min_breakout_pts":   [4.0, 7.0, 10.0, 13.0],
        "use_percent":        [False],
        "min_breakout_pct":   [0.25],
        "max_body_ratio":     [0.30, 0.45, 0.60],
        "prev_body_lookback": [3, 5],
        "rr_input":           [1.0, 1.5, 2.0, 2.5, 3.0],
        "be_bars":            [1, 2, 3],
    },
}


# -- Core backtest engine -----------------------------------------------------
def run_backtest(
    opens: np.ndarray, highs: np.ndarray,
    lows:  np.ndarray, closes: np.ndarray,
    lookback_len: int       = 13,
    min_red_dominance: float = 0.60,
    min_breakout_pts: float  = 9.0,
    use_percent: bool        = False,
    min_breakout_pct: float  = 0.25,
    max_body_ratio: float    = 0.50,
    prev_body_lookback: int  = 4,
    rr_input: float          = 2.0,
    be_bars: int             = 2,
    return_trades: bool      = False,
    # stop/pause events injected by executor -- ignored here but must be accepted
    _stop_event=None, _pause_event=None,
) -> dict | None:
    """
    Bar-by-bar simulation -- faithful Python port of Pine Script v20.

    Entry  : close of signal bar
    Stop   : bar low fill (pessimistic)
    Target : bar high fill (optimistic)
    BE     : after be_bars bars in profit -> move stop to entry
    """
    n         = len(closes)
    start_idx = max(lookback_len + 1, prev_body_lookback + 1)
    pnl_list  = []
    trade_log = []
    pos       = None

    for i in range(start_idx, n):

        # -- POSITION MANAGEMENT ------------------------------------------
        if pos is not None:
            bars_in = i - pos["bar"]

            if lows[i] <= pos["sl"]:                          # stop hit
                pnl = pos["sl"] - pos["ep"]
                pnl_list.append(pnl)
                if return_trades: trade_log.append((pos["bar"], i, pnl))
                pos = None; continue

            if highs[i] >= pos["tp"]:                         # target hit
                pnl = pos["tp"] - pos["ep"]
                pnl_list.append(pnl)
                if return_trades: trade_log.append((pos["bar"], i, pnl))
                pos = None; continue

            if be_bars > 0 and bars_in >= be_bars:            # breakeven
                cc = closes[i]
                if cc > pos["ep"] and pos["sl"] < pos["ep"]:
                    pos["sl"] = pos["ep"]
                elif cc < pos["ep"]:
                    pos["tp"] = pos["ep"]

            continue   # pyramiding = 0

        # -- SIGNAL DETECTION ---------------------------------------------
        red = sum(1 for j in range(1, lookback_len + 1)
                  if closes[i - j] < opens[i - j])
        if red / lookback_len < min_red_dominance:  continue  # not bearish enough
        if closes[i] <= opens[i]:                   continue  # must be green

        body = closes[i] - opens[i]
        if use_percent:
            if body / opens[i] * 100 < min_breakout_pct: continue
        else:
            if body < min_breakout_pts:               continue

        cnt = min(prev_body_lookback, i)
        if any(abs(closes[i-j] - opens[i-j]) > max_body_ratio * body
               for j in range(1, cnt + 1)):          continue

        # -- ENTER LONG ---------------------------------------------------
        ep  = closes[i]
        pos = {"bar": i, "ep": ep, "sl": ep - body, "tp": ep + body * rr_input}

    # Force-close open trade
    if pos is not None:
        pnl = closes[-1] - pos["ep"]
        pnl_list.append(pnl)
        if return_trades: trade_log.append((pos["bar"], n - 1, pnl))

    if not pnl_list:
        return None

    pnls  = np.array(pnl_list, dtype=float)
    wins  = pnls[pnls > 0]
    losses= pnls[pnls < 0]
    cum   = np.cumsum(pnls)
    max_dd= float((cum - np.maximum.accumulate(cum)).min())

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
