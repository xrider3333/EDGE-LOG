"""wfdive lens: which reading made BEFORE the lockbox best predicts the lockbox?

Pure analysis over the Gather agent's saved _wfdive_data/runs.json — no Firestore,
no backtests, no engine calls. Run from this worktree:

    python tools/wfdive/lens_predict.py

Writes _wfdive_data/lens_predict.json with every number below, so a verifier can
recompute without re-running this script.

Readings compared, per run (engine fields — see validate.py/ml_gate.py):
  IS        — best_pnl_pts / best_trades / best_pf (Stage-A first-75% training slice).
              Years approximated as 0.75 * (windows.optimize span) since auto.py's
              75/25 split is a BAR-count split (ksplit = int(n*0.75) over the bars
              array), not a saved calendar date — flagged as an approximation.
  WF fixed  — gate_validate.ungated_wf (the FIXED crowned-champion params, sliced
              over the walk-forward calendar years by gate_validate.wf_range).
  WF re-tuned — validate.wf_oos (each fold re-tuned on its own past, stitched OOS
              trades in fold order; net/trades/pf/years are the reconciled,
              guard-checked figures per analytics.wf_oos_block).
  Lockbox   — validate.lockbox (one-shot, sealed, fixed champion params never seen
              during optimization); cross-checked against gate_validate.ungated_lockbox.

Excludes: books (validate.py never runs WF folds on a book) and any reading/lockbox
with zero trades (a zero-trade WF/lockbox test is not evidence of anything).
"""
import json
import math
import os
import random
import sys
from datetime import date

import numpy as np
from scipy.stats import spearmanr

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402

random.seed(42)
np.random.seed(42)
N_BOOT = 3000


# ── helpers ────────────────────────────────────────────────────────────────
def is_book(d):
    if d.get("book") is not None:
        return True
    scope = str(d.get("scope") or "")
    return "Book" in scope or "\U0001F4DA" in scope  # 📚


def safe_float(x):
    try:
        v = float(x)
        if math.isfinite(v):
            return v
    except (TypeError, ValueError):
        pass
    return None


def years_between(d0, d1):
    try:
        a = date.fromisoformat(str(d0)[:10])
        b = date.fromisoformat(str(d1)[:10])
        yrs = (b - a).days / 365.25
        return yrs if yrs > 0 else None
    except (TypeError, ValueError):
        return None


def rep_key(d):
    """Sort key for 'pick the newest run in a family' — timestamp string first
    (YYYY-MM-DD HH:MM, present on almost every run per Gather report), id as
    tiebreak/fallback."""
    ts = d.get("timestamp") or ""
    try:
        rid = int(d.get("id"))
    except (TypeError, ValueError):
        rid = -1
    return (str(ts), rid)


