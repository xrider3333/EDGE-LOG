"""LIVE alarm: the NinjaTrader 10-second capture keeps writing bars but loses its buy/sell split.

WHY (2026-10-02). On 10-02 from 00:05 to 12:30 ET every NQ bar in NQ_10s.csv had volume but ZERO
buy/sell classification (rt=3: a live bar with no trade ticks seen). The PC had been put to sleep at
00:04 ET and the chart back-filled bars without ticks on wake. Bars kept flowing, so the existing
"10s feed stale" page (api/nt_heartbeat.py) stayed silent, and nothing said so until a study tripped on
it - the order-flow shadows read garbage for half a day. api/capture_health.py reports this once a day
in the nightly paper report; this is the same measurement made LIVE.

WHERE IT RUNS. api/nt_heartbeat.publish() calls check() on the runner's nt-bridge-watchdog thread
(every BRIDGE_SEC, 5 minutes), next to the existing 10s-feed-stale check. Its small state (latched
alert, last push time) rides in the same meta/nt_alert doc under "delta_feed", so a runner restart
neither forgets an open alert nor repeats it.

THE RULE (per instrument, NQ and ES, evaluated against the clock - not against the file's last bar).
  * window = the last 30 minutes of bars that traded (volume > 0). A bar is CLASSIFIED when
    buy_vol + sell_vol > 0 and rt != 3 (rt 3 = no trade ticks seen; the column is absent in old rows).
  * fewer than 30 traded bars in the window -> skip (market closed / halt / feed off; staleness
    belongs to the other alarm). State is held, nothing is sent.
  * coverage under 80% -> ONE push. While it persists, at most one reminder per day.
  * recovery: coverage 95% or better over the last 15 minutes (at least 30 traded bars) after an
    alert -> one "back" message, and the latch clears.
Only the file tail is read (a seek from the end), because the files are 30 MB and growing.

PHONE TEXT (2026-10-07, "make the notifications simpler to understand"). This is the ONLY alerter
that pushes order-flow completeness: tools/nt_readiness.py and tools/nt8_freshness_sweep.py keep
the same gap in their JSON / inbox reports but no longer push it (8 of the owner's 10 pushes in
90 minutes on 10-07 were this one gap, reported by three tools). The text follows the one plain
format of api/ntfy_push.py (plain()): title "Order flow: data gap" / "Order flow: OK", then
"Trading: not affected." (the buy/sell split feeds shadow studies only, never a trade), the
problem with one number, and "Do: nothing". Priority low (no buzz). Times are the owner's clock
(Phoenix), not ET. NQ and ES in the same pass share ONE push.

Everything here is exception-proof by contract: a watchdog must never take down the watch loop.
"""
import datetime as dt
import os
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
PATHS = {
    "NQ": (r"C:\EdgeLog\ohlc_addon\NQ_10s.csv", r"C:\EdgeLog\ohlc\NQ_10s.csv"),
    "ES": (r"C:\EdgeLog\ohlc_addon\ES_10s.csv", r"C:\EdgeLog\ohlc\ES_10s.csv"),
}
WINDOW_S = 30 * 60
RECOVER_WINDOW_S = 15 * 60
MIN_BARS = 30                 # traded bars needed in a window before it says anything
ALERT_BELOW_PCT = 80.0
RECOVER_AT_PCT = 95.0
REPEAT_S = 24 * 3600          # while the gap stands: one reminder a day, not one every 2 hours
TAIL_BYTES = 262144           # ~3,000 rows, about 8 hours of bars
AREA = "Order flow"


def read_tail(path, nbytes=TAIL_BYTES):
    """Rows (time, volume, classified, rt) from the end of the file, oldest first. Never raises
    on a missing/torn file (returns [])."""
    try:
        with open(path, "rb") as fh:
            fh.seek(0, 2)
            size = fh.tell()
            fh.seek(max(0, size - nbytes))
            raw = fh.read()
        if size > nbytes:
            raw = raw.split(b"\n", 1)[-1]          # drop the partial first line
        rows = []
        for ln in raw.decode("utf-8", "replace").splitlines():
            p = ln.split(",")
            if len(p) < 9:
                continue                              # header or a torn final line
            try:
                t = float(p[0])
                vol = float(p[5])
                bs = float(p[7] or 0) + float(p[8] or 0)
            except ValueError:
                continue
            try:
                rt = int(float(p[10])) if len(p) > 10 and p[10].strip() else None
            except ValueError:
                rt = None
            rows.append((t, vol, bs > 0 and rt != 3, rt))
        return rows
    except Exception:
        return []


def newest_rows(instrument, paths=None):
    """Tail rows of the fresher of the instrument's file copies (addon / watch folder)."""
    best = []
    for p in (paths or PATHS[instrument]):
        if not os.path.exists(p):
            continue
        rows = read_tail(p)
        if rows and (not best or rows[-1][0] > best[-1][0]):
            best = rows
    return best


def _cov(rows, now_ts, window_s):
    """(traded bars, classified bars) among rows inside (now - window, now]."""
    lo = now_ts - window_s
    traded = [r for r in rows if lo < r[0] <= now_ts + 60 and r[1] > 0]
    return len(traded), sum(1 for r in traded if r[2]), traded


def _hhmm(ts, now_ts=None):
    """The owner's local clock (Phoenix) as 'HH:MM' ('yesterday 21:11' for last night's start)."""
    from api import ntfy_push
    return ntfy_push.hhmm(ts, now=now_ts)


