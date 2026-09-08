"""Queue the pre-registered 2x SIZE-TILT validate of the compression finding (owner 2026-09-08).

Run #321 validated the compression read as a FILTER (NOISE_1_1_SBS_V90_SQ.py): PASS 6/6,
WF 7/8, PBO 0.099, but a filter keeps 13% of the trades and earns ~40% less than the ungated
paper leg with a lower annualised MAR. The round-6 writeup and the feature board both say the
live form is a SIZE TILT. NOISE_1_1_SBS_V90_SQT.py takes every trade and doubles the size of
the coiled ones, tilt fixed at 2.0, same fenced 27-cell gate neighbourhood as #321.

EVERY JOB FIELD IS COPIED FROM RUN #321'S OWN JOB (doc wyWdcdsZqoVGGlVyZYh0) so the two
verdicts compare like with like - the HARD RULE on rerun windows. Only `strategy`, `preset`
and `note` differ. The job's cost_pts must equal the strategy's house figure (0.533), because
the file charges the second contract's round trip itself; the script refuses otherwise.

The decision rule lives in the strategy file's docstring and is repeated in the job note so
the report carries it. Judge in that order and stop at the first failure.
"""
import os
import sys

os.chdir(r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG")
import firebase_admin
from firebase_admin import credentials, firestore

if not firebase_admin._apps:
    firebase_admin.initialize_app(credentials.Certificate("serviceAccount.json"))
db = firestore.client()
UID = "IO0K35JpLIcH9YK4C0pMNYUzZOM2"
u = db.collection("users").document(UID)

STRAT = "NOISE_1_1_SBS_V90_SQT.py"
if not os.path.exists(os.path.join("augur_strategies", STRAT)):
    sys.exit(f"ABORT - {STRAT} is not in the runner's checkout (ship first)")

busy = [(d.id, (d.to_dict() or {}).get("status"))
        for d in u.collection("backtests").stream()
        if (d.to_dict() or {}).get("status") in ("queued", "running", "paused")]
print("queue depth:", len(busy), busy)
if len(busy) > 8:
    sys.exit("ABORT - queue too deep, not adding")
if any(STRAT in str((u.collection("backtests").document(i).get().to_dict() or {}).get("strategy"))
       for i, _ in busy):
    sys.exit(f"ABORT - a {STRAT} job is already queued or running")

SRC_DOC = "wyWdcdsZqoVGGlVyZYh0"          # run #321, the filter validate
src = (u.collection("backtests").document(SRC_DOC).get().to_dict() or {})
if not src or "NOISE_1_1_SBS_V90_SQ" not in str(src.get("strategy", "")):
    sys.exit("ABORT - could not read run #321's job to copy its window")
if abs(float(src.get("cost_pts", -1)) - 0.533) > 1e-9:
    sys.exit(f"ABORT - #321 cost_pts is {src.get('cost_pts')}, the tilt file assumes 0.533")

CARRY = ["type", "instrument", "timeframe", "session", "source", "cost_pts", "mult",
         "commission_usd", "slippage_pts", "date_from", "date_to", "lockbox_months",
         "equity_points", "min_trades", "mc_sims", "n_trials", "n_rounds", "wf_folds",
         "select_oos_topk", "discover", "provider", "dsr", "neighbors", "regime",
         "pills", "context"]
job = {k: src[k] for k in CARRY if k in src}
job.update(
    status="queued",
    progress=0,
    strategy=STRAT,
    preset="NOISE paper leg + hourly-compression 2x SIZE TILT (FENCED 27-cell neighbourhood, tilt fixed 2.0)",
    note=("PRE-REGISTERED size-tilt validate of the compression finding, the live form of run "
          "#321's filter. Every trade taken; a trade decided while the hourly squeeze was "
          "compressed is taken at 2x size (fixed, not searched). Same 27 fenced gate cells as "
          "#321, same window, costs, source and lockbox, copied from #321's own job. The second "
          "contract pays its own round trip (charged inside the file at 0.533 pts). DECISION "
          "RULE, in order, stop at the first failure: (1) PASS with WF >= 6/8 and a positive "
          "lockbox, else not adopted; (2) full-window drawdown <= 1.10 x the ungated paper leg's "
          "(local read $18,425) - worse means leverage, not edge; (3) full-window PF >= 1.45 and "
          "net above the ungated $395,169; (4) lockbox PF >= the ungated lockbox PF (1.36). All "
          "four = adopt as the NOISE paper leg size rule (2 contracts coiled, 1 otherwise). "
          "Round-6 scan expectation: +$124k, PF 1.41 -> 1.49, DD unchanged."),
    created_by="tools/queue_sq_tilt.py",
    createdAt=firestore.SERVER_TIMESTAMP,
)

for k in ("date_from", "date_to", "source", "cost_pts", "lockbox_months"):
    if k not in job:
        sys.exit(f"ABORT - {k} missing, refusing to queue an unpinned window")

ref = u.collection("backtests").document()
ref.set(job)
print("queued:", ref.id)
print("  strategy :", job["strategy"], "| 27 fenced cells, tilt 2.0 fixed")
print("  window   :", job["date_from"], "->", job["date_to"], "| lockbox", job["lockbox_months"], "mo")
print("  source   :", job["source"], "| cost_pts", job["cost_pts"], "| mult", job["mult"])
