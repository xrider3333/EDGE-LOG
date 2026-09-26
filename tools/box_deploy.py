r"""tools/box_deploy.py -- the ONE way to change what code the Webull QQQ book runs
(WEBULL_GO_LIVE.md item 1.9: "nothing controls changes on the live box"). Runs on the
PC, drives the box over ssh. Never runs itself on the box, and never touches Webull or
any broker API.

Retires ~/edgelog/flat_restart_once.sh (the shell script that restarts both services
whenever it finds the book flat, with no window check and no record of why) -- its
flatness test is reimplemented here as _book_is_flat, in Python, so it is unit
tested; deploy/cloud/CHANGE_CONTROL.md tells the owner to delete the shell script on
the box once this ships.

WHAT ONE RUN DOES, IN ORDER
  1. Resolves the target commit: --commit, or (default) whatever origin/main is on
     GitHub right now (`git ls-remote` -- printed, never assumed silently).
  2. Refuses if "now" (America/New_York) falls on a trading session
     (api/market_calendar.is_session) inside the PROTECTED WINDOW [09:25, 16:05) ET,
     unless --owner-waiver '<text>' is given. A waiver is always printed and, on a
     real (non---dry-run) run, appended to the deploy log with the ET time it was used.
  3. Refuses unless the book is flat on the box right now (_book_is_flat): no open
     legs in qqq_exec/state.json, no non-zero qty in webull_orders/state.json's
     broker_sent_positions, and no pending entry in qqq_exec/state.json's
     "_broker_resend" or "_broker_fill_capture" queues. An unreadable or unparsable
     state file (ssh failure, missing file, bad JSON) is NEVER treated as an empty,
     flat book -- _read_remote_json returns None on any such failure, and both
     _book_is_flat and main() refuse rather than guess.
  4. Refuses if the box's repo has any local change to a tracked file
     (_remote_git_clean) -- a `git checkout` would carry it onto the new commit, so
     the code actually running could silently differ from the sha this script prints
     and logs. Fetches the box's repo state, resolves --commit (any ref: a sha,
     branch or tag) to its full commit sha ON THE BOX (_remote_resolve_commit, via
     `git rev-parse --verify <ref>^{commit}`, AFTER the fetch) so what gets deployed
     and logged is always an exact sha, never a branch name that could mean something
     else on the box than it does here, and prints the commits and the changed files
     between the box's current HEAD and the resolved target, SCOPED to the book's own
     code paths (_book_pathspecs: the two services' modules, market_calendar, every
     crown leg's strategy file plus its whole _AUGUR_PARENT chain -- read via
     `git show <target>:<path>` off the box, at the TARGET commit, so a crown-leg
     strategy swap in the commit being deployed is picked up with no edit needed here
     --, the KEEL trainer, and deploy/cloud/*). A change outside these paths (e.g. a
     STUDIES page tweak on main) never shows up and never blocks a deploy. If any
     changed file is a unit template, requirements-cloud.txt or edgelog.logrotate
     under deploy/cloud/, this prints a loud warning that install.sh must be applied
     by hand -- this script never runs it.
  5. Without --yes, stops here and prints "re-run with --yes to deploy" (exit 1).
     --dry-run does steps 1-4 and stops the same way, but skips the --yes gate
     entirely, never snapshots config, never writes the deploy log, and never touches
     the box beyond the read-only git/cat/wc calls steps 2-4 needed -- which DOES
     include a `git fetch` on the box (it only moves the box's remote-tracking refs,
     never any code).
  6. Snapshots the box's live config (tools/box_config_snapshot.py) -- BEFORE.
  7. Re-reads both state files and re-runs _book_is_flat ONE more time, immediately
     before touching anything -- steps 1-6 include a 180s git fetch and dozens of ssh
     round trips, long enough for the book to open a leg (ENGUQ_335 trades the ETH
     session, so this can happen outside 09:25-16:05 ET too) in the gap since step 3.
     Aborts, logs it, and touches nothing if the book is no longer flat, or if the
     clock has moved into the protected window since step 2.
  8. On the box: `git checkout --detach <sha>` (a detached HEAD, not a branch merge --
     correct for a rollback just as much as a roll-forward; no fetch here -- the sha
     was already fetched and resolved in step 4, so re-fetching would only reopen the
     just-closed flatness gap with a network round trip), stop both services
     (`sudo -n`, so a missing passwordless-sudo grant fails fast instead of hanging),
     start them, and verify for the WHOLE BOOT_VERIFY_TIMEOUT_SEC window (stopping
     early only on a Traceback or a broker reconcile failure -- see _verify_boot):
     both `systemctl is-active` (sampled AFTER boot verification, not right after
     start, and only trusted if NRestarts is a known, unchanged value for BOTH
     services since the start -- an unparsable NRestarts fails closed, and a unit
     sampled the instant it starts reads "active" even if it then crash-loops), the
     fresh qqq_exec log shows "SERVING" AND "lease claimed" AND -- unless
     webull_orders/config.json's mode is OFF (_remote_broker_mode: OFF never logs a
     reconcile result at all) -- "broker reconcile OK at boot", and neither service's
     fresh log shows "Traceback". Every step from the checkout onward is wrapped so
     an ssh timeout or a non-zero stop/start return code is logged as "DEPLOY FAILED
     <step>" instead of crashing with a bare traceback and no outcome line.
  9. Snapshots the box's live config again -- AFTER (so a config drift the new code
     causes on its own is visible immediately, not just at the next scheduled check).
  10. Appends one line to C:\EdgeLog\logs\box_deploy.log (written at run time by this
     script; nothing else reads it).

Usage:
    python tools/box_deploy.py --dry-run
    python tools/box_deploy.py --yes
    python tools/box_deploy.py --commit <sha> --yes
    python tools/box_deploy.py --owner-waiver "owner OK, 10:15 ET, hotfix for X" --yes

Tests (tests/test_box_deploy.py) exercise only the pure decision functions
(_in_protected_window, _book_is_flat, the strategy-chain parser, and the
unit/deps-changed pattern) against fake clocks/state/text, plus _read_remote_json's
own failure handling with _ssh monkeypatched to a fake result (never a real
subprocess). No test in this repo opens an ssh connection to the box.
"""
import argparse
import datetime as _dt
import json
import os
import re
import shlex
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from api import market_calendar  # noqa: E402
from tools import box_config_snapshot  # noqa: E402

