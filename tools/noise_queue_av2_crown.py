"""E9 ONE-TIME AUTO-VALIDATE 2 (4-YR LOCKBOX) ON THE NOISE CROWN #382 (scope SCOPE_RESEARCH_LOOP_2026-11-03 w92, MANAGER #162).

The crown's own RANGED file, NOISE_1_8_CT304.py (4 open knobs: gate_tf_min, gate_len, gate_ratio, tilt_mult; never pinned),
under the AV2 scope shipped v87.85 (row 57): variant validate2, 900 trials (OWNER RULE), 48-month lockbox, veto/report only.
Data = run #382's own: NQ 5m RTH, source db_noadj_rth (NOADJ_NQ_5m_RTH.csv), 2010-06-07 .. 2026-07-16. The END is pinned to
#382's (rerun-pinning rule): bars after 07-16 are the live forward stretch and stay out of every search.
HONEST CAVEAT, also in the job note: the 4-yr lockbox (2022-07..2026-07) is NOT virgin - it holds #382's spent 12-month
lockbox and the last WF folds, which the crown was chosen on. AV2 here measures how the crown's search behaves when four
years are held back; it cannot be a clean out-of-sample read of #382.
ORDER: it queues AFTER the census top-2 (E1). It refuses to queue unless --go is passed (MANAGER / the lane passes it once
E1's two jobs are in the queue), so it can never jump them.
    python tools/noise_queue_av2_crown.py --dry
    python tools/noise_queue_av2_crown.py --go
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
TAG = "AUTO-VALIDATE 2 (4-yr lockbox) NOISE crown #382 (E9 w92, owner 11-03, MANAGER #162)"
BASE = dict(type="validate", instrument="NQ", timeframe="5m", session="rth", source="db_noadj_rth",
            commission_usd=0.0, slippage_pts=0.0, cost_pts=0.533, mult=20,
            date_from="2010-06-07", date_to="2026-07-16", lockbox_months=48, wf_folds=8, variant="validate2", warm_days=300,
            n_trials=900, min_trades=30, mc_sims=500, n_rounds=0, select_oos_topk=10, oos_sample_k=30, discover="auto",
            provider="ollama", dsr=True, neighbors=True, regime=True, pills=True, context=True, equity_points=400)
JOBS = [
    ("NOISE", "NOISE crown #382 under AV2", dict(BASE, strategy="NOISE_1_8_CT304.py"),
     "run #382's own ranged file (gate + tilt knobs open)"),
]
LOG = os.path.join("C:/EdgeLog/_anatomy_cache/e9_av2", "queued.txt")


def note(fam, name, j, why):
    return ("%s: %s. Scope SCOPE_RESEARCH_LOOP_2026-11-03 E9, one-time. File %s = %s. NQ 5m RTH, source %s (NOADJ_NQ_5m_RTH.csv) "
            "pinned, window %s..%s (run #382's; forward bars excluded), AV2 scope: %d-month lockbox, veto/report only, never picks. "
            "900 trials, %d folds, warm_days %d, cost %s pt x %s $/pt. CAVEAT: the 4-yr lockbox holds #382's spent 12-month "
            "lockbox and its last WF folds, so it is not virgin - read as search behaviour, not as a clean OOS of #382. "
            "Nothing live, paper or in BOOK #463 changes. Driver tools/noise_queue_av2_crown.py."
            % (TAG, name, j["strategy"], why, j["source"], j["date_from"], j["date_to"], j["lockbox_months"],
               j["wf_folds"], j["warm_days"], j["cost_pts"], j["mult"]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--go", action="store_true", help="queue now (only once the E1 census top-2 are in the queue)")
    a = ap.parse_args()
    if not a.dry and not a.go:
        sys.exit("WAITS - E9 queues AFTER the census top-2 (E1). Re-run with --go once those two jobs are queued.")
    for fn in ("NOISE_1_8_CT304.py",):
        if not os.path.exists(os.path.join(REPO, "augur_strategies", fn)):
            sys.exit("ABORT - %s is not in the shared checkout" % fn)
    from augur_engine import data as D
    m = D.find_master("NQ", "5m", "rth", "db_noadj_rth")
    if not m or m.get("filename") != "NOADJ_NQ_5m_RTH.csv" or str(m.get("date_to"))[:10] < "2026-07-16":
        sys.exit("ABORT - the NQ 5m RTH db_noadj_rth master is not the registered one / too short: %r" % (m,))
    import firebase_admin
    from firebase_admin import credentials, firestore
    from google.api_core import exceptions as _gx
    from google.cloud.firestore_v1.base_query import FieldFilter as _FF
    if not firebase_admin._apps:
        firebase_admin.initialize_app(credentials.Certificate(os.path.join(REPO, "serviceAccount.json")))
    u = firestore.client().collection("users").document(UID)

    def _retry(fn, tries=4, wait=120):
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
        print("  live %s %-8s %-24s %-3s %s..%s  %s" % (did, x.get("status"), str(x.get("strategy"))[:24],
                                                       x.get("instrument"), x.get("date_from"), x.get("date_to"),
                                                       str(x.get("preset") or "")[:60]))
    clash = []
    for fam, name, j, _ in JOBS:
        for did, x in live:
            if TAG in str(x.get("note") or "") or TAG in str(x.get("preset") or ""):
                clash.append("%s already carries this tag (%s)" % (did, x.get("status")))
            if (x.get("strategy") == j["strategy"] and x.get("instrument") == j["instrument"]
                    and str(x.get("date_from")) == j["date_from"] and str(x.get("date_to")) == j["date_to"]):
                clash.append("%s: %s %s same window already %s as %s" % (fam, j["strategy"], j["instrument"],
                                                                        x.get("status"), did))
    if clash:
        sys.exit("ABORT - would double-queue:\n  " + "\n  ".join(sorted(set(clash))))
    if len(live) > 9:
        sys.exit("ABORT - queue too deep (%d)" % len(live))
    out = []
    for fam, name, j, why in JOBS:
        job = dict(j, status="queued", progress=0, preset="%s: %s" % (TAG, name), note=note(fam, name, j, why))
        if a.dry:
            print("DRY %s" % fam)
            for k in sorted(job):
                print("    %-16s %s" % (k, job[k]))
            continue
        job["createdAt"] = datetime.datetime.now(datetime.timezone.utc)
        ref = u.collection("backtests").document()
        _retry(lambda: ref.set(job))
        out.append((fam, ref.id))
        print("queued users/%s/backtests/%s  %s  [%s]" % (UID, ref.id, j["strategy"] + " " + j["instrument"],
                                                          job["preset"]))
        time.sleep(0.3)
    if out:
        with open(LOG, "a") as f:
            for fam, jid in out:
                f.write("%s %s %s\n" % (datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
                                        fam, jid))


if __name__ == "__main__":
    main()
