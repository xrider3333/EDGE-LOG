# -*- coding: utf-8 -*-
"""RUNBOARD WATCH LIST - how MANAGER and the strategy chats (Claude sessions on this PC) edit the
COMPARE > RUNBOARD watch list without a code ship (owner go via MANAGER 2026-09-26).

The web app reads ONE Firestore doc, users/{uid}/meta/runboard_watch, on COMPARE > RUNBOARD under
the WATCH chip (LANE VERDICT row):

    { "version": 1, "updated_at": "<UTC ISO>", "updated_by": "<chat name>",
      "runs": [ {"id": 382, "family": "NOISE", "lane": "NOISE", "verdict": "LIVE - Webull NOISE leg",
                 "note": "", "added_by": "MANAGER", "added_at": "2026-09-26", "verdict_by": "NOISE",
                 "verdict_at": "2026-09-26"}, ... ] }

Credentials: firebase_admin, serviceAccount.json at the repo root, falling back to
C:\\Users\\xride\\OneDrive\\Desktop\\EDGE-LOG\\serviceAccount.json (same lookup as
tools/family_rename.py / tools/r59_noise_capital_board.py). uid IO0K35JpLIcH9YK4C0pMNYUzZOM2.
Never print, copy or commit the credentials.

    python tools/runboard_watch.py list
    python tools/runboard_watch.py add 382 [383 ...] [--family NOISE] [--lane NOISE]
                                    [--verdict "LIVE - Webull NOISE leg"] [--note "..."] --from MANAGER
    python tools/runboard_watch.py verdict 382 "LIVE - Webull NOISE leg" --from NOISE [--lane NOISE]
    python tools/runboard_watch.py note 382 "keep an eye on the tail" --from NOISE
    python tools/runboard_watch.py remove 382 [383 ...] --from MANAGER
    python tools/runboard_watch.py import seed.json --from MANAGER
    --dry on every write command prints the resulting doc and writes nothing.

`add` is idempotent: only the fields you pass change on a run already on the list; a new run
appends at the end. Each run must already exist in users/{uid}/runs (add refuses an unknown run
unless --force) and, when --family is omitted, its family is read off the run's own famKey. `import`
merges a JSON list of entries with the same shape as `runs` above - meant for seeding; it validates
family/verdict but does not re-check that each run exists (it is expected to carry known-good rows);
an imported verdict without verdict_at is stamped with its lane (else --from) and today's date.

RULES: every write is a read-modify-write inside a Firestore transaction, so two chats appending at
the same moment never stomp each other (falls back to a plain read-then-write against the in-memory
fake client tests/test_runboard_watch.py injects, which has no contention to retry - see _apply).
Every write stamps updated_at (UTC ISO) and updated_by. verdict is at most 80 characters. family
must be in the house vocabulary - CLAUDE.md "Strategy FAMILY names" / tests/test_family_vocabulary.py:
ORB NOISE ENGU-Q ENGU CBU-Q TTM DIP GAPGO TTIBS VWAP REVERT SUPERTREND RSIDIV OVERNIGHT EMAPB REPLAY
RFML BOOK MISC. --from is required on every write (the chat's inbox name, e.g. NOISE, MANAGER) and is
stamped as updated_by / the default added_by / verdict_by. Output is plain text throughout.
"""
import argparse, datetime, json, os, sys

UID = "IO0K35JpLIcH9YK4C0pMNYUzZOM2"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ONE FAMILY VOCABULARY (owner 2026-09-24) - must match CLAUDE.md "Strategy FAMILY names" and
# tests/test_family_vocabulary.py's VOCAB; tests/test_runboard_watch.py cross-checks the two.
FAMILIES = {"ORB", "NOISE", "ENGU-Q", "ENGU", "CBU-Q", "TTM", "DIP", "GAPGO", "TTIBS", "VWAP",
            "REVERT", "SUPERTREND", "RSIDIV", "OVERNIGHT", "EMAPB", "REPLAY", "RFML", "BOOK", "MISC"}
MAX_VERDICT = 80


class ToolError(Exception):
    """A refusal the CLI should report plainly and exit non-zero for, not a traceback."""


