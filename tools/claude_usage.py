"""Claude token usage per chat per day (board B14) and a status-line meter (board B15).

Reads every ~/.claude/projects/*/*.jsonl transcript, counts each assistant message once (by message id), and writes a
daily table per session to C:/EdgeLog/manager/usage.md.

  python tools/claude_usage.py                 # write usage.md (last 14 days)
  python tools/claude_usage.py --days 30
  python tools/claude_usage.py --statusline    # read the status-line JSON on stdin, print one meter line
"""
import collections, datetime as dt, glob, json, os, sys

PROJECTS = os.path.join(os.path.expanduser("~"), ".claude", "projects")
OUT = r"C:\EdgeLog\manager\usage.md"
CACHE = r"C:\EdgeLog\manager\usage_cache.json"
# Owner-set daily budget for the meter, in output-weighted tokens; edit here, never in settings.
DAILY_BUDGET = int(os.environ.get("EL_USAGE_BUDGET", "40000000"))


def _local_day(ts):
    try:
        return dt.datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone().strftime("%Y-%m-%d")
    except Exception:
        return None


def scan_file(path, since):
    """Yield (day, session_id, title, usage dict) once per assistant message."""
    seen, title, sid = set(), None, os.path.splitext(os.path.basename(path))[0]
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            try:
                r = json.loads(line)
            except Exception:
                continue
            t = r.get("type")
            if t in ("custom-title", "agent-name") and (r.get("customTitle") or r.get("agentName")):
                title = r.get("customTitle") or r.get("agentName")
            elif t == "user" and title is None:
                c = (r.get("message") or {}).get("content")
                if isinstance(c, str) and not c.startswith("<"):
                    title = " ".join(c.split())[:50]
            if t != "assistant":
                continue
            m = r.get("message") or {}
            u, mid = m.get("usage"), m.get("id")
            day = _local_day(r.get("timestamp") or "")
            if not u or not day or day < since or mid in seen:
                continue
            seen.add(mid)
            yield day, r.get("sessionId") or sid, u
    scan_file.title = title


def collect(days):
    since = (dt.date.today() - dt.timedelta(days=days - 1)).isoformat()
    cutoff = dt.datetime.now().timestamp() - days * 86400
    rows = collections.defaultdict(lambda: collections.Counter())
    titles = {}
    for p in glob.glob(os.path.join(PROJECTS, "*", "*.jsonl")):
        if os.path.getmtime(p) < cutoff:
            continue
        for day, sid, u in scan_file(p, since):
            c = rows[(day, sid)]
            c["in"] += u.get("input_tokens") or 0
            c["out"] += u.get("output_tokens") or 0
            c["cache_w"] += u.get("cache_creation_input_tokens") or 0
            c["cache_r"] += u.get("cache_read_input_tokens") or 0
            c["msgs"] += 1
        sid = os.path.splitext(os.path.basename(p))[0]
        titles[sid] = scan_file.title or sid[:8]
    return rows, titles


def fmt(n):
    return "%.1fM" % (n / 1e6) if n >= 1e6 else "%.0fk" % (n / 1e3)


def write_md(days):
    rows, titles = collect(days)
    by_day = collections.defaultdict(list)
    for (day, sid), c in rows.items():
        by_day[day].append((sid, c))
    out = ["# Claude usage per chat", "",
           "Written by tools/claude_usage.py at %s. Tokens per session per day; cache read is cheap, output is dear." %
           dt.datetime.now().strftime("%Y-%m-%d %H:%M"), ""]
    totals = {}
    for day in sorted(by_day, reverse=True):
        lst = sorted(by_day[day], key=lambda x: -(x[1]["out"] + x[1]["cache_w"]))
        tot = sum((c for _, c in lst), collections.Counter())
        totals[day] = dict(tot)
        out += ["## %s - %s out, %s cache write, %s cache read, %d replies" %
                (day, fmt(tot["out"]), fmt(tot["cache_w"]), fmt(tot["cache_r"]), tot["msgs"]), "",
                "| Chat | Replies | Input | Output | Cache write | Cache read |", "|---|---|---|---|---|---|"]
        for sid, c in lst:
            out.append("| %s | %d | %s | %s | %s | %s |" % (titles.get(sid, sid[:8]).replace("|", "/"), c["msgs"],
                       fmt(c["in"]), fmt(c["out"]), fmt(c["cache_w"]), fmt(c["cache_r"])))
        out.append("")
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write("\n".join(out))
    with open(CACHE, "w", encoding="utf-8") as f:
        json.dump({"at": dt.datetime.now().timestamp(), "days": totals}, f)
    return OUT


def weight(c):
    # rough cost weight: output 5x input, cache write 1.25x, cache read 0.1x
    return c.get("in", 0) + 5 * c.get("out", 0) + 1.25 * c.get("cache_w", 0) + 0.1 * c.get("cache_r", 0)


def statusline():
    try:
        info = json.load(sys.stdin)
    except Exception:
        info = {}
    today = dt.date.today().isoformat()
    day = {}
    try:
        cache = json.load(open(CACHE, encoding="utf-8"))
        day = cache["days"].get(today, {}) if dt.datetime.now().timestamp() - cache["at"] < 900 else {}
    except Exception:
        pass
    if not day:  # cache stale: scan only today's files
        rows, _ = collect(1)
        day = dict(sum((c for (d, _), c in rows.items() if d == today), collections.Counter()))
    mine = collections.Counter()
    tp = info.get("transcript_path")
    if tp and os.path.exists(tp):
        for d, _, u in scan_file(tp, today):
            mine["in"] += u.get("input_tokens") or 0
            mine["out"] += u.get("output_tokens") or 0
            mine["cache_w"] += u.get("cache_creation_input_tokens") or 0
            mine["cache_r"] += u.get("cache_read_input_tokens") or 0
    pct = 100 * weight(day) / DAILY_BUDGET if DAILY_BUDGET else 0
    bar = "#" * min(10, int(pct / 10)) + "-" * (10 - min(10, int(pct / 10)))
    model = ((info.get("model") or {}).get("display_name")) or ""
    print("%s [%s] %d%% of day | this chat %s out | all chats %s out" %
          (model, bar, pct, fmt(mine["out"]), fmt(day.get("out", 0))))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    if "--statusline" in sys.argv:
        statusline()
    else:
        n = int(sys.argv[sys.argv.index("--days") + 1]) if "--days" in sys.argv else 14
        print(write_md(n))
