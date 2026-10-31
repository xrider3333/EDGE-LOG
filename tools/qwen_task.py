"""QWEN TASK = THE ONE DOOR (MANAGER #222, owner GO 10-30). Chats and tools never call the local model directly; they
file a numbered task here and tools/qwen_runner.py (the one worker) runs it on whatever model is loaded.

  python tools/qwen_task.py add '<title>' '<body>' [--from LANE]   -> writes Q<next>-<slug>.md + a STATUS.md row
  python tools/qwen_task.py list                                    -> number, status line, title
  python tools/qwen_task.py show N                                  -> the whole task file
  python tools/qwen_task.py check N [--minutes M]                   -> PASS/FAIL lines for the JSON answer block (c21)
                                                                       + CHECK_START/CHECK_END stamps and a minutes row (c22)

  from qwen_task import add_task; n = add_task(title, body, frm="MANAGER")

Folder: C:\\EdgeLog\\manager\\qwen_tasks (override QWEN_TASKS_DIR). Q<next> = max existing Q number + 1, taken under a
lock file (.qwen_task.lock, O_EXCL; a lock older than 60 s is stale) so two chats never get the same number.
Task file: line 1 "STATUS: ⭕ open", then "# Q<n> - <title>", "From: <LANE> · Date: YYYY-MM-DD", blank, body. New
files copy the line endings of the newest existing Q file. STATUS.md is read and written as UTF-8 bytes (BOM and
line endings kept, never cp1252); the new row is "| Q<n> | <title> | ⭕ | YYYY-MM-DD filed by <LANE> |".

ANSWER FORM (c21, scope P2): `add` appends ANSWER_RULE to every task body, so the RESULT must END with one fenced ```json
block {"answer": str, "numbers": [{"name","value","unit"}], "times": [{"what","iso","tz"}], "files_read": [...],
"confidence": 0-1}. `check N` reads the LAST such block under ## RESULT and prints one "PASS <what>" / "FAIL <what>"
line per rule (block present, valid JSON, answer is text, every number has a unit, every time has a tz and an ISO
date-time that parses, files_read is a list, confidence in 0..1); exit 0 = all PASS. The runner's own parsing is
untouched: the block is plain markdown inside result_markdown.
CHECK MINUTES (c22, scope P13): the first `check` on a task stamps "CHECK_START: <local ISO with offset>" at the end
of the task file, every `check` stamps/updates "CHECK_END: ..."; `--minutes M` overrides the clock. The row
"| Q<n> | date | Qwen wall min (runner footer) | Claude check min | PASS/FAIL |" is written (replaced if already
there) under "## Check minutes" in C:\\EdgeLog\\manager\\qwen_vs_claude.md (override QWEN_VS_CLAUDE).
"""
import argparse
import datetime
import glob
import json
import os
import re
import sys
import time

OPEN = "⭕"
LOCK_NAME = ".qwen_task.lock"
LOCK_STALE_S = 60
LOCK_WAIT_S = 30

ANSWER_RULE = (
    "## ANSWER FORM (required - tools/qwen_task.py check reads it)\n"
    "End your ## RESULT with ONE fenced ```json block, nothing after it but the runner footer:\n"
    "```json\n"
    "{\"answer\": \"<the finding in plain words, one short paragraph>\",\n"
    " \"numbers\": [{\"name\": \"<what>\", \"value\": 0, \"unit\": \"USD|points|%|count|min|...\"}],\n"
    " \"times\": [{\"what\": \"<which time>\", \"iso\": \"2026-10-31T09:40\", \"tz\": \"UTC|ET|MST\"}],\n"
    " \"files_read\": [\"C:\\\\...\"], \"confidence\": 0.0}\n"
    "```\n"
    "Every number carries a unit (dollars are not points); every time carries its time zone and an ISO date-time. "
    "Empty lists are fine. No block, or a bad one, = the check FAILS.")
CHECK_START = "CHECK_START:"
CHECK_END = "CHECK_END:"
CHECK_SECTION = "## Check minutes"
CHECK_HEAD = [CHECK_SECTION + " (written by tools/qwen_task.py check - Qwen wall from the runner footer, Claude minutes from the stamps)",
              "| Task | Date | Qwen wall min | Claude check min | JSON block |", "|---|---|---|---|---|"]


def vs_path():
    return os.environ.get("QWEN_VS_CLAUDE") or r"C:\EdgeLog\manager\qwen_vs_claude.md"


