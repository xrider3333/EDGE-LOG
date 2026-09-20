"""wfdive LENS: do later walk-forward years' re-tunes actually add edge, or would
settings frozen early have done as well? (2026-09-16 research deep dive, Q1/Q3.)

Reuses tools/backfill_wf_oos.py's own replay machinery (rebuild_plan,
fold_bounds_from_rows, fold_params, build_fold_match, make_slice_evaluator via
rebuild_from_market_data's imports) so every fold's bar bounds and evaluator call
match the engine's own walk-forward exactly -- this script does not re-implement
any strategy-walk arithmetic, only ADDS extra evaluator calls (fixed params on
slices they were not originally tuned for) that the app itself never runs.

Cheap replays only -- fixed-param backtests over already-sliced windows, no
optimizer search, single process, CPU-lock held for the whole loop, this
process's own priority lowered (owner: live fleet runs on this box).

For each replayable run (see pick_runs()):
  1. Rebuild the fold plan (rebuild_plan) and load the pinned data window once.
  2. Build the UPPER-TRIANGULAR matrix: fold i's saved re-tuned params x fold j's
     test slice, for every j >= i (fold i's params cannot pre-date slice j < i in
     a real walk, so those cells are never evaluated).
  3. Diagonal (i == j) is checked against the doc's OWN saved fold figures via
     backfill_wf_oos.build_fold_match -- EXACTLY the tolerance the backfill tool
     uses (trades exact, net/PF within tolerance). Any fold failing that check
     drops the WHOLE run (never a partially-trusted matrix).
  4. Two extra fixed-param rows, evaluated on every individual slice 1..N:
     CHAMPION (validate.champion -- the crowned, fixed, hindsight-picked config)
     and DEFAULTS (the strategy file's own DEFAULT_PARAMS).
  5. Pooled comparisons (points + PF, unitless where it matters):
       window "2..N"   -- RE-TUNED (diagonal 2..N) vs FROZEN-AT-FOLD-1 (row 1,
                          cols 2..N) vs CHAMPION vs DEFAULTS. Fold 1 is dropped
                          because frozen-at-fold-1 trivially EQUALS the re-tuned
                          diagonal there (nothing to compare yet).
       window "mid..N" -- RE-TUNED (diagonal mid..N) vs FROZEN-AT-FOLD-mid (row
                          mid, cols mid..N). mid = ceil(N/2), clamped to N-1.
  6. Learning curve: for each i in 1..N-1, params_i on slice i+1 (one bar ahead
     of its own training) vs params_1 on slice i+1 -- does more training data
     (a later fold) make the very next slice better than the earliest params
     would have?
  7. Parameter drift between consecutive fold pairs, each numeric change
     normalized by that param's DEFAULT_PARAMS search-range width (so a change
     is comparable across params of very different scale), plus the share of
     consecutive pairs with an IDENTICAL full parameter vector.
  8. Free "less training data" comparison, no extra replay: validate.wf_rolling
     .oos_net (rolling -- fixed-size recent window) vs validate.wf_anchored
     .oos_net (anchored -- all history) already saved on the doc.

Usage (from this worktree):  python tools/wfdive/lens_frozen.py
Writes: _wfdive_data/lens_frozen.json
"""
import copy
import json
import math
import os
import random
import statistics
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402

sys.path.insert(0, common.WORKTREE_ROOT)
from tools.backfill_wf_oos import (  # noqa: E402
    ReplaySkip, build_fold_match, fold_bounds_from_rows, fold_params, rebuild_plan,
)

PRIORITY_IDS = [257, 335, 243]
RUN_CAP = 30
DP = 4  # trade-pnl rounding, matches backfill_wf_oos's own build_fold_match


# ── run selection ─────────────────────────────────────────────────────────────
def is_book(d):
    if d.get("book") is not None:
        return True
    scope = str(d.get("scope") or "")
    return "Book" in scope or "\U0001F4DA" in scope  # memory: exclude books, no WF folds


