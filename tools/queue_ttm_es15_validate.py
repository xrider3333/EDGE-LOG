"""Queue the ES 15-minute TTM cell's leg-level Auto-Validate (TTMSQZ_3_0_ES15N.py, 81 fenced cells).

BOOK run #342 cleared its bar with this cell in it, and its job note said in advance that a clear
result would be a LEAD for exactly this run, not an adoption. Window, master, costs and lockbox are
copied from run #299's job so every TTM validate in the family sits on the same tape.

    python tools/queue_ttm_es15_validate.py
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

FILE = "TTMSQZ_3_0_ES15N.py"
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

CARRY = ["type", "instrument", "session", "source", "cost_pts", "mult", "multiplier",
         "commission_usd", "slippage_pts", "date_from", "date_to", "lockbox_months",
         "equity_points", "min_trades", "mc_sims", "n_trials", "n_rounds", "wf_folds",
         "select_oos_topk", "discover", "provider", "dsr", "neighbors", "regime", "pills", "context"]
job = {k: src[k] for k in CARRY if k in src}
job.update(
    type="validate", status="queued", progress=0, strategy=FILE, timeframe="15m",
    preset="Short  (ES 15m Carter neighbourhood)",
    note=("THE ES 15-MINUTE TTM CELL, ON ITS OWN. BOOK run #342 (the validated deep-squeeze tilt on the "
          "30-minute leg plus three ES contracts of this cell) cleared every clause of its bar - annualised "
          "MAR times 1.10 against a bar of times 1.05, whole-run drawdown times 1.007, lockbox times 1.08 at "
          "a LOWER lockbox drawdown, eight of eight slices - and its job note said before it ran that a clear "
          "result would be a LEAD for this run, not an adoption. A book result cannot certify a leg. "
          "Alone, on the round-9 scan at the 30-minute crown settings: 525 trades, profit factor 1.31, "
          "$22,460 at a drawdown of $8,240, lockbox +$3,417 at profit factor 1.51. The four knobs and the "
          "admissible set are INHERITED from run #299's file, not chosen for this tape, so the fence was "
          "fixed before anyone looked at 15-minute results; out-of-set configurations are refused inside the "
          "file, not clamped. "
          "PRE-REGISTERED BAR (written before the run): (a) PASS, or WEAK on the overfit check alone; "
          "(b) lockbox net above zero AND whole-run profit factor at least 1.20; (c) the crowned cell inside "
          "the declared set, which the file enforces. Clearing this makes the cell a LEG-LEVEL candidate - "
          "and adoption still needs one more thing after that: a BOOK run carrying the CROWNED cell (not the "
          "scan's inherited settings) that clears the same times 1.05 MAR, drawdown within 5 percent and "
          "lockbox clauses against BOOK #336. If the crowned cell is not the inherited one, run #342 does not "
          "transfer and the book has to be re-measured."),
)
for k in ("date_from", "date_to", "source", "cost_pts", "lockbox_months"):
    if k not in job:
        sys.exit(f"ABORT - {k} missing, refusing to queue an unpinned window")
job["createdAt"] = datetime.datetime.now(datetime.timezone.utc)
ref = u.collection("backtests").document()
ref.set(job)
print("queued:", ref.id)
print("  strategy :", job["strategy"], "| 81 cells |", job["instrument"], job["timeframe"])
print("  window   :", job["date_from"], "->", job["date_to"], "| lockbox", job["lockbox_months"], "mo")
print("  source   :", job["source"], "| cost_pts", job["cost_pts"], "| mult", job.get("mult") or job.get("multiplier"))
