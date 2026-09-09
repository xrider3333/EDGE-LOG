"""EVENT SIZE SCAN — pre-registered sweep of scheduled-event SIZE rules on three crowned legs.

WHY THIS EXISTS
    Through 2026-09 the per-trade feature mining, four new mechanisms and four new feature
    families all produced nothing that survived out of sample.  The one thing that DID work
    was different in kind: KEEL v12 (2026-09-09) halves position size before the 14:00 ET
    FOMC statement, read straight off the Fed's own published calendar.  It improved net in
    4 of 4 stretches with drawdown never worse, sat in the bottom 0.1% of 4,000 random
    calendars, beat 3 placebos, and the same hole shows up on ORB and ENGU-Q.  The lesson
    recorded was: WHEN TILTS DRY UP, GET NEW INFORMATION.  Scheduled events are new
    information the machine has never systematically used.  This file generalises that one
    finding into a pre-registered sweep over many published calendars.

    SIZE RULES ONLY.  Never an entry filter.  Filters have failed every single time this
    month; a size rule keeps every trade the strategy would have taken and only changes how
    many contracts ride on it, so the trade COUNT is identical in every cell (tested).

================================================================================================
PRE-REGISTRATION  — written before a single number was computed, and NOT edited afterwards.
================================================================================================

LEGS (crowned; each run at its own file's DEFAULT_PARAMS defaults, nothing else pinned)
    NOISE   augur_strategies/NOISE_1_1_SBS_V90.py      NQ 5m RTH   cost 0.533 pts, $20/pt, 1 contract
    ORB     augur_strategies/ORB_3_6_R6.py             NQ 5m RTH   cost 0.533 pts, $20/pt, 1 contract
    ENGUQ   augur_strategies/ENGUQ_1M_ETH_ER_1_0.py    NQ 1m ETH   cost 0.533 pts, $20/pt, 1 contract

WINDOW
    2010-06-07 .. 2025-06-30.
    The LAST 12 MONTHS (entry date >= 2024-07-01) are a SEALED LOCKBOX.  Every number in the
    scan below is computed on the pre-lockbox slice 2010-06-07 .. 2024-06-30 only.  The
    lockbox is loaded ONCE, at the very end, for the cells that already cleared everything
    else, and is reported separately and clearly marked as the single peek.

EVENT CALENDARS  (built into tools/data/*.csv, each with a `date` column and a source note)
    fomc_decision   scheduled FOMC decision (statement) days.  ALREADY ON MAIN
                    (tools/data/fomc_dates.txt / .csv, scraped from federalreserve.gov).
                    Included as the known-positive control, since KEEL v12 lives on it.
    cpi             BLS Consumer Price Index news-release days, 08:30 ET.  Hard-coded from
                    the BLS published annual schedules (bls.gov/schedule/<year>/home.htm).
    nfp             BLS Employment Situation ("non-farm payrolls") release days, 08:30 ET.
                    Hard-coded from the SAME BLS annual schedules, so the published
                    exceptions to "first Friday" (e.g. 2015-05-08, 2013-10-22, 2020-01-10)
                    are the real dates, not a re-derived rule.
    fomc_minutes    3 weeks (21 calendar days) after each scheduled decision day, 14:00 ET.
                    Derived from the verified FOMC decision file — that is the Fed's own
                    stated publication rule.
    quad_witching   3rd Friday of March / June / September / December.  Derived.
    month_end       last TWO trading days of each calendar month.       Derived from the tape.
    month_start     first TWO trading days of each calendar month.      Derived from the tape.
    quarter_end     last TWO trading days of each calendar quarter.     Derived from the tape.
    quarter_start   first TWO trading days of each calendar quarter.    Derived from the tape.
    fed_blackout    every trading day in the 10 calendar days BEFORE a scheduled decision
                    day (decision day itself excluded).  Derived from the FOMC file.
    Verification: a handful of dates are cross-checked against the FOMC file already on main
    (fomc_minutes and fed_blackout are DERIVED from it, so they inherit its verification),
    and the CSV header of every file records its source and whether it was verified.  Any
    date that could not be verified is marked in the file's own note line.

RULE FORM  (fixed; no other form is tried)
    On a day in the calendar (and, run separately, the trading day BEFORE it and the trading
    day AFTER it), multiply position size by m for trades whose DECISION BAR (entry bar)
    falls inside a stated clock window.  Size only.  No signal is ever skipped, no entry or
    exit is ever touched.  m = 0.0 is "flat that trade" as a SIZE of zero — the trade is
    still taken and still counted, it just carries no contracts.
        day offset    : {0 = event day, -1 = the trading day before, +1 = the trading day after}
        multiplier m  : {0.0, 0.5, 1.5, 2.0}
        clock window  : {all = whole session, am = entry bar before 14:00 ET,
                         pm = entry bar at/after 14:00 ET}
    A trade's event day is the ET CALENDAR DATE of its entry bar (the same convention
    augur_engine.ml_keel.pre_statement_mask uses), and its clock is that bar's ET hour.
    3 legs x 10 calendars x 3 offsets x 4 multipliers x 3 clock windows = 1,080 cells.
    EVERY cell is reported.  Never only the best.

BAR PER CELL  (ALL of these required, computed on the pre-lockbox slice only)
    B0  at least 30 pre-lockbox trades are affected by the rule (n_affected >= 30).
    B1  NET improves versus the untouched leg.
    B2  ANNUALISED MAR = (net / years) / |max drawdown| improves versus the untouched leg.
    B3  the improvement is not carried by one calendar year:
          (a) the per-year net improvement is positive in at least half of the calendar
              years that contain at least one affected trade, AND
          (b) dropping the single best calendar year still leaves the total improvement > 0.
        The full year table is reported for every cell that reaches this test.
    B4  it survives a PERMUTATION test: 2,000 random calendars drawn from the leg's own
        trading days with the SAME NUMBER OF DAYS PER CALENDAR YEAR as the real calendar.
        The real calendar's net improvement must rank in the top 5% (p <= 0.05, one-sided).
        The rank is reported.  PLUS it must beat at least 2 placebo calendars — the same
        calendar shifted +7 and -7 calendar days (then snapped to trading days) — on net
        improvement.
    A cell SURVIVES only if B0 and B1 and B2 and B3 and B4 all hold.  Nothing else is a pass.

LOCKBOX
    Opened once, at the end, for the surviving cells only.  Reported separately.  A lockbox
    number is never part of the bar and never selects a cell.

OUTPUT
    docs/anatomy/EVENT_SIZE_SCAN.md — this pre-registration, all 1,080 cells, the year
    tables, the permutation ranks, the lockbox peek, and a blunt summary.

USAGE
    python tools/event_size_scan.py                 # full scan + lockbox peek for survivors
    python tools/event_size_scan.py --perm 500      # fewer permutation draws (dev only)
    python tools/event_size_scan.py --no-lockbox    # pre-lockbox work only, seal stays shut
    python tools/event_size_scan.py --print-all     # dump all 1,080 rows to stdout too
"""
import argparse
import csv
import datetime as dt
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS = os.path.join(ROOT, "tools")
DATA = os.path.join(TOOLS, "data")
DOCS = os.path.join(ROOT, "docs", "anatomy")
SHARED = r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"

