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
                        regime_report, neighborhood)

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


def run_grid(strategy, *, instrument=None, timeframe="5m", session="rth", source=None,
             preset=None, grid=None, master=None, arrays=None, cost_pts=0.0,
             min_trades=30, top_n=10, workers=1, rank_by="total_pnl", progress_cb=None,
             compute_dsr=False, mc_sims=0, years=None,
             compute_regime=False, compute_neighbors=False):
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
        arrays = load_master_arrays(master)
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

    if workers and workers > 1 and path:
        import augur_mp_worker as W
        from concurrent.futures import ProcessPoolExecutor
        tasks = list(enumerate(combos))
        nchunks = max(1, workers * 4)
        size = max(1, (len(tasks) + nchunks - 1) // nchunks)
        chunks = [tasks[i:i + size] for i in range(0, len(tasks), size)]
        done = 0
        with ProcessPoolExecutor(max_workers=workers, initializer=W.init_worker,
                                 initargs=(path, O, H, L, C, V, did, cost_pts)) as ex:
            for out in ex.map(W.eval_chunk, chunks):
                for idx, m, _err in out:
                    if m:
                        results.append((combos[idx], m))
                done += 1
                if progress_cb:
                    progress_cb(min(done * size, len(combos)), len(combos))
    else:
        for i, params in enumerate(combos):
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
            if progress_cb and (i % 25 == 0 or i + 1 == len(combos)):
                progress_cb(i + 1, len(combos))

    valid = [(p, m) for p, m in results if m and m.get("num_trades", 0) >= min_trades]
    valid.sort(key=lambda pm: pm[1].get(rank_by, 0) or 0, reverse=True)
    top = []
    for p, m in valid[:top_n]:
        row = dict(p)
        row.update({k: m.get(k) for k in _METRIC_KEYS})
        top.append(row)
    best = valid[0] if valid else None
    out = {
        "n_combos": len(combos), "n_valid": len(valid), "top": top,
        "best_params": (best[0] if best else None),
        "best": (best[1] if best else None),
        "bars": int(len(C)),
        "master": (arrays.get("meta") or {}).get("name"),
    }

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

    # Phase-4 analytics on the winner (opt-in): Monte-Carlo drawdown + Deflated Sharpe.
    if best and (compute_dsr or mc_sims):
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
            if len(cum) > 160:
                _st = len(cum) / 160
                cum = [cum[int(i * _st)] for i in range(160)]
            out["equity"] = {"cum": [round(float(x), 1) for x in cum],
                             "final": round(float(_s), 1), "n": len(win_pnls)}
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
    return out
