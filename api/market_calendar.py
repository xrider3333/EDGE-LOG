"""US EQUITY (NYSE / Nasdaq) session calendar -- stdlib only, no pandas.

Built for api/qqq_exec.py: a market holiday must never count as a trading day, in
feed uptime, readiness, or signals_day. `pandas.tseries.holiday.USFederalHolidayCalendar`
is DELIBERATELY not used -- it includes Columbus Day and Veterans Day, which the US
equity market does NOT observe. Every holiday rule here is implemented explicitly.

Holidays covered: New Year's Day, Martin Luther King Jr. Day (3rd Mon Jan),
Washington's Birthday/Presidents Day (3rd Mon Feb), Good Friday (Easter Sunday - 2
days, Anonymous Gregorian algorithm), Memorial Day (last Mon May), Juneteenth (Jun 19,
observed by the equity market from 2022 onward), Independence Day, Labor Day (1st Mon
Sep), Thanksgiving (4th Thu Nov), Christmas Day.

Observed-holiday rule: a holiday that falls on Saturday is observed the preceding
Friday; one that falls on Sunday is observed the following Monday. Applies to every
fixed-date holiday above (New Year's, Juneteenth, Independence Day, Christmas) -- the
"nth weekday" holidays (MLK, Presidents, Memorial, Labor, Thanksgiving, Good Friday)
always land on a weekday already and never shift.

Half days (13:00 ET close instead of 16:00): the day after Thanksgiving; July 3 when
July 4 falls on a weekday other than Monday (Tue-Fri -- i.e. July 4 is NOT itself
shifted); December 24 when it falls Monday-Thursday. These are the standard NYSE/Nasdaq
early-close days.

CLI self-test: `python -m api.market_calendar --selftest`.
"""
import sys
from datetime import date, datetime, timedelta

__all__ = ["is_session", "session_close_et", "sessions_between", "holiday_name",
           "holiday_dates"]


# -- date coercion -------------------------------------------------------------------
def _coerce_date(d):
    if isinstance(d, datetime):
        return d.date()
    if isinstance(d, date):
        return d
    if isinstance(d, str):
        s = d.strip()[:10]
        return datetime.strptime(s, "%Y-%m-%d").date()
    raise TypeError(f"market_calendar: unsupported date type {type(d).__name__}: {d!r}")


# -- small calendar helpers -----------------------------------------------------------
def _nth_weekday(year, month, weekday, n):
    """The date of the n-th `weekday` (0=Mon..6=Sun) in `month`/`year`, 1-indexed."""
    d = date(year, month, 1)
    offset = (weekday - d.weekday()) % 7
    d = d + timedelta(days=offset)
    d = d + timedelta(days=7 * (n - 1))
    return d


def _last_weekday(year, month, weekday):
    """The date of the LAST `weekday` (0=Mon..6=Sun) in `month`/`year`."""
    if month == 12:
        first_of_next = date(year + 1, 1, 1)
    else:
        first_of_next = date(year, month + 1, 1)
    d = first_of_next - timedelta(days=1)
    offset = (d.weekday() - weekday) % 7
    return d - timedelta(days=offset)


def _easter(year):
    """Easter Sunday (Gregorian) via the Anonymous Gregorian / Meeus-Jones-Butcher
    algorithm. Returns a datetime.date."""
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    return date(year, month, day)


def _observed(d):
    """Saturday -> preceding Friday, Sunday -> following Monday, else unchanged.

    NOT for New Year's Day - use _observed_new_year, which carries the exchange's carve-out."""
    if d.weekday() == 5:      # Saturday
        return d - timedelta(days=1)
    if d.weekday() == 6:      # Sunday
        return d + timedelta(days=1)
    return d


