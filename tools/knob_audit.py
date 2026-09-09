"""
tools/knob_audit.py -- THE SEARCH SPACE AUDIT.

Follow-on to tools/candidate_board.py. The board asked "is our PICKING any good?"
(answer: choosing among the ten finalists is a coin flip in the sealed year, 71% of
(family,knob) pairs carry no measurable predictive power, 58% of crowns sit on a range
edge). A separate walk-forward study found that RE-OPTIMISING DOESN'T PAY on ORB:
re-picked parameters earned $166k over 11 forward years against $377k for leaving the
strategy file's defaults alone.

Both point at the same lever: the SEARCH SPACE itself. This tool audits it knob by
knob and emits one actionable verdict per knob.

PRE-REGISTERED MEASUREMENTS -- fixed before any number was read. Nothing below was
added, dropped or reworded after seeing a result.

  1 SPREAD    Where the crowned value landed across runs, expressed as a fraction of
              the DECLARED range (the min/max written in the strategy file's
              DEFAULT_PARAMS block). Reported as the interquartile spread of the
              normalised position, plus the run count.
  2 EDGE RATE Share of runs whose crowned value sat at the very bottom or very top of
              the declared range. Reported SEPARATELY for continuous knobs and for
              on/off switches: a switch is always "on an edge" by construction and
              inflates the number (the board measured 84% with switches, 58% without).
  3 POWER     Median predictive-power score from each run's stored parameter-
              relationship block, plus median mutual information and median absolute
              correlation. Zero = that knob's value told the search nothing about the
              result inside the space that was searched.
  4 DRIFT     Rank correlation between the crowned value and the run's date. A knob
              that drifts is EITHER regime-sensitive OR pure noise; these cached run
              docs cannot tell the two apart, and the report says so.
  5 VERDICT   FREEZE / WIDEN / KEEP / UNCLEAR, with the evidence inline.
  6 BUDGET    Per family: knobs currently searched vs knobs the audit keeps, and the
              resulting grid size, using the per-knob step counts declared in the
              strategy file.

  SANITY CHECK (mandatory, reported honestly): for every FREEZE knob, did the ten
  short-listed finalists inside a single run actually carry DIFFERENT values for it?
  If they all carried the same value, that knob was never really searched in that run
  and its "zero power" reading is partly an artifact of the search, not a fact about
  the market. Reported per knob, never hidden.

DEFINITIONS (plain language)
  knob            one tunable input of a strategy (a row of its Settings panel).
  declared range  the lowest and highest value the strategy file allows for that knob.
  crowned value   the value the run's champion configuration ended up carrying.
  finalist        one of the ten configurations a validate run short-lists.
  lockbox         the final months of data the search never saw.
  on/off switch   a knob with only two possible values (a tick-box), or one the search
                  only ever gave two distinct values.
  edge            crowned value within 2% of the range width of the declared min or max.
  step count      how many distinct values the declared range holds at its declared
                  step -- the number of settings the search must try for that knob.

DATA
  Cached run docs only: C:\\EdgeLog\\_anatomy_cache\\runs\\<rid>.json. ZERO Firestore
  reads. Declared ranges come from augur_strategies/<strategy file>. BOOK runs (pooled
  multi-leg books) are skipped -- they carry no single parameter set.

Usage:
  python tools/knob_audit.py
  python tools/knob_audit.py --min-runs 5
"""
import os
import re
import ast
import sys
import json
import math
import argparse
import collections

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_CACHE_BASE = os.environ.get("EDGELOG_CACHE_DIR") or (
    r"C:\EdgeLog\_anatomy_cache" if os.path.isdir(r"C:\EdgeLog")
    else os.path.join(ROOT, "tools", "_anatomy_cache"))
RUN_CACHE_DIR = os.path.join(_CACHE_BASE, "runs")
STRAT_DIR = os.path.join(ROOT, "augur_strategies")
OUT_DIR = os.path.join(ROOT, "docs", "candidates")

MIN_RUNS = 5          # below this a knob's spread/edge rate is not askable
EDGE_TOL = 0.02       # "at the edge" = within 2% of the range width
WIDEN_AT = 0.50       # edge rate at or above this = the optimum is probably outside
TIGHT_IQR = 0.10      # interquartile spread at or below this = the crown sits still
WIDEN_BY = 0.50       # how far past the offending edge to re-declare, as a fraction
                      # of the current width
OFF_FLOOR_AT = 0.60   # share parked on a 0 floor that counts as "the knob is off"
OFF_FLOOR_TAG = "0 = off floor"

# Families whose runs are pooled. Anything else is reported as OTHER and not audited.
SKIP_FAMS = {"BOOK", "COMBINED"}


# ---------------------------------------------------------------------------
# small stats primitives (kept self-contained -- no scipy)
# ---------------------------------------------------------------------------
def _num(v):
    if isinstance(v, bool):
        return float(v)
    try:
        f = float(v)
        return f if math.isfinite(f) else np.nan
    except (TypeError, ValueError):
        return np.nan


def _rank(a):
    a = np.asarray(a, dtype=float)
    order = np.argsort(a, kind="mergesort")
    r = np.empty(len(a), dtype=float)
    r[order] = np.arange(1, len(a) + 1, dtype=float)
    uniq, inv, cnt = np.unique(a, return_inverse=True, return_counts=True)
    if (cnt > 1).any():
        sums = np.zeros(len(uniq))
        np.add.at(sums, inv, r)
        r = (sums / cnt)[inv]
    return r


