"""RE-JUDGE THE WEAK-EDGE ETF BOOK STACK (BOOKMARKS B1, runs #332/#338) ON THE LOCKBOX CLAUSE.

WHY (2026-09-09, owner: "now do the same for the ETF book stack"). Round 25 pre-registered a stack
test for the weak-edge book: added to the champion book of the day, it had to RAISE that book's
annualised MAR by at least 15 percent while giving up no more than 10 percent of its net. It came
back at plus 12 percent and MISSED, so the ETF book was never adopted as a stack - it lives as a
standalone stocks-account book (shadow leg ETFBOOK_332). MAR carries a WHOLE-RUN drawdown in its
denominator, and the book risk-clause audit (BOOK.md section 10) showed that denominator is one
stretch of tape. This queues B1's own bar with exactly one clause swapped.

THIS IS A STRONGER TEST THAN THE B11 RE-JUDGE, AND THE DIFFERENCE MATTERS. B11's book re-tunes
every fold, so only a weaker "tradeable representation" of it could be run. The ETF book has no
such problem: its legs ARE fixed-parameter files, they are exactly the legs BOOK run #338 already
carries, and they are replayed here unchanged. Nothing is approximated.

THE BAR, WRITTEN BEFORE THE RUNS - B1's OWN BAR WITH ONE CLAUSE SWAPPED:
    (1) annualised MAR at least 1.15x the incumbent        [unchanged - B1's own +15%]
    (2) LOCKBOX drawdown within 5 percent of it            [swapped in for the whole-run denominator]
    (3) net at least 90 percent of the incumbent's         [unchanged - B1's "give up <= 10% of net"]
  The whole-run drawdown and the lockbox NET are reported as checks, not gates, together with how
  many days the added legs traded inside the incumbent's worst stretch. Wording:
  `tools/book_dd_attribution.bar_text()`.

WINDOW. Everything runs on 2010-06-07 .. 2026-06-30 with a 12-month lockbox, the same window the
B11 re-judge used, so run #347 is the incumbent for BOTH re-judges and the two are comparable.
That is NOT r25's window (2010-06-07 .. 2025-06-29) - it adds a year, and that year was never
loaded when these legs were selected, so it is genuine holdout for them. Say so when quoting any
number here against B1's recorded plus 12 percent: different window, and B1's recorded figure was
the 20-leg equal-risk weak-edge book while these cards carry the 7 ETF legs of run #338.

THE CARDS:
  ETF-S      the 7 ETF legs alone on the shared window - so the book's own MAR and lockbox can be
             read against the stacks instead of against run #338's different window.
  ETF-A1     run #347 (ORB #234 + ENGU-Q ETH #226, the champion B1 was judged against) + the 7 ETF
             legs at weight 1 - one $100,000 sleeve per leg, which is what a deployment looks like.
  ETF-B1     the ADOPTED book (BOOK #336) + the same 7 legs - does this help what is traded TODAY.
  NOT QUEUED, and here is why: r25 stacked RISK-MATCHED (each side scaled so its daily standard
  deviation matches). On THIS window that scale is x0.991 - the two books' daily sigmas have
  converged ($3,403 against $3,433), against x0.833 on r25's own window. A risk-matched card would
  therefore differ from ETF-A1 by 0.4 percent (scan: net $1,313,442 against $1,318,092, MAR 0.877
  against 0.878, lockbox drawdown $36,908 against $36,950) and would tell us nothing ETF-A1 does
  not. It is recorded here rather than run.

THE PREDICTION, WRITTEN BEFORE THE RUNS (`tools/book_dd_attribution.py`, same legs):
    ETF-S    net $524,281 whole DD $43,818 ann.MAR 0.787 lockbox $52,428 LB DD $25,007
             net/DD 11.96, and 14 of 16 years positive - it has TWO losing years of its own,
             which neither stack card shows because the NQ legs paper over them.
    ETF-A1   net $1,318,092 whole DD $93,429 ann.MAR 0.878 lockbox $253,632 LB DD $36,950
             vs #347 => MAR x1.278 OK, net x1.660 OK, LOCKBOX DD x1.034 OK  -> ** PASS **
             but whole-run DD x1.299, so the OLD clause MISSES.
    ETF-B1   net $1,643,978 whole DD $53,597 ann.MAR 1.910 lockbox $245,598 LB DD $48,867
             vs #336 => MAR x0.940 NO, LOCKBOX DD x1.863 NO                 -> MISS

    SO THIS IS PREDICTED TO BE THE FIRST CASE WHERE THE CLAUSE SWAP CHANGES A VERDICT, AND IT
    CHANGES IT TOWARDS ADOPTING SOMETHING THE OLD CLAUSE BLOCKED. Read that carefully before
    treating it as a recommendation:
      * The disagreement is real, not an inert clause. All seven ETF legs DO trade inside run
        #347's worst stretch (the 2020 crash) - they are dip buyers and that stretch is a crash.
        The whole-run drawdown says the stack costs 30 percent more drawdown; the lockbox drawdown
        says it costs 3 percent. Both are measured; they disagree about the direction of the risk.
      * A PASS here is a CANDIDATE, not an adoption. These seven legs have never been through a
        leg-level Auto-Validate - they are round-25 sweep cells, and a BOOK card is not a substitute
        for a validate (the NQDIP_1_1 lesson, run #315). Two of them are near-duplicates (QQQ RSI2
        long-only and QQQ RSI2 both-sides), which is a concentration the bar does not price.
      * ETF-B1 is the card that bears on the deployed book and it MISSES clearly. Whatever ETF-A1
        says, adding these legs to what is traded today is predicted to cut MAR 6 percent and
        nearly double the lockbox drawdown.

    python tools/queue_etf_lockbox_rejudge.py          # writes the jobs
    python tools/queue_etf_lockbox_rejudge.py --dry    # prints them and writes nothing
"""
import argparse
import copy
import datetime
import os
import sys

