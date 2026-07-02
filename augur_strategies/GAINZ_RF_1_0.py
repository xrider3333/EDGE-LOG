"""
RF MACHINE LEARNING — Random-Forest direction classifier (port of the GainzAlgo
"Machine Learning Random Forest Strategy" Pine *indicator* into a backtestable Augur
plugin).

The original was a TradingView *indicator* (drew labels + a stats table) and so could
never be optimized here. This is a faithful, look-ahead-safe Python port of its actual
logic:

  • 3 engineered features, each scaled ~0-100:
      - anchor   = an oscillator (RSI default; MFI / Stochastic / Z-Score optional)
      - trend    = 50 + corr(close, bar_index, trendLen)*50   (rolling trend strength)
      - momentum = clamp(50 + (mom/ATR)*16.67, 0, 100)
  • a from-scratch Random-Forest CLASSIFIER (ensemble of Gini decision stumps with a
    real information-gain threshold search — exactly what the Pine `trainClassifier`
    did) is RE-TRAINED on a rolling `lookback`-bar window and predicts P(next bar up).
  • a fresh BULL signal fires when P(up) ≥ probThreshold; a fresh BEAR signal when
    P(down) ≥ probThreshold, gated by a cooldown so it can't machine-gun.
  • each signal opens ONE position with ATR-based exits:
      TP = entry ± atrMultTP·ATR,  SL = entry ∓ atrMultSL·ATR,
      and a time-stop after `maxHold` bars (the Pine `lineLookback`).
    Both-touched-same-bar resolves as a LOSS (pessimistic fill).

Deviations from the indicator, on purpose, to make it a realistic 1-contract backtest:
  • SINGLE position (the indicator tracked many overlapping paper trades at once).
  • the regression "expected return" forest was display-only in the Pine and is dropped.
  • RF training is stochastic; we seed it (`seed`) so grid/auto runs are reproducible,
    and expose `retrain_every` (retrain the forest every N bars, predict every bar) so
    the per-bar retrain cost is tractable on long intraday series.

PNL convention: SHARES*(EXIT-ENTRY) in points; the engine applies multiplier + costs.
No look-ahead: at bar i we train only on pairs whose outcome is already known
(features[t] → close[t+1]>close[t], for t ≤ i-1) and predict with features[i], entering
at close[i]; exits are evaluated from bar i+1 on.
"""
import numpy as np
import pandas as pd

STRATEGY_NAME = 'GainzAlgo RF 1.0 · RSI/trend/momentum direction (random-forest)'
DESCRIPTION   = ("Rolling-window random-forest (Gini decision-stump ensemble) classifies "
                 "next-bar direction from RSI/trend/momentum features; trades fresh "
                 "high-conviction signals with ATR TP/SL + time-stop. Port of the "
                 "GainzAlgo RF indicator.")

# Most RF strategies in this family were built/validated on ES intraday.
_AUGUR_MARKET = {"instrument": "ES", "timeframe": "5m"}

