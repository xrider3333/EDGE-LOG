"""MAPCHECK-F - the house's FUTURES / BOOK power-first check (Custom ML, MANAGER #91 GO; built on FRONTIER's MDL r1, OK #92).

Before a futures or book idea gets a pre-registration, put its PRIOR on the map: how strong it plausibly is after decay and costs
(a yearly Sharpe ratio, with an uncertainty), how often it trades, how fat its tails are and how it moves in BOOK #463's drawdown
weeks. MAPCHECK-F draws M synthetic legs from that prior with MDL r1's own generator (tools/rocfrontier/r12_mdl.py gen_leg, imported
unchanged), adds each to the book the way MDL r1 does (size c in 0.5 / 1 / 2 x a unit, c frozen on the WF ROC) and prints:
  * the leg's OWN walk-forward ROC @ $30k (median, P(>= 15) - the MDL map line for an uncorrelated leg),
  * P(book lift) on #463: book WF ROC >= 98.5 (1.05 x 93.81) AND Sortino >= 3.816 - WALK-FORWARD ONLY (#463's lockbox is SPENT,
    BOOK LOOKS r1; no lockbox figure is printed),
  * the same read on the S1 line (#463 + 0.264 x RES, file e204dd53, 121.06 / Sortino 3.926): its bar = 1.05 x its own WF ROC with its
    own Sortino (MDL r1 has no S1 mode; this tool adds it with the same generator on the line's own drawdown weeks).
A synthetic prior is NOT a book look. A pilot daily series of real data added to #463 IS one - this tool refuses a pilot; route that to
MANAGER's BOOK LOOKS tally first.

Pins (FRONTIER #92): r12_mdl / r12_refs imported read-only; MDL r1's SEED and M_DRAWS untouched (each prior uses its OWN seed,
printed); #463 from r11_risk's cache, refused unless WF 93.81 / 3.816 reproduce; EDGELOG_ROCFRONTIER_MDL pointed at this tool's own
folder before the import, so MDL r1's record is never written.

    python tools/mapcheck_f.py            every prior in PRIORS below -> C:\\EdgeLog\\custom_ml\\mapcheck_f\\MAPCHECK_F.txt / .csv
    python tools/mapcheck_f.py NAME ...   only those priors
Close rule (MANAGER #84, used for EARN-FCST / LAZY-PRICES): median own ROC under ~8 AND P(own ROC >= 15) under ~10% -> close at draft;
a leg that earns while the book falls is read on P(book lift) instead (the map: it helps at almost any positive return).
"""
import math
import os
import sys

OUT = r"C:\EdgeLog\custom_ml\mapcheck_f"
os.environ["EDGELOG_ROCFRONTIER_MDL"] = os.path.join(OUT, "_mdl_scratch")      # MDL r1's own folder is never the target
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "rocfrontier"))
sys.path.insert(0, os.path.dirname(HERE))

import numpy as np                                                       # noqa: E402
import pandas as pd                                                      # noqa: E402
import r11_risk as R11                                                   # noqa: E402
import r12_mdl as M12                                                    # noqa: E402
from augur_engine import seat_pipeline as SP                             # noqa: E402

S1_FILE = r"C:\EdgeLog\_anatomy_cache\rocfrontier\resmom_r1\resmom_cells_daily_wf_close.csv"
S1_SHA = "e204dd53419a22bc"
M = 2000
SEED0 = 20261010                                                         # this tool's own seed base; prior k uses [SEED0, k]

