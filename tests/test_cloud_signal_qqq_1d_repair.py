"""api/cloud_signal.py -- EMPTY QQQ_1d.csv REPAIRS ITSELF (MANAGER GO 2026-10-25).

A QQQ_1d.csv with no row to keep (0 bytes, blank lines, a header only, rows whose time never
parses -- qqq_1d_missing_or_empty's EMPTY, the box monitor's own test) used to make the daily
refresh raise inside pandas (EmptyDataError) or merge its junk, so it only logged "refresh
failed" while the monitor paged the file every day; a MISSING file is downloaded at the next
refresh. Now the refresh treats an empty file like a missing one. Pinned here:

  1. each kind of empty file -> the next refresh (yfinance stubbed) keeps a byte-for-byte
     QQQ_1d.csv.corrupt-<stamp> copy, writes the download through the atomic replace (no .tmp
     left), logs both steps, and is due whatever the file's mtime (an emptied-today file used
     to wait for tomorrow); QQQ_5m.csv / QQQ_1m.csv are never touched;
  2. a file with any row whose time parses is never set aside or replaced by this path (the
     tripwire RECORDS a set-aside, so the refresh's own fail-safe cannot swallow it): a current
     one is not fetched at all, a stale one is merged as before (every old row kept), one whose
     merge fails (a good row beside junk) is left as it was, one pandas cannot read (a row with
     too many fields, bytes that are not utf-8) never costs a yfinance pull, and one whose
     numbers are quoted (EMPTY to the text test, every row to pandas) is merged and unquoted;
  3. a re-download with no rows leaves QQQ_1d.csv as it was (still EMPTY: the monitor's note and
     the engine's record-only routing stay as before) and the copy in place; retried every tick
     it keeps ONE copy and logs each line once, and the first download that lands repairs it;
     a replace that does not land says "not written", never "repaired";
  4. end to end with the box monitor: the pre-open note says the file is empty, the 09:35
     refresh repairs it, the monitor's one low "OK" is the note that says so.

No network: _fetch_yf_daily is a stub in every test, every store is under tmp_path.
"""
import csv
import datetime as dt
import importlib.util
import os

import pandas as pd
import pytest

from api import cloud_signal as cs
from api import ntfy_push

HEADER = "time,open,high,low,close,volume\n"
NOW = dt.datetime(2026, 10, 5, 9, 35, 30, tzinfo=cs._zi(cs.TZ))    # a Monday, the 09:35 refresh
FRI = dt.date(2026, 10, 2)
EMPTY_FILES = {
    "0-byte": "",
    "blank lines": "\n\n  \n",
    "header only": HEADER,
    "garbage rows": HEADER + "x,1,1,1,1,1\nnan,1,1,1,1,1\ninf,1,1,1,1,1\n",
    "garbage, no header": "hello world\nfoo,bar\n",
    "quoted header only": '"time","open","high","low","close","volume"\n',
}


@pytest.fixture(autouse=True)
def _fresh_once_a_day_log():
    """The repair's retry lines go through _log_fail_safe_once (once per ET day per copy)."""
    cs._DAILY_CALIBRATION_LOG.clear()
    yield
    cs._DAILY_CALIBRATION_LOG.clear()


def _quiet(*_a, **_k):
    return None


def _paths(tmp_path):
    paths = cs._paths(home=str(tmp_path / "home"))
    os.makedirs(paths["ohlc_dir"], exist_ok=True)
    return paths


def _write(path, text, mtime=None):
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(text)
    if mtime is not None:
        os.utime(path, (mtime, mtime))


def _yf(through=FRI, n=30):
    """What yfinance's daily history returns: `n` sessions through `through`, Open..Volume."""
    days = cs.market_calendar.sessions_between(through - dt.timedelta(days=2 * n), through)[-n:]
    idx = pd.DatetimeIndex([pd.Timestamp(d.isoformat()) for d in days])
    return pd.DataFrame({"Open": 100.0, "High": 101.0, "Low": 99.0, "Close": 100.5,
                         "Volume": 1.0e6}, index=idx)


def _stub_yf(monkeypatch, frames):
    """_fetch_yf_daily returns each of `frames` in turn (then the last one); returns the calls."""
    calls = []

    def fake():
        calls.append(1)
        return frames[min(len(calls), len(frames)) - 1]
    monkeypatch.setattr(cs, "_fetch_yf_daily", fake)
    return calls


def _copies(paths):
    return sorted(n for n in os.listdir(paths["ohlc_dir"]) if n.startswith("QQQ_1d.csv.corrupt-"))