def tasks_dir():
    return os.environ.get("QWEN_TASKS_DIR") or r"C:\EdgeLog\manager\qwen_tasks"


def today():
    return datetime.date.today().isoformat()


def _read(path):
    with open(path, "rb") as f:
        raw = f.read()
    bom = raw.startswith(b"\xef\xbb\xbf")
    return (raw[3:] if bom else raw).decode("utf-8"), bom


def _write(path, text, bom=False):
    tmp = path + ".qttmp"
    with open(tmp, "wb") as f:
        f.write((b"\xef\xbb\xbf" if bom else b"") + text.encode("utf-8"))
    os.replace(tmp, path)


def _eol(text, default="\n"):
    if "\r\n" in text:
        return "\r\n"
    return "\n" if "\n" in text else default


def cell(s):
    """One table cell / one line: no pipes, no newlines."""
    return re.sub(r"\s+", " ", str(s).replace("|", "/")).strip()


def slug(title, n=40):
    s = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return (s[:n].rstrip("-") or "task")


def task_files(tdir=None):
    out = []
    for p in glob.glob(os.path.join(tdir or tasks_dir(), "Q*-*.md")):
        m = re.match(r"Q(\d+)-", os.path.basename(p))
        if m:
            out.append((int(m.group(1)), p))
    return sorted(out)


def next_number(tdir=None):
    tdir = tdir or tasks_dir()
    nums = [n for n, _ in task_files(tdir)]
    st = os.path.join(tdir, "STATUS.md")
    if os.path.exists(st):                                   # a row can exist before its file (hand-filed)
        nums += [int(x) for x in re.findall(r"^\|\s*Q(\d+)\s*\|", _read(st)[0], re.M)]
    return max(nums or [0]) + 1


class Lock:
    def __init__(self, tdir, wait_s=LOCK_WAIT_S, sleep=time.sleep):
        self.path = os.path.join(tdir, LOCK_NAME)
        self.wait_s, self.sleep = wait_s, sleep

    def __enter__(self):
        t0 = time.time()
        while True:
            try:
                fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(fd, ("%d %s" % (os.getpid(), time.time())).encode())
                os.close(fd)
                return self
            except FileExistsError:
                try:
                    if time.time() - os.path.getmtime(self.path) > LOCK_STALE_S:
                        os.remove(self.path)
                        continue
                except OSError:
                    continue
                if time.time() - t0 > self.wait_s:
                    raise TimeoutError("qwen_task lock held: %s" % self.path)
                self.sleep(0.1)

    def __exit__(self, *a):
        try:
            os.remove(self.path)
        except OSError:
            pass


def _newest_eol(tdir):
    files = task_files(tdir)
    if not files:
        return "\n"
    try:
        return _eol(_read(max(files, key=lambda x: os.path.getmtime(x[1]))[1])[0])
    except OSError:
        return "\n"


def append_status_row(n, title, note, icon=OPEN, tdir=None):
    p = os.path.join(tdir or tasks_dir(), "STATUS.md")
    row = "| Q%d | %s | %s | %s |" % (n, cell(title), icon, cell(note))
    if os.path.exists(p):
        text, bom = _read(p)
        eol = _eol(text, "\r\n")
        sep = "" if (not text or text.endswith(("\n", "\r"))) else eol
        _write(p, text + sep + row + eol, bom)
    else:
        eol = "\r\n"
        _write(p, "# Qwen task board" + eol + "| # | Task | Status | Note |" + eol + "|---|------|--------|------|"
               + eol + row + eol)
    return row


def add_task(title, body, frm="MANAGER", tdir=None):
    """File Q<next>; returns its number."""
    tdir = tdir or tasks_dir()
    title, frm = cell(title) or "untitled", cell(frm or "MANAGER") or "MANAGER"
    os.makedirs(tdir, exist_ok=True)
    with Lock(tdir):
        n = next_number(tdir)
        eol = _newest_eol(tdir)
        d = today()
        text = ("STATUS: %s open\n# Q%d - %s\nFrom: %s · Date: %s\n\n%s\n\n%s\n"
                % (OPEN, n, title, frm, d, str(body).replace("\r\n", "\n").rstrip(), ANSWER_RULE))
        path = os.path.join(tdir, "Q%d-%s.md" % (n, slug(title)))
        _write(path, text.replace("\n", eol))
        append_status_row(n, title, "%s filed by %s" % (d, frm), tdir=tdir)
    return n


def find(n, tdir=None):
    for k, p in task_files(tdir):
        if k == int(n):
            return p
    return None


