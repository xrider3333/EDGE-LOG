"""QWEN TASK RUNNER (AUTOMATIONS.md B3, MANAGER #204) - works the Qwen task board unattended.

  python tools/qwen_runner.py run      loop: lowest-numbered open (⭕) Q task, else sleep 5 min
  python tools/qwen_runner.py once     one cycle (one task at most), then exit

Board: C:\\EdgeLog\\manager\\qwen_tasks (Q<n>-*.md + STATUS.md; override QWEN_TASKS_DIR).
State/log/transcripts: C:\\EdgeLog\\qwen_runner (override QWEN_RUNNER_HOME). STOP file there = exit cleanly.

Guards before every task AND every model turn (wait 60 s, re-check):
  ram_guard.should_yield() (free RAM < 6 GB), quiet mode, the qwen_lab STOP file,
  Ollama /api/ps shows a model named 1.* or 2.* (the owner's Cline) - never start beside it.
Model 3.qwen3.6:35b-32k, num_ctx 32768 (never more), keep_alive 5m in a task, 0 after.
Tools are READ-ONLY (read_file, list_dir, grep) + finish. Reads only under C:\\EdgeLog, the main checkout and the
memory folder; refuses NinjaTrader/Webull/TradingView/.ssh, key/token/secret/password/credential/.env/.pem names,
binaries. Writes ONLY: the task file (line 1 + ## RESULT), its STATUS.md icon, the MANAGER inbox, one phone push,
and its own home. No git, no subprocess (ram_guard may call nvidia-smi).
The result is the local model's work: UNVERIFIED until Claude checks it.
"""
import argparse
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

MODEL = "3.qwen3.6:35b-32k"
NUM_CTX = 32768
KEEP_ALIVE_TASK = "5m"
MAX_TURNS = 40
MAX_TASK_S = 45 * 60
MAX_EMPTY = 3
READ_CAP = 12000
GREP_MAX_FILES = 2000
GREP_MAX_HITS = 200
GREP_MAX_FILE_BYTES = 5 * 1024 * 1024
IDLE_SLEEP_S = 300
GUARD_SLEEP_S = 60
ONE_LINE_MAX = 200
CTX_LIMIT = 75000

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
        return "ERROR: unknown tool %r (tools: read_file, list_dir, grep, finish)" % name
    except Refused as e:
        return "REFUSED: %s" % e
    except Exception as e:                                           # noqa: BLE001
        return "ERROR: %s: %s" % (type(e).__name__, str(e)[:200])


# ------------------------------------------------------------------------------------------------ guards
def ollama_ps():
    import local_llm as LL
    return LL._http_json("/api/ps", timeout=10)


def owner_model_loaded(ps_fn=None):
    """(True, why) when a 1.* / 2.* model is loaded (the owner's Cline) or Ollama cannot be asked."""
    try:
        d = (ps_fn or ollama_ps)() or {}
    except Exception as e:                                           # noqa: BLE001
        return True, "Ollama /api/ps failed (%s)" % type(e).__name__
    for m in d.get("models") or []:
        name = str(m.get("name") or m.get("model") or "")
        if name.startswith("1.") or name.startswith("2."):
            return True, "owner model %s is loaded" % name
    return False, ""


def runner_stop_path():
    return os.path.join(home(), "STOP")


def check_guards(yield_fn=None, quiet_fn=None, lab_stop_fn=None, ps_fn=None):
    """('stop', why) | ('yield', why) | (None, '')."""
    if os.path.exists(runner_stop_path()):
        return "stop", "runner STOP file"
    import ram_guard
    y, why = (yield_fn or ram_guard.should_yield)()
    if y:
        return "yield", why
    q, qwhy = (quiet_fn or ram_guard.quiet_on)()
    if q:
        return "yield", "quiet mode (%s)" % qwhy
    if (lab_stop_fn or (lambda: os.path.exists(ram_guard.stop_path())))():
        return "yield", "qwen_lab STOP file"
    o, owhy = owner_model_loaded(ps_fn)
    if o:
        return "yield", owhy
    return None, ""


# ------------------------------------------------------------------------------------------------ model
class RunnerChat:
    """qwen_lab.OllamaChat with the runner's keep_alive (5m in a task) and a hard num_ctx of 32768."""

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
                               "num_predict": qwen_lab.NUM_PREDICT}}
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
                 roots=None, max_turns=MAX_TURNS, max_task_s=MAX_TASK_S):
        self.chat_factory = chat_factory or RunnerChat
        self.guards = guards or check_guards
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
                set_status_icon(n, OPEN)
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
                "%s or the memory folder) and finish. You cannot run code, write files, git, or touch "
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
        set_status_icon(n, WORKING)
        self.log("Q%d: started (%s)" % (n, os.path.basename(path)))
        task_text, _ = _read_text(path)
        chat = self.chat_factory()
        msgs = [{"role": "system", "content": self.system_prompt(task_text)},
                {"role": "user", "content": "Start the task now. Use the tools; end with finish."}]
        ts = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        tpath = os.path.join(home(), "transcripts", "Q%d-%s.json" % (n, ts))
        tr = {"task": key, "file": path, "model": MODEL, "num_ctx": NUM_CTX, "started": now_s(), "calls": [],
              "messages": msgs}
        t0, turns, empty, limit, keep = self.clock(), 0, 0, CTX_LIMIT, 6
        outcome = None

        def dump():
            try:
                with open(tpath, "w", encoding="utf-8") as f:
                    json.dump(tr, f, indent=1, default=str)
            except OSError:
                pass
        try:
            while outcome is None:
                if turns >= self.max_turns:
                    outcome = ("blocked", "", "turn budget used (%d turns) without finish" % self.max_turns)
                    break
                if self.clock() - t0 > self.max_task_s:
                    outcome = ("blocked", "", "45-min wall budget used without finish")
                    break
                if not self.wait_guards():
                    set_first_line(path, "STATUS: %s open" % OPEN)
                    set_status_icon(n, OPEN)
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
                    msgs.append({"role": "tool", "content": res, "tool_name": name})
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
        footer = ("\n\n---\n_model %s (num_ctx %d) · %d turns · wall %.1f min · generated by tools/qwen_runner.py "
                  "(B3) at %s · **UNVERIFIED** - Claude has not checked this yet_"
                  % (MODEL, NUM_CTX, turns, secs / 60.0, now_s()))
        body = (md.strip() or "(no result - %s)" % one)
        append_result(path, "## RESULT\n" + body + footer)
        if status == "done":
            set_first_line(path, STATUS_DONE)
            set_status_icon(n, DONE)
            word = "🟢 DONE"
        else:
            set_first_line(path, "STATUS: 🔴 blocked - %s" % one)
            set_status_icon(n, BLOCKED)
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
                                             "secs": round(secs, 1), "at": now_s()})
        st["history"] = st["history"][-50:]
        self.save_state(st)
        self.log("Q%d: %s - %s" % (n, word, one))

    # ---- cycles
    def cycle(self):
        """'stop' | 'idle' | task outcome."""
        if not self.wait_guards():
            return "stop"
        pick = pick_task()
        if not pick:
            return "idle"
        return self.work(*pick)

    def run(self, once=False):
        self.log("runner start (once=%s) tasks=%s" % (once, tasks_dir()))
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
    a = ap.parse_args(argv)
    Runner().run(once=a.cmd == "once")
    return 0


if __name__ == "__main__":
    sys.exit(main())
