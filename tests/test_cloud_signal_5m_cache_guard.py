"""tests/test_cloud_signal_5m_cache_guard.py -- 5m CACHE NEVER SHRINKS (MANAGER GO 2026-10-25):
api/cloud_signal.py fetch_and_merge never writes a QQQ_5m.csv that holds less than the file does
now, and never rebuilds a lost one from the fetch alone on a store that has decided off it before
(10-25: a copy rebuilt from yfinance's ~60 days moved closed DIP trades and changed trade ids).
While a refusal is open no leg on the timeframe decides (live or shadow, fetching or not) and the
engine pages once a day. The box runbook note is deploy/cloud/README.md "The QQQ 5-minute bar
cache".

No network: Webull, yfinance and every push are stubbed. The DIP cases run the shipped live
DIP_424 leg (and the shadow pair) on tests/test_dip424_shadow.py's synthetic fixtures through the
REAL fetch_and_merge.

COVERS
  1. A normal append day -- Webull rows, and the yfinance fallback's newer-only rows -- gives
     byte-identical QQQ_5m.csv / state.json and the same signals.csv rows with the guard on as
     with it off; the reach file is written once and never touched again.
  2. MISSING on an established store: no file is written from the fetch, no leg decides (live or
     shadow, fetch or offline tick), the feed's freshness is still stamped, ONE high plain note a
     day (lint-clean, Trading: AFFECTED, the Do line); the file put back by hand -> the legs
     decide exactly as a store that never lost it, and one low "OK". Without the guard the same
     tick rebuilds the file from yfinance with fewer sessions (the 10-25 hazard).
  3. A first boot (no bar_source in state.json, no reach file) still cold-starts from the fetch.
  4. EMPTY (0 bytes, blank lines, a header only, junk or torn rows, and a file pandas cannot
     parse: too many fields, glued rows, not utf-8): copied ONCE to .corrupt-<stamp>, left in
     place, refused; on a first boot copied aside, then replaced. A failed copy is said so.
  5. SHRINK: a merge that would drop a bar the file holds is refused (the file kept as it was).
     SHORT: a shorter copy put in place by hand on an established store (its first session later
     than QQQ_5m.reach.json's) is refused, paged and never written; a restore that reaches back
     as far clears it (one ending early too); a longer restore moves the reach earlier; deleting
     the reach file by hand is the one way to take a later start. A torn first row dropped by
     tools/qqq_cache_repair.py does not trip it; the reach file alone counts as established.
  6. A file replaced while the fetch is in flight (an operator's restore) is never written over.
  7. PRICES while the guard refuses: the guard tail holds the refused fetch's newest bars,
     mark_bars / api/qqq_exec.py price an open lot off it (the breaker's marks, the EOD close)
     with no file and no stream; it is removed by the first good write; a normal day reads the
     cache exactly as before.
  8. QQQ_1m.csv is unguarded (a missing one is written from the fetch; an empty or unparseable
     one raises). The stream path (api/cloud_signal_stream.py) makes no decision while the guard
     refuses.
  9. The note's text for every cause passes api/ntfy_push lint (the EMPTY copy line is true, SHRINK
     has its own Do line); one-leg grammar; no page off the box, for shadow legs alone or for a
     live leg before its live_since; an unreadable state.json counts as established; the live
     heartbeat carries an open refusal.
"""
import csv
import json
import os
import sys

import pandas as pd
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
TESTS = os.path.dirname(os.path.abspath(__file__))
if TESTS not in sys.path:
    sys.path.insert(0, TESTS)

import api.cloud_signal as cs                       # noqa: E402
from api import dip_live as DL                      # noqa: E402
from api import ntfy_push                           # noqa: E402
import test_dip424_shadow as S                      # noqa: E402  (the synthetic DIP fixtures)

QUIET = lambda *a, **k: None   # noqa: E731
LIVE = "DIP_424"
CRASH, CRASH_AT = S.CRASH, S.CRASH_AT
D_ENTRY, D_X1 = S.D_ENTRY, S.D_X1
at = S.at
FIX_LIVE_SINCE = S.CRASH_DAYS[0].isoformat()


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    DL._PROBE_MEMO.clear()
    monkeypatch.setattr(cs, "_BAR_CACHE_REFUSED", {})
    monkeypatch.setattr(cs, "_BAR_CACHE_NOTED", {})
    monkeypatch.setattr(cs, "_DAILY_CALIBRATION_LOG", {})
    monkeypatch.setattr(cs, "_UNSETTLED_DROP_LOGGED", {})
    monkeypatch.setattr(cs, "_YF_KEPT_LOGGED", {})
    yield
    DL._PROBE_MEMO.clear()


class Feed:
    """The network, stubbed: Webull answers with `webull` (a frame, or None = down), yfinance with
    `yf` (a frame in yfinance's own shape); the wall clock is `clock` (epoch). Every other network
    path raises; pushes are collected (on the box only when `box` is set)."""

    def __init__(self, monkeypatch):
        self.webull, self.yf, self.clock, self.pushes = None, None, 0, []
        self.box = False

        def boom(*a, **k):
            raise AssertionError("network touched")
        monkeypatch.setattr(cs, "_fetch_webull",
                            lambda tf, count=None, log=print: None if self.webull is None
                            else self.webull.copy())
        monkeypatch.setattr(cs.qp, "_fetch_yf",
                            lambda tf: pd.DataFrame() if self.yf is None else self.yf.copy())
        monkeypatch.setattr(cs, "_wall_epoch", lambda: int(self.clock))
        monkeypatch.setattr(cs, "_fetch_yf_daily", boom)
        monkeypatch.setattr(cs, "_maybe_refresh_daily_cache", lambda *a, **k: None)
        monkeypatch.setattr(cs, "NOISE_FORWARD_LOG", False)
        monkeypatch.setattr(cs, "_is_cloud_host", lambda: self.box)
        monkeypatch.setattr(cs, "_engine_push_background",
                            lambda msg, title, priority="high", paths=None, log=print:
                            self.pushes.append({"title": title, "message": msg,
                                                "priority": priority}))
        monkeypatch.setattr(cs, "_engine_push",
                            lambda msg, title, priority="high", paths=None, log=print:
                            self.pushes.append({"title": title, "message": msg,
                                                "priority": priority}))


@pytest.fixture
def feed(monkeypatch):
    return Feed(monkeypatch)


def _legs(home):
    """(live, shadow): the SHIPPED live DIP leg (live_since at the fixture's first session) and
    the shipped shadow pair."""
    return {LIVE: dict(cs.CROWN_LEGS[LIVE], live_since=FIX_LIVE_SINCE)}, S._dip_legs(home)


