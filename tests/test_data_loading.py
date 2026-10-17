"""Unit tests for augur_engine.data.load_master_arrays — master-CSV -> OHLCV arrays.

The date-slice + day_id factorization is look-ahead-critical: day_id must be
re-derived AFTER any date slice so it stays 0-based and contiguous, or every
day_id-aware strategy would silently key off shifted day boundaries. These tests use
a tiny synthetic CSV (no real data, no sqlite) with monkeypatched UPLOADS to pin:
  * day_id groups ET calendar days as 0,0,0,1,1
  * date_from / date_to slice correctly (date_to is inclusive of the whole day)
  * day_id is re-factorized to 0-based after a slice (the look-ahead-safety property)
  * a missing volume column yields volume=None
"""
import numpy as np
import pandas as pd
import pytest

import augur_engine.data as D

# 3 bars on ET 2026-03-02, 2 bars on 2026-03-03 (EST, UTC-5).
_ROWS = [
    ("2026-03-02 10:00", 1.0, 2.0, 0.5, 1.5, 10),
    ("2026-03-02 10:05", 1.0, 2.0, 0.5, 1.5, 11),
    ("2026-03-02 10:10", 1.0, 2.0, 0.5, 1.5, 12),
    ("2026-03-03 10:00", 1.0, 2.0, 0.5, 1.5, 20),
    ("2026-03-03 10:05", 1.0, 2.0, 0.5, 1.5, 21),
]


@pytest.fixture
def master(tmp_path, monkeypatch):
    """Write the synthetic master CSV into a temp UPLOADS dir and return a master row.
    Returns a factory so a test can also request the no-volume variant."""
    def _make(with_volume=True):
        cols = ["time", "open", "high", "low", "close", "volume"]
        rows = [(int(pd.Timestamp(t, tz="US/Eastern").timestamp()), o, h, l, c, v)
                for (t, o, h, l, c, v) in _ROWS]
        df = pd.DataFrame(rows, columns=cols)
        if not with_volume:
            df = df.drop(columns=["volume"])
        name = "m.csv" if with_volume else "nv.csv"
        df.to_csv(tmp_path / name, index=False)
        monkeypatch.setattr(D, "UPLOADS", str(tmp_path))
        return {"filename": name, "name": "TEST"}
    return _make


def test_day_id_groups_calendar_days(master):
    a = D.load_master_arrays(master())
    assert a["day_id"].tolist() == [0, 0, 0, 1, 1]
    assert len(a["close"]) == 5
    assert a["close"].dtype == np.float64


def test_arrays_and_meta_present(master):
    m = master()
    a = D.load_master_arrays(m)
    assert set(["open", "high", "low", "close", "volume", "day_id", "index", "meta"]) <= set(a)
    assert a["meta"] is m
    assert a["volume"][0] == 10.0


def test_date_from_slices_and_refactorizes_day_id(master):
    a = D.load_master_arrays(master(), date_from="2026-03-03")
    # only the 03-03 bars survive, and day_id restarts at 0 (NOT 1)
    assert len(a["close"]) == 2
    assert a["day_id"].tolist() == [0, 0]


def test_date_to_is_inclusive_of_whole_day(master):
    a = D.load_master_arrays(master(), date_to="2026-03-02")
    assert len(a["close"]) == 3
    assert a["day_id"].tolist() == [0, 0, 0]


def test_date_window_both_ends(master):
    a = D.load_master_arrays(master(), date_from="2026-03-02", date_to="2026-03-02")
    assert len(a["close"]) == 3


def test_missing_volume_column_is_none(master):
    a = D.load_master_arrays(master(with_volume=False))
    assert a["volume"] is None


# -- ETH session cut (MANAGER #98, 2026-10-16) ------------------------------------------------------------------
# A CME ETH session dated D runs 18:00 ET D-1 .. 17:00 ET D (to 17:29 in the 2010-15 masters). A date_to window on
# an ETH master must stop at the 18:00 roll of date_to, not at midnight, or it carries the next session's evening.

def _eth_master(tmp_path, monkeypatch, stamps, name="eth.csv", session="eth", source="db_noadj_eth"):
    rows = [(int(pd.Timestamp(t, tz="US/Eastern").timestamp()), 1.0, 2.0, 0.5, 1.5, 5) for t in stamps]
    pd.DataFrame(rows, columns=["time", "open", "high", "low", "close", "volume"]).to_csv(tmp_path / name, index=False)
    monkeypatch.setattr(D, "UPLOADS", str(tmp_path))
    return {"filename": name, "name": "ETH TEST", "session": session, "source": source}


