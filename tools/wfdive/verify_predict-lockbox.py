"""wfdive VERIFY (adversarial): independent recomputation of the "which pre-lockbox
reading predicts the lockbox" lens (tools/wfdive/lens_predict.py + fold_position_trend.py).

Pure JSON over _wfdive_data/runs.json. Only common.py loaders are imported — none of the
lens's analysis functions. Run from the worktree root:

    python tools/wfdive/verify_predict-lockbox.py

Writes _wfdive_data/verify_predict-lockbox.json.

Field semantics (read from augur_engine, not guessed):
  best_pnl_pts / best_trades / best_pf   Stage-A first-75%-of-bars IS metrics of the CROWNED
                                         config (bestA is reassigned by _select_oos_champion).
  gate_validate.ungated_wf               crowned champion, ONE WARM continuous backtest over
                                         opt_from..date_to, trades entry-sliced to [wf0, wf1)
                                         where wf0 = first ANCHORED fold test start (bar 0.4n)
                                         and wf1 = min(last fold end, lockbox start).
  validate.wf_oos                        PRIMARY-scheme re-tuned folds, each fold's champion
                                         run COLD on its own test slice, stitched.
  selection.candidates[].wf_oos_pnl      each finalist's FIXED params run COLD on the anchored
                                         fold test slices (same slices rolling uses: te_s =
                                         init + f*tsize for both schemes).
  validate.lockbox                       crowned champion run COLD from lb_from (Stage C).
  gate_validate.ungated_lockbox          the same champion's WARM full-window backtest sliced
                                         at lb_start (entry timestamp).
  Stage-A IS = bars [0, 0.75n); WF years = bars [0.4n, n)  ->  58% of the WF span sits
  inside Stage A's own search window.
"""
import collections
import json
import math
import os
import random
import sys
from datetime import date

import numpy as np
from scipy.stats import spearmanr, binomtest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402

SEED = 7
NBOOT = 2000
rng = random.Random(SEED)


# ── helpers ─────────────────────────────────────────────────────────────────
def is_book(d):
    if d.get("book") is not None:
        return True
    s = str(d.get("scope") or "")
    return ("Book" in s) or ("\U0001F4DA" in s)


def f(x):
    try:
        v = float(x)
        return v if math.isfinite(v) else None
    except (TypeError, ValueError):
        return None


def yrs(a, b):
    try:
        d0 = date.fromisoformat(str(a)[:10]); d1 = date.fromisoformat(str(b)[:10])
        y = (d1 - d0).days / 365.25
        return y if y > 0 else None
    except (TypeError, ValueError):
        return None


def newest_key(d):
    try:
        rid = int(d.get("id"))
    except (TypeError, ValueError):
        rid = -1
    return (str(d.get("timestamp") or ""), rid)


def one_per_family(recs, ok):
    best = {}
    for r in recs:
        if not ok(r):
            continue
        k = r["fam"]
        if k not in best or newest_key(r["doc"]) > newest_key(best[k]["doc"]):
            best[k] = r
    return list(best.values())


def median(xs):
    xs = [x for x in xs if x is not None and math.isfinite(x)]
    return float(np.median(xs)) if xs else None


def spear(pairs):
    pairs = [(a, b) for a, b in pairs if a is not None and b is not None]
    if len(pairs) < 4:
        return None
    xs = [p[0] for p in pairs]; ys = [p[1] for p in pairs]
    if len(set(xs)) < 2 or len(set(ys)) < 2:
        return None
    r, _ = spearmanr(xs, ys)
    return float(r) if math.isfinite(r) else None


def cboot(rows, fam_of, stat, nboot=NBOOT):
    """family-clustered bootstrap: resample FAMILIES with replacement."""
    idx = collections.defaultdict(list)
    for i, k in enumerate(fam_of):
        idx[k].append(i)
    fams = list(idx)
    point = stat(rows)
    if point is None or not fams:
        return point, None, None
    out = []
    for _ in range(nboot):
        pick = [rng.choice(fams) for _ in fams]
        s = stat([rows[i] for k in pick for i in idx[k]])
        if s is not None and math.isfinite(s):
            out.append(s)
    if not out:
        return point, None, None
    out.sort()
    return point, out[int(0.05 * len(out))], out[min(len(out) - 1, int(0.95 * len(out)))]


def r3(x):
    return None if x is None else round(float(x), 3)


