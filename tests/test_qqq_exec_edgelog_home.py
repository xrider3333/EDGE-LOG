"""EDGELOG_HOME (2026-09-13, "moving the stack to a cloud VM is fill-in-the-blanks").

api/qqq_exec.py and api/webull_orders.py used to hardcode every path as a bare
C:\\EdgeLog\\... literal. EDGELOG_HOME is the one base directory a Linux VM sets
differently; every specific-path env var still overrides its own default
individually. These tests pin two things: (1) with EDGELOG_HOME unset on Windows,
every derived default is byte-identical to the old hardcoded literal, and (2)
setting EDGELOG_HOME actually moves the defaults, proven via a subprocess (a plain
monkeypatch can't un-ring the module-import bell -- these constants are computed once
at import time).
"""
import os
import subprocess
import sys

from api import qqq_exec as qe
from api import webull_orders as WO

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ── default (EDGELOG_HOME unset): every Windows path stays identical ──────────────

def test_qqq_exec_default_edgelog_home_matches_windows_literal():
    if os.name != "nt":
        return  # the "stays identical on Windows" claim only means something on Windows
    assert qe.EDGELOG_HOME == r"C:\EdgeLog"
    assert qe.OUT_DIR == r"C:\EdgeLog\qqq_exec"
    assert qe.NQ_10S_PRIMARY == r"C:\EdgeLog\ohlc_addon\NQ_10s.csv"
    assert qe.NQ_10S_FALLBACK == r"C:\EdgeLog\ohlc\NQ_10s.csv"
    assert qe.WEBULL_KEYS == r"C:\EdgeLog\webull_keys.json"
    assert qe._WEBULL_TOKEN_DIR == r"C:\EdgeLog\webull_token"
    assert qe.QQQ_EXEC_VBS == r"C:\EdgeLog\_run_qqq_exec.vbs"
    assert qe.DEFAULT_CONFIG["kill_file"] == r"C:\EdgeLog\qqq_exec\KILL"


def test_webull_orders_default_edgelog_home_matches_windows_literal():
    if os.name != "nt":
        return
    assert WO.EDGELOG_HOME == r"C:\EdgeLog"
    assert WO.DEFAULT_CONFIG_PATH == r"C:\EdgeLog\webull_orders\config.json"
    assert WO.DEFAULT_PAPER_KEYS == r"C:\EdgeLog\webull_paper_keys.json"
    assert WO.DEFAULT_PAPER_TOKEN_DIR == r"C:\EdgeLog\webull_paper_token"
    assert WO.DEFAULT_LIVE_KEYS == r"C:\EdgeLog\webull_keys.json"
    assert WO.DEFAULT_LIVE_TOKEN_DIR == r"C:\EdgeLog\webull_token"
    assert WO.DEFAULT_ARM_LIVE_FILE == r"C:\EdgeLog\webull_orders\ARM_LIVE"
    assert WO.DEFAULT_KILL_FILE == r"C:\EdgeLog\webull_orders\KILL"
    assert WO.DEFAULT_STATE_PATH == r"C:\EdgeLog\webull_orders\state.json"


# ── EDGELOG_HOME override actually moves every default ─────────────────────────────
# A plain monkeypatch of os.environ + importlib.reload would work too, but a subprocess
# is cleaner here: it guarantees no other test's earlier import of these modules (with
# a stale EDGELOG_HOME baked into module-level constants) can leak into the assertion.

