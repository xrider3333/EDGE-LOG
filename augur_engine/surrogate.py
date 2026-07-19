"""Multi-surrogate bake-off — param-discovery READ-OUT (#31, P1 only).

Design doc: docs/SURROGATE_DISCOVERY_DESIGN.md — this module implements pipeline
steps 2-4 + 6 (§2), the bake-off roster (§3), the per-model cards (§4), and
respects the guardrails (§6). It deliberately does NOT implement step 5
(steering/acquisition, P2) — the sampler that produced `points` is untouched;
this module only FITS models to already-sampled configs and READS the joint
surface off them (interactions, joint optimum, ground-truth check).

IS-ONLY (§6): this module never loads data or a lockbox itself. Every point it
ever sees is handed in by the caller (auto.py's `_pts_full`, built from
`_ev(0, ksplit, ...)` — the in-sample window only). `ground_truth_fn`, if
given, is likewise the caller's own IS evaluator; nothing here reaches past it.

DETERMINISM: every model/CV call is seeded (default 42) and every estimator
that supports it is pinned to n_jobs=1 — sklearn/xgboost's multi-threaded
reductions are not always bit-identical across worker counts/machines, and a
surrogate read-out that changes between two runs on the same points would be
worse than useless for the owner's "which model do I trust" question.

NO NEW DEPENDENCIES: numpy/sklearn are treated as hard dependencies (already
used throughout augur_engine/analytics.py + ml_gate.py). xgboost and shap are
OPTIONAL — imported once at module top with graceful degradation; if either is
missing, the corresponding roster entry / knob-screen feature is skipped with a
`note`/`skipped` string instead of raising. A run must never die because a
surrogate model couldn't be built (auto.py's integration wraps the whole call
in try/except too, per the design's guardrail).

ROSTER — a small adapter registry, so a future model (e.g. pyGAM) is ONE new
entry: `_build_roster()` returns a list of {name, kind, estimator, grid} (or
{name, skipped: reason}). Adding pyGAM later means adding one more `try:
import pygam ... roster.append({...})` block; nothing else in this file
changes (the fit/score/predict/interaction/knob-screen code is roster-generic).
"""
import itertools

import numpy as np

from sklearn.base import BaseEstimator, RegressorMixin
from sklearn.ensemble import RandomForestRegressor
from sklearn.gaussian_process import GaussianProcessRegressor
from sklearn.gaussian_process.kernels import ConstantKernel, Matern, RBF, WhiteKernel
from sklearn.linear_model import LassoCV, Ridge
from sklearn.model_selection import GridSearchCV, KFold
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import PolynomialFeatures, StandardScaler

try:
    from xgboost import XGBRegressor
    HAS_XGBOOST = True
except Exception:
    XGBRegressor = None
    HAS_XGBOOST = False

try:
    import shap as _shap
    HAS_SHAP = True
except Exception:
    _shap = None
    HAS_SHAP = False

__all__ = ["surrogate_bakeoff", "HAS_XGBOOST", "HAS_SHAP"]

# ── guardrail thresholds (documented, not vibes) ───────────────────────────────
MIN_POINTS = 40                 # below this the surface is too thin to fit anything honest
MIN_VARYING_PARAMS = 2          # need >=2 varying knobs for a JOINT surface to mean anything
MAX_CANDIDATES = 20000          # shared dense-but-bounded argmax grid, every model uses the same one
GP_MAX_POINTS = 1000            # GaussianProcessRegressor is O(n^3); subsample above this, deterministically
INTERACTION_GRID_N = 8          # <=8x8 2-D PD grid per pair (design §3/§4)
INTERACTION_BG_N = 50           # background rows for the marginal/joint PD average (deterministic subsample)
DEAD_LASSO_EPS = 1e-6           # LassoCV coefficient at/under this = "linearly dead" (L1 truly zeroed it)
WEAK_NORM_THRESH = 0.10         # combined normalized (lasso, shap/importance) score below this = "weak"
GP_HIGH_UNCERTAINTY_MULT = 1.5  # GP optimum flagged HIGH-uncertainty if its std > this x the typical in-sample std


