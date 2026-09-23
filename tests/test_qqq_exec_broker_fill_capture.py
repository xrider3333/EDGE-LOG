"""api/qqq_exec.py's broker order-status FILL-PRICE CAPTURE (feature #57, 2026-09-22;
DEFERRED 2026-09-22 review).

WHY. broker_orders.csv's broker_fill_px/slippage columns existed since the broker
mirror shipped (2026-09-13) but were ALWAYS blank for a real send:
_extract_broker_fill_price only ever reads the place_order() ACK -- the response
captured at the instant the order was submitted -- and Webull documents that ack's
filled_price as "may be zero or null" before the order has actually executed. Nothing
previously asked again.

FIRST CUT vs. DEFERRED. The first cut called _query_broker_fill directly from
_mirror_to_broker, synchronously, once, right after the send. Review caught two real
problems: (a) a market order is rarely filled in the few milliseconds before the very
next call, so the one-shot query almost always came back empty and nothing ever asked
again -- the feature did nothing in practice; (b) it could stall the NEXT leg's send by
up to ORDER_STATUS_HARD_TIMEOUT_SEC when two legs act on the same tick (this book's own
trades do). So capture is now QUEUED (_queue_broker_fill_capture, a pure state write
with no network call, called from _mirror_to_broker) and serviced later from tick()
(_maybe_capture_broker_fills), modelled directly on the existing broker re-send queue
(_queue_broker_resend / _maybe_resend_broker_orders).

These tests stub api.webull_orders.OrderAdapter.order_status directly (no real SDK, no
network, no real EDGELOG_HOME) and a controllable clock (qe.time.time, the same
monkeypatch idiom tests/test_qqq_exec_broker_resend.py uses) to drive the queue through
its delay/retry/give-up timeline without a single real sleep.
"""
import concurrent.futures as cf
import csv
import json
import os
from unittest.mock import MagicMock

from api import qqq_exec as qe
from api import webull_orders as WO

NOOP = lambda *a, **k: None  # noqa: E731


# ── fixtures / helpers (mirrors tests/test_qqq_exec_broker_mirror.py's own) ─────────

def _broker_cfg(tmp_path, mode="PAPER"):
    cfg = WO.load_config("__no_such_file__")   # defaults only, no real file on disk
    cfg["mode"] = mode
    cfg["rails"]["session_start"] = "00:00"
    cfg["rails"]["session_end"] = "23:59"
    cfg["state_path"] = str(tmp_path / "wo_state.json")
    cfg["paper_keys_path"] = str(tmp_path / "paper_keys.json")
    cfg["live_keys_path"] = str(tmp_path / "live_keys.json")
    cfg["arm_live_file"] = str(tmp_path / "ARM_LIVE")
    cfg["kill_file"] = str(tmp_path / "WO_KILL")
    return cfg


def _paper_adapter(tmp_path, monkeypatch):
    cfg = _broker_cfg(tmp_path, mode="PAPER")
    with open(cfg["paper_keys_path"], "w", encoding="utf-8") as f:
        json.dump({"app_key": "AK", "app_secret": "AS"}, f)
    adapter = WO.OrderAdapter(config=cfg, log=NOOP)
    client = MagicMock()
    client.account_v2.get_account_list.return_value.json.return_value = {
        "data": [{"account_id": "ACCT1", "account_class": "INDIVIDUAL_MARGIN"}]}
    client.order_v3.place_order.return_value.json.return_value = {"status": "SUBMITTED"}
    client.account_v2.get_account_position.return_value.json.return_value = {"data": []}
    monkeypatch.setattr(adapter, "_build_client", lambda mode: client)
    return adapter, client


def _patch_qqq_paths(tmp_path, monkeypatch):
    out = tmp_path / "qqq_out"
    monkeypatch.setattr(qe, "OUT_DIR", str(out))
    monkeypatch.setattr(qe, "ORDERS_CSV", str(out / "orders.csv"))
    monkeypatch.setattr(qe, "TRADES_CSV", str(out / "trades.csv"))
    monkeypatch.setattr(qe, "BROKER_ORDERS_CSV", str(out / "broker_orders.csv"))
    return out


def _patch_broker_adapter(monkeypatch, adapter):
    monkeypatch.setattr(qe, "_get_broker_adapter", lambda log=print: adapter)


