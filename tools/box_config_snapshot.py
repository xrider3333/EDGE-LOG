r"""tools/box_config_snapshot.py -- the box's live config exists ONLY on the box
(WEBULL_GO_LIVE.md 1.9); this copies it somewhere the owner can see what changed.

Copies qqq_exec/config.json, webull_orders/config.json, cloud_signal's own config
files (config.json if the box has one, stream_config.json -- see
api/cloud_signal_stream.py -- if present), the edgelog systemd unit/timer/path files,
any of their drop-in overrides (e.g. edgelog-qqq-exec.service.d/standby.conf), and
/etc/logrotate.d/edgelog into a timestamped folder under a PRIVATE, UNTRACKED local
directory (default C:\EdgeLog\box_config_history\<timestamp>\ -- these files can hold
account ids, so this NEVER writes into the repo), and prints a diff against the
previous snapshot. The PRINTED diff masks any value whose key looks like an account
id, key, secret or token (first 2 chars + "**") -- the on-disk snapshot files keep the
full values, only what reaches stdout (and so the lead agent's transcript) is
redacted. tools/box_deploy.py calls this before and after every deploy.

The ssh/scp transport (_fetch_all_from_box) and the pure snapshot-writing/diffing
logic (take_snapshot) are split apart on purpose: take_snapshot only needs a dict of
{relative_path: bytes-or-None}, so tests exercise it directly against temp
directories with fake bytes, with no ssh involved anywhere in the test suite.

Usage:
    python tools/box_config_snapshot.py                 # take + diff a snapshot
    python tools/box_config_snapshot.py --label pre-deploy
"""
import argparse
import datetime as _dt
import difflib
import os
import re
import shlex
import subprocess
import sys

HOST = "ubuntu@163.192.117.12"
KEY = os.path.expanduser(os.path.join("~", ".ssh", "edgelog_oracle"))
SSH_OPTS = ["-i", KEY, "-o", "BatchMode=yes", "-o", "ConnectTimeout=20"]
REMOTE_HOME = "/home/ubuntu/edgelog"

# (remote path, local-relative path). cloud_signal/config.json is speculative -- no
# such file exists in this codebase today (api/cloud_signal.py's CROWN_LEGS are
# hardcoded, not read from a config file), but a future one would land here with no
# code change needed; it is simply absent (None) until then. stream_config.json DOES
# exist today (api/cloud_signal_stream.py's load_stream_config).
REMOTE_FILES = [
    (f"{REMOTE_HOME}/qqq_exec/config.json", "qqq_exec/config.json"),
    (f"{REMOTE_HOME}/webull_orders/config.json", "webull_orders/config.json"),
    (f"{REMOTE_HOME}/cloud_signal/config.json", "cloud_signal/config.json"),
    (f"{REMOTE_HOME}/cloud_signal/stream_config.json", "cloud_signal/stream_config.json"),
    ("/etc/logrotate.d/edgelog", "etc/logrotate.d/edgelog"),
]
# systemd unit glob -- listed live off the box (see _list_remote_units) rather than
# hardcoded, so a renamed/added edgelog-*.service|timer|path unit is picked up with no
# edit here.
SYSTEMD_GLOB = "/etc/systemd/system/edgelog-*"
SYSTEMD_SUFFIXES = (".service", ".timer", ".path")
# A drop-in override directory (e.g. edgelog-qqq-exec.service.d/standby.conf) changes a
# unit's live behaviour -- RestartSec, etc. -- without touching the .service file
# itself, so it has to be captured and diffed too. Listed live off the box, same as
# the units.
SYSTEMD_DROPIN_GLOB = "/etc/systemd/system/edgelog-*.d/*.conf"
_ETC_SYSTEMD_PREFIX = "/etc/systemd/system/"

# Config keys whose printed diff VALUES get masked (first 2 chars + "**") -- these
# files can hold account ids and secrets, and a printed diff is stdout the lead agent's
# transcript captures. The files on disk in the private snapshot folder keep the full,
# unmasked values; only what gets printed/returned as diff text is redacted.
_SENSITIVE_KEY_RE = re.compile(
    r'("(?:[^"]*(?:account|_id|key|secret|token)[^"]*)"\s*:\s*)"([^"]*)"', re.IGNORECASE)


