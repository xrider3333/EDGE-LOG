"""api/qqq_exec.py's "LIVE POSITIONS + ACCOUNT EQUITY" build (2026-09-23, item 3 --
owner: "since we are live with live pricing, can you show the positions live? and
potentially equity as well").

Covers: the positions_live payload (per-leg live price/age/source, open P&L computed
off that SAME live price, the broker-vs-book net-QQQ mismatch check), the account
equity refresh/publish cycle (boot-time read, ~once/min while the market is open,
stale fallback that keeps the last good value and never raises), and the new
publish-throttle ceiling that lets those live marks refresh at most every 10s, only
in-session and only while a position is open (the Firestore-quota rule).

No network, no real EDGELOG_HOME: every test builds its own state/cfg dicts and fake
broker adapters.
"""
from datetime import datetime, timedelta

import pytest

from api import qqq_exec as qe

NOOP = lambda *a, **k: None  # noqa: E731


@pytest.fixture(autouse=True)
def _steady_state_after_boot_read(monkeypatch):
    """_maybe_read_account_equity forces ONE read per process at boot (module-level flag).
    Every test here starts in the steady state AFTER that read, so the flag can never leak
    between tests; the boot behaviour itself is pinned by the tests that set it False."""
    monkeypatch.setattr(qe, "_EQUITY_BOOT_READ_DONE", True)


def _cfg(**overrides):
    cfg = dict(qe.DEFAULT_CONFIG)
    cfg.update(overrides)
    return cfg


def _lot(side="long", shares=10, entry_px=700.0, entry_ts="2026-09-23 09:35:00", trade_id="t1"):
    return {"side": side, "shares_remaining": shares, "shares_total": shares,
           "entry_px": entry_px, "entry_ts": entry_ts, "trade_id": trade_id}


class _FakeAdapterNoPositions:
    def status(self):
        return {"broker_sent_positions": {}}


class _FakeAdapterWithPositions:
    def __init__(self, positions):
        self._positions = positions

    def status(self):
        return {"broker_sent_positions": self._positions}


# ── positions_live: empty/flat ──────────────────────────────────────────────────────────

def test_positions_live_empty_when_flat(monkeypatch):
    monkeypatch.setattr(qe, "_get_broker_adapter", lambda log=print: _FakeAdapterNoPositions())
    out = qe._build_positions_live({"legs": {}}, _cfg(), log=NOOP)
    assert out["legs"] == []
    assert out["total_open_pnl"] == 0.0
    assert out["legs_net_qty"] == 0
    assert out["mismatch"] is False


# ── positions_live: live price + open P&L (independent of the bar-close mark) ──────────

def test_positions_live_uses_live_price_for_open_pnl(monkeypatch):
    monkeypatch.setattr(qe, "_get_broker_adapter", lambda log=print: _FakeAdapterNoPositions())
    monkeypatch.setattr(qe, "_live_price_for_leg", lambda leg, log=print: (705.0, 1.2, "stream"))
    monkeypatch.setattr(qe, "_now_et", lambda: datetime(2026, 9, 23, 10, 0, 0))
    state = {"legs": {"ORB": _lot(side="long", shares=10, entry_px=700.0)},
            "_unrl_by_leg": {"ORB": 999.0}}   # deliberately different -- must be ignored
    out = qe._build_positions_live(state, _cfg(), log=NOOP)
    assert len(out["legs"]) == 1
    leg = out["legs"][0]
    assert leg["leg"] == "ORB"
    assert leg["live_px"] == 705.0
    assert leg["live_age_s"] == 1.2
    assert leg["live_source"] == "stream"
    assert leg["open_pnl"] == pytest.approx((705.0 - 700.0) * 10)
    assert leg["time_in_trade_min"] == pytest.approx(25.0)
    assert out["total_open_pnl"] == pytest.approx(50.0)