try:
    from zoneinfo import ZoneInfo
    _NY = ZoneInfo("America/New_York")
except Exception:  # pragma: no cover -- zoneinfo ships with 3.9+, this repo runs 3.13
    _NY = None

# -- box + repo -----------------------------------------------------------------------
HOST = "ubuntu@163.192.117.12"
KEY = os.path.expanduser(os.path.join("~", ".ssh", "edgelog_oracle"))
SSH_OPTS = ["-i", KEY, "-o", "BatchMode=yes", "-o", "ConnectTimeout=20"]
REPO_URL = "https://github.com/xrider3333/EDGE-LOG.git"
REMOTE_HOME = "/home/ubuntu/edgelog"
REMOTE_REPO = f"{REMOTE_HOME}/EDGE-LOG"
SERVICES = ["edgelog-qqq-exec", "edgelog-cloud-signal"]
QQQ_LOG = f"{REMOTE_HOME}/logs/qqq_exec.log"
CS_LOG = f"{REMOTE_HOME}/logs/cloud_signal.log"

# -- protected deploy window (WEBULL_GO_LIVE.md 1.9) -----------------------------------
PROTECTED_START = _dt.time(9, 25)
PROTECTED_END = _dt.time(16, 5)

BOOT_VERIFY_TIMEOUT_SEC = 60
BOOT_VERIFY_POLL_SEC = 3

LOG_PATH = os.path.join(os.environ.get("EDGELOG_HOME") or r"C:\EdgeLog", "logs", "box_deploy.log")

# -- book code paths, scoped for the commit/diff display -------------------------------
# Everything the two live services actually import, plus the deploy templates. The
# three crown legs' strategy files (and whatever THEY dynamically load as their own
# _AUGUR_PARENT base -- see augur_strategies/ORB_3_6_R6.py's own pattern) are resolved
# off the box in _book_pathspecs, AT THE TARGET COMMIT (via `git show`, not the box's
# current checkout), so a strategy swap in the commit being deployed is picked up with
# no edit to this file.
_STATIC_BOOK_PATHS = [
    "api/qqq_exec.py",
    "api/webull_orders.py",
    "api/webull_stream.py",
    "api/webull_sync.py",
    "api/cloud_signal.py",
    "api/cloud_signal_stream.py",
    "api/market_calendar.py",
    "augur_engine/ml_keel.py",
    "augur_engine/fastloop.py",
    "tools/keel_live_state.py",
    "deploy/cloud",
]

_STRATEGY_RE = re.compile(r'"strategy":\s*"([^"]+)"')
_PARENT_RE = re.compile(r'_AUGUR_PARENT\s*=\s*"([^"]+)"')

# A changed file under deploy/cloud/ that install.sh applies (a systemd unit/timer/path
# template, the pinned dependency list, or the logrotate config) never gets applied by
# a plain `git checkout` -- box_deploy.py never runs install.sh, so main() warns loudly
# when the diff touches one of these instead of silently deploying code with stale
# units or dependencies.
_UNIT_OR_DEPS_RE = re.compile(
    r'^deploy/cloud/(?:.*\.(?:service|timer|path)|requirements-cloud\.txt|edgelog\.logrotate)$')


def parse_crown_strategy_files(cloud_signal_src):
    """The distinct augur_strategies/*.py filenames CROWN_LEGS names, read straight
    out of api/cloud_signal.py's own source text (never imported/executed -- this
    module must never run a strategy file's code, only read its text)."""
    return sorted(set(_STRATEGY_RE.findall(cloud_signal_src)))


