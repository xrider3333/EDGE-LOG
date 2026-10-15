"""DECAY r1 harness (DISC, 2026-10-15) - see docs/PREREG_disc_decay_r1_2026-10-15.md (its LF sha256 is checked first).

Reads the saved run docs (Firestore `runs`, read-only), builds the per-run Sharpe ratios IS / WF / LB, and prints:
the discount ratios (median, family-cluster bootstrap interval, slope through the origin), family medians, the
three-predictor model with family fixed effects (HC1 t and leave-one-family-out signs), and the forward haircut per
book / live leg. Writes nothing but --out.

    python tools/disc_decay_r1.py [--out C:\\EdgeLog\\_anatomy_cache\\decay_r1]
"""
import argparse
import hashlib
import json
import math
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PREREG = os.path.join(ROOT, "docs", "PREREG_disc_decay_r1_2026-10-15.md")
VOID = {369, 428, 455}
LEGS = {234: "ORB #234", 314: "ORB #314", 335: "ENGU-Q #335", 459: "TTM #459", 422: "NOISE #422", 382: "NOISE #382", 424: "DIP #424"}
WIN = (-2.0, 3.0)
SEED = 20261015


def lf_sha256(path):
    return hashlib.sha256(open(path, "rb").read().replace(b"\r\n", b"\n")).hexdigest()


def pull(cred, uid):
    import firebase_admin
    from firebase_admin import credentials, firestore
    if not firebase_admin._apps:
        firebase_admin.initialize_app(credentials.Certificate(cred))
    col = firestore.client().collection("users").document(uid).collection("runs")
    fields = ["famKey", "note", "strategy", "timestamp", "validate.is_sharpe", "validate.is_trades", "validate.trades_per_param",
              "validate.n_params", "validate.plateau", "validate.wf_oos.sharpe", "validate.wf_oos.trades", "validate.wf_oos.net",
              "validate.wf_oos.max_drawdown", "validate.wf_oos.years", "validate.lockbox.sharpe", "validate.lockbox.trades"]
    rows = []
    for doc in col.select(fields).stream():
        r = doc.to_dict() or {}
        v = r.get("validate") or {}
        if not v:
            continue
        wf, lb, pl = v.get("wf_oos") or {}, v.get("lockbox") or {}, v.get("plateau") or {}
        try:
            run = int(doc.id)
        except ValueError:
            continue
        rows.append(dict(run=run, fam=r.get("famKey"), note=str(r.get("note") or ""), strategy=r.get("strategy"),
                         ts=r.get("timestamp"), sr_is=v.get("is_sharpe"), is_trades=v.get("is_trades") or 0,
                         tpp=v.get("trades_per_param"), n_params=v.get("n_params"),
                         plateau=(pl.get("good") / pl.get("tot")) if pl.get("tot") else None,
                         sr_wf=wf.get("sharpe"), wf_trades=wf.get("trades") or 0, wf_net=wf.get("net"),
                         wf_dd=wf.get("max_drawdown"), wf_years=wf.get("years"),
                         sr_lb=lb.get("sharpe"), lb_trades=lb.get("trades") or 0))
    return pd.DataFrame(rows)


def sample(df):
    d = df[df.sr_is.notna() & df.sr_wf.notna() & df.sr_lb.notna() & (df.is_trades >= 100) & (df.wf_trades >= 100)
           & (df.lb_trades >= 30) & ~df.run.isin(VOID) & ~df.note.str.contains("VOID")].copy()
    for c in ("sr_is", "sr_wf", "sr_lb", "tpp", "plateau"):
        d[c] = pd.to_numeric(d[c], errors="coerce")
    d["q_lb"] = (d.sr_lb / d.sr_is).clip(*WIN)
    d["q_wf"] = (d.sr_wf / d.sr_is).clip(*WIN)
    d["h"] = np.where(d.sr_wf >= 0.3, (d.sr_lb / d.sr_wf).clip(*WIN), np.nan)
    return d


