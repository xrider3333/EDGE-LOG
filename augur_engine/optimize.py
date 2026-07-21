"""Grid optimization (streamlit-free) — Phase 2 of the EDGELOG port.

run_grid() expands a parameter grid (a strategy's PARAM_GRID_PRESETS label, or a custom
{param:[values]} dict), evaluates every combo, gates on min_trades, and returns the top-N
ranked configs + the winner — the same shape the optimizer's Executions tab produces.

Multicore reuses the proven streamlit-free augur_mp_worker (the app's verified 3.4x path);
workers=1 runs single-threaded (used for headless verification).
"""
import itertools
import inspect

from .strategies import load_strategy, _resolve
from .data import find_master, load_master_arrays
from .engine import _apply_costs
from .analytics import (annualized_sr, deflated_sharpe, monte_carlo_drawdown,
                        regime_report, neighborhood, downsample_pnls, downsample_points,
                        mae_mfe, relationship_scores, pdp_plateau)
from . import trial_cache as TC

_METRIC_KEYS = ("total_pnl", "num_trades", "win_rate", "profit_factor",
                "max_drawdown", "avg_pnl")


def expand_grid(grid: dict):
    """{param:[v,...]} -> list of param dicts (cartesian product)."""
    keys = list(grid.keys())
    vals = [grid[k] if isinstance(grid[k], (list, tuple)) else [grid[k]] for k in keys]
    return [dict(zip(keys, combo)) for combo in itertools.product(*vals)]


def grid_from_preset(mod, preset_label):
    presets = getattr(mod, "PARAM_GRID_PRESETS", {})
    if preset_label not in presets:
        raise ValueError(f"preset '{preset_label}' not in {list(presets)}")
    return presets[preset_label]


def list_presets(strategy):
    """Preset labels available for a strategy (for the UI scope picker)."""
    mod = load_strategy(strategy) if isinstance(strategy, str) else strategy
    return list(getattr(mod, "PARAM_GRID_PRESETS", {}).keys())


def _topk_ensemble(fn, O, H, L, C, extras, cost_pts, ranked, k=5):
    """Re-run the top-K ranked configs and equal-weight blend them (board §6).
    `ranked` = param dicts, best first. Returns the ensemble_blend dict (+ the
    configs used) or None if fewer than 2 produced trades. Kept small so both
    run_grid (auto) and engine.run_ensemble_topk can share it."""
    import numpy as np
    from .analytics import ensemble_blend, ensemble_ccmp
    nb = len(C)
    bar_pnls, used = [], []
    for pp in ranked[:int(k)]:
        try:
            m = fn(O, H, L, C, return_trades=True, **extras, **pp)
        except Exception:
            m = None
        tr = (m or {}).get("trades") or []
        if not tr:
            continue
        bar = np.zeros(nb)
        for t in tr:
            eb = int(t[1]) if len(t) > 1 else int(t[0])
            eb = 0 if eb < 0 else (nb - 1 if eb >= nb else eb)
            bar[eb] += float(t[2]) - (cost_pts if cost_pts > 0 else 0.0)
        bar_pnls.append(bar); used.append(pp)
    if len(bar_pnls) < 2:
        return None
    ens = ensemble_blend([b.tolist() for b in bar_pnls])
    if ens:
        ens["configs"] = used
        try:                                    # §6 stacking / CCMP (weights fit OOS)
            cc = ensemble_ccmp([b.tolist() for b in bar_pnls])
            if cc:
                ens["ccmp"] = cc
        except Exception:
            pass
    return ens


