"""tools/qwen_runner.py ONE DOOR, ONE WORKER (MANAGER #222): loaded-model pick, never two models, router chat,
Cline-busy yield, dated STATUS.md started/result lines."""
import datetime
import os
import sys
import time
import urllib.error

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))
import qwen_runner as R  # noqa: E402
from test_qwen_runner import env, make, tc, _w, _r  # noqa: E402,F401

TODAY = datetime.date.today().isoformat()
LOADED = {"data": [{"id": R.STRATA_MODEL, "status": {"value": "loaded"}, "meta": {"n_ctx": 262144}}]}
LOADING = {"data": [{"id": R.STRATA_MODEL, "status": {"value": "loading"}}]}


def seq_http(*answers):
    """/models answers in order (an Exception instance is raised); the last one repeats."""
    a = list(answers)

    def http(path, payload=None, timeout=None):
        x = a.pop(0) if len(a) > 1 else a[0]
        if isinstance(x, Exception):
            raise x
        return x
    return http


def fake_clock():
    t = [0.0]
    return t, (lambda s: t.__setitem__(0, t[0] + s)), (lambda: t[0])


# ---------------------------------------------------------------- backend = whatever is loaded
def test_strata_loading_then_loaded_is_waited_for():
    t, sleep, clock = fake_clock()
    http = seq_http(LOADING, LOADING, LOADING, LOADED)
    assert R.select_backend("auto", http, sleep=sleep, clock=clock) == "strata"
    assert 0 < t[0] < R.STRATA_LOAD_WAIT_S


def test_strata_503_loading_counts_as_answering():
    err = urllib.error.HTTPError("http://x/v1/models", 503, "Loading model", {}, None)
    t, sleep, clock = fake_clock()
    assert R.select_backend("auto", seq_http(err, err, LOADED), sleep=sleep, clock=clock) == "strata"
    t, sleep, clock = fake_clock()
    assert R.select_backend("auto", seq_http(err), sleep=sleep, clock=clock) is None       # never loads 5.* beside it
    assert t[0] >= R.STRATA_LOAD_WAIT_S                                                    # waited the full 15 min


def test_strata_silent_means_ollama():
    assert R.select_backend("auto", seq_http(OSError("refused"))) == "ollama"


def test_cycle_yields_when_strata_never_loads(env):
    r, fc = make(env, [], [], [], backend="auto", selector=lambda c: None)
    assert r.cycle() == "idle" and fc.calls == []
    assert R.first_line(str(env["tasks"] / "Q2-b.md")).startswith("STATUS: ⭕")
    assert "not loading a second model" in _r(str(env["home"] / "runner.log"))


# ---------------------------------------------------------------- never two models
@pytest.mark.parametrize("name", ["2.qwen3.8:27b-48k", "3.qwen3.6:35b-128k", "4.qwen3.6:35b-64k", "llama3:8b"])
def test_any_other_ollama_model_yields(name):
    y, why = R.other_model_loaded(lambda: {"models": [{"name": name}]})
    assert y and name in why


def test_own_model_or_none_is_clear():
    assert R.other_model_loaded(lambda: {"models": []}) == (False, "")
    assert R.other_model_loaded(lambda: {"models": [{"name": R.MODEL}]}) == (False, "")


# ---------------------------------------------------------------- Cline busy
def test_cline_busy_by_recent_session_file(tmp_path):
    d = tmp_path / "sessions"
    (d / "s1").mkdir(parents=True)
    f = d / "s1" / "s1.messages.json"
    f.write_text("{}")
    now = time.time()
    os.utime(str(f), (now - 5, now - 5))
    b, why = R.cline_busy([str(d)], now=now)
    assert b and "s1.messages.json" in why
    os.utime(str(f), (now - 120, now - 120))
    assert R.cline_busy([str(d)], now=now) == (False, "")
    assert R.cline_busy([str(tmp_path / "missing")], now=now) == (False, "")


def test_cline_dirs_env_override(monkeypatch):
    monkeypatch.setenv("QWEN_CLINE_DIRS", "a" + os.pathsep + "b")
    assert R.cline_dirs() == ["a", "b"]
    monkeypatch.delenv("QWEN_CLINE_DIRS")
    assert any(p.endswith(os.path.join(".cline", "data", "sessions")) for p in R.cline_dirs())


def _g(**kw):
    base = dict(yield_fn=lambda: (False, ""), quiet_fn=lambda: (False, None), lab_stop_fn=lambda: False,
                ps_fn=lambda: {"models": []}, alive_fn=lambda: (True, ""), cline_fn=lambda: (False, ""),
                slots_fn=lambda: None)
    base.update(kw)
    return R.check_guards(**base)


@pytest.mark.parametrize("backend", ["ollama", "strata"])
def test_guard_yields_while_cline_works_then_resumes(env, backend):
    a, why = _g(backend=backend, cline_fn=lambda: (True, "Cline is mid-task (x.json written 3 s ago)"))
    assert a == "yield" and "Cline" in why
    assert _g(backend=backend) == (None, "")