def _native(v):
    """Strip numpy scalar types down to plain python so every returned value is
    JSON/Firestore-safe (mirrors the same concern in auto.py/analytics.py)."""
    if v is None or isinstance(v, (bool, str)):
        return v
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating,)):
        return float(v)
    return v


def _collapse_conditional(params, dp):
    """Reset inactive conditional params (depends_on unmet) to their default.
    Duplicate of auto.py's `_collapse` — kept local (not imported) because
    auto.py imports THIS module for the integration call; importing back would
    be circular. Keep in sync if the depends_on contract ever changes."""
    pe = dict(params)
    for k, meta in (dp or {}).items():
        if not isinstance(meta, dict):
            continue
        cond = meta.get("depends_on")
        if cond and k in pe and not all(pe.get(dk) == dv for dk, dv in cond.items()):
            pe[k] = meta.get("default")
    return pe


def _json_safe_hyperparams(d):
    out = {}
    for k, v in (d or {}).items():
        if v is None or isinstance(v, (int, float, str, bool)):
            out[k] = v
        else:
            out[k] = str(v)          # e.g. a GP kernel object -> its repr
    return out


def _json_safe_row(row, pkeys, dp):
    out = {}
    for k in pkeys:
        v = row.get(k)
        meta = dp.get(k) or {}
        typ = meta.get("type", "float")
        if v is None:
            out[k] = None
        elif typ == "int":
            out[k] = int(round(float(v)))
        elif typ == "float":
            out[k] = round(float(v), 6)
        elif typ == "bool":
            out[k] = bool(v)
        else:
            out[k] = v
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Encoding: params -> model matrix (numeric as float; categorical/bool one-hot)
# ─────────────────────────────────────────────────────────────────────────────
class _Encoder:
    """Fits column layout once from (pkeys, dp, points); `transform` reuses it
    for the training rows, the candidate grid, and every interaction/PD row.
    Categorical value sets are the OBSERVED values across `points` UNION each
    param's own declared default (so a `_collapse_conditional` fallback to the
    default is always encodable, even on a value that was never sampled)."""

    def __init__(self, pkeys, dp, points):
        self.pkeys = list(pkeys)
        self.dp = dp or {}
        self.numeric_params = []
        self.cat_params = []
        self.cat_values = {}
        for k in self.pkeys:
            meta = self.dp.get(k) or {}
            typ = meta.get("type", "float")
            if typ in ("int", "float"):
                self.numeric_params.append(k)
            else:
                self.cat_params.append(k)
                vals = {p.get(k) for p in points if p.get(k) is not None}
                default = meta.get("default")
                if default is not None:
                    vals.add(default)
                self.cat_values[k] = sorted(vals, key=str)

        self.feature_names = list(self.numeric_params)
        self.feature_param = {k: k for k in self.numeric_params}
        self.cat_col_start = {}
        col = len(self.numeric_params)
        for k in self.cat_params:
            self.cat_col_start[k] = col
            for v in self.cat_values[k]:
                fname = f"{k}={v}"
                self.feature_names.append(fname)
                self.feature_param[fname] = k
                col += 1
        self.n_features = col

    def transform(self, rows):
        X = np.zeros((len(rows), self.n_features), dtype=float)
        for i, r in enumerate(rows):
            for j, k in enumerate(self.numeric_params):
                try:
                    X[i, j] = float(r.get(k, 0) or 0)
                except (TypeError, ValueError):
                    X[i, j] = 0.0
            for k in self.cat_params:
                v = r.get(k)
                start = self.cat_col_start[k]
                for vi, vv in enumerate(self.cat_values[k]):
                    if v == vv:
                        X[i, start + vi] = 1.0
        return X

    def group_columns(self):
        """param -> list of column indices belonging to it (1 for numeric, len(values) for cat)."""
        groups = {}
        for j, fname in enumerate(self.feature_names):
            groups.setdefault(self.feature_param[fname], []).append(j)
        return groups


