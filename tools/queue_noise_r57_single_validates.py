"""Queue SINGLE-config validates (Gate-validate) on the EXACT five NOISE configurations of round 57.

Owner, 2026-09-14: "run single validates on the exact configs too." The five round-57 Auto-Validates
(#386-#388 so far) each crown the richest cell of their neighbourhood, and none crowned the configuration it was
built around. An Auto-Validate cannot be forced onto one cell without pinning the file, which removes the overfit
and neighbourhood tests. The house's documented route for persisting ONE researched configuration is GATE VALIDATE:
one continuous backtest of fixed parameters over the whole window, the pre-lockbox / lockbox split sliced from that
same continuous run (so NOT the cold-restart reload that distorts NOISE Auto-Validate lockboxes), plus the ML-gate
bake-off ranked on pre-lockbox only. It saves as its own run on EL ("Gate-Validate"). It has no parameter search,
so no overfit probability or plateau test -- those live on the neighbourhood Auto-Validates.

Each job runs the round-57 fenced file at its centre cell, the cell parity-checked to the dollar against the
round-56 scorecard. Windows and costs match the Auto-Validates.
"""
import sys
import time

import firebase_admin
from firebase_admin import credentials, firestore

firebase_admin.initialize_app(credentials.Certificate("serviceAccount.json"))
u = firestore.client().collection("users").document("IO0K35JpLIcH9YK4C0pMNYUzZOM2")

NB = dict(lookback=40, band_mult_long=0.75, band_mult_short=1.5, stop_k=1.75, vol_skip_pct=95.0)
JOBS = [
    ("NOISE_1_9_HSQ304.py", "5m", "2026-07-16", dict(gate_tf_min=60, gate_len=20, gate_ratio=1.0),
     "live crown, only trades during an hourly squeeze (textbook 60-minute / 20 / 1.0)"),
    ("NOISE_1_9_HSQ243.py", "5m", "2026-07-16", dict(gate_tf_min=60, gate_len=20, gate_ratio=1.0),
     "retired 243, only trades during an hourly squeeze (textbook 60-minute / 20 / 1.0)"),
    ("NOISE_1_1_N304.py", "15m", "2026-06-30", dict(NB), "the live crown settings on 15-minute bars"),
    ("NOISE_1_1_N304C2.py", "5m", "2026-07-16", dict(NB), "the live crown settings waiting for 2 closes"),
    ("NOISE_1_4_C3N.py", "5m", "2026-07-16",
     dict(lookback=74, band_mult_long=1.0, band_mult_short=1.75, stop_k=0.75, vol_skip_pct=93.0, confirm_bars=3),
     "the cost-robust corner C3"),
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
print("queue depth", len(live), [str(j.get("strategy"))[:22] + ":" + str(j.get("type")) for j in live])
if len(live) + len(JOBS) > 14:
    sys.exit("ABORT queue too deep")
if any(j.get("type") == "gate_validate" and j.get("strategy") in {x[0] for x in JOBS} for j in live):
    sys.exit("ABORT a single validate for one of these files is already live")

for fn, tf, date_to, params, what in JOBS:
    job = dict(
        type="gate_validate", status="queued", strategy=fn, params=params,
        instrument="NQ", timeframe=tf, session="rth", source="db_noadj_rth",
        cost_pts=0.533, mult=20, commission_usd=0.0, slippage_pts=0.0, min_trades=30,
        date_from="2010-06-07", date_to=date_to, lockbox_months=12,
        gates=["logistic", "rf", "xgb"], thresholds=[0.50, 0.55, 0.60], progress=0,
        preset="NOISE round 57 - SINGLE validate of the exact config: " + what,
        note=("Round 57 (NOISE.md 2026-09-14). Owner: run single validates on the exact configs. This is " + what +
              ", run as ONE fixed configuration (the fenced file centre cell, parity-checked to the dollar against "
              "the round-56 scorecard). Its lockbox is sliced from one continuous run, so unlike the NOISE "
              "Auto-Validate strip it is not a cold-restart number. No parameter search, so no overfit or "
              "plateau test - those are on the neighbourhood Auto-Validate of the same file. Nothing moves "
              "without the owner."),
    )
    ref = retry(lambda: u.collection("backtests").add(job)[1])
    print("queued", ref.id, "gate_validate", fn, tf, "to", date_to, params)
