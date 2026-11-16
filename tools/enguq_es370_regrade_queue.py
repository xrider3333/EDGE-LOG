"""AUTO-VALIDATE 900 - ENGU-Q on ES, the #370 re-grade at the HONEST cost on the ROLL-CORRECTED tape.

Owner GO 11-16 via MANAGER inbox #167, amended by MANAGER after ENGUQ flagged the closure.

WHY THIS RUN EXISTS. ENGU-Q on ES is CLOSED-NO in ENGUQ.md. Run #370 passes 6/6 with folds 8/8 ONLY at
cost 0.40 a round trip, which is below one tick plus commission on ES; round 46 pre-registered the
failure condition before the grade was read ("if it only survives at 0.40 it is not a leg"). #377 is
the SAME cell at the honest 0.60 and is WEAK. #442, which the ledger says "corrects #370", is WEAK with
the overfit check failing at 0.905 and a sealed year of ten trades whose ten best are all of it. On top
of that, 35 of #370's trades cross a contract switch and book $24,862 of pure carry on the no-adjust
tape. The sector-wide frontier nevertheless carries ENGUQES370 in its pool and in picks #1-#3 at the
0.40 no-adjust series, and OPUS-HUNT is rebuilding the mix from validated legs only.

ENGUQ.md names the minimum re-open condition itself: "one re-grade at 0.60 on back-adjusted prices with
June repaired, plus the concentration test on the graded cell." This run is that re-grade.

WHAT CHANGES FROM #370, and nothing else:
  cost_pts  0.40 -> 0.60   (one tick plus commission on ES; the owner screen says net > 0 after NORMAL cost)
  source    db_noadj_eth -> db_adj_eth  (ADJ_ES_1m_ETH.csv, back-adjusted, roll-corrected)
  n_trials  626 evaluated -> 900        (OWNER RULE, never lowered)
Same ranged file ENGUQ_1M_ETH_R2_1_0.py (never a pinned copy), same ES 1m ETH, same window
2010-06-07..2026-06-30, same 12-month lockbox (2025-06-30..2026-06-30), same 8 folds, same mult 50.

PRE-SET VERDICT, written before the run reads: the leg re-opens only if it PASSES at 0.60 on the
corrected tape. WEAK or worse and ENGU-Q on ES stays CLOSED-NO, the frontier pool loses the leg, and
picks #1-#3 need rebuilding without it. A pass that leans on the sealed year's ten best trades is not a
pass - the concentration read is reported beside the grade either way.

    python tools/enguq_es370_regrade_queue.py --dry
    python tools/enguq_es370_regrade_queue.py
"""
import argparse
import datetime
import os
import sys
import time

REPO = r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"
os.chdir(REPO)
sys.path.insert(0, REPO)
UID = "IO0K35JpLIcH9YK4C0pMNYUzZOM2"
TAG = "AUTO-VALIDATE 900 ENGU-Q ES #370 RE-GRADE at 0.60 on the roll-corrected tape (owner 11-16)"
STRATEGY = "ENGUQ_1M_ETH_R2_1_0.py"
MASTER_ID, MASTER_FILE = 58, "ADJ_ES_1m_ETH.csv"
LOGDIR = r"C:\EdgeLog\_anatomy_cache\enguq_es370_regrade"

JOB = dict(
    type="validate", strategy=STRATEGY,
    instrument="ES", timeframe="1m", session="eth", source="db_adj_eth",
    commission_usd=0.0, slippage_pts=0.0, cost_pts=0.60, mult=50,
    date_from="2010-06-07", date_to="2026-06-30",
    lockbox_months=12, wf_folds=8, warm_days=300,
    n_trials=900, min_trades=30, mc_sims=2000, n_rounds=0, select_oos_topk=10,
    discover="auto", provider="ollama",
    dsr=True, neighbors=True, regime=True, pills=True, context=True, equity_points=400,
)

