"""
CONCENTRATION CHECK — run this BEFORE queueing anything, not after it passes.

Why it exists (2026-09-08): an ENGU-Q 24h configuration found by an R / YR-objective
search scored the library-record EV R 1.40, held 26 of 26 one-step neighbours in a
plateau check, and then PASSED its Auto-Validate on all six gates (run #320). It makes
101% of its net from TEN trades in fifteen years; strip them and the other 823 trades
lose money at PF 0.98. Neither a plateau check nor a walk-forward nor a lockbox detects
that - they answer different questions:
    plateau      -> do NEIGHBOURING settings agree?
    walk-forward -> does it hold on data it was not tuned on?
    concentration-> is the profit spread across trades, or is it a handful of tails?
EV R is especially prone to it: dividing by the average LOSING trade rewards exactly the
few-enormous-winners shape, so a wide trail on a 24-hour tape can score 1.4 while being
untradeable.

Usage:
    python tools/concentration_check.py <strategy.py> <inst> <tf> <sess> <src> <cost> <mult> [params_json]
    (params_json omitted or {} = the file's real DEFAULT_PARAMS defaults, which for a fenced
     neighbourhood file reproduces its plateau centre -- see THE {} TRAP below)

Reports, on the pre-lockbox window: full stats, the top-10 share of net, and the stats
with the ten biggest winners removed. Net / PF / win% / EV R are order-independent so they
stay meaningful after the removal; DRAWDOWN IS NOT and is deliberately not printed for the
ex-top-10 series.

Bar used by this project: top-10 share >= 90% = ARTIFACT, do not queue. 50-90% = state it
loudly on the card. Below 50% with a positive ex-top-10 net = a normally-distributed edge.
Reference points measured: deployed ENGU-Q leg 80%, NOISE crowns 22-42%.

THE {} TRAP -- FIXED HERE 2026-09-09
-------------------------------------
Until today this tool passed the caller's params dict STRAIGHT to run_backtest, so any key the
caller left out fell through to the strategy plugin's own run_backtest() KEYWORD defaults --
which in this codebase are routinely the file's INHERITED PARENT defaults, kept as a parity
anchor, and a completely different configuration from the file's DEFAULT_PARAMS (what the web
Builder pre-fills and what the owner means by "the current default"). queue_guard.py hit and
fixed exactly this on 2026-09-08; this file had the same hole and its usage line above even
promised the opposite. Caught 2026-09-09 grading ENGUQ_1M_ETH_R3_1_0.py: `{}` silently ran
the inherited anchor (2,655 trades / $324,648 / top-10 79%) instead of the file's real
defaults, and would have condemned a config it never actually ran. It now resolves through
queue_guard.resolve_params() -- DEFAULT_PARAMS[k]['default'] for every key the caller omits,
the caller's own params overlaid on top -- exactly like a real queued job, and prints the
resolved dict so a mismatch is visible before the verdict is trusted.

THE TAIL / BETA BLOCK -- ADDED 2026-09-09 (the owner's challenge)
-----------------------------------------------------------------
Owner, on the ENGU-Q crown: "interesting how it beat on important metrics like EV R, R/YR
etc, but those are only bc of the fat tail. i tells me its only working bc qqq, what it was
trading, was going up the last 10 years. take those tail trades out and you have a problem?
asses. would need to make sure that concentration rule gets adheaerd too."

The audit agreed with him. Top-10 share ALONE does not settle it, because a fat tail can be a
real edge OR it can be long exposure to a rising index wearing a strategy costume. What
separates the two is WHEN the tail lands. So every run of this tool now also prints, off the
same single backtest it already ran, four reads aimed straight at that question:

  * yearly net beside the instrument's OWN yearly return (its close-to-close change), so a
    config that only earns in up years is visible on sight;
  * the correlation of those two yearly series -- near +1 means the "edge" is the market;
  * the benchmark's DOWN years called out separately, because that is where a long-only proxy
    bleeds and a real edge should not;
  * positive years with, and without, each year's three biggest trades -- plus the longest
    single hold in calendar days, since on a 24-hour tape a months-long hold IS beta.

These reads are REPORTED ALWAYS and ENFORCED ONLY WITH --enforce. That split is deliberate,
and it is the same reasoning queue_guard.py's header gives: this program's own deployed legs
are fat-tailed and working, so a bar that failed them by default would be wrong. Use
--enforce when the owner has asked for a config that must NOT depend on the index rising (the
ENGU-Q R3 hold-cap line of work). That bar: top-10 share < 60%, non-negative in EVERY
benchmark down year, and yearly correlation < 0.40. A breach exits 1 with the reason named.

MEASURED REFERENCE POINTS -- all four printed by THIS tool on ITS window (ENGU-Q ETH, NQ 1m,
2010-06-07..2025-06-29), 2026-09-09, so they are directly comparable to anything you run:
    run #335's own search champion  top-10 82%  corr +0.77  2018+2022 -$54,250  FAIL (all 3)
    #309, the previous crown        top-10 53%  corr +0.59  2018+2022  +$8,905  FAIL (2022, corr)
    R2 defaults, the live crown     top-10 51%  corr +0.51  2018+2022 +$19,732  FAIL (corr)
    R3, that same crown + hold cap  top-10 44%  corr +0.39  2018+2022 +$20,491  PASS
The R3 line is the point of the whole exercise: one added knob (cap the hold at 8,280 bars)
moves a family that fails every read to one that passes all three, and the only thing it is
paying for that is headline profit. Longest hold falls 142 days -> 13, which is the mechanism.
"""
import os, sys, json
import numpy as np
import pandas as pd
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT); os.chdir(ROOT)
from augur_engine.engine import run_backtest
from augur_engine.data import find_master, load_master_arrays
from tools.queue_guard import resolve_params

