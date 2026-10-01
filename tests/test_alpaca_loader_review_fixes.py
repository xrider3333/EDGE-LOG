"""Three real defects in the staged Alpaca loader, from MANAGER's review of 2026-09-30.

None of them can fire today - no keys, no stock master exists - which is exactly why they were
worth fixing now rather than after the first pull.

FINDING 10 is the one that should sting. My first test file for this loader opened with "an
unpinned lookup must never substitute one for the other" and then never called find_master. It
could not have: `alpaca_split_rth` sorts BEFORE `nt_noadj_rth` and `tv`, and it was not in the
excluded-source list, so the claim was false. The library already holds QQQ 1m and 5m from the
NinjaTrader capture, so the first QQQ stock pull would have re-pointed every unpinned QQQ lookup
at split-adjusted data - including api/bars.py's fallback. That is the same shape as the
September regression that re-pointed the live NT gate at back-adjusted prices.

FINDING 4: `adjustment=split` re-adjusts the WHOLE history as of the query, so after a split the
stored bars and the new ones are on different bases. "Existing rows win" - right for a
non-adjusted futures master - then splices a 10:1 cliff into the middle of a series, and because
rows only grow the write guard never sees it.

FINDING 5: the cash session ends at 13:00 ET on about three days a year, so filtering every day
to 16:00 left extended-hours prints inside a master labelled "rth".
"""
import importlib.util
import os
import sqlite3
import sys

import pandas as pd
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

TOOL = os.path.join(ROOT, "tools", "import_alpaca_stocks.py")


def _load():
    spec = importlib.util.spec_from_file_location("_alpaca_rev", TOOL)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


alp = _load()


@pytest.fixture(autouse=True)
def _quiet_log(monkeypatch):
    """The loader's log() appends to a file in the checkout. Tests used to leave fake master
    registrations in it (finding 10), so every test here captures it instead."""
    captured = []
    monkeypatch.setattr(alp, "log", lambda msg: captured.append(str(msg)))
    return captured


def _sec(stamp):
    return int(pd.Timestamp(stamp, tz="US/Eastern").timestamp())


def _bars(times, close):
    return pd.DataFrame({"time": times, "open": close, "high": close, "low": close,
                         "close": close, "volume": 100})


# ============================================= 10. an unpinned lookup must not get stock data

def test_a_stock_source_is_excluded_from_unpinned_lookups():
    from augur_engine import data
    assert data.is_adjusted_source("alpaca_split_rth") is True
    assert data.is_adjusted_source("alpaca_raw_eth") is True
    assert data.is_adjusted_source("nt_noadj_rth") is False
    assert data.is_adjusted_source("db_noadj_rth") is False


def test_the_same_ticker_collision_that_would_have_bitten_QQQ(tmp_path, monkeypatch):
    """The real case: QQQ 5m already exists from the NinjaTrader capture. Registering an Alpaca
    QQQ 5m master must NOT change what an unpinned lookup returns. This is the test the first
    file should have had."""
    from augur_engine import data
    rows = [
        dict(instrument="QQQ", timeframe="5m", session="rth", source="nt_noadj_rth",
             filename="nt.csv"),
        dict(instrument="QQQ", timeframe="5m", session="rth", source="alpaca_split_rth",
             filename="alpaca.csv"),
    ]
    # list_masters orders by source, which is how alpaca_ would win: it sorts first.
    monkeypatch.setattr(data, "list_masters", lambda: sorted(rows, key=lambda r: r["source"]))
    assert rows[1]["source"] < rows[0]["source"], "fixture must reproduce the sort order"

    m = data.find_master("QQQ", "5m", session="rth")
    assert m is not None and m["source"] == "nt_noadj_rth", (
        "an unpinned QQQ lookup must still get the capture master, not split-adjusted stock bars")
    named = data.find_master("QQQ", "5m", session="rth", source="alpaca_split_rth")
    assert named["filename"] == "alpaca.csv", "naming the source must still reach it"


def test_a_stock_only_ticker_returns_nothing_unpinned(monkeypatch):
    """find_master returns None rather than substituting - failing to find data is recoverable,
    a service silently re-pointed at another price convention is not."""
    from augur_engine import data
    monkeypatch.setattr(data, "list_masters", lambda: [
        dict(instrument="AAPL", timeframe="5m", session="rth", source="alpaca_split_rth",
             filename="a.csv")])
    assert data.find_master("AAPL", "5m", session="rth") is None
    assert data.find_master("AAPL", "5m", session="rth",
                            source="alpaca_split_rth") is not None


# ================================================= 4. a changed split basis must not splice

def test_a_split_rebasing_is_detected():
    """NVDA's 2024 10:1: the bars both pulls share come back a tenth of the stored price."""
    t = [_sec("2024-06-04 10:00"), _sec("2024-06-05 10:00")]
    cur = _bars(t, [1150.0, 1220.0])
    new = _bars(t + [_sec("2024-06-07 10:00")], [115.0, 122.0, 120.9])
    changed, detail = alp.split_basis_changed(cur, new)
    assert changed is True
    assert "disagree by up to" in detail and "2024-06-04" in detail


def test_a_normal_top_up_is_not_mistaken_for_a_rebasing():
    """The common case - same prices, new bars on the end - must stay additive."""
    t = [_sec("2024-06-04 10:00"), _sec("2024-06-05 10:00")]
    cur = _bars(t, [100.0, 101.0])
    new = _bars(t + [_sec("2024-06-06 10:00")], [100.0, 101.0, 102.0])
    assert alp.split_basis_changed(cur, new)[0] is False


