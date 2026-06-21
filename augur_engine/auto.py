"""Auto-Optimize + Walk-Forward (streamlit-free) — the smart-search scopes.

A faithful port of optimizer.py's `opt_mode == "auto"` path (the 🤖 AUTO-OPTIMIZE
and 🔁 Walk-Forward scopes), extracted so the EDGELOG web frontend + job runner can
drive them without importing the Streamlit app.

Two modes, same call:
  • method="single"      — seeded random/Bayesian search maximizing total PnL on the
                           first 75% of history, then RE-TEST every surviving config on
                           the held-out last 25% (out-of-sample). The headline is
                           realism-gated (enough wins AND losses, capped trade-rate/PF)
                           so a profit-factor mirage can't win.
  • method="walkforward" — anchored folds: each fold re-optimizes on all history up to
                           its test slice, crowns a champion by NET PnL (same realism
                           gate), and tests it on the next unseen slice. One row per
                           fold → param drift + per-fold OOS visible. Headline = the
                           LAST fold's champion (most recent re-optimize).

Determinism: seeded random sampler (seed=42), no optuna dependency, so results are
reproducible across machines — matching the app's _HAS_OPTUNA=False fallback path.
"""
import inspect
import random as _random

from .strategies import load_strategy, _resolve, strategy_params
from .data import find_master, load_master_arrays
from .engine import _apply_costs
from .analytics import (annualized_sr, deflated_sharpe, monte_carlo_drawdown,
                        regime_report, neighborhood, downsample_pnls, downsample_points)

# Realism gates — identical to optimizer.py (WF_MIN_SIDE / MAX_TRADE_RATE / MAX_PF).
# A champion/headline config must take at least this many WINNING and LOSING trades
# (not a one-sided fluke), trade no more often than MAX_TRADE_RATE per bar, and have
# a profit factor no higher than MAX_PF (above that = overfit / fill artifact).
WF_MIN_SIDE = 5
MAX_TRADE_RATE = 0.015
MAX_PF = 6.0
OOS_SPLIT = 0.75

_METRIC_KEYS = ("total_pnl", "num_trades", "win_rate", "profit_factor",
                "max_drawdown", "avg_pnl", "wins", "losses")


def _auto_space_from_params(default_params: dict) -> dict:
    """DEFAULT_PARAMS -> search space: name -> ('float'|'int', lo, hi, step) | ('cat', [..])."""
    space = {}
    for name, meta in (default_params or {}).items():
        if not isinstance(meta, dict):
            continue
        typ = meta.get("type", "float")
        if typ == "bool":
            space[name] = ("cat", [True, False])
        elif typ == "str":
            opts = meta.get("options") or [meta.get("default")]
            space[name] = ("cat", list(opts))
        elif typ == "int":
            space[name] = ("int", int(meta.get("min", 0)), int(meta.get("max", 10)),
                           int(meta.get("step", 1) or 1))
        else:
            space[name] = ("float", float(meta.get("min", 0.0)),
                           float(meta.get("max", 1.0)), float(meta.get("step", 0.0) or 0.0))
    return space


class _RandomSampler:
    """Seeded random search over the space (the app's optuna-absent fallback)."""

    def __init__(self, space, seed=42):
        self.space = space
        self._rng = _random.Random(seed)

    def ask(self):
        p = {}
        for name, spec in self.space.items():
            kind = spec[0]
            if kind == "cat":
                p[name] = self._rng.choice(spec[1])
            elif kind == "int":
                _, lo, hi, step = spec
                step = max(1, int(step))
                n = (hi - lo) // step
                p[name] = lo + step * self._rng.randint(0, max(0, n))
            else:
                _, lo, hi, step = spec
                if step and step > 0:
                    n = int(round((hi - lo) / step))
                    p[name] = round(lo + step * self._rng.randint(0, max(0, n)), 6)
                else:
                    p[name] = round(self._rng.uniform(lo, hi), 6)
        return p


