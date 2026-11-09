"""ENGU-Q BODY BREAK, R-FLOORED - STAGE 2: does a fixed R/R target pay where holding does not?

THE ONE QUESTION THE GATE LEFT OPEN.  The 48-cell gate found no held-to-close expectancy
distinguishable from zero in any cell, and none beating cost.  That does NOT by itself shut the
owner's question, because a fixed target TRUNCATES the outcome distribution: where the favourable
excursion mean-reverts, taking a target can pay more than holding to the session close.  Stage 2
tests that directly, on the owner's own T and M values, as a small DETERMINISTIC grid - no trial
budget, no search, no GO required.

Prereg docs/PREREG_enguq_bodybreak_rfloor_2026-11-09.md, addendum 2.

SELECTION IS RESULT-BLIND, which is the part that makes this worth reading.  The entry cells are
every gate cell with n >= 2,000 at s=1.5, across all three floors - six cells.  Trade count was
fixed by the grid before anything was measured and cannot peek at an outcome.  Choosing the cells
with the best baseline would be selecting on the very thing being tested.

THE EXIT IS THE OWNER'S, IN FULL.  Target entry + T*R; time stop at the earlier of M bars held or
the 15:55 bar close; the STOP WINS TIES on any bar whose range covers both.  Every trade closes the
same session - there is no overnight hold anywhere.

    python tools/enguq_bbrf_stage2.py --selftest
    python tools/enguq_bbrf_stage2.py
"""
import argparse
import json
import math
import os
import sys

import numpy as np
import pandas as pd

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
SHARED_CHECKOUT = r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"
if not os.path.isdir(os.path.join(_ROOT, "augur_uploads")) and os.path.isdir(SHARED_CHECKOUT):
    sys.path.insert(0, SHARED_CHECKOUT)

from tools.enguq_pullback_break_r2 import (            # noqa: E402
    ATR_LEN, atr, body_ratio, drift_slope, load_es, usd,
)
from tools.enguq_bbrf_gate import (                    # noqa: E402  one definition of each constant
    COST_HOUSE, COST_REAL, COST_SLIP, DOLLARS_PER_POINT, FLAT_MIN, FLOOR_PT,
    LAST_ENTRY_MIN, PRE_LOCKBOX_TO, mde,
)

ENTRY_CELLS = ((15, 0.5, 2.0), (20, 0.5, 2.0))     # the n >= 2,000 cells, result-blind
ATR_STOP = 1.5
TARGETS = (1.0, 1.5, 2.0, 3.0)
TIME_STOPS = (12, 24, 48)
N_FOLDS = 8
MAX_FOLD_SHARE = 0.40
TRADES_A_YEAR_FLOOR = 50.0
OUT = r"C:\EdgeLog\_anatomy_cache\enguq_bbrf_gate"


def exit_fixed(high, low, close, entry_px, entry_bar, stop_px, target_px, flat_bar):
    """Walk to the exit.  THE STOP IS CHECKED FIRST on every bar, so a bar covering both the stop
    and the target books the STOP - conservative, because optimism at the tie invents a result."""
    for i in range(entry_bar, flat_bar + 1):
        if low[i] <= stop_px:
            return i, stop_px, "stop"
        if high[i] >= target_px:
            return i, target_px, "target"
    return flat_bar, close[flat_bar], "time"


def four(daily, dates, years=None):
    from augur_engine.drawdowns import four_numbers
    return four_numbers(np.asarray(daily, float), dates=dates, years=years)