WIN = dict(date_from="2010-06-07", date_to="2025-06-29")


def stats(pnls):
    p = np.asarray(pnls, float)
    if len(p) == 0:
        return None
    gw = p[p > 0].sum(); gl = -p[p < 0].sum()
    pf = gw / gl if gl > 0 else float("inf")
    w = float((p > 0).mean())
    return dict(n=len(p), net=float(p.sum()), pf=float(pf), win=100 * w, evr=(1 - w) * (pf - 1))


def beta_block(trades, mult, arrays):
    """Print the tail / beta reads; return (correlation, benchmark down years, yearly net).

    `trades` are the engine's raw tuples (entry_bar, exit_bar, pnl_points, ...), so the bar
    indices are mapped back onto the master `index` to recover real entry / exit timestamps.
    The benchmark is the instrument itself -- its own close-to-close change per calendar
    year -- which is the only honest yardstick for "was this just the market going up".
    """
    idx = pd.DatetimeIndex(pd.to_datetime(pd.Series(arrays["index"])))
    try:
        idx = idx.tz_localize(None)
    except (TypeError, AttributeError):
        pass
    ent = pd.DatetimeIndex([idx[int(t[0])] for t in trades])
    ext = pd.DatetimeIndex([idx[int(t[1])] for t in trades])
    pnl = pd.Series([t[2] * mult for t in trades], index=ent)

    px = pd.Series(np.asarray(arrays["close"], float), index=idx)
    last = px.resample("YE").last()
    bench = ((last / last.shift(1) - 1.0) * 100).dropna()
    bench.index = bench.index.year

    yr = pnl.groupby(pnl.index.year).sum()
    ex3 = pnl.groupby(pnl.index.year).apply(
        lambda x: float(x.sum() - np.sort(x.values)[::-1][:3].sum()))
    common = yr.index.intersection(bench.index)
    corr = float(yr[common].corr(bench[common])) if len(common) > 2 else float("nan")
    down = [int(y) for y in common if bench[y] < 0]
    hold = max((ext[i] - ent[i]).days for i in range(len(ent)))

    print("\n  TAIL / BETA -- is this the strategy, or is it the instrument going up?")
    print("  %6s %8s %12s %12s %7s" % ("year", "bench %", "net $", "ex-top3 $", "trades"))
    for y in yr.index:
        b = float(bench.get(y, float("nan")))
        mark = "  <- bench DOWN" if y in down else ""
        print("  %6d %8.1f %12s %12s %7d%s"
              % (y, b, format(yr[y], ",.0f"), format(ex3[y], ",.0f"),
                 int((pnl.index.year == y).sum()), mark))
    print("  positive years %d/%d   ex-top-3 positive years %d/%d   longest hold %d days"
          % (int((yr > 0).sum()), len(yr), int((ex3 > 0).sum()), len(ex3), hold))
    print("  correlation of yearly net with the instrument's yearly return: %+.3f"
          "   (near +1 = the market, not an edge)" % corr)
    if down:
        neg = [y for y in down if float(yr.get(y, 0.0)) < 0]
        print("  benchmark DOWN years %s: net $%s%s"
              % (down, format(float(yr[down].sum()), ",.0f"),
                 ("   LOSES money in %s" % neg) if neg else "   positive in every one"))
    else:
        print("  this window holds no down year for the instrument -- the down-year read "
              "cannot be made, which is itself a caveat on any beta claim here.")
    return corr, down, yr


