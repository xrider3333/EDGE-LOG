"""Queue a RESTATEMENT validate of a TTM file after the same-bar gap-stop fix (2026-09-27).

    python tools/queue_ttm_restate.py TTMSQZ_3_0_ES30SSOF2R347.py "<preset label>" "<note>"

Window, master, costs and lockbox are copied from run #299's job like every TTM validate.
"""
import os, sys, datetime
os.chdir(r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG")
import firebase_admin
from firebase_admin import credentials, firestore
from google.cloud.firestore_v1 import FieldFilter
if not firebase_admin._apps:
    firebase_admin.initialize_app(credentials.Certificate("serviceAccount.json"))
db = firestore.client()
u = db.collection("users").document("IO0K35JpLIcH9YK4C0pMNYUzZOM2")
FILE, PRESET, NOTE = sys.argv[1], sys.argv[2], sys.argv[3]
if not os.path.exists(os.path.join("augur_strategies", FILE)):
    sys.exit(f"ABORT - {FILE} is not in the runner's checkout (ship first)")
for st in ("queued", "running"):
    for d in u.collection("backtests").where(filter=FieldFilter("status", "==", st)).stream():
        if FILE == str((d.to_dict() or {}).get("strategy")):
            sys.exit(f"ABORT - {FILE} is already {st} ({d.id})")
src = u.collection("backtests").document("slnV5HahFiJxxPzpttDA").get().to_dict() or {}
if "TTMSQZ_3_0_ES30N" not in str(src.get("strategy", "")):
    sys.exit("ABORT - could not read the ES30N job to copy its window")
CARRY = ["type", "instrument", "timeframe", "session", "source", "cost_pts", "mult", "multiplier",
         "commission_usd", "slippage_pts", "date_from", "date_to", "lockbox_months",
         "equity_points", "min_trades", "mc_sims", "n_trials", "n_rounds", "wf_folds",
         "select_oos_topk", "discover", "provider", "dsr", "neighbors", "regime", "pills", "context"]
job = {k: src[k] for k in CARRY if k in src}
job.update(type="validate", status="queued", progress=0, strategy=FILE, preset=PRESET, note=NOTE)
for k in ("date_from", "date_to", "source", "cost_pts", "lockbox_months"):
    if k not in job:
        sys.exit(f"ABORT - {k} missing, refusing to queue an unpinned window")
job["createdAt"] = datetime.datetime.now(datetime.timezone.utc)
ref = u.collection("backtests").document(); ref.set(job)
print("queued:", ref.id, FILE, job["date_from"], "->", job["date_to"], job["source"], job["cost_pts"])
