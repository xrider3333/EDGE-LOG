"""tools/webull_freshness.py -- QQQ_1d STALE: TRUE IMPACT (MANAGER GO 2026-10-25).

A QQQ_1d.csv that HAS rows but lacks the newest sessions used to page "NOISE trades on a price
history that is a day short" (the 09:40 session check, and the pre-open gate's out-of-date miss).
The engine's code says what it really does (proved on the box's real bars in
tests/test_cloud_signal_qqq_1d_stale.py); the monitor now words each case from the 5m cache's tail:

  1. the lacking sessions WHOLE in the 5m cache: DIP #424 is unchanged, NOISE "can change only on
     a day right at its limit" -- still HIGH (a skip right at the line can flip); one or more
     sessions behind, a half day too;
  2. one PART-way there: "DIP #424 decides on only part of <day>'s prices" (+ NOISE's line);
  3. one MISSING there: "DIP #424 takes no new trades and sends no exit for its held shares";
  4. the two files sharing under 20 sessions: DIP not trading and NOISE's vol skip on the 5m
     window alone (off under 60 sessions);
  5. a 5m cache deep enough for both (253+ whole sessions COUNTED in the file): "not affected", a
     default note; one only the calendar calls deep -- a torn first row (09-18's time=200960, or
     one that still reads as an RTH bar), holes in the history -- pages HIGH at 09:47 and 08:30;
  6. a newest bar or a 5m cache that cannot be read: a hedged "may" line;
  7. the pre-open gate's out-of-date miss is worded the same way; every note passes lint;
  8. the tail read: only the sessions after the daily file's newest bar, one 64 KB read while it
     is current, growing chunks when it is far behind, the full read only when the two files
     share under 20 sessions or the daily file is behind a cache the calendar calls deep (never
     while it is current); never raises.
Reuses tests/test_webull_freshness.py's fixture home. No push, no systemctl, no live file.
"""
import datetime as dt
import importlib.util
import os

import pytest

from api import ntfy_push