def _fake_clock(monkeypatch, start=1_000_000.0):
    clock = [start]
    monkeypatch.setattr(qe.time, "time", lambda: clock[0])
    return clock


def _read_csv(path):
    with open(path, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


NOWDT = None  # _maybe_capture_broker_fills does not read nowdt today; kept for the
             # same call shape as _maybe_resend_broker_orders/_maybe_run_broker_reconcile


class _StubAdapter:
    """A minimal fake with just enough surface for _query_broker_fill -- no SDK, no
    OrderAdapter machinery."""
    def __init__(self, status_fn):
        self._status_fn = status_fn
        self.calls = 0

    def order_status(self, signal_id, account_id=None):
        self.calls += 1
        return self._status_fn(signal_id, account_id)


class _RaisingAdapter:
    def order_status(self, signal_id, account_id=None):
        raise RuntimeError("SDK exploded")


# ── _query_broker_fill: direct unit tests, stub adapter, no network (unchanged by the
# deferred rework -- this function's own contract did not change, only its caller) ──

def test_query_broker_fill_success_returns_price():
    resp = {"orders": [{"client_order_id": "X", "status": "FILLED", "filled_price": "501.50"}]}
    adapter = _StubAdapter(lambda sig, acct: {"ok": True, "response": resp, "client_order_id": "X"})
    px, note = qe._query_broker_fill(adapter, "X", account_id="A1", log=NOOP)
    assert px == 501.50
    assert note is None


def test_query_broker_fill_no_price_yet_is_not_treated_as_an_error():
    resp = {"orders": [{"client_order_id": "X", "status": "SUBMITTED", "filled_price": None}]}
    adapter = _StubAdapter(lambda sig, acct: {"ok": True, "response": resp, "client_order_id": "X"})
    px, note = qe._query_broker_fill(adapter, "X", log=NOOP)
    assert px is None
    assert "SUBMITTED" in note


def test_query_broker_fill_not_ok_response_returns_its_reason():
    adapter = _StubAdapter(lambda sig, acct: {"ok": False, "reason": "no PAPER client"})
    px, note = qe._query_broker_fill(adapter, "X", log=NOOP)
    assert px is None
    assert note == "no PAPER client"


def test_query_broker_fill_exception_is_caught_never_raises():
    px, note = qe._query_broker_fill(_RaisingAdapter(), "X", log=NOOP)
    assert px is None
    assert "SDK exploded" in note


def test_query_broker_fill_missing_order_status_method_is_caught():
    """A fake/test adapter with no order_status attribute at all must degrade the same
    as any other failure -- never an uncaught AttributeError reaching the caller."""
    class NoStatusMethod:
        pass
    px, note = qe._query_broker_fill(NoStatusMethod(), "X", log=NOOP)
    assert px is None
    assert note is not None


def test_query_broker_fill_timeout_is_caught_and_bounded(monkeypatch):
    """The SDK's own timeouts are not reliably honoured (same precaution as
    _reconcile_with_timeout) -- a call that never returns must still come back within
    ORDER_STATUS_HARD_TIMEOUT_SEC, not hang the caller."""
    class _NeverDoneFuture:
        def result(self, timeout=None):
            raise cf.TimeoutError()

    class _Executor:
        def submit(self, fn, *a, **k):
            return _NeverDoneFuture()

    monkeypatch.setattr(qe, "_order_status_executor", _Executor())
    px, note = qe._query_broker_fill(_StubAdapter(lambda s, a: {"ok": True}), "X", log=NOOP)
    assert px is None
    assert "timed out" in note


# ── _mirror_to_broker: queues a job, NEVER queries inline ───────────────────────────

def test_mirror_to_broker_queues_a_job_instead_of_querying_inline(tmp_path, monkeypatch):
    """The core of the deferred redesign: a real accepted send must record a capture
    job in state and must NOT touch order_status at all during _mirror_to_broker
    itself -- proves the send path truly cannot be stalled by a status query."""
    _patch_qqq_paths(tmp_path, monkeypatch)
    adapter, client = _paper_adapter(tmp_path, monkeypatch)
    _patch_broker_adapter(monkeypatch, adapter)
    state = {}

    qe._mirror_to_broker(state, leg="ORB", side="long", shares=5, shadow_px=500.0,
                         intent="OPEN", ts="2026-09-22 09:31:00", log=NOOP)

    assert client.order_v3.get_order_detail.call_count == 0, \
        "the order path must never call order_status inline"
    jobs = state.get("_broker_fill_capture") or {}
    assert "ORB:OPEN" in jobs
    job = jobs["ORB:OPEN"]
    assert job["leg"] == "ORB" and job["intent"] == "OPEN"
    assert job["shadow_px"] == 500.0
    assert job["tries"] == 0
    assert job["signal_id"]

    rows = _read_csv(qe.BROKER_ORDERS_CSV)
    assert rows[-1]["broker_fill_px"] == ""  # nothing captured yet -- queued, not asked


def test_mirror_to_broker_off_mode_never_queues(tmp_path, monkeypatch):
    _patch_qqq_paths(tmp_path, monkeypatch)
    adapter = WO.OrderAdapter(config=_broker_cfg(tmp_path, mode="OFF"), log=NOOP)
    _patch_broker_adapter(monkeypatch, adapter)
    state = {}

    qe._mirror_to_broker(state, leg="ORB", side="long", shares=5, shadow_px=500.0,
                         intent="OPEN", ts="2026-09-22 09:31:00", log=NOOP)

    assert not state.get("_broker_fill_capture")


def test_mirror_to_broker_blocked_order_never_queues(tmp_path, monkeypatch):
    _patch_qqq_paths(tmp_path, monkeypatch)
    cfg = _broker_cfg(tmp_path, mode="PAPER")
    cfg["rails"]["max_shares_per_leg"] = 1
    adapter = WO.OrderAdapter(config=cfg, log=NOOP)
    _patch_broker_adapter(monkeypatch, adapter)
    state = {}

    qe._mirror_to_broker(state, leg="ORB", side="long", shares=5, shadow_px=500.0,
                         intent="OPEN", ts="2026-09-22 09:31:00", log=NOOP)

    rows = _read_csv(qe.BROKER_ORDERS_CSV)
    assert rows[-1]["mode"] == "BLOCKED"
    assert not state.get("_broker_fill_capture")


def test_mirror_to_broker_failed_placement_never_queues(tmp_path, monkeypatch):
    _patch_qqq_paths(tmp_path, monkeypatch)
    adapter, client = _paper_adapter(tmp_path, monkeypatch)
    client.order_v3.place_order.side_effect = RuntimeError("network exploded")
    _patch_broker_adapter(monkeypatch, adapter)
    state = {}

    qe._mirror_to_broker(state, leg="ORB", side="long", shares=5, shadow_px=500.0,
                         intent="OPEN", ts="2026-09-22 09:31:00", log=NOOP)

    rows = _read_csv(qe.BROKER_ORDERS_CSV)
    assert rows[-1]["ok"] == "False"
    assert not state.get("_broker_fill_capture")


def test_mirror_to_broker_close_also_queues_a_job(tmp_path, monkeypatch):
    """Both OPEN and CLOSE sends get a job -- a different key each, so neither
    overwrites the other."""
    _patch_qqq_paths(tmp_path, monkeypatch)
    adapter, client = _paper_adapter(tmp_path, monkeypatch)
    _patch_broker_adapter(monkeypatch, adapter)
    state = {}

    qe._mirror_to_broker(state, leg="ORB", side="long", shares=5, shadow_px=500.0,
                         intent="OPEN", ts="2026-09-22 09:31:00", log=NOOP)
    qe._mirror_to_broker(state, leg="ORB", side="long", shares=5, shadow_px=506.0,
                         intent="CLOSE", ts="2026-09-22 09:31:00", seq=1, log=NOOP)

    jobs = state.get("_broker_fill_capture") or {}
    assert set(jobs.keys()) == {"ORB:OPEN", "ORB:CLOSE"}
    assert jobs["ORB:CLOSE"]["shadow_px"] == 506.0


# ── _maybe_capture_broker_fills: the deferred queue itself ──────────────────────────

def _seed_broker_row(path, signal_id, shadow_px=500.0):
    """Writes one broker_orders.csv row shaped exactly like _mirror_to_broker's own,
    with broker_fill_px/slippage/reason still blank -- the state _update_broker_order_row
    is expected to find and patch in place."""
    row = {c: "" for c in qe.BROKER_ORDER_COLS}
    row.update({"ts_et": "2026-09-22 09:31:00", "leg": "ORB", "intent": "OPEN",
               "side": "BUY", "shares": 5, "signal_id": signal_id,
               "client_order_id": signal_id, "mode": "PAPER", "ok": "True", "sent": "True",
               "shadow_px": shadow_px, "duplicate": "False"})
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=qe.BROKER_ORDER_COLS)
        w.writeheader()
        w.writerow(row)