def _home(root, n5=30):
    """A box store: 5m sessions up to D_CRASH (the last `n5`), QQQ_1d for the whole fixture."""
    paths = S.write_home(root, CRASH[:CRASH_AT + 1], n5)
    S.write_1d(paths, CRASH)
    return paths


def _bars(days):
    return pd.concat([S.session_bars(*t) for t in CRASH if t[0] in set(days)], ignore_index=True)


def _yf_shape(epoch_df):
    idx = pd.DatetimeIndex([pd.Timestamp(int(t), unit="s", tz="UTC").tz_convert(cs.TZ)
                            for t in epoch_df["time"]])
    return pd.DataFrame({"Open": epoch_df["open"].values, "High": epoch_df["high"].values,
                         "Low": epoch_df["low"].values, "Close": epoch_df["close"].values,
                         "Volume": epoch_df["volume"].values}, index=idx)


def _tick(feed, paths, now, live, shadow, fetch=True, warnings=None):
    feed.clock = now.timestamp()
    lv = cs.step(now=now, legs=live, paths=paths, fetch=fetch, warnings=warnings)
    sh = cs.run_shadow_step(now=now, fetch=fetch, live_legs=live, shadow_legs=shadow,
                            live_paths=paths, log=QUIET) if fetch else []
    return lv, sh


