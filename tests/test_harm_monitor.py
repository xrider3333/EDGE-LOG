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


# ------------------------------------------------------------------ the Webull legs (BOOK.md 10ax)
def test_webull_bands_frozen_and_complete():
    assert set(HM.WEBULL_ORDER) == set(HM.WEBULL_BANDS) == set(HM.WEBULL_UNIT) == set(HM.WEBULL_START)
    for nm, b in HM.WEBULL_BANDS.items():
        assert b["mu"] > 0 and b["sd"] > 0 and b["c"] > 2.0 and b["dd_alarm"] > 0, nm
    assert HM.WEBULL_BANDS["ORB_R6"]["big"] and HM.WEBULL_BANDS["NOISE_382"]["big"] is None
    assert HM.WEBULL_WEEK_ROWS == 5


def test_webull_planted_trips_and_quiet_paths():
    b = HM.WEBULL_BANDS["NOISE_382"]
    r = HM.evaluate(np.full(300, -1.0), b, 252.0, HM.WEBULL_WEEK_ROWS)          # quietly losing $1 a session: $300 deep (under A2), far behind
    assert r["a1"] and not r["a2"]
    o = HM.WEBULL_BANDS["ORB_R6"]
    r = HM.evaluate(np.r_[np.full(30, o["mu"]), np.full(10, -70.0), np.full(30, o["mu"])], o, 252.0, HM.WEBULL_WEEK_ROWS)
    assert r["a2"] and r["dd_max"] == 700.0
    rng = np.random.default_rng(20261010)
    for nm, b in HM.WEBULL_BANDS.items():
        assert not any(HM.evaluate(np.full(250, b["mu"]), b, 252.0, 5)[k] for k in ("a1", "a2")), nm
        x = rng.normal(b["mu"], b["sd"], 252)                  # a backtest-like year (the band's own mean / sd); fixed seed, checked not to trip
        r = HM.evaluate(x, b, 252.0, 5)
        assert not r["a1"] and not r["a2"], (nm, r["a1_worst_z"], r["dd_max"])


def test_week_rows_sets_the_check_spacing():
    b = {"mu": 0.0, "sd": 1.0, "c": 2.0, "dd_alarm": 1e9}
    x = np.r_[np.full(5, -1.0), np.full(1, 3.0)]               # z at row 5 = -5/sqrt(5) = -2.24 (trips); at row 6 = -2/sqrt(6) = -0.82
    assert HM.evaluate(x, b, week_rows=5)["a1"] and not HM.evaluate(x, b)["a1"]
    assert HM.evaluate(x, b, week_rows=5)["a1_first_trip_row"] == 5


def _box_folder(root, name, trades, signals):
    import pandas as pd
    os.makedirs(os.path.join(root, name, "qqq_exec"))
    os.makedirs(os.path.join(root, name, "cloud_signal"))
    pd.DataFrame(trades).to_csv(os.path.join(root, name, "qqq_exec", "trades.csv"), index=False)
    pd.DataFrame(signals).to_csv(os.path.join(root, name, "cloud_signal", "signals.csv"), index=False)


