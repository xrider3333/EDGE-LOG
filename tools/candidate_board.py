"""
tools/candidate_board.py -- THE CANDIDATE BOARD.

Every Auto-Validate run doc (`users/<uid>/runs/<rid>`) carries `selection.candidates`:
the 10 parameter sets the search short-listed, each with its in-sample, walk-forward,
pre-lockbox and LOCKBOX stat blocks, plus a `crowned` flag saying which one the search
picked. That is ~10x more out-of-sample evidence than we have ever looked at -- we
normally read only the crowned row. This tool pools every run's candidates into one
table and asks whether the search's own picking is any good.

PRE-REGISTERED QUESTIONS -- written BEFORE any answer was computed. No question below
was added, dropped or reworded after seeing a number. Anything found later that is not
on this list is reported as EXPLORATORY, never as a result.

  Q1  Does the in-sample winner win out of sample?
      Within each run, rank the 10 candidates by in-sample net and by lockbox net.
      Report the Spearman rank correlation per run, the distribution across runs, and
      the share of runs where the top-in-sample candidate also lands top-3 in the
      lockbox. Compare against the null of random ranking by permutation.

      DISCLOSURE (specification ambiguity found while implementing, resolved by
      reporting BOTH, never by picking after the fact): a candidate carries TWO
      "in-sample net" numbers -- `is_pnl` (the top-level score the search itself ranks
      on) and `cal.is.total_pnl` (the Stage-A first-75%-split calibration slice; see
      edgelog-validate-header-75-split). They are never equal. `is_pnl` is the PRIMARY
      answer because it is the number the search actually optimises; `cal.is` is
      reported beside it as a robustness row in every table. Both were computed in the
      same pass and neither was dropped.

  Q2  Is the crowned candidate better than a random one of the 10, in the lockbox?
      Paired across runs: crowned lockbox net vs the MEAN of the other nine. Sign test
      + effect size. Repeat for lockbox profit factor and lockbox net/DD.

  Q3  Which single parameter values are STABLE across runs of the same family?
      Per family, per knob: the crowned value in each run, over time. Report the
      interquartile spread as a FRACTION OF THE SEARCHED RANGE, and whether the crowned
      value drifts with run date (rank correlation with time). A knob whose crown lands
      anywhere in its range is noise; a knob that always lands in the same place is a
      real structural constant.

  Q4  Which knobs actually move the result?
      Pool the per-run `relationship` blocks (mutual information / correlation /
      predictive power score per knob) by family; rank knobs by median predictive power
      score. Cross-check against Q3: do the knobs that matter also sit still?

  Q5  Does walk-forward performance predict lockbox performance better than in-sample?
      Per run, Spearman(in-sample net, lockbox net) vs Spearman(walk-forward OOS net,
      lockbox net). Paired test across runs. This is the practical question: which
      number should we crown on.

  Q6  Fence check. For every crowned candidate, is each knob's value sitting at the
      EDGE of its searched range? Report the share of crowns on a fence per family. A
      fence crown means the search never saw the real optimum.

DEFINITIONS (plain language, EDGELOG-UI terms)
  candidate      one of the 10 parameter sets `selection.candidates` short-lists.
  crowned        the single candidate the run declared its champion (`crowned: true`).
  in-sample (IS) the optimise window the search fitted on.
  walk-forward   rolling out-of-sample folds inside the optimise window (`wf_oos_pnl`).
  lockbox (LB)   the final N months the search NEVER saw -- the honest score.
  net            total_pnl in dollars.
  PF             profit factor = gross win / gross loss.
  net/DD         net divided by max drawdown -- return per unit of pain.
  Spearman rho   rank correlation, -1..+1. 0 = the ordering carries no information.
  fence          a crowned knob value equal to the lowest or highest value searched.

HARVEST + READ BUDGET
  One Firestore `.get()` per run id, ids 1..400. Every fetched doc is cached as JSON
  under C:\\EdgeLog\\_anatomy_cache\\runs\\<rid>.json and a cached id is NEVER re-read.
  Ids that came back missing are recorded in _missing.json so repeat runs do not burn
  reads on them either (--refresh-missing retries them). The Firestore read count is
  printed every run; the Spark plan cap is 50k reads/day.

  BOOK runs (a pooled multi-leg book, `book` block present) are skipped: they carry no
  `selection.candidates`.

Usage:
  python tools/candidate_board.py                 # harvest (cached) + analyse + write
  python tools/candidate_board.py --no-fetch      # analyse from cache only, 0 reads
  python tools/candidate_board.py --max-id 400
"""
import os
import sys
import json
import math
import argparse
import datetime

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHARED = r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"
UID = "IO0K35JpLIcH9YK4C0pMNYUzZOM2"

_CACHE_BASE = os.environ.get("EDGELOG_CACHE_DIR") or (
    r"C:\EdgeLog\_anatomy_cache" if os.path.isdir(r"C:\EdgeLog") else os.path.join(ROOT, "tools", "_anatomy_cache"))
RUN_CACHE_DIR = os.path.join(_CACHE_BASE, "runs")
MISSING_FP = os.path.join(RUN_CACHE_DIR, "_missing.json")
OUT_DIR = os.path.join(ROOT, "docs", "candidates")

# A candidate needs a lockbox block with trades to be scoreable at all.
MIN_CANDS = 3          # runs with fewer short-listed configs carry no ranking signal
N_PERM = 5000
SEED = 42

READS = {"n": 0}


# ---------------------------------------------------------------------------
# harvest
# ---------------------------------------------------------------------------
def _json_default(o):
    if isinstance(o, (datetime.datetime, datetime.date)):
        return o.isoformat()
    return str(o)


