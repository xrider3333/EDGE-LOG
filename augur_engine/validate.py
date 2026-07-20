"""Auto-Validate pipeline — one call runs the canonical validation sequence on a fresh
strategy and returns a report card + verdict. Pure orchestration over the existing
run_auto / run_backtest engine calls (no new backtest logic).

Sequence (all on data BEFORE the reserved lockbox, so the holdout is never seen):
  A. In-sample Auto-Optimize (single 75/25 split)  -> champion params, trades/param, DSR.
  B. Rolling walk-forward                           -> walk-forward efficiency + consistency.
  A.5 (opt-in, #88) OOS-checked champion selection  -> re-crown the IS-max champion by
      walk-forward-fold OOS PnL among the top-K IS candidates, when select_oos_topk>=2.
  C. Lockbox one-shot                               -> (crowned) champion re-tested on the
      reserved slice.
Then a PASS / WEAK / FAIL verdict against professional thresholds.
"""
import datetime as _dt

from .data import find_master, load_master_arrays
from .engine import run_backtest
from .auto import (run_auto, _is_real as _sel_is_real, _METRIC_KEYS as _SEL_METRIC_KEYS,
                   make_slice_evaluator, score_candidates_on_folds)
from .optimize import run_grid
from .analytics import probability_backtest_overfitting, equity_curve_from_pnls


def _parse(d):
    try:
        return _dt.date.fromisoformat(str(d)[:10])
    except Exception:
        return None


def _sharpe_from_trades(trades, years):
    """Annualized Sharpe from a per-trade NET-PnL series. The trades come from run_backtest,
    which has ALREADY subtracted cost_pts (t[2] is net) — do NOT subtract cost again here, or
    Sharpe double-counts fees. Returns None when there aren't enough trades / no span."""
    pnls = [float(t[2]) for t in (trades or [])]
    n = len(pnls)
    if n < 3 or not years or years <= 0:
        return None
    mean = sum(pnls) / n
    sd = (sum((p - mean) ** 2 for p in pnls) / n) ** 0.5
    if sd <= 0:
        return None
    return (mean / sd) * ((n / years) ** 0.5)


def _sortino_from_trades(trades, years):
    """Annualized Sortino — like Sharpe but the denominator counts only DOWNSIDE (below-zero)
    dispersion. Trades are already net of cost (run_backtest applied cost_pts) — no re-subtract."""
    pnls = [float(t[2]) for t in (trades or [])]
    n = len(pnls)
    if n < 3 or not years or years <= 0:
        return None
    mean = sum(pnls) / n
    dd = (sum(min(0.0, p) ** 2 for p in pnls) / n) ** 0.5
    if dd <= 0:
        return None
    return (mean / dd) * ((n / years) ** 0.5)


def _avg_wl(trades):
    """Avg win / avg loss in POINTS (net of cost) from a per-trade NET-PnL series. Trades are
    already net (run_backtest applied cost_pts) — do NOT subtract cost again. avg_loss is a
    POSITIVE magnitude. Returns (None, None) when there are no wins / losses."""
    pnls = [float(t[2]) for t in (trades or [])]
    wins = [p for p in pnls if p > 0]
    losses = [-p for p in pnls if p < 0]
    aw = (sum(wins) / len(wins)) if wins else None
    al = (sum(losses) / len(losses)) if losses else None
    return aw, al


