"""wfdive VERIFY (adversarial) for lens_frozen.json -- "do later re-tunes add edge".

Independent recompute. Imports ONLY common.py (loaders/lock/priority) plus the
engine's own replay primitives (tools/backfill_wf_oos.rebuild_plan / fold_params,
augur_engine.auto.make_slice_evaluator, augur_engine.engine.run_backtest). Nothing
from lens_frozen.py / lens_frozen_addendum.py is imported.

Part A  -- bookkeeping on the saved lens_frozen.json + runs.json (no replay):
  A1 reproduce the headline medians / CIs from the per-run ratios the lens saved
  A2 cluster the 30 runs by the WEB's own family tag (doc.famKey) -> cluster-level
     medians + cluster bootstrap (the lens treated 21 runs as 21 families)
  A3 drop runs whose fold params never change (share_identical_pairs == 1.0):
     their frozen/retuned ratio is 1.0 by construction
  A4 learning curve: split ties (identical params -> identical cell) from real wins
  A5 rolling vs anchored: validate.py's `held` = number of PROFITABLE folds, not
     folds run -> the lens's net/held-fold normalisation is wrong; use raw oos_net
  A6 mid-window: the lens's frozen-mid window INCLUDES the mid fold's own diagonal
  A7 diagonal-check consistency vs the doc's own fold rows
  A8 Stage-A in-sample overlap: ksplit = int(0.75 * n) (auto.py OOS_SPLIT) vs the
     fold test slices -> how many "walk-forward" folds the CHAMPION was fitted on
  A9 crowned vs IS-max candidate: WF-years PnL and #88b lockbox PnL from the doc

Part B  -- independent replay (cpu_lock + low priority, single process):
  full upper-triangular matrix (params_i x slice_j, j>=i), champion row, defaults
  row, and the SEALED LOCKBOX for champion / last-fold params / fold-1 params /
  defaults (validate.windows.lockbox, exactly as validate.py's Stage C calls
  run_backtest). Saves every cell with gross_win/gross_loss so any window pools.

Part C  -- recompute every lens number from the replayed matrix, plus:
  champion-vs-retuned split into folds INSIDE Stage A's 75% IS window vs AFTER it,
  mid-window without the diagonal fold, and the lockbox re-tune test.

Usage (from the worktree root):
  python tools/wfdive/verify_frozen-vs-retuned.py            # A + B + C
  python tools/wfdive/verify_frozen-vs-retuned.py --no-replay # A + C on a saved matrix
Writes: _wfdive_data/verify_frozen_matrix.json, _wfdive_data/verify_frozen-vs-retuned.json
"""
import argparse
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

LENS_PATH = os.path.join(common.DATA_DIR, "lens_frozen.json")
MATRIX_PATH = os.path.join(common.DATA_DIR, "verify_frozen_matrix.json")
OUT_PATH = os.path.join(common.DATA_DIR, "verify_frozen-vs-retuned.json")
DP = 4
OOS_SPLIT = 0.75  # augur_engine/auto.py:45, applied as ksplit = int(n * OOS_SPLIT) (auto.py:1045)


# ── small stat helpers (own implementations) ─────────────────────────────────
def cell(pnls):
    w = [p for p in pnls if p > 0]
    l = [p for p in pnls if p < 0]
    return {"trades": len(pnls), "net": round(float(sum(pnls)), DP), "wins": len(w),
            "losses": len(l), "gross_win": round(float(sum(w)), DP),
            "gross_loss": round(float(-sum(l)), DP)}


def pool(cells):
    cells = [c for c in cells if c is not None]
    gw = sum(c["gross_win"] for c in cells)
    gl = sum(c["gross_loss"] for c in cells)
    return {"trades": sum(c["trades"] for c in cells), "net": round(sum(c["net"] for c in cells), DP),
            "wins": sum(c["wins"] for c in cells), "gross_win": round(gw, DP),
            "gross_loss": round(gl, DP), "pf": (round(gw / gl, 4) if gl > 0 else None)}


def ratio(a, b, key):
    av, bv = a.get(key), b.get(key)
    if av is None or bv is None or not isinstance(bv, (int, float)) or bv == 0 or not math.isfinite(bv):
        return None
    if key == "pf" and bv <= 0:
        return None
    return round(av / bv, 4)


def fin(vals):
    return [v for v in vals if isinstance(v, (int, float)) and math.isfinite(v)]


def med_ci(vals, n_boot=4000, seed=7):
    vals = fin(vals)
    if not vals:
        return {"median": None, "ci95": None, "n": 0}
    if len(vals) < 3:
        return {"median": round(statistics.median(vals), 4), "ci95": None, "n": len(vals)}
    rng = random.Random(seed)
    boots = sorted(statistics.median(rng.choices(vals, k=len(vals))) for _ in range(n_boot))
    return {"median": round(statistics.median(vals), 4),
            "ci95": [round(boots[int(0.025 * n_boot)], 4), round(boots[int(0.975 * n_boot) - 1], 4)],
            "n": len(vals)}


