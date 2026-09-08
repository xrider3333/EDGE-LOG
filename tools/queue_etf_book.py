"""Build (and only with --send, queue) the ROUND-25 WEAK-EDGE BOOK as a real BOOK job.

r25 passed its gates as a standalone script. The recorded next step was "ETF masters ->
plugin files -> BOOK validate": get the same legs in front of the runner's own book
machinery (augur_engine/book.py) so the pooled PF / drawdown / 8-slice consistency /
sealed 12-month lockbox come off the house scorer instead of a one-off harness.

WHAT THIS QUEUES
  ETF legs : recomputed from r25's PRE-REGISTERED INCLUSION RULE, not hard-coded — every
             (ticker, cell) with PF >= 1.40, net > 0 and n >= 100 over 2010-06-07 ->
             2025-06-29, measured here by r25's OWN run_cell on the registered 1d masters.
             The selected set is printed so the job is auditable.
  NQ leg   : NQDIP_1_0.py with all four mechanisms on (RSI / DBL / PB / CAP). r25's rule
             selected all four NQ cells, and NQDIP_1_0 *is* those four mechanisms in one
             file, already validated as run #307.

TWO DELIBERATE DIFFERENCES FROM THE r25 SCRIPT — state them, do not quietly "fix" them:
  1. NQ SIZING. r25 sized its NQ legs at ONE full NQ contract ($20/pt), whose notional
     grew ~5x across the window. NQDIP_1_0 sizes to a CONSTANT $100,000 in whole MNQ
     micros, which is what the walk-forward phase adopted and what the ETF legs already
     do ($100k notional per trade). A pooled book whose legs drift apart in size is not
     measuring diversification, so the constant-notional version is the honest one here.
     Expect the NQ contribution to differ from the r25 printout for this reason alone.
  2. WARM-UP. r25 handed its ETF legs a year of pre-window bars (download from 2009-06-01)
     and then dropped trades closing before 2010-06-07. augur_engine/book.py gives every
     leg ONE window, so pinning date_from to 2010-06-07 spends the first ~210 trading days
     of the window warming the 200-day trend filter. The ETF legs therefore start trading
     around mid-2011 in this job and will show fewer trades than the r25 table. Pinning is
     the house rule (rerun-window pinning) and comparability to the other book jobs is
     worth more than the extra year; the alternative (date_from 2009-06-01, which the NQ
     masters would ignore since they start 2010-06-07) is available via --warm.

SIZING/COSTS: every leg bills its own dollars inside the plugin, so each leg carries
cost_pts 0 and mult 1 — a book result is already in dollars and must not be multiplied
again (the bug that stored 20x headlines on runs #258/#261/#262/#263).

Usage:
  python tools/queue_etf_book.py              # print the job JSON, send nothing
  python tools/queue_etf_book.py --warm       # same, window opened at 2009-06-01
  python tools/queue_etf_book.py --send       # queue it (queue-depth guarded)
"""
import argparse
import datetime
import importlib.util
import json
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
from augur_engine.data import find_master, load_master_arrays  # noqa: E402

WIN_FROM, WIN_TO = "2010-06-07", "2025-06-29"
WARM_FROM = "2009-06-01"
LOCKBOX_MONTHS = 12                       # the convention the other book jobs use
PF_MIN, N_MIN = 1.40, 100                 # r25's pre-registered inclusion rule
TICKERS = ["GLD", "TLT", "IWM", "QQQ"]    # r25's ETF universe (SPY is a control, excluded)
CELLS = {
    "DBL7L": ("ETFDIP_DBL7_1_0.py", {}),
    "RSI2L": ("ETFDIP_RSI2_1_0.py", {"allow_shorts": False}),
    "RSI2B": ("ETFDIP_RSI2_1_0.py", {"allow_shorts": True}),
    "PB20L": ("ETFDIP_PB20_1_0.py", {}),
}
MAX_QUEUE_DEPTH = 6                       # same guard tools/queue_t8_books.py uses


