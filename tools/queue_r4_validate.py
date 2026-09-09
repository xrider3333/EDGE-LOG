"""Queue the full-discovery Auto-Validate for ENGU-Q R4 (the crown with a deeper limit).

The file: augur_strategies/ENGUQ_1M_ETH_R4_1_0.py, shipped as a24ed5e. It is the live crown
(run #335's configuration) with ONE default moved - the resting entry limit goes from 0.55 to
0.85 ATR below the signal close - and the ranges fenced to the plateau actually measured
(limit 0.55-1.00), so the search draws the landscape around the crown instead of re-searching
the whole space.

What the local measurement says, full window 2010-06-07..2026-06-30, NQ 1m 24h, 0.533 x $20:
crown 1,949 trades / $613,126 / PF 1.711 / MAR 0.92 / top-10 55.6% / index correlation +0.51 /
2022 +$7,340 / 118 held-out trades, against this file's 1,995 / $617,284 / PF 1.717 / MAR 1.08
/ 56.3% / +0.44 / 2022 +$17,489 / 118. So: +17% MAR, +0.7% net, lower index correlation, 2022
more than doubled, tail dependence and held-out sample unchanged. The plateau is real - 0.70,
0.85 and 1.00 all beat the crown on MAR while everything shallower is worse.

Three caveats carried onto the job card because they matter to how the verdict should be read:
0.85 was chosen after seeing the table on the same window it is scored on; the setting was
already inside run #335's own fence and that search picked 0.1 (it optimised a different
objective); and re-optimising has historically NOT paid on this project. This is why the file
gets a validate rather than the paper leg being moved.

    python tools/queue_r4_validate.py
"""
import os
import sys
import time

os.chdir(r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG")
import firebase_admin                                              # noqa: E402
from firebase_admin import credentials, firestore                  # noqa: E402
from google.api_core import exceptions as _gx                      # noqa: E402

if not firebase_admin._apps:
    firebase_admin.initialize_app(credentials.Certificate("serviceAccount.json"))
u = firestore.client().collection("users").document("IO0K35JpLIcH9YK4C0pMNYUzZOM2")


def _retry(fn, tries=4, wait=300):
    for i in range(tries):
        try:
            return fn()
        except (_gx.ResourceExhausted, _gx.ServiceUnavailable, _gx.DeadlineExceeded) as e:
            print("attempt %d blocked (%s); waiting %ds" % (i + 1, type(e).__name__, wait),
                  flush=True)
            if i == tries - 1:
                raise
            time.sleep(wait)


FN = "ENGUQ_1M_ETH_R4_1_0.py"
live = _retry(lambda: [(d.to_dict() or {}) for d in u.collection("backtests")
                       .where("status", "in", ["queued", "running"]).stream()])
print("queue depth", len(live))
if len(live) > 9:
    sys.exit("ABORT queue too deep")
if any(FN in str(j.get("strategy")) for j in live):
    sys.exit("ABORT already queued/running")

job = {
    "type": "validate", "status": "queued", "strategy": FN, "discover": "auto",
    "preset": "ENGU-Q R4 - crown + deeper resting limit (fenced 0.55-1.00) full discovery",
    "instrument": "NQ", "timeframe": "1m", "session": "eth", "source": "db_noadj_eth",
    "date_from": "2010-06-07", "date_to": "2026-06-30", "lockbox_months": 12,
    "cost_pts": 0.533, "slippage_pts": 0.0, "commission_usd": 0.0, "mult": 20,
    "n_trials": 300, "n_rounds": 5, "wf_folds": 0, "min_trades": 30, "workers": 4,
    "equity_points": 400, "dsr": True,
    "note": (
        "One knob off the live crown: the resting entry limit 0.55 -> 0.85 ATR below the "
        "signal close. Found by walking the five settings this campaign had never touched "
        "(entry limit depth, ATR length, efficiency window, volume filter, initial stop "
        "width); it was the only one of the five that improves the crown. Local full-window "
        "measurement: 1,995 trades / $617,284 / PF 1.717 / MAR 1.08 / top-10 56.3% / index "
        "correlation +0.44 / 2018 +$10,574 / 2022 +$17,489 / 118 held-out trades, against "
        "the crown's 1,949 / $613,126 / 1.711 / 0.92 / 55.6% / +0.51 / +$12,392 / +$7,340 / "
        "118. So +17% MAR and a much stronger 2022 with tail dependence and held-out sample "
        "unchanged (proportional-tail EV R 0.223 vs 0.224). PLATEAU, not a spike: 0.70 / "
        "0.85 / 1.00 all beat the crown on MAR (0.96 / 1.08 / 1.03) and everything shallower "
        "is worse. CAVEATS, stated: 0.85 was picked after seeing that table on the same "
        "window it is scored on; limit depth was already inside run #335's fence (0.0-1.0) "
        "and that full-discovery search chose 0.1 because it optimised its own objective, "
        "not MAR; and this project's ORB meta walk-forward found re-picked parameters earn "
        "LESS than leaving defaults alone. Hence a validate, not a paper-leg move. It does "
        "NOT fix the tail - concentration is unchanged and +0.44 still fails the enforced "
        "tail bar - so it is independent of the hold cap (R3) and, if both survive, they "
        "should be tested together. Parity verified: at limit 0.55 the file reproduces the "
        "crown exactly (1,949 trades, $613,126). exec_feasibility_audit PASS."),
}
ref = _retry(lambda: u.collection("backtests").add(job))
print("queued", ref[1].id)