def test_webull_forward_reads_the_newest_folder_at_plugin_size(tmp_path):
    root = str(tmp_path)
    T = lambda leg, tid, ex, sh, pnl, size=1.0, keel=1.0: {"leg": leg, "trade_id": tid, "exit_ts": ex, "shares": sh, "pnl": pnl, "size": size,
                                                          "keel_size": keel}
    trades = [T("NOISE", "NOISE_304-x", "2026-09-22 15:59:00", 10, 50.0),                   # another config, before NOISE_382's start
              T("NOISE", "NOISE_382-a", "2026-09-25 10:30:00", 15, -30.0, 1.5, None),      # sent at KEEL 1.5; keel only on the engine row
              T("NOISE", "NOISE_382-b", "2026-09-28 11:00:00", 20, 40.0, 2.0, 1.0),        # plugin size 2
              T("ORB", "ORB_R6-a", "2026-09-10 15:59:00", 10, 12.0),
              T("ORB", None, "2026-09-11 15:59:00", 5, -6.0)]                               # no trade id: by leg + date, at 10 sh
    sig = [{"leg": "NOISE_382", "event": "ENTRY", "trade_id": "NOISE_382-a", "keel_size": 1.5, "ref_time": "2026-09-25T09:40:00-04:00"},
           {"leg": "NOISE_382", "event": "EXIT", "trade_id": "NOISE_382-a", "keel_size": None, "ref_time": "2026-09-25T10:30:00-04:00"},
           {"leg": "NOISE_382", "event": "EXIT", "trade_id": "NOISE_382-b", "keel_size": None, "ref_time": "2026-09-28T11:00:00-04:00"}]
    _box_folder(root, "2026-09-30_1445", trades, sig)
    _box_folder(root, "2026-10-20_1445", [T("ORB", "ORB_R6-z", "2026-10-19 15:59:00", 10, 999.0)], sig)   # after the run day: ignored
    fw, meta = HM.webull_forward("2026-10-05", root)
    assert meta["folder"] == "2026-09-30_1445" and meta["end"] == "2026-09-30"
    n = fw["NOISE_382"]
    assert n.index[0].strftime("%Y-%m-%d") == "2026-09-24" and len(n) == 5                  # 09-24, 25, 28, 29, 30
    assert abs(n.sum() - (-30.0 / 15 * 10 * 1.0 + 40.0 / 20 * 10 * 2.0)) < 1e-9            # -20 at plugin size 1, +40 at plugin size 2
    assert abs(meta["keel_scale"]["NOISE_382"] - (10.0 / 20.0)) < 1e-9                       # sent $10 / plugin-size $20
    assert abs(fw["ORB_R6"].sum() - (12.0 - 12.0)) < 1e-9 and meta["trades"]["ORB_R6"] == 2
    assert "DIP_424F" not in fw
    assert any("1 ORB_R6 trade(s) have no trade id" in t for t in meta["notes"])
    assert any("the box ledger read is stale" in t for t in meta["notes"])                   # 09-30 folder, 10-05 run day
    reads = HM.read_webull(fw, meta)
    assert reads["DIP_424F"]["no_trades"] and reads["NOISE_382"]["keel_scale"] == meta["keel_scale"]["NOISE_382"]


def test_webull_missing_folder_is_an_error_not_a_crash(tmp_path):
    fw, meta = HM.webull_forward("2026-10-05", str(tmp_path))
    assert fw == {} and "no pull-job folder" in meta["error"]


def test_post_carries_the_webull_block_before_the_record():
    b = HM.BANDS
    reads = {nm: HM.evaluate(np.full(60, b[nm]["mu"]), b[nm]) for nm in HM.ORDER}
    wb = HM.WEBULL_BANDS
    wreads = {"ORB_R6": HM.evaluate(np.full(20, wb["ORB_R6"]["mu"]), wb["ORB_R6"], 252.0, 5),
              "NOISE_382": HM.evaluate(np.full(300, -1.0), wb["NOISE_382"], 252.0, 5),
              "DIP_424F": {"no_trades": True}}
    for nm in ("ORB_R6", "NOISE_382"):
        wreads[nm].update({"start": "2026-09-09", "trades": 3})
    wreads["ORB_R6"]["keel_scale"] = None
    wmeta = {"folder": "2026-10-10_1445", "end": "2026-10-09", "notes": ["1 ORB_R6 trade(s) have no trade id (assigned by leg and date)"]}
    lines = HM.format_post(reads, "2026-10-12", None, (wreads, wmeta)).splitlines()
    assert lines[1].startswith("- TRIP: Webull NOISE_382")
    i = next(k for k, l in enumerate(lines) if l.startswith("- Webull legs ("))
    assert lines[i - 1].startswith("- #463 (") and "2026-10-10_1445" in lines[i]
    assert lines[i + 1].startswith("- Webull data note:") and lines[i + 2].startswith("- Webull ORB_R6 at 10 sh")
    assert lines[i + 3] == "- Webull DIP_424F at 6 sh a lot: no trades yet."
    assert not any(l.startswith("- Webull NOISE_382 at") for l in lines)                       # a tripped leg is listed once, at the top
    assert lines[-2].startswith("- On record: NOISE A1 at the 07-17 check")
    err = HM.format_post(reads, "2026-10-12", None, ({}, {"error": "FileNotFoundError: x"})).splitlines()
    assert "- Webull legs not read: FileNotFoundError: x." in err and err[1] == "- No alarm tripped."


