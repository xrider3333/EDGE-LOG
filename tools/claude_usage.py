"""Claude token usage per chat per day (board B14) and a status-line meter (board B15).

Reads every ~/.claude/projects/*/*.jsonl transcript, counts each assistant message once (by message id), and writes a
daily table per session to C:/EdgeLog/manager/usage.md.

  python tools/claude_usage.py                 # write usage.md (last 14 days)
  python tools/claude_usage.py --days 30
  python tools/claude_usage.py --statusline    # read the status-line JSON on stdin, print one short line:
                                               #   "Fable 72% | this chat $0.40 | $4.10 today | 7d avg $3.6"
"""
import collections, datetime as dt, glob, json, os, sys

PROJECTS = os.path.join(os.path.expanduser("~"), ".claude", "projects")
OUT = r"C:\EdgeLog\manager\usage.md"
CACHE = r"C:\EdgeLog\manager\usage_cache.json"
# Owner-set daily budget for the meter, in output-weighted tokens; edit here, never in settings.
DAILY_BUDGET = int(os.environ.get("EL_USAGE_BUDGET", "40000000"))
# $ per million tokens (input, output, cache write, cache read) by model id, most specific first.
# Source: claude-api skill price table (cached 2026-10-06) + the usual 1.25x write / 0.1x read cache rule;
# Fable 5.x cache read $0.25, Opus 5.5 / Sonnet 5.x $0.20 per the skill notes. VERIFY against
# platform.claude.com/pricing when prices change. Subscription chats are not billed per token;
# the $ shows relative cost, not an invoice.
PRICES = [
    ("fable-5", (10, 50, 12.5, 0.25)),
    ("mythos-5", (10, 50, 12.5, 0.25)),
    ("opus-5-5", (4, 20, 5, 0.2)),
    ("opus-5", (5, 25, 6.25, 0.5)),
    ("opus-4", (5, 25, 6.25, 0.5)),
    ("opus", (5, 25, 6.25, 0.5)),
    ("sonnet-5", (2, 10, 2.5, 0.2)),
    ("sonnet-4", (3, 15, 3.75, 0.3)),
    ("sonnet", (3, 15, 3.75, 0.3)),
    ("haiku-5-5", (0.1, 0.5, 0.125, 0.01)),
    ("haiku-4", (1, 5, 1.25, 0.1)),
    ("haiku", (1, 5, 1.25, 0.1)),
]
DEFAULT_PRICE = PRICES[2][1]  # unknown model id -> priced as Opus 5.5 (the default model)


def price_for(model):
    m = (model or "").lower()
    return next((v for k, v in PRICES if k in m), DEFAULT_PRICE)


def dollars(model, u):
    p = price_for(model)
    return ((u.get("input_tokens") or 0) * p[0] + (u.get("output_tokens") or 0) * p[1] +
            (u.get("cache_creation_input_tokens") or 0) * p[2] + (u.get("cache_read_input_tokens") or 0) * p[3]) / 1e6


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
            u = dict(u, _usd=dollars(m.get("model"), u))
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
            c["usd_c"] += round(u["_usd"] * 100, 4)
        sid = os.path.splitext(os.path.basename(p))[0]
        titles[sid] = scan_file.title or sid[:8]
    return rows, titles


def fmt(n):
    return "%.1fM" % (n / 1e6) if n >= 1e6 else "%.0fk" % (n / 1e3)


def usd(c):
    return c.get("usd_c", 0) / 100


SPARK = " .:-=+*#%@"


def vs_avg(today, avg):
    """'+37%' / '-12%' / 'n/a' - today's $ against the 7-day average."""
    if avg <= 0:
        return "n/a"
    d = 100 * (today - avg) / avg
    return "%+.0f%%" % d


def trend(vals):
    hi = max(vals) or 1
    return "".join(SPARK[min(9, int(9 * v / hi + 0.999))] if v else "_" for v in vals)


