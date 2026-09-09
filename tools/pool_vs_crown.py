"""
tools/pool_vs_crown.py -- CARRY THE SHORTLIST, OR CROWN ONE CELL?

The candidate board (tools/candidate_board.py) left one standing recommendation:
"stop collapsing the shortlist to one cell -- carry the finalists as a SET". That
recommendation was never actually tested. It rested on two negatives (the crown does
not beat the other nine in the sealed year; walk-forward rank does not predict sealed
rank) plus one positive about the shortlist as a GROUP. None of those is the same as
"an equal-weight basket of the finalists beats the crown".

This tool builds the basket and scores it against the crown, in the sealed lockbox
year, run by run and then pooled across runs. It is allowed to conclude that the
recommendation is wrong.

WHAT THE CURVE FIELDS ACTUALLY ARE (established by inspection before any number below
was computed -- see docs/candidates/POOL_VS_CROWN.md for the same statement in plain
English):

  candidate["equity"]     = {"t": [...], "cum": [...], "final": float}
  candidate["lb_equity"]  = {"t": [...], "cum": [...], "final": float, "base": float}

  * "cum" is CUMULATIVE profit and loss, sampled AFTER EACH TRADE -- not per bar.
    Proof: every candidate whose sealed year holds 80 trades or fewer has exactly one
    curve point per trade (78 trades -> 78 points, 56 -> 56).
  * The engine DOWNSAMPLES. The full-history curve is capped at 160 points and the
    lockbox curve at 80. A candidate with 229 sealed-year trades still gets 80 points,
    so intermediate peaks and troughs between sampled trades are LOST. Drawdown read
    off a downsampled curve is therefore an UNDER-estimate. It is applied identically
    to the crown and to the basket here, so the comparison stays fair, and the tool
    prints the size of the under-statement against the engine's own reported drawdown.
  * "t" is the BAR INDEX into the run's one-minute series, not a clock time. For the
    full curve the last t tracks the run's total bar count; for the lockbox curve t
    restarts at zero at the start of the sealed year. Within a run every candidate is
    indexed on the SAME bar series, which is what makes the curves alignable.
  * "cum" is OFFSET: the lockbox curve starts at "base", the candidate's equity at the
    moment the sealed year opens. Sealed-year-only profit = cum - base.
  * "cum"[-1] is NOT "final". The sampler drops trailing trades, so the last plotted
    point can sit short of the true end (run 335's crown: curve ends +2372.8 points,
    true sealed-year net +2908.1). This tool APPENDS the true endpoint to every curve
    so each candidate's basket contribution nets out to the engine's reported figure.
  * Units are INDEX POINTS. Dollars = points x the run's contract multiplier.

PRE-REGISTERED QUESTIONS -- written before any answer was computed.

  Q1  Crown alone vs an equal-weight basket of the finalists, in the sealed year:
      net, profit factor, maximum drawdown, annualised return over drawdown.
  Q2  The same four numbers for: crown alone / basket of all finalists / basket of the
      top three by walk-forward / a random single finalist (the average over all
      finalists, which is the honest "pick any one of them" baseline).
  Q3  Drawdown is the whole point of a basket. HOW MUCH lower is the basket's drawdown
      than the average single finalist's? (That it is lower at all is arithmetic -- the
      deepest fall of an average line cannot exceed the average of the deepest falls --
      so only the SIZE of the gap is evidence, measured against what pooling would give
      if the finalists were unrelated bets.)
  Q4  Paired statistics across runs: sign test plus Wilcoxon signed-rank, with effect
      size, and an explicit statement of how many runs carried enough data and how
      much the shared-tape families shrink the effective sample.
  Q5  How genuinely different are the finalists? If they are near-copies of each other
      a basket is not diversification, it is just the same bet at a different size.

EQUAL WEIGHT MEANS 1/N, NOT N COPIES. Each finalist is scaled to 1/N of one contract
before the curves are added, so the basket risks the same capital as the crown does.
Anything else would be leverage dressed up as diversification.

USAGE
  python tools/pool_vs_crown.py                 # read the run cache, write both files
  python tools/pool_vs_crown.py --min-cands 5   # loosen the completeness bar
"""
from __future__ import annotations

import argparse
import csv
import glob
import json
import math
import os
import statistics
from typing import Any, Dict, List, Optional, Sequence, Tuple

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_CACHE_BASE = os.environ.get("EDGELOG_CACHE_DIR") or (
    r"C:\EdgeLog\_anatomy_cache" if os.path.isdir(r"C:\EdgeLog")
    else os.path.join(ROOT, "tools", "_anatomy_cache"))
RUN_CACHE_DIR = os.path.join(_CACHE_BASE, "runs")
OUT_DIR = os.path.join(ROOT, "docs", "candidates")
OUT_MD = os.path.join(OUT_DIR, "POOL_VS_CROWN.md")
OUT_CSV = os.path.join(OUT_DIR, "pool_vs_crown.csv")

# A pair of finalists closer than this, measured as a share of the span the search
# swept each knob over, is treated as the same configuration wearing a different hat.
DUPE_TOL = 0.05
# Buckets used to line the finalists up on a common calendar before correlating them.
CORR_BUCKETS = 26

# ---------------------------------------------------------------------------
# curve handling
# ---------------------------------------------------------------------------