# ── extraction ───────────────────────────────────────────────────────────────
def extract(d):
    rid = d.get("id")
    fam = common.family_key(d)
    v = d.get("validate") or {}
    gv = d.get("gate_validate") or {}
    windows = v.get("windows") or {}
    opt = windows.get("optimize") or [None, None]
    wf_split = windows.get("wf_split")
    lockbox_months = windows.get("lockbox_months")

    rec = {
        "id": rid, "family": fam, "strategy": d.get("strategy"),
        "instrument": d.get("instrument"), "timeframe": d.get("timeframe"),
        "timestamp": d.get("timestamp"), "starred": bool(d.get("starred")),
        "verdict": v.get("verdict"), "is_book": is_book(d),
        "wf_best_mode": v.get("wf_best_mode"),
    }

    # ---- IS (Stage-A first 75%, bar-count split -> years approximated) ----
    is_pnl = safe_float(d.get("best_pnl_pts"))
    is_trades = d.get("best_trades")
    is_pf = safe_float(d.get("best_pf"))
    opt_years = years_between(opt[0], opt[1]) if opt[0] and opt[1] else None
    is_years = (opt_years * 0.75) if opt_years else None
    rec["is"] = None
    if is_pnl is not None and is_trades and is_years:
        rec["is"] = {"pnl": is_pnl, "trades": int(is_trades), "pf": is_pf,
                      "years": is_years, "years_approx": True}

    # ---- WF fixed (gate_validate.ungated_wf, sliced over gate_validate.wf_range) --
    uwf = gv.get("ungated_wf") if isinstance(gv, dict) else None
    wf_range = gv.get("wf_range") if isinstance(gv, dict) else None
    rec["wf_fixed"] = None
    if isinstance(uwf, dict):
        wfy = years_between(wf_range[0], wf_range[1]) if (wf_range and len(wf_range) == 2) else None
        if wfy is None and wf_split and opt[1]:
            wfy = years_between(wf_split, opt[1])
        trades = uwf.get("num_trades")
        pnl = safe_float(uwf.get("total_pnl"))
        if pnl is not None and trades and wfy:
            rec["wf_fixed"] = {"pnl": pnl, "trades": int(trades),
                                "pf": safe_float(uwf.get("profit_factor")), "years": wfy}

    # ---- WF re-tuned (validate.wf_oos: stitched, reconciled fold OOS trades) ----
    wo = v.get("wf_oos")
    rec["wf_retuned"] = None
    if isinstance(wo, dict):
        pnl = safe_float(wo.get("net"))
        trades = wo.get("trades")
        yrs = safe_float(wo.get("years"))
        if pnl is not None and trades and yrs:
            rec["wf_retuned"] = {"pnl": pnl, "trades": int(trades),
                                  "pf": safe_float(wo.get("profit_factor")), "years": yrs,
                                  "n_folds": wo.get("n_folds"), "from": wo.get("from"), "to": wo.get("to")}

    # ---- Lockbox (one-shot, sealed) ----
    lb = v.get("lockbox")
    rec["lockbox"] = None
    if isinstance(lb, dict):
        lby = years_between(lb.get("from"), lb.get("to"))
        if lby is None and lockbox_months:
            lby = float(lockbox_months) / 12.0
        pnl = safe_float(lb.get("pnl"))
        trades = lb.get("trades")
        if pnl is not None and trades and lby:
            rec["lockbox"] = {"pnl": pnl, "trades": int(trades), "pf": safe_float(lb.get("pf")),
                               "years": lby, "dd": safe_float(lb.get("dd")),
                               "from": lb.get("from"), "to": lb.get("to")}
    ulb = gv.get("ungated_lockbox") if isinstance(gv, dict) else None
    rec["ungated_lockbox_pnl"] = safe_float(ulb.get("total_pnl")) if isinstance(ulb, dict) else None

    # ---- selection (#88 Stage A.5 crown pool + #88b holdout) ----
    sel = d.get("selection")
    rec["selection"] = None
    if isinstance(sel, dict):
        cands = sel.get("candidates") or []
        wf_scores = sorted(sf for sf in (safe_float(c.get("wf_oos_pnl")) for c in cands) if sf is not None)
        crowned = next((c for c in cands if c.get("crowned")), None)
        is_max_cand = max((c for c in cands if safe_float(c.get("is_pnl")) is not None),
                           key=lambda c: safe_float(c.get("is_pnl")), default=None)

        def _cand_lb(c):
            lbx = (c or {}).get("lockbox")
            if not isinstance(lbx, dict):
                return None
            pnl = safe_float(lbx.get("total_pnl"))
            trades = lbx.get("num_trades")
            yrs = safe_float(lbx.get("years"))
            if pnl is None or not trades:
                return None
            return {"pnl": pnl, "trades": int(trades), "pf": safe_float(lbx.get("profit_factor")),
                     "years": yrs}

        rec["selection"] = {
            "k": sel.get("k"), "is_max_crowned": sel.get("is_max_crowned"),
            "n_candidates": len(cands), "wf_scores": wf_scores,
            "crowned_wf_oos_pnl": safe_float((crowned or {}).get("wf_oos_pnl")),
            "crowned_is_pnl": safe_float((crowned or {}).get("is_pnl")),
            "crowned_lockbox": _cand_lb(crowned),
            "is_max_is_pnl": safe_float((is_max_cand or {}).get("is_pnl")),
            "is_max_wf_oos_pnl": safe_float((is_max_cand or {}).get("wf_oos_pnl")),
            "is_max_lockbox": _cand_lb(is_max_cand),
            "is_max_is_crowned_is_same_config": (
                crowned is not None and is_max_cand is not None
                and crowned.get("params") == is_max_cand.get("params")
            ),
            "other_candidates_lockbox": [
                _cand_lb(c) for c in cands
                if c is not crowned and _cand_lb(c) is not None
            ],
        }
    return rec


