# refresh_noadj_yahoo.py — keep the NON-ADJUSTED masters current for FREE using
# Yahoo =F, no Databento needed. Verified: Yahoo NQ=F/ES=F are RAW front-month
# (non-adjusted — they carry roll gaps), and align with the Databento non-adj
# masters at the seam (ES penny-perfect, NQ ~11pt). So appending Yahoo's recent
# bars extends the non-adj series cleanly.
#
# Yahoo intraday history limits: 5m ~60 days, 1m ~7 days. So this keeps the masters
# CURRENT (recent tail); it cannot backfill deep history (use Databento/TV for that).
# Roll gaps Yahoo carries are CORRECT for a non-adjusted series (they live overnight
# between sessions and don't affect intraday-flat strategies like ORB).
#
# MUST NEVER save a still-forming bar. yf.Ticker(...).history() returns the CURRENT,
# in-progress bar as its last row, and this script only ever appends bars past the
# master's last timestamp -- so a partial bar saved once stays wrong forever (every
# later run only sees timestamps after it and skips it). This bit on 2026-09-24: a run
# at ~15:07 ET saved the NQ 5m bar stamped 15:05 ET with Yahoo's still-forming
# close 30742.00/volume 1708, against Yahoo's own final 30738.75/2502 once that bar
# closed -- the only bad bar among 458 Yahoo-sourced bars in 60 days, fixed by hand
# after the fact. _drop_unclosed() below keeps only bars whose full interval (bar
# start + timeframe + a safety margin) has already elapsed as of "now".
#
# MUST NEVER SAVE A BAR THAT SPANS A CONTRACT SWITCH either. Yahoo's continuous
# front-month series changes contract whenever it likes, including mid-session, and it
# does not mark the change. Twice in 2026 the change landed INSIDE one bar, so the bar
# opened on the expiring contract and closed on the next one (2026-06-15 03:30 ET and
# 2026-09-14 11:30 ET; ROLL_AUDIT.md section 2.7). A bar like that is two contracts
# glued together: it books fake profit for anything holding through it and trips fake
# stops. augur_engine/roll_guard.py recognises one and this script then STOPS appending
# at the last clean bar and says so, rather than storing it. The next quarterly roll is
# December 2026, expiry 2026-12-18.
#
# Run:  python tools/refresh_noadj_yahoo.py
import os, sqlite3, sys, time
import pandas as pd, numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
from augur_engine import roll_guard
UP   = os.path.join(ROOT, "augur_uploads")
DB   = os.path.join(ROOT, "optimizer_history.db")
YTK  = {"NQ": "NQ=F", "ES": "ES=F"}
YINT = {"5m": "5m", "1m": "1m"}
TF_SECONDS = {"5m": 300, "1m": 60}
YAHOO_SETTLE_S = 15 * 60   # Yahoo's CME futures feed runs ~10 min behind; 15 min is safe


def _to_tv(h):
    """yfinance intraday frame -> TV frame (time unix s + OHLCV), UTC seconds."""
    idx = h.index
    idx = idx.tz_convert("UTC") if idx.tz is not None else idx.tz_localize("UTC")
    out = pd.DataFrame({
        "time": (idx.view("int64") // 1_000_000_000),
        "open": h["Open"].values, "high": h["High"].values,
        "low": h["Low"].values, "close": h["Close"].values,
        "volume": h["Volume"].fillna(0).astype("int64").values,
    })
    return out.dropna(subset=["open"]).reset_index(drop=True)


def _drop_unclosed(df, tf, now_s, margin_s=None):
    """Drop bars from a TV-format frame (`_to_tv`'s output; `time` = bar START, unix
    seconds) that cannot have fully closed yet as of `now_s`. Yahoo's history() always
    hands back the still-forming current bar as its last row; keeping it would poison
    a non-adjusted master forever, since later runs only append bars past it (see the
    2026-09-24 header note above). A bar closes at time + tf_seconds; margin_s (default
    YAHOO_SETTLE_S) is extra slack for Yahoo's own lag: its CME futures prices are
    delayed about 10 minutes, so a bar can still be filling there well after its
    nominal close. A skipped bar is not lost - the next run appends it."""
    tf_s = TF_SECONDS[tf]
    if margin_s is None:
        margin_s = YAHOO_SETTLE_S
    if not len(df):
        return df
    return df[df["time"] + tf_s + margin_s <= now_s].reset_index(drop=True)


def _rth(df):
    et = pd.to_datetime(df["time"], unit="s", utc=True).dt.tz_convert("US/Eastern")
    mins = et.dt.hour * 60 + et.dt.minute
    return df[(mins >= 9*60+30) & (mins < 16*60) & (et.dt.dayofweek < 5)].reset_index(drop=True)


def main(now_s=None):
    try:
        import yfinance as yf
    except Exception as e:
        print("yfinance not installed:", e); return
    if now_s is None:
        now_s = int(time.time())
    conn = sqlite3.connect(DB)
    masters = conn.execute(
        "SELECT id,filename,instrument,timeframe,session FROM csv_files "
        "WHERE is_master=1 AND source LIKE 'db_noadj%'").fetchall()
    for mid, fn, inst, tf, sess in masters:
        if inst not in YTK or tf not in YINT:
            print(f"  skip {fn} (no Yahoo support for {inst} {tf})"); continue
        p = os.path.join(UP, fn)
        cur = pd.read_csv(p)
        last = int(cur["time"].max())
        try:
            h = yf.Ticker(YTK[inst]).history(period="60d" if tf == "5m" else "7d",
                                             interval=YINT[tf])
        except Exception as e:
            print(f"  {fn}: Yahoo pull failed: {str(e)[:50]}"); continue
        if h is None or not len(h):
            print(f"  {fn}: no Yahoo data"); continue
        new = _to_tv(h)
        n_before = len(new)
        new = _drop_unclosed(new, tf, now_s)
        n_skipped = n_before - len(new)
        if n_skipped:
            print(f"  {fn}: skipped {n_skipped} unfinished bar(s) (still forming)")
        if str(sess).lower() == "rth":
            new = _rth(new)
        new = new[new["time"] > last]                       # only bars past the seam
        if not len(new):
            print(f"  {fn}: already current (last {pd.to_datetime(last,unit='s')})"); continue
        # Refuse a bar that spans a contract switch. Everything from the suspect bar
        # onwards is held back, not lost: the next run sees it again, once a human has
        # either confirmed the roll or cleared the false alarm.
        new, hit = roll_guard.split_tv_frame(new, after_time=last)
        if hit is not None:
            alert = roll_guard.write_alert(fn, tf, hit)
            print(f"  {fn}: REFUSED an in-bar contract switch. " + roll_guard.describe(hit))
            print(f"    held back {hit['et_date']} onwards"
                  + (f"; alert written to {alert}" if alert else ""))
            if not len(new):
                continue
        merged = (pd.concat([cur, new], ignore_index=True)
                    .drop_duplicates(subset="time").sort_values("time").reset_index(drop=True))
        merged.to_csv(p, index=False)
        d1 = str(pd.to_datetime(merged["time"].max(), unit="s", utc=True).tz_convert("US/Eastern").date())
        conn.execute("UPDATE csv_files SET rows=?, date_to=? WHERE id=?", (len(merged), d1, mid))
        conn.commit()
        print(f"  {fn}: +{len(new):,} bars -> {len(merged):,} total, now through {d1}")
    conn.close()
    print("Done. Non-adj masters extended from Yahoo (free, raw front-month).")


if __name__ == "__main__":
    main()
