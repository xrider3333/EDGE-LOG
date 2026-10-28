"""tools/qwen_runner.py Strata (OpenAI /v1) backend, MANAGER #211: selection, tool-call parsing, length, guards."""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))
import qwen_runner as R  # noqa: E402
from test_qwen_runner import env, make, tc, _w, _r  # noqa: E402,F401

LOADED = {"object": "list", "data": [{"id": R.STRATA_MODEL, "status": {"value": "loaded"},
                                      "meta": {"n_ctx": 262144}}]}


def http_of(models=LOADED, replies=(), sent=None):
    replies = list(replies)

    def http(path, payload=None, timeout=None):
        if sent is not None:
            sent.append((path, payload, timeout))
        if path == "/models":
            if isinstance(models, Exception):
                raise models
            return models
        return replies.pop(0)
    return http


# ---------------------------------------------------------------- selection
def test_auto_picks_strata_when_loaded():
    assert R.select_backend("auto", http_of()) == "strata"


@pytest.mark.parametrize("models", [
    {"data": [{"id": R.STRATA_MODEL, "status": {"value": "loading"}}]},
    {"data": [{"id": "other-model", "status": {"value": "loaded"}}]},
    {"data": []},
    OSError("refused"),
])
def test_auto_falls_back_to_ollama(models):
    assert R.select_backend("auto", http_of(models)) == "ollama"


def test_forced_backends_skip_the_probe():
    def boom(*a, **k):
        raise AssertionError("no probe")
    assert R.select_backend("strata", boom) == "strata"
    assert R.select_backend("ollama", boom) == "ollama"


def test_selection_rechecked_before_each_task(env):
    seen = []
    r, fc = make(env, [tc("finish", result_markdown="a", status="done", one_line="one"),
                       tc("finish", result_markdown="b", status="done", one_line="two")], [], [],
                 backend="auto", selector=lambda c: seen.append(c) or ("strata" if len(seen) == 1 else "ollama"))
    r.cycle()
    assert r.cur == "strata"
    assert "backend strata" in _r(str(env["tasks"] / "Q2-b.md"))
    r.cycle()
    assert r.cur == "ollama" and seen == ["auto", "auto"]
    assert "backend ollama" in _r(str(env["tasks"] / "Q10-c.md"))


def test_no_probe_when_board_is_empty(env):
    for n in (2, 10):
        p = [x for x in os.listdir(str(env["tasks"])) if x.startswith("Q%d-" % n)][0]
        R.set_first_line(str(env["tasks"] / p), "STATUS: 🟢 done")
    seen = []
    r, _ = make(env, [], [], [], backend="auto", selector=lambda c: seen.append(c) or "strata")
    assert r.cycle() == "idle" and seen == []


# ---------------------------------------------------------------- OpenAI call + parsing
def test_strata_chat_payload_and_tool_call_parsing():
    sent = []
    reply = {"choices": [{"finish_reason": "tool_calls", "message": {"role": "assistant", "content": None,
             "tool_calls": [{"id": "c1", "type": "function",
                             "function": {"name": "list_dir", "arguments": "{\"path\": \"C:\\\\EdgeLog\"}"}}]}}],
             "usage": {"prompt_tokens": 50, "completion_tokens": 9}}
    ch = R.StrataChat(http=http_of(replies=[reply], sent=sent))
    assert ch.num_ctx == 262144
    assert ch.ctx_limit == R.STRATA_CTX_CAP_TOK * R.CHARS_PER_TOK
    msgs = [{"role": "system", "content": "s"}, {"role": "user", "content": "u"},
            {"role": "assistant", "content": "", "tool_calls": [{"function": {"name": "grep", "arguments": {"a": 1}}}]},
            {"role": "tool", "content": "res", "tool_name": "grep"}]
    msg, stats = ch.chat(msgs, R.TOOLS)
    path, payload, _ = sent[-1]
    assert path == "/chat/completions"
    assert payload["temperature"] == 0.2 and payload["model"] == R.STRATA_MODEL
    assert "keep_alive" not in json.dumps(payload) and "options" not in payload
    assert payload["tools"][0] == {"type": "function", "function": R.TOOLS[0]}
    a = payload["messages"][2]
    assert a["tool_calls"][0]["function"]["arguments"] == "{\"a\": 1}" and a["tool_calls"][0]["type"] == "function"
    assert payload["messages"][3]["tool_call_id"] == a["tool_calls"][0]["id"]
    assert msg["tool_calls"][0]["function"] == {"name": "list_dir", "arguments": "{\"path\": \"C:\\\\EdgeLog\"}"}
    assert stats["done_reason"] == "tool_calls" and stats["prompt_tokens"] == 50


def test_ctx_limit_small_server():
    assert R.strata_ctx_limit(65536) == (65536 - R.STRATA_REPLY_TOK) * 4
    assert R.strata_ctx_limit(None) == R.CTX_LIMIT


def test_strata_has_no_unload():
    assert not hasattr(R.StrataChat, "unload")


