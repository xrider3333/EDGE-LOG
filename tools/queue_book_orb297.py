"""Queue the four-leg BOOK with the opening-range leg swapped to run #297's configuration.

WHY THIS ONE (round 53, tools/r53_book_orb_leg.py, results ORB_ROUND53_BOOK_LEG.txt).
Rounds 48-52 tuned every leg of the book EXCEPT the opening-range leg, which has sat at run #234's
configuration since the book was built. Round 53 put 216 opening-range configurations through the
adopted four-leg book, one at a time, and scored the book on return-over-drawdown with the sealed
year reported separately.

  * The book NEEDS the leg: removing it drops the selection stretch from 38.18 to 32.51 and the
    sealed year from 10.33 to 9.28. Doubling its weight is worse on both. Weight 1 is right.
  * Ranking the leg by the selection stretch is WORSE THAN USELESS: selection-stretch and
    sealed-year performance are NEGATIVELY correlated across the 216 (Pearson -0.31). The top
    tenth by selection stretch averages 4.63 in the sealed year against 7.84 for the field. The
    three-bar opening range is the trap - best selection stretch of any group, worst sealed year.
  * On the sealed year, the stretch nothing was chosen on, run #297's configuration ranks FIRST of
    214. The incumbent ranks 14th. #297 also beats the incumbent on the selection stretch, which
    matters precisely because the two are otherwise negatively related.
  * It is a plateau, not a spike: the top six sealed-year rows are all its immediate neighbours,
    every one of them the same two filter settings with a two-bar range and a 2.0 stop, differing
    only in target and breakeven, which barely move the result.
  * It is ALREADY VALIDATED as run #297 in its own right (7 of 8 walk-forward folds, lockbox
    $98,179 at profit factor 1.536), so this queues the BOOK evidence, not a new strategy.

WHAT IT ACTUALLY CHANGES: nothing but the two filter thresholds on the opening-range leg. It keeps
run #234's geometry exactly - 2.0 stop, 5.5 target, breakeven at 1R, two-bar range - and moves the
vol-regime filter from 0.70 to 0.75 and the volume-pace gate from 0.70 to 0.80. Those are the
crown's filter settings on the incumbent's geometry.

NOT THE SAME AS THE CROWN SWAP another session queued: putting run #314 itself in this slot scores
42.18 on the selection stretch but 10.04 in the sealed year, BELOW the incumbent's 10.33.

Usage:
  python tools/queue_book_orb297.py            # print the job, send nothing
  python tools/queue_book_orb297.py --send     # queue it (queue-depth guarded, idempotent)
"""
import datetime
import importlib.util as ilu
import json
import os
import sys
import time

