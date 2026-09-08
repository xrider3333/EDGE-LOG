"""
tools/leg_scan_ideas.py - NEW-MECHANISM LEG SCAN (not a validate, nothing gets crowned).

The four existing families (ORB, NOISE, ENGU-Q, NQDIP) have been mined out: every
in-sample filter added to them dies out of sample. This file does not re-cut them.
It tests mechanisms that use a DIFFERENT trigger or DIFFERENT information - the
opening gap, scheduled event days, the NQ-vs-ES strength spread, and the last hour
of the day - against a pre-registered grid, an honest calendar split, and fixed
exits. Every cell is reported, not just the good ones.

===============================================================================
PRE-REGISTRATION  (written before the first run; unchanged after seeing results)
===============================================================================
WINDOW      2010-06-07 .. 2025-06-30.  2025-07-01 onward is a LOCKBOX: this file
            never loads a bar from it (enforced in code and in the tests).
SPLIT       DISCOVERY = the first 60% of that window by CALENDAR DATE.
            HOLDOUT   = the remaining 40%.  No re-splitting, no re-shuffling.
GRIDS       Fixed below, per mechanism. EVERY cell is reported, never only the best.
SCORE       Per cell, computed SEPARATELY on discovery and on holdout:
              n        = number of trades
              net $    = total profit/loss in dollars, after costs
              PF       = profit factor = (dollars won) / (dollars lost)
              maxDD $  = largest peak-to-trough fall of the running total, in dollars
              MAR      = (net $ / years in that segment) / maxDD $   (annualised MAR)
              trades/yr= n / years in that segment
              EV R     = average trade in R, where R = the average LOSING trade in $
LEAD BAR    A cell is a LEAD only if DISCOVERY and HOLDOUT each show
              PF >= 1.25  AND  MAR >= 1.0  AND  n >= 80.
            Anything else is NOT a lead, however pretty one half looks.
EXITS       Fixed per mechanism, never searched:
              stop  = 1.5 x the 14-bar ATR of the 5-minute chart at the entry bar,
                      unless a mechanism states its own stop (only M2a does);
              time exit as stated per mechanism;
              flat at 16:00 ET always (the 15:55 bar's close).
            Inside a bar the STOP is assumed to hit before any target (pessimistic),
            and a bar that OPENS through the stop fills at that open, not at the stop.
COSTS       0.533 NQ points round trip x $20/point = $10.66 per trade, one contract.
YEAR VIEW   (M5) Year-by-year net dollars is printed for every cell, in discovery and
            in holdout, so a cell that is really one lucky year is visible on sight.
===============================================================================

MECHANISMS
  M1 OPENING GAP    gap = the 09:30 open minus the prior day's regular-hours close,
                    divided by the prior 20 days' average daily range (ADR20).
                    (a) FADE  : |gap| >= g and the first 5-minute bar closes back
                        toward the prior close -> trade toward the gap fill at 09:35,
                        target = the prior close (a full fill), time exit 11:00.
                    (b) GO-WITH: |gap| >= g and the first bar extends the gap ->
                        trade with the gap at 09:35, time exit 12:00.
                    g in {0.3, 0.5, 0.8}. Each also split by whether the OVERNIGHT
                    session (NQ 5m ETH master, prior 18:00 -> 09:30) had already
                    traded back more than half of the gap before the open.
  M2 EVENT DAYS     (a) FOMC 2pm : the 14:00-14:30 range; if the 14:30 bar CLOSES
                        beyond it, enter that way at 14:35, stop = the range's other
                        side, hold to 15:55.
                    (b) OPEX     : third Friday; at 10:30 fade the first hour's move
                        back toward the prior close, target = prior close, exit 15:00.
                    (c) MONTH-END: buy at 09:35 on the last 2 trading days of a month,
                        exit 15:55; and separately the first 2 trading days.
                    Small samples by construction - the n is stated for each.
  M3 NQ vs ES       At 10:30, spread = NQ's first-hour % return minus ES's.
                    (a) CONTINUATION: spread >= s -> buy NQ; <= -s -> short NQ; 15:55.
                    (b) MEAN-REVERSION: the same thresholds, opposite direction.
                    s in {0.20%, 0.35%, 0.50%}. Repeated with the PRIOR FULL DAY's
                    NQ-minus-ES close-to-close return, entering at 09:35 instead.
  M4 LAST HOUR      At 15:00, close-position = where the last price sits inside the
                    day's 09:30-14:55 high-low range (1.0 = at the high, 0 = at the low).
                    >= 0.8 -> buy, <= 0.2 -> sell, exit 15:55; only on days whose range
                    is at least m x ADR20, m in {1.0, 1.5, 2.0}. Fade = same, opposite.
  M5 INFORMATION    Not a leg - the year-by-year net printed for every cell above.

OUTPUT   prints a table; writes docs/anatomy/LEG_SCAN_IDEAS.md
USAGE    python tools/leg_scan_ideas.py            (a few minutes on 5m data)
         python tools/leg_scan_ideas.py --quick    (2013-2016 only, for smoke tests)
"""
import os
import sys
import argparse
import datetime as _dt

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from tools.feature_board import load  # noqa: E402  (shared master loader)