def _today_epoch():
    return NOW.timestamp() - 60          # the file's mtime: emptied this morning


# -- 1. every kind of empty file repairs itself at the next refresh ---------------------------
@pytest.mark.parametrize("kind", sorted(EMPTY_FILES))
def test_an_empty_file_is_set_aside_and_downloaded_again(tmp_path, monkeypatch, kind):
    paths = _paths(tmp_path)
    p1d = cs._cache_path("1d", paths)
    _write(p1d, EMPTY_FILES[kind], mtime=_today_epoch())
    others = {}
    for tf in ("5m", "1m"):
        p = cs._cache_path(tf, paths)
        _write(p, HEADER + "1759411800,1,1,1,1,1\n", mtime=1_759_000_000)
        others[p] = (open(p, "rb").read(), os.path.getmtime(p))
    assert cs.qqq_1d_missing_or_empty(paths) == cs.QQQ_1D_EMPTY
    assert cs._daily_cache_refreshed_today(paths, NOW), "the old mtime gate would skip it"
    assert cs._daily_cache_refresh_due(NOW, paths), "empty is due like missing"
    calls = _stub_yf(monkeypatch, [_yf()])
    logged = []
    cs._maybe_refresh_daily_cache(NOW, paths, log=logged.append)
    assert calls == [1]
    df = pd.read_csv(p1d)
    assert len(df) == 30 and df["time"].is_monotonic_increasing
    assert cs._daily_cache_newest_date(paths) == FRI
    assert cs.qqq_1d_missing_or_empty(paths) is None
    (copy,) = _copies(paths)
    with open(os.path.join(paths["ohlc_dir"], copy), encoding="utf-8", newline="") as f:
        assert f.read() == EMPTY_FILES[kind], "the copy is the broken file, byte for byte"
    assert not [n for n in os.listdir(paths["ohlc_dir"]) if n.endswith(".tmp")]
    assert any("has no row to keep -- kept a copy as " + copy in m for m in logged)
    assert any("QQQ_1d.csv repaired: 30 daily row(s) downloaded" in m for m in logged)
    assert not any("refresh failed" in m for m in logged)
    for p, (data, mtime) in others.items():
        assert open(p, "rb").read() == data and os.path.getmtime(p) == mtime, p
    # repaired: the same day's next tick does not fetch again
    cs._maybe_refresh_daily_cache(NOW + dt.timedelta(minutes=5), paths, log=_quiet)
    assert calls == [1]


def test_before_the_fix_an_empty_file_only_logged_refresh_failed(tmp_path, monkeypatch):
    """The bug this replaces, kept honest: pandas raises on a 0-byte file -- the very read the
    old refresh started with -- and a missing file reads as nothing at all."""
    paths = _paths(tmp_path)
    assert cs.load_cached_bars("1d", paths) is None
    _write(cs._cache_path("1d", paths), "")
    with pytest.raises(pd.errors.EmptyDataError):
        cs.load_cached_bars("1d", paths)


# -- 2. a file with rows is never set aside by this path --------------------------------------
def _good(days, close=100.0):
    rows = [f"{int(pd.Timestamp(d.isoformat(), tz=cs.TZ).timestamp())},{close},{close + 1},"
            f"{close - 1},{close},1.0\n" for d in days]
    return HEADER + "".join(rows)


def _tripwire(monkeypatch):
    """Records every set-aside instead of raising: a raise inside the refresh would be caught by
    its own fail-safe and logged as "refresh failed", which a test could mistake for a pass."""
    hits = []
    monkeypatch.setattr(cs, "_keep_broken_daily_copy", lambda p: hits.append(p) or p)
    return hits


def _never_set_aside(hits, logged, paths):
    assert hits == [] and _copies(paths) == []
    assert not any("has no row to keep" in m or "repaired" in m for m in logged)


def test_a_current_file_is_not_fetched_or_rewritten(tmp_path, monkeypatch):
    paths = _paths(tmp_path)
    p1d = cs._cache_path("1d", paths)
    _write(p1d, _good(cs.market_calendar.sessions_between(dt.date(2026, 9, 1), FRI)),
           mtime=_today_epoch() - 86400)
    before = open(p1d, "rb").read()
    hits = _tripwire(monkeypatch)
    calls = _stub_yf(monkeypatch, [_yf()])
    logged = []
    cs._maybe_refresh_daily_cache(NOW, paths, log=logged.append)
    assert calls == [] and open(p1d, "rb").read() == before
    _never_set_aside(hits, logged, paths)


