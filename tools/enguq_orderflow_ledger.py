"""ENGU-Q round 63 - record the entry-bar ORDER FLOW of every ENGU-Q shadow trade.

Bar written first: ENGUQ_R63_OFLOW_PREREG.md. Read that before reading any number this
prints. The short version: the 10-second capture starts 2026-06-26, which gives only 8 day-one
survivors so far, so NOTHING here is evidence for a rule. This tool exists so the sample
ACCUMULATES instead of being re-argued from 33 points every month.

WHAT IT DOES. For each ENGU-Q paper leg it asks api.paper for the shadow trades, then for each
trade's SIGNAL MINUTE (never the fill bar - fill-bar conditions leak) it aggregates the
10-second rows stamped inside that minute and writes one row per trade to

    C:\\EdgeLog\\enguq_orderflow\\<LEG>.csv

with the pre-registered predictor `imbalance` = delta / volume, plus the raw parts so a later
reader can re-derive anything without re-running this. Re-running is safe: rows are keyed by
entry timestamp and rewritten in place, so it can be run nightly or on demand.

    python tools/enguq_orderflow_ledger.py                 # record + print the current read
    python tools/enguq_orderflow_ledger.py --since 2026-06-26

READ-ONLY against the capture and against Firestore: it opens the CSV capture and api.paper's
shadow path, and writes only to its own local ledger.

THE SIGNAL MINUTE, and why it is not simply the entry timestamp. api.paper reports a trade's
entry as the FILL bar. This file's parent rests a limit up to 10 bars below the signal close, so
the signal is at or before the fill. Without the engine's own probe the exact signal bar is not
recoverable from the trade tuple alone, so each row carries BOTH reads - the fill minute and the
10-minute window ending at it - and `imbalance` uses the window. That is stated in the
pre-registration as the definition; do not switch to the fill minute later because it reads
better.
"""
import argparse
import csv
import datetime as dt
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

CAPTURE = r"C:\EdgeLog\ohlc\NQ_10s.csv"
OUTDIR = r"C:\EdgeLog\enguq_orderflow"
LEGS = ("ENGUQ_335", "ENGUQ_335_S1", "ENGUQ_335_S2")
SCAN_BARS = 10          # the parent's limit scan, so the signal is within this many minutes


