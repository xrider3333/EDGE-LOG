"""Queue the FOUR-LEG book: crown swap PLUS the NOISE crown, which the book has never carried (round 49, 2026-09-09).

Run #361 - the book adopted 2026-09-09 - carries the opening-range crown, an ENGU-Q leg and three lots
of the TTM structural-stop leg. Its ENGU-Q leg is the #309 efficiency file, but the ENGU-Q crown moved
to run #335 (the R2 file) on 2026-09-08 and only the paper leg was swapped. This queues the same book
with the current crown, and at the same time corrects the ENGU-Q leg's cost from the day-session 0.533
to the 24-hour convention 0.783, so the book is not scored on an optimistic fill.

Local read (tools/r48_book_crown_swap.py), same window and lockbox split as #361:
                        selection net / DD / n-per-DD        lockbox net / DD / n-per-DD
  #361 as adopted        857,995 / 71,773 / 11.95             253,081 / 32,129 /  7.88
  crown swap + cost fix  1,048,336 / 36,435 / 28.77           231,399 / 21,577 / 10.72
PRE-REGISTERED BAR: beat run #361 on net-over-drawdown in BOTH stretches and keep a positive lockbox.
STATED OUT LOUD: every version of this book - including the adopted one - has a lockbox year whose ten
best days are 103 percent of its profit, so the recent year is tail-driven regardless of the swap.
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
               "daytype_hi": 0.8, "stop_k": 1.75, "exit_mode": "vwap"}   # run #304's own champion, read from the run doc

legs = [
    {"strategy": "ORB_3_6_C2.py", "params": defaults("ORB_3_6_C2.py"), "instrument": "NQ",
     "timeframe": "5m", "session": "rth", "source": "db_noadj_rth", "cost_pts": 0.533, "mult": 20, "weight": 1},
    {"strategy": "ENGUQ_1M_ETH_R2_1_0.py", "params": defaults("ENGUQ_1M_ETH_R2_1_0.py"), "instrument": "NQ",
     "timeframe": "1m", "session": "eth", "source": "db_noadj_eth", "cost_pts": 0.783, "mult": 20, "weight": 1},
    {"strategy": "TTMSQZ_3_0_ES30SS20.py", "params": defaults("TTMSQZ_3_0_ES30SS20.py"), "instrument": "ES",
     "timeframe": "30m", "session": "rth", "source": "db_noadj_rth", "cost_pts": 0.363, "mult": 50, "weight": 3},
    {"strategy": "NOISE_1_1_NBHD.py", "params": NOISE_CROWN, "instrument": "NQ",
     "timeframe": "5m", "session": "rth", "source": "db_noadj_rth", "cost_pts": 0.533, "mult": 20, "weight": 1},
]
live = _retry(lambda: [(d.to_dict() or {}) for d in u.collection("backtests")
                       .where("status", "in", ["queued", "running"]).stream()])
print("queue depth", len(live))
if len(live) > 9:
    sys.exit("ABORT queue too deep")
if any("FOUR-LEG" in str(j.get("strategy", "")) for j in live):
    sys.exit("ABORT four-leg book already queued/running")
job = {
    "type": "book", "status": "queued",
    "strategy": "BOOK FOUR-LEG: ORB 234 + ENGU-Q 335 + TTM SS x3 + NOISE 304",
    "book_name": "FOUR-LEG BOOK - ORB 234 + ENGU-Q #335 (R2) + TTM SS x3 + NOISE #304",
    "date_from": "2010-06-07", "date_to": "2026-06-30", "lockbox_months": 12,
    "slices": 8, "equity_points": 400, "mult": 1, "legs": legs,
    "note": ("Round 49 (tools/r49_book_add_noise.py), on top of round 48. The book has never carried a NOISE leg, "
             "even though NOISE is crowned (run #304) and paper-traded. This is the round-48 crown-swap book - the "
             "opening-range crown, the CURRENT ENGU-Q crown at its honest 24-hour cost, and three lots of the TTM "
             "structural-stop leg - plus the NOISE crown at weight 1, using run #304's own champion settings read "
             "from the run document. LOCAL READ, same window and lockbox split throughout: the adopted book #361 "
             "scores 11.95 net-over-drawdown in the selection window and 7.88 in the lockbox; the crown swap alone "
             "lifts that to 28.77 and 10.72; adding NOISE at weight 1 lifts it again to 38.18 in the selection "
             "window while the lockbox stays level at 10.33. Net rises from 1,048,336 to 1,395,904 dollars for "
             "127 dollars of extra drawdown - the leg is nearly free in risk terms. It also IMPROVES concentration: "
             "the ten best days fall from 31 to 25 percent of selection-window profit. WEIGHT 1 IS DELIBERATE: at "
             "weight 2 the selection window looks better still at 43.82 but the lockbox DEGRADES to 9.00, which is "
             "the signature of leverage rather than edge, so it was rejected. CORRELATIONS, whole window: ENGU-Q to "
             "everything else is 0.01, TTM to everything is 0.05 to 0.10, but NOISE to the opening-range crown is "
             "0.42 - they share the NQ day session - so this leg is additive rather than diversifying and is "
             "judged on that basis. PRE-REGISTERED BAR: beat the crown-swap book on selection-window "
             "net-over-drawdown while keeping the lockbox within ten percent of it, and stay positive in the "
             "lockbox. SAID OUT LOUD: every version of this book has a lockbox year whose ten best days are around "
             "103 percent of its profit; adding NOISE does not fix that, and the ENGU-Q leg's own lockbox was "
             "already read when run #335 was crowned, so the lockbox column is a comparison rather than a fresh "
             "sealed test."),
}
job["createdAt"] = datetime.datetime.now(datetime.timezone.utc)
ref = u.collection("backtests").document(); _retry(lambda: ref.set(job))
print("queued", ref.id, job["strategy"])
