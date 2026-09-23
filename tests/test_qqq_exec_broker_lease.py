"""api/qqq_exec.py's cross-host lease gate for the BROKER MIRROR specifically
(2026-09-14, "fail CLOSED once real orders can flow").

WHY THIS IS SEPARATE FROM tests/test_qqq_exec_lease.py. That file covers _check_lease,
which gates whether this PROCESS may serve at all, and fails OPEN on any read problem --
correct there, because the only thing it protects is the harmless SHADOW book (SHADOW
mode places no real order). This file covers _check_lease_for_broker and the gate inside
_mirror_to_broker, which protect REAL broker orders (once api/webull_orders.py's mode is
PAPER or LIVE) and must fail CLOSED: this owner's Firestore free tier (50k reads/day) has
already been exhausted twice, and an outage that used to just mean "the lease check gave
up and said proceed" could now mean "two hosts' broker mirrors both send".

Decision table this file proves:
  mode OFF          -> unaffected regardless of lease state (nothing real to protect)
  mode PAPER/LIVE + lease unverifiable (read error/timeout/missing field) -> no adapter
                        send, BLOCKED recorded, shadow keeps recording
  mode PAPER/LIVE + another host's lease FRESH -> no send; resumes once it goes stale
  lease lost mid-session -> the NEXT _mirror_to_broker call blocks, no retry/queueing
  host_id is recorded on every broker_orders.csv row, appended not inserted

No real Firestore or Webull network call anywhere here -- same minimal fakes as
test_qqq_exec_lease.py / test_qqq_exec_broker_mirror.py.
"""
import csv
import datetime as _dt
import json
import os
import time
from unittest.mock import MagicMock

from api import qqq_exec as qe
from api import webull_orders as WO

NOOP = lambda *a, **k: None  # noqa: E731


# ── fake Firestore (mirrors test_qqq_exec_lease.py) ─────────────────────────────────

class _FakeSnap:
    def __init__(self, data):
        self._data = data
        self.exists = data is not None

    def to_dict(self):
        return self._data


class _FakeDocRef:
    def __init__(self, data):
        self._data = data

    def collection(self, name):
        return _FakeColl(self._data)

    def get(self):
        return _FakeSnap(self._data)


class _FakeColl:
    def __init__(self, data):
        self._data = data

    def document(self, name):
        return _FakeDocRef(self._data)


class _FakeDb:
    def __init__(self, doc=None):
        self.doc = doc

    def collection(self, name):
        return _FakeColl(self.doc)


class _BoomDb:
    def collection(self, name):
        raise RuntimeError("Firestore unreachable")


def _lease_doc(host_id, age_sec=0.0):
    return {"lease": {"host_id": host_id, "leased_at": time.time() - age_sec}}


# ── Part A: _check_lease_for_broker -- unit tests ───────────────────────────────────

def test_no_db_is_unverifiable():
    ok, reason = qe._check_lease_for_broker(None, "uid1", log=NOOP)
    assert ok is False
    assert "unverifiable" in reason


def test_no_uid_is_unverifiable():
    ok, reason = qe._check_lease_for_broker(_FakeDb({}), "", log=NOOP)
    assert ok is False
    assert "unverifiable" in reason


def test_missing_doc_is_ok_first_ever_host():
    ok, reason = qe._check_lease_for_broker(_FakeDb(None), "uid1", log=NOOP)
    assert ok is True


def test_doc_without_lease_field_is_ok():
    ok, reason = qe._check_lease_for_broker(_FakeDb({"mode": "SHADOW"}), "uid1", log=NOOP)
    assert ok is True


def test_own_host_lease_is_ok(monkeypatch):
    monkeypatch.setattr(qe, "_lease_host_id", lambda: "this-host")
    ok, reason = qe._check_lease_for_broker(
        _FakeDb(_lease_doc("this-host", age_sec=1.0)), "uid1", log=NOOP)
    assert ok is True


