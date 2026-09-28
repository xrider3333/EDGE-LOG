"""
ROUND 61 - carry the ORB crown's trend-day winners past the close. PRE-REGISTERED. (2026-09-28)

OWNER ASK (via MANAGER, 2026-09-28): more alpha from the ORB family - a new MECHANISM, not a parameter
nudge; no crown re-optimising, no learned gates, nothing tagged at the fill bar; judged on the owner
yardstick (ROC %/yr at a $30k worst drawdown valued daily, beat the raw twin and its Sortino).

THE MECHANISM. ORB's whole edge is the trend day: the few sessions that run from the open and never come
back. The crown is flattened at 16:00 on every one of them, so it banks the trend day and then hands the
next morning's follow-through to someone else. Two facts from this stack say that follow-through may be
there to take: (1) intraday CONTINUATION beats reversion on NQ in every window measured (rounds 8/38, the
NQ-vs-ES spread and last-hour tests), and (2) a trade still open at the close with a large open profit is
by construction a trend day that has not reversed. The idea is an EXIT change only: the same entries,
the same stops and targets inside the session, and for trades that reach the close still open AND well
in profit, exit at the NEXT session's 09:30 open instead of at 16:00.

HOW IT COULD BE FOOLING US, written down first:
  (a) NQ has a positive overnight drift, so ANY long carried overnight earns a little. If the gain is
      drift, carrying LONG winners helps and carrying SHORT winners hurts. MECHANISM CHECK: the short
      side of the chosen cell must not lose money on the carry, or it is drift, not continuation.
  (b) A few huge gaps (2020, 2022) could carry the whole result. The gain must survive removing the
      single biggest carried gap.
  (c) Contract rolls: a carry across a quarterly switch books the roll jump as profit. The whole test
      runs on the ROLL-CORRECTED master (db_adj_rth), and the crown's intraday trades are checked for
      parity against the raw master first.
  (d) Weekend carries hold 66 hours. Reported separately; they stay in the result.
  (e) The 09:30 open auction slips. Every carried trade pays 0.25 points extra on top of the house cost.

VARIANTS (all on the #314 crown's frozen parameters, ORB_3_6_R6.py):
  C1  carry trades open at the close with open profit >= 1R      (R = the trade's stop distance)
  C2  carry trades open at the close with open profit >= 2R
  C0  carry EVERY trade still open at the close                  (control: is it just the overnight?)
  P1  carry only trades open at the close with open profit <  1R (placebo: the non-trend-day complement)

WINDOW. Pre-lockbox only, 2010-06-07 to 2025-08-12. The crown validate's lockbox starts 2025-08-13 and
is not read. Scored in two halves - EARLY 2010-06-07..2017-12-31 and LATE 2018-01-01..2025-08-12 - and on
the crown's walk-forward stretch 2016-07-13..2025-08-12.

PRE-REGISTERED BAR for a variant to go to an Auto-Validate (900 trials, fenced ranges, crown window):
  1. It beats the #314 raw twin on ROC %/yr at a $30k worst drawdown (= 30 x annual net / max daily
     drawdown) in BOTH halves AND on the walk-forward stretch.
  2. It beats the raw twin on daily Sortino in both halves.
  3. At least 100 carried trades over the window.
  4. Its gain over the raw twin stays positive with the single biggest carried gap removed.
  5. MECHANISM: its short-side carries do not lose money in total.
  C0 and P1 are controls: they are reported and cannot be promoted.
If no variant clears all five, round 61 is DEAD and nothing is queued.
"""
import os
import sys

ROOT = r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"
sys.path.insert(0, ROOT)
os.chdir(ROOT)
os.environ.setdefault("AUGUR_TRIAL_CACHE", "1")

FN = "augur_strategies/ORB_3_6.py"
COST, MULT, SLIP_OPEN = 0.533, 20.0, 0.25
WIN = dict(date_from="2010-06-07", date_to="2025-08-12")
HALVES = {"EARLY 2010-2017": ("2010-06-07", "2017-12-31"), "LATE 2018-2025/08": ("2018-01-01", "2025-08-12"),
          "WF STRETCH 2016-07..2025-08": ("2016-07-13", "2025-08-12")}
CROWN = dict(or_bars=2, trade_mode="First-candle dir", close_confirm=True, partial_exit_R=0.0, trail_bars=0,
             flat_eod=True, skip_holidays=True, breakout_buf=0.25, stop_frac=2.5, target_R=5.0,
             be_after_R=0.5, atr_filter=0.75, vpace_filter=0.8)
VARIANTS = {"C1 carry >=1R": ("ge", 1.0), "C2 carry >=2R": ("ge", 2.0),
            "C0 carry all (control)": ("all", None), "P1 carry <1R (placebo)": ("lt", 1.0)}


