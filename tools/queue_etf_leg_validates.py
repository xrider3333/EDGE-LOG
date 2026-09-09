"""AUTO-VALIDATE THE SEVEN ETF DIP LEGS INDIVIDUALLY - blocker #1 on the run-349 candidate.

WHY (2026-09-09, owner: "validate the seven ETF legs individually"). The ETF stack re-judge
(BOOK.md 10c, run #349) PASSED B1's own bar with the lockbox drawdown swapped in, and the first
of the four things listed between it and an adoption was this: not one of the seven legs has ever
been through a leg-level Auto-Validate. They are round-25 SWEEP CELLS. A book card is not a
substitute for a validate - that is what run #315 taught when NQDIP_1_1's sweep claimed MAR 10.2
on 8-of-8 slices and its validate came back 3-of-8 folds and FAILED.

SEVEN LEGS, SIX VALIDATES - and the reason is worth stating. Two of the seven are the QQQ RSI2
leg with `allow_shorts` False and True. In `augur_engine/auto.py` a bool is a CATEGORICAL that is
ALWAYS searched over both values ("a bool was ALWAYS searched over both values, so `default` could
not pin it"). So one QQQ RSI2 validate searches both directions and crowns one of them: the pair
is a single question, not two. That also settles, on its own, the "two of the seven are near
duplicates" caveat from BOOK.md 10c - they were never two independent legs.

WINDOW, AND THE TWO HOLDOUTS. Validate window 2009-06-01 .. 2026-06-30, which is exactly what
round 25 loaded, so the crown is chosen on the data that picked these cells and nothing more.
That leaves TWO genuinely untouched stretches:
  * the LOCKBOX, 2025-06-30 .. 2026-06-30 - the validate's own holdout, and
  * the PRE-WINDOW, 2006-01-03 .. 2009-05-31 - which round 25 never downloaded at all (it started
    at 2009-06-01) and which is deliberately EXCLUDED from the window above so it stays clean.
The pre-window is the bigger of the two and it contains 2008. It is read offline afterwards at
zero runner cost, per leg, on whatever config each validate crowns.

THE HONEST LIMIT, WRITTEN DOWN FIRST SO IT CANNOT LOOK LIKE AN EXCUSE AFTERWARDS. These legs trade
7 to 13 times a YEAR. Measured now, before the runs:
    leg              n in window   n in 12-mo lockbox   n in pre-window
    DBL7 GLD             130               11                 28
    DBL7 TLT             122                8                 30
    RSI2 IWM             169               13                 30
    DBL7 QQQ             174               12                 22
    RSI2 QQQ             168               11                 24
    PB20 QQQ             221               14                 31
  A twelve-month lockbox holding 8 to 14 trades cannot carry a verdict in EITHER direction. So the
  weight of evidence here is, in order: the 8 walk-forward folds, then the pre-window read, then
  the lockbox. A leg that "passes its lockbox" on 9 trades has not shown much, and a leg that
  fails it on 9 trades has not been refuted. That ordering is fixed now, before any result.

THE BAR, PRE-REGISTERED:
  (1) The Auto-Validate verdict is the primary read. PASS = the leg is validated. WEAK = candidate
      only. FAIL = the leg comes OUT of the ETF book.
  (2) THE CROWN MUST BE THE BOOK'S CELL, OR THE BOOK'S CELL IS NOT VALIDATED. If a validate crowns
      materially different settings from the r25 cell run #338/#349 actually carry, then what has
      been validated is a DIFFERENT leg and the book's version remains unvalidated. This is the run
      #343 precedent exactly: it crowned different settings than BOOK run #342 used, and the note
      on that job had pre-committed that this means "run 342 does not transfer".
  (3) A leg whose crowned config LOSES MONEY in the pre-window is flagged whatever its verdict.
      Recorded now: at the BOOK's own cell, DBL7 QQQ already loses $26,273 across 2006-2009. The
      other five are positive there ($6,292 to $36,388).

THE CONSEQUENCE FOR RUN #349, PRE-REGISTERED. Its PASS was computed with all seven legs. If any
leg FAILS, #349 is re-scored on the survivors and the lockbox clause re-applied to the smaller
book; if that flips it, the candidate is withdrawn. **Run #349's PASS is provisional on these six
validates.** Nothing is adopted before they land.

    python tools/queue_etf_leg_validates.py          # writes the jobs
    python tools/queue_etf_leg_validates.py --dry    # prints them and writes nothing
"""
import argparse
import datetime
import os
import sys

