import os

from api import qqq_exec as qe


def _host(monkeypatch, name="edgelog", box=True):
    monkeypatch.setattr(qe, "_lease_host_id", lambda: name)
    monkeypatch.setattr(qe, "_is_cloud_box", lambda: box)


def test_mode_switch():
    assert qe._lease_mode({}) == "firestore"
    assert qe._lease_mode({"lease_mode": "LOCAL"}) == "local"


def test_local_lease_fails_closed(monkeypatch):
    _host(monkeypatch)
    monkeypatch.setitem(qe._LOCAL_LEASE, "held", True)
    monkeypatch.setitem(qe._LOCAL_LEASE, "pid", os.getpid())
    assert not qe._local_lease_ok({"lease_mode": "local"})[0]                      # no list
    assert not qe._local_lease_ok({"serving_hosts": []})[0]
    _host(monkeypatch, "RAZER")
    assert not qe._local_lease_ok({"serving_hosts": ["edgelog"]})[0]               # PC
    _host(monkeypatch)
    assert qe._local_lease_ok({"serving_hosts": ["edgelog"]})[0]
    monkeypatch.setitem(qe._LOCAL_LEASE, "pid", -1)                                # other process
    assert not qe._local_lease_ok({"serving_hosts": ["edgelog"]})[0]
    monkeypatch.setitem(qe._LOCAL_LEASE, "held", False)
    monkeypatch.setitem(qe._LOCAL_LEASE, "pid", os.getpid())
    assert not qe._local_lease_ok({"serving_hosts": ["edgelog"]})[0]


def test_local_mode_never_reads_firestore(monkeypatch):
    _host(monkeypatch)
    monkeypatch.setitem(qe._LOCAL_LEASE, "held", True)
    monkeypatch.setitem(qe._LOCAL_LEASE, "pid", os.getpid())

    def boom(*a, **k):
        raise AssertionError("Firestore lease read in local mode")
    monkeypatch.setattr(qe, "_lease_verify_cached", boom)
    monkeypatch.setattr(qe, "_check_lease_for_broker", boom)
    src = open(qe.__file__, encoding="utf-8").read()
    assert "lease_ok, lease_reason = _local_lease_ok(cfg)" in src
    assert qe._local_lease_ok({"lease_mode": "local", "serving_hosts": ["edgelog"]}) == (
        True, "lease ok (local: serving host + host slot)")


def test_default_is_firestore_lease_unchanged():
    # the shipped default must keep today's Firestore lease until the owner sets lease_mode=local
    assert "lease_mode" not in qe.DEFAULT_CONFIG
    assert qe._lease_mode(dict(qe.DEFAULT_CONFIG)) == "firestore"
    assert qe._lease_mode(qe._read_config_for_gate(path="no-such-file.json")) == "firestore"
    for v in (None, "", "firestore", "Firestore", "loc", 1):
        assert qe._lease_mode({"lease_mode": v}) == "firestore"


# ---- verifier 11-18 follow-up ----
import json
import sys
import threading

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_qqq_exec_broker_lease import (_BoomDb, _armed_adapter, _read_csv, _tick_cfg,
                                              _tick_paths, _OUTSIDE_MARKET_HOURS)
from test_qqq_exec_serving import _slot_child


def _local_env(tmp_path, monkeypatch, host="edgelog", box=True):
    out = tmp_path / "qqq_exec"
    out.mkdir(parents=True, exist_ok=True)
    for name, path in {"OUT_DIR": out, "CONFIG_PATH": out / "config.json",
                       "STATE_PATH": out / "state.json", "SERVING_LOCK": out / "SERVING.lock"}.items():
        monkeypatch.setattr(qe, name, str(path))
    (out / "config.json").write_text(json.dumps({"lease_mode": "local", "serving_hosts": ["edgelog"]}))
    monkeypatch.setattr(qe, "HOST_SLOT_WAIT_SEC", 0.5)
    monkeypatch.setattr(qe, "_reconcile_broker_at_boot", lambda log=print: None)
    _host(monkeypatch, host, box)
    monkeypatch.setitem(qe._LOCAL_LEASE, "held", False)
    monkeypatch.setitem(qe._LOCAL_LEASE, "pid", None)
    return out


