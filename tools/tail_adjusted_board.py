"""WHICH LEG IS ACTUALLY BEST ONCE THE TAIL IS TAKEN AWAY?

The owner ranks legs on EV R and R per year, and this project has since proved that on
ENGU-Q's 24-hour tape EV R is largely a TAIL DETECTOR: a high EV R has always come with a
high top-10 concentration, because dividing by the average LOSING trade rewards the
few-enormous-winners shape. Every ranking on the board is therefore open to the same
challenge the owner made about the crown: is this leg better, or is it just better at
accumulating a handful of outliers?

This computes both readings side by side for the crowned legs of every family, on each
family's own market, timeframe and cost:

    HEADLINE     EV R and R per year exactly as the board reports them
    TAIL-ADJUSTED the same two numbers after DELETING each leg's ten biggest winners

Ten trades is the project's existing concentration convention (tools/concentration_check.py),
so this is not a new yardstick - it is the yardstick already in use, applied to the ranking
metric rather than to net profit. The gap between the two readings is the answer: a leg whose
edge is spread barely moves, a leg whose edge IS the tail collapses.

No pass/fail bar. This is a board read, not a search: the output is a RANKING under each
reading, and what matters is whether the order changes.

WINDOW: 2010-06-07..2025-06-29, the common pre-lockbox window the book studies use, so the
sealed year is never touched.

RESULT, 2026-09-09.

  leg                       n     EV R   -top10   -0.5%    R/YR   R/YR ex   top-10
  ENGU-Q crown (R2, live) 1,831   0.503   0.245   0.263    61.1     29.7     51%
  ENGU-Q capped (R3)      2,492   0.343   0.193   0.173    56.8     31.8     44%
  NOISE R/YR frontier     5,548   0.279   0.160   0.004   102.6     58.9     43%
  NOISE crown             3,147   0.194   0.117   0.089    40.6     24.5     40%
  ORB crown (#234)        2,411   0.150   0.086   0.078    24.0     13.7     43%

1. TAIL DEPENDENCE IS UNIVERSAL HERE, not an ENGU-Q defect. Every crowned leg in the library
   loses 40-51% of its EV R to ten trades, across three families and both session types. The
   owner's challenge about the crown applies, in degree, to the whole board.

2. THE FIXED-TEN RANKING IS STABLE. Delete ten trades from each leg and the EV R order does
   not change at all; on R per year the only swap is the capped ENGU-Q overtaking the live
   crown (31.8 vs 29.7) - the first support for the hold cap that does not come from the
   concentration reads themselves.

3. AND THE FIXED-TEN RULE FLATTERS BIG-SAMPLE LEGS, WHICH MATTERS: ten trades is 0.55% of the
   crown's sample but 0.18% of the NOISE frontier's. Under EQUAL treatment - delete the top
   0.5% of each leg's own trades - the frontier collapses from EV R 0.279 to **0.004** (28 of
   5,548 trades removed) and falls from third to LAST, behind the ORB crown. Its edge is
   almost entirely its top half-percent of trades. Nothing else moves much: crown 0.263,
   capped 0.173, NOISE crown 0.089, ORB 0.078.

   That is a correction to how this leg has been read. It passed the existing fixed-ten
   concentration check (top-10 43%, comparable to ORB's 43% and NOISE crown's 40%) precisely
   BECAUSE it trades so often - the check's fixed count cannot see the shape at that sample
   size. Any future concentration read on a high-frequency leg should use the proportional
   column, not the fixed-ten one.

No bar, no queue: this is a board read. What it changes is how much confidence a headline
EV R deserves, and it says the answer depends on the leg's trade count.
"""
import io
import json
import os
import sys

import numpy as np

ROOT = r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"
sys.path.insert(0, ROOT)
os.chdir(ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))
from book_ryr_frontier import arrays, defaults                    # noqa: E402
from augur_engine.engine import run_backtest                      # noqa: E402

SCR = os.path.dirname(os.path.abspath(__file__))

R2 = dict(buf_atr=0.3, tl_len=206, trail_frac=2.5, limit_atr=0.55, atr_len=52, act_R=1.5,
          breakeven_R=2.0, ema_len=220, er_len=100, stop_mult=1.0, regime_len=10,
          min_brk=1.6, vol_mult=1.1, er_th=0.0)

# label, file, instrument, timeframe, session, source, cost, multiplier, params
LEGS = [
    ("ENGU-Q crown (R2, live)", "ENGUQ_1M_ETH_R2_1_0.py", "NQ", "1m", "eth",
     "db_noadj_eth", 0.533, 20.0, dict(R2)),
    ("ENGU-Q capped (R3)", "ENGUQ_1M_ETH_R3_1_0.py", "NQ", "1m", "eth",
     "db_noadj_eth", 0.533, 20.0, dict(R2, max_hold_bars=8280)),
    ("ORB crown (#234)", "ORB_3_6_C2.py", "NQ", "5m", "rth",
     "db_noadj_rth", 0.533, 20.0, None),
    ("NOISE crown", "NOISE_1_0.py", "NQ", "5m", "rth",
     "db_noadj_rth", 0.533, 20.0, None),
    ("NOISE R/YR frontier", "NOISE_1_2_RYR.py", "NQ", "5m", "rth",
     "db_noadj_rth", 0.533, 20.0, {}),
]


