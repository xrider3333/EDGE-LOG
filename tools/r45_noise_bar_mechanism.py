#!/usr/bin/env python3
"""NOISE ROUND 45 (2026-09-09) -- WHY does the fatter bar help, and where does it stop helping?

WHY THIS RUNS (owner: "keep testing noise")
-------------------------------------------
Round 44 measured the live crown geometry, unchanged, across bar sizes and found the 5-minute bar
it trades is beaten badly by 10 and 15 minutes: at the stressed cost, net-over-drawdown 17.82 (5m)
against 30.11 (10m) and 34.52 (15m), with MORE money on 38% fewer trades and half the drawdown. It
queued a full-space Auto-Validate on the registered 15m master and stopped there. Two questions were
left, and they decide what the recommendation to the owner actually is:

  A. WHERE DOES THE LADDER PEAK? Round 44 stopped at 15 minutes because that is the largest
     registered master it could gate against. If net-over-drawdown is still climbing at 30 or 60
     minutes then "15m is better" is the wrong headline -- the real finding would be "this strategy
     wants to trade far less often than it does", which is a different claim and a different
     validate. Round 5 walked 1m-60m in 2026-08 but ranked on MONEY, which hides exactly this.

  B. IS THE BAR A PROXY FOR A KNOB? This is the question that changes the cost of acting. A bar
     change means a new chart, a new NinjaTrader configuration and a re-port. If instead the fatter
     bar is doing something the strategy ALREADY has a knob for -- confirming for longer before
     entering, or holding through more noise before stopping out -- then the same benefit is
     available on the 5-minute bar for the price of one number, with no chart change and no re-port.
     Three mechanisms are plausible and separable:
       * CONFIRMATION: a 15m close is three 5m closes of agreement, so `confirm_bars` 1 -> 3 on 5m
         is the direct analogue.
       * PATIENCE: the exit and the stop are only checked when a bar CLOSES, so a fatter bar holds
         through intra-bar noise a 5m bar would react to. `stop_k` (the bandwidth stop multiple) is
         the knob that widens the same tolerance on 5m.
       * RESOLUTION: the band's own volatility estimate is indexed by bar ORDINAL within the session
         (round 5's correction -- `lookback` counts SESSIONS, not bars), so a fatter bar genuinely
         changes the resolution of the intraday volatility profile. This one has NO knob. If the 5m
         grid cannot reach 15m behaviour, this is what is left, and the bar itself is the lever.

PRE-REGISTRATION (fixed before any cell ran)
---------------------------------------------
Part A is descriptive: report net-over-drawdown, profit factor, slices, concentration, dollars a
trade and median hold for 5/10/15/20/30/45/60 minutes at three costs. No bar is adopted here; the
15m Auto-Validate already queued (job kzTWeRL5SR5c0po62KOM) is the evidence step.

Part B is a decision:
  * the 5-minute grid is `confirm_bars` x `stop_k` around the crown, everything else pinned;
  * the bar is declared A PROXY FOR A KNOB only if some 5m cell reaches **at least 90% of the 15m
    cell's net-over-drawdown at the stressed cost 0.783** while keeping profit factor >= the 15m
    cell's, at least as many chronological slices, and top-10 share no more than 5 points worse;
  * if the best 5m cell falls short of that, the honest conclusion is that the bar carries something
    the knobs cannot express, and the chart change is the real proposal.
  * EITHER WAY NOTHING IS ADOPTED HERE. A winning 5m cell would be a mechanism explanation and would
    need its own Auto-Validate; this file crowns nothing and touches no board.

Guard against fooling myself: this grid is SMALL and pre-declared (4 x 5 = 20 cells), it is ranked on
net-over-drawdown and profit factor rather than EV R (an out-of-range stop or an early breakeven can
inflate EV R -- memory `edgelog-evr-gameable-by-breakeven`), and the whole point is to EXPLAIN round
44 rather than to find a new champion. A 5m cell that wins here is a hypothesis, not a result.

DATA. One source tape: the registered NQ 1m RTH master resampled in-file (round 44's resampler),
2010-06-07 -> 2026-07-16, entry-sliced at 2025-02-14, the spent stretch confirmatory only. THREE
parity gates -- resampled 5m, 15m and 30m must each reproduce their registered master on the crown
geometry, each clipped to that master's own last bar (round 44's calendar lesson).

Usage:  python tools/r45_noise_bar_mechanism.py
Writes: tools/r37_results/r45_ladder.csv, r45_knobgrid.csv, r45_mechanism.txt
"""
import csv
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.environ.get("EDGELOG_REPO_ROOT") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))
os.chdir(ROOT)