def spearman(x, y):
    """Rank correlation, -1..+1. NaN when under 3 usable pairs or either side is flat."""
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    m = np.isfinite(x) & np.isfinite(y)
    if m.sum() < 3:
        return np.nan
    rx, ry = _rank(x[m]), _rank(y[m])
    if rx.std() == 0 or ry.std() == 0:
        return np.nan
    return float(np.corrcoef(rx, ry)[0, 1])


# ---------------------------------------------------------------------------
# metric 1 + 2: spread and edge rate
# ---------------------------------------------------------------------------
def norm_pos(value, lo, hi):
    """Where a crowned value sits inside its declared range: 0 = the declared minimum,
    1 = the declared maximum. NaN when the range is unusable."""
    value, lo, hi = _num(value), _num(lo), _num(hi)
    if not (np.isfinite(value) and np.isfinite(lo) and np.isfinite(hi)) or hi <= lo:
        return np.nan
    return (value - lo) / (hi - lo)


def iqr_frac(positions):
    """SPREAD: the interquartile spread of the normalised positions. 0 = every run
    crowned the same value; 1 = the crown lands anywhere in the range."""
    p = np.asarray([x for x in positions if np.isfinite(x)], dtype=float)
    if len(p) < 2:
        return np.nan
    return float(np.percentile(p, 75) - np.percentile(p, 25))


def on_edge(value, lo, hi, tol_frac=EDGE_TOL):
    """True when the crowned value sits at the declared minimum or maximum."""
    p = norm_pos(value, lo, hi)
    if not np.isfinite(p):
        return False
    return bool(p <= tol_frac or p >= 1.0 - tol_frac)


def edge_rate(values, lo, hi, tol_frac=EDGE_TOL):
    """EDGE RATE: share of crowned values sitting on the declared min or max."""
    vals = [v for v in values if np.isfinite(_num(v))]
    if not vals:
        return np.nan
    return float(np.mean([on_edge(v, lo, hi, tol_frac) for v in vals]))


def edge_sides(values, lo, hi, tol_frac=EDGE_TOL):
    """(share at the bottom, share at the top) -- which way the crowns pile up."""
    vals = [v for v in values if np.isfinite(_num(v))]
    if not vals:
        return (np.nan, np.nan)
    p = [norm_pos(v, lo, hi) for v in vals]
    p = [x for x in p if np.isfinite(x)]
    if not p:
        return (np.nan, np.nan)
    return (float(np.mean([x <= tol_frac for x in p])),
            float(np.mean([x >= 1.0 - tol_frac for x in p])))


def is_switch(spec):
    """An on/off switch: a tick-box knob, a two-option list, or a DECLARED range holding
    two settings or fewer. Judged from the strategy file alone -- deliberately NOT from
    how many values a particular search happened to try, because a continuous knob the
    search only gave two values to is a knob that was under-searched, not a switch.
    Switches are always 'on an edge' by construction and are counted separately."""
    if not spec:
        return False
    if str(spec.get("type") or "").lower() == "bool":
        return True
    opts = spec.get("options")
    if isinstance(opts, (list, tuple)) and len(opts) <= 2:
        return True
    sc = step_count(spec)
    return bool(sc is not None and sc <= 2)


def step_count(spec):
    """How many settings the declared range holds -- the per-knob cost of a grid."""
    if not spec:
        return None
    opts = spec.get("options")
    if isinstance(opts, (list, tuple)) and opts:
        return len(opts)
    if str(spec.get("type") or "").lower() == "bool":
        return 2
    lo, hi, st = _num(spec.get("min")), _num(spec.get("max")), _num(spec.get("step"))
    if not (np.isfinite(lo) and np.isfinite(hi)) or hi < lo:
        return None
    if not np.isfinite(st) or st <= 0:
        return None
    return int(math.floor(round((hi - lo) / st, 6))) + 1


# ---------------------------------------------------------------------------
# metric 4: drift
# ---------------------------------------------------------------------------
def drift_rho(timestamps, values):
    """DRIFT: rank correlation between the crowned value and when the run happened."""
    ts = pd.to_datetime(pd.Series(list(timestamps)), errors="coerce", format="mixed")
    if ts.notna().sum() < 3:
        return np.nan
    return spearman(ts.astype("int64").astype(float).values,
                    np.asarray([_num(v) for v in values], dtype=float))


# ---------------------------------------------------------------------------
# metric 5: the verdict
# ---------------------------------------------------------------------------
def _pc_share(rec):
    """Plain-English share of runs the switch was ON, for the switch verdict text."""
    p = _num(rec.get("median_pos"))
    return "on and off in different runs" if not np.isfinite(p) else         ("mostly on" if p >= 0.5 else "mostly off")


