# AUGUR-SOURCE: claude-review
"""MISC EXPCAL 1.0 - "expiry-calendar long": long 1 NQ on rule-computed calendar days, flat by 15:55 ET.

READ THIS FIRST - WHAT THE HARNESS SAID (opus hunt strategy 58, verdict cell 58c, WF 2016-07-01 .. 2025-06-30):
  * VERDICT IN THE HUNT: FAIL ("Route B missed"). It is in the engine only because the owner's loose screen lets a
    profitable, 20-trades-a-year leg be judged by the engine. THE ENGINE RUN DECIDES: a WEAK or a FAIL takes this leg
    out of every book row.
  * LUCK: the book-add block bootstrap gave P(lift) 0.68 against a bar of 0.95, on 5 of 8 folds (bar 6). The
    random-day control (200 draws of the same number of NQ days per year, long 09:30 -> 15:55) put the real net per
    trade at the 83rd percentile against a bar of the 95th: THE CALENDAR DAYS ARE NOT DISTINGUISHABLE FROM RANDOM DAYS
    AFTER 2016. (The build brief quoted "68th percentile (P 0.68, bar 0.95)" for the random-day control; RESULTS.md
    and results.json say 83rd for that control and 0.683 for P(lift). Both fail their bar.)
  * ONE-EPISODE SHAPE: the 10 best days = 105 pct of the WF net (the other 247 trades lose money between them). Net
    t 1.49 (halves 0.73 / 1.30). By calendar year, $: 2016H2 -780, 2017 -908, 2018 +8,936, 2019 +4,712, 2020 -918,
    2021 +17,187, 2022 -6,579, 2023 +13,982, 2024 +8,541, 2025H1 +5,299.
  * SIZE: 257 trades = 28.6 a year, +$49,470.38 = $5,499 a year at 1 NQ, max drawdown about $19.7k.
  * NOT A BLIND READ: the hunt read 2010-06 .. 2025-06 on these exact days. The 2025-07 .. 2026-06 lockbox was never
    read by the hunt or by the build of this file (every parity run and test stops at 2025-06-30).
  * IT IS A LONG-INDEX INTRADAY SEAT: it loses on the same down-trend days as a long book (daily correlation with
    book #463 +0.10).

Provenance: C:/EdgeLog/_anatomy_cache/opus_hunt1109/futures/S58 (PREREG.md, RESULTS.md, s58_run.py build() with
excl_fomc=True, kind='union'; trades_58c.csv). Mechanism (prereg): calendar-predictable dealer gamma in monthly
option-expiry week, the vol-seller roll on the eve of VIX settlement, holiday inventory flows.

-- The rule (the prereg's; NOTHING is tunable - one config) --------------------------------------------------------
ELIGIBLE SESSION: its last 5m bar is the 15:55 bar, and its 09:30, 14:00 and 15:55 bars exist (all three, on FULL
days too - the harness's test). Every bar must start inside 09:30 .. 15:55 ET (always true on the RTH masters).
FULL day -> BUY at the OPEN of the 09:30 bar, SELL at the OPEN of the 15:55 bar, same session:
  1. OPEXTUE: the Tuesday of the week of the month's third Friday (third Friday - 3 days). Not a session -> no trade.
  2. VIXEVE: S = (third Friday of the NEXT calendar month) - 30 days; settlement = S, or the NYSE session before it
     when S is a closure; VIXEVE = the last NYSE session strictly before settlement that is not a scheduled early
     close (walk back over early closes: 3 July when 4 July is a weekday, the Friday after Thanksgiving, 24 Dec).
  3. PREHOL: the last NYSE session before a weekday full NYSE closure, when that session is not itself a closure.
PM day -> BUY at the OPEN of the 14:00 bar, SELL at the OPEN of the 15:55 bar:
  4. POSTHOL: the first NYSE session after a weekday full NYSE closure, when it is not also a FULL day.
SKIPPED: every FOMC decision day and the NYSE session before it (FULL and PM alike).
Long only, 1 contract, no stop, no target, one trade a day at most, never overnight.
"NYSE closure" = a weekday in session_calendar.closed_days(y) (New Year, Good Friday, Christmas, special closures)
or in session_calendar.holiday_sessions(y) (MLK, Presidents, Memorial, Juneteenth 2022+, 4 July, Labor,
Thanksgiving - CME trades a short session, NYSE is shut). Hurricane Sandy (2012-10-29 / 30, unscheduled) is a
closure but creates no PREHOL / POSTHOL - the prereg's stated choice; the two mourning closures (2018-12-05,
2025-01-09, announced days ahead) do.

THE CALENDAR IS COMPUTED HERE, FROM DATES ONLY: augur_engine.session_calendar + tools/data/fomc_dates.txt, the
harness's two sources. No bar price enters the day selection, and no bar at all enters the four day sets or the FOMC
set - they are functions of the calendar date (the bars' first and last YEAR only size the table that is built).
tools/data/fomc_dates.txt is pinned: its sha256 is checked at run time (CRLF folded to LF first, so a Windows and a
Linux checkout agree; the CRLF form hashes to the harness's pin 9cf8e527...b575f - tested) and a mismatch or a
missing file RAISES. No day after the file's last listed decision day (2027-12-08) is traded: past it the FOMC
exclusion cannot be applied.

TRADE <-> BARS: entry bar = the session's 09:30 (or 14:00) bar, exit bar = its 15:55 bar; the trade needs the whole
session inside the job's bars, so a walk-forward slice that starts after 09:30 or ends before the 15:55 bar of a
calendar day takes no trade for it - a slice edge never opens a trade late or closes it early. Nothing is held
through a session close: mark_open_trades returns no marks.

INFORMATION TIMES:
  * which days trade: the exchange calendar (published years ahead) and the Fed's scheduled meeting calendar
    (published the year before). Known at the prior close. The FOMC file was collected on 2026-07-17 from the Fed's
    pages and lists SCHEDULED meetings only; not verifiable here: that no listed meeting was rescheduled after the
    prior close of its eve.
  * entry price: the open of the 09:30 / 14:00 bar (a calendar rule has no signal bar).
  * the 15:55 open is read for the P&L only.
  * ONE CLOCK FACT IS NOT KNOWN AT THE ENTRY: that the session runs to a 15:55 bar (and has a 14:00 bar). It is the
    harness's eligibility test, a fact about bar TIMES, never a price. On a scheduled half day it is known in
    advance; an unscheduled early halt or a data hole after the entry would in life leave a position this file
    never opened. On the masters 2010-06 .. 2025-06 it dropped only scheduled short sessions and one data-hole day
    (2014-12-31); circuit-breaker days (2020-03) reach 15:55 and stay in.
tests/test_misc_expcal.py: truncation, future scramble, price-independence of the calendar, same-day intrabar.

-- Data ----------------------------------------------------------------------------------------------------------
THE JOB'S MASTER = NQ 5m RTH, source db_noadj_rth (the engine's house basis; master id 37). The harness ran on
db_adj_rth (id 73). The P&L is a difference of two opens inside one session, so an additive back-adjust cancels;
tools/misc_expcal_parity.py runs BOTH masters against trades_58c.csv and prints where, if anywhere, they differ.
No side panel: the bars are the only price source.

-- Sizing and costs (INSIDE the plugin: job cost_pts 0, mult 1) - the MISC_AUCSHORT / MISC_GLDNIGHT pattern ---------
points = open(15:55) - open(entry); net points = points - `cost_pts` (0.533, the house NQ round trip); DOLLARS =
net points x `point_value` ($20) in the trade tuple's field 2 (the harness's own order of operations, so the dollars
match to the last bit). PNL_UNITS = "usd". Side +1; entry / exit prices = the two opens.
(MISC_LATE30_1_0, the other NQ leg of this hunt, reports points and lets the job charge cost_pts 0.533 x mult 20
instead. This file follows the two newest calendar legs, as briefed. Consequence: a dollars file is UNSIZED for the
engine's per-stretch DD pct - augur_engine/stretch_dd.py.)

-- Auto-Validate ranges ------------------------------------------------------------------------------------------
NONE. PINNED (min = max = hard bounds): cost_pts, point_value. The rule has no knob the prereg left open, and none
was added to pad a grid: the search space is ONE config. The runner refuses Auto-Validate on such a file ("NO SEARCH
SPACE"); run it as a SINGLE (job type gate_validate, params {}).
"""
import datetime as _dt
import hashlib
import os

