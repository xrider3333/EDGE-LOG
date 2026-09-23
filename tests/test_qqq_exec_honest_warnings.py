"""api/qqq_exec.py's "HONEST WARNINGS" build (2026-09-23) -- the owner's screenshot of
the live QQQ tab showed RATIO DRIFT, SLOW LATENCY and NOT READY chips that were all
structurally false alarms for a book that runs signal_source="engine": the ratio is
never used to price anything in that mode, the latency measure was timed from the
signal bar's START (so every 5-minute bar read ~330s "late" by construction), and the
readiness gate's "live parity" check compared against NinjaTrader on a book that has
never had a NinjaTrader fill to compare against. Plus the plain-English rewrite of
Webull's own raw ServerException text (item 2).

No network, no real EDGELOG_HOME: every test builds its own state/cfg dicts and
monkeypatches api.cloud_signal's bar-source attribution rather than touching a real
bar cache.
"""
from datetime import datetime, timedelta

import pytest

from api import qqq_exec as qe
from api import cloud_signal as cs

NOOP = lambda *a, **k: None  # noqa: E731


def _cfg(**overrides):
    cfg = dict(qe.DEFAULT_CONFIG)
    cfg.update(overrides)
    return cfg


# ── item 1a: RATIO DRIFT is not used in engine mode ────────────────────────────────────

def test_ratio_health_not_used_in_engine_mode_even_when_stale_and_drifted():
    """A calibration that would trip BOTH the staleness and drift warnings under the
    old, mode-blind logic must never warn in engine mode -- it is not used to price
    anything there."""
    nowdt = datetime(2026, 9, 23, 10, 0, 0)
    state = {
        "calib": {"ratio": 50.0, "at": "2026-09-23 09:00:00", "source": "yfinance+NQ_10s"},
        "ratio_hist": [{"at": "2026-09-23 08:00:00", "ratio": 40.0}] * 20,
    }
    out = qe._build_ratio_health(state, nowdt, cfg=_cfg(signal_source="engine"), log=NOOP)
    assert out["used"] is False
    assert out["warn"] is False
    assert "not used" in out["note"].lower()
    assert "webull" in out["note"].lower()


def test_ratio_health_default_cfg_none_treated_as_engine():
    """_build_ratio_health(cfg=None) (every pre-2026-09-23 call site) must default to
    the SAME 'engine' assumption _build_price_status already uses -- this book's
    actual, current default -- rather than silently reverting to the old
    always-warn-if-stale behaviour."""
    nowdt = datetime(2026, 9, 23, 10, 0, 0)
    state = {"calib": {"ratio": 50.0, "at": "2026-09-23 01:00:00", "source": "x"},
            "ratio_hist": []}
    out = qe._build_ratio_health(state, nowdt, log=NOOP)
    assert out["used"] is False
    assert out["warn"] is False


def test_ratio_health_ninjatrader_mode_keeps_staleness_warning():
    nowdt = datetime(2026, 9, 23, 10, 0, 0)
    state = {
        "calib": {"ratio": 40.0, "at": "2026-09-23 09:00:00", "source": "x"},  # 60 min stale
        "ratio_hist": [{"at": "2026-09-23 09:00:00", "ratio": 40.0}] * 20,
    }
    out = qe._build_ratio_health(state, nowdt, cfg=_cfg(signal_source="ninjatrader"), log=NOOP)
    assert out["used"] is True
    assert out["warn"] is True
    assert "stale" in out["note"].lower() or "hasn't refreshed" in out["note"].lower()


def test_ratio_health_ninjatrader_mode_healthy_case_unchanged():
    nowdt = datetime(2026, 9, 23, 10, 0, 0)
    state = {
        "calib": {"ratio": 40.0, "at": "2026-09-23 09:59:00", "source": "x"},
        "ratio_hist": [{"at": "2026-09-23 09:59:00", "ratio": 40.0}] * 20,
    }
    out = qe._build_ratio_health(state, nowdt, cfg=_cfg(signal_source="ninjatrader"), log=NOOP)
    assert out["used"] is True
    assert out["warn"] is False
    assert "healthy" in out["note"].lower()


# ── item 1b: after-close latency ────────────────────────────────────────────────────────

class _FixedNow:
    """Patches qe._now_et() to a fixed instant for a deterministic latency_s/
    after_close_s computation."""
    def __init__(self, dt):
        self.dt = dt

    def __call__(self):
        return self.dt


@pytest.fixture(autouse=True)
def _patch_cs_home_for_this_module(tmp_path, monkeypatch):
    """_leg_timeframe_seconds/_bar_close_age go through _cs_module() -> api.cloud_signal
    -- point its DEFAULT_PATHS at a private tmp dir so nothing here can touch the real
    EDGELOG_HOME (CROWN_LEGS/TIMEFRAME_SECONDS themselves are plain in-memory dicts,
    read regardless of paths, so ENGINE_LEG_MAP resolution works with no files at all)."""
    monkeypatch.setattr(cs, "DEFAULT_PATHS", cs._paths(home=str(tmp_path / "cs_home")))


