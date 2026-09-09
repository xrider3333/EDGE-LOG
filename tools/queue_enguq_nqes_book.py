"""Queue the ENGU-Q two-leg BOOK: the R2 crown file on NQ 1m 24h + the same file on ES 1m 24h (2026-09-08).

Why: round 37 found the ENGU-Q R2 crown clears the house bar on ES unchanged, and round 37d measured the
ES leg's correlation to the NQ leg at 0.20 daily / 0.21 monthly with a pooled 1:1 n/DD of 16.1 against
13.2 for NQ alone (tools/r37d_es_nq_corr.py). This puts that pooled read in front of the app's own BOOK
scorer with a sealed lockbox. NOTHING IS TUNED: both legs run the file's defaults (the #335 crown's
paper-leg configuration). Window pinned to the R2 crown run #335 (2010-06-07..2026-06-30), 12-month
lockbox, 8 slices. Each leg carries its own cost and multiplier (NQ 0.783/RT at $20, ES 0.40/RT at $50).
The ES single-leg validate (job GIrlgbDJ1umq12NrnfY8) remains the gate for the ES leg itself.

    python tools/queue_enguq_nqes_book.py
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


FN = "ENGUQ_1M_ETH_R2_1_0.py"
sp = ilu.spec_from_file_location("m", os.path.join("augur_strategies", FN)); m = ilu.module_from_spec(sp); sp.loader.exec_module(m)
P = {k: v["default"] for k, v in m.DEFAULT_PARAMS.items()}
legs = [
    {"strategy": FN, "params": dict(P), "instrument": "NQ", "timeframe": "1m", "session": "eth",
     "source": "db_noadj_eth", "cost_pts": 0.783, "mult": 20, "weight": 1},
    {"strategy": FN, "params": dict(P), "instrument": "ES", "timeframe": "1m", "session": "eth",
     "source": "db_noadj_eth", "cost_pts": 0.40, "mult": 50, "weight": 1},
]
live = _retry(lambda: [(d.to_dict() or {}) for d in u.collection("backtests")
                       .where("status", "in", ["queued", "running"]).stream()])
print("queue depth", len(live), [str(j.get("strategy"))[:30] + ":" + str(j.get("status")) for j in live])
if len(live) > 9: sys.exit("ABORT queue too deep")
if any("ENGU-Q NQ+ES" in str(j.get("strategy")) for j in live): sys.exit("ABORT already queued/running")
job = {
    "type": "book", "status": "queued",
    "strategy": "BOOK: ENGU-Q NQ+ES (R2 crown file on both tapes)",
    "book_name": "ENGU-Q TWO-LEG BOOK - R2 crown on NQ 1m 24h + ES 1m 24h",
    "date_from": "2010-06-07", "date_to": "2026-06-30", "lockbox_months": 12,
    "slices": 8, "equity_points": 400, "mult": 1, "legs": legs,
    "note": ("Round 37/37d follow-up (tools/r37_es_branch.py, tools/r37d_es_nq_corr.py). The ENGU-Q R2 crown file "
             "at its defaults on BOTH tapes, pooled one-to-one by the app's BOOK scorer. Local read on "
             "2010-06-07..2025-06-29: NQ leg $511,847 / PF 1.69 / n-per-DD 13.2; ES leg $208,644 / PF 1.37 / "
             "n-per-DD 10.8 (top-10 share 69 percent, said out loud); daily correlation 0.20, monthly 0.21, 685 shared "
             "entry days of 1,148 (NQ) / 1,262 (ES); pooled $720,491 / DD $44,896 / n-per-DD 16.1. NOTHING IS TUNED "
             "- every knob is ATR- or R-relative, which is why the file travels. Bar pre-registered: the book must "
             "beat the NQ leg alone on net-over-drawdown on the same window (16.1 vs 13.2 locally) and its lockbox "
             "must be positive; the ES single-leg validate (job GIrlgbDJ1umq12NrnfY8) stays the gate for the ES "
             "leg itself. Window pinned to the R2 crown run #335 so the three are comparable. The NQ 1-minute data "
             "hole (2026-07-01..08-05) sits AFTER this window."),
}
job["createdAt"] = datetime.datetime.now(datetime.timezone.utc)
ref = u.collection("backtests").document(); _retry(lambda: ref.set(job))
print("queued", ref.id, job["strategy"])