def main():
    import numpy as np
    import pandas as pd
    from augur_engine.engine import run_backtest
    from augur_engine.data import find_master, load_master_arrays

    def trades_on(src):
        A = load_master_arrays(find_master("NQ", "5m", "rth", src), **WIN)
        r = run_backtest(FN, arrays=A, params=dict(CROWN), cost_pts=COST, return_trades=True)
        return A, r["trades"]

    A_raw, t_raw = trades_on("db_noadj_rth")
    A, tr = trades_on("db_adj_rth")
    print("PARITY: crown on raw master %d trades $%.2f | on roll-corrected %d trades $%.2f"
          % (len(t_raw), sum(t[2] for t in t_raw) * MULT, len(tr), sum(t[2] for t in tr) * MULT), flush=True)

    idx = pd.DatetimeIndex(A["index"]).tz_localize(None)
    o, h, l, c = (np.asarray(A[k], float) for k in ("open", "high", "low", "close"))
    day = idx.normalize()
    starts = np.flatnonzero(np.r_[True, day[1:] != day[:-1]])
    ends = np.r_[starts[1:] - 1, len(idx) - 1]
    sess_of = np.searchsorted(starts, np.arange(len(idx)), side="right") - 1

    rows = []
    for (ei, xi, pnl_pts, side, entry) in tr:
        s = sess_of[ei]
        a, b = starts[s], ends[s]
        rng = h[a:a + 2].max() - l[a:a + 2].min()
        risk = CROWN["stop_frac"] * rng
        at_close = (c[b] - entry) * side
        eod = (xi == b) and abs((pnl_pts + COST) - at_close) < 1e-6
        nxt_open = o[starts[s + 1]] if s + 1 < len(starts) else np.nan
        gap = (nxt_open - c[b]) * side if eod else 0.0
        weekend = eod and s + 1 < len(starts) and (day[starts[s + 1]] - day[a]).days > 1
        rows.append(dict(t=idx[xi], side=side, base=pnl_pts * MULT, eod=eod,
                         open_R=(at_close / risk) if (eod and risk > 0) else np.nan,
                         gap=(gap - SLIP_OPEN) * MULT if eod else 0.0, weekend=weekend,
                         carry_day=day[starts[s + 1]] if (eod and s + 1 < len(starts)) else idx[xi].normalize()))
    T = pd.DataFrame(rows)
    print("crown trades %d, still open at the close %d (%.0f%%)" % (len(T), T.eod.sum(), 100 * T.eod.mean()))

    def daily(pnl, when):
        s = pd.Series(pnl.values, index=pd.DatetimeIndex(when).normalize())
        return s.groupby(level=0).sum().sort_index()

    def score(d, lo, hi):
        z = d[(d.index >= pd.Timestamp(lo)) & (d.index <= pd.Timestamp(hi))]
        cum = z.cumsum()
        dd = float((cum.cummax().clip(lower=0) - cum).max()) if len(z) else 0.0
        yrs = max((pd.Timestamp(hi) - pd.Timestamp(lo)).days / 365.25, 1e-9)
        roc30 = 30.0 * (z.sum() / yrs) / dd if dd > 0 else np.nan
        neg = z[z < 0]
        sortino = (z.mean() / np.sqrt((neg ** 2).sum() / len(z)) * np.sqrt(252)) if len(neg) else np.nan
        return roc30, sortino, z.sum(), dd

    base_d = daily(T.base, T.t)
    print("\nRAW TWIN (#314 as is, roll-corrected):")
    base_sc = {}
    for nm, (lo, hi) in HALVES.items():
        base_sc[nm] = score(base_d, lo, hi)
        print("  %-28s ROC@$30k %6.1f%%/yr  Sortino %5.2f  net $%9.0f  DD $%7.0f" % ((nm,) + base_sc[nm]))

    for vname, (kind, thr) in VARIANTS.items():
        sel = T.eod & (T.open_R >= thr if kind == "ge" else (T.open_R < thr if kind == "lt" else True))
        # base leg books on its exit day; the carried gap books on the next session's day
        legs = pd.concat([daily(T.base, T.t),
                          daily(T.gap.where(sel, 0.0), T.carry_day)]).groupby(level=0).sum().sort_index()
        assert legs.index.is_monotonic_increasing
        car = T[sel]
        gain = car.gap.sum()
        big = car.gap.max() if len(car) else 0.0
        print("\n%s: %d carried (%d weekend), carry money $%+.0f (longs $%+.0f, shorts $%+.0f), "
              "without the biggest gap $%+.0f"
              % (vname, len(car), int(car.weekend.sum()), gain, car.gap[car.side > 0].sum(),
                 car.gap[car.side < 0].sum(), gain - big))
        ok = [len(car) >= 100, gain - big > 0, car.gap[car.side < 0].sum() >= 0]
        for nm, (lo, hi) in HALVES.items():
            sc = score(legs, lo, hi)
            beat_roc = sc[0] > base_sc[nm][0]
            beat_so = sc[1] > base_sc[nm][1]
            ok.append(beat_roc)
            if nm != "WF STRETCH 2016-07..2025-08":
                ok.append(beat_so)
            print("  %-28s ROC@$30k %6.1f%%/yr (%s)  Sortino %5.2f (%s)  net $%9.0f  DD $%7.0f"
                  % (nm, sc[0], "beats" if beat_roc else "LOSES", sc[1], "beats" if beat_so else "LOSES", sc[2], sc[3]))
        control = kind in ("all", "lt")
        print("  VERDICT: %s" % ("CONTROL - reported only" if control else
                                  ("CLEARS ALL FIVE - go to validate" if all(ok) else "FAILS the pre-registered bar")))


if __name__ == "__main__":
    main()