from augur_engine.data import find_master, load_master_arrays  # noqa: E402
from augur_engine.engine import run_backtest  # noqa: E402
from r41_bar_ladder_overlap import resample  # noqa: E402

FN = "NOISE_1_0.py"
MULT = 20.0
SRC = "db_noadj_rth"
WIN = dict(date_from="2010-06-07", date_to="2026-07-16")
SPLIT = "2025-02-14"
COSTS = [0.533, 0.783, 1.033]
BARS = [5, 10, 15, 20, 30, 45, 60]
STRESS = 0.783

CROWN = dict(lookback=40, band_mult_long=0.75, band_mult_short=1.5, exit_mode="vwap",
             side="Both", window="all_day", flat_eod=True, skip_holidays=False,
             stop_mode="bandwidth", stop_k=1.75, daytype_mode="skip_bot_short",
             daytype_lo=0.2, daytype_hi=0.8, vol_skip_pct=95.0)

CONFIRMS = [1, 2, 3, 4]
STOPS = [1.75, 2.5, 3.5, 5.0, 7.0]


def metrics(rows, years, bar_min):
    """rows: list of (pnl_points, hold_bars). Money in dollars, hold in minutes."""
    if not rows:
        return dict(n=0, net=0.0, pf=0.0, dd=0.0, ndd=0.0, slices8=0, top10=float("nan"),
                    ex10=0.0, per_trade=0.0, wr=0.0, evr=0.0, hold=0.0)
    p = np.array([r[0] for r in rows], dtype=float) * MULT
    hold = np.array([r[1] for r in rows], dtype=float) * bar_min
    n = len(p)
    wins, losses = p[p > 0], p[p < 0]
    gp, gl = wins.sum(), -losses.sum()
    eq = np.cumsum(p)
    dd = float(np.max(np.maximum.accumulate(eq) - eq))
    net = float(p.sum())
    avg_loss = (gl / len(losses)) if len(losses) else 0.0
    k = n // 8
    top10 = float(np.sort(p)[-10:].sum()) if n >= 10 else net
    return dict(n=n, net=net, pf=(gp / gl if gl > 0 else float("inf")), dd=dd,
                ndd=(net / dd if dd > 0 else 99.0),
                slices8=sum(1 for i in range(8)
                            if p[i * k:(i + 1) * k if i < 7 else n].sum() > 0) if k > 0 else 0,
                top10=(100.0 * top10 / net if net > 0 else float("nan")), ex10=net - top10,
                per_trade=net / n, wr=100.0 * len(wins) / n,
                evr=((net / n) / avg_loss if avg_loss > 0 else 0.0),
                hold=float(np.median(hold)))


def measure(arrays, params, cost, bar_min):
    r = run_backtest(FN, arrays=arrays, params=dict(params), cost_pts=cost, return_trades=True)
    tr = sorted(r.get("trades") or [], key=lambda z: z[0])
    idx = pd.DatetimeIndex(arrays["index"])
    cut = pd.Timestamp(SPLIT).date()
    cut_ts = pd.Timestamp(SPLIT, tz=idx.tz) if idx.tz is not None else pd.Timestamp(SPLIT)
    pre = [(t[2], t[1] - t[0]) for t in tr if idx[t[0]].date() < cut]
    post = [(t[2], t[1] - t[0]) for t in tr if idx[t[0]].date() >= cut]
    return dict(sel=metrics(pre, (cut_ts - idx[0]).days / 365.25, bar_min),
                held=metrics(post, (idx[-1] - cut_ts).days / 365.25, bar_min))


