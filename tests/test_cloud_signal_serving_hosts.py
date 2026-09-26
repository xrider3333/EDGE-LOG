"""api/cloud_signal.py's serving_hosts gate (2026-09-26, EXIT/serving_hosts item 2, "the
PC does not run the QQQ signal engine either"): reads the SAME "serving_hosts" list from
the SAME config.json as api.qqq_exec._serving_hosts_ok (see that function's docstring for
the full rationale) -- one list in one file governs both halves of the book. No import of
api.qqq_exec here: that module already imports THIS one (_build_keel_status), so the
reverse import would be circular -- _host_id/_qqq_exec_config_path duplicate the small
pieces of logic they need instead.

cloud_signal_thread is BOTH call sites that matter here (deploy/cloud/edgelog-cloud-
signal.service's own ExecStart runs it directly on the box, and api/runner.py starts it
as a thread on the PC), so one gate at the top of that function covers both.

HARNESS: same conventions as tests/test_cloud_signal.py -- DEFAULT_PATHS pointed at a
private tmp_path, no real network/yfinance call anywhere (the gate returns before any of
that runs).
"""
import json
import os
import threading

from api import cloud_signal as cs

NOOP = lambda *a, **k: None  # noqa: E731

# tests/conftest.py's autouse _isolate_serving_hosts_config monkeypatches
# cs._qqq_exec_config_path on every test (so no test can reach the real EDGELOG_HOME's
# config.json by accident) -- captured here, at collection time, BEFORE that fixture
# ever runs, so the two tests below that exercise the function's own path-building logic
# call the genuine implementation, not that fixture's stub.
_REAL_QQQ_EXEC_CONFIG_PATH = cs._qqq_exec_config_path


def _write_config(path, cfg):
    os.makedirs(os.path.dirname(str(path)), exist_ok=True)
    with open(str(path), "w", encoding="utf-8") as f:
        json.dump(cfg, f)


# ── _serving_hosts_ok: the pure decision (config file I/O only) ──────────────────────

def test_key_absent_is_todays_behaviour(tmp_path, monkeypatch):
    monkeypatch.setattr(cs, "_qqq_exec_config_path",
                        lambda: str(tmp_path / "no_such" / "config.json"))
    ok, reason = cs._serving_hosts_ok(log=NOOP)
    assert ok is True and reason is None


def test_host_listed_is_ok(tmp_path, monkeypatch):
    cfg_path = tmp_path / "qqq_exec" / "config.json"
    _write_config(cfg_path, {"serving_hosts": ["edgelog"]})
    monkeypatch.setattr(cs, "_qqq_exec_config_path", lambda: str(cfg_path))
    monkeypatch.setattr(cs, "_host_id", lambda: "edgelog")
    ok, reason = cs._serving_hosts_ok(log=NOOP)
    assert ok is True and reason is None


def test_host_not_listed_is_refused(tmp_path, monkeypatch):
    cfg_path = tmp_path / "qqq_exec" / "config.json"
    _write_config(cfg_path, {"serving_hosts": ["edgelog"]})
    monkeypatch.setattr(cs, "_qqq_exec_config_path", lambda: str(cfg_path))
    monkeypatch.setattr(cs, "_host_id", lambda: "owners-pc")
    ok, reason = cs._serving_hosts_ok(log=NOOP)
    assert ok is False
    assert "owners-pc" in reason and "edgelog" in reason


def test_empty_list_is_ignored(tmp_path, monkeypatch):
    cfg_path = tmp_path / "qqq_exec" / "config.json"
    _write_config(cfg_path, {"serving_hosts": []})
    monkeypatch.setattr(cs, "_qqq_exec_config_path", lambda: str(cfg_path))
    monkeypatch.setattr(cs, "_host_id", lambda: "owners-pc")
    ok, reason = cs._serving_hosts_ok(log=NOOP)
    assert ok is True and reason is None


def test_unreadable_config_fails_open(tmp_path, monkeypatch):
    cfg_path = tmp_path / "qqq_exec" / "config.json"
    os.makedirs(cfg_path.parent, exist_ok=True)
    cfg_path.write_text("{not json", encoding="utf-8")
    monkeypatch.setattr(cs, "_qqq_exec_config_path", lambda: str(cfg_path))
    ok, reason = cs._serving_hosts_ok(log=NOOP)
    assert ok is True and reason is None