def test_capture_waits_for_first_delay_before_asking(tmp_path, monkeypatch):
    out = _patch_qqq_paths(tmp_path, monkeypatch)
    clock = _fake_clock(monkeypatch)
    _seed_broker_row(out / "broker_orders.csv", "sig-1")
    stub = _StubAdapter(lambda s, a: {"ok": True, "response": {}, "client_order_id": s})
    _patch_broker_adapter(monkeypatch, stub)
    state = {}
    qe._queue_broker_fill_capture(state, leg="ORB", intent="OPEN", signal_id="sig-1",
                                  account_id="A1", shadow_px=500.0, log=NOOP)

    qe._maybe_capture_broker_fills(state, {}, NOWDT, True, log=NOOP)

    assert stub.calls == 0, "must not ask before BROKER_FILL_CAPTURE_FIRST_DELAY_SEC"
    assert "ORB:OPEN" in state["_broker_fill_capture"]


def test_capture_fills_on_a_later_tick_and_writes_the_row(tmp_path, monkeypatch):
    out = _patch_qqq_paths(tmp_path, monkeypatch)
    clock = _fake_clock(monkeypatch)
    csv_path = out / "broker_orders.csv"
    _seed_broker_row(csv_path, "sig-1", shadow_px=500.0)
    resp = {"orders": [{"client_order_id": "sig-1", "status": "FILLED", "filled_price": "501.50"}]}
    stub = _StubAdapter(lambda s, a: {"ok": True, "response": resp, "client_order_id": s})
    _patch_broker_adapter(monkeypatch, stub)
    state = {}
    qe._queue_broker_fill_capture(state, leg="ORB", intent="OPEN", signal_id="sig-1",
                                  account_id="A1", shadow_px=500.0, log=NOOP)

    clock[0] += qe.BROKER_FILL_CAPTURE_FIRST_DELAY_SEC + 0.1
    qe._maybe_capture_broker_fills(state, {}, NOWDT, True, log=NOOP)

    assert stub.calls == 1
    assert "ORB:OPEN" not in (state.get("_broker_fill_capture") or {}), \
        "a resolved job must be popped from the queue"
    rows = _read_csv(csv_path)
    assert rows[-1]["broker_fill_px"] == "501.5"
    assert float(rows[-1]["slippage"]) == 1.5


