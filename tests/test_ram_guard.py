"""tools/ram_guard.py (AUTOMATIONS.md B2) - fake memory readings, fake pusher; no real push, no real STOP."""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))
import ram_guard as G  # noqa: E402


@pytest.fixture(autouse=True)
def _paths(tmp_path, monkeypatch):
    monkeypatch.setenv("RAM_GUARD_STOP", str(tmp_path / "qwen_lab" / "STOP"))
    monkeypatch.setenv("RAM_GUARD_STATE", str(tmp_path / "state" / "ram_guard.json"))
    monkeypatch.setattr(G, "send_push", lambda *a, **k: pytest.fail("real push path called"))
    return tmp_path


class Pusher:
    def __init__(self):
        self.calls = []

    def __call__(self, ram):
        self.calls.append(ram)
        return True, "sent"


def test_should_yield_ram_and_vram():
    assert G.should_yield(ram_fn=lambda: 4.0)[0] is True
    assert G.should_yield(ram_fn=lambda: 10.0)[0] is False
    assert G.should_yield(ram_fn=lambda: None)[0] is False
    y, why = G.should_yield(ram_fn=lambda: 10.0, min_free_vram_gb=2.0, vram_fn=lambda: 1.0)
    assert y and "VRAM" in why
    assert G.should_yield(ram_fn=lambda: 10.0, min_free_vram_gb=2.0, vram_fn=lambda: None)[0] is False


def test_low_ram_writes_stop_and_pushes_once_per_30_min():
    p = Pusher()
    G.watch_once(now=1000, ram_fn=lambda: 4.0, pusher=p, log=lambda *_: None)
    stop = G.stop_path()
    with open(stop, encoding="utf-8") as f:
        lines = f.read().splitlines()
    assert lines[0] == G.STOP_HEADER and lines[1].startswith("reason: free RAM 4.0")
    G.watch_once(now=1000 + 600, ram_fn=lambda: 4.0, pusher=p, log=lambda *_: None)
    assert len(p.calls) == 1
    G.watch_once(now=1000 + 1800, ram_fn=lambda: 4.0, pusher=p, log=lambda *_: None)
    assert len(p.calls) == 2
    with open(G.state_path(), encoding="utf-8") as f:
        assert json.load(f)["last_push"] == 2800


def test_own_stop_removed_after_10_min_above_8_gb():
    p, quiet = Pusher(), (lambda *_: None)
    G.watch_once(now=0, ram_fn=lambda: 4.0, pusher=p, log=quiet)
    G.watch_once(now=60, ram_fn=lambda: 9.0, pusher=p, log=quiet)
    G.watch_once(now=400, ram_fn=lambda: 7.0, pusher=p, log=quiet)       # dip to 6-8 resets the clock
    G.watch_once(now=460, ram_fn=lambda: 9.0, pusher=p, log=quiet)
    G.watch_once(now=1000, ram_fn=lambda: 9.0, pusher=p, log=quiet)
    assert os.path.exists(G.stop_path())
    G.watch_once(now=1060, ram_fn=lambda: 9.0, pusher=p, log=quiet)
    assert not os.path.exists(G.stop_path())


def test_foreign_stop_never_removed_nor_overwritten():
    stop = G.stop_path()
    os.makedirs(os.path.dirname(stop))
    with open(stop, "w", encoding="utf-8") as f:
        f.write("owner stop\n")
    p = Pusher()
    G.watch_once(now=0, ram_fn=lambda: 4.0, pusher=p, log=lambda *_: None)
    G.watch_once(now=10, ram_fn=lambda: 20.0, pusher=p, log=lambda *_: None)
    G.watch_once(now=10000, ram_fn=lambda: 20.0, pusher=p, log=lambda *_: None)
    with open(stop, encoding="utf-8") as f:
        assert f.read() == "owner stop\n"
    assert len(p.calls) == 1


def test_check_exit_codes(monkeypatch):
    monkeypatch.setattr(G, "free_vram_gb", lambda: None)
    monkeypatch.setattr(G, "quiet_on", lambda: (False, None))
    monkeypatch.setattr(G, "free_ram_gb", lambda: 12.0)
    assert G.check(log=lambda *_: None) == 0
    monkeypatch.setattr(G, "free_ram_gb", lambda: 3.0)
    assert G.check(log=lambda *_: None) == 2
    monkeypatch.setattr(G, "free_ram_gb", lambda: 12.0)
    monkeypatch.setattr(G, "quiet_on", lambda: (True, "local flag"))
    assert G.check(log=lambda *_: None) == 2


def test_qwen_lab_waits_on_the_guard(monkeypatch):
    import qwen_lab as Q
    monkeypatch.setattr(Q, "push_lock_state", lambda: (False, ""))
    monkeypatch.delenv("QWEN_LAB_RAM_GUARD", raising=False)
    monkeypatch.setattr(G, "free_ram_gb", lambda: 2.0)
    held, who = Q.load_hold_state()
    assert held and "ram_guard" in who
    monkeypatch.setattr(G, "free_ram_gb", lambda: 20.0)
    assert Q.load_hold_state() == (False, "")
    monkeypatch.setenv("QWEN_LAB_RAM_GUARD", "0")
    monkeypatch.setattr(G, "free_ram_gb", lambda: 2.0)
    assert Q.load_hold_state() == (False, "")