# -- pre-registered constants (do not edit after the first run) ---------------
WINDOW_FROM = "2010-06-07"
WINDOW_TO = "2025-06-30"
LOCKBOX_FROM = "2025-07-01"          # never loaded by this file
DISCOVERY_FRACTION = 0.60
POINT_VALUE = 20.0                   # $ per NQ point, one contract
COST_POINTS = 0.533                  # round-trip slippage+commission in NQ points
COST_DOLLARS = COST_POINTS * POINT_VALUE
ATR_LEN = 14
STOP_ATR_MULT = 1.5
LEAD_PF = 1.25
LEAD_MAR = 1.0
LEAD_N = 80
GAP_GRID = (0.3, 0.5, 0.8)
RS_GRID = (0.20, 0.35, 0.50)         # percent
RANGE_GRID = (1.0, 1.5, 2.0)         # multiples of ADR20

FOMC_CSV = os.path.join(ROOT, "tools", "data", "fomc_dates.csv")
OUT_MD = os.path.join(ROOT, "docs", "anatomy", "LEG_SCAN_IDEAS.md")


# ============================================================================
# split
# ============================================================================
def split_bounds(window_from=WINDOW_FROM, window_to=WINDOW_TO,
                 fraction=DISCOVERY_FRACTION):
    """Calendar 60/40 split of the pre-registered window.

    Returns (disc_start, disc_end, hold_start, hold_end) as datetime.date.
    hold_end is always < LOCKBOX_FROM: the last 12 months are never seen.
    """
    a = pd.Timestamp(window_from).date()
    b = pd.Timestamp(window_to).date()
    span = (b - a).days
    cut = a + _dt.timedelta(days=int(round(span * fraction)))
    return a, cut, cut + _dt.timedelta(days=1), b


def segment_years(start, end):
    return max((end - start).days / 365.25, 1e-9)


# ============================================================================
# metrics
# ============================================================================
def score(trades, seg_start, seg_end):
    """trades = list of dicts with keys pnl (dollars, after cost) and date.

    Every number here is defined in the pre-registration block at the top.
    """
    out = {"n": 0, "net": 0.0, "pf": float("nan"), "dd": 0.0,
           "mar": float("nan"), "tpy": 0.0, "evr": float("nan"),
           "years": segment_years(seg_start, seg_end)}
    if not trades:
        return out
    t = sorted(trades, key=lambda r: r["date"])
    p = np.array([r["pnl"] for r in t], float)
    eq = np.concatenate([[0.0], np.cumsum(p)])
    peak = np.maximum.accumulate(eq)
    dd = float(np.max(peak - eq))
    wins = p[p > 0].sum()
    losses = -p[p < 0].sum()
    losers = p[p < 0]
    out["n"] = len(p)
    out["net"] = float(p.sum())
    out["pf"] = float(wins / losses) if losses > 0 else float("inf")
    out["dd"] = dd
    out["tpy"] = len(p) / out["years"]
    out["mar"] = float((out["net"] / out["years"]) / dd) if dd > 0 else float("nan")
    if len(losers):
        out["evr"] = float(p.mean() / abs(losers.mean()))
    return out