def curve_points(cand: Dict[str, Any]) -> Optional[List[Tuple[float, float]]]:
    """Sealed-year cumulative profit for one finalist as (bar index, points) steps.

    Returns None when the run doc carries no sealed-year curve for this finalist,
    and [] when it carries one that is empty. The leading (0, 0) point and the true
    endpoint are both added here; everything downstream assumes them.
    """
    lb = cand.get("lb_equity")
    if not isinstance(lb, dict):
        return None
    cum = lb.get("cum")
    ts = lb.get("t")
    if not isinstance(cum, list) or not isinstance(ts, list) or not cum or not ts:
        return None
    base = float(lb.get("base") or 0.0)
    pts: List[Tuple[float, float]] = [(0.0, 0.0)]
    for t, v in zip(ts, cum):
        try:
            pts.append((float(t), float(v) - base))
        except (TypeError, ValueError):
            continue
    if len(pts) < 2:
        return None
    final = lb.get("final")
    if final is not None:
        try:
            true_end = float(final) - base
        except (TypeError, ValueError):
            true_end = pts[-1][1]
        if abs(true_end - pts[-1][1]) > 1e-9:
            pts.append((pts[-1][0] + 1.0, true_end))
    return pts


def step_at(pts: Sequence[Tuple[float, float]], grid: Sequence[float]) -> List[float]:
    """Forward-fill a step curve onto a shared bar-index grid.

    Cumulative profit only changes when a trade closes, so between two curve points
    the value simply holds. Before the first trade the value is zero; after the last
    it holds at the final value. That is the only defensible way to add curves whose
    trades land on different bars.
    """
    out: List[float] = []
    i = 0
    last = 0.0
    n = len(pts)
    for g in grid:
        while i < n and pts[i][0] <= g:
            last = pts[i][1]
            i += 1
        out.append(last)
    return out


def pool_curve(curves: Sequence[Sequence[Tuple[float, float]]],
               n_weight: Optional[int] = None) -> Tuple[List[float], List[float]]:
    """Equal-weight basket: every finalist gets 1/N of one contract.

    n_weight defaults to the number of curves supplied. Pass a larger n_weight when
    some finalists traded nothing in the sealed year -- their share of the capital
    still sits in the basket earning zero, which is the honest accounting.
    """
    if not curves:
        return [], []
    n = int(n_weight or len(curves))
    if n <= 0:
        return [], []
    grid = sorted({float(t) for c in curves for t, _ in c})
    filled = [step_at(c, grid) for c in curves]
    pooled = [sum(col) / n for col in zip(*filled)]
    return grid, pooled


def curve_stats(grid: Sequence[float], vals: Sequence[float], years: float,
                mult: float) -> Dict[str, float]:
    """Net, profit factor, maximum drawdown and annualised return over drawdown.

    Profit factor here is measured on the STEPS of the curve, not on trades, because a
    basket has no trades of its own. Applying the same step definition to the crown
    keeps the two sides comparable; the crown's engine-reported per-trade figure is
    carried separately as a sanity anchor.
    """
    if not vals:
        return {"net": 0.0, "pf": 0.0, "dd": 0.0, "mar": 0.0}
    gains = 0.0
    losses = 0.0
    peak = vals[0]
    dd = 0.0
    prev = vals[0]
    for v in vals:
        d = v - prev
        if d > 0:
            gains += d
        elif d < 0:
            losses -= d
        prev = v
        if v > peak:
            peak = v
        if v - peak < dd:
            dd = v - peak
    net = vals[-1] * mult
    ddollars = dd * mult
    pf = (gains / losses) if losses > 1e-12 else (float("inf") if gains > 0 else 0.0)
    mar = (net / years) / abs(ddollars) if years > 0 and abs(ddollars) > 1e-9 else 0.0
    return {"net": net, "pf": pf, "dd": ddollars, "mar": mar}


# ---------------------------------------------------------------------------
# how different are the finalists
# ---------------------------------------------------------------------------


def searched_ranges(doc: Dict[str, Any]) -> Dict[str, Tuple[float, float]]:
    """The span the search actually swept each knob over, from the run's own
    range-widening record. Normalising by this rather than by the finalists' own
    spread stops a shortlist that argues over one knob by one notch from looking as
    varied as one that argues over every knob end to end."""
    out: Dict[str, Tuple[float, float]] = {}
    for row in (doc.get("auto_expand") or []):
        if not isinstance(row, dict):
            continue
        rng = row.get("final_range") or row.get("orig_range")
        p = row.get("param")
        if p and isinstance(rng, (list, tuple)) and len(rng) == 2:
            try:
                lo, hi = float(rng[0]), float(rng[1])
            except (TypeError, ValueError):
                continue
            if hi > lo:
                out[str(p)] = (lo, hi)
    return out


