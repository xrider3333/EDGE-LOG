"""tools/local_llm.py --summarize + tools/local_llm_mcp.py (owner 2026-10-11: hand the local
qwen long reading to save tokens). No test touches the real Ollama: urlopen is faked in-process,
and the subprocess test points the server at a fake Ollama on 127.0.0.1:<random port>."""
import http.server
import io
import json
import os
import subprocess
import sys
import threading
import urllib.error

import pytest

TOOLS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools")
sys.path.insert(0, TOOLS)
import local_llm  # noqa: E402
import local_llm_mcp  # noqa: E402

# distinctive fake secrets: none of these strings may ever appear in a request body
SECRETS = {
    "ALPACA_API_KEY_ID=PKFAKEKEY0001": "PKFAKEKEY0001",
    "export APCA_API_SECRET_KEY=sEcReTvAlUe0002": "sEcReTvAlUe0002",
    "curl -H 'Authorization: Bearer brr0003tokentoken'": "brr0003tokentoken",
    "NTFY_TOPIC=edgelog-topic-0004": "edgelog-topic-0004",
    "pushed to https://ntfy.sh/edgelog-topic-0005 ok": "edgelog-topic-0005",
    'config: {"access_token": "tok0006abcdef"}': "tok0006abcdef",
    "login password=hunter0007": "hunter0007",
    "GITHUB TOKEN=ghp_0008aaaaaaaaaaaaaaaaaaaaaaaa": "0008aaaaaaaa",
    "webull app_key: wbkey0009": "wbkey0009",
    "db url postgres://admin:pw0010@localhost/x": "pw0010",
}
BENIGN = [
    "PREFLIGHT: PASS (VERSION=73.1206, bodyLen=6262856)",
    "warm-up: 'ready' in 1.5s (26.1 tok/s), 400 tokens",
    "sha256 9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08",
    "monkey=3 keyboard layout ok",
    "pushed main -> origin/main 1234abcd",
]


class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()


class FakeOllama:
    """Stands in for urllib.request.urlopen. Records every request body (raw bytes)."""

    def __init__(self, answer=None, down=False):
        self.bodies, self.urls = [], []
        self.answer = answer or (lambda prompt: "FINAL ANSWER")
        self.down = down

    def __call__(self, req, timeout=None):
        url = req.full_url
        self.urls.append(url)
        if self.down:
            raise urllib.error.URLError(ConnectionRefusedError(10061, "refused"))
        if req.data:
            self.bodies.append(req.data)
        if url.endswith("/api/version"):
            out = {"version": "test"}
        elif url.endswith("/api/tags"):
            out = {"models": [{"name": local_llm.MODEL, "size": 17.4e9,
                               "details": {"parameter_size": "36.0B", "quantization_level": "Q4_K_M"}}]}
        elif url.endswith("/api/ps"):
            out = {"models": [{"name": local_llm.MODEL, "size": 100, "size_vram": 0,
                               "context_length": 32768, "expires_at": "2026-10-11T13:14:43-07:00"}]}
        elif url.endswith("/api/generate"):
            body = json.loads(req.data)
            out = {"response": self.answer(body["prompt"]), "eval_count": 20,
                   "eval_duration": 2e9, "prompt_eval_count": 50, "prompt_eval_duration": 1e9,
                   "load_duration": 0}
        else:
            raise AssertionError("unexpected url %s" % url)
        return _Resp(json.dumps(out).encode("utf-8"))

    def generate_bodies(self):
        return [json.loads(b) for b in self.bodies]


@pytest.fixture(autouse=True)
def _private_log(tmp_path, monkeypatch):
    # the audit log must never be the owner's real C:\EdgeLog\local_llm.log in a test
    monkeypatch.setattr(local_llm, "LOG_PATH", str(tmp_path / "local_llm.log"))


@pytest.fixture
def fake(monkeypatch):
    f = FakeOllama()
    monkeypatch.setattr(local_llm.urllib.request, "urlopen", f)
    return f


# ── chunking ──────────────────────────────────────────────────────────────────────────────
def _body_lines(chunks):
    return [ln for ch in chunks for ln in ch.split("\n") if not ln.startswith("===== FILE:")]


