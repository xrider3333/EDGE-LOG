"""market_news.py -- the PRE-MARKET and AFTER-HOURS stock news blocks of the B7 morning digest
(owner 10-28, MANAGER #222). FREE SOURCES ONLY, no login, no key:
  - moves:     yfinance 5m bars with pre/post hours (Yahoo): pre = today's pre-market vs the last close,
               after-hours = the last session's after-hours vs its close
  - headlines: Yahoo Finance's public RSS feed per symbol (feeds.finance.yahoo.com/rss/2.0/headline)
Universe: the Nasdaq-100 as of the newest month in tools/data/ndx_members_wikipedia.json, plus QQQ.

Every number here is quoted straight from Yahoo; nothing is a model's opinion. Never raises:
a failed source gives a block that says what failed.
"""
import json
import os
import re
import urllib.request
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
NDX_FILE = os.path.join(HERE, "data", "ndx_members_wikipedia.json")
RSS = "https://feeds.finance.yahoo.com/rss/2.0/headline?s={sym}&region=US&lang=en-US"
UA = {"User-Agent": "Mozilla/5.0"}
TOP = 10            # movers listed per block (5 up + 5 down)
HEADLINES = 2       # per listed mover
MIN_MOVE = 1.0      # % - smaller moves are not "movers"


def ndx_members(path=NDX_FILE):
    """The newest Nasdaq-100 list: base, then each month's adds (col 5) and drops (col 6)."""
    d = json.load(open(path, encoding="utf-8"))
    cur = set(str(d["base"]).split())
    for m in d["months"]:
        cur |= set(str(m[5] or "").split())
        cur -= set(str(m[6] or "").split())
    return sorted(cur)


def _moves(closes, today):
    """(pre, post) % for one symbol's 5m closes (New York index, pre/post bars included).
    post = the last session's last after-hours bar (16:00-20:00) vs its last regular bar;
    pre  = today's last bar before 09:30 vs the last regular bar of the session before today."""
    import datetime as _dt
    c = closes.dropna()
    if c.empty:
        return None, None
    t, d = c.index.time, c.index.date
    reg = (t >= _dt.time(9, 30)) & (t < _dt.time(16, 0))
    days = sorted(set(d[reg]))
    pre = post = None
    last = [x for x in days if x < today] if any(x == today for x in d) else days
    if last:
        s = last[-1]
        rc = c[reg & (d == s)]
        ah = c[(d == s) & (t >= _dt.time(16, 0))]
        if len(rc) and len(ah):
            post = (ah.iloc[-1] / rc.iloc[-1] - 1) * 100
        pm = c[(d == today) & (t < _dt.time(9, 30))]
        if len(rc) and len(pm) and today > s:
            pre = (pm.iloc[-1] / rc.iloc[-1] - 1) * 100
    return pre, post


def quotes(symbols, yf=None, today=None):
    """{sym: {pre, post, name}} from ONE yfinance download of 5 days of 5m bars with pre/post
    hours (the after-hours figure Yahoo's quote clears at 04:00 ET is rebuilt from the bars)."""
    import datetime as _dt
    if yf is None:
        import yfinance as yf
    try:
        df = yf.download(" ".join(symbols), period="5d", interval="5m", prepost=True,
                         progress=False, group_by="ticker", auto_adjust=False, threads=True)
    except Exception:
        return {}
    if df is None or df.empty:
        return {}
    try:
        df.index = df.index.tz_convert("America/New_York")
    except Exception:
        pass
    if today is None:
        from zoneinfo import ZoneInfo
        today = _dt.datetime.now(ZoneInfo("America/New_York")).date()
    out = {}
    for s in symbols:
        try:
            pre, post = _moves(df[s]["Close"], today)
        except Exception:
            continue
        if pre is not None or post is not None:
            out[s] = {"pre": pre, "post": post, "name": s}
    return out


def headlines(sym, n=HEADLINES, fetch=None):
    try:
        if fetch:
            xml = fetch(RSS.format(sym=sym))
        else:
            req = urllib.request.Request(RSS.format(sym=sym), headers=UA)
            with urllib.request.urlopen(req, timeout=15) as r:
                raw = r.read()
            try:
                xml = raw.decode("utf-8")
            except UnicodeDecodeError:
                xml = raw.decode("cp1252", "replace")     # Yahoo's feed sometimes sends cp1252 quotes
        items = ET.fromstring(xml).findall("./channel/item")
        return [re.sub(r"\s+", " ", (it.findtext("title") or "")).strip() for it in items[:n]
                if (it.findtext("title") or "").strip()]
    except Exception:
        return []


def movers(q, key, top=TOP, floor=MIN_MOVE):
    rows = [(s, v[key]) for s, v in q.items() if isinstance(v.get(key), (int, float)) and abs(v[key]) >= floor]
    up = sorted((r for r in rows if r[1] > 0), key=lambda r: -r[1])[:top // 2]
    dn = sorted((r for r in rows if r[1] < 0), key=lambda r: r[1])[:top // 2]
    return up + dn


def block(title, q, key, empty_note, fetch=None):
    L = [f"## {title}"]
    rows = movers(q, key)
    if not q:
        return L + ["- not available: the Yahoo quote pull failed", ""]
    if not rows:
        return L + [f"- {empty_note}", ""]
    for s, pct in rows:
        L.append(f"- **{s}** {pct:+.1f}%")
        for h in headlines(s, fetch=fetch):
            L.append(f"  - {h}")
    return L + [""]


def news_blocks(symbols=None, yf=None, fetch=None):
    """Lines for the digest: PRE-MARKET block then AFTER-HOURS block."""
    try:
        symbols = symbols or (ndx_members() + ["QQQ"])
    except Exception:
        return ["## Pre-market news", "- not available: Nasdaq-100 list unreadable", "",
                "## After-hours news (last evening)", "- not available", ""]
    q = quotes(symbols, yf=yf)
    L = [f"Moves are Yahoo's figures for the Nasdaq-100 + QQQ ({len(q)} of {len(symbols)} quoted), "
         f"moves of {MIN_MOVE:.0f}% or more; headlines from Yahoo Finance RSS.", ""]
    L += block("Pre-market news", q, "pre", "no pre-market move of 1% or more yet (Yahoo's pre-market starts 04:00 ET)", fetch)
    L += block("After-hours news (last evening)", q, "post",
               "no after-hours figure (Yahoo clears it once its pre-market starts) or no move of 1% or more", fetch)
    return L