def test_capture_retries_are_spaced_then_gives_up_and_records_reason(tmp_path, monkeypatch):
    out = _patch_qqq_paths(tmp_path, monkeypatch)
    clock = _fake_clock(monkeypatch)
    csv_path = out / "broker_orders.csv"
    _seed_broker_row(csv_path, "sig-1", shadow_px=500.0)
    resp = {"orders": [{"status": "SUBMITTED", "filled_price": None}]}
    stub = _StubAdapter(lambda s, a: {"ok": True, "response": resp, "client_order_id": s})
    _patch_broker_adapter(monkeypatch, stub)
    state = {}
    qe._queue_broker_fill_capture(state, leg="ORB", intent="OPEN", signal_id="sig-1",
                                  account_id="A1", shadow_px=500.0, log=NOOP)

    # first attempt, after the initial delay -- still no fill.
    clock[0] += qe.BROKER_FILL_CAPTURE_FIRST_DELAY_SEC + 0.1
    qe._maybe_capture_broker_fills(state, {}, NOWDT, True, log=NOOP)
    assert stub.calls == 1
    assert "ORB:OPEN" in state["_broker_fill_capture"], "not filled yet -- must stay queued"
    assert state["_broker_fill_capture"]["ORB:OPEN"]["tries"] == 1

    # too soon for a second try -- the retry gap must be respected.
    clock[0] += 1.0
    qe._maybe_capture_broker_fills(state, {}, NOWDT, True, log=NOOP)
    assert stub.calls == 1, "must not retry before BROKER_FILL_CAPTURE_RETRY_GAP_SEC"

    # the gap has passed -- a second attempt happens.
    clock[0] += qe.BROKER_FILL_CAPTURE_RETRY_GAP_SEC
    qe._maybe_capture_broker_fills(state, {}, NOWDT, True, log=NOOP)
    assert stub.calls == 2

    # past the give-up window -- the job is dropped and the CSV row explains why.
    clock[0] += qe.BROKER_FILL_CAPTURE_MAX_AGE_SEC
    qe._maybe_capture_broker_fills(state, {}, NOWDT, True, log=NOOP)
    assert "ORB:OPEN" not in state.get("_broker_fill_capture", {})
    rows = _read_csv(csv_path)
    assert rows[-1]["broker_fill_px"] == ""
    assert rows[-1]["reason"] != ""

    # once given up, further ticks touch nothing more (queue is empty).
    calls_before = stub.calls
    clock[0] += 100
    qe._maybe_capture_broker_fills(state, {}, NOWDT, True, log=NOOP)
    assert stub.calls == calls_before