def main():
    argv = [a for a in sys.argv[1:] if not a.startswith("--")]
    enforce = "--enforce" in sys.argv
    fn, inst, tf, sess, src, cost, mult = argv[:7]
    params = json.loads(argv[7]) if len(argv) > 7 else {}
    params, _src, _has_dp = resolve_params(fn, params)
    if not _has_dp:
        print("  NOTE: %s has no DEFAULT_PARAMS to resolve against -- unsupplied keys fall "
              "through to the plugin's signature defaults, which may be an inherited parity "
              "anchor rather than this file's configuration." % fn)
    A = load_master_arrays(find_master(inst, tf, sess, src), **WIN)
    r = run_backtest(fn, arrays=A, params=params, cost_pts=float(cost), return_trades=True)
    if not r or not r.get("trades"):
        print("no trades"); sys.exit(2)
    M = float(mult)
    pnls = [t[2] * M for t in r["trades"]]
    cum = np.cumsum([p for p in pnls]); dd = float((cum - np.maximum.accumulate(cum)).min())
    full = stats(pnls)
    srt = sorted(pnls, reverse=True)
    top10 = sum(srt[:10])
    ex = stats(srt[10:])
    share = 100 * top10 / full["net"] if full["net"] else float("inf")
    print(f"\n{fn}  {inst} {tf} {sess}  window {WIN['date_from']}..{WIN['date_to']}")
    print("  params run: " + json.dumps(params, sort_keys=True))
    print(f"  FULL         n={full['n']:5} net=${full['net']:>11,.0f} PF={full['pf']:6.3f} win={full['win']:5.1f}% "
          f"EV R={full['evr']:6.3f} DD=${-dd:>10,.0f}")
    print(f"  top-10 winners = ${top10:,.0f}  =  {share:.0f}% of net")
    print(f"  EX-TOP-10    n={ex['n']:5} net=${ex['net']:>11,.0f} PF={ex['pf']:6.3f} win={ex['win']:5.1f}% "
          f"EV R={ex['evr']:6.3f}   (drawdown not meaningful once trades are reordered)")
    artifact = share >= 90 or ex["net"] <= 0
    if artifact:
        print("\n  VERDICT: ARTIFACT — do NOT queue. The profit is the tail, not the strategy.")
    elif share >= 50:
        print("\n  VERDICT: CONCENTRATED — queueable, but say the top-10 share out loud on the card.")
    else:
        print("\n  VERDICT: SPREAD — profit is distributed across the trade list.")

    corr, down, yr = beta_block(r["trades"], M, A)
    if artifact:
        sys.exit(1)
    if not enforce:
        print("\n  (the tail / beta reads above are REPORTED only — pass --enforce to make "
              "them a bar)")
        sys.exit(0)

    fails = []
    if share >= 60:
        fails.append("top-10 share %.0f%% >= 60%%" % share)
    bad = [y for y in down if float(yr.get(y, 0.0)) < 0]
    if bad:
        fails.append("loses money in benchmark down year(s) %s" % bad)
    if corr == corr and corr >= 0.40:
        fails.append("yearly correlation with the instrument %+.2f >= 0.40" % corr)
    if fails:
        print("\n  ENFORCED BAR: FAIL — " + "; ".join(fails))
        sys.exit(1)
    print("\n  ENFORCED BAR: PASS — spread enough, and it does not need the index to rise.")


if __name__ == "__main__":
    main()
