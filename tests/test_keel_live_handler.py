"""LIVE KEEL handler (tools/keel_intraday.py, owner call 10-12 via MANAGER #143): each closed live
NOISE_382 trade in cloud_signal/keel_inbox is appended to the leg's LIVE KEEL state -- made once
at the CUT from the nightly -- with ml_keel.keel_append_trade, its P from the ONE conversion
function qqq_trade_to_walk_pnl.

COVERS: the conversion rule; the NQ/QQQ price ratio (prior session, fallback, tail vs whole-file
read); exit order and the exact keel_append_trade chain (state, _prev, record, cut + cut file, ack);
a same-second reversal accepted; idempotency; a missing entry record rejected while the next trade
goes; the refusals (overlap, feature names, numbers, bad files); no nightly to cut from; an
unreadable live state never re-cut; atomic writes; the inbox always emptied.
Custom ML 10-12: THE CUT (no backfill: entries before live_from or on / before the cut's NQ data
refused, nothing made; a nightly older than the session before live_from never cut; --cut by hand,
never twice); THE APPEND LOG (every row with P's inputs, written before the state; live state == cut
+ replay, verify / --verify; a run killed between the log and the state completed by the next run's
catch-up; a log that lacks a trade the state holds stops the ledger); THE CHAIN (prev_trade_id: a
missed or doubled close refused with n_before and an ack alert, the chain then goes on).
"""
import hashlib
import json
import math
import os
import sys

