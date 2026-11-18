"""MISC MOCTREND 1.0 - late-day trend to the close on NQ: enter at `entry_min`, ride the day's direction to the 16:00 close.

# AUGUR-SOURCE: claude

Provenance: NOISE lane w132 catalogue re-run (tools/noise_w132_catalogue.py, cell MOC_TREND), NQ 5m RTH db_noadj_rth,
2016-05..2025-06, 1 contract, cost 0.783: +$11.8k/yr, owner loose screen PASS; harness book add on #463 = $152k/yr at
DD 15.1 pct. NOT A BLIND READ: the 15:00 cell was seen before this file was written; the engine's walk-forward and
lockbox judge it, and the open knobs (entry time, minimum move) are searched fresh.

-- The rule -----------------------------------------------------------------------------
On a regular full session (09:30 bar present, last bar 15:55 on 5m):
  * side = sign(open of the `entry_min` bar - open of the 09:30 bar), the day's direction so far;
  * skip when |that move| < `min_move` x ADR (ADR = mean full-session high-low of the previous 20 full
    sessions, strictly earlier days);
  * entry = open of the `entry_min` bar; exit = close of the last regular bar (the closing print).
One trade a day at most, never overnight, no stop, no target. Half days (no 15:55 bar) give no trade.

INFORMATION TIMES: the side reads the 09:30 open and the entry bar's own open, both known at entry. The
half-day test reads the session calendar shape only (a short session is known in advance).

-- Costs ----------------------------------------------------------------------------------
PnL is NQ points in the trade tuple; the job charges the round trip (cost_pts, mult 20).
"""
import numpy as np
import pandas as pd

STRATEGY_NAME = "MISC MOCTREND 1.0 · late-day trend to the close (NQ)"
DESCRIPTION = ("At the entry time, trade the direction of the day so far (entry-bar open vs the 09:30 open) "
               "and hold to the closing print. One trade a day, skip half days.")

_AUGUR_MARKET = {"instrument": "NQ", "timeframe": "5m", "session": "rth", "source": "db_noadj_rth"}

DEFAULT_PARAMS = {
    "entry_min": {"default": 900, "min": 840, "max": 930, "step": 15, "type": "int",
                  "label": "Entry time (minutes after midnight ET; 900 = 15:00)",
                  "tooltip": "Enter at the open of the bar starting at this minute."},
    "min_move": {"default": 0.0, "min": 0.0, "max": 0.6, "step": 0.2, "type": "float",
                 "label": "Minimum move so far (x average daily range)",
                 "tooltip": "Skip the day when the move from the 09:30 open to entry is smaller than this many average ranges."},
}

PARAM_GRID_PRESETS = {
    "Short  (the catalogue cell)": {"entry_min": [900], "min_move": [0.0]},
    "Medium (entry x minimum move)": {"entry_min": [840, 855, 870, 885, 900, 915, 930], "min_move": [0.0, 0.2, 0.4, 0.6]},
}

PNL_UNITS = "points"

_OPEN_MIN = 570      # 09:30 ET
_CLOSE_MIN = 960     # 16:00 ET
_ADR_LEN = 20


def _bar_minutes(idx):
    if len(idx) < 2:
        return 5
    d = np.diff(idx.asi8[: min(len(idx), 2000)]) // 60_000_000_000
    d = d[(d > 0) & (d < 120)]
    return int(np.median(d)) if len(d) else 5


def run_backtest(opens, highs, lows, closes, volumes=None, day_id=None, index=None,
                 entry_min: int = 900, min_move: float = 0.0,
                 return_trades: bool = False, _stop_event=None, _pause_event=None, **_ignore):
    n = len(closes)
    if n < 500 or index is None or len(index) != n:
        return None
    o = np.asarray(opens, float); h = np.asarray(highs, float)
    l = np.asarray(lows, float); c = np.asarray(closes, float)
    idx = pd.DatetimeIndex(index)
    if idx.tz is not None:
        idx = idx.tz_convert("US/Eastern").tz_localize(None)
    step = _bar_minutes(idx)
    date = (idx.year * 10000 + idx.month * 100 + idx.day).to_numpy()
    minute = (idx.hour * 60 + idx.minute).to_numpy()
    cut = np.flatnonzero(np.diff(date) != 0) + 1
    starts = np.concatenate([[0], cut]); ends = np.concatenate([cut, [n]])
    full_bars = (_CLOSE_MIN - _OPEN_MIN) // step
    last_min = _CLOSE_MIN - step
    hist = []
    trades = []
    for a, b in zip(starts, ends):
        if _stop_event is not None and _stop_event.is_set():
            return None
        m = minute[a:b]
        rth = np.flatnonzero((m >= _OPEN_MIN) & (m < _CLOSE_MIN)) + a
        if len(rth) == 0:
            continue
        mr = minute[rth]
        full = mr[0] == _OPEN_MIN and mr[-1] == last_min
        adr = float(np.mean(hist[-_ADR_LEN:])) if len(hist) >= _ADR_LEN else None
        if full and adr is not None and adr > 0:
            e = rth[mr == int(entry_min)]
            if len(e):
                eb = int(e[0]); xb = int(rth[-1])
                ep = float(o[eb]); mv = ep - float(o[rth[0]])
                side = 1 if mv > 0 else (-1 if mv < 0 else 0)
                if side and abs(mv) >= float(min_move) * adr and xb > eb:
                    xp = float(c[xb])
                    trades.append((eb, xb, float(side * (xp - ep)), side, ep, xp))
        if full and len(rth) >= full_bars - 2:
            hist.append(float(h[rth].max() - l[rth].min()))
    return _score(trades, return_trades)


def _score(trades, return_trades):
    if not trades:
        return None
    p = np.array([t[2] for t in trades], float)
    w = p[p > 0]; ls = p[p < 0]
    gw = float(w.sum()); gl = float(-ls.sum())
    cum = np.cumsum(p); peak = np.maximum.accumulate(np.maximum(cum, 0.0))
    out = {"total_pnl": float(p.sum()), "num_trades": int(len(p)),
           "win_rate": float(100.0 * len(w) / len(p)),
           "profit_factor": (gw / gl) if gl > 1e-9 else (float("inf") if gw > 0 else 0.0),
           "max_drawdown": float(min(0.0, (cum - peak).min())),
           "avg_pnl": float(p.mean()), "wins": int(len(w)), "losses": int(len(ls))}
    if return_trades:
        out["trades"] = trades
    return out


def mark_open_trades(trades, opens, highs, lows, closes, volumes=None, day_id=None, index=None,
                     **params):
    """Every trade enters late in the session and leaves at its close: none is held overnight."""
    return [[] for _ in (trades or [])]
