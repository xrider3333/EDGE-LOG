"""THE 1:1 BOOK TIED. DOES ANY OTHER WEIGHT ACTUALLY WIN, OR IS THE WHOLE CURVE A TIE?

tools/r3_two_horizon_book.py pooled the uncapped crown and the hold-capped crown one contract
each: concentration fell to 36.2% (the lowest measured on this family) and both index down
years stayed positive, but annualised MAR came out 0.95 against the better leg's 0.97 - a
tie, and the pre-registered bar said BEAT, so nothing was queued.

1:1 is a convention, not a result. This walks the whole weight curve from all-uncapped to
all-capped and asks whether the tie is a property of the mix or just of that one point.

WHY THIS IS NOT AUTOMATICALLY CURVE FITTING, AND WHERE IT WOULD BE: a weight is chosen on the
same window it is measured on, so a single winning point proves nothing - that is exactly how
this project has burned itself before. The protection is to require the winner to sit in a
PLATEAU: its two neighbouring weights must beat the better leg too. A lone spike is reported
and rejected.

PRE-REGISTERED, written before running. A weight is worth queueing only if:
  1. its MAR beats the better single leg by at least 5%   (0.97 -> 1.02 or better; a 2%
     "win" is inside the noise this project has already measured on drawdown-based reads)
  2. BOTH neighbouring weights also beat the better single leg  (the plateau rule)
  3. pooled top-10 share  < 50%
  4. both index down years positive
  5. it is not an endpoint of the curve (an endpoint is just one of the legs again)
Failing any of these, the answer is that horizon mixing does not improve risk-adjusted
return on this family, and that is a real answer worth writing down once.

RESULT, 2026-09-09 - NO WEIGHT CLEARS. HORIZON MIXING IS CLOSED as a way to raise MAR.

  w(cap)      net $    maxDD $   MAR  top-10   corr    2018    2022
   0.0      613,126     39,200  0.97   55.6%  +0.48   9,403   6,256   <- all uncapped
   0.2      603,683     38,687  0.97   46.8%  +0.47  10,464   5,347
   0.3      598,962     38,687  0.96   42.5%  +0.46  10,995   4,892
   0.4      594,241     38,687  0.96   38.6%  +0.45  11,525   4,437
   0.5      589,519     38,687  0.95   36.2%  +0.45  12,055   3,983
   0.6      584,798     38,687  0.94   36.0%  +0.44  12,586   3,528
   0.7      580,077     38,687  0.93   36.4%  +0.43  13,116   3,074
   0.8      575,356     38,687  0.93   37.7%  +0.42  13,647   2,619
   1.0      565,913     40,548  0.87   42.7%  +0.39  14,708   1,710   <- all capped

MAR falls monotonically with the capped weight; nothing gets near the +5% the bar required,
so no mix is queued and this question does not need re-opening. Every weight is 17/17 on
positive years.

THE ONE THING WORTH TAKING FROM THE CURVE, and it is a Pareto point rather than a win:
at w=0.2 the MAR is 0.97 - IDENTICAL to the uncapped crown - while concentration falls 55.6%
-> 46.8% and index correlation edges 0.48 -> 0.47. That is a free reduction in tail
dependence, not a better edge, and the pre-registered bar deliberately did not reward it. If
the owner wants it, the practical shape is 4 uncapped contracts to 1 capped, which needs size
to express - a one-contract account cannot trade a 0.2 weight. It is an owner call about what
the book is FOR (tail dependence vs risk-adjusted return), not a result that promotes itself.

Also note the interior weights all share the same $38,687 drawdown: one episode dominates the
whole curve, which is another reason not to read small MAR differences here as signal.
"""
import io
import json
import os
import sys

import numpy as np
import pandas as pd

ROOT = r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"
sys.path.insert(0, ROOT)
os.chdir(ROOT)
from augur_engine.engine import run_backtest                      # noqa: E402
from augur_engine.data import find_master, load_master_arrays     # noqa: E402

SCR = os.path.dirname(os.path.abspath(__file__))
WIN = dict(date_from="2010-06-07", date_to="2026-06-30")
MULT, COST = 20.0, 0.533
STRAT = "ENGUQ_1M_ETH_R3_1_0.py"
CROWN = dict(buf_atr=0.3, tl_len=206, trail_frac=2.5, limit_atr=0.55, atr_len=52, act_R=1.5,
             breakeven_R=2.0, ema_len=220, er_len=100, stop_mult=1.0, regime_len=10,
             min_brk=1.6, vol_mult=1.1, er_th=0.0)
# weight on the CAPPED leg; the uncapped leg carries (1 - w). Endpoints are the bare legs.
WEIGHTS = [0.0, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 1.0]


def leg_daily(cap, arr, idx):
    r = run_backtest(STRAT, arrays=arr, params=dict(CROWN, max_hold_bars=cap),
                     cost_pts=COST, return_trades=True)
    tr = (r or {}).get("trades") or []
    ex = pd.DatetimeIndex([idx[int(t[1])] for t in tr]).normalize()
    return pd.Series([t[2] * MULT for t in tr], index=ex).groupby(level=0).sum()