def _since(rows, now_ts):
    """(local 'HH:MM' where the current unclassified stretch started, is_lower_bound). Walks back from
    the newest traded bar to the last classified one; if the tail holds none, the start is only a
    lower bound."""
    traded = [r for r in rows if r[1] > 0 and r[0] <= now_ts + 60]
    first_bad = None
    for r in reversed(traded):
        if r[2]:
            break
        first_bad = r[0]
    if first_bad is None:
        return None, False
    full = any(r[2] for r in traded)
    return _hhmm(first_bad - 10, now_ts), not full


def evaluate(instrument, rows, now_ts, prior=None):
    """Pure. -> (new state dict, event or None). `prior` is this instrument's earlier state:
    {"alerted": bool, "last_push": epoch, "since_ts": epoch}. An event is what check() turns into
    the phone note: {"kind": "missing", "inst", "have_pct", "since", "lower"} or
    {"kind": "back", "inst", "since"}."""
    prior = dict(prior or {})
    alerted = bool(prior.get("alerted"))
    last_push = float(prior.get("last_push") or 0)
    n30, ok30, traded = _cov(rows, now_ts, WINDOW_S)
    state = {"alerted": alerted, "last_push": last_push, "since_ts": prior.get("since_ts"),
             "bars": n30, "state": "skip"}
    if n30 < MIN_BARS:
        return state, None                            # closed / halt / feed off: hold, say nothing
    miss30 = round(100.0 * (n30 - ok30) / n30)
    cov30 = 100.0 * ok30 / n30
    state.update({"state": "ok", "missing_pct": miss30})
    n15, ok15, _ = _cov(rows, now_ts, RECOVER_WINDOW_S)
    cov15 = 100.0 * ok15 / n15 if n15 else 0.0
    if alerted and n15 >= MIN_BARS and cov15 >= RECOVER_AT_PCT:
        since = prior.get("since_ts")
        state.update({"alerted": False, "since_ts": None, "state": "recovered"})
        return state, {"kind": "back", "inst": instrument,
                       "since": _hhmm(since, now_ts) if since else None}
    if cov30 < ALERT_BELOW_PCT and not (n15 >= MIN_BARS and cov15 >= RECOVER_AT_PCT):
        start, lower = _since(rows, now_ts)
        state["state"] = "bad"
        due = (not alerted) or (now_ts - last_push >= REPEAT_S)
        if not alerted:
            state["since_ts"] = _start_ts(rows, now_ts)
        if due:
            state.update({"alerted": True, "last_push": now_ts})
            return state, {"kind": "missing", "inst": instrument, "have_pct": 100 - miss30,
                           "since": start, "lower": lower}
    return state, None


def _start_ts(rows, now_ts):
    """Epoch where the current unclassified stretch began (start of its first bar)."""
    first_bad = None
    for r in reversed([r for r in rows if r[1] > 0 and r[0] <= now_ts + 60]):
        if r[2]:
            break
        first_bad = r[0]
    return (first_bad - 10) if first_bad is not None else now_ts - 10


def _join(insts):
    return " and ".join(insts)


def notes_for(events, now_ts=None):
    """Plain phone notes (api/ntfy_push.plain) for one pass's events: at most one 'data gap' note
    (NQ and ES together) and one 'back' note."""
    from api import ntfy_push
    out = []
    gap = [e for e in events if e["kind"] == "missing"]
    if gap:
        have = min(e["have_pct"] for e in gap)
        starts = [e["since"] for e in gap if e.get("since")]
        since = ""
        if starts:
            since = " since %s%s" % (starts[0], " or earlier" if any(e.get("lower") for e in gap) else "")
        out.append(ntfy_push.plain(
            AREA, "data gap", None,
            "Order-flow data is missing on %s%s (%d%% of bars have it)." % (_join([e["inst"] for e in gap]), since, have),
            "nothing - it usually recovers by itself, and you get a message when it does"))
    back = [e for e in events if e["kind"] == "back"]
    if back:
        since = next((e["since"] for e in back if e.get("since")), None)
        out.append(ntfy_push.plain(
            AREA, "OK", None,
            "Order-flow data is back on %s%s; the gap stays empty." % (
                _join([e["inst"] for e in back]), " (it was missing from %s)" % since if since else ""),
            "nothing"))
    return out


def check(now_ts, prior_block, push, instruments=("NQ", "ES"), rows_for=None):
    """Run every instrument. `push(message, title, priority)` is called once per kind of event (one
    'data gap' note for NQ + ES together, one 'back' note). `rows_for` overrides the file read
    (tests). Returns the new "delta_feed" block to store (a dict keyed by instrument). Never raises."""
    prior_block = prior_block or {}
    out, events = {}, []
    for inst in instruments:
        try:
            rows = rows_for(inst) if rows_for else newest_rows(inst)
            st, ev = evaluate(inst, rows, now_ts, prior_block.get(inst))
            if ev:
                events.append(ev)
            out[inst] = st
        except Exception as e:
            out[inst] = dict(prior_block.get(inst) or {}, state="error", error=type(e).__name__)
    try:
        for note in notes_for(events, now_ts):
            try:
                push(note["message"], note["title"], note["priority"])
            except Exception:
                pass
    except Exception:
        pass
    return out