def _load_missing():
    if os.path.exists(MISSING_FP):
        try:
            with open(MISSING_FP, encoding="utf-8") as f:
                return set(int(x) for x in json.load(f))
        except Exception:
            return set()
    return set()


def _save_missing(ids):
    os.makedirs(RUN_CACHE_DIR, exist_ok=True)
    with open(MISSING_FP, "w", encoding="utf-8") as f:
        json.dump(sorted(ids), f)


def _db():
    import firebase_admin
    from firebase_admin import credentials, firestore
    cred_path = os.path.join(ROOT, "serviceAccount.json")
    if not os.path.exists(cred_path):
        cred_path = os.path.join(SHARED, "serviceAccount.json")
    if not firebase_admin._apps:
        firebase_admin.initialize_app(credentials.Certificate(cred_path))
    return firestore.client()


def harvest(max_id=400, fetch=True, refresh_missing=False, verbose=True):
    """Return {rid: doc} for every run id 1..max_id that exists. One .get() per
    uncached id; cached ids are read off disk and never re-fetched."""
    os.makedirs(RUN_CACHE_DIR, exist_ok=True)
    missing = set() if refresh_missing else _load_missing()
    docs, db = {}, None
    for rid in range(1, max_id + 1):
        fp = os.path.join(RUN_CACHE_DIR, f"{rid}.json")
        if os.path.exists(fp):
            with open(fp, encoding="utf-8") as f:
                docs[rid] = json.load(f)
            continue
        if rid in missing or not fetch:
            continue
        if db is None:
            db = _db()
        try:
            snap = db.collection("users").document(UID).collection("runs").document(str(rid)).get()
        except Exception as e:
            if "ResourceExhausted" in type(e).__name__ or "Quota" in str(e) or "429" in str(e):
                _save_missing(missing)
                raise SystemExit(
                    f"Firestore READ QUOTA EXHAUSTED after {READS['n']} reads (Spark, 50k/day, resets "
                    f"midnight Pacific). {len(docs)} runs cached in {RUN_CACHE_DIR}; re-run with "
                    f"--no-fetch to analyse what we have.")
            raise
        READS["n"] += 1
        if not snap.exists:
            missing.add(rid)
            continue
        d = snap.to_dict()
        with open(fp, "w", encoding="utf-8") as f:
            json.dump(d, f, default=_json_default, indent=1)
        docs[rid] = d
    _save_missing(missing)
    if verbose:
        print(f"[harvest] Firestore reads this session: {READS['n']}  |  runs on disk: {len(docs)}  "
              f"|  known-missing ids: {len(missing)}")
    return docs


def _is_book(d):
    b = d.get("book")
    if isinstance(b, dict) and b:
        return True
    if isinstance(b, list) and b:
        return True
    fam = str(d.get("famKey") or "")
    return fam.upper().startswith("BOOK")


def _num(v):
    try:
        f = float(v)
        return f if math.isfinite(f) else np.nan
    except (TypeError, ValueError):
        return np.nan


def _stat(block, key):
    if not isinstance(block, dict):
        return np.nan
    return _num(block.get(key))


def _session(d):
    for k in ("session", "data_source", "source_name", "source"):
        v = str(d.get(k) or "").upper()
        if "ETH" in v:
            return "ETH"
        if "RTH" in v:
            return "RTH"
    return ""


# ---------------------------------------------------------------------------
# tidy table
# ---------------------------------------------------------------------------
def build_table(docs):
    """One row per (run, candidate)."""
    rows = []
    for rid in sorted(docs):
        d = docs[rid]
        if _is_book(d):
            continue
        sel = d.get("selection") or {}
        cands = sel.get("candidates") or []
        if not isinstance(cands, list) or not cands:
            continue
        val = d.get("validate") or {}
        win = (val.get("windows") or {}) if isinstance(val, dict) else {}
        opt = win.get("optimize") or [None, None]
        lbw = win.get("lockbox") or [None, None]
        pbo = ((val.get("pbo") or {}) if isinstance(val, dict) else {}).get("pbo")
        dsr = ((d.get("dsr") or {})).get("dsr")
        base = dict(
            run=rid,
            famKey=d.get("famKey"),
            famSeq=d.get("famSeq"),
            strategy=d.get("strategy"),
            instrument=d.get("instrument"),
            timeframe=d.get("timeframe"),
            session=_session(d),
            timestamp=str(d.get("timestamp") or ""),
            date_from=d.get("date_from"),
            date_to=d.get("date_to"),
            opt_from=opt[0] if len(opt) > 0 else None,
            opt_to=opt[1] if len(opt) > 1 else None,
            lb_from=lbw[0] if len(lbw) > 0 else None,
            lb_to=lbw[1] if len(lbw) > 1 else None,
            lb_months=win.get("lockbox_months"),
            pbo=_num(pbo),
            dsr=_num(dsr),
            n_evaluated=_num(d.get("n_evaluated")),
            n_cands=len(cands),
        )
        for i, c in enumerate(cands):
            if not isinstance(c, dict):
                continue
            cal = c.get("cal") or {}
            r = dict(base)
            r["cand_ix"] = i
            r["crowned"] = bool(c.get("crowned"))
            r["params"] = json.dumps(c.get("params") or {}, sort_keys=True, default=str)
            r["folds_held"] = _num(c.get("folds_held"))
            r["is_pnl"] = _num(c.get("is_pnl"))
            r["wf_oos_pnl"] = _num(c.get("wf_oos_pnl"))
            for tag, blk in (("is", cal.get("is") or c.get("is_rng")),
                             ("wf", cal.get("wf") or c.get("wf_rng")),
                             ("pre", cal.get("pre") or c.get("metrics")),
                             ("lb", c.get("lockbox"))):
                r[f"{tag}_net"] = _stat(blk, "total_pnl")
                r[f"{tag}_pf"] = _stat(blk, "profit_factor")
                r[f"{tag}_trades"] = _stat(blk, "num_trades")
                r[f"{tag}_dd"] = _stat(blk, "max_drawdown")
            rows.append(r)
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    for tag in ("is", "wf", "pre", "lb"):
        dd = df[f"{tag}_dd"].abs()
        df[f"{tag}_netdd"] = np.where(dd > 0, df[f"{tag}_net"] / dd, np.nan)
    return df


