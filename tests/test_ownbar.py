"""OWN-BAR FAST PATH (owner order 2026-11-21, PAPER only) -- api/ownbar.py and its hooks in
api/webull_stream.py, api/cloud_signal_stream.py, api/cloud_signal.py, api/qqq_exec.py."""
import json
import os
import socket
import time

import pytest

from api import ownbar
from api import cloud_signal_stream as css
from api import webull_stream as ws

NOOP = lambda *a, **k: None  # noqa: E731
B0 = 1795111200            # a 5m-aligned epoch (bar start)
CLOSE = B0 + 300


def _minutes(skip=None):
    out = {}
    for k in range(5):
        if k == skip:
            continue
        out[B0 + 60 * k] = {"time": B0 + 60 * k, "open": 100 + k, "high": 101 + k,
                            "low": 99 + k, "close": 100.5 + k, "volume": 1000 + k}
    return out


def _fold(minutes=None, now=CLOSE + 0.06, last=CLOSE - 0.1, connected=True, conn=B0 - 600):
    return ownbar.fold_own_bar(_minutes() if minutes is None else minutes, B0, now, last,
                               connected, conn, stale_after=2.0, grace=0.05)


def _free_port():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


# -- the fold -----------------------------------------------------------------------------
def test_fold_at_boundary_folds_five_minutes():
    bar, why = _fold()
    assert why == "ok"
    assert bar == {"time": B0, "open": 100.0, "high": 105.0, "low": 99.0, "close": 104.5,
                   "volume": float(sum(1000 + k for k in range(5)))}


def test_missing_minute_is_partial_and_refused():
    bar, why = _fold(minutes=_minutes(skip=2))
    assert bar is None and "missing minute 3/5" in why


def test_minute_without_prints_is_refused():
    m = _minutes()
    m[B0 + 240]["volume"] = 0
    bar, why = _fold(minutes=m)
    assert bar is None and "no real prints" in why


def test_last_minute_not_closed_yet_is_refused():
    bar, why = _fold(now=CLOSE + 0.01, last=CLOSE)
    assert bar is None and "not closed" in why


def test_stale_2_1s_refused_and_1_9s_used():
    now = CLOSE + 0.06
    bar, why = _fold(now=now, last=now - 2.1)
    assert bar is None and "stale" in why
    bar, why = _fold(now=now, last=now - 1.9)
    assert bar is not None and why == "ok"


def test_stale_default_is_2s(monkeypatch):
    monkeypatch.delenv("EDGELOG_OWNBAR_STALE_S", raising=False)
    assert ownbar.stale_s() == 2.0
    monkeypatch.setenv("EDGELOG_OWNBAR_STALE_S", "3.5")
    assert ownbar.stale_s() == 3.5


def test_disconnected_or_reconnected_inside_bar_refused():
    assert _fold(connected=False)[0] is None
    bar, why = _fold(conn=B0 + 30)
    assert bar is None and "partial" in why


# -- flag + LIVE refusal ---------------------------------------------------------------------
def test_flag_default_off(monkeypatch):
    monkeypatch.delenv("EDGELOG_OWNBAR_DECIDE", raising=False)
    assert ownbar.enabled() is False
    assert ownbar.active(lambda: {"mode": "PAPER"})[0] is False


def test_live_refused_paper_allowed(monkeypatch):
    monkeypatch.setenv("EDGELOG_OWNBAR_DECIDE", "1")
    assert ownbar.active(lambda: {"mode": "PAPER"}) == (True, "ok")
    on, why = ownbar.active(lambda: {"mode": "LIVE"})
    assert on is False and "LIVE" in why
    assert ownbar.active(lambda: {"mode": "OFF"})[0] is False


def test_ownbar_active_live_logs_and_alerts_once(monkeypatch):
    monkeypatch.setenv("EDGELOG_OWNBAR_DECIDE", "1")
    monkeypatch.setattr(ownbar, "live_refusal", lambda load_config=None: "broker mode is LIVE")
    pushes = []
    monkeypatch.setattr(css, "_ownbar_push", lambda m, p, l, priority="high": pushes.append(m))
    css._OWNBAR_REFUSAL_LOGGED["why"] = None
    assert css.ownbar_active({}, log=NOOP) is False
    assert css.ownbar_active({}, log=NOOP) is False
    assert len(pushes) == 1 and "LIVE" in pushes[0]


