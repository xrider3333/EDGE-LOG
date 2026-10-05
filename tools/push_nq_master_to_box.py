r"""tools/push_nq_master_to_box.py -- nightly copy of the NQ 5m RTH master to the cloud box,
for the KEEL v12 live state that tools/keel_live_state.py rebuilds THERE on a systemd timer
(edgelog-keel-state.timer, 18:30 ET Mon-Fri). The box has no NQ feed of its own; this PC
keeps augur_uploads/NOADJ_NQ_5m_RTH.csv current through the day.

What it does, and nothing else:
  0. tops the master up with the day's FULL session first (tools/refresh_noadj_yahoo.py, the
     project's own non-adjusted refresher) -- the PC's copy otherwise often stops mid-afternoon,
     the nightly build then drops that day as incomplete, and KEEL would train one session
     behind (owner 2026-09-24: pick up from the price action right before each trading day);
  1. sha256 of the local master; skip everything if the box already holds the same bytes;
  2. scp it to <remote dir>/<name>.tmp, check the remote sha256, then `mv` it into place
     (atomic on the box, so the nightly build never reads a half-written file);
  3. append one line per run to C:\EdgeLog\logs\push_nq_master.log.

ROBUST UNDER TASK SCHEDULER (2026-10-05). The scheduled run failed 09-30 ("FAIL scp: " with
nothing after it), 10-01 ("FAIL mkdir on box: ", blank again) and 10-03 ("ssh: connect to host
... Unknown error"), while the same command run by hand from a shell worked -- so the box's copy
stayed at 09-29 and KEEL v12 rebuilt on stale data for days. Now:
  - mkdir, scp and the rename each get RETRY_DELAYS_SEC retries (3 tries over ~5 minutes), so
    one network blip at 17:20 ET no longer costs the night;
  - the run stops retrying (and cuts a slow call short) before RUN_DEADLINE_SEC, under the
    task's own 30-minute limit, and ssh keep-alives end a dead link in about a minute, so the
    last line is always a FAIL with its cause;
  - a failure line always carries the return code, and stdout when stderr is blank, so a
    failure can never again log as an empty string;
  - ssh/scp are run by an explicit path (Windows' own OpenSSH first, then Git's), with stdin
    closed and no console window -- pythonw under Task Scheduler has no console and no usable
    stdin, and its PATH is not the shell's -- and every OK/FAIL line names the one that ran;
  - a failed call is tried once more AT ONCE with the other client (Git's ssh/scp when
    Windows' own failed, or the reverse), and the one that worked is used first for the rest
    of the run. The 10-03 "Unknown error" is Windows OpenSSH's wording, the hand runs that
    worked were most likely Git's ssh, and with a stripped environment Windows OpenSSH has
    been seen to exit 255 with no output at all -- so one client failing blank no longer
    fails the try, and its line is logged before the other client runs;
  - the box side checks too: tools/keel_live_state.py logs and pushes once when the newest NQ
    session it was given is older than the last completed trading day.
A failed run changes nothing on the box. KEEL keeps scoring from the last state it has and
falls back to size 1.0 on its own once that state is more than 5 sessions old
(api/cloud_signal.KEEL_MAX_STALE_SESSIONS), so a PC that is off for a night costs nothing.

Scheduled on the PC as "EdgeLog push NQ master to box" (Mon-Fri 14:20 local = 17:20 ET).
Usage: python tools/push_nq_master_to_box.py [--dry-run]
"""
import argparse
import datetime as _dt
import hashlib
import os
import shutil
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOST = "ubuntu@163.192.117.12"
KEY = os.path.expanduser(os.path.join("~", ".ssh", "edgelog_oracle"))
NAME = "NOADJ_NQ_5m_RTH.csv"
LOCAL = os.path.join(ROOT, "augur_uploads", NAME)
REMOTE_DIR = "/home/ubuntu/edgelog/nq"
LOG_PATH = os.path.join(os.environ.get("EDGELOG_HOME") or r"C:\EdgeLog", "logs", "push_nq_master.log")
# ServerAlive: a link that dies mid-upload (the PC's two default routes flap) ends in about
# a minute instead of running out the scp's whole timeout
SSH_OPTS = ["-i", KEY, "-o", "BatchMode=yes", "-o", "ConnectTimeout=20",
            "-o", "ServerAliveInterval=15", "-o", "ServerAliveCountMax=4"]