def test_default_config_path_matches_qqq_execs_own_layout(monkeypatch):
    monkeypatch.delenv("EDGELOG_QQQ_EXEC_DIR", raising=False)
    monkeypatch.setattr(cs, "edgelog_home", lambda: r"C:\EdgeLog")
    assert _REAL_QQQ_EXEC_CONFIG_PATH() == os.path.join(r"C:\EdgeLog", "qqq_exec", "config.json")


def test_config_path_honours_the_same_env_override_qqq_exec_uses(tmp_path, monkeypatch):
    monkeypatch.setenv("EDGELOG_QQQ_EXEC_DIR", str(tmp_path / "custom_qqq_exec"))
    assert _REAL_QQQ_EXEC_CONFIG_PATH() == str(tmp_path / "custom_qqq_exec" / "config.json")


# ── cloud_signal_thread: gated before any engine work ─────────────────────────────────

def test_thread_refuses_before_any_engine_work_when_excluded(tmp_path, monkeypatch):
    cfg_path = tmp_path / "qqq_exec" / "config.json"
    _write_config(cfg_path, {"serving_hosts": ["edgelog"]})
    monkeypatch.setattr(cs, "_qqq_exec_config_path", lambda: str(cfg_path))
    monkeypatch.setattr(cs, "_host_id", lambda: "owners-pc")
    migrate_calls = []
    monkeypatch.setattr(cs, "_migrate_signals_header",
                        lambda *a, **k: migrate_calls.append(1))
    history_calls = []
    monkeypatch.setattr(cs, "log_history_windows", lambda *a, **k: history_calls.append(1))
    logs = []
    stop = threading.Event()   # never even consulted -- the gate returns before the loop
    cs.cloud_signal_thread(stop=stop, log=lambda m: logs.append(str(m)))
    assert migrate_calls == [], "excluded host must never touch signals.csv"
    assert history_calls == [], "excluded host must do no engine work at all, not even logging"
    assert any("REFUSING" in m and "owners-pc" in m for m in logs)


def test_thread_proceeds_past_the_gate_when_host_is_listed(tmp_path, monkeypatch):
    cfg_path = tmp_path / "qqq_exec" / "config.json"
    _write_config(cfg_path, {"serving_hosts": ["edgelog"]})
    monkeypatch.setattr(cs, "_qqq_exec_config_path", lambda: str(cfg_path))
    monkeypatch.setattr(cs, "_host_id", lambda: "edgelog")
    monkeypatch.setattr(cs, "log_history_windows", lambda *a, **k: None)
    migrate_calls = []
    monkeypatch.setattr(cs, "_migrate_signals_header",
                        lambda *a, **k: migrate_calls.append(1))
    paths = cs._paths(home=str(tmp_path / "home"))
    os.makedirs(paths["state_dir"], exist_ok=True)
    with open(paths["signals_path"], "w", encoding="utf-8") as f:
        f.write("leg,event\n")
    monkeypatch.setattr(cs, "DEFAULT_PATHS", paths)
    stop = threading.Event()
    stop.set()   # boot only, leave before the loop's first iteration
    cs.cloud_signal_thread(stop=stop, log=NOOP)
    assert migrate_calls == [1], "a listed host must reach its normal boot-time work"


def test_thread_proceeds_past_the_gate_when_key_absent(tmp_path, monkeypatch):
    monkeypatch.setattr(cs, "_qqq_exec_config_path",
                        lambda: str(tmp_path / "no_such" / "config.json"))
    monkeypatch.setattr(cs, "_host_id", lambda: "owners-pc")
    monkeypatch.setattr(cs, "log_history_windows", lambda *a, **k: None)
    migrate_calls = []
    monkeypatch.setattr(cs, "_migrate_signals_header",
                        lambda *a, **k: migrate_calls.append(1))
    paths = cs._paths(home=str(tmp_path / "home2"))
    os.makedirs(paths["state_dir"], exist_ok=True)
    with open(paths["signals_path"], "w", encoding="utf-8") as f:
        f.write("leg,event\n")
    monkeypatch.setattr(cs, "DEFAULT_PATHS", paths)
    stop = threading.Event()
    stop.set()
    cs.cloud_signal_thread(stop=stop, log=NOOP)
    assert migrate_calls == [1]


