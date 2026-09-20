r"""Candidate matrix builder (owner request 2026-09-16, "IS depth" deep dive #2).

For ONE validated run (by run number, read from _wfdive_data/runs.json -- no Firestore),
this draws candidate configs EXACTLY the way the engine's own per-fold walk-forward search
draws them:

    samp = augur_engine.auto._RandomSampler(space, seed=seed)     # same class, same seed
    pe   = augur_engine.auto._collapse(samp.ask(), dp)            # same collapse

continued from ONE sampler out to C_total draws (default target 1000, floor 400). Because
every fold of a walk-forward run re-seeds its OWN `_RandomSampler(space, seed=seed)` fresh
(augur_engine/auto.py `_wf_fold_row`: "a fresh sampler from the run's seed"), the FIRST
n_trials draws of our one continued sampler are BIT-IDENTICAL to what every one of that
run's folds searched -- there is only ever one seeded candidate list per run, not one per
fold. Continuing past n_trials gives extra configs the run's own search never evaluated
(what the analysis needs to ask "would a bigger year-1 IS budget, or extra IS-only points,
change anything").

Two extra rows are appended, tagged (never counted in "n_trials"/"C_total"):
    "champion" -- validate.champion (== best_params) exactly as the run crowned it
    "default"  -- the strategy file's OWN DEFAULT_PARAMS defaults (today's file, may not
                  equal what a rewritten default would have been at validation time)

For EVERY config (sampler draws + the 2 extras), this runs ONE warm continuous backtest
over the run's FULL window (date_from..date_to, LOCKBOX INCLUDED -- never split, never
sliced before running) via augur_engine.auto.make_slice_evaluator -- the identical
kwarg-detection + cost-apply path every trial/fold in the engine already goes through
(same function auto.py's own `_ev` and validate.py's `#88` selection stage call) -- so a
downstream reader can slice the returned per-trade arrays into ANY sub-window (a fold's
train/test bars, the lockbox, a shorter IS budget) by filtering the SAME warm trade list on
entry bar index or entry timestamp, with NO cold-start artefact at that sub-window's start
(hard constraint: "use WARM evaluation ... so window starts carry no cold-start artefact").

Usage (run from THIS worktree; see tools/wfdive/common.py for why):
    python tools/wfdive/isdepth/build_matrix.py 299                     # full build, C_total auto
    python tools/wfdive/isdepth/build_matrix.py 299 --c-total 1000
    python tools/wfdive/isdepth/build_matrix.py 335 --time-only 5       # measure only, no matrix

Output (both written under _wfdive_data/isdepth/):
    matrix_<run_id>.npz   -- CSR-style flat per-trade arrays + per-config summary arrays
    matrix_<run_id>.json  -- sidecar: params list (index/tag/params), window, bars, seed,
                             n_trials, min_trades, seconds/backtest, build provenance

Checkpointed every 50 configs (both files rewritten, so a killed run leaves a usable
partial matrix with an honest "n_built" < "c_total" in the sidecar).
"""
import argparse
import json
import os
import sys
import time

WORKTREE_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if WORKTREE_ROOT not in sys.path:
    sys.path.insert(0, WORKTREE_ROOT)
TOOLS_DIR = os.path.join(WORKTREE_ROOT, "tools")
if TOOLS_DIR not in sys.path:
    sys.path.insert(0, TOOLS_DIR)

from tools.wfdive import common  # noqa: E402

OUT_DIR = os.path.join(common.DATA_DIR, "isdepth")
os.makedirs(OUT_DIR, exist_ok=True)

# same data_source -> session mapping backfill_wf_oos.py uses (SESSION), kept identical so
# a run this tool can plan is exactly a run backfill_wf_oos.py could also plan.
SESSION = {"db_noadj_rth": "rth", "db_noadj_eth": "eth", "yahoo_adj": "rth"}

DEFAULT_MIN_TRADES = 30      # api/runner.py + augur_engine/validate.py signature default;
                              # no run doc in runs.json records a per-job override (checked)
DEFAULT_SEED = 42            # augur_engine/validate.py run_validate() signature default;
                              # no call site in api/runner.py threads a job-level seed
TARGET_C_TOTAL = 1000
FLOOR_C_TOTAL = 400
BUDGET_SECONDS = 25 * 60
CHECKPOINT_EVERY = 50