def strategy_chain(name, read_src, _seen=None, _depth=0):
    """`name` plus every file its _AUGUR_PARENT chain points to (see
    augur_strategies/ORB_3_6_R6.py's own dynamic-import pattern), as a sorted list.
    `read_src(filename)` returns that augur_strategies file's text, or None if it
    can't be read -- the chain just stops there rather than raising. Depth-capped and
    cycle-guarded so a bad/circular _AUGUR_PARENT can never loop forever."""
    seen = _seen if _seen is not None else set()
    if name in seen or _depth > 10:
        return sorted(seen)
    src = read_src(name)
    if not src:
        return sorted(seen)   # unreadable/missing -- don't add a file that isn't there
    seen.add(name)
    m = _PARENT_RE.search(src)
    if m and m.group(1) not in seen:
        return strategy_chain(m.group(1), read_src, _seen=seen, _depth=_depth + 1)
    return sorted(seen)


def _book_pathspecs(read_at_target):
    """The list of git pathspecs (relative to the repo root) that count as the book's
    own code for the commit/diff display. `read_at_target(repo_relative_path)` returns
    that file's text AT THE COMMIT BEING DEPLOYED (not whatever the box currently has
    checked out), or None if it doesn't exist there -- see _remote_show."""
    paths = list(_STATIC_BOOK_PATHS)
    cs_src = read_at_target("api/cloud_signal.py")
    strategy_files = parse_crown_strategy_files(cs_src) if cs_src else []
    seen = set()
    for name in strategy_files:
        for fname in strategy_chain(
                name, lambda n: read_at_target(f"augur_strategies/{n}")):
            if fname not in seen:
                seen.add(fname)
                paths.append(f"augur_strategies/{fname}")
    return paths


# -- pure decision functions (unit tested, no ssh) --------------------------------------
def _in_protected_window(now_et):
    """True if `now_et` (a datetime; only its date and time-of-day matter) falls on an
    equity trading session (api/market_calendar.is_session) with a clock time inside
    [09:25, 16:05) ET -- the window WEBULL_GO_LIVE.md 1.9 calls out as needing a
    deliberate --owner-waiver to deploy through."""
    if not market_calendar.is_session(now_et.date()):
        return False
    t = now_et.time()
    return PROTECTED_START <= t < PROTECTED_END


def _book_is_flat(qqq_state, webull_state):
    """Mirrors ~/edgelog/flat_restart_once.sh's own flatness check (see that script,
    retired by this change -- deploy/cloud/CHANGE_CONTROL.md) in plain Python so it
    can be unit tested: flat only when qqq_exec's state.json has no open legs and no
    pending broker resend/fill-capture entries ("_broker_resend" /
    "_broker_fill_capture" -- see api/qqq_exec.py's _queue_broker_resend /
    _queue_broker_fill_capture), and webull_orders' state.json shows every
    broker_sent_positions qty at 0.

    A state that is None, or anything that isn't a parsed dict, is NEVER treated as an
    empty/flat book -- that was the retired shell script's own failure mode inverted
    (it fails CLOSED on a json.load error), and this must too: an unreadable file
    (ssh failure, missing file, bad JSON -- see _read_remote_json) means "don't know",
    not "flat". Only an explicitly present, parsed dict with empty legs, resend and
    fill-capture, and zero qtys counts as flat.

    A MALFORMED entry one level down (e.g. "legs" itself is a list, or one
    broker_sent_positions value is a bare int instead of {"qty": ...}) is treated the
    same way, not raised as an AttributeError/TypeError: this function never crashes
    on bad shape, it fails CLOSED with a reason instead, exactly like the top-level
    unreadable-state case above. This used to assume every one of those was always a
    dict/mapping and blew up with a bare traceback (no REFUSED line, nothing logged)
    on the first malformed entry -- still fail-closed in effect (nothing was ever
    stopped or started), but not a clean, logged refusal.

    Returns (is_flat, [reason, ...]); reasons is empty exactly when is_flat is True."""
    reasons = []
    if not isinstance(qqq_state, dict):
        reasons.append("qqq_exec state.json unreadable")
    if not isinstance(webull_state, dict):
        reasons.append("webull_orders state.json unreadable")
    if reasons:
        return (False, reasons)

    def _mapping_or_flag(container, key, human):
        """container[key] if it's a dict (missing key -> {}), else None plus a
        reason appended to `reasons` -- callers must treat None as "don't know",
        same as the top-level unreadable-state case."""
        val = container.get(key)
        if val is None:
            return {}
        if not isinstance(val, dict):
            reasons.append(f"{human} is not a mapping (got {type(val).__name__}) "
                           "-- treating as not flat")
            return None
        return val

    legs = _mapping_or_flag(qqq_state, "legs", "qqq_exec state.json 'legs'")
    if legs:
        reasons.append(f"qqq_exec state.json has open legs: {sorted(legs)}")
    resend = _mapping_or_flag(qqq_state, "_broker_resend", "qqq_exec state.json '_broker_resend'")
    if resend:
        reasons.append(f"pending broker resend entries: {sorted(resend)}")
    fillcap = _mapping_or_flag(qqq_state, "_broker_fill_capture",
                               "qqq_exec state.json '_broker_fill_capture'")
    if fillcap:
        reasons.append(f"pending broker fill-capture entries: {sorted(fillcap)}")

    positions = _mapping_or_flag(webull_state, "broker_sent_positions",
                                 "webull_orders state.json 'broker_sent_positions'")
    if positions:
        nonzero = {}
        for k, v in positions.items():
            if not isinstance(v, dict):
                reasons.append(f"webull_orders broker_sent_positions[{k!r}] is not a "
                               f"mapping (got {type(v).__name__}) -- treating as not flat")
                nonzero[k] = "malformed"
                continue
            qty = v.get("qty")
            if qty:
                nonzero[k] = qty
        if nonzero:
            reasons.append(f"webull_orders broker_sent_positions not flat: {nonzero}")
    return (not reasons, reasons)


