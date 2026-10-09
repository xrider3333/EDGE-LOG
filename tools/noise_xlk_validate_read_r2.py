# -*- coding: utf-8 -*-
"""NOISE sector funds r1 - the XLK 900-trial Auto-Validate reader (copied from MANAGER's QQQ stage-2 reader). Reads the 2 job docs ONCE (2 Firestore reads; cached to stage2_job_<fam>.json),
then: the engine's verdict, checks, folds, PBO, lockbox; the winner vs the live settings; where the live config sits in
the searched population; and the owner's yardstick (ROC @ $30k DD, daily, WF and LB apart, + DD5) from a continuous
engine re-run of the winner (and of the live core) on the pinned QQQ master.

  python C:\\EdgeLog\\manager\\qqq_validate_1007\\stage2_read.py [--refresh]
"""
import json
import os
import sys

REPO = r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"
os.chdir(REPO)
sys.path.insert(0, REPO)
os.environ.pop("AUGUR_TRIAL_CACHE", None)
import warnings                                                         # noqa: E402

import numpy as np                                                      # noqa: E402
import pandas as pd                                                     # noqa: E402

from augur_engine import data as D                                      # noqa: E402
from augur_engine.engine import run_backtest                            # noqa: E402

warnings.filterwarnings("ignore", message="Mean of empty slice", category=RuntimeWarning)
OUT = "C:/EdgeLog/_anatomy_cache/noise_funds_r1/xlk_validate"
UID = "IO0K35JpLIcH9YK4C0pMNYUzZOM2"
JOBS = {"NOISE": "Nbi74iUDiB9AcYXjotZk"}
LIVE = {"NOISE": dict(lookback=40, band_mult_long=1.0, band_mult_short=1.0, stop_k=1.75)}
LIVE_NAME = {"NOISE": "Stage A crown"}
FILE = {"NOISE": "NOISE_1_1_FUNDGRID.py"}
COST, UNIT = 0.01, 4610                                               # the r2 job's engine cost (IS ranks)
SPLIT = pd.Timestamp("2025-12-05")                                    # XLK 2-for-1: real shares = adjusted / 2 before it
LINES = []


def say(s=""):
    print(s, flush=True)
    LINES.append(s)


def jdefault(o):
    try:
        return o.isoformat()
    except Exception:
        return str(o)


def fetch(refresh):
    docs = {}
    need = [f for f in JOBS if refresh or not os.path.exists(os.path.join(OUT, "r2_job_%s.json" % f))]
    if need:
        import firebase_admin
        from firebase_admin import credentials, firestore
        if not firebase_admin._apps:
            firebase_admin.initialize_app(credentials.Certificate(os.path.join(REPO, "serviceAccount.json")))
        u = firestore.client().collection("users").document(UID)
        for f in need:
            x = u.collection("backtests").document(JOBS[f]).get().to_dict() or {}
            json.dump(x, open(os.path.join(OUT, "r2_job_%s.json" % f), "w"), default=jdefault)
    for f in JOBS:
        docs[f] = json.load(open(os.path.join(OUT, "r2_job_%s.json" % f)))
    return docs


def ddmax(x):
    c = np.cumsum(x)
    pk = np.maximum.accumulate(np.concatenate([[0.0], c]))[1:]
    return float((pk - c).max()) if len(c) else 0.0


def dd5(x):
    c = np.concatenate([[0.0], np.cumsum(x)])
    dd = np.maximum.accumulate(c) - c
    eps, cur = [], 0.0
    for i in range(1, len(c)):
        if dd[i] == 0.0:
            if cur > 0:
                eps.append(cur)
            cur = 0.0
        else:
            cur = max(cur, dd[i])
    if cur > 0:
        eps.append(cur)
    eps = sorted(eps, reverse=True)[:5]
    return (float(np.mean(eps)) if eps else 0.0), len(eps)


def yard(df, t0, t1):
    """ROC @ $30k (daily DD) + DD5 at the $30k sizing over exit dates [t0, t1] on the QQQ session calendar."""
    t = df[(df.date >= t0) & (df.date <= t1)]
    days = DAYS[(DAYS >= t0) & (DAYS <= t1)]
    x = t.groupby("date").usd.sum().reindex(days, fill_value=0.0).to_numpy()
    yrs = ((t1 + pd.Timedelta(days=1)) - t0).days / 365.25
    d = ddmax(x)
    d5, ne = dd5(x)
    gl = -t.usd[t.usd < 0].sum()
    big = t.usd.max() if len(t) else 0.0
    return dict(n=len(t), net=float(x.sum()), yrs=yrs, dd=d, roc30=30 * (x.sum() / yrs) / d if d > 0 else float("nan"),
                dd5_30k=30000 * d5 / d if d > 0 else float("nan"), dd5_ratio=d5 / d if d > 0 else float("nan"), eps=ne,
                pf=t.usd[t.usd > 0].sum() / gl if gl > 0 else float("inf"), ex_big=float(x.sum() - big))


