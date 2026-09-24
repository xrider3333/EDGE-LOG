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
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOST = "ubuntu@163.192.117.12"
KEY = os.path.expanduser(os.path.join("~", ".ssh", "edgelog_oracle"))
NAME = "NOADJ_NQ_5m_RTH.csv"
LOCAL = os.path.join(ROOT, "augur_uploads", NAME)
REMOTE_DIR = "/home/ubuntu/edgelog/nq"
LOG_PATH = os.path.join(os.environ.get("EDGELOG_HOME") or r"C:\EdgeLog", "logs", "push_nq_master.log")
SSH_OPTS = ["-i", KEY, "-o", "BatchMode=yes", "-o", "ConnectTimeout=20"]


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
    return subprocess.run(["ssh", *SSH_OPTS, HOST, cmd], capture_output=True, text=True,
                          timeout=timeout)


def _remote_sha(path):
    r = _ssh(f"sha256sum {path} 2>/dev/null | cut -d' ' -f1")
    return (r.stdout or "").strip() if r.returncode == 0 else ""


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true", help="report what would happen, change nothing")
    ap.add_argument("--local", default=LOCAL, help="the master to push (default: this checkout's augur_uploads copy)")
    ap.add_argument("--no-refresh", action="store_true", help="push the master as it is, without topping it up first")
    args = ap.parse_args(argv)
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
    try:
        if _remote_sha(final) == local_sha:
            _log(f"SKIP box already has this master ({size_mb:.1f} MB, sha {local_sha[:12]})")
            return 0
        if args.dry_run:
            _log(f"DRY-RUN would push {size_mb:.1f} MB (sha {local_sha[:12]}) to {HOST}:{final}")
            return 0
        r = _ssh(f"mkdir -p {REMOTE_DIR}")
        if r.returncode != 0:
            _log(f"FAIL mkdir on box: {(r.stderr or '').strip()[:200]}")
            return 1
        tmp = f"{final}.tmp"
        r = subprocess.run(["scp", *SSH_OPTS, "-q", local, f"{HOST}:{tmp}"], capture_output=True,
                           text=True, timeout=900)
        if r.returncode != 0:
            _log(f"FAIL scp: {(r.stderr or '').strip()[:200]}")
            return 1
        if _remote_sha(tmp) != local_sha:
            _ssh(f"rm -f {tmp}")
            _log("FAIL checksum mismatch after upload; temp file removed, box copy unchanged")
            return 1
        r = _ssh(f"mv -f {tmp} {final}")
        if r.returncode != 0:
            _log(f"FAIL rename on box: {(r.stderr or '').strip()[:200]}")
            return 1
        _log(f"OK pushed {size_mb:.1f} MB (sha {local_sha[:12]}) to {HOST}:{final}")
        return 0
    except subprocess.TimeoutExpired as e:
        _log(f"FAIL timeout: {e}")
        return 1
    except OSError as e:
        _log(f"FAIL {type(e).__name__}: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
