"""api/qqq_exec.py's serving_hosts gate (2026-09-26, "the owner's PC can never take over
the book"): an optional config.json allow-list of host ids (_lease_host_id names) that
may run the book AT ALL, checked BEFORE the cross-host LEASE PROTOCOL (see
tests/test_qqq_exec_lease.py). The lease only ever lets ONE host serve at a time but does
not care WHICH one, and fails OPEN on any read trouble (the very first host to boot must
always be able to start) -- serving_hosts is the opposite: static, never touches
Firestore, and refuses a non-listed host unconditionally. See _serving_hosts_ok's own
docstring for the full rationale.

Two call sites are covered here, matching qqq_exec_thread's own docstring ("neither can
skip it"):
  1. qqq_exec_thread -- THE ONLY LOOP THAT RUNS THE BOOK (serve()'s standalone process
     and api/runner.py's in-process fallback thread both funnel through it), gated first,
     before _enter_host_slot or _claim_lease.
  2. ensure_standalone -- so an excluded PC never even LAUNCHES the detached VBS adapter
     on a fleet restart (deploy/_run_qqq_exec.vbs), not just refuses once it is up.

HARNESS: same conventions as tests/test_qqq_exec_lease.py/test_qqq_exec_serving.py --
every OUT_DIR-relative path monkeypatched into a private tmp_path, no real
Firestore/Webull/network call anywhere.
"""
import json
import os

import pytest

from api import qqq_exec as qe

NOOP = lambda *a, **k: None  # noqa: E731


def _write_config(path, cfg):
    os.makedirs(os.path.dirname(str(path)), exist_ok=True)
    with open(str(path), "w", encoding="utf-8") as f:
        json.dump(cfg, f)


def _out_paths(tmp_path, monkeypatch):
    out = tmp_path / "qqq_exec"
    for name, path in {"OUT_DIR": out, "CONFIG_PATH": out / "config.json",
                       "STATE_PATH": out / "state.json", "ORDERS_CSV": out / "orders.csv",
                       "TRADES_CSV": out / "trades.csv",
                       "BROKER_ORDERS_CSV": out / "broker_orders.csv",
                       "SERVING_LOCK": out / "SERVING.lock"}.items():
        monkeypatch.setattr(qe, name, str(path))
    return out


def _stub_enter_host_slot(calls):
    def _f(log=print):
        calls.append(1)
        return None, "stub-refuse (test never proceeds past the host slot)"
    return _f


# ── _serving_hosts_ok: the pure decision, no I/O ──────────────────────────────────────

def test_key_absent_is_todays_behaviour():
    ok, reason = qe._serving_hosts_ok({"mode": "SHADOW"}, log=NOOP)
    assert ok is True and reason is None


def test_key_present_and_host_listed(monkeypatch):
    monkeypatch.setattr(qe, "_lease_host_id", lambda: "edgelog")
    ok, reason = qe._serving_hosts_ok({"serving_hosts": ["edgelog"]}, log=NOOP)
    assert ok is True and reason is None


def test_key_present_and_host_not_listed(monkeypatch):
    monkeypatch.setattr(qe, "_lease_host_id", lambda: "owners-pc")
    ok, reason = qe._serving_hosts_ok({"serving_hosts": ["edgelog"]}, log=NOOP)
    assert ok is False
    assert "owners-pc" in reason and "edgelog" in reason


def test_host_id_is_stripped_and_matched_exactly(monkeypatch):
    monkeypatch.setattr(qe, "_lease_host_id", lambda: "edgelog")
    ok, reason = qe._serving_hosts_ok({"serving_hosts": [" edgelog ", "other-box"]}, log=NOOP)
    assert ok is True and reason is None


def test_non_list_value_is_ignored():
    ok, reason = qe._serving_hosts_ok({"serving_hosts": "edgelog"}, log=NOOP)
    assert ok is True and reason is None


def test_empty_list_is_ignored():
    # a footgun otherwise (nobody would ever be able to serve again) -- treated the same
    # as the key being absent, not as "refuse every host"
    ok, reason = qe._serving_hosts_ok({"serving_hosts": []}, log=NOOP)
    assert ok is True and reason is None


