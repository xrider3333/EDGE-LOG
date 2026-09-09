#!/usr/bin/env python3
"""NOISE ROUND 49 (2026-09-09) -- THE BAND ANCHOR: the strategy measures from a level fixed at the
open all day. Should it follow the session instead?

WHY THIS RUNS (owner: "continue optimizing and search for more on the NOISE alpha")
-----------------------------------------------------------------------------------
Rounds 43-48 have now swept the knob space, the bar space, the conditional space and the band's own
volatility ESTIMATOR, and every one came back empty. One structural choice has still never been
questioned, and it is visible in two lines of the strategy:

    ref_hi = max(session open, prior close)
    ref_lo = min(session open, prior close)

Those are computed once per session and never move. The band widens through the day, because sigma
carries a time-of-day profile, but it stays centred on the MORNING. A 15:00 breakout is therefore
judged against a level set five and a half hours earlier, on a day that may have trended a long way
since. Every family this program trades re-references intraday except this one -- the NOISE exit
itself is a VWAP cross, so the strategy already believes a moving reference is meaningful for
getting OUT while using a fixed one to get IN.

THE THREE ANCHORS (research fork `augur_strategies/NOISE_1_5_ANCHOR.py`, parity-gated below)
  open   the shipped anchor -- fixed for the session. Reproduces the parent exactly.
  vwap   the session's running VWAP through the PREVIOUS bar, so the band tracks where the day has
         actually been trading. Same reference the exit already uses.
  mid    the midpoint of the session's range so far, through the previous bar -- a cruder tracker
         that does not need volume, so it also tells us whether any benefit is about VWAP
         specifically or just about following the session at all.

Both alternatives are strictly causal: at bar k they read bars 0..k-1 and fall back to the shipped
anchor at bar 0. (Round 47 was retracted for a one-bar look-ahead, so the shift is explicit in the
fork and gated here.)

THE PRE-REGISTERED BAR (fixed before any cell ran)
----------------------------------------------------
  G0 PARITY: the fork with anchor_mode='open' must reproduce the parent file to the cent on the
     crown configuration. If it does not, nothing below is printed.
  An anchor becomes a CANDIDATE, meaning it earns an Auto-Validate, only if it clears ALL of:
  (a) higher PROFIT FACTOR than the shipped anchor at BOTH costs (0.533 house, 0.783 stressed) --
      profit factor and never dollars, per round 46's amplitude finding;
  (b) higher profit factor in BOTH eras (through 2023, and 2024 onward) -- rounds 43-46 each found
      something that beat the crown historically and had quietly stopped working;
  (c) concentration no worse: top-10 share within 3 points and ex-top-10 net positive;
  (d) net-over-drawdown at least as good at the stressed cost;
  (e) it holds on BOTH band widths tested -- the crown's 0.75/1.50 and one step wider 1.00/1.75 --
      because an anchor that only works at one width is a width finding, not an anchor finding.

Nothing is adopted here. A winner is queued as an Auto-Validate with the knob open and goes to
forward paper evidence before any board change.

Usage:  python tools/r49_noise_anchor.py
Writes: tools/r37_results/r49_anchor.csv, r49_anchor.txt
"""
import csv
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.environ.get("EDGELOG_REPO_ROOT") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FORK_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

from augur_engine.data import find_master, load_master_arrays  # noqa: E402
from augur_engine.engine import run_backtest  # noqa: E402

MULT = 20.0
WIN = dict(date_from="2010-06-07", date_to="2026-07-16")
CUT = pd.Timestamp("2024-01-01").date()
COSTS = [0.533, 0.783]

CROWN = dict(lookback=40, band_mult_long=0.75, band_mult_short=1.5, exit_mode="vwap",
             side="Both", window="all_day", flat_eod=True, skip_holidays=False,
             stop_mode="bandwidth", stop_k=1.75, daytype_mode="skip_bot_short",
             daytype_lo=0.2, daytype_hi=0.8, vol_skip_pct=95.0)
WIDER = dict(CROWN, band_mult_long=1.0, band_mult_short=1.75)


def load_fork():
    import importlib.util as ilu
    p = os.path.join(FORK_DIR, "augur_strategies", "NOISE_1_5_ANCHOR.py")
    spec = ilu.spec_from_file_location("NOISE_1_5_ANCHOR", p)
    m = ilu.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def stats(p):
    p = np.asarray(p, float)
    if not len(p):
        return dict(n=0, net=0.0, pf=0.0, dd=0.0, ndd=0.0, top10=float("nan"), ex10=0.0, per=0.0)
    w, l = p[p > 0].sum(), -p[p < 0].sum()
    eq = np.cumsum(p)
    d = float(np.max(np.maximum.accumulate(eq) - eq))
    net = float(p.sum())
    t10 = float(np.sort(p)[-10:].sum()) if len(p) >= 10 else net
    return dict(n=len(p), net=net, pf=(w / l if l > 0 else 99.0), dd=d,
                ndd=(net / d if d > 0 else 99.0),
                top10=(100.0 * t10 / net if net > 0 else float("nan")),
                ex10=net - t10, per=net / len(p))


def measure(strategy, A, params, cost):
    r = run_backtest(strategy, arrays=A, params=dict(params), cost_pts=cost, return_trades=True)
    tr = sorted(r.get("trades") or [], key=lambda z: z[0])
    idx = pd.DatetimeIndex(A["index"])
    d = np.array([idx[t[0]].date() for t in tr])
    p = np.array([t[2] * MULT for t in tr])
    return dict(all=stats(p), old=stats(p[d < CUT]), rec=stats(p[d >= CUT]),
                raw_net=float(r.get("total_pnl") or 0.0) * MULT, raw_n=r.get("num_trades"))