def _run_thread(monkeypatch):
    stop, seen, logs = threading.Event(), [], []

    def one_tick(**kw):
        seen.append(dict(qe._LOCAL_LEASE))
        stop.set()
        return kw["cfg"], kw["state"], {}
    monkeypatch.setattr(qe, "tick", one_tick)
    qe.qqq_exec_thread(None, ["u"], stop=stop, log=logs.append)
    return seen, logs


def test_flag_set_while_serving_and_cleared_on_exit(tmp_path, monkeypatch):
    _local_env(tmp_path, monkeypatch)
    seen, logs = _run_thread(monkeypatch)
    assert seen and seen[0] == {"held": True, "pid": os.getpid()}
    assert qe._LOCAL_LEASE == {"held": False, "pid": None}, "the flag must not outlive the slot"


def test_stale_lock_dead_holder_then_new_process_gets_slot(tmp_path, monkeypatch):
    out = _local_env(tmp_path, monkeypatch)
    (out / "SERVING.lock").write_text("999999 0"+chr(10))       # heartbeat of a long-dead pid
    child = _slot_child(str(out / "SERVING.lock"), hold_sec=0)
    child.wait(timeout=30)                                  # a holder that came and died
    seen, _ = _run_thread(monkeypatch)
    assert seen and seen[0]["held"] is True


def test_second_process_holds_slot_thread_returns_flag_false(tmp_path, monkeypatch):
    out = _local_env(tmp_path, monkeypatch)
    child = _slot_child(str(out / "SERVING.lock"), hold_sec=120)
    try:
        assert child.stdout.readline().strip() == "held"
        seen, logs = _run_thread(monkeypatch)
        assert seen == [] and any("REFUSING" in m for m in logs)
        assert qe._LOCAL_LEASE["held"] is False
    finally:
        child.kill()
        child.wait(timeout=10)


def test_not_the_box_refuses_whatever_host_id_says(tmp_path, monkeypatch):
    _local_env(tmp_path, monkeypatch, host="edgelog", box=False)   # PC with EDGELOG_HOST_ID=edgelog
    monkeypatch.setattr(qe, "_notify", lambda *a, **k: None)
    seen, logs = _run_thread(monkeypatch)
    assert seen == [] and any("not the Oracle box" in m for m in logs)
    monkeypatch.setitem(qe._LOCAL_LEASE, "held", True)
    monkeypatch.setitem(qe._LOCAL_LEASE, "pid", os.getpid())
    assert not qe._local_lease_ok({"serving_hosts": ["edgelog"]})[0]


def test_real_is_cloud_box_false_on_windows(monkeypatch):
    monkeypatch.setattr(qe.sys, "platform", "win32")
    assert qe._is_cloud_box() is False


def test_end_to_end_tick_local_mode_firestore_down_broker_sends(tmp_path, monkeypatch):
    _tick_paths(tmp_path, monkeypatch)
    _host(monkeypatch)
    monkeypatch.setitem(qe._LOCAL_LEASE, "held", True)
    monkeypatch.setitem(qe._LOCAL_LEASE, "pid", os.getpid())
    adapter, mock_client = _armed_adapter(tmp_path, monkeypatch, "PAPER")
    monkeypatch.setattr(qe, "_get_broker_adapter", lambda log=print: adapter)
    monkeypatch.setattr(qe, "_lease_verify_cached",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("Firestore read")))
    cfg = _tick_cfg(tmp_path)
    cfg.update(lease_mode="local", serving_hosts=["edgelog"])
    cfg, state, doc = qe.tick(cfg=cfg, state={"legs": {}}, now=_OUTSIDE_MARKET_HOURS,
                              db=_BoomDb(), uid="uid1", log=lambda *_: None)
    assert state["_broker_lease_ok"] is True, state.get("_broker_lease_reason")
    qe._mirror_to_broker(state, leg="ORB", side="long", shares=5, shadow_px=500.0,
                         intent="OPEN", ts="2026-09-14 09:31:00", log=lambda *_: None)
    mock_client.order_v3.place_order.assert_called_once()
    assert _read_csv(qe.BROKER_ORDERS_CSV)[-1]["mode"] == "PAPER"
