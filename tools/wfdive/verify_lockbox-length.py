"""VERIFY (adversarial): recompute the "Is a 12-month lockbox long enough" lens
(tools/wfdive/lens_lblen.py -> _wfdive_data/lens_lblen.json, plus the two aux
corpus reads) from the SAVED files with independent code, and re-replay the 20
champions to test the lens's own window definitions.

Only wfdive.common loaders are imported (setup_data_env / low_priority / cpu_lock /
family_key / load_runs); nothing from the lens's own analysis functions.

PART A  -- pure data reads (lens_lblen.json, aux_*.json, runs.json, coverage.json):
  A1 selection audit: verification flags, doc lockbox_months, crown-pool size,
     is_max_crowned, mechanism families, identical-result pairs.
  A2 claim 1 (engine power field): recompute corpus stats, dedupe by family and by
     mechanism, check UNITS (points vs $), extrapolate the engine's own classical
     power to 18/24/36-month lockboxes for the crowns.
  A3 claim 3 (no-edge control): check p_verdict_pass == p_net_gt_0 identity.
  A4 claim 4 (fixed vs re-tuned WF): recompute shares; split by crown-pool size,
     by re-tuned/fixed trade-count ratio (cold-start), by mechanism; window
     alignment; duplicate rows; lockbox-PF vs WF-PF selection-effect test.
  A5 claim 5 (recency): recompute Spearman(year, PF) from by_year with/without
     partial years; check the crowns' "extra year" windows vs doc lockbox length.
  A6 claim 6 (cold start): recompute medians with the doc's true lockbox length.
PART B  -- replay (cpu_lock, BELOW_NORMAL priority, single process):
  For each of the 20 lens runs: continuous whole-run replay + cold lockbox replay
  of the saved champion; compute the Stage-A 75%-of-bars split date (auto.py
  OOS_SPLIT = 0.75 over the optimize window) and check it against
  validate.is_trades; rebuild the lens's pool (>= wf_split) AND the corrected
  Stage-A-OOS pool (>= ksplit date); month-block bootstrap (own code) +
  CONTIGUOUS rolling-window pass rates at 12/18/24/36 months; decompose the fixed
  champion's "WF" stretch into its Stage-A in-sample part and its out-of-sample
  part; compare with the re-tuned folds on the same out-of-sample stretch.

Run from the worktree root:
    python tools/wfdive/verify_lockbox-length.py            (A + B)
    python tools/wfdive/verify_lockbox-length.py --no-replay (A only)
Writes _wfdive_data/verify_lockbox-length.json
"""
import datetime as _dt
import json
import math
import os
import re
import statistics
import sys
import traceback
from collections import Counter, defaultdict

import numpy as np
import pandas as pd
from scipy import stats as _sps

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # -> tools/
from wfdive.common import (  # noqa: E402
    setup_data_env, low_priority, cpu_lock, family_key, load_runs, DATA_DIR,
)

os.environ.setdefault("AUGUR_TRIAL_CACHE", "1")

OUT_PATH = os.path.join(DATA_DIR, "verify_lockbox-length.json")
LENS_PATH = os.path.join(DATA_DIR, "lens_lblen.json")
AUXP_PATH = os.path.join(DATA_DIR, "aux_power_field_corpus.json")
AUXF_PATH = os.path.join(DATA_DIR, "aux_fixed_vs_retuned_corpus.json")
COV_PATH = os.path.join(DATA_DIR, "coverage.json")

SESSION_MAP = {"db_noadj_rth": "rth", "db_noadj_eth": "eth", "yahoo_adj": "rth"}
CROWN_IDS = [257, 335, 243]
LENGTHS = [12, 18, 24, 36]
N_RES = 2500
SEED = 777   # deliberately different from the lens's seed
Z_ALPHA, Z_POWER = 1.6449, 0.8416


def log(*a):
    print("[verify_lblen]", *a, flush=True)


def _phi(x):
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def mechanism(strategy):
    stem = re.sub(r"\.py$", "", str(strategy or ""), flags=re.I)
    m = re.match(r"[A-Za-z]+", stem)
    return (m.group(0).upper() if m else stem.upper())


def med(xs):
    xs = [x for x in xs if x is not None and not (isinstance(x, float) and math.isnan(x))]
    return round(statistics.median(xs), 4) if xs else None


def metrics(pnls):
    pnls = [float(p) for p in pnls]
    n = len(pnls)
    if not n:
        return {"trades": 0, "net": 0.0, "pf": None, "win_rate": None, "net_per_trade": None}
    gw = sum(p for p in pnls if p > 0)
    gl = -sum(p for p in pnls if p < 0)
    pf = (gw / gl) if gl > 1e-9 else (float("inf") if gw > 0 else 0.0)
    return {"trades": n, "net": round(sum(pnls), 3),
            "pf": (round(pf, 4) if math.isfinite(pf) else None),
            "win_rate": round(100.0 * sum(1 for p in pnls if p > 0) / n, 2),
            "net_per_trade": round(sum(pnls) / n, 4)}


