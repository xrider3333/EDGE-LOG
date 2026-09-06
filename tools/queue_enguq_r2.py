"""Queue the Auto-Validate for ENGU-Q R2 (the crown with its two risk knobs corrected).

Written 2026-09-05. NOT run that day: Firestore's daily quota was exhausted. Run as-is when
quota resets:

    python tools/queue_enguq_r2.py

WHAT IS BEING VALIDATED. `augur_strategies/ENGUQ_1M_ETH_R2_1_0.py` is run #309 -- the crowned
ENGU-Q leg, live on the paper board -- with the trading logic untouched and exactly two
defaults moved: breakeven_R 3.0 -> 1.5 and stop_mult 1.3 -> 1.0. Its ranges are FENCED to the
neighbourhood that was actually measured, so this validate draws the landscape around the
crown rather than re-searching the whole space.

MEASURED (2010-06-07..2026-06-30, NQ 1m ETH db_noadj_eth, cost 0.533 x $20):

                       trades      net      PF    EV R   R/YR      DD    MAR   LB   top-10  hold
    #309 crown          1,604   $591,267  1.655   0.434   43.4  $48,900  0.75   99    58%   282d
    R2 (this file)      2,139   $582,827  1.665   0.485   64.6  $39,697  0.91  118    56%   142d
    sibling be2.0/s1.0  1,949   $613,126  1.711   0.503   61.0  $41,534  0.92  118    56%   142d

R2 gives up 1.4% of net and buys +49% R per year, +21% MAR, -19% drawdown, 19 more held-out
trades, a cleaner tail and half the longest hold. The be2.0 sibling beats the crown on every
read INCLUDING net; it is one line away (breakeven_R 2.0) if the owner prefers it.

WHY R2 IS THE DEFAULT RATHER THAN THE SIBLING. Both knobs were swept on the whole window, so
the two cells were re-scored on PRE-LOCKBOX DATA ONLY (2010-06-07..2025-06-30). R2 ranks
FIRST there on both MAR and R per year -- it is the cell a rule that never saw the held-out
year would have chosen. The sibling ranks second by a hair (MAR 0.90 vs 0.96). And every cell
that beat the crown before the lockbox also beat it inside the held-out year, so the ranking
is stable across the split, which is what distinguishes a real improvement from a fit.

Held-out year alone (entries >= 2025-06-30):
    #309 crown      99 trades  PF 1.620  EV R 0.407  R/YR 40.4  MAR 1.75
    R2             118 trades            EV R 0.429  R/YR 50.7  MAR 2.02
    sibling        118 trades  PF 1.675  EV R 0.487  R/YR 57.5  MAR 2.13

IN THE BOOK. Swapping this leg for the crown inside the frontier pair (run #317) dominates
that book: EV R 0.429 -> 0.436, R per year 202 -> 220, PF 1.526 -> 1.530, MAR 1.19 -> 1.39,
drawdown $40,129 -> $33,992, held-out trades 520 -> 539, top-10 45% -> 43%. It is the first
thing in this campaign to beat #317 on every read at once instead of trading one for another.

CAVEATS THAT TRAVEL WITH IT. Two knobs were selected by a sweep, so there is selection here
however small. The era split is 2-2, not 4-0: profit factor slips a little in 2010-14 and
2018-22 and improves in 2014-18 and 2022-26. And the held-out numbers above come from a sweep
that could see that window -- the pre-lockbox re-selection above is the answer to that, and
THIS VALIDATE is the real test. Nothing moves on the paper board without the owner's call.
"""
import datetime

import firebase_admin
from firebase_admin import credentials, firestore

CRED = r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG\serviceAccount.json"
UID = "IO0K35JpLIcH9YK4C0pMNYUzZOM2"

NOTE = (
    "ENGU-Q R2 = the crowned run #309 with the trading logic untouched and exactly two defaults moved: "
    "breakeven_R 3.0 to 1.5 and stop_mult 1.3 to 1.0, with both knobs FENCED to the measured neighbourhood. "
    "#309's own search maximised net and drawdown, never MAR or R per year, and pushed breakeven_R to the top "
    "of its range so the stop almost never interfered - which is why 58 percent of its net sat in ten trades "
    "with a 282-day longest hold. "
    "MEASURED 2010-06-07..2026-06-30 NQ 1m ETH cost 0.533x20 - crown: n=1604 net 591267 PF 1.655 EVR 0.434 "
    "RYR 43.4 DD 48900 MAR 0.75 LB 99 top10 58pct hold 282d. R2: n=2139 net 582827 PF 1.665 EVR 0.485 RYR 64.6 "
    "DD 39697 MAR 0.91 LB 118 top10 56pct hold 142d. So it gives up 1.4pct of net for +49pct R per year, "
    "+21pct MAR, -19pct drawdown and half the hold. "
    "HELD-OUT YEAR - crown 99 tr EVR 0.407 RYR 40.4 MAR 1.75; R2 118 tr EVR 0.429 RYR 50.7 MAR 2.02. "
    "SELECTION CHECK: re-scored on pre-lockbox data only, R2 ranks first on both MAR and R per year, so a rule "
    "that never saw the held-out year picks it; and every cell beating the crown pre-lockbox also beat it in the "
    "held-out year, so the ranking is stable across the split. "
    "IN THE BOOK: swapped into the #317 frontier pair it dominates on every read - EVR 0.429 to 0.436, RYR 202 to "
    "220, PF 1.526 to 1.530, MAR 1.19 to 1.39, DD 40129 to 33992, LB 520 to 539, top10 45 to 43pct. "
    "CAVEATS: two knobs were swept so there is selection; era split is 2-2 not 4-0 (PF slips in 2010-14 and "
    "2018-22, improves in 2014-18 and 2022-26); the sibling breakeven_R 2.0 beats the crown on every read "
    "including net and is one line away. This validate is the real test; nothing moves on paper without the owner."
)

JOB = {
    "type": "validate", "strategy": "ENGUQ_1M_ETH_R2_1_0.py", "discover": "auto",
    "n_trials": 300, "n_rounds": 5, "dsr": True, "workers": 4, "provider": "claude-cli",
    "min_trades": 30, "wf_folds": 0, "lockbox_months": 12, "equity_points": 400,
    "instrument": "NQ", "timeframe": "1m", "session": "eth", "source": "db_noadj_eth",
    "mult": 20, "cost_pts": 0.533, "slippage_pts": 0.0, "commission_usd": 0.0,
    "date_from": "2010-06-07", "date_to": "2026-06-30",
    "preset": "ENGU-Q R2 - crown plus the two risk knobs (fenced) full discovery",
    "note": NOTE, "status": "queued", "progress": 0,
}


def main():
    if not firebase_admin._apps:
        firebase_admin.initialize_app(credentials.Certificate(CRED))
    col = firestore.client().collection("users").document(UID).collection("backtests")
    job = dict(JOB, createdAt=datetime.datetime.now(datetime.timezone.utc))
    print("queued", col.add(job)[1].id)


if __name__ == "__main__":
    main()