def cluster_med_ci(pairs, n_boot=4000, seed=7):
    """pairs: [(cluster_key, value)]. Point estimate = median of per-cluster medians;
    CI = cluster bootstrap (resample CLUSTERS with replacement, pool their runs, median)."""
    groups = {}
    for k, v in pairs:
        if isinstance(v, (int, float)) and math.isfinite(v):
            groups.setdefault(k, []).append(v)
    if not groups:
        return {"median_of_cluster_medians": None, "cluster_boot_ci95": None, "n_clusters": 0, "n_runs": 0}
    keys = list(groups)
    cmeds = {k: round(statistics.median(groups[k]), 4) for k in keys}
    rng = random.Random(seed)
    boots = []
    for _ in range(n_boot):
        samp = rng.choices(keys, k=len(keys))
        vals = [v for k in samp for v in groups[k]]
        boots.append(statistics.median(vals))
    boots.sort()
    return {"median_of_cluster_medians": round(statistics.median(cmeds.values()), 4),
            "pooled_median": round(statistics.median([v for k in keys for v in groups[k]]), 4),
            "cluster_boot_ci95": ([round(boots[int(0.025 * n_boot)], 4), round(boots[int(0.975 * n_boot) - 1], 4)]
                                  if len(keys) >= 2 else None),
            "n_clusters": len(keys), "n_runs": sum(len(g) for g in groups.values()),
            "cluster_medians": cmeds}


def sign_count(vals, thresh=1.0):
    vals = fin(vals)
    return {"n": len(vals), "below": sum(1 for v in vals if v < thresh),
            "equal": sum(1 for v in vals if v == thresh), "above": sum(1 for v in vals if v > thresh)}


# ── run facts straight from the docs ─────────────────────────────────────────
def is_pinned_file(strategy_file):
    """Every DEFAULT_PARAMS knob degenerate (min==max, or a single option)?"""
    import importlib.util
    p = os.path.join(common.WORKTREE_ROOT, "augur_strategies", strategy_file)
    spec = importlib.util.spec_from_file_location("_m", p)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    dp = getattr(m, "DEFAULT_PARAMS", {}) or {}
    knobs = [v for v in dp.values() if isinstance(v, dict)]
    if not knobs:
        return None, 0
    free = 0
    for v in knobs:
        mn, mx = v.get("min"), v.get("max")
        opts = v.get("options") if v.get("options") is not None else v.get("choices")
        deg = (mn is not None and mx is not None and float(mn) == float(mx)) or (opts is not None and len(opts) <= 1)
        if not deg:
            free += 1
    return free == 0, free


def fold_rows(d):
    rows = sorted(d.get("top10_results") or [], key=lambda r: int(r["fold"]))
    return rows


def params_from_rows(d, pkeys):
    return [{k: r.get(k) for k in pkeys} for r in fold_rows(d)]


def identical_all_folds(params_list):
    return all(params_list[i] == params_list[0] for i in range(1, len(params_list)))


def stage_a_split(d):
    """ksplit = int(0.75 * n) where n = bars in the optimize window = train_bars(fold 1)
    + sum(test_bars). Returns (ksplit, fold_bounds{fold:(te_s,te_e)}, n)."""
    rows = fold_rows(d)
    train0 = int(rows[0]["train_bars"])
    bounds, cum = {}, 0
    for r in rows:
        tb = int(r["test_bars"])
        bounds[int(r["fold"])] = (train0 + cum, train0 + cum + tb)
        cum += tb
    n = train0 + cum
    return int(n * OOS_SPLIT), bounds, n


