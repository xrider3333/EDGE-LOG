# -*- coding: utf-8 -*-
"""NOISE ROUND 62 - judge the CT422V validate (vol-skip memory 68 / 160 / 252) against its pre-registered bar.

Bar (NOISE.md round 62, written before the job was queued): the 68-session cell at skip 95 is acceptable for live if
the validate is not FAIL and, replayed continuously on one tape, its profit factor is within 0.02 of the 252-session
cell (or above) in BOTH the walk-forward (2016-06-30 .. 2025-07-16) and the sealed year (2025-07-16 .. 2026-07-16).
The crowned cell is reported, never adopted. One Firestore read (the run doc), then engine replays.

  python tools/r62_judge_ct422v.py
"""
import importlib.util as ilu
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.environ.get("EDGELOG_REPO_ROOT") or r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"
os.environ["EDGELOG_REPO_ROOT"] = ROOT
sys.path.insert(0, ROOT)
os.chdir(ROOT)
import firebase_admin                                                 # noqa: E402
from firebase_admin import credentials, firestore                     # noqa: E402
from google.cloud.firestore_v1.base_query import FieldFilter         # noqa: E402

from augur_engine.data import find_master, load_master_arrays         # noqa: E402
from augur_engine.engine import run_backtest                          # noqa: E402

FN = "NOISE_1_8_CT422V.py"
WF0, LB0, LB1 = (pd.Timestamp(x).date() for x in ("2016-06-30", "2025-07-16", "2026-07-16"))
firebase_admin.initialize_app(credentials.Certificate(os.path.join(ROOT, "serviceAccount.json")))
U = firestore.client().collection("users").document("IO0K35JpLIcH9YK4C0pMNYUzZOM2")
docs = [d.to_dict() for d in U.collection("runs").where(filter=FieldFilter("strategy", "==", FN))
        .select(["id", "famKey", "famSeq", "best_params", "validate.verdict", "validate.pbo.pbo", "validate.folds_held"])
        .stream()]
if not docs:
    sys.exit("no run doc yet for " + FN)
r = max(docs, key=lambda x: int(x.get("id") or 0))
v = r.get("validate") or {}
pbo = (v.get("pbo") or {}).get("pbo") if isinstance(v.get("pbo"), dict) else None
print("#%s %s-%s %s  verdict %s  folds %s  overfit %s  crowned %s" % (r.get("id"), r.get("famKey"), r.get("famSeq"), FN,
      v.get("verdict"), v.get("folds_held"), pbo, r.get("best_params")))

A = load_master_arrays(find_master("NQ", "5m", "rth", "db_noadj_rth"), date_from="2010-06-07", date_to="2026-07-15")
IDX = pd.DatetimeIndex(A["index"])
sp = ilu.spec_from_file_location("ct422v_judge", os.path.join(ROOT, "augur_strategies", FN))
MOD = ilu.module_from_spec(sp)
sp.loader.exec_module(MOD)


def replay(params):
    t = run_backtest(MOD, arrays=A, params=params, cost_pts=0.533, return_trades=True)["trades"]
    d = np.array([IDX[max(int(x[0]) - 1, 0)].date() for x in t])
    p = np.array([x[2] * 20.0 for x in t], float)
    out = {}
    for nm, a, b in (("WF", WF0, LB0), ("LB", LB0, LB1)):
        q = p[(d >= a) & (d < b)]
        gw, gl = q[q > 0].sum(), -q[q < 0].sum()
        y = (pd.Timestamp(b) - pd.Timestamp(a)).days / 365.25
        cum = np.cumsum(q)
        dd = float((np.maximum.accumulate(np.concatenate([[0.0], cum]))[1:] - cum).max())
        down = np.sqrt(np.mean(np.minimum(q, 0.0) ** 2))
        out[nm] = dict(n=len(q), pf=gw / gl, net=float(q.sum()), roc=100 * q.sum() / y / 1e5, dd=dd,
                       so=(q.mean() / down) * np.sqrt(len(q) / y))
    return out


cells = [("68 sessions, skip 95 (live)", dict(vol_skip_pct=95.0, vol_ref_sessions=68)),
         ("160 sessions, skip 95", dict(vol_skip_pct=95.0, vol_ref_sessions=160)),
         ("252 sessions, skip 95 (#422)", dict(vol_skip_pct=95.0, vol_ref_sessions=252))]
bp = r.get("best_params") or {}
if bp and not (abs(float(bp.get("vol_skip_pct", 0)) - 95.0) < 1e-9):
    cells.append(("crowned (reported only)", {k: bp[k] for k in ("vol_skip_pct", "vol_ref_sessions") if k in bp}))
res = {}
for label, params in cells:
    res[label] = s = replay(params)
    print("  %-30s" % label + " | ".join("%s %4d tr PF %4.3f %5.1f%%/yr DD $%7s Sortino %4.2f" % (
        k, x["n"], x["pf"], x["roc"], format(int(x["dd"]), ","), x["so"]) for k, x in s.items()))
a, b = res["68 sessions, skip 95 (live)"], res["252 sessions, skip 95 (#422)"]
ok = v.get("verdict") != "FAIL" and all(a[k]["pf"] >= b[k]["pf"] - 0.02 for k in ("WF", "LB"))
print("BAR (68 within 0.02 PF of 252 in WF AND sealed year, validate not FAIL): %s  [WF %.3f vs %.3f, LB %.3f vs %.3f]"
      % ("MET - the live 68-session window is acceptable" if ok else "NOT MET - live needs the full 252-session memory",
         a["WF"]["pf"], b["WF"]["pf"], a["LB"]["pf"], b["LB"]["pf"]))
