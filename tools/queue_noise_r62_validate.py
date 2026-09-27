"""Queue the round-62 NOISE Auto-Validate (NOISE.md round 62, 2026-09-27; MANAGER status tasker, owner 2026-09-27).

  NOISE_1_8_CT422V   NOISE #422's crowned cell with the volatility-skip MEMORY opened (68 / 160 / 252 prior sessions)
                     beside the skip threshold (92.5 / 95 / 97.5) - 9 fenced cells. Asks whether the ~68-session
                     memory the live engine can hold trades as well as the validated 252. Centre = #422's cell
                     exactly (4,824 trades, $540,428 to 2026-07-15; tools/r62_noise_ct422v_parity.py).

Window, cost and lockbox match runs #420 / #422. 900 trials, passed explicitly. Refuses if already queued or running.
"""
import sys
import time

import firebase_admin
from firebase_admin import credentials, firestore

firebase_admin.initialize_app(credentials.Certificate("serviceAccount.json"))
u = firestore.client().collection("users").document("IO0K35JpLIcH9YK4C0pMNYUzZOM2")

JOBS = [
    ("NOISE_1_8_CT422V.py",
     "NOISE #422's crowned cell (live crown core + hourly squeeze 1.75x) with the volatility-skip memory opened: "
     "68 / 160 / 252 prior sessions x skip 92.5 / 95 / 97.5 (9 fenced cells). Pre-registered NON-INFERIORITY bar: the "
     "68-session cell at skip 95 is acceptable for live if the validate is not FAIL and, replayed continuously, its "
     "profit factor is within 0.02 of the 252-session cell (or above) in BOTH the walk-forward and the sealed year. "
     "The crowned cell is reported, never adopted from this round."),
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
        preset="NOISE round 62 - " + fn[:-3],
        note=("Round 62 (NOISE.md 2026-09-27). MANAGER status tasker: run the next pre-registered NOISE "
              "backtest that needs no owner decision. This job: " + what + " Fenced neighbourhood, parity-checked to the dollar. READ THE "
              "LOCKBOX CONTINUOUSLY: the saved strip is a cold-restart reload for NOISE. Nothing moves "
              "without the owner."),
    )
    ref = retry(lambda: u.collection("backtests").add(job)[1])
    print("queued", ref.id, fn, "900 trials")
