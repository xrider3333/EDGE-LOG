"""Data-quality gate (Backtesting Stack pill 2.2; ROADMAP #24) — structural asserts
on OHLCV masters. Streamlit-free, numpy/pandas only.

Two-layer design (the statistical layer — IsolationForest / inverse-PCA — is pill 2.3,
not here). This module is the HARD layer: impossible-data checks that should never fire
on a healthy file:

  • bad_hl        high < low
  • bad_range     open/close outside [low, high]
  • nonpos_price  a price <= 0  (FAIL on non-adjusted sources; WARN on adjusted ones,
                  where deep-history back-adjustment can legitimately push levels low)
  • neg_volume    volume < 0
  • dup_ts        duplicate timestamps
  • unsorted_ts   timestamps not strictly increasing
  • session_gaps  intra-day holes > 1.5x the bar interval (excluding the 18:00 ET
                  futures-maintenance reopen) — WARN, not FAIL (halts happen)

Cadence (per the stack): structural_report() on the fresh frame at EVERY pull
(milliseconds — it only sees the new rows); check_master_cached() for the whole-master
scan, cached by file mtime+size so it only recomputes when the master actually changed.
"""
import json
import os
import re
import time

import numpy as np
import pandas as pd

from .paths import UPLOADS

_TF = {"s": 1, "m": 60, "h": 3600, "d": 86400}
CACHE_FILE = "_data_health.json"


def tf_seconds(tf):
    """'5m' -> 300, '10s' -> 10, '1h' -> 3600, '1d' -> 86400; None if unparseable."""
    m = re.match(r"(\d+)\s*([smhd])", str(tf or "").strip().lower())
    return int(m.group(1)) * _TF[m.group(2)] if m else None


def _is_adjusted(source):
    """Back-adjusted continuous data may legitimately carry tiny/negative deep-history
    prices; non-adjusted (noadj / NT / TV / yahoo raw) must not. Treat only explicit
    'noadj'/'nt_' sources as raw; anything else gets the benefit of the doubt."""
    s = str(source or "").lower()
    return not ("noadj" in s or s.startswith("nt_"))


def structural_report(df, timeframe=None, source=None, session=None, max_examples=3):
    """Vectorized impossible-data checks on an OHLCV frame with a unix-sec 'time' col.
    Returns {rows, checks:{...}, gaps:[iso strings], verdict, notes:[...]}."""
    n = int(len(df))
    out = {"rows": n, "checks": {}, "gaps": [], "notes": [], "verdict": "PASS"}
    if n == 0:
        out["notes"].append("empty frame")
        return out
    o = df["open"].to_numpy(float) if "open" in df else None
    h = df["high"].to_numpy(float) if "high" in df else None
    l = df["low"].to_numpy(float) if "low" in df else None
    c = df["close"].to_numpy(float) if "close" in df else None
    t = df["time"].to_numpy("int64") if "time" in df else None
    v = df["volume"].to_numpy(float) if "volume" in df.columns else None

    ck = out["checks"]
    if h is not None and l is not None:
        ck["bad_hl"] = int((h < l).sum())
    if all(x is not None for x in (o, h, l, c)):
        ck["bad_range"] = int(((o > h) | (o < l) | (c > h) | (c < l)).sum())
    if all(x is not None for x in (o, h, l, c)):
        ck["nonpos_price"] = int(((o <= 0) | (h <= 0) | (l <= 0) | (c <= 0)).sum())
    if v is not None:
        ck["neg_volume"] = int((v < 0).sum())
    if t is not None:
        dt = np.diff(t)
        ck["unsorted_ts"] = int((dt < 0).sum())
        ck["dup_ts"] = int((dt == 0).sum())

    # intra-day session gaps: holes within one ET calendar day, excluding resumes at
    # exactly 18:00 ET (the futures maintenance-break reopen).
    #   RTH >= 1m bars: hole > 1.5x the bar interval (liquid session -> a missing bar
    #                   is a real anomaly; this is what catches the 2020 COVID halts).
    #   ETH or sub-1m:  hole >= 2h only — no-trade bars are routine in thin overnight
    #                   liquidity (2010-era 1m ETH has tens of thousands), and old-era
    #                   CME schedule breaks (<=1h) aren't data errors either.
    # Verdict impact: gaps only WARN when RECENT (within ~30 days of the data's end,
    # i.e. still fixable / a live-collector problem). Historical halts stay visible in
    # the card but don't permanently tarnish the badge.
    secs = tf_seconds(timeframe)
    if t is not None and secs and n > 1:
        et = pd.to_datetime(pd.Series(t), unit="s", utc=True).dt.tz_convert("US/Eastern")
        thin = ("eth" in str(session or "").lower()) or (secs < 60)
        thresh = max(7200, 1.5 * secs) if thin else 1.5 * secs
        same_day = et.dt.date.values[1:] == et.dt.date.values[:-1]
        dt = np.diff(t)
        hole = same_day & (dt > thresh)
        resume = et.iloc[1:][hole]
        real = resume[~((resume.dt.hour == 18) & (resume.dt.minute == 0))]
        ck["session_gaps"] = int(len(real))
        out["gaps"] = [x.strftime("%Y-%m-%d %H:%M") for x in real.head(max_examples)]
        if len(real):
            recent_cut = et.iloc[-1] - pd.Timedelta(days=30)
            ck["recent_gaps"] = int((real >= recent_cut).sum())

    hard = (ck.get("bad_hl", 0) + ck.get("bad_range", 0) + ck.get("neg_volume", 0)
            + ck.get("dup_ts", 0) + ck.get("unsorted_ts", 0))
    npp = ck.get("nonpos_price", 0)
    if npp:
        if _is_adjusted(source):
            out["notes"].append(f"{npp} non-positive price bar(s) — likely back-adjustment artifact; "
                                "don't trust $-levels / log-returns that deep in history")
        else:
            hard += npp
            out["notes"].append(f"{npp} non-positive price bar(s) on NON-adjusted data — corrupt import?")
    if hard > 0:
        out["verdict"] = "FAIL"
    elif ck.get("recent_gaps", 0) > 0 or npp:
        out["verdict"] = "WARN"
    return out