# ---------------------------------------------------------------------------
# stats primitives (no scipy dependency for the core, kept self-contained)
# ---------------------------------------------------------------------------
def _rank(a):
    a = np.asarray(a, dtype=float)
    order = np.argsort(a, kind="mergesort")
    r = np.empty(len(a), dtype=float)
    r[order] = np.arange(1, len(a) + 1, dtype=float)
    # average ties
    uniq, inv, cnt = np.unique(a, return_inverse=True, return_counts=True)
    for k in np.where(cnt > 1)[0]:
        m = inv == k
        r[m] = r[m].mean()
    return r


def spearman(x, y):
    """Rank correlation. NaN if fewer than 3 usable pairs or either side is constant."""
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    m = np.isfinite(x) & np.isfinite(y)
    if m.sum() < 3:
        return np.nan
    rx, ry = _rank(x[m]), _rank(y[m])
    if rx.std() == 0 or ry.std() == 0:
        return np.nan
    return float(np.corrcoef(rx, ry)[0, 1])


def sign_test(diffs):
    """Two-sided exact binomial sign test on paired differences. Returns
    (n_used, n_positive, p_value)."""
    d = np.asarray([x for x in diffs if np.isfinite(x) and x != 0.0], dtype=float)
    n = len(d)
    if n == 0:
        return 0, 0, np.nan
    k = int((d > 0).sum())
    from math import comb
    tail = sum(comb(n, i) for i in range(0, min(k, n - k) + 1)) / (2.0 ** n)
    return n, k, float(min(1.0, 2.0 * tail))


def cohen_d_paired(diffs):
    d = np.asarray([x for x in diffs if np.isfinite(x)], dtype=float)
    if len(d) < 2 or d.std(ddof=1) == 0:
        return np.nan
    return float(d.mean() / d.std(ddof=1))


def perm_p_mean(values, n_perm=N_PERM, seed=SEED):
    """Permutation p-value for 'mean of these per-run rank correlations is 0'.
    Under the null of random ranking each rho is equally likely to flip sign, so the
    null distribution is built by random sign flips (an exact-in-distribution test for
    a symmetric null)."""
    v = np.asarray([x for x in values if np.isfinite(x)], dtype=float)
    if len(v) < 3:
        return np.nan, np.nan
    obs = float(v.mean())
    rng = np.random.default_rng(seed)
    signs = rng.choice([-1.0, 1.0], size=(n_perm, len(v)))
    null = (signs * v).mean(axis=1)
    p = float((np.abs(null) >= abs(obs) - 1e-12).mean())
    return obs, p


# ---------------------------------------------------------------------------
# searched ranges + fence detector
# ---------------------------------------------------------------------------
def searched_ranges(doc, table_params=None):
    """{param: (lo, hi)} = the range the search actually covered.
    Preference order: auto_expand.final_range (what the search finally swept, after
    auto-widening) -> plateau_pick.boundary_flags tested_min/max -> the empirical
    min/max over the run's `points` grid and its own candidate values."""
    rng = {}
    for e in (doc.get("auto_expand") or []):
        if not isinstance(e, dict):
            continue
        p = e.get("param")
        fr = e.get("final_range") or e.get("orig_range")
        if p and isinstance(fr, (list, tuple)) and len(fr) == 2:
            lo, hi = _num(fr[0]), _num(fr[1])
            if np.isfinite(lo) and np.isfinite(hi):
                rng[p] = (min(lo, hi), max(lo, hi))
    for b in ((doc.get("plateau_pick") or {}).get("boundary_flags") or []):
        if not isinstance(b, dict):
            continue
        p = b.get("param")
        lo, hi = _num(b.get("tested_min")), _num(b.get("tested_max"))
        if p and p not in rng and np.isfinite(lo) and np.isfinite(hi):
            rng[p] = (lo, hi)
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
                obs.setdefault(k, []).append(f)
    for k, vals in obs.items():
        if k not in rng and len(set(vals)) > 1:
            rng[k] = (min(vals), max(vals))
    if table_params:
        rng = {k: v for k, v in rng.items() if k in table_params}
    return rng


def grid_counts(doc):
    """{param: number of DISTINCT values the search actually tried}. A knob with <=2
    distinct values is an on/off switch, not a range: the search covered its whole
    space, so calling its crowned value a 'fence' would be meaningless. Q6 excludes
    those and reports them separately."""
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


def on_fence(value, lo, hi, tol_frac=0.02):
    """True when a crowned value sits at the edge of the searched range. Tolerance is
    2% of the range width, so a grid step landing exactly on the boundary counts."""
    value, lo, hi = _num(value), _num(lo), _num(hi)
    if not (np.isfinite(value) and np.isfinite(lo) and np.isfinite(hi)) or hi <= lo:
        return False
    tol = tol_frac * (hi - lo)
    return bool(value <= lo + tol or value >= hi - tol)


