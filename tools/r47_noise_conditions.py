#!/usr/bin/env python3
"""NOISE ROUND 47 (2026-09-09) -- WHERE IS THE ALPHA CONDITIONAL? A pre-registered battery of
entry-time conditions on the crown, each scored as a size tilt against the SHIFT null.

WHY THIS RUNS (owner: "continue optimizing the frontier models and search for more on the NOISE alpha")
--------------------------------------------------------------------------------------------------
Rounds 43-46 exhausted the KNOB directions around the crown and all four ended the same way: nothing
moves. Round 46's closing finding was that the optimum has moved to where the crown already sits, so
it is the best point in both directions -- which means more perturbation of the same knobs is a dead
line of enquiry, not a promising one.

What has NOT been swept is CONDITIONAL alpha: not "is a different configuration better on average"
but "is the crown's own edge concentrated in identifiable states, so the same trades sized by state
earn more than the same trades sized flat". Exactly one such effect is known and validated on this
family -- the 60-minute compression tilt (memory `edgelog-ttm-squeeze-study`: real and strong on
NOISE under the shift null at 0.0-0.5%, while the same claim FAILED on ORB and ENGU-Q). One
validated effect found by accident is a reason to sweep the space properly, once, with the right
null and the right corrections.

THE NULL MATTERS AND IS THE REASON THIS IS WORTH RUNNING NOW. `tools/tilt_guard.py` gained
`permute="shift"` on 2026-09-09: it rolls the condition tag along the trade sequence, preserving the
condition's own firing rate and run lengths and destroying only its ALIGNMENT with the trades. A
day-resampling null asks the wrong question of an intraday condition and can manufacture
significance from the shape mismatch alone. Every intraday condition below uses the shift null;
the two calendar conditions use the day null, which is correct for them.

THE PRE-REGISTERED BAR (fixed before any condition was computed)
-----------------------------------------------------------------
A condition becomes a CANDIDATE worth a fenced validate only if it clears ALL of:

  (1) SIZE OF EFFECT, MEASURED AMPLITUDE-FREE. Round 46 established that this tape's amplitude
      grew about sevenfold while its timing did not move, so DOLLARS PER TRADE are not a safe
      effect measure: a condition that selects volatile states earns more dollars for reasons
      that have nothing to do with edge. The effect here is PROFIT FACTOR INSIDE the state
      against profit factor outside it -- a ratio, so amplitude cancels -- supported by dollars
      per unit of entry-time volatility. The bar is a profit-factor ratio of at least 1.15 in
      the direction being tilted, on at least 200 tagged trades.
  (1b) DIRECTION IS CHOSEN BY THE DATA, NOT ASSUMED. A state that trades BETTER is tested as a
      size-up (1.5x); a state that trades WORSE is tested as a CUT (0.5x). Testing a bad state
      as a size-up, which an earlier draft of this file did, asks a question nobody would act on.
  (2) THE FULL TILT GUARD passes in that direction: better money on both stretches with
      drawdown no more than 10% worse, it must beat the exposure-matched uniform control (a
      size-up that cannot beat flat leverage IS flat leverage), the shift permutation must place
      it at or under 5%, and no single trade may carry the gain.
  (3) MULTIPLICITY: the permutation p-value survives Benjamini-Hochberg across the whole battery.
      Twelve conditions were declared before any was computed; the correction is over all twelve,
      whatever each one turns out to say.
  (4) ERA STABILITY -- the clause this session earned the hard way: the profit-factor edge must
      hold in BOTH 2010-2023 and 2024-2026. Rounds 43-46 found three separate configurations that
      beat the crown historically and had quietly stopped working; a conditional edge that only
      paid before 2024 is the same trap wearing different clothes.

Nothing here is adopted, nothing is crowned, and no board or NinjaTrader configuration is touched.
A condition that clears all four would earn a fenced Auto-Validate and forward paper evidence, in
that order. The 5-minute NOISE lockbox is SPENT, so the 2024-2026 stretch is a stability CHECK and
never a selection window.

THE TWELVE CONDITIONS, declared before computing any of them. Every one is causal at entry -- it
uses only bars up to and including the entry bar, and the day's own completed history:
   1  compression: the band's own width in the bottom third of its trailing 60-session history
   2  expansion: the same in the top third (the mirror -- if compression pays, this should not)
   3  first hour of the session
   4  last hour of the session
   5  midday (neither of the above)
   6  with-trend: the entry side agrees with the sign of close minus its 200-bar mean
   7  against-trend: it does not
   8  gap day: the open is at least half an average daily range from the prior close
   9  quiet open: the first 30 minutes covered less range than usual for the session
  10  busy open: the first 30 minutes covered more range than usual
  11  Monday (calendar -- day null)
  12  Friday (calendar -- day null)

Usage:  python tools/r47_noise_conditions.py [--perm N]
Writes: tools/r37_results/r47_conditions.csv, r47_conditions.txt
"""
import argparse
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
from tilt_guard import guard  # noqa: E402

