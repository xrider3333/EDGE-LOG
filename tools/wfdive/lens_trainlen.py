"""wfdive lens: TRAIN-LENGTH sensitivity of walk-forward re-tuning (Q3: "could we
tune on less data?").

For each of the owner-starred crowns that actually walk-forward re-tunes
(#257 ORB_3_6_E1.py NQ 5m rth, #335 ENGUQ_1M_ETH_R2_1_0.py NQ 1m eth), this
calls the ENGINE'S OWN per-fold search function (augur_engine.auto._wf_fold_row
-- the exact function augur_engine.auto.run_auto's walk-forward branch and
augur_engine.wf_pool's parallel workers both call, never a hand-written copy,
per BACKTEST_SPEED.md rule 1) once per (fold, training-window variant), holding
the TEST slice (te_s, te_e) exactly as the run doc saved it and varying only the
TRAINING slice start (tr_start):

  T_all  -- anchored: tr_start = 0 (all history before the test slice)
  T_5y   -- last 5 CALENDAR years of bars before the test slice
  T_3y   -- last 3 calendar years
  T_2y   -- last 2 calendar years

A variant is SKIPPED (noted, not silently truncated) when its calendar lookback
would need bars before the optimize window's first bar.

Reproduction gate (must pass before any variant numbers are trusted): fold 1 of
each run, re-run with the run doc's OWN saved scheme (rolling for #335, anchored
for #257) and the run doc's OWN saved seed/n_trials/min_trades/cost_pts, must
reproduce that fold's saved champion params AND oos_pnl/oos_trades/oos_pf. If it
does not, the script stops and prints why instead of producing variant numbers.

n_trials/seed/min_trades were not saved directly on either run doc (Gather's
audit: 0/351 runs carry an n_trials field). They are derived here from fields
that ARE saved and are algebraically pinned to n_trials by validate.py's own
code (see DERIVATION comment below) -- not guessed -- and the reproduction gate
is exactly the check that this derivation was right.

Run from the worktree root:
    python tools/wfdive/lens_trainlen.py
Checkpoints after every (fold, variant) to _wfdive_data/lens_trainlen.json so a
partial run survives a cutoff.
"""
import copy
import json
import os
import sys
import time
import traceback

WORKTREE = r"C:\Users\xride\AppData\Local\EdgeLog-worktrees\wfdive"
if WORKTREE not in sys.path:
    sys.path.insert(0, WORKTREE)
os.chdir(WORKTREE)

from tools.wfdive.common import setup_data_env, low_priority, cpu_lock, DATA_DIR, load_runs  # noqa: E402

RESULTS_PATH = os.path.join(DATA_DIR, "lens_trainlen.json")
TRIAL_CACHE_DB = os.path.join(DATA_DIR, "trial_cache.db")

# ── speed knobs (BACKTEST_SPEED.md rule 2) — set BEFORE importing augur_engine ──
os.environ["AUGUR_TRIAL_CACHE"] = "1"
os.environ.setdefault("AUGUR_TRIAL_CACHE_DB", TRIAL_CACHE_DB)
os.environ["PYTHONIOENCODING"] = "utf-8"

low_priority()
setup_data_env()

import pandas as pd  # noqa: E402
from augur_engine.data import find_master, load_master_arrays  # noqa: E402
from augur_engine.strategies import load_strategy  # noqa: E402
from augur_engine.auto import (_wf_fold_row, make_slice_evaluator,  # noqa: E402
                                _auto_space_from_params)
from augur_engine import trial_cache as TC  # noqa: E402

WALL_DEADLINE_S = 75 * 60          # hard stop for THIS script's own work
FOLD_SEARCH_CAP_S = 10 * 60        # if one (fold,variant) search exceeds this, cut n_trials
START = time.time()


def elapsed():
    return time.time() - START


def remaining():
    return WALL_DEADLINE_S - elapsed()


