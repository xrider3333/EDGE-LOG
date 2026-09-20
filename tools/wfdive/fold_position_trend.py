"""wfdive follow-up for Q1/Q3: does re-tuning on MORE history (anchored, ever-
growing training window) beat re-tuning on a fixed/sliding window (rolling)?
And within the PRIMARY scheme's own fold sequence, do LATER folds (more prior
data, later calendar years) generalize better than EARLIER folds, or is it flat
(meaning the extra WF tuning years aren't adding discriminating power)?

Pure JSON analysis over _wfdive_data/runs.json. No Firestore, no backtests.
Run from this worktree: python tools/wfdive/fold_position_trend.py
"""
import json
import math
import os
import random
import sys

import numpy as np
from scipy.stats import spearmanr

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402
from lens_predict import is_book, cluster_bootstrap_stat, spearman_stat, dedupe_one_per_family  # noqa: E402

random.seed(42)
np.random.seed(42)


def main():
    runs = common.load_runs()
    non_book = [d for d in runs if not is_book(d)]

    # ---- (1) rolling vs anchored: which uses more training data, which scores higher? ----
    mode_rows = []
    for d in non_book:
        v = d.get("validate") or {}
        wr, wa = v.get("wf_rolling"), v.get("wf_anchored")
        if not (isinstance(wr, dict) and isinstance(wa, dict) and wr.get("ran") and wa.get("ran")):
            continue
        if not wr.get("n_folds") or not wa.get("n_folds"):
            continue
        mode_rows.append({
            "id": d.get("id"), "family": common.family_key(d),
            "wf_best_mode": v.get("wf_best_mode"),
            "rolling_oos_net": wr.get("oos_net"), "anchored_oos_net": wa.get("oos_net"),
            "rolling_held": wr.get("held"), "anchored_held": wa.get("held"),
            "rolling_fold_frac": wr.get("fold_frac"), "anchored_fold_frac": wa.get("fold_frac"),
            "anchored_beats_rolling": (wa.get("oos_net") or 0) > (wr.get("oos_net") or 0),
        })
    dedup_mode = dedupe_one_per_family(
        [{"id": r["id"], "family": r["family"], "timestamp": next(
            (dd.get("timestamp") for dd in non_book if dd.get("id") == r["id"]), "")}
         for r in mode_rows], lambda r: True)
    dedup_ids = {r["id"] for r in dedup_mode}
    dedup_rows = [r for r in mode_rows if r["id"] in dedup_ids]
    n_anchored_wins = sum(1 for r in dedup_rows if r["anchored_beats_rolling"])
    primary_mode_counts = {}
    for r in mode_rows:
        primary_mode_counts[r["wf_best_mode"]] = primary_mode_counts.get(r["wf_best_mode"], 0) + 1

    out1 = {
        "n_runs_both_schemes_ran": len(mode_rows), "n_families": len(set(r["family"] for r in mode_rows)),
        "n_dedup": len(dedup_rows),
        "anchored_beats_rolling_wins_dedup": n_anchored_wins,
        "anchored_beats_rolling_losses_dedup": len(dedup_rows) - n_anchored_wins,
        "primary_(saved-as-wf_oos)_scheme_counts_all_runs": primary_mode_counts,
    }
    print("=== (1) anchored (growing window) vs rolling (fixed/sliding window) ===")
    print(json.dumps(out1, indent=1, default=str))

    # ---- (2) within the PRIMARY scheme's own folds: does fold position predict OOS quality? ----
    # top10_results = the PRIMARY scheme's per-fold rows (fold, oos_pf, oos_pnl, oos_trades,
    # train_bars, test_bars). Use RANK-normalized fold position (fold / n_folds) so short and
    # long fold sequences are comparable, and oos_pf (unitless) instead of raw oos_pnl.
    fold_level = []
    for d in non_book:
        rows = d.get("top10_results") or []
        rows = [r for r in rows if isinstance(r, dict) and r.get("fold") is not None
                and r.get("oos_trades")]
        if len(rows) < 3:
            continue
        n = max(r["fold"] for r in rows)
        if n < 3:
            continue
        fam = common.family_key(d)
        for r in rows:
            pf = r.get("oos_pf")
            if pf is None or not math.isfinite(pf):
                continue
            fold_level.append({
                "id": d.get("id"), "family": fam,
                "fold_pos": r["fold"] / n,          # 0..1, early -> late
                "train_bars": r.get("train_bars"),
                "oos_pf": min(pf, 10.0),            # cap absurd PF outliers (tiny-sample folds)
                "oos_trades": r.get("oos_trades"),
            })
    fams2 = [x["family"] for x in fold_level]
    pe, ci, nb = cluster_bootstrap_stat(
        fold_level, fams2,
        lambda xs: spearman_stat([(x["fold_pos"], x["oos_pf"]) for x in xs]))
    pe_tb, ci_tb, _ = cluster_bootstrap_stat(
        fold_level, fams2,
        lambda xs: spearman_stat([(x["train_bars"], x["oos_pf"]) for x in xs
                                   if x["train_bars"] is not None]))
    out2 = {
        "n_fold_rows": len(fold_level), "n_runs": len(set(x["id"] for x in fold_level)),
        "n_families": len(set(fams2)),
        "spearman_fold_position_vs_oos_pf_point": pe, "ci90": list(ci),
        "spearman_train_bars_vs_oos_pf_point": pe_tb, "ci90_trainbars": list(ci_tb),
    }
    print("\n=== (2) fold position (early->late) vs that fold's own OOS PF ===")
    print(json.dumps(out2, indent=1, default=str))

    out = {"anchored_vs_rolling": out1, "fold_position_vs_quality": out2,
           "mode_rows": mode_rows, "fold_level_n": len(fold_level)}
    with open(os.path.join(common.DATA_DIR, "fold_position_trend.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, default=str, indent=1)
    print("\nsaved -> _wfdive_data/fold_position_trend.json")


if __name__ == "__main__":
    main()
