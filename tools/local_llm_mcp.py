"""local_llm_mcp.py -- the LOCAL model (Ollama / qwen3.8) as an MCP server, so a chat can hand
it long reading (logs, papers, big CSVs) instead of pulling the text into its own context.

Owner 2026-10-11: "set up your local Qwen so the chats can hand it long reading (logs, papers)
and save tokens". Everything real lives in tools/local_llm.py (summarize / status); this file
is only the wire. Same rule as there: the answer is an UNVERIFIED pointer - quote the file,
never the model.

TOOLS
  local_summarize {paths: string[], question: string, words?: int, tail?: int, grep?: string}
      read files/globs (text + PDF), redact key/token/password lines, map-reduce a short
      answer. Can take minutes on a cold model or a big read.
  local_status    {warm_test?: bool}
      is Ollama up, is the model installed / loaded / on the GPU, 1-line warm test.

PROTOCOL: MCP over stdio, hand-written JSON-RPC 2.0 (the `mcp` package is not installed and
not needed): one JSON message per line on stdin/stdout. Handles initialize (echoes the
client's protocolVersion, default 2025-06-18), notifications/initialized, ping, tools/list,
tools/call, notifications/cancelled. stdout carries protocol messages ONLY - anything else
(progress, stray prints) goes to stderr. A tool error comes back as isError content; nothing
raises across the wire. Tool calls run on a worker thread (one model call at a time) so a
ping is still answered while a long read runs.

REGISTER (MANAGER, after review - see docs/LOCAL_LLM.md):
  claude mcp add --scope user local-llm -- "<python3.13>" "<EDGE-LOG>\\tools\\local_llm_mcp.py"

Stdlib only.
"""
from __future__ import annotations

import json
import os
import sys
import threading
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import local_llm  # noqa: E402

SERVER_NAME = "local-llm"
SERVER_VERSION = "1.0.0"
DEFAULT_PROTOCOL = "2025-06-18"

INSTRUCTIONS = (
    "Local qwen3.8 model on the owner's PC (Ollama). Hand it LONG READING you would otherwise "
    "pull into context: logs, papers (PDF), long .md/.py, big CSV/JSON - for first-pass "
    "screening ('did the ship land and why not', 'what does this paper validate on'). "
    "Its answer is UNVERIFIED: quote the file, never the model; never use it for numbers, "
    "verdicts, or code that ships. Use tail/grep to narrow big files. Slow: a cold start is "
    "minutes and it may run on CPU - call local_status first if unsure.")

TOOLS = [
    {
        "name": "local_summarize",
        "title": "Local model: read files and answer one question",
        "description": (
            "Read text files / logs / .md / .py / .csv / .json / PDFs on this PC (globs OK, "
            "e.g. C:/EdgeLog/manager/ship_*.log), redact any key/token/password line, and have "
            "the LOCAL qwen3.8 model answer ONE question in a short reply (default <= 200 "
            "words). Saves context tokens on long reading. The answer is UNVERIFIED - use it "
            "to know where to look, then quote the file itself. Use `tail` for big logs and "
            "`grep` to send only matching lines (+-3 lines). Takes seconds warm, minutes cold "
            "or on a big read."),
        "inputSchema": {
            "type": "object",
            "properties": {
                "paths": {"type": "array", "items": {"type": "string"}, "minItems": 1,
                          "description": "absolute file paths or globs"},
                "question": {"type": "string", "description": "the one question to answer"},
                "words": {"type": "integer", "minimum": 20, "maximum": 1000,
                          "description": "answer length cap, default 200"},
                "tail": {"type": "integer", "minimum": 1,
                         "description": "read only the last N lines of each file"},
                "grep": {"type": "string",
                         "description": "regex (case-insensitive): send only matching lines "
                                        "+-3 lines of context"},
            },
            "required": ["paths", "question"],
            "additionalProperties": False,
        },
        "annotations": {"readOnlyHint": True, "openWorldHint": False},
    },
    {
        "name": "local_status",
        "title": "Local model: status",
        "description": (
            "Is Ollama up at 127.0.0.1:11434, is qwen3.8 installed / loaded / on the GPU, and "
            "a one-line warm test with tokens/sec (the warm test loads the model if cold - "
            "minutes; pass warm_test=false to skip it)."),
        "inputSchema": {
            "type": "object",
            "properties": {"warm_test": {"type": "boolean",
                                         "description": "run the 1-line warm test (default true)"}},
            "additionalProperties": False,
        },
        "annotations": {"readOnlyHint": True, "openWorldHint": False},
    },
]