# ------------------------------------------------------------------------------------------------ the priors
# s_mid / s_sd: the leg's yearly Sharpe ratio AFTER costs and after decay / winner's-curse shrink (stated per row), drawn ~ Normal(s_mid,
# s_sd) per synthetic leg. n: trades a year. rho_dd: its correlation with the book in the book's drawdown weeks; rho_out 'zero' = flat
# with the book elsewhere, 'same' = the same coupling all the time. tails / vol as MDL r1. src: where the prior comes from.
PRIORS = [
    dict(name="AUCTION-K5", n=24, s_mid=0.33, s_sd=0.30, rho_dd=-0.15, rho_out="zero", tails="t3", vol="const",
         src="TV new-type r2 (ledger 2.70): TLT pre-auction short, t 1.997 over the WF ~9 yr -> yearly Sharpe ~0.67, halved for the "
             "near-miss selection; rates sell-offs (2022, 2025) are #463 drawdown years -> mildly negative rho"),
    dict(name="MONTHEND-ES", n=8, s_mid=0.45, s_sd=0.30, rho_dd=0.0, rho_out="zero", tails="t3", vol="const",
         src="ledger 2.18: ES K=5 2% threshold, PF 2.27, 12/16 years, MAR 0.49 (~ROC 14.7 own) -> Sharpe ~0.6, x0.75 published-effect "
             "decay; 8 trades a year (greyed: < 50 sealed-year trades)"),
    dict(name="OVERNIGHT-DOWNDAY", n=100, s_mid=0.15, s_sd=0.15, rho_dd=0.0, rho_out="zero", tails="t3", vol="clustered",
         src="ledger 2.13: long NQ 01:30-04:00 after a down session, $16.6 a trade (9/16 years); per-trade Sharpe ~0.015 x sqrt(100)"),
    dict(name="MACRO830-FADE", n=23, s_mid=0.30, s_sd=0.30, rho_dd=0.0, rho_out="zero", tails="t3", vol="clustered",
         src="ledger 2.95 NT1: fading the 08:30 CPI / payroll move on NQ, t 1.77 on 210 WF trades (under the coin-flip null) -> "
             "Sharpe ~0.59, halved"),
    dict(name="GEX-MOMENTUM", n=250, s_mid=0.35, s_sd=0.25, rho_dd=0.3, rho_out="same", tails="t3", vol="clustered",
         src="Baltussen-Da-Lammers-Martens 2021 (hedging demand and market intraday momentum): last-half-hour index momentum, "
             "stronger when dealers are short gamma; the house's own unconditioned test died (ledger 2.5, 0 of 40 cells; the own-"
             "morning twin 10.72 in 2.74 is NOISE's continuation) - so the prior is the GAMMA CONDITIONING's lift only, ~0.35; "
             "momentum-shaped -> moves with #463 (+0.3). Data: SqueezeMetrics GEX photographed 10-08 (catalog row 15)"),
    dict(name="TRANSFER-CME", n=400, s_mid=0.20, s_sd=0.35, rho_dd=0.15, rho_out="same", tails="t3", vol="clustered",
         src="ledger 2.29 (pre-registered, never run): ORB / NOISE / TTM cores on ZN / 6E / CL / GC via Databento; the fund-proxy "
             "version (2.49 TRANSFER r2) died -> prior ~0 to small; the cores are momentum -> mild positive rho"),
    dict(name="XLK-NOISE (reference)", n=314, s_mid=1.10, s_sd=0.30, rho_dd=0.5, rho_out="same", tails="t3", vol="clustered",
         src="ledger 2.108: measured own ROC 32.27 (2,829 trades), corr 0.74 with NOISE #422 / 0.51 with #463 -> a with-book leg; "
             "the measured book add (98.6, bootstrap p5 -20.9) is the check on this tool's calibration"),
]


# ------------------------------------------------------------------------------------------------ the engine
def book463():
    legs_meta = R11.load_json("build.json")["legs"]
    B = R11.load_book("U", legs_meta)
    got = M12.reproduce(B)
    assert abs(got["WF"]["roc"] - 93.81) < 0.005 and abs(got["WF"]["sort"] - 3.816) < 0.0005, f"#463 does not reproduce: {got['WF']}"
    return np.asarray(B.raw, float), B.index


def line_s1():
    D = SP.load_pinned_daily(S1_FILE, S1_SHA)
    L = SP.line_L(D["book_mtm"], D["RES"])
    SP.check_parity(SP.window(L), "line_L")
    return L.to_numpy(float), pd.DatetimeIndex(L.index)


def legs_from_prior(S, V, p, M, rng):
    """M legs on stretch S: MDL r1's gen_leg at s = 0, then each row's own drift s_i V / (252 q) on its active days."""
    q = min(1.0, p["n"] / 252.0)
    rho_out = 0.0 if p["rho_out"] == "zero" else p["rho_dd"]
    leg = M12.gen_leg(S.z, S.dd, S.g[p["vol"]], V, 0.0, p["n"], p["rho_dd"], rho_out, p["tails"], M, rng)
    s = rng.normal(p["s_mid"], p["s_sd"], M)
    active = leg != 0.0
    return leg + (s * V / (252.0 * q))[:, None] * active, s