def test_after_close_s_for_5m_leg_orb(tmp_path, monkeypatch):
    """ORB is a 5-minute leg (CROWN_LEGS["ORB_R6"]["timeframe"] == "5m"): an order sent
    32s after the bar OPENED (bar started at 09:30:00, order at 09:30:32) is really
    only 32s after the PREVIOUS bar's close (09:30:00) -- wait, more precisely: fill_dt
    IS the bar's own start, so after_close_s = latency_s - 300 here would be negative
    (32 - 300) if the order beat the bar's own close, which cannot happen in practice --
    use a realistic order time of bar_start + 305s (5s after the bar it opened on
    actually closed) so after_close_s comes out to a clean +5."""
    orders_csv = tmp_path / "orders.csv"
    monkeypatch.setattr(qe, "ORDERS_CSV", str(orders_csv))
    bar_start = datetime(2026, 9, 23, 9, 30, 0)
    order_time = bar_start + timedelta(seconds=305)   # 5s after the 5m bar closed
    monkeypatch.setattr(qe, "_now_et", _FixedNow(order_time))
    qe._record_order("ORB", "ENTER", "long", 5, None, 700.0, "engine_webull", "signal entry",
                     log=NOOP, fill_dt=bar_start, signal_source="engine")
    import csv
    with open(orders_csv, encoding="utf-8", newline="") as f:
        row = list(csv.DictReader(f))[0]
    assert float(row["latency_s"]) == pytest.approx(305.0)
    assert float(row["after_close_s"]) == pytest.approx(5.0)


def test_after_close_s_for_1m_leg_enguq(tmp_path, monkeypatch):
    """ENGUQ is a 1-minute leg: the same 5s-after-close order time now measures as
    latency_s=65 (60 for the bar's own width + 5), after_close_s=5 -- the whole point
    of item 1b (a 1-minute leg's raw latency_s should NOT read like a 5-minute leg's)."""
    orders_csv = tmp_path / "orders.csv"
    monkeypatch.setattr(qe, "ORDERS_CSV", str(orders_csv))
    bar_start = datetime(2026, 9, 23, 9, 30, 0)
    order_time = bar_start + timedelta(seconds=65)
    monkeypatch.setattr(qe, "_now_et", _FixedNow(order_time))
    qe._record_order("ENGUQ", "ENTER", "long", 5, None, 700.0, "engine_webull", "signal entry",
                     log=NOOP, fill_dt=bar_start, signal_source="engine")
    import csv
    with open(orders_csv, encoding="utf-8", newline="") as f:
        row = list(csv.DictReader(f))[0]
    assert float(row["latency_s"]) == pytest.approx(65.0)
    assert float(row["after_close_s"]) == pytest.approx(5.0)


def test_after_close_s_blank_for_ninjatrader_mode(tmp_path, monkeypatch):
    """fill_dt in ninjatrader mode is a real fill time, not a bar start -- there is no
    bar to measure "after close" against, so the new column must stay blank (never a
    fabricated number)."""
    orders_csv = tmp_path / "orders.csv"
    monkeypatch.setattr(qe, "ORDERS_CSV", str(orders_csv))
    fill_dt = datetime(2026, 9, 23, 9, 30, 5)
    monkeypatch.setattr(qe, "_now_et", _FixedNow(fill_dt + timedelta(seconds=2)))
    qe._record_order("ORB", "ENTER", "long", 5, 20000.0, 700.0, "webull_quote", "signal entry",
                     log=NOOP, fill_dt=fill_dt, signal_source="ninjatrader")
    import csv
    with open(orders_csv, encoding="utf-8", newline="") as f:
        row = list(csv.DictReader(f))[0]
    assert row["after_close_s"] == ""
    assert float(row["latency_s"]) == pytest.approx(2.0)


def test_after_close_s_blank_when_leg_has_no_live_timeframe_mapping():
    orders_csv_tf = qe._leg_timeframe_seconds("NOT_A_REAL_LEG", log=NOOP)
    assert orders_csv_tf is None


def test_build_latency_after_close_stats_and_warn_threshold():
    """p95 after-close under AFTER_CLOSE_WARN_SEC (60s) must not warn; over it must."""
    orders_ok = [{"after_close_s": str(v)} for v in [5, 10, 15, 20, 25, 30, 35, 40, 45, 50]]
    out_ok = qe._build_latency(orders_ok, log=NOOP)
    assert out_ok["after_close"]["n"] == 10
    assert out_ok["after_close"]["warn"] is False

    orders_slow = [{"after_close_s": str(v)} for v in [5, 10, 61, 70, 80, 90, 95, 99, 100, 120]]
    out_slow = qe._build_latency(orders_slow, log=NOOP)
    assert out_slow["after_close"]["p95_s"] > qe.AFTER_CLOSE_WARN_SEC
    assert out_slow["after_close"]["warn"] is True