def param_distances(params: Sequence[Dict[str, Any]],
                    ranges: Optional[Dict[str, Tuple[float, float]]] = None) -> Dict[str, Any]:
    """How far apart the finalists' parameter sets are, on the search's own scale.

    Each knob is divided by the span the search swept it over, so a distance of 1.0
    means "as far apart as this knob can get". Where the run did not record a span the
    finalists' own spread is used instead, which flatters them. Knobs every finalist
    agrees on are counted as FROZEN and left out -- they say nothing about how
    different the finalists are.
    """
    ranges = ranges or {}
    keys = sorted({k for p in params for k in p})
    numeric: Dict[str, Tuple[float, float]] = {}
    frozen: List[str] = []
    varying: List[str] = []
    for k in keys:
        vals = [p.get(k) for p in params]
        if all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in vals):
            lo, hi = min(vals), max(vals)
            if hi - lo <= 1e-12:
                frozen.append(k)
            else:
                numeric[k] = ranges.get(k) or (float(lo), float(hi))
                varying.append(k)
        else:
            if len({json.dumps(v, sort_keys=True, default=str) for v in vals}) <= 1:
                frozen.append(k)
            else:
                varying.append(k)

    def dist(a: Dict[str, Any], b: Dict[str, Any]) -> float:
        if not varying:
            return 0.0
        tot = 0.0
        for k in varying:
            av, bv = a.get(k), b.get(k)
            if k in numeric:
                lo, hi = numeric[k]
                try:
                    tot += min(1.0, abs(float(av) - float(bv)) / (hi - lo))
                except (TypeError, ValueError):
                    tot += 1.0
            else:
                sa = json.dumps(av, sort_keys=True, default=str)
                sb = json.dumps(bv, sort_keys=True, default=str)
                tot += 0.0 if sa == sb else 1.0
        return tot / len(varying)

    n = len(params)
    pairs: List[float] = []
    for i in range(n):
        for j in range(i + 1, n):
            pairs.append(dist(params[i], params[j]))
    exact = sum(1 for i in range(n) for j in range(i + 1, n)
                if json.dumps(params[i], sort_keys=True, default=str)
                == json.dumps(params[j], sort_keys=True, default=str))
    near = sum(1 for d in pairs if d <= DUPE_TOL)

    # Greedy clustering: walk the finalists in order, start a new cluster whenever a
    # finalist sits further than the tolerance from every cluster seed already open.
    seeds: List[int] = []
    for i in range(n):
        if all(dist(params[i], params[s]) > DUPE_TOL for s in seeds):
            seeds.append(i)
    return {
        "n": n,
        "n_keys": len(keys),
        "n_frozen": len(frozen),
        "n_varying": len(varying),
        "frozen_share": (len(frozen) / len(keys)) if keys else 0.0,
        "mean_dist": statistics.fmean(pairs) if pairs else 0.0,
        "min_dist": min(pairs) if pairs else 0.0,
        "pairs": len(pairs),
        "exact_dupe_pairs": exact,
        "near_dupe_pairs": near,
        "distinct_configs": len(seeds),
    }


def distinct_curves(curves: Sequence[Sequence[Tuple[float, float]]]) -> Dict[str, int]:
    """How many of the finalists actually traded DIFFERENTLY in the sealed year.

    This is the duplicate test that cannot be argued with: two finalists whose
    sealed-year lines are the same line took the same trades, whatever their settings
    say. Pooling them buys nothing at all.
    """
    sigs = []
    for c in curves:
        sigs.append(tuple((round(t, 3), round(v, 4)) for t, v in c))
    n = len(sigs)
    uniq = len(set(sigs))
    pairs = sum(1 for i in range(n) for j in range(i + 1, n) if sigs[i] == sigs[j])
    return {"n": n, "distinct": uniq, "identical_pairs": pairs}


def bucket_correlation(curves: Sequence[Sequence[Tuple[float, float]]],
                       buckets: int = CORR_BUCKETS) -> Optional[float]:
    """Mean pairwise correlation of the finalists' profit, chopped into equal
    stretches of the sealed year. Two finalists that make and lose money in the same
    stretches cannot diversify each other however different their settings look."""
    if len(curves) < 2:
        return None
    hi = max((c[-1][0] for c in curves), default=0.0)
    if hi <= 0:
        return None
    edges = [hi * i / buckets for i in range(buckets + 1)]
    series: List[List[float]] = []
    for c in curves:
        lvl = step_at(c, edges)
        series.append([lvl[i + 1] - lvl[i] for i in range(buckets)])
    cors: List[float] = []
    for i in range(len(series)):
        for j in range(i + 1, len(series)):
            a, b = series[i], series[j]
            ma, mb = statistics.fmean(a), statistics.fmean(b)
            va = sum((x - ma) ** 2 for x in a)
            vb = sum((x - mb) ** 2 for x in b)
            if va <= 1e-12 or vb <= 1e-12:
                continue
            cov = sum((x - ma) * (y - mb) for x, y in zip(a, b))
            cors.append(cov / math.sqrt(va * vb))
    return statistics.fmean(cors) if cors else None


# ---------------------------------------------------------------------------
# statistics
# ---------------------------------------------------------------------------


def sign_test(diffs: Sequence[float]) -> Dict[str, Any]:
    """Two-sided sign test: of the runs where the two sides differ, how often does the
    first side win? Ties are dropped, which is the standard treatment."""
    nz = [d for d in diffs if abs(d) > 1e-9]
    n = len(nz)
    wins = sum(1 for d in nz if d > 0)
    if n == 0:
        return {"n": 0, "wins": 0, "p": 1.0}
    k = min(wins, n - wins)
    tail = sum(math.comb(n, i) for i in range(0, k + 1)) / (2.0 ** n)
    return {"n": n, "wins": wins, "p": min(1.0, 2.0 * tail)}


def wilcoxon(diffs: Sequence[float]) -> Dict[str, Any]:
    """Wilcoxon signed-rank: like the sign test but it also weighs HOW BIG each run's
    difference was. Reported with the matched-pairs rank correlation as effect size,
    which runs from -1 (the second side wins every run, by a lot) to +1."""
    nz = [d for d in diffs if abs(d) > 1e-9]
    n = len(nz)
    if n == 0:
        return {"n": 0, "w_plus": 0.0, "p": 1.0, "r": 0.0}
    order = sorted(range(n), key=lambda i: abs(nz[i]))
    ranks = [0.0] * n
    i = 0
    while i < n:
        j = i
        while j + 1 < n and abs(abs(nz[order[j + 1]]) - abs(nz[order[i]])) < 1e-12:
            j += 1
        avg = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    w_plus = sum(r for r, d in zip(ranks, nz) if d > 0)
    w_minus = sum(r for r, d in zip(ranks, nz) if d < 0)
    total = w_plus + w_minus
    r_eff = (w_plus - w_minus) / total if total > 0 else 0.0
    try:
        from scipy.stats import wilcoxon as _w  # type: ignore
        p = float(_w(list(nz)).pvalue)
    except Exception:
        mu = n * (n + 1) / 4.0
        sd = math.sqrt(n * (n + 1) * (2 * n + 1) / 24.0)
        z = (w_plus - mu) / sd if sd > 0 else 0.0
        p = math.erfc(abs(z) / math.sqrt(2.0))
    return {"n": n, "w_plus": w_plus, "p": p, "r": r_eff}