def read(S, V, p, M, seed, bar_roc, bar_sort):
    leg, s = legs_from_prior(S, V, p, M, np.random.default_rng(seed))
    own = M12.vmeas(leg, S.years)
    rho, do = M12.realised(leg, S)
    roc3, sort3 = np.empty((len(M12.CS), M)), np.empty((len(M12.CS), M))
    for i, c in enumerate(M12.CS):
        roc3[i], sort3[i] = M12.vstats(S.x + c * leg, S.years)
    ci, cols = M12.pick_c(roc3), np.arange(M)
    roc, sort = roc3[ci, cols], sort3[ci, cols]
    lift = (roc >= bar_roc) & (sort >= bar_sort)
    return {"own_med": float(np.nanmedian(own["roc"])), "own_p15": float(np.mean(own["roc"] >= 15)),
            "own_usd_med": float(np.nanmedian(own["ann"] / own["mdd"] * 30000.0)), "rho_med": float(np.nanmedian(rho)),
            "do_med": float(np.nanmedian(do)), "lift": float(np.mean(lift)), "book_roc_med": float(np.nanmedian(roc))}


def main(names=None):
    os.makedirs(OUT, exist_ok=True)
    x, dates = book463()
    SW, _, V = M12.build_stretches(x, dates)
    xs, ds = line_s1()
    LW = M12.Stretch(xs, ds, M12.trail_std(xs), *M12.WINDOWS["WF"])   # the S1 file holds WF rows only (no LB stretch)
    VL = M12.unit_vol(LW.x)
    bar_s1 = (1.05 * LW.stats["roc"], LW.stats["sort"])
    lines = [f"MAPCHECK-F (Custom ML; MDL r1's generator, FRONTIER OK #92) - {M} synthetic legs per prior, seed [{SEED0}, k]; WALK-FORWARD only "
             f"(#463's lockbox is spent). #463 WF {SW.stats['roc']:.2f} / {SW.stats['sort']:.3f}, bar {M12.BAR_WF_ROC:.2f} / {M12.BAR_WF_SORT:.3f}; "
             f"S1 line WF {LW.stats['roc']:.2f} / {LW.stats['sort']:.3f}, bar {bar_s1[0]:.2f} / {bar_s1[1]:.3f}. Unit volatility "
             f"${V:,.0f} a year (MDL r1's: 1/3 of the book's).",
             "Close rule (MANAGER #84): median own ROC < ~8 AND P(own >= 15) < ~10% -> close at draft, unless the leg earns while the book "
             "falls (then P(book lift) decides). Fewer than 50 trades a year = greyed (cannot make 50 sealed-year trades)."]
    rows = []
    for k, p in enumerate(PRIORS):
        if names and p["name"] not in names:
            continue
        a = read(SW, V, p, M, [SEED0, k, 0], M12.BAR_WF_ROC, M12.BAR_WF_SORT)
        b = read(LW, VL, p, M, [SEED0, k, 1], *bar_s1)
        closes = a["own_med"] < 8 and a["own_p15"] < 0.10 and a["rho_med"] > -0.15
        verdict = ("GREYED (< 50 trades a year)" if p["n"] < 50 else "") + (" CLOSE at draft" if closes else " CLEARS - worth a prereg")
        rows.append(dict(name=p["name"], n=p["n"], s_mid=p["s_mid"], s_sd=p["s_sd"], rho_dd=p["rho_dd"], own_med=a["own_med"],
                         own_p15=a["own_p15"], rho_real=a["rho_med"], do_med=a["do_med"], lift463=a["lift"], lift_s1=b["lift"],
                         book_roc_med=a["book_roc_med"], verdict=verdict.strip()))
        lines.append(f"\n{p['name']}: n {p['n']}/yr, yearly Sharpe {p['s_mid']:.2f} +- {p['s_sd']:.2f}, rho_dd {p['rho_dd']:+.2f} "
                     f"({p['rho_out']}), {p['tails']} tails, {p['vol']} vol")
        lines.append(f"  own WF ROC @ $30k: median {a['own_med']:+.1f}, P(>= 15) {a['own_p15']:.0%}; realised rho_dd {a['rho_med']:+.2f}, DO "
                     f"{a['do_med']:+.3f}")
        lines.append(f"  P(book lift, WF): #463 {a['lift']:.0%} (median book ROC {a['book_roc_med']:.1f}), S1 line {b['lift']:.0%}")
        lines.append(f"  -> {verdict.strip()}")
        lines.append(f"  prior source: {p['src']}")
    txt = "\n".join(lines)
    print(txt)
    open(os.path.join(OUT, "MAPCHECK_F.txt"), "w", encoding="utf-8").write(txt + "\n")
    pd.DataFrame(rows).to_csv(os.path.join(OUT, "MAPCHECK_F.csv"), index=False)


if __name__ == "__main__":
    main(sys.argv[1:] or None)