# -- ssh/scp transport (never exercised in tests) ----------------------------------------
def _ssh(cmd, timeout=120):
    return subprocess.run(["ssh", *SSH_OPTS, HOST, cmd], capture_output=True, text=True, encoding="utf-8", errors="replace",
                          timeout=timeout)


def _remote_show(sha, repo_relative_path, timeout=30):
    """Text of a file AT A SPECIFIC COMMIT (`git show <sha>:<path>`), or None if it
    doesn't exist there or the read fails. Never used on a secrets file -- callers
    only ever pass source-code paths, and this never checks anything out."""
    r = _ssh(f"git -C {shlex.quote(REMOTE_REPO)} show "
             f"{shlex.quote(sha)}:{shlex.quote(repo_relative_path)} 2>/dev/null",
             timeout=timeout)
    out = r.stdout or ""
    return out if (r.returncode == 0 and out) else None


def _read_remote_json(path):
    """A remote JSON file's parsed dict, or None on ANY failure: non-zero ssh return
    code, empty output, a JSON parse error, or a top-level value that isn't a dict.
    None must never be confused with "file exists and is an empty dict" -- callers
    (_book_is_flat, main) treat None as "don't know", not "flat"."""
    r = _ssh(f"cat {shlex.quote(path)} 2>/dev/null")
    text = (r.stdout or "").strip()
    if r.returncode != 0 or not text:
        return None
    try:
        data = json.loads(text)
    except (ValueError, TypeError):
        return None
    return data if isinstance(data, dict) else None


def _remote_line_count(path):
    r = _ssh(f"wc -l < {shlex.quote(path)} 2>/dev/null")
    try:
        return int((r.stdout or "0").strip())
    except ValueError:
        return 0


def _remote_head_sha():
    """The box's current HEAD sha, or '' if `git rev-parse` itself failed -- callers
    must check for '' rather than trust it as a real sha."""
    r = _ssh(f"git -C {shlex.quote(REMOTE_REPO)} rev-parse HEAD")
    return (r.stdout or "").strip() if r.returncode == 0 else ""


def _remote_git_fetch():
    return _ssh(f"git -C {shlex.quote(REMOTE_REPO)} fetch --quiet origin", timeout=180)


def _remote_resolve_commit(ref):
    """`ref` (a sha, or any git ref name such as a branch or tag) resolved to its
    full commit sha ON THE BOX, via `git rev-parse --verify <ref>^{commit}` --
    called AFTER _remote_git_fetch so a ref that only just landed on origin still
    resolves. Returns None if the ref doesn't resolve to a commit at all (bad sha,
    typo, or a branch name the box has never fetched).

    Without this, `--commit main` would resolve to whatever the BOX's own local
    `main` branch happens to point at (its stale, non-fast-forwarded local branch,
    not origin/main) with no fetch of that specific ref -- deploying and logging
    'target=main' instead of a real sha, so nobody could later tell exactly what
    code was running from the log alone."""
    r = _ssh(f"git -C {shlex.quote(REMOTE_REPO)} rev-parse --verify "
             f"{shlex.quote(ref + '^{commit}')}")
    out = (r.stdout or "").strip()
    return out if (r.returncode == 0 and out) else None


def _remote_git_clean():
    """True when the box's repo has no local changes to TRACKED files (untracked
    files are ignored -- they can't ride along on a `git checkout`). `git checkout
    --detach <sha>` silently carries forward any local edit to a tracked file, so
    without this check the code actually running after a deploy could differ from
    the sha this script resolved, printed and logged -- exactly the gap
    `--commit`'s own resolution above is trying to close."""
    r = _ssh(f"git -C {shlex.quote(REMOTE_REPO)} status --porcelain --untracked-files=no")
    return r.returncode == 0 and not (r.stdout or "").strip()


