"""MEASURE A CONTRACT ROLL THE EVENING IT HAPPENS, AND APPEND IT TO THE ROLL TABLE.

WHY (TTM's ask, 2026-09-27; December 2026 ES expiry is Friday 12-18). The roll table
`tools/data/rolls_<root>.csv` ends at the September 2026 switch. Everything before
2026-06-07 was measured from `databento_raw`, which no longer runs, so from here on a new
switch has to be measured from what we still collect. TTM's guard re-reads the table every
run and the fake squeeze it guards against fires 0-2 days after a roll, so a row that lands
a day late is useless.

HOW THE MEASUREMENT WORKS. We hold two independent feeds for the same instrument:

  * the Yahoo-fed NOADJ master, a continuous front-month series that switches contract
    whenever Yahoo decides to, without marking it;
  * the NinjaTrader capture (the 10-second masters), a separate continuous series that
    switches when the PLATFORM rolls.

They almost never roll at the same minute. So the SPREAD between them - master close minus
capture close, minute by minute - sits flat at some small tracking error, and then STEPS by
one contract's carry when one of the two rolls. The size of that step is the offset; the
minute it happens is the timing. This is exactly how the September 2026 offsets were
recovered (median over 1,630 minutes), and this tool is that method made repeatable.

IT REPORTS, IT DOES NOT SILENTLY DECIDE. `--append` is opt-in. Without it the tool prints
what it found and writes nothing. When it does append, the row carries `status=measured`
and `source=capture_spread`, never `exact` - `exact` is reserved for the 64 switches measured
from contract-level raw data. `measured` means: two independent feeds, a clean step, a stated
sample size and spread. A consumer that wants only fully-trusted rows should ask
`rolls.is_trustworthy(row)` rather than comparing the status string, so this vocabulary can
grow without breaking a guard.

WHAT IT CANNOT DO. It cannot tell you WHICH contract is which - neither feed labels the
contract - so `old` and `new` are filled from the quarterly cycle, not observed. And if BOTH
feeds roll in the same minute the spread never steps and this finds nothing; that is a real
limitation, it is reported as "no step found" rather than guessed at, and the fallback is the
calendar prior in `augur_engine/roll_guard.py`, which arms for the ten days before expiry
regardless of whether a row exists.

    python tools/roll_watch.py --root ES                 # look at the current roll window
    python tools/roll_watch.py --root ES --since 2026-09-10 --until 2026-09-16
    python tools/roll_watch.py --root NQ --selftest      # re-derive the September 2026 answer
    python tools/roll_watch.py --root ES --append        # write the row it found
"""
import argparse
import csv
import datetime as dt
import os
import sqlite3
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
from augur_engine import roll_guard  # noqa: E402

UPLOADS = os.path.join(ROOT, "augur_uploads")
DB = os.path.join(ROOT, "optimizer_history.db")
TABLE_DIR = os.path.join(ROOT, "tools", "data")

# The reference series: the Yahoo-fed 1-minute 24-hour master, and the NinjaTrader capture.
MASTER = {"NQ": "NOADJ_NQ_1m_ETH.csv", "ES": "NOADJ_ES_1m_ETH.csv"}
CAPTURE_SOURCE = "nt_noadj_eth"

# A step has to be at least this share of the expected carry to count as a roll rather than
# tracking noise, and the two sides have to be quiet enough for the step to be unambiguous.
MIN_STEP_FRAC_OF_CARRY = 0.5
MAX_SIDE_SPREAD_PTS_FRAC = 0.0015   # each side's own p5..p95 must be tighter than this x price
MIN_MINUTES_PER_SIDE = 120
# how far either side of the switch to take the median over. Wide enough for a stable
# median, short enough that the OTHER feed's roll (a day later in September 2026) stays
# outside it.
WINDOW_MINUTES = 600

# The September 2026 answer this method produced, and what the roll table now records.
# tests/test_roll_watch.py fails if these drift apart, because the selftest is the only
# end-to-end proof that the December measurement will work.
SELFTEST = {"NQ": dict(since="2026-09-13", until="2026-09-15", expect=296.5, tol=4.0),
            "ES": dict(since="2026-09-13", until="2026-09-15", expect=67.75, tol=1.0)}


