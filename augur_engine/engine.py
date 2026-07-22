"""The callable backtest entry point (streamlit-free).

run_backtest() ties a strategy plugin + a master (or raw arrays) + params together,
using the SAME rules as the Streamlit app:
  • signature introspection — pass volumes/day_id only if the plugin declares them
    (or has **kwargs), so older plugins that don't take them still work;
  • cost application — subtract cost_pts (commission+slippage per round-trip, in
    points) from each trade and re-derive NET metrics, byte-identical to the app's
    _apply_costs / augur_mp_worker path.
"""
import inspect

from .strategies import load_strategy
from .data import find_master, load_master_arrays
from .analytics import monte_carlo_drawdown
from . import trial_cache as TC
from . import window_delta as WD


def _apply_costs(m, cost_pts):
    """Re-derive NET metrics from the trade list after subtracting cost_pts/trade.
    Same math as augur_mp_worker._apply_costs (kept inline so this package is
    self-contained)."""
    trades = m.get("trades") if isinstance(m, dict) else None
    if not trades:
        return m
    net = []
    for t in trades:
        nt = list(t)
        if len(nt) >= 3:
            nt[2] = nt[2] - cost_pts
        net.append(tuple(nt))
    pnls = [t[2] for t in net]
    n = len(pnls)
    wins = sum(1 for x in pnls if x > 0)
    losses = sum(1 for x in pnls if x < 0)
    gw = sum(x for x in pnls if x > 0)
    gl = -sum(x for x in pnls if x < 0)
    total = float(sum(pnls))
    pf = (gw / gl) if gl > 1e-9 else (float("inf") if gw > 0 else 0.0)
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