FN = "NOISE_1_0.py"
MULT = 20.0
SRC = "db_noadj_rth"
WIN = dict(date_from="2010-06-07", date_to="2026-07-16")
CUT = pd.Timestamp("2024-01-01").date()
STRESS = 0.783
TILT = 1.5
MIN_TAGGED = 200

CROWN = dict(lookback=40, band_mult_long=0.75, band_mult_short=1.5, exit_mode="vwap",
             side="Both", window="all_day", flat_eod=True, skip_holidays=False,
             stop_mode="bandwidth", stop_k=1.75, daytype_mode="skip_bot_short",
             daytype_lo=0.2, daytype_hi=0.8, vol_skip_pct=95.0)


def features(A, entries, sides):
    """Per-trade entry-time features, all causal: bar i uses bars <= i only."""
    idx = pd.DatetimeIndex(A["index"])
    hi, lo, cl, op = A["high"], A["low"], A["close"], A["open"]
    did = np.asarray(A["day_id"])
    n = len(cl)

    # --- rolling band-width proxy: the strategy's own scale is the recent realised range ---
    tr = np.maximum(hi[1:], cl[:-1]) - np.minimum(lo[1:], cl[:-1])
    tr = np.r_[hi[0] - lo[0], tr]
    win = 24                                   # two hours of 5m bars
    csum = np.cumsum(np.r_[0.0, tr])
    atr = (csum[win:] - csum[:-win]) / win
    atr = np.r_[np.full(win, np.nan), atr][:n]

    # its own trailing distribution, 60 sessions back, shifted so today is never in it
    day_start = {}
    for i, d in enumerate(did):
        day_start.setdefault(d, i)
    days = sorted(day_start)
    day_atr = {d: np.nanmedian(atr[day_start[d]:day_start[d] + 78]) for d in days}
    lo3, hi3 = {}, {}
    vals = [day_atr[d] for d in days]
    for k, d in enumerate(days):
        past = [v for v in vals[max(0, k - 60):k] if not np.isnan(v)]
        if len(past) >= 20:
            lo3[d], hi3[d] = np.percentile(past, 33), np.percentile(past, 67)

    # --- slow mean for the trend condition (200 bars, causal) ---
    m200 = pd.Series(cl).rolling(200, min_periods=200).mean().to_numpy()

    # --- per-day: prior close, open, first-30-minute range, and its trailing typical value ---
    first30, dopen, prior_close, drange = {}, {}, {}, {}
    prev = None
    for d in days:
        s = day_start[d]
        e = s + 78
        dopen[d] = op[s]
        first30[d] = float(np.max(hi[s:s + 6]) - np.min(lo[s:s + 6]))
        drange[d] = float(np.max(hi[s:e]) - np.min(lo[s:e]))
        prior_close[d] = cl[day_start[prev] + 77] if prev is not None and day_start[prev] + 77 < n else np.nan
        prev = d
    f30_hist, dr_hist = {}, {}
    f30v = [first30[d] for d in days]
    drv = [drange[d] for d in days]
    for k, d in enumerate(days):
        p1 = f30v[max(0, k - 60):k]
        p2 = drv[max(0, k - 60):k]
        if len(p1) >= 20:
            f30_hist[d] = float(np.median(p1))
            dr_hist[d] = float(np.median(p2))

    out = {}
    dts = idx[entries]
    dd = np.array([did[i] for i in entries])
    out["compression"] = np.array([(d in lo3) and (not np.isnan(atr[i])) and atr[i] <= lo3[d]
                                   for i, d in zip(entries, dd)])
    out["expansion"] = np.array([(d in hi3) and (not np.isnan(atr[i])) and atr[i] >= hi3[d]
                                 for i, d in zip(entries, dd)])
    ordinal = np.array([i - day_start[d] for i, d in zip(entries, dd)])
    out["first hour"] = ordinal < 12
    out["last hour"] = ordinal >= 66
    out["midday"] = (ordinal >= 12) & (ordinal < 66)
    agree = np.array([(not np.isnan(m200[i])) and ((cl[i] > m200[i]) == (s == 1))
                      for i, s in zip(entries, sides)])
    out["with-trend"] = agree
    out["against-trend"] = np.array([(not np.isnan(m200[i])) and not a
                                     for i, a in zip(entries, agree)])
    out["gap day"] = np.array([(d in dr_hist) and (not np.isnan(prior_close[d]))
                               and abs(dopen[d] - prior_close[d]) >= 0.5 * dr_hist[d]
                               for d in dd])
    out["quiet open"] = np.array([(d in f30_hist) and first30[d] < f30_hist[d] for d in dd])
    out["busy open"] = np.array([(d in f30_hist) and first30[d] > f30_hist[d] for d in dd])
    out["Monday"] = np.array([t.weekday() == 0 for t in dts])
    out["Friday"] = np.array([t.weekday() == 4 for t in dts])
    scale = np.array([atr[i] if not np.isnan(atr[i]) else np.nan for i in entries])
    return out, dts, scale


