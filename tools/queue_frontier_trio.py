"""Queue the FRONTIER TRIO book — written 2026-09-05, could not be queued that day because
Firestore's daily quota was exhausted. Run it as-is when quota resets:

    python tools/queue_frontier_trio.py

WHAT IT IS. Run #317 ("FRONTIER PAIR v2") pools the NOISE frequency leg with the crowned
ENGU-Q #309 edge leg and is the best book in the library: EV R 0.429, R per year 202,
PF 1.526, drawdown $40,129, MAR 1.19, 520 held-out trades. This adds a THIRD leg: a second
NOISE configuration found by an EV R-objective search of NOISE_1_0 (250 configs, only two
cleared the gates). It diversifies rather than duplicates because it trades the AFTERNOON
block long-only while the incumbent NOISE leg trades the MORNING.

MEASURED (2010-06-07..2026-06-30, one contract per leg, no leg selection; the anchor
reproduces #317 to the dollar, drawdown $40,129, which is the check that the pooling is right):

  full window   pair : n= 7,573  PF 1.526  EV R 0.429  R/YR 202.1  DD $40,129  MAR 1.19  top-10 44.6%
  full window   TRIO : n=12,243  PF 1.478  EV R 0.396  R/YR 301.8  DD $44,381  MAR 1.31  top-10 36.5%
  held-out year pair :    520 tr PF 1.472  EV R 0.382  R/YR 198.8  MAR 2.31
  held-out year TRIO :    771 tr PF 1.438  EV R 0.357  R/YR 275.5  MAR 2.76

HOW TO READ IT, including what it does NOT do. The trio wins R per year (+49% full window,
+39% held-out), risk-adjusted return, held-out sample size and tail concentration, and it
does that with barely more drawdown. It LOSES about 8% of EV R (0.429 -> 0.396). The owner
asked for something that beats everything on EV R AND R per year; this beats the pair on one
of those two, not both, and that is the honest description.

Nothing in the library beats it on both, and that was measured rather than assumed: every
family was scored on the EV R axis (ENGU-Q 24h 0.434, ENGU-Q day session 0.295, NOISE 0.270,
NQDIP 0.223, ORB 0.193, ENGU-Q on ES 0.184, TTIBS 0.175), pooled EV R cannot exceed the best
leg, and the ENGU-Q family cannot make a better leg without turning into buy-and-hold (a
trail-width sweep lifts EV R to 1.10 but drives the top-10 share past 116% with holds of
1,473 days). STUDIES rows 1258-1261 carry the full argument.

TWO CAVEATS THAT TRAVEL WITH THIS BOOK:
  * Two of the three legs were selected by searches on this same window, so the book inherits
    that selection. The held-out figures above are the part that is not selected.
  * EV R and R per year can BOTH be inflated by simply sizing one leg up - 0.429 to 0.518 and
    202 to 244 at 10x, without a single extra trade. This book is strictly 1:1:1, and
    annualised MAR is the read that catches leverage (it falls under weighting, and it RISES
    here, which is the evidence the gain is real diversification).
"""
import argparse
import copy
import datetime
import os
import sys

import firebase_admin
from firebase_admin import credentials, firestore

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from queue_guard import guard, split_from_lockbox         # noqa: E402  (--guard, opt-in)

CRED = r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG\serviceAccount.json"
UID = "IO0K35JpLIcH9YK4C0pMNYUzZOM2"
ANCHOR_JOB = "RUCseZED4N2cHaJavajx"          # the #317 pair, copied for its exact schema

NOISE_AFTERNOON = dict(lookback=9, band_mult_long=0.5, band_mult_short=2.0,
                       exit_mode="boundary", side="Long Only", window="afternoon_block",
                       flat_eod=True, skip_holidays=False, stop_mode="off", confirm_bars=2,
                       daytype_mode="off", daytype_lo=0.1, daytype_hi=0.7,
                       vol_skip_pct=78.0, stop_k=2.75)

