"""
OVERNIGHT HOLD — capture the overnight risk-premium, sit out the cash session.

The 16yr ES/NQ diagnostic (tools/intraday_diag.py) showed the overnight session
(prior RTH close -> next RTH open) carries ~2x the risk-adjusted return of the
RTH session, and nearly the same Sharpe as buy-and-hold while in the market less
than half the time. This strategy trades ONLY that window:

  • enter at each session's LAST bar close  (the RTH close)
  • exit  at the next session's FIRST bar open (the next RTH open)
  • hold nothing during the cash session.

On an RTH-only master the gap between one session's last bar and the next
session's first bar IS the overnight move, so the trade = open[next] - close[prev].

Deliberately LOW parameter count (the point — minimal degrees of freedom):
  • direction (default Long Only)
  • optional trend gate: only hold overnight when the prior session closed above a
    simple moving average of session closes (off by default — its job is to test
    whether the edge survives without bull-beta).
  • optional skip-Mondays / weekday filter is intentionally NOT included; keep it lean.

Needs per-bar session ids (day_id) + works on a RTH master. PNL = SHARES*(EXIT-ENTRY).
"""
import numpy as np

STRATEGY_NAME = 'OVERNIGHT HOLD 1.0 · close→open risk-premium'
DESCRIPTION   = ("Hold only the overnight session (RTH close → next RTH open), flat all "
                 "day. Captures the documented overnight risk-premium with ~1 trade/day "
                 "and almost no parameters. Optional trend gate to test edge-vs-beta.")

_AUGUR_MARKET = {"instrument": "ES", "timeframe": "5m"}

DEFAULT_PARAMS = {
    "trade_mode": {
        "default": "Long Only", "type": "str",
        "options": ["Long Only", "Short Only", "Both"],
        "label": "Direction",
        "tooltip": "Long Only = buy the close, sell the open (the documented tilt). "
                   "Short Only / Both are for research/symmetry checks.",
    },
    "trend_filter": {
        "default": True, "type": "bool",
        "label": "Trend gate (only hold in uptrends)",
        "tooltip": "Only take the overnight when the prior session closed ABOVE an SMA "
                   "of recent session closes. ON is the validated operating point: across "
                   "16yr it raised Sharpe 0.61->0.74 and cut the 2022 bear-year loss from "
                   "-$35k to -$9k (1 contract). OFF = pure overnight premium (more beta). "
                   "For shorts the gate flips (below the SMA).",
    },
    "trend_len": {
        "default": 50, "min": 2, "max": 200, "step": 1, "type": "int",
        "label": "Trend SMA (sessions)",
        "tooltip": "Lookback in SESSIONS for the trend gate's moving average. 50 (~10wk) "
                   "was the validated sweet spot; 100 similar. 20 whipsaws.",
        "depends_on": {"trend_filter": True},
    },
    "stop_pts": {
        "default": 0.0, "min": 0.0, "max": 200.0, "step": 5.0, "type": "float",
        "label": "Overnight stop (points, 0=off)",
        "tooltip": "Optional hard stop on the held position, in points, using the "
                   "session-low/high reached before the exit bar. 0 disables (pure "
                   "close→open). A realism knob — overnight gaps can be large.",
    },
}

PARAM_GRID_PRESETS = {
    "Short  (direction scan)": {
        "trade_mode": ["Long Only", "Short Only", "Both"],
        "trend_filter": [False], "trend_len": [20], "stop_pts": [0.0],
    },
    "Medium (trend gate)": {
        "trade_mode": ["Long Only", "Both"],
        "trend_filter": [False, True], "trend_len": [10, 20, 50],
        "stop_pts": [0.0],
    },
    "Long   (gate + stops)": {
        "trade_mode": ["Long Only", "Short Only", "Both"],
        "trend_filter": [False, True], "trend_len": [10, 20, 50, 100],
        "stop_pts": [0.0, 25.0, 50.0, 100.0],
    },
}


