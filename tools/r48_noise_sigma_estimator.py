#!/usr/bin/env python3
"""NOISE ROUND 48 (2026-09-09) -- THE BAND ESTIMATOR ITSELF: five ways to measure "how far price
usually travels by this time of day", tested against the one the strategy has always used.

WHY THIS RUNS (owner: "continue optimizing and search for more on the NOISE alpha")
-----------------------------------------------------------------------------------
Rounds 43-47 swept three spaces around this crown and all four came back empty: the KNOB space
(43, 45, 46), the BAR space (44, 45) and the CONDITIONAL space (47, whose one candidate turned out
to be a one-bar look-ahead and was retracted the same day). Every one of those rounds moved the
strategy's settings. **None of them touched the strategy's core measurement.**

NOISE decides everything from one number. For each bar ordinal k inside the session it estimates
how far price has typically travelled from the open by that point:

    AD[session, k]  = |close(k) - open(0)| / open(0)          (one session's displacement profile)
    sigma[today, k] = MEAN of AD[k] over the previous `lookback` sessions

and the bands are `ref x (1 +/- band_mult x sigma)`. That plain mean over the last N sessions has
been the estimator since the family was written. It has never been questioned, and it has two
obvious weaknesses that are worth a proper test:

  * **A mean is not robust.** One crash session inflates the estimate for the next `lookback`
    sessions, widening the bands and suppressing entries long after the event has passed.
  * **It is entirely historical.** It knows the typical 10:30 displacement over the last 40
    sessions and nothing about whether TODAY is wild or quiet. Round 46 measured that this tape's
    amplitude grew about sevenfold since 2010 while its timing did not move, so an estimator that
    cannot see today's own scale is exactly the thing that ages badly.

THE FIVE ESTIMATORS (all causal -- each value used at bar k reads only sessions strictly before
today, plus, for the last one, today's own COMPLETED bars before k)

  BASE      the shipped mean over the last `lookback` sessions.
  MEDIAN    the median of the same window. Robust: one wild session no longer moves it.
  TRIM20    the mean after dropping the highest 20% of sessions. The middle ground.
  EWMA      an exponentially weighted mean across sessions (half-life = lookback/3), so a changed
            regime is reflected in days rather than in `lookback` days.
  DAYSCALE  the BASE profile multiplied by TODAY's own scale: at bar k, the ratio of today's
            realised displacement over bars 0..k-1 to what the profile expected over those same
            bars, clipped to [0.5, 2.0] and held at 1.0 for the first six bars. This is the only
            estimator here that lets the band breathe with the session actually being traded.

THE PRE-REGISTERED BAR (fixed before any estimator ran)
--------------------------------------------------------
An estimator becomes a CANDIDATE, meaning it earns an Auto-Validate, only if it clears ALL of:

  (a) higher PROFIT FACTOR than BASE at BOTH costs (house 0.533 and stressed 0.783). Profit factor,
      never dollars -- round 46's amplitude lesson;
  (b) higher profit factor than BASE in BOTH eras (through 2023, and 2024 onward). Rounds 43-46
      each found something that beat the crown historically and had quietly stopped working;
  (c) concentration no worse: top-10 share within 3 points of BASE and ex-top-10 net positive;
  (d) net-over-drawdown at least as good at the stressed cost;
  (e) it must hold across the LOOKBACK it is given -- tested at 24, 40 (the crown) and 60 sessions.
      An estimator that only wins at one lookback is a coincidence, not a better measurement.

Everything else is held exactly at the live crown: bands 0.75/1.50, VWAP exit, both sides, all day,
bandwidth stop 1.75, weak-close short veto, volatility skip 95. The ONLY thing that changes between
cells is how sigma is computed, which is what makes this a clean test of the measurement itself.

Nothing is adopted here. A winner gets an Auto-Validate queued on a fenced file and then forward
paper evidence, in that order.

Usage:  python tools/r48_noise_sigma_estimator.py
Writes: tools/r37_results/r48_sigma.csv, r48_sigma.txt
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
from augur_engine.engine import run_backtest, load_strategy  # noqa: E402

MULT = 20.0
SRC = "db_noadj_rth"
WIN = dict(date_from="2010-06-07", date_to="2026-07-16")
CUT = pd.Timestamp("2024-01-01").date()
COSTS = [0.533, 0.783]
LOOKBACKS = [24, 40, 60]

CROWN = dict(lookback=40, band_mult_long=0.75, band_mult_short=1.5, exit_mode="vwap",
             side="Both", window="all_day", flat_eod=True, skip_holidays=False,
             stop_mode="bandwidth", stop_k=1.75, daytype_mode="skip_bot_short",
             daytype_lo=0.2, daytype_hi=0.8, vol_skip_pct=95.0)


def _profiles(o, c, sess_bounds):
    """AD[session, bar] = |close - session open| / session open. Exactly the shipped definition."""
    n_sess = len(sess_bounds)
    max_len = max((b - a) for a, b in sess_bounds) if sess_bounds else 0
    AD = np.full((n_sess, max_len), np.nan, dtype=float)
    for si, (a, b) in enumerate(sess_bounds):
        AD[si, :b - a] = np.abs(c[a:b] - o[a]) / o[a]
    return AD, n_sess, max_len


def make_sigma(mode):
    """Return a drop-in replacement for the strategy's _sigma_matrix. Every variant reads only
    sessions STRICTLY BEFORE today; DAYSCALE additionally reads today's own completed bars."""
    def _sigma(o, c, sess_bounds, lookback):
        AD, n_sess, max_len = _profiles(o, c, sess_bounds)
        sig = np.full((n_sess, max_len), np.nan, dtype=float)
        with np.errstate(invalid="ignore"):
            if mode == "EWMA":
                hl = max(1.0, lookback / 3.0)
                w = np.exp(-np.log(2.0) * np.arange(lookback)[::-1] / hl)   # newest gets weight 1
                w = w / w.sum()
            for si in range(lookback, n_sess):
                win = AD[si - lookback:si, :]
                if mode == "BASE" or mode == "DAYSCALE":
                    sig[si, :] = np.nanmean(win, axis=0)
                elif mode == "MEDIAN":
                    sig[si, :] = np.nanmedian(win, axis=0)
                elif mode == "TRIM20":
                    q = np.nanpercentile(win, 80, axis=0)
                    keep = win <= q
                    sig[si, :] = np.array([np.nanmean(win[keep[:, k], k]) if keep[:, k].any()
                                           else np.nan for k in range(max_len)])
                elif mode == "EWMA":
                    ww = np.where(np.isnan(win), 0.0, w[:, None])
                    tot = ww.sum(axis=0)
                    sig[si, :] = np.where(tot > 0,
                                          np.nansum(np.nan_to_num(win) * ww, axis=0) / np.maximum(tot, 1e-12),
                                          np.nan)
                else:
                    raise ValueError(mode)
        if mode == "DAYSCALE":
            # today's own scale, from COMPLETED bars only: at bar k compare today's realised
            # displacement over bars 0..k-1 with what the profile expected over the same bars.
            for si in range(lookback, n_sess):
                today = AD[si, :]
                prof = sig[si, :].copy()
                cum_t = np.nancumsum(np.nan_to_num(today))
                cum_p = np.nancumsum(np.nan_to_num(prof))
                ratio = np.ones(max_len)
                for k in range(6, max_len):
                    if cum_p[k - 1] > 0 and not np.isnan(cum_t[k - 1]):
                        ratio[k] = min(2.0, max(0.5, cum_t[k - 1] / cum_p[k - 1]))
                    else:
                        ratio[k] = ratio[k - 1]
                sig[si, :] = prof * ratio
        return sig
    return _sigma


