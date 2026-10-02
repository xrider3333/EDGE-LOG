r"""tools/backfill_qqq_5m_alpaca.py -- one-shot QQQ 5-minute history backfill for the
Webull QQQ paper book's Oracle box, from Alpaca's free market-data API (owner GO
2026-09-26).

WHY. NOISE_1_0.py's vol_skip_pct filter ranks each session against VOL_SKIP_REF_SESSIONS
(252) trailing sessions in the real backtest (see api/cloud_signal.py's
REQUIRED_LOOKBACK_SESSIONS block comment) -- but the box's live ~/edgelog/ohlc/QQQ_5m.csv
cache only holds however many sessions have accumulated since the paper book started, far
short of 252. This tool fills that gap with real historical SIP bars, entirely offline
from the two live services: it never rewrites QQQ_5m.csv itself (see UPLOAD below and
api/cloud_signal.py's own small change), so it cannot race edgelog-cloud-signal's 30s
cache-writer thread.

NO KEY EXISTS YET (2026-09-26) -- everything here is built and tested against a FAKE
Alpaca HTTP layer (tests/test_backfill_qqq_5m_alpaca.py). See deploy_notes for the exact
owner steps to add a real one.

KEY LOOKUP: not done here. augur_engine/alpaca_keys.py is the single lookup for the whole
repo -- env, then the Windows user environment read straight from the registry, then
C:\EdgeLog\secrets\alpaca_keys.json, augur_config.json and tools/.alpaca_keys.json.
This file used to prefer the secrets file over the environment. The environment now wins,
because the argument for that file was about where a key is STORED (outside the repo, so it
cannot be committed by accident), not about which source should win when two disagree -- and
a key set in the process environment is the only override you can apply to one command
without editing a file.

ADJUSTMENT. Alpaca applies split adjustment server-side via `adjustment=split|raw|...`.
QQQ had NO split in this window (unlike, say, NVDA or AAPL in other years), so `split`
and `raw` return IDENTICAL data here -- there is no real-world 2x mismatch to reason
about, and the default (`adjustment=split`, matching tools/import_alpaca_stocks.py's own
default) is harmless either way. Without a real key, the only actual check of this
choice is the cross-check this tool always runs before --apply: it compares a few
overlapping bars against the box's own cache and refuses to upload on a mismatch (see
cross_check()'s adjustment-mismatch note) -- that comparison, not any pre-reasoned split
history, is what should be trusted once a real fetch happens.

WINDOW. At least MIN_SESSIONS (265) NYSE/Nasdaq sessions (api.market_calendar -- half days
count as one session each, same as the live engine's own day-bucketing), ending at the
last FULLY CLOSED session as of now (last_full_session()) -- never a session still being
built. The requested window necessarily overlaps the tail of the box's own cache, which is
what makes the cross-check possible.

WRITES A LOCAL FILE FIRST, always (default tools/data/qqq_5m_alpaca_backfill.csv -- under
tools/data/ and *.csv-shaped, so .gitignore's bare `*.csv` rule already keeps it out of
git; no .gitignore edit needed). Nothing is uploaded without a separate --apply.

UPLOAD (--apply only) never rewrites the live ~/edgelog/ohlc/QQQ_5m.csv cache. It scp's
the local file to ~/edgelog/ohlc/QQQ_5m_backfill.csv.tmp and `mv`s it into place on the
box (atomic on POSIX, so a reader never sees a half-written file) -- a SEPARATE file that
api/cloud_signal.py's bar-loading code (historical_bars/_prepend_backfill) reads
read-only, cached by the file's own mtime, and splices onto the FRONT of the live cache
for signal computation only, never onto what gets written back to disk. --apply also
refuses outright:
  * if the cross-check against the box's own overlapping bars disagrees beyond a small
    tolerance (CROSS_CHECK_TOLERANCE per bar, CROSS_CHECK_MAX_BAD_FRACTION of bars) --
    including when there is no overlap at all, since that means nothing was verified;
  * if the fetch came up short of --sessions actual distinct sessions;
  * during the PROTECTED WINDOW (09:25-16:05 ET) on a trading day, so the upload's own
    ssh/scp round trip can never land while the box's tick loop is running.

USAGE
    python tools/backfill_qqq_5m_alpaca.py --check          # verify the key works, exit
    python tools/backfill_qqq_5m_alpaca.py                  # fetch + cross-check, LOCAL file only
    python tools/backfill_qqq_5m_alpaca.py --apply           # + upload to the box
    python tools/backfill_qqq_5m_alpaca.py --apply --tolerance 0.10 --max-bad-fraction 0.05
                                                              # widen the cross-check if a
                                                              # Yahoo/Webull-sourced box cache
                                                              # disagrees with SIP by more than
                                                              # the default 2 cents / 1% of bars
                                                              # for reasons that look like
                                                              # ordinary vendor noise, not a
                                                              # real mismatch (see the printed
                                                              # per-column breakdown)

Tests (tests/test_backfill_qqq_5m_alpaca.py) cover: key lookup order (including a
BOM-prefixed secrets file, see load_keys' own docstring), RTH filtering and half days
(including real after-hours bars Alpaca actually returns past a half day's 13:00 close),
the on-disk column/schema contract, cross-check refusal (short overlap, over-tolerance, no
overlap, adjustment-mismatch note, per-column breakdown, --tolerance/--max-bad-fraction
overrides), a 403's subscription/recency message vs a real auth failure, the end_iso
free-plan recency clamp, the cloud_signal prepend (older-only, never overrides a
live-cache row, fail-safe, no-op on a missing/empty cache) -- and run()'s own refusal
wiring (short fetch, protected window, failed cross-check) via injected fakes. No test
opens a socket or an ssh connection: every network boundary (http_get, box_cache_df,
ssh_fn, scp_fn) is an injectable parameter of run(), defaulting to the real thing only in
main().
"""
import argparse
import os
import shlex
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone

