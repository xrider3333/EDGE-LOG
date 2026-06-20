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


def _parse(d):
    try:
        return _dt.date.fromisoformat(str(d)[:10])
    except Exception:
        return None


def run_validate(strategy, *, instrument=None, timeframe="5m", session="rth", source=None,
                 cost_pts=0.0, min_trades=30, n_trials=200, wf_folds=0, seed=42,
                 lockbox_months=12, date_from=None, date_to=None, progress_cb=None,
                 thresholds=None):
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

    # ── Stage A — in-sample Auto-Optimize (single 75/25 split) ────────────────
    A = run_auto(strategy, instrument=instrument, timeframe=timeframe, session=session,
                 source=source, method="single", oos=True, n_trials=n_trials,
                 cost_pts=cost_pts, min_trades=min_trades, top_n=10, seed=seed,
                 compute_dsr=True, date_from=opt_from, date_to=opt_to,
                 progress_cb=_stage(0, 40)) or {}
    champ = A.get("best_params") or {}
    bestA = A.get("best") or {}
    nparam = len(champ)
    is_trades = int(bestA.get("num_trades", 0) or 0)
    tpp = (is_trades / nparam) if nparam else 0.0
    dsr = A.get("dsr") or {}

    # ── Stage B — rolling walk-forward ────────────────────────────────────────
    B = run_auto(strategy, instrument=instrument, timeframe=timeframe, session=session,
                 source=source, method="walkforward", wf_mode="rolling", oos=True,
                 wf_folds=wf_folds, n_trials=n_trials, cost_pts=cost_pts,
                 min_trades=min_trades, top_n=20, seed=seed,
                 date_from=opt_from, date_to=opt_to, progress_cb=_stage(40, 90)) or {}
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
    checks = {
        "sample": tpp >= th["trades_per_param"],
        "wfe": wf_ran and wfe >= th["wfe"],
        "consistency": wf_ran and fold_frac >= th["fold_frac"],
        "luck": (not dsr) or float(dsr.get("dsr", 1) or 1) >= th["dsr"],
    }
    n_pass = sum(1 for v in checks.values() if v)

    # ── Stage C — lockbox one-shot (champion on the reserved slice) ───────────
    lb = None
    if champ:
        if progress_cb:
            progress_cb(92, 100)
        try:
            lb = run_backtest(strategy, instrument=instrument, timeframe=timeframe,
                              session=session, source=source, params=champ,
                              cost_pts=cost_pts, date_from=lb_from, date_to=None)
        except Exception:
            lb = None
    lb_pnl = float((lb or {}).get("total_pnl", 0) or 0)
    lb_pf = float((lb or {}).get("profit_factor", 0) or 0)
    lb_trades = int((lb or {}).get("num_trades", 0) or 0)
    lb_pass = lb is not None and lb_pnl > 0 and lb_pf >= 1.0
    if progress_cb:
        progress_cb(100, 100)

    # ── Verdict ───────────────────────────────────────────────────────────────
    if n_pass == 4 and lb_pass:
        verdict = "PASS"
    elif n_pass >= 3 and lb_pass:
        verdict = "WEAK"
    else:
        verdict = "FAIL"

    report = {
        "verdict": verdict, "checks": checks, "n_pass": n_pass,
        "trades_per_param": round(tpp, 1), "n_params": nparam, "is_trades": is_trades,
        "wfe": round(wfe, 3), "folds_held": int(held), "n_folds": n_folds, "wf_ran": wf_ran,
        "dsr": (dsr.get("dsr") if dsr else None),
        "lockbox": {"pnl": lb_pnl, "pf": lb_pf, "trades": lb_trades, "pass": lb_pass,
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
        "bars": A.get("bars"), "wf": True, "best_oos_pnl": sOos, "evolved_file": None,
    }
