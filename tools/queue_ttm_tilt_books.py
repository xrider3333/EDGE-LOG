"""Queue the two BOOK runs that follow run #340 (TTMSQZ_3_0_ES30T.py PASSED its pre-registered bar).

Both are clones of BOOK run #336's own job (pYOuka2FnJeb5Ewp3iAD = ORB 234 + ENGU-Q 309 + 3 ES of
TTM 299), so the window, masters, costs, lockbox and leg weights are identical and only the TTM
side changes:

  BOOK-T    the adopted TTM leg swapped for the VALIDATED tilted one (run #340's file, same params,
            same weight 3). The direct question: is the book better with the tilt?
  BOOK-T15  BOOK-T plus a fourth leg - the ES 15-minute Carter cell at the crown config, weight 3 -
            the round-9 near miss. The combination question.

BAR FOR BOTH, WRITTEN BEFORE THEY RUN, against run #336 (net $1,119,697, drawdown $34,329,
annualised MAR 2.03, lockbox $193,170): annualised MAR at least 5 percent above #336 at a whole-run
drawdown within 5 percent of it, and a lockbox at least as large. The local scan says BOOK-T lands
at MAR x1.045 (a MISS by the same margin round 8 found) and BOOK-T15 at x1.097 with drawdown x1.011
- both are stated here so the runs confirm or refute a written prediction rather than settle one.
BOOK-T15 also carries a caveat that no bar can fix: its 15-minute leg has never been validated on
its own, so a clear result there is a lead for a leg-level validate, NOT an adoption.

    python tools/queue_ttm_tilt_books.py
"""
import os
import sys
import copy
import datetime

os.chdir(r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG")
import firebase_admin
from firebase_admin import credentials, firestore
from google.cloud.firestore_v1 import FieldFilter

if not firebase_admin._apps:
    firebase_admin.initialize_app(credentials.Certificate("serviceAccount.json"))
db = firestore.client()
UID = "IO0K35JpLIcH9YK4C0pMNYUzZOM2"
u = db.collection("users").document(UID)

for f in ("TTMSQZ_3_0_ES30T.py", "TTMSQZ_3_0_ES30N.py"):
    if not os.path.exists(os.path.join("augur_strategies", f)):
        sys.exit(f"ABORT - {f} is not in the runner's checkout (ship first)")

busy = []
for st in ("queued", "running"):
    for d in u.collection("backtests").where(filter=FieldFilter("status", "==", st)).stream():
        x = d.to_dict() or {}
        busy.append((st, str(x.get("strategy"))[:44]))
        if "TTM 299 tilt" in str(x.get("strategy")):
            sys.exit(f"ABORT - a tilt BOOK is already {st} ({d.id}); not queueing twice")
print("queue depth:", len(busy), busy)
if len(busy) > 9:
    sys.exit("ABORT - queue too deep, not adding")

SRC = "pYOuka2FnJeb5Ewp3iAD"          # BOOK run #336
src = u.collection("backtests").document(SRC).get().to_dict() or {}
legs = src.get("legs") or []
if len(legs) != 3 or "TTMSQZ_3_0_ES30N" not in str(legs[2].get("strategy")):
    sys.exit("ABORT - BOOK #336's job does not look as expected; not cloning blind")

DROP = ["claimedBy", "createdAt", "elapsed_s", "fingerprint", "finishedAt", "heartbeat_at",
        "heartbeat_pid", "progress", "result", "run_id", "slices", "startedAt", "status"]
BAR = ("BAR WRITTEN BEFORE THE RUN, against BOOK run #336 (net $1,119,697, drawdown $34,329, "
       "annualised MAR 2.03, lockbox $193,170): annualised MAR at least 5 percent above it at a "
       "whole-run drawdown within 5 percent, and a lockbox at least as large. ")


def clone(name, mutate, note):
    job = {k: copy.deepcopy(v) for k, v in src.items() if k not in DROP}
    job["legs"] = copy.deepcopy(legs)
    mutate(job)
    job.update(strategy=name, book_name=name, status="queued", progress=0, type="book",
               note=note, createdAt=datetime.datetime.now(datetime.timezone.utc))
    ref = u.collection("backtests").document()
    ref.set(job)
    print("queued:", ref.id, "|", name)
    for L in job["legs"]:
        print("   %-26s %-4s %-4s w%.0f  %s" % (L.get("strategy"), L.get("instrument"),
                                                L.get("timeframe"), float(L.get("weight") or 1), L.get("params")))


clone("BOOK: ORB 234 + ENGU-Q 309 + TTM 299 tilt x3",
      lambda j: j["legs"][2].update(strategy="TTMSQZ_3_0_ES30T.py"),
      "THE VALIDATED DEEP-SQUEEZE TILT AS THE BOOK LEG. Run #340 (TTMSQZ_3_0_ES30T.py) PASSED all six "
      "gates on run #299's own four knobs and admissible set, and cleared the bar written before it: "
      "lockbox $6,948 at profit factor 2.38 against run #299's $4,992 at 2.22, whole-run $69,884 at "
      "drawdown $4,549 against $51,709 at $3,740, annualised MAR 0.96 against 0.86. The search "
      "re-crowned run #299's exact cell, so the ONLY difference between this book and #336 is size: "
      "the 188 of 359 trades entered while the hourly squeeze is deep (ratio at or under 0.85) carry "
      "1.5 contracts instead of 1. " + BAR +
      "PREDICTED, from the local scan on this window: MAR x1.045 at unchanged drawdown - a MISS on the "
      "MAR clause by the same margin round 8 found. This run is here to confirm or refute that "
      "prediction under the engine, not to renegotiate the bar.")

clone("BOOK: ORB 234 + ENGU-Q 309 + TTM 299 tilt x3 + TTM ES 15m x3",
      lambda j: (j["legs"][2].update(strategy="TTMSQZ_3_0_ES30T.py"),
                 j["legs"].append(dict(j["legs"][2], strategy="TTMSQZ_3_0_ES30N.py", timeframe="15m"))),
      "BOTH ROUND-8 AND ROUND-9 NEAR MISSES AT ONCE. The validated tilt (run #340) on the 30-minute leg, "
      "plus three ES contracts of the 15-minute Carter cell at the same crown settings - the round-9 "
      "near miss (MAR x1.049 against a x1.05 bar, lockbox x1.053, drawdown flat). They are different "
      "mechanisms: size, and a second tape. " + BAR +
      "PREDICTED, from the local scan: MAR x1.097, drawdown x1.011, lockbox x1.083 - clears. "
      "CAVEAT THAT NO BAR FIXES: the 15-minute leg has never been validated on its own (alone it is "
      "profit factor 1.31 with a positive but thin lockbox of $3,417, and it correlates 0.29 with the "
      "30-minute leg and 0.16 with the baseline book). A clear result here is a LEAD for a leg-level "
      "fenced validate of that cell, NOT an adoption.")