def check_master(master, uploads=None):
    """Full-file structural scan of one master registry row -> report dict."""
    uploads = uploads or UPLOADS
    path = os.path.join(uploads, master["filename"])
    st = os.stat(path)
    df = pd.read_csv(path, usecols=lambda col: col in
                     ("time", "open", "high", "low", "close", "volume"))
    rep = structural_report(df, timeframe=master.get("timeframe"),
                            source=master.get("source"), session=master.get("session"))
    rep.update({"checked_at": time.time(),
                "file_mtime": st.st_mtime, "file_size": st.st_size})
    return rep


def check_master_cached(master, uploads=None):
    """check_master() with an mtime+size cache (augur_uploads/_data_health.json), so
    the whole-master scan only re-runs when the CSV actually changed. Never raises —
    a failure comes back as {'verdict':'ERROR', 'notes':[...]}."""
    uploads = uploads or UPLOADS
    cpath = os.path.join(uploads, CACHE_FILE)
    try:
        cache = json.load(open(cpath, encoding="utf-8"))
    except Exception:
        cache = {}
    fn = master.get("filename")
    try:
        st = os.stat(os.path.join(uploads, fn))
        hit = cache.get(fn)
        if hit and hit.get("file_mtime") == st.st_mtime and hit.get("file_size") == st.st_size:
            return hit
        rep = check_master(master, uploads)
        cache[fn] = rep
        try:
            with open(cpath, "w", encoding="utf-8") as fh:
                json.dump(cache, fh)
        except OSError:
            pass
        return rep
    except Exception as e:
        return {"verdict": "ERROR", "notes": [f"{type(e).__name__}: {e}"], "checks": {}}


def health_summary(master, uploads=None):
    """Compact per-master health blob for the runner's meta sync (small for Firestore):
    verdict + only the non-zero check counts + first gap examples."""
    rep = check_master_cached(master, uploads)
    return {"verdict": rep.get("verdict"),
            "bad": {k: v for k, v in (rep.get("checks") or {}).items() if v},
            "gaps": (rep.get("gaps") or [])[:3],
            "notes": (rep.get("notes") or [])[:2],
            "checked_at": rep.get("checked_at")}
