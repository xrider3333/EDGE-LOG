"""QWEN TASK RUNNER (AUTOMATIONS.md B3, MANAGER #204) - works the Qwen task board unattended.

  python tools/qwen_runner.py run      loop: lowest-numbered open (⭕) Q task, else sleep 5 min
  python tools/qwen_runner.py once     one cycle (one task at most), then exit

Board: C:\\EdgeLog\\manager\\qwen_tasks (Q<n>-*.md + STATUS.md; override QWEN_TASKS_DIR).
State/log/transcripts: C:\\EdgeLog\\qwen_runner (override QWEN_RUNNER_HOME). STOP file there = exit cleanly.

Guards before every task AND every model turn (wait 60 s, re-check):
  ram_guard.should_yield() (free RAM < 6 GB), quiet mode, the qwen_lab STOP file,
  Ollama /api/ps shows a model named 2.*, 3.* or 4.* (the owner's Cline) - never start beside it.
Model 5.qwen3.6:35b-32k, num_ctx 32768 (never more), keep_alive 5m in a task, 0 after.
Tools are READ-ONLY (read_file, list_dir, grep) + finish. Reads only under C:\\EdgeLog, the main checkout and the
memory folder; refuses NinjaTrader/Webull/TradingView/.ssh, key/token/secret/password/credential/.env/.pem names,
binaries. Writes ONLY: the task file (line 1 + ## RESULT), its STATUS.md icon, the MANAGER inbox, one phone push,
and its own home. No git; the only subprocess is run_python's sandboxed child (ram_guard may call nvidia-smi).
run_python + write_scratch (MANAGER #206): .py files directly in qwen_tasks\\scratch only, AST-gated, read-only,
60 s. No network is guaranteed ONLY by the AST gate.
The result is the local model's work: UNVERIFIED until Claude checks it.

BACKENDS (MANAGER #211): --backend auto|strata|ollama (default auto). auto = Strata (OpenAI-compatible, 127.0.0.1:8080/v1)
when /v1/models lists qwen3.8-flash-next-gyro-gyro-s as loaded, else Ollama; re-checked before each task. With Strata
the RAM floor and the 1.*/2.* owner-model check are skipped (Strata holds RAM by design); the guard is "Strata answers
/v1/models within 10 s" plus quiet mode and both STOP files. No keep_alive/unload is ever sent to Strata. Its
compaction budget is sized from meta.n_ctx (capped at 200k tokens, ~4 chars/token, reply room kept).

ONE DOOR, ONE WORKER (MANAGER #222). Chats file tasks with tools/qwen_task.py; this runner is the only thing that talks
to the model, and it uses WHATEVER IS LOADED:
  - Strata :8080 answers (any HTTP reply, a 503 "loading" included) -> wait up to 15 min for it to list its model as
    loaded, then use Strata. Still loading after 15 min -> yield (never load 5.* beside a loading Strata).
  - Strata silent -> Ollama 5.qwen3.6:35b-32k, but ONLY when /api/ps shows no other model loaded (never two models).
  - Calls go through the router 127.0.0.1:11435/v1 as model 5.qwen3.6:35b-32k when the router answers (it sends 5.*
    to Strata while Strata is up); router down -> the direct paths (Strata /v1, Ollama /api/chat).
CLINE BUSY = yield (checked before every task and every turn): any file under ~/.cline/data/sessions/*/ or VS Code's
globalStorage/saoudrizwan.claude-dev/tasks/*/ modified in the last 60 s (Cline rewrites <id>.json + <id>.messages.json
on every message/tool step), OR, on Strata, llama-server /slots shows a slot with is_processing true. Ollama /api/ps
has no active-request field (checked 10-30: name/model/size/digest/details/expires_at/size_vram/context_length only),
so on Ollama the session-file test is the busy signal. Override the Cline folders with QWEN_CLINE_DIRS (os.pathsep).
STATUS.md (the owner's view): start = 🟡 + "YYYY-MM-DD started HH:MM"; finish = 🟢/🔴 + "YYYY-MM-DD <one line>".
"""
import argparse
import ast
import datetime
import fnmatch
import glob
import json
import os
import re
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
if HERE not in sys.path:
    sys.path.insert(0, HERE)

MODEL = "5.qwen3.6:35b-32k"
NUM_CTX = 32768
KEEP_ALIVE_TASK = "5m"
MAX_TURNS = 40
MAX_TASK_S = 45 * 60
# Strata reads/writes slower per turn: Q3 + Q4 ran out of the 45-min wall on 10-28 (MANAGER #213).
STRATA_MAX_TURNS = 80
STRATA_MAX_TASK_S = 120 * 60
MAX_EMPTY = 3
READ_CAP = 12000
GREP_MAX_FILES = 2000
GREP_MAX_HITS = 200
GREP_MAX_FILE_BYTES = 5 * 1024 * 1024
IDLE_SLEEP_S = 300
GUARD_SLEEP_S = 60
ONE_LINE_MAX = 200
CTX_LIMIT = 75000

STRATA_URL = "http://127.0.0.1:8080/v1"
STRATA_MODEL = "qwen3.8-flash-next-gyro-gyro-s"
STRATA_DISPLAY = "1.STRATA qwen3.8-flash:125b-256k"   # owner renumber 10-30 (MANAGER #220); wire id stays STRATA_MODEL
OWNER_MODEL_PREFIXES = ("2.", "3.", "4.")              # the owner's Cline models; the runner's own 5.* is not one
STRATA_ROOT = "http://127.0.0.1:8080"
ROUTER_URL = "http://127.0.0.1:11435/v1"
ROUTER_ALIVE_S = 5
STRATA_LOAD_WAIT_S = 15 * 60
STRATA_LOAD_POLL_S = 15
CLINE_IDLE_S = 60
STRATA_ALIVE_S = 10
STRATA_CTX_CAP_TOK = 200000
STRATA_REPLY_TOK = 16384
STRATA_TIMEOUT_S = 1800
CHARS_PER_TOK = 4

OPEN, WORKING, DONE, BLOCKED = "⭕", "🟡", "🟢", "🔴"
STATUS_WORKING = "STATUS: 🟡 Qwen working"
STATUS_DONE = "STATUS: 🟢 done - waiting for Claude check"

MAIN_CHECKOUT = r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"
MEMORY_DIR = r"C:\Users\xride\.claude\projects\C--Users-xride-OneDrive-Desktop\memory"
DENY_DIR_RX = re.compile(r"ninjatrader|webull|tradingview|^\.ssh$", re.I)
DENY_NAME_RX = re.compile(r"key|token|secret|password|credential|\.env|\.pem", re.I)


def tasks_dir():
    return os.environ.get("QWEN_TASKS_DIR") or r"C:\EdgeLog\manager\qwen_tasks"


def home():
    return os.environ.get("QWEN_RUNNER_HOME") or r"C:\EdgeLog\qwen_runner"


def read_roots():
    env = os.environ.get("QWEN_RUNNER_ROOTS")
    if env:
        return [r for r in env.split(os.pathsep) if r]
    return [r"C:\EdgeLog", MAIN_CHECKOUT, MEMORY_DIR]


def now_s():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class Refused(Exception):
    pass


# ------------------------------------------------------------------------------------------------ text-file edits
def _read_text(path):
    """(text, bom) with line endings untouched."""
    with open(path, "rb") as f:
        raw = f.read()
    bom = raw.startswith(b"\xef\xbb\xbf")
    return raw[3:].decode("utf-8") if bom else raw.decode("utf-8"), bom


def _write_text(path, text, bom):
    data = (b"\xef\xbb\xbf" if bom else b"") + text.encode("utf-8")
    tmp = path + ".qrtmp"
    with open(tmp, "wb") as f:
        f.write(data)
    os.replace(tmp, path)


