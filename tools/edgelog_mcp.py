"""edgelog_mcp.py -- EDGE-LOG chat inbox, open board and Qwen task folder as an MCP server, so the
local Qwen (Cline) can read its tasks, read the board, and post back to a chat's inbox.

Owner GO 10-28 (MANAGER #195). The wire is tools/local_llm_mcp.py's Server (hand-written JSON-RPC
2.0 over stdio, one message per line, stdout = protocol only); this file only adds the tools.

TOOLS
  inbox_read  {lane: string, all?: bool}   open items of one lane's inbox (all=true: done too)
  inbox_post  {to: string, text: string}   post to an EXISTING inbox; the sender is always QWEN
  board_read  {grep?: string, max_chars?: int}   <home>/manager/open_board/board.md
  task_list   {}                           <home>/manager/qwen_tasks/* (first heading, RESULT?)
  task_result {name: string}               one task file, by basename only (read-only)

PATHS: EDGELOG_HOME (default C:\\EdgeLog). The inbox folder is EDGELOG_CHAT_INBOX when set (the
variable tools/chat_inbox.py reads), else <home>/chat_inbox.

REGISTER (MANAGER, after review - see docs/LOCAL_LLM.md):
  claude mcp add --scope user edgelog -- "<python3.13>" "<EDGE-LOG>\\tools\\edgelog_mcp.py"

Stdlib only.
"""
from __future__ import annotations

import contextlib
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import chat_inbox  # noqa: E402
import local_llm_mcp  # noqa: E402

SERVER_NAME = "edgelog"
SERVER_VERSION = "1.0.0"
SENDER = "QWEN"                 # hard-coded: the caller cannot choose who a post is from
MAX_POST = 4000
BOARD_CAP = 20000
TASK_EXTS = (".md", ".txt")

INSTRUCTIONS = (
    "EDGE-LOG chat inboxes, the open board and the Qwen task folder. Read your task with "
    "task_list / task_result, read the board with board_read, read a lane's inbox with "
    "inbox_read, and post back with inbox_post (always sent from QWEN, existing inboxes only).")

_STR = {"type": "string"}
TOOLS = [
    {"name": "inbox_read", "title": "Read a chat inbox",
     "description": "Open items of one chat lane's inbox (all=true includes done items).",
     "inputSchema": {"type": "object",
                     "properties": {"lane": dict(_STR, description="inbox / chat name"),
                                    "all": {"type": "boolean"}},
                     "required": ["lane"], "additionalProperties": False},
     "annotations": {"readOnlyHint": True, "openWorldHint": False}},
    {"name": "inbox_post", "title": "Post to a chat inbox (from QWEN)",
     "description": "Post one item to an EXISTING chat inbox. The sender is always QWEN. "
                    "Text 1-%d chars." % MAX_POST,
     "inputSchema": {"type": "object",
                     "properties": {"to": _STR, "text": dict(_STR, maxLength=MAX_POST)},
                     "required": ["to", "text"], "additionalProperties": False},
     "annotations": {"readOnlyHint": False, "destructiveHint": False, "openWorldHint": False}},
    {"name": "board_read", "title": "Read the open board",
     "description": "Read the MANAGER open board (board.md). grep = case-insensitive substring "
                    "line filter; output capped at max_chars (default %d)." % BOARD_CAP,
     "inputSchema": {"type": "object",
                     "properties": {"grep": _STR, "max_chars": {"type": "integer", "minimum": 1}},
                     "additionalProperties": False},
     "annotations": {"readOnlyHint": True, "openWorldHint": False}},
    {"name": "task_list", "title": "List Qwen task files",
     "description": "Files in manager/qwen_tasks with their first heading and whether they "
                    "already contain a RESULT section.",
     "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
     "annotations": {"readOnlyHint": True, "openWorldHint": False}},
    {"name": "task_result", "title": "Read one Qwen task file",
     "description": "Read one task file from manager/qwen_tasks by basename (e.g. t01.md).",
     "inputSchema": {"type": "object", "properties": {"name": _STR},
                     "required": ["name"], "additionalProperties": False},
     "annotations": {"readOnlyHint": True, "openWorldHint": False}},
]

_text = local_llm_mcp._text


def home():
    return os.environ.get("EDGELOG_HOME") or r"C:\EdgeLog"


def inbox_dir():
    return os.environ.get("EDGELOG_CHAT_INBOX") or os.path.join(home(), "chat_inbox")


def board_path():
    return os.path.join(home(), "manager", "open_board", "board.md")


def tasks_dir():
    return os.path.join(home(), "manager", "qwen_tasks")


def _use_box():
    chat_inbox.BOX = inbox_dir()            # chat_inbox reads its module global at call time


def _read(p):
    with open(p, encoding="utf-8", errors="replace") as f:
        return f.read()


