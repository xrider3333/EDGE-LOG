"""The 'other'-bucket metering hooks in api/nt_heartbeat.py and api/paper.py must find the
LIVE runner's _note_reads through sys.modules ('__main__' first -- the runner is launched
as `python -m api.runner` -- then an already-imported 'api.runner'), and must NEVER import
api.runner themselves: a fresh import would build a second _ReadMeter that nothing prints,
so those reads would vanish from the `[reads]` line (review finding, 2026-09-08)."""
import os
import sys
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from api import nt_heartbeat, paper  # noqa: E402


def _with_fake_main(monkeypatch, calls):
    fake_main = types.ModuleType("__main__")
    fake_main._note_reads = lambda bucket, n: calls.append((bucket, n))
    monkeypatch.setitem(sys.modules, "__main__", fake_main)
    # make a fresh `import api.runner` loud, so a regression is caught rather than hidden
    monkeypatch.setitem(sys.modules, "api.runner", None)


def test_heartbeat_hook_routes_to_live_main_module(monkeypatch):
    calls = []
    _with_fake_main(monkeypatch, calls)
    nt_heartbeat._note_read()
    assert calls == [("other", 1)]


def test_paper_hook_routes_to_live_main_module_with_min_one(monkeypatch):
    calls = []
    _with_fake_main(monkeypatch, calls)
    paper._note_reads_other(0)
    paper._note_reads_other(7)
    assert calls == [("other", 1), ("other", 7)]


def test_hooks_are_silent_when_no_runner_is_loaded(monkeypatch):
    monkeypatch.setitem(sys.modules, "__main__", types.ModuleType("__main__"))
    monkeypatch.setitem(sys.modules, "api.runner", None)
    nt_heartbeat._note_read()          # must not raise, must not import api.runner
    paper._note_reads_other(3)
    assert sys.modules.get("api.runner") is None
