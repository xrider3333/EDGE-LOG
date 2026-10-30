"""QWEN TASK = THE ONE DOOR (MANAGER #222, owner GO 10-30). Chats and tools never call the local model directly; they
file a numbered task here and tools/qwen_runner.py (the one worker) runs it on whatever model is loaded.

  python tools/qwen_task.py add '<title>' '<body>' [--from LANE]   -> writes Q<next>-<slug>.md + a STATUS.md row
  python tools/qwen_task.py list                                    -> number, status line, title
  python tools/qwen_task.py show N                                  -> the whole task file

  from qwen_task import add_task; n = add_task(title, body, frm="MANAGER")

Folder: C:\\EdgeLog\\manager\\qwen_tasks (override QWEN_TASKS_DIR). Q<next> = max existing Q number + 1, taken under a
lock file (.qwen_task.lock, O_EXCL; a lock older than 60 s is stale) so two chats never get the same number.
Task file: line 1 "STATUS: ⭕ open", then "# Q<n> - <title>", "From: <LANE> · Date: YYYY-MM-DD", blank, body. New
files copy the line endings of the newest existing Q file. STATUS.md is read and written as UTF-8 bytes (BOM and
line endings kept, never cp1252); the new row is "| Q<n> | <title> | ⭕ | YYYY-MM-DD filed by <LANE> |".
"""
import argparse
import datetime
import glob
import os
import re
import sys
import time

OPEN = "⭕"
LOCK_NAME = ".qwen_task.lock"
LOCK_STALE_S = 60
LOCK_WAIT_S = 30


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
        text = ("STATUS: %s open\n# Q%d - %s\nFrom: %s · Date: %s\n\n%s\n"
                % (OPEN, n, title, frm, d, str(body).replace("\r\n", "\n").rstrip()))
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
    a = ap.parse_args(argv)
    if a.cmd == "add":
        n = add_task(a.title, a.body, a.frm)
        print("Q%d filed: %s" % (n, find(n)))
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