# ═════════════════════════════════════════════════════════════════════════════
# PART A -- saved-file recomputation
# ═════════════════════════════════════════════════════════════════════════════
def part_a(lens, auxp, auxf, cov, runs):
    by = {r["id"]: r for r in runs}
    book_ids = set(cov.get("books", {}).get("ids") or [])
    A = {}
    lens_runs = lens["runs"]
    sel_ids = [r["id"] for r in lens_runs]

    # ── A1 selection audit ───────────────────────────────────────────────────
    rows = []
    for r in lens_runs:
        d = by.get(r["id"], {})
        s = d.get("selection") or {}
        cands = s.get("candidates") or []
        v = d.get("validate") or {}
        lb = v.get("lockbox") or {}
        rows.append({
            "id": r["id"], "strategy": r.get("strategy"), "mechanism": mechanism(r.get("strategy")),
            "family": r.get("family"), "crown": r.get("crown"),
            "lockbox_months_doc": r.get("lockbox_months_doc"),
            "verify_lockbox_ok": (r.get("verify_lockbox_reproduction") or {}).get("ok"),
            "verify_ungated_full_ok": (r.get("verify_ungated_full_secondary") or {}).get("ok")
            if r.get("verify_ungated_full_secondary") else "absent",
            "crown_pool_size": len(cands), "is_max_crowned": s.get("is_max_crowned"),
            "wf_split_source": (r.get("wf_split") or {}).get("source"),
            "wf_split": (r.get("wf_split") or {}).get("date"),
            "honest_trades_lens": (r.get("honest_edge") or {}).get("trades"),
            "stageA_is_trades_doc": v.get("is_trades"),
            "pre_wfsplit_trades_doc": ((d.get("gate_validate") or {}).get("ungated_is") or {}).get("num_trades"),
            "lockbox_trades": lb.get("trades"), "lockbox_pf": lb.get("pf"), "lockbox_pass": lb.get("pass"),
        })
    mech_counts = Counter(x["mechanism"] for x in rows)
    # identical-result pairs among the 20 (same wf_oos net + same lockbox pnl)
    sig = defaultdict(list)
    for r in lens_runs:
        d = by.get(r["id"], {})
        v = d.get("validate") or {}
        key = (round(float((v.get("wf_oos") or {}).get("net") or 0), 1),
               round(float((v.get("lockbox") or {}).get("pnl") or 0), 1),
               int((v.get("lockbox") or {}).get("trades") or 0))
        sig[key].append(r["id"])
    dup_pairs = [ids for ids in sig.values() if len(ids) > 1]
    A["A1_selection_audit"] = {
        "n_lens_runs": len(lens_runs),
        "all_lockbox_reproduction_ok": all(x["verify_lockbox_ok"] for x in rows),
        "ungated_full_check": Counter(str(x["verify_ungated_full_ok"]) for x in rows),
        "lockbox_months_doc": Counter(x["lockbox_months_doc"] for x in rows),
        "runs_not_12mo": [(x["id"], x["lockbox_months_doc"]) for x in rows if x["lockbox_months_doc"] != 12],
        "crown_pool_size": Counter(x["crown_pool_size"] for x in rows),
        "n_crowned_by_wf_among_gt1": sum(1 for x in rows if x["crown_pool_size"] > 1),
        "n_is_max_NOT_crowned": sum(1 for x in rows if x["is_max_crowned"] is False),
        "mechanism_counts": dict(mech_counts),
        "n_distinct_mechanisms": len(mech_counts),
        "identical_result_pairs": dup_pairs,
        "stageA_is_trades_vs_pre_wfsplit": [
            {"id": x["id"], "stageA_is_trades": x["stageA_is_trades_doc"],
             "pre_wfsplit_trades": x["pre_wfsplit_trades_doc"],
             "honest_pool_trades_lens": x["honest_trades_lens"],
             "approx_stageA_IS_trades_inside_lens_honest_pool":
                 ((x["stageA_is_trades_doc"] or 0) - (x["pre_wfsplit_trades_doc"] or 0))
                 if x["stageA_is_trades_doc"] and x["pre_wfsplit_trades_doc"] else None}
            for x in rows],
        "actual_lockbox_pass_share_20": round(sum(1 for x in rows if x["lockbox_pass"]) / len(rows), 3),
        "rows": rows,
    }

    # ── A2 claim 1: engine power field ───────────────────────────────────────
    prow = auxp["rows"]
    vals = [x["achieved_power"] for x in prow if x["achieved_power"] is not None]
    n_pow = sum(1 for x in prow if x["powered_ge_0.80"])
    # dedupe by family (newest id) and by mechanism (newest id)
    fam_best, mech_best = {}, {}
    for x in sorted(prow, key=lambda x: -x["id"]):
        d = by.get(x["id"], {})
        fk = family_key(d) if d else f"?{x['id']}"
        fam_best.setdefault(fk, x)
        mech_best.setdefault(mechanism(x["strategy"]), x)
    fam_vals = [x["achieved_power"] for x in fam_best.values() if x["achieved_power"] is not None]
    mech_vals = [x["achieved_power"] for x in mech_best.values() if x["achieved_power"] is not None]
    # units check: lockbox pnl/trade (points, from validate.lockbox) vs claimed/mde
    units = []
    for rid in CROWN_IDS:
        d = by[rid]; p = d.get("power") or {}; lb = d["validate"]["lockbox"]
        mult = float(d.get("multiplier") or 20)
        units.append({"id": rid, "lockbox_pnl_pts": lb["pnl"], "lockbox_trades": lb["trades"],
                      "lockbox_pts_per_trade": round(lb["pnl"] / lb["trades"], 3),
                      "power_claimed_per_trade": p.get("claimed_per_trade"),
                      "power_mde_per_trade": p.get("mde_per_trade"), "power_sd": p.get("sd"),
                      "doc_multiplier_usd_per_pt": mult,
                      "mde_in_usd": round(float(p.get("mde_per_trade") or 0) * mult, 1),
                      "claimed_in_usd": round(float(p.get("claimed_per_trade") or 0) * mult, 1)})
    # classical extrapolation for crowns: power(L) with n scaled by L / lockbox_months
    extrap = []
    for rid in CROWN_IDS:
        d = by[rid]; p = d.get("power") or {}; v = d["validate"]; lb = v["lockbox"]
        L0 = int(v["windows"]["lockbox_months"]); n0 = int(p["n"]); sd = float(p["sd"])
        claimed = float(p["claimed_per_trade"]); lb_mean = lb["pnl"] / lb["trades"]
        row = {"id": rid, "lockbox_months_doc": L0, "n_lockbox_trades": n0, "sd_pts": sd,
               "claimed_per_trade_pts": round(claimed, 3), "lockbox_observed_mean_pts": round(lb_mean, 3),
               "achieved_power_doc": p.get("achieved_power"), "power_by_length": {},
               "power_by_length_using_lockbox_mean": {}}
        for L in LENGTHS:
            n = n0 * L / L0
            se = sd / math.sqrt(n)
            row["power_by_length"][str(L)] = round(_phi(claimed / se - Z_ALPHA), 3)
            row["power_by_length_using_lockbox_mean"][str(L)] = round(_phi(lb_mean / se - Z_ALPHA), 3)
        n_req = ((Z_ALPHA + Z_POWER) * sd / claimed) ** 2 if claimed > 0 else float("inf")
        n_req2 = ((Z_ALPHA + Z_POWER) * sd / lb_mean) ** 2 if lb_mean > 0 else float("inf")
        row["months_for_80pct_power_claimed"] = round(n_req / (n0 / L0), 1)
        row["months_for_80pct_power_lockbox_mean"] = round(n_req2 / (n0 / L0), 1)
        extrap.append(row)
    A["A2_claim1_power_field"] = {
        "n_rows": len(prow), "n_powered": n_pow, "median_achieved_power": med(vals),
        "share_lt_0.20": round(sum(1 for x in vals if x < 0.2) / len(vals), 3),
        "dedup_by_family": {"n": len(fam_best), "median": med(fam_vals),
                            "share_lt_0.20": round(sum(1 for x in fam_vals if x < 0.2) / len(fam_vals), 3),
                            "n_powered": sum(1 for x in fam_best.values() if x["powered_ge_0.80"])},
        "dedup_by_mechanism": {"n": len(mech_best), "median": med(mech_vals),
                               "mechanisms": sorted(mech_best)},
        "rows_in_books": [x["id"] for x in prow if x["id"] in book_ids],
        "lockbox_months_distribution": Counter(x["lockbox_months"] for x in prow),
        "units_check_crowns": units,
        "classical_extrapolation_crowns": extrap,
    }

    # ── A3 claim 3: identity p_verdict_pass == p_net_gt_0 ────────────────────
    ident, noedge = [], defaultdict(list)
    realp = defaultdict(list)
    for r in lens_runs:
        pt = r.get("power_table") or {}
        for L, blk in pt.items():
            for k in ("real_edge", "no_edge_control"):
                b = blk[k]
                ident.append(abs(b["p_verdict_pass"] - b["p_net_gt_0"]) < 1e-12)
            noedge[L].append(blk["no_edge_control"]["p_verdict_pass"])
            realp[L].append(blk["real_edge"]["p_verdict_pass"])
    A["A3_claim3_noedge"] = {
        "p_verdict_pass_equals_p_net_gt_0_everywhere": all(ident), "n_checks": len(ident),
        "noedge_median_by_L": {L: med(v) for L, v in noedge.items()},
        "noedge_min_max_by_L": {L: (round(min(v), 3), round(max(v), 3)) for L, v in noedge.items()},
        "real_median_by_L_lens_pool": {L: med(v) for L, v in realp.items()},
        "real_min_by_L_lens_pool": {L: round(min(v), 3) for L, v in realp.items()},
        "n_runs_with_power_table": sum(1 for r in lens_runs if r.get("power_table")),
        "crossing_null_everywhere": all(r.get("power_crossing_months") is None for r in lens_runs),
    }

    # ── A4 claim 4: fixed vs re-tuned WF ─────────────────────────────────────
    rows_all = auxf["rows_all"]; dedup = auxf["rows_deduped_families"]
    n_all = len(rows_all)

    def _pf_beats(r):
        return bool(r["fixed_wf_pf"] and r["retuned_wf_pf"] and r["fixed_wf_pf"] > r["retuned_wf_pf"])

    def _net_beats(r):
        return bool(r["fixed_wf_net"] is not None and r["retuned_wf_net"] is not None
                    and r["fixed_wf_net"] > r["retuned_wf_net"])

    # my own dedup from rows_all
    seen, mydedup = set(), []
    for r in sorted(rows_all, key=lambda r: -r["id"]):
        if r["family"] in seen:
            continue
        seen.add(r["family"]); mydedup.append(r)
    books_in = [r["id"] for r in rows_all if r["id"] in book_ids]
    zero_tr = [r["id"] for r in rows_all if not r["retuned_wf_trades"] or not r["fixed_wf_trades"]]

    enriched = []
    for r in mydedup:
        d = by.get(r["id"], {}); s = d.get("selection") or {}
        v = d.get("validate") or {}; wo = v.get("wf_oos") or {}; gv = d.get("gate_validate") or {}
        lb = v.get("lockbox") or {}
        enriched.append({
            **r, "mechanism": mechanism(r["strategy"]),
            "crown_pool_size": len(s.get("candidates") or []) if s else 0,
            "selection_mode": s.get("mode") if s else None,
            "is_max_crowned": s.get("is_max_crowned") if s else None,
            "trade_ratio_retuned_over_fixed": round(r["retuned_wf_trades"] / r["fixed_wf_trades"], 3),
            "wf_oos_from": wo.get("from"), "wf_oos_to": wo.get("to"), "wf_range": gv.get("wf_range"),
            "wf_oos_backfill": wo.get("backfill"), "wf_oos_mode": wo.get("mode"),
            "lockbox_pf": lb.get("pf"), "lockbox_trades": lb.get("trades"), "lockbox_pass": lb.get("pass"),
            "pf_beats": _pf_beats(r), "net_beats": _net_beats(r),
        })

    def _share(rs, fn):
        return {"n": sum(1 for r in rs if fn(r)), "of": len(rs),
                "share": (round(sum(1 for r in rs if fn(r)) / len(rs), 3) if rs else None)}

    grp_pool = defaultdict(list)
    for r in enriched:
        k = "1_candidate" if r["crown_pool_size"] == 1 else ("gt1_candidates" if r["crown_pool_size"] > 1 else "no_selection")
        grp_pool[k].append(r)
    grp_ratio = defaultdict(list)
    for r in enriched:
        tr = r["trade_ratio_retuned_over_fixed"]
        k = ("retuned_lt_0.8x_fixed" if tr < 0.8 else ("retuned_gt_1.25x_fixed" if tr > 1.25 else "within_0.8_1.25"))
        grp_ratio[k].append(r)
    grp_mech = defaultdict(list)
    for r in enriched:
        grp_mech[r["mechanism"]].append(r)
    # window alignment: wf_oos.from vs wf_range[0], wf_oos.to vs wf_range[1] (days apart)
    misaligned = []
    for r in enriched:
        if r["wf_range"] and r["wf_oos_from"] and r["wf_oos_to"]:
            d0 = abs((pd.Timestamp(r["wf_oos_from"]) - pd.Timestamp(r["wf_range"][0])).days)
            d1 = abs((pd.Timestamp(r["wf_oos_to"]) - pd.Timestamp(r["wf_range"][1])).days)
            if d0 > 7 or d1 > 7:
                misaligned.append({"id": r["id"], "wf_oos": [r["wf_oos_from"], r["wf_oos_to"]],
                                   "wf_range": r["wf_range"], "days_off": [d0, d1]})
    # duplicate rows among "independent" families (identical numbers)
    sig2 = defaultdict(list)
    for r in enriched:
        sig2[(round(r["retuned_wf_net"] or 0, 1), round(r["fixed_wf_net"] or 0, 1),
              r["retuned_wf_trades"], r["fixed_wf_trades"])].append(r["id"])
    dup_fams = [ids for ids in sig2.values() if len(ids) > 1]
    # selection-effect test: lockbox PF vs fixed-WF PF and vs re-tuned WF PF by crown-pool size
    sel_test = {}
    for k, rs in grp_pool.items():
        rs2 = [r for r in rs if (r["lockbox_trades"] or 0) >= 30 and r["lockbox_pf"] is not None
               and r["fixed_wf_pf"] and r["retuned_wf_pf"]]
        if len(rs2) < 3:
            sel_test[k] = {"n": len(rs2)}
            continue
        lbp = [r["lockbox_pf"] for r in rs2]; fp = [r["fixed_wf_pf"] for r in rs2]; rp = [r["retuned_wf_pf"] for r in rs2]
        sel_test[k] = {
            "n": len(rs2),
            "median_fixed_wf_pf": med(fp), "median_retuned_wf_pf": med(rp), "median_lockbox_pf": med(lbp),
            "share_lockbox_pf_below_fixed_wf_pf": round(sum(1 for r in rs2 if r["lockbox_pf"] < r["fixed_wf_pf"]) / len(rs2), 3),
            "share_lockbox_pf_below_retuned_wf_pf": round(sum(1 for r in rs2 if r["lockbox_pf"] < r["retuned_wf_pf"]) / len(rs2), 3),
            "median_gap_fixed_minus_lockbox_pf": med([f - l for f, l in zip(fp, lbp)]),
            "median_gap_retuned_minus_lockbox_pf": med([q - l for q, l in zip(rp, lbp)]),
            "spearman_fixed_wf_pf_vs_lockbox_pf": [round(float(x), 3) for x in _sps.spearmanr(fp, lbp)],
            "spearman_retuned_wf_pf_vs_lockbox_pf": [round(float(x), 3) for x in _sps.spearmanr(rp, lbp)],
            "lockbox_pass_share": round(sum(1 for r in rs2 if r["lockbox_pass"]) / len(rs2), 3),
        }
    A["A4_claim4_fixed_vs_retuned"] = {
        "n_rows_all": n_all, "n_dedup_lens": len(dedup), "n_dedup_mine": len(mydedup),
        "books_included": books_in, "zero_trade_rows": zero_tr,
        "pf_share_all": _share(rows_all, _pf_beats), "net_share_all": _share(rows_all, _net_beats),
        "pf_share_dedup": _share(mydedup, _pf_beats), "net_share_dedup": _share(mydedup, _net_beats),
        "by_crown_pool_size": {k: {"pf": _share(v, lambda r: r["pf_beats"]), "net": _share(v, lambda r: r["net_beats"]),
                                   "median_trade_ratio": med([r["trade_ratio_retuned_over_fixed"] for r in v])}
                               for k, v in grp_pool.items()},
        "by_trade_ratio": {k: {"pf": _share(v, lambda r: r["pf_beats"]), "net": _share(v, lambda r: r["net_beats"])}
                           for k, v in grp_ratio.items()},
        "by_mechanism": {k: {"n": len(v), "pf": _share(v, lambda r: r["pf_beats"]), "net": _share(v, lambda r: r["net_beats"])}
                         for k, v in sorted(grp_mech.items())},
        "n_mechanisms": len(grp_mech),
        "mechanism_majority_vote_pf": {k: (sum(1 for r in v if r["pf_beats"]) > len(v) / 2) for k, v in grp_mech.items()},
        "window_misaligned_gt_7d": misaligned,
        "duplicate_number_families": dup_fams,
        "selection_effect_lockbox_vs_wf": sel_test,
        "wf_oos_backfill_count": Counter(str(r["wf_oos_backfill"]) for r in enriched),
        "rows": enriched,
    }

    # ── A5 claim 5: recency ──────────────────────────────────────────────────
    rec = []
    for r in lens_runs:
        yt = r.get("by_year") or []
        full = [(y["year"], y["pf"]) for y in yt if y["trades"] >= 5 and y["pf"] is not None]
        nopart = [(y, p) for y, p in full if 2011 <= y <= 2025]
        def _rho(pairs):
            if len(pairs) < 4:
                return (None, None, len(pairs))
            rho, pv = _sps.spearmanr([a for a, _ in pairs], [b for _, b in pairs])
            return (round(float(rho), 3), round(float(pv), 4), len(pairs))
        rc = r.get("recency_cost") or {}
        e24 = rc.get("extra_12mo_if_lockbox_to_24") or {}
        L0 = r.get("lockbox_months_doc")
        rec.append({"id": r["id"], "crown": r["crown"], "mechanism": mechanism(r["strategy"]),
                    "lens_rho": (r.get("recency_pf_trend") or {}).get("spearman_rho"),
                    "lens_p": (r.get("recency_pf_trend") or {}).get("p_value"),
                    "my_rho_all_years": _rho(full), "my_rho_2011_2025": _rho(nopart),
                    "years_in_table": [y["year"] for y in yt][:1] + [y["year"] for y in yt][-1:],
                    "lockbox_months_doc": L0,
                    "extra_window_months_actual": (24 - L0) if L0 else None,
                    "extra_12mo_if_lockbox_to_24_lens": e24,
                    "honest_pf_lens": (r.get("honest_edge") or {}).get("pf")})
    sig_pos = [x["id"] for x in rec if x["my_rho_all_years"][0] is not None and x["my_rho_all_years"][1] < 0.05 and x["my_rho_all_years"][0] > 0]
    sig_pos_np = [x["id"] for x in rec if x["my_rho_2011_2025"][0] is not None and x["my_rho_2011_2025"][1] < 0.05 and x["my_rho_2011_2025"][0] > 0]
    A["A5_claim5_recency"] = {
        "lens_rho_matches_mine": all(x["lens_rho"] is None or abs(x["lens_rho"] - x["my_rho_all_years"][0]) < 1e-6 for x in rec),
        "sig_positive_all_years": sig_pos, "n_sig_positive_all_years": len(sig_pos),
        "sig_positive_2011_2025_only": sig_pos_np, "n_sig_positive_2011_2025": len(sig_pos_np),
        "rows": rec,
    }

    # ── A6 claim 6: cold start ───────────────────────────────────────────────
    cs = []
    for r in lens_runs:
        c = r.get("cold_start_share") or {}
        cs.append({"id": r["id"], "crown": r["crown"], "mechanism": mechanism(r["strategy"]),
                   "lockbox_months_doc": r.get("lockbox_months_doc"),
                   "lens_12mo_label_actual_months": r.get("lockbox_months_doc"),
                   "share_12": (c.get("12mo") or {}).get("share_lost"),
                   "share_24": (c.get("24mo") or {}).get("share_lost"),
                   "warm12": (c.get("12mo") or {}).get("warm_trades"), "cold12": (c.get("12mo") or {}).get("cold_trades"),
                   "warm24": (c.get("24mo") or {}).get("warm_trades"), "cold24": (c.get("24mo") or {}).get("cold_trades")})
    all12 = [x["share_12"] for x in cs if x["share_12"] is not None]
    all24 = [x["share_24"] for x in cs if x["share_24"] is not None]
    true12 = [x for x in cs if x["lockbox_months_doc"] == 12 and x["id"] != 377]
    A["A6_claim6_cold_start"] = {
        "median_all20_12label": med(all12), "median_all20_24label": med(all24),
        "median_true12mo_runs_excl377_at12": med([x["share_12"] for x in true12]),
        "median_true12mo_runs_excl377_at24": med([x["share_24"] for x in true12]),
        "n_true12mo_runs_excl377": len(true12),
        "mislabelled": [(x["id"], x["lockbox_months_doc"], x["share_12"], x["share_24"]) for x in cs if x["lockbox_months_doc"] != 12],
        "noise_rows": [(x["id"], x["share_12"], x["share_24"]) for x in cs if x["mechanism"] == "NOISE"],
        "rows": cs,
    }

    # corpus-wide lockbox pass share (dedup families, non-book, lockbox trades >= 10)
    fam_lb = {}
    for d in sorted(runs, key=lambda d: -d["id"]):
        if d["id"] in book_ids:
            continue
        lb = (d.get("validate") or {}).get("lockbox") or {}
        if (lb.get("trades") or 0) < 10:
            continue
        fam_lb.setdefault(family_key(d), lb.get("pass"))
    A["corpus_lockbox_pass_share_dedup_families"] = {
        "n_families": len(fam_lb), "share_pass": round(sum(1 for v in fam_lb.values() if v) / len(fam_lb), 3) if fam_lb else None}
    return A