# 3 tries in all: wait 90s, then 180s (with each try's own 20s connect timeout, ~5 minutes)
RETRY_DELAYS_SEC = (90, 180)
# The scheduled task is killed at 30 minutes (its ExecutionTimeLimit). The whole run stops
# retrying, and cuts any one call short, before this many seconds, so its last log line is
# always a FAIL with the cause -- never a RETRY line cut off by Task Scheduler.
RUN_DEADLINE_SEC = 25 * 60
_sleep = time.sleep          # the one wait seam -- tests never really sleep
_clock = time.monotonic      # the one clock seam
_deadline = {"at": None}     # monotonic time the run must stop by (set by main)


def _time_left():
    """Seconds before the run's deadline, or None when no deadline is set."""
    at = _deadline.get("at")
    return None if at is None else at - _clock()


_worked = {}                 # name -> the client that last succeeded this run (tried first)


def _find_clients(name):
    """Every ssh/scp client on this machine, by explicit path, each once. Task Scheduler
    starts pythonw with its own PATH, so a bare "ssh" can resolve to a different client than
    the shell's (or none). Order: EDGELOG_SSH_DIR if set, Windows' own OpenSSH, Git's, then
    PATH. Never empty (the bare name, last resort)."""
    suffix = ".exe" if os.name == "nt" else ""
    cands = []
    override = (os.environ.get("EDGELOG_SSH_DIR") or "").strip()
    if override:
        cands.append(os.path.join(override, name + suffix))
    if os.name == "nt":
        sysroot = os.environ.get("SystemRoot") or r"C:\Windows"
        cands.append(os.path.join(sysroot, "System32", "OpenSSH", name + suffix))
        pf = os.environ.get("ProgramFiles") or r"C:\Program Files"
        cands.append(os.path.join(pf, "Git", "usr", "bin", name + suffix))
    found = [c for c in cands if os.path.isfile(c)]
    on_path = shutil.which(name)
    if on_path:
        found.append(on_path)
    out, seen = [], set()
    for c in found:
        k = os.path.normcase(os.path.abspath(c))
        if k not in seen:
            seen.add(k)
            out.append(c)
    return out or [name]


def _exes(name):
    """_find_clients(name), with the client that last worked this run moved to the front."""
    out = list(_find_clients(name))
    good = _worked.get(name)
    if good in out:
        out.remove(good)
        out.insert(0, good)
    return out


def _exe(name):
    """The ssh/scp client tried first (see _exes)."""
    return _exes(name)[0]


def _run_client(name, build, timeout):
    """Run build(exe) with the first client from _exes(name); when that exits non-zero or
    cannot start, log it and run the next client ONCE, at once. A timeout is not passed on
    (it already took its full time; _retry's next try handles it). Returns the last result,
    or raises the last client's OSError."""
    exes = _exes(name)[:2]
    for i, exe in enumerate(exes):
        last = i == len(exes) - 1
        left = _time_left()
        if left is not None:
            if left <= 1:
                raise subprocess.TimeoutExpired(cmd=name, timeout=0)
            timeout = min(timeout, max(1, int(left)))   # never run past the run's deadline
        try:
            r = _run(build(exe), timeout)
        except OSError as e:
            if last:
                raise
            _log(f"FALLBACK {name}: {exe} could not start ({type(e).__name__}: {e}); "
                 f"trying {exes[i + 1]}")
            continue
        if r.returncode == 0:
            _worked[name] = exe
            return r
        if last:
            return r
        _log(f"FALLBACK {name}: {exe} failed ({_describe(r)}); trying {exes[i + 1]}")
    return r