def stats(p, years):
    p = np.asarray(p, float)
    if not len(p):
        return dict(n=0, net=0.0, pf=0.0, dd=0.0, ndd=0.0, top10=float("nan"), ex10=0.0, per=0.0)
    w, l = p[p > 0].sum(), -p[p < 0].sum()
    eq = np.cumsum(p)
    d = float(np.max(np.maximum.accumulate(eq) - eq))
    net = float(p.sum())
    top10 = float(np.sort(p)[-10:].sum()) if len(p) >= 10 else net
    return dict(n=len(p), net=net, pf=(w / l if l > 0 else 99.0), dd=d,
                ndd=(net / d if d > 0 else 99.0),
                top10=(100.0 * top10 / net if net > 0 else float("nan")),
                ex10=net - top10, per=net / len(p))


def measure(mod, A, params, cost):
    r = run_backtest(mod, arrays=A, params=dict(params), cost_pts=cost, return_trades=True)
    tr = sorted(r.get("trades") or [], key=lambda z: z[0])
    idx = pd.DatetimeIndex(A["index"])
    d = np.array([idx[t[0]].date() for t in tr])
    p = np.array([t[2] * MULT for t in tr])
    yrs = (idx[-1] - idx[0]).days / 365.25
    return dict(all=stats(p, yrs), old=stats(p[d < CUT], yrs * 0.85), rec=stats(p[d >= CUT], yrs * 0.15))