def log(msg):
    print("[local-llm-mcp] %s" % msg, file=sys.stderr, flush=True)


def _text(text, is_error=False):
    return {"content": [{"type": "text", "text": str(text)}], "isError": bool(is_error)}


def _int_arg(args, key, lo=None, hi=None):
    v = args.get(key)
    if v is None:
        return None
    if isinstance(v, bool) or not isinstance(v, (int, float, str)):
        raise ValueError("%s must be an integer" % key)
    try:
        v = int(v)
    except (TypeError, ValueError):
        raise ValueError("%s must be an integer" % key)
    if lo is not None and v < lo:
        raise ValueError("%s must be >= %d" % (key, lo))
    if hi is not None and v > hi:
        raise ValueError("%s must be <= %d" % (key, hi))
    return v


def tool_local_summarize(args):
    paths = args.get("paths")
    if isinstance(paths, str):
        paths = [paths]
    if not isinstance(paths, list) or not paths or not all(isinstance(p, str) for p in paths):
        return _text("paths must be a non-empty list of file paths / globs", True)
    question = args.get("question")
    if not isinstance(question, str) or not question.strip():
        return _text("question must be a non-empty string", True)
    try:
        words = _int_arg(args, "words", 20, 1000) or local_llm.WORDS
        tail = _int_arg(args, "tail", 1)
    except ValueError as e:
        return _text(str(e), True)
    grep = args.get("grep")
    if grep is not None and not isinstance(grep, str):
        return _text("grep must be a string", True)
    try:
        res = local_llm.summarize(paths, question, words=words, tail=tail, grep=grep or None,
                                  progress=log)
    except (local_llm.OllamaDown, local_llm.OllamaError, ValueError) as e:
        return _text("local_summarize: %s" % e, True)
    return _text(local_llm.format_summary(res))


def tool_local_status(args):
    warm = args.get("warm_test", True)
    ok, txt = local_llm.status(warm_test=bool(warm))
    return _text(txt, not ok)


HANDLERS = {"local_summarize": tool_local_summarize, "local_status": tool_local_status}