def year_net(trades):
    d = {}
    for r in trades:
        y = r["date"].year
        d[y] = d.get(y, 0.0) + r["pnl"]
    return dict(sorted(d.items()))


def is_lead(d, h):
    for s in (d, h):
        if s["n"] < LEAD_N:
            return False
        if not (s["pf"] == s["pf"]) or s["pf"] < LEAD_PF:
            return False
        if not (s["mar"] == s["mar"]) or s["mar"] < LEAD_MAR:
            return False
    return True


# ============================================================================
# day frames
# ============================================================================
class DayBook:
    """Per-trading-day 5-minute arrays plus the causal daily context each
    mechanism needs (prior close, ADR20, overnight retrace flag)."""

    def __init__(self, rth, eth=None):
        rth = rth.copy()
        rth["_date"] = rth["_dt"].dt.date
        rth["_hm"] = rth["_dt"].dt.strftime("%H:%M")
        # 14-bar ATR of the 5-minute chart, continuous across days
        h, l, c = rth["high"].values, rth["low"].values, rth["close"].values
        pc = np.concatenate([[c[0]], c[:-1]])
        tr = np.maximum(h - l, np.maximum(np.abs(h - pc), np.abs(l - pc)))
        rth["_atr"] = pd.Series(tr).rolling(ATR_LEN, min_periods=ATR_LEN).mean().values

        self.dates = []
        self.day = {}
        for d, g in rth.groupby("_date", sort=True):
            g = g.reset_index(drop=True)
            self.dates.append(d)
            self.day[d] = {
                "idx": {hm: i for i, hm in enumerate(g["_hm"])},
                "o": g["open"].values.astype(float),
                "h": g["high"].values.astype(float),
                "l": g["low"].values.astype(float),
                "c": g["close"].values.astype(float),
                "atr": g["_atr"].values.astype(float),
            }
        closes = np.array([self.day[d]["c"][-1] for d in self.dates])
        opens = np.array([self.day[d]["o"][0] for d in self.dates])
        rng = np.array([self.day[d]["h"].max() - self.day[d]["l"].min()
                        for d in self.dates])
        adr20 = pd.Series(rng).rolling(20, min_periods=20).mean().shift(1).values
        for i, d in enumerate(self.dates):
            e = self.day[d]
            e["prior_close"] = float(closes[i - 1]) if i > 0 else float("nan")
            e["open0930"] = float(opens[i])
            e["adr20"] = float(adr20[i]) if adr20[i] == adr20[i] else float("nan")
            e["prior_ret"] = (float(closes[i - 1] / closes[i - 2] - 1.0)
                              if i > 1 else float("nan"))
            e["on_retraced"] = None
        self._add_overnight(eth)

    def _add_overnight(self, eth):
        """Did the overnight session already trade back more than half of the gap?

        The ETH master's trading day rolls at 18:00 ET, so the bars stamped with a
        given date are that date's overnight session plus its day session. Only the
        bars before 09:30 are used - all of it known at the open.
        """
        if eth is None:
            return
        e = eth.copy()
        e["_d"] = (e["_dt"] + pd.Timedelta(hours=6)).dt.date
        e = e[e["_dt"].dt.strftime("%H:%M") < "09:30"]
        lo = e.groupby("_d")["low"].min()
        hi = e.groupby("_d")["high"].max()
        for d in self.dates:
            ent = self.day[d]
            pc, op = ent["prior_close"], ent["open0930"]
            if pc != pc or d not in lo.index:
                continue
            gap = op - pc
            if abs(gap) < 1e-9:
                continue
            half = pc + 0.5 * gap
            ent["on_retraced"] = bool(lo[d] <= half) if gap > 0 else bool(hi[d] >= half)

    def gap_units(self, d):
        """The opening gap in units of the prior 20 days' average daily range."""
        e = self.day[d]
        return gap_units_from(e["open0930"], e["prior_close"], e["adr20"])

    def i(self, d, hm):
        return self.day[d]["idx"].get(hm)

    def price_at(self, d, hm):
        j = self.i(d, hm)
        return None if j is None else float(self.day[d]["o"][j])