def test_other_hosts_fresh_lease_blocks(monkeypatch):
    monkeypatch.setattr(qe, "_lease_host_id", lambda: "cloud-vm")
    ok, reason = qe._check_lease_for_broker(
        _FakeDb(_lease_doc("owners-pc", age_sec=5.0)), "uid1", log=NOOP)
    assert ok is False
    assert "owners-pc" in reason


def test_other_hosts_stale_lease_is_ok(monkeypatch):
    monkeypatch.setattr(qe, "_lease_host_id", lambda: "cloud-vm")
    ok, reason = qe._check_lease_for_broker(
        _FakeDb(_lease_doc("owners-pc", age_sec=qe.LEASE_STALE_SEC + 30)), "uid1", log=NOOP)
    assert ok is True
    assert "stale" in reason


def test_lease_boundary_just_under_stale_still_blocks(monkeypatch):
    monkeypatch.setattr(qe, "_lease_host_id", lambda: "cloud-vm")
    ok, reason = qe._check_lease_for_broker(
        _FakeDb(_lease_doc("owners-pc", age_sec=qe.LEASE_STALE_SEC - 5)), "uid1", log=NOOP)
    assert ok is False


def test_firestore_read_error_is_unverifiable():
    ok, reason = qe._check_lease_for_broker(_BoomDb(), "uid1", log=NOOP)
    assert ok is False
    assert "unverifiable" in reason


def test_unreadable_leased_at_is_unverifiable_not_free(monkeypatch):
    """DIFFERENT from _check_lease (which fail-opens this exact shape): a foreign claim
    with a garbage timestamp cannot be told apart from a genuinely fresh one, so real
    broker sends must block rather than assume it is safe."""
    monkeypatch.setattr(qe, "_lease_host_id", lambda: "cloud-vm")
    doc = {"lease": {"host_id": "owners-pc", "leased_at": "not-a-number"}}
    ok, reason = qe._check_lease_for_broker(_FakeDb(doc), "uid1", log=NOOP)
    assert ok is False
    assert "unverifiable" in reason


def test_missing_leased_at_on_a_foreign_claim_is_unverifiable_not_free(monkeypatch):
    """Same DIFFERENCE as above -- this is the "missing field" case from the fix spec:
    _check_lease treats a foreign claim with no leased_at as free, but for real broker
    orders that must block instead."""
    monkeypatch.setattr(qe, "_lease_host_id", lambda: "cloud-vm")
    doc = {"lease": {"host_id": "owners-pc"}}
    ok, reason = qe._check_lease_for_broker(_FakeDb(doc), "uid1", log=NOOP)
    assert ok is False
    assert "unverifiable" in reason


# ── Part B: _mirror_to_broker gating on state["_broker_lease_ok"] ──────────────────

def _broker_cfg(tmp_path, mode="OFF"):
    cfg = WO.load_config("__no_such_file__")   # defaults only
    cfg["mode"] = mode
    cfg["rails"]["session_start"] = "00:00"
    cfg["rails"]["session_end"] = "23:59"
    cfg["state_path"] = str(tmp_path / "wo_state.json")
    cfg["paper_keys_path"] = str(tmp_path / "paper_keys.json")
    cfg["live_keys_path"] = str(tmp_path / "live_keys.json")
    cfg["arm_live_file"] = str(tmp_path / "ARM_LIVE")
    cfg["kill_file"] = str(tmp_path / "WO_KILL")
    return cfg


def _mock_client():
    client = MagicMock()
    client.account_v2.get_account_list.return_value.json.return_value = {
        # account_class is what _account_id() selects on by default (purpose "stock"
        # wants INDIVIDUAL_MARGIN -- see api/webull_orders.py's DEFAULT_ACCOUNT_SELECT).
        "data": [{"account_id": "ACCT1", "account_class": "INDIVIDUAL_MARGIN"}]}
    client.order_v3.place_order.return_value.json.return_value = {"status": "SUBMITTED"}
    client.account_v2.get_account_position.return_value.json.return_value = {"data": []}
    return client