def test_non_dict_cfg_never_raises():
    ok, reason = qe._serving_hosts_ok(None, log=NOOP)
    assert ok is True and reason is None


# ── qqq_exec_thread: gated before the host slot or the lease ─────────────────────────

def test_thread_refuses_before_host_slot_or_lease_when_excluded(tmp_path, monkeypatch):
    out = _out_paths(tmp_path, monkeypatch)
    _write_config(out / "config.json", {"serving_hosts": ["edgelog"]})
    monkeypatch.setattr(qe, "_lease_host_id", lambda: "owners-pc")
    slot_calls, claim_calls = [], []
    monkeypatch.setattr(qe, "_enter_host_slot", _stub_enter_host_slot(slot_calls))
    monkeypatch.setattr(qe, "_claim_lease",
                        lambda *a, **k: claim_calls.append(1) or (True, "x", None))
    logs = []
    qe.qqq_exec_thread(object(), ["uid1"], log=lambda m: logs.append(str(m)))
    assert slot_calls == [], "excluded host must never even take the host slot"
    assert claim_calls == [], "excluded host must never claim the lease"
    assert not os.path.exists(str(out / "SERVING.lock"))
    assert any("REFUSING" in m and "owners-pc" in m for m in logs)


def test_thread_proceeds_past_the_gate_when_host_is_listed(tmp_path, monkeypatch):
    out = _out_paths(tmp_path, monkeypatch)
    _write_config(out / "config.json", {"serving_hosts": ["edgelog"]})
    monkeypatch.setattr(qe, "_lease_host_id", lambda: "edgelog")
    slot_calls = []
    monkeypatch.setattr(qe, "_enter_host_slot", _stub_enter_host_slot(slot_calls))
    qe.qqq_exec_thread(None, ["uid1"], log=NOOP)
    assert slot_calls == [1]


def test_thread_proceeds_past_the_gate_when_key_absent(tmp_path, monkeypatch):
    out = _out_paths(tmp_path, monkeypatch)   # no config.json written at all
    monkeypatch.setattr(qe, "_lease_host_id", lambda: "owners-pc")
    slot_calls = []
    monkeypatch.setattr(qe, "_enter_host_slot", _stub_enter_host_slot(slot_calls))
    qe.qqq_exec_thread(None, ["uid1"], log=NOOP)
    assert slot_calls == [1]
    # MAJOR review fix (2026-09-26): the gate reads via _read_config_for_gate, never
    # load_config, precisely so checking it never has this side effect any more.
    assert not os.path.exists(str(out / "config.json")), \
        "the gate must never create config.json just by checking it"


# ── _read_config_for_gate: never load_config's write-a-default side effect ───────────

def test_read_config_for_gate_returns_empty_dict_when_file_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(qe, "CONFIG_PATH", str(tmp_path / "qqq_exec" / "config.json"))
    assert qe._read_config_for_gate(log=NOOP) == {}
    assert not os.path.exists(str(tmp_path / "qqq_exec" / "config.json"))


def test_read_config_for_gate_reads_an_existing_file(tmp_path, monkeypatch):
    path = tmp_path / "config.json"
    _write_config(path, {"serving_hosts": ["edgelog"], "mode": "LIVE"})
    monkeypatch.setattr(qe, "CONFIG_PATH", str(path))
    cfg = qe._read_config_for_gate(log=NOOP)
    assert cfg == {"serving_hosts": ["edgelog"], "mode": "LIVE"}


def test_read_config_for_gate_fails_open_and_warns_on_a_corrupt_file(tmp_path, monkeypatch):
    path = tmp_path / "config.json"
    os.makedirs(str(tmp_path), exist_ok=True)
    with open(str(path), "w", encoding="utf-8") as f:
        f.write("{not json")
    monkeypatch.setattr(qe, "CONFIG_PATH", str(path))
    logs = []
    assert qe._read_config_for_gate(log=lambda m: logs.append(str(m))) == {}
    assert any("WARNING" in m and str(path) in m for m in logs)


# ── ensure_standalone: gated before it ever launches the detached VBS ────────────────

