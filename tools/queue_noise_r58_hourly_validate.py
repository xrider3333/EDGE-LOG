"""Queue the round-58 Auto-Validate: live crown + squeeze filter with the verification frame FIXED at one hour
(NOISE_1_9_HSQ304H.py, 9 cells). Owner 2026-09-14: "auto validate anything that needs the auto validation."
The hourly filter is on EL only as single validate #390, which saves no walk-forward years; the three neighbourhood
validates that contained it crowned a 30-minute cell. Same window, cost and lockbox as #385/#387; 900 trials.
"""
import sys
import time

import firebase_admin
from firebase_admin import credentials, firestore

firebase_admin.initialize_app(credentials.Certificate("serviceAccount.json"))
u = firestore.client().collection("users").document("IO0K35JpLIcH9YK4C0pMNYUzZOM2")


def retry(fn, tries=5):
    for i in range(tries):
        try:
            return fn()
        except Exception as e:                                      # noqa: BLE001
            time.sleep(3 * (i + 1))
            print("retry", i + 1, type(e).__name__)
    raise SystemExit("gave up talking to Firestore")


live = [d.to_dict() for d in retry(lambda: list(u.collection("backtests").stream()))
        if (d.to_dict() or {}).get("status") in ("queued", "running")]
if any(j.get("strategy") == "NOISE_1_9_HSQ304H.py" for j in live):
    sys.exit("ABORT already live")
job = dict(
    type="validate", status="queued", strategy="NOISE_1_9_HSQ304H.py",
    instrument="NQ", timeframe="5m", session="rth", source="db_noadj_rth",
    cost_pts=0.533, mult=20, commission_usd=0.0, slippage_pts=0.0,
    date_from="2010-06-07", date_to="2026-07-16", lockbox_months=12,
    equity_points=400, min_trades=30, mc_sims=2000, n_trials=900, n_rounds=0, wf_folds=8,
    select_oos_topk=10, discover="auto", provider="ollama",
    dsr=True, neighbors=True, regime=True, pills=True, context=True, progress=0,
    preset="NOISE round 58 - live crown x HOURLY squeeze filter, hourly frame fixed, 9 cells",
    note=("Round 58 (NOISE.md 2026-09-14). The live crown keeping only trades taken during an hourly squeeze "
          "(textbook centre 60-minute / 20 / 1.0: 615 trades, PF 2.351 on a continuous replay) is on EL only as "
          "single validate 390, which has no walk-forward years. Neighbourhood validates 385 and 387 crowned a "
          "30-minute cell. This file fixes the frame at one hour and opens only length and threshold (9 cells). "
          "The fence was drawn after seeing hourly beat 30-minute on these years. Read the lockbox continuously."),
)
ref = retry(lambda: u.collection("backtests").add(job)[1])
print("queued", ref.id, "NOISE_1_9_HSQ304H.py 900 trials")