def test_flag_off_run_stream_aware_step_unchanged(monkeypatch):
    monkeypatch.delenv("EDGELOG_OWNBAR_DECIDE", raising=False)
    monkeypatch.setattr(css, "handle_ownbar", lambda *a, **k: pytest.fail("own-bar ran"))
    monkeypatch.setattr(css.cs, "step", lambda **k: ["classic"])
    monkeypatch.setattr(css.cs, "bar_cache_refusal", lambda *a, **k: None)
    monkeypatch.setattr(css, "load_stream_config", lambda *a, **k: {"bar_close_from_stream": False})
    monkeypatch.setattr(css, "_run_stream_extras", NOOP)
    assert css.run_stream_aware_step(legs={}, paths={"state_dir": "x"}, log=NOOP) == ["classic"]


def test_flag_off_engine_sleep_is_time_sleep(monkeypatch):
    from api import cloud_signal as cs
    monkeypatch.delenv("EDGELOG_OWNBAR_DECIDE", raising=False)
    slept = []
    monkeypatch.setattr(cs._time, "sleep", lambda s: slept.append(s))
    monkeypatch.setattr(ownbar, "shared_socket", lambda p: pytest.fail("socket used"))
    cs._engine_sleep(0.25, True)
    assert slept == [0.25]


def test_flag_off_exec_wait_has_no_socket(monkeypatch):
    from api import qqq_exec as qe
    monkeypatch.delenv("EDGELOG_OWNBAR_DECIDE", raising=False)
    assert qe._ownbar_exec_socket() is None


# -- streamer side --------------------------------------------------------------------------
def _streamer(tmp_path, now):
    s = ws.WebullBarStreamer(log=NOOP, clock=lambda: now, handoff_home=str(tmp_path))
    s._client = object()
    s._last_connect_epoch = B0 - 600
    s._last_print_wall = now - 0.2
    s._last_print_event_epoch = CLOSE + 0.01      # a QQQ print at/after the boundary
    m = _minutes()
    last = m.pop(B0 + 240)
    with s._lock:
        s._remember_1m(list(m.values()))
        s.builders[60]._bars[s.symbols[0]] = dict(last)   # 5th minute still open at the boundary
    return s


def test_streamer_publishes_own_bar_and_wakes_engine(tmp_path, monkeypatch):
    port = _free_port()
    monkeypatch.setenv("EDGELOG_OWNBAR_ENGINE_PORT", str(port))
    sock = ownbar.WakeSocket(port)
    try:
        s = _streamer(tmp_path, CLOSE + 0.35)
        p = s._ownbar_pass(CLOSE + 0.35)
        assert p["ok"] and p["bar"]["close"] == 104.5 and p["bar_end"] == CLOSE
        assert ownbar.read_handoff(str(tmp_path))["bar"]["volume"] == p["bar"]["volume"]
        assert sock.wait(1.0) == str(CLOSE).encode()
    finally:
        sock.close()


def test_streamer_stale_feed_publishes_not_ok(tmp_path, monkeypatch):
    monkeypatch.setenv("EDGELOG_OWNBAR_ENGINE_PORT", str(_free_port()))
    s = _streamer(tmp_path, CLOSE + 0.35)
    s._last_print_wall = CLOSE + 0.35 - 2.1
    p = s._ownbar_pass(CLOSE + 0.35)
    assert p["ok"] is False and "stale" in p["reason"]


def test_streamer_missing_minute_publishes_not_ok(tmp_path, monkeypatch):
    monkeypatch.setenv("EDGELOG_OWNBAR_ENGINE_PORT", str(_free_port()))
    s = _streamer(tmp_path, CLOSE + 0.35)
    with s._lock:
        s._recent_1m.pop(B0 + 120)
    p = s._ownbar_pass(CLOSE + 0.35)
    assert p["ok"] is False and "missing minute" in p["reason"]


# -- engine side: fallback, commit, audit -------------------------------------------------------
@pytest.fixture
def engine(tmp_path, monkeypatch):
    pushes, handled = [], []
    monkeypatch.setattr(css, "_ownbar_push",
                        lambda m, p, l, priority="high": pushes.append((m, priority)))
    monkeypatch.setattr(css, "_handle_handoff_window",
                        lambda *a, **k: handled.append(k))
    monkeypatch.setattr(css, "_OWNBAR_ALERTS", None)
    css._OWNBAR_DONE["bar_end"] = None
    return {"home": str(tmp_path), "state_dir": str(tmp_path)}, pushes, handled