def _default_dest_root():
    return os.path.join(os.environ.get("EDGELOG_HOME") or r"C:\EdgeLog", "box_config_history")


# ── pure snapshot writing + diffing (unit tested with temp dirs) ─────────────────────────
def take_snapshot(files, dest_root=None, now=None):
    """`files`: {relative_path: bytes or None} -- None means "not present on the box",
    and that path is simply skipped (not written, not diffed as a deletion beyond
    noting it). Writes a new timestamped folder under `dest_root`
    (default C:\\EdgeLog\\box_config_history), and diffs each written file, by relative
    path, against the same path in the immediately-previous snapshot folder (if any).

    Returns (snapshot_dir, written_paths, diff_text). diff_text is '' when this is the
    first snapshot or nothing differs from the previous one."""
    dest_root = dest_root or _default_dest_root()
    ts = (now or _dt.datetime.now()).strftime("%Y%m%d_%H%M%S")
    snap_dir = os.path.join(dest_root, ts)
    prev_dir = _previous_snapshot_dir(dest_root, before=ts)

    written = []
    diff_chunks = []
    for rel, content in sorted(files.items()):
        if content is not None:
            local_path = os.path.join(snap_dir, rel.replace("/", os.sep))
            os.makedirs(os.path.dirname(local_path), exist_ok=True)
            with open(local_path, "wb") as f:
                f.write(content)
            written.append(rel)
        # Diffed either way (content is None too): a file present in the previous
        # snapshot but absent now must show up as "missing", not be silently dropped.
        if prev_dir:
            chunk = _diff_one(prev_dir, snap_dir, rel)
            if chunk:
                diff_chunks.append(chunk)
    return snap_dir, written, "\n".join(diff_chunks)


def _previous_snapshot_dir(dest_root, before):
    if not os.path.isdir(dest_root):
        return None
    names = sorted(n for n in os.listdir(dest_root)
                   if os.path.isdir(os.path.join(dest_root, n)) and n < before)
    return os.path.join(dest_root, names[-1]) if names else None


def _mask_sensitive(line):
    """Masks the VALUE of any `"key": "value"` pair whose key contains account, _id,
    key, secret or token (case-insensitive) -- e.g. an account id in
    webull_orders/config.json -- to the first 2 characters plus "**". Only touches
    printed/returned diff text; the files on disk are never modified."""
    def _repl(m):
        val = m.group(2)
        masked = (val[:2] + "**") if val else "**"
        return f'{m.group(1)}"{masked}"'
    return _SENSITIVE_KEY_RE.sub(_repl, line)


def _diff_one(prev_dir, new_dir, rel):
    prev_path = os.path.join(prev_dir, rel.replace("/", os.sep))
    new_path = os.path.join(new_dir, rel.replace("/", os.sep))
    prev_lines = _read_text_lines(prev_path)
    new_lines = _read_text_lines(new_path)
    if prev_lines is None and new_lines is None:
        return ""
    if prev_lines is None:
        return f"--- {rel} ---\n(new file this snapshot)"
    if prev_lines == new_lines:
        return ""
    if new_lines is None:
        return f"--- {rel} ---\n(present in the previous snapshot, missing from this one)"
    diff = difflib.unified_diff(prev_lines, new_lines,
                                fromfile=f"{rel} (previous)", tofile=f"{rel} (this snapshot)",
                                lineterm="")
    masked = [_mask_sensitive(line) for line in diff]
    return f"--- {rel} ---\n" + "\n".join(masked)


def _read_text_lines(path):
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return f.read().splitlines(keepends=True)
    except (OSError, UnicodeDecodeError):
        return ["(binary or unreadable file -- not diffed line by line)"]