def _collapse(p, default_params):
    """Reset inactive conditional params (depends_on unmet) to their default."""
    pe = dict(p)
    for k, meta in (default_params or {}).items():
        if not isinstance(meta, dict):
            continue
        cond = meta.get("depends_on")
        if cond and k in pe and not all(p.get(dk) == dv for dk, dv in cond.items()):
            pe[k] = meta.get("default")
    return pe


def _is_real(r, nbars):
    """The realism gate as a predicate over a metrics dict."""
    return (int(r.get("wins", 0) or 0) >= WF_MIN_SIDE
            and int(r.get("losses", 0) or 0) >= WF_MIN_SIDE
            and (int(r.get("num_trades", 0) or 0) / max(1, nbars)) <= MAX_TRADE_RATE
            and float(r.get("profit_factor", 0) or 0) <= MAX_PF)


def run_auto(strategy, *, instrument=None, timeframe="5m", session="rth", source=None,
             master=None, arrays=None, cost_pts=0.0, min_trades=30, n_trials=200,
             top_n=10, method="single", oos=True, wf_folds=0, seed=42,
             compute_dsr=False, mc_sims=0, progress_cb=None, years=None,
             compute_regime=False, compute_neighbors=False,
             date_from=None, date_to=None, wf_mode="anchored"):
    """Smart search. Returns the same shape as run_grid plus OOS columns.

    method="single" or "walkforward". Returns {mode,n_combos,n_valid,top[...],
    best_params,best,bars,master,(equity/mc/dsr)} where each top row carries
    oos_pnl/oos_trades/oos_pf (single) or fold/test_bars/oos_* (walkforward).
    """
    path = _resolve(strategy) if isinstance(strategy, str) else None
    mod = load_strategy(strategy) if isinstance(strategy, str) else strategy
    dp = getattr(mod, "DEFAULT_PARAMS", {}) or {}
    space = _auto_space_from_params(dp)
    if not space:
        raise ValueError("strategy exposes no tunable DEFAULT_PARAMS for auto search")
    pkeys = list(space.keys())

    if arrays is None:
        if master is None:
            master = find_master(instrument, timeframe, session, source)
            if master is None:
                raise ValueError(f"no master for {instrument} {timeframe} {session} {source}")
        arrays = load_master_arrays(master, date_from=date_from, date_to=date_to)
    O, H, L, C = arrays["open"], arrays["high"], arrays["low"], arrays["close"]
    V, did = arrays.get("volume"), arrays.get("day_id")

    fn = mod.run_backtest
    sp = inspect.signature(fn).parameters
    has_kw = any(p.kind == p.VAR_KEYWORD for p in sp.values())
    pass_vol = V is not None and (has_kw or "volumes" in sp)
    pass_day = did is not None and (has_kw or "day_id" in sp)

    def _ev(a, b, params):
        """Evaluate params on the [a:b) window, slicing extras consistently."""
        ex = {}
        if pass_vol:
            ex["volumes"] = V[a:b]
        if pass_day:
            ex["day_id"] = did[a:b]
        try:
            if cost_pts > 0:
                m = fn(O[a:b], H[a:b], L[a:b], C[a:b], return_trades=True, **ex, **params)
                if m:
                    m = _apply_costs(m, cost_pts)
                    m.pop("trades", None)
                return m
            return fn(O[a:b], H[a:b], L[a:b], C[a:b], **ex, **params)
        except Exception:
            return None

    n = len(C)
    oos_on = bool(oos) and n >= 200
    records = []   # each: {**params, **metrics, oos_*...}

    if method == "walkforward" and oos_on and n >= 4000:
        # ── Walk-forward: anchored (expanding IS from 0) or rolling (fixed-length
        #    IS window of `init` bars that slides forward — more regime-honest). ──
        rolling = str(wf_mode).lower() == "rolling"
        req = int(wf_folds or 0)
        n_folds = (max(2, min(8, req)) if req >= 2 else min(8, max(2, n // 3000)))
        init = int(n * 0.40)
        tsize = max(1, (n - init) // n_folds)
        n_total = n_trials * n_folds
        done = 0
        for f in range(n_folds):
            tr_end = init + f * tsize
            tr_start = max(0, tr_end - init) if rolling else 0
            te_s = tr_end
            te_e = n if f == n_folds - 1 else te_s + tsize
            samp = _RandomSampler(space, seed=seed)
            recs = []
            for _ in range(n_trials):
                pe = _collapse(samp.ask(), dp)
                m = _ev(tr_start, tr_end, pe)
                if m and m.get("num_trades", 0) >= min_trades:
                    recs.append({**pe, **m})
                done += 1
                if progress_cb and done % 10 == 0:
                    progress_cb(done, n_total)
            if not recs:
                continue
            gated = [r for r in recs if _is_real(r, tr_end - tr_start)]
            champ = max(gated or recs, key=lambda r: float(r.get("total_pnl", 0) or 0))
            pp = {k: champ[k] for k in pkeys if k in champ}
            om = _ev(te_s, te_e, pp)
            row = {k: champ.get(k) for k in pkeys}
            row.update({k: champ.get(k) for k in _METRIC_KEYS})
            row["fold"] = f + 1
            row["test_bars"] = te_e - te_s
            row["train_bars"] = tr_end - tr_start   # IS window length (for WFE)
            row["oos_pnl"] = float(om["total_pnl"]) if om else 0.0
            row["oos_trades"] = int(om["num_trades"]) if om else 0
            row["oos_pf"] = float(om.get("profit_factor", 0)) if om else 0.0
            records.append(row)
        if progress_cb:
            progress_cb(n_total, n_total)
        is_wf = True
    else:
        # ── Single 75/25 split (or no-OOS) ────────────────────────────────
        samp = _RandomSampler(space, seed=seed)
        ksplit = int(n * OOS_SPLIT) if oos_on else n
        seen = set()
        for i in range(n_trials):
            pe = _collapse(samp.ask(), dp)
            m = _ev(0, ksplit, pe)
            if m and m.get("num_trades", 0) >= min_trades:
                sig = tuple(sorted(pe.items()))
                if sig not in seen:
                    seen.add(sig)
                    records.append({**pe, **m})
            if progress_cb and (i % 10 == 0 or i + 1 == n_trials):
                progress_cb(i + 1, n_trials)
        if oos_on:
            for rec in records:
                pp = {k: rec[k] for k in pkeys if k in rec}
                om = _ev(ksplit, n, pp)
                rec["oos_pnl"] = float(om["total_pnl"]) if om else 0.0
                rec["oos_trades"] = int(om["num_trades"]) if om else 0
                rec["oos_pf"] = float(om.get("profit_factor", 0)) if om else 0.0
        is_wf = False

    if not records:
        return {"mode": method, "n_combos": n_trials * (1 if not is_wf else 1),
                "n_valid": 0, "top": [], "best_params": None, "best": None,
                "bars": int(n), "master": (arrays.get("meta") or {}).get("name"),
                "no_results": True}

    # ── Rank ────────────────────────────────────────────────────────────────
    if is_wf:
        # Keep fold order; headline = last fold's champion (most recent re-optimize).
        ranked = records
        best = records[-1]
    else:
        # Realism-gated headline (enough wins AND losses, capped rate/PF) ranked
        # above the rest, then by total PnL — a few-loss PF mirage can't headline.
        ranked = sorted(records, key=lambda r: (1 if _is_real(r, n) else 0,
                                                float(r.get("total_pnl", 0) or 0)),
                        reverse=True)
        best = ranked[0]

    top = []
    for r in ranked[:top_n]:
        row = {k: r.get(k) for k in pkeys if k in r}
        row.update({k: r.get(k) for k in _METRIC_KEYS if k in r})
        for k in ("oos_pnl", "oos_trades", "oos_pf", "fold", "test_bars", "train_bars"):
            if k in r:
                row[k] = r[k]
        top.append(row)

    out = {"mode": method, "n_combos": (n_trials if not is_wf else n_trials),
           "n_valid": len(records), "top": top,
           "best_params": {k: best.get(k) for k in pkeys if k in best},
           "best": {k: best.get(k) for k in _METRIC_KEYS if k in best},
           "bars": int(n), "master": (arrays.get("meta") or {}).get("name"),
           "wf": is_wf}
    if not is_wf:   # config-PnL spread + param points for distribution / scatter / heatmap
        out["dist"] = downsample_pnls([r.get("total_pnl", 0) for r in records])
        out["points"] = downsample_points(
            [dict({k: r.get(k) for k in pkeys}, pnl=round(float(r.get("total_pnl", 0) or 0), 1))
             for r in records])

    # ── Regime report card + neighborhood robustness on the winner (opt-in) ──
    if (compute_regime or compute_neighbors) and best:
        bp0 = {k: best.get(k) for k in pkeys if k in best}

        def _eval_full(pp):
            ex = {}
            if pass_vol:
                ex["volumes"] = V
            if pass_day:
                ex["day_id"] = did
            try:
                if cost_pts > 0:
                    m = fn(O, H, L, C, return_trades=True, **ex, **pp)
                    if m:
                        m = _apply_costs(m, cost_pts)
                    return m
                return fn(O, H, L, C, return_trades=True, **ex, **pp)
            except Exception:
                return None

        if compute_regime:
            wm = _eval_full(bp0)
            idx = arrays.get("index")
            if wm and wm.get("trades") and idx is not None:
                rr = regime_report(wm["trades"], idx, H, L, C, cost_pts=cost_pts)
                if rr:
                    out["regime"] = rr
        if compute_neighbors:
            # No discrete grid in auto search → derive ±1 candidates from each
            # numeric param's DEFAULT_PARAMS step around the winner value.
            vopts = {}
            for k in pkeys:
                meta = dp.get(k, {})
                if not isinstance(meta, dict) or meta.get("type") not in ("int", "float"):
                    continue
                bv = bp0.get(k)
                if bv is None:
                    continue
                step = meta.get("step") or (1 if meta.get("type") == "int" else 0)
                if not step:
                    continue
                lo, hi = meta.get("min"), meta.get("max")
                cand = sorted({bv,
                               (bv - step if lo is None else max(lo, bv - step)),
                               (bv + step if hi is None else min(hi, bv + step))})
                if len(cand) > 1:
                    vopts[k] = cand
            if vopts:
                nb = neighborhood(lambda pp: _eval_full(pp), bp0, vopts)
                if nb:
                    out["neighborhood"] = nb

    # ── Winner analytics (equity + MC + DSR), same as run_grid ──────────────
    if (compute_dsr or mc_sims) and best:
        if years is None:
            try:
                idx = arrays.get("index")
                years = max(0.1, (idx[-1] - idx[0]).days / 365.25)
            except Exception:
                years = 1.0
        bp = {k: best.get(k) for k in pkeys if k in best}

        def _net_pnls(pp, a=0, b=n):
            ex = {}
            if pass_vol:
                ex["volumes"] = V[a:b]
            if pass_day:
                ex["day_id"] = did[a:b]
            try:
                m = fn(O[a:b], H[a:b], L[a:b], C[a:b], return_trades=True, **ex, **pp)
            except Exception:
                return None
            if not m or not m.get("trades"):
                return None
            return [t[2] - cost_pts for t in m["trades"]]

        win_pnls = _net_pnls(bp)
        if win_pnls:
            cum, s = [], 0.0
            for x in win_pnls:
                s += x; cum.append(s)
            if len(cum) > 160:
                st = len(cum) / 160
                cum = [cum[int(i * st)] for i in range(160)]
            out["equity"] = {"cum": [round(float(x), 1) for x in cum],
                             "final": round(float(s), 1), "n": len(win_pnls)}
            if mc_sims:
                out["mc"] = monte_carlo_drawdown(win_pnls, n_sims=int(mc_sims))
            if compute_dsr:
                srs = []
                for r in ranked[:40]:
                    pp = {k: r.get(k) for k in pkeys if k in r}
                    pn = _net_pnls(pp)
                    sr = annualized_sr(pn, years) if pn else None
                    if sr:
                        srs.append(sr["sr"])
                out["dsr"] = deflated_sharpe(annualized_sr(win_pnls, years), srs,
                                             len(records), years)
    return out