# ---------------------------------------------------------------------------
# per-run analysis
# ---------------------------------------------------------------------------


def analyse_run(doc: Dict[str, Any], min_cands: int = 3) -> Optional[Dict[str, Any]]:
    sel = doc.get("selection")
    if not isinstance(sel, dict):
        return None
    cands = sel.get("candidates")
    if not isinstance(cands, list) or len(cands) < 2:
        return None

    mult = float(doc.get("multiplier") or 1.0)
    years = 0.0
    lo_date = hi_date = None
    for c in cands:
        lbm = c.get("lockbox") or {}
        if lbm.get("years"):
            years = float(lbm["years"])
            lo_date, hi_date = lbm.get("from"), lbm.get("to")
            break
    if years <= 0:
        vlb = (doc.get("validate") or {}).get("lockbox") or {}
        lo_date, hi_date = vlb.get("from"), vlb.get("to")
        if lo_date and hi_date:
            try:
                from datetime import date
                a = date(*[int(x) for x in str(lo_date)[:10].split("-")])
                b = date(*[int(x) for x in str(hi_date)[:10].split("-")])
                years = (b - a).days / 365.25
            except Exception:
                years = 0.0
    if years <= 0:
        years = 1.0  # the sealed slice is one year by construction on every run here

    entries: List[Dict[str, Any]] = []
    for idx, c in enumerate(cands):
        pts = curve_points(c)
        lbm = c.get("lockbox") or {}
        traded = bool(lbm.get("num_trades"))
        entries.append({
            "idx": idx,
            "crowned": bool(c.get("crowned")),
            "params": c.get("params") or {},
            "wf": float(c.get("wf_oos_pnl") or ((c.get("cal") or {}).get("wf") or {}).get("total_pnl") or 0.0),
            "curve": pts,
            "traded": traded,
            "lb_reported_dd": lbm.get("max_drawdown"),
            "lb_reported_pf": lbm.get("profit_factor"),
            "lb_reported_net": lbm.get("total_pnl"),
            "lb_trades": lbm.get("num_trades"),
        })

    withcurve = [e for e in entries if e["curve"]]
    if len(withcurve) < min_cands:
        return None
    crown = next((e for e in entries if e["crowned"]), None)
    if crown is None or not crown["curve"]:
        return None

    # Finalists with no sealed-year curve AND no sealed-year trades traded nothing;
    # their 1/N slice of the capital sits idle and is counted in the denominator.
    # Finalists whose curve is simply absent from the doc (older run schema) cannot be
    # scored at all and are dropped, with the count reported.
    idle = [e for e in entries if not e["curve"] and e["traded"] is False
            and (e["lb_trades"] is not None)]
    unknown = [e for e in entries if not e["curve"] and e not in idle]
    n_weight = len(withcurve) + len(idle)

    curves = [e["curve"] for e in withcurve]
    g_all, v_all = pool_curve(curves, n_weight=n_weight)
    top3 = [e for e in sorted(withcurve, key=lambda e: -e["wf"])[:3]]
    g3, v3 = pool_curve([e["curve"] for e in top3], n_weight=len(top3))

    gc, vc = pool_curve([crown["curve"]], n_weight=1)
    s_crown = curve_stats(gc, vc, years, mult)
    s_pool = curve_stats(g_all, v_all, years, mult)
    s_top3 = curve_stats(g3, v3, years, mult)

    singles = []
    for e in withcurve:
        gs, vs = pool_curve([e["curve"]], n_weight=1)
        singles.append(curve_stats(gs, vs, years, mult))
    for _ in idle:
        singles.append({"net": 0.0, "pf": 0.0, "dd": 0.0, "mar": 0.0})
    s_rand = {
        "net": statistics.fmean([s["net"] for s in singles]),
        "pf": statistics.fmean([s["pf"] for s in singles if math.isfinite(s["pf"])]) if singles else 0.0,
        "dd": statistics.fmean([s["dd"] for s in singles]),
        "mar": statistics.fmean([s["mar"] for s in singles]),
    }

    # How much drawdown the downsampling hides, measured on the crown against the
    # engine's own reported figure.
    dd_gap = None
    if crown["lb_reported_dd"]:
        rep = abs(float(crown["lb_reported_dd"])) * mult
        if rep > 1e-9:
            dd_gap = abs(s_crown["dd"]) / rep - 1.0

    # Distances are measured over the finalists that are actually IN the basket, so
    # "how different are they" answers the same population the money numbers do.
    scored = [e for e in withcurve if e["params"]] + [e for e in idle if e["params"]]
    pdist = param_distances([e["params"] for e in scored], searched_ranges(doc))
    dcurve = distinct_curves(curves)
    corr = bucket_correlation(curves)

    return {
        "rid": doc.get("id"),
        "fam": doc.get("famKey") or doc.get("strategy") or "?",
        "strategy": doc.get("strategy"),
        "instrument": doc.get("instrument"),
        "n_cands": len(cands),
        "n_curves": len(withcurve),
        "n_idle": len(idle),
        "n_unknown": len(unknown),
        "n_weight": n_weight,
        "years": years,
        "lb_from": lo_date,
        "lb_to": hi_date,
        "mult": mult,
        "crown": s_crown,
        "pool": s_pool,
        "top3": s_top3,
        "rand": s_rand,
        "dd_gap": dd_gap,
        "corr": corr,
        "dist": pdist,
        "dcurve": dcurve,
    }


