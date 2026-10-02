"""Per-trade candles for the REAL trade journal (HOME ledger chart).

Owner ask 2026-09-30 (via MANAGER, "go with defaults"): every real trade gets EL's own candle
chart automatically - one 1-minute chart with a 10-second close-up - and it has to open on
the phone, when the PC may be asleep. So the bars are PUBLISHED with the trade, the same way
tools/qqq_bars_publish.py publishes the Webull paper day bars: one small Firestore doc per
trade, users/{uid}/trade_bars/{tradeId}, written by the runner right after the trade syncs.
The web draws it with the shared candle renderer (index.html window.candleSVG) and falls back
to the runner's get_bars command only when no doc exists yet.

Futures only for now (MNQ/NQ -> NQ bars, MES/ES -> ES bars). Stock trades wait for the Alpaca
stock-bars loader (ELWA-FEATURES) and the owner's free key; they are recorded as 'no_source'
in the local state file and never written.

Bar sources, freshest first:
  * 10s  - the NinjaTrader capture C:\\EdgeLog\\ohlc\\{NQ,ES}_10s.csv (read through api/paper.py
           so the bar-END stamp rule lives in one place). Exists since 2026-06-23.
  * 1m   - rebuilt from that capture when it covers the window, else the no-adjust 1-minute
           24-hour master (db_noadj_eth, NOADJ_{NQ,ES}_1m_ETH.csv), read by byte-seeking the
           time-ascending file so a 300 MB master costs milliseconds, not six seconds.
Prices are NOT back-adjusted, so the fill markers sit on the candles. If a series still misses
the entry fill (a roll week: the continuous file is on the other contract month), it is shifted
by whole ticks onto the fill and the shift is stamped on the doc, so the web can say so.

Chart window (2026-10-02): the 1-minute chart spans the trade's WHOLE Globex session (18:00 ET the
evening before to 17:00 ET on the session date) so the web can pan and zoom out TradingView-style;
the 10-second close-up is the trade +/- 30 minutes. A chart is final once its bars reach the session
end (or 2 h after it, whichever comes first) - until then it is rebuilt every sweep.

SHOULD HAVE TRADED (2026-10-02): setups the owner did NOT take, users/{uid}/missed_trades/{id}, get
the same chart at users/{uid}/trade_bars/missed_{id} (the entry minute, no exit) and the same point
score, merged onto the missed_trades doc as pointScore and nothing else.

Firestore quota: nothing here lists the journal on a timer. sweep() reads only trades dated in
the last few days (a handful of docs), at most every SWEEP_EVERY seconds, plus ONE full read of
the journal per runner start; a local state file remembers what is already published. The
missed_trades collection is read once in full per runner start, then only entries whose updatedAt
is newer than the last good read (minus 10 minutes); entries still unfinished are kept in memory
and re-processed from there, so a sweep costs one billed read when nothing changed.
"""
import hashlib
import json
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone

import pandas as pd

COLLECTION = "trade_bars"
SCHEMA_V = 1
DOC_CAP_BYTES = 200_000
ET = "America/New_York"
STATE_PATH = os.environ.get("EDGELOG_TRADE_BARS_STATE", r"C:\EdgeLog\trade_bars_state.json")
FILLS_PATH = os.environ.get("EDGELOG_FILLS", r"C:\EdgeLog\fills.csv")
FUT = {"MNQ": "NQ", "NQ": "NQ", "MES": "ES", "ES": "ES"}
TICK = 0.25
SESSION_OPEN_HM, SESSION_CLOSE_HM = "18:00", "17:00"   # Globex session, ET: opens the evening before
GIVE_UP_AFTER_SESSION_SEC = 2 * 3600       # an unfinished 1-minute chart is final this long after the session end
S10_BEFORE_SEC, S10_AFTER_SEC = 1800, 1800 # the 10-second close-up: the trade +/- 30 minutes
MAX_10S = 1500                             # a long hold keeps its first and last 750 (a 1 h hold is 720 bars)
SWEEP_EVERY = 300                          # seconds between journal sweeps inside the runner
RECENT_DAYS = 3
MISSED_COLL = "missed_trades"              # SHOULD HAVE TRADED entries (written by the web app)
MISSED_PREFIX = "missed_"                  # their bars doc id is missed_<id>, never a trade id
MISSED_OVERLAP = timedelta(minutes=10)     # incremental read: updatedAt >= last good read - this
PS_RETRY_HOURS = 48                        # a point score still waiting on bars is retried this long after exit
CAPTURE_SRC = "NinjaTrader 10-second capture"

