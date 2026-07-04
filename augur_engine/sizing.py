"""Execution-layer position-sizing overlays for backtested trade lists (streamlit-free).

The backtest engines return per-trade PnL in POINTS at 1 contract. These helpers reweight
each trade's *size* by a sizing rule WITHOUT changing entries/exits — the "how many contracts
per signal" decision that lives at the execution layer. Schemes are compared **capital-matched**
(same total dollar-risk deployed), so a fair "where do you spend the risk budget?" test.

Rules (multiplicative, all optional) — each is an independent, validated ORB edge:
  • risk_parity  size ∝ 1/initial_risk (constant-$ risk per trade), capped at `rp_cap`× avg.   (ORB.md §4.7)
  • time_tilt    size ∝ tier by entry-hour — morning breakouts carry ~2× the profit factor.     (ORB.md §4.9-4.10)
  • side_tilt    size ∝ long_w / short_w — ORB shorts carry the edge; longs are ~deadweight.     (ORB.md §4.11)

On NQ 5m RTH these stack: baseline lockbox MAR 6.9 → time×rp 12.7 → +short-tilt 15.0.
MAR = net PnL ÷ |max drawdown| — the drawdown-adjusted return you actually size on.
"""
import numpy as np

# (upper_bar_exclusive, weight). 5m RTH: bar t ≈ 9:30 + 5·t min, so 12 ≈ first hour, 36 ≈ first 3h.
DEFAULT_TIME_TIERS = ((12, 2.0), (36, 1.0), (10**9, 0.5))


def mar(total_pnl, max_drawdown):
    """Drawdown-adjusted return. `max_drawdown` may be signed (neg) or magnitude."""
    dd = abs(float(max_drawdown or 0.0))
    return (float(total_pnl) / dd) if dd > 1e-9 else float("inf")


def time_weight(entry_bar, tiers=DEFAULT_TIME_TIERS):
    """Per-trade time-of-day weight from session-relative entry bar index (vectorized)."""
    b = np.asarray(entry_bar, float)
    w = np.full(b.shape, tiers[-1][1], float)
    lo = 0
    for upper, wt in tiers:                     # ascending tiers → assign each [lo, upper) band
        w = np.where((b >= lo) & (b < upper), wt, w)
        lo = upper
    return w


def trade_features(trades, arrays, stop_frac, or_bars):
    """Extract (pnl_pts, risk_pts, entry_bar, side) from engine trade tuples + master arrays.

    trades : list of (entry_gidx, exit_gidx, pnl_pts, side, entry_px) from run_backtest(..., return_trades=True).
    Recomputes each trade's INITIAL risk = stop_frac × opening-range width of the entry's session
    (same rule the strategy uses), and the session-relative entry bar (time-of-day)."""
    H = np.asarray(arrays["high"], float); L = np.asarray(arrays["low"], float)
    did = np.asarray(arrays["day_id"]); n = len(H)
    sess_or = np.zeros(n); sess_start = np.zeros(n, int)
    i = 0
    while i < n:
        j = i
        while j < n and did[j] == did[i]:
            j += 1
        sess_or[i:j] = H[i:i + or_bars].max() - L[i:i + or_bars].min()
        sess_start[i:j] = i
        i = j
    gi   = np.array([t[0] for t in trades])
    pnl  = np.array([t[2] for t in trades], float)
    side = np.array([t[3] for t in trades], float)
    risk = np.maximum(stop_frac * sess_or[gi], 1e-9)
    ebar = (gi - sess_start[gi]).astype(float)
    return pnl, risk, ebar, side


def sizing_weights(risk_pts, entry_bar=None, side=None, *, risk_parity=True, rp_cap=3.0,
                   time_tilt=False, tiers=DEFAULT_TIME_TIERS, long_w=1.0, short_w=1.0):
    """Per-trade size multipliers (pre capital-match). Compose any subset of the three rules."""
    risk_pts = np.asarray(risk_pts, float)
    w = np.ones_like(risk_pts)
    if side is not None:
        w = w * np.where(np.asarray(side) > 0, long_w, short_w)
    if time_tilt and entry_bar is not None:
        w = w * time_weight(entry_bar, tiers)
    if risk_parity:
        f = 1.0 / risk_pts
        f = f / f.mean()
        f = np.minimum(f, rp_cap)
        w = w * f
    return w


def sized_metrics(pnl_pts, risk_pts, weights, *, mult, fee_pts, cap_final=None):
    """Capital-match `weights` to the size-1 total-risk budget, then compute net metrics + equity.

    Returns dict: net, num_trades, win_rate, profit_factor, max_drawdown, mar, avg_size, max_size, equity_usd.
    `cap_final` (optional) hard-caps each final contract size for realism (raw risk-parity can spike).
    """
    pnl_pts = np.asarray(pnl_pts, float); risk_pts = np.asarray(risk_pts, float)
    w = np.asarray(weights, float).copy()
    denom = float((w * risk_pts).sum())
    if denom <= 1e-12:
        return None
    k = float(risk_pts.sum()) / denom          # capital-match: same total $risk as size-1 baseline
    size = w * k
    if cap_final:
        size = np.minimum(size, float(cap_final))
    net = size * (pnl_pts - fee_pts) * mult
    cum = np.cumsum(net); dd = float((cum - np.maximum.accumulate(cum)).min()) if len(cum) else 0.0
    gw = float(net[net > 0].sum()); gl = float(-net[net < 0].sum())
    return {
        "net": float(net.sum()), "num_trades": int(len(net)),
        "win_rate": float(100.0 * (net > 0).mean()) if len(net) else 0.0,
        "profit_factor": (gw / gl) if gl > 1e-9 else (float("inf") if gw > 0 else 0.0),
        "max_drawdown": dd, "mar": mar(net.sum(), dd),
        "avg_size": float(size.mean()), "max_size": float(size.max()),
        "equity_usd": cum,
    }