def list_tasks(tdir=None):
    out = []
    for n, p in task_files(tdir):
        lines = _read(p)[0].splitlines()
        status = next((l for l in lines[:3] if l.lower().startswith("status:")), "")
        head = next((l.lstrip("# ").strip() for l in lines if l.startswith("#")), os.path.basename(p))
        out.append((n, status.strip(), head))
    return out

# ---------------------------------------------------------------- c21: JSON answer block check
_FENCE_RX = re.compile(r"```json[ \t]*\n(.*?)\n[ \t]*```", re.S | re.I)


def answer_block(text):
    """The LAST fenced ```json block under ## RESULT (raw string) or None."""
    text = text.replace("\r\n", "\n")
    i = text.find("## RESULT")
    part = text[i:] if i >= 0 else ""
    blocks = _FENCE_RX.findall(part)
    return blocks[-1] if blocks else None


def _iso_ok(v):
    if not isinstance(v, str) or not v.strip():
        return False
    try:
        datetime.datetime.fromisoformat(v.strip().replace("Z", "+00:00"))
        return True
    except ValueError:
        return False


def _num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def check_answer(text):
    """[(ok, what)] for the task text. A missing or unparsable block ends the list early."""
    out = []
    raw = answer_block(text)
    if raw is None:
        return [(False, "json block: none under ## RESULT")]
    out.append((True, "json block: present"))
    try:
        d = json.loads(raw)
    except ValueError as e:
        return out + [(False, "json parses: %s" % e)]
    if not isinstance(d, dict):
        return out + [(False, "json parses: top level is not an object")]
    out.append((True, "json parses"))
    for k in ("answer", "numbers", "times", "files_read", "confidence"):
        out.append((k in d, "key %s: %s" % (k, "present" if k in d else "MISSING")))
    a = d.get("answer")
    ok_a = isinstance(a, str) and bool(a.strip())
    out.append((ok_a, "answer: %s" % ("text" if ok_a else "not a non-empty string")))
    nums = d.get("numbers")
    if not isinstance(nums, list):
        out.append((False, "numbers: not a list"))
    else:
        bad = [i for i, x in enumerate(nums) if not (isinstance(x, dict) and isinstance(x.get("name"), str) and _num(x.get("value"))
                                                 and isinstance(x.get("unit"), str) and x.get("unit").strip())]
        out.append((not bad, "numbers: %d, unit on every number" % len(nums) if not bad
                    else "numbers: #%s missing name / number value / unit" % ",".join(map(str, bad))))
    tms = d.get("times")
    if not isinstance(tms, list):
        out.append((False, "times: not a list"))
    else:
        bad_tz = [i for i, x in enumerate(tms) if not (isinstance(x, dict) and isinstance(x.get("what"), str)
                                                    and isinstance(x.get("tz"), str) and x.get("tz").strip())]
        bad_iso = [i for i, x in enumerate(tms) if not (isinstance(x, dict) and _iso_ok(x.get("iso")))]
        out.append((not bad_tz, "times: %d, tz on every time" % len(tms) if not bad_tz
                    else "times: #%s missing what / tz" % ",".join(map(str, bad_tz))))
        out.append((not bad_iso, "times: ISO parses" if not bad_iso else "times: #%s iso does not parse" % ",".join(map(str, bad_iso))))
    fr = d.get("files_read")
    ok_f = isinstance(fr, list) and all(isinstance(x, str) for x in fr)
    out.append((ok_f, "files_read: %s" % ("list" if ok_f else "not a list of paths")))
    c = d.get("confidence")
    ok_c = _num(c) and 0 <= c <= 1
    out.append((ok_c, "confidence: %s" % (c if ok_c else "not a number in 0..1")))
    return out


# ---------------------------------------------------------------- c22: checker minutes
def _now_iso():
    return datetime.datetime.now().astimezone().isoformat(timespec="minutes")


def _stamp(text, key):
    m = re.search(r"^%s\s*(\S+)" % re.escape(key), text, re.M)
    return m.group(1) if m else None


def _set_stamp(text, key, val):
    line = "%s %s" % (key, val)
    if re.search(r"^%s.*$" % re.escape(key), text, re.M):
        return re.sub(r"^%s.*$" % re.escape(key), line, text, count=1, flags=re.M)
    return text.rstrip("\n") + "\n" + line + "\n"


def qwen_wall_minutes(text):
    """The runner footer's 'wall X min' (the last one) or None."""
    m = re.findall(r"wall\s+([\d.]+)\s+min", text)
    return float(m[-1]) if m else None


