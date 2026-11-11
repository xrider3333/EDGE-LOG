"""MISC LATE30 1.0 - wide-day late continuation on NQ: 15:00 -> 15:30 ET.

# AUGUR-SOURCE: claude

Provenance: OPUS-HUNT futures round 2, strategy 36 cell 36d
(C:/EdgeLog/_anatomy_cache/opus_hunt1109/futures/S36: PREREG.md, RESULTS.md, three verifier
folders). It is the closed LEG_SCAN M4a zone (ledger 2.5) with the exit moved from 15:55 to
15:30. NOT A BLIND READ: the family's 2016-25 behaviour was partly known to the house, the cell
was report-only in its own prereg, and the robustness verifier found the result depends on the
15:00 -> 15:30 window. This file exists so the engine's Auto-Validate can judge it.

-- The rule -----------------------------------------------------------------------------
On a regular full session, at 15:00:00 ET:
  * R  = today's high minus low over the bars 09:30 .. 14:59;
  * ADR = mean full-session (09:30-16:00) high-low range of the previous `adr_len` FULL
    sessions (strictly earlier days);
  * if R >= `range_mult` x ADR and the last price (close of the bar ending 15:00) sits in the
    top `zone_pct` percent of R -> BUY; in the bottom `zone_pct` percent -> SELL.
Entry = open of the 15:00 bar. Exit = open of the bar `exit_min` minutes later (default 15:30).
No stop, no target. One trade a day at most, never overnight.

INFORMATION TIMES: every input is a completed bar before 15:00. The session-complete test for
TODAY reads only bars before 15:00 (the 09:30 bar exists and at most two 5-minute bars are
missing); a day without the exit bar gives no trade. Range and zone are differences inside one
session, so the back-adjusted master gives the same signal as real prices.

-- Costs ----------------------------------------------------------------------------------
PnL is NQ points in the trade tuple; the job charges the house round trip (cost_pts 0.533,
mult 20).
"""
import numpy as np
import pandas as pd

STRATEGY_NAME = 'MISC LATE30 1.0 · wide-day late continuation (NQ 15:00 -> 15:30)'
DESCRIPTION = ("At 15:00 ET, if the day's range is at least range_mult x its 20-session average and "
               "price sits in the top / bottom zone of that range, buy the high / sell the low and "
               "exit at 15:30. One trade a day, flat before the closing window.")

_AUGUR_MARKET = {"instrument": "NQ", "timeframe": "5m", "session": "rth", "source": "db_adj_rth"}

DEFAULT_PARAMS = {
    "range_mult": {"default": 1.0, "min": 0.75, "max": 1.5, "step": 0.25, "type": "float",
                   "label": "Range so far vs average (x)",
                   "tooltip": "Trade only if the 09:30-15:00 range is at least this many times the average full-day range."},
    "zone_pct": {"hard_min": 5, "default": 20, "min": 10, "max": 30, "step": 5, "type": "int",
                 "label": "Zone (percent of the range)",
                 "tooltip": "Price must sit in the top (buy) or bottom (sell) this-many percent of the day's range."},
    "adr_len": {"hard_min": 5, "default": 20, "min": 10, "max": 40, "step": 10, "type": "int",
                "label": "Average-range window (sessions)",
                "tooltip": "Full sessions in the average daily range, ending the session before."},
    "exit_min": {"hard_min": 5, "default": 30, "min": 15, "max": 55, "step": 5, "type": "int",
                 "label": "Hold (minutes after 15:00)",
                 "tooltip": "Exit at the open of the bar this many minutes after 15:00 ET."},
}

PARAM_GRID_PRESETS = {
    "Short  (the hunt cell 36d)": {"range_mult": [1.0], "zone_pct": [20], "adr_len": [20], "exit_min": [30]},
    "Medium (neighbours)": {"range_mult": [0.75, 1.0, 1.25, 1.5], "zone_pct": [10, 15, 20, 25, 30],
                            "adr_len": [10, 20, 40], "exit_min": [15, 20, 25, 30, 35, 45, 55]},
}

PNL_UNITS = "points"

_OPEN_MIN = 570      # 09:30 ET
_SIG_MIN = 900       # 15:00 ET
_CLOSE_MIN = 960     # 16:00 ET


def _bar_minutes(idx):
    if len(idx) < 2:
        return 5
    d = np.diff(idx.asi8[: min(len(idx), 2000)]) // 60_000_000_000
    d = d[(d > 0) & (d < 120)]
    return int(np.median(d)) if len(d) else 5


def run_backtest(opens, highs, lows, closes, volumes=None, day_id=None, index=None,
                 range_mult: float = 1.0, zone_pct: int = 20, adr_len: int = 20, exit_min: int = 30,
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
    full_bars = (_CLOSE_MIN - _OPEN_MIN) // step             # 78 on 5m
    pre_bars = (_SIG_MIN - _OPEN_MIN) // step                # 66 on 5m
    exit_at = _SIG_MIN + int(exit_min)
    zone = float(zone_pct) / 100.0
    hist = []                                                # full-session ranges of earlier days
    trades = []
    for a, b in zip(starts, ends):
        if _stop_event is not None and _stop_event.is_set():
            return None
        m = minute[a:b]
        rth = np.flatnonzero((m >= _OPEN_MIN) & (m < _CLOSE_MIN)) + a
        if len(rth) == 0:
            continue
        mr = minute[rth]
        pre = rth[mr < _SIG_MIN]
        adr = float(np.mean(hist[-int(adr_len):])) if len(hist) >= int(adr_len) else None
        # ---- today's trade: only bars before 15:00 decide it
        if (adr is not None and adr > 0 and len(pre) >= pre_bars - 2 and mr[0] == _OPEN_MIN):
            e = rth[mr == _SIG_MIN]; x = rth[mr == exit_at]
            if len(e) and len(x):
                hi = float(h[pre].max()); lo = float(l[pre].min()); rng = hi - lo
                last = float(c[pre[-1]])
                if rng > 0 and rng >= float(range_mult) * adr:
                    pos = (last - lo) / rng
                    side = 1 if pos >= 1.0 - zone else (-1 if pos <= zone else 0)
                    if side:
                        eb = int(e[0]); xb = int(x[0])
                        ep = float(o[eb]); xp = float(o[xb])
                        trades.append((eb, xb, float(side * (xp - ep)), side, ep, xp))
        # ---- after the session: add it to the average-range history if it was a full one
        if mr[0] == _OPEN_MIN and mr[-1] == _CLOSE_MIN - step and len(rth) >= full_bars - 2:
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
    """Every trade enters at 15:00 and leaves the same session: no trade is held through a close."""
    return [[] for _ in (trades or [])]