def gap_units_from(open0930, prior_close, adr20):
    """The opening gap measured in units of the prior 20-day average daily range.

    Positive = the session opened above yesterday's regular-hours close.
    Returns nan when the inputs are not yet known (first 20 days, or a zero range).
    """
    if adr20 is None or adr20 != adr20 or adr20 <= 0:
        return float("nan")
    if prior_close != prior_close or open0930 != open0930:
        return float("nan")
    return (open0930 - prior_close) / adr20


def range_breakout_dir(range_hi, range_lo, break_close):
    """+1 if the bar CLOSED above the range, -1 if below, 0 if inside it."""
    if break_close > range_hi:
        return 1
    if break_close < range_lo:
        return -1
    return 0


# ============================================================================
# trade simulation
# ============================================================================
def simulate(book, d, entry_hm, direction, exit_hm, stop_px=None, target_px=None,
             stop_atr_mult=STOP_ATR_MULT):
    """One trade. Enters at the OPEN of entry_hm's bar, leaves at the stop, the
    target, or the close of the bar that ends at exit_hm - whichever comes first.
    The stop is assumed to win any same-bar race with the target."""
    e = book.day[d]
    ei = book.i(d, entry_hm)
    if ei is None:
        return None
    xi = book.i(d, exit_hm)
    if xi is None:                      # early close: fall back to the last bar
        xi = len(e["c"]) - 1
    else:
        xi -= 1                         # exit_hm is a clock time = that bar's close
    if xi < ei:
        return None
    atr = e["atr"][ei]
    if atr != atr or atr <= 0:
        return None
    entry = float(e["o"][ei])
    if stop_px is None:
        stop_px = entry - direction * stop_atr_mult * atr
    exit_px = float(e["c"][xi])
    for j in range(ei, xi + 1):
        o, hi, lo = e["o"][j], e["h"][j], e["l"][j]
        if direction > 0:
            if o <= stop_px:
                exit_px = float(o); break
            if lo <= stop_px:
                exit_px = float(stop_px); break
            if target_px is not None and hi >= target_px:
                exit_px = float(target_px); break
        else:
            if o >= stop_px:
                exit_px = float(o); break
            if hi >= stop_px:
                exit_px = float(stop_px); break
            if target_px is not None and lo <= target_px:
                exit_px = float(target_px); break
    pnl = direction * (exit_px - entry) * POINT_VALUE - COST_DOLLARS
    return {"date": d, "pnl": float(pnl)}


# ============================================================================
# mechanisms - each returns {cell_name: [trades]}
# ============================================================================
def m1_gap(book):
    cells = {}
    for g in GAP_GRID:
        for mode in ("FADE", "GOWITH"):
            for sub in ("all", "on_retraced", "not_retraced"):
                cells["M1 %s g=%.1f %s" % (mode, g, sub)] = []
    for d in book.dates:
        e = book.day[d]
        gu = book.gap_units(d)
        if gu != gu or abs(gu) < min(GAP_GRID):
            continue
        i0 = book.i(d, "09:30")
        if i0 is None or book.i(d, "09:35") is None:
            continue
        bar0_up = e["c"][i0] > e["o"][i0]
        gap_up = gu > 0
        extends = (bar0_up == gap_up)
        retr = e["on_retraced"]
        for g in GAP_GRID:
            if abs(gu) < g:
                continue
            for mode in ("FADE", "GOWITH"):
                if mode == "FADE":
                    if extends:
                        continue
                    direction = -1 if gap_up else 1
                    tr = simulate(book, d, "09:35", direction, "11:00",
                                  target_px=e["prior_close"])
                else:
                    if not extends:
                        continue
                    direction = 1 if gap_up else -1
                    tr = simulate(book, d, "09:35", direction, "12:00")
                if tr is None:
                    continue
                cells["M1 %s g=%.1f all" % (mode, g)].append(tr)
                if retr is True:
                    cells["M1 %s g=%.1f on_retraced" % (mode, g)].append(tr)
                elif retr is False:
                    cells["M1 %s g=%.1f not_retraced" % (mode, g)].append(tr)
    return cells