def _minutes(start, end):
    try:
        return round(max((datetime.datetime.fromisoformat(end) - datetime.datetime.fromisoformat(start)).total_seconds(), 0) / 60.0, 1)
    except (ValueError, TypeError):
        return None


def write_vs_row(n, date, qwen_min, claude_min, verdict, path=None):
    """Append (or replace the Q<n> row of) the Check minutes table in qwen_vs_claude.md."""
    path = path or vs_path()
    text, bom = _read(path) if os.path.exists(path) else ("", False)
    eol = _eol(text)
    text = text.replace("\r\n", "\n")
    row = "| Q%d | %s | %s | %s | %s |" % (n, date, "-" if qwen_min is None else qwen_min,
                                          "-" if claude_min is None else claude_min, verdict)
    if CHECK_SECTION not in text:
        text = text.rstrip("\n") + ("\n\n" if text.strip() else "") + "\n".join(CHECK_HEAD) + "\n" + row + "\n"
    else:
        i = text.index(CHECK_SECTION)
        head, tail = text[:i], text[i:]
        rx = r"^\|\s*Q%d\s*\|.*$" % n
        if re.search(rx, tail, re.M):
            tail = re.sub(rx, lambda _m: row, tail, count=1, flags=re.M)
        else:
            tail = tail.rstrip("\n") + "\n" + row + "\n"
        text = head + tail
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    _write(path, text.replace("\n", eol), bom)
    return row


def check_task(n, minutes=None, tdir=None, now=None, out=print):
    """c21 + c22: PASS/FAIL lines, CHECK_START/CHECK_END stamps, the minutes row. Returns 0 (all PASS) or 1."""
    n = int(n)
    path = find(n, tdir)
    if not path:
        out("FAIL no Q%d" % n)
        return 1
    text, bom = _read(path)
    eol = _eol(text)
    text = text.replace("\r\n", "\n")
    results = check_answer(text)
    for ok, what in results:
        out("%s %s" % ("PASS" if ok else "FAIL", what))
    now = now or _now_iso()
    start = _stamp(text, CHECK_START)
    end = now
    if minutes is not None:
        claude_min = round(float(minutes), 1)
        start = start or (datetime.datetime.fromisoformat(now) - datetime.timedelta(minutes=float(minutes))).isoformat(timespec="minutes")
    else:
        start = start or now
        claude_min = _minutes(start, end)
    text = _set_stamp(_set_stamp(text, CHECK_START, start), CHECK_END, end)
    _write(path, text.replace("\n", eol), bom)
    verdict = "PASS" if all(ok for ok, _ in results) else "FAIL"
    qwen_min = qwen_wall_minutes(text)
    write_vs_row(n, end[:10], qwen_min, claude_min, verdict)
    out("%s Q%d - Qwen wall %s min, Claude check %s min (CHECK_START %s, CHECK_END %s)"
        % (verdict, n, "-" if qwen_min is None else qwen_min, "-" if claude_min is None else claude_min, start, end))
    return 0 if verdict == "PASS" else 1


def main(argv=None):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:                                        # noqa: BLE001
        pass
    ap = argparse.ArgumentParser(description="Qwen task board: the one door to the local model")
    sp = ap.add_subparsers(dest="cmd", required=True)
    a1 = sp.add_parser("add")
    a1.add_argument("title")
    a1.add_argument("body")
    a1.add_argument("--from", dest="frm", default="MANAGER")
    sp.add_parser("list")
    a3 = sp.add_parser("show")
    a3.add_argument("n", type=int)
    a4 = sp.add_parser("check", help="PASS/FAIL the JSON answer block of Q<n>; stamp CHECK_START/CHECK_END; log minutes")
    a4.add_argument("n", type=int)
    a4.add_argument("--minutes", type=float, default=None, help="Claude's check minutes (overrides the stamps' clock)")
    a = ap.parse_args(argv)
    if a.cmd == "add":
        n = add_task(a.title, a.body, a.frm)
        print("Q%d filed: %s" % (n, find(n)))
    elif a.cmd == "check":
        return check_task(a.n, a.minutes)
    elif a.cmd == "list":
        for n, st, head in list_tasks():
            print("Q%-4d %-40s %s" % (n, st[:40], head))
    else:
        p = find(a.n)
        if not p:
            print("no Q%d" % a.n)
            return 1
        print(_read(p)[0])
    return 0


if __name__ == "__main__":
    sys.exit(main())