NOTE = (
    TAG + ". Re-grade of run #370 (ENGU-Q on ES), ordered by the owner 11-16 and amended to the honest "
    "cost after this lane flagged that ENGU-Q on ES is CLOSED-NO in ENGUQ.md. #370 passes ONLY at 0.40 a "
    "round trip, below one tick plus commission on ES; round 46 pre-registered 'if it only survives at "
    "0.40 it is not a leg' before the grade was read. #377, the same cell at 0.60, is WEAK. #442 "
    "('corrects #370') is WEAK with the overfit check failing at 0.905 and a sealed year of ten trades "
    "whose ten best are 100 percent of it. 35 of #370's trades cross a contract switch and book $24,862 "
    "of pure carry on the no-adjust tape. CHANGES FROM #370 AND NOTHING ELSE: cost 0.40 to 0.60, source "
    "db_noadj_eth to db_adj_eth (ADJ_ES_1m_ETH.csv id 58, back-adjusted roll-corrected), trials to 900 "
    "(owner rule). Same ranged file, ES 1m ETH, window 2010-06-07..2026-06-30, 12-month lockbox "
    "2025-06-30..2026-06-30, 8 folds, warm 300 days, mult 50. PRE-SET VERDICT: the leg re-opens only on a "
    "PASS at 0.60 on the corrected tape; WEAK or worse and ENGU-Q on ES stays CLOSED-NO, the sector "
    "frontier pool loses ENGUQES370 and picks 1-3 rebuild without it. A pass carried by the sealed year's "
    "ten best trades is not a pass - #370's own sealed year made $64,852 on its ten best against a year of "
    "$25,372, the other 57 trades losing $39,482, power 0.37 against an 0.80 target - so the concentration "
    "read is reported beside the grade either way. Reported to MANAGER: run number, config, four numbers "
    "(ROC@30k, DD5, DD% from peak, Sortino), WF total dollars, engine WF against the lane series used in "
    "the sector table ($291,013) as a ratio, and the daily series path. Nothing live or paper changes. "
    "Driver tools/enguq_es370_regrade_queue.py."
)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args()

    spath = os.path.join(REPO, "augur_strategies", STRATEGY)
    if not os.path.exists(spath):
        sys.exit("ABORT - not in the shared checkout, the runner would not see it: " + spath)
    if "_PINNED" in STRATEGY:
        sys.exit("ABORT - Auto-Validate never runs on a pinned file")

    # the file must still have a real search space (owner rule: no 1-config validates)
    import importlib.util
    spec = importlib.util.spec_from_file_location("eq", spath)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    dp = mod.DEFAULT_PARAMS
    numeric = [k for k, s in dp.items() if s.get("type") in ("int", "float")]
    open_knobs = [k for k in numeric if float(dp[k]["min"]) < float(dp[k]["max"])]
    if not open_knobs:
        sys.exit("ABORT - every numeric knob has min == max; this is a pinned file in disguise")
    print("file OK: %s, %d numeric knobs, %d with a real range" % (STRATEGY, len(numeric), len(open_knobs)))

    from augur_engine import data as D
    m = D.find_master(JOB["instrument"], JOB["timeframe"], JOB["session"], JOB["source"])
    if not m or m.get("filename") != MASTER_FILE or int(m.get("id") or 0) != MASTER_ID:
        sys.exit("ABORT - the roll-corrected ES 1m ETH master is not id %s %s: %r" % (MASTER_ID, MASTER_FILE, m))
    if str(m.get("date_to"))[:10] < JOB["date_to"]:
        sys.exit("ABORT - master ends %s, before the window end %s" % (m.get("date_to"), JOB["date_to"]))
    if str(m.get("date_from"))[:10] > JOB["date_from"]:
        sys.exit("ABORT - master starts %s, after the window start %s" % (m.get("date_from"), JOB["date_from"]))
    print("master OK: id %s %s rows=%s %s..%s" % (m.get("id"), m.get("filename"), m.get("rows"),
                                                  m.get("date_from"), m.get("date_to")))

    import firebase_admin
    from firebase_admin import credentials, firestore
    from google.api_core import exceptions as _gx
    from google.cloud.firestore_v1.base_query import FieldFilter as _FF
    if not firebase_admin._apps:
        firebase_admin.initialize_app(credentials.Certificate(os.path.join(REPO, "serviceAccount.json")))
    u = firestore.client().collection("users").document(UID)

    def _retry(fn, tries=4, wait=90):
        for i in range(tries):
            try:
                return fn()
            except (_gx.ResourceExhausted, _gx.ServiceUnavailable, _gx.DeadlineExceeded) as e:
                print("attempt %d blocked (%s); waiting %ds" % (i + 1, type(e).__name__, wait), flush=True)
                if i == tries - 1:
                    raise
                time.sleep(wait)

    live = _retry(lambda: [(d.id, d.to_dict() or {}) for st in ("queued", "running", "paused")
                           for d in u.collection("backtests").where(filter=_FF("status", "==", st)).stream()])
    print("queue depth", len(live))
    for did, x in live:
        print("  live %s %-8s %-28s %-4s %s..%s" % (did, x.get("status"), str(x.get("strategy"))[:28],
                                                    x.get("instrument"), x.get("date_from"), x.get("date_to")))
    clash = []
    for did, x in live:
        if TAG in str(x.get("note") or "") or TAG in str(x.get("preset") or ""):
            clash.append("%s already carries this label (%s)" % (did, x.get("status")))
        if (x.get("strategy") == STRATEGY and str(x.get("instrument")) == JOB["instrument"]
                and str(x.get("date_from")) == JOB["date_from"] and str(x.get("date_to")) == JOB["date_to"]):
            clash.append("%s: same file, instrument and window already %s" % (did, x.get("status")))
    if clash:
        sys.exit("ABORT - would double-queue:\n  " + "\n  ".join(sorted(set(clash))))
    if len(live) > 9:
        sys.exit("ABORT - queue too deep (%d)" % len(live))

    job = dict(JOB, status="queued", progress=0,
               preset="%s: ranged R2 file, cost 0.60, roll-corrected master" % TAG, note=NOTE)
    if a.dry:
        print("\nDRY RUN - nothing written. Job:")
        for k in sorted(job):
            v = job[k]
            print("    %-16s %s" % (k, (str(v)[:150] + "...") if len(str(v)) > 150 else v))
        return
    job["createdAt"] = datetime.datetime.now(datetime.timezone.utc)
    ref = u.collection("backtests").document()
    _retry(lambda: ref.set(job))
    print("queued users/%s/backtests/%s" % (UID, ref.id))
    os.makedirs(LOGDIR, exist_ok=True)
    with open(os.path.join(LOGDIR, "validate_queued.txt"), "a") as fh:
        fh.write("%s ENGU-Q ES #370 re-grade 0.60 db_adj_eth job %s\n" % (
            datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"), ref.id))


if __name__ == "__main__":
    main()