def _observed_new_year(year):
    """The observed New Year's holiday for `year`, or None when there is not one.

    THE CARVE-OUT, and it is the exchange's own: a Saturday holiday is observed the preceding
    Friday UNLESS that Friday is the LAST BUSINESS DAY OF THE YEAR. New Year's Day is the only
    holiday that can land in that case, and it lands there every time - the preceding Friday is
    Dec 31 by definition. So a Saturday Jan 1 is not observed at all: the market TRADES on Dec 31
    and resumes normally on Monday Jan 3.

    Treating it like any other Saturday holiday is what made 2021-12-31 and 2027-12-31 read as
    holidays in this module while the NYSE was open both days."""
    d = date(year, 1, 1)
    if d.weekday() == 5:          # Saturday -> would be Dec 31, the last business day: not observed
        return None
    if d.weekday() == 6:          # Sunday -> Monday Jan 2, which is inside the same year
        return d + timedelta(days=1)
    return d


# -- holiday table (cached per year) ---------------------------------------------------
_HOLIDAY_CACHE = {}


def holiday_dates(year):
    """{date: name} of every NYSE/Nasdaq equity-market holiday whose OBSERVED date
    falls in `year`.

    Every observed date lands inside `year`: a Saturday New Year is NOT observed at all (see
    _observed_new_year), so nothing shifts back into December of the prior year. `_holidays_near`
    still merges year-1/year/year+1 because a Sunday Dec 25 or Jul 4 shifts forward, and because
    a caller near a year boundary wants both sides."""
    if year in _HOLIDAY_CACHE:
        return _HOLIDAY_CACHE[year]
    h = {}
    _ny = _observed_new_year(year)
    if _ny is not None:
        h[_ny] = "New Year's Day"
    h[_nth_weekday(year, 1, 0, 3)] = "Martin Luther King Jr. Day"
    h[_nth_weekday(year, 2, 0, 3)] = "Washington's Birthday"
    h[_easter(year) - timedelta(days=2)] = "Good Friday"
    h[_last_weekday(year, 5, 0)] = "Memorial Day"
    if year >= 2022:
        h[_observed(date(year, 6, 19))] = "Juneteenth"
    h[_observed(date(year, 7, 4))] = "Independence Day"
    h[_nth_weekday(year, 9, 0, 1)] = "Labor Day"
    h[_nth_weekday(year, 11, 3, 4)] = "Thanksgiving Day"
    h[_observed(date(year, 12, 25))] = "Christmas Day"
    _HOLIDAY_CACHE[year] = h
    return h


def _holidays_near(year):
    """Merged holiday_dates for year-1/year/year+1, so a date near either year boundary is
    judged against both sides.

    It does NOT exist to pull a New Year's holiday back onto Dec 31 - that shift was wrong and is
    gone (Jan 1 2022 was a Saturday and the NYSE traded Friday Dec 31 2021)."""
    merged = {}
    for y in (year - 1, year, year + 1):
        merged.update(holiday_dates(y))
    return merged


# -- public API -------------------------------------------------------------------------
def holiday_name(d):
    """Name of the holiday `d` falls on (its OBSERVED date), or None if `d` is not a
    recognised NYSE/Nasdaq holiday (including if it's just a weekend with no holiday)."""
    dd = _coerce_date(d)
    return _holidays_near(dd.year).get(dd)


def is_session(d):
    """False on weekends and on NYSE/Nasdaq holidays; True otherwise."""
    dd = _coerce_date(d)
    if dd.weekday() >= 5:   # Sat=5, Sun=6
        return False
    if dd in _holidays_near(dd.year):
        return False
    return True


def _is_half_day(dd):
    """True if `dd` is a recognised 13:00 ET early close: day after Thanksgiving;
    July 3 when July 4 falls on a weekday other than Monday; Dec 24 when it falls
    Monday-Thursday."""
    thanksgiving = _nth_weekday(dd.year, 11, 3, 4)
    if dd == thanksgiving + timedelta(days=1):
        return True
    jul4 = date(dd.year, 7, 4)
    if dd.month == 7 and dd.day == 3 and jul4.weekday() not in (0, 5, 6):
        # jul4 weekday: 0=Mon (no early close), 5/6=Sat/Sun (July 4 itself shifts off
        # July 3-4 entirely, so July 3 is not a special early-close day either).
        return True
    if dd.month == 12 and dd.day == 24 and dd.weekday() in (0, 1, 2, 3):
        return True
    return False


def session_close_et(d):
    """'16:00' normally, '13:00' on a recognised half day. Callers should check
    is_session(d) first -- this does not itself check whether `d` is a session."""
    dd = _coerce_date(d)
    return "13:00" if _is_half_day(dd) else "16:00"


