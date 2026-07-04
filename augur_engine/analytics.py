"""Research analytics (streamlit-free) — Phase 4 of the EDGELOG port.

Faithful ports of the optimizer's Monte-Carlo drawdown and Deflated-Sharpe panels:
  • monte_carlo_drawdown — block-shuffle the trade order N times, report the drawdown
    distribution (p50..p99). "Size to p95" is the practical risk number.
  • deflated_sharpe — Bailey/Lopez de Prado: haircut the winner's Sharpe by the best
    Sharpe expected from pure luck across N searched configs (PSR vs that luck bar).
Both are seeded (rng=42) → reproducible, matching the app.
"""
import math

import numpy as np
from scipy import stats as _sst

_GAMMA = 0.5772156649   # Euler-Mascheroni


def downsample_pnls(pnls, cap=400):
    """Sorted (desc) list of config PnLs, downsampled to <=cap — feeds the web's
    PnL-distribution / plateau-vs-isolated-spike panel."""
    out = sorted((float(x or 0) for x in pnls), reverse=True)
    if len(out) > cap:
        step = len(out) / cap
        out = [out[int(i * step)] for i in range(cap)]
    return [round(x, 1) for x in out]


def mae_mfe(trades, highs, lows, cap=600):
    """Per-trade Maximum Adverse / Favorable Excursion (in points) from rich trades
    (entry_idx, exit_idx, pnl, side, entry_px); side = +1 long / -1 short. MAE = worst
    move against the trade, MFE = best move in favour, while open. Returns
    {mae:[...], mfe:[...], won:[...]} or None if trades lack side/entry_px (legacy 3-tuples)."""
    n = len(highs)
    mae, mfe, won = [], [], []
    for t in trades:
        if not isinstance(t, (list, tuple)) or len(t) < 5:
            return None
        ei, xi, pnl, side, epx = t[0], t[1], t[2], t[3], t[4]
        a = max(0, int(min(ei, xi))); b = min(n - 1, int(max(ei, xi)))
        if b < a:
            continue
        hi = float(np.max(highs[a:b + 1])); lo = float(np.min(lows[a:b + 1]))
        if side >= 0:                       # long: adverse = down, favourable = up
            mae.append(round(lo - epx, 2)); mfe.append(round(hi - epx, 2))
        else:                               # short: adverse = up, favourable = down
            mae.append(round(epx - hi, 2)); mfe.append(round(epx - lo, 2))
        won.append(1 if pnl > 0 else 0)
    if not mae:
        return None
    if len(mae) > cap:
        step = len(mae) / cap
        idx = [int(i * step) for i in range(cap)]
        mae = [mae[i] for i in idx]; mfe = [mfe[i] for i in idx]; won = [won[i] for i in idx]
    return {"mae": mae, "mfe": mfe, "won": won}


def downsample_points(points, cap=400):
    """Stride-sample a list of per-config {param:..., pnl} dicts to <=cap — feeds the
    web's scatter (param vs PnL) and heatmap (param X×Y → PnL) panels."""
    if len(points) > cap:
        step = len(points) / cap
        return [points[int(i * step)] for i in range(cap)]
    return list(points)


def annualized_sr(pnls, years):
    """{sr, n, tpy, skew, kurt} annualized Sharpe of a per-trade PnL series (None if
    too few trades / zero variance). Same formula as optimizer._ann_sr."""
    p = np.asarray(pnls, float)
    if len(p) < 3:
        return None
    sd = p.std(ddof=1)
    if sd <= 0:
        return None
    tpy = len(p) / years
    sr = (p.mean() / sd) * np.sqrt(tpy)
    z = (p - p.mean()) / sd
    return dict(sr=float(sr), n=int(len(p)), tpy=float(tpy),
                skew=float((z ** 3).mean()), kurt=float((z ** 4).mean()))


def _max_dd(arr):
    cum = np.cumsum(arr)
    peak = np.maximum.accumulate(cum)
    return float((cum - peak).min())