import pandas as pd
import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from api import market_calendar  # noqa: E402
from augur_engine import alpaca_keys  # noqa: E402
from augur_engine import alpaca_rate  # noqa: E402

try:
    from zoneinfo import ZoneInfo
    _ET = ZoneInfo("America/New_York")
except Exception:  # pragma: no cover -- zoneinfo ships with 3.9+, this repo runs 3.13
    _ET = None

# -- Alpaca -----------------------------------------------------------------------------
BARS_URL = "https://data.alpaca.markets/v2/stocks/bars"
SYMBOL = "QQQ"
TIMEFRAME = "5Min"
DEFAULT_FEED = "sip"
DEFAULT_ADJUSTMENT = "split"          # see module docstring "ADJUSTMENT"

MIN_SESSIONS = 265

# Alpaca's free plan lags real-time SIP data by ~15 minutes and 403s a request for
# anything more recent than that; pad by a minute so a fetch never lands right on the
# edge (see fetch_5m_bars' 403 handling and run()'s end_iso clamp).
FREE_SIP_DELAY = timedelta(minutes=16)

# -- cross-check --------------------------------------------------------------------------
CROSS_CHECK_TOLERANCE = 0.02          # 2 cents per bar (open/high/low/close each)
CROSS_CHECK_MAX_BAD_FRACTION = 0.01   # refuse if > 1% of overlapping bars exceed tolerance

# -- box (same host/key/paths as tools/box_deploy.py) --------------------------------------
HOST = "ubuntu@163.192.117.12"
SSH_KEY = os.path.expanduser(os.path.join("~", ".ssh", "edgelog_oracle"))
SSH_OPTS = ["-i", SSH_KEY, "-o", "BatchMode=yes", "-o", "ConnectTimeout=20"]
REMOTE_HOME = "/home/ubuntu/edgelog"
REMOTE_OHLC_DIR = f"{REMOTE_HOME}/ohlc"
REMOTE_CACHE_5M = f"{REMOTE_OHLC_DIR}/QQQ_5m.csv"
REMOTE_BACKFILL_5M = f"{REMOTE_OHLC_DIR}/QQQ_5m_backfill.csv"