def test_webull_dip_reads_the_live_engine_key_and_slot_legs(tmp_path):
    """the live DIP leg trades under engine key DIP_424 (trade ids DIP_424-<UTC>-L-<SLOT>, executor legs DIP_STREAK .. DIP_GAPDN), not
    under its band name DIP_424F - a band-name match would never see a DIP trade (found 10-14 on the box's first DIP lots)"""
    root = str(tmp_path)
    T = lambda leg, tid, ex, sh, pnl: {"leg": leg, "trade_id": tid, "exit_ts": ex, "shares": sh, "pnl": pnl, "size": 1.0, "keel_size": None,
                                       "entry_px": 700.0, "exit_px": 700.0 + pnl / sh}
    trades = [T("DIP_STREAK", "DIP_424-20261013T133000Z-L-STREAK", "2026-10-15 09:35:00", 6, 24.0),
              T("DIP_GAPDN", "DIP_424-20261013T133000Z-L-GAPDN", "2026-10-15 09:35:00", 6, 18.0),
              T("DIP_RSI", None, "2026-10-16 09:35:00", 6, -12.0)]                         # no trade id: by the DIP_ slot-leg prefix
    sig = [{"leg": "DIP_424", "event": "EXIT", "trade_id": "DIP_424-20261013T133000Z-L-STREAK", "keel_size": None,
            "ref_time": "2026-10-15T09:30:00-04:00"},
           {"leg": "DIP_424", "event": "EXIT", "trade_id": "DIP_424-20261013T133000Z-L-GAPDN", "keel_size": None,
            "ref_time": "2026-10-15T09:30:00-04:00"},
           {"leg": "DIP_424", "event": "EXIT", "trade_id": "DIP_424-20261014T133000Z-L-RSI", "keel_size": None,
            "ref_time": "2026-10-16T09:30:00-04:00"}]
    _box_folder(root, "2026-10-16_1445", trades, sig)
    fw, meta = HM.webull_forward("2026-10-19", root)
    assert "DIP_424F" in fw and meta["trades"]["DIP_424F"] == 3 and meta["starts"]["DIP_424F"] == "2026-10-13"
    assert abs(fw["DIP_424F"].sum() - (24.0 + 18.0 - 12.0)) < 1e-9                         # 6 sh a lot: the $ as booked
    assert any("1 DIP_424F trade(s) have no trade id" in t for t in meta["notes"])
    assert not any("engine exits" in t for t in meta["notes"])                                # 3 engine exits = 3 executor trades
    r = HM.read_webull(fw, meta)
    assert not r["DIP_424F"].get("no_trades") and r["DIP_424F"]["trades"] == 3


def test_webull_dip_is_marked_to_market_from_the_folder_marks(tmp_path):
    """Q42: an open DIP lot's $ is booked day by day from each pull folder's state.json mark_px; the close books exit - last mark. A folder
    taken before 14:30 MST holds intraday marks and is not read."""
    import json
    root = str(tmp_path)
    lot = lambda tid, mark: {"trade_id": tid, "shares_remaining": 6, "entry_px": 739.55, "mark_px": mark}
    sig = [{"leg": "DIP_424", "event": "EXIT", "trade_id": "DIP_424-A", "keel_size": None, "ref_time": "2026-10-15T09:30:00-04:00"},
           {"leg": "DIP_424", "event": "EXIT", "trade_id": "DIP_424-B", "keel_size": None, "ref_time": "2026-10-15T09:30:00-04:00"}]
    closed = [{"leg": "DIP_STREAK", "trade_id": "DIP_424-A", "exit_ts": "2026-10-15 09:35:00", "shares": 6, "pnl": 6 * (746.0 - 739.55),
               "size": 1.0, "keel_size": None, "entry_px": 739.55, "exit_px": 746.0},
              {"leg": "DIP_GAPDN", "trade_id": "DIP_424-B", "exit_ts": "2026-10-15 09:35:00", "shares": 6, "pnl": 6 * (746.0 - 739.55),
               "size": 1.0, "keel_size": None, "entry_px": 739.55, "exit_px": 746.0}]
    for name, marks, rows in (("2026-10-13_1445", (743.57, 743.57), []), ("2026-10-14_1445", (745.0, 745.0), []),
                              ("2026-10-15_1445", None, closed), ("2026-10-16_1100", None, closed)):     # 10-16 11:00 = intraday
        _box_folder(root, name, rows or [dict(closed[0], trade_id="NOISE_382-x", leg="NOISE", exit_ts="2026-09-30 10:00:00")], sig)
        legs = {} if marks is None else {"DIP_STREAK": lot("DIP_424-A", marks[0]), "DIP_GAPDN": lot("DIP_424-B", marks[1])}
        json.dump({"legs": legs}, open(os.path.join(root, name, "qqq_exec", "state.json"), "w"))
    fw, meta = HM.webull_forward("2026-10-16", root)
    d = fw["DIP_424F"]
    assert abs(d["2026-10-13"] - 2 * 6 * (743.57 - 739.55)) < 1e-9
    assert meta["end"] == "2026-10-15"                                                    # the 10-16 11:00 folder is not a close
    assert abs(d["2026-10-14"] - 2 * 6 * (745.0 - 743.57)) < 1e-9
    assert abs(d["2026-10-15"] - 2 * 6 * (746.0 - 745.0)) < 1e-9
    assert abs(d.sum() - 2 * 6 * (746.0 - 739.55)) < 1e-9                                # MTM sums to the booked P&L
    assert any("taken before the close" in n for n in meta["notes"])
    assert HM.WEBULL_BANDS["DIP_424F"]["c"] < 4.0 and "DIP_424F" in HM.WEBULL_MTM


