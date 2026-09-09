# -*- coding: utf-8 -*-
"""META WALK-FORWARD: is RE-OPTIMISING the ORB worth anything?

Every round so far asked "which config is best". This asks a different question: if you had
stood at a date in the past, run the same selection we run, and traded the winner for the next
year, would you have beaten simply leaving the parameters alone? Each config is run ONCE over
all history and sliced afterwards, so every decision date sees identical warm-up.
Nothing after LB_END is ever loaded."""
import sys, itertools, json, numpy as np, pandas as pd
sys.path.insert(0, r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG\tools")
import orb_pick as P

GRID = dict(or_bars=[1,2,3], stop_frac=[2.0,2.5,3.0], target_R=[4.0,5.0,5.5,6.0],
            be_after_R=[0.5,1.0], atr_filter=[0.7,0.75], vpace_filter=[0.7,0.8])
KEYS = list(GRID)
CFGS = [dict(zip(KEYS, v)) for v in itertools.product(*GRID.values())]
CROWN = dict(atr_filter=0.75, vpace_filter=0.8, stop_frac=2.5, target_R=5.0, be_after_R=0.5, or_bars=2)
DEFAULT = {k: P.BASE[k] for k in KEYS}          # the untouched parent default = "leave it alone"
print("configs:", len(CFGS), flush=True)

res = {}
for i, cfg in enumerate(CFGS):
    tr = P.trades_of(cfg)
    res[json.dumps(cfg, sort_keys=True)] = pd.DataFrame(tr, columns=["ts","net"]) if tr else pd.DataFrame(columns=["ts","net"])
    if i % 25 == 0: print("  %d/%d" % (i, len(CFGS)), flush=True)

def score(df, lo, hi):
    d = df[(df.ts >= lo) & (df.ts < hi)]
    if len(d) < 30: return None
    p = d.net.values; yrs = max((d.ts.iloc[-1] - d.ts.iloc[0]).days / 365.25, 0.1)
    cum = np.cumsum(p); dd = abs(float((cum - np.maximum.accumulate(cum)).min()))
    w = p[p > 0].sum(); l = abs(p[p < 0].sum())
    return dict(n=len(p), net=p.sum(), mar=((p.sum()/yrs)/dd if dd else np.nan),
                pf=(w/l if l else np.inf), tpy=len(p)/yrs)

START = pd.Timestamp("2010-06-07"); LB = pd.Timestamp(P.LB_END)
DATES = [pd.Timestamp("%d-08-13" % y) for y in range(2015, 2026)]
dk, ck = json.dumps(DEFAULT, sort_keys=True), json.dumps({**DEFAULT, **CROWN}, sort_keys=True)
rows = []
for D in DATES:
    F = min(D + pd.DateOffset(years=1), LB)
    if F <= D: continue
    isc = {k: score(v, START, D) for k, v in res.items()}
    fwd = {k: score(v, D, F) for k, v in res.items()}
    elig = {k: s for k, s in isc.items() if s and s["tpy"] >= 120}
    if not elig: continue
    pick = max(elig, key=lambda k: elig[k]["mar"])
    pnet = max(elig, key=lambda k: elig[k]["net"])
    alive = [k for k in elig if fwd.get(k)]
    if not alive: continue
    fn = np.array([fwd[k]["net"] for k in alive]); fm = np.array([fwd[k]["mar"] for k in alive])
    rows.append(dict(date=D.date(), n_elig=len(elig),
        pick_net=fwd[pick]["net"] if fwd.get(pick) else np.nan,
        pick_mar=fwd[pick]["mar"] if fwd.get(pick) else np.nan,
        picknet_net=fwd[pnet]["net"] if fwd.get(pnet) else np.nan,
        default_net=fwd[dk]["net"] if fwd.get(dk) else np.nan,
        crown_net=fwd[ck]["net"] if fwd.get(ck) else np.nan,
        median_net=float(np.median(fn)), mean_net=float(fn.mean()),
        pct_of_field=float((fn < (fwd[pick]["net"] if fwd.get(pick) else -1e9)).mean()*100),
        median_mar=float(np.median(fm))))
df = pd.DataFrame(rows)
pd.set_option("display.width", 200)
print("\n=== FORWARD YEAR after each decision date (net $, one contract) ===")
print(df.round(1).to_string(index=False))
print("\n=== SUMMARY over %d decision dates ===" % len(df))
for c, lab in (("pick_net","re-optimised by MAR"), ("picknet_net","re-optimised by NET"),
               ("default_net","left alone (parent default)"), ("crown_net","today's crown params"),
               ("median_net","a config picked at random")):
    v = df[c].dropna()
    print("  %-30s total $%9.0f | mean/yr $%8.0f | positive years %d/%d" %
          (lab, v.sum(), v.mean(), (v > 0).sum(), len(v)))
print("\n  re-optimised beat leave-alone in %d of %d years" % ((df.pick_net > df.default_net).sum(), len(df)))
print("  re-optimised beat a RANDOM config in %d of %d years (mean percentile %.0f)" %
      ((df.pick_net > df.median_net).sum(), len(df), df.pct_of_field.mean()))
