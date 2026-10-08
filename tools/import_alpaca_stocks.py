# import_alpaca_stocks.py — pull intraday US STOCK OHLCV from Alpaca into the AUGUR
# library as masters tagged 'alpaca_<adj>_<session>'.
#
# WHY ALPACA: the free (Basic) plan serves HISTORICAL bars from the full SIP
# consolidated feed (100% of volume) back to 2016 — the "IEX only / ~2.5% of volume"
# restriction applies to REAL-TIME streaming, not historical queries. The only catch is
# `end` must be >=15 min old, which is irrelevant for backtesting.
#
# SPLITS: stocks need split adjustment or every split looks like a crash (NVDA 10:1 2024,
# AAPL 4:1 2020) and breakout/gap strategies fire on garbage. Alpaca does this server-side
# via `adjustment` (raw|split|dividend|spin-off|all) — no custom back-adjust code needed
# (unlike the futures roll logic in stitch_databento.py). Default here: split.
#
# The source tag keeps these SEPARATE from the deliberately NON-adjusted futures masters
# (nt_noadj / db_noadj) so the two conventions can never blend inside one master.
#
# Mirrors the proven tools/import_nt_ohlc.py pattern: talks to optimizer_history.db +
# augur_uploads directly via sqlite3/pandas — it does NOT import optimizer.py.
# Idempotent + additive: re-running EXTENDS the matching master (existing rows win).
#
# KEY: never hardcoded, never printed, and NOT resolved here -- augur_engine/alpaca_keys.py
# is the one lookup for the whole repo (env, then the Windows user environment straight out
# of the registry, then three JSON locations). See that module for the order and why.
#
# Run:
#   python tools/import_alpaca_stocks.py --check
#   python tools/import_alpaca_stocks.py --symbols AAPL,MSFT,NVDA --timeframe 5Min --start 2016-01-01
#   python tools/import_alpaca_stocks.py --symbols AAPL --timeframe 1Min --start 2024-01-01 --rth
import os
import re
import sys
import time
import uuid
import sqlite3
import argparse
from datetime import datetime, timedelta, timezone

import pandas as pd
import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UP   = os.path.join(ROOT, "augur_uploads")
DB   = os.path.join(ROOT, "optimizer_history.db")

if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
from augur_engine import alpaca_keys  # noqa: E402
from augur_engine import alpaca_rate  # noqa: E402
from augur_engine import pull_provenance  # noqa: E402
from augur_engine.master_write import write_master_csv  # noqa: E402
LOG  = os.path.join(os.path.dirname(os.path.abspath(__file__)), "import_alpaca_stocks.log")

BARS_URL = "https://data.alpaca.markets/v2/stocks/bars"

# Alpaca timeframe -> the library's timeframe tag (must match existing master conventions)
TF_TAG = {"1min": "1m", "2min": "2m", "5min": "5m", "15min": "15m", "30min": "30m",
          "1hour": "1h", "1day": "1D", "1week": "1W"}


