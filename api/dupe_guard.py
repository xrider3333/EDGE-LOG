"""
dupe_guard - notice when a backtest/validate job repeats work that is already finished.

WHY THIS EXISTS
---------------
On 2026-08-18 five pinned NOISE variant validate jobs were queued by one session that
then died. A second session checked the queue, saw only status=='queued'/'running' docs,
concluded none of its configs were in flight, and re-queued four of them. Four ~18-minute
validates ran a second time and produced bit-identical figures. The dedupe check of the
day looked ONLY at in-flight jobs and never at finished ones.

The fix: fingerprint the WORK a job describes, and compare that fingerprint against
ALREADY-COMPLETED jobs as well as in-flight ones.

WHAT COUNTS AS "THE SAME WORK"
------------------------------
MATERIAL_FIELDS below is an explicit allowlist, not a denylist, and that is deliberate.
A denylist would fold every future cosmetic field into the fingerprint and quietly stop
detecting real duplicates. The allowlist names exactly the inputs that determine the
numbers a job produces:

  * which code ran   -> type, strategy, kind
  * over which bars  -> date_from, date_to, instrument, timeframe, source, session
  * priced how       -> mult, cost_pts, commission_usd, slippage_pts
  * searched how     -> preset, discover, n_trials, n_rounds, wf_folds, wf_mode,
                        lockbox_months, lockbox, min_trades, transfer_to, dsr, oos,
                        top_n, grid, params, ml_filter, ml_threshold, sizing,
                        book_legs, run_id

Deliberately EXCLUDED, because two jobs differing only in these compute the same thing:
  note (free text - the four real duplicates carried DIFFERENT notes), provider, workers,
  equity_points, mc_sims, pills, status, progress, control, result, error, createdAt,
  finishedAt, elapsed_s, claimedBy, uid, id, and every repeat-tracking field this module
  writes.

Values are normalised before hashing so that 20 and 20.0, "" and None, and dict key order
never read as a difference.

WHAT IT DOES NOT DO
-------------------
It never blocks a job. Reruns are legitimate - confirming reproducibility, or running the
same configuration against newer data. The guard's job is to make the repeat IMPOSSIBLE TO
MISS, and to record the link so Past Runs and the STUDIES board can say "repeat of run N"
without anyone having to spot it by eye.
"""

import hashlib
import json
import time

MATERIAL_FIELDS = (
    "type", "strategy", "kind",
    "date_from", "date_to", "instrument", "timeframe", "source", "session",
    "mult", "cost_pts", "commission_usd", "slippage_pts",
    "preset", "discover", "n_trials", "n_rounds", "wf_folds", "wf_mode",
    "lockbox_months", "lockbox", "min_trades", "transfer_to", "dsr", "oos", "top_n",
    "grid", "params", "ml_filter", "ml_threshold", "sizing", "book_legs", "run_id",
)

# Fields this module writes onto job docs. Never part of a fingerprint.
REPEAT_FIELDS = ("repeat_of", "repeat_of_run", "repeat_of_at", "fingerprint", "run_id")


def _norm(v):
    """Normalise a value so cosmetic representation differences never read as a change."""
    if v is None or v == "":
        return None
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        f = float(v)
        return 0.0 if f == 0 else f
    if isinstance(v, dict):
        out = {}
        for k in sorted(v.keys()):
            nv = _norm(v[k])
            if nv is not None:
                out[str(k)] = nv
        return out or None
    if isinstance(v, (list, tuple)):
        out = [_norm(x) for x in v]
        return out or None
    return str(v)


def material_view(job):
    """The subset of a job doc that determines its numbers, normalised."""
    view = {}
    for f in MATERIAL_FIELDS:
        nv = _norm((job or {}).get(f))
        if nv is not None:
            view[f] = nv
    return view


def job_fingerprint(job):
    """A stable 16-char hex digest of the work a job describes."""
    blob = json.dumps(material_view(job), sort_keys=True, separators=(",", ":"),
                      default=str)
    return hashlib.sha1(blob.encode("utf-8")).hexdigest()[:16]


def explain_difference(job_a, job_b):
    """Every material field on which two jobs disagree, as {field: (a, b)}.
    An empty dict means they are the same work."""
    a, b = material_view(job_a), material_view(job_b)
    diff = {}
    for f in set(a) | set(b):
        if a.get(f) != b.get(f):
            diff[f] = (a.get(f), b.get(f))
    return diff


def _finished_at(job):
    v = (job or {}).get("finishedAt")
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _when(job):
    ts = _finished_at(job)
    if ts:
        return time.strftime("%Y-%m-%d %H:%M", time.localtime(ts))
    created = (job or {}).get("createdAt")
    try:
        return created.strftime("%Y-%m-%d %H:%M")
    except Exception:
        return "an earlier date"


