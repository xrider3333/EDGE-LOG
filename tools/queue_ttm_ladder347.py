"""Queue the STAGED BOOK-LEG validate (TTMSQZ_3_0_ES30SSOF2R347.py): run #428 sized 3 / 4 / 7 ES; was: the ROLL-GUARD validate (TTMSQZ_3_0_ES30SSOF2R.py): run #369 with every true ES contract
switch removed from the price series, per ROLL_AUDIT.md section 3.3 (MANAGER dispatch 2026-09-26).

Window, master, costs and lockbox are copied from run #299's job, the same source every TTM validate
in the family uses, so this sits on #369's tape exactly.

    python tools/queue_ttm_rollguard.py
"""
import os
import sys
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

FILE = "TTMSQZ_3_0_ES30SSOF2R347.py"
if not os.path.exists(os.path.join("augur_strategies", FILE)):
    sys.exit(f"ABORT - {FILE} is not in the runner's checkout (ship first)")

busy = []
for st in ("queued", "running"):
    for d in u.collection("backtests").where(filter=FieldFilter("status", "==", st)).stream():
        x = d.to_dict() or {}
        busy.append((st, str(x.get("strategy"))[:44]))
        if FILE in str(x.get("strategy")):
            sys.exit(f"ABORT - {FILE} is already {st} ({d.id}); not queueing twice")
print("queue depth:", len(busy), busy)
if len(busy) > 9:
    sys.exit("ABORT - queue too deep, not adding")

src = (u.collection("backtests").document("slnV5HahFiJxxPzpttDA").get().to_dict() or {})
if "TTMSQZ_3_0_ES30N" not in str(src.get("strategy", "")):
    sys.exit("ABORT - could not read the ES30N job to copy its window")

CARRY = ["type", "instrument", "timeframe", "session", "source", "cost_pts", "mult", "multiplier",
         "commission_usd", "slippage_pts", "date_from", "date_to", "lockbox_months",
         "equity_points", "min_trades", "mc_sims", "n_trials", "n_rounds", "wf_folds",
         "select_oos_topk", "discover", "provider", "dsr", "neighbors", "regime", "pills", "context"]
job = {k: src[k] for k in CARRY if k in src}
job.update(
    type="validate", status="queued", progress=0, strategy=FILE,
    preset="Short  (roll-guarded TTM book leg, 3/4/7 contracts)",
    note=("THE STAGED TTM BOOK LEG, VALIDATED IN ITS OWN RIGHT. Run 428 (the roll-guarded leg, PASS, PBO 0.036) with "
          "each trade sized 3, 4 or 7 whole ES contracts by its own tilt ladder instead of 3 x 1.0 / 1.5 / 2.25. "
          "Staged for the owner confirm; BOOK #448 / #450 carry it at weight 1.0. The sizing is fixed a priori "
          "(round 18a), not searched; the search space is 428s own fence. MEASURED LOCALLY at 428s cell: 246 trades, "
          "358,610 dollars, PF 3.58, drawdown 16,007, MAR 1.39. PRE-REGISTERED BAR: (a) PASS, or WEAK on the "
          "overfit check alone; (b) the search crowns the SAME cell as run 428 (kc 1.5, entry cutoff 5) - if the "
          "ladder changes which cell wins, the ladder is doing selection and the staged leg is not 428 re-sized; "
          "(c) lockbox profit factor at least 5; (d) walk-forward Sortino at least run 428s 3.22."),
)
for k in ("date_from", "date_to", "source", "cost_pts", "lockbox_months"):
    if k not in job:
        sys.exit(f"ABORT - {k} missing, refusing to queue an unpinned window")
job["createdAt"] = datetime.datetime.now(datetime.timezone.utc)
ref = u.collection("backtests").document()
ref.set(job)
print("queued:", ref.id)
print("  strategy :", job["strategy"], "|", job["instrument"], job["timeframe"])
print("  window   :", job["date_from"], "->", job["date_to"], "| lockbox", job["lockbox_months"], "mo")
print("  source   :", job["source"], "| cost_pts", job["cost_pts"], "| mult", job.get("mult") or job.get("multiplier"))
