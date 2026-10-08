"""AUTO-VALIDATE 900 XLK (NOISE sector funds r1 PASS, 2026-10-08): the NOISE habitat grid on XLK.

docs/PREREG_noise_sectors_r1_2026-10-08.md (+ amendment 1): "PASS (any fund): a pinned 900-trial Auto-Validate the same
day for that fund (NOISE_1_0 on its 5m master, alpaca_split_rth, 2016-01-04 .. 2026-06-30, the grid's axes as the search
space)". Stage A 2026-10-08 11:10 MST: XLK PASS (crown 40 / 1.00 / 1.00 / 1.75, own ROC@30k 32.27, DD5 $22,850).
The job shape is MANAGER's QQQ validates' (C:/EdgeLog/manager/qqq_validate_1007/queue_qqq_validate_1007.py), copied:

  NOISE_1_1_FUNDGRID.py = NOISE_1_0 with the frozen grid's four axes open (the short band opens 0.75..1.50 step 0.25, so it
  adds 1.25 - disclosed in the file) and the inherited NQ filters pinned; parity-checked trade for trade against the
  Stage A harness on the crown and a corner cell.

XLK 5m RTH, master pinned by source alpaca_split_rth (id 123, master_c177163c.csv, sha256 bd68ebc1...), window
2016-01-04 .. 2026-06-30, 12-month lockbox (2025-06-30 .. 2026-06-30 - the first read of XLK's lockbox for NOISE), 900
trials (OWNER RULE), 8 folds, warm_days 300, cost 0.02 price units a share round trip (= $0.02 a share), mult 4610 shares
(= floor($100,000 / XLK's 2016-06-30 close), the fund unit - display dollars only), trade floor 30, select_oos_topk 10,
mc 2000, discover auto, no AI rounds.

Refuses if a job on the same file + instrument + window is already queued / running / paused, or one carries the label.
Run it only once NOISE_1_1_FUNDGRID.py is on main (the runner reads the shared checkout).
    python tools/noise_queue_xlk_validate.py --dry
    python tools/noise_queue_xlk_validate.py
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
TAG = "AUTO-VALIDATE 900 XLK (NOISE sectors r1 PASS 10-08)"
BASE = dict(type="validate", instrument="XLK", timeframe="5m", session="rth", source="alpaca_split_rth",
            commission_usd=0.0, slippage_pts=0.0, cost_pts=0.02, mult=4610,
            date_from="2016-01-04", date_to="2026-06-30", lockbox_months=12, wf_folds=8, warm_days=300,
            n_trials=900, min_trades=30, mc_sims=2000, n_rounds=0, select_oos_topk=10, discover="auto",
            provider="ollama", dsr=True, neighbors=True, regime=True, pills=True, context=True, equity_points=400)
JOBS = [
    ("NOISE", "NOISE habitat grid on XLK", dict(BASE, strategy="NOISE_1_1_FUNDGRID.py"),
     "NOISE_1_0 with the sector funds r1 grid open and the NQ filters pinned"),
]
LOG = os.path.join("C:/EdgeLog/_anatomy_cache/noise_funds_r1", "xlk_validate_queued.txt")


def note(fam, name, j, why):
    return ("%s: %s. NOISE sector funds r1 Stage A PASS for XLK (docs/PREREG_noise_sectors_r1_2026-10-08.md). "
            "File %s = %s. XLK 5m RTH, master %s "
            "(id 123) pinned, window %s..%s, %d-month lockbox (first read of XLK's lockbox for NOISE), %d folds, "
            "warm_days %d, cost %s a share x %s shares (fund unit, display only), 900 trials. Reading rule: the engine's "
            "own verdict; a book seat stays a report (house line #45). Nothing live or paper changes. Driver "
            "tools/noise_queue_xlk_validate.py."
            % (TAG, name, j["strategy"], why, j["source"], j["date_from"], j["date_to"], j["lockbox_months"],
               j["wf_folds"], j["warm_days"], j["cost_pts"], j["mult"]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args()
    for _, _, j, _ in JOBS:
        if not os.path.exists(os.path.join(REPO, "augur_strategies", j["strategy"])):
            sys.exit("ABORT - %s is not in the shared checkout" % j["strategy"])
    from augur_engine import data as D
    m = D.find_master("XLK", "5m", "rth", "alpaca_split_rth")
    if not m or m.get("filename") != "master_c177163c.csv" or str(m.get("date_to"))[:10] != "2026-06-30":
        sys.exit("ABORT - the XLK 5m RTH alpaca_split_rth master is not the registered one: %r" % (m,))
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
