"""tools/harm_monitor.py (FRONTIER, BOOK.md 10aq): planted trips must trip, a backtest-like path must not, and the post puts trips first.
Pure functions only - no data, no Firestore, no inbox write."""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))
import harm_monitor as HM  # noqa: E402


def test_bands_frozen_and_complete():
    assert set(HM.ORDER) == set(HM.BANDS)
    for nm, b in HM.BANDS.items():
        assert b["mu"] > 0 and b["sd"] > 0 and 2.0 < b["c"] < 3.0 and b["dd_alarm"] > 0, nm
    assert HM.BANDS["ORB"]["big"] and HM.BANDS["TTM x3"]["big"] and HM.BANDS["NOISE"]["big"] is None


def test_planted_shortfall_trips_a1_not_a2():
    b = HM.BANDS["NOISE"]
    x = np.full(300, -60.0)                                  # a quiet, slowly losing leg: an $18k drawdown (under A2) but far behind pace
    r = HM.evaluate(x, b)
    assert r["a1"] and r["a1_text"].startswith("TRIPPED")
    assert r["dd_max"] == 60.0 * 300 and not r["a2"]


def test_planted_drawdown_trips_a2():
    b = HM.BANDS["ORB"]
    x = np.r_[np.full(40, b["mu"]), np.full(10, -6000.0), np.full(40, b["mu"])]    # one $60k crash inside an otherwise on-pace record
    r = HM.evaluate(x, b)
    assert r["a2"] and r["dd_max"] == 60000.0 and r["a2_text"].startswith("TRIPPED")


def test_on_pace_path_does_not_trip():
    for nm, b in HM.BANDS.items():
        r = HM.evaluate(np.full(600, b["mu"]), b)               # exactly the backtest's pace every day: S = 0, no drawdown
        assert not r["a1"] and not r["a2"], nm
        assert r["a1_text"].startswith("ahead of the backtest's pace by $0")


def test_backtest_like_random_path_does_not_trip():
    rng = np.random.default_rng(20261009)                       # a WF-like path (the leg's own mean / sd, 1 year); fixed seed, checked not to trip
    b = HM.BANDS["#463"]
    x = rng.normal(b["mu"], b["sd"], 292)
    r = HM.evaluate(x, b)
    assert not r["a1"] and not r["a2"], (r["a1_worst_z"], r["dd_max"])


def test_a1_checks_weekly_and_is_sticky():
    b = HM.BANDS["NOISE"]
    x = np.r_[np.full(30, -3000.0), np.full(400, b["mu"] + 2000.0)]     # deep early hole, then a strong recovery past the line
    r = HM.evaluate(x, b)
    assert r["a1"], "a trip at any past weekly check stays a trip"
    assert r["a1_z"] > r["a1_worst_z"]


def test_empty_and_big_day_watch():
    r = HM.evaluate([], HM.BANDS["ORB"])
    assert not r["a1"] and not r["a2"] and r["days"] == 0
    b = HM.BANDS["TTM x3"]
    r = HM.evaluate(np.r_[np.full(146, b["mu"]), [b["big"] + 1.0]], b)
    assert r["big_days"] == 1 and abs(r["big_expected"] - b["big_per_year"] * 147 / 292.0) < 1e-9 and "watch line only" in r["watch_text"]


def test_trip_names_its_first_check_row():
    b = HM.BANDS["NOISE"]
    x = np.r_[np.full(12, -2000.0), np.full(200, b["mu"] + 3000.0)]       # tripped at an early check, recovered since
    r = HM.evaluate(x, b)
    assert r["a1"] and r["a1_first_trip_row"] in (6, 12) and "stays tripped" in r["a1_text"] and "ahead of" in r["a1_text"]


def test_find_holes_runs_vs_single_sessions():
    import pandas as pd
    ref = set(pd.bdate_range("2026-07-01", "2026-07-31"))
    have = ref - set(pd.bdate_range("2026-07-06", "2026-07-10")) - {pd.Timestamp("2026-07-20")}
    runs, singles = HM.find_holes(have, ref)
    assert len(runs) == 1 and len(runs[0]) == 5 and runs[0][0] == pd.Timestamp("2026-07-06")
    assert singles == [pd.Timestamp("2026-07-20")]
    assert HM.find_holes(ref, ref) == ([], [])


def test_paused_leg_is_not_read_and_is_named():
    import pandas as pd
    b = HM.BANDS
    fw = {nm: pd.Series(np.full(30, b[nm]["mu"])) for nm in HM.ORDER}
    meta = {"paused": {"ENGU-Q": "its master has no bars on 2026-07-01..2026-08-05 (25 sessions)", "#463": "a leg is paused (ENGU-Q)"},
            "notes": ["data ends 2026-10-08, 1 weekday(s) before the run day"], "end": pd.Timestamp("2026-10-08")}
    reads = HM.read_all(fw, meta)
    assert reads["ENGU-Q"]["paused"] and "a1" not in reads["ENGU-Q"]
    txt = HM.format_post(reads, "2026-10-12", meta)
    assert "data through 2026-10-08" in txt.splitlines()[0]
    assert "- PAUSED: ENGU-Q" in txt and "- PAUSED: #463" in txt and "- Data note: data ends" in txt
    assert not any(l.startswith("- ENGU-Q (") for l in txt.splitlines())


def test_post_lists_trips_first_then_every_leg():
    b = HM.BANDS
    reads = {"ORB": HM.evaluate(np.full(60, b["ORB"]["mu"]), b["ORB"]),
             "TTM x3": HM.evaluate(np.full(60, b["TTM x3"]["mu"]), b["TTM x3"]),
             "NOISE": HM.evaluate(np.full(300, -60.0), b["NOISE"]),
             "ENGU-Q": HM.evaluate(np.full(60, b["ENGU-Q"]["mu"]), b["ENGU-Q"]),
             "#463": HM.evaluate(np.full(60, b["#463"]["mu"]), b["#463"])}
    txt = HM.format_post(reads, "2026-10-12")
    lines = txt.splitlines()
    assert lines[1].startswith("- TRIP: NOISE")
    assert [l.split(" ")[1] for l in lines[2:6]] == ["ORB", "TTM", "ENGU-Q", "#463"]
    assert "read-only" in lines[0] and "never 'fine'" in lines[-1]
    assert lines[-2].startswith("- On record: NOISE A1 at the 07-17 check")