def capture_1m(root, since_sec, until_sec):
    """The NinjaTrader 10-second capture reduced to one close per minute.

    The capture stamps a bar by its END, so the row stamped t+60 carries the closing price of
    the minute that STARTS at t. Keying on the minute start is what lines it up with the
    master, whose bars are stamped by their start.
    """
    conn = sqlite3.connect(DB, timeout=60)
    row = conn.execute(
        "SELECT filename FROM csv_files WHERE is_master=1 AND instrument=? AND timeframe='10s' "
        "AND source=? LIMIT 1", (root, CAPTURE_SOURCE)).fetchone()
    conn.close()
    if not row:
        return None, "no %s 10s capture master registered" % root
    p = os.path.join(UPLOADS, row[0])
    if not os.path.exists(p):
        return None, "capture master %s is not on disk" % row[0]
    d = pd.read_csv(p, usecols=["time", "close"])
    t = d["time"].values.astype("int64")
    keep = (t >= since_sec - 120) & (t <= until_sec + 120)
    d, t = d[keep], t[keep]
    if not len(d):
        return None, "capture holds nothing in that window"
    # bar END -> the minute that bar closes; take the last 10s close inside each minute
    minute_start = ((t - 1) // 60) * 60
    out = (pd.DataFrame({"minute": minute_start, "cap": d["close"].values.astype("float64")})
           .groupby("minute", as_index=False).last())
    return out, None


def master_1m(root, since_sec, until_sec):
    p = os.path.join(UPLOADS, MASTER[root])
    if not os.path.exists(p):
        return None, "master %s is not on disk" % MASTER[root]
    d = pd.read_csv(p, usecols=["time", "close"])
    t = d["time"].values.astype("int64")
    keep = (t >= since_sec) & (t <= until_sec)
    d = d[keep]
    if not len(d):
        return None, "master holds nothing in that window"
    return pd.DataFrame({"minute": d["time"].values.astype("int64"),
                         "mst": d["close"].values.astype("float64")}), None


def master_switch_minute(root, since_sec, until_sec):
    """When the MASTER itself changed contract, from the master alone.

    The table's row describes the master's switch, so its TIMING must come from the master,
    not from the spread. The spread steps at BOTH feeds' rolls - in September 2026 the master
    rolled 09-14 11:30 and the NinjaTrader capture rolled a day later, 09-15 14:26 - and a
    search for "the biggest step in the spread" happily returns the capture's roll with the
    sign inverted. `roll_guard` already recognises the master's own switch and was checked
    against sixteen years of real masters, so it is what decides the minute here.
    """
    p = os.path.join(UPLOADS, MASTER[root])
    if not os.path.exists(p):
        return None, "master %s is not on disk" % MASTER[root]
    d = pd.read_csv(p, usecols=["time", "open", "close", "volume"])
    t = d["time"].values.astype("int64")
    keep = (t >= since_sec) & (t <= until_sec)
    d = d[keep]
    if not len(d):
        return None, "master holds nothing in that window"
    hits = roll_guard.suspect_bars(d["time"].values, d["open"].values, d["close"].values,
                                   volumes=d["volume"].values)
    if not hits:
        return None, ("the master shows no in-bar contract switch in this window - either it "
                      "has not rolled yet, or it rolled cleanly between two bars, which this "
                      "path cannot see")
    return hits[0], None


def spread_series(root, since_sec, until_sec):
    """master close minus capture close, per shared minute."""
    m, err = master_1m(root, since_sec, until_sec)
    if m is None:
        return None, err
    c, err = capture_1m(root, since_sec, until_sec)
    if c is None:
        return None, err
    j = m.merge(c, on="minute", how="inner").sort_values("minute")
    if len(j) < 2 * MIN_MINUTES_PER_SIDE:
        return None, ("only %d minutes are present in BOTH feeds; need at least %d"
                      % (len(j), 2 * MIN_MINUTES_PER_SIDE))
    j["spread"] = j["mst"] - j["cap"]
    return j, None


def measure(root, since_sec, until_sec):
    """Offset and timing for the master's own contract switch.

    Timing from the master. Magnitude from how far the master-minus-capture spread moves
    across that minute, taken over a quiet stretch on each side so the capture's own roll -
    which happens on its own schedule and moves the spread back - cannot contaminate it.
    """
    hit, err = master_switch_minute(root, since_sec, until_sec)
    if hit is None:
        return None, err
    j, err = spread_series(root, since_sec, until_sec)
    if j is None:
        return None, err
    sec = int(hit["time"])
    minutes = j["minute"].values.astype("int64")
    spread = j["spread"].values.astype("float64")

    before = spread[(minutes < sec) & (minutes >= sec - WINDOW_MINUTES * 60)]
    after = spread[(minutes > sec) & (minutes <= sec + WINDOW_MINUTES * 60)]
    if len(before) < MIN_MINUTES_PER_SIDE or len(after) < MIN_MINUTES_PER_SIDE:
        return None, ("not enough shared minutes either side of %s (%d before, %d after; need "
                      "%d each) - the capture may have been down"
                      % (_et(sec), len(before), len(after), MIN_MINUTES_PER_SIDE))
    med_b, med_a = float(np.median(before)), float(np.median(after))
    offset = med_a - med_b
    sb = float(np.percentile(before, 95) - np.percentile(before, 5))
    sa = float(np.percentile(after, 95) - np.percentile(after, 5))
    price = float(np.median(j["mst"].values))
    carry = roll_guard.carry_prior_pts(price)
    tight = max(sb, sa)
    return dict(minute=sec, offset=offset, med_before=med_b, med_after=med_a,
                n_before=len(before), n_after=len(after), spread_before=sb, spread_after=sa,
                carry_prior=carry, price=price, n_shared=len(j), tightest=tight,
                clean=bool(tight <= price * MAX_SIDE_SPREAD_PTS_FRAC),
                master_body=float(hit["body"]), et=_et(sec)), None


def _et(sec):
    return str(pd.to_datetime(int(sec), unit="s", utc=True)
               .tz_convert("US/Eastern").strftime("%Y-%m-%d %H:%M"))


def quarterly_pair(root, switch_sec):
    """(old, new) contract codes from the quarterly cycle - the CYCLE, not an observation.

    Neither feed labels the contract, so these are derived from the calendar. They are a
    label for humans, never the basis of the offset.
    """
    codes = {3: "H", 6: "M", 9: "U", 12: "Z"}
    d = dt.datetime.fromtimestamp(int(switch_sec), dt.timezone.utc).date()
    exp = roll_guard.roll_window_for(d)
    if not exp:
        return "", ""
    e = exp[1]
    nxt_month = {3: 6, 6: 9, 9: 12, 12: 3}[e.month]
    nxt_year = e.year + (1 if e.month == 12 else 0)
    return ("%s%s%d" % (root, codes[e.month], e.year % 10),
            "%s%s%d" % (root, codes[nxt_month], nxt_year % 10))


def append_row(root, best, table_dir=TABLE_DIR, dry=True):
    """Append the measured switch to rolls_<root>.csv, keeping it sorted by time."""
    path = os.path.join(table_dir, "rolls_%s.csv" % root)
    with open(path, encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
        cols = list(csv.DictReader(open(path, encoding="utf-8")).fieldnames)
    sec = int(best["minute"])
    if any(int(r["switch_sec"]) == sec for r in rows):
        return None, "a row for %s is already in the table" % _et(sec)
    old, new = quarterly_pair(root, sec)
    # a switch lands INSIDE a bar unless it falls exactly on a minute boundary
    kind = "mid_session" if sec % 60 == 0 else "in_bar"
    row = {c: "" for c in cols}
    row.update(root=root, old=old, new=new, switch_sec=sec, switch_et=_et(sec),
               offset_pts="%.2f" % best["offset"],
               offset_ci_pts="%.2f..%.2f" % (min(best["med_before"], best["med_after"]) * 0 +
                                             best["offset"] - best["tightest"] / 2.0,
                                             best["offset"] + best["tightest"] / 2.0),
               offset_sec=_et(sec), kind=kind, source="capture_spread", status="measured",
               note=("Measured the evening of the switch by tools/roll_watch.py: the spread "
                     "between the Yahoo-fed master and the NinjaTrader capture stepped %.2f "
                     "points here, from a median of %.2f over %d minutes to %.2f over %d. "
                     "Neither feed labels the contract, so %s and %s come from the quarterly "
                     "cycle, not from an observation."
                     % (best["offset"], best["med_before"], best["n_before"],
                        best["med_after"], best["n_after"], old, new)))
    if dry:
        return row, None
    rows.append(row)
    rows.sort(key=lambda r: int(r["switch_sec"]))
    tmp = path + ".tmp-%d" % os.getpid()
    with open(tmp, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow(r)
    os.replace(tmp, path)
    return row, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default="ES", choices=("NQ", "ES"))
    ap.add_argument("--since", default="", help="YYYY-MM-DD (default: this roll window)")
    ap.add_argument("--until", default="")
    ap.add_argument("--append", action="store_true", help="write the row it found")
    ap.add_argument("--selftest", action="store_true",
                    help="re-derive the September 2026 offset and check it")
    a = ap.parse_args()

    if a.selftest:
        cfg = SELFTEST[a.root]
        a.since, a.until = cfg["since"], cfg["until"]

    if a.since:
        since = int(pd.Timestamp(a.since, tz="US/Eastern").timestamp())
        until = int(pd.Timestamp(a.until or a.since, tz="US/Eastern").timestamp()) + 86400
    else:
        today = dt.date.today()
        win = roll_guard.roll_window_for(today)
        if not win:
            nxt = min(e for y in (today.year, today.year + 1)
                      for e in roll_guard.quarterly_expiries(y) if e > today)
            print("%s: not in a roll window today. The next expiry is %s, so the window opens "
                  "%s. Nothing to measure yet."
                  % (a.root, nxt, nxt - dt.timedelta(days=roll_guard.WINDOW_DAYS_BEFORE)))
            return 0
        since = int(pd.Timestamp(str(win[0]), tz="US/Eastern").timestamp())
        until = int(pd.Timestamp(str(win[1]), tz="US/Eastern").timestamp())

    print("%s: looking for a roll step between %s and %s (ET)" % (a.root, _et(since), _et(until)))
    best, err = measure(a.root, since, until)
    if best is None:
        print("   NO MEASUREMENT: %s" % err)
        print("   The calendar guard in augur_engine/roll_guard.py still arms for the ten days "
              "before expiry, so a caller stays protected without a row.")
        return 2
    print("   step found at %s ET" % _et(best["minute"]))
    print("   offset %+.2f points  (expected carry about %.0f at %s)"
          % (best["offset"], best["carry_prior"], format(best["price"], ",.0f")))
    print("   spread median %+.2f over %d minutes before, %+.2f over %d after"
          % (best["med_before"], best["n_before"], best["med_after"], best["n_after"]))
    print("   each side's own p5..p95 width: %.2f before, %.2f after  -> %s"
          % (best["spread_before"], best["spread_after"],
             "clean" if best["clean"] else "NOISY, treat with care"))

    if a.selftest:
        cfg = SELFTEST[a.root]
        got, want, tol = best["offset"], cfg["expect"], cfg["tol"]
        ok = abs(got - want) <= tol
        print("   SELFTEST: recovered %+.2f against the recorded %+.2f (tolerance %.2f) -> %s"
              % (got, want, tol, "PASS" if ok else "FAIL"))
        return 0 if ok else 1

    row, err = append_row(a.root, best, dry=not a.append)
    if row is None:
        print("   not appended: %s" % err)
        return 0
    print("   row: %s | %s>%s | %s | %s | status=%s"
          % (row["switch_et"], row["old"], row["new"], row["offset_pts"], row["kind"], row["status"]))
    print("   %s" % ("APPENDED to tools/data/rolls_%s.csv" % a.root if a.append
                     else "dry run - re-run with --append to write it"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