def _eol(text):
    return "\r\n" if "\r\n" in text else "\n"


def first_line(path):
    text, _ = _read_text(path)
    return text.splitlines()[0] if text else ""


def set_first_line(path, line):
    text, bom = _read_text(path)
    m = re.match(r"[^\r\n]*", text)
    _write_text(path, line + text[m.end():], bom)


def append_result(path, md):
    text, bom = _read_text(path)
    eol = _eol(text)
    body = md.replace("\r\n", "\n").replace("\n", eol)
    sep = "" if text.endswith(eol) or not text else eol
    _write_text(path, text + sep + eol + body.rstrip() + eol, bom)


_ROW_RX = r"^(\|\s*Q%d\s*\|[^|\r\n]*\|\s*)([^|\r\n]*?)(\s*\|)"


def status_row_icon(n, tdir=None):
    p = os.path.join(tdir or tasks_dir(), "STATUS.md")
    if not os.path.exists(p):
        return None
    text, _ = _read_text(p)
    m = re.search(_ROW_RX % n, text, re.M)
    return m.group(2).strip() if m else None


def set_status_icon(n, icon, tdir=None):
    """Edit only the Status cell of row Q<n>; encoding and line endings kept. False when the row is missing."""
    p = os.path.join(tdir or tasks_dir(), "STATUS.md")
    if not os.path.exists(p):
        return False
    text, bom = _read_text(p)
    new, k = re.subn(_ROW_RX % n, lambda m: m.group(1) + icon + m.group(3), text, count=1, flags=re.M)
    if k:
        _write_text(p, new, bom)
    return bool(k)


_FULLROW_RX = r"^(\|\s*Q%d\s*\|[^|\r\n]*\|)[^|\r\n]*\|[^\r\n]*"


def set_status_row(n, icon, note, tdir=None, title=None):
    """Status + Note cells of every Q<n> row (duplicates too); the note is dated YYYY-MM-DD. Missing row -> appended."""
    p = os.path.join(tdir or tasks_dir(), "STATUS.md")
    note = re.sub(r"\s+", " ", str(note).replace("|", "/")).strip()
    note = "%s %s" % (datetime.date.today().isoformat(), note)
    if not os.path.exists(p):
        return False
    text, bom = _read_text(p)
    new, k = re.subn(_FULLROW_RX % n, lambda m: "%s %s | %s |" % (m.group(1), icon, note), text, flags=re.M)
    if not k:
        eol = _eol(text)
        sep = "" if not text or text.endswith(("\n", "\r")) else eol
        new = text + sep + "| Q%d | %s | %s | %s |" % (n, (title or "Q%d" % n).replace("|", "/"), icon, note) + eol
    _write_text(p, new, bom)
    return True


# ------------------------------------------------------------------------------------------------ pick
def list_tasks(tdir=None):
    out = []
    for p in glob.glob(os.path.join(tdir or tasks_dir(), "Q*-*.md")):
        m = re.match(r"Q(\d+)-", os.path.basename(p))
        if m:
            out.append((int(m.group(1)), p))
    return sorted(out)


def is_open(n, path, tdir=None):
    line = first_line(path)
    if line.startswith("STATUS:"):
        return OPEN in line
    return status_row_icon(n, tdir) == OPEN


def pick_task(tdir=None):
    for n, p in list_tasks(tdir):
        if is_open(n, p, tdir):
            return n, p
    return None


# ------------------------------------------------------------------------------------------------ path safety
def _nc(p):
    return os.path.normcase(os.path.realpath(os.path.abspath(p)))


def safe_path(path, roots=None):
    if not path or not isinstance(path, str):
        raise Refused("path is empty")
    full = _nc(path)
    ok_root = None
    for r in roots or read_roots():
        rr = _nc(r)
        if full == rr or full.startswith(rr.rstrip("\\/") + os.sep):
            ok_root = rr
            break
    if not ok_root:
        raise Refused("outside the allowed read roots")
    rel = full[len(ok_root):].strip("\\/")
    parts = [x for x in re.split(r"[\\/]", rel) if x]
    for part in parts:
        if DENY_DIR_RX.search(part):
            raise Refused("refused: NinjaTrader/Webull/TradingView/.ssh paths are off limits")
    if parts and DENY_NAME_RX.search(parts[-1]):
        raise Refused("refused: credential-like file name")
    return full


def is_binary(path):
    try:
        with open(path, "rb") as f:
            chunk = f.read(8192)
    except OSError:
        return True
    if b"\x00" in chunk:
        return True
    try:
        chunk.decode("utf-8")
    except UnicodeDecodeError as e:
        return e.start < len(chunk) - 4                   # a cut multibyte char at the end is fine
    return False


def tool_read_file(path, offset=None, limit=None, roots=None):
    p = safe_path(path, roots)
    if not os.path.isfile(p):
        raise Refused("not a file")
    if is_binary(p):
        raise Refused("refused: binary file")
    with open(p, encoding="utf-8", errors="replace") as f:
        lines = f.read().splitlines()
    start = max(int(offset or 1), 1)
    end = len(lines) if not limit else min(len(lines), start - 1 + max(int(limit), 1))
    body = "\n".join("%d\t%s" % (i + 1, lines[i]) for i in range(start - 1, end))
    note = "[%s: lines %d-%d of %d]" % (path, start, end, len(lines))
    if len(body) > READ_CAP:
        body = body[:READ_CAP] + "\n...[cut at %d chars; read again with a later offset]" % READ_CAP
    return note + "\n" + body


def tool_list_dir(path, roots=None):
    p = safe_path(path, roots)
    if not os.path.isdir(p):
        raise Refused("not a folder")
    rows = []
    for name in sorted(os.listdir(p)):
        full = os.path.join(p, name)
        try:
            safe_path(full, roots)
        except Refused:
            continue
        if os.path.isdir(full):
            rows.append(name + "/")
        else:
            try:
                rows.append("%s  (%d bytes)" % (name, os.path.getsize(full)))
            except OSError:
                rows.append(name)
    out = "\n".join(rows) or "(empty)"
    return out[:READ_CAP]


def tool_grep(pattern, path_glob, roots=None):
    try:
        rx = re.compile(pattern)
    except re.error as e:
        raise Refused("bad regex: %s" % e)
    if not path_glob:
        raise Refused("path_glob is empty")
    base = path_glob if os.path.isabs(path_glob) else None
    if not base:
        raise Refused("path_glob must be an absolute path under an allowed root")
    lead = re.split(r"[*?\[]", path_glob, maxsplit=1)[0]
    safe_path(lead if os.path.isdir(lead) else os.path.dirname(lead), roots)
    hits, files = [], 0
    for fp in glob.iglob(path_glob, recursive=True):
        if files >= GREP_MAX_FILES or len(hits) >= GREP_MAX_HITS:
            break
        if not os.path.isfile(fp):
            continue
        try:
            safe_path(fp, roots)
        except Refused:
            continue
        try:
            if os.path.getsize(fp) > GREP_MAX_FILE_BYTES or is_binary(fp):
                continue
        except OSError:
            continue
        files += 1
        with open(fp, encoding="utf-8", errors="replace") as f:
            for i, line in enumerate(f, 1):
                if rx.search(line):
                    hits.append("%s:%d: %s" % (fp, i, line.rstrip()[:300]))
                    if len(hits) >= GREP_MAX_HITS:
                        break
    out = "\n".join(hits) or "(no matches in %d files)" % files
    if len(hits) >= GREP_MAX_HITS:
        out += "\n...[stopped at %d matches]" % GREP_MAX_HITS
    return out[:READ_CAP]


