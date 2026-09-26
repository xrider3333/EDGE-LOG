"""One-off: mark the September 2026 contract-roll-splice paper trades ROLL, never delete.

ROLL_AUDIT.md ("Urgent (live/paper)" item 1; section 4.5.4) found that an in-bar Sep->Dec
contract switch inside the 09-14 11:30 ET bar put fake trades into the paper record: a
09-14 11:45-15:55 ET NOISE-family long on 15 legs (-$980.66/contract, sized differently
per leg), a 09-16 09:45 ET ORB long (-$1,930.66) and a 09-16 14:10 ET ORB_R6 long
(-$2,410.66). The owner call was to KEEP these trades (never delete a paper trade) but
mark them, in a way that survives api/paper.py's nightly re-upsert of the whole paper
record from the unadjusted master.

This script applies tools/data/paper_roll_artifacts.json (the committed flag list; see
its "_comment" field and api/paper.py's ROLL_ARTIFACTS) to the LIVE Firestore docs, once.
Going forward, api/paper.py itself re-applies the same fields on every nightly run, so
this script only needs to run again if new entries are added to the JSON file for docs
that predate the code change reaching the runner.

Usage:
    python tools/mark_roll_artifacts.py            # dry run: print what would change
    python tools/mark_roll_artifacts.py --apply    # merge-only write of roll_artifact/roll_note

Safety:
  * merge-only writes (`set(doc, merge=True)` with ONLY roll_artifact/roll_note in the
    payload) -- nothing else on any trade doc is touched, and no doc is ever deleted.
  * every entry is verified against the live doc (leg, entry_unix via the doc id, and
    recorded_pnl_usd to the cent) before ANYTHING is written. A single mismatch or a
    missing doc stops the run with nothing applied -- this never guesses.
  * --apply is required to write; the default is read-only.
"""
import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
sys.path.insert(0, ROOT)

UID = "IO0K35JpLIcH9YK4C0pMNYUzZOM2"
FLAG_LIST = os.path.join(ROOT, "tools", "data", "paper_roll_artifacts.json")
PNL_TOL = 0.02  # cents of float-formatting slack; not a real tolerance for "is this the trade"


def _db():
    import firebase_admin
    from firebase_admin import credentials, firestore
    if not firebase_admin._apps:
        cred_path = next((p for p in (
            os.path.join(ROOT, "serviceAccount.json"),
            os.path.expanduser(r"~\OneDrive\Desktop\EDGE-LOG\serviceAccount.json"),
        ) if os.path.exists(p)), None)
        if not cred_path:
            raise SystemExit("serviceAccount.json not found (checked this checkout and the "
                              "shared one at ~\\OneDrive\\Desktop\\EDGE-LOG)")
        firebase_admin.initialize_app(credentials.Certificate(cred_path))
    return firestore.client()


