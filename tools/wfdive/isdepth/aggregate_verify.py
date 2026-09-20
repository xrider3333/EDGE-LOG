r"""Cross-family aggregation of verify_<run_id>.json (independent of analyze_matrix.py).

Families are ONE vote each (5 files = 5 mechanisms: TTM squeeze, ORB, NQDIP, NOISE, ENGU-Q).
Also adds a per-family candidate DISPERSION read straight from the matrix: how different are
the candidates from each other on a 1y test window (PF p10/p50/p90 across sampler configs,
share of configs with PF<1)? If the candidates barely differ, 'no ranking power' also means
'nothing to lose', and IS depth cannot matter by construction.

Usage: python tools/wfdive/isdepth/aggregate_verify.py 299 314 307 304 335
"""
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(HERE))), "_wfdive_data", "isdepth")
sys.path.insert(0, HERE)
from verify_isdepth import Matrix, origins, shift, fin  # noqa: E402  (my own module)

NAMES = {299: "TTM squeeze", 314: "ORB", 307: "NQDIP", 304: "NOISE", 335: "ENGU-Q R2"}


def r(x, d=2):
    return None if x is None else round(x, d)


def dispersion(rid):
    M = Matrix(rid)
    ors = [o for o in origins(M.t_from, M.t_to) if shift(o, -6) >= M.t_from and shift(o, 1) <= M.t_to]
    rows = []
    for o in ors:
        st = M.stats(o, shift(o, 1))
        pf = st["pf"][:M.c_total]; n = st["n"][:M.c_total]; net = st["net"][:M.c_total]
        ok = n >= 5
        pf = np.where(np.isfinite(pf), pf, 10.0)[ok]
        if pf.size < 10:
            continue
        rows.append({"pf_p10": float(np.percentile(pf, 10)), "pf_p50": float(np.percentile(pf, 50)),
                     "pf_p90": float(np.percentile(pf, 90)), "frac_pf_below_1": float((pf < 1).mean()),
                     "frac_net_neg": float((net[ok] < 0).mean()),
                     "net_p90_over_p50": (float(np.percentile(net[ok], 90) / np.percentile(net[ok], 50))
                                          if np.percentile(net[ok], 50) > 0 else None)})
    return {k: r(float(np.median([x[k] for x in rows if x[k] is not None])), 3) for k in rows[0]} if rows else {}