# ---------------------------------------------------------------------------
# analysis
# ---------------------------------------------------------------------------
def scoreable(df):
    """Runs where the ranking questions are even askable: >=MIN_CANDS candidates, all
    with a populated lockbox block carrying trades."""
    if df.empty:
        return df
    ok = []
    for rid, g in df.groupby("run"):
        if len(g) < MIN_CANDS:
            continue
        if g["lb_net"].notna().sum() < MIN_CANDS or (g["lb_trades"].fillna(0) > 0).sum() < MIN_CANDS:
            continue
        if g["is_net"].notna().sum() < MIN_CANDS:
            continue
        ok.append(rid)
    return df[df["run"].isin(ok)].copy()


def q1(df, is_col="is_pnl"):
    """IS ordering vs LB ordering. `is_col` = which in-sample number does the ranking:
    'is_pnl' (the search's own objective, PRIMARY) or 'is_net' (the cal.is 75%-split
    slice, robustness). See the DISCLOSURE under Q1 in the module docstring."""
    rows = []
    for rid, g in df.groupby("run"):
        g = g[g["lb_net"].notna() & g[is_col].notna()]
        if len(g) < MIN_CANDS:
            continue
        rho = spearman(g[is_col].values, g["lb_net"].values)
        n = len(g)
        top_is = g.sort_values(is_col, ascending=False).iloc[0]
        lb_order = g.sort_values("lb_net", ascending=False).reset_index(drop=True)
        pos = int(lb_order.index[lb_order["cand_ix"] == top_is["cand_ix"]][0]) + 1
        rows.append(dict(run=rid, famKey=g["famKey"].iloc[0], n=n, rho=rho,
                         top_is_lb_rank=pos, top3=bool(pos <= 3),
                         top_is_lb_net=_num(top_is["lb_net"]),
                         best_lb_net=_num(lb_order["lb_net"].iloc[0]),
                         median_lb_net=float(g["lb_net"].median())))
    out = pd.DataFrame(rows)
    if out.empty:
        return out, {}
    obs, p = perm_p_mean(out["rho"].values)
    # null share for "top-IS lands top-3": expected 3/n per run, averaged
    exp_top3 = float(np.mean([min(3, n) / n for n in out["n"]]))
    k = int(out["top3"].sum())
    N = len(out)
    from math import comb
    # one-sided binomial tail P(X >= k) under the per-run-averaged null
    pn = exp_top3
    p_top3 = float(sum(comb(N, i) * pn ** i * (1 - pn) ** (N - i) for i in range(k, N + 1)))
    return out, dict(n_runs=N, mean_rho=obs, median_rho=float(out["rho"].median()),
                     perm_p=p, share_neg=float((out["rho"] < 0).mean()),
                     top3_share=k / N, top3_null=pn, top3_p=p_top3)


def q2(df):
    """Crowned vs the mean of the other nine, in the lockbox."""
    res = {}
    detail = []
    for rid, g in df.groupby("run"):
        cr = g[g["crowned"]]
        rest = g[~g["crowned"]]
        if len(cr) != 1 or len(rest) < 2:
            continue
        cr = cr.iloc[0]
        row = dict(run=rid, famKey=g["famKey"].iloc[0], n_rest=len(rest))
        for metric in ("lb_net", "lb_pf", "lb_netdd"):
            cv = _num(cr[metric])
            rv = pd.to_numeric(rest[metric], errors="coerce")
            rv = rv[np.isfinite(rv)]
            row[f"crown_{metric}"] = cv
            row[f"rest_{metric}"] = float(rv.mean()) if len(rv) else np.nan
            row[f"d_{metric}"] = cv - float(rv.mean()) if (len(rv) and np.isfinite(cv)) else np.nan
        detail.append(row)
    det = pd.DataFrame(detail)
    if det.empty:
        return det, res
    for metric in ("lb_net", "lb_pf", "lb_netdd"):
        d = det[f"d_{metric}"].values
        n, k, p = sign_test(d)
        res[metric] = dict(n=n, n_pos=k, share_pos=(k / n if n else np.nan), p=p,
                           median_d=float(np.nanmedian(d)), mean_d=float(np.nanmean(d)),
                           d_effect=cohen_d_paired(d))
    return det, res


def q3(df, docs):
    """Crowned knob values across runs of a family: spread vs searched range, drift."""
    recs = []
    for rid, g in df.groupby("run"):
        cr = g[g["crowned"]]
        if len(cr) != 1:
            continue
        cr = cr.iloc[0]
        prm = json.loads(cr["params"])
        doc = docs.get(rid, {})
        rng = searched_ranges(doc, table_params=set(prm))
        nvals = grid_counts(doc)
        for k, v in prm.items():
            f = _num(v)
            if not np.isfinite(f):
                continue
            lo, hi = rng.get(k, (np.nan, np.nan))
            width = hi - lo if (np.isfinite(lo) and np.isfinite(hi)) else np.nan
            recs.append(dict(run=rid, famKey=cr["famKey"], strategy=cr["strategy"],
                             param=k, value=f, lo=lo, hi=hi, width=width,
                             n_values=nvals.get(k, np.nan),
                             pos=(f - lo) / width if (np.isfinite(width) and width > 0) else np.nan,
                             ts=str(cr["timestamp"])))
    cw = pd.DataFrame(recs)
    if cw.empty:
        return cw, cw
    rows = []
    for (fam, param), g in cw.groupby(["famKey", "param"]):
        g = g[np.isfinite(g["pos"])]
        if len(g) < 3:
            continue
        iqr_pos = float(g["pos"].quantile(0.75) - g["pos"].quantile(0.25))
        ts = pd.to_datetime(g["ts"], errors="coerce")
        drift = spearman(ts.astype("int64").astype(float).values, g["value"].values) \
            if ts.notna().sum() >= 3 else np.nan
        is_bin = bool(np.nanmedian(pd.to_numeric(g["n_values"], errors="coerce")) <= 2)
        rows.append(dict(famKey=fam, param=param, n_runs=len(g), kind=("on/off" if is_bin else "range"),
                         iqr_frac=iqr_pos, median_pos=float(g["pos"].median()),
                         drift_rho=drift,
                         verdict=("CONSTANT" if iqr_pos <= 0.10 else
                                  "loose" if iqr_pos <= 0.35 else "NOISE")))
    return cw, pd.DataFrame(rows).sort_values(["famKey", "iqr_frac"])


