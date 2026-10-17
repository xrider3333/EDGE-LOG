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
look-ahead. Inside the loaded span the calendar is the data's OWN session dates (what the strategy can trade; on
NOADJ_NQ_5m_RTH.csv 2010-06-07..2016-06-30 this marks 219 last-3 sessions = 73 months x 3, TTM's literal build). Past
either end of the loaded data (a load that starts or ends mid-month) it is extended with the CME equity-index
regular-hours calendar (`exchange_sessions`: every weekday except New Year's Day, Good Friday, Christmas - each as
observed - and the full closures in SPECIAL_CLOSURES; the US holidays on which the CME trades a shortened session -
MLK, Presidents, Memorial, Juneteenth, Independence, Labor, Thanksgiving - ARE sessions, as on the house masters
2014-2016). So a load that ends on 2025-06-27 still knows 2025-06-30 is June's last session, and truncating the data
never changes an earlier bar's answer (when the data's sessions match the exchange's). One caveat, stated: a session
MISSING from the data inside the span (a data hole, e.g. 2014-12-31 on NOADJ_NQ_5m_RTH.csv) is not on the calendar the
helpers read - the data's own dates rule inside the span.

Pure numpy / pandas, no I/O; the QWEN LAB safety gate allows `from augur_engine.session_calendar import <name>`.
"""
from __future__ import annotations

import datetime as _dt

import numpy as np
import pandas as pd

__all__ = ["session_calendar", "session_dates", "session_index_in_month", "days_to_month_end",
           "is_last_n_sessions_of_month", "is_first_n_sessions_of_month", "week_of_month", "exchange_sessions",
           "is_exchange_session", "closed_days", "SPECIAL_CLOSURES"]

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


def exchange_sessions(d0, d1):
    """[datetime.date] of the CME equity-index regular-hours sessions from d0 to d1 inclusive (the published
    calendar - knowable in advance)."""
    a, b = pd.Timestamp(d0).date(), pd.Timestamp(d1).date()
    out = []
    d = a
    while d <= b:
        if is_exchange_session(d):
            out.append(d)
        d += _dt.timedelta(days=1)
    return out


def _ymd(d):
    return d.year * 10000 + d.month * 100 + d.day


def _month_bounds(ymd):
    """(first day, last day) of the calendar month of an int YYYYMMDD."""
    y, m = int(ymd) // 10000, (int(ymd) // 100) % 100
    first = _dt.date(y, m, 1)
    nxt = _dt.date(y + (m == 12), 1 if m == 12 else m + 1, 1)
    return first, nxt - _dt.timedelta(days=1)


def _bar_ymd(index):
    """int64 YYYYMMDD of every bar, in the index's own clock (US/Eastern on the house masters)."""
    idx = pd.DatetimeIndex(index)
    return (np.asarray(idx.year, dtype=np.int64) * 10000 + np.asarray(idx.month, dtype=np.int64) * 100
            + np.asarray(idx.day, dtype=np.int64))


def session_calendar(index, day_id=None):
    """Per-bar calendar facts (numpy int64 arrays): date (YYYYMMDD of the bar's session = the date of the
    session's first bar), year, month, day, weekday (0 = Monday), session_index_in_month (0 = the month's first
    trading session), sessions_in_month, days_to_month_end (sessions LEFT in the month after this one; 0 = the last),
    week_of_month (1 + (day - 1) // 7). Sessions are day_id runs (or the bar date without day_id). The calendar is the
    data's own session dates inside the loaded span, extended past its ends by exchange_sessions (see the module
    docstring)."""
    ymd = _bar_ymd(index)
    n = len(ymd)
    keys = ("date", "year", "month", "day", "weekday", "session_index_in_month", "sessions_in_month",
            "days_to_month_end", "week_of_month")
    if n == 0:
        return {k: np.zeros(0, dtype=np.int64) for k in keys}
    key = np.asarray(day_id) if day_id is not None else ymd
    if len(key) != n:
        raise ValueError("session_calendar: day_id has %d rows, index %d" % (len(key), n))
    starts = np.flatnonzero(np.r_[True, key[1:] != key[:-1]])
    lens = np.diff(np.r_[starts, n])
    sess = ymd[starts]                                           # one date per session (its first bar's)
    have = np.unique(sess)
    lo, hi = _month_bounds(have[0])[0], _month_bounds(have[-1])[1]
    first = _dt.date(int(have[0]) // 10000, (int(have[0]) // 100) % 100, int(have[0]) % 100)
    last = _dt.date(int(have[-1]) // 10000, (int(have[-1]) // 100) % 100, int(have[-1]) % 100)
    ext = [_ymd(d) for d in exchange_sessions(lo, first - _dt.timedelta(days=1))] + \
          [_ymd(d) for d in exchange_sessions(last + _dt.timedelta(days=1), hi)]
    cal = np.unique(np.r_[have, np.asarray(ext, dtype=np.int64)])
    month = cal // 100
    mstart = np.flatnonzero(np.r_[True, month[1:] != month[:-1]])
    msize = np.diff(np.r_[mstart, len(cal)])
    gid = np.repeat(np.arange(len(mstart)), msize)
    pos = np.arange(len(cal)) - mstart[gid]
    size = msize[gid]
    p = np.searchsorted(cal, sess)
    s_pos, s_size = pos[p], size[p]
    y, m, d = sess // 10000, (sess // 100) % 100, sess % 100
    wd = np.asarray(pd.DatetimeIndex(index)[starts].weekday, dtype=np.int64)
    per_session = {"date": sess, "year": y, "month": m, "day": d, "weekday": wd, "session_index_in_month": s_pos,
                   "sessions_in_month": s_size, "days_to_month_end": s_size - 1 - s_pos,
                   "week_of_month": 1 + (d - 1) // 7}
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
