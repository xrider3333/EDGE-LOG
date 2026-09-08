"""
ORB ROUND 9 - DOES THE #314 DECISION SURVIVE REALITY?  (2026-09-08, owner: "continue
improvements")

Every parameter direction on ORB is now closed (rounds 4-8, #325 FAIL). What is left is
whether the crown we chose holds up under the things a backtest table hides. Three tests,
each cheap, each able to change a decision:

  A `fill`      REALISTIC ENTRY. ORB_3_6 fills at the CLOSE of the confirming bar. Live, a
                market order on that close fills at the NEXT bar's open. ORB_3_6_FILL.py
                adds that as a knob. Re-run #314 and #234 both ways and report the cost.
                If the edge dies on next-open fills, nothing else about the crown matters.

  B `boot`      IS THE RISK ADVANTAGE REAL? #314 was crowned on MAR and drawdown, and this
                project already knows maxDD's confidence interval is wider than the
                statistic (memory: net/DD unreliable). Stationary block bootstrap of both
                trade sequences (2,000 resamples, 20-trade blocks): how often is #314's
                MAR actually higher, and what is the interval on the drawdown gap?

  C `size`      CONSTANT-RISK SIZING, the one lever never tried on ORB. Fixed one contract
                means dollar risk per trade swings with the opening-range width. Sizing so
                every trade risks the same dollars (in MICROS, so it can be done finely:
                10 MNQ = 1 NQ) is live-legal because the stop distance is known at entry.
                Normalised to the SAME average size as fixed 10 micros, so it is a shape
                comparison not a leverage comparison. Risk-parity was DEAD on ENGU-Q; ORB
                is different because its stop is tied to a range that varies 5x.

RESULTS (2026-09-08, tools/orb_realism.py all):

  A. FILL - the close-fill assumption is HONEST for this strategy. #314 on next-open fills:
     net $396,343 vs $397,150 (-$800 over 16 years), drawdown identical, PF 1.370 vs 1.371,
     MAR unchanged (0.85 full / 2.79 five-year), 12 trades lost to last-bar confirmations.
     The gap between confirming close and next open averages -0.05 pts (slightly in our
     favour), median zero, 90th percentile one tick; one 359-pt air pocket in 16 years.
     Same picture on #234. Backtest entries should track paper and NT closely.

  B. BOOTSTRAP - the #314-over-#234 risk advantage is NOT statistically separable.
     Full window: P(MAR #314 > #234) 62%, P(DD lower) 67%, DD-gap 90% interval
     [-$14,178, +$28,364]. Five-year window, the one the crown was chosen on: P(MAR
     higher) 54%, P(DD lower) 61%, bootstrap median MAR 2.20 vs 2.16, DD-gap interval
     [-$14,510, +$21,178]. Same entries, different exit - the exit does not produce an
     outcome the data can tell apart. The point estimates (2.79 vs 2.37) sit well inside
     resampling noise. #314 keeps the crown on its non-statistical merits (PASS with the
     ES leg) but nobody should describe it as a demonstrated improvement.

  C. CONSTANT-RISK SIZING IS DEAD, and the reason is the most useful thing in this file.
     Equalising dollar risk per trade at the SAME average size collapses net from
     $397,150 to $123,698 and MAR from 0.85 to 0.31. Constant risk means sizing DOWN on
     wide-opening-range days and UP on narrow ones - and wide-range sessions are where
     ORB earns its money (a wide range is a trend day; a 5R target is reachable). It
     systematically under-bets the best days. This is the same fact the vol-regime
     filter exploits from the other side, and why round 8 could not loosen it. Any
     sizing rule that shrinks size on wide-range days will destroy this strategy.

    python tools/orb_realism.py [fill|boot|size|all]
"""
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from tools.orb_hunt import strat, LB_END                              # noqa: E402
from tools.orb_hunt3 import robustness                                # noqa: E402
from tools.orb_pick import bars, BASE, COST, MULT                     # noqa: E402

CROWN = dict(BASE, atr_filter=0.75, vpace_filter=0.8, stop_frac=2.5, target_R=5.0, be_after_R=0.5)
OLD = dict(BASE)   # #234
FIVE_Y = "2021-08-13"


def run(params, strategy="ORB_3_6_FILL.py"):
    b = bars()
    r = strat(strategy).run_backtest(b["open"], b["high"], b["low"], b["close"],
                                     volumes=b["volume"], day_id=b["day_id"],
                                     return_trades=True, **params)
    idx = b["index"]; le = pd.Timestamp(LB_END, tz=idx.tz)
    return [t for t in (r or {}).get("trades") or [] if idx[t[0]] <= le]


