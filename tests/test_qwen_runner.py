"""tools/qwen_runner.py (AUTOMATIONS.md B3): pick order, guards, path refusals, file edits, inbox, crash resume."""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))
import qwen_runner as R  # noqa: E402

STATUS = ("# Qwen task board\r\n| # | Task | Status | Note |\r\n|---|------|--------|------|\r\n"
          "| Q1 | one | ✅ | x |\r\n| Q2 | two | ⭕ | y |\r\n| Q10 | ten | ⭕ | z |\r\n")


def _w(p, s):
    with open(p, "wb") as f:
        f.write(s.encode("utf-8"))


def _r(p):
    with open(p, "rb") as f:
        return f.read().decode("utf-8")


@pytest.fixture
def env(tmp_path, monkeypatch):
    t = tmp_path / "tasks"
    t.mkdir()
    h = tmp_path / "home"
    root = tmp_path / "root"
    root.mkdir()
    monkeypatch.setenv("QWEN_TASKS_DIR", str(t))
    monkeypatch.setenv("QWEN_RUNNER_HOME", str(h))
    _w(str(t / "README.md"), "RULES: be careful\r\n")
    _w(str(t / "STATUS.md"), STATUS)
    _w(str(t / "Q1-a.md"), "STATUS: ✅ closed\r\n# one\r\n")
    _w(str(t / "Q2-b.md"), "STATUS: ⭕ open\r\n# two\r\nread stuff\r\n")
    _w(str(t / "Q10-c.md"), "STATUS: ⭕ open\r\n# ten\r\n")
    return {"tasks": t, "home": h, "root": root}


class FakeChat:
    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []
        self.unloaded = False

    def chat(self, messages, tools):
        self.calls.append(messages)
        return self.replies.pop(0)

    def unload(self):
        self.unloaded = True


def tc(name, **args):
    return ({"content": "", "tool_calls": [{"function": {"name": name, "arguments": args}}]}, {"done_reason": "stop"})


def make(env, replies, posts, pushes, guards=None, **kw):
    fc = FakeChat(replies)
    r = R.Runner(chat_factory=lambda: fc, guards=guards or (lambda: (None, "")), sleep=lambda s: None,
                 poster=lambda n, w, one: posts.append((n, w, one)) or 7,
                 pusher=lambda n, ok, one: pushes.append((n, ok, one)) or (True, "ok"),
                 roots=[str(env["root"])], **kw)
    return r, fc


# ---------------------------------------------------------------- pick
def test_pick_lowest_open(env):
    assert R.pick_task()[0] == 2
    R.set_first_line(str(env["tasks"] / "Q2-b.md"), "STATUS: 🟢 done")
    assert R.pick_task()[0] == 10           # numeric, not lexical
    R.set_first_line(str(env["tasks"] / "Q10-c.md"), "STATUS: 🔴 blocked")
    assert R.pick_task() is None


def test_pick_falls_back_to_status_row(env):
    _w(str(env["tasks"] / "Q2-b.md"), "# no status line\r\n")
    assert R.pick_task()[0] == 2


# ---------------------------------------------------------------- guards
def _g(**kw):
    base = dict(yield_fn=lambda: (False, ""), quiet_fn=lambda: (False, None), lab_stop_fn=lambda: False,
                ps_fn=lambda: {"models": [{"name": "3.qwen3.6:35b-32k"}]})
    base.update(kw)
    return R.check_guards(**base)


def test_guards_clear(env):
    assert _g() == (None, "")


def test_guard_ram(env):
    assert _g(yield_fn=lambda: (True, "free RAM 4.0 GB"))[0] == "yield"


def test_guard_quiet(env):
    assert _g(quiet_fn=lambda: (True, "owner"))[0] == "yield"


def test_guard_lab_stop(env):
    assert _g(lab_stop_fn=lambda: True) == ("yield", "qwen_lab STOP file")


@pytest.mark.parametrize("name", ["1.qwen3.8-general:27b-48k", "2.coder:32b"])
def test_guard_owner_model(env, name):
    a, why = _g(ps_fn=lambda: {"models": [{"name": name}]})
    assert a == "yield" and name in why


def test_guard_ps_down_yields(env):
    def boom():
        raise OSError("down")
    assert _g(ps_fn=boom)[0] == "yield"


def test_guard_runner_stop(env):
    os.makedirs(str(env["home"]), exist_ok=True)
    _w(str(env["home"] / "STOP"), "x")
    assert _g()[0] == "stop"


def test_wait_guards_waits_then_goes(env):
    seq = [("yield", "ram"), ("yield", "ram"), (None, "")]
    slept = []
    r = R.Runner(guards=lambda: seq.pop(0), sleep=slept.append, chat_factory=lambda: None)
    assert r.wait_guards() is True and slept == [60, 60]


def test_stop_exits_cleanly(env):
    posts, pushes = [], []
    r, fc = make(env, [], posts, pushes, guards=lambda: ("stop", "runner STOP file"))
    assert r.run() == "stop"
    assert fc.calls == [] and R.first_line(str(env["tasks"] / "Q2-b.md")) == "STATUS: ⭕ open"