@pytest.mark.skipif(os.name != "nt", reason="the wscript launcher is Windows-only")
def test_ensure_standalone_refuses_without_launching_when_excluded(tmp_path, monkeypatch):
    out = tmp_path / "qqq_exec"
    monkeypatch.setattr(qe, "OUT_DIR", str(out))
    monkeypatch.setattr(qe, "CONFIG_PATH", str(out / "config.json"))
    _write_config(out / "config.json", {"serving_hosts": ["edgelog"]})
    monkeypatch.setattr(qe, "SERVING_LOCK", str(tmp_path / "absent.lock"))
    monkeypatch.setattr(qe, "_lease_host_id", lambda: "owners-pc")
    launched = []
    monkeypatch.setattr(qe.subprocess, "Popen", lambda *a, **k: launched.append(a))
    vbs = tmp_path / "_run_qqq_exec.vbs"
    vbs.write_text("' launcher", encoding="utf-8")
    logs = []
    assert qe.ensure_standalone(log=lambda m: logs.append(str(m)), vbs=str(vbs)) is True
    assert launched == [], "an excluded PC must never spawn the detached adapter, ever"
    assert any("owners-pc" in m for m in logs)


@pytest.mark.skipif(os.name != "nt", reason="the wscript launcher is Windows-only")
def test_ensure_standalone_launches_normally_when_host_listed(tmp_path, monkeypatch):
    out = tmp_path / "qqq_exec"
    monkeypatch.setattr(qe, "OUT_DIR", str(out))
    monkeypatch.setattr(qe, "CONFIG_PATH", str(out / "config.json"))
    _write_config(out / "config.json", {"serving_hosts": ["edgelog"]})
    monkeypatch.setattr(qe, "SERVING_LOCK", str(tmp_path / "absent.lock"))
    monkeypatch.setattr(qe, "_lease_host_id", lambda: "edgelog")
    launched = []
    monkeypatch.setattr(qe.subprocess, "Popen", lambda *a, **k: launched.append(a[0]))
    vbs = tmp_path / "_run_qqq_exec.vbs"
    vbs.write_text("' launcher", encoding="utf-8")
    assert qe.ensure_standalone(log=NOOP, vbs=str(vbs)) is True
    assert launched and launched[0][0] == "wscript.exe"


@pytest.mark.skipif(os.name != "nt", reason="the wscript launcher is Windows-only")
def test_ensure_standalone_launches_normally_when_key_absent(tmp_path, monkeypatch):
    out = tmp_path / "qqq_exec"
    monkeypatch.setattr(qe, "OUT_DIR", str(out))
    monkeypatch.setattr(qe, "CONFIG_PATH", str(out / "config.json"))   # no file written
    monkeypatch.setattr(qe, "SERVING_LOCK", str(tmp_path / "absent.lock"))
    monkeypatch.setattr(qe, "_lease_host_id", lambda: "owners-pc")
    launched = []
    monkeypatch.setattr(qe.subprocess, "Popen", lambda *a, **k: launched.append(a[0]))
    vbs = tmp_path / "_run_qqq_exec.vbs"
    vbs.write_text("' launcher", encoding="utf-8")
    assert qe.ensure_standalone(log=NOOP, vbs=str(vbs)) is True
    assert launched and launched[0][0] == "wscript.exe"


# ── run_once (--once): gated BEFORE the host slot (major review finding #2) ──────────
#
# Without this gate, --once had no db/uid needed to run at all: with no --uid, tick()'s
# broker-lease block is skipped entirely (its own comment calls that "an accepted,
# narrow gap"), so a single manual `python -m api.qqq_exec --once` on an excluded PC
# could still tick the book and mirror a real Webull paper order -- exactly the
# "PC takes over the book" case this whole gate exists to close.

def _stub_tick(calls):
    def _f(**kw):
        calls.append(kw)
        doc = {"mode": "SHADOW", "feed_stale": False, "breaker_tripped": False,
              "positions": {}, "today": {"realized_pnl": 0.0, "unrealized_pnl": 0.0},
              "calib": None}
        return kw.get("cfg") or {"mode": "SHADOW"}, kw.get("state") or {}, doc
    return _f


