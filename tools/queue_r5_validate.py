"""Queue the full-discovery Auto-Validate for ENGU-Q R4 (the crown with a deeper limit).

The file: augur_strategies/ENGUQ_1M_ETH_R5_1_0.py, shipped as a24ed5e. It is the live crown
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


FN = "ENGUQ_1M_ETH_R5_1_0.py"
live = _retry(lambda: [(d.to_dict() or {}) for d in u.collection("backtests")
                       .where("status", "in", ["queued", "running"]).stream()])
print("queue depth", len(live))
if len(live) > 9:
    sys.exit("ABORT queue too deep")
if any(FN in str(j.get("strategy")) for j in live):
    sys.exit("ABORT already queued/running")

job = {
    "type": "validate", "status": "queued", "strategy": FN, "discover": "auto",
    "preset": "ENGU-Q R5 - deeper limit + hold cap stacked (fenced) full discovery",
    "instrument": "NQ", "timeframe": "1m", "session": "eth", "source": "db_noadj_eth",
    "date_from": "2010-06-07", "date_to": "2026-06-30", "lockbox_months": 12,
    "cost_pts": 0.533, "slippage_pts": 0.0, "commission_usd": 0.0, "mult": 20,
    "n_trials": 300, "n_rounds": 5, "wf_folds": 0, "min_trades": 30, "workers": 4,
    "equity_points": 400, "dsr": True,
    "note": ("Stacks the two independent improvements measured today: the resting entry limit 0.55 -> "
        "0.85 ATR (money side) and the hold cap 8,280 -> 9,660 bars (tail side). They act on "
        "different parts of the trade - where the entry rests, when the position is forced "
        "out - and across a 4x4 grid they stack: only two of sixteen cells cleared the "
        "pre-registered bar and they are neighbours (limit 0.85 and 1.00, both at cap 9,660), "
        "which is a plateau not a spike. FULL WINDOW: 2,585 trades, $566,907, PF 1.538, MAR "
        "1.16, top-10 43.0%, index correlation +0.27, 2018 +$13,022, 2022 +$24,796, 151 "
        "held-out trades, longest hold 15 days - against the live crown's 1,949 / $613,126 / "
        "1.711 / 0.92 / 55.6% / +0.51 / +$12,392 / +$7,340 / 118 / 142 days. THE POINT: this "
        "is the FIRST ENGU-Q configuration to PASS the enforced tail bar - queue_guard "
        "--tail-enforce returns VERDICT PASS and TAIL/BETA BAR PASS (top-10 45%, correlation "
        "+0.273, both index down years positive at +$37,817 combined, 17/17 positive years). "
        "The crown fails that bar on correlation alone. HELD-OUT YEAR, which nobody tuned on, "
        "beats the crown: 151 trades / PF 1.648 / +$99,997 / R per year 66.8 against 118 / "
        "1.675 / $88,380 / 57.5; reload 152 vs continuous 151, so no lockbox artifact. COST: "
        "7.5% of net and PF 1.711 -> 1.538 - the price of not depending on the index rising. "
        "CAVEATS: both values were chosen after seeing their grids on the same window they "
        "are scored on (mitigated by two independent discoveries, two plateaus, and a "
        "neighbour cell that also clears); re-optimising has historically not paid on this "
        "project; and the cap does NOT travel to ES, so nothing here should be carried to an "
        "ES leg. Parity exact: limit 0.55 + cap 0 reproduces the crown (1,949 / $613,126) and "
        "limit 0.55 + cap 8,280 reproduces the R3 parent (2,647 / $565,913). "
        "exec_feasibility_audit PASS."),
}
ref = _retry(lambda: u.collection("backtests").add(job))
print("queued", ref[1].id)