def run_backtest(strategy, *, instrument=None, timeframe="5m", session="rth",
                 source=None, params=None, master=None, arrays=None,
                 cost_pts=0.0, return_trades=False, mc_sims=0, mc_block=1,
                 date_from=None, date_to=None, sizing=None,
                 ml_filter=None, ml_threshold=0.50, ml_min_history=30,
                 ml_refit_every=25):
    """Run one backtest and return the metrics dict (with a "_meta" block).

    strategy   : plugin filename ('ORB_3_0.py'), path, or a loaded module.
    Data is resolved in priority order: explicit `arrays` -> explicit `master` row
    -> find_master(instrument, timeframe, session, source).
    cost_pts   : per-round-trip cost in POINTS (e.g. NQ $5.66 / $20 = 0.283).
    """
    mod = strategy if hasattr(strategy, "run_backtest") else load_strategy(strategy)
    params = dict(params or {})

    if arrays is None:
        if master is None:
            master = find_master(instrument, timeframe, session, source)
            if master is None:
                raise ValueError(
                    f"no master for instrument={instrument} timeframe={timeframe} "
                    f"session={session} source={source}")
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
    # Bar timestamps — only handed to strategies that ask for `index` (e.g. REPLAY_1_0,
    # which matches discretionary entry times to bars). Existing strategies don't declare
    # it, so this is a no-op for them.
    _idx = arrays.get("index")
    if _idx is not None and (has_kw or "index" in sp):
        extras["index"] = _idx

    _gate_on = bool(ml_filter) and str(ml_filter).lower() not in ("", "none")
    want_trades = bool(return_trades or cost_pts > 0 or mc_sims > 0 or _gate_on or sizing)

    # ── Trial-level result cache read-through (PR1, docs/INCREMENTAL_BACKTEST_
    #    REUSE.md) — CONSERVATIVE gate: only the plain path (no ML gate, no sizing
    #    overlay, no Monte-Carlo, caller doesn't want trades back) is eligible.
    #    Those overlays are lower-volume and/or harder to source a clean ctx for
    #    (a MC result is literally random — never cacheable), so per "when in
    #    doubt, miss" this just recomputes them every time, byte-identical to
    #    today. Off entirely unless AUGUR_TRIAL_CACHE is set. This SAME
    #    conservative gate also bounds PR4 (window_delta) below — a delta is
    #    never attempted for a request the scalar cache itself wouldn't touch. ──
    _cache_key = None
    _cache_ctx = None
    _pr4_gate = (TC.is_enabled() and not return_trades and mc_sims == 0
                and not sizing and not _gate_on)
    if _pr4_gate:
        _cache_ctx = TC.build_ctx(mod, arrays, cost_pts=cost_pts, session=session,
                                  date_from=date_from, date_to=date_to,
                                  ml_filter=ml_filter, ml_threshold=ml_threshold,
                                  ml_min_history=ml_min_history,
                                  ml_refit_every=ml_refit_every,
                                  sizing=sizing, master=master)
        if _cache_ctx is not None:
            try:
                _cache_key = TC.make_key(_cache_ctx, params)
                _hit = TC.get(_cache_key)
            except Exception:
                _cache_key, _hit = None, None
            if _hit is not None:
                TC.record_hit()
                return _hit
            if _cache_key is not None:
                TC.record_miss()

    # ── Window-extension delta (PR4, docs/INCREMENTAL_BACKTEST_REUSE.md §2(c))
    #    — only ever attempted after a PR1 scalar-cache MISS (an exact hit
    #    above already returned) and under the SAME conservative `_pr4_gate`,
    #    PLUS window_delta's own stricter internal gate (strategy's
    #    STATELESS_AT_EOD opt-in, cost_pts > 0 — see that module's docstring
    #    for why). try_extend() never raises and returns None the instant any
    #    precondition isn't cleanly met, so this is a pure no-op — byte-
    #    identical to today — for every strategy that hasn't opted in (i.e.
    #    every real strategy shipped so far). ──
    _gross_trades = None
    _delta_trades = None
    if _pr4_gate:
        try:
            _delta_trades = WD.try_extend(mod, arrays, params, cost_pts=cost_pts,
                                          session=session, date_from=date_from,
                                          date_to=date_to, master=master,
                                          ml_filter=ml_filter, ml_threshold=ml_threshold,
                                          ml_min_history=ml_min_history,
                                          ml_refit_every=ml_refit_every, sizing=sizing)
        except Exception:
            _delta_trades = None

    if _delta_trades is not None:
        # Same aggregation `_apply_costs` always uses — see this module's
        # docstring for why this makes delta-vs-full equality PROVABLE rather
        # than merely likely.
        res = _apply_costs({"trades": _delta_trades}, cost_pts)
        _gross_trades = _delta_trades
    else:
        res = fn(O, H, L, C, **extras, **params, return_trades=want_trades)
        _gross_trades = res.get("trades") if isinstance(res, dict) else None
        if res and cost_pts > 0:
            res = _apply_costs(res, cost_pts)

    # ── ML trade gate (board 3A.2 / ROADMAP #25): gate AFTER costs (the model
    #    learns net wins), BEFORE Monte-Carlo (MC sizes the gated equity curve).
    #    Headline stats become the GATED run; the ungated originals ride along
    #    inside res["ml_gate"]["ungated"] for the before/after card.
    if _gate_on and isinstance(res, dict) and res.get("trades"):
        from .ml_gate import gate_trades
        g = gate_trades(arrays, res["trades"], model=str(ml_filter),
                        threshold=float(ml_threshold),
                        min_history=int(ml_min_history),
                        refit_every=int(ml_refit_every))
        if g:
            orig_trades = res["trades"]          # all trades, pre-gate (win+loss)
            res["trades"] = g["trades"]
            res.update(g["stats"])
            res["ml_gate"] = g["summary"]
            # SHAP-style feature attribution (board §5): which entry inputs the gate
            # keys on. Trains one as-of-now model on ALL completed trades. Best-effort.
            try:
                from .ml_gate import gate_explain
                ex = gate_explain(arrays, orig_trades, model=str(ml_filter),
                                  min_history=int(ml_min_history))
                if ex:
                    res["ml_gate"]["explain"] = ex
            except Exception:
                pass
            # Gate calibration (board 3A): is the gate's P(win) a trustworthy probability,
            # and does a higher score mean higher expectancy? Best-effort (5-fold refit).
            try:
                from .ml_gate import gate_calibration
                cal = gate_calibration(arrays, orig_trades, model=str(ml_filter),
                                       min_history=int(ml_min_history),
                                       threshold=float(ml_threshold))
                if cal:
                    res["ml_gate"]["calibration"] = cal
            except Exception:
                pass

    # ── Sizing overlay (opt-in, ORB-family): attach a sized-vs-baseline comparison to
    #    res["sizing"] WITHOUT touching the headline 1-contract metrics. Needs the
    #    strategy's per-trade risk model (stop_frac × opening-range width), so it is
    #    gated on stop_frac/or_bars. `sizing` = a dict of augur_engine.sizing rule
    #    kwargs (risk_parity / time_tilt / long_w / short_w) + mult / fee_pts / cap_final.
    #    See ORB.md §4.7-4.11 + tools/orb_edge_report.py. Best-effort: never breaks a run.
    if sizing and isinstance(res, dict):
        try:
            from . import sizing as _SZ
            sp2 = dict(sizing)
            _stopf = sp2.pop("stop_frac", params.get("stop_frac"))
            _orb   = sp2.pop("or_bars", params.get("or_bars"))
            _mult  = float(sp2.pop("mult", 1.0))
            _fee   = float(sp2.pop("fee_pts", cost_pts))
            _cap   = sp2.pop("cap_final", None)
            if _stopf and _orb:
                _gross = fn(O, H, L, C, **extras, **params, return_trades=True)   # gross trades (fees applied per-size below)
                _gtr = _gross.get("trades") if isinstance(_gross, dict) else None
                if _gtr:
                    _p, _r, _eb, _sd = _SZ.trade_features(_gtr, arrays, float(_stopf), int(_orb))
                    _base = _SZ.sized_metrics(_p, _r, _SZ.sizing_weights(_r, _eb, _sd, risk_parity=False),
                                              mult=_mult, fee_pts=_fee)
                    _over = _SZ.sized_metrics(_p, _r, _SZ.sizing_weights(_r, _eb, _sd, **sp2),
                                              mult=_mult, fee_pts=_fee, cap_final=_cap)
                    if _base and _over:
                        _base.pop("equity_usd", None); _over.pop("equity_usd", None)
                        res["sizing"] = {"baseline": _base, "sized": _over, "rule": sp2,
                                         "mult": _mult, "fee_pts": _fee}
        except Exception:
            pass

    if isinstance(res, dict):
        if mc_sims and res.get("trades"):
            res["mc"] = monte_carlo_drawdown([t[2] for t in res["trades"]],
                                             n_sims=int(mc_sims), block=int(mc_block))
        if not return_trades:
            res.pop("trades", None)
        res["_meta"] = {
            "strategy": getattr(mod, "STRATEGY_NAME", None),
            "master": (arrays.get("meta") or {}).get("name"),
            "bars": int(len(C)),
            "cost_pts": float(cost_pts),
        }
        # `res` is trades-free here whenever _cache_key was set (that branch only
        # ever fires when not return_trades, and the pop() two lines up already
        # ran) — safe to store as-is; a write failure never surfaces as a
        # computation error (the backtest itself already succeeded).
        if _cache_key is not None and _cache_ctx is not None:
            try:
                TC.put(_cache_key, res, strategy_file_sha=_cache_ctx["strategy_file_sha"],
                      master_id=_cache_ctx["master_id"], engine_epoch=_cache_ctx["engine_epoch"])
            except Exception:
                pass
        # PR4 (window_delta): persist this FULL window's gross trades — whether
        # they came from a from-scratch compute or were just built by a delta
        # extension — so a LATER, larger date_to can extend from THIS window.
        # Uses `_gross_trades` (captured before `_apply_costs` ran / the trades
        # a successful delta already assembled), never `res["trades"]` (already
        # popped above whenever not return_trades). Best-effort, gated
        # identically to the read side (window_delta._eligible) — a genuine
        # no-op for every strategy that hasn't opted into STATELESS_AT_EOD.
        if _pr4_gate and _gross_trades:
            try:
                WD.record_full(mod, arrays, params, cost_pts=cost_pts, session=session,
                               date_from=date_from, date_to=date_to, master=master,
                               ml_filter=ml_filter, ml_threshold=ml_threshold,
                               ml_min_history=ml_min_history, ml_refit_every=ml_refit_every,
                               sizing=sizing, gross_trades=_gross_trades)
            except Exception:
                pass
    return res


