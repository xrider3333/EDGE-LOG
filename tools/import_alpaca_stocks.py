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
# KEY (never hardcoded; read in this order):
#   1. env  ALPACA_API_KEY / ALPACA_SECRET_KEY
#   2. augur_config.json  {"alpaca_key": "...", "alpaca_secret": "..."}
#   3. tools/.alpaca_keys.json  {"key": "...", "secret": "..."}
#
# Run:
#   python tools/import_alpaca_stocks.py --check
#   python tools/import_alpaca_stocks.py --symbols AAPL,MSFT,NVDA --timeframe 5Min --start 2016-01-01
#   python tools/import_alpaca_stocks.py --symbols AAPL --timeframe 1Min --start 2024-01-01 --rth
import os
import re
import sys
import json
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
    """Resolve the API key/secret without ever hardcoding it. Returns (key, secret)."""
    k, s = os.environ.get("ALPACA_API_KEY"), os.environ.get("ALPACA_SECRET_KEY")
    if k and s:
        return k, s
    for path, kk, sk in ((os.path.join(ROOT, "augur_config.json"), "alpaca_key", "alpaca_secret"),
                         (os.path.join(os.path.dirname(os.path.abspath(__file__)), ".alpaca_keys.json"), "key", "secret")):
        try:
            with open(path, encoding="utf-8") as fh:
                cfg = json.load(fh)
            if cfg.get(kk) and cfg.get(sk):
                return cfg[kk], cfg[sk]
        except Exception:
            pass
    return None, None


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
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    out = pd.DataFrame({
        "time":   pd.to_datetime(df["t"], utc=True).astype("int64") // 10**9,
        "open":   df["o"].astype(float), "high": df["h"].astype(float),
        "low":    df["l"].astype(float), "close": df["c"].astype(float),
        "volume": df["v"].astype("int64"),
    })
    return out.drop_duplicates(subset="time").sort_values("time").reset_index(drop=True)


def rth_filter(df):
    """Keep only the 09:30-16:00 ET cash session."""
    et = pd.to_datetime(df["time"], unit="s", utc=True).dt.tz_convert("US/Eastern")
    mins = et.dt.hour * 60 + et.dt.minute
    return df[(mins >= 9 * 60 + 30) & (mins < 16 * 60)].reset_index(drop=True)


def detect_session(df):
    et = pd.to_datetime(df["time"], unit="s", utc=True).dt.tz_convert("US/Eastern")
    mins = et.dt.hour * 60 + et.dt.minute
    inside = ((mins >= 9 * 60 + 30) & (mins < 16 * 60)).mean()
    return "rth" if inside > 0.98 else "eth"


def upsert_master(conn, inst, tf, src, sess, new):
    """Create or EXTEND the master for (instrument, timeframe, source). Existing rows win
    on overlap — same additive contract as import_nt_ohlc.py."""
    row = conn.execute(
        "SELECT id, filename FROM csv_files WHERE is_master=1 AND instrument=? "
        "AND timeframe=? AND source=?", (inst, tf, src)).fetchone()
    if row:
        mid, fn = row
        cur = pd.read_csv(os.path.join(UP, fn))
        merged = (pd.concat([cur, new], ignore_index=True)
                    .drop_duplicates(subset="time")
                    .sort_values("time").reset_index(drop=True))
    else:
        mid, fn = None, f"master_{uuid.uuid4().hex[:8]}.csv"
        merged = new
    merged.to_csv(os.path.join(UP, fn), index=False)
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
        raise SystemExit(
            "No Alpaca key found. Set env ALPACA_API_KEY / ALPACA_SECRET_KEY, or add\n"
            '  "alpaca_key": "...", "alpaca_secret": "..."  to augur_config.json, or create\n'
            '  tools/.alpaca_keys.json  with  {"key": "...", "secret": "..."}')

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
