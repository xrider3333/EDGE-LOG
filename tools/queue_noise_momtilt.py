"""Queue the NOISE momentum-size-tilt Auto-Validate (NOISE_1_1_SBS_V90_MT.py, 18 fenced cells).

Window, costs, source and lockbox are COPIED from run #243's own job (the untilted paper leg,
job 9cr6rtZPZng2HIiLxH3K) so the tilted leg is judged against its control on the same tape.
Refuses to add anything if the strategy file is not in the runner's checkout, or if the
queue is already more than nine deep. Written 2026-09-07 (tools/trade_anatomy.py finding).

    python tools/queue_noise_momtilt.py
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

FILE = "NOISE_1_1_SBS_V90_MT.py"
# the runner executes the SHARED checkout - refuse to queue for a file it cannot see
if not os.path.exists(os.path.join("augur_strategies", FILE)):
    sys.exit(f"ABORT - {FILE} is not in the runner's checkout (ship first)")

busy = []
for st in ("queued", "running"):
    for d in u.collection("backtests").where(filter=FieldFilter("status", "==", st)).stream():
        x = d.to_dict() or {}
        busy.append((st, str(x.get("strategy"))[:40]))
        if FILE in str(x.get("strategy")):
            sys.exit(f"ABORT - {FILE} is already {st} ({d.id}); not queueing twice")
print("queue depth:", len(busy), busy)
if len(busy) > 9:
    sys.exit("ABORT - queue too deep, not adding")

SRC_DOC = "9cr6rtZPZng2HIiLxH3K"          # run #243, the untilted control
src = (u.collection("backtests").document(SRC_DOC).get().to_dict() or {})
if not src or "NOISE_1_1_SBS_V90" not in str(src.get("strategy", "")):
    sys.exit("ABORT - could not read run #243's job to copy its window")

CARRY = ["type", "instrument", "timeframe", "session", "source", "cost_pts", "mult",
         "commission_usd", "slippage_pts", "date_from", "date_to", "lockbox_months",
         "equity_points", "min_trades", "mc_sims", "n_trials", "n_rounds", "wf_folds",
         "select_oos_topk", "discover", "provider", "dsr", "neighbors", "regime",
         "pills", "context"]
job = {k: src[k] for k in CARRY if k in src}
job.update(
    type="validate", status="queued", progress=0, strategy=FILE,
    preset="Short  (the fenced 18-cell tilt neighbourhood)",
    note=("NOISE paper leg + MOMENTUM SIZE TILT (tools/trade_anatomy.py, docs/anatomy/NOISE_243.md, "
          "2026-09-07). The anatomy study mined only the first 60% of pre-lockbox trades and found "
          "one pre-entry reading that carried into the untouched 40%: the prior two-hour move in the "
          "trade's own direction, in ATR. Top third vs bottom third earned $51 vs -$10 per trade in "
          "discovery and $245 vs $90 in holdout. As a 2x size tilt on the top third: MAR 0.97->1.37 "
          "(discovery) and 2.50->2.86 (holdout), PF up in both, DD ~+30%. Local replay on this exact "
          "window: parent $380,745 / PF 1.387 / DD $22,096; tilt 24/4.25/2.0 $607,419 / PF 1.453 / "
          "DD $32,343 (1,521 of 4,429 trades tilted). CONTROL = run #243 (same window, costs, lockbox). "
          "PRE-REGISTERED READ: adopt only if PASS, PBO robust, lockbox PF >= 1.36 (the untilted "
          "leg's), full-window MAR above the untilted 1.34, and the crowned cell is INTERIOR. The "
          "anatomy holdout overlaps this validate's WF window, so WF is a re-test; the lockbox year "
          "is the only untouched slice. Every trade is taken - this is sizing, not a filter."),
)
for k in ("date_from", "date_to", "source", "cost_pts", "lockbox_months"):
    if k not in job:
        sys.exit(f"ABORT - {k} missing, refusing to queue an unpinned window")
job["createdAt"] = datetime.datetime.now(datetime.timezone.utc)
ref = u.collection("backtests").document()
ref.set(job)
print("queued:", ref.id)
print("  strategy :", job["strategy"], "| 18 cells")
print("  window   :", job["date_from"], "->", job["date_to"], "| lockbox", job["lockbox_months"], "mo")
print("  source   :", job["source"], "| cost_pts", job["cost_pts"], "| mult", job["mult"])
