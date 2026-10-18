"""tools/pull_box_ledgers.py -- nightly copy of the Webull book's ledgers from the Oracle box
to the PC (WEBULL_GO_LIVE.md 2.9 / 3.9: the book's positions, today's P&L and order memory
existed only on one VM, and broker_orders.csv trims itself to its last 100 rows).

Copies, read-only on the box, into a dated PRIVATE folder on the PC (never the repo: the
webull_orders config and state carry account ids):

    C:\\EdgeLog\\box_backup\\<YYYY-MM-DD_HHMM>\\{qqq_exec,webull_orders,cloud_signal}\\...

Only ledgers and state, not the KEEL model (rebuilt on the box nightly) or lock files.
Keeps the newest KEEP_DAYS folders. Appends lines to C:\\EdgeLog\\logs\\pull_box_ledgers.log:
a START line, a TRY line per failed attempt, and ALWAYS one OK/FAIL result line (the PC monitor,
tools/webull_freshness_pc.py, reads only OK/FAIL). Exit 0 on success, 1 on any failure (so the
scheduled task shows red). Never writes on the box, never touches Webull.

ONE SSH CONNECTION (2026-10-16, after the 10-15 14:45 MST run died silently): the old loop ran
one scp per file (19 connections). Under Task Scheduler one of them stalled past its 120 s
timeout, the uncaught TimeoutExpired killed the run before it could log, and the monitor only
saw the backup go stale 36 h later (10-14 14:45 too: c3d3d373 then caught the timeout and
retried each failed scp once; this replaces that per-file loop, whose connections still stall). Now the box tars the files that exist (read-only, to
stdout) over a single ssh call; the PC keeps only the listed files from the stream. Each try
is bounded (TRY_TIMEOUT_SEC) with keep-alives, stdin closed and no console window (the
tools/push_nq_master_to_box.py lessons); a failed try goes at once to the other ssh client
(Windows' own OpenSSH, then Git's), then once more after RETRY_DELAY_SEC -- worst case well
under the task's 15-minute limit. Any crash is logged as FAIL, never silent.

WHOLE COPIES ONLY (review 2026-10-18): a file tar could not read, or one that SHRANK while read
(tar zero-pads it), is never saved -- the try is repeated, and if every try had it the other
files are still kept and the night is FAIL naming it. A file whose folder cannot be read on
the box is UNREADABLE (FAIL), not 'missing'. Files land in <run>.partial first and move into
the dated folder only once the whole stream checked out, so a failure never deletes a
same-minute earlier copy.

Usage:  python tools/pull_box_ledgers.py [--dest C:\\EdgeLog\\box_backup] [--dry-run]
"""
import argparse
import datetime as _dt
import io
import os
import shlex
import shutil
import subprocess
import sys
import tarfile
import time

HOST = "ubuntu@163.192.117.12"
SSH_KEY = os.path.expanduser("~/.ssh/edgelog_oracle")
SSH_OPTS = ["-i", SSH_KEY, "-o", "ConnectTimeout=20", "-o", "BatchMode=yes",
            "-o", "ServerAliveInterval=15", "-o", "ServerAliveCountMax=4"]
