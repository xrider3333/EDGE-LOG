"""Queue the five round-57 NOISE Auto-Validates -- every scorecard configuration that has never been the
champion of an Auto-Validate (round 56, NOISE.md 2026-09-13).

Owner, 2026-09-13: "some of these configs are in an auto validate, and some aren't - start auto validating them
... keep up the robust overparameterization of the IS portion (900)."

  NOISE_1_9_HSQ304   live crown, only trades during an hourly squeeze    (a cell of #385, never crowned)
  NOISE_1_9_HSQ243   retired #243, only trades during an hourly squeeze  (a cell of #321, never crowned)
  NOISE_1_1_N304     the crown settings on 15-minute bars                (hand test, round 44)
  NOISE_1_1_N304C2   the crown settings waiting for 2 closes             (hand test, round 45)
  NOISE_1_4_C3N      the cost-robust corner C3                           (hand test, rounds 38-43)

Each file is a fenced one-step neighbourhood with the configuration as every knob's default, parity-checked:
its centre cell reproduces the round-56 scorecard to the dollar and out-of-set cells are refused. Windows,
costs and lockbox match runs #382 and #385 (15-minute bars end at the tape's own last day, 2026-06-30).
900 trials each, the runner default, passed explicitly. The runner's five job slots take all five at once.

Nothing is adopted. Refuses if the queue is more than nine deep or any of these files is already live.
"""
import sys
import time

import firebase_admin
from firebase_admin import credentials, firestore

firebase_admin.initialize_app(credentials.Certificate("serviceAccount.json"))
u = firestore.client().collection("users").document("IO0K35JpLIcH9YK4C0pMNYUzZOM2")

JOBS = [
    ("NOISE_1_9_HSQ304.py", "5m", "2026-07-16",
     "live crown, only trades during an hourly squeeze - 27 fenced cells centred on the textbook hourly setting; "
     "a cell of run 385 that its search never crowned. Scorecard centre: 615 trades, PF 2.351, 2024 on 2.184."),
    ("NOISE_1_9_HSQ243.py", "5m", "2026-07-16",
     "retired 243, only trades during an hourly squeeze - 27 fenced cells centred on the textbook hourly setting; "
     "a cell of run 321 that its search never crowned. Scorecard centre: 586 trades, PF 2.233, 2024 on 2.140."),
    ("NOISE_1_1_N304.py", "15m", "2026-06-30",
     "the live crown settings on 15-minute bars - 243 fenced cells, one step each side on five knobs; hand test "
     "of round 44, never validated (run 362 searched 15-minute bars wide open and crowned something else). "
     "Scorecard centre: 3,011 trades, PF 1.446, 2024 on 1.356."),
    ("NOISE_1_1_N304C2.py", "5m", "2026-07-16",
     "the live crown settings waiting for 2 closes - 243 fenced cells; hand test of round 45, never validated "
     "(run 316 validated a different 2-close configuration). Scorecard centre: 4,075 trades, PF 1.403, 2024 on 1.299."),
    ("NOISE_1_4_C3N.py", "5m", "2026-07-16",
     "the cost-robust corner C3 - 729 fenced cells, one step each side on six knobs; hand-measured rounds 38 to 43, "
     "never validated. Scorecard centre: 2,112 trades, PF 1.457, 2024 on 1.343."),
]


def retry(fn, tries=5):
    for i in range(tries):
        try:
            return fn()
        except Exception as e:                                      # noqa: BLE001
            wait = 3 * (i + 1)
            print("attempt %d blocked (%s); waiting %ds" % (i + 1, type(e).__name__, wait), flush=True)
            time.sleep(wait)
    raise SystemExit("gave up talking to Firestore")


live = [d.to_dict() for d in retry(lambda: list(u.collection("backtests").stream()))
        if (d.to_dict() or {}).get("status") in ("queued", "running")]
print("queue depth", len(live), [str(j.get("strategy"))[:22] + ":" + str(j.get("status")) for j in live])
if len(live) + len(JOBS) > 14:
    sys.exit("ABORT queue too deep")
names = {j.get("strategy") for j in live}
for fn, _, _, _ in JOBS:
    if fn in names:
        sys.exit("ABORT %s is already queued or running" % fn)

for fn, tf, date_to, what in JOBS:
    job = dict(
        type="validate", status="queued", strategy=fn,
        instrument="NQ", timeframe=tf, session="rth", source="db_noadj_rth",
        cost_pts=0.533, mult=20, commission_usd=0.0, slippage_pts=0.0,
        date_from="2010-06-07", date_to=date_to, lockbox_months=12,
        equity_points=400, min_trades=30, mc_sims=2000, n_trials=900, n_rounds=0, wf_folds=8,
        select_oos_topk=10, discover="auto", provider="ollama",
        dsr=True, neighbors=True, regime=True, pills=True, context=True, progress=0,
        preset="NOISE round 57 - never-validated config: " + fn[:-3],
        note=("Round 57 (NOISE.md 2026-09-13). Owner asked for every NOISE configuration that has never been "
              "an Auto-Validate champion to be validated, at 900 in-sample trials. This job: " + what + " The file "
              "is a fenced neighbourhood with this configuration as every knob default, parity-checked to the "
              "dollar against the round-56 scorecard. READ THE LOCKBOX CONTINUOUSLY: the saved strip is a "
              "cold-restart reload that drops a large share of the NOISE sealed year. Nothing moves without "
              "the owner."),
    )
    ref = retry(lambda: u.collection("backtests").add(job)[1])
    print("queued", ref.id, fn, tf, "to", date_to, "900 trials")
