"""STRATEGY-BEATING map checks of 2026-10-12 (MANAGER #167 follow-ups: the 30-min-to-1-day ROI hunt, then #682's NOISE controls):
five ideas put on the power-first map with Custom ML's tools/mapcheck_f.py core imported UNCHANGED (book463 / line_s1 / read), each
prior set with its own seed base, written to its own folder. MDL r1's and MAPCHECK-F's record files are never written: r12_mdl is
imported FIRST with EDGELOG_ROCFRONTIER_MDL pointed at this run's own scratch folder.

    python tools/rocfrontier/r29_mapcheck_1012.py ideas       MEGACAP-EARN, AUCTION-1300            (seed [20261012, k])
    python tools/rocfrontier/r29_mapcheck_1012.py noisectrl   NOISE-SPY, NOISE-DIA, NOISE-GLD       (seed [20261013, k])

Verdict rules are MAPCHECK-F's: < 50 trades a year = GREYED; median own ROC < 8 AND P(own >= 15) < 10% (and not a book-falling
earner) = close; P(lifting #463, WF) < 30% = close. A synthetic prior is not a book look; nothing here reads real P&L.
"""
import os
import sys

OUT = r"C:\EdgeLog\_anatomy_cache\rocfrontier\mapcheck_sb1012"
os.makedirs(OUT, exist_ok=True)
os.environ["EDGELOG_ROCFRONTIER_MDL"] = os.path.join(OUT, "_mdl_scratch")
HERE = os.path.dirname(os.path.abspath(__file__))
for p in (os.path.dirname(os.path.dirname(HERE)), os.path.dirname(HERE), HERE):
    if p not in sys.path:
        sys.path.insert(0, p)
import r12_mdl as M12                                    # noqa: E402  (first import: binds the scratch path above)
import mapcheck_f as MF                                  # noqa: E402
assert MF.M12 is M12
import pandas as pd                                      # noqa: E402

SETS = {
    "ideas": (20261012, "MAPCHECK_SB1012", [
        dict(name="MEGACAP-EARN", n=36, s_mid=0.20, s_sd=0.30, rho_dd=0.0, rho_out="zero", tails="t3", vol="clustered",
             src="NQ next cash session after an NDX top-9 name's after-hours earnings gap (~9 names x 4 = 36 a year), continuation or "
                 "fade by the gap; the house's index gap continuation AND gap fade are both dead (MISC r17, GAPFADE), the earnings family "
                 "is closed for baskets (MANAGER #84) and one name moves NQ by a fraction of its own gap -> small prior, Sharpe 0.2 +- 0.3"),
        dict(name="AUCTION-1300", n=100, s_mid=0.15, s_sd=0.25, rho_dd=0.0, rho_out="zero", tails="t3", vol="clustered",
             src="NQ 13:01-16:00 after a Treasury coupon auction, side by the auction's bid-to-cover against its own trailing average "
                 "(~100 coupon auctions a year); XASSET (bonds -> NQ/ES, daily) lost to buy-and-hold, AUCTION r2's edge was in the "
                 "PRE-auction rates move not the equity reaction -> Sharpe 0.15 +- 0.25"),
    ]),
    "noisectrl": (20261013, "MAPCHECK_SB1012_NOISECTRL", [
        dict(name="NOISE-SPY", n=300, s_mid=0.30, s_sd=0.40, rho_dd=0.50, rho_out="same", tails="t3", vol="clustered",
             src="ES = SPY's index: NOISE transferred best PF 1.126, re-tuned natively PF 1.35 in selection then 0.99 on its holdout "
                 "(NOISE.md 08-22) -> after the winner's curse ~0.3 +- 0.4; an equity-index trend leg moves with #463 like XLK (corr 0.51) "
                 "-> rho_dd 0.5"),
        dict(name="NOISE-DIA", n=300, s_mid=0.20, s_sd=0.40, rho_dd=0.45, rho_out="same", tails="t3", vol="clustered",
             src="the Dow is close to ES (dead twice) and further from NQ's tape -> below SPY's prior; with-book like SPY"),
        dict(name="NOISE-GLD", n=250, s_mid=0.10, s_sd=0.40, rho_dd=0.00, rho_out="zero", tails="t3", vol="clustered",
             src="unchanged NOISE on GLD PF 0.91 (TRANSFER r2, ledger 2.49, seen); gold's price discovery sits outside US hours; "
                 "own-crown re-tune is a new question with a low prior -> 0.1 +- 0.4; uncorrelated"),
    ]),
}


