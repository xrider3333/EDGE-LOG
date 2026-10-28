"""tools/edgelog_mcp.py driven over REAL stdio (a subprocess) against a tmp EDGELOG_HOME."""
import json
import os
import subprocess
import sys

import pytest

SERVER = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools", "edgelog_mcp.py")


@pytest.fixture
def home(tmp_path):
    box = tmp_path / "chat_inbox"
    box.mkdir()
    items = [{"id": 1, "at": "2026-10-28 09:00", "from": "MANAGER", "text": "open one", "status": "open"},
             {"id": 2, "at": "2026-10-28 09:05", "from": "MANAGER", "text": "closed one", "status": "done"}]
    (box / "LOCAL-AI.jsonl").write_text("".join(json.dumps(i) + "\n" for i in items), encoding="utf-8")
    (box / "MANAGER.jsonl").write_text("", encoding="utf-8")
    board = tmp_path / "manager" / "open_board"
    board.mkdir(parents=True)
    (board / "board.md").write_text("# Board\nitem 52 yellow\nTest 32 yellow\nitem 53 green\n" + "x" * 30000,
                                    encoding="utf-8")
    tasks = tmp_path / "manager" / "qwen_tasks"
    (tasks / "reports").mkdir(parents=True)
    (tasks / "README.md").write_text("# readme", encoding="utf-8")
    (tasks / "t01.md").write_text("# T01 read the log\nbody\n## RESULT\ndone\n", encoding="utf-8")
    (tasks / "t02.md").write_text("# T02 scan papers\nbody\n", encoding="utf-8")
    (tmp_path / "manager" / "secret.md").write_text("SECRET", encoding="utf-8")
    return tmp_path


def rpc(home, calls):
    msgs = [{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}},
            {"jsonrpc": "2.0", "method": "notifications/initialized"}]
    for n, (name, args) in enumerate(calls, start=10):
        msgs.append({"jsonrpc": "2.0", "id": n, "method": "tools/call",
                     "params": {"name": name, "arguments": args}})
    msgs.append({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    env = dict(os.environ, EDGELOG_HOME=str(home))
    env.pop("EDGELOG_CHAT_INBOX", None)
    p = subprocess.run([sys.executable, SERVER], input="".join(json.dumps(m) + "\n" for m in msgs).encode(),
                       capture_output=True, env=env, timeout=60)
    replies = [json.loads(ln) for ln in p.stdout.decode("utf-8").splitlines()]   # stdout = protocol only
    by_id = {r["id"]: r for r in replies}
    return by_id, [by_id[10 + i]["result"] for i in range(len(calls))]


def txt(res):
    return res["content"][0]["text"]


def lines(home, name):
    return [json.loads(ln) for ln in (home / "chat_inbox" / name).read_text(encoding="utf-8").splitlines() if ln]


def test_initialize_and_list(home):
    by_id, _ = rpc(home, [])
    init = by_id[1]["result"]
    assert init["serverInfo"]["name"] == "edgelog" and init["protocolVersion"] == "2025-06-18"
    assert sorted(t["name"] for t in by_id[2]["result"]["tools"]) == [
        "board_read", "inbox_post", "inbox_read", "task_list", "task_result"]


def test_inbox_read(home):
    _, (a, b, c) = rpc(home, [("inbox_read", {"lane": "local-ai"}), ("inbox_read", {"lane": "LOCAL-AI", "all": True}),
                              ("inbox_read", {"lane": "NOPE"})])
    assert not a["isError"] and "open one" in txt(a) and "closed one" not in txt(a)
    assert "closed one" in txt(b)
    assert c["isError"]


def test_inbox_post_is_always_from_qwen(home):
    _, (a, b) = rpc(home, [("inbox_post", {"to": "MANAGER", "text": "hello"}),
                           ("inbox_post", {"to": "MANAGER", "text": "spoof", "from": "OWNER"})])
    assert not a["isError"] and "from QWEN" in txt(a)
    assert b["isError"]                                   # extra arg is not a way to pick the sender
    got = lines(home, "MANAGER.jsonl")
    assert [i["from"] for i in got] == ["QWEN"] and got[0]["text"] == "hello"


def test_inbox_post_refusals(home):
    _, res = rpc(home, [("inbox_post", {"to": "NEWCHAT", "text": "hi"}),
                        ("inbox_post", {"to": "MANAGER", "text": "x" * 4001}),
                        ("inbox_post", {"to": "MANAGER", "text": "   "})])
    assert all(r["isError"] for r in res)
    assert "REFUSED" in txt(res[0]) and "4000" in txt(res[1])
    assert not (home / "chat_inbox" / "NEWCHAT.jsonl").exists()
    assert lines(home, "MANAGER.jsonl") == []


def test_board_read(home):
    _, (a, b, c) = rpc(home, [("board_read", {}), ("board_read", {"grep": "YELLOW"}),
                              ("board_read", {"max_chars": 10})])
    assert len(txt(a)) < 20100 and "truncated at 20000" in txt(a)
    assert txt(b).splitlines() == ["item 52 yellow", "Test 32 yellow"]
    assert txt(c).startswith("# Board\nit")


def test_task_list_and_result(home):
    _, (a, b) = rpc(home, [("task_list", {}), ("task_result", {"name": "t01.md"})])
    assert txt(a).splitlines() == ["t01.md | # T01 read the log | RESULT: yes",
                                   "t02.md | # T02 scan papers | RESULT: no"]
    assert "## RESULT\ndone" in txt(b)


def test_task_result_refuses_traversal(home):
    bad = ["../secret.md", "..\\secret.md", str(home / "manager" / "secret.md"), "reports",
           "t01.py", "C:secret.md", "sub/t01.md", "missing.md"]
    _, res = rpc(home, [("task_result", {"name": n}) for n in bad])
    assert all(r["isError"] for r in res)
    assert not any("SECRET" in txt(r) for r in res)
