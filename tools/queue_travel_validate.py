"""Queue the GAPGO TRAVEL 1.0 family-seed Auto-Validate (open ranges, 8 WF folds, 12-month lockbox).

Pre-queue gates already run (2026-09-08): parity with the round-33b harness cell is exact
(n=2007 / $151,024 / PF 1.341 / DD $16,672), tools/concentration_check.py = CONCENTRATED
(top-10 share 50%, ex-top-10 +$74,781 at PF 1.17 -> queueable, said out loud on the card),
and tools/gapgo_vs_orb_overlap.py measured the overlap with the ORB crown (see the note).
Window pinned to the ORB crown's certified window (2010-06-07 .. 2026-08-13) so the two
are comparable; lockbox = the last 12 months of it, never opened locally.

    python tools/queue_travel_validate.py

Refuses if the queue is more than nine deep. Idempotent guard: refuses if a GAPGO_1_0 job
is already queued or running.
"""
import os, sys, datetime, time
os.chdir(r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG")
import firebase_admin
from firebase_admin import credentials, firestore
from google.api_core import exceptions as _gx
if not firebase_admin._apps:
    firebase_admin.initialize_app(credentials.Certificate("serviceAccount.json"))
u = firestore.client().collection("users").document("IO0K35JpLIcH9YK4C0pMNYUzZOM2")


def _retry(fn, tries=4, wait=300):
    for i in range(tries):
        try:
            return fn()
        except (_gx.ResourceExhausted, _gx.ServiceUnavailable, _gx.DeadlineExceeded) as e:
            print("attempt %d blocked (%s); waiting %ds" % (i + 1, type(e).__name__, wait), flush=True)
            if i == tries - 1:
                raise
            time.sleep(wait)


live = _retry(lambda: [(d.to_dict() or {}) for d in u.collection("backtests")
                       .where("status", "in", ["queued", "running"]).stream()])
print("queue depth", len(live), [str(j.get("strategy"))[:24] + ":" + str(j.get("status")) for j in live])
if len(live) > 9: sys.exit("ABORT queue too deep")
if any(j.get("strategy") == "GAPGO_TRAVEL_1_0.py" for j in live): sys.exit("ABORT GAPGO_1_0 already queued/running")
job = dict(type="validate", status="queued", strategy="GAPGO_TRAVEL_1_0.py",
    instrument="NQ", timeframe="5m", session="rth", source="db_noadj_rth",
    cost_pts=0.533, mult=20, commission_usd=0.0, slippage_pts=0.0,
    date_from="2010-06-07", date_to="2026-08-13", lockbox_months=12,
    equity_points=400, min_trades=30, mc_sims=2000, n_trials=250, n_rounds=0, wf_folds=8,
    select_oos_topk=10, discover="auto", provider="ollama",
    dsr=True, neighbors=True, regime=True, pills=True, context=True, progress=0,
    preset="GAPGO TRAVEL 1.0 - second trigger of the opening-momentum family: distance-from-open continuation (round 36)",
    note=("Round 36 (tools/r36_family_seeds5.py, tools/r36b_travel_vs_gapgo.py). Same family as GAPGO_1_0 "
          "(the direction the market is already moving at the open continues), DIFFERENT READ: at a fixed "
          "clock time (10:00 ET) if price has travelled at least k x the 20-day average daily range from the "
          "session open, go with it; stop at the open, breakeven at 1R (PINNED), flat at the close, calendar "
          "roll-seam skip. Triage centre (10:00 / 0.3 ATR / stop at open) on 2010-06-07..2025-06-29: n=1050 / "
          "$146,387 / PF 1.345 / DD $18,115 / n-per-DD 8.08 / 6-of-8 slices / EV R 0.20. The edge decays with "
          "the clock (10:30 PF 1.23, 11:00 PF 1.16). CONCENTRATION said out loud: top-10 share 54 percent, "
          "ex-top-10 +$67,064 at PF 1.16. WHY IT IS A FAMILY MEMBER NOT A TWIN: shares only 26 percent of "
          "GAPGO's trade days, earns +$157,283 on the days GAPGO does NOT trade and -$10,896 on shared days, "
          "daily correlation 0.24; pooled 1:1 with GAPGO the net-over-drawdown is 9.8 vs 9.1 and 8.1 alone. "
          "Open knobs: clock_min 585-630, k_atr 0.2-0.5, stop_frac 0.5/1.0 (32 cells). Window pinned to the "
          "ORB crown so GAPGO, TRAVEL and ORB are comparable; the lockbox has never been loaded locally. A "
          "SEED for the family hand-off, not a challenger."))
job["createdAt"] = datetime.datetime.now(datetime.timezone.utc)
ref = u.collection("backtests").document(); _retry(lambda: ref.set(job))
print("queued", ref.id, job["strategy"])
