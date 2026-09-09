"""Queue the COMBINED validate (TTMSQZ_3_0_ES30SSOF2.py, 9 cells): both validated changes at once.

Window, master, costs and lockbox are copied from run #299's job so every TTM validate in the
family sits on the same tape. Written 2026-09-09 out of TTM round 12b.

    python tools/queue_ttm_structural_stop.py
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

FILE = "TTMSQZ_3_0_ES30SSOF2.py"
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
    preset="Short  (ES 30m structural stop, open-bar tilt, fade 2)",
    note=("BOTH VALIDATED CHANGES AT ONCE. Two single changes to the book leg cleared their own "
          "pre-registered bars within an hour of each other: run #368 puts 1.5 contracts on the session "
          "open-bar entry - the 87 of 357 trades that average 805 dollars against 115 - and run #364 leaves "
          "on the SECOND fading bar rather than the first. They touch nothing in common: one decides how "
          "much, the other decides when to leave. This run asks whether they add up. "
          "MEASURED LOCALLY, all four legs in one process, pinned window: book leg 357 trades / PF 2.91 / "
          "101,017 dollars / drawdown 4,338 / MAR 1.450 / lockbox 16,977 at 6.72. Fade 2: 354 / 2.80 / "
          "101,795 / 4,277 / 1.482 / 17,452 at 7.82. Open bar: 357 / 3.28 / 136,043 / 5,330 / 1.589 / "
          "22,321 at 8.52. BOTH: 354 / 3.12 / 135,884 / 4,634 / 1.826 / 22,739 at 9.89, lockbox drawdown "
          "1,978. They do more than add up, and the reason is legible - the open-bar tilt buys money with "
          "drawdown, 4,338 to 5,330, and the later fade gives most of that back at 4,634 while keeping the "
          "money. Annualised MAR 1.826 against the book leg 1.450, a quarter better, with a lockbox larger "
          "than either parent at a lockbox drawdown lower than either parent. "
          "WHY IT IS STILL A SEPARATE RUN: two changes that each help can interact badly. The later fade "
          "holds trades longer and the tilt puts more size on precisely the trades that run, so the pair "
          "could concentrate risk in a way neither did alone. That is what a drawdown clause is for. "
          "PRE-REGISTERED BAR: (a) PASS, or WEAK on the overfit check alone; (b) lockbox net at least run "
          "#368 22,321 - the BETTER PARENT, not the incumbent, because a combination that cannot beat its "
          "own best half is not worth the extra complexity; (c) whole-run annualised MAR at least run #368 "
          "1.589, at a drawdown no more than 25 percent above the book leg 4,338. "
          "If it clears, adoption still needs one BOOK run against the book in production."),

)
for k in ("date_from", "date_to", "source", "cost_pts", "lockbox_months"):
    if k not in job:
        sys.exit(f"ABORT - {k} missing, refusing to queue an unpinned window")
job["createdAt"] = datetime.datetime.now(datetime.timezone.utc)
ref = u.collection("backtests").document()
ref.set(job)
print("queued:", ref.id)
print("  strategy :", job["strategy"], "| 9 cells |", job["instrument"], job["timeframe"])
print("  window   :", job["date_from"], "->", job["date_to"], "| lockbox", job["lockbox_months"], "mo")
print("  source   :", job["source"], "| cost_pts", job["cost_pts"], "| mult", job.get("mult") or job.get("multiplier"))