_spec = importlib.util.spec_from_file_location(
    "webull_freshness_helpers_q1d_stale",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_webull_freshness.py"))
T = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(T)
wf = T.wf
et = T.et

MON = dt.date(2026, 10, 5)
THU, FRI = dt.date(2026, 10, 1), dt.date(2026, 10, 2)
HEADER = "time,open,high,low,close,volume\n"
DIP_STOPS = "DIP #424 takes no new trades and sends no exit for its held shares"
AT_LINE = "NOISE's vol skip can change only on a day right at its limit"


@pytest.fixture(autouse=True)
def _no_ping(monkeypatch):
    monkeypatch.delenv("EDGELOG_FRESHNESS_PING_URL", raising=False)


def _sessions_before(day, n):
    out, d = [], day
    while len(out) < n:
        d = wf.prev_session(d)
        out.append(d)
    return out[::-1]


def _write_5m(h, days, spans=None, now=None):
    """QQQ_5m.csv with every 5m bar of each of `days` (09:30 .. 5 minutes before its close); a
    day in `spans` only from its (start, end) bar times; plus today's bars to the newest closed."""
    now = now or h.now
    rows = [HEADER]
    newest = int(now.timestamp()) // 300 * 300 - 300
    for day in list(days) + [now.date()]:
        if day in (spans or {}):
            first, last = spans[day]
        elif wf.market_calendar.is_session(day):
            ch, cm = wf.close_hhmm(day)
            first, last = (9, 30), divmod(ch * 60 + cm - 5, 60)
        else:
            continue
        t, end = wf.at(day, first), wf.at(day, last)
        while t <= end and t.timestamp() <= newest:
            rows.append(f"{int(t.timestamp())},1,1,1,1,1\n")
            t += dt.timedelta(minutes=5)
    T._w(h.paths["qqq_5m"], "".join(rows))


def _home(tmp_path, now, d1_day, k5=93, spans=None, drop=()):
    """The fixture box at `now`: QQQ_1d.csv's newest bar `d1_day`, `k5` sessions in the 5m cache
    before today (whole, but `spans` / without `drop`)."""
    h = T.Home(tmp_path, now)
    h.bars(now, d1_day=d1_day)
    _write_5m(h, [d for d in _sessions_before(now.date(), k5) if d not in drop], spans)
    return h


def _set_d1(h, day):
    """QQQ_1d.csv with one row, its newest bar `day` (Home.bars' daily file, the 5m left alone)."""
    e = int(dt.datetime(day.year, day.month, day.day, tzinfo=wf.ET).timestamp())
    T._w(h.paths["qqq_1d"], HEADER + f"{e},1,1,1,1,1\n")


def _stale(h):
    return wf.qqq_1d_stale(wf.collect(h.paths, h.run_cmd), h.now.date())


def _session_note(h):
    """The 09:40 session check's one push for it (2 runs in a row, from 09:45)."""
    h.advance(h.now.replace(hour=9, minute=45, second=30))
    h.run()
    h.advance(h.now.replace(minute=47))
    h.run()
    (p,) = [x for x in h.pushes if x["title"] != "QQQ book: OK"]
    assert ntfy_push.lint(p) == []
    return p


def _trading(p):
    return p["message"].split("\n")[0]


def lint_ok(p):
    return ntfy_push.lint(p) == []


# -- 1. whole in the 5m cache -------------------------------------------------------------------
def test_one_session_behind_whole_in_the_5m_cache(tmp_path):
    h = _home(tmp_path, et(2026, 10, 5, 9, 44), THU)
    s = _stale(h)
    assert s["lacking"] == [FRI] and s["affects"] == AT_LINE == wf.NOISE_AT_THE_LINE
    assert s["dev"] == ("lacks 2026-10-02: DIP #424 unchanged (the 5m cache holds those sessions "
                        "whole); NOISE's vol-skip scale is measured on 1 session(s) fewer (the "
                        "same daily dates; only a rank right at the skip line can change)")
    p = _session_note(h)
    assert p["title"] == "QQQ book: CHECK NOW" and p["priority"] == "high"
    assert p["message"] == ("Trading: AFFECTED - " + AT_LINE + ".\n"
                            "The QQQ daily price history was not updated this morning.\n"
                            "Do: ask Claude (PAPER-WB chat).")


def test_two_sessions_behind_across_a_holiday_and_a_half_day(tmp_path):
    h = _home(tmp_path, et(2026, 12, 1, 9, 44), dt.date(2026, 11, 25))
    s = _stale(h)
    assert s["lacking"] == [dt.date(2026, 11, 27), dt.date(2026, 11, 30)]   # 11-26: closed
    assert s["affects"] == AT_LINE and "DIP #424 unchanged" in s["dev"]
    assert "measured on 2 session(s) fewer" in s["dev"]


# -- 2. part-way in the 5m cache ----------------------------------------------------------------
@pytest.mark.parametrize("span", [((9, 30), (12, 0)), ((9, 40), (15, 55)), ((10, 0), (11, 0))])
def test_a_partial_lacking_session(tmp_path, span):
    h = _home(tmp_path, et(2026, 10, 5, 9, 44), THU, spans={FRI: span})
    s = _stale(h)
    assert s["affects"] == "DIP #424 decides on only part of Friday's prices, and " + AT_LINE
    assert "PARTIAL 5m session for 2026-10-02" in s["dev"]
    p = _session_note(h)
    assert _trading(p) == ("Trading: AFFECTED - DIP #424 decides on only part of Friday's "
                           "prices, and " + AT_LINE + ".")


def test_a_half_day_is_whole_at_12_55_and_partial_before(tmp_path):
    half = dt.date(2026, 11, 27)
    now = et(2026, 11, 30, 9, 44)
    whole = _home(tmp_path / "w", now, dt.date(2026, 11, 25))
    assert "DIP #424 unchanged" in _stale(whole)["dev"]
    cut = _home(tmp_path / "c", now, dt.date(2026, 11, 25), spans={half: ((9, 30), (12, 50))})
    assert _stale(cut)["affects"].startswith("DIP #424 decides on only part of Friday's prices")


def test_two_partial_sessions(tmp_path):
    h = _home(tmp_path, et(2026, 10, 5, 9, 44), dt.date(2026, 9, 30),
              spans={THU: ((9, 30), (12, 0)), FRI: ((9, 30), (15, 0))})
    assert _stale(h)["affects"] == "DIP #424 decides on only part of 2 days' prices, and " + AT_LINE


# -- 3. missing from the 5m cache ---------------------------------------------------------------
def test_a_lacking_session_missing_from_the_5m_cache(tmp_path):
    h = _home(tmp_path, et(2026, 10, 5, 9, 44), THU, drop=(FRI,))
    s = _stale(h)
    assert s["affects"] == DIP_STOPS                    # NOISE: nothing it lacks is in its scale
    assert "NOT READY (2026-10-02 in neither file" in s["dev"]
    assert "NOISE unchanged (no lacking session is in its scale)" in s["dev"]
    assert _trading(_session_note(h)) == "Trading: AFFECTED - " + DIP_STOPS + "."


def test_one_missing_and_one_whole(tmp_path):
    h = _home(tmp_path, et(2026, 10, 5, 9, 44), dt.date(2026, 9, 30), drop=(THU,))
    s = _stale(h)
    assert s["affects"] == DIP_STOPS + ", and " + AT_LINE
    assert "NOT READY (2026-10-01 in neither file" in s["dev"]


# -- 4. the two files sharing under 20 sessions -------------------------------------------------
@pytest.mark.parametrize("k5, behind, noise", [
    (25, 10, "NOISE's vol skip is off"),                               # 24 sessions: under 60
    (93, 80, "NOISE's vol skip ranks on 92 sessions, not 252"),
    (93, 100, "NOISE's vol skip ranks on 92 sessions, not 252"),       # ends before the 5m cache
])
def test_far_behind(tmp_path, k5, behind, noise):
    now = et(2026, 10, 5, 9, 44)
    d1 = _sessions_before(MON, behind + 1)[0]
    h = _home(tmp_path, now, d1, k5=k5)
    s = _stale(h)
    assert s["affects"] == DIP_STOPS + ", and " + noise
    assert f"under {wf.DAILY_MIN_OVERLAP}; the engine's vol-window note pages that too" in s["dev"]
    assert lint_ok(_session_note(h))


# -- 5. a 5m cache deep enough for both legs ----------------------------------------------------
def test_a_deep_5m_cache_is_not_affected(tmp_path):
    h = _home(tmp_path, et(2026, 10, 5, 9, 44), THU, k5=300)
    s = _stale(h)
    assert s["affects"] is None
    assert "NOISE unchanged (its 252-session window is all 5m)" in s["dev"]
    p = _session_note(h)
    assert p["title"] == "QQQ book: needs a fix" and p["priority"] == "default"
    assert _trading(p) == "Trading: not affected."


# -- 5b. "not affected" only on the sessions really in the 5m cache -----------------------------
TORN_0918 = "200960,,373221,,,"      # the 2026-09-18 torn 5m row: sorted by time, it lands first


def _old_rth_row():
    """A torn row whose epoch still reads as an RTH bar (2002-01-02 10:00 ET): it passes the
    first-day filter, so only the full session list can show the cache is not deep."""
    return f"{int(wf.at(dt.date(2002, 1, 2), (10, 0)).timestamp())},1,1,1,1,1"


def _tear_first_row(h, row):
    with open(h.paths["qqq_5m"], encoding="utf-8") as f:
        head, rest = f.read().split("\n", 1)
    T._w(h.paths["qqq_5m"], head + "\n" + row + "\n" + rest)


def _holes(tmp_path, now, d1_day):
    """256 sessions by the calendar from the 5m cache's first row, 6 whole sessions missing long
    before the daily file's newest bar: 250 real -- yesterday's 252-session rank then reads 3
    daily bars (NOISE_1_0 _vol_percentile: ref = ext[j-252:j] reaches into prior_ranges)."""
    drop = tuple(_sessions_before(now.date(), 256)[100:106])
    return _home(tmp_path, now, d1_day, k5=256, drop=drop)


@pytest.mark.parametrize("case", ["torn 09-18 row", "torn RTH-looking row", "6 holes"])
def test_a_deep_looking_cache_that_is_not_deep_pages_high(tmp_path, case):
    """The calendar count from the 5m cache's first row overcounts a torn first row or a hole:
    NOISE's vol skip still reads the daily bars, so the note stays HIGH at 09:47 and at the
    08:30 pre-open -- "not affected" is only ever said off the sessions really in the file."""
    notes = []
    for label, now, d1 in (("s", et(2026, 10, 5, 9, 44), THU),
                           ("po", et(2026, 10, 5, 8, 30, 20), dt.date(2026, 9, 30))):
        if case == "6 holes":
            h = _holes(tmp_path / label, now, d1)
        else:
            h = _home(tmp_path / label, now, d1)
            _tear_first_row(h, TORN_0918 if case == "torn 09-18 row" else _old_rth_row())
        snap = wf.collect(h.paths, h.run_cmd)
        days = snap["qqq_5m_days"]
        if case == "torn 09-18 row":                  # the first-day filter skips it: not deep
            assert snap["qqq_5m_first"] == _sessions_before(MON, 93)[0] and days is None
        else:                                         # deep by the calendar: the list is read
            assert days is not None
            assert sum(d < MON for d in days) == (250 if case == "6 holes" else 94)
        s = wf.qqq_1d_stale(snap, MON)
        assert s["affects"].endswith(AT_LINE)
        if label == "s":
            notes.append(_session_note(h))
        else:
            h.run()
            notes.extend(h.pushes)
    assert [(p["title"], p["priority"]) for p in notes] == [("QQQ book: CHECK NOW", "high")] * 2
    assert _trading(notes[0]) == "Trading: AFFECTED - " + AT_LINE + "."
    assert notes[1]["message"].split("\n")[:2] == ["Trading: AFFECTED - " + AT_LINE + ".",
                                                   "The QQQ daily price history is out of date."]
    assert all(lint_ok(p) for p in notes)


def test_a_deep_cache_with_its_first_row_torn_is_still_not_affected(tmp_path):
    """The full list is the proof both ways: a cache really 300 sessions deep stays "not
    affected" with a torn row on top."""
    h = _home(tmp_path, et(2026, 10, 5, 9, 44), THU, k5=300)
    _tear_first_row(h, TORN_0918)
    s = _stale(h)
    assert s["affects"] is None and "its 252-session window is all 5m" in s["dev"]


def test_not_affected_needs_the_counted_list(tmp_path):
    """Without the full list (snap["qqq_5m_days"] not read) a deep calendar count is never
    proof: NOISE stays at the line, and the developer words say why."""
    h = _home(tmp_path, et(2026, 10, 5, 9, 44), THU, k5=300)
    snap = wf.collect(h.paths, h.run_cmd)
    assert snap["qqq_5m_days"] is not None and wf.qqq_1d_stale(snap, MON)["affects"] is None
    s = wf.qqq_1d_stale(dict(snap, qqq_5m_days=None), MON)
    assert s["affects"] == AT_LINE
    assert "-- 300 5m sessions by the calendar, not counted in the file" in s["dev"]


# -- 6. what cannot be read ---------------------------------------------------------------------
def test_an_unreadable_newest_bar_or_5m_cache_is_hedged(tmp_path):
    h = _home(tmp_path, et(2026, 10, 5, 9, 44), THU)
    T._w(h.paths["qqq_1d"], HEADER + "1759377600,1,1,1,1,1\ninf,torn\n")     # rows, no last bar
    assert _stale(h)["affects"] == wf.QQQ_1D_STALE_UNKNOWN
    h2 = _home(tmp_path / "b", et(2026, 10, 5, 9, 44), THU)
    os.remove(h2.paths["qqq_5m"])
    assert _stale(h2)["affects"] == wf.QQQ_1D_STALE_UNKNOWN
    assert _trading(_session_note(h2)) == "Trading: AFFECTED - " + wf.QQQ_1D_STALE_UNKNOWN + "."


def test_current_missing_or_empty_files_are_not_stale(tmp_path):
    h = _home(tmp_path, et(2026, 10, 5, 9, 44), FRI)
    assert _stale(h) is None                                   # holds the previous session
    for text in (None, "", HEADER):
        if text is None:
            os.remove(h.paths["qqq_1d"])
        else:
            T._w(h.paths["qqq_1d"], text)
        assert _stale(h) is None                               # qqq_1d_missing's own words


# -- 7. the pre-open gate -----------------------------------------------------------------------
@pytest.mark.parametrize("kw, title, trading", [
    ({}, "QQQ book: CHECK NOW", "Trading: AFFECTED - " + AT_LINE + "."),
    ({"spans": {FRI: ((9, 30), (11, 0))}}, "QQQ book: CHECK NOW",
     "Trading: AFFECTED - DIP #424 decides on only part of Friday's prices, and " + AT_LINE + "."),
    ({"drop": (FRI,)}, "QQQ book: CHECK NOW",
     "Trading: AFFECTED - " + DIP_STOPS + ", and " + AT_LINE + "."),        # Thursday is whole
    ({"k5": 300}, "QQQ book: needs a fix", "Trading: not affected."),
])
def test_the_preopen_out_of_date_miss(tmp_path, kw, title, trading):
    h = _home(tmp_path, et(2026, 10, 5, 8, 30, 20), dt.date(2026, 9, 30), **kw)
    h.run()
    (p,) = h.pushes
    assert p["title"] == title and lint_ok(p)
    assert p["message"].split("\n")[:2] == [trading, "The QQQ daily price history is out of date."]
    slot = h.status()["preopen"]["slots"]["08:30"]["misses"]
    assert any(m.startswith("QQQ_1d newest bar 2026-09-30, expected 2026-10-01 or newer -- "
                            "lacks 2026-10-01, 2026-10-02: ") for m in slot)


def test_no_stale_words_remain():
    assert not hasattr(wf, "SHORT_HISTORY")
    with open(wf.__file__, encoding="utf-8") as f:
        src = f.read()
    assert "price history that is a day short" not in src and "look-back truncated" not in src


# -- 8. the tail read ---------------------------------------------------------------------------
def _full_spans(paths, after):
    out = {}
    for e in wf._csv_row_epochs(paths["qqq_5m"]):
        t = dt.datetime.fromtimestamp(e, tz=wf.ET)
        if t.date() > after and t.weekday() < 5 and (9, 30) <= (t.hour, t.minute) < (16, 0):
            lo, hi = out.get(t.date(), ((t.hour, t.minute),) * 2)
            out[t.date()] = (min(lo, (t.hour, t.minute)), max(hi, (t.hour, t.minute)))
    return out


@pytest.mark.parametrize("chunk", [wf.TAIL_READ_BYTES, 4096, 97])
@pytest.mark.parametrize("after", [THU, dt.date(2026, 9, 1), dt.date(2026, 1, 2)])
def test_the_tail_read_is_the_full_read_after_the_daily_files_newest_bar(tmp_path, monkeypatch,
                                                                       chunk, after):
    h = _home(tmp_path, et(2026, 10, 5, 9, 44), THU, spans={FRI: ((9, 30), (11, 0))})
    monkeypatch.setattr(wf, "TAIL_READ_BYTES", chunk)
    got = wf.five_min_day_spans(h.paths, after)
    assert got == _full_spans(h.paths, after)
    assert all(d > after for d in got)


def test_the_tail_read_reads_one_chunk_while_the_file_is_current(tmp_path, monkeypatch):
    h = _home(tmp_path, et(2026, 10, 5, 9, 44), FRI)
    reads = []
    real_open = open

    class Counting:
        def __init__(self, f):
            self.f = f

        def __enter__(self):
            return self

        def __exit__(self, *a):
            self.f.close()

        def seek(self, *a):
            return self.f.seek(*a)

        def tell(self):
            return self.f.tell()

        def read(self, n=-1):
            reads.append(n)
            return self.f.read(n)

    def counting_open(path, mode="r", *a, **k):
        f = real_open(path, mode, *a, **k)
        return Counting(f) if path == h.paths["qqq_5m"] and "b" in mode else f
    monkeypatch.setattr(wf, "open", counting_open, raising=False)
    assert os.path.getsize(h.paths["qqq_5m"]) > 2 * wf.TAIL_READ_BYTES
    spans = wf.five_min_day_spans(h.paths, FRI)
    assert list(spans) == [MON] and reads == [wf.TAIL_READ_BYTES]


def test_collect_reads_the_whole_5m_cache_only_when_far_behind_or_deep(tmp_path, monkeypatch):
    calls = []
    real = wf.five_min_session_days
    monkeypatch.setattr(wf, "five_min_session_days", lambda p: calls.append(1) or real(p))
    h = _home(tmp_path, et(2026, 10, 5, 9, 44), THU)
    snap = wf.collect(h.paths, h.run_cmd)
    assert calls == [] and snap["qqq_5m_days"] is None
    assert snap["qqq_5m_first"] == _sessions_before(MON, 93)[0] and FRI in snap["qqq_5m_spans"]
    _set_d1(h, _sessions_before(MON, 85)[0])                     # 9 sessions shared
    snap = wf.collect(h.paths, h.run_cmd)
    assert calls == [1] and len(snap["qqq_5m_days"]) == 94
    # a cache the calendar calls deep: read only while the daily file is behind it
    deep = _home(tmp_path / "deep", et(2026, 10, 5, 9, 44), FRI, k5=300)
    assert wf.collect(deep.paths, deep.run_cmd)["qqq_5m_days"] is None and calls == [1]
    _set_d1(deep, THU)
    assert len(wf.collect(deep.paths, deep.run_cmd)["qqq_5m_days"]) == 301 and calls == [1, 1]
    pre = _home(tmp_path / "pre", et(2026, 10, 5, 8, 30, 20), THU, k5=300)   # 08:30: current
    assert wf.collect(pre.paths, pre.run_cmd)["qqq_5m_days"] is None and calls == [1, 1]


def test_the_readers_never_raise(tmp_path):
    h = _home(tmp_path, et(2026, 10, 5, 9, 44), THU)
    T._w(h.paths["qqq_5m"], "")
    assert wf.five_min_day_spans(h.paths, THU) == {} and wf.five_min_first_day(h.paths) is None
    T._w(h.paths["qqq_5m"], HEADER + "x,1\n1e400,1\n99999999999999,1\n")
    assert wf.five_min_day_spans(h.paths, THU) == {}
    os.remove(h.paths["qqq_5m"])
    assert wf.five_min_day_spans(h.paths, THU) is None and wf.five_min_first_day(h.paths) is None


def test_the_backfill_moves_the_first_session_back(tmp_path):
    h = _home(tmp_path, et(2026, 10, 5, 9, 44), THU)
    old = int(wf.at(dt.date(2025, 1, 6), (9, 30)).timestamp())
    T._w(h.paths["qqq_5m_backfill"], HEADER + f"{old},1,1,1,1,1\n")
    assert wf.five_min_first_day(h.paths) == dt.date(2025, 1, 6)