def run(which):
    seed0, stem, priors = SETS[which]
    x, dates = MF.book463()
    SW, _, V = M12.build_stretches(x, dates)
    xs, ds = MF.line_s1()
    LW = M12.Stretch(xs, ds, M12.trail_std(xs), *M12.WINDOWS["WF"])
    VL = M12.unit_vol(LW.x)
    bar_s1 = (1.05 * LW.stats["roc"], LW.stats["sort"])
    lines = [f"MAPCHECK (STRATEGY-BEATING 10-12) with MAPCHECK-F's core unchanged - {MF.M} legs per prior, seed [{seed0}, k]; WF only. "
             f"#463 WF {SW.stats['roc']:.2f} / {SW.stats['sort']:.3f}, bar {M12.BAR_WF_ROC:.2f} / {M12.BAR_WF_SORT:.3f}; S1 line WF "
             f"{LW.stats['roc']:.2f} / {LW.stats['sort']:.3f}, bar {bar_s1[0]:.2f} / {bar_s1[1]:.3f}."]
    rows = []
    for k, p in enumerate(priors):
        a = MF.read(SW, V, p, MF.M, [seed0, k, 0], M12.BAR_WF_ROC, M12.BAR_WF_SORT)
        b = MF.read(LW, VL, p, MF.M, [seed0, k, 1], *bar_s1)
        closes = a["own_med"] < 8 and a["own_p15"] < 0.10 and a["rho_med"] > -0.15
        if p["n"] < 50:
            verdict = "GREYED - cannot be a seat on its own (< 50 trades a year)"
        elif closes:
            verdict = "CLOSE at draft (own-ROC rule)"
        elif a["lift"] < MF.LIFT_MIN:
            verdict = f"CLOSE at draft (P(book lift) {a['lift']:.0%} < {MF.LIFT_MIN:.0%})"
        else:
            verdict = "CLEARS - worth a prereg"
        rows.append(dict(name=p["name"], n=p["n"], s_mid=p["s_mid"], s_sd=p["s_sd"], own_med=a["own_med"], own_p15=a["own_p15"],
                         own_usd_med=a["own_usd_med"], lift463=a["lift"], lift_s1=b["lift"], book_roc_med=a["book_roc_med"], verdict=verdict))
        lines += [f"\n{p['name']}: n {p['n']}/yr, yearly Sharpe {p['s_mid']:.2f} +- {p['s_sd']:.2f}, rho_dd {p['rho_dd']:+.2f}",
                  f"  own WF ROC @ $30k: median {a['own_med']:+.1f} (${a['own_usd_med']:,.0f} a year), P(>= 15) {a['own_p15']:.0%}",
                  f"  P(book lift, WF): #463 {a['lift']:.0%} (median book ROC {a['book_roc_med']:.1f}), S1 line {b['lift']:.0%}",
                  f"  -> {verdict}", f"  prior: {p['src']}"]
    txt = "\n".join(lines)
    print(txt)
    open(os.path.join(OUT, stem + ".txt"), "w", encoding="utf-8").write(txt + "\n")
    pd.DataFrame(rows).to_csv(os.path.join(OUT, stem + ".csv"), index=False)


if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in SETS:
        raise SystemExit("usage: r29_mapcheck_1012.py ideas | noisectrl")
    run(sys.argv[1])