DEFAULT_PARAMS = {
    "probThreshold": {
        "default": 0.60, "min": 0.52, "max": 0.80, "step": 0.01, "type": "float",
        "label": "Signal probability threshold",
        "tooltip": "Only act when the forest's P(up) (or P(down)) is at least this. "
                   "Higher = rarer, higher-conviction signals.",
    },
    "atrMultTP": {
        "default": 2.0, "min": 0.5, "max": 6.0, "step": 0.25, "type": "float",
        "label": "Take-profit (x ATR)",
        "tooltip": "Target distance from entry, in ATRs.",
    },
    "atrMultSL": {
        "default": 2.0, "min": 0.5, "max": 6.0, "step": 0.25, "type": "float",
        "label": "Stop-loss (x ATR)",
        "tooltip": "Stop distance from entry, in ATRs.",
    },
    "maxHold": {
        "default": 20, "min": 4, "max": 80, "step": 2, "type": "int",
        "label": "Max hold / expiry (bars)",
        "tooltip": "Time-stop: if neither TP nor SL is hit within N bars, exit at market "
                   "(the Pine 'lineLookback').",
    },
    "lookback": {
        "default": 60, "min": 30, "max": 200, "step": 10, "type": "int",
        "label": "Training window (bars)",
        "tooltip": "How many recent bars the forest is re-fit on each time. Rolling, so "
                   "it tracks the current regime instead of memorising history.",
    },
    "numTrees": {
        "default": 30, "min": 10, "max": 80, "step": 5, "type": "int",
        "label": "Number of trees (stumps)",
        "tooltip": "Ensemble size. More trees = smoother probability, slower.",
    },
    "signalCooldown": {
        "default": 10, "min": 1, "max": 40, "step": 1, "type": "int",
        "label": "Cooldown between signals (bars)",
        "tooltip": "Minimum bars between two like-direction signals.",
    },
    "anchorType": {
        "default": "RSI", "type": "str",
        "options": ["RSI", "MFI", "Stochastic", "ZScore"],
        "label": "Anchor oscillator",
        "tooltip": "The first feature. MFI needs volume (falls back to RSI without it).",
    },
    "anchorLen": {
        "default": 14, "min": 2, "max": 50, "step": 1, "type": "int",
        "label": "Anchor length",
    },
    "trendLen": {
        "default": 20, "min": 5, "max": 60, "step": 1, "type": "int",
        "label": "Trend-correlation length",
    },
    "momLen": {
        "default": 10, "min": 2, "max": 40, "step": 1, "type": "int",
        "label": "Momentum / ATR length",
    },
    "tpSlLen": {
        "default": 14, "min": 2, "max": 50, "step": 1, "type": "int",
        "label": "ATR length for TP/SL",
    },
    "trade_mode": {
        "default": "Both", "type": "str",
        "options": ["Long Only", "Short Only", "Both"],
        "label": "Direction",
    },
    "retrain_every": {
        "default": 3, "min": 1, "max": 20, "step": 1, "type": "int",
        "label": "Retrain cadence (bars)",
        "tooltip": "Re-fit the forest every N bars (predict every bar). 1 = retrain every "
                   "bar (faithful, slowest). 3-5 is a good speed/fidelity trade.",
    },
    "seed": {
        "default": 42, "min": 0, "max": 9999, "step": 1, "type": "int",
        "label": "RNG seed",
        "tooltip": "Seeds the forest's randomness so results are reproducible. Vary it to "
                   "sanity-check that any edge isn't a single lucky seed.",
    },
}

PARAM_GRID_PRESETS = {
    "Short  (fast scan)": {
        "probThreshold": [0.58, 0.62, 0.66],
        "atrMultTP": [1.5, 2.5], "atrMultSL": [1.5, 2.5],
        "maxHold": [20], "lookback": [60], "numTrees": [30],
        "signalCooldown": [10], "trade_mode": ["Both"], "retrain_every": [3],
    },
    "Medium (balanced)": {
        "probThreshold": [0.56, 0.60, 0.64, 0.68],
        "atrMultTP": [1.5, 2.0, 3.0], "atrMultSL": [1.5, 2.0, 3.0],
        "maxHold": [12, 20, 32], "lookback": [40, 60, 100],
        "numTrees": [30], "signalCooldown": [8, 16],
        "trade_mode": ["Both"], "retrain_every": [3],
    },
    "Long   (deep sweep)": {
        "probThreshold": [0.55, 0.58, 0.62, 0.66, 0.70],
        "atrMultTP": [1.0, 1.5, 2.0, 3.0, 4.0], "atrMultSL": [1.0, 1.5, 2.0, 3.0],
        "maxHold": [8, 16, 24, 40], "lookback": [40, 60, 100, 150],
        "numTrees": [20, 40], "signalCooldown": [6, 12, 20],
        "trade_mode": ["Long Only", "Short Only", "Both"], "retrain_every": [3],
    },
}


# ── helpers ──────────────────────────────────────────────────────────────────
def _rma(x: pd.Series, n: int) -> pd.Series:
    """Wilder's RMA (what Pine ta.rsi / ta.atr use)."""
    return x.ewm(alpha=1.0 / max(1, n), adjust=False).mean()


def _rsi(close: pd.Series, n: int) -> pd.Series:
    d = close.diff()
    up = _rma(d.clip(lower=0.0), n)
    dn = _rma((-d).clip(lower=0.0), n)
    rs = up / dn.replace(0.0, np.nan)
    return (100.0 - 100.0 / (1.0 + rs)).fillna(50.0)


def _stoch(close, high, low, n):
    ll = low.rolling(n, min_periods=1).min()
    hh = high.rolling(n, min_periods=1).max()
    rng = (hh - ll).replace(0.0, np.nan)
    return (100.0 * (close - ll) / rng).fillna(50.0)


def _mfi(high, low, close, vol, n):
    tp = (high + low + close) / 3.0
    rmf = tp * vol
    pos = rmf.where(tp > tp.shift(1), 0.0)
    neg = rmf.where(tp < tp.shift(1), 0.0)
    pr = pos.rolling(n, min_periods=1).sum()
    nr = neg.rolling(n, min_periods=1).sum().replace(0.0, np.nan)
    return (100.0 - 100.0 / (1.0 + pr / nr)).fillna(50.0)


