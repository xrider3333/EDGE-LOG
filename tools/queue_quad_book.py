"""QUEUE THE FOUR-LEG FRONTIER BOOK - and the honest reason it exists.

WHAT HAPPENED. Today's even-handed tail read disqualified the NOISE R/YR frontier leg as a
STANDALONE edge: delete the top 0.5% of its own trades (30 of 5,969) and it goes from
+$173,763 to -$6,317, EV R -0.010. On that basis the frontier PAIR was repaired by swapping
it for the ORB #234 crown, which lifted the pooled MAR from 1.38 to 1.69 (job LUxH9euN).

THEN THE TRIO TEST CONTRADICTED THE REPAIR NARRATIVE, and this is the part worth reading:

    book                          net $     maxDD $   MAR   dayTop10  index corr   2018      2022
    PAIR repaired (queued)       986,430    36,360   1.69     38.3%     +0.04    42,831   115,649
    PAIR alt (NOISE crown)       892,764    34,026   1.63     40.7%     +0.16    45,475    73,969
    TRIO new (no bad leg)      1,266,068    49,894   1.58     34.3%     -0.10    78,903   183,362
    TRIO incumbent (#324)      1,066,527    36,011   1.84     35.1%     +0.10    56,567   108,658
    QUAD (all four)            1,439,831    49,894   1.80     31.3%     -0.11    89,996   218,051

The INCUMBENT trio - the one carrying the "bad" leg - has the best pooled MAR of anything
measured (1.84), better than the repaired pair. A leg can be fragile alone and still earn its
slot in a book, because what a book wants from a leg is uncorrelated P&L, not a standalone
edge. My pre-registered "no passenger legs" rule assumed those were the same thing. They are
not, and the measurement says so.

WHY THE QUAD IS QUEUED RATHER THAN THE INCUMBENT TRIO. The incumbent trio already exists as
run #324, so validating it again proves nothing. The quad is the new object: it adds the ORB
leg to that trio and, against #324, gives +35% net ($1,439,831 vs $1,066,527), lower tail
concentration (31.3% vs 35.1%), an index correlation that turns NEGATIVE (-0.11 vs +0.10 -
the book makes money in the years the index falls, by construction rather than by luck), and
much stronger down years (2018 $89,996 vs $56,567; 2022 $218,051 vs $108,658). It gives up 2%
of MAR (1.80 vs 1.84) and carries a bigger drawdown ($49,894 vs $36,011). That is a real
trade-off, stated rather than hidden: more money and far less index dependence, for a
slightly worse risk-adjusted return and a deeper hole.

NOTHING IS TUNED. All four legs run their files' own DEFAULT_PARAMS - the configurations
already crowned. One contract each, no leg weighting. Window pinned to the R2 crown's run
#335 (2010-06-07..2026-06-30), 12-month lockbox, 8 slices, so it is directly comparable to
runs #323, #324 and the repaired pair.

ORB CHECK, because the ORB family is where this project's look-ahead was found:
`tools/exec_feasibility_audit.py augur_strategies/ORB_3_6_C2.py` = PASS, 0 failures, 0
warnings, run before queueing.

    python tools/queue_quad_book.py
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


SPEC = [
    ("ENGUQ_1M_ETH_R2_1_0.py", "NQ", "1m", "eth", "db_noadj_eth"),
    ("ORB_3_6_C2.py", "NQ", "5m", "rth", "db_noadj_rth"),
    ("NOISE_1_0.py", "NQ", "5m", "rth", "db_noadj_rth"),
    ("NOISE_1_2_RYR.py", "NQ", "5m", "rth", "db_noadj_rth"),
]
legs = [{"strategy": fn, "params": defaults(fn), "instrument": inst, "timeframe": tf,
         "session": sess, "source": src, "cost_pts": 0.533, "mult": 20, "weight": 1}
        for fn, inst, tf, sess, src in SPEC]

live = _retry(lambda: [(d.to_dict() or {}) for d in u.collection("backtests")
                       .where("status", "in", ["queued", "running"]).stream()])
print("queue depth", len(live))
if len(live) > 9:
    sys.exit("ABORT queue too deep")
if any("FRONTIER QUAD" in str(j.get("strategy")) for j in live):
    sys.exit("ABORT already queued/running")

job = {
    "type": "book", "status": "queued",
    "strategy": "BOOK: FRONTIER QUAD - ENGU-Q R2 + ORB 234 + NOISE crown + NOISE R/YR",
    "book_name": "FRONTIER QUAD - ENGU-Q R2 (NQ 1m 24h) + ORB #234 + NOISE crown + NOISE "
                 "R/YR frontier (all NQ 5m day)",
    "date_from": "2010-06-07", "date_to": "2026-06-30", "lockbox_months": 12,
    "slices": 8, "equity_points": 400, "mult": 1, "legs": legs,
    "note": (
        "Four-leg version of run #324. Measured locally (tools/frontier_trio.py, one "
        "contract per leg, nothing tuned): net $1,439,831, maxDD $49,894, MAR 1.80, "
        "day-level top-10 concentration 31.3%, correlation of yearly net with the index "
        "-0.11, 2018 +$89,996, 2022 +$218,051, 17/17 positive years. Against run #324 that "
        "is +35% net, lower concentration (31.3% vs 35.1%), a NEGATIVE index correlation "
        "(vs +0.10) and much stronger down years, for 2% less MAR (1.80 vs 1.84) and a "
        "deeper drawdown ($49,894 vs $36,011). CONTEXT WORTH KEEPING: today's proportional "
        "tail read disqualified the NOISE R/YR leg as a STANDALONE edge (delete the top "
        "0.5% of its own trades, 30 of 5,969, and it goes +$173,763 -> -$6,317, EV R "
        "-0.010), which is why the frontier pair was repaired with ORB (job LUxH9euN). But "
        "the trio test then showed the incumbent trio CARRYING that leg has the best pooled "
        "MAR measured (1.84) - a leg can be fragile alone and still earn a book slot, "
        "because a book wants uncorrelated P&L rather than a standalone edge. The pre-"
        "registered 'no passenger legs' rule assumed those were the same thing; they are "
        "not. This job grades the new object (that trio plus ORB) rather than re-validating "
        "#324. exec_feasibility_audit on ORB_3_6_C2 = PASS before queueing."),
}
ref = _retry(lambda: u.collection("backtests").add(job))
print("queued", ref[1].id)