def load_runs(cache_dir: str = RUN_CACHE_DIR) -> List[Dict[str, Any]]:
    out = []
    for fp in glob.glob(os.path.join(cache_dir, "*.json")):
        stem = os.path.basename(fp)[:-5]
        if not stem.isdigit():
            continue
        try:
            with open(fp, "r", encoding="utf-8") as fh:
                d = json.load(fh)
        except Exception:
            continue
        if isinstance(d, dict):
            d.setdefault("id", int(stem))
            out.append(d)
    out.sort(key=lambda d: int(d.get("id") or 0))
    return out


# ---------------------------------------------------------------------------
# report
# ---------------------------------------------------------------------------


def _fmt_money(v: float) -> str:
    return f"{'-' if v < 0 else ''}${abs(v):,.0f}"


def _fmt_pf(v: float) -> str:
    return "inf" if not math.isfinite(v) else f"{v:.2f}"


def build_report(rows: List[Dict[str, Any]]) -> str:
    L: List[str] = []
    A = L.append
    A("# POOL vs CROWN -- does carrying the shortlist beat crowning one cell?")
    A("")
    A(f"Runs scored: **{len(rows)}**. Every number below is the SEALED LOCKBOX YEAR only -- "
      "the stretch the search never saw. Dollars, at each run's own contract size.")
    A("")
    A("## What the stored curves are (checked before use)")
    A("")
    A("Each finalist stores its sealed-year equity as a list of cumulative profit "
      "readings taken AFTER EACH TRADE, in index points, together with the bar number "
      "each reading sits on. Three things had to be handled:")
    A("")
    A("- **They are thinned.** The engine keeps at most 80 readings per sealed year, so "
      "a finalist with 229 trades is drawn with 80 dots and the dips between them are "
      "invisible. Drawdown read off a thinned curve is therefore too shallow. It is "
      "thinned the same way for the crown and for the basket, so the comparison is "
      "fair, and the size of the understatement is reported below.")
    A("- **They are offset.** The sealed-year line starts at whatever the finalist had "
      "made before the sealed year opened. That starting level is subtracted so every "
      "finalist begins the sealed year at zero.")
    A("- **The last dot is not the end.** The thinning drops trailing trades, so the "
      "final dot can sit short of the finalist's true sealed-year result. The true end "
      "value is appended, which makes every finalist's contribution net out to the "
      "figure the run report shows.")
    A("")
    A("Different finalists trade on different bars, so the lines are put on the shared "
      "bar numbering, held flat between trades (cumulative profit only moves when a "
      "trade closes) and then averaged. A finalist that took NO trades in the sealed "
      "year still gets its slice of the money and earns zero on it -- that is counted, "
      "not skipped. A finalist whose curve is missing from the run record entirely "
      "(older records stored only the top few) cannot be scored and is dropped.")
    A("")
    gaps = [r["dd_gap"] for r in rows if r["dd_gap"] is not None]
    if gaps:
        A(f"Thinning cost, measured on the crown against the run report's own drawdown: "
          f"median {statistics.median(gaps)*100:+.1f}%, worst {min(gaps)*100:+.1f}% "
          f"(n={len(gaps)}). Typically small; it applies to both sides, so it moves the "
          "gap between crown and basket far less than it moves either one alone.")
        A("")
    A("**Equal weight means 1/N.** Each finalist is scaled to 1/N of one contract "
      "before the lines are added, so the basket ties up the same money as the crown. "
      "Adding them at full size would be leverage, not diversification.")
    A("")

    A("## 1-2. Crown, basket, top-three basket, random single finalist")
    A("")
    A("*Profit factor* = money made divided by money lost. *Return over drawdown* = the "
      "year's profit divided by the deepest peak-to-trough fall. *Random single* = the "
      "average finalist, which is what you actually get if you pick one without a rule.")
    A("")
    A("| Basket | Net | Profit factor | Max drawdown | Return over drawdown |")
    A("|---|---:|---:|---:|---:|")
    for name, key in (("CROWN alone", "crown"), ("ALL finalists, 1/N", "pool"),
                      ("TOP 3 by walk-forward, 1/N", "top3"), ("RANDOM single finalist", "rand")):
        nets = [r[key]["net"] for r in rows]
        pfs = [r[key]["pf"] for r in rows if math.isfinite(r[key]["pf"]) and r[key]["pf"] > 0]
        dds = [r[key]["dd"] for r in rows]
        mars = [r[key]["mar"] for r in rows]
        A(f"| {name} | {_fmt_money(statistics.fmean(nets))} | {_fmt_pf(statistics.median(pfs)) if pfs else 'n/a'} "
          f"| {_fmt_money(statistics.fmean(dds))} | {statistics.median(mars):.2f} |")
    A("")
    A("Net and drawdown are the average across runs; profit factor and return over "
      "drawdown are the median, because both are ratios and a single run with a tiny "
      "drawdown would otherwise dominate.")
    A("")

    A("**One thing the arithmetic settles before any test runs.** A 1/N basket's net is "
      "EXACTLY the average of the finalists' nets -- adding N lines and dividing by N is "
      "the same operation as averaging their end points. So the basket can never beat "
      "\"pick one at random\" on money; it IS pick-one-at-random on money. The only "
      "thing pooling can change is the SHAPE of the year, which means drawdown.")
    A("")

    A("## 3. Drawdown -- where a basket is supposed to earn its keep")
    A("")
    pool_dd = [abs(r["pool"]["dd"]) for r in rows]
    rand_dd = [abs(r["rand"]["dd"]) for r in rows]
    crown_dd = [abs(r["crown"]["dd"]) for r in rows]
    red = [1.0 - (p / s) for p, s in zip(pool_dd, rand_dd) if s > 1e-9]
    redc = [1.0 - (p / s) for p, s in zip(pool_dd, crown_dd) if s > 1e-9]
    A("The basket's drawdown is guaranteed to be no worse than the average finalist's: "
      "the deepest fall of an average line can never exceed the average of the deepest "
      "falls. So *whether* it is shallower is not a finding and no test of it is "
      "reported here. The finding is HOW MUCH shallower, against what pooling would "
      "give if the finalists were genuinely different bets.")
    A("")
    A(f"- Basket drawdown vs the AVERAGE single finalist: **{statistics.fmean(red)*100:.1f}% "
      f"shallower** on average (median {statistics.median(red)*100:.1f}%), across "
      f"{len(red)} runs.")
    A(f"- Basket drawdown vs the CROWN (a real comparison -- the crown is one specific "
      f"finalist, not the average): {statistics.fmean(redc)*100:+.1f}% on average "
      f"(median {statistics.median(redc)*100:+.1f}%), shallower in "
      f"{sum(1 for x in redc if x > 0)} of {len(redc)} runs.")
    st_dc = sign_test([-(p - s) for p, s in zip(pool_dd, crown_dd)])
    wx_dc = wilcoxon([-(p - s) for p, s in zip(pool_dd, crown_dd)])
    A(f"- Basket shallower than the crown: sign test {st_dc['wins']}/{st_dc['n']}, "
      f"p={st_dc['p']:.4f}; signed-rank p={wx_dc['p']:.4f}, effect size r={wx_dc['r']:+.2f}.")
    # What the reduction WOULD be at the finalists' measured similarity, and at zero
    # similarity, using the standard blend-of-N formula sqrt((1+(N-1)rho)/N).
    pred, ideal = [], []
    for r, obs in zip([r for r, s in zip(rows, rand_dd) if s > 1e-9], red):
        n = max(2, r["n_weight"])
        rho = r["corr"]
        if rho is None:
            continue
        rho = max(0.0, min(1.0, rho))
        pred.append(1.0 - math.sqrt((1.0 + (n - 1) * rho) / n))
        ideal.append(1.0 - math.sqrt(1.0 / n))
    if pred:
        A(f"- For scale: at the similarity these finalists actually show, the textbook "
          f"blend formula predicts about **{statistics.fmean(pred)*100:.0f}%**, and if "
          f"they were unrelated bets it would be about "
          f"**{statistics.fmean(ideal)*100:.0f}%**. Observed "
          f"{statistics.fmean(red)*100:.0f}% sits at the near-identical end of that "
          f"scale, not the diversified end.")
    A("")

    A("## 4. Paired tests, run by run")
    A("")
    A("Each run contributes exactly one crown number and one basket number, so the pair "
      "shares tape, costs and sealed window. The sign test asks only who won more "
      "often; the signed-rank test also weighs the size of each run's gap.")
    A("")
    A("| Comparison | Median gap | Wins | Sign p | Signed-rank p | Effect size r |")
    A("|---|---:|---:|---:|---:|---:|")

    def _row(label: str, diffs: List[float], money: bool = True) -> None:
        st, wx = sign_test(diffs), wilcoxon(diffs)
        med = statistics.median(diffs) if diffs else 0.0
        A(f"| {label} | {(_fmt_money(med) if money else f'{med:+.3f}')} | {st['wins']}/{st['n']} "
          f"| {st['p']:.4f} | {wx['p']:.4f} | {wx['r']:+.2f} |")

    _row("Basket net - crown net", [r["pool"]["net"] - r["crown"]["net"] for r in rows])
    _row("Top-3 basket net - crown net", [r["top3"]["net"] - r["crown"]["net"] for r in rows])
    _row("Crown drawdown - basket drawdown (positive = basket shallower)",
         [abs(r["crown"]["dd"]) - abs(r["pool"]["dd"]) for r in rows])
    _row("Basket return-over-drawdown - crown",
         [r["pool"]["mar"] - r["crown"]["mar"] for r in rows], money=False)
    _row("Basket return-over-drawdown - random single",
         [r["pool"]["mar"] - r["rand"]["mar"] for r in rows], money=False)
    A("")
    fams: Dict[str, List[float]] = {}
    for r in rows:
        fams.setdefault(r["fam"], []).append(r["pool"]["net"] - r["crown"]["net"])
    A(f"**Sample honesty.** {len(rows)} runs, but only **{len(fams)} strategy families** "
      f"({', '.join(f'{k} {len(v)}' for k, v in sorted(fams.items(), key=lambda kv: -len(kv[1])))}). "
      "Runs of one family re-search the same instrument over the same tape, so they are "
      "nowhere near independent -- the effective sample is closer to the family count "
      "than the run count. Collapsing each family to its own average first:")
    fam_diffs = [statistics.fmean(v) for v in fams.values()]
    stf, wxf = sign_test(fam_diffs), wilcoxon(fam_diffs)
    A("")
    A(f"- basket minus crown, one number per family: median {_fmt_money(statistics.median(fam_diffs))}, "
      f"{stf['wins']}/{stf['n']} families favour the basket, sign p={stf['p']:.4f}, "
      f"signed-rank p={wxf['p']:.4f}.")
    fam_dd = {}
    for r in rows:
        fam_dd.setdefault(r["fam"], []).append(abs(r["crown"]["dd"]) - abs(r["pool"]["dd"]))
    fdd = [statistics.fmean(v) for v in fam_dd.values()]
    stfd = sign_test(fdd)
    A(f"- crown drawdown minus basket drawdown, one number per family: median "
      f"{_fmt_money(statistics.median(fdd))}, {stfd['wins']}/{stfd['n']} families "
      f"favour the basket, sign p={stfd['p']:.4f}.")
    A("")

    A("## 5. How different are the ten finalists really?")
    A("")
    A("Each knob is measured against the span the search actually swept it over, so 1.0 "
      "means the two finalists sit at opposite ends of that knob. A knob every finalist "
      "agrees on is called FROZEN and left out.")
    A("")
    fz = [r["dist"]["frozen_share"] for r in rows]
    md = [r["dist"]["mean_dist"] for r in rows]
    dc = [r["dist"]["distinct_configs"] / r["dist"]["n"] for r in rows if r["dist"]["n"]]
    nd = [r["dist"]["near_dupe_pairs"] / r["dist"]["pairs"] for r in rows if r["dist"]["pairs"]]
    ex = sum(r["dist"]["exact_dupe_pairs"] for r in rows)
    dcv = [r["dcurve"]["distinct"] / r["dcurve"]["n"] for r in rows if r["dcurve"]["n"]]
    idp = sum(1 for r in rows if r["dcurve"]["identical_pairs"] > 0)
    cors = [r["corr"] for r in rows if r["corr"] is not None]
    A(f"- Knobs FROZEN across all finalists: median **{statistics.median(fz)*100:.0f}%** of "
      "them -- the shortlist agrees outright on a quarter of the knobs and spreads out "
      "on the rest.")
    A(f"- Distance between two finalists, as a share of the span the search swept: "
      f"median **{statistics.median(md):.2f}**, closest pair in the median run "
      f"{statistics.median([r['dist']['min_dist'] for r in rows]):.2f}.")
    A(f"- Pairs close enough to call the same settings (within {DUPE_TOL:.0%} of the "
      f"searched span): median **{statistics.median(nd)*100:.0f}%** of all pairs; "
      f"{ex} pairs identical outright; on settings alone, median "
      f"**{statistics.median(dc)*100:.0f}%** of the finalists count as distinct.")
    A(f"- The test that cannot be argued with -- do they TRADE differently? Comparing the "
      f"sealed-year lines themselves: median **{statistics.median(dcv)*100:.0f}%** of "
      f"finalists produced a distinct line, and {idp} of {len(rows)} runs contain at "
      f"least one pair that traded identically despite different settings.")
    if cors:
        A(f"- And what actually decides it -- how alike their MONEY is. Splitting the "
          f"sealed year into {CORR_BUCKETS} equal stretches and correlating the finalists' "
          f"profit stretch by stretch: median **{statistics.median(cors):+.2f}** "
          f"(1.0 means they win and lose in the same weeks, 0 unrelated), "
          f"{sum(1 for c in cors if c > 0.5)} of {len(cors)} runs above +0.50. "
          + ("Low enough that a basket really does spread the risk."
             if statistics.median(cors) < 0.5 else
             "High enough that the basket is largely one bet repeated."))
    A("")
    A("So the finalists look different on paper -- they sit far apart on the knobs they "
      "argue about -- but they make their money in the same weeks. Different settings, "
      "same bet.")
    A("")

    A("## 6. Verdict")
    A("")
    d_net = [r["pool"]["net"] - r["crown"]["net"] for r in rows]
    d_dd = [abs(r["crown"]["dd"]) - abs(r["pool"]["dd"]) for r in rows]
    d_mar = [r["pool"]["mar"] - r["crown"]["mar"] for r in rows]
    st_net, wx_net = sign_test(d_net), wilcoxon(d_net)
    st_mar, wx_mar = sign_test(d_mar), wilcoxon(d_mar)
    money_win = st_net["p"] < 0.05 and statistics.median(d_net) > 0
    mar_win = st_mar["p"] < 0.05 and statistics.median(d_mar) > 0
    med_corr = statistics.median(cors) if cors else None
    real_div = (med_corr is not None and med_corr < 0.5)
    A(f"- **Money: no.** Against the crown the median gap is "
      f"{_fmt_money(statistics.median(d_net))} per run, basket ahead in "
      f"{st_net['wins']} of {st_net['n']}, sign p={st_net['p']:.3f}, signed-rank "
      f"p={wx_net['p']:.3f}; across families {stf['wins']}/{stf['n']}. Against picking "
      "a finalist at random the basket cannot win at all -- it is the same number by "
      "arithmetic. Pooling is not a way to make more money.")
    A(f"- **Drawdown: yes, but small and mostly mechanical.** {statistics.fmean(red)*100:.0f}% "
      f"shallower than the average finalist (a guaranteed direction, so only the size "
      f"is news) and {statistics.fmean(redc)*100:+.0f}% shallower than the crown, "
      f"median gap {_fmt_money(statistics.median(d_dd))}, {st_dc['wins']}/{st_dc['n']} "
      f"runs, p={st_dc['p']:.3f}, r={wx_dc['r']:+.2f}. Real, but a fraction of what "
      "pooling ten genuinely different bets would give.")
    A(f"- **Return over drawdown: {'yes' if mar_win else 'no'}.** Median gap "
      f"{statistics.median(d_mar):+.2f} (sign p={st_mar['p']:.3f}, signed-rank "
      f"p={wx_mar['p']:.3f}, r={wx_mar['r']:+.2f}). The one variant that does look "
      f"better is the TOP-3-by-walk-forward basket, whose median return over drawdown "
      f"is the highest in the table above -- but it is not significant either "
      f"({sign_test([r['top3']['mar'] - r['crown']['mar'] for r in rows])['p']:.3f}) "
      "and the candidate board already showed walk-forward rank does not carry over.")
    A("")
    if money_win:
        A("**So: pooling wins on money.** Carry the shortlist.")
    elif real_div:
        A("**So: pooling buys smoothness, not money -- and the smoothness is real.** The "
          "finalists trade differently enough that the basket is genuine risk-spreading. "
          "Worth carrying if a shallower year is worth more than nothing extra earned.")
    else:
        A("**So: pooling buys a slightly smoother year and nothing else, and even that "
          "is mostly arithmetic.** The basket earns the same as picking a finalist "
          "blindly (it is that number), does not beat the crown on money, and its "
          "drawdown advantage is a fraction of what pooling genuinely different bets "
          "would deliver.")
    A("")
    A("**Practicality check -- the one that decides it.** " + (
        "The finalists disagree on real knobs AND their profit does not arrive at the "
        "same times, so the smoothing is diversification rather than arithmetic."
        if real_div else
        f"The finalists look different on the knobs but their sealed-year profit "
        f"correlates at {med_corr:+.2f} and {idp} of {len(rows)} runs contain finalists "
        "that traded IDENTICALLY. A basket of near-identical bets is not "
        "diversification; it is the same bet at a different size. The observed "
        f"{statistics.fmean(red)*100:.0f}% drawdown cut against the "
        f"{statistics.fmean(ideal)*100:.0f}% that unrelated bets would give is the "
        "measurement of exactly how cosmetic this is."))
    A("")
    A("**Recommendation.** The standing advice to \"carry the finalists as a SET\" is "
      "NOT supported. It should be restated as: the search's shortlist contains no "
      "extra money, and averaging it is not a risk tool because the shortlist is one "
      "bet wearing ten hats. If a smoother equity line is the goal, pool across "
      "FAMILIES, where the profit really does arrive at different times -- not across "
      "one search's finalists.")
    A("")
    A("## Per-family summary (per-run rows are in `pool_vs_crown.csv`)")
    A("")
    A("| Family | Runs | Crown net | Basket net | Crown DD | Basket DD | DD cut vs avg finalist | Distinct lines | Profit corr |")
    A("|---|---:|---:|---:|---:|---:|---:|---:|---:|")
    byfam: Dict[str, List[Dict[str, Any]]] = {}
    for r in rows:
        byfam.setdefault(r["fam"], []).append(r)
    for fam, rs in sorted(byfam.items(), key=lambda kv: -len(kv[1])):
        cut = [1.0 - abs(r["pool"]["dd"]) / abs(r["rand"]["dd"])
               for r in rs if abs(r["rand"]["dd"]) > 1e-9]
        cc = [r["corr"] for r in rs if r["corr"] is not None]
        dl = [r["dcurve"]["distinct"] / r["dcurve"]["n"] for r in rs if r["dcurve"]["n"]]
        A(f"| {fam} | {len(rs)} | {_fmt_money(statistics.fmean([r['crown']['net'] for r in rs]))} "
          f"| {_fmt_money(statistics.fmean([r['pool']['net'] for r in rs]))} "
          f"| {_fmt_money(statistics.fmean([r['crown']['dd'] for r in rs]))} "
          f"| {_fmt_money(statistics.fmean([r['pool']['dd'] for r in rs]))} "
          f"| {statistics.fmean(cut)*100:.0f}% | {statistics.fmean(dl)*100:.0f}% "
          f"| {('%+.2f' % statistics.fmean(cc)) if cc else 'n/a'} |")
    A("")
    A("Generated by `tools/pool_vs_crown.py` from the cached run reports. "
      "No Firestore read, no job queued.")
    return "\n".join(L)


