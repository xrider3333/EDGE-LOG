"""THE SECOND HOLDOUT: score each crowned ETF leg on 2006-01-03 .. 2009-05-31, which nothing has seen.

WHY THIS EXISTS (2026-09-09). The six ETF leg validates (`tools/queue_etf_leg_validates.py`) run on
2009-06-01 .. 2026-06-30 - exactly the stretch round 25 loaded when it picked these cells - and hold
out the last twelve months. But these legs trade 7 to 13 times a YEAR, so that lockbox contains 8 to
14 trades and cannot carry a verdict in either direction.

There is a second holdout, and it is bigger. Round 25 downloaded ETF data from 2009-06-01, so
**2006-01-03 .. 2009-05-31 was never loaded by the selection at all** - and the validate window above
deliberately excludes it so it stays clean. It holds 22 to 31 trades per leg, roughly two to three
times the lockbox, and it contains the 2008 crisis, which is the one regime a dip-buying book behind
a trend filter most needs to be asked about.

This tool reads each validate's CROWNED config straight off its run document and scores it there.
It costs no runner time: the crown is already chosen, this is a replay.

WHAT IT PRINTS, per leg: the crown, its pre-window trade count, net, profit factor and drawdown, the
same figures for the BOOK's own r25 cell so the two can be compared, and whether the crown and the
book cell are even the same configuration - because if they are not, what the validate validated is
a different leg, and the book's version remains unvalidated (the run #343 precedent).

    python tools/etf_leg_prewindow.py                  # every ETF leg validate it can find
    python tools/etf_leg_prewindow.py --runs 352 353   # only these run numbers
"""
from __future__ import annotations

import argparse
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from augur_engine.book import _leg_trades        # noqa: E402
from tools.book_dd_attribution import all_jobs, DEFAULT_UID, _m   # noqa: E402

PRE_FROM, PRE_TO = "2006-01-03", "2009-05-31"
TAG = "etf leg validate"      # matched case-insensitively: the job note writes it in caps

# The r25 cell each leg carries inside BOOK runs #338/#349, so the crown can be compared with it.
_D7 = {"dbl_n": 7, "trend_len": 200, "cost_bps": 2.0, "notional": 100000}
_R2L = {"rsi_thr_short": 90, "rsi_len": 2, "rsi_thr": 10, "allow_shorts": False,
        "trend_len": 200, "rsi_exit": 5, "cost_bps": 2.0, "notional": 100000}
_R2B = dict(_R2L, allow_shorts=True)
_PB = {"pb_ema": 20, "trend_len": 200, "pb_hold": 10, "cost_bps": 2.0, "notional": 100000}
BOOK_CELL = {
    ("ETFDIP_DBL7_1_0.py", "GLD"): [_D7],
    ("ETFDIP_DBL7_1_0.py", "TLT"): [_D7],
    ("ETFDIP_DBL7_1_0.py", "QQQ"): [_D7],
    ("ETFDIP_RSI2_1_0.py", "IWM"): [_R2B],
    ("ETFDIP_RSI2_1_0.py", "QQQ"): [_R2L, _R2B],   # the book carries BOTH directions here
    ("ETFDIP_PB20_1_0.py", "QQQ"): [_PB],
}
# knobs that are a fixed part of the sizing contract, not settings anyone chose
FIXED = {"notional", "cost_bps"}


def score_window(strategy, instrument, params, date_from, date_to):
    leg = {"strategy": strategy, "instrument": instrument, "timeframe": "1d", "session": "rth",
           "source": "yahoo_adj", "cost_pts": 0, "mult": 1, "weight": 1, "params": dict(params)}
    trades, _ = _leg_trades(leg, date_from, date_to)
    if not trades:
        return dict(n=0, net=0.0, pf=float("nan"), dd=0.0, wins=0)
    p = np.array([x[1] for x in trades], dtype=float)
    days = {}
    for d, v in trades:
        days[d] = days.get(d, 0.0) + v
    cum = np.cumsum([days[k] for k in sorted(days)])
    dd = float(-(cum - np.maximum.accumulate(cum)).min()) if len(cum) else 0.0
    gw, gl = float(p[p > 0].sum()), float(-p[p < 0].sum())
    return dict(n=len(p), net=float(p.sum()), pf=(gw / gl if gl > 1e-9 else float("inf")),
                dd=dd, wins=int((p > 0).sum()))