def _remote_broker_mode():
    """The order adapter's effective mode ("OFF"/"PAPER"/"LIVE") read straight from
    webull_orders/config.json's "mode" key on the box, or "OFF" if that file is
    missing, unreadable, or not a dict -- the exact same fallback
    api.webull_orders.load_config() itself uses when the file isn't there.

    _verify_boot only ever sees a "broker reconcile OK at boot" line when the order
    adapter actually ran a reconcile -- _reconcile_broker_at_boot returns early,
    logging nothing at all, when the adapter is in OFF mode (see its own
    docstring). Requiring reconcile_ok unconditionally would therefore make every
    deploy fail boot verification forever while the book is OFF; this function lets
    main() require it only when the box is actually in PAPER or LIVE mode."""
    cfg = _read_remote_json(f"{REMOTE_HOME}/webull_orders/config.json")
    if not isinstance(cfg, dict):
        return "OFF"
    return str(cfg.get("mode") or "OFF").upper()


def _remote_git_log_and_diff(base_sha, target_sha, pathspecs):
    """Returns (log_text, diff_text, log_ok, diff_ok) -- callers must check the *_ok
    flags rather than treat empty text as "nothing changed", since a failed git
    command also prints nothing."""
    paths_arg = " ".join(shlex.quote(p) for p in pathspecs)
    log_cmd = (f"git -C {shlex.quote(REMOTE_REPO)} log --oneline "
               f"{shlex.quote(base_sha)}..{shlex.quote(target_sha)} -- {paths_arg}")
    diff_cmd = (f"git -C {shlex.quote(REMOTE_REPO)} diff --stat "
                f"{shlex.quote(base_sha)} {shlex.quote(target_sha)} -- {paths_arg}")
    log_r = _ssh(log_cmd)
    diff_r = _ssh(diff_cmd)
    return ((log_r.stdout or "").strip(), (diff_r.stdout or "").strip(),
            log_r.returncode == 0, diff_r.returncode == 0)


def _remote_git_diff_names(base_sha, target_sha, pathspecs):
    """The bare list of changed file paths (git diff --name-only), used only to check
    each one against _UNIT_OR_DEPS_RE -- separate from the --stat text shown to the
    operator because --stat's " path | N ++--" format isn't reliable to parse.
    Returns (names, ok)."""
    paths_arg = " ".join(shlex.quote(p) for p in pathspecs)
    cmd = (f"git -C {shlex.quote(REMOTE_REPO)} diff --name-only "
           f"{shlex.quote(base_sha)} {shlex.quote(target_sha)} -- {paths_arg}")
    r = _ssh(cmd)
    names = [ln.strip() for ln in (r.stdout or "").splitlines() if ln.strip()]
    return names, r.returncode == 0