def tool_inbox_read(args):
    lane = args.get("lane")
    if not isinstance(lane, str) or not lane.strip():
        return _text("lane must be a non-empty string", True)
    _use_box()
    name = chat_inbox.norm(lane)
    if name not in chat_inbox.known():
        return _text("no inbox named %s. known: %s" % (name, ", ".join(chat_inbox.known()) or "(none)"), True)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        chat_inbox.show(lane, chat_inbox.load(lane), only_open=not bool(args.get("all")))
    return _text(buf.getvalue().rstrip("\n"))


def tool_inbox_post(args):
    extra = sorted(set(args) - {"to", "text"})
    if extra:
        return _text("REFUSED: unexpected argument(s) %s - the sender is always %s" % (", ".join(extra), SENDER), True)
    to, text = args.get("to"), args.get("text")
    if not isinstance(to, str) or not to.strip():
        return _text("to must be a non-empty string", True)
    if not isinstance(text, str) or not text.strip():
        return _text("text must be a non-empty string", True)
    if len(text) > MAX_POST:
        return _text("text is %d chars; the limit is %d" % (len(text), MAX_POST), True)
    _use_box()
    name = chat_inbox.norm(to)
    if name not in chat_inbox.known():
        return _text("REFUSED: no inbox named %s (posts go to existing inboxes only). known: %s"
                     % (name, ", ".join(chat_inbox.known()) or "(none)"), True)
    nid = chat_inbox.post(name, text, SENDER)
    return _text("posted #%d to %s from %s" % (nid, name, SENDER))


def tool_board_read(args):
    grep = args.get("grep")
    if grep is not None and not isinstance(grep, str):
        return _text("grep must be a string", True)
    try:
        cap = local_llm_mcp._int_arg(args, "max_chars", 1) or BOARD_CAP
    except ValueError as e:
        return _text(str(e), True)
    p = board_path()
    if not os.path.isfile(p):
        return _text("board not found: %s" % p, True)
    txt = _read(p)
    if grep:
        g = grep.lower()
        lines = [ln for ln in txt.splitlines() if g in ln.lower()]
        txt = "\n".join(lines) if lines else "(no line matches %r)" % grep
    if len(txt) > cap:
        txt = txt[:cap] + "\n...[truncated at %d of %d chars]" % (cap, len(txt))
    return _text(txt)


def _task_files():
    d = tasks_dir()
    if not os.path.isdir(d):
        return d, None
    return d, sorted(fn for fn in os.listdir(d)
                     if os.path.isfile(os.path.join(d, fn)) and fn.lower().endswith(TASK_EXTS)
                     and not fn.upper().startswith("README"))


def tool_task_list(args):
    d, files = _task_files()
    if files is None:
        return _text("task folder not found: %s" % d, True)
    if not files:
        return _text("no task files in %s" % d)
    rows = []
    for fn in files:
        lines = _read(os.path.join(d, fn)).splitlines()
        head = next((ln.strip() for ln in lines if ln.lstrip().startswith("#")),
                    next((ln.strip() for ln in lines if ln.strip()), ""))
        has = any("RESULT" in ln and (ln.lstrip().startswith("#") or ln.strip().rstrip(":") == "RESULT")
                  for ln in lines)
        rows.append("%s | %s | RESULT: %s" % (fn, head, "yes" if has else "no"))
    return _text("\n".join(rows))


def tool_task_result(args):
    name = args.get("name")
    if not isinstance(name, str) or not name.strip():
        return _text("name must be a non-empty string", True)
    if (name != os.path.basename(name) or "/" in name or "\\" in name or ".." in name
            or os.path.isabs(name) or ":" in name or not name.lower().endswith(TASK_EXTS)):
        return _text("REFUSED: name must be a plain task file name (%s) inside qwen_tasks"
                     % "/".join(TASK_EXTS), True)
    d, files = _task_files()
    if not files or name not in files:
        return _text("no task file named %s in %s" % (name, d), True)
    return _text(_read(os.path.join(d, name)))


HANDLERS = {"inbox_read": tool_inbox_read, "inbox_post": tool_inbox_post,
            "board_read": tool_board_read, "task_list": tool_task_list,
            "task_result": tool_task_result}


class Server(local_llm_mcp.Server):
    server_name = SERVER_NAME
    server_title = "EDGE-LOG inbox, board and Qwen tasks"
    server_version = SERVER_VERSION
    instructions = INSTRUCTIONS
    tools = TOOLS
    handlers = HANDLERS


def serve(instream=None, outstream=None):
    instream = instream if instream is not None else sys.stdin.buffer
    outstream = outstream if outstream is not None else sys.stdout.buffer
    srv = Server(outstream)
    print("[edgelog-mcp] ready (home %s, pid %d)" % (home(), os.getpid()), file=sys.stderr, flush=True)
    for raw in instream:
        try:
            srv.handle_line(raw.decode("utf-8", "replace") if isinstance(raw, bytes) else raw)
        except Exception as e:
            print("[edgelog-mcp] dropped a message: %s" % e, file=sys.stderr, flush=True)
    srv.wait()


def main():
    out = sys.stdout.buffer
    sys.stdout = sys.stderr
    serve(sys.stdin.buffer, out)


if __name__ == "__main__":
    main()