def monte_carlo_drawdown(pnls, n_sims=1000, block=1, seed=42):
    """Block-shuffle the trade PnL series n_sims times; return the drawdown
    distribution (same units as pnls). p95 = "size your account to survive this"."""
    arr = np.asarray(pnls, float)
    n = len(arr)
    if n < 2:
        return None
    dd_obs = _max_dd(arr)
    rng = np.random.default_rng(seed)
    bs = max(1, int(block))
    nblk = math.ceil(n / bs)
    blocks = [arr[i * bs:(i + 1) * bs] for i in range(nblk)]
    dds = np.empty(int(n_sims))
    for s in range(int(n_sims)):
        order = rng.permutation(nblk)
        dds[s] = _max_dd(np.concatenate([blocks[b] for b in order]))
    pct = {p: float(np.percentile(dds, 100 - p)) for p in (50, 75, 90, 95, 99)}
    return dict(as_traded=dd_obs, p50=pct[50], p75=pct[75], p90=pct[90],
                p95=pct[95], p99=pct[99],
                pct_worse=float((dds < dd_obs).mean() * 100),
                n_sims=int(n_sims), block=bs)


def deflated_sharpe(winner, sample_srs, n_cfg, years):
    """Deflated Sharpe of the grid winner vs the best-of-N luck bar.
    winner: an annualized_sr() dict; sample_srs: annualized SRs across sampled configs;
    n_cfg: total configs searched. Returns {winner_sharpe, luck_bar, dsr, verdict}."""
    srs = [s for s in sample_srs if s is not None]
    if winner is None or len(srs) < 8:
        return None
    vsr = float(np.var(srs, ddof=1))
    sr0 = (math.sqrt(vsr) * ((1 - _GAMMA) * _sst.norm.ppf(1 - 1.0 / n_cfg)
                             + _GAMMA * _sst.norm.ppf(1 - 1.0 / (n_cfg * math.e))))
    sr, T = winner["sr"], winner["n"]
    tpy = T / years
    sr_t, sr0_t = sr / math.sqrt(tpy), sr0 / math.sqrt(tpy)      # per-trade units
    den = math.sqrt(max(1e-9, 1 - winner["skew"] * sr_t
                        + ((winner["kurt"] - 1) / 4.0) * sr_t ** 2))
    dsr = float(_sst.norm.cdf(((sr_t - sr0_t) * math.sqrt(T - 1)) / den))
    return dict(winner_sharpe=float(sr), luck_bar=float(sr0), dsr=dsr, n_cfg=int(n_cfg),
                verdict=("beats the luck bar" if dsr >= 0.95
                         else "uncertain — may not beat luck" if dsr >= 0.80
                         else "does NOT beat the luck bar"))


def _bucket(usd_by_group, order):
    """One regime table: [{bucket,n,pnl,pf,avg}] in `order`, pnl/avg in trade units."""
    out = []
    for b in order:
        v = usd_by_group.get(b)
        if v is None or len(v) == 0:
            continue
        v = np.asarray(v, float)
        gw = float(v[v > 0].sum()); gl = float(-v[v < 0].sum())
        pf = (gw / gl) if gl > 0 else (float("inf") if gw > 0 else 0.0)
        out.append({"bucket": b, "n": int(len(v)), "pnl": float(v.sum()),
                    "pf": (99.0 if pf == float("inf") else round(pf, 2)),
                    "avg": float(v.mean())})
    return out


