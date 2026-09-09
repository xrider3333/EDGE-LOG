#!/usr/bin/env python3
"""NOISE ROUND 50 (2026-09-09) -- WHAT THE SINGLE-POSITION RULE THROWS AWAY.

WHY THIS RUNS (owner: "continue optimizing and search for more on the NOISE alpha")
-----------------------------------------------------------------------------------
Rounds 43-49 swept the knob space, the bar space, the conditional space, the volatility estimator
and the band anchor. All five came back empty, which is strong evidence the crown's SETTINGS are
right. None of them touched a structural rule that has been in the family since it was written and
has never been examined:

    the strategy can hold ONE position at a time.

Every entry trigger that fires while a position is already open is silently discarded. On a
five-minute chart with a median hold of about eight bars, that is potentially a lot of discarded
signal -- and if those discarded signals carry the same edge as the taken ones, the strategy is
leaving money on the table for a reason nobody ever tested.

**This is a capacity question, not a settings question**, which is why it is worth asking after five
empty rounds: it is the first thing in this sweep that could make the strategy earn MORE rather than
earn the same more cleanly.

HOW IT IS MEASURED, without changing behaviour. `augur_strategies/NOISE_1_6_SIGNALS.py` is the
crown file with one surgical change: the entry trigger is evaluated on EVERY bar and appended to a
log as (bar, side, was-a-position-open), while the ACTION is still gated on being flat exactly as
before. Gate G0 below proves the fork trades identically to the parent, so the log is a pure
observation of the shipped strategy.

Each discarded signal is then given the strategy's OWN exit rule, applied honestly:
  * entry at the NEXT bar's open (the same one-bar delay the real strategy takes -- round 47 was
    retracted for a one-bar look-ahead, so this is explicit);
  * exit on the first VWAP cross back against the position, exactly the shipped exit;
  * a hard flat at the session close, exactly the shipped rule;
  * the same cost per round turn.
No stop is applied to the discarded set, which if anything FLATTERS them -- stated here so the
result is read with that in mind.

THE PRE-REGISTERED BAR (fixed before any number was computed)
--------------------------------------------------------------
Allowing concurrent positions becomes a CANDIDATE worth building and validating only if:
  (a) the discarded signals are PROFITABLE in their own right at the stressed cost (0.783), on at
      least 200 of them;
  (b) their PROFIT FACTOR is at least 80% of the taken signals' -- they do not have to be as good,
      but a second position that is materially worse than the first is added risk for scraps;
  (c) that holds in BOTH eras (through 2023, and 2024 onward), the clause that killed three
      candidates in rounds 43-46;
  (d) concentration on the discarded set is not extreme: its ten best trades under 60% of its net,
      with a positive ex-top-10 net.
If it clears, the next step is a real multi-position fork and an Auto-Validate -- not an adoption.
If the discarded signals are unprofitable, then the single-position rule is doing useful work and
this closes the last structural question about the crown.

Usage:  python tools/r50_noise_missed_signals.py
Writes: tools/r37_results/r50_missed.csv, r50_missed.txt
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


def load_fork():
    import importlib.util as ilu
    p = os.path.join(FORK_DIR, "augur_strategies", "NOISE_1_6_SIGNALS.py")
    spec = ilu.spec_from_file_location("NOISE_1_6_SIGNALS", p)
    m = ilu.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def stats(p):
    p = np.asarray(p, float)
    if not len(p):
        return dict(n=0, net=0.0, pf=0.0, per=0.0, top10=float("nan"), ex10=0.0)
    w, l = p[p > 0].sum(), -p[p < 0].sum()
    net = float(p.sum())
    t10 = float(np.sort(p)[-10:].sum()) if len(p) >= 10 else net
    return dict(n=len(p), net=net, pf=(w / l if l > 0 else 99.0), per=net / len(p),
                top10=(100.0 * t10 / net if net > 0 else float("nan")), ex10=net - t10)


def session_bounds(day_id):
    d = np.asarray(day_id)
    starts = np.flatnonzero(np.r_[True, d[1:] != d[:-1]])
    ends = np.r_[starts[1:], len(d)]
    return list(zip(starts, ends))


def simulate(A, signals, cost):
    """Give each signal the strategy's own exit: fill at the NEXT bar's open, exit on the first
    VWAP cross against the position, hard flat at the session close."""
    o, h, l, c = A["open"], A["high"], A["low"], A["close"]
    v = A.get("volume")
    bounds = {}
    for a, b in session_bounds(A["day_id"]):
        for i in range(a, b):
            bounds[i] = (a, b)
    vwap_cache = {}
    out = []
    for bar, side, _ in signals:
        a, b = bounds[bar]
        if bar + 1 >= b - 1:
            continue                                   # no room to fill and manage
        if a not in vwap_cache:
            sv = v[a:b] if v is not None else None
            if sv is None or not np.isfinite(sv).any() or sv.sum() <= 0:
                vwap_cache[a] = None
            else:
                typ = (h[a:b] + l[a:b] + c[a:b]) / 3.0
                with np.errstate(invalid="ignore", divide="ignore"):
                    vwap_cache[a] = np.cumsum(typ * sv) / np.cumsum(sv)
        vw = vwap_cache[a]
        fill = bar + 1
        px = o[fill]
        exit_px = c[b - 1]                              # default: flat at the close
        for k in range(fill, b - 1):
            if vw is not None and not np.isnan(vw[k - a]):
                if (side > 0 and c[k] < vw[k - a]) or (side < 0 and c[k] > vw[k - a]):
                    exit_px = o[k + 1]
                    break
        pnl = (exit_px - px) if side > 0 else (px - exit_px)
        out.append((bar, (pnl - cost) * MULT))
    return out


def main():
    print(__doc__.split("WHY THIS RUNS")[0].strip())
    print("=" * 112)
    A = load_master_arrays(find_master("NQ", "5m", "rth", "db_noadj_rth"), **WIN)
    fork = load_fork()

    base = run_backtest("NOISE_1_0.py", arrays=A, params=dict(CROWN), cost_pts=0.783,
                        return_trades=True)
    forked = run_backtest(fork, arrays=A, params=dict(CROWN), cost_pts=0.783, return_trades=True)
    same = (base["num_trades"] == forked["num_trades"]
            and abs(base["total_pnl"] - forked["total_pnl"]) < 1e-6)
    print("G0 PARITY  parent %d trades / $%s   fork %d trades / $%s   -> %s"
          % (base["num_trades"], format(round(base["total_pnl"] * MULT), ","),
             forked["num_trades"], format(round(forked["total_pnl"] * MULT), ","),
             "IDENTICAL" if same else "MISMATCH"))
    if not same:
        sys.exit("G0 FAILED - the instrumented fork does not trade like the parent.")

    sig = list(fork.SIGNAL_LOG)
    taken = [s for s in sig if s[2] == 0]
    missed = [s for s in sig if s[2] == 1]
    print()
    print("SIGNALS: %d fired in total -- %d acted on (flat at the time), %d DISCARDED because a "
          "position was already open (%.0f%%)"
          % (len(sig), len(taken), len(missed), 100.0 * len(missed) / max(len(sig), 1)))

    idx = pd.DatetimeIndex(A["index"])
    rows, R = [], {}
    print()
    print("  %-22s %6s | %6s %8s %11s %9s %7s %8s | %8s %8s"
          % ("set", "cost", "n", "PF", "net $", "$/trade", "top10", "ex10 $", "PF old", "PF new"))
    for cost in COSTS:
        for label, sset in (("TAKEN (the strategy)", taken), ("DISCARDED (never traded)", missed)):
            sim = simulate(A, sset, cost)
            if not sim:
                continue
            bars = np.array([s[0] for s in sim])
            p = np.array([s[1] for s in sim])
            d = np.array([idx[b].date() for b in bars])
            a_, o_, r_ = stats(p), stats(p[d < CUT]), stats(p[d >= CUT])
            R[(label, cost)] = (a_, o_, r_)
            rows.append(dict(set=label, cost=cost, n=a_["n"], pf=round(a_["pf"], 4),
                             net=round(a_["net"]), per=round(a_["per"]),
                             top10=round(a_["top10"], 1), ex10=round(a_["ex10"]),
                             pf_old=round(o_["pf"], 4), pf_new=round(r_["pf"], 4),
                             net_old=round(o_["net"]), net_new=round(r_["net"])))
            print("  %-22s %6.3f | %6d %8.4f %11s %9s %6.1f%% %8s | %8.4f %8.4f"
                  % (label, cost, a_["n"], a_["pf"], format(round(a_["net"]), ","),
                     format(round(a_["per"]), ","), a_["top10"], format(round(a_["ex10"]), ","),
                     o_["pf"], r_["pf"]))
        print()

    out = ["THE BAR: the discarded signals must be profitable at the stressed cost on at least 200 "
           "of them, reach at least 80% of the taken signals' profit factor, hold in BOTH eras, and "
           "not be concentrated (top-10 under 60% of net, positive ex-top-10).", ""]
    t, m = R.get(("TAKEN (the strategy)", 0.783)), R.get(("DISCARDED (never traded)", 0.783))
    if not m:
        out.append("  no discarded signals to score.")
    else:
        ta, ma = t[0], m[0]
        c1 = ma["net"] > 0 and ma["n"] >= 200
        c2 = ma["pf"] >= 0.80 * ta["pf"]
        c3 = m[1]["pf"] > 1.0 and m[2]["pf"] > 1.0
        c4 = ma["top10"] < 60 and ma["ex10"] > 0
        out.append("  discarded: %d signals, profit factor %.4f against the taken set's %.4f "
                   "(%.0f%% of it), net $%s at $%s a trade"
                   % (ma["n"], ma["pf"], ta["pf"], 100.0 * ma["pf"] / ta["pf"],
                      format(round(ma["net"]), ","), format(round(ma["per"]), ",")))
        out.append("  (a) profitable on >= 200 ....... %s" % ("yes" if c1 else "NO"))
        out.append("  (b) >= 80%% of taken profit factor %s" % ("yes" if c2 else "NO"))
        out.append("  (c) holds in both eras ......... %s (old %.4f, since 2024 %.4f)"
                   % ("yes" if c3 else "NO", m[1]["pf"], m[2]["pf"]))
        out.append("  (d) not concentrated ........... %s (top-10 %.1f%%, ex-top-10 $%s)"
                   % ("yes" if c4 else "NO", ma["top10"], format(round(ma["ex10"]), ",")))
        out.append("")
        if c1 and c2 and c3 and c4:
            out.append("CANDIDATE: the single-position rule is throwing away tradeable edge. Build a "
                       "multi-position fork and queue an Auto-Validate on it. Note the discarded set "
                       "was simulated WITHOUT a stop, which flatters it, so the fork must carry the "
                       "real stop before anything is believed.")
        else:
            out.append("NOT A CANDIDATE. The single-position rule is doing useful work: the signals "
                       "it discards do not clear the bar even when simulated generously (no stop). "
                       "That closes the last structural question about this crown.")
    for ln in out:
        print(ln)
    p = os.path.join(ROOT, "tools", "r37_results", "r50_missed.csv")
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    with open(os.path.join(ROOT, "tools", "r37_results", "r50_missed.txt"), "w",
              encoding="utf-8") as fh:
        fh.write("\n".join(out) + "\n")
    print()
    print("wrote tools/r37_results/r50_missed.csv, r50_missed.txt")


if __name__ == "__main__":
    main()
