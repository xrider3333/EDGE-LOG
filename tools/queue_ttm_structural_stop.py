"""Queue the STRUCTURAL STOP re-run with the verification length PINNED (TTMSQZ_3_0_ES30SS20.py, 9 cells).

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

FILE = "TTMSQZ_3_0_ES30SS20.py"
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
    preset="Short  (ES 30m structural stop, gate length 20)",
    note=("THE STRUCTURAL STOP, WITH THE KNOB ITS SEARCH RAN AWAY ON PINNED. Run #352 put this stop through "
          "Auto-Validate and PASSED every house gate - plateau, walk-forward, sample, consistency, overfit "
          "and luck, overfit probability 0.17, deflated Sharpe beats the luck bar, 162 trades per knob. It "
          "did NOT clear the bar written before it ran. The search crowned a verification length of 16 "
          "instead of 20, which nearly doubles the trades - 665 against 357 - and takes the whole-run "
          "drawdown to $7,143 against the book leg $4,549, a 57 percent rise against a 10 percent cap, for "
          "an annualised MAR of 0.956 against the book leg 0.957. A dead heat bought with more risk, which "
          "is what the drawdown clause exists to catch, and the same corner-walking that run #331 showed. "
          "This run asks the question the round was about - does the STOP help - with gate_len held at 20, "
          "the value run #299 and run #340 both crowned months before this stop was considered and the "
          "value the paper book carries today. That is one change at a time, not a cell chosen to fit a bar. "
          "At that cell, mechanism only: 357 trades, profit factor 2.70, $73,720, drawdown $3,642, lockbox "
          "$11,710 at 5.38. With run #340 validated tilt on top, which is the shipped file: $101,017 at "
          "2.91, drawdown $4,338 - BELOW the book leg $4,549 - and a lockbox of $16,977 at 6.72. "
          "THE BAR IS UNCHANGED FROM RUN #352 so the two are comparable: (a) PASS, or WEAK on the overfit "
          "check alone; (b) lockbox net at least $6,948 AND lockbox profit factor at least 2.38; (c) "
          "whole-run annualised MAR at least the book leg, at a drawdown no more than 10 percent above its "
          "$4,549. THE CAVEAT NEITHER RUN CAN SETTLE: this stop averages about $1,041 a contract against "
          "the ATR stop $586, some 76 percent wider, worst observed distance $6,612. In this window that "
          "never cost anything - worst single trade $2,056 against $1,813 - but that is one draw, not proof. "
          "Adoption needs a gap-stress read on top of a PASS, and then a BOOK run against #341."),
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