# ═════════════════════════════════════════════════════════════════════════════
# PART B -- replay
# ═════════════════════════════════════════════════════════════════════════════
_FULL = {}


def _full_arrays(instrument, timeframe, session, source):
    key = (instrument, timeframe, session, source)
    if key not in _FULL:
        from augur_engine.data import find_master, load_master_arrays
        m = find_master(instrument, timeframe, session, source)
        _FULL[key] = (load_master_arrays(m, date_from=None, date_to=None) if m else None)
    return _FULL[key]


def _slice(full, date_from, date_to):
    idx = full["index"]
    mask = np.ones(len(idx), dtype=bool)
    if date_from:
        mask &= (idx >= pd.Timestamp(date_from, tz=idx.tz))
    if date_to:
        mask &= (idx < pd.Timestamp(date_to, tz=idx.tz) + pd.Timedelta(days=1))
    sub = idx[mask]
    return {"open": full["open"][mask], "high": full["high"][mask], "low": full["low"][mask],
            "close": full["close"][mask],
            "volume": (full["volume"][mask] if full.get("volume") is not None else None),
            "day_id": pd.factorize(pd.Series(sub).dt.date)[0].astype("int64"),
            "index": sub, "meta": full.get("meta")}


def _replay(doc, arrays, params):
    from augur_engine.engine import run_backtest
    res = run_backtest(doc["strategy"], arrays=arrays, params=params,
                       cost_pts=float(doc.get("cost_pts") or 0.0), return_trades=True)
    idx = arrays["index"]; nb = len(idx)
    pairs = []
    for t in (res or {}).get("trades") or []:
        pairs.append((pd.Timestamp(idx[min(max(int(t[0]), 0), nb - 1)]), float(t[2])))
    pairs.sort(key=lambda x: x[0])
    return res, pairs


