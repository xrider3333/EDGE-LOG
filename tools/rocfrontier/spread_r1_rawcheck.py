"""SPREAD r1 RESTATED for the 2026-10-05 percent-read audit (ledger 2.24): the original spread_r1.py read the NQ/ES log ratio and the hedge
ratio off the back-adjusted (db_adj_rth) prices. Here the ratio is built from TRUE returns (adjusted point change / prior RAW close, roll-
corrected and shift-invariant) and h from RAW opens; P&L stays in adjusted points. Same 12 cells, pre-lockbox only. Run from the shared checkout.
Restated result (2026-10-05): 0 of 12 still clear - best MAR 0.09 (was 0.06). The null is not re-run (it cannot add a pass)."""
import os, sys, json, numpy as np, pandas as pd
ROOT = r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"; sys.path.insert(0, ROOT)
from augur_engine.data import find_master, load_master_arrays
HERE = os.environ.get("EDGELOG_ROCFRONTIER_R2", os.path.join("C:" + os.sep, "EdgeLog", "_anatomy_cache", "rocfrontier", "r2"))   # results go outside git
def daily(inst, src="db_adj_rth"):
    m = find_master(inst, "5m", "rth", src); assert m and m["source"] == src, m
    A = load_master_arrays(m, date_from="2010-06-07", date_to="2025-06-29")
    df = pd.DataFrame({"o": A["open"], "c": A["close"]}, index=pd.DatetimeIndex(A["index"]).tz_localize(None))
    df = df[df.index < pd.Timestamp("2025-06-30")]
    g = df.groupby(df.index.normalize())
    return pd.DataFrame({"o": g.o.first(), "c": g.c.last()})
NQ, ES = daily("NQ"), daily("ES")
D = NQ.join(ES, lsuffix="_nq", rsuffix="_es", how="inner").dropna()
assert D.index.max() < pd.Timestamp("2025-06-30")
RAW = daily("NQ", "db_noadj_rth").join(daily("ES", "db_noadj_rth"), lsuffix="_nq", rsuffix="_es", how="inner").reindex(D.index)
print("raw coverage of the adjusted days:", RAW.notna().mean().round(4).to_dict())
assert RAW.notna().mean().min() > 0.99
RAW = RAW.ffill()
r_nq = (D.c_nq.diff() / RAW.c_nq.shift(1)).fillna(0.0)
r_es = (D.c_es.diff() / RAW.c_es.shift(1)).fillna(0.0)
x = (np.log1p(r_nq) - np.log1p(r_es)).cumsum()
x_old = np.log(D.c_nq / D.c_es)
print("ratio check: corr of daily changes old vs true %.3f; same sign %.3f; adj/raw NQ 2010-06 %.2f 2016-07 %.2f, ES %.2f %.2f" % (
    np.corrcoef(x_old.diff().fillna(0), x.diff().fillna(0))[0, 1], (np.sign(x_old.diff()) == np.sign(x.diff())).mean(),
    D.c_nq.iloc[0] / RAW.c_nq.iloc[0], (D.c_nq / RAW.c_nq)[D.index >= "2016-07-01"].iloc[0],
    D.c_es.iloc[0] / RAW.c_es.iloc[0], (D.c_es / RAW.c_es)[D.index >= "2016-07-01"].iloc[0]))
COST_NQ, COST_ES = 0.533 * 20, 0.363 * 50
def simulate(target):
    """target: desired spread position (-1/0/1) decided at close t (Series on D.index). Fill at open t+1."""
    tgt = target.reindex(D.index).fillna(0).values
    o_nq, c_nq, o_es, c_es = D.o_nq.values, D.c_nq.values, D.o_es.values, D.c_es.values
    n = len(D); pnl = np.zeros(n); pos = 0; h = 0.0; spells = []; cur = 0.0
    for t in range(1, n):
        want = tgt[t - 1]
        # overnight leg (close t-1 -> open t) on the position held into the night
        pnl[t] += pos * (20 * (o_nq[t] - c_nq[t - 1]) - h * 50 * (o_es[t] - c_es[t - 1])); cur += pnl[t]
        if want != pos:
            if pos != 0:
                c_ = COST_NQ + COST_ES * h; pnl[t] -= c_; cur -= c_; spells.append(cur); cur = 0.0
            if want != 0:
                h = round((20 * RAW.o_nq.values[t]) / (50 * RAW.o_es.values[t]), 1)
                c_ = COST_NQ + COST_ES * h; pnl[t] -= c_; cur = -c_
            pos = want
        day = pos * (20 * (c_nq[t] - o_nq[t]) - h * 50 * (c_es[t] - o_es[t])); pnl[t] += day; cur += day
    if pos != 0: spells.append(cur)
    return pd.Series(pnl, index=D.index), np.array(spells)