def test_build_latency_after_close_empty_on_a_pure_ninjatrader_day():
    orders = [{"latency_s": "1.2", "after_close_s": ""}, {"latency_s": "0.8", "after_close_s": ""}]
    out = qe._build_latency(orders, log=NOOP)
    assert out["n"] == 2                      # the OLD measure is untouched
    assert out["after_close"]["n"] == 0
    assert out["after_close"]["warn"] is False


# ── item 1c: PRICE SOURCE ages off the bar's CLOSE, not its START ──────────────────────

def test_bar_close_age_adds_back_the_timeframe(monkeypatch):
    now = 1_000_000.0
    monkeypatch.setattr(qe.time, "time", lambda: now)
    # a 5-minute bar that opened 301s ago closed just 1s ago.
    bs = {"5m": {"source": "webull", "newest_epoch": now - 301, "checked_at": "x"}}
    age = qe._bar_close_age("5m", bar_source=bs, log=NOOP)
    assert age == pytest.approx(1.0)


def test_bar_close_age_none_when_timeframe_missing():
    assert qe._bar_close_age("5m", bar_source={}, log=NOOP) is None


def test_build_price_status_reads_bar_close_not_bar_start(monkeypatch):
    """THE BUG: a 5-minute bar that just closed used to read as ~300s 'behind' (the
    owner's '389s behind' screenshot). It must now read close to the real fetch delay
    instead."""
    monkeypatch.setattr(qe, "_qqq_stream_instance", lambda: None)
    now = 2_000_000.0
    monkeypatch.setattr(qe.time, "time", lambda: now)
    bs = {"5m": {"source": "webull", "newest_epoch": now - 304, "checked_at": "2026-09-23T10:00:00"}}
    monkeypatch.setattr(cs, "read_bar_source", lambda paths=None: bs)
    out = qe._build_price_status(_cfg(signal_source="engine"), {}, log=NOOP)
    assert out["source"] == "WEBULL"
    assert out["age_sec"] == pytest.approx(4, abs=1)


def test_build_price_status_prefers_a_fresh_live_stream(monkeypatch):
    class _Stream:
        def is_fresh(self):
            return True

        def last_trade(self):
            return {"price": 512.3, "epoch": 1, "age": 2.5}

    monkeypatch.setattr(qe, "_qqq_stream_instance", lambda: _Stream())
    out = qe._build_price_status(_cfg(signal_source="engine"), {}, log=NOOP)
    assert out["source"] == "WEBULL"
    assert out["age_sec"] == round(2.5)   # Python 3 banker's rounding -> 2


def test_build_price_status_falls_back_when_stream_read_raises(monkeypatch):
    class _BoomStream:
        def is_fresh(self):
            raise RuntimeError("boom")

    monkeypatch.setattr(qe, "_qqq_stream_instance", lambda: _BoomStream())
    now = 3_000_000.0
    monkeypatch.setattr(qe.time, "time", lambda: now)
    bs = {"1m": {"source": "yahoo", "newest_epoch": now - 65, "checked_at": "x"}}
    monkeypatch.setattr(cs, "read_bar_source", lambda paths=None: bs)
    out = qe._build_price_status(_cfg(signal_source="engine"), {}, log=NOOP)
    assert out["source"] == "YAHOO"
    assert out["age_sec"] == pytest.approx(5, abs=1)


# ── item 1d: NOT READY re-based on Webull (broker) parity ──────────────────────────────

def test_readiness_missing_text_says_webull_not_ninjatrader():
    feed_days = [{"valid": True, "uptime_pct": 1.0}] * 10
    broker_parity = {"checked": 0, "failed": 0}
    reprice = {"total": 0, "coverage_pct": 1.0}
    out = qe._build_readiness(feed_days, broker_parity, reprice, {"events": []}, log=NOOP)
    joined = " ".join(out["missing"]).lower()
    assert "webull" in joined
    assert "ninjatrader" not in joined
    assert out["live_parity_checked"] == 0


def test_readiness_ready_when_broker_parity_clears_the_bar():
    feed_days = [{"valid": True, "uptime_pct": 1.0}] * 10
    broker_parity = {"checked": qe.DAYS_REQUIRED, "failed": 0}
    reprice = {"total": 5, "coverage_pct": 1.0}
    out = qe._build_readiness(feed_days, broker_parity, reprice, {"events": []}, log=NOOP)
    assert out["ready"] is True
    assert out["live_parity_checked"] == qe.DAYS_REQUIRED


