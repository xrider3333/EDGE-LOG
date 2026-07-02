# import_nt_ohlc.py — pull NinjaTrader OHLC+order-flow exports
# (C:\EdgeLog\ohlc\*.csv, written by the EdgeLogOHLCExport indicator) into the
# AUGUR library as masters tagged 'nt_noadj_<session>', PRESERVING the order-flow
# columns (delta/buy_vol/sell_vol/tick_count/rt) that the generic TradingView
# watch-folder ingest would silently drop.
#
# Mirrors the refresh_noadj_yahoo.py pattern: talks to optimizer_history.db +
# augur_uploads directly via sqlite3/pandas — it does NOT import the Streamlit app.
# Idempotent + additive: re-running EXTENDS the matching master (dedupe by time,
# existing rows win on overlap), exactly like the Yahoo refresher.
#
# Run:  python tools/import_nt_ohlc.py
import os, sys, sqlite3, glob, uuid, re
from datetime import datetime
import pandas as pd

ROOT    = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from augur_engine.data_quality import structural_report   # per-pull gate (stack pill 2.2)
UP      = os.path.join(ROOT, "augur_uploads")
DB      = os.path.join(ROOT, "optimizer_history.db")
SRC_DIR = os.environ.get("EDGELOG_NT_OHLC", r"C:\EdgeLog\ohlc")
LOG     = os.path.join(os.path.dirname(os.path.abspath(__file__)), "import_nt_ohlc.log")


