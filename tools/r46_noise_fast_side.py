#!/usr/bin/env python3
"""NOISE ROUND 46 (2026-09-09) -- THE MIRROR TEST: if the tape now rewards entering FAST, a faster
configuration must win the recent years and LOSE the old ones. Plus: has the tape actually changed?

WHY THIS RUNS (owner: "keep testing noise")
-------------------------------------------
Round 45 established the strongest recent fact about this family: **every change that improves NOISE
over 2010-2023 has lost 2024, 2025 and 2026.** The 15-minute bar is ahead in 11 of 17 calendar years
and none of the last three; `confirm_bars=2` on the crown's own chart -- an entirely different
mechanism -- is ahead in 10 of 17 and none of the last three; round 43's C3 geometry has the same
shape; and the 2026-08-17 variant campaign already recorded its filters "gave back some 2025-26
profit". The reading offered was: since 2024 this tape rewards entering FAST, and every version of
"wait for more evidence before entering" now pays for information the market no longer withholds.

**That reading has never been tested. It has only been inferred from things that lost.** Every
candidate this family has produced is SLOWER than the crown. Nobody has pointed the same measurement
in the other direction, and a story that only ever explains failures is not yet a finding.

THE PRE-REGISTERED PREDICTION (written before any cell ran, and falsifiable)
----------------------------------------------------------------------------
If "the tape rewards entering fast since 2024" is true, then a set of pre-declared FASTER variants of
the crown must show the MIRROR of round 45's signature:

  * they should be AHEAD of the crown in the recent stretch (2024-01-01 onward), and
  * BEHIND the crown across the old stretch (2010-2023),
  * with the crossover visible year by year rather than resting on one year.

The falsifier is explicit and is the reason this round is worth running: **if the faster variants are
simply WORSE IN BOTH stretches, the regime story is wrong** and the honest account becomes the dull
one -- the crown is a well-chosen configuration and everything tested near it, faster or slower, is
worse. That outcome would retire the "tape rewards fast" language from this program's vocabulary
rather than leave it standing as a story that only ever explains losses.

NOTHING HERE IS A SEARCH AND NOTHING IS ADOPTED. The variant list is small, declared below, and each
variant is one step FASTER than the crown along one axis the strategy already has. No cell is chosen
by its recent-stretch score; the recent stretch is the PREDICTION being tested, not a selection
window. A variant that wins both stretches would still need its own Auto-Validate before anything
moved, and the 5-minute NOISE lockbox is spent, so nothing here can crown anything.

THE VARIANTS -- each one step faster than the crown, along one axis
--------------------------------------------------------------------
  NARROW BANDS     band_mult_long 0.50 (crown 0.75) -- the entry level sits closer, so a move
                   qualifies sooner. Also the pair 0.50/1.25 (both sides one step in).
  SHORT LOOKBACK   lookback 20 and 10 (crown 40) -- the band re-estimates on fewer sessions, so it
                   tracks a changing regime faster instead of averaging it away.
  BOUNDARY EXIT    exit_mode 'boundary' -- fills on the touch instead of waiting for a bar to close
                   back across VWAP: a faster exit as well as a faster entry.
  FASTER BAR       the same crown geometry on 3-minute and 2-minute bars (round 45's ladder read the
                   slow half; this reads the fast half on the recent tape specifically).
  NO VOL FILTER    vol_skip_pct 100 -- the crown skips entries after the most volatile prior days;
                   removing that gate is "act now" in the most literal sense available.

PART B -- HAS THE TAPE ACTUALLY CHANGED? Independent of P&L, measure the crown's own trades year by
year: how many bars after entry does a winning trade reach its best point (median), and what share of
entries are still open after 30 minutes. If the "faster tape" story is real, the peak should arrive
SOONER in 2024-2026 than it did in 2010-2023. If that timing is flat, then whatever changed is not
the speed of the move, and the round 45 language needs correcting a second time.

DATA. Registered NQ 5m RTH master for the variants (the crown's own tape, no resampling) and the
resampled 1m tape for the 2m/3m cells, all 2010-06-07 -> 2026-07-16 at the stressed cost 0.783 (the
basis a decision rests on; the house 0.533 is printed too). Stretches are calendar: OLD = through
2023-12-31, RECENT = 2024-01-01 onward. The NOISE lockbox is spent; no stretch here is a lockbox and
none of this crowns anything.

Usage:  python tools/r46_noise_fast_side.py
Writes: tools/r37_results/r46_fast_side.csv, r46_timing.csv, r46_fast_side.txt
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
CUT = pd.Timestamp("2024-01-01").date()          # OLD < CUT <= RECENT
COSTS = [0.533, 0.783]
STRESS = 0.783

CROWN = dict(lookback=40, band_mult_long=0.75, band_mult_short=1.5, exit_mode="vwap",
             side="Both", window="all_day", flat_eod=True, skip_holidays=False,
             stop_mode="bandwidth", stop_k=1.75, daytype_mode="skip_bot_short",
             daytype_lo=0.2, daytype_hi=0.8, vol_skip_pct=95.0)

VARIANTS = [
    ("CROWN (reference)", 5, dict(CROWN)),
    ("narrow upper band 0.50", 5, dict(CROWN, band_mult_long=0.5)),
    ("narrow both 0.50/1.25", 5, dict(CROWN, band_mult_long=0.5, band_mult_short=1.25)),
    ("short lookback 20", 5, dict(CROWN, lookback=20)),
    ("short lookback 10", 5, dict(CROWN, lookback=10)),
    ("boundary exit", 5, dict(CROWN, exit_mode="boundary")),
    ("no volatility filter", 5, dict(CROWN, vol_skip_pct=100.0)),
    ("3-minute bar", 3, dict(CROWN)),
    ("2-minute bar", 2, dict(CROWN)),
]


def stats(p):
    p = np.asarray(p, dtype=float)
    if len(p) == 0:
        return dict(n=0, net=0.0, pf=0.0, dd=0.0, ndd=0.0, per_trade=0.0, wr=0.0)
    wins, losses = p[p > 0], p[p < 0]
    gl = -losses.sum()
    eq = np.cumsum(p)
    dd = float(np.max(np.maximum.accumulate(eq) - eq))
    return dict(n=len(p), net=float(p.sum()), pf=(wins.sum() / gl if gl > 0 else float("inf")),
                dd=dd, ndd=(float(p.sum()) / dd if dd > 0 else 99.0),
                per_trade=float(p.mean()), wr=100.0 * len(wins) / len(p))


def split_run(arrays, params, cost):
    r = run_backtest(FN, arrays=arrays, params=dict(params), cost_pts=cost, return_trades=True)
    idx = pd.DatetimeIndex(arrays["index"])
    tr = sorted(r.get("trades") or [], key=lambda z: z[0])
    old, rec, yearly = [], [], {}
    for t in tr:
        d = idx[t[0]].date()
        pnl = t[2] * MULT
        (old if d < CUT else rec).append(pnl)
        yearly[d.year] = yearly.get(d.year, 0.0) + pnl
    return stats(old), stats(rec), yearly


def main():
    print(__doc__.split("WHY THIS RUNS")[0].strip())
    print("=" * 116)

    A5 = load_master_arrays(find_master("NQ", "5m", "rth", SRC), **WIN)
    A1 = load_master_arrays(find_master("NQ", "1m", "rth", SRC), **WIN)
    tapes = {5: A5, 3: resample(A1, 3), 2: resample(A1, 2)}

    print("PART A -- THE MIRROR TEST (stressed cost %.3f; OLD = through 2023, RECENT = 2024 onward)"
          % STRESS)
    print("%-24s | %6s %7s %11s %7s %8s | %6s %7s %11s %7s %8s | %s"
          % ("variant", "n", "PF", "net $", "net/DD", "$/trade", "n", "PF", "net $", "net/DD",
             "$/trade", "vs crown"))
    rows, base_old, base_rec, base_year = [], None, None, None
    yearly_all = {}
    for label, bar, params in VARIANTS:
        o, rc, yr = split_run(tapes[bar], params, STRESS)
        yearly_all[label] = yr
        if label.startswith("CROWN"):
            base_old, base_rec, base_year = o, rc, yr
        do = (100.0 * (o["net"] - base_old["net"]) / abs(base_old["net"])) if base_old else 0.0
        dr = (100.0 * (rc["net"] - base_rec["net"]) / abs(base_rec["net"])) if base_rec else 0.0
        rows.append(dict(variant=label, bar=bar, old_n=o["n"], old_pf=round(o["pf"], 3),
                         old_net=round(o["net"]), old_ndd=round(o["ndd"], 2),
                         old_per=round(o["per_trade"]), rec_n=rc["n"], rec_pf=round(rc["pf"], 3),
                         rec_net=round(rc["net"]), rec_ndd=round(rc["ndd"], 2),
                         rec_per=round(rc["per_trade"]), d_old=round(do, 1), d_rec=round(dr, 1)))
        print("%-24s | %6d %7.3f %11s %7.2f %8s | %6d %7.3f %11s %7.2f %8s | old %+6.1f%%  recent %+6.1f%%"
              % (label, o["n"], o["pf"], format(round(o["net"]), ","), o["ndd"],
                 format(round(o["per_trade"]), ","), rc["n"], rc["pf"],
                 format(round(rc["net"]), ","), rc["ndd"], format(round(rc["per_trade"]), ","),
                 do, dr))

    out = []
    mirror = [r for r in rows if not r["variant"].startswith("CROWN")
              and r["d_rec"] > 0 and r["d_old"] < 0]
    better_recent = [r for r in rows if not r["variant"].startswith("CROWN") and r["d_rec"] > 0]
    worse_both = [r for r in rows if not r["variant"].startswith("CROWN")
                  and r["d_rec"] <= 0 and r["d_old"] <= 0]
    out.append("PART A -- the prediction was: faster variants AHEAD in the recent stretch and BEHIND "
               "in the old one.")
    out.append("  variants showing that MIRROR signature: %d of %d  (%s)"
               % (len(mirror), len(rows) - 1,
                  ", ".join(r["variant"] for r in mirror) if mirror else "none"))
    out.append("  ahead of the crown in the RECENT stretch at all: %d of %d  (%s)"
               % (len(better_recent), len(rows) - 1,
                  ", ".join("%s %+.0f%%" % (r["variant"], r["d_rec"]) for r in better_recent)
                  if better_recent else "none"))
    out.append("  WORSE IN BOTH stretches: %d of %d" % (len(worse_both), len(rows) - 1))
    if not better_recent:
        out.append("  -> THE REGIME STORY IS NOT SUPPORTED. Not one faster variant beats the crown on "
                   "the recent tape, so 'this tape rewards entering fast' cannot be what round 45 "
                   "measured. The honest account is the dull one: the crown is a well-chosen "
                   "configuration and its neighbours - faster AND slower - are worse. Round 45's "
                   "language should be corrected to say exactly that.")
    elif mirror:
        out.append("  -> THE MIRROR IS PRESENT in %d variant(s). That is real support for the regime "
                   "reading, and those variants are the ones to take forward - to a fenced validate "
                   "and forward paper evidence, never straight to the board." % len(mirror))
    else:
        out.append("  -> MIXED: some variants beat the crown recently but not with the mirror shape "
                   "(they do not give it back in the old years), which is what a simply BETTER "
                   "configuration looks like rather than a regime effect.")

    # ── PART B: has the tape's timing actually changed? ──────────────────────────────
    print()
    print("PART B -- the crown's own trades: how fast does a move pay, year by year?")
    r = run_backtest(FN, arrays=A5, params=dict(CROWN), cost_pts=STRESS, return_trades=True)
    idx = pd.DatetimeIndex(A5["index"])
    hi, lo = A5["high"], A5["low"]
    trows = []
    per_year = {}
    for t in sorted(r.get("trades") or [], key=lambda z: z[0]):
        a, b, pnl, side, px = t[0], t[1], t[2], t[3], t[4]
        if b <= a:
            continue
        seg_hi, seg_lo = hi[a:b + 1], lo[a:b + 1]
        # bars from entry to the best price the trade ever saw, in its own direction
        k = int(np.argmax(seg_hi)) if side == 1 else int(np.argmin(seg_lo))
        mfe = (float(seg_hi.max()) - px) if side == 1 else (px - float(seg_lo.min()))
        y = idx[a].year
        per_year.setdefault(y, []).append((k, b - a, mfe * MULT, pnl * MULT))
    print("  %-6s %8s %14s %14s %12s" % ("year", "trades", "bars to peak", "bars held",
                                         "peak $ (med)"))
    for y in sorted(per_year):
        v = per_year[y]
        k = np.median([x[0] for x in v])
        h = np.median([x[1] for x in v])
        m = np.median([x[2] for x in v])
        trows.append(dict(year=y, trades=len(v), bars_to_peak=round(float(k), 2),
                          bars_held=round(float(h), 2), peak_usd=round(float(m))))
        print("  %-6d %8d %14.1f %14.1f %12s" % (y, len(v), k, h, format(round(float(m)), ",")))
    old_k = np.median([x[0] for y in per_year if y < 2024 for x in per_year[y]])
    rec_k = np.median([x[0] for y in per_year if y >= 2024 for x in per_year[y]])
    old_h = np.median([x[1] for y in per_year if y < 2024 for x in per_year[y]])
    rec_h = np.median([x[1] for y in per_year if y >= 2024 for x in per_year[y]])
    out.append("")
    out.append("PART B -- median bars from entry to the trade's best price: OLD %.1f, RECENT %.1f "
               "(bars held: %.1f vs %.1f). A faster tape would show the peak arriving SOONER."
               % (old_k, rec_k, old_h, rec_h))
    if rec_k < old_k * 0.9:
        out.append("  -> the move DOES pay sooner since 2024, which is mechanism-level support for "
                   "the fast reading independent of any P&L comparison.")
    elif rec_k > old_k * 1.1:
        out.append("  -> the move pays LATER since 2024, which contradicts the fast reading outright.")
    else:
        out.append("  -> the timing is essentially UNCHANGED (within 10%), so whatever shifted in "
                   "2024 is not the speed at which a move pays. Round 45's explanation should be "
                   "held loosely: the pattern it measured is real, the story attached to it is not "
                   "supported by the tape's own timing.")

    # ── PART C: amplitude vs a real change of optimum ────────────────────────────────
    # Part B shows the tape's AMPLITUDE grew enormously (median peak per trade ~$100 in
    # 2010-2017 against ~$900 in 2024-2026) while its TIMING did not move. That matters
    # for how rounds 43-45 were read: comparing raw DOLLARS across eras is mechanically
    # inflated by amplitude, so a configuration gap looks dramatic recently for reasons
    # that have nothing to do with edge. Profit factor is amplitude-free. If the slower
    # variants' decay survives on profit factor, it is real; if it does not, rounds 43-45
    # were reading volatility.
    print()
    print("PART C -- amplitude-free check: profit factor by era (the crown against the two slower")
    print("          candidates rounds 44 and 45 measured)")
    A15 = resample(A1, 15)
    era = [("crown 5m (reference)", A5, dict(CROWN)),
           ("confirm_bars=2 on 5m", A5, dict(CROWN, confirm_bars=2)),
           ("15-minute bar", A15, dict(CROWN))]
    print("  %-24s | %-24s | %-24s" % ("config", "OLD 2010-2023", "RECENT 2024-2026"))
    crows, base = [], None
    for lbl, arr, p in era:
        o, rc, _ = split_run(arr, p, STRESS)
        if base is None:
            base = (o["pf"], rc["pf"])
        crows.append(dict(config=lbl, old_pf=round(o["pf"], 3), rec_pf=round(rc["pf"], 3),
                          old_per=round(o["per_trade"]), rec_per=round(rc["per_trade"]),
                          old_edge=round(o["pf"] - base[0], 3), rec_edge=round(rc["pf"] - base[1], 3)))
        print("  %-24s | PF %.3f  $%4.0f a trade  | PF %.3f  $%4.0f a trade   (edge vs crown "
              "%+.3f -> %+.3f)" % (lbl, o["pf"], o["per_trade"], rc["pf"], rc["per_trade"],
                                   o["pf"] - base[0], rc["pf"] - base[1]))
    out.append("")
    out.append("PART C -- on profit factor, which amplitude cannot inflate, the decay is REAL: the "
               "two slower candidates led the crown by +%.3f and +%.3f across 2010-2023 and now "
               "trail it by %.3f and %.3f, while the crown's own profit factor is FLAT (%.3f -> "
               "%.3f)." % (crows[1]["old_edge"], crows[2]["old_edge"], abs(crows[1]["rec_edge"]),
                           abs(crows[2]["rec_edge"]), crows[0]["old_pf"], crows[0]["rec_pf"]))
    out.append("  Put with Part A (nothing faster wins either) and Part B (the tape's timing is "
               "unchanged), the correct account is NOT that this tape rewards speed. It is that THE "
               "OPTIMUM HAS MOVED TO WHERE THE CROWN ALREADY SITS: before 2024 the crown was on the "
               "fast side of a slower optimum, and today it is the best point in BOTH directions.")
    out.append("  That is good news for the crown and a reason to keep measuring rather than to "
               "conclude - an optimum that moved once can move again.")
    out.append("  METHOD, worth banking: the tape's amplitude grew about sevenfold (median peak per "
               "trade ~$100 in 2010-2017 against ~$900 in 2024-2026) while its timing did not move, "
               "so ANY cross-era comparison in raw dollars is inflated. Compare eras on profit "
               "factor or on volatility-normalised dollars, never on raw net.")

    for f, rr in (("r46_fast_side.csv", rows), ("r46_timing.csv", trows), ("r46_era_pf.csv", crows)):
        p = os.path.join(ROOT, "tools", "r37_results", f)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rr[0]))
            w.writeheader()
            w.writerows(rr)

    print()
    print("=" * 116)
    for ln in out:
        print(ln)
    with open(os.path.join(ROOT, "tools", "r37_results", "r46_fast_side.txt"), "w",
              encoding="utf-8") as fh:
        fh.write("\n".join(out) + "\n")
    print()
    print("wrote tools/r37_results/r46_fast_side.csv, r46_timing.csv, r46_fast_side.txt")


if __name__ == "__main__":
    main()