def _run_in_subprocess(code):
    env = dict(os.environ)
    result = subprocess.run([sys.executable, "-c", code], cwd=ROOT, env=env,
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, f"stderr:\n{result.stderr}\nstdout:\n{result.stdout}"
    return result.stdout.strip()


def test_qqq_exec_edgelog_home_override_moves_every_default(tmp_path):
    home = str(tmp_path / "cloud_home").replace("\\", "/")
    code = (
        "import os\n"
        f"os.environ['EDGELOG_HOME'] = {home!r}\n"
        "from api import qqq_exec as qe\n"
        "print(qe.OUT_DIR)\n"
        "print(qe.NQ_10S_PRIMARY)\n"
        "print(qe.NQ_10S_FALLBACK)\n"
        "print(qe.WEBULL_KEYS)\n"
        "print(qe.QQQ_EXEC_VBS)\n"
        "print(qe.DEFAULT_CONFIG['kill_file'])\n"
    )
    out = _run_in_subprocess(code).splitlines()
    assert out[0] == os.path.join(home, "qqq_exec")
    assert out[1] == os.path.join(home, "ohlc_addon", "NQ_10s.csv")
    assert out[2] == os.path.join(home, "ohlc", "NQ_10s.csv")
    assert out[3] == os.path.join(home, "webull_keys.json")
    assert out[4] == os.path.join(home, "_run_qqq_exec.vbs")
    assert out[5] == os.path.join(home, "qqq_exec", "KILL")


def test_webull_orders_edgelog_home_override_moves_every_default(tmp_path):
    home = str(tmp_path / "cloud_home").replace("\\", "/")
    code = (
        "import os\n"
        f"os.environ['EDGELOG_HOME'] = {home!r}\n"
        "from api import webull_orders as WO\n"
        "print(WO.DEFAULT_CONFIG_PATH)\n"
        "print(WO.DEFAULT_PAPER_KEYS)\n"
        "print(WO.DEFAULT_STATE_PATH)\n"
    )
    out = _run_in_subprocess(code).splitlines()
    assert out[0] == os.path.join(home, "webull_orders", "config.json")
    assert out[1] == os.path.join(home, "webull_paper_keys.json")
    assert out[2] == os.path.join(home, "webull_orders", "state.json")


# ── a specific env var still wins over EDGELOG_HOME ─────────────────────────────────

def test_specific_env_var_overrides_edgelog_home(tmp_path):
    home = str(tmp_path / "home").replace("\\", "/")
    override = str(tmp_path / "explicit_dir").replace("\\", "/")
    code = (
        "import os\n"
        f"os.environ['EDGELOG_HOME'] = {home!r}\n"
        f"os.environ['EDGELOG_QQQ_EXEC_DIR'] = {override!r}\n"
        "from api import qqq_exec as qe\n"
        "print(qe.OUT_DIR)\n"
    )
    out = _run_in_subprocess(code).strip()
    assert out == override


# ── ensure_standalone() on Linux: systemd, not the .vbs ────────────────────────────

def test_ensure_standalone_on_linux_falls_back_without_launching(tmp_path, monkeypatch):
    monkeypatch.setattr(qe, "SERVING_LOCK", str(tmp_path / "absent.lock"))
    monkeypatch.setattr(qe.os, "name", "posix")
    launched = []
    monkeypatch.setattr(qe.subprocess, "Popen", lambda *a, **k: launched.append(a))
    try:
        assert qe.ensure_standalone(log=lambda *_: None) is False
        assert launched == [], "Linux must never try to wscript.exe-launch the Windows .vbs"
    finally:
        monkeypatch.setattr(qe.os, "name", os.name)


def test_ensure_standalone_on_linux_skips_when_already_serving(tmp_path, monkeypatch):
    """Same as Windows: a fresh heartbeat (systemd unit's own tick) means the caller's
    fallback thread must stay off, regardless of OS."""
    lock = tmp_path / "SERVING.lock"
    lock.write_text(f"{os.getpid()} 2026-09-13 09:00:00\n", encoding="utf-8")
    monkeypatch.setattr(qe, "SERVING_LOCK", str(lock))
    monkeypatch.setattr(qe.os, "name", "posix")
    try:
        assert qe.ensure_standalone(log=lambda *_: None) is True
    finally:
        monkeypatch.setattr(qe.os, "name", os.name)


# ── "running on" label: EDGELOG_HOST_ROLE=cloud (the deploy/cloud/edgelog.env.example
# switch) shows CLOUD, same as the older EDGELOG_RUN_LOCATION ────────────────────────

def test_run_location_shows_cloud_via_host_role(monkeypatch):
    monkeypatch.delenv("EDGELOG_RUN_LOCATION", raising=False)
    monkeypatch.setenv("EDGELOG_HOST_ROLE", "cloud")
    assert qe._build_run_location()["label"] == "CLOUD"


def test_run_location_shows_cloud_via_run_location(monkeypatch):
    monkeypatch.delenv("EDGELOG_HOST_ROLE", raising=False)
    monkeypatch.setenv("EDGELOG_RUN_LOCATION", "cloud")
    assert qe._build_run_location()["label"] == "CLOUD"


def test_run_location_defaults_to_this_pc(monkeypatch):
    monkeypatch.delenv("EDGELOG_RUN_LOCATION", raising=False)
    monkeypatch.delenv("EDGELOG_HOST_ROLE", raising=False)
    assert qe._build_run_location()["label"] == "THIS PC"
