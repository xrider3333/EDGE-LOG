"""Queue the ENGU-Q R2 crown file on ES 1m ETH at REALISTIC FILL COST (round 46, 2026-09-09).

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
if any(j.get("strategy") == "ENGUQ_1M_ETH_R2_1_0.py" and j.get("instrument") == "ES"
       and float(j.get("cost_pts") or 0) == 0.60 for j in live):
    sys.exit("ABORT ENGU-Q R2 on ES at 0.60 already queued/running")
job = dict(type="validate", status="queued", strategy="ENGUQ_1M_ETH_R2_1_0.py",
    instrument="ES", timeframe="1m", session="eth", source="db_noadj_eth",
    cost_pts=0.60, mult=50, commission_usd=0.0, slippage_pts=0.0,
    date_from="2010-06-07", date_to="2026-06-30", lockbox_months=12,
    equity_points=400, min_trades=30, mc_sims=2000, n_trials=250, n_rounds=0, wf_folds=8,
    select_oos_topk=10, discover="auto", provider="ollama",
    dsr=True, neighbors=True, regime=True, pills=True, context=True, progress=0,
    preset="ENGU-Q R2 on ES 1m 24h at 0.60 a round trip - the REALISTIC-FILL grade (round 46)",
    note=("Round 46 (tools/r46_enguq_es_recency.py). This is the SAME file, window and lockbox as the ES "
          "validate already running at 0.40 a round trip, re-run at 0.60 - about 30 dollars on one ES, which is "
          "one tick of slippage plus commission. WHY: round 42 closed the NOISE ES branch precisely on this "
          "point (it earned 44 to 57 dollars a trade against a 25 to 30 dollar round trip and failed the house "
          "rule that a trade must pay twice its cost), and the rule written down there was that any future ES "
          "validate must be queued at 0.50 or worse. The ENGU-Q ES leg passes that arithmetic comfortably: "
          "98.48 dollars a trade at 0.60, which is 3.3 times its cost, against NOISE-on-ES at under 2. "
          "RECENCY, the other reason this is worth a second grade: a sibling found that essentially everything "
          "which improves NOISE over 2010 to 2023 has lost money over 2024 to 2026. The ENGU-Q ES leg is the "
          "opposite - profit factor 1.24 over 2010-2023 and 1.59 over 2024-2026 at this cost, with 357 dollars "
          "a trade in the recent stretch against 66 before it. HONEST MARKS: 2015 and 2016 were losing years on "
          "ES (minus 4,578 and minus 10,500 at this cost); the recent strength comes from bigger trades rather "
          "than more of them, and the drawdown arrives in the same stretch (net over drawdown 2.5 across "
          "2024-2026 versus 5.5 before); 2026 to the end of June is nearly flat at 2,010 dollars on 62 trades. "
          "The lockbox here is the same twelve months the 0.40 run is grading, so it is a cost sensitivity on a "
          "sealed year rather than a fresh sealed year - read it as: does the verdict survive honest fills."))
job["createdAt"] = datetime.datetime.now(datetime.timezone.utc)
ref = u.collection("backtests").document(); _retry(lambda: ref.set(job))
print("queued", ref.id, job["strategy"], "on", job["instrument"])
