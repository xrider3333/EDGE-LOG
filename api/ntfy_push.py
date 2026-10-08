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

api/qqq_exec.py's single POST (_ntfy_post) IS push_result() below since the WEBULL PUSH PLAN
10-07 (MANAGER #86), and so is api/cloud_signal.py's KEEL fallback push (until then a raw POST
to a hard-coded https://ntfy.sh/<topic> that ignored NTFY_TOKEN / NTFY_SERVER). Both send every
HIGH or URGENT push through this module's Outbox (below) -- see PERSISTED OUTBOX.

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
  push_result(...) is the same call returning (ok, detail): ok is True / False, or None
  when NTFY_TOPIC is unset (nothing to send to); detail is "HTTP 200" or "<Error>: <text>".
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
GitHub Actions dead-man's switches tools/nt_cloud_watchdog.py and tools/qqq_deadman.py), and the
pushes added with the executor outbox / KEEL-vs-FIXED work in api/cloud_signal.py (KEEL size
differs, prices stopped / on the backup source) and api/qqq_exec.py (re-price failed), and --
WEBULL PUSH PLAN 10-07 (MANAGER #86) -- EVERY push of api/qqq_exec.py (its _say(): plain() +
dedupe per problem; ~10 benign or other-owner sites keep only their log line and timeline
event) and api/cloud_signal.py's KEEL fallback push (now only for a REAL fallback to 1.0).
NOT yet: deploy/cloud/healthcheck.sh (off on the box) -- so the lock screen always reads the
same way:

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
  ONE OWNER PER PROBLEM: "NQ data did not reach the box" is pushed ONLY by
  tools/webull_freshness.py's nq_master check (tools/keel_live_state.py keeps its log line and
  its nq_stale_alert.json marker, which the monitor reads; the PC sweep keeps it in its JSON
  and inbox). "Webull not flat after the close": api/qqq_exec.py pushes the RESULT of its own
  check, tools/webull_freshness.py only "the check did not run". The signal-engine stall is
  tools/webull_freshness.py's (engine_hb); api/qqq_exec.py logs it on its timeline.
  "today's close was not settled" (end-of-day exits recorded late) is
  pushed ONLY by tools/webull_freshness.py's eod_settled check; api/cloud_signal.py records the
  give-up and api/qqq_exec.py logs the board event, neither pushes it. Order-flow completeness
  (the buy/sell split of the 10-second bars) is pushed ONLY by api/delta_alarm.py; the morning
  readiness check and the 30-minute sweep keep those items in their JSON / inbox / printed
  reports and leave them out of the phone push.
  dedupe() is the shared repeat rule: the same problem set pushes once, then at most once a
  day while unchanged; a NEW or WORSE problem pushes at once; when everything clears, ONE low
  priority "back to normal" goes out, but only if that episode had a high priority push.
  dedupe_in(store, key, current, now_ts) is the same rule for a caller that keeps several
  independent problems in one JSON dict ({key: dedupe state}); it updates `store` in place.
  lint() returns what is wrong with a note (title length, three lines, banned words) -- the
  tests use it; callers never need it.

