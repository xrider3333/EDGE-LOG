"""Queue a fenced TTM Auto-Validate with an explicitly PINNED source and the owner's 900-trial budget.

    python tools/queue_ttm_validate.py FILE "<preset label>" "<note>" [--source db_adj_rth] [--n-trials 900]

Window, costs, lockbox and every other job field are copied from run #299's job (like every TTM validate,
see tools/queue_ttm_restate.py); only the source and the trial budget are set here, and both are required
to be explicit so a validate can never fall back to an unpinned master lookup or a lowered budget.
"""
import os, sys, argparse, datetime
os.chdir(r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG")
ap = argparse.ArgumentParser()
ap.add_argument("file"); ap.add_argument("preset"); ap.add_argument("note")
ap.add_argument("--source", required=True)
ap.add_argument("--n-trials", type=int, default=900)
a = ap.parse_args()
if a.n_trials < 900:
    sys.exit("ABORT - the owner's trial budget is 900; never lower it")
import firebase_admin
from firebase_admin import credentials, firestore
from google.cloud.firestore_v1 import FieldFilter
if not firebase_admin._apps:
    firebase_admin.initialize_app(credentials.Certificate("serviceAccount.json"))
db = firestore.client()
u = db.collection("users").document("IO0K35JpLIcH9YK4C0pMNYUzZOM2")
if not os.path.exists(os.path.join("augur_strategies", a.file)):
    sys.exit(f"ABORT - {a.file} is not in the runner's checkout (ship first)")
from augur_engine.data import find_master
if find_master("ES", "30m", "rth", a.source) is None:
    sys.exit(f"ABORT - no ES 30m RTH master for source {a.source}")
for st in ("queued", "running"):
    for d in u.collection("backtests").where(filter=FieldFilter("status", "==", st)).stream():
        if a.file == str((d.to_dict() or {}).get("strategy")):
            sys.exit(f"ABORT - {a.file} is already {st} ({d.id})")
src = u.collection("backtests").document("slnV5HahFiJxxPzpttDA").get().to_dict() or {}
if "TTMSQZ_3_0_ES30N" not in str(src.get("strategy", "")):
    sys.exit("ABORT - could not read the ES30N job to copy its window")
CARRY = ["type", "instrument", "timeframe", "session", "cost_pts", "mult", "multiplier",
         "commission_usd", "slippage_pts", "date_from", "date_to", "lockbox_months",
         "equity_points", "min_trades", "mc_sims", "n_rounds", "wf_folds",
         "select_oos_topk", "discover", "provider", "dsr", "neighbors", "regime", "pills", "context"]
job = {k: src[k] for k in CARRY if k in src}
job.update(type="validate", status="queued", progress=0, strategy=a.file, preset=a.preset, note=a.note,
           source=a.source, n_trials=a.n_trials)
for k in ("date_from", "date_to", "cost_pts", "lockbox_months"):
    if k not in job:
        sys.exit(f"ABORT - {k} missing, refusing to queue an unpinned window")
job["createdAt"] = datetime.datetime.now(datetime.timezone.utc)
ref = u.collection("backtests").document(); ref.set(job)
print("queued:", ref.id, a.file, job["date_from"], "->", job["date_to"], job["source"], job["cost_pts"],
      "n_trials", job["n_trials"])
