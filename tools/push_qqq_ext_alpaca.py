"""push_qqq_ext_alpaca.py -- QQQ pre-market / after-hours bars from Alpaca, pushed to the box
for the Webull trade chart (row 74 follow-up, owner 10-31 via MANAGER #237).

Yahoo serves 1-minute extended-hours bars for the last 7 days only; Alpaca's free plan serves
full-volume SIP history at 1 minute. The box has no Alpaca key and gets none: this runs on the
PC (augur_engine/alpaca_keys resolves the key there), keeps only the extended-hours bars
(04:00-09:30 and 16:00-20:00 ET), merges them into C:/EdgeLog/qqq_bars/QQQ_ext_alpaca_{1m,5m}.csv
and copies both files to the box's ~/edgelog/qqq_bars/ (temp name, then an atomic rename).
tools/qqq_bars_publish.py on the box prefers these files day by day; its own yfinance pull
stays the fallback for any day they miss.

Prices are RAW (adjustment=raw), like the regular-session bars the chart draws next to them.
One line per run goes to C:/EdgeLog/logs/push_qqq_ext.log. Keys are never printed.

    python tools/push_qqq_ext_alpaca.py [--days 45] [--no-push]
"""
import argparse
import datetime as dt
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, ROOT)

import qqq_bars_publish as qbp  # noqa: E402

HOME = os.environ.get("EDGELOG_HOME", r"C:\EdgeLog")
LOCAL_DIR = os.path.join(HOME, "qqq_bars")
LOG = os.path.join(HOME, "logs", "push_qqq_ext.log")
BOX = "ubuntu@163.192.117.12"
BOX_DIR = "/home/ubuntu/edgelog/qqq_bars"
SSH_KEY = os.path.expanduser(r"~\.ssh\edgelog_oracle")
ALPACA_TF = {"1m": "1Min", "5m": "5Min"}


def _log(msg):
    line = f"{dt.datetime.now():%Y-%m-%dT%H:%M:%S} {msg}"
    print(line)
    try:
        os.makedirs(os.path.dirname(LOG), exist_ok=True)
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


def ext_rows(df):
    """Alpaca frame (time, open, high, low, close, volume) -> [(epoch, o, h, l, c, v)] of the
    extended-hours bars only."""
    out = []
    if df is None or not len(df):
        return out
    for r in df.itertuples(index=False):
        t = int(r.time)
        if qbp._is_ext_epoch(t):
            out.append((t, float(r.open), float(r.high), float(r.low), float(r.close), float(r.volume)))
    return out


def pull(days, fetch=None, keys=None, now=None):
    """{tf: rows} for the last `days` calendar days, ending 20 minutes ago (Alpaca's free
    plan refuses a newer end)."""
    if fetch is None or keys is None:
        import import_alpaca_stocks as ias
        fetch = fetch or ias.fetch_bars
        keys = keys or ias.load_keys()
    key, secret = keys[0], keys[1]
    now = now or dt.datetime.now(dt.timezone.utc)
    end = (now - dt.timedelta(minutes=20)).strftime("%Y-%m-%dT%H:%M:%SZ")
    start = (now - dt.timedelta(days=days)).strftime("%Y-%m-%dT00:00:00Z")
    return {tf: ext_rows(fetch("QQQ", atf, start, end, key, secret, feed="sip", adjustment="raw"))
            for tf, atf in ALPACA_TF.items()}


def push_files(paths, run=subprocess.run):
    ssh = ["ssh", "-i", SSH_KEY, "-o", "BatchMode=yes", BOX]
    for p in paths:
        name = os.path.basename(p)
        r = run(["scp", "-q", "-i", SSH_KEY, "-o", "BatchMode=yes", p, f"{BOX}:{BOX_DIR}/{name}.tmp"],
                capture_output=True, text=True, timeout=300)
        if r.returncode != 0:
            raise RuntimeError(f"scp {name}: {(r.stderr or '').strip()[:200]}")
        r = run(ssh + [f"mv -f {BOX_DIR}/{name}.tmp {BOX_DIR}/{name}"], capture_output=True, text=True, timeout=60)
        if r.returncode != 0:
            raise RuntimeError(f"mv {name}: {(r.stderr or '').strip()[:200]}")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--days", type=int, default=45)
    ap.add_argument("--no-push", action="store_true")
    a = ap.parse_args(argv)
    try:
        got = pull(a.days)
        files = []
        for tf, rows in got.items():
            p = os.path.join(LOCAL_DIR, f"QQQ_ext_alpaca_{tf}.csv")
            n = qbp.merge_bar_csv(p, rows)
            files.append(p)
            _log(f"OK {tf}: {len(rows)} extended-hours bars pulled ({a.days} d), {n} in {p}")
        if not a.no_push:
            push_files(files)
            _log(f"OK pushed {len(files)} file(s) to {BOX}:{BOX_DIR}")
        return 0
    except SystemExit as e:
        _log(f"FAILED: {e}")
        return 1
    except Exception as e:  # noqa: BLE001 -- one log line, never a key
        _log(f"FAILED: {type(e).__name__}: {str(e)[:300]}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