import numpy as np
import pandas as pd

from augur_engine import session_calendar as _SC

STRATEGY_NAME = 'MISC EXPCAL 1.0 · expiry-calendar long, NQ 09:30 / 14:00 -> 15:55 (opus hunt 58c)'
DESCRIPTION = ("Long 1 NQ from the 09:30 open to the 15:55 open on the Tuesday of monthly option-expiry week, the "
               "eve of VIX settlement and the session before a holiday closure; from the 14:00 open on the session "
               "after a holiday closure; never on an FOMC day or its eve. Days come from the exchange calendar and "
               "the pinned FOMC list only. Hunt verdict FAIL (random-day control 83rd percentile, P(lift) 0.68): "
               "the engine run decides. Costs inside the plugin -> job cost_pts 0, mult 1.")

_AUGUR_MARKET = {"instrument": "NQ", "timeframe": "5m", "session": "rth", "source": "db_noadj_rth"}

FOMC_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools", "data",
                         "fomc_dates.txt")
FOMC_SHA256_LF = "e27995e3040fd14ec6862d1a0a22729fb021783b18e73e835ee83f6eb0d8acf7"     # the same file with LF line ends (git blob form)
FOMC_SHA256_CRLF = "9cf8e527a141db26bf3330f5a9c78772421c97720ef133535ac73ae4e42b575f"  # the harness's pin (s58_run.py)

