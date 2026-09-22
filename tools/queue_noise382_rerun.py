"""
RE-RUN THE TOP NOISE AUTO-VALIDATE (#382) UNDER THE NEW ENGINE

WHY (owner 2026-09-22: "re run the top noise auto validate that gave us the best performing
roc/y ... lets see how it stacks up to that run and where the configs land"). On EXPLORE,
#382's 1E variants hold the best return-on-capital per year in the NOISE family (the KEEL v12
row at 84.2%). #382 itself is `NOISE_1_8_CT304.py` — the live NOISE crown with the hourly
compression size tilt — and it PASSED 6/6 on 2026-07-16 with a 12-month lockbox of $79,939
(3,997 points), profit factor 1.39, 239 trades.

Since that run the engine changed in one way that matters here: WARM STARTS (RESEARCH.md item
7, v73.841). Every scored out-of-sample stretch now runs from 300 prior sessions and keeps only
the trades entering inside it. NOISE lost 15% of its fold trades to the old cold start, so
#382's walk-forward numbers were measured on a footing that no longer exists.

TWO ARMS, so the comparison can actually be read:
  COLD  (warm_days 0)   — apples-to-apples with the stored #382. Any difference against it is
                          search-seed noise plus whatever else moved in the engine, NOT warm
                          starts.
  WARM  (warm_days 300) — today's default. Difference against the COLD arm is warm starts
                          alone.
Window, master, cost, lockbox length and tuning budget are pinned to #382's own run doc, so
nothing else varies. The file's space is small (2 x 2 x 2 x 3 = 24 cells), so both arms search
it exhaustively and "where the configs land" is a complete picture, not a sample.

    python tools/queue_noise382_rerun.py --dry
    python tools/queue_noise382_rerun.py
"""
import argparse
import datetime
import os
import sys

os.chdir(r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG")
import firebase_admin                                        # noqa: E402
from firebase_admin import credentials, firestore            # noqa: E402
from google.cloud.firestore_v1 import FieldFilter            # noqa: E402

UID = "IO0K35JpLIcH9YK4C0pMNYUzZOM2"
TAG = "N382RERUN"
STRATEGY = "NOISE_1_8_CT304.py"
INST, TF, SESS, SRC = "NQ", "5m", "rth", "db_noadj_rth"
COST = 0.533
DATE_FROM, DATE_TO = "2010-06-07", "2026-07-16"     # #382's own window, pinned
LOCKBOX_MONTHS = 12                                  # #382's own lockbox
ARMS = [("COLD (like #382)", 0), ("WARM (today's default)", 300)]

NOTE = ("Re-run of run #382 (NOISE-36, NOISE_1_8_CT304.py, the live NOISE crown x hourly "
        "compression size tilt) on its OWN pinned window and lockbox, after warm starts "
        "shipped (RESEARCH.md item 7, v73.841). Two arms: warm_days 0 is apples-to-apples "
        "with the stored #382 (differences = search noise), warm_days 300 is today's default "
        "(difference from the cold arm = warm starts alone). #382 for reference: PASS 6/6, "
        "whole $192,598 / PF 1.318 / 3,438 trades, lockbox 3,997 pts ($79,939) PF 1.395 on "
        "239 trades, WFE 2.472, crown tilt 2.0 at gate 30/16/1.15. The file's space is 24 "
        "cells, so both arms search it exhaustively. Driver tools/queue_noise382_rerun.py.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--trials", type=int, default=900)
    a = ap.parse_args()

    if not os.path.exists(os.path.join("augur_strategies", STRATEGY)):
        sys.exit("ABORT - %s is not in the runner's checkout (ship first)" % STRATEGY)

    if not firebase_admin._apps:
        firebase_admin.initialize_app(credentials.Certificate("serviceAccount.json"))
    u = firestore.client().collection("users").document(UID)

    busy = []
    for st in ("queued", "running"):
        for d in u.collection("backtests").where(filter=FieldFilter("status", "==", st)).stream():
            x = d.to_dict() or {}
            busy.append((st, str(x.get("strategy"))[:48]))
            if TAG in str(x.get("note") or ""):
                sys.exit("ABORT - a %s card is already %s (%s); not queueing twice"
                         % (TAG, st, d.id))
    print("queue depth: %d %s" % (len(busy), busy))
    if len(busy) > 6:
        sys.exit("ABORT - queue too deep, not adding")

    for label, warm in ARMS:
        job = {"type": "validate", "strategy": STRATEGY, "instrument": INST,
               "timeframe": TF, "session": SESS, "source": SRC, "cost_pts": COST,
               "date_from": DATE_FROM, "date_to": DATE_TO,
               "lockbox_months": LOCKBOX_MONTHS, "n_trials": int(a.trials),
               "warm_days": int(warm),
               "note": "[%s] ARM %s (warm_days %d) | %s" % (TAG, label, warm, NOTE),
               "status": "queued",
               "createdAt": datetime.datetime.now(datetime.timezone.utc)}
        if a.dry:
            print("\nDRY - %s: %s %s..%s lockbox %d mo, warm_days %d, %d trials"
                  % (label, STRATEGY, DATE_FROM, DATE_TO, LOCKBOX_MONTHS, warm, a.trials))
            continue
        ref = u.collection("backtests").document()
        ref.set(job)
        print("queued %-26s -> %s" % (label, ref.id))
    if a.dry:
        print("\n(dry run - nothing was written)")


if __name__ == "__main__":
    main()