def _mod(path):
    sp = importlib.util.spec_from_file_location(os.path.basename(path), path)
    m = importlib.util.module_from_spec(sp)
    sp.loader.exec_module(m)
    return m


def defaults(fn):
    m = _mod(os.path.join(ROOT, "augur_strategies", fn))
    return {k: v["default"] for k, v in m.DEFAULT_PARAMS.items()}


def select_etf_legs():
    """Re-apply r25's inclusion rule to the registered 1d masters. Returns (legs, table)."""
    r25 = _mod(os.path.join(ROOT, "tools", "r25_weak_edge_book.py"))
    lo = pd.Timestamp(WIN_FROM).date()
    legs, table = [], []
    for tk in TICKERS:
        master = find_master(tk, "1d", "rth", "yahoo_adj")
        if master is None:
            raise SystemExit(f"{tk}: no 1d master — run tools/build_etf_masters.py first")
        arr = load_master_arrays(master, date_from=WARM_FROM, date_to=WIN_TO)
        do, dh, dl, dc = arr["open"], arr["high"], arr["low"], arr["close"]
        dts = [d.date() for d in arr["index"]]
        for cell, (plugin, extra) in CELLS.items():
            tr = r25.run_cell(do, dh, dl, dc, dts, cell,
                              shares_fn=lambda de, o=do: r25.NOTIONAL / o[de],
                              cost_fn=lambda de, dx, o=do: r25.ETF_COST / (r25.NOTIONAL / o[de]))
            p = np.array([z[1] for z in tr if z[0] >= lo], float)
            if len(p) == 0:
                continue
            gw = p[p > 0].sum(); gl = -p[p < 0].sum()
            pf = gw / gl if gl > 1e-9 else 99.0
            ok = bool(pf >= PF_MIN and p.sum() > 0 and len(p) >= N_MIN)
            table.append((f"{tk}/{cell}", len(p), float(p.sum()), float(pf), ok))
            if ok:
                params = defaults(plugin); params.update(extra)
                legs.append({"strategy": plugin, "params": params, "instrument": tk,
                             "timeframe": "1d", "session": "rth", "source": "yahoo_adj",
                             "cost_pts": 0, "mult": 1, "weight": 1})
    return legs, table


def nq_leg():
    return {"strategy": "NQDIP_1_0.py", "params": defaults("NQDIP_1_0.py"),
            "instrument": "NQ", "timeframe": "5m", "session": "rth",
            "source": "db_noadj_rth", "cost_pts": 0, "mult": 1, "weight": 1}


