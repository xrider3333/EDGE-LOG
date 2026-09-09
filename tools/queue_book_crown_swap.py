"""Queue the BOOK with the CURRENT ENGU-Q crown in place of the ex-crown (round 48, 2026-09-09).

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


legs = [
    {"strategy": "ORB_3_6_C2.py", "params": defaults("ORB_3_6_C2.py"), "instrument": "NQ",
     "timeframe": "5m", "session": "rth", "source": "db_noadj_rth", "cost_pts": 0.533, "mult": 20, "weight": 1},
    {"strategy": "ENGUQ_1M_ETH_R2_1_0.py", "params": defaults("ENGUQ_1M_ETH_R2_1_0.py"), "instrument": "NQ",
     "timeframe": "1m", "session": "eth", "source": "db_noadj_eth", "cost_pts": 0.783, "mult": 20, "weight": 1},
    {"strategy": "TTMSQZ_3_0_ES30SS20.py", "params": defaults("TTMSQZ_3_0_ES30SS20.py"), "instrument": "ES",
     "timeframe": "30m", "session": "rth", "source": "db_noadj_rth", "cost_pts": 0.363, "mult": 50, "weight": 3},
]
live = _retry(lambda: [(d.to_dict() or {}) for d in u.collection("backtests")
                       .where("status", "in", ["queued", "running"]).stream()])
print("queue depth", len(live))
if len(live) > 9:
    sys.exit("ABORT queue too deep")
if any("crown swap" in str(j.get("strategy", "")) for j in live):
    sys.exit("ABORT crown-swap book already queued/running")
job = {
    "type": "book", "status": "queued",
    "strategy": "BOOK: ORB 234 + ENGU-Q 335 CROWN SWAP + TTM structural-stop x3",
    "book_name": "CROWN-SWAP BOOK - ORB 234 + ENGU-Q #335 (R2) + TTM SS x3",
    "date_from": "2010-06-07", "date_to": "2026-06-30", "lockbox_months": 12,
    "slices": 8, "equity_points": 400, "mult": 1, "legs": legs,
    "note": ("Round 48 (tools/r48_book_crown_swap.py). The book adopted today as run #361 still carries the "
             "EX-CROWN ENGU-Q leg: it uses the #309 efficiency file, but the ENGU-Q crown moved to run #335 - "
             "the R2 file, same mechanism with a 2.0 R breakeven and a 1.0 stop - on 2026-09-08, and only the "
             "paper leg was swapped that night. This is the same book with the current crown in that slot. It "
             "also corrects that leg's cost from 0.533 a round trip, which is the day-session convention, to "
             "0.783, which is the 24-hour convention it actually trades on, so the swap is not scored on an "
             "optimistic fill; the cost correction on its own is worth about 14,000 dollars and changes no "
             "conclusion. LOCAL READ on the same window and lockbox split as #361: selection window 1,048,336 "
             "dollars on a 36,435 drawdown, net-over-drawdown 28.77, against #361's 857,995 on 71,773 and 11.95; "
             "lockbox 231,399 on a 21,577 drawdown, 10.72, against #361's 253,081 on 32,129 and 7.88. So it makes "
             "22 percent more in the selection window on HALF the drawdown, and in the lockbox it makes 9 percent "
             "less on a third less drawdown. PRE-REGISTERED BAR: beat #361 on net-over-drawdown in BOTH stretches "
             "with a positive lockbox. SAID OUT LOUD, because it is the honest caveat and the swap does not fix "
             "it: every version of this book, the adopted one included, has a lockbox year whose ten best days are "
             "103 percent of its profit, so the recent year is tail-driven either way. The ENGU-Q leg's own lockbox "
             "was already read when run #335 was crowned, so the lockbox column here is a comparison rather than a "
             "fresh sealed test. Concentration in the SELECTION window is spread for both books - 31 to 36 percent "
             "of net in the ten best days - which is the stretch that carries the claim."),
}
job["createdAt"] = datetime.datetime.now(datetime.timezone.utc)
ref = u.collection("backtests").document(); _retry(lambda: ref.set(job))
print("queued", ref.id, job["strategy"])
