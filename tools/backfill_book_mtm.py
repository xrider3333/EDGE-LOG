"""Add the OPEN-TRADES-VALUED-DAILY reading (`book.mtm`) to book runs saved before it existed.

WHY (2026-09-25, book round 56, BOOK_ROUND56_ROC.txt section 5). augur_engine/book.py now scores
every book twice: at close (the headline, unchanged) and with every open trade valued at each
day's last price (`book.mtm`). COMPARE's book rows print the second drawdown whenever it differs.
Runs saved before v73.898 carry no such block, so their rows stay silent - including the FRONTIER
book #397, whose lockbox drawdown is $25,357 at close and $49,855 with open ENGU-Q trades counted.

WHAT IT DOES, per book run:
  1. reads the run's job doc (ONE filtered query) and its run doc (ONE read);
  2. re-runs the book through augur_engine.book.run_book with the job's own legs and window;
  3. REFUSES unless the re-run's at-close figures (whole, pre-lockbox, lockbox: net AND
     drawdown) equal the stored ones to the cent - a book whose files have moved since it ran
     is reported and skipped, never re-scored into a different book;
  4. with --write, updates ONLY the field `book.mtm` on that run doc. Nothing else is touched.

Re-running it over a run that already has `book.mtm` REPLACES that block - which is how a
correction reaches stored runs (2026-09-25: DIP / ETF legs had been valued at $1 a point; the
dry run prints the stored reading beside the new one).

Run from the shared checkout (the masters live there - BACKTEST_SPEED.md rule 3):
    python tools/backfill_book_mtm.py --runs 397 396 372          # dry run: prints what it would write
    python tools/backfill_book_mtm.py --runs 397 396 372 --write
    python tools/backfill_book_mtm.py --all --write                # every book run in the local run cache
"""
import argparse
import glob
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
os.environ.setdefault("AUGUR_TRIAL_CACHE", "1")

UID = "IO0K35JpLIcH9YK4C0pMNYUzZOM2"
RUN_CACHE = os.environ.get("EDGELOG_RUN_CACHE", r"C:\EdgeLog\_anatomy_cache\runs")


def _db():
    import firebase_admin
    from firebase_admin import credentials, firestore
    if not firebase_admin._apps:
        firebase_admin.initialize_app(credentials.Certificate(os.path.join(ROOT, "serviceAccount.json")))
    return firestore.client().collection("users").document(UID)


def cached_book_ids():
    ids = []
    for fp in glob.glob(os.path.join(RUN_CACHE, "*.json")):
        name = os.path.basename(fp)[:-5]
        if not name.isdigit():
            continue
        try:
            d = json.load(open(fp, encoding="utf-8"))
        except Exception:
            continue
        if isinstance(d.get("book"), dict) and isinstance(d["book"].get("legs"), list):
            ids.append(int(name))
    return sorted(ids)


def same(a, b):
    return a is not None and b is not None and abs(float(a) - float(b)) < 0.01


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--runs", nargs="*", type=int, default=[])
    ap.add_argument("--all", action="store_true", help="every book run in the local run cache")
    ap.add_argument("--write", action="store_true", help="write book.mtm (default: dry run)")
    a = ap.parse_args()
    from google.cloud.firestore_v1.base_query import FieldFilter as FF
    from augur_engine.book import run_book

    ids = sorted(set(a.runs) | (set(cached_book_ids()) if a.all else set()))
    if not ids:
        sys.exit("name book runs with --runs, or pass --all")
    u = _db()
    wrote = skipped = 0
    for rid in ids:
        jobs = list(u.collection("backtests").where(filter=FF("run_id", "==", rid)).stream())
        snap = u.collection("runs").document(str(rid)).get()
        if not jobs or not snap.exists:
            print(f"#{rid}: SKIP - {'no job doc' if not jobs else 'no run doc'}")
            skipped += 1
            continue
        job, doc = jobs[0].to_dict() or {}, snap.to_dict() or {}
        stored = doc.get("book") or {}
        if not job.get("legs") or not stored.get("legs"):
            print(f"#{rid}: SKIP - not a book run")
            skipped += 1
            continue
        try:
            bk = run_book(job["legs"], date_from=job.get("date_from"), date_to=job.get("date_to"),
                          lockbox_months=int(job.get("lockbox_months", 12) or 12),
                          slices=int(job.get("slices", 8) or 8))["book"]
        except Exception as e:
            print(f"#{rid}: SKIP - re-run failed: {type(e).__name__}: {e}")
            skipped += 1
            continue
        bad = [f"{st}.{k}" for st in ("whole", "pre_lockbox", "lockbox") for k in ("total_pnl", "max_drawdown")
               if not same((bk.get(st) or {}).get(k), (stored.get(st) or {}).get(k))]
        if bad:
            print(f"#{rid}: SKIP - re-run does not reproduce the stored book ({', '.join(bad)}); not re-scored")
            skipped += 1
            continue
        m = bk.get("mtm") or {}
        if m.get("error"):
            print(f"#{rid}: SKIP - mtm error {m['error']}")
            skipped += 1
            continue
        old = stored.get("mtm") or {}

        def _dd(block, st):
            v = (block.get(st) or {}).get("max_drawdown")
            return "none" if v is None else f"${v:,.0f}"
        # every stretch, as: valued daily now [stored valued daily before | at close]. The stored
        # reading matters because a re-run can CORRECT an earlier book.mtm (2026-09-25: the DIP
        # files' open trades had been valued at $1 a point).
        parts = [f"{st} {_dd(m, st)} [was {_dd(old, st)} | at close {_dd(stored, st)}]"
                 for st in ("whole", "pre_lockbox", "lockbox")]
        print(f"#{rid}: reproduces to the cent | valued daily: " + ", ".join(parts)
              + f", differs={m.get('drawdown_differs')}"
              + (f", unmarked={m.get('unmarked_trades')}" if m.get("unmarked_trades") else "")
              + f"{' -> WRITTEN' if a.write else ' (dry run)'}")
        if a.write:
            u.collection("runs").document(str(rid)).update({"book.mtm": m})
            wrote += 1
    print(f"done: {wrote} written, {skipped} skipped, {len(ids)} named")


if __name__ == "__main__":
    main()