def selftest():
    ok = fail = 0

    def chk(name, cond):
        nonlocal ok, fail
        if cond:
            ok += 1
        else:
            fail += 1
            print("  MISMATCH: " + name)

    h = np.array([0.0, 11.0, 13.0, 20.0, 10.0])
    lo = np.array([0.0, 9.5, 9.2, 9.1, 9.0])
    c = np.array([0.0, 10.5, 12.0, 15.0, 9.5])
    # entry 10, stop 9, target 12 (T=2 on R=1): bar 2's high 13 reaches the target first
    b, px, why = exit_fixed(h, lo, c, 10.0, 1, 9.0, 12.0, 4)
    chk("a reached target books the TARGET", (b, px, why) == (2, 12.0, "target"))
    # a far target is never reached -> the time/flat exit at the last bar's close
    b2, px2, why2 = exit_fixed(h, lo, c, 10.0, 1, 8.0, 99.0, 4)
    chk("an unreachable target exits on TIME at the flat bar's close",
        (b2, px2, why2) == (4, 9.5, "time"))
    # a bar covering both: stop 9.5 and target 11 both inside bar 1
    b3, px3, why3 = exit_fixed(h, lo, c, 10.0, 1, 9.5, 11.0, 4)
    chk("a bar covering BOTH books the STOP", (b3, px3, why3) == (1, 9.5, "stop"))
    # the stop is checked before the target on LATER bars too
    b4, px4, why4 = exit_fixed(h, lo, c, 10.0, 1, 9.3, 13.0, 4)
    chk("the stop still wins on a later covering bar", why4 == "stop" and b4 == 2)

    chk("the owner's four targets are carried", TARGETS == (1.0, 1.5, 2.0, 3.0))
    chk("the time stops are one, two and four hours of 5m bars", TIME_STOPS == (12, 24, 48))
    chk("stage 2 is 72 cells",
        len(ENTRY_CELLS) * len(FLOOR_PT) * len(TARGETS) * len(TIME_STOPS) == 72)
    chk("MDE is imported, not re-implemented",
        abs(mde(1.0, 3000) - math.sqrt(7.85 / 3000)) < 1e-12)

    # a 1R target on a floored stop must put cost well under a tenth of R
    chk("cost at the 12 pt floor is under 4% of R", COST_REAL / 12.0 < 0.04)

    print("selftest: %d checks PASS, %d MISMATCH" % (ok, fail))
    return 0 if fail == 0 else 1


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        return selftest()

    os.makedirs(OUT, exist_ok=True)
    df, rows = load_es()
    pre = df[df["ts"] <= pd.Timestamp(PRE_LOCKBOX_TO + " 18:00", tz="America/New_York")]
    o = pre["open"].to_numpy(float); h = pre["high"].to_numpy(float)
    lo = pre["low"].to_numpy(float); c = pre["close"].to_numpy(float)
    n = len(c)
    tsi = pd.DatetimeIndex(pre["ts"])
    years = (tsi[-1] - tsi[0]).days / 365.25
    print("ES rows %s | pre-lockbox %s bars | %s .. %s | %.2f yr (LOCKBOX NOT OPENED)"
          % (usd(rows), usd(n), tsi[0].date(), tsi[-1].date(), years))

    trade_date = (tsi + pd.Timedelta(hours=6)).normalize().tz_localize(None)
    codes, uniq = pd.factorize(trade_date)
    minute = tsi.hour * 60 + tsi.minute
    flat_of_day = np.full(len(uniq), -1, int)
    for i in np.flatnonzero(minute <= FLAT_MIN):
        flat_of_day[codes[i]] = i
    flat_bar = flat_of_day[codes]

    rth = (minute >= 9 * 60 + 30) & (minute <= 15 * 60 + 30)
    can_enter = rth & (minute <= LAST_ENTRY_MIN)
    sma200 = pd.Series(c).rolling(200).mean().shift(1).to_numpy()
    higher_close = np.zeros(n, bool)
    higher_close[1:] = (c[1:] > c[:-1]) & (c[1:] > o[1:])
    atr20 = atr(h, lo, c, ATR_LEN)

    first_open = np.zeros(len(uniq)); seen = np.zeros(len(uniq), bool)
    for i, k in enumerate(codes):
        if not seen[k]:
            first_open[k] = o[i]; seen[k] = True
    day_open = first_open[codes]
    green = np.zeros(n, bool)
    green[1:] = c[:-1] > day_open[1:]

    all_dates = np.array(sorted(set(trade_date)), dtype="datetime64[ns]")
    # fold bounds are BAR INDICES over the trade-date axis, cut into 8 equal slices of DAYS
    bounds = np.linspace(0, len(all_dates), N_FOLDS + 1).astype(int)

    print("\nSTAGE 2 - 72 cells.  Entry cells chosen RESULT-BLIND by n >= 2,000 at s=1.5.")
    print("  Target = entry + T*R.  Flat at the earlier of M bars or the 15:55 close.  Stop wins ties.")
    print("  net $ at the REAL 0.45 pt round trip; 0.95 pt WITH SLIPPAGE in the JSON.\n")
    print(format("cell", "<30") + format("n", ">7") + format("a yr", ">7")
          + format("net $", ">11") + format("ROC30", ">8") + format("DD5 $", ">10")
          + format("DD%", ">7") + format("Sort", ">7") + format("fold+", ">6")
          + format("top fold", ">9") + format("1ep", ">5"))

    report = []
    for (w, d, b) in ENTRY_CELLS:
        sl = drift_slope(c, w)
        br = body_ratio(o, h, lo, c, w)
        sig = (higher_close & can_enter & green
               & ~np.isnan(sma200) & ~np.isnan(atr20) & ~np.isnan(sl)
               & (c > sma200) & (sl <= -(d * atr20) / w) & (br >= b))
        idx = np.flatnonzero(sig)
        for fl in FLOOR_PT:
            for T in TARGETS:
                for M in TIME_STOPS:
                    name = "w=%d f=%d T=%.1f M=%d" % (w, int(fl), T, M)
                    ex_d, pnl, rs = [], [], []
                    for i in idx:
                        e = i + 1
                        if e >= n or flat_bar[i] < e or codes[e] != codes[i]:
                            continue
                        entry_px = o[e]
                        risk = max(ATR_STOP * atr20[i], fl)
                        stop = entry_px - risk
                        fb = min(flat_bar[i], e + M - 1)
                        if fb < e:
                            continue
                        xb, xpx, why = exit_fixed(h, lo, c, entry_px, e, stop,
                                                  entry_px + T * risk, fb)
                        ex_d.append(trade_date[xb])
                        pnl.append((xpx - entry_px - COST_REAL) * DOLLARS_PER_POINT)
                        rs.append(risk)
                    cnt = len(pnl)
                    a_yr = cnt / years if years else 0.0
                    if cnt < 2:
                        report.append({"cell": name, "trades": cnt, "verdict": "NO TRADES"})
                        continue
                    ex = np.array(ex_d, dtype="datetime64[ns]")
                    pn = np.array(pnl, float)
                    daily = pd.Series(pn).groupby(ex).sum()
                    du = pd.Series(0.0, index=all_dates)
                    du.loc[daily.index] = daily.values
                    f = four(du.to_numpy(), dates=all_dates, years=years)

                    folds, shares = 0, []
                    for k in range(N_FOLDS):
                        a0, a1 = all_dates[bounds[k]], all_dates[min(bounds[k + 1], len(all_dates) - 1)]
                        m = (ex >= a0) & (ex <= a1)
                        s_ = float(pn[m].sum())
                        shares.append(s_)
                        if s_ > 0:
                            folds += 1
                    net = float(pn.sum())
                    top = (max(shares) / net) if net > 0 else None
                    passes = (folds >= 7 and net > 0 and a_yr >= TRADES_A_YEAR_FLOOR
                              and top is not None and top <= MAX_FOLD_SHARE
                              and not bool(f.get("one_episode")))
                    report.append({
                        "cell": name, "w": w, "d": d, "b": b, "floor_pt": fl, "T": T, "M": M,
                        "trades": cnt, "a_year": round(a_yr, 1),
                        "mean_risk_pt": round(float(np.mean(rs)), 2),
                        "net_usd_real": round(net, 0),
                        "net_usd_slip": round(float(((pn / DOLLARS_PER_POINT)
                                                     - (COST_SLIP - COST_REAL)).sum()
                                                    * DOLLARS_PER_POINT), 0),
                        "roc30": None if f.get("roc30") is None else round(float(f["roc30"]), 2),
                        "dd5_usd": None if f.get("dd5_usd") is None else round(float(f["dd5_usd"]), 0),
                        "dd_pct_peak": None if f.get("dd_pct_peak") is None else round(float(f["dd_pct_peak"]), 2),
                        "sortino": None if f.get("sortino") is None else round(float(f["sortino"]), 3),
                        "folds_positive": folds, "fold_net": [round(x, 0) for x in shares],
                        "max_fold_share": None if top is None else round(top, 3),
                        "one_episode": bool(f.get("one_episode")), "passes_bar": bool(passes)})

                    def sh(v, wd, nd=2, money=False):
                        if v is None:
                            return format("-", ">" + str(wd))
                        return format(usd(v) if money else format(float(v), "." + str(nd) + "f"),
                                      ">" + str(wd))
                    print(format(name, "<30") + format(usd(cnt), ">7")
                          + format(format(a_yr, ".1f"), ">7") + sh(net, 11, 0, True)
                          + sh(f.get("roc30"), 8, 2) + sh(f.get("dd5_usd"), 10, 0, True)
                          + sh(f.get("dd_pct_peak"), 7, 2) + sh(f.get("sortino"), 7, 3)
                          + format(str(folds) + "/8", ">6")
                          + sh(None if top is None else top * 100, 9, 1)
                          + format("YES" if f.get("one_episode") else "no", ">5"))

    npass = sum(1 for r in report if r.get("passes_bar"))
    print("\nCELLS CLEARING THE FULL BAR: %d of %d" % (npass, len(report)))
    if not npass:
        print("NO CELL CLEARS - the owner's fixed-R intraday exit does not pay on this entry.")
    p = os.path.join(OUT, "stage2.json")
    with open(p, "w", encoding="utf-8") as fh:
        json.dump({"rows": report, "years": round(years, 2),
                   "cost_pts": {"real": COST_REAL, "house": COST_HOUSE, "slip": COST_SLIP}},
                  fh, indent=1)
    print("wrote " + p)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
