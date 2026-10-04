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
  * coverage under 80% -> ONE push. While it persists, at most one reminder per 2 hours.
  * recovery: coverage 95% or better over the last 15 minutes (at least 30 traded bars) after an
    alert -> one "back" message, and the latch clears.
Only the file tail is read (a seek from the end), because the files are 30 MB and growing.

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
REPEAT_S = 2 * 3600
TAIL_BYTES = 262144           # ~3,000 rows, about 8 hours of bars
TITLE = "EDGELOG 10S ORDER FLOW"


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


def _hhmm(ts):
    return dt.datetime.fromtimestamp(ts, ET).strftime("%H:%M")


def _since(rows, now_ts):
    """(ET 'HH:MM' where the current unclassified stretch started, is_lower_bound). Walks back from
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
    return _hhmm(first_bad - 10), not full


def evaluate(instrument, rows, now_ts, prior=None):
    """Pure. -> (new state dict, message or None). `prior` is this instrument's earlier state:
    {"alerted": bool, "last_push": epoch, "since_ts": epoch}."""
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
        msg = ("10s capture: buy/sell volume is back on %s (%d%% of bars classified over the last 15 min"
               % (instrument, round(cov15)))
        msg += (", missing from %s ET)" % _hhmm(since)) if since else ")"
        msg += " - order-flow data is valid again, but bars from the gap stay unusable."
        state.update({"alerted": False, "since_ts": None, "state": "recovered"})
        return state, msg
    if cov30 < ALERT_BELOW_PCT and not (n15 >= MIN_BARS and cov15 >= RECOVER_AT_PCT):
        start, lower = _since(rows, now_ts)
        state["state"] = "bad"
        due = (not alerted) or (now_ts - last_push >= REPEAT_S)
        if not alerted:
            state["since_ts"] = _start_ts(rows, now_ts)
        if due:
            msg = ("10s capture: buy/sell volume missing on %d%% of %s bars in the last 30 min"
                   % (miss30, instrument))
            if start:
                msg += " (since %s%s ET)" % ("at least " if lower else "", start)
            msg += " - order-flow data is invalid until it recovers"
            nt = sum(1 for r in traded if not r[2])
            if nt and sum(1 for r in traded if r[3] == 3) * 2 >= nt:
                msg += ". Bars are arriving with no trade ticks, typical after the PC sleeps or the data connection drops"
            msg += "."
            state.update({"alerted": True, "last_push": now_ts})
            return state, msg
    return state, None


def _start_ts(rows, now_ts):
    """Epoch where the current unclassified stretch began (start of its first bar)."""
    first_bad = None
    for r in reversed([r for r in rows if r[1] > 0 and r[0] <= now_ts + 60]):
        if r[2]:
            break
        first_bad = r[0]
    return (first_bad - 10) if first_bad is not None else now_ts - 10


def check(now_ts, prior_block, push, instruments=("NQ", "ES"), rows_for=None):
    """Run every instrument. `push(message, title)` is called once per alert/recovery. `rows_for`
    overrides the file read (tests). Returns the new "delta_feed" block to store (a dict keyed by
    instrument). Never raises."""
    prior_block = prior_block or {}
    out = {}
    for inst in instruments:
        try:
            rows = rows_for(inst) if rows_for else newest_rows(inst)
            st, msg = evaluate(inst, rows, now_ts, prior_block.get(inst))
            if msg:
                try:
                    push(msg, TITLE)
                except Exception:
                    pass
            out[inst] = st
        except Exception as e:
            out[inst] = dict(prior_block.get(inst) or {}, state="error", error=type(e).__name__)
    return out
