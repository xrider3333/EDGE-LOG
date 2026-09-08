"""ETFDIP PB20 1.0 — the ROUND-25 weak-edge book's pullback leg, as one plugin file.

Provenance: tools/r25_weak_edge_book.py, cell "PB20L". Verified trade-for-trade against
the r25 harness by tools/etf_book_parity.py.

── The rule ──────────────────────────────────────────────────────────────────────────
Daily bars (aggregated from `day_id`). LONG ONLY, one position at a time.
  ENTRY  : the day's LOW touches EMA(`pb_ema`) of daily closes while YESTERDAY closed
           above that EMA (the first touch of a rising average), AND the close is above
           SMA(`trend_len`).
  EXIT   : a close above the ENTRY DAY's prior high (dh[de-1] — the high of the bar that
           produced the signal), or after `pb_hold` days, whichever comes first.
  FILL   : signals read on a CLOSE, filled at the NEXT day's OPEN. No stop (r17/r18b).
  WARM-UP: scan starts at day `trend_len + 10` (r25's fixed 210 behind a 200-day SMA).

  The EMA is seeded exactly the way r25 seeds it: ema[L-1] = mean(close[:L]), then the
  standard 2/(L+1) recursion. A different seed shifts the whole series and moves trades,
  so it is not a detail.

── Sizing and costs (INSIDE the plugin — job cost_pts 0, mult 1) ──────────────────────
shares = notional / entry open; round trip costs `cost_bps` of notional (2 bps of $100k =
r25's $20 flat). PnL is DOLLARS in the trade tuple's field 2 (SHARES*(EXIT-ENTRY)+FEE,
same as NQDIP_1_0.py).

INSTRUMENT COMES FROM THE JOB — GLD / TLT / IWM / QQQ / SPY 1d masters, source
`yahoo_adj`, built by tools/build_etf_masters.py.

── Auto-Validate ranges ──────────────────────────────────────────────────────────────
pb_ema / pb_hold / trend_len are OPEN; sizing knobs are pinned min=max.
"""
import numpy as np

STRATEGY_NAME = 'ETFDIP PB20 1.0 · pullback-to-EMA buy (r25 weak-edge book leg)'
DESCRIPTION = ("Buy the first touch of a short EMA in an uptrend, exit on a close above "
               "the signal day's prior high or after N days. Daily bars, long only, "
               "next-open fills, no stop. Constant-notional share sizing with costs "
               "inside the plugin -> job cost_pts 0, mult 1. Instrument from the job.")

_AUGUR_MARKET = {"instrument": "QQQ", "timeframe": "1d", "session": "rth",
                 "source": "yahoo_adj"}

DEFAULT_PARAMS = {
    "notional": {"default": 100000, "min": 100000, "max": 100000, "step": 1, "type": "int",
                 "label": "Notional per trade ($)",
                 "tooltip": "Fixed. shares = notional / entry open (r25 equal-notional convention)."},
    "cost_bps": {"default": 2.0, "min": 2.0, "max": 2.0, "step": 0.5, "type": "float",
                 "label": "Round-trip cost (bps)",
                 "tooltip": "Fixed: 2 bps of notional = the $20 flat round trip r25 charged."},
    "pb_ema": {"default": 20, "min": 5, "max": 50, "step": 5, "type": "int",
               "label": "Pullback EMA (days)",
               "tooltip": "Buy the first touch of this EMA while yesterday closed above it. r25 used 20."},
    "pb_hold": {"default": 10, "min": 3, "max": 20, "step": 1, "type": "int",
                "label": "Max hold (days)",
                "tooltip": "Time stop if the prior high is never taken out. r25 used 10."},
    "trend_len": {"default": 200, "min": 100, "max": 300, "step": 25, "type": "int",
                  "label": "Trend filter SMA (days)",
                  "tooltip": "Longs only while the close is above this SMA of daily closes. r25 used 200."},
}

