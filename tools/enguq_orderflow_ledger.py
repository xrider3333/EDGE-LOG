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


def signal_minutes(leg, trades):
    """Recover each trade's TRUE SIGNAL minute, which is what the pre-registration names.

    MANAGER build review 2026-09-30, finding 1/2. The pre-registration fixes the predictor as
    "the signal bar's order-flow imbalance ... the minute's delta divided by its volume" and says
    "Signal bar, never the fill bar". A paper trade's entry_dt is the FILL bar: the parent rests a
    limit at `close - limit_atr * ATR` on the signal bar i and fills at some j in [i+1, i+10]. So
    the signal must be recovered, not assumed.

    It is recoverable exactly, because the recorded entry price IS that resting limit. Rebuild the
    parent's own ATR (a simple rolling mean of true range over atr_len, with the leading NaNs
    filled by the bar's own true range - augur_strategies/ENGUQ_1M_ETH_R2_1_0.py) and walk back up
    to _N_SCAN bars from the fill, looking for the bar whose limit price matches to within a tick.
    Returns {fill_epoch: signal_epoch}; a trade whose signal cannot be identified is left out and
    reported, never silently mapped to the fill bar.
    """
    import numpy as np
    from augur_engine.data import find_master, load_master_arrays
    lim = float(leg["params"].get("limit_atr") or 0.0)
    if lim <= 0:
        return {}, 0                      # fill == signal when there is no resting limit
    m = find_master(leg.get("instrument") or "NQ", leg.get("timeframe") or "1m",
                    leg.get("session") or "eth", "db_noadj_eth")
    if m is None:
        return {}, 0
    arr = load_master_arrays(m)
    h, l, c = (np.asarray(arr[k], float) for k in ("high", "low", "close"))
    n = len(c)
    tr = np.empty(n); tr[0] = h[0] - l[0]
    tr[1:] = np.maximum(h[1:] - l[1:],
                        np.maximum(np.abs(h[1:] - c[:-1]), np.abs(l[1:] - c[:-1])))
    al = int(leg["params"].get("atr_len") or 52)
    atr = np.full(n, np.nan)
    csum = np.cumsum(tr)
    atr[al - 1:] = (csum[al - 1:] - np.concatenate([[0], csum[:-al]])) / al
    atr = np.where(np.isnan(atr), tr, atr)
    limit_px = c - lim * atr

    import pandas as pd
    idx = pd.DatetimeIndex(arr["index"])
    pos = {int(t.timestamp()): i for i, t in enumerate(idx)}
    out, missed = {}, 0
    for t in trades:
        fe = int(t["entry_dt"].timestamp()); fe -= fe % 60
        j = pos.get(fe)
        px = t.get("entry_px")
        if j is None or px is None:
            missed += 1
            continue
        hit = None
        for k in range(1, SCAN_BARS + 1):
            i = j - k
            if i < 0:
                break
            if abs(limit_px[i] - float(px)) <= 0.125:      # a quarter of an NQ tick
                hit = i
                break
        if hit is None:
            missed += 1
            continue
        se = int(idx[hit].timestamp()); se -= se % 60
        out[fe] = se
    return out, missed


def rows_for(leg_key, today, since=None):
    from api import paper
    if since:
        paper.PAPER_START = since
    leg = next((l for l in paper.PAPER_LEGS if l["key"] == leg_key), None)
    if leg is None:
        return [], None
    r = paper.run_shadow(leg, today) or {}
    # run_shadow never raises, so a missing master (a worktree carries no optimizer_history.db)
    # would otherwise show up here as a quiet "0 trades" instead of an error. Surface it.
    for w in (r.get("warnings") or []):
        if "stale" not in str(w):
            print("   [%s] shadow warning: %s" % (leg_key, w))
    return (r.get("trades") or []), leg


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
        trades, leg = trades if isinstance(trades, tuple) else (trades, None)
        sig_of, unresolved = signal_minutes(leg, trades) if leg else ({}, len(trades))
        last_bar = max((t["exit_dt"] for t in trades), default=None)
        out = []
        for t in trades:
            e, x = t["entry_dt"], t["exit_dt"]
            ep = int(e.timestamp()); ep -= ep % 60
            tot, seen = window(per_min, ep)
            one = per_min.get(ep)
            se = sig_of.get(ep)
            sig = per_min.get(se) if se is not None else None
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
            # MANAGER review: an OPEN trade's exit is stamped at the last bar, so a position
            # younger than 24 hours would be logged as a same-day death. It is unresolved,
            # not a death, and counting it as one biases every fresh entry downward.
            unresolved_row = (last_bar is not None and x >= last_bar and held_h < 24.0)
            out.append(dict(
                entry=e.isoformat(), exit=x.isoformat(),
                survived_day_one=("" if unresolved_row else int(survived)),
                unresolved=int(unresolved_row),
                exited_later_calendar_day=int(next_cal),
                hold_hours=round(held_h, 2), pnl_usd=round(float(t["pnl_usd"]), 2),
                win_minutes_seen=seen,
                win_volume=tot[0], win_delta=tot[1], win_buy=tot[2], win_sell=tot[3],
                win_ticks=tot[4],
                signal_minute=(dt.datetime.utcfromtimestamp(se).isoformat() if se else ""),
                signal_volume=(sig[0] if sig else 0), signal_delta=(sig[1] if sig else 0),
                # PRIMARY, and the only column the pre-registered checkpoint may read.
                imbalance=(round(sig[1] / sig[0], 4) if sig and sig[0] else ""),
                # descriptive only: the whole scan window, and the fill minute itself. Neither
                # may be used at the checkpoint - the fill minute in particular fills into
                # opposing flow by construction (a resting limit buy is hit by sellers).
                window_imbalance=round(tot[1] / tot[0], 4) if tot[0] else "",
                fill_minute_volume=one[0] if one else 0,
                fill_minute_delta=one[1] if one else 0,
                fill_minute_imbalance=(round(one[1] / one[0], 4) if one and one[0] else ""),
            ))
        path = os.path.join(OUTDIR, key + ".csv")
        if out:
            with open(path, "w", newline="") as fh:
                w = csv.DictWriter(fh, fieldnames=list(out[0]))
                w.writeheader(); w.writerows(out)
        cov = [r for r in out if r["imbalance"] != "" and not r["unresolved"]]
        s = [r for r in cov if r["survived_day_one"]]
        d = [r for r in cov if not r["survived_day_one"]]
        print("\n%s: %d trades, %d scored (%d held 24h or more, %d did not); "
              "%d unresolved (still open and under 24h), %d signal bar not recovered"
              % (key, len(out), len(cov), len(s), len(d),
                 sum(r["unresolved"] for r in out), unresolved))
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