def test_strata_busy_slot_yields(env):
    a, why = _g(backend="strata", slots_fn=lambda: [{"id": 0, "is_processing": False}, {"id": 1, "is_processing": True}])
    assert a == "yield" and "slot 1" in why
    assert _g(backend="strata", slots_fn=lambda: [{"id": 0, "is_processing": False}]) == (None, "")
    assert _g(backend="ollama", slots_fn=lambda: [{"id": 0, "is_processing": True}]) == (None, "")  # slots = Strata only


def test_strata_slots_unreadable_is_none():
    def boom(url):
        raise OSError("down")
    assert R.strata_slots(boom) is None
    assert R.strata_slots(lambda url: {"error": "slots disabled"}) is None
    assert R.strata_slots(lambda url: [{"id": 0}]) == [{"id": 0}]


# ---------------------------------------------------------------- router
def test_router_chat_sends_model_5_openai_shape():
    sent = []

    def http(path, payload=None, timeout=None):
        sent.append((path, payload))
        return {"choices": [{"message": {"content": "", "tool_calls": [
            {"id": "c1", "function": {"name": "finish", "arguments": "{}"}}]}, "finish_reason": "tool_calls"}],
            "usage": {"completion_tokens": 3, "prompt_tokens": 9}}
    c = R.RouterChat("ollama", http=http)
    msg, stats = c.chat([{"role": "user", "content": "hi"}], [{"name": "finish", "parameters": {}}])
    assert sent[0][0] == "/chat/completions" and sent[0][1]["model"] == "5.qwen3.6:35b-32k"
    assert msg["tool_calls"][0]["function"]["name"] == "finish" and stats["prompt_tokens"] == 9
    s = R.RouterChat("strata", http=http, info=LOADED["data"][0])
    assert s.num_ctx == 262144 and s.ctx_limit > R.CTX_LIMIT


def test_default_chat_router_first_then_direct(monkeypatch):
    monkeypatch.setattr(R, "RunnerChat", lambda: "direct-ollama")
    monkeypatch.setattr(R, "StrataChat", lambda: "direct-strata")
    assert isinstance(R.default_chat("ollama", router_ok=lambda: True), R.RouterChat)
    assert R.default_chat("ollama", router_ok=lambda: False) == "direct-ollama"
    assert R.default_chat("strata", router_ok=lambda: False) == "direct-strata"


def test_router_alive():
    assert R.router_alive(lambda *a: {"data": []}) is True

    def boom(*a):
        raise OSError("x")
    assert R.router_alive(boom) is False


# ---------------------------------------------------------------- STATUS.md = the owner's view
def test_status_started_then_result_dated(env):
    seen = []

    class Peek:
        model = R.MODEL
        num_ctx = R.NUM_CTX

        def chat(self, messages, tools):
            seen.append(_r(str(env["tasks"] / "STATUS.md")))
            return tc("finish", result_markdown="x", status="done", one_line="found 3 things")[0], {}
    r = R.Runner(chat_factory=Peek, guards=lambda: (None, ""), sleep=lambda s: None,
                 poster=lambda *a: 1, pusher=lambda *a: (True, ""))
    r.cycle()
    mid = [l for l in seen[0].split("\r\n") if l.startswith("| Q2 ")][0]
    assert mid.startswith("| Q2 | two | 🟡 | %s started " % TODAY) and mid.endswith(" |")
    st = _r(str(env["tasks"] / "STATUS.md"))
    assert "| Q2 | two | 🟢 | %s found 3 things |\r\n" % TODAY in st
    assert "\r\n" in st and st.count("\n") == st.count("\r\n")               # CRLF kept


def test_status_blocked_row_and_no_trailing_pipe_row(env):
    _w(str(env["tasks"] / "STATUS.md"), "| # | Task | Status | Note |\r\n| Q2 | two | ⭕ | old note\r\n")
    assert R.set_status_row(2, "🔴", "model call failed: x|y")
    assert _r(str(env["tasks"] / "STATUS.md")).endswith("| Q2 | two | 🔴 | %s model call failed: x/y |\r\n" % TODAY)


def test_status_duplicate_rows_all_updated_and_missing_row_appended(env):
    _w(str(env["tasks"] / "STATUS.md"), "| Q9 | nine | ✅ | a |\r\n| Q9 | nine | ✅ | a |\r\n")
    R.set_status_row(9, "🟡", "started 10:00")
    assert _r(str(env["tasks"] / "STATUS.md")).count("🟡 | %s started 10:00 |" % TODAY) == 2
    R.set_status_row(14, "🟡", "started 10:01", title="new")
    assert _r(str(env["tasks"] / "STATUS.md")).endswith("| Q14 | new | 🟡 | %s started 10:01 |\r\n" % TODAY)


def test_status_md_bom_kept(env):
    p = str(env["tasks"] / "STATUS.md")
    with open(p, "wb") as f:
        f.write(b"\xef\xbb\xbf| Q2 | two | \xe2\xad\x95 | y |\n")
    R.set_status_row(2, "🟢", "ok")
    raw = open(p, "rb").read()
    assert raw.startswith(b"\xef\xbb\xbf") and b"\r\n" not in raw and "🟢".encode() in raw
