"""Queue the STRUCTURAL STOP Auto-Validate (TTMSQZ_3_0_ES30SS.py, 27 fenced cells).

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

FILE = "TTMSQZ_3_0_ES30SS.py"
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
    preset="Short  (ES 30m structural stop)",
    note=("THE PROTECTIVE STOP, MOVED FROM A VOLATILITY MULTIPLE TO THE STRUCTURE. Round 12b tested the "
          "entry, the stop and the exit of the crown cell; pullback entries, fixed time exits and scaling "
          "out were all worse, and one change was not: stopping at the FAR SIDE OF THE SQUEEZE RANGE - the "
          "level that says the setup was simply wrong - instead of 1.5 ATR. On the pinned window, mechanism "
          "only: 357 trades, profit factor 2.70 against the crown 2.12, net $73,720 against $51,709, "
          "drawdown $3,642 against $3,740, lockbox $11,710 at profit factor 5.38 against $4,992 at 2.22. "
          "Buffers of 0, 0.5 and 1.0 points behave alike, which is what a structural effect looks like "
          "rather than a fitted one; this file freezes the buffer at 0. With run #340's validated "
          "deep-squeeze 1.5x tilt on top, which is the leg the paper book carries: $101,017 at profit "
          "factor 2.91, drawdown $4,338 against the tilted leg's $4,549, lockbox $16,977 at 6.72 against "
          "$6,948 at 2.38. THE FILE WAS BUILT BEFORE THIS WAS BELIEVED and reproduces the scan to the "
          "dollar - which matters, because the same round caught a look-ahead bug in a different rule "
          "exactly this way. stop_atr is dropped from the searched set because the structural stop makes "
          "it inert; three knobs remain over the same admissible values as run #299, enforced in the file, "
          "refusing out-of-set configurations rather than clamping them. "
          "PRE-REGISTERED BAR (written before the run): (a) PASS, or WEAK on the overfit check alone; "
          "(b) lockbox net at least the book leg's $6,948 AND lockbox profit factor at least its 2.38; "
          "(c) whole-run annualised MAR at least the book leg's, at a whole-run drawdown no more than 10 "
          "percent above its $4,549. "
          "THE RISK THIS RUN CANNOT SETTLE, recorded here so it is not forgotten at adoption time: the "
          "structural stop averages $1,041 a contract against the ATR stop's $586, so it is about 76 "
          "percent wider, and its worst observed distance is $6,612. In THIS window that never cost "
          "anything - the worst single trade is $2,056 against the incumbent's $1,813, only 13 percent "
          "worse - but sixteen years that never punished a wider tail is one draw, not proof. Adoption "
          "needs a gap-stress read on top of a PASS here, and then a BOOK run against #341."),
)
for k in ("date_from", "date_to", "source", "cost_pts", "lockbox_months"):
    if k not in job:
        sys.exit(f"ABORT - {k} missing, refusing to queue an unpinned window")
job["createdAt"] = datetime.datetime.now(datetime.timezone.utc)
ref = u.collection("backtests").document()
ref.set(job)
print("queued:", ref.id)
print("  strategy :", job["strategy"], "| 27 cells |", job["instrument"], job["timeframe"])
print("  window   :", job["date_from"], "->", job["date_to"], "| lockbox", job["lockbox_months"], "mo")
print("  source   :", job["source"], "| cost_pts", job["cost_pts"], "| mult", job.get("mult") or job.get("multiplier"))