def test_a_stale_file_is_merged_as_before_every_old_row_kept(tmp_path, monkeypatch):
    paths = _paths(tmp_path)
    p1d = cs._cache_path("1d", paths)
    old_days = cs.market_calendar.sessions_between(dt.date(2026, 6, 1), dt.date(2026, 9, 30))
    _write(p1d, _good(old_days, close=50.0), mtime=_today_epoch() - 86400)
    old = pd.read_csv(p1d)
    hits = _tripwire(monkeypatch)
    _stub_yf(monkeypatch, [_yf()])
    logged = []
    cs._maybe_refresh_daily_cache(NOW, paths, log=logged.append)
    new = pd.read_csv(p1d)
    assert set(old["time"]) <= set(new["time"]) and len(new) > len(old)
    kept = new[new["time"].isin(old["time"]) & ~new["time"].isin(cs.qp._to_epoch_frame(_yf())["time"])]
    assert (kept["close"] == 50.0).all()
    _never_set_aside(hits, logged, paths)


def test_a_good_row_beside_junk_is_never_set_aside(tmp_path, monkeypatch):
    """One row whose time parses = a file with rows: not this path. Its merge still fails on the
    junk row (as before this fix) and the file is left exactly as it was."""
    paths = _paths(tmp_path)
    p1d = cs._cache_path("1d", paths)
    _write(p1d, HEADER + "x,1,1,1,1,1\n" + _good([dt.date(2026, 9, 30)])[len(HEADER):],
           mtime=_today_epoch() - 86400)
    before = open(p1d, "rb").read()
    assert cs.qqq_1d_missing_or_empty(paths) is None
    hits = _tripwire(monkeypatch)
    _stub_yf(monkeypatch, [_yf()])
    logged = []
    cs._maybe_refresh_daily_cache(NOW, paths, log=logged.append)
    assert open(p1d, "rb").read() == before
    assert any("QQQ daily cache refresh failed" in m for m in logged)
    _never_set_aside(hits, logged, paths)


@pytest.mark.parametrize("bad", [
    b"1759498200,1,1,1,1,1,9,9\n",          # too many fields: pandas raises ParserError
    b"1759498200,\xff\xfe,1,1,1,1\n",       # not utf-8: pandas raises UnicodeDecodeError
])
def test_a_file_pandas_cannot_read_never_costs_a_download(tmp_path, monkeypatch, bad):
    """A file with a good row that pandas cannot read is read BEFORE the yfinance pull, as it
    always was: twelve due ticks, no download, the file and its mtime as they were."""
    paths = _paths(tmp_path)
    p1d = cs._cache_path("1d", paths)
    with open(p1d, "wb") as f:
        f.write((HEADER + _good([dt.date(2026, 9, 29)])[len(HEADER):]).encode() + bad)
    old_mtime = _today_epoch() - 3 * 86400
    os.utime(p1d, (old_mtime, old_mtime))
    before = open(p1d, "rb").read()
    assert cs.qqq_1d_missing_or_empty(paths) is None and not cs._daily_file_broken(paths)
    with pytest.raises((pd.errors.ParserError, UnicodeDecodeError)):
        cs.load_cached_bars("1d", paths)
    hits = _tripwire(monkeypatch)
    calls = _stub_yf(monkeypatch, [_yf()])
    logged = []
    for k in range(12):
        tick = NOW + dt.timedelta(minutes=5 * k)
        assert cs._daily_cache_refresh_due(tick, paths)
        cs._maybe_refresh_daily_cache(tick, paths, log=logged.append)
    assert calls == [] and open(p1d, "rb").read() == before
    assert os.path.getmtime(p1d) == old_mtime
    assert sum("QQQ daily cache refresh failed" in m for m in logged) == 12
    _never_set_aside(hits, logged, paths)


