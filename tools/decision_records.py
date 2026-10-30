"""C17 - decision records written automatically when a decision closes.

Reads the open board (C:/EdgeLog/manager/open_board/board.md). Every row whose status is CLOSED - done, pass, fail or
confirmed - gets one record file docs/decisions/<item|test>-<N>.md: title, status, who, date, what, statusText, plus a
history line each time its closed status or text changes. Open rows (open / run / wait / queued / park / block / needs-you)
get no record. A record is only ever added to or appended to, never deleted, so the owner's decision trail survives
board edits.
Usage:
  python tools/decision_records.py                 write into this checkout's docs/decisions (dry: --dry)
  python tools/decision_records.py --auto          daily task: fresh worktree 'decisions-bot', write, commit, wt.py ship --fast
  python tools/decision_records.py --install       windowless daily scheduled task (pythonw, 18:30)"""
import argparse
import datetime as dt
import os
import re
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BOARD = "C:/EdgeLog/manager/open_board/board.md"
CLOSED = {"done", "pass", "fail", "confirmed"}
ROW = re.compile(r"^- \*\*(item|test) (\d+)\*\* \[([a-z/ -]+)\] (.*)$")
NOWIN = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def parse(text):
    rows, cur = [], None
    for ln in text.splitlines():
        m = ROW.match(ln)
        if m:
            kind, n, st, rest = m.groups()
            parts = [p.strip() for p in rest.split(" | ")]
            f = {"kind": kind, "n": int(n), "status": st.strip(), "title": parts[0], "who": "", "date": "", "what": "", "statusText": ""}
            for p in parts[1:]:
                k, _, v = p.partition(":")
                if k.strip() in ("who", "date"):
                    f[k.strip()] = v.strip()
            rows.append(f)
            cur = f
        elif cur is not None and ln.startswith("  - "):
            k, _, v = ln[4:].partition(":")
            if k.strip() in ("what", "statusText"):
                cur[k.strip()] = v.strip()
        elif ln.startswith("## "):
            cur = None
    return rows


def body(r):
    return ("# %s %d - %s\n\n- **status:** %s\n- **who:** %s\n- **date:** %s\n- **status text:** %s\n\n## What was decided / done\n%s\n"
            % (r["kind"], r["n"], r["title"], r["status"], r["who"], r["date"], r["statusText"], r["what"] or "(no text on the board)"))


def write(repo, dry=False):
    out = os.path.join(repo, "docs", "decisions")
    os.makedirs(out, exist_ok=True)
    rows = [r for r in parse(open(BOARD, encoding="utf-8").read()) if r["status"] in CLOSED]
    today, changed = dt.date.today().isoformat(), []
    for r in rows:
        p = os.path.join(out, "%s-%d.md" % (r["kind"], r["n"]))
        new = body(r)
        if os.path.exists(p):
            old = open(p, encoding="utf-8").read()
            head, sep, hist = old.partition("\n## History\n")
            if head + "\n" == new or head == new.rstrip("\n"):
                continue
            text = new + "\n## History\n" + (hist if sep else "") + "- %s: board changed to [%s] %s\n" % (today, r["status"], r["statusText"])
        else:
            text = new + "\n## History\n- %s: recorded from the board as [%s] (row date %s)\n" % (today, r["status"], r["date"] or "?")
        changed.append(p)
        if not dry:
            open(p, "w", encoding="utf-8", newline="\n").write(text)
    print("decision records: %d closed rows on the board, %d written or updated%s" % (len(rows), len(changed), " (dry)" if dry else ""))
    return changed


def sh(cmd, cwd):
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, creationflags=NOWIN)
    return r.returncode, r.stdout + r.stderr


def auto():
    py = sys.executable.replace("pythonw", "python")
    code, out = sh([py, "tools/wt.py", "new", "decisions-bot"], REPO)
    wt = out.strip().splitlines()[-1].strip() if out.strip() else ""
    if code or not os.path.isdir(wt):
        raise SystemExit("worktree failed: " + out[-300:])
    sh(["git", "fetch", "-q", "origin"], wt)
    sh(["git", "reset", "-q", "--hard", "origin/main"], wt)
    if not write(wt):
        return
    sh(["git", "add", "docs/decisions"], wt)
    sh(["git", "commit", "-q", "-m", "C17: decision records from the open board (auto, %s)\n\nCo-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" % dt.date.today()], wt)
    code, out = sh([py, "-u", "tools/wt.py", "ship", "decisions-bot", "--fast"], REPO)
    log = "C:/EdgeLog/manager/decisions_auto.log"
    open(log, "a", encoding="utf-8").write("%s\n%s\n" % (dt.datetime.now().isoformat(timespec="seconds"), out[-1500:]))


def install():
    pyw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    tr = '"%s" "%s" --auto' % (pyw, os.path.abspath(__file__))
    print(subprocess.run(["schtasks", "/Create", "/F", "/SC", "DAILY", "/ST", "18:30", "/TN", "EdgeLog C17 decision records", "/TR", tr],
                         capture_output=True, text=True).stdout)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--auto", action="store_true")
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--install", action="store_true")
    a = ap.parse_args()
    install() if a.install else (auto() if a.auto else write(REPO, a.dry))