# ─────────────────────────────────────────────────────────────────────────────
# GP adapter: its own X/y standardization (sklearn's TransformedTargetRegressor
# doesn't forward return_std=True through the inverse-transform step, which we
# need for the GP-only uncertainty_note) — R^2 is invariant to a fixed affine
# y-rescaling, and RMSE is rescaled back to raw PnL units before reporting.
# ─────────────────────────────────────────────────────────────────────────────
class _StdYGP(BaseEstimator, RegressorMixin):
    def __init__(self, kernel=None, y_mean=0.0, y_std=1.0):
        self.kernel = kernel
        self.y_mean = y_mean
        self.y_std = y_std

    def fit(self, X, y):
        self.scaler_ = StandardScaler().fit(X)
        Xs = self.scaler_.transform(X)
        ys = (np.asarray(y, dtype=float) - self.y_mean) / (self.y_std or 1.0)
        kernel = self.kernel
        if kernel is None:
            kernel = ConstantKernel(1.0) * Matern(length_scale=1.0, nu=1.5) + WhiteKernel(1e-3)
        self.gp_ = GaussianProcessRegressor(kernel=kernel, random_state=0,
                                            n_restarts_optimizer=0, normalize_y=False)
        self.gp_.fit(Xs, ys)
        return self

    def predict(self, X, return_std=False):
        Xs = self.scaler_.transform(X)
        if return_std:
            mu, sd = self.gp_.predict(Xs, return_std=True)
            return mu * (self.y_std or 1.0) + self.y_mean, sd * (self.y_std or 1.0)
        return self.gp_.predict(Xs) * (self.y_std or 1.0) + self.y_mean


def _build_roster(seed, y_mean, y_std):
    """The pluggable adapter registry (§3). Each entry: {name, kind, estimator,
    grid} ready for GridSearchCV, or {name, skipped: reason}. To add a new
    model (e.g. pyGAM), append one more try/except block here — nothing else
    in this file needs to change."""
    roster = []

    try:
        est = Pipeline([("poly", PolynomialFeatures(degree=2, include_bias=False)),
                        ("scale", StandardScaler()), ("ridge", Ridge())])
        roster.append({"name": "quadratic", "kind": "linear", "estimator": est,
                       "grid": {"ridge__alpha": [0.1, 1.0, 10.0]}})
    except Exception as e:
        roster.append({"name": "quadratic", "skipped": f"unavailable: {e}"})

    try:
        est = RandomForestRegressor(n_estimators=200, random_state=int(seed), n_jobs=1)
        roster.append({"name": "random_forest", "kind": "tree", "estimator": est,
                       "grid": {"max_depth": [3, 5, None], "min_samples_leaf": [2, 5]}})
    except Exception as e:
        roster.append({"name": "random_forest", "skipped": f"unavailable: {e}"})

    if HAS_XGBOOST:
        try:
            est = XGBRegressor(n_estimators=200, random_state=int(seed), n_jobs=1,
                               tree_method="hist", verbosity=0)
            roster.append({"name": "xgboost", "kind": "tree", "estimator": est,
                           "grid": {"max_depth": [2, 3, 4], "learning_rate": [0.05, 0.1]}})
        except Exception as e:
            roster.append({"name": "xgboost", "skipped": f"unavailable: {e}"})
    else:
        roster.append({"name": "xgboost", "skipped": "xgboost not installed"})

    try:
        kernels = [
            ConstantKernel(1.0) * Matern(length_scale=1.0, nu=1.5) + WhiteKernel(1e-3),
            ConstantKernel(1.0) * Matern(length_scale=0.3, nu=1.5) + WhiteKernel(1e-3),
            ConstantKernel(1.0) * RBF(length_scale=1.0) + WhiteKernel(1e-3),
        ]
        est = _StdYGP(kernel=None, y_mean=float(y_mean), y_std=float(y_std or 1.0))
        roster.append({"name": "gp", "kind": "gp", "estimator": est,
                       "grid": {"kernel": kernels}})
    except Exception as e:
        roster.append({"name": "gp", "skipped": f"unavailable: {e}"})

    return roster


def _fit_and_score(estimator, grid, X, y, folds, seed):
    cv = KFold(n_splits=folds, shuffle=True, random_state=int(seed))
    gs = GridSearchCV(estimator, grid, cv=cv, n_jobs=1, error_score=np.nan,
                      scoring=["r2", "neg_root_mean_squared_error"], refit="r2")
    gs.fit(X, y)
    idx = gs.best_index_
    cv_r2 = float(gs.cv_results_["mean_test_r2"][idx])
    cv_rmse = float(-gs.cv_results_["mean_test_neg_root_mean_squared_error"][idx])
    return gs.best_estimator_, gs.best_params_, cv_r2, cv_rmse


