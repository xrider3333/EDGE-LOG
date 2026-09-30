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

Firestore quota: nothing here lists the journal on a timer. sweep() reads only trades dated in
the last few days (a handful of docs), at most every SWEEP_EVERY seconds, plus ONE full read of
the journal per runner start; a local state file remembers what is already published.
"""
import hashlib
import json
import os
import re
import time
from datetime import datetime, timezone

import pandas as pd

COLLECTION = "trade_bars"
SCHEMA_V = 1
DOC_CAP_BYTES = 200_000
ET = "America/New_York"
STATE_PATH = os.environ.get("EDGELOG_TRADE_BARS_STATE", r"C:\EdgeLog\trade_bars_state.json")
FILLS_PATH = os.environ.get("EDGELOG_FILLS", r"C:\EdgeLog\fills.csv")
FUT = {"MNQ": "NQ", "NQ": "NQ", "MES": "ES", "ES": "ES"}
TICK = 0.25
M1_BEFORE_MIN, M1_AFTER_MIN = 90, 45       # the 1-minute chart: context around the trade
S10_BEFORE_SEC, S10_AFTER_SEC = 300, 300   # the 10-second close-up
MAX_10S = 1500                             # a long hold keeps its first and last 750
SWEEP_EVERY = 300                          # seconds between journal sweeps inside the runner
RECENT_DAYS = 3
GIVE_UP_HOURS = 6                          # an unfinished chart is final this long after exit

_last_sweep = {}
_full_done = set()


# ── trade times ─────────────────────────────────────────────────────────────────────────────
def _sym(t):
    return re.sub(r"\s.*$", "", str(t.get("symbol") or "").upper().strip())


def instrument_of(t):
    return FUT.get(_sym(t))


def _et(date, hhmm):
    s = str(hhmm or "").strip()
    if not date or not re.match(r"^\d{1,2}:\d{2}(:\d{2})?$", s):
        return None
    return pd.Timestamp(f"{date} {s}", tz=ET)


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


def _shift_onto_fill(df, px, t_epoch, step):
    """Whole-tick shift that puts a fill price inside its own bar (roll weeks), else 0."""
    if df is None or df.empty or px in (None, ""):
        return 0.0
    px = float(px)
    bar = df[(df["time"] <= t_epoch) & (df["time"] + step > t_epoch)]
    if bar.empty:
        return 0.0
    b = bar.iloc[-1]
    if b["low"] - 2 * TICK <= px <= b["high"] + 2 * TICK:
        return 0.0
    return round((px - b["close"]) / TICK) * TICK


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

    # 1-minute chart: rebuilt from the capture when it covers the window, else the master
    w0, w1 = e_s - M1_BEFORE_MIN * 60, x_s + M1_AFTER_MIN * 60
    need_to = min(w1, int(now.timestamp()) - 120)          # the last bar that could exist yet
    m1, m1_src = None, None
    if ticks is not None and not ticks.empty:
        from api import paper as _paper
        win = ticks[(ticks["time"] > w0) & (ticks["time"] <= w1 + 60)]
        if not win.empty:
            cand = _paper._resample(win, 1)
            cand = cand[(cand["time"] >= w0) & (cand["time"] <= w1)]
            if (not cand.empty and cand["time"].iloc[0] <= w0 + 300
                    and int(cand["time"].iloc[-1]) + 120 >= need_to):
                m1, m1_src = cand.reset_index(drop=True), "NinjaTrader 10-second capture"
    if m1 is None:
        # capture missing, or it stopped (NinjaTrader closed): the master, if it reaches further
        path, name = _master_path(inst)
        if path and os.path.exists(path):
            mm = _read_window(path, w0, w1)
            if mm is not None and not mm.empty:
                m1, m1_src = mm, f"1-minute master {name}"
    if m1 is None and ticks is not None and not ticks.empty:
        from api import paper as _paper
        win = ticks[(ticks["time"] > w0) & (ticks["time"] <= w1 + 60)]
        if not win.empty:
            m1 = _paper._resample(win, 1)
            m1, m1_src = m1[(m1["time"] >= w0) & (m1["time"] <= w1)].reset_index(drop=True), "NinjaTrader 10-second capture"
    if m1 is None or m1.empty:
        return None, "no_bars"

    sh1 = _shift_onto_fill(m1, t.get("entry"), e_s, 60)
    sh10 = _shift_onto_fill(s10, t.get("entry"), e_s, 10) if s10 is not None else 0.0
    b1 = _pack(m1, 60, sh1)
    b10 = _pack(s10, 10, sh10) if s10 is not None else None

    last_needed = x_s + M1_AFTER_MIN * 60
    have_to = int(m1["time"].iloc[-1]) + 60
    complete = bool(have_to >= last_needed - 120
                    or now >= x + pd.Timedelta(hours=GIVE_UP_HOURS))
    side = "short" if str(t.get("type") or "").upper() == "SHORT" else "long"
    doc = {
        "v": SCHEMA_V, "trade_id": tid, "sym": _sym(t), "inst": inst, "side": side,
        "date": t.get("date"), "times_from": how,
        "entry": {"t": e_s, "px": t.get("entry")}, "exit": {"t": x_s, "px": t.get("exit")},
        "b1m": dict(b1, src=m1_src, shift=sh1),
        "b10s": (dict(b10, src="NinjaTrader 10-second capture", shift=sh10) if b10 else None),
        "complete": complete, "sig": signature(t),
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


def _point_score_module():
    global _PS
    if _PS is None:
        import importlib.util
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        spec = importlib.util.spec_from_file_location("point_score", os.path.join(root, "tools", "point_score.py"))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _PS = mod
    return _PS


def point_score(t, fills=None):
    """The agreed pointScore record for a futures trade, or None (stocks wait for Alpaca bars)."""
    if not instrument_of(t):
        return None
    e, _x, how = trade_times(t, fills)
    if e is None:
        return None
    fill = e.strftime("%Y-%m-%d %H:%M:%S")
    side = "SHORT" if str(t.get("type") or "").upper() == "SHORT" else "LONG"
    rec = _point_score_module().score_trade({"sym": _sym(t), "side": side, "fill": fill})
    rec = json.loads(json.dumps(rec, default=str))       # plain JSON types for Firestore
    rec.update({"fill": fill, "fill_from": how, "sig": signature(t)})
    return rec


def _same_score(a, b):
    keys = ("total", "max", "na_count", "points", "trend", "sig", "signal_bar")
    return bool(a) and bool(b) and all(a.get(k) == b.get(k) for k in keys)


def publish(db, uid, docs, log=print, dry_run=False, force=False, state=None, fills=None, now=None):
    """Build + write bars (and the point score) for (tid, trade) pairs. Returns the number written."""
    own_state = state is None
    state = _load_state() if own_state else state
    fills = fills if fills is not None else _fills_index()
    cache, n = {}, 0
    now = now or pd.Timestamp.now(tz=ET)
    for tid, t in docs:
        sig, st = signature(t), state.get(tid) or {}
        have_ps = (t.get("pointScore") or {}).get("sig") == sig
        if not force and st.get("sig") == sig and (st.get("complete") or st.get("skip")) and (have_ps or not instrument_of(t)):
            continue
        if instrument_of(t) and (force or not have_ps or not st.get("complete")):
            try:
                rec = point_score(t, fills)
                if rec and not _same_score(rec, t.get("pointScore")):
                    if not dry_run:
                        db.collection("users").document(uid).collection("trades").document(tid).set(
                            {"pointScore": rec}, merge=True)
                    log(f"  [point-score] {'(dry) ' if dry_run else ''}{tid} {t.get('date')} {t.get('symbol')} "
                        f"{rec.get('total')}/{rec.get('max')}")
            except Exception as e:
                log(f"  [point-score] {tid}: {type(e).__name__}: {e}")
        if not force and st.get("sig") == sig and (st.get("complete") or st.get("skip")):
            continue
        doc, why = build(t, tid, fills, cache, now)
        if doc is None:
            e, x, _ = trade_times(t, fills)
            final = why in ("no_source", "no_times") or (x is not None and now >= x + pd.Timedelta(days=2))
            state[tid] = {"sig": sig, "skip": why if final else None, "err": why, "at": time.time()}
            if why != "no_source":
                log(f"  [trade-bars] {tid} {t.get('date')} {t.get('symbol')}: {why}")
            continue
        if not dry_run:
            db.collection("users").document(uid).collection(COLLECTION).document(tid).set(doc)
        state[tid] = {"sig": sig, "complete": doc["complete"], "at": time.time()}
        n += 1
        log(f"  [trade-bars] {'(dry) ' if dry_run else ''}{tid} {t.get('date')} {t.get('symbol')} "
            f"1m={doc['b1m']['s'].count(';') + 1} 10s={(doc['b10s']['s'].count(';') + 1) if doc['b10s'] else 0} "
            f"complete={doc['complete']}")
    if own_state and not dry_run:
        _save_state(state)
    return n


def sweep(db, uid, log=print, force=False):
    """Runner hook (Runner.sync_trades): publish bars for new / changed / unfinished trades.
    The first call per runner start reads the whole journal once; after that only trades
    dated in the last RECENT_DAYS, at most every SWEEP_EVERY seconds."""
    now = time.time()
    if not force and now - _last_sweep.get(uid, 0) < SWEEP_EVERY:
        return 0
    _last_sweep[uid] = now
    coll = db.collection("users").document(uid).collection("trades")
    if uid in _full_done:
        from google.cloud.firestore_v1.base_query import FieldFilter
        since = (pd.Timestamp.now(tz=ET) - pd.Timedelta(days=RECENT_DAYS)).strftime("%Y-%m-%d")
        snaps = coll.where(filter=FieldFilter("date", ">=", since)).stream()
    else:
        snaps = coll.stream()
    docs = [(s.id, s.to_dict() or {}) for s in snaps]
    _full_done.add(uid)
    return publish(db, uid, docs, log=log)