def regime_report(trades, index, highs, lows, closes, cost_pts=0.0):
    """REGIME REPORT CARD (TODO #13): slice a config's trades by the market regime
    on each ENTRY day — volatility tercile (rolling-20 ATR), trend-vs-chop (efficiency
    ratio), day-of-week — plus a monthly PnL grid. PnL is in POINTS (net of cost_pts);
    the caller multiplies by the contract multiplier. Faithful port of the app's
    _render_regime_panel. Returns None if there isn't enough warm-up history.
    """
    import pandas as pd
    if not trades:
        return None
    eix = pd.to_datetime(pd.Series(index))
    dts = eix.dt.date.values
    H, L, C = np.asarray(highs, float), np.asarray(lows, float), np.asarray(closes, float)
    day = pd.DataFrame({"d": dts, "h": H, "l": L, "c": C}).groupby("d").agg(
        hi=("h", "max"), lo=("l", "min"), cl=("c", "last"))
    day["pc"] = day["cl"].shift(1)
    tr = np.maximum(day["hi"] - day["lo"],
                    np.maximum((day["hi"] - day["pc"]).abs(),
                               (day["lo"] - day["pc"]).abs()))
    day["atr20"] = tr.rolling(20).mean()
    dmv = day["cl"].diff()
    day["er20"] = (day["cl"].diff(20).abs() / dmv.abs().rolling(20).sum()).clip(0, 1)
    q1, q2 = day["atr20"].quantile([1 / 3, 2 / 3])
    erm = float(day["er20"].median())

    vol_g, trend_g, dow_g = {}, {}, {}
    monthly = {}   # (year, month) -> sum pnl
    n_used = 0
    for t in trades:   # trades may be 3- or 5-tuples (entry_i, exit_i, pnl[, side, entry_px])
        eb, xb, pnl = t[0], t[1], t[2]
        if eb < 0 or eb >= len(dts):
            continue
        d = dts[eb]
        if d not in day.index:
            continue
        drow = day.loc[d]
        if pd.isna(drow["atr20"]):
            continue
        usd = float(pnl) - cost_pts
        vb = "Low vol" if drow["atr20"] <= q1 else "High vol" if drow["atr20"] > q2 else "Mid vol"
        tb = "Trend" if drow["er20"] > erm else "Chop"
        ts = eix.iloc[eb]
        db = ts.strftime("%a")
        vol_g.setdefault(vb, []).append(usd)
        trend_g.setdefault(tb, []).append(usd)
        dow_g.setdefault(db, []).append(usd)
        monthly[(ts.year, ts.month)] = monthly.get((ts.year, ts.month), 0.0) + usd
        n_used += 1
    if n_used == 0:
        return None

    years = sorted({y for (y, m) in monthly})
    mrows = [{"year": y, "months": [round(monthly.get((y, m), 0.0), 1) if (y, m) in monthly
                                    else None for m in range(1, 13)]} for y in years]
    vol_t = _bucket(vol_g, ["Low vol", "Mid vol", "High vol"])
    worst = min(vol_t, key=lambda r: r["pnl"])["bucket"] if vol_t else None
    return {"vol": vol_t,
            "trend": _bucket(trend_g, ["Trend", "Chop"]),
            "dow": _bucket(dow_g, ["Mon", "Tue", "Wed", "Thu", "Fri"]),
            "monthly": {"years": years, "rows": mrows},
            "n_trades": int(n_used), "worst_vol": worst}


def neighborhood(evalfn, best_params, value_options):
    """NEIGHBORHOOD ROBUSTNESS (TODO #12): for each numeric param, re-run the winner
    with that one param shifted to its ±1-step grid value and record the neighbor's
    profit factor. A real optimum sits on high ground (profitable neighbors); a winner
    whose neighbor falls off a cliff is curve-fit luck.

    evalfn(params)->metrics ; value_options={param: sorted candidate values}.
    Returns {verdict, good, tot, rows:[{param, minus, winner, plus}]} (each cell
    {val, pf} or None at a grid edge).
    """
    rows, good, tot = [], 0, 0
    wpf = None
    try:
        wm = evalfn(dict(best_params))
        wpf = float(wm.get("profit_factor", 0) or 0) if wm else 0.0
    except Exception:
        wpf = 0.0
    for p, vals in value_options.items():
        vals = sorted(v for v in vals if v is not None)
        bv = best_params.get(p)
        if len(vals) < 2 or bv not in vals:
            continue
        ix = vals.index(bv)
        cells = {}
        for off, key in ((-1, "minus"), (1, "plus")):
            j = ix + off
            if 0 <= j < len(vals):
                try:
                    m = evalfn({**best_params, p: vals[j]})
                except Exception:
                    m = None
                if m:
                    pf = float(m.get("profit_factor", 0) or 0)
                    tot += 1
                    if pf > 1.0:
                        good += 1
                    cells[key] = {"val": vals[j], "pf": round(min(pf, 99), 2)}
                else:
                    cells[key] = None
            else:
                cells[key] = None
        rows.append({"param": p, "minus": cells.get("minus"),
                     "winner": {"val": bv, "pf": round(min(wpf, 99), 2)},
                     "plus": cells.get("plus")})
    if not rows:
        return None
    ok = (good >= tot * 0.7) if tot else False
    return {"verdict": ("HIGH GROUND" if ok else "CHECK NEIGHBORS"),
            "good": int(good), "tot": int(tot), "rows": rows}


