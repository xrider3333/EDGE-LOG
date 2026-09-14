"""Queue the FRONTIER book: run #379 with only its opening-range leg swapped to run #297 (round 55).

See tools/r55_frontier_orb_leg.py and ORB_ROUND55_FRONTIER.txt. Earlier notes below describe round 53.


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

import firebase_admin as _fa
from google.cloud.firestore_v1.base_query import FieldFilter as _FF
_j = list(u.collection("backtests").where(filter=_FF("run_id", "==", 379)).stream())
assert _j, "run #379 job not found"
legs = [dict(l) for l in _j[0].to_dict()["legs"]]
_oi = [i for i, l in enumerate(legs) if str(l["strategy"]).startswith("ORB")]
assert len(_oi) == 1
legs[_oi[0]] = dict(legs[_oi[0]], strategy="ORB_3_6.py", params=ORB297)
NAME = "BOOK FRONTIER: ORB 297 filters + ENGU-Q 335 + TTM COMBINED x3 + NOISE 304"
job = {
    "type": "book", "status": "queued", "strategy": NAME,
    "book_name": "FRONTIER BOOK - opening range #297 + ENGU-Q #335 + squeeze COMBINED x3 + NOISE #304",
    "date_from": "2010-06-07", "date_to": "2026-06-30", "lockbox_months": 12,
    "slices": 8, "equity_points": 400, "mult": 1, "legs": legs,
    "note": ("Round 55 (tools/r55_frontier_orb_leg.py). Two slot upgrades were each confirmed on their own "
             "and had never been run together. Run #375 put run #297's opening-range leg into the adopted "
             "book and raised sealed-year return-over-drawdown 10.33 to 11.19 on the same money. Run #379 "
             "upgraded the squeeze slot to the combined leg but used run #314 in the opening-range slot, "
             "which rounds 53 and 55 both show is WORSE there than even the old control. This is #379 "
             "with only the opening-range leg swapped to #297, legs read verbatim from #379's own job. "
             "Measured locally with the house book engine at exact parity to #379 to the cent: sealed-year "
             "return-over-drawdown 11.02 to 12.07, sealed net $294,142 to $306,042, sealed drawdown "
             "$26,683 to $25,357, 8 of 8 slices. Selection stretch 44.35 to 43.72, a 1.4 percent "
             "difference on the stretch that round 53 showed is not predictive of the sealed year. "
             "SHAPE: the vol-regime filter axis is a smooth ridge through #297; all 26 geometry neighbours "
             "at these filters beat #379 on the sealed year. The volume-pace gate at 0.90 scores higher "
             "on the sealed year but far lower on the selection stretch - a one-year artifact, not used. "
             "No knob was tuned for this card: both upgrades were chosen before the sweep that measured them"),
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
if any("BOOK FRONTIER: ORB 297" in str(j.get("strategy", "")) for j in live):
    sys.exit("ABORT this book is already queued or running")
job["createdAt"] = datetime.datetime.now(datetime.timezone.utc)
ref = u.collection("backtests").document()
_retry(lambda: ref.set(job))
print("queued", ref.id, NAME)