def test_positions_live_short_leg_pnl(monkeypatch):
    monkeypatch.setattr(qe, "_now_et", lambda: datetime(2026, 9, 23, 9, 10, 0))
    monkeypatch.setattr(qe, "_live_price_for_leg", lambda leg, log=print: (690.0, 0.5, "bar"))
    monkeypatch.setattr(qe, "_get_broker_adapter", lambda log=print: _FakeAdapterNoPositions())
    state = {"legs": {"NOISE": _lot(side="short", shares=5, entry_px=700.0,
                                    entry_ts="2026-09-23 09:00:00")}}
    out = qe._build_positions_live(state, _cfg(), log=NOOP)
    leg = out["legs"][0]
    # short: profits when price falls -- (entry-live)*shares = (700-690)*5 = 50
    assert leg["open_pnl"] == pytest.approx(50.0)


def test_positions_live_no_live_price_leaves_open_pnl_none(monkeypatch):
    monkeypatch.setattr(qe, "_get_broker_adapter", lambda log=print: _FakeAdapterNoPositions())
    monkeypatch.setattr(qe, "_live_price_for_leg", lambda leg, log=print: (None, None, None))
    state = {"legs": {"ORB": _lot()}}
    out = qe._build_positions_live(state, _cfg(), log=NOOP)
    assert out["legs"][0]["open_pnl"] is None
    assert out["legs"][0]["live_source"] is None
    assert out["total_open_pnl"] == 0.0


# ── broker-vs-book cross-check ──────────────────────────────────────────────────────────

def test_positions_live_mismatch_false_when_broker_agrees(monkeypatch):
    monkeypatch.setattr(qe, "_live_price_for_leg", lambda leg, log=print: (700.0, 0, "bar"))
    monkeypatch.setattr(qe, "_get_broker_adapter",
                        lambda log=print: _FakeAdapterWithPositions(
                            {"ORB": {"symbol": "QQQ", "qty": 10}}))
    state = {"legs": {"ORB": _lot(side="long", shares=10)}}
    out = qe._build_positions_live(state, _cfg(), log=NOOP)
    assert out["legs_net_qty"] == 10
    assert out["broker_net_qty"] == 10
    assert out["mismatch"] is False


def test_positions_live_mismatch_true_when_broker_disagrees(monkeypatch):
    monkeypatch.setattr(qe, "_live_price_for_leg", lambda leg, log=print: (700.0, 0, "bar"))
    monkeypatch.setattr(qe, "_get_broker_adapter",
                        lambda log=print: _FakeAdapterWithPositions(
                            {"ORB": {"symbol": "QQQ", "qty": 0}}))   # Webull never got it
    state = {"legs": {"ORB": _lot(side="long", shares=10)}}
    out = qe._build_positions_live(state, _cfg(), log=NOOP)
    assert out["legs_net_qty"] == 10
    assert out["broker_net_qty"] == 0
    assert out["mismatch"] is True


def test_positions_live_never_raises_when_broker_adapter_errors(monkeypatch):
    def boom(log=print):
        raise RuntimeError("adapter unavailable")
    monkeypatch.setattr(qe, "_get_broker_adapter", boom)
    monkeypatch.setattr(qe, "_live_price_for_leg", lambda leg, log=print: (700.0, 0, "bar"))
    state = {"legs": {"ORB": _lot()}}
    out = qe._build_positions_live(state, _cfg(), log=NOOP)   # must not raise
    assert out["broker_net_qty"] is None
    assert out["mismatch"] is False
    assert len(out["legs"]) == 1


# ── _live_price_for_leg: stream vs bar fallback ─────────────────────────────────────────

def test_live_price_for_leg_prefers_fresh_stream(monkeypatch):
    class _Stream:
        def is_fresh(self):
            return True

        def last_trade(self):
            return {"price": 701.5, "age": 0.4}

    monkeypatch.setattr(qe, "_qqq_stream_instance", lambda: _Stream())
    px, age, src = qe._live_price_for_leg("ORB", log=NOOP)
    assert (px, age, src) == (701.5, 0.4, "stream")