def _select_oos_champion(strategy, arrays, champ, bestA, A, wf_anch, cost_pts=0.0, k=5):
    """#88 OOS-checked champion selection (owner-approved 2026-07-20). Motivating
    evidence: run #167 crowned the sharpest realism-gated IN-SAMPLE config (IS
    $257,873) which then collapsed on the lockbox ($35,083, PBO gate fired, verdict
    WEAK) -- while run #165's WEAKER-IS champion had DOUBLE the lockbox PnL. A
    stronger search (steering / auto-expand) sharpens the IS optimum and widens the
    IS -> OOS gap; picking purely on IS PnL rewards exactly that overfit.

    Builds a candidate set of up to `k` distinct configs -- the realism-gated top of
    `A["top"]` (deduped by full param signature) plus `A["plateau_pick"]["params"]`
    when it's a distinct config (a reserved slot, backfilled from the ranked list if
    the plateau pick turns out to duplicate one already included) -- then scores each
    candidate's FIXED params on the SAME anchored walk-forward fold test slices
    `wf_anch` already ran (`score_candidates_on_folds`/`make_slice_evaluator` -- no
    re-optimization per fold, no duplicated kwarg-detection logic). The candidate with
    the highest summed fold-OOS PnL is crowned (ties: more folds held OOS-PF>1, then
    higher IS PnL) -- it becomes the new champion for everything downstream in
    validate.py (lockbox, transfer, KPIs, verdict); the lockbox itself is untouched
    here and still gets exactly ONE look, at whichever config this function returns.

    `arrays` MUST be the OPTIMIZE-WINDOW arrays (opt_from..opt_to, the same window
    Stage A/B already searched) -- fold bar-indices line up against it, and each
    candidate's equity curve is built ONLY over this window (never the lockbox slice).
    `wf_anch` is a walk-forward run_auto() result (method="walkforward", wf_mode=
    "anchored") -- its fold rows carry train_bars/test_bars, from which the anchored
    test-slice bounds are derived (test_start == train_bars, since anchored mode's
    train window always starts at bar 0).

    Returns (champ, bestA, selection) -- `champ`/`bestA` are the ORIGINAL inputs,
    UNCHANGED, whenever there is nothing to select from (no realism-gated candidates,
    or no anchored walk-forward folds available) or when the IS-max candidate itself
    wins the race; `selection` is always a dict:
      {"mode": "wf_oos_topk", "k": int, "is_max_crowned": bool,
       "candidates": [{"params", "is_pnl", "wf_oos_pnl", "folds_held", "crowned",
                       "equity": {"cum": [...], "final": pts}}, ...],
       "error": str}   (# "error" present only on the empty/no-fold no-op path)
    This function does not itself guard against a genuine backtest/strategy failure
    escaping make_slice_evaluator/run_backtest (those already swallow their own
    exceptions) -- an unexpected exception here is a real bug and is left to
    propagate; run_validate's own call site wraps this in a try/except and falls back
    to the untouched IS-max champion with `selection["error"]` set, per #88's hard
    rule that a selection-stage failure must never break Auto-Validate."""
    pkeys = list(champ.keys())

    def _sig(p):
        return tuple(sorted((kk, p.get(kk)) for kk in pkeys))

    top_rows = A.get("top") or []
    nb_bars = int(A.get("bars") or 0) or 10 ** 9
    gated_rows = [r for r in top_rows if _sel_is_real(r, nb_bars)] or list(top_rows)

    ppick = A.get("plateau_pick") or {}
    pp_params = ({kk: ppick["params"].get(kk) for kk in pkeys} if ppick.get("params") else None)
    pp_metrics = ({kk: ppick["metrics"].get(kk) for kk in _SEL_METRIC_KEYS if kk in ppick["metrics"]}
                  if ppick.get("metrics") else {})

    cands = []
    sigs = set()
    budget = (int(k) - 1) if pp_params else int(k)

    def _add(row_params, row_metrics, is_pnl):
        sig = _sig(row_params)
        if sig in sigs:
            return
        sigs.add(sig)
        cands.append({"params": row_params, "is_pnl": float(is_pnl or 0), "metrics": row_metrics})

    for row in gated_rows:
        if len(cands) >= budget:
            break
        _add({kk: row.get(kk) for kk in pkeys},
             {kk: row.get(kk) for kk in _SEL_METRIC_KEYS if kk in row},
             row.get("total_pnl", 0))
    if pp_params and len(cands) < int(k):
        _add(pp_params, pp_metrics, pp_metrics.get("total_pnl", 0))
    if len(cands) < int(k):   # plateau pick was a dup (or absent) -- backfill from the ranked list
        for row in gated_rows:
            if len(cands) >= int(k):
                break
            _add({kk: row.get(kk) for kk in pkeys},
                 {kk: row.get(kk) for kk in _SEL_METRIC_KEYS if kk in row},
                 row.get("total_pnl", 0))

    fold_bounds = []
    if wf_anch and wf_anch.get("ran"):
        for fr in (wf_anch.get("folds") or []):
            tb = int(fr.get("train_bars") or 0)
            te = int(fr.get("test_bars") or 0)
            if te > 0:
                fold_bounds.append((tb, tb + te))

    if not cands or not fold_bounds:
        return champ, bestA, {
            "mode": "wf_oos_topk", "k": int(k), "candidates": [], "is_max_crowned": True,
            "error": ("no realism-gated candidates" if not cands
                      else "no anchored walk-forward folds available"),
        }

    fold_scores = score_candidates_on_folds(strategy, arrays, [c["params"] for c in cands],
                                            fold_bounds, cost_pts=cost_pts)
    for c, rows in zip(cands, fold_scores):
        c["wf_oos_pnl"] = sum(r["oos_pnl"] for r in rows)
        c["folds_held"] = sum(1 for r in rows if r["held"])

    n_bars = len(arrays["close"])
    ev = make_slice_evaluator(strategy, arrays, cost_pts)
    for c in cands:
        m = ev(0, n_bars, c["params"], keep_trades=True)
        pnls = [float(t[2]) for t in (m.get("trades") or [])] if m else []
        c["equity"] = equity_curve_from_pnls(pnls, cap=160)

    orig_sig = _sig(champ)
    winner = max(cands, key=lambda c: (c.get("wf_oos_pnl", 0.0), c.get("folds_held", 0),
                                       c.get("is_pnl", 0.0)))
    is_max_crowned = (_sig(winner["params"]) == orig_sig)
    for c in cands:
        c["crowned"] = (c is winner)

    selection = {
        "mode": "wf_oos_topk", "k": int(k),
        "candidates": [{"params": dict(c["params"]), "is_pnl": round(float(c["is_pnl"]), 1),
                        "wf_oos_pnl": round(float(c.get("wf_oos_pnl", 0.0)), 1),
                        "folds_held": int(c.get("folds_held", 0)),
                        "crowned": bool(c.get("crowned", False)),
                        "equity": c.get("equity")} for c in cands],
        "is_max_crowned": is_max_crowned,
    }
    return dict(winner["params"]), dict(winner.get("metrics") or {}), selection