def test_run_once_refuses_before_the_host_slot_when_excluded(tmp_path, monkeypatch):
    out = _out_paths(tmp_path, monkeypatch)
    _write_config(out / "config.json", {"serving_hosts": ["edgelog"]})
    monkeypatch.setattr(qe, "_lease_host_id", lambda: "owners-pc")
    slot_calls, tick_calls, mirror_calls = [], [], []
    monkeypatch.setattr(qe, "_enter_host_slot", _stub_enter_host_slot(slot_calls))
    monkeypatch.setattr(qe, "tick", _stub_tick(tick_calls))
    monkeypatch.setattr(qe, "_mirror_to_broker", lambda *a, **k: mirror_calls.append(1))
    logs = []
    result = qe.run_once(uid=None, db=None, log=lambda m: logs.append(str(m)))
    assert result is None
    assert slot_calls == [], "an excluded host must never even take the host slot"
    assert tick_calls == [], "an excluded host must never tick"
    assert mirror_calls == [], "an excluded host must never mirror to the broker"
    assert not os.path.exists(str(out / "SERVING.lock"))
    assert any("REFUSING --once" in m and "owners-pc" in m for m in logs)


def test_run_once_proceeds_past_the_gate_when_host_is_listed(tmp_path, monkeypatch):
    out = _out_paths(tmp_path, monkeypatch)
    _write_config(out / "config.json", {"serving_hosts": ["edgelog"]})
    monkeypatch.setattr(qe, "_lease_host_id", lambda: "edgelog")
    tick_calls = []
    monkeypatch.setattr(qe, "tick", _stub_tick(tick_calls))
    result = qe.run_once(uid=None, db=None, log=NOOP)
    assert result is not None and len(tick_calls) == 1


def test_run_once_proceeds_past_the_gate_when_key_absent(tmp_path, monkeypatch):
    _out_paths(tmp_path, monkeypatch)   # no config.json written at all
    monkeypatch.setattr(qe, "_lease_host_id", lambda: "owners-pc")
    tick_calls = []
    monkeypatch.setattr(qe, "tick", _stub_tick(tick_calls))
    result = qe.run_once(uid=None, db=None, log=NOOP)
    assert result is not None and len(tick_calls) == 1


# ── serve(): gated BEFORE serving_alive/_check_lease (minor review finding #3) ────────
#
# An excluded host used to reach _check_lease (a Firestore read, possibly
# _note_standby) and log a misleading "SERVING" line before qqq_exec_thread's own copy
# of this gate ever refused it -- a hostname typo in serving_hosts plus
# systemd Restart=always/RestartSec=15 turned that into a Firestore read every 15s.

def test_serve_refuses_before_any_lease_read_when_excluded(tmp_path, monkeypatch):
    out = _out_paths(tmp_path, monkeypatch)
    _write_config(out / "config.json", {"serving_hosts": ["edgelog"]})
    monkeypatch.setattr(qe, "_lease_host_id", lambda: "owners-pc")
    lease_calls, thread_calls = [], []
    monkeypatch.setattr(qe, "_check_lease", lambda *a, **k: lease_calls.append(1) or (True, "x"))
    monkeypatch.setattr(qe, "serving_alive", lambda: (False, None))
    monkeypatch.setattr(qe, "qqq_exec_thread", lambda *a, **k: thread_calls.append(1))
    logs = []
    qe.serve(object(), ["uid1"], log=lambda m: logs.append(str(m)))
    assert lease_calls == [], "an excluded host must never read the cross-host lease"
    assert thread_calls == [], "an excluded host must never start the tick loop"
    assert not any("SERVING standalone" in m for m in logs), \
        "an excluded host must never log the misleading SERVING line"
    assert any("REFUSING to serve" in m and "owners-pc" in m for m in logs)


def test_serve_proceeds_past_the_gate_when_host_is_listed(tmp_path, monkeypatch):
    out = _out_paths(tmp_path, monkeypatch)
    _write_config(out / "config.json", {"serving_hosts": ["edgelog"]})
    monkeypatch.setattr(qe, "_lease_host_id", lambda: "edgelog")
    thread_calls = []
    monkeypatch.setattr(qe, "_check_lease", lambda *a, **k: (True, "ok"))
    monkeypatch.setattr(qe, "serving_alive", lambda: (False, None))
    monkeypatch.setattr(qe, "qqq_exec_thread", lambda *a, **k: thread_calls.append(1))
    qe.serve(object(), ["uid1"], log=NOOP)
    assert thread_calls == [1]