def test_capture_never_raises_when_the_query_blows_up(tmp_path, monkeypatch):
    out = _patch_qqq_paths(tmp_path, monkeypatch)
    clock = _fake_clock(monkeypatch)
    _seed_broker_row(out / "broker_orders.csv", "sig-1")
    _patch_broker_adapter(monkeypatch, _RaisingAdapter())
    state = {}
    qe._queue_broker_fill_capture(state, leg="ORB", intent="OPEN", signal_id="sig-1",
                                  account_id="A1", shadow_px=500.0, log=NOOP)
    clock[0] += qe.BROKER_FILL_CAPTURE_FIRST_DELAY_SEC + 0.1

    qe._maybe_capture_broker_fills(state, {}, NOWDT, True, log=NOOP)   # must not raise

    assert "ORB:OPEN" in state["_broker_fill_capture"], "a query failure retries, not gives up early"


def test_capture_adapter_unavailable_never_raises(tmp_path, monkeypatch):
    _patch_qqq_paths(tmp_path, monkeypatch)
    clock = _fake_clock(monkeypatch)
    def boom(log=print):
        raise RuntimeError("adapter unavailable")
    monkeypatch.setattr(qe, "_get_broker_adapter", boom)
    state = {}
    qe._queue_broker_fill_capture(state, leg="ORB", intent="OPEN", signal_id="sig-1",
                                  account_id="A1", shadow_px=500.0, log=NOOP)
    clock[0] += 100

    qe._maybe_capture_broker_fills(state, {}, NOWDT, True, log=NOOP)   # must not raise

    assert "ORB:OPEN" in state["_broker_fill_capture"], "an unavailable adapter must not drop the job"


def test_capture_services_one_job_per_tick(tmp_path, monkeypatch):
    out = _patch_qqq_paths(tmp_path, monkeypatch)
    clock = _fake_clock(monkeypatch)
    _seed_broker_row(out / "broker_orders.csv", "sig-open")
    resp = {"orders": [{"status": "SUBMITTED", "filled_price": None}]}
    stub = _StubAdapter(lambda s, a: {"ok": True, "response": resp, "client_order_id": s})
    _patch_broker_adapter(monkeypatch, stub)
    state = {}
    qe._queue_broker_fill_capture(state, leg="ORB", intent="OPEN", signal_id="sig-open",
                                  account_id="A1", shadow_px=500.0, log=NOOP)
    qe._queue_broker_fill_capture(state, leg="ENGUQ", intent="OPEN", signal_id="sig-open2",
                                  account_id="A1", shadow_px=700.0, log=NOOP)
    clock[0] += qe.BROKER_FILL_CAPTURE_FIRST_DELAY_SEC + 0.1

    qe._maybe_capture_broker_fills(state, {}, NOWDT, True, log=NOOP)

    assert stub.calls == 1, "only one job's SDK call may happen per tick"
    tries = [state["_broker_fill_capture"][k]["tries"] for k in state["_broker_fill_capture"]]
    assert sorted(tries) == [0, 1], "exactly one job advanced, the other untouched"


