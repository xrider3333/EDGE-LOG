"""THE NIGHTLY RE-CUT (Custom ML #151 item 2 + DISC #154, 2026-10-14; tools/keel_live_state.py
nightly_recut): under THE NQ FEED tonight's NQ rebuild IS the backtest, so after the nightly checks
the live state := tonight's nightly, the append log starts empty, and the feed learns only trades
after tonight's data.

COVERS: live == tonight's nightly + an empty log + the day archived + _prev gone + the ack; the feed
learns nothing already in tonight's data, then the next day's trades; the report (matched / differ
beyond s x 4.5 pts / missed / extra; per-entry 'behind'); a stale nightly refused, the live state
kept; old-cut rows left by a crash never applied to the new cut; build() re-cuts under the nq feed
and leaves the live state alone under the qqq feed.
"""
import json
import os
import sys

import numpy as np
import pandas as pd
import pytest

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(THIS_DIR)
for _p in (ROOT, THIS_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from api import cloud_signal as cs  # noqa: E402
from augur_engine import ml_keel as K  # noqa: E402
import tools.keel_intraday as KI  # noqa: E402
import tools.keel_live_state as L  # noqa: E402
from _keel_live_world import LEG, QUIET, LiveWorld  # noqa: E402
from test_keel_live_nq_feed import ARRAY_KEYS, STATE_KEYS, NQWorld, _same  # noqa: E402


@pytest.fixture(scope="module")
def base(tmp_path_factory):
    return LiveWorld(tmp_path_factory.mktemp("keel_recut") / "w")


@pytest.fixture
def nw(base, tmp_path):
    return NQWorld(base.clone(tmp_path / "w"))


def _tonight(nw):
    """Tonight's nightly over the master + the live days, installed like the 18:30 build does."""
    arr = nw.full_arrays()
    trades = nw.trades(arr, None)
    walk = K.keel_build_state(arr, [t[:3] for t in trades], version=nw.w.version)
    nw.w.install_nightly(walk, through=nw.w.live_days[-1], built_at="2024-02-06T23:30:00+00:00")
    return walk, arr, trades


def _recut(nw, walk, arr, trades, **kw):
    return L.nightly_recut(walk, arr, trades, nw.w.files["dir"], LEG, nw.w.version, log=QUIET, **kw)


def test_the_recut_makes_the_live_state_tonights_nightly_and_starts_an_empty_log(nw):
    res = nw.run()
    assert res["appended"]
    walk, arr, trades = _tonight(nw)
    rep = _recut(nw, walk, arr, trades)
    assert rep["recut"] is True and rep["appended"] == len(res["appended"])
    assert rep["matched"] == len(res["appended"]) and rep["differ"] == rep["missed"] == rep["extra"] == []
    live = nw.w.load("live_path")
    _same(live, walk)
    _same(nw.w.load("live_cut_path"), walk)
    meta = cs.keel_live_meta(live)
    assert meta["cut"]["data_through"] == str(nw.w.live_days[-1]) and meta["appended"] == []
    assert meta["cut"]["live_from"] == str(nw.w.live_days[0])
    assert KI.read_appends(nw.w.files["appends_path"]) == []
    assert not os.path.exists(nw.w.files["live_prev_path"])
    arch = os.path.join(nw.w.files["dir"], L.RECUT_ARCHIVE_DIR)
    (logf,) = [f for f in os.listdir(arch) if f.endswith(".jsonl")]
    assert len(KI.read_appends(os.path.join(arch, logf))) == len(res["appended"])
    ack = nw.w.ack()
    assert ack["n"] == walk["n"] and ack["last"]["status"] == "recut" and ack["appended"] == 0
    assert ack["feed"]["feed"] == "nq_yahoo", "the feed block survives the re-cut"
    assert KI.verify_live_state(nw.w.home, LEG, log=QUIET)["ok"] is True
    on_disk = json.load(open(os.path.join(nw.w.files["dir"], L.RECUT_REPORT_FILE), encoding="utf-8"))
    assert on_disk["recut"] is True and on_disk["new_n"] == walk["n"]


def test_after_the_recut_the_feed_learns_only_trades_after_tonights_data(nw):
    nw.run()
    walk, arr, trades = _tonight(nw)
    _recut(nw, walk, arr, trades)
    again = nw.run()
    assert again["status"] == "ok" and again["appended"] == [] and again["refused"] == []
    # the next day: one more trade past tonight's data is learned on the new cut
    nxt = pd.Timestamp(nw.full["time"].max(), unit="s", tz="UTC").tz_convert("US/Eastern")
    day = pd.Timestamp("2024-02-07", tz="US/Eastern")
    assert nxt < day
    bars = []
    for k in range(78):
        t = int((day + pd.Timedelta(hours=9, minutes=30 + 5 * k)).timestamp())
        bars.append((t, 15000.0 + k, 15001.0 + k, 14999.0 + k, 15000.5 + k, 100))
    extra = pd.DataFrame(bars, columns=["time", "open", "high", "low", "close", "volume"])
    nw.yahoo = pd.concat([nw.yahoo, extra], ignore_index=True)
    full = len(nw.full) + 78                      # the master + the live days + the new day
    nw.full = pd.concat([nw.full, extra], ignore_index=True)
    e, x = full - 60, full - 40
    nw.drop_rule = True                           # only this one trade on the new day
    nw.extra = [(e, x, 9.0, 1.0)]
    res = nw.run()
    assert [a["entry_bar"] for a in res["appended"]] == [e]
    assert res["appended"][0]["cut_at"] == cs.keel_live_meta(walk_after := nw.w.load("live_cut_path"))["cut"]["cut_at"]
    assert nw.w.load("live_path")["n"] == walk_after["n"] + 1
    assert KI.verify_live_state(nw.w.home, LEG, log=QUIET)["ok"] is True


def test_the_report_names_a_p_beyond_tolerance_a_missed_and_an_extra_trade(nw):
    arr = nw.full_arrays()
    idx = pd.DatetimeIndex(arr["index"])
    d = nw.w.live_days[0]
    a, b, c = nw.bar(d, 5), nw.bar(d, 30), nw.bar(d, 50)
    rows = [{"feed": "nq_yahoo", "trade_id": "A", "entry_bar_time": idx[a].isoformat(), "side": "long",
             "exit_bar_time": idx[a + 4].isoformat(), "P": 10.0},
            {"feed": "nq_yahoo", "trade_id": "B", "entry_bar_time": idx[b].isoformat(), "side": "short",
             "exit_bar_time": idx[b + 4].isoformat(), "P": 10.0},
            {"feed": "nq_yahoo", "trade_id": "X", "entry_bar_time": idx[b + 10].isoformat(),
             "side": "long", "exit_bar_time": idx[b + 12].isoformat(), "P": 1.0}]
    trades = [(a, a + 4, 10.0 + 8.9, 1.0, 0.0),       # within 2.0 x 4.5 = 9.0 -> matched
              (b, b + 4, 10.0 + 9.1, -1.0, 0.0),      # beyond -> differ
              (c, c + 3, 3.0, 1.0, 0.0)]              # never appended -> missed
    cut = {"data_through": str(nw.w.nightly_day), "live_from": str(d)}
    matched, differ, missed, extra = L._recut_compare(rows, arr, trades, [2.0, 2.0, 1.0], cut)
    assert [m["trade_id"] for m in matched] == ["A"]
    assert [x["trade_id"] for x in differ] == ["B"] and differ[0]["tol"] == 9.0
    assert [m["entry_bar_time"] for m in missed] == [idx[c].isoformat()]
    assert [x["trade_id"] for x in extra] == ["X"]


def test_behind_counts_the_exits_an_entry_was_scored_without(nw):
    arr = nw.full_arrays()
    idx = pd.DatetimeIndex(arr["index"])
    d = nw.w.live_days[0]
    trades = [(nw.bar(d, 2), nw.bar(d, 6), 1.0, 1.0, 0.0), (nw.bar(d, 8), nw.bar(d, 12), 1.0, 1.0, 0.0)]
    n0 = 100
    xrows = {"Q1": {"entry_bar_time": idx[nw.bar(d, 14)].isoformat(), "state_n": n0, "state_source": "live"},
             "Q0": {"entry_bar_time": idx[nw.bar(d, 7)].isoformat(), "state_n": n0, "state_source": "live"},
             "OLD": {"entry_bar_time": idx[nw.bar(nw.w.nightly_day, 7)].isoformat(), "state_n": 1}}
    prefix = [(i, i + 1, 0.0, 1.0, 0.0) for i in range(n0)]          # n0 trades long before
    out = L._recut_behind(xrows, arr, prefix + trades, {"data_through": str(nw.w.nightly_day)})
    by = {r["trade_id"]: r for r in out}
    assert set(by) == {"Q0", "Q1"}, "entries on / before the cut's data are not counted"
    assert by["Q0"]["walk_n"] == n0 + 1 and by["Q0"]["behind"] == 1
    assert by["Q1"]["walk_n"] == n0 + 2 and by["Q1"]["behind"] == 2


def test_a_nightly_older_than_the_live_cut_is_refused_and_the_live_state_kept(nw):
    nw.run()
    before = nw.w.load("live_path")
    walk, arr, trades = _tonight(nw)
    nw.w.install_nightly(walk, through=nw.w.days[-5])
    rep = _recut(nw, walk, arr, trades)
    assert rep["recut"] is False and "before the live cut" in rep["reason"]
    _same(nw.w.load("live_path"), before)
    assert KI.read_appends(nw.w.files["appends_path"]) != []


def test_old_cut_rows_left_by_a_crash_are_never_applied_to_the_new_cut(nw):
    nw.run()
    old_rows = KI.read_appends(nw.w.files["appends_path"])
    walk, arr, trades = _tonight(nw)
    _recut(nw, walk, arr, trades)
    with open(nw.w.files["appends_path"], "w", encoding="utf-8") as f:    # the crash: log not emptied
        for r in old_rows:
            f.write(json.dumps(r) + "\n")
    res = nw.run()
    assert res["status"] == "ok" and res["appended"] == [] and res["refused"] == []
    assert nw.w.load("live_path")["n"] == walk["n"]
    assert KI.verify_live_state(nw.w.home, LEG, log=QUIET)["ok"] is True


def test_build_recuts_under_the_nq_feed(nw):
    nw.run()
    state, summary = L.build(nw.w.nq_master, nw.w.files["dir"], leg=LEG, log=QUIET)
    rep = json.load(open(os.path.join(nw.w.files["dir"], L.RECUT_REPORT_FILE), encoding="utf-8"))
    assert rep["recut"] is True
    _same(nw.w.load("live_path"), state)
    assert KI.read_appends(nw.w.files["appends_path"]) == []


def test_build_leaves_the_live_state_alone_under_the_qqq_feed(nw, monkeypatch):
    nw.run()
    before = nw.w.load("live_path")
    monkeypatch.setattr(cs, "KEEL_LIVE_FEED", cs.KEEL_LIVE_FEED_QQQ)
    L.build(nw.w.nq_master, nw.w.files["dir"], leg=LEG, log=QUIET)
    _same(nw.w.load("live_path"), before)
    assert not os.path.exists(os.path.join(nw.w.files["dir"], L.RECUT_REPORT_FILE))