_last_sweep = {}
_full_done = set()
_missed_mem = {}                           # uid -> {missed id: trade-shaped dict} read so far
_missed_since = {}                         # uid -> UTC start time of the last good missed_trades read


# ── trade times ─────────────────────────────────────────────────────────────────────────────
def _sym(t):
    return re.sub(r"\s.*$", "", str(t.get("symbol") or "").upper().strip())


def instrument_of(t):
    return FUT.get(_sym(t))


def _et(date, hhmm):
    s = str(hhmm or "").strip()
    if not date or not re.match(r"^\d{1,2}:\d{2}(:\d{2})?$", s):
        return None
    try:
        return pd.Timestamp(f"{date} {s}", tz=ET)
    except Exception:                      # a hand-typed date that is not one, or a time that does not exist
        return None


def _session_bounds(e):
    """(start, end) in epoch seconds of the Globex session an ET time belongs to: 18:00 ET on the
    calendar day before the session date, to 17:00 ET on the session date. The session date is the
    time's own date, or the next day for a time at/after 18:00 ET (that evening's open). DST-correct:
    each end is built from its ET wall-clock, never from a fixed 23-hour offset."""
    e = e.tz_convert(ET) if e.tzinfo is not None else e.tz_localize(ET)
    day = e.date() + (timedelta(days=1) if e.hour >= 18 else timedelta(0))
    start = pd.Timestamp(f"{day - timedelta(days=1)} {SESSION_OPEN_HM}", tz=ET)
    end = pd.Timestamp(f"{day} {SESSION_CLOSE_HM}", tz=ET)
    return int(start.timestamp()), int(end.timestamp())


def _fills_index(path=FILLS_PATH):
    """ExecutionId -> UTC time and OrderId -> earliest UTC time, from the NinjaTrader AddOn's
    fills.csv. Seconds-precision times for NT trades (the journal keeps only HH:MM)."""
    ex, od = {}, {}
    if not os.path.exists(path):
        return ex, od
    try:
        f = pd.read_csv(path, dtype=str, usecols=["ExecutionId", "Time", "OrderId"])
    except Exception:
        return ex, od
    for r in f.itertuples(index=False):
        try:
            ts = pd.Timestamp(r.Time, tz="UTC").tz_convert(ET)
        except Exception:
            continue
        ex[str(r.ExecutionId)] = ts
        k = str(r.OrderId)
        if k not in od or ts < od[k]:
            od[k] = ts
    return ex, od


def trade_times(t, fills=None):
    """(entry, exit, how) as ET Timestamps. 'fills' = seconds from the broker fills file."""
    e = _et(t.get("date"), t.get("entryTime"))
    x = _et(t.get("date"), t.get("exitTime"))
    how = "journal"
    ex, od = fills or ({}, {})
    fx = ex.get(str(t.get("ntExecId") or ""))
    if fx is not None:
        fe = od.get(str(t.get("orderId") or ""))
        secs = t.get("durationSecs")
        if fe is None and secs not in (None, ""):
            fe = fx - pd.Timedelta(seconds=float(secs))
        if fe is not None and fe <= fx and (e is None or abs((fe - e).total_seconds()) < 3 * 3600):
            e, x, how = fe, fx, "fills"
    if e is None:
        return None, None, how
    if x is None or x < e:
        dur = t.get("durationSecs") or (float(t.get("durationMins") or 0) * 60)
        x = e + pd.Timedelta(seconds=float(dur or 0))
    return e, x, how


def signature(t):
    keys = ("date", "entryTime", "exitTime", "entry", "exit", "type", "symbol", "size")
    return hashlib.sha1(json.dumps([str(t.get(k)) for k in keys]).encode()).hexdigest()[:16]


# ── bars ────────────────────────────────────────────────────────────────────────────────────
def _read_10s(inst, cache):
    """The live capture as bar-START epochs (NinjaTrader stamps a 10s row at its END)."""
    if inst in cache:
        return cache[inst]
    from api import paper as _paper
    df, _path = _paper._load_fresh_ticks(inst)
    cache[inst] = df
    return df


