"""Queue the WIDER re-run of NOISE run #316 (owner 2026-09-05).

Owner: "do the wider re-run on 316. we need to make sure theres no concentration where a
handfull of trades lead it to being profiable".

Run #316 validated NOISE_1_1_LB51.py over 90 cells and crowned lookback 37 with stop_k
2.0 -- the MINIMUM and the MAXIMUM of those two ranges. A crown standing on its own fence
is not a plateau centre, it is the best cell the search was allowed to reach. It also put
PBO 0.46 on a 90-cell population, which is too small to read against run #304's 0.14 on
495 cells.

NOISE_1_3_WIDE.py moves the two walls out (lookback down to 16, stop_k up to 2.5), adds
room either side of the short band and the confirm bars, and holds every other knob
exactly where #316 had it. 600 cells.

EVERY JOB FIELD IS COPIED FROM RUN #316'S OWN JOB (doc 8ktC5qWGwXgVfeN5d92w) so the two
verdicts compare like with like -- the HARD RULE on rerun windows. The only fields that
differ are `strategy`, `preset` and `note`.

READ THE REPORT IN THIS ORDER AND STOP AT THE FIRST FAILURE:
  1. CONCENTRATION on the crowned config. This is the question that was asked. Run #304
     is the worked example of why it comes first: best PBO on the board at 0.14, and its
     top five trades are 137% of net -- strip them and it loses $7,381.
  2. PBO on 600 cells, against #304's 0.14 on 495.
  3. Is the crown INTERIOR? If it walks to lookback 16 or stop_k 2.5 the fence is still
     wrong and the answer is another re-fence, not an adoption.
  4. Walk-forward folds against #316's 8 of 8, and the lockbox.
  5. Only then the money.
"""
import os
import sys

os.chdir(r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG")
import firebase_admin
from firebase_admin import credentials, firestore

if not firebase_admin._apps:
    firebase_admin.initialize_app(credentials.Certificate("serviceAccount.json"))
db = firestore.client()
UID = "IO0K35JpLIcH9YK4C0pMNYUzZOM2"
u = db.collection("users").document(UID)

# the runner executes the SHARED checkout, not this worktree - refuse to queue a job for
# a strategy file the runner cannot see (memory: "shipped is not running")
if not os.path.exists(os.path.join("augur_strategies", "NOISE_1_3_WIDE.py")):
    sys.exit("ABORT - NOISE_1_3_WIDE.py is not in the runner's checkout")

busy = [(d.id, (d.to_dict() or {}).get("status"))
        for d in u.collection("backtests").stream()
        if (d.to_dict() or {}).get("status") in ("queued", "running")]
print("queue depth:", len(busy), busy)
if len(busy) > 8:
    sys.exit("ABORT - queue too deep, not adding")

SRC_DOC = "8ktC5qWGwXgVfeN5d92w"          # run #316
src = (u.collection("backtests").document(SRC_DOC).get().to_dict() or {})
if not src or "NOISE_1_1_LB51" not in str(src.get("strategy", "")):
    sys.exit("ABORT - could not read run #316's job to copy its window")

CARRY = ["type", "instrument", "timeframe", "session", "source", "cost_pts", "mult",
         "commission_usd", "slippage_pts", "date_from", "date_to", "lockbox_months",
         "equity_points", "min_trades", "mc_sims", "n_trials", "n_rounds", "wf_folds",
         "select_oos_topk", "discover", "provider", "dsr", "neighbors", "regime",
         "pills", "context"]
job = {k: src[k] for k in CARRY if k in src}
job.update(
    status="queued",
    progress=0,
    strategy="NOISE_1_3_WIDE.py",
    preset="NOISE 1.3 WIDE - run #316 re-fenced, 600 cells (crown sat on two walls)",
    note=("Wider re-run of run #316 (NOISE_1_1_LB51, 90 cells). #316 crowned lookback 37 and "
          "stop_k 2.0, which are the MIN and MAX of its own ranges - a crown on its fence is the "
          "best cell it was allowed to reach, not a plateau centre. Here lookback opens down to "
          "16 (same step-7 lattice, so 37/44/51 are still on it), stop_k up to 2.5, band_mult_short "
          "1.00-2.00 and confirm_bars 1-3: 600 cells. band_mult_long 0.75, vol_skip_pct 90 and the "
          "day-type filter are held exactly where #316 had them, deliberately - opening those is "
          "run #302, which wandered off the champion core and came back WEAK at PBO 0.60. Window, "
          "costs, source and lockbox copied from #316's own job. JUDGE IT IN THIS ORDER: (1) "
          "CONCENTRATION on the crowned config - this is the owner's actual question, and run #304 "
          "shows why it leads: PBO 0.14 but its top five trades are 137% of net, strip them and it "
          "loses $7,381; (2) PBO on 600 cells against #304's 0.14 on 495; (3) is the crown INTERIOR "
          "this time, or did it walk to another wall; (4) WF folds vs #316's 8 of 8, and the "
          "lockbox; (5) money last."),
)

for k in ("date_from", "date_to", "source", "cost_pts", "lockbox_months"):
    if k not in job:
        sys.exit(f"ABORT - {k} missing, refusing to queue an unpinned window")

ref = u.collection("backtests").document()
ref.set(job)
print("queued:", ref.id)
print("  strategy :", job["strategy"], "| 600 cells")
print("  window   :", job["date_from"], "->", job["date_to"], "| lockbox", job["lockbox_months"], "mo")
print("  source   :", job["source"], "| cost_pts", job["cost_pts"], "| mult", job["mult"])