DATE_FROM = "2010-06-07"
DATE_TO = "2025-06-30"
LOCKBOX_FROM = dt.date(2024, 7, 1)

MULT_USD = 20.0          # NQ, $/point
COST_PTS = 0.533         # NQ house cost, points per round trip

LEGS = [
    dict(key="NOISE", label="NOISE #243/#304 family crown (NQ 5m RTH)",
         file="NOISE_1_1_SBS_V90.py", inst="NQ", tf="5m", sess="RTH"),
    dict(key="ORB", label="ORB #314 crown (NQ 5m RTH)",
         file="ORB_3_6_R6.py", inst="NQ", tf="5m", sess="RTH"),
    dict(key="ENGUQ", label="ENGU-Q #309 crown (NQ 1m ETH)",
         file="ENGUQ_1M_ETH_ER_1_0.py", inst="NQ", tf="1m", sess="ETH"),
]

MULTIPLIERS = (0.0, 0.5, 1.5, 2.0)
OFFSETS = (0, -1, 1)
OFFSET_LABEL = {0: "event day", -1: "day before", 1: "day after"}
CLOCK_WINDOWS = ("all", "am", "pm")
CLOCK_LABEL = {"all": "whole session", "am": "before 14:00 ET", "pm": "at/after 14:00 ET"}

N_PERM = 2000
PERM_ALPHA = 0.05
PLACEBO_SHIFTS = (7, -7)
MIN_AFFECTED = 30
SEED = 20260909


# ═════════════════════════════════════════════════════════════════════════════════════════
# published calendars, hard-coded
# ═════════════════════════════════════════════════════════════════════════════════════════

# BLS Consumer Price Index news-release days.  Source: the BLS published annual schedules,
# https://www.bls.gov/schedule/<year>/home.htm (2010-2025), fetched 2026-09-09.  Irregular
# entries are the real published dates, not typos: the 2013 October shutdown pushed the
# September CPI to 2013-10-30, and 2015's releases genuinely ran late in the month.
CPI_RELEASES = """
2010-06-17 2010-07-16 2010-08-13 2010-09-17 2010-10-15 2010-11-17 2010-12-15
2011-01-14 2011-02-17 2011-03-17 2011-04-15 2011-05-13 2011-06-15 2011-07-15 2011-08-18
2011-09-15 2011-10-19 2011-11-16 2011-12-16
2012-01-19 2012-02-17 2012-03-16 2012-04-13 2012-05-15 2012-06-14 2012-07-17 2012-08-15
2012-09-14 2012-10-16 2012-11-15 2012-12-14
2013-01-16 2013-02-21 2013-03-15 2013-04-16 2013-05-16 2013-06-18 2013-07-16 2013-08-15
2013-09-17 2013-10-30 2013-11-20 2013-12-17
2014-01-16 2014-02-20 2014-03-18 2014-04-15 2014-05-15 2014-06-17 2014-07-22 2014-08-19
2014-09-17 2014-10-22 2014-11-20 2014-12-17
2015-01-16 2015-02-26 2015-03-24 2015-04-17 2015-05-22 2015-06-18 2015-07-17 2015-08-19
2015-09-16 2015-10-15 2015-11-17 2015-12-15
2016-01-20 2016-02-19 2016-03-16 2016-04-14 2016-05-17 2016-06-16 2016-07-15 2016-08-16
2016-09-16 2016-10-18 2016-11-17 2016-12-15
2017-01-18 2017-02-15 2017-03-15 2017-04-14 2017-05-12 2017-06-14 2017-07-14 2017-08-11
2017-09-14 2017-10-13 2017-11-15 2017-12-13
2018-01-12 2018-02-14 2018-03-13 2018-04-11 2018-05-10 2018-06-12 2018-07-12 2018-08-10
2018-09-13 2018-10-11 2018-11-14 2018-12-12
2019-01-11 2019-02-13 2019-03-12 2019-04-10 2019-05-10 2019-06-12 2019-07-11 2019-08-13
2019-09-12 2019-10-10 2019-11-13 2019-12-11
2020-01-14 2020-02-13 2020-03-11 2020-04-10 2020-05-12 2020-06-10 2020-07-14 2020-08-12
2020-09-11 2020-10-13 2020-11-12 2020-12-10
2021-01-13 2021-02-10 2021-03-10 2021-04-13 2021-05-12 2021-06-10 2021-07-13 2021-08-11
2021-09-14 2021-10-13 2021-11-10 2021-12-10
2022-01-12 2022-02-10 2022-03-10 2022-04-12 2022-05-11 2022-06-10 2022-07-13 2022-08-10
2022-09-13 2022-10-13 2022-11-10 2022-12-13
2023-01-12 2023-02-14 2023-03-14 2023-04-12 2023-05-10 2023-06-13 2023-07-12 2023-08-10
2023-09-13 2023-10-12 2023-11-14 2023-12-12
2024-01-11 2024-02-13 2024-03-12 2024-04-10 2024-05-15 2024-06-12 2024-07-11 2024-08-14
2024-09-11 2024-10-10 2024-11-13 2024-12-11
2025-01-15 2025-02-12 2025-03-12 2025-04-10 2025-05-13 2025-06-11
""".split()

# BLS Employment Situation ("non-farm payrolls") release days.  SAME source pages, so the
# published exceptions to the first-Friday rule are the real dates: 2011-07-08, 2012-03-09,
# 2013-10-22 (shutdown), 2014-01-10, 2015-05-08, 2020-01-10, 2021-10-08, 2022-07-08 ...
NFP_RELEASES = """
2010-07-02 2010-08-06 2010-09-03 2010-10-08 2010-11-05 2010-12-03
2011-01-07 2011-02-04 2011-03-04 2011-04-01 2011-05-06 2011-06-03 2011-07-08 2011-08-05
2011-09-02 2011-10-07 2011-11-04 2011-12-02
2012-01-06 2012-02-03 2012-03-09 2012-04-06 2012-05-04 2012-06-01 2012-07-06 2012-08-03
2012-09-07 2012-10-05 2012-11-02 2012-12-07
2013-01-04 2013-02-01 2013-03-08 2013-04-05 2013-05-03 2013-06-07 2013-07-05 2013-08-02
2013-09-06 2013-10-22 2013-11-08 2013-12-06
2014-01-10 2014-02-07 2014-03-07 2014-04-04 2014-05-02 2014-06-06 2014-07-03 2014-08-01
2014-09-05 2014-10-03 2014-11-07 2014-12-05
2015-01-09 2015-02-06 2015-03-06 2015-04-03 2015-05-08 2015-06-05 2015-07-02 2015-08-07
2015-09-04 2015-10-02 2015-11-06 2015-12-04
2016-01-08 2016-02-05 2016-03-04 2016-04-01 2016-05-06 2016-06-03 2016-07-08 2016-08-05
2016-09-02 2016-10-07 2016-11-04 2016-12-02
2017-01-06 2017-02-03 2017-03-10 2017-04-07 2017-05-05 2017-06-02 2017-07-07 2017-08-04
2017-09-01 2017-10-06 2017-11-03 2017-12-08
2018-01-05 2018-02-02 2018-03-09 2018-04-06 2018-05-04 2018-06-01 2018-07-06 2018-08-03
2018-09-07 2018-10-05 2018-11-02 2018-12-07
2019-01-04 2019-02-01 2019-03-08 2019-04-05 2019-05-03 2019-06-07 2019-07-05 2019-08-02
2019-09-06 2019-10-04 2019-11-01 2019-12-06
2020-01-10 2020-02-07 2020-03-06 2020-04-03 2020-05-08 2020-06-05 2020-07-02 2020-08-07
2020-09-04 2020-10-02 2020-11-06 2020-12-04
2021-01-08 2021-02-05 2021-03-05 2021-04-02 2021-05-07 2021-06-04 2021-07-02 2021-08-06
2021-09-03 2021-10-08 2021-11-05 2021-12-03
2022-01-07 2022-02-04 2022-03-04 2022-04-01 2022-05-06 2022-06-03 2022-07-08 2022-08-05
2022-09-02 2022-10-07 2022-11-04 2022-12-02
2023-01-06 2023-02-03 2023-03-10 2023-04-07 2023-05-05 2023-06-02 2023-07-07 2023-08-04
2023-09-01 2023-10-06 2023-11-03 2023-12-08
2024-01-05 2024-02-02 2024-03-08 2024-04-05 2024-05-03 2024-06-07 2024-07-05 2024-08-02
2024-09-06 2024-10-04 2024-11-01 2024-12-06
2025-01-10 2025-02-07 2025-03-07 2025-04-04 2025-05-02 2025-06-06
""".split()