def test_chunks_respect_the_size_and_keep_every_line_in_order():
    a = ["a-line %04d %s" % (i, "x" * 40) for i in range(300)]
    b = ["b-line %04d" % i for i in range(50)]
    chunks = local_llm.make_chunks([("A.log", a), ("B.log", b)], 2000)
    assert len(chunks) > 5
    assert all(len(c) <= 2000 for c in chunks)
    assert _body_lines(chunks) == a + b
    assert chunks[0].startswith("===== FILE: A.log =====")
    assert chunks[1].startswith("===== FILE: A.log (continued) =====")
    assert any("===== FILE: B.log =====" in c for c in chunks)


def test_one_small_file_is_one_chunk_and_a_long_line_is_hard_split():
    assert len(local_llm.make_chunks([("s.txt", ["hello", "world"])], 84000)) == 1
    long = "z" * 9000
    chunks = local_llm.make_chunks([("l.txt", [long])], 4000)
    assert all(len(c) <= 4000 for c in chunks)
    assert "".join(_body_lines(chunks)) == long


def test_summarize_clamps_the_chunk_to_fit_num_ctx(tmp_path, fake):
    p = tmp_path / "x.log"
    p.write_text("one line\n", encoding="utf-8")
    res = local_llm.summarize([str(p)], "q", chunk_tokens=10 ** 6)
    assert res["chunk_tokens"] < local_llm.NUM_CTX
    # every generate call carries the same num_ctx (a different one reloads the 17 GB weights)
    assert {b["options"]["num_ctx"] for b in fake.generate_bodies()} == {local_llm.NUM_CTX}
    assert all(b["think"] is False for b in fake.generate_bodies())


# ── redaction ─────────────────────────────────────────────────────────────────────────────
def test_secret_lines_are_masked_and_ordinary_lines_are_not():
    lines = list(SECRETS) + BENIGN
    mask = local_llm.secret_mask(lines)
    assert mask[:len(SECRETS)] == [True] * len(SECRETS), [l for l, m in zip(lines, mask) if not m]
    assert mask[len(SECRETS):] == [False] * len(BENIGN), [l for l, m in zip(lines, mask) if m]


def test_a_pem_private_key_block_is_masked_whole():
    lines = ["before", "-----BEGIN RSA PRIVATE KEY-----", "MIIEowIBAAKCAQEAx", "abcDEF==",
             "-----END RSA PRIVATE KEY-----", "after"]
    assert local_llm.secret_mask(lines) == [False, True, True, True, True, False]


def test_keys_never_reach_the_request_body(tmp_path, fake):
    p = tmp_path / "ship.log"
    p.write_text("\n".join(BENIGN[:2] + list(SECRETS) + BENIGN[2:]) + "\n", encoding="utf-8")
    res = local_llm.summarize([str(p)], "did it land", words=50)
    sent = b"".join(fake.bodies)
    assert fake.generate_bodies(), "the model was never called"
    for value in SECRETS.values():
        assert value.encode() not in sent, value
    assert b"PREFLIGHT: PASS" in sent and b"[REDACTED]" in sent
    assert res["redacted"] == len(SECRETS)
    out = local_llm.format_summary(res)
    assert out.splitlines()[0] == ("LOCAL MODEL SUMMARY (qwen3.8, unverified - quote nothing "
                                   "from it as fact)")
    assert "redacted: %d lines" % len(SECRETS) in out
    assert "reading 50 tok/s, writing 10.0 tok/s" in out
    # the audit log holds the question and the answer, never the file text
    log = open(local_llm.LOG_PATH, encoding="utf-8").read()
    assert "did it land" in log and not any(v in log for v in SECRETS.values())


def test_grep_first_sends_only_hits_with_context_and_still_redacts(tmp_path, fake):
    lines = ["noise %d" % i for i in range(40)]
    lines[20] = "ERROR push rejected"
    lines[22] = "Authorization: Bearer grepsecret0011"
    p = tmp_path / "g.log"
    p.write_text("\n".join(lines), encoding="utf-8")
    res = local_llm.summarize([str(p)], "why", grep="error")
    sent = b"".join(fake.bodies)
    assert b"L21: ERROR push rejected" in sent
    assert b"noise 17" in sent and b"noise 23" in sent           # +-3 lines of context
    assert b"noise 16" not in sent and b"noise 24" not in sent
    assert b"grepsecret0011" not in sent
    assert res["files"][0]["lines_sent"] == 7 and res["redacted"] == 1