# ── extraction (my own, not the lens's) ──────────────────────────────────────
def extract(d):
    v = d.get("validate") or {}
    gv = d.get("gate_validate") or {}
    gv = gv if isinstance(gv, dict) else {}
    w = v.get("windows") or {}
    opt = w.get("optimize") or [None, None]
    rec = {"id": d.get("id"), "fam": common.family_key(d), "doc": d, "strategy": d.get("strategy"),
           "verdict": v.get("verdict"), "starred": bool(d.get("starred")),
           "wf_best_mode": v.get("wf_best_mode"), "lockbox_months": w.get("lockbox_months"),
           "opt": opt, "wf_split": w.get("wf_split")}
    opt_y = yrs(opt[0], opt[1]) if opt[0] and opt[1] else None
    # IS (Stage-A first 75% of bars; calendar approx)
    rec["is"] = None
    if f(d.get("best_pnl_pts")) is not None and d.get("best_trades") and opt_y:
        rec["is"] = {"pnl": f(d["best_pnl_pts"]), "n": int(d["best_trades"]), "pf": f(d.get("best_pf")),
                     "years": 0.75 * opt_y}
    # FIXED (warm, crowned, WF calendar range)
    rec["fx"] = None
    uwf = gv.get("ungated_wf")
    wr = gv.get("wf_range")
    if isinstance(uwf, dict):
        y = yrs(wr[0], wr[1]) if (isinstance(wr, list) and len(wr) == 2) else None
        if y is None and w.get("wf_split") and opt[1]:
            y = yrs(w["wf_split"], opt[1])
        if f(uwf.get("total_pnl")) is not None and uwf.get("num_trades") and y:
            rec["fx"] = {"pnl": f(uwf["total_pnl"]), "n": int(uwf["num_trades"]),
                         "pf": f(uwf.get("profit_factor")), "years": y, "range": wr}
    # RE-TUNED (cold per fold, primary scheme)
    rec["rt"] = None
    wo = v.get("wf_oos")
    if isinstance(wo, dict) and f(wo.get("net")) is not None and wo.get("trades") and f(wo.get("years")):
        rec["rt"] = {"pnl": f(wo["net"]), "n": int(wo["trades"]), "pf": f(wo.get("profit_factor")),
                     "years": f(wo["years"]), "mode": wo.get("mode"), "from": wo.get("from"), "to": wo.get("to"),
                     "src": wo.get("src")}
    # LOCKBOX cold (validate.lockbox) and warm (gate_validate.ungated_lockbox)
    rec["lb"] = None
    lb = v.get("lockbox")
    if isinstance(lb, dict):
        y = yrs(lb.get("from"), lb.get("to"))
        if y is None and w.get("lockbox_months"):
            y = float(w["lockbox_months"]) / 12.0
        if f(lb.get("pnl")) is not None and lb.get("trades") and y:
            rec["lb"] = {"pnl": f(lb["pnl"]), "n": int(lb["trades"]), "pf": f(lb.get("pf")), "years": y,
                         "from": lb.get("from"), "to": lb.get("to")}
    rec["lbw"] = None
    ul = gv.get("ungated_lockbox")
    if isinstance(ul, dict) and f(ul.get("total_pnl")) is not None and ul.get("num_trades"):
        y = rec["lb"]["years"] if rec["lb"] else (float(w["lockbox_months"]) / 12.0 if w.get("lockbox_months") else None)
        if y:
            rec["lbw"] = {"pnl": f(ul["total_pnl"]), "n": int(ul["num_trades"]), "pf": f(ul.get("profit_factor")),
                          "years": y}
    # lockbox trade counts even when one side is zero (cold-start detector)
    rec["lb_n_cold"] = int((lb or {}).get("trades") or 0) if isinstance(lb, dict) else None
    rec["lb_n_warm"] = int((ul or {}).get("num_trades") or 0) if isinstance(ul, dict) else None
    # selection
    rec["sel"] = None
    sel = d.get("selection")
    if isinstance(sel, dict):
        cands = [c for c in (sel.get("candidates") or []) if isinstance(c, dict)]
        robust = [c for c in (sel.get("robust") or []) if isinstance(c, dict)]
        def _c(c, crownable):
            lbx = c.get("lockbox")
            return {"params": c.get("params"), "is_pnl": f(c.get("is_pnl")), "wf": f(c.get("wf_oos_pnl")),
                    "crowned": bool(c.get("crowned")), "crownable": crownable,
                    "lb_pnl": (f(lbx.get("total_pnl")) if isinstance(lbx, dict) else None),
                    "lb_n": (int(lbx.get("num_trades") or 0) if isinstance(lbx, dict) else None),
                    "lb_years": (f(lbx.get("years")) if isinstance(lbx, dict) else None),
                    "wf_rng_pnl": (f((c.get("wf_rng") or {}).get("total_pnl")) if isinstance(c.get("wf_rng"), dict) else None)}
        rec["sel"] = {"k": sel.get("k"), "is_max_crowned": sel.get("is_max_crowned"),
                      "cands": [_c(c, True) for c in cands] + [_c(c, False) for c in robust],
                      "n_crown_pool": len(cands), "n_robust": len(robust), "champion": v.get("champion")}
    # folds (primary scheme rows)
    rows = [r for r in (d.get("top10_results") or []) if isinstance(r, dict) and r.get("fold") is not None]
    rec["folds"] = [{"fold": int(r["fold"]), "pf": f(r.get("oos_pf")), "pnl": f(r.get("oos_pnl")),
                     "n": int(r.get("oos_trades") or 0), "train_bars": r.get("train_bars")} for r in rows]
    rec["wf_roll"] = v.get("wf_rolling") if isinstance(v.get("wf_rolling"), dict) else None
    rec["wf_anch"] = v.get("wf_anchored") if isinstance(v.get("wf_anchored"), dict) else None
    rec["has_validate"] = bool(v)
    return rec


