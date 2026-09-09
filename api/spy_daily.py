"""SPY daily-close benchmark -- backend half of the SPY-vs-account comparison.

WHY THIS EXISTS (2026-09-09). The web app used to fetch SPY's daily closes straight
from Yahoo's chart endpoint through the free corsproxy.io CORS relay, because Yahoo
itself blocks browser-origin requests. corsproxy.io now returns HTTP 403
`keyless_legacy_url` on every anonymous call, and a direct browser call to Yahoo is
CORS-blocked outright -- so the OVERVIEW rail and HOME's MORE STATS row both fell back
to an honest em dash (v73.687) rather than a fabricated number. This module restores
real data through a path the browser was never going to have: the backend already has
an Alpaca key (once the owner adds one) and a live Firestore connection, so it can pull
SPY once and let every browser tab read one small shared document instead of every
visitor hitting a live price API on every page load.

ADJUSTMENT: split-adjusted (Alpaca `adjustment=split`) -- matching what Yahoo's chart
endpoint effectively served: a price series with stock splits removed but NOT
dividend/total-return adjusted. Deliberately not "all"/dividend adjustment -- that would
silently change what "SPY return" means for every account-vs-benchmark comparison
already shipped, which is a bigger decision than a plumbing fix and is not this task's
call to make.

STORAGE: users/{uid}/meta/spy_daily, ONE document, shaped
    {updated_at, from, to, adjustment, bars: [["YYYY-MM-DD", close], ...]}
~2,700 trading days (2015-present) at 2-decimal closes serializes to well under
Firestore's 1 MiB/doc cap -- see tests/test_spy_daily.py for the measured size. One
document read per browser session, never one read per bar and never one write per bar --
this account has already burned through its 50k-reads/day Spark quota twice.

CREDENTIALS: resolved ONLY via tools/import_alpaca_stocks.load_keys() (env
ALPACA_API_KEY/ALPACA_SECRET_KEY, then augur_config.json alpaca_key/alpaca_secret, then
tools/.alpaca_keys.json) -- the exact order that module already documents and uses; this
file adds no fourth location. Nothing in this file ever prints, logs, commits, or
transmits the key or secret -- the only thing that gets written anywhere is the fetched
SPY closes.

SCHEDULING: api/runner.py's --watch loop calls maybe_run(q) every tick. Real work (one
Alpaca call + one Firestore write per allow-listed uid) happens AT MOST ONCE PER ET
CALENDAR DAY, gated by an in-memory date stamp -- the same pattern
api/etf_book_shadow.py's maybe_nightly_update uses -- and only after MIN_ET_FOR_TODAY so
the day's own daily bar has actually settled. Every other tick is a couple of cheap
comparisons; no network call, and no exception can escape into the runner's main loop.
If no Alpaca key is configured, ONE line is logged the first time this process notices,
then it goes quiet (no per-tick spam, no retry loop) until a key appears or the process
restarts.

MANUAL BACKFILL / VERIFY:
    python -m api.spy_daily --once --cred serviceAccount.json --allow-uid <uid>
forces one fetch+merge+publish immediately, bypassing the daily gate and the clock
window -- for the owner to run right after adding keys, or for verification.
"""
import os
import sys
import time
from datetime import datetime, timedelta, timezone

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from tools.import_alpaca_stocks import load_keys, fetch_bars   # noqa: E402

SYMBOL = "SPY"
META_DOC = "spy_daily"                    # users/{uid}/meta/spy_daily
BACKFILL_START = "2015-01-01"             # Alpaca's free-plan history floor
ADJUSTMENT = "split"                      # see module docstring -- never "all"/dividend
MIN_ET_FOR_TODAY = (16, 30)               # ET -- today's daily bar is trusted after this
_CHECK_FLOOR_S = 300.0                    # cheapest possible no-op re-check floor

_last_check_ts = 0.0
_last_run_date = None          # ET date string this process last completed a fetch for
_warned_missing_keys = False   # log the "add your keys" line once per process, not per tick


def _log(msg):
    print(f"[spy-daily] {msg}", flush=True)


def _et_now():
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo("America/New_York"))
    except Exception:                      # pragma: no cover -- tz db missing
        return datetime.utcnow()


# -- Firestore doc I/O -----------------------------------------------------------------
def _doc_ref(db, uid):
    return db.collection("users").document(uid).collection("meta").document(META_DOC)


def _read_existing(db, uid):
    """Returns {date_str: close} from the current doc, or {} if missing/unreadable.
    Never raises -- a bad read just means "start from an empty map"."""
    try:
        snap = _doc_ref(db, uid).get()
        data = snap.to_dict() if getattr(snap, "exists", False) else None
        out = {}
        for row in (data or {}).get("bars") or []:
            if isinstance(row, (list, tuple)) and len(row) == 2 and row[0]:
                try:
                    out[str(row[0])] = float(row[1])
                except (TypeError, ValueError):
                    continue
        return out
    except Exception as e:
        _log(f"read existing doc failed (treating as empty): {type(e).__name__}: {e}")
        return {}