def dollars(tr, size=None):
    p = np.array([(t[2] - COST) * MULT for t in tr], float)
    return p if size is None else p * np.asarray(size, float)


def stats(p, dts, start=None):
    if len(p) < 20:
        return None
    if start is not None:
        keep = np.array([d >= pd.Timestamp(start) for d in dts])
        p, dts = p[keep], [d for d, k in zip(dts, keep) if k]
    if len(p) < 20:
        return None
    yrs = (dts[-1] - dts[0]).days / 365.25
    cum = np.cumsum(p); dd = abs(float((cum - np.maximum.accumulate(cum)).min()))
    W, L = p[p > 0], p[p < 0]
    return dict(n=len(p), net=p.sum(), dd=dd, pf=W.sum() / abs(L.sum()) if len(L) else np.inf,
                mar=(p.sum() / yrs) / dd if dd else np.nan, wr=100 * len(W) / len(p),
                worst=robustness(dts, list(p))["worst"])


def entry_dates(tr):
    idx = bars()["index"]
    return [idx[t[0]].tz_localize(None) for t in tr]


def line(label, s):
    print("  %-34s n=%5d net=%10s DD=%9s PF=%.3f MAR=%.2f WR=%.1f worst12=%9s"
          % (label, s["n"], f"{s['net']:,.0f}", f"{s['dd']:,.0f}", s["pf"], s["mar"], s["wr"], f"{s['worst']:,.0f}"))


# ── A. realistic fill ────────────────────────────────────────────────────────────
def test_fill():
    print("\n" + "=" * 110)
    print("A. REALISTIC ENTRY FILL - close of the confirming bar vs open of the NEXT bar")
    print("=" * 110)
    b = bars(); O = b["open"]; C = b["close"]
    out = {}
    for name, P in (("#314 crown", CROWN), ("#234 old crown", OLD)):
        for mode in (False, True):
            tr = run(dict(P, fill_next_open=mode))
            dts = entry_dates(tr); p = dollars(tr)
            out[(name, mode)] = (tr, dts, p)
            for wl, ws in (("FULL", None), ("last 5y", FIVE_Y)):
                s = stats(p, dts, ws)
                if s:
                    line("%s | %s | %s" % (name, "NEXT-OPEN fill" if mode else "close fill", wl), s)
        # the slippage the close-fill assumption hides: next open minus confirming close, signed by side
        tr0 = out[(name, False)][0]
        slip = []
        for t in tr0:
            eb = t[0]
            if eb + 1 < len(O):
                slip.append((O[eb + 1] - C[eb]) * (1 if t[3] > 0 else -1))
        slip = np.array(slip)
        print("  %-34s adverse gap close->next open: mean %+.2f pts ($%+.0f/trade), median %+.2f, "
              "p90 %+.2f, worst %+.1f pts" % (name + " slippage", slip.mean(), slip.mean() * MULT,
                                               np.median(slip), np.percentile(slip, 90), slip.max()))
        print()
    return out


