"""
ROUND 62 - size the ORB crown up on the morning after a mega-cap earnings report. PRE-REGISTERED. (2026-09-28)

OWNER ASK (via MANAGER, 2026-09-28): more ORB alpha. The house lesson from the event-size scan and KEEL
v12: when the tape is mined out, bring NEW INFORMATION, and the only sizing that has ever held up is a
simple FIXED rule on a calendar known in advance. The event-size scan covered ten MACRO calendars (FOMC,
CPI, NFP, minutes, quad witching, month/quarter turns, Fed blackout) - it never looked at company
earnings. This does, with one cell, a placebo and a family-wide null, all written before any number.

THE MECHANISM. The seven largest NQ weights (AAPL, MSFT, NVDA, AMZN, GOOGL, META, TSLA) report outside
regular hours. The next 09:30 open must price a large, public information shock to a big slice of the
index at once, which is the textbook condition for a trend day - and ORB's whole edge is the trend day.
Report dates are published weeks ahead, so a size rule keyed on them is knowable before the session.

THE CALENDAR is frozen in tools/data/megacap_earnings_dates.csv (607 reports, Yahoo, 2002-2026, pulled
2026-09-28 before this file ran). A report's REACTION SESSION is the first RTH session that opens after
it: a report stamped before 09:30 ET reacts the same day, anything later reacts the next session.

THE RULE (one cell, nothing searched): every #314 crown trade ENTERED in a reaction session is sized
1.5x - the house tilt size used by every fixed tilt on the paper board. All other trades 1x.

HOW IT COULD BE FOOLING US, written down first:
  (a) Survivorship: NVDA, TSLA and META were not top NQ weights in the early 2010s. Robustness read on
      the four names that were top weights throughout (AAPL, MSFT, AMZN, GOOGL). Reported, not a gate.
  (b) Any 1.5x on ~15% of sessions adds size; the yardstick (ROC at a $30k drawdown) removes leverage,
      and a family-wide null asks whether ANY calendar of the same size does as well.
  (c) The placebo - the session BEFORE each reaction session, sized 1.5x - must NOT also pass.

WINDOW. Pre-lockbox only, 2010-06-07 to 2025-08-12, NQ 5m RTH raw master (ORB is roll-immune intraday).
Halves EARLY 2010-06-07..2017-12-31 and LATE 2018-01-01..2025-08-12, plus the crown's walk-forward
stretch 2016-07-13..2025-08-12. The crown's lockbox (from 2025-08-13) is not read.

PRE-REGISTERED BAR to go to an Auto-Validate-grade test (a tilted paper/book leg is an owner call):
  1. Beats the #314 raw twin on ROC %/yr at a $30k worst drawdown in BOTH halves AND the WF stretch.
  2. Beats the raw twin on daily Sortino in both halves.
  3. At least 100 tilted trades.
  4. The gain over the raw twin survives removing the single biggest tilted trade.
  5. FAMILY-WIDE NULL: its WF-stretch ROC gain ranks at or above the 95th percentile of 2,000 random
     calendars drawn from the crown's own trading sessions with the same count per year.
  6. The placebo calendar does not also clear bar 1.
If any of 1-6 fails, round 62 is DEAD.
"""
import os
import sys

ROOT = r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
os.environ.setdefault("AUGUR_TRIAL_CACHE", "1")

FN = "augur_strategies/ORB_3_6.py"
COST, MULT, TILT = 0.533, 20.0, 1.5
WIN = dict(date_from="2010-06-07", date_to="2025-08-12")
HALVES = {"EARLY 2010-2017": ("2010-06-07", "2017-12-31"), "LATE 2018-2025/08": ("2018-01-01", "2025-08-12"),
          "WF STRETCH 2016-07..2025-08": ("2016-07-13", "2025-08-12")}
CROWN = dict(or_bars=2, trade_mode="First-candle dir", close_confirm=True, partial_exit_R=0.0, trail_bars=0,
             flat_eod=True, skip_holidays=True, breakout_buf=0.25, stop_frac=2.5, target_R=5.0,
             be_after_R=0.5, atr_filter=0.75, vpace_filter=0.8)
NULL_DRAWS, SEED = 2000, 62


