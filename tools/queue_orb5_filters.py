"""Queue the three round-5 FILTER candidates as PINNED Auto-Validates.

Round 5 (tools/orb_hunt5.py, 2026-08-26) swept the crown's two filters, which had never
been questioned -- they came along with the config that won. Thirteen cells cleared the
pre-registered gate, all of them "filter harder". These three are the spread of that
ridge: one knob, both knobs, both knobs harder.

Window, lockbox, source and costs are pinned to run #234's own job so the verdicts are
directly comparable to the crown's (the HARD RULE on rerun windows).

THE CAUTION THAT TRAVELS WITH THESE: a whole ridge clearing at once is weaker evidence
than a lone cell. Every candidate buys its better lockbox and worse-year with FEWER
trades. The walk-forward and the ES transfer leg decide, not the offline table.
"""
import os
import sys
import datetime

os.chdir(r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG")
import firebase_admin
from firebase_admin import credentials, firestore

if not firebase_admin._apps:
    firebase_admin.initialize_app(credentials.Certificate("serviceAccount.json"))
db = firestore.client()
UID = "IO0K35JpLIcH9YK4C0pMNYUzZOM2"
u = db.collection("users").document(UID)

busy = [(d.id, (d.to_dict() or {}).get("status"))
        for d in u.collection("backtests").stream()
        if (d.to_dict() or {}).get("status") in ("queued", "running")]
print("queue depth:", len(busy), busy)
if len(busy) > 8:
    sys.exit("ABORT - queue too deep, not adding")

# every field mirrors run #234's job so the verdicts compare like with like
BASE = dict(type="validate", status="queued", instrument="NQ", timeframe="5m",
            session="rth", source="db_noadj_rth", cost_pts=0.533, mult=20,
            commission_usd=0.0, slippage_pts=0.0,
            date_from="2010-06-07", date_to="2026-08-13", lockbox_months=12,
            equity_points=400, min_trades=30, mc_sims=2000, n_trials=200, n_rounds=0,
            wf_folds=0, select_oos_topk=10, discover="auto", provider="ollama",
            dsr=True, neighbors=True, regime=True, pills=True, context=True, progress=0)

JOBS = [
    dict(strategy="ORB_3_6_F75.py",
         preset="ORB R5 FILTERS - crown #234 with vol-regime 0.75 (one knob)",
         note=("Round-5 filter sweep candidate 1 of 3. The crown with atr_filter 0.70 -> 0.75 "
               "and nothing else changed. Offline on the pinned window: net $386,710 (crown "
               "$389,874), maxDD $28,477 (crown $29,142), LB $92,383 (crown $88,943), roll12 "
               "win 73.2% (crown 72.7%), worst roll12 -$16,349 (crown -$22,050), 2,500 trades "
               "(crown 2,607). The mildest of the ridge: it costs 0.8% of the money and buys a "
               "better drawdown, lockbox and worst year. CAUTION: 13 cells cleared the same "
               "pre-registered gate, all of them 'filter harder', so this is ridge evidence "
               "rather than a lone signal. Judge on WF folds vs #234's 7/8 and on the ES "
               "transfer leg, which is where round 4's two gate-clearers died.")),
    dict(strategy="ORB_3_6_F7580.py",
         preset="ORB R5 FILTERS - crown #234 with vol-regime 0.75 + volume-pace 0.80",
         note=("Round-5 filter sweep candidate 2 of 3. Both filters tightened: atr 0.75, "
               "vpace 0.80. Offline: net $378,648, maxDD $30,275, LB $93,209, roll12 win 76.0%, "
               "worst -$16,206, 2,299 trades. The best-balanced cell on the ridge - 2.9% less "
               "money than the crown for a materially better worst year and win rate. Same "
               "caution as candidate 1: the improvement is bought with 12% fewer trades.")),
    dict(strategy="ORB_3_6_F8080.py",
         preset="ORB R5 FILTERS - crown #234 with both filters at 0.80",
         note=("Round-5 filter sweep candidate 3 of 3, the far end of the ridge: atr 0.80, "
               "vpace 0.80. Offline: net $367,833, maxDD $32,940, LB $101,017 (the best "
               "lockbox of the three, +13.6% on the crown), roll12 win 76.5%, worst -$18,199, "
               "2,169 trades (17% fewer than the crown). Included precisely BECAUSE it is the "
               "most aggressive: if the walk-forward likes the ridge, it should like this end "
               "of it too, and if it does not, that asymmetry is the finding.")),
]

for j in JOBS:
    doc = dict(BASE, **j)
    doc["createdAt"] = datetime.datetime.now(datetime.timezone.utc)
    ref = u.collection("backtests").document()
    ref.set(doc)
    print("queued", ref.id, j["strategy"])