# ─────────────────────────────────────────────────────────────────────────────
# Candidate grid — the shared, bounded argmax surface every model's
# predicted_best_params is read off (dense-but-bounded, built from the SAMPLED
# value ranges: numerics snapped to step + clamped to hard_min/hard_max,
# categoricals restricted to observed values).
# ─────────────────────────────────────────────────────────────────────────────
def _build_candidate_grid(points, pkeys, dp):
    axes = {}
    for k in pkeys:
        meta = dp.get(k) or {}
        typ = meta.get("type", "float")
        seen = sorted({p.get(k) for p in points if p.get(k) is not None}, key=str)
        if not seen:
            continue
        if typ in ("int", "float"):
            numeric_seen = sorted(float(v) for v in seen)
            lo, hi = numeric_seen[0], numeric_seen[-1]
            hard_min, hard_max = meta.get("hard_min"), meta.get("hard_max")
            if hard_min is not None:
                lo = max(lo, float(hard_min))
            if hard_max is not None:
                hi = min(hi, float(hard_max))
            if hi < lo:
                lo, hi = hi, lo
            step = float(meta.get("step") or 0)
            if step > 0:
                nsteps = max(1, int(round((hi - lo) / step)))
                cand = [lo + i * step for i in range(nsteps + 1)]
            else:
                cand = list(np.linspace(lo, hi, 12)) if hi > lo else [lo]
            if typ == "int":
                cand = sorted({int(round(c)) for c in cand})
            else:
                cand = sorted({round(float(c), 6) for c in cand})
        else:
            cand = seen
        axes[k] = cand

    ordered = [k for k in pkeys if k in axes]
    n_params = max(1, len(ordered))
    per_param_cap = max(2, int(round(MAX_CANDIDATES ** (1.0 / n_params))))
    for k in ordered:
        vals = axes[k]
        if len(vals) > per_param_cap:
            idx = sorted({int(round(i)) for i in np.linspace(0, len(vals) - 1, per_param_cap)})
            axes[k] = [vals[i] for i in idx]

    combos = itertools.islice(itertools.product(*(axes[k] for k in ordered)), MAX_CANDIDATES)
    rows = [dict(zip(ordered, c)) for c in combos]
    return rows


# ─────────────────────────────────────────────────────────────────────────────
# Interactions — lightweight Friedman-H-style statistic: compare the 2-D PD
# surface against the sum of the two 1-D PDs; normalized residual variance in
# [0,1] = interaction strength. Grid-based (not data-density-weighted) — a
# documented approximation, cheap enough to run per pair per model.
# ─────────────────────────────────────────────────────────────────────────────
def _interaction_axis(param, points, n=INTERACTION_GRID_N):
    seen = []
    seenset = set()
    for p in points:
        v = p.get(param)
        if v is None or v in seenset:
            continue
        seenset.add(v)
        seen.append(v)
    seen.sort()
    if len(seen) <= n:
        return seen
    idx = sorted({int(round(i)) for i in np.linspace(0, len(seen) - 1, n)})
    return [seen[i] for i in idx]