def main():
    print(__doc__.split("WHY THIS RUNS")[0].strip())
    print("=" * 118)
    A = load_master_arrays(find_master("NQ", "5m", "rth", "db_noadj_rth"), **WIN)
    fork = load_fork()

    # ── G0 parity ───────────────────────────────────────────────────────────────────
    a = measure("NOISE_1_0.py", A, CROWN, 0.533)
    b = measure(fork, A, dict(CROWN, anchor_mode="open"), 0.533)
    same = (a["raw_n"] == b["raw_n"]) and abs(a["raw_net"] - b["raw_net"]) < 0.01
    print("G0 PARITY  parent %d trades / $%s   fork(open) %d trades / $%s   -> %s"
          % (a["raw_n"], format(round(a["raw_net"]), ","), b["raw_n"],
             format(round(b["raw_net"]), ","), "IDENTICAL" if same else "MISMATCH"))
    if not same:
        sys.exit("G0 FAILED - the fork does not reproduce the parent; nothing printed.")
    print()

    rows, R = [], {}
    for wname, wp in (("crown 0.75/1.50", CROWN), ("wider 1.00/1.75", WIDER)):
        print("BAND WIDTH %s" % wname)
        print("  %-7s %6s | %6s %8s %10s %7s %7s %7s | %8s %8s | %9s %9s"
              % ("anchor", "cost", "n", "PF", "net $", "net/DD", "top10", "$/trade",
                 "PF old", "PF new", "net old", "net new"))
        for anchor in ("open", "vwap", "mid"):
            for cost in COSTS:
                m = measure(fork, A, dict(wp, anchor_mode=anchor), cost)
                R[(wname, anchor, cost)] = m
                al, o, rc = m["all"], m["old"], m["rec"]
                rows.append(dict(width=wname, anchor=anchor, cost=cost, n=al["n"],
                                 pf=round(al["pf"], 4), net=round(al["net"]), dd=round(al["dd"]),
                                 ndd=round(al["ndd"], 2), top10=round(al["top10"], 1),
                                 ex10=round(al["ex10"]), per=round(al["per"]),
                                 pf_old=round(o["pf"], 4), pf_new=round(rc["pf"], 4),
                                 net_old=round(o["net"]), net_new=round(rc["net"])))
                print("  %-7s %6.3f | %6d %8.4f %10s %7.2f %6.1f%% %7s | %8.4f %8.4f | %9s %9s"
                      % (anchor, cost, al["n"], al["pf"], format(round(al["net"]), ","), al["ndd"],
                         al["top10"], format(round(al["per"]), ","), o["pf"], rc["pf"],
                         format(round(o["net"]), ","), format(round(rc["net"]), ",")))
        print()

    out = ["THE BAR: higher profit factor than the shipped anchor at BOTH costs AND in BOTH eras, "
           "concentration within 3 points with positive ex-top-10, net-over-drawdown at least as "
           "good when stressed, and it must hold at BOTH band widths.", ""]
    winners = []
    for anchor in ("vwap", "mid"):
        ok_all, detail = [], []
        for wname in ("crown 0.75/1.50", "wider 1.00/1.75"):
            ok = True
            for cost in COSTS:
                base, v = R[(wname, "open", cost)], R[(wname, anchor, cost)]
                ok = ok and v["all"]["pf"] > base["all"]["pf"]
                if cost == 0.783:
                    ok = (ok and v["old"]["pf"] > base["old"]["pf"]
                          and v["rec"]["pf"] > base["rec"]["pf"]
                          and v["all"]["ndd"] >= base["all"]["ndd"]
                          and v["all"]["top10"] <= base["all"]["top10"] + 3
                          and v["all"]["ex10"] > 0)
            ok_all.append(ok)
            base, v = R[(wname, "open", 0.783)], R[(wname, anchor, 0.783)]
            detail.append("%s: PF %.4f vs %.4f | net/DD %.2f vs %.2f | old %.4f vs %.4f | new "
                          "%.4f vs %.4f" % (wname, v["all"]["pf"], base["all"]["pf"],
                                            v["all"]["ndd"], base["all"]["ndd"], v["old"]["pf"],
                                            base["old"]["pf"], v["rec"]["pf"], base["rec"]["pf"]))
        if all(ok_all):
            winners.append(anchor)
        out.append("  %-5s %s" % (anchor, "CLEARS EVERY CLAUSE" if all(ok_all)
                                  else "no (%d of 2 widths)" % sum(ok_all)))
        for d in detail:
            out.append("      " + d)
    out.append("")
    if winners:
        out.append("CANDIDATE(S): %s -- queue an Auto-Validate on the fork with anchor_mode open, "
                   "then forward paper evidence. Nothing is adopted here." % ", ".join(winners))
    else:
        out.append("NO ANCHOR BEATS THE SHIPPED ONE. Measuring the band from a level fixed at the "
                   "open is not the weakness it looks like, and the last structural choice around "
                   "this crown is now tested.")
    for ln in out:
        print(ln)
    p = os.path.join(ROOT, "tools", "r37_results", "r49_anchor.csv")
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    with open(os.path.join(ROOT, "tools", "r37_results", "r49_anchor.txt"), "w",
              encoding="utf-8") as fh:
        fh.write("\n".join(out) + "\n")
    print()
    print("wrote tools/r37_results/r49_anchor.csv, r49_anchor.txt")


if __name__ == "__main__":
    main()