SANDY = frozenset((_dt.date(2012, 10, 29), _dt.date(2012, 10, 30)))   # unscheduled: no PREHOL / POSTHOL (prereg)

DEFAULT_PARAMS = {
    "cost_pts": {"default": 0.533, "min": 0.533, "max": 0.533, "hard_min": 0.533, "hard_max": 0.533, "step": 0.001,
                 "type": "float", "label": "Cost (NQ points a round trip)",
                 "tooltip": "Fixed: the house NQ round trip, 0.533 points ($10.66), charged once a trade."},
    "point_value": {"default": 20, "min": 20, "max": 20, "hard_min": 20, "hard_max": 20, "step": 1,
                    "type": "int", "label": "Dollars a point",
                    "tooltip": "Fixed: one NQ contract, $20 a point."},
}

PARAM_GRID_PRESETS = {
    "Short  (the hunt cell 58c - the only config)": {"cost_pts": [0.533], "point_value": [20]},
}

PNL_UNITS = "usd"
ROLL_SIGNAL = "difference"   # no decision reads a price; the P&L is a difference of two opens inside one session

_OPEN_MIN = 570          # 09:30 ET, minute of day: the first RTH 5m bar and the FULL-day entry
_PM_MIN = 840            # the bar stamped 14:00 ET: the PM-day entry
_LAST_SLOT = 955         # 15:55 ET: the last RTH 5m bar of a full session and the exit
_CACHE = {}              # per-process: the FOMC list, the calendar tables, the bar clock


# ------------------------------------------------------------------------------------------------ the FOMC list
def _fomc():
    """The scheduled FOMC decision days of the pinned file, as a sorted tuple of dates. Raises when the file is
    missing or is not the pinned content - a run without the exclusion is a different strategy."""
    if "fomc" in _CACHE:
        return _CACHE["fomc"]
    if not os.path.exists(FOMC_PATH):
        raise RuntimeError("MISC_EXPCAL_1_0: FOMC file %s is missing" % FOMC_PATH)
    with open(FOMC_PATH, "rb") as fh:
        raw = fh.read().replace(b"\r\n", b"\n")
    got = hashlib.sha256(raw).hexdigest()
    if got != FOMC_SHA256_LF:
        raise RuntimeError("MISC_EXPCAL_1_0: FOMC file %s is not the pinned content (LF sha256 %s, pinned %s)"
                           % (FOMC_PATH, got, FOMC_SHA256_LF))
    days = tuple(sorted(_dt.date.fromisoformat(ln.strip()[:10]) for ln in raw.decode("ascii").split("\n")
                        if ln[:2] == "20"))            # the harness's line test
    _CACHE["fomc"] = days
    return days


# ------------------------------------------------------------------------------------------------ the calendar
def _third_fri(y, m):
    d = _dt.date(y, m, 1)
    return d + _dt.timedelta(days=(4 - d.weekday()) % 7 + 14)


def _early_close(d):
    """Scheduled NYSE 13:00 closes (the harness's early_close): the Friday after Thanksgiving, 24 Dec on a weekday,
    3 July on a weekday when 4 July is a weekday."""
    if d.month == 11 and d.weekday() == 4 and (d - _dt.timedelta(days=1)) in _SC.holiday_sessions(d.year):
        return True
    if d.month == 12 and d.day == 24 and d.weekday() < 5:
        return True
    if d.month == 7 and d.day == 3 and d.weekday() < 5 and _dt.date(d.year, 7, 4).weekday() < 5:
        return True
    return False


