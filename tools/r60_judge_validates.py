# -*- coding: utf-8 -*-
"""NOISE ROUND 60 - judge the two round-60 Auto-Validates against the bars written into their files.

Reads each run doc ONCE (by strategy name, newest first), takes the crowned cell, and replays it and the centre
cell CONTINUOUSLY on one tape (2010-06-07 .. 2026-07-16, the validates' own window; the saved lockbox strip is a
cold-restart reload for NOISE and is never used here). Eras: before 2024 / 2024 on / sealed year from 2025-07-16.

  GEO304 bar: PASS, overfit <= 0.198, AND the crowned geometry beats the centre on PF in BOTH eras.
  CT304H bar: PASS (or WEAK on the overfit gate alone), AND in the sealed year the crowned tilt earns at least the
              crown's dollars at a drawdown no more than 25% above the crown's, AND annual MAR >= the crown's.

  python tools/r60_judge_validates.py
"""
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.environ.get("EDGELOG_REPO_ROOT") or r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"
os.environ["EDGELOG_REPO_ROOT"] = ROOT
sys.path.insert(0, ROOT)
os.chdir(ROOT)
import importlib.util as ilu                                          # noqa: E402

import firebase_admin                                                 # noqa: E402
from firebase_admin import credentials, firestore                     # noqa: E402
from google.cloud.firestore_v1.base_query import FieldFilter         # noqa: E402

from augur_engine.data import find_master, load_master_arrays         # noqa: E402
from augur_engine.engine import run_backtest                          # noqa: E402

END = pd.Timestamp("2026-07-16").date()
E24, LB0 = pd.Timestamp("2024-01-01").date(), pd.Timestamp("2025-07-16").date()
firebase_admin.initialize_app(credentials.Certificate(os.path.join(ROOT, "serviceAccount.json")))
U = firestore.client().collection("users").document("IO0K35JpLIcH9YK4C0pMNYUzZOM2")
A = load_master_arrays(find_master("NQ", "5m", "rth", "db_noadj_rth"), date_from="2010-06-07", date_to=str(END))
IDX = pd.DatetimeIndex(A["index"])


def mod(fn):
    sp = ilu.spec_from_file_location(fn[:-3], os.path.join(ROOT, "augur_strategies", fn))
    m = ilu.module_from_spec(sp)
    sp.loader.exec_module(m)
    return m


def run_doc(fn):
    q = (U.collection("runs").where(filter=FieldFilter("strategy", "==", fn))
         .select(["id", "famKey", "famSeq", "best_params", "validate.verdict", "validate.pbo.pbo",
                  "validate.checks", "validate.folds_held"]))
    docs = [d.to_dict() for d in q.stream()]
    return max(docs, key=lambda r: int(r.get("id") or 0)) if docs else None


def stretches(m, params):
    r = run_backtest(m, arrays=A, params=params, cost_pts=0.533, return_trades=True)
    t = r["trades"] if r and r.get("trades") else []
    d = np.array([IDX[max(int(x[0]) - 1, 0)].date() for x in t])
    p = np.array([x[2] * 20.0 for x in t], float)
    out = {}
    for nm, a, b in (("pre-2024", None, E24), ("2024 on", E24, None), ("sealed yr", LB0, None), ("whole", None, None)):
        k = np.ones(len(d), bool)
        if a is not None:
            k &= d >= a
        if b is not None:
            k &= d < b
        q = p[k]
        cum = np.cumsum(q)
        dd = float((np.maximum.accumulate(np.concatenate([[0.0], cum]))[1:] - cum).max()) if len(q) else 0.0
        gw, gl = q[q > 0].sum(), -q[q < 0].sum()
        yrs = max(((pd.Timestamp(b or END) - pd.Timestamp(a or "2010-06-07")).days / 365.25), 1e-9)
        out[nm] = dict(n=len(q), net=float(q.sum()), pf=(gw / gl if gl > 0 else float("inf")), dd=dd,
                       mar=(q.sum() / yrs / dd) if dd > 0 else 0.0)
    return out


def show(label, s):
    print("  %-34s" % label + " | ".join("%s %4d tr $%9s PF %4.2f DD $%7s MAR %4.2f" % (
        k, v["n"], format(int(v["net"]), ","), v["pf"], format(int(v["dd"]), ","), v["mar"])
        for k, v in s.items() if k != "whole"))


for fn, centre, kind in (("NOISE_1_9_GEO304.py", None, "GEO"), ("NOISE_1_8_CT304H.py", None, "CT")):
    r = run_doc(fn)
    print("\n" + "=" * 120)
    if not r:
        print(fn, "- no run doc yet (still queued or running)")
        continue
    v = r.get("validate") or {}
    pbo = ((v.get("pbo") or {}).get("pbo") if isinstance(v.get("pbo"), dict) else None)
    m = mod(fn)
    ctr = dict(m._CENTER) if hasattr(m, "_CENTER") else {k: d["default"] for k, d in m.DEFAULT_PARAMS.items()}
    best = {k: r["best_params"][k] for k in ctr if k in (r.get("best_params") or {})}
    same = all(abs(float(best[k]) - float(ctr[k])) < 1e-9 for k in ctr if k in best)
    print("#%s %s-%s  %s  verdict %s  folds %s  overfit %s  crowned %s  %s" % (
        r.get("id"), r.get("famKey"), r.get("famSeq"), fn, v.get("verdict"), v.get("folds_held"), pbo, best,
        "= THE CENTRE" if same else "(not the centre)"))
    sc, sb = stretches(m, ctr), stretches(m, dict(ctr, **best))
    show("centre", sc)
    show("crowned", sb)
    if kind == "GEO":
        ok = (v.get("verdict") == "PASS" and pbo is not None and pbo <= 0.198
              and sb["pre-2024"]["pf"] > sc["pre-2024"]["pf"] and sb["2024 on"]["pf"] > sc["2024 on"]["pf"])
        print("  BAR:", "MET - a different geometry earns its place" if (ok and not same) else
              ("centre crowned - the crown's geometry holds on compressed hours" if same else "NOT MET - keep the centre"))
    else:
        crown = stretches(mod("NOISE_1_0.py"), dict(lookback=40, band_mult_long=0.75, band_mult_short=1.5,
                          exit_mode="vwap", side="Both", window="all_day", flat_eod=True, skip_holidays=False,
                          stop_mode="bandwidth", stop_k=1.75, confirm_bars=1, daytype_mode="skip_bot_short",
                          daytype_lo=0.2, daytype_hi=0.8, vol_skip_pct=95.0))
        show("live crown #304 (reference)", crown)
        L, C = sb["sealed yr"], crown["sealed yr"]
        verdict_ok = v.get("verdict") == "PASS" or (v.get("verdict") == "WEAK" and pbo is not None and pbo > 0.5)
        ok = verdict_ok and L["net"] >= C["net"] and L["dd"] <= 1.25 * C["dd"] and L["mar"] >= C["mar"]
        print("  BAR (sealed year vs crown): net $%s vs $%s, DD $%s vs $%s (limit +25%%), MAR %.2f vs %.2f -> %s" % (
            format(int(L["net"]), ","), format(int(C["net"]), ","), format(int(L["dd"]), ","), format(int(C["dd"]), ","),
            L["mar"], C["mar"], "MET" if ok else "NOT MET"))