def _pd_surfaces(estimator, enc, points, a, b, seed):
    """Batched 2-D + two 1-D partial-dependence estimates for param pair (a,b):
    for every (av, bv) grid cell, average the model's prediction over a fixed
    deterministic background sample of real sampled rows with a/b overridden —
    the standard PDP marginal-average construction, just vectorized into three
    single `predict` calls (2-D grid, PD_a, PD_b) instead of one call per cell."""
    n = len(points)
    bg_n = min(INTERACTION_BG_N, n)
    rng = np.random.RandomState(seed)
    bg_idx = sorted(rng.choice(n, size=bg_n, replace=False).tolist())
    bg_rows = [points[i] for i in bg_idx]
    a_vals = _interaction_axis(a, points)
    b_vals = _interaction_axis(b, points)
    if len(a_vals) < 2 or len(b_vals) < 2:
        return None
    na, nb = len(a_vals), len(b_vals)

    rows2d = [dict(br, **{a: av, b: bv}) for av in a_vals for bv in b_vals for br in bg_rows]
    pred2d = np.asarray(estimator.predict(enc.transform(rows2d)), dtype=float)
    pd2d = pred2d.reshape(na, nb, bg_n).mean(axis=2)

    rows_a = [dict(br, **{a: av}) for av in a_vals for br in bg_rows]
    pd_a = np.asarray(estimator.predict(enc.transform(rows_a)), dtype=float).reshape(na, bg_n).mean(axis=1)

    rows_b = [dict(br, **{b: bv}) for bv in b_vals for br in bg_rows]
    pd_b = np.asarray(estimator.predict(enc.transform(rows_b)), dtype=float).reshape(nb, bg_n).mean(axis=1)

    return pd2d, pd_a, pd_b, a_vals, b_vals


def _pair_strength(pd2d, pd_a, pd_b):
    grand_mean = float(pd2d.mean())
    na, nb = pd2d.shape
    additive = pd_a.reshape(na, 1) + pd_b.reshape(1, nb) - grand_mean
    resid = pd2d - additive
    ss_resid = float(np.sum(resid ** 2))
    ss_total = float(np.sum((pd2d - grand_mean) ** 2))
    if ss_total <= 1e-12:
        return 0.0
    return float(min(1.0, max(0.0, ss_resid / ss_total)))


def _all_pair_strengths(estimator, numeric_params, points, enc, seed):
    """Every numeric-param pair's interaction strength, strongest first
    (stable-sorted, so ties keep the deterministic `numeric_params` order)."""
    out = []
    for a, b in itertools.combinations(sorted(numeric_params), 2):
        r = _pd_surfaces(estimator, enc, points, a, b, seed)
        if r is None:
            continue
        pd2d, pd_a, pd_b, a_vals, b_vals = r
        s = _pair_strength(pd2d, pd_a, pd_b)
        out.append((a, b, s, a_vals, b_vals, pd2d))
    out.sort(key=lambda t: t[2], reverse=True)
    return out


def _pair_card(a, b, s, a_vals, b_vals, pd2d, with_grid):
    card = {"param_a": a, "param_b": b, "strength": round(s, 3)}
    if with_grid:
        # Firestore rejects nested arrays-of-arrays (see analytics.pdp_plateau's
        # curves convention) -- one dict per a-row, each carrying a FLAT "row"
        # array across b_values, instead of a literal list-of-lists.
        card["a_values"] = [_native(v) for v in a_vals]
        card["b_values"] = [_native(v) for v in b_vals]
        card["pd_grid"] = [{"a": _native(av), "row": [round(float(x), 1) for x in pd2d[i]]}
                           for i, av in enumerate(a_vals)]
    return card


# ─────────────────────────────────────────────────────────────────────────────
# Knob screen — LASSO (linear-dead check) + SHAP/impurity (nonlinear check)
# NOTE: full Boruta-SHAP (shadow features, iterative significance testing) is
# deliberately deferred -- overkill at the 5-9 knobs these strategies expose;
# upgrade path is to swap the SHAP block below for a boruta_shap.BorutaShap
# run if a strategy ever grows enough knobs to need it.
# ─────────────────────────────────────────────────────────────────────────────
def _knob_screen(X, y, enc, pkeys, folds, seed):
    groups = enc.group_columns()

    lasso_mag = {k: None for k in pkeys}
    try:
        Xs = StandardScaler().fit_transform(X)
        cv = KFold(n_splits=folds, shuffle=True, random_state=int(seed))
        lcv = LassoCV(cv=cv, random_state=int(seed), n_jobs=1, max_iter=20000).fit(Xs, y)
        coef = lcv.coef_
        for k in pkeys:
            cols = groups.get(k)
            if cols:
                lasso_mag[k] = float(np.sqrt(np.sum(coef[cols] ** 2)))
    except Exception:
        pass

    return lasso_mag, groups