def _atr(high, low, close, n):
    tr = pd.concat([high - low,
                    (high - close.shift(1)).abs(),
                    (low - close.shift(1)).abs()], axis=1).max(axis=1)
    return _rma(tr, n)


def _train_stumps(X, y, n_trees, n_thresh, rng):
    """Gini information-gain decision-stump forest (vectorised over candidate
    thresholds). Returns (feat_idx, thresh, leftProb, rightProb) arrays."""
    L, F = X.shape
    yb = y.astype(np.float64)
    sBull = yb.sum()
    base_p = sBull / L if L else 0.0
    gini_base = 1.0 - base_p * base_p - (1.0 - base_p) ** 2
    fi = rng.integers(0, F, size=n_trees)
    th = np.empty(n_trees); lp = np.full(n_trees, 0.5); rp = np.full(n_trees, 0.5)
    for t in range(n_trees):
        f = fi[t]
        col = X[:, f]
        cand = col[rng.integers(0, L, size=n_thresh)]          # (nt,)
        masks = col[:, None] <= cand[None, :]                  # (L, nt)
        lTot = masks.sum(0).astype(np.float64)
        rTot = L - lTot
        lBull = (masks * yb[:, None]).sum(0)
        rBull = sBull - lBull
        with np.errstate(divide="ignore", invalid="ignore"):
            pL = np.where(lTot > 0, lBull / lTot, 0.0)
            pR = np.where(rTot > 0, rBull / rTot, 0.0)
            giniL = 1.0 - pL * pL - (1.0 - pL) ** 2
            giniR = 1.0 - pR * pR - (1.0 - pR) ** 2
            wg = (lTot * giniL + rTot * giniR) / L
        gain = np.where((lTot > 0) & (rTot > 0), gini_base - wg, -1.0)
        b = int(np.argmax(gain))
        th[t] = cand[b]; lp[t] = pL[b]; rp[t] = pR[b]
    return fi, th, lp, rp


def _predict_prob(stumps, xcur):
    fi, th, lp, rp = stumps
    vals = xcur[fi]
    return float(np.where(vals <= th, lp, rp).mean())


