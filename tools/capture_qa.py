"""QA list for the 10-second capture (C:\\EdgeLog\\ohlc\\<SYM>_10s.csv) - which sessions and bars a delta read must drop.

WHY (2026-10-10, TV #862 / MANAGER #154). Two faults hide behind rows that look fine:

  ZERO-SPLIT SESSIONS. Before the v2 capture indicator (EdgeLogOHLCExport, deployed 10-02/10-03) the chart's tick
  subscription could die silently while bars kept closing. Every bar then had prices and volume but buy=sell=0 and
  tick_count=0 - and the old 0/1 flag still said rt=1 (live). Whole sessions read as 'perfectly balanced' order flow.
  v2 marks such a bar rt=3 ('live, no ticks'), and no rt=1 zero-tick row exists after 09-28, so this is history -
  but every delta reader over 08..09 sees it unless it skips these sessions.

  VOLUME SPIKES. The first live bar after NinjaTrader (re)connects can carry the volume of the whole gap: 09-24
  13:01:20 and 13:30:30 ET (NQ, ~400k contracts in one 10 s bar, zero ticks) each sit a minute after a reconnect in
  NT's log; 08-25 10:51:50 and 09-02 15:03:50 hit NQ and ES in the same second. A real burst is backed by trades
  (ES 06-30 15:59:50, quarter-end close: 23,208 contracts over 10,345 ticks); a spike is not.

Rules (RTH 09:30-16:00 ET, weekdays, traded bars only):
  session  zero_split   more than half the traded bars carry no buy/sell split (buy_vol + sell_vol == 0); the
                        reason says whether those rows claimed to be live (rt 1/2) or were honestly marked rt=3
  bar      volume_spike one 10 s bar with volume >= 20,000 at more than 50 contracts per counted trade, or
                        >= 100,000 with no trades counted at all (a tick-dead session still prints a real
                        25-35k ES closing bar, so zero ticks alone is not enough)

The CSV rows are never touched. Output: C:\\EdgeLog\\ohlc\\_10s_qa.json, rewritten whole each run (idempotent).
Readers: `bad_sessions(sym)` -> set of 'YYYY-MM-DD'; `bad_bars(sym)` -> set of END-stamped unix times.

  python tools/capture_qa.py            # print the findings
  python tools/capture_qa.py --write    # and write the QA list
"""
import argparse
import csv
import datetime as dt
import json
import os
import sys
from zoneinfo import ZoneInfo

EL = os.environ.get("EDGELOG_HOME") or r"C:\EdgeLog"
ET = ZoneInfo("America/New_York")
SYMS = ("NQ", "ES")
ZERO_SPLIT_SHARE = 0.5
MIN_SESSION_ROWS = 120          # 20 min of traded bars, so a 1-minute fragment does not count as a session
SPIKE_VOL = 20000
SPIKE_VOL_PER_TICK = 50
SPIKE_VOL_NO_TICKS = 100000   # a tick-dead session still has real closing prints of 25-35k (ES 16:00 bar)


def qa_path():
    return os.path.join(EL, "ohlc", "_10s_qa.json")


def _rth(d):
    return d.weekday() < 5 and 9 * 60 + 30 <= d.hour * 60 + d.minute < 16 * 60


def scan_rows(rows):
    """rows: iterable of (t_end, volume, buy_plus_sell, tick_count, rt) -> (sessions, spikes). Pure."""
    by_day, spikes = {}, []
    for t, v, flow, tc, rt in rows:
        if v <= 0:
            continue
        d = dt.datetime.fromtimestamp(t - 10, ET)          # END-stamped: the bar's own minute is its start
        if (tc > 0 and v >= SPIKE_VOL and v / tc > SPIKE_VOL_PER_TICK) or (tc <= 0 and v >= SPIKE_VOL_NO_TICKS):
            spikes.append({"t": int(t), "et": dt.datetime.fromtimestamp(t, ET).strftime("%Y-%m-%d %H:%M:%S"),
                           "volume": v, "tick_count": tc, "rt": rt, "reason": "volume_spike"})
        if not _rth(d):
            continue
        s = by_day.setdefault(d.strftime("%Y-%m-%d"), {"traded": 0, "zero": 0, "zero_live": 0, "zero_rt3": 0})
        s["traded"] += 1
        if flow <= 0:
            s["zero"] += 1
            if rt in ("1", "2"):
                s["zero_live"] += 1
            elif rt == "3":
                s["zero_rt3"] += 1
    sessions = []
    for day, s in sorted(by_day.items()):
        if s["traded"] < MIN_SESSION_ROWS or s["zero"] / s["traded"] <= ZERO_SPLIT_SHARE:
            continue
        flagged_live = s["zero_live"] >= s["zero_rt3"]
        sessions.append({"date": day, "reason": "zero_split", "traded_bars": s["traded"], "zero_split_bars": s["zero"],
                         "share": round(s["zero"] / s["traded"], 3),
                         "rows_claimed": "live (rt 1/2)" if flagged_live else "no ticks (rt 3)"})
    return sessions, spikes


def read_rows(path):
    with open(path, newline="", encoding="utf-8", errors="replace") as f:
        r = csv.reader(f)
        next(r, None)
        for row in r:
            try:
                yield (int(float(row[0])), float(row[5] or 0), float(row[7] or 0) + float(row[8] or 0),
                       float(row[9] or 0), row[10].strip())
            except (ValueError, IndexError):
                continue


def build(ohlc_dir=None):
    ohlc_dir = ohlc_dir or os.path.join(EL, "ohlc")
    out = {"generated_utc": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
           "rules": {"session": f"RTH traded bars with buy_vol+sell_vol == 0 > {ZERO_SPLIT_SHARE:.0%} (min {MIN_SESSION_ROWS} bars)",
                     "bar": f"(tick_count > 0 and volume >= {SPIKE_VOL} and volume/tick_count > {SPIKE_VOL_PER_TICK}) or (tick_count == 0 and volume >= {SPIKE_VOL_NO_TICKS})"},
           "note": "rows are never edited; a delta read drops these sessions / bars. tools/capture_qa.py"}
    for sym in SYMS:
        p = os.path.join(ohlc_dir, f"{sym}_10s.csv")
        sessions, spikes = scan_rows(read_rows(p)) if os.path.exists(p) else ([], [])
        out[sym] = {"bad_sessions": sessions, "bad_bars": spikes}
    return out


def write(data, path=None):
    path = path or qa_path()
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1)
    os.replace(tmp, path)


def _load(path=None):
    try:
        return json.load(open(path or qa_path(), encoding="utf-8"))
    except Exception:
        return {}


def bad_sessions(sym, path=None):
    return {s["date"] for s in (_load(path).get(sym) or {}).get("bad_sessions") or []}


def bad_bars(sym, path=None):
    return {int(b["t"]) for b in (_load(path).get(sym) or {}).get("bad_bars") or []}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args(argv)
    data = build()
    for sym in SYMS:
        ss, bb = data[sym]["bad_sessions"], data[sym]["bad_bars"]
        print(f"{sym}: {len(ss)} bad session(s): " + ", ".join(f"{s['date']} ({s['share']:.0%}, {s['rows_claimed']})" for s in ss))
        print(f"{sym}: {len(bb)} spike bar(s): " + ", ".join(f"{b['et']} {b['volume']:,.0f}/{b['tick_count']:.0f}t" for b in bb))
    if a.write:
        write(data)
        print("wrote", qa_path())
    return 0


if __name__ == "__main__":
    sys.exit(main())