def _tree_importance_screen(pkeys, groups, tree_est, tree_name, X):
    """mean|SHAP| per knob from a fitted tree model; falls back to the RF's own
    impurity importances (labeled as such) if shap is missing or errors."""
    shap_mag = {k: None for k in pkeys}
    source = None
    if tree_est is None:
        return shap_mag, source
    if HAS_SHAP:
        try:
            explainer = _shap.TreeExplainer(tree_est)
            sv = np.asarray(explainer.shap_values(X), dtype=float)
            if sv.ndim == 3:            # some shap/xgboost combos add a trailing output-dim
                sv = sv[:, :, 0]
            mean_abs = np.mean(np.abs(sv), axis=0)
            for k in pkeys:
                cols = groups.get(k)
                if cols:
                    shap_mag[k] = float(np.sum(mean_abs[cols]))
            source = f"shap:{tree_name}"
            return shap_mag, source
        except Exception:
            pass
    try:
        imp = np.asarray(tree_est.feature_importances_, dtype=float)
        for k in pkeys:
            cols = groups.get(k)
            if cols:
                shap_mag[k] = float(np.sum(imp[cols]))
        source = f"rf_importance:{tree_name}"
    except Exception:
        source = None
    return shap_mag, source


def _verdict(lasso_mag, shap_mag):
    vals_l = [v for v in lasso_mag.values() if v is not None]
    vals_s = [v for v in shap_mag.values() if v is not None]
    max_l = max(vals_l) if vals_l else 0.0
    max_s = max(vals_s) if vals_s else 0.0
    out = {}
    for k in lasso_mag:
        lm, sm = lasso_mag.get(k), shap_mag.get(k)
        norm_l = (lm / max_l) if (lm is not None and max_l > 0) else (0.0 if lm is not None else None)
        norm_s = (sm / max_s) if (sm is not None and max_s > 0) else (0.0 if sm is not None else None)
        combined = max([v for v in (norm_l, norm_s) if v is not None] or [0.0])
        if lm is not None and lm < DEAD_LASSO_EPS:
            verdict = "dead"
        elif combined < WEAK_NORM_THRESH:
            verdict = "weak"
        else:
            verdict = "drives PnL"
        out[k] = verdict
    return out


def _consensus(fit_cards, enc, dp):
    proposals = [c["predicted_best_params"] for c in fit_cards if c.get("predicted_best_params")]
    if len(proposals) < 2:
        return {"agree": True, "note": "fewer than two models fit -- nothing to compare yet.",
                "mismatched_params": []}
    mismatches = []
    for k in enc.numeric_params:
        meta = dp.get(k) or {}
        step = float(meta.get("step") or 0)
        lo, hi = meta.get("min"), meta.get("max")
        span = (float(hi) - float(lo)) if (hi is not None and lo is not None and float(hi) > float(lo)) else 0.0
        tol = max(step, 0.10 * span, 1e-9)
        vals = [float(p[k]) for p in proposals if p.get(k) is not None]
        if vals and (max(vals) - min(vals)) > tol:
            mismatches.append(k)
    for k in enc.cat_params:
        vals = {p.get(k) for p in proposals if k in p}
        if len(vals) > 1:
            mismatches.append(k)
    agree = not mismatches
    if agree:
        note = ("every fitted model's predicted optimum lands in the same region -- "
                "higher confidence in the joint surface.")
    else:
        note = ("models disagree on " + ", ".join(mismatches) + " -- the surface is likely "
                "noisy or under-sampled there; widen sampling before trusting any single "
                "model's pick.")
    return {"agree": agree, "note": note, "mismatched_params": mismatches}