# ---------------------------------------------------------------- paths
def test_path_refusals(env, tmp_path):
    root = env["root"]
    (root / "ok.txt").write_text("hello\nworld\n", encoding="utf-8")
    assert "hello" in R.run_tool("read_file", {"path": str(root / "ok.txt")}, [str(root)])
    out = tmp_path / "outside.txt"
    out.write_text("x", encoding="utf-8")
    assert R.run_tool("read_file", {"path": str(out)}, [str(root)]).startswith("REFUSED")
    assert R.run_tool("read_file", {"path": str(root / ".." / "outside.txt")}, [str(root)]).startswith("REFUSED")
    for d in ["NinjaTrader 8", "webull_cfg", "TradingView", ".ssh"]:
        (root / d).mkdir()
        (root / d / "a.txt").write_text("x", encoding="utf-8")
        assert R.run_tool("read_file", {"path": str(root / d / "a.txt")}, [str(root)]).startswith("REFUSED"), d
    for n in ["api_key.txt", "token.json", "my_secret.md", "password.txt", "credentials.json", ".env", "x.pem"]:
        (root / n).write_text("x", encoding="utf-8")
        assert R.run_tool("read_file", {"path": str(root / n)}, [str(root)]).startswith("REFUSED"), n
    (root / "b.bin").write_bytes(b"\x00\x01\x02")
    assert "binary" in R.run_tool("read_file", {"path": str(root / "b.bin")}, [str(root)])
    listing = R.run_tool("list_dir", {"path": str(root)}, [str(root)])
    assert "ok.txt" in listing and ".env" not in listing and "NinjaTrader" not in listing
    g = R.run_tool("grep", {"pattern": "x|hello", "path_glob": str(root / "**" / "*")}, [str(root)])
    assert "ok.txt" in g and "NinjaTrader" not in g and ".pem" not in g
    assert R.run_tool("grep", {"pattern": "x", "path_glob": str(tmp_path / "*.txt")}, [str(root)]).startswith("REFUSED")


def test_read_file_cap_and_offset(env):
    p = env["root"] / "big.txt"
    p.write_text("\n".join("line %d %s" % (i, "y" * 50) for i in range(2000)), encoding="utf-8")
    out = R.run_tool("read_file", {"path": str(p)}, [str(env["root"])])
    assert len(out) < R.READ_CAP + 300 and "cut at" in out
    out = R.run_tool("read_file", {"path": str(p), "offset": 10, "limit": 2}, [str(env["root"])])
    assert "10\tline 9" in out and "12\t" not in out


# ---------------------------------------------------------------- full task: edits + inbox + push
def test_done_edits_status_inbox_push(env):
    (env["root"] / "f.txt").write_text("data", encoding="utf-8")
    posts, pushes = [], []
    r, fc = make(env, [tc("read_file", path=str(env["root"] / "f.txt")),
                       tc("finish", result_markdown="Found **data**.", status="done", one_line="all good " + "z" * 300)],
                 posts, pushes)
    assert r.run(once=True) == "done"
    q = _r(str(env["tasks"] / "Q2-b.md"))
    assert q.startswith("STATUS: 🟢 done - waiting for Claude check\r\n")
    assert "## RESULT\r\nFound **data**." in q and "UNVERIFIED" in q and "qwen_runner" in q and "2 turns" in q
    assert "\n" not in q.replace("\r\n", "")                      # CRLF kept, no bare LF
    s = _r(str(env["tasks"] / "STATUS.md"))
    assert "| Q2 | two | 🟢 | y |\r\n" in s and "| Q10 | ten | ⭕ | z |" in s and "| Q1 | one | ✅ |" in s
    assert posts == [(2, "🟢 DONE", ("all good " + "z" * 300)[:200])]
    assert pushes and pushes[0][1] is True
    assert fc.unloaded
    assert os.listdir(str(env["home"] / "transcripts"))[0].startswith("Q2-")
    assert json.load(open(str(env["home"] / "state.json"), encoding="utf-8"))["in_flight"] is None
    assert "Q2" in open(str(env["home"] / "runner.log"), encoding="utf-8").read()


def test_inbox_post_sender_qwen(env, monkeypatch):
    import chat_inbox
    seen = []
    monkeypatch.setattr(chat_inbox, "post", lambda chat, text, frm: seen.append((chat, text, frm)) or 1)
    R._post_inbox(4, "🔴 BLOCKED", "no fee column")
    assert seen == [("MANAGER", "QWEN Q4: 🔴 BLOCKED - no fee column", "QWEN")]


def test_blocked_finish(env):
    posts, pushes = [], []
    r, _ = make(env, [tc("finish", result_markdown="need python", status="blocked", one_line="needs code")],
                posts, pushes)
    r.run(once=True)
    assert R.first_line(str(env["tasks"] / "Q2-b.md")) == "STATUS: 🔴 blocked - needs code"
    assert R.status_row_icon(2) == "🔴" and posts[0][1] == "🔴 BLOCKED"