def main():
    print(__doc__.split("WHY THIS RUNS")[0].strip())
    print("=" * 112)
    out = []

    A1 = load_master_arrays(find_master("NQ", "1m", "rth", SRC), **WIN)
    tapes = {k: resample(A1, k) for k in BARS}

    # ── parity gates, each clipped to its own registered master's coverage ───────────
    ok = True
    for k in (5, 15, 30):
        reg0 = load_master_arrays(find_master("NQ", "%dm" % k, "rth", SRC), **WIN)
        last = pd.DatetimeIndex(reg0["index"])[-1].date().isoformat()
        gw = dict(WIN, date_to=last)
        reg = load_master_arrays(find_master("NQ", "%dm" % k, "rth", SRC), **gw)
        res = resample(load_master_arrays(find_master("NQ", "1m", "rth", SRC), **gw), k)
        a = measure(reg, CROWN, 0.533, k)
        b = measure(res, CROWN, 0.533, k)
        an, bn = a["sel"]["n"] + a["held"]["n"], b["sel"]["n"] + b["held"]["n"]
        anet = a["sel"]["net"] + a["held"]["net"]
        bnet = b["sel"]["net"] + b["held"]["net"]
        dn, dnet = 100.0 * (bn - an) / max(an, 1), 100.0 * (bnet - anet) / max(abs(anet), 1)
        bad = abs(dn) > 2 or abs(dnet) > 2
        ok = ok and not bad
        print("GATE %2dm (clipped to %s): n %5d vs %5d (%+.2f%%), net $%s vs $%s (%+.2f%%) -> %s"
              % (k, last, bn, an, dn, format(round(bnet), ","), format(round(anet), ","), dnet,
                 "FAIL" if bad else "ok"))
    if not ok:
        sys.exit("PARITY GATE FAILED - nothing printed.")
    print()

    # ── PART A: the full ladder ─────────────────────────────────────────────────────
    print("PART A -- THE LIVE CROWN GEOMETRY ON EVERY BAR (selection stretch; hold = median minutes)")
    print("%-4s %6s | %6s %7s %10s %9s %7s %5s %7s %8s %7s | %5s %7s %9s"
          % ("bar", "cost", "n", "PF", "net $", "DD $", "net/DD", "sl/8", "top10", "$/trade",
             "hold", "n", "PF", "net $"))
    L, lrows = {}, []
    for k in BARS:
        for cost in COSTS:
            m = measure(tapes[k], CROWN, cost, k)
            L[(k, cost)] = m
            s, h = m["sel"], m["held"]
            lrows.append(dict(bar=k, cost=cost, n=s["n"], pf=round(s["pf"], 3), net=round(s["net"]),
                              dd=round(s["dd"]), ndd=round(s["ndd"], 2), slices=s["slices8"],
                              top10=round(s["top10"], 1), ex10=round(s["ex10"]),
                              per_trade=round(s["per_trade"]), hold=round(s["hold"], 1),
                              wr=round(s["wr"], 1), evr=round(s["evr"], 3),
                              held_n=h["n"], held_pf=round(h["pf"], 3), held_net=round(h["net"])))
            print("%-4s %6.3f | %6d %7.3f %10s %9s %7.2f %5d %6.1f%% %8s %6.0fm | %5d %7.3f %9s"
                  % ("%dm" % k, cost, s["n"], s["pf"], format(round(s["net"]), ","),
                     format(round(s["dd"]), ","), s["ndd"], s["slices8"], s["top10"],
                     format(round(s["per_trade"]), ","), s["hold"], h["n"], h["pf"],
                     format(round(h["net"]), ",")))
        print()

    peak = max(BARS, key=lambda k: L[(k, STRESS)]["sel"]["ndd"])
    out.append("PART A: net-over-drawdown at the stressed cost peaks at %dm (%.2f); the 5m bar the "
               "crown trades reads %.2f." % (peak, L[(peak, STRESS)]["sel"]["ndd"],
                                             L[(5, STRESS)]["sel"]["ndd"]))
    out.append("  ladder: " + "  ".join("%dm %.1f" % (k, L[(k, STRESS)]["sel"]["ndd"]) for k in BARS))
    out.append("  median hold: " + "  ".join("%dm %.0fmin" % (k, L[(k, STRESS)]["sel"]["hold"])
                                             for k in BARS))
    out.append("  $/trade:     " + "  ".join("%dm $%.0f" % (k, L[(k, STRESS)]["sel"]["per_trade"])
                                             for k in BARS))

    # ── PART B: can a knob on 5m reproduce 15m? ─────────────────────────────────────
    tgt = L[(15, STRESS)]["sel"]
    print("PART B -- can a KNOB on the 5-minute bar reach the 15-minute cell?")
    print("  target (15m at %.3f): net/DD %.2f, PF %.3f, %d/8 slices, top-10 %.1f%%, $%s a trade, "
          "hold %.0f min" % (STRESS, tgt["ndd"], tgt["pf"], tgt["slices8"], tgt["top10"],
                             format(round(tgt["per_trade"]), ","), tgt["hold"]))
    print("  bar to clear: 90%% of the target net/DD (%.2f) with PF >= %.3f, slices >= %d, "
          "top-10 <= %.1f%%" % (0.90 * tgt["ndd"], tgt["pf"], tgt["slices8"], tgt["top10"] + 5))
    print()
    print("  %-9s %-8s | %6s %7s %10s %7s %5s %7s %8s %7s"
          % ("confirm", "stop_k", "n", "PF", "net $", "net/DD", "sl/8", "top10", "$/trade", "hold"))
    grid, best = [], None
    for cb in CONFIRMS:
        for sk in STOPS:
            p = dict(CROWN, confirm_bars=cb, stop_k=sk)
            s = measure(tapes[5], p, STRESS, 5)["sel"]
            grid.append(dict(confirm_bars=cb, stop_k=sk, n=s["n"], pf=round(s["pf"], 3),
                             net=round(s["net"]), dd=round(s["dd"]), ndd=round(s["ndd"], 2),
                             slices=s["slices8"], top10=round(s["top10"], 1),
                             per_trade=round(s["per_trade"]), hold=round(s["hold"], 1),
                             wr=round(s["wr"], 1), evr=round(s["evr"], 3)))
            if best is None or s["ndd"] > best[1]["ndd"]:
                best = ((cb, sk), s)
            print("  %-9d %-8.2f | %6d %7.3f %10s %7.2f %5d %6.1f%% %8s %6.0fm"
                  % (cb, sk, s["n"], s["pf"], format(round(s["net"]), ","), s["ndd"], s["slices8"],
                     s["top10"], format(round(s["per_trade"]), ","), s["hold"]))
        print()

    (cb, sk), b = best
    reach = 100.0 * b["ndd"] / tgt["ndd"]
    clears = (b["ndd"] >= 0.90 * tgt["ndd"] and b["pf"] >= tgt["pf"]
              and b["slices8"] >= tgt["slices8"] and b["top10"] <= tgt["top10"] + 5)
    out.append("")
    out.append("PART B: the best 5-minute cell is confirm_bars=%d, stop_k=%.2f -- net/DD %.2f, "
               "which is %.0f%% of the 15-minute cell's %.2f." % (cb, sk, b["ndd"], reach, tgt["ndd"]))
    out.append("  it reads PF %.3f (target %.3f), %d/8 slices (target %d), top-10 %.1f%% (target "
               "%.1f%%), $%s a trade (target $%s), hold %.0f min (target %.0f min)."
               % (b["pf"], tgt["pf"], b["slices8"], tgt["slices8"], b["top10"], tgt["top10"],
                  format(round(b["per_trade"]), ","), format(round(tgt["per_trade"]), ","),
                  b["hold"], tgt["hold"]))
    if clears:
        out.append("  VERDICT: THE BAR IS A PROXY FOR A KNOB. The same benefit is available on the "
                   "5-minute chart the crown already trades, for the price of one number - no chart "
                   "change, no NinjaTrader re-port. This is a hypothesis, not an adoption: it needs "
                   "its own Auto-Validate before anything moves.")
    else:
        out.append("  VERDICT: THE BAR IS NOT A PROXY FOR A KNOB. No confirmation or stop setting on "
                   "the 5-minute bar reaches the 15-minute cell, so the fatter bar carries something "
                   "the knobs cannot express - consistent with the band's volatility estimate being "
                   "indexed by bar ORDINAL within the session, which only a real bar change moves. "
                   "The queued 15-minute Auto-Validate is therefore the right next step, and a chart "
                   "change is the real proposal if it passes.")

    # ── PART C: is either improvement still working? year by year ───────────────────
    # Both Part A and Part B produce a candidate that beats the crown over the whole
    # window. The 2026-08-17 variant campaign in NOISE_1_0.py's own docstring already
    # banked confirm_bars=2 and noted it "gave back some 2025-26 profit". Before either
    # is recommended, check the obvious thing nobody has: does the advantage still hold
    # in recent years, or is it paid entirely by the old tape?
    def yearly(arrays, params, bar_min):
        r = run_backtest(FN, arrays=arrays, params=dict(params), cost_pts=STRESS,
                         return_trades=True)
        idx = pd.DatetimeIndex(arrays["index"])
        d = {}
        for t in sorted(r.get("trades") or [], key=lambda z: z[0]):
            y = idx[t[0]].year
            d[y] = d.get(y, 0.0) + t[2] * MULT
        return d

    print()
    print("PART C -- is either improvement STILL working? (net by calendar year, stressed cost)")
    pairs = (("15-minute bar vs the 5-minute crown", yearly(tapes[15], CROWN, 15),
              yearly(tapes[5], CROWN, 5)),
             ("confirm_bars=2 vs the crown, both on 5m",
              yearly(tapes[5], dict(CROWN, confirm_bars=2), 5), yearly(tapes[5], CROWN, 5)))
    crows = []
    for label, cand, base in pairs:
        yrs = sorted(set(cand) | set(base))
        wins = [y for y in yrs if cand.get(y, 0.0) > base.get(y, 0.0)]
        tail = [y for y in yrs[-3:] if cand.get(y, 0.0) > base.get(y, 0.0)]
        print("  %s: ahead in %d of %d years, and in %d of the LAST THREE"
              % (label, len(wins), len(yrs), len(tail)))
        print("     " + "  ".join("%d %+.0fk" % (y, (cand.get(y, 0.0) - base.get(y, 0.0)) / 1000.0)
                                  for y in yrs[-6:]))
        for y in yrs:
            crows.append(dict(pair=label, year=y, candidate=round(cand.get(y, 0.0)),
                              baseline=round(base.get(y, 0.0)),
                              delta=round(cand.get(y, 0.0) - base.get(y, 0.0))))
        out.append("")
        out.append("PART C: %s -- ahead in %d of %d years, %d of the last three."
                   % (label, len(wins), len(yrs), len(tail)))
    out.append("  BOTH candidates share one signature: they beat the crown across 2010-2023 and LOSE")
    out.append("  2024, 2025 and 2026. Two independent mechanisms decaying together, plus the same")
    out.append("  give-back already noted by the 2026-08-17 variant campaign, is more than a hot")
    out.append("  streak in the baseline -- it is the reason NOT to change the bar or the")
    out.append("  confirmation on this evidence.")

    for f, rows_ in (("r45_ladder.csv", lrows), ("r45_knobgrid.csv", grid),
                     ("r45_yearly.csv", crows)):
        pth = os.path.join(ROOT, "tools", "r37_results", f)
        os.makedirs(os.path.dirname(pth), exist_ok=True)
        with open(pth, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows_[0]))
            w.writeheader()
            w.writerows(rows_)

    print("=" * 112)
    for ln in out:
        print(ln)
    with open(os.path.join(ROOT, "tools", "r37_results", "r45_mechanism.txt"), "w",
              encoding="utf-8") as fh:
        fh.write("\n".join(out) + "\n")
    print()
    print("wrote tools/r37_results/r45_ladder.csv, r45_knobgrid.csv, r45_mechanism.txt")


if __name__ == "__main__":
    main()
