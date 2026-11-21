# -*- coding: utf-8 -*-
"""NT REAL DAYS - remember each day's realized P&L of the real NinjaTrader account(s), and flag a past
day whose logged NT trades do not add up to it.

WHY (2026-11-20): the website's NT miss badge (index.html ntReconBadge) only compares TODAY's realized
P&L against today's logged trades. A real trade placed on NT web/mobile on an earlier day, never imported,
went unflagged once the day rolled over.

    record()  GET the local bridge /accounts (read only), store realized per non-sim account for the
              current CME session date (18:00 ET rolls to the next) in C:\\EdgeLog\\nt_real_days.json (last value of the day wins), and
              mirror the file to users/{uid}/meta/nt_real_days (one write, only when it changed).
              Bridge down = nothing, quietly.
    check()   for each recorded day in the last `days` (every one, even before the newest import), compare
              with the logged NinjaTrader trades of that account and NY close date (read from
              meta/trades_index: head + shards, a few docs once a day). Mismatch -> one phone push per
              (account, day, rounded realized), keyed in C:\\EdgeLog\\nt_real_days_state.json.

It never logs in, never posts to the bridge, never touches orders. CLI:
    python tools/nt_real_days.py record|check|both
"""
from __future__ import annotations

import datetime as _dt
import json
import os
import re
import sys
import tempfile
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

BRIDGE = "http://127.0.0.1:8391"
DATA_PATH = r"C:\EdgeLog\nt_real_days.json"
STATE_PATH = r"C:\EdgeLog\nt_real_days_state.json"
UID = "IO0K35JpLIcH9YK4C0pMNYUzZOM2"   # same default as api/trades_index.py
KEEP_DAYS = 45
TOL = 2.5
SIM_RE = re.compile(r"^(sim|backtest|playback|demo)", re.I)

try:
    from zoneinfo import ZoneInfo
    NY = ZoneInfo("America/New_York")
except Exception:                       # tzdata missing: EST fixed offset is close enough for a date
    NY = _dt.timezone(_dt.timedelta(hours=-5))


def session_day(now=None):
    """The CME trading session NT's RealizedProfitLoss belongs to: it resets ~18:00 ET, so a
    reading from 18:00 ET on counts for the NEXT session (Fri/Sat evening -> Monday). Stamping
    by NY calendar day let the evening reset overwrite day D with the new session's 0 (verifier 11-20)."""
    t = (now or _dt.datetime.now(NY)).astimezone(NY)
    d = t.date() + _dt.timedelta(days=1 if t.hour >= 18 else 0)
    while d.weekday() >= 5:
        d += _dt.timedelta(days=1)
    return d.isoformat()


def ny_today(now=None):
    return (now or _dt.datetime.now(NY)).astimezone(NY).date().isoformat()


def is_real(name):
    n = str(name or "")
    return bool(n) and not SIM_RE.match(n) and not n.upper().startswith("DEMO")


def bridge_accounts(timeout=5):
    """-> list of account rows, or None when the bridge does not answer. GET only."""
    try:
        with urllib.request.urlopen(BRIDGE + "/accounts", timeout=timeout) as r:
            return (json.loads(r.read().decode("utf-8")) or {}).get("accounts") or []
    except Exception:
        return None


def _load(path):
    try:
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def _save(path, data):
    d = os.path.dirname(path) or "."
    os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".nt_real_days.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=1, sort_keys=True)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def _db():
    from api.trades_index import _client
    return _client()


def mirror(data):
    """One write of the whole file to users/{uid}/meta/nt_real_days."""
    db = _db()
    db.collection("users").document(UID).collection("meta").document("nt_real_days").set(
        {"accounts": data, "updated_at": time.time()})


def record(path=DATA_PATH, now=None, log=print):
    rows = bridge_accounts()
    if rows is None:
        return False
    day = session_day(now)
    data = _load(path)
    before = json.dumps(data, sort_keys=True)
    seen = (now or _dt.datetime.now(NY)).astimezone(NY).isoformat(timespec="seconds")
    for r in rows:
        name = r.get("name")
        if not is_real(name) or r.get("realized") is None:
            continue
        try:
            realized = round(float(r["realized"]), 2)
        except (TypeError, ValueError):
            continue
        acct = data.setdefault(str(name), {})
        prev = acct.get(day)
        if prev and prev.get("realized") == realized:
            continue                       # unchanged: keep the file (and the mirror) still
        acct[day] = {"realized": realized, "seen_at": seen}
    cutoff = (_dt.date.fromisoformat(day) - _dt.timedelta(days=KEEP_DAYS)).isoformat()
    for acct in data.values():
        for d in [d for d in acct if d < cutoff]:
            del acct[d]
    if json.dumps(data, sort_keys=True) == before:
        return False
    _save(path, data)
    try:
        mirror(data)
    except Exception as e:
        log("nt_real_days: Firestore mirror failed: %s: %s" % (type(e).__name__, e))
    return True


