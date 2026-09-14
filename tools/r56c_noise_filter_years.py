# -*- coding: utf-8 -*-
"""Year by year and ex-top-10 for the hourly squeeze filter on the live crown (and the crown raw)."""
exec(open(__import__("os").path.join(__import__("os").path.dirname(__import__("os").path.abspath(__file__)), "r56b_noise_squeeze_filter.py"), encoding="utf-8").read().split('print("%-30s')[0])
b, d, p = trades(CROWN, 0.533)
m = np.array([bool(COMP["hourly gate"][i - 1]) for i in b])
yrs = np.array([x.year for x in d])
print("year |  crown n    net $    PF | filter n   net $     PF | rest-of-crown PF")
lose = 0
for y in range(2010, 2027):
    k = yrs == y
    q, f, r = p[k], p[k & m], p[k & ~m]
    lose += f.sum() < 0
    print("%d | %6d %9s %6.3f | %6d %8s %6.3f | %6.3f" % (y, len(q), format(int(q.sum()), ","), pf(q), len(f),
          format(int(f.sum()), ","), pf(f) if (f < 0).any() else 99, pf(r)))
f = np.sort(p[m])
print("filter: losing years %d of 17 | ex-top-10 net $%s PF %.3f | ex-top-20 PF %.3f | rest of the crown (not compressed) PF %.3f"
      % (lose, format(int(f[:-10].sum()), ","), pf(f[:-10]), pf(f[:-20]), pf(p[~m])))