def test_capture_give_ups_are_not_limited_to_one_per_tick(tmp_path, monkeypatch):
    """Give-up bookkeeping is local (no network) -- unlike the one live SDK call per
    tick, every job that has already aged out clears in the same tick, mirroring
    _maybe_resend_broker_orders' own give-up handling."""
    out = _patch_qqq_paths(tmp_path, monkeypatch)
    clock = _fake_clock(monkeypatch)
    _seed_broker_row(out / "broker_orders.csv", "sig-a")
    stub = _StubAdapter(lambda s, a: {"ok": True, "response": {}, "client_order_id": s})
    _patch_broker_adapter(monkeypatch, stub)
    state = {}
    qe._queue_broker_fill_capture(state, leg="ORB", intent="OPEN", signal_id="sig-a",
                                  account_id="A1", shadow_px=500.0, log=NOOP)
    qe._queue_broker_fill_capture(state, leg="ENGUQ", intent="OPEN", signal_id="sig-b",
                                  account_id="A1", shadow_px=700.0, log=NOOP)
    clock[0] += qe.BROKER_FILL_CAPTURE_MAX_AGE_SEC + 1.0

    qe._maybe_capture_broker_fills(state, {}, NOWDT, True, log=NOOP)

    assert state.get("_broker_fill_capture") == {}, "both stale jobs must be cleared in one tick"
    assert stub.calls == 0, "a job that is already given up must never even be queried"


# ── restart survival ─────────────────────────────────────────────────────────────────

def test_capture_queue_survives_a_state_json_round_trip(tmp_path, monkeypatch):
    """The queue lives in the SAME `state` dict qqq_exec already persists whole to
    state.json on every tick -- proves it comes back intact after a save/load cycle,
    the same way state["_broker_resend"] already does (see the module's own claim in
    the "broker FILL CAPTURE, deferred" section comment)."""
    path = tmp_path / "state.json"
    state = {"legs": {}}
    qe._queue_broker_fill_capture(state, leg="ORB", intent="OPEN", signal_id="sig-1",
                                  account_id="A1", shadow_px=500.0, log=NOOP)
    qe.save_state(state, path=str(path), log=NOOP)

    reloaded = qe.load_state(path=str(path), log=NOOP)

    job = (reloaded.get("_broker_fill_capture") or {}).get("ORB:OPEN")
    assert job is not None
    assert job["signal_id"] == "sig-1"
    assert job["shadow_px"] == 500.0
    assert job["tries"] == 0


# ── _replace_with_retry: the ONE shared atomic-swap helper (2026-09-22 review) ──────
# WHY THIS SECTION EXISTS: _update_broker_order_row originally rewrote broker_orders.csv
# with a plain `open(path, "w")` straight over the live ledger -- exactly the failure
# class (a crash/kill/disk-hiccup/reader-lock mid-write truncating a shared CSV) that
# already garbled the QQQ bar cache and blocked every push gate (see
# tests/test_qqq_cache_atomic.py). save_state already had the fix for this shape
# (unique temp name, fsync, retry-swap) inline; it is now factored out into
# _replace_with_retry so BOTH callers share it instead of each growing their own retry
# loop -- the same pattern tools/qqq_paper.py's own _replace_with_retry already
# established for the QQQ bar caches.

def test_replace_with_retry_succeeds_after_transient_permission_errors(tmp_path, monkeypatch):
    """A reader's hold is milliseconds -- the common case must ride it out and land."""
    dst = tmp_path / "broker_orders.csv"
    dst.write_text("old", encoding="utf-8")
    tmp = tmp_path / "broker_orders.csv.tmp"
    tmp.write_text("new", encoding="utf-8")
    real_replace = qe.os.replace
    calls = {"n": 0}

    def flaky(src, dst_):
        calls["n"] += 1
        if calls["n"] <= 3:
            raise PermissionError(32, "The process cannot access the file")
        return real_replace(src, dst_)

    monkeypatch.setattr(qe.os, "replace", flaky)
    monkeypatch.setattr(qe.time, "sleep", lambda s: None)

    ok = qe._replace_with_retry(str(tmp), str(dst), log=None, retries=10)

    assert ok is True
    assert calls["n"] == 4, "must retry exactly the failing attempts, not more"
    assert dst.read_text(encoding="utf-8") == "new"
    assert not tmp.exists(), "the source is gone once os.replace actually succeeds"