def recommend(rec):
    """One verdict per knob. Evaluated as a fixed ladder so the order is auditable.

    rec keys: n_runs, kind ('range'|'switch'), edge_rate, lo_share, hi_share,
              iqr, med_pps, n_power, lo, hi.
    Returns (verdict, reason).
    """
    n = rec.get("n_runs", 0)
    if n < MIN_RUNS:
        return "UNCLEAR", f"only {int(n)} crowned runs; needs {MIN_RUNS - int(n)} more"

    er = _num(rec.get("edge_rate"))
    lo_share = _num(rec.get("lo_share"))
    hi_share = _num(rec.get("hi_share"))
    lo = _num(rec.get("lo"))
    iqr = _num(rec.get("iqr"))
    pps = _num(rec.get("med_pps"))
    npow = rec.get("n_power", 0) or 0

    # 0. an on/off switch carries no stored power score -- judge it on consistency.
    if rec.get("kind") == "switch":
        if np.isfinite(iqr) and iqr <= 1e-9:
            return "FREEZE", (f"an on/off switch crowned the same way in all {int(n)} runs; "
                              f"the search is paying for a setting it never changes")
        return "UNCLEAR", (f"an on/off switch that flips between runs "
                           f"({_pc_share(rec)}), with no stored power score to judge it on")

    # 1. crowns piling on a declared edge -- the optimum was probably never bracketed.
    if rec.get("kind") == "range" and np.isfinite(er) and er >= WIDEN_AT:
        top_heavy = np.isfinite(hi_share) and np.isfinite(lo_share) and hi_share >= lo_share
        if top_heavy and hi_share >= WIDEN_AT:
            return "WIDEN", f"{hi_share:.0%} of crowns sit on the declared maximum"
        if (not top_heavy) and np.isfinite(lo_share) and lo_share >= WIDEN_AT:
            if np.isfinite(lo) and lo == 0.0:
                # 0 is almost always "feature off": there is nothing below it to widen
                # into, so a clear majority parked there is a decision, not a fence.
                if lo_share >= OFF_FLOOR_AT:
                    return "FREEZE", (f"{lo_share:.0%} of crowns sit on the "
                                      f"{OFF_FLOOR_TAG}; the search keeps switching this "
                                      f"knob OFF rather than tuning it")
                # a bare majority at an un-wideable floor proves nothing either way
            else:
                return "WIDEN", f"{lo_share:.0%} of crowns sit on the declared minimum"
        elif np.isfinite(lo_share) and np.isfinite(hi_share) and                 lo_share < WIDEN_AT and hi_share < WIDEN_AT:
            return "WIDEN", (f"{er:.0%} of crowns sit on a declared edge, split between "
                             f"both ends ({lo_share:.0%} bottom / {hi_share:.0%} top) -- "
                             f"the knob is either switched off or pushed to the ceiling, "
                             f"never in between")

    # 2. no measurable power AND the crown sits still -- pin it, stop paying for it.
    if npow >= 3 and np.isfinite(pps) and pps <= 0 and np.isfinite(iqr) and iqr <= TIGHT_IQR:
        return "FREEZE", (f"predictive power 0 over {int(npow)} runs and the crown moves "
                          f"across only {iqr:.0%} of the range")

    # 3. real power, crown lands in the interior -- keep searching it.
    if npow >= 3 and np.isfinite(pps) and pps > 0 and np.isfinite(er) and er < WIDEN_AT:
        return "KEEP", (f"predictive power {pps:.2f} over {int(npow)} runs, "
                        f"crowns interior ({er:.0%} on an edge)")

    if npow < 3:
        return "UNCLEAR", (f"power measured in only {int(npow)} runs; needs "
                           f"{3 - int(npow)} more with a stored relationship block")
    if np.isfinite(pps) and pps <= 0:
        return "UNCLEAR", (f"predictive power 0 but the crown wanders "
                           f"({iqr:.0%} of the range) -- no single value to pin")
    return "UNCLEAR", "evidence does not resolve"


def widen_to(lo, hi, step, hi_share, lo_share, frac=WIDEN_BY):
    """The range this audit would declare instead, extended past the edge the crowns
    pile on by `frac` of the current width, snapped to the declared step."""
    lo, hi, step = _num(lo), _num(hi), _num(step)
    if not (np.isfinite(lo) and np.isfinite(hi)) or hi <= lo:
        return (np.nan, np.nan)
    w = hi - lo
    ext = w * frac
    if np.isfinite(step) and step > 0:
        ext = max(step, round(ext / step) * step)
    if np.isfinite(hi_share) and hi_share >= (lo_share if np.isfinite(lo_share) else -1):
        return (lo, hi + ext)
    new_lo = lo - ext
    if lo > 0 and new_lo <= 0:
        # a period / length / multiple cannot sensibly go to zero: halve the floor instead
        new_lo = lo / 2.0
        if np.isfinite(step) and step > 0:
            new_lo = max(step, round(new_lo / step) * step)
    return (new_lo, hi)


# ---------------------------------------------------------------------------
# loading
# ---------------------------------------------------------------------------
def load_docs(cache_dir=RUN_CACHE_DIR):
    docs = {}
    if not os.path.isdir(cache_dir):
        return docs
    for fn in os.listdir(cache_dir):
        if not fn.endswith(".json") or not fn[:-5].isdigit():
            continue
        try:
            with open(os.path.join(cache_dir, fn), encoding="utf-8") as f:
                docs[int(fn[:-5])] = json.load(f)
        except Exception:
            continue
    return docs


_PARAM_CACHE = {}