def run_gate_validate(strategy, *, instrument=None, timeframe="5m", session="rth",
                      source=None, params=None, master=None, arrays=None,
                      cost_pts=0.0, date_from=None, date_to=None,
                      gates=("logistic", "rf", "xgb"),
                      thresholds=(0.50, 0.55, 0.60), lockbox_months=12,
                      progress_cb=None):
    """The honest gate bake-off (board 4.10, ROADMAP #25): run the strategy ONCE
    (fixed params), then rank every gate x cut-off candidate on the PRE-LOCKBOX
    slice only, and give the single winner ONE look at the lockbox. Losing
    candidates' lockbox numbers never leave ml_gate.gate_validate — no shopping.
    """
    from .ml_gate import gate_validate as _gv
    mod = strategy if hasattr(strategy, "run_backtest") else load_strategy(strategy)
    if arrays is None:
        if master is None:
            master = find_master(instrument, timeframe, session, source)
            if master is None:
                raise ValueError(
                    f"no master for instrument={instrument} timeframe={timeframe} "
                    f"session={session} source={source}")
        arrays = load_master_arrays(master, date_from=date_from, date_to=date_to)
    if progress_cb:
        progress_cb(5, 100)                       # runner cb signature: (done, total)
    base = run_backtest(mod, arrays=arrays, params=params, cost_pts=cost_pts,
                        return_trades=True)
    if not (isinstance(base, dict) and base.get("trades")):
        return None
    if progress_cb:
        progress_cb(15, 100)
    gv = _gv(arrays, base["trades"], gates=tuple(gates),
             thresholds=tuple(thresholds), lockbox_months=int(lockbox_months))
    if progress_cb:
        progress_cb(95, 100)
    res = {k: v for k, v in base.items() if k != "trades"}
    res["gate_validate"] = gv
    res["_meta"] = {
        "strategy": getattr(mod, "STRATEGY_NAME", None),
        "master": (arrays.get("meta") or {}).get("name"),
        "bars": int(len(arrays["close"])), "cost_pts": float(cost_pts),
    }
    return res