def run(fam, params):
    """AS TRADED: gross engine trades, then $0.02 a REAL share (adjusted shares x 0.5 before the split)."""
    r = run_backtest(FILE[fam], arrays=A, params=params, cost_pts=0.0, return_trades=True)
    tr = (r or {}).get("trades") or []
    ix = pd.DatetimeIndex(A["index"]).tz_localize(None)
    last = len(ix) - 1
    x = np.array([min(int(t[1]), last) for t in tr], int)
    e = np.array([int(t[0]) for t in tr], int)
    ratio = np.where(ix[e] < SPLIT, 0.5, 1.0)
    return pd.DataFrame({"date": ix[x].normalize(), "usd": [float(t[2]) * UNIT for t in tr] - 0.02 * UNIT * ratio})


def fmt(st):
    return ("n %4d  net $%9s  PF %.3f  daily DD $%7s  ROC @ $30k %6.1f %%/yr  DD5 $%6s at that size (DD5/DD %.2f)"
            % (st["n"], format(int(st["net"]), ","), st["pf"], format(int(st["dd"]), ","), st["roc30"],
               format(int(round(st["dd5_30k"])), ",") if np.isfinite(st["dd5_30k"]) else "-", st["dd5_ratio"]))


def main(argv):
    global A, DAYS
    docs = fetch("--refresh" in argv)
    for f, x in docs.items():
        if x.get("status") != "done":
            say("%s job %s is %s (progress %s) %s" % (f, JOBS[f], x.get("status"), x.get("progress"),
                                                    str(x.get("error") or "")[:300]))
    if any(x.get("status") != "done" for x in docs.values()):
        return
    m = D.find_master("XLK", "5m", "rth", "alpaca_split_rth")
    A = D.load_master_arrays(m, "2016-01-04", "2026-06-30")
    DAYS = pd.DatetimeIndex(sorted(set(pd.DatetimeIndex(A["index"]).tz_localize(None).normalize())))
    for fam, x in docs.items():
        r = x["result"]
        v = r["validate"]
        w = v.get("windows") or {}
        say("")
        say("=" * 118)
        say("%s family on XLK - job %s, run #%s, file %s, %s trials, elapsed %.0f min" % (
            fam, JOBS[fam], x.get("run_id"), x.get("strategy"), x.get("n_trials"), float(x.get("elapsed_s") or 0) / 60))
        say("  VERDICT %s  (%s of %s gates; checks %s)" % (v.get("verdict"), v.get("n_pass"), v.get("n_gates"),
                                                         json.dumps(v.get("checks"))))
        wa = v.get("wf_anchored") or {}
        say("  folds held %s of %s (anchored; wfe %s; OOS net $%s)   rolling: %s" % (
            v.get("folds_held"), v.get("n_folds"), wa.get("wfe"), format(int(float(wa.get("oos_net") or 0) * UNIT), ","),
            json.dumps({k: (v.get("wf_rolling") or {}).get(k) for k in ("held", "n_folds", "wfe")})))
        pb = v.get("pbo") or {}
        say("  PBO %s (%s; %s configs, %s splits)   DSR %s   plateau %s   trades/param %s" % (
            pb.get("pbo"), pb.get("verdict"), pb.get("n_configs"), pb.get("n_splits"), v.get("dsr"),
            json.dumps(v.get("plateau")), v.get("trades_per_param")))
        lb = v.get("lockbox") or {}
        say("  LOCKBOX (engine, fresh-start strip %s..%s): trades %s  net $%s  PF %.3f  pass %s" % (
            lb.get("from"), lb.get("to"), lb.get("trades"), format(int(float(lb.get("pnl") or 0) * UNIT), ","),
            float(lb.get("pf") or 0), lb.get("pass")))
        gv = r.get("gate_validate") or {}
        ul = gv.get("ungated_lockbox") or {}
        if ul:
            say("  LOCKBOX (continuous slice): trades %s  net $%s  PF %.3f" % (
                ul.get("num_trades"), format(int(float(ul.get("total_pnl") or 0) * UNIT), ","),
                float(ul.get("profit_factor") or 0)))
        wo = v.get("wf_oos") or {}
        if wo:
            keys = {k: wo.get(k) for k in wo if not isinstance(wo.get(k), (list, dict))}
            say("  WF OOS block (re-fitted folds, stitched): %s" % json.dumps(keys, default=str)[:600])
            try:
                net, dd_, yrs = float(wo.get("net")), abs(float(wo.get("max_drawdown") or wo.get("dd"))), float(wo.get("years"))
                say("    -> ROC @ $30k on the re-fitted folds (trade-close DD, the block's own) %.1f %%/yr" % (30 * net / yrs / dd_))
            except Exception as e:
                say("    (no ROC from the block: %s)" % e)
        champ = dict(r.get("best_params") or v.get("champion") or {})
        say("  WINNER settings: %s" % json.dumps(champ, default=str))
        live = LIVE[fam]
        diff = {k: (champ.get(k), live[k]) for k in live if k in champ and champ.get(k) != live[k]}
        say("  vs %s (live): differs on %d of %d knobs: %s" % (LIVE_NAME[fam], len(diff), len(live), json.dumps(diff)))
        ae = r.get("auto_expand_summary") or r.get("auto_expand")
        if ae:
            say("  auto-expand: %s" % json.dumps(ae, default=str)[:400])
        # where does the live config sit in the searched population?
        pts = r.get("points") or []
        say("  searched population saved: %d points (n_evaluated %s, n_valid %s, n_combos %s, truncated %s)" % (
            len(pts), r.get("n_evaluated"), r.get("n_valid"), r.get("n_combos"), r.get("population_truncated")))
        if pts:
            p0 = pts[0]
            say("    point fields: %s" % (list(p0.keys()) if isinstance(p0, dict) else type(p0).__name__))
        # rank of the live config on the SAME Stage-A in-sample score the population carries (first 75% of the
        # optimize window's bars, net of 0.02 a share, engine points), whether or not the sampler visited it
        o0, o1 = (w.get("optimize") or ["2016-01-04", "2025-06-29"])
        AO = D.load_master_arrays(m, o0, o1)
        k = int(len(AO["close"]) * 0.75)
        AS = {kk: (AO[kk][:k] if kk in ("open", "high", "low", "close", "volume", "day_id", "index") else AO[kk])
              for kk in AO}
        for lab, p in (("LIVE " + LIVE_NAME[fam], live), ("WINNER", champ)):
            rr = run_backtest(FILE[fam], arrays=AS, params=p, cost_pts=COST)
            ip = float((rr or {}).get("total_pnl") or 0)
            if pts and isinstance(pts[0], dict) and "pnl" in pts[0]:
                pp = np.array([float(z.get("pnl") or 0) for z in pts])
                visited = any(all(str(z.get(kk)) == str(p.get(kk)) for kk in live if kk in z) for z in pts)
                say("  IS (Stage A, first 75%% of %s..%s, %d bars to %s): %-18s pnl %.1f pts/share (%d trades) -> rank %d of %d "
                    "saved points (top %.1f%%); visited by the sampler: %s" % (
                        o0, o1, k, pd.DatetimeIndex(AO["index"])[k - 1].date(), lab, ip, (rr or {}).get("num_trades", 0),
                        int((pp > ip).sum()) + 1, len(pp), 100 * ((pp > ip).sum() + 1) / len(pp), visited))
        json.dump({"fam": fam, "points_head": pts[:3], "top": (r.get("top") or [])[:3]},
                  open(os.path.join(OUT, "r2_points_peek_%s.json" % fam), "w"), default=jdefault, indent=1)
        # the owner's yardstick, continuous re-run of the winner and of the live core on the pinned master
        wf0 = pd.Timestamp(w.get("wf_split") or "2016-07-01")
        opt1 = pd.Timestamp((w.get("optimize") or [None, "2025-06-29"])[1])
        lb0, lb1 = (pd.Timestamp(z) for z in (w.get("lockbox") or ["2025-06-30", "2026-06-30"]))
        say("  windows: optimize %s, WF from %s, lockbox %s" % (w.get("optimize"), w.get("wf_split"), w.get("lockbox")))
        R487 = dict(lookback=60, band_mult_long=1.0, band_mult_short=1.25, stop_k=1.75)
        for lab, p in (("WINNER", champ), ("LIVE " + LIVE_NAME[fam], live), ("#487 WINNER", R487)):
            df = run(fam, p)
            say("  %-18s WF %s..%s  %s" % (lab, wf0.date(), opt1.date(), fmt(yard(df, wf0, opt1))))
            sb = yard(df, lb0, lb1)
            say("  %-18s LB %s..%s  %s  ex-biggest $%s" % (lab, lb0.date(), lb1.date(), fmt(sb),
                                                          format(int(sb["ex_big"]), ",")))
            sw = yard(df, pd.Timestamp("2016-07-01"), pd.Timestamp("2025-06-29"))
            say("  %-18s Stage-1 WF 2016-07-01..2025-06-29  %s" % (lab, fmt(sw)))
    open(os.path.join(OUT, "r2_out.txt"), "w", encoding="utf-8").write("\n".join(LINES) + "\n")


if __name__ == "__main__":
    main(sys.argv[1:])