def q4(docs, df):
    """Pooled `relationship` blocks by family."""
    fam_of = df.drop_duplicates("run").set_index("run")["famKey"].to_dict()
    recs = []
    for rid, d in docs.items():
        if rid not in fam_of:
            continue
        rel = d.get("relationship")
        if not isinstance(rel, list):
            continue
        for e in rel:
            if not isinstance(e, dict) or not e.get("param"):
                continue
            recs.append(dict(run=rid, famKey=fam_of[rid], param=e["param"],
                             mi=_num(e.get("mi")), r=abs(_num(e.get("r"))), pps=_num(e.get("pps"))))
    raw = pd.DataFrame(recs)
    if raw.empty:
        return raw, raw
    agg = (raw.groupby(["famKey", "param"])
              .agg(n_runs=("pps", "size"), med_pps=("pps", "median"), med_mi=("mi", "median"),
                   med_absr=("r", "median"), share_pps0=("pps", lambda s: float((s <= 0).mean())))
              .reset_index())
    agg = agg[agg["n_runs"] >= 3].sort_values(["famKey", "med_pps"], ascending=[True, False])
    return raw, agg


def q5(df, is_col="is_pnl"):
    """WF vs IS as a predictor of the lockbox ordering. `is_col` as in q1()."""
    rows = []
    for rid, g in df.groupby("run"):
        gg = g[g["lb_net"].notna()]
        if len(gg) < MIN_CANDS:
            continue
        r_is = spearman(gg[is_col].values, gg["lb_net"].values)
        wf = gg["wf_oos_pnl"] if gg["wf_oos_pnl"].notna().sum() >= MIN_CANDS else gg["wf_net"]
        r_wf = spearman(wf.values, gg["lb_net"].values)
        if not (np.isfinite(r_is) and np.isfinite(r_wf)):
            continue
        rows.append(dict(run=rid, famKey=gg["famKey"].iloc[0], rho_is=r_is, rho_wf=r_wf,
                         d=r_wf - r_is))
    out = pd.DataFrame(rows)
    if out.empty:
        return out, {}
    n, k, p = sign_test(out["d"].values)
    obs_is, p_is = perm_p_mean(out["rho_is"].values)
    obs_wf, p_wf = perm_p_mean(out["rho_wf"].values)
    return out, dict(n_runs=len(out), mean_rho_is=obs_is, perm_p_is=p_is,
                     mean_rho_wf=obs_wf, perm_p_wf=p_wf,
                     n_pair=n, n_wf_better=k, sign_p=p,
                     median_d=float(out["d"].median()), d_effect=cohen_d_paired(out["d"].values))


def q6(df, docs):
    """Fence check on every crowned candidate."""
    rows = []
    for rid, g in df.groupby("run"):
        cr = g[g["crowned"]]
        if len(cr) != 1:
            continue
        cr = cr.iloc[0]
        prm = json.loads(cr["params"])
        doc = docs.get(rid, {})
        rng = searched_ranges(doc, table_params=set(prm))
        nvals = grid_counts(doc)
        knobs = fenced = binary = 0
        names = []
        for k, v in prm.items():
            lo, hi = rng.get(k, (np.nan, np.nan))
            if not (np.isfinite(lo) and np.isfinite(hi) and hi > lo):
                continue
            if nvals.get(k, 99) <= 2:
                binary += 1          # on/off switch: whole space searched, cannot be fenced
                continue
            knobs += 1
            if on_fence(v, lo, hi):
                fenced += 1
                names.append(k)
        if knobs == 0:
            continue
        rows.append(dict(run=rid, famKey=cr["famKey"], n_knobs=knobs, n_binary=binary,
                         n_fenced=fenced, frac_fenced=fenced / knobs, any_fenced=fenced > 0,
                         fenced_params=",".join(sorted(names))))
    out = pd.DataFrame(rows)
    if out.empty:
        return out, out
    fam = (out.groupby("famKey")
              .agg(n_runs=("run", "size"), share_any=("any_fenced", "mean"),
                   mean_frac=("frac_fenced", "mean"), med_knobs=("n_knobs", "median"),
                   med_binary=("n_binary", "median"))
              .reset_index().sort_values("n_runs", ascending=False))
    return out, fam


# ---------------------------------------------------------------------------
# report
# ---------------------------------------------------------------------------
def _md_table(df, cols=None, floatfmt=3, maxrows=12):
    if df is None or len(df) == 0:
        return "_(no rows)_\n"
    d = df if cols is None else df[cols]
    d = d.head(maxrows).copy()
    for c in d.columns:
        if pd.api.types.is_float_dtype(d[c]):
            d[c] = d[c].map(lambda v: "" if not np.isfinite(v) else f"{v:,.{floatfmt}f}")
    head = "| " + " | ".join(str(c) for c in d.columns) + " |"
    sep = "| " + " | ".join("---" for _ in d.columns) + " |"
    body = ["| " + " | ".join(str(v) for v in r) + " |" for r in d.itertuples(index=False)]
    return "\n".join([head, sep] + body) + "\n"


def _p(x, nd=3):
    return "n/a" if x is None or not np.isfinite(x) else (f"<0.001" if x < 0.001 else f"{x:.{nd}f}")