def _fomc_dates():
    if not os.path.exists(FOMC_CSV):
        return set()
    rows = pd.read_csv(FOMC_CSV, comment="#")
    col = rows.columns[0]
    return set(pd.to_datetime(rows[col], errors="coerce").dropna().dt.date)


def _third_friday(d):
    return d.weekday() == 4 and 15 <= d.day <= 21


def m2_events(book):
    cells = {"M2a FOMC 14:30 break": [], "M2b OPEX fade 1st hour": [],
             "M2c MONTH-END last2 long": [], "M2c MONTH-START first2 long": []}
    fomc = _fomc_dates()
    dates = book.dates
    by_month = {}
    for i, d in enumerate(dates):
        by_month.setdefault((d.year, d.month), []).append(i)
    last2, first2 = set(), set()
    for _k, idxs in by_month.items():
        for i in idxs[-2:]:
            last2.add(dates[i])
        for i in idxs[:2]:
            first2.add(dates[i])

    for d in dates:
        e = book.day[d]
        if d in fomc:
            i_a, i_b = book.i(d, "14:00"), book.i(d, "14:30")
            if i_a is not None and i_b is not None and i_b > i_a:
                rh = float(e["h"][i_a:i_b].max())
                rl = float(e["l"][i_a:i_b].min())
                direction = range_breakout_dir(rh, rl, float(e["c"][i_b]))
                if direction != 0:
                    stop = rl if direction > 0 else rh
                    tr = simulate(book, d, "14:35", direction, "16:00", stop_px=stop)
                    if tr:
                        cells["M2a FOMC 14:30 break"].append(tr)
        if _third_friday(d):
            p1030 = book.price_at(d, "10:30")
            if p1030 is not None and e["prior_close"] == e["prior_close"]:
                move = p1030 - e["open0930"]
                if abs(move) > 0:
                    direction = -1 if move > 0 else 1
                    tr = simulate(book, d, "10:30", direction, "15:00",
                                  target_px=e["prior_close"])
                    if tr:
                        cells["M2b OPEX fade 1st hour"].append(tr)
        if d in last2:
            tr = simulate(book, d, "09:35", 1, "16:00")
            if tr:
                cells["M2c MONTH-END last2 long"].append(tr)
        if d in first2:
            tr = simulate(book, d, "09:35", 1, "16:00")
            if tr:
                cells["M2c MONTH-START first2 long"].append(tr)
    return cells


def m3_relstrength(book, es_book):
    cells = {}
    for s in RS_GRID:
        cells["M3a 1sthr CONT s=%.2f" % s] = []
        cells["M3b 1sthr REV  s=%.2f" % s] = []
        cells["M3c prevday CONT s=%.2f" % s] = []
        cells["M3d prevday REV  s=%.2f" % s] = []
    for d in book.dates:
        if d not in es_book.day:
            continue
        e, ee = book.day[d], es_book.day[d]
        nq_o, es_o = e["open0930"], ee["open0930"]
        nq_p, es_p = book.price_at(d, "10:30"), es_book.price_at(d, "10:30")
        if nq_p is not None and es_p is not None and nq_o > 0 and es_o > 0:
            spread = (nq_p / nq_o - 1.0) * 100.0 - (es_p / es_o - 1.0) * 100.0
            for s in RS_GRID:
                if abs(spread) >= s:
                    sgn = 1 if spread > 0 else -1
                    for key, direction in (("M3a 1sthr CONT s=%.2f" % s, sgn),
                                           ("M3b 1sthr REV  s=%.2f" % s, -sgn)):
                        tr = simulate(book, d, "10:30", direction, "16:00")
                        if tr:
                            cells[key].append(tr)
        pr_n, pr_e = e["prior_ret"], ee["prior_ret"]
        if pr_n == pr_n and pr_e == pr_e:
            spread2 = (pr_n - pr_e) * 100.0
            for s in RS_GRID:
                if abs(spread2) >= s:
                    sgn = 1 if spread2 > 0 else -1
                    for key, direction in (("M3c prevday CONT s=%.2f" % s, sgn),
                                           ("M3d prevday REV  s=%.2f" % s, -sgn)):
                        tr = simulate(book, d, "09:35", direction, "16:00")
                        if tr:
                            cells[key].append(tr)
    return cells


