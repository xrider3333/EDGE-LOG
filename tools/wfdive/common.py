"""wfdive shared helpers (2026-09-16 research deep dive: WF vs lockbox validation).

Every wfdive script imports this module first. It centralizes:
  - fs_client()      read-only firebase_admin client (serviceAccount.json from the
                      SHARED checkout; this worktree has no credential of its own).
  - setup_data_env() points augur_engine.data / augur_engine.paths at the SHARED
                      checkout's augur_uploads/ + optimizer_history.db, exactly the
                      way tools/backfill_wf_oos.py's main() does it, so
                      augur_engine.data.find_master()/load_master_arrays() work when
                      this code runs from the worktree (a worktree's own
                      optimizer_history.db is untracked -- see "Worktree registry
                      trap" in memory).
  - low_priority()   drop this process below normal priority (owner: the live
                      trading fleet runs on this box during market hours).
  - cpu_lock(name)   a single exclusive-lock file so at most one heavy replay (a
                      real backtest, not a Firestore read) runs across every agent
                      in this research session.
  - family_key(doc)  a stable "same strategy, re-validated" grouping key, so
                      analysis never treats N re-runs of one file as N independent
                      votes (memory: "Runs cluster by FAMILY").
  - load_runs()      loads the Gather agent's saved _wfdive_data/runs.json.

Run every script from THIS worktree
(C:/Users/xride/AppData/Local/EdgeLog-worktrees/wfdive) so `import augur_engine`
resolves to the worktree copy (identical code to main) -- setup_data_env() then
redirects only the DATA paths (uploads dir + sqlite registry) to the shared
checkout, the same split tools/backfill_wf_oos.py's main() already relies on.
"""
import contextlib
import os
import re
import sys
import time

# ── paths ────────────────────────────────────────────────────────────────────
WORKTREE_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SHARED_ROOT = os.path.expanduser(r"~\OneDrive\Desktop\EDGE-LOG")
DATA_DIR = os.path.join(WORKTREE_ROOT, "_wfdive_data")
LOCK_PATH = os.path.join(DATA_DIR, "cpu.lock")

UID = "IO0K35JpLIcH9YK4C0pMNYUzZOM2"

if WORKTREE_ROOT not in sys.path:
    sys.path.insert(0, WORKTREE_ROOT)


def _ensure_data_dir():
    os.makedirs(DATA_DIR, exist_ok=True)


# ── Firestore (READ-ONLY for this research session — never write/delete) ─────
def fs_client():
    """A firebase_admin Firestore client, initialized once per process.

    serviceAccount.json lives in the SHARED checkout (gitignored, so a worktree
    never has its own copy) — checked there first, then this worktree, matching
    tools/backfill_wf_oos.py's _db() lookup order (it checks its own ROOT first,
    then the shared OneDrive path; we check shared first since that's the only
    place it has ever actually been found on this box).
    """
    import firebase_admin
    from firebase_admin import credentials, firestore

    cred_path = next(
        (p for p in (
            os.path.join(SHARED_ROOT, "serviceAccount.json"),
            os.path.join(WORKTREE_ROOT, "serviceAccount.json"),
        ) if os.path.isfile(p)),
        None,
    )
    if not cred_path:
        raise SystemExit(
            "serviceAccount.json not found (checked shared checkout and this worktree)"
        )
    if not firebase_admin._apps:
        firebase_admin.initialize_app(credentials.Certificate(cred_path))
    return firestore.client()


def runs_collection(db=None):
    """users/<uid>/runs collection ref (the run docs this whole dive reads)."""
    db = db or fs_client()
    return db.collection("users").document(UID).collection("runs")


# ── data env: masters + registry live in the SHARED checkout ─────────────────
def setup_data_env(verbose=True):
    """Point augur_engine.data / augur_engine.paths at the shared checkout's
    augur_uploads/ (master CSVs) and optimizer_history.db (master registry),
    exactly the override tools/backfill_wf_oos.py's main() applies via
    EDGELOG_UPLOADS / EDGELOG_DB_PATH:

        if os.environ.get("EDGELOG_UPLOADS"):
            _data.UPLOADS = os.environ["EDGELOG_UPLOADS"]
        if os.environ.get("EDGELOG_DB_PATH"):
            _paths.DB_PATH = _data.DB_PATH = os.environ["EDGELOG_DB_PATH"]

    A worktree's own augur_uploads/ and optimizer_history.db do not exist (the
    registry is an untracked local sqlite file — "Worktree registry trap" in
    memory), so augur_engine.data.find_master() returns None until this runs.
    This sets the env vars AND applies the module overrides directly (import
    order between a script and this helper is otherwise fragile), then verifies
    find_master() resolves NQ 5m rth as a smoke test. Idempotent — safe to call
    more than once per process.
    """
    uploads = os.path.join(SHARED_ROOT, "augur_uploads")
    db_path = os.path.join(SHARED_ROOT, "optimizer_history.db")
    if not os.path.isdir(uploads):
        raise SystemExit(f"shared augur_uploads not found at {uploads}")
    if not os.path.isfile(db_path):
        raise SystemExit(f"shared optimizer_history.db not found at {db_path}")

    os.environ["EDGELOG_UPLOADS"] = uploads
    os.environ["EDGELOG_DB_PATH"] = db_path

    import augur_engine.data as _data
    import augur_engine.paths as _paths

    _data.UPLOADS = uploads
    _paths.DB_PATH = db_path
    _data.DB_PATH = db_path

    master = _data.find_master("NQ", "5m", "rth", "db_noadj_rth")
    if verbose:
        if master:
            print(f"[wfdive.common] setup_data_env OK: NQ 5m rth -> "
                  f"{master.get('filename')} ({master.get('date_from')}..{master.get('date_to')})")
        else:
            print("[wfdive.common] setup_data_env WARNING: find_master('NQ','5m','rth',"
                  "'db_noadj_rth') returned None — check source string against "
                  "list_masters()")
    return master