def cold_start_flag(rec):
    """Lockbox trades/yr far below the run's own usual rate (250-day-trend /
    NQDIP-style warm-up losing most early trades) — flag, don't silently read
    as edge decay (memory: 'validate folds + lockbox start COLD')."""
    lb = rec["lockbox"]
    if not lb:
        return None
    lb_tpy = lb["trades"] / lb["years"]
    ref_tpy = None
    if rec["wf_retuned"]:
        ref_tpy = rec["wf_retuned"]["trades"] / rec["wf_retuned"]["years"]
    elif rec["wf_fixed"]:
        ref_tpy = rec["wf_fixed"]["trades"] / rec["wf_fixed"]["years"]
    if ref_tpy is None or ref_tpy <= 0:
        return None
    ratio = lb_tpy / ref_tpy
    return {"lb_trades_per_yr": round(lb_tpy, 2), "ref_trades_per_yr": round(ref_tpy, 2),
            "ratio": round(ratio, 3), "flagged": ratio < 0.4}


# ── bootstrap machinery (family-clustered) ──────────────────────────────────
def cluster_bootstrap_stat(items, family_of, stat_fn, n_boot=N_BOOT):
    """items: list of arbitrary per-run payloads. family_of: parallel list of
    family keys. stat_fn(list_of_items) -> float (or None to skip a resample).
    Resamples FAMILIES with replacement (whole family's runs move together),
    returns (point_estimate_on_real_data, (p5, p95), n_boot_used)."""
    fam_to_idx = {}
    for i, f in enumerate(family_of):
        fam_to_idx.setdefault(f, []).append(i)
    fams = list(fam_to_idx.keys())
    point = stat_fn(items)
    if point is None or not fams:
        return point, (None, None), 0
    boots = []
    for _ in range(n_boot):
        chosen = [random.choice(fams) for _ in fams]
        idxs = [i for f in chosen for i in fam_to_idx[f]]
        sample = [items[i] for i in idxs]
        s = stat_fn(sample)
        if s is not None and math.isfinite(s):
            boots.append(s)
    if not boots:
        return point, (None, None), 0
    boots.sort()
    lo = boots[int(0.05 * len(boots))]
    hi = boots[min(len(boots) - 1, int(0.95 * len(boots)))]
    return point, (lo, hi), len(boots)


def median_stat(vals):
    xs = [v for v in vals if v is not None and math.isfinite(v)]
    return float(np.median(xs)) if xs else None


def spearman_stat(pairs):
    xs = [p[0] for p in pairs]
    ys = [p[1] for p in pairs]
    if len(xs) < 3 or len(set(xs)) < 2 or len(set(ys)) < 2:
        return None
    rho, _ = spearmanr(xs, ys)
    return float(rho) if math.isfinite(rho) else None


def dedupe_one_per_family(records, keep_if):
    """One row per family: the newest run (by rep_key) satisfying keep_if."""
    best = {}
    for r in records:
        if not keep_if(r):
            continue
        f = r["family"]
        if f not in best or rep_key(r) > rep_key(best[f]):
            best[f] = r
    return list(best.values())