def test_replace_with_retry_gives_up_cleans_tmp_when_not_keeping(tmp_path, monkeypatch):
    """_update_broker_order_row's own contract: a persistently failed swap must not
    leave a stray .tmp beside the live ledger forever."""
    dst = tmp_path / "broker_orders.csv"
    dst.write_text("old", encoding="utf-8")
    before = dst.read_bytes()
    tmp = tmp_path / "broker_orders.csv.tmp"
    tmp.write_text("new", encoding="utf-8")
    monkeypatch.setattr(qe.os, "replace",
                        lambda s, d: (_ for _ in ()).throw(PermissionError(32, "locked")))
    monkeypatch.setattr(qe.time, "sleep", lambda s: None)
    logged = []

    ok = qe._replace_with_retry(str(tmp), str(dst), log=logged.append,
                                what="broker_orders.csv row update", retries=3,
                                keep_tmp_on_failure=False)

    assert ok is False
    assert dst.read_bytes() == before, "a persistently failed rename must not touch the destination"
    assert not tmp.exists(), "the abandoned .tmp must be cleaned up when keep_tmp_on_failure=False"
    assert len(logged) == 1, "exactly one log line for the whole exhausted retry"
    assert "broker_orders.csv row update" in logged[0]


def test_replace_with_retry_keeps_tmp_when_asked_to(tmp_path, monkeypatch):
    """save_state's own contract is the OPPOSITE of _update_broker_order_row's: a
    persistently-locked state.json swap must leave the .tmp on disk as a recoverable
    copy, never delete it -- state.json is the sole record of open positions."""
    dst = tmp_path / "state.json"
    dst.write_text("old", encoding="utf-8")
    tmp = tmp_path / "state.json.tmp"
    tmp.write_text("new", encoding="utf-8")
    monkeypatch.setattr(qe.os, "replace",
                        lambda s, d: (_ for _ in ()).throw(PermissionError(32, "locked")))
    monkeypatch.setattr(qe.time, "sleep", lambda s: None)

    ok = qe._replace_with_retry(str(tmp), str(dst), log=None, retries=2,
                                keep_tmp_on_failure=True)

    assert ok is False
    assert tmp.exists(), "keep_tmp_on_failure=True must leave the recoverable copy in place"


def test_replace_with_retry_never_raises_on_a_non_retryable_error(tmp_path, monkeypatch):
    dst = tmp_path / "broker_orders.csv"
    dst.write_text("old", encoding="utf-8")
    tmp = tmp_path / "broker_orders.csv.tmp"
    tmp.write_text("new", encoding="utf-8")
    monkeypatch.setattr(qe.os, "replace",
                        lambda s, d: (_ for _ in ()).throw(OSError("simulated disk hiccup")))

    ok = qe._replace_with_retry(str(tmp), str(dst), log=None, retries=5,
                                keep_tmp_on_failure=False)

    assert ok is False
    assert dst.read_text(encoding="utf-8") == "old"
    assert not tmp.exists()


def test_replace_with_retry_stays_silent_when_log_is_none(tmp_path, monkeypatch):
    dst = tmp_path / "broker_orders.csv"
    dst.write_text("old", encoding="utf-8")
    tmp = tmp_path / "broker_orders.csv.tmp"
    tmp.write_text("new", encoding="utf-8")
    monkeypatch.setattr(qe.os, "replace",
                        lambda s, d: (_ for _ in ()).throw(PermissionError(32, "locked")))
    monkeypatch.setattr(qe.time, "sleep", lambda s: None)

    assert qe._replace_with_retry(str(tmp), str(dst), log=None, retries=2,
                                  keep_tmp_on_failure=False) is False


def test_save_state_still_round_trips_via_the_shared_helper(tmp_path):
    """save_state's own public contract must be unchanged now that it delegates to
    _replace_with_retry instead of its own inline retry loop."""
    path = tmp_path / "state.json"
    ok = qe.save_state({"legs": {}, "hello": "world"}, path=str(path), log=NOOP)
    assert ok is True
    assert qe.load_state(path=str(path), log=NOOP)["hello"] == "world"


# ── _update_broker_order_row: atomic rewrite, never a plain in-place truncation ─────

def _tmp_leftovers(out_dir, basename="broker_orders.csv"):
    return [p for p in out_dir.iterdir()
           if p.name.startswith(basename + ".") and p.name.endswith(".tmp")]


