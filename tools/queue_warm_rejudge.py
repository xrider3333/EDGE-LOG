"""RE-JUDGE THE COLD-START VICTIMS UNDER WARM STARTS (2026-09-24, owner: "auto validate anything promising").

Warm starts shipped in v73.841 (2026-09-20): every stretch a validate scores out of sample now warms up
over earlier sessions and keeps only the trades that enter inside it. Nothing stored was re-judged. The
cold-start audit (tools/wf_coldstart_audit.py) named the runs whose verdicts it bent most - every daily
long-trend strategy, all of which FAILED on walk-forward efficiency while the intraday legs passed:

    ETF stack legs  #354 GLD, #355 TLT, #356 QQQ (N-day low), #357 IWM, #358 QQQ (RSI2), #359 QQQ (pullback)
    Dip strategy    #400 NQDIP 1.0, #401 NQDIP 1.1 (and #307 / #315 before them)

LIKE FOR LIKE: each job copies its original's file, instrument, master, window, lockbox length and
minimum-trades floor. What changes:
  * warm_days 400 - the runner default is 300, but these files search trend filters up to 300 sessions
    and the dip file needs trend + 30 before it trades, so 300 would still starve the longest cells;
  * 900 tuning trials - the owner's standing rule (the originals ran 300 / 900).
The dip jobs go back to the 12-month lockbox #307/#315 used: the 24-month lockbox of #400/#401 was a
patch for the cold lockbox, which warm starts now fix properly.

Pre-registered, before any result: a leg that flips FAIL -> PASS is a candidate again, not adopted; the
ETF book (run #349) is re-scored only on legs that PASS; the dip strategy's dollars stay about half plain
long exposure (tools/nqdip_beta_check.py) whatever the verdict.
    python tools/queue_warm_rejudge.py [--dry]
"""
import argparse, datetime, os, sys, time
os.chdir(r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG")
import firebase_admin
from firebase_admin import credentials, firestore
from google.cloud.firestore_v1 import FieldFilter

UID = "IO0K35JpLIcH9YK4C0pMNYUzZOM2"
TAG = "WARM RE-JUDGE"
WARM, TRIALS = 400, 900
ETF = dict(type="validate", timeframe="1d", session="rth", source="yahoo_adj", cost_pts=0.0, mult=1,
           date_from="2009-06-01", date_to="2026-06-30", lockbox_months=12, wf_folds=8, n_trials=TRIALS,
           min_trades=100, discover="auto", equity_points=400, warm_days=WARM)
DIP = dict(type="validate", instrument="NQ", timeframe="5m", session="rth", source="db_noadj_rth",
           cost_pts=0.0, mult=1, commission_usd=0.0, slippage_pts=0.0, date_from="2010-06-07",
           date_to="2026-08-24", lockbox_months=12, wf_folds=8, n_trials=TRIALS, min_trades=30,
           mc_sims=2000, n_rounds=0, select_oos_topk=10, discover="auto", provider="ollama", dsr=True,
           neighbors=True, regime=True, pills=True, context=True, equity_points=400, warm_days=WARM)
JOBS = [
    (dict(ETF, strategy="ETFDIP_DBL7_1_0.py", instrument="GLD"), 354),
    (dict(ETF, strategy="ETFDIP_DBL7_1_0.py", instrument="TLT"), 355),
    (dict(ETF, strategy="ETFDIP_DBL7_1_0.py", instrument="QQQ"), 356),
    (dict(ETF, strategy="ETFDIP_RSI2_1_0.py", instrument="IWM"), 357),
    (dict(ETF, strategy="ETFDIP_RSI2_1_0.py", instrument="QQQ"), 358),
    (dict(ETF, strategy="ETFDIP_PB20_1_0.py", instrument="QQQ"), 359),
    (dict(DIP, strategy="NQDIP_1_0.py"), 307),
    (dict(DIP, strategy="NQDIP_1_1.py"), 315),
]


def note(orig):
    return ("%s of run #%d. Warm starts (v73.841) were shipped after this strategy was judged on cold "
            "walk-forward folds and a cold lockbox; the cold-start audit measured those costing its trend "
            "filter a large share of every out-of-sample stretch. Same file, instrument, master, window, "
            "lockbox length and trade floor as #%d; changed: warm_days 400 (covers the longest trend "
            "filter searched) and 900 tuning trials (owner rule). A FAIL->PASS flip makes it a candidate "
            "again, nothing more. Driver tools/queue_warm_rejudge.py." % (TAG, orig, orig))


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--dry", action="store_true"); a = ap.parse_args()
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
    for job, orig in JOBS:
        job = dict(job, status="queued", progress=0, note=note(orig),
                   preset="%s - #%d under warm starts" % (TAG, orig))
        if a.dry:
            print("DRY", job["strategy"], job["instrument"], "orig #%d" % orig); continue
        job["createdAt"] = datetime.datetime.now(datetime.timezone.utc)
        ref = u.collection("backtests").document(); ref.set(job)
        print("queued", ref.id, job["strategy"], job["instrument"], "re-judges #%d" % orig)
        time.sleep(0.3)
