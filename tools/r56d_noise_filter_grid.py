# -*- coding: utf-8 -*-
"""The squeeze FILTER's whole 27-cell neighbourhood (run 321's pre-registered grid) on both bases,
continuous replay, house cost. Plateau or spike?"""
exec(open(__import__("os").path.join(__import__("os").path.dirname(__import__("os").path.abspath(__file__)), "r56b_noise_squeeze_filter.py"), encoding="utf-8").read().split('print("%-30s')[0])
import itertools
print("%-9s %-14s | %5s %9s %6s | %6s %6s %6s | %s" % ("base", "gate tf/len/r", "n", "net $", "PF", "PF<24", "PF24+", "sealPF", ""))
for blab, base in (("#304", CROWN), ("#243", V243)):
    b, d, p = trades(base, 0.533)
    rows = []
    for tf, ln, ra in itertools.product((30, 60, 120), (16, 20, 24), (0.85, 1.0, 1.15)):
        c = SQ._compression(H, L, C, A["day_id"], A["index"], tf, ln, ra)
        m = np.array([bool(c[i - 1]) for i in b])
        q, qd = p[m], d[m]
        rows.append((tf, ln, ra, len(q), q.sum(), pf(q), pf(q[qd < B0]), pf(q[qd >= B0]), pf(q[qd >= S0])))
    for r in rows:
        tag = " <- textbook" if r[:3] == (60, 20, 1.0) else (" <- run 321 pick" if r[:3] == (30, 16, 1.15) else "")
        print("%-9s %-14s | %5d %9s %6.3f | %6.3f %6.3f %6.3f |%s" % (blab, "%d/%d/%.2f" % r[:3], r[3], format(int(r[4]), ","), r[5], r[6], r[7], r[8], tag))
    arr = np.array([r[5] for r in rows]); b24 = np.array([r[7] for r in rows])
    hourly = [r for r in rows if r[0] == 60]
    print("  %s: %d of 27 cells PF > raw base %.3f; 2024+ PF > raw in %d of 27; hourly cells full PF %.3f-%.3f, 2024+ %.3f-%.3f; textbook ranks %d of 27 on full PF"
          % (blab, int((arr > pf(p)).sum()), pf(p), int((b24 > pf(p[d >= B0])).sum()),
             min(r[5] for r in hourly), max(r[5] for r in hourly), min(r[7] for r in hourly), max(r[7] for r in hourly),
             1 + int((arr > [r[5] for r in rows if r[:3] == (60, 20, 1.0)][0]).sum())))
    print()