class Server:
    """JSON-RPC 2.0 over newline-delimited stdio. `out` is a BINARY stream.

    Another server (tools/edgelog_mcp.py) reuses this framing by subclassing and overriding
    the class attributes below; the defaults are this server's own."""

    server_name = SERVER_NAME
    server_title = "Local qwen3.8 reader"
    server_version = SERVER_VERSION
    instructions = INSTRUCTIONS
    tools = TOOLS
    handlers = HANDLERS

    def __init__(self, out):
        self._out = out
        self._wlock = threading.Lock()
        self._model_lock = threading.Lock()     # one model call at a time
        self._workers = []
        self._cancelled = set()
        self._clock = threading.Lock()

    # -- wire ------------------------------------------------------------------------------
    def send(self, msg):
        data = json.dumps(msg, ensure_ascii=False, separators=(",", ":")).encode("utf-8") + b"\n"
        with self._wlock:
            self._out.write(data)
            self._out.flush()

    def _result(self, mid, result):
        self.send({"jsonrpc": "2.0", "id": mid, "result": result})

    def _error(self, mid, code, message):
        self.send({"jsonrpc": "2.0", "id": mid, "error": {"code": code, "message": message}})

    # -- dispatch --------------------------------------------------------------------------
    def handle_line(self, line):
        line = line.strip()
        if not line:
            return
        try:
            msg = json.loads(line)
        except ValueError:
            self._error(None, -32700, "parse error")
            return
        if isinstance(msg, list):                 # JSON-RPC batch (older protocol revisions)
            if not msg:
                self._error(None, -32600, "invalid request: empty batch")
            for m in msg:
                self.handle_message(m)
            return
        self.handle_message(msg)

    def handle_message(self, msg):
        if not isinstance(msg, dict) or msg.get("jsonrpc") != "2.0":
            self._error(msg.get("id") if isinstance(msg, dict) else None, -32600, "invalid request")
            return
        method = msg.get("method")
        mid = msg.get("id")
        is_note = "id" not in msg
        params = msg.get("params") or {}
        if not isinstance(method, str):
            if not is_note and ("result" in msg or "error" in msg):
                return                            # a reply to something we never sent - ignore
            if not is_note:
                self._error(mid, -32600, "invalid request: no method")
            return
        if is_note:
            if method == "notifications/cancelled" and isinstance(params, dict):
                with self._clock:
                    self._cancelled.add(json.dumps(params.get("requestId")))
            # notifications/initialized and anything else: nothing to send back
            return
        try:
            if method == "initialize":
                pv = params.get("protocolVersion") if isinstance(params, dict) else None
                self._result(mid, {
                    "protocolVersion": pv if isinstance(pv, str) and pv else DEFAULT_PROTOCOL,
                    "capabilities": {"tools": {"listChanged": False}},
                    "serverInfo": {"name": self.server_name, "title": self.server_title,
                                   "version": self.server_version},
                    "instructions": self.instructions,
                })
            elif method == "ping":
                self._result(mid, {})
            elif method == "tools/list":
                self._result(mid, {"tools": self.tools})
            elif method == "tools/call":
                self._start_call(mid, params if isinstance(params, dict) else {})
            else:
                self._error(mid, -32601, "method not found: %s" % method)
        except Exception as e:                    # never let one message kill the server
            log("internal error on %s: %s\n%s" % (method, e, traceback.format_exc()))
            self._error(mid, -32603, "internal error: %s" % e)

    def _start_call(self, mid, params):
        name = params.get("name")
        args = params.get("arguments") or {}
        handler = self.handlers.get(name)
        if handler is None:
            self._error(mid, -32602, "unknown tool: %s" % name)
            return
        if not isinstance(args, dict):
            self._result(mid, _text("arguments must be an object", True))
            return
        t = threading.Thread(target=self._run_call, args=(mid, name, handler, args),
                             name="tool-%s" % name, daemon=True)
        self._workers.append(t)
        t.start()

    def _run_call(self, mid, name, handler, args):
        log("tools/call %s %s" % (name, json.dumps(args)[:300]))
        try:
            with self._model_lock:
                result = handler(args)
        except Exception as e:
            log("tool %s crashed: %s\n%s" % (name, e, traceback.format_exc()))
            result = _text("%s failed: %s: %s" % (name, type(e).__name__, e), True)
        with self._clock:
            cancelled = json.dumps(mid) in self._cancelled
        if cancelled:
            log("tools/call %s finished after the client cancelled it - reply dropped" % name)
            return
        self._result(mid, result)

    def wait(self):
        for t in list(self._workers):
            t.join()


def serve(instream=None, outstream=None):
    """Run until stdin closes. instream: binary line source; outstream: binary sink."""
    instream = instream if instream is not None else sys.stdin.buffer
    outstream = outstream if outstream is not None else sys.stdout.buffer
    srv = Server(outstream)
    log("ready (model %s at %s, pid %d)" % (local_llm.MODEL, local_llm.HOST, os.getpid()))
    for raw in instream:
        try:
            line = raw.decode("utf-8", "replace") if isinstance(raw, bytes) else raw
            srv.handle_line(line)
        except Exception as e:
            log("dropped a message: %s" % e)
    srv.wait()                                  # let an in-flight call answer before exiting
    log("stdin closed - exiting")


def main():
    out = sys.stdout.buffer
    # From here on, anything that print()s (a library, a stray debug line) lands on stderr,
    # never in the protocol stream.
    sys.stdout = sys.stderr
    serve(sys.stdin.buffer, out)


if __name__ == "__main__":
    main()
