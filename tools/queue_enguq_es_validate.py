"""Queue the ENGU-Q R2 crown file on ES 1m ETH — the ES BRANCH of the ENGU-Q family (round 37, 2026-09-08).

Pre-queue reads (tools/r37_es_branch.py, r37b cost log, r37c plateau log): at its NQ defaults on the ES
24h tape 2010-06-07..2025-06-29 the R2 crown file scores n=2013 / $208,644 (at $50/pt, 0.40 pts/RT) /
PF 1.367 / DD $19,396 / n/DD 10.76 / 7-of-8 slices; top-10 share 69% (ENGU-Q's known tail shape), ex-top-10
+$64,902 at PF 1.11 = CONCENTRATED, queueable, said out loud. Every knob is ATR- or R-relative, so nothing
was re-tuned for ES. Window pinned to the R2 crown run #335 (2010-06-07..2026-06-30), 12-month lockbox,
open ranges as declared in the file, 8 walk-forward folds.

    python tools/queue_enguq_es_validate.py
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
print("queue depth", len(live), [str(j.get("strategy"))[:24] + ":" + str(j.get("instrument")) + ":" + str(j.get("status")) for j in live])
if len(live) > 9: sys.exit("ABORT queue too deep")
if any(j.get("strategy") == "ENGUQ_1M_ETH_R2_1_0.py" and j.get("instrument") == "ES" for j in live):
    sys.exit("ABORT ENGU-Q R2 on ES already queued/running")
job = dict(type="validate", status="queued", strategy="ENGUQ_1M_ETH_R2_1_0.py",
    instrument="ES", timeframe="1m", session="eth", source="db_noadj_eth",
    cost_pts=0.40, mult=50, commission_usd=0.0, slippage_pts=0.0,
    date_from="2010-06-07", date_to="2026-06-30", lockbox_months=12,
    equity_points=400, min_trades=30, mc_sims=2000, n_trials=250, n_rounds=0, wf_folds=8,
    select_oos_topk=10, discover="auto", provider="ollama",
    dsr=True, neighbors=True, regime=True, pills=True, context=True, progress=0,
    preset="ENGU-Q R2 on ES 1m 24h - the ES BRANCH of the ENGU-Q family (round 37)",
    note=("Round 37 (tools/r37_es_branch.py): the crowned NQ files were run unchanged on the ES tape. ORB "
          "does not travel (PF 1.06, ex-top-10 negative) and NOISE is a near miss (PF 1.24, 5 of 8 slices), "
          "but the ENGU-Q R2 crown file at its NQ defaults clears the house bar on ES 24h 1-minute: "
          "2,013 trades / $208,644 at $50 a point after 0.40 points a round trip / PF 1.37 / DD $19,396 / "
          "n-per-DD 10.8 / 7 of 8 chronological slices / EV R 0.27. Every knob is ATR- or R-relative so "
          "nothing was re-tuned for ES. CONCENTRATION said out loud: top-10 share 69 percent (ENGU-Q's "
          "known tail shape; the NQ crown is 52), ex-top-10 +$64,902 at PF 1.11 = concentrated, queueable. "
          "Cost sensitivity and the one-step plateau read are in tools/r16_results/r37b_* and r37c_*. "
          "Window pinned to the R2 crown run #335 (2010-06-07..2026-06-30) so the NQ and ES branches are "
          "comparable; the ES lockbox has never been loaded locally. This is a BRANCH validate: the ask is "
          "whether the ENGU-Q mechanism survives a walk-forward and a sealed year on a second instrument, "
          "which would make ENGU-Q the first family with an ES leg for the ES/MES account."))
job["createdAt"] = datetime.datetime.now(datetime.timezone.utc)
ref = u.collection("backtests").document(); _retry(lambda: ref.set(job))
print("queued", ref.id, job["strategy"], "on", job["instrument"])