def m4_lasthour(book):
    cells = {}
    for m in RANGE_GRID:
        cells["M4a LASTHR WITH rng>=%.1fADR" % m] = []
        cells["M4b LASTHR FADE rng>=%.1fADR" % m] = []
    for d in book.dates:
        e = book.day[d]
        i15 = book.i(d, "15:00")
        if i15 is None or i15 < 1:
            continue
        hi = float(e["h"][:i15].max())
        lo = float(e["l"][:i15].min())
        last = float(e["c"][i15 - 1])
        if hi - lo <= 0:
            continue
        pos = (last - lo) / (hi - lo)
        if not (pos >= 0.8 or pos <= 0.2):
            continue
        adr = e["adr20"]
        if adr != adr or adr <= 0:
            continue
        rng_units = (hi - lo) / adr
        sgn = 1 if pos >= 0.8 else -1
        for m in RANGE_GRID:
            if rng_units < m:
                continue
            for key, direction in (("M4a LASTHR WITH rng>=%.1fADR" % m, sgn),
                                   ("M4b LASTHR FADE rng>=%.1fADR" % m, -sgn)):
                tr = simulate(book, d, "15:00", direction, "16:00")
                if tr:
                    cells[key].append(tr)
    return cells


# ============================================================================
# report
# ============================================================================
def fmt(v, nd=2):
    if v is None or (isinstance(v, float) and v != v):
        return "n/a"
    if v == float("inf"):
        return "inf"
    return ("%%.%df" % nd) % v


HDR = "    n |      net $ |     PF |   maxDD $ |     MAR | tr/yr |  EV R"