PERSISTED OUTBOX (sweep 2026-10-05, finding 16: "every alert, including URGENT 'BROKER NOT
FLAT', is a single 4 s POST with the result ignored -- silence looks the same as delivery").
Outbox(path, sender) is a small queue on disk for the pushes that must not be lost:
  * send() tries once, right away, exactly like a plain push. Delivered -> one log line
    "push sent (<priority>, HTTP 200)". Failed -> the push is written to the outbox file and
    one log line says so; send() returns "queued". While older pushes are still waiting
    (ntfy was unreachable a moment ago) a new one is queued behind them WITHOUT a try, so a
    caller on a 5 s tick never waits on a network that just failed.
  * A background thread (one per outbox, started only while something is queued) retries,
    oldest first, spaced 30 s, 60 s, 2 min, 5 min, then every 10 min. A failed try holds
    every other queued push until the next spacing, so a dead network is never hammered;
    a NEW push lifts that hold (ntfy may be back). One log line per push when it finally
    goes ("delivered on try N, M min late") or is given up ("dropped after N tries").
  * Bounded: at most 50 waiting (the oldest non-urgent one is dropped first, logged), and a
    push older than 12 h is dropped (logged). A late push says when it was raised.
  * A push ntfy refuses for ITSELF (HTTP 4xx other than 401/403/404/408/425/429 -- e.g. 400 a
    bad header, 413 too large; permanent_reject) can never go: it is dropped with one log line
    instead of holding every later push behind it (send() returns "rejected"). 401/403/404
    are the topic or token, the same for every push: those stay queued for a fixed config.
  * Survives a restart: the file is rewritten after every change; resume() at start-up
    picks it up and starts the retry thread.
Only HIGH and URGENT pushes use it (is_durable); routine pushes stay a single try.
"""
import datetime as _dt
import json
import os
import re
import threading
import time
import urllib.error
import urllib.request
import uuid

try:
    from zoneinfo import ZoneInfo
    LOCAL_TZ = ZoneInfo("America/Phoenix")        # the owner's clock: MST all year, no DST
except Exception:                                  # tzdata missing -> the same fixed offset
    LOCAL_TZ = _dt.timezone(_dt.timedelta(hours=-7))


def push(message, title=None, priority=None, timeout=8, log=None):
    """POST one ntfy notification. See module docstring for the full contract."""
    ok, _detail = push_result(message, title=title, priority=priority, timeout=timeout, log=log)
    return bool(ok)


def push_result(message, title=None, priority=None, timeout=8, log=None):
    """push() returning (ok, detail) -- ok None when NTFY_TOPIC is unset. Never raises."""
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
        return None, "NTFY_TOPIC unset"

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
            status = resp.status
            return 200 <= status < 300, f"HTTP {status}"
    except Exception as e:
        _log(f"ntfy push failed: {type(e).__name__}: {e}")
        return False, f"{type(e).__name__}: {e}"


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


def with_article(word):
    """'ORB' -> 'an ORB', 'ENGU-Q' -> 'an ENGU-Q', 'NOISE' -> 'a NOISE' (each said as a word);
    text that already starts with 'a ' / 'an ' is returned as it is."""
    w = str(word or "").strip()
    if not w or w.lower().startswith(("a ", "an ")):
        return w or "a"
    return ("an " if w[0].upper() in "AEIOU" else "a ") + w


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


def dedupe_in(store, key, current, now_ts, repeat_s=DAY_S):
    """dedupe() for one of several independent problems kept in one dict -> the action (None |
    "push" | "clear"). `store` ({key: dedupe state}) is updated in place; the caller persists it.
    `current` is {problem_id: rank} as for dedupe(), {} when this problem is clear."""
    if not isinstance(store, dict):
        return None
    action, new = dedupe(current, store.get(key) or {}, now_ts, repeat_s=repeat_s)
    if new.get("set") or new.get("high"):
        store[key] = new
    else:
        store.pop(key, None)
    return action


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


# -- PERSISTED OUTBOX (finding 16) -- see the module docstring ---------------------------------
DURABLE_PRIORITIES = ("high", "urgent", "max", "4", "5")
URGENT_PRIORITIES = ("urgent", "max", "5")
OUTBOX_MAX_ITEMS = 50
OUTBOX_MAX_AGE_SEC = 12 * 3600.0
OUTBOX_RETRY_SPACING_SEC = (30.0, 60.0, 120.0, 300.0, 600.0)   # then every 600 s
OUTBOX_MAX_SENDS_PER_PASS = 5
OUTBOX_WORKER_MAX_WAIT_SEC = 600.0
# 4xx answers that are NOT about the one push: auth / topic (the same for every push -- keep
# the queue for a fixed config) and the throttles (retry later)
OUTBOX_RETRYABLE_4XX = (401, 403, 404, 408, 425, 429)
_HTTP_STATUS_RE = re.compile(r"\bHTTP(?: Error)? (\d{3})\b")


def is_durable(priority):
    """True for the priorities that go through an Outbox (HIGH and URGENT)."""
    return str(priority or "").strip().lower() in DURABLE_PRIORITIES


def permanent_reject(detail):
    """True when a sender's failure detail is an HTTP 4xx about the push itself ("HTTP 400",
    "HTTPError: HTTP Error 413: ...") -- a retry of the same push cannot succeed."""
    m = _HTTP_STATUS_RE.search(str(detail or ""))
    if not m:
        return False
    code = int(m.group(1))
    return 400 <= code < 500 and code not in OUTBOX_RETRYABLE_4XX


def _fmt_age(sec):
    sec = max(0.0, float(sec))
    if sec < 120:
        return f"{sec:.0f}s"
    if sec < 7200:
        return f"{sec / 60:.0f} min"
    return f"{sec / 3600:.1f} h"


def sent_late(msg, created_epoch, now_epoch=None):
    """A push delivered late says when it was raised, on the owner's clock: a plain() note gets
    "(Sent late - raised at HH:MM.)" on its problem line, so it still passes lint(); any other
    text gets a "(late: raised HH:MM)" prefix -- the same clock, never ET."""
    lines = str(msg).split("\n")
    if len(lines) == 3 and lines[0].startswith("Trading: "):
        lines[1] = "%s (Sent late - raised at %s.)" % (lines[1], hhmm(created_epoch, now=now_epoch))
        return "\n".join(lines)
    return f"(late: raised {hhmm(created_epoch, now=now_epoch)}) {msg}"


class Outbox:
    """A persisted queue of HIGH/URGENT pushes with spaced retries -- see the module docstring.

    `sender(message, title, priority)` makes ONE try and returns (ok, detail) -- ok True
    delivered, False failed, None "not configured" (no topic: dropped, nothing to retry) --
    or a plain bool. `tag` prefixes every log line ("[<tag>] ntfy ..."). `background=False`
    (tests) never starts the retry thread: call flush() yourself. `clock` is the time source.
    Thread-safe; never raises out of send(), flush(), resume() or kick()."""

    def __init__(self, path, sender, tag="ntfy", background=True, clock=None, log=None,
                 max_items=OUTBOX_MAX_ITEMS, max_age_sec=OUTBOX_MAX_AGE_SEC,
                 spacing=OUTBOX_RETRY_SPACING_SEC):
        self.path = path
        self._sender = sender
        self.tag = tag
        self.background = bool(background)
        self._clock = clock or time.time
        self._log = log
        self.max_items = int(max_items)
        self.max_age_sec = float(max_age_sec)
        self.spacing = tuple(float(s) for s in spacing) or (60.0,)
        self._lock = threading.RLock()
        self._items = None            # loaded from disk on first use
        self._hold_until = 0.0        # after a failed try: nothing goes before this
        self._wake = threading.Event()
        self._thread = None

    # -- small helpers ---------------------------------------------------------------------
    def set_log(self, log):
        if log is not None:
            self._log = log

    def _emit(self, text):
        try:
            (self._log or print)(f"[{self.tag}] ntfy {text}")
        except Exception:
            pass

    def _retry_gap(self, attempts):
        return self.spacing[min(max(int(attempts), 1) - 1, len(self.spacing) - 1)]

    def _call(self, message, title, priority):
        try:
            r = self._sender(message, title, priority)
        except Exception as e:
            return False, f"{type(e).__name__}: {e}"
        if isinstance(r, tuple):
            return r[0], (r[1] if len(r) > 1 else "")
        if r is None:
            return None, "not configured"
        return bool(r), ("sent" if r else "failed")

    def _load_locked(self):
        if self._items is None:
            items = []
            try:
                with open(self.path, encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, list):
                    items = [i for i in data if isinstance(i, dict) and "message" in i]
            except FileNotFoundError:
                pass
            except (OSError, ValueError) as e:
                self._emit(f"outbox file unreadable ({type(e).__name__}) -- starting empty")
            # A row whose times or try count are not numbers (a hand-edited or foreign file)
            # would make every later pass and every new send fail: drop it, one line.
            good, bad = [], 0
            for it in items:
                try:
                    it["created_epoch"] = float(it.get("created_epoch"))
                    it["next_try_epoch"] = float(it.get("next_try_epoch") or 0.0)
                    it["attempts"] = int(it.get("attempts") or 0)
                    it["message"] = str(it["message"])
                    good.append(it)
                except (TypeError, ValueError):
                    bad += 1
            if bad:
                self._emit(f"outbox file had {bad} unreadable push(es) -- dropped them")
            self._items = good
        return self._items

    def _save_locked(self):
        try:
            d = os.path.dirname(self.path)
            if d:
                os.makedirs(d, exist_ok=True)
            tmp = f"{self.path}.{os.getpid()}.{threading.get_ident()}.tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self._items or [], f, indent=1)
            for i in range(5):          # a reader holding the file for a moment (Windows)
                try:
                    os.replace(tmp, self.path)
                    return True
                except PermissionError:
                    if i == 4:
                        raise
                    time.sleep(0.05)
        except Exception as e:
            self._emit(f"outbox could not be saved ({type(e).__name__}: {e})")
        return False

    def _expire_locked(self, now):
        items = self._load_locked()
        keep = []
        for it in items:
            age = now - float(it.get("created_epoch", now))
            if age > self.max_age_sec:
                self._emit(f"push dropped after {int(it.get('attempts') or 0)} tries over "
                           f"{_fmt_age(age)} (last error: {it.get('last_error') or 'n/a'}): "
                           f"{it.get('title')}")
            else:
                keep.append(it)
        changed = len(keep) != len(items)
        items[:] = keep
        return changed

    # -- public ----------------------------------------------------------------------------
    def pending(self):
        with self._lock:
            return [dict(i) for i in self._load_locked()]

    def next_due(self):
        """Epoch of the next retry, or None when nothing is waiting."""
        with self._lock:
            items = self._load_locked()
            if not items:
                return None
            return max(min(float(i.get("next_try_epoch") or 0.0) for i in items),
                       self._hold_until)

    def send(self, message, title, priority, log=None):
        """Deliver now or keep for retry. Returns True (delivered), "queued" (kept in the
        outbox), "rejected" (ntfy refused this push itself -- permanent_reject -- not kept), or
        None (sender not configured -- nothing to retry). Never raises."""
        self.set_log(log)
        try:
            now = self._clock()
            with self._lock:
                waiting = len(self._load_locked())
            if waiting:
                self._enqueue(message, title, priority, now, attempts=0,
                              why=f"{waiting} earlier push(es) still waiting")
                return "queued"
            ok, detail = self._call(message, title, priority)
            if ok is None:
                return None
            if ok:
                self._emit(f"push sent ({priority}, {detail}): {title}")
                return True
            if permanent_reject(detail):
                self._emit(f"push refused by ntfy ({detail}) -- a retry cannot help, not "
                           f"kept: {title}")
                return "rejected"
            self._enqueue(message, title, priority, now, attempts=1, why=detail)
            return "queued"
        except Exception as e:
            self._emit(f"outbox send failed ({type(e).__name__}: {e}): {title}")
            return False

    def _enqueue(self, message, title, priority, now, attempts, why):
        with self._lock:
            items = self._load_locked()
            self._expire_locked(now)
            while len(items) >= self.max_items:
                drop = next((i for i in items
                             if str(i.get("priority") or "").lower() not in URGENT_PRIORITIES),
                            items[0])
                items.remove(drop)
                self._emit(f"outbox full ({self.max_items}) -- dropped the oldest waiting push: "
                           f"{drop.get('title')}")
            gap = self._retry_gap(attempts) if attempts else 0.0
            # uuid4, not "<ms>-<len(items)>": a flush that removes an item and an enqueue in the
            # same millisecond could repeat an id, and flush() matches items by id
            items.append({"id": uuid.uuid4().hex, "title": title,
                          "message": message, "priority": priority, "created_epoch": now,
                          "attempts": int(attempts), "next_try_epoch": now + gap,
                          "last_error": why})
            if not attempts:
                self._hold_until = 0.0      # a new push: worth one try now, ntfy may be back
            self._save_locked()
            n = len(items)
        if attempts:
            self._emit(f"push failed ({why}) -- kept in the outbox, next try in "
                       f"{_fmt_age(gap)} ({n} waiting): {title}")
        else:
            self._emit(f"push queued behind {n - 1} undelivered push(es): {title}")
        self.kick()

    def flush(self, now=None, max_sends=OUTBOX_MAX_SENDS_PER_PASS):
        """One retry pass: send what is due, oldest first; the first failure ends the pass
        and holds the rest until its next try -- except a push ntfy refuses for itself
        (permanent_reject), which is dropped and the pass goes on. Returns (sent,
        still_waiting). Never raises."""
        sent = 0
        try:
            now = self._clock() if now is None else float(now)
            with self._lock:
                if self._expire_locked(now):
                    self._save_locked()
                items = self._load_locked()
                if now < self._hold_until:
                    return 0, len(items)
                due = sorted((i for i in items if float(i.get("next_try_epoch") or 0) <= now),
                             key=lambda i: float(i.get("created_epoch") or 0))[:max_sends]
            for it in due:
                late = now - float(it.get("created_epoch") or now)
                msg = it["message"]
                if it.get("attempts") or late >= 60:
                    msg = sent_late(msg, it["created_epoch"], now)
                ok, detail = self._call(msg, it.get("title"), it.get("priority"))
                with self._lock:
                    items = self._load_locked()
                    cur = next((i for i in items if i.get("id") == it.get("id")), None)
                    if cur is None:
                        continue
                    if ok is None:
                        items.remove(cur)
                        self._save_locked()
                        self._emit(f"push dropped ({detail}, nothing to send to): "
                                   f"{cur.get('title')}")
                        continue
                    if ok:
                        items.remove(cur)
                        self._save_locked()
                        sent += 1
                        self._emit(f"push delivered on try {int(cur.get('attempts') or 0) + 1} "
                                   f"({detail}), {_fmt_age(late)} late: {cur.get('title')}")
                        continue
                    if permanent_reject(detail):
                        # one bad push must not hold every later HIGH/URGENT one for 12 h
                        items.remove(cur)
                        self._save_locked()
                        self._emit(f"push dropped -- ntfy refused it ({detail}), a retry cannot "
                                   f"help: {cur.get('title')}")
                        continue
                    cur["attempts"] = int(cur.get("attempts") or 0) + 1
                    cur["last_error"] = detail
                    cur["next_try_epoch"] = now + self._retry_gap(cur["attempts"])
                    self._hold_until = cur["next_try_epoch"]
                    self._save_locked()
                break
            with self._lock:
                return sent, len(self._load_locked())
        except Exception as e:
            self._emit(f"outbox pass failed ({type(e).__name__}: {e})")
            return sent, None

    def kick(self):
        """Wake (or start) the retry thread when this outbox runs one. Never raises."""
        if not self.background:
            return
        try:
            with self._lock:
                self._wake.set()
                if self._thread is not None and self._thread.is_alive():
                    return
                t = threading.Thread(target=self._run, name=f"{self.tag}-ntfy-outbox",
                                     daemon=True)
                self._thread = t
            t.start()
        except Exception as e:
            self._emit(f"outbox retry thread could not start ({type(e).__name__}: {e})")

    def _run(self):
        while True:
            self._wake.clear()
            self.flush()
            with self._lock:
                nd = self.next_due()
                if nd is None:
                    self._thread = None
                    return
            wait = min(max(nd - self._clock(), 0.5), OUTBOX_WORKER_MAX_WAIT_SEC)
            self._wake.wait(wait)

    def resume(self, log=None):
        """Start-up: pick up pushes left from before a restart. Returns how many wait."""
        self.set_log(log)
        try:
            with self._lock:
                n = len(self._load_locked())
            if n:
                self._emit(f"{n} undelivered push(es) kept from before the restart -- retrying")
                self.kick()
            return n
        except Exception as e:
            self._emit(f"outbox resume failed ({type(e).__name__}: {e})")
            return 0
