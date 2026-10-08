"""A refresh may correct a bar it already holds, within a bounded window, and the twin follows.

THE DEFECT (TBIS, 2026-10-08). ADJ_NQ_5m_RTH disagreed with its no-adjust parent on exactly one
of their 322,426 shared bars - its own last bar, 10-07 15:55, volume 2,645 against the true
14,755. Not a forming bar: it had closed seventeen hours before the build read it, and had closed
before the original write too, so the settle margin passed it. Yahoo had simply not finished
reporting a bar it had already closed. The refresh could only append past the seam, so nothing
could ever correct it; the adjusted build then snapshotted it and froze it for a day.

WHAT IS PINNED HERE. That a restatement inside the window is applied and announced; that settled
history is still untouchable; that a forming bar still never enters; that the row count does not
move, so the shrink guard still means what it meant; and the property TBIS verifies each morning -
a twin agrees with its parent on every shared bar, compared on VOLUME, which back-adjustment never
touches and which is what gave the defect away.
"""
import io
import os

import pandas as pd
import pytest

import tools.refresh_noadj_yahoo as rn


def _bars(start_t, n, tf_s=300, vol=5000.0, px=100.0):
    return pd.DataFrame({
        "time": [start_t + i * tf_s for i in range(n)],
        "open": [px + i for i in range(n)],
        "high": [px + i + 1 for i in range(n)],
        "low": [px + i - 1 for i in range(n)],
        "close": [px + i + 0.5 for i in range(n)],
        "volume": [vol] * n,
        "source": ["yahoo"] * n,
    })


# ───────────────────────────────────────────────────── the restatement itself
def test_a_feed_correcting_a_bar_we_already_hold_is_detected():
    """The real shape: a closed bar whose volume the feed later revises upward."""
    cur = _bars(1_000_000, 5, vol=5000.0)
    fresh = cur.copy()
    fresh.loc[4, "volume"] = 14755.0          # the 2,645 -> 14,755 case
    found = rn._restatements(cur, fresh)
    assert [(t, c) for t, c, _w, _n in found] == [(1_000_000 + 4 * 300, "volume")]
    assert found[0][2] == 5000.0 and found[0][3] == 14755.0


def test_an_unchanged_pull_restates_nothing():
    """A refresh that finds the same numbers must not rewrite the file."""
    cur = _bars(1_000_000, 5)
    assert rn._restatements(cur, cur.copy()) == []


def test_applying_a_restatement_changes_values_not_the_row_count():
    """The shrink guard counts rows. A restatement must leave that count alone, or the guard
    starts refusing legitimate corrections - and it is the one thing standing between a bad
    write and a destroyed master."""
    cur = _bars(1_000_000, 6, vol=5000.0)
    fresh = cur.copy()
    fresh.loc[5, "volume"] = 14755.0
    out = rn._apply_restatements(cur, fresh)
    assert len(out) == len(cur)
    assert list(out.columns) == list(cur.columns)
    assert list(out["time"]) == list(cur["time"])
    assert out.iloc[5]["volume"] == 14755.0


def test_a_restatement_does_not_rewrite_the_rows_around_it():
    cur = _bars(1_000_000, 6, vol=5000.0)
    fresh = cur.copy()
    fresh.loc[3, "close"] = 999.0
    out = rn._apply_restatements(cur, fresh)
    assert out.iloc[3]["close"] == 999.0
    for i in (0, 1, 2, 4, 5):
        assert out.iloc[i]["close"] == cur.iloc[i]["close"], i


def test_the_provenance_of_a_corrected_bar_is_left_alone():
    """It is the same bar from the same feed. Rewriting `source` would hide that it was ever
    corrected, and the audit trail is the point."""
    cur = _bars(1_000_000, 4, vol=5000.0)
    fresh = cur.copy()
    fresh["source"] = "somewhere_else"
    fresh.loc[3, "volume"] = 14755.0
    out = rn._apply_restatements(cur, fresh)
    assert list(out["source"]) == ["yahoo"] * 4


# ───────────────────────────────────────────────────── the window has an edge
def test_settled_history_is_outside_the_window():
    """The append-only rule was written after a master was truncated to half its rows. Only the
    last few days may be corrected; a pull that disagrees about older history is ignored, so one
    bad response can never rewrite years."""
    assert rn.RESTATE_WINDOW_S == 3 * 24 * 60 * 60
    now = 2_000_000_000
    old_t = now - rn.RESTATE_WINDOW_S - 3600          # just outside
    new_t = now - 3600                                 # inside
    assert old_t < now - rn.RESTATE_WINDOW_S <= new_t


def test_a_forming_bar_still_never_enters():
    """My change must not weaken the guard that already worked. A bar whose close plus the settle
    margin is still ahead of now is dropped, exactly as before."""
    now = 2_000_000_000
    closed = now - rn.YAHOO_SETTLE_S - 300 - 1
    forming = now - 60
    df = pd.DataFrame({"time": [closed, forming], "open": [1.0, 1.0], "high": [1.0, 1.0],
                       "low": [1.0, 1.0], "close": [1.0, 1.0], "volume": [1.0, 1.0]})
    kept = rn._drop_unclosed(df, "5m", now)
    assert list(kept["time"]) == [closed]


