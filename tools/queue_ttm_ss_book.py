"""Queue the BOOK run for the structural-stop TTM leg, against the book the owner runs today (#341).

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

FILE = "TTMSQZ_3_0_ES30SS20.py"
if not os.path.exists(os.path.join("augur_strategies", FILE)):
    sys.exit(f"ABORT - {FILE} is not in the runner's checkout (ship first)")

busy = []
for st in ("queued", "running"):
    for d in u.collection("backtests").where(filter=FieldFilter("status", "==", st)).stream():
        x = d.to_dict() or {}
        busy.append((st, str(x.get("strategy"))[:44]))
        if "structural stop" in str(x.get("strategy")):
            sys.exit(f"ABORT - a structural-stop BOOK is already {st} ({d.id})")
print("queue depth:", len(busy), busy)
if len(busy) > 9:
    sys.exit("ABORT - queue too deep, not adding")

# run #341's job = the book the owner runs today (ORB 234 + ENGU-Q 309 + 3 ES of the tilted leg)
SRC = None
for d in u.collection("backtests").where(filter=FieldFilter("type", "==", "book")).stream():
    x = d.to_dict() or {}
    if x.get("run_id") == 341:
        SRC = (d.id, x); break
if SRC is None:
    sys.exit("ABORT - could not find BOOK run #341's job to clone")
src = SRC[1]
legs = src.get("legs") or []
if len(legs) != 3 or "TTMSQZ_3_0_ES30T" not in str(legs[2].get("strategy")):
    sys.exit("ABORT - #341's job does not look as expected; not cloning blind")

DROP = ["claimedBy", "createdAt", "elapsed_s", "fingerprint", "finishedAt", "heartbeat_at",
        "heartbeat_pid", "progress", "result", "run_id", "slices", "startedAt", "status", "note"]
job = {k: copy.deepcopy(v) for k, v in src.items() if k not in DROP}
job["legs"] = copy.deepcopy(legs)
job["legs"][2]["strategy"] = FILE
job["legs"][2]["params"] = {"kc_mult": 1.5, "eod_cutoff": 1}     # gate_len is pinned inside the file
name = "BOOK: ORB 234 + ENGU-Q 309 + TTM structural-stop x3"
job.update(
    strategy=name, book_name=name, status="queued", progress=0, type="book",
    note=("THE STRUCTURAL-STOP TTM LEG IN THE BOOK THE OWNER RUNS TODAY. Run #353 (TTMSQZ_3_0_ES30SS20.py, "
          "verification length pinned at run #299's own value of 20) PASSED all six house gates and cleared "
          "every clause of the bar written before it ran: lockbox $16,977 at profit factor 6.72 against the "
          "book leg's $6,948 at 2.38; whole run $101,017 at profit factor 2.91 and annualised MAR 1.450 "
          "against 0.957; drawdown $4,338 against $4,549 - LOWER, in the whole run and in the lockbox alike "
          "($2,003 against $4,053). Deflated Sharpe beats the luck bar; overfit probability 0.35, gate green; "
          "137 trades per knob. The engine reproduces the local file to the dollar. This run measures the "
          "same leg inside the book, against #341, which is the book in production since 2026-09-09. "
          "BAR, PRE-REGISTERED, in the wording BOOK.md section 10 made canonical today: (1) annualised MAR at "
          "least 1.05x run #341; (2) LOCKBOX drawdown within 5 percent of it; (3) lockbox net at least as "
          "large. The whole-run drawdown is reported as a CHECK, not a gate - this book's worst stretch is one "
          "month of tape the TTM leg never traded, so it cannot move at any weight and says nothing about the "
          "risk being added. "
          "THE OPEN RISK THIS RUN DOES NOT SETTLE: the structural stop is about 76 percent wider per contract "
          "than the ATR stop it replaces ($1,041 against $586, worst observed $6,612). Sixteen years never "
          "punished that - the worst single trade is $2,056 against $1,813 - but that is one draw. A gap-stress "
          "harness (tools/ttmsqz_r13_gap_stress.py) is running separately and adoption waits on it, whatever "
          "this book run says."),
    createdAt=datetime.datetime.now(datetime.timezone.utc),
)
ref = u.collection("backtests").document()
ref.set(job)
print("queued:", ref.id, "|", name, "| cloned from #341's job", SRC[0])
for L in job["legs"]:
    print("   %-26s %-4s %-4s w%.0f  %s" % (L.get("strategy"), L.get("instrument"), L.get("timeframe"),
                                            float(L.get("weight") or 1), L.get("params")))