# ------------------------------------------------------------------------------------------------ scratch python (MANAGER #206)
# run_python / write_scratch: Qwen may write and run small READ-ONLY data scripts, only .py files directly inside the
# scratch folder. Layer 1 = a dedicated AST gate (qwen_lab.safety_gate is plugin-shaped - it bans print, json,
# pathlib and top-level code - so it cannot be reused as is). Layer 2 = a child bootstrap that patches builtins.open
# and adds an audit hook (the qwen_lab sandbox approach): write modes, paths outside the read roots, the deny-list and
# subprocess/socket/os.remove-style events raise PermissionError. The child runs `python -I -B`, cwd = scratch, a
# minimal environment, 60 s timeout, 256 MB output cap (12000 chars back to the model).
# NO NETWORK is guaranteed ONLY by the AST gate (the audit hook's socket/urllib/http prefixes are a backstop, not a
# firewall): there is no OS-level network sandbox.
PY_TIMEOUT_S = 60
PY_OUT_CAP_BYTES = 256 * 1024 * 1024
PY_RESULT_CHARS = 12000
SCRATCH_MAX_CHARS = 20000
SCRATCH_NAME_RX = re.compile(r"^[A-Za-z0-9_-]+\.py$")
PY_ALLOWED_IMPORTS = {"pandas", "numpy", "csv", "json", "math", "statistics", "datetime", "re", "pathlib",
                      "collections", "itertools", "functools", "decimal", "fractions", "string", "textwrap",
                      "operator", "typing", "dataclasses", "bisect", "heapq", "calendar", "zoneinfo"}
PY_FORBIDDEN_NAMES = {
    "exec", "eval", "compile", "__import__", "globals", "locals", "vars", "getattr", "setattr", "delattr", "input",
    "breakpoint", "help", "memoryview", "__builtins__", "__loader__", "__spec__", "os", "sys", "subprocess", "socket",
    "shutil", "ctypes", "importlib", "builtins", "io", "requests", "urllib", "http", "pickle", "marshal", "runpy",
    "threading", "multiprocessing", "asyncio", "signal", "tempfile", "inspect", "gc", "types", "codecs", "mmap",
    "winreg", "msvcrt", "_winapi", "webbrowser", "ftplib", "smtplib", "ssl", "sqlite3", "shelve", "dbm", "exit",
    "quit", "classmethod", "staticmethod", "super", "object"}
PY_FORBIDDEN_ATTRS = {
    "system", "popen", "remove", "unlink", "rename", "rmdir", "removedirs", "mkdir", "makedirs", "chmod", "chdir",
    "touch", "write_text", "write_bytes", "symlink_to", "hardlink_to", "link_to", "open", "tofile", "savetxt",
    "save", "savez", "savez_compressed", "dump", "urlopen", "connect", "environ", "getenv", "putenv", "spawn",
    "Popen", "check_output", "load", "read_pickle", "eval", "query", "exec", "import_module", "write",
    "writelines", "writer", "DictWriter", "ExcelWriter", "HDFStore", "memmap", "f_globals", "f_locals",
    "f_builtins", "f_back", "gi_frame", "cr_frame", "tb_frame", "co_code"}
PY_TO_OK = {"to_numpy", "to_list", "to_dict", "to_frame", "to_period", "to_timestamp", "to_pydatetime",
            "to_datetime", "to_numeric", "to_timedelta", "to_series", "to_string", "to_markdown", "to_records",
            "to_offset", "to_flat_index", "to_datetime64"}


def scratch_dir():
    return os.environ.get("QWEN_SCRATCH_DIR") or os.path.join(tasks_dir(), "scratch")


def scratch_path(name):
    """The one path rule for both tools: a [A-Za-z0-9_-]+.py name (bare or full path) directly inside scratch."""
    if not name or not isinstance(name, str):
        raise Refused("name is empty")
    if not SCRATCH_NAME_RX.match(os.path.basename(name)):
        raise Refused("only [A-Za-z0-9_-]+.py files directly inside the scratch folder")
    sd = _nc(scratch_dir())
    full = _nc(name if os.path.isabs(name) else os.path.join(sd, name))
    if os.path.dirname(full) != sd:
        raise Refused("outside the scratch folder %s" % scratch_dir())
    return full


def _open_mode_problem(call):
    if len(call.args) > 2:
        return "open() with more than path and mode"
    mode = call.args[1] if len(call.args) == 2 else None
    for kw in call.keywords:
        if kw.arg is None:
            return "open(**kwargs)"
        if kw.arg == "mode":
            mode = kw.value
        elif kw.arg not in ("encoding", "errors", "newline"):
            return "open(%s=...)" % kw.arg
    if mode is None:
        return None
    if not (isinstance(mode, ast.Constant) and isinstance(mode.value, str)):
        return "open() mode must be a literal string"
    if any(c in mode.value for c in "wax+"):
        return "open() in write mode %r" % mode.value
    return None


def py_safety_gate(code):
    """AST gate for scratch scripts: read-only data work. Returns a list of problems ([] = OK)."""
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return ["syntax error: %s (line %s)" % (e.msg, e.lineno)]
    probs, open_calls = [], set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "open":
            open_calls.add(id(node.func))
            p = _open_mode_problem(node)
            if p:
                probs.append("line %d: %s" % (node.lineno, p))
    for node in ast.walk(tree):
        ln = getattr(node, "lineno", 0)
        if isinstance(node, ast.Import):
            for a in node.names:
                if a.name.split(".")[0] not in PY_ALLOWED_IMPORTS:
                    probs.append("line %d: import %s is not allowed" % (ln, a.name))
        elif isinstance(node, ast.ImportFrom):
            if node.level or not node.module or node.module.split(".")[0] not in PY_ALLOWED_IMPORTS:
                probs.append("line %d: from %s import is not allowed" % (ln, node.module))
            for a in node.names:
                if a.name == "*" or a.name.startswith("_") or a.name in PY_FORBIDDEN_NAMES \
                        or a.name in PY_FORBIDDEN_ATTRS:
                    probs.append("line %d: from %s import %s is not allowed" % (ln, node.module, a.name))
        elif isinstance(node, ast.Name):
            if node.id in PY_FORBIDDEN_NAMES or node.id.startswith("__"):
                probs.append("line %d: name %s is not allowed" % (ln, node.id))
            elif node.id == "open" and id(node) not in open_calls:
                probs.append("line %d: open may only be called directly" % ln)
        elif isinstance(node, ast.Attribute):
            a = node.attr
            if a.startswith("_") or a in PY_FORBIDDEN_ATTRS or (a.startswith("to_") and a not in PY_TO_OK) \
                    or a.startswith("save"):
                probs.append("line %d: .%s is not allowed" % (ln, a))
        elif isinstance(node, (ast.Global, ast.Nonlocal, ast.AsyncFunctionDef, ast.Await)):
            probs.append("line %d: %s is not allowed" % (ln, type(node).__name__))
        elif isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value.startswith("__") \
                and node.value.endswith("__"):
            probs.append("line %d: dunder string %r is not allowed" % (ln, node.value))
    out = []
    for p in probs:
        if p not in out:
            out.append(p)
    return out


