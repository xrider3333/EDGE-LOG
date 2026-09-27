"""
ROUND 60 - the evidence for the ORB crown call, pre-registered. (2026-09-27)

THE OWNER CALL THIS SERVES. The ORB crown is #314 (smoothest ride, owner-crowned 2026-09-05). Run
#257 (owner-starred) earns the most money: +$26,507 over #234 by calendar year, most walk-forward
money, and its region held up under run #421's re-fitted walk-forward. The owner will choose between
them after MANAGER's ROC/yr assessment. Two things that choice needs are not measured yet, and
neither needs an owner decision to measure. This file measures them and nothing else.

WRITTEN AND PUSHED BEFORE ANY NUMBER BELOW EXISTED. The reads are fixed here; the run fills them in.

TEST A - IS #257's MONEY LEAD REAL, OR A FEW LUCKY YEARS?  (paired calendar-year block bootstrap)
  Configs, frozen, one contract, NQ 5m RTH no-adjust, 0.533 pts per round turn, window pinned to the
  certified one: 2010-06-07 to 2026-08-13. #257, #314, #234, #239.
  Method: every config's P&L is cut into calendar years. 20,000 draws resample the SAME years for
  every config (paired), 17 years per draw with replacement, and the whole resampled history is
  scored: total money, and maximum drawdown on the day-by-day path of the resampled years in order.
  Reported: P(#257 earns more than X) and P(#257's drawdown is deeper than X) for X = #314, #234,
  #239; the same on the recent regime alone (2018-2026 blocks), because the ORB edge is improving and
  the recent years are the representative ones.
  PRE-REGISTERED READS:
    - "#257 earns more than X" is CALLED REAL only if P >= 0.80 on BOTH the whole window and 2018+.
      Between 0.50 and 0.80 it is a COIN FLIP and is reported as one. Below 0.50 it is reversed.
    - "#257's drawdown is deeper than X" is CALLED REAL on the same 0.80 bar.
    - Neither outcome crowns anything. The crown is the owner's call; this prices it.

TEST B - WHAT DID THE ONLY UNSEEN DATA SAY?  (fresh six weeks, roll-corrected)
  Every validate in this family ends 2026-08-13. The data now runs to 2026-09-25, so the weeks since
  are the only stretch no ORB configuration was chosen on. It includes the 2026-09-14 in-bar contract
  splice that pushed two losing trades through the volatility filter on paper (ROLL_AUDIT 4.5.4), so
  it is read on the ROLL-CORRECTED master (db_adj_rth), with history loaded from 2025-06-01 so both
  filters are warm, and only trades entered on or after 2026-08-14 counted. The raw master is printed
  beside it so the splice's effect is visible.
  Configs: #257, #314, #234, #239 and run #421's crowned cell (stop 2.75, breakeven 0.4, target 6).
  PRE-REGISTERED READ: REPORT ONLY. Six weeks is roughly 25-30 trades per config; no difference that
  size can separate these configs, and nothing is moved on it. It is printed so the forward paper
  record has a matching backtest to be checked against, trade for trade.

Uses the engine (augur_engine.engine.run_backtest) on the strategy parent ORB_3_6.py - the same
arms every card file forwards to - so the figures match the runs by construction; the parity line
checks #257 against its stored run to the cent before anything else is printed.
"""
import os
import sys

ROOT = r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"
sys.path.insert(0, ROOT)
os.chdir(ROOT)
os.environ.setdefault("AUGUR_TRIAL_CACHE", "1")

FN = "augur_strategies/ORB_3_6.py"
COST, MULT = 0.533, 20.0
WIN = dict(date_from="2010-06-07", date_to="2026-08-13")
FRESH_FROM = "2026-08-14"
DRAWS = 20000
SEED = 60

BASE = dict(or_bars=2, trade_mode="First-candle dir", close_confirm=True, partial_exit_R=0.0,
            trail_bars=0, flat_eod=True, skip_holidays=True, breakout_buf=0.25,
            stop_frac=2.0, target_R=5.5, be_after_R=1.0, atr_filter=0.7, vpace_filter=0.7)
