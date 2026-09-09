"""
ROUND 37 — does any CROWNED NQ mechanism branch into an ES family? (pre-registered 2026-09-08)

The validates already carry thin ES transfer legs for two crowns (NOISE #243: PF 1.12 on 4,522
trades; ORB #314: PF 1.02) and none for ENGU-Q. This is the full house read of each crowned FILE
at its own defaults on the ES tape - net, PF, DD, n/DD, 8 chronological slices, concentration -
next to the same file on NQ, same window 2010-06-07..2025-06-29 (lockbox never loaded).
ES costs: 0.30 pts/RT day session, 0.40 pts/RT 24h (commission ~$4 + one tick each side);
NQ costs: 0.533 / 0.783 as always. $50/pt ES, $20/pt NQ.
Cells: NOISE crown card (NOISE_1_1_SBS_V90) on ES 5m RTH | ENGU-Q R2 crown on ES 1m ETH |
       ORB crown card (ORB_3_6_C2) on ES 5m RTH | plus each on NQ as the reference.
A branch worth a file = PF >= 1.25, n/DD >= 8, n >= 300, top-10 < 90%, ex-top-10 > 0 on ES.
"""
import os, sys, csv
import numpy as np
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT); os.chdir(ROOT)
import importlib.util as _ilu
from augur_engine.engine import run_backtest
from augur_engine.data import find_master, load_master_arrays

WIN = dict(date_from="2010-06-07", date_to="2025-06-29")
CELLS = [("NOISE crown card", "augur_strategies/NOISE_1_1_SBS_V90.py", "5m", "rth", 0.533, 0.30),
         ("ORB crown card", "augur_strategies/ORB_3_6_C2.py", "5m", "rth", 0.533, 0.30),
         ("ENGU-Q R2 crown", "augur_strategies/ENGUQ_1M_ETH_R2_1_0.py", "1m", "eth", 0.783, 0.40)]


def defaults(fn):
    sp = _ilu.spec_from_file_location("m", fn); m = _ilu.module_from_spec(sp); sp.loader.exec_module(m)
    return {k: v["default"] for k, v in m.DEFAULT_PARAMS.items()}


def read(label, fn, inst, tf, sess, cost, mult):
    src = "db_noadj_rth" if sess == "rth" else "db_noadj_eth"
    A = load_master_arrays(find_master(inst, tf, sess, src), **WIN)
    r = run_backtest(fn, arrays=A, params=defaults(fn), cost_pts=cost, return_trades=True)
    if not r or not r.get("trades"):
        print(f"{label:18} {inst:3} no trades"); return None
    p = np.array([t[2] * mult for t in r["trades"]]); n = len(p)
    gw = p[p > 0].sum(); gl = -p[p < 0].sum(); pf = gw / gl if gl else 99
    cum = np.cumsum(p); dd = float((cum - np.maximum.accumulate(cum)).min()); net = float(p.sum())
    w = float((p > 0).mean()); evr = (1 - w) * (pf - 1); yrs = 15.06
    k = n // 8; folds = sum(1 for i in range(8) if p[i * k:(i + 1) * k if i < 7 else n].sum() > 0)
    srt = sorted(p, reverse=True); top10 = sum(srt[:10]); ex = np.array(srt[10:])
    exgw = ex[ex > 0].sum(); exgl = -ex[ex < 0].sum()
    row = dict(label=label, inst=inst, n=n, net=round(net), pf=round(pf, 3), dd=round(-dd), mar=round(net / -dd, 2) if dd < 0 else 99,
               win=round(100 * w, 1), evr=round(evr, 3), ryr=round(evr * n / yrs, 1), folds8=folds,
               top10_pct=round(100 * top10 / net) if net > 0 else 999, exnet=round(float(ex.sum())),
               expf=round(exgw / exgl, 3) if exgl else 99)
    g = "PASS" if (pf >= 1.25 and row["mar"] >= 8 and n >= 300 and row["top10_pct"] < 90 and row["exnet"] > 0) else "fail"
    print(f"{label:18} {inst:3} n={n:5} net=${net:>10,.0f} PF={pf:.3f} DD=${-dd:>9,.0f} n/DD={row['mar']:5.2f} win={100*w:4.1f} "
          f"EVR={evr:.3f} f8={folds} top10={row['top10_pct']}% ex=${row['exnet']:>9,} exPF={row['expf']:.2f}  {g}", flush=True)
    return row


rows = []
for label, fn, tf, sess, cnq, ces in CELLS:
    for inst, cost, mult in (("NQ", cnq, 20.0), ("ES", ces, 50.0)):
        try:
            r = read(label, fn, inst, tf, sess, cost, mult)
            if r: rows.append(r)
        except Exception as e:
            print(f"{label:18} {inst:3} ERROR {e}", flush=True)
with open("tools/r16_results/r37_es_branch.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader()
    for r in rows: w.writerow(r)
print("saved tools/r16_results/r37_es_branch.csv")