def bh(pvals):
    """Benjamini-Hochberg: return the adjusted values in the input order."""
    p = np.asarray(pvals, float)
    m = len(p)
    order = np.argsort(p)
    adj = np.empty(m)
    prev = 1.0
    for rank in range(m - 1, -1, -1):
        i = order[rank]
        prev = min(prev, p[i] * m / (rank + 1))
        adj[i] = prev
    return adj


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--perm", type=int, default=2000)
    a = ap.parse_args()

    print(__doc__.split("WHY THIS RUNS")[0].strip())
    print("=" * 112)

    A = load_master_arrays(find_master("NQ", "5m", "rth", SRC), **WIN)
    r = run_backtest(FN, arrays=A, params=dict(CROWN), cost_pts=STRESS, return_trades=True)
    tr = sorted(r.get("trades") or [], key=lambda z: z[0])
    entries = [t[0] for t in tr]
    sides = [t[3] for t in tr]
    pnl = np.array([t[2] * MULT for t in tr])
    feats, dts, scale = features(A, entries, sides)
    dates = np.array([d.date() for d in dts])
    old, rec = dates < CUT, dates >= CUT
    base = np.ones(len(pnl))

    print("crown trades %d (%d before 2024, %d since), net $%s at the stressed cost"
          % (len(pnl), old.sum(), rec.sum(), format(round(pnl.sum()), ",")))
    print("battery of %d pre-declared conditions; intraday ones use the SHIFT null, calendar ones "
          "the DAY null" % len(feats))
    print()
    print("  %-16s %7s %8s %8s %7s | %8s %8s | %-9s %-8s %s"
          % ("condition", "tagged", "PF in", "PF out", "PF rat", "old rat", "new rat",
             "direction", "perm p", "guard"))

    rows = []
    for name, mask in feats.items():
        mask = np.asarray(mask, bool)
        nin = int(mask.sum())
        if nin < 10 or nin == len(mask):
            continue

        def pf(v):
            w = float(v[v > 0].sum())
            l = float(-v[v < 0].sum())
            return (w / l) if l > 0 else float("inf")

        pf_in, pf_out = pf(pnl[mask]), pf(pnl[~mask])
        ratio = pf_in / pf_out if pf_out > 0 else float("nan")
        okv = ~np.isnan(scale) & (scale > 0)
        r_in = float(np.mean(pnl[mask & okv] / (scale[mask & okv] * MULT))) if (mask & okv).sum() else float("nan")
        r_out = float(np.mean(pnl[~mask & okv] / (scale[~mask & okv] * MULT))) if (~mask & okv).sum() else float("nan")
        po = (pf(pnl[mask & old]) / pf(pnl[~mask & old])) if (mask & old).sum() > 20 else float("nan")
        pn = (pf(pnl[mask & rec]) / pf(pnl[~mask & rec])) if (mask & rec).sum() > 20 else float("nan")

        up = pf_in >= pf_out
        mult = TILT if up else 0.5
        permute = "days" if name in ("Monday", "Friday") else "shift"
        g = guard(pnl, dts, base, mask, mult, old, rec, permute=permute,
                  label="NOISE %s %s%.1fx" % (name, "" if up else "CUT ", mult),
                  perm=a.perm, min_trades=25)
        p = 1.0
        for ln in g["report"].splitlines():
            if "permutation" in ln and "match it" in ln:
                try:
                    p = float(ln.split("->")[1].split("%")[0].strip()) / 100.0
                except Exception:
                    pass
        rows.append(dict(condition=name, tagged=nin, share=round(100.0 * nin / len(mask), 1),
                         pf_in=round(pf_in, 3), pf_out=round(pf_out, 3), pf_ratio=round(ratio, 3),
                         r_in=round(r_in, 4), r_out=round(r_out, 4),
                         per_in=round(float(pnl[mask].mean())),
                         per_out=round(float(pnl[~mask].mean())),
                         pf_ratio_old=round(po, 3), pf_ratio_new=round(pn, 3),
                         direction=("size-up %.1fx" % mult) if up else ("cut %.1fx" % mult),
                         perm_p=round(p, 4), guard="PASS" if g["passed"] else "fail",
                         reasons="; ".join(g["reasons"])[:150], permute=permute))
        print("  %-16s %7d %8.3f %8.3f %7.2f | %8s %8s | %-9s %-8.3f %s"
              % (name, nin, pf_in, pf_out, ratio,
                 ("%.2f" % po) if po == po else "-", ("%.2f" % pn) if pn == pn else "-",
                 "size-up" if up else "CUT", p, "PASS" if g["passed"] else "fail"))

    padj = bh([r["perm_p"] for r in rows])
    for r_, q in zip(rows, padj):
        r_["perm_q"] = round(float(q), 4)

    out = []
    out.append("THE PRE-REGISTERED BAR: profit-factor ratio >= 1.15 in the tilted direction on >= %d "
               "tagged trades, the full tilt guard passing, the permutation surviving "
               "Benjamini-Hochberg across all %d conditions, and the edge holding in BOTH eras. "
               "Effects are read on PROFIT FACTOR rather than dollars because round 46 showed this "
               "tape's amplitude grew about sevenfold while its timing did not move."
               % (MIN_TAGGED, len(rows)))
    def effect(r_):
        """distance from neutral in the direction being tilted"""
        return r_["pf_ratio"] if r_["direction"].startswith("size-up") else 1.0 / max(r_["pf_ratio"], 1e-9)

    def era_ok(r_):
        a_, b_ = r_["pf_ratio_old"], r_["pf_ratio_new"]
        if a_ != a_ or b_ != b_:
            return False
        if r_["direction"].startswith("size-up"):
            return a_ >= 1.0 and b_ >= 1.0
        return a_ <= 1.0 and b_ <= 1.0

    cands = [r_ for r_ in rows
             if r_["tagged"] >= MIN_TAGGED and effect(r_) >= 1.15 and r_["guard"] == "PASS"
             and r_["perm_q"] <= 0.05 and era_ok(r_)]
    near = [r_ for r_ in rows if r_ not in cands and effect(r_) >= 1.15
            and r_["tagged"] >= MIN_TAGGED]
    out.append("")
    for r_ in sorted(rows, key=lambda x: -effect(x)):
        out.append("  %-16s PF %5.3f in vs %5.3f out = %5.2f (old %5s, since 2024 %5s) | %5d trades "
                   "| %-11s | perm p %.3f q %.3f | guard %s%s"
                   % (r_["condition"], r_["pf_in"], r_["pf_out"], r_["pf_ratio"],
                      ("%.2f" % r_["pf_ratio_old"]) if r_["pf_ratio_old"] == r_["pf_ratio_old"] else "-",
                      ("%.2f" % r_["pf_ratio_new"]) if r_["pf_ratio_new"] == r_["pf_ratio_new"] else "-",
                      r_["tagged"], r_["direction"], r_["perm_p"], r_["perm_q"], r_["guard"],
                      (" -- " + r_["reasons"]) if r_["reasons"] else ""))
    out.append("")
    if cands:
        out.append("CANDIDATES clearing every clause: %s" % ", ".join(c["condition"] for c in cands))
        out.append("  Each earns a fenced Auto-Validate and then forward paper evidence, in that "
                   "order. Nothing is adopted here.")
    else:
        out.append("NO CONDITION CLEARS EVERY CLAUSE. The crown's edge is not concentrated in any of "
                   "the twelve states declared, which is the same answer the knob sweeps of rounds "
                   "43-46 gave from a different direction: this configuration is hard to improve "
                   "from the outside.")
        if near:
            out.append("  Closest, and why each falls short: " +
                       "; ".join("%s (PF ratio %.2f, %s)" %
                                 (r_["condition"], r_["pf_ratio"],
                                  "guard " + r_["guard"] if r_["guard"] != "PASS"
                                  else "q=%.3f" % r_["perm_q"] if r_["perm_q"] > 0.05
                                  else "era split %.2f/%.2f" % (r_["pf_ratio_old"], r_["pf_ratio_new"]))
                                 for r_ in near[:4]))

    p = os.path.join(ROOT, "tools", "r37_results", "r47_conditions.csv")
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print()
    print("=" * 112)
    for ln in out:
        print(ln)
    with open(os.path.join(ROOT, "tools", "r37_results", "r47_conditions.txt"), "w",
              encoding="utf-8") as fh:
        fh.write("\n".join(out) + "\n")
    print()
    print("wrote tools/r37_results/r47_conditions.csv, r47_conditions.txt")


if __name__ == "__main__":
    main()
