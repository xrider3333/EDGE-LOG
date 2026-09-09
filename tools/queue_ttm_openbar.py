"""Queue the OPEN-BAR TILT validate (TTMSQZ_3_0_ES30SSO.py, 9 cells) against the book leg.

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

FILE = "TTMSQZ_3_0_ES30SSO.py"
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
    preset="Short  (ES 30m structural stop, open-bar tilt)",
    note=("SIZE UP THE TRADE THE EDGE LIVES IN. Round 15b asked whether this leg should skip the noisy "
          "first bars of the session, the way it already skips the last. The answer was INVERTED and by a "
          "distance: the 87 trades that fill on the session FIRST AVAILABLE bar average 805 dollars against "
          "115 for the other 270 - seven times the rest, a quarter of the trades - and blocking them removes "
          "70,053 dollars of a 101,017 dollar leg. The shop preference is that a subset that good gets SIZED "
          "rather than filtered, so this puts 1.5 contracts on it, the same shape and multiplier already "
          "validated for the deep-squeeze tilt. Whole run: 136,043 dollars at profit factor 3.28 against "
          "101,017 at 2.91, drawdown 5,330 against 4,338, annualised MAR 1.589 against 1.450, lockbox 22,321 "
          "at 8.52 against 16,977 at 6.72 - at an UNCHANGED lockbox drawdown of 2,003. "
          "THE CONTROL THAT MATTERS: scaling every trade by 1.5 cannot change annualised MAR, and it does "
          "not - the flat leverage control sits at the incumbent MAR in both the mining half and the "
          "held-back half, while this tilt lifts it 0.97 to 1.35 and 0.76 to 0.84, and leaves the lockbox "
          "drawdown alone where the flat version pushes it from 2,003 to 3,005. Permutation on the mining "
          "half: plus 399 dollars a trade, p 0.0000. The multiplier is fixed at 1.5 a priori; 2.0 measures "
          "better on every column and is deliberately NOT used, because a search that crowns the biggest "
          "size is exactly what runs #331 and #352 already produced. "
          "WHAT THE OPEN BAR MEANS: a fire is decided on a closed bar and filled at the next open, so no "
          "trade can enter on the session very first bar - the first version of the measurement looked for "
          "ordinal zero and found none. The rule is ordinal one, the 10:00 ET bar, whose fire was decided on "
          "the 09:30 close: the overnight gap releasing into an hour that is still coiled. "
          "HONEST LIMIT: the rule was found by looking at these trades. The held-back half and the lockbox "
          "are the evidence, the mining half is where it came from, and the lockbox holds 16 trades. "
          "PRE-REGISTERED BAR against run #353: (a) PASS, or WEAK on the overfit check alone; (b) lockbox "
          "net at least 16,977 AND lockbox profit factor at least 6.72; (c) whole-run annualised MAR at "
          "least 1.450, at a drawdown no more than 25 percent above its 4,338 - a WIDER drawdown clause than "
          "the last three bars used, stated as such, because this change ADDS SIZE and should have to earn "
          "its risk in MAR rather than merely avoid drawdown. "
          "It composes with the deep-squeeze tilt multiplicatively - 1.0, 1.5 or 2.25 contracts - which is "
          "disclosed rather than capped, and makes round 11 whole-contract question harder at adoption."),
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
