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


def _boundary_gaps(df, timeframe=None):
    """SESSION-boundary close->open gaps in POINTS, keyed by the resume bar's unix ts:
    {'ts': [...], 'p': [point gaps], 'c': [prev closes]}.

    Boundary = wall-clock jump >= max(30 min, 3x bar). Calendar-date breaks are NOT
    used because the ETH session's real break (17:00->18:00 ET) sits INSIDE one
    calendar date — date-keying makes mid-week rolls invisible on ETH masters.
    Points (not %) on purpose: back-adjustment shifts the price LEVEL of a whole
    segment, so at a non-roll boundary the adjusted and raw point-gaps are IDENTICAL —
    their diff isolates pure roll spread. Keying by exact ts aligns siblings 1:1
    (adj / no-adj twins share the same bar grid)."""
    if df is None or len(df) < 2 or "time" not in df:
        return {"ts": [], "p": [], "c": []}
    t = df["time"].to_numpy("int64")
    o = df["open"].to_numpy(float)
    c = df["close"].to_numpy(float)
    secs = tf_seconds(timeframe) or 300
    # boundaries = wall-clock holes (session breaks / weekends) UNION UTC-day
    # crossings: the stitcher's volume-dominance roll is keyed by UTC day
    # (sec // 86400), so on ETH masters the contract switch is a MID-SESSION
    # bar-to-bar seam at 20:00/19:00 ET with no time hole at all.
    hole = np.diff(t) >= max(1800, 3 * secs)
    utc_day = (t // 86400)
    bnd = np.flatnonzero(hole | (np.diff(utc_day) != 0))
    if not len(bnd):
        return {"ts": [], "p": [], "c": []}
    p = o[bnd + 1] - c[bnd]
    ok = np.isfinite(p)
    return {"ts": [int(x) for x, k in zip(t[bnd + 1], ok) if k],
            "p": [round(float(x), 4) for x, k in zip(p, ok) if k],
            "c": [round(float(x), 4) for x, k in zip(c[bnd], ok) if k]}


def _find_sibling(master, masters=None):
    """The adj<->no-adj counterpart of a master (same instrument/timeframe/session,
    opposite adjustment class). Prefers the db_noadj_* twin for adjusted masters."""
    if masters is None:
        from .data import list_masters
        masters = list_masters()
    # Pair only true stitch twins: the adjusted stitch output <-> 'db_noadj_*' (raw
    # stitch output). The adjusted side's registered source varies by ingest path
    # (tv / yahoo / merged), so classify by exclusion: adjusted = anything that isn't
    # db_noadj_* or nt_*. Twins share the SAME bar set by construction, so row-count
    # parity (±0.5%) is the real gate — it rejects cross-feed impostors like the
    # small true-Yahoo 1m pulls, whose grids/prices would produce junk diffs.
    _is_raw = lambda s: s.startswith("db_noadj_") or s.startswith("nt_")
    src = str(master.get("source", ""))
    if src.startswith("nt_"):
        return None                                        # NT 10s feed has no stitch twin
    want = (lambda s: not _is_raw(s)) if src.startswith("db_noadj_") else _is_raw
    rows0 = float(master.get("rows") or 0)
    cand = [m for m in masters
            if str(m.get("instrument")) == str(master.get("instrument"))
            and str(m.get("timeframe")) == str(master.get("timeframe"))
            and str(m.get("session", "")).lower() == str(master.get("session", "")).lower()
            and m.get("filename") != master.get("filename")
            and want(str(m.get("source", "")))
            and rows0 and abs(float(m.get("rows") or 0) - rows0) <= 0.005 * rows0]
    return cand[0] if cand else None


def roll_seam_check(master, rep, uploads=None, max_examples=6):
    """Roll-seam / adjustment check (stack pill 2.6) — PAIRED design.

    ES/NQ roll quarterly; stitch_noadj keeps the raw front-month (a price JUMP lives
    at each roll boundary) while stitch_databento Panama-adjusts those jumps away.
    A single series can't separate roll spread from a real news gap (COVID overnights
    and weekend reopens land in roll windows too), so we DIFF the day-boundary gaps
    of the adj/no-adj SIBLINGS: market movement cancels, roll spread remains.

      seam:   |gap_noadj - gap_adj| > max(4 x robust scale of the diff, 0.15%)
              inside a quarterly roll window (Mar/Jun/Sep/Dec, day 1-25)
      no-adj master -> seams reported (expected; overnight PnL across one is fake)
      adjusted master -> rolls_removed + a MISSING-QUARTER scan: a quarter in range
              with no detected seam = a roll the adjustment may have missed -> WARN
              when >25% of quarters are missing (systematic failure).
    Masters without a stitch twin (e.g. the NT 10s feed) just record their class.
    """
    bg = rep.get("_bg") or {}
    adjusted = _is_adjusted(master.get("source"))
    out = {"adjusted": adjusted, "paired_with": None, "seams": None,
           "seam_dates": [], "max_spread_pct": None, "missing_quarters": []}
    sib = _find_sibling(master)
    if sib is None or not bg.get("ts"):
        return out
    sib_rep = check_master_cached(sib, uploads)          # cached -> cheap after 1st scan
    sbg = sib_rep.get("_bg") or {}
    if not sbg.get("ts"):
        return out
    out["paired_with"] = sib.get("name")
    sg = dict(zip(sbg["ts"], sbg["p"]))
    common = [(ts, p, sg[ts], c) for ts, p, c in zip(bg["ts"], bg["p"], bg["c"]) if ts in sg]
    if len(common) < 8:
        return out
    dd = np.array([abs(a - b) for _, a, b, _ in common])        # |points diff| = roll spread
    cc = np.array([c for _, _, _, c in common], float)
    px = float(np.median(cc)) or 1.0                             # typical price (reporting)
    mad = float(np.median(np.abs(dd - np.median(dd)))) or 1e-9
    # per-boundary floor (0.05% of THAT boundary's price): prices grow ~10x over the
    # span, so a global floor sized for late-era prices swallows early-era spreads.
    thresh = np.maximum(4 * 1.4826 * mad, 0.0005 * np.abs(cc))
    dts = pd.to_datetime(pd.Series([ts for ts, _, _, _ in common]), unit="s",
                         utc=True).dt.tz_convert("US/Eastern")
    in_win = dts.dt.month.isin([3, 6, 9, 12]).values & (dts.dt.day.values >= 1) & (dts.dt.day.values <= 25)
    seam = in_win & (dd > thresh)
    idx = np.flatnonzero(seam)
    out["seams"] = int(len(idx))
    out["seam_dates"] = [dts.iloc[i].strftime("%Y-%m-%d") for i in idx[:max_examples]]
    if len(idx):
        out["max_spread_pct"] = round(float((dd[idx] / px).max()) * 100, 2)
    # missing-quarter scan: every quarter spanned should contain >=1 seam.
    if len(common) > 60:                                  # only meaningful on long spans
        yq = list(zip(dts.dt.year.values, (dts.dt.month.values + 2) // 3))
        q = sorted(set(yq))
        hit = {yq[i] for i in idx}
        miss = [f"{y}Q{n}" for y, n in q if (y, n) not in hit]
        out["n_quarters"] = len(q)
        out["n_missing"] = len(miss)                       # FULL count (list below is capped)
        out["missing_quarters"] = miss[:8]
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
    # boundary gaps stored for the PAIRED roll-seam check (pill 2.6). Rolls themselves
    # are computed in health_summary() so sibling lookups can't recurse.
    rep["_bg"] = _boundary_gaps(df, timeframe=master.get("timeframe"))
    rep.update({"_v": 6, "checked_at": time.time(),
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
        if (hit and hit.get("file_mtime") == st.st_mtime
                and hit.get("file_size") == st.st_size and hit.get("_v") == 6):
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
    verdict = rep.get("verdict")
    notes = list((rep.get("notes") or []))
    try:
        rolls = roll_seam_check(master, rep, uploads)
    except Exception:
        rolls = {"adjusted": _is_adjusted(master.get("source")), "seams": None}
    nq = rolls.get("n_quarters") or 0
    miss = rolls.get("missing_quarters") or []
    n_miss = rolls.get("n_missing", len(miss))
    if rolls.get("seams"):
        if rolls.get("adjusted"):
            notes.append(f"{rolls['seams']} quarterly rolls adjusted away "
                         f"(max spread {rolls.get('max_spread_pct')}% vs raw sibling)")
        else:
            notes.append(f"{rolls['seams']} roll seams (raw front-month, e.g. "
                         f"{', '.join(rolls.get('seam_dates', [])[:2])}) — overnight PnL "
                         "across a seam is roll spread, not a real move")
    if rolls.get("adjusted") and nq >= 8 and n_miss > 0.25 * nq:
        notes.append(f"adjustment may have MISSED rolls — no seam found in "
                     f"{n_miss}/{nq} quarters (e.g. {', '.join(miss[:3])})")
        if verdict == "PASS":
            verdict = "WARN"
    return {"verdict": verdict,
            "bad": {k: v for k, v in (rep.get("checks") or {}).items() if v},
            "gaps": (rep.get("gaps") or [])[:3],
            "notes": notes[:3],
            "adj": ("adj" if rolls.get("adjusted") else "no-adj"),
            "seams": rolls.get("seams"),
            "checked_at": rep.get("checked_at")}