def declared_params(strategy_name, strat_dir=None):
    """The DEFAULT_PARAMS block of a strategy file: {knob: {min,max,step,type,...}}.
    Parsed as a literal -- the file is never imported or executed."""
    strat_dir = strat_dir or STRAT_DIR
    if not strategy_name:
        return {}
    key = (strat_dir, strategy_name)
    if key in _PARAM_CACHE:
        return _PARAM_CACHE[key]
    fp = os.path.join(strat_dir, str(strategy_name))
    out = {}
    if os.path.exists(fp):
        try:
            with open(fp, encoding="utf-8") as f:
                tree = ast.parse(f.read())
            for node in tree.body:
                if not isinstance(node, ast.Assign):
                    continue
                if not any(getattr(t, "id", "") == "DEFAULT_PARAMS" for t in node.targets):
                    continue
                val = ast.literal_eval(node.value)
                if isinstance(val, dict):
                    out = {k: v for k, v in val.items() if isinstance(v, dict)}
                break
        except Exception:
            out = {}
    _PARAM_CACHE[key] = out
    return out


def family_of(doc):
    fam = doc.get("famKey")
    if fam:
        return str(fam).upper()
    s = str(doc.get("strategy") or "") + " " + str(doc.get("scope") or "")
    su = s.upper()
    for guess in ("ENGU-Q", "ENGUQ", "ORB", "NOISE", "TTMSQZ", "TTIBS", "VWAP", "REVERT",
                  "SUPERTREND", "NQDIP", "GAPGO", "ENGU"):
        if guess in su:
            return "ENGU-Q" if guess == "ENGUQ" else guess
    return "OTHER"


def is_book(doc):
    b = doc.get("book")
    if isinstance(b, (dict, list)) and b:
        return True
    return str(doc.get("famKey") or "").upper().startswith("BOOK")


def n_distinct_searched(doc):
    """{knob: how many distinct values this run's search actually tried}."""
    obs = {}
    pools = list(doc.get("points") or [])
    for c in ((doc.get("selection") or {}).get("candidates") or []):
        if isinstance(c, dict) and isinstance(c.get("params"), dict):
            pools.append(c["params"])
    for pt in pools:
        if not isinstance(pt, dict):
            continue
        for k, v in pt.items():
            if k in ("pnl", "dd"):
                continue
            f = _num(v)
            if np.isfinite(f):
                obs.setdefault(k, set()).add(f)
    return {k: len(v) for k, v in obs.items()}


# ---------------------------------------------------------------------------
# the crown table: one row per (run, knob)
# ---------------------------------------------------------------------------
def crown_table(docs):
    rows = []
    for rid, d in sorted(docs.items()):
        if is_book(d):
            continue
        fam = family_of(d)
        if fam in SKIP_FAMS:
            continue
        prm = d.get("best_params") or {}
        if not isinstance(prm, dict) or not prm:
            continue
        strat = str(d.get("strategy") or "")
        spec_all = declared_params(strat)
        nd = n_distinct_searched(d)
        for k, v in prm.items():
            f = _num(v)
            if not np.isfinite(f):
                continue          # text knobs (Direction, Session) are not audited here
            spec = spec_all.get(k) or {}
            lo, hi = _num(spec.get("min")), _num(spec.get("max"))
            if str(spec.get("type") or "").lower() == "bool" and not np.isfinite(lo):
                lo, hi = 0.0, 1.0
            rows.append(dict(
                run=rid, famKey=fam, strategy=strat, param=k, value=f,
                lo=lo, hi=hi, step=_num(spec.get("step")),
                has_spec=bool(spec),
                switch=is_switch(spec),
                label=str(spec.get("label") or "").strip(),
                n_searched=nd.get(k, np.nan),
                pos=norm_pos(f, lo, hi),
                edge=on_edge(f, lo, hi),
                ts=str(d.get("timestamp") or ""),
            ))
    return pd.DataFrame(rows)


def power_table(docs):
    """Pooled parameter-relationship blocks: predictive power per (family, knob)."""
    rows = []
    for rid, d in docs.items():
        if is_book(d):
            continue
        fam = family_of(d)
        if fam in SKIP_FAMS:
            continue
        rel = d.get("relationship")
        if not isinstance(rel, list):
            continue
        for e in rel:
            if not isinstance(e, dict) or not e.get("param"):
                continue
            rows.append(dict(run=rid, famKey=fam, param=e["param"],
                             pps=_num(e.get("pps")), mi=_num(e.get("mi")),
                             absr=abs(_num(e.get("r")))))
    return pd.DataFrame(rows)


