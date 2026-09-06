"""
WHICH ORB DO WE ACTUALLY TRADE?  (2026-09-05, owner: "your job is to find the right ORB
to trade.")

Every ORB configuration that has PASSED a real Auto-Validate on the legal base
(ORB_3_4 / ORB_3_6 / ORB_3_9 - the ORB_3_0 / ORB_SIMPLE / ORBV2 family is the retired
look-ahead era and is excluded) is re-run here side by side and scored on the things
that decide what goes on a chart, not on what wins a backtest table:

  1. THE RECENT REGIME.  The full 16-year window is diluted by 2010-2016, which was flat
     for this strategy (the standing regime caveat). A configuration is only worth
     trading if it works on the tape we are about to trade, so every row is measured on
     the full window AND on the last 8, 5 and 3 years.
  2. DROUGHT.  The vol-regime filter stands the strategy down for whole stretches - ten
     straight sessions in August 2026. A config that sits out for months is hard to hold
     on to whatever its backtest says, so we measure the longest gap between trades and
     the share of sessions actually traded.
  3. RISK AND CONSISTENCY.  Max drawdown, worst rolling 12 months, and how many calendar
     years finish positive.
  4. THE TWO OWNER READS.  EV R (expectancy in units of the average losing trade) and
     R / YR (EV R x trades per year).

The validated evidence each row already carries - walk-forward folds, walk-forward
efficiency, lockbox and the ES transfer leg - is printed from the run documents in the
REFERENCE table at the top so the whole decision sits on one screen.

NOTHING HERE CROWNS ANYTHING. It ranks; the owner crowns.

FINDING THAT CHANGED THE ANSWER (2026-09-05): EV R AND R / YR ARE GAMEABLE HERE.
The breakeven stop sets the AVERAGE LOSS, which is the denominator of EV R. Moving the
breakeven trigger earlier scratches more trades to zero, shrinks the average loss, and
inflates EV R and R / YR without making money. Measured on the last 5 years, same config
otherwise (atr 0.75 / vpace 0.80 / stop 2.5 / target 5.0):

    be_after_R   net$      DD$      EV R    avg loss   scratched   MAR
    0.00       328,442   31,829    0.203     $2,095        13      2.07
    0.10       235,084   34,382    0.559       $544       464      1.37   <- best EV R, WORST money
    0.25       244,082   31,139    0.300     $1,052       283      1.57
    0.50       319,297   22,925    0.249     $1,657       114      2.79   <- best MAR
    1.00       330,632   27,766    0.210     $2,038        27      2.39

Net money is essentially FLAT from 0.0 to 1.0 ($319k-$331k, a 3 percent spread) while
EV R nearly triples. So EV R is not measuring edge across this knob - it is measuring how
often the stop scratches. What the breakeven actually buys is DRAWDOWN: $22,925 at 0.5
against $27,766 at 1.0 and $31,829 with it off.

Therefore this file ranks on the recent-window MAR and drawdown as well, and the ORB
recommendation rests on those, NOT on the EV R column. The EV R and R / YR columns stay
because the owner asked for them and because they are honest WITHIN a fixed breakeven -
they are just not safe to optimise across one.

    python tools/orb_pick.py
"""
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from tools.orb_hunt import strat, IS_END, LB_END                     # noqa: E402
from tools.orb_hunt3 import robustness                               # noqa: E402