os.chdir(r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG")
import firebase_admin                                        # noqa: E402
from firebase_admin import credentials, firestore            # noqa: E402
from google.cloud.firestore_v1 import FieldFilter            # noqa: E402

UID = "IO0K35JpLIcH9YK4C0pMNYUzZOM2"
DATE_FROM, DATE_TO, LOCKBOX_MONTHS = "2010-06-07", "2026-06-30", 12
TAG = "ETF stack lockbox re-judge"

ORB = {"strategy": "ORB_3_6_C2.py", "instrument": "NQ", "timeframe": "5m", "session": "rth",
       "source": "db_noadj_rth", "cost_pts": 0.533, "mult": 20, "weight": 1,
       "params": {"skip_holidays": True, "close_confirm": True, "vpace_filter": 0.7,
                  "breakout_buf": 0.25, "flat_eod": True, "or_bars": 2, "be_after_R": 1.0,
                  "stop_frac": 2.0, "trail_bars": 0, "target_R": 5.5, "partial_exit_R": 0.0,
                  "trade_mode": "First-candle dir", "atr_filter": 0.7}}
ENG226 = {"strategy": "ENGUQ_1M_ETH_FROZEN_1_0.py", "instrument": "NQ", "timeframe": "1m",
          "session": "eth", "source": "db_noadj_eth", "cost_pts": 0.783, "mult": 20, "weight": 1,
          "params": {"buf_atr": 0.9, "vol_mult": 0.8, "ema_len": 1380, "tl_len": 170,
                     "stop_mult": 1.0, "trail_frac": 2.5, "regime_len": 0, "min_brk": 1.3,
                     "breakeven_R": 1.5, "atr_len": 106, "act_R": 2.5}}
ENG309 = {"strategy": "ENGUQ_1M_ETH_ER_1_0.py", "instrument": "NQ", "timeframe": "1m",
          "session": "eth", "source": "db_noadj_eth", "cost_pts": 0.533, "mult": 20, "weight": 1,
          "params": {"buf_atr": 0.3, "tl_len": 206, "trail_frac": 2.5, "breakeven_R": 3.0,
                     "atr_len": 52, "act_R": 1.5, "ema_len": 220, "limit_atr": 0.55, "er_len": 100,
                     "stop_mult": 1.3, "regime_len": 10, "min_brk": 1.6, "vol_mult": 1.1,
                     "er_th": 0.0}}
TTM = {"strategy": "TTMSQZ_3_0_ES30N.py", "instrument": "ES", "timeframe": "30m", "session": "rth",
       "source": "db_noadj_rth", "cost_pts": 0.363, "mult": 50, "weight": 3,
       "params": {"gate_len": 20, "stop_atr": 1.5, "eod_cutoff": 1, "kc_mult": 1.5}}

# The seven ETF legs EXACTLY as BOOK run #338 carries them - copied, not re-specified.
_D7 = {"dbl_n": 7, "trend_len": 200, "cost_bps": 2.0, "notional": 100000}
_R2L = {"rsi_thr_short": 90, "rsi_len": 2, "rsi_thr": 10, "allow_shorts": False,
        "trend_len": 200, "rsi_exit": 5, "cost_bps": 2.0, "notional": 100000}
_R2B = dict(_R2L, allow_shorts=True)
_PB = {"pb_ema": 20, "trend_len": 200, "pb_hold": 10, "cost_bps": 2.0, "notional": 100000}


def etf(fn, inst, params):
    return {"strategy": fn, "instrument": inst, "timeframe": "1d", "session": "rth",
            "source": "yahoo_adj", "cost_pts": 0, "mult": 1, "weight": 1, "params": dict(params)}


ETF7 = [etf("ETFDIP_DBL7_1_0.py", "GLD", _D7),
        etf("ETFDIP_DBL7_1_0.py", "TLT", _D7),
        etf("ETFDIP_RSI2_1_0.py", "IWM", _R2B),
        etf("ETFDIP_DBL7_1_0.py", "QQQ", _D7),
        etf("ETFDIP_RSI2_1_0.py", "QQQ", _R2L),
        etf("ETFDIP_RSI2_1_0.py", "QQQ", _R2B),
        etf("ETFDIP_PB20_1_0.py", "QQQ", _PB)]

JOBS = [
    ("BOOK: %s ETF-S - the 7 ETF legs alone on the shared window" % TAG, list(ETF7)),
    ("BOOK: %s ETF-A1 - champion 347 + 7 ETF legs" % TAG, [ORB, ENG226] + ETF7),
    ("BOOK: %s ETF-B1 - adopted book 336 + 7 ETF legs" % TAG, [ORB, ENG309, TTM] + ETF7),
]

NOTE = ("Pre-registered bar, B1's own stack bar with ONE clause swapped: annualised MAR >= "
        "incumbent x1.15, LOCKBOX drawdown within 5 percent of it, net >= 90 percent of it. The "
        "whole-run drawdown and the lockbox net are CHECKS, not gates - the whole-run number is set "
        "by one stretch of tape (BOOK.md section 10). Incumbents: run #347 for ETF-A1, stored BOOK "
        "run #336 for ETF-B1. Window 2010-06-07..2026-06-30 is NOT r25's window - it adds a year "
        "that was never loaded when these legs were selected, so that year is genuine holdout for "
        "them; and B1's recorded plus 12 percent was the 20-leg equal-risk book, not these 7 ETF "
        "legs. PREDICTED: ETF-A1 PASSES the new clause and MISSES the old one (MAR x1.278, whole-run "
        "drawdown x1.299, LOCKBOX drawdown x1.034) - the first verdict the swap changes; ETF-B1 "
        "MISSES both (MAR x0.940). A pass is a CANDIDATE, not an adoption: none of these seven legs "
        "has ever been through a leg-level Auto-Validate, and two of them are near-duplicates. "
        "Driver tools/queue_etf_lockbox_rejudge.py.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true", help="print the jobs and write nothing")
    a = ap.parse_args()

    for leg in [ORB, ENG226, ENG309, TTM] + ETF7:
        if not os.path.exists(os.path.join("augur_strategies", leg["strategy"])):
            sys.exit("ABORT - %s is not in the runner's checkout (ship first)" % leg["strategy"])

    if not firebase_admin._apps:
        firebase_admin.initialize_app(credentials.Certificate("serviceAccount.json"))
    u = firestore.client().collection("users").document(UID)

    busy = []
    for st in ("queued", "running"):
        for d in u.collection("backtests").where(filter=FieldFilter("status", "==", st)).stream():
            x = d.to_dict() or {}
            busy.append((st, str(x.get("strategy"))[:52]))
            if TAG in str(x.get("strategy")):
                sys.exit("ABORT - a %s card is already %s (%s); not queueing twice" % (TAG, st, d.id))
    print("queue depth: %d %s" % (len(busy), busy))
    if len(busy) > 6:
        sys.exit("ABORT - queue too deep, not adding")

    for name, legs in JOBS:
        job = {"type": "book", "strategy": name, "legs": copy.deepcopy(legs),
               "date_from": DATE_FROM, "date_to": DATE_TO, "lockbox_months": LOCKBOX_MONTHS,
               "slices": 8, "mult": 1, "note": NOTE, "status": "queued",
               "createdAt": datetime.datetime.now(datetime.timezone.utc)}
        if a.dry:
            print("\nDRY - would queue: %s\n  %d legs" % (name, len(legs)))
            continue
        ref = u.collection("backtests").document()
        ref.set(job)
        print("queued %s\n  -> %s" % (name, ref.id))
    if a.dry:
        print("\n(dry run - nothing was written)")


if __name__ == "__main__":
    main()
