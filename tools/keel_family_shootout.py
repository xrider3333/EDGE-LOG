"""Is KEEL the best option for the NOISE family, against its own sisters, on the same stretches?

Reads each NOISE validate's stored family blocks (RAW / GATE / TILT / HYBRID) straight off the run,
and puts KEEL v12 beside them computed from the engine. Every figure is the SAME walk-forward and
lockbox stretch the run itself defines, in dollars at the NQ multiplier.

Selection is stated rather than hidden: each family's representative is the row with the best
WALK-FORWARD money, chosen without looking at the lockbox, which is how a live pick would have to be
made. The lockbox column is then the held-back read on that already-made choice.
"""
import os, sys, numpy as np, pandas as pd
ROOT = r"C:/Users/xride/OneDrive/Desktop/EDGE-LOG"
HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(ROOT); sys.path.insert(0, ROOT); sys.path.insert(0, os.path.join(ROOT, "tools"))
import firebase_admin
from firebase_admin import credentials, firestore
if not firebase_admin._apps:
    firebase_admin.initialize_app(credentials.Certificate(os.path.join(ROOT, "serviceAccount.json")))
DB = firestore.client()
COL = DB.collection("users").document("IO0K35JpLIcH9YK4C0pMNYUzZOM2").collection("runs")
M = 20.0

def blk(b):
    if not isinstance(b, dict):
        return None
    n = b.get("total_pnl"); dd = b.get("max_drawdown")
    if n is None or dd is None:
        return None
    return dict(net=float(n) * M, dd=float(dd) * M, pf=b.get("profit_factor"),
                sh=b.get("sharpe"), so=b.get("sortino"), tr=b.get("num_trades"))

def mar(x, yrs):
    return (x["net"] / yrs) / abs(x["dd"]) if x and x["dd"] else float("nan")

# KEEL v12, engine-computed, from the cached size vectors (same trade lists, same stretches)
S = np.load(os.path.join(HERE, "v12_state.npz"), allow_pickle=True)
WF0, LB0, END = "2016-05-02", "2025-02-11", "2026-08-12"
def keel12(rid):
    if f"{rid}_P" not in S:
        return None, None
    ts = pd.DatetimeIndex(S[f"{rid}_ts"]); P = S[f"{rid}_P"] * S[f"{rid}_size_v12"]
    out = []
    for m, a, b in ((((ts >= pd.Timestamp(WF0)) & (ts < pd.Timestamp(LB0))), WF0, LB0),
                    ((ts >= pd.Timestamp(LB0)), LB0, END)):
        p = P[m]; cum = np.cumsum(p)
        dd = float((cum - np.maximum.accumulate(np.concatenate([[0.0], cum]))[1:]).min())
        gw, gl = p[p > 0].sum(), -p[p < 0].sum()
        out.append(dict(net=float(p.sum()), dd=dd, pf=float(gw / gl) if gl else 99, sh=None, so=None, tr=int(m.sum())))
    return out[0], out[1]

WFY, LBY = (pd.Timestamp(LB0) - pd.Timestamp(WF0)).days / 365.25, (pd.Timestamp(END) - pd.Timestamp(LB0)).days / 365.25

RUNS = (("243","NOISE #243 - the PAPER leg's run, NQ 5m"),("304","NOISE #304 - the CROWN, NQ 5m"),
        ("374","NOISE #374 - the EXIT variant, NQ 5m"),("345","NOISE #345 - NQ 1m"),
        ("362","NOISE #362 - NQ 15m"),("344","NOISE #344 - on ES 5m"))
for rid, tag in RUNS:
    gv = (COL.document(rid).get().to_dict() or {}).get("gate_validate") or {}
    if not gv:
        print(f"#{rid}: no gate block"); continue
    rows = []
    raw_wf, raw_lb = blk(gv.get("ungated_wf")), blk(gv.get("ungated_lockbox") or gv.get("lockbox"))
    rows.append(("RAW (no overlay)", raw_wf, raw_lb, ""))
    for fam, key, lbl in (("candidates", "gate", "GATE"), ("tilts", "tilt", "TILT"), ("hybrids", "hyb", "HYBRID")):
        best, bwf, blb, nm = None, None, None, ""
        for c in (gv.get(fam) or []):
            w = blk(c.get("wf_rng"))
            if w and (best is None or w["net"] > best):
                best, bwf, blb = w["net"], w, blk(c.get("lockbox"))
                nm = str(c.get("model") or "") + (" @" + str(c.get("threshold")) if c.get("threshold") is not None else "")
        if bwf:
            rows.append((lbl, bwf, blb, nm))
    _k = gv.get("keel") or {}
    kw, kl = blk(_k.get("wf_rng")), blk(_k.get("lockbox"))
    if kw:
        rows.append(("KEEL " + str(_k.get("version") or "?"), kw, kl, "avg size " + str(_k.get("avg_size"))))

    print("\n" + "=" * 108)
    print(f"{tag}   — best-of-family chosen on WALK-FORWARD money only; lockbox is the held-back read")
    print(f"  {'family':30s} {'WF net':>11s} {'WF dd':>10s} {'WF MAR':>7s} | {'LB net':>10s} {'LB dd':>10s} {'LB MAR':>7s}  pick")
    base = rows[0][1]["net"]
    for lbl, w, l, nm in rows:
        lbs = f"{l['net']:>10,.0f} {l['dd']:>10,.0f} {mar(l, LBY):>7.2f}" if l else f"{'-':>10s} {'-':>10s} {'-':>7s}"
        print(f"  {lbl:30s} {w['net']:>11,.0f} {w['dd']:>10,.0f} {mar(w, WFY):>7.2f} | {lbs}  {nm}")
    print(f"  (walk-forward money vs raw: " + ", ".join(
        f"{lbl.split(' ')[0]} {100*(w['net']/base-1):+.0f}%" for lbl, w, l, nm in rows[1:]) + ")")