def log(msg):
    line = f"{datetime.now():%Y-%m-%d %H:%M:%S}  {msg}"
    print(line)
    try:
        with open(LOG, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except Exception:
        pass


def load_keys():
    """Resolve the API key/secret. ONE shared lookup now lives in augur_engine/alpaca_keys.py -
    including the Windows registry fallback, which is what lets a process that started before
    the keys were saved still find them. Never prints the value."""
    return alpaca_keys.load_keys()


def fetch_bars(sym, timeframe, start, end, key, secret, feed="sip", adjustment="split"):
    """Page through Alpaca's bars endpoint. Returns a DataFrame (time,open,high,low,close,volume).

    Alpaca caps a request at 10,000 bars and returns next_page_token to continue; the free
    plan allows 200 req/min, so we pace politely and retry on 429."""
    heads = {"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret}
    rows, token, pages = [], None, 0
    while True:
        params = {"symbols": sym, "timeframe": timeframe, "start": start, "end": end,
                  "limit": 10000, "adjustment": adjustment, "feed": feed, "sort": "asc"}
        if token:
            params["page_token"] = token
        # One account, five lanes. The 0.31s pace below assumes this process is the only
        # one pulling; alpaca_rate is what makes that true for the ACCOUNT instead.
        alpaca_rate.wait()
        r = requests.get(BARS_URL, headers=heads, params=params, timeout=60)
        if r.status_code == 429:                       # rate limited -> back off and retry
            log("    429 rate-limited, sleeping 20s…"); time.sleep(20); continue
        if r.status_code in (401, 403):
            raise SystemExit(f"AUTH FAILED ({r.status_code}) — check your Alpaca key/secret. {r.text[:200]}")
        if r.status_code != 200:
            raise RuntimeError(f"HTTP {r.status_code}: {r.text[:300]}")
        js = r.json()
        bars = (js.get("bars") or {}).get(sym) or []
        rows.extend(bars)
        pages += 1
        token = js.get("next_page_token")
        if not token:
            break
        if pages % 10 == 0:
            log(f"    …{len(rows):,} bars so far")
        time.sleep(0.31)                               # ~195/min, under the 200/min cap
    if not rows:
        pull_provenance.record(sym, timeframe, start, end, pd.DataFrame(),
                               adjustment=adjustment, feed=feed)
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    out = pd.DataFrame({
        "time":   (pd.to_datetime(df["t"], utc=True) - pd.Timestamp(0, tz="UTC")) // pd.Timedelta(seconds=1),  # POSIX seconds independent of datetime resolution (pandas 3 = microseconds; astype//1e9 breaks)
        "open":   df["o"].astype(float), "high": df["h"].astype(float),
        "low":    df["l"].astype(float), "close": df["c"].astype(float),
        "volume": df["v"].astype("int64"),
    })
    out = out.drop_duplicates(subset="time").sort_values("time").reset_index(drop=True)
    # WHICH PHOTOGRAPH OF THE VENDOR THIS IS (augur_engine/pull_provenance.py). Recorded HERE,
    # in fetch_bars, because TTM, TBIS and the ROC-frontier harnesses call this straight into
    # their own research caches and never reach upsert_master - recording on the library path
    # alone would miss exactly the pulls that matter. Never fatal: a pull that worked must not
    # fail because its receipt could not be filed.
    pull_provenance.record(sym, timeframe, start, end, out,
                           adjustment=adjustment, feed=feed)
    return out


# NYSE closes at 13:00 ET on about three sessions a year. SIP keeps printing afterwards, and
# those prints are extended-hours trades, so a master labelled "rth" that keeps them is not the
# cash session. The futures RTH masters these results get compared against have no such bars
# (MANAGER review 2026-09-30, finding 5). Dates are the half-days through 2027; add as needed -
# an unknown year simply keeps the normal 16:00 close, which is the safe direction for a filter
# that is only ever trimming. 2016-12-23 is NOT one: NYSE traded a full session that day (only the
# bond market closed early); listing it cut 13:00-16:00 off a WF session (pre-run review 2026-10-03).
# Removed 2026-07-03 + 2027-12-24 (NYSE closed: July 4 / Christmas observed) and 2027-07-02 (full session, July 4 is a Sunday) - list checked = XNYS 2016-2027 (pre-run review round 2, 2026-10-03).
EARLY_CLOSE_DATES = {
    "2016-11-25", "2017-07-03", "2017-11-24", "2018-07-03", "2018-11-23",
    "2018-12-24", "2019-07-03", "2019-11-29", "2019-12-24", "2020-11-27", "2020-12-24",
    "2021-11-26", "2022-11-25", "2023-07-03", "2023-11-24", "2024-07-03", "2024-11-29",
    "2024-12-24", "2025-07-03", "2025-11-28", "2025-12-24", "2026-11-27",
    "2026-12-24", "2027-11-26",
}
EARLY_CLOSE_MIN = 13 * 60        # 13:00 ET
REGULAR_CLOSE_MIN = 16 * 60      # 16:00 ET

def rth_filter(df):
    """Keep only the cash session, ending at the day's ACTUAL close.

    16:00 ET normally, 13:00 ET on an NYSE half day. Filtering every day to 16:00 left
    13:00-15:55 extended-hours prints inside masters labelled "rth", where a breakout rule's
    end-of-day exit could land on a thin post-close print.
    """
    if df is None or not len(df):
        return df
    et = pd.to_datetime(df["time"], unit="s", utc=True).dt.tz_convert("US/Eastern")
    mins = et.dt.hour * 60 + et.dt.minute
    close = pd.Series(REGULAR_CLOSE_MIN, index=df.index)
    early = et.dt.strftime("%Y-%m-%d").isin(EARLY_CLOSE_DATES)
    close[early.values] = EARLY_CLOSE_MIN
    return df[(mins >= 9 * 60 + 30) & (mins < close)].reset_index(drop=True)


def detect_session(df):
    et = pd.to_datetime(df["time"], unit="s", utc=True).dt.tz_convert("US/Eastern")
    mins = et.dt.hour * 60 + et.dt.minute
    inside = ((mins >= 9 * 60 + 30) & (mins < 16 * 60)).mean()
    return "rth" if inside > 0.98 else "eth"


# ── unadjusted splits that `adjustment=split` missed ─────────────────────────────────────
# FOUND IN THE WILD BY TBIS (2026-10-03), after it had already cost a result. Alpaca's
# split-adjusted feed did NOT adjust GE's 1-for-8 REVERSE split of 2021-08-02: the stored history
# runs 12.95 on 07-30 and then opens at 104.48, an 8.07x jump with the earlier years never
# rebased. TBIS's 10-minute bars read that as a real move and booked a fake +$139k trade, and it
# took a deliberate >25%-overnight-gap scan of 50 large caps to find it. Its scan found exactly
# one such defect, so this is rare - and rare is precisely what nobody checks for by hand.
#
# TELLING IT FROM REAL NEWS. A 25% overnight move is ordinary (INTC, ORCL, CELG all have real
# ones). What marks a split is the SIZE being a simple ratio: 8.000, 4.000, 1/8, 3/2. Real news
# does not land on 8.07x by coincidence, so the test is "a big overnight gap whose ratio sits
# within a couple of percent of a simple split ratio".
#
# Spin-offs are a different thing and are unadjusted BY DESIGN under adjustment=split, so they
# are not caught here and should not be: their ratios are not simple.
SPLIT_GAP_MIN = 0.25             # ignore overnight moves smaller than this - all ordinary news
SPLIT_RATIO_TOL = 0.02           # 2% - far tighter than any news gap lands on a simple ratio


def _simple_split_ratios():
    """Whole-number split ratios only: n:1 and 1:n for n from 2 to 20.

    NOT the fractional ones (3:2, 4:3, 5:4). Measured on real data, they cost more than they are
    worth: CELG's genuine takeover pop of 1.32x on 2019-01-03 sits within 2% of 4/3 and was
    refused as a missed split. A 1.3x overnight move is ordinary news; an 8.07x one is not. So the
    gap has to be at least a doubling or a halving AND land on a whole ratio, which is what makes
    the test discriminating rather than merely sensitive. TBIS's scan of 50 names across 10 years
    found exactly one real defect and it was 8:1.
    """
    out = set()
    for n in range(2, 21):
        out.add(float(n))
        out.add(1.0 / n)
    return sorted(out)


# TBIS's volume test (QA pass, 2026-10-04). A real split changes the SHARE COUNT, so volume
# scales by about 1/price_ratio: an 8:1 reverse split that multiplies the price by 8 divides the
# volume by 8, and price_ratio * volume_ratio lands near 1. A genuine news gap moves price without
# touching the share count, so the product lands near the price ratio instead - nowhere near 1.
# Measured on siporb's daily cache: 369 whole-ratio flags, 64 of which pass this. GE 2021-08-02
# gives price 8.068 x volume 0.143 = 1.15 (passes); AACG 2018-08-27 gives 0.1265 x 1.817 = 0.23
# (fails, correctly - that one is not a split).
SPLIT_VOLUME_TOL = 1.6              # "within 1.6x of 1", i.e. 0.625 .. 1.6
SPLIT_VOLUME_SESSIONS = 20          # 20-day median each side, so one heavy day cannot carry it

RTH_OPEN_MIN = 9 * 60 + 30          # 09:30 ET


def _is_daily_frame(minutes):
    """Is this a DAILY series rather than an intraday one?

    The test is the shape, not the timeframe label the caller happens to know: every bar in the
    frame sits at ONE clock time, and that time is outside the regular session. An Alpaca 1D
    master stamps every bar 00:00 ET and looks exactly like this; an intraday frame never does,
    because its bars run across the session.

    Deliberately narrow. Re-stamping every row to midday - which is what a scan that owns its own
    data can do - would, on an intraday frame, promote a stray premarket-only day into a session
    boundary and could invent a gap that is not there.
    """
    if not len(minutes):
        return False
    first = minutes[0]
    for m in minutes:
        if m != first:
            return False
    return first < RTH_OPEN_MIN or first >= EARLY_CLOSE_MIN


def _session_bounds(day_strs, minutes, dates):
    """{date: (first_rth_idx, last_rth_idx)} using each day's ACTUAL close.

    The regular session is what a split is quoted against, and it is also the only boundary that
    means the same thing on an RTH frame and an ETH one. A day with no regular-session bar at all
    (a pure premarket row) simply gets no entry.

    EXCEPT on a DAILY frame, where one bar IS the whole session. Without this the guard was blind
    to every 1D master: Alpaca stamps those at 00:00 ET, no date had a regular-session bar, every
    day was skipped, and a 1D master holding a missed split passed upsert_master silently
    (TBIS, 2026-10-07).
    """
    out = {}
    if _is_daily_frame(minutes):
        for i, day in enumerate(day_strs):
            first, last = out.get(day, (i, i))
            out[day] = (min(first, i), max(last, i))
        return out
    for i, day in enumerate(day_strs):
        close_min = EARLY_CLOSE_MIN if day in EARLY_CLOSE_DATES else REGULAR_CLOSE_MIN
        if minutes[i] < RTH_OPEN_MIN or minutes[i] >= close_min:
            continue
        first, last = out.get(day, (i, i))
        out[day] = (min(first, i), max(last, i))
    return out


def _median(vals):
    v = sorted(float(x) for x in vals if x is not None and float(x) > 0)
    if not v:
        return None
    n = len(v)
    return v[n // 2] if n % 2 else 0.5 * (v[n // 2 - 1] + v[n // 2])


def split_like_gaps(df, tol=SPLIT_RATIO_TOL, min_gap=SPLIT_GAP_MIN,
                    require_volume=False, vol_tol=SPLIT_VOLUME_TOL):
    """Session gaps that look like an unadjusted split: [(date, ratio, nearest, name)].

    Measured REGULAR SESSION CLOSE to the NEXT REGULAR SESSION OPEN - not last-bar-to-first-bar.
    On an extended-hours frame the latter compares an after-hours close (17:50) with a premarket
    open (04:30), which read GE's 1-for-8 as 7.80x and slipped outside the 2% window while the
    regular-session boundary reads 8.06x and fires (TBIS's QA, 2026-10-04). The regular session is
    also the basis a split is actually quoted against, and the one boundary that means the same
    thing on an RTH frame and an ETH one.

    require_volume adds TBIS's volume test, and is OFF by default because the two callers want
    opposite things. The WRITE guard in upsert_master must stay strict: a false refusal costs the
    caller a look and an `allow_split_gap=True`, while a false accept once wrote a fake +$139k
    trade. A SCAN across thousands of cached symbols wants precision instead - siporb's daily
    cache throws 369 whole-ratio flags, of which 64 pass the volume test - so a scan passes
    require_volume=True and accepts that a split with atypical volume will be missed.
    """
    if df is None or len(df) < 2:
        return []
    d = df.sort_values("time").reset_index(drop=True)
    et = pd.to_datetime(d["time"], unit="s", utc=True).dt.tz_convert("US/Eastern")
    day = et.dt.strftime("%Y-%m-%d").tolist()
    minutes = (et.dt.hour * 60 + et.dt.minute).tolist()
    bounds = _session_bounds(day, minutes, None)
    sessions = sorted(bounds)
    if len(sessions) < 2:
        return []
    has_vol = "volume" in d.columns
    ratios = _simple_split_ratios()
    out = []
    for k in range(1, len(sessions)):
        prev_day, this_day = sessions[k - 1], sessions[k]
        prev_close = float(d["close"].iloc[bounds[prev_day][1]])
        nxt_open = float(d["open"].iloc[bounds[this_day][0]])
        if prev_close <= 0 or nxt_open <= 0:
            continue
        ratio = nxt_open / prev_close
        if abs(ratio - 1.0) < min_gap:
            continue
        nearest = min(ratios, key=lambda r: abs(ratio - r))
        if not (nearest > 0 and abs(ratio - nearest) / nearest <= tol):
            continue
        if require_volume and has_vol:
            before, after = [], []
            for s in sessions[max(0, k - SPLIT_VOLUME_SESSIONS):k]:
                a, b = bounds[s]
                before.append(float(d["volume"].iloc[a:b + 1].sum()))
            for s in sessions[k:k + SPLIT_VOLUME_SESSIONS]:
                a, b = bounds[s]
                after.append(float(d["volume"].iloc[a:b + 1].sum()))
            mb, ma = _median(before), _median(after)
            if mb is None or ma is None:
                pass                      # no volume to judge by - fall back to the price test
            else:
                product = ratio * (ma / mb)
                if not (1.0 / vol_tol <= product <= vol_tol):
                    continue              # price moved, share count did not: ordinary news
        name = ("%d:1" % round(nearest)) if nearest >= 2 else ("1:%d" % round(1 / nearest))
        out.append((this_day, ratio, nearest, name))
    return out


SPLIT_REBASE_TOLERANCE = 0.005      # 0.5% - far below any split, far above a cent of rounding


def split_basis_changed(cur, new, tol=SPLIT_REBASE_TOLERANCE):
    """Do the bars both pulls share disagree enough that the split basis must have changed?

    WHY THIS MATTERS (MANAGER review 2026-09-30, finding 4). Alpaca's `adjustment=split`
    re-adjusts the WHOLE history as of the moment of the query. So after a split lands between
    two pulls, the stored bars are on the old basis and the new ones on the new basis. The
    additive "existing rows win" rule - right for a non-adjusted futures master - then leaves a
    10:1 cliff mid-series that every breakout and gap rule reads as a real crash. It is silent:
    rows only grow, so the write guard's shrink check never sees it. Reproduced with NVDA's 2024
    10:1 split: stored closes 1150 and 1220 sitting directly before 120.9 and 121.8.

    Returns (changed, detail) where detail names the worst disagreeing bar for a human.
    """
    if cur is None or new is None or not len(cur) or not len(new):
        return False, ""
    j = cur.merge(new, on="time", how="inner", suffixes=("_old", "_new"))
    if not len(j):
        return False, ""                     # no overlap, so nothing to compare
    old_c = j["close_old"].astype(float).abs()
    ratio = (j["close_old"].astype(float) - j["close_new"].astype(float)).abs() / old_c.where(
        old_c > 0, 1.0)
    worst = float(ratio.max())
    if worst <= tol:
        return False, ""
    i = int(ratio.idxmax())
    when = pd.to_datetime(int(j["time"].iloc[i]), unit="s", utc=True).tz_convert("US/Eastern")
    return True, ("the %d bar(s) both pulls share disagree by up to %.1f%% - worst at %s, "
                  "stored %.4f against %.4f now"
                  % (len(j), worst * 100, str(when)[:16],
                     float(j["close_old"].iloc[i]), float(j["close_new"].iloc[i])))

def upsert_master(conn, inst, tf, src, sess, new, allow_split_gap=False):
    """Create or EXTEND the master for (instrument, timeframe, source). Existing rows win
    on overlap — same additive contract as import_nt_ohlc.py."""
    row = conn.execute(
        "SELECT id, filename FROM csv_files WHERE is_master=1 AND instrument=? "
        "AND timeframe=? AND source=?", (inst, tf, src)).fetchone()
    # An unadjusted split in the history makes every rule downstream read a fake move, and it
    # is invisible in a row count or a date span - the only guards a master otherwise has. Stop
    # before it is registered rather than let a lane discover it in a result (TBIS, +$139k).
    gaps = split_like_gaps(new)
    if gaps and not allow_split_gap:
        when, ratio, _nearest, name = gaps[0]
        log("  %s %s (%s): REFUSED - %s opens %.2fx its previous close, which is a %s split the "
            "feed did not adjust (Alpaca missed GE's 1-for-8 on 2021-08-02 the same way). The "
            "history before it is on the old price basis, so every rule downstream would read a "
            "fake move. Re-pull with adjustment=raw and rebase it yourself, or pass "
            "allow_split_gap=True if you have checked this one is real news."
            % (inst, tf, src, when, ratio, name))
        return

    rebased_note = None
    if row:
        mid, fn = row
        cur = pd.read_csv(os.path.join(UP, fn))
        changed, detail = split_basis_changed(cur, new)
        if changed:
            # The stored history is on a stale price basis. Keeping it would splice two bases
            # into one series; the only honest options are to replace it wholly or to stop.
            covers = (int(new["time"].min()) <= int(cur["time"].min())
                      and int(new["time"].max()) >= int(cur["time"].max()))
            if not covers:
                log("  %s %s (%s): REFUSED - the split basis changed (%s), and this pull does "
                    "not cover the stored span, so replacing it would drop history. Re-run with "
                    "--start at or before %s to rebuild it."
                    % (inst, tf, src, detail,
                       str(pd.to_datetime(int(cur["time"].min()), unit="s", utc=True).date())))
                return
            merged = new.sort_values("time").reset_index(drop=True)
            rebased_note = ("REBASED onto the new split basis - %s. The stored bars were "
                            "replaced wholesale rather than spliced." % detail)
            log("  %s %s (%s): %s" % (inst, tf, src, rebased_note))
        else:
            merged = (pd.concat([cur, new], ignore_index=True)
                        .drop_duplicates(subset="time")
                        .sort_values("time").reset_index(drop=True))
    else:
        mid, fn = None, f"master_{uuid.uuid4().hex[:8]}.csv"
        merged = new
    # A rebase legitimately replaces history and may hold fewer rows, so it has to say so;
    # any other write still has to grow.
    write_master_csv(merged, os.path.join(UP, fn), allow_shrink=bool(rebased_note),
                     shrink_reason=(rebased_note or ""))
    d0 = str(pd.to_datetime(merged["time"].min(), unit="s", utc=True).tz_convert("US/Eastern").date())
    d1 = str(pd.to_datetime(merged["time"].max(), unit="s", utc=True).tz_convert("US/Eastern").date())
    if mid:
        conn.execute("UPDATE csv_files SET rows=?, date_from=?, date_to=?, session=? WHERE id=?",
                     (len(merged), d0, d1, sess, mid))
        log(f"  extended {inst} {tf} ({src}): -> {len(merged):,} rows, {d0}..{d1}")
    else:
        name = f"{inst} {tf} (Alpaca {sess.upper()})"
        conn.execute(
            "INSERT INTO csv_files (name,filename,instrument,timeframe,rows,date_from,"
            "date_to,created_at,is_master,source,provenance,session) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (name, fn, inst, tf, len(merged), d0, d1, datetime.now().isoformat(), 1, src, "", sess))
        log(f"  NEW master {name}: {len(merged):,} rows, {d0}..{d1} -> {fn}")


def main():
    ap = argparse.ArgumentParser(description="Import Alpaca intraday stock bars into the AUGUR library.")
    ap.add_argument("--symbols", default="AAPL,MSFT,NVDA,AMZN,META,TSLA",
                    help="comma-separated tickers (default: mega-cap basket)")
    ap.add_argument("--timeframe", default="5Min", help="1Min,5Min,15Min,1Hour,1Day (default 5Min)")
    ap.add_argument("--start", default="2016-01-01", help="YYYY-MM-DD (Alpaca history starts 2016)")
    ap.add_argument("--end", default=None, help="YYYY-MM-DD (default: now-20min, free-plan safe)")
    ap.add_argument("--feed", default="sip", help="sip (full volume, default) or iex")
    ap.add_argument("--adjustment", default="split", help="raw|split|dividend|spin-off|all (default split)")
    ap.add_argument("--rth", action="store_true", help="filter to the 09:30-16:00 ET cash session")
    ap.add_argument("--check", action="store_true", help="verify the key works, then exit")
    a = ap.parse_args()

    key, secret = load_keys()
    if not key or not secret:
        raise SystemExit(alpaca_keys.HELP)

    tf_tag = TF_TAG.get(a.timeframe.lower())
    if not tf_tag:
        raise SystemExit(f"unsupported --timeframe {a.timeframe!r}; use one of {sorted(TF_TAG)}")

    # Free plan cannot query the most recent 15 minutes — default to a 20-min safety margin.
    end = a.end or (datetime.now(timezone.utc) - timedelta(minutes=20)).strftime("%Y-%m-%dT%H:%M:%SZ")
    start = a.start if "T" in a.start else a.start + "T00:00:00Z"

    if a.check:
        df = fetch_bars("AAPL", "1Day", "2026-01-02T00:00:00Z", "2026-01-10T00:00:00Z",
                        key, secret, a.feed, a.adjustment)
        log(f"KEY OK — fetched {len(df)} daily AAPL bars as a smoke test (feed={a.feed}).")
        if len(df):
            log(f"  sample: {df.iloc[-1].to_dict()}")
        return

    syms = [s.strip().upper() for s in a.symbols.split(",") if s.strip()]
    conn = sqlite3.connect(DB, timeout=30)
    log(f"Alpaca import: {len(syms)} symbols, {a.timeframe} ({tf_tag}), {start[:10]}..{end[:10]}, "
        f"feed={a.feed}, adjustment={a.adjustment}{', RTH only' if a.rth else ''}")
    try:
        for sym in syms:
            log(f"  {sym}: fetching…")
            try:
                df = fetch_bars(sym, a.timeframe, start, end, key, secret, a.feed, a.adjustment)
            except Exception as e:
                log(f"  {sym}: FAILED — {type(e).__name__}: {e}")
                continue
            if df.empty:
                log(f"  {sym}: no bars returned"); continue
            if a.rth:
                df = rth_filter(df)
                if df.empty:
                    log(f"  {sym}: no RTH bars"); continue
            sess = detect_session(df)
            src = f"alpaca_{a.adjustment}_{sess}"
            upsert_master(conn, sym, tf_tag, src, sess, df)
            conn.commit()
    finally:
        conn.commit(); conn.close()
    log("Done.")


if __name__ == "__main__":
    main()