# ── Firestore plumbing (real client or an injected fake - see tests/test_runboard_watch.py) ──────
def real_client():
    import firebase_admin
    from firebase_admin import credentials, firestore
    cred = os.path.join(ROOT, "serviceAccount.json")
    if not os.path.exists(cred):
        cred = os.path.join(r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG", "serviceAccount.json")
    if not firebase_admin._apps:
        firebase_admin.initialize_app(credentials.Certificate(cred))
    return firestore.client()


def _user(db):
    return db.collection("users").document(UID)


def watch_ref(db):
    return _user(db).collection("meta").document("runboard_watch")


def run_ref(db, run_id):
    return _user(db).collection("runs").document(str(run_id))


def _read(ref, transaction=None):
    snap = ref.get(transaction=transaction) if transaction is not None else ref.get()
    return snap.to_dict() if getattr(snap, "exists", False) else None


def _get_run_doc(db, run_id):
    return _read(run_ref(db, run_id))


def _apply(db, ref, mutate):
    """Read-modify-write `ref` as one atomic step: mutate(existing_dict_or_None) -> new_dict.

    Against a real firebase_admin client this runs inside a genuine Firestore transaction
    (`db.transaction()` + `firestore.transactional`, the same pattern api/runner.py uses for run
    ids and family counters), which the SDK retries on contention - so two chats appending to the
    watch list at the same moment do a true read-modify-write, never a last-write-wins stomp. The
    in-memory fake client the tests inject (tests/test_runboard_watch.py FakeClient) deliberately
    has no `.transaction()` and therefore no contention to retry, so this falls back to a plain
    get-then-set against it; the merge logic under test - every rule below - runs identically
    either way.
    """
    if hasattr(db, "transaction"):
        from firebase_admin import firestore

        txn = db.transaction()

        @firestore.transactional
        def _txn(t):
            new = mutate(_read(ref, t))
            t.set(ref, new)
            return new

        return _txn(txn)
    new = mutate(_read(ref))
    ref.set(new)
    return new


def _dry_or_apply(db, ref, mutate, dry):
    return mutate(_read(ref)) if dry else _apply(db, ref, mutate)


def _finish(new, dry, msg):
    if dry:
        print(json.dumps(new, indent=2, ensure_ascii=False, sort_keys=False))
        print("--dry: wrote nothing")
    else:
        print(msg)
    return new


# ── small helpers ─────────────────────────────────────────────────────────────────────────────
def _utc_now_iso():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _et_today():
    from zoneinfo import ZoneInfo
    return datetime.datetime.now(ZoneInfo("America/New_York")).date().isoformat()


def _check_family(fam):
    if fam not in FAMILIES:
        raise ToolError(f"family {fam!r} is not in the house vocabulary ({', '.join(sorted(FAMILIES))})")


def _check_verdict(text):
    if len(text) > MAX_VERDICT:
        raise ToolError(f"verdict is {len(text)} chars (max {MAX_VERDICT}): {text!r}")


def _finalize(runs, frm):
    return {"version": 1, "updated_at": _utc_now_iso(), "updated_by": frm, "runs": runs}


def _find(runs, run_id):
    return next((r for r in runs if r.get("id") == run_id), None)


# ── commands ──────────────────────────────────────────────────────────────────────────────────
def cmd_list(db):
    """Print the watch list, one line per run: id, family, verdict, lane, verdict date. 1 read."""
    doc = _read(watch_ref(db))
    if not doc:
        print(f"[RUNBOARD WATCH] users/{UID}/meta/runboard_watch does not exist yet")
        return
    runs = doc.get("runs") or []
    print(f"[RUNBOARD WATCH] {len(runs)} run(s) - updated {doc.get('updated_at', '?')} "
          f"by {doc.get('updated_by', '?')}")
    for r in runs:
        print("  #%-6s %-10s %-44s lane=%-10s verdict_at=%s" % (
            r.get("id"), r.get("family") or "-", (r.get("verdict") or "(no verdict yet)")[:44],
            r.get("lane") or "-", r.get("verdict_at") or "-"))


def cmd_add(db, ids, family, lane, verdict, note, frm, force, dry):
    if family is not None:
        _check_family(family)
    if verdict is not None:
        _check_verdict(verdict)

    already = {r.get("id") for r in (_read(watch_ref(db)) or {}).get("runs", [])}
    resolved = {}
    for rid in ids:
        if rid in already:
            continue   # already tracked: existence/family were vetted when it was first added
        run_doc = _get_run_doc(db, rid)
        if run_doc is None and not force:
            raise ToolError(f"run #{rid}: not found in users/{UID}/runs - pass --force to add it "
                             "anyway (then set --family explicitly)")
        fam = family or (run_doc or {}).get("famKey")
        if not fam:
            raise ToolError(f"run #{rid}: no --family given and the run has no famKey - pass "
                             "--family explicitly")
        _check_family(fam)
        resolved[rid] = fam

    def mutate(cur):
        runs = list((cur or {}).get("runs") or [])
        by_id = {r["id"]: r for r in runs}
        today = _et_today()
        for rid in ids:
            entry = by_id.get(rid)
            if entry is None:
                fam = family if family is not None else resolved.get(rid)
                if fam is None:
                    # a concurrent add resolved this id between our pre-check and this attempt
                    raise ToolError(f"run #{rid}: could not resolve a family inside the "
                                     "transaction - re-run add")
                entry = {"id": rid, "family": fam, "lane": lane or "", "verdict": "",
                         "note": note or "", "added_by": frm, "added_at": today}
                if verdict is not None:
                    entry["verdict"] = verdict
                    entry["verdict_by"] = lane or frm
                    entry["verdict_at"] = today
                runs.append(entry)
                by_id[rid] = entry
            else:
                if family is not None:
                    entry["family"] = family
                if lane is not None:
                    entry["lane"] = lane
                if note is not None:
                    entry["note"] = note
                if verdict is not None:
                    entry["verdict"] = verdict
                    entry["verdict_by"] = lane or frm
                    entry["verdict_at"] = today
        return _finalize(runs, frm)

    new = _dry_or_apply(db, watch_ref(db), mutate, dry)
    return _finish(new, dry, f"add: {len(ids)} id(s) processed by {frm}: {ids}")


def cmd_verdict(db, run_id, text, frm, lane, dry):
    _check_verdict(text)
    today = _et_today()

    def mutate(cur):
        runs = list((cur or {}).get("runs") or [])
        entry = _find(runs, run_id)
        if entry is None:
            raise ToolError(f"run #{run_id} is not on the watch list yet - add it first")
        entry["verdict"] = text
        entry["verdict_by"] = lane or frm
        entry["verdict_at"] = today
        return _finalize(runs, frm)

    new = _dry_or_apply(db, watch_ref(db), mutate, dry)
    return _finish(new, dry, f"verdict: #{run_id} set by {lane or frm}: {text!r}")


def cmd_note(db, run_id, text, frm, dry):
    def mutate(cur):
        runs = list((cur or {}).get("runs") or [])
        entry = _find(runs, run_id)
        if entry is None:
            raise ToolError(f"run #{run_id} is not on the watch list yet - add it first")
        entry["note"] = text
        return _finalize(runs, frm)

    new = _dry_or_apply(db, watch_ref(db), mutate, dry)
    return _finish(new, dry, f"note: #{run_id} set by {frm}: {text!r}")


def cmd_remove(db, ids, frm, dry):
    idset = set(ids)

    def mutate(cur):
        runs = list((cur or {}).get("runs") or [])
        missing = idset - {r.get("id") for r in runs}
        if missing:
            print("note: not on the watch list, nothing to remove: %s" %
                  ", ".join(str(m) for m in sorted(missing)))
        kept = [r for r in runs if r.get("id") not in idset]
        return _finalize(kept, frm)

    new = _dry_or_apply(db, watch_ref(db), mutate, dry)
    return _finish(new, dry, f"remove: {len(ids)} id(s) processed by {frm}: {ids}")


def cmd_import(db, path, frm, dry):
    with open(path, encoding="utf-8") as f:
        entries = json.load(f)
    if not isinstance(entries, list):
        raise ToolError("import file must contain a JSON list of entries")
    norm = []
    for e in entries:
        if "id" not in e:
            raise ToolError(f"import entry missing id: {e!r}")
        e = dict(e)
        e["id"] = int(e["id"])
        if e.get("family"):
            _check_family(e["family"])
        if e.get("verdict"):
            _check_verdict(e["verdict"])
        norm.append(e)

    def mutate(cur):
        runs = list((cur or {}).get("runs") or [])
        by_id = {r["id"]: r for r in runs}
        today = _et_today()
        for e in norm:
            rid = e["id"]
            # a verdict is never saved without who set it and when (same rule as add / verdict):
            #   an imported verdict that carries neither is stamped with its lane (else --from) and today
            if e.get("verdict") and not e.get("verdict_at"):
                e = dict(e, verdict_by=e.get("verdict_by") or e.get("lane") or frm, verdict_at=today)
            if rid in by_id:
                by_id[rid].update(e)
            else:
                if not e.get("family"):
                    raise ToolError(f"import entry #{rid}: missing family (new entries need one)")
                entry = {"id": rid, "family": e.get("family"), "lane": e.get("lane") or "",
                         "verdict": e.get("verdict") or "", "note": e.get("note") or "",
                         "added_by": e.get("added_by") or frm, "added_at": e.get("added_at") or today}
                entry.update(e)
                runs.append(entry)
                by_id[rid] = entry
        return _finalize(runs, frm)

    new = _dry_or_apply(db, watch_ref(db), mutate, dry)
    return _finish(new, dry, f"import: {len(norm)} entrie(s) from {path} merged by {frm}")


# ── CLI ───────────────────────────────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list")

    a = sub.add_parser("add")
    a.add_argument("ids", nargs="+", type=int)
    a.add_argument("--family")
    a.add_argument("--lane")
    a.add_argument("--verdict")
    a.add_argument("--note")
    a.add_argument("--from", dest="frm", required=True)
    a.add_argument("--force", action="store_true")
    a.add_argument("--dry", action="store_true")

    v = sub.add_parser("verdict")
    v.add_argument("id", type=int)
    v.add_argument("text")
    v.add_argument("--from", dest="frm", required=True)
    v.add_argument("--lane")
    v.add_argument("--dry", action="store_true")

    n = sub.add_parser("note")
    n.add_argument("id", type=int)
    n.add_argument("text")
    n.add_argument("--from", dest="frm", required=True)
    n.add_argument("--dry", action="store_true")

    r = sub.add_parser("remove")
    r.add_argument("ids", nargs="+", type=int)
    r.add_argument("--from", dest="frm", required=True)
    r.add_argument("--dry", action="store_true")

    i = sub.add_parser("import")
    i.add_argument("file")
    i.add_argument("--from", dest="frm", required=True)
    i.add_argument("--dry", action="store_true")

    args = ap.parse_args()
    # a Windows console is cp1252: a verdict with an arrow or any character outside it would
    #   crash print() (the runner's own check-mark crash) - print a ? for it instead
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(errors="replace")
        except Exception:
            pass
    db = real_client()
    try:
        if args.cmd == "list":
            cmd_list(db)
        elif args.cmd == "add":
            cmd_add(db, args.ids, args.family, args.lane, args.verdict, args.note, args.frm,
                    args.force, args.dry)
        elif args.cmd == "verdict":
            cmd_verdict(db, args.id, args.text, args.frm, args.lane, args.dry)
        elif args.cmd == "note":
            cmd_note(db, args.id, args.text, args.frm, args.dry)
        elif args.cmd == "remove":
            cmd_remove(db, args.ids, args.frm, args.dry)
        elif args.cmd == "import":
            cmd_import(db, args.file, args.frm, args.dry)
        code = 0
    except ToolError as e:
        print(f"error: {e}", file=sys.stderr)
        code = 1
    # every write above is already committed (the SDK returns only after the commit), so leave
    #   now: on Windows the gRPC channel's own shutdown wait otherwise holds the process open for
    #   a minute or more after the work is done, which timed out a chained add + list.
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(code)


if __name__ == "__main__":
    main()