# The child bootstrap (runs under python -I): argv = [script, json config]. Patches builtins.open and installs an
# audit hook BEFORE the script runs; reads of the interpreter's own library folders are allowed so imports work.
_PY_CHILD = r'''
import builtins, json, os, re, sys
cfg = json.loads(sys.argv[2])
script = sys.argv[1]
for _p in cfg["site"]:
    if _p not in sys.path:
        sys.path.append(_p)
nc = lambda p: os.path.normcase(os.path.realpath(os.path.abspath(p)))
roots = [nc(r) for r in cfg["roots"]]
libs = [nc(p) for p in [sys.prefix, sys.base_prefix, sys.exec_prefix] + [p for p in sys.path if p]]
ddir, dname = re.compile(cfg["deny_dir"], re.I), re.compile(cfg["deny_name"], re.I)
BLOCK = ("subprocess.", "os.system", "os.exec", "os.spawn", "os.posix_spawn", "os.startfile", "os.kill", "os.remove",
         "os.rename", "os.rmdir", "os.mkdir", "os.chmod", "os.link", "os.symlink", "os.truncate",
         "os.chdir", "shutil.", "socket.", "ctypes.", "winreg.", "_winapi.", "msvcrt.", "urllib.", "http.",
         "ftplib.", "smtplib.", "webbrowser.", "mmap.", "sqlite3.", "builtins.input", "sys.addaudithook")
def under(p, r):
    return p == r or p.startswith(r.rstrip("\\/") + os.sep)
def writing(mode, flags):
    if isinstance(mode, str):
        return any(c in mode for c in "wax+")
    try:
        f = int(flags or 0)
    except (TypeError, ValueError):
        return True
    return bool(f & (os.O_WRONLY | os.O_RDWR | os.O_APPEND | os.O_CREAT | os.O_TRUNC))
def check_read(p):
    full = nc(p)
    root = next((r for r in roots if under(full, r)), None)
    if root is None:
        if any(under(full, l) for l in libs):
            return
        raise PermissionError("scratch sandbox: reading %s is outside the allowed read roots" % p)
    parts = [x for x in re.split(r"[\\/]", full[len(root):]) if x]
    if any(ddir.search(x) for x in parts) or (parts and dname.search(parts[-1])):
        raise PermissionError("scratch sandbox: reading %s is on the deny-list" % p)
state = {"armed": False, "in": False}
def hook(event, args):
    if not state["armed"] or state["in"]:
        return
    state["in"] = True
    try:
        if event == "open":
            path, mode, flags = (list(args) + [None, None, None])[:3]
            if writing(mode, flags):
                raise PermissionError("scratch sandbox: writing is blocked")
            if path is not None and not isinstance(path, int):
                check_read(os.fsdecode(path) if isinstance(path, (bytes, bytearray)) else str(path))
            return
        for pre in BLOCK:
            if event.startswith(pre):
                raise PermissionError("scratch sandbox: %s is blocked" % event)
    finally:
        state["in"] = False
real_open = builtins.open
def guarded_open(file, mode="r", *a, **k):
    if writing(mode, None) or k.get("opener") is not None:
        raise PermissionError("scratch sandbox: open() in write mode %r is blocked" % (mode,))
    if not isinstance(file, int):
        check_read(os.fsdecode(file) if isinstance(file, (bytes, bytearray)) else str(file))
    return real_open(file, mode, *a, **k)
with real_open(script, encoding="utf-8") as fh:
    src = fh.read()
code = compile(src, script, "exec")
for _m in ("numpy", "pandas"):          # load the allowed C libraries BEFORE arming (their import uses ctypes)
    try:
        __import__(_m)
    except ImportError:
        pass
builtins.open = guarded_open
sys.addaudithook(hook)
state["armed"] = True
exec(code, {"__name__": "__main__", "__file__": script})
'''