def _load_entries():
    with open(FLAG_LIST, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("entries") or []


# Optional per the task: the WRITE-ONCE daily report docs (paper_reports/2026-09-14..16)
# keep their original numbers untouched -- this only adds a note field nothing else reads,
# pointing whoever opens that day's report at the explanation, same merge-only guarantee
# as the trade docs above (only this one key is ever touched).
REPORT_NOTES = {
    "2026-09-14": "This day's blend/book figures include the NOISE-family fake long from "
                  "the in-bar Sep->Dec contract-roll splice (ROLL_AUDIT.md 4.5.4). The "
                  "affected paper_trades docs are now flagged roll_artifact:true and shown "
                  "with a ROLL badge on the NT8 FUTURES tab; the numbers on THIS report doc "
                  "are unchanged (write-once).",
    "2026-09-15": "This day's blend (-$84,279) and book (-$10,544.28) figures are a splice "
                  "artifact: that night's run appended September-contract NT capture bars "
                  "after the December master's last bar, marking several ENGU-Q trades at "
                  "fake prices (ROLL_AUDIT.md 4.5.4/4.5.5). No 09-15 paper_trades doc was on "
                  "the owner-approved roll_artifact list, so none is flagged; this note only "
                  "explains the report's own numbers. The numbers on THIS report doc are "
                  "unchanged (write-once).",
    "2026-09-16": "This day's figures include the ORB (-$1,930.66) and ORB_R6 (-$2,410.66) "
                  "fake longs let through by ORB's volatility filter reading the splice-"
                  "widened 09-14 session range (ROLL_AUDIT.md 4.5.4). The affected "
                  "paper_trades docs are now flagged roll_artifact:true and shown with a "
                  "ROLL badge on the NT8 FUTURES tab; the numbers on THIS report doc are "
                  "unchanged (write-once).",
}


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true",
                     help="write the marks (merge-only); default is dry-run/print-only")
    ap.add_argument("--report-notes", action="store_true",
                     help="also add a merge-only 'roll_note' string to the 09-14/15/16 "
                          "paper_reports docs (optional; never touches their numbers)")
    ap.add_argument("--uid", default=UID)
    args = ap.parse_args()

    entries = _load_entries()
    if not entries:
        raise SystemExit(f"no entries in {FLAG_LIST}")

    db = _db()
    col = db.collection("users").document(args.uid).collection("paper_trades")

    matched = []
    problems = []
    for e in entries:
        leg, eu = e["leg"], int(e["entry_unix"])
        doc_id = f"pt_{leg}_{eu}"
        snap = col.document(doc_id).get()
        if not snap.exists:
            problems.append(f"MISSING doc {doc_id} (leg={leg} entry_unix={eu})")
            continue
        t = snap.to_dict() or {}
        if t.get("leg") != leg:
            problems.append(f"{doc_id}: doc's leg field is {t.get('leg')!r}, expected {leg!r}")
            continue
        if int(t.get("entryTime") or -1) != eu:
            problems.append(f"{doc_id}: doc's entryTime is {t.get('entryTime')!r}, "
                             f"expected {eu}")
            continue
        recorded = float(e.get("recorded_pnl_usd"))
        actual = float(t.get("pnl_usd") or 0.0)
        if abs(actual - recorded) > PNL_TOL:
            problems.append(f"{doc_id}: pnl_usd is {actual:.2f}, expected {recorded:.2f} "
                             f"(diff {actual - recorded:+.2f}) -- STOPPING, not guessing")
            continue
        already = bool(t.get("roll_artifact"))
        matched.append({"doc_id": doc_id, "leg": leg, "entry_et": e.get("entry_et"),
                         "pnl_usd": actual, "reason": e.get("reason"), "already_marked": already})

    print(f"Flag list: {FLAG_LIST} ({len(entries)} entries)")
    print(f"Matched {len(matched)}/{len(entries)} against live Firestore docs.\n")
    for m in matched:
        flag = " [already marked]" if m["already_marked"] else ""
        print(f"  {m['doc_id']:<38} leg={m['leg']:<20} entry_et={m['entry_et']:<27} "
              f"pnl={m['pnl_usd']:>10.2f}{flag}")

    if problems:
        print(f"\n{len(problems)} PROBLEM(S) -- stopping, nothing will be written even with --apply:")
        for p in problems:
            print(f"  ! {p}")
        raise SystemExit(1)

    if not args.apply:
        print("\nDry run only -- nothing written. Re-run with --apply to write the marks "
              "(merge-only: adds roll_artifact/roll_note, touches nothing else, never deletes).")
    else:
        to_write = [m for m in matched if not m["already_marked"]]
        print(f"\n--apply: writing roll_artifact/roll_note to {len(to_write)} doc(s) "
              f"({len(matched) - len(to_write)} already marked, left untouched)...")
        batch = db.batch()
        pending = 0
        for m in to_write:
            ref = col.document(m["doc_id"])
            batch.set(ref, {"roll_artifact": True,
                             "roll_note": m["reason"] or "2026-09 contract roll splice "
                                                          "(ROLL_AUDIT 4.5.4)"}, merge=True)
            pending += 1
            if pending >= 400:
                batch.commit(); batch = db.batch(); pending = 0
        if pending:
            batch.commit()
        print("Done.")

    if args.report_notes:
        rcol = db.collection("users").document(args.uid).collection("paper_reports")
        print(f"\n{'--apply' if args.apply else 'DRY RUN'}: report notes on "
              f"{len(REPORT_NOTES)} paper_reports doc(s):")
        for did, note in REPORT_NOTES.items():
            snap = rcol.document(did).get()
            if not snap.exists:
                print(f"  ! {did}: doc does not exist -- skipped")
                continue
            existing = (snap.to_dict() or {}).get("roll_note")
            status = "already has a roll_note" if existing else "will add roll_note"
            print(f"  {did}: {status}")
            if args.apply and not existing:
                rcol.document(did).set({"roll_note": note}, merge=True)
        if args.apply:
            print("Report notes done (numbers on these docs were not touched).")
        else:
            print("Dry run only -- re-run with --apply --report-notes to write.")


if __name__ == "__main__":
    main()