def sanity_table(docs):
    """SANITY CHECK: inside each run, did the ten finalists actually differ on a knob?
    Also: does the BEST finalist (highest lockbox net) differ from the WORST?"""
    rows = []
    for rid, d in docs.items():
        if is_book(d):
            continue
        fam = family_of(d)
        if fam in SKIP_FAMS:
            continue
        cands = ((d.get("selection") or {}).get("candidates") or [])
        cands = [c for c in cands if isinstance(c, dict) and isinstance(c.get("params"), dict)]
        if len(cands) < 3:
            continue
        lb = []
        for c in cands:
            blk = c.get("lockbox") or {}
            lb.append(_num(blk.get("total_pnl")) if isinstance(blk, dict) else np.nan)
        lb = np.asarray(lb, dtype=float)
        best = int(np.nanargmax(lb)) if np.isfinite(lb).any() else None
        worst = int(np.nanargmin(lb)) if np.isfinite(lb).any() else None
        keys = set()
        for c in cands:
            keys |= set(c["params"].keys())
        for k in keys:
            vals = [_num(c["params"].get(k)) for c in cands]
            fin = [v for v in vals if np.isfinite(v)]
            if not fin:
                continue
            bw = np.nan
            if best is not None and worst is not None and best != worst:
                vb, vw = vals[best], vals[worst]
                if np.isfinite(vb) and np.isfinite(vw):
                    bw = float(vb != vw)
            rows.append(dict(run=rid, famKey=fam, param=k,
                             n_distinct=len(set(fin)),
                             all_same=float(len(set(fin)) <= 1),
                             best_vs_worst_differ=bw))
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# the audit
# ---------------------------------------------------------------------------
def audit(docs, min_runs=MIN_RUNS):
    cw = crown_table(docs)
    pw = power_table(docs)
    sn = sanity_table(docs)
    if cw.empty:
        return cw, pd.DataFrame(), sn

    pagg = {}
    if not pw.empty:
        g = pw.groupby(["famKey", "param"])
        pagg = {k: dict(n_power=int(v["pps"].notna().sum()),
                        med_pps=float(v["pps"].median()),
                        med_mi=float(v["mi"].median()),
                        med_absr=float(v["absr"].median()))
                for k, v in g}

    sagg = {}
    if not sn.empty:
        for k, v in sn.groupby(["famKey", "param"]):
            sagg[k] = dict(n_sanity=len(v),
                           share_all_same=float(v["all_same"].mean()),
                           share_bw_differ=float(v["best_vs_worst_differ"].mean(skipna=True))
                           if v["best_vs_worst_differ"].notna().any() else np.nan,
                           med_distinct=float(v["n_distinct"].median()))

    n_pinned = 0
    out = []
    for (fam, param), g in cw.groupby(["famKey", "param"]):
        g = g[g["has_spec"]]
        if g.empty:
            continue
        # Drop runs whose own strategy file PINS the knob (declared minimum == maximum).
        # Those runs never searched it, so they say nothing about where in a range the
        # crown lands, and their degenerate range would poison the family's declared one.
        searched = g[np.isfinite(g["pos"])]
        if searched.empty:
            n_pinned += 1
            continue
        g = searched
        pair = g.groupby(["lo", "hi"]).size().sort_values(ascending=False)
        lo, hi = (float(pair.index[0][0]), float(pair.index[0][1]))
        n_variants = int(len(pair))
        step = float(g["step"].mode().iloc[0]) if g["step"].notna().any() else np.nan
        switch = bool(g["switch"].mode().iloc[0])
        lab = [x for x in g["label"].tolist() if x]
        label = max(set(lab), key=lab.count) if lab else ""
        vals = g["value"].tolist()
        # Edge and position are measured against EACH RUN'S OWN declared range, so a
        # family whose files declare different widths is still scored honestly.
        er = float(g["edge"].mean())
        lo_s = float((g["pos"] <= EDGE_TOL).mean())
        hi_s = float((g["pos"] >= 1.0 - EDGE_TOL).mean())
        iq = iqr_frac(g["pos"].tolist())
        _fp = [x for x in g["pos"].tolist() if np.isfinite(x)]
        med_pos = float(np.median(_fp)) if _fp else np.nan
        p = pagg.get((fam, param), {})
        s = sagg.get((fam, param), {})
        modal = float(pd.Series(vals).mode().iloc[0])
        rec = dict(n_runs=len(g), kind="switch" if switch else "range",
                   edge_rate=er, lo_share=lo_s, hi_share=hi_s, iqr=iq,
                   med_pps=p.get("med_pps", np.nan), n_power=p.get("n_power", 0),
                   lo=lo, hi=hi, median_pos=med_pos)
        verdict, reason = recommend(rec)
        pin_at = lo if (verdict == "FREEZE" and OFF_FLOOR_TAG in reason) else modal
        nlo, nhi = (widen_to(lo, hi, step, hi_s, lo_s) if verdict == "WIDEN"
                    else (np.nan, np.nan))
        out.append(dict(
            famKey=fam, param=param, label=label, n_runs=len(g), kind=rec["kind"],
            declared_lo=lo, declared_hi=hi, step=step,
            n_declared_variants=n_variants,
            widest_lo=float(g["lo"].min()), widest_hi=float(g["hi"].max()),
            steps=step_count(dict(min=lo, max=hi, step=step)) if not switch else 2,
            modal_value=modal, pin_at=pin_at, median_value=float(np.median(vals)),
            iqr_frac=iq, median_pos=med_pos,
            edge_rate=er, lo_edge_share=lo_s, hi_edge_share=hi_s,
            n_power=p.get("n_power", 0), med_pps=p.get("med_pps", np.nan),
            med_mi=p.get("med_mi", np.nan), med_absr=p.get("med_absr", np.nan),
            drift_rho=drift_rho(g["ts"].tolist(), vals),
            n_sanity=s.get("n_sanity", 0),
            share_finalists_all_same=s.get("share_all_same", np.nan),
            share_best_worst_differ=s.get("share_bw_differ", np.nan),
            med_finalist_distinct=s.get("med_distinct", np.nan),
            recommendation=verdict, reason=reason,
            widen_lo=nlo, widen_hi=nhi,
        ))
    res = pd.DataFrame(out)
    res.attrs["n_pinned"] = n_pinned
    if not res.empty:
        # SANITY OVERRIDE: a FREEZE that rests on a knob the finalists never varied is
        # an artifact of the search, not a fact. Flag it, never hide it.
        art = (res["recommendation"].eq("FREEZE")
               & res["share_finalists_all_same"].ge(0.50)
               & res["n_sanity"].ge(3))
        res["freeze_is_artifact"] = art
        res.loc[art, "reason"] = res.loc[art, "reason"] + \
            " -- BUT the finalists never varied it in " + \
            (res.loc[art, "share_finalists_all_same"] * 100).round(0).astype(int).astype(str) + \
            "% of runs, so the zero-power reading is partly an artifact"
        res = res.sort_values(["famKey", "recommendation", "param"])
    return cw, res, sn