def relationship_scores(points, target="pnl", max_rows=4000):
    """RELATIONSHIP SCORING (ROADMAP #24): per-parameter relationship to PnL across the
    searched configs, three measures of increasing power:
      • Pearson r            — linear correlation only,
      • Mutual Information    — ANY dependency, linear or not (sklearn's
        mutual_info_regression, which uses the Kraskov-Stogbauer-Grassberger k-NN estimator),
      • PPS-style score       — a depth-4 decision tree's cross-validated MAE vs the naive
        median baseline (1 - MAE_model/MAE_naive, clipped to 0..1) — catches non-linear
        predictive power (inverted-U / threshold relationships Pearson misses).
    `points` = [{param:val, ..., target:val}, ...] (the same shape synced for the scatter).
    Returns [{param, r, mi, pps}, ...] sorted by pps -> mi -> |r|, or None when there isn't
    enough numeric variation / rows. Never raises — an unavailable piece comes back as None.
    """
    try:
        pts = [p for p in (points or []) if isinstance(p, dict) and target in p]
        if len(pts) < 30:
            return None
        if len(pts) > max_rows:                      # cap for speed; stride-sample
            step = len(pts) / max_rows
            pts = [pts[int(i * step)] for i in range(max_rows)]
        cols = {}
        for k in pts[0].keys():
            if k == target:
                continue
            v0 = pts[0][k]
            if isinstance(v0, bool) or not isinstance(v0, (int, float)):
                continue                             # numeric params only
            try:
                col = [float(p[k]) for p in pts]
            except (KeyError, TypeError, ValueError):
                continue
            if len(set(col)) > 1:                    # needs variation to score
                cols[k] = col
        if not cols:
            return None
        knames = list(cols.keys())
        X = np.column_stack([cols[k] for k in knames]).astype(float)
        y = np.asarray([float(p[target]) for p in pts], float)
        try:
            from sklearn.feature_selection import mutual_info_regression
            mi = mutual_info_regression(X, y, random_state=42)
        except Exception:
            mi = [None] * len(knames)
        tree = None
        try:
            from sklearn.tree import DecisionTreeRegressor
            from sklearn.model_selection import cross_val_score
            tree = DecisionTreeRegressor
            naive = float(np.mean(np.abs(y - np.median(y)))) or 1e-9
            cv = max(2, min(5, len(pts) // 10))
        except Exception:
            tree = None
        rows = []
        for i, k in enumerate(knames):
            xi = X[:, i]
            dx = xi - xi.mean(); dy = y - y.mean()
            den = float(np.sqrt((dx * dx).sum() * (dy * dy).sum()))
            r = float((dx * dy).sum() / den) if den else 0.0
            pps = None
            if tree is not None:
                try:
                    mae = -cross_val_score(tree(max_depth=4, random_state=42),
                                           xi.reshape(-1, 1), y, cv=cv,
                                           scoring="neg_mean_absolute_error").mean()
                    pps = max(0.0, 1.0 - mae / naive)
                except Exception:
                    pps = None
            rows.append({"param": k, "r": round(r, 3),
                         "mi": (round(float(mi[i]), 3) if (i < len(mi) and mi[i] is not None) else None),
                         "pps": (round(float(pps), 3) if pps is not None else None)})
        rows.sort(key=lambda d: ((d["pps"] or 0), (d["mi"] or 0), abs(d["r"])), reverse=True)
        return rows or None
    except Exception:
        return None


def pdp_plateau(points, pnl_key="pnl", min_points=12):
    """3C.1 — PDP-plateau winner pick (ROADMAP #24a; board 3C.1).

    GOAL: pick the config sitting on a broad, HIGH region of the param→PnL
    surface — a plateau — instead of the raw argmax spike, because a lone spike
    is usually luck while a plateau survives live drift.

    ENGINE (GAM-style, native — no pyGAM dependency): for each varying param,
    the partial-dependence curve = mean PnL of all evaluated configs grouped by
    that param's value, lightly kernel-smoothed (a GAM is exactly a sum of
    smooth per-param curves). Each config is then scored ADDITIVELY:
        score(c) = mean_pnl + Σ_k [ smoothed_curve_k(c[k]) − mean_pnl ]
    A spike scores low because its neighbours on every axis drag its curves
    down; a plateau member scores high because the whole ridge supports it.

    points : [{param: value, ..., pnl: float}, ...] — every VALID evaluated
             config (grid combos or auto samples). Returns None when the
             surface is too thin to say anything (< min_points or no varying
             numeric/categorical params).
    """
    if not points or len(points) < int(min_points):
        return None
    import numpy as np
    keys = [k for k in points[0] if k != pnl_key]
    vary = [k for k in keys if len({str(p.get(k)) for p in points}) > 1]
    if not vary:
        return None
    pnls = np.array([float(p.get(pnl_key, 0) or 0) for p in points])
    mu = float(pnls.mean())
    contrib = np.zeros(len(points))
    curves = {}
    for k in vary:
        groups = {}
        for p, y in zip(points, pnls):
            groups.setdefault(p.get(k), []).append(y)
        numeric = all(isinstance(v, (int, float)) and not isinstance(v, bool)
                      for v in groups)
        order = sorted(groups) if numeric else sorted(groups, key=str)
        means = np.array([float(np.mean(groups[v])) for v in order])
        sm = means.copy()
        if numeric and len(order) >= 3:            # 1-2-1 kernel + softened ends
            sm[1:-1] = 0.25 * means[:-2] + 0.5 * means[1:-1] + 0.25 * means[2:]
            sm[0] = 0.6 * means[0] + 0.4 * means[1]
            sm[-1] = 0.6 * means[-1] + 0.4 * means[-2]
        curve = {v: float(s) for v, s in zip(order, sm)}
        # list of dicts, NOT list of lists — Firestore rejects nested arrays
        curves[k] = [{"v": v, "mean": round(float(m), 1), "smooth": round(float(s), 1)}
                     for v, m, s in zip(order, means, sm)]
        contrib += np.array([curve[p.get(k)] - mu for p in points])
    score = mu + contrib
    i = int(np.argmax(score))
    return {"index": i,
            "params": {k: points[i][k] for k in keys},
            "score": round(float(score[i]), 1),
            "argmax_index": int(np.argmax(pnls)),
            "argmax_score": round(float(score[int(np.argmax(pnls))]), 1),
            "curves": curves}


def ensemble_blend(bar_pnls, buckets=50):
    """Equal-weight top-K ensemble (board §6 · Carl §7.1).

    `bar_pnls` = list of K aligned per-bar NET-PnL arrays (one per config, length =
    #bars). Allocating 1/K of capital to each config gives a portfolio whose per-bar
    PnL is the mean of the K series: its total PnL is the average of the K totals
    (so LOWER than the rank-1 config by construction), but its drawdown is usually
    SHALLOWER because the configs don't all dip at once — that's the whole point.
    The honest verdict is on RECOVERY (profit ÷ drawdown), not raw $.

    Returns the blend vs the single best (rank-1) config, the diversification
    (avg pairwise correlation of the configs on chronological buckets — lower = more
    diversified), and downsampled equity curves for the web. None if < 2 configs.
    """
    A = np.asarray(bar_pnls, float)
    if A.ndim != 2 or A.shape[0] < 2:
        return None
    k, nb = A.shape

    def _dscurve(inc, n=100):
        cum = np.cumsum(inc)
        if len(cum) > n:
            step = len(cum) / n
            cum = [cum[int(i * step)] for i in range(n)]
        return [round(float(x), 1) for x in cum]

    def _st(inc):
        cum = np.cumsum(inc)
        tot = float(cum[-1]); dd = _max_dd(inc)
        return {"total_pnl": round(tot, 1), "max_drawdown": round(dd, 1),
                "recovery": (round(tot / abs(dd), 2) if dd < -1e-9
                             else (999.0 if tot > 0 else 0.0))}

    ens_inc = A.mean(axis=0)                       # equal-weight portfolio
    blend, best = _st(ens_inc), _st(A[0])

    # diversification: correlate the configs on ~`buckets` chronological chunks
    # (per-bar PnL is too sparse — mostly zeros — to correlate directly).
    bsz = max(1, nb // int(buckets))
    B = np.array([A[:, i:i + bsz].sum(axis=1) for i in range(0, nb, bsz)]).T
    cors = []
    for i in range(k):
        for j in range(i + 1, k):
            a, b = B[i], B[j]
            if a.std() > 1e-9 and b.std() > 1e-9:
                cors.append(float(np.corrcoef(a, b)[0, 1]))
    avg_cor = round(float(np.mean(cors)), 3) if cors else None

    return {
        "k": int(k), "blend": blend, "best": best,
        "avg_corr": avg_cor,
        "recovery_gain": round(blend["recovery"] - best["recovery"], 2),
        "pnl_kept_pct": (round(100.0 * blend["total_pnl"] / best["total_pnl"], 1)
                         if best["total_pnl"] else None),
        "blend_curve": _dscurve(ens_inc), "best_curve": _dscurve(A[0]),
        "improved": bool(blend["recovery"] > best["recovery"]),
    }


def conformal_pnl_band(pnls, alpha=0.2, cal_frac=0.5, seed=42):
    """Split-conformal prediction interval for a single trade's NET PnL (board §4).

    Distribution-free: split the trades into calibration/test, build a symmetric
    interval around the calibration median whose half-width is the conformal quantile
    of |pnl − median|, then MEASURE the coverage on the untouched test split. The
    self-check is the point — a valid 80% band should actually cover ~80% of held-out
    trades. Units are POINTS (the web multiplies by the contract value)."""
    p = np.asarray([float(x) for x in pnls], float)
    n = len(p)
    if n < 60:
        return None
    rng = np.random.RandomState(int(seed))
    perm = rng.permutation(n)
    ncal = max(20, int(n * cal_frac))
    cal, test = p[perm[:ncal]], p[perm[ncal:]]
    med = float(np.median(cal))
    scores = np.abs(cal - med)
    lvl = min(1.0, np.ceil((ncal + 1) * (1 - alpha)) / ncal)
    q = float(np.quantile(scores, lvl, method="higher"))
    lo, hi = med - q, med + q
    cov = float(np.mean((test >= lo) & (test <= hi))) if len(test) else None
    return {"alpha": round(float(alpha), 2), "coverage_target": round(1 - float(alpha), 2),
            "coverage_measured": (round(cov, 3) if cov is not None else None),
            "lo": round(lo, 2), "hi": round(hi, 2), "median": round(med, 2),
            "half_width": round(q, 2), "n": int(n),
            "calibrated": bool(cov is not None and abs(cov - (1 - alpha)) <= 0.07)}


def causal_entry_test(trades, closes, cost_pts=0.0, n_sims=1000, seed=42):
    """Does the ENTRY RULE carry signal, or is the edge just market exposure? (board §7)

    Randomization test: keep each trade's direction (side) and holding length, but move
    every entry to a RANDOM bar; exit at the close that many bars later. Repeat n_sims
    times to build a null of 'same bets, random timing', then read where the real total
    sits. High percentile → entry timing has genuine predictive content. Needs 5-tuple
    trades (side at t[3]). CAVEAT: random trades exit at close, not the strategy's
    stop/target — so this isolates entry-timing/direction skill, not the exit logic."""
    C = np.asarray(closes, float)
    nb = len(C)
    T = [t for t in trades if len(t) >= 4]
    if len(T) < 30 or nb < 50:
        return None
    durs = np.array([max(1, int(t[1]) - int(t[0])) for t in T])
    sides = np.array([1.0 if float(t[3]) > 0 else -1.0 for t in T])
    m = len(T)
    maxd = int(durs.max())
    if nb - maxd - 1 <= 0:
        return None
    real = float(sum(float(t[2]) for t in T))           # NET (costs already in t[2])
    rng = np.random.RandomState(int(seed))
    nulls = np.empty(int(n_sims))
    for s in range(int(n_sims)):
        e = rng.randint(0, nb - maxd - 1, size=m)
        nulls[s] = float(np.sum(sides * (C[e + durs] - C[e]))) - m * float(cost_pts)
    pct = float((nulls < real).mean()) * 100.0
    return {"real_total_pts": round(real, 1),
            "null_median_pts": round(float(np.median(nulls)), 1),
            "null_p95_pts": round(float(np.percentile(nulls, 95)), 1),
            "percentile": round(pct, 1), "n_sims": int(n_sims), "n_trades": m,
            "verdict": ("entry timing carries real signal" if pct >= 95 else
                        ("modest signal" if pct >= 80 else
                         "weak / none — edge ≈ market exposure"))}


def synthetic_day_bootstrap(trades, index, n_sims=800, seed=42):
    """Alternate-history stress via a trading-DAY bootstrap (board §8).

    Group trades into trading days (by entry date), then resample whole days WITH
    REPLACEMENT to build n_sims synthetic histories of the same length. Unlike the
    Monte-Carlo pill (which reorders the exact realized trades), this changes the
    COMPOSITION of days — some days repeat, some drop — so it answers 'how would a
    different mix of market days have gone'. Reports the PnL spread + a bad-case
    drawdown + how often the run stays profitable. CAVEAT: treats days as exchangeable
    (ignores regime persistence across days). Points; web ×contract value."""
    import pandas as pd
    T = [t for t in trades if len(t) >= 3]
    if len(T) < 40 or index is None:
        return None
    ts = pd.DatetimeIndex(index)
    if ts.tz is not None:
        ts = ts.tz_localize(None)
    day_pnls = {}
    for t in T:
        d = ts[min(int(t[0]), len(ts) - 1)].date()
        day_pnls[d] = day_pnls.get(d, 0.0) + float(t[2])
    days = sorted(day_pnls)
    vals = np.array([day_pnls[d] for d in days], float)
    nd = len(vals)
    if nd < 30:
        return None
    rng = np.random.RandomState(int(seed))
    tot = np.empty(int(n_sims)); mdd = np.empty(int(n_sims))
    for s in range(int(n_sims)):
        seq = vals[rng.randint(0, nd, size=nd)]
        cum = np.cumsum(seq); peak = np.maximum.accumulate(cum)
        tot[s] = float(cum[-1]); mdd[s] = float((cum - peak).min())
    return {"n_days": int(nd), "n_sims": int(n_sims),
            "real_total_pts": round(float(vals.sum()), 1),
            "p05_total_pts": round(float(np.percentile(tot, 5)), 1),
            "p50_total_pts": round(float(np.percentile(tot, 50)), 1),
            "p95_total_pts": round(float(np.percentile(tot, 95)), 1),
            "worst5_maxdd_pts": round(float(np.percentile(mdd, 5)), 1),
            "prob_profit": round(float((tot > 0).mean()) * 100.0, 1)}