# ── DERIVATION of n_trials/seed/min_trades (no field on the doc says these
#    directly — see module docstring) ────────────────────────────────────────
# validate.py line ~1411 saves the RUN DOC's top-level "n_combos": n_trials * 2
# (the SAME n_trials value run_validate threads into BOTH Stage A's run_auto call
# and every Stage-B _run_wf() call — one shared parameter, not two independent
# ones). #257's doc has n_combos=400 -> n_trials=200; #335's has n_combos=600 ->
# n_trials=300. Cross-check against Stage A's OWN "steering" block (auto.py
# run_auto, auto_steer path): steer_seed_frac defaults to 0.4, so
# n_seed = round(0.4 * n_trials), and steered_trials + fallback_random must sum
# to n_trials - n_seed. #257: steering={seed_trials:80, steered:0, fallback:120}
# -> 80+0+120=200=n_trials, and round(0.4*200)=80 ✓. #335: steering=
# {seed_trials:120, steered:180, fallback:0} -> 120+180+0=300=n_trials, and
# round(0.4*300)=120 ✓. Both independent derivations agree exactly.
# seed: run_validate's own default (42) — no other value is saved or implied
# anywhere on either doc; not falsifiable from saved fields, so used as-is.
# min_trades: run_validate's own default (30) — same situation.
RUN_CONFIGS = {
    "257": dict(
        run_id="257", strategy="ORB_3_6_E1.py", instrument="NQ", timeframe="5m",
        session="rth", source="db_noadj_rth", cost_pts=0.533,
        n_trials=200, seed=42, min_trades=30,
        wf_mode="anchored",  # validate.windows / doc: wf_best_mode
    ),
    "335": dict(
        run_id="335", strategy="ENGUQ_1M_ETH_R2_1_0.py", instrument="NQ", timeframe="1m",
        session="eth", source="db_noadj_eth", cost_pts=0.533,
        n_trials=300, seed=42, min_trades=30,
        wf_mode="rolling",
    ),
}

# fold order: last 4 first ("most informative first"), then the earlier 4 if time remains
FOLD_ORDER = [8, 7, 6, 5, 4, 3, 2, 1]
VARIANTS = ["T_all", "T_5y", "T_3y", "T_2y"]
VARIANT_YEARS = {"T_5y": 5, "T_3y": 3, "T_2y": 2}


def load_checkpoint():
    if os.path.isfile(RESULTS_PATH):
        with open(RESULTS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"meta": {}, "runs": {}}


def save_checkpoint(state):
    tmp = RESULTS_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, default=str)
    os.replace(tmp, RESULTS_PATH)


def get_saved_folds(run_id):
    """Pull this run's top10_results (the PRIMARY-scheme fold rows the engine
    itself saved) from the Gather agent's runs.json — never re-read Firestore."""
    runs = load_runs()
    for r in runs:
        if str(r.get("id")) == str(run_id):
            return r
    raise SystemExit(f"run {run_id} not found in runs.json")


def build_fold_specs_from_saved(saved_folds, n_total_bars):
    """Recompute (tr_start, tr_end, te_s, te_e) for every fold EXACTLY as
    run_auto's walk-forward branch derives fold_specs — but keyed off the
    SAVED train_bars/test_bars (n_folds=8 confirmed identical to the engine's
    own formula for both runs — see the arithmetic check in the session notes:
    for #257 anchored, tr_end_f = train_bars_f (tr_start always 0); for #335
    rolling, tr_start_f = tr_end_f - train_bars_f, and train_bars_f is constant
    across folds, matching init=int(n*0.40) exactly). This function derives the
    bar bounds purely from the doc's own saved train_bars/test_bars, so it can
    never drift from what the engine actually ran, regardless of exactly which
    wf_folds request produced n_folds=8."""
    specs = {}
    for row in saved_folds:
        f = int(row["fold"])
        specs[f] = {"test_bars": int(row["test_bars"]), "train_bars": int(row["train_bars"])}
    # te_s by contiguous accumulation: te_s(fold 1) = train_bars(fold 1) (true for
    # BOTH anchored [tr_start=0 always] and rolling [fold-1's tr_start = tr_end -
    # init = 0 too, since tr_end==init on fold 1]); te_s(fold f>1) = te_s(f-1) +
    # test_bars(f-1) (fold test slices are contiguous and non-overlapping).
    te_s = None
    for f in sorted(specs):
        if te_s is None:
            te_s = specs[f]["train_bars"]
        specs[f]["te_s"] = te_s
        te_s = te_s + specs[f]["test_bars"]
        specs[f]["te_e"] = te_s
    n_folds = len(specs)
    for f in specs:
        specs[f]["tr_end"] = specs[f]["te_s"]
        specs[f]["tr_start_saved"] = specs[f]["te_s"] - specs[f]["train_bars"]
        specs[f]["te_e"] = n_total_bars if f == n_folds else specs[f]["te_e"]
    return specs