def run_validate(strategy, *, instrument=None, timeframe="5m", session="rth", source=None,
                 cost_pts=0.0, min_trades=30, n_trials=200, wf_folds=0, seed=42,
                 lockbox_months=12, date_from=None, date_to=None, progress_cb=None,
                 thresholds=None, transfer_to=None, equity_points=400,
                 discover="auto", provider="ollama", api_key=None, ai_rounds=4, save_dir=None,
                 select_oos_topk=0):
    th = {"trades_per_param": 30, "wfe": 0.5, "fold_frac": 0.66, "dsr": 0.8}
    th.update(thresholds or {})

    # ── resolve the data window + lockbox cutoff ──────────────────────────────
    master = find_master(instrument, timeframe, session, source)
    if master is None:
        raise ValueError(f"no master for {instrument} {timeframe} {session} {source}")
    full_lo = _parse(date_from) or _parse(master.get("date_from"))
    full_hi = _parse(date_to) or _parse(master.get("date_to"))
    if not full_hi:
        raise ValueError("could not determine data end date for the lockbox")
    lb_start = full_hi - _dt.timedelta(days=int(lockbox_months * 30.44))
    if full_lo and lb_start <= full_lo:
        raise ValueError("not enough history before the lockbox window — widen the data "
                         "range or shrink the lockbox months")
    opt_to = (lb_start - _dt.timedelta(days=1)).isoformat()   # optimization stops before lockbox
    lb_from = lb_start.isoformat()
    opt_from = full_lo.isoformat() if full_lo else None

    def _stage(lo, hi):
        def cb(done, total):
            if progress_cb and total:
                progress_cb(int(lo + (hi - lo) * done / total), 100)
        return cb

    # ── Stage 0 (optional) — AI-evolve the strategy CODE on the pre-lockbox window,
    #    then validate the evolved strategy. The lockbox is never seen by the rewrite. ──
    evolved_file = None
    discover_err = None
    if str(discover) == "evolve":
        try:
            from .ai import ai_evolve
            ev = ai_evolve(strategy, instrument=instrument, timeframe=timeframe,
                           session=session, source=source, n_rounds=ai_rounds,
                           provider=provider, api_key=api_key, cost_pts=cost_pts,
                           min_trades=min_trades, date_from=opt_from, date_to=opt_to,
                           save_dir=save_dir, progress_cb=_stage(0, 30)) or {}
            evolved_file = ev.get("evolved_file")
            if evolved_file:
                strategy = evolved_file   # judge the evolved strategy from here on
        except Exception as e:
            discover_err = f"{type(e).__name__}: {e}"   # fall back to the original strategy
    aS, aE, bS, bE = (30, 55, 55, 90) if evolved_file else (0, 40, 40, 90)

    # ── Stage A — in-sample Auto-Optimize (single 75/25 split) ────────────────
    A = run_auto(strategy, instrument=instrument, timeframe=timeframe, session=session,
                 source=source, method="single", oos=True, n_trials=n_trials,
                 cost_pts=cost_pts, min_trades=min_trades, top_n=24, seed=seed,
                 compute_dsr=True, compute_neighbors=True, compute_regime=True, mc_sims=500,
                 compute_surrogate=True,   # #31 P1: multi-surrogate bake-off on the sampled configs
                 # #36 P2: GP-steered sampling ON for Auto-Validate — the pre-registered
                 # 2-family acceptance bar was met 2026-07-19: TTIBS A/B steered found a
                 # +8.6% better IS optimum at equal budget, ORB 3.1 A/B +66% (both 150
                 # trials, seed 42, lockbox held out, 0 GP fallbacks). run_auto's own
                 # default stays False (library neutrality); this call site is the opt-in.
                 auto_steer=True,
                 date_from=opt_from, date_to=opt_to, progress_cb=_stage(aS, aE)) or {}
    # #88 (2026-07-20): the SAME "library default off, production opts in at its one
    # call site" pattern as auto_steer above applies to `select_oos_topk` — this
    # run_validate signature's own default is 0/OFF (library neutrality, and what
    # the tests exercise directly); the production Auto-Validate job path
    # (api/runner.py's jtype=="validate" branch) is the one call site that passes
    # select_oos_topk=5, because run #167's IS-max champion (IS $257,873) collapsed
    # to a $35,083 lockbox (PBO gate fired, WEAK) while run #165's weaker-IS champion
    # had DOUBLE the lockbox PnL — see _select_oos_champion below (Stage A.5) for the
    # actual selection logic, which runs after Stage B once wf_anch's fold rows exist.
    champ = A.get("best_params") or {}
    bestA = A.get("best") or {}
    nparam = len(champ)
    is_trades = int(bestA.get("num_trades", 0) or 0)
    tpp = (is_trades / nparam) if nparam else 0.0
    dsr = A.get("dsr") or {}
    nb = A.get("neighborhood") or {}          # plateau check (param robustness)
    mc = A.get("mc") or {}                     # Monte-Carlo drawdown (sizing)
    eq_opt = list((A.get("equity") or {}).get("cum") or [])   # champion equity, optimize window (pts)

    # ── Stage B — walk-forward in BOTH windowing schemes ──────────────────────
    #    ROLLING = fixed-length in-sample window (re-optimizes on a constant recent slice);
    #    ANCHORED = expanding window (re-optimizes on ALL history up to each fold). We run
    #    both, report each, and drive the gate off the STRONGER scheme (higher fold
    #    consistency, then WFE) — the one you'd actually deploy. Ties -> rolling.
    def _run_wf(mode, c0, c1):
        Bm = run_auto(strategy, instrument=instrument, timeframe=timeframe, session=session,
                      source=source, method="walkforward", wf_mode=mode, oos=True,
                      wf_folds=wf_folds, n_trials=n_trials, cost_pts=cost_pts,
                      min_trades=min_trades, top_n=20, seed=seed,
                      date_from=opt_from, date_to=opt_to, progress_cb=_stage(c0, c1)) or {}
        ran = bool(Bm.get("wf"))
        fl = Bm.get("top") or []
        so = st = si = strn = hd = 0.0
        for r in fl:
            so += float(r.get("oos_pnl", 0) or 0); st += float(r.get("test_bars", 0) or 0)
            si += float(r.get("total_pnl", 0) or 0); strn += float(r.get("train_bars", 0) or 0)
            if float(r.get("oos_pf", 0) or 0) > 1:
                hd += 1
        nf = len(fl) if ran else 0
        return {"mode": mode, "ran": ran, "folds": fl, "n_folds": nf, "held": int(hd),
                "oos_net": so,
                "wfe": (((so / st) / (si / strn)) if (ran and st and strn and si) else 0.0),
                "fold_frac": ((hd / nf) if nf else 0.0)}

    _bmid = (bS + bE) // 2
    wf_roll = _run_wf("rolling", bS, _bmid)
    wf_anch = _run_wf("anchored", _bmid, bE)
    # primary = the stronger scheme (fold consistency, then WFE); ties -> rolling
    _prim = (wf_anch if (wf_anch["ran"] and
                         (wf_anch["fold_frac"], wf_anch["wfe"]) > (wf_roll["fold_frac"], wf_roll["wfe"]))
             else wf_roll)
    # the NON-selected scheme's folds ride along (compact rows) so the web 1C chart can
    # flip between the two windowing schemes for comparison.
    _altw = wf_roll if _prim is wf_anch else wf_anch
    _alt_folds = [{k: r.get(k) for k in ("fold", "total_pnl", "oos_pnl", "oos_pf",
                                         "train_bars", "test_bars") if k in r}
                  for r in (_altw.get("folds") or [])] if _altw.get("ran") else []
    wf_ran = _prim["ran"]; folds = _prim["folds"]; n_folds = _prim["n_folds"]
    held = _prim["held"]; wfe = _prim["wfe"]; fold_frac = _prim["fold_frac"]; sOos = _prim["oos_net"]
    _wf_compact = lambda w: {"mode": w["mode"], "ran": w["ran"], "wfe": round(w["wfe"], 3),
                             "held": w["held"], "n_folds": w["n_folds"],
                             "fold_frac": round(w["fold_frac"], 3), "oos_net": w["oos_net"]}

    # ── Stage A.5 — OOS-checked champion selection (#88, opt-in via select_oos_topk)
    #    Motivating evidence: run #167 crowned the sharpest realism-gated IN-SAMPLE
    #    config (IS $257,873) which collapsed on the lockbox ($35,083, PBO gate fired,
    #    verdict WEAK), while run #165's WEAKER-IS champion had DOUBLE the lockbox
    #    PnL. Re-crowns `champ`/`bestA` (used by EVERYTHING below — lockbox, transfer,
    #    full-window KPIs, gate bake-off, adversarial checks, verdict) by walk-forward
    #    fold OOS PnL among the top-K IS candidates, instead of the raw IS-max. The
    #    lockbox below still gets exactly ONE look, at whichever config comes out of
    #    this. `select_oos_topk` in (0, 1) skips this block entirely (today's
    #    behavior, byte-identical) — see _select_oos_champion's docstring for the
    #    candidate-set/scoring/crowning rules. Any failure here (bad fixture, a
    #    strategy that raises somewhere unexpected) is caught and falls back to the
    #    untouched IS-max champion, with the failure logged in selection["error"]
    #    rather than breaking the run — a selection-stage bug must never sink
    #    Auto-Validate. NOTE (known scope limit, flagged honestly): `dsr`/`nb`
    #    (deflated-Sharpe / neighborhood-plateau, both computed above from the
    #    ORIGINAL IS-max winner) are NOT re-run for the crowned candidate when it
    #    differs from IS-max — checks["plateau"]/checks["luck"]/is_sharpe describe the
    #    SEARCH's own robustness/luck profile, not literally the crowned config's own
    #    neighborhood/Sharpe. Every KPI that comes from a FRESH backtest on `champ`
    #    (lockbox, transfer, total_sharpe/win_rate/dd, gate_bakeoff, adversarial,
    #    conformal, causal, synthetic) automatically reflects the crowned candidate,
    #    since those calls all run AFTER this block reassigns `champ`.
    selection = None
    _select_k = int(select_oos_topk or 0)
    if _select_k >= 2 and champ:
        try:
            _arr_sel = load_master_arrays(master, date_from=opt_from, date_to=opt_to)
            champ, bestA, selection = _select_oos_champion(
                strategy, _arr_sel, champ, bestA, A, wf_anch, cost_pts=cost_pts, k=_select_k)
            is_trades = int(bestA.get("num_trades", 0) or 0)
            tpp = (is_trades / nparam) if nparam else 0.0
        except Exception as _sel_e:
            selection = {"mode": "wf_oos_topk", "k": _select_k, "candidates": [],
                        "is_max_crowned": True,
                        "error": f"{type(_sel_e).__name__}: {_sel_e}"}

    # ── Gate ──────────────────────────────────────────────────────────────────
    plateau_ran = bool(nb)
    checks = {
        "sample": tpp >= th["trades_per_param"],
        "plateau": (not plateau_ran) or nb.get("verdict") == "HIGH GROUND",
        "wfe": wf_ran and wfe >= th["wfe"],
        "consistency": wf_ran and fold_frac >= th["fold_frac"],
        "luck": (not dsr) or float(dsr.get("dsr", 1) or 1) >= th["dsr"],
    }
    # ── Stage C — lockbox one-shot (champion on the reserved slice) ───────────
    lb = None
    if champ:
        if progress_cb:
            progress_cb(92, 100)
        try:
            lb = run_backtest(strategy, instrument=instrument, timeframe=timeframe,
                              session=session, source=source, params=champ,
                              cost_pts=cost_pts, date_from=lb_from, date_to=None,
                              return_trades=True)
        except Exception:
            lb = None
    # extend the equity curve through the (never-optimized) lockbox slice
    lb_idx = len(eq_opt)
    equity = list(eq_opt)
    if lb and lb.get("trades"):
        s = eq_opt[-1] if eq_opt else 0.0
        for t in lb["trades"]:
            s += (float(t[2]) - cost_pts)
            equity.append(s)
    if len(equity) > 240:   # downsample for transport/plot
        step = len(equity) / 240.0
        lb_idx = int(lb_idx / step)
        equity = [equity[int(i * step)] for i in range(240)]
    lb_pnl = float((lb or {}).get("total_pnl", 0) or 0)
    lb_pf = float((lb or {}).get("profit_factor", 0) or 0)
    lb_trades = int((lb or {}).get("num_trades", 0) or 0)
    lb_pass = lb is not None and lb_pnl > 0 and lb_pf >= 1.0

    # ── LOCKBOX-slice distributions for the 1D/1G report tiles (owner: those charts should
    #    be viewable on the OUT-OF-SAMPLE slice, not just the whole run). win_dist = per-trade
    #    net PnLs of the lockbox backtest; mae_mfe re-derived over the lockbox window arrays. ──
    win_dist_lb = None
    mae_mfe_lb = None
    if lb and lb.get("trades"):
        try:
            win_dist_lb = [round(float(t[2]), 2) for t in lb["trades"]][:600]
            from .analytics import mae_mfe as _mmfe
            _lba = load_master_arrays(master, date_from=lb_from, date_to=None)
            mae_mfe_lb = _mmfe(lb["trades"], _lba["high"], _lba["low"])
        except Exception:
            pass

    # ── WALK-FORWARD out-of-sample distributions (1G/1H WF scope): concatenate the
    #    per-fold OOS trades of the PRIMARY (stronger) scheme — each fold's champion tested
    #    on its unseen window, so this is genuinely out-of-sample, walk-forward flavoured.
    #    Best-effort; then strip the heavy per-trade arrays off the fold rows we return so
    #    the saved doc stays light.
    win_dist_wf = None
    mae_mfe_wf = None
    try:
        _wf_pnls, _wf_mae, _wf_mfe, _wf_won = [], [], [], []
        for _fr in (folds or []):
            _wf_pnls += list(_fr.get("_oos_pnls") or [])
            _wf_mae += list(_fr.get("_oos_mae") or [])
            _wf_mfe += list(_fr.get("_oos_mfe") or [])
            _wf_won += list(_fr.get("_oos_won") or [])
        if _wf_pnls:
            win_dist_wf = [round(float(v), 2) for v in _wf_pnls][:600]
        if _wf_mae and _wf_mfe and len(_wf_mae) == len(_wf_mfe):
            mae_mfe_wf = {"mae": _wf_mae[:600], "mfe": _wf_mfe[:600],
                          "won": (_wf_won[:600] if len(_wf_won) == len(_wf_mae) else [])}
    except Exception:
        pass
    for _rowset in (folds, (_altw.get("folds") if isinstance(_altw, dict) else None)):
        for _fr in (_rowset or []):
            for _k in ("_oos_pnls", "_oos_mae", "_oos_mfe", "_oos_won"):
                _fr.pop(_k, None)

    # ── Per-trade Win% / Sharpe so the report's KPI matrix + Past-runs columns aren't blank.
    #    Lockbox stats come from the lockbox trades we already have; the WHOLE-RUN totals come
    #    from ONE champion backtest over the full window (incl. lockbox) with trades. ──
    lb_wr = (float(lb.get("win_rate", 0) or 0) if lb else None)
    lb_sharpe = _sharpe_from_trades((lb or {}).get("trades"),
                                    max(0.05, lockbox_months / 12.0))
    lb_sortino = _sortino_from_trades((lb or {}).get("trades"),
                                      max(0.05, lockbox_months / 12.0))
    lb_aw, lb_al = _avg_wl((lb or {}).get("trades"))   # honest avg win/loss (points, net)
    lb_dd = abs(float((lb or {}).get("max_drawdown", 0) or 0))   # lockbox max drawdown magnitude (points) → MAR
    total_wr = total_sharpe = total_trades = total_dd = total_sortino = None
    total_aw = total_al = None
    if champ:
        try:
            full = run_backtest(strategy, instrument=instrument, timeframe=timeframe,
                                session=session, source=source, params=champ, cost_pts=cost_pts,
                                date_from=opt_from, date_to=None, return_trades=True)
        except Exception:
            full = None
        if full:
            _yrs = max(0.1, ((full_hi - (full_lo or full_hi)).days) / 365.25)
            total_sharpe = _sharpe_from_trades(full.get("trades"), _yrs)
            total_sortino = _sortino_from_trades(full.get("trades"), _yrs)
            total_wr = float(full.get("win_rate", 0) or 0)
            total_trades = int(full.get("num_trades", 0) or 0)
            total_dd = float(full.get("max_drawdown", 0) or 0)
            total_aw, total_al = _avg_wl(full.get("trades"))   # honest avg win/loss (points, net)

            # ── Rebuild the 1A equity curve at a SINGLE UNIFORM resolution from the whole-window
            #    champion trades. Fixes the pre-lockbox-smooth / lockbox-jagged seam: the old curve
            #    spliced a 160-pt DECIMATED optimize segment (each dot = dozens of trades) onto a
            #    PER-TRADE lockbox segment, so the same variation looked flat pre-lockbox and choppy
            #    after. `full` spans the whole window and its trades are already NET, so accumulate
            #    directly (the old lockbox extension double-charged cost_pts). `equity_points` = the
            #    display-detail knob: same trades-per-dot everywhere, so both halves read consistently.
            _ft = full.get("trades") or []
            if _ft:
                _cum = []; _s = 0.0
                for _t in _ft:
                    _s += float(_t[2]); _cum.append(_s)
                _bnd = max(0, len(_cum) - int(lb_trades or 0))   # lockbox = the chronological tail
                _N = max(40, int(equity_points or 400))
                if len(_cum) > _N:
                    _stp = len(_cum) / _N
                    lb_idx = int(_bnd / _stp)
                    equity = [round(_cum[int(_i * _stp)], 1) for _i in range(_N)]
                else:
                    equity = [round(x, 1) for x in _cum]; lb_idx = _bnd

    # ── OVERALL champion behaviour for the distribution charts (1D trade-PnL, 1G MAE/MFE, 1I stress).
    #    Stage A's win_dist / mae_mfe / stress cover only the 75% in-sample tune slice; re-run the ONE
    #    champion over the ENTIRE window (in-sample + walk-forward span + lockbox) so those charts show
    #    how it actually trades. A 1-combo grid reuses the same analytics pipeline. Falls back to the
    #    in-sample values (below) if it fails, so a validate never breaks on this. ──
    OV = {}
    if champ:
        try:
            OV = run_grid(strategy, instrument=instrument, timeframe=timeframe, session=session,
                          source=source, grid={k: [v] for k, v in champ.items()},
                          cost_pts=cost_pts, min_trades=1, top_n=1,
                          compute_dsr=False, mc_sims=500, compute_regime=True,
                          date_from=opt_from, date_to=None) or {}
        except Exception:
            OV = {}

    # ── Cross-instrument transfer — re-test the CHAMPION (no re-optimization) on
    #    other instruments. Edge that only works where it was fit is a single-symbol
    #    artifact; surviving on a sibling (NQ↔ES) is structural evidence. ──────────
    tlist = (transfer_to if isinstance(transfer_to, (list, tuple))
             else ([transfer_to] if transfer_to else []))
    transfer = []
    for ti in tlist:
        if not ti or str(ti) == str(instrument):
            continue
        try:
            tb = run_backtest(strategy, instrument=ti, timeframe=timeframe, session=session,
                              source=source, params=champ, cost_pts=cost_pts,
                              date_from=opt_from, date_to=None)
        except Exception:
            tb = None
        if tb:
            tpnl = float(tb.get("total_pnl", 0) or 0)
            tpf = float(tb.get("profit_factor", 0) or 0)
            transfer.append({"inst": ti, "pnl": tpnl, "pf": tpf,
                             "trades": int(tb.get("num_trades", 0) or 0),
                             "pass": tpnl > 0 and tpf >= 1.0})
    if champ and tlist:
        checks["transfer"] = any(t["pass"] for t in transfer)

    # ── Gate bake-off + PBO — both re-run the champion / candidates on already-resolved data. ──
    #    GATE BAKE-OFF: ungated (take every trade) + logistic / RF / XGB gates × cut-offs, ranked
    #    on the pre-lockbox slice by recovery factor; the winner gets ONE lockbox look (losers'
    #    lockbox numbers never leave gate_validate — no lockbox-shopping). Tells us which of the
    #    four to deploy. PBO / CSCV: how often the in-sample-best of the top candidate configs
    #    lands below the OUT-OF-SAMPLE median — the overfit-of-SELECTION governor (complements DSR).
    gate_bakeoff = pbo = None
    _full_arr = None
    if champ:
        try:
            _full_arr = load_master_arrays(master, date_from=opt_from, date_to=None)
        except Exception:
            _full_arr = None
        if _full_arr is not None and isinstance(full, dict) and full.get("trades"):
            try:
                from .ml_gate import gate_validate as _gate_bakeoff_fn
                gate_bakeoff = _gate_bakeoff_fn(_full_arr, full["trades"],
                                                lockbox_months=lockbox_months)
            except Exception:
                gate_bakeoff = None
        try:
            import pandas as _pd
            from collections import defaultdict as _dd
            _pre_arr = load_master_arrays(master, date_from=opt_from, date_to=opt_to)
            _pidx = _pd.to_datetime(_pd.Series(_pre_arr.get("index")))
            _pn = len(_pidx)
            mats = []
            for row in (A.get("top") or [])[:24]:
                cfg = {k: row[k] for k in champ.keys() if k in row}
                if not cfg:
                    continue
                try:
                    _bt = run_backtest(strategy, arrays=_pre_arr, params=cfg,
                                       cost_pts=cost_pts, return_trades=True)
                except Exception:
                    continue
                mon = _dd(float)
                for t in (_bt.get("trades") or []):
                    ts = _pidx.iloc[min(int(t[0]), _pn - 1)]
                    mon[(ts.year, ts.month)] += float(t[2])   # already net of cost
                if mon:
                    mats.append(mon)
            allk = sorted(set().union(*[m.keys() for m in mats])) if mats else []
            if len(mats) >= 2 and len(allk) >= 4:
                perf = [[m.get(k, 0.0) for k in allk] for m in mats]
                pbo = probability_backtest_overfitting(perf)
        except Exception:
            pbo = None
    if pbo is not None:
        checks["pbo"] = (float(pbo.get("pbo", 1.0)) <= 0.5)   # overfit-of-selection gate

    # ── Adversarial validation (board §4): is the reserved lockbox a DIFFERENT regime
    #    than the training history? Trains a classifier to tell lockbox bars from
    #    pre-lockbox bars on market-state features — high AUC = regime drift, so the
    #    lockbox verdict is weaker evidence. INFORMATIONAL (not a gate; verdict unchanged). ──
    #    Also runs three more distribution-free robustness checks on the champion's
    #    whole-history trades: conformal PnL band (§4), causal entry test (§7), and a
    #    trading-day bootstrap (§8). All INFORMATIONAL — none changes the verdict.
    adversarial = conformal = causal = synthetic = leadlag = acf = vif = featsel = edgesig = tailfit = season = None
    try:
        from .ml_gate import (adversarial_validation, entry_features, gate_feature_select)
        from .analytics import (conformal_pnl_band, causal_entry_test,
                                synthetic_day_bootstrap, lead_lag, serial_dependence,
                                vif_collinearity, edge_significance, return_tailfit,
                                seasonality)
        _avarr = _full_arr if _full_arr is not None else load_master_arrays(
            master, date_from=opt_from, date_to=None)
        adversarial = adversarial_validation(_avarr, lb_start)
        acf = serial_dependence(_avarr)                       # §1 momentum vs mean-revert
        tailfit = return_tailfit(_avarr)                      # §1 fat-tail fit
        season = seasonality(_avarr)                          # §6 intraday/weekly seasonality
        _Xf, _nf = entry_features(_avarr)
        vif = vif_collinearity(_Xf, _nf)                      # §2 collinearity of inputs
        _ftr = full.get("trades") if (champ and isinstance(full, dict)) else None
        if _ftr:
            conformal = conformal_pnl_band([t[2] for t in _ftr])
            causal = causal_entry_test(_ftr, _avarr.get("close"), cost_pts=cost_pts)
            synthetic = synthetic_day_bootstrap(_ftr, _avarr.get("index"))
            featsel = gate_feature_select(_avarr, _ftr)       # §2 which inputs to keep
            edgesig = edge_significance([t[2] for t in _ftr]) # §4 is the edge significant?
        # cross-instrument lead-lag (board §7): does a sibling lead this instrument?
        _sib = (tlist[0] if tlist else
                {"NQ": "ES", "ES": "NQ", "MNQ": "MES", "MES": "MNQ"}.get(str(instrument).upper()))
        if _sib and str(_sib).upper() != str(instrument).upper():
            _sm = find_master(_sib, timeframe, session, source)
            if _sm:
                leadlag = lead_lag(_avarr, load_master_arrays(_sm),
                                   name_a=str(instrument), name_b=str(_sib))
    except Exception:
        pass

    # ── Advisory flags — shown in the checklist as context, but they do NOT hard-fail the
    #    verdict (regime drift / collinearity are caveats, not kill-switches; a gate not helping
    #    is fine — ungated is a valid deploy). The chosen gate + whether it held is headlined. ──
    flags = {}
    if gate_bakeoff is not None:
        _ch = gate_bakeoff.get("chosen")
        flags["gate"] = {
            "chosen": ((_ch.get("model") + "@" + str(int(round(_ch.get("threshold", 0) * 100))) + "%")
                       if _ch else "ungated"),
            "helped": bool((gate_bakeoff.get("lockbox") or {}).get("helped")),
            "earns_pre": bool(gate_bakeoff.get("gate_earns_pre")),
            "verdict": gate_bakeoff.get("verdict")}
    if isinstance(adversarial, dict) and adversarial.get("auc") is not None:
        flags["adversarial"] = {"pass": bool(adversarial["auc"] < 0.75),
                                "auc": adversarial["auc"], "verdict": adversarial.get("verdict")}
    if isinstance(vif, dict) and vif.get("n_high") is not None:
        flags["vif"] = {"pass": bool(vif["n_high"] == 0), "n_high": int(vif["n_high"]),
                        "verdict": vif.get("verdict")}

    n_pass = sum(1 for v in checks.values() if v)
    n_gates = len(checks)
    if progress_cb:
        progress_cb(100, 100)

    # ── Verdict ───────────────────────────────────────────────────────────────
    if n_pass == n_gates and lb_pass:
        verdict = "PASS"
    elif n_pass >= n_gates - 1 and lb_pass:
        verdict = "WEAK"
    else:
        verdict = "FAIL"

    report = {
        "verdict": verdict, "checks": checks, "n_pass": n_pass, "n_gates": n_gates,
        "discover": discover, "evolved_file": evolved_file, "discover_err": discover_err,
        "trades_per_param": round(tpp, 1), "n_params": nparam, "is_trades": is_trades,
        "plateau": ({"verdict": nb.get("verdict"), "good": nb.get("good"),
                     "tot": nb.get("tot")} if plateau_ran else None),
        "wfe": round(wfe, 3), "folds_held": int(held), "n_folds": n_folds, "wf_ran": wf_ran,
        "transfer": transfer,
        "dsr": (dsr.get("dsr") if dsr else None),
        "is_pf": float(bestA.get("profit_factor", 0) or 0),
        "is_dd": abs(float((bestA or {}).get("max_drawdown", 0) or 0)),   # in-sample champion max DD magnitude (points) → MAR
        "is_sharpe": (dsr.get("winner_sharpe") if dsr else None),
        "mc_p95": ((OV.get("mc") or mc or {}).get("p95")),   # whole-run Monte-Carlo P95 drawdown (sizing floor)
        "equity": equity, "lb_idx": lb_idx,   # PnL curve (points); lb_idx = lockbox boundary
        "total_sharpe": total_sharpe, "total_sortino": total_sortino, "total_win_rate": total_wr,
        "total_trades": total_trades, "total_dd": total_dd,   # whole-run champion (incl. lockbox)
        "total_avg_win": total_aw, "total_avg_loss": total_al,   # measured (points), not derived
        "lockbox": {"pnl": lb_pnl, "pf": lb_pf, "trades": lb_trades, "pass": lb_pass,
                    "win_rate": lb_wr, "sharpe": lb_sharpe, "sortino": lb_sortino, "dd": lb_dd,

                    "avg_win": lb_aw, "avg_loss": lb_al,   # measured from lockbox trades (points)
                    "from": lb_from, "to": full_hi.isoformat()},
        "windows": {"optimize": [opt_from, opt_to], "lockbox": [lb_from, full_hi.isoformat()],
                    "lockbox_months": lockbox_months},
        "adversarial": adversarial,   # §4: is the lockbox a different regime? (context)
        "conformal": conformal,       # §4: distribution-free per-trade PnL band + coverage
        "causal": causal,             # §7: does entry timing beat random-entry nulls?
        "synthetic": synthetic,       # §8: PnL spread across a trading-day bootstrap
        "lead_lag": leadlag,          # §7: does a sibling instrument lead this one?
        "acf": acf,                   # §1: serial dependence (momentum vs mean-revert)
        "vif": vif,                   # §2: collinearity of the entry features
        "feature_select": featsel,    # §2: which entry inputs a gate would keep
        "edge_sig": edgesig,          # §4: is the edge statistically significant?
        "tailfit": tailfit,           # §1: fat-tail fit of returns (Student-t df)
        "seasonality": season,        # §6: intraday / weekly seasonality
        "pbo": pbo,                   # CSCV Probability of Backtest Overfitting (selection risk)
        "gate_bakeoff": gate_bakeoff, # ungated + logistic/RF/XGB × cut-off bake-off (one lockbox look)
        "wf_rolling": _wf_compact(wf_roll), "wf_anchored": _wf_compact(wf_anch),
        "wf_best_mode": _prim["mode"],   # which windowing scheme was stronger (drove the gate)
        "flags": flags,               # advisory: gate choice · adversarial regime drift · VIF
        "champion": champ, "thresholds": th,
    }
    # Shape stays compatible with the Runs-history saver (best / top / dsr).
    return {
        "mode": "validate", "validate": report,
        "best_params": champ, "best": bestA, "top": folds,
        "dsr": (dsr or None), "n_combos": n_trials * 2, "n_valid": A.get("n_valid"),
        "bars": A.get("bars"), "wf": True, "best_oos_pnl": sOos, "evolved_file": evolved_file,
        "dist": A.get("dist"), "points": A.get("points"),   # config SEARCH space → stays in-sample
        "equity_top": A.get("equity_top"),
        # 1D / 1G / 1I: whole-run champion behaviour when available, else the in-sample slice.
        "stress": (OV.get("stress") or A.get("stress")),
        "mae_mfe": (OV.get("mae_mfe") or A.get("mae_mfe")),
        "win_dist": (OV.get("win_dist") or A.get("win_dist")),
        "champ_dist_scope": ("overall" if OV.get("win_dist") else "in-sample"),
        # lockbox-slice versions of 1D/1G (the report's scope dropdown flips between them)
        "win_dist_lb": win_dist_lb, "mae_mfe_lb": mae_mfe_lb,
        # walk-forward out-of-sample versions of 1G/1H (WF scope in the dropdown)
        "win_dist_wf": win_dist_wf, "mae_mfe_wf": mae_mfe_wf,
        # the NON-selected walk-forward scheme's folds (1C comparison toggle)
        "wf_alt_folds": _alt_folds, "wf_alt_mode": (_altw.get("mode") if _altw.get("ran") else None),
        # 1B monthly + 1F regime + §8 MC drawdown → whole-run champion when available, else in-sample.
        "mc": (OV.get("mc") or A.get("mc")), "regime": (OV.get("regime") or A.get("regime")),
        "neighborhood": A.get("neighborhood"),
        "relationship": A.get("relationship"),   # per-param Pearson / MI / PPS (#24)
        # plateau pick + boundary-peak flags (3C.1b): forwarded from Stage A so Auto-Validate
        # run docs also carry the truncated-search detection (was previously dropped here).
        "plateau_pick": A.get("plateau_pick"),
        # #31 P1 surrogate bake-off cards (per-model CV accuracy, ground-truthed picks,
        # interactions, knob screen) — forwarded from Stage A, IS-only by construction.
        "surrogate": A.get("surrogate"),
        "auto_expand": A.get("auto_expand"), "auto_expand_summary": A.get("auto_expand_summary"),
        "steering": A.get("steering"),   # #36 P2: seed/steered/fallback trial counts (badge in 2L)
        # top-level so the existing Robustness card renders the gate bake-off with no new UI.
        "gate_validate": gate_bakeoff,
        # #88: OOS-checked champion selection evidence trail — None when select_oos_topk
        # disabled (0/1); see _select_oos_champion's docstring for the schema.
        "selection": selection,
    }