# -- protected upload window (same shape as tools/box_deploy.py's PROTECTED window) --------
import datetime as _dt  # noqa: E402
PROTECTED_START = _dt.time(9, 25)
PROTECTED_END = _dt.time(16, 5)

DEFAULT_OUT = os.path.join(ROOT, "tools", "data", "qqq_5m_alpaca_backfill.csv")

COLUMNS = ["time", "open", "high", "low", "close", "volume"]


# ── keys ──────────────────────────────────────────────────────────────────────────────────
def load_keys():
    """Resolve the Alpaca key/secret. ONE shared lookup, augur_engine/alpaca_keys.py --
    including the Windows registry fallback, which is what lets a process that started
    before the keys were saved still find them. Returns (key, secret) or (None, None), and
    never prints or logs the value."""
    return alpaca_keys.load_keys()


# ── session window ───────────────────────────────────────────────────────────────────────
def last_full_session(now_et=None):
    """The most recent NYSE/Nasdaq session that has FULLY CLOSED as of `now_et` (default:
    real now in America/New_York) -- today's own session counts only once its own close
    time (api.market_calendar.session_close_et, half-day aware) has passed; otherwise this
    steps back to the prior session. Returns a datetime.date."""
    now_et = now_et or datetime.now(_ET)
    today = now_et.date()
    if market_calendar.is_session(today):
        close_h, close_m = (int(x) for x in market_calendar.session_close_et(today).split(":"))
        close_dt = now_et.replace(hour=close_h, minute=close_m, second=0, microsecond=0)
        if now_et >= close_dt:
            return today
    d = today - timedelta(days=1)
    while not market_calendar.is_session(d):
        d -= timedelta(days=1)
    return d


def _end_iso_for(end_date, now_et):
    """UTC ISO end bound for the fetch: normally midnight UTC the day AFTER `end_date`
    (i.e. through that session's own close), but never later than `now_et` minus
    FREE_SIP_DELAY. Without this clamp, a run the same evening before about 20:15 ET (or
    a --end date still in progress) asks Alpaca's free SIP feed for data under ~15
    minutes old, which comes back as a 403 -- see fetch_5m_bars' own message for that
    case. This only ever pulls the bound EARLIER; a `--end` well in the past is
    untouched."""
    naive_end = datetime(end_date.year, end_date.month, end_date.day, tzinfo=timezone.utc) \
        + timedelta(days=1)
    safe_now = now_et.astimezone(timezone.utc) - FREE_SIP_DELAY
    return min(naive_end, safe_now).strftime("%Y-%m-%dT%H:%M:%SZ")


def sessions_ending(end_date, n):
    """The `n` most recent NYSE/Nasdaq sessions ending at (and including) `end_date`,
    oldest first. `end_date` need not itself be a session -- it is only an upper bound."""
    out = []
    d = end_date
    while len(out) < n:
        if market_calendar.is_session(d):
            out.append(d)
        d -= timedelta(days=1)
    return list(reversed(out))