def surrogate_bakeoff(points, pkeys, dp, ground_truth_fn=None, top_pairs=3, seed=42, cv_folds=5):
    """Fit the bake-off (§3) to already-sampled `points`, read the joint surface
    off the best model (§4), and (if `ground_truth_fn` given) ground-truth every
    model's proposed optimum with a real backtest (§2 step 6). NO steering (P2) —
    `points` is exactly what run_auto's random sampler already produced.

    points : [{param: value, ..., pnl: float[, dd: float]}, ...] — same shape run_auto
             builds for pdp_plateau (`_pts_full`).
    pkeys  : ordered param-name list (run_auto's own `pkeys` — the tunable knobs).
    dp     : the strategy's DEFAULT_PARAMS dict (types, min/max/step, hard_min/hard_max,
             depends_on).
    ground_truth_fn : optional callable(params_dict) -> metrics_dict|None, a real
             backtest evaluator over the SAME (caller's) IS window. Only called for
             each model's predicted_best_params, deduped by identical proposal.
    top_pairs : how many interaction pairs (with full 2-D PD grids) to return for
             the BEST model; every other fitted model gets its top-1 pair only.
    seed / cv_folds : as documented at the top of this module.

    Returns None when there isn't enough signal to say anything honest (<MIN_POINTS
    points or <MIN_VARYING_PARAMS varying knobs) -- this is the ONLY documented
    None case. Any other internal fit failure degrades to a per-model "skipped"
    card rather than raising; a genuinely unexpected exception is left to
    propagate to the caller's own try/except (auto.py's integration owns the
    "never kill a run" contract at the call site, per the design doc).
    """
    pts = [p for p in (points or []) if isinstance(p, dict) and "pnl" in p]
    if len(pts) < MIN_POINTS:
        return None
    vary = [k for k in pkeys if len({str(p.get(k)) for p in pts}) > 1]
    if len(vary) < MIN_VARYING_PARAMS:
        return None

    enc = _Encoder(pkeys, dp, pts)
    X = enc.transform(pts)
    y = np.array([float(p.get("pnl", 0) or 0) for p in pts], dtype=float)
    n = len(pts)
    folds = max(2, min(int(cv_folds), n // 8))
    y_mean, y_std = float(y.mean()), float(y.std() or 1.0)

    # GP tractability cap (§3: O(n^3), fine at <=~1000) -- deterministic subsample.
    gp_pts, gp_X, gp_y, gp_note = pts, X, y, None
    if n > GP_MAX_POINTS:
        rng = np.random.RandomState(seed)
        idx = sorted(rng.choice(n, size=GP_MAX_POINTS, replace=False).tolist())
        gp_pts = [pts[i] for i in idx]
        gp_X, gp_y = X[idx], y[idx]
        gp_note = f"subsampled {GP_MAX_POINTS}/{n} points (seed {seed}) for O(n^3) tractability."

    roster = _build_roster(seed, y_mean, y_std)
    cards = []
    fitted = {}
    fit_points = {}       # model name -> the (possibly GP-subsampled) points/X it was fit on
    for spec in roster:
        name = spec["name"]
        if spec.get("skipped"):
            cards.append({"model": name, "skipped": spec["skipped"]})
            continue
        use_X, use_y, use_pts = (gp_X, gp_y, gp_pts) if name == "gp" else (X, y, pts)
        try:
            est, best_params, cv_r2, cv_rmse = _fit_and_score(
                spec["estimator"], spec["grid"], use_X, use_y, folds, seed)
        except Exception as e:
            cards.append({"model": name, "skipped": f"fit failed: {e}"})
            continue
        fitted[name] = est
        fit_points[name] = use_pts
        card = {"model": name, "cv_r2": round(cv_r2, 3), "cv_rmse": round(cv_rmse, 1),
               "best_hyperparams": _json_safe_hyperparams(best_params), "_kind": spec["kind"]}
        if name == "gp" and gp_note:
            card["gp_subsample_note"] = gp_note
        cards.append(card)

    fit_cards = [c for c in cards if "_kind" in c]
    if not fit_cards:
        return None

    best_card = max(fit_cards, key=lambda c: c["cv_r2"])
    best_name = best_card["model"]

    # ── predicted_best_params / predicted_best_pnl (shared candidate grid) ──
    cand_rows = _build_candidate_grid(pts, pkeys, dp)
    cand_rows = [_collapse_conditional(r, dp) for r in cand_rows]
    seen_sig = {}
    dedup_rows = []
    for r in cand_rows:
        sig = tuple(sorted(r.items(), key=lambda kv: kv[0]))
        if sig not in seen_sig:
            seen_sig[sig] = len(dedup_rows)
            dedup_rows.append(r)
    Xc = enc.transform(dedup_rows)

    for card in fit_cards:
        est = fitted[card["model"]]
        preds = np.asarray(est.predict(Xc), dtype=float)
        bi = int(np.argmax(preds))
        card["predicted_best_params"] = _json_safe_row(dedup_rows[bi], pkeys, dp)
        card["predicted_best_pnl"] = round(float(preds[bi]), 1)
        card["ground_truth_pnl"] = None
        card["uncertainty_note"] = None
        card["_best_row_idx"] = bi

    if "gp" in fitted:
        gp_card = next(c for c in fit_cards if c["model"] == "gp")
        gp_est = fitted["gp"]
        bi = gp_card["_best_row_idx"]
        _, sd_best = gp_est.predict(Xc[bi:bi + 1], return_std=True)
        _, sd_train = gp_est.predict(gp_X, return_std=True)
        sd_typical = float(np.median(sd_train))
        sd_best0 = float(sd_best[0])
        high = sd_best0 > GP_HIGH_UNCERTAINTY_MULT * sd_typical
        gp_card["uncertainty_note"] = (
            f"predictive std at its optimum = {round(sd_best0, 1)} vs typical in-sample "
            f"std = {round(sd_typical, 1)} -- "
            + ("HIGH uncertainty here; trust the ground-truth run over this prediction."
               if high else "in line with the sampled surface; reasonably confident."))

    for card in fit_cards:
        card.pop("_best_row_idx", None)

    # ── interactions (best model: full top_pairs w/ PD grids; others: top-1) ──
    varying_numeric = [k for k in enc.numeric_params if len({p.get(k) for p in pts}) > 1]
    if len(varying_numeric) >= 2:
        for card in fit_cards:
            est = fitted[card["model"]]
            use_pts = fit_points[card["model"]]
            ranked = _all_pair_strengths(est, varying_numeric, use_pts, enc, seed)
            if card["model"] == best_name:
                card["top_interactions"] = [_pair_card(a, b, s, av, bv, pd2d, with_grid=True)
                                            for (a, b, s, av, bv, pd2d) in ranked[:max(0, int(top_pairs))]]
            elif ranked:
                a, b, s, av, bv, pd2d = ranked[0]
                card["top_interactions"] = [_pair_card(a, b, s, av, bv, pd2d, with_grid=False)]
            else:
                card["top_interactions"] = []
    else:
        for card in fit_cards:
            card["top_interactions"] = []

    # ── knob screen (LASSO + SHAP/impurity) ─────────────────────────────────
    lasso_mag, groups = _knob_screen(X, y, enc, pkeys, folds, seed)
    tree_name = best_name if best_name in ("random_forest", "xgboost") else (
        "random_forest" if "random_forest" in fitted else None)
    tree_est = fitted.get(tree_name) if tree_name else None
    shap_mag, shap_source = _tree_importance_screen(pkeys, groups, tree_est, tree_name, X)
    verdicts = _verdict(lasso_mag, shap_mag)
    knob_screen = {
        k: {"lasso": (round(lasso_mag[k], 4) if lasso_mag[k] is not None else None),
            "shap_or_imp": (round(shap_mag[k], 4) if shap_mag[k] is not None else None),
            "shap_source": shap_source, "verdict": verdicts[k]}
        for k in pkeys
    }

    consensus = _consensus(fit_cards, enc, dp)
    sampled_best_pnl = round(float(y.max()), 1)

    # ── ground truth (§2 step 6): run each proposal, dedupe identical ones ──
    if ground_truth_fn is not None:
        cache = {}
        for card in fit_cards:
            pp = card.get("predicted_best_params")
            if not pp:
                continue
            sig = tuple(sorted(pp.items()))
            if sig not in cache:
                try:
                    m = ground_truth_fn(dict(pp))
                except Exception:
                    m = None
                cache[sig] = float(m["total_pnl"]) if (m and "total_pnl" in m) else None
            gt = cache[sig]
            card["ground_truth_pnl"] = round(gt, 1) if gt is not None else None
            card["beat_sampled_best"] = bool(gt is not None and gt > sampled_best_pnl)

    for c in cards:
        c.pop("_kind", None)

    return {"n_points": n, "cv_folds": folds, "seed": int(seed),
           "sampled_best_pnl": sampled_best_pnl, "best_model": best_name,
           "models": cards, "consensus": consensus, "knob_screen": knob_screen}