def budget(res, docs, min_runs=MIN_RUNS):
    """BUDGET IMPACT: knobs searched vs knobs kept, and the grid size either way."""
    # representative strategy file per family = the most-used one that exists on disk
    rep = collections.defaultdict(collections.Counter)
    for rid, d in docs.items():
        if is_book(d):
            continue
        fam = family_of(d)
        if fam in SKIP_FAMS:
            continue
        s = str(d.get("strategy") or "")
        if declared_params(s):
            rep[fam][s] += 1
    rows = []
    for fam, cnt in rep.items():
        # The reference file is the one that declares the most of the family's audited
        # knobs -- NOT simply the most-used file, which is often a cut-down variant that
        # pins half the space and would understate the grid.
        audited = set(res[res["famKey"] == fam]["param"]) if not res.empty else set()
        strat = max(cnt, key=lambda f: (len(audited & set(declared_params(f))),
                                        len([k for k, v in declared_params(f).items()
                                             if (step_count(v) or 0) > 1]),
                                        cnt[f]))
        spec = declared_params(strat)
        sc = {k: step_count(v) for k, v in spec.items()}
        sc = {k: v for k, v in sc.items() if v and v > 1}
        if not sc:
            continue
        sub = res[res["famKey"] == fam] if not res.empty else pd.DataFrame()
        frozen = set(sub[sub["recommendation"] == "FREEZE"]["param"]) if len(sub) else set()
        kept = {k: v for k, v in sc.items() if k not in frozen}
        full = int(np.prod(list(sc.values())))
        cut = int(np.prod(list(kept.values()))) if kept else 1
        rows.append(dict(famKey=fam, file=strat, n_runs=int(sum(cnt.values())),
                         knobs_now=len(sc), knobs_kept=len(kept),
                         knobs_frozen=len(sc) - len(kept), grid_now=full, grid_kept=cut,
                         shrink_factor=(full / cut) if cut else np.nan,
                         frozen_list=",".join(sorted(frozen & set(sc)))))
    return pd.DataFrame(rows).sort_values("grid_now", ascending=False)


# ---------------------------------------------------------------------------
# report
# ---------------------------------------------------------------------------
def _knob(r):
    """How the owner sees this knob: its Settings-panel label, with the internal name
    in brackets so the CSV and the app can be lined up."""
    lab = str(r.get("label") or "").strip()
    return f"{lab} (`{r['param']}`)" if lab else f"`{r['param']}`"


def _fm(x, nd=2):
    try:
        f = float(x)
        if not math.isfinite(f):
            return "n/a"
        return f"{f:.{nd}f}".rstrip("0").rstrip(".") if nd else f"{f:.0f}"
    except (TypeError, ValueError):
        return "n/a"


def _pc(x):
    try:
        f = float(x)
        return "n/a" if not math.isfinite(f) else f"{f*100:.0f}%"
    except (TypeError, ValueError):
        return "n/a"