COST, MULT = 0.533, 20.0
_UP = os.path.join(ROOT, "augur_uploads")
if not os.path.isdir(_UP):
    _UP = os.path.join(r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG", "augur_uploads")
MASTER = os.path.join(_UP, "NOADJ_NQ_5m_RTH.csv")

BASE = dict(or_bars=2, trade_mode="First-candle dir", close_confirm=True,
            partial_exit_R=0.0, trail_bars=0, flat_eod=True, skip_holidays=True,
            breakout_buf=0.25, stop_frac=2.0, target_R=5.5, be_after_R=1.0,
            atr_filter=0.7, vpace_filter=0.7)

# run -> (label, overrides, validated evidence from the run document)
CANDIDATES = [
    (234, "CROWN C2", {}, "7/8 wfe 4.65 LB $88,943/1.453 ES 1.024"),
    (239, "BE 0.8", dict(be_after_R=0.8), "7/8 wfe 4.42 LB $94,268/1.495 ES 1.028"),
    (244, "STOP 1.75", dict(stop_frac=1.75), "7/8 wfe 4.59 LB $90,036/1.490 ES 1.027"),
    (250, "TARGET 5.0", dict(target_R=5.0), "7/8 wfe 4.57 LB $86,988/1.443 ES 1.024"),
    (257, "E1 wide", dict(atr_filter=0.5, breakout_buf=0.3, stop_frac=2.5),
     "7/8 wfe 4.95 LB $91,405/1.502 ES 1.000"),
    (260, "E3 tight-pace", dict(breakout_buf=0.3, stop_frac=1.75, vpace_filter=0.9),
     "7/8 wfe 4.39 LB $95,543/1.712 ES 1.051"),
    (266, "G115 no-vol", dict(atr_filter=0.0, breakout_buf=0.3, stop_frac=2.5),
     "7/8 wfe 5.10 LB $91,405/1.502 ES 1.003"),
    (294, "F75", dict(atr_filter=0.75), "7/8 wfe 4.27 LB $92,383/1.479 ES not run"),
    (297, "F75/80", dict(atr_filter=0.75, vpace_filter=0.8), "7/8 wfe 4.00 LB $98,179/1.536 ES not run"),
    (298, "F80/80", dict(atr_filter=0.8, vpace_filter=0.8), "7/8 wfe 3.72 LB $105,977/1.604 ES not run"),
    (314, "R6", dict(atr_filter=0.75, vpace_filter=0.8, stop_frac=2.5, target_R=5.0,
                     be_after_R=0.5), "7/8 wfe 3.15 LB $92,102/1.561 ES 1.019"),
]

WINDOWS = [("FULL 16.2y", "2010-06-07"), ("last 8y", "2018-08-13"),
           ("last 5y", "2021-08-13"), ("last 3y", "2023-08-13")]

_B = None


def bars():
    global _B
    if _B is None:
        df = pd.read_csv(MASTER)
        dt = pd.to_datetime(df["time"], unit="s", utc=True).dt.tz_convert("US/Eastern")
        df = df.assign(_dt=dt).sort_values("time").reset_index(drop=True)
        _B = dict(open=df["open"].values.astype(float), high=df["high"].values.astype(float),
                  low=df["low"].values.astype(float), close=df["close"].values.astype(float),
                  volume=df["volume"].values.astype(float),
                  day_id=pd.factorize(df["_dt"].dt.date)[0],
                  index=pd.DatetimeIndex(df["_dt"]))
    return _B


def trades_of(over):
    """Run one config ONCE on the whole master; slice by date afterwards, so every
    window sees the identical warm-up and the identical filter history."""
    b = bars()
    r = strat("ORB_3_6.py").run_backtest(
        b["open"], b["high"], b["low"], b["close"], volumes=b["volume"],
        day_id=b["day_id"], return_trades=True, **dict(BASE, **over))
    idx = b["index"]
    le = pd.Timestamp(LB_END, tz=idx.tz)
    out = []
    for t in (r or {}).get("trades") or []:
        d = idx[t[0]]
        if d <= le:
            out.append((d.tz_localize(None), (t[2] - COST) * MULT))
    return out


def sessions():
    b = bars()
    idx = b["index"]
    return pd.Series(idx.date).drop_duplicates().values


def stats(tr, start, all_days):
    """tr = [(entry_datetime, net$)] already inside the window."""
    if len(tr) < 20:
        return None
    dts = [d for d, _ in tr]
    p = np.array([x for _, x in tr], float)
    yrs = (dts[-1] - dts[0]).days / 365.25
    cum = np.cumsum(p)
    dd = abs(float((cum - np.maximum.accumulate(cum)).min()))
    wins, losses = p[p > 0], p[p < 0]
    al = abs(losses.mean()) if len(losses) else np.nan
    evr = p.mean() / al if al == al and al > 0 else np.nan
    rob = robustness(dts, list(p))
    # drought: longest gap in CALENDAR DAYS between consecutive entries
    gaps = [(dts[i + 1] - dts[i]).days for i in range(len(dts) - 1)]
    # share of trading sessions in the window that produced a trade
    d0 = pd.Timestamp(start).date()
    win_days = [d for d in all_days if d >= d0 and d <= pd.Timestamp(LB_END).date()]
    traded = len({d.date() for d in dts})
    yearly = pd.Series(p, index=pd.DatetimeIndex(dts)).groupby(pd.DatetimeIndex(dts).year).sum()
    return dict(n=len(p), net=p.sum(), dd=dd, pf=wins.sum() / abs(losses.sum()) if len(losses) else np.inf,
                wr=100 * len(wins) / len(p), evr=evr, ryr=evr * len(p) / yrs if yrs > 0 else np.nan,
                tpy=len(p) / yrs if yrs > 0 else np.nan, mar=(p.sum() / yrs) / dd if dd else np.nan,
                worst12=rob["worst"], win12=rob["win_pct"],
                maxgap=max(gaps) if gaps else 0, p95gap=int(np.percentile(gaps, 95)) if gaps else 0,
                sess=100.0 * traded / len(win_days) if win_days else np.nan,
                posyrs=int((yearly > 0).sum()), nyrs=len(yearly))


def main():
    all_days = sessions()
    print("=" * 132)
    print("WHICH ORB DO WE TRADE?  Every PASSING legal ORB config, re-run side by side.")
    print("  master NQ 5m RTH no-adj, 0.533 pts/RT, one contract, entries to %s" % LB_END)
    print("=" * 132)
    print("\nVALIDATED EVIDENCE (from the run documents - folds / walk-forward efficiency / lockbox / ES transfer)")
    for rn, lab, _, ev in CANDIDATES:
        print("   #%-4d %-14s %s" % (rn, lab, ev))

    cache = {}
    for rn, lab, over, _ in CANDIDATES:
        cache[rn] = trades_of(over)

    for wlab, wstart in WINDOWS:
        print("\n" + "-" * 132)
        print("%s   (from %s)" % (wlab, wstart))
        print("%-5s %-14s %6s %10s %9s %6s %6s %6s %6s %6s %9s %5s %6s %6s %5s"
              % ("run", "config", "trd", "net$", "DD$", "PF", "MAR", "EV R", "R/YR", "tr/yr",
                 "worst12", "w12%", "maxgap", "sess%", "yrs+"))
        print("-" * 132)
        rows = []
        for rn, lab, over, _ in CANDIDATES:
            tr = [(d, v) for d, v in cache[rn] if d >= pd.Timestamp(wstart)]
            s = stats(tr, wstart, all_days)
            if s:
                rows.append((rn, lab, s))
        for rn, lab, s in sorted(rows, key=lambda x: -x[2]["ryr"]):
            print("#%-4d %-14s %6d %10s %9s %6.3f %6.2f %6.3f %6.1f %6.0f %9s %5.1f %6d %6.1f %2d/%-2d"
                  % (rn, lab, s["n"], f"{s['net']:,.0f}", f"{s['dd']:,.0f}", s["pf"], s["mar"],
                     s["evr"], s["ryr"], s["tpy"], f"{s['worst12']:,.0f}", s["win12"],
                     s["maxgap"], s["sess"], s["posyrs"], s["nyrs"]))
    print("\nmaxgap = longest run of CALENDAR DAYS with no trade.  sess% = share of trading")
    print("sessions in the window that produced a trade.  yrs+ = calendar years net positive.")


if __name__ == "__main__":
    main()
