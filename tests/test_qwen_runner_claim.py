"""tools/qwen_runner.py MANAGER #225 (Q13 deadlock 10-30): claim late, release after a long yield, re-open stale 🟡,
Cline busy = a router request in the last 60 s (the runner's own requests never count)."""
import json
import os
import sys
import time

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))
import qwen_runner as R  # noqa: E402

STATUS = ("# Qwen task board\r\n| # | Task | Status | Note |\r\n|---|------|--------|------|\r\n"
          "| Q2 | two | ⭕ | y |\r\n| Q3 | three | 🟡 | 2026-10-30 started 16:14 |\r\n")


def _w(p, s):
    with open(p, "wb") as f:
        f.write(s.encode("utf-8"))


@pytest.fixture
def env(tmp_path, monkeypatch):
    t = tmp_path / "tasks"
    t.mkdir()
    h = tmp_path / "home"
    monkeypatch.setenv("QWEN_TASKS_DIR", str(t))
    monkeypatch.setenv("QWEN_RUNNER_HOME", str(h))
    monkeypatch.setenv("QWEN_CLINE_DIRS", "")
    monkeypatch.setattr(R, "strata_slots", lambda get=None: None)
    _w(str(t / "README.md"), "RULES\r\n")
    _w(str(t / "STATUS.md"), STATUS)
    _w(str(t / "Q2-b.md"), "STATUS: ⭕ open\r\n# two\r\n")
    return {"tasks": t, "home": h}


class Chat:
    def __init__(self, seen=None):
        self.calls, self.seen = 0, seen

    def chat(self, messages, tools):
        self.calls += 1
        if self.seen is not None:
            self.seen.append(R.first_line(os.path.join(R.tasks_dir(), "Q2-b.md")))
        return ({"content": "", "tool_calls": [{"function": {"name": "finish", "arguments": {
            "result_markdown": "x", "status": "done", "one_line": "ok"}}}]}, {})


def runner(guards, chat):
    return R.Runner(chat_factory=lambda: chat, guards=guards, sleep=lambda s: None,
                    poster=lambda *a: 1, pusher=lambda *a: (True, ""))


def q2():
    return R.first_line(os.path.join(R.tasks_dir(), "Q2-b.md"))


def test_claim_late_task_stays_open_while_guards_yield(env):
    states = []
    seq = [(None, "")] + [("yield", "Cline mid-task")] * 30 + [(None, "")]

    def g():
        states.append((q2(), R.status_row_icon(2)))
        return seq.pop(0)
    seen = []
    r = runner(g, Chat(seen))
    assert r.run(once=True) == "done"
    assert all(s == ("STATUS: ⭕ open", "⭕") for s in states)     # never 🟡 while waiting (30 min, unclaimed)
    assert seen == [R.STATUS_WORKING]                               # claimed right before the first call


def test_taken_by_cline_while_waiting_is_left_alone(env):
    seq = [(None, ""), ("yield", "Cline")]

    def g():
        if not seq:
            _w(str(env["tasks"] / "Q2-b.md"), "STATUS: 🟡 Cline working\r\n# two\r\n")
            return None, ""
        return seq.pop(0)
    c = Chat()
    assert runner(g, c).run(once=True) == "idle"
    assert c.calls == 0 and q2() == "STATUS: 🟡 Cline working"


def test_release_after_long_yield_not_counted(env):
    seq = [(None, ""), (None, ""), (None, "")] + [("yield", "Cline mid-task")] * 20

    class Tool(Chat):
        def chat(self, messages, tools):
            self.calls += 1
            return ({"content": "", "tool_calls": [{"function": {"name": "list_dir", "arguments": {"path": "C:\\x"}}}]}, {})
    r = runner(lambda: seq.pop(0), Tool())
    assert r.run(once=True) == "released"
    assert q2() == "STATUS: ⭕ open" and R.status_row_icon(2) == "⭕"
    assert "released - owner busy" in R.status_note(2) and R.status_note(2).startswith("20")
    st = r.load_state()
    assert st["in_flight"] is None and st["attempts"]["Q2"] == 0


def test_short_yield_keeps_claim(env):
    seq = [(None, ""), (None, "")] + [("yield", "Cline")] * 5 + [(None, "")]
    calls = []

    class Two(Chat):
        def chat(self, messages, tools):
            calls.append(q2())
            if len(calls) == 1:
                return ({"content": "", "tool_calls": [{"function": {"name": "list_dir", "arguments": {"path": "C:\\x"}}}]}, {})
            return super().chat(messages, tools)
    assert runner(lambda: seq.pop(0), Two()).run(once=True) == "done"
    assert calls == [R.STATUS_WORKING, R.STATUS_WORKING]


def _age(p, secs):
    t = time.time() - secs
    os.utime(p, (t, t))


def test_stale_working_reopened(env):
    p = str(env["tasks"] / "Q3-c.md")
    _w(p, "STATUS: 🟡 Qwen working\r\n# three\r\n")
    os.makedirs(str(env["home"] / "transcripts"), exist_ok=True)
    tp = str(env["home"] / "transcripts" / "Q3-20261030-161400.json")
    _w(tp, "{}")
    _age(p, 25 * 60)
    _age(tp, 25 * 60)
    r = runner(lambda: (None, ""), Chat())
    assert r.reopen_stale(now=time.time()) == [3]
    assert R.first_line(p) == "STATUS: ⭕ open" and R.status_row_icon(3) == "⭕"
    assert "re-opened" in R.status_note(3)