def read(pnl, years):
    p = np.asarray(pnl, float)
    w = p[p > 0]
    pf = float(w.sum() / max(-p[p < 0].sum(), 1e-9))
    wr = len(w) / len(p)
    ev = (1 - wr) * (pf - 1)
    return dict(n=len(p), net=float(p.sum()), pf=pf, win=wr * 100, ev_r=ev,
                r_yr=ev * len(p) / years)


def main():
    rows = []
    for label, fn, inst, tf, sess, src, cost, mult, params in LEGS:
        try:
            A = arrays(inst, tf, sess, src)
        except Exception as exc:                                   # noqa: BLE001
            print("  %-26s no data (%s)" % (label, exc), flush=True)
            continue
        p = defaults(fn) if params is None else params
        r = run_backtest(fn, arrays=A, params=p, cost_pts=cost, return_trades=True)
        tr = (r or {}).get("trades") or []
        if len(tr) < 50:
            print("  %-26s only %d trades" % (label, len(tr)), flush=True)
            continue
        idx = A["index"]
        years = (idx[-1] - idx[0]).days / 365.25
        pnl = np.array([t[2] * mult for t in tr], float)
        order = np.argsort(pnl)[::-1]
        keep = np.ones(len(pnl), bool)
        keep[order[:10]] = False
        # A FIXED count of ten is the project's convention, but it is NOT equal treatment
        # across legs: ten trades out of 1,831 is 0.55% of the sample while ten out of 5,548
        # is 0.18%, so a small-sample leg is penalised harder for the same underlying shape.
        # The proportional reading deletes the top 0.5% of each leg's OWN trades instead.
        k = max(1, int(round(len(pnl) * 0.005)))
        keep_p = np.ones(len(pnl), bool)
        keep_p[order[:k]] = False
        full, ex, exp = read(pnl, years), read(pnl[keep], years), read(pnl[keep_p], years)
        top10 = float(pnl[order[:10]].sum() / pnl.sum())
        rows.append(dict(label=label, inst=inst, tf=tf, sess=sess, full=full, ex=ex,
                         ex_prop=exp, prop_k=k, top10=top10))
        print("  %-26s n=%5d  EV R %.3f -> %.3f (top 10) -> %.3f (top %d = 0.5 pct)   "
              "R/YR %6.1f -> %6.1f   top-10 %4.0f%%"
              % (label, full["n"], full["ev_r"], ex["ev_r"], exp["ev_r"], k,
                 full["r_yr"], ex["r_yr"], top10 * 100), flush=True)

    print("\nRANKING ON EV R                headline        tail-adjusted")
    a = sorted(rows, key=lambda r: -r["full"]["ev_r"])
    b = sorted(rows, key=lambda r: -r["ex"]["ev_r"])
    for i in range(len(rows)):
        print("  %d. %-26s %.3f   |   %-26s %.3f"
              % (i + 1, a[i]["label"], a[i]["full"]["ev_r"], b[i]["label"], b[i]["ex"]["ev_r"]))
    print("\nRANKING ON R PER YEAR          headline        tail-adjusted")
    a = sorted(rows, key=lambda r: -r["full"]["r_yr"])
    b = sorted(rows, key=lambda r: -r["ex"]["r_yr"])
    for i in range(len(rows)):
        print("  %d. %-26s %6.1f  |   %-26s %6.1f"
              % (i + 1, a[i]["label"], a[i]["full"]["r_yr"], b[i]["label"], b[i]["ex"]["r_yr"]))
    print("")
    print("RANKING ON EV R, PROPORTIONAL (top 0.5 pct of each leg own trades deleted)")
    for i, r in enumerate(sorted(rows, key=lambda r: -r["ex_prop"]["ev_r"]), 1):
        print("  %d. %-26s %.3f   (deleted %d of %d trades)"
              % (i, r["label"], r["ex_prop"]["ev_r"], r["prop_k"], r["full"]["n"]))
    print("\nLARGEST COLLAPSE (headline EV R minus tail-adjusted, biggest first):")
    for r in sorted(rows, key=lambda r: -(r["full"]["ev_r"] - r["ex"]["ev_r"])):
        d = r["full"]["ev_r"] - r["ex"]["ev_r"]
        print("  %-26s -%.3f  (%.0f%% of its EV R was ten trades)"
              % (r["label"], d, d / r["full"]["ev_r"] * 100 if r["full"]["ev_r"] else 0))
    json.dump(rows, io.open(os.path.join(SCR, "_tail_board.json"), "w"), indent=1,
              default=float)
    print("SAVED")


if __name__ == "__main__":
    main()
