# -*- coding: utf-8 -*-
"""Is "barely-clearing entries earn more" a NEW fact, or just the range-width effect again?
For every crown trade: distance of the confirming close beyond the trigger level, in units of
that day's opening-range width. Then a 2-way table vs the range-width ratio."""
import sys, numpy as np, pandas as pd
sys.path.insert(0, r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG\tools")
import orb_pick as P

b = P.bars(); idx = b["index"]; day = b["day_id"]
o,h,l,c = b["open"],b["high"],b["low"],b["close"]
CROWN = dict(P.BASE, atr_filter=0.75, vpace_filter=0.8, stop_frac=2.5, target_R=5.0, be_after_R=0.5)
r = P.strat("ORB_3_6.py").run_backtest(o,h,l,c, volumes=b["volume"], day_id=day, return_trades=True, **CROWN)

# per-day opening range (first 2 bars) and its 20-day trailing median
starts = np.flatnonzero(np.r_[True, np.diff(day) != 0])
rng_of, hi_of, lo_of, dayno = {}, {}, {}, {}
for n, s in enumerate(starts):
    hi, lo = h[s:s+2].max(), l[s:s+2].min()
    d = day[s]; rng_of[d], hi_of[d], lo_of[d], dayno[d] = hi-lo, hi, lo, n
med = {}
seq = [rng_of[day[s]] for s in starts]
for n, s in enumerate(starts):
    prev = seq[max(0,n-20):n]
    med[day[s]] = float(np.median(prev)) if prev else np.nan

LE = pd.Timestamp(P.LB_END, tz=idx.tz); F5 = pd.Timestamp("2021-08-13", tz=idx.tz)
rows = []
for t in r["trades"]:
    ei, _, pts, dr, epx = t[0], t[1], t[2], t[3], t[4]
    ts = idx[ei]
    if ts > LE: continue
    d = day[ei]; rg = rng_of[d]
    lvl = (hi_of[d] + 0.25*rg) if dr > 0 else (lo_of[d] - 0.25*rg)
    dist = ((epx - lvl) if dr > 0 else (lvl - epx)) / rg      # in opening-range widths
    ratio = rg / med[d] if med[d] == med[d] and med[d] > 0 else np.nan
    rows.append((ts, dist, ratio, (pts - P.COST) * P.MULT, ts >= F5))
df = pd.DataFrame(rows, columns=["ts","dist","ratio","net","is5y"]).dropna()

def blk(g):
    w = g.net[g.net > 0].sum(); ls = -g.net[g.net < 0].sum()
    return pd.Series({"n": len(g), "net": g.net.sum(), "PF": (w/ls if ls else np.inf), "avg": g.net.mean()})

for name, d in (("FULL", df), ("5y", df[df.is5y])):
    print("\n=== %s: %d trades, corr(dist, range-width ratio) = %.3f  [Spearman %.3f]" %
          (name, len(d), d.dist.corr(d.ratio), d.dist.corr(d.ratio, method="spearman")))
    d = d.assign(Q=pd.qcut(d.dist, 4, labels=["nearest","2","3","farthest"]))
    print(d.groupby("Q", observed=True).apply(blk, include_groups=False).round(2).to_string())
    d = d.assign(R=pd.qcut(d.ratio, 2, labels=["narrow day","wide day"]))
    print("\n2-way (does distance survive INSIDE each range bucket?)")
    print(d.groupby(["R","Q"], observed=True).apply(blk, include_groups=False).round(2).to_string())

# ---- NULL: permute the distance labels WITHIN each calendar year (keeps regime + trade mix,
#      breaks only the link between how far a close cleared the level and what the trade earned).
print("\n\n=== PERMUTATION NULL (2000 draws, distance shuffled within year) ===")
rng = np.random.default_rng(42)
for name, d in (("FULL", df), ("5y", df[df.is5y])):
    d = d.copy(); d["yr"] = d.ts.dt.year
    def near_pf(dist):
        q = pd.qcut(dist, 4, labels=False, duplicates="drop")
        g = d.net[q == 0]
        w = g[g > 0].sum(); ls = -g[g < 0].sum()
        return (w / ls) if ls else np.inf
    obs = near_pf(d.dist.values)
    hits = 0; draws = []
    for _ in range(2000):
        sh = d.groupby("yr")["dist"].transform(lambda s: rng.permutation(s.values))
        v = near_pf(sh.values); draws.append(v); hits += (v >= obs)
    draws = np.array(draws)
    print("%-5s nearest-quartile PF observed %.3f | null median %.3f, 95th pct %.3f | p = %.4f"
          % (name, obs, np.median(draws), np.percentile(draws, 95), (hits + 1) / 2001))