def write_md(days):
    rows, titles = collect(max(days, 7))
    by_day = collections.defaultdict(list)
    for (day, sid), c in rows.items():
        by_day[day].append((sid, c))
    out = ["# Claude usage per chat", "",
           "Written by tools/claude_usage.py at %s. Tokens per session per day; cache read is cheap, output is dear." %
           dt.datetime.now().strftime("%Y-%m-%d %H:%M"),
           "$ = API list-price estimate (PRICES in the script, per model id - verify when prices change); subscription chats are not billed per token.", ""]
    week = [(dt.date.today() - dt.timedelta(days=i)).isoformat() for i in range(6, -1, -1)]
    per = collections.defaultdict(lambda: [0.0] * 7)
    for (day, sid), c in rows.items():
        if day in week:
            per[sid][week.index(day)] += usd(c)
    reps = collections.Counter()
    outs = collections.Counter()
    for (day, sid), c in rows.items():
        if day in week:
            reps[sid] += c["msgs"]
            outs[sid] += c["out"]
    out += ["## Last 7 days (%s .. %s)" % (week[0], week[-1]), "",
            "7d avg = the 7 days' $ / 7. Today vs avg: + means dearer than usual. Out/reply = output tokens per reply.", "",
            "| Chat | 7-day $ | 7d avg $ | Today $ | Today vs avg | Replies | Out/reply | Trend (old -> today) |",
            "|---|---|---|---|---|---|---|---|"]
    for sid, v in sorted(per.items(), key=lambda x: -sum(x[1])):
        out.append("| %s | $%.2f | $%.2f | $%.2f | %s | %d | %s | `%s` |" % (
            titles.get(sid, sid[:8]).replace("|", "/"), sum(v), sum(v) / 7, v[-1], vs_avg(v[-1], sum(v) / 7),
            reps[sid], "%d" % (outs[sid] / max(1, reps[sid])), trend(v)))
    daytot = [sum(v[i] for v in per.values()) for i in range(7)]
    out += ["| **ALL** | **$%.2f** | **$%.2f** | **$%.2f** | %s | %d | %s | `%s` |" % (
        sum(daytot), sum(daytot) / 7, daytot[-1], vs_avg(daytot[-1], sum(daytot) / 7), sum(reps.values()),
        "%d" % (sum(outs.values()) / max(1, sum(reps.values()))), trend(daytot)), ""]
    totals = {}
    for day in sorted(by_day, reverse=True):
        lst = sorted(by_day[day], key=lambda x: -(x[1]["out"] + x[1]["cache_w"]))
        tot = sum((c for _, c in lst), collections.Counter())
        totals[day] = dict(tot)
        out += ["## %s - $%.2f, %s out, %s cache write, %s cache read, %d replies" %
                (day, usd(tot), fmt(tot["out"]), fmt(tot["cache_w"]), fmt(tot["cache_r"]), tot["msgs"]), "",
                "| Chat | $ | Replies | Input | Output | Cache write | Cache read |", "|---|---|---|---|---|---|---|"]
        for sid, c in lst:
            out.append("| %s | $%.2f | %d | %s | %s | %s | %s |" % (titles.get(sid, sid[:8]).replace("|", "/"), usd(c), c["msgs"],
                       fmt(c["in"]), fmt(c["out"]), fmt(c["cache_w"]), fmt(c["cache_r"])))
        out.append("")
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write("\n".join(out))
    with open(CACHE, "w", encoding="utf-8") as f:
        json.dump({"at": dt.datetime.now().timestamp(), "days": totals, "week_usd": daytot}, f)
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
    day, week = {}, []
    try:
        cache = json.load(open(CACHE, encoding="utf-8"))
        week = cache.get("week_usd") or []
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
            mine["usd_c"] += u["_usd"] * 100
    pct = 100 * weight(day) / DAILY_BUDGET if DAILY_BUDGET else 0
    model = ((info.get("model") or {}).get("display_name")) or ""
    avg = sum(week) / 7 if len(week) == 7 else 0
    print(statusline_text(model, pct, usd(mine), usd(day), avg))


def statusline_text(model, pct, mine_usd, day_usd, avg_usd):
    """One short line: '<model> 72% | this chat $0.40 | $4.10 today | 7d avg $3.6'. % = share of the daily budget."""
    return "%s%d%% | this chat $%.2f | $%.2f today | 7d avg $%.1f" % (
        (model + " ") if model else "", pct, mine_usd, day_usd, avg_usd)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    if "--statusline" in sys.argv:
        statusline()
    else:
        n = int(sys.argv[sys.argv.index("--days") + 1]) if "--days" in sys.argv else 14
        print(write_md(n))
