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

THE ONE PLAIN PHONE FORMAT (2026-10-07, owner: "make the notifications simpler to understand").
On 10-07 the owner got ~10 pushes in 90 minutes, 8 of them about ONE data gap, each written for
a developer ("rt=3", "Tick Replay", "ended with code 1", account numbers, UTC). Every PC-side
alerter now builds its push with plain() below -- and, since the box-pings change the same day,
so do the box and off-PC alerters (tools/webull_freshness.py, tools/keel_live_state.py, and the
GitHub Actions dead-man's switches tools/nt_cloud_watchdog.py and tools/qqq_deadman.py). NOT yet:
api/qqq_exec.py's and api/cloud_signal.py's own pushes, and deploy/cloud/healthcheck.sh (off on
the box) -- so the lock screen always reads the same way:

    title   "<area>: <status>"   under 40 characters, e.g. "Order flow: data gap",
                                 "NinjaTrader: CHECK NOW", "Paper NT8: OK" -- no shouting, no jargon
    line 1  "Trading: not affected."   or   "Trading: AFFECTED - <what, plain>."
    line 2  the problem in plain words, at most ONE number ("... (46% of bars have it).")
    line 3  "Do: nothing."  or  "Do: <who / what>."

  Times are the owner's clock (America/Phoenix, MST, no DST) as HH:MM via hhmm(), never UTC or
  ET. Money and prices carry thousands separators (usd(), price()). Strategies and accounts
  use words (strategy_word(): "ENGU-Q", account_word(): "paper" / "your real account"), never
  codes. PRIORITY, by what the problem does to TRADING:
    high     ONLY when trading is affected (a strategy not running when it should be, a paper
             position with no stop, the automatic drawdown stop close)      -> buzzes
    default  something broke that needs a fix today but trading is fine (a failed backup,
             a paper strategy trading outside its size limit)
    low      data-only / informational / "back to normal" / fills           -> ntfy priority 2, no buzz
  ONE OWNER PER PROBLEM: order-flow completeness (the buy/sell split of the 10-second bars) is
  pushed ONLY by api/delta_alarm.py; the morning readiness check and the 30-minute sweep keep
  those items in their JSON / inbox / printed reports and leave them out of the phone push.
  dedupe() is the shared repeat rule: the same problem set pushes once, then at most once a
  day while unchanged; a NEW or WORSE problem pushes at once; when everything clears, ONE low
  priority "back to normal" goes out, but only if that episode had a high priority push.
  lint() returns what is wrong with a note (title length, three lines, banned words) -- the
  tests use it; callers never need it.
"""
import datetime as _dt
import os
import re
import time
import urllib.error
import urllib.request

try:
    from zoneinfo import ZoneInfo
    LOCAL_TZ = ZoneInfo("America/Phoenix")        # the owner's clock: MST all year, no DST
except Exception:                                  # tzdata missing -> the same fixed offset
    LOCAL_TZ = _dt.timezone(_dt.timedelta(hours=-7))


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


# ------------------------------------------------------------------------------------------
# THE ONE PLAIN PHONE FORMAT (see the module docstring) -- text builders, repeat rule, lint
# ------------------------------------------------------------------------------------------
TITLE_MAX = 39                       # "under 40 characters"
DAY_S = 24 * 3600
RANK = {"low": 0, "default": 1, "high": 2, "urgent": 3}

STRATEGY_WORDS = {"EdgeLogNOISE": "NOISE", "EdgeLogENGUQ1m": "ENGU-Q"}
ACCOUNT_WORDS = {"DEMO7240108": "paper", "1810769": "your real account"}

# words that must never reach the lock screen (lint() flags them; the tests enforce it)
BANNED = ("rt=3", "tick replay", "exit code", "pipeline", "sidecar", "no-tick", "ntfy",
          "firestore", "bridge", "watchdog")
_BANNED_RE = re.compile(r"\bDEMO\d+\b|\b\d{6,}\b|\bUTC\b|\bET\b")


def strategy_word(name):
    """'EdgeLogENGUQ1m' -> 'ENGU-Q'; an unknown 'EdgeLogFoo' -> 'Foo'."""
    name = str(name or "")
    return STRATEGY_WORDS.get(name) or (name[7:] if name.startswith("EdgeLog") and len(name) > 7 else name)


def account_word(acct):
    """'DEMO7240108' -> 'paper', '1810769' -> 'your real account', anything else -> 'another account'."""
    return ACCOUNT_WORDS.get(str(acct or ""), "another account")


def instrument_word(inst):
    """'NQ 12-26' -> 'NQ' (the contract month means nothing on a lock screen)."""
    return (str(inst or "").split() or ["?"])[0]


def usd(x):
    """946.4 -> '$946' (whole dollars, thousands separators)."""
    return "$%s" % format(abs(float(x)), ",.0f")


def price(x):
    """31477.75 -> '31,477.75'."""
    return format(float(x), ",.2f")


def to_local(when, naive_is="utc"):
    """Epoch seconds, a datetime, or 'YYYY-MM-DD HH:MM:SS' / ISO text -> an aware datetime on the
    owner's clock (None when unreadable). A naive value is read as UTC unless naive_is='local'
    (the sweep's own PC-clock datetimes are already local)."""
    try:
        if isinstance(when, (int, float)):
            return _dt.datetime.fromtimestamp(float(when), LOCAL_TZ)
        if isinstance(when, str):
            when = _dt.datetime.fromisoformat(when.strip().replace("Z", "+00:00"))
        if when.tzinfo is None:
            when = when.replace(tzinfo=LOCAL_TZ if naive_is == "local" else _dt.timezone.utc)
        return when.astimezone(LOCAL_TZ)
    except Exception:
        return None


def _now():
    return time.time()


def hhmm(when, now=None, naive_is="utc"):
    """'21:11' in the owner's local time. Adds 'yesterday' / a weekday only when the moment is on
    another calendar day AND more than 6 hours from `now` (a fill or gap from last night)."""
    t = to_local(when, naive_is)
    if t is None:
        return "??:??"
    n = to_local(now if now is not None else _now(), naive_is) or _dt.datetime.now(LOCAL_TZ)
    clock = t.strftime("%H:%M")
    if t.date() == n.date() or abs((n - t).total_seconds()) <= 6 * 3600:
        return clock
    return ("yesterday " if (n.date() - t.date()).days == 1 else t.strftime("%a ")) + clock


def _one_line(x):
    return " ".join(str(x or "").split())


def _sentence(x):
    x = _one_line(x)
    return x if (not x or x[-1] in ".!?") else x + "."


def join_problems(phrases, limit=2):
    """'A. B. +1 more' -- the first `limit` plain sentences, then a count of the rest."""
    ps = [_sentence(p) for p in phrases if _one_line(p)]
    out = " ".join(ps[:limit])
    return out + (" +%d more" % (len(ps) - limit) if len(ps) > limit else "")


def plain(area, status, trading=None, problem="", action="nothing", priority=None):
    """Build one phone note in the plain format -> {"title", "message", "priority"}.

    area      what it is about: "Order flow", "NinjaTrader", "Paper NT8", "Paper fill: ENGU-Q bought"
    status    "OK" / "data gap" / "needs a fix" / "CHECK NOW" (None -> the title is just `area`)
    trading   None = "Trading: not affected."; text starting "not affected" is used as written
              ("not affected (flat)"); any other text = "Trading: AFFECTED - <text>."
    problem   ONE plain line, at most one number
    action    "nothing", "nothing - fixes itself when NinjaTrader runs overnight", "open NinjaTrader ..."
    priority  None = high when trading is AFFECTED, else low. Pass "default" for "fix it today, trading
              is fine". The title is cut at 39 characters.
    """
    area, status = _one_line(area), _one_line(status)
    title = ("%s: %s" % (area, status) if status else area)[:TITLE_MAX].rstrip()
    t = _one_line(trading)
    affected = bool(t) and not t.lower().startswith("not affected")
    if not t:
        line1 = "Trading: not affected."
    elif affected:
        line1 = "Trading: AFFECTED - " + _sentence(t)
    else:
        line1 = "Trading: " + _sentence(t)
    lines = (line1, _sentence(problem), "Do: " + _sentence(action or "nothing"))
    return {"title": title, "message": "\n".join(lines),
            "priority": priority or ("high" if affected else "low")}


def send(note, timeout=8, log=None):
    """Push a plain() note. Goes through push() (looked up at call time, so tests that
    monkeypatch ntfy_push.push see it). Never raises, like push()."""
    return push(note["message"], title=note["title"], priority=note["priority"],
                timeout=timeout, log=log)


def dedupe(current, state, now_ts, repeat_s=DAY_S):
    """The shared repeat rule -> (action, new_state), action None | "push" | "clear".

    current   {problem_id: rank} for every problem that would be pushed right now ({} = all clear);
              rank = RANK[priority] of the push that problem would cause
    state     what the last call returned ({} at the start); callers persist it as JSON
    * a problem id that is not in the stored set, or whose rank went UP -> "push" at once
    * the same set, unchanged -> "push" again only after `repeat_s` (default one day)
    * a problem that cleared while others remain -> no push; it counts as NEW if it comes back
    * everything cleared -> "clear" ONCE, and only if some push in the episode was high priority
      (a gap that only ever sent low-priority notes does not owe the owner a "back to normal")
    new_state = {"set": {...}, "at": <epoch of the last push>, "high": <episode had a high push>}.
    """
    state = state if isinstance(state, dict) else {}
    prior = state.get("set") or {}
    if isinstance(prior, list):                                  # a bare id list from an older state file
        prior = {str(i): 1 for i in prior}
    cur = {str(k): int(v) for k, v in (current or {}).items()}
    at, high = float(state.get("at") or 0), bool(state.get("high"))
    if not cur:
        return ("clear" if (prior and high) else None), {"set": {}, "at": 0, "high": False}
    if not prior:
        high = False                                             # a fresh episode
    if any(k not in prior or v > int(prior[k]) for k, v in cur.items()) or now_ts - at >= repeat_s:
        return "push", {"set": cur, "at": now_ts, "high": high or max(cur.values()) >= RANK["high"]}
    return None, {"set": cur, "at": at, "high": high}


def lint(note):
    """What is wrong with a plain() note, as a list of short strings (empty = fine)."""
    title, msg = note.get("title") or "", note.get("message") or ""
    probs = []
    if not title or len(title) > TITLE_MAX:
        probs.append("title is empty or over %d characters" % TITLE_MAX)
    if sum(c.isalpha() for c in title) > 3 and title == title.upper():
        probs.append("title is ALL CAPS")
    lines = msg.split("\n")
    if len(lines) != 3:
        probs.append("body is %d lines, not 3" % len(lines))
    else:
        if not (lines[0].startswith("Trading: not affected") or lines[0].startswith("Trading: AFFECTED - ")):
            probs.append("line 1 is not a Trading: line")
        if not lines[2].startswith("Do: "):
            probs.append("line 3 is not a Do: line")
        if not lines[1].strip():
            probs.append("line 2 (the problem) is empty")
    low = (title + "\n" + msg).lower()
    probs += ["banned word: %s" % w for w in BANNED if w in low]
    probs += ["banned token: %s" % t for t in dict.fromkeys(m.group(0) for m in _BANNED_RE.finditer(title + "\n" + msg))]
    if note.get("priority") not in RANK:
        probs.append("priority %r is not one of %s" % (note.get("priority"), "/".join(RANK)))
    return probs


def compose(area, descs):
    """One plain note for several problems at once (the readiness check and the sweep both use it).

    descs     [{"affects": what trading loses (text) or None, "problem": one plain sentence,
                "action": what the owner does, "rank": RANK of the push this problem causes}]
    The worst problem leads: the Trading line names the first thing that is affected, the problem
    line joins the first two problems (+N more), the Do line is the worst problem's. Title status:
    "CHECK NOW" when trading is affected, "needs a fix" (rank 1), "heads up" (rank 0); priority
    high / default / low to match."""
    ds = sorted(descs, key=lambda d: -int(d.get("rank", 0)))
    affects = next((d["affects"] for d in ds if d.get("affects")), None)
    rank = max(int(d.get("rank", 0)) for d in ds)
    status = "CHECK NOW" if affects else ("needs a fix" if rank >= 1 else "heads up")
    return plain(area, status, affects, join_problems([d["problem"] for d in ds]), ds[0]["action"],
                 priority="high" if affects else ("default" if rank >= 1 else "low"))


def back_to_normal(area, what=""):
    """The one low-priority 'all clear' after a problem that had a high priority push."""
    what = _one_line(what).rstrip(".")
    return plain(area, "OK", None, "Back to normal" + (" (was: %s)." % what if what else "."), "nothing")
