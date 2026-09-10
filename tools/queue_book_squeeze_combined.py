"""Queue the book with the CROWNED squeeze leg in place of the structural-stop-only one (round 54, 2026-09-10).

The staleness audit has now caught three legs. The adopted book carries the squeeze file that validated
as run #353 (structural stop only). The crowned squeeze leg is run #369 - the combined leg - and on its
own validate it makes 38 percent more money on 23 percent LESS drawdown from the same 273 trades. That
leg carries triple weight in the book, so it is the biggest of the three staleness findings, and unlike
the opening-range swap the newer leg is better STANDALONE, not merely better-timed.

Local read (tools/r54_book_squeeze_leg_audit.py), one window and one lockbox split throughout:
                                       selection net/DD    held-back net/DD   profit factor
  adopted book, run #366                  38.18                10.33              1.701
  opening-range crown, run #373           41.73                10.06              1.749
  squeeze crown only                      40.57                11.16              1.737
  BOTH crowns (this job, weight 3)        44.35                11.02              1.787
  BOTH crowns at squeeze weight 4         47.16                12.06              1.829

PRE-REGISTERED BAR: beat run #366 on selection-window net-over-drawdown AND keep the held-back year at
or above #366's 10.33, which the weight-3 job clears on the local read.
STATED OUT LOUD: the two squeeze files correlate 0.969 day to day, so this is the same mechanism with
better exits, not a new source of return. The weight-4 job is a KNOB TEST, not a staleness fix - the
weight ladder now turns over at 4 (2 gives 40.96, 3 gives 44.35, 4 gives 47.16, 5 gives 45.99) where the
same ladder on the OLD squeeze leg ran monotonic and was rejected for that reason; an interior optimum is
the difference, but it is still a knob picked on the selection window and it is labelled as one.
"""
import os, sys, datetime, time
os.chdir(r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG")
import importlib.util as ilu
import firebase_admin
from firebase_admin import credentials, firestore
from google.api_core import exceptions as _gx
if not firebase_admin._apps:
    firebase_admin.initialize_app(credentials.Certificate("serviceAccount.json"))
u = firestore.client().collection("users").document("IO0K35JpLIcH9YK4C0pMNYUzZOM2")


def _retry(fn, tries=4, wait=300):
    for i in range(tries):
        try:
            return fn()
        except (_gx.ResourceExhausted, _gx.ServiceUnavailable, _gx.DeadlineExceeded) as e:
            print("attempt %d blocked (%s); waiting %ds" % (i + 1, type(e).__name__, wait), flush=True)
            if i == tries - 1:
                raise
            time.sleep(wait)


def defaults(fn):
    sp = ilu.spec_from_file_location("m", os.path.join("augur_strategies", fn))
    m = ilu.module_from_spec(sp); sp.loader.exec_module(m)
    return {k: v["default"] for k, v in m.DEFAULT_PARAMS.items()}


NOISE_CROWN = {"daytype_lo": 0.2, "window": "all_day", "confirm_bars": 1, "daytype_mode": "skip_bot_short",
               "band_mult_long": 0.75, "vol_skip_pct": 95.0, "band_mult_short": 1.5, "skip_holidays": False,
               "stop_mode": "bandwidth", "flat_eod": True, "lookback": 40, "side": "Both",
               "daytype_hi": 0.8, "stop_k": 1.75, "exit_mode": "vwap"}   # run #304's own champion


def legs_for(sq_weight):
    return [
        {"strategy": "ORB_3_6_R6.py", "params": defaults("ORB_3_6_R6.py"), "instrument": "NQ",
         "timeframe": "5m", "session": "rth", "source": "db_noadj_rth", "cost_pts": 0.533, "mult": 20, "weight": 1},
        {"strategy": "ENGUQ_1M_ETH_R2_1_0.py", "params": defaults("ENGUQ_1M_ETH_R2_1_0.py"), "instrument": "NQ",
         "timeframe": "1m", "session": "eth", "source": "db_noadj_eth", "cost_pts": 0.783, "mult": 20, "weight": 1},
        {"strategy": "TTMSQZ_3_0_ES30SSOF2.py", "params": defaults("TTMSQZ_3_0_ES30SSOF2.py"), "instrument": "ES",
         "timeframe": "30m", "session": "rth", "source": "db_noadj_rth", "cost_pts": 0.363, "mult": 50,
         "weight": sq_weight},
        {"strategy": "NOISE_1_1_NBHD.py", "params": NOISE_CROWN, "instrument": "NQ",
         "timeframe": "5m", "session": "rth", "source": "db_noadj_rth", "cost_pts": 0.533, "mult": 20, "weight": 1},
    ]


live = _retry(lambda: [(d.to_dict() or {}) for d in u.collection("backtests")
                       .where("status", "in", ["queued", "running"]).stream()])
print("queue depth", len(live))
if len(live) > 9:
    sys.exit("ABORT queue too deep")
if any("SQUEEZE CROWN" in str(j.get("strategy", "")) for j in live):
    sys.exit("ABORT squeeze-crown book already queued/running")

NOTE_HEAD = (
    "Round 54 (tools/r54_book_squeeze_leg_audit.py). Third instance of the same defect rounds 51 and 53 "
    "found: when a strategy earns a new crown the paper account is swapped and the book is not. The book "
    "carries the structural-stop-only squeeze file, validated as run #353 at 55,912 dollars on 4,338 of "
    "drawdown; the CROWNED squeeze leg is run #369 - the combined leg, structural stop plus deep tilt plus "
    "open-bar tilt plus the one-bar fade exit - which makes 77,105 dollars on 3,350 of drawdown from the "
    "same 273 trades. Unlike the opening-range swap in run #373, this newer leg is better STANDALONE, not "
    "merely better-timed, and it carries triple weight so the effect is multiplied. This job also keeps the "
    "opening-range crown that run #373 validated. LOCAL READ, one window and one lockbox split throughout: "
    "adopted book #366 scores 38.18 selection net-over-drawdown and 10.33 in the held-back year; run #373 "
    "scores 41.73 and 10.06; the squeeze crown alone scores 40.57 and 11.16; BOTH crowns score 44.35 and "
    "11.02 at squeeze weight 3, and 47.16 and 12.06 at weight 4. "
)
NOTE_TAIL = (
    "SAID OUT LOUD: the two squeeze files correlate 0.969 day to day, so this is the same mechanism with "
    "better exits rather than a new source of return, and every version of this book still has a held-back "
    "year whose ten best days are roughly the whole of its profit."
)
JOBS = [
    (3, "BOOK SQUEEZE CROWN x3: ORB 314 + ENGU-Q 335 + TTM COMBINED x3 + NOISE 304",
     "PRE-REGISTERED BAR: beat run #366 on selection-window net-over-drawdown AND hold the held-back year "
     "at or above #366's 10.33. This job changes only WHICH FILE fills the squeeze slot - no knob is tuned. "),
    (4, "BOOK SQUEEZE CROWN x4 KNOB TEST: ORB 314 + ENGU-Q 335 + TTM COMBINED x4 + NOISE 304",
     "THIS ONE IS A KNOB TEST, NOT A STALENESS FIX, and is labelled so on purpose. The squeeze weight "
     "ladder now turns over - 2 gives 40.96, 3 gives 44.35, 4 gives 47.16, 5 gives 45.99 - where the same "
     "ladder on the OLD squeeze leg ran monotonic and was rejected for having no interior optimum. An "
     "interior optimum is the difference, but the weight is still picked on the selection window, so this "
     "is scored as a candidate and not adopted on its own showing. "),
]
for w, name, mid in JOBS:
    job = {
        "type": "book", "status": "queued", "strategy": name,
        "book_name": name,
        "date_from": "2010-06-07", "date_to": "2026-06-30", "lockbox_months": 12,
        "slices": 8, "equity_points": 400, "mult": 1, "legs": legs_for(w),
        "note": NOTE_HEAD + mid + NOTE_TAIL,
        "createdAt": datetime.datetime.now(datetime.timezone.utc),
    }
    ref = u.collection("backtests").document(); _retry(lambda: ref.set(job))
    print("queued", ref.id, name)