def pick_runs(runs, log=print):
    """-> (selected_docs, selection_report). selected_docs is capped at RUN_CAP,
    always includes PRIORITY_IDS when they are replayable non-books, then one run
    per remaining family (that family's newest-by-timestamp replayable run),
    remaining families themselves ordered newest-first so a cap always keeps the
    most recently validated work."""
    ok_runs, refused = [], []
    for d in runs:
        if is_book(d):
            continue
        plan, reason = rebuild_plan(d)
        if plan is None:
            refused.append({"id": d.get("id"), "reason": reason})
        else:
            ok_runs.append(d)
    by_id = {d.get("id"): d for d in ok_runs}

    fam_map = {}
    for d in ok_runs:
        fam_map.setdefault(common.family_key(d), []).append(d)

    selected, picked_families, priority_report = [], set(), []
    for pid in PRIORITY_IDS:
        d = by_id.get(pid)
        if d is None:
            priority_report.append({"id": pid, "included": False,
                                     "reason": "not replayable or not found"})
            continue
        selected.append(d)
        picked_families.add(common.family_key(d))
        priority_report.append({"id": pid, "included": True,
                                 "family": common.family_key(d)})

    remaining_fams = []
    for fk, docs in fam_map.items():
        if fk in picked_families:
            continue
        newest = max(docs, key=lambda d: (str(d.get("timestamp") or ""), d.get("id") or 0))
        remaining_fams.append((fk, newest))
    remaining_fams.sort(key=lambda t: (str(t[1].get("timestamp") or ""), t[1].get("id") or 0),
                         reverse=True)
    for fk, d in remaining_fams:
        if len(selected) >= RUN_CAP:
            break
        selected.append(d)
        picked_families.add(fk)

    report = {
        "total_runs_seen": len(runs),
        "ok_non_book_replayable": len(ok_runs),
        "distinct_families_among_ok": len(fam_map),
        "priority": priority_report,
        "families_not_sampled": len(fam_map) - len(picked_families),
        "cap": RUN_CAP,
        "n_selected": len(selected),
    }
    log(f"[pick_runs] {len(ok_runs)} ok/{len(refused)} refused non-book runs, "
        f"{len(fam_map)} distinct families -> selected {len(selected)} run(s)")
    return selected, report


# ── pooled-stat helpers (mirrors analytics.wf_oos_block's own PF convention) ──
def cell_from_pnls(pnls):
    """pnls: list of per-trade net pnls (already rounded to DP). -> small dict a
    verifier can re-pool without needing the raw trades (gross_win/gross_loss are
    additive across cells; PF and win_rate are not, so they are NOT stored here --
    recompute them from the pooled sums via pf_from_gross())."""
    trades = len(pnls)
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]
    return {"trades": trades, "net": round(float(sum(pnls)), DP) if pnls else 0.0,
            "wins": len(wins), "losses": len(losses),
            "gross_win": round(float(sum(wins)), DP), "gross_loss": round(float(-sum(losses)), DP)}


def pf_from_gross(gross_win, gross_loss):
    """gross_win/gross_loss if gross_loss > 0, else None (no losing trade -- the
    same None analytics.wf_oos_block / json_safe would save for an infinite PF)."""
    return (gross_win / gross_loss) if gross_loss > 0 else None


def pool_cells(cells):
    """Sum a list of cell_from_pnls() dicts into one pooled stat dict."""
    trades = sum(c["trades"] for c in cells)
    net = round(sum(c["net"] for c in cells), DP)
    wins = sum(c["wins"] for c in cells)
    losses = sum(c["losses"] for c in cells)
    gw = round(sum(c["gross_win"] for c in cells), DP)
    gl = round(sum(c["gross_loss"] for c in cells), DP)
    win_rate = round(100.0 * wins / trades, 2) if trades else None
    return {"trades": trades, "net": net, "wins": wins, "losses": losses,
            "gross_win": gw, "gross_loss": gl, "pf": pf_from_gross(gw, gl),
            "win_rate": win_rate}


def ratio(a, b, key):
    """a[key] / b[key] for a unitless comparison; None when b's value is not a
    usable positive finite number (never divide by zero/None/inf silently)."""
    bv, av = b.get(key), a.get(key)
    if av is None or bv is None:
        return None
    if key == "pf":
        if not (isinstance(bv, (int, float)) and math.isfinite(bv) and bv > 0):
            return None
        if not (isinstance(av, (int, float)) and math.isfinite(av)):
            return None
        return round(av / bv, 4)
    if not isinstance(bv, (int, float)) or bv == 0:
        return None
    return round(av / bv, 4)