def _trend_days(n, up, start="2026-07-01"):
    import pandas as pd
    d = pd.bdate_range(start, periods=n)
    moves = pd.Series(0.02, index=d)                             # every day a trend day (>= 1.73%)
    orb = pd.Series([100.0 if i in up else -50.0 for i in range(n)], index=d)
    return moves, orb


def test_trend_capture_frozen_rule():
    assert HM.TREND_THR == 0.017319 and HM.TREND_BLOCK == 26 and HM.TREND_ALARM == 11 and HM.TREND_BASE == 0.6078
    import pandas as pd
    moves, orb = _trend_days(60, set(range(0, 20)) | set(range(26, 37)))   # block 1: 20 up, block 2: 11 up (trips), open: 0 of 8
    moves.iloc[-1] = 0.0172                                       # just under the threshold: not a trend day
    t = HM.trend_capture(moves, orb)
    assert t["days"] == 59 and [b["hits"] for b in t["blocks"]] == [20, 11]
    assert [b["tripped"] for b in t["blocks"]] == [False, True] and t["tripped"]
    assert t["open_days"] == 7 and t["open_hits"] == 0
    line = HM.trend_line(t, "2026-07-01")
    assert "TREND TRIP" in line and "report-only" in line and "1.73%" in line
    quiet = HM.trend_capture(*_trend_days(30, set(range(0, 16))))
    assert not quiet["tripped"] and "TREND TRIP" not in HM.trend_line(quiet, "2026-07-01")
    none = HM.trend_capture(pd.Series(0.001, index=moves.index), orb)
    assert none["days"] == 0 and "no NQ trend day" in HM.trend_line(none, "2026-07-01")
    assert "not read" in HM.trend_line({"error": "boom"}, "2026-07-01")


def test_post_carries_the_trend_line_after_the_legs():
    t = HM.trend_capture(*_trend_days(10, {1, 2}))
    reads = {nm: HM.evaluate(np.full(20, b["mu"]), b) for nm, b in HM.BANDS.items()}
    txt = HM.format_post(reads, "2026-10-12", {"trend": t})
    lines = txt.split("\n")
    i = [k for k, ln in enumerate(lines) if ln.startswith("- ORB trend-day capture")]
    assert len(i) == 1 and i[0] > max(k for k, ln in enumerate(lines) if ln.startswith("- #463"))