PARAM_GRID_PRESETS = {
    "Short  (r25 defaults)": {"pb_ema": [20], "pb_hold": [10], "trend_len": [200]},
    "Medium (the r17/r25 shapes)": {"pb_ema": [10, 20, 30], "pb_hold": [5, 10, 15],
                                    "trend_len": [150, 200, 250]},
}


def _sessions(day_id, n):
    b = []; a = 0
    while a < n:
        j = a
        while j < n and day_id[j] == day_id[a]:
            j += 1
        b.append((a, j)); a = j
    return b


def _sma(x, L):
    k = np.concatenate([[0.0], np.cumsum(x)]); s = np.full(len(x), np.nan)
    for d in range(L - 1, len(x)):
        s[d] = (k[d + 1] - k[d + 1 - L]) / L
    return s


def _ema(x, L):
    """r25's seeding: ema[L-1] = mean(x[:L]), then the 2/(L+1) recursion."""
    e = np.full(len(x), np.nan)
    if len(x) < L:
        return e
    e[L - 1] = x[:L].mean(); k = 2.0 / (L + 1)
    for d in range(L, len(x)):
        e[d] = e[d - 1] + k * (x[d] - e[d - 1])
    return e


def run_backtest(opens, highs, lows, closes, volumes=None, day_id=None,
                 notional: int = 100000, cost_bps: float = 2.0,
                 pb_ema: int = 20, pb_hold: int = 10, trend_len: int = 200,
                 return_trades: bool = False, _stop_event=None, _pause_event=None, **_ignore):
    o = np.asarray(opens, float); h = np.asarray(highs, float)
    lw = np.asarray(lows, float); c = np.asarray(closes, float)
    n = len(c)
    if n < 50:
        return None
    if day_id is None or len(day_id) != n:
        bounds = [(i, i + 1) for i in range(n)]
    else:
        bounds = _sessions(np.asarray(day_id), n)
    D = len(bounds)
    pb_ema, pb_hold, trend_len = int(pb_ema), int(pb_hold), int(trend_len)
    start = max(trend_len + 10, 30)
    if D < start + 20:
        return None

    do = np.array([o[a] for a, b in bounds])
    dh = np.array([h[a:b].max() for a, b in bounds])
    dl = np.array([lw[a:b].min() for a, b in bounds])
    dc = np.array([c[b - 1] for a, b in bounds])
    open_bar = np.array([a for a, b in bounds])
    trend = _sma(dc, trend_len)
    ema = _ema(dc, pb_ema)

    trades = []
    pos = 0; de = 0; d = start
    while d < D - 1:
        if _stop_event is not None and _stop_event.is_set():
            return None
        if pos == 0:
            if dc[d] > trend[d] and dl[d] <= ema[d] and dc[d - 1] > ema[d - 1]:
                pos, de = 1, d + 1
                d += 1
                continue
        else:
            if d >= de and ((dc[d] > dh[de - 1]) or (d - de >= pb_hold)):
                ep = float(do[de]); xp = float(do[d + 1])
                sh = float(notional) / ep
                pnl = (xp - ep) * sh - float(notional) * float(cost_bps) / 10000.0
                trades.append((int(open_bar[de]), int(open_bar[d + 1]), float(pnl), 1, ep, xp))
                pos = 0
        d += 1
    return _score(trades, return_trades)


def _score(trades, return_trades):
    if not trades:
        return None
    trades.sort(key=lambda t: (t[1], t[0]))
    p = np.array([t[2] for t in trades], float)
    w = p[p > 0]; l = p[p < 0]
    gw = float(w.sum()); gl = float(-l.sum())
    cum = np.cumsum(p)
    out = {"total_pnl": float(p.sum()), "num_trades": int(len(p)),
           "win_rate": float(100.0 * len(w) / len(p)),
           "profit_factor": (gw / gl) if gl > 1e-9 else (float("inf") if gw > 0 else 0.0),
           "max_drawdown": float((cum - np.maximum.accumulate(cum)).min()),
           "avg_pnl": float(p.mean()), "wins": int(len(w)), "losses": int(len(l))}
    if return_trades:
        out["trades"] = trades
    return out
