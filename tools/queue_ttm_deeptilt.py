"""Queue the TTM deep-squeeze SIZE TILT Auto-Validate (TTMSQZ_3_0_ES30T.py, 81 fenced cells).

Window, master, costs and lockbox are COPIED from run #299's own job (job slnV5HahFiJxxPzpttDA,
TTMSQZ_3_0_ES30N.py) so the tilted leg is judged against its control on the same tape.
Refuses to queue if the file is not in the runner's checkout or the same file is already in
flight. Written 2026-09-09 out of TTM round 8 (tools/ttmsqz_round8_crown.py).

    python tools/queue_ttm_deeptilt.py
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

FILE = "TTMSQZ_3_0_ES30T.py"
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

SRC_DOC = "slnV5HahFiJxxPzpttDA"          # the ES30N job = run #299's control window
src = (u.collection("backtests").document(SRC_DOC).get().to_dict() or {})
if "TTMSQZ_3_0_ES30N" not in str(src.get("strategy", "")):
    sys.exit("ABORT - could not read the ES30N job to copy its window")

CARRY = ["type", "instrument", "timeframe", "session", "source", "cost_pts", "mult",
         "multiplier", "commission_usd", "slippage_pts", "date_from", "date_to",
         "lockbox_months", "equity_points", "min_trades", "mc_sims", "n_trials", "n_rounds",
         "wf_folds", "select_oos_topk", "discover", "provider", "dsr", "neighbors",
         "regime", "pills", "context"]
job = {k: src[k] for k in CARRY if k in src}
job.update(
    type="validate", status="queued", progress=0, strategy=FILE,
    preset="Short  (ES 30m deep-squeeze tilt neighbourhood)",
    note=("TTM CROWN + DEEP-SQUEEZE SIZE TILT. Round 8 (tools/ttmsqz_round8_crown.py, 2026-09-08) "
          "scanned twelve one-change variants of the crown (run #299) alone and stacked as the book "
          "leg; eleven were worse or flat and the only near miss was SIZE: every trade still taken, "
          "but the ones entered while the verifying hourly squeeze is DEEP (ratio at or under 0.85, "
          "the house threshold from the KEEL overlay) sized 1.5. Local read on this exact window, "
          "crown cell: 188 of 359 trades tilted, net $69,884 vs $51,709, PF 2.23 vs 2.12, drawdown "
          "$4,549 vs $3,740, lockbox $6,948 vs $4,992 at PF 2.38 vs 2.22. Stacked as three ES "
          "contracts on the ORB 234 + ENGU-Q 309 baseline: annualised MAR 2.00 -> 2.09 at UNCHANGED "
          "book drawdown, book lockbox +3 percent. That was +4.5 percent against round 8's +5 percent "
          "bar, so NOTHING was crowned there and this is the fenced test instead. "
          "The multiplier (1.5) and the deep threshold (0.85) are FIXED a priori - the lesson of run "
          "#331, where an open multiplier let an in-sample-money search crown the most aggressive "
          "corner - and the ratio is read at fixed length 20 / Bollinger 2.0 / Keltner 1.5 so its "
          "meaning cannot drift with the search. Only run #299's own four knobs vary, over the same "
          "admissible set, enforced inside the file (out-of-set configurations are refused, not "
          "clamped). CONTROL = run #299, same window, master, costs and lockbox. "
          "PRE-REGISTERED BAR (written before the run): (a) PASS, or WEAK on the overfit check "
          "alone; (b) lockbox net at least run 299's $4,992 AND lockbox profit factor at least its "
          "2.22; (c) whole-run annualised MAR at least run 299's, at a whole-run drawdown no more "
          "than 25 percent above its $3,740. The lockbox drawdown is deliberately NOT a clause: run "
          "299's lockbox holds 16 trades, so its drawdown is noise (the crown cell's own tilted "
          "lockbox drawdown is 29 percent higher on those same few trades). Adoption needs one more "
          "step either way - a BOOK run against #336 that must lift annualised MAR at least 5 "
          "percent at a book drawdown within 5 percent. Every trade is taken; this is sizing, not a "
          "filter."),
)
for k in ("date_from", "date_to", "source", "cost_pts", "lockbox_months"):
    if k not in job:
        sys.exit(f"ABORT - {k} missing, refusing to queue an unpinned window")
job["createdAt"] = datetime.datetime.now(datetime.timezone.utc)
ref = u.collection("backtests").document()
ref.set(job)
print("queued:", ref.id)
print("  strategy :", job["strategy"], "| 81 cells")
print("  window   :", job["date_from"], "->", job["date_to"], "| lockbox", job["lockbox_months"], "mo")
print("  source   :", job["source"], "| cost_pts", job["cost_pts"], "| mult", job.get("mult") or job.get("multiplier"))