_THU = ["2016-06-30 16:59", "2016-06-30 17:15", "2016-06-30 17:29",   # session 06-30 (2010-15-era tail kept)
        "2016-06-30 18:00", "2016-06-30 23:58", "2016-07-01 09:30"]   # session 07-01


def test_an_eth_window_ends_at_the_1800_roll_of_date_to(tmp_path, monkeypatch):
    m = _eth_master(tmp_path, monkeypatch, _THU)
    a = D.load_master_arrays(m, date_to="2016-06-30")
    got = [str(t)[:16] for t in a["index"]]
    assert got == ["2016-06-30 16:59", "2016-06-30 17:15", "2016-06-30 17:29"]
    assert a["window_cut"] == "eth_session_18et"


def test_session_start_str_lets_a_second_window_meet_a_date_to_window_with_no_gap(tmp_path, monkeypatch):
    m = _eth_master(tmp_path, monkeypatch, _THU)
    start = D.session_start_str(m, "2016-07-01")
    assert start == "2016-06-30 18:00"
    opt = D.load_master_arrays(m, date_to="2016-06-30")
    lb = D.load_master_arrays(m, date_from=start)
    assert len(opt["close"]) + len(lb["close"]) == len(_THU)                 # no bar lost, none counted twice
    plain = D.load_master_arrays(m, date_from="2016-07-01")                  # a bare date_from stays midnight:
    assert str(plain["index"][0])[:16] == "2016-07-01 09:30"                 # the 06-30 evening is in neither
    assert str(lb["index"][0])[:16] == "2016-06-30 18:00"


def test_a_dst_sunday_and_a_friday_cut_at_the_wall_clock_roll(tmp_path, monkeypatch):
    m = _eth_master(tmp_path, monkeypatch, ["2026-03-08 17:59", "2026-03-08 18:00", "2026-03-06 16:59",
                                             "2026-03-06 18:30"], name="dst.csv")
    sun = D.load_master_arrays(m, date_from="2026-03-08", date_to="2026-03-08")
    assert [str(t)[11:16] for t in sun["index"]] == ["17:59"]                  # EDT began 02:00 that day
    assert D.window_end_ts(m, "2026-03-06") == pd.Timestamp("2026-03-06 18:00", tz="US/Eastern")


def test_rth_and_unlabelled_masters_keep_the_calendar_cut(tmp_path, monkeypatch):
    rth = _eth_master(tmp_path, monkeypatch, _THU, name="rth.csv", session="rth", source="db_noadj_rth")
    assert len(D.load_master_arrays(rth, date_to="2016-06-30")["close"]) == 5   # 18:00 and 23:58 stay in
    assert D.session_start_str(rth, "2016-07-01") == "2016-07-01"
    bare = {"filename": "rth.csv", "name": "BARE"}
    assert D.window_cut_rule(bare) == "calendar"
    assert D.window_cut_rule({"source": "db_adj_eth"}) == "eth_session_18et"     # no session column: source


def test_the_escape_hatch_restores_the_old_cut_for_repro_gates(tmp_path, monkeypatch):
    m = _eth_master(tmp_path, monkeypatch, _THU)
    monkeypatch.setenv("AUGUR_ETH_CALENDAR_CUT", "1")
    a = D.load_master_arrays(m, date_to="2016-06-30")
    assert len(a["close"]) == 5 and a["window_cut"] == "calendar"
    assert D.session_start_str(m, "2016-07-01") == "2016-07-01"


def test_the_memo_never_serves_one_cut_for_the_other(tmp_path, monkeypatch):
    m = _eth_master(tmp_path, monkeypatch, _THU)
    k1 = D._memo_key(m, None, "2016-06-30", 1.0, 2)
    monkeypatch.setenv("AUGUR_ETH_CALENDAR_CUT", "1")
    assert D._memo_key(m, None, "2016-06-30", 1.0, 2) != k1


def test_alpaca_stock_masters_labelled_eth_keep_the_calendar_cut():
    assert D.window_cut_rule({"session": "eth", "source": "alpaca_split_eth"}) == "calendar"
    assert D.window_cut_rule({"session": "ETH ", "source": "merged"}) == "eth_session_18et"


def test_reconcile_clips_platform_trades_with_the_engines_eth_cut():
    from augur_engine import reconcile as R
    class T:
        def __init__(self, ts):
            self.entry_dt = pd.Timestamp(ts)
    tr = [T("2026-10-15 16:30"), T("2026-10-15 19:30"), T("2026-10-14 20:00")]
    eth = R.clip_window(tr, "2026-10-14", "2026-10-15", session="eth")
    assert [str(t.entry_dt)[:16] for t in eth] == ["2026-10-15 16:30", "2026-10-14 20:00"]
    assert len(R.clip_window(tr, "2026-10-14", "2026-10-15")) == 3                # RTH/default: calendar day