def variant_tr_start(mode, index, te_s, n_years=None):
    """tr_start bar index for one training-window variant, given `index` (the
    optimize-window's DatetimeIndex) and te_s (fold's test-slice start bar,
    == tr_end for every variant — only the training START moves).
    Returns (tr_start, skip_reason)."""
    if mode == "T_all":
        return 0, None
    boundary_date = index[te_s - 1] if te_s > 0 else index[0]
    cutoff = boundary_date - pd.DateOffset(years=n_years)
    if cutoff < index[0]:
        return None, (f"{mode} needs data back to {cutoff.date()}, before the "
                       f"optimize window's first bar {index[0].date()}")
    tr_start = int(index.searchsorted(cutoff, side="left"))
    return tr_start, None


def run_one(cfg, mod, arrays, space, dp, pkeys, ev, f, tr_start, te_s, te_e):
    H, L, IDX = arrays["high"], arrays["low"], arrays.get("index")
    t0 = time.time()
    row = _wf_fold_row(ev, H, L, space, dp, pkeys, cfg["seed"], cfg["n_trials"],
                        cfg["min_trades"], cfg["cost_pts"], f - 1, tr_start, te_s,
                        te_s, te_e, index=IDX)
    dt = time.time() - t0
    return row, dt


def summarize_row(row, pkeys):
    if row is None:
        return None
    return {
        "params": {k: row.get(k) for k in pkeys},
        "oos_pnl": row.get("oos_pnl"), "oos_trades": row.get("oos_trades"),
        "oos_pf": row.get("oos_pf"), "oos_wins": row.get("oos_wins"),
        "oos_win_rate": row.get("oos_win_rate"),
        "is_total_pnl": row.get("total_pnl"), "is_trades": row.get("num_trades"),
        "is_pf": row.get("profit_factor"),
    }


def reproduce_check(run_id, cfg, mod, arrays, space, dp, pkeys, ev, specs, saved_folds_by_num):
    """Reproduce fold 1 with the SAVED scheme's own tr_start (not a variant) and
    compare params + oos figures to the doc. Returns (ok, detail_dict)."""
    f = 1
    sp = specs[f]
    tr_start_saved = sp["tr_start_saved"]
    te_s, te_e = sp["te_s"], sp["te_e"]
    print(f"[{run_id}] reproduction check: fold {f}, tr=({tr_start_saved},{te_s}) "
          f"te=({te_s},{te_e}), n_trials={cfg['n_trials']}, seed={cfg['seed']} ...")
    t0 = time.time()
    with cpu_lock(f"lens_trainlen repro #{run_id} fold{f}"):
        row, dt = run_one(cfg, mod, arrays, space, dp, pkeys, ev, f, tr_start_saved, te_s, te_e)
    print(f"[{run_id}] reproduction fold {f} took {dt:.1f}s")
    saved = saved_folds_by_num[f]
    detail = {"elapsed_s": dt, "reproduced_row": summarize_row(row, pkeys),
              "saved_row": {"params": {k: saved.get(k) for k in pkeys},
                            "oos_pnl": saved.get("oos_pnl"), "oos_trades": saved.get("oos_trades"),
                            "oos_pf": saved.get("oos_pf")}}
    if row is None:
        detail["ok"] = False
        detail["reason"] = "no trial cleared min_trades on the training window"
        return False, detail, dt
    params_match = all(row.get(k) == saved.get(k) for k in pkeys)
    pnl_close = abs(float(row.get("oos_pnl", 0)) - float(saved.get("oos_pnl", 0))) < 1e-3
    trades_match = int(row.get("oos_trades", -1)) == int(saved.get("oos_trades", -2))
    pf_close = abs(float(row.get("oos_pf", 0)) - float(saved.get("oos_pf", 0))) < 1e-3
    ok = params_match and pnl_close and trades_match and pf_close
    detail["ok"] = ok
    detail["params_match"] = params_match
    detail["pnl_close"] = pnl_close
    detail["trades_match"] = trades_match
    detail["pf_close"] = pf_close
    return ok, detail, dt


