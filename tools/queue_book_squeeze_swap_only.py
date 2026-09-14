"""Queue the SQUEEZE-SWAP-ONLY four-leg book (book round 55d, 2026-09-14).

The adopted book #366 with ONE change: the squeeze slot holds the crowned combined leg (#369) instead of
the stop-only file (#353). The opening-range CONTROL (#234) is kept, because round 55c showed the
opening-range half of #379 is a coin flip year by year (against this book: dominates 7 of 15 full years,
loses 6) and its ratio edge is one dodged 2020 drawdown, while the squeeze swap earns more net in 13 of 15
years and loses one. Local read: selection 40.57, held-back 11.16 - the best held-back year of any
four-leg book scored - against #366's 38.18 / 10.33. Nothing tuned; one file swapped.
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
        {"strategy": "ORB_3_6_C2.py", "params": defaults("ORB_3_6_C2.py"), "instrument": "NQ",
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
if any("SQUEEZE SWAP ONLY" in str(j.get("strategy", "")) for j in live):
    sys.exit("ABORT already queued/running")
name = "BOOK SQUEEZE SWAP ONLY: ORB 234 + ENGU-Q 335 + TTM COMBINED x3 + NOISE 304"
job = {
    "type": "book", "status": "queued", "strategy": name, "book_name": name,
    "date_from": "2010-06-07", "date_to": "2026-06-30", "lockbox_months": 12,
    "slices": 8, "equity_points": 400, "mult": 1, "legs": legs_for(3),
    "note": ("Book round 55d (tools/book55c_year_by_year.py, tools/book55d_squeeze_only_years.py). The adopted book "
             "#366 with ONE change - the squeeze slot holds the crowned combined leg, run #369, instead of the "
             "stop-only file, run #353; the opening-range control #234 is KEPT. WHY NOT #379: judged year by year "
             "rather than by one whole-window ratio, the opening-range half of #379 is a coin flip - against this "
             "book it has more net and no deeper drawdown in 7 of 15 full years and less net with deeper drawdown "
             "in 6 - and #379's ratio lead over #366 is mostly one stretch, 2020, where #366 sets its whole-window "
             "maximum drawdown of 36,562 dollars and #379 does not. The squeeze swap on its own earns more net in "
             "13 of 15 years with a worst year of minus 4,061 dollars, and against #366 this book dominates 6 full "
             "years, loses 1 and is mixed in 8 (mostly more net with a slightly deeper in-year drawdown). "
             "PRE-REGISTERED YEAR TEST (dominate 9 of 15, lose no more than 3) is NOT met by the letter and is "
             "stated here. LOCAL READ: selection 40.57, held-back 11.16 - the best held-back year of any four-leg "
             "book scored - against #366 at 38.18 and 10.33. Nothing tuned; one file swapped."),
    "createdAt": datetime.datetime.now(datetime.timezone.utc),
}
ref = u.collection("backtests").document(); _retry(lambda: ref.set(job))
print("queued", ref.id, name)