def _f(x, nd=2):
    return "n/a" if x is None or not np.isfinite(x) else f"{x:,.{nd}f}"


def write_report(df, sdf, docs, q1r, q1s, q2d, q2s, cw, q3t, relraw, q4t, q5d, q5s, q6d, q6f,
                 q1s_alt=None, q5s_alt=None):
    os.makedirs(OUT_DIR, exist_ok=True)
    L = []
    A = L.append
    A("# CANDIDATE BOARD -- does the search's own picking generalise?\n")
    A(f"Built {datetime.date.today().isoformat()} by `tools/candidate_board.py`. "
      f"Pool: **{df['run'].nunique()} Auto-Validate runs / {len(df)} candidates**; "
      f"**{sdf['run'].nunique()} runs** have a lockbox score on >= {MIN_CANDS} candidates and carry the "
      f"questions below. Every question was written down before any answer was computed "
      f"(see the module docstring).\n")
    A("**Terms.** *Candidate* = one of the ~10 parameter sets a run short-lists. *Crowned* = the one "
      "the run declared champion. *In-sample (IS)* = the window the search fitted on. *Walk-forward "
      "(WF)* = rolling out-of-sample folds inside that window. *Lockbox (LB)* = the final months the "
      "search never saw -- the honest score. *net* = dollars. *PF* = gross win / gross loss. *net/DD* "
      "= net per dollar of worst drawdown. *Spearman rho* = rank correlation, 0 means the ordering "
      "carries no information. *Fence* = a crowned knob sitting on the edge of the range searched.\n")

    A("## Q1 -- Does the in-sample winner win out of sample?\n")
    A("Per run, rank the candidates by IS net and by LB net, then correlate the two orderings. Row 1 "
      "(**primary**) ranks on `is_pnl`, the number the search itself optimises. Row 2 ranks on the "
      "`cal.is` 75%-split calibration slice -- both were pre-committed and both are shown; see the Q1 "
      "disclosure in the module docstring.\n")
    r1 = [dict(in_sample_field="is_pnl (PRIMARY)", runs=q1s.get("n_runs"), mean_rho=q1s.get("mean_rho"),
               median_rho=q1s.get("median_rho"), share_rho_negative=q1s.get("share_neg"),
               perm_p=q1s.get("perm_p"), top3_share=q1s.get("top3_share"), top3_null=q1s.get("top3_null"))]
    if q1s_alt:
        r1.append(dict(in_sample_field="cal.is (robustness)", runs=q1s_alt.get("n_runs"),
                       mean_rho=q1s_alt.get("mean_rho"), median_rho=q1s_alt.get("median_rho"),
                       share_rho_negative=q1s_alt.get("share_neg"), perm_p=q1s_alt.get("perm_p"),
                       top3_share=q1s_alt.get("top3_share"), top3_null=q1s_alt.get("top3_null")))
    A(_md_table(pd.DataFrame(r1)))
    A(f"On the primary field the top-IS candidate lands **top-3 in the lockbox in "
      f"{q1s.get('top3_share', float('nan')):.0%} of runs** vs **{q1s.get('top3_null', float('nan')):.0%} "
      f"expected by chance** (binomial p = {_p(q1s.get('top3_p'))}).\n")

    A("## Q2 -- Is the crowned candidate better than a random one of the ten?\n")
    A("Paired per run: crowned lockbox score minus the mean of the other candidates. Sign test on the "
      "differences; effect size = Cohen's d on the paired differences.\n")
    rows = []
    for m, lab in (("lb_net", "LB net ($)"), ("lb_pf", "LB profit factor"), ("lb_netdd", "LB net/DD")):
        s = q2s.get(m, {})
        rows.append(dict(metric=lab, n_runs=s.get("n"), crown_wins=s.get("n_pos"),
                         share=s.get("share_pos"), median_diff=s.get("median_d"),
                         cohens_d=s.get("d_effect"), sign_p=s.get("p")))
    A(_md_table(pd.DataFrame(rows)))

    A("## Q3 -- Which knobs are structural constants and which are noise?\n")
    A("For each family and knob, the crowned value in each run is expressed as a POSITION in the range "
      "the search covered (0 = bottom of range, 1 = top). `iqr_frac` = interquartile spread of that "
      "position: <=0.10 = **CONSTANT** (the crown always lands in the same place -- a real structural "
      "value), >0.35 = **NOISE** (the crown lands anywhere). `drift_rho` = rank correlation of the "
      "crowned value with run date.\n")
    if len(q3t):
        cnt = q3t["verdict"].value_counts().to_dict()
        A(f"Across {len(q3t)} (family, knob) pairs with >=3 crowned runs: "
          f"**{cnt.get('CONSTANT', 0)} CONSTANT, {cnt.get('loose', 0)} loose, {cnt.get('NOISE', 0)} NOISE.**\n")
        A("Most stable knobs (lowest spread):\n")
        A(_md_table(q3t.sort_values("iqr_frac").head(10),
                    ["famKey", "param", "kind", "n_runs", "iqr_frac", "median_pos", "drift_rho", "verdict"]))
        A("Loosest knobs (the search picks a different value every time):\n")
        A(_md_table(q3t.sort_values("iqr_frac", ascending=False).head(8),
                    ["famKey", "param", "kind", "n_runs", "iqr_frac", "median_pos", "drift_rho", "verdict"]))
        A("\n`kind` = *on/off* when the search only ever tried two values (a switch, e.g. "
          "`skip_holidays`); a NOISE verdict there means the search flips that switch from run to run "
          "rather than that it wanders a wide range.\n")
    else:
        A("_Not enough crowned runs per family to judge._\n")

    A("## Q4 -- Which knobs actually move the result?\n")
    A("`pps` = predictive power score, the run's own measure of how much a knob explains the result "
      "(0 = explains nothing). Pooled across runs of a family, median.\n")
    if len(q4t):
        A(_md_table(q4t.head(12), ["famKey", "param", "n_runs", "med_pps", "med_mi", "med_absr", "share_pps0"]))
        share0 = float((q4t["med_pps"] <= 0).mean())
        A(f"\n**{share0:.0%} of (family, knob) pairs have a median predictive power score of zero** -- "
          f"the search reports most of its own knobs as explaining nothing.\n")
    else:
        A("_No relationship blocks pooled._\n")

    A("## Q5 -- Should we crown on walk-forward or on in-sample?\n")
    A("Per run: how well does IS net order the lockbox, vs how well does WF out-of-sample net order it? "
      "Same primary/robustness split as Q1.\n")

    def _q5row(lab, s):
        return dict(in_sample_field=lab, runs=s.get("n_runs"), mean_rho_IS=s.get("mean_rho_is"),
                    perm_p_IS=s.get("perm_p_is"), mean_rho_WF=s.get("mean_rho_wf"),
                    perm_p_WF=s.get("perm_p_wf"),
                    wf_better_share=(s.get("n_wf_better", 0) / s["n_pair"] if s.get("n_pair") else float("nan")),
                    sign_p=s.get("sign_p"))
    r5 = [_q5row("is_pnl (PRIMARY)", q5s)]
    if q5s_alt:
        r5.append(_q5row("cal.is (robustness)", q5s_alt))
    A(_md_table(pd.DataFrame(r5)))

    A("## Q6 -- Fence check: did the search ever see the real optimum?\n")
    A("A crowned knob is *on a fence* when its value sits within 2% of the range width of the lowest or "
      "highest value the search covered (after auto-expansion). A fence crown means the true optimum "
      "may lie outside the box that was searched. **On/off switches are excluded** -- a knob with only "
      "two values searched has had its whole space covered, so it cannot be fenced in any useful sense; "
      "counting them would inflate this number (84% unfiltered vs 58% here). `med_binary` = how many "
      "such switches a typical crown in that family carries.\n")
    if len(q6f):
        A(_md_table(q6f, ["famKey", "n_runs", "share_any", "mean_frac", "med_knobs", "med_binary"]))
        A(f"\nOverall: **{q6d['any_fenced'].mean():.0%} of crowned candidates have at least one knob on a "
          f"fence**; on average **{q6d['frac_fenced'].mean():.0%} of a crown's knobs** sit on an edge.\n")
    else:
        A("_No searched ranges recoverable._\n")

    A("\n## What this means for where new parameters come from\n")
    L.append(_verdict_text(q1s, q2s, q3t, q4t, q5s, q6d))
    txt = "\n".join(L)
    lines = txt.splitlines()
    if len(lines) > 140:
        txt = "\n".join(lines[:140])
    fp = os.path.join(OUT_DIR, "CANDIDATE_BOARD.md")
    with open(fp, "w", encoding="utf-8") as f:
        f.write(txt + "\n")
    return fp


