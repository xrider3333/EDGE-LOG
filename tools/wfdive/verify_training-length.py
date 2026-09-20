"""wfdive VERIFY (adversarial): recompute every number in the "Tune on less data"
lens (lens_trainlen.py) from the saved files only, with independent code.

Inputs (all under _wfdive_data/, never Firestore):
  lens_trainlen.json      the lens's per-(fold, variant) results + reproduction gate
  probe_335_full.json     run #335's saved doc (ENGU-Q crown): top10_results = PRIMARY
                          (rolling) fold rows, wf_alt_folds = ANCHORED fold rows,
                          validate.wf_rolling / wf_anchored, selection, windows
  probe_257_full.json     run #257's saved doc (ORB crown)

Engine facts used (read from augur_engine/auto.py, not assumed):
  - _wf_fold_row draws a FRESH _RandomSampler(space, seed) per fold -> every fold,
    every scheme and every training-window variant evaluates the SAME n_trials
    candidate param sets; the fold champion is argmax training total_pnl after the
    realism gate. No GP steering in the walk-forward branch (that lives only in the
    Stage-A "single" branch, auto_steer=True).
  - fold specs: init=int(0.4n), tsize=(n-init)//n_folds, te_e=n on the last fold,
    rolling tr_start = tr_end-init, anchored tr_start = 0.
  - trial cache key includes the (a, b) slice bounds, so different training windows
    never share cache entries.

Cheap, no backtests: the only engine calls are _auto_space_from_params + the seeded
sampler (pure Python, no data) to locate each observed champion inside the shared
300-candidate draw. Writes _wfdive_data/verify_training-length.json.

Run from the worktree root:
    python tools/wfdive/verify_training-length.py
"""
import json
import os
import sys

WORKTREE = r"C:\Users\xride\AppData\Local\EdgeLog-worktrees\wfdive"
if WORKTREE not in sys.path:
    sys.path.insert(0, WORKTREE)
os.chdir(WORKTREE)
os.environ["PYTHONIOENCODING"] = "utf-8"

from tools.wfdive.common import DATA_DIR, low_priority  # noqa: E402

low_priority()

OUT = os.path.join(DATA_DIR, "verify_training-length.json")
NQ_PT = 20.0


def jload(name):
    with open(os.path.join(DATA_DIR, name), "r", encoding="utf-8") as f:
        return json.load(f)


lens = jload("lens_trainlen.json")
doc335 = jload("probe_335_full.json")
doc257 = jload("probe_257_full.json")

R = {"checks": {}, "notes": []}


def close(a, b, tol=1e-6):
    try:
        return abs(float(a) - float(b)) <= tol * max(1.0, abs(float(b)))
    except Exception:
        return False


# ────────────────────────────────────────────────────────────────────────────
# 0. Windows: WF years must not overlap the lockbox; optimize window == data loaded
# ────────────────────────────────────────────────────────────────────────────
for rid, doc in (("335", doc335), ("257", doc257)):
    w = doc["validate"]["windows"]
    folds = doc["validate"]["wf_oos"]["folds"]
    last_to = folds[-1]["to"]
    lb_from = w["lockbox"][0]
    R["checks"][f"{rid}_windows"] = {
        "optimize": w["optimize"], "lockbox": w["lockbox"],
        "last_fold_to": last_to, "lockbox_from": lb_from,
        "wf_overlaps_lockbox": last_to >= lb_from,
        "lens_loaded_window": [lens["runs"][rid]["opt_from"], lens["runs"][rid]["opt_to"]],
        "lens_window_matches_optimize": [lens["runs"][rid]["opt_from"], lens["runs"][rid]["opt_to"]] == w["optimize"],
    }