def test_live_price_for_leg_falls_back_to_bar_when_not_fresh(monkeypatch):
    class _Stream:
        def is_fresh(self):
            return False

        def last_trade(self):
            raise AssertionError("must not be called when not fresh")

    monkeypatch.setattr(qe, "_qqq_stream_instance", lambda: _Stream())
    monkeypatch.setattr(qe, "_engine_mark_price", lambda leg, log=print: (699.0, "engine_cache"))
    monkeypatch.setattr(qe, "_leg_timeframe_bar_close_age", lambda leg, log=print: 12.0)
    px, age, src = qe._live_price_for_leg("ORB", log=NOOP)
    assert (px, age, src) == (699.0, 12.0, "bar")


def test_live_price_for_leg_stream_exception_falls_back_to_bar(monkeypatch):
    class _BoomStream:
        def is_fresh(self):
            raise RuntimeError("boom")

    monkeypatch.setattr(qe, "_qqq_stream_instance", lambda: _BoomStream())
    monkeypatch.setattr(qe, "_engine_mark_price", lambda leg, log=print: (699.0, "engine_cache"))
    monkeypatch.setattr(qe, "_leg_timeframe_bar_close_age", lambda leg, log=print: None)
    px, age, src = qe._live_price_for_leg("ORB", log=NOOP)   # must not raise
    assert (px, age, src) == (699.0, None, "bar")


def test_live_price_for_leg_none_when_nothing_available(monkeypatch):
    monkeypatch.setattr(qe, "_qqq_stream_instance", lambda: None)
    monkeypatch.setattr(qe, "_engine_mark_price", lambda leg, log=print: (None, None))
    px, age, src = qe._live_price_for_leg("ORB", log=NOOP)
    assert (px, age, src) == (None, None, None)


# ── account equity: refresh gating (boot / ~1min / market hours) ───────────────────────

class _FakeBalanceAdapter:
    def __init__(self, balance, raise_exc=None):
        self._balance = balance
        self._raise = raise_exc
        self.calls = 0

    def get_stock_account_balance(self):
        self.calls += 1
        if self._raise:
            raise self._raise
        return self._balance


def test_maybe_read_account_equity_reads_at_boot_even_off_hours(monkeypatch):
    adapter = _FakeBalanceAdapter({"account_id": "a1", "net_liq": 100000.0, "cash": 5000.0})
    monkeypatch.setattr(qe, "_get_broker_adapter", lambda log=print: adapter)
    state = {}
    off_hours = datetime(2026, 9, 20, 3, 0, 0)   # a Sunday, well outside market hours
    qe._maybe_read_account_equity(state, _cfg(), off_hours, log=NOOP)
    assert adapter.calls == 1
    assert state["equity"]["net_liq"] == 100000.0
    assert state["equity"]["first_net_liq_today"] == 100000.0


def test_maybe_read_account_equity_skips_when_not_due_and_offhours(monkeypatch):
    adapter = _FakeBalanceAdapter({"account_id": "a1", "net_liq": 100000.0, "cash": 5000.0})
    monkeypatch.setattr(qe, "_get_broker_adapter", lambda log=print: adapter)
    state = {"equity": {"_epoch": qe.time.time(), "net_liq": 99000.0, "day": "2026-09-19",
                        "first_net_liq_today": 99000.0, "as_of_et": "2026-09-19 09:31:00"}}
    off_hours = datetime(2026, 9, 20, 3, 0, 0)
    qe._maybe_read_account_equity(state, _cfg(), off_hours, log=NOOP)
    assert adapter.calls == 0, "already have a reading and the market is shut -- must not read again"
    assert state["equity"]["net_liq"] == 99000.0


def test_maybe_read_account_equity_refreshes_during_session_once_due(monkeypatch):
    now_holder = {"t": 1_000_000.0}
    monkeypatch.setattr(qe.time, "time", lambda: now_holder["t"])
    adapter = _FakeBalanceAdapter({"account_id": "a1", "net_liq": 100500.0, "cash": 5000.0})
    monkeypatch.setattr(qe, "_get_broker_adapter", lambda log=print: adapter)
    state = {"equity": {"_epoch": now_holder["t"] - qe.ACCOUNT_EQUITY_REFRESH_SEC - 1,
                        "net_liq": 100000.0, "day": "2026-09-23",
                        "first_net_liq_today": 100000.0, "as_of_et": "2026-09-23 09:31:00"}}
    in_session = datetime(2026, 9, 23, 10, 0, 0)
    qe._maybe_read_account_equity(state, _cfg(), in_session, log=NOOP)
    assert adapter.calls == 1
    assert state["equity"]["net_liq"] == 100500.0
    assert state["equity"]["first_net_liq_today"] == 100000.0, "first-of-day reading is preserved"