CAL_SOURCE = {
    "fomc_decision": "tools/data/fomc_dates.txt (federalreserve.gov, already verified on main)",
    "cpi": "BLS published annual schedules bls.gov/schedule/<year>/home.htm, fetched 2026-09-09",
    "nfp": "BLS published annual schedules bls.gov/schedule/<year>/home.htm, fetched 2026-09-09",
    "fomc_minutes": "DERIVED: scheduled FOMC decision day + 21 calendar days (the Fed's own rule)",
    "quad_witching": "DERIVED: 3rd Friday of Mar/Jun/Sep/Dec",
    "month_end": "DERIVED: last 2 trading days of each calendar month (from the NQ RTH tape)",
    "month_start": "DERIVED: first 2 trading days of each calendar month (from the NQ RTH tape)",
    "quarter_end": "DERIVED: last 2 trading days of each calendar quarter (from the NQ RTH tape)",
    "quarter_start": "DERIVED: first 2 trading days of each calendar quarter (from the NQ RTH tape)",
    "fed_blackout": "DERIVED: trading days in the 10 calendar days before a scheduled decision day",
}


# ═════════════════════════════════════════════════════════════════════════════════════════
# calendar builders  (pure — the unit tests hit these directly)
# ═════════════════════════════════════════════════════════════════════════════════════════

def fomc_decision_days(path=None):
    """Scheduled FOMC decision (statement) days as dates, from the file already on main."""
    p = path or os.path.join(DATA, "fomc_dates.txt")
    if not os.path.exists(p):
        p = os.path.join(SHARED, "tools", "data", "fomc_dates.txt")
    out = []
    with open(p, "r", encoding="utf-8") as fh:
        for ln in fh:
            ln = ln.strip()
            if ln and not ln.startswith("#"):
                out.append(dt.date.fromisoformat(ln))
    return sorted(set(out))


def third_friday(year, month):
    """The 3rd Friday of `month` — the quad-witching / index-expiry day."""
    d = dt.date(year, month, 1)
    first_fri = d + dt.timedelta(days=(4 - d.weekday()) % 7)
    return first_fri + dt.timedelta(days=14)


def build_quad_witching(y0, y1):
    return sorted(third_friday(y, m) for y in range(y0, y1 + 1) for m in (3, 6, 9, 12))


def build_fomc_minutes(decision_days):
    """The Fed publishes the minutes 3 weeks after the policy decision."""
    return sorted({d + dt.timedelta(days=21) for d in decision_days})


def build_fed_blackout(decision_days, trading_days):
    """Every trading day in the 10 calendar days before a decision (decision day excluded)."""
    td = set(trading_days)
    out = set()
    for d in decision_days:
        for k in range(1, 11):
            c = d - dt.timedelta(days=k)
            if c in td:
                out.add(c)
    return sorted(out)


