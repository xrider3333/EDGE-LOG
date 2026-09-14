"""Queue the NOISE SQUEEZE-FILTER-ON-THE-LIVE-CROWN Auto-Validate (run #321's 27-cell grid, re-based).

WHY (round 56, 2026-09-13 -- NOISE.md). Run #321 validated the higher-timeframe squeeze as a FILTER
and PASSED 6 of 6 with the family's lowest overfit score (PBO 0.099), but froze its core to run #243,
the crown retired on 2026-09-05. Round 56 replayed every NOISE configuration on one continuous tape
and the filter family tops it on every quality number. On the live crown the textbook hourly cell
(60-minute frame, length 20, ratio 1.0) reads 615 trades, profit factor 2.351, 2024-onward 2.184,
sealed year 1.985, one losing year of seventeen, 1.814 with its ten best trades removed; 25 of the 27
grid cells beat the raw crown's 1.357 and all nine hourly cells sit between 1.68 and 2.35. The
textbook cell is the TOP of that plateau, so the neighbourhood's level is the honest expectation.

Nobody has validated the filter on the base that trades. This job does, with #321's own
pre-registered grid unchanged -- not re-fenced around the cell that was noticed.
`augur_strategies/NOISE_1_9_SQ304.py` reproduces the round-56 harness to the dollar (textbook cell
615 trades / $139,997; #321's pick 1,661 / $209,211) and refuses any out-of-set cell.

READ THE LOCKBOX CONTINUOUSLY. The validate grades its lockbox on a cold-restart reload, which for
NOISE drops a large share of the sealed year. Judge the bar in the strategy file's docstring on a
continuous replay sliced by entry time.

Nothing is adopted by this job. Refuses if the queue is more than nine deep, or if this file is
already queued or running.
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
            wait = 3 * (i + 1)
            print("attempt %d blocked (%s); waiting %ds" % (i + 1, type(e).__name__, wait), flush=True)
            time.sleep(wait)
    raise SystemExit("gave up talking to Firestore")


live = [d.to_dict() for d in retry(lambda: list(u.collection("backtests").stream()))
        if (d.to_dict() or {}).get("status") in ("queued", "running")]
print("queue depth", len(live), [str(j.get("strategy"))[:22] + ":" + str(j.get("status")) for j in live])
if len(live) > 9:
    sys.exit("ABORT queue too deep")
if any(j.get("strategy") == "NOISE_1_9_SQ304.py" for j in live):
    sys.exit("ABORT NOISE_1_9_SQ304.py is already queued or running")

job = dict(
    type="validate", status="queued", strategy="NOISE_1_9_SQ304.py",
    instrument="NQ", timeframe="5m", session="rth", source="db_noadj_rth",
    cost_pts=0.533, mult=20, commission_usd=0.0, slippage_pts=0.0,
    date_from="2010-06-07", date_to="2026-07-16", lockbox_months=12,
    equity_points=400, min_trades=30, mc_sims=2000, n_trials=120, n_rounds=0, wf_folds=8,
    select_oos_topk=10, discover="auto", provider="ollama",
    dsr=True, neighbors=True, regime=True, pills=True, context=True, progress=0,
    preset="NOISE squeeze FILTER on the LIVE crown - run 321 grid, 27 fenced cells",
    note=("Round 56 (NOISE.md 2026-09-13). THE QUESTION: run #321 validated the higher-timeframe "
          "squeeze as a filter and passed 6 of 6 with PBO 0.099, but froze its core to the retired "
          "#243 crown. Round 56 replayed every NOISE configuration on one continuous tape and the "
          "filter family tops it on every quality number. On the live crown the textbook hourly cell "
          "(60-minute frame, length 20, ratio 1.0) reads 615 trades, profit factor 2.351, 2024 onward "
          "2.184, sealed year 1.985, one losing year of seventeen, 1.814 without its ten best trades; "
          "25 of the 27 grid cells beat the raw crown 1.357 and all nine hourly cells sit between 1.68 "
          "and 2.35. The textbook cell is the top of that plateau, so expect the neighbourhood level, "
          "not its own number. This file is #321 re-based onto the live crown with #321 own grid "
          "unchanged, parity checked to the dollar against the harness. READ THE LOCKBOX "
          "CONTINUOUSLY: the saved strip is a cold-restart reload that drops a large share of the "
          "NOISE sealed year. THE BAR, pre-registered in the file: verdict PASS, or WEAK where only "
          "the overfit check fails; AND on a continuous replay of this job own lockbox window the "
          "chosen cell beats the raw crown on profit factor and on net per resampled 95th-percentile "
          "drawdown. Nothing moves without the owner."),
)
ref = retry(lambda: u.collection("backtests").add(job)[1])
print("queued", ref.id, "- NOISE_1_9_SQ304.py on NQ 5m RTH, 27 fenced cells, 8 folds, 12-month lockbox")