def test_unusable_own_bar_falls_back_to_rest_and_alerts_once_per_episode(engine):
    paths, pushes, handled = engine
    for k in range(2):                                   # two bad bars in a row = one episode
        end = CLOSE + 300 * k
        ownbar.write_handoff(paths["home"], {"bar_end": end, "ok": False,
                                             "reason": "stream stale: last update 2.10s old"})
        assert css.handle_ownbar(None, {"NOISE_382": {}}, paths, NOOP, wall=end + 0.1) is True
    assert handled == [] and len(pushes) == 1 and "fell back" in pushes[0][0]
    rows = [json.loads(x) for x in open(ownbar.audit_path(paths["home"]))]
    assert [r["kind"] for r in rows] == ["fallback", "fallback"]
    # a good bar ends the episode; the next bad one alerts again
    end = CLOSE + 600
    ownbar.write_handoff(paths["home"], {"bar_end": end, "ok": True, "bar": {"time": end - 300,
                         "open": 1, "high": 1, "low": 1, "close": 1, "volume": 1}})
    css.handle_ownbar(None, {"NOISE_382": {}}, paths, NOOP, wall=end + 0.1)
    end = CLOSE + 900
    ownbar.write_handoff(paths["home"], {"bar_end": end, "ok": False, "reason": "missing minute 2/5"})
    css.handle_ownbar(None, {"NOISE_382": {}}, paths, NOOP, wall=end + 0.1)
    assert len(pushes) == 2


def test_no_own_bar_file_falls_back_after_1_5s(engine):
    paths, pushes, handled = engine
    assert css.handle_ownbar(None, {"X": {}}, paths, NOOP, wall=CLOSE + 1.2) is False
    assert css.handle_ownbar(None, {"X": {}}, paths, NOOP, wall=CLOSE + 1.6) is True
    assert handled == [] and len(pushes) == 1


def test_usable_own_bar_commits_with_ownbar_source_and_wakes_executor(engine, monkeypatch):
    paths, pushes, handled = engine
    port = _free_port()
    monkeypatch.setenv("EDGELOG_OWNBAR_EXEC_PORT", str(port))
    sock = ownbar.WakeSocket(port)
    try:
        bar = {"time": B0, "open": 1, "high": 2, "low": 0.5, "close": 1.5, "volume": 10}
        ownbar.write_handoff(paths["home"], {"bar_end": CLOSE, "ok": True, "bar": bar})
        assert css.handle_ownbar(None, {"NOISE_382": {}}, paths, NOOP, wall=CLOSE + 0.07)
        k = handled[0]
        assert k["force_live"] is True and k["bar_source"] == "ownbar" and k["payload"] == bar
        k["on_commit"]("NOISE_382", [{"event": "ENTRY"}])
        assert sock.wait(1.0) == f"NOISE_382:{CLOSE}".encode()
        # handled once per boundary
        assert css.handle_ownbar(None, {"NOISE_382": {}}, paths, NOOP, wall=CLOSE + 0.2) is False
    finally:
        sock.close()


def test_audit_logs_both_bars_and_alerts_on_flip_only(engine):
    paths, pushes, _ = engine
    own = {"time": B0, "open": 1, "high": 2, "low": 0.5, "close": 1.5, "volume": 10}
    rest = dict(own, close=1.49, volume=12)
    rec = {"bar": own, "events": [{"event": "ENTRY", "side": "long"}], "committed_live": True,
           "decided_epoch": CLOSE + 0.1}
    css._ownbar_audit(paths, "NOISE_382", B0, rec, rest, rec["events"], True, "same", NOOP)
    assert pushes == []
    css._ownbar_audit(paths, "NOISE_382", B0, rec, rest, [], False, "stream=.. rest=[]", NOOP)
    assert len(pushes) == 1 and "FLIP" in pushes[0][0] and pushes[0][1] == "urgent"
    assert "NOT reversed" in pushes[0][0]
    rows = [json.loads(x) for x in open(ownbar.audit_path(paths["home"]))]
    assert [r["flip"] for r in rows] == [False, True]
    assert rows[1]["own_bar"]["close"] == 1.5 and rows[1]["rest_final_bar"]["close"] == 1.49
    assert rows[1]["ohlc_diff_own_minus_rest"]["volume"] == -2
    assert rows[1]["rest_decision"] == [] and len(rows[1]["own_decision"]) == 1


