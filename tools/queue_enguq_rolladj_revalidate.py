"""PREPARED, NOT QUEUED - the two ENGU-Q re-validates on back-adjusted (roll-corrected) masters.

Owner call outstanding (ROLL_AUDIT.md 7.1). A bare run of this file is a DRY RUN: it opens no
Firestore client, writes nothing and touches no runner. It queues only with --confirm, and even
then it refuses unless every precondition below is satisfied. Safe to commit unqueued.

    python tools/queue_enguq_rolladj_revalidate.py             # dry run, prints the two job cards
    python tools/queue_enguq_rolladj_revalidate.py --confirm   # queues, if the preconditions pass

WHY (ROLL_AUDIT.md 3.2, written 2026-09-25; ENGUQ.md 2026-09-26)
ENGU-Q has no contract-roll handling, so a position held across a quarterly switch books the
contract offset, and for one to three days after a switch the regime average, moving average and
trendline still hold old-contract prices. Re-run on back-adjusted prices:

    ENGU-Q #335 validate champion (NQ 1m 24h, cost 0.533)
        whole   $541,330 / PF 1.820  ->  $476,435 / PF 1.699                (verified)
        cold LB  $58,163 / PF 1.531  ->   $43,468 / PF 1.366                (verified)
    ENGU-Q #370 (ES 1m 24h, cost 0.40)
        whole   681 tr / $381,313 / PF 2.459 -> 747 tr / $341,487 / PF 2.187 (verified)
        cold LB  $25,372 / PF 1.614          ->  $17,261 / PF 1.406          (verified)

Those came from local re-runs of the strategy file. Walk-forward folds, PBO and DSR were NOT
re-run for any crown - that is what these two jobs are for. Note up front that these runs are NOT
like-for-like with the originals in three declared ways, and each job card says so: the price
series is corrected, the trial budget rises to the house 900 (the originals ran 300 on NQ and 250
on ES), and the declared ranges are fenced shut (auto_expand False; the originals ran with the
runner default, which widened them).

PRECONDITIONS - all checked at run time, and --confirm aborts if any fails:
  1. A registered back-adjusted master exists for each tape. NONE EXISTS TODAY: the registry holds
     34 masters and no adjusted futures series at 1 minute; the only adjusted futures series are
     four 5-minute twins whose offset is stale and which stop adjusting on 2026-03-15.
  2. The committed roll table has an exact, offset-carrying row for every switch inside the window
     AND for every switch after it (the running adjustment sums all later switches). Today the last
     row on each root is a guess pinned to a weekend gap, and the June 2026 guess sits inside the
     window - the real NQ switch is inside the 2026-06-15 03:30 ET bar.
  3. The post-June-2026 data tail is repaired (the raw vendor files stop 2026-06-05).
  4. The full-window shift test passes on the exact parameters being queued (a constant shift must
     give identical trades). Proved for the #335 leg and #370; not proved file-wide.
"""
import argparse
import os
import sqlite3
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UID = "IO0K35JpLIcH9YK4C0pMNYUzZOM2"

# The two jobs. Window, cost, contract value and the sealed year are pinned to the run each one
# corrects; the source names are the masters that must be BUILT first (they do not exist yet).
JOBS = [
    dict(
        label="ENGU-Q #335 on back-adjusted NQ",
        strategy="ENGUQ_1M_ETH_R2_1_0.py",
        instrument="NQ", timeframe="1m", session="eth",
        source="db_adj_eth",                     # must exist and be registered first
        date_from="2010-06-07", date_to="2026-06-30",
        cost_pts=0.533, mult=20, lockbox_months=12, n_trials=900, warm_days=300,
        note=("[ROLL-ADJUSTED RE-VALIDATE] Corrects ENGU-Q #335 for the quarterly contract switch "
              "(ROLL_AUDIT.md 3.2). Window, cost, contract value and the sealed year are pinned to "
              "#335. Three declared differences from #335: the price series is back-adjusted, the "
              "trial budget is 900 against #335's 300, and the ranges are fenced (auto_expand off) "
              "where #335 widened them. Local re-run for reference: whole $541,330 -> $476,435, "
              "cold lockbox $58,163 -> $43,468. June 2026 splice repair is a further -$5,860 on "
              "the raw leg and is NOT in that figure."),
    ),
    dict(
        label="ENGU-Q #370 on back-adjusted ES",
        strategy="ENGUQ_1M_ETH_R2_1_0.py",
        instrument="ES", timeframe="1m", session="eth",
        source="db_adj_es_eth",                  # must exist and be registered first
        date_from="2010-06-07", date_to="2026-06-30",
        cost_pts=0.40, mult=50, lockbox_months=12, n_trials=900, warm_days=300,
        note=("[ROLL-ADJUSTED RE-VALIDATE] Corrects ENGU-Q #370 (ES) for the quarterly contract "
              "switch. Same three declared differences as the NQ job. Local re-run for reference: "
              "681 tr / $381,313 -> 747 tr / $341,487; cold lockbox $25,372 -> $17,261; lockbox by "
              "entry $34,960 -> $28,136 with the June splice repaired. NOTE the ES/MES paper-leg "
              "question is CLOSED-NO (ENGUQ.md 2026-09-26); this job exists to correct the record, "
              "not to re-open it."),
    ),
]


