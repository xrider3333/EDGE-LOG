"""Order-flow back-fill for the 10-second capture through NinjaTrader's EdgeLogHistFetch add-on (PAPER-NT8, 2026-10-08).

The capture (C:\\EdgeLog\\ohlc\\<SYM>_10s.csv) has its buy/sell split only while NinjaTrader runs. Hours it was
not running come back as rt=3 rows (prices and volume, no split). Tick Replay on the chart used to refill them,
but no market-day start has loaded any Tick Replay history since 10-04. The add-on
(tools/nt/EdgeLogHistFetch.cs, AddOns folder) fetches the ticks itself; this script is its other half:

  queue   find runs of no-split rows in the last 3 days and drop one request file per run into
          C:\\EdgeLog\\nt_hist\\queue (idempotent: a run already requested is not requested again)
  merge   every finished request whose file has not been merged yet -> tools/repair_10s_from_replay.py
          --master <capture> --sidecar <file> (the existing, guarded merge: never deletes, backs up first)
  bars    queue a plain history pull, e.g. two 2020 ES minute sessions for the TBIS lane
  status  what is queued, running, done, failed

Run by the NT8 sweep every 30 minutes (queue + merge); safe to run by hand any time.
  python tools/nt_hist_backfill.py                      # queue + merge
  python tools/nt_hist_backfill.py --dry-run            # print what it would queue / merge
  python tools/nt_hist_backfill.py bars --instrument "ES 03-20" --period Minute --from 2020-02-28T14:30:00Z \\
         --to 2020-02-28T21:00:00Z --out C:\\EdgeLog\\nt_hist\\out\\ES_0320_1m_20200228.csv
"""
import argparse
import csv
import datetime as dt
import glob
import json
import os
import sys
from zoneinfo import ZoneInfo

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EL = os.environ.get("EDGELOG_HOME") or r"C:\EdgeLog"
ET = ZoneInfo("America/New_York")
SYMS = ("NQ", "ES")
REACH_DAYS = 3            # how far back to look for holes (NinjaTrader tick history is kept for days, not months)
MIN_RUN_ROWS = 6          # ignore a run shorter than a minute
JOIN_GAP_SEC = 1800       # rows closer than 30 min belong to one run


def qdir():
    return os.path.join(EL, "nt_hist", "queue")


def front_contract(root, day):
    sys.path.insert(0, os.path.join(ROOT, "tools"))
    import nt_rollover as R
    return R.label(root, R.front_month(day))