def load_trades():
    """Every logged trade from meta/trades_index (head + its shards)."""
    from api import trades_index as ti
    db = _db()
    head = ti.read_head(db, UID) or {}
    by_id = {}
    for i in range(int(head.get("shards") or 0)):
        sh = ti._read(ti.shard_ref(db, UID, i)) or {}
        for t in sh.get("trades") or []:
            by_id[t.get("_id")] = t
    for c in sorted(head.get("recent") or [], key=lambda c: c.get("rev") or 0):
        if c.get("trade") is not None:
            by_id[c.get("id")] = c["trade"]
    return list(by_id.values())


def last_import_date(trades):
    """The newest NY close date that has any logged NinjaTrader trade."""
    ds = [str(t.get("date")) for t in trades
          if (t.get("broker") or "NinjaTrader") == "NinjaTrader" and t.get("date")]
    return max(ds) if ds else None


def mismatches(data, trades, today, days=10):
    floor = (_dt.date.fromisoformat(today) - _dt.timedelta(days=days)).isoformat()
    # Every recorded day in the window, NOT only days after the newest import: 11-19 can be
    # missing while 11-20 is logged, and that is the exact case this check exists for.
    start = floor
    out = []
    for acct, by_day in sorted(data.items()):
        if not is_real(acct):
            continue
        for day, rec in sorted(by_day.items()):
            if day < start or day >= today:
                continue
            realized = float(rec.get("realized") or 0)
            if abs(realized) <= 0.005:
                continue
            tr = [t for t in trades if (t.get("broker") or "NinjaTrader") == "NinjaTrader"
                  and str(t.get("account")) == str(acct) and t.get("date") == day]
            net = round(sum(float(t.get("pnl") or 0) for t in tr), 2)
            gross = round(sum(float(t.get("grossPnl") or t.get("pnl") or 0) for t in tr), 2)
            if tr and min(abs(realized - net), abs(realized - gross)) <= TOL:
                continue
            out.append({"account": acct, "day": day, "realized": realized, "net": net, "n": len(tr)})
    return out


def check(days=10, path=DATA_PATH, state_path=STATE_PATH, now=None, trades=None, log=print):
    data = _load(path)
    if not data:
        return []
    if trades is None:
        trades = load_trades()
    found = mismatches(data, trades, ny_today(now), days)
    state = _load(state_path)
    sent = []
    from api import ntfy_push
    for m in found:
        key = "%s|%s|%d" % (m["account"], m["day"], int(round(m["realized"])))
        if key in state:
            continue
        msg = ("NT real {a} {d}: NinjaTrader says {r:.2f} realized, the log has {n:.2f} ({c} trades)"
               " - import Position History for that day").format(
            a=m["account"], d=m["day"], r=m["realized"], n=m["net"], c=m["n"])
        try:
            ntfy_push.push(msg, title="NinjaTrader: trades not imported", priority="default")
        except Exception as e:
            log("push failed: %s" % type(e).__name__)
            continue
        state[key] = time.time()
        _save(state_path, state)
        sent.append(msg)
        log(msg)
    if sent:
        _save(state_path, state)
    return sent


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    cmd = argv[0] if argv else "both"
    if cmd not in ("record", "check", "both"):
        print("usage: nt_real_days.py record|check|both")
        return 2
    if cmd in ("record", "both"):
        print("recorded" if record() else "no change")
    if cmd in ("check", "both"):
        print("%d push(es)" % len(check()))
    return 0


if __name__ == "__main__":
    # the NT poller runs this inline: a hung Firestore call must never stall its loop (verifier 11-20)
    import os, threading
    _t = threading.Timer(90, lambda: (print("nt_real_days: timed out after 90 s"), os._exit(3)))
    _t.daemon = True
    _t.start()
    sys.exit(main())
