"""Compact printer for verify_<run_id>.json (and side-by-side with analysis_<run_id>.json)."""
import json
import os
import sys

DATA = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))),
                    "_wfdive_data", "isdepth")


def r1(x):
    return None if x is None else (round(x, 2) if isinstance(x, float) else x)


def cur(c):
    return {K: (r1(d["median"]), d["n"]) for K, d in c.items()}


def ci(d):
    return f"{r1(d['median'])} [{r1(d['lo'])},{r1(d['hi'])}] n={d['n']}"


def main(rid, sections):
    v = json.load(open(os.path.join(DATA, f"verify_{rid}.json"), encoding="utf-8"))
    f = v["V0_facts"]
    print(f"##### run {rid} {f['strategy']} {f['instrument']} {f['timeframe']} unique={f['n_unique_configs_in_pool']}/{f['c_total']} "
          f"(first {f['n_trials']}: {f['n_unique_configs_in_first_n_trials']}) champ_in_first={f['champion_in_first_n_trials']} "
          f"tr/yr={f['champion_trades_per_year']} hold_max_d={r1(f['hold_days_max'])} held>1d={r1(f['frac_trades_held_over_1_day'])} "
          f"K1_elig={f['eligibility_frac_seed0_at_K1_per_origin']}")
    L = v["V1_learning_curve"]
    if "1" in sections:
        print("V1 all-origins seed0 :", cur(L["all_origins_per_K"]["seed0"]))
        print("V1 all-origins fullpl:", cur(L["all_origins_per_K"]["fullpool"]))
        for k in ("common_origins_Kle8", "common_origins_Kle10"):
            c = L[k]
            print(f"V1 {k} n={c['n_origins']} from {c['first_origin']}")
            print("   seed0  :", cur(c["seed0"]))
            print("   fullpl :", cur(c["fullpool"]))
            print("   crown  :", ci(c["champ_pct"]), " default:", ci(c["default_pct"]))
            print("   paired vs K3 (median diff, n_pos/n, p):",
                  {K: (r1(d["median_diff_pct_vs_K3"]), f"{d['sign_test']['n_pos']}/{d['sign_test']['n_nonzero']}", r1(d["sign_test"]["p"]))
                   for K, d in c["paired_vs_K3_seed0"].items()})
            print("   within-origin rho(K,pct):", ci(c["within_origin_spearman_K_vs_pct"]))
        print("V1 regret% vs oracle by K:", cur(L["regret_rel_pct_by_K_seed0"]))
        print("V1 test PF by K        :", cur(L["test_pf_by_K_seed0"]))
    if "2" in sections:
        for K, d in v["V2_leaks"].items():
            print(f"V2 K={K}: n={d['n']} pct entry={r1(d['median_pct_entry'])} exit={r1(d['median_pct_exit_assign'])} strict={r1(d['median_pct_strict_no_open_trades'])} "
                  f"pick_changed exit={r1(d['frac_pick_changed_exit_vs_entry'])} strict={r1(d['frac_pick_changed_strict_vs_entry'])} open@cut/pick={r1(d['median_open_at_cut_frac_of_pick_trades'])}")
    if "3" in sections:
        print("V3 distinct picks of 30 seeds (median, max, frac same as seed0):",
              {K: (d["median_distinct_picks_of_30"], d["max_distinct_picks"], r1(d["median_frac_seeds_same_as_seed0"])) for K, d in v["V3_pseudo_seeds"].items()})
    if "4" in sections:
        R = v["V4_rank_persistence"]
        print(f"V4 fixed-1y-future, common origins n={R['n_origins_common']} ({R['first_origin']}..{R['last_origin']})")
        for Lk, d in R["by_L_fixed_1y_future"].items():
            print(f"   L={Lk}: rho_net={ci(d['rho_net'])} rho_pf={ci(d['rho_pf'])} frac_pos={r1(d['frac_rho_net_pos'])} "
                  f"top-dec B%={r1(d['top_decile_B_pct']['median'])} bottom-dec={r1(d['bottom_decile_B_pct']['median'])} "
                  f"top-bot={ci(d['top_minus_bottom_decile'])} bestA B%={r1(d['best_A_B_pct']['median'])}")
        T = R["ten_finalists_pipeline_mirror"]
        print(f"V4 ten-finalist mirror, common origins n={T['n_origins_common']}")
        for Lk, d in T["by_L"].items():
            print(f"   L={Lk}: n={d['n_origins']} rho(LB,fut)={ci(d['rho_lockbox_vs_future_1y'])} rho(LBpf,futpf)={r1(d['rho_lockbox_pf_vs_future_pf']['median'])} "
                  f"rho(IS,fut)={ci(d['rho_insample_vs_future_1y'])} frac_pos={r1(d['frac_rho_lb_pos'])} "
                  f"LBbest fut rank frac={r1(d['lockbox_best_future_rank_frac(0=best)']['median'])} ISbest={r1(d['insample_best_future_rank_frac']['median'])} "
                  f"P(LBbest>median)={r1(d['p_lockbox_best_beats_finalist_median'])} nfin={d['median_n_finalists']}")
    if "5" in sections:
        D = v["V5_designs_origin_level"]
        print(f"V5 origin-level designs, common n={D['n_origins_common']}")
        for k, d in D["designs"].items():
            print(f"   {k}: n={d['n_origins']} pass={r1(d['pass_rate'])} P(fut+|pass)={r1(d['p_fut1y_pos_given_pass'])}({d['n_pass']}) "
                  f"P(fut+|fail)={r1(d['p_fut1y_pos_given_fail'])}({d['n_fail']}) medPF pass/fail={r1(d['median_fut1y_pf_pass'])}/{r1(d['median_fut1y_pf_fail'])} "
                  f"rho(LBpf,futpf)={r1(d['spearman_lockbox_pf_vs_future_pf'])} frozen-nolb pct={ci(d['frozen_minus_nolockbox_future_pct'])} "
                  f"sign={d['sign_test_frozen_vs_nolockbox']['n_pos']}/{d['sign_test_frozen_vs_nolockbox']['n_nonzero']} p={r1(d['sign_test_frozen_vs_nolockbox']['p'])} "
                  f"P(fut2+|pass/fail)={r1(d['p_fut2y_pos_given_pass'])}/{r1(d['p_fut2y_pos_given_fail'])}")
    if "6" in sections:
        R = v["V6_recency"]
        print(f"V6 recency n={R['n_origins']}: recent3={ci(R['recent3'])} old3={ci(R['old3'])} last6={ci(R['last6'])} recent1={ci(R['recent1'])} old1of3={ci(R['old1_of_3'])}")
        print(f"   paired recent3-old3: {R['paired_recent3_minus_old3']} med diff={r1(R['median_diff_recent3_minus_old3'])}; recent3-last6: {R['paired_recent3_minus_last6']}; recent1-old1: {R['paired_recent1_minus_old1']}")
    if "7" in sections:
        s7 = v["V7_pf_shrinkage_by_K"]
        if "all_origins" in s7:
            print("V7 PF shrinkage (testPF-1)/(trainPF-1) all origins :", cur(s7["all_origins"]))
            print("V7 PF shrinkage common origins K<=8               :", cur(s7["common_origins_Kle8"]))
        else:
            print("V7 PF shrinkage (testPF-1)/(trainPF-1) by K:", cur(s7))
    if "A" in sections and os.path.exists(os.path.join(DATA, f"analysis_{rid}.json")):
        a = json.load(open(os.path.join(DATA, f"analysis_{rid}.json"), encoding="utf-8"))
        A1 = a["A1_learning_curve"]["curves"]
        print("AUTHOR A1 all-origins R1 tl1:", {K: (r1(d["test_pct"]["median"]), d["n_origins"]) for K, d in A1["all_origins_per_K"]["R1"]["1"].items()})
        print("AUTHOR A1 common R1 tl1     :", {K: (r1(d["test_pct"]["median"]), d["n_origins"]) for K, d in A1["common_origin_set"]["R1"]["1"].items()})
        A2 = a["A2_rank_persistence"]
        print("AUTHOR A2:", {Lk: (r1(d["rho_net"]["median"]), r1(d["rho_pf"]["median"]), d["n_pairs"]) for Lk, d in A2.items()})
        A3 = a["A3_design_backtest"]["designs"]
        print("AUTHOR A3 own-t (pass, P|pass n, P|fail n):",
              {k: (r1(d["own_t_set"]["pass_rate"]), r1(d["own_t_set"]["p_future1y_pos_given_pass"]["p"]), d["own_t_set"]["p_future1y_pos_given_pass"]["n"],
                   r1(d["own_t_set"]["p_future1y_pos_given_fail"]["p"]), d["own_t_set"]["p_future1y_pos_given_fail"]["n"]) for k, d in A3.items()})


if __name__ == "__main__":
    rid = int(sys.argv[1])
    sections = sys.argv[2] if len(sys.argv) > 2 else "1234567A"
    main(rid, sections)