def test_update_broker_order_row_never_writes_the_destination_directly(tmp_path, monkeypatch):
    """The rewrite must ONLY ever open the live ledger for READING -- all writing goes
    to a private temp file, swapped in with one atomic os.replace (_replace_with_retry)
    -- so a concurrent reader can only ever see the OLD file or the fully-written NEW
    one, never a half-written one. Mirrors tests/test_qqq_cache_atomic.py's own
    "never truncates the destination" style, applied to this file's own writer."""
    out = _patch_qqq_paths(tmp_path, monkeypatch)
    csv_path = out / "broker_orders.csv"
    _seed_broker_row(csv_path, "sig-1", shadow_px=500.0)

    import builtins
    real_open = builtins.open

    def guarded_open(file, mode="r", *a, **kw):
        if "w" in mode and os.path.abspath(str(file)) == os.path.abspath(str(csv_path)):
            raise AssertionError("must never open the live ledger for writing directly")
        return real_open(file, mode, *a, **kw)

    monkeypatch.setattr("builtins.open", guarded_open)

    ok = qe._update_broker_order_row("sig-1", {"broker_fill_px": 501.5, "slippage": 1.5},
                                     log=NOOP)

    assert ok is True
    rows = _read_csv(csv_path)
    assert rows[0]["broker_fill_px"] == "501.5"


def test_update_broker_order_row_interrupted_swap_leaves_ledger_intact(tmp_path, monkeypatch):
    """THE scenario the review flagged: the swap itself fails partway (a crash, a kill,
    a disk hiccup, or a reader holding the file open). The ledger must still parse,
    still hold EVERY row it had before (not just the one row being targeted), no stray
    .tmp is left behind, and the function returns False rather than raising."""
    out = _patch_qqq_paths(tmp_path, monkeypatch)
    csv_path = out / "broker_orders.csv"
    _seed_broker_row(csv_path, "sig-1", shadow_px=500.0)
    # a SECOND, unrelated row -- proves nothing is lost anywhere in the ledger, not
    # just that the one targeted row happens to survive.
    existing = _read_csv(csv_path)
    extra = dict(existing[0])
    extra.update({"signal_id": "sig-2", "leg": "ENGUQ", "shadow_px": "700.0"})
    with open(csv_path, "a", newline="", encoding="utf-8") as f:
        csv.DictWriter(f, fieldnames=list(existing[0].keys())).writerow(extra)
    before = _read_csv(csv_path)
    assert len(before) == 2

    monkeypatch.setattr(
        qe.os, "replace",
        lambda s, d: (_ for _ in ()).throw(
            PermissionError(32, "simulated: a reader has the ledger open")))
    monkeypatch.setattr(qe.time, "sleep", lambda s: None)

    ok = qe._update_broker_order_row("sig-1", {"broker_fill_px": 501.5, "slippage": 1.5},
                                     log=NOOP)

    assert ok is False
    after = _read_csv(csv_path)
    assert after == before, "the ledger must hold exactly the rows it had before the failed swap"
    assert after[0]["broker_fill_px"] == "", "the update must not have landed either"
    assert _tmp_leftovers(out) == [], "no stray .tmp may be left behind on the failure path"


def test_update_broker_order_row_write_failure_leaves_ledger_intact_and_cleans_tmp(
        tmp_path, monkeypatch):
    """A failure writing/fsyncing the TEMP file itself (before any swap is even
    attempted) must be just as safe as a failed swap: original untouched, no stray
    .tmp, False returned."""
    out = _patch_qqq_paths(tmp_path, monkeypatch)
    csv_path = out / "broker_orders.csv"
    _seed_broker_row(csv_path, "sig-1", shadow_px=500.0)
    before = _read_csv(csv_path)

    monkeypatch.setattr(qe.os, "fsync",
                        lambda fd: (_ for _ in ()).throw(OSError("simulated disk hiccup")))

    ok = qe._update_broker_order_row("sig-1", {"broker_fill_px": 501.5}, log=NOOP)

    assert ok is False
    assert _read_csv(csv_path) == before
    assert _tmp_leftovers(out) == []


def test_update_broker_order_row_missing_row_never_writes_anything(tmp_path, monkeypatch):
    """A signal_id that aged out of ORDERS_KEEP must be a clean no-op -- no temp file
    ever created, nothing rewritten, just False."""
    out = _patch_qqq_paths(tmp_path, monkeypatch)
    csv_path = out / "broker_orders.csv"
    _seed_broker_row(csv_path, "sig-1", shadow_px=500.0)
    before = csv_path.read_bytes()

    ok = qe._update_broker_order_row("sig-does-not-exist", {"broker_fill_px": 1.0}, log=NOOP)

    assert ok is False
    assert csv_path.read_bytes() == before
    assert _tmp_leftovers(out) == []