def _month_net(pairs):
    b = defaultdict(float)
    for ts, p in pairs:
        b[(ts.year, ts.month)] += p
    return b


def _boot(pairs, L, rng, n=N_RES):
    b = _month_net(pairs)
    keys = sorted(b)
    if not keys:
        return None
    net = np.array([b[k] for k in keys])
    draws = rng.integers(0, len(keys), size=(n, L))
    s = net[draws].sum(axis=1)
    return {"p_net_gt_0": round(float(np.mean(s > 0)), 4), "n_months": len(keys)}


def _contig(pairs, L):
    """Pass share over every CONTIGUOUS L-month window (monthly starts) fully inside
    the pool span -- calendar months, empty months count as 0."""
    if not pairs:
        return None
    b = _month_net(pairs)
    t0, t1 = pairs[0][0], pairs[-1][0]
    first = pd.Period(t0.strftime("%Y-%m"), "M"); last = pd.Period(t1.strftime("%Y-%m"), "M")
    months = list(pd.period_range(first, last, freq="M"))
    net = np.array([b.get((m.year, m.month), 0.0) for m in months])
    if len(net) < L:
        return None
    sums = np.array([net[i:i + L].sum() for i in range(len(net) - L + 1)])
    return {"share_pass": round(float(np.mean(sums > 0)), 4), "n_windows": int(len(sums)),
            "min_net": round(float(sums.min()), 1), "median_net": round(float(np.median(sums)), 1)}