def main():
    print(__doc__.split("WHY THIS RUNS")[0].strip())
    print("=" * 116)
    A = load_master_arrays(find_master("NQ", "5m", "rth", SRC), **WIN)
    mod = load_strategy("NOISE_1_0.py")
    original = mod._sigma_matrix

    modes = ["BASE", "MEDIAN", "TRIM20", "EWMA", "DAYSCALE"]
    rows, R = [], {}
    for lb in LOOKBACKS:
        print("LOOKBACK %d sessions" % lb)
        print("  %-9s %6s | %6s %8s %10s %7s %7s %7s | %8s %8s | %8s %8s"
              % ("estimator", "cost", "n", "PF", "net $", "net/DD", "top10", "$/trade",
                 "PF old", "PF new", "net old", "net new"))
        for mode in modes:
            mod._sigma_matrix = make_sigma(mode) if mode != "BASE" else original
            for cost in COSTS:
                m = measure(mod, A, dict(CROWN, lookback=lb), cost)
                a, o, rc = m["all"], m["old"], m["rec"]
                R[(mode, lb, cost)] = m
                rows.append(dict(estimator=mode, lookback=lb, cost=cost, n=a["n"],
                                 pf=round(a["pf"], 4), net=round(a["net"]), dd=round(a["dd"]),
                                 ndd=round(a["ndd"], 2), top10=round(a["top10"], 1),
                                 ex10=round(a["ex10"]), per=round(a["per"]),
                                 pf_old=round(o["pf"], 4), pf_new=round(rc["pf"], 4),
                                 net_old=round(o["net"]), net_new=round(rc["net"])))
                print("  %-9s %6.3f | %6d %8.4f %10s %7.2f %6.1f%% %7s | %8.4f %8.4f | %8s %8s"
                      % (mode, cost, a["n"], a["pf"], format(round(a["net"]), ","), a["ndd"],
                         a["top10"], format(round(a["per"]), ","), o["pf"], rc["pf"],
                         format(round(o["net"]), ","), format(round(rc["net"]), ",")))
        print()
    mod._sigma_matrix = original

    p = os.path.join(ROOT, "tools", "r37_results", "r48_sigma.csv")
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

    out = ["THE BAR: higher profit factor than BASE at BOTH costs AND in BOTH eras, concentration "
           "within 3 points with a positive ex-top-10 net, net-over-drawdown at least as good at "
           "the stressed cost, and it must hold at ALL THREE lookbacks (24 / 40 / 60).", ""]
    winners = []
    for mode in modes[1:]:
        checks, detail = [], []
        for lb in LOOKBACKS:
            ok = True
            for cost in COSTS:
                b, v = R[("BASE", lb, cost)], R[(mode, lb, cost)]
                ok = ok and v["all"]["pf"] > b["all"]["pf"]
                if cost == 0.783:
                    ok = ok and v["old"]["pf"] > b["old"]["pf"] and v["rec"]["pf"] > b["rec"]["pf"]
                    ok = ok and v["all"]["ndd"] >= b["all"]["ndd"]
                    ok = ok and v["all"]["top10"] <= b["all"]["top10"] + 3 and v["all"]["ex10"] > 0
            checks.append(ok)
            b, v = R[("BASE", lb, 0.783)], R[(mode, lb, 0.783)]
            detail.append("lb %d: PF %.4f vs %.4f (old %.4f vs %.4f, new %.4f vs %.4f)"
                          % (lb, v["all"]["pf"], b["all"]["pf"], v["old"]["pf"], b["old"]["pf"],
                             v["rec"]["pf"], b["rec"]["pf"]))
        allok = all(checks)
        if allok:
            winners.append(mode)
        out.append("  %-9s %s  [%d of 3 lookbacks]" % (mode, "CLEARS EVERY CLAUSE" if allok
                                                       else "no", sum(checks)))
        for d in detail:
            out.append("      " + d)
    out.append("")
    if winners:
        out.append("CANDIDATE(S): %s -- queue an Auto-Validate on a fenced file carrying this "
                   "estimator, then forward paper evidence. Nothing is adopted here." % ", ".join(winners))
    else:
        out.append("NO ESTIMATOR CLEARS THE BAR. The plain mean the family has always used is not "
                   "beaten by a robust, a trimmed, a recency-weighted or a same-day-scaled version "
                   "of itself, which closes the last untouched space around this crown.")
    for ln in out:
        print(ln)
    with open(os.path.join(ROOT, "tools", "r37_results", "r48_sigma.txt"), "w",
              encoding="utf-8") as fh:
        fh.write("\n".join(out) + "\n")
    print()
    print("wrote tools/r37_results/r48_sigma.csv, r48_sigma.txt")


if __name__ == "__main__":
    main()
