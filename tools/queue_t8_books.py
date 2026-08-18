"""Queue the three owner-visible BOOK confirmations from the t8 round.

Refuses to write anything if any job is already queued or running.
"""
import os
import sys
import json
import datetime

os.chdir(r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG")
import firebase_admin
from firebase_admin import credentials, firestore

if not firebase_admin._apps:
    firebase_admin.initialize_app(credentials.Certificate("serviceAccount.json"))
db = firestore.client()
UID = "IO0K35JpLIcH9YK4C0pMNYUzZOM2"
u = db.collection("users").document(UID)

busy = []
for d in u.collection("backtests").stream():
    j = d.to_dict() or {}
    if j.get("status") in ("queued", "running"):
        busy.append((d.id, j.get("status"), j.get("type")))
print("queue depth (queued+running):", len(busy), busy)
if len(busy) > 6:
    print("ABORT - queue too deep, not adding")
    sys.exit(1)

COST = 0.533
SRC5 = "db_noadj_rth"

ENG149 = {"tl_len": 48, "ema_len": 390, "regime_len": 0, "buf_atr": 0.9, "min_brk": 1.3,
          "atr_len": 30, "vol_mult": 0.8, "stop_mult": 1.0, "act_R": 2.5,
          "trail_frac": 2.5, "breakeven_R": 1.5}


def defaults(fn):
    import importlib.util
    sp = importlib.util.spec_from_file_location("m", os.path.join("augur_strategies", fn))
    m = importlib.util.module_from_spec(sp)
    sp.loader.exec_module(m)
    return {k: v["default"] for k, v in m.DEFAULT_PARAMS.items()}


def leg5(fn, params=None):
    return {"strategy": fn, "params": params or defaults(fn), "instrument": "NQ",
            "timeframe": "5m", "session": "rth", "source": SRC5,
            "cost_pts": COST, "mult": 20, "weight": 1}


ORB_C2 = leg5("ORB_3_6_C2.py")
N_V90 = leg5("NOISE_1_1_SBS_V90.py")
N_SBA = leg5("NOISE_1_1_SBA.py")
ENGQ = {"strategy": "ENGUQ_1M_1_0.py", "params": ENG149, "instrument": "NQ",
        "timeframe": "1m", "session": "rth", "source": "db_noadj_rth",
        "cost_pts": COST, "mult": 20, "weight": 1}

JOBS = [
    {"strategy": "BOOK: ORB234 + NOISE SBS_V90",
     "book_name": "ORB #234 crown + NOISE skip-shorts-after-weak-close + skip-wildest-10%",
     "date_from": "2010-06-07", "date_to": "2026-08-12", "lockbox_months": 18,
     "legs": [ORB_C2, N_V90],
     "note": ("t8 book round 2026-08-18. Same shape as run #238 but with the CURRENT ORB "
              "crown (#234 ORB_3_6_C2, was #230 ORB_3_4_C221) and the pinned NOISE variant "
              "NOISE_1_1_SBS_V90 in place of #238's confirm2+skip_bot_short leg. Window and "
              "18-month lockbox pinned to #238 so the two runs are directly comparable. "
              "Local pre-read: $770,619 / PF 1.342 / DD $35,518 / MAR 21.70 / 8-of-8 slices "
              "vs #238's $716,089 / 1.290 / $39,809 / 17.99 / 7-of-8.")},
    {"strategy": "BOOK: ORB234 + NOISE SBA",
     "book_name": "ORB #234 crown + NOISE skip-all-after-weak-close",
     "date_from": "2010-06-07", "date_to": "2026-08-12", "lockbox_months": 18,
     "legs": [ORB_C2, N_SBA],
     "note": ("t8 book round 2026-08-18. Sibling of the SBS_V90 job: same ORB crown leg, "
              "NOISE leg = NOISE_1_1_SBA (skip ALL trades the day after a weak close). "
              "Best two-leg MAR in the local round. Local pre-read: $756,729 / PF 1.321 / "
              "DD $33,691 / MAR 22.46 / 7-of-8 slices.")},
    {"strategy": "BOOK: ORB234 + ENGU-Q RTH (baseline)",
     "book_name": "BASELINE - ORB #234 crown + ENGU-Q RTH 149, 1:1",
     "date_from": "2010-06-07", "date_to": "2026-06-30", "lockbox_months": 12,
     "legs": [ORB_C2, ENGQ],
     "note": ("t8 book round 2026-08-18. The owner's stated book baseline, rebuilt on the "
              "current legal ORB crown #234. date_to pinned to 2026-06-30 because the NQ 1m "
              "RTH master has a real hole 2026-07-17 -> 2026-08-05. This is the CONTROL for "
              "the 3-leg job. Local pre-read: $850,825 / PF 1.352 / DD $58,171 / MAR 14.63 / "
              "8-of-8 slices.")},
    {"strategy": "BOOK: ORB234 + ENGU-Q RTH + NOISE SBS_V90 (3-leg)",
     "book_name": "3-LEG - ORB #234 + ENGU-Q RTH 149 + NOISE SBS_V90, 1:1:1",
     "date_from": "2010-06-07", "date_to": "2026-06-30", "lockbox_months": 12,
     "legs": [ORB_C2, ENGQ, N_V90],
     "note": ("t8 book round 2026-08-18. THE QUESTION: does NOISE earn a permanent slot "
              "next to the ORB x ENGU-Q baseline? Same window/lockbox as the baseline job so "
              "the pair is directly comparable. Local pre-read: $1,245,994 / PF 1.369 / "
              "DD $56,090 / MAR 22.21 / 8-of-8 slices - better than the baseline on net, PF, "
              "drawdown and MAR at once. Measured daily correlations: ORB~ENGU-Q 0.010, "
              "ORB~NOISE 0.389, ENGU-Q~NOISE 0.044.")},
]

ids = []
for j in JOBS:
    doc = dict(j)
    doc.update({"type": "book", "status": "queued", "slices": 8, "equity_points": 400,
                "createdAt": datetime.datetime.now(datetime.timezone.utc)})
    ref = u.collection("backtests").document()
    ref.set(doc)
    ids.append((ref.id, j["strategy"]))
    print("queued", ref.id, j["strategy"])

print(json.dumps(ids))
