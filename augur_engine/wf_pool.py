"""
Walk-forward folds in parallel processes (2026-09-08).

WHY. A validate's Stage B calls run_auto(method="walkforward") twice, once per windowing
scheme (rolling, anchored). Each scheme runs up to 8 folds, and every fold is n_trials
backtests on its training window plus one on its test window: 3,200 backtests at the
default 200 trials, sixteen times the in-sample search that precedes it, all on one core.
Measured 2026-09-08 on a 4.5-year NQ 5m NOISE validate: the sequential job ran the better
part of an hour with the machine 90% idle.

The folds share nothing. Each builds its own sampler from the run's seed, so a fold's
result does not depend on which folds ran before it or on which process ran it. That makes
a fold the natural parallel unit, and it makes the parallel result BIT-IDENTICAL to the
sequential one by construction: both paths call auto._wf_fold_row, and a worker builds its
evaluator with the same make_slice_evaluator(mod, arrays, cost_pts, cache_ctx) the
sequential path uses. tests/test_wf_parallel.py pins that identity.

WHAT A WORKER LOADS. Arrays are RELOADED from the master inside each worker (the largest
master, NQ 1-minute ETH at 306 MB, parses in about 3 s) rather than pickled across from
the parent, which for that master would be a quarter-gigabyte per worker. When the caller
handed run_auto explicit arrays and no master (the tests do), those arrays are sent once
per worker at pool start instead.

Windows starts worker processes fresh (spawn, not fork), so everything a worker needs is
module-level here and importable by name.
"""
_W = {}


def init_worker(strategy, master, date_from, date_to, arrays, cost_pts, session):
    """Pool initializer: one evaluator per worker process, built the way run_auto builds
    its own. `arrays` is None when the worker should reload from `master`."""
    from .strategies import load_strategy
    from .data import load_master_arrays
    from . import trial_cache as TC
    from .auto import make_slice_evaluator
    mod = load_strategy(strategy)
    if arrays is None:
        arrays = load_master_arrays(master, date_from=date_from, date_to=date_to)
    ctx = None
    if TC.is_enabled():
        try:
            ctx = TC.build_ctx(mod, arrays, cost_pts=cost_pts, session=session,
                               date_from=date_from, date_to=date_to, master=master)
        except Exception:
            ctx = None          # cache off for this worker; numbers are unaffected
    _W["ev"] = make_slice_evaluator(mod, arrays, cost_pts, cache_ctx=ctx)
    _W["H"], _W["L"] = arrays["high"], arrays["low"]
    _W["cost_pts"] = float(cost_pts or 0.0)


def fold_task(spec):
    """One fold. spec = (f, tr_start, tr_end, te_s, te_e, space, dp, pkeys, seed,
    n_trials, min_trades). Returns (f, row-or-None)."""
    from .auto import _wf_fold_row
    f, tr_start, tr_end, te_s, te_e, space, dp, pkeys, seed, n_trials, min_trades = spec
    row = _wf_fold_row(_W["ev"], _W["H"], _W["L"], space, dp, pkeys, seed, n_trials,
                       min_trades, _W["cost_pts"], f, tr_start, tr_end, te_s, te_e)
    return f, row