NOTE = (
    "Third leg added to the #317 frontier pair: a second NOISE configuration from an EV R-objective "
    "search of NOISE_1_0 (250 configs, 2 cleared the gates). It trades the AFTERNOON block long-only "
    "while the incumbent NOISE leg trades the MORNING, which is why they diversify instead of duplicate. "
    "Measured 2010-06-07..2026-06-30, one contract per leg, no leg selection; the anchor reproduces #317 "
    "to the dollar (DD 40129). FULL WINDOW pair: n=7573 PF 1.526 EVR 0.429 RYR 202.1 DD 40129 MAR 1.19 "
    "top10 44.6pct. FULL WINDOW trio: n=12243 net 933801 PF 1.478 EVR 0.396 RYR 301.8 DD 44381 MAR 1.31 "
    "top10 36.5pct. HELD-OUT pair: 520 tr PF 1.472 EVR 0.382 RYR 198.8 MAR 2.31. HELD-OUT trio: 771 tr "
    "PF 1.438 EVR 0.357 RYR 275.5 MAR 2.76. "
    "HONEST READ: it wins R per year, MAR, held-out sample and tail concentration, and LOSES about 8pct "
    "of EV R - so it beats the pair on one of the owner's two named reads, not both. Two of three legs "
    "were search-selected on this window, so the held-out figures are the unselected part. EV R and R per "
    "year can both be inflated by sizing one leg up (0.429 to 0.518 at 10x with zero new trades); this "
    "book is strictly 1:1:1 and MAR is the guard against that. STUDIES rows 1258-1261 carry the ceiling "
    "argument. Drivers: tools/noise_evr_search.py plus the orchestrator frontier_* scratchpad benches."
)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--guard", action="store_true",
                    help="run tools/queue_guard.py on every leg first; refuse to queue if any "
                         "leg comes back ARTIFACT (default off, behaviour otherwise unchanged)")
    args = ap.parse_args()
    if not firebase_admin._apps:
        firebase_admin.initialize_app(credentials.Certificate(CRED))
    col = firestore.client().collection("users").document(UID).collection("backtests")
    j = copy.deepcopy(col.document(ANCHOR_JOB).get().to_dict())
    if not j:
        raise SystemExit("anchor job %s not found" % ANCHOR_JOB)
    noise_leg, eng_leg = j["legs"][0], j["legs"][1]
    assert noise_leg["strategy"].startswith("NOISE"), noise_leg["strategy"]
    assert eng_leg["strategy"].startswith("ENGUQ"), eng_leg["strategy"]

    afternoon = copy.deepcopy(noise_leg)
    afternoon["strategy"] = "NOISE_1_0.py"
    afternoon["params"] = NOISE_AFTERNOON

    name = "BOOK: FRONTIER TRIO (two session-split NOISE legs + #309)"
    j["legs"] = [noise_leg, afternoon, eng_leg]
    j.update(preset=name, strategy=name, status="queued", progress=0,
             book_name="3-LEG - NOISE morning (RYR) + NOISE afternoon (EV R) + ENGU-Q #309, 1:1:1",
             createdAt=datetime.datetime.now(datetime.timezone.utc), note=NOTE)

    if args.guard:
        # --guard (2026-09-07, opt-in, default OFF): tools/queue_guard.py's continuous-lockbox
        # check on every leg -- catches the #310 empty-continuous-lockbox shape and the
        # ex-top-10-net-goes-negative shape two BOOK legs showed on 2026-09-05. SUSPECT
        # (concentration, reload/continuous divergence) is printed but does not block --
        # concentration alone must never fail a leg (ENGUQ.md section 1.0).
        split = split_from_lockbox(j["date_to"], j.get("lockbox_months", 12))
        for leg in j["legs"]:
            res = guard(leg["strategy"], leg.get("params") or {}, instrument=leg["instrument"],
                       timeframe=leg["timeframe"], session=leg["session"], source=leg["source"],
                       cost_pts=leg["cost_pts"], mult=leg["mult"], date_from=j["date_from"],
                       date_to=j["date_to"], split=split, label=f"{name} :: {leg['strategy']}")
            if res["verdict"] == "ARTIFACT":
                sys.exit(f"ABORT -- leg {leg['strategy']} is ARTIFACT, refusing to queue "
                         f"(see the guard printout above)")

    print("queued", col.add(j)[1].id)


if __name__ == "__main__":
    main()