# ── fetch ─────────────────────────────────────────────────────────────────────────────────
def fetch_5m_bars(key, secret, start_iso, end_iso, feed=DEFAULT_FEED,
                  adjustment=DEFAULT_ADJUSTMENT, http_get=None, log=print):
    """Page through Alpaca's bars endpoint for QQQ 5Min bars in [start_iso, end_iso).
    Returns a DataFrame with columns exactly COLUMNS (time = bar START, UTC epoch
    seconds). `http_get` defaults to requests.get; tests inject a fake. Mirrors
    tools/import_alpaca_stocks.py's fetch_bars (same paging/backoff/auth-error shape)."""
    http_get = http_get or requests.get
    heads = {"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret}
    rows, token, pages = [], None, 0
    while True:
        params = {"symbols": SYMBOL, "timeframe": TIMEFRAME, "start": start_iso,
                  "end": end_iso, "limit": 10000, "adjustment": adjustment,
                  "feed": feed, "sort": "asc"}
        if token:
            params["page_token"] = token
        # One account, five lanes. The 0.31s pace below assumes this process is the only
        # one pulling; alpaca_rate is what makes that true for the ACCOUNT instead.
        alpaca_rate.wait()
        r = http_get(BARS_URL, headers=heads, params=params, timeout=60)
        if r.status_code == 429:
            log("    429 rate-limited, sleeping 20s…"); time.sleep(20); continue
        if r.status_code == 401:
            raise SystemExit(f"AUTH FAILED (401) — check your Alpaca key/secret. {r.text[:200]}")
        if r.status_code == 403:
            body = r.text[:300]
            if any(w in body.lower() for w in ("subscription", "recent", "sip")):
                raise SystemExit(
                    "ALPACA REFUSED (403) — this looks like the free plan's SIP-feed "
                    "recency limit (data less than ~15 minutes old), not a bad key: try "
                    f"an earlier --end, or re-run in a few minutes. {body}")
            raise SystemExit(f"AUTH FAILED (403) — check your Alpaca key/secret. {body}")
        if r.status_code != 200:
            raise RuntimeError(f"HTTP {r.status_code}: {r.text[:300]}")
        js = r.json()
        bars = (js.get("bars") or {}).get(SYMBOL) or []
        rows.extend(bars)
        pages += 1
        token = js.get("next_page_token")
        if not token:
            break
        if pages % 10 == 0:
            log(f"    …{len(rows):,} bars so far")
        time.sleep(0.31)
    if not rows:
        return pd.DataFrame(columns=COLUMNS)
    df = pd.DataFrame(rows)
    out = pd.DataFrame({
        "time":   (pd.to_datetime(df["t"], utc=True) - pd.Timestamp(0, tz="UTC")) // pd.Timedelta(seconds=1),
        "open":   df["o"].astype(float), "high": df["h"].astype(float),
        "low":    df["l"].astype(float), "close": df["c"].astype(float),
        "volume": df["v"].astype(float),
    })
    return out.drop_duplicates(subset="time").sort_values("time").reset_index(drop=True)


def _close_minutes_et(d):
    """Minutes-since-midnight ET close for calendar date `d`, half-day aware
    (api.market_calendar.session_close_et -- '13:00' on a half day, else '16:00')."""
    hh, mm = (int(x) for x in market_calendar.session_close_et(d).split(":"))
    return hh * 60 + mm


def rth_filter(df):
    """Keep only bars whose START falls in the 09:30 ET .. that day's own regular-session
    close (api.market_calendar.session_close_et, half-day aware). A fixed 16:00 ceiling is
    NOT safe here: Alpaca's bars endpoint returns extended-hours bars too, and after-hours
    trading runs from 13:00 on an early-close day (day-after-Thanksgiving, 12/24, some
    7/3s) -- a fixed 16:00 bound would let 13:00-15:55 after-hours bars leak into the RTH
    window on those days, bars the live box cache never contains. The session still counts
    once either way (api.market_calendar.is_session doesn't care how many bars a day has),
    which is what sessions_ending/session-count checks below rely on."""
    if not len(df):
        return df
    et = pd.to_datetime(df["time"], unit="s", utc=True).dt.tz_convert("US/Eastern")
    mins = et.dt.hour * 60 + et.dt.minute
    dates = et.dt.date
    close_by_date = {d: _close_minutes_et(d) for d in dates.unique()}
    close_mins = dates.map(close_by_date)
    return df[(mins >= 9 * 60 + 30) & (mins < close_mins)].reset_index(drop=True)


def distinct_session_dates(df):
    """Sorted set of US/Eastern calendar dates present in `df`."""
    if not len(df):
        return []
    et = pd.to_datetime(df["time"], unit="s", utc=True).dt.tz_convert("US/Eastern")
    return sorted(set(et.dt.date.tolist()))


# ── cross-check against the box's own cache ────────────────────────────────────────────────
def _adjustment_mismatch_note(merged):
    """Best-effort diagnostic: if the overlap disagrees by something close to a clean 2x
    (or 0.5x) ratio, that is the signature of a raw-vs-split-adjustment mismatch rather
    than ordinary vendor rounding noise -- worth surfacing in the refusal reason since
    --adjustment is the most likely fix. Never raises; returns "" if inconclusive."""
    try:
        box_close = merged["close_box"]
        new_close = merged["close_new"]
        nonzero = box_close != 0
        if not nonzero.any():
            return ""
        ratio = (new_close[nonzero] / box_close[nonzero]).median()
        if 1.9 <= ratio <= 2.1 or 0.45 <= ratio <= 0.55:
            return (f" (median new/box ratio {ratio:.3f} looks like a raw-vs-split "
                    f"adjustment mismatch -- try the other --adjustment)")
    except Exception:
        pass
    return ""


def cross_check(new_df, box_df, tolerance=CROSS_CHECK_TOLERANCE,
                max_bad_fraction=CROSS_CHECK_MAX_BAD_FRACTION):
    """Compares `new_df` (the fetch) against `box_df` (the box's live cache) on their
    overlapping bars (inner join on `time`). Returns a dict: n_compared, max_abs_diff
    (largest per-bar max(|open|,|high|,|low|,|close| diff), or None if n_compared==0),
    n_over_tol, bad_fraction, col_over_tol (per-column {open,high,low,close: count over
    tolerance} -- lets a caller tell vendor high/low noise from a real open/close
    mismatch), ok, reason. ok is False whenever there is nothing to compare (an empty
    overlap proves nothing, so it is treated as a failed check, not a free pass) or when
    more than `max_bad_fraction` of the overlapping bars differ by more than `tolerance`
    on any of the four price columns. `tolerance`/`max_bad_fraction` are the CLI's
    --tolerance/--max-bad-fraction, in case vendor-noise defaults (2 cents, 1%) prove too
    tight for a real Yahoo/Webull-sourced box cache -- see module docstring "UPLOAD".
    Pure function -- no I/O, fully covered by tests/test_backfill_qqq_5m_alpaca.py."""
    if box_df is None or not len(box_df) or new_df is None or not len(new_df):
        return {"n_compared": 0, "max_abs_diff": None, "n_over_tol": 0,
                "bad_fraction": None, "col_over_tol": {}, "ok": False,
                "reason": "no overlapping bars with the box cache -- cannot verify, refusing"}
    merged = new_df.merge(box_df, on="time", suffixes=("_new", "_box"))
    n_compared = len(merged)
    if n_compared == 0:
        return {"n_compared": 0, "max_abs_diff": None, "n_over_tol": 0,
                "bad_fraction": None, "col_over_tol": {}, "ok": False,
                "reason": "no overlapping bars with the box cache -- cannot verify, refusing"}
    diffs = pd.DataFrame({
        c: (merged[f"{c}_new"] - merged[f"{c}_box"]).abs() for c in ("open", "high", "low", "close")
    })
    per_bar_max = diffs.max(axis=1)
    max_abs_diff = float(per_bar_max.max())
    n_over_tol = int((per_bar_max > tolerance).sum())
    bad_fraction = n_over_tol / n_compared
    ok = bad_fraction <= max_bad_fraction
    col_over_tol = {c: int((diffs[c] > tolerance).sum()) for c in diffs.columns}
    reason = None
    if not ok:
        by_col = ", ".join(f"{c}={n}" for c, n in col_over_tol.items() if n)
        reason = (f"{n_over_tol}/{n_compared} overlapping bars disagree by > "
                  f"${tolerance:.2f} (max abs diff ${max_abs_diff:.4f}; over-tolerance by "
                  f"column: {by_col or 'none'})" + _adjustment_mismatch_note(merged))
    return {"n_compared": n_compared, "max_abs_diff": max_abs_diff, "n_over_tol": n_over_tol,
            "bad_fraction": bad_fraction, "col_over_tol": col_over_tol, "ok": ok, "reason": reason}


# ── local write ───────────────────────────────────────────────────────────────────────────
def write_local(df, out_path):
    """Atomic local write (tmp then os.replace) so a half-written file is never mistaken
    for a finished one. `df` must already be COLUMNS-shaped."""
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    tmp = out_path + ".tmp"
    df.to_csv(tmp, index=False)
    os.replace(tmp, out_path)


# ── box transport (never exercised in tests -- see run()'s injectable ssh_fn/scp_fn) ──────
def _ssh(cmd, timeout=60):
    return subprocess.run(["ssh", *SSH_OPTS, HOST, cmd], capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=timeout)


def read_box_cache_5m():
    """Read-only fetch of the box's live QQQ_5m.csv over ssh (`cat`), parsed into a
    DataFrame -- or None on ANY failure (unreachable box, missing file, bad CSV). Never
    writes anything, never used for anything but the cross-check comparison."""
    try:
        r = _ssh(f"cat {shlex.quote(REMOTE_CACHE_5M)} 2>/dev/null")
        if r.returncode != 0 or not (r.stdout or "").strip():
            return None
        import io
        return pd.read_csv(io.StringIO(r.stdout))
    except Exception:
        return None


def _scp_upload(local_path, remote_path, timeout=120):
    return subprocess.run(["scp", *SSH_OPTS, local_path, f"{HOST}:{remote_path}"],
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=timeout)


def apply_upload(local_path, ssh_fn=None, scp_fn=None):
    """scp `local_path` to REMOTE_BACKFILL_5M + '.tmp' then `mv` it into place on the box
    (atomic on POSIX -- a reader of REMOTE_BACKFILL_5M never sees a half-written file).
    Never touches REMOTE_CACHE_5M. Returns (ok: bool, message: str)."""
    ssh_fn = ssh_fn or _ssh
    scp_fn = scp_fn or _scp_upload
    remote_tmp = REMOTE_BACKFILL_5M + ".tmp"
    r = scp_fn(local_path, remote_tmp)
    if r.returncode != 0:
        return False, f"scp upload failed: {(r.stderr or r.stdout or '').strip()[:400]}"
    r = ssh_fn(f"mv {shlex.quote(remote_tmp)} {shlex.quote(REMOTE_BACKFILL_5M)}")
    if r.returncode != 0:
        return False, f"remote mv failed: {(r.stderr or r.stdout or '').strip()[:400]}"
    return True, f"uploaded to {HOST}:{REMOTE_BACKFILL_5M}"


# ── protected window ──────────────────────────────────────────────────────────────────────
def in_protected_window(now_et=None):
    """True during 09:25-16:05 ET on a trading day -- the same window box_deploy.py
    protects its own deploys with, applied here to the upload's ssh/scp round trip so it
    can never land while the box's tick loop is running."""
    now_et = now_et or datetime.now(_ET)
    if not market_calendar.is_session(now_et.date()):
        return False
    t = now_et.time()
    return PROTECTED_START <= t < PROTECTED_END


# ── orchestration (testable: every I/O boundary is an injectable parameter) ───────────────
def run(args, key_secret=None, http_get=None, box_cache_df=None, now_et=None,
       ssh_fn=None, scp_fn=None, log=print):
    """Core of the CLI, fully injectable for tests. Returns a process exit code."""
    key, secret = key_secret if key_secret is not None else load_keys()
    if not key or not secret:
        log("No Alpaca key found. See this file's module docstring \"KEY LOOKUP\" for "
            "every place checked, or deploy_notes for the exact owner steps.")
        return 1

    if args.check:
        smoke_start = "2026-01-02T00:00:00Z"
        smoke_end = "2026-01-10T00:00:00Z"
        df = fetch_5m_bars(key, secret, smoke_start, smoke_end, args.feed, args.adjustment,
                           http_get=http_get, log=log)
        log(f"KEY OK — fetched {len(df)} QQQ 5Min bars as a smoke test (feed={args.feed}).")
        return 0

    now_et = now_et or datetime.now(_ET)
    end_date = args.end or last_full_session(now_et)
    if isinstance(end_date, str):
        end_date = datetime.strptime(end_date, "%Y-%m-%d").date()
    sessions_wanted = args.sessions
    start_date = sessions_ending(end_date, sessions_wanted)[0]
    start_iso = f"{start_date:%Y-%m-%d}T00:00:00Z"
    end_iso = _end_iso_for(end_date, now_et)

    log(f"Fetching QQQ {TIMEFRAME} bars {start_date}..{end_date} (feed={args.feed}, "
        f"adjustment={args.adjustment}) …")
    df = fetch_5m_bars(key, secret, start_iso, end_iso, args.feed, args.adjustment,
                       http_get=http_get, log=log)
    df = rth_filter(df)
    n_sessions = len(distinct_session_dates(df))
    log(f"  {len(df):,} RTH bars across {n_sessions} session(s) (wanted >= {sessions_wanted})")

    write_local(df, args.out)
    log(f"  wrote {args.out}")

    box_df = box_cache_df if box_cache_df is not None else read_box_cache_5m()
    check = cross_check(df, box_df, tolerance=args.tolerance, max_bad_fraction=args.max_bad_fraction)
    if check["n_compared"]:
        by_col = ", ".join(f"{c}={n}" for c, n in check["col_over_tol"].items() if n) or "none"
        log(f"  cross-check: {check['n_compared']} overlapping bar(s), max abs diff "
            f"${check['max_abs_diff']:.4f}, {check['n_over_tol']} over ${args.tolerance:.2f} "
            f"(by column: {by_col})")
    else:
        log("  cross-check: no overlapping bars with the box cache")
    if not check["ok"]:
        log(f"  CROSS-CHECK FAILED: {check['reason']}")

    if not args.apply:
        log("  local file only (pass --apply to upload once the cross-check above looks right)")
        return 0

    if not check["ok"]:
        log("REFUSING --apply: cross-check against the box cache failed (see above).")
        return 1
    if n_sessions < sessions_wanted:
        log(f"REFUSING --apply: only {n_sessions} session(s) fetched, wanted >= {sessions_wanted}.")
        return 1
    if in_protected_window(now_et):
        log(f"REFUSING --apply: inside the protected window "
            f"({PROTECTED_START}-{PROTECTED_END} ET on a trading day).")
        return 1

    ok, message = apply_upload(args.out, ssh_fn=ssh_fn, scp_fn=scp_fn)
    log(f"  {'APPLIED' if ok else 'APPLY FAILED'}: {message}")
    return 0 if ok else 1


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Backfill QQQ 5-minute history from Alpaca for the box's NOISE_382 "
                    "vol_skip_pct window.")
    ap.add_argument("--sessions", type=int, default=MIN_SESSIONS,
                    help=f"minimum sessions to fetch (default {MIN_SESSIONS})")
    ap.add_argument("--end", default=None, help="YYYY-MM-DD override for the last full "
                    "session (default: computed from the real clock)")
    ap.add_argument("--out", default=DEFAULT_OUT, help="local output CSV path")
    ap.add_argument("--feed", default=DEFAULT_FEED, help="sip (default) or iex")
    ap.add_argument("--adjustment", default=DEFAULT_ADJUSTMENT,
                    help="raw|split|dividend|spin-off|all (default split -- see module "
                    "docstring \"ADJUSTMENT\")")
    ap.add_argument("--apply", action="store_true",
                    help="upload to the box's QQQ_5m_backfill.csv after a passing cross-check")
    ap.add_argument("--check", action="store_true", help="verify the key works, then exit")
    ap.add_argument("--tolerance", type=float, default=CROSS_CHECK_TOLERANCE,
                    help="cross-check: per-bar OHLC tolerance in dollars before a bar counts "
                    f"as disagreeing (default {CROSS_CHECK_TOLERANCE})")
    ap.add_argument("--max-bad-fraction", type=float, dest="max_bad_fraction",
                    default=CROSS_CHECK_MAX_BAD_FRACTION,
                    help="cross-check: fraction of overlapping bars allowed over --tolerance "
                    f"before refusing --apply (default {CROSS_CHECK_MAX_BAD_FRACTION}) -- raise "
                    "this if a Yahoo/Webull-sourced box cache disagrees with SIP on more than "
                    "the default 1% of bars for reasons the printed by-column breakdown shows "
                    "are ordinary vendor noise, not a real mismatch")
    args = ap.parse_args(argv)
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