def read(daily, bench, years):
    eq = daily.cumsum()
    dd = float((eq.cummax() - eq).max())
    d = daily.values
    yr = daily.groupby(daily.index.year).sum()
    common = yr.index.intersection(bench.index)
    return dict(net=float(d.sum()), dd=dd,
                mar=(float(d.sum()) / years) / dd if dd > 1e-9 else float("nan"),
                top10=float(np.sort(d)[::-1][:10].sum() / d.sum()),
                corr=float(yr[common].corr(bench[common])),
                y2018=float(yr.get(2018, 0.0)), y2022=float(yr.get(2022, 0.0)),
                pos_years=int((yr > 0).sum()), n_years=int(len(yr)))


def main():
    arr = load_master_arrays(find_master("NQ", "1m", "eth", "db_noadj_eth"), **WIN)
    idx = pd.DatetimeIndex(pd.to_datetime(arr["index"]))
    try:
        idx = idx.tz_localize(None)
    except (TypeError, AttributeError):
        pass
    years = (idx[-1] - idx[0]).days / 365.25
    last = pd.Series(np.asarray(arr["close"], float), index=idx).resample("YE").last()
    bench = ((last / last.shift(1) - 1.0) * 100).dropna()
    bench.index = bench.index.year

    unc = leg_daily(0, arr, idx)
    cap = leg_daily(8280, arr, idx)
    frame = pd.concat([unc, cap], axis=1).fillna(0.0)
    frame.columns = ["uncapped", "capped"]
    # sanity check the pooling before anything is read off it (the sum() bug, 2026-09-09)
    assert abs(frame.sum().sum() - (unc.sum() + cap.sum())) < 1.0, "pooling lost money"
    print("  legs built: uncapped $%s, capped $%s, 1:1 pooled $%s (checks out)"
          % (format(unc.sum(), ",.0f"), format(cap.sum(), ",.0f"),
             format(frame.sum().sum(), ",.0f")), flush=True)

    rows = {}
    print("\n  %8s %12s %10s %6s %6s %6s %9s %9s %5s"
          % ("w(cap)", "net $", "maxDD $", "MAR", "top10", "corr", "2018", "2022", "yrs+"),
          flush=True)
    for w in WEIGHTS:
        daily = frame["uncapped"] * (1.0 - w) + frame["capped"] * w
        s = read(daily, bench, years)
        rows[w] = s
        tag = "  <- all uncapped" if w == 0 else ("  <- all capped" if w == 1 else "")
        print("  %8.1f %12s %10s %6.2f %5.1f%% %+6.2f %9s %9s %2d/%d%s"
              % (w, format(s["net"], ",.0f"), format(s["dd"], ",.0f"), s["mar"],
                 s["top10"] * 100, s["corr"], format(s["y2018"], ",.0f"),
                 format(s["y2022"], ",.0f"), s["pos_years"], s["n_years"], tag), flush=True)

    best_leg = max(rows[0.0]["mar"], rows[1.0]["mar"])
    need = best_leg * 1.05
    interior = [w for w in WEIGHTS if 0.0 < w < 1.0]
    winners = []
    for i, w in enumerate(interior):
        s = rows[w]
        nb = [interior[i - 1] if i > 0 else None, interior[i + 1] if i + 1 < len(interior) else None]
        nb_ok = all(rows[x]["mar"] > best_leg for x in nb if x is not None)
        ok = (s["mar"] >= need and nb_ok and s["top10"] < 0.50
              and s["y2018"] > 0 and s["y2022"] > 0)
        if ok:
            winners.append(w)
    print("\nPRE-REGISTERED VERDICT (better single leg MAR %.2f, needs >= %.2f, plus plateau, "
          "top-10 < 50%%, both down years positive)" % (best_leg, need))
    for w in interior:
        s = rows[w]
        print("   w=%.1f  MAR %.2f %-4s  top10 %.1f%% %-4s  2018/2022 %s/%s"
              % (w, s["mar"], "OK" if s["mar"] >= need else "no",
                 s["top10"] * 100, "OK" if s["top10"] < 0.50 else "no",
                 "+" if s["y2018"] > 0 else "-", "+" if s["y2022"] > 0 else "-"))
    print("\n%s" % ("CLEARS: " + str(winners) + " -- queue the best as a BOOK Auto-Validate."
                    if winners else
                    "NO WEIGHT CLEARS. Mixing the two horizons does not improve risk-adjusted "
                    "return on this family at any weight - the whole curve is a tie or worse. "
                    "Nothing queued; this closes the horizon-mixing question."))
    json.dump({str(k): v for k, v in rows.items()},
              io.open(os.path.join(SCR, "_horizon_weights.json"), "w"), indent=1, default=float)
    print("SAVED")


if __name__ == "__main__":
    main()