def _run(args, timeout):
    """subprocess.run for ssh/scp: output captured, stdin closed (pythonw has no usable
    stdin, and an ssh client reading it can fail with no message at all) and, on Windows,
    no console window."""
    kw = {"capture_output": True, "text": True, "timeout": timeout,
          "stdin": subprocess.DEVNULL}
    if os.name == "nt":
        kw["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    return subprocess.run(args, **kw)


def _describe(r):
    """One line for a failed ssh/scp: the return code, then stderr -- or stdout when stderr
    is blank -- so a failure is never logged as an empty string."""
    err = (getattr(r, "stderr", "") or "").strip()
    out = (getattr(r, "stdout", "") or "").strip()
    text = err or (f"stdout: {out}" if out else "no output")
    return f"rc={getattr(r, 'returncode', '?')}: {text[-200:]}"


def _retry(what, fn, delays=None):
    """(ok, why, tries): run fn() (returns a CompletedProcess) until it exits 0, waiting
    delays[i] between tries. A timeout or OSError counts as a failed try."""
    delays = RETRY_DELAYS_SEC if delays is None else tuple(delays)
    tries = len(delays) + 1
    why = "not run"
    for i in range(tries):
        try:
            r = fn()
            if r.returncode == 0:
                return True, None, i + 1
            why = _describe(r)
        except subprocess.TimeoutExpired as e:
            why = f"timeout after {e.timeout}s"
        except OSError as e:
            why = f"{type(e).__name__}: {e}"
        if i < tries - 1:
            left = _time_left()
            if left is not None and left < delays[i] + 30:
                # no room for another try before the task limit: stop, so the caller's FAIL
                # line (with this cause) is written while the run is still alive
                return False, f"{why}; stopped retrying, the run's time limit is near", i + 1
            _log(f"RETRY {what}: try {i + 1}/{tries} failed ({why}); next try in {delays[i]}s")
            _sleep(delays[i])
    return False, why, tries


def _log(msg):
    line = f"{_dt.datetime.now().isoformat(timespec='seconds')} {msg}"
    print(line)
    try:
        os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _refresh_master():
    """Run tools/refresh_noadj_yahoo.py in a child process (it appends Yahoo NQ=F bars after the
    master's last bar). Returns (ok, note). Never raises: a failed refresh still lets the push
    go ahead with whatever the master holds -- the box build drops an incomplete last session."""
    tool = os.path.join(ROOT, "tools", "refresh_noadj_yahoo.py")
    try:
        r = subprocess.run([sys.executable, tool], capture_output=True, text=True, timeout=600,
                           cwd=ROOT)
    except (OSError, subprocess.TimeoutExpired) as e:
        return False, f"{type(e).__name__}: {e}"
    lines = [ln.strip() for ln in (r.stdout or "").splitlines() if NAME in ln]
    note = "; ".join(lines) or (r.stderr or "").strip()[-200:] or "no output"
    return r.returncode == 0, note[:300]


def _ssh(cmd, timeout=120):
    return _run_client("ssh", lambda exe: [exe, *SSH_OPTS, HOST, cmd], timeout)


def _scp(local, remote, timeout=900):
    return _run_client("scp", lambda exe: [exe, *SSH_OPTS, "-q", local, f"{HOST}:{remote}"],
                       timeout)


def _via():
    """Which clients a log line is about: the ones that worked this run, else the first."""
    return f"[ssh {_worked.get('ssh') or _exe('ssh')}, scp {_worked.get('scp') or _exe('scp')}]"


def _remote_sha_retried(path):
    """(sha, why, tries): the box's sha256 of `path`, read with _retry. sha is "" when it
    could not be read; `why` then says why (the last try's cause), else None."""
    cmd = f"sha256sum {path} 2>/dev/null | cut -d' ' -f1"
    holder = {}

    def once():
        holder["r"] = _ssh(cmd)
        return holder["r"]
    ok, why, n = _retry(f"checksum of {path}", once)
    if not ok:
        return "", why, n
    sha = (holder["r"].stdout or "").strip()
    return sha, (None if sha else "the box returned no checksum (file missing?)"), n


def _remote_sha(path, retry=False):
    if retry:
        return _remote_sha_retried(path)[0]
    cmd = f"sha256sum {path} 2>/dev/null | cut -d' ' -f1"
    try:
        r = _ssh(cmd)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return (r.stdout or "").strip() if r.returncode == 0 else ""


def main(argv=None):
    try:
        return _main(argv)
    finally:
        _deadline["at"] = None    # the deadline belongs to one run only


def _main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true", help="report what would happen, change nothing")
    ap.add_argument("--local", default=LOCAL, help="the master to push (default: this checkout's augur_uploads copy)")
    ap.add_argument("--no-refresh", action="store_true", help="push the master as it is, without topping it up first")
    args = ap.parse_args(argv)
    _deadline["at"] = _clock() + RUN_DEADLINE_SEC
    local = args.local
    if not (args.no_refresh or args.dry_run):
        ok, note = _refresh_master()
        _log(("REFRESH ok: " if ok else "REFRESH FAILED (pushing the master as it is): ") + note)
    if not os.path.exists(local):
        _log(f"FAIL local master missing: {local}")
        return 2
    local_sha = _sha256(local)
    size_mb = os.path.getsize(local) / 1e6
    final = f"{REMOTE_DIR}/{NAME}"
    _worked.clear()
    try:
        if _remote_sha(final) == local_sha:
            _log(f"SKIP box already has this master ({size_mb:.1f} MB, sha {local_sha[:12]})")
            return 0
        if args.dry_run:
            _log(f"DRY-RUN would push {size_mb:.1f} MB (sha {local_sha[:12]}) to {HOST}:{final}")
            return 0
        ok, why, n = _retry("mkdir on box", lambda: _ssh(f"mkdir -p {REMOTE_DIR}"))
        if not ok:
            _log(f"FAIL mkdir on box after {n} tries: {why} {_via()}")
            return 1
        tmp = f"{final}.tmp"
        ok, why, n = _retry("scp", lambda: _scp(local, tmp))
        if not ok:
            _log(f"FAIL scp after {n} tries: {why} {_via()}")
            return 1
        tmp_sha, sha_why, sha_n = _remote_sha_retried(tmp)
        if tmp_sha != local_sha:
            try:
                removed = _ssh(f"rm -f {tmp}").returncode == 0
            except (OSError, subprocess.TimeoutExpired):
                removed = False
            gone = ("temp file removed" if removed
                    else f"temp file may still be there ({tmp})")
            if tmp_sha:
                _log(f"FAIL checksum mismatch after upload; {gone}, box copy unchanged {_via()}")
            else:
                _log(f"FAIL could not read the uploaded file's checksum after {sha_n} tries: "
                     f"{sha_why}; {gone}, box copy unchanged {_via()}")
            return 1
        ok, why, n = _retry("rename on box", lambda: _ssh(f"mv -f {tmp} {final}"))
        if not ok:
            # a rename that landed but whose reply was lost fails every later try (the temp
            # file is gone) -- the file in place is what counts
            if _remote_sha(final, retry=True) == local_sha:
                _log(f"OK pushed {size_mb:.1f} MB (sha {local_sha[:12]}) to {HOST}:{final} "
                     f"(the rename reported {why}, but the box holds the new file) {_via()}")
                return 0
            _log(f"FAIL rename on box after {n} tries: {why} {_via()}")
            return 1
        _log(f"OK pushed {size_mb:.1f} MB (sha {local_sha[:12]}) to {HOST}:{final} {_via()}")
        return 0
    except subprocess.TimeoutExpired as e:
        _log(f"FAIL timeout: {e}")
        return 1
    except OSError as e:
        _log(f"FAIL {type(e).__name__}: {e} {_via()}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
