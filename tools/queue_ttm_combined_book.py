"""Queue the BOOK run for the COMBINED TTM leg (run #369), against the book the owner runs today.

Clone of run #341's own job - same window, masters, costs and weights - with the TTM leg swapped
from TTMSQZ_3_0_ES30T.py to TTMSQZ_3_0_ES30SS20.py. Written 2026-09-09 after run #353.

    python tools/queue_ttm_ss_book.py
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

FILE = "TTMSQZ_3_0_ES30SSOF2.py"
if not os.path.exists(os.path.join("augur_strategies", FILE)):
    sys.exit(f"ABORT - {FILE} is not in the runner's checkout (ship first)")

busy = []
for st in ("queued", "running"):
    for d in u.collection("backtests").where(filter=FieldFilter("status", "==", st)).stream():
        x = d.to_dict() or {}
        busy.append((st, str(x.get("strategy"))[:44]))
        if "TTM combined leg" in str(x.get("strategy")):
            sys.exit(f"ABORT - a combined-leg BOOK is already {st} ({d.id})")
print("queue depth:", len(busy), busy)
if len(busy) > 9:
    sys.exit("ABORT - queue too deep, not adding")

# run #341's job = the book the owner runs today (ORB 234 + ENGU-Q 309 + 3 ES of the tilted leg)
SRC = None
for d in u.collection("backtests").where(filter=FieldFilter("type", "==", "book")).stream():
    x = d.to_dict() or {}
    if x.get("run_id") == 361:
        SRC = (d.id, x); break
if SRC is None:
    sys.exit("ABORT - could not find BOOK run #361's job to clone")
src = SRC[1]
legs = src.get("legs") or []
if len(legs) != 3 or "TTMSQZ_3_0_ES30SS20" not in str(legs[2].get("strategy")):
    sys.exit("ABORT - #361's job does not look as expected; not cloning blind")

DROP = ["claimedBy", "createdAt", "elapsed_s", "fingerprint", "finishedAt", "heartbeat_at",
        "heartbeat_pid", "progress", "result", "run_id", "slices", "startedAt", "status", "note"]
job = {k: copy.deepcopy(v) for k, v in src.items() if k not in DROP}
job["legs"] = copy.deepcopy(legs)
job["legs"][2]["strategy"] = FILE
job["legs"][2]["params"] = {"kc_mult": 1.5, "eod_cutoff": 1}     # gate_len is pinned inside the file
name = "BOOK: ORB 234 + ENGU-Q 309 + TTM combined leg x3"
job.update(
    strategy=name, book_name=name, status="queued", progress=0, type="book",
    note=("THE COMBINED TTM LEG IN THE BOOK THE OWNER RUNS TODAY. Run #369 (TTMSQZ_3_0_ES30SSOF2.py) put "
          "BOTH validated changes in one leg - 1.5 contracts on the session open-bar entry (run #368) and "
          "the momentum-fade exit waiting for a second fading bar (run #364) - and PASSED all six gates "
          "with an overfit probability of 0.099, the lowest any run in this family has recorded, a deflated "
          "Sharpe that beats the luck bar, walk-forward efficiency 1.704 and 136 trades per knob. It cleared "
          "every clause of a bar set against the BETTER PARENT rather than the incumbent: lockbox 22,739 "
          "dollars against run #368 22,321, annualised MAR 1.826 against its 1.589, at a drawdown of 4,634 "
          "against a cap of 5,423. Against the leg the book actually carries (run #353): 135,884 dollars "
          "against 101,017, MAR 1.826 against 1.450 - a quarter better - lockbox 22,739 at profit factor "
          "9.89 against 16,977 at 6.72, and a lockbox drawdown of 1,978 against 2,003. "
          "WHY THE PAIR IS BETTER THAN EITHER HALF: the open-bar tilt buys money by sizing the trades this "
          "mechanism earns most on, and pays for it in drawdown, 4,338 to 5,330. The later fade gives most "
          "of that back, to 4,634, while keeping the money. That is a legible interaction rather than a "
          "lucky one, and it is why the combination was run separately instead of assumed. "
          "BAR, PRE-REGISTERED, canonical per BOOK.md section 10: against BOOK run #361, (1) annualised MAR "
          "at least 1.05x, (2) LOCKBOX drawdown within 5 percent, (3) lockbox net at least as large. The "
          "whole-run drawdown is a CHECK, not a gate - this book worst stretch is tape the TTM leg never "
          "trades, so it cannot move at any weight. "
          "ONE THING THIS RUN DOES NOT SETTLE, for the adoption decision: the deep-squeeze tilt and the "
          "open-bar tilt MULTIPLY, so a trade meeting both carries 2.25 contracts and the leg trades a 1.0 / "
          "1.5 / 2.25 ladder. Round 11 whole-contract answer covered one tilt, not two, and needs redoing "
          "before this ever reaches an order ticket."),

    createdAt=datetime.datetime.now(datetime.timezone.utc),
)
ref = u.collection("backtests").document()
ref.set(job)
print("queued:", ref.id, "|", name, "| cloned from BOOK #361 job", SRC[0])
for L in job["legs"]:
    print("   %-26s %-4s %-4s w%.0f  %s" % (L.get("strategy"), L.get("instrument"), L.get("timeframe"),
                                            float(L.get("weight") or 1), L.get("params")))