os.chdir(r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG")
import firebase_admin
from firebase_admin import credentials, firestore
from google.api_core import exceptions as _gx

if not firebase_admin._apps:
    firebase_admin.initialize_app(credentials.Certificate("serviceAccount.json"))
u = firestore.client().collection("users").document("IO0K35JpLIcH9YK4C0pMNYUzZOM2")


def _retry(fn, tries=4, wait=180):
    for i in range(tries):
        try:
            return fn()
        except (_gx.ResourceExhausted, _gx.ServiceUnavailable, _gx.DeadlineExceeded) as e:
            print("attempt %d blocked (%s); waiting %ds" % (i + 1, type(e).__name__, wait), flush=True)
            if i == tries - 1:
                raise
            time.sleep(wait)


def defaults(fn):
    p = os.path.join("augur_strategies", fn)
    sp = ilu.spec_from_file_location("m", p)
    m = ilu.module_from_spec(sp)
    sp.loader.exec_module(m)
    return {k: v["default"] for k, v in m.DEFAULT_PARAMS.items()}


ORB297 = dict(defaults("ORB_3_6.py"))
ORB297.update(or_bars=2, trade_mode="First-candle dir", close_confirm=True, partial_exit_R=0.0,
              trail_bars=0, flat_eod=True, skip_holidays=True, breakout_buf=0.25, stop_frac=2.0,
              target_R=5.5, be_after_R=1.0, atr_filter=0.75, vpace_filter=0.8)
NOISE_CROWN = {"daytype_lo": 0.2, "window": "all_day", "confirm_bars": 1, "daytype_mode": "skip_bot_short",
               "band_mult_long": 0.75, "vol_skip_pct": 95.0, "band_mult_short": 1.5, "skip_holidays": False,
               "stop_mode": "bandwidth", "flat_eod": True, "lookback": 40, "side": "Both",
               "daytype_hi": 0.8, "stop_k": 1.75, "exit_mode": "vwap"}

legs = [
    {"strategy": "ORB_3_6.py", "params": ORB297, "instrument": "NQ", "timeframe": "5m",
     "session": "rth", "source": "db_noadj_rth", "cost_pts": 0.533, "mult": 20, "weight": 1},
    {"strategy": "ENGUQ_1M_ETH_R2_1_0.py", "params": defaults("ENGUQ_1M_ETH_R2_1_0.py"), "instrument": "NQ",
     "timeframe": "1m", "session": "eth", "source": "db_noadj_eth", "cost_pts": 0.783, "mult": 20, "weight": 1},
    {"strategy": "TTMSQZ_3_0_ES30SS20.py", "params": defaults("TTMSQZ_3_0_ES30SS20.py"), "instrument": "ES",
     "timeframe": "30m", "session": "rth", "source": "db_noadj_rth", "cost_pts": 0.363, "mult": 50, "weight": 3},
    {"strategy": "NOISE_1_1_NBHD.py", "params": NOISE_CROWN, "instrument": "NQ", "timeframe": "5m",
     "session": "rth", "source": "db_noadj_rth", "cost_pts": 0.533, "mult": 20, "weight": 1},
]

NAME = "BOOK ORB LEG 297: ORB 297 filters + ENGU-Q 335 + TTM SS x3 + NOISE 304"
job = {
    "type": "book", "status": "queued", "strategy": NAME,
    "book_name": "ORB-LEG BOOK - opening range #297 + ENGU-Q #335 + TTM SS x3 + NOISE #304",
    "date_from": "2010-06-07", "date_to": "2026-06-30", "lockbox_months": 12,
    "slices": 8, "equity_points": 400, "mult": 1, "legs": legs,
    "note": ("Round 53 (tools/r53_book_orb_leg.py). The opening-range leg is the one leg the book has "
             "never varied. 216 configurations were run through the adopted four-leg book. Three things "
             "came out. The book needs the leg (without it the selection stretch falls 38.18 to 32.51 and "
             "the sealed year 10.33 to 9.28) and wants it at weight 1 (weight 2 is worse on both). Ranking "
             "the leg on the selection stretch is worse than useless - selection and sealed-year scores are "
             "NEGATIVELY correlated at -0.31, and the three-bar opening range is the trap, with the best "
             "selection stretch of any group and by far the worst sealed year. And on the sealed year, the "
             "only stretch nothing was chosen on, run #297's configuration ranks FIRST of 214 at 11.54 "
             "against the incumbent's 10.33 (14th), while also beating it on the selection stretch. It is a "
             "plateau: the top six sealed-year rows are its own neighbours, all sharing the two-bar range, "
             "the 2.0 stop and these two filter settings, differing only in target and breakeven. The change "
             "versus the incumbent is ONLY the two filter thresholds - vol-regime 0.70 to 0.75, volume-pace "
             "0.70 to 0.80 - on run #234's geometry, and that configuration is already validated on its own "
             "as run #297 (7 of 8 walk-forward folds, lockbox $98,179 at PF 1.536). NOTE this is NOT the "
             "crown swap another session queued: run #314 itself in this slot scores 42.18 on the selection "
             "stretch but 10.04 in the sealed year, BELOW the incumbent."),
}

if "--send" not in sys.argv:
    print(json.dumps({k: (v if k != "legs" else "[%d legs]" % len(v)) for k, v in job.items()},
                     indent=1, default=str))
    print("\nlegs:")
    for l in legs:
        print("  %-28s w%-2d %s %s %s" % (l["strategy"], l["weight"], l["instrument"], l["timeframe"], l["session"]))
    print("\ndry run - pass --send to queue")
    sys.exit(0)

live = _retry(lambda: [(d.to_dict() or {}) for d in u.collection("backtests")
                       .where("status", "in", ["queued", "running"]).stream()])
print("queue depth", len(live))
if len(live) > 9:
    sys.exit("ABORT queue too deep")
if any("ORB LEG 297" in str(j.get("strategy", "")) for j in live):
    sys.exit("ABORT this book is already queued or running")
job["createdAt"] = datetime.datetime.now(datetime.timezone.utc)
ref = u.collection("backtests").document()
_retry(lambda: ref.set(job))
print("queued", ref.id, NAME)