def run_grid(strategy, *, instrument=None, timeframe="5m", session="rth", source=None,
             preset=None, grid=None, master=None, arrays=None, cost_pts=0.0,
             min_trades=30, top_n=10, workers=1, rank_by="total_pnl", progress_cb=None,
             compute_dsr=False, mc_sims=0, years=None,
             compute_regime=False, compute_neighbors=False,
             compute_ensemble=False, ensemble_k=5,
             date_from=None, date_to=None):
    """Exhaustive grid sweep. Returns {n_combos,n_valid,top[...],best_params,best,bars,master}.

    Supply either `preset` (a PARAM_GRID_PRESETS label) or `grid` ({param:[values]}).
    Data resolves like run_backtest: arrays -> master row -> find_master(...).
    """
    path = _resolve(strategy) if isinstance(strategy, str) else None
    mod = load_strategy(strategy) if isinstance(strategy, str) else strategy
    g = grid if grid is not None else grid_from_preset(mod, preset)
    combos = expand_grid(g)

    if arrays is None:
        if master is None:
            master = find_master(instrument, timeframe, session, source)
            if master is None:
                raise ValueError(f"no master for {instrument} {timeframe} {session} {source}")
        arrays = load_master_arrays(master, date_from=date_from, date_to=date_to)
    O, H, L, C = arrays["open"], arrays["high"], arrays["low"], arrays["close"]
    V = arrays.get("volume")
    did = arrays.get("day_id")

    fn = mod.run_backtest
    sp = inspect.signature(fn).parameters
    has_kw = any(p.kind == p.VAR_KEYWORD for p in sp.values())
    extras = {}
    if V is not None and (has_kw or "volumes" in sp):
        extras["volumes"] = V
    if did is not None and (has_kw or "day_id" in sp):
        extras["day_id"] = did

    results = []   # (params, metrics)

    # ── Trial-level result cache (PR1, docs/INCREMENTAL_BACKTEST_REUSE.md) ──
    # Built ONCE per job (not per config); a None ctx (flag off, or a required
    # field couldn't be cleanly sourced -- e.g. arrays supplied directly with no
    # master/fingerprint) is the universal "don't cache this job" signal every
    # read-through below checks.
    cache_ctx = None
    if TC.is_enabled():
        cache_ctx = TC.build_ctx(mod, arrays, cost_pts=cost_pts, session=session,
                                 date_from=date_from, date_to=date_to, master=master)

    if workers and workers > 1 and path:
        import augur_mp_worker as W
        from concurrent.futures import ProcessPoolExecutor
        tasks = list(enumerate(combos))
        nchunks = max(1, workers * 4)
        size = max(1, (len(tasks) + nchunks - 1) // nchunks)
        chunks = [tasks[i:i + size] for i in range(0, len(tasks), size)]
        done = 0
        with ProcessPoolExecutor(max_workers=workers, initializer=W.init_worker,
                                 initargs=(path, O, H, L, C, V, did, cost_pts,
                                          cache_ctx)) as ex:
            try:
                for out in ex.map(W.eval_chunk, chunks):
                    for idx, m, _err in out:
                        if m:
                            results.append((combos[idx], m))
                    done += 1
                    if progress_cb:
                        progress_cb(min(done * size, len(combos)), len(combos))
            except BaseException:
                # A web STOP makes progress_cb raise. Cancel the still-queued chunks
                # instead of letting the context-manager exit drain the whole sweep
                # (shutdown(wait=True)); in-flight chunks (<= workers) finish promptly.
                ex.shutdown(wait=False, cancel_futures=True)
                raise
    else:
        for i, params in enumerate(combos):
            key = None
            if cache_ctx is not None:
                try:
                    if TC.is_enabled():
                        key = TC.make_key(cache_ctx, params, a=0, b=len(O))
                        cached = TC.get(key)
                        if cached is not None:
                            TC.record_hit()
                            results.append((params, cached))
                            if progress_cb and (i % 25 == 0 or i + 1 == len(combos)):
                                progress_cb(i + 1, len(combos))
                            continue
                        TC.record_miss()
                except Exception:
                    key = None   # cache machinery failed -- fall through to a normal compute
            try:
                if cost_pts > 0:
                    m = fn(O, H, L, C, return_trades=True, **extras, **params)
                    if m:
                        m = _apply_costs(m, cost_pts)
                        m.pop("trades", None)
                else:
                    m = fn(O, H, L, C, **extras, **params)
            except Exception:
                m = None
            if m:
                results.append((params, m))
                if key is not None:
                    try:
                        TC.put(key, m, strategy_file_sha=cache_ctx["strategy_file_sha"],
                              master_id=cache_ctx["master_id"],
                              engine_epoch=cache_ctx["engine_epoch"])
                    except Exception:
                        pass
            if progress_cb and (i % 25 == 0 or i + 1 == len(combos)):
                progress_cb(i + 1, len(combos))

    valid = [(p, m) for p, m in results if m and m.get("num_trades", 0) >= min_trades]

    def _rank_key(pm):
        # "mar" = net PnL / |max drawdown| (drawdown-adjusted return — what you size on).
        # Not a returned metric key, so derive it; otherwise sort by the named metric.
        m = pm[1]
        if rank_by == "mar":
            dd = abs(float(m.get("max_drawdown", 0) or 0.0))
            pnl = float(m.get("total_pnl", 0) or 0.0)
            return (pnl / dd) if dd > 1e-9 else (float("inf") if pnl > 0 else 0.0)
        return m.get(rank_by, 0) or 0

    valid.sort(key=_rank_key, reverse=True)
    top = []
    for p, m in valid[:top_n]:
        row = dict(p)
        row.update({k: m.get(k) for k in _METRIC_KEYS})
        top.append(row)
    best = valid[0] if valid else None
    # points rows carry pnl AND dd (drawdown magnitude, engine pts) so the web's param
    # charts can plot risk metrics, not just PnL (ORB.md item L: a DD lever like
    # be_after_R is invisible on a PnL axis). MAR is derived client-side as pnl/dd.
    _pts_full = [dict(p, pnl=round(float(m.get("total_pnl", 0) or 0), 1),
                      dd=round(abs(float(m.get("max_drawdown", 0) or 0)), 1)) for p, m in valid]
    out = {
        "n_combos": len(combos), "n_valid": len(valid), "top": top,
        "best_params": (best[0] if best else None),
        "best": (best[1] if best else None),
        "bars": int(len(C)),
        "master": (arrays.get("meta") or {}).get("name"),
        "dist": downsample_pnls([m.get("total_pnl", 0) for _, m in valid]),
        "points": downsample_points(_pts_full),
    }
    _rel = relationship_scores(_pts_full)   # Pearson / MI / PPS per param vs PnL (ROADMAP #24)
    if _rel:
        out["relationship"] = _rel
    # ── 3C.1 PDP-plateau pick (ROADMAP #24a): the broad-high-ground champion,
    #    reported ALONGSIDE the argmax `best` (both visible; deploy decision is
    #    the owner's). Index aligns with `valid` so we attach real metrics.
    _pp = pdp_plateau(_pts_full)
    if _pp:
        _pi = _pp.pop("index")
        _ppm = valid[_pi][1]
        out["plateau_pick"] = {
            "params": valid[_pi][0],
            "metrics": {k: _ppm.get(k) for k in _METRIC_KEYS},
            "score": _pp["score"], "argmax_score": _pp["argmax_score"],
            "curves": _pp["curves"],
            # boundary-peak detector (3C.1b): flags knobs whose optimum is pinned at
            # the tested-range edge and still rising → the search was truncated.
            "boundary_flags": _pp["boundary_flags"],
            "search_truncated": _pp["search_truncated"],
            "same_as_best": bool(best and valid[_pi][0] == best[0]),
        }

    # ── §6 Ensemble top-K (opt-in): blend the top-K configs equal-weight and compare
    #    to the rank-1 winner by recovery factor — a diversified blend is more robust
    #    to the winner being a lucky spike. Costs `ensemble_k` extra backtests. ──
    if compute_ensemble and len(valid) >= 2:
        _ens = _topk_ensemble(fn, O, H, L, C, extras, cost_pts,
                              [p for p, _m in valid], k=int(ensemble_k))
        if _ens:
            _ens["rank_by"] = rank_by
            _ens["n_valid"] = len(valid)
            _ens["single_best_params"] = valid[0][0]
            out["ensemble"] = _ens

    # Regime report card + neighborhood robustness on the winner (opt-in).
    if best and (compute_regime or compute_neighbors):
        bp = best[0]

        def _eval_net(pp, want_trades=False):
            try:
                if cost_pts > 0:
                    m = fn(O, H, L, C, return_trades=True, **extras, **pp)
                    if m:
                        m = _apply_costs(m, cost_pts)
                        if not want_trades:
                            m.pop("trades", None)
                    return m
                return fn(O, H, L, C, return_trades=want_trades, **extras, **pp)
            except Exception:
                return None

        if compute_regime:
            wm = _eval_net(bp, want_trades=True)
            idx = arrays.get("index")
            if wm and wm.get("trades") and idx is not None:
                rr = regime_report(wm["trades"], idx, H, L, C, cost_pts=cost_pts)
                if rr:
                    out["regime"] = rr
        if compute_neighbors:
            vopts = {k: sorted(set(v)) for k, v in g.items()
                     if isinstance(v, (list, tuple)) and len(set(v)) > 1
                     and all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in v)}
            if vopts:
                nb = neighborhood(lambda pp: _eval_net(pp), bp, vopts)
                if nb:
                    out["neighborhood"] = nb

    # Champion analytics on the winner. The cheap ones (champion equity, per-trade win
    # distribution, MAE/MFE, top-config equity overlay, chronological stress) are derived
    # from a single winner backtest, so we compute them for EVERY run — a grid sweep gets the
    # same 1A/1D/1G/1I tiles a validate run does. Monte-Carlo drawdown (mc) and Deflated
    # Sharpe (dsr) stay opt-in (they re-run extra backtests) via their own guards below.
    if best:
        if years is None:
            try:
                idx = arrays.get("index")
                years = max(0.1, (idx[-1] - idx[0]).days / 365.25)
            except Exception:
                years = 1.0

        def _net_pnls(pp):
            try:
                m = fn(O, H, L, C, return_trades=True, **extras, **pp)
            except Exception:
                return None
            if not m or not m.get("trades"):
                return None
            return [t[2] - cost_pts for t in m["trades"]]

        win_pnls = _net_pnls(best[0])
        if win_pnls:
            cum = []
            _s = 0.0
            for _x in win_pnls:
                _s += _x; cum.append(_s)
            if len(cum) > 160:   # endpoint-pinned: last sample = the true final
                _st = (len(cum) - 1) / 159
                cum = [cum[round(i * _st)] for i in range(160)]
            out["equity"] = {"cum": [round(float(x), 1) for x in cum],
                             "final": round(float(_s), 1), "n": len(win_pnls)}
            # Winner's per-trade PnL sample (downsampled) for the trade-PnL distribution curve.
            _wd = win_pnls
            if len(_wd) > 400:
                _ds = len(_wd) / 400
                _wd = [_wd[int(i * _ds)] for i in range(400)]
            out["win_dist"] = [round(float(x), 2) for x in _wd]
            try:    # MAE/MFE (needs rich 5-tuple trades; None for legacy strategies)
                _wm = fn(O, H, L, C, return_trades=True, **extras, **best[0])
                if _wm and _wm.get("trades"):
                    _mm = mae_mfe(_wm["trades"], H, L)
                    if _mm:
                        out["mae_mfe"] = _mm
            except Exception:
                pass
            # top-N equity overlay (robustness: do the best configs all climb alike?)
            etop = []
            for (pp_, _m) in valid[:50]:   # top config equity curves for the TOP CONFIGS PNL overlay
                pn = _net_pnls(pp_)
                if not pn:
                    continue
                cc, ss = [], 0.0
                for x in pn:
                    ss += x; cc.append(ss)
                if len(cc) > 80:
                    st2 = len(cc) / 80
                    cc = [cc[int(i * st2)] for i in range(80)]
                etop.append({"cum": [round(float(x), 1) for x in cc]})   # map, not nested array
            out["equity_top"] = etop
            if len(win_pnls) >= 16:   # PnL across 8 chronological windows (concentration check)
                N = 8; sz = len(win_pnls) // N
                out["stress"] = [round(float(sum(win_pnls[i*sz:(len(win_pnls) if i == N-1 else (i+1)*sz)])), 1)
                                 for i in range(N)]
            if mc_sims:
                out["mc"] = monte_carlo_drawdown(win_pnls, n_sims=int(mc_sims))
            if compute_dsr:
                import random as _rnd
                _rnd.seed(42)
                idxs = (list(range(len(valid))) if len(valid) <= 40
                        else sorted(_rnd.sample(range(len(valid)), 40)))
                srs = []
                for _k in idxs:
                    pn = _net_pnls(valid[_k][0])
                    r = annualized_sr(pn, years) if pn else None
                    if r:
                        srs.append(r["sr"])
                out["dsr"] = deflated_sharpe(annualized_sr(win_pnls, years), srs,
                                             len(combos), years)
    # MAE/MFE always (cheap: one winner backtest) so the AI loop's diagnostics get it too.
    if best and "mae_mfe" not in out:
        try:
            _wm = fn(O, H, L, C, return_trades=True, **extras, **best[0])
            if _wm and _wm.get("trades"):
                _mm = mae_mfe(_wm["trades"], H, L)
                if _mm:
                    out["mae_mfe"] = _mm
        except Exception:
            pass
    return out