def load_capture(path=CAPTURE):
    """epoch-second -> (volume, delta, buy, sell, ticks), keyed to the minute it falls in."""
    if not os.path.isfile(path):
        return {}
    per_min = {}
    with open(path, newline="") as fh:
        for r in csv.DictReader(fh):
            try:
                t = int(r["time"])
                tc = int(r.get("tick_count") or 0)
            except (TypeError, ValueError):
                continue
            if tc <= 0:                      # rows before the delta capture went live
                continue
            # F3 (audit 2026-09-30): NinjaTrader stamps every 10-second row at the bar's END,
            # so a row stamped 10:00:00 covers 09:59:50-10:00:00 and belongs to 09:59. The
            # repo rule is (time - 1) // 60 - api/paper.py::_resample and
            # tools/backfill_1m_from_10s.py both do it, and a missing -1 once put 11,611 of
            # 12,762 minute opens at odds with the Databento master.
            m = ((t - 1) // 60) * 60
            a = per_min.setdefault(m, [0, 0, 0, 0, 0])
            a[0] += int(float(r.get("volume") or 0))
            a[1] += int(float(r.get("delta") or 0))
            a[2] += int(float(r.get("buy_vol") or 0))
            a[3] += int(float(r.get("sell_vol") or 0))
            a[4] += tc
    return per_min


def window(per_min, fill_epoch, bars=SCAN_BARS):
    """Aggregate the parent's SCAN window: the `bars` minutes BEFORE the fill minute.

    F4 (audit 2026-09-30). The parent rests its limit and scans j in [i+1, i+_N_SCAN], so with
    limit_atr > 0 the fill bar is NEVER the signal bar and the signal lies in
    [fill-_N_SCAN, fill-1]. The first cut of this function aggregated [fill-9, fill], which
    both omitted a legitimate signal minute AND included the fill minute - the exact fill-bar
    read the round-63 pre-registration forbids. Excluding the fill minute is the point.
    """
    tot = [0, 0, 0, 0, 0]
    seen = 0
    for k in range(1, bars + 1):
        a = per_min.get(fill_epoch - 60 * k)
        if a is None:
            continue
        seen += 1
        for i in range(5):
            tot[i] += a[i]
    return tot, seen


def rows_for(leg_key, today, since=None):
    from api import paper
    if since:
        paper.PAPER_START = since
    leg = next((l for l in paper.PAPER_LEGS if l["key"] == leg_key), None)
    if leg is None:
        return []
    r = paper.run_shadow(leg, today) or {}
    # run_shadow never raises, so a missing master (a worktree carries no optimizer_history.db)
    # would otherwise show up here as a quiet "0 trades" instead of an error. Surface it.
    for w in (r.get("warnings") or []):
        if "stale" not in str(w):
            print("   [%s] shadow warning: %s" % (leg_key, w))
    return r.get("trades") or []


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default="2026-06-26",
                    help="first day to ask the shadow for (the capture starts 2026-06-26)")
    args = ap.parse_args()

    per_min = load_capture()
    if not per_min:
        print("no 10-second capture at", CAPTURE)
        return 2
    mins = sorted(per_min)
    print("capture: %d minutes with order flow, %s .. %s UTC"
          % (len(mins), dt.datetime.utcfromtimestamp(mins[0]),
             dt.datetime.utcfromtimestamp(mins[-1])))
    os.makedirs(OUTDIR, exist_ok=True)
    today = dt.date.today()

    for key in LEGS:
        trades = rows_for(key, today, args.since)
        out = []
        for t in trades:
            e, x = t["entry_dt"], t["exit_dt"]
            ep = int(e.timestamp()); ep -= ep % 60
            tot, seen = window(per_min, ep)
            one = per_min.get(ep)
            # F5 (audit 2026-09-30). Two definitions of "survived its first day" disagree, and
            # they disagree in opposite directions on exactly the entries the cash-session gate
            # removes, so the choice is pinned here instead of left implicit.
            #   held_24h - elapsed time >= 24 hours. ENTRY-TIME NEUTRAL, and the definition the
            #              family's whole-history hold table already uses. This one is PRIMARY.
            #   next_cal - the exit falls on a later calendar date. Entry-time BIASED: a 23:00
            #              entry exiting 01:00 held two hours and would score as a survivor.
            # Both are written out so a later reader sees the gap rather than inherits a choice.
            held_h = (x - e).total_seconds() / 3600.0
            survived = held_h >= 24.0
            next_cal = x.date() > e.date()
            out.append(dict(
                entry=e.isoformat(), exit=x.isoformat(),
                survived_day_one=int(survived), exited_later_calendar_day=int(next_cal),
                hold_hours=round(held_h, 2), pnl_usd=round(float(t["pnl_usd"]), 2),
                win_minutes_seen=seen,
                win_volume=tot[0], win_delta=tot[1], win_buy=tot[2], win_sell=tot[3],
                win_ticks=tot[4],
                imbalance=round(tot[1] / tot[0], 4) if tot[0] else "",
                fill_minute_volume=one[0] if one else 0,
                fill_minute_delta=one[1] if one else 0,
                fill_minute_imbalance=(round(one[1] / one[0], 4) if one and one[0] else ""),
            ))
        path = os.path.join(OUTDIR, key + ".csv")
        if out:
            with open(path, "w", newline="") as fh:
                w = csv.DictWriter(fh, fieldnames=list(out[0]))
                w.writeheader(); w.writerows(out)
        cov = [r for r in out if r["imbalance"] != ""]
        s = [r for r in cov if r["survived_day_one"]]
        d = [r for r in cov if not r["survived_day_one"]]
        print("\n%s: %d trades, %d with order flow (%d held 24h or more, %d did not)"
              % (key, len(out), len(cov), len(s), len(d)))
        print("   ledger -> %s" % path)
        if len(s) >= 3 and len(d) >= 3:
            def med(v):
                q = sorted(v); h = len(q) // 2
                return q[h] if len(q) % 2 else (q[h - 1] + q[h]) / 2.0
            ms, md = med([r["imbalance"] for r in s]), med([r["imbalance"] for r in d])
            print("   median imbalance  held 24h+ %+.4f   held less %+.4f   gap %+.4f"
                  % (ms, md, ms - md))
            print("   NOT EVIDENCE at this sample size - the bar is 60 and 60, read once "
                  "(ENGUQ_R63_OFLOW_PREREG.md).")
        else:
            print("   too few on one side to print a median yet.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