def _py_env():
    keep = ("SYSTEMROOT", "SystemRoot", "WINDIR", "TEMP", "TMP", "NUMBER_OF_PROCESSORS", "PROCESSOR_ARCHITECTURE")
    env = {k: os.environ[k] for k in keep if k in os.environ}
    env.update(OMP_NUM_THREADS="1", MKL_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1")
    return env


def tool_write_scratch(name, code):
    p = scratch_path(name)
    if not isinstance(code, str) or not code.strip():
        raise Refused("code is empty")
    if len(code) > SCRATCH_MAX_CHARS:
        raise Refused("code is %d chars (max %d)" % (len(code), SCRATCH_MAX_CHARS))
    probs = py_safety_gate(code)
    if probs:
        raise Refused("safety gate: " + "; ".join(probs[:8]))
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8", newline="\n") as f:
        f.write(code)
    return "wrote %s (%d chars); run it with run_python" % (p, len(code))


def tool_run_python(path, roots=None, timeout=None):
    """Run one scratch .py in a child process: the AST gate first (it is the ONLY no-network guarantee - there is no
    OS-level network sandbox), then `python -I -B` with the builtins.open + audit-hook wrapper (write modes, paths
    outside the read roots + scratch, and the deny-list refused at runtime), cwd = scratch, minimal env, 60 s timeout,
    256 MB output cap, 12000 chars back to the model."""
    import subprocess
    import tempfile
    p = scratch_path(path)
    if not os.path.isfile(p):
        raise Refused("no such scratch file (write it first with write_scratch)")
    with open(p, encoding="utf-8", errors="replace") as f:
        code = f.read()
    if len(code) > SCRATCH_MAX_CHARS:
        raise Refused("script is %d chars (max %d)" % (len(code), SCRATCH_MAX_CHARS))
    probs = py_safety_gate(code)
    if probs:
        raise Refused("safety gate: " + "; ".join(probs[:8]))
    cfg = {"roots": list(roots or read_roots()) + [scratch_dir()], "deny_dir": DENY_DIR_RX.pattern,
           "deny_name": DENY_NAME_RX.pattern,
           "site": [x for x in sys.path if x and "site-packages" in x.lower()]}
    limit = timeout or PY_TIMEOUT_S
    flags = 0x08000000 if os.name == "nt" else 0                     # CREATE_NO_WINDOW
    t0 = time.time()
    why = None
    with tempfile.TemporaryFile() as out:
        proc = subprocess.Popen([sys.executable, "-I", "-B", "-X", "utf8", "-c", _PY_CHILD, p, json.dumps(cfg)],
                                cwd=os.path.dirname(p), env=_py_env(), stdin=subprocess.DEVNULL, stdout=out,
                                stderr=subprocess.STDOUT, creationflags=flags)
        while proc.poll() is None:
            if time.time() - t0 > limit:
                why = "TIMEOUT: killed after %d s" % limit
            elif os.fstat(out.fileno()).st_size > PY_OUT_CAP_BYTES:
                why = "OUTPUT CAP: killed past %d MB of output" % (PY_OUT_CAP_BYTES // (1024 * 1024))
            if why:
                proc.kill()
                proc.wait()
                break
            time.sleep(0.05)
        out.seek(0)
        text = out.read(PY_RESULT_CHARS * 4).decode("utf-8", errors="replace")
    head = "[exit %s, %.1f s%s]" % (proc.returncode, time.time() - t0, "; " + why if why else "")
    if len(text) > PY_RESULT_CHARS:
        text = text[:PY_RESULT_CHARS] + "\n...[output cut at %d chars]" % PY_RESULT_CHARS
    return head + "\n" + text


TOOLS = [
    {"name": "read_file", "description": "Read a text file (numbered lines, at most 12000 chars per call). Read-only.",
     "parameters": {"type": "object", "properties": {
         "path": {"type": "string", "description": "absolute path"},
         "offset": {"type": "integer", "description": "first line (1-based)"},
         "limit": {"type": "integer", "description": "number of lines"}}, "required": ["path"]}},
    {"name": "list_dir", "description": "List a folder.",
     "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}},
    {"name": "grep", "description": "Regex search over files matching an absolute glob (** allowed). Capped.",
     "parameters": {"type": "object", "properties": {
         "pattern": {"type": "string"}, "path_glob": {"type": "string"}}, "required": ["pattern", "path_glob"]}},
    {"name": "write_scratch", "description": "Create/overwrite a [A-Za-z0-9_-]+.py file (max 20000 chars) in the "
     "scratch folder. Read-only data work only: pandas, numpy, csv, json, math, statistics, datetime, re, pathlib, "
     "open(...) in read mode. No writes, network, subprocess, eval/exec, os, getattr.",
     "parameters": {"type": "object", "properties": {"name": {"type": "string"}, "code": {"type": "string"}},
                    "required": ["name", "code"]}},
    {"name": "run_python", "description": "Run a scratch .py (60 s limit, output cut at 12000 chars). print() results.",
     "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}},
    {"name": "finish", "description": "End the task: your RESULT markdown, status done or blocked, and one line.",
     "parameters": {"type": "object", "properties": {
         "result_markdown": {"type": "string"},
         "status": {"type": "string", "enum": ["done", "blocked"]},
         "one_line": {"type": "string", "description": "<= 200 chars"}},
         "required": ["result_markdown", "status", "one_line"]}},
]


def run_tool(name, args, roots=None):
    args = args if isinstance(args, dict) else {}
    try:
        if name == "read_file":
            return tool_read_file(args.get("path"), args.get("offset"), args.get("limit"), roots)
        if name == "list_dir":
            return tool_list_dir(args.get("path"), roots)
        if name == "grep":
            return tool_grep(args.get("pattern") or "", args.get("path_glob") or "", roots)
        if name == "write_scratch":
            return tool_write_scratch(args.get("name"), args.get("code"))
        if name == "run_python":
            return tool_run_python(args.get("path"), roots)
        return "ERROR: unknown tool %r (tools: read_file, list_dir, grep, write_scratch, run_python, finish)" % name
    except Refused as e:
        return "REFUSED: %s" % e
    except Exception as e:                                           # noqa: BLE001
        return "ERROR: %s: %s" % (type(e).__name__, str(e)[:200])


# ------------------------------------------------------------------------------------------------ guards
def ollama_ps():
    import local_llm as LL
    return LL._http_json("/api/ps", timeout=10)


def owner_model_loaded(ps_fn=None):
    """(True, why) when a 2.* / 3.* / 4.* model is loaded (the owner's Cline) or Ollama cannot be asked."""
    try:
        d = (ps_fn or ollama_ps)() or {}
    except Exception as e:                                           # noqa: BLE001
        return True, "Ollama /api/ps failed (%s)" % type(e).__name__
    for m in d.get("models") or []:
        name = str(m.get("name") or m.get("model") or "")
        if name.startswith(OWNER_MODEL_PREFIXES):
            return True, "owner model %s is loaded" % name
    return False, ""


def other_model_loaded(ps_fn=None):
    """(True, why) when Ollama has ANY model loaded other than the runner's 5.* (never two models), or /api/ps fails."""
    try:
        d = (ps_fn or ollama_ps)() or {}
    except Exception as e:                                           # noqa: BLE001
        return True, "Ollama /api/ps failed (%s)" % type(e).__name__
    for m in d.get("models") or []:
        name = str(m.get("name") or m.get("model") or "")
        if not name.startswith("5."):
            return True, "%s model %s is loaded - not loading a second model" % (
                "owner" if name.startswith(OWNER_MODEL_PREFIXES) else "other", name)
    return False, ""


def cline_dirs():
    env = os.environ.get("QWEN_CLINE_DIRS")
    if env is not None:
        return [d for d in env.split(os.pathsep) if d]
    u = os.path.expanduser("~")
    appdata = os.environ.get("APPDATA") or os.path.join(u, "AppData", "Roaming")
    return [os.path.join(u, ".cline", "data", "sessions"),
            os.path.join(appdata, "Code", "User", "globalStorage", "saoudrizwan.claude-dev", "tasks")]


def cline_busy(dirs=None, now=None, window_s=CLINE_IDLE_S):
    """(True, why) when a Cline session/task file was written in the last `window_s` seconds (Cline mid-task)."""
    now = time.time() if now is None else now
    for d in (cline_dirs() if dirs is None else dirs):
        for p in glob.glob(os.path.join(d, "*", "*")):
            try:
                age = now - os.path.getmtime(p)
            except OSError:
                continue
            if age < window_s:
                return True, "Cline is mid-task (%s written %d s ago)" % (os.path.basename(p), max(0, int(age)))
    return False, ""


def strata_slots(get=None):
    """llama-server /slots -> list, or None when it cannot be read (endpoint off / Strata down)."""
    if get is None:
        import urllib.request

        def get(url):
            with urllib.request.urlopen(url, timeout=STRATA_ALIVE_S) as r:
                return json.loads(r.read().decode("utf-8"))
    try:
        d = get(STRATA_ROOT + "/slots")
    except Exception:                                                # noqa: BLE001
        return None
    return d if isinstance(d, list) else None


def strata_slot_busy(slots_fn=None):
    slots = (slots_fn or strata_slots)()
    if slots is None:
        return False, ""
    busy = [s.get("id") for s in slots if isinstance(s, dict) and s.get("is_processing")]
    return (True, "Strata slot %s is processing (someone else's request)" % busy[0]) if busy else (False, "")


def engine_busy(backend, cline_fn=None, slots_fn=None):
    """Cline session files always; Strata /slots too when on Strata."""
    b, why = (cline_fn or cline_busy)()
    if b:
        return b, why
    if backend == "strata":
        return strata_slot_busy(slots_fn)
    return False, ""


def runner_stop_path():
    return os.path.join(home(), "STOP")


def strata_http(path, payload=None, timeout=STRATA_ALIVE_S):
    """GET (payload None) or POST JSON to the Strata /v1 endpoint; decoded JSON back."""
    import urllib.request
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(STRATA_URL + path, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def strata_model_info(http=None):
    """The /v1/models entry for STRATA_MODEL when it is listed as loaded, else None (any error = None)."""
    try:
        d = (http or strata_http)("/models", None, STRATA_ALIVE_S) or {}
    except Exception:                                                # noqa: BLE001
        return None
    for m in d.get("data") or []:
        if m.get("id") != STRATA_MODEL:
            continue
        st = m.get("status")
        val = st.get("value") if isinstance(st, dict) else st
        if str(val or "").lower() == "loaded":
            return m
    return None


def strata_answers(http=None):
    """True when :8080 gives ANY HTTP reply (a 503 'loading' counts); False on refused / timeout."""
    import urllib.error
    try:
        (http or strata_http)("/models", None, STRATA_ALIVE_S)
        return True
    except urllib.error.HTTPError:
        return True
    except Exception:                                                # noqa: BLE001
        return False


def select_backend(choice="auto", http=None, sleep=None, clock=None, wait_s=STRATA_LOAD_WAIT_S,
                   poll_s=STRATA_LOAD_POLL_S, log=None):
    """'strata' | 'ollama' | None. auto: Strata loaded -> strata; Strata answering but still loading -> poll up to
    wait_s, then strata, or None (yield: never load 5.* beside it); Strata silent -> ollama."""
    if choice in ("strata", "ollama"):
        return choice
    if strata_model_info(http):
        return "strata"
    if not strata_answers(http):
        return "ollama"
    sleep, clock = sleep or time.sleep, clock or time.time
    t0 = clock()
    if log:
        log("backend: Strata answers but is not loaded yet - waiting up to %d min" % (wait_s // 60))
    while clock() - t0 < wait_s:
        sleep(poll_s)
        if strata_model_info(http):
            return "strata"
    return None


def strata_alive(http=None):
    try:
        (http or strata_http)("/models", None, STRATA_ALIVE_S)
        return True, ""
    except Exception as e:                                           # noqa: BLE001
        return False, "Strata /v1/models did not answer in %d s (%s)" % (STRATA_ALIVE_S, type(e).__name__)


def check_guards(yield_fn=None, quiet_fn=None, lab_stop_fn=None, ps_fn=None, backend="ollama", alive_fn=None,
                 cline_fn=None, slots_fn=None):
    """('stop', why) | ('yield', why) | (None, ''). Strata: no RAM floor / owner-model check; endpoint must answer."""
    if os.path.exists(runner_stop_path()):
        return "stop", "runner STOP file"
    import ram_guard
    if backend == "strata":
        ok, why = (alive_fn or strata_alive)()
        if not ok:
            return "yield", why
    else:
        y, why = (yield_fn or ram_guard.should_yield)()
        if y:
            return "yield", why
    q, qwhy = (quiet_fn or ram_guard.quiet_on)()
    if q:
        return "yield", "quiet mode (%s)" % qwhy
    if (lab_stop_fn or (lambda: os.path.exists(ram_guard.stop_path())))():
        return "yield", "qwen_lab STOP file"
    if backend != "strata":
        o, owhy = other_model_loaded(ps_fn)
        if o:
            return "yield", owhy
    b, bwhy = engine_busy(backend, cline_fn, slots_fn)
    if b:
        return "yield", bwhy
    return None, ""


# ------------------------------------------------------------------------------------------------ router
def router_http(path, payload=None, timeout=ROUTER_ALIVE_S):
    import urllib.request
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(ROUTER_URL + path, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def router_alive(http=None):
    try:
        (http or router_http)("/models", None, ROUTER_ALIVE_S)
        return True
    except Exception:                                                # noqa: BLE001
        return False


# ------------------------------------------------------------------------------------------------ model
class RunnerChat:
    """qwen_lab.OllamaChat with the runner's keep_alive (5m in a task) and a hard num_ctx of 32768."""
    backend = "ollama"
    ctx_limit = CTX_LIMIT

    def __init__(self):
        import qwen_lab
        self.inner = qwen_lab.OllamaChat(model=MODEL, num_ctx=NUM_CTX)
        self.num_ctx = NUM_CTX
        self.model = MODEL

    def chat(self, messages, tools):
        LL, q = self.inner.LL, self.inner
        import qwen_lab
        payload = {"model": q.model, "messages": messages, "stream": False, "think": q.think,
                   "keep_alive": KEEP_ALIVE_TASK, "tools": [{"type": "function", "function": t} for t in tools],
                   "options": {"temperature": 0.2, "seed": 20261028, "num_ctx": min(int(q.num_ctx), NUM_CTX),
                               "num_predict": qwen_lab.NUM_PREDICT, **LL.cpu_options()}}
        t0 = time.time()
        d = LL._http_json("/api/chat", payload, timeout=q.timeout)
        if d.get("error"):
            raise LL.OllamaError("Ollama error: %s" % str(d["error"])[:300])
        return d.get("message") or {}, {"secs": round(time.time() - t0, 1), "eval_tokens": d.get("eval_count"),
                                         "prompt_tokens": d.get("prompt_eval_count"),
                                         "done_reason": d.get("done_reason")}

    def unload(self):
        try:
            self.inner.LL._http_json("/api/generate", {"model": MODEL, "keep_alive": 0}, timeout=30)
        except Exception:                                            # noqa: BLE001
            pass


def to_openai_messages(messages):
    """Runner messages (Ollama shape) -> OpenAI chat shape: tool_call ids, string arguments, tool_call_id links."""
    out, pending = [], []
    for i, m in enumerate(messages):
        role = m.get("role")
        if role == "assistant" and m.get("tool_calls"):
            tcs = []
            for j, tc in enumerate(m["tool_calls"]):
                fn = tc.get("function") or {}
                args = fn.get("arguments")
                if not isinstance(args, str):
                    args = json.dumps(args or {})
                tid = tc.get("id") or "call_%d_%d" % (i, j)
                tcs.append({"id": tid, "type": "function", "function": {"name": fn.get("name"), "arguments": args}})
            pending = [t["id"] for t in tcs]
            out.append({"role": "assistant", "content": m.get("content") or "", "tool_calls": tcs})
        elif role == "tool":
            tid = m.get("tool_call_id")
            if tid and tid in pending:
                pending.remove(tid)
            elif not tid:
                tid = pending.pop(0) if pending else "call_x"
            out.append({"role": "tool", "tool_call_id": tid, "content": m.get("content") or ""})
        else:
            out.append({"role": role, "content": m.get("content") or ""})
    return out


def parse_openai_reply(d):
    """(message, stats) from a /v1/chat/completions reply; done_reason mirrors finish_reason ('length' kept)."""
    if d.get("error"):
        raise RuntimeError("Strata error: %s" % str(d["error"])[:300])
    ch = (d.get("choices") or [{}])[0]
    m = ch.get("message") or {}
    tcs = []
    for tc in m.get("tool_calls") or []:
        fn = tc.get("function") or {}
        tcs.append({"id": tc.get("id"), "function": {"name": fn.get("name"), "arguments": fn.get("arguments") or "{}"}})
    msg = {"role": "assistant", "content": m.get("content") or ""}
    if tcs:
        msg["tool_calls"] = tcs
    u = d.get("usage") or {}
    return msg, {"eval_tokens": u.get("completion_tokens"), "prompt_tokens": u.get("prompt_tokens"),
                 "done_reason": ch.get("finish_reason")}


def strata_ctx_limit(n_ctx):
    """Compaction budget in chars: min(n_ctx - reply room, 200k) tokens x 4 (never below the Ollama budget)."""
    try:
        n = int(n_ctx)
    except (TypeError, ValueError):
        n = NUM_CTX
    return max(CTX_LIMIT, min(n - STRATA_REPLY_TOK, STRATA_CTX_CAP_TOK) * CHARS_PER_TOK)


class StrataChat:
    """OpenAI /v1/chat/completions on the Strata server. Never sends keep_alive or an unload."""
    backend = "strata"

    def __init__(self, http=None, info=None):
        self.http = http or strata_http
        self.model = STRATA_MODEL
        info = info if info is not None else (strata_model_info(self.http) or {})
        self.num_ctx = int(((info.get("meta") or {}).get("n_ctx")) or NUM_CTX)
        self.ctx_limit = strata_ctx_limit(self.num_ctx)

    def chat(self, messages, tools):
        payload = {"model": self.model, "messages": to_openai_messages(messages), "temperature": 0.2,
                   "max_tokens": STRATA_REPLY_TOK, "stream": False,
                   "tools": [{"type": "function", "function": t} for t in tools]}
        t0 = time.time()
        d = self.http("/chat/completions", payload, STRATA_TIMEOUT_S) or {}
        msg, stats = parse_openai_reply(d)
        stats["secs"] = round(time.time() - t0, 1)
        return msg, stats


class RouterChat:
    """OpenAI /v1/chat/completions through the router (:11435) as model 5.qwen3.6:35b-32k; the router picks the
    backend (Strata while it is up, else Ollama). On the Ollama backend the model is unloaded after the task."""

    def __init__(self, backend="ollama", http=None, info=None):
        self.backend = backend
        self.http = http or router_http
        self.model = MODEL
        if backend == "strata":
            info = info if info is not None else (strata_model_info() or {})
            self.num_ctx = int(((info.get("meta") or {}).get("n_ctx")) or NUM_CTX)
            self.ctx_limit = strata_ctx_limit(self.num_ctx)
            self.max_tokens = STRATA_REPLY_TOK
        else:
            self.num_ctx, self.ctx_limit, self.max_tokens = NUM_CTX, CTX_LIMIT, None

    def chat(self, messages, tools):
        payload = {"model": self.model, "messages": to_openai_messages(messages), "temperature": 0.2, "seed": 20261028,
                   "stream": False, "tools": [{"type": "function", "function": t} for t in tools]}
        if self.max_tokens:
            payload["max_tokens"] = self.max_tokens
        t0 = time.time()
        d = self.http("/chat/completions", payload, STRATA_TIMEOUT_S) or {}
        msg, stats = parse_openai_reply(d)
        stats["secs"] = round(time.time() - t0, 1)
        return msg, stats

    def unload(self):
        if self.backend != "ollama":
            return                                                   # never unload Strata
        try:
            import local_llm as LL
            LL._http_json("/api/generate", {"model": MODEL, "keep_alive": 0}, timeout=30)
        except Exception:                                            # noqa: BLE001
            pass


def default_chat(backend, router_ok=None):
    """Router when it answers, else the direct path for this backend."""
    if (router_ok or router_alive)():
        return RouterChat(backend)
    return StrataChat() if backend == "strata" else RunnerChat()


def compact(messages, limit=CTX_LIMIT, keep_last=6):
    import qwen_lab
    return qwen_lab.compact_messages(messages, limit=limit, keep_last=keep_last)


# ------------------------------------------------------------------------------------------------ runner
def _post_inbox(n, icon_word, one):
    import chat_inbox
    return chat_inbox.post("MANAGER", "QWEN Q%d: %s - %s" % (n, icon_word, one), "QWEN")


def _push(n, ok, one, log=None):
    try:
        if REPO not in sys.path:
            sys.path.insert(0, REPO)
        from api import ntfy_push
        note = ntfy_push.plain("Qwen Q%d" % n, "done, check it" if ok else "blocked", None, one,
                               "nothing - Claude checks it", priority="low")
        return ntfy_push.push_result(note["message"], title=note["title"], priority=note["priority"], log=log)
    except Exception as e:                                           # noqa: BLE001
        return False, "%s: %s" % (type(e).__name__, str(e)[:80])


class Runner:
    def __init__(self, chat_factory=None, guards=None, sleep=None, clock=None, poster=None, pusher=None,
                 roots=None, max_turns=MAX_TURNS, max_task_s=MAX_TASK_S, backend="ollama", selector=None):
        self.backend = backend
        self.selector = selector or (lambda c: select_backend(c, sleep=self.sleep, clock=self.clock, log=self.log))
        self.cur = backend if backend in ("strata", "ollama") else "ollama"
        self.chat_factory = chat_factory or (lambda: default_chat(self.cur))
        self.guards = guards or (lambda: check_guards(backend=self.cur))
        self.sleep = sleep or time.sleep
        self.clock = clock or time.time
        self.poster = poster or _post_inbox
        self.pusher = pusher or _push
        self.roots = roots
        self.max_turns = max_turns
        self.max_task_s = max_task_s
        os.makedirs(os.path.join(home(), "transcripts"), exist_ok=True)

    # ---- state / log
    def state_path(self):
        return os.path.join(home(), "state.json")

    def load_state(self):
        try:
            with open(self.state_path(), encoding="utf-8") as f:
                return json.load(f) or {}
        except Exception:                                            # noqa: BLE001
            return {}

    def save_state(self, st):
        tmp = self.state_path() + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(st, f, indent=2)
        os.replace(tmp, self.state_path())

    def log(self, msg):
        line = "%s %s" % (now_s(), msg)
        try:
            with open(os.path.join(home(), "runner.log"), "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except OSError:
            pass
        print(line, flush=True)

    # ---- guards
    def wait_guards(self):
        """True when clear to go; False when the runner STOP file says exit."""
        while True:
            act, why = self.guards()
            if act == "stop":
                self.log("STOP: %s - exiting" % why)
                return False
            if act is None:
                return True
            self.log("yield: %s - waiting %d s" % (why, GUARD_SLEEP_S))
            self.sleep(GUARD_SLEEP_S)

    # ---- crash resume
    def resume(self):
        st = self.load_state()
        fl = st.get("in_flight")
        if not fl:
            return
        n, p = int(fl["n"]), fl["path"]
        key = "Q%d" % n
        if os.path.exists(p) and WORKING in first_line(p):
            tries = int(st.setdefault("attempts", {}).get(key, 0))
            if tries >= 2:
                self._close(n, p, "blocked", "", "runner died mid-task twice", turns=0, secs=0, meta=None)
                self.log("resume: Q%d left 🟡 twice by a dead runner - marked 🔴" % n)
            else:
                set_first_line(p, "STATUS: %s open" % OPEN)
                set_status_row(n, OPEN, "runner died mid-task - back to open for one retry")
                self.log("resume: Q%d left 🟡 by a dead runner - reset to ⭕ for one retry" % n)
        st["in_flight"] = None
        self.save_state(st)

    # ---- one task
    def system_prompt(self, task_text):
        try:
            rules, _ = _read_text(os.path.join(tasks_dir(), "README.md"))
        except OSError:
            rules = ""
        return ("You are Qwen, working ONE task file unattended for the EDGE-LOG project.\n"
                "TASK-FILE RULES (the harness does the status edits, the inbox post and the push for you):\n%s\n\n"
                "YOUR TOOLS: read_file, list_dir, grep (all READ-ONLY; absolute Windows paths under C:\\EdgeLog, "
                "%s or the memory folder), write_scratch + run_python (small READ-ONLY .py scripts in the scratch "
                "folder; print your results) and finish. You cannot write other files, git, or touch "
                "NinjaTrader/Webull/TradingView/credentials. If the task needs something you cannot do, call finish "
                "with status 'blocked' and say why. Read in small pieces (offset/limit). When done, call finish with "
                "result_markdown (what you found, files used, time zone of every time, how sure you are - never "
                "invent meanings), status, and one_line (<= 200 chars).\n\nTHE TASK:\n%s"
                % (rules.strip(), MAIN_CHECKOUT, task_text))

    def work(self, n, path):
        st = self.load_state()
        key = "Q%d" % n
        st.setdefault("attempts", {})[key] = int(st.get("attempts", {}).get(key, 0)) + 1
        st["in_flight"] = {"n": n, "path": path, "at": now_s()}
        self.save_state(st)
        set_first_line(path, STATUS_WORKING)
        set_status_row(n, WORKING, "started %s" % datetime.datetime.now().strftime("%H:%M"))
        self.log("Q%d: started (%s)" % (n, os.path.basename(path)))
        task_text, _ = _read_text(path)
        chat = self.chat_factory()
        model = getattr(chat, "model", None)
        model = model if isinstance(model, str) and model else MODEL
        model = STRATA_DISPLAY if model == STRATA_MODEL else model
        if isinstance(chat, RouterChat):
            model = "%s via router" % (STRATA_DISPLAY if self.cur == "strata" else MODEL)
        nctx = getattr(chat, "num_ctx", NUM_CTX)
        nctx = nctx if isinstance(nctx, int) else NUM_CTX
        self.task_meta = {"backend": self.cur, "model": model, "num_ctx": nctx}
        self.log("Q%d: backend %s model %s (num_ctx %d)" % (n, self.cur, model, nctx))
        msgs = [{"role": "system", "content": self.system_prompt(task_text)},
                {"role": "user", "content": "Start the task now. Use the tools; end with finish."}]
        ts = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        tpath = os.path.join(home(), "transcripts", "Q%d-%s.json" % (n, ts))
        tr = {"task": key, "file": path, "backend": self.cur, "model": model, "num_ctx": nctx, "started": now_s(), "calls": [],
              "messages": msgs}
        base_limit = getattr(chat, "ctx_limit", CTX_LIMIT)
        base_limit = base_limit if isinstance(base_limit, int) else CTX_LIMIT
        t0, turns, empty, limit, keep = self.clock(), 0, 0, base_limit, 6
        max_turns, max_task_s = self.max_turns, self.max_task_s
        if self.cur == "strata":
            max_turns, max_task_s = max(max_turns, STRATA_MAX_TURNS), max(max_task_s, STRATA_MAX_TASK_S)
        outcome = None

        def dump():
            try:
                with open(tpath, "w", encoding="utf-8") as f:
                    json.dump(tr, f, indent=1, default=str)
            except OSError:
                pass
        try:
            while outcome is None:
                if turns >= max_turns:
                    outcome = ("blocked", "", "turn budget used (%d turns) without finish" % max_turns)
                    break
                if self.clock() - t0 > max_task_s:
                    outcome = ("blocked", "", "%d-min wall budget used without finish" % (max_task_s // 60))
                    break
                if not self.wait_guards():
                    set_first_line(path, "STATUS: %s open" % OPEN)
                    set_status_row(n, OPEN, "runner stopped mid-task - back to open")
                    st = self.load_state()
                    st["in_flight"] = None
                    st["attempts"][key] = max(0, int(st["attempts"].get(key, 1)) - 1)
                    self.save_state(st)
                    self.log("Q%d: runner STOP mid-task - reset to ⭕" % n)
                    tr["ended"] = "stopped"
                    dump()
                    return "stopped"
                turns += 1
                try:
                    msg, stats = chat.chat(compact(msgs, limit, keep), TOOLS)
                except Exception as e:                               # noqa: BLE001
                    outcome = ("blocked", "", "model call failed: %s" % str(e)[:150])
                    break
                tr["calls"].append(dict(turn=turns, at=now_s(), **(stats or {})))
                content = msg.get("content") or ""
                tcs = msg.get("tool_calls") or []
                clean = {"role": "assistant", "content": content}
                if tcs:
                    clean["tool_calls"] = tcs
                msgs.append(clean)
                if not tcs:
                    empty += 1
                    cut = (stats or {}).get("done_reason") == "length"
                    self.log("Q%d: turn %d no tool call (%s, %d of %d)" % (n, turns, "cut at length" if cut else
                                                                         ("empty" if not content.strip() else "text only"),
                                                                         empty, MAX_EMPTY))
                    if empty >= MAX_EMPTY:
                        outcome = ("blocked", "", "the model gave %d replies with no tool call%s" % (
                            empty, " (cut at the context limit)" if cut else ""))
                        break
                    if cut or not content.strip():
                        limit, keep = max(15000, limit // 2), max(2, keep - 2)
                    msgs.append({"role": "user", "content": "No tool call came through. Keep replies short. "
                                 "Call a tool now - read_file/list_dir/grep - or finish if you have the answer."})
                    dump()
                    continue
                empty = 0
                for tc in tcs:
                    fn = tc.get("function") or {}
                    name, args = fn.get("name"), fn.get("arguments") or {}
                    if isinstance(args, str):
                        try:
                            args = json.loads(args)
                        except ValueError:
                            args = {}
                    if name == "finish":
                        status = "done" if str(args.get("status")) == "done" else "blocked"
                        outcome = (status, str(args.get("result_markdown") or ""),
                                   str(args.get("one_line") or "").strip() or "(no line)")
                        break
                    res = run_tool(name, args, self.roots)
                    self.log("Q%d: turn %d %s(%s) -> %d chars%s" % (n, turns, name, json.dumps(args)[:160], len(res),
                                                                   " " + res[:80] if res.startswith(("REFUSED", "ERROR")) else ""))
                    if name in ("run_python", "write_scratch"):
                        tr.setdefault("python_runs", []).append({"turn": turns, "at": now_s(), "tool": name,
                                                                 "args": args, "result": res})
                    tmsg = {"role": "tool", "content": res, "tool_name": name}
                    if tc.get("id"):
                        tmsg["tool_call_id"] = tc["id"]
                    msgs.append(tmsg)
                dump()
        finally:
            try:
                getattr(chat, "unload", lambda: None)()
            except Exception:                                        # noqa: BLE001
                pass
        status, md, one = outcome
        secs = self.clock() - t0
        self._close(n, path, status, md, one, turns, secs, meta=tr)
        tr["ended"], tr["outcome"] = status, one
        dump()
        return status

    def _close(self, n, path, status, md, one, turns, secs, meta):
        one = re.sub(r"\s+", " ", str(one)).strip()[:ONE_LINE_MAX]
        tm = getattr(self, "task_meta", None) or {"backend": self.cur, "model": MODEL, "num_ctx": NUM_CTX}
        footer = ("\n\n---\n_backend %s · model %s (num_ctx %d) · %d turns · wall %.1f min · generated by tools/qwen_runner.py "
                  "(B3) at %s · **UNVERIFIED** - Claude has not checked this yet_"
                  % (tm["backend"], tm["model"], tm["num_ctx"], turns, secs / 60.0, now_s()))
        body = (md.strip() or "(no result - %s)" % one)
        append_result(path, "## RESULT\n" + body + footer)
        if status == "done":
            set_first_line(path, STATUS_DONE)
            set_status_row(n, DONE, one)
            word = "🟢 DONE"
        else:
            set_first_line(path, "STATUS: 🔴 blocked - %s" % one)
            set_status_row(n, BLOCKED, one)
            word = "🔴 BLOCKED"
        try:
            pid = self.poster(n, word, one)
            self.log("Q%d: inbox MANAGER #%s" % (n, pid))
        except Exception as e:                                       # noqa: BLE001
            self.log("Q%d: inbox post failed: %s" % (n, e))
        try:
            self.log("Q%d: push %s" % (n, self.pusher(n, status == "done", one)))
        except Exception as e:                                       # noqa: BLE001
            self.log("Q%d: push failed: %s" % (n, e))
        st = self.load_state()
        st["in_flight"] = None
        st.setdefault("history", []).append({"task": "Q%d" % n, "status": status, "line": one, "turns": turns,
                                             "backend": tm["backend"], "model": tm["model"],
                                             "secs": round(secs, 1), "at": now_s()})
        st["history"] = st["history"][-50:]
        self.save_state(st)
        self.log("Q%d: %s - %s [backend %s, model %s]" % (n, word, one, tm["backend"], tm["model"]))

    # ---- cycles
    def cycle(self):
        """'stop' | 'idle' | task outcome."""
        if pick_task():                                              # re-check the backend before each task
            new = self.selector(self.backend)
            if new is None:
                self.log("yield: Strata still loading after %d min - not loading a second model" % (STRATA_LOAD_WAIT_S // 60))
                return "idle"
            if new != self.cur:
                self.log("backend: %s -> %s" % (self.cur, new))
            self.cur = new
        if not self.wait_guards():
            return "stop"
        pick = pick_task()
        if not pick:
            return "idle"
        self.task_meta = None
        return self.work(*pick)

    def run(self, once=False):
        self.log("runner start (once=%s, backend=%s) tasks=%s" % (once, self.backend, tasks_dir()))
        self.resume()
        while True:
            r = self.cycle()
            if r in ("stop", "stopped") or once:
                self.log("runner exit (%s)" % r)
                return r
            if r == "idle":
                self.sleep(IDLE_SLEEP_S)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Qwen task runner (AUTOMATIONS.md B3)")
    ap.add_argument("cmd", choices=["run", "once"])
    ap.add_argument("--backend", choices=["auto", "strata", "ollama"], default="auto")
    a = ap.parse_args(argv)
    Runner(backend=a.backend).run(once=a.cmd == "once")
    return 0


if __name__ == "__main__":
    sys.exit(main())