def _armed_adapter(tmp_path, monkeypatch, mode):
    """A real OrderAdapter whose effective_mode() genuinely resolves to PAPER or LIVE
    (armed exactly like webull_orders' own tests do it), with its SDK client mocked out
    so nothing ever touches the network."""
    cfg = _broker_cfg(tmp_path, mode=mode)
    if mode == "PAPER":
        with open(cfg["paper_keys_path"], "w", encoding="utf-8") as f:
            json.dump({"app_key": "AK", "app_secret": "AS"}, f)
    elif mode == "LIVE":
        with open(cfg["live_keys_path"], "w", encoding="utf-8") as f:
            json.dump({"app_key": "AK", "app_secret": "AS"}, f)
        open(cfg["arm_live_file"], "w", encoding="utf-8").close()
    adapter = WO.OrderAdapter(config=cfg, log=NOOP)
    mock_client = _mock_client()
    monkeypatch.setattr(adapter, "_build_client", lambda m: mock_client)
    assert adapter.effective_mode()[0] == mode, "test setup must actually arm the mode under test"
    return adapter, mock_client


def _patch_qqq_paths(tmp_path, monkeypatch):
    out = tmp_path / "qqq_out"
    monkeypatch.setattr(qe, "OUT_DIR", str(out))
    monkeypatch.setattr(qe, "BROKER_ORDERS_CSV", str(out / "broker_orders.csv"))
    return out


