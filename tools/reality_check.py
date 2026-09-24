"""
SEARCH-ADJUSTED P-VALUE FOR THE CROWN (RESEARCH.md item 3)

THE QUESTION. A validate crowns the best of ten finalists on their walk-forward folds. The
best of ten always looks good - that is what "best of ten" means. So: is the crowned
config's walk-forward record better than the best of ten near-identical configs would look
by luck alone? A plain p-value on the winner cannot answer that, because the winner was
chosen for being the winner.

THE TEST. White's Reality Check (2000), the same shape Hansen (2005) refined:
  statistic  V = max over configs of sqrt(n) x (that config's mean fold net)
  null       no config has a positive expected fold net
  bootstrap  resample the folds with replacement; inside each resample, RE-CENTRE every
             config on its own observed mean, so the null holds by construction; recompute
             the max; p = share of bootstrap maxima at or above V.
Because every config is re-centred, the test asks only whether the BEST result is larger
than the best a no-edge search would have produced with the same number of configs and the
same fold-to-fold noise.

WHY IT ONLY BECAME POSSIBLE NOW. The per-fold rows under each finalist were not saved until
2026-09-09; before that a run stored a fold COUNT and a TOTAL, which cannot be resampled.
The item was marked BLOCKED on data for that reason. 23 of the last 40 runs now carry them.

READ IT WITH THE POWER IN MIND, and this is stated before any result is looked at: eight
folds is a tiny sample. A p-value near 1 does NOT mean the strategy is worthless - it means
this test cannot separate it from luck at this fold count. Treat a small p as evidence and a
large p as "the walk-forward record alone does not carry the crown", never as a verdict.

    python tools/reality_check.py            # every run that carries per-fold rows
    python tools/reality_check.py --runs 406,405,410
"""
import argparse
import json
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

UID = "IO0K35JpLIcH9YK4C0pMNYUzZOM2"
CACHE = r"C:\EdgeLog\_anatomy_cache\runs"
N_BOOT = 20000
SEED = 42


def _client():
    import firebase_admin
    from firebase_admin import credentials, firestore
    if not firebase_admin._apps:
        firebase_admin.initialize_app(credentials.Certificate("serviceAccount.json"))
    return firestore.client().collection("users").document(UID)


def recent_runs(limit=60):
    from firebase_admin import firestore
    u = _client()
    out = []
    for snap in (u.collection("runs")
                 .order_by("timestamp", direction=firestore.Query.DESCENDING)
                 .limit(limit).stream()):
        out.append((snap.id, snap.to_dict() or {}))
    return out


def one_run(rid):
    os.makedirs(CACHE, exist_ok=True)
    p = os.path.join(CACHE, "%s.json" % rid)
    if os.path.exists(p):
        try:
            return json.load(open(p, encoding="utf-8"))
        except Exception:
            pass
    d = _client().collection("runs").document(str(rid)).get().to_dict() or {}
    return d


def fold_matrix(doc, groups=("candidates",)):
    """configs x folds of out-of-sample net, plus which row was crowned.

    `groups` picks which saved blocks count as candidates. Finalists alone is the
    choice the crowning rule actually made; adding the robust rows and the sampled
    cloud widens it to configs drawn from across the search, a harsher multiplicity.
    """
    sel = doc.get("selection")
    if not isinstance(sel, dict):
        return None, None, None
    rows = [c for g in groups for c in (sel.get(g) or [])
            if isinstance(c, dict) and c.get("folds")]
    if len(rows) < 2:
        return None, None, None
    n = min(len(c["folds"]) for c in rows)
    if n < 4:
        return None, None, None
    M = np.array([[float(f.get("net") or 0.0) for f in c["folds"][:n]] for c in rows])
    crowned = next((i for i, c in enumerate(rows) if c.get("crowned")), None)
    if crowned is None:                       # fall back to the best walk-forward total
        crowned = int(np.argmax([float(c.get("wf_oos_pnl") or 0) for c in rows]))
    return M, crowned, rows