def test_exec_check_big_day_miss_and_slip():
    import pandas as pd
    S = pd.DataFrame([
        # trade A: a big long day, engine +$120 at 10 sh, executor +$100 (83%: booked)
        dict(leg="ORB_R6", event="ENTRY", side="long", ref_price=700.0, ref_time="2026-10-05T10:00:00-04:00", trade_id="ORB_R6-A"),
        dict(leg="ORB_R6", event="EXIT", side="long", ref_price=712.0, ref_time="2026-10-05T15:55:00-04:00", trade_id="ORB_R6-A"),
        # trade B: a big short day, engine +$100, executor +$50 (short of 80%)
        dict(leg="ORB_R6", event="ENTRY", side="short", ref_price=700.0, ref_time="2026-10-06T10:00:00-04:00", trade_id="ORB_R6-B"),
        dict(leg="ORB_R6", event="EXIT", side="short", ref_price=690.0, ref_time="2026-10-06T15:55:00-04:00", trade_id="ORB_R6-B"),
        # trade C: an ordinary day the executor never filled (a MISS)
        dict(leg="ORB_R6", event="ENTRY", side="long", ref_price=700.0, ref_time="2026-10-07T10:00:00-04:00", trade_id="ORB_R6-C"),
        dict(leg="ORB_R6", event="EXIT", side="long", ref_price=701.0, ref_time="2026-10-07T15:55:00-04:00", trade_id="ORB_R6-C"),
        # another leg's signals are ignored
        dict(leg="NOISE_382", event="ENTRY", side="long", ref_price=1.0, ref_time="2026-10-07T10:00:00-04:00", trade_id="NOISE_382-X"),
    ])
    T = pd.DataFrame([dict(trade_id="ORB_R6-A", pnl=100.0, shares=10), dict(trade_id="ORB_R6-B", pnl=50.0, shares=10)])
    c = HM.webull_exec_check(S, T, "2026-09-09", "2026-10-09")
    assert c["engine"] == 3 and c["filled"] == 2 and c["missed"] == [("2026-10-07", 10.0)]
    assert [(d, round(g, 6), x, ok) for d, g, x, ok in c["big"]] == [("2026-10-05", 120.0, 100.0, True), ("2026-10-06", 100.0, 50.0, False)]
    assert c["slip_n"] == 2 and abs(c["slip_mean"] - (-35.0)) < 1e-9
    line = HM.exec_line(c)
    assert "MISSED 2026-10-07" in line and "SHORT of 80%" in line and "booked" in line and "report-only" in line
    none = HM.webull_exec_check(S.iloc[:0], T.iloc[:0], "2026-09-09", "2026-10-09")
    assert none["engine"] == 0 and "no closed engine trade" in HM.exec_line(none)
    assert "not read" in HM.exec_line({"error": "x"})


def test_box_qqq_1m_merges_folders_newest_wins(tmp_path):
    import pandas as pd
    for d, rows in (("2026-10-12_1445", [(1792000000, 1.0, 1.5), (1792000060, 2.0, 2.5)]),
                    ("2026-10-13_1445", [(1792000060, 9.0, 9.5), (1792000120, 3.0, 3.5)])):
        os.makedirs(tmp_path / d / "ohlc")
        pd.DataFrame([dict(time=t, open=o, high=o, low=o, close=c, volume=0) for t, o, c in rows]).to_csv(tmp_path / d / "ohlc" / "QQQ_1m.csv",
                                                                                                     index=False)
    q = HM.box_qqq_1m(str(tmp_path))
    assert len(q) == 3 and list(q["o"]) == [1.0, 9.0, 3.0]                # the newer folder's copy of the shared minute wins
    assert q.index[0] == pd.Timestamp(1792000000, unit="s", tz="UTC").tz_convert("America/New_York").tz_localize(None)
    assert HM.box_qqq_1m(str(tmp_path / "none")) is None


def test_parity_line_words():
    pr = {"engine": 3, "live": 2, "missing_live": [("2026-09-21", 1)], "extra_live": []}
    line = HM.parity_line(pr)
    assert "NOT EMITTED LIVE: 2026-09-21 long" in line and "report-only" in line
    assert "Same days and sides" in HM.parity_line({"engine": 1, "live": 1, "missing_live": [], "extra_live": []})
    assert "not read" in HM.parity_line({"error": "x"})


def test_relay_line_words():
    assert "not read" in HM.relay_line({"error": "x"}, 0.0, 0, "2026-09-09")
    line = HM.relay_line({"n": 4, "net": 12.5}, -7.0, 5, "2026-09-09")
    assert "report-only" in line and "4 trade(s) since 2026-09-09" in line and "5 trade(s)" in line and "not a decider" in line

