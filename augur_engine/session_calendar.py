# -*- coding: utf-8 -*-
"""Session-calendar helpers for strategy files: REAL dates for calendar rules (MANAGER #156, QWEN LAB fix round 3).

Why: a strategy gets `day_id`, a bare session NUMBER, so a calendar rule (the turn of the month, the last N sessions of
a month, an options-expiry week) could not be built - the lab's QL_TOM_CALENDAR_NQ counted 21-session blocks from the
load start and traded 3 times in six years. The engine already hands a strategy the bar timestamps when its
run_backtest DECLARES an `index` keyword (engine.py, auto.py, optimize.py, rolls.py: `"index" in signature`): the bar
OPEN times, US/Eastern on the house masters. These helpers turn that index (plus day_id) into calendar facts, ONE
value per BAR (equal on every bar of a session), so a rule reads them at the bar it decides on:

    from augur_engine.session_calendar import is_last_n_sessions_of_month
    last3 = is_last_n_sessions_of_month(index, 3, day_id)        # True on the last 3 trading sessions of each month
    ...
    if last3[a]:                                                 # a = the session's first bar
        ...

    session_dates(index, day_id)                 int YYYYMMDD of the bar's session
    session_index_in_month(index, day_id)        0 = the first trading session of the calendar month
    days_to_month_end(index, day_id)             trading sessions LEFT in the month after this one (0 = the last)
    is_last_n_sessions_of_month(index, n, day_id)    days_to_month_end < n
    is_first_n_sessions_of_month(index, n, day_id)   session_index_in_month < n
    week_of_month(index, day_id)                 1 + (day of month - 1) // 7: days 1-7 = week 1 (a third Friday is
                                                 always in week 3)
    session_calendar(index, day_id)              a dict of all of the above per bar, plus year / month / day /
                                                 weekday (0 = Monday) / sessions_in_month

THE CALENDAR THEY READ. The month-end helpers need the FUTURE session calendar (is today one of the last 3 sessions of
the month?). That is the exchange's published trading calendar, known in advance - not a price - so reading it is not
look-ahead. The positions and counts are read from the CME equity-index regular-hours calendar ALONE, across the whole
span (`exchange_sessions`: every weekday except New Year's Day, Good Friday, Christmas - each as observed - and the
full closures in SPECIAL_CLOSURES; the US holidays on which the CME trades a shortened session - MLK, Presidents,
Memorial, Juneteenth, Independence, Labor, Thanksgiving - ARE sessions, as on the house masters 2014-2016), never from
the data's own dates. So the answer for a bar is a function of its date alone: truncating the data, starting the load
later, or a hole in the data never changes it (tested, incl. the real holes of the RTH masters). A session MISSING
from the data (a data hole: all 7 pinned RTH masters lack the same 15 published sessions 2012-11-22..2014-12-31, e.g.
2014-12-31 and Thanksgiving 2013) still counts - it is a session with no bars to trade - so on NOADJ_NQ_5m_RTH.csv
2010-06-07..2016-06-30 is_last_n_sessions_of_month(index, 3) marks 217 tradable sessions: 73 months x 3 minus
2013-11-28 and 2014-12-31 (review round 4: the old 'data's own dates inside the span' build marked 219 - 2013-11-26 and
2014-12-26 only on a load that reached the next month, i.e. not causal). A data session OFF the published calendar
(none on the house masters 2010-2025) gets its position among the published sessions around it and shifts no other
session's count.

THE DATE OF A SESSION is its TRADING day (`_trading_ymd`): each bar's US/Eastern date, or the NEXT day for a bar at or
after 18:00 ET (the CME's 18:00 roll - a Sunday 18:00 bar trades Monday's session). Regular-hours bars keep their own
date. Sessions are the runs of day_id (or of the bar date without day_id) split where the trading day changes, so an
ETH master whose day_id is the ET calendar date (load_master_arrays) or an 18:00 trading day both date every bar right
(review round 4: dating a session by its first bar's calendar date counted 13 Sunday-evening chunks as sessions in
2016-01..03 - Feb 2016 had 25 'sessions' - and dated Monday's 18:00-roll sessions Sunday). A tz-aware index is read on
the US/Eastern clock; a naive one is taken as US/Eastern (the house masters).

Pure numpy / pandas, no I/O; the QWEN LAB safety gate allows `from augur_engine.session_calendar import <name>`.
"""
from __future__ import annotations

