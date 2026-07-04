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

__all__ = ["gate_trades", "entry_features", "gate_validate", "gate_explain",
           "adversarial_validation"]


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
                min_history=30, refit_every=25, seed=42, feats=None):
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

    F = feats if feats is not None else entry_features(arrays)[0]
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


# ── gate VALIDATE: choose the gate honestly, then one look at the lockbox ─────
def _slice_stats(entry_ts, pnls, t0=None, t1=None):
    """Stats over trades whose ENTRY falls in [t0, t1) (None = open end)."""
    m = np.ones(len(pnls), bool)
    if t0 is not None:
        m &= entry_ts >= t0
    if t1 is not None:
        m &= entry_ts < t1
    return _stats(np.asarray(pnls, float)[m])


def _rec(s):
    """Recovery factor = profit per point of drawdown — the fair gated-vs-ungated
    yardstick: a gate trades LESS, so raw total PnL structurally favours ungated,
    but equal-risk sizing scales with drawdown. Positive-pnl/zero-dd → big."""
    dd = abs(s.get("max_drawdown") or 0.0)
    p = s.get("total_pnl") or 0.0
    return (p / dd) if dd > 1e-9 else (999.0 if p > 0 else 0.0)


def gate_validate(arrays, trades, gates=("logistic", "rf", "xgb"),
                  thresholds=(0.50, 0.55, 0.60), lockbox_months=12,
                  min_kept=50, windows=4, min_history=30, refit_every=25,
                  seed=42):
    """The honest way to pick a gate (board 4.10, ROADMAP #25).

    Discipline, by construction:
      • the last `lockbox_months` are RESERVED: every candidate (model x cut-off)
        is ranked ONLY on its pre-lockbox results;
      • the winner gets exactly ONE look at the lockbox — and the lockbox numbers
        of the losing candidates never leave this function, so lockbox-shopping
        is impossible by design;
      • the gate model itself trains rolling on past trades only (gate_trades),
        so even the lockbox slice mirrors live behaviour;
      • 'ungated' (take every trade) is always candidate #0 — if no gate beats
        it pre-lockbox, the verdict says so and the one-look is skipped.

    Returns a compact json-safe dict for the web card.
    """
    if not trades:
        return None
    idx = arrays["index"]
    T = sorted([(int(t[0]), int(t[1]), float(t[2])) for t in trades if len(t) >= 3],
               key=lambda t: t[0])
    nb = len(idx)
    entry_ts = np.array([idx[min(t[0], nb - 1)] for t in T])
    pnls_all = np.array([t[2] for t in T], float)
    lb_start = idx[-1] - pd.DateOffset(months=int(lockbox_months))
    t_first = entry_ts.min()

    feats = entry_features(arrays)[0]                      # compute once, reuse 9x
    ung_pre = _slice_stats(entry_ts, pnls_all, None, lb_start)
    ung_lb = _slice_stats(entry_ts, pnls_all, lb_start, None)

    cands = []
    lb_secret = {}                                         # lockbox stats stay HERE
    for m in gates:
        for th in thresholds:
            g = gate_trades(arrays, T, model=m, threshold=th,
                            min_history=min_history, refit_every=refit_every,
                            seed=seed, feats=feats)
            kept = g["trades"]
            k_ts = np.array([idx[min(t[0], nb - 1)] for t in kept])
            k_p = np.array([t[2] for t in kept], float)
            pre = _slice_stats(k_ts, k_p, None, lb_start)
            key = f"{m}@{th:.2f}"
            lb_secret[key] = (_slice_stats(k_ts, k_p, lb_start, None), k_ts, k_p)
            cands.append({"model": str(m), "threshold": float(th),
                          "impl": g["summary"].get("model_impl", str(m)),
                          "kept_pre": int(pre["num_trades"]),
                          "pre": pre, "eligible": pre["num_trades"] >= int(min_kept)})

    # ── selection: pre-lockbox RECOVERY FACTOR (pnl per point of drawdown) among
    #    eligible gated candidates — the equal-risk yardstick, not raw totals.
    elig = [c for c in cands if c["eligible"]]
    chosen = max(elig, key=lambda c: _rec(c["pre"])) if elig else None
    gate_earns = bool(chosen and _rec(chosen["pre"]) > _rec(ung_pre))

    out = {
        "gates": list(gates), "thresholds": [float(t) for t in thresholds],
        "n_candidates": len(cands), "lockbox_months": int(lockbox_months),
        "windows": int(windows), "min_kept": int(min_kept),
        "span": [str(pd.Timestamp(t_first).date()), str(idx[-1].date())],
        "lockbox_from": str(pd.Timestamp(lb_start).date()),
        "ungated_pre": ung_pre, "ungated_lockbox": ung_lb,
        "candidates": [{"model": c["model"], "threshold": c["threshold"],
                        "kept_pre": c["kept_pre"],
                        "pre_pnl": c["pre"]["total_pnl"],
                        "pre_pf": c["pre"]["profit_factor"],
                        "pre_wr": c["pre"]["win_rate"],
                        "pre_rec": round(_rec(c["pre"]), 2),
                        "eligible": c["eligible"]} for c in cands],
        "ungated_pre_rec": round(_rec(ung_pre), 2),
        "gate_earns_pre": gate_earns,
        "chosen": None, "lockbox": None,
    }
    if chosen is None:
        out["verdict"] = "NO ELIGIBLE GATE (all kept too few pre-lockbox trades)"
        return out
    key = f"{chosen['model']}@{chosen['threshold']:.2f}"
    ch_lb, ch_ts, ch_p = lb_secret[key]
    out["chosen"] = {"model": chosen["model"], "threshold": chosen["threshold"],
                     "impl": chosen["impl"], "pre": chosen["pre"]}
    if not gate_earns:
        out["verdict"] = "UNGATED WINS PRE-LOCKBOX — no gate earns its keep; lockbox not opened"
        return out

    # ── consistency: chosen vs ungated across chronological pre-lockbox slices ─
    edges = pd.date_range(pd.Timestamp(t_first), pd.Timestamp(lb_start),
                          periods=int(windows) + 1)
    held = 0; wrows = []
    for i in range(int(windows)):
        a, b = edges[i], edges[i + 1]
        gw = _slice_stats(ch_ts, ch_p, a, b)
        uw = _slice_stats(entry_ts, pnls_all, a, b)
        ok = gw["profit_factor"] >= uw["profit_factor"]   # quality, per window
        held += int(ok)
        wrows.append({"from": str(a.date()), "to": str(b.date()),
                      "gated_pf": round(min(gw["profit_factor"], 99), 2),
                      "ungated_pf": round(min(uw["profit_factor"], 99), 2),
                      "held": ok})
    out["consistency"] = {"held": held, "windows": int(windows), "rows": wrows}

    # ── the ONE look at the lockbox (chosen candidate only) ───────────────────
    lb_helped = _rec(ch_lb) >= _rec(ung_lb)               # equal-risk yardstick
    out["lockbox"] = {"gated": ch_lb, "ungated": ung_lb,
                      "gated_rec": round(_rec(ch_lb), 2),
                      "ungated_rec": round(_rec(ung_lb), 2),
                      "helped": bool(lb_helped)}
    out["verdict"] = ("LOCKBOX HELD — gate beat ungated on the untouched slice"
                      if lb_helped else
                      "LOCKBOX FAILED — gate lost to ungated out-of-sample (pre-lockbox win was likely fit)")
    return out