def run_ensemble_topk(strategy, *, instrument=None, timeframe="5m", session="rth",
                      source=None, preset=None, grid=None, master=None, arrays=None,
                      cost_pts=0.0, date_from=None, date_to=None, k=5, top_n=12,
                      min_trades=30, rank_by="total_pnl", workers=1, progress_cb=None):
    """Ensemble top-K (board §6, Carl §7.1): sweep the grid, then — instead of
    crowning the single best config — BLEND the top-K equal-weight and compare the
    blend to the rank-1 config by recovery factor. A blend that dips less often is
    more robust to the winner being a lucky spike; the trade-off is a bit less raw $.
    """
    from .optimize import run_grid
    mod = strategy if hasattr(strategy, "run_backtest") else load_strategy(strategy)
    if arrays is None:
        if master is None:
            master = find_master(instrument, timeframe, session, source)
            if master is None:
                raise ValueError(
                    f"no master for instrument={instrument} timeframe={timeframe} "
                    f"session={session} source={source}")
        arrays = load_master_arrays(master, date_from=date_from, date_to=date_to)
    gr = run_grid(mod, arrays=arrays, preset=preset, grid=grid, cost_pts=cost_pts,
                  min_trades=int(min_trades), top_n=max(int(top_n), int(k)),
                  rank_by=rank_by, workers=int(workers), progress_cb=progress_cb,
                  compute_ensemble=True, ensemble_k=int(k))
    ens = gr.get("ensemble")
    if not ens:
        return None
    return {"ensemble": ens, "best_params": gr.get("best_params"),
            "sweep": {"n_combos": gr.get("n_combos"), "n_valid": gr.get("n_valid"),
                      "top": gr.get("top")},
            "_meta": {"strategy": getattr(mod, "STRATEGY_NAME", None),
                      "master": (arrays.get("meta") or {}).get("name"),
                      "bars": int(len(arrays["close"])), "cost_pts": float(cost_pts)}}