def cluster_boot(d, col, stat, n=2000, seed=SEED):
    rng = np.random.default_rng(seed)
    fams = d.fam.unique(); groups = {f: d[d.fam == f][col].dropna().to_numpy() for f in fams}
    out = []
    for _ in range(n):
        pick = rng.choice(fams, len(fams), replace=True)
        x = np.concatenate([rng.choice(groups[f], len(groups[f]), replace=True) for f in pick if len(groups[f])])
        out.append(stat(x))
    return np.percentile(out, 5), np.percentile(out, 95)


def slope0(x, y):
    return float((x * y).sum() / (x * x).sum())


def ols_fe(d, y, xs):
    """OLS of y on standardised xs + family dummies; HC1 t-stats for xs."""
    z = d.dropna(subset=[y] + xs).copy()
    X = np.column_stack([(z[c] - z[c].mean()) / z[c].std(ddof=0) for c in xs])
    F = pd.get_dummies(z.fam, drop_first=False).to_numpy(float)
    A = np.column_stack([X, F]); Y = z[y].to_numpy(float)
    beta, *_ = np.linalg.lstsq(A, Y, rcond=None)
    e = Y - A @ beta; n, k = A.shape
    XtXi = np.linalg.pinv(A.T @ A)
    V = XtXi @ (A.T * (e ** 2)) @ A @ XtXi * n / max(n - k, 1)
    se = np.sqrt(np.diag(V))
    return {c: (float(beta[i]), float(beta[i] / se[i]) if se[i] > 0 else float("nan")) for i, c in enumerate(xs)}, len(z)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=r"C:\EdgeLog\_anatomy_cache\decay_r1")
    ap.add_argument("--cred", default=os.path.join(ROOT, "serviceAccount.json"))
    ap.add_argument("--uid", default="IO0K35JpLIcH9YK4C0pMNYUzZOM2")
    ap.add_argument("--expect-sha", default=None)
    a = ap.parse_args(argv)
    sha = lf_sha256(PREREG)
    print("prereg LF sha256", sha)
    if a.expect_sha and a.expect_sha != sha:
        sys.exit("PREREG HASH MISMATCH - stopping")
    raw = pull(a.cred, a.uid)
    d0 = sample(raw)
    os.makedirs(a.out, exist_ok=True)
    d0.to_csv(os.path.join(a.out, "runs_sample.csv"), index=False)
    res = {"prereg_sha256": sha, "n_all": int(len(d0))}
    for lab, d in (("PRIMARY SR_IS>=0.3", d0[d0.sr_is >= 0.3]), ("SENSITIVITY SR_IS>0", d0[d0.sr_is > 0])):
        print("\n==", lab, "| runs", len(d), "| families", d.fam.nunique(), d.fam.value_counts().to_dict())
        blk = {"n": int(len(d))}
        for col, nm in (("q_lb", "Q1 q_LB = SR_LB/SR_IS"), ("q_wf", "Q2 q_WF = SR_WF/SR_IS"), ("h", "Q3 h = SR_LB/SR_WF (SR_WF>=0.3)")):
            x = d[col].dropna()
            lo, hi = cluster_boot(d, col, np.median)
            print("%-34s n %3d  median %.2f  90%% [%.2f, %.2f]  mean %.2f" % (nm, len(x), x.median(), lo, hi, x.mean()))
            blk[col] = {"n": int(len(x)), "median": float(x.median()), "lo90": float(lo), "hi90": float(hi), "mean": float(x.mean())}
        s_lb, s_wf = slope0(d.sr_is, d.sr_lb.clip(-5, 10)), slope0(d.sr_is, d.sr_wf.clip(-5, 10))
        print("slope through origin: SR_LB on SR_IS %.2f | SR_WF on SR_IS %.2f  (paper: 0.57)" % (s_lb, s_wf))
        blk["slope_lb"], blk["slope_wf"] = s_lb, s_wf
        fm = d.groupby("fam")[["q_lb", "q_wf", "h"]].median().round(2); fm["n"] = d.groupby("fam").size()
        print(fm.to_string()); blk["family_medians"] = fm.reset_index().to_dict("records")
        res[lab] = blk
    # predictors (primary sample)
    d = d0[d0.sr_is >= 0.3].copy()
    d["log_tpp"] = np.log(pd.to_numeric(d.tpp, errors="coerce").clip(lower=1e-9))
    xs = ["sr_is", "log_tpp", "plateau"]; sign = {"sr_is": -1, "log_tpp": 1, "plateau": 1}
    print("\n== PREDICTORS (family fixed effects, HC1)")
    pred = {}
    for y in ("q_lb", "q_wf"):
        full, n = ols_fe(d, y, xs)
        loo = {c: [] for c in xs}
        for f in d.fam.unique():
            b, _ = ols_fe(d[d.fam != f], y, xs)
            for c in xs:
                loo[c].append(b[c][0])
        for c in xs:
            b, t = full[c]
            same = all(np.sign(v) == np.sign(b) for v in loo[c] if np.isfinite(v))
            holds = (t * sign[c] >= 2) and same
            print("%-5s %-8s beta %+.3f  t %+.2f  LOFO same sign %s  -> %s" % (y, c, b, t, same, "HOLDS" if holds else "does not hold"))
            pred["%s|%s" % (y, c)] = {"beta": b, "t": t, "lofo_same_sign": bool(same), "holds": bool(holds), "n": n}
    res["predictors"] = pred
    # date, descriptive only
    try:
        d["date"] = pd.to_datetime(d.ts, errors="coerce", utc=True)
        print("\nrun dates %s .. %s; corr(date, q_lb) %.2f (descriptive only)" % (d.date.min(), d.date.max(),
              d.q_lb.corr(d.date.astype("int64").astype(float))))
    except Exception as e:
        print("date read skipped:", e)
    # forward haircut per leg
    print("\n== FORWARD HAIRCUT per book / live leg (family median h; house median if the family has < 8 runs)")
    prim = d0[d0.sr_is >= 0.3]
    house_h = float(prim.h.median()); hc = {}
    for run, lab in LEGS.items():
        rr = raw[raw.run == run]
        fam = rr.fam.iloc[0] if len(rr) else None
        fh = prim[prim.fam == fam].h.dropna()
        h = float(fh.median()) if len(fh) >= 8 else house_h
        roc = None
        if len(rr) and rr.wf_dd.notna().iloc[0] and rr.wf_years.notna().iloc[0] and abs(rr.wf_dd.iloc[0]) > 0:
            roc = 30.0 * (rr.wf_net.iloc[0] / rr.wf_years.iloc[0]) / abs(rr.wf_dd.iloc[0])
        print("%-12s family %-7s h %.2f (%s)  WF ROC@30k (stored WF curve) %s -> expected forward %s | DD5 - | DD%% - | Sortino -" % (
            lab, fam, h, "family" if len(fh) >= 8 else "house", "%.1f" % roc if roc is not None else "n/a",
            "%.1f" % (roc * h) if roc is not None else "n/a"))
        hc[lab] = {"family": fam, "h": h, "source": "family" if len(fh) >= 8 else "house", "wf_roc": roc,
                   "fwd_roc": (roc * h) if roc is not None else None}
    res["haircut"] = hc
    med = res["PRIMARY SR_IS>=0.3"]["q_lb"]["median"]
    verdict = "HOUSE DECAY LIKE THE PAPER" if 0.35 <= med <= 0.75 else ("LESS DECAY" if med > 0.75 else "MORE DECAY")
    print("\nVERDICT:", verdict, "(median q_LB %.2f; paper 0.55)" % med)
    res["verdict"] = verdict
    json.dump(res, open(os.path.join(a.out, "decay_r1_result.json"), "w"), indent=1, default=str)


if __name__ == "__main__":
    main()