def row(s):
    return "%5d | %10.0f | %6s | %9.0f | %7s | %5s | %6s" % (
        s["n"], s["net"], fmt(s["pf"]), s["dd"],
        fmt(s["mar"]), fmt(s["tpy"], 1), fmt(s["evr"]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true",
                    help="2013-2016 only, for smoke tests (NOT a valid scan)")
    args = ap.parse_args()

    wf, wt = (WINDOW_FROM, WINDOW_TO) if not args.quick else ("2013-01-01", "2016-12-31")
    d0, d1, h0, h1 = split_bounds(wf, wt)
    assert h1 < pd.Timestamp(LOCKBOX_FROM).date(), "holdout must not reach the lockbox"

    print("window %s .. %s   (lockbox %s+ never loaded)" % (wf, wt, LOCKBOX_FROM))
    print("discovery %s .. %s   holdout %s .. %s" % (d0, d1, h0, h1))
    print("loading masters ...")
    nq = load("NQ", "5m", "RTH", wf, wt)
    es = load("ES", "5m", "RTH", wf, wt)
    eth = load("NQ", "5m", "ETH", wf, wt)
    for df in (nq, es, eth):
        assert df["_dt"].dt.date.max() < pd.Timestamp(LOCKBOX_FROM).date()

    book = DayBook(nq, eth)
    es_book = DayBook(es)
    print("NQ days %d   ES days %d" % (len(book.dates), len(es_book.dates)))

    cells = {}
    print("M1 opening gap ...")
    cells.update(m1_gap(book))
    print("M2 event days ...")
    cells.update(m2_events(book))
    print("M3 NQ vs ES ...")
    cells.update(m3_relstrength(book, es_book))
    print("M4 last hour ...")
    cells.update(m4_lasthour(book))

    results = []
    for name in sorted(cells):
        tr = cells[name]
        dsc = [t for t in tr if d0 <= t["date"] <= d1]
        hld = [t for t in tr if h0 <= t["date"] <= h1]
        sd, sh = score(dsc, d0, d1), score(hld, h0, h1)
        results.append({"name": name, "d": sd, "h": sh,
                        "lead": is_lead(sd, sh),
                        "yd": year_net(dsc), "yh": year_net(hld)})

    print("\n%-32s | %s" % ("CELL / segment", HDR))
    print("-" * 118)
    for r in results:
        flag = "   <<< LEAD" if r["lead"] else ""
        print("%-27s DISC | %s%s" % (r["name"], row(r["d"]), flag))
        print("%-27s HOLD | %s" % ("", row(r["h"])))
    leads = [r for r in results if r["lead"]]
    print("\nLEADS: %d of %d cells" % (len(leads), len(results)))
    for r in leads:
        print("  " + r["name"])

    write_md(results, wf, wt, d0, d1, h0, h1)
    print("\nwrote %s" % OUT_MD)


def _near_miss_score(r):
    """How far a cell fell short of the LEAD bar (0 = cleared it). Lower = closer."""
    pen = 0.0
    for s in (r["d"], r["h"]):
        pf = s["pf"] if s["pf"] == s["pf"] else 0.0
        mar = s["mar"] if s["mar"] == s["mar"] else 0.0
        pen += max(0.0, LEAD_PF - min(pf, 5.0)) * 2.0
        pen += max(0.0, LEAD_MAR - min(mar, 5.0))
        pen += max(0.0, (LEAD_N - s["n"]) / LEAD_N)
    return pen


def _best_year_share(ynet):
    """Share of a half's net dollars contributed by its single best calendar year."""
    if not ynet:
        return "n/a"
    tot = sum(ynet.values())
    if tot <= 0:
        return "not profitable"
    best_year = max(ynet, key=lambda k: ynet[k])
    return "%.0f%% from %d" % (100.0 * ynet[best_year] / tot, best_year)


def write_md(results, wf, wt, d0, d1, h0, h1):
    os.makedirs(os.path.dirname(OUT_MD), exist_ok=True)
    L = []
    L.append("# LEG SCAN - new-mechanism ideas (a SCAN, not a validate)\n")
    L.append("_Generated %s by `tools/leg_scan_ideas.py`. Nothing here is crowned._\n"
             % _dt.date.today())
    L.append("Run window %s .. %s. Discovery %s .. %s, holdout %s .. %s.\n"
             % (wf, wt, d0, d1, h0, h1))
    L.append("## Pre-registration (written before the first run)\n")
    L.append("```\n" + __doc__.strip() + "\n```\n")
    L.append("## Plain-English glossary\n")
    L.append("- **Discovery / holdout** - the window is cut in two by date. Rules are")
    L.append("  looked at on the first 60% (discovery); the last 40% (holdout) is the")
    L.append("  fresh data that decides whether the idea was real.")
    L.append("- **Lockbox** - 2025-07 onward. Not loaded at all here, kept for later.")
    L.append("- **PF (profit factor)** - dollars won divided by dollars lost. Below 1.0")
    L.append("  the rule loses money.")
    L.append("- **maxDD** - the deepest peak-to-trough fall of the running total, in dollars.")
    L.append("- **MAR** - average dollars per year divided by maxDD: what you earn per year")
    L.append("  for each dollar of worst-case pain. Higher is better; 1.0 is the bar here.")
    L.append("- **EV R** - the average trade expressed in units of the average LOSING trade.")
    L.append("  0.10 means a typical trade earns a tenth of a typical loss.")
    L.append("- **ADR20** - the average daily high-to-low range over the prior 20 days.")
    L.append("- **LEAD** - discovery AND holdout both clear PF>=1.25, MAR>=1.0, n>=80.\n")

    leads = [r for r in results if r["lead"]]
    L.append("## Verdict\n")
    if leads:
        L.append("**%d LEAD cell(s)** out of %d.\n" % (len(leads), len(results)))
    else:
        L.append("**No leads.** Not one of the %d cells cleared the pre-registered bar "
                 "on discovery and holdout at the same time.\n" % len(results))

    L.append("## All cells (every one, not just the good ones)\n")
    L.append("| cell | seg | n | net $ | PF | maxDD $ | MAR | tr/yr | EV R | LEAD |")
    L.append("|---|---|---:|---:|---:|---:|---:|---:|---:|:--:|")
    for r in results:
        for tag, s in (("DISC", r["d"]), ("HOLD", r["h"])):
            L.append("| %s | %s | %d | %.0f | %s | %.0f | %s | %s | %s | %s |" % (
                r["name"], tag, s["n"], s["net"], fmt(s["pf"]), s["dd"],
                fmt(s["mar"]), fmt(s["tpy"], 1), fmt(s["evr"]),
                ("YES" if r["lead"] else "-") if tag == "DISC" else ""))
    L.append("")

    L.append("## M5 - year-by-year net dollars, every cell\n")
    L.append("One lucky year is the commonest way a scan fools itself; D = a discovery")
    L.append("year, H = a holdout year.\n")
    for r in results:
        yrs = sorted(set(list(r["yd"]) + list(r["yh"])))
        if not yrs:
            L.append("- **%s** - no trades." % r["name"])
            continue
        parts = []
        for y in yrs:
            if y in r["yd"]:
                parts.append("%dD %+.0f" % (y, r["yd"][y]))
            if y in r["yh"]:
                parts.append("%dH %+.0f" % (y, r["yh"][y]))
        L.append("- **%s** - %s" % (r["name"], "  ".join(parts)))
    L.append("")

    if leads:
        L.append("## Lead year tables\n")
        for r in leads:
            L.append("### %s\n" % r["name"])
            L.append("| year | segment | net $ |")
            L.append("|---|---|---:|")
            for y, v in r["yd"].items():
                L.append("| %d | discovery | %.0f |" % (y, v))
            for y, v in r["yh"].items():
                L.append("| %d | holdout | %.0f |" % (y, v))
            L.append("")

    near = sorted([r for r in results if not r["lead"]], key=_near_miss_score)[:8]
    L.append("## Closest misses\n")
    L.append("\"best year\" = the share of that half's net dollars that came from its")
    L.append("single best calendar year. A high share means the cell is one good year")
    L.append("wearing a fifteen-year costume.\n")
    for r in near:
        L.append("- **%s** - discovery PF %s / MAR %s / n %d / net %.0f (best year %s); "
                 "holdout PF %s / MAR %s / n %d / net %.0f (best year %s)."
                 % (r["name"], fmt(r["d"]["pf"]), fmt(r["d"]["mar"]), r["d"]["n"],
                    r["d"]["net"], _best_year_share(r["yd"]),
                    fmt(r["h"]["pf"]), fmt(r["h"]["mar"]),
                    r["h"]["n"], r["h"]["net"], _best_year_share(r["yh"])))
    L.append("")

    L.append("## Blunt summary\n")
    both = len([r for r in results if r["d"]["net"] > 0 and r["h"]["net"] > 0])
    neither = len([r for r in results if r["d"]["net"] <= 0 and r["h"]["net"] <= 0])
    L.append("- %d of %d cells made money in BOTH halves; %d in neither."
             % (both, len(results), neither))
    if leads:
        L.append("- Leads: " + ", ".join(r["name"] for r in leads) + ".")
        L.append("- A lead is a candidate for a fenced strategy file and a real validate,")
        L.append("  not an edge. It has not seen the lockbox and has not been walk-forwarded.")
    else:
        L.append("- Nothing here is tradeable as written. None of these mechanisms survived")
        L.append("  its own holdout at the bar that was set before looking.")
    L.append("- Costs are $10.66 a round trip, one contract. Several cells are profitable")
    L.append("  before costs and negative after; that is the whole story for the thin ones.")
    L.append("- The event cells (FOMC, OPEX, month turn) have small samples by")
    L.append("  construction and mostly cannot reach n>=80 in both halves; their numbers")
    L.append("  are reported for information, not as candidates.")
    with open(OUT_MD, "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")


if __name__ == "__main__":
    main()