def _master_path(inst):
    from augur_engine.data import find_master, UPLOADS
    m = find_master(inst, "1m", "eth", "db_noadj_eth")
    return (os.path.join(UPLOADS, m["filename"]), m.get("name") or m["filename"]) if m else (None, None)


def _read_window(path, t_from, t_to):
    """Rows of a time-ascending master CSV with t_from <= time <= t_to, found by bisecting
    byte offsets (one seek per step) instead of parsing the whole file."""
    size = os.path.getsize(path)
    with open(path, "rb") as f:
        header = f.readline().decode().strip().split(",")
        body0 = f.tell()

        def time_at(off):
            f.seek(off)
            if off > body0:
                f.readline()                 # finish the partial line
            line = f.readline()
            while line and not line.strip():
                line = f.readline()
            if not line:
                return None, None
            try:
                return int(float(line.split(b",", 1)[0])), f.tell() - len(line)
            except ValueError:
                return None, None

        lo, hi = body0, size
        while hi - lo > 4096:
            mid = (lo + hi) // 2
            tm, _ = time_at(mid)
            if tm is None or tm >= t_from:
                hi = mid
            else:
                lo = mid
        f.seek(lo)
        if lo > body0:
            f.readline()
        rows = []
        for raw in f:
            parts = raw.decode("utf-8", "replace").strip().split(",")
            try:
                tm = int(float(parts[0]))
            except (ValueError, IndexError):
                continue
            if tm < t_from:
                continue
            if tm > t_to:
                break
            rows.append(parts[:6])
    if not rows:
        return None
    df = pd.DataFrame(rows, columns=header[:6])
    for c in df.columns:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df.dropna().rename(columns=str.lower)


def _shift_onto_fill(df, px, t_epoch, step, span=None):
    """Whole-tick shift that puts a fill price inside its own bar (roll weeks), else 0.
    span: the fill is only known to lie somewhere in [t_epoch, t_epoch + span) - a journal
    time known to the minute (review 2026-09-30 #6: testing only the 10s bar at HH:MM:00
    'moved' charts whose real fill was 50 s later). Every bar overlapping that span counts."""
    if df is None or df.empty or px in (None, ""):
        return 0.0
    px = float(px)
    if span:
        bar = df[(df["time"] < t_epoch + span) & (df["time"] + step > t_epoch)]
    else:
        bar = df[(df["time"] <= t_epoch) & (df["time"] + step > t_epoch)]
    if bar.empty:
        return 0.0
    lo, hi = float(bar["low"].min()), float(bar["high"].max())
    if lo - 2 * TICK <= px <= hi + 2 * TICK:
        return 0.0
    return round((px - float(bar["close"].iloc[-1])) / TICK) * TICK


def _covers(df, e_s, x_s):
    """True when a 1m frame (bar-START epochs) has the entry bar and the exit bar."""
    return bool(df is not None and not df.empty and int(df["time"].iloc[0]) <= e_s
                and int(df["time"].iloc[-1]) + 60 > x_s)


def _fmt(v):
    s = f"{float(v):.2f}"
    return s.rstrip("0").rstrip(".") if "." in s else s