import datetime as _dt

import numpy as np
import pandas as pd

__all__ = ["session_calendar", "session_dates", "session_index_in_month", "days_to_month_end",
           "is_last_n_sessions_of_month", "is_first_n_sessions_of_month", "week_of_month", "exchange_sessions",
           "is_exchange_session", "closed_days", "SPECIAL_CLOSURES", "holiday_sessions", "is_holiday_session",
           "holiday_close"]

# full regular-hours closures beyond the yearly rules (NYSE closed; the CME equity-index RTH tape has no session)
SPECIAL_CLOSURES = frozenset(_dt.date.fromisoformat(d) for d in (
    "2001-09-11", "2001-09-12", "2001-09-13", "2001-09-14",      # September 11
    "2004-06-11",                                                # President Reagan's funeral
    "2007-01-02",                                                # President Ford's funeral
    "2012-10-29", "2012-10-30",                                  # Hurricane Sandy
    "2018-12-05",                                                # President G.H.W. Bush's funeral
    "2025-01-09",                                                # President Carter's funeral
))
_CLOSED_CACHE = {}


def _easter(year):
    """Easter Sunday (Gregorian; the Anonymous / Meeus-Jones-Butcher algorithm)."""
    a, b, c = year % 19, year // 100, year % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l_ = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l_) // 451
    month = (h + l_ - 7 * m + 114) // 31
    day = ((h + l_ - 7 * m + 114) % 31) + 1
    return _dt.date(year, month, day)


def _observed(d):
    """A Saturday holiday is observed the Friday before, a Sunday one the Monday after."""
    if d.weekday() == 5:
        return d - _dt.timedelta(days=1)
    if d.weekday() == 6:
        return d + _dt.timedelta(days=1)
    return d


def closed_days(year):
    """The weekdays of `year` with NO regular-hours CME equity-index session: New Year's Day (a Sunday one observed
    on Monday; a Saturday one is not observed - Dec 31 trades), Good Friday, Christmas (observed), and the
    SPECIAL_CLOSURES of that year."""
    if year in _CLOSED_CACHE:
        return _CLOSED_CACHE[year]
    out = set()
    ny = _dt.date(year, 1, 1)
    if ny.weekday() == 6:
        out.add(ny + _dt.timedelta(days=1))
    elif ny.weekday() < 5:
        out.add(ny)
    out.add(_easter(year) - _dt.timedelta(days=2))
    out.add(_observed(_dt.date(year, 12, 25)))
    out |= {d for d in SPECIAL_CLOSURES if d.year == year}
    _CLOSED_CACHE[year] = frozenset(out)
    return _CLOSED_CACHE[year]


def is_exchange_session(d):
    """True when date `d` has a regular-hours session on the CME equity-index calendar."""
    d = pd.Timestamp(d).date()
    return d.weekday() < 5 and d not in closed_days(d.year)


# CME equity-index HOLIDAY SHORT SESSIONS (MANAGER #98-1 / #108, 10-19): the US holidays on which the NYSE is closed
# but the CME equity-index futures trade a session that halts at 12:00 CT = 13:00 ET (10:30 CT = 11:30 ET on the
# house masters through 2012-09-03): MLK (3rd Monday of January), Presidents' (3rd Monday of February), Memorial (last
# Monday of May), Juneteenth (June 19 as observed, from 2022), Independence (July 4 as observed), Labor (1st Monday of
# September), Thanksgiving (4th Thursday of November). Verified 10-19 against the NQ/ES 5m RTH and ETH masters
# 2010-06..2026-10 (tools/splice_nt_sessions.py has the detail). They ARE exchange sessions (is_exchange_session).
# Shared by tools/splice_nt_sessions.py (the session window) and tools/refresh_resampled_masters.py (the RTH close a
# coarse bucket runs to).
HOLIDAY_CLOSE = (13, 0)                                          # ET hour, minute
HOLIDAY_CLOSE_OLD = (11, 30)
HOLIDAY_OLD_LAST = _dt.date(2012, 9, 3)                          # the last holiday session ending 11:30 ET
_HOLIDAY_CACHE = {}