def test_maybe_read_account_equity_not_due_yet_skips_even_in_session(monkeypatch):
    now_holder = {"t": 1_000_000.0}
    monkeypatch.setattr(qe.time, "time", lambda: now_holder["t"])
    adapter = _FakeBalanceAdapter({"account_id": "a1", "net_liq": 100500.0, "cash": 5000.0})
    monkeypatch.setattr(qe, "_get_broker_adapter", lambda log=print: adapter)
    state = {"equity": {"_epoch": now_holder["t"] - 5, "net_liq": 100000.0, "day": "2026-09-23",
                        "first_net_liq_today": 100000.0, "as_of_et": "2026-09-23 09:31:00"}}
    in_session = datetime(2026, 9, 23, 10, 0, 0)
    qe._maybe_read_account_equity(state, _cfg(), in_session, log=NOOP)
    assert adapter.calls == 0
    assert state["equity"]["net_liq"] == 100000.0


def test_maybe_read_account_equity_new_day_resets_first_reading(monkeypatch):
    adapter = _FakeBalanceAdapter({"account_id": "a1", "net_liq": 101000.0, "cash": 6000.0})
    monkeypatch.setattr(qe, "_get_broker_adapter", lambda log=print: adapter)
    state = {"equity": {"_epoch": 0.0, "net_liq": 100000.0, "day": "2026-09-22",
                        "first_net_liq_today": 99500.0, "as_of_et": "2026-09-22 09:31:00"}}
    in_session = datetime(2026, 9, 23, 9, 31, 0)
    qe._maybe_read_account_equity(state, _cfg(), in_session, log=NOOP)
    assert state["equity"]["day"] == "2026-09-23"
    assert state["equity"]["first_net_liq_today"] == 101000.0


# ── account equity: failure keeps the last value, marks stale, never raises ────────────

def test_maybe_read_account_equity_failure_keeps_last_value(monkeypatch):
    adapter = _FakeBalanceAdapter(None, raise_exc=RuntimeError("network blip"))
    monkeypatch.setattr(qe, "_get_broker_adapter", lambda log=print: adapter)
    state = {"equity": {"_epoch": 0.0, "net_liq": 100000.0, "cash": 5000.0, "day": "2026-09-23",
                        "first_net_liq_today": 100000.0, "as_of_et": "2026-09-23 09:31:00"}}
    in_session = datetime(2026, 9, 23, 10, 0, 0)
    qe._maybe_read_account_equity(state, _cfg(), in_session, log=NOOP)   # must not raise
    assert state["equity"]["net_liq"] == 100000.0, "the previous reading survives a failed refresh"


def test_maybe_read_account_equity_none_balance_keeps_last_value(monkeypatch):
    adapter = _FakeBalanceAdapter(None)   # e.g. OFF mode
    monkeypatch.setattr(qe, "_get_broker_adapter", lambda log=print: adapter)
    state = {"equity": {"_epoch": 0.0, "net_liq": 100000.0, "day": "2026-09-23",
                        "first_net_liq_today": 100000.0, "as_of_et": "2026-09-23 09:31:00"}}
    in_session = datetime(2026, 9, 23, 10, 0, 0)
    qe._maybe_read_account_equity(state, _cfg(), in_session, log=NOOP)
    assert state["equity"]["net_liq"] == 100000.0


def test_maybe_read_account_equity_never_raises_even_when_adapter_lookup_itself_fails(monkeypatch):
    def boom(log=print):
        raise RuntimeError("cannot build adapter")
    monkeypatch.setattr(qe, "_get_broker_adapter", boom)
    state = {}
    qe._maybe_read_account_equity(state, _cfg(), datetime(2026, 9, 23, 10, 0, 0), log=NOOP)


