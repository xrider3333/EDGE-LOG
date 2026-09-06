"""IMPROVE THE CROWN — #309's risk knobs, one at a time (2026-09-05)

Run #309 is the crowned ENGU-Q leg and sits on the paper board. Measured on
2010-06-07..2026-06-30, NQ 1m ETH, cost 0.533 x $20:

    n=1,604   net $591,267   PF 1.655   EV R 0.434   R/YR 43.4
    drawdown $48,900   MAR 0.75   held-out 99 trades   top-10 share 58%   longest hold 282d

Its weakest number by a distance is MAR: it earns about $36,800 a year against a $48,900
drawdown. Profit factor and EV R are the best in the library; the risk side is not.

The crown's own search maximised net and drawdown together, not MAR, and it pushed
breakeven_R to 3.0 - the very top of that knob's range - which means it preferred the stop
to interfere as little as possible. That is exactly the setting that lets a winner run into
a 282-day hold and puts 58% of the net into ten trades. So the risk knobs are where an
improvement should be, and nobody has swept them AROUND the crown.

This is a ONE-KNOB-AT-A-TIME sweep, deliberately: the crown is a validated configuration and
the point is to find whether a single honest change makes it better, not to re-search the
space and crown a fresh over-fit. Every cell keeps all of #309's other params.

PRE-REGISTERED, written before running. A cell is an IMPROVEMENT only if it is arguably
better rather than a trade of one number for another:
    MAR up by >= 15%  AND  R/YR not down by more than 5%   (the risk case)
    or R/YR up by >= 15%  AND  MAR not down by more than 5%  (the frequency case)
and in BOTH cases the tail guard must hold: top-10 share <= 58% (no worse than the crown),
still profitable excluding the top ten, and >= 90 held-out trades.
Anything that improves one read by wrecking another is reported and rejected.
"""
import io
import os
import sys
import json

SCR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCR)
from frontier_trio_es import leg_trades, score, show, ENG309  # noqa: E402

SWEEP = {
    "breakeven_R": [0.0, 1.0, 1.5, 2.0, 2.5],       # crown 3.0 (top of range)
    "stop_mult":   [0.8, 1.0, 1.6, 2.0],            # crown 1.3
    "act_R":       [0.5, 1.0, 2.0, 2.5],            # crown 1.5
    "trail_frac":  [1.5, 2.0, 3.0],                 # crown 2.5
    "limit_atr":   [0.0, 0.35, 0.75],               # crown 0.55
    "regime_len":  [0, 5, 20],                      # crown 10
}


def leg(p):
    return leg_trades("ENGUQ_1M_ETH_ER_1_0.py", p, "NQ", "1m", "eth", "db_noadj_eth", 0.533, 20)


if __name__ == "__main__":
    base = score(leg(ENG309), "#309 CROWN (base)")
    print("BASE"); show(base)
    b_mar, b_ryr = base["mar"], base["r_yr"]

    out, wins = {"base": base}, []
    for knob, vals in SWEEP.items():
        print("\n%s  (crown = %s)" % (knob, ENG309[knob]))
        for v in vals:
            p = dict(ENG309); p[knob] = v
            s = score(leg(p), "%s=%s" % (knob, v))
            if s is None:
                print("  %s=%-6s NO TRADES" % (knob, v)); continue
            show(s)
            out[s["label"]] = s
            dm = (s["mar"] - b_mar) / b_mar
            dr = (s["r_yr"] - b_ryr) / b_ryr
            guard = (s["top10"] <= base["top10"] and s["ex10"] > 0 and s["lb_n"] >= 90)
            ok = guard and ((dm >= 0.15 and dr >= -0.05) or (dr >= 0.15 and dm >= -0.05))
            print("      MAR %+.0f%%  R/YR %+.0f%%  guard %s  -> %s"
                  % (dm * 100, dr * 100, "ok" if guard else "FAIL",
                     "IMPROVEMENT" if ok else "no"))
            if ok:
                wins.append((s["label"], knob, v, s, dm, dr))

    print("\n" + "=" * 100)
    print("IMPROVEMENTS:", [w[0] for w in wins] or "NONE")
    for lbl, knob, v, s, dm, dr in wins:
        print("  %-18s MAR %.2f (%+.0f%%)  R/YR %.1f (%+.0f%%)  EV R %.3f  top-10 %.0f%%  LB %d"
              % (lbl, s["mar"], dm * 100, s["r_yr"], dr * 100, s["ev_r"], s["top10"] * 100, s["lb_n"]))

    json.dump({"base": base, "cells": out,
               "improvements": [w[0] for w in wins]},
              io.open(os.path.join(SCR, "_enguq309_risk.json"), "w"), indent=1, default=float)
    print("SAVED")
