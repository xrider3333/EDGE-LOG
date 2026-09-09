"""
ROUND 46 — does the ENGU-Q ES leg have the RECENCY problem? (2026-09-09)

A sibling's rounds 43-45 found that essentially everything which improves NOISE over 2010-2023 has
LOST money over 2024-2026 on this tape. The ENGU-Q ES leg is the last open candidate from my branch
work, and its sealed year was already thin (+$17,496 on a $33,074 drawdown), so it gets the same test
before anything else is claimed for it.

Year by year, calendar year, the R2 crown file at its own defaults:
  NQ 1m 24h at 0.783 a round trip, $20 a point   (the crowned leg, as reference)
  ES 1m 24h at 0.40 and at 0.60 a round trip, $50 a point  (0.60 = the realistic-fill cost this
  session's round 42 argued for; round 37 already showed the ES leg clears the house bar at 0.60)
Plus the per-trade-versus-cost arithmetic that closed the NOISE ES branch: a leg must earn at least
twice its own round trip.

Window 2010-06-07..2026-06-30 (the ENGU-Q crown window). The last 12 months of that were the sealed
year for the ES validate, so 2025-2026 rows are reported as ALREADY-READ, not as a fresh test.
"""
import os, sys, csv
import numpy as np, pandas as pd
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT); os.chdir(ROOT)
import importlib.util as ilu
from augur_engine.engine import run_backtest
from augur_engine.data import find_master, load_master_arrays

FN = "augur_strategies/ENGUQ_1M_ETH_R2_1_0.py"
sp = ilu.spec_from_file_location("m", FN); m = ilu.module_from_spec(sp); sp.loader.exec_module(m)
P = {k: v["default"] for k, v in m.DEFAULT_PARAMS.items()}
LEGS = [("NQ", 0.783, 20.0), ("ES", 0.40, 50.0), ("ES", 0.60, 50.0)]
series = {}
for inst, cost, mult in LEGS:
    A = load_master_arrays(find_master(inst, "1m", "eth", "db_noadj_eth"),
                           date_from="2010-06-07", date_to="2026-06-30")
    idx = pd.DatetimeIndex(A["index"])
    r = run_backtest(FN, arrays=A, params=P, cost_pts=cost, return_trades=True)
    df = pd.DataFrame({"t": [idx[t[0]] for t in r["trades"]], "pnl": [t[2] * mult for t in r["trades"]]})
    key = f"{inst} @{cost:.2f}"
    series[key] = df
    p = df.pnl.values; gw = p[p > 0].sum(); gl = -p[p < 0].sum()
    print(f"{key:12} n={len(p):5} net=${p.sum():>10,.0f} PF={gw/gl:.3f} ${p.sum()/len(p):7.2f}/trade "
          f"vs ${cost*mult:5.2f} cost = {p.sum()/len(p)/(cost*mult):5.2f}x", flush=True)

print(f"\n{'year':6}" + "".join(f"{k:>22}" for k in series) + "   (net $ / trades)")
years = sorted({t.year for df in series.values() for t in df.t})
ROWS = []
for y in years:
    cells = []
    row = {"year": y}
    for k, df in series.items():
        s = df[df.t.dt.year == y].pnl
        cells.append(f"{s.sum():>13,.0f} /{len(s):>4}" if len(s) else f"{'-':>13} /{0:>4}")
        row[k] = round(float(s.sum())); row[k + " n"] = len(s)
    ROWS.append(row)
    tag = "  <- sealed year for the ES validate" if y >= 2025 else ""
    print(f"{y:6}" + "".join(f"{c:>22}" for c in cells) + tag)

print("\nRECENCY SPLIT (the sibling's 2024 boundary):")
for k, df in series.items():
    for lab, sel in (("2010-2023", df.t.dt.year <= 2023), ("2024-2026", df.t.dt.year >= 2024)):
        s = df[sel].pnl.values
        if not len(s):
            continue
        gw = s[s > 0].sum(); gl = -s[s < 0].sum()
        cum = np.cumsum(s); dd = float((cum - np.maximum.accumulate(cum)).min())
        print(f"  {k:12} {lab:10} n={len(s):5} net=${s.sum():>10,.0f} PF={gw/gl if gl else 99:.3f} "
              f"DD=${-dd:>9,.0f} n/DD={s.sum()/-dd if dd < 0 else 99:6.2f} ${s.sum()/len(s):7.2f}/trade")
with open("tools/r16_results/r46_enguq_es_recency.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(ROWS[0].keys())); w.writeheader()
    for r in ROWS: w.writerow(r)
print("\nsaved tools/r16_results/r46_enguq_es_recency.csv")