@pytest.mark.parametrize("download", ["rows", "none"])
def test_a_quoted_file_is_merged_and_unquoted_never_set_aside(tmp_path, monkeypatch, download):
    """Quoted numbers: the text test (and the monitor's) reads the file EMPTY, pandas reads every
    row. It is merged -- every old row kept, no copy -- and the write unquotes it, so both reads
    then agree; with no download the same rows are written back unquoted."""
    paths = _paths(tmp_path)
    p1d = cs._cache_path("1d", paths)
    days = cs.market_calendar.sessions_between(dt.date(2021, 1, 4), FRI)
    rows = [[int(pd.Timestamp(d.isoformat(), tz=cs.TZ).timestamp()), 50.0, 51.0, 49.0, 50.0,
             1.0] for d in days]
    with open(p1d, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, quoting=csv.QUOTE_ALL)
        w.writerow(["time", "open", "high", "low", "close", "volume"])
        w.writerows(rows)
    os.utime(p1d, (_today_epoch(), _today_epoch()))
    old = pd.read_csv(p1d)
    assert len(old) == len(days) > 1400 and cs._daily_cache_newest_date(paths) == FRI
    assert cs.qqq_1d_missing_or_empty(paths) == cs.QQQ_1D_EMPTY
    assert not cs._daily_file_broken(paths)
    hits = _tripwire(monkeypatch)
    calls = _stub_yf(monkeypatch, [_yf() if download == "rows" else pd.DataFrame()])
    logged = []
    cs._maybe_refresh_daily_cache(NOW, paths, log=logged.append)
    assert calls == [1]
    new = pd.read_csv(p1d)
    assert set(old["time"]) <= set(new["time"]) and len(new) == len(old)
    assert new["time"].iloc[0] == old["time"].iloc[0]           # DIP's series start unmoved
    assert cs.qqq_1d_missing_or_empty(paths) is None            # the text test agrees now
    assert '"' not in open(p1d, encoding="utf-8").read()
    _never_set_aside(hits, logged, paths)
    cs._maybe_refresh_daily_cache(NOW + dt.timedelta(minutes=5), paths, log=_quiet)
    assert calls == [1]                                          # current, written today


def test_a_file_that_gains_a_row_during_the_download_is_merged_not_replaced(tmp_path,
                                                                            monkeypatch):
    paths = _paths(tmp_path)
    p1d = cs._cache_path("1d", paths)
    _write(p1d, "", mtime=_today_epoch())
    late = _good([dt.date(2026, 6, 1)], close=7.0)

    def fetch_while_a_row_lands():
        _write(p1d, late)                    # another writer, between the check and the merge
        return _yf()
    monkeypatch.setattr(cs, "_fetch_yf_daily", fetch_while_a_row_lands)
    cs._maybe_refresh_daily_cache(NOW, paths, log=_quiet)
    new = pd.read_csv(p1d)
    assert 7.0 in set(new["close"]) and len(new) == 31
    assert len(_copies(paths)) == 1                              # the empty file it saw


# -- 3. a failed re-download -------------------------------------------------------------------
def test_a_failed_download_leaves_the_file_and_the_copy_then_the_next_one_repairs(tmp_path,
                                                                                 monkeypatch):
    paths = _paths(tmp_path)
    p1d = cs._cache_path("1d", paths)
    _write(p1d, HEADER, mtime=_today_epoch())
    mtime = os.path.getmtime(p1d)
    calls = _stub_yf(monkeypatch, [pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), _yf()])
    logged = []
    for k in range(3):                                           # three ticks, yfinance down
        cs._maybe_refresh_daily_cache(NOW + dt.timedelta(minutes=5 * k), paths,
                                      log=logged.append)
        assert open(p1d, encoding="utf-8").read() == HEADER and os.path.getmtime(p1d) == mtime
        assert cs.qqq_1d_missing_or_empty(paths) == cs.QQQ_1D_EMPTY   # the state as before
        assert len(_copies(paths)) == 1, "one copy per broken file, however many retries"
    assert calls == [1, 1, 1]
    # every tick retries; each line is logged once (per copy, per ET day), not every bar
    assert sum("re-download got no rows -- the file is left as it was" in m for m in logged) == 1
    assert sum("has no row to keep -- kept a copy as" in m for m in logged) == 1
    cs._maybe_refresh_daily_cache(NOW + dt.timedelta(minutes=15), paths, log=_quiet)
    assert calls == [1, 1, 1, 1] and len(pd.read_csv(p1d)) == 30
    assert len(_copies(paths)) == 1