# ── _build_equity_status: stale fallback ────────────────────────────────────────────────

def test_equity_status_not_read_yet():
    out = qe._build_equity_status({}, datetime(2026, 9, 23, 10, 0, 0), log=NOOP)
    assert out["net_liq"] is None
    assert out["stale"] is True


def test_equity_status_fresh_reading_not_stale():
    state = {"equity": {"net_liq": 100500.0, "cash": 5000.0, "as_of_et": "2026-09-23 09:59:00",
                        "first_net_liq_today": 100000.0}}
    out = qe._build_equity_status(state, datetime(2026, 9, 23, 10, 0, 0), log=NOOP)
    assert out["stale"] is False
    assert out["net_liq"] == 100500.0
    assert out["change_today"] == pytest.approx(500.0)
    assert out["change_today_pct"] == pytest.approx(0.5)


def test_equity_status_stale_after_three_missed_refreshes_but_keeps_last_value():
    old_as_of = (datetime(2026, 9, 23, 10, 0, 0)
                - timedelta(seconds=qe.ACCOUNT_EQUITY_REFRESH_SEC * 3 + 30))
    state = {"equity": {"net_liq": 100500.0, "cash": 5000.0,
                        "as_of_et": old_as_of.strftime("%Y-%m-%d %H:%M:%S"),
                        "first_net_liq_today": 100000.0}}
    out = qe._build_equity_status(state, datetime(2026, 9, 23, 10, 0, 0), log=NOOP)
    assert out["stale"] is True
    assert out["net_liq"] == 100500.0, "a stale reading still surfaces its LAST value"
    assert out["note"]


def test_equity_status_no_first_of_day_reading_change_is_none():
    state = {"equity": {"net_liq": 100500.0, "as_of_et": "2026-09-23 09:59:00"}}
    out = qe._build_equity_status(state, datetime(2026, 9, 23, 10, 0, 0), log=NOOP)
    assert out["change_today"] is None
    assert out["change_today_pct"] is None


# ── publish throttle: item 3's Firestore-quota rule ─────────────────────────────────────

def _throttle_doc(positions):
    return {"mode": "SHADOW", "signal_source": "engine", "updated_at": "x",
           "feed_stale": False, "px_feed_stale": False, "breaker_tripped": False,
           "kill": False, "positions": positions,
           "today": {"orders": [], "trades": [], "realized_pnl": 0.0, "unrealized_pnl": 0.0},
           "events": [], "broker": {"effective_mode": "OFF"},
           "lease": {"host_id": "h", "leased_at": 1.0}}


def test_publish_throttle_tightens_to_10s_when_position_open_in_session(monkeypatch):
    monkeypatch.setattr(qe, "_in_market_window", lambda dt: True)
    doc = _throttle_doc({"ORB": {"side": "long", "shares": 5}})
    # same fingerprint as last time (nothing structural changed) -- only the interval
    # should decide whether to publish.
    h = str(hash(__import__("json").dumps(qe._publish_fingerprint(doc), sort_keys=True, default=str)))
    now = qe.time.time()
    state = {"last_doc_hash": h, "last_publish": now - 15}   # 15s since last publish
    should, _h, _now = qe._should_publish(state, doc, cfg=qe.DEFAULT_CONFIG)
    assert should is True, ("armed=False + in-session default interval is 60s, but a position "
                            "is open -- must tighten to the 10s ceiling and publish at 15s")


def test_publish_throttle_stays_at_normal_interval_when_flat(monkeypatch):
    monkeypatch.setattr(qe, "_in_market_window", lambda dt: True)
    doc = _throttle_doc({})   # flat
    h = str(hash(__import__("json").dumps(qe._publish_fingerprint(doc), sort_keys=True, default=str)))
    now = qe.time.time()
    state = {"last_doc_hash": h, "last_publish": now - 15}
    should, _h, _now = qe._should_publish(state, doc, cfg=qe.DEFAULT_CONFIG)
    assert should is False, "flat -- the 10s ceiling must not apply, 15s < the normal 60s session interval"


