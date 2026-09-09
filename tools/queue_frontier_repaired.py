"""QUEUE THE REPAIRED FRONTIER PAIR: ENGU-Q R2 crown + ORB #234 crown, one contract each.

WHY THIS REPLACES THE EXISTING PAIR (run #323). That book pairs the ENGU-Q R2 crown with
NOISE_1_2_RYR, and today's even-handed tail read killed that second leg: delete the top 0.5%
of its OWN trades (30 of 5,969) and it goes from +$173,763 to **-$6,317**, EV R -0.010. It
passed the house fixed-ten concentration check only because it trades three times as often as
the legs it was compared with, so ten trades is 0.18% of its sample against 0.55% of the
crown's (tools/tail_adjusted_board.py, tools/frontier_repair.py).

THE AUDITION, pre-registered before running (tools/frontier_repair.py): every candidate pooled
1:1 with the SAME ENGU-Q leg, day by day, incumbent scored alongside rather than from memory.
A candidate replaces the incumbent only on beating its pooled MAR, keeping a proportional-tail
EV R above 0.05, staying under 0.50 daily correlation with the ENGU-Q leg, and leaving both
index down years positive.

    pair                              net $     maxDD $   MAR   day-top10  index corr  leg corr
    incumbent (NOISE R/YR frontier)   786,889    35,399   1.38     43.3%      +0.34      -0.00
    + NOISE crown                     892,764    34,026   1.63     40.7%      +0.16      +0.03
    + ORB #234 crown                  986,430    36,360   1.69     38.3%      +0.04      +0.01   <- queued
    ENGU-Q R2 alone                   613,126    39,200   0.97       n/a      +0.48        n/a

Both replacements cleared; ORB is queued because it wins on every read. Pooled MAR 1.69 against
the incumbent pair's 1.38 (+22%) and the ENGU-Q leg alone at 0.97; index correlation falls to
+0.04, which is the owner's whole complaint answered at book level; 2018 +$42,831 and 2022
+$115,649 - the pair MAKES money in both index down years. Leg-to-leg daily correlation +0.01,
so this is genuine diversification and not leverage. The ORB leg's own proportional-tail EV R
is 0.077 (survives; $181,388 left of $373,305 after deleting 13 trades).

ORB-SPECIFIC CHECK, because the ORB family is where this project's look-ahead was found: the
audit voided ORB 3.0/3.1, not this file (the #234 crown), and
`python tools/exec_feasibility_audit.py augur_strategies/ORB_3_6_C2.py` returns PASS with 0
hard failures and 0 warnings. Run before queueing, not after.

NOT TUNED: both legs run their files' own DEFAULT_PARAMS - the configurations already crowned
and on the paper board. Window pinned to the R2 crown's run #335 (2010-06-07..2026-06-30),
12-month lockbox, 8 slices, so it is directly comparable to runs #323 and #324.

    python tools/queue_frontier_repaired.py
"""
import os
import sys
import time

os.chdir(r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG")
import importlib.util as ilu                                       # noqa: E402
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


def defaults(fn):
    sp = ilu.spec_from_file_location("m", os.path.join("augur_strategies", fn))
    m = ilu.module_from_spec(sp)
    sp.loader.exec_module(m)
    return {k: v["default"] for k, v in m.DEFAULT_PARAMS.items()}


ENGUQ = "ENGUQ_1M_ETH_R2_1_0.py"
ORB = "ORB_3_6_C2.py"
legs = [
    {"strategy": ENGUQ, "params": defaults(ENGUQ), "instrument": "NQ", "timeframe": "1m",
     "session": "eth", "source": "db_noadj_eth", "cost_pts": 0.533, "mult": 20, "weight": 1},
    {"strategy": ORB, "params": defaults(ORB), "instrument": "NQ", "timeframe": "5m",
     "session": "rth", "source": "db_noadj_rth", "cost_pts": 0.533, "mult": 20, "weight": 1},
]

live = _retry(lambda: [(d.to_dict() or {}) for d in u.collection("backtests")
                       .where("status", "in", ["queued", "running"]).stream()])
print("queue depth", len(live))
if len(live) > 9:
    sys.exit("ABORT queue too deep")
if any("FRONTIER PAIR REPAIRED" in str(j.get("strategy")) for j in live):
    sys.exit("ABORT already queued/running")

job = {
    "type": "book", "status": "queued",
    "strategy": "BOOK: FRONTIER PAIR REPAIRED - ENGU-Q R2 + ORB 234",
    "book_name": "FRONTIER PAIR REPAIRED - ENGU-Q R2 crown (NQ 1m 24h) + ORB #234 crown "
                 "(NQ 5m day)",
    "date_from": "2010-06-07", "date_to": "2026-06-30", "lockbox_months": 12,
    "slices": 8, "equity_points": 400, "mult": 1, "legs": legs,
    "note": (
        "Replaces the NOISE R/YR frontier leg in run #323, which today's even-handed tail "
        "read disqualified: delete the top 0.5% of its own trades (30 of 5,969) and that leg "
        "goes from +$173,763 to -$6,317 (EV R -0.010). It had passed the fixed-ten "
        "concentration check only because it trades three times as often as the legs it was "
        "compared with. Audition pre-registered in tools/frontier_repair.py; every candidate "
        "pooled 1:1 with the same ENGU-Q leg, incumbent included. THIS PAIR, measured "
        "locally: net $986,430, maxDD $36,360, MAR 1.69 (incumbent pair 1.38, ENGU-Q leg "
        "alone 0.97), day-level top-10 concentration 38.3%, correlation of yearly net with "
        "the index +0.04 (incumbent +0.34), 2018 +$42,831 and 2022 +$115,649 - positive in "
        "BOTH index down years - and leg-to-leg daily correlation +0.01, so it is "
        "diversification rather than leverage. The ORB leg's own proportional-tail EV R is "
        "0.077 ($181,388 left of $373,305 after 13 trades deleted). Both legs run their "
        "files' DEFAULT_PARAMS, nothing tuned. exec_feasibility_audit on ORB_3_6_C2 = PASS "
        "(0 failures, 0 warnings), run BEFORE queueing because the ORB family is where this "
        "project's look-ahead was found. Window pinned to run #335 so this is comparable to "
        "#323 and #324."),
}
ref = _retry(lambda: u.collection("backtests").add(job))
print("queued", ref[1].id)