def log(msg):
    """Print AND append to import_nt_ohlc.log (so the scheduled task is debuggable
    even when run windowless via pythonw)."""
    line = f"{datetime.now():%Y-%m-%d %H:%M:%S}  {msg}"
    print(line)
    try:
        with open(LOG, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except Exception:
        pass


def _root(fn):
    m = re.match(r"([A-Za-z]+)_", os.path.basename(fn))
    return m.group(1).upper() if m else ""


def _tf(fn):
    m = re.search(r"_(\d+)\s*([smhdSMHD])", os.path.basename(fn))
    return (m.group(1) + m.group(2).lower()) if m else ""


def _session(df):
    """24h capture -> 'eth'; a 09:30-16:00 ET-only file -> 'rth'."""
    et = pd.to_datetime(df["time"], unit="s", utc=True).dt.tz_convert("US/Eastern")
    mins = et.dt.hour * 60 + et.dt.minute
    inside = ((mins >= 9 * 60 + 30) & (mins < 16 * 60)).mean()
    return "rth" if inside > 0.98 else "eth"


STALE_MIN  = 20                                # capture is "stale" if no bar in this many min
STALE_FLAG = os.path.join(os.path.dirname(SRC_DIR), "ohlc", "_STALE.flag")


def _market_open(now_utc):
    """Approx CME ES/NQ Globex hours: Sun 18:00 ET -> Fri 17:00 ET, minus the daily
    17:00-18:00 ET maintenance break. Good enough to decide if staleness is alarming."""
    et = now_utc.tz_convert("US/Eastern")
    wd, h = et.weekday(), et.hour + et.minute / 60.0   # Mon=0 .. Sun=6
    if wd == 5:  return False                            # Saturday
    if wd == 6:  return h >= 18                          # Sunday opens 18:00
    if wd == 4:  return h < 17                           # Friday closes 17:00
    return not (17 <= h < 18)                            # Mon-Thu: daily break 17-18


def _health_check(fresh):
    """Warn (log + _STALE.flag) if capture has gone stale DURING market hours —
    i.e. NT is off or the charts/AddOn aren't running. Clears the flag when healthy."""
    now = pd.Timestamp.now(tz="UTC")
    if not fresh or not _market_open(now):
        try: os.remove(STALE_FLAG)
        except OSError: pass
        return
    stale = []
    for name, t in fresh.items():
        age = (now - pd.to_datetime(t, unit="s", utc=True)).total_seconds() / 60.0
        if age > STALE_MIN:
            stale.append(f"{name} ({age:.0f} min old)")
    if stale:
        msg = "STALE during market hours — capture may be down (NT off / charts closed): " + ", ".join(stale)
        log("  ⚠ " + msg)
        try:
            with open(STALE_FLAG, "w", encoding="utf-8") as fh:
                fh.write(f"{now:%Y-%m-%d %H:%M:%S}Z  {msg}\n")
        except OSError: pass
    else:
        try: os.remove(STALE_FLAG)
        except OSError: pass


def main():
    files = sorted(glob.glob(os.path.join(SRC_DIR, "*.csv")))
    if not files:
        log(f"No CSVs in {SRC_DIR} — apply the EdgeLogOHLCExport indicator first.")
        return
    conn = sqlite3.connect(DB, timeout=30)
    fresh = {}                                          # basename -> newest bar unix-sec (health-check)
    for f in files:
        inst, tf = _root(f), _tf(f)
        if not inst or not tf:
            log(f"  skip (can't parse name): {os.path.basename(f)}"); continue
        new = pd.read_csv(f)
        if "time" not in new.columns or new.empty:
            log(f"  skip (no rows): {os.path.basename(f)}"); continue
        fresh[os.path.basename(f)] = int(new["time"].max())
        sess = _session(new)
        src  = f"nt_noadj_{sess}"

        # ── data-quality gate (stack 2.2): structural asserts on the INCOMING frame.
        # Impossible prices/volume -> refuse to merge (source CSV stays put; next run
        # retries after it's fixed). Duplicate/unsorted timestamps only warn — the
        # merge below dedupes+sorts them away.
        rep = structural_report(new, timeframe=tf, source=src, session=sess)
        ck = rep.get("checks", {})
        hard = (ck.get("bad_hl", 0) + ck.get("bad_range", 0)
                + ck.get("neg_volume", 0) + ck.get("nonpos_price", 0))
        if hard:
            log(f"  DATA-QUALITY FAIL {os.path.basename(f)}: "
                f"{ {k: v for k, v in ck.items() if v} } — NOT merged")
            continue
        if rep["verdict"] != "PASS" or ck.get("dup_ts") or ck.get("unsorted_ts"):
            log(f"  data-quality warn {os.path.basename(f)}: "
                f"{ {k: v for k, v in ck.items() if v} }")

        row = conn.execute(
            "SELECT id, filename FROM csv_files WHERE is_master=1 AND instrument=? "
            "AND timeframe=? AND source=?", (inst, tf, src)).fetchone()

        if row:
            mid, fn = row
            cur = pd.read_csv(os.path.join(UP, fn))
            merged = (pd.concat([cur, new], ignore_index=True)
                        .drop_duplicates(subset="time")          # existing wins on overlap
                        .sort_values("time").reset_index(drop=True))
        else:
            mid, fn = None, f"master_{uuid.uuid4().hex[:8]}.csv"
            merged = new.drop_duplicates(subset="time").sort_values("time").reset_index(drop=True)

        merged.to_csv(os.path.join(UP, fn), index=False)
        d0 = str(pd.to_datetime(merged["time"].min(), unit="s", utc=True).tz_convert("US/Eastern").date())
        d1 = str(pd.to_datetime(merged["time"].max(), unit="s", utc=True).tz_convert("US/Eastern").date())

        if mid:
            conn.execute("UPDATE csv_files SET rows=?, date_from=?, date_to=?, session=? WHERE id=?",
                         (len(merged), d0, d1, sess, mid))
            log(f"  extended {inst} {tf} ({src}): -> {len(merged):,} rows, {d0}..{d1}")
        else:
            name = f"{inst} {tf} (NT non-adj {sess.upper()})"
            conn.execute(
                "INSERT INTO csv_files (name,filename,instrument,timeframe,rows,date_from,"
                "date_to,created_at,is_master,source,provenance,session) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (name, fn, inst, tf, len(merged), d0, d1, datetime.now().isoformat(),
                 1, src, "", sess))
            log(f"  NEW master {name}: {len(merged):,} rows, {d0}..{d1} -> {fn}")
    conn.commit(); conn.close()
    _health_check(fresh)
    log("Done.")


if __name__ == "__main__":
    main()