def reality_check(M, n_boot=N_BOOT, seed=SEED):
    """White's Reality Check p-value for max mean fold net over configs."""
    rng = np.random.default_rng(seed)
    N, T = M.shape
    mu = M.mean(axis=1)
    V = float(np.sqrt(T) * mu.max())
    C = M - mu[:, None]                        # re-centred: the null holds by construction
    idx = rng.integers(0, T, size=(n_boot, T))
    boot = np.sqrt(T) * C[:, idx].mean(axis=2).max(axis=0)   # N x n_boot -> max per draw
    p = float((boot >= V).mean())
    return dict(V=V, p=p, n_configs=int(N), n_folds=int(T),
                best_mean=float(mu.max()), median_mean=float(np.median(mu)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", default="", help="comma list; default = every recent run that has the rows")
    ap.add_argument("--limit", type=int, default=60)
    ap.add_argument("--out", default="docs/candidates/REALITY_CHECK.md")
    a = ap.parse_args()

    if a.runs:
        docs = [(r.strip(), one_run(r.strip())) for r in a.runs.split(",") if r.strip()]
    else:
        docs = recent_runs(a.limit)

    results = []
    for rid, d in docs:
        M, crowned, rows = fold_matrix(d)
        if M is None:
            continue
        rc = reality_check(M)
        mu = M.mean(axis=1)
        rank = int((mu > mu[crowned]).sum()) + 1          # 1 = best of the finalists
        # the same test against the WIDER pool the search actually looked at
        W, _wc, _wr = fold_matrix(d, ("candidates", "robust", "oos_sample"))
        wide = reality_check(W) if (W is not None and W.shape[0] > M.shape[0]) else None
        v = d.get("validate") or {}
        results.append(dict(run=rid, fam=d.get("famKey"), verdict=v.get("verdict"),
                            crown_rank=rank,
                            wide_n=(int(W.shape[0]) if W is not None else 0),
                            wide_p=(wide["p"] if wide else None), **rc))

    if not results:
        print("no run carried per-fold candidate rows")
        return
    results.sort(key=lambda r: str(r["run"]))

    lines = ["# SEARCH-ADJUSTED P-VALUE FOR THE CROWN (RESEARCH.md item 3)", "",
             "White's Reality Check over each run's ten finalists and their walk-forward folds.",
             "A small p means the best finalist beat what a no-edge search of the same size and",
             "the same fold noise would have produced. **Eight folds is a tiny sample: a large p",
             "means this test cannot separate the crown from luck, not that the strategy is bad.**",
             "", "Driver `tools/reality_check.py` (%d bootstrap draws, seed %d)." % (N_BOOT, SEED),
             "",
             "| Run | Family | Verdict | Finalists | Folds | Crown's rank | Best mean fold net | p (finalists) | p (wider pool) |",
             "|---|---|---|---|---|---|---|---|---|"]
    for r in results:
        pstr = ("%.4f" % r["p"]) if r["p"] >= 0.0001 else "<0.0001"
        wp = r.get("wide_p")
        wstr = "n/a" if wp is None else (("%.4f" % wp) if wp >= 0.0001 else "<0.0001")
        if wp is not None:
            wstr += " (%d cfg)" % r["wide_n"]
        lines.append("| #{} | {} | {} | {} | {} | {} of {} | {:,.0f} | {} | {} |".format(
            r["run"], r["fam"], r["verdict"], r["n_configs"], r["n_folds"],
            r["crown_rank"], r["n_configs"], r["best_mean"], pstr, wstr))
    ps = np.array([r["p"] for r in results])
    wps = np.array([r["wide_p"] for r in results if r.get("wide_p") is not None])
    lines += ["", "**Summary.** %d runs tested. Against the finalists: median p %.3f, %d "
              "below 0.05. Against the wider pool (%d runs have one): median p %.3f, %d "
              "below 0.05."
              % (len(ps), float(np.median(ps)), int((ps < 0.05).sum()), len(wps),
                 float(np.median(wps)) if len(wps) else float("nan"),
                 int((wps < 0.05).sum()) if len(wps) else 0),
              "", "**Read this before quoting it.** The finalists trade the same tape with "
              "near-identical settings, so their fold results are highly correlated, and a "
              "multiplicity adjustment over correlated candidates is WEAK by construction. "
              "That is why nearly every run clears the bar: the test is closer to asking "
              "whether the best finalist's mean fold result is large next to fold-to-fold "
              "noise than to asking whether the SEARCH found something. It adjusts for ten "
              "when the search looked at nine hundred, and not at all for how many rounds a "
              "family has had. Item 1 is the test that answers that; this is not a substitute.",
              "", "The crown's rank column is where the crowned config sits among its own",
              "finalists on mean fold net - a rank far from 1 means the crowning rule chose",
              "something other than the walk-forward leader, which it is entitled to do",
              "(it ranks on the fold TOTAL and the count of folds held, not the mean)."]
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    open(a.out, "w", encoding="utf-8").write("\n".join(lines) + "\n")
    print("\n".join(lines))
    print("\nwrote", a.out)


if __name__ == "__main__":
    main()