# ── ssh/scp transport (never exercised in tests) ──────────────────────────────────────
def _ssh(cmd, timeout=60):
    return subprocess.run(["ssh", *SSH_OPTS, HOST, cmd], capture_output=True, text=True, encoding="utf-8", errors="replace",
                          timeout=timeout)


def _remote_exists(path):
    return _ssh(f"test -e {shlex.quote(path)}").returncode == 0


def _remote_read_bytes(path, max_bytes=1_000_000):
    """Reads a small remote file's raw bytes over ssh (base64, to survive the text
    pipe safely) rather than a separate scp per file -- these config files are a few
    KB each. Returns None if the file doesn't exist or is unreadable."""
    if not _remote_exists(path):
        return None
    r = subprocess.run(
        ["ssh", *SSH_OPTS, HOST, f"base64 -w0 {shlex.quote(path)} 2>/dev/null"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
    if r.returncode != 0 or not (r.stdout or "").strip():
        return None
    import base64
    try:
        data = base64.b64decode(r.stdout.strip())
    except Exception:
        return None
    if len(data) > max_bytes:
        return None  # sanity cap -- these are hand-written config files, not logs
    return data


def _list_remote_units():
    r = _ssh(f"ls -1 {SYSTEMD_GLOB} 2>/dev/null")
    names = [ln.strip() for ln in (r.stdout or "").splitlines() if ln.strip()]
    return [n for n in names if n.endswith(SYSTEMD_SUFFIXES)]


def _list_remote_dropins():
    r = _ssh(f"ls -1 {SYSTEMD_DROPIN_GLOB} 2>/dev/null")
    return [ln.strip() for ln in (r.stdout or "").splitlines() if ln.strip()]


def _dropin_rel_path(dropin_path):
    """/etc/systemd/system/edgelog-qqq-exec.service.d/standby.conf ->
    etc/systemd/system/edgelog-qqq-exec.service.d/standby.conf -- the local snapshot's
    relative path for a systemd drop-in override, keeping the unit.d/ structure so it
    doesn't collide with the unit file itself. Returns None for a path that doesn't
    live under /etc/systemd/system/ (shouldn't happen given SYSTEMD_DROPIN_GLOB, but
    never silently mis-file something that does)."""
    if not dropin_path.startswith(_ETC_SYSTEMD_PREFIX):
        return None
    return "etc/systemd/system/" + dropin_path[len(_ETC_SYSTEMD_PREFIX):]


def _fetch_all_from_box():
    """Builds the {relative_path: bytes-or-None} dict take_snapshot() needs, reading
    everything off the box read-only (cat/test/ls, via base64 -- never a write)."""
    files = {}
    for remote_path, rel in REMOTE_FILES:
        files[rel] = _remote_read_bytes(remote_path)
    for unit_path in _list_remote_units():
        rel = "etc/systemd/system/" + os.path.basename(unit_path)
        files[rel] = _remote_read_bytes(unit_path)
    for dropin_path in _list_remote_dropins():
        rel = _dropin_rel_path(dropin_path)
        if rel:
            files[rel] = _remote_read_bytes(dropin_path)
    return files


def take_snapshot_from_box(label=None, dest_root=None):
    """The real thing: fetches every config file off the box and writes+diffs a
    snapshot. Returns (snapshot_dir, written_paths, diff_text). `label` is cosmetic
    (printed / could be folded into a manifest later) -- the folder name is always
    the timestamp, so pre- and post-deploy snapshots never collide."""
    files = _fetch_all_from_box()
    snap_dir, written, diff_text = take_snapshot(files, dest_root=dest_root)
    if label:
        try:
            with open(os.path.join(snap_dir, "_label.txt"), "w", encoding="utf-8") as f:
                f.write(label + "\n")
        except OSError:
            pass
    return snap_dir, written, diff_text


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--label", default=None, help="cosmetic label written into the snapshot folder")
    args = ap.parse_args(argv)
    snap_dir, written, diff_text = take_snapshot_from_box(label=args.label)
    print(f"snapshot: {snap_dir}")
    print(f"files: {written}")
    if diff_text:
        print(diff_text)
    else:
        print("(no diff against the previous snapshot)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
