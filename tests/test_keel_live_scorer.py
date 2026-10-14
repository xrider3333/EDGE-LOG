"""LIVE KEEL scorer and entry records (api/cloud_signal.py, owner call 10-12 via MANAGER #143).

COVERS: the scorer prefers the LIVE state when it loads and its feature names match, else the
nightly reference as before (other feature columns, unreadable, no live record); the date rule
gates the nightly only; the same-bar rule through _live_prev (and the live state when _prev does
not fit); keel_ledger_n / keel_ledger_behind (closed live trades since the cut, neither appended nor
rejected; the warning past KEEL_LEDGER_BEHIND_WARN); the step-time fallback read stays quiet while
the live state scores; the ENTRY RECORD -- _diff_leg puts the exact feature row on a live-learning
leg's ENTRY on the box and _note_keel_entries writes it once per trade_id (not on an offline tick,
a shadow leg or off the box; a fallback entry too); the signal row's ledger columns.
"""
import csv
import json
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
from _keel_live_world import LEG, TRUSTING, TRUSTING_CFG, LiveWorld  # noqa: E402
from test_cloud_signal_keel import _sizing_cfg  # noqa: E402


@pytest.fixture(scope="module")
def base(tmp_path_factory):
    with pytest.MonkeyPatch.context() as mp:
        mp.setitem(K.CFG, TRUSTING, TRUSTING_CFG)
        yield LiveWorld(tmp_path_factory.mktemp("keel_live_scorer") / "w", version=TRUSTING)


@pytest.fixture
def w(base, tmp_path, monkeypatch):
    monkeypatch.delenv("EDGELOG_QQQ_EXEC_DIR", raising=False)
    return base.clone(tmp_path / "w")


def _grow(w, ts):
    for t in ts:
        w.write_xrow(w.xrow_record(t, 1.0))
        w.drop(w.inbox_trade(t))
    res = w.run()
    assert all(r["status"] == "appended" for r in res), res
    cs._KEEL_STATE_CACHE.clear()
    return w.load("live_path")


def _score(w, t, cfg=None, logs=None):
    sc = {}
    size, diag = cs._keel_size_for_entry(cfg or w.keel_cfg(), w.q_arrays, t["e"], t["entry_time"],
                                         log=(logs.append if logs is not None else (lambda *a: None)),
                                         scratch=sc)
    return size, diag, sc


def _direct(state, w, t):
    return K.keel_score_from_state(state, w.q_arrays, t["e"], x_row=w.x_row(t["e"]),
                                   cross_series=True)[0]


# ── which state scores ──────────────────────────────────────────────────────────────────────────
def test_the_live_state_scores_when_it_fits(w):
    live = _grow(w, w.live_trades[:3])
    t = w.live_trades[3]
    size, diag, sc = _score(w, t)
    assert isinstance(diag, dict)
    assert size == _direct(live, w, t)
    assert size != _direct(w.nightly, w, t), "fixture: the live ledger must size differently"
    assert sc["state_source"] == "live" and sc["ledger_n"] == w.nightly["n"] + 3
    assert cs._keel_ledger_cols(sc) == {"keel_ledger_n": w.nightly["n"] + 3, "keel_ledger_behind": ""}


def test_before_the_cut_the_nightly_scores_as_before(w):
    t = w.live_trades[0]
    size, diag, sc = _score(w, t)
    assert size == _direct(w.nightly, w, t) and sc["state_source"] == "nightly"
    assert sc["ledger_n"] == w.nightly["n"] and sc["ledger_behind"] is None


@pytest.mark.parametrize("damage", ["names", "garbage", "no_meta", "version"])
def test_a_live_state_that_cannot_score_falls_back_to_the_nightly(w, damage):
    import joblib
    live = _grow(w, w.live_trades[:3])
    if damage == "garbage":
        with open(w.files["live_path"], "wb") as f:
            f.write(b"torn")
    elif damage == "names":
        joblib.dump(dict(live, feature_names=list(reversed(live["feature_names"]))), w.files["live_path"])
    elif damage == "no_meta":
        joblib.dump({k: v for k, v in live.items() if k != cs.KEEL_LIVE_META}, w.files["live_path"])
    else:
        joblib.dump(dict(live, version="v4"), w.files["live_path"])
    cs._KEEL_STATE_CACHE.clear()
    t = w.live_trades[3]
    logs = []
    size, diag, sc = _score(w, t, logs=logs)
    assert size == _direct(w.nightly, w, t) and sc["state_source"] == "nightly"
    assert any("scores on the nightly reference" in s for s in logs)