# ──────────────────────────────── the property TBIS checks: twin follows parent
def test_the_twin_matches_its_parent_on_every_shared_bar_after_a_restatement(tmp_path):
    """MANAGER's test. Plant a restated bar in the parent, rebuild the twin, and require the two
    to agree on every shared bar. Volume is the probe: back-adjustment shifts prices by a constant
    per roll but never touches volume, so equality is exact and a stale copy cannot hide."""
    bam = pytest.importorskip("tools.build_adjusted_masters")
    parent = _bars(int(pd.Timestamp("2021-03-01 14:30", tz="UTC").timestamp()), 60)
    p = tmp_path / "NOADJ_SYN_5m_RTH.csv"
    parent.to_csv(p, index=False)
    frame_before, _ = bam.build_one(str(p), "NQ", "5m", "back")

    # the feed revises the last bar, exactly as Yahoo did on 10-07 15:55
    fresh = parent.copy()
    fresh.loc[len(fresh) - 1, "volume"] = 14755.0
    restated = rn._apply_restatements(parent, fresh)
    assert rn._restatements(parent, fresh), "the fixture must actually restate something"
    restated.to_csv(p, index=False)

    frame_after, _ = bam.build_one(str(p), "NQ", "5m", "back")
    assert len(frame_after) == len(frame_before)
    merged = frame_after.set_index("time").join(
        restated.set_index("time")["volume"].rename("parent_vol"), how="inner")
    assert len(merged) == len(restated)
    disagree = merged[merged["volume"] != merged["parent_vol"]]
    assert disagree.empty, "twin disagrees with its parent on %d bar(s)" % len(disagree)
    assert merged["volume"].iloc[-1] == 14755.0, "the corrected bar did not reach the twin"


# ───────────────── the WIRING: main() must actually apply what the helpers can compute
def _fake_yf(frame):
    """A stand-in yfinance whose history() hands back `frame` in Yahoo's own column names."""
    import types as _t

    class _Ticker(object):
        def __init__(self, sym):
            self.sym = sym

        def history(self, period=None, interval=None):
            idx = pd.to_datetime(frame["time"], unit="s", utc=True)
            return pd.DataFrame({"Open": frame["open"].values, "High": frame["high"].values,
                                 "Low": frame["low"].values, "Close": frame["close"].values,
                                 "Volume": frame["volume"].values}, index=idx)

    mod = _t.ModuleType("yfinance")
    mod.Ticker = _Ticker
    return mod


def _registry(db_path, filename, rows):
    import sqlite3
    conn = sqlite3.connect(db_path)
    # date_to is here because main() updates it after a successful write - a fake registry
    # missing it fails the test for a reason that has nothing to do with restatement.
    conn.execute("CREATE TABLE csv_files (id INTEGER PRIMARY KEY, filename TEXT, "
                 "instrument TEXT, timeframe TEXT, session TEXT, rows INTEGER, "
                 "is_master INTEGER, source TEXT, date_to TEXT)")
    conn.execute("INSERT INTO csv_files (filename,instrument,timeframe,session,rows,is_master,"
                 "source) VALUES (?,?,?,?,?,1,'db_noadj')",
                 (filename, "NQ", "5m", "eth", rows))
    conn.commit()
    conn.close()


def test_main_applies_a_restatement_rather_than_only_being_able_to(tmp_path, monkeypatch):
    """THE WIRING TEST. Every check above calls the helpers directly, so deleting the call to
    them inside main() would leave all of them green while the live refresh quietly went back to
    append-only - the exact defect, reintroduced invisibly. This drives main() end to end against
    a fake feed and requires the corrected value to reach the file on disk."""
    fn = "NOADJ_SYN_5m_ETH.csv"
    up = tmp_path / "augur_uploads"
    up.mkdir()
    base = int(pd.Timestamp("2021-03-02 14:30", tz="UTC").timestamp())
    held = _bars(base, 8, vol=5000.0)
    (up / fn).write_text(held.to_csv(index=False), encoding="utf-8")
    db = str(tmp_path / "reg.db")
    _registry(db, fn, len(held))

    # the feed now reports the LAST held bar with its true volume, plus one genuinely new bar
    feed = _bars(base, 9, vol=5000.0)
    feed.loc[7, "volume"] = 14755.0
    now = int(feed["time"].iloc[8]) + 300 + rn.YAHOO_SETTLE_S + 60   # bar 8 is closed and settled

    monkeypatch.setattr(rn, "UP", str(up))
    monkeypatch.setattr(rn, "DB", db)
    monkeypatch.setitem(__import__("sys").modules, "yfinance", _fake_yf(feed))
    rn.main(now_s=now)

    out = pd.read_csv(up / fn)
    assert len(out) == 9, "the new bar should be appended as well (%d rows)" % len(out)
    assert out.iloc[7]["volume"] == 14755.0, "main() did not apply the restatement"
    assert list(out.iloc[:7]["volume"]) == [5000.0] * 7, "untouched bars moved"


def test_main_leaves_settled_history_alone(tmp_path, monkeypatch):
    """The same wiring, with the disagreement placed OUTSIDE the window: it must be ignored, so
    one bad pull can never rewrite years of history."""
    fn = "NOADJ_SYN2_5m_ETH.csv"
    up = tmp_path / "augur_uploads"
    up.mkdir()
    base = int(pd.Timestamp("2021-03-02 14:30", tz="UTC").timestamp())
    held = _bars(base, 8, vol=5000.0)
    (up / fn).write_text(held.to_csv(index=False), encoding="utf-8")
    db = str(tmp_path / "reg2.db")
    _registry(db, fn, len(held))

    feed = _bars(base, 8, vol=5000.0)
    feed.loc[0, "volume"] = 99999.0            # old bar, far outside the window
    now = int(feed["time"].iloc[7]) + 300 + rn.YAHOO_SETTLE_S + rn.RESTATE_WINDOW_S + 600

    monkeypatch.setattr(rn, "UP", str(up))
    monkeypatch.setattr(rn, "DB", db)
    monkeypatch.setitem(__import__("sys").modules, "yfinance", _fake_yf(feed))
    rn.main(now_s=now)

    out = pd.read_csv(up / fn)
    assert out.iloc[0]["volume"] == 5000.0, "settled history was rewritten"
