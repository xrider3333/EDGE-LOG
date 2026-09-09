#!/usr/bin/env python3
"""NOISE ROUND 44 (2026-09-09) -- IS THE LIVE CROWN ON THE WRONG BAR?

WHY THIS RUNS (owner: "keep testing noise")
-------------------------------------------
Round 41 walked a bar ladder while chasing the 2-minute scalp story, and its own table says
something it never followed up. For the crown's geometry, ranked on net-over-drawdown at the
stressed cost (0.783 pts / $15.66 a round turn):

    1m 7.4    2m 19.4    3m 23.4    **5m 16.1**    10m 23.6

The 5-minute bar -- the one the crowned, paper-traded, NinjaTrader-deployed configuration
actually trades -- is the WORST of 2/3/5/10. Round 41 summarised this as "the bar barely
matters", which is true of the 2m-vs-5m comparison it cared about and NOT true of its own
numbers: 23.6 against 16.1 is a 47% difference in the number a leg decision rests on. If that
survives a proper look it is the cheapest improvement available to this family -- no new rules,
no new file, no new knobs, the same configuration on a different chart.

Round 41 measured it once: one window, one metric, one configuration (#243), no concentration
read, no held-out read, no plateau, and no walk of the neighbouring bars around the winner. And
the live crown is **#304**, not the #243 geometry it used. This round is the proper look.

THE PRE-REGISTERED BAR (fixed before any cell ran)
---------------------------------------------------
Changing the crown's bar is a change to a live, deployed configuration, so it carries the same
height as any crown change. An alternative bar becomes a QUEUEABLE CANDIDATE only if, measured
on one resampled source tape, entry-sliced, it clears ALL of:

  (a) net-over-drawdown above the 5-minute cell at ALL THREE costs (0.533 / 0.783 / 1.033);
  (b) profit factor at or above the 5-minute cell at all three costs;
  (c) eight-slice chronological consistency at least equal to the 5-minute cell at 0.783;
  (d) top-10 share no more than 5 points worse than the 5-minute cell, ex-top-10 net positive;
  (e) the post-split stretch (SPENT lockbox -- confirmatory only, it ranks nothing) not worse in
      profit factor than the 5-minute cell's, because a bar change that only works in the old
      years is a curve-fit to a dead regime;
  (f) NEIGHBOUR SANITY: the bars either side of the winner must also beat 5m on (a). A single
      winning bar with losing neighbours is a sampling artifact of where the session grid lands,
      not a property of the strategy. This is the bar-dimension equivalent of a knob plateau and
      it is the clause that would have caught round 41's 2-minute story earlier.

Clearing all six queues a fenced Auto-Validate on the winning bar. It does NOT crown anything.
Nothing about this file touches the paper board or NinjaTrader.

DATA / GATES. One source tape: the registered NQ 1m RTH master (db_noadj_rth), resampled inside
this file to 2/3/5/10/15 minutes (round 41's resampler, reused unchanged), so no cell can differ
because of how its master was built. TWO parity gates, one better than round 41 had:
  G1 the resampled 5m must reproduce the REGISTERED 5m master on the live crown geometry;
  G2 the resampled 15m must reproduce the REGISTERED 15m master on the same geometry.
Both to within 2% on trade count and net, or nothing below is printed.

Window 2010-06-07 -> 2026-07-16, trades split by ENTRY at 2025-02-14. The NOISE lockbox is SPENT
(read since 2026-08-12); the post-split stretch is confirmatory only.

Usage:  python tools/r44_noise_crown_bar.py
Writes: tools/r37_results/r44_crown_bar.csv, r44_crown_bar.txt
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
from r41_bar_ladder_overlap import resample  # noqa: E402  (one resampler, already gated once)

FN = "NOISE_1_0.py"
MULT = 20.0
SRC = "db_noadj_rth"
WIN = dict(date_from="2010-06-07", date_to="2026-07-16")
SPLIT = "2025-02-14"
COSTS = [0.533, 0.783, 1.033]
BARS = [2, 3, 5, 10, 15]

# The LIVE family crown and paper leg (api/paper.py NOISE_304_NBHD knobs), unchanged.
CROWN = dict(lookback=40, band_mult_long=0.75, band_mult_short=1.5, exit_mode="vwap",
             side="Both", window="all_day", flat_eod=True, skip_holidays=False,
             stop_mode="bandwidth", stop_k=1.75, daytype_mode="skip_bot_short",
             daytype_lo=0.2, daytype_hi=0.8, vol_skip_pct=95.0)


def metrics(pnl_pts, years):
    p = np.asarray(pnl_pts, dtype=float) * MULT
    n = len(p)
    if n == 0:
        return dict(n=0, net=0.0, pf=0.0, dd=0.0, ndd=0.0, slices8=0, top10_share=float("nan"),
                    ex10_net=0.0, per_trade=0.0, wr=0.0, evr=0.0)
    wins, losses = p[p > 0], p[p < 0]
    gp, gl = wins.sum(), -losses.sum()
    eq = np.cumsum(p)
    dd = float(np.max(np.maximum.accumulate(eq) - eq))
    net = float(p.sum())
    avg_loss = (gl / len(losses)) if len(losses) else 0.0
    k = n // 8
    top10 = float(np.sort(p)[-10:].sum()) if n >= 10 else net
    return dict(n=n, net=net, pf=(gp / gl if gl > 0 else float("inf")),
                dd=dd, ndd=(net / dd if dd > 0 else 99.0),
                slices8=sum(1 for i in range(8)
                            if p[i * k:(i + 1) * k if i < 7 else n].sum() > 0) if k > 0 else 0,
                top10_share=(100.0 * top10 / net if net > 0 else float("nan")),
                ex10_net=net - top10, per_trade=net / n,
                wr=100.0 * len(wins) / n,
                evr=((net / n) / avg_loss if avg_loss > 0 else 0.0))


def measure(arrays, params, cost, split=SPLIT):
    r = run_backtest(FN, arrays=arrays, params=dict(params), cost_pts=cost, return_trades=True)
    tr = sorted(r.get("trades") or [], key=lambda z: z[0])
    idx = pd.DatetimeIndex(arrays["index"])
    days = np.array([idx[t[0]].date() for t in tr])
    pnl = [t[2] for t in tr]
    cut = pd.Timestamp(split).date()
    cut_ts = pd.Timestamp(split, tz=idx.tz) if idx.tz is not None else pd.Timestamp(split)
    return dict(
        sel=metrics([p for d, p in zip(days, pnl) if d < cut], (cut_ts - idx[0]).days / 365.25),
        held=metrics([p for d, p in zip(days, pnl) if d >= cut], (idx[-1] - cut_ts).days / 365.25),
        all=metrics(pnl, (idx[-1] - idx[0]).days / 365.25))


def main():
    print(__doc__.split("WHY THIS RUNS")[0].strip())
    print("=" * 108)

    A1 = load_master_arrays(find_master("NQ", "1m", "rth", SRC), **WIN)
    tapes = {k: resample(A1, k) for k in BARS}

    # ── parity gates ────────────────────────────────────────────────────────────────
    # A registered master may cover LESS calendar than the 1m tape (the 15m one ends
    # 2026-06-30 mid-session while 1m runs to 2026-07-16). Comparing them over different
    # spans measures the calendar, not the resampler -- so each gate is clipped to the
    # registered master's OWN last bar before anything is compared.
    ok = True
    for k in (5, 15):
        reg = load_master_arrays(find_master("NQ", "%dm" % k, "rth", SRC), **WIN)
        last = pd.DatetimeIndex(reg["index"])[-1].date().isoformat()
        gate_win = dict(WIN, date_to=last)
        reg = load_master_arrays(find_master("NQ", "%dm" % k, "rth", SRC), **gate_win)
        res_k = resample(load_master_arrays(find_master("NQ", "1m", "rth", SRC), **gate_win), k)
        a = measure(reg, CROWN, 0.533)["all"]
        b = measure(res_k, CROWN, 0.533)["all"]
        dn = 100.0 * (b["n"] - a["n"]) / max(a["n"], 1)
        dnet = 100.0 * (b["net"] - a["net"]) / max(abs(a["net"]), 1)
        bad = abs(dn) > 2 or abs(dnet) > 2
        ok = ok and not bad
        print("GATE G%d resampled %2dm vs REGISTERED %2dm master (live crown geometry): "
              "clipped to %s: n %5d vs %5d (%+.2f%%), net $%s vs $%s (%+.2f%%) -> %s"
              % (1 if k == 5 else 2, k, k, last, b["n"], a["n"], dn, format(round(b["net"]), ","),
                 format(round(a["net"]), ","), dnet, "FAIL" if bad else "ok"))
    if not ok:
        sys.exit("PARITY GATE FAILED - the resampled tape does not reproduce a registered master; "
                 "nothing printed.")
    print()

    # ── the ladder ──────────────────────────────────────────────────────────────────
    print("THE LIVE CROWN GEOMETRY (#304, unchanged) ON EVERY BAR -- %s to %s, entry-sliced at %s"
          % (WIN["date_from"], WIN["date_to"], SPLIT))
    print("%-4s %6s | %6s %7s %10s %9s %7s %5s %7s %10s %8s | %5s %7s %9s"
          % ("bar", "cost", "n", "PF", "net $", "DD $", "net/DD", "sl/8", "top10", "ex10 $",
             "$/trade", "n", "PF", "net $"))
    R, rows = {}, []
    for k in BARS:
        for cost in COSTS:
            m = measure(tapes[k], CROWN, cost)
            R[(k, cost)] = m
            s, h = m["sel"], m["held"]
            rows.append(dict(bar=k, cost=cost, n=s["n"], pf=round(s["pf"], 3), net=round(s["net"]),
                             dd=round(s["dd"]), ndd=round(s["ndd"], 2), slices=s["slices8"],
                             top10=round(s["top10_share"], 1), ex10=round(s["ex10_net"]),
                             per_trade=round(s["per_trade"]), wr=round(s["wr"], 1),
                             evr=round(s["evr"], 3), held_n=h["n"], held_pf=round(h["pf"], 3),
                             held_net=round(h["net"])))
            print("%-4s %6.3f | %6d %7.3f %10s %9s %7.2f %5d %6.1f%% %10s %8s | %5d %7.3f %9s"
                  % ("%dm" % k, cost, s["n"], s["pf"], format(round(s["net"]), ","),
                     format(round(s["dd"]), ","), s["ndd"], s["slices8"], s["top10_share"],
                     format(round(s["ex10_net"]), ","), format(round(s["per_trade"]), ","),
                     h["n"], h["pf"], format(round(h["net"]), ",")))
        print()

    out = os.path.join(ROOT, "tools", "r37_results", "r44_crown_bar.csv")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

    # ── the pre-registered read ─────────────────────────────────────────────────────
    lines = []
    lines.append("=" * 108)
    lines.append("THE BAR: an alternative must beat 5m on net-over-drawdown at ALL THREE costs, match its")
    lines.append("profit factor and slice count, stay within 5 points on top-10 share with a positive")
    lines.append("ex-top-10 net, not be worse in the spent recent stretch, and its NEIGHBOURING bars must")
    lines.append("beat 5m too (a lone winning bar is a session-grid artifact, not an edge).")
    lines.append("=" * 108)
    five = {c: R[(5, c)] for c in COSTS}
    verdicts = {}
    for k in BARS:
        if k == 5:
            continue
        a = all(R[(k, c)]["sel"]["ndd"] > five[c]["sel"]["ndd"] for c in COSTS)
        b = all(R[(k, c)]["sel"]["pf"] >= five[c]["sel"]["pf"] for c in COSTS)
        c_ = R[(k, 0.783)]["sel"]["slices8"] >= five[0.783]["sel"]["slices8"]
        d = (R[(k, 0.783)]["sel"]["top10_share"] <= five[0.783]["sel"]["top10_share"] + 5
             and R[(k, 0.783)]["sel"]["ex10_net"] > 0)
        e = R[(k, 0.783)]["held"]["pf"] >= five[0.783]["held"]["pf"]
        verdicts[k] = dict(a=a, b=b, c=c_, d=d, e=e)
        lines.append("  %3dm: net/DD %s | PF %s | slices %s | concentration %s | recent stretch %s"
                     % (k, "beats 5m" if a else "NO", "ok" if b else "NO", "ok" if c_ else "NO",
                        "ok" if d else "NO", "ok" if e else "NO"))
    for k in BARS:
        if k == 5 or not all(verdicts[k].values()):
            continue
        nbrs = [x for x in BARS if x != 5 and abs(BARS.index(x) - BARS.index(k)) == 1]
        nb_ok = all(all(R[(x, c)]["sel"]["ndd"] > five[c]["sel"]["ndd"] for c in COSTS) for x in nbrs)
        verdicts[k]["f"] = nb_ok
        lines.append("  %3dm neighbour sanity (%s): %s" %
                     (k, ", ".join("%dm" % x for x in nbrs), "ok" if nb_ok else "NO -- lone winner"))
    winners = [k for k in BARS if k != 5 and all(verdicts[k].values())]
    lines.append("")
    lines.append("  5m reference at 0.783: net/DD %.2f, PF %.3f, %d/8 slices, top-10 %.1f%%, "
                 "$%s a trade, recent stretch $%s at PF %.3f"
                 % (five[0.783]["sel"]["ndd"], five[0.783]["sel"]["pf"], five[0.783]["sel"]["slices8"],
                    five[0.783]["sel"]["top10_share"], format(round(five[0.783]["sel"]["per_trade"]), ","),
                    format(round(five[0.783]["held"]["net"]), ","), five[0.783]["held"]["pf"]))
    if winners:
        for k in winners:
            s = R[(k, 0.783)]["sel"]
            lines.append("  -> %dm CLEARS EVERY CLAUSE: net/DD %.2f vs %.2f, PF %.3f vs %.3f, $%s a trade "
                         "vs $%s, money %+.0f%%" %
                         (k, s["ndd"], five[0.783]["sel"]["ndd"], s["pf"], five[0.783]["sel"]["pf"],
                          format(round(s["per_trade"]), ","),
                          format(round(five[0.783]["sel"]["per_trade"]), ","),
                          100.0 * (s["net"] - five[0.783]["sel"]["net"]) / five[0.783]["sel"]["net"]))
        lines.append("  -> QUEUE a fenced validate on the winning bar. Crowning stays the owner's call.")
    else:
        lines.append("  -> NO BAR CLEARS EVERY CLAUSE. The crown stays on 5 minutes and round 41's")
        lines.append("     ladder is explained: it ranked one metric at one cost on one window.")
    # ── the recent stretch IN CONTEXT ────────────────────────────────────────────────
    # Clause (e) is failing every candidate this family produces (round 43's C3, and now
    # every bigger bar). Before reading that as "the crown is regime-current", ask whether
    # each cell's recent stretch is unusual FOR ITSELF: take its own pre-split history,
    # slide a window of the same trade count through it, and report where the recent
    # stretch's dollars-per-trade falls in that distribution. A soft patch at the 30th
    # percentile is ordinary; one at the 2nd is an anomaly worth acting on.
    lines.append("")
    lines.append("THE RECENT STRETCH IN CONTEXT -- is each bar's weak patch unusual for itself?")
    lines.append("  (its own pre-split history, sliding a window of the same trade count, at 0.783)")
    for k in BARS:
        r = run_backtest(FN, arrays=tapes[k], params=dict(CROWN), cost_pts=0.783, return_trades=True)
        tr = sorted(r.get("trades") or [], key=lambda z: z[0])
        idx = pd.DatetimeIndex(tapes[k]["index"])
        cut = pd.Timestamp(SPLIT).date()
        pre = np.array([t[2] * MULT for t in tr if idx[t[0]].date() < cut])
        post = np.array([t[2] * MULT for t in tr if idx[t[0]].date() >= cut])
        w = len(post)
        if w < 20 or len(pre) < w + 20:
            continue
        roll = np.convolve(pre, np.ones(w), mode="valid") / w
        pct = 100.0 * float((roll <= post.mean()).mean())
        lines.append("    %3dm: recent $%6.0f a trade over %4d trades -- the %4.1fth percentile of its "
                     "own history (median $%.0f, worst $%.0f)"
                     % (k, post.mean(), w, pct, float(np.median(roll)), float(roll.min())))
    lines.append("  A low percentile everywhere means the whole family is in a soft patch, not that")
    lines.append("  the 5-minute bar is uniquely regime-current.")

    for ln in lines:
        print(ln)
    with open(os.path.join(ROOT, "tools", "r37_results", "r44_crown_bar.txt"), "w",
              encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    print()
    print("wrote tools/r37_results/r44_crown_bar.csv and r44_crown_bar.txt")


if __name__ == "__main__":
    main()
