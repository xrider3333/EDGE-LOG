import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))
import qwen_cascade as Q  # noqa: E402


def fake(replies):
    seen = []

    def chat(msgs):
        seen.append(list(msgs))
        return replies[len(seen) - 1]
    return chat, seen


def test_pass_first_try_strips_think_and_fence():
    chat, _ = fake(['<think>hm</think>```json\n{"a": 1}\n```'])
    r = Q.cascade("p", Q.json_check(["a"]), chat=chat)
    assert r["ok"] and r["tries"] == 1 and r["answer"] == '{"a": 1}' and not r["escalate"]


def test_retry_feeds_reason_back_then_passes():
    chat, seen = fake(["nope", '{"a": 2}'])
    r = Q.cascade("p", Q.json_check(["a"]), chat=chat)
    assert r["ok"] and r["tries"] == 2
    assert "failed the check" in seen[1][-1]["content"]


def test_escalates_after_tries():
    chat, _ = fake(["x", "y", "z"])
    r = Q.cascade("p", Q.json_check(), tries=3, chat=chat)
    assert r["escalate"] and not r["ok"] and len(r["why"]) == 3


def test_unreachable_model_escalates():
    def chat(msgs):
        raise OSError("refused")
    r = Q.cascade("p", Q.json_check(), chat=chat)
    assert r["escalate"] and "unreachable" in r["why"][0]


def test_pydantic_check_with_contracts():
    import contracts as C
    chk = Q.pydantic_check(C.InboxItem)
    assert chk('{"id": 1, "at": "2026-10-30 13:43", "from": "M", "text": "x", "status": "open"}')[0]
    assert not chk('{"id": 1}')[0]
