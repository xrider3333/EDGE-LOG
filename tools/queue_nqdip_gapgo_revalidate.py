"""Queue fresh Auto-Validates of NQDIP 1.0, NQDIP 1.1 and GAPGO 1.0 (owner 2026-09-15: "auto validate both and tell me their results").

WHY AGAIN, AND WHAT CHANGES:
  * The validate's lockbox is a COLD RESTART: Stage C runs the champion on the reserved slice only
    (augur_engine/validate.py, date_from=lb_from). NQDIP returns nothing until it has trend_len + 30
    sessions, so on a 12-month slice (~250 sessions) it loses most of the year: #307 (trend_len 100)
    shows 30 lockbox trades / $5,920 against $22,719 run continuously (tools/nqdip_beta_check.py), and
    #315 (trend_len 250) could not place a single trade and FAILED on that alone.
    -> NQDIP jobs use lockbox_months=24 (~500 sessions), so even trend_len 300 leaves ~170 tradeable
       sessions. Trade-off, stated: the tuning window is one year shorter than #307/#315's.
  * 900 trials, the runner's current default (#307/#315 ran 300, #330 ran 250).
  * GAPGO has no warm-up problem (20-day range), so it keeps the standard 12-month lockbox and is a
    straight re-run of #330 at 900 trials.
Windows pinned to each baseline run (rerun-window rule). Ranges OPEN (pinned-validate rule).
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


COMMON = dict(type="validate", status="queued", instrument="NQ", timeframe="5m", session="rth",
              source="db_noadj_rth", commission_usd=0.0, slippage_pts=0.0, equity_points=400,
              min_trades=30, mc_sims=2000, n_trials=900, n_rounds=0, wf_folds=8, select_oos_topk=10,
              discover="auto", provider="ollama", dsr=True, neighbors=True, regime=True, pills=True,
              context=True, progress=0, date_from="2010-06-07")

WARM = ("LOCKBOX IS 24 MONTHS ON PURPOSE: the validate's held-back read is a cold restart on the reserved slice, and "
        "this strategy places no trade until it has its trend length plus 30 sessions, so a 12-month slice starves it - "
        "run #307 showed 30 held-back trades and $5,920 against $22,719 run continuously over the same year, and run "
        "#315 (trend length 250) could not trade at all and FAILED on that alone. 24 months (~500 sessions) leaves room "
        "for the longest trend filter in range. Cost: the tuning window is a year shorter than #307/#315. ")
BETA = ("BETA CONTEXT (tools/nqdip_beta_check.py): long-only, constant $100,000 notional per mechanism in whole micros, "
        "up to four on at once. A trend-filtered always-long control at the SAME unit-days and NO costs makes $231,538 "
        "against the dip book's $479,321 over the #307 window - about half the dollars are exposure; timing doubles "
        "dollars per unit-day and wins 11 of 15 years. Dollars are NOT comparable to the one-contract legs. ")

JOBS = [
    dict(COMMON, strategy="NQDIP_1_0.py", cost_pts=0.0, mult=1, date_to="2026-08-24", lockbox_months=24,
         preset="NQDIP 1.0 RE-VALIDATE - 24-month lockbox so the trend filter can warm up, 900 trials",
         note=("Re-validate of run #307 (PASS at 300 trials, 12-month lockbox). Same file, same window, open ranges, "
               "costs inside the plugin (cost 0, mult 1). " + WARM + BETA)),
    dict(COMMON, strategy="NQDIP_1_1.py", cost_pts=0.0, mult=1, date_to="2026-08-24", lockbox_months=24,
         preset="NQDIP 1.1 RE-VALIDATE - 24-month lockbox so the trend filter can warm up, 900 trials",
         note=("Re-validate of run #315, which FAILED with ZERO held-back trades because it crowned trend length 250 "
               "and a cold 12-month slice cannot supply 280 sessions of warm-up - a structural failure, not a losing "
               "year. Same file, same window, open ranges, cost 0 / mult 1. " + WARM + BETA)),
    dict(COMMON, strategy="GAPGO_1_0.py", cost_pts=0.533, mult=20, date_to="2026-08-13", lockbox_months=12,
         preset="GAPGO 1.0 RE-VALIDATE - 900 trials, standard 12-month lockbox",
         note=("Straight re-run of run #330 (FAIL: held-back year 127 trades, PF 0.74, -$2,106) at the runner's current "
               "900 trials instead of 250. No warm-up issue - the gap filter needs only 20 sessions - so the lockbox "
               "stays at 12 months and the window is pinned to #330's. Mechanism: trade the overnight gap's direction "
               "(gap at least gap_mult x the 20-day average range) once a bar closes beyond the first-bar range, "
               "breakeven at 1R pinned, flat at the close. Expectation stated in advance: the held-back year is the "
               "same data #330 already read, so a different verdict would come from a different crowned config, "
               "not from new evidence.")),
]

if __name__ == "__main__":
    live = _retry(lambda: [(d.to_dict() or {}) for d in u.collection("backtests")
                           .where("status", "in", ["queued", "running"]).stream()])
    print("queue depth", len(live), [str(j.get("strategy"))[:24] + ":" + str(j.get("status")) for j in live])
    if len(live) > 7:
        sys.exit("ABORT queue too deep")
    busy = {j.get("strategy") for j in live}
    for job in JOBS:
        if job["strategy"] in busy:
            print("SKIP already queued/running:", job["strategy"]); continue
        job = dict(job, createdAt=datetime.datetime.now(datetime.timezone.utc))
        ref = u.collection("backtests").document(); _retry(lambda: ref.set(job))
        print("queued", ref.id, job["strategy"], "lockbox", job["lockbox_months"], "months")
