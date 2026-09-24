"""Queue the two round-60 NOISE Auto-Validates (NOISE.md round 60, 2026-09-24).

Owner, 2026-09-24: "auto validate anything promising and continue searching."

  NOISE_1_9_GEO304   crown geometry searched on compressed hours only - 243 fenced cells, the hourly filter
                     frozen at run 398's crowned setting (60 min / 20 / 1.15). Centre: 996 trades, $188,870.
  NOISE_1_8_CT304H   hourly compression SIZE tilt on the live crown at 1.25 / 1.5 / 1.75x - 27 fenced cells,
                     frame frozen at 60 min, 2.0x and the 30-minute frame out of the set (both measured and
                     rejected in round 55). Centre (20 / 1.0 / 1.5x): 4,824 trades, $468,775 vs crown $398,776.

Both parity-checked to the dollar against the files they were cut from. Window, cost and lockbox match runs
#382, #385, #398 (2010-06-07 .. 2026-07-16, cost 0.533, 12-month lockbox). 900 trials, the runner default,
passed explicitly. Refuses if either file is already queued or running.
"""
import sys
import time

import firebase_admin
from firebase_admin import credentials, firestore

firebase_admin.initialize_app(credentials.Certificate("serviceAccount.json"))
u = firestore.client().collection("users").document("IO0K35JpLIcH9YK4C0pMNYUzZOM2")

JOBS = [
    ("NOISE_1_9_GEO304.py",
     "the crown's entry geometry searched again, but only on compressed hours - 243 fenced cells (lookback, "
     "both band widths, stop, volatility skip, one step either side of run 304), with the hourly squeeze "
     "filter frozen at run 398's crowned setting. Centre = run 398's champion on the crown: 996 trades, "
     "$188,870. Adopt a different geometry only if it PASSES, overfit <= 0.198, and beats the centre "
     "continuously on profit factor both before 2024 and from 2024 on."),
    ("NOISE_1_8_CT304H.py",
     "the hourly compression SIZE tilt on the live crown at a sane size - 27 fenced cells, frame frozen at "
     "60 minutes, tilt 1.25/1.5/1.75x (2.0x and the 30-minute frame are out: runs 382/409/410 crowned them "
     "and round 55 rejected them continuously). Centre 20/1.0/1.5x: 4,824 trades, $468,775 vs the crown's "
     "$398,776. Bar: sealed year earns at least the crown's dollars at <= 25% more drawdown and MAR >= crown."),
]


def retry(fn, tries=5):
    for i in range(tries):
        try:
            return fn()
        except Exception as e:                                      # noqa: BLE001
            print("attempt %d blocked (%s); waiting %ds" % (i + 1, type(e).__name__, 3 * (i + 1)), flush=True)
            time.sleep(3 * (i + 1))
    raise SystemExit("gave up talking to Firestore")


live = [d.to_dict() for d in retry(lambda: list(u.collection("backtests")
                                                .where("status", "in", ["queued", "running"]).stream()))]
print("queue depth", len(live))
names = {j.get("strategy") for j in live}
for fn, _ in JOBS:
    if fn in names:
        sys.exit("ABORT %s is already queued or running" % fn)

for fn, what in JOBS:
    job = dict(
        type="validate", status="queued", strategy=fn,
        instrument="NQ", timeframe="5m", session="rth", source="db_noadj_rth",
        cost_pts=0.533, mult=20, commission_usd=0.0, slippage_pts=0.0,
        date_from="2010-06-07", date_to="2026-07-16", lockbox_months=12,
        equity_points=400, min_trades=30, mc_sims=2000, n_trials=900, n_rounds=0, wf_folds=8,
        select_oos_topk=10, discover="auto", provider="ollama",
        dsr=True, neighbors=True, regime=True, pills=True, context=True, progress=0,
        preset="NOISE round 60 - " + fn[:-3],
        note=("Round 60 (NOISE.md 2026-09-24). Owner: auto validate anything promising and continue "
              "searching. This job: " + what + " Fenced neighbourhood, parity-checked to the dollar. READ THE "
              "LOCKBOX CONTINUOUSLY: the saved strip is a cold-restart reload for NOISE. Nothing moves "
              "without the owner."),
    )
    ref = retry(lambda: u.collection("backtests").add(job)[1])
    print("queued", ref.id, fn, "900 trials")
