"""Queue the FADE-AFTER-2-BARS validate (TTMSQZ_3_0_ES30SSF2.py, 9 cells) against the book leg.

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

FILE = "TTMSQZ_3_0_ES30SSF2.py"
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
    preset="Short  (ES 30m structural stop, fade after 2 bars)",
    note=("THE BOOK LEG, LEAVING ONE BAR LATER. The momentum-fade exit leaves on the FIRST bar momentum "
          "fades; waiting for a SECOND has now been measured twice - round 8 on the old ATR-stop base and "
          "round 14b on the structural-stop base the book carries - and both times it came out ahead on "
          "everything except one number. On the pinned window against run #353: 354 trades against 357, net "
          "$101,795 against $101,017, drawdown $4,277 against $4,338 - LOWER - lockbox $17,452 against "
          "$16,977 at profit factor 7.82 against 6.72. The exits move exactly as one extra bar of patience "
          "should move them: 105 fade exits instead of 175, 194 held to the close instead of 135, 55 stopped "
          "instead of 47. "
          "WHY IT WAS NOT PICKED UP SOONER, STATED PLAINLY: both scans screened on beating the incumbent on "
          "BOTH whole-run profit factor and lockbox net, and this cell fails that screen on the first half - "
          "2.80 against 2.91. That screen is triage for a scan with dozens of cells; it is NOT what this shop "
          "crowns on. Every pre-registered bar in this family - runs #340, #352, #353 - is built from the "
          "house gates, the LOCKBOX net and profit factor, and annualised MAR at a drawdown cap. Whole-run "
          "profit factor has never been a clause in any of them, so the bar below is the same shape as its "
          "three predecessors rather than one reshaped after seeing which clause failed. "
          "DISCLOSED, because it is the one number that gets worse: whole-run profit factor falls 2.91 to "
          "2.80. A few small winners that used to be booked on the first fade now ride to the close, where "
          "some give back. "
          "PRE-REGISTERED BAR against run #353: (a) PASS, or WEAK on the overfit check alone; (b) lockbox net "
          "at least $16,977 AND lockbox profit factor at least 6.72; (c) whole-run annualised MAR at least "
          "1.450, at a whole-run drawdown NO HIGHER than $4,338 - the claim is that the drawdown FALLS, so "
          "the bar holds it to that with no slack. "
          "The file was parity-checked against the scan before queueing and caught a real bug doing it: the "
          "parent freezes fade_bars so a passed value is silently ignored, and the first version of this file "
          "reproduced the parent to the dollar instead of changing anything. Adoption, if it clears, still "
          "needs a BOOK run against the book in production."),
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