def test_the_date_rule_gates_the_nightly_only(w):
    w.install_nightly(w.nightly, through=w.days[-8])            # a stale reference
    t = w.live_trades[5]
    size, diag, _sc = _score(w, t)
    assert isinstance(diag, str) and "stale" in diag, "no live state: the stale nightly falls back"
    w.install_nightly(w.nightly)                                # the cut night's nightly
    live = _grow(w, w.live_trades[:5])
    w.install_nightly(w.nightly, through=w.days[-8])            # the reference goes stale again
    cs._KEEL_STATE_CACHE.clear()
    size, diag, sc = _score(w, t)
    assert isinstance(diag, dict) and size == _direct(live, w, t) and sc["state_source"] == "live"
    # the step-time read: no fallback while the live state would score
    now = t["entry_time"].to_pydatetime()
    assert cs._keel_fallback_reason(w.keel_cfg(), now, arrays=w.q_arrays) is None
    os.remove(w.files["live_path"])
    cs._KEEL_STATE_CACHE.clear()
    assert "stale" in cs._keel_fallback_reason(w.keel_cfg(), now, arrays=w.q_arrays)


def test_the_same_bar_rule_scores_on_the_state_before_the_last_append(w):
    t0, t1 = w.live_trades[:2]
    assert t1["e"] == t0["x"]
    _grow(w, [t0])
    logs = []
    size, diag, sc = _score(w, t1, logs=logs)
    assert sc["state_source"] == "live_prev" and sc["ledger_n"] == w.nightly["n"]
    assert size == _direct(w.load("live_prev_path"), w, t1) == _direct(w.nightly, w, t1)
    assert any("same-bar" in s for s in logs)
    # a _prev that is not the state right before the last append (its n), or whose own last exit
    # is on this bar too: the live state scores, said in the log
    import joblib
    prev = w.load("live_prev_path")
    pmeta = cs.keel_live_meta(prev)
    for bad, why in ((dict(prev, n=int(prev["n"]) - 1), "not the state before the last append"),
                     (dict(prev, **{cs.KEEL_LIVE_META: dict(
                         pmeta, last_exit_bar_ts=w.q_idx[t1["e"]].isoformat())}),
                      "its own last exit is on this bar too")):
        joblib.dump(bad, w.files["live_prev_path"])
        cs._KEEL_STATE_CACHE.clear()
        logs = []
        size, diag, sc = _score(w, t1, logs=logs)
        assert sc["state_source"] == "live" and size == _direct(w.load("live_path"), w, t1)
        assert any(why in s for s in logs), why
    # no usable _prev: the live state scores anyway, said in the log
    os.remove(w.files["live_prev_path"])
    cs._KEEL_STATE_CACHE.clear()
    logs = []
    size, diag, sc = _score(w, t1, logs=logs)
    assert sc["state_source"] == "live" and size == _direct(w.load("live_path"), w, t1)
    assert any("same-bar rule not kept" in s for s in logs)


# ── health: keel_ledger_behind ──────────────────────────────────────────────────────────────────
def _trades_csv(w, rows):
    d = os.path.join(w.home, "qqq_exec")
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "trades.csv"), "w", encoding="utf-8", newline="") as f:
        wr = csv.DictWriter(f, fieldnames=["leg", "entry_ts", "exit_ts", "side", "shares", "pnl",
                                           "trade_id"])
        wr.writeheader()
        for r in rows:
            wr.writerow(r)


def _row(tid, exit_ts, leg="NOISE"):
    return {"leg": leg, "entry_ts": exit_ts, "exit_ts": exit_ts, "side": "long", "shares": 10,
            "pnl": 1.0, "trade_id": tid}


