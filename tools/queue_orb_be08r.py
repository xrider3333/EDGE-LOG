"""Queue the Auto-Validate of run #239's region (ORB_3_6_BE08R.py, ES transfer on).

    python tools/queue_orb_be08r.py

Window pinned to the certified one every configuration in the ranking table was measured on
(2010-06-07 to 2026-08-13, 12-month lockbox), so the result is comparable to runs #234, #239,
#314 and #421. Trial budget 900, the owner's standing figure, against a 729-cell space.

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
    type="validate", status="queued", strategy="ORB_3_6_BE08R.py",
    instrument="NQ", timeframe="5m", session="rth", source="db_noadj_rth",
    cost_pts=0.533, mult=20, commission_usd=0.0, slippage_pts=0.0,
    date_from="2010-06-07", date_to="2026-08-13", lockbox_months=12,
    equity_points=400, min_trades=30, mc_sims=2000, n_trials=900, n_rounds=0, wf_folds=0,
    select_oos_topk=5, discover="auto", provider="ollama",
    dsr=True, neighbors=True, regime=True, pills=True, context=True, progress=0,
    transfer_to="ES",
    preset="ORB BE08 region - run #239 neighbourhood, re-fitted walk-forward (owner: auto-validate anything promising)",
    note=("Run #239 is the ORB control (#234) with the breakeven moved from 1.0 to 0.8 of the risk. Round 63 "
          "(ORB_ROUND63_BOOK463_LEG.md) found it is the only ORB leg that clears the pre-registered bar inside "
          "BOOK #463 (walk-forward ROC at a $30k daily-valued drawdown 101.9 vs 94.0 %/yr, lockbox 158.7 vs 155.5, "
          "Sortino better in both); the Frontier lane reproduced it to the cent (run #478). The owner's call is "
          "shadow first (paper leg ORB_239), and the owner asked that anything promising go through the house "
          "Auto-Validate. #239's only validate is a pinned card, so its walk-forward is an in-sample replay. This "
          "run fences six narrow ranges around #239 (729 cells, budget 900) so the walk-forward is re-fitted in "
          "every fold - the test only #314 and #421 have faced - and the report gets its landscape. HONEST MARK: "
          "read it for the REGION (folds held, re-fitted walk-forward ROC at $30k vs #314's 21.7 and #421's 22.4, "
          "plateau, PBO). Run #421 showed a re-tune can crown an edge cell that loses the lockbox to the frozen "
          "card, and re-tuning ORB has no forward skill, so a crowned cell that differs from #239 is NOT a "
          "candidate; the paper leg stays the frozen #239 cell. ES transfer leg on. Defaults reproduce #239 "
          "exactly: 2,607 trades, $394,864.38; lockbox 178 trades, $94,267.52, PF 1.4949."))

job["createdAt"] = datetime.datetime.now(datetime.timezone.utc)
ref = u.collection("backtests").document()
_retry(lambda: ref.set(job))
print("queued", ref.id, job["strategy"])