def main():
    import numpy as np
    import pandas as pd
    from augur_engine.engine import run_backtest
    from augur_engine.data import find_master, load_master_arrays

    A = load_master_arrays(find_master("NQ", "5m", "rth", "db_noadj_rth"), **WIN)
    idx = pd.DatetimeIndex(A["index"])
    r = run_backtest(FN, arrays=A, params=dict(CROWN), cost_pts=COST, return_trades=True)
    T = pd.DataFrame({"entry": [idx[t[0]] for t in r["trades"]], "exit": [idx[t[1]] for t in r["trades"]],
                      "pnl": [t[2] * MULT for t in r["trades"]]})
    T["sess"] = T.entry.dt.tz_localize(None).dt.normalize()
    T["exit_day"] = T.exit.dt.tz_localize(None).dt.normalize()
    sessions = pd.DatetimeIndex(sorted(set(idx.tz_localize(None).normalize())))
    print("crown: %d trades, $%.0f over %d sessions" % (len(T), T.pnl.sum(), len(sessions)), flush=True)

    E = pd.read_csv(os.path.join(HERE, "data", "megacap_earnings_dates.csv"))
    E["ts"] = pd.to_datetime(E.report_et)

    def reaction(ts):
        d = ts.normalize()
        if ts.hour * 60 + ts.minute >= 9 * 60 + 30:
            d = d + pd.Timedelta(days=1)
        k = sessions.searchsorted(d)
        return sessions[k] if k < len(sessions) else pd.NaT

    E["react"] = E.ts.map(reaction)
    cal_all = set(E.react.dropna())
    cal_top4 = set(E[E.ticker.isin(["AAPL", "MSFT", "AMZN", "GOOGL"])].react.dropna())
    placebo = set(sessions[max(sessions.searchsorted(d) - 1, 0)] for d in cal_all)

    def daily(w):
        s = pd.Series((T.pnl * w).values, index=T.exit_day.values)
        return s.groupby(level=0).sum().sort_index()

    def score(d, lo, hi):
        z = d[(d.index >= pd.Timestamp(lo)) & (d.index <= pd.Timestamp(hi))]
        cum = z.cumsum()
        dd = float((cum.cummax().clip(lower=0) - cum).max())
        yrs = (pd.Timestamp(hi) - pd.Timestamp(lo)).days / 365.25
        neg = z[z < 0]
        return 30.0 * (z.sum() / yrs) / dd, z.mean() / np.sqrt((neg ** 2).sum() / len(z)) * np.sqrt(252), z.sum(), dd

    base = {nm: score(daily(np.ones(len(T))), lo, hi) for nm, (lo, hi) in HALVES.items()}
    print("\nRAW TWIN #314:")
    for nm, sc in base.items():
        print("  %-28s ROC@$30k %6.1f%%/yr  Sortino %5.2f  net $%9.0f  DD $%7.0f" % ((nm,) + sc))

    def evaluate(cal):
        w = np.where(T.sess.isin(cal), TILT, 1.0)
        d = daily(w)
        return w, {nm: score(d, lo, hi) for nm, (lo, hi) in HALVES.items()}

    wf = "WF STRETCH 2016-07..2025-08"
    results = {}
    for name, cal in (("EARNINGS, all 7 names", cal_all), ("EARNINGS, top-4 throughout", cal_top4),
                      ("PLACEBO, session before", placebo)):
        w, sc = evaluate(cal)
        tilted = T[w > 1]
        extra = tilted.pnl * (TILT - 1)
        results[name] = (w, sc, tilted, extra)
        print("\n%s: %d calendar sessions in window, %d tilted trades, extra money $%+.0f, "
              "without the biggest tilted trade $%+.0f"
              % (name, sum(1 for d in cal if sessions[0] <= d <= sessions[-1]), len(tilted), extra.sum(),
                 extra.sum() - extra.max()))
        for nm in HALVES:
            print("  %-28s ROC@$30k %6.1f%%/yr (%s)  Sortino %5.2f (%s)  net $%9.0f  DD $%7.0f"
                  % (nm, sc[nm][0], "beats" if sc[nm][0] > base[nm][0] else "LOSES",
                     sc[nm][1], "beats" if sc[nm][1] > base[nm][1] else "LOSES", sc[nm][2], sc[nm][3]))

    # family-wide null: random calendars, same count per year, drawn from the crown's own sessions
    rng = np.random.default_rng(SEED)
    real = [d for d in cal_all if sessions[0] <= d <= sessions[-1]]
    per_year = pd.Series([d.year for d in real]).value_counts()
    by_year = {y: sessions[sessions.year == y] for y in per_year.index}
    real_gain = results["EARNINGS, all 7 names"][1][wf][0] - base[wf][0]
    null = []
    for _ in range(NULL_DRAWS):
        cal = set()
        for y, n in per_year.items():
            cal.update(rng.choice(by_year[y], size=min(n, len(by_year[y])), replace=False))
        null.append(evaluate(cal)[1][wf][0] - base[wf][0])
    null = np.array(null)
    pct = (null < real_gain).mean()
    print("\nFAMILY-WIDE NULL (%d random calendars): real WF-stretch ROC gain %+.2f pts sits at the %.1fth "
          "percentile (null median %+.2f, 95th %+.2f)" % (NULL_DRAWS, real_gain, 100 * pct,
                                                          np.median(null), np.percentile(null, 95)))

    w, sc, tilted, extra = results["EARNINGS, all 7 names"]
    psc = results["PLACEBO, session before"][1]
    bars = {
        "1 beats ROC@$30k in both halves + WF": all(sc[nm][0] > base[nm][0] for nm in HALVES),
        "2 beats Sortino in both halves": all(sc[nm][1] > base[nm][1] for nm in list(HALVES)[:2]),
        "3 >=100 tilted trades": len(tilted) >= 100,
        "4 survives its biggest tilted trade": extra.sum() - extra.max() > 0,
        "5 null percentile >= 95th": pct >= 0.95,
        "6 placebo does NOT clear bar 1": not all(psc[nm][0] > base[nm][0] for nm in HALVES),
    }
    print("\nPRE-REGISTERED BAR:")
    for k, v in bars.items():
        print("  %-40s %s" % (k, "PASS" if v else "FAIL"))
    print("VERDICT: %s" % ("CLEARS - candidate for a forward/validate test (owner call)" if all(bars.values())
                           else "DEAD"))


if __name__ == "__main__":
    main()
