"""ML trade gate — the plug-and-play "bouncer" (board 3A.2, ROADMAP #25).

Meta-labeling (Lopez de Prado, Advances in Financial ML 2018): the base strategy
generates its trades exactly as normal; a secondary model — trained ONLY on the
trades that finished strictly BEFORE each new trade's entry bar — scores each
trade's win-chance from conditions at entry, and trades under the threshold are
skipped. The strategy file is never touched: the gate consumes the standard
(entry_bar, exit_bar, pnl) trade tuples every plugin already returns.

Leakage rules (the whole point):
  • a trade may only be judged by a model fit on trades whose EXIT bar is strictly
    before this trade's ENTRY bar (its outcome was known when the signal fired);
  • until `min_history` trades have completed, the bouncer is off duty — early
    trades PASS THROUGH ungated (status "warmup"), so a short window is honest,
    not silently ungated-then-gated;
  • refits happen every `refit_every` newly-completed trades (a per-trade refit
    is pointlessly slow; the model barely moves one trade at a time).

Model zoo: "logistic" (sklearn, the KISS baseline), "rf" (shallow sklearn
RandomForest), "xgb" (literal XGBoost — installed 2026-07-02, owner-approved;
sklearn HistGradientBoosting is the automatic fallback if the package is
missing). The doctrine: if rf/xgb can't beat logistic out-of-sample, the extra
complexity isn't earning anything.
"""
import numpy as np
import pandas as pd

__all__ = ["gate_trades", "entry_features"]


# ── features at the entry bar (OHLC + clock only — no volume dependency) ───────
def _atr(h, l, c, n):
    tr = pd.concat([h - l, (h - c.shift(1)).abs(), (l - c.shift(1)).abs()],
                   axis=1).max(axis=1)
    return tr.ewm(alpha=1.0 / max(1, n), adjust=False).mean()


def entry_features(arrays):
    """Full-series feature matrix (n_bars x n_feat) + names. Row i describes the
    market AS OF bar i's close using only bars <= i — safe to read at entry."""
    C = pd.Series(np.asarray(arrays["close"], float))
    H = pd.Series(np.asarray(arrays["high"], float))
    L = pd.Series(np.asarray(arrays["low"], float))
    idx = arrays.get("index")

    atr14 = _atr(H, L, C, 14).replace(0.0, np.nan)
    atr100 = _atr(H, L, C, 100).replace(0.0, np.nan)
    feats = {
        # momentum, in ATR units (comparable across price levels / eras)
        "mom_5":    (C - C.shift(5)) / atr14,
        "mom_20":   (C - C.shift(20)) / atr14,
        # volatility regime: absolute level + expansion vs the slow baseline
        "atr_norm": atr14 / C,
        "atr_ratio": atr14 / atr100,
        # trend strength (rolling corr of close vs time, like the GainzAlgo port)
        "trend_20": C.rolling(20, min_periods=20).corr(
            pd.Series(np.arange(len(C), dtype=float))),
        # where price sits in the recent 20-bar range (0 = low, 1 = high)
        "range_pos": (C - L.rolling(20, min_periods=1).min())
                     / (H.rolling(20, min_periods=1).max()
                        - L.rolling(20, min_periods=1).min()).replace(0.0, np.nan),
    }
    if idx is not None:
        tod = (idx.hour * 60 + idx.minute) / 1440.0 * 2 * np.pi
        feats["tod_sin"] = pd.Series(np.sin(tod), index=C.index)
        feats["tod_cos"] = pd.Series(np.cos(tod), index=C.index)
        feats["dow"] = pd.Series(idx.dayofweek.astype(float), index=C.index)
    X = pd.DataFrame(feats)
    X = X.replace([np.inf, -np.inf], np.nan).fillna(0.0)
    return X.to_numpy(float), list(X.columns)


# ── stats in the engine's exact shape ──────────────────────────────────────────
def _stats(pnls):
    pnls = np.asarray(list(pnls), float)
    n = len(pnls)
    wins = pnls[pnls > 0]; losses = pnls[pnls < 0]
    gw = float(wins.sum()); gl = float(-losses.sum())
    cum = np.cumsum(pnls) if n else np.array([0.0])
    peak = np.maximum.accumulate(cum)
    return {
        "total_pnl": float(pnls.sum()), "num_trades": int(n),
        "win_rate": float(100.0 * len(wins) / n) if n else 0.0,
        "profit_factor": (gw / gl) if gl > 1e-9 else (float("inf") if gw > 0 else 0.0),
        "max_drawdown": float((cum - peak).min()) if n else 0.0,
        "avg_pnl": float(pnls.mean()) if n else 0.0,
        "wins": int(len(wins)), "losses": int(len(losses)),
    }