def test_grep_with_no_hit_sends_nothing(tmp_path, fake):
    p = tmp_path / "g.log"
    p.write_text("a\nb\n", encoding="utf-8")
    res = local_llm.summarize([str(p)], "why", grep="nomatch")
    assert res["calls"] == 0 and not fake.bodies and "no line matched" in res["answer"]


# ── reading ───────────────────────────────────────────────────────────────────────────────
def test_tail_reads_only_the_last_lines(tmp_path, fake):
    p = tmp_path / "big.log"
    p.write_text("\n".join("row %03d" % i for i in range(500)), encoding="utf-8")
    res = local_llm.summarize([str(p)], "q", tail=5)
    sent = b"".join(fake.bodies)
    assert b"row 499" in sent and b"row 495" in sent and b"row 494" not in sent
    assert res["files"][0]["lines_sent"] == 5 and res["files"][0]["lines_total"] == 500


def test_globs_missing_files_binary_and_utf16(tmp_path):
    (tmp_path / "a.log").write_text("alpha", encoding="utf-8")
    (tmp_path / "b.log").write_bytes("beta ünï\r\n".encode("utf-16-le"))     # PS 5.1 '>' output
    (tmp_path / "c.bin").write_bytes(b"\x00\x01\x02binary\x00")
    files, problems = local_llm.expand_paths([str(tmp_path / "*.log"), str(tmp_path / "nope.log"),
                                              str(tmp_path / "*.zzz")])
    assert [os.path.basename(f) for f in files] == ["a.log", "b.log"]
    assert len(problems) == 2
    assert local_llm.read_text(str(tmp_path / "b.log"))[0].strip() == "beta ünï"
    assert local_llm.read_text(str(tmp_path / "c.bin")) == (None, "binary file - skipped")


def _tiny_pdf(text):
    stream = b"BT /F1 12 Tf 72 712 Td (" + text.encode("latin-1") + b") Tj ET"
    objs = [b"<< /Type /Catalog /Pages 2 0 R >>",
            b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
            b"/Resources << /Font << /F1 5 0 R >> >> >>",
            b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    out, offsets = b"%PDF-1.4\n", []
    for i, o in enumerate(objs, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % i + o + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)
    out += b"".join(b"%010d 00000 n \n" % off for off in offsets)
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, xref)
    return out


def test_pdf_text_is_read_with_page_markers(tmp_path):
    pytest.importorskip("pypdf")
    p = tmp_path / "paper.pdf"
    p.write_bytes(_tiny_pdf("Lockbox held out 2024"))
    text, note = local_llm.read_text(str(p))
    assert "[page 1]" in text and "Lockbox held out 2024" in text and note == "pdf, 1 pages"


def test_pdf_is_skipped_with_a_reason_when_pypdf_is_missing(tmp_path, monkeypatch, fake):
    monkeypatch.setitem(sys.modules, "pypdf", None)          # import pypdf -> ImportError
    (tmp_path / "paper.pdf").write_bytes(b"%PDF-1.4 whatever")
    (tmp_path / "notes.md").write_text("# notes\nkeep this", encoding="utf-8")
    res = local_llm.summarize([str(tmp_path / "paper.pdf"), str(tmp_path / "notes.md")], "q")
    out = local_llm.format_summary(res)
    assert "SKIPPED" in out and "pypdf not installed" in out and "notes.md" in out


# ── map-reduce, word cap, errors ──────────────────────────────────────────────────────────
def test_map_reduce_calls_once_per_chunk_then_reduces(tmp_path, monkeypatch):
    f = FakeOllama(answer=lambda pr: "note: saw a FAIL" if "This is part" in pr else "it failed")
    monkeypatch.setattr(local_llm.urllib.request, "urlopen", f)
    p = tmp_path / "long.log"
    p.write_text("\n".join("line %05d %s" % (i, "y" * 60) for i in range(2000)), encoding="utf-8")
    res = local_llm.summarize([str(p)], "did it fail", chunk_tokens=10000)
    prompts = [b["prompt"] for b in f.generate_bodies()]
    assert res["chunks"] >= 3 and res["calls"] == res["chunks"] + 1
    assert all("QUESTION: did it fail" in pr for pr in prompts)
    assert "[part 1 of %d] note: saw a FAIL" % res["chunks"] in prompts[-1]
    assert res["answer"] == "it failed"