# ── per-run replay ──────────────────────────────────────────────────────────
def replay_one(d, log=print):
    """-> (result_dict, None) or (None, reason). Loads market data, builds the
    upper-triangular matrix, verifies the diagonal, and computes every pooled/
    learning-curve/param-drift block described in the module docstring."""
    from augur_engine.auto import _auto_space_from_params, make_slice_evaluator
    from augur_engine.data import find_master, load_master_arrays
    from augur_engine.strategies import load_strategy

    run_id = d.get("id")
    plan, reason = rebuild_plan(d)
    if plan is None:
        return None, f"rebuild_plan refused: {reason}"

    mod = load_strategy(plan["strategy"])
    dp_meta = getattr(mod, "DEFAULT_PARAMS", {}) or {}
    space = _auto_space_from_params(dp_meta)
    pkeys = list(space.keys())
    # A "pinned" single-config file (every numeric knob min==max, every categorical
    # knob a single option) never actually searches -- every fold's "re-tuned"
    # params are forced identical, so its frozen-vs-retuned ratio is a trivial 1.0,
    # not evidence either way (memory: "Auto-Validate = FULL search space, never a
    # pinned file" -- #257 is exactly this case, confirmed below by param_drift).
    def _degenerate(spec):
        if spec[0] in ("int", "float"):
            return float(spec[2]) == float(spec[1])
        return len(spec[1]) <= 1
    is_pinned = bool(space) and all(_degenerate(s) for s in space.values())
    rows = [fb["row"] for fb in plan["folds"]]
    params_list, preason = fold_params(pkeys, rows)
    if preason:
        return None, f"fold_params refused: {preason}"

    master = find_master(plan["instrument"], plan["timeframe"], plan["session"], plan["source"])
    if master is None:
        return None, (f"no master for {plan['instrument']} {plan['timeframe']} "
                       f"{plan['session']} {plan['source']}")
    t_load = time.time()
    arrays = load_master_arrays(master, date_from=plan["date_from"], date_to=plan["date_to"])
    n = len(arrays["close"])
    if n != plan["expect_n"]:
        return None, (f"bars_mismatch: window has {n} bars, fold rows expect "
                       f"{plan['expect_n']} (data changed since this run validated)")
    ev = make_slice_evaluator(mod, arrays, plan["cost_pts"])
    index = arrays.get("index")
    log(f"  #{run_id} {plan['strategy']} {plan['instrument']} {plan['timeframe']} "
        f"loaded {n} bars in {time.time() - t_load:.1f}s, {len(plan['folds'])} fold(s), "
        f"mode={plan['mode']}")

    N = len(plan["folds"])
    fold_no = [fb["fold"] for fb in plan["folds"]]  # 1..N in order
    bounds = {fb["fold"]: (fb["te_s"], fb["te_e"]) for fb in plan["folds"]}

    # ---- diagonal: verify against the doc's own saved fold figures ----
    diag_checks, diag_cells = [], {}
    for fb, params in zip(plan["folds"], params_list):
        m = build_fold_match(ev, index, fb, params, dp=DP)
        diag_checks.append({"fold": m["fold"], "ok": m["ok"], "reason": m["reason"],
                             "trades": m["oos_trades"], "d_trades": m["d_trades"],
                             "net": round(m["oos_pnl"], DP), "d_net": round(m["d_net"], 6)})
        diag_cells[m["fold"]] = cell_from_pnls(m["pnls"])
    if not all(c["ok"] for c in diag_checks):
        bad = [c for c in diag_checks if not c["ok"]]
        return None, ("diagonal mismatch vs saved fold figures: "
                       + "; ".join(f"fold {c['fold']}: {c['reason']}" for c in bad))

    # ---- upper-triangular matrix: params_i x slice_j for j >= i ----
    matrix = {}          # matrix[i][j] = cell dict, i,j are fold numbers, j >= i
    for idx_i, (fb_i, params_i) in enumerate(zip(plan["folds"], params_list)):
        i = fb_i["fold"]
        matrix[i] = {i: diag_cells[i]}   # reuse the verified diagonal cell
        for fb_j in plan["folds"][idx_i + 1:]:
            j = fb_j["fold"]
            a, b = bounds[j]
            om = ev(a, b, params_i, keep_trades=True)
            pnls = [round(float(t[2]), DP) for t in (om.get("trades") or [])] if om else []
            matrix[i][j] = cell_from_pnls(pnls)

    # ---- champion (fixed, hindsight-crowned) + defaults rows, every slice ----
    champion_params = (d.get("validate") or {}).get("champion")
    if not isinstance(champion_params, dict) or not champion_params:
        sel = d.get("selection") or {}
        crowned = [c for c in (sel.get("candidates") or []) if c.get("crowned")]
        champion_params = crowned[0].get("params") if crowned else None
    defaults_params = {k: v.get("default") for k, v in dp_meta.items() if isinstance(v, dict)}
    defaults_params = {k: v for k, v in defaults_params.items() if k in pkeys}

    def fixed_row(params):
        if not params:
            return None
        row = {}
        for fb in plan["folds"]:
            j = fb["fold"]
            a, b = bounds[j]
            om = ev(a, b, params, keep_trades=True)
            pnls = [round(float(t[2]), DP) for t in (om.get("trades") or [])] if om else []
            row[j] = cell_from_pnls(pnls)
        return row

    champion_row = fixed_row(champion_params)
    defaults_row = fixed_row(defaults_params) if defaults_params else None

    # ---- pooled comparisons ----
    def pooled(cells_by_j, lo, hi):
        return pool_cells([cells_by_j[j] for j in fold_no if lo <= j <= hi])

    pools = {}
    if N >= 2:
        lo2 = fold_no[1]  # fold 2 (drop fold 1: frozen_1 there trivially == re-tuned)
        hiN = fold_no[-1]
        re_tuned_2N = pooled({j: matrix[j][j] for j in fold_no}, lo2, hiN)
        frozen1_2N = pooled(matrix[fold_no[0]], lo2, hiN)
        block = {"from_fold": lo2, "to_fold": hiN, "re_tuned": re_tuned_2N,
                 "frozen_1": frozen1_2N,
                 "ratio_frozen1_over_retuned_net": ratio(frozen1_2N, re_tuned_2N, "net"),
                 "ratio_frozen1_over_retuned_pf": ratio(frozen1_2N, re_tuned_2N, "pf")}
        if champion_row:
            champ_2N = pooled(champion_row, lo2, hiN)
            block["champion"] = champ_2N
            block["ratio_champion_over_retuned_net"] = ratio(champ_2N, re_tuned_2N, "net")
            block["ratio_champion_over_retuned_pf"] = ratio(champ_2N, re_tuned_2N, "pf")
        if defaults_row:
            def_2N = pooled(defaults_row, lo2, hiN)
            block["defaults"] = def_2N
            block["ratio_defaults_over_retuned_net"] = ratio(def_2N, re_tuned_2N, "net")
            block["ratio_defaults_over_retuned_pf"] = ratio(def_2N, re_tuned_2N, "pf")
        pools["window_2_N"] = block

        mid_pos = min(max((N + 1) // 2, 1), N - 1)  # index into fold_no, 0-based, < N-1
        mid = fold_no[mid_pos]
        if mid in matrix and any(j > mid for j in matrix[mid]):
            re_tuned_midN = pooled({j: matrix[j][j] for j in fold_no}, mid, hiN)
            frozen_mid_midN = pooled(matrix[mid], mid, hiN)
            mblock = {"mid_fold": mid, "from_fold": mid, "to_fold": hiN,
                      "re_tuned": re_tuned_midN, "frozen_mid": frozen_mid_midN,
                      "ratio_frozen_mid_over_retuned_net": ratio(frozen_mid_midN, re_tuned_midN, "net"),
                      "ratio_frozen_mid_over_retuned_pf": ratio(frozen_mid_midN, re_tuned_midN, "pf")}
            if champion_row:
                champ_midN = pooled(champion_row, mid, hiN)
                mblock["champion"] = champ_midN
                mblock["ratio_champion_over_retuned_net"] = ratio(champ_midN, re_tuned_midN, "net")
                mblock["ratio_champion_over_retuned_pf"] = ratio(champ_midN, re_tuned_midN, "pf")
            pools["window_mid_N"] = mblock

    # ---- learning curve: params_i on slice i+1 vs params_1 on slice i+1 ----
    learning_curve = []
    for idx in range(N - 1):
        i, nxt = fold_no[idx], fold_no[idx + 1]
        tuned_cell = matrix[i][nxt]
        frozen1_cell = matrix[fold_no[0]][nxt]
        learning_curve.append({
            "i": i, "slice": nxt,
            "tuned_net": tuned_cell["net"], "tuned_trades": tuned_cell["trades"],
            "tuned_pf": pf_from_gross(tuned_cell["gross_win"], tuned_cell["gross_loss"]),
            "frozen1_net": frozen1_cell["net"], "frozen1_trades": frozen1_cell["trades"],
            "frozen1_pf": pf_from_gross(frozen1_cell["gross_win"], frozen1_cell["gross_loss"]),
            "tuned_beats_frozen1_net": (None if i == fold_no[0] else
                                        tuned_cell["net"] > frozen1_cell["net"]),
        })

    # ---- parameter drift between consecutive folds ----
    widths = {}
    for k, spec in space.items():
        kind = spec[0]
        if kind in ("int", "float"):
            widths[k] = abs(float(spec[2]) - float(spec[1])) or None
        else:
            widths[k] = None  # categorical -- distance is a 0/1 "changed" flag instead
    pairs = []
    identical_pairs = 0
    for idx in range(N - 1):
        pa, pb = params_list[idx], params_list[idx + 1]
        changed = {}
        for k in pkeys:
            va, vb = pa.get(k), pb.get(k)
            if isinstance(va, (int, float)) and isinstance(vb, (int, float)) \
                    and not isinstance(va, bool) and not isinstance(vb, bool):
                if abs(float(vb) - float(va)) > 1e-9:
                    w = widths.get(k)
                    changed[k] = {"from": va, "to": vb,
                                  "norm_dist": (round(abs(float(vb) - float(va)) / w, 4)
                                                if w else None)}
            elif va != vb:
                changed[k] = {"from": va, "to": vb, "norm_dist": 1.0}
        if not changed:
            identical_pairs += 1
        pairs.append({"from_fold": fold_no[idx], "to_fold": fold_no[idx + 1],
                      "n_changed": len(changed), "n_params": len(pkeys),
                      "changed": changed})
    param_drift = {"pairs": pairs,
                   "share_identical_pairs": round(identical_pairs / (N - 1), 4) if N > 1 else None,
                   "search_range_widths": widths}

    # ---- free scheme comparison already saved on the doc ----
    v = d.get("validate") or {}
    wr, wa = v.get("wf_rolling"), v.get("wf_anchored")
    scheme_compare = None
    if isinstance(wr, dict) and isinstance(wa, dict) and wr.get("ran") and wa.get("ran"):
        r_net, a_net = wr.get("oos_net"), wa.get("oos_net")
        r_held, a_held = wr.get("held"), wa.get("held")
        scheme_compare = {
            "rolling": {"oos_net": r_net, "held": r_held, "n_folds": wr.get("n_folds"),
                        "net_per_held_fold": (round(r_net / r_held, 2) if r_held else None)},
            "anchored": {"oos_net": a_net, "held": a_held, "n_folds": wa.get("n_folds"),
                         "net_per_held_fold": (round(a_net / a_held, 2) if a_held else None)},
            "note": "rolling = fixed-size recent training window (less total data); "
                    "anchored = grows from the start (all history). held counts differ "
                    "run to run, so compare net_per_held_fold, not raw net.",
        }

    # ---- cold-start flag (memory: validate folds start COLD) ----
    diag_trades = [diag_cells[j]["trades"] for j in fold_no]
    med_trades = statistics.median(diag_trades) if diag_trades else 0
    cold_folds = [fold_no[k] for k, t in enumerate(diag_trades)
                  if med_trades > 0 and t < 0.25 * med_trades]

    return {
        "id": run_id, "strategy": plan["strategy"], "instrument": plan["instrument"],
        "timeframe": plan["timeframe"], "family": common.family_key(d),
        "mode": plan["mode"], "n_folds": N, "fold_numbers": fold_no,
        "date_from": plan["date_from"], "date_to": plan["date_to"],
        "is_pinned_single_config": is_pinned,
        "diagonal_checks": diag_checks,
        "champion_params_used": bool(champion_row), "defaults_params_used": bool(defaults_row),
        "pools": pools, "learning_curve": learning_curve, "param_drift": param_drift,
        "scheme_compare": scheme_compare, "cold_start_folds": cold_folds,
        "median_diag_trades_per_fold": med_trades,
    }, None


# ── bootstrap CI helper ──────────────────────────────────────────────────────
def bootstrap_median_ci(values, n_boot=2000, seed=42):
    vals = [v for v in values if v is not None and isinstance(v, (int, float)) and math.isfinite(v)]
    if len(vals) < 2:
        return {"median": (round(statistics.median(vals), 4) if vals else None),
                "ci95": None, "n": len(vals)}
    rng = random.Random(seed)
    boots = []
    for _ in range(n_boot):
        sample = [vals[rng.randrange(len(vals))] for _ in range(len(vals))]
        boots.append(statistics.median(sample))
    boots.sort()
    lo = boots[int(0.025 * n_boot)]
    hi = boots[min(int(0.975 * n_boot), n_boot - 1)]
    return {"median": round(statistics.median(vals), 4), "ci95": [round(lo, 4), round(hi, 4)],
            "n": len(vals)}


# ── main ──────────────────────────────────────────────────────────────────────
def main():
    common.low_priority()
    common.setup_data_env()
    runs = common.load_runs()
    selected, selection_report = pick_runs(runs)
    print(f"[lens_frozen] selected {len(selected)} run(s): "
          f"{[d.get('id') for d in selected]}")

    results, dropped = {}, []
    t0 = time.time()
    with common.cpu_lock("lens_frozen: frozen-vs-retuned WF replay"):
        for k, d in enumerate(selected, 1):
            run_id = d.get("id")
            print(f"[{k}/{len(selected)}] replaying #{run_id} "
                  f"({d.get('strategy')} {d.get('instrument')} {d.get('timeframe')}) ...")
            t1 = time.time()
            try:
                res, reason = replay_one(d, log=print)
            except ReplaySkip as e:
                res, reason = None, str(e)
            except Exception as e:
                res, reason = None, f"{type(e).__name__}: {e}"
            if res is None:
                print(f"  DROPPED #{run_id}: {reason}")
                dropped.append({"id": run_id, "reason": reason})
            else:
                print(f"  ok #{run_id} in {time.time() - t1:.1f}s "
                      f"({res['n_folds']} folds, mode {res['mode']})")
                results[str(run_id)] = res
    print(f"[lens_frozen] replay loop done in {time.time() - t0:.1f}s: "
          f"{len(results)} usable, {len(dropped)} dropped")

    # ── aggregate across runs (already one-per-family by construction) ────────
    # Headline = NON-PINNED runs only: a pinned single-config file (#257 is one)
    # never actually re-tunes anything, so its ratio is a trivial 1.0, not
    # evidence either way. Reported separately, never blended into the headline.
    pinned_ids = [rid for rid, r in results.items() if r.get("is_pinned_single_config")]
    non_pinned = {rid: r for rid, r in results.items() if not r.get("is_pinned_single_config")}

    def collect(pool, path_fn):
        return [path_fn(r) for r in pool.values() if path_fn(r) is not None]

    def ratio_block(pool):
        return {
            "frozen1_over_retuned_net": bootstrap_median_ci(
                collect(pool, lambda r: (r.get("pools", {}).get("window_2_N") or {}).get(
                    "ratio_frozen1_over_retuned_net"))),
            "frozen1_over_retuned_pf": bootstrap_median_ci(
                collect(pool, lambda r: (r.get("pools", {}).get("window_2_N") or {}).get(
                    "ratio_frozen1_over_retuned_pf"))),
            "champion_over_retuned_net": bootstrap_median_ci(
                collect(pool, lambda r: (r.get("pools", {}).get("window_2_N") or {}).get(
                    "ratio_champion_over_retuned_net"))),
            "champion_over_retuned_pf": bootstrap_median_ci(
                collect(pool, lambda r: (r.get("pools", {}).get("window_2_N") or {}).get(
                    "ratio_champion_over_retuned_pf"))),
            "frozen_mid_over_retuned_net": bootstrap_median_ci(
                collect(pool, lambda r: (r.get("pools", {}).get("window_mid_N") or {}).get(
                    "ratio_frozen_mid_over_retuned_net"))),
            "frozen_mid_over_retuned_pf": bootstrap_median_ci(
                collect(pool, lambda r: (r.get("pools", {}).get("window_mid_N") or {}).get(
                    "ratio_frozen_mid_over_retuned_pf"))),
            "share_identical_param_pairs": bootstrap_median_ci(
                collect(pool, lambda r: r.get("param_drift", {}).get("share_identical_pairs"))),
        }

    agg = {
        "n_runs_used": len(results),
        "n_runs_dropped": len(dropped),
        "n_pinned_single_config_excluded_from_headline": len(pinned_ids),
        "pinned_single_config_ids": pinned_ids,
        "headline_non_pinned": ratio_block(non_pinned),
        "all_runs_incl_pinned": ratio_block(results),
    }
    # learning curve: does slice i+1 favor the freshly-tuned params (i) over the
    # earliest-tuned ones (params_1)? share of non-trivial (i != fold 1) comparisons
    # where tuned_net > frozen1_net. Non-pinned only (a pinned file's rows are
    # always trivially equal, not a real "tuned beats frozen1" data point).
    lc_flags = []
    for r in non_pinned.values():
        for row in r.get("learning_curve", []):
            if row.get("tuned_beats_frozen1_net") is not None:
                lc_flags.append(1.0 if row["tuned_beats_frozen1_net"] else 0.0)
    agg["learning_curve_share_tuned_beats_frozen1"] = {
        "share": round(sum(lc_flags) / len(lc_flags), 4) if lc_flags else None,
        "n_comparisons": len(lc_flags)}

    sc_ratios = []
    for r in results.values():
        sc = r.get("scheme_compare")
        if sc and sc["rolling"]["net_per_held_fold"] is not None and sc["anchored"]["net_per_held_fold"]:
            sc_ratios.append(sc["rolling"]["net_per_held_fold"] / sc["anchored"]["net_per_held_fold"])
    agg["rolling_over_anchored_net_per_fold"] = bootstrap_median_ci(sc_ratios)

    out = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "lens": "frozen-vs-retuned walk-forward (Q1/Q3): does later re-tuning add "
                "edge, or would fold-1's or the crowned champion's fixed params have "
                "done as well pooled over the same later out-of-sample slices?",
        "selection": selection_report,
        "priority_ids": PRIORITY_IDS,
        "dropped_runs": dropped,
        "aggregate": agg,
        "runs": results,
    }
    out_path = os.path.join(common.DATA_DIR, "lens_frozen.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, default=str, indent=1)
    print(f"[lens_frozen] saved {out_path}")

    print("\n=== per-crown rows (#257 / #335 / #243) ===")
    for pid in PRIORITY_IDS:
        r = results.get(str(pid))
        if not r:
            drop = next((x for x in dropped if x["id"] == pid), None)
            print(f"#{pid}: NOT USABLE ({drop['reason'] if drop else 'not selected/found'})")
            continue
        w = r.get("pools", {}).get("window_2_N", {})
        print(f"#{pid} {r['strategy']} folds {r['fold_numbers']} mode={r['mode']}")
        print(f"  window fold {w.get('from_fold')}..{w.get('to_fold')}: "
              f"RE-TUNED net={w.get('re_tuned', {}).get('net')} pf={w.get('re_tuned', {}).get('pf')} "
              f"trades={w.get('re_tuned', {}).get('trades')}")
        print(f"  FROZEN-AT-FOLD-1: net={w.get('frozen_1', {}).get('net')} "
              f"pf={w.get('frozen_1', {}).get('pf')} "
              f"ratio(net)={w.get('ratio_frozen1_over_retuned_net')} "
              f"ratio(pf)={w.get('ratio_frozen1_over_retuned_pf')}")
        if "champion" in w:
            print(f"  CHAMPION: net={w.get('champion', {}).get('net')} "
                  f"pf={w.get('champion', {}).get('pf')} "
                  f"ratio(net)={w.get('ratio_champion_over_retuned_net')} "
                  f"ratio(pf)={w.get('ratio_champion_over_retuned_pf')}")
        sc = r.get("scheme_compare")
        if sc:
            print(f"  rolling net/held-fold={sc['rolling']['net_per_held_fold']} vs "
                  f"anchored net/held-fold={sc['anchored']['net_per_held_fold']}")


if __name__ == "__main__":
    main()