def part_b(lens, runs):
    by = {r["id"]: r for r in runs}
    rng = np.random.default_rng(SEED)
    out = []
    with cpu_lock("verify_lblen: 20 champion replays (single-threaded, low-priority)"):
        for lr in lens["runs"]:
            rid = lr["id"]; d = by[rid]
            log(f"--- #{rid} {d.get('strategy')} {d.get('instrument')} {d.get('timeframe')}")
            row = {"id": rid, "crown": rid in CROWN_IDS, "strategy": d.get("strategy"),
                   "mechanism": mechanism(d.get("strategy"))}
            try:
                v = d["validate"]; w = v["windows"]; champ = v["champion"]
                opt_from, opt_to = w["optimize"]; lb_from = w["lockbox"][0]
                date_from, date_to = d["date_from"], d["date_to"]
                sess = SESSION_MAP[d["data_source"]]
                full = _full_arrays(d["instrument"], d["timeframe"], sess, d["data_source"])
                if full is None:
                    row["error"] = "no master"; out.append(row); continue
                tz = full["index"].tz
                # Stage-A 75% split (auto.py OOS_SPLIT over the optimize window, by BARS)
                arr_opt = _slice(full, opt_from, opt_to)
                n_opt = len(arr_opt["index"]); ks = int(n_opt * 0.75)
                ks_ts = pd.Timestamp(arr_opt["index"][ks])
                row["stageA_split"] = {"n_opt_bars": n_opt, "doc_bars": d.get("bars"), "ksplit_bar": ks,
                                       "ksplit_date": ks_ts.date().isoformat()}
                # continuous replay
                arr_a = _slice(full, date_from, date_to)
                res_a, pairs_a = _replay(d, arr_a, champ)
                # cold lockbox replay (validate.py's own construction)
                arr_b = _slice(full, lb_from, date_to)
                res_b, pairs_b = _replay(d, arr_b, champ)
                lb_saved = v["lockbox"]
                mb = metrics([p for _, p in pairs_b])
                row["lockbox_reproduction"] = {
                    "replayed": mb, "saved": {"trades": lb_saved["trades"], "net": round(lb_saved["pnl"], 3), "pf": lb_saved["pf"]},
                    "ok": (abs(mb["trades"] - lb_saved["trades"]) <= 1 and abs(mb["net"] - lb_saved["pnl"]) <= max(5, 0.02 * abs(lb_saved["pnl"])))}
                gv = d.get("gate_validate") or {}
                uf = gv.get("ungated_full") or {}
                ma = metrics([p for _, p in pairs_a])
                row["ungated_full_reproduction"] = {"replayed": ma, "saved": {"trades": uf.get("num_trades"), "net": uf.get("total_pnl")},
                                                    "ok": (bool(uf) and abs(ma["trades"] - int(uf.get("num_trades") or 0)) <= 2)}
                # check ksplit against validate.is_trades (Stage-A IS trade count)
                is_pairs = [(t, p) for t, p in pairs_a if t < ks_ts]
                row["stageA_split"]["champion_trades_before_ksplit"] = len(is_pairs)
                row["stageA_split"]["validate_is_trades_doc"] = v.get("is_trades")
                row["stageA_split"]["best_pnl_pts_doc"] = d.get("best_pnl_pts")
                row["stageA_split"]["champion_net_before_ksplit"] = round(sum(p for _, p in is_pairs), 1)
                # pools
                wf_split = (lr.get("wf_split") or {}).get("date")
                wf_ts = pd.Timestamp(wf_split, tz=tz) if wf_split else None
                lb_ts = pd.Timestamp(lb_from, tz=tz); opt_to_ts = pd.Timestamp(opt_to, tz=tz) + pd.Timedelta(days=1)
                pool_lens = [(t, p) for t, p in pairs_a if wf_ts is not None and t >= wf_ts]
                pool_oos = [(t, p) for t, p in pairs_a if t >= ks_ts]
                pool_lb = [(t, p) for t, p in pairs_a if t >= lb_ts]
                seg_wf_is = [(t, p) for t, p in pairs_a if wf_ts is not None and wf_ts <= t < ks_ts]
                seg_wf_oos = [(t, p) for t, p in pairs_a if ks_ts <= t < opt_to_ts]
                seg_wf_all = [(t, p) for t, p in pairs_a if wf_ts is not None and wf_ts <= t < opt_to_ts]
                row["pools"] = {
                    "lens_pool_from_wf_split": {"from": wf_split, **metrics([p for _, p in pool_lens])},
                    "stageA_oos_pool_from_ksplit": {"from": ks_ts.date().isoformat(), **metrics([p for _, p in pool_oos])},
                    "lockbox_only_warm_slice": {"from": lb_from, **metrics([p for _, p in pool_lb])},
                    "share_of_lens_pool_that_was_stageA_in_sample": (round(len(seg_wf_is) / len(pool_lens), 3) if pool_lens else None),
                }
                row["fixed_wf_decomposition"] = {
                    "wf_stretch_all": metrics([p for _, p in seg_wf_all]),
                    "wf_stretch_stageA_in_sample_part": {"to": ks_ts.date().isoformat(), **metrics([p for _, p in seg_wf_is])},
                    "wf_stretch_stageA_oos_part": {"from": ks_ts.date().isoformat(), **metrics([p for _, p in seg_wf_oos])},
                    "lockbox_cold": mb,
                    "crown_pool_size": len(((d.get("selection") or {}).get("candidates")) or []),
                }
                # re-tuned folds on the same Stage-A OOS stretch (fold rows from validate.wf_oos)
                wo = v.get("wf_oos") or {}
                folds = wo.get("folds") or []
                f_oos = [f for f in folds if f.get("from") and pd.Timestamp(f["from"], tz=tz) >= ks_ts]
                if f_oos:
                    f0 = min(pd.Timestamp(f["from"], tz=tz) for f in f_oos)
                    fixed_same = [(t, p) for t, p in pairs_a if f0 <= t < opt_to_ts]
                    row["retuned_vs_fixed_on_folds_after_ksplit"] = {
                        "folds_used": [(f["from"], f["to"]) for f in f_oos],
                        "retuned_net": round(sum(float(f["net"]) for f in f_oos), 1),
                        "retuned_trades": int(sum(int(f["trades"]) for f in f_oos)),
                        "retuned_net_per_trade": round(sum(float(f["net"]) for f in f_oos) / max(1, sum(int(f["trades"]) for f in f_oos)), 3),
                        "fixed_same_window": metrics([p for _, p in fixed_same]),
                        "all_folds_retuned_net": round(sum(float(f["net"]) for f in folds), 1),
                        "all_folds_retuned_trades": int(sum(int(f["trades"]) for f in folds)),
                    }
                # bootstrap + contiguous windows
                pw = {}
                for name, pool in (("lens_pool", pool_lens), ("stageA_oos_pool", pool_oos)):
                    if len(pool) < 20:
                        pw[name] = None; continue
                    blk = {}
                    for L in LENGTHS:
                        blk[str(L)] = {"boot": _boot(pool, L, rng), "contiguous": _contig(pool, L)}
                    pw[name] = blk
                row["power"] = pw
                # per-year with corrected flag
                byy = defaultdict(list)
                for t, p in pairs_a:
                    byy[t.year].append(p)
                row["by_year"] = [{"year": y, **metrics(byy[y]),
                                   "stageA_in_sample": (pd.Timestamp(y, 12, 31, tz=tz) < ks_ts),
                                   "before_wf_split": (wf_ts is not None and pd.Timestamp(y, 12, 31, tz=tz) < wf_ts)}
                                  for y in sorted(byy)]
                # recency cost with the true extra windows
                date_to_ts = pd.Timestamp(date_to, tz=tz)
                x12 = [(t, p) for t, p in pairs_a if (lb_ts - pd.DateOffset(months=12)) <= t < lb_ts]
                x24 = [(t, p) for t, p in pairs_a if (date_to_ts - pd.DateOffset(months=24)) <= t < lb_ts]
                row["recency_cost"] = {
                    "true_extra_12mo_before_lockbox": {"from": (lb_ts - pd.DateOffset(months=12)).date().isoformat(), "to": lb_from, **metrics([p for _, p in x12])},
                    "lens_window_date_to_minus_24mo_to_lockbox_start": {"from": (date_to_ts - pd.DateOffset(months=24)).date().isoformat(), "to": lb_from,
                                                                        "months": round((lb_ts - (date_to_ts - pd.DateOffset(months=24))).days / 30.44, 1),
                                                                        **metrics([p for _, p in x24])},
                }
                # cold-start share with a true 12mo and a true 24mo cold window
                for L in (12, 24):
                    cf = (date_to_ts - pd.DateOffset(months=L))
                    arr_c = _slice(full, cf.date().isoformat(), date_to)
                    _, pairs_c = _replay(d, arr_c, champ)
                    warm = [(t, p) for t, p in pairs_a if t >= cf]
                    row.setdefault("cold_start", {})[str(L)] = {
                        "warm_trades": len(warm), "cold_trades": len(pairs_c),
                        "share_lost": (round(1 - len(pairs_c) / len(warm), 3) if warm else None),
                        "warm_net": round(sum(p for _, p in warm), 1), "cold_net": round(sum(p for _, p in pairs_c), 1)}
                log(f"  ok  lb_repro={row['lockbox_reproduction']['ok']} ksplit={row['stageA_split']['ksplit_date']} "
                    f"IS_trades doc={v.get('is_trades')} mine={len(is_pairs)} lens_pool={len(pool_lens)} oos_pool={len(pool_oos)}")
            except Exception as e:
                row["error"] = f"{type(e).__name__}: {e}"; row["traceback"] = traceback.format_exc()
                log("  ERROR", row["error"])
            out.append(row)
    return out