def test_readiness_failed_broker_parity_reported_against_webull():
    feed_days = [{"valid": True, "uptime_pct": 1.0}] * 10
    broker_parity = {"checked": 3, "failed": 1}
    reprice = {"total": 3, "coverage_pct": 1.0}
    out = qe._build_readiness(feed_days, broker_parity, reprice, {"events": []}, log=NOOP)
    assert out["ready"] is False
    assert any("webull" in m.lower() for m in out["missing"])


# ── item 2: plain-English Webull error codes ────────────────────────────────────────────

_RAW_SIDE_MISMATCH = ("ServerException: HTTP Status: 417, Code: "
                     "OPENAPI_ORDER_SIDE_NOT_MATCH_WITH_POSITION, Msg: This order will "
                     "generate new short stock positions..., RequestID: abc123")
_RAW_SHORT_NOT_ALLOWED = ("ServerException: HTTP Status: 417, Code: "
                          "OPENAPI_GENERATE_NEW_SHORT_POSITION, Msg: This order will "
                          "generate new short stock positions..., RequestID: def456")


def test_plain_broker_error_known_code_side_mismatch():
    out = qe._plain_broker_error(_RAW_SIDE_MISMATCH)
    assert out == ("Webull refused: the account already holds the opposite side of QQQ "
                   "from another strategy")


def test_plain_broker_error_known_code_short_not_allowed():
    out = qe._plain_broker_error(_RAW_SHORT_NOT_ALLOWED)
    assert out == "Webull refused: this account type cannot short"


def test_plain_broker_error_unknown_code_gets_honest_fallback():
    raw = "ServerException: HTTP Status: 400, Code: OPENAPI_SOMETHING_NEW, Msg: x"
    out = qe._plain_broker_error(raw)
    assert out == "Webull refused the order (code OPENAPI_SOMETHING_NEW)"


def test_plain_broker_error_no_code_passes_through_unchanged():
    raw = "this strategy already has an open position"
    assert qe._plain_broker_error(raw) == raw


def test_plain_broker_error_empty_is_none():
    assert qe._plain_broker_error("") is None
    assert qe._plain_broker_error(None) is None


def test_build_broker_status_publishes_plain_fields_alongside_raw(monkeypatch):
    class _FakeAdapter:
        def status(self):
            return {"requested_mode": "PAPER", "effective_mode": "PAPER",
                    "mode_reason": "x", "environment": "sandbox",
                    "paper_credentials_present": True, "live_credentials_present": False,
                    "live_armed": False, "kill_file_present": False, "halted": False,
                    "halt_reason": None, "last_error": _RAW_SIDE_MISMATCH,
                    "last_order": {"leg": "NOISE", "symbol": "QQQ", "side": "SELL",
                                  "qty": 10, "intent": "OPEN", "mode": "PAPER",
                                  "ok": False, "sent": True, "error": _RAW_SIDE_MISMATCH,
                                  "ts": 1234567890.0},
                    "daily_pnl": 0.0, "open_legs": []}

    monkeypatch.setattr(qe, "_get_broker_adapter", lambda log=print: _FakeAdapter())
    out = qe._build_broker_status(log=NOOP)
    assert out["last_error"] == _RAW_SIDE_MISMATCH, "raw text must still travel for a details toggle"
    assert out["last_error_plain"] == ("Webull refused: the account already holds the "
                                       "opposite side of QQQ from another strategy")
    assert out["last_order"]["reason"] == _RAW_SIDE_MISMATCH
    assert out["last_order"]["reason_plain"] == out["last_error_plain"], (
        "the owner's screenshot showed the SAME event as both 'last order' and 'last "
        "error' -- both plain rewrites must agree so the web tab can de-duplicate them")

def test_plain_error_matches_the_real_live_code_with_its_intent_suffix():
    # The exact text the box logged on 2026-09-23 -- Webull appends _OPEN to the code.
    raw = ("ServerException: HTTP Status: 417, Code: OPENAPI_ORDER_SIDE_NOT_MATCH_WITH_POSITION_OPEN, "
           "Msg: Please close your existing long positions of this security before placing a "
           "short order., RequestID: 1b6a5d44-c9f1-4afa-ab66-748672000000")
    assert qe._plain_broker_error(raw) == qe.WEBULL_ERROR_SENTENCES[
        "OPENAPI_ORDER_SIDE_NOT_MATCH_WITH_POSITION"]


def test_plain_error_prefix_match_needs_an_underscore_boundary():
    raw = "ServerException: HTTP Status: 417, Code: OPENAPI_GENERATE_NEW_SHORT_POSITIONX, Msg: x"
    assert qe._plain_broker_error(raw) == "Webull refused the order (code OPENAPI_GENERATE_NEW_SHORT_POSITIONX)"