# ── main ─────────────────────────────────────────────────────────────────────
def main():
    runs = common.load_runs()
    print(f"loaded {len(runs)} runs")
    non_book = [d for d in runs if not is_book(d)]
    print(f"non-book: {len(non_book)}")

    recs = [extract(d) for d in non_book]
    by_id = {r["id"]: r for r in recs}

    # Universe for lockbox-anchored analyses: needs a real (non-zero-trade) lockbox.
    with_lb = [r for r in recs if r["lockbox"]]
    print(f"non-book runs with a usable (non-zero-trade) lockbox: {len(with_lb)} "
          f"across {len(set(r['family'] for r in with_lb))} families")

    cold = {r["id"]: cold_start_flag(r) for r in with_lb}
    flagged_cold = [rid for rid, c in cold.items() if c and c["flagged"]]
    print(f"cold-start flagged (lockbox trades/yr < 40% of WF trades/yr): {len(flagged_cold)} runs")

    out = {"n_runs_total": len(runs), "n_non_book": len(non_book),
           "n_with_lockbox": len(with_lb),
           "n_families_with_lockbox": len(set(r["family"] for r in with_lb)),
           "cold_start_flags": {str(rid): cold[rid] for rid in flagged_cold}}

    # ══════════════════════════════════════════════════════════════════════
    # (a) RATE DECAY: lockbox pts/yr divided by each reading's pts/yr.
    # ══════════════════════════════════════════════════════════════════════
    out["a_rate_decay"] = {}
    for name, key in (("fixed", "wf_fixed"), ("re_tuned", "wf_retuned"), ("is", "is")):
        rows = []
        for r in with_lb:
            reading = r[key]
            if not reading:
                continue
            lb = r["lockbox"]
            reading_rate = reading["pnl"] / reading["years"]
            lb_rate = lb["pnl"] / lb["years"]
            reading_pt = reading["pnl"] / reading["trades"]
            lb_pt = lb["pnl"] / lb["trades"]
            if reading_rate == 0 or reading_pt == 0:
                continue
            rows.append({
                "id": r["id"], "family": r["family"],
                "ratio_rate": lb_rate / reading_rate,
                "ratio_pertrade": lb_pt / reading_pt,
                "reading_positive": reading["pnl"] > 0,
                "lockbox_positive": lb["pnl"] > 0,
            })
        fams = [x["family"] for x in rows]
        pe_rate, ci_rate, nb1 = cluster_bootstrap_stat(
            rows, fams, lambda xs: median_stat([x["ratio_rate"] for x in xs]))
        pe_pt, ci_pt, nb2 = cluster_bootstrap_stat(
            rows, fams, lambda xs: median_stat([x["ratio_pertrade"] for x in xs]))
        # sign flips: reading said "profitable" but lockbox wasn't, or vice versa
        sign_flip_profit_to_loss = sum(1 for x in rows if x["reading_positive"] and not x["lockbox_positive"])
        sign_flip_loss_to_profit = sum(1 for x in rows if (not x["reading_positive"]) and x["lockbox_positive"])
        out["a_rate_decay"][name] = {
            "n_runs": len(rows), "n_families": len(set(fams)),
            "median_ratio_rate_lb_over_reading": pe_rate,
            "ci90_ratio_rate": list(ci_rate),
            "median_ratio_pertrade_lb_over_reading": pe_pt,
            "ci90_ratio_pertrade": list(ci_pt),
            "abs_log_ratio_rate": (abs(math.log(pe_rate)) if pe_rate and pe_rate > 0 else None),
            "sign_flip_profitable_reading_unprofitable_lockbox": sign_flip_profit_to_loss,
            "sign_flip_unprofitable_reading_profitable_lockbox": sign_flip_loss_to_profit,
        }

    # ══════════════════════════════════════════════════════════════════════
    # (b) PF: Spearman(reading PF, lockbox PF) + confusion tables.
    # ══════════════════════════════════════════════════════════════════════
    out["b_pf_predict"] = {}
    for name, key in (("fixed", "wf_fixed"), ("re_tuned", "wf_retuned"), ("is", "is")):
        pf_rows = []
        for r in with_lb:
            reading = r[key]
            lb = r["lockbox"]
            if not reading or reading.get("pf") is None or lb.get("pf") is None:
                continue
            pf_rows.append({"id": r["id"], "family": r["family"],
                             "reading_pf": reading["pf"], "lockbox_pf": lb["pf"]})
        fams = [x["family"] for x in pf_rows]
        # one-run-per-family Spearman (dedupe on this reading's availability)
        dedup = dedupe_one_per_family(with_lb, lambda r: r[key] and r[key].get("pf") is not None
                                       and r["lockbox"].get("pf") is not None)
        dedup_pairs = [(r[key]["pf"], r["lockbox"]["pf"]) for r in dedup]
        rho_dedup = spearman_stat(dedup_pairs)
        # all-runs Spearman with family-cluster bootstrap CI
        pe_rho, ci_rho, nb = cluster_bootstrap_stat(
            pf_rows, fams, lambda xs: spearman_stat([(x["reading_pf"], x["lockbox_pf"]) for x in xs]))

        def confusion(thresh):
            elig = [x for x in pf_rows if x["reading_pf"] > thresh]
            n = len(elig)
            hit = sum(1 for x in elig if x["lockbox_pf"] > 1.0)
            fams_e = len(set(x["family"] for x in elig))
            return {"n_runs": n, "n_families": fams_e,
                    "pct_lockbox_pf_gt_1": (round(100.0 * hit / n, 1) if n else None)}

        out["b_pf_predict"][name] = {
            "n_runs_all": len(pf_rows), "n_families_all": len(set(fams)),
            "n_runs_dedup": len(dedup), "spearman_rho_one_per_family": rho_dedup,
            "spearman_rho_all_runs_point": pe_rho, "spearman_rho_ci90_cluster_boot": list(ci_rho),
            "confusion_given_reading_pf_gt_1_0": confusion(1.0),
            "confusion_given_reading_pf_gt_1_2": confusion(1.2),
            "confusion_given_reading_pf_gt_1_5": confusion(1.5),
        }

    # ══════════════════════════════════════════════════════════════════════
    # (c) SELECTION HAIRCUT: k>=2 candidate runs — crowned vs finalist spread;
    #     fixed-minus-retuned gap vs lockbox shortfall (relative to fixed).
    # ══════════════════════════════════════════════════════════════════════
    sel_rows = []
    for r in with_lb:
        sel = r["selection"]
        if not sel or not sel.get("k") or sel["k"] < 2 or len(sel.get("wf_scores") or []) < 2:
            continue
        wf_scores = sel["wf_scores"]
        crowned_wf = sel.get("crowned_wf_oos_pnl")
        if crowned_wf is None:
            continue
        med_finalist = float(np.median(wf_scores))
        max_finalist = float(np.max(wf_scores))
        wff, wfr, lb = r["wf_fixed"], r["wf_retuned"], r["lockbox"]
        gap_frac = None
        shortfall_frac = None
        if wff and wfr and wff["pnl"] not in (0, None):
            fixed_rate = wff["pnl"] / wff["years"]
            retuned_rate = wfr["pnl"] / wfr["years"]
            lb_rate = lb["pnl"] / lb["years"]
            if fixed_rate != 0:
                gap_frac = (fixed_rate - retuned_rate) / abs(fixed_rate)
                shortfall_frac = (fixed_rate - lb_rate) / abs(fixed_rate)
        sel_rows.append({
            "id": r["id"], "family": r["family"], "k": sel["k"],
            "crowned_wf_oos_pnl": crowned_wf, "finalist_median_wf": med_finalist,
            "finalist_max_wf": max_finalist,
            "crowned_minus_median_frac": ((crowned_wf - med_finalist) / abs(med_finalist)
                                           if med_finalist else None),
            "crowned_is_the_max": bool(crowned_wf >= max_finalist - 1e-6),
            "fixed_minus_retuned_gap_frac": gap_frac,
            "lockbox_shortfall_vs_fixed_frac": shortfall_frac,
        })
    gap_pairs = [(x["fixed_minus_retuned_gap_frac"], x["lockbox_shortfall_vs_fixed_frac"])
                 for x in sel_rows
                 if x["fixed_minus_retuned_gap_frac"] is not None and x["lockbox_shortfall_vs_fixed_frac"] is not None]
    fams_c = [r["family"] for r in sel_rows]
    pe_c, ci_c, nb_c = cluster_bootstrap_stat(
        sel_rows, fams_c,
        lambda xs: spearman_stat([(x["fixed_minus_retuned_gap_frac"], x["lockbox_shortfall_vs_fixed_frac"])
                                   for x in xs if x["fixed_minus_retuned_gap_frac"] is not None
                                   and x["lockbox_shortfall_vs_fixed_frac"] is not None]))
    out["c_selection_haircut"] = {
        "n_runs": len(sel_rows), "n_families": len(set(fams_c)),
        "n_crowned_equals_max_finalist": sum(1 for x in sel_rows if x["crowned_is_the_max"]),
        "median_crowned_minus_median_finalist_frac": median_stat(
            [x["crowned_minus_median_frac"] for x in sel_rows]),
        "n_pairs_gap_vs_shortfall": len(gap_pairs),
        "spearman_gap_vs_shortfall_point": pe_c, "spearman_gap_vs_shortfall_ci90": list(ci_c),
        "rows": sel_rows,
    }

    # ══════════════════════════════════════════════════════════════════════
    # (d) #88b HOLDOUT: WF-crowned pick vs IS-max pick vs other finalists, on lockbox.
    # ══════════════════════════════════════════════════════════════════════
    holdout_rows = []
    for r in recs:  # note: does not require top-level validate.lockbox (uses candidate's own)
        sel = r["selection"]
        if not sel:
            continue
        if sel.get("is_max_is_crowned_is_same_config"):
            continue  # nothing to compare — same config crowned and IS-max
        c_lb = sel.get("crowned_lockbox")
        m_lb = sel.get("is_max_lockbox")
        if not c_lb or not m_lb:
            continue
        c_rate = c_lb["pnl"] / c_lb["years"] if c_lb.get("years") else None
        m_rate = m_lb["pnl"] / m_lb["years"] if m_lb.get("years") else None
        if c_rate is None or m_rate is None:
            continue
        others = sel.get("other_candidates_lockbox") or []
        other_rates = [o["pnl"] / o["years"] for o in others if o.get("years") and o["pnl"] / o["years"] != c_rate]
        holdout_rows.append({
            "id": r["id"], "family": r["family"],
            "crowned_lockbox_rate": c_rate, "is_max_lockbox_rate": m_rate,
            "crowned_beats_is_max": c_rate > m_rate,
            "crowned_beats_all_others": (c_rate >= max(other_rates)) if other_rates else None,
            "n_other_finalists": len(other_rates),
        })
    dedup_holdout = dedupe_one_per_family(
        [r for r in recs if r["id"] in {h["id"] for h in holdout_rows}], lambda r: True)
    dedup_ids = {r["id"] for r in dedup_holdout}
    dedup_holdout_rows = [h for h in holdout_rows if h["id"] in dedup_ids]
    out["d_88b_holdout"] = {
        "n_runs_all": len(holdout_rows), "n_families_all": len(set(h["family"] for h in holdout_rows)),
        "n_runs_dedup": len(dedup_holdout_rows),
        "crowned_beats_is_max_wins_dedup": sum(1 for h in dedup_holdout_rows if h["crowned_beats_is_max"]),
        "crowned_beats_is_max_losses_dedup": sum(1 for h in dedup_holdout_rows if not h["crowned_beats_is_max"]),
        "crowned_beats_all_others_wins_dedup": sum(
            1 for h in dedup_holdout_rows if h["crowned_beats_all_others"] is True),
        "crowned_beats_all_others_losses_dedup": sum(
            1 for h in dedup_holdout_rows if h["crowned_beats_all_others"] is False),
        "rows": holdout_rows,
    }

    # ── save ───────────────────────────────────────────────────────────────
    out_path = os.path.join(common.DATA_DIR, "lens_predict.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, default=str, indent=1)
    print(f"\nsaved -> {out_path}")
    print(json.dumps({k: v for k, v in out.items() if k not in ("cold_start_flags",)
                       and not (isinstance(v, dict) and "rows" in v)}, default=str, indent=1)[:6000])


if __name__ == "__main__":
    main()