def test_stale_not_reopened_while_transcript_grows(env):
    p = str(env["tasks"] / "Q3-c.md")
    _w(p, "STATUS: 🟡 Qwen working\r\n# three\r\n")
    os.makedirs(str(env["home"] / "transcripts"), exist_ok=True)
    _w(str(env["home"] / "transcripts" / "Q3-x.json"), "{}")      # fresh
    _age(p, 60 * 60)
    assert runner(lambda: (None, ""), Chat()).reopen_stale(now=time.time()) == []
    assert R.first_line(p) == R.STATUS_WORKING


def test_never_reopens_own_active_task(env):
    p = str(env["tasks"] / "Q2-b.md")
    r = runner(lambda: (None, ""), Chat())
    r.claim(2, p)
    _age(p, 40 * 60)                                                # file old, but own transcript fresh
    os.makedirs(str(env["home"] / "transcripts"), exist_ok=True)
    _w(str(env["home"] / "transcripts" / "Q2-20261030-170000.json"), "{}")
    assert r.reopen_stale(now=time.time()) == []
    assert q2() == R.STATUS_WORKING and r.load_state()["in_flight"]["n"] == 2


def test_foreign_working_without_started_note_left_alone(env):
    p = str(env["tasks"] / "Q4-d.md")
    _w(p, "STATUS: 🟡 Claude checking\r\n# four\r\n")
    _age(p, 60 * 60)
    assert runner(lambda: (None, ""), Chat()).reopen_stale(now=time.time()) == []


def test_cline_busy_from_router_timestamp(tmp_path):
    now = 1_000_000.0
    assert R.cline_busy([], now=now, last_fn=lambda: {"ts": now - 30, "model": "2.x", "active": 0})[0] is True
    assert R.cline_busy([], now=now, last_fn=lambda: {"ts": now - 90, "model": "2.x", "active": 0}) == (False, "")
    assert R.cline_busy([], now=now, last_fn=lambda: {"ts": now - 300, "model": "2.x", "active": 1})[0] is True
    assert R.cline_busy([], now=now, last_fn=lambda: {"ts": now - 7200, "model": "2.x", "active": 1}) == (False, "")


def test_router_file_read_and_fallback(tmp_path, monkeypatch):
    f = tmp_path / "last.json"
    monkeypatch.setenv("QWEN_ROUTER_LAST", str(f))
    d = tmp_path / "sess" / "abc"
    d.mkdir(parents=True)
    _w(str(d / "abc.json"), "{}")
    now = time.time()
    assert R.cline_busy([str(tmp_path / "sess")], now=now)[0] is True        # no router file -> session test
    f.write_text(json.dumps({"ts": now - 120, "active": 0}), encoding="utf-8")
    assert R.cline_busy([str(tmp_path / "sess")], now=now) == (False, "")    # router says idle: wins


def test_runner_requests_carry_header(monkeypatch):
    seen = {}

    class Resp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return b"{}"
    import urllib.request

    def fake(req, timeout=None):
        seen.update({k.lower(): v for k, v in req.header_items()})
        return Resp()
    monkeypatch.setattr(urllib.request, "urlopen", fake)
    R.router_http("/chat/completions", {"model": "5.x"})
    assert seen.get("x-qwen-runner") == "1"


def test_router_skips_runner_requests():
    """The router (C:\\EdgeLog\\llm_router\\router.py, not in git) records only POSTs without X-Qwen-Runner."""
    p = r"C:\EdgeLog\llm_router\router.py"
    if not os.path.exists(p):
        pytest.skip("router not on this PC")
    src = open(p, encoding="utf-8").read()
    i = src.index("def do_POST")
    body = src[i:src.index("def _proxy", i)]
    assert 'X-Qwen-Runner' in body and body.index("X-Qwen-Runner") < body.index("mark_request")


# ---------------------------------------------------------------- MANAGER #226: Cline is the primary worker
def test_cline_running_needs_process_and_recent_activity():
    now = 1_000_000.0
    act = lambda: {"ts": now - 20 * 60, "active": 0}           # noqa: E731
    assert R.cline_running(lambda: True, act, [], now)[0] is True
    assert R.cline_running(lambda: False, act, [], now) == (False, "")          # no VS Code process
    old = lambda: {"ts": now - 31 * 60, "active": 0}           # noqa: E731
    assert R.cline_running(lambda: True, old, [], now) == (False, "")           # idle 30 min


def test_guards_yield_while_cline_running(env):
    g = R.check_guards(yield_fn=lambda: (False, ""), quiet_fn=lambda: (False, ""), lab_stop_fn=lambda: False,
                       ps_fn=lambda: [], cline_fn=lambda: (False, ""),
                       running_fn=lambda: (True, "Cline is running"))
    assert g[0] == "yield" and "Cline" in g[1]


def test_no_foreign_reopen_while_cline_running(env):
    p = str(env["tasks"] / "Q3-c.md")
    _w(p, "STATUS: 🟡 Qwen working\r\n# three\r\n")
    _age(p, 60 * 60)
    r = R.Runner(chat_factory=lambda: None, guards=lambda: (None, ""), sleep=lambda s: None,
                 running_fn=lambda: (True, "on"))
    assert r.reopen_stale(now=time.time()) == []
    r.running_fn = lambda: (False, "")
    assert r.reopen_stale(now=time.time()) == [3]