# -- latency stamps ------------------------------------------------------------------------------
def test_latency_stamps_and_webull_times(monkeypatch):
    from api import qqq_exec as qe
    from datetime import datetime, timezone
    emitted = datetime.fromtimestamp(CLOSE + 0.12, timezone.utc).isoformat()
    qe._set_latency_ctx({"emitted_at": emitted})
    st = qe._latency_stamps(CLOSE + 0.2, CLOSE + 0.45)
    assert st["bar_end_ts"] == CLOSE and abs(st["decision_ts"] - (CLOSE + 0.12)) < 1e-3
    assert st["send_ts"] == round(CLOSE + 0.2, 3) and st["ack_ts"] == round(CLOSE + 0.45, 3)
    qe._LATENCY_CTX.clear()
    assert qe._latency_stamps(1.0, 2.0)["bar_end_ts"] == ""
    resp = {"orders": [{"client_order_id": "C1", "place_time": str(int((CLOSE + 0.3) * 1000)),
                        "filled_time": str(int((CLOSE + 0.9) * 1000))}]}
    qe._stash_order_times(resp, "C1", "S1")
    t = qe._order_times_for({"signal_id": "S1"})
    assert t == {"place_ts": round(CLOSE + 0.3, 3), "fill_ts": round(CLOSE + 0.9, 3)}
    assert "fill_ts" in qe.BROKER_ORDER_COLS and qe.BROKER_ORDER_COLS[-6] == "bar_end_ts"


def test_daily_latency_line():
    rows = [{"bar_end_ts": CLOSE, "send_ts": CLOSE + d / 1000, "ack_ts": CLOSE + d / 1000 + 0.28,
             "fill_ts": CLOSE + d / 1000 + 0.6} for d in (100, 150, 200, 250, 900)]
    rows.append({"bar_end_ts": "", "send_ts": "", "ack_ts": "", "fill_ts": ""})
    line = ownbar.latency_line(rows)
    assert line.startswith("latency bar->send p50 200 / p90 900 ms")
    assert "send->ack p50 280" in line and "send->fill p50 600" in line
    assert ownbar.latency_line([{}]) == ""


# -- timing: boundary -> fold -> engine wake -> commit -> executor wake -> send ------------------
def test_bar_end_to_send_under_300ms_with_fake_adapter(tmp_path, monkeypatch):
    """The plumbing budget, measured: streamer fold + hand-off file + UDP to the engine,
    engine reads the file and 'decides' (stub, 0 ms -- the real ORB/NOISE engine cost is
    measured separately, see the commit), appends signals.csv, UDP to the executor, which
    reads the row and calls a fake adapter. Asserts < 300 ms from the fold call."""
    ep, xp = _free_port(), _free_port()
    monkeypatch.setenv("EDGELOG_OWNBAR_ENGINE_PORT", str(ep))
    monkeypatch.setenv("EDGELOG_OWNBAR_EXEC_PORT", str(xp))
    eng, exe = ownbar.WakeSocket(ep), ownbar.WakeSocket(xp)
    sent = []

    class FakeAdapter:
        def place_stock_order(self, **k):
            sent.append(time.perf_counter())
            return {"ok": True, "sent": True}
    try:
        s = _streamer(tmp_path, CLOSE + 0.35)
        sig = tmp_path / "signals.csv"
        t0 = time.perf_counter()
        s._ownbar_pass(CLOSE + 0.35)
        assert eng.wait(1.0)                                     # engine woken
        p = ownbar.read_handoff(str(tmp_path))
        assert p["ok"]
        with open(sig, "a", encoding="utf-8") as f:             # commit the row
            f.write(f"ENTRY,NOISE_382,long,{p['bar']['close']}\n")
        ownbar.wake(ownbar.exec_port(), b"NOISE_382")
        assert exe.wait(1.0)                                     # executor woken
        row = open(sig, encoding="utf-8").read().strip().split(",")
        FakeAdapter().place_stock_order(side="BUY", qty=5, symbol="QQQ", leg=row[1])
        ms = (sent[0] - t0) * 1000
        print(f"own-bar plumbing bar fold -> fake send: {ms:.1f} ms")
        assert ms < 300, ms
    finally:
        eng.close()
        exe.close()


# -- VERIFIER 11-21 must-fixes ---------------------------------------------------------------
def test_grace_default_is_0_3(monkeypatch):
    monkeypatch.delenv("EDGELOG_OWNBAR_GRACE_S", raising=False)
    assert ownbar.grace_s() == 0.3


def test_unconfirmed_fifth_minute_is_refused():
    bar, why = ownbar.fold_own_bar(_minutes(), B0, CLOSE + 0.35, CLOSE + 0.3, True, B0 - 600,
                                   stale_after=2.0, grace=0.3, fifth_closed=False)
    assert bar is None and why.startswith(ownbar.NOT_CONFIRMED)