def _resolve_origin_main():
    r = subprocess.run(["git", "ls-remote", REPO_URL, "refs/heads/main"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30)
    out = (r.stdout or "").strip()
    if r.returncode != 0 or not out:
        raise RuntimeError(f"could not resolve origin/main: {(r.stderr or '').strip()[:200]}")
    return out.split()[0]


def _services_active():
    """`systemctl is-active` for both services. Call this AFTER _verify_boot, not
    right after `systemctl start` -- a unit reports "active" the instant it starts
    even if Restart=always then crash-loops it for the rest of the boot window."""
    r = _ssh(f"systemctl is-active {' '.join(SERVICES)}")
    lines = (r.stdout or "").strip().splitlines()
    while len(lines) < len(SERVICES):
        lines.append("unknown")
    return dict(zip(SERVICES, lines))


def _n_restarts():
    """Each service's systemd NRestarts counter (how many times it has been
    restarted since it was last started), or None for a service whose value couldn't
    be parsed. Sampled right after `systemctl start` and again after _verify_boot;
    an increase between the two means the unit crash-looped during the boot window
    even though `systemctl is-active` alone would still read "active".

    Queries each unit with ITS OWN `systemctl show` call rather than one call for
    both units. A single call (`systemctl show A B -p NRestarts --value`) was tried
    first, but on this box it prints a blank line between the two units' values
    ('0', '', '0') rather than one line per unit -- zipping that by position always
    parsed edgelog-cloud-signal's value off the blank line and got None, and a
    None == None compare in the stability check then always read as "stable" for
    that service, silently defeating the crash-loop guard. One ssh round trip per
    unit costs one extra call for two services and never has this ambiguity."""
    out = {}
    for name in SERVICES:
        r = _ssh(f"systemctl show {shlex.quote(name)} -p NRestarts --value")
        val = (r.stdout or "").strip()
        try:
            out[name] = int(val)
        except ValueError:
            out[name] = None
    return out


def _restarts_stable(before, after):
    """True only when EVERY service's NRestarts count is a known, unchanged integer
    across `before` and `after`. A missing/unparsable value (None) on either side
    fails CLOSED (treated as NOT stable, i.e. possibly crash-looping) rather than
    comparing None == None and reading as stable -- that inversion is exactly the
    bug _n_restarts's docstring above describes."""
    for name in SERVICES:
        b, a = before.get(name), after.get(name)
        if b is None or a is None or b != a:
            return False
    return True


def _verify_boot(log_path, since_lines, timeout_sec=BOOT_VERIFY_TIMEOUT_SEC,
                 poll_sec=BOOT_VERIFY_POLL_SEC):
    """Polls `log_path` (the fresh lines only, past `since_lines`) for the WHOLE
    `timeout_sec` window, watching for "SERVING", "lease claimed" and "broker
    reconcile OK at boot" (see api/qqq_exec.py lines ~6146, ~6092, ~6971).

    Stops polling EARLY only on a bad signal -- a "Traceback" or a
    "BROKER RECONCILE MISMATCH/READ FAILURE at boot" line -- never on a good one.
    The previous version broke out the moment it saw "SERVING" plus either "lease
    claimed" or "broker reconcile OK at boot", which (a) let a crash 10-60s into
    the window go unnoticed (the spec's "no Traceback in the first 60s" needs the
    full window watched, not just until the good lines show up) and (b) could stop
    before the reconcile result was even logged, since qqq_exec's own boot order is
    SERVING -> lease claimed -> _reconcile_broker_at_boot (a networked Webull call
    with its own timeout) -- so "lease" alone was reached well before "reconcile_ok"
    had a chance to appear. Whether "reconcile_ok" is actually REQUIRED for the
    deploy to count as OK (broker OFF mode never logs it at all -- see
    _reconcile_broker_at_boot's own docstring) is decided by the caller in main(),
    using _remote_broker_mode(), not by this function.

    Returns a dict of what it saw -- never raises."""
    seen = {"serving": False, "lease": False, "reconcile_ok": False,
            "reconcile_fail": None, "traceback": False}
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        r = _ssh(f"tail -n +{since_lines + 1} {shlex.quote(log_path)} 2>/dev/null")
        text = r.stdout or ""
        if "SERVING" in text:
            seen["serving"] = True
        if "lease claimed" in text:
            seen["lease"] = True
        if "broker reconcile OK at boot" in text:
            seen["reconcile_ok"] = True
        for bad in ("BROKER RECONCILE MISMATCH at boot", "BROKER RECONCILE READ FAILURE at boot"):
            if bad in text and not seen["reconcile_fail"]:
                seen["reconcile_fail"] = bad
        if "Traceback" in text:
            seen["traceback"] = True
            break
        if seen["reconcile_fail"]:
            break
        time.sleep(poll_sec)
    return seen


def _log(msg):
    line = f"{_dt.datetime.now().isoformat(timespec='seconds')} {msg}"
    print(line)
    try:
        os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--commit", default=None,
                    help="git ref/sha to deploy (default: origin/main right now)")
    ap.add_argument("--owner-waiver", default=None, metavar="TEXT",
                    help="explicit owner text authorizing a deploy inside the "
                         "09:25-16:05 ET protected window on a trading day; logged")
    ap.add_argument("--yes", action="store_true",
                    help="actually deploy (without this, prints the plan and stops)")
    ap.add_argument("--dry-run", action="store_true",
                    help="do every check, print the plan, change nothing")
    args = ap.parse_args(argv)

    if args.yes and args.dry_run:
        print("REFUSED: --yes and --dry-run together make no sense -- pick one")
        return 2

    now_et = _dt.datetime.now(_NY) if _NY else _dt.datetime.now()
    try:
        target = args.commit or _resolve_origin_main()
    except (OSError, subprocess.TimeoutExpired, RuntimeError) as e:
        print(f"FAILED to resolve target commit: {e}")
        return 2
    print(f"target commit: {target}" + ("" if args.commit else " (origin/main, resolved now)"))

    if _in_protected_window(now_et) and not args.owner_waiver:
        print(f"REFUSED: {now_et:%Y-%m-%d %H:%M} ET is inside the 09:25-16:05 protected "
              f"window on a trading day. Re-run with --owner-waiver '<why>' to override.")
        return 1
    if args.owner_waiver:
        print(f"OWNER WAIVER in effect: {args.owner_waiver!r} (at {now_et:%Y-%m-%d %H:%M} ET)")

    try:
        qqq_state = _read_remote_json(f"{REMOTE_HOME}/qqq_exec/state.json")
        webull_state = _read_remote_json(f"{REMOTE_HOME}/webull_orders/state.json")
    except (OSError, subprocess.TimeoutExpired) as e:
        print(f"FAILED to read box state: {e}")
        return 2
    if not isinstance(qqq_state, dict) or not isinstance(webull_state, dict):
        print("REFUSED: could not read book state -- refusing")
        return 2
    try:
        flat, reasons = _book_is_flat(qqq_state, webull_state)
    except Exception as e:  # deliberately broad -- must never end in a bare traceback; fail closed
        print(f"REFUSED: could not evaluate book flatness ({type(e).__name__}: {e}) -- refusing")
        return 2
    if not flat:
        print("REFUSED: the book is not flat on the box:")
        for r_ in reasons:
            print(f"  - {r_}")
        return 1
    print("book is flat on the box.")

    try:
        current = _remote_head_sha()
        if not current:
            raise RuntimeError("could not read the box's current HEAD (git rev-parse failed)")
        if not _remote_git_clean():
            raise RuntimeError("the box's repo has local changes to tracked files -- refusing "
                               "to deploy (git status --porcelain --untracked-files=no is not "
                               "empty; a checkout would carry them onto the new commit)")
        fetch_r = _remote_git_fetch()
        if fetch_r.returncode != 0:
            raise RuntimeError(f"git fetch failed on the box: {(fetch_r.stderr or '').strip()[:300]}")
        resolved = _remote_resolve_commit(target)
        if not resolved:
            raise RuntimeError(f"could not resolve target commit {target!r} on the box "
                               "(git rev-parse --verify failed -- bad sha, typo, or a ref "
                               "the box has never fetched)")
        if resolved != target:
            print(f"resolved target {target!r} -> {resolved}")
        target = resolved
        pathspecs = _book_pathspecs(lambda relpath: _remote_show(target, relpath))
        log_text, diff_text, log_ok, diff_ok = _remote_git_log_and_diff(current, target, pathspecs)
        if not (log_ok and diff_ok):
            raise RuntimeError("git log/diff failed on the box for the book's paths")
        changed_names, names_ok = _remote_git_diff_names(current, target, pathspecs)
        if not names_ok:
            raise RuntimeError("git diff --name-only failed on the box for the book's paths")
    except (OSError, subprocess.TimeoutExpired, RuntimeError) as e:
        print(f"FAILED to read box git state: {e}")
        return 2
    print(f"box current HEAD: {current}")
    print("commits touching the book's code paths:")
    print(log_text or "  (none -- box is already at or ahead of the target for these paths)")
    print("files that change:")
    print(diff_text or "  (none)")

    unit_or_deps_changed = [n for n in changed_names if _UNIT_OR_DEPS_RE.match(n)]
    if unit_or_deps_changed:
        print("WARNING: unit/deps changed -- install.sh must be applied by hand: "
              + ", ".join(unit_or_deps_changed))

    if args.dry_run:
        print("DRY-RUN: stopping here, nothing changed. Re-run with --yes (no --dry-run) to deploy.")
        return 0
    if not args.yes:
        print("Re-run with --yes to deploy.")
        return 1

    print("snapshotting box config (pre-deploy)...")
    pre_dir, _, pre_diff = box_config_snapshot.take_snapshot_from_box(label="pre-deploy")
    print(f"  -> {pre_dir}")
    if pre_diff:
        print(pre_diff)

    _log(f"DEPLOY START target={target} current={current} waiver={args.owner_waiver!r}")

    # One more flatness (and protected-window) check, as close to the restart as this
    # script can get it: steps so far include a 180s git fetch and dozens of ssh round
    # trips, long enough for the book to open a leg since the first check above.
    print("re-checking the book is still flat immediately before the restart...")
    try:
        qqq_state2 = _read_remote_json(f"{REMOTE_HOME}/qqq_exec/state.json")
        webull_state2 = _read_remote_json(f"{REMOTE_HOME}/webull_orders/state.json")
    except (OSError, subprocess.TimeoutExpired) as e:
        _log(f"DEPLOY ABORTED re-check-failed error={e!r}")
        print(f"ABORTED: could not re-read box state just before the restart: {e}")
        return 2
    if not isinstance(qqq_state2, dict) or not isinstance(webull_state2, dict):
        _log("DEPLOY ABORTED re-check book state unreadable")
        print("ABORTED: could not read book state just before the restart -- refusing; "
              "nothing was stopped or started.")
        return 2
    try:
        flat2, reasons2 = _book_is_flat(qqq_state2, webull_state2)
    except Exception as e:  # deliberately broad -- fail closed with a clean ABORTED line
        _log(f"DEPLOY ABORTED re-check-flatness-error error={e!r}")
        print(f"ABORTED: could not evaluate book flatness just before the restart "
              f"({type(e).__name__}: {e}) -- nothing was stopped or started.")
        return 2
    if not flat2:
        _log(f"DEPLOY ABORTED no-longer-flat reasons={reasons2}")
        print("ABORTED: the book is no longer flat right before the restart -- "
              "nothing was stopped or started:")
        for r_ in reasons2:
            print(f"  - {r_}")
        return 1
    now_et2 = _dt.datetime.now(_NY) if _NY else _dt.datetime.now()
    if _in_protected_window(now_et2) and not args.owner_waiver:
        _log(f"DEPLOY ABORTED entered-protected-window now={now_et2.isoformat()}")
        print(f"ABORTED: {now_et2:%Y-%m-%d %H:%M} ET is now inside the 09:25-16:05 "
              f"protected window -- nothing was stopped or started.")
        return 1
    print("book is still flat.")

    try:
        n0_qqq = _remote_line_count(QQQ_LOG)
        n0_cs = _remote_line_count(CS_LOG)
        before_restarts = _n_restarts()

        # Checkout ONLY here -- no `git fetch` in this command. `target` was already
        # fetched and resolved to a full sha above (step 4), so the commit object is
        # already in the box's local git db; re-fetching here bought nothing but put
        # back up to a network-fetch-sized gap between the flatness re-check just
        # above and `systemctl stop` below, during which ENGUQ_335 (which trades the
        # ETH session) could open a leg on a book this script had just confirmed flat.
        r = _ssh(f"git -C {shlex.quote(REMOTE_REPO)} checkout --quiet --detach {shlex.quote(target)}",
                 timeout=60)
        if r.returncode != 0:
            _log(f"DEPLOY FAILED checkout rc={r.returncode} stderr={(r.stderr or '').strip()[:400]!r}")
            print("FAILED: checkout on the box did not succeed; services were not touched.")
            return 2

        stop_r = _ssh(f"sudo -n systemctl stop {' '.join(SERVICES)}", timeout=60)
        if stop_r.returncode != 0:
            _log(f"DEPLOY FAILED stop rc={stop_r.returncode} stderr={(stop_r.stderr or '').strip()[:400]!r}")
            print("FAILED: systemctl stop did not succeed on the box -- check it by hand.")
            return 2
        start_r = _ssh(f"sudo -n systemctl start {' '.join(SERVICES)}", timeout=60)
        if start_r.returncode != 0:
            _log(f"DEPLOY FAILED start rc={start_r.returncode} stderr={(start_r.stderr or '').strip()[:400]!r}")
            print("FAILED: systemctl start did not succeed on the box -- services may be "
                  "DOWN, check by hand immediately.")
            return 2

        after_start_restarts = _n_restarts()
        # Full BOOT_VERIFY_TIMEOUT_SEC window, watching for crashes the whole time --
        # see _verify_boot's own docstring. is-active / NRestarts are sampled only
        # AFTER this returns, never right after `systemctl start`.
        seen = _verify_boot(QQQ_LOG, n0_qqq)
        active = _services_active()
        after_verify_restarts = _n_restarts()
        cs_tail = (_ssh(f"tail -n +{n0_cs + 1} {shlex.quote(CS_LOG)} 2>/dev/null").stdout or "")
        cs_traceback = "Traceback" in cs_tail
        broker_mode = _remote_broker_mode()
    except (OSError, subprocess.TimeoutExpired) as e:
        _log(f"DEPLOY FAILED exception={e!r}")
        print(f"DEPLOY FAILED: {e} -- the box may be mid-restart, check it by hand.")
        return 2

    # A unit reports "active" the instant `systemctl start` returns even if
    # Restart=always then crash-loops it -- only trust "active" together with an
    # unchanged, KNOWN NRestarts count across the boot-verification window (a None on
    # either side fails closed -- see _restarts_stable's own docstring).
    stable = _restarts_stable(after_start_restarts, after_verify_restarts)

    # OFF mode never logs a reconcile result at all (_reconcile_broker_at_boot
    # returns early -- see its docstring), so reconcile_ok is only required when the
    # box is actually in PAPER or LIVE mode; SERVING and "lease claimed" are always
    # required, per the spec ("SERVING", "lease claimed" AND "broker reconcile OK at
    # boot"), not "lease OR reconcile" as this used to accept.
    reconcile_required = broker_mode != "OFF"
    boot_clean = (seen["serving"] and seen["lease"] and not seen["traceback"]
                  and not seen["reconcile_fail"]
                  and (seen["reconcile_ok"] or not reconcile_required))
    ok = (all(v == "active" for v in active.values()) and stable
          and boot_clean and not cs_traceback)

    print(f"services active: {active}")
    print(f"NRestarts: before={before_restarts} after_start={after_start_restarts} "
          f"after_verify={after_verify_restarts} (stable={stable})")
    print(f"broker mode on the box: {broker_mode} (reconcile required: {reconcile_required})")
    print(f"boot verification: {seen}, cloud-signal traceback: {cs_traceback}")

    print("snapshotting box config (post-deploy)...")
    post_dir, _, post_diff = box_config_snapshot.take_snapshot_from_box(label="post-deploy")
    print(f"  -> {post_dir}")
    if post_diff:
        print(post_diff)

    _log(f"DEPLOY {'OK' if ok else 'VERIFY-FAILED'} target={target} active={active} "
         f"stable={stable} broker_mode={broker_mode} serving={seen['serving']} "
         f"lease={seen['lease']} reconcile_ok={seen['reconcile_ok']} "
         f"reconcile_fail={seen['reconcile_fail']} traceback={seen['traceback']} "
         f"cs_traceback={cs_traceback}")

    if not ok:
        print("VERIFY FAILED -- the box is on the new commit but did not come up clean. "
              "Check the logs by hand before trusting it; consider re-running "
              "box_deploy.py --commit <previous sha> --yes to roll back.")
        return 2
    print("DEPLOY OK.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