# ────────────────────────────────────────────────────────────────────────────
# 1. Fold specs: recompute from the ENGINE formula (auto.py WF branch) and compare
#    with the lens's saved-train_bars-derived specs and with the doc's rows.
# ────────────────────────────────────────────────────────────────────────────
def engine_fold_specs(n, n_folds, rolling):
    init = int(n * 0.40)
    tsize = max(1, (n - init) // n_folds)
    out = {}
    for f in range(n_folds):
        tr_end = init + f * tsize
        tr_start = max(0, tr_end - init) if rolling else 0
        te_s = tr_end
        te_e = n if f == n_folds - 1 else te_s + tsize
        out[f + 1] = dict(tr_start=tr_start, tr_end=tr_end, te_s=te_s, te_e=te_e,
                          train_bars=tr_end - tr_start, test_bars=te_e - te_s)
    return out


for rid, doc, rolling in (("335", doc335, True), ("257", doc257, False)):
    n = lens["runs"][rid]["n_bars"]
    eng = engine_fold_specs(n, 8, rolling)
    lens_specs = lens["runs"][rid]["fold_specs"]
    saved = {int(r["fold"]): r for r in doc["top10_results"]}
    mism = []
    for f in range(1, 9):
        e, l, s = eng[f], lens_specs[str(f)], saved[f]
        if not (e["te_s"] == l["te_s"] and e["te_e"] == l["te_e"] and e["tr_start"] == l["tr_start_saved"]
                and e["train_bars"] == s["train_bars"] and e["test_bars"] == s["test_bars"]):
            mism.append({"fold": f, "engine": e, "lens": l, "saved": {k: s[k] for k in ("train_bars", "test_bars")}})
    R["checks"][f"{rid}_fold_specs"] = {"n_bars": n, "scheme": "rolling" if rolling else "anchored",
                                        "mismatches": mism, "ok": not mism,
                                        "init_bars": int(n * 0.4)}

# ────────────────────────────────────────────────────────────────────────────
# 2. #257: zero free params? (independent of the lens's n_free logic)
# ────────────────────────────────────────────────────────────────────────────
pk257 = ["or_bars", "trade_mode", "stop_frac", "breakout_buf", "close_confirm", "partial_exit_R",
         "trail_bars", "be_after_R", "target_R", "atr_filter", "vpace_filter", "flat_eod", "skip_holidays"]
try:
    from augur_engine.strategies import load_strategy
    from augur_engine.auto import _auto_space_from_params, _RandomSampler, _collapse
    mod257 = load_strategy("ORB_3_6_E1.py")
    dp257 = mod257.DEFAULT_PARAMS
    sp257 = _auto_space_from_params(dp257)
    pinned = {}
    for k, spec in sp257.items():
        if spec[0] == "cat":
            pinned[k] = len(spec[1]) == 1
        else:
            pinned[k] = spec[1] == spec[2]
    n_pinned = sum(pinned.values())
    # draw 200 from seed 42 -> how many DISTINCT configs?
    samp = _RandomSampler(sp257, seed=42)
    draws = {json.dumps(_collapse(samp.ask(), dp257), sort_keys=True) for _ in range(200)}
    space_err = None
except Exception as e:  # pragma: no cover
    pinned, n_pinned, draws, sp257, space_err = {}, None, set(), {}, f"{type(e).__name__}: {e}"

rows257 = doc257["top10_results"]
param_sets_257 = {json.dumps({k: r.get(k) for k in pk257}, sort_keys=True) for r in rows257}
alt257 = {int(r["fold"]): r for r in doc257.get("wf_alt_folds") or []}
alt_eq_prim = all(close(alt257[int(r["fold"])]["oos_pnl"], r["oos_pnl"], 1e-9) for r in rows257)
R["checks"]["257_zero_free_params"] = {
    "space_error": space_err,
    "n_params": len(sp257), "n_pinned": n_pinned, "pinned_by_param": pinned,
    "distinct_configs_in_200_seed42_draws": len(draws),
    "distinct_param_sets_across_8_saved_folds": len(param_sets_257),
    "doc_n_evaluated": doc257.get("n_evaluated"), "doc_n_valid": doc257.get("n_valid"),
    "selection_n_candidates": len((doc257.get("selection") or {}).get("candidates") or []),
    "rolling_alt_oos_equals_anchored_primary_all_8_folds": alt_eq_prim,
    "wf_rolling_oos_net": doc257["validate"]["wf_rolling"]["oos_net"],
    "wf_anchored_oos_net": doc257["validate"]["wf_anchored"]["oos_net"],
}
# reproduction gate + fold-8 confirmation
rep = lens["runs"]["257"]["reproduction"]
s1 = {int(r["fold"]): r for r in rows257}[1]
R["checks"]["257_reproduction"] = {
    "elapsed_s": rep["elapsed_s"],
    "params_match": rep["reproduced_row"]["params"] == {k: s1.get(k) for k in pk257},
    "oos_pnl": [rep["reproduced_row"]["oos_pnl"], s1["oos_pnl"]],
    "oos_trades": [rep["reproduced_row"]["oos_trades"], s1["oos_trades"]],
    "oos_pf": [rep["reproduced_row"]["oos_pf"], s1["oos_pf"]],
    "ok": (rep["reproduced_row"]["params"] == {k: s1.get(k) for k in pk257}
           and close(rep["reproduced_row"]["oos_pnl"], s1["oos_pnl"], 1e-9)
           and rep["reproduced_row"]["oos_trades"] == s1["oos_trades"]),
}
f8 = lens["runs"]["257"]["folds"]["8"]["T_all"]
s8 = {int(r["fold"]): r for r in rows257}[8]
R["checks"]["257_fold8_T_all_vs_saved"] = {
    "lens": [f8["oos_pnl"], f8["oos_trades"], f8["oos_pf"], f8["is_total_pnl"], f8["is_trades"]],
    "saved": [s8["oos_pnl"], s8["oos_trades"], s8["oos_pf"], s8["total_pnl"], s8["num_trades"]],
    "ok": close(f8["oos_pnl"], s8["oos_pnl"], 1e-9) and f8["oos_trades"] == s8["oos_trades"]
          and close(f8["is_total_pnl"], s8["total_pnl"], 1e-9),
    "params_match_saved": f8["params"] == {k: s8.get(k) for k in pk257},
}
# fixed-vs-retuned for #257 (memory note "PF 1.35 vs 1.36"): same config, so any gap is
# the cold-start / slice effect, not tuning
gv = doc257.get("gate_validate") or {}
R["checks"]["257_fixed_vs_retuned_same_config"] = {
    "fixed_ungated_wf": {k: (gv.get("ungated_wf") or {}).get(k) for k in ("total_pnl", "num_trades", "profit_factor")},
    "retuned_wf_oos": {k: doc257["validate"]["wf_oos"].get(k) for k in ("net", "trades", "profit_factor")},
    "sum_fold_oos_pnl": sum(r["oos_pnl"] for r in rows257),
}

# ────────────────────────────────────────────────────────────────────────────
# 3. #335: reproduction gate (fold 1) + T_all vs the doc's ANCHORED rows (folds 4-8)
#    + T_5y vs the doc's ROLLING rows (folds 4-8)
# ────────────────────────────────────────────────────────────────────────────
pk335 = ["er_len", "er_th", "limit_atr", "tl_len", "vol_mult", "stop_mult", "act_R", "trail_frac",
         "buf_atr", "min_brk", "ema_len", "atr_len", "regime_len", "breakeven_R"]
rows335 = {int(r["fold"]): r for r in doc335["top10_results"]}
alt335 = {int(r["fold"]): r for r in doc335.get("wf_alt_folds") or []}
assert doc335.get("wf_alt_mode") == "anchored" and doc335["validate"]["wf_best_mode"] == "rolling"
rep = lens["runs"]["335"]["reproduction"]
s1 = rows335[1]
R["checks"]["335_reproduction"] = {
    "elapsed_s": rep["elapsed_s"],
    "params_match": rep["reproduced_row"]["params"] == {k: s1.get(k) for k in pk335},
    "oos_pnl": [rep["reproduced_row"]["oos_pnl"], s1["oos_pnl"]],
    "oos_trades": [rep["reproduced_row"]["oos_trades"], s1["oos_trades"]],
    "oos_pf": [rep["reproduced_row"]["oos_pf"], s1["oos_pf"]],
    "is_pnl": [rep["reproduced_row"]["is_total_pnl"], s1["total_pnl"]],
    "ok": (rep["reproduced_row"]["params"] == {k: s1.get(k) for k in pk335}
           and close(rep["reproduced_row"]["oos_pnl"], s1["oos_pnl"], 1e-9)
           and rep["reproduced_row"]["oos_trades"] == s1["oos_trades"]),
    "note": "fold 1 rolling == fold 1 anchored (tr_start 0 either way), so this gate covers both schemes",
}
F = lens["runs"]["335"]["folds"]
folds_done = sorted(int(f) for f in F)
tall_vs_anch = {}
t5_vs_roll = {}
for f in folds_done:
    a = F[str(f)].get("T_all")
    if a is not None and f in alt335:
        s = alt335[f]
        tall_vs_anch[f] = {
            "lens_oos_pnl": a["oos_pnl"], "saved_anchored_oos_pnl": s["oos_pnl"],
            "lens_oos_pf": a["oos_pf"], "saved_oos_pf": s["oos_pf"],
            "lens_is_pnl": a["is_total_pnl"], "saved_is_pnl": s["total_pnl"],
            "lens_train_bars": a["train_bars"], "saved_train_bars": s["train_bars"],
            "match": (close(a["oos_pnl"], s["oos_pnl"], 1e-9) and close(a["oos_pf"], s["oos_pf"], 1e-9)
                      and close(a["is_total_pnl"], s["total_pnl"], 1e-9) and a["train_bars"] == s["train_bars"]),
        }
    b = F[str(f)].get("T_5y")
    if b is not None:
        s = rows335[f]
        t5_vs_roll[f] = {
            "lens_T5y": [b["oos_pnl"], b["oos_trades"], b["oos_pf"], b["train_bars"]],
            "saved_rolling": [s["oos_pnl"], s["oos_trades"], s["oos_pf"], s["train_bars"]],
            "same_params": b["params"] == {k: s.get(k) for k in pk335},
            "same_oos": close(b["oos_pnl"], s["oos_pnl"], 1e-9) and b["oos_trades"] == s["oos_trades"],
            "train_bars_ratio": b["train_bars"] / s["train_bars"],
        }
R["checks"]["335_T_all_equals_saved_anchored"] = {
    "per_fold": tall_vs_anch,
    "n_match": sum(1 for v in tall_vs_anch.values() if v["match"]),
    "n": len(tall_vs_anch),
    "note": "T_all (tr_start=0, same test slice) IS the engine's anchored scheme; the doc saved those rows",
}
R["checks"]["335_T_5y_vs_saved_rolling"] = {
    "per_fold": t5_vs_roll,
    "n_same_oos": sum(1 for v in t5_vs_roll.values() if v["same_oos"]),
    "n": len(t5_vs_roll),
}

# ────────────────────────────────────────────────────────────────────────────
# 4. Variant comparisons (folds 4-8): pooled nets/trades, per-fold matches, %s
# ────────────────────────────────────────────────────────────────────────────
VARS = ["T_all", "T_5y", "T_3y", "T_2y"]
pooled = {}
for v in VARS:
    pooled[v] = {
        "net_pts": sum(F[str(f)][v]["oos_pnl"] for f in folds_done),
        "trades": sum(F[str(f)][v]["oos_trades"] for f in folds_done),
        "n_folds": len(folds_done),
        "n_negative_folds": sum(1 for f in folds_done if F[str(f)][v]["oos_pnl"] < 0),
        "per_fold_net": {f: F[str(f)][v]["oos_pnl"] for f in folds_done},
        "per_fold_trades": {f: F[str(f)][v]["oos_trades"] for f in folds_done},
    }
pooled["saved_rolling(deployed)"] = {
    "net_pts": sum(rows335[f]["oos_pnl"] for f in folds_done),
    "trades": sum(rows335[f]["oos_trades"] for f in folds_done),
    "n_folds": len(folds_done),
    "n_negative_folds": sum(1 for f in folds_done if rows335[f]["oos_pnl"] < 0),
}
pooled["saved_anchored"] = {
    "net_pts": sum(alt335[f]["oos_pnl"] for f in folds_done),
    "n_folds": len(folds_done),
    "n_negative_folds": sum(1 for f in folds_done if alt335[f]["oos_pnl"] < 0),
}
R["checks"]["335_pooled_folds_4_8"] = pooled
R["checks"]["335_pooled_folds_4_8_usd"] = {k: round(v["net_pts"] * NQ_PT) for k, v in pooled.items()}


def pct(a, b):
    return (a / b - 1.0) * 100.0


P = {k: v["net_pts"] for k, v in pooled.items()}
R["checks"]["335_pct_deltas"] = {
    "T_3y_vs_T_5y": pct(P["T_3y"], P["T_5y"]),
    "T_3y_vs_deployed": pct(P["T_3y"], P["saved_rolling(deployed)"]),
    "T_5y_vs_deployed": pct(P["T_5y"], P["saved_rolling(deployed)"]),
    "T_2y_vs_T_3y": pct(P["T_2y"], P["T_3y"]),
    "T_2y_vs_T_5y": pct(P["T_2y"], P["T_5y"]),
    "T_all_vs_deployed": pct(P["T_all"], P["saved_rolling(deployed)"]),
    "T_all_trades_vs_deployed": pct(pooled["T_all"]["trades"], pooled["saved_rolling(deployed)"]["trades"]),
    "fold8_T_2y_vs_T_3y": pct(F["8"]["T_2y"]["oos_pnl"], F["8"]["T_3y"]["oos_pnl"]),
    "fold7_T_all_over_T_5y_x": F["7"]["T_all"]["oos_pnl"] / F["7"]["T_5y"]["oos_pnl"],
    "fold5_T_all_vs_T_5y": pct(F["5"]["T_all"]["oos_pnl"], F["5"]["T_5y"]["oos_pnl"]),
    "fold5_T_all_vs_saved_rolling": pct(F["5"]["T_all"]["oos_pnl"], rows335[5]["oos_pnl"]),
    "T_2y_pooled_excluding_fold8_vs_T_3y_excluding_fold8": pct(
        P["T_2y"] - F["8"]["T_2y"]["oos_pnl"], P["T_3y"] - F["8"]["T_3y"]["oos_pnl"]),
    "full_8_fold_anchored_vs_rolling_from_doc": pct(doc335["validate"]["wf_anchored"]["oos_net"],
                                                     doc335["validate"]["wf_rolling"]["oos_net"]),
}


def same_cell(x, y):
    return (x["params"] == y["params"] and close(x["oos_pnl"], y["oos_pnl"], 1e-9)
            and x["oos_trades"] == y["oos_trades"])


per_fold_matches = {}
for f in folds_done:
    c = F[str(f)]
    per_fold_matches[f] = {
        "T_5y==T_3y": same_cell(c["T_5y"], c["T_3y"]),
        "T_3y==T_2y": same_cell(c["T_3y"], c["T_2y"]),
        "T_all==T_5y": same_cell(c["T_all"], c["T_5y"]),
        "T_5y==saved_rolling": (c["T_5y"]["params"] == {k: rows335[f].get(k) for k in pk335}),
        "T_2y_vs_T_3y_net_sign": ("worse" if c["T_2y"]["oos_pnl"] < c["T_3y"]["oos_pnl"] - 1e-6
                                  else "equal" if abs(c["T_2y"]["oos_pnl"] - c["T_3y"]["oos_pnl"]) <= 1e-6
                                  else "better"),
    }
R["checks"]["335_per_fold_variant_matches"] = per_fold_matches
R["checks"]["335_T5y_eq_T3y_count"] = [sum(1 for v in per_fold_matches.values() if v["T_5y==T_3y"]), len(per_fold_matches)]

# fold 5 sensitivity claim
R["checks"]["335_fold5"] = {
    "saved_rolling": [rows335[5]["train_bars"], rows335[5]["oos_pnl"], rows335[5]["oos_trades"], rows335[5]["oos_pf"]],
    "T_5y": [F["5"]["T_5y"]["train_bars"], F["5"]["T_5y"]["oos_pnl"], F["5"]["T_5y"]["oos_trades"], F["5"]["T_5y"]["oos_pf"]],
    "train_bars_pct_smaller": (1 - F["5"]["T_5y"]["train_bars"] / rows335[5]["train_bars"]) * 100,
    "extra_bars_in_rolling_window": rows335[5]["train_bars"] - F["5"]["T_5y"]["train_bars"],
    "T_3y_same_as_T_5y": same_cell(F["5"]["T_5y"], F["5"]["T_3y"]),
    "T_2y_same_as_T_5y": same_cell(F["5"]["T_5y"], F["5"]["T_2y"]),
}

# ────────────────────────────────────────────────────────────────────────────
# 5. Timing: means per variant, ratio, and the fold-8 T_all cache-warm caveat
# ────────────────────────────────────────────────────────────────────────────
tim = {v: [F[str(f)][v]["elapsed_s"] for f in folds_done] for v in VARS}
means = {v: sum(x) / len(x) for v, x in tim.items()}
R["checks"]["335_timing"] = {
    "per_variant_s": tim, "mean_s": means,
    "T_all_over_T_3y": means["T_all"] / means["T_3y"],
    "T_all_over_T_3y_excluding_fold8": (sum(tim["T_all"][:-1]) / 4) / (sum(tim["T_3y"][:-1]) / 4)
    if folds_done[-1] == 8 else None,
    "fold8_T_all_s": F["8"]["T_all"]["elapsed_s"],
    "other_T_all_s": [F[str(f)]["T_all"]["elapsed_s"] for f in folds_done if f != 8],
    "note": "lens_trainlen.log shows a first (killed) process had already begun fold 8 T_all with the "
            "same trial-cache DB, so fold 8 T_all's 71.8s is partly cache hits; the other T_all folds "
            "took 114-150s. Mean T_all is therefore UNDERSTATED, the speed ratio conservative.",
}

# ────────────────────────────────────────────────────────────────────────────
# 6. Mechanism: the shared 300-candidate draw. Locate each observed champion in
#    the seed-42 sequence (pure Python, no data). If every champion sits at an
#    index < 300 the 'n_trials=300' derivation is corroborated a second way.
# ────────────────────────────────────────────────────────────────────────────
champ_sets = {}
for f in folds_done:
    for v in VARS:
        key = json.dumps(F[str(f)][v]["params"], sort_keys=True)
        champ_sets.setdefault(key, []).append(f"fold{f}:{v}")
for f, r in rows335.items():
    key = json.dumps({k: r.get(k) for k in pk335}, sort_keys=True)
    champ_sets.setdefault(key, []).append(f"fold{f}:saved_rolling")
for f, r in alt335.items():
    pass  # alt rows carry no params

crown = json.dumps({k: (doc335["validate"].get("champion") or {}).get(k) for k in pk335}, sort_keys=True)
mech = {"n_distinct_champions_in_20_lens_cells": len({json.dumps(F[str(f)][v]["params"], sort_keys=True)
                                                        for f in folds_done for v in VARS}),
        "n_distinct_champions_incl_saved_rolling_8_folds": len(champ_sets),
        "crown_is_a_fold_champion": crown in champ_sets,
        "champion_usage": {k[:60] + "...": v for k, v in champ_sets.items()}}
try:
    mod335 = load_strategy("ENGUQ_1M_ETH_R2_1_0.py")
    dp335 = mod335.DEFAULT_PARAMS
    sp335 = _auto_space_from_params(dp335)
    samp = _RandomSampler(sp335, seed=42)
    seq = [json.dumps({k: v for k, v in _collapse(samp.ask(), dp335).items() if k in pk335}, sort_keys=True)
           for _ in range(900)]
    idx = {}
    for key in list(champ_sets) + [crown]:
        try:
            idx[key[:60] + "..."] = seq.index(key)
        except ValueError:
            idx[key[:60] + "..."] = None
    mech["champion_index_in_seed42_draw"] = idx
    mech["all_fold_champions_within_first_300_draws"] = all(
        (i is not None and i < 300) for k, i in idx.items() if k != crown[:60] + "...")
    mech["crown_index_in_seed42_draw"] = idx.get(crown[:60] + "...")
    mech["n_unique_in_first_300"] = len(set(seq[:300]))
    mech["n_free_params_335"] = sum(1 for k, s in sp335.items()
                                    if not ((s[0] == "cat" and len(s[1]) <= 1) or (s[0] != "cat" and s[1] == s[2])))
except Exception as e:  # pragma: no cover
    mech["sampler_error"] = f"{type(e).__name__}: {e}"
R["checks"]["335_mechanism_shared_candidate_draw"] = mech

# ────────────────────────────────────────────────────────────────────────────
# 7. Points vs dollars sanity for the numbers quoted in the brief
# ────────────────────────────────────────────────────────────────────────────
R["checks"]["units"] = {
    "retuned_wf_oos_net_pts": doc335["validate"]["wf_oos"]["net"] if "net" in doc335["validate"]["wf_oos"]
    else sum(r["oos_pnl"] for r in doc335["top10_results"]),
    "retuned_wf_usd": round(sum(r["oos_pnl"] for r in doc335["top10_results"]) * NQ_PT),
    "fixed_ungated_wf_pts": (doc335.get("gate_validate") or {}).get("ungated_wf", {}).get("total_pnl"),
    "fixed_ungated_wf_usd": round(((doc335.get("gate_validate") or {}).get("ungated_wf", {}).get("total_pnl") or 0) * NQ_PT),
    "selection_crowned_wf_oos_pnl_pts": next(c.get("wf_oos_pnl") for c in doc335["selection"]["candidates"] if c.get("crowned")),
}

# calendar-window sanity: bars per calendar year implied by each variant
bpy = {}
for f in folds_done:
    for v, yrs in (("T_5y", 5), ("T_3y", 3), ("T_2y", 2)):
        bpy.setdefault(v, []).append(F[str(f)][v]["train_bars"] / yrs)
R["checks"]["335_bars_per_calendar_year_by_variant"] = {v: [round(x) for x in xs] for v, xs in bpy.items()}

with open(OUT, "w", encoding="utf-8") as f:
    json.dump(R, f, indent=2, default=str)
print(json.dumps(R, indent=2, default=str))
print("\nsaved:", OUT)