def _make_model(name, seed):
    """Gate-model zoo. All shallow/regularized on purpose: training sets are a few
    hundred trades, and an expressive model would memorize them. Uniform Pipeline
    (scaler is a no-op for the trees, harmless) so fit(clf__sample_weight=…) works
    for every member."""
    name = str(name or "").lower()
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler
    if name in ("logistic", "logit", "lr"):
        from sklearn.linear_model import LogisticRegression
        clf = LogisticRegression(max_iter=500, C=1.0, random_state=int(seed))
    elif name in ("rf", "forest", "random_forest", "randomforest"):
        from sklearn.ensemble import RandomForestClassifier
        clf = RandomForestClassifier(n_estimators=100, max_depth=4,
                                     min_samples_leaf=10, n_jobs=-1,
                                     random_state=int(seed))
    elif name in ("boosted", "xgb", "xgboost", "hgb", "gbt"):
        # literal XGBoost (installed 2026-07-02, owner-approved); sklearn
        # HistGradientBoosting stays as the automatic fallback so the gate
        # still works on a machine without the package.
        try:
            from xgboost import XGBClassifier
            clf = XGBClassifier(max_depth=3, n_estimators=100, learning_rate=0.1,
                                tree_method="hist", n_jobs=-1, verbosity=0,
                                random_state=int(seed))
            impl = "xgboost"
        except ImportError:
            from sklearn.ensemble import HistGradientBoostingClassifier
            clf = HistGradientBoostingClassifier(max_depth=3, max_iter=100,
                                                 learning_rate=0.1,
                                                 random_state=int(seed))
            impl = "hgb-fallback"
        from sklearn.pipeline import Pipeline as _P
        pipe = _P([("sc", StandardScaler()), ("clf", clf)])
        pipe._gate_impl = impl
        return pipe
    else:
        raise ValueError(
            f"unknown gate model '{name}' (supported: logistic, rf, boosted)")
    return Pipeline([("sc", StandardScaler()), ("clf", clf)])


# ── the gate itself ────────────────────────────────────────────────────────────
def gate_trades(arrays, trades, model="logistic", threshold=0.50,
                min_history=30, refit_every=25, seed=42):
    """Walk the trade list chronologically; keep/skip each trade by the model's
    profit-weighted win-probability, trained only on trades completed before its
    entry.

    Training samples are WEIGHTED by |pnl| (de Prado's practice): a rare big
    winner counts for more than many small losers, so P >= 0.5 approximates
    "positive expected value", not "wins more often than not" — critical for
    low-win-rate / big-winner strategies (ENGU wins ~32% of the time on purpose).

    arrays : the load_master_arrays dict the backtest ran on (same slice!).
    trades : [(entry_bar, exit_bar, pnl), ...] — pnl NET (gate after costs so the
             model learns net wins, the thing that matters).
    Returns {"trades": kept, "stats": gated headline stats, "summary": {...}}
    or None if there's nothing to gate.
    """
    if not trades:
        return None
    T = [(int(t[0]), int(t[1]), float(t[2])) for t in trades if len(t) >= 3]
    T.sort(key=lambda t: t[0])                      # chronological by entry
    E = np.array([t[0] for t in T]); Xi = np.array([t[1] for t in T])
    P = np.array([t[2] for t in T]); y = (P > 0).astype(int)
    n = len(T)

    F, _names = entry_features(arrays)
    nb = len(F)
    Ecl = np.clip(E, 0, nb - 1)                     # guard odd bar indices
    X = F[Ecl]

    mdl = None; fitted_on = -1
    keep = np.ones(n, bool)
    prob = np.full(n, np.nan)
    warmup = 0; n_fits = 0; degenerate = 0
    thr = float(threshold)

    for k in range(n):
        done = Xi[:k] < E[k]                        # finished strictly before entry
        nd = int(done.sum())
        if nd < int(min_history):
            warmup += 1                             # bouncer off duty: pass through
            continue
        if mdl is None or (nd - fitted_on) >= int(refit_every):
            ytr = y[:k][done]
            if np.unique(ytr).size < 2:             # all past wins / all past losses:
                degenerate += 1                     # nothing learnable — pass through
                continue
            mdl = _make_model(model, seed)
            # |pnl| sample weights: learn "which trades MATTER", not raw frequency
            mdl.fit(X[:k][done], ytr,
                    clf__sample_weight=np.abs(P[:k][done]) + 1e-9)
            fitted_on = nd; n_fits += 1
        p = float(mdl.predict_proba(X[k:k + 1])[0, 1])
        prob[k] = p
        if p < thr:
            keep[k] = False

    kept = [T[i] for i in range(n) if keep[i]]
    skipped_pnls = P[~keep]
    before = _stats(P); after = _stats([t[2] for t in kept])
    return {
        "trades": kept,
        "stats": after,
        "summary": {
            "model": str(model),
            "model_impl": getattr(mdl, "_gate_impl", str(model)),
            "threshold": thr,
            "min_history": int(min_history), "refit_every": int(refit_every),
            "n_fits": int(n_fits), "warmup": int(warmup),
            "degenerate": int(degenerate),
            "n_total": int(n), "n_kept": int(len(kept)),
            "n_skipped": int(n - len(kept)),
            "skipped_pnl": float(skipped_pnls.sum()),   # what the bouncer turned away
            "skipped_wr": (float(100.0 * (skipped_pnls > 0).sum() / len(skipped_pnls))
                           if len(skipped_pnls) else None),
            "ungated": before, "gated": after,
        },
    }