def same_cell(crown, cell):
    """Do the crown and the book cell agree on every knob anyone actually chose?"""
    keys = (set(crown) | set(cell)) - FIXED
    diff = {k: (crown.get(k), cell.get(k)) for k in sorted(keys) if crown.get(k) != cell.get(k)}
    return (not diff), diff


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, nargs="*", help="only these run numbers")
    ap.add_argument("--uid", default=DEFAULT_UID)
    a = ap.parse_args()

    jobs = all_jobs(a.uid)

    picked = []
    for rid, j in sorted(jobs.items()):
        if a.runs and rid not in a.runs:
            continue
        if not a.runs and TAG not in str(j.get("note") or "").lower():
            continue
        if j.get("type") != "validate" or j.get("status") != "done":
            continue
        picked.append((rid, j))
    if not picked:
        sys.exit("no finished ETF leg validates found yet")

    print("THE SECOND HOLDOUT - %s .. %s, never loaded by round 25 and excluded from the validate window"
          % (PRE_FROM, PRE_TO))
    print("(the validates' own lockbox holds 8-14 trades per leg; this stretch holds 22-31 and contains 2008)\n")
    rows = []
    for rid, j in picked:
        fn, inst = j.get("strategy"), j.get("instrument")
        res = j.get("result") or {}
        crown = dict(res.get("best_params") or {})
        verdict = (res.get("validate") or {}).get("verdict")
        cells = BOOK_CELL.get((fn, inst), [])
        print("=" * 100)
        print("run #%s  %s on %s   validate verdict: %s" % (rid, fn, inst, verdict))
        print("  crown: %s" % ", ".join("%s=%s" % (k, crown[k]) for k in sorted(crown) if k not in FIXED))
        agree = False
        for cell in cells:
            ok, diff = same_cell(crown, cell)
            agree = agree or ok
        if cells:
            print("  book cell%s: %s" % ("s" if len(cells) > 1 else "",
                                         " | ".join(", ".join("%s=%s" % (k, c[k]) for k in sorted(c) if k not in FIXED)
                                                    for c in cells)))
            if agree:
                print("  -> the crown IS the book's cell: this validate speaks for the leg the book carries.")
            else:
                _, diff = same_cell(crown, cells[0])
                print("  -> CROWN DIFFERS from the book's cell on %s. What was validated is a DIFFERENT"
                      % ", ".join(sorted(diff)))
                print("     leg; the book's version remains UNVALIDATED (the run #343 precedent).")
        sc = score_window(fn, inst, crown, PRE_FROM, PRE_TO)
        print("  PRE-WINDOW, crowned config : n=%-4d net $%-10s PF %-6s DD $%s"
              % (sc["n"], _m(sc["net"]), ("%.2f" % sc["pf"]) if sc["pf"] == sc["pf"] else "-", _m(sc["dd"])))
        for i, cell in enumerate(cells):
            sb = score_window(fn, inst, cell, PRE_FROM, PRE_TO)
            print("  PRE-WINDOW, book cell%-5s : n=%-4d net $%-10s PF %-6s DD $%s"
                  % (("" if len(cells) == 1 else " #%d" % (i + 1)), sb["n"], _m(sb["net"]),
                     ("%.2f" % sb["pf"]) if sb["pf"] == sb["pf"] else "-", _m(sb["dd"])))
        rows.append((rid, fn, inst, verdict, agree, sc))

    print("\n" + "=" * 100)
    print("%-5s %-22s %-8s %-8s %6s %11s %7s   %s"
          % ("run", "leg", "verdict", "crown=", "n", "pre net $", "pre PF", "reading"))
    for rid, fn, inst, verdict, agree, sc in rows:
        nm = "%s %s" % (fn.replace("ETFDIP_", "").replace("_1_0.py", ""), inst)
        read = ("pre-window LOSES money" if sc["net"] < 0 else "pre-window positive")
        if not agree:
            read += "; crown != book cell"
        print("%-5s %-22s %-8s %-8s %6d %11s %7s   %s"
              % (rid, nm, verdict, "book" if agree else "OTHER", sc["n"], _m(sc["net"]),
                 ("%.2f" % sc["pf"]) if sc["pf"] == sc["pf"] else "-", read))


if __name__ == "__main__":
    main()