def summarize_b(B):
    ok = [r for r in B if not r.get("error")]
    S = {"n_ok": len(ok), "n_error": len(B) - len(ok),
         "lockbox_repro_ok": sum(1 for r in ok if r["lockbox_reproduction"]["ok"]),
         "ungated_full_ok": sum(1 for r in ok if r["ungated_full_reproduction"]["ok"])}
    S["ksplit_check"] = [{"id": r["id"], "ksplit_date": r["stageA_split"]["ksplit_date"],
                          "doc_is_trades": r["stageA_split"]["validate_is_trades_doc"],
                          "mine_before_ksplit": r["stageA_split"]["champion_trades_before_ksplit"],
                          "n_opt_bars": r["stageA_split"]["n_opt_bars"], "doc_bars": r["stageA_split"]["doc_bars"]} for r in ok]
    S["share_lens_pool_stageA_in_sample"] = {r["id"]: r["pools"]["share_of_lens_pool_that_was_stageA_in_sample"] for r in ok}
    S["median_share_lens_pool_stageA_in_sample"] = med(list(S["share_lens_pool_stageA_in_sample"].values()))
    for name in ("lens_pool", "stageA_oos_pool"):
        for L in LENGTHS:
            bo = [r["power"][name][str(L)]["boot"]["p_net_gt_0"] for r in ok if r["power"].get(name)]
            co = [r["power"][name][str(L)]["contiguous"]["share_pass"] for r in ok if r["power"].get(name) and r["power"][name][str(L)]["contiguous"]]
            S[f"{name}_L{L}"] = {"boot_median": med(bo), "boot_min": (round(min(bo), 3) if bo else None), "n": len(bo),
                                 "contig_median": med(co), "contig_min": (round(min(co), 3) if co else None), "n_contig": len(co)}
    S["crowns"] = {}
    for r in ok:
        if r["crown"]:
            S["crowns"][r["id"]] = {
                "pools": r["pools"], "power": r["power"], "fixed_wf_decomposition": r["fixed_wf_decomposition"],
                "retuned_vs_fixed_after_ksplit": r.get("retuned_vs_fixed_on_folds_after_ksplit"),
                "recency_cost": r["recency_cost"], "cold_start": r["cold_start"]}
    # fixed-WF decomposition across all 20: in-sample part PF vs OOS part PF
    dec = []
    for r in ok:
        f = r["fixed_wf_decomposition"]
        dec.append({"id": r["id"], "crown_pool": f["crown_pool_size"],
                    "pf_wf_all": f["wf_stretch_all"]["pf"], "pf_wf_is_part": f["wf_stretch_stageA_in_sample_part"]["pf"],
                    "pf_wf_oos_part": f["wf_stretch_stageA_oos_part"]["pf"], "pf_lockbox": f["lockbox_cold"]["pf"],
                    "trades_is_part": f["wf_stretch_stageA_in_sample_part"]["trades"], "trades_oos_part": f["wf_stretch_stageA_oos_part"]["trades"]})
    S["fixed_wf_decomposition"] = dec
    S["n_pf_is_part_gt_oos_part"] = sum(1 for x in dec if x["pf_wf_is_part"] and x["pf_wf_oos_part"] and x["pf_wf_is_part"] > x["pf_wf_oos_part"])
    S["n_pf_oos_part_gt_lockbox"] = sum(1 for x in dec if x["pf_wf_oos_part"] and x["pf_lockbox"] and x["pf_wf_oos_part"] > x["pf_lockbox"])
    rv = []
    for r in ok:
        q = r.get("retuned_vs_fixed_on_folds_after_ksplit")
        if q:
            rv.append({"id": r["id"], "crown_pool": r["fixed_wf_decomposition"]["crown_pool_size"],
                       "retuned_npt": q["retuned_net_per_trade"], "fixed_npt": q["fixed_same_window"]["net_per_trade"],
                       "retuned_net": q["retuned_net"], "fixed_net": q["fixed_same_window"]["net"],
                       "retuned_trades": q["retuned_trades"], "fixed_trades": q["fixed_same_window"]["trades"],
                       "fixed_beats_net": q["fixed_same_window"]["net"] > q["retuned_net"]})
    S["retuned_vs_fixed_after_ksplit"] = rv
    S["n_fixed_beats_retuned_net_after_ksplit"] = sum(1 for x in rv if x["fixed_beats_net"])
    S["n_fixed_beats_retuned_net_after_ksplit_single_candidate"] = [(x["id"], x["fixed_beats_net"]) for x in rv if x["crown_pool"] == 1]
    cs12 = [r["cold_start"]["12"]["share_lost"] for r in ok if r["cold_start"]["12"]["share_lost"] is not None and r["id"] != 377]
    cs24 = [r["cold_start"]["24"]["share_lost"] for r in ok if r["cold_start"]["24"]["share_lost"] is not None and r["id"] != 377]
    S["cold_start_true12_median"] = med(cs12); S["cold_start_true24_median"] = med(cs24)
    S["cold_start_rows"] = {r["id"]: r["cold_start"] for r in ok}
    return S


def main():
    no_replay = "--no-replay" in sys.argv
    low_priority()
    lens = json.load(open(LENS_PATH, encoding="utf-8"))
    auxp = json.load(open(AUXP_PATH, encoding="utf-8"))
    auxf = json.load(open(AUXF_PATH, encoding="utf-8"))
    cov = json.load(open(COV_PATH, encoding="utf-8"))
    runs = load_runs()
    log("PART A ...")
    A = part_a(lens, auxp, auxf, cov, runs)
    payload = {"generated_at": _dt.datetime.now(_dt.timezone.utc).isoformat(), "seed": SEED, "part_a": A}
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, default=str)
    log("PART A written")
    if not no_replay:
        setup_data_env()
        B = part_b(lens, runs)
        payload["part_b_runs"] = B
        payload["part_b_summary"] = summarize_b(B)
        with open(OUT_PATH, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, default=str)
        log("PART B written")
    log(f"wrote {OUT_PATH}")


if __name__ == "__main__":
    main()
