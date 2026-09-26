"""Queue the ROLL-GUARD validate (TTMSQZ_3_0_ES30SSOF2R.py): run #369 with every true ES contract
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

FILE = "TTMSQZ_3_0_ES30SSOF2R.py"
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
    preset="Short  (ES 30m book leg with roll guard)",
    note=("ROLL GUARD FOR THE BOOK LEG (run 369). The roll audit found the squeeze, ATR, hourly check and "
          "open-bar tilt read each ES contract switch as a real opening gap, so fake squeezes fire 0-2 days "
          "after some rolls. This file shifts every bar before each TRUE switch (from the exact switch table, "
          "not the house seam detector) so the series is continuous, then runs 369 unchanged. Not look-ahead: "
          "a later switch shifts a whole lookback window by one constant, which nothing this leg reads can "
          "see. MEASURED LOCALLY, pinned window: unguarded 354 trades / 135,884 dollars / PF 3.117 / "
          "drawdown 4,634 / MAR 1.83; guarded 355 / 121,491 / 2.789 / 5,300 / 1.43 - the roll audit figures "
          "exactly - lockbox 15 trades / 22,739 / PF 9.89 in both. A CORRECTION, not an improvement. "
          "PRE-REGISTERED BAR: (a) PASS, or WEAK on the overfit check alone; (b) whole run within 2 percent of "
          "121,491; (c) lockbox at least 20,000 at profit factor at least 5; (d) whole-run MAR above the "
          "corrected parents 368 (1.31) and 353 (1.15). Swapping the paper or book leg is an owner call."),
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