def find_run(run_id):
    runs = common.load_runs()
    for r in runs:
        if str(r.get("id")) == str(run_id):
            return r
    raise SystemExit(f"run #{run_id} not found in {os.path.join(common.DATA_DIR, 'runs.json')}")


def n_trials_of(doc):
    """validate.py saves n_combos = n_trials * 2 (Stage A count + Stage B/WF count, same
    n_trials value threaded through both -- see augur_engine/validate.py run_validate()'s
    two run_auto() calls, both passed the caller's single `n_trials`). No run doc in
    runs.json carries n_trials directly, so this is the only route back to it."""
    nc = doc.get("n_combos")
    if not nc or int(nc) % 2 != 0:
        raise SystemExit(f"run #{doc.get('id')}: n_combos={nc!r} - cannot recover n_trials "
                         "(expected an even n_combos = n_trials*2, see validate.py)")
    return int(nc) // 2


def full_window(doc):
    """(date_from, date_to) exactly as run_validate() resolved them for the FULL-window
    champion replay (validate.py: `full = run_backtest(..., date_from=opt_from,
    date_to=date_to, ...)` where opt_from = full_lo.isoformat() and full_lo = parse(the
    run's OWN date_from) when that field is set -- true for every run in runs.json, so this
    is just the doc's own date_from/date_to, unlike backfill_wf_oos.rebuild_plan()'s window
    (validate.windows.optimize), which stops BEFORE the lockbox on purpose."""
    df, dt = doc.get("date_from"), doc.get("date_to")
    if not df or not dt:
        raise SystemExit(f"run #{doc.get('id')}: missing date_from/date_to")
    return str(df), str(dt)


def build_plan(doc):
    """Independent of backfill_wf_oos.rebuild_plan() (that one deliberately excludes the
    lockbox) -- but reuses its SESSION map and its fold_bounds_from_rows() for the fold
    bar-bounds a validator needs (those bounds are relative to the PRE-lockbox array,
    which is a PREFIX of the full-window array loaded here since both start at the same
    date_from -- so a fold's [te_s:te_e) slice of the full-window arrays is bar-identical
    to the smaller pre-lockbox array backfill_wf_oos.py would have loaded)."""
    from backfill_wf_oos import fold_bounds_from_rows
    v = doc.get("validate") or {}
    if v.get("wf_ran") is not True:
        raise SystemExit(f"run #{doc.get('id')}: validate.wf_ran is not True")
    mode = str(v.get("wf_best_mode") or "").lower()
    if mode not in ("rolling", "anchored"):
        raise SystemExit(f"run #{doc.get('id')}: no usable wf_best_mode ({v.get('wf_best_mode')!r})")
    top = doc.get("top10_results")
    bounds, expect_n, reason = fold_bounds_from_rows(top if isinstance(top, list) else [])
    if reason:
        raise SystemExit(f"run #{doc.get('id')}: {reason}")
    src = doc.get("data_source")
    sess = SESSION.get(src)
    if not sess:
        raise SystemExit(f"run #{doc.get('id')}: unknown data_source {src!r}")
    date_from, date_to = full_window(doc)
    try:
        cost_pts = float(doc.get("cost_pts"))
    except (TypeError, ValueError):
        raise SystemExit(f"run #{doc.get('id')}: no cost_pts")
    lb_from = None
    win = v.get("windows") if isinstance(v.get("windows"), dict) else {}
    lb = win.get("lockbox") if isinstance(win.get("lockbox"), list) else None
    if lb and lb[0]:
        lb_from = str(lb[0])
    return {
        "run_id": doc.get("id"), "strategy": doc["strategy"], "instrument": doc["instrument"],
        "timeframe": doc["timeframe"], "session": sess, "source": src, "cost_pts": cost_pts,
        "mode": mode, "date_from": date_from, "date_to": date_to,
        "lockbox_from": lb_from, "lockbox_months": win.get("lockbox_months"),
        "fold_bounds": bounds, "pre_lockbox_bars": expect_n,
        "n_trials": n_trials_of(doc), "min_trades": DEFAULT_MIN_TRADES, "seed": DEFAULT_SEED,
    }


def load_space(plan):
    from augur_engine.strategies import load_strategy
    from augur_engine.auto import _auto_space_from_params
    mod = load_strategy(plan["strategy"])
    dp = getattr(mod, "DEFAULT_PARAMS", {}) or {}
    space = _auto_space_from_params(dp)
    pkeys = list(space.keys())
    return mod, dp, space, pkeys


