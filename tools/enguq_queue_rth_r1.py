"""AUTO-VALIDATE 900 - ENGU-Q RTH r1: a market-hours ENGU-Q fit for the Webull QQQ book.

Owner decision 2026-10-09 ~20:20 MST, relayed as MANAGER #64: "DIP + search a market-hours
ENGU-Q". Pre-registration docs/PREREG_enguq_rth_r1_2026-10-10.md with addenda 1-4; reviewed by
STRATEGY-BEATING (#67 GO WITH EDITS, #69 folds confirmed with four pins). Not a port of the crown
- a NEW fit on the tape it would trade. ENGU-Q #335 stays live on NinjaTrader and becomes a
no-order tracker on Webull; nothing here goes near the paper book without the owner.

THE BAR, and it is a high one that was set before any cell existed: FRONTIER's Q36 measured NQ
#335's own signals filled on QQQ prints under the Webull executor and they keep 98% of the leg's
dollars, ROC at $30k of 28.42. The power line by Q36's own method is 12.70, so clause 1 needs a
walk-forward ROC of about 41.1 to beat the reference detectably. The crown's own is 26.5.

MY PRIOR IS THAT THIS FAILS, written before the run and strengthened twice since:
  - both QQQ Auto-Validates this house has run came back WEAK (ORB #486 PBO 0.976, NOISE #485
    PBO 0.687), and re-searching a crown has never paid here;
  - addendum 4 MEASURED the lever we thought mattered: dropping the two hard-coded NQ price
    floors moves the QQQ trade count from 308 to 398, about 90 of the 886 missing trades. The
    dominant constraint is the tape - 1,023,757 regular-hours bars against the overnight
    master's 5,503,474 - and no re-fit can conjure those bars back.
The round is run because the owner asked, because the operational case for a QQQ-native leg that
needs no live NQ feed is real, and because a clean falsification closes the question.

HARNESS, all gated before this script may be run (addendum 4):
  - tests/test_enguq_rth_lattice.py: every default on its own lattice, and BOTH reference cells
    reachable - the crown file's defaults AND run #335's champion settings, which are different
    numbers and where the third lattice break was caught (stop_mult 1.2, unreachable on 0.25).
  - code equivalence: the ranged file at #335's settings reproduces the crown trade for trade,
    1,387 against 1,387, on db_noadj_eth 2010-06-07..2026-06-30.
  - the two new floor knobs are asserted to MOVE the walk, not merely to exist.
  - timed trial on this master: 7.5 s a trial at the worst corner, no infinity or not-a-number
    with both floors at 0.00.

COSTS: 0.02 price units a share round trip = $0.01 a share a side, Q36's convention, at 822
shares - one NQ contract's notional in QQQ. Display dollars only.

Refuses if a job on the same file + instrument + window is already queued, running or paused, or
if any live job carries this label, or if the master is not the registered one FRONTIER pulled.
Run it only once ENGUQ_RTH_1_0.py is on main - the runner reads the shared checkout.
    python tools/enguq_queue_rth_r1.py --dry
    python tools/enguq_queue_rth_r1.py
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
TAG = "AUTO-VALIDATE 900 ENGU-Q RTH r1 market-hours QQQ fit"
MASTER = "master_dd092f50.csv"
STRATEGY = "ENGUQ_RTH_1_0.py"

JOB = dict(
    type="validate", strategy=STRATEGY,
    instrument="QQQ", timeframe="1m", session="rth", source="alpaca_split_rth",
    commission_usd=0.0, slippage_pts=0.0, cost_pts=0.02, mult=822,
    date_from="2016-01-04", date_to="2026-06-30",
    lockbox_months=12, wf_folds=8, warm_days=300,
    n_trials=900, min_trades=30, mc_sims=2000, n_rounds=0, select_oos_topk=10,
    discover="auto", provider="ollama",
    dsr=True, neighbors=True, regime=True, pills=True, context=True, equity_points=400,
)
LOGDIR = r"C:\EdgeLog\_anatomy_cache\enguq_rth_r1"
LOG = os.path.join(LOGDIR, "rth_r1_queued.txt")

NOTE = (
    "%s. ENGU-Q RTH r1, the market-hours fit for the Webull QQQ book (owner 2026-10-09 via "
    "MANAGER #64). Pre-registration docs/PREREG_enguq_rth_r1_2026-10-10.md + addenda 1-4, "
    "reviewed by STRATEGY-BEATING (#67, #69). File %s = the crown's mechanism re-fenced for a "
    "390-bar session, with the two hard-coded NQ price floors (risk 0.50 points, ATR 0.25) "
    "exposed as searchable knobs and the compiled walk removed because it hard-codes both. "
    "QQQ 1m RTH, master %s (id 144) pinned, window %s..%s, %d-month lockbox, %d folds, "
    "warm_days %d, cost %s a share round trip x %s shares (one NQ contract's notional; display "
    "dollars only), 900 trials (OWNER RULE, never lowered). THE BAR: walk-forward ROC at $30k "
    "must beat Q36's reference 28.42 by more than the 12.70 power line, so about 41.1, with "
    "Sortino at least matching, at least 100 WF and 50 LB trades, the lockbox profitable "
    "without its biggest trade, and the verdict not WEAK. WF decides; the lockbox is veto-only. "
    "My pre-registered prior is that this FAILS: both prior QQQ validates came back WEAK, and "
    "addendum 4 measured the floors recovering only ~90 of the 886 missing trades, leaving the "
    "tape's fifth-as-many bars as the binding constraint. Nothing live or paper changes. "
    "Driver tools/enguq_queue_rth_r1.py."
    % (TAG, STRATEGY, MASTER, JOB["date_from"], JOB["date_to"], JOB["lockbox_months"],
       JOB["wf_folds"], JOB["warm_days"], JOB["cost_pts"], JOB["mult"])
)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args()

    if not os.path.exists(os.path.join(REPO, "augur_strategies", STRATEGY)):
        sys.exit("ABORT - %s is not in the shared checkout; the runner would not find it"
                 % STRATEGY)

    # the master must be the one FRONTIER pulled, selected by FILENAME - find_master for
    # QQQ 1m returned the DAILY total-return master during the timed trial, a 2,637-bar tape
    # that would have run silently and produced a meaningless search.
    from augur_engine import data as D
    m = next((x for x in D.list_masters()
              if isinstance(x, dict) and x.get("filename") == MASTER), None)
    if not m:
        sys.exit("ABORT - %s is not registered as a master" % MASTER)
    if (m.get("instrument") != "QQQ" or m.get("timeframe") != "1m"
            or m.get("session") != "rth" or str(m.get("date_to"))[:10] != "2026-06-30"):
        sys.exit("ABORT - %s is not the registered QQQ 1m RTH master: %r" % (MASTER, m))
    print("master OK: %s rows=%s %s..%s source=%s"
          % (m.get("name"), m.get("rows"), m.get("date_from"), m.get("date_to"),
             m.get("source")))

    # the lattice gate must be green before anything is queued
    import subprocess
    gate = subprocess.run([sys.executable, "-m", "pytest", "-q",
                           os.path.join(REPO, "tests", "test_enguq_rth_lattice.py")],
                          capture_output=True, text=True, cwd=REPO)
    print("lattice gate:", (gate.stdout or "").strip().splitlines()[-1:] or gate.returncode)
    if gate.returncode != 0:
        sys.exit("ABORT - the lattice gate is not green; a search space that cannot express "
                 "its reference cells is a void round")

    import firebase_admin
    from firebase_admin import credentials, firestore
    from google.api_core import exceptions as _gx
    from google.cloud.firestore_v1.base_query import FieldFilter as _FF
    if not firebase_admin._apps:
        firebase_admin.initialize_app(
            credentials.Certificate(os.path.join(REPO, "serviceAccount.json")))
    u = firestore.client().collection("users").document(UID)

    def _retry(fn, tries=4, wait=120):
        for i in range(tries):
            try:
                return fn()
            except (_gx.ResourceExhausted, _gx.ServiceUnavailable, _gx.DeadlineExceeded) as e:
                print("attempt %d blocked (%s); waiting %ds" % (i + 1, type(e).__name__, wait),
                      flush=True)
                if i == tries - 1:
                    raise
                time.sleep(wait)

    live = _retry(lambda: [(d.id, d.to_dict() or {}) for st in ("queued", "running", "paused")
                           for d in u.collection("backtests")
                           .where(filter=_FF("status", "==", st)).stream()])
    print("queue depth", len(live))
    for did, x in live:
        print("  live %s %-8s %-26s %-5s %s..%s  %s"
              % (did, x.get("status"), str(x.get("strategy"))[:26], x.get("instrument"),
                 x.get("date_from"), x.get("date_to"), str(x.get("preset") or "")[:50]))

    clash = []
    for did, x in live:
        if TAG in str(x.get("note") or "") or TAG in str(x.get("preset") or ""):
            clash.append("%s already carries this label (%s)" % (did, x.get("status")))
        if (x.get("strategy") == STRATEGY and x.get("instrument") == JOB["instrument"]
                and str(x.get("date_from")) == JOB["date_from"]
                and str(x.get("date_to")) == JOB["date_to"]):
            clash.append("%s: %s %s same window already %s"
                         % (did, STRATEGY, JOB["instrument"], x.get("status")))
    if clash:
        sys.exit("ABORT - would double-queue:\n  " + "\n  ".join(sorted(set(clash))))
    if len(live) > 9:
        sys.exit("ABORT - queue too deep (%d)" % len(live))

    job = dict(JOB, status="queued", progress=0,
               preset="%s: market-hours ENGU-Q, full ranges" % TAG, note=NOTE)
    if a.dry:
        for k in sorted(job):
            print("    %-16s %s" % (k, job[k]))
        return
    job["createdAt"] = datetime.datetime.now(datetime.timezone.utc)
    ref = u.collection("backtests").document()
    _retry(lambda: ref.set(job))
    print("queued users/%s/backtests/%s" % (UID, ref.id))
    os.makedirs(LOGDIR, exist_ok=True)
    with open(LOG, "a") as fh:
        fh.write("%s ENGU-Q RTH r1 %s\n"
                 % (datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
                    ref.id))


if __name__ == "__main__":
    main()
