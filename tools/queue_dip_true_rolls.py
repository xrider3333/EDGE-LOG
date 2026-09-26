"""RE-VALIDATE DIP ON TRUE ROLLS (2026-09-26, owner GO via MANAGER).

ROLL_AUDIT.md 3.6 found NQDIP 1.0/1.1 dropping the whole overnight gap on every night the house detector
flagged (and missing two thirds of the real switches), so DIP drawdowns read 23-29% too small. NQDIP 1.2
(1.0 rules) and 1.3 (1.1 rules) remove only the contract offset at the true switch bar. This queues the
three live DIP candidates again on the fixed files, LIKE FOR LIKE with the runs they replace:

    #425 DIP on ES   (NQDIP_1_0 on ES, PASS 6/6)  -> NQDIP_1_2 on ES
    #423 DIP on NQ   (NQDIP_1_0 on NQ, WEAK)      -> NQDIP_1_2 on NQ
    #424 DIP 1.1 NQ  (NQDIP_1_1 on NQ, WEAK)      -> NQDIP_1_3 on NQ

Same master (db_noadj_rth), window 2010-06-07..2026-08-24, 12-month lockbox, 8 folds, warm_days 400,
900 tuning trials, trade floor 30. Pre-registered, before any result: the verdict that counts is the new
one; if #425's replacement drops below PASS, DIP on ES stops being a book candidate until re-argued.
    python tools/queue_dip_true_rolls.py [--dry]
"""
import argparse, datetime, os, sys, time
os.chdir(r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG")
import firebase_admin
from firebase_admin import credentials, firestore
from google.cloud.firestore_v1 import FieldFilter

UID = "IO0K35JpLIcH9YK4C0pMNYUzZOM2"
TAG = "DIP TRUE ROLLS"
DIP = dict(type="validate", timeframe="5m", session="rth", source="db_noadj_rth",
           cost_pts=0.0, mult=1, commission_usd=0.0, slippage_pts=0.0, date_from="2010-06-07",
           date_to="2026-08-24", lockbox_months=12, wf_folds=8, n_trials=900, min_trades=30,
           mc_sims=2000, n_rounds=0, select_oos_topk=10, discover="auto", provider="ollama", dsr=True,
           neighbors=True, regime=True, pills=True, context=True, equity_points=400, warm_days=400)
JOBS = [
    (dict(DIP, strategy="NQDIP_1_2.py", instrument="ES"), 425, "DIP on ES"),
    (dict(DIP, strategy="NQDIP_1_2.py", instrument="NQ"), 423, "DIP on NQ"),
    (dict(DIP, strategy="NQDIP_1_3.py", instrument="NQ"), 424, "DIP 1.1 on NQ"),
]


def note(orig, name):
    return ("%s - %s, re-run of #%d on the roll-fixed file. ROLL_AUDIT.md 3.6: the old file dropped the "
            "whole overnight gap on every night the house detector flagged (and missed most real switches), "
            "so its drawdown read 23-29%% too small. The new file removes only the contract offset at the true "
            "switch bar (tools/data/contract_switches_*.csv). Same master, window, lockbox, folds, warm_days "
            "and trade floor as #%d. Driver tools/queue_dip_true_rolls.py." % (TAG, name, orig, orig))


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--dry", action="store_true"); a = ap.parse_args()
    for job, _, _ in JOBS:
        if not os.path.exists(os.path.join("augur_strategies", job["strategy"])):
            sys.exit("ABORT - %s is not in the shared checkout yet (pull main first)" % job["strategy"])
    if not firebase_admin._apps:
        firebase_admin.initialize_app(credentials.Certificate("serviceAccount.json"))
    u = firestore.client().collection("users").document(UID)
    live = []
    for stt in ("queued", "running"):
        for d in u.collection("backtests").where(filter=FieldFilter("status", "==", stt)).stream():
            x = d.to_dict() or {}
            if TAG in str(x.get("note") or ""):
                sys.exit("ABORT - a %s job is already %s (%s)" % (TAG, stt, d.id))
            live.append(x)
    print("queue depth", len(live))
    if len(live) > 4:
        sys.exit("ABORT - queue too deep")
    for job, orig, name in JOBS:
        job = dict(job, status="queued", progress=0, note=note(orig, name),
                   preset="%s - %s (replaces #%d)" % (TAG, name, orig))
        if a.dry:
            print("DRY", job["strategy"], job["instrument"], "replaces #%d" % orig); continue
        job["createdAt"] = datetime.datetime.now(datetime.timezone.utc)
        ref = u.collection("backtests").document(); ref.set(job)
        print("queued", ref.id, job["strategy"], job["instrument"], "replaces #%d" % orig)
        time.sleep(0.3)