def run_backtest(
    opens, highs, lows, closes,
    volumes=None,
    probThreshold: float = 0.60, atrMultTP: float = 2.0, atrMultSL: float = 2.0,
    maxHold: int = 20, lookback: int = 60, numTrees: int = 30,
    signalCooldown: int = 10, anchorType: str = "RSI", anchorLen: int = 14,
    trendLen: int = 20, momLen: int = 10, tpSlLen: int = 14,
    trade_mode: str = "Both", retrain_every: int = 3, seed: int = 42,
    target_horizon: int = 1,
    return_trades: bool = False, _stop_event=None, _pause_event=None,
):
    o = np.asarray(opens, float); h = np.asarray(highs, float)
    l = np.asarray(lows, float);  c = np.asarray(closes, float)
    n = len(c)
    lookback = int(lookback); numTrees = int(numTrees); maxHold = int(maxHold)
    retrain_every = max(1, int(retrain_every))
    if n < lookback + maxHold + 5:
        return None

    H = pd.Series(h); L = pd.Series(l); C = pd.Series(c)
    vol = (pd.Series(np.asarray(volumes, float)) if (volumes is not None and len(volumes) == n)
           else None)

    # ── features (scaled ~0-100) ──────────────────────────────────────────────
    if anchorType == "Stochastic":
        anchor = _stoch(C, H, L, anchorLen)
    elif anchorType == "MFI" and vol is not None and vol.sum() > 0:
        anchor = _mfi(H, L, C, vol, anchorLen)
    elif anchorType == "ZScore":
        m = C.rolling(anchorLen, min_periods=1).mean()
        s = C.rolling(anchorLen, min_periods=1).std().replace(0.0, np.nan)
        anchor = (50 + (C - m) / s * 16.67).clip(0, 100).fillna(50.0)
    else:
        anchor = _rsi(C, anchorLen)

    bar_idx = pd.Series(np.arange(n, dtype=float))
    corr = C.rolling(trendLen, min_periods=trendLen).corr(bar_idx).fillna(0.0)
    trend = (50.0 + corr * 50.0).clip(0, 100)

    mom = C.diff(momLen)
    atr_m = _atr(H, L, C, momLen).replace(0.0, np.nan)
    momfeat = (50.0 + (mom / atr_m) * 16.67).clip(0, 100).fillna(50.0)

    atr_tp = _atr(H, L, C, tpSlLen).bfill().fillna(0.0).to_numpy()

    Feat = np.column_stack([anchor.to_numpy(), trend.to_numpy(), momfeat.to_numpy()])
    Feat = np.nan_to_num(Feat, nan=50.0)
    # target: is price higher `target_horizon` bars ahead? (1 = faithful next-bar)
    th_ = max(1, int(target_horizon))
    nextup = (np.roll(c, -th_) > c).astype(np.int64)   # nextup[i] = close[i+th] > close[i]
    nextup[-th_:] = 0

    allow_long = trade_mode in ("Long Only", "Both")
    allow_short = trade_mode in ("Short Only", "Both")
    rng = np.random.default_rng(int(seed))
    n_thresh = 10

    pnl_list, trade_log = [], []
    pos = None                  # dict(side, bar, ep, tp, sl)
    last_bull = last_bear = -10 ** 9
    stumps = None

    # last usable entry bar: leave room for resolution
    last_i = n - 2
    for i in range(lookback, last_i + 1):
        if _stop_event is not None and getattr(_stop_event, "is_set", lambda: False)():
            break

        # ── manage an open position (resolve on THIS bar's range) ─────────────
        if pos is not None:
            side = pos["side"]
            tp, sl = pos["tp"], pos["sl"]
            tp_hit = (h[i] >= tp) if side > 0 else (l[i] <= tp)
            sl_hit = (l[i] <= sl) if side > 0 else (h[i] >= sl)
            expired = (i - pos["bar"]) >= maxHold
            if sl_hit:                      # pessimistic: stop wins ties
                px = sl
            elif tp_hit:
                px = tp
            elif expired:
                px = c[i]
            else:
                px = None
            if px is not None:
                pnl = (px - pos["ep"]) if side > 0 else (pos["ep"] - px)
                pnl_list.append(pnl)
                if return_trades:
                    trade_log.append((pos["bar"], i, float(pnl)))
                pos = None
            # no pyramiding; one position at a time
            continue

        # ── (re)train + predict ───────────────────────────────────────────────
        # Training labels look `th_` bars ahead, so the newest sample we may use is
        # the one whose outcome is already realised by bar i: index i-th_ (inclusive).
        # For th_=1 this is the standard [i-lookback : i] window (no look-ahead).
        _end = i - (th_ - 1)
        if _end - lookback < 0:
            continue
        if stumps is None or ((i - lookback) % retrain_every == 0):
            Xtr = Feat[_end - lookback:_end]
            ytr = nextup[_end - lookback:_end]
            if np.unique(ytr).size < 2:
                stumps = None
                continue
            stumps = _train_stumps(Xtr, ytr, numTrees, n_thresh, rng)
        if stumps is None:
            continue
        p_up = _predict_prob(stumps, Feat[i])
        p_dn = 1.0 - p_up

        bull = p_up >= probThreshold and (i - last_bull) >= signalCooldown
        bear = p_dn >= probThreshold and (i - last_bear) >= signalCooldown

        a = atr_tp[i]
        if a <= 0:
            continue
        ep = c[i]
        if bull and allow_long:
            pos = {"side": +1, "bar": i, "ep": ep,
                   "tp": ep + atrMultTP * a, "sl": ep - atrMultSL * a}
            last_bull = i
        elif bear and allow_short:
            pos = {"side": -1, "bar": i, "ep": ep,
                   "tp": ep - atrMultTP * a, "sl": ep + atrMultSL * a}
            last_bear = i

    # close any runner at the last bar
    if pos is not None:
        px = c[-1]
        pnl = (px - pos["ep"]) if pos["side"] > 0 else (pos["ep"] - px)
        pnl_list.append(pnl)
        if return_trades:
            trade_log.append((pos["bar"], n - 1, float(pnl)))

    if not pnl_list:
        return None
    pnls = np.asarray(pnl_list, float)
    wins = pnls[pnls > 0]; losses = pnls[pnls < 0]
    gw = float(wins.sum()); gl = float(-losses.sum())
    cum = np.cumsum(pnls); peak = np.maximum.accumulate(cum)
    out = {
        "total_pnl": float(pnls.sum()),
        "num_trades": int(len(pnls)),
        "win_rate": float(100.0 * len(wins) / len(pnls)) if len(pnls) else 0.0,
        "profit_factor": (gw / gl) if gl > 1e-9 else (float("inf") if gw > 0 else 0.0),
        "max_drawdown": float((cum - peak).min()) if len(cum) else 0.0,
        "avg_pnl": float(pnls.mean()),
        "wins": int(len(wins)), "losses": int(len(losses)),
    }
    if return_trades:
        out["trades"] = trade_log
    return out
