"""ETFDIP DBL7 1.0 — the ROUND-25 weak-edge book's N-day-low leg, as one plugin file.

Provenance: tools/r25_weak_edge_book.py, cell "DBL7L". That harness is a standalone
script; this file is the same rule where the app can see it, so Auto-Validate (WF folds,
sealed lockbox, PBO/DSR, surfaces) and a BOOK job can judge it like every other strategy.
The r25 harness's `run_cell` is the reference — the logic below is a transcription of it,
verified trade-for-trade by tools/etf_book_parity.py.

── The rule ──────────────────────────────────────────────────────────────────────────
Daily bars (aggregated from `day_id`, so a 1d master is already one bar per day and an
intraday RTH master collapses to its sessions). LONG ONLY, one position at a time.
  ENTRY  : the day's close is the LOWEST close of the last `dbl_n` days, AND the close is
           above SMA(`trend_len`) of daily closes.
  EXIT   : the day's close is the HIGHEST close of the last `dbl_n` days.
  FILL   : every signal is read on a CLOSE and filled at the NEXT day's OPEN. No stop —
           the round-18b study measured stops as strictly harmful to this hold-for-days
           edge; the gap risk is real and is in the numbers.
  WARM-UP: the scan starts at day `trend_len + 10` (r25 used a fixed 210 with a 200-day
           trend filter; the +10 is that same cushion, scaled with the knob).

── Sizing and costs (INSIDE the plugin — set the job's cost_pts to 0 and mult to 1) ───
Equities, so `shares = notional / entry open` (constant notional, the r25 EQN convention)
and the round trip costs `cost_bps` of notional (2 bps of $100k = the $20 flat r25 used).
PnL is returned in DOLLARS in the trade tuple's field 2 — the plugin contract's
SHARES*(EXIT-ENTRY)+FEE form, same as NQDIP_1_0.py — so a job must pass cost_pts 0 and
mult 1 or the numbers get multiplied twice.

INSTRUMENT COMES FROM THE JOB. This file has no ticker in it; point it at the GLD / TLT /
IWM / QQQ / SPY 1d masters (source `yahoo_adj`) built by tools/build_etf_masters.py.

── Auto-Validate ranges ──────────────────────────────────────────────────────────────
`dbl_n` and `trend_len` are OPEN (a pinned file gives n_evaluated=1 and kills PDP /
parallel coords / surfaces / PBO). Sizing knobs are pinned min=max on purpose: the search
space is about the edge, not the leverage.
"""
import numpy as np

STRATEGY_NAME = 'ETFDIP DBL7 1.0 · N-day-low dip buy (r25 weak-edge book leg)'
DESCRIPTION = ("Buy the lowest close of the last N days while above a long SMA, sell the "
               "N-day closing high. Daily bars, long only, next-open fills, no stop. "
               "Constant-notional share sizing with costs inside the plugin -> job "
               "cost_pts 0, mult 1. Instrument comes from the job (ETF 1d masters).")

_AUGUR_MARKET = {"instrument": "QQQ", "timeframe": "1d", "session": "rth",
                 "source": "yahoo_adj"}

DEFAULT_PARAMS = {
    "notional": {"default": 100000, "min": 100000, "max": 100000, "step": 1, "type": "int",
                 "label": "Notional per trade ($)",
                 "tooltip": "Fixed. shares = notional / entry open (r25 equal-notional convention)."},
    "cost_bps": {"default": 2.0, "min": 2.0, "max": 2.0, "step": 0.5, "type": "float",
                 "label": "Round-trip cost (bps)",
                 "tooltip": "Fixed: 2 bps of notional = the $20 flat round trip r25 charged."},
    "dbl_n": {"default": 7, "min": 3, "max": 15, "step": 1, "type": "int",
              "label": "N-day low / high",
              "tooltip": "Buy the lowest close of N days, sell the highest close of N days. r25 used 7."},
    "trend_len": {"default": 200, "min": 100, "max": 300, "step": 25, "type": "int",
                  "label": "Trend filter SMA (days)",
                  "tooltip": "Longs only while the close is above this SMA of daily closes. r25 used 200."},
}

PARAM_GRID_PRESETS = {
    "Short  (r25 defaults)": {"dbl_n": [7], "trend_len": [200]},
    "Medium (the r17/r25 shapes)": {"dbl_n": [5, 7, 10, 15], "trend_len": [150, 200, 250]},
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


def run_backtest(opens, highs, lows, closes, volumes=None, day_id=None,
                 notional: int = 100000, cost_bps: float = 2.0,
                 dbl_n: int = 7, trend_len: int = 200,
                 return_trades: bool = False, _stop_event=None, _pause_event=None, **_ignore):
    o = np.asarray(opens, float); h = np.asarray(highs, float)
    lo = np.asarray(lows, float); c = np.asarray(closes, float)
    n = len(c)
    if n < 50:
        return None
    if day_id is None or len(day_id) != n:
        bounds = [(i, i + 1) for i in range(n)]
    else:
        bounds = _sessions(np.asarray(day_id), n)
    D = len(bounds)
    dbl_n, trend_len = int(dbl_n), int(trend_len)
    start = max(trend_len + 10, 30)
    if D < start + 20:
        return None

    do = np.array([o[a] for a, b in bounds])
    dc = np.array([c[b - 1] for a, b in bounds])
    open_bar = np.array([a for a, b in bounds])
    trend = _sma(dc, trend_len)

    trades = []
    pos = 0; de = 0; d = start
    while d < D - 1:
        if _stop_event is not None and _stop_event.is_set():
            return None
        if pos == 0:
            if d >= dbl_n and dc[d] > trend[d] and dc[d] == dc[d - dbl_n + 1:d + 1].min():
                pos, de = 1, d + 1
                d += 1
                continue
        else:
            if d >= de and dc[d] == dc[d - dbl_n + 1:d + 1].max():
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
