"""ENGU-Q BODY BREAK, R-FLOORED - the 48-cell POWER-FIRST GATE.

WHAT THIS DECIDES.  Owner order 11-09 (MANAGER #149) asks for a NEW intraday strategy built around a
fixed R/R target or a time stop.  Six independent reads in this lane say shortening this family's
hold taxes the edge, so this gate exists to close the round at draft if the arithmetic says it cannot
work - BEFORE a 900-trial budget is spent.  Prereg
docs/PREREG_enguq_bodybreak_rfloor_2026-11-09.md, body sha
6fe6f7525bfb84d66b9a7f7167ed8db68f79b5ab2182490c89d5b5e5d5ceeeea, gate statistics in addendum 1.

THE ONE THING r2 GOT WRONG THAT THIS DESIGN FIXES.  r2's measured risk was 1.5-5.3 ES points, so the
real 0.45 pt round trip was 8-30% OF 1R.  No exit rule survives that toll; it is arithmetic, not a
market finding.  Here the stop is max(s x ATR20, FLOOR_PT) with FLOOR_PT in {8,12,16} points, which
puts cost near 3-6% of R - and the gate reports cost in R per cell so the claim is measured, not
asserted.

TWO STATISTICS, BECAUSE ONE WOULD BE DISHONEST (addendum 1).
  BASELINE  hold to the SESSION-END reference exit (out at the 15:55 bar close, or the stop if it is
            touched first).  No target, no time stop.  The entry's intraday expectancy in R.
  CEILING   mean MAXIMUM FAVOURABLE EXCURSION in R inside the session before the stop.  No target can
            realise more than the move that happened.
A negative baseline does NOT close a cell: a target truncates the outcome distribution and can raise
expectancy where the excursion mean-reverts.  THE CEILING is what can close a cell - if mean MFE in R
is at or below cost in R, no target clears cost.

GROSS IS COMPARED IN R, NEVER IN POINTS.  With a variable R, a points comparison across cells
compares POSITION SIZES rather than edges.  That was this lane's charge against MANAGER's scan r1 and
then its own mistake in r2; it is pinned here so it cannot happen a third time.

    python tools/enguq_bbrf_gate.py --selftest
    python tools/enguq_bbrf_gate.py
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
# A data-reading driver resolves masters from the engine's OWN package location, not the working
# directory, so a worktree's engine looks for augur_uploads inside the worktree - where the
# gitignored data is not.  Shared checkout goes first when this runs from a worktree.
SHARED_CHECKOUT = r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"
if not os.path.isdir(os.path.join(_ROOT, "augur_uploads")) and os.path.isdir(SHARED_CHECKOUT):
    sys.path.insert(0, SHARED_CHECKOUT)

from tools.enguq_pullback_break_r2 import (            # noqa: E402  r2's own definitions
    ATR_LEN, atr, body_ratio, drift_slope, load_es, usd,
)

PREREG = "docs/PREREG_enguq_bodybreak_rfloor_2026-11-09.md"
PREREG_BODY_SHA = "6fe6f7525bfb84d66b9a7f7167ed8db68f79b5ab2182490c89d5b5e5d5ceeeea"
PRE_LOCKBOX_TO = "2025-06-30"
OUT = r"C:\EdgeLog\_anatomy_cache\enguq_bbrf_gate"

# ---- the grid the gate screens: ENTRY and R FLOOR only.  T and M are the validate's to search.
W_SLOPE = (15, 20)
D_ATR = (0.5, 1.0)
BODY = (2.0, 3.0)
ATR_STOP = (1.5, 2.5)
FLOOR_PT = (8.0, 12.0, 16.0)

DOLLARS_PER_POINT = 50.0
COST_REAL = 0.45          # MANAGER #144: $5.66 both sides at $12.50/pt
COST_HOUSE = 0.533        # the house headline, carried for comparability with r2
COST_SLIP = 0.95          # the real figure WITH the $5-a-side slippage a market order pays
LAST_ENTRY_MIN = 14 * 60 + 30      # no entry after 14:30 ET, so a time stop has room
FLAT_MIN = 15 * 60 + 55            # the session-end reference exit bar
TRADES_A_YEAR_FLOOR = 50.0


def mde(sd, n):
    """Minimum detectable edge for a one-sample mean, 80% power, two-sided 5%.

    n = 7.85 * sd^2 / delta^2, so delta = sd * sqrt(7.85 / n).  None when there is nothing to
    measure - a zero n or a degenerate spread is not a small MDE, it is no MDE."""
    if not n or sd is None or not np.isfinite(sd) or sd <= 0:
        return None
    return float(sd) * math.sqrt(7.85 / float(n))


def session_exit(high, low, close, entry_px, entry_bar, stop_px, flat_bar):
    """The SESSION-END reference exit, plus the maximum favourable excursion on the way.

    Walks from the entry bar to the session's flat bar.  THE STOP IS CHECKED FIRST on every bar, so
    a bar whose range covers both the stop and a better price books the stop - conservative by
    construction, because optimism at the tie is how an intrabar result gets invented.

    Returns (exit_bar, exit_px, reason, mfe_pts) where mfe_pts is the best HIGH seen up to and
    including the exit bar, measured from the entry price and floored at zero.
    """
    best = 0.0
    for i in range(entry_bar, flat_bar + 1):
        if low[i] <= stop_px:
            return i, stop_px, "stop", best
        best = max(best, high[i] - entry_px)
    return flat_bar, close[flat_bar], "flat", best


def selftest():
    ok = fail = 0

    def chk(name, cond):
        nonlocal ok, fail
        if cond:
            ok += 1
        else:
            fail += 1
            print("  MISMATCH: " + name)

    # --- mde arithmetic
    chk("MDE is sd*sqrt(7.85/n)", abs(mde(1.0, 3000) - math.sqrt(7.85 / 3000)) < 1e-12)
    chk("MDE at 3,000 trades on sd 1.0 is about 0.051 R", abs(mde(1.0, 3000) - 0.0512) < 5e-4)
    chk("MDE at 1,000 trades on sd 1.0 is about 0.089 R", abs(mde(1.0, 1000) - 0.0886) < 5e-4)
    chk("a zero trade count has NO MDE, not a small one", mde(1.0, 0) is None)
    chk("a degenerate spread has NO MDE", mde(0.0, 500) is None)

    # --- the reference exit
    h = np.array([10.0, 12.0, 15.0, 11.0, 10.5])
    lo = np.array([9.5, 9.8, 11.0, 9.6, 10.0])   # never below the 9.0 stop
    c = np.array([9.8, 11.5, 14.0, 9.7, 10.2])
    # entry 10.0 at bar 1, stop 9.0, flat bar 4: never stopped, out at the close of bar 4
    b, px, why, mfe = session_exit(h, lo, c, 10.0, 1, 9.0, 4)
    chk("an untouched stop exits at the SESSION-END close", (b, px, why) == (4, 10.2, "flat"))
    chk("the excursion is the best HIGH above entry", abs(mfe - 5.0) < 1e-12)
    # stop at 9.9 is hit on bar 1 itself
    b2, px2, why2, mfe2 = session_exit(h, lo, c, 10.0, 1, 9.9, 4)
    chk("a stop touched on the entry bar books the stop", (b2, px2, why2) == (1, 9.9, "stop"))
    chk("a trade stopped at once has no favourable excursion", abs(mfe2 - 0.0) < 1e-12)
    # the stop is checked BEFORE the high on every bar
    h3 = np.array([0.0, 20.0]); lo3 = np.array([0.0, 5.0]); c3 = np.array([0.0, 6.0])
    b3, px3, why3, mfe3 = session_exit(h3, lo3, c3, 10.0, 1, 9.0, 1)
    chk("a bar covering BOTH the stop and a better price books the STOP",
        why3 == "stop" and px3 == 9.0)
    chk("that conservative tie reports NO excursion", abs(mfe3 - 0.0) < 1e-12)

    # --- the R floor actually floors
    atr20 = np.array([1.0, 10.0])
    risk = np.maximum(1.5 * atr20, 12.0)
    chk("a small ATR is overridden by the floor", risk[0] == 12.0)
    chk("a large ATR beats the floor", risk[1] == 15.0)
    chk("cost in R falls as the floor rises",
        COST_REAL / 12.0 < COST_REAL / 8.0)
    chk("the real round trip at a 12 pt floor is about 3.75% of R",
        abs(COST_REAL / 12.0 - 0.0375) < 1e-9)

    # --- the grid is the declared 48 and nothing more
    n_cells = len(W_SLOPE) * len(D_ATR) * len(BODY) * len(ATR_STOP) * len(FLOOR_PT)
    chk("the gate screens exactly 48 cells", n_cells == 48)

    print("selftest: %d checks PASS, %d MISMATCH" % (ok, fail))
    return 0 if fail == 0 else 1


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        return selftest()

    os.makedirs(OUT, exist_ok=True)
    pr = os.path.join(SHARED_CHECKOUT, PREREG) if not os.path.exists(PREREG) else PREREG
    if os.path.exists(pr):
        body = open(pr, "rb").read().split(b"\n---\n\n## ADDENDUM 1")[0]
        import hashlib
        got = hashlib.sha256(body).hexdigest()
        print("prereg body sha %s  %s" % (got, "MATCHES" if got == PREREG_BODY_SHA else "DIFFERS"))
    else:
        print("prereg not found at %s - running anyway, but the sha is unverified" % pr)

    df, rows = load_es()
    print("ES ADJ_ES_5m_ETH.csv rows %s" % usd(rows))
    pre = df[df["ts"] <= pd.Timestamp(PRE_LOCKBOX_TO + " 18:00", tz="America/New_York")]
    o = pre["open"].to_numpy(float); h = pre["high"].to_numpy(float)
    lo = pre["low"].to_numpy(float); c = pre["close"].to_numpy(float)
    n = len(c)
    tsi = pd.DatetimeIndex(pre["ts"])
    years = (tsi[-1] - tsi[0]).days / 365.25
    print("pre-lockbox %s bars, %s .. %s, %.2f years (LOCKBOX NOT OPENED)"
          % (usd(n), tsi[0].date(), tsi[-1].date(), years))

    # the ETH session rolls at 18:00 ET, so a bar at or after 18:00 belongs to the NEXT trade date
    trade_date = (tsi + pd.Timedelta(hours=6)).normalize().tz_localize(None)
    codes, uniq = pd.factorize(trade_date)
    minute = tsi.hour * 60 + tsi.minute

    # the session-end reference bar for each trade date: the LAST bar at or before 15:55
    flat_of_day = np.full(len(uniq), -1, int)
    elig = np.flatnonzero(minute <= FLAT_MIN)
    for i in elig:
        flat_of_day[codes[i]] = i
    flat_bar = flat_of_day[codes]

    rth = (minute >= 9 * 60 + 30) & (minute <= 15 * 60 + 30)
    can_enter = rth & (minute <= LAST_ENTRY_MIN)
    sma200 = pd.Series(c).rolling(200).mean().shift(1).to_numpy()
    higher_close = np.zeros(n, bool)
    higher_close[1:] = (c[1:] > c[:-1]) & (c[1:] > o[1:])
    atr20 = atr(h, lo, c, ATR_LEN)

    # session green so far: the close is above the session's FIRST open, read one bar back
    first_open_of_day = np.zeros(len(uniq))
    seen = np.zeros(len(uniq), bool)
    for i, k in enumerate(codes):
        if not seen[k]:
            first_open_of_day[k] = o[i]
            seen[k] = True
    day_open = first_open_of_day[codes]
    green = np.zeros(n, bool)
    green[1:] = c[:-1] > day_open[1:]

    print("\nGATE - 48 cells, ENTRY and R FLOOR only.  Gross in R, never in points.")
    print("  BASELINE = session-end reference exit.  CEILING = mean MFE in R (no target beats it).")
    print("  cost R at the REAL 0.45 pt round trip; MDE = sd*sqrt(7.85/n).\n")
    hdr = (format("cell", "<34") + format("n", ">7") + format("a yr", ">7")
           + format("risk pt", ">9") + format("cost R", ">8") + format("base R", ">9")
           + format("sd", ">7") + format("MDE", ">7") + format("ceil R", ">8")
           + format("verdict", ">16"))
    print(hdr)

    report = []
    for w in W_SLOPE:
        sl = drift_slope(c, w)
        for d in D_ATR:
            for b in BODY:
                br = body_ratio(o, h, lo, c, w)
                sig = (higher_close & can_enter & green
                       & ~np.isnan(sma200) & ~np.isnan(atr20) & ~np.isnan(sl)
                       & (c > sma200) & (sl <= -(d * atr20) / w) & (br >= b))
                idx = np.flatnonzero(sig)
                for s in ATR_STOP:
                    for fl in FLOOR_PT:
                        name = "w=%d d=%.1f b=%.1f s=%.1f f=%d" % (w, d, b, s, int(fl))
                        base_r, mfe_r, risks = [], [], []
                        for i in idx:
                            e = i + 1          # SIGNAL bar tagged, NEXT BAR'S OPEN filled
                            if e >= n or flat_bar[i] < e or codes[e] != codes[i]:
                                continue
                            entry_px = o[e]
                            risk = max(s * atr20[i], fl)
                            stop = entry_px - risk
                            xb, xpx, why, mfe_pts = session_exit(
                                h, lo, c, entry_px, e, stop, flat_bar[i])
                            base_r.append((xpx - entry_px) / risk)
                            mfe_r.append(mfe_pts / risk)
                            risks.append(risk)
                        cnt = len(base_r)
                        a_yr = cnt / years if years else 0.0
                        if cnt < 2:
                            print(format(name, "<34") + format(usd(cnt), ">7")
                                  + format(format(a_yr, ".1f"), ">7")
                                  + format("-", ">9") * 7 + format("NO TRADES", ">16"))
                            report.append({"cell": name, "trades": cnt, "verdict": "NO TRADES"})
                            continue
                        bro = float(np.mean(base_r)); sd = float(np.std(base_r, ddof=1))
                        ceil_r = float(np.mean(mfe_r)); rk = float(np.mean(risks))
                        cr = COST_REAL / rk
                        m = mde(sd, cnt)
                        if ceil_r <= cr:
                            v = "HARD CLOSE"
                        elif m is None or (ceil_r - cr) <= m:
                            v = "powered-dead"
                        elif a_yr < TRADES_A_YEAR_FLOOR:
                            v = "THIN n/yr"
                        else:
                            v = "OPEN"
                        report.append({
                            "cell": name, "w": w, "d": d, "b": b, "s": s, "floor_pt": fl,
                            "trades": cnt, "a_year": round(a_yr, 1), "mean_risk_pt": round(rk, 2),
                            "cost_R_real": round(cr, 4), "cost_R_house": round(COST_HOUSE / rk, 4),
                            "cost_R_slip": round(COST_SLIP / rk, 4),
                            "baseline_R": round(bro, 4), "sd_R": round(sd, 4),
                            "mde_R": None if m is None else round(m, 4),
                            "ceiling_mfe_R": round(ceil_r, 4), "verdict": v})
                        print(format(name, "<34") + format(usd(cnt), ">7")
                              + format(format(a_yr, ".1f"), ">7")
                              + format(format(rk, ".2f"), ">9")
                              + format(format(cr, ".4f"), ">8")
                              + format(format(bro, ".4f"), ">9")
                              + format(format(sd, ".3f"), ">7")
                              + format("-" if m is None else format(m, ".4f"), ">7")
                              + format(format(ceil_r, ".4f"), ">8")
                              + format(v, ">16"))

    v = [r["verdict"] for r in report]
    print("\nVERDICT COUNTS: %s" % json.dumps({k: v.count(k) for k in sorted(set(v))}))
    if "OPEN" not in v:
        print("NO CELL IS OPEN - THE ROUND CLOSES AT DRAFT, no trial budget spent.")
    p = os.path.join(OUT, "gate.json")
    with open(p, "w", encoding="utf-8") as f:
        json.dump({"prereg_body_sha": PREREG_BODY_SHA, "years": round(years, 2),
                   "stretch": [str(tsi[0].date()), str(tsi[-1].date())],
                   "cost_pts": {"real": COST_REAL, "house": COST_HOUSE, "slip": COST_SLIP},
                   "rows": report}, f, indent=1)
    print("wrote " + p)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