REMOTE_HOME = "/home/ubuntu/edgelog"
FILES = [
    "qqq_exec/trades.csv", "qqq_exec/orders.csv", "qqq_exec/broker_orders.csv",
    "qqq_exec/reprice.csv", "qqq_exec/state.json", "qqq_exec/config.json",
    "qqq_exec/corrections.log",
    "webull_orders/state.json", "webull_orders/config.json",
    "cloud_signal/signals.csv", "cloud_signal/state.json", "cloud_signal/corrections.log",
    "cloud_signal/keel/NOISE_382_v12_summary.json",
    # SHADOW LEGS (owner 2026-09-28; api/cloud_signal.py shadow_paths): the would-be trades of
    # NOISE #422 plain / fixed tilts / KEEL and ENGU-Q, their state and heartbeat, and the
    # NOISE_422_KEEL leg's own KEEL summary -- read by tools/shadow_legs_report.py. A file
    # not there yet (before the first shadow tick / first KEEL build) is listed as missing.
    "cloud_signal/shadow/signals.csv", "cloud_signal/shadow/state.json",
    "cloud_signal/shadow/heartbeat.json",
    # the NOISE forward log (api/noise_forward.py) -- tools/noise_forward_log.py --home reads it
    "cloud_signal/shadow/noise_forward_log.csv",
    "cloud_signal/keel/NOISE_422_KEEL_v12_summary.json",
    # DIP #424's learned KEEL leg (shadow, 2026-10-09) -- its trades are in the shadow ledger
    "cloud_signal/keel/DIP_424K_v12_summary.json",
]
DEFAULT_DEST = r"C:\EdgeLog\box_backup"
LOG_PATH = r"C:\EdgeLog\logs\pull_box_ledgers.log"
KEEP_DAYS = 60
TRY_TIMEOUT_SEC = 180        # one ssh + tar of ~19 small ledgers takes seconds when the link is up
RETRY_DELAY_SEC = 30         # before the last try (the first two go back to back, one per client)
MISSING_TAG = "MISSING "     # the box's stderr line for a listed file that is not there
UNREADABLE_TAG = "UNREADABLE "   # ... for one that may be there but cannot be read (not a FAIL-free miss)
# tar's exit codes: 0 clean; 1 = a file CHANGED while it was read (an appended ledger keeps a clean
# prefix -- fine -- but a file that SHRANK is zero-padded to its old size: that copy is corrupt);
# 2 = fatal for some file(s) (cannot open / stat) while every other file still streams. tar names
# each problem file on stderr as "tar: <name>: <why>" -- see _tar_problems.
TAR_CLEAN_RCS = (0, 1)
TAR_PARTIAL_RC = 2
TAR_BAD_WORDS = ("File shrank", "Cannot ", "Read error", "Unexpected EOF")
TAR_CHANGED_WORDS = ("file changed as we read it",)
STAGE_SUFFIX = ".partial"    # unpack lands here first; never matches the readers' 20??-??-??_???? glob


def _log(line):
    stamp = _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        print(line)
    except Exception:                 # pythonw under Task Scheduler has no usable stdout
        pass
    try:
        os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(f"{stamp} {line}\n")
    except OSError:
        pass


def _prune(dest, keep):
    runs = sorted(d for d in os.listdir(dest)
                  if os.path.isdir(os.path.join(dest, d)) and not d.endswith(STAGE_SUFFIX))
    for old in runs[:-keep] if len(runs) > keep else []:
        shutil.rmtree(os.path.join(dest, old), ignore_errors=True)


def _find_clients():
    """Every ssh client on this machine by explicit path, each once: Windows' own OpenSSH, then
    Git's, then whatever PATH finds (Task Scheduler's PATH is not the shell's). Never empty."""
    suffix = ".exe" if os.name == "nt" else ""
    cands = []
    if os.name == "nt":
        sysroot = os.environ.get("SystemRoot") or r"C:\Windows"
        cands.append(os.path.join(sysroot, "System32", "OpenSSH", "ssh" + suffix))
        pf = os.environ.get("ProgramFiles") or r"C:\Program Files"
        cands.append(os.path.join(pf, "Git", "usr", "bin", "ssh" + suffix))
    found = [c for c in cands if os.path.isfile(c)]
    on_path = shutil.which("ssh")
    if on_path:
        found.append(on_path)
    out, seen = [], set()
    for c in found:
        k = os.path.normcase(os.path.abspath(c))
        if k not in seen:
            seen.add(k)
            out.append(c)
    return out or ["ssh"]


def remote_command(files=None, home=None):
    """The shell line the box runs, read-only: each listed file that is a readable regular file
    (a link to one is followed, as scp did) goes on the list tar reads from stdin; one that is
    plainly absent (its folder is there and readable) is named on stderr as MISSING; anything
    else (a folder that cannot be searched, a file that cannot be read, not a regular file) as
    UNREADABLE. tar then streams the listed files to stdout (-h: follow links)."""
    files = FILES if files is None else files
    home = REMOTE_HOME if home is None else home
    quoted = " ".join(shlex.quote(f) for f in files)
    return (f"cd {shlex.quote(home)} || exit 3; "
            f"for f in {quoted}; do d=$(dirname \"$f\"); "
            f"if [ -f \"$f\" ] && [ -r \"$f\" ]; then printf '%s\\n' \"$f\"; "
            f"elif [ ! -e \"$f\" ] && [ ! -L \"$f\" ] && [ -d \"$d\" ] && [ -x \"$d\" ] "
            f"&& [ -r \"$d\" ]; then printf '{MISSING_TAG}%s\\n' \"$f\" >&2; "
            f"elif [ ! -e \"$d\" ]; then printf '{MISSING_TAG}%s\\n' \"$f\" >&2; "
            f"else printf '{UNREADABLE_TAG}%s\\n' \"$f\" >&2; fi; "
            f"done | tar -chf - -T -")


