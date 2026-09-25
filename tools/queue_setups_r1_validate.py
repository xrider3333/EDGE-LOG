"""Queue the SETUPS round 1 Auto-Validate: CBU-Q on NQ 1m 24h (SETUPS_PREREG.md section 7).

Triage (tools/setups_r1_triage.py, 516 pre-declared cells): exactly one cell passes the house bar -
CBUQ_1M_1_0.py on NQ, level_mode pdh / end_min 30 / vol_mult 2 / ride be_R 1: n=617, $52,868 at
$20/pt after 0.533 pts/RT, PF 1.805, net/DD 8.79, 8 of 8 slices, stress PF 1.729, 5 of 5 one-step
neighbours >= 1.15. Pre-queue gates: queue_guard PASS (not an artifact); concentration_check
CONCENTRATED (top-10 share 85%, ex-top-10 +$7,970 at PF 1.12) - queueable, said out loud. The guard's
continuous run through the sealed stretch shows the triage cell at 27 trades / PF 0.44 there; the
validate searches the full declared space and grades its own crown, so this is stated, not acted on.

Job exactly as pre-registered: 900 trials, 8 walk-forward folds, window 2010-06-07..2026-04-06 with a
9-month lockbox (2025-07-07..2026-04-06), declared ranges only (auto_expand off), no landscape sample
(oos_sample_k 0), transfer to ES. Verdict rule (section 7): PASS required; the crown's sealed stretch
needs >= 60 trades and PF >= 1.10; and it must earn on days ORB #314 and NOISE #382 are flat.

    python tools/queue_setups_r1_validate.py
"""
import os, sys, datetime, time
os.chdir(r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG")
import firebase_admin
from firebase_admin import credentials, firestore
from google.api_core import exceptions as _gx
if not firebase_admin._apps:
    firebase_admin.initialize_app(credentials.Certificate("serviceAccount.json"))
u = firestore.client().collection("users").document("IO0K35JpLIcH9YK4C0pMNYUzZOM2")
STRAT = "CBUQ_1M_1_0.py"


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
print("queue depth", len(live), [str(j.get("strategy"))[:24] + ":" + str(j.get("instrument")) + ":" + str(j.get("status")) for j in live])
if len(live) > 9:
    sys.exit("ABORT queue too deep")
if any(j.get("strategy") == STRAT and j.get("instrument") == "NQ" for j in live):
    sys.exit("ABORT CBU-Q on NQ already queued/running")
job = dict(type="validate", status="queued", strategy=STRAT,
    instrument="NQ", timeframe="1m", session="eth", source="db_noadj_eth",
    cost_pts=0.533, mult=20, commission_usd=0.0, slippage_pts=0.0,
    date_from="2010-06-07", date_to="2026-04-06", lockbox_months=9,
    equity_points=400, min_trades=30, mc_sims=2000, n_trials=900, n_rounds=0, wf_folds=8,
    select_oos_topk=10, oos_sample_k=0, auto_expand=False, transfer_to="ES",
    discover="auto", provider="ollama",
    dsr=True, neighbors=True, regime=True, pills=True, context=True, progress=0,
    preset="SETUPS round 1 - CBU-Q on NQ 1m 24h (the owner CBU setup, automated)",
    note=("SETUPS round 1 (SETUPS_PREREG.md): the owner discretionary setups CBU, CBD, EBU, ENGU and ENGD "
          "as five strategy files over 516 pre-declared triage cells on NQ and ES. One cell passes the house "
          "bar: CBU on NQ, a close at a new high of the day above the prior-day high inside the first 30 "
          "minutes on twice the usual volume, breakeven at 1R then ride to the close - 617 trades, 52,868 "
          "dollars, profit factor 1.81, net over drawdown 8.8, 8 of 8 slices, 1.73 at the stressed cost, "
          "5 of 5 neighbours above 1.15. CONCENTRATED, said out loud: top-ten share 85 percent, ex-top-10 "
          "plus 7,970 at profit factor 1.12. The pre-queue guard shows that triage cell at 27 trades and "
          "profit factor 0.44 in the sealed stretch; this validate searches the full declared space and "
          "grades its own crown. Lockbox 9 months (2025-07-07 to 2026-04-06) so no journal trade sits in it."))
job["createdAt"] = datetime.datetime.now(datetime.timezone.utc)
ref = u.collection("backtests").document()
_retry(lambda: ref.set(job))
print("queued", ref.id, job["strategy"], "on", job["instrument"])