def test_a_replace_that_does_not_land_says_not_written(tmp_path, monkeypatch):
    """qp._replace_with_retry never raises: on a failure it removes the .tmp and returns False.
    The log then says the repair was not written (never "repaired"), the file is still EMPTY,
    and the next refresh repairs it."""
    paths = _paths(tmp_path)
    p1d = cs._cache_path("1d", paths)
    _write(p1d, "", mtime=_today_epoch())
    real = cs.qp._replace_with_retry

    def fails(tmp, dst, log=print, what=None, **_k):
        os.remove(tmp)
        return False
    monkeypatch.setattr(cs.qp, "_replace_with_retry", fails)
    _stub_yf(monkeypatch, [_yf()])
    logged = []
    cs._maybe_refresh_daily_cache(NOW, paths, log=logged.append)
    assert open(p1d, encoding="utf-8").read() == ""
    assert cs.qqq_1d_missing_or_empty(paths) == cs.QQQ_1D_EMPTY
    assert any("QQQ_1d.csv repair not written -- the next refresh tries again" in m
               for m in logged)
    assert not any("repaired" in m for m in logged)
    assert not [n for n in os.listdir(paths["ohlc_dir"]) if n.endswith(".tmp")]
    monkeypatch.setattr(cs.qp, "_replace_with_retry", real)
    logged.clear()
    cs._maybe_refresh_daily_cache(NOW + dt.timedelta(minutes=5), paths, log=logged.append)
    assert len(pd.read_csv(p1d)) == 30 and len(_copies(paths)) == 1
    assert any("QQQ_1d.csv repaired: 30 daily row(s) downloaded" in m for m in logged)


def test_a_second_broken_file_gets_its_own_copy(tmp_path, monkeypatch):
    paths = _paths(tmp_path)
    p1d = cs._cache_path("1d", paths)
    _write(p1d, "", mtime=_today_epoch())
    _stub_yf(monkeypatch, [pd.DataFrame()])
    cs._maybe_refresh_daily_cache(NOW, paths, log=_quiet)
    _write(p1d, HEADER, mtime=_today_epoch())
    cs._maybe_refresh_daily_cache(NOW, paths, log=_quiet)
    texts = sorted(open(os.path.join(paths["ohlc_dir"], c), encoding="utf-8").read()
                   for c in _copies(paths))
    assert texts == ["", HEADER]


def test_a_copy_that_cannot_be_made_fails_safe(tmp_path, monkeypatch):
    """The set-aside raises (a full disk, say): the refresh logs and leaves everything as it
    was -- never a download written over a file it could not keep."""
    paths = _paths(tmp_path)
    p1d = cs._cache_path("1d", paths)
    _write(p1d, "", mtime=_today_epoch())

    def boom(_path):
        raise OSError("disk full")
    monkeypatch.setattr(cs, "_keep_broken_daily_copy", boom)
    calls = _stub_yf(monkeypatch, [_yf()])
    logged = []
    cs._maybe_refresh_daily_cache(NOW, paths, log=logged.append)
    assert calls == [] and open(p1d, encoding="utf-8").read() == ""
    assert any("QQQ daily cache refresh failed (OSError: disk full)" in m for m in logged)


# -- 4. end to end with the box monitor --------------------------------------------------------
def _load(name, fname):
    spec = importlib.util.spec_from_file_location(
        name, os.path.join(os.path.dirname(os.path.abspath(__file__)), fname))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_the_monitors_ok_is_the_note_that_says_it_was_repaired(tmp_path, monkeypatch):
    """The file empties mid-morning (its mtime today: before this fix the refresh skipped it
    until tomorrow and the monitor's note stayed open all day); the session check pages it once,
    the engine's next refresh repairs it, and the monitor's one low "OK" says the file is back."""
    monkeypatch.delenv("EDGELOG_FRESHNESS_PING_URL", raising=False)
    Q = _load("repair_q1d_helpers", "test_webull_freshness_qqq_1d_missing.py")
    T, wf = Q.T, Q.wf
    h = Q._home(tmp_path, T.et(2026, 10, 5, 9, 44, 30), state=None)
    h.run()
    Q._set_1d(h, "empty")
    for mm in (46, 48):
        Q._run_at(h, 9, mm)
    (p,) = h.pushes
    assert p["title"] == "QQQ book: CHECK NOW" and Q.EMPTY_LINE in p["message"]
    paths = cs._paths(home=h.root)
    assert paths["ohlc_dir"] == os.path.dirname(h.paths["qqq_1d"])
    assert cs._daily_cache_refresh_due(NOW.replace(minute=50), paths)
    _stub_yf(monkeypatch, [_yf()])
    cs._maybe_refresh_daily_cache(NOW.replace(minute=50), paths, log=_quiet)   # its next bar
    Q._run_at(h, 9, 52)
    assert [x["title"] for x in h.pushes] == ["QQQ book: CHECK NOW", "QQQ book: OK"]
    ok = h.pushes[-1]
    assert ok["priority"] == "low"
    assert "was: the QQQ daily price file on the cloud box is empty" in ok["message"]
    assert ntfy_push.lint(ok) == []
    assert wf.qqq_1d_file_state(h.paths["qqq_1d"]) is None and len(_copies(paths)) == 1
