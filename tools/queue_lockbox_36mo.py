"""
RESEARCH.md ITEM 9 — DOES A 36-MONTH SEALED STRETCH CHANGE THE VERDICT?

WHY (owner 2026-09-20: "do item 7 warm starts first then queue the 36 month revalidates").
The second deep dive found that tuning DEPTH is not the scarce resource — the settings the
engine picks with two or three years of history are as good as the ones it picks with
fifteen — while the 12-month sealed stretch is far too short to confirm anything (months
needed for 80% power: 120 to 404). If the years are free, they are better spent sealed.
RESEARCH.md item 5 therefore proposes 36 months for every leg; this is the test of it.

TWO ARMS, NOT ONE, AND HERE IS WHY. Warm starts (item 7) shipped FIRST, two hours before
these were queued, and they change every fold and every lockbox number. Comparing a new
36-month run against a stored 12-month run would mix the two changes together and answer
neither. So each family runs TWICE on the same file, same window, same budget, warm starts
on in both — the ONLY difference is lockbox_months 12 against 36.

WHAT IS AND IS NOT BEING RE-VALIDATED. Item 9 names crowns #257 (ORB), #243 (NOISE) and
#335 (ENGU-Q). Only #335's file can be re-validated as written: the other two are PINNED
files with zero free knobs, and Auto-Validate refuses those by design (a pinned file records
one config and ships a report with no landscape — CLAUDE.md's standing rule). For those two
the DECLARED parent file is used instead (`_AUGUR_PARENT`: ORB_3_6_E1 -> ORB_3_6,
NOISE_1_1_SBS_V90 -> NOISE_1_0), so what these runs answer for ORB and NOISE is "does the
FAMILY's crown and verdict move when three years leave tuning", not "does #257 itself".
Say that whenever these numbers are quoted.

WINDOWS are pinned to each crown's own run doc, so the tape is the same as the run being
reasoned about; only the sealed stretch's length differs between the arms.

READ IT LIKE THIS, AND WRITE THE READING DOWN BEFORE THE RUNS FINISH:
  • If the crowned config is the same in both arms and the verdict holds, 36 months costs
    nothing and buys a sealed stretch with more than one regime in it — adopt item 5.
  • If the 36-month arm crowns something different, the three years that left tuning were
    load-bearing after all, and item 5 needs the tuning-depth claim re-checked on this
    family rather than on the five the dive tested.
  • A 36-month arm that fails where the 12-month arm passes is NOT by itself an argument
    against the longer stretch — a longer stretch is a harder test, which is the point.
    Compare the profit factors and the trade counts, not the pass flags.

    python tools/queue_lockbox_36mo.py --dry     # print the six jobs, write nothing
    python tools/queue_lockbox_36mo.py           # queue them
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
TAG = "LB36"
LOCKBOX_ARMS = (12, 36)

# (label, crown run, file to search, instrument, timeframe, session, source, cost, from, to)
FAMILIES = [
    ("ORB (parent of crown #257)", 257, "ORB_3_6.py", "NQ", "5m", "rth",
     "db_noadj_rth", 0.533, "2010-06-07", "2026-08-13"),
    ("NOISE (parent of crown #243)", 243, "NOISE_1_0.py", "NQ", "5m", "rth",
     "db_noadj_rth", 0.533, "2010-06-07", "2026-08-12"),
    ("ENGU-Q (crown #335's own file)", 335, "ENGUQ_1M_ETH_R2_1_0.py", "NQ", "1m", "eth",
     "db_noadj_eth", 0.533, "2010-06-07", "2026-06-30"),
]

NOTE = (
    "RESEARCH.md item 9 - the direct test of item 5 (sealed stretch 36 months for every "
    "leg). Paired arms: the SAME file, window, master and 900-trial budget run at "
    "lockbox_months 12 and 36, warm starts (item 7, shipped 2026-09-20 v73.841) ON in "
    "both, so the only difference between the two is the length of the sealed stretch. A "
    "stored 12-month run is NOT the control - it was measured with cold folds and a cold "
    "lockbox, which item 7 changed. For ORB and NOISE the crown's own file is PINNED (zero "
    "free knobs) and Auto-Validate refuses pinned files, so the DECLARED parent is searched "
    "instead: these two answer 'does the FAMILY's crown move when three years leave tuning', "
    "not 'does crown #257/#243 itself'. Read profit factor and trade count across the arms, "
    "not the pass flags: a longer sealed stretch is a harder test by construction. Driver "
    "tools/queue_lockbox_36mo.py.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true", help="print the jobs and write nothing")
    ap.add_argument("--trials", type=int, default=900,
                    help="tuning budget; 900 is the standing default (RESEARCH.md 3a)")
    a = ap.parse_args()

    for _l, _r, fn, *_rest in FAMILIES:
        if not os.path.exists(os.path.join("augur_strategies", fn)):
            sys.exit("ABORT - %s is not in the runner's checkout (ship first)" % fn)

    if not firebase_admin._apps:
        firebase_admin.initialize_app(credentials.Certificate("serviceAccount.json"))
    u = firestore.client().collection("users").document(UID)

    busy = []
    for st in ("queued", "running"):
        for d in u.collection("backtests").where(filter=FieldFilter("status", "==", st)).stream():
            x = d.to_dict() or {}
            busy.append((st, str(x.get("strategy"))[:48]))
            # a validate job's `strategy` is the FILE, so the tag lives in the note -
            # look there, or this guard can never fire (it silently could not before).
            if TAG in str(x.get("note") or ""):
                sys.exit("ABORT - a %s card is already %s (%s); not queueing twice"
                         % (TAG, st, d.id))
    print("queue depth: %d %s" % (len(busy), busy))
    if len(busy) > 6:
        sys.exit("ABORT - queue too deep, not adding")

    queued = []
    for label, crown, fn, inst, tf, sess, src, cost, d0, d1 in FAMILIES:
        for months in LOCKBOX_ARMS:
            name = "%s %dmo - %s" % (TAG, months, label)
            job = {"type": "validate", "strategy": fn, "instrument": inst,
                   "timeframe": tf, "session": sess, "source": src,
                   "cost_pts": cost, "date_from": d0, "date_to": d1,
                   "lockbox_months": months, "n_trials": int(a.trials),
                   # warm starts are the engine default since v73.841; stated here so the
                   # job doc itself records which footing these runs stand on.
                   "warm_days": 300,
                   "note": "[%s] ARM lockbox %d months | crown under test #%d | %s | %s"
                           % (TAG, months, crown, label, NOTE),
                   "status": "queued",
                   "createdAt": datetime.datetime.now(datetime.timezone.utc)}
            if a.dry:
                print("\nDRY - would queue: %s" % name)
                print("   %s %s %s %s | %s..%s | lockbox %d mo | %d trials"
                      % (fn, inst, tf, sess, d0, d1, months, a.trials))
                continue
            ref = u.collection("backtests").document()
            ref.set(job)
            queued.append((name, ref.id))
            print("queued %-46s -> %s" % (name, ref.id))
    if a.dry:
        print("\n(dry run - nothing was written)")
    elif queued:
        print("\n%d jobs queued. Watch C:\\EdgeLog\\runner.log; do NOT poll Firestore."
              % len(queued))


if __name__ == "__main__":
    main()