def test_marks_working_before_model(env):
    seen = {}

    class Peek(FakeChat):
        def chat(self, messages, tools):
            seen["line"] = R.first_line(str(env["tasks"] / "Q2-b.md"))
            seen["row"] = R.status_row_icon(2)
            seen["sys"] = messages[0]["content"]
            return tc("finish", result_markdown="x", status="done", one_line="ok")
    r = R.Runner(chat_factory=lambda: Peek([]), guards=lambda: (None, ""), sleep=lambda s: None,
                 poster=lambda *a: 1, pusher=lambda *a: (True, ""), roots=[str(env["root"])])
    r.run(once=True)
    assert seen["line"] == R.STATUS_WORKING and seen["row"] == "🟡"
    assert "RULES: be careful" in seen["sys"] and "read stuff" in seen["sys"]


def test_empty_replies_close_blocked(env):
    posts, pushes = [], []
    empty = ({"content": ""}, {"done_reason": "length"})
    r, fc = make(env, [empty, empty, empty], posts, pushes)
    assert r.run(once=True) == "blocked"
    assert len(fc.calls) == 3
    assert "no tool call" in R.first_line(str(env["tasks"] / "Q2-b.md"))
    assert fc.calls[1][-1]["role"] == "user"                       # nudged


def test_turn_budget(env):
    posts, pushes = [], []
    (env["root"] / "f.txt").write_text("d", encoding="utf-8")
    r, _ = make(env, [tc("list_dir", path=str(env["root"]))] * 3, posts, pushes, max_turns=3)
    assert r.run(once=True) == "blocked" and "turn budget" in posts[0][2]


def test_guard_checked_every_turn(env):
    posts, pushes = [], []
    calls = []

    def g():
        calls.append(1)
        return None, ""
    r, _ = make(env, [tc("list_dir", path=str(env["root"])),
                      tc("finish", result_markdown="x", status="done", one_line="ok")], posts, pushes, guards=g)
    r.run(once=True)
    assert len(calls) == 3                                         # before task + 2 turns


def test_stop_mid_task_resets_open(env):
    seq = [(None, ""), (None, ""), ("stop", "runner STOP file")]
    posts, pushes = [], []
    r, _ = make(env, [tc("list_dir", path=str(env["root"]))], posts, pushes, guards=lambda: seq.pop(0))
    assert r.run(once=True) == "stopped"
    assert R.first_line(str(env["tasks"] / "Q2-b.md")) == "STATUS: ⭕ open" and R.status_row_icon(2) == "⭕"
    assert posts == []


# ---------------------------------------------------------------- crash resume
def _crash(env):
    """Simulate a runner that died mid-task on Q2."""
    posts, pushes = [], []

    class Die(FakeChat):
        def chat(self, messages, tools):
            raise KeyboardInterrupt
    r = R.Runner(chat_factory=lambda: Die([]), guards=lambda: (None, ""), sleep=lambda s: None,
                 poster=lambda *a: posts.append(a) or 1, pusher=lambda *a: (True, ""), roots=[str(env["root"])])
    with pytest.raises(KeyboardInterrupt):
        r.run(once=True)
    assert R.first_line(str(env["tasks"] / "Q2-b.md")) == R.STATUS_WORKING
    return posts


def test_crash_resume_once_then_blocked(env):
    _crash(env)
    posts, pushes = [], []
    r, _ = make(env, [], posts, pushes)
    r.resume()
    assert R.first_line(str(env["tasks"] / "Q2-b.md")) == "STATUS: ⭕ open" and R.status_row_icon(2) == "⭕"
    _crash(env)
    r, _ = make(env, [], posts, pushes)
    r.resume()
    assert R.first_line(str(env["tasks"] / "Q2-b.md")).startswith("STATUS: 🔴 blocked - runner died")
    assert R.status_row_icon(2) == "🔴" and posts[0][1] == "🔴 BLOCKED"


def test_resume_ignores_tasks_not_left_working(env):
    os.makedirs(str(env["home"]), exist_ok=True)
    json.dump({"in_flight": {"n": 2, "path": str(env["tasks"] / "Q2-b.md")}},
              open(str(env["home"] / "state.json"), "w", encoding="utf-8"))
    r, _ = make(env, [], [], [])
    r.resume()
    assert R.first_line(str(env["tasks"] / "Q2-b.md")) == "STATUS: ⭕ open"


def test_status_icon_keeps_bom_and_crlf(env):
    p = str(env["tasks"] / "STATUS.md")
    with open(p, "wb") as f:
        f.write(b"\xef\xbb\xbf" + STATUS.encode("utf-8"))
    assert R.set_status_icon(10, "🟡")
    raw = open(p, "rb").read()
    assert raw.startswith(b"\xef\xbb\xbf") and raw.decode("utf-8-sig") == STATUS.replace("| Q10 | ten | ⭕", "| Q10 | ten | 🟡")