def build_job(warm=False):
    etf, table = select_etf_legs()
    print(f"{'leg':14}{'n':>6}{'net$':>11}{'PF':>8}  include")
    for lg, n, net, pf, ok in table:
        print(f"{lg:14}{n:>6}{net:>11,.0f}{pf:>8.3f}  {'YES' if ok else 'no'}")
    print(f"\nrule selected {len(etf)} ETF legs (PF>={PF_MIN}, net>0, n>={N_MIN})")

    legs = etf + [nq_leg()]
    picked = ", ".join(f"{l['instrument']}/{l['strategy'].split('_1_0')[0]}"
                       + ("(both)" if l["params"].get("allow_shorts") else "")
                       for l in etf)
    note = (
        "PRE-REGISTERED. This is ROUND 25's weak-edge book (tools/r25_weak_edge_book.py, "
        "pre-registered 2026-08-25 before any pooled number was computed) put in front of "
        "the app's own BOOK scorer, per the recorded next step 'ETF masters -> plugin "
        "files -> BOOK validate'. NOTHING IS TUNED HERE: every leg runs r25's frozen "
        "parameters, and membership is r25's own mechanical inclusion rule (PF >= 1.40, "
        "net > 0, n >= 100 over 2010-06-07..2025-06-29) recomputed at build time from the "
        "registered 1d masters, not a hand-picked list. Selected: " + picked + ", plus "
        "NQDIP_1_0 (all four NQ dip mechanisms - r25's rule selected all four NQ cells). "
        "Gates to judge it by, also pre-registered: standalone book PF >= 1.25 and MAR >= 8. "
        "TWO KNOWN DIFFERENCES FROM THE r25 PRINTOUT, both deliberate: (1) the NQ leg is "
        "sized to a constant $100k in whole MNQ micros (NQDIP_1_0's WF-phase convention, "
        "and what the ETF legs do) instead of r25's one full NQ contract, whose notional "
        "grew ~5x across the window; (2) a BOOK job gives every leg ONE window, so with "
        "date_from pinned to 2010-06-07 the ETF legs spend their first ~210 trading days "
        "warming the 200-day trend filter, where r25 warmed them on 2009-2010 bars it then "
        "discarded - expect fewer ETF trades here than in the r25 table. Every leg bills "
        "its own dollars inside the plugin, hence cost_pts 0 and mult 1 on each. Data: "
        "Yahoo daily total-return (auto_adjust=True) 1d masters built by "
        "tools/build_etf_masters.py; plugin-vs-r25 parity is 16/16 legs to the cent "
        "(tools/etf_book_parity.py). Yahoo re-scales a total-return series on every "
        "dividend, so this book's numbers are only reproducible against a master built "
        "from the same pull."
    )
    return {
        "type": "book",
        "strategy": "BOOK: r25 weak-edge (ETF dips + NQDIP)",
        "book_name": "ROUND 25 WEAK-EDGE BOOK - %d ETF dip legs + NQDIP_1_0" % len(etf),
        "date_from": (WARM_FROM if warm else WIN_FROM),
        "date_to": WIN_TO,
        "lockbox_months": LOCKBOX_MONTHS,
        "slices": 8,
        "equity_points": 400,
        "mult": 1,
        "legs": legs,
        "note": note,
        "status": "queued",
    }


def send(job):
    os.chdir(r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG")
    import firebase_admin
    from firebase_admin import credentials, firestore
    if not firebase_admin._apps:
        firebase_admin.initialize_app(credentials.Certificate("serviceAccount.json"))
    db = firestore.client()
    u = db.collection("users").document("IO0K35JpLIcH9YK4C0pMNYUzZOM2")
    busy = [(d.id, (d.to_dict() or {}).get("status"), (d.to_dict() or {}).get("type"))
            for d in u.collection("backtests").stream()
            if (d.to_dict() or {}).get("status") in ("queued", "running")]
    print("queue depth (queued+running):", len(busy), busy)
    if len(busy) > MAX_QUEUE_DEPTH:
        print("ABORT - queue too deep, not adding")
        return 1
    doc = dict(job)
    doc["createdAt"] = datetime.datetime.now(datetime.timezone.utc)
    ref = u.collection("backtests").document()
    ref.set(doc)
    print("queued", ref.id, job["strategy"])
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--send", action="store_true", help="actually queue it (guarded)")
    ap.add_argument("--warm", action="store_true",
                    help="open the window at 2009-06-01 so the ETF legs warm up outside it")
    a = ap.parse_args()
    job = build_job(a.warm)
    print("\n" + json.dumps(job, indent=2, default=str))
    print(f"\nSUMMARY  {job['book_name']}\n"
          f"  window        {job['date_from']} -> {job['date_to']}, "
          f"lockbox {job['lockbox_months']} months, {job['slices']} slices\n"
          f"  legs          {len(job['legs'])} "
          f"({len(job['legs']) - 1} ETF + 1 NQ), every leg cost_pts 0 / mult 1\n"
          f"  gates         PF >= 1.25 and MAR >= 8 (r25's pre-registration)")
    if a.send:
        return send(job)
    print("\nNOT SENT. Re-run with --send to queue.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
