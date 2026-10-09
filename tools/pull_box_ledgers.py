"""tools/pull_box_ledgers.py -- nightly copy of the Webull book's ledgers from the Oracle box
to the PC (WEBULL_GO_LIVE.md 2.9 / 3.9: the book's positions, today's P&L and order memory
existed only on one VM, and broker_orders.csv trims itself to its last 100 rows).

Copies, read-only on the box, into a dated PRIVATE folder on the PC (never the repo: the
webull_orders config and state carry account ids):

    C:\\EdgeLog\\box_backup\\<YYYY-MM-DD_HHMM>\\{qqq_exec,webull_orders,cloud_signal}\\...

Only ledgers and state, not the KEEL model (rebuilt on the box nightly) or lock files.
Keeps the newest KEEP_DAYS folders. Appends one line per run to
C:\\EdgeLog\\logs\\pull_box_ledgers.log. Exit 0 on success, 1 on any failure (so the
scheduled task shows red). Never writes on the box, never touches Webull.

Usage:  python tools/pull_box_ledgers.py [--dest C:\\EdgeLog\\box_backup] [--dry-run]
"""
import argparse
import datetime as _dt
import os
import shutil
import subprocess
import sys

HOST = "ubuntu@163.192.117.12"
SSH_KEY = os.path.expanduser("~/.ssh/edgelog_oracle")
SSH_OPTS = ["-i", SSH_KEY, "-o", "ConnectTimeout=20", "-o", "BatchMode=yes"]
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


def _log(line):
    stamp = _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(line)
    try:
        os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(f"{stamp} {line}\n")
    except OSError:
        pass


def _prune(dest, keep):
    runs = sorted(d for d in os.listdir(dest) if os.path.isdir(os.path.join(dest, d)))
    for old in runs[:-keep] if len(runs) > keep else []:
        shutil.rmtree(os.path.join(dest, old), ignore_errors=True)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dest", default=DEFAULT_DEST)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    run_dir = os.path.join(args.dest, _dt.datetime.now().strftime("%Y-%m-%d_%H%M"))
    if args.dry_run:
        _log(f"DRY-RUN would copy {len(FILES)} file(s) from {HOST} into {run_dir}")
        return 0
    copied, missing, failed = 0, [], []
    for rel in FILES:
        local = os.path.join(run_dir, *rel.split("/"))
        os.makedirs(os.path.dirname(local), exist_ok=True)
        r = subprocess.run(["scp", "-q", *SSH_OPTS, f"{HOST}:{REMOTE_HOME}/{rel}", local],
                           capture_output=True, text=True, encoding="utf-8", errors="replace",
                           timeout=120)
        if r.returncode == 0:
            copied += 1
        elif "No such file" in (r.stderr or ""):
            missing.append(rel)
        else:
            failed.append(rel)
    try:
        _prune(args.dest, KEEP_DAYS)
    except OSError:
        pass
    status = "OK" if not failed and copied else "FAIL"
    _log(f"{status} copied {copied}/{len(FILES)} into {run_dir}"
         + (f"; missing on box: {', '.join(missing)}" if missing else "")
         + (f"; FAILED: {', '.join(failed)}" if failed else ""))
    return 0 if status == "OK" else 1


if __name__ == "__main__":
    sys.exit(main())