def test_streamer_waits_for_fifth_minute_evidence_then_falls_back(tmp_path, monkeypatch):
    monkeypatch.setenv("EDGELOG_OWNBAR_ENGINE_PORT", str(_free_port()))
    s = _streamer(tmp_path, CLOSE + 0.35)
    s._last_print_event_epoch = CLOSE - 0.5          # last print still inside minute 5
    assert s.fifth_minute_closed(CLOSE) is False
    assert s._ownbar_pass(CLOSE + 0.35, final=False) == {
        "retry": True, "reason": s._ownbar_pass(CLOSE + 0.35, final=False)["reason"]}
    assert ownbar.read_handoff(str(tmp_path)) is None   # nothing published while retrying
    p = s._ownbar_pass(CLOSE + 1.0, final=True)
    assert p["ok"] is False and ownbar.NOT_CONFIRMED in p["reason"]


def test_fifth_minute_evidence_print_or_rolled_builder(tmp_path):
    s = _streamer(tmp_path, CLOSE + 0.35)
    assert s.fifth_minute_closed(CLOSE) is True       # print stamped at/after the boundary
    s._last_print_event_epoch = CLOSE - 1
    assert s.fifth_minute_closed(CLOSE) is False
    with s._lock:
        s.builders[60]._bars[s.symbols[0]] = {"time": CLOSE, "open": 1, "high": 1, "low": 1,
                                              "close": 1, "volume": 1}
    assert s.fifth_minute_closed(CLOSE) is True       # builder rolled to the next minute


class _Q:
    def __init__(self):
        b = type("B", (), {})()
        b.symbol, b.timestamp, b.trading_session = "QQQ", 0, None
        self.basic = b
        self.bids = [type("L", (), {"price": "1", "size": "1"})()]
        self.asks = [type("L", (), {"price": "1.01", "size": "1"})()]


def test_quotes_do_not_refresh_trade_print_staleness(tmp_path):
    now = [CLOSE + 0.35]
    s = ws.WebullBarStreamer(log=NOOP, clock=lambda: now[0], handoff_home=str(tmp_path))
    s._last_print_wall = now[0] - 2.1
    s._on_message("quote", _Q())                      # a quote arrives: feed is "alive"
    assert s._last_feed_epoch == now[0]
    assert s._last_print_wall == now[0] - 2.1         # but the trade-print clock did not move


def test_handle_ownbar_skips_non_rth_bar(engine):
    paths, pushes, handled = engine
    from datetime import datetime
    from zoneinfo import ZoneInfo
    open_bar_end = int(datetime(2026, 11, 23, 9, 30, tzinfo=ZoneInfo("America/New_York")).timestamp())
    assert css.handle_ownbar(None, {"X": {}}, paths, NOOP, wall=open_bar_end + 2) is False
    assert pushes == [] and handled == []


def test_exec_socket_and_warm_gated_on_paper(monkeypatch):
    from api import qqq_exec as qe
    monkeypatch.setenv("EDGELOG_OWNBAR_DECIDE", "1")
    monkeypatch.setattr(ownbar, "live_refusal", lambda load_config=None: "broker mode is LIVE")
    qe._OWNBAR_ACTIVE.update(at=0.0, on=False)
    monkeypatch.setattr(qe, "_ensure_ownbar_warm_thread", lambda: pytest.fail("warm started"))
    assert qe._ownbar_exec_socket() is None


def test_warm_head_timeout_is_short():
    import inspect
    from api import webull_orders as wo
    assert inspect.signature(wo.keepalive_warm).parameters["timeout"].default == (0.4, 0.4)
    assert ownbar.warm_lead_s() == 5.0


def test_update_row_migrates_old_header(tmp_path, monkeypatch):
    import csv
    from api import qqq_exec as qe
    path = tmp_path / "broker_orders.csv"
    old = ["ts_et", "leg", "signal_id", "broker_fill_px"]
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=old)
        w.writeheader()
        w.writerow({"ts_et": "x", "leg": "L", "signal_id": "S0", "broker_fill_px": ""})
        w.writerow({"ts_et": "x", "leg": "L", "signal_id": "S1", "broker_fill_px": ""})
    monkeypatch.setattr(qe, "BROKER_ORDERS_CSV", str(path))
    assert qe._update_broker_order_row("S1", {"broker_fill_px": 1.5, "fill_ts": 123.4}, log=NOOP)
    rows = list(csv.DictReader(open(path, encoding="utf-8", newline="")))
    assert rows[1]["fill_ts"] == "123.4" and rows[1]["broker_fill_px"] == "1.5"
    assert rows[0]["fill_ts"] == ""