def main():
    runs = common.load_runs()
    out = {"seed": SEED, "nboot": NBOOT, "n_runs_total": len(runs)}
    nonbook = [d for d in runs if not is_book(d)]
    books = [d for d in runs if is_book(d)]
    recs = [extract(d) for d in nonbook]
    by = {r["id"]: r for r in recs}
    out["n_books_excluded"] = len(books)
    out["n_non_book"] = len(nonbook)
    withv = [r for r in recs if r["has_validate"]]
    U = [r for r in recs if r["lb"]]  # usable (non-zero-trade, finite) cold lockbox
    out["universe"] = {
        "n_with_validate": len(withv), "n_families_with_validate": len({r["fam"] for r in withv}),
        "n_lockbox_usable": len(U), "n_families_lockbox_usable": len({r["fam"] for r in U}),
        "n_lockbox_zero_trade_excluded": sum(1 for r in withv if isinstance((r["doc"].get("validate") or {}).get("lockbox"), dict) and not r["lb"]),
        "verdicts_in_universe": dict(collections.Counter(str(r["verdict"]) for r in U)),
        "starred_in_universe": [r["id"] for r in U if r["starred"]],
        "book_ids_in_universe": [r["id"] for r in U if is_book(r["doc"])],
        "n_with_fx": sum(1 for r in U if r["fx"]), "n_with_rt": sum(1 for r in U if r["rt"]),
        "n_with_is": sum(1 for r in U if r["is"]), "n_with_lbw": sum(1 for r in U if r["lbw"]),
        "n_all_three_readings": sum(1 for r in U if r["fx"] and r["rt"] and r["is"]),
        "n_families_all_three": len({r["fam"] for r in U if r["fx"] and r["rt"] and r["is"]}),
    }
    # units sanity: best_pnl_usd ~= best_pnl_pts * multiplier
    uchk = []
    for r in U[:400]:
        d = r["doc"]
        if f(d.get("best_pnl_usd")) and f(d.get("best_pnl_pts")) and f(d.get("multiplier")):
            uchk.append(f(d["best_pnl_usd"]) / (f(d["best_pnl_pts"]) * f(d["multiplier"])))
    out["units_check_usd_over_pts_x_mult_median"] = r3(median(uchk))
    # wf_oos mode == primary scheme; backfill reconciliation
    out["wf_oos_mode_equals_wf_best_mode"] = dict(collections.Counter(
        str(r["rt"]["mode"] == r["wf_best_mode"]) for r in recs if r["rt"]))
    bad_bf = 0; n_bf = 0
    for r in recs:
        wo = (r["doc"].get("validate") or {}).get("wf_oos") or {}
        bf = (wo.get("backfill") or {}).get("matches")
        if isinstance(bf, list):
            n_bf += 1
            if any((abs(f(m.get("d_net")) or 0) > 1e-3 or int(m.get("d_trades") or 0) != 0) for m in bf if isinstance(m, dict)):
                bad_bf += 1
    out["wf_oos_backfill"] = {"n_blocks": n_bf, "n_with_any_fold_mismatch": bad_bf}
    # crowned candidate params == validate.champion?
    same = collections.Counter()
    for r in recs:
        s = r["sel"]
        if not s or not s["champion"]:
            continue
        cr = next((c for c in s["cands"] if c["crowned"]), None)
        if cr and cr["params"]:
            same[str(all(cr["params"].get(k) == s["champion"].get(k) for k in s["champion"]))] += 1
    out["crowned_params_equal_validate_champion"] = dict(same)
    # best_pnl_pts == crowned is_pnl
    eq = collections.Counter()
    for r in recs:
        s = r["sel"]; d = r["doc"]
        if not s:
            continue
        cr = next((c for c in s["cands"] if c["crowned"]), None)
        if cr and cr["is_pnl"] is not None and f(d.get("best_pnl_pts")) is not None:
            eq[str(abs(cr["is_pnl"] - f(d["best_pnl_pts"])) < 1.0)] += 1
    out["best_pnl_pts_equals_crowned_is_pnl"] = dict(eq)

    # ══ F1: #335 / #257 illustration + population decomposition of the fixed-vs-retuned gap ══
    def _ill(rid):
        r = by.get(rid)
        if not r:
            return None
        s = r["sel"] or {}
        cr = next((c for c in s.get("cands", []) if c["crowned"]), {})
        return {"strategy": r["strategy"], "wf_best_mode": r["wf_best_mode"],
                "crowned_wf_cold_fixed": cr.get("wf"), "crowned_wf_rng_warm": cr.get("wf_rng_pnl"),
                "ungated_wf_warm_fixed": (r["fx"] or {}).get("pnl"), "ungated_wf_pf": (r["fx"] or {}).get("pf"),
                "ungated_wf_n": (r["fx"] or {}).get("n"), "wf_range": (r["fx"] or {}).get("range"),
                "anchored_oos_net": (r["wf_anch"] or {}).get("oos_net"), "rolling_oos_net": (r["wf_roll"] or {}).get("oos_net"),
                "wf_oos_retuned": r["rt"], "lockbox_cold": r["lb"], "lockbox_warm": r["lbw"],
                "is": r["is"], "opt": r["opt"], "wf_split": r["wf_split"],
                "n_candidates": len(s.get("cands", [])),
                "candidate_wf_scores": sorted([c["wf"] for c in s.get("cands", []) if c["wf"] is not None], reverse=True),
                "candidate_lockboxes_by_wf_rank": [(c["wf"], c["lb_pnl"], c["lb_n"], c["crowned"]) for c in sorted(s.get("cands", []), key=lambda c: -(c["wf"] or 0))]}
    out["f1_illustrations"] = {"335": _ill(335), "257": _ill(257)}
    # IS overlap: Stage-A IS = first 75% of bars, WF = last 60% of bars => overlap 35%/60%
    out["f1_is_overlap_of_wf_span_bars"] = round((0.75 - 0.40) / (1.0 - 0.40), 3)
    # population: same crowned fixed params, cold-per-fold (crowned.wf) vs warm (ungated_wf)
    cs_rows = []; rt_rows = []; rt_cold_rows = []
    for r in U:
        s = r["sel"]
        cr = next((c for c in (s or {}).get("cands", []) if c["crowned"]), None)
        if cr and cr["wf"] and r["fx"] and r["fx"]["pnl"]:
            cs_rows.append({"fam": r["fam"], "id": r["id"], "ratio": cr["wf"] / r["fx"]["pnl"]})
            if r["rt"] and r["rt"]["pnl"] is not None:
                rt_cold_rows.append({"fam": r["fam"], "id": r["id"], "ratio": r["rt"]["pnl"] / cr["wf"],
                                     "n_cands": len(s["cands"])})
        if r["rt"] and r["fx"] and r["fx"]["pnl"]:
            rt_rows.append({"fam": r["fam"], "id": r["id"], "ratio": r["rt"]["pnl"] / r["fx"]["pnl"]})
    def _med_ratio(rows):
        p, lo, hi = cboot(rows, [x["fam"] for x in rows], lambda xs: median([x["ratio"] for x in xs]))
        return {"n_runs": len(rows), "n_families": len({x["fam"] for x in rows}), "median": r3(p), "ci90": [r3(lo), r3(hi)]}
    out["f1_gap_decomposition"] = {
        "cold_per_fold_over_warm_SAME_fixed_params": _med_ratio(cs_rows),
        "retuned_over_warm_fixed": _med_ratio(rt_rows),
        "retuned_over_cold_fixed_APPLES_TO_APPLES": _med_ratio(rt_cold_rows),
        "retuned_over_cold_fixed_single_finalist_only": _med_ratio([x for x in rt_cold_rows if x["n_cands"] == 1]),
        "retuned_over_cold_fixed_ge2_finalists": _med_ratio([x for x in rt_cold_rows if x["n_cands"] >= 2]),
        "retuned_over_cold_fixed_10_finalists": _med_ratio([x for x in rt_cold_rows if x["n_cands"] >= 10]),
    }

    # ══ F2: anchored vs rolling ══
    both = [r for r in recs if r["wf_roll"] and r["wf_anch"] and r["wf_roll"].get("ran") and r["wf_anch"].get("ran")
            and r["wf_roll"].get("n_folds") and r["wf_anch"].get("n_folds")]
    dd = one_per_family(both, lambda r: True)
    a_wins = sum(1 for r in dd if (r["wf_anch"]["oos_net"] or 0) > (r["wf_roll"]["oos_net"] or 0))
    def _tie(r):
        a, ro = (r["wf_anch"]["oos_net"] or 0), (r["wf_roll"]["oos_net"] or 0)
        return abs(a - ro) <= 1e-6 * max(1.0, abs(a), abs(ro))
    ties_dd = sum(1 for r in dd if _tie(r))
    r_wins = len(dd) - a_wins - ties_dd
    pinned_ids = {r["id"] for r in recs if r["sel"] and r["sel"]["n_crown_pool"] == 1}
    tie_pinned = sum(1 for r in dd if _tie(r) and r["id"] in pinned_ids)
    nonpin = [r for r in dd if r["id"] not in pinned_ids and not _tie(r)]
    a_wins_np = sum(1 for r in nonpin if (r["wf_anch"]["oos_net"] or 0) > (r["wf_roll"]["oos_net"] or 0))
    prim_U = collections.Counter(str(r["wf_best_mode"]) for r in U)
    anch_primary_but_lower = sum(1 for r in both if r["wf_best_mode"] == "anchored"
                                 and (r["wf_anch"]["oos_net"] or 0) < (r["wf_roll"]["oos_net"] or 0))
    n_anch_primary = sum(1 for r in both if r["wf_best_mode"] == "anchored")
    # mechanism check: does the engine rule reproduce wf_best_mode?
    rule_ok = collections.Counter()
    for r in both:
        a, ro = r["wf_anch"], r["wf_roll"]
        pred = "anchored" if (a["fold_frac"], a["wfe"]) > (ro["fold_frac"], ro["wfe"]) else "rolling"
        rule_ok[str(pred == r["wf_best_mode"])] += 1
    out["f2_anchored_vs_rolling"] = {
        "n_runs_both_ran": len(both), "n_families": len({r["fam"] for r in both}), "n_dedup": len(dd),
        "anchored_beats_rolling_oos_net_dedup": a_wins, "rolling_beats_anchored_dedup": r_wins,
        "ties_dedup": ties_dd, "ties_that_are_single_finalist_pinned_runs": tie_pinned,
        "non_pinned_non_tie_dedup": {"n": len(nonpin), "anchored_wins": a_wins_np, "rolling_wins": len(nonpin) - a_wins_np},
        "anchored_wins_all_runs": sum(1 for r in both if (r["wf_anch"]["oos_net"] or 0) > (r["wf_roll"]["oos_net"] or 0)),
        "primary_mode_in_lockbox_universe": dict(prim_U),
        "anchored_primary_runs": n_anch_primary, "anchored_primary_but_rolling_scored_higher": anch_primary_but_lower,
        "engine_rule_reproduces_wf_best_mode": dict(rule_ok),
        "note": "rolling and anchored TEST slices are identical (auto.py: te_s = init + f*tsize for both), so this comparison has no era/price-level confound",
    }

    # ══ F3: fold position vs OOS PF ══
    fl = []
    per_run = []
    for r in recs:
        rows = [x for x in r["folds"] if x["n"] and x["pf"] is not None]
        if len(rows) < 3:
            continue
        nmax = max(x["fold"] for x in rows)
        if nmax < 3:
            continue
        for x in rows:
            fl.append({"fam": r["fam"], "id": r["id"], "pos": x["fold"] / nmax, "pf": min(x["pf"], 10.0),
                       "train_bars": x["train_bars"], "mode": r["wf_best_mode"], "strategy": r["strategy"]})
        rho = spear([(x["fold"], min(x["pf"], 10.0)) for x in rows])
        early = [min(x["pf"], 10.0) for x in rows if x["fold"] <= nmax / 2]
        late = [min(x["pf"], 10.0) for x in rows if x["fold"] > nmax / 2]
        per_run.append({"fam": r["fam"], "id": r["id"], "rho": rho, "n_folds": len(rows),
                        "late_minus_early_median_pf": (median(late) - median(early)) if (early and late) else None,
                        "held_early": (sum(1 for p in early if p > 1) / len(early)) if early else None,
                        "held_late": (sum(1 for p in late if p > 1) / len(late)) if late else None,
                        "strategy": r["strategy"], "mode": r["wf_best_mode"]})
    fams = [x["fam"] for x in fl]
    p_pool, lo_pool, hi_pool = cboot(fl, fams, lambda xs: spear([(x["pos"], x["pf"]) for x in xs]))
    p_tb, lo_tb, hi_tb = cboot(fl, fams, lambda xs: spear([(x["train_bars"], x["pf"]) for x in xs if x["train_bars"] is not None]))
    # within-run rho distribution
    pr = [x for x in per_run if x["rho"] is not None]
    p_m, lo_m, hi_m = cboot(pr, [x["fam"] for x in pr], lambda xs: float(np.mean([x["rho"] for x in xs])))
    p_d, lo_d, hi_d = cboot([x for x in per_run if x["late_minus_early_median_pf"] is not None],
                            [x["fam"] for x in per_run if x["late_minus_early_median_pf"] is not None],
                            lambda xs: median([x["late_minus_early_median_pf"] for x in xs]))
    # held-fraction early vs late
    he = [x for x in per_run if x["held_early"] is not None and x["held_late"] is not None]
    p_h, lo_h, hi_h = cboot(he, [x["fam"] for x in he], lambda xs: float(np.mean([x["held_late"] - x["held_early"] for x in xs])))
    # per-family-group pooled rho (rolling-primary train_bars is constant -> the pooled train_bars rho is between-run noise)
    groups = {}
    for g, pref in (("orb", "orb"), ("enguq", "enguq"), ("noise", "noise"), ("ttmsqz", "ttmsqz"), ("ttibs", "ttibs")):
        sub = [x for x in fl if str(x["strategy"] or "").lower().startswith(pref)]
        if len(sub) >= 20:
            p, lo, hi = cboot(sub, [x["fam"] for x in sub], lambda xs: spear([(x["pos"], x["pf"]) for x in xs]))
            groups[g] = {"n_fold_rows": len(sub), "n_runs": len({x["id"] for x in sub}), "n_families": len({x["fam"] for x in sub}),
                         "rho": r3(p), "ci90": [r3(lo), r3(hi)]}
    # single-finalist (pinned search space) runs re-tune NOTHING per fold -> exclude for Q3
    pinned_ids = {r["id"] for r in recs if r["sel"] and r["sel"]["n_crown_pool"] == 1}
    fl_np = [x for x in fl if x["id"] not in pinned_ids]
    p_np, lo_np, hi_np = cboot(fl_np, [x["fam"] for x in fl_np], lambda xs: spear([(x["pos"], x["pf"]) for x in xs]))
    pr_np = [x for x in pr if x["id"] not in pinned_ids]
    p_mnp, lo_mnp, hi_mnp = cboot(pr_np, [x["fam"] for x in pr_np], lambda xs: float(np.mean([x["rho"] for x in xs])))
    groups_np = {}
    for g, pref in (("orb", "orb"), ("enguq", "enguq"), ("noise", "noise"), ("ttmsqz", "ttmsqz")):
        sub = [x for x in fl_np if str(x["strategy"] or "").lower().startswith(pref)]
        if len(sub) >= 20:
            p, lo, hi = cboot(sub, [x["fam"] for x in sub], lambda xs: spear([(x["pos"], x["pf"]) for x in xs]))
            groups_np[g] = {"n_fold_rows": len(sub), "n_runs": len({x["id"] for x in sub}), "n_families": len({x["fam"] for x in sub}),
                            "rho": r3(p), "ci90": [r3(lo), r3(hi)]}
    out["f3_fold_position"] = {
        "n_fold_rows": len(fl), "n_runs": len({x["id"] for x in fl}), "n_families": len({x["fam"] for x in fl}),
        "fold_rows_from_single_finalist_pinned_runs": len(fl) - len(fl_np),
        "runs_single_finalist_pinned": len({x["id"] for x in fl if x["id"] in pinned_ids}),
        "excluding_pinned": {"n_fold_rows": len(fl_np), "n_runs": len({x["id"] for x in fl_np}), "n_families": len({x["fam"] for x in fl_np}),
                             "pooled_spearman_pos_vs_pf": r3(p_np), "ci90": [r3(lo_np), r3(hi_np)],
                             "within_run_rho_mean": r3(p_mnp), "ci90_within": [r3(lo_mnp), r3(hi_mnp)], "n_runs_within": len(pr_np),
                             "by_family_group": groups_np},
        "pooled_spearman_pos_vs_pf": r3(p_pool), "ci90": [r3(lo_pool), r3(hi_pool)],
        "pooled_spearman_trainbars_vs_pf": r3(p_tb), "ci90_trainbars": [r3(lo_tb), r3(hi_tb)],
        "rolling_primary_rows_with_constant_train_bars": sum(1 for x in fl if x["mode"] == "rolling"),
        "within_run_rho_mean": r3(p_m), "within_run_rho_ci90": [r3(lo_m), r3(hi_m)],
        "within_run_rho_median": r3(median([x["rho"] for x in pr])),
        "within_run_share_positive": r3(sum(1 for x in pr if x["rho"] > 0) / len(pr)) if pr else None,
        "n_runs_within": len(pr),
        "late_minus_early_median_pf_median": r3(p_d), "ci90_late_minus_early": [r3(lo_d), r3(hi_d)],
        "held_frac_late_minus_early_mean": r3(p_h), "ci90_held": [r3(lo_h), r3(hi_h)],
        "by_family_group": groups,
    }

    # ══ F4 / F5 / F6: reading -> lockbox (cold AND warm targets, points AND PF) ══
    def reading_rows(key, target):
        rows = []
        for r in U:
            rd = r[key]; lb = r[target]
            if not rd or not lb:
                continue
            rr = rd["pnl"] / rd["years"]; lr = lb["pnl"] / lb["years"]
            rpt = rd["pnl"] / rd["n"]; lpt = lb["pnl"] / lb["n"]
            if rr == 0 or rpt == 0:
                continue
            rows.append({"fam": r["fam"], "id": r["id"], "ratio_rate": lr / rr, "ratio_pt": lpt / rpt,
                         "r_pos": rd["pnl"] > 0, "l_pos": lb["pnl"] > 0,
                         "r_pf": rd.get("pf"), "l_pf": lb.get("pf"),
                         "pf_ratio": ((lb["pf"] / rd["pf"]) if (rd.get("pf") and lb.get("pf") is not None and rd["pf"] > 0) else None),
                         "pf_diff": ((lb["pf"] - rd["pf"]) if (rd.get("pf") is not None and lb.get("pf") is not None) else None)})
        return rows

    def analyse(rows, dedup_recs=None):
        fams = [x["fam"] for x in rows]
        o = {"n_runs": len(rows), "n_families": len(set(fams))}
        for nm, k in (("median_ratio_rate", "ratio_rate"), ("median_ratio_pertrade", "ratio_pt"),
                      ("median_pf_ratio_lb_over_reading", "pf_ratio"), ("median_pf_diff_lb_minus_reading", "pf_diff")):
            p, lo, hi = cboot(rows, fams, lambda xs, k=k: median([x[k] for x in xs]))
            o[nm] = {"point": r3(p), "ci90": [r3(lo), r3(hi)]}
        pf_rows = [x for x in rows if x["r_pf"] is not None and x["l_pf"] is not None]
        p, lo, hi = cboot(pf_rows, [x["fam"] for x in pf_rows], lambda xs: spear([(x["r_pf"], x["l_pf"]) for x in xs]))
        o["spearman_pf_all_runs"] = {"point": r3(p), "ci90": [r3(lo), r3(hi)], "n": len(pf_rows)}
        # one per family (newest)
        best = {}
        for x in pf_rows:
            rec = by[x["id"]]
            if x["fam"] not in best or newest_key(rec["doc"]) > newest_key(by[best[x["fam"]]["id"]]["doc"]):
                best[x["fam"]] = x
        dd = list(best.values())
        o["spearman_pf_one_per_family"] = {"point": r3(spear([(x["r_pf"], x["l_pf"]) for x in dd])), "n": len(dd)}
        for th in (1.0, 1.2, 1.5):
            el = [x for x in pf_rows if x["r_pf"] > th]
            o[f"given_reading_pf_gt_{th}"] = {"n_runs": len(el), "n_families": len({x["fam"] for x in el}),
                                              "pct_lockbox_pf_gt_1": (round(100.0 * sum(1 for x in el if x["l_pf"] > 1) / len(el), 1) if el else None)}
        o["flip_profit_reading_to_loss_lockbox"] = sum(1 for x in rows if x["r_pos"] and not x["l_pos"])
        o["flip_loss_reading_to_profit_lockbox"] = sum(1 for x in rows if (not x["r_pos"]) and x["l_pos"])
        o["n_reading_negative"] = sum(1 for x in rows if not x["r_pos"])
        return o

    out["f4_f5_f6_reading_vs_lockbox"] = {}
    for tgt in ("lb", "lbw"):
        for key in ("fx", "rt", "is"):
            out["f4_f5_f6_reading_vs_lockbox"][f"{key}_vs_{tgt}"] = analyse(reading_rows(key, tgt))
    # SAME-universe comparison (runs carrying all three readings) so n is equal across readings
    same_ids = {r["id"] for r in U if r["fx"] and r["rt"] and r["is"]}
    out["f4_same_universe"] = {}
    for tgt in ("lb", "lbw"):
        for key in ("fx", "rt", "is"):
            rows = [x for x in reading_rows(key, tgt) if x["id"] in same_ids]
            a = analyse(rows)
            out["f4_same_universe"][f"{key}_vs_{tgt}"] = {k: a[k] for k in ("n_runs", "n_families", "median_ratio_rate",
                                                                             "median_pf_ratio_lb_over_reading", "median_pf_diff_lb_minus_reading",
                                                                             "spearman_pf_all_runs", "spearman_pf_one_per_family",
                                                                             "flip_profit_reading_to_loss_lockbox", "flip_loss_reading_to_profit_lockbox")}
    # paired within-run comparison: is |log ratio| smaller for fixed than re-tuned on the SAME runs?
    pair = []
    for r in U:
        if r["fx"] and r["rt"] and r["lb"]:
            fr = r["fx"]["pnl"] / r["fx"]["years"]; tr = r["rt"]["pnl"] / r["rt"]["years"]; lr = r["lb"]["pnl"] / r["lb"]["years"]
            if fr > 0 and tr > 0 and lr > 0:
                pair.append({"fam": r["fam"], "id": r["id"], "d": abs(math.log(lr / fr)) - abs(math.log(lr / tr)),
                             "pf_d": (abs(math.log(r["lb"]["pf"] / r["fx"]["pf"])) - abs(math.log(r["lb"]["pf"] / r["rt"]["pf"]))) if (r["lb"]["pf"] and r["fx"]["pf"] and r["rt"]["pf"]) else None})
    p, lo, hi = cboot(pair, [x["fam"] for x in pair], lambda xs: median([x["d"] for x in xs]))
    p2, lo2, hi2 = cboot([x for x in pair if x["pf_d"] is not None], [x["fam"] for x in pair if x["pf_d"] is not None],
                         lambda xs: median([x["pf_d"] for x in xs]))
    out["f4_paired_abs_log_error_fixed_minus_retuned"] = {
        "n": len(pair), "n_families": len({x["fam"] for x in pair}),
        "rate_median": r3(p), "ci90": [r3(lo), r3(hi)],
        "pf_median": r3(p2), "ci90_pf": [r3(lo2), r3(hi2)],
        "note": "negative = fixed reading closer to lockbox than re-tuned on the same run (all-positive runs only)"}

    # ══ F7: selection haircut: fixed-minus-retuned gap vs lockbox shortfall + permutation null ══
    sel_rows = []
    for r in U:
        s = r["sel"]
        if not s or not s.get("k") or s["k"] < 2:
            continue
        wfs = sorted([c["wf"] for c in s["cands"] if c["crownable"] and c["wf"] is not None])
        if len(wfs) < 2:
            continue
        cr = next((c for c in s["cands"] if c["crowned"]), None)
        if not cr or cr["wf"] is None:
            continue
        row = {"fam": r["fam"], "id": r["id"], "crowned_wf": cr["wf"], "med_fin": float(np.median(wfs)), "max_fin": max(wfs)}
        if r["fx"] and r["rt"] and r["fx"]["pnl"]:
            fr = r["fx"]["pnl"] / r["fx"]["years"]; tr = r["rt"]["pnl"] / r["rt"]["years"]; lr = r["lb"]["pnl"] / r["lb"]["years"]
            row["fixed_rate"] = fr; row["retuned_rate"] = tr; row["lb_rate"] = lr
            row["gap"] = (fr - tr) / abs(fr); row["short"] = (fr - lr) / abs(fr)
        sel_rows.append(row)
    gp = [x for x in sel_rows if "gap" in x]
    p, lo, hi = cboot(gp, [x["fam"] for x in gp], lambda xs: spear([(x["gap"], x["short"]) for x in xs]))
    # permutation null: shuffle the RE-TUNED rate across runs, keep fixed & lockbox paired
    null = []
    trs = [x["retuned_rate"] for x in gp]
    for _ in range(2000):
        perm = trs[:]; rng.shuffle(perm)
        rho = spear([((x["fixed_rate"] - t) / abs(x["fixed_rate"]), x["short"]) for x, t in zip(gp, perm)])
        if rho is not None:
            null.append(rho)
    null.sort()
    # alternative without the shared 'fixed' term: does the WF-score spread among finalists predict lockbox/fixed?
    alt = [x for x in gp if x["med_fin"]]
    p_alt, lo_alt, hi_alt = cboot(alt, [x["fam"] for x in alt],
                                  lambda xs: spear([((x["crowned_wf"] - x["med_fin"]) / abs(x["med_fin"]), x["short"]) for x in xs]))
    # cleaner: gap measured on cold-fixed (crowned.wf) vs cold-retuned (wf_oos.net) — same slices, no cold-start confound
    cc = []
    for r in U:
        s = r["sel"]
        cr = next((c for c in (s or {}).get("cands", []) if c["crowned"]), None)
        if cr and cr["wf"] and r["rt"] and r["fx"] and r["fx"]["pnl"] > 0 and len(s["cands"]) >= 2:
            cc.append({"fam": r["fam"], "id": r["id"], "gap_cold": (cr["wf"] - r["rt"]["pnl"]) / abs(cr["wf"]),
                       "short": (r["fx"]["pnl"] / r["fx"]["years"] - r["lb"]["pnl"] / r["lb"]["years"]) / (r["fx"]["pnl"] / r["fx"]["years"]),
                       "lb_pf_over_fx_pf": (r["lb"]["pf"] / r["fx"]["pf"]) if (r["lb"]["pf"] is not None and r["fx"]["pf"]) else None})
    p_cc, lo_cc, hi_cc = cboot(cc, [x["fam"] for x in cc], lambda xs: spear([(x["gap_cold"], x["short"]) for x in xs]))
    ccp = [x for x in cc if x["lb_pf_over_fx_pf"] is not None]
    p_cp, lo_cp, hi_cp = cboot(ccp, [x["fam"] for x in ccp], lambda xs: spear([(x["gap_cold"], x["lb_pf_over_fx_pf"]) for x in xs]))
    out["f7_selection_haircut"] = {
        "n_runs_k_ge2": len(sel_rows), "n_families": len({x["fam"] for x in sel_rows}),
        "crowned_is_max_finalist": sum(1 for x in sel_rows if x["crowned_wf"] >= x["max_fin"] - 1e-6),
        "median_crowned_minus_median_finalist_frac": r3(median([(x["crowned_wf"] - x["med_fin"]) / abs(x["med_fin"]) for x in sel_rows if x["med_fin"]])),
        "n_pairs_gap_vs_shortfall": len(gp), "n_families_pairs": len({x["fam"] for x in gp}),
        "spearman_gap_vs_shortfall": r3(p), "ci90": [r3(lo), r3(hi)],
        "permutation_null_shuffle_retuned": {"n": len(null), "mean": r3(float(np.mean(null))) if null else None,
                                             "p95": r3(null[int(0.95 * len(null))]) if null else None,
                                             "p99": r3(null[int(0.99 * len(null))]) if null else None,
                                             "p_value_observed_ge": (r3(sum(1 for z in null if z >= p) / len(null)) if (null and p is not None) else None)},
        "alt_finalist_spread_vs_shortfall": {"spearman": r3(p_alt), "ci90": [r3(lo_alt), r3(hi_alt)], "n": len(alt)},
        "gap_on_cold_slices_vs_shortfall": {"spearman": r3(p_cc), "ci90": [r3(lo_cc), r3(hi_cc)], "n": len(cc), "n_families": len({x["fam"] for x in cc})},
        "gap_on_cold_slices_vs_lb_pf_over_fx_pf": {"spearman": r3(p_cp), "ci90": [r3(lo_cp), r3(hi_cp)], "n": len(ccp)},
    }

    # ══ F8: #88b holdout — crowned vs IS-max vs field, on the candidates' own lockbox (no years needed) ══
    ho = []; dropped_years = 0
    within_wf = []; within_is = []
    for r in recs:
        s = r["sel"]
        if not s:
            continue
        cands = [c for c in s["cands"] if c["lb_pnl"] is not None]
        crownable = [c for c in cands if c["crownable"]]
        cr = next((c for c in cands if c["crowned"]), None)
        if cr is None:
            continue
        pool = [c for c in s["cands"] if c["crownable"] and c["is_pnl"] is not None]
        ismax = max(pool, key=lambda c: c["is_pnl"], default=None)
        # within-run rank correlations over the whole scored field (candidates + robust)
        if len(cands) >= 4:
            within_wf.append({"fam": r["fam"], "id": r["id"], "rho": spear([(c["wf"], c["lb_pnl"]) for c in cands if c["wf"] is not None]),
                              "n": len(cands)})
            within_is.append({"fam": r["fam"], "id": r["id"], "rho": spear([(c["is_pnl"], c["lb_pnl"]) for c in cands if c["is_pnl"] is not None]),
                              "n": len(cands)})
        if ismax is None or ismax["params"] == cr["params"]:
            continue
        if ismax["lb_pnl"] is None:
            continue
        if cr["lb_years"] is None or ismax["lb_years"] is None:
            dropped_years += 1
        others = [c for c in cands if c is not cr]
        rank = 1 + sum(1 for c in others if c["lb_pnl"] > cr["lb_pnl"])
        ho.append({"fam": r["fam"], "id": r["id"], "crowned_lb": cr["lb_pnl"], "ismax_lb": ismax["lb_pnl"],
                   "win": cr["lb_pnl"] > ismax["lb_pnl"], "tie": cr["lb_pnl"] == ismax["lb_pnl"],
                   "n_field": len(cands), "rank_in_field": rank, "best_of_field": rank == 1,
                   "flag_is_max_crowned": s.get("is_max_crowned"), "verdict": r["verdict"]})
    hd = one_per_family([{"fam": h["fam"], "id": h["id"], "doc": by[h["id"]]["doc"], "h": h} for h in ho], lambda x: True)
    hd = [x["h"] for x in hd]
    wins = sum(1 for h in hd if h["win"]); ties = sum(1 for h in hd if h["tie"]); losses = len(hd) - wins - ties
    best1 = sum(1 for h in hd if h["best_of_field"])
    chance = float(np.mean([1.0 / h["n_field"] for h in hd])) if hd else None
    ww = [x for x in within_wf if x["rho"] is not None]; wi = [x for x in within_is if x["rho"] is not None]
    p_ww, lo_ww, hi_ww = cboot(ww, [x["fam"] for x in ww], lambda xs: float(np.mean([x["rho"] for x in xs])))
    p_wi, lo_wi, hi_wi = cboot(wi, [x["fam"] for x in wi], lambda xs: float(np.mean([x["rho"] for x in xs])))
    out["f8_88b_holdout"] = {
        "n_runs_all": len(ho), "n_families_all": len({h["fam"] for h in ho}), "n_dedup": len(hd),
        "n_runs_lens_would_drop_for_missing_years": dropped_years,
        "crowned_beats_is_max_on_lockbox": wins, "ties": ties, "losses": losses,
        "binom_two_sided_p_wins_vs_losses": (r3(binomtest(wins, wins + losses, 0.5).pvalue) if (wins + losses) else None),
        "crowned_best_of_field": best1, "chance_baseline_mean_1_over_field": r3(chance),
        "field_size_counts": dict(collections.Counter(h["n_field"] for h in hd)),
        "median_rank_in_field": median([h["rank_in_field"] for h in hd]),
        "flag_is_max_crowned_values": dict(collections.Counter(str(h["flag_is_max_crowned"]) for h in hd)),
        "within_run_spearman_WF_score_vs_lockbox": {"mean": r3(p_ww), "ci90": [r3(lo_ww), r3(hi_ww)], "n_runs": len(ww),
                                                    "n_families": len({x["fam"] for x in ww}),
                                                    "share_positive": r3(sum(1 for x in ww if x["rho"] > 0) / len(ww)) if ww else None},
        "within_run_spearman_IS_pnl_vs_lockbox": {"mean": r3(p_wi), "ci90": [r3(lo_wi), r3(hi_wi)], "n_runs": len(wi),
                                                  "share_positive": r3(sum(1 for x in wi if x["rho"] > 0) / len(wi)) if wi else None},
        "rows_dedup": hd,
    }

    # ══ F9: cold start ══
    flags = {}
    direct = []
    for r in U:
        lb = r["lb"]
        ref = None
        if r["rt"]:
            ref = r["rt"]["n"] / r["rt"]["years"]
        elif r["fx"]:
            ref = r["fx"]["n"] / r["fx"]["years"]
        if ref:
            ratio = (lb["n"] / lb["years"]) / ref
            if ratio < 0.4:
                flags[str(r["id"])] = {"strategy": r["strategy"], "ratio": r3(ratio)}
        if r["lb_n_cold"] is not None and r["lb_n_warm"]:
            direct.append({"id": r["id"], "fam": r["fam"], "strategy": r["strategy"],
                           "cold_n": r["lb_n_cold"], "warm_n": r["lb_n_warm"], "cold_over_warm": r["lb_n_cold"] / r["lb_n_warm"],
                           "cold_pnl": r["lb"]["pnl"], "warm_pnl": (r["lbw"] or {}).get("pnl")})
    d_sorted = sorted(direct, key=lambda x: x["cold_over_warm"])
    out["f9_cold_start"] = {
        "lens_style_ratio_flags_lt_0_4": flags,
        "direct_detector_n_runs_with_both_lockboxes": len(direct),
        "n_cold_lt_90pct_of_warm": sum(1 for x in direct if x["cold_over_warm"] < 0.9),
        "n_cold_lt_70pct_of_warm": sum(1 for x in direct if x["cold_over_warm"] < 0.7),
        "n_families_cold_lt_90pct": len({x["fam"] for x in direct if x["cold_over_warm"] < 0.9}),
        "median_cold_over_warm_trades": r3(median([x["cold_over_warm"] for x in direct])),
        "worst_15": [{k: (r3(v) if isinstance(v, float) else v) for k, v in x.items() if k != "fam"} for x in d_sorted[:15]],
        "nqdip_runs": [{k: (r3(v) if isinstance(v, float) else v) for k, v in x.items() if k != "fam"} for x in direct if "nqdip" in str(x["strategy"]).lower()],
    }

    # ══ F10: lockbox months ══
    out["f10_lockbox_months_non_book_with_validate"] = dict(collections.Counter(str(r["lockbox_months"]) for r in withv))
    out["f10_lockbox_months_in_lockbox_universe"] = dict(collections.Counter(str(r["lockbox_months"]) for r in U))
    # do longer lockboxes look different? (18-24 mo vs 12 mo) — lockbox PF by lockbox_months
    bym = collections.defaultdict(list)
    for r in U:
        if r["lb"]["pf"] is not None:
            bym[str(r["lockbox_months"])].append(r["lb"]["pf"])
    out["f10_lockbox_pf_median_by_months"] = {k: {"n": len(v), "median_pf": r3(median(v)), "share_pf_gt_1": r3(sum(1 for x in v if x > 1) / len(v))} for k, v in bym.items()}

    path = os.path.join(common.DATA_DIR, "verify_predict-lockbox.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(out, fh, default=str, indent=1)
    slim = {k: v for k, v in out.items()}
    slim["f8_88b_holdout"] = {k: v for k, v in out["f8_88b_holdout"].items() if k != "rows_dedup"}
    print(json.dumps(slim, default=str, indent=1))
    print(f"\nsaved -> {path}")


if __name__ == "__main__":
    main()