def _read_csv(path):
    with open(path, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def test_off_mode_lease_unverifiable_is_unchanged(tmp_path, monkeypatch):
    """Broker mode OFF -> keep fail-open: an unverifiable/blocked lease state must not
    change OFF-mode behaviour at all -- there is no real order to protect."""
    _patch_qqq_paths(tmp_path, monkeypatch)
    adapter = WO.OrderAdapter(config=_broker_cfg(tmp_path, mode="OFF"), log=NOOP)
    monkeypatch.setattr(qe, "_get_broker_adapter", lambda log=print: adapter)

    state = {"legs": {}, "_broker_lease_ok": False,
            "_broker_lease_reason": "lease unverifiable: Firestore read failed"}
    qe._mirror_to_broker(state, leg="ORB", side="long", shares=5, shadow_px=500.0,
                         intent="OPEN", ts="2026-09-14 09:31:00", log=NOOP)
    rows = _read_csv(qe.BROKER_ORDERS_CSV)
    assert rows[-1]["mode"] == "OFF"
    assert rows[-1]["sent"] == "False"
    assert rows[-1]["ok"] == "True"


def test_paper_read_error_no_adapter_send_blocked_recorded(tmp_path, monkeypatch):
    _patch_qqq_paths(tmp_path, monkeypatch)
    adapter, mock_client = _armed_adapter(tmp_path, monkeypatch, "PAPER")
    monkeypatch.setattr(qe, "_get_broker_adapter", lambda log=print: adapter)

    state = {"legs": {}, "_broker_lease_ok": False,
            "_broker_lease_reason": "lease unverifiable: Firestore read failed (RuntimeError: boom)"}
    qe._mirror_to_broker(state, leg="ORB", side="long", shares=5, shadow_px=500.0,
                         intent="OPEN", ts="2026-09-14 09:31:00", log=NOOP)

    mock_client.order_v3.place_order.assert_not_called()
    rows = _read_csv(qe.BROKER_ORDERS_CSV)
    assert rows[-1]["mode"] == "BLOCKED"
    assert rows[-1]["ok"] == "False"
    assert rows[-1]["sent"] == "False"
    assert "lease unverifiable" in rows[-1]["reason"]


def test_paper_other_host_fresh_blocks_then_resumes_after_stale(tmp_path, monkeypatch):
    _patch_qqq_paths(tmp_path, monkeypatch)
    adapter, mock_client = _armed_adapter(tmp_path, monkeypatch, "PAPER")
    monkeypatch.setattr(qe, "_get_broker_adapter", lambda log=print: adapter)

    # another host's lease is fresh -> blocked, no send
    state = {"legs": {}, "_broker_lease_ok": False,
            "_broker_lease_reason": "host 'owners-pc' holds a fresh lease (5s old) -- broker sends blocked"}
    qe._mirror_to_broker(state, leg="ORB", side="long", shares=5, shadow_px=500.0,
                         intent="OPEN", ts="2026-09-14 09:31:00", log=NOOP)
    mock_client.order_v3.place_order.assert_not_called()
    assert _read_csv(qe.BROKER_ORDERS_CSV)[-1]["mode"] == "BLOCKED"

    # the other host's lease has since gone stale -> resumes, sends normally
    state["_broker_lease_ok"] = True
    state["_broker_lease_reason"] = "lease ok (other host stale)"
    qe._mirror_to_broker(state, leg="ORB", side="long", shares=5, shadow_px=500.0,
                         intent="OPEN", ts="2026-09-14 09:31:05", log=NOOP)
    mock_client.order_v3.place_order.assert_called_once()
    rows = _read_csv(qe.BROKER_ORDERS_CSV)
    assert rows[-1]["mode"] == "PAPER"
    assert rows[-1]["sent"] == "True"


def test_live_mode_same_gating_as_paper(tmp_path, monkeypatch):
    _patch_qqq_paths(tmp_path, monkeypatch)
    adapter, mock_client = _armed_adapter(tmp_path, monkeypatch, "LIVE")
    monkeypatch.setattr(qe, "_get_broker_adapter", lambda log=print: adapter)

    state = {"legs": {}, "_broker_lease_ok": False,
            "_broker_lease_reason": "lease unverifiable: timeout"}
    qe._mirror_to_broker(state, leg="ORB", side="long", shares=5, shadow_px=500.0,
                         intent="OPEN", ts="2026-09-14 09:31:00", log=NOOP)
    mock_client.order_v3.place_order.assert_not_called()
    assert _read_csv(qe.BROKER_ORDERS_CSV)[-1]["mode"] == "BLOCKED"

    state["_broker_lease_ok"] = True
    state["_broker_lease_reason"] = None
    qe._mirror_to_broker(state, leg="ORB", side="long", shares=5, shadow_px=500.0,
                         intent="OPEN", ts="2026-09-14 09:31:05", log=NOOP)
    mock_client.order_v3.place_order.assert_called_once()
    assert _read_csv(qe.BROKER_ORDERS_CSV)[-1]["mode"] == "LIVE"


def test_lease_lost_mid_session_stops_sends_next_tick(tmp_path, monkeypatch):
    """First send: lease ok, goes through. Then the lease is lost -- the very next
    _mirror_to_broker call (standing in for "the next tick") blocks; nothing is queued
    or retried."""
    _patch_qqq_paths(tmp_path, monkeypatch)
    adapter, mock_client = _armed_adapter(tmp_path, monkeypatch, "PAPER")
    monkeypatch.setattr(qe, "_get_broker_adapter", lambda log=print: adapter)

    state = {"legs": {}, "_broker_lease_ok": True, "_broker_lease_reason": None}
    qe._mirror_to_broker(state, leg="ORB", side="long", shares=5, shadow_px=500.0,
                         intent="OPEN", ts="2026-09-14 09:31:00", log=NOOP)
    assert mock_client.order_v3.place_order.call_count == 1

    state["_broker_lease_ok"] = False
    state["_broker_lease_reason"] = "lease unverifiable: Firestore read failed"
    qe._mirror_to_broker(state, leg="ORB", side="long", shares=5, shadow_px=506.0,
                         intent="CLOSE", ts="2026-09-14 09:31:00", seq=1, log=NOOP)
    assert mock_client.order_v3.place_order.call_count == 1, "no new send once the lease is lost"
    rows = _read_csv(qe.BROKER_ORDERS_CSV)
    assert rows[-1]["intent"] == "CLOSE"
    assert rows[-1]["mode"] == "BLOCKED"


def test_no_lease_key_at_all_defaults_to_proceed_backward_compat(tmp_path, monkeypatch):
    """A direct caller that never went through tick() (every pre-2026-09-14 test, and
    any future one that does not care) must see EXACTLY the old behaviour: state with
    no _broker_lease_ok key at all still sends normally."""
    _patch_qqq_paths(tmp_path, monkeypatch)
    adapter, mock_client = _armed_adapter(tmp_path, monkeypatch, "PAPER")
    monkeypatch.setattr(qe, "_get_broker_adapter", lambda log=print: adapter)

    state = {"legs": {}}
    qe._mirror_to_broker(state, leg="ORB", side="long", shares=5, shadow_px=500.0,
                         intent="OPEN", ts="2026-09-14 09:31:00", log=NOOP)
    mock_client.order_v3.place_order.assert_called_once()


# ── Part C: host_id column ───────────────────────────────────────────────────────────

def test_host_id_recorded_on_every_row(tmp_path, monkeypatch):
    _patch_qqq_paths(tmp_path, monkeypatch)
    adapter = WO.OrderAdapter(config=_broker_cfg(tmp_path, mode="OFF"), log=NOOP)
    monkeypatch.setattr(qe, "_get_broker_adapter", lambda log=print: adapter)
    monkeypatch.setattr(qe, "_lease_host_id", lambda: "test-host-42")

    state = {"legs": {}}
    qe._mirror_to_broker(state, leg="ORB", side="long", shares=5, shadow_px=500.0,
                         intent="OPEN", ts="2026-09-14 09:31:00", log=NOOP)
    rows = _read_csv(qe.BROKER_ORDERS_CSV)
    assert rows[-1]["host_id"] == "test-host-42"


def test_host_id_column_appended_never_inserted_migrates_old_file(tmp_path, monkeypatch):
    """An existing broker_orders.csv written before this column existed must be
    migrated in place (old rows padded with ""), never dropped or reordered."""
    out = _patch_qqq_paths(tmp_path, monkeypatch)
    os.makedirs(out, exist_ok=True)
    old_cols = qe.BROKER_ORDER_COLS[:-1]   # every column except the new trailing host_id
    assert old_cols == ["ts_et", "leg", "intent", "side", "shares", "signal_id",
                        "client_order_id", "mode", "ok", "sent", "shadow_px",
                        "broker_fill_px", "slippage", "reason", "duplicate"], (
        "host_id must be APPENDED at the end, never inserted")
    old_row = {c: "" for c in old_cols}
    old_row["leg"] = "OLD"
    old_row["intent"] = "OPEN"
    with open(qe.BROKER_ORDERS_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=old_cols)
        w.writeheader()
        w.writerow(old_row)

    adapter = WO.OrderAdapter(config=_broker_cfg(tmp_path, mode="OFF"), log=NOOP)
    monkeypatch.setattr(qe, "_get_broker_adapter", lambda log=print: adapter)
    state = {"legs": {}}
    qe._mirror_to_broker(state, leg="ORB", side="long", shares=5, shadow_px=500.0,
                         intent="OPEN", ts="2026-09-14 09:31:00", log=NOOP)

    rows = _read_csv(qe.BROKER_ORDERS_CSV)
    assert rows[0]["leg"] == "OLD"
    assert rows[0]["host_id"] == "", "old rows are padded, not dropped"
    assert rows[1]["leg"] == "ORB"
    assert rows[1]["host_id"]


# ── Part D: tick() wiring -- db/uid -> _check_lease_for_broker -> state ─────────────

class _FakeAdapter:
    """Stands in for _get_broker_adapter()'s return value -- only effective_mode() and
    status() are exercised by tick()/_build_doc in these tests."""
    def __init__(self, mode="OFF"):
        self._mode = mode

    def effective_mode(self):
        return self._mode, f"forced {self._mode} for test"

    def status(self):
        return {"requested_mode": self._mode, "effective_mode": self._mode,
                "mode_reason": "test", "environment": None,
                "paper_credentials_present": False, "live_credentials_present": False,
                "live_armed": False, "kill_file_present": False, "halted": False,
                "halt_reason": None, "last_order": None, "last_error": None,
                "daily_pnl": 0.0, "open_legs": []}


def _tick_paths(tmp_path, monkeypatch):
    out = tmp_path / "qqq_exec_out"
    monkeypatch.setattr(qe, "OUT_DIR", str(out))
    monkeypatch.setattr(qe, "CONFIG_PATH", str(out / "config.json"))
    monkeypatch.setattr(qe, "STATE_PATH", str(out / "state.json"))
    monkeypatch.setattr(qe, "ORDERS_CSV", str(out / "orders.csv"))
    monkeypatch.setattr(qe, "TRADES_CSV", str(out / "trades.csv"))
    monkeypatch.setattr(qe, "BROKER_ORDERS_CSV", str(out / "broker_orders.csv"))
    return out


def _tick_cfg(tmp_path):
    cfg = dict(qe.DEFAULT_CONFIG)
    cfg["signal_source"] = "engine"
    cfg["shares"] = {"ORB": 5, "ENGUQ": 5, "NOISE": 5}
    cfg["kill_file"] = str(tmp_path / "KILL")
    return cfg


_OUTSIDE_MARKET_HOURS = _dt.datetime(2026, 9, 8, 3, 0)   # 03:00 ET, a known trading weekday
                                                          # in this suite (see
                                                          # test_qqq_exec_engine_source.py)


def test_tick_wires_lease_check_when_paper_and_db_uid_given(tmp_path, monkeypatch):
    _tick_paths(tmp_path, monkeypatch)
    monkeypatch.setattr(qe, "_get_broker_adapter", lambda log=print: _FakeAdapter("PAPER"))
    db = _FakeDb(_lease_doc("owners-pc", age_sec=5.0))   # another host's FRESH lease

    cfg, state, doc = qe.tick(cfg=_tick_cfg(tmp_path), state={"legs": {}},
                              now=_OUTSIDE_MARKET_HOURS, db=db, uid="uid1",
                              log=lambda *_: None)

    assert state["_broker_lease_ok"] is False
    assert "owners-pc" in state["_broker_lease_reason"]
    assert doc["broker"]["lease_ok_to_send"] is False
    assert "owners-pc" in doc["broker"]["lease_block_reason"]


def test_tick_skips_lease_check_when_broker_off(tmp_path, monkeypatch):
    _tick_paths(tmp_path, monkeypatch)
    monkeypatch.setattr(qe, "_get_broker_adapter", lambda log=print: _FakeAdapter("OFF"))
    db = _FakeDb(_lease_doc("owners-pc", age_sec=5.0))   # would refuse if it were checked

    cfg, state, doc = qe.tick(cfg=_tick_cfg(tmp_path), state={"legs": {}},
                              now=_OUTSIDE_MARKET_HOURS, db=db, uid="uid1",
                              log=lambda *_: None)

    assert state["_broker_lease_ok"] is True, "OFF mode must never be gated by the lease"
    assert doc["broker"]["lease_ok_to_send"] is True


def test_tick_skips_lease_check_entirely_without_db_or_uid(tmp_path, monkeypatch):
    """Backward compatibility: every pre-2026-09-14 caller/test calls tick() with
    neither db nor uid -- the NEW lease-gating block must not construct/consult the
    broker adapter at all in that case.

    Two OTHER call sites are expected regardless of db/uid, both independent of
    Firestore entirely: _build_doc's pre-existing "broker" status block (mode/creds/
    etc for the doc), and 2026-09-14's _run_broker_housekeeping (daily P&L wiring +
    FIX 2's reconcile scheduling -- see api/qqq_exec.py's own docstring on that
    function for why it's ONE consolidated call site for both). This test counts
    calls (expects exactly 2, not 0) to isolate "did the LEASE-GATE block specifically
    add a call" from those two pre-existing/independent ones."""
    _tick_paths(tmp_path, monkeypatch)

    calls = []

    def counting(log=print):
        calls.append(1)
        return _FakeAdapter("PAPER")
    monkeypatch.setattr(qe, "_get_broker_adapter", counting)

    cfg, state, doc = qe.tick(cfg=_tick_cfg(tmp_path), state={"legs": {}},
                              now=_OUTSIDE_MARKET_HOURS, log=lambda *_: None)
    assert "_broker_lease_ok" not in state
    assert len(calls) == 2, ("only _build_doc's status block and _run_broker_housekeeping "
                             "may call the broker adapter here -- the LEASE-GATE block "
                             "must skip it entirely when tick() is called without db/uid")