# ── gate EXPLAIN: which entry features the gate keys on (board 5 · SHAP-style) ──
def gate_explain(arrays, trades, model="logistic", min_history=30, seed=42, top=10):
    """Global feature attribution for the ML gate — the "which inputs does the
    bouncer actually use" panel (board §5 SHAP).

    Trains ONE gate model on ALL completed trades (the as-of-now deployed gate: same
    entry features + |pnl| weighting as gate_trades) and reports, per feature:
      • imp  — PERMUTATION importance: how much the fit degrades (Δ log-loss) when
               that one input is shuffled. Model-agnostic, so it's directly
               comparable across logistic / rf / xgb — the honest "how hard the gate
               leans on this input" number.
      • rel  — imp scaled 0..1 (for the bar chart).
      • native — the model's own importance (|coef| logistic / feature_importances_
               trees), as a cross-check.
      • dir  — +1 if a HIGHER value pushes P(win) UP (gate tends to KEEP), -1 if it
               pushes DOWN (SKIP), 0 if flat.

    If the optional `shap` package is installed, TREE gates (rf/xgb) use real SHAP
    values (TreeExplainer mean|value|) for importance + direction; otherwise the
    permutation importance above stands in — so this works with or without shap.
    Per-trade LOCAL explanations ("why was THIS trade skipped") are a further step
    (no per-trade drill-down UI yet). Returns a json-safe dict or None if there
    aren't enough trades / only one outcome class.
    """
    if not trades:
        return None
    T = [(int(t[0]), int(t[1]), float(t[2])) for t in trades if len(t) >= 3]
    if len(T) < max(int(min_history), 40):
        return None
    E = np.array([t[0] for t in T]); P = np.array([t[2] for t in T], float)
    y = (P > 0).astype(int)
    if np.unique(y).size < 2:
        return None

    F, names = entry_features(arrays)
    nb = len(F)
    X = F[np.clip(E, 0, nb - 1)]
    w = np.abs(P) + 1e-9

    mdl = _make_model(model, seed)
    mdl.fit(X, y, clf__sample_weight=w)

    # permutation importance — model-agnostic, profit-weighted, Δ log-loss
    try:
        from sklearn.inspection import permutation_importance
        pim = permutation_importance(mdl, X, y, scoring="neg_log_loss",
                                     n_repeats=6, random_state=int(seed),
                                     sample_weight=w)
        imp = np.asarray(pim.importances_mean, float)
    except Exception:
        imp = np.zeros(len(names))

    # the model's own importance, for cross-check
    clf = mdl.named_steps.get("clf")
    if hasattr(clf, "coef_"):
        nat = np.abs(np.ravel(clf.coef_))
    elif hasattr(clf, "feature_importances_"):
        nat = np.asarray(clf.feature_importances_, float)
    else:
        nat = np.zeros(len(names))
    if len(nat) != len(names):
        nat = np.zeros(len(names))

    # direction: sign of corr(raw feature, predicted P(win))
    try:
        p = mdl.predict_proba(X)[:, 1]
    except Exception:
        p = np.full(len(X), 0.5)
    dirs = []
    for j in range(X.shape[1]):
        xj = X[:, j]
        if np.std(xj) < 1e-12 or np.std(p) < 1e-12:
            dirs.append(0)
        else:
            c = float(np.corrcoef(xj, p)[0, 1])
            dirs.append(1 if c > 0.02 else (-1 if c < -0.02 else 0))

    # ── prefer REAL SHAP for tree gates when the package is present (owner-approved
    #    dep 2026-07-04); otherwise the permutation importance above stands in. ──
    method = "permutation Δlog-loss + native"
    shap_used = False
    if str(model).lower() in ("rf", "forest", "random_forest", "randomforest",
                              "boosted", "xgb", "xgboost", "hgb", "gbt"):
        try:
            import shap
            Xs = mdl.named_steps["sc"].transform(X)
            if len(Xs) > 2000:                        # cap for speed
                rng = np.random.RandomState(int(seed))
                Xs = Xs[rng.choice(len(Xs), 2000, replace=False)]
            sv = shap.TreeExplainer(mdl.named_steps["clf"]).shap_values(Xs)
            if isinstance(sv, list):                  # [class0, class1]
                sv = np.asarray(sv[-1])
            sv = np.asarray(sv)
            if sv.ndim == 3:                          # (n, feat, class) -> class 1
                sv = sv[:, :, -1]
            imp = np.abs(sv).mean(axis=0)
            dirs = []
            for j in range(sv.shape[1]):
                xj = Xs[:, j]
                if np.std(xj) < 1e-12 or np.std(sv[:, j]) < 1e-12:
                    dirs.append(0)
                else:
                    c = float(np.corrcoef(xj, sv[:, j])[0, 1])
                    dirs.append(1 if c > 0.02 else (-1 if c < -0.02 else 0))
            method = "SHAP · TreeExplainer mean|value|"
            shap_used = True
        except Exception:
            pass

    mx = float(max(np.max(imp), 1e-9))
    feats_out = [{"name": names[j], "imp": round(float(imp[j]), 5),
                 "rel": round(float(max(imp[j], 0.0) / mx), 4),
                 "native": round(float(nat[j]), 4), "dir": int(dirs[j])}
                for j in range(len(names))]
    feats_out.sort(key=lambda d: d["imp"], reverse=True)
    return {
        "model": str(model), "impl": getattr(mdl, "_gate_impl", str(model)),
        "n": int(len(T)), "base_rate": round(float(100.0 * y.mean()), 1),
        "method": method, "shap": bool(shap_used),
        "features": feats_out[:int(top)],
    }