def _rows(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8", newline="") as f:
        return [{k: v for k, v in r.items() if k != "emitted_at"} for r in csv.DictReader(f)]


def _bytes(path):
    with open(path, "rb") as f:
        return f.read()


def _sessions(path):
    t = pd.read_csv(path)["time"]
    return pd.to_datetime(t, unit="s", utc=True).dt.tz_convert(cs.TZ).dt.date.nunique()


def _state(paths):
    with open(paths["state_path"], encoding="utf-8") as f:
        return json.load(f)


def _established(paths, tf="5m"):
    """A state.json saying this store's engine has decided off the `tf` cache before."""
    os.makedirs(paths["state_dir"], exist_ok=True)
    with open(paths["state_path"], "w", encoding="utf-8") as f:
        json.dump({"legs": {}, "bar_source": {tf: {"source": "webull", "newest_epoch": 1,
                                                   "checked_at": "x"}}}, f)


# ── 1. a normal day is unchanged ───────────────────────────────────────────────────────────
def _normal_day(root, feed, monkeypatch, guard_on):
    if not guard_on:
        monkeypatch.setattr(cs, "BAR_CACHE_GUARD_TIMEFRAMES", ())
    paths = _home(root)
    live, shadow = _legs(paths["home"])
    both = _bars([D_ENTRY, D_X1])
    events, reach_seen = [], []
    # Webull: the seed tick, the day's seven entries, the next morning's exit; then a
    # yfinance-fallback tick whose copy of every cached bar is RESTATED (+5 cents, other volumes)
    for now in (at(D_ENTRY, 9, 30, 5), at(D_ENTRY, 9, 35, 5), at(D_X1, 9, 35, 5)):
        feed.webull = both
        events += _tick(feed, paths, now, live, shadow)[0]
        reach_seen.append(_stat_bytes(_reach(paths)))
    feed.webull = None
    restated = both.copy()
    restated[["open", "high", "low", "close"]] += 0.05
    restated["volume"] = 777.0
    feed.yf = _yf_shape(restated)
    events += _tick(feed, paths, at(D_X1, 9, 42, 30), live, shadow)[0]
    reach_seen.append(_stat_bytes(_reach(paths)))
    return paths, events, reach_seen


def _reach(paths):
    return os.path.join(paths["ohlc_dir"], "QQQ_5m.reach.json")


def _stat_bytes(path):
    """(mtime_ns, bytes) of `path`, or None when it is not there."""
    if not os.path.exists(path):
        return None
    return os.stat(path).st_mtime_ns, _bytes(path)


def test_a_normal_append_day_is_byte_identical_with_the_guard_on_and_off(tmp_path, feed,
                                                                           monkeypatch):
    on, ev_on, reach_on = _normal_day(tmp_path / "on", feed, monkeypatch, guard_on=True)
    with monkeypatch.context() as m:
        off, ev_off, reach_off = _normal_day(tmp_path / "off", feed, m, guard_on=False)
    assert cs.BAR_CACHE_GUARD_TIMEFRAMES == ("5m",)
    # the reach file: made by the first write, never rewritten by an append (guard off: none)
    assert reach_off == [None] * 4 and reach_on[0] is not None
    assert reach_on == [reach_on[0]] * 4
    assert json.loads(reach_on[0][1])["first_session"] == \
        S.CRASH[CRASH_AT + 1 - 30][0].isoformat()
    assert not os.path.exists(os.path.join(on["ohlc_dir"], "QQQ_5m_guard_tail.csv"))
    kinds = [e["event"] for e in ev_on]
    assert kinds.count("SEED") == 1 and kinds.count("ENTRY") == 7 and "EXIT" in kinds, kinds
    assert _rows(on["signals_path"]) == _rows(off["signals_path"]) != []
    sp_on, sp_off = cs.shadow_paths(on), cs.shadow_paths(off)
    assert _rows(sp_on["signals_path"]) == _rows(sp_off["signals_path"]) != []
    assert _bytes(on["state_path"]) == _bytes(off["state_path"])
    assert _bytes(sp_on["state_path"]) == _bytes(sp_off["state_path"])
    five_on = os.path.join(on["ohlc_dir"], "QQQ_5m.csv")
    assert _bytes(five_on) == _bytes(os.path.join(off["ohlc_dir"], "QQQ_5m.csv"))
    # the yfinance tick appended D_X1's 09:35 bar and left every cached bar exactly as it was
    disk = pd.read_csv(five_on).set_index("time")
    x1 = _bars([D_X1])["time"]
    assert (disk.loc[_bars([D_ENTRY])["time"], "volume"] == 1000.0).all()
    assert disk.loc[int(x1.iloc[0]), "volume"] == 1000.0
    assert disk.loc[int(x1.iloc[1]), "volume"] == 777.0 and int(x1.iloc[2]) not in disk.index
    assert _state(on)["bar_source"]["5m"]["source"] == "yfinance"
    assert not cs._BAR_CACHE_REFUSED
    assert not [n for n in os.listdir(on["ohlc_dir"]) if ".corrupt-" in n]


# ── 2. MISSING on an established store ─────────────────────────────────────────────────────
def test_a_missing_cache_is_never_rebuilt_from_the_fetch_and_no_leg_decides(tmp_path, feed,
                                                                            monkeypatch):
    paths = _home(tmp_path / "box")
    ctrl = _home(tmp_path / "ctrl")                    # the same store, never loses its file
    live, shadow = _legs(paths["home"])
    live_c, shadow_c = _legs(ctrl["home"])
    five = os.path.join(paths["ohlc_dir"], "QQQ_5m.csv")
    feed.box = True
    feed.webull = _bars([D_ENTRY])
    lv, sh = _tick(feed, paths, at(D_ENTRY, 9, 30, 5), live, shadow)
    _tick(feed, ctrl, at(D_ENTRY, 9, 30, 5), live_c, shadow_c)
    assert [e["event"] for e in lv] == ["SEED"]
    saved, n_before = _bytes(five), _sessions(five)
    leg_before = _state(paths)["legs"][LIVE]
    shadow_before = _state(cs.shadow_paths(paths))["legs"]

    # the file is lost; Webull is down; yfinance serves its short window (10 sessions here)
    os.remove(five)
    feed.webull = None
    feed.yf = _yf_shape(_bars([t[0] for t in CRASH[CRASH_AT - 8:CRASH_AT + 2]]))
    notes, real_note = [], cs._engine_note
    monkeypatch.setattr(cs, "_engine_note",
                        lambda *a, **k: notes.append(a[0]) or real_note(*a, **k))
    w = {}
    lv, sh = _tick(feed, paths, at(D_ENTRY, 9, 35, 5), live, shadow, warnings=w)
    assert lv == [] and sh == [], "no decision of any leg off a refused cache"
    assert not os.path.exists(five), "never rebuilt from the fetch"
    st = _state(paths)
    assert st["legs"][LIVE] == leg_before, "the leg's state is untouched (last_bar_epoch too)"
    assert _state(cs.shadow_paths(paths))["legs"] == shadow_before
    assert st["bar_source"]["5m"]["source"] == "yfinance", "the feed's freshness is still stamped"
    assert w[cs.BAR_CACHE_GUARD_KEY]["5m"]["why"] == cs.BAR_CACHE_MISSING
    assert cs.bar_cache_refusal("5m", paths)["why"] == cs.BAR_CACHE_MISSING
    assert cs.bar_cache_refusal("5m", cs.shadow_paths(paths)) is not None, "one cache, both stores"
    # ONE high plain note: what happened, Trading: AFFECTED, the Do line
    (p,) = feed.pushes
    assert ntfy_push.lint(p) == [], p
    assert p["title"] == "QQQ price file: not trading" and p["priority"] == "high"
    line1, line2, line3 = p["message"].split("\n")
    assert line1 == ("Trading: AFFECTED - DIP takes no new trades and sends no exit for its held "
                     "shares until the file is back.")
    assert line2.startswith("The QQQ_5m.csv price file is missing.")
    assert line3 == "Do: ask Claude (PAPER-WB chat) to restore QQQ_5m.csv from the PC backup."

    # more ticks the same day -- fetching, and an offline ~1s one -- decide nothing, page nothing
    lv, sh = _tick(feed, paths, at(D_ENTRY, 9, 40, 5), live, shadow)
    assert lv == [] and sh == [] and not os.path.exists(five)
    assert cs.step(now=at(D_ENTRY, 9, 40, 6), legs=live, paths=paths, fetch=False) == []
    assert len(feed.pushes) == 1, "one page a day"
    assert notes == ["bar_cache_guard:5m"], (
        "one note a day -- not a phone_dedupe.json write every tick")
    cs._BAR_CACHE_NOTED.clear()             # a restart the same day: the in-process memo is gone
    _tick(feed, paths, at(D_ENTRY, 9, 41, 5), live, shadow)
    assert len(feed.pushes) == 1, "the repeat rule (phone_dedupe.json) holds a restart's repeat"
    assert len(notes) == 2

    # put back by hand from the trusted copy: the next fetch appends and the legs decide again --
    # exactly as a store that never lost the file
    with open(five, "wb") as f:
        f.write(saved)
    feed.webull = _bars([D_ENTRY])
    lv, sh = _tick(feed, paths, at(D_ENTRY, 9, 45, 5), live, shadow)
    lv_c, sh_c = _tick(feed, ctrl, at(D_ENTRY, 9, 45, 5), live_c, shadow_c)
    def shape(evs):
        return [(e["leg"], e["event"], e["trade_id"], e["ref_price"]) for e in evs]
    assert [e["event"] for e in lv] == ["ENTRY"] * 7
    assert shape(lv) == shape(lv_c) and shape(sh) == shape(sh_c)
    assert cs.bar_cache_refusal("5m", paths) is None
    assert _sessions(five) == n_before + 1
    assert _bytes(five) == _bytes(os.path.join(ctrl["ohlc_dir"], "QQQ_5m.csv"))
    (ok,) = feed.pushes[1:]
    assert ok["title"] == "QQQ price file: OK" and ok["priority"] == "low"
    assert ntfy_push.lint(ok) == []
    _tick(feed, paths, at(D_ENTRY, 9, 50, 5), live, shadow)
    assert len(feed.pushes) == 2, "the OK is sent once"


def test_without_the_guard_the_same_tick_rebuilds_the_cache_short(tmp_path, feed, monkeypatch):
    """The hazard the guard closes (10-25): today's code wrote the yfinance window as the cache."""
    monkeypatch.setattr(cs, "BAR_CACHE_GUARD_TIMEFRAMES", ())
    paths = _home(tmp_path)
    live, shadow = _legs(paths["home"])
    five = os.path.join(paths["ohlc_dir"], "QQQ_5m.csv")
    feed.webull = _bars([D_ENTRY])
    _tick(feed, paths, at(D_ENTRY, 9, 30, 5), live, shadow)
    n_before = _sessions(five)
    os.remove(five)
    feed.webull = None
    feed.yf = _yf_shape(_bars([t[0] for t in CRASH[CRASH_AT - 8:CRASH_AT + 2]]))
    _tick(feed, paths, at(D_ENTRY, 9, 35, 5), live, shadow)
    # nine of the ten served sessions settled (today's 09:30 bar is still inside the margin)
    assert os.path.exists(five) and _sessions(five) == 9 < n_before == 30


# ── 3. a first boot still cold-starts ──────────────────────────────────────────────────────
def test_a_first_boot_starts_the_cache_from_the_fetch(tmp_path, feed):
    paths = cs._paths(home=str(tmp_path))
    feed.clock = 10 ** 10
    feed.webull = _bars([D_ENTRY])
    logged = []
    merged, source, ok = cs.fetch_and_merge("5m", paths, log=logged.append)
    five = os.path.join(paths["ohlc_dir"], "QQQ_5m.csv")
    assert source == "webull" and ok and len(merged) == len(feed.webull)
    assert pd.read_csv(five)["time"].tolist() == feed.webull["time"].tolist()
    assert cs.bar_cache_refusal("5m", paths) is None
    assert sum("first boot, it starts from the fetch" in m for m in logged) == 1


# ── 4. EMPTY ───────────────────────────────────────────────────────────────────────────────
EMPTY_FILES = {
    "zero_bytes": b"",
    "blank_lines": b"\n\n  \n",
    "header_only": b"time,open,high,low,close,volume\n",
    "junk_rows": b"time,open,high,low,close,volume\nabc,1,2,3,4,5\n,1,2,3,4,5\n",
    "torn_rows_only": b"time,open,high,low,close,volume\n200960,799926800000,373221,,,\n",
    # pandas cannot parse these at all (ParserError / UnicodeDecodeError) -- rows in them
    "too_many_fields": b"time,open,high,low,close,volume\n1759411800,1,2,3,4,5\n"
                       b"1759412100,1,2,3,4,5,6,7\n",
    "glued_rows": b"time,open,high,low,close,volume\n1759411800,1,2,3,4,5\n"
                  b"1759412100,1,2,3,4,51759412400,1,2,3,4,5\n",
    "not_utf8": b"time,open,high,low,close,volume\n1759411800,1,2,3,4,5\n\xff\xfe\x00\x81,1,2\n",
}


@pytest.mark.parametrize("kind", sorted(EMPTY_FILES))
def test_an_empty_cache_is_copied_aside_once_kept_and_refused(tmp_path, feed, kind):
    paths = cs._paths(home=str(tmp_path))
    os.makedirs(paths["ohlc_dir"], exist_ok=True)
    _established(paths)
    five = os.path.join(paths["ohlc_dir"], "QQQ_5m.csv")
    with open(five, "wb") as f:
        f.write(EMPTY_FILES[kind])
    feed.clock = 10 ** 10
    feed.webull = _bars([D_ENTRY])
    logged = []
    for _ in range(3):                                 # retried every tick: one copy, one log line
        merged, source, ok = cs.fetch_and_merge("5m", paths, log=logged.append)
    assert ok is True and merged["time"].tolist() == feed.webull["time"].tolist()
    assert _bytes(five) == EMPTY_FILES[kind], "the broken file is left where it is"
    copies = [n for n in os.listdir(paths["ohlc_dir"]) if n.startswith("QQQ_5m.csv.corrupt-")]
    assert len(copies) == 1
    assert _bytes(os.path.join(paths["ohlc_dir"], copies[0])) == EMPTY_FILES[kind]
    rec = cs.bar_cache_refusal("5m", paths)
    assert rec["why"] == cs.BAR_CACHE_EMPTY and rec["copy"] == copies[0]
    guard_lines = [m for m in logged if "5m CACHE GUARD" in m]
    assert len(guard_lines) == 1 and "REFUSED to rebuild" in guard_lines[0]
    assert copies[0] in guard_lines[0]
    # an offline tick never reads it (a 0-byte file would raise EmptyDataError there)
    legs = {"STUB": {"strategy": "unused.py", "timeframe": "5m"}}
    assert cs.step(now=at(D_ENTRY, 10, 0), legs=legs, paths=paths, fetch=False) == []


@pytest.mark.parametrize("kind", ["zero_bytes", "header_only"])
def test_an_empty_cache_on_a_first_boot_is_copied_aside_then_replaced(tmp_path, feed, kind):
    paths = cs._paths(home=str(tmp_path))
    os.makedirs(paths["ohlc_dir"], exist_ok=True)
    five = os.path.join(paths["ohlc_dir"], "QQQ_5m.csv")
    with open(five, "wb") as f:
        f.write(EMPTY_FILES[kind])
    feed.clock = 10 ** 10
    feed.webull = _bars([D_ENTRY])
    cs.fetch_and_merge("5m", paths, log=QUIET)
    assert pd.read_csv(five)["time"].tolist() == feed.webull["time"].tolist()
    copies = [n for n in os.listdir(paths["ohlc_dir"]) if n.startswith("QQQ_5m.csv.corrupt-")]
    assert len(copies) == 1 and cs.bar_cache_refusal("5m", paths) is None


@pytest.mark.parametrize("kind", ["too_many_fields", "glued_rows", "not_utf8"])
def test_the_unparseable_fixtures_really_fail_the_plain_read(tmp_path, kind):
    """The three files above are ones pandas raises on (so the guard's except is what catches
    them), not ones that parse into junk rows."""
    p = tmp_path / "x.csv"
    p.write_bytes(EMPTY_FILES[kind])
    with pytest.raises((pd.errors.ParserError, UnicodeDecodeError)):
        pd.read_csv(p)


def test_an_empty_cache_whose_copy_fails_says_no_copy_was_kept(tmp_path, feed, monkeypatch):
    paths = cs._paths(home=str(tmp_path))
    os.makedirs(paths["ohlc_dir"], exist_ok=True)
    _established(paths)
    with open(os.path.join(paths["ohlc_dir"], "QQQ_5m.csv"), "wb"):
        pass

    def full_disk(path):
        raise OSError(28, "No space left on device")
    monkeypatch.setattr(cs, "_keep_broken_daily_copy", full_disk)
    feed.clock = 10 ** 10
    feed.webull = _bars([D_ENTRY])
    logged = []
    cs.fetch_and_merge("5m", paths, log=logged.append)
    rec = cs.bar_cache_refusal("5m", paths)
    assert rec["why"] == cs.BAR_CACHE_EMPTY and rec["copy"] is None
    assert any("could not keep a copy of QQQ_5m.csv" in m for m in logged)
    assert any("(no copy could be kept)" in m for m in logged)
    note = cs._bar_cache_guard_note("5m", rec, [LIVE])
    assert ntfy_push.lint(note) == [], note
    line2 = note["message"].split("\n")[1]
    assert "no copy could be kept" in line2 and "a copy was kept" not in line2


# ── 5. SHRINK ──────────────────────────────────────────────────────────────────────────────
def test_a_merge_that_would_drop_cached_bars_is_refused_and_the_file_kept(tmp_path, feed,
                                                                         monkeypatch):
    paths = _home(tmp_path, n5=5)
    five = os.path.join(paths["ohlc_dir"], "QQQ_5m.csv")
    before = _bytes(five)
    first = int(pd.read_csv(five)["time"].min())
    real = cs._merge_bar_frames
    # a merge bug that loses the first session (the kind of rewrite the guard is the backstop for)
    monkeypatch.setattr(cs, "_merge_bar_frames", lambda old, fresh: real(old, fresh).loc[
        lambda d: d["time"] >= first + 86400])
    feed.clock = 10 ** 10
    feed.webull = _bars([D_ENTRY])
    logged = []
    merged, source, ok = cs.fetch_and_merge("5m", paths, log=logged.append)
    assert ok is True and _bytes(five) == before, "the file is kept as it was"
    rec = cs.bar_cache_refusal("5m", paths)
    assert rec["why"] == cs.BAR_CACHE_SHRINK
    (line,) = [m for m in logged if "5m CACHE GUARD" in m]
    assert "5 session(s) from" in line and "-> 5 from" in line and "REFUSED" in line
    # the bug fixed: the next fetch writes and drops the refusal
    monkeypatch.setattr(cs, "_merge_bar_frames", real)
    cs.fetch_and_merge("5m", paths, log=logged.append)
    assert cs.bar_cache_refusal("5m", paths) is None and _sessions(five) == 6
    assert any("is good again (6 session(s)" in m for m in logged)


def test_bars_dropped_counts_only_real_bars():
    old = pd.DataFrame({"time": [200960, 1_759_411_800, 1_759_412_100],
                        "open": [7.9e11, 2.0, 3.0], "high": [373221.0, 2.0, 3.0],
                        "low": [None, 2.0, 3.0], "close": [None, 2.0, 3.0], "volume": 1.0})
    assert cs._bar_times(old).tolist() == [1_759_411_800, 1_759_412_100], "the torn row is no bar"
    assert cs._bars_dropped(old, old) == 0
    assert cs._bars_dropped(old, old.iloc[1:]) == 0
    assert cs._bars_dropped(old, old.iloc[:2]) == 1
    assert cs._bars_dropped(old.iloc[:0], old.iloc[:0]) == 0
    assert cs._bars_dropped(old, cs._merge_bar_frames(old, old.assign(close=9.0))) == 0
    assert cs._bar_times(pd.DataFrame({"time": ["abc", "inf", ""], "open": 1, "high": 1,
                                       "low": 1, "close": 1})).empty
    assert cs._bar_times(None).empty and cs._bar_times(pd.DataFrame({"x": [1]})).empty


# ── 8. the 1m cache is unguarded; the stream path ──────────────────────────────────────────
def test_the_1m_cache_is_left_as_it_was(tmp_path, feed):
    paths = cs._paths(home=str(tmp_path))
    os.makedirs(paths["ohlc_dir"], exist_ok=True)
    _established(paths, tf="1m")
    one = os.path.join(paths["ohlc_dir"], "QQQ_1m.csv")
    feed.clock = 10 ** 10
    feed.webull = _bars([D_ENTRY])
    cs.fetch_and_merge("1m", paths, log=QUIET)
    assert os.path.exists(one) and cs.bar_cache_refusal("1m", paths) is None
    with open(one, "wb"):
        pass
    with pytest.raises(pd.errors.EmptyDataError):
        cs.fetch_and_merge("1m", paths, log=QUIET)
    with open(one, "wb") as f:
        f.write(EMPTY_FILES["too_many_fields"])
    with pytest.raises(pd.errors.ParserError):
        cs.fetch_and_merge("1m", paths, log=QUIET)
    assert not [n for n in os.listdir(paths["ohlc_dir"]) if "reach" in n or "guard_tail" in n]


def test_the_stream_path_makes_no_decision_while_the_guard_refuses(tmp_path, monkeypatch):
    from api import cloud_signal_stream as css
    paths = cs._paths(home=str(tmp_path))
    seen = []
    monkeypatch.setattr(css, "in_handoff_window", lambda now: True)
    monkeypatch.setattr(css, "_handle_handoff_window", lambda *a, **k: seen.append("window"))
    monkeypatch.setattr(css, "_resolve_pending_against_rest", lambda *a, **k: seen.append("rest"))
    monkeypatch.setattr(cs, "step", lambda **k: seen.append("step") or [])
    now = at(D_ENTRY, 9, 35, 1)
    css.run_stream_aware_step(now=now, paths=paths, fetch=False, log=QUIET)
    assert seen == ["window", "rest", "step"]
    cs._BAR_CACHE_REFUSED[os.path.abspath(cs._cache_path("5m", paths))] = {"why": "missing"}
    seen.clear()
    css.run_stream_aware_step(now=now, paths=paths, fetch=False, log=QUIET)
    assert seen == ["step"], "classic step() still runs (and skips the 5m legs itself)"


# ── 9. the note, its gates, the state read ─────────────────────────────────────────────────
@pytest.mark.parametrize("why,copy", [(cs.BAR_CACHE_MISSING, None),
                                      (cs.BAR_CACHE_EMPTY, "QQQ_5m.csv.corrupt-20261025-101500"),
                                      (cs.BAR_CACHE_EMPTY, None),
                                      (cs.BAR_CACHE_SHORT, None),
                                      (cs.BAR_CACHE_SHRINK, None)])
def test_the_note_for_every_cause_is_plain_and_lint_clean(why, copy):
    note = cs._bar_cache_guard_note("5m", {"why": why, "copy": copy},
                                    ["ORB_R6", "NOISE_382", "DIP_424"])
    assert ntfy_push.lint(note) == [], note
    line1, line2, line3 = note["message"].split("\n")
    until = "this is fixed" if why == cs.BAR_CACHE_SHRINK else "the file is back"
    assert line1 == ("Trading: AFFECTED - ORB, NOISE and DIP take no new trades and send no exit "
                     f"for their held shares until {until}.")
    assert "QQQ_5m.csv" in line2 and "corrupt" not in line2
    if why == cs.BAR_CACHE_EMPTY:
        assert ("a copy was kept beside it" in line2) == bool(copy)
        assert ("no copy could be kept" in line2) == (not copy)
    else:
        assert "copy was kept" not in line2 and "no copy could" not in line2
    if why == cs.BAR_CACHE_SHRINK:
        assert line3 == ("Do: ask Claude (PAPER-WB chat) to check the engine's bar merge - do not "
                         "replace the file.")
    else:
        assert line3 == "Do: ask Claude (PAPER-WB chat) to restore QQQ_5m.csv from the PC backup."
    assert note["priority"] == "high"


def test_no_page_off_the_box_or_for_shadow_legs_alone(tmp_path, feed):
    paths = cs._paths(home=str(tmp_path))
    rec = {"why": cs.BAR_CACHE_MISSING, "text": "x", "since": "s", "copy": None}
    cs._BAR_CACHE_REFUSED[os.path.abspath(cs._cache_path("5m", paths))] = rec
    now = at(D_ENTRY, 10, 0)
    live = {LIVE: dict(cs.CROWN_LEGS[LIVE], live_since=FIX_LIVE_SINCE)}
    w = {}
    cs._note_bar_cache_guard(live, now, paths, True, warnings=w)          # not the box
    assert feed.pushes == [] and w[cs.BAR_CACHE_GUARD_KEY]["5m"]["why"] == cs.BAR_CACHE_MISSING
    feed.box = True
    cs._note_bar_cache_guard(S._dip_legs(paths["home"]), now, paths, True)  # shadow legs only
    cs._note_bar_cache_guard(live, now, paths, False)                       # an offline tick
    assert feed.pushes == []
    cs._note_bar_cache_guard(live, now, paths, True)
    assert len(feed.pushes) == 1


def test_an_unreadable_state_counts_as_an_established_store(tmp_path):
    paths = cs._paths(home=str(tmp_path))
    assert cs._bar_cache_seen_before("5m", paths) is False          # no state.json: first boot
    os.makedirs(paths["state_dir"], exist_ok=True)
    with open(paths["state_path"], "w", encoding="utf-8") as f:
        f.write("{not json")
    assert cs._bar_cache_seen_before("5m", paths) is True
    _established(paths, tf="1m")
    assert cs._bar_cache_seen_before("5m", paths) is False


# ── 5b. SHORT: a shorter copy put in place by hand ─────────────────────────────────────────
def _keep_last_sessions(path, sessions, dst=None):
    """Write `path`'s last `sessions` sessions to `dst` (default: over `path`, through a temp
    file and os.replace -- an operator's mv)."""
    df = pd.read_csv(path)
    days = pd.to_datetime(df["time"], unit="s", utc=True).dt.tz_convert(cs.TZ).dt.date
    keep = sorted(days.unique())[-sessions:]
    tmp = (dst or path) + ".restore.tmp"
    df[days.isin(keep)].to_csv(tmp, index=False)
    os.replace(tmp, dst or path)


def _reach_first(paths):
    with open(_reach(paths), encoding="utf-8") as f:
        return json.load(f)["first_session"]


def test_a_shorter_copy_put_in_place_is_refused_paged_and_a_restore_clears_it(tmp_path, feed):
    paths = _home(tmp_path / "box")
    live, shadow = _legs(paths["home"])
    five = os.path.join(paths["ohlc_dir"], "QQQ_5m.csv")
    backup = _bytes(five)                  # a copy saved before the problem: it ends a day early
    feed.box = True
    feed.webull = _bars([D_ENTRY])
    lv, _sh = _tick(feed, paths, at(D_ENTRY, 9, 30, 5), live, shadow)
    assert [e["event"] for e in lv] == ["SEED"]
    first = _reach_first(paths)
    assert first == S.CRASH[CRASH_AT + 1 - 30][0].isoformat()
    reach_bytes = _bytes(_reach(paths))
    leg_before = _state(paths)["legs"][LIVE]
    shadow_before = _state(cs.shadow_paths(paths))["legs"]

    # the 10-25 hazard done by hand: a yfinance-length copy (10 sessions) moved over the file
    _keep_last_sessions(five, 10)
    short = _bytes(five)
    w = {}
    lv, sh = _tick(feed, paths, at(D_ENTRY, 9, 35, 5), live, shadow, warnings=w)
    assert lv == [] and sh == [], "no decision off the shorter copy"
    assert _bytes(five) == short, "never written to (not even appended)"
    assert _state(paths)["legs"][LIVE] == leg_before
    assert _state(cs.shadow_paths(paths))["legs"] == shadow_before
    rec = cs.bar_cache_refusal("5m", paths)
    assert rec["why"] == cs.BAR_CACHE_SHORT and f"later than the {first}" in rec["text"]
    assert w[cs.BAR_CACHE_GUARD_KEY]["5m"]["why"] == cs.BAR_CACHE_SHORT
    assert _bytes(_reach(paths)) == reach_bytes, "the reach never moves later"
    (p,) = feed.pushes
    assert ntfy_push.lint(p) == [] and p["priority"] == "high"
    assert p["message"].split("\n")[1].startswith("The QQQ_5m.csv price file now starts later")
    assert not [n for n in os.listdir(paths["ohlc_dir"]) if ".corrupt-" in n], "nothing to copy"

    # restored from the copy saved before the problem (same first day, ends a day early): taken
    with open(five, "wb") as f:
        f.write(backup)
    lv, _sh = _tick(feed, paths, at(D_ENTRY, 9, 45, 5), live, shadow)
    assert cs.bar_cache_refusal("5m", paths) is None
    assert "ENTRY" in [e["event"] for e in lv], "the legs decide again"
    assert _sessions(five) == 31 and _reach_first(paths) == first
    assert feed.pushes[-1]["title"] == "QQQ price file: OK"


def test_a_longer_restore_moves_the_reach_earlier_and_only_a_hand_delete_takes_a_later_one(
        tmp_path, feed):
    paths = _home(tmp_path / "box", n5=10)
    five = os.path.join(paths["ohlc_dir"], "QQQ_5m.csv")
    feed.clock = 10 ** 10
    feed.webull = _bars([D_ENTRY])
    logged = []
    cs.fetch_and_merge("5m", paths, log=logged.append)
    ten_back = S.CRASH[CRASH_AT + 1 - 10][0].isoformat()
    assert _reach_first(paths) == ten_back
    assert sum("recorded in QQQ_5m.reach.json" in m for m in logged) == 1
    # a longer trusted copy (40 sessions) put in place: the reach moves EARLIER
    longer = _home(tmp_path / "long", n5=40)
    os.replace(os.path.join(longer["ohlc_dir"], "QQQ_5m.csv"), five)
    cs.fetch_and_merge("5m", paths, log=logged.append)
    forty_back = S.CRASH[CRASH_AT + 1 - 40][0].isoformat()
    assert cs.bar_cache_refusal("5m", paths) is None and _reach_first(paths) == forty_back
    assert any(f"(was {ten_back})" in m for m in logged)
    # a later start (back to 10 sessions) is refused ...
    _keep_last_sessions(five, 10)
    cs.fetch_and_merge("5m", paths, log=logged.append)
    assert cs.bar_cache_refusal("5m", paths)["why"] == cs.BAR_CACHE_SHORT
    # ... until the reach file is deleted by hand: then the next good write records it afresh
    os.remove(_reach(paths))
    cs.fetch_and_merge("5m", paths, log=logged.append)
    assert cs.bar_cache_refusal("5m", paths) is None
    assert _reach_first(paths) == S.CRASH[CRASH_AT + 2 - 10][0].isoformat()


def test_a_torn_first_row_and_its_repair_never_trip_the_reach(tmp_path, feed):
    from tools import qqq_cache_repair
    paths = _home(tmp_path, n5=5)
    five = os.path.join(paths["ohlc_dir"], "QQQ_5m.csv")
    # 09-18's torn row, here with all four prices there: it still is no 1970 session
    torn = pd.DataFrame([{"time": 200960, "open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0,
                          "volume": 0.0}])
    pd.concat([torn, pd.read_csv(five)], ignore_index=True).to_csv(five, index=False)
    feed.clock = 10 ** 10
    feed.webull = _bars([D_ENTRY])
    cs.fetch_and_merge("5m", paths, log=QUIET)
    assert _reach_first(paths) == S.CRASH[CRASH_AT + 1 - 5][0].isoformat()
    assert int(pd.read_csv(five)["time"].iloc[0]) == 200960
    # tools/qqq_cache_repair.py --apply drops it (its own atomic rewrite of the file)
    qqq_cache_repair.main(["--home", paths["home"], "--apply"])
    assert int(pd.read_csv(five)["time"].iloc[0]) != 200960
    cs.fetch_and_merge("5m", paths, log=QUIET)
    assert cs.bar_cache_refusal("5m", paths) is None and _sessions(five) == 6
    # a file whose only "bar" is such a torn row reaches back to no session at all: SHORT
    torn.to_csv(five, index=False)
    cs.fetch_and_merge("5m", paths, log=QUIET)
    assert cs.bar_cache_refusal("5m", paths)["why"] == cs.BAR_CACHE_SHORT
    assert len(pd.read_csv(five)) == 1, "never written to"


def test_the_reach_file_alone_marks_an_established_store_and_an_unreadable_one_is_rewritten(
        tmp_path, feed):
    paths = _home(tmp_path, n5=5)
    five = os.path.join(paths["ohlc_dir"], "QQQ_5m.csv")
    feed.clock = 10 ** 10
    feed.webull = _bars([D_ENTRY])
    cs.fetch_and_merge("5m", paths, log=QUIET)           # no state.json: the first write
    assert os.path.exists(_reach(paths)) and not os.path.exists(paths["state_path"])
    saved = _bytes(five)
    os.remove(five)                                      # (a state.json reset changes nothing)
    cs.fetch_and_merge("5m", paths, log=QUIET)
    assert not os.path.exists(five)
    assert cs.bar_cache_refusal("5m", paths)["why"] == cs.BAR_CACHE_MISSING
    # an unreadable reach file: still established; the next good write records it again
    with open(_reach(paths), "w", encoding="utf-8") as f:
        f.write("{not json")
    assert cs._bar_cache_seen_before("5m", paths) is True
    with open(five, "wb") as f:
        f.write(saved)
    logged = []
    cs.fetch_and_merge("5m", paths, log=logged.append)
    assert cs.bar_cache_refusal("5m", paths) is None
    assert any("could not read QQQ_5m.reach.json" in m for m in logged)
    assert _reach_first(paths) == S.CRASH[CRASH_AT + 1 - 5][0].isoformat()


# ── 6. a restore landing mid-fetch ─────────────────────────────────────────────────────────
def test_a_restore_landing_while_the_fetch_is_in_flight_is_never_written_over(tmp_path, feed,
                                                                             monkeypatch):
    paths = _home(tmp_path / "box", n5=10)
    five = os.path.join(paths["ohlc_dir"], "QQQ_5m.csv")
    feed.clock = 10 ** 10
    feed.webull = _bars([D_ENTRY])
    cs.fetch_and_merge("5m", paths, log=QUIET)
    longer = _home(tmp_path / "long", n5=40)
    restored = _bytes(os.path.join(longer["ohlc_dir"], "QQQ_5m.csv"))
    tmp = five + ".restore.tmp"
    with open(tmp, "wb") as f:
        f.write(restored)
    real_fetch = cs._fetch_webull

    def fetch_while_the_operator_moves_a_copy_in(tf, count=None, log=print):
        os.replace(tmp, five)                            # the mv lands between read and write
        return real_fetch(tf, log=log)
    monkeypatch.setattr(cs, "_fetch_webull", fetch_while_the_operator_moves_a_copy_in)
    logged = []
    merged, source, ok = cs.fetch_and_merge("5m", paths, log=logged.append)
    assert ok is True and source == "webull" and len(merged)
    assert _bytes(five) == restored, "the restored copy is not overwritten"
    assert any("changed while this fetch was in flight" in m for m in logged)
    # the next fetch merges onto the restored file
    monkeypatch.setattr(cs, "_fetch_webull", real_fetch)
    cs.fetch_and_merge("5m", paths, log=QUIET)
    assert _sessions(five) == 41
    assert _reach_first(paths) == S.CRASH[CRASH_AT + 1 - 40][0].isoformat()


# ── 7. prices while the guard refuses ──────────────────────────────────────────────────────
def _qqq_exec_home(tmp_path, monkeypatch, paths):
    from api import qqq_exec as qe
    monkeypatch.setattr(cs, "DEFAULT_PATHS", paths)
    monkeypatch.setattr(qe, "_cs_module", lambda: cs)
    monkeypatch.setattr(qe, "_qqq_stream_instance", lambda: None)     # no live stream at all
    out = tmp_path / "qqq_out"
    out.mkdir(exist_ok=True)
    for name, f in (("OUT_DIR", ""), ("ORDERS_CSV", "orders.csv"), ("TRADES_CSV", "trades.csv"),
                    ("BROKER_ORDERS_CSV", "broker_orders.csv"), ("SERVING_LOCK", "SERVING.lock")):
        monkeypatch.setattr(qe, name, str(out / f) if f else str(out))
    return qe


def test_prices_survive_a_refusal_through_the_guard_tail(tmp_path, feed, monkeypatch):
    paths = _home(tmp_path / "box", n5=5)
    qe = _qqq_exec_home(tmp_path, monkeypatch, paths)
    five = os.path.join(paths["ohlc_dir"], "QQQ_5m.csv")
    tail = os.path.join(paths["ohlc_dir"], "QQQ_5m_guard_tail.csv")
    _established(paths)
    feed.clock = 10 ** 10
    feed.webull = _bars([D_ENTRY])
    cs.fetch_and_merge("5m", paths, log=QUIET)
    saved = _bytes(five)
    # a normal day: no tail, mark_bars is load_cached_bars exactly
    df, from_tail = cs.mark_bars("5m", paths)
    assert from_tail is False and df.equals(cs.load_cached_bars("5m", paths))
    px, src = qe._engine_mark_price("ORB", log=QUIET)
    assert src == "engine_webull" and px == float(df.sort_values("time")["close"].iloc[-1])

    # the file is lost while an ORB lot is open; newer bars keep arriving (refused)
    os.remove(five)
    feed.webull = _bars([D_ENTRY, D_X1])
    newest = float(feed.webull.sort_values("time")["close"].iloc[-1])
    cs.fetch_and_merge("5m", paths, log=QUIET)
    assert not os.path.exists(five) and os.path.exists(tail)
    assert len(pd.read_csv(tail)) == min(len(feed.webull), cs.WEBULL_TAIL_BARS)
    assert cs.mark_bars("5m", paths)[1] is True
    assert qe._engine_mark_price("ORB", log=QUIET) == (pytest.approx(newest), "engine_webull_guard")
    assert qe._exit_price_for_leg("NOISE", log=QUIET) == (pytest.approx(newest),
                                                          "engine_webull_guard")
    state = {"legs": {}, "_px_source": "test"}
    cfg = dict(qe.DEFAULT_CONFIG, signal_source="engine", shares={"ORB": 5})
    qe._open_lot(state, cfg, "ORB", "long", 5, 700.0, 500.0, 0.0, log=QUIET)
    qe._mark_and_check_breaker(state, cfg, None, None, log=QUIET)
    assert state["legs"]["ORB"]["mark_fresh"] is True, "the breaker still sees the open lot"
    qe._close_all(state, cfg, "EOD", quote_fn=None, ratio_fn=None, log=QUIET)
    assert "ORB" not in state["legs"], "the EOD flatten still closes it"
    with open(qe.TRADES_CSV, newline="", encoding="utf-8") as f:
        row = list(csv.DictReader(f))[-1]
    assert row["exit_reason"] == "EOD (px: engine_webull_guard)"
    assert abs(float(row["exit_px"]) - (newest - cfg.get("slippage_per_share", 0.0))) < 0.006

    # the file put back: the first good write removes the tail, prices come off the cache again
    with open(five, "wb") as f:
        f.write(saved)
    cs.fetch_and_merge("5m", paths, log=QUIET)
    assert cs.bar_cache_refusal("5m", paths) is None and not os.path.exists(tail)
    assert cs.mark_bars("5m", paths)[1] is False
    assert qe._engine_mark_price("ORB", log=QUIET) == (pytest.approx(newest), "engine_webull")


def test_without_the_guard_tail_nothing_prices_with_the_file_gone(tmp_path, feed, monkeypatch):
    """The gap the tail closes: the same refusal with the tail write disabled leaves the open
    lot with no price (the breaker blind, the EOD close 'lot left open') when the stream is
    not fresh."""
    paths = _home(tmp_path / "box", n5=5)
    qe = _qqq_exec_home(tmp_path, monkeypatch, paths)
    monkeypatch.setattr(cs, "_write_guard_tail", lambda *a, **k: None)
    _established(paths)
    feed.clock = 10 ** 10
    feed.webull = _bars([D_ENTRY])
    cs.fetch_and_merge("5m", paths, log=QUIET)
    os.remove(os.path.join(paths["ohlc_dir"], "QQQ_5m.csv"))
    cs.fetch_and_merge("5m", paths, log=QUIET)
    assert qe._exit_price_for_leg("ORB", log=QUIET) == (None, None)


def test_mark_bars_prefers_whichever_is_newer_and_raises_as_the_cache_does(tmp_path):
    paths = cs._paths(home=str(tmp_path))
    os.makedirs(paths["ohlc_dir"], exist_ok=True)
    five = os.path.join(paths["ohlc_dir"], "QQQ_5m.csv")
    tail = os.path.join(paths["ohlc_dir"], "QQQ_5m_guard_tail.csv")
    old, new = _bars([D_ENTRY]), _bars([D_X1])
    old.to_csv(five, index=False)
    new.to_csv(tail, index=False)
    df, from_tail = cs.mark_bars("5m", paths)
    assert from_tail is True and df["time"].tolist() == new["time"].tolist()
    new.to_csv(five, index=False)
    old.to_csv(tail, index=False)
    df, from_tail = cs.mark_bars("5m", paths)
    assert from_tail is False and df["time"].tolist() == new["time"].tolist()
    # an unparseable cache: the tail when it has bars, else the cache's own error
    with open(five, "wb") as f:
        f.write(EMPTY_FILES["too_many_fields"])
    assert cs.mark_bars("5m", paths)[1] is True
    with open(tail, "wb") as f:
        f.write(b"")
    with pytest.raises(pd.errors.ParserError):
        cs.mark_bars("5m", paths)
    os.remove(tail)
    with pytest.raises(pd.errors.ParserError):
        cs.mark_bars("5m", paths)


# ── 9b. the live_since gate; the heartbeat ─────────────────────────────────────────────────
def test_no_page_for_a_live_leg_before_its_live_since(tmp_path, feed):
    paths = cs._paths(home=str(tmp_path))
    rec = {"why": cs.BAR_CACHE_MISSING, "text": "x", "since": "s", "copy": None}
    cs._BAR_CACHE_REFUSED[os.path.abspath(cs._cache_path("5m", paths))] = rec
    feed.box = True
    now = at(D_ENTRY, 10, 0)
    later = {LIVE: dict(cs.CROWN_LEGS[LIVE], live_since=D_X1.isoformat())}
    w = {}
    cs._note_bar_cache_guard(later, now, paths, True, warnings=w)
    assert feed.pushes == [] and cs._BAR_CACHE_NOTED == {}
    assert w[cs.BAR_CACHE_GUARD_KEY]["5m"]["why"] == cs.BAR_CACHE_MISSING, "still named"
    cs._note_bar_cache_guard({LIVE: dict(cs.CROWN_LEGS[LIVE], live_since=FIX_LIVE_SINCE)}, now,
                             paths, True)
    assert len(feed.pushes) == 1


def test_the_live_thread_puts_an_open_refusal_on_its_heartbeat(tmp_path, monkeypatch):
    import threading
    paths = cs._paths(home=str(tmp_path / "live"))
    monkeypatch.setattr(cs, "DEFAULT_PATHS", paths)
    monkeypatch.setattr(cs, "CROWN_LEGS", {})
    monkeypatch.setattr(cs, "SHADOW_LEGS", {})
    monkeypatch.setattr(cs, "_is_cloud_host", lambda: False)
    monkeypatch.setattr(cs.market_calendar, "is_session", lambda d: True)
    monkeypatch.setattr(cs.market_calendar, "session_close_et", lambda d: "16:00")
    monkeypatch.setattr(cs, "RTH_OPEN", cs._dt.time(0, 0))
    monkeypatch.setattr(cs, "RTH_CLOSE", cs._dt.time(23, 59, 59))
    entry = {"why": cs.BAR_CACHE_SHORT, "since": "2026-10-25T10:00:05-04:00", "copy": None}

    def fake_step(now=None, legs=None, paths=None, fetch=True, warnings=None, **kw):
        warnings[cs.BAR_CACHE_GUARD_KEY] = {"5m": entry}
        return []

    stop = threading.Event()
    monkeypatch.setattr(cs, "step", fake_step)
    monkeypatch.setattr(cs._time, "sleep", lambda s: stop.set())     # one loop, then stop
    cs._engine_thread_run(stop=stop, log=QUIET)
    with open(paths["heartbeat_path"], encoding="utf-8") as f:
        hb = json.load(f)
    assert hb["ok"] is True and hb[cs.BAR_CACHE_GUARD_KEY] == {"5m": entry}
    assert hb["note"].startswith("0 event(s)")
    assert "5m CACHE GUARD: short since 2026-10-25T10:00:05-04:00" in hb["note"]
