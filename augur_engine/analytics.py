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
        curves[k] = [[v, round(float(m), 1), round(float(s), 1)]
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