def _run(args, timeout):
    """subprocess.run for ssh: bytes captured, stdin closed (an ssh client reading a scheduled
    task's stdin can hang or fail blank) and, on Windows, no console window."""
    kw = {"capture_output": True, "timeout": timeout, "stdin": subprocess.DEVNULL}
    if os.name == "nt":
        kw["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    return subprocess.run(args, **kw)


def _attempts(clients):
    """(client, delay before it) for each try: every client once at once (the first two),
    then the first client again after RETRY_DELAY_SEC. Three tries at most."""
    plan = [(c, 0) for c in clients[:2]]
    plan.append((clients[0], RETRY_DELAY_SEC))
    return plan


def _client_label(client):
    low = client.replace("\\", "/").lower()
    kind = ("Windows OpenSSH" if "/openssh/" in low else
            "Git ssh" if "/git/" in low else "ssh")
    return f"{kind} ({client})"


def _tagged(stderr, tag):
    return [ln[len(tag):].strip() for ln in (stderr or "").splitlines() if ln.startswith(tag)]


def _tar_problems(stderr, files=None):
    """({name: why} for listed files tar could not copy whole -- it could not read them, or they
    shrank and were zero-padded -- and [names that only grew while read], from tar's stderr)."""
    want = set(FILES if files is None else files)
    bad, changed = {}, []
    for ln in (stderr or "").splitlines():
        if not ln.startswith("tar: "):
            continue
        parts = ln[len("tar: "):].split(": ", 1)
        if len(parts) != 2 or parts[0] not in want:
            continue
        name, why = parts
        if any(w in why for w in TAR_BAD_WORDS):
            bad[name] = why.strip()[:80]
        elif any(w in why for w in TAR_CHANGED_WORDS) and name not in changed:
            changed.append(name)
    return bad, changed


def _describe(rc, stderr):
    err = " | ".join(ln for ln in (stderr or "").splitlines()
                     if ln.strip() and not ln.startswith((MISSING_TAG, UNREADABLE_TAG)))
    return f"rc={rc}: {err[-200:] or 'no output'}"


def fetch_stream(log=None, sleep=None):
    """The first CLEAN try's result -- a dict: tag, stream (tar bytes), missing, unreadable, bad
    ({name: why} tar could not copy whole), changed (grew while read). A try whose stream has bad
    files is kept and the next try runs (a file mid-rewrite is whole a moment later); when every
    try had them, the last such stream is returned (its good files are still worth keeping, and
    the bad ones fail the night). Raises RuntimeError naming every try when no try produced a
    stream at all. Never hangs past the tries' timeouts."""
    log = log or _log
    sleep = sleep or time.sleep
    whys, fallback = [], None
    for i, (client, delay) in enumerate(_attempts(_find_clients()), start=1):
        if delay:
            sleep(delay)
        tag = _client_label(client)
        try:
            r = _run([client, *SSH_OPTS, HOST, remote_command()], TRY_TIMEOUT_SEC)
        except subprocess.TimeoutExpired:
            why = f"timed out after {TRY_TIMEOUT_SEC} s"
        except OSError as e:
            why = f"could not start: {type(e).__name__}: {e}"
        else:
            stderr = (r.stderr or b"").decode("utf-8", "replace")
            if r.returncode in TAR_CLEAN_RCS + (TAR_PARTIAL_RC,) and r.stdout:
                bad, changed = _tar_problems(stderr)
                got = {"tag": tag, "stream": r.stdout, "missing": _tagged(stderr, MISSING_TAG),
                       "unreadable": _tagged(stderr, UNREADABLE_TAG), "bad": bad,
                       "changed": changed}
                if not bad and r.returncode in TAR_CLEAN_RCS:
                    return got
                fallback = got
                why = _describe(r.returncode, stderr)
                if not bad:            # a fatal tar error naming no listed file: nothing to keep
                    fallback = None
            else:
                why = _describe(r.returncode, stderr)
        whys.append(f"try {i} {tag}: {why}")
        log(f"TRY {i} failed via {tag}: {why}")
    if fallback is not None:
        return fallback
    raise RuntimeError("; ".join(whys) or "no ssh client")


def unpack(stream, run_dir, files=None, skip=()):
    """Write each LISTED regular file of the tar stream under run_dir (names in `skip` -- copies
    tar flagged as not whole -- are never written); anything else in the stream (a name not in
    the list, a link, an absolute or ../ path) is ignored. The whole stream is read and checked
    BEFORE anything is written. Returns the set of names written."""
    want = set(FILES if files is None else files) - set(skip)
    got = {}
    with tarfile.open(fileobj=io.BytesIO(stream), mode="r:") as tf:
        for m in tf:
            if not m.isfile() or m.name not in want:
                continue
            fh = tf.extractfile(m)
            data = fh.read() if fh is not None else b""
            if len(data) != m.size:
                raise ValueError(f"{m.name}: {len(data)} of {m.size} bytes in the stream")
            got[m.name] = data
    for rel, data in got.items():
        local = os.path.join(run_dir, *rel.split("/"))
        os.makedirs(os.path.dirname(local), exist_ok=True)
        with open(local, "wb") as f:
            f.write(data)
    return set(got)


def _land(stage, run_dir):
    """Move every staged file into run_dir (a same-minute earlier run's folder keeps its other
    files; a file both have is replaced by this newer copy)."""
    for root, _dirs, names in os.walk(stage):
        for n in names:
            src = os.path.join(root, n)
            dst = os.path.join(run_dir, os.path.relpath(src, stage))
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            os.replace(src, dst)


def _pull(args):
    run_dir = os.path.join(args.dest, _dt.datetime.now().strftime("%Y-%m-%d_%H%M"))
    if args.dry_run:
        _log(f"DRY-RUN would copy {len(FILES)} file(s) from {HOST} into {run_dir}")
        return 0
    _log(f"START pulling {len(FILES)} file(s) from {HOST} over one ssh connection")
    try:
        got = fetch_stream()
    except RuntimeError as e:
        _log(f"FAIL copied 0/{len(FILES)} into {run_dir}; {e}")
        return 1
    stage = run_dir + STAGE_SUFFIX
    shutil.rmtree(stage, ignore_errors=True)
    try:
        written = unpack(got["stream"], stage, skip=got["bad"])
        _land(stage, run_dir)
    except Exception as e:
        _log(f"FAIL copied 0/{len(FILES)} into {run_dir}; the tar stream from {got['tag']} could "
             f"not be read or saved: {type(e).__name__}: {e}")
        return 1
    finally:
        shutil.rmtree(stage, ignore_errors=True)   # only this run's own staging, never run_dir
    absent = set(got["missing"])
    missing = [f for f in FILES if f in absent and f not in written]
    failed = [f for f in FILES if f not in written and f not in missing]
    why = dict(got["bad"])
    why.update({f: "unreadable on the box" for f in got["unreadable"] if f in failed})
    try:
        _prune(args.dest, KEEP_DAYS)
    except OSError:
        pass
    status = "OK" if not failed and written else "FAIL"
    changed = [f for f in got["changed"] if f in written]
    _log(f"{status} copied {len(written)}/{len(FILES)} into {run_dir} via {got['tag']}"
         + (f"; missing on box: {', '.join(missing)}" if missing else "")
         + (f"; FAILED: {', '.join(f + (' (' + why[f] + ')' if f in why else '') for f in failed)}"
            if failed else "")
         + (f"; grew while read (kept): {', '.join(changed)}" if changed else ""))
    return 0 if status == "OK" else 1


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dest", default=DEFAULT_DEST)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    try:
        return _pull(args)
    except Exception as e:            # never die silently: the monitor only sees OK/FAIL lines
        _log(f"FAIL crashed: {type(e).__name__}: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