def main(rids):
    fam = {}
    for rid in rids:
        v = json.load(open(os.path.join(DATA, f"verify_{rid}.json"), encoding="utf-8"))
        f = v["V0_facts"]; L = v["V1_learning_curve"]; c8 = L["common_origins_Kle8"]
        seed0 = {K: r(d["median"], 1) for K, d in c8["seed0"].items()}
        paired = {K: (r(d["median_diff_pct_vs_K3"], 1), f"{d['sign_test']['n_pos']}/{d['sign_test']['n_nonzero']}", r(d["sign_test"]["p"], 2))
                  for K, d in c8["paired_vs_K3_seed0"].items()}
        R = v["V4_rank_persistence"]["by_L_fixed_1y_future"]
        T = v["V4_rank_persistence"]["ten_finalists_pipeline_mirror"]["by_L"]
        D = v["V5_designs_origin_level"]["designs"]
        S7 = v["V7_pf_shrinkage_by_K"]["common_origins_Kle8"]
        fam[rid] = {
            "family": NAMES.get(rid, f.get("strategy")), "strategy": f["strategy"],
            "unique_configs": f["n_unique_configs_in_pool"], "c_total": f["c_total"],
            "trades_per_year": f["champion_trades_per_year"], "hold_days_max": r(f["hold_days_max"], 1),
            "K1_eligibility_median": r(f["eligibility_frac_seed0_at_K1_per_origin"]["median"], 2),
            "pct_by_K_common8_seed0": seed0,
            "pct_by_K_common8_fullpool": {K: r(d["median"], 1) for K, d in c8["fullpool"].items()},
            "paired_vs_K3": paired,
            "within_origin_rho_K_pct": r(c8["within_origin_spearman_K_vs_pct"]["median"], 2),
            "crown_pct_hindsight": r(c8["champ_pct"]["median"], 1), "default_pct": r(c8["default_pct"]["median"], 1),
            "rank_rho_net_by_L": {Lk: (r(d["rho_net"]["median"], 2), r(d["rho_net"]["lo"], 2), r(d["rho_net"]["hi"], 2)) for Lk, d in R.items()},
            "rank_top_minus_bottom_decile_by_L": {Lk: r(d["top_minus_bottom_decile"]["median"], 1) for Lk, d in R.items()},
            "finalist_rho_lb_future_by_L": {Lk: (r(d["rho_lockbox_vs_future_1y"]["median"], 2), r(d["rho_lockbox_vs_future_1y"]["lo"], 2), r(d["rho_lockbox_vs_future_1y"]["hi"], 2)) for Lk, d in T.items()},
            "finalist_rho_is_future_by_L": {Lk: r(d["rho_insample_vs_future_1y"]["median"], 2) for Lk, d in T.items()},
            "finalist_lb_best_beats_median_by_L": {Lk: r(d["p_lockbox_best_beats_finalist_median"], 2) for Lk, d in T.items()},
            "design_gate": {k: {"pass": r(d["pass_rate"], 2), "P+|pass": r(d["p_fut1y_pos_given_pass"], 2), "n_pass": d["n_pass"],
                                "P+|fail": r(d["p_fut1y_pos_given_fail"], 2), "n_fail": d["n_fail"],
                                "rho_lbpf_futpf": r(d["spearman_lockbox_pf_vs_future_pf"], 2),
                                "frozen_minus_nolb": r(d["frozen_minus_nolockbox_future_pct"]["median"], 1),
                                "frozen_sign_p": r(d["sign_test_frozen_vs_nolockbox"]["p"], 2)} for k, d in D.items()},
            "pf_shrinkage_common8": {K: r(d["median"], 2) for K, d in S7.items()},
            "pseudo_seed_distinct_picks_median": v["V3_pseudo_seeds"].get("6", {}).get("median_distinct_picks_of_30"),
            "leak_pick_changed_strict_K3": r(v["V2_leaks"].get("3", {}).get("frac_pick_changed_strict_vs_entry"), 2),
            "leak_pct_entry_vs_strict_K3": (r(v["V2_leaks"].get("3", {}).get("median_pct_entry"), 1), r(v["V2_leaks"].get("3", {}).get("median_pct_strict_no_open_trades"), 1)),
            "dispersion_1y_test_windows": dispersion(rid),
        }

    # ── pooled votes (one per family) ──
    def vote(fn):
        return {NAMES.get(rid): fn(fam[rid]) for rid in rids}
    pooled = {}
    for K in ("6", "8", "all"):
        pooled[f"paired_K{K}_vs_K3_median_diff"] = vote(lambda x: x["paired_vs_K3"][K][0])
        pooled[f"paired_K{K}_vs_K3_sign"] = vote(lambda x: x["paired_vs_K3"][K][1])
        pooled[f"paired_K{K}_vs_K3_p"] = vote(lambda x: x["paired_vs_K3"][K][2])
    pooled["families_where_any_K_ge6_beats_K3_p_lt_0.1"] = [NAMES[rid] for rid in rids
                                                           if any(fam[rid]["paired_vs_K3"][K][2] is not None and fam[rid]["paired_vs_K3"][K][2] < 0.1
                                                                  and fam[rid]["paired_vs_K3"][K][0] > 0 for K in ("6", "8", "10", "all"))]
    pooled["families_where_K3_beats_any_K_ge6_p_lt_0.1"] = [NAMES[rid] for rid in rids
                                                           if any(fam[rid]["paired_vs_K3"][K][2] is not None and fam[rid]["paired_vs_K3"][K][2] < 0.1
                                                                  and fam[rid]["paired_vs_K3"][K][0] < 0 for K in ("6", "8", "10", "all"))]
    pooled["median_pct_across_families_by_K_common8"] = {K: r(float(np.median([fam[rid]["pct_by_K_common8_seed0"][K] for rid in rids
                                                                                if fam[rid]["pct_by_K_common8_seed0"][K] is not None])), 1)
                                                         for K in ("1", "2", "3", "4", "5", "6", "8", "all")}
    pooled["rank_rho_net_median_across_families_by_L"] = {Lk: r(float(np.median([fam[rid]["rank_rho_net_by_L"][Lk][0] for rid in rids])), 2)
                                                          for Lk in fam[rids[0]]["rank_rho_net_by_L"]}
    pooled["rank_rho_net_families_CI_excludes_0_by_L"] = {Lk: [NAMES[rid] for rid in rids if fam[rid]["rank_rho_net_by_L"][Lk][1] > 0]
                                                          for Lk in fam[rids[0]]["rank_rho_net_by_L"]}
    pooled["finalist_rho_lb_future_median_by_L"] = {Lk: r(float(np.median([fam[rid]["finalist_rho_lb_future_by_L"][Lk][0] for rid in rids])), 2)
                                                    for Lk in fam[rids[0]]["finalist_rho_lb_future_by_L"]}
    pooled["finalist_rho_lb_future_families_CI_excludes_0_by_L"] = {Lk: [NAMES[rid] for rid in rids if fam[rid]["finalist_rho_lb_future_by_L"][Lk][1] > 0]
                                                                    for Lk in fam[rids[0]]["finalist_rho_lb_future_by_L"]}
    gate = {}
    for k in fam[rids[0]]["design_gate"]:
        gate[k] = {"n_fail_origins_by_family": {NAMES[rid]: fam[rid]["design_gate"][k]["n_fail"] for rid in rids},
                   "families_where_P+|pass_gt_P+|fail": [NAMES[rid] for rid in rids
                                                          if fam[rid]["design_gate"][k]["P+|fail"] is not None
                                                          and fam[rid]["design_gate"][k]["P+|pass"] > fam[rid]["design_gate"][k]["P+|fail"]],
                   "families_with_any_fail": [NAMES[rid] for rid in rids if fam[rid]["design_gate"][k]["n_fail"] > 0],
                   "median_frozen_minus_nolockbox_pct": r(float(np.median([fam[rid]["design_gate"][k]["frozen_minus_nolb"] for rid in rids])), 1),
                   "rho_lbpf_futpf_by_family": {NAMES[rid]: fam[rid]["design_gate"][k]["rho_lbpf_futpf"] for rid in rids}}
    pooled["design_gate"] = gate
    pooled["pf_shrinkage_median_across_families_by_K"] = {K: r(float(np.median([fam[rid]["pf_shrinkage_common8"][K] for rid in rids
                                                                                 if fam[rid]["pf_shrinkage_common8"][K] is not None])), 2)
                                                          for K in ("1", "2", "3", "4", "5", "6", "8", "all")}
    out = {"families": {str(rid): fam[rid] for rid in rids}, "pooled": pooled, "n_families": len(rids),
           "note": "each family = one vote; origins inside a family are 6-month steps with 1y test windows (50% overlap) and "
                   "overlapping training windows, so within-family CIs are optimistic; percentiles are era-safe, dollars are not."}
    path = os.path.join(DATA, "verify_cross.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(fin(out), f, indent=1, default=str)
    print(json.dumps(fin(pooled), indent=1, default=str))
    for rid in rids:
        print(NAMES[rid], "dispersion:", fam[rid]["dispersion_1y_test_windows"], "unique", fam[rid]["unique_configs"])
    print("wrote", path)


if __name__ == "__main__":
    main([int(x) for x in sys.argv[1:]] or [299, 314, 307, 304, 335])