def _session_bounds(did, n):
    """Return arrays: is_first[i] (first bar of a session), and a list of
    (last_bar_of_prev, first_bar_of_cur) boundary pairs."""
    is_first = np.zeros(n, dtype=bool)
    is_first[0] = True
    if did is not None:
        is_first[1:] = did[1:] != did[:-1]
    else:
        # no session ids: cannot identify overnight — treat as one session (no trades)
        pass
    boundaries = [(i - 1, i) for i in range(1, n) if is_first[i]]
    return is_first, boundaries


def _session_closes(did, closes, n):
    """Per-session last close + the session id order, for the trend SMA."""
    if did is None:
        return None, None
    last_close = []
    sess_of_pair = []
    cur = did[0]
    last_c = closes[0]
    order = {}
    for i in range(1, n):
        if did[i] != did[i - 1]:
            order[did[i - 1]] = len(last_close)
            last_close.append(closes[i - 1])
            cur = did[i]
        last_c = closes[i]
    order[did[-1]] = len(last_close)
    last_close.append(closes[-1])
    return np.array(last_close, dtype=float), order


def run_backtest(
    opens, highs, lows, closes,
    volumes=None,
    trade_mode: str = "Long Only", trend_filter: bool = False,
    trend_len: int = 20, stop_pts: float = 0.0,
    day_id=None,
    return_trades: bool = False, _stop_event=None, _pause_event=None,
):
    opens = np.asarray(opens, float); highs = np.asarray(highs, float)
    lows = np.asarray(lows, float);   closes = np.asarray(closes, float)
    n = len(closes)
    if n < 10:
        return None

    did = np.asarray(day_id) if (day_id is not None and len(day_id) == n) else None
    if did is None:
        # Overnight requires session structure; nothing to do without it.
        return None

    is_first, boundaries = _session_bounds(did, n)
    if not boundaries:
        return None

    sess_close, sess_order = _session_closes(did, closes, n)
    sma = None
    if trend_filter and sess_close is not None and len(sess_close) > trend_len:
        sma = np.full(len(sess_close), np.nan)
        c = np.cumsum(np.insert(sess_close, 0, 0.0))
        sma[trend_len - 1:] = (c[trend_len:] - c[:-trend_len]) / trend_len

    allow_long  = trade_mode in ("Long Only", "Both")
    allow_short = trade_mode in ("Short Only", "Both")

    pnl_list, trade_log = [], []

    for (prev_i, cur_i) in boundaries:
        if _stop_event is not None and _stop_event.is_set():
            break
        entry = closes[prev_i]          # prior session's RTH close
        exit_ = opens[cur_i]            # next session's RTH open

        # trend gate uses the prior session's close vs SMA of session closes
        go_long = allow_long
        go_short = allow_short
        if trend_filter and sma is not None:
            si = sess_order.get(did[prev_i], None)
            if si is None or np.isnan(sma[si]):
                continue                # not enough history for the gate yet
            above = closes[prev_i] > sma[si]
            go_long = allow_long and above
            go_short = allow_short and (not above)

        side = 0
        if go_long:
            side = +1
        elif go_short:
            side = -1
        if side == 0:
            continue

        # optional overnight stop using the intervening low/high.
        # On an RTH master there are no overnight bars, so the only adverse
        # excursion we can see is the next session's first-bar range.
        if stop_pts and stop_pts > 0:
            if side > 0:
                stop_px = entry - stop_pts
                if lows[cur_i] <= stop_px:
                    exit_ = min(exit_, stop_px) if opens[cur_i] > stop_px else opens[cur_i]
            else:
                stop_px = entry + stop_pts
                if highs[cur_i] >= stop_px:
                    exit_ = max(exit_, stop_px) if opens[cur_i] < stop_px else opens[cur_i]

        pnl = (exit_ - entry) if side > 0 else (entry - exit_)
        pnl_list.append(pnl)
        if return_trades:
            trade_log.append((prev_i, cur_i, pnl))

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