# ── B. bootstrap the risk advantage ──────────────────────────────────────────────
def test_boot(nboot=2000, block=20, seed=7, start=None):
    print("\n" + "=" * 110)
    print("B. IS #314's RISK ADVANTAGE REAL? stationary block bootstrap, %d resamples, %d-trade blocks" % (nboot, block))
    print("=" * 110)
    rng = np.random.default_rng(seed)
    seqs = {}
    for name, P in (("#314", CROWN), ("#234", OLD)):
        tr = run(P); p, d = dollars(tr), entry_dates(tr)
        if start is not None:
            keep = np.array([x >= pd.Timestamp(start) for x in d], bool)
            p, d = p[keep], [x for x, k in zip(d, keep) if k]
        seqs[name] = (p, d)
    print("  window: %s" % ("FULL 16.2y" if start is None else "from %s" % start))
    yrs = (seqs["#314"][1][-1] - seqs["#314"][1][0]).days / 365.25

    def resample(p):
        n = len(p); out = np.empty(n); i = 0
        while i < n:
            s = rng.integers(0, n); L = rng.geometric(1.0 / block)
            for j in range(L):
                if i >= n: break
                out[i] = p[(s + j) % n]; i += 1
        return out

    def mar_dd(p):
        cum = np.cumsum(p); dd = abs(float((cum - np.maximum.accumulate(cum)).min()))
        return (p.sum() / yrs) / dd if dd else np.nan, dd

    m314, m234, d314, d234 = [], [], [], []
    for _ in range(nboot):
        a, da = mar_dd(resample(seqs["#314"][0])); b_, db = mar_dd(resample(seqs["#234"][0]))
        m314.append(a); m234.append(b_); d314.append(da); d234.append(db)
    m314, m234, d314, d234 = map(np.array, (m314, m234, d314, d234))
    print("  point estimate      : MAR #314 %.2f vs #234 %.2f | DD $%s vs $%s"
          % (mar_dd(seqs["#314"][0])[0], mar_dd(seqs["#234"][0])[0],
             f"{mar_dd(seqs['#314'][0])[1]:,.0f}", f"{mar_dd(seqs['#234'][0])[1]:,.0f}"))
    print("  bootstrap MAR       : #314 median %.2f [5%%-95%%: %.2f-%.2f] | #234 median %.2f [%.2f-%.2f]"
          % (np.median(m314), np.percentile(m314, 5), np.percentile(m314, 95),
             np.median(m234), np.percentile(m234, 5), np.percentile(m234, 95)))
    print("  bootstrap max DD    : #314 median $%s [%s-%s] | #234 median $%s [%s-%s]"
          % (f"{np.median(d314):,.0f}", f"{np.percentile(d314,5):,.0f}", f"{np.percentile(d314,95):,.0f}",
             f"{np.median(d234):,.0f}", f"{np.percentile(d234,5):,.0f}", f"{np.percentile(d234,95):,.0f}"))
    print("  P(MAR #314 > #234)  : %.1f%%   (paired by resample index)" % (100 * np.mean(m314 > m234)))
    print("  P(DD  #314 < #234)  : %.1f%%" % (100 * np.mean(d314 < d234)))
    gap = d234 - d314
    print("  DD gap #234-#314    : median $%s, 90%% interval [$%s, $%s]"
          % (f"{np.median(gap):,.0f}", f"{np.percentile(gap,5):,.0f}", f"{np.percentile(gap,95):,.0f}"))
    print("  READ: the two paths are NOT independent (same entries, different exits), so treat the")
    print("        paired probabilities as an upper bound on certainty, not a p-value.")


# ── C. constant-risk sizing in micros ────────────────────────────────────────────
def test_size():
    print("\n" + "=" * 110)
    print("C. CONSTANT-RISK SIZING (micros) on #314 - same AVERAGE size as fixed 10 MNQ (= 1 NQ)")
    print("=" * 110)
    b = bars(); H, L, day = b["high"], b["low"], b["day_id"]
    tr = run(CROWN); dts = entry_dates(tr)
    # stop distance per trade = stop_frac x the opening range of that session (first 2 bars)
    risk_pts = []
    for t in tr:
        eb = t[0]; s = eb
        while s > 0 and day[s - 1] == day[eb]:
            s -= 1
        rng = max(H[s], H[s + 1]) - min(L[s], L[s + 1])
        risk_pts.append(CROWN["stop_frac"] * rng)
    risk_pts = np.array(risk_pts)
    p1 = dollars(tr)                                         # 1 NQ = 10 micros
    print("  stop distance (pts): median %.1f, p10 %.1f, p90 %.1f -> $ risk at 1 NQ: median $%s, p90 $%s"
          % (np.median(risk_pts), np.percentile(risk_pts, 10), np.percentile(risk_pts, 90),
             f"{np.median(risk_pts)*MULT:,.0f}", f"{np.percentile(risk_pts,90)*MULT:,.0f}"))
    line("FIXED 10 micros (= the crown)", stats(p1, dts))
    line("   ... last 5y", stats(p1, dts, FIVE_Y))
    for cap in (20, 30, 50):
        # micros so every trade risks the same $; then rescale so the AVERAGE size is 10 micros
        raw = 1.0 / (risk_pts * 2.0)                          # micros per $1 of risk
        size = np.clip(raw / raw.mean() * 10.0, 1, cap)
        size = np.round(size)
        size = size / size.mean() * 10.0                      # exact same average exposure
        p = p1 * (size / 10.0)
        line("CONSTANT-RISK, cap %d micros" % cap, stats(p, dts))
        line("   ... last 5y", stats(p, dts, FIVE_Y))
        print("     sizes: min %.0f, median %.0f, max %.0f micros" % (size.min(), np.median(size), size.max()))
    print("  READ: a MAR gain here with the same average size is a real shape improvement; a gain that")
    print("        needs the cap raised is just leverage on narrow-range days.")


if __name__ == "__main__":
    what = sys.argv[1] if len(sys.argv) > 1 else "all"
    if what in ("fill", "all"): test_fill()
    if what in ("boot", "all"):
        test_boot()
        test_boot(start=FIVE_Y)
    if what in ("size", "all"): test_size()