def test_answer_is_capped_at_words(tmp_path, monkeypatch):
    monkeypatch.setattr(local_llm.urllib.request, "urlopen",
                        FakeOllama(answer=lambda pr: " ".join(["w"] * 500)))
    p = tmp_path / "x.log"
    p.write_text("x", encoding="utf-8")
    res = local_llm.summarize([str(p)], "q", words=30)
    assert res["answer"].endswith("[cut at 30 words]") and len(res["answer"].split()) == 34


def test_too_many_chunks_is_refused_before_any_model_call(tmp_path, fake):
    p = tmp_path / "huge.log"
    p.write_text("\n".join("r %d %s" % (i, "q" * 80) for i in range(5000)), encoding="utf-8")
    with pytest.raises(ValueError, match="max_chunks"):
        local_llm.summarize([str(p)], "q", chunk_tokens=1000, max_chunks=3)
    assert not fake.bodies


def test_ollama_down_is_one_clear_message(tmp_path, monkeypatch):
    monkeypatch.setattr(local_llm.urllib.request, "urlopen", FakeOllama(down=True))
    p = tmp_path / "x.log"
    p.write_text("x", encoding="utf-8")
    with pytest.raises(local_llm.OllamaDown) as e:
        local_llm.summarize([str(p)], "q")
    assert str(e.value) == "Ollama not reachable at 127.0.0.1:11434 - start Ollama"
    ok, txt = local_llm.status()
    assert not ok and txt == "Ollama not reachable at 127.0.0.1:11434 - start Ollama"
    # the old entry point still never raises
    text, secs, tps = local_llm.ask("hi")
    assert "Ollama not reachable" in text and tps == 0.0


def test_status_reports_cpu_only_and_a_warm_test(fake):
    ok, txt = local_llm.status()
    assert ok
    assert "Ollama: UP at 127.0.0.1:11434 (version test)" in txt
    assert "installed" in txt and "CPU ONLY" in txt
    assert "warm test: 'FINAL ANSWER'" in txt and "10.0 tok/s" in txt


def test_existing_ask_still_returns_text_secs_tps(fake):
    text, secs, tps = local_llm.ask("one word")
    assert text == "FINAL ANSWER" and tps == 10.0
    assert fake.generate_bodies()[0]["options"]["num_ctx"] == local_llm.NUM_CTX


# ── MCP server ────────────────────────────────────────────────────────────────────────────
def _rpc(messages):
    """Feed newline-delimited JSON into an in-process server; return replies by id."""
    raw = b"".join(json.dumps(m).encode() + b"\n" if not isinstance(m, bytes) else m
                   for m in messages)
    out = io.BytesIO()
    local_llm_mcp.serve(io.BytesIO(raw), out)
    lines = out.getvalue().decode("utf-8").splitlines()
    replies = [json.loads(ln) for ln in lines]
    return {r.get("id"): r for r in replies}, replies


