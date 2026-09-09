"""TTM Squeeze round 9 - is ONE ES cell the right leg, or should the book carry an ES-only TTM SUB-BOOK?

Round 7 put three ES contracts of the crown (run 299, ES 30m verified by the hourly squeeze) on the
house baseline and the book improved. It also tried a three-cell TTM book and that FAILED - but the
two extra cells were NQ (15m and 5m), which correlate 0.3-0.4 with the NQ crowns, so it never tested
the honest version of the idea: MORE OF THE SAME UNCORRELATED THING, on ES only.

Round 4 showed the hourly-squeeze verification is net-positive in all twelve base cells (NQ/ES x
5m/15m/30m x both entry styles), so ES 15m and ES 5m are real cells, not scraps. This round runs the
ES ones at the CROWN CONFIG UNCHANGED - no per-timeframe tuning, which is the whole point - and asks
whether adding them to the book beats the single 30m leg the owner adopted.

WEIGHTS ARE A PRIORI, NOT FITTED. Two rules are reported, both fixed before the run:
  FLAT      - 3 contracts of the 30m cell (the adopted book) plus 1 of each extra cell;
  RISK-MATCHED - each extra cell scaled so its own whole-run drawdown equals the 30m cell's at
              weight 3, rounded to one decimal.

BAR (same three clauses as round 8, against the ADOPTED book = baseline + 3 ES of run 299):
  annualised MAR at least 5 percent above it, whole-run drawdown within 5 percent, lockbox at least
  as large. Anything short is recorded and nothing is crowned.

Log: tools/data/ttmsqz_round9_subbook.txt   Driver reuses tools/ttmsqz_round8_crown.py's helpers.
"""
import os, sys, importlib.util, time
import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
r8 = importlib.util.module_from_spec(
    importlib.util.spec_from_file_location("r8", os.path.join(ROOT, "tools", "ttmsqz_round8_crown.py")))
r8.__spec__.loader.exec_module(r8)
r6 = r8.r6
LOG = os.path.join(ROOT, "tools", "data", "ttmsqz_round9_subbook.txt")
COST, MULT, LB_FROM = r8.COST, r8.MULT, r8.LB_FROM
CROWN = r8.CROWN

# The ES cells, all at the crown config; only the tape and the entry style change.
CELLS = [
    ("ES 30m Carter (run 299, the adopted leg)", "ES", "30m", {}),
    ("ES 15m Carter", "ES", "15m", {}),
    ("ES 15m range-break", "ES", "15m", dict(entry_fill="range_break")),
    ("ES 5m Carter", "ES", "5m", {}),
    ("ES 5m range-break", "ES", "5m", dict(entry_fill="range_break")),
]