# ── cmd_once / cmd_loop: gated too, not just the runner/systemd thread (MINOR review ──
# fix, 2026-09-26). Before this fix only cloud_signal_thread checked serving_hosts, so a
# hand-run `python -m api.cloud_signal --once` (or --loop) on an excluded PC still ran
# the engine -- these two entry points are not a money path (no order path exists here
# at all) but they are still meant to be off on an excluded host, same as the thread.

def test_cmd_once_refuses_when_host_excluded(tmp_path, monkeypatch, capsys):
    cfg_path = tmp_path / "qqq_exec" / "config.json"
    _write_config(cfg_path, {"serving_hosts": ["edgelog"]})
    monkeypatch.setattr(cs, "_qqq_exec_config_path", lambda: str(cfg_path))
    monkeypatch.setattr(cs, "_host_id", lambda: "owners-pc")
    live = cs._paths(home=str(tmp_path / "live_home"))
    os.makedirs(live["state_dir"], exist_ok=True)
    monkeypatch.setattr(cs, "DEFAULT_PATHS", live)
    rc = cs.cmd_once()
    assert rc == 2
    assert not os.path.exists(live["heartbeat_path"]), "excluded host must never stamp a heartbeat"
    out = capsys.readouterr().out
    assert "owners-pc" in out and "REFUSED" in out


def test_cmd_loop_refuses_when_host_excluded(tmp_path, monkeypatch, capsys):
    cfg_path = tmp_path / "qqq_exec" / "config.json"
    _write_config(cfg_path, {"serving_hosts": ["edgelog"]})
    monkeypatch.setattr(cs, "_qqq_exec_config_path", lambda: str(cfg_path))
    monkeypatch.setattr(cs, "_host_id", lambda: "owners-pc")
    live = cs._paths(home=str(tmp_path / "live_home2"))
    os.makedirs(live["state_dir"], exist_ok=True)
    monkeypatch.setattr(cs, "DEFAULT_PATHS", live)
    rc = cs.cmd_loop()
    assert rc == 2
    assert not os.path.exists(live["heartbeat_path"]), "excluded host must never stamp a heartbeat"
    out = capsys.readouterr().out
    assert "owners-pc" in out and "REFUSED" in out


def test_cmd_once_proceeds_when_host_is_listed(tmp_path, monkeypatch):
    """The gate must not block a listed host -- --once falls through to its normal
    _refuse_beside_live_writer check (no heartbeat here, so that check passes too) and
    runs step()."""
    cfg_path = tmp_path / "qqq_exec" / "config.json"
    _write_config(cfg_path, {"serving_hosts": ["edgelog"]})
    monkeypatch.setattr(cs, "_qqq_exec_config_path", lambda: str(cfg_path))
    monkeypatch.setattr(cs, "_host_id", lambda: "edgelog")
    live = cs._paths(home=str(tmp_path / "live_home3"))
    os.makedirs(live["state_dir"], exist_ok=True)
    monkeypatch.setattr(cs, "DEFAULT_PATHS", live)
    monkeypatch.setattr(cs, "log_history_windows", lambda *a, **k: None)
    monkeypatch.setattr(cs, "step", lambda **k: [])
    rc = cs.cmd_once()
    assert rc == 0
    assert os.path.exists(live["heartbeat_path"]), "a listed host must run --once normally"


def test_cmd_once_proceeds_when_key_absent(tmp_path, monkeypatch):
    """Key-absent must fall through exactly like today, same as every other gate here."""
    monkeypatch.setattr(cs, "_qqq_exec_config_path",
                        lambda: str(tmp_path / "no_such" / "config.json"))
    monkeypatch.setattr(cs, "_host_id", lambda: "owners-pc")
    live = cs._paths(home=str(tmp_path / "live_home4"))
    os.makedirs(live["state_dir"], exist_ok=True)
    monkeypatch.setattr(cs, "DEFAULT_PATHS", live)
    monkeypatch.setattr(cs, "log_history_windows", lambda *a, **k: None)
    monkeypatch.setattr(cs, "step", lambda **k: [])
    rc = cs.cmd_once()
    assert rc == 0
    assert os.path.exists(live["heartbeat_path"])
