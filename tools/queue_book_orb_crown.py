"""Queue the adopted book with its OPENING-RANGE leg moved to the current crown too (round 53, 2026-09-09).

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
    {"strategy": "ORB_3_6_R6.py", "params": defaults("ORB_3_6_R6.py"), "instrument": "NQ",
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
if any("ORB CROWN ALIGNED" in str(j.get("strategy", "")) for j in live):
    sys.exit("ABORT this book already queued/running")
job = {
    "type": "book", "status": "queued",
    "strategy": "BOOK ORB CROWN ALIGNED: ORB 314 + ENGU-Q 335 + TTM SS x3 + NOISE 304",
    "book_name": "ORB-CROWN-ALIGNED BOOK - ORB #314 (R6) + ENGU-Q #335 (R2) + TTM SS x3 + NOISE #304",
    "date_from": "2010-06-07", "date_to": "2026-06-30", "lockbox_months": 12,
    "slices": 8, "equity_points": 400, "mult": 1, "legs": legs,
    "note": ("Round 53 (tools/r53_book_orb_leg_audit.py). The book adopted today gained 26 percent of its "
             "return-over-drawdown from one observation - it was carrying the ENGU-Q leg that had stopped being the "
             "crown the day before. That is a class of defect, so the same question was asked of the opening-range "
             "leg, and the answer is the same: the book uses run #234's configuration, but the opening-range crown "
             "moved to run #314 on 2026-09-05, with #234 explicitly kept as the CONTROL. The paper leg already "
             "trades #314; the book does not. This is the adopted book with that slot moved to the crown. "
             "LOCAL READ, same window and held-back split: selection window 1,391,722 dollars on a 33,350 drawdown, "
             "return-over-drawdown 41.73 against the adopted book 38.18, whole window 50.03 against 46.11, and "
             "profit factor 1.749 against 1.701. The held-back year is slightly WORSE at 10.06 against 10.33, "
             "which is inside the pre-registered tolerance of a tenth but is a give-back and is stated as one. "
             "THE HONEST ODDITY, because it makes this thinner evidence than the ENGU-Q swap was: run #314 is "
             "WEAKER on its own than run #234 - 9.12 return-over-drawdown against 10.32 in the selection window - "
             "so the book improves not because the leg is better but because its drawdowns fall in different "
             "places, which is why the book's drawdown drops from 36,562 to 33,350. The two legs correlate 0.899 "
             "day to day, so this is a small re-shaping of one leg rather than a new source of return. Running "
             "BOTH opening-range legs together is worse than either (34.84), so this is a swap, not an addition. "
             "PRE-REGISTERED BAR: beat the adopted book on selection-window return-over-drawdown while keeping the "
             "held-back year within a tenth of it. If it passes, the book and the paper leg finally agree on which "
             "opening-range configuration is the crown."),
}
job["createdAt"] = datetime.datetime.now(datetime.timezone.utc)
ref = u.collection("backtests").document(); _retry(lambda: ref.set(job))
print("queued", ref.id, job["strategy"])