def sessions_between(start, end):
    """Sorted list of datetime.date -- every NYSE/Nasdaq session day in [start, end]
    inclusive."""
    s = _coerce_date(start)
    e = _coerce_date(end)
    if e < s:
        s, e = e, s
    out = []
    d = s
    one = timedelta(days=1)
    while d <= e:
        if is_session(d):
            out.append(d)
        d += one
    return out


# -- self-test ----------------------------------------------------------------------------
def _selftest():
    cases = [
        ("2024-03-29", False, "Good Friday"),
        ("2025-01-09", True, None),
        ("2025-06-19", False, "Juneteenth"),
        ("2026-01-19", False, "Martin Luther King Jr. Day"),
        ("2026-09-07", False, "Labor Day"),
        ("2026-11-26", False, "Thanksgiving Day"),
        ("2026-12-25", False, "Christmas Day"),
        ("2027-01-01", False, "New Year's Day"),
        # A SATURDAY NEW YEAR DOES NOT CLOSE THE PRECEDING FRIDAY. The exchange observes a
        # Saturday holiday on the preceding Friday UNLESS that Friday is the last business day
        # of the year - and for New Year's it always is. This module used to shift it back and
        # so called two real trading days holidays.
        ("2021-12-31", True, None),      # Jan 1 2022 was a Saturday; the NYSE traded this day
        ("2027-12-31", True, None),      # Jan 1 2028 is a Saturday; same carve-out
        ("2022-01-03", True, None),      # and the Monday after is an ordinary session
        ("2023-01-02", False, "New Year's Day"),   # Sunday Jan 1 DOES shift forward to Monday
        ("2021-01-01", False, "New Year's Day"),   # a weekday Jan 1 is itself the holiday
        # observed-shift cases: the actual Jul-4 date is a plain weekend (not itself a
        # holiday key -- only the OBSERVED date carries the name), so holiday_name is
        # None there; the observed date is what actually closes the market.
        ("2027-07-04", False, None),                 # Sunday -> observed Monday 07-05
        ("2027-07-05", False, "Independence Day"),   # the observed date itself
        ("2026-07-04", False, None),                 # Saturday -> observed Friday 07-03
        ("2026-07-03", False, "Independence Day"),   # the observed date itself
    ]
    half_day_cases = [
        ("2026-11-27", "13:00"),  # day after Thanksgiving
    ]
    ok = True
    for ds, expect_session, expect_holiday in cases:
        got_session = is_session(ds)
        got_name = holiday_name(ds)
        pass_ = (got_session == expect_session) and (
            (expect_holiday is None and got_name is None) or
            (expect_holiday is not None and got_name == expect_holiday))
        print(f"{'PASS' if pass_ else 'FAIL'} is_session({ds})={got_session} "
              f"(want {expect_session}) holiday_name={got_name!r} (want {expect_holiday!r})")
        ok = ok and pass_
    for ds, expect_close in half_day_cases:
        got = session_close_et(ds)
        pass_ = got == expect_close
        print(f"{'PASS' if pass_ else 'FAIL'} session_close_et({ds})={got!r} (want {expect_close!r})")
        ok = ok and pass_
    # 2027-07-04 is genuinely a Sunday and 2026-07-04 genuinely a Saturday -- assert the
    # weekday assumptions the observed-shift cases above depend on, so a bug in the case
    # data itself would be caught rather than silently validating the wrong thing.
    wd_checks = [("2027-07-04", 6), ("2026-07-04", 5)]
    for ds, want_wd in wd_checks:
        got_wd = _coerce_date(ds).weekday()
        pass_ = got_wd == want_wd
        print(f"{'PASS' if pass_ else 'FAIL'} weekday({ds})={got_wd} (want {want_wd})")
        ok = ok and pass_
    print("SELFTEST: PASS" if ok else "SELFTEST: FAIL")
    return ok


def main():
    if "--selftest" in sys.argv:
        ok = _selftest()
        sys.exit(0 if ok else 1)
    print(__doc__)


if __name__ == "__main__":
    main()