def _calendar(y0, y1):
    """{'full': set, 'pm': set, 'fomcx': set, 'kind': {ymd: labels}} of yyyymmdd ints for calendar years y0 .. y1,
    plus 'fomc_last'. A function of the two years and the pinned FOMC file ONLY - no bar is an argument. Whether a
    given date is in a set does not depend on y0 / y1 (the tables are built two years wider than asked)."""
    key = (int(y0), int(y1))
    if key in _CACHE.get("cal", {}):
        return _CACHE["cal"][key]
    closures = set()
    for y in range(y0 - 2, y1 + 3):
        closures |= set(_SC.closed_days(y))
        closures |= set(_SC.holiday_sessions(y).keys())
    closures = {d for d in closures if d.weekday() < 5}
    one = _dt.timedelta(days=1)

    def nyse(d):
        return d.weekday() < 5 and d not in closures

    def prev_nyse(d):
        d -= one
        while not nyse(d):
            d -= one
        return d

    def next_nyse(d):
        d += one
        while not nyse(d):
            d += one
        return d

    opextue, vixeve, prehol, posthol = set(), set(), set(), set()
    for y in range(y0 - 1, y1 + 2):
        for m in range(1, 13):
            opextue.add(_third_fri(y, m) - _dt.timedelta(days=3))
            ny, nm = (y + (m == 12), m % 12 + 1)
            s0 = _third_fri(ny, nm) - _dt.timedelta(days=30)
            st = s0 if nyse(s0) else prev_nyse(s0)
            e = prev_nyse(st)
            while _early_close(e):
                e = prev_nyse(e)
            vixeve.add(e)
    lo, hi = _dt.date(y0 - 1, 1, 1), _dt.date(y1 + 1, 12, 31)
    for c in sorted(closures):
        if c in SANDY or c < lo or c > hi:
            continue
        p = prev_nyse(c)
        if p not in closures:                          # always true (prev_nyse never returns a closure); the harness's line
            prehol.add(p)
        posthol.add(next_nyse(c))
    fomc = _fomc()
    fomcx = set(fomc) | {prev_nyse(d) for d in fomc}
    full = opextue | vixeve | prehol
    pm = posthol - full

    def ymd(s):
        return {d.year * 10000 + d.month * 100 + d.day for d in s}

    kind = {}
    for name, s in (("OPEXTUE", opextue), ("VIXEVE", vixeve), ("PREHOL", prehol), ("POSTHOL", posthol)):
        for k in ymd(s):
            kind.setdefault(k, []).append(name)
    last = fomc[-1]
    out = {"full": ymd(full), "pm": ymd(pm), "fomcx": ymd(fomcx), "kind": kind,
           "fomc_last": last.year * 10000 + last.month * 100 + last.day}
    _CACHE.setdefault("cal", {})[key] = out
    return out


# ------------------------------------------------------------------------------------------------ the bar clock
def _clock(index):
    """ET calendar date (yyyymmdd) and minute of day of every bar. The engine hands slices of one master, so the
    largest index seen is converted once and later slices of it are cut from that copy."""
    idx = pd.DatetimeIndex(index)
    ns = idx.asi8
    tz = str(idx.tz)
    c = _CACHE.get("clock")
    n = len(ns)
    if c is not None and c[0] == tz and n:
        a = int(np.searchsorted(c[1], ns[0]))
        if a + n <= len(c[1]) and np.array_equal(c[1][a:a + n], ns):
            return c[2][a:a + n], c[3][a:a + n]
    loc = idx.tz_convert("US/Eastern").tz_localize(None) if idx.tz is not None else idx
    date = (loc.year * 10000 + loc.month * 100 + loc.day).to_numpy().astype(np.int64)
    minute = (loc.hour * 60 + loc.minute).to_numpy().astype(np.int64)
    if (c is None or n > len(c[1])) and n and bool(np.all(ns[1:] > ns[:-1])):
        _CACHE["clock"] = (tz, ns.copy(), date, minute)
    return date, minute


def _sessions(date, minute):
    """Sessions of the bars: (first bar, end bar (exclusive), yyyymmdd, last minute, RTH flag). A session is RTH when
    every bar starts inside 09:30 .. 15:55 ET; anything else (the contract test's 24-hour tape, an ETH feed) is never
    traded."""
    n = len(date)
    cut = np.flatnonzero(date[1:] != date[:-1]) + 1
    starts = np.concatenate([[0], cut]).astype(np.int64)
    ends = np.concatenate([cut, [n]]).astype(np.int64)
    lo = np.minimum.reduceat(minute, starts)
    hi = np.maximum.reduceat(minute, starts)
    return starts, ends, date[starts], minute[ends - 1], (lo >= _OPEN_MIN) & (hi <= _LAST_SLOT)


