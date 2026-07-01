"""Auto-Validate pipeline — one call runs the canonical validation sequence on a fresh
strategy and returns a report card + verdict. Pure orchestration over the existing
run_auto / run_backtest engine calls (no new backtest logic).

Sequence (all on data BEFORE the reserved lockbox, so the holdout is never seen):
  A. In-sample Auto-Optimize (single 75/25 split)  -> champion params, trades/param, DSR.
  B. Rolling walk-forward                           -> walk-forward efficiency + consistency.
  C. Lockbox one-shot                               -> champion re-tested on the reserved slice.
Then a PASS / WEAK / FAIL verdict against professional thresholds.
"""
import datetime as _dt

from .data import find_master
from .engine import run_backtest
from .auto import run_auto
from .optimize import run_grid


def _parse(d):
    try:
        return _dt.date.fromisoformat(str(d)[:10])
    except Exception:
        return None


def _sharpe_from_trades(trades, cost, years):
    """Annualized Sharpe from a per-trade NET-PnL series (trade tuple's t[2] is gross points).
    Returns None when there aren't enough trades / no time span — so the caller can show '—'."""
    pnls = [float(t[2]) - cost for t in (trades or [])]
    n = len(pnls)
    if n < 3 or not years or years <= 0:
        return None
    mean = sum(pnls) / n
    sd = (sum((p - mean) ** 2 for p in pnls) / n) ** 0.5
    if sd <= 0:
        return None
    return (mean / sd) * ((n / years) ** 0.5)


def _avg_wl(trades, cost):
    """Avg win / avg loss in POINTS (fees included) from a per-trade NET-PnL series
    (trade tuple's t[2] is gross points). avg_loss is a POSITIVE magnitude. Returns
    (None, None) when there are no wins / losses — so the report shows '—' or falls back."""
    pnls = [float(t[2]) - cost for t in (trades or [])]
    wins = [p for p in pnls if p > 0]
    losses = [-p for p in pnls if p < 0]
    aw = (sum(wins) / len(wins)) if wins else None
    al = (sum(losses) / len(losses)) if losses else None
    return aw, al


def run_validate(strategy, *, instrument=None, timeframe="5m", session="rth", source=None,
                 cost_pts=0.0, min_trades=30, n_trials=200, wf_folds=0, seed=42,
                 lockbox_months=12, date_from=None, date_to=None, progress_cb=None,
                 thresholds=None, transfer_to=None,
                 discover="auto", provider="ollama", api_key=None, ai_rounds=4, save_dir=None):
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
                 cost_pts=cost_pts, min_trades=min_trades, top_n=10, seed=seed,
                 compute_dsr=True, compute_neighbors=True, compute_regime=True, mc_sims=500,
                 date_from=opt_from, date_to=opt_to, progress_cb=_stage(aS, aE)) or {}
    champ = A.get("best_params") or {}
    bestA = A.get("best") or {}
    nparam = len(champ)
    is_trades = int(bestA.get("num_trades", 0) or 0)
    tpp = (is_trades / nparam) if nparam else 0.0
    dsr = A.get("dsr") or {}
    nb = A.get("neighborhood") or {}          # plateau check (param robustness)
    mc = A.get("mc") or {}                     # Monte-Carlo drawdown (sizing)
    eq_opt = list((A.get("equity") or {}).get("cum") or [])   # champion equity, optimize window (pts)

    # ── Stage B — rolling walk-forward ────────────────────────────────────────
    B = run_auto(strategy, instrument=instrument, timeframe=timeframe, session=session,
                 source=source, method="walkforward", wf_mode="rolling", oos=True,
                 wf_folds=wf_folds, n_trials=n_trials, cost_pts=cost_pts,
                 min_trades=min_trades, top_n=20, seed=seed,
                 date_from=opt_from, date_to=opt_to, progress_cb=_stage(bS, bE)) or {}
    wf_ran = bool(B.get("wf"))
    folds = B.get("top") or []
    sOos = sTest = sIs = sTrain = held = 0.0
    for r in folds:
        sOos += float(r.get("oos_pnl", 0) or 0); sTest += float(r.get("test_bars", 0) or 0)
        sIs += float(r.get("total_pnl", 0) or 0); sTrain += float(r.get("train_bars", 0) or 0)
        if float(r.get("oos_pf", 0) or 0) > 1:
            held += 1
    wfe = ((sOos / sTest) / (sIs / sTrain)) if (wf_ran and sTest and sTrain and sIs) else 0.0
    n_folds = len(folds) if wf_ran else 0
    fold_frac = (held / n_folds) if n_folds else 0.0

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

    # ── Per-trade Win% / Sharpe so the report's KPI matrix + Past-runs columns aren't blank.
    #    Lockbox stats come from the lockbox trades we already have; the WHOLE-RUN totals come
    #    from ONE champion backtest over the full window (incl. lockbox) with trades. ──
    lb_wr = (float(lb.get("win_rate", 0) or 0) if lb else None)
    lb_sharpe = _sharpe_from_trades((lb or {}).get("trades"), cost_pts,
                                    max(0.05, lockbox_months / 12.0))
    lb_aw, lb_al = _avg_wl((lb or {}).get("trades"), cost_pts)   # honest avg win/loss (points)
    total_wr = total_sharpe = total_trades = total_dd = None
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
            total_sharpe = _sharpe_from_trades(full.get("trades"), cost_pts, _yrs)
            total_wr = float(full.get("win_rate", 0) or 0)
            total_trades = int(full.get("num_trades", 0) or 0)
            total_dd = float(full.get("max_drawdown", 0) or 0)
            total_aw, total_al = _avg_wl(full.get("trades"), cost_pts)   # honest avg win/loss (points)

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
        "is_sharpe": (dsr.get("winner_sharpe") if dsr else None),
        "mc_p95": ((OV.get("mc") or mc or {}).get("p95")),   # whole-run Monte-Carlo P95 drawdown (sizing floor)
        "equity": equity, "lb_idx": lb_idx,   # PnL curve (points); lb_idx = lockbox boundary
        "total_sharpe": total_sharpe, "total_win_rate": total_wr,
        "total_trades": total_trades, "total_dd": total_dd,   # whole-run champion (incl. lockbox)
        "total_avg_win": total_aw, "total_avg_loss": total_al,   # measured (points), not derived
        "lockbox": {"pnl": lb_pnl, "pf": lb_pf, "trades": lb_trades, "pass": lb_pass,
                    "win_rate": lb_wr, "sharpe": lb_sharpe,
                    "avg_win": lb_aw, "avg_loss": lb_al,   # measured from lockbox trades (points)
                    "from": lb_from, "to": full_hi.isoformat()},
        "windows": {"optimize": [opt_from, opt_to], "lockbox": [lb_from, full_hi.isoformat()],
                    "lockbox_months": lockbox_months},
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
        # 1B monthly + 1F regime + §8 MC drawdown → whole-run champion when available, else in-sample.
        "mc": (OV.get("mc") or A.get("mc")), "regime": (OV.get("regime") or A.get("regime")),
        "neighborhood": A.get("neighborhood"),
        "relationship": A.get("relationship"),   # per-param Pearson / MI / PPS (#24)
    }