def build_period_edges(trading_days, period, n=2):
    """First / last `n` trading days of each calendar month (period='M') or quarter ('Q').

    Returns (starts, ends).  `trading_days` must be a sorted list of dates."""
    key = {}
    for d in trading_days:
        k = (d.year, d.month) if period == "M" else (d.year, (d.month - 1) // 3)
        key.setdefault(k, []).append(d)
    starts, ends = [], []
    for k in sorted(key):
        days = sorted(key[k])
        starts.extend(days[:n])
        ends.extend(days[-n:])
    return sorted(set(starts)), sorted(set(ends))


def build_all_calendars(trading_days, y0, y1):
    """Every calendar in the pre-registration, as {name: sorted list of dates}."""
    dec = [d for d in fomc_decision_days() if y0 <= d.year <= y1]
    m_start, m_end = build_period_edges(trading_days, "M", 2)
    q_start, q_end = build_period_edges(trading_days, "Q", 2)
    cals = {
        "fomc_decision": dec,
        "cpi": [dt.date.fromisoformat(s) for s in CPI_RELEASES],
        "nfp": [dt.date.fromisoformat(s) for s in NFP_RELEASES],
        "fomc_minutes": build_fomc_minutes(dec),
        "quad_witching": build_quad_witching(y0, y1),
        "month_start": m_start,
        "month_end": m_end,
        "quarter_start": q_start,
        "quarter_end": q_end,
        "fed_blackout": build_fed_blackout(dec, trading_days),
    }
    return {k: sorted(d for d in v if y0 <= d.year <= y1) for k, v in cals.items()}


def write_calendar_csvs(cals, verify_notes):
    """Write each calendar to tools/data/<name>_dates.csv with a `date` column + source note."""
    os.makedirs(DATA, exist_ok=True)
    paths = {}
    for name, days in cals.items():
        if name == "fomc_decision":
            continue                                   # already on main, never rewritten
        fp = os.path.join(DATA, f"{name}_dates.csv")
        with open(fp, "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(["date", "note"])
            w.writerow(["# source", CAL_SOURCE[name]])
            w.writerow(["# verification", verify_notes.get(name, "not verified")])
            for d in days:
                w.writerow([d.isoformat(), name])
        paths[name] = fp
    return paths


def verify_calendars(cals):
    """Cross-check a handful of dates.  Returns {name: note} — anything unverified says so."""
    notes = {}
    dec = set(cals["fomc_decision"])
    mins = set(cals["fomc_minutes"])
    ok = sum(1 for d in dec if d + dt.timedelta(days=21) in mins)
    notes["fomc_minutes"] = (f"VERIFIED: derived from the on-main FOMC file; {ok}/{len(dec)} "
                             f"decisions map to a minutes date exactly 21 days later")
    bl = set(cals["fed_blackout"])
    notes["fed_blackout"] = (f"VERIFIED: derived from the on-main FOMC file; no decision day is "
                             f"itself in the set ({len(dec & bl)} overlaps, must be 0)")
    qw = cals["quad_witching"]
    spot = {dt.date(2024, 3, 15), dt.date(2024, 6, 21), dt.date(2024, 9, 20), dt.date(2024, 12, 20)}
    notes["quad_witching"] = ("VERIFIED: 2024 spot-check "
                              f"{'all 4 present' if spot <= set(qw) else 'MISMATCH'}; all entries "
                              f"are Fridays: {all(d.weekday() == 4 for d in qw)}")
    # CPI / NFP: the release always lands on a weekday, and NFP is a Friday except on the
    # published exceptions, which is exactly what the BLS pages recorded.
    cpi = cals["cpi"]
    notes["cpi"] = (f"PARTIALLY VERIFIED: {len(cpi)} dates transcribed from the BLS annual "
                    f"schedule pages; all weekdays: {all(d.weekday() < 5 for d in cpi)}; NOT "
                    f"independently cross-checked against a second source")
    nfp = cals["nfp"]
    fri = sum(1 for d in nfp if d.weekday() == 4)
    notes["nfp"] = (f"PARTIALLY VERIFIED: {len(nfp)} dates transcribed from the BLS annual "
                    f"schedule pages; {fri}/{len(nfp)} are Fridays (the rest are the published "
                    f"exceptions); NOT independently cross-checked against a second source")
    for k in ("month_start", "month_end", "quarter_start", "quarter_end"):
        notes[k] = "VERIFIED BY CONSTRUCTION: taken from the traded tape's own session dates"
    return notes


def shift_to_trading_days(days, trading_days, k):
    """Shift a calendar by k TRADING days (k=0 snaps a non-trading date forward to the next
    trading day).  Days that fall outside the tape are dropped.

    Vectorised on int64 ordinals: a searchsorted against a Python list of `date` objects
    rebuilds an object array on EVERY call, which made the ENGU-Q scan quadratic."""
    if not len(days) or not len(trading_days):
        return []
    td_o = _ords(trading_days)                                   # already sorted
    n = len(td_o)
    i = np.searchsorted(td_o, _ords(sorted(days)), side="left") + int(k)
    i = i[(i >= 0) & (i < n)]
    return sorted({dt.date.fromordinal(int(x)) for x in np.unique(td_o[i])})


def shift_calendar_days(days, delta_days):
    """Placebo shift: move every date by delta_days CALENDAR days."""
    return sorted({d + dt.timedelta(days=int(delta_days)) for d in days})


# ═════════════════════════════════════════════════════════════════════════════════════════
# leg loading
# ═════════════════════════════════════════════════════════════════════════════════════════

def load_leg(leg, date_from=DATE_FROM, date_to=DATE_TO):
    """Run one crowned leg at its file's pinned DEFAULT_PARAMS over the whole window.

    Returns a dict with, per trade in chronological order:
        date  ET calendar date of the ENTRY (decision) bar
        hour  ET hour of the entry bar
        pnl   net dollars for ONE contract (cost already subtracted)
    The lockbox is NOT sliced off here — the caller does that, so the slicing is explicit
    and testable (tests/test_event_size_scan.py asserts the pre-lockbox path never sees it).
    """
    sys.path.insert(0, TOOLS)
    import feature_board as FB                                   # heavy; imported lazily

    df = FB.load(leg["inst"], leg["tf"], leg["sess"], date_from, date_to)
    trades = FB.run_strategy(leg["file"], df, {})                # {} => the file's own defaults
    if not trades:
        raise RuntimeError(f"{leg['key']}: no trades")
    trades = sorted(trades, key=lambda t: t[0])
    eb = np.array([int(t[0]) for t in trades])
    pnl = (np.array([float(t[2]) for t in trades]) - COST_PTS) * MULT_USD
    idx = pd.DatetimeIndex(df["_dt"])
    ts = idx[eb]
    date = np.array(ts.date)
    return dict(key=leg["key"], label=leg["label"], n=len(pnl), pnl=pnl,
                date=date, hour=np.asarray(ts.hour), ord=_ords(date),
                yr=np.array([d.year for d in date], np.int64),
                trading_days=sorted({d for d in pd.DatetimeIndex(df["_dt"]).date}))


def _ords(dates):
    """Dates as int64 ordinals — object-dtype date arrays make np.isin quadratic."""
    return np.fromiter((d.toordinal() for d in dates), np.int64, len(dates))


def slice_pre_lockbox(rec, lockbox_from=LOCKBOX_FROM):
    """The ONLY door to pre-lockbox data.  Returns a record holding no lockbox trade."""
    m = rec["date"] < lockbox_from
    return _subset(rec, m, stage="pre-lockbox")


def slice_lockbox(rec, lockbox_from=LOCKBOX_FROM):
    """THE SINGLE PEEK.  Called once, at the very end, for surviving cells only."""
    m = rec["date"] >= lockbox_from
    return _subset(rec, m, stage="lockbox")


PER_TRADE = ("pnl", "date", "hour", "ord", "yr")


def _subset(rec, m, stage):
    out = {k: v for k, v in rec.items() if k not in PER_TRADE + ("n", "stage")}
    for k in PER_TRADE:
        if k in rec:
            out[k] = np.asarray(rec[k])[m]
    out["n"] = int(m.sum())
    out["stage"] = stage
    return out


# ═════════════════════════════════════════════════════════════════════════════════════════
# metrics + the size rule
# ═════════════════════════════════════════════════════════════════════════════════════════

def metrics(pnl, years):
    """Net, max drawdown on the trade sequence, and ANNUALISED MAR = (net/years)/|DD|."""
    p = np.asarray(pnl, float)
    if not len(p):
        return dict(net=0.0, dd=0.0, mar=0.0, pf=0.0, n=0)
    cum = np.cumsum(p)
    dd = float((cum - np.maximum.accumulate(np.concatenate([[0.0], cum]))[1:]).min())
    gw, gl = float(p[p > 0].sum()), float(-p[p < 0].sum())
    return dict(net=float(p.sum()), dd=dd, n=len(p),
                pf=(gw / gl) if gl > 1e-9 else float("inf"),
                mar=((float(p.sum()) / years) / abs(dd)) if dd < -1e-9 else float("inf"))


def clock_mask(hour, clockwin):
    if clockwin == "all":
        return np.ones(len(hour), bool)
    if clockwin == "am":
        return hour < 14
    if clockwin == "pm":
        return hour >= 14
    raise ValueError(clockwin)


def cell_mask(rec, dayset, clockwin):
    """Which trades the rule touches: entry date in `dayset` AND entry bar in the clock window."""
    o = rec.get("ord")
    if o is None:
        o = _ords(rec["date"])
    ds = _ords(sorted(dayset)) if len(dayset) else np.empty(0, np.int64)
    return np.isin(o, ds) & clock_mask(np.asarray(rec["hour"]), clockwin)


def apply_size(pnl, mask, m):
    """The whole rule.  Multiplies size — it NEVER drops a trade, so len() is invariant."""
    return np.asarray(pnl, float) * np.where(mask, float(m), 1.0)


def year_deltas(rec, mask, m):
    """Per calendar year: the net change the rule makes.  Only years with an affected trade."""
    d = apply_size(rec["pnl"], mask, m) - rec["pnl"]
    yr = rec.get("yr")
    if yr is None:
        yr = np.array([x.year for x in rec["date"]], np.int64)
    out = {}
    for y in (np.unique(yr[mask]) if mask.any() else []):
        out[int(y)] = float(d[yr == y].sum())
    return out


def year_test(ydeltas):
    """B3: positive in >= half the affected years, and still positive with the best year gone."""
    if not ydeltas:
        return False, 0, 0, 0.0
    vals = np.array(list(ydeltas.values()), float)
    pos = int((vals > 0).sum())
    tot = float(vals.sum())
    drop_best = float(tot - vals.max())
    ok = (pos >= int(np.ceil(len(vals) / 2.0))) and (drop_best > 0)
    return bool(ok), pos, len(vals), drop_best


# ═════════════════════════════════════════════════════════════════════════════════════════
# permutation harness
# ═════════════════════════════════════════════════════════════════════════════════════════

def day_sums(rec, trading_days, clockwin):
    """Per trading day, the summed PnL of that day's trades inside the clock window."""
    td = list(trading_days)
    pos = {d: i for i, d in enumerate(td)}
    out = np.zeros(len(td))
    cm = clock_mask(rec["hour"], clockwin)
    for d, p, keep in zip(rec["date"], rec["pnl"], cm):
        if keep:
            i = pos.get(d)
            if i is not None:
                out[i] += p
    return out


def permute_sums(daysum, day_year, dayset_idx, n_perm, rng):
    """Null distribution of the affected-trade PnL sum under random calendars with the SAME
    number of days PER CALENDAR YEAR.  Returns (S_real, S_draws)."""
    dayset_idx = np.asarray(dayset_idx, int)
    s_real = float(daysum[dayset_idx].sum()) if len(dayset_idx) else 0.0
    draws = np.zeros(int(n_perm))
    if not len(dayset_idx):
        return s_real, draws
    yrs = day_year[dayset_idx]
    for y in np.unique(yrs):
        k = int((yrs == y).sum())
        pool = np.flatnonzero(day_year == y)
        if k <= 0 or not len(pool):
            continue
        k = min(k, len(pool))
        r = rng.random((int(n_perm), len(pool)))
        sel = np.argpartition(r, k - 1, axis=1)[:, :k] if k < len(pool) else \
            np.tile(np.arange(len(pool)), (int(n_perm), 1))
        draws += daysum[pool][sel].sum(axis=1)
    return s_real, draws


def perm_pvalue(s_real, s_draws, m):
    """One-sided p on the NET IMPROVEMENT delta = (m-1) * S.  Also the rank of the real one."""
    d_real = (m - 1.0) * s_real
    d_draws = (m - 1.0) * np.asarray(s_draws, float)
    n = len(d_draws)
    better = int((d_draws >= d_real).sum())
    p = (1.0 + better) / (1.0 + n)
    rank = 1 + int((d_draws > d_real).sum())
    return p, rank, n + 1, float(d_draws.mean() * 1.0)


# ═════════════════════════════════════════════════════════════════════════════════════════
# the scan
# ═════════════════════════════════════════════════════════════════════════════════════════

def window_years(a, b):
    return max((pd.Timestamp(b) - pd.Timestamp(a)).days / 365.25, 1.0 / 12)


def scan_leg(rec, cals, trading_days, n_perm, rng, years):
    """Every cell for one leg on the given (pre-lockbox) record.  Returns a list of dicts."""
    base = metrics(rec["pnl"], years)
    td = list(trading_days)
    pos = {d: i for i, d in enumerate(td)}
    day_year = np.array([d.year for d in td])
    ds_cache = {w: day_sums(rec, td, w) for w in CLOCK_WINDOWS}
    perm_cache = {}
    rows = []
    for cname, cdays in cals.items():
        for off in OFFSETS:
            dayset = shift_to_trading_days(cdays, td, off)
            dayset_idx = np.array([pos[d] for d in dayset if d in pos], int)
            placebos = {}
            for sh in PLACEBO_SHIFTS:
                pl = shift_to_trading_days(shift_calendar_days(cdays, sh), td, off)
                placebos[sh] = set(pl)
            for w in CLOCK_WINDOWS:
                mask = cell_mask(rec, dayset, w)
                n_aff = int(mask.sum())
                s_aff = float(rec["pnl"][mask].sum())
                pl_masks = {sh: cell_mask(rec, placebos[sh], w) for sh in PLACEBO_SHIFTS}
                pl_s = {sh: float(rec["pnl"][pl_masks[sh]].sum()) for sh in PLACEBO_SHIFTS}
                for m in MULTIPLIERS:
                    sized = apply_size(rec["pnl"], mask, m)
                    sm = metrics(sized, years)
                    row = dict(leg=rec["key"], calendar=cname, offset=off, clock=w, m=m,
                               n_affected=n_aff, cal_days=len(dayset),
                               base_net=base["net"], base_dd=base["dd"], base_mar=base["mar"],
                               net=sm["net"], dd=sm["dd"], mar=sm["mar"],
                               d_net=sm["net"] - base["net"], d_mar=sm["mar"] - base["mar"],
                               b0=n_aff >= MIN_AFFECTED,
                               b1=sm["net"] > base["net"], b2=sm["mar"] > base["mar"])
                    ydel = year_deltas(rec, mask, m)
                    ok3, pos_y, tot_y, drop_best = year_test(ydel)
                    row.update(b3=ok3, years_pos=pos_y, years_n=tot_y,
                               drop_best_year=drop_best, ydeltas=ydel)
                    row["placebo"] = {sh: (m - 1.0) * pl_s[sh] for sh in PLACEBO_SHIFTS}
                    row["d_real_S"] = (m - 1.0) * s_aff
                    row["beats_placebos"] = all(row["d_real_S"] > v for v in row["placebo"].values())
                    if row["b0"] and row["b1"] and row["b2"] and row["b3"]:
                        ck = (w, cname, off)
                        if ck not in perm_cache:
                            perm_cache[ck] = permute_sums(ds_cache[w], day_year, dayset_idx,
                                                          n_perm, rng)
                        s_real, s_draws = perm_cache[ck]
                        p, rank, ntot, _ = perm_pvalue(s_real, s_draws, m)
                        row.update(perm_p=p, perm_rank=rank, perm_n=ntot,
                                   b4=(p <= PERM_ALPHA) and row["beats_placebos"])
                    else:
                        row.update(perm_p=None, perm_rank=None, perm_n=None, b4=False)
                    row["survives"] = bool(row["b0"] and row["b1"] and row["b2"]
                                           and row["b3"] and row["b4"])
                    rows.append(row)
    return rows, base


def random_matched_calendar(days, trading_days, rng):
    """A random calendar with the SAME number of days per calendar year as `days`."""
    by_year = {}
    for d in days:
        by_year[d.year] = by_year.get(d.year, 0) + 1
    pool = {}
    for d in trading_days:
        pool.setdefault(d.year, []).append(d)
    out = []
    for y, k in by_year.items():
        p = pool.get(y, [])
        if p:
            out.extend(rng.choice(np.array(p, dtype=object), size=min(k, len(p)),
                                  replace=False).tolist())
    return sorted(out)


def family_null(pres, cals, pre_td, n_perm, reps, rng, years):
    """POST-HOC DIAGNOSTIC — NOT part of the pre-registered bar, and it can never rescue or
    kill a cell.  It answers the one question the pre-registration forgot to ask: 1,080 cells
    were each judged at a nominal one-sided 5%, with no multiple-comparisons clause, so HOW
    MANY CELLS WOULD SURVIVE IF EVERY CALENDAR WERE MEANINGLESS?  Each replicate swaps all ten
    calendars for random ones with the same number of days per calendar year and re-runs the
    identical pipeline.  Returns the per-replicate survivor counts."""
    counts = []
    for rep in range(int(reps)):
        fake = {name: random_matched_calendar(d, pre_td, rng) for name, d in cals.items()}
        n = 0
        for rec in pres:
            rr, _ = scan_leg(rec, fake, pre_td, n_perm, rng, years)
            n += sum(1 for r in rr if r["survives"])
        counts.append(n)
        print(f"    null replicate {rep + 1}/{reps}: {n} survivors")
    return counts


# ═════════════════════════════════════════════════════════════════════════════════════════
# reporting
# ═════════════════════════════════════════════════════════════════════════════════════════

HDR = (f"{'leg':6s} {'calendar':14s} {'offset':11s} {'clock':6s} {'m':>4s} {'n_aff':>6s} "
       f"{'net':>12s} {'dNet':>11s} {'MAR':>6s} {'dMAR':>7s} {'B0':>3s}{'B1':>3s}{'B2':>3s}"
       f"{'B3':>3s}{'B4':>3s} {'perm p':>7s} {'rank':>6s}  verdict")


def fmt_row(r):
    p = "" if r["perm_p"] is None else f"{r['perm_p']:.4f}"
    rk = "" if r["perm_rank"] is None else f"{r['perm_rank']}/{r['perm_n']}"
    yn = lambda b: " Y " if b else " . "                                        # noqa: E731
    return (f"{r['leg']:6s} {r['calendar']:14s} {OFFSET_LABEL[r['offset']]:11s} {r['clock']:6s} "
            f"{r['m']:4.1f} {r['n_affected']:6d} {r['net']:12,.0f} {r['d_net']:+11,.0f} "
            f"{r['mar']:6.2f} {r['d_mar']:+7.2f} {yn(r['b0'])}{yn(r['b1'])}{yn(r['b2'])}"
            f"{yn(r['b3'])}{yn(r['b4'])} {p:>7s} {rk:>6s}  "
            f"{'SURVIVES' if r['survives'] else ''}")


def write_md(rows, bases, cals, verify_notes, lockbox_rows, args, cal_paths, null_counts):
    os.makedirs(DOCS, exist_ok=True)
    fp = os.path.join(DOCS, "EVENT_SIZE_SCAN.md")
    surv = [r for r in rows if r["survives"]]
    reached = [r for r in rows if r["perm_p"] is not None]
    L = []
    A = L.append
    A("# EVENT SIZE SCAN — scheduled-event position-size rules on three crowned legs")
    A("")
    A(f"Generated {dt.datetime.now():%Y-%m-%d %H:%M} · `tools/event_size_scan.py` · "
      f"{len(rows)} cells · {args.perm} permutation draws · seed {SEED}")
    A("")
    A("## Blunt summary")
    A("")
    if not surv:
        A("**NOTHING SURVIVES.** Not one of the "
          f"{len(rows)} pre-registered cells clears all five clauses of the bar on the "
          "pre-lockbox window. The KEEL v12 FOMC hole remains the only scheduled-event size "
          "lever this project has evidence for; none of the other nine published calendars "
          "reproduces anything like it on any of the three legs, at any multiplier, in any "
          "clock window, on the event day or the day either side of it.")
    else:
        A(f"**{len(surv)} of {len(rows)} cells survive** all five clauses on the pre-lockbox "
          f"window ({100.0*len(surv)/len(rows):.1f}%). They are listed below with their "
          "permutation ranks, and the sealed year is opened once for them at the end.")
        A("")
        A("**But read the survivor list as a hypothesis list, not as "
          f"{len(surv)} findings.** The pre-registration has a hole in it: it judged every one "
          f"of {len(rows)} cells at a nominal one-sided 5% and never wrote down a "
          "multiple-comparisons clause. The cells are also heavily redundant — m=0.0 and m=0.5 "
          "always share a permutation p-value with each other (and m=1.5 with m=2.0), because "
          "the improvement is (m-1) x the same affected-trade sum; 'whole session' and "
          "'before 14:00' overlap almost completely on an RTH leg; and consecutive day offsets "
          "of a multi-day calendar overlap. So the honest denominator is a few hundred "
          "effectively independent tests, and roughly five percent of them are expected to "
          "clear a 5% threshold with no edge at all.")
        if null_counts:
            nc = np.array(null_counts, float)
            A("")
            A(f"The post-hoc family-wide null below settles it: with all ten calendars replaced "
              f"by random ones of the same size, the identical pipeline still produces a median "
              f"of **{np.median(nc):.0f}** survivors (range {nc.min():.0f}-{nc.max():.0f}, mean "
              f"{nc.mean():.1f}) across {len(nc)} replicates, against the real scan's "
              f"**{len(surv)}**. P(random >= real) = {(nc >= len(surv)).mean():.3f}.")
    A("")
    A("## Pre-registration (verbatim, written before any number was computed)")
    A("")
    A("```")
    A(__doc__.strip())
    A("```")
    A("")
    A("## Legs — untouched baseline (pre-lockbox 2010-06-07 .. 2024-06-30)")
    A("")
    A("| leg | trades | net | max DD | annualised MAR |")
    A("|---|---:|---:|---:|---:|")
    for k, b in bases.items():
        A(f"| {k} | {b['n']:,} | ${b['net']:,.0f} | ${b['dd']:,.0f} | {b['mar']:.2f} |")
    A("")
    A("## Event calendars built")
    A("")
    A("> **Shipping note:** the repo `.gitignore` ignores `*.csv` globally, so these files "
      "exist on disk but git will not see them. `tools/data/fomc_dates.csv` is tracked only "
      "because it was force-added. Ship these the same way (`git add -f tools/data/*_dates.csv`) "
      "or they will silently not travel with the tool. Regenerating them is cheap and "
      "deterministic — `python tools/event_size_scan.py` rewrites all nine every run.")
    A("")
    A("Day counts are what the SCAN saw (pre-lockbox years only). The CSV files themselves "
      "cover the whole 2010-06-07..2025-06-30 window.")
    A("")
    A("| calendar | days seen by the scan | file | source | verification |")
    A("|---|---:|---|---|---|")
    for name in cals:
        A(f"| {name} | {len(cals[name])} | "
          f"`{os.path.relpath(cal_paths.get(name, os.path.join(DATA,'fomc_dates.txt')), ROOT)}` | "
          f"{CAL_SOURCE[name]} | {verify_notes.get(name, 'already verified on main')} |")
    A("")
    A("## Surviving cells")
    A("")
    if not surv:
        A("_None._")
    else:
        A("| leg | calendar | offset | clock | m | n_aff | net | ΔNet | MAR | ΔMAR | "
          "perm rank | perm p | placebo +7 | placebo -7 |")
        A("|---|---|---|---|---:|---:|---:|---:|---:|---:|---|---:|---:|---:|")
        for r in surv:
            A(f"| {r['leg']} | {r['calendar']} | {OFFSET_LABEL[r['offset']]} | "
              f"{CLOCK_LABEL[r['clock']]} | {r['m']} | {r['n_affected']} | ${r['net']:,.0f} | "
              f"${r['d_net']:+,.0f} | {r['mar']:.2f} | {r['d_mar']:+.2f} | "
              f"{r['perm_rank']}/{r['perm_n']} | {r['perm_p']:.4f} | "
              f"${r['placebo'][7]:+,.0f} | ${r['placebo'][-7]:+,.0f} |")
    A("")
    A("## Family-wide null — post-hoc diagnostic, NOT part of the pre-registered bar")
    A("")
    A("This was not in the pre-registration and it neither rescues nor kills a single cell. "
      "It exists because the pre-registration forgot a multiple-comparisons clause, and the "
      "only way to read the survivor count honestly is to know what the same pipeline does "
      "when the calendars mean nothing. Each replicate replaces all ten calendars with random "
      "ones carrying the same number of days per calendar year, then runs the identical "
      "B0-B4 pipeline over all three legs.")
    A("")
    if not null_counts:
        A("_Not run (`--null-reps 0`)._")
    else:
        nc = np.array(null_counts, float)
        A("| replicates | real survivors | null median | null range | null mean | "
          "P(null >= real) |")
        A("|---:|---:|---:|---|---:|---:|")
        A(f"| {len(nc)} | {len(surv)} | {np.median(nc):.0f} | "
          f"{nc.min():.0f}-{nc.max():.0f} | {nc.mean():.1f} | {(nc >= len(surv)).mean():.3f} |")
        A("")
        A("Per-replicate survivor counts: " + ", ".join(str(int(x)) for x in null_counts))
        A("")
        A(f"Cells that reached the permutation at all (cleared B0-B3): {len(reached)} of "
          f"{len(rows)}. Of those, {len(surv)} cleared B4.")
    A("")
    A("## Lockbox — THE SINGLE PEEK (2024-07-01 .. 2025-06-30)")
    A("")
    if lockbox_rows is None:
        A("_Not opened (`--no-lockbox`)._")
    elif not lockbox_rows:
        A("_Nothing survived the pre-lockbox bar, so the seal was never broken._")
    else:
        A("| leg | calendar | offset | clock | m | LB n_aff | LB base net | LB sized net | "
          "ΔNet | LB base DD | LB sized DD |")
        A("|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|")
        for r in lockbox_rows:
            A(f"| {r['leg']} | {r['calendar']} | {OFFSET_LABEL[r['offset']]} | "
              f"{CLOCK_LABEL[r['clock']]} | {r['m']} | {r['n_affected']} | "
              f"${r['base_net']:,.0f} | ${r['net']:,.0f} | ${r['d_net']:+,.0f} | "
              f"${r['base_dd']:,.0f} | ${r['dd']:,.0f} |")
    A("")
    A("## Cells that cleared net + MAR + the year test (B0-B3) and so reached the permutation")
    A("")
    reached = [r for r in rows if r["perm_p"] is not None]
    if not reached:
        A("_None — no cell got past net, MAR and the one-year-carry test._")
    else:
        A("| leg | calendar | offset | clock | m | n_aff | ΔNet | ΔMAR | years + / n | "
          "drop-best-year Δ | perm rank | perm p | beats placebos |")
        A("|---|---|---|---|---:|---:|---:|---:|---|---:|---|---:|---|")
        for r in sorted(reached, key=lambda x: x["perm_p"]):
            A(f"| {r['leg']} | {r['calendar']} | {OFFSET_LABEL[r['offset']]} | "
              f"{CLOCK_LABEL[r['clock']]} | {r['m']} | {r['n_affected']} | "
              f"${r['d_net']:+,.0f} | {r['d_mar']:+.2f} | {r['years_pos']}/{r['years_n']} | "
              f"${r['drop_best_year']:+,.0f} | {r['perm_rank']}/{r['perm_n']} | "
              f"{r['perm_p']:.4f} | {'yes' if r['beats_placebos'] else 'NO'} |")
    A("")
    A("## Year tables")
    A("")
    A("Per-calendar-year net change the rule makes, for every cell that cleared B0-B2 "
      "(the cells where a year table can even be read).")
    A("")
    shown = [r for r in rows if r["b0"] and r["b1"] and r["b2"]]
    if not shown:
        A("_No cell improved both net and MAR, so there is no year table to show._")
    for r in shown:
        ys = sorted(r["ydeltas"])
        A(f"**{r['leg']} · {r['calendar']} · {OFFSET_LABEL[r['offset']]} · "
          f"{CLOCK_LABEL[r['clock']]} · m={r['m']}** — years positive "
          f"{r['years_pos']}/{r['years_n']}, drop-best-year Δ ${r['drop_best_year']:+,.0f}, "
          f"B3 {'PASS' if r['b3'] else 'FAIL'}")
        A("")
        A("| year | " + " | ".join(str(y) for y in ys) + " |")
        A("|---|" + "---:|" * len(ys))
        A("| Δnet | " + " | ".join(f"{r['ydeltas'][y]:+,.0f}" for y in ys) + " |")
        A("")
    A("")
    A(f"## All {len(rows)} cells")
    A("")
    A("`B0` n_affected>=30 · `B1` net improves · `B2` annualised MAR improves · "
      "`B3` not carried by one year · `B4` permutation p<=0.05 AND beats both placebos. "
      "The permutation is only run for cells that already cleared B0-B3 (it cannot rescue a "
      "cell that failed an earlier clause), so `perm p` is blank elsewhere.")
    A("")
    A("| leg | calendar | offset | clock | m | n_aff | net | ΔNet | MAR | ΔMAR | "
      "B0 | B1 | B2 | B3 | B4 | perm p | rank |")
    A("|---|---|---|---|---:|---:|---:|---:|---:|---:|---|---|---|---|---|---:|---|")
    for r in rows:
        y = lambda b: "Y" if b else "no"                                        # noqa: E731
        pp = "" if r["perm_p"] is None else f"{r['perm_p']:.4f}"
        pr = "" if r["perm_rank"] is None else f"{r['perm_rank']}/{r['perm_n']}"
        A(f"| {r['leg']} | {r['calendar']} | {OFFSET_LABEL[r['offset']]} | {r['clock']} | "
          f"{r['m']} | {r['n_affected']} | ${r['net']:,.0f} | ${r['d_net']:+,.0f} | "
          f"{r['mar']:.2f} | {r['d_mar']:+.2f} | {y(r['b0'])} | {y(r['b1'])} | {y(r['b2'])} | "
          f"{y(r['b3'])} | {y(r['b4'])} | {pp} | {pr} |")
    with open(fp, "w", encoding="utf-8") as fh:
        fh.write("\n".join(L) + "\n")
    return fp


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--perm", type=int, default=N_PERM)
    ap.add_argument("--no-lockbox", action="store_true", help="leave the sealed year shut")
    ap.add_argument("--print-all", action="store_true", help="dump all cells to stdout too")
    ap.add_argument("--null-reps", type=int, default=25,
                    help="post-hoc family-wide null replicates (0 = skip); NOT part of the bar")
    args = ap.parse_args()

    rng = np.random.default_rng(SEED)
    print(f"EVENT SIZE SCAN — window {DATE_FROM}..{DATE_TO}, lockbox from {LOCKBOX_FROM}")
    print(f"  legs {[l['key'] for l in LEGS]}  multipliers {MULTIPLIERS}  "
          f"offsets {OFFSETS}  clock {CLOCK_WINDOWS}  perm {args.perm}")

    recs = {}
    for leg in LEGS:
        r = load_leg(leg)
        recs[leg["key"]] = r
        print(f"  [{leg['key']}] {r['n']:,} trades  net ${r['pnl'].sum():,.0f} (full window)")

    trading_days = sorted(set(recs["NOISE"]["trading_days"]))      # the NQ RTH session calendar
    pre_td = [d for d in trading_days if d < LOCKBOX_FROM]
    y0, y1 = pre_td[0].year, pre_td[-1].year
    cals = build_all_calendars(pre_td, y0, y1)
    verify = verify_calendars(cals)
    # The SCAN only ever sees `cals` (pre-lockbox years). The CSVs written to tools/data/ cover
    # the WHOLE window, because a shipped calendar file that stops before today is the exact
    # trap tools/keel_event_check.py warns about — a live tilt keyed on it would never fire.
    cals_full = build_all_calendars(trading_days, y0, pd.Timestamp(DATE_TO).year)
    cal_paths = write_calendar_csvs(cals_full, verify)
    print("\nCALENDARS  (scan uses pre-lockbox years; the CSVs cover the whole window)")
    for k, v in cals.items():
        print(f"  {k:14s} {len(v):5d} days (scan) / {len(cals_full[k]):5d} (csv)   "
              f"{verify.get(k, 'already verified on main')[:60]}")

    years = window_years(DATE_FROM, LOCKBOX_FROM.isoformat())
    rows, bases, pres = [], {}, []
    print(f"\nPRE-LOCKBOX SCAN  ({DATE_FROM} .. {(LOCKBOX_FROM - dt.timedelta(days=1))})"
          f"  years={years:.2f}")
    for leg in LEGS:
        pre = slice_pre_lockbox(recs[leg["key"]])
        assert pre["date"].max() < LOCKBOX_FROM, "lockbox leaked into the pre-lockbox slice"
        pres.append(pre)
        rr, base = scan_leg(pre, cals, pre_td, args.perm, rng, years)
        rows.extend(rr)
        bases[leg["key"]] = base
        print(f"  [{leg['key']}] pre-lockbox {base['n']:,} trades  net ${base['net']:,.0f}  "
              f"DD ${base['dd']:,.0f}  MAR {base['mar']:.2f}  -> {len(rr)} cells")

    print(f"\n{HDR}")
    print("-" * len(HDR))
    interesting = [r for r in rows if args.print_all or (r["b0"] and r["b1"] and r["b2"])]
    for r in (rows if args.print_all else interesting):
        print(fmt_row(r))
    if not args.print_all:
        print(f"  ... {len(rows) - len(interesting)} further cells failed B0/B1/B2 and are in "
              f"the .md (use --print-all to dump every row here)")

    surv = [r for r in rows if r["survives"]]
    reached = [r for r in rows if r["perm_p"] is not None]
    null_counts = []
    if args.null_reps > 0:
        print(f"\nFAMILY-WIDE NULL (post-hoc diagnostic, NOT part of the bar) — "
              f"{args.null_reps} replicates with all ten calendars randomised")
        null_counts = family_null(pres, cals, pre_td, args.perm, args.null_reps,
                                  np.random.default_rng(SEED + 1), years)
        nc = np.array(null_counts, float)
        print(f"  real scan: {len(surv)} survivors of {len(rows)} cells   |   "
              f"random calendars: median {np.median(nc):.0f}, "
              f"range {nc.min():.0f}-{nc.max():.0f}, mean {nc.mean():.1f}   |   "
              f"P(null >= real) = {(nc >= len(surv)).mean():.3f}")

    print(f"\nCLAUSE COUNTS over {len(rows)} cells: "
          f"B0 {sum(r['b0'] for r in rows)}  B1 {sum(r['b1'] for r in rows)}  "
          f"B2 {sum(r['b2'] for r in rows)}  B0&B1&B2 {sum(r['b0'] and r['b1'] and r['b2'] for r in rows)}  "
          f"B3 {sum(r['b3'] for r in rows)}  reached-permutation {len(reached)}  "
          f"B4 {sum(r['b4'] for r in rows)}  SURVIVORS {len(surv)}")

    lockbox_rows = None
    if not args.no_lockbox:
        lockbox_rows = []
        if surv:
            print(f"\nLOCKBOX — THE SINGLE PEEK ({LOCKBOX_FROM} .. {DATE_TO}) for "
                  f"{len(surv)} surviving cells")
            lb_years = window_years(LOCKBOX_FROM.isoformat(), DATE_TO)
            lb_td = [d for d in trading_days if d >= LOCKBOX_FROM]
            lb_cals = build_all_calendars(lb_td, LOCKBOX_FROM.year, 2025)
            for r in surv:
                lb = slice_lockbox(recs[r["leg"]])
                dayset = shift_to_trading_days(lb_cals[r["calendar"]], lb_td, r["offset"])
                mask = cell_mask(lb, dayset, r["clock"])
                b = metrics(lb["pnl"], lb_years)
                s = metrics(apply_size(lb["pnl"], mask, r["m"]), lb_years)
                lockbox_rows.append(dict(r, n_affected=int(mask.sum()), base_net=b["net"],
                                         base_dd=b["dd"], base_mar=b["mar"], net=s["net"],
                                         dd=s["dd"], mar=s["mar"],
                                         d_net=s["net"] - b["net"], d_mar=s["mar"] - b["mar"]))
                print(f"  {r['leg']:6s} {r['calendar']:14s} {OFFSET_LABEL[r['offset']]:11s} "
                      f"{r['clock']:4s} m={r['m']:.1f}  LB n_aff {int(mask.sum()):4d}  "
                      f"base ${b['net']:+10,.0f} -> sized ${s['net']:+10,.0f} "
                      f"({s['net']-b['net']:+,.0f})   DD ${b['dd']:,.0f} -> ${s['dd']:,.0f}")
        else:
            print("\nLOCKBOX: nothing survived, so the seal was NOT broken.")

    fp = write_md(rows, bases, cals, verify, lockbox_rows, args, cal_paths, null_counts)
    print(f"\nwrote {fp}")
    print("VERDICT: " + (f"{len(surv)} surviving cell(s)" if surv else
                         "NOTHING SURVIVES — no scheduled-event size rule outside the known "
                         "FOMC hole clears the pre-registered bar"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