def _iso(ts):
    return dt.datetime.fromtimestamp(ts, dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


MISSING_GAP_SEC = 300     # rows more than 5 min apart inside CME hours = bars missing altogether (NT was off)


def _session_bars(a, b):
    """10 s bar ENDS strictly between a and b that fall in CME trading hours (Sun 18:00 - Fri 17:00 ET,
    daily 17:00-18:00 halt excluded)."""
    sys.path.insert(0, os.path.join(ROOT, "tools"))
    from nt8_freshness_sweep import cme_open
    n, t = 0, a + 60
    while t < b:                                    # minute steps: cheap, a gap is at most a few days
        if cme_open(dt.datetime.fromtimestamp(t, ET)):
            n += 6
        t += 60
    return n


def holes(path, now_ts, reach_days=REACH_DAYS):
    """[(first_end, last_end, n_rows)] holes in the capture: runs of rows that traded but carry no buy/sell
    split, and spans inside CME hours with no rows at all (NinjaTrader off: night mode, sleep, a dead feed).
    For a missing span first/last are the rows either side of it; n_rows is the number of missing bars."""
    lo = now_ts - reach_days * 86400
    runs, cur, prev = [], None, None
    try:
        with open(path, newline="", encoding="utf-8", errors="replace") as f:
            for r in csv.DictReader(f):
                try:
                    t = int(float(r["time"]))
                    if t < lo:
                        continue
                    vol = float(r.get("volume") or 0)
                    flow = float(r.get("buy_vol") or 0) + float(r.get("sell_vol") or 0)
                except (TypeError, ValueError, KeyError):
                    continue
                if prev is not None and t - prev > MISSING_GAP_SEC:
                    miss = _session_bars(prev, t)
                    if miss >= MIN_RUN_ROWS:
                        if cur:
                            runs.append(tuple(cur))
                            cur = None
                        runs.append((prev, t, miss))
                prev = t
                if vol > 0 and flow == 0:
                    if cur and t - cur[1] <= JOIN_GAP_SEC:
                        cur[1], cur[2] = t, cur[2] + 1
                    else:
                        if cur:
                            runs.append(tuple(cur))
                        cur = [t, t, 1]
    except OSError:
        return []
    if cur:
        runs.append(tuple(cur))
    return [r for r in runs if r[2] >= MIN_RUN_ROWS]


def _already(name):
    return any(os.path.exists(os.path.join(qdir(), name + ext)) for ext in (".req", ".req.running", ".done", ".failed"))


def write_req(name, fields):
    os.makedirs(qdir(), exist_ok=True)
    tmp = os.path.join(qdir(), name + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        for k, v in fields.items():
            f.write(f"{k}={v}\n")
    os.replace(tmp, os.path.join(qdir(), name + ".req"))


def queue(now_ts=None, ohlc_dir=None, dry_run=False, log=print):
    now_ts = now_ts or int(dt.datetime.now(dt.timezone.utc).timestamp())
    ohlc_dir = ohlc_dir or os.path.join(EL, "ohlc")
    made = []
    for sym in SYMS:
        for first, last, n in holes(os.path.join(ohlc_dir, f"{sym}_10s.csv"), now_ts):
            frm, to = first - 10, last + 1                          # rows are END-stamped: cover the first bar's start
            day = dt.datetime.fromtimestamp(first, ET).date()
            name = f"{sym}_{dt.datetime.fromtimestamp(frm, dt.timezone.utc):%Y%m%dT%H%M}_{n}"
            if _already(name):
                continue
            fields = {"instrument": front_contract(sym, day), "kind": "ticks10s", "from": _iso(frm), "to": _iso(to),
                      "out": os.path.join(ohlc_dir, "replay", f"{name}_backfill.csv"), "sym": sym}
            log(("would queue " if dry_run else "queued ") + f"{name}: {fields['instrument']} {fields['from']}..{fields['to']} ({n} rows)")
            if not dry_run:
                write_req(name, fields)
            made.append(name)
    return made


def _read_req(path):
    d = {}
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                d[k.strip()] = v.strip()
    return d


def merge(ohlc_dir=None, dry_run=False, log=print, run=None):
    """Merge each finished ticks10s request once (state: nt_hist\\merged.json)."""
    ohlc_dir = ohlc_dir or os.path.join(EL, "ohlc")
    state_p = os.path.join(EL, "nt_hist", "merged.json")
    try:
        merged = set(json.load(open(state_p, encoding="utf-8")))
    except Exception:
        merged = set()
    if run is None:
        sys.path.insert(0, os.path.join(ROOT, "tools"))
        import repair_10s_from_replay as RP
        run = RP.main
    done = []
    for p in sorted(glob.glob(os.path.join(qdir(), "*.done"))):
        name = os.path.basename(p)[:-5]
        d = _read_req(p)
        if name in merged or d.get("kind") != "ticks10s" or not os.path.exists(d.get("out", "")):
            continue
        master = os.path.join(ohlc_dir, f"{d.get('sym', name[:2])}_10s.csv")
        log(("would merge " if dry_run else "merging ") + f"{name} -> {master}")
        if dry_run:
            continue
        rc = run(["--master", master, "--sidecar", d["out"]])
        if rc == 0:
            merged.add(name)
            done.append(name)
        else:
            log(f"merge of {name} returned {rc} - left for the next run")
    if done and not dry_run:
        os.makedirs(os.path.dirname(state_p), exist_ok=True)
        with open(state_p + ".tmp", "w", encoding="utf-8") as f:
            json.dump(sorted(merged), f, indent=1)
        os.replace(state_p + ".tmp", state_p)
    return done


def status():
    out = {}
    for p in glob.glob(os.path.join(qdir(), "*")):
        for ext in (".req.running", ".req", ".done", ".failed"):
            if p.endswith(ext):
                out.setdefault(ext.lstrip("."), []).append(os.path.basename(p))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("cmd", nargs="?", default="run", choices=["run", "queue", "merge", "bars", "status"])
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--instrument")
    ap.add_argument("--period", default="Minute")
    ap.add_argument("--value", default="1")
    ap.add_argument("--from", dest="frm")
    ap.add_argument("--to")
    ap.add_argument("--out")
    a = ap.parse_args(argv)
    if a.cmd == "status":
        print(json.dumps(status(), indent=1))
        return 0
    if a.cmd == "bars":
        if not (a.instrument and a.frm and a.to and a.out):
            print("bars needs --instrument --from --to --out", file=sys.stderr)
            return 2
        name = "bars_" + a.instrument.replace(" ", "_") + "_" + a.frm.replace(":", "").replace("-", "")[:13]
        write_req(name, {"instrument": a.instrument, "kind": "bars", "period": a.period, "value": a.value,
                         "from": a.frm, "to": a.to, "out": a.out})
        print("queued", name)
        return 0
    if a.cmd in ("run", "queue"):
        queue(dry_run=a.dry_run)
    if a.cmd in ("run", "merge"):
        merge(dry_run=a.dry_run)
    return 0


if __name__ == "__main__":
    sys.exit(main())