# ── process courtesy: the live trading fleet runs on this box during market hours ──
def low_priority():
    """Lower this process's OS scheduling priority so a research script never
    competes with the live runner/paper-trading fleet for CPU. Uses psutil when
    available (BELOW_NORMAL_PRIORITY_CLASS on Windows); a no-op with a printed
    note otherwise — never raises, since a research probe must not fail just
    because priority couldn't be lowered."""
    try:
        import psutil
    except ImportError:
        print("[wfdive.common] low_priority: psutil not importable — running at "
              "normal priority (no-op)")
        return False
    try:
        p = psutil.Process()
        if hasattr(psutil, "BELOW_NORMAL_PRIORITY_CLASS"):
            p.nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)
        else:
            p.nice(10)  # POSIX: 0 default, 19 lowest: a mild, safe deprioritization
        print(f"[wfdive.common] low_priority: set (pid {p.pid})")
        return True
    except Exception as e:
        print(f"[wfdive.common] low_priority FAILED ({type(e).__name__}: {e}) — "
              "continuing at normal priority")
        return False


# ── one heavy replay at a time, across every agent in this session ───────────
STALE_SECONDS = 90 * 60  # 90 minutes


@contextlib.contextmanager
def cpu_lock(name, poll_s=5, stale_s=STALE_SECONDS):
    """Exclusive lock so only ONE heavy replay (a real backtest — NOT a Firestore
    read, NOT rebuild_plan's pure bookkeeping) runs at a time across every wfdive
    agent. Backed by a plain lock FILE (os.O_CREAT|O_EXCL — atomic create-if-
    absent, portable, no extra dependency), not an OS file lock, so it also works
    across separate processes/agents sharing this one worktree directory.

    Usage:
        with cpu_lock("gate #257 replay"):
            ... run_backtest / run_validate ...

    - Polls every `poll_s` seconds until the lock file can be created.
    - A lock file older than `stale_s` (default 90 min) is treated as abandoned
      (a crashed holder) and removed so this call can proceed — printed loudly
      so a human notices if it happens.
    - The file's contents are "<holder name> @ <epoch time>" for diagnosis.
    - Always removed on exit (success or exception).
    """
    _ensure_data_dir()
    holder = f"{name} (pid {os.getpid()})"
    acquired = False
    waited = 0.0
    while not acquired:
        try:
            fd = os.open(LOCK_PATH, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            with os.fdopen(fd, "w") as f:
                f.write(f"{holder} @ {time.time()}\n")
            acquired = True
            break
        except FileExistsError:
            pass
        # someone else holds it (or a stale lock) — check staleness
        try:
            age = time.time() - os.path.getmtime(LOCK_PATH)
        except OSError:
            age = None  # lock disappeared between the failed create and this stat
        if age is not None and age > stale_s:
            try:
                with open(LOCK_PATH, "r") as f:
                    stale_holder = f.read().strip()
            except OSError:
                stale_holder = "<unreadable>"
            print(f"[wfdive.common] cpu_lock: STALE lock ({age:.0f}s old, held by "
                  f"{stale_holder!r}) — removing and retrying")
            try:
                os.remove(LOCK_PATH)
            except OSError:
                pass
            continue
        if waited == 0.0:
            print(f"[wfdive.common] cpu_lock: waiting for {LOCK_PATH} "
                  f"(held by another replay) ...")
        time.sleep(poll_s)
        waited += poll_s
    try:
        if waited:
            print(f"[wfdive.common] cpu_lock: acquired after {waited:.0f}s wait ({holder})")
        else:
            print(f"[wfdive.common] cpu_lock: acquired ({holder})")
        yield
    finally:
        try:
            os.remove(LOCK_PATH)
        except OSError:
            pass


# ── family clustering: "one strategy file, re-validated many times" ──────────
# Strips a trailing "this is a re-save of the same file" marker off a strategy
# file stem so e.g. "engu_q_r2.py", "engu_q_r2_v3.py", "engu_q_r2_fixed.py" all
# collapse to one family. Rule (documented, not guessed): drop the extension,
# then strip UNAMBIGUOUS re-save markers only:
#   _v###                        (explicit version tag: _v2, _v10)
#   _final / _fixed / _fix### / _tweak(ed) / _copy### / _new / _old / _test###
#   a trailing date stamp _YYYYMMDD or -YYYYMMDD
# then lowercases and combines with instrument + timeframe (a family is
# strategy-code + market, not strategy-code alone — the same file validated on
# NQ vs ES is a different question).
#
# Deliberately NOT stripped: a bare trailing "_<digits>" (e.g. "_1", "_2", "_3",
# "_5") or an "_r<digits>" tag (e.g. "_r2".."_r5"). Those are load-bearing parts
# of real strategy identities on this project — "orb_3_1" (ORB version 3.1) vs
# "orb_2_5" are DIFFERENT algorithms, not two saves of one file, and ENGU-Q's
# R2/R3/R4/R5 are separately-tracked variants (memory: "validate-gap audit
# 09-14 — top: R2>R5>R4>#309>R3"), not version bumps of a single family. A
# generic digit-strip would silently MERGE those distinct families — the
# opposite failure from the one this function exists to prevent — so
# under-splitting (treating orb_3_1 and orb_3_0 as different families when
# they're actually the same file re-saved) is accepted as the safer error over
# over-merging genuinely different strategies. Callers who spot a real re-save
# pair this misses should extend the explicit marker list above, not add a
# digit-strip rule.
_VER_SUFFIXES = re.compile(
    r"(_v\d+|_final|_fixed|_fix\d*|_tweaked?|_copy\d*|_new|_old|_test\d*"
    r"|_\d{8}|-\d{8})$",
    re.IGNORECASE,
)


def family_key(doc):
    """Stable family id for a run doc: (strategy-file-stem-with-version-suffixes-
    stripped, instrument, timeframe). Two runs share a family_key iff they are
    the same strategy code (modulo a version/variant suffix) validated on the
    same instrument + timeframe — the unit memory's "runs cluster by FAMILY"
    rule says to dedupe/cluster-bootstrap on, never count as independent votes.

    Books (job type "book" / doc.get("book") not None) still get a family_key
    (their strategy field is the book NAME, not a file) so they can be grouped
    too, but callers should EXCLUDE books from WF/lockbox analysis regardless
    (memory: "#366 is a BOOK — exclude books from WF analysis", books pool legs
    and have no walk-forward folds).
    """
    strat = str(doc.get("strategy") or "unknown")
    stem = re.sub(r"\.py$", "", strat, flags=re.IGNORECASE)
    # strip at most one trailing version-ish suffix, repeated up to 2x to catch
    # e.g. "_v2_final" (two stacked suffixes) without over-stripping a file whose
    # real name legitimately ends in digits that are NOT a revision tag (we only
    # strip once more if the FIRST strip actually matched).
    prev = stem
    for _ in range(2):
        nxt = _VER_SUFFIXES.sub("", prev)
        if nxt == prev or not nxt:
            break
        prev = nxt
    stem = prev.lower()
    inst = str(doc.get("instrument") or "").upper()
    tf = str(doc.get("timeframe") or "").lower()
    return f"{stem}|{inst}|{tf}"


# ── loading the Gather agent's saved data ─────────────────────────────────────
def load_runs(path=None):
    """Load _wfdive_data/runs.json (list of run-doc dicts, each carrying its
    Firestore doc id under "id"). Every downstream analysis script reads THIS
    file, never Firestore directly (Firestore reads are Gather-only, per the
    hard constraint that the daily quota is shared with the live app)."""
    import json

    path = path or os.path.join(DATA_DIR, "runs.json")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


if __name__ == "__main__":
    # Smoke test: `python tools/wfdive/common.py` from the worktree root.
    low_priority()
    setup_data_env()
    print("UID:", UID)
    print("DATA_DIR:", DATA_DIR)
    print("family_key smoke test:")
    for d in (
        {"strategy": "engu_q_r2.py", "instrument": "NQ", "timeframe": "1m"},
        {"strategy": "engu_q_r2_v3.py", "instrument": "NQ", "timeframe": "1m"},
        {"strategy": "orb_3_1.py", "instrument": "NQ", "timeframe": "5m"},
        {"strategy": "orb_3_1_final.py", "instrument": "NQ", "timeframe": "5m"},
        {"strategy": "orb_2_5.py", "instrument": "NQ", "timeframe": "5m"},
    ):
        print(f"  {d['strategy']:24s} -> {family_key(d)}")
