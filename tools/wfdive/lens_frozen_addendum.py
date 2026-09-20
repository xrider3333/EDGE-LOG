"""Post-processing addendum to lens_frozen.json -- pure bookkeeping on ALREADY
REPLAYED data (no market data touched, no cpu_lock needed): adds a THIRD
aggregate, "headline_filtered", that additionally drops the low-frequency
daily-bar ETFDIP/NQDIP runs whose fold-1 (and often several other folds) traded
ZERO times -- the documented engine cold-start artifact (memory:
"validate-coldstart-folds ... long-warm-up strategies lose 75-87% of fold
trades"; here it is a full zero, not just a reduction) plus these runs sit on
only ~4,000 daily bars total, a handful of trades per fold, too little sample
to support a ratio at all. Both "pinned" (no real search) and "cold/low-freq"
runs are excluded from headline_filtered; everything is still visible in
headline_non_pinned / all_runs_incl_pinned and in each run's own record, so no
information is discarded, only the headline's denominator is cleaned up.

Run from this worktree: python tools/wfdive/lens_frozen_addendum.py
"""
import json
import os
import statistics

import common
from lens_frozen import bootstrap_median_ci

PATH = os.path.join(common.DATA_DIR, "lens_frozen.json")


def main():
    with open(PATH, "r", encoding="utf-8") as f:
        d = json.load(f)
    runs = d["runs"]

    cold_low_freq_ids = [rid for rid, r in runs.items() if r["diagonal_checks"][0]["trades"] == 0]
    pinned_ids = [rid for rid, r in runs.items() if r["is_pinned_single_config"]]
    excluded = set(cold_low_freq_ids) | set(pinned_ids)
    clean = {rid: r for rid, r in runs.items() if rid not in excluded}

    def collect(path_fn):
        return [path_fn(r) for r in clean.values() if path_fn(r) is not None]

    headline_filtered = {
        "excluded_pinned_ids": pinned_ids,
        "excluded_cold_or_low_freq_zero_fold1_trades_ids": cold_low_freq_ids,
        "excluded_cold_or_low_freq_strategies": sorted(set(
            runs[rid]["strategy"] for rid in cold_low_freq_ids)),
        "n_runs_used": len(clean),
        "frozen1_over_retuned_net": bootstrap_median_ci(
            collect(lambda r: (r.get("pools", {}).get("window_2_N") or {}).get(
                "ratio_frozen1_over_retuned_net"))),
        "frozen1_over_retuned_pf": bootstrap_median_ci(
            collect(lambda r: (r.get("pools", {}).get("window_2_N") or {}).get(
                "ratio_frozen1_over_retuned_pf"))),
        "champion_over_retuned_net": bootstrap_median_ci(
            collect(lambda r: (r.get("pools", {}).get("window_2_N") or {}).get(
                "ratio_champion_over_retuned_net"))),
        "champion_over_retuned_pf": bootstrap_median_ci(
            collect(lambda r: (r.get("pools", {}).get("window_2_N") or {}).get(
                "ratio_champion_over_retuned_pf"))),
        "frozen_mid_over_retuned_net": bootstrap_median_ci(
            collect(lambda r: (r.get("pools", {}).get("window_mid_N") or {}).get(
                "ratio_frozen_mid_over_retuned_net"))),
        "frozen_mid_over_retuned_pf": bootstrap_median_ci(
            collect(lambda r: (r.get("pools", {}).get("window_mid_N") or {}).get(
                "ratio_frozen_mid_over_retuned_pf"))),
        "share_identical_param_pairs": bootstrap_median_ci(
            collect(lambda r: r.get("param_drift", {}).get("share_identical_pairs"))),
    }
    lc_flags = []
    for r in clean.values():
        for row in r.get("learning_curve", []):
            if row.get("tuned_beats_frozen1_net") is not None:
                lc_flags.append(1.0 if row["tuned_beats_frozen1_net"] else 0.0)
    headline_filtered["learning_curve_share_tuned_beats_frozen1"] = {
        "share": round(sum(lc_flags) / len(lc_flags), 4) if lc_flags else None,
        "n_comparisons": len(lc_flags)}

    sc_ratios = []
    for r in clean.values():
        sc = r.get("scheme_compare")
        if sc and sc["rolling"]["net_per_held_fold"] is not None and sc["anchored"]["net_per_held_fold"]:
            sc_ratios.append(sc["rolling"]["net_per_held_fold"] / sc["anchored"]["net_per_held_fold"])
    headline_filtered["rolling_over_anchored_net_per_fold"] = bootstrap_median_ci(sc_ratios)

    d["aggregate"]["headline_filtered"] = headline_filtered
    with open(PATH, "w", encoding="utf-8") as f:
        json.dump(d, f, default=str, indent=1)
    print(f"n clean runs: {len(clean)} (excluded {len(pinned_ids)} pinned + "
          f"{len(cold_low_freq_ids)} cold/low-freq)")
    print(json.dumps(headline_filtered, indent=1, default=str))


if __name__ == "__main__":
    main()