def cells():
    out = {}
    for L in (10, 20, 40, 60, 120, 250):
        out["MOM L=%d" % L] = np.sign(x - x.shift(L))
    for N in (10, 20, 60):
        for Z in (1.5, 2.0):
            mu, sd = x.rolling(N).mean(), x.rolling(N).std()
            z = (x - mu) / sd
            pos = np.zeros(len(x)); p = 0; age = 0
            zv = z.values
            for i in range(len(x)):
                if np.isnan(zv[i]): pos[i] = 0; continue
                if p == 0:
                    if zv[i] >= Z: p, age = -1, 0
                    elif zv[i] <= -Z: p, age = 1, 0
                else:
                    age += 1
                    if (p == -1 and zv[i] <= 0) or (p == 1 and zv[i] >= 0) or age >= 10: p = 0
                pos[i] = p
            out["REV N=%d Z=%.1f" % (N, Z)] = pd.Series(pos, index=x.index)
    return out
def dd(s):
    c = s.cumsum(); return float((c.cummax() - c).max())
def score(s, spells):
    s = s[s.index >= "2010-06-07"]
    yrs = (s.index[-1] - s.index[0]).days / 365.25
    by = s.groupby(s.index.year).sum()
    top10 = np.sort(spells)[::-1][:10].sum() / spells.sum() if spells.sum() > 0 else np.nan
    return dict(net=s.sum(), dd=dd(s), mar=(s.sum() / yrs) / max(dd(s), 1), ypos=int((by > 0).sum()), ny=len(by),
                top10=top10, n=len(spells), roc=100 * s.sum() / yrs / 1e5)
# frontier book #397 pre-lockbox daily (legs at close, ENGU-Q marked to market) - book56 files, parity-exact with #397
X = pd.read_csv(r"C:\EdgeLog\_anatomy_cache\book56\leg_dailies.csv", index_col="date", parse_dates=True).sort_index()
M = pd.read_csv(r"C:\EdgeLog\_anatomy_cache\book56\enguq_mtm_daily.csv", index_col="date", parse_dates=True).sort_index()
ix = X.index.union(M.index); X = X.reindex(ix).fillna(0); M = M.reindex(ix).fillna(0)
book = (X["ORB297"] + M["ENGUQ335_mtm"] + 3 * X["TTM369"] + X["NOISE304"]); book = book[book.index < "2025-06-30"]
yb = (book.index[-1] - book.index[0]).days / 365.25
bmar = book.sum() / yb / dd(book)
s20 = lambda s: float(s[(s.index >= "2020-02-26") & (s.index <= "2020-03-27")].sum())
rows = []
for name, tgt in cells().items():
    s, sp = simulate(tgt)
    r = score(s, sp)
    ix2 = book.index.union(s.index)
    comb = book.reindex(ix2).fillna(0) + s.reindex(ix2).fillna(0)
    comb = comb[comb.index < "2025-06-30"]
    r.update(name=name, corr=np.corrcoef(s.reindex(book.index).fillna(0), book)[0, 1], s2020=s20(s),
             bk_mar=comb.sum() / yb / dd(comb), bk_lift=(comb.sum() / yb / dd(comb)) / bmar - 1, bk_s2020=s20(comb))
    rows.append(r)
print("BOOK #397 pre-lockbox MAR %.2f, Feb-Mar 2020 stretch $%.0f" % (bmar, s20(book)))
print("%-16s %5s %9s %7s %5s %6s %6s %5s %6s %8s | %6s %6s" % ("cell", "n", "net", "DD", "MAR", "ROC%", "yrs+", "top10", "corr", "2020str", "bkMAR", "lift"))
for r in rows:
    print("%-16s %5d %9.0f %7.0f %5.2f %6.1f %3d/%-2d %5.2f %6.3f %8.0f | %6.2f %+5.1f%%" % (r["name"], r["n"], r["net"], r["dd"], r["mar"], r["roc"], r["ypos"], r["ny"], r["top10"], r["corr"], r["s2020"], r["bk_mar"], 100 * r["bk_lift"]))
json.dump(rows, open(os.path.join(HERE, "spread_r1_rawcheck.json"), "w"), default=float, indent=1)
sys.exit(0)
# family-wide null: random direction per spell, same timing/turnover
rng = np.random.default_rng(7); obs = sum(1 for r in rows if r["mar"] >= 0.8 and r["ypos"] >= 10)
cnts = []
C = cells()
for k in range(200):
    c_ = 0
    for name, tgt in C.items():
        t = tgt.fillna(0)
        spell_id = (t != t.shift()).cumsum()
        flip = pd.Series(rng.choice([-1, 1], size=int(spell_id.max()) + 1), index=range(int(spell_id.max()) + 1))
        s, sp = simulate(t * spell_id.map(flip).values)
        r = score(s, sp)
        c_ += (r["mar"] >= 0.8 and r["ypos"] >= 10)
    cnts.append(c_)
cnts = np.array(cnts)
print("null (200 random-direction draws): cells clearing rule 1 mean %.2f, p(>= observed %d) = %.3f" % (cnts.mean(), obs, (cnts >= obs).mean()))
json.dump(rows, open(os.path.join(HERE, "spread_r1_results.json"), "w"), default=float, indent=1)