def test_runner_parses_string_arguments_and_links_ids(env):
    os.makedirs(str(env["root"] / "d"), exist_ok=True)
    reps = [({"content": "", "tool_calls": [{"id": "c9", "function": {"name": "list_dir",
                                                                        "arguments": json.dumps({"path": str(env["root"])})}}]},
             {"done_reason": "tool_calls"}),
            ({"content": "", "tool_calls": [{"id": "c10", "function": {"name": "finish", "arguments": json.dumps(
                {"result_markdown": "found d", "status": "done", "one_line": "ok"})}}]}, {"done_reason": "tool_calls"})]
    r, fc = make(env, reps, [], [])
    assert r.cycle() == "done"
    tool_msg = [m for m in fc.calls[1] if m.get("role") == "tool"][0]
    assert tool_msg["tool_call_id"] == "c9" and "d/" in tool_msg["content"]
    out = R.to_openai_messages(fc.calls[1])
    assert out[-1]["tool_call_id"] == "c9"


def test_length_finish_reason_handled_like_ollama(env):
    d = {"choices": [{"finish_reason": "length", "message": {"content": "partial..."}}]}
    msg, stats = R.parse_openai_reply(d)
    assert stats["done_reason"] == "length" and "tool_calls" not in msg

    class Big:
        model, num_ctx, ctx_limit = R.STRATA_MODEL, 262144, 800000

        def __init__(self):
            self.limits = []

        def chat(self, messages, tools):
            return msg, stats
    big = Big()
    seen = []
    orig = R.compact
    R.compact = lambda m, limit, keep: seen.append(limit) or m
    try:
        r = R.Runner(chat_factory=lambda: big, guards=lambda: (None, ""), sleep=lambda s: None,
                     poster=lambda *a: 1, pusher=lambda *a: (True, ""), roots=[str(env["root"])], backend="strata")
        assert r.cycle() == "blocked"
    finally:
        R.compact = orig
    assert seen == [800000, 400000, 200000]          # starts at the Strata budget, halves on each length cut
    t = _r(str(env["tasks"] / "Q2-b.md"))
    assert "cut at the context limit" in t and "backend strata · model %s (num_ctx 262144)" % R.STRATA_MODEL in t


def test_error_reply_raises():
    with pytest.raises(RuntimeError):
        R.parse_openai_reply({"error": {"message": "bad"}})


# ---------------------------------------------------------------- guards
def _gs(**kw):
    base = dict(yield_fn=lambda: (True, "free RAM 2.0 GB"), quiet_fn=lambda: (False, None), lab_stop_fn=lambda: False,
                ps_fn=lambda: {"models": [{"name": "2.qwen3.6:35b-256k"}]}, alive_fn=lambda: (True, ""),
                backend="strata")
    base.update(kw)
    return R.check_guards(**base)


def test_strata_skips_ram_and_owner_model(env):
    assert _gs() == (None, "")


def test_ollama_keeps_ram_and_owner_model(env):
    assert _gs(backend="ollama")[0] == "yield"
    assert _gs(backend="ollama", yield_fn=lambda: (False, ""))[0] == "yield"     # 2.* loaded


def test_strata_endpoint_dead_yields(env):
    a, why = _gs(alive_fn=lambda: (False, "Strata /v1/models did not answer in 10 s (URLError)"))
    assert a == "yield" and "Strata" in why


def test_strata_alive_uses_10s(env):
    sent = []
    assert R.strata_alive(http_of(sent=sent)) == (True, "")
    assert sent[0][2] == 10
    assert R.strata_alive(http_of(OSError("x")))[0] is False


def test_strata_still_honours_quiet_and_stops(env):
    assert _gs(quiet_fn=lambda: (True, "owner"))[0] == "yield"
    assert _gs(lab_stop_fn=lambda: True) == ("yield", "qwen_lab STOP file")
    os.makedirs(str(env["home"]), exist_ok=True)
    _w(str(env["home"] / "STOP"), "x")
    assert _gs()[0] == "stop"


def test_default_guard_follows_current_backend(env, monkeypatch):
    got = []
    monkeypatch.setattr(R, "check_guards", lambda **k: got.append(k.get("backend")) or (None, ""))
    r = R.Runner(chat_factory=lambda: None, sleep=lambda s: None, backend="strata")
    r.wait_guards()
    r.cur = "ollama"
    r.wait_guards()
    assert got == ["strata", "ollama"]


def test_runner_log_and_transcript_record_backend(env):
    r, _ = make(env, [tc("finish", result_markdown="x", status="done", one_line="ok")], [], [], backend="ollama")
    r.cycle()
    log = _r(str(env["home"] / "runner.log"))
    assert "backend ollama model %s" % R.MODEL in log
    tdir = env["home"] / "transcripts"
    tr = json.loads(_r(str(tdir / os.listdir(str(tdir))[0])))
    assert tr["backend"] == "ollama" and tr["model"] == R.MODEL


def test_cli_backend_flag(monkeypatch):
    got = {}

    class FakeRunner:
        def __init__(self, backend):
            got["b"] = backend

        def run(self, once):
            return "idle"
    monkeypatch.setattr(R, "Runner", FakeRunner)
    R.main(["once"])
    assert got["b"] == "auto"
    R.main(["once", "--backend", "strata"])
    assert got["b"] == "strata"