def gen_candidates(space, dp, seed, c_total):
    """The engine's OWN sampler, continued past n_trials. Returns a plain list of param
    dicts, length c_total, in draw order -- candidates[:n_trials] is bit-identical to
    every fold's own search list for this run (see module docstring)."""
    from augur_engine.auto import _RandomSampler, _collapse
    samp = _RandomSampler(space, seed=seed)
    return [_collapse(samp.ask(), dp) for _ in range(c_total)]


def run_one(ev, params, dp_pkeys=None):
    """ONE warm continuous backtest over whatever window `ev` was built on (the evaluator
    closure already has (arrays, cost_pts) baked in) -- ev(0, n, params, keep_trades=True)
    is the caller's job; this just normalizes a possibly-None result into the fixed shape
    the matrix arrays need, and pulls the trade list into (entry_bar, exit_bar, net)."""
    pass  # not used -- inlined in main() for speed (avoid a function-call per trade)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run_id", type=int)
    ap.add_argument("--c-total", type=int, default=None,
                    help=f"total candidates incl. sampler draws (default: auto, target "
                         f"{TARGET_C_TOTAL}, floor {FLOOR_C_TOTAL}, capped by the "
                         f"{BUDGET_SECONDS//60}-min budget after timing 5 configs)")
    ap.add_argument("--time-only", type=int, default=0, metavar="K",
                    help="just time K configs (5 sampler draws by default when K=5) and exit "
                         "- no matrix written, no cpu_lock held longer than the K backtests")
    args = ap.parse_args()

    common.low_priority()
    common.setup_data_env()

    doc = find_run(args.run_id)
    plan = build_plan(doc)
    mod, dp, space, pkeys = load_space(plan)
    print(f"[build_matrix] run #{plan['run_id']} {plan['strategy']} {plan['instrument']} "
          f"{plan['timeframe']} {plan['session']} src={plan['source']} cost_pts={plan['cost_pts']}")
    print(f"[build_matrix] window {plan['date_from']}..{plan['date_to']} (FULL, lockbox incl.) "
          f"mode={plan['mode']} n_trials={plan['n_trials']} seed={plan['seed']} "
          f"min_trades={plan['min_trades']}")
    print(f"[build_matrix] space ({len(pkeys)} knobs): {pkeys}")

    from augur_engine.data import find_master, load_master_arrays
    from augur_engine.auto import make_slice_evaluator, _RandomSampler, _collapse

    master = find_master(plan["instrument"], plan["timeframe"], plan["session"], plan["source"])
    if master is None:
        raise SystemExit(f"no master for {plan['instrument']} {plan['timeframe']} "
                         f"{plan['session']} {plan['source']}")

    with common.cpu_lock(f"isdepth build_matrix #{plan['run_id']} {plan['strategy']}"):
        t_load = time.time()
        arrays = load_master_arrays(master, date_from=plan["date_from"], date_to=plan["date_to"])
        n_bars = len(arrays["close"])
        idx = arrays.get("index")
        print(f"[build_matrix] loaded {n_bars} bars in {time.time() - t_load:.1f}s")
        ev = make_slice_evaluator(mod, arrays, plan["cost_pts"])

        # ── candidates: sampler draws + champion + default, in that order ──────────────
        c_total = args.c_total or TARGET_C_TOTAL
        raw = gen_candidates(space, dp, plan["seed"], max(c_total, 5))
        champ = dict((doc.get("validate") or {}).get("champion") or doc.get("best_params") or {})
        defaults = {k: (meta.get("default") if isinstance(meta, dict) else None) for k, meta in dp.items()}
        # champion/default must carry every pkey - fill any gap from the file's own default
        # (never invents a value the run didn't have and the file doesn't declare)
        for k in pkeys:
            if k not in champ:
                champ[k] = defaults.get(k)

        # ── time 5 configs first (task requirement) ─────────────────────────────────────
        timing_n = min(5, len(raw))
        t0 = time.time()
        for p in raw[:timing_n]:
            ev(0, n_bars, p, keep_trades=True)
        secs_per_bt = (time.time() - t0) / max(1, timing_n)
        print(f"[build_matrix] measured {secs_per_bt:.3f}s/backtest over {timing_n} configs "
              f"on {n_bars} bars")

        if args.time_only:
            print(f"[build_matrix] --time-only: exiting (no matrix written)")
            out = {"run_id": plan["run_id"], "strategy": plan["strategy"], "n_bars": n_bars,
                  "seconds_per_backtest": secs_per_bt, "timed_n": timing_n,
                  "instrument": plan["instrument"], "timeframe": plan["timeframe"]}
            path = os.path.join(OUT_DIR, f"timing_{plan['run_id']}.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump(out, f, indent=1)
            print(f"[build_matrix] wrote {path}")
            return 0

        if args.c_total is None:
            budget_c = int(BUDGET_SECONDS / max(1e-6, secs_per_bt))
            c_total = max(FLOOR_C_TOTAL, min(TARGET_C_TOTAL, budget_c))
            if c_total < TARGET_C_TOTAL:
                print(f"[build_matrix] AUTO-LOWERED c_total {TARGET_C_TOTAL} -> {c_total} "
                     f"({secs_per_bt:.3f}s/bt x {TARGET_C_TOTAL} = "
                     f"{secs_per_bt * TARGET_C_TOTAL / 60:.1f}min > {BUDGET_SECONDS/60:.0f}min budget)")
        else:
            c_total = args.c_total
        est_min = secs_per_bt * (c_total + 2) / 60.0
        print(f"[build_matrix] building c_total={c_total} (+2 tagged) est {est_min:.1f} min")

        candidates = gen_candidates(space, dp, plan["seed"], c_total)
        configs = [{"index": i, "tag": "sampler", "params": p} for i, p in enumerate(candidates)]
        configs.append({"index": len(configs), "tag": "champion", "params": champ})
        configs.append({"index": len(configs), "tag": "default", "params": defaults})

        n_cfg = len(configs)
        entry_bar_parts, exit_bar_parts, net_parts = [], [], []
        entry_ns_parts, exit_ns_parts = [], []
        offsets = [0]
        n_trades_arr = []
        total_pnl_arr = []
        pf_arr = []
        wins_arr = []
        losses_arr = []
        max_dd_arr = []
        win_rate_arr = []

        import numpy as np

        def _ts_ns(bar):
            if idx is None:
                return 0
            b = min(max(int(bar), 0), n_bars - 1)
            return int(idx[b].value)

        t_start = time.time()
        matrix_path = os.path.join(OUT_DIR, f"matrix_{plan['run_id']}.npz")
        sidecar_path = os.path.join(OUT_DIR, f"matrix_{plan['run_id']}.json")

        def checkpoint(n_done):
            eb = np.array(entry_bar_parts, dtype=np.int64) if entry_bar_parts else np.zeros(0, np.int64)
            xb = np.array(exit_bar_parts, dtype=np.int64) if exit_bar_parts else np.zeros(0, np.int64)
            en = np.array(entry_ns_parts, dtype=np.int64) if entry_ns_parts else np.zeros(0, np.int64)
            xn = np.array(exit_ns_parts, dtype=np.int64) if exit_ns_parts else np.zeros(0, np.int64)
            nt = np.array(net_parts, dtype=np.float64) if net_parts else np.zeros(0, np.float64)
            off = np.array(offsets, dtype=np.int64)
            np.savez_compressed(
                matrix_path, entry_bar=eb, exit_bar=xb, entry_ns=en, exit_ns=xn, net=nt,
                offsets=off, n_trades=np.array(n_trades_arr, dtype=np.int64),
                total_pnl=np.array(total_pnl_arr, dtype=np.float64),
                profit_factor=np.array(pf_arr, dtype=np.float64),
                wins=np.array(wins_arr, dtype=np.int64), losses=np.array(losses_arr, dtype=np.int64),
                max_drawdown=np.array(max_dd_arr, dtype=np.float64),
                win_rate=np.array(win_rate_arr, dtype=np.float64),
            )
            sidecar = {
                "run_id": plan["run_id"], "strategy": plan["strategy"], "instrument": plan["instrument"],
                "timeframe": plan["timeframe"], "session": plan["session"], "source": plan["source"],
                "cost_pts": plan["cost_pts"], "seed": plan["seed"], "n_trials": plan["n_trials"],
                "min_trades": plan["min_trades"], "wf_mode": plan["mode"],
                "date_from": plan["date_from"], "date_to": plan["date_to"],
                "lockbox_from": plan["lockbox_from"], "lockbox_months": plan["lockbox_months"],
                "n_bars": n_bars, "pkeys": pkeys, "space": {k: list(v) for k, v in space.items()},
                "fold_bounds": [{"fold": fb["fold"], "te_s": fb["te_s"], "te_e": fb["te_e"],
                                "test_bars": fb["test_bars"],
                                "train_bars_saved": fb["row"].get("train_bars")}
                               for fb in plan["fold_bounds"]],
                "pre_lockbox_bars": plan["pre_lockbox_bars"],
                "c_total": c_total, "n_built": n_done, "n_configs_total": n_cfg,
                "champion_index": n_cfg - 2, "default_index": n_cfg - 1,
                "seconds_per_backtest": secs_per_bt, "timed_n": timing_n,
                "build_seconds_so_far": time.time() - t_start,
                "configs": configs[:n_done],
                "notes": {
                    "timestamp_units": "int64 nanoseconds since UNIX epoch (UTC) - pandas "
                        "Timestamp.value on augur_engine.data.load_master_arrays' tz-aware "
                        "US/Eastern index; the instant is absolute/tz-invariant, only the "
                        "DISPLAY tz was US/Eastern",
                    "bar_index_semantics": "entry_bar/exit_bar are 0-based indices into THIS "
                        "matrix's own full-window bar array (n_bars), identical indexing to "
                        "fold_bounds' te_s/te_e - a fold's OOS test slice for this run is "
                        "trades with entry_bar in [fold.te_s, fold.te_e)",
                    "trades_after_costs": "net is ALREADY net of cost_pts (engine's own "
                        "_apply_costs ran inside make_slice_evaluator when cost_pts>0) - do "
                        "not subtract cost_pts again",
                    "per_config_summary_arrays": "n_trades/total_pnl/profit_factor/wins/"
                        "losses/max_drawdown/win_rate are the FULL-WINDOW warm metrics the "
                        "engine's own backtest returned for that config (profit_factor may "
                        "be +inf for a config with zero losing trades - stored as a real "
                        "IEEE-754 inf in the .npz float64 array, not null)",
                    "realism_gate_not_applied_here": "this file stores every candidate's raw "
                        "replay; WF_MIN_SIDE/MAX_TRADE_RATE/MAX_PF (augur_engine/auto.py) and "
                        "min_trades must be applied by the ANALYSIS reading this matrix, "
                        "windowed to whatever slice it is scoring (a fold's train window, "
                        "e.g.) - see augur_engine.auto._is_real(r, nbars) - nbars there is "
                        "the WINDOW's bar count, not n_bars",
                },
            }
            with open(sidecar_path, "w", encoding="utf-8") as f:
                json.dump(sidecar, f, indent=1, default=str)

        for i, cfg in enumerate(configs):
            om = ev(0, n_bars, cfg["params"], keep_trades=True)
            trades = list((om or {}).get("trades") or [])
            for t in trades:
                eb, xb = int(t[0]), int(t[1])
                entry_bar_parts.append(eb)
                exit_bar_parts.append(xb)
                net_parts.append(float(t[2]))
                entry_ns_parts.append(_ts_ns(eb))
                exit_ns_parts.append(_ts_ns(xb))
            offsets.append(len(entry_bar_parts))
            n_trades_arr.append(int((om or {}).get("num_trades", len(trades)) or len(trades)))
            total_pnl_arr.append(float((om or {}).get("total_pnl", sum(t[2] for t in trades)) or 0.0))
            pf = (om or {}).get("profit_factor")
            pf_arr.append(float(pf) if pf is not None else 0.0)
            wins_arr.append(int((om or {}).get("wins", 0) or 0))
            losses_arr.append(int((om or {}).get("losses", 0) or 0))
            max_dd_arr.append(float((om or {}).get("max_drawdown", 0.0) or 0.0))
            win_rate_arr.append(float((om or {}).get("win_rate", 0.0) or 0.0))

            done = i + 1
            if done % CHECKPOINT_EVERY == 0 or done == n_cfg:
                checkpoint(done)
                elapsed = time.time() - t_start
                rate = elapsed / done
                eta = rate * (n_cfg - done)
                print(f"[build_matrix] {done}/{n_cfg} ({cfg['tag']}) "
                     f"{elapsed:.0f}s elapsed, {rate:.3f}s/cfg, ETA {eta:.0f}s -- checkpointed")

    print(f"[build_matrix] DONE. wrote {matrix_path} and {sidecar_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
