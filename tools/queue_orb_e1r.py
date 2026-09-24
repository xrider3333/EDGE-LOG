"""Queue the Auto-Validate of run #257's region (ORB_3_6_E1R.py, ES transfer on).

    python tools/queue_orb_e1r.py

Window pinned to the certified one every configuration in the ranking table was measured on
(2010-06-07 to 2026-08-13, 12-month lockbox), so the result is comparable to runs #234, #257
and #314. Trial budget 900, the owner's standing figure, against a 729-cell space.

It refuses to add anything if the queue is already more than nine deep.
"""
import datetime
import os
import sys
import time

os.chdir(r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG")
import firebase_admin
from firebase_admin import credentials, firestore
from google.api_core import exceptions as _gx

if not firebase_admin._apps:
    firebase_admin.initialize_app(credentials.Certificate("serviceAccount.json"))
u = firestore.client().collection("users").document("IO0K35JpLIcH9YK4C0pMNYUzZOM2")


def _retry(fn, tries=7, wait=600):
    for i in range(tries):
        try:
            return fn()
        except (_gx.ResourceExhausted, _gx.ServiceUnavailable, _gx.DeadlineExceeded) as e:
            print("attempt %d blocked (%s); waiting %ds" % (i + 1, type(e).__name__, wait), flush=True)
            if i == tries - 1:
                raise
            time.sleep(wait)


from google.cloud.firestore_v1.base_query import FieldFilter as _FF
busy = _retry(lambda: [(d.to_dict() or {}).get("strategy")
                       for st in ("queued", "running", "paused")
                       for d in u.collection("backtests").where(filter=_FF("status", "==", st)).stream()])
print("queue depth", len(busy), [str(b)[:34] for b in busy])
if len(busy) > 9:
    sys.exit("ABORT queue too deep")

job = dict(
    type="validate", status="queued", strategy="ORB_3_6_E1R.py",
    instrument="NQ", timeframe="5m", session="rth", source="db_noadj_rth",
    cost_pts=0.533, mult=20, commission_usd=0.0, slippage_pts=0.0,
    date_from="2010-06-07", date_to="2026-08-13", lockbox_months=12,
    equity_points=400, min_trades=30, mc_sims=2000, n_trials=900, n_rounds=0, wf_folds=0,
    select_oos_topk=5, discover="auto", provider="ollama",
    dsr=True, neighbors=True, regime=True, pills=True, context=True, progress=0,
    transfer_to="ES",
    preset="ORB E1 region - run #257's money direction, mapped instead of pinned",
    note=("Run #257 is the configuration with the most walk-forward money in the opening-range "
          "family ($339,110 against the control's $310,678) and the most money by calendar year "
          "(+$25,338 over the control, +$17,138 across the four biggest years), and it is starred. "
          "But it exists only as a pinned card: one configuration evaluated, so no parameter "
          "landscape, no neighbours, no plateau, no PBO/DSR - and its walk-forward number is NOT "
          "comparable to the crown's, because a pinned run has nothing to re-fit inside a fold "
          "while run #314 re-fitted in every fold for its $252,549. This validate puts #257's "
          "direction through the same hard test. #257 changes three knobs against the control, all "
          "in one direction - hold the trade open wider and gate it less: stop 2.00 to 2.50, "
          "breakout buffer 0.25 to 0.30, vol-regime filter 0.70 to 0.50. The family agrees with "
          "that direction: walk-forward money falls in lockstep as the filters tighten (#257/#266 "
          "$334-339k, control cluster $310k, #294 $290k, #297 $276k, #298 $262k) and the calendar "
          "years say the same, so tighter filters are a drawdown dial. But the direction does not "
          "run forever - #266, which removes the vol-regime filter entirely, earns $6,470 LESS than "
          "#257 which merely loosens it. So there is an interior best between loose and off, and a "
          "pinned point cannot show where it is or how broad the plateau is. Six knobs carry narrow "
          "ranges straddling #257 on both sides (729 cells, budget 900); everything else is the "
          "control's value, pinned. HONEST MARK: this is a neighbourhood map, not a hunt for a new "
          "crown. This session's meta walk-forward showed that re-picking opening-range parameters "
          "across the full space has NO forward skill - re-picking earned $166k over eleven forward "
          "years against $377k for leaving the parent defaults alone - so a neighbour that beats "
          "#257 by a few thousand dollars is not a reason to move anything. Judge on walk-forward "
          "folds against the control's 7 of 8, on walk-forward efficiency against the crown's 3.15 "
          "which is the only other number measured the same re-fitted way, on the lockbox against "
          "$88,943, and on whether the plateau around #257 is broad or a spike. ES transfer leg on. "
          "Defaults reproduce #257 exactly: net $416,382, drawdown $32,505, 2,751 trades."))
job["createdAt"] = datetime.datetime.now(datetime.timezone.utc)
ref = u.collection("backtests").document()
_retry(lambda: ref.set(job))
print("queued", ref.id, job["strategy"])