def write_report(res, bud, docs, out_dir=OUT_DIR):
    os.makedirs(out_dir, exist_ok=True)
    L = []
    A = L.append
    n_runs = sum(1 for d in docs.values() if not is_book(d))
    A("# SEARCH SPACE AUDIT -- which knobs to stop searching")
    A("")
    A(f"Built by `tools/knob_audit.py` from {n_runs} cached run records. No Firestore reads. "
      "One verdict per knob per strategy family.")
    A("")
    A("**Words used here.** A *knob* is one tunable input of a strategy -- a row of its "
      "Settings panel. Its *declared range* is the lowest and highest value the strategy "
      "file allows. The *crowned value* is the one the run's champion ended up carrying. "
      "A *finalist* is one of the ten configurations a validate run short-lists. The "
      "*lockbox* is the final months of data the search never saw. A knob is *on an edge* "
      "when its crowned value sits within 2% of the range width of the declared minimum or "
      "maximum. An *on/off switch* is a knob with only two settings; it is always on an "
      "edge by construction, so it is counted separately everywhere below. *Predictive "
      "power* is the 0-1 score each run stores per knob saying how much that knob's value "
      "explained the run's result; 0 means it explained nothing inside the space searched. "
      "*Spread* is how much the crowned value moved between runs, measured as a share of "
      "the declared range (0 = always the same setting, 1 = anywhere).")
    A("")
    A("**Why this exists.** The candidate board found that picking between the ten "
      "finalists is a coin flip in the sealed year, that 71% of knobs carry no measurable "
      "predictive power, and that 58% of champions sit on a range edge. A separate "
      "walk-forward study found that re-picking parameters on ORB earned $166k over 11 "
      "forward years against $377k for leaving the file's defaults alone. Both say the same "
      "thing: the problem is the space we search, not the picker. This audits the space.")
    A("")

    if res.empty:
        A("_No auditable knobs found._")
        with open(os.path.join(out_dir, "KNOB_AUDIT.md"), "w", encoding="utf-8") as f:
            f.write("\n".join(L) + "\n")
        return

    cont = res[res["kind"] == "range"]
    sw = res[res["kind"] == "switch"]
    A("## Headline")
    A("")
    A(f"- {len(res)} knobs audited across {res['famKey'].nunique()} families "
      f"({len(cont)} real ranges, {len(sw)} on/off switches).")
    A(f"- Edge rate **{_pc(cont['edge_rate'].mean())} over real ranges**, "
      f"{_pc(res['edge_rate'].mean())} once switches are mixed in -- the second number is "
      "inflated and should not be quoted. This is lower than the candidate board's 58% "
      "because the board measured against the range each search actually swept after "
      "auto-widening, while this measures against the range the strategy file DECLARES, "
      "and drops runs whose file pinned the knob outright.")
    A(f"- Verdicts: " + ", ".join(f"**{k}** {v}" for k, v in
                                  res["recommendation"].value_counts().items()) + ".")
    if res["freeze_is_artifact"].any():
        A(f"- {int(res['freeze_is_artifact'].sum())} FREEZE verdicts rest on knobs the ten "
          "finalists never actually varied -- flagged in the table, see the sanity check.")
    A("")

    A("## FREEZE -- stop searching, pin at this value")
    A("")
    A("Zero predictive power and a crown that barely moves, or crowns piling on the "
      "`0 = off` floor. Pinning these costs nothing measurable and shrinks the grid.")
    A("")
    fz = res[res["recommendation"] == "FREEZE"]
    if len(fz):
        A("| family | knob | pin at | runs | spread | power | finalists varied it? |")
        A("|---|---|---:|---:|---:|---:|---|")
        for _, r in fz.iterrows():
            sv = r["share_finalists_all_same"]
            var = ("n/a" if not np.isfinite(_num(sv)) else
                   f"no in {_pc(sv)} of runs" if sv >= 0.5 else f"yes ({_pc(1-sv)} of runs)")
            A(f"| {r.famKey} | {_knob(r)} | **{_fm(r.pin_at)}** | {int(r.n_runs)} | "
              f"{_pc(r.iqr_frac)} | {_fm(r.med_pps)} | {var} |")
    else:
        A("_None._")
    A("")

    A("## WIDEN -- the optimum is probably outside the range we drew")
    A("")
    A("Half or more of the champions land on a declared end-stop, so the value we read off "
      "the champion is a limit we imposed rather than something the market chose. The "
      "proposed range extends past the busier end-stop by half the current width, snapped "
      "to the declared step. Where the crowns split across BOTH ends the knob is behaving "
      "as on-or-maxed rather than as a dial, and the widening is a probe, not a fix. The "
      "last column is the widest range any file in that family already allows: where it is "
      "wider than the proposal, the fix is to adopt that file's range rather than invent a "
      "new one.")
    A("")
    wd = res[res["recommendation"] == "WIDEN"]
    if len(wd):
        A("| family | knob | declared now | crowns on an end-stop (bottom / top) | declare instead | widest a file already allows | runs |")
        A("|---|---|---|---:|---|---|---:|")
        for _, r in wd.iterrows():
            wide = f"{_fm(r.widest_lo)} to {_fm(r.widest_hi)}"
            if _num(r.widest_lo) == _num(r.declared_lo) and _num(r.widest_hi) == _num(r.declared_hi):
                wide = "same"
            A(f"| {r.famKey} | {_knob(r)} | {_fm(r.declared_lo)} to {_fm(r.declared_hi)} | "
              f"{_pc(r.edge_rate)} ({_pc(r.lo_edge_share)} / {_pc(r.hi_edge_share)}) | "
              f"**{_fm(r.widen_lo)} to {_fm(r.widen_hi)}** | {wide} | {int(r.n_runs)} |")
    else:
        A("_None._")
    A("")

    A("## KEEP -- real power, champions land in the interior")
    A("")
    kp = res[res["recommendation"] == "KEEP"]
    if len(kp):
        A("| family | knob | power | spread | edge rate | drift | runs |")
        A("|---|---|---:|---:|---:|---:|---:|")
        for _, r in kp.iterrows():
            A(f"| {r.famKey} | {_knob(r)} | {_fm(r.med_pps)} | {_pc(r.iqr_frac)} | "
              f"{_pc(r.edge_rate)} | {_fm(r.drift_rho)} | {int(r.n_runs)} |")
    else:
        A("_None._")
    A("")

    A("## Drift -- does the winning setting move with the calendar?")
    A("")
    A("Rank correlation between the crowned value and the run's date, -1 to +1. "
      "**These cached records cannot tell a regime-sensitive knob from a noisy one.** A "
      "drifting knob may be tracking a changing market or may simply be re-rolled each "
      "time; distinguishing them needs a fixed-window re-run of the same knob across eras, "
      "which is not in this data. Listed for follow-up only, never as a finding.")
    A("")
    dr = res[res["drift_rho"].abs() >= 0.5].sort_values("drift_rho")
    if len(dr):
        A("| family | knob | drift | runs | verdict |")
        A("|---|---|---:|---:|---|")
        for _, r in dr.head(8).iterrows():
            A(f"| {r.famKey} | {_knob(r)} | {_fm(r.drift_rho)} | {int(r.n_runs)} | "
              f"{r.recommendation} |")
    else:
        A("_No knob drifts at |0.5| or above._")
    A("")

    A("## Sanity check -- was the knob ever really searched?")
    A("")
    A("For each FREEZE knob: inside a single run, did the ten short-listed finalists carry "
      "different values for it? If they all carried the same value, the search never "
      "explored it there and the zero-power reading is partly an artifact of our own grid, "
      "not evidence about the market. Reported per knob rather than buried.")
    A("")
    sc = res[res["recommendation"] == "FREEZE"].copy()
    if len(sc) and sc["n_sanity"].sum():
        A("| family | knob | runs checked | finalists all identical | best vs worst finalist differ | reading |")
        A("|---|---|---:|---:|---:|---|")
        for _, r in sc.iterrows():
            if not r["n_sanity"]:
                continue
            rd = ("ARTIFACT -- never searched" if r["freeze_is_artifact"]
                  else "genuine -- it was searched and did not matter")
            A(f"| {r.famKey} | {_knob(r)} | {int(r.n_sanity)} | "
              f"{_pc(r.share_finalists_all_same)} | {_pc(r.share_best_worst_differ)} | {rd} |")
        A("")
        art = int(sc["freeze_is_artifact"].sum())
        A(f"**What this changes:** {art} of {len(sc)} FREEZE verdicts are artifacts of a "
          "grid that never varied the knob. Freezing those is still the right *action* -- "
          "the search was not using them anyway -- but it is **not** evidence the knob is "
          "useless, so none of them should be written off permanently. The remaining "
          f"{len(sc) - art} were genuinely varied and genuinely did not move the result.")
    else:
        A("_No finalist records available for the FREEZE knobs._")
    A("")

    A("## Budget impact -- the same trial budget over a smaller space")
    A("")
    A("*Settings* here is every combination the declared ranges allow, multiplied together "
      "-- the haystack, not a list the search ever walks. Freezing a knob deletes its "
      "multiplier outright. The trial budget does not change; each trial simply covers more "
      "of what is left. The reference file for each family is the one declaring the most of "
      "that family's audited knobs, not the most-run variant.")
    A("")
    if not bud.empty:
        A("| family | reference file | runs | knobs now | knobs kept | settings now | settings after | smaller by |")
        A("|---|---|---:|---:|---:|---:|---:|---:|")
        for _, r in bud.iterrows():
            f = _num(r.shrink_factor)
            fs = "unchanged" if (np.isfinite(f) and f <= 1.0001) else f"{f:,.0f}x"
            A(f"| {r.famKey} | `{r.file}` | {int(r.n_runs)} | {int(r.knobs_now)} | "
              f"{int(r.knobs_kept)} | {int(r.grid_now):,} | {int(r.grid_kept):,} | {fs} |")
    else:
        A("_No strategy files matched._")
    A("")

    A("## How to act on this")
    A("")
    A("1. Pin every FREEZE knob at the value in that table and take it out of the search.")
    A("2. Re-declare the WIDEN ranges before the next sweep -- a champion on an end-stop is "
      "an unfinished search, and its value is a floor or ceiling we imposed, not a finding.")
    A("3. Leave the KEEP knobs alone and let the same trial budget cover the smaller space.")
    A("4. Nothing here says a frozen knob is worthless. It says the search, as run, could "
      "not tell -- and for the artifact-flagged ones it never even asked.")
    A("")
    A("Row-level numbers for every knob, including every UNCLEAR one: "
      "`docs/candidates/knob_audit.csv` (and the same rows as `knob_audit.json`, because "
      "the repo does not track CSV files).")

    with open(os.path.join(out_dir, "KNOB_AUDIT.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")
    res.to_csv(os.path.join(out_dir, "knob_audit.csv"), index=False)
    # *.csv is gitignored repo-wide, so mirror the same rows as JSON for the repo.
    res.to_json(os.path.join(out_dir, "knob_audit.json"), orient="records", indent=1)
    return len(L)


def main(argv=None):
    ap = argparse.ArgumentParser()
    global MIN_RUNS
    ap.add_argument("--min-runs", type=int, default=MIN_RUNS)
    ap.add_argument("--cache", default=RUN_CACHE_DIR)
    ap.add_argument("--out", default=OUT_DIR)
    a = ap.parse_args(argv)
    MIN_RUNS = a.min_runs
    docs = load_docs(a.cache)
    print(f"loaded {len(docs)} cached run records from {a.cache}")
    cw, res, sn = audit(docs, a.min_runs)
    bud = budget(res, docs, a.min_runs)
    n = write_report(res, bud, docs, a.out)
    print(f"knobs audited: {len(res)}  crown rows: {len(cw)}  sanity rows: {len(sn)}")
    if not res.empty:
        print(res["recommendation"].value_counts().to_string())
    print(f"wrote {a.out}\\KNOB_AUDIT.md ({n} lines) + knob_audit.csv")
    return 0


if __name__ == "__main__":
    sys.exit(main())
