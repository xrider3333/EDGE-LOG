"""RE-JUDGE BOOKMARKS B11 (the NASDAQ dip book) ON THE LOCKBOX-DRAWDOWN CLAUSE.

WHY (2026-09-09, owner: "re-judge B11 - queue the lockbox-clause version of that stack").
B11 was adopted on a bar that read "raise the champion book's annualised MAR by at least 15
percent". MAR is net over WHOLE-RUN drawdown, and the book risk-clause audit (v73.649,
`tools/book_clause_audit.py`, `BOOK.md` section 10) showed that denominator is one stretch of
tape. B11 is NOT one of the adoptions that was decided on an inert clause - six of its eight legs
DO trade the champion's worst stretch, adding -$52,391 of the stacked -$123,925, so its MAR bar
was doing real work. What the MAR bar could not see is the price: the stack raises the champion's
whole-run drawdown 73 percent and its last-twelve-months drawdown 104 percent ($38,838 ->
$79,330), and it fails a lockbox-drawdown clause outright. This queues the runs that put that
reading on the record as real BOOK cards instead of an offline scan.

WHAT IS AND IS NOT BEING RE-RUN - read this before quoting any result.
  B11's own book is a WALK-FORWARD construct: its parameters are re-chosen every fold, so it
  cannot be replayed as a BOOK job, which by design replays FIXED parameters. What can be run is
  the TRADEABLE representation of the same family - `augur_strategies/NQDIP_1_0.py` at the
  configs its own Auto-Validates crowned. That is a weaker object than the walk-forward book and
  the difference is stated, not hidden:
    * NQ 5m leg  = run #307's crown. Its validate PASSED (lockbox 30 trades, PF 1.24, +$5,920).
    * QQQ 1d leg = run #308's crown. Its validate FAILED, and its lockbox held ZERO trades. It is
      carried anyway, because B11's headline is a QQQ+NQ book and dropping the QQQ half would
      quietly re-scope the claim. Any result on the A2 card inherits that failure.
  So these cards judge "does the tradeable NASDAQ dip family clear a lockbox-drawdown clause on
  top of a book we own", NOT "does the walk-forward book". A pass here would not restore B11; a
  miss here does not by itself retract it either. It prices the thing that can actually be traded.

THE BAR, WRITTEN BEFORE THE RUNS - B11's OWN BAR WITH EXACTLY ONE CLAUSE SWAPPED:
    (1) annualised MAR at least 1.15x the incumbent      [unchanged - B11's +15%]
    (2) LOCKBOX drawdown within 5 percent of it          [was: whole-run drawdown]
    (3) lockbox net at least as large as the incumbent's [unchanged]
  The whole-run drawdown is reported as a CHECK, not a gate, together with how many days the
  added legs traded inside the incumbent's worst stretch. Canonical wording:
  `tools/book_dd_attribution.bar_text()`.

THE CARDS (one window for all of them: 2010-06-07 .. 2026-06-30, lockbox 12 months, so every
card is like for like and the two incumbents are directly comparable):
  CONTROL-A  ORB #234 + ENGU-Q ETH #226, one NQ each - the champion B11 was ACTUALLY judged
             against. This card does not exist yet, which is why B11's claim has never been
             checkable as a stored run; every clause below needs it.
  CAND-A2    CONTROL-A + NQDIP NQ 5m (#307) + NQDIP QQQ 1d (#308) - the full QQQ+NQ shape B11
             claimed. Never run as a book.
  CAND-B1    the ADOPTED book (BOOK #336: ORB #234 + ENGU-Q #309 + 3 ES of TTM #299) plus the
             NQDIP NQ 5m leg - the only version of this question that bears on the book the
             owner trades TODAY. Judged against #336 itself.
  CAND-A1 IS NOT QUEUED: it already exists as stored BOOK run #311 (ORB #234 + ENGU-Q ETH #226 +
  NQDIP #307, same window, same 12-month lockbox). Once CONTROL-A lands, #311 becomes judgeable
  against it without spending a slot.

THE PREDICTION, WRITTEN BEFORE THE RUNS (from `tools/book_dd_attribution.py` on the same legs,
so these cards confirm or refute a written number rather than settle one):
    CONTROL-A  net $793,811   whole DD $71,903   ann.MAR 0.687  lockbox $201,204  LB DD $35,723
    CAND-A2    net $1,857,814 whole DD $154,999  ann.MAR 0.746  lockbox $294,996  LB DD $38,160
               => MAR x1.086, whole-run DD x2.156, LOCKBOX DD x1.068, lockbox net x1.466  -> MISS
    CAND-B1    net $1,595,725 whole DD $74,275   ann.MAR 1.337  lockbox $224,475  LB DD $32,457
               vs BOOK #336 (MAR 2.031, DD $34,329, LB $193,170, LB DD $26,235)
               => MAR x0.659, whole-run DD x2.164, LOCKBOX DD x1.237, lockbox net x1.162 -> MISS
    and, once CONTROL-A exists, the stored BOOK #311 reads
               => MAR x1.008, whole-run DD x1.587, LOCKBOX DD x1.122, lockbox net x1.156  -> MISS

    SO THE PREDICTION IS THAT ALL THREE MISS, AND THE CLAUSE THAT KILLS THEM IS NOT THE RISK ONE.
    Every card fails on MAR: x1.008 and x1.086 against a bar of x1.15, and CAND-B1 at x0.659 makes
    the book the owner trades materially WORSE. B11's headline was MAR x1.35. The gap is the point
    of this exercise - the +35 percent belongs to the walk-forward construction, which re-picks its
    parameters every fold, and does not survive being frozen into a tradeable file.
    A second thing worth predicting out loud because it cuts against the motivating finding:
    swapping the risk clause makes the bar EASIER on the A cards, not harder. Their whole-run
    drawdown ratios are x1.587 and x2.156 while their LOCKBOX drawdown ratios are x1.122 and
    x1.068 - the latter is nearly inside the 5 percent tolerance. The two clauses disagree about
    the direction of the risk here, which is exactly why both are printed on every card.

    python tools/queue_b11_lockbox_rejudge.py          # writes the jobs
    python tools/queue_b11_lockbox_rejudge.py --dry    # prints them and writes nothing
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
TAG = "B11 lockbox re-judge"

# Legs, copied from the stored job docs so nothing is re-specified by hand:
#   ORB / ENGU-Q #309 / TTM  <- BOOK run #336's own legs
#   ENGU-Q ETH #226          <- BOOK run #311's own second leg
#   NQDIP NQ 5m              <- run #307's crowned params (and #311's third leg, identical)
#   NQDIP QQQ 1d             <- run #308's crowned params
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
DIP_NQ = {"strategy": "NQDIP_1_0.py", "instrument": "NQ", "timeframe": "5m", "session": "rth",
          "source": "db_noadj_rth", "cost_pts": 0.0, "mult": 1, "weight": 1,
          "params": {"rsi_len": 5, "pb_hold": 14, "cap_mult": 1.0, "pb_ema": 5, "rsi_exit": 9,
                     "trend_len": 100, "cost_pts_rt": 0.783, "cost_bps": 2.0, "notional": 100000,
                     "use_pb": True, "cap_hold": 5, "use_rsi": True, "cap_q": 0.3, "rsi_thr": 30,
                     "dbl_n": 10, "use_cap": True, "use_dbl": True}}
DIP_QQQ = {"strategy": "NQDIP_1_0.py", "instrument": "QQQ", "timeframe": "1d", "session": "rth",
           "source": "yahoo_adj", "cost_pts": 0.0, "mult": 1, "weight": 1,
           "params": {"rsi_len": 3, "pb_hold": 19, "cap_mult": 1.25, "pb_ema": 10, "rsi_exit": 7,
                      "trend_len": 300, "cost_pts_rt": 0.783, "cost_bps": 2.0, "notional": 100000,
                      "use_pb": True, "cap_hold": 4, "use_rsi": True, "cap_q": 0.4, "rsi_thr": 15,
                      "dbl_n": 14, "use_cap": True, "use_dbl": True}}

JOBS = [
    ("BOOK: %s CONTROL-A - champion of the day (ORB 234 + ENGU-Q ETH 226)" % TAG, [ORB, ENG226]),
    ("BOOK: %s CAND-A2 - champion + NQDIP NQ 5m + NQDIP QQQ 1d" % TAG, [ORB, ENG226, DIP_NQ, DIP_QQQ]),
    ("BOOK: %s CAND-B1 - adopted book 336 + NQDIP NQ 5m" % TAG, [ORB, ENG309, TTM, DIP_NQ]),
]

NOTE = ("Pre-registered bar, B11's own with ONE clause swapped: annualised MAR >= incumbent x1.15, "
        "LOCKBOX drawdown within 5 percent of it, lockbox net >= it. The whole-run drawdown is a "
        "CHECK, not a gate - it is set by one stretch of tape (BOOK.md section 10). Incumbents: "
        "CONTROL-A for the A cards, stored BOOK run #336 for CAND-B1. CAVEAT ON EVERY A CARD: this "
        "is the TRADEABLE NQDIP_1_0 representation of B11, not B11's walk-forward book, which "
        "re-tunes per fold and cannot be replayed as a BOOK job; and the QQQ 1d leg's own validate "
        "(run #308) FAILED with zero lockbox trades. A pass here does not restore B11 and a miss "
        "does not by itself retract it. Driver tools/queue_b11_lockbox_rejudge.py.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true", help="print the jobs and write nothing")
    a = ap.parse_args()

    for leg in [ORB, ENG226, ENG309, TTM, DIP_NQ, DIP_QQQ]:
        p = os.path.join("augur_strategies", leg["strategy"])
        if not os.path.exists(p):
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
            print("\nDRY - would queue: %s\n  %d legs: %s" %
                  (name, len(legs), ", ".join("%s %s %s x%g" % (l["strategy"], l["instrument"],
                                                                l["timeframe"], l.get("weight", 1))
                                              for l in legs)))
            continue
        ref = u.collection("backtests").document()
        ref.set(job)
        print("queued %s\n  -> %s" % (name, ref.id))
    if a.dry:
        print("\n(dry run - nothing was written)")


if __name__ == "__main__":
    main()