def _nth_weekday(year, month, weekday, n):
    d = _dt.date(year, month, 1)
    return d + _dt.timedelta(days=(weekday - d.weekday()) % 7 + 7 * (n - 1))


def _last_weekday(year, month, weekday):
    d = _dt.date(year + (month == 12), month % 12 + 1, 1) - _dt.timedelta(days=1)
    return d - _dt.timedelta(days=(d.weekday() - weekday) % 7)


def holiday_sessions(year):
    """{date: name} of the CME equity-index holiday short sessions of `year` (NYSE closed, CME to 13:00 ET)."""
    if year not in _HOLIDAY_CACHE:
        h = {_nth_weekday(year, 1, 0, 3): "Martin Luther King Jr. Day", _nth_weekday(year, 2, 0, 3): "Presidents' Day",
             _last_weekday(year, 5, 0): "Memorial Day", _observed(_dt.date(year, 7, 4)): "Independence Day",
             _nth_weekday(year, 9, 0, 1): "Labor Day", _nth_weekday(year, 11, 3, 4): "Thanksgiving"}
        if year >= 2022:
            h[_observed(_dt.date(year, 6, 19))] = "Juneteenth"
        shut = closed_days(year)                         # New Year, Good Friday, Christmas + the special closures
        _HOLIDAY_CACHE[year] = {d: n for d, n in sorted(h.items()) if d not in shut}
    return _HOLIDAY_CACHE[year]


def is_holiday_session(d):
    """True when date `d` is a CME equity-index holiday short session (see holiday_sessions)."""
    d = pd.Timestamp(d).date()
    return d in holiday_sessions(d.year)


def holiday_close(d):
    """(hour, minute) ET at which the CME holiday short session on `d` halts, or None when `d` is not one."""
    d = pd.Timestamp(d).date()
    if d not in holiday_sessions(d.year):
        return None
    return HOLIDAY_CLOSE_OLD if d <= HOLIDAY_OLD_LAST else HOLIDAY_CLOSE


def _exchange_days(d0, d1):
    """numpy datetime64[D] of the CME equity-index regular-hours sessions from d0 to d1 inclusive (vectorised)."""
    a, b = pd.Timestamp(d0).date(), pd.Timestamp(d1).date()
    if b < a:
        return np.zeros(0, dtype="datetime64[D]")
    days = np.arange(np.datetime64(a, "D"), np.datetime64(b, "D") + np.timedelta64(1, "D"))
    days = days[(days.astype(np.int64) + 3) % 7 < 5]             # 1970-01-01 was a Thursday (weekday 3)
    shut = [np.datetime64(d, "D") for y in range(a.year, b.year + 1) for d in closed_days(y)]
    if shut:
        days = days[~np.isin(days, np.asarray(shut, dtype="datetime64[D]"))]
    return days


def exchange_sessions(d0, d1):
    """[datetime.date] of the CME equity-index regular-hours sessions from d0 to d1 inclusive (the published
    calendar - knowable in advance)."""
    return [d.item() for d in _exchange_days(d0, d1)]


def _ymd(d):
    return d.year * 10000 + d.month * 100 + d.day


def _days_ymd(days):
    """int64 YYYYMMDD of a datetime64[D] array."""
    di = pd.DatetimeIndex(days)
    return (np.asarray(di.year, dtype=np.int64) * 10000 + np.asarray(di.month, dtype=np.int64) * 100
            + np.asarray(di.day, dtype=np.int64))


def _month_bounds(ymd):
    """(first day, last day) of the calendar month of an int YYYYMMDD."""
    y, m = int(ymd) // 10000, (int(ymd) // 100) % 100
    first = _dt.date(y, m, 1)
    nxt = _dt.date(y + (m == 12), 1 if m == 12 else m + 1, 1)
    return first, nxt - _dt.timedelta(days=1)


ROLL_HOUR_ET = 18                                                # the CME equity-index trading day starts 18:00 ET


def _trading_ymd(index):
    """int64 YYYYMMDD of every bar's TRADING day: its US/Eastern date, the next day for a bar at or after 18:00 ET (a
    Sunday 18:00 bar trades Monday's session). A tz-aware index is read on the US/Eastern clock, a naive one as
    US/Eastern. Regular-hours bars keep their own date."""
    idx = pd.DatetimeIndex(index)
    if idx.tz is not None:
        idx = idx.tz_convert("US/Eastern").tz_localize(None)
    day = idx.normalize() + pd.to_timedelta((np.asarray(idx.hour) >= ROLL_HOUR_ET).astype(np.int64), unit="D")
    return (np.asarray(day.year, dtype=np.int64) * 10000 + np.asarray(day.month, dtype=np.int64) * 100
            + np.asarray(day.day, dtype=np.int64))