def _plan(index):
    """THE DAY SELECTION, from bar TIMESTAMPS only (no price is an argument): a list of (entry bar, exit bar,
    yyyymmdd, 'F' | 'P') for every eligible calendar day in these bars, in day order."""
    date, minute = _clock(index)
    if len(date) < 2:
        return []
    starts, ends, sdate, lmin, rth = _sessions(date, minute)
    if len(sdate) > 1 and not bool(np.all(sdate[1:] > sdate[:-1])):
        return []                                       # bars out of time order: never guess at sessions
    cand = np.flatnonzero(rth & (lmin == _LAST_SLOT))
    if not len(cand):
        return []                                       # no whole RTH session: the FOMC file is never opened
    cal = _calendar(int(sdate[0]) // 10000, int(sdate[-1]) // 10000)
    out = []
    for j in cand:
        d = int(sdate[j])
        full = d in cal["full"]
        if not (full or d in cal["pm"]):
            continue
        if d in cal["fomcx"] or d > cal["fomc_last"]:
            continue                                    # FOMC day / its eve; or past the pinned list's reach
        s, n1 = int(starts[j]), int(ends[j])
        m = minute[s:n1]
        if not bool(np.all(m[1:] > m[:-1])):
            continue
        a = s + int(np.searchsorted(m, _OPEN_MIN))
        b = s + int(np.searchsorted(m, _PM_MIN))
        x = n1 - 1                                      # the 15:55 bar (lmin == _LAST_SLOT)
        if int(minute[a]) != _OPEN_MIN or b >= n1 or int(minute[b]) != _PM_MIN:
            continue                                    # no 09:30 or no 14:00 bar on the clock (the harness's elig)
        out.append((a if full else b, x, d, "F" if full else "P"))
    return out


def _trades(index, opens, cost_pts=0.533, point_value=20):
    """Every trade on these bars: a list of dicts (bars, date, type, prices, gross points, net dollars)."""
    cost = float(cost_pts)
    ppt = float(point_value)
    out = []
    for e, x, d, typ in _plan(index):
        p_in = float(opens[e])
        p_out = float(opens[x])                         # the 15:55 print: the P&L only
        if not (np.isfinite(p_in) and np.isfinite(p_out)):
            continue                                    # the harness's o930 / o1400 / o1555 notna test
        gross = p_out - p_in
        net = gross - cost
        out.append({"e": e, "x": x, "D": d, "typ": typ, "p_in": p_in, "p_out": p_out, "gross": gross,
                    "net_pts": net, "net": net * ppt})
    return out


def _cfg_ok(cost_pts, point_value):
    try:
        return bool(np.isfinite(float(cost_pts)) and float(point_value) > 0)
    except (TypeError, ValueError):
        return False


def run_backtest(opens, highs, lows, closes, volumes=None, day_id=None, index=None,
                 cost_pts: float = 0.533, point_value: int = 20,
                 return_trades: bool = False, _stop_event=None, _pause_event=None, **_ignore):
    n = len(closes)
    if n < 2 or index is None or len(index) != n:
        return None
    if not _cfg_ok(cost_pts, point_value):
        return None
    if _stop_event is not None and _stop_event.is_set():
        return None
    rows = _trades(index, opens, cost_pts=cost_pts, point_value=point_value)
    trades = [(r["e"], r["x"], float(r["net"]), 1, float(r["p_in"]), float(r["p_out"])) for r in rows]
    return _score(trades, return_trades)


def _score(trades, return_trades):
    if not trades:
        return None
    trades.sort(key=lambda t: (t[1], t[0]))
    pnl = np.array([t[2] for t in trades], float)
    w = pnl[pnl > 0]
    ls = pnl[pnl < 0]
    gw = float(w.sum())
    gl = float(-ls.sum())
    cum = np.cumsum(pnl)
    out = {"total_pnl": float(pnl.sum()), "num_trades": int(len(pnl)),
           "win_rate": float(100.0 * len(w) / len(pnl)),
           "profit_factor": (gw / gl) if gl > 1e-9 else (float("inf") if gw > 0 else 0.0),
           "max_drawdown": float((cum - np.maximum.accumulate(cum)).min()),
           "avg_pnl": float(pnl.mean()), "wins": int(len(w)), "losses": int(len(ls))}
    if return_trades:
        out["trades"] = trades
    return out


def mark_open_trades(trades, opens, highs, lows, closes, volumes=None, day_id=None, index=None, **params):
    """Every trade opens and closes inside one session: nothing is held through a session close, so there is no
    mark. One empty list per trade, in trade order."""
    return [[] for _ in (trades or [])]