# ── Part A ───────────────────────────────────────────────────────────────────
def part_a(lens, by_id):
    R = lens["runs"]
    out = {}
    facts = {}
    for rid, r in R.items():
        d = by_id[int(rid)]
        v = d.get("validate") or {}
        sel = d.get("selection") or {}
        pinned, free = is_pinned_file(d["strategy"])
        rows = fold_rows(d)
        pk = [k for k in rows[0] if k in (r.get("param_drift", {}).get("search_range_widths") or {})]
        plist = params_from_rows(d, pk)
        ksplit, bounds, n = stage_a_split(d)
        folds = sorted(bounds)
        inside = [j for j in folds if bounds[j][1] <= ksplit]
        after = [j for j in folds if bounds[j][0] >= ksplit]
        strad = [j for j in folds if j not in inside and j not in after]
        facts[rid] = {
            "strategy": d["strategy"], "instrument": d["instrument"], "timeframe": d["timeframe"],
            "famKey": d.get("famKey"), "famSeq": d.get("famSeq"), "lens_family": r["family"],
            "starred": bool(d.get("starred")), "mode": v.get("wf_best_mode"),
            "pinned_file": pinned, "free_knobs": free, "lens_is_pinned": r["is_pinned_single_config"],
            "identical_params_all_folds": identical_all_folds(plist),
            "lens_share_identical": r["param_drift"]["share_identical_pairs"],
            "fold1_trades": int(rows[0].get("oos_trades") or 0),
            "is_max_crowned": sel.get("is_max_crowned"),
            "n_bars_opt": n, "stage_a_ksplit": ksplit,
            "folds_inside_stageA_IS": inside, "folds_after_stageA_IS": after, "fold_straddling": strad,
            "wf_rolling": {k: (v.get("wf_rolling") or {}).get(k) for k in ("oos_net", "held", "n_folds", "fold_frac", "wfe")},
            "wf_anchored": {k: (v.get("wf_anchored") or {}).get(k) for k in ("oos_net", "held", "n_folds", "fold_frac", "wfe")},
        }
        # A9 crowned vs IS-max from the doc
        cands = sel.get("candidates") or []
        if cands:
            cr = next((c for c in cands if c.get("crowned")), None)
            im = max(cands, key=lambda c: c.get("is_pnl") or 0)

            def lbn(c):
                l = c.get("lockbox")
                return (l.get("total_pnl") if isinstance(l, dict) else (0.0 if l is None else None))
            facts[rid]["crowned"] = {"is_pnl": cr.get("is_pnl"), "wf_oos_pnl": cr.get("wf_oos_pnl"), "lockbox_pnl": lbn(cr)} if cr else None
            facts[rid]["is_max"] = {"is_pnl": im.get("is_pnl"), "wf_oos_pnl": im.get("wf_oos_pnl"), "lockbox_pnl": lbn(im)}
    out["run_facts"] = facts

    # sets
    all_ids = list(R)
    pinned_ids = [i for i in all_ids if facts[i]["pinned_file"]]
    cold_ids = [i for i in all_ids if facts[i]["fold1_trades"] == 0]
    clean = [i for i in all_ids if i not in pinned_ids and i not in cold_ids]
    ident_ids = [i for i in clean if facts[i]["identical_params_all_folds"]]
    clean_nonident = [i for i in clean if i not in ident_ids]
    out["sets"] = {"all": all_ids, "pinned": pinned_ids, "cold_fold1_zero": cold_ids, "clean": clean,
                   "clean_identical_params_all_folds": ident_ids, "clean_non_identical": clean_nonident,
                   "lens_headline_filtered_ids_match": sorted(clean) == sorted(
                       set(all_ids) - set(lens["aggregate"]["headline_filtered"]["excluded_pinned_ids"])
                       - set(lens["aggregate"]["headline_filtered"]["excluded_cold_or_low_freq_zero_fold1_trades_ids"]))}

    def fam_counts(ids):
        c = {}
        for i in ids:
            c[facts[i]["famKey"]] = c.get(facts[i]["famKey"], 0) + 1
        return c
    out["famKey_counts"] = {"all": fam_counts(all_ids), "clean": fam_counts(clean),
                            "clean_non_identical": fam_counts(clean_nonident)}
    # exact duplicate fold rows (same code under two names)
    sig = {}
    for i in all_ids:
        rows = fold_rows(by_id[int(i)])
        s = tuple((int(r["fold"]), int(r.get("oos_trades") or 0), round(float(r.get("oos_pnl") or 0), 2)) for r in rows)
        sig.setdefault(s, []).append(i)
    out["duplicate_fold_rows"] = [v for v in sig.values() if len(v) > 1]

    # A1 + A2 + A3: ratios
    def g(i, win, key):
        return (R[i]["pools"].get(win) or {}).get(key)
    keys = [("frozen1_over_retuned_net", "window_2_N", "ratio_frozen1_over_retuned_net"),
            ("frozen1_over_retuned_pf", "window_2_N", "ratio_frozen1_over_retuned_pf"),
            ("champion_over_retuned_net", "window_2_N", "ratio_champion_over_retuned_net"),
            ("champion_over_retuned_pf", "window_2_N", "ratio_champion_over_retuned_pf"),
            ("defaults_over_retuned_net", "window_2_N", "ratio_defaults_over_retuned_net"),
            ("defaults_over_retuned_pf", "window_2_N", "ratio_defaults_over_retuned_pf"),
            ("frozen_mid_over_retuned_net", "window_mid_N", "ratio_frozen_mid_over_retuned_net"),
            ("frozen_mid_over_retuned_pf", "window_mid_N", "ratio_frozen_mid_over_retuned_pf")]
    agg = {}
    for setname, ids in (("clean_21", clean), ("clean_non_identical", clean_nonident),
                         ("non_pinned", [i for i in all_ids if i not in pinned_ids]), ("all", all_ids)):
        blk = {"n_runs": len(ids), "n_famKey_clusters": len(fam_counts(ids))}
        for name, win, key in keys:
            vals = [g(i, win, key) for i in ids]
            blk[name] = {"per_run": med_ci(vals), "sign": sign_count(vals),
                         "cluster": cluster_med_ci([(facts[i]["famKey"], g(i, win, key)) for i in ids])}
        agg[setname] = blk
    out["A1_A2_A3_ratios_from_lens_json"] = agg

    # A4 learning curve with ties split
    lc = {}
    for setname, ids in (("clean_21", clean), ("clean_non_identical", clean_nonident)):
        win = loss = tie = 0
        per_run = []
        per_cluster_pairs = []
        for i in ids:
            w = l = t = 0
            for row in R[i]["learning_curve"]:
                if row.get("tuned_beats_frozen1_net") is None:
                    continue
                if row["tuned_net"] == row["frozen1_net"] and row["tuned_trades"] == row["frozen1_trades"]:
                    t += 1
                elif row["tuned_net"] > row["frozen1_net"]:
                    w += 1
                else:
                    l += 1
            win += w; loss += l; tie += t
            if w + l:
                per_run.append(w / (w + l))
                per_cluster_pairs.append((facts[i]["famKey"], w / (w + l)))
        lc[setname] = {"wins": win, "losses": loss, "ties_identical_cell": tie,
                       "lens_share_counting_ties_as_loss": round(win / (win + loss + tie), 4) if (win + loss + tie) else None,
                       "share_among_non_ties": round(win / (win + loss), 4) if (win + loss) else None,
                       "per_run_share_median": med_ci(per_run), "cluster": cluster_med_ci(per_cluster_pairs)}
    out["A4_learning_curve"] = lc

    # A5 rolling vs anchored on raw oos_net (both schemes ran n_folds == same)
    sc = {}
    for setname, ids in (("clean_21", clean), ("clean_non_identical", clean_nonident), ("all", all_ids)):
        raw, lens_style, pairs = [], [], []
        for i in ids:
            wr, wa = facts[i]["wf_rolling"], facts[i]["wf_anchored"]
            if not wr["oos_net"] or not wa["oos_net"] or wr["n_folds"] != wa["n_folds"] or wa["oos_net"] <= 0:
                continue
            raw.append(wr["oos_net"] / wa["oos_net"]); pairs.append((facts[i]["famKey"], wr["oos_net"] / wa["oos_net"]))
            if wr["held"] and wa["held"]:
                lens_style.append((wr["oos_net"] / wr["held"]) / (wa["oos_net"] / wa["held"]))
        sc[setname] = {"raw_oos_net_ratio": med_ci(raw), "sign": sign_count(raw), "cluster": cluster_med_ci(pairs),
                       "lens_style_per_held_fold_ratio": med_ci(lens_style),
                       "note": "validate.py _run_wf: held = count of folds with oos_pf > 1 (profitable folds), NOT folds run; n_folds is the same for both schemes so raw oos_net is the like-for-like number"}
    out["A5_rolling_vs_anchored"] = sc

    # A6 mid-window diag inclusion (net only from saved data)
    a6 = {}
    for i in clean:
        r = R[i]
        m = r["pools"].get("window_mid_N") or {}
        mid = m.get("mid_fold")
        diag = {c["fold"]: c for c in r["diagonal_checks"]}
        if not mid or mid not in diag:
            continue
        fm, rt = m["frozen_mid"]["net"], m["re_tuned"]["net"]
        dn = diag[mid]["net"]
        a6[i] = {"mid_fold": mid, "lens_ratio_net": m.get("ratio_frozen_mid_over_retuned_net"),
                 "ratio_net_excluding_mid_diag": (round((fm - dn) / (rt - dn), 4) if (rt - dn) else None),
                 "diag_share_of_retuned_window_net": (round(dn / rt, 4) if rt else None)}
    vals = [a6[i]["ratio_net_excluding_mid_diag"] for i in a6]
    out["A6_mid_window_excluding_diag_from_saved"] = {
        "per_run": a6, "median": med_ci(vals), "sign": sign_count(vals),
        "cluster": cluster_med_ci([(facts[i]["famKey"], a6[i]["ratio_net_excluding_mid_diag"]) for i in a6]),
        "lens_median_incl_diag": med_ci([(R[i]["pools"].get("window_mid_N") or {}).get("ratio_frozen_mid_over_retuned_net") for i in clean])}

    # A7 diagonal check vs doc rows
    a7 = {"runs_checked": 0, "folds_checked": 0, "mismatch": []}
    for i in all_ids:
        rows = {int(r["fold"]): r for r in fold_rows(by_id[int(i)])}
        a7["runs_checked"] += 1
        for c in R[i]["diagonal_checks"]:
            a7["folds_checked"] += 1
            row = rows[c["fold"]]
            if c["trades"] != int(row.get("oos_trades") or 0) or abs((c["net"] - c["d_net"]) - float(row.get("oos_pnl") or 0)) > 0.01 or not c["ok"]:
                a7["mismatch"].append({"id": i, "fold": c["fold"], "lens": c, "doc": {k: row.get(k) for k in ("oos_trades", "oos_pnl", "oos_pf")}})
    out["A7_diag_consistency"] = a7

    # A8 Stage A overlap summary
    a8 = {}
    for i in clean:
        f = facts[i]
        w2n = [j for j in sorted(f["folds_inside_stageA_IS"] + f["folds_after_stageA_IS"] + f["fold_straddling"]) if j >= 2]
        a8[i] = {"ksplit": f["stage_a_ksplit"], "n_bars": f["n_bars_opt"],
                 "inside_IS": [j for j in f["folds_inside_stageA_IS"] if j >= 2],
                 "straddle": f["fold_straddling"], "after_IS": f["folds_after_stageA_IS"],
                 "share_of_2N_folds_inside_or_straddling_IS": round(
                     sum(1 for j in w2n if j not in f["folds_after_stageA_IS"]) / len(w2n), 3),
                 "is_max_crowned": f["is_max_crowned"]}
    out["A8_stage_a_overlap"] = {"per_run": a8,
                                 "is_max_crowned_count_clean": sum(1 for i in clean if facts[i]["is_max_crowned"]),
                                 "n_clean": len(clean)}

    # A9 crowned vs IS-max
    a9 = []
    for i in all_ids:
        f = facts[i]
        if f.get("crowned") and f.get("is_max") and f["crowned"] != f["is_max"]:
            a9.append({"id": i, "famKey": f["famKey"], "crowned_wf": f["crowned"]["wf_oos_pnl"], "ismax_wf": f["is_max"]["wf_oos_pnl"],
                       "crowned_lb": f["crowned"]["lockbox_pnl"], "ismax_lb": f["is_max"]["lockbox_pnl"]})
    n_cr_better_lb = sum(1 for x in a9 if x["crowned_lb"] is not None and x["ismax_lb"] is not None and x["crowned_lb"] > x["ismax_lb"])
    n_cmp = sum(1 for x in a9 if x["crowned_lb"] is not None and x["ismax_lb"] is not None)
    out["A9_crowned_vs_ismax"] = {"rows": a9, "n_recrowned": len(a9), "n_lockbox_comparable": n_cmp,
                                  "crowned_lockbox_better_count": n_cr_better_lb}
    return out