import numpy as np
import pytest

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(THIS_DIR)
for _p in (ROOT, THIS_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from api import cloud_signal as cs  # noqa: E402
from augur_engine import ml_keel as K  # noqa: E402
import tools.keel_intraday as KI  # noqa: E402
from _keel_live_world import BUILT_AT, LEG, QUIET, LiveWorld  # noqa: E402

STATE_KEYS = ("n", "n_fits", "fitted_on", "trust_now", "t_fast_now", "version", "feature_names")
ARRAY_KEYS = ("E", "Xi", "X", "P", "z", "trust", "rho")


@pytest.fixture(scope="module")
def base(tmp_path_factory):
    return LiveWorld(tmp_path_factory.mktemp("keel_live_handler") / "w")


@pytest.fixture
def w(base, tmp_path):
    return base.clone(tmp_path / "w")


def _prep(w, ts, keel_size=1.0, names=None, skip_xrow=()):
    for i, t in enumerate(ts):
        if t["k"] not in skip_xrow:
            w.write_xrow(w.xrow_record(t, keel_size))
        w.drop(w.inbox_trade(t), name=names[i] if names else None)


def _manual(w, ts, keel_size=1.0, start=None):
    """The chain this test computes itself: the cut copy of the nightly, then keel_append_trade per
    trade with P = (pnl / shares) x (engine / keel) x ratio. Returns every state, the cut first."""
    st = dict(start if start is not None else w.nightly)
    out = [st]
    for t in ts:
        tr = w.inbox_trade(t)
        engine = t["plugin"] * keel_size
        P = (tr["pnl_usd"] / tr["shares"]) * (engine / keel_size) * w.ratio_for(t["entry_time"].date())
        st = K.keel_append_trade(st, w.x_row(t["e"]), P, entry_bar=KI.bar_number(t["entry_time"]),
                                 exit_bar=KI.bar_number(t["exit_ts"]))
        out.append(st)
    return out


def _same_state(a, b):
    for k in STATE_KEYS:
        assert a[k] == b[k] or (isinstance(a[k], float) and math.isnan(a[k]) and math.isnan(b[k])), k
    for k in ARRAY_KEYS:
        assert np.array_equal(np.asarray(a[k]), np.asarray(b[k]), equal_nan=True), k
    for m in a["z_members"]:
        assert np.array_equal(a["z_members"][m], b["z_members"][m], equal_nan=True), m


def _sha(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


# ── the conversion function ─────────────────────────────────────────────────────────────────────
def test_the_conversion_is_per_share_pnl_times_plugin_size_times_the_ratio():
    # P = (pnl / shares) x (engine / keel) x ratio: 30 $ on 20 shares, engine 3.0 at keel 1.5
    # (plugin 2.0), ratio 36.0 -> 1.5 x 2.0 x 36 = 108 points
    assert KI.qqq_trade_to_walk_pnl(30.0, 20, 3.0, 1.5, 36.0) == pytest.approx(108.0, rel=1e-15)
    assert KI.qqq_trade_to_walk_pnl(-12.5, 10, 1.0, 1.0, 35.0) == pytest.approx(-43.75, rel=1e-15)
    assert KI.qqq_trade_to_walk_pnl("7", "7", "1.5", "0.75", "2") == pytest.approx(4.0)
    for bad in [dict(shares=0), dict(shares=-3), dict(engine_size=0), dict(keel_size=0),
                dict(ratio=float("nan")), dict(ratio=0), dict(pnl_usd=float("inf")),
                dict(pnl_usd=None), dict(shares="x")]:
        args = dict(pnl_usd=10.0, shares=10, engine_size=2.0, keel_size=1.0, ratio=35.0)
        args.update(bad)
        with pytest.raises(ValueError):
            KI.qqq_trade_to_walk_pnl(**args)


# ── the price ratio ─────────────────────────────────────────────────────────────────────────────
def test_the_ratio_is_nq_close_over_qqq_close_at_the_prior_sessions_last_bar(w, monkeypatch):
    day = w.live_days[1]
    ratio, info = KI.price_ratio(w.nq_master, w.qqq_csv, day)
    assert ratio == w.ratio_for(day)
    assert info["session"] == w.live_days[0].isoformat() and info["fallback"] is False
    # the tail read and the whole-file read agree (a tail too short forces the whole file)
    monkeypatch.setattr(KI, "TAIL_BYTES", 300)
    assert KI.price_ratio(w.nq_master, w.qqq_csv, day)[0] == ratio


def test_the_ratio_falls_back_to_an_earlier_session_then_refuses(w):
    import pandas as pd
    day = w.live_days[1]
    prior, before = w.live_days[0], w.nightly_day
    q = pd.read_csv(w.qqq_csv)
    dates = pd.to_datetime(q["time"], unit="s", utc=True).dt.tz_convert("US/Eastern").dt.date
    q[dates != prior].to_csv(w.qqq_csv, index=False)
    ratio, info = KI.price_ratio(w.nq_master, w.qqq_csv, day)
    assert info["session"] == before.isoformat() and info["fallback"] is True
    assert ratio == w.ratio_for(prior)          # the session before `prior`
    q.iloc[:0].to_csv(w.qqq_csv, index=False)
    with pytest.raises(ValueError):
        KI.price_ratio(w.nq_master, w.qqq_csv, day)


# ── the append ──────────────────────────────────────────────────────────────────────────────────
def test_trades_go_in_exit_order_and_the_live_state_is_the_keel_append_trade_chain(w):
    ts = w.live_trades[:4]
    assert ts[1]["reversal"] and ts[1]["entry_ts"] == ts[0]["exit_ts"], \
        "fixture: a same-second reversal (one executor tick) -- never an overlap"
    # file names sort in REVERSE exit order: the handler must not go by name
    _prep(w, ts, names=[f"{90 - t['k']:02d}_{t['trade_id']}.json" for t in ts])
    res = w.run()
    assert [r["status"] for r in res] == ["appended"] * 4
    assert [r["trade_id"] for r in res] == [t["trade_id"] for t in ts]
    assert w.inbox() == [] and len(os.listdir(w.paths["done"])) == 4
    chain = _manual(w, ts)
    live, prev = w.load("live_path"), w.load("live_prev_path")
    _same_state(live, chain[-1])
    _same_state(prev, chain[-2])
    assert live["n"] == w.nightly["n"] + 4
    meta = cs.keel_live_meta(live)
    assert [a["trade_id"] for a in meta["appended"]] == [t["trade_id"] for t in ts]
    assert meta["cut"]["built_at"] == BUILT_AT and meta["cut"]["n"] == w.nightly["n"]
    assert meta["cut"]["data_through"] == str(w.nightly_day)
    assert meta["cut"]["from_exit_ts"] == ts[0]["exit_ts"]
    assert meta["last_trade_id"] == ts[-1]["trade_id"] and meta["last_exit_ts"] == ts[-1]["exit_ts"]
    assert meta["last_exit_bar_ts"] == w.q_idx[ts[-1]["x"]].isoformat()
    a = meta["appended"][2]
    assert a["plugin_size"] == ts[2]["plugin"] and a["ratio"] == w.ratio_for(ts[2]["entry_time"].date())
    ack = w.ack()
    assert ack["n"] == live["n"] and ack["last_trade_id"] == ts[-1]["trade_id"]
    assert ack["cut"] == meta["cut"] and ack["rejected"] == {}
    # the live state scores the next entry exactly as the chain's own end state does
    nxt = w.live_trades[4]
    got = K.keel_score_from_state(live, w.q_arrays, nxt["e"], x_row=w.x_row(nxt["e"]))[0]
    assert got == K.keel_score_from_state(chain[-1], w.q_arrays, nxt["e"], x_row=w.x_row(nxt["e"]))[0]
    assert not [n for n in os.listdir(w.files["dir"]) if n.endswith(".tmp")]
    # the CUT file is the nightly copy the chain started from; the APPEND LOG holds every row with
    # P's three inputs, and replaying it on the cut gives the live state
    cut = w.load("live_cut_path")
    _same_state(cut, w.nightly)
    assert cs.keel_live_meta(cut)["appended"] == [] and cs.keel_live_meta(cut)["cut"] == meta["cut"]
    rows = KI.read_appends(w.files["appends_path"])
    assert [r["trade_id"] for r in rows] == [t["trade_id"] for t in ts]
    assert [r["n_before"] for r in rows] == [w.nightly["n"] + i for i in range(4)]
    assert [r["n_after"] for r in rows] == [w.nightly["n"] + i + 1 for i in range(4)]
    for r, t, st in zip(rows, ts, chain[1:]):
        tr = w.inbox_trade(t)
        assert r["pnl_per_share"] == tr["pnl_usd"] / tr["shares"]
        assert r["plugin_size"] == t["plugin"] and r["engine_size"] == t["plugin"] * 1.0
        assert r["ratio"] == w.ratio_for(t["entry_time"].date())
        assert r["nq_close"] / r["qqq_close"] == r["ratio"]
        assert r["ratio_session"] == KI._sessions_before(t["entry_time"].date(), 1)[0].isoformat()
        assert r["P"] == st["P"][-1] == r["pnl_per_share"] * r["plugin_size"] * r["ratio"]
        assert r["x_row"] == [float(v) for v in w.x_row(t["e"])[0]]
        assert (r["entry_bar"], r["exit_bar"]) == (KI.bar_number(t["entry_time"]),
                                                   KI.bar_number(t["exit_ts"]))
        assert r["entry_ts"] == t["entry_ts"] and r["exit_ts"] == t["exit_ts"]
    _same_state(KI.rebuild_live_state(w.home, LEG), live)
    v = KI.verify_live_state(w.home, LEG, log=lambda *a: None)
    assert v["ok"] is True and v["mismatches"] == [] and v["n_live"] == v["n_rebuilt"] == live["n"]
    assert set(v["fields"]) == set(KI.EXACT_KEYS)


def test_a_trade_already_appended_is_a_no_op(w):
    ts = w.live_trades[:2]
    _prep(w, ts)
    w.run()
    before = {k: _sha(w.files[k]) for k in ("live_path", "live_prev_path")}
    mt = os.path.getmtime(w.files["live_path"])
    w.drop(w.inbox_trade(ts[1]))
    (r,) = w.run()
    assert r["status"] == "noop" and r["reason"] == "already appended"
    assert {k: _sha(w.files[k]) for k in before} == before
    assert os.path.getmtime(w.files["live_path"]) == mt
    assert w.inbox() == [] and w.ack()["n"] == w.nightly["n"] + 2


def test_a_missing_entry_record_is_rejected_and_the_next_trade_still_goes(w):
    ts = [w.live_trades[k] for k in (2, 3, 4)]
    _prep(w, ts, skip_xrow=(3,))
    res = w.run()
    assert [r["status"] for r in res] == ["appended", "rejected", "appended"]
    assert "no entry record" in res[1]["reason"]
    tid = ts[1]["trade_id"]
    assert sorted(os.listdir(w.paths["rejected"])) == [f"{tid}.json", f"{tid}.json.reason.json"]
    assert w.ack()["rejected"] == {tid: res[1]["reason"]}
    _same_state(w.load("live_path"), _manual(w, [ts[0], ts[2]])[-1])
    assert w.inbox() == []
    # the record arrives, the trade is re-sent: it is refused now as an overlap (a later trade is
    # already in the ledger) -- never appended out of order
    w.write_xrow(w.xrow_record(ts[1], 1.0))
    w.drop(w.inbox_trade(ts[1]))
    (r,) = w.run()
    assert r["status"] == "rejected" and "before the last appended exit" in r["reason"]


def test_the_refusals_reject_the_trade_and_leave_the_ledger_alone(w):
    t0, t1, t2, t3 = w.live_trades[2:6]
    _prep(w, [t1])
    assert [r["status"] for r in w.run()] == ["appended"]
    n1 = w.load("live_path")["n"]
    # out of order: t0 entered before t1 (already in the ledger) exited
    w.write_xrow(w.xrow_record(t0, 1.0))
    w.drop(w.inbox_trade(t0))
    # other feature columns in its entry record
    rec = w.xrow_record(t2, 1.0)
    rec["feature_names"] = list(reversed(rec["feature_names"]))
    w.write_xrow(rec)
    w.drop(w.inbox_trade(t2))
    res = {r["trade_id"]: r for r in w.run()}
    assert "before the last appended exit" in res[t0["trade_id"]]["reason"]
    assert "feature names differ" in res[t2["trade_id"]]["reason"]
    # unusable numbers
    w.write_xrow(w.xrow_record(t3, 1.0))
    tr = w.inbox_trade(t3)
    tr["pnl_usd"] = None              # an unmarked exit (api/qqq_exec sends it as null)
    w.drop(tr)
    (r,) = w.run()
    assert r["status"] == "rejected" and "pnl_usd" in r["reason"]
    w.drop(w.inbox_trade(t3, shares=0))
    (r,) = w.run()
    assert r["status"] == "rejected" and "shares" in r["reason"]
    # bad files: not JSON, another leg, a non-.json name
    with open(os.path.join(w.paths["inbox"], "torn.json"), "w") as f:
        f.write("{not json")
    w.drop(w.inbox_trade(t3, leg="ORB_R6"), name="orb.json")
    with open(os.path.join(w.paths["inbox"], "notes.txt"), "w") as f:
        f.write("x")
    res = w.run()
    assert sorted(r["file"] for r in res) == ["notes.txt", "orb.json", "torn.json"]
    assert all(r["status"] == "rejected" and r["reason"].startswith("bad trade file") for r in res)
    assert w.inbox() == []
    assert w.load("live_path")["n"] == n1
    assert set(w.ack()["rejected"]) == {t0["trade_id"], t2["trade_id"], t3["trade_id"]}


def test_no_nightly_state_to_cut_from_rejects_every_trade(w):
    os.remove(w.files["state_path"])
    _prep(w, w.live_trades[:2])
    res = w.run()
    assert [r["status"] for r in res] == ["rejected", "rejected"]
    assert all("no readable nightly" in r["reason"] for r in res)
    assert not os.path.exists(w.files["live_path"]) and w.inbox() == []


def test_an_unreadable_live_state_is_never_cut_again(w):
    with open(w.files["live_path"], "wb") as f:
        f.write(b"not a joblib file")
    sha = _sha(w.files["live_path"])
    _prep(w, w.live_trades[:1])
    (r,) = w.run()
    assert r["status"] == "rejected" and "cannot be read" in r["reason"]
    assert _sha(w.files["live_path"]) == sha and w.inbox() == []


def test_the_live_state_is_written_atomically(w, monkeypatch):
    import joblib
    _prep(w, w.live_trades[:1])
    w.run()
    sha = _sha(w.files["live_path"])
    real = joblib.dump

    def torn(obj, path, *a, **k):
        if str(path).startswith(w.files["live_path"]):
            with open(path, "wb") as f:
                f.write(b"half a state")
            raise OSError("disk full")
        return real(obj, path, *a, **k)
    monkeypatch.setattr(joblib, "dump", torn)
    _prep(w, [w.live_trades[2]])
    (r,) = w.run()
    assert r["status"] == "rejected" and "disk full" in r["reason"]
    assert "the append log holds the trade" in r["reason"]
    assert _sha(w.files["live_path"]) == sha, "the live state is the old one, whole"
    assert not [n for n in os.listdir(w.files["dir"]) if n.endswith(".tmp")]
    assert w.inbox() == []
    # the log row (the decision) was written first: the NEXT run completes it (catch-up) before
    # anything else, and the re-sent trade is then a no-op -- no second log row
    monkeypatch.setattr(joblib, "dump", real)
    w.drop(w.inbox_trade(w.live_trades[2]))
    (r,) = w.run()
    assert r["status"] == "noop" and w.load("live_path")["n"] == w.nightly["n"] + 2
    assert w.live_trades[2]["trade_id"] not in w.ack()["rejected"]
    assert len(KI.read_appends(w.files["appends_path"])) == 2
    _same_state(w.load("live_path"), _manual(w, [w.live_trades[0], w.live_trades[2]])[-1])
    assert KI.verify_live_state(w.home, LEG, log=lambda *a: None)["ok"] is True


def test_the_handler_main_reads_the_box_paths(w, monkeypatch):
    monkeypatch.setattr(KI, "LIVE_FROM_DAY", str(w.live_days[0]))
    _prep(w, w.live_trades[:1])
    assert KI.main(["--home", w.home, "--nq-file", w.nq_master, "--feed", KI.FEED_QQQ_INBOX]) == 0
    assert w.inbox() == [] and w.load("live_path")["n"] == w.nightly["n"] + 1
    with open(w.files["xrows_path"], encoding="utf-8") as f:
        assert len(f.read().splitlines()) == 1
    assert json.load(open(w.files["live_ack_path"], encoding="utf-8"))["appended"] == 1


# ── THE CUT (Custom ML 10-12: tonight's nightly, live trades from 10-13 on, no backfill) ─────────
def test_the_box_cut_is_the_owner_date():
    assert KI.LIVE_FROM_DAY == "2026-10-13"
    assert str(KI.cut_floor()) == "2026-10-12", "a cut needs the 10-12 nightly (or a later one)"


def test_a_trade_entered_before_the_cut_is_refused_and_nothing_is_made(w):
    t0, t1 = w.live_trades[:2]
    _prep(w, [t0])
    (r,) = w.run(live_from=str(w.live_days[1]))           # learning starts the day after t0's
    assert r["status"] == "rejected" and r["reason"].startswith("before the cut (no backfill)")
    assert not os.path.exists(w.files["live_path"]) and not os.path.exists(w.files["live_cut_path"])
    assert not os.path.exists(w.files["appends_path"])
    ack = w.ack()
    assert ack["n"] is None and ack["last_processed"]["trade_id"] == t0["trade_id"]
    assert ack["alerts"] == [], "a pre-cut trade is expected, never an alert"
    # the nightly already holds the entry's day (the handler ran late): refused, no cut either
    w.install_nightly(w.nightly, through=w.live_days[0])
    _prep(w, [t1])
    (r,) = w.run()
    assert r["status"] == "rejected" and "on or before the cut's NQ data" in r["reason"]
    assert not os.path.exists(w.files["live_path"])


def test_a_nightly_older_than_the_cut_night_is_never_cut(w):
    w.install_nightly(w.nightly, through=w.days[-4])      # the session before the cut night
    _prep(w, w.live_trades[:1])
    (r,) = w.run()
    assert r["status"] == "rejected" and "the cut needs one through" in r["reason"]
    assert not os.path.exists(w.files["live_path"]) and not os.path.exists(w.files["live_cut_path"])


def test_the_cut_by_hand_is_made_once(w, monkeypatch):
    monkeypatch.setattr(KI, "LIVE_FROM_DAY", str(w.live_days[0]))
    assert KI.main(["--home", w.home, "--cut"]) == 0
    live, cut = w.load("live_path"), w.load("live_cut_path")
    _same_state(live, w.nightly)
    _same_state(cut, w.nightly)
    c = cs.keel_live_meta(live)["cut"]
    assert c["from_exit_ts"] is None and c["data_through"] == str(w.nightly_day)
    assert c["live_from"] == str(w.live_days[0]) and w.ack()["n"] == w.nightly["n"]
    sha = (_sha(w.files["live_path"]), _sha(w.files["live_cut_path"]))
    assert KI.main(["--home", w.home, "--cut"]) == 1, "never re-cut"
    assert (_sha(w.files["live_path"]), _sha(w.files["live_cut_path"])) == sha
    _prep(w, w.live_trades[:2])
    assert [r["status"] for r in w.run()] == ["appended", "appended"]
    _same_state(w.load("live_path"), _manual(w, w.live_trades[:2])[-1])
    assert KI.main(["--home", w.home, "--verify"]) == 0


# ── THE APPEND LOG (Custom ML 10-12, MUST b) ───────────────────────────────────────────────────
def test_verify_catches_a_live_state_that_is_not_the_cut_plus_the_log(w, monkeypatch):
    import joblib
    monkeypatch.setattr(KI, "LIVE_FROM_DAY", str(w.live_days[0]))
    _prep(w, w.live_trades[:3])
    w.run()
    q = lambda: KI.verify_live_state(w.home, LEG, log=QUIET)  # noqa: E731
    assert q()["ok"] is True
    live = w.load("live_path")
    # within 1e-9 is equal; past it is not
    joblib.dump(dict(live, trust_now=float(live["trust_now"]) + 1e-10), w.files["live_path"])
    assert q()["ok"] is True
    joblib.dump(dict(live, trust_now=float(live["trust_now"]) + 1e-6), w.files["live_path"])
    assert q()["mismatches"] == ["trust_now"]
    z = np.array(live["z"], float)
    z[-1] += 1e-6
    joblib.dump(dict(live, z=z), w.files["live_path"])
    assert q()["mismatches"] == ["last_z"]
    joblib.dump(dict(live, n_fits=int(live["n_fits"]) + 1), w.files["live_path"])
    assert q()["mismatches"] == ["n_fits"]
    joblib.dump(live, w.files["live_path"])
    # a log row whose P was changed: the replay no longer gives the live state
    rows = KI.read_appends(w.files["appends_path"])
    rows[1]["P"] += 0.5
    with open(w.files["appends_path"], "w", encoding="utf-8") as f:
        f.write("".join(json.dumps(r) + "\n" for r in rows))
    assert q()["ok"] is False
    assert KI.main(["--home", w.home, "--verify"]) == 1
    os.remove(w.files["live_cut_path"])
    assert "no cut state" in q()["mismatches"][0]


def test_a_log_that_lacks_a_trade_the_state_holds_stops_the_ledger(w):
    _prep(w, w.live_trades[:2])
    w.run()
    rows = KI.read_appends(w.files["appends_path"])
    with open(w.files["appends_path"], "w", encoding="utf-8") as f:
        f.write(json.dumps(rows[0]) + "\n")               # the second row lost
    n = w.load("live_path")["n"]
    _prep(w, w.live_trades[2:4])
    res = w.run()
    assert [r["status"] for r in res] == ["rejected", "rejected"]
    assert all("the append log lacks 1 trade(s)" in r["reason"] and r["alert"] for r in res)
    assert w.load("live_path")["n"] == n and w.inbox() == []
    kinds = [(a["kind"], a["trade_id"]) for a in w.ack()["alerts"]]
    assert kinds == [("ledger", t["trade_id"]) for t in w.live_trades[2:4]]


# ── THE CHAIN (Custom ML 10-12, MUST d) ────────────────────────────────────────────────────────
def _chained(w, ts, prevs):
    for t, p in zip(ts, prevs):
        w.write_xrow(w.xrow_record(t, 1.0))
        w.drop(w.inbox_trade(t, prev_trade_id=p))


def test_a_chained_sequence_appends_and_the_ack_keeps_the_last_handled_trade(w):
    ts = w.live_trades[:4]
    _chained(w, ts, [None] + [t["trade_id"] for t in ts[:-1]])
    res = w.run()
    assert [r["status"] for r in res] == ["appended"] * 4
    assert [r["n_before"] for r in res] == [w.nightly["n"] + i for i in range(4)]
    assert w.ack()["last_processed"]["trade_id"] == ts[-1]["trade_id"] and w.ack()["alerts"] == []
    rows = KI.read_appends(w.files["appends_path"])
    assert [r["prev_trade_id"] for r in rows] == [None] + [t["trade_id"] for t in ts[:-1]]


def test_a_missed_close_is_refused_with_its_n_before_and_alerted_then_the_chain_goes_on(w):
    t0, t1, t2, t3 = w.live_trades[:4]
    _chained(w, [t0], [None])
    w.run()
    n = w.load("live_path")["n"]
    # t1's close never reached the inbox: t2 says t1 came before it
    _chained(w, [t2, t3], [t1["trade_id"], t2["trade_id"]])
    r2, r3 = w.run()
    assert r2["status"] == "rejected" and r2["alert"] is True and r2["n_before"] == n
    assert r2["reason"].startswith("missed or doubled close") and t1["trade_id"] in r2["reason"]
    assert f"n={n}" in r2["reason"]
    assert r3["status"] == "appended" and r3["n_before"] == n, "the chain goes on from t2"
    (a,) = w.ack()["alerts"]
    assert a["kind"] == "chain" and a["trade_id"] == t2["trade_id"] and a["at"]
    assert t2["trade_id"] in w.ack()["rejected"]


def test_a_doubled_close_is_refused(w):
    t0, t1, t2 = w.live_trades[:3]
    _chained(w, [t0, t1], [None, t0["trade_id"]])
    w.run()
    _chained(w, [t2], [t0["trade_id"]])                    # an executor state from before t1
    (r,) = w.run()
    assert r["status"] == "rejected" and r["reason"].startswith("missed or doubled close")
    assert w.load("live_path")["n"] == w.nightly["n"] + 2
    # the rule itself
    assert chain_ok(KI.chain_problem({"prev_trade_id": "A"}, "A", 5))
    assert not chain_ok(KI.chain_problem({"prev_trade_id": "A"}, None, 5))
    assert chain_ok(KI.chain_problem({"prev_trade_id": None}, "B", 5)), "a null prev: not checked"
    assert chain_ok(KI.chain_problem({}, "B", 5)), "no prev key (a hand-made file): not checked"


def chain_ok(why):
    return why is None


def test_a_trade_resent_after_a_refusal_is_not_chain_checked(w):
    t0, t1, t2 = w.live_trades[:3]
    _chained(w, [t0], [None])
    w.run()
    w.drop(w.inbox_trade(t1, prev_trade_id=t0["trade_id"]))   # no entry record yet: refused
    (r,) = w.run()
    assert r["status"] == "rejected" and "no entry record" in r["reason"]
    w.write_xrow(w.xrow_record(t1, 1.0))
    w.drop(w.inbox_trade(t1, prev_trade_id=t0["trade_id"]))   # re-sent by hand
    (r,) = w.run()
    assert r["status"] == "appended"
    _chained(w, [t2], [t1["trade_id"]])
    (r,) = w.run()
    assert r["status"] == "appended" and w.ack()["alerts"] == []
    # a re-send that is refused again does not move the chain either: the next close follows the
    # last trade really handled
    t3, t4, t5 = w.live_trades[3:6]
    w.drop(w.inbox_trade(t3, prev_trade_id=t2["trade_id"]))   # no entry record: refused
    _chained(w, [t4], [t3["trade_id"]])
    assert [r["status"] for r in w.run()] == ["rejected", "appended"]
    w.write_xrow(w.xrow_record(t3, 1.0))
    w.drop(w.inbox_trade(t3, prev_trade_id=t2["trade_id"]))   # re-sent: now an overlap
    _chained(w, [t5], [t4["trade_id"]])                        # the next close, the same run
    r3, r5 = w.run()
    assert r3["status"] == "rejected" and "before the last appended exit" in r3["reason"]
    assert r5["status"] == "appended" and w.ack()["alerts"] == []
    assert w.ack()["last_processed"]["trade_id"] == t5["trade_id"]
