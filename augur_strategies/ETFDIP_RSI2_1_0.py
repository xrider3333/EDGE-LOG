"""ETFDIP RSI2 1.0 — the ROUND-25 weak-edge book's short-RSI leg, as one plugin file.

Provenance: tools/r25_weak_edge_book.py, cells "RSI2L" (long only) and "RSI2B" (both
sides). Both r25 cells are in this one file behind `allow_shorts`, because they are the
same mechanism with the mirror trade switched on. Verified trade-for-trade against the
r25 harness by tools/etf_book_parity.py.

── The rule ──────────────────────────────────────────────────────────────────────────
Daily bars (aggregated from `day_id`). One position at a time.
  LONG   : Wilder RSI(`rsi_len`) of daily closes < `rsi_thr` while the close is ABOVE
           SMA(`trend_len`).   Exit when the close is back above SMA(`rsi_exit`).
  SHORT  : only when `allow_shorts` — RSI > `rsi_thr_short` while the close is BELOW
           SMA(`trend_len`).   Exit when the close is back below SMA(`rsi_exit`).
  FILL   : signals read on a CLOSE, filled at the NEXT day's OPEN. No stop (r17/r18b).
  WARM-UP: scan starts at day `trend_len + 10` (r25's fixed 210 behind a 200-day SMA).

── Sizing and costs (INSIDE the plugin — job cost_pts 0, mult 1) ──────────────────────
shares = notional / entry open; round trip costs `cost_bps` of notional (2 bps of $100k =
r25's $20 flat). PnL is DOLLARS in the trade tuple's field 2 (the SHARES*(EXIT-ENTRY)+FEE
form, same as NQDIP_1_0.py).

INSTRUMENT COMES FROM THE JOB — GLD / TLT / IWM / QQQ / SPY 1d masters, source
`yahoo_adj`, built by tools/build_etf_masters.py.

── Auto-Validate ranges ──────────────────────────────────────────────────────────────
rsi_len / rsi_thr / rsi_thr_short / rsi_exit / trend_len are OPEN; sizing is pinned.
`allow_shorts` is the one structural switch (r25 kept IWM and QQQ on "both", the rest
long-only), so it is a bool, not a swept number.
"""
import numpy as np

STRATEGY_NAME = 'ETFDIP RSI2 1.0 · short-RSI mean reversion (r25 weak-edge book leg)'
DESCRIPTION = ("Connors-style 2-day RSI: buy oversold above a long SMA (optionally short "
               "overbought below it), exit on a close back through a short SMA. Daily "
               "bars, next-open fills, no stop. Constant-notional share sizing with costs "
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
    "rsi_len": {"default": 2, "min": 2, "max": 5, "step": 1, "type": "int",
                "label": "RSI length (days)", "tooltip": "Connors-style short RSI. r25 used 2."},
    "rsi_thr": {"default": 10, "min": 5, "max": 30, "step": 5, "type": "int",
                "label": "Long below RSI", "tooltip": "Oversold trigger for the long side. r25 used 10."},
    "rsi_thr_short": {"default": 90, "min": 70, "max": 95, "step": 5, "type": "int",
                      "label": "Short above RSI",
                      "tooltip": "Overbought trigger for the mirror short. Ignored unless shorts are on. r25 used 90."},
    "rsi_exit": {"default": 5, "min": 3, "max": 10, "step": 1, "type": "int",
                 "label": "Exit SMA (days)",
                 "tooltip": "Exit when the close crosses back through this short SMA. r25 used 5."},
    "trend_len": {"default": 200, "min": 100, "max": 300, "step": 25, "type": "int",
                  "label": "Trend filter SMA (days)",
                  "tooltip": "Longs above it, shorts below it. r25 used 200."},
    "allow_shorts": {"default": False, "type": "bool", "label": "Trade the mirror short",
                     "tooltip": "OFF = r25's RSI2L cell (long only). ON = r25's RSI2B cell (both sides)."},
}

PARAM_GRID_PRESETS = {
    "Short  (r25 defaults)": {"rsi_len": [2], "rsi_thr": [10], "rsi_thr_short": [90],
                              "rsi_exit": [5], "trend_len": [200]},
    "Medium (the r17/r25 shapes)": {"rsi_len": [2, 3], "rsi_thr": [5, 10, 20],
                                    "rsi_thr_short": [80, 90], "rsi_exit": [3, 5, 8],
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


def _wilder_rsi(x, per):
    """Verbatim from r25_weak_edge_book.wilder_rsi (and r19b before it)."""
    d = np.diff(x, prepend=x[0]); up = np.where(d > 0, d, 0.0); dn = np.where(d < 0, -d, 0.0)
    au = np.zeros_like(x); ad = np.zeros_like(x)
    if len(x) <= per:
        return np.full_like(x, 50.0)
    au[per] = up[1:per + 1].mean(); ad[per] = dn[1:per + 1].mean()
    for i in range(per + 1, len(x)):
        au[i] = (au[i - 1] * (per - 1) + up[i]) / per
        ad[i] = (ad[i - 1] * (per - 1) + dn[i]) / per
    rs = np.divide(au, ad, out=np.full_like(x, np.inf), where=ad > 1e-12)
    return 100 - 100 / (1 + rs)


def run_backtest(opens, highs, lows, closes, volumes=None, day_id=None,
                 notional: int = 100000, cost_bps: float = 2.0,
                 rsi_len: int = 2, rsi_thr: int = 10, rsi_thr_short: int = 90,
                 rsi_exit: int = 5, trend_len: int = 200, allow_shorts: bool = False,
                 return_trades: bool = False, _stop_event=None, _pause_event=None, **_ignore):
    o = np.asarray(opens, float); c = np.asarray(closes, float)
    n = len(c)
    if n < 50:
        return None
    if day_id is None or len(day_id) != n:
        bounds = [(i, i + 1) for i in range(n)]
    else:
        bounds = _sessions(np.asarray(day_id), n)
    D = len(bounds)
    rsi_len, rsi_exit, trend_len = int(rsi_len), int(rsi_exit), int(trend_len)
    start = max(trend_len + 10, 30)
    if D < start + 20:
        return None

    do = np.array([o[a] for a, b in bounds])
    dc = np.array([c[b - 1] for a, b in bounds])
    open_bar = np.array([a for a, b in bounds])
    trend = _sma(dc, trend_len)
    exit_sma = _sma(dc, rsi_exit)
    rsi = _wilder_rsi(dc, rsi_len)

    trades = []
    pos = 0; de = 0; d = start
    while d < D - 1:
        if _stop_event is not None and _stop_event.is_set():
            return None
        if pos == 0:
            s = 0
            if dc[d] > trend[d] and rsi[d] < rsi_thr:
                s = 1
            elif allow_shorts and dc[d] < trend[d] and rsi[d] > rsi_thr_short:
                s = -1
            if s != 0:
                pos, de = s, d + 1
                d += 1
                continue
        else:
            ex = (dc[d] > exit_sma[d]) if pos > 0 else (dc[d] < exit_sma[d])
            if d >= de and ex:
                ep = float(do[de]); xp = float(do[d + 1])
                sh = float(notional) / ep
                pnl = pos * (xp - ep) * sh - float(notional) * float(cost_bps) / 10000.0
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