def test_publish_throttle_does_not_apply_off_session_even_with_a_position_open(monkeypatch):
    monkeypatch.setattr(qe, "_in_market_window", lambda dt: False)
    doc = _throttle_doc({"ORB": {"side": "long", "shares": 5}})
    h = str(hash(__import__("json").dumps(qe._publish_fingerprint(doc), sort_keys=True, default=str)))
    now = qe.time.time()
    state = {"last_doc_hash": h, "last_publish": now - 15}
    should, _h, _now = qe._should_publish(state, doc, cfg=qe.DEFAULT_CONFIG)
    assert should is False, "off-session -- the 10s ceiling is scoped to market hours only"


def test_publish_throttle_never_loosens_the_armed_interval(monkeypatch):
    """Armed (PAPER/LIVE) already publishes every 20s -- a position open must not make
    that SLOWER; 10s (<20s) still wins."""
    monkeypatch.setattr(qe, "_in_market_window", lambda dt: True)
    doc = _throttle_doc({"ORB": {"side": "long", "shares": 5}})
    doc["broker"] = {"effective_mode": "PAPER"}
    h = str(hash(__import__("json").dumps(qe._publish_fingerprint(doc), sort_keys=True, default=str)))
    now = qe.time.time()
    state = {"last_doc_hash": h, "last_publish": now - 12}
    should, _h, _now = qe._should_publish(state, doc, cfg=qe.DEFAULT_CONFIG)
    assert should is True, "armed interval is 20s, but a position is open -- 10s ceiling wins"


def test_publish_throttle_worst_case_constant_is_10s():
    assert qe.PUBLISH_INTERVAL_POSITION_OPEN_SEC == 10.0

# -- 2026-09-23 17:00 ET: a restart showed the 16:49 reading as STALE all evening ------------

def test_every_process_reads_once_at_boot_even_with_an_older_persisted_reading(monkeypatch):
    adapter = _FakeBalanceAdapter({"account_id": "a1", "net_liq": 100100.0, "cash": 5000.0})
    monkeypatch.setattr(qe, "_get_broker_adapter", lambda log=print: adapter)
    monkeypatch.setattr(qe, "_EQUITY_BOOT_READ_DONE", False)   # a fresh process
    state = {"equity": {"_epoch": qe.time.time() - 600, "net_liq": 100000.0,
                        "day": "2026-09-23", "first_net_liq_today": 100000.0,
                        "as_of_et": "2026-09-23 16:49:51"}}
    after_close = datetime(2026, 9, 23, 17, 0, 0)
    qe._maybe_read_account_equity(state, _cfg(), after_close, log=NOOP)
    assert adapter.calls == 1, "the boot read happens even off-hours"
    assert state["equity"]["net_liq"] == 100100.0
    assert state["equity"]["first_net_liq_today"] == 100000.0, "same day keeps its baseline"
    qe._maybe_read_account_equity(state, _cfg(), after_close + timedelta(minutes=5), log=NOOP)
    assert adapter.calls == 1, "only ONE boot read; off-hours refreshes stay off"


def test_equity_status_never_stale_while_the_market_is_shut():
    state = {"equity": {"net_liq": 100500.0, "cash": 5000.0,
                        "as_of_et": "2026-09-23 16:49:51", "first_net_liq_today": 100000.0}}
    out = qe._build_equity_status(state, datetime(2026, 9, 23, 21, 0, 0), log=NOOP)
    assert out["stale"] is False
    assert out["note"] is None


def test_equity_status_stale_in_the_market_window_when_reads_stop():
    state = {"equity": {"net_liq": 100500.0, "cash": 5000.0,
                        "as_of_et": "2026-09-24 09:40:00", "first_net_liq_today": 100000.0}}
    out = qe._build_equity_status(state, datetime(2026, 9, 24, 9, 50, 0), log=NOOP)
    assert out["stale"] is True