os.chdir(r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG")
import firebase_admin                                        # noqa: E402
from firebase_admin import credentials, firestore            # noqa: E402
from google.cloud.firestore_v1 import FieldFilter            # noqa: E402

UID = "IO0K35JpLIcH9YK4C0pMNYUzZOM2"
DATE_FROM, DATE_TO = "2009-06-01", "2026-06-30"
LOCKBOX_MONTHS, WF_FOLDS, N_TRIALS = 12, 8, 300
# r25's own inclusion floor was n >= 100, and every leg clears it on this window (122-221). The
# usual 300 would reject every cell these mechanisms can produce and hand back a dead validate.
MIN_TRADES = 100
TAG = "ETF leg validate"

# (file, instrument, the r25 cell the BOOK carries - recorded in the note so the crown can be
#  compared against it, NOT passed as params: pinning a validate kills the landscape it exists to
#  produce, so every one of these searches the file's own declared ranges.)
LEGS = [
    ("ETFDIP_DBL7_1_0.py", "GLD", "dbl_n 7, trend_len 200"),
    ("ETFDIP_DBL7_1_0.py", "TLT", "dbl_n 7, trend_len 200"),
    ("ETFDIP_DBL7_1_0.py", "QQQ", "dbl_n 7, trend_len 200"),
    ("ETFDIP_RSI2_1_0.py", "IWM", "rsi_len 2, rsi_thr 10, rsi_exit 5, trend_len 200, allow_shorts True"),
    ("ETFDIP_RSI2_1_0.py", "QQQ", "rsi_len 2, rsi_thr 10, rsi_exit 5, trend_len 200 - the book "
                                  "carries BOTH allow_shorts False and True; this one validate "
                                  "searches the bool and answers for both"),
    ("ETFDIP_PB20_1_0.py", "QQQ", "pb_ema 20, pb_hold 10, trend_len 200"),
]

NOTE_HEAD = (
    "ETF LEG VALIDATE (owner 2026-09-09: validate the seven ETF legs individually). Blocker #1 on "
    "the run-349 candidate (BOOK.md 10c): these legs are round-25 SWEEP CELLS and have never been "
    "validated - the run #315 lesson. Full discovery over the file's own ranges, nothing pinned. "
    "Window 2009-06-01..2026-06-30 is exactly what r25 loaded, which leaves TWO clean holdouts: this "
    "job's 12-month lockbox, and the PRE-WINDOW 2006-01-03..2009-05-31 that r25 never downloaded and "
    "that is deliberately excluded here - it is read offline afterwards and holds 22-31 trades per "
    "leg against the lockbox's 8-14. WEIGHT OF EVIDENCE, FIXED BEFORE THE RUNS: walk-forward folds "
    "first, then the pre-window, then the lockbox - these legs trade 7-13 times a YEAR, so a lockbox "
    "of 8-14 trades cannot carry a verdict either way. BAR: PASS = validated; WEAK = candidate; FAIL "
    "= the leg comes out of the ETF book. AND: if the crown differs materially from the r25 cell the "
    "book carries, the BOOK's cell is NOT thereby validated (the run #343 precedent). Run #349's PASS "
    "is PROVISIONAL on these six. Driver tools/queue_etf_leg_validates.py.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args()

    for fn, _, _ in LEGS:
        if not os.path.exists(os.path.join("augur_strategies", fn)):
            sys.exit("ABORT - %s is not in the runner's checkout (ship first)" % fn)

    if not firebase_admin._apps:
        firebase_admin.initialize_app(credentials.Certificate("serviceAccount.json"))
    u = firestore.client().collection("users").document(UID)

    busy = []
    for stt in ("queued", "running"):
        for d in u.collection("backtests").where(filter=FieldFilter("status", "==", stt)).stream():
            x = d.to_dict() or {}
            busy.append((stt, str(x.get("strategy"))[:44]))
            if TAG in str(x.get("note") or ""):
                sys.exit("ABORT - an %s job is already %s (%s); not queueing twice" % (TAG, stt, d.id))
    print("queue depth: %d %s" % (len(busy), busy))
    if len(busy) > 6:
        sys.exit("ABORT - queue too deep, not adding")

    for fn, inst, cell in LEGS:
        job = {"type": "validate", "strategy": fn, "instrument": inst, "timeframe": "1d",
               "session": "rth", "source": "yahoo_adj", "cost_pts": 0.0, "mult": 1,
               "date_from": DATE_FROM, "date_to": DATE_TO, "lockbox_months": LOCKBOX_MONTHS,
               "wf_folds": WF_FOLDS, "n_trials": N_TRIALS, "min_trades": MIN_TRADES,
               "discover": "auto", "equity_points": 400, "status": "queued",
               "note": "%s BOOK CELL TO COMPARE THE CROWN AGAINST: %s." % (NOTE_HEAD, cell),
               "createdAt": datetime.datetime.now(datetime.timezone.utc)}
        if a.dry:
            print("\nDRY - would queue: %s on %s 1d  (%d trials, %d folds, min_trades %d)"
                  % (fn, inst, N_TRIALS, WF_FOLDS, MIN_TRADES))
            continue
        ref = u.collection("backtests").document()
        ref.set(job)
        print("queued %-24s %-4s -> %s" % (fn, inst, ref.id))
    if a.dry:
        print("\n(dry run - nothing was written)")


if __name__ == "__main__":
    main()