def process_run(run_id, state):
    cfg = RUN_CONFIGS[run_id]
    doc = get_saved_folds(run_id)
    saved_folds = doc.get("top10_results") or []
    saved_folds_by_num = {int(r["fold"]): r for r in saved_folds}
    windows = (doc.get("validate") or {}).get("windows") or {}
    opt_from, opt_to = windows.get("optimize") or [None, None]
    print(f"\n===== run #{run_id} ({cfg['strategy']}, {cfg['instrument']} {cfg['timeframe']} "
          f"{cfg['session']}) optimize window {opt_from}..{opt_to} =====")

    master = find_master(cfg["instrument"], cfg["timeframe"], cfg["session"], cfg["source"])
    if master is None:
        raise SystemExit(f"no master for {cfg}")
    arrays = load_master_arrays(master, date_from=opt_from, date_to=opt_to)
    n = len(arrays["close"])
    index = arrays.get("index")
    print(f"[{run_id}] loaded {n} bars, index {index[0]}..{index[-1]}" if index is not None
          else f"[{run_id}] loaded {n} bars (no index)")

    mod = load_strategy(cfg["strategy"])
    dp = getattr(mod, "DEFAULT_PARAMS", {}) or {}
    space = _auto_space_from_params(dp)
    pkeys = list(space.keys())
    n_free = sum(1 for k, spec in space.items()
                 if not (spec[0] == "cat" and len(spec[1]) <= 1)
                 and not (spec[0] in ("int", "float") and spec[1] == spec[2]))
    print(f"[{run_id}] search space: {len(pkeys)} params, {n_free} with a non-degenerate range")

    cache_ctx = None
    if TC.is_enabled():
        cache_ctx = TC.build_ctx(mod, arrays, cost_pts=cfg["cost_pts"], session=cfg["session"],
                                  date_from=opt_from, date_to=opt_to, master=master)
    ev = make_slice_evaluator(mod, arrays, cfg["cost_pts"], cache_ctx=cache_ctx)

    specs = build_fold_specs_from_saved(saved_folds, n)

    run_state = state["runs"].setdefault(run_id, {
        "config": cfg, "n_bars": n, "n_free_params": n_free,
        "opt_from": opt_from, "opt_to": opt_to, "fold_specs": specs,
        "reproduction": None, "folds": {}, "skipped_variants": {},
    })
    run_state["n_bars"] = n
    run_state["n_free_params"] = n_free
    run_state["fold_specs"] = specs

    # ── reproduction gate ──────────────────────────────────────────────────
    if run_state.get("reproduction") is None or not run_state["reproduction"].get("ok"):
        ok, detail, dt = reproduce_check(run_id, cfg, mod, arrays, space, dp, pkeys, ev,
                                         specs, saved_folds_by_num)
        run_state["reproduction"] = detail
        save_checkpoint(state)
        if not ok:
            print(f"[{run_id}] REPRODUCTION FAILED — stopping this run. Detail: {detail}")
            return False
        print(f"[{run_id}] reproduction OK — params and OOS figures match the saved fold row.")
    else:
        print(f"[{run_id}] reproduction already OK from checkpoint, skipping re-check.")

    # if the strategy has zero free params, every variant necessarily produces the
    # SAME single champion regardless of training window — record that fact and
    # skip the (otherwise redundant) heavy search.
    if n_free == 0:
        print(f"[{run_id}] {cfg['strategy']} has ZERO free parameters (every knob pinned "
              f"min==max / single option) — the walk-forward search cannot select a "
              f"different config no matter what training window it sees. Variant sweep "
              f"is not informative; running ONE more confirmation fold instead of 32.")
        run_state["degenerate_space"] = True
        save_checkpoint(state)
        # one extra cheap confirmation on a DIFFERENT fold+variant to prove it really
        # is training-window-invariant, not just fold-1 coincidence
        f = FOLD_ORDER[0]
        sp = specs[f]
        tr_start, skip = variant_tr_start("T_all", index, sp["te_s"])
        with cpu_lock(f"lens_trainlen confirm #{run_id} fold{f} T_all"):
            row, dt = run_one(cfg, mod, arrays, space, dp, pkeys, ev, f, tr_start,
                              sp["te_s"], sp["te_e"])
        run_state["folds"].setdefault(str(f), {})["T_all"] = {
            **summarize_row(row, pkeys), "elapsed_s": dt,
            "tr_start": tr_start, "te_s": sp["te_s"], "te_e": sp["te_e"],
        }
        saved = saved_folds_by_num[f]
        same_params = row is not None and all(row.get(k) == saved.get(k) for k in pkeys)
        run_state["degenerate_confirmation"] = {
            "fold": f, "same_params_as_saved": same_params,
            "note": "T_all on the largest-training-window fold reproduces the identical "
                    "single config the saved (anchored) scheme found — confirms the space "
                    "truly has no free knob to re-tune.",
        }
        save_checkpoint(state)
        return True

    n_trials_use = cfg["n_trials"]
    # calibrate: reproduction call's dt already measured one (fold,scheme) search at
    # roughly T_5y-to-T_all sized training windows depending on run; use it as the
    # first data point for the 10-min-per-search cap.
    repro_dt = run_state["reproduction"]["elapsed_s"]
    if repro_dt > FOLD_SEARCH_CAP_S:
        scale = FOLD_SEARCH_CAP_S / repro_dt
        n_trials_use = max(20, int(cfg["n_trials"] * scale))
        print(f"[{run_id}] reproduction search took {repro_dt:.0f}s > {FOLD_SEARCH_CAP_S}s cap — "
              f"cutting n_trials {cfg['n_trials']} -> {n_trials_use} for ALL variants "
              f"(including a redone reduced-budget T_all baseline).")
        run_state["n_trials_cut"] = {"from": cfg["n_trials"], "to": n_trials_use,
                                     "reason": f"reproduction search took {repro_dt:.0f}s"}
        cfg = {**cfg, "n_trials": n_trials_use}
        # redo the reproduction at the reduced budget as the like-for-like baseline
        ok2, detail2, _ = reproduce_check(run_id, cfg, mod, arrays, space, dp, pkeys, ev,
                                          specs, saved_folds_by_num)
        run_state["reproduction_reduced_budget"] = detail2
        save_checkpoint(state)

    for f in FOLD_ORDER:
        if remaining() < 90:
            print(f"[{run_id}] wall-clock budget nearly exhausted ({remaining():.0f}s left) — "
                  f"stopping before fold {f}.")
            run_state.setdefault("stopped_early_at_fold", f)
            break
        sp = specs[f]
        fold_state = run_state["folds"].setdefault(str(f), {})
        for variant in VARIANTS:
            if variant in fold_state:
                continue  # checkpoint resume
            if remaining() < 60:
                print(f"[{run_id}] wall-clock budget exhausted mid-fold {f} — stopping.")
                run_state.setdefault("stopped_early_at_fold", f)
                save_checkpoint(state)
                return True
            n_years = VARIANT_YEARS.get(variant)
            tr_start, skip_reason = variant_tr_start(variant, index, sp["te_s"], n_years)
            if skip_reason:
                print(f"[{run_id}] fold {f} {variant}: SKIPPED — {skip_reason}")
                run_state["skipped_variants"].setdefault(str(f), {})[variant] = skip_reason
                save_checkpoint(state)
                continue
            print(f"[{run_id}] fold {f} {variant}: tr_start={tr_start} "
                  f"(train_bars={sp['te_s']-tr_start}) te=({sp['te_s']},{sp['te_e']}) "
                  f"n_trials={cfg['n_trials']} ...")
            with cpu_lock(f"lens_trainlen #{run_id} fold{f} {variant}"):
                row, dt = run_one(cfg, mod, arrays, space, dp, pkeys, ev, f, tr_start,
                                  sp["te_s"], sp["te_e"])
            summ = summarize_row(row, pkeys) or {"oos_pnl": 0.0, "oos_trades": 0, "oos_pf": 0.0}
            summ["elapsed_s"] = dt
            summ["tr_start"] = tr_start
            summ["train_bars"] = sp["te_s"] - tr_start
            summ["te_s"], summ["te_e"] = sp["te_s"], sp["te_e"]
            fold_state[variant] = summ
            print(f"[{run_id}] fold {f} {variant}: oos_pnl={summ.get('oos_pnl')} "
                  f"oos_trades={summ.get('oos_trades')} oos_pf={summ.get('oos_pf')} "
                  f"({dt:.1f}s)")
            save_checkpoint(state)
    return True


def main():
    state = load_checkpoint()
    state["meta"]["started_at"] = state["meta"].get("started_at", time.time())
    state["meta"]["run_configs"] = RUN_CONFIGS
    order = ["257", "335"]  # ORB first (cheap — confirms/dismisses in minutes), then ENGU-Q
    for run_id in order:
        try:
            process_run(run_id, state)
        except Exception as e:
            print(f"[{run_id}] EXCEPTION: {type(e).__name__}: {e}")
            traceback.print_exc()
            state["runs"].setdefault(run_id, {})["error"] = f"{type(e).__name__}: {e}"
            save_checkpoint(state)
        if remaining() < 60:
            print(f"Global wall-clock budget exhausted after run {run_id} "
                  f"({elapsed():.0f}s elapsed). Stopping.")
            break
    state["meta"]["finished_at"] = time.time()
    state["meta"]["total_elapsed_s"] = elapsed()
    save_checkpoint(state)
    print(f"\nDone. Total elapsed {elapsed():.0f}s. Results: {RESULTS_PATH}")


if __name__ == "__main__":
    main()
