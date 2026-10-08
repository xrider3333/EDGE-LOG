"""EARN-FCST r1 MAP CHECK (MANAGER #84) - can ROC 15 at $30k be reached at the literature's effect size?

Noise = the harness's own random beta-neutral books on EARN-FCST's eligible names (gross daily P&L, $1M a side, WF
2018-01..2025-06; no cell or twin P&L is computed). Signal = a constant drift added to each random book: the published
annual hedge return (Chen, Cho, Dou & Lev 2022, JAR: size-adjusted 5.02% - 9.74% a year, all CRSP stocks) x a decay
(McLean & Pontiff 2016: -26% out of sample, -58% after publication; the WF window straddles the 2020 SSRN / 2022 JAR
dates -> x0.55 blended) x a liquid-names haircut (anomalies about halve in the largest names -> x0.5), minus the cost
row (5 bps a side on the assumed monthly turnover, + 1%/yr borrow on the $1M short side).

    python tools/earnfcst_mapcheck.py      (cwd = the shared checkout; EDGELOG_ROOT, XSML_CA as for earnfcst_r1.py)
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import xsml_r1 as X                                                   # noqa: E402
import earnfcst_r1 as E                                               # noqa: E402

N_BOOKS = 300
LIT = {"low 5.02%": 0.0502, "mid 7.38%": 0.0738, "high 9.74%": 0.0974}
DECAY = {"no decay": 1.0, "M-P x0.55": 0.55}
LIQ = {"all stocks": 1.0, "top-500 x0.5": 0.5}
TURN = {"turnover 30%/mo": 0.30, "100%/mo": 1.00}


def main():
    D, beta, w, elig, cell, twin, info = E.setup()
    rng = np.random.default_rng(E.SEED + 84)
    noise = []
    for _ in range(N_BOOKS):
        books = [(t, X.side_books(D, t, elig[t], rng.random(len(elig[t])), beta=beta[D.pos(t)])) for t in w]
        noise.append(X.periodic_book(D, books))
    wfmask = (noise[0].index >= X.WF0) & (noise[0].index <= X.WF1)
    sd = float(np.mean([x[wfmask].std() for x in noise])) * np.sqrt(252)
    rows = []
    for ln, a in LIT.items():
        for dn, dk in DECAY.items():
            for qn, q in LIQ.items():
                for tn, tv in TURN.items():
                    cost = X.COST * (2 * tv * X.GROSS) * 2 * 12 + X.BORROW * X.GROSS   # out + in, both sides, monthly
                    drift = (a * dk * q * X.GROSS - cost) / 252.0
                    roc = np.array([X.roc_sortino(x + np.where(wfmask, drift, 0.0))[0] for x in noise])
                    rows.append(dict(effect=ln, decay=dn, names=qn, turnover=tn, gross_usd_yr=a * dk * q * X.GROSS,
                                     cost_usd_yr=cost, roc_median=float(np.median(roc)),
                                     p_roc_ge_15=float((roc >= 15).mean())))
    R = pd.DataFrame(rows)
    os.makedirs(E.OUT, exist_ok=True)
    R.to_csv(os.path.join(E.OUT, "MAPCHECK.csv"), index=False)
    c = R[(R.effect == "mid 7.38%") & (R.decay == "M-P x0.55") & (R.names == "top-500 x0.5") & (R.turnover == "turnover 30%/mo")].iloc[0]
    best = R.sort_values("roc_median").iloc[-1]
    lines = [f"EARN-FCST r1 MAP CHECK (MANAGER #84): {N_BOOKS} random beta-neutral books on the eligible names as the noise "
             f"(annualised P&L std ${sd:,.0f} on $1M a side); signal = literature hedge return x decay x liquid haircut - costs.",
             f"  CENTRAL (mid 7.38% x0.55 x0.5, 30%/mo turnover): gross ${c.gross_usd_yr:,.0f}/yr, cost ${c.cost_usd_yr:,.0f}/yr "
             f"-> median WF ROC @ $30k {c.roc_median:+.1f}, P(ROC >= 15) {c.p_roc_ge_15:.1%}",
             f"  MOST FAVOURABLE cell of the grid ({best.effect}, {best.decay}, {best.names}, {best.turnover}): median "
             f"{best.roc_median:+.1f}, P(>= 15) {best.p_roc_ge_15:.1%}",
             "  MANAGER's close rule: median under ~8 AND P(>= 15) under ~10% -> close without a Stage A.",
             "  grid: " + "; ".join(f"{r.effect}/{r.decay}/{r.names}/{r.turnover}: {r.roc_median:+.1f} ({r.p_roc_ge_15:.0%})"
                                     for r in R.itertuples())]
    txt = "\n".join(lines)
    print(txt)
    open(os.path.join(E.OUT, "MAPCHECK.txt"), "w", encoding="utf-8").write(txt + "\n")


if __name__ == "__main__":
    main()
