"""
augur_mp_worker — streamlit-free multiprocessing worker for AUGUR grid sweeps.

WHY THIS FILE EXISTS (the v5.8.7 lesson): on Windows, ProcessPoolExecutor uses
the 'spawn' start method, so every worker process imports the module that owns
the task function. When that function lived inside optimizer.py, each worker
re-imported the ENTIRE Streamlit app in bare mode and every backtest errored —
silently producing "0 valid combos". This module imports ONLY numpy/stdlib, so
workers stay clean. optimizer.py submits `eval_chunk` tasks here.

Protocol:
  • Pool is created with initializer=init_worker, initargs=(strategy_path,
    O, H, L, C, volumes_or_None, day_id_or_None, cost_pts).
    The big OHLCV arrays are pickled ONCE per worker (not per task).
  • init_worker loads the strategy module BY FILE PATH (importlib), introspects
    run_backtest's signature (same rule as the app: pass volumes/day_id only if
    declared or **kwargs), and stashes everything in process-level globals.
  • eval_chunk(chunk) — chunk is a list of (idx, params_dict) — returns a list
    of (idx, metrics_dict_or_None, error_str_or_None). Cost application
    (commission+slippage per round trip) happens HERE so results are byte-
    identical to the single-thread path. min_trades gating stays in the parent.
"""
import importlib.util
import inspect
import os

# Per-process state, set once by init_worker.
_G = {"fn": None, "extras": {}, "cost_pts": 0.0,
      "O": None, "H": None, "L": None, "C": None,
      "cache_ctx": None, "tc": None}


def _apply_costs(m, cost_pts):
    """Identical math to optimizer._apply_costs — re-derive NET metrics from the
    trade list after subtracting cost_pts from each round-trip trade."""
    trades = m.get("trades") if isinstance(m, dict) else None
    if not trades:
        return m
    net = []
    for t in trades:
        nt = list(t)
        if len(nt) >= 3:
            nt[2] = nt[2] - cost_pts
        net.append(tuple(nt))
    pnls   = [t[2] for t in net]
    n      = len(pnls)
    wins   = sum(1 for x in pnls if x > 0)
    losses = sum(1 for x in pnls if x < 0)
    gw     = sum(x for x in pnls if x > 0)
    gl     = -sum(x for x in pnls if x < 0)
    total  = float(sum(pnls))
    if   gl > 1e-9: pf = gw / gl
    elif gw > 0:    pf = float("inf")
    else:           pf = 0.0
    cum = peak = mdd = 0.0
    for x in pnls:
        cum += x; peak = max(peak, cum); mdd = min(mdd, cum - peak)
    out = dict(m)
    out.update({"total_pnl": total, "num_trades": n,
                "win_rate": (100.0 * wins / n) if n else 0.0,
                "profit_factor": pf, "max_drawdown": float(mdd),
                "avg_pnl": (total / n) if n else 0.0,
                "wins": wins, "losses": losses, "trades": net})
    return out


def init_worker(strategy_path, O, H, L, C, volumes, day_id, cost_pts, cache_ctx=None):
    """Pool initializer — runs once per worker process. `cache_ctx` is a new,
    OPTIONAL trailing initarg (docs/INCREMENTAL_BACKTEST_REUSE.md, PR1) — existing
    8-positional-arg callers (optimizer.py's Streamlit app, tools/test_mp_worker.py)
    are unaffected; they simply never pass it and get cache_ctx=None (caching off
    for that worker, byte-identical to before this change)."""
    spec = importlib.util.spec_from_file_location(
        "augur_mp_strategy_" + os.path.basename(strategy_path).replace(".", "_"),
        strategy_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    fn = mod.run_backtest

    sp = inspect.signature(fn).parameters
    has_kw = any(p.kind == p.VAR_KEYWORD for p in sp.values())
    extras = {}
    if volumes is not None and (has_kw or "volumes" in sp):
        extras["volumes"] = volumes
    if day_id is not None and (has_kw or "day_id" in sp):
        extras["day_id"] = day_id

    _G["fn"] = fn
    _G["extras"] = extras
    _G["cost_pts"] = float(cost_pts or 0.0)
    _G["O"], _G["H"], _G["L"], _G["C"] = O, H, L, C

    # Trial-level result cache: only imported when the PARENT (augur_engine.
    # optimize.run_grid) already confirmed AUGUR_TRIAL_CACHE is on AND could source
    # a full ctx for this job. This keeps a cache-disabled (the default) worker
    # exactly as lightweight as it was before this change — no augur_engine
    # package import at all — which matters here specifically: this module's
    # whole reason to exist (see the module docstring) is that workers stay
    # numpy/stdlib-only so a Windows spawn-mode worker starts fast and clean.
    _G["cache_ctx"] = cache_ctx
    _G["tc"] = None
    if cache_ctx is not None:
        try:
            from augur_engine import trial_cache as _tc
            _G["tc"] = _tc
        except Exception:
            _G["tc"] = None   # fail-open — this worker just never hits the cache


def eval_chunk(chunk):
    """Evaluate a list of (idx, params) → list of (idx, metrics|None, err|None).
    Trial-cache read-through (PR1): a cache HIT skips the backtest call entirely;
    a MISS computes exactly as before, then writes the cache entry. Cache-machinery
    failures (a bad key, a locked/corrupt DB) degrade to a normal uncached compute
    for that one config — they are kept in a SEPARATE try/except from the backtest
    call itself, so a cache bug can never be misreported as a backtest error, and a
    genuine backtest error is reported EXACTLY as before this change."""
    fn      = _G["fn"]
    extras  = _G["extras"]
    cost    = _G["cost_pts"]
    O, H, L, C = _G["O"], _G["H"], _G["L"], _G["C"]
    ctx = _G.get("cache_ctx")
    tc = _G.get("tc")
    out = []
    for idx, p in chunk:
        key = None
        if ctx is not None and tc is not None:
            try:
                if tc.is_enabled():
                    key = tc.make_key(ctx, p, a=0, b=len(O))
                    cached = tc.get(key)
                    if cached is not None:
                        tc.record_hit()
                        out.append((idx, cached, None))
                        continue
                    tc.record_miss()
            except Exception:
                key = None   # cache machinery failed -- fall through to a normal compute
        try:
            if cost > 0:
                m = fn(O, H, L, C, return_trades=True, **extras, **p)
                if m:
                    m = _apply_costs(m, cost)
                    m.pop("trades", None)
            else:
                m = fn(O, H, L, C, **extras, **p)
            out.append((idx, m, None))
        except Exception as e:
            out.append((idx, None, f"{type(e).__name__}: {e}"))
            continue
        if key is not None and m is not None:
            try:
                tc.put(key, m, strategy_file_sha=ctx.get("strategy_file_sha"),
                      master_id=ctx.get("master_id"), engine_epoch=ctx.get("engine_epoch"))
            except Exception:
                pass
    return out