def registered_masters():
    """Read-only look at the master registry the runner resolves against."""
    db = os.path.join(ROOT, "optimizer_history.db")
    if not os.path.isfile(db):
        return None
    con = sqlite3.connect("file:%s?mode=ro" % db.replace("\\", "/"), uri=True)
    try:
        rows = con.execute(
            "SELECT filename, source FROM csv_files WHERE is_master=1").fetchall()
    except sqlite3.Error as exc:
        print("registry unreadable:", exc)
        return None
    finally:
        con.close()
    return {str(r[1] or "").strip().lower() for r in rows}


def preconditions():
    """Return a list of unmet preconditions, empty when it is safe to queue."""
    bad = []
    have = registered_masters()
    if have is None:
        bad.append("master registry not readable from this checkout "
                   "(worktrees carry no optimizer_history.db - run from the shared checkout)")
    else:
        for job in JOBS:
            if job["source"].lower() not in have:
                bad.append("master %r is not registered (%s)" % (job["source"], job["label"]))
    seams = os.path.join(ROOT, "tools", "data")
    tables = [f for f in os.listdir(seams) if f.startswith("contract_switches")] \
        if os.path.isdir(seams) else []
    if not tables:
        bad.append("no contract-switch table under tools/data - the roll table is the input the "
                   "adjusted masters are built from")
    else:
        bad.append("contract-switch table found (%s) - CHECK BY HAND that the last row on each "
                   "root is an exact switch with an offset, not a weekend-gap guess, before "
                   "queueing: the running adjustment sums every switch after each bar, so a "
                   "guessed September row silently poisons the whole series" % ", ".join(tables))
    return bad


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--confirm", action="store_true",
                    help="actually queue the jobs (owner approval required)")
    args = ap.parse_args()

    print("ENGU-Q roll-adjusted re-validate - %s" % ("QUEUE" if args.confirm else "DRY RUN"))
    for job in JOBS:
        print("\n  %s" % job["label"])
        for k in ("strategy", "instrument", "timeframe", "session", "source", "date_from",
                  "date_to", "cost_pts", "mult", "lockbox_months", "n_trials", "warm_days"):
            print("    %-15s %s" % (k, job[k]))
        print("    auto_expand     False")
        print("    note            %s" % job["note"][:110] + "...")

    bad = preconditions()
    print("\nPRECONDITIONS")
    for b in bad:
        print("  - %s" % b)
    if not bad:
        print("  all clear")

    if not args.confirm:
        print("\nDry run only. Nothing was queued. Re-run with --confirm once the owner approves "
              "and the preconditions above are clear.")
        return 0

    blocking = [b for b in bad if not b.startswith("contract-switch table found")]
    if blocking:
        print("\nREFUSING TO QUEUE - %d precondition(s) unmet." % len(blocking))
        return 2

    import firebase_admin                                          # noqa: E402
    from firebase_admin import credentials, firestore              # noqa: E402
    cred = os.path.join(ROOT, "serviceAccount.json")
    if not os.path.isfile(cred):
        print("no credential file at", cred)
        return 2
    if not firebase_admin._apps:
        firebase_admin.initialize_app(credentials.Certificate(cred))
    col = firestore.client().collection("users").document(UID).collection("backtests")
    for job in JOBS:
        doc = dict(job)
        doc.pop("label")
        doc.update(type="validate", status="queued", progress=0, auto_expand=False,
                   createdAt=firestore.SERVER_TIMESTAMP)
        ref = col.document()
        ref.set(doc)
        print("queued", ref.id, job["label"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