def _pack(df, step, shift=0.0):
    """'off,o,h,l,c,v;...' with off = (bar start - t0) / step. t0 = first bar start."""
    if df is None or df.empty:
        return None
    t0 = int(df["time"].iloc[0])
    parts = []
    for r in df.itertuples(index=False):
        parts.append(",".join((str((int(r.time) - t0) // step), _fmt(r.open + shift), _fmt(r.high + shift),
                               _fmt(r.low + shift), _fmt(r.close + shift), str(int(r.volume or 0)))))
    return {"t0": t0, "step": step, "s": ";".join(parts)}


def build(t, tid, fills=None, cache=None, now=None):
    """(doc, None) or (None, reason). Pure apart from reading local price files."""
    cache = {} if cache is None else cache
    inst = instrument_of(t)
    if not inst:
        return None, "no_source"
    e, x, how = trade_times(t, fills)
    if e is None:
        return None, "no_times"
    now = now or pd.Timestamp.now(tz=ET)
    e_s, x_s = int(e.timestamp()), int(x.timestamp())

    # 10-second close-up from the capture
    ticks = _read_10s(inst, cache)
    s10 = None
    if ticks is not None and not ticks.empty:
        st = ticks.assign(time=ticks["time"] - 10)            # bar END -> bar START
        s10 = st[(st["time"] >= e_s - S10_BEFORE_SEC) & (st["time"] <= x_s + S10_AFTER_SEC)]
        if len(s10) > MAX_10S:
            s10 = pd.concat([s10.head(MAX_10S // 2), s10.tail(MAX_10S // 2)])
        if s10.empty or s10["time"].iloc[0] > e_s:           # capture does not reach the entry
            s10 = None

    # 1-minute chart: the capture when it is fresh; otherwise whichever of capture and master
    # has the trade's own bars and reaches furthest (review 2026-09-30 #2: once the capture
    # stopped, ANY master rows in the window won, and a stale master replaced a good chart
    # with a stub that ended before the entry). The window is the trade's whole Globex session
    # (2026-10-02, so the web can zoom out); a trade held across the 17:00 break runs to the end of
    # the session it exits in.
    w0, w1 = _session_bounds(e)
    w1 = max(w1, _session_bounds(x)[1])
    need_to = min(w1, int(now.timestamp()) - 120)          # the last bar that could exist yet
    cands = []
    if ticks is not None and not ticks.empty:
        from api import paper as _paper
        win = ticks[(ticks["time"] > w0) & (ticks["time"] <= w1 + 60)]
        if not win.empty:
            cand = _paper._resample(win, 1)
            cand = cand[(cand["time"] >= w0) & (cand["time"] <= w1)].reset_index(drop=True)
            if not cand.empty:
                cands.append((cand, CAPTURE_SRC))
    fresh = bool(cands) and (int(cands[0][0]["time"].iloc[0]) <= w0 + 300
                             and int(cands[0][0]["time"].iloc[-1]) + 120 >= need_to)
    if not fresh:
        path, name = _master_path(inst)
        if path and os.path.exists(path):
            mm = _read_window(path, w0, w1)
            if mm is not None and not mm.empty:
                cands.append((mm.reset_index(drop=True), f"1-minute master {name}"))
    if not cands:
        return None, "no_bars"
    m1, m1_src = max(cands, key=lambda c: (_covers(c[0], e_s, x_s), min(int(c[0]["time"].iloc[-1]), w1),
                                           int(c[0]["time"].iloc[0]) <= w0 + 300, c[1] == CAPTURE_SRC))

    sh1 = _shift_onto_fill(m1, t.get("entry"), e_s, 60)
    sh10 = 0.0
    if s10 is not None:
        # seconds known from the broker fills -> the fill's own 10s bar; journal time known to
        # the minute only -> anywhere in that minute (review 2026-09-30 #6)
        sh10 = _shift_onto_fill(s10, t.get("entry"), e_s, 10, span=None if how == "fills" else 60)
    b1 = _pack(m1, 60, sh1)
    b10 = _pack(s10, 10, sh10) if s10 is not None else None

    # final once the 1m bars reach the session end (minus 2 minutes), or 2 h after the session end
    have_to = int(m1["time"].iloc[-1]) + 60
    complete = bool(have_to >= w1 - 120
                    or now.timestamp() >= w1 + GIVE_UP_AFTER_SESSION_SEC)
    side = "short" if str(t.get("type") or "").upper() == "SHORT" else "long"
    doc = {
        "v": SCHEMA_V, "trade_id": tid, "sym": _sym(t), "inst": inst, "side": side,
        "date": t.get("date"), "times_from": how,
        "entry": {"t": e_s, "px": t.get("entry")}, "exit": {"t": x_s, "px": t.get("exit")},
        "b1m": dict(b1, src=m1_src, shift=sh1),
        "b10s": (dict(b10, src=CAPTURE_SRC, shift=sh10) if b10 else None),
        "complete": complete, "covers": _covers(m1, e_s, x_s), "sig": signature(t),
        "published_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    if len(json.dumps(doc)) > DOC_CAP_BYTES and doc["b10s"]:
        doc["b10s"] = None                                   # the 1m chart is the one that matters
    if len(json.dumps(doc)) > DOC_CAP_BYTES:
        return None, "too_big"
    return doc, None


# ── state + sweep ──────────────────────────────────────────────────────────────────────────
def _load_state(path=STATE_PATH):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_state(state, path=STATE_PATH):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f)
    os.replace(tmp, path)


# ── POINT SCORE (owner 2026-09-30 via MANAGER; rules: docs/POINT_SCORE_SPEC.md, code: tools/point_score.py,
#    owned by DISCRECTIONALRY-TO-ALGO). Scored in the same pass as the chart, and ONLY the pointScore field is
#    merged onto the trade - setup, grade and notes are never touched.
_PS = None
_PS_MTIME = None
_PS_SRC = None
PS_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools", "point_score.py")


def _point_score_module():
    """tools/point_score.py, loaded by path and RE-loaded whenever the file changes: the runner lives
    for days, and a spec bump (ps1 -> ps1.1 on 2026-10-01) must reach it without a restart."""
    global _PS, _PS_MTIME
    try:
        mt = os.stat(PS_PATH).st_mtime_ns
    except OSError:
        mt = None
    if _PS is None or (mt is not None and mt != _PS_MTIME):
        import importlib.util
        spec = importlib.util.spec_from_file_location("point_score", PS_PATH)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _PS, _PS_MTIME = mod, mt
    return _PS


def _ps_fresh_bars(mod):
    """point_score caches each root's bars for the life of the process, and the runner lives for
    days while the masters it reads are rewritten (10s import every 15 min, Yahoo 1m every 4 h).
    Drop that cache whenever a source file changed (review 2026-09-30 #1: every live trade was
    scored against bars that ended before its signal minute and locked in as 0/0)."""
    global _PS_SRC
    cache = getattr(mod, "_BARS_CACHE", None)
    if cache is None:
        return
    try:
        up = mod.uploads_dir()
        names = sorted(set(getattr(mod, "MASTER_1M", {}).values()) | set(getattr(mod, "MASTER_10S", {}).values()))
        src = []
        for n in names:
            fp = os.path.join(up, n)
            st = os.stat(fp) if os.path.exists(fp) else None
            src.append((n, st.st_mtime_ns, st.st_size) if st else (n, None, None))
        src = (up, tuple(src))
    except Exception:
        src = None                                        # cannot tell: never trust the cache
    if src is None or src != _PS_SRC:
        cache.clear()
    _PS_SRC = src


def _ps_retry_reasons(mod):
    """NA reasons that mean 'the bars are not there YET' - worth another try while the trade is recent."""
    return {getattr(mod, k) for k in ("NA_NOBAR", "NA_NO10BAR", "NA_NO10") if hasattr(mod, k)}


def _ps_pending(rec, reasons):
    if not rec:
        return True
    if not rec.get("max"):
        return True
    pts = list(rec.get("points") or []) + ([rec["trend"]] if rec.get("trend") else [])
    return any(q.get("hit") is None and q.get("na_reason") in reasons for q in pts if isinstance(q, dict))


def point_score(t, fills=None):
    """The agreed pointScore record for a futures trade, or None (stocks wait for Alpaca bars)."""
    if not instrument_of(t):
        return None
    e, _x, how = trade_times(t, fills)
    if e is None:
        return None
    fill = e.strftime("%Y-%m-%d %H:%M:%S")
    side = "SHORT" if str(t.get("type") or "").upper() == "SHORT" else "LONG"
    mod = _point_score_module()
    _ps_fresh_bars(mod)
    rec = mod.score_trade({"sym": _sym(t), "side": side, "fill": fill})
    rec = json.loads(json.dumps(rec, default=str))       # plain JSON types for Firestore
    rec.update({"fill": fill, "fill_from": how, "sig": signature(t)})
    return rec


def _same_score(a, b):
    keys = ("total", "max", "na_count", "points", "trend", "sig", "signal_bar")
    return bool(a) and bool(b) and all(a.get(k) == b.get(k) for k in keys)


def _write_score(db, uid, coll, tid, rec):
    """Merge ONLY the pointScore field onto users/{uid}/{coll}/{tid}. A journal trade is set(merge) as
    always; a SHOULD HAVE TRADED entry is update()d, which fails (NotFound) instead of re-creating an
    entry the owner deleted since it was read - a ghost doc with only a score would show as a blank row."""
    ref = db.collection("users").document(uid).collection(coll).document(tid)
    if coll == "trades":
        ref.set({"pointScore": rec}, merge=True)
    else:
        ref.update({"pointScore": rec})


def publish(db, uid, docs, log=print, dry_run=False, force=False, state=None, fills=None, now=None,
            coll="trades", bars_prefix="", gone=None):
    """Build + write bars (and the point score) for (id, trade) pairs. Returns the number written.
    coll / bars_prefix pick the source collection and the bars doc id: the journal is
    ("trades", "") -> trade_bars/{id}; SHOULD HAVE TRADED entries are ("missed_trades", "missed_") ->
    trade_bars/missed_{id}, and their state-file key is that same bars doc id, so the two kinds of id
    can never collide. gone: optional list that collects the ids whose source doc no longer exists."""
    own_state = state is None
    state = _load_state() if own_state else state
    fills = fills if fills is not None else _fills_index()
    cache, n = {}, 0
    now = now or pd.Timestamp.now(tz=ET)
    for tid, t in docs:
        key = bars_prefix + tid                       # the bars doc id and the state-file key
        sig, st = signature(t), state.get(key) or {}
        ps_due = False
        if instrument_of(t):
            ps = t.get("pointScore") or {}
            _e, _x, _h = trade_times(t, fills)
            recent = _x is not None and now < _x + pd.Timedelta(hours=PS_RETRY_HOURS)
            # re-score while the stored score is still waiting on bars (all NA / signal minute
            # missing) and the trade is recent - not only while the chart is incomplete
            mod = _point_score_module()
            # a record from an older spec version is re-scored once (DISCRECTIONALRY-TO-ALGO 2026-10-01)
            stale_v = bool(ps) and ps.get("v") != getattr(mod, "VERSION", ps.get("v"))
            ps_due = force or ps.get("sig") != sig or stale_v or (recent and _ps_pending(ps, _ps_retry_reasons(mod)))
        if not force and st.get("sig") == sig and (st.get("complete") or st.get("skip")) and not ps_due:
            continue
        if ps_due:
            try:
                rec = point_score(t, fills)
                if rec and not _same_score(rec, t.get("pointScore")):
                    if not dry_run:
                        _write_score(db, uid, coll, tid, rec)
                        t["pointScore"] = rec         # what is stored now: the next sweep compares against it
                    log(f"  [point-score] {'(dry) ' if dry_run else ''}{key} {t.get('date')} {t.get('symbol')} "
                        f"{rec.get('total')}/{rec.get('max')}")
            except Exception as e:
                if type(e).__name__ == "NotFound" and coll != "trades":
                    log(f"  [point-score] {key}: the entry was deleted - dropped")
                    if gone is not None:
                        gone.append(tid)
                    continue
                log(f"  [point-score] {key}: {type(e).__name__}: {e}")
        if not force and st.get("sig") == sig and (st.get("complete") or st.get("skip")):
            continue
        doc, why = build(t, key, fills, cache, now)
        if doc is None:
            e, x, _ = trade_times(t, fills)
            final = why in ("no_source", "no_times") or (x is not None and now >= x + pd.Timedelta(days=2))
            state[key] = {"sig": sig, "skip": why if final else None, "err": why, "at": time.time()}
            if why != "no_source":
                log(f"  [trade-bars] {key} {t.get('date')} {t.get('symbol')}: {why}")
            continue
        if not force and st.get("sig") == sig and st.get("covers") and not doc["covers"]:
            # the published chart had the trade's bars and every source now lacks them: keep it
            log(f"  [trade-bars] {key}: kept the published chart (new bars do not cover the trade)")
            if doc["complete"]:                          # past the give-up time: the kept chart is final
                state[key] = dict(st, complete=True, at=time.time())
            continue
        if not dry_run:
            db.collection("users").document(uid).collection(COLLECTION).document(key).set(doc)
        state[key] = {"sig": sig, "complete": doc["complete"], "covers": doc["covers"], "at": time.time()}
        n += 1
        log(f"  [trade-bars] {'(dry) ' if dry_run else ''}{key} {t.get('date')} {t.get('symbol')} "
            f"1m={doc['b1m']['s'].count(';') + 1} 10s={(doc['b10s']['s'].count(';') + 1) if doc['b10s'] else 0} "
            f"complete={doc['complete']}")
    if own_state and not dry_run:
        _save_state(state)
    return n


# ── SHOULD HAVE TRADED: setups the owner did not take ───────────────────────────────────────
def _num(v):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f == f and abs(f) != float("inf") else None


def _missed_trade(d):
    """A missed_trades doc as the trade-shaped dict build() / point_score() take: the entry minute is
    both the entry and the exit (there is no exit). No price goes in: the owner's entry is a level read
    off a snapshot, not a fill, so it must never shift the chart onto "his contract month" (the roll
    shift trusts the price it is given). The web draws the entry marker from the entry doc itself."""
    return {"date": d.get("date"), "entryTime": d.get("entryTime"), "exitTime": d.get("entryTime"),
            "entry": None, "exit": None, "type": d.get("type"),
            "symbol": d.get("symbol"), "size": None, "pointScore": d.get("pointScore")}


def _sweep_missed(db, uid, log=print):
    """Publish bars + point score for the owner's SHOULD HAVE TRADED entries. Reads the collection in
    full ONCE per runner start; after that only entries whose updatedAt is newer than the last good
    read (minus MISSED_OVERLAP for clock skew and slow server timestamps). Everything already read
    stays in _missed_mem, so an entry whose chart is not complete yet, or whose score is still
    waiting on bars, is re-processed from memory with no read at all. A deleted entry just stops being
    updated: its bars doc is left alone (the web ignores orphans)."""
    coll = db.collection("users").document(uid).collection(MISSED_COLL)
    started = datetime.now(timezone.utc)
    if uid in _missed_since:
        from google.cloud.firestore_v1.base_query import FieldFilter
        snaps = coll.where(filter=FieldFilter("updatedAt", ">=", _missed_since[uid] - MISSED_OVERLAP)).stream()
    else:
        snaps = coll.stream()
    rows = [(s.id, s.to_dict() or {}) for s in snaps]
    _note_reads(max(1, len(rows)))                       # one query = at least one billed read
    _missed_since[uid] = started                         # only after the read worked
    mem = _missed_mem.setdefault(uid, {})
    for i, d in rows:
        mem[i] = _missed_trade(d)                        # an edited entry replaces its old copy
    pairs = [(i, t) for i, t in mem.items() if instrument_of(t)]
    gone = []
    n = publish(db, uid, pairs, log=log, fills=({}, {}), coll=MISSED_COLL, bars_prefix=MISSED_PREFIX, gone=gone)
    for i in gone:
        mem.pop(i, None)
    return n


def sweep(db, uid, log=print, force=False):
    """Runner hook (Runner.sync_trades): publish bars for new / changed / unfinished trades, then for
    the SHOULD HAVE TRADED entries. The first call per runner start reads the whole journal once; after
    that only trades dated in the last RECENT_DAYS, at most every SWEEP_EVERY seconds."""
    now = time.time()
    if not force and now - _last_sweep.get(uid, 0) < SWEEP_EVERY:
        return 0
    _last_sweep[uid] = now
    n, err = 0, None
    try:
        coll = db.collection("users").document(uid).collection("trades")
        if uid in _full_done:
            from google.cloud.firestore_v1.base_query import FieldFilter
            since = (pd.Timestamp.now(tz=ET) - pd.Timedelta(days=RECENT_DAYS)).strftime("%Y-%m-%d")
            snaps = coll.where(filter=FieldFilter("date", ">=", since)).stream()
        else:
            snaps = coll.stream()
        docs = [(s.id, s.to_dict() or {}) for s in snaps]
        _note_reads(max(1, len(docs)))                   # one query = at least one billed read
        _full_done.add(uid)
        n = publish(db, uid, docs, log=log)
    except Exception as e:                               # the missed entries still get their turn
        err = e
    try:
        n += _sweep_missed(db, uid, log)
    except Exception as e:
        log(f"  [trade-bars] missed entries skipped: {type(e).__name__}: {e}")
    if err is not None:
        raise err
    return n


def _note_reads(n):
    """Count the sweep's reads into the LIVE runner's [reads] meter, bucket 'other' (review
    2026-09-30 #7). The runner runs as __main__, so look it up; never import a second copy."""
    for name in ("__main__", "api.runner"):
        m = sys.modules.get(name)
        fn = getattr(m, "_note_reads", None) if m is not None else None
        if callable(fn):
            try:
                fn("other", n)
            except Exception:
                pass
            return