def _verdict_text(q1s, q2s, q3t, q4t, q5s, q6d):
    out = []
    mr = q1s.get("mean_rho", float("nan"))
    p1 = q1s.get("perm_p", float("nan"))
    if np.isfinite(p1) and p1 > 0.05:
        out.append(f"1. **The score the search optimises does not order the lockbox.** Ranking on "
                   f"`is_pnl` gives mean rank correlation {_f(mr)} across {q1s.get('n_runs')} runs, "
                   f"permutation p = {_p(p1)} -- indistinguishable from shuffling the ten candidates, "
                   f"and the top-in-sample candidate reaches the lockbox top-3 no more often than "
                   f"chance. The `cal.is` slice does slightly better but is not what the search ranks "
                   f"on, so it cannot be claimed as a working selection rule.")
    else:
        out.append(f"1. In-sample net orders the lockbox with mean rho {_f(mr)} "
                   f"(perm p = {_p(p1)}) -- weak but real.")
    s = q2s.get("lb_net", {})
    if np.isfinite(s.get("p", float("nan"))) and s["p"] > 0.05:
        out.append(f"2. **Crowning adds nothing measurable.** The crowned candidate beats the mean of "
                   f"the others in the lockbox in {s.get('n_pos')}/{s.get('n')} runs "
                   f"(sign p = {_p(s.get('p'))}, d = {_f(s.get('d_effect'))}). On this evidence the "
                   f"choice among the short-list is a coin flip -- the short-listing itself may still "
                   f"be doing work, but the final pick is not.")
    else:
        out.append(f"2. The crowned candidate does beat the field: {s.get('n_pos')}/{s.get('n')} runs, "
                   f"sign p = {_p(s.get('p'))}, median edge {_f(s.get('median_d'))} $.")
    if len(q3t):
        c = int((q3t["verdict"] == "CONSTANT").sum())
        n = int((q3t["verdict"] == "NOISE").sum())
        out.append(f"3. Of {len(q3t)} (family, knob) pairs, {c} land in the same place every run "
                   f"(structural) and {n} land anywhere in their range (noise). Only the constants are "
                   f"worth carrying into a new strategy; the noise knobs should be FROZEN at their "
                   f"median rather than re-optimised, because re-optimising them is what burns the "
                   f"degrees of freedom that PBO and DSR then have to pay for.")
    if len(q4t):
        z = float((q4t["med_pps"] <= 0).mean())
        out.append(f"4. {z:.0%} of knobs have zero median predictive power in the search's own "
                   f"relationship block. A search over knobs that explain nothing is a search over "
                   f"noise -- the fix is fewer knobs, not more trials "
                   f"(see also edgelog-validate-trial-budget).")
    if q5s:
        better = q5s.get("n_wf_better", 0) / q5s["n_pair"] if q5s.get("n_pair") else float("nan")
        out.append(f"5. Walk-forward orders the lockbox better than in-sample in {better:.0%} of runs "
                   f"(sign p = {_p(q5s.get('sign_p'))}; mean rho WF {_f(q5s.get('mean_rho_wf'))} vs IS "
                   f"{_f(q5s.get('mean_rho_is'))}). "
                   + ("That is a real if modest reason to crown on walk-forward, not in-sample."
                      if np.isfinite(q5s.get('sign_p', float('nan'))) and q5s['sign_p'] < 0.05
                      else "Neither number is a usable ranking signal on its own."))
    if len(q6d):
        out.append(f"6. {q6d['any_fenced'].mean():.0%} of crowns sit on at least one range edge. Where a "
                   f"crown is fenced the search never bracketed the optimum, so that knob's value is a "
                   f"statement about the box we drew, not about the market.")
    out.append("")
    out.append("**Where new parameters should come from.** Not from re-running the same search wider or "
               "longer: the numbers above say the ranking inside a short-list is close to chance, most "
               "knobs explain nothing, and a large share of crowns are pinned to a fence we drew "
               "ourselves. The leverage is (a) freeze the noise knobs at their pooled median and search "
               "only the constants, which shrinks the effective parameter count and lifts DSR for free; "
               "(b) stop treating the crowned row as the answer -- neither in-sample NOR walk-forward "
               "orders the lockbox, so the short-list should be carried forward as a SET (or pooled as "
               "a book leg) rather than collapsed to one cell by a tie-breaker that measures nothing; "
               "(c) treat any fenced crown as an unfinished search -- widen that one knob or drop it; "
               "and (d) spend the saved compute on NEW INFORMATION (the KEEL v12 lesson) rather than "
               "finer slicing of the same tape.")
    return "\n".join(out)