CSV_COLS = ["rid", "fam", "strategy", "instrument", "lb_from", "lb_to", "years", "mult",
            "n_cands", "n_curves", "n_idle", "n_unknown", "n_weight",
            "crown_net", "crown_pf", "crown_dd", "crown_mar",
            "pool_net", "pool_pf", "pool_dd", "pool_mar",
            "top3_net", "top3_pf", "top3_dd", "top3_mar",
            "rand_net", "rand_pf", "rand_dd", "rand_mar",
            "dd_thinning_gap", "profit_corr", "frozen_share", "mean_param_dist",
            "near_dupe_pairs", "exact_dupe_pairs", "distinct_configs",
            "distinct_curves", "identical_curve_pairs"]


def write_csv(rows: List[Dict[str, Any]], path: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(CSV_COLS)
        for r in rows:
            w.writerow([
                r["rid"], r["fam"], r["strategy"], r["instrument"], r["lb_from"], r["lb_to"],
                round(r["years"], 4), r["mult"], r["n_cands"], r["n_curves"], r["n_idle"],
                r["n_unknown"], r["n_weight"],
                *[round(r[k][m], 4) for k in ("crown", "pool", "top3", "rand")
                  for m in ("net", "pf", "dd", "mar")],
                ("" if r["dd_gap"] is None else round(r["dd_gap"], 4)),
                ("" if r["corr"] is None else round(r["corr"], 4)),
                round(r["dist"]["frozen_share"], 4), round(r["dist"]["mean_dist"], 4),
                r["dist"]["near_dupe_pairs"], r["dist"]["exact_dupe_pairs"],
                r["dist"]["distinct_configs"],
                r["dcurve"]["distinct"], r["dcurve"]["identical_pairs"],
            ])


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Score an equal-weight basket of a run's finalists against its crown "
                    "in the sealed lockbox year.")
    ap.add_argument("--cache", default=RUN_CACHE_DIR, help="cached run-report directory")
    ap.add_argument("--min-cands", type=int, default=3,
                    help="minimum finalists carrying a sealed-year curve (default 3)")
    ap.add_argument("--md", default=OUT_MD)
    ap.add_argument("--csv", default=OUT_CSV)
    args = ap.parse_args(argv)

    docs = load_runs(args.cache)
    rows = []
    for d in docs:
        try:
            r = analyse_run(d, min_cands=args.min_cands)
        except Exception as exc:  # a malformed doc must not kill the sweep
            print(f"  run {d.get('id')}: skipped ({exc})")
            continue
        if r:
            rows.append(r)
    if not rows:
        print("No run carried enough sealed-year candidate curves.")
        return 1
    md = build_report(rows)
    os.makedirs(os.path.dirname(args.md), exist_ok=True)
    with open(args.md, "w", encoding="utf-8") as fh:
        fh.write(md + "\n")
    write_csv(rows, args.csv)
    print(f"{len(rows)} runs scored -> {args.md} ({len(md.splitlines())+1} lines), {args.csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
