"""Queue the ORB round-7 Auto-Validate (ORB_3_8_R7.py, ES transfer on).

Written 2026-09-05 but NOT sent: Firestore returned 429 Quota exceeded (Spark plan,
50k reads/day - see memory edgelog-firestore-quota). The job is parked here rather than
in a scratchpad because scratchpads get wiped. Re-run it once the daily quota resets:

    python tools/queue_orb_r7.py

It refuses to add anything if the queue is already more than nine deep.
"""
import os, sys, datetime
os.chdir(r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG")
import firebase_admin
from firebase_admin import credentials, firestore
if not firebase_admin._apps:
    firebase_admin.initialize_app(credentials.Certificate("serviceAccount.json"))
u = firestore.client().collection("users").document("IO0K35JpLIcH9YK4C0pMNYUzZOM2")
busy=[(d.to_dict() or {}).get("strategy") for d in u.collection("backtests").stream()
      if (d.to_dict() or {}).get("status") in ("queued","running")]
print("queue depth", len(busy), [str(b)[:34] for b in busy])
if len(busy) > 9: sys.exit("ABORT queue too deep")
job = dict(type="validate", status="queued", strategy="ORB_3_8_R7.py",
    instrument="NQ", timeframe="5m", session="rth", source="db_noadj_rth",
    cost_pts=0.533, mult=20, commission_usd=0.0, slippage_pts=0.0,
    date_from="2010-06-07", date_to="2026-08-13", lockbox_months=12,
    equity_points=400, min_trades=30, mc_sims=2000, n_trials=250, n_rounds=0, wf_folds=0,
    select_oos_topk=10, discover="auto", provider="ollama",
    dsr=True, neighbors=True, regime=True, pills=True, context=True, progress=0,
    transfer_to="ES",
    preset="ORB R7 - crown #314 + the prior-day LONG filter (the shelved 2026-08-18 lead)",
    note=("Round 7 (tools/orb_hunt7.py). ORB.md flagged on 2026-08-18 that ORB's genuinely bad "
          "population is LONG entries after a prior-day close in the 0.6-0.8 band (252 trades, "
          "-$103 each, PF 0.79) and called it an unexploited, not-yet-pre-registered lead. Tried "
          "once on the #234 exit it did not clear; on the #314 exit that was just crowned it clears "
          "every leg of a gate written before the sweep ran (MAR on the FULL window AND the last 5 "
          "years, plus lockbox and worst rolling year). Crown #314: 5y MAR 2.79 / full MAR 0.85 / "
          "full DD $28,857 / LB $87,132 / worst -$13,608. With the filter at 0.60-0.85 and the stop "
          "at 3.0x: 5y MAR 3.13 / full MAR 1.18 / full DD $22,442 / LB $99,844 / worst -$7,917. "
          "WHY IT READS AS REAL: it is DIRECTIONAL - skipping the LONGS clears at 8 of 8 bands "
          "tested, while skipping BOTH sides in the same bands is a disaster at every one (full MAR "
          "0.50-0.60). A pure trade-count effect would help both. Live-legal: the prior session's "
          "close position is fixed before this session opens. HONEST MARK: this stacks two levers "
          "found in one sweep, so the file leaves both OPEN (stop 2.5-3.0 so the WF can decline the "
          "widening; partial and trail 0-on; band edges 0.55-0.65 / 0.80-0.90) and the breakeven is "
          "PINNED, never searched, because it sets EV R's denominator. Window pinned to #234/#314. "
          "ES transfer leg on."))
job["createdAt"] = datetime.datetime.now(datetime.timezone.utc)
ref = u.collection("backtests").document(); ref.set(job)
print("queued", ref.id, job["strategy"])