CONFIGS = {
    "#257": dict(BASE, stop_frac=2.5, breakout_buf=0.30, atr_filter=0.5),
    "#314": dict(BASE, stop_frac=2.5, target_R=5.0, be_after_R=0.5, atr_filter=0.75, vpace_filter=0.8),
    "#234": dict(BASE),
    "#239": dict(BASE, be_after_R=0.8),
}
CELL_421 = dict(BASE, stop_frac=2.75, target_R=6.0, be_after_R=0.4, atr_filter=0.5)


def main():
    import numpy as np
    import pandas as pd
    from augur_engine.engine import run_backtest
    from augur_engine.data import find_master, load_master_arrays

    def daily(arrays, params, since=None):
        idx = pd.DatetimeIndex(arrays["index"])
        r = run_backtest(FN, arrays=arrays, params=params, cost_pts=COST, return_trades=True)
        s = pd.Series([t[2] * MULT for t in r["trades"]],
                      index=[idx[t[1]].tz_localize(None) for t in r["trades"]]).sort_index()
        if since is not None:
            s = s[s.index >= pd.Timestamp(since)]
        return s

    # ---------------- TEST A ----------------
    A = load_master_arrays(find_master("NQ", "5m", "rth", "db_noadj_rth"), **WIN)
    trades = {k: daily(A, p) for k, p in CONFIGS.items()}
    t257 = trades["#257"]
    ok = len(t257) == 2751 and abs(t257.sum() - 416381.84) < 0.01
    print("PARITY #257 vs its stored run (2,751 trades, $416,381.84): %d trades, $%.2f -> %s"
          % (len(t257), t257.sum(), "EXACT" if ok else "MISMATCH - stop"), flush=True)
    if not ok:
        sys.exit(2)

    days = {k: s.groupby(s.index.normalize()).sum() for k, s in trades.items()}
    years = sorted(set(y for s in days.values() for y in s.index.year))
    # per config, per year: the ordered daily P&L of that year
    blocks = {k: {y: s[s.index.year == y].values for y in years} for k, s in days.items()}

    def score(ys, k):
        path = np.concatenate([blocks[k][y] for y in ys]) if ys else np.zeros(1)
        cum = np.cumsum(path)
        return path.sum(), float((np.maximum.accumulate(np.concatenate([[0.0], cum]))[1:] - cum).max())

    rng = np.random.default_rng(SEED)
    for label, pool in (("WHOLE WINDOW (2010-2026)", years), ("RECENT REGIME (2018-2026)", [y for y in years if y >= 2018])):
        n = len(pool)
        wins = {x: 0 for x in ("#314", "#234", "#239")}
        deeper = {x: 0 for x in ("#314", "#234", "#239")}
        for _ in range(DRAWS):
            ys = list(rng.choice(pool, size=n, replace=True))
            m257, d257 = score(ys, "#257")
            for x in wins:
                mx, dx = score(ys, x)
                wins[x] += m257 > mx
                deeper[x] += d257 > dx
        print("\nTEST A - %s, %d paired draws of %d calendar years" % (label, DRAWS, n))
        for x in wins:
            pw, pd_ = wins[x] / DRAWS, deeper[x] / DRAWS
            call = "REAL" if pw >= 0.80 else ("COIN FLIP" if pw >= 0.50 else "REVERSED")
            print("  #257 vs %s: P(more money) %.3f [%s] | P(deeper drawdown) %.3f [%s]"
                  % (x, pw, call, pd_, "REAL" if pd_ >= 0.80 else "not established"))
    for k, s in trades.items():
        c = s.cumsum()
        print("  actual %s: $%.0f, max drawdown $%.0f, %d trades" % (k, s.sum(), (c.cummax() - c).max(), len(s)))

    # ---------------- TEST B ----------------
    print("\nTEST B - trades entered %s to the end of the data, REPORT ONLY" % FRESH_FROM)
    cfgs = dict(CONFIGS, **{"#421 cell": CELL_421})
    for src in ("db_adj_rth", "db_noadj_rth"):
        B = load_master_arrays(find_master("NQ", "5m", "rth", src), date_from="2025-06-01", date_to=None)
        last = pd.DatetimeIndex(B["index"]).max()
        print("  master %s (roll-%s), data to %s" % (src, "corrected" if src == "db_adj_rth" else "RAW", last))
        for k, p in cfgs.items():
            s = daily(B, p, since=FRESH_FROM)
            print("    %-10s %2d trades  $%+9.2f  won %2d" % (k, len(s), s.sum(), int((s > 0).sum())))


if __name__ == "__main__":
    main()
