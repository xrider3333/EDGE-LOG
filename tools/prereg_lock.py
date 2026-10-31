"""tools/prereg_lock.py - lock a preregistration BEFORE the run; no verdict without it (board C8).

  python tools/prereg_lock.py lock <file> [--amend "<reason>"]
  python tools/prereg_lock.py check <id-or-file>     -> LOCKED / CHANGED since lock / NOT LOCKED
  python tools/prereg_lock.py list

A lock is one append-only JSON line in <EDGELOG_HOME>/prereg_locks.jsonl:
  {id (file stem), version, path, sha256, locked_at (UTC ISO), git_head, reason}
The hash is over the file's text with line endings normalised to LF, so a CRLF checkout of the same
prereg is the same prereg. Nothing is ever rewritten or deleted: re-locking a CHANGED file under the
same id is refused unless --amend gives a reason, which appends version N+1 and keeps the old line.

verdict_gate() is what tools/run_record.py calls before it stores a verdict.
"""
import argparse
import datetime
import hashlib
import json
import os
import subprocess
import sys

EXPLORATORY_TOKEN = "none - exploratory"
EXPLORATORY = "EXPLORATORY"
LOCK_FILE = "prereg_locks.jsonl"


class PreregError(Exception):
    """A lock or a verdict refused; the message is the one line the caller prints."""


def locks_path():
    home = os.environ.get("EDGELOG_HOME") or (r"C:\EdgeLog" if os.name == "nt" else "/var/lib/edgelog")
    return os.path.join(home, LOCK_FILE)


def file_sha256(path):
    with open(path, "rb") as f:
        raw = f.read()
    return hashlib.sha256(raw.replace(b"\r\n", b"\n")).hexdigest()


def prereg_id(path_or_id):
    return os.path.splitext(os.path.basename(str(path_or_id).strip()))[0]


def _git_head(path):
    try:
        out = subprocess.run(["git", "rev-parse", "HEAD"], cwd=os.path.dirname(os.path.abspath(path)) or ".",
                             capture_output=True, text=True, timeout=10)
        return (out.stdout.strip() or None) if out.returncode == 0 else None
    except Exception:  # noqa: BLE001 - a file outside a repo simply has no head
        return None


def read_locks(path=None):
    path = path or locks_path()
    out = []
    if not os.path.exists(path):
        return out
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    out.append(json.loads(line))
                except ValueError:
                    continue          # a torn line never blocks reading the rest
    return out


def latest(pid, locks=None):
    rows = [r for r in (read_locks() if locks is None else locks) if r.get("id") == pid]
    return rows[-1] if rows else None


def _utcnow():
    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0)


def lock(path, amend=None, now=None):
    """Append a lock for `path`. Returns (entry, message). Raises PreregError on a refused re-lock."""
    if not os.path.isfile(path):
        raise PreregError("prereg file not found: %s" % path)
    pid, sha = prereg_id(path), file_sha256(path)
    prev = latest(pid)
    if prev is not None and prev.get("sha256") == sha:
        return prev, "already LOCKED %s v%s at %s (sha256 %s)" % (pid, prev.get("version", 1),
                                                                   prev.get("locked_at"), sha[:12])
    if prev is not None and not (amend and str(amend).strip()):
        raise PreregError("refused: %s was locked at %s with sha256 %s and the file has CHANGED (now %s). "
                          "Pass --amend \"<reason>\" to record a new version; the old lock is kept."
                          % (pid, prev.get("locked_at"), prev.get("sha256"), sha))
    entry = {"id": pid, "version": (int(prev.get("version", 1)) + 1) if prev else 1,
             "path": os.path.abspath(path), "sha256": sha,
             "locked_at": (now or _utcnow()).isoformat(), "git_head": _git_head(path),
             "reason": str(amend).strip() if (prev is not None and amend) else None}
    lp = locks_path()
    os.makedirs(os.path.dirname(lp) or ".", exist_ok=True)
    with open(lp, "a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(entry) + "\n")
        f.flush()
        os.fsync(f.fileno())
    return entry, "LOCKED %s v%d (sha256 %s)" % (pid, entry["version"], sha[:12])


def check(id_or_file):
    """(status, entry, detail) with status LOCKED / CHANGED / NOT LOCKED / MISSING FILE."""
    pid = prereg_id(id_or_file)
    entry = latest(pid)
    if entry is None:
        return "NOT LOCKED", None, "%s has no lock" % pid
    path = id_or_file if os.path.isfile(str(id_or_file)) else entry.get("path")
    if not path or not os.path.isfile(path):
        return "MISSING FILE", entry, "%s is locked but its file %s is gone" % (pid, path)
    now = file_sha256(path)
    if now != entry.get("sha256"):
        return "CHANGED", entry, "%s CHANGED since lock at %s (locked %s, now %s)" % (
            pid, entry.get("locked_at"), entry.get("sha256", "")[:12], now[:12])
    return "LOCKED", entry, "%s LOCKED v%s at %s" % (pid, entry.get("version", 1), entry.get("locked_at"))


def _as_utc(t):
    """A datetime (naive = local time, the run records' own convention) or an ISO / 'YYYY-MM-DD HH:MM' string."""
    if isinstance(t, str):
        s = t.strip().replace("Z", "+00:00")
        t = datetime.datetime.fromisoformat(s)
    if t.tzinfo is None:
        t = t.astimezone()            # naive = this box's local clock
    return t.astimezone(datetime.timezone.utc)


def verdict_gate(verdict, prereg, run_start):
    """The verdict to store, or PreregError. No verdict -> None, nothing checked.

    prereg == "none - exploratory" stores EXPLORATORY (never PASS / crown). Otherwise prereg must name a
    locked id, locked BEFORE run_start, whose file still hashes to the lock."""
    if verdict is None or not str(verdict).strip():
        return None
    v = str(verdict).strip()
    p = (prereg or "").strip()
    if p.lower() == EXPLORATORY_TOKEN:
        return EXPLORATORY
    if not p:
        raise PreregError('verdict %r refused: no prereg - name a locked prereg id (tools/prereg_lock.py lock '
                          '<file>) or pass prereg "%s"' % (v, EXPLORATORY_TOKEN))
    status, entry, detail = check(p)
    if status != "LOCKED":
        raise PreregError("verdict %r refused: prereg %s" % (v, detail))
    # the FIRST lock of this id that has the current hash is when this text was fixed
    first = next(r for r in read_locks() if r.get("id") == entry["id"] and r.get("sha256") == entry["sha256"])
    if _as_utc(first["locked_at"]) >= _as_utc(run_start):
        raise PreregError("verdict %r refused: prereg %s was locked at %s, NOT before the run started (%s)"
                          % (v, entry["id"], first["locked_at"], run_start))
    return v


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    lp = sub.add_parser("lock")
    lp.add_argument("file", nargs="+")
    lp.add_argument("--amend", help="reason for recording a new version of a changed prereg")
    cp = sub.add_parser("check")
    cp.add_argument("target")
    sub.add_parser("list")
    a = ap.parse_args(argv)
    if a.cmd == "lock":
        rc = 0
        for f in a.file:
            try:
                print(lock(f, amend=a.amend)[1])
            except PreregError as e:
                print(str(e), file=sys.stderr)
                rc = 2
        return rc
    if a.cmd == "check":
        status, _, detail = check(a.target)
        print(detail)
        return 0 if status == "LOCKED" else 1
    for r in read_locks():
        print("%-48s v%-2s %s %s %s" % (r.get("id"), r.get("version", 1), r.get("locked_at"),
                                       (r.get("sha256") or "")[:12], r.get("reason") or ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