# ── adversarial validation: is the lockbox a DIFFERENT regime? (board §4) ───────
def adversarial_validation(arrays, lb_start, model="rf", max_per_class=4000, seed=42):
    """Can a classifier tell the LOCKBOX period apart from the training history?

    The lockbox only proves an edge transfers if the reserved slice *looks like* the
    data the strategy was built on. Here we label every pre-lockbox bar class 0 and
    every lockbox bar class 1, train a classifier on the market-state features
    (entry_features: momentum / volatility / trend / range-pos / clock), and read the
    cross-validated ROC-AUC:
      • AUC ~ 0.50 → the two periods are INDISTINGUISHABLE — a lockbox PASS is trustworthy;
      • AUC high  → the lockbox is a DIFFERENT regime — a PASS there is weaker evidence,
                    and a FAIL might just be regime change, not a broken edge.
    Also reports which features drifted most (importance) and the direction of the
    shift (lockbox mean − pre mean, in pre-period std units). Informational — it
    contextualizes the lockbox, it does not change the verdict. sklearn-only.
    """
    import pandas as pd
    idx = arrays.get("index")
    if idx is None:
        return None
    X, names = entry_features(arrays)
    ts = pd.DatetimeIndex(idx)
    if ts.tz is not None:                    # master index is tz-aware; compare tz-naive
        ts = ts.tz_localize(None)
    lb = pd.Timestamp(lb_start)
    pre = np.where(ts < lb)[0]
    post = np.where(ts >= lb)[0]
    if len(pre) < 100 or len(post) < 100:
        return None
    rng = np.random.RandomState(int(seed))

    def _samp(ix):
        return ix if len(ix) <= max_per_class else rng.choice(ix, max_per_class, replace=False)

    pi, qi = _samp(pre), _samp(post)
    Xa = np.vstack([X[pi], X[qi]])
    ya = np.r_[np.zeros(len(pi)), np.ones(len(qi))]
    from sklearn.model_selection import cross_val_score, StratifiedKFold
    mdl = _make_model(model, seed)
    try:
        auc = float(np.mean(cross_val_score(
            mdl, Xa, ya, scoring="roc_auc",
            cv=StratifiedKFold(4, shuffle=True, random_state=int(seed)))))
    except Exception:
        return None

    mdl.fit(Xa, ya)
    clf = mdl.named_steps.get("clf")
    if hasattr(clf, "feature_importances_"):
        imp = np.asarray(clf.feature_importances_, float)
    elif hasattr(clf, "coef_"):
        imp = np.abs(np.ravel(clf.coef_))
    else:
        imp = np.zeros(len(names))
    if len(imp) != len(names):
        imp = np.zeros(len(names))
    drift = []
    for j in range(len(names)):
        pm = float(X[pi][:, j].mean()); lm = float(X[qi][:, j].mean())
        sd = float(X[pi][:, j].std()) or 1.0
        drift.append({"name": names[j], "imp": round(float(imp[j]), 4),
                      "shift": round((lm - pm) / sd, 2)})
    drift.sort(key=lambda d: d["imp"], reverse=True)

    if auc < 0.55:
        v = "indistinguishable — the lockbox looks like the training history; trust the holdout"
    elif auc < 0.70:
        v = "mild drift — a modestly different regime"
    elif auc < 0.85:
        v = "notable drift — the lockbox is a meaningfully different regime; weigh the PASS/FAIL accordingly"
    else:
        v = "strong drift — the lockbox is a different market; a PASS there is weak evidence (and a FAIL may be regime, not a broken edge)"
    return {"auc": round(auc, 3), "verdict": v, "model": str(model),
            "n_pre": int(len(pre)), "n_lockbox": int(len(post)),
            "drift_features": drift[:5], "lockbox_from": str(lb.date())}