def test_ledger_behind_counts_closed_live_trades_neither_appended_nor_rejected(w, monkeypatch):
    monkeypatch.setattr(cs, "KEEL_LIVE_FEED", cs.KEEL_LIVE_FEED_QQQ)   # the QQQ feed's own count
    ts = w.live_trades
    _grow(w, ts[:2])
    # a rejected one (no entry record) -- the handler's ack names it
    w.drop(w.inbox_trade(ts[2]))
    assert [r["status"] for r in w.run()] == ["rejected"]
    cut_exit = ts[0]["exit_ts"]
    rows = [_row("NOISE_382-20240101T150000Z-L", "2024-01-02 10:00:00"),     # before the cut
            # entered on the cut's own NQ day, held past the cut's first exit: before the cut
            dict(_row("NOISE_382-20240130T205500Z-L", ts[1]["exit_ts"]),
                 entry_ts=f"{w.nightly_day} 15:55:00"),
            _row("ORB_R6-20240202T150000Z-L", "2024-02-02 15:00:00", leg="ORB"),
            _row("NOISE_304-20240202T150000Z-L", "2024-02-02 15:00:00")]
    rows += [_row(t["trade_id"], t["exit_ts"]) for t in ts[:3]]
    rows += [_row(t["trade_id"], t["exit_ts"]) for t in ts[3:5]]              # not appended yet
    _trades_csv(w, rows)
    assert cut_exit == rows[4]["exit_ts"]
    cs._KEEL_STATE_CACHE.clear()
    logs = []
    size, diag, sc = _score(w, ts[5], logs=logs)
    assert sc["state_source"] == "live" and sc["ledger_behind"] == 2
    assert cs._keel_ledger_cols(sc) == {"keel_ledger_n": w.nightly["n"] + 2, "keel_ledger_behind": 2}
    assert not any("WARNING" in s for s in logs)
    # more than KEEL_LEDGER_BEHIND_WARN behind: still scored on the live state, with a warning
    rows += [_row(f"NOISE_382-2024020{i}T200000Z-L", "2024-02-05 15:0%d:00" % i) for i in range(2)]
    _trades_csv(w, rows)
    logs = []
    size2, diag, sc = _score(w, ts[5], logs=logs)
    assert sc["ledger_behind"] == 4 > cs.KEEL_LEDGER_BEHIND_WARN
    assert size2 == size == _direct(w.load("live_path"), w, ts[5])
    assert any("WARNING KEEL live ledger is 4 closed live trade(s) behind" in s for s in logs)


# ── the entry record ────────────────────────────────────────────────────────────────────────────
def _diff_two_ticks(w, cfg_keel, leg=LEG, shadow=False):
    """Seed on one open trade, then a tick that discovers trade `t` (ENTRY + EXIT): _diff_leg as
    step() calls it. Returns (events, t)."""
    t = w.live_trades[5]
    arrays = w.q_arrays
    last = len(arrays["close"]) - 1
    leg_state = {"trades": {}}
    open_trade = (t["e"] - 20, last, 3.0, 1, float(arrays["close"][t["e"] - 20]))
    cfg0 = _sizing_cfg([open_trade], size=2.0, cost=0.0, keel_cfg=cfg_keel)
    if shadow:
        cfg0["shadow"] = True
    cs._diff_leg(leg, cs.run_leg_trades(cfg0, arrays, leg_key=leg), leg_state,
                 w.q_idx[t["e"] - 19], cfg=cfg0, arrays=arrays, fetch=False)
    new_trade = (t["e"], t["x"], -1.0, 1, float(arrays["close"][t["e"]]))
    cfg1 = _sizing_cfg([open_trade, new_trade], size=2.0, cost=0.0, keel_cfg=cfg_keel)
    if shadow:
        cfg1["shadow"] = True
    ev = cs._diff_leg(leg, cs.run_leg_trades(cfg1, arrays, leg_key=leg), leg_state,
                      w.q_idx[t["x"]], cfg=cfg1, arrays=arrays, fetch=False,
                      max_entry_age_sec=10 ** 9)
    return ev, t, cfg1


def _xrows(w):
    try:
        with open(w.files["xrows_path"], encoding="utf-8") as f:
            return [json.loads(x) for x in f.read().splitlines() if x.strip()]
    except FileNotFoundError:
        return []