def build_merged_doc(existing, new_df, adjustment=ADJUSTMENT):
    """Merge an Alpaca fetch_bars() DataFrame (time,open,high,low,close,volume) into the
    existing {date: close} map and return (doc, n_added, n_changed).

    Keyed by date, so re-merging the SAME rows twice changes nothing (idempotent) and a
    fetch window that overlaps already-stored dates never duplicates a date -- it either
    leaves it alone (unchanged close) or overwrites it (an Alpaca restatement, e.g. a
    late split/dividend correction, is allowed to win)."""
    merged = dict(existing)
    added, changed = 0, 0
    if new_df is not None and len(new_df):
        et_dates = (pd.to_datetime(new_df["time"], unit="s", utc=True)
                      .dt.tz_convert("America/New_York").dt.date)
        for d, close in zip(et_dates, new_df["close"]):
            key = d.isoformat()
            close = round(float(close), 2)
            if key not in merged:
                added += 1
            elif merged[key] != close:
                changed += 1
            merged[key] = close
    dates = sorted(merged)
    bars = [[d, merged[d]] for d in dates]
    doc = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "from": dates[0] if dates else None,
        "to": dates[-1] if dates else None,
        "adjustment": adjustment,
        "bars": bars,
    }
    return doc, added, changed


def fetch_and_merge(db, uid, key, secret, *, now=None):
    """One fetch+merge+write cycle for one uid. An incremental run only asks Alpaca for
    the stretch from the last stored date forward (full 2015-01-01 backfill only when
    the doc is empty), so this is a cheap call on every day after the first. Returns a
    small result dict; never raises."""
    now = now or datetime.now(timezone.utc)
    existing = _read_existing(db, uid)
    start = max(existing) if existing else BACKFILL_START
    if "T" not in start:
        start = start + "T00:00:00Z"
    end = (now - timedelta(minutes=20)).strftime("%Y-%m-%dT%H:%M:%SZ")
    df = fetch_bars(SYMBOL, "1Day", start, end, key, secret, feed="sip", adjustment=ADJUSTMENT)
    doc, added, changed = build_merged_doc(existing, df, ADJUSTMENT)
    if not doc["bars"]:
        _log(f"{uid}: fetch returned no bars (start={start[:10]}) -- nothing written")
        return {"ok": False, "added": 0, "changed": 0, "n_bars": 0}
    _doc_ref(db, uid).set(doc)
    _log(f"{uid}: {doc['from']}..{doc['to']}, {len(doc['bars'])} bars total "
         f"(+{added} new, {changed} revised)")
    return {"ok": True, "added": added, "changed": changed, "n_bars": len(doc["bars"])}


# -- scheduling hook for the runner's watch loop ----------------------------------------
def maybe_run(q, *, force=False):
    """Cheap, throttled, exception-proof hook for api/runner.py's --watch loop. Real
    work (one Alpaca call + one Firestore write PER allow-listed uid) happens at most
    once per ET calendar day, and only after the day's own bar has settled -- see
    MIN_ET_FOR_TODAY. Every other call returns in well under 1ms and never blocks or
    raises into the caller's loop."""
    global _last_check_ts
    now_wall = time.time()
    if not force and (now_wall - _last_check_ts) < _CHECK_FLOOR_S:
        return None
    _last_check_ts = now_wall
    try:
        return _maybe_run_inner(q, force=force)
    except Exception as e:
        _log(f"maybe_run error: {type(e).__name__}: {e}")
        return None


def _maybe_run_inner(q, *, force=False):
    global _last_run_date, _warned_missing_keys
    now_et = _et_now()
    today = now_et.date().isoformat()
    if not force:
        if _last_run_date == today:
            return None
        if (now_et.hour, now_et.minute) < MIN_ET_FOR_TODAY:
            return None
    key, secret = load_keys()
    if not key or not secret:
        if not _warned_missing_keys:
            _log("no Alpaca key configured -- add ALPACA_API_KEY / ALPACA_SECRET_KEY "
                 "env vars, or \"alpaca_key\"/\"alpaca_secret\" to augur_config.json, "
                 "or create tools/.alpaca_keys.json with {\"key\": ..., \"secret\": ...}. "
                 "The SPY benchmark stays empty (web shows an em dash) until then.")
            _warned_missing_keys = True
        return None
    _last_run_date = today
    n_ok = 0
    for uid in list(getattr(q, "allow", None) or []):
        try:
            r = fetch_and_merge(q.db, uid, key, secret)
            n_ok += 1 if r.get("ok") else 0
        except Exception as e:
            _log(f"{uid}: fetch/publish failed: {type(e).__name__}: {e}")
    return {"ok": n_ok > 0, "uids": n_ok}


# -- manual one-shot driver ---------------------------------------------------------------
def run_once_cli():
    """python -m api.spy_daily --once --cred serviceAccount.json --allow-uid <uid>
    Forces one backfill/incremental fetch + publish immediately, bypassing the daily
    gate and the clock window -- e.g. right after the owner adds Alpaca keys."""
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--cred", required=True, help="Firebase service-account JSON path")
    ap.add_argument("--allow-uid", action="append", required=True)
    ap.add_argument("--once", action="store_true")
    a = ap.parse_args()

    key, secret = load_keys()
    if not key or not secret:
        raise SystemExit(
            "No Alpaca key found. Set env ALPACA_API_KEY / ALPACA_SECRET_KEY, or add\n"
            '  "alpaca_key": "...", "alpaca_secret": "..."  to augur_config.json, or create\n'
            '  tools/.alpaca_keys.json  with  {"key": "...", "secret": "..."}')

    import firebase_admin
    from firebase_admin import credentials, firestore
    cred = credentials.Certificate(a.cred)
    try:
        firebase_admin.initialize_app(cred)
    except ValueError:
        pass  # already initialized
    db = firestore.client()

    for uid in a.allow_uid:
        result = fetch_and_merge(db, uid, key, secret)
        print(f"{uid}: {result}")


if __name__ == "__main__":
    run_once_cli()
