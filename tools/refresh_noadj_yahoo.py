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
# Run:  python tools/refresh_noadj_yahoo.py
import os, sqlite3, time
import pandas as pd, numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UP   = os.path.join(ROOT, "augur_uploads")
DB   = os.path.join(ROOT, "optimizer_history.db")
YTK  = {"NQ": "NQ=F", "ES": "ES=F"}
YINT = {"5m": "5m", "1m": "1m"}


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


def _rth(df):
    et = pd.to_datetime(df["time"], unit="s", utc=True).dt.tz_convert("US/Eastern")
    mins = et.dt.hour * 60 + et.dt.minute
    return df[(mins >= 9*60+30) & (mins < 16*60) & (et.dt.dayofweek < 5)].reset_index(drop=True)


def main():
    try:
        import yfinance as yf
    except Exception as e:
        print("yfinance not installed:", e); return
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
        if str(sess).lower() == "rth":
            new = _rth(new)
        new = new[new["time"] > last]                       # only bars past the seam
        if not len(new):
            print(f"  {fn}: already current (last {pd.to_datetime(last,unit='s')})"); continue
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
