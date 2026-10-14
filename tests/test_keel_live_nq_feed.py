"""THE NQ FEED (owner call 10-14 via MANAGER #149, supersedes #143): the LIVE KEEL ledger learns
NOISE #382's OWN NQ trades -- the backtest's trades -- from Yahoo's settled NQ=F bars on top of the
nightly's NQ master (tools/keel_intraday.process_nq_feed), not the book's QQQ trades.

COVERS: cut + the feed's appends == keel_build_state over the same trades (THE exact claim: the live
state IS the walk); a trade exiting on the last bar of a running session waits, one exiting on the
session's last bar (15:55, 12:55 on a half day) counts; idempotent runs; nothing before the cut;
an entry on / before the last appended exit bar refused + alerted, never retried, the next trade
still learned; a failed Yahoo pull = the master alone; bars at / before the master's last bar never
read; a contract-switch hold; the learned-N-min stamp; restated trades reported, the ledger left
alone; set_aside_inbox + main under the nq feed; the nightly feed alert; keel_ledger_behind blank.
No network: every Yahoo pull is a fake.
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
from _keel_live_world import LEG, QUIET, LiveWorld, nq_trades  # noqa: E402

STATE_KEYS = ("n", "n_fits", "fitted_on", "trust_now", "t_fast_now", "feature_names")
ARRAY_KEYS = ("E", "Xi", "X", "P", "z", "trust", "rho")
LATE = 4_000_000_000            # "now" long after every bar: everything settled


@pytest.fixture(scope="module")
def base(tmp_path_factory):
    return LiveWorld(tmp_path_factory.mktemp("keel_nq_feed") / "w")


class NQWorld:
    """The LiveWorld split for the NQ feed: the box master holds the sessions through the nightly's
    day; the live days' NQ bars come from a fake Yahoo pull; #382 is the world's synthetic NQ trade
    rule (a trade that would still be open at the array's end is closed there, as STEP E does)."""

    def __init__(self, w):
        self.w = w
        full = pd.read_csv(w.nq_master)
        et = pd.to_datetime(full["time"], unit="s", utc=True).dt.tz_convert("US/Eastern")
        self.full = full
        self.master = full[et.dt.date <= w.nightly_day].reset_index(drop=True)
        self.master.to_csv(w.nq_master, index=False)
        self.yahoo = full[et.dt.date > w.nightly_day][
            ["time", "open", "high", "low", "close", "volume"]].reset_index(drop=True)
        self.extra = []          # (entry bar, exit bar, P, side) added to the rule's trades
        self.drop_rule = False

    def trades(self, arr, leg):
        out = [] if self.drop_rule else [(e, x, p, 1.0, 0.0) for e, x, p in nq_trades(arr, 11)]
        last = len(arr["close"]) - 1
        for e, x, p, side in self.extra:
            if e <= last:
                out.append((e, min(x, last), p, side, 0.0))
        return out

    def fetch(self, upto=None):
        def f(now_s):
            y = self.yahoo
            return y if upto is None else y[y["time"] <= upto].reset_index(drop=True)
        return f

    def run(self, now_s=LATE, fetch_fn=None, upto=None, **kw):
        kw.setdefault("live_from", str(self.w.live_days[0]))
        return KI.process_nq_feed(self.w.home, self.w.nq_master, LEG, log=QUIET, now_s=now_s,
                                  fetch_fn=fetch_fn or self.fetch(upto), trades_fn=self.trades, **kw)

    def full_arrays(self):
        p = os.path.join(os.path.dirname(self.w.nq_master), "_full", KI.MASTER_NAME)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        self.full.to_csv(p, index=False)
        return L.load_nq_arrays(p, drop_incomplete=False, log=QUIET)[0]

    def bar(self, day, k):
        """The master + Yahoo index of bar k (0 = 09:30) of `day`."""
        arr = self.full_arrays()
        idx = pd.DatetimeIndex(arr["index"])
        return int(np.flatnonzero(np.array([d.date() == day for d in idx]))[k])

    def appends(self):
        return KI.read_appends(self.w.files["appends_path"])


@pytest.fixture
def nw(base, tmp_path):
    return NQWorld(base.clone(tmp_path / "w"))


def _same(a, b):
    for k in STATE_KEYS:
        assert a[k] == b[k], k
    for k in ARRAY_KEYS:
        assert np.array_equal(np.asarray(a[k]), np.asarray(b[k]), equal_nan=True), k
    for k in a["z_members"]:
        assert np.array_equal(a["z_members"][k], b["z_members"][k], equal_nan=True), k


# ── THE exact claim ─────────────────────────────────────────────────────────────────────────────
def test_the_cut_plus_the_feeds_appends_is_the_walk_over_the_same_trades(nw):
    res = nw.run()
    assert res["status"] == "ok" and not res["refused"]
    arr = nw.full_arrays()
    walk = K.keel_build_state(arr, [t[:3] for t in nw.trades(arr, None)], version=nw.w.version)
    live = nw.w.load("live_path")
    assert live["n"] == walk["n"] > nw.w.nightly["n"]
    assert len(res["appended"]) == walk["n"] - nw.w.nightly["n"]
    _same(live, walk)
    assert KI.verify_live_state(nw.w.home, LEG, log=QUIET)["ok"] is True


def test_each_row_carries_the_walks_inputs_and_the_learned_stamp(nw):
    nw.run(now_s=LATE)
    arr = nw.full_arrays()
    F, _ = K.keel_features(arr)
    idx = pd.DatetimeIndex(arr["index"])
    rows = nw.appends()
    assert rows
    for r in rows:
        assert r["feed"] == KI.FEED_NQ_YAHOO and r["trade_id"].startswith(f"{LEG}-NQ-")
        assert np.array_equal(np.array([np.nan if v is None else v for v in r["x_row"]]),
                              F[r["entry_bar"]], equal_nan=True)
        assert r["entry_bar_time"] == idx[r["entry_bar"]].isoformat()
        assert r["exit_bar_time"] == idx[r["exit_bar"]].isoformat()
        close = int(idx[r["exit_bar"]].timestamp()) + 300
        assert r["learned_min_after_exit"] == round((LATE - close) / 60.0, 1)
    ack = nw.w.ack()
    assert ack["feed"]["feed"] == "nq_yahoo"
    assert ack["feed"]["last_learned"]["trade_id"] == rows[-1]["trade_id"]
    assert ack["feed"]["bars_through"] == idx[-1].isoformat()
    assert ack["n"] == nw.w.load("live_path")["n"]


def test_a_second_run_on_the_same_bars_appends_nothing(nw):
    first = nw.run()
    n = nw.w.load("live_path")["n"]
    again = nw.run()
    assert first["appended"] and not again["appended"] and not again["refused"]
    assert nw.w.load("live_path")["n"] == n
    assert nw.w.ack()["last"]["status"] == "nothing new"


# ── the FINAL rule (STEP E closes an open trade at the array's last bar) ────────────────────────
def test_a_trade_exiting_on_the_last_bar_of_a_running_session_waits_then_counts(nw):
    d = nw.w.live_days[0]
    e, x = nw.bar(d, 10), nw.bar(d, 20)
    nw.drop_rule = True
    nw.extra = [(e, x, 7.5, 1.0)]
    upto = int(nw.full_arrays()["index"][x].timestamp())       # the pull ends on the exit bar
    r1 = nw.run(upto=upto)
    assert r1["appended"] == []
    upto2 = int(nw.full_arrays()["index"][x + 1].timestamp())   # one more bar: the exit is final
    r2 = nw.run(upto=upto2)
    assert [a["exit_bar"] for a in r2["appended"]] == [x]
    assert r2["appended"][0]["P"] == 7.5


def test_a_trade_exiting_on_the_sessions_last_bar_counts_at_once(nw):
    d = nw.w.live_days[0]
    e, x = nw.bar(d, 60), nw.bar(d, 77)                         # 77 = 15:55
    nw.drop_rule = True
    nw.extra = [(e, x, -3.25, -1.0)]
    upto = int(nw.full_arrays()["index"][x].timestamp())
    res = nw.run(upto=upto)
    assert [(a["exit_bar"], a["side"]) for a in res["appended"]] == [(x, "short")]


def test_the_session_end_bar_on_a_full_and_a_half_day():
    et = "US/Eastern"
    assert KI._ends_session(pd.Timestamp("2024-02-02 15:55", tz=et)) is True
    assert KI._ends_session(pd.Timestamp("2024-02-02 15:50", tz=et)) is False
    assert KI._ends_session(pd.Timestamp("2024-11-29 12:55", tz=et)) is True    # half day
    assert KI._ends_session(pd.Timestamp("2024-11-29 15:55", tz=et)) is False
    assert KI._ends_session(pd.Timestamp("2024-02-03 15:55", tz=et)) is False   # Saturday


# ── the cut, the order rule ─────────────────────────────────────────────────────────────────────
def test_nothing_before_live_from_or_on_the_cuts_nq_data_is_learned(nw):
    nw.w.install_nightly(nw.w.nightly, through=nw.w.live_days[0])    # the cut needs the eve's nightly
    res = nw.run(live_from=str(nw.w.live_days[1]))
    days = {pd.Timestamp(a["entry_bar_time"]).date() for a in res["appended"]}
    assert days == {nw.w.live_days[1]}


def test_an_entry_on_the_last_appended_exit_bar_is_refused_alerted_and_never_retried(nw):
    d = nw.w.live_days[0]
    a, b, c = nw.bar(d, 5), nw.bar(d, 12), nw.bar(d, 30)
    nw.drop_rule = True
    nw.extra = [(a, b, 4.0, 1.0), (b, nw.bar(d, 20), -2.0, -1.0), (c, nw.bar(d, 40), 1.5, 1.0)]
    res = nw.run()
    assert [t["entry_bar"] for t in res["appended"]] == [a, c]
    (ref,) = res["refused"]
    assert ref["alert"] is True and "on or before the last appended exit bar" in ref["reason"]
    ack = nw.w.ack()
    assert ref["trade_id"] in ack["rejected"]
    assert ack["alerts"][-1]["kind"] == "order"
    again = nw.run()
    assert not again["refused"] and not again["appended"], "a refused trade is not retried"


def test_no_nightly_to_cut_from_learns_nothing(nw):
    os.remove(nw.w.files["state_path"])
    res = nw.run()
    assert res["status"].startswith("refused") and not os.path.exists(nw.w.files["live_path"])


# ── the bars ────────────────────────────────────────────────────────────────────────────────────
def test_a_failed_yahoo_pull_uses_the_master_alone(nw):
    def boom(now_s):
        raise RuntimeError("no network")
    res = nw.run(fetch_fn=boom)
    assert res["status"] == "ok" and res["appended"] == []
    fb = nw.w.ack()["feed"]
    assert fb["yahoo"].startswith("failed: RuntimeError") and fb["yahoo_bars"] == 0
    assert fb["bars_through"] == fb["master_through"]


def test_bars_at_or_before_the_masters_last_bar_are_never_read():
    fresh = pd.DataFrame({"time": [100, 200, 300, 300, 400], "open": [1, 2, 3, 3.5, 4],
                          "high": 9, "low": 0, "close": 1, "volume": 1})
    bars, hit = KI.bars_after_master(200, fresh)
    assert hit is None
    assert list(bars["time"]) == [300, 400] and list(bars["open"]) == [3.5, 4]


def test_a_contract_switch_holds_the_bars_from_the_suspect_bar_on(nw, monkeypatch):
    from augur_engine import roll_guard
    cut_at = int(nw.yahoo["time"].iloc[40])

    def split(df, after_time, **kw):
        hit = {"time": cut_at, "et_date": "2024-02-01", "open": 1.0, "close": 2.0, "body": 1.0,
               "carry_prior": 100.0, "expiry": "2024-03-15"}
        return df[df["time"] < cut_at].reset_index(drop=True), hit
    monkeypatch.setattr(roll_guard, "split_tv_frame", split)
    nw.run()
    fb = nw.w.ack()["feed"]
    assert fb["roll_hold"]["et_date"] == "2024-02-01" and fb["yahoo_bars"] == 40


def test_a_restated_trade_is_reported_and_the_ledger_left_alone(nw):
    d = nw.w.live_days[0]
    e, x = nw.bar(d, 5), nw.bar(d, 12)
    nw.drop_rule = True
    nw.extra = [(e, x, 4.0, 1.0)]
    nw.run()
    n = nw.w.load("live_path")["n"]
    nw.extra = [(e, x, 5.5, 1.0)]          # a later pull gives the same trade another P
    res = nw.run()
    assert not res["appended"] and nw.w.load("live_path")["n"] == n
    (r,) = nw.w.ack()["feed"]["restated"]
    assert r["was_P"] == 4.0 and r["now_P"] == 5.5


# ── main, the inbox, the scorer's health mark ───────────────────────────────────────────────────
def test_main_under_the_nq_feed_sets_the_executor_files_aside_and_runs_the_feed(nw, monkeypatch):
    assert cs.KEEL_LIVE_FEED == cs.KEEL_LIVE_FEED_NQ == KI.FEED_NQ_YAHOO
    t = nw.w.live_trades[0]
    nw.w.drop(nw.w.inbox_trade(t))
    monkeypatch.setattr(KI, "fetch_yahoo_nq", lambda now_s=None: nw.yahoo)
    monkeypatch.setattr(KI, "LIVE_FROM_DAY", str(nw.w.live_days[0]))
    monkeypatch.setattr(L, "run_nq_backtest", lambda a, leg=None, log=None: (nw.trades(a, leg), {}))
    assert KI.main(["--home", nw.w.home, "--nq-file", nw.w.nq_master]) == 0
    assert nw.w.inbox() == []
    assert os.listdir(nw.w.paths["done"]) == [f"{t['trade_id']}.json"]
    rows = nw.appends()
    assert rows and all(r["feed"] == "nq_yahoo" for r in rows)


def test_the_ledger_behind_mark_is_blank_under_the_nq_feed(nw, monkeypatch):
    meta = {"cut": {"data_through": "2024-01-31", "live_from": "2024-02-01"}, "appended": []}
    assert cs.keel_ledger_behind(nw.w.keel_cfg(), LEG, meta) is None
    monkeypatch.setattr(cs, "KEEL_LIVE_FEED", cs.KEEL_LIVE_FEED_QQQ)
    assert cs.keel_ledger_behind(nw.w.keel_cfg(), LEG, meta) is None   # no executor ledger here


# ── the nightly alert ───────────────────────────────────────────────────────────────────────────
def test_the_feed_check_alerts_when_its_bars_end_before_the_nightlys_data():
    ack = {"feed": {"feed": "nq_yahoo", "bars_through": "2026-10-13T15:55:00-04:00",
                    "yahoo": "failed: X", "restated": [{}]}}
    bad = L.feed_check(ack, "2026-10-14")
    assert bad["ok"] is False and "BEHIND" in bad["details"] and bad["restated"] == 1
    assert L.feed_check(ack, "2026-10-13")["ok"] is True
    assert L.feed_check(ack, None)["ok"] is None
    assert L.feed_check({"feed": {"feed": "qqq_inbox"}}, "2026-10-14")["ok"] is None
    assert L.feed_check({}, "2026-10-14")["ok"] is None


def test_the_nightly_live_check_carries_the_feed_check(nw):
    nw.run()
    out_dir = nw.w.files["dir"]
    rep = L.live_check(nw.w.nightly, out_dir, LEG, nw.w.version, log=QUIET,
                       data_through=str(nw.w.live_days[-1] + pd.Timedelta(days=7)))
    assert rep["feed"]["ok"] is False and "feed" in rep["reasons"]
    rep = L.live_check(nw.w.nightly, out_dir, LEG, nw.w.version, log=QUIET,
                       data_through=str(nw.w.live_days[-1]))
    assert rep["feed"]["ok"] is True and "feed" not in rep["reasons"]


# ── the phone line (tools/webull_freshness.py keel_live:<leg>) ──────────────────────────────────
def test_the_monitor_names_a_feed_behind_and_an_order_refusal_in_plain_words():
    from tools import webull_freshness as WF
    feed = {"ok": False, "reasons": ["feed"], "leg": LEG,
            "feed": {"bars_through": "2026-10-13T15:55:00-04:00", "nightly_through": "2026-10-14",
                     "details": "feed bars through 2026-10-13, nightly through 2026-10-14"}}
    line = WF._keel_live_problem(feed)
    assert "stopped learning" in line and "2026-10-13" in line and "2026-10-14" in line
    (v,) = WF.check_keel_live({"keel_live_check": feed})
    assert "nightly through 2026-10-14" in str(v)
    order = {"ok": False, "reasons": ["chain"],
             "chain": {"alerts": [{"kind": "order", "trade_id": "x"}]}}
    assert "in order" in WF._keel_live_problem(order)
    chain = {"ok": False, "reasons": ["chain"], "chain": {"alerts": [{"kind": "chain"}]}}
    assert "missing or doubled" in WF._keel_live_problem(chain)