# ── Part B: replay ───────────────────────────────────────────────────────────
def replay_run(d, log=print):
    from tools.backfill_wf_oos import rebuild_plan, fold_params
    from augur_engine.auto import _auto_space_from_params, make_slice_evaluator
    from augur_engine.data import find_master, load_master_arrays
    from augur_engine.strategies import load_strategy
    from augur_engine.engine import run_backtest

    plan, reason = rebuild_plan(d)
    if plan is None:
        return None, reason
    mod = load_strategy(plan["strategy"])
    dp = getattr(mod, "DEFAULT_PARAMS", {}) or {}
    pkeys = list(_auto_space_from_params(dp).keys())
    rows = [fb["row"] for fb in plan["folds"]]
    plist, preason = fold_params(pkeys, rows)
    if preason:
        return None, preason
    master = find_master(plan["instrument"], plan["timeframe"], plan["session"], plan["source"])
    if master is None:
        return None, "no master"
    t0 = time.time()
    arrays = load_master_arrays(master, date_from=plan["date_from"], date_to=plan["date_to"])
    n = len(arrays["close"])
    if n != plan["expect_n"]:
        return None, f"bars mismatch {n} vs {plan['expect_n']}"
    ev = make_slice_evaluator(mod, arrays, plan["cost_pts"])
    bounds = {fb["fold"]: (fb["te_s"], fb["te_e"]) for fb in plan["folds"]}
    folds = [fb["fold"] for fb in plan["folds"]]

    def run(j, params):
        a, b = bounds[j]
        om = ev(a, b, params, keep_trades=True)
        pnls = [round(float(t[2]), DP) for t in (om.get("trades") or [])] if om else []
        return cell(pnls)

    matrix = {}
    for ii, i in enumerate(folds):
        matrix[i] = {j: run(j, plist[ii]) for j in folds if j >= i}
    diag_ok = []
    for ii, i in enumerate(folds):
        row = rows[ii]
        c = matrix[i][i]
        ok = (c["trades"] == int(row.get("oos_trades") or 0)
              and abs(c["net"] - float(row.get("oos_pnl") or 0)) <= max(0.05, 1e-4 * abs(float(row.get("oos_pnl") or 0))))
        diag_ok.append({"fold": i, "ok": ok, "trades": c["trades"], "doc_trades": row.get("oos_trades"),
                        "net": c["net"], "doc_net": row.get("oos_pnl")})
    v = d.get("validate") or {}
    champ = v.get("champion")
    if not isinstance(champ, dict) or not champ:
        sel = d.get("selection") or {}
        cr = [c for c in (sel.get("candidates") or []) if c.get("crowned")]
        champ = cr[0]["params"] if cr else None
    champ = {k: champ.get(k) for k in pkeys} if champ else None
    defaults = {k: dp[k].get("default") for k in pkeys if isinstance(dp.get(k), dict)}
    champ_row = {j: run(j, champ) for j in folds} if champ else None
    def_row = {j: run(j, defaults) for j in folds} if defaults else None
    t_wf = time.time() - t0

    # sealed lockbox, as validate.py Stage C: run_backtest(date_from=lb_from, date_to=date_to)
    lbw = (v.get("windows") or {}).get("lockbox") or []
    lockbox = None
    if len(lbw) == 2 and lbw[0] and lbw[1]:
        def lbrun(params):
            m = run_backtest(mod, instrument=plan["instrument"], timeframe=plan["timeframe"],
                             session=plan["session"], source=plan["source"], params=params,
                             cost_pts=plan["cost_pts"], date_from=lbw[0], date_to=lbw[1], return_trades=True)
            pnls = [round(float(t[2]), DP) for t in (m.get("trades") or [])] if m else []
            return cell(pnls)
        lockbox = {"window": lbw, "champion": lbrun(champ) if champ else None,
                   "last_fold_params": lbrun(plist[-1]), "fold1_params": lbrun(plist[0]),
                   "mid_fold_params": lbrun(plist[min(max((len(folds) + 1) // 2, 1), len(folds) - 1)]),
                   "defaults": lbrun(defaults) if defaults else None,
                   "doc_lockbox": {"pnl": (v.get("lockbox") or {}).get("pnl"), "trades": (v.get("lockbox") or {}).get("trades"),
                                   "pf": (v.get("lockbox") or {}).get("pf")}}
        lockbox["champion_matches_doc"] = (lockbox["champion"] is not None and lockbox["doc_lockbox"]["trades"] is not None
                                           and lockbox["champion"]["trades"] == int(lockbox["doc_lockbox"]["trades"] or 0)
                                           and abs(lockbox["champion"]["net"] - float(lockbox["doc_lockbox"]["pnl"] or 0)) < 0.5)
    log(f"  #{d['id']} {plan['strategy']} {n} bars, {len(folds)} folds, wf {t_wf:.1f}s, total {time.time() - t0:.1f}s, diag ok={all(x['ok'] for x in diag_ok)}")
    return {"id": d["id"], "strategy": plan["strategy"], "mode": plan["mode"], "folds": folds,
            "bounds": {str(k): v_ for k, v_ in bounds.items()}, "n_bars": n,
            "params": {str(f): p for f, p in zip(folds, plist)}, "champion": champ, "defaults": defaults,
            "matrix": {str(i): {str(j): c for j, c in r.items()} for i, r in matrix.items()},
            "champion_row": {str(j): c for j, c in champ_row.items()} if champ_row else None,
            "defaults_row": {str(j): c for j, c in def_row.items()} if def_row else None,
            "diag": diag_ok, "lockbox": lockbox}, None


def part_b(ids, by_id, log=print):
    saved = {}
    if os.path.exists(MATRIX_PATH):
        with open(MATRIX_PATH, "r", encoding="utf-8") as f:
            saved = json.load(f)
    todo = [i for i in ids if str(i) not in saved]
    if not todo:
        return saved
    common.low_priority()
    common.setup_data_env()
    os.environ.setdefault("AUGUR_TRIAL_CACHE", "1")
    with common.cpu_lock("verify_frozen-vs-retuned replay"):
        for k, i in enumerate(todo, 1):
            log(f"[{k}/{len(todo)}] #{i} ...")
            try:
                res, reason = replay_run(by_id[int(i)], log=log)
            except Exception as e:
                res, reason = None, f"{type(e).__name__}: {e}"
            saved[str(i)] = res if res else {"id": i, "error": reason}
            if res is None:
                log(f"  FAILED #{i}: {reason}")
            with open(MATRIX_PATH, "w", encoding="utf-8") as f:
                json.dump(saved, f, default=str)
    return saved


# ── Part C: recompute from the replayed matrix ───────────────────────────────
def part_c(mat, lens, facts, sets):
    R = lens["runs"]
    per = {}
    for rid, m in mat.items():
        if not m or m.get("error"):
            continue
        folds = m["folds"]
        M = {int(i): {int(j): c for j, c in r.items()} for i, r in m["matrix"].items()}
        ch = {int(j): c for j, c in (m.get("champion_row") or {}).items()} or None
        df = {int(j): c for j, c in (m.get("defaults_row") or {}).items()} or None
        N = len(folds)
        lo2, hiN = folds[1], folds[-1]
        mid = folds[min(max((N + 1) // 2, 1), N - 1)]
        def P(rowcells, lo, hi):
            return pool([rowcells[j] for j in folds if lo <= j <= hi and j in rowcells])
        diag = {j: M[j][j] for j in folds}
        rt2 = P(diag, lo2, hiN); fr2 = P(M[folds[0]], lo2, hiN)
        ch2 = P(ch, lo2, hiN) if ch else None; df2 = P(df, lo2, hiN) if df else None
        rtm = P(diag, mid, hiN); frm = P(M[mid], mid, hiN)
        rtm1 = P(diag, mid + 1, hiN); frm1 = P(M[mid], mid + 1, hiN)
        chm1 = P(ch, mid + 1, hiN) if ch else None
        # Stage A overlap split
        f = facts[rid]
        inside = [j for j in f["folds_inside_stageA_IS"] if j >= lo2]
        after = [j for j in f["folds_after_stageA_IS"] if j >= lo2]
        def Pset(rowcells, js):
            return pool([rowcells[j] for j in js if j in rowcells]) if js else None
        rt_in, rt_af = Pset(diag, inside), Pset(diag, after)
        ch_in, ch_af = (Pset(ch, inside), Pset(ch, after)) if ch else (None, None)
        fr_in, fr_af = Pset(M[folds[0]], inside), Pset(M[folds[0]], after)
        # learning curve with ties
        lc = []
        for idx in range(1, N - 1):
            i, nx = folds[idx], folds[idx + 1]
            t, z = M[i][nx], M[folds[0]][nx]
            lc.append("tie" if (t["net"] == z["net"] and t["trades"] == z["trades"]) else ("win" if t["net"] > z["net"] else "loss"))
        lens_w2 = R[rid]["pools"].get("window_2_N") or {}
        lens_wm = R[rid]["pools"].get("window_mid_N") or {}
        lb = m.get("lockbox") or {}
        per[rid] = {
            "famKey": f["famKey"], "diag_all_ok": all(x["ok"] for x in m["diag"]),
            "w2N": {"re_tuned": rt2, "frozen1": fr2, "champion": ch2, "defaults": df2,
                    "r_frozen1_net": ratio(fr2, rt2, "net"), "r_frozen1_pf": ratio(fr2, rt2, "pf"),
                    "r_champ_net": ratio(ch2, rt2, "net") if ch2 else None, "r_champ_pf": ratio(ch2, rt2, "pf") if ch2 else None,
                    "r_def_net": ratio(df2, rt2, "net") if df2 else None, "r_def_pf": ratio(df2, rt2, "pf") if df2 else None},
            "lens_w2N_match": {"re_tuned_net_diff": round(rt2["net"] - (lens_w2.get("re_tuned") or {}).get("net", float("nan")), 4),
                               "frozen1_net_diff": round(fr2["net"] - (lens_w2.get("frozen_1") or {}).get("net", float("nan")), 4),
                               "champion_net_diff": (round(ch2["net"] - (lens_w2.get("champion") or {}).get("net", float("nan")), 4) if ch2 else None),
                               "re_tuned_trades_diff": rt2["trades"] - (lens_w2.get("re_tuned") or {}).get("trades", -1)},
            "mid": {"mid_fold": mid, "incl_diag": {"re_tuned": rtm, "frozen_mid": frm, "r_net": ratio(frm, rtm, "net"), "r_pf": ratio(frm, rtm, "pf"),
                                                    "lens_r_net": lens_wm.get("ratio_frozen_mid_over_retuned_net")},
                    "excl_diag": {"re_tuned": rtm1, "frozen_mid": frm1, "champion": chm1,
                                  "r_net": ratio(frm1, rtm1, "net"), "r_pf": ratio(frm1, rtm1, "pf"),
                                  "r_champ_net": ratio(chm1, rtm1, "net") if chm1 else None, "r_champ_pf": ratio(chm1, rtm1, "pf") if chm1 else None}},
            "stageA_split": {"inside_IS_folds": inside, "after_IS_folds": after,
                             "inside": {"re_tuned": rt_in, "champion": ch_in, "frozen1": fr_in,
                                        "r_champ_net": ratio(ch_in, rt_in, "net") if (ch_in and rt_in) else None,
                                        "r_champ_pf": ratio(ch_in, rt_in, "pf") if (ch_in and rt_in) else None},
                             "after": {"re_tuned": rt_af, "champion": ch_af, "frozen1": fr_af,
                                       "r_champ_net": ratio(ch_af, rt_af, "net") if (ch_af and rt_af) else None,
                                       "r_champ_pf": ratio(ch_af, rt_af, "pf") if (ch_af and rt_af) else None,
                                       "r_frozen1_net": ratio(fr_af, rt_af, "net") if (fr_af and rt_af) else None,
                                       "r_frozen1_pf": ratio(fr_af, rt_af, "pf") if (fr_af and rt_af) else None}},
            "learning_curve": {"wins": lc.count("win"), "losses": lc.count("loss"), "ties": lc.count("tie")},
            "lockbox": ({k: (lb.get(k) or {}).get("net") for k in ("champion", "last_fold_params", "fold1_params", "mid_fold_params", "defaults")}
                        | {"trades": {k: (lb.get(k) or {}).get("trades") for k in ("champion", "last_fold_params", "fold1_params", "defaults")},
                           "pf": {k: (lambda c: round(c["gross_win"] / c["gross_loss"], 4) if c and c["gross_loss"] > 0 else None)(lb.get(k))
                                  for k in ("champion", "last_fold_params", "fold1_params", "defaults")},
                           "champion_matches_doc": lb.get("champion_matches_doc"), "doc": lb.get("doc_lockbox")}) if lb else None,
        }
    # aggregates
    def agg(ids, label):
        ids = [i for i in ids if i in per]
        blk = {"label": label, "n_runs": len(ids), "n_famKey_clusters": len({per[i]["famKey"] for i in ids})}
        def add(name, fn):
            vals = [fn(per[i]) for i in ids]
            blk[name] = {"per_run": med_ci(vals), "sign": sign_count(vals),
                         "cluster": cluster_med_ci([(per[i]["famKey"], fn(per[i])) for i in ids])}
        add("frozen1_over_retuned_net", lambda p: p["w2N"]["r_frozen1_net"])
        add("frozen1_over_retuned_pf", lambda p: p["w2N"]["r_frozen1_pf"])
        add("champion_over_retuned_net", lambda p: p["w2N"]["r_champ_net"])
        add("champion_over_retuned_pf", lambda p: p["w2N"]["r_champ_pf"])
        add("defaults_over_retuned_net", lambda p: p["w2N"]["r_def_net"])
        add("defaults_over_retuned_pf", lambda p: p["w2N"]["r_def_pf"])
        add("frozen_mid_over_retuned_net_INCL_diag(lens)", lambda p: p["mid"]["incl_diag"]["r_net"])
        add("frozen_mid_over_retuned_pf_INCL_diag(lens)", lambda p: p["mid"]["incl_diag"]["r_pf"])
        add("frozen_mid_over_retuned_net_EXCL_diag", lambda p: p["mid"]["excl_diag"]["r_net"])
        add("frozen_mid_over_retuned_pf_EXCL_diag", lambda p: p["mid"]["excl_diag"]["r_pf"])
        add("champion_over_retuned_net_folds_after_mid", lambda p: p["mid"]["excl_diag"]["r_champ_net"])
        add("champion_over_retuned_net_INSIDE_stageA_IS", lambda p: p["stageA_split"]["inside"]["r_champ_net"])
        add("champion_over_retuned_pf_INSIDE_stageA_IS", lambda p: p["stageA_split"]["inside"]["r_champ_pf"])
        add("champion_over_retuned_net_AFTER_stageA_IS", lambda p: p["stageA_split"]["after"]["r_champ_net"])
        add("champion_over_retuned_pf_AFTER_stageA_IS", lambda p: p["stageA_split"]["after"]["r_champ_pf"])
        add("frozen1_over_retuned_net_AFTER_stageA_IS", lambda p: p["stageA_split"]["after"]["r_frozen1_net"])
        add("frozen1_over_retuned_pf_AFTER_stageA_IS", lambda p: p["stageA_split"]["after"]["r_frozen1_pf"])
        # lockbox
        def lbr(p, k):
            lb = p.get("lockbox")
            if not lb or lb.get("champion") is None or lb.get(k) is None or not lb["champion"]:
                return None
            return round(lb[k] / lb["champion"], 4) if lb["champion"] > 0 else None
        add("lockbox_lastfold_over_champion_net", lambda p: lbr(p, "last_fold_params"))
        add("lockbox_fold1_over_champion_net", lambda p: lbr(p, "fold1_params"))
        add("lockbox_defaults_over_champion_net", lambda p: lbr(p, "defaults"))
        lbsign = {"last_fold_beats_champion": 0, "champion_beats_last_fold": 0, "tie": 0, "n": 0,
                  "last_fold_positive": 0, "champion_positive": 0, "fold1_positive": 0, "defaults_positive": 0}
        for i in ids:
            lb = per[i].get("lockbox")
            if not lb or lb.get("champion") is None or lb.get("last_fold_params") is None:
                continue
            lbsign["n"] += 1
            if lb["last_fold_params"] > lb["champion"]:
                lbsign["last_fold_beats_champion"] += 1
            elif lb["last_fold_params"] < lb["champion"]:
                lbsign["champion_beats_last_fold"] += 1
            else:
                lbsign["tie"] += 1
            lbsign["last_fold_positive"] += int(lb["last_fold_params"] > 0)
            lbsign["champion_positive"] += int(lb["champion"] > 0)
            lbsign["fold1_positive"] += int((lb.get("fold1_params") or 0) > 0)
            lbsign["defaults_positive"] += int((lb.get("defaults") or 0) > 0)
        blk["lockbox_sign"] = lbsign
        # learning curve
        w = sum(per[i]["learning_curve"]["wins"] for i in ids); l = sum(per[i]["learning_curve"]["losses"] for i in ids)
        t = sum(per[i]["learning_curve"]["ties"] for i in ids)
        blk["learning_curve"] = {"wins": w, "losses": l, "ties": t,
                                 "share_ties_as_loss": round(w / (w + l + t), 4) if (w + l + t) else None,
                                 "share_non_ties": round(w / (w + l), 4) if (w + l) else None}
        blk["diag_all_ok"] = all(per[i]["diag_all_ok"] for i in ids)
        blk["lockbox_champion_matches_doc"] = {i: (per[i].get("lockbox") or {}).get("champion_matches_doc") for i in ids}
        return blk
    out = {"per_run": per,
           "agg_clean_21": agg(sets["clean"], "clean (lens headline_filtered set)"),
           "agg_clean_non_identical": agg(sets["clean_non_identical"], "clean minus runs whose fold params never change"),
           "agg_all_30": agg(sets["all"], "all replayed runs")}
    # per-crown rows
    out["crowns"] = {i: per[i] for i in ("257", "335", "243") if i in per}
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-replay", action="store_true")
    ap.add_argument("--ids", default="")
    a = ap.parse_args()
    with open(LENS_PATH, "r", encoding="utf-8") as f:
        lens = json.load(f)
    runs = common.load_runs()
    by_id = {r.get("id"): r for r in runs}
    ids = [i for i in lens["runs"]]
    if a.ids:
        ids = [i for i in ids if i in a.ids.split(",")]
    print(f"[verify] {len(ids)} run(s) from lens_frozen.json")
    A = part_a(lens, by_id)
    mat = {}
    if not a.no_replay:
        mat = part_b(ids, by_id)
    elif os.path.exists(MATRIX_PATH):
        with open(MATRIX_PATH, "r", encoding="utf-8") as f:
            mat = json.load(f)
    C = part_c(mat, lens, A["run_facts"], A["sets"]) if mat else None
    out = {"generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
           "lens_generated_at": lens.get("generated_at"),
           "part_a": A, "part_c": C}
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1, default=str)
    print(f"[verify] saved {OUT_PATH}")
    # console summary
    print("\n== sets ==")
    for k, v in A["sets"].items():
        print(f"  {k}: {v if not isinstance(v, list) else (len(v), v)}")
    print("  famKey counts:", A["famKey_counts"])
    print("  duplicate fold rows:", A["duplicate_fold_rows"])
    print("  diag consistency mismatches:", len(A["A7_diag_consistency"]["mismatch"]))
    print("\n== A1-A3 ratios (from lens JSON) ==")
    for s, blk in A["A1_A2_A3_ratios_from_lens_json"].items():
        print(f" [{s}] n={blk['n_runs']} clusters={blk['n_famKey_clusters']}")
        for k, v in blk.items():
            if isinstance(v, dict) and "per_run" in v:
                print(f"   {k:32s} per-run {v['per_run']['median']} CI {v['per_run']['ci95']} n={v['per_run']['n']} | sign {v['sign']} | cluster med-of-med {v['cluster']['median_of_cluster_medians']} clusterCI {v['cluster']['cluster_boot_ci95']} k={v['cluster']['n_clusters']} | {v['cluster']['cluster_medians']}")
    print("\n== A4 learning curve ==", json.dumps(A["A4_learning_curve"], default=str))
    print("\n== A5 rolling vs anchored ==")
    for s, v in A["A5_rolling_vs_anchored"].items():
        print(f"  [{s}] raw {v['raw_oos_net_ratio']} sign {v['sign']} cluster {v['cluster']['median_of_cluster_medians']} {v['cluster']['cluster_boot_ci95']} | lens-style {v['lens_style_per_held_fold_ratio']}")
    print("\n== A6 mid excl diag (net, saved) ==", A["A6_mid_window_excluding_diag_from_saved"]["median"],
          A["A6_mid_window_excluding_diag_from_saved"]["sign"], "lens incl:", A["A6_mid_window_excluding_diag_from_saved"]["lens_median_incl_diag"])
    print("\n== A8 stage A overlap ==")
    for i, v in A["A8_stage_a_overlap"]["per_run"].items():
        print(f"  #{i} inside {v['inside_IS']} straddle {v['straddle']} after {v['after_IS']} share {v['share_of_2N_folds_inside_or_straddling_IS']} is_max_crowned={v['is_max_crowned']}")
    print("  is_max_crowned in clean:", A["A8_stage_a_overlap"]["is_max_crowned_count_clean"], "/", A["A8_stage_a_overlap"]["n_clean"])
    print("\n== A9 crowned vs IS-max ==", {k: v for k, v in A["A9_crowned_vs_ismax"].items() if k != "rows"})
    if C:
        print("\n== PART C (replayed) ==")
        for s in ("agg_clean_21", "agg_clean_non_identical", "agg_all_30"):
            blk = C[s]
            print(f" [{s}] n={blk['n_runs']} clusters={blk['n_famKey_clusters']} diag_all_ok={blk['diag_all_ok']}")
            for k, v in blk.items():
                if isinstance(v, dict) and "per_run" in v:
                    print(f"   {k:48s} per-run {v['per_run']['median']} CI {v['per_run']['ci95']} n={v['per_run']['n']} | sign {v['sign']} | cluster {v['cluster']['median_of_cluster_medians']} {v['cluster']['cluster_boot_ci95']} k={v['cluster']['n_clusters']}")
            print("   lockbox_sign", blk["lockbox_sign"])
            print("   learning_curve", blk["learning_curve"])
            print("   lockbox champion matches doc:", blk["lockbox_champion_matches_doc"])
        print("\n== crowns ==")
        for i, p in C["crowns"].items():
            print(f" #{i} w2N {json.dumps(p['w2N'], default=str)}")
            print(f"     lens match {p['lens_w2N_match']}")
            print(f"     mid {json.dumps(p['mid'], default=str)}")
            print(f"     stageA {json.dumps(p['stageA_split'], default=str)}")
            print(f"     lockbox {json.dumps(p['lockbox'], default=str)}")
        print("\n== per-run lens match (2..N re_tuned/frozen1/champion net diffs) ==")
        for i, p in C["per_run"].items():
            print(f"  #{i} {p['lens_w2N_match']} diag_ok={p['diag_all_ok']} lb_match={(p.get('lockbox') or {}).get('champion_matches_doc')}")


if __name__ == "__main__":
    main()