def main():
    L = ["TTM SQUEEZE ROUND 9 - an ES-only TTM sub-book vs the single adopted leg   %s" % time.strftime("%Y-%m-%d %H:%M"),
         "window %s..%s, lockbox from %s; ES 0.363 pts a round trip, 50 dollars a point; crown config unchanged on every cell"
         % (r8.DATE_FROM, r8.DATE_TO, LB_FROM),
         "BAR vs the adopted book (baseline + 3 ES of run 299): ann. MAR >= x1.05, whole-run DD within 5 percent, lockbox >= it"]
    print("\n".join(L), flush=True)
    base = r8.baseline_daily()
    cells = []
    for name, inst, tf, over in CELLS:
        kw = dict(CROWN); kw.update(over)
        df = r6.load(inst, tf, "RTH")
        t = r8.run_ttm(df, kw, inst=inst)
        if t is None or not len(t):
            L.append("  %-42s no trades" % name); print(L[-1], flush=True); continue
        s = r8.alone_score(t)
        cells.append(dict(name=name, t=t, s=s, daily=r8._daily(t["usd"].values, t["date"])))
        L.append("  %-42s n %4d  PF %5.2f  net $%9s  DD $%7s  MAR %5.2f | LB $%7s  PF %5s  on %d" % (
            name, s["n"], min(s["pf"], 99), "{:,.0f}".format(s["net"]), "{:,.0f}".format(s["dd"]), s["mar"],
            "{:,.0f}".format(s["lb"]), "%.2f" % min(s["lbpf"], 99) if s["lbpf"] == s["lbpf"] else "n/a", s["lbn"]))
        print(L[-1], flush=True)

    # correlations of daily dollars - the only reason a second cell can earn a place
    L.append("")
    L.append("DAILY-PROFIT CORRELATIONS (on days either side traded)")
    names = [c["name"] for c in cells]
    allc = pd.concat([c["daily"].rename(c["name"]) for c in cells] + [base.rename("baseline book")], axis=1).fillna(0.0)
    cm = allc.corr()
    L.append("  %-42s %s" % ("", "  ".join("%8s" % n.split(" ")[1] if " " in n else n for n in names + ["baseline"])))
    for n in names + ["baseline book"]:
        L.append("  %-42s %s" % (n, "  ".join("%8.3f" % cm.loc[n, m] for m in names + ["baseline book"])))
    print("\n".join(L[-len(names) - 2:]), flush=True)

    crown = cells[0]
    adopted = base.add(r8._daily(crown["t"]["usd"].values * 3.0, crown["t"]["date"]), fill_value=0.0).sort_index()
    sa = r8.book_score(adopted)
    H = "  %-46s %11s %9s %6s %11s %9s %6s  %s"
    L.append("")
    L.append(H % ("book", "net $", "DD $", "MAR", "lockbox $", "LB DD $", "yrs+", "verdict"))

    def emit(nm, daily, verdict=""):
        s = r8.book_score(daily)
        if not verdict:
            c1 = s["mar"] >= sa["mar"] * 1.05
            c2 = s["dd"] <= sa["dd"] * 1.05
            c3 = s["lb"] >= sa["lb"]
            verdict = "LEAD - all three clauses" if (c1 and c2 and c3) else "no (%s)" % ", ".join(
                x for x, ok in (("MAR", c1), ("DD", c2), ("LB", c3)) if not ok)
            verdict += "   [MAR x%.3f, DD x%.3f, LB x%.3f vs adopted]" % (
                s["mar"] / sa["mar"], s["dd"] / sa["dd"], s["lb"] / sa["lb"])
        L.append(H % (nm, "{:,.0f}".format(s["net"]), "{:,.0f}".format(s["dd"]), "%.2f" % s["mar"],
                      "{:,.0f}".format(s["lb"]), "{:,.0f}".format(s["lbdd"]), "%d/%d" % (s["ypos"], s["ny"]), verdict))
        print(L[-1], flush=True)
        return s

    emit("BASELINE (ORB 234 + ENGU-Q 309)", base, "reference")
    emit("ADOPTED: baseline + 3 ES of run 299", adopted, "the thing to beat")

    extras = cells[1:]
    flat = adopted.copy()
    for c in extras:
        flat = flat.add(c["daily"], fill_value=0.0)
    emit("FLAT sub-book: adopted + 1 of each ES cell", flat.sort_index())

    target_dd = crown["s"]["dd"] * 3.0
    rm = adopted.copy()
    wl = []
    for c in extras:
        w = round(target_dd / c["s"]["dd"], 1) if c["s"]["dd"] > 0 else 0.0
        w = min(w, 5.0)
        wl.append("%s x%.1f" % (c["name"].replace("ES ", ""), w))
        rm = rm.add(c["daily"] * w, fill_value=0.0)
    emit("RISK-MATCHED sub-book (%s)" % ", ".join(wl), rm.sort_index())

    # one-cell-at-a-time: which single extra, if any, is worth anything
    for c in extras:
        emit("adopted + 1 of %s" % c["name"], adopted.add(c["daily"], fill_value=0.0).sort_index())
    for c in extras:
        emit("adopted + 3 of %s" % c["name"], adopted.add(c["daily"] * 3.0, fill_value=0.0).sort_index())

    # INFORMATION ONLY - the two near misses together. NOT a result: each bar was pre-registered
    # for ONE change, and a combination has to be pre-registered and BOOK-validated on its own.
    ratio = r8.compression_ratio(r6.load("ES", "30m", "RTH"), 60)
    rr = ratio[np.clip(crown["t"]["eb"].values - 1, 0, len(ratio) - 1)]
    deep = np.isfinite(rr) & (rr <= 0.85)
    tilted = np.where(deep, 1.5 * crown["t"]["usd"].values, crown["t"]["usd"].values)
    combo = base.add(r8._daily(tilted * 3.0, crown["t"]["date"]), fill_value=0.0)
    e15 = [c for c in extras if c["name"] == "ES 15m Carter"]
    if e15:
        combo = combo.add(e15[0]["daily"] * 3.0, fill_value=0.0)
        L.append("")
        L.append("INFORMATION ONLY (not a result, not crowned): both near misses at once -")
        emit("  deep-squeeze tilt on the 30m leg + 3 of ES 15m Carter", combo.sort_index())
        L.append("  Each bar above was pre-registered for ONE change. A combination needs its own")
        L.append("  pre-registration and a BOOK validate; stacking two near misses until they clear is")
        L.append("  exactly the search that produces runs like 290.")

    r8._lines_to(L, LOG)
    print("log ->", LOG)


if __name__ == "__main__":
    main()