def session_calendar(index, day_id=None):
    """Per-bar calendar facts (numpy int64 arrays): date (YYYYMMDD of the bar's session = its TRADING day, see the
    module docstring), year, month, day, weekday (0 = Monday, of that date), session_index_in_month (published sessions
    of the month BEFORE this one: 0 = the month's first trading session), sessions_in_month (published sessions in
    the month), days_to_month_end (published sessions LEFT in the month after this one; 0 = the last), week_of_month
    (1 + (day - 1) // 7). Sessions are the runs of day_id (or of the bar date without day_id), split where the trading
    day changes. Positions and counts come from the published exchange calendar alone (exchange_sessions), never from
    the data's own dates - so a data hole, a truncation or a later load start never changes an answer."""
    ymd = _trading_ymd(index)
    n = len(ymd)
    keys = ("date", "year", "month", "day", "weekday", "session_index_in_month", "sessions_in_month",
            "days_to_month_end", "week_of_month")
    if n == 0:
        return {k: np.zeros(0, dtype=np.int64) for k in keys}
    key = np.asarray(day_id) if day_id is not None else ymd
    if len(key) != n:
        raise ValueError("session_calendar: day_id has %d rows, index %d" % (len(key), n))
    starts = np.flatnonzero(np.r_[True, (key[1:] != key[:-1]) | (ymd[1:] != ymd[:-1])])
    lens = np.diff(np.r_[starts, n])
    sess = ymd[starts]                                           # one trading day per session
    lo, hi = _month_bounds(int(sess.min()))[0], _month_bounds(int(sess.max()))[1]
    ex = _days_ymd(_exchange_days(lo, hi))                       # the published calendar, whole months, sorted
    mo = (sess // 100) * 100
    m0 = np.searchsorted(ex, mo, side="left")                    # the month's first published session
    m1 = np.searchsorted(ex, mo + 99, side="right")              # one past its last
    before = np.searchsorted(ex, sess, side="left")              # published sessions before this date
    after = np.searchsorted(ex, sess, side="right")              # the first published session after it
    s_pos, s_size, s_left = before - m0, m1 - m0, m1 - after
    y, m, d = sess // 10000, (sess // 100) % 100, sess % 100
    wd = np.asarray(pd.to_datetime(sess.astype(str), format="%Y%m%d").weekday, dtype=np.int64)
    per_session = {"date": sess, "year": y, "month": m, "day": d, "weekday": wd, "session_index_in_month": s_pos,
                   "sessions_in_month": s_size, "days_to_month_end": s_left, "week_of_month": 1 + (d - 1) // 7}
    return {k: np.repeat(np.asarray(v, dtype=np.int64), lens) for k, v in per_session.items()}


def session_dates(index, day_id=None):
    """int64 YYYYMMDD of each bar's session (the date of the session's first bar)."""
    return session_calendar(index, day_id)["date"]


def session_index_in_month(index, day_id=None):
    """0-based index of each bar's session within its calendar month (0 = the month's first trading session)."""
    return session_calendar(index, day_id)["session_index_in_month"]


def days_to_month_end(index, day_id=None):
    """Trading sessions left in the calendar month AFTER each bar's session (0 on the month's last session)."""
    return session_calendar(index, day_id)["days_to_month_end"]


def week_of_month(index, day_id=None):
    """1 + (day of month - 1) // 7 of each bar's session: days 1-7 = week 1, 8-14 = week 2, ... (1..5)."""
    return session_calendar(index, day_id)["week_of_month"]


def is_last_n_sessions_of_month(index, n, day_id=None):
    """True on every bar of the last `n` trading sessions of each calendar month."""
    return session_calendar(index, day_id)["days_to_month_end"] < int(n)


def is_first_n_sessions_of_month(index, n, day_id=None):
    """True on every bar of the first `n` trading sessions of each calendar month."""
    return session_calendar(index, day_id)["session_index_in_month"] < int(n)