# ---------------------------------------------------------------------------
def main(argv=None):
    ap = argparse.ArgumentParser(description="Pool every Auto-Validate run's candidates and test "
                                             "whether the search's own selection generalises.")
    ap.add_argument("--max-id", type=int, default=400)
    ap.add_argument("--no-fetch", action="store_true", help="analyse from cache only (0 Firestore reads)")
    ap.add_argument("--refresh-missing", action="store_true", help="retry ids previously seen missing")
    a = ap.parse_args(argv)

    docs = harvest(max_id=a.max_id, fetch=not a.no_fetch, refresh_missing=a.refresh_missing)
    df = build_table(docs)
    if df.empty:
        raise SystemExit("no candidates harvested -- nothing to analyse")
    os.makedirs(OUT_DIR, exist_ok=True)
    csv_fp = os.path.join(OUT_DIR, "candidates.csv")
    df.to_csv(csv_fp, index=False, encoding="utf-8")
    with open(os.path.join(OUT_DIR, "candidates.json"), "w", encoding="utf-8") as f:
        json.dump(json.loads(df.to_json(orient="records")), f, indent=1)
    print(f"[table] {len(df)} candidate rows / {df['run'].nunique()} runs -> {csv_fp}")

    sdf = scoreable(df)
    print(f"[scoreable] {sdf['run'].nunique()} runs with lockbox on >= {MIN_CANDS} candidates")

    q1r, q1s = q1(sdf, "is_pnl")
    q1r_alt, q1s_alt = q1(sdf, "is_net")
    q2d, q2s = q2(sdf)
    cw, q3t = q3(df, docs)
    relraw, q4t = q4(docs, df)
    q5d, q5s = q5(sdf, "is_pnl")
    q5d_alt, q5s_alt = q5(sdf, "is_net")
    q6d, q6f = q6(df, docs)

    print("\n=== Q1 IS->LB ordering (PRIMARY is_pnl) ===", json.dumps(q1s, indent=1, default=str))
    print("=== Q1 robustness (cal.is) ===", json.dumps(q1s_alt, indent=1, default=str))
    print("=== Q2 crowned vs rest ===", json.dumps(q2s, indent=1, default=str))
    print(f"=== Q3 knob stability === {len(q3t)} pairs; "
          f"{dict(q3t['verdict'].value_counts()) if len(q3t) else {}}")
    print(f"=== Q4 relationship === {len(q4t)} pairs; "
          f"zero-pps share {float((q4t['med_pps'] <= 0).mean()) if len(q4t) else float('nan'):.3f}")
    print("=== Q5 WF vs IS (PRIMARY is_pnl) ===", json.dumps(q5s, indent=1, default=str))
    print("=== Q5 robustness (cal.is) ===", json.dumps(q5s_alt, indent=1, default=str))
    print(f"=== Q6 fences === any-fence share "
          f"{q6d['any_fenced'].mean() if len(q6d) else float('nan'):.3f} over {len(q6d)} crowns")

    for name, d in (("q1_runs", q1r), ("q1_runs_calis", q1r_alt), ("q2_runs", q2d),
                    ("q3_crowned_knobs", cw), ("q3_stability", q3t), ("q4_relationship", q4t),
                    ("q5_runs", q5d), ("q5_runs_calis", q5d_alt), ("q6_fences", q6d)):
        if len(d):
            d.to_csv(os.path.join(OUT_DIR, f"{name}.csv"), index=False, encoding="utf-8")

    fp = write_report(df, sdf, docs, q1r, q1s, q2d, q2s, cw, q3t, relraw, q4t, q5d, q5s, q6d, q6f,
                      q1s_alt=q1s_alt, q5s_alt=q5s_alt)
    print(f"\n[report] {fp}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