def test_mcp_handshake_list_and_call(tmp_path, fake):
    p = tmp_path / "ship.log"
    p.write_text("PUSH: landed 73.1206\nALPACA_API_KEY_ID=PKFAKEKEY0001\n", encoding="utf-8")
    by_id, replies = _rpc([
        {"jsonrpc": "2.0", "id": 1, "method": "initialize",
         "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                    "clientInfo": {"name": "test", "version": "0"}}},
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        {"jsonrpc": "2.0", "id": 3, "method": "ping"},
        {"jsonrpc": "2.0", "id": 4, "method": "tools/call",
         "params": {"name": "local_summarize",
                    "arguments": {"paths": [str(tmp_path / "*.log")], "question": "did it land",
                                  "words": 40, "tail": 10}}},
    ])
    assert len(replies) == 4                                  # the notification gets no reply
    init = by_id[1]["result"]
    assert init["protocolVersion"] == "2025-06-18"
    assert init["serverInfo"]["name"] == "local-llm" and "tools" in init["capabilities"]
    assert sorted(t["name"] for t in by_id[2]["result"]["tools"]) == ["local_status", "local_summarize"]
    for t in by_id[2]["result"]["tools"]:
        assert t["inputSchema"]["type"] == "object"
    assert by_id[3]["result"] == {}
    call = by_id[4]["result"]
    assert call["isError"] is False
    text = call["content"][0]["text"]
    assert call["content"][0]["type"] == "text"
    assert text.startswith(local_llm.SUMMARY_HEADER) and "FINAL ANSWER" in text
    assert "redacted: 1 line " in text
    assert b"PKFAKEKEY0001" not in b"".join(fake.bodies)


def test_mcp_echoes_the_clients_protocol_version_or_defaults():
    by_id, _ = _rpc([
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-03-26"}},
        {"jsonrpc": "2.0", "id": 2, "method": "initialize", "params": {}},
    ])
    assert by_id[1]["result"]["protocolVersion"] == "2025-03-26"
    assert by_id[2]["result"]["protocolVersion"] == "2025-06-18"


def test_mcp_errors_come_back_on_the_wire_never_raise(tmp_path, monkeypatch):
    monkeypatch.setattr(local_llm.urllib.request, "urlopen", FakeOllama(down=True))
    (tmp_path / "x.log").write_text("x", encoding="utf-8")
    by_id, replies = _rpc([
        b"{not json\n",
        {"jsonrpc": "2.0", "id": 1, "method": "no/such/method"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
         "params": {"name": "local_summarize", "arguments": {"paths": [], "question": "q"}}},
        {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
         "params": {"name": "local_summarize",
                    "arguments": {"paths": [str(tmp_path / "x.log")], "question": "q"}}},
        {"jsonrpc": "2.0", "id": 4, "method": "tools/call",
         "params": {"name": "nope", "arguments": {}}},
        {"jsonrpc": "2.0", "id": 5, "method": "tools/call",
         "params": {"name": "local_summarize",
                    "arguments": {"paths": [str(tmp_path / "x.log")], "question": "q", "words": "lots"}}},
        {"jsonrpc": "2.0", "id": 6, "method": "tools/call",
         "params": {"name": "local_status", "arguments": {}}},
    ])
    assert by_id[None]["error"]["code"] == -32700
    assert by_id[1]["error"]["code"] == -32601
    assert by_id[2]["result"]["isError"] is True
    assert by_id[3]["result"]["isError"] is True
    assert "Ollama not reachable at 127.0.0.1:11434 - start Ollama" in by_id[3]["result"]["content"][0]["text"]
    assert by_id[4]["error"]["code"] == -32602
    assert by_id[5]["result"]["isError"] is True
    assert by_id[6]["result"]["isError"] is True


class _FakeOllamaHTTP(http.server.BaseHTTPRequestHandler):
    bodies = []

    def _send(self, obj):
        data = json.dumps(obj).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        self._send({"version": "fake"})

    def do_POST(self):
        body = self.rfile.read(int(self.headers["Content-Length"]))
        type(self).bodies.append(body)
        self._send({"response": "landed fine", "eval_count": 5, "eval_duration": 1e9,
                    "prompt_eval_count": 40, "load_duration": 0})

    def log_message(self, *a):
        pass


def test_mcp_server_process_speaks_clean_stdio(tmp_path):
    """The real process: every stdout line is a JSON-RPC message, and no key reaches 'Ollama'."""
    _FakeOllamaHTTP.bodies = []
    httpd = http.server.HTTPServer(("127.0.0.1", 0), _FakeOllamaHTTP)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        log = tmp_path / "ship.log"
        log.write_text("PUSH ok\npassword=hunter0007\nNTFY_TOPIC=edgelog-topic-0004\n", encoding="utf-8")
        env = dict(os.environ, AUGUR_LOCAL_LLM_HOST="http://127.0.0.1:%d" % httpd.server_port,
                   AUGUR_LOCAL_LLM_LOG=str(tmp_path / "llm.log"), PYTHONIOENCODING="utf-8")
        msgs = [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
             "params": {"name": "local_summarize",
                        "arguments": {"paths": [str(log)], "question": "did it land"}}},
        ]
        p = subprocess.run([sys.executable, os.path.join(TOOLS, "local_llm_mcp.py")],
                           input="".join(json.dumps(m) + "\n" for m in msgs).encode(),
                           capture_output=True, env=env, timeout=120)
    finally:
        httpd.shutdown()
    lines = p.stdout.decode("utf-8").splitlines()
    replies = {r["id"]: r for r in (json.loads(ln) for ln in lines)}   # any stray print breaks this
    assert sorted(replies) == [1, 2, 3], p.stderr.decode("utf-8", "replace")
    text = replies[3]["result"]["content"][0]["text"]
    assert replies[3]["result"]["isError"] is False and "landed fine" in text
    sent = b"".join(_FakeOllamaHTTP.bodies)
    assert sent and b"hunter0007" not in sent and b"edgelog-topic-0004" not in sent
    assert b"ready" in p.stderr                                   # logging went to stderr