def test_a_cent_of_vendor_rounding_is_not_a_rebasing():
    t = [_sec("2024-06-04 10:00")]
    assert alp.split_basis_changed(_bars(t, [100.00]), _bars(t, [100.01]))[0] is False


def test_no_overlap_means_nothing_to_compare():
    a = _bars([_sec("2024-06-04 10:00")], [100.0])
    b = _bars([_sec("2024-07-04 10:00")], [10.0])
    assert alp.split_basis_changed(a, b)[0] is False


def test_a_rebasing_replaces_the_master_instead_of_splicing(tmp_path, _quiet_log):
    """The whole point: after a rebasing the stored file must be on ONE basis."""
    db = tmp_path / "t.db"
    conn = sqlite3.connect(db)
    conn.execute("""CREATE TABLE csv_files (id INTEGER PRIMARY KEY, name TEXT, filename TEXT,
        instrument TEXT, timeframe TEXT, rows INT, date_from TEXT, date_to TEXT,
        created_at TEXT, is_master INT, source TEXT, provenance TEXT, session TEXT)""")
    conn.commit()
    alp.UP = str(tmp_path)

    t = [_sec("2024-06-04 10:00"), _sec("2024-06-05 10:00")]
    alp.upsert_master(conn, "NVDA", "5m", "alpaca_split_rth", "rth", _bars(t, [1150.0, 1220.0]))
    conn.commit()
    fn = conn.execute("SELECT filename FROM csv_files").fetchone()[0]

    post = _bars(t + [_sec("2024-06-07 10:00")], [115.0, 122.0, 120.9])
    alp.upsert_master(conn, "NVDA", "5m", "alpaca_split_rth", "rth", post)
    conn.commit()

    stored = pd.read_csv(os.path.join(str(tmp_path), fn))
    assert list(stored["close"]) == [115.0, 122.0, 120.9], "one basis, not two"
    ratios = (stored["close"].shift(-1) / stored["close"]).dropna()
    assert ratios.min() > 0.5, "no fake crash left in the series"
    assert any("REBASED" in m for m in _quiet_log), "a wholesale replacement must be reported"


def test_a_rebasing_that_would_LOSE_history_is_refused(tmp_path, _quiet_log):
    """If the new pull does not reach as far back as the stored one, replacing it would drop
    history - so it refuses and says what to re-run instead."""
    db = tmp_path / "t.db"
    conn = sqlite3.connect(db)
    conn.execute("""CREATE TABLE csv_files (id INTEGER PRIMARY KEY, name TEXT, filename TEXT,
        instrument TEXT, timeframe TEXT, rows INT, date_from TEXT, date_to TEXT,
        created_at TEXT, is_master INT, source TEXT, provenance TEXT, session TEXT)""")
    conn.commit()
    alp.UP = str(tmp_path)
    old_t = [_sec("2024-01-02 10:00"), _sec("2024-06-04 10:00")]
    alp.upsert_master(conn, "NVDA", "5m", "alpaca_split_rth", "rth", _bars(old_t, [900.0, 1150.0]))
    conn.commit()
    fn = conn.execute("SELECT filename FROM csv_files").fetchone()[0]
    before = open(os.path.join(str(tmp_path), fn), encoding="utf-8").read()

    short = _bars([_sec("2024-06-04 10:00")], [115.0])      # rebased but only the recent bar
    alp.upsert_master(conn, "NVDA", "5m", "alpaca_split_rth", "rth", short)
    conn.commit()
    assert open(os.path.join(str(tmp_path), fn), encoding="utf-8").read() == before
    assert any("REFUSED" in m and "--start" in m for m in _quiet_log)


# ========================================== 5. RTH ends at the session's actual close

def test_a_half_day_is_cut_at_one_oclock():
    """2024-11-29, the day after Thanksgiving: 13:00 close. A 13:05 print is extended hours."""
    times = [_sec("2024-11-29 %02d:%02d" % (h, m))
             for h, m in ((9, 30), (12, 55), (13, 0), (13, 5), (15, 55))]
    kept = alp.rth_filter(_bars(times, 100.0))
    et = pd.to_datetime(kept["time"], unit="s", utc=True).dt.tz_convert("US/Eastern")
    assert [x.strftime("%H:%M") for x in et] == ["09:30", "12:55"]


def test_a_normal_day_still_runs_to_four_oclock():
    times = [_sec("2024-11-26 %02d:%02d" % (h, m))
             for h, m in ((9, 30), (13, 5), (15, 55), (16, 0))]
    kept = alp.rth_filter(_bars(times, 100.0))
    et = pd.to_datetime(kept["time"], unit="s", utc=True).dt.tz_convert("US/Eastern")
    assert [x.strftime("%H:%M") for x in et] == ["09:30", "13:05", "15:55"]


def test_an_unlisted_year_keeps_the_normal_close():
    """An unknown half day is kept, not dropped - for a filter that only trims, erring towards
    keeping a real bar is the safe direction, and the list is easy to extend."""
    times = [_sec("2035-07-03 14:00")]
    assert len(alp.rth_filter(_bars(times, 100.0))) == 1


def test_the_half_day_list_covers_the_data_the_loader_can_pull():
    """Alpaca history starts 2016, so a list that began later would silently miss early days."""
    years = {d[:4] for d in alp.EARLY_CLOSE_DATES}
    assert "2016" in years and "2026" in years


def test_an_empty_frame_is_handled():
    assert alp.rth_filter(pd.DataFrame({"time": []})) is not None