def test_a_live_entry_carries_its_exact_feature_row_and_it_is_written_once(w, monkeypatch):
    monkeypatch.setenv("EDGELOG_HOST_ROLE", "cloud")
    live = _grow(w, w.live_trades[:3])
    events, t, cfg = _diff_two_ticks(w, w.keel_cfg())
    (entry,) = [e for e in events if e["event"] == "ENTRY"]
    rec = entry["_keel_xrow"]
    F, names = w.q_feats
    assert rec["x_row"] == [float(v) for v in F[t["e"]]] and rec["feature_names"] == list(names)
    assert rec["trade_id"] == entry["trade_id"] and rec["entry_time"] == str(entry["ref_time"])
    assert rec["entry_bar"] == t["e"] and rec["entry_bar_time"] == w.q_idx[t["e"]].isoformat()
    assert rec["keel_size"] == entry["keel_size"] == _direct(live, w, t)
    assert rec["engine_size"] == entry["size"] == pytest.approx(2.0 * entry["keel_size"], rel=1e-15)
    assert rec["plugin_size"] == 2.0
    assert (rec["state_source"], rec["state_n"]) == ("live", live["n"])
    assert entry["keel_ledger_n"] == live["n"]
    legs = {LEG: dict(cfg, keel=w.keel_cfg())}
    # an offline tick (a replay) never writes it
    cs._note_keel_entries(events, legs, w.cs_paths, False, log=lambda *a: None, push=lambda *a, **k: None)
    assert _xrows(w)[-1]["trade_id"] != rec["trade_id"]
    n0 = len(_xrows(w))
    for _ in range(2):
        cs._note_keel_entries(events, legs, w.cs_paths, True, log=lambda *a: None,
                              push=lambda *a, **k: None)
    got = _xrows(w)
    assert len(got) == n0 + 1 and got[-1] == rec
    assert cs.read_keel_xrows(w.files["xrows_path"])[rec["trade_id"]] == rec
    # the signal row carries the ledger columns
    cs._append_signals(events, w.cs_paths)
    with open(w.cs_paths["signals_path"], encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    (row,) = [r for r in rows if r["event"] == "ENTRY"]
    assert row["keel_ledger_n"] == str(live["n"]) and "_keel_xrow" not in row


def test_no_record_off_the_box_or_on_a_shadow_leg_and_a_fallback_entry_has_one(w, monkeypatch):
    monkeypatch.delenv("EDGELOG_HOST_ROLE", raising=False)
    events, _t, _cfg = _diff_two_ticks(w, w.keel_cfg())
    assert not any("_keel_xrow" in e for e in events)
    monkeypatch.setenv("EDGELOG_HOST_ROLE", "cloud")
    events, _t, _cfg = _diff_two_ticks(w, w.keel_cfg(), shadow=True)
    assert not any("_keel_xrow" in e for e in events)
    # a leg that does not learn live (no xrows_path in its keel block)
    cfg = {k: v for k, v in w.keel_cfg().items() if k not in ("xrows_path",)}
    events, _t, _cfg = _diff_two_ticks(w, cfg)
    assert not any("_keel_xrow" in e for e in events)
    # the fixed-tilt fallback (no nightly, no live state) is recorded too
    os.remove(w.files["state_path"])
    cs._KEEL_STATE_CACHE.clear()
    events, t, _cfg = _diff_two_ticks(w, w.keel_cfg())
    (entry,) = [e for e in events if e["event"] == "ENTRY"]
    rec = entry["_keel_xrow"]
    assert rec["state_source"] == "fallback" and rec["state_n"] is None
    assert "keel state unavailable" in rec["keel_reason"]
    assert rec["x_row"] == [float(v) for v in w.q_feats[0][t["e"]]]
    assert rec["keel_size"] == entry["keel_size"] and entry["keel_ledger_n"] == ""


def test_the_record_file_survives_a_torn_line_and_never_raises(w, tmp_path):
    t = w.live_trades[0]
    rec = w.xrow_record(t, 1.0)
    os.makedirs(os.path.dirname(w.files["xrows_path"]), exist_ok=True)
    with open(w.files["xrows_path"], "w", encoding="utf-8") as f:
        f.write('{"trade_id": "torn')                          # a crash mid-line
    assert cs._append_keel_xrow(w.files["xrows_path"], rec) is True
    assert cs.read_keel_xrows(w.files["xrows_path"]) == {rec["trade_id"]: rec}
    assert cs._append_keel_xrow(w.files["xrows_path"], rec) is False
    # an unwritable path: None, logged, no exception
    logs = []
    bad = str(tmp_path / "a_file")
    open(bad, "w").close()
    assert cs._append_keel_xrow(os.path.join(bad, "x.jsonl"), rec, log=logs.append) is None
    assert logs and "not written" in logs[0]
    # NaN features are null in the file and NaN again for the handler
    rec2 = dict(rec, trade_id=rec["trade_id"] + "X", x_row=[None] + rec["x_row"][1:])
    assert cs._append_keel_xrow(w.files["xrows_path"], rec2) is True
    assert cs.read_keel_xrows(w.files["xrows_path"])[rec2["trade_id"]]["x_row"][0] is None
    assert cs._jsonable_row(np.array([np.nan, 1.5, np.inf])) == [None, 1.5, None]
