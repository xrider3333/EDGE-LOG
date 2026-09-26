r"""One ntfy.sh push helper -- so a topic (and, once the owner has one, an access token)
lives in exactly one place instead of being re-typed at every call site.

WHY THIS EXISTS (WEBULL_GO_LIVE.md 1.10, 2026-09-26). Every alerter in this project
(api/nt_drawdown_alert.py, api/nt_exec_review.py, api/nt_heartbeat.py,
tools/nt_rollover.py, tools/nt_cloud_watchdog.py, api/qqq_exec.py) built its own
`https://ntfy.sh/{topic}` URL and its own urllib.request.Request. That was harmless while
the topic was public and unauthenticated, but the repo is public and the topic committed
in deploy/_run_qqq_exec.vbs and tools/_restart_runner.bat.example is readable by anyone
who clones it -- moving to a PRIVATE topic with an access token means every sender needs
the SAME two new env vars (NTFY_TOKEN, NTFY_SERVER) wired the same way, or one of them
quietly stays on the old public channel. One helper, one place to get it right.

api/qqq_exec.py is DELIBERATELY NOT switched to this helper yet -- another track is
rewriting its push function at the same time. The change the lead applies there at
integration (replacing the whole body of _notify() at api/qqq_exec.py ~622-633, which
today builds its own https://ntfy.sh/{topic} request the same way this module used to):

    def _notify(msg, title, log=print):
        from api import ntfy_push
        ntfy_push.push(msg, title=title, priority="default", timeout=4,
                        log=lambda t: log(f"[qqq-exec] {t}"))

Also still carrying the OLD literal topic and needing a manual fix at integration --
all of this is on the owner's PC, none of it on the Oracle cloud box (see
deploy/cloud/README.md's "ntfy alerts" section for the full rotation steps):
  C:\EdgeLog\_run_qqq_exec.vbs           (the PC's installed copy of the tracked .vbs)
  C:\EdgeLog\_restart_runner.bat         (the launcher tools/fleet_restart.py actually
                                           uses, not the tracked .example)
  C:\EdgeLog\_restart_runner.bat.bak-20260908 and .bak-20260908-keep
  the "EdgeLog NT futures rollover" scheduled task's command line
  the stale worktree EDGE-LOG\.claude\worktrees\intelligent-dewdney-3a903d
  this repo's own tracked deploy/_run_qqq_exec.vbs and tools/_restart_runner.bat.example
    on origin/main, until this branch merges
  git history (2 commits) -- permanent; the old topic must be assumed compromised
None of the untracked ones above live in git, so this repo's fix to the tracked files
never reaches them on their own; each needs a manual fix by hand.

CONTRACT.
  push(message, title=None, priority=None, log=None) -> bool
  Reads from the environment on every call (never cached, so a test or a restart always
  sees the current value):
    NTFY_TOPIC   required. No push is attempted without it -- returns False instead.
    NTFY_TOKEN   optional. When set, sent as 'Authorization: Bearer <token>' so the topic
                 can be private (ntfy.sh: Settings > reserve topic > create a token, or a
                 self-hosted server's own auth). Unset behaves exactly as before this
                 module existed: an unauthenticated POST to a public topic.
    NTFY_SERVER  optional, default 'https://ntfy.sh'. Lets a self-hosted ntfy server (or a
                 future account) work with no code change.
  Returns True on a 2xx response, False on anything else -- a missing topic, a timeout, a
  non-2xx status, a DNS failure. NEVER RAISES: the same contract api/qqq_exec.py's own
  _notify(msg, title, log=print) already uses, because a phone alert is a nice-to-have and
  must never be able to take down the loop that is watching real money.
  NEVER LOGS NTFY_TOPIC OR NTFY_TOKEN. `log` (default: does nothing) is called with a
  plain status line -- "NTFY_TOPIC unset, push skipped: <title>: <message>" (title part
  omitted when there is no title) or "ntfy push failed: <type>: <e>" -- that never
  contains either value; callers pass their own print with their own "[module-name] "
  prefix, exactly like every module already did inline. The no-topic case still logs
  the title/message (neither is secret) because every sender used to log its own alert
  text in that case, and losing it would be a silent behaviour change.
"""
import os
import urllib.error
import urllib.request


def push(message, title=None, priority=None, timeout=8, log=None):
    """POST one ntfy notification. See module docstring for the full contract."""
    def _log(text):
        if log is not None:
            log(text)

    # .strip() on every value read here: a launcher that builds `set NTFY_TOPIC=<val> &&
    # ...` in cmd.exe (deploy/_run_qqq_exec.vbs) leaves a trailing space on the value, and
    # a path with a trailing space is an InvalidURL to http.client -- every push from that
    # launcher failed silently until this stripped it (see tools/_restart_runner.bat.example
    # and the "EdgeLog NT futures rollover" scheduled task, which build the same way).
    topic = (os.environ.get("NTFY_TOPIC") or "").strip()
    if not topic:
        # Keep the alert text in the log line even though the push itself is skipped --
        # every sender used to log its own message text in this case (dd-alert,
        # exec-review, nt-heartbeat, rollover), so dropping it here would be a silent
        # loss of information, not just a skipped push.
        _log(f"NTFY_TOPIC unset, push skipped: {title + ': ' if title else ''}{message}")
        return False

    server = ((os.environ.get("NTFY_SERVER") or "").strip() or "https://ntfy.sh").rstrip("/")
    headers = {}
    if title:
        headers["Title"] = title
    if priority:
        headers["Priority"] = priority
    token = (os.environ.get("NTFY_TOKEN") or "").strip()
    # A never-filled-in placeholder (deploy/cloud/edgelog.env.example,
    # deploy/cloud/install.sh) must never be sent as a real bearer token -- ntfy.sh 401s
    # ANY request carrying invalid credentials, even on a public topic, so a placeholder
    # would silently break every push on a box where the owner set NTFY_TOPIC and never
    # touched the token line. Belt-and-suspenders alongside those two files now shipping
    # an empty default.
    if token and "CHANGE-ME" not in token:
        headers["Authorization"] = f"Bearer {token}"

    try:
        req = urllib.request.Request(
            f"{server}/{topic}", data=message.encode("utf-8"), headers=headers,
            method="POST")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return 200 <= resp.status < 300
    except Exception as e:
        _log(f"ntfy push failed: {type(e).__name__}: {e}")
        return False