def scan_for_duplicate(candidate, prior_jobs, exclude_ids=()):
    """Core matcher, free of any Firestore dependency so it can be exercised offline.

    `candidate` is the job about to run. `prior_jobs` is an iterable of (doc_id, job_dict)
    for OTHER jobs - completed ones as well as in-flight ones. Returns the match dict for
    the EARLIEST matching completed job (the canonical original), or None.
    """
    fp = job_fingerprint(candidate)
    exclude = set(str(x) for x in exclude_ids)
    hits = []
    for doc_id, job in prior_jobs:
        if str(doc_id) in exclude:
            continue
        job = job or {}
        status = str(job.get("status") or "").lower()
        # An errored or cancelled job produced no numbers, so repeating one is not a
        # duplicate - it is a retry, which is exactly what the owner would want.
        if status not in ("done", "queued", "running", "paused"):
            continue
        if job_fingerprint(job) != fp:
            continue
        hits.append((doc_id, job, status))
    if not hits:
        return None
    done = [h for h in hits if h[2] == "done"]
    pool = done or hits
    pool.sort(key=lambda h: _finished_at(h[1]) or float("inf"))
    doc_id, job, status = pool[0]
    return {
        "fingerprint": fp,
        "job_id": doc_id,
        "status": status,
        "run_id": job.get("run_id"),
        "when": _when(job),
        # the raw finish time travels with the match: resolve_run_id needs it to pick the
        # run that was saved moments after this job, and _when() has already lost it.
        "finishedAt": _finished_at(job),
        "strategy": job.get("strategy"),
        "date_from": job.get("date_from"),
        "date_to": job.get("date_to"),
        "source": job.get("source"),
        "n_matches": len(hits),
    }


def resolve_run_id(match, runs_lookup):
    """Best-effort answer to which RUN NUMBER that earlier job became.

    Jobs finished before this guard shipped carry no run_id, so fall back to the run whose
    strategy, window and source match and whose save time is closest AFTER the job finished.
    """
    if match.get("run_id"):
        return match["run_id"]
    want = (str(match.get("strategy") or ""), str(match.get("date_from") or ""),
            str(match.get("source") or ""))
    best, best_gap = None, None
    for rid, run in runs_lookup:
        run = run or {}
        got = (str(run.get("strategy") or ""), str(run.get("date_from") or ""),
               str(run.get("data_source") or ""))
        if got != want:
            continue
        try:
            saved = time.mktime(time.strptime(str(run.get("timestamp")), "%Y-%m-%d %H:%M"))
        except Exception:
            continue
        gap = saved - _finished_at(match)
        if -60 <= gap <= 3600 and (best_gap is None or gap < best_gap):
            best, best_gap = rid, gap
    return best


def describe(match, run_id=None):
    """The one-line, plain-English sentence the runner logs and the web app shows."""
    rid = run_id or match.get("run_id")
    who = ("run #%s" % rid) if rid else ("job %s" % str(match.get("job_id"))[:8])
    if match.get("status") == "done":
        return ("This is a REPEAT of %s, which already finished this exact configuration "
                "on %s. Same strategy file, same date window, same data source and the "
                "same search settings." % (who, match.get("when")))
    return ("This duplicates %s, which is already %s with this exact configuration."
            % (who, match.get("status")))


def find_duplicate(db, uid, candidate, exclude_ids=(), collection="backtests",
                   scan_limit=400):
    """Look through the user's own backtest jobs - COMPLETED ones included, which is the
    whole point - for one that computes the same thing as `candidate`.

    Returns (match, run_id) or (None, None). Every failure is swallowed: a guard that can
    break a backtest is worse than the duplicate it prevents.
    """
    prior = None
    try:
        col = db.collection("users").document(uid).collection(collection)
        prior = [(s.id, s.to_dict() or {})
                 for s in col.order_by("createdAt", direction="DESCENDING")
                 .limit(scan_limit).stream()]
    except Exception:
        try:
            col = db.collection("users").document(uid).collection(collection)
            prior = [(s.id, s.to_dict() or {}) for s in col.limit(scan_limit).stream()]
        except Exception:
            return None, None
    match = scan_for_duplicate(candidate, prior, exclude_ids=exclude_ids)
    if not match:
        return None, None
    run_id = None
    try:
        runs = db.collection("users").document(uid).collection("runs")
        run_id = resolve_run_id(match, [(s.id, s.to_dict() or {})
                                        for s in runs.limit(600).stream()])
    except Exception:
        pass
    return match, run_id
