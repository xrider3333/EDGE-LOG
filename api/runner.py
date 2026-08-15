"""Local job runner — bridges a job queue to augur_engine. Compute stays on THIS PC.

The web frontend (EDGELOG) enqueues a backtest job; this runner (running on your
machine) picks it up, runs the engine against your local data, and writes the result
back. Two queue backends:

  • LocalQueue (default, no credentials) — watches augur_jobs/*.json. Lets you test
    the full enqueue -> engine -> result flow with zero setup.
  • FirestoreQueue — polls a Firestore 'backtests' collection for status=='queued'
    docs and writes results back. Needs a Firebase service-account key (download from
    the Firebase console; pass --cred path or set GOOGLE_APPLICATION_CREDENTIALS).
    THE AUTH GATE: it only runs jobs whose `uid` is in --allow-uid, so a random web
    visitor can't trigger code on your PC.

Run:  python -m api.runner                         # local test mode, one pass
      python -m api.runner --watch                 # local, keep polling
      python -m api.runner --firestore --cred sa.json --allow-uid <your-firebase-uid>

Job doc fields (in):  strategy, instrument, timeframe, session, source, params,
                      cost_pts, return_trades, status='queued'[, uid]
Result fields (out):  status='done'|'error', result{...}|error, finishedAt
"""
import os
import sys
import json
import time
import glob
import argparse
import threading

import augur_engine as ae
from augur_engine import trial_cache as TC
from .util import json_safe
try:
    from . import paper as _paper
except Exception as _e:
    _paper = None
    print(f"[paper] import skipped: {type(_e).__name__}: {_e}")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JOBS_DIR = os.path.join(ROOT, "augur_jobs")

# Safety-backstop cadence for the Firestore queue listener (item #36, listener
# conversion): even with on_snapshot listeners live, re-run the plain queued-docs
# poll this often in case the watch channel wedges silently (this has happened
# before on the web client side — see MEMORY "EDGELOG cmd-channel lessons").
LISTENER_BACKSTOP_SEC = 600.0
# How often the data-freshness watchdog republishes meta/data_health (api/data_health.py).
HEALTH_SEC = 3600.0
# How often the NinjaTrader bridge watchdog republishes meta/nt_bridge (api/nt_bridge_pub.py).
BRIDGE_SEC = 300.0

# Commands the parallel CommandThread (see below) is allowed to serve WHILE a backtest
# job is running in the main loop. Only cheap/pure reads — reconcile (re-runs the engine)
# and the Library file-ops (process_command) can mutate or be heavy, so they stay on the
# main loop as before. FirestoreQueue.run_commands() skips any queued doc whose action is
# in this set so the two loops never race to claim the same doc.
# similar_setups is CPU-heavy (a chunked NxN-ish correlation pass over thousands of
# trades) but still a pure read — no engine job state touched — so it belongs here too,
# same as get_bars/get_blotter: served in parallel, never queued behind a running job.
# config_trades (api/configs.py) is the same shape again — one champion re-run + a gate
# scoring pass, no engine job state touched — the per-trade GATE/TILT/HYBRID blotter.
READONLY_ACTIONS = {"get_bars", "get_blotter", "similar_setups", "config_trades"}

# ── Firestore doc/batch size guard ──────────────────────────────────────────
# Triggered by a real production failure (2026-08-13): job doc
# 'backtests/g2iIT39Xnfuxcc69keQw' was 1,114,777 bytes -- over Firestore's hard
# 1,048,576-byte-per-document cap -- so the write at run_once()'s ref.update(patch)
# raised, the exception was swallowed by the "[queue] skipped" catch-all, and the
# job was left stuck on status='running' forever with its result never saved. A
# batched startup sync separately blew Firestore's 10 MiB per-request batch cap
# ("[sync-runs] startup skipped ... 11,534,336 bytes"). shrink_to_fit() below is
# applied to both single-doc save paths (the job doc in FirestoreQueue.run_once and
# the Runs-history doc in FirestoreQueue._persist_run); sync_runs additionally
# chunks its batch by bytes, not just doc count.
FIRESTORE_DOC_LIMIT = 1_048_576
DOC_SIZE_BUDGET = 950_000        # ~10% margin below the hard 1 MiB cap
BATCH_BYTE_BUDGET = 9_000_000    # margin below the hard 10 MiB batch-commit cap

# Field names that hold long per-bar/per-config arrays -- found anywhere in a result
# doc, at any nesting depth -- and are safe to downsample before anything else, since
# a big Auto-Validate/Book/grid result is almost entirely made of these.
_CURVE_KEYS = ("equity", "equity_top", "win_dist", "win_dist_wf", "win_dist_lb",
               "wf_alt_folds")
# Per-config population arrays: capped to the top-N configs by PnL/score (stage 2).
_POPULATION_KEYS = ("dist", "points", "top", "top10_results", "equity_top")
# Substrings of top-level keys that are NEVER trimmed by any stage -- champion
# stats/curves + WF/lockbox numbers are what a saved run is judged by.
_PROTECTED_KEY_HINTS = (
    "best", "champ", "validate", "lockbox", "book", "wf_", "wfe",
    "id", "timestamp", "strategy", "instrument", "timeframe", "scope", "status",
    "finishedAt", "elapsed_s", "error", "n_combos", "n_valid", "n_evaluated",
    "days_in_test", "dsr", "mc", "cache_reuse", "data_source", "source_name",
    "famKey", "famSeq",
)


def _is_protected_key(k) -> bool:
    kl = str(k).lower()
    return any(h in kl for h in _PROTECTED_KEY_HINTS)


def _doc_size(doc) -> int:
    """Proxy for the Firestore-encoded size of `doc`. json.dumps length isn't byte-
    identical to Firestore's wire encoding but tracks it closely enough that the
    margin baked into DOC_SIZE_BUDGET/BATCH_BYTE_BUDGET covers the drift."""
    try:
        return len(json.dumps(doc, default=str))
    except Exception:
        return 0


def _downsample_list(lst, cap):
    """Even-index stride down to <= cap elements, always keeping the first and last
    (same shape as augur_engine.history._downsample_equity, generalized to any list)."""
    if not isinstance(lst, list) or len(lst) <= cap or cap < 2:
        return lst
    step = len(lst) / (cap - 1)
    idx = sorted({min(len(lst) - 1, round(i * step)) for i in range(cap - 1)} | {len(lst) - 1})
    return [lst[i] for i in idx]


def _walk_shrink_curves(node, cap, hits):
    """Recursively downsample any _CURVE_KEYS array (or list-of-curves, e.g.
    equity_top) found at any depth to <= cap points. Mutates `node` in place."""
    if isinstance(node, dict):
        for k, v in node.items():
            if k in _CURVE_KEYS and isinstance(v, list):
                if v and isinstance(v[0], list):   # list of curves
                    node[k] = [_downsample_list(c, cap) if isinstance(c, list) else c for c in v]
                else:
                    before = len(v)
                    node[k] = _downsample_list(v, cap)
                    if len(node[k]) != before:
                        hits.append((k, before, len(node[k])))
            else:
                _walk_shrink_curves(v, cap, hits)
    elif isinstance(node, list):
        for item in node:
            _walk_shrink_curves(item, cap, hits)


def _population_rank_key(cfg):
    if isinstance(cfg, dict):
        for k in ("total_pnl", "pnl", "score", "net_pnl"):
            if k in cfg:
                try:
                    return float(cfg[k] or 0)
                except Exception:
                    return 0.0
    return 0.0


def _cap_population(node, n, hits):
    """Truncate any _POPULATION_KEYS list-of-configs, anywhere in the tree, to its
    top `n` entries by PnL/score. Mutates `node` in place."""
    if isinstance(node, dict):
        for k, v in node.items():
            if k in _POPULATION_KEYS and isinstance(v, list) and len(v) > n:
                before = len(v)
                try:
                    v = sorted(v, key=_population_rank_key, reverse=True)
                except Exception:
                    pass
                node[k] = v[:n]
                hits.append((k, before, n))
            else:
                _cap_population(v, n, hits)
    elif isinstance(node, list):
        for item in node:
            _cap_population(item, n, hits)


def shrink_to_fit(doc, budget=DOC_SIZE_BUDGET, log=print, label="doc", equity_points=400):
    """Shrink a result/run doc that would blow Firestore's 1 MiB per-document limit,
    in defined stages, cheapest/least-destructive first. Champion stats + WF/lockbox
    numbers (anything matching _PROTECTED_KEY_HINTS) are NEVER touched. Mutates and
    returns `doc`. Logs each stage it had to apply -- see the header comment above
    _CURVE_KEYS for the production failure this exists to fix."""
    size0 = _doc_size(doc)
    if size0 <= budget or not isinstance(doc, dict):
        return doc
    # Stage 1: downsample every equity/curve array to <= equity_points, first/last kept.
    hits = []
    _walk_shrink_curves(doc, equity_points, hits)
    size1 = _doc_size(doc)
    if hits:
        detail = ", ".join(f"{k} {b}->{a}" for k, b, a in hits)
        log(f"[size-guard] {label} {size0}B -> {size1}B (stage 1: downsampled {detail})")
    if size1 <= budget:
        return doc
    # Stage 2: cap per-config population arrays (dist/points/top/equity_top) to the
    # top-N configs by PnL/score, shrinking N until it fits (floor of 10 configs).
    for n in (150, 100, 60, 30, 15, 10):
        hits2 = []
        _cap_population(doc, n, hits2)
        if not hits2:
            continue
        size2 = _doc_size(doc)
        doc["population_truncated"] = True
        kept = {k: a for k, b, a in hits2}
        log(f"[size-guard] {label} {size1}B -> {size2}B (stage 2: kept top {n} configs "
            f"-- {kept})")
        size1 = size2
        if size1 <= budget:
            return doc
        # else: still oversized -- fall through and try the next, smaller n (each
        # _cap_population call further truncates the already-capped lists in place)
    if size1 <= budget:
        return doc
    # Stage 3 (last resort): drop the heaviest non-protected top-level field(s)
    # entirely until it fits. Champion stats/curves + WF/lockbox numbers are
    # protected (_is_protected_key) and are never dropped.
    dropped = []
    while _doc_size(doc) > budget:
        candidates = [(k, _doc_size(v)) for k, v in doc.items() if not _is_protected_key(k)]
        if not candidates:
            break
        k, _sz = max(candidates, key=lambda kv: kv[1])
        doc.pop(k, None)
        dropped.append(k)
    if dropped:
        doc["population_truncated"] = True
        doc["fields_dropped"] = dropped
        log(f"[size-guard] {label} -> {_doc_size(doc)}B (stage 3: dropped {dropped})")
    return doc


def _anthropic_key():
    """Read the Anthropic API key from local augur_config.json (never from a job doc)."""
    try:
        cfg = json.load(open(os.path.join(ROOT, "augur_config.json"), encoding="utf-8"))
        return cfg.get("anthropic_key") or None
    except Exception:
        return None


def _web_version():
    """EDGELOG's single version number, read off the website (index.html `const VERSION`).
    The runner reports the SAME number as the web app so they always match — deliberately
    NOT optimizer.py's legacy engine version (that file is being retired)."""
    try:
        import re
        head = open(os.path.join(ROOT, "index.html"), encoding="utf-8").read(60000)
        m = re.search(r"const VERSION\s*=\s*'([^']+)'", head)
        return m.group(1) if m else "?"
    except Exception:
        return "?"


class _JobStopped(BaseException):
    """Raised from the progress callback to abort a running job when the web sets
    control='stop'. Subclasses BaseException so process_job's `except Exception`
    (and the engine's per-combo `except Exception`) won't swallow it."""


def process_job(job: dict, progress_cb=None) -> dict:
    """Run one job through the engine; return a result patch to merge back.
    job['type']: 'backtest' (default, single config) or 'grid' (param sweep)."""
    jtype = job.get("type", "backtest")
    # optional date-range window (YYYY-MM-DD); blank/missing => full master.
    df_from = job.get("date_from") or None
    df_to = job.get("date_to") or None

    # ── Trial-cache per-JOB reuse accounting (PR2, docs/INCREMENTAL_BACKTEST_REUSE.md
    # #7.2). process_job is the one clean accounting point: the runner is one process,
    # one job at a time, so a reset-right-before/read-right-after around the single
    # dispatch below cleanly scopes trial_cache's in-process _STATS counters to THIS
    # job only. Every stats touch is try/except-wrapped (both here and at the bottom)
    # so a stats hiccup can NEVER fail a real backtest -- the module's own
    # fail-toward-MISS principle extended to accounting/logging. Entirely inert
    # (no-op) when the cache is off, so behavior stays byte-identical to pre-PR2.
    _grid_parallel = False   # set True below only for a grid job with workers>1
    if TC.is_enabled():
        try:
            TC.reset_stats()
        except Exception:
            pass
    try:
        if jtype == "grid":
            # workers>1 spawns a ProcessPoolExecutor (augur_mp_worker.eval_chunk runs
            # in SEPARATE OS processes, each with its OWN trial_cache._STATS) -- those
            # workers' record_hit/record_miss calls never reach this parent process's
            # counters, so the accounting below would under-report a parallel grid
            # job's real reuse. Captured once here (rather than re-parsed again later)
            # so the dispatch call and the honesty check after it can never disagree.
            _grid_workers = int(job.get("workers", 1))
            _grid_parallel = _grid_workers > 1
            r = ae.run_grid(
                job["strategy"], instrument=job.get("instrument"),
                timeframe=job.get("timeframe", "5m"), session=job.get("session", "rth"),
                source=job.get("source"), preset=job.get("preset"), grid=job.get("grid"),
                date_from=df_from, date_to=df_to,
                cost_pts=float(job.get("cost_pts", 0) or 0),
                min_trades=int(job.get("min_trades", 30)), top_n=int(job.get("top_n", 10)),
                workers=_grid_workers, progress_cb=progress_cb,
                compute_dsr=bool(job.get("dsr", True)), mc_sims=int(job.get("mc_sims", 2000)),
                compute_regime=bool(job.get("regime", True)),
                compute_neighbors=bool(job.get("neighbors", True)),
                compute_ensemble=bool(job.get("ensemble", True)),
                ensemble_k=int(job.get("ensemble_k", 5)),
                compute_context=bool(job.get("context", True)))
        elif jtype in ("auto", "walkforward"):
            r = ae.run_auto(
                job["strategy"], instrument=job.get("instrument"),
                timeframe=job.get("timeframe", "5m"), session=job.get("session", "rth"),
                source=job.get("source"),
                method=("walkforward" if jtype == "walkforward" else "single"),
                date_from=df_from, date_to=df_to, wf_mode=job.get("wf_mode", "anchored"),
                oos=bool(job.get("oos", True)), wf_folds=int(job.get("wf_folds", 0) or 0),
                n_trials=int(job.get("n_trials", 200)),
                cost_pts=float(job.get("cost_pts", 0) or 0),
                min_trades=int(job.get("min_trades", 30)), top_n=int(job.get("top_n", 10)),
                progress_cb=progress_cb,
                compute_dsr=bool(job.get("dsr", True)), mc_sims=int(job.get("mc_sims", 2000)),
                compute_regime=bool(job.get("regime", True)),
                compute_neighbors=bool(job.get("neighbors", True)),
                compute_pills=bool(job.get("pills", False)),
                compute_context=bool(job.get("context", True)))
        elif jtype == "validate":
            _disc = job.get("discover", "auto")
            _prov = job.get("provider", "ollama")
            _key = _anthropic_key() if (_disc == "evolve" and _prov == "anthropic") else None
            r = ae.run_validate(
                job["strategy"], instrument=job.get("instrument"),
                timeframe=job.get("timeframe", "5m"), session=job.get("session", "rth"),
                source=job.get("source"), date_from=df_from, date_to=df_to,
                cost_pts=float(job.get("cost_pts", 0) or 0),
                min_trades=int(job.get("min_trades", 30)),
                n_trials=int(job.get("n_trials", 200)),
                wf_folds=int(job.get("wf_folds", 0) or 0),
                lockbox_months=int(job.get("lockbox_months", 12)),
                transfer_to=job.get("transfer_to"),
                discover=_disc, provider=_prov, api_key=_key,
                ai_rounds=int(job.get("n_rounds", 4)),
                equity_points=int(job.get("equity_points", 400) or 400),
                thresholds=job.get("thresholds"),
                # #88 (owner-approved 2026-07-20): OOS-checked champion selection — the
                # production Auto-Validate path opts in HERE (run_validate's own
                # signature default stays 0/OFF for library neutrality / tests).
                # Motivating evidence: run #167 crowned the sharpest realism-gated
                # IN-SAMPLE config (IS $257,873) which collapsed to a $35,083 lockbox
                # (PBO gate fired, verdict WEAK), while run #165's WEAKER-IS champion
                # had DOUBLE the lockbox PnL. Re-scores the top-5 IS candidates by
                # walk-forward fold OOS PnL and crowns the steadiest one instead of
                # the raw IS-max (augur_engine/validate.py's Stage A.5).
                select_oos_topk=int(job.get("select_oos_topk", 10) or 0),   # v68.5 (owner): crown pool widened to the top-10 IS configs, still WF-ranked
                progress_cb=progress_cb)
        elif jtype == "book":
            # BOOK (RUNBOARD item B): N strategy files traded side by side over ONE window,
            # every leg's trades pooled into a single pile and scored as ONE strategy. Fixed
            # params — nothing is tuned here — so there is no WF fold result to report; the
            # lockbox split and the house consistency count are in the result's `book` block.
            r = ae.run_book(
                job.get("legs") or [],
                date_from=df_from, date_to=df_to,
                lockbox_months=int(job.get("lockbox_months", 12) or 12),
                slices=int(job.get("slices", 8) or 8),
                equity_points=int(job.get("equity_points", 400) or 400),
                name=job.get("book_name") or job.get("strategy"),
                progress_cb=progress_cb)
        elif jtype == "gate_validate":
            r = ae.run_gate_validate(
                job["strategy"], instrument=job.get("instrument"),
                timeframe=job.get("timeframe", "5m"), session=job.get("session", "rth"),
                source=job.get("source"), params=job.get("params") or {},
                cost_pts=float(job.get("cost_pts", 0) or 0),
                date_from=df_from, date_to=df_to,
                gates=job.get("gates") or ("logistic", "rf", "xgb"),
                thresholds=job.get("thresholds") or (0.50, 0.55, 0.60),
                lockbox_months=int(job.get("lockbox_months", 12) or 12),
                progress_cb=progress_cb)
        elif jtype == "ai_optimize":
            prov = job.get("provider", "ollama")
            # Anthropic key comes from LOCAL config, never the job doc (which is in
            # Firestore). Ollama / claude-cli need no key.
            key = _anthropic_key() if prov == "anthropic" else None
            r = ae.ai_optimize(
                job["strategy"], instrument=job.get("instrument"),
                timeframe=job.get("timeframe", "5m"), session=job.get("session", "rth"),
                source=job.get("source"), preset=job.get("preset"), grid=job.get("grid"),
                n_rounds=int(job.get("n_rounds", 5)), provider=prov, model=job.get("model"),
                api_key=key, cost_pts=float(job.get("cost_pts", 0) or 0),
                date_from=df_from, date_to=df_to,
                min_trades=int(job.get("min_trades", 30)), workers=int(job.get("workers", 1)),
                progress_cb=progress_cb)
        elif jtype == "ai_evolve":
            prov = job.get("provider", "ollama")
            key = _anthropic_key() if prov == "anthropic" else None
            r = ae.ai_evolve(
                job["strategy"], instrument=job.get("instrument"),
                timeframe=job.get("timeframe", "5m"), session=job.get("session", "rth"),
                source=job.get("source"), preset=job.get("preset"), grid=job.get("grid"),
                n_rounds=int(job.get("n_rounds", 4)), provider=prov, model=job.get("model"),
                api_key=key, cost_pts=float(job.get("cost_pts", 0) or 0),
                date_from=df_from, date_to=df_to,
                min_trades=int(job.get("min_trades", 30)), progress_cb=progress_cb)
        else:
            r = ae.run_backtest(
                job["strategy"], instrument=job.get("instrument"),
                timeframe=job.get("timeframe", "5m"), session=job.get("session", "rth"),
                source=job.get("source"), params=job.get("params") or {},
                cost_pts=float(job.get("cost_pts", 0) or 0),
                date_from=df_from, date_to=df_to,
                return_trades=bool(job.get("return_trades")),
                mc_sims=int(job.get("mc_sims", 0)),
                # Sizing overlay (ORB): a dict of augur_engine.sizing rule kwargs +
                # stop_frac/or_bars/mult/fee_pts → adds res["sizing"] (baseline vs sized),
                # headline unchanged. Missing/None = off. (ORB.md §4.7-4.11)
                sizing=job.get("sizing"),
                # ML trade gate (board 3A.2): 'none'/missing = ungated, as ever
                ml_filter=job.get("ml_filter"),
                ml_threshold=float(job.get("ml_threshold", 0.50) or 0.50),
                ml_min_history=int(job.get("ml_min_history", 30) or 30))
    except Exception as e:
        return {"status": "error", "error": f"{type(e).__name__}: {e}",
                "finishedAt": time.time()}
    if r is None:
        return {"status": "error", "error": "no result (0 trades or invalid window)",
                "finishedAt": time.time()}
    if TC.is_enabled():
        try:
            summary = TC.job_reuse_summary()
            note = ""
            if _grid_parallel:
                # HONESTY CAVEAT: don't silently print/attach a low parent-only count
                # as if it were the complete picture -- label it explicitly instead.
                summary["note"] = "parallel-grid counts not aggregated (workers>1 -- parent-process only)"
                note = " [parent-process only; workers>1]"
            r["cache_reuse"] = summary
            print(f"    -> cache: reused {summary['hits']}/{summary['total']} configs "
                  f"({summary['pct_reused']}%){note}")
        except Exception:
            pass
    return {"status": "done", "result": json_safe(r), "finishedAt": time.time()}


class LocalQueue:
    """File-backed queue for testing: each job is a JSON file in augur_jobs/."""

    def __init__(self):
        os.makedirs(JOBS_DIR, exist_ok=True)

    def enqueue(self, job: dict) -> str:
        jid = job.get("id") or f"job_{int(time.time()*1000)}"
        job = {**job, "id": jid, "status": "queued"}
        with open(os.path.join(JOBS_DIR, jid + ".json"), "w", encoding="utf-8") as f:
            json.dump(job, f, indent=1)
        return jid

    def pending(self):
        for p in sorted(glob.glob(os.path.join(JOBS_DIR, "*.json"))):
            try:
                j = json.load(open(p, encoding="utf-8"))
            except Exception:
                continue
            if j.get("status") == "queued":
                yield p, j

    def complete(self, path, job, patch):
        job.update(patch)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(job, f, indent=1)

    def run_once(self, log=print) -> int:
        n = 0
        for path, job in self.pending():
            log(f"  running {job['id']}: {job.get('strategy')} "
                f"{job.get('instrument')} {job.get('timeframe')}…")
            patch = process_job(job)
            self.complete(path, job, patch)
            n += 1
            if patch["status"] == "done":
                m = patch["result"]
                if "n_combos" in m:                       # grid result
                    b = m.get("best") or {}
                    log(f"    -> done: {m['n_valid']}/{m['n_combos']} valid, "
                        f"best PF {min(b.get('profit_factor', 0), 99):.2f}")
                else:                                     # single backtest
                    log(f"    -> done: PF {min(m['profit_factor'], 99):.2f}, "
                        f"{m['num_trades']} trades, total {m['total_pnl']:.1f} pts")
            else:
                log(f"    -> error: {patch['error']}")
        return n


class FirestoreQueue:
    """Firestore-backed queue. Only runs jobs whose uid is allowlisted."""

    def __init__(self, cred_path=None, collection="backtests", allow_uids=(), nt_fills=None,
                 webull_keys=None):
        try:
            import firebase_admin
            from firebase_admin import credentials, firestore
        except ImportError:
            raise SystemExit("pip install firebase-admin  (needed for --firestore)")
        if not firebase_admin._apps:
            cred = credentials.Certificate(cred_path) if cred_path else credentials.ApplicationDefault()
            firebase_admin.initialize_app(cred)
        self.db = firestore.client()
        self.col = collection
        self.allow = set(allow_uids)
        self.nt_fills = nt_fills
        self.webull_keys = webull_keys
        # Listener conversion (item #36): `wake` is a thread-safe signal the
        # on_snapshot callbacks set from a Firestore SDK background thread — the
        # main watch loop (main() below) blocks on it instead of a fixed sleep.
        # Callbacks do ONLY that (plus stamping the watchdog time); the *actual*
        # queued-doc query + claim + execute still happens in run_once()/
        # run_commands() on the main loop thread, unchanged, so serial execution
        # and the existing claim logic (status->running writes) can never double-
        # run a doc just because a listener fired.
        self.wake = threading.Event()
        self._watches = []
        self._last_event_ts = 0.0

    def _on_snapshot(self, _col_snapshot, _changes, _read_time):
        """Firestore background-thread callback for both the backtests and commands
        watches. Must stay cheap — no engine work, no Firestore writes here."""
        self._last_event_ts = time.time()
        self.wake.set()

    def start_listeners(self, log=print, ready_timeout=15.0):
        """Attach on_snapshot listeners on status=='queued' for every allowlisted
        uid's backtests + commands subcollections. Returns True if at least one
        listener confirmed it's alive (fired its initial snapshot) within
        ready_timeout, else False so the caller falls back to plain polling.
        Never raises — any failure here is a reason to poll, not to crash."""
        from google.cloud.firestore_v1.base_query import FieldFilter
        if not self.allow:
            return False   # collection_group mode has no per-uid path to watch
        qf = FieldFilter("status", "==", "queued")
        ready = threading.Event()

        def _cb(col_snapshot, changes, read_time):
            ready.set()
            self._on_snapshot(col_snapshot, changes, read_time)

        ok = 0
        for uid in self.allow:
            for coll in (self.col, "commands"):
                try:
                    ref = self.db.collection("users").document(uid).collection(coll)
                    watch = ref.where(filter=qf).on_snapshot(_cb)
                    self._watches.append(watch)
                    ok += 1
                except Exception as e:
                    log(f"  [listener] {uid}/{coll} setup failed: {type(e).__name__}: {e}")
        if not ok:
            return False
        # Firestore always fires an initial snapshot right after attach (even if
        # empty), so waiting here confirms the channel is actually live rather
        # than just "no exception was raised while attaching".
        return ready.wait(ready_timeout)

    def sync_webull(self, log=print) -> int:
        """Pull Webull filled orders (official OpenAPI) into each allowlisted user's
        journal. webull_sync gates itself to ONCE PER NY DAY (free-plan Firestore
        quota rule) — calling this every loop is free on all but the first pass."""
        if not self.webull_keys:
            return 0
        from api import webull_sync
        total = 0
        for uid in (self.allow or []):
            try:
                r = webull_sync.sync_trades(self.db, uid, self.webull_keys, log)
                total += r.get("added", 0) + r.get("updated", 0)
            except Exception as e:
                log(f"  [webull] skipped for {uid}: {type(e).__name__}: {e}")
        return total

    def sync_trades(self, log=print) -> int:
        """Pull NinjaTrader fills (written by the EdgeLogExport AddOn) into each
        allowlisted user's trade journal (users/{uid}/trades). Idempotent — re-reading
        the whole fills file never duplicates trades. Returns trades added+updated."""
        if not self.nt_fills:
            return 0
        from api import nt_sync
        total = 0
        for uid in (self.allow or []):
            try:
                r = nt_sync.sync_trades(self.db, uid, self.nt_fills, log)
                total += r.get("added", 0) + r.get("updated", 0)
            except Exception as e:
                log(f"  [nt-sync] skipped for {uid}: {type(e).__name__}: {e}")
        return total

    def sync_runs(self, log=print) -> int:
        """Push run history from optimizer_history.db up to users/{uid}/runs so the web
        UI can browse it. One doc per run (keyed by run id), with detail blobs parsed.
        Skips the equity/full_results blobs on any run whose doc would exceed ~900KB.
        Chunks each batch commit by BOTH doc count (Firestore's 500-write cap) AND
        estimated bytes (Firestore's 10 MiB request cap) -- a run of big docs, not just
        a run of many docs, can blow the request size (see the "[sync-runs] startup
        skipped ... 11,534,336 bytes" production failure in BACKTESTING_STACK.md)."""
        import json as _json
        total = 0
        for uid in (self.allow or []):
            col = self.db.collection("users").document(uid).collection("runs")
            batch = self.db.batch(); pending = 0; batch_bytes = 0
            for r in ae.list_runs():
                doc = ae.get_run(r["id"])
                if doc is None:
                    continue
                doc = json_safe(doc)
                if len(_json.dumps(doc, default=str)) > 900_000:
                    doc.pop("full_results", None); doc.pop("equity", None)
                doc_bytes = _doc_size(doc)
                if pending and (pending >= 400 or batch_bytes + doc_bytes > BATCH_BYTE_BUDGET):
                    batch.commit(); batch = self.db.batch(); pending = 0; batch_bytes = 0
                # merge=True so web-only fields that never exist in the local SQLite doc
                # (e.g. `archived`, set from the browser to hide a run from Past Runs) are
                # PRESERVED across re-sync. A plain .set() is a full-doc overwrite and would
                # silently drop them on every runner restart.
                batch.set(col.document(str(r["id"])), doc, merge=True)
                pending += 1; total += 1; batch_bytes += doc_bytes
            if pending:
                batch.commit()
            log(f"  synced {total} runs -> users/{uid}/runs")
        return total

    def sync_meta(self, log=print) -> int:
        """Push the strategy library (with each strategy's grid presets/scopes) and the
        master list to users/{uid}/meta so the web Executions tab can populate its pickers."""
        for uid in (self.allow or []):
            meta = self.db.collection("users").document(uid).collection("meta")
            strats = []
            # Per-strategy validation-roadmap state the user ticked in the Streamlit app
            # (augur_config.json -> roadmaps[file] = {step: bool}). Synced so the web
            # Library roadmap shows the same completed steps.
            try:
                _cfg0 = json.load(open(os.path.join(ROOT, "augur_config.json"), encoding="utf-8"))
                _roadmaps = _cfg0.get("roadmaps", {}) or {}
            except Exception:
                _roadmaps = {}
            for s in ae.list_strategies():
                try:
                    presets = ae.list_presets(s["file"])
                except Exception:
                    presets = []
                # numeric param spec (for the web Builder's CUSTOM scope / range editor)
                try:
                    _dp = ae.strategy_params(ae.load_strategy(s["file"])) or {}
                    pspec = [{"name": pn, "type": pm.get("type", "float"),
                              "min": pm.get("min"), "max": pm.get("max"),
                              "step": pm.get("step"), "default": pm.get("default"),
                              "label": pm.get("label", pn)}
                             for pn, pm in _dp.items()
                             if isinstance(pm, dict) and pm.get("type", "float") in ("int", "float")]
                except Exception:
                    pspec = []
                # Combo count per preset (product of grid value-counts) so the web
                # Builder can show an adaptive ETA without shipping the full grids.
                pcombos = {}
                try:
                    from augur_engine import optimize as _opt
                    _m = ae.load_strategy(s["file"])
                    for _lbl in presets:
                        try:
                            _g = _opt.grid_from_preset(_m, _lbl) or {}
                            _n = 1
                            for _vv in _g.values():
                                _n *= len(_vv) if isinstance(_vv, (list, tuple)) else 1
                            pcombos[_lbl] = _n
                        except Exception:
                            pass
                except Exception:
                    pass
                strats.append({**s, "presets": presets, "preset_combos": pcombos,
                               "params": pspec, "roadmap": _roadmaps.get(s["file"], {})})
            # eta_calib {sec_per_bt, bars} + worker count let the web estimate run time.
            meta.document("strategies").set(json_safe(
                {"list": strats, "eta_calib": _cfg0.get("eta_calib"),
                 "workers": _cfg0.get("workers")}))
            keep = ("name", "instrument", "timeframe", "session", "source",
                    "rows", "date_from", "date_to")
            _mfull = ae.list_masters()
            masters = [{k: m.get(k) for k in keep} for m in _mfull]
            # Per-master data-health card (stack 2.2): structural asserts, cached by
            # file mtime+size — only masters that changed since last sync get re-scanned.
            try:
                from augur_engine import data_quality as _dq
                for m, mf in zip(masters, _mfull):
                    m["health"] = _dq.health_summary(mf)
                    p = _dq.profile_master(mf)          # EDA profile (stack 1.1/2.3/2.4)
                    if p and "error" not in p:
                        m["profile"] = {k: p.get(k) for k in
                                        ("bars", "ret", "price", "vol_by_year",
                                         "hour_profile", "coverage", "outliers")}
            except Exception as e:
                log(f"  [data-health] skipped: {type(e).__name__}: {e}")
            # Auto-pull (auto-refresh) status, read from local augur_config.json. Tag
            # each master with whether auto-refresh is enabled for it so the web Library
            # can show a live AUTO badge + last-bar date, and Settings a sync summary.
            ar_global, ar_masters = False, {}
            try:
                cfg = json.load(open(os.path.join(ROOT, "augur_config.json"), encoding="utf-8"))
                ar = cfg.get("autorefresh", {}) or {}
                ar_global = bool(ar.get("enabled_global", False))
                ar_masters = ar.get("masters", {}) or {}
            except Exception:
                pass
            for m in masters:
                key = f"{m.get('instrument')}|{m.get('timeframe')}|{m.get('source')}"
                m["auto"] = bool(ar_global and ar_masters.get(key, False))
            status = {"synced_at": time.time(), "autorefresh": ar_global,
                      "n_auto": sum(1 for m in masters if m.get("auto")),
                      "n_masters": len(masters), "n_strategies": len(strats)}
            meta.document("masters").set(json_safe({"list": masters, "status": status}))
            log(f"  synced meta (strategies+masters) -> users/{uid}/meta "
                f"(auto-pull {'ON' if ar_global else 'OFF'}, {status['n_auto']}/{len(masters)} masters)")
        return 1

    def _next_run_id(self, uid) -> int:
        """Sequential run id = (max existing id in users/{uid}/runs) + 1, so web sweeps get
        a clean number instead of a 10-digit epoch. Falls back to an epoch id (still unique)
        only if the lookup fails."""
        try:
            from google.cloud.firestore_v1 import Query
            col = self.db.collection("users").document(uid).collection("runs")
            snap = list(col.order_by("id", direction=Query.DESCENDING).limit(1).stream())
            if snap:
                top = (snap[0].to_dict() or {}).get("id")
                if isinstance(top, (int, float)):
                    return int(top) + 1
        except Exception:
            pass
        return int(time.time())

    def _family_of(self, strategy) -> str:
        """Coarse master family for a strategy (must match the web resolver + backfill), so every
        ORB / TTIBS / ENGU-Q run gets one stable per-family number (ORB-1, ORB-2, ...)."""
        import re
        s0 = str(strategy or "").upper()
        if "ORB_FADE" in s0 or "ORBFADE" in s0 or "ORB FADE" in s0: return "ORB-FADE"
        if s0.startswith("ORB"): return "ORB"
        if s0.startswith("ENGUQ"): return "ENGU-Q"
        if s0.startswith("TTIBS") or s0.startswith("TBISS"): return "TTIBS"
        if s0.startswith("REVERT"): return "REVERT"
        if "SUPERTREND" in s0 or s0.startswith("STRICT"): return "SUPERTREND"
        if s0.startswith("VWAP"): return "VWAP-FADE"
        if s0.startswith("OVERNIGHT"): return "OVERNIGHT"
        if s0.startswith("RSIDIV"): return "RSIDIV"
        # new/unknown strategy -> derive a key from the leading name token (strip version/ext)
        base = re.sub(r"\.PY$", "", s0)
        m = re.match(r"[A-Z][A-Z0-9]*", base)
        return m.group(0) if m else "MISC"

    def _assign_family(self, uid, strategy):
        """Next STABLE per-family number via a transaction on meta/familyCounters (concurrent-safe;
        never renumbers, deleting a run leaves a gap). Returns (famKey, famSeq) or (None, None)."""
        try:
            from firebase_admin import firestore
            famkey = self._family_of(strategy)
            ref = (self.db.collection("users").document(uid)
                   .collection("meta").document("familyCounters"))
            txn = self.db.transaction()

            @firestore.transactional
            def _bump(t):
                data = ref.get(transaction=t).to_dict() or {}
                counters = dict(data.get("counters") or {})
                nxt = int(counters.get(famkey, 0)) + 1
                counters[famkey] = nxt
                t.set(ref, {"counters": counters, "scheme": "stable-v1"}, merge=True)
                return nxt

            return famkey, _bump(txn)
        except Exception:
            return None, None

    def _master_of(self, job):
        try:
            return ae.find_master(job.get("instrument"), job.get("timeframe", "5m"),
                                  job.get("session", "rth"), job.get("source"))
        except Exception:
            return None

    def _run_window(self, job, result, mm):
        """(date_from, date_to, days_in_test) — the explicit job window if set, else the
        source master's full span. days = calendar days between the two."""
        df = job.get("date_from") or result.get("date_from") or ""
        dt = job.get("date_to") or result.get("date_to") or ""
        if mm:
            df = df or str(mm.get("date_from") or "")[:10]
            dt = dt or str(mm.get("date_to") or "")[:10]
        days = 0
        try:
            from datetime import date
            days = max(0, (date.fromisoformat(str(dt)[:10]) - date.fromisoformat(str(df)[:10])).days)
        except Exception:
            pass
        return df, dt, days

    def _winner_equity(self, job, best_params):
        """Re-run the winning config once (return_trades) and build a downsampled equity
        curve so Results shows the sparkline + curve. Fail-safe -> None on any error."""
        try:
            from augur_engine import history as _H
            cost = float(job.get("cost_pts", 0) or 0)
            bt = ae.run_backtest(
                job["strategy"], instrument=job.get("instrument"),
                timeframe=job.get("timeframe", "5m"), session=job.get("session", "rth"),
                source=job.get("source"), params=best_params or {}, cost_pts=cost,
                date_from=job.get("date_from") or None, date_to=job.get("date_to") or None,
                return_trades=True)
            trades = (bt or {}).get("trades") or []
            # trades from run_backtest(cost_pts>0) are already NET of cost (engine
            # _apply_costs) — subtracting cost again here double-charged ~n·cost_pts
            # (≈197 pts on a 695-trade TTIBS run; runs #161-#168 all carried it).
            cum, c = [], 0.0
            for t in trades:
                c += (t[2] if isinstance(t, (list, tuple)) and len(t) > 2 else 0)
                cum.append(c)
            return _H._downsample_equity(cum, c) if cum else None
        except Exception:
            return None

    def _persist_run(self, uid, job, result, log=print, elapsed_s=0.0):
        """Save a completed web grid sweep into users/{uid}/runs (Runs history),
        shaped like the app's synced runs so the Runs tab renders it identically."""
        mult = float(job.get("mult", 20) or 20)
        best = result.get("best") or {}
        # gate-validate has no swept "best" config — headline off the chosen gate so the
        # Past-Runs row shows real numbers (lockbox gated if opened, else pre-lockbox).
        if not best and result.get("gate_validate"):
            _gv = result["gate_validate"]
            best = (((_gv.get("lockbox") or {}).get("gated"))
                    or ((_gv.get("chosen") or {}).get("pre")) or {})
        rid = self._next_run_id(uid)
        famkey, famseq = self._assign_family(uid, job.get("strategy", ""))
        mm = self._master_of(job)
        df, dt, days = self._run_window(job, result, mm)
        equity = result.get("equity") or self._winner_equity(job, result.get("best_params"))
        pnl_usd = (best.get("total_pnl") or 0) * mult
        doc = json_safe({
            "id": rid,
            "timestamp": time.strftime("%Y-%m-%d %H:%M"),
            "strategy": job.get("strategy", ""),
            "instrument": job.get("instrument", ""),
            "timeframe": job.get("timeframe", ""),
            "scope": ({"ai_optimize": "AI optimize", "ai_evolve": "AI evolve",
                       "auto": "Auto-Optimize", "walkforward": "Walk-Forward",
                       "validate": "🧭 Auto-Validate", "gate_validate": "🚪🧭 Gate-Validate",
                       "book": "📚 Book"}
                      .get(job.get("type"), job.get("preset", "web sweep"))),
            # carry the validate report card into run history so Results/Library can show it
            "validate": result.get("validate"),
            "data_source": job.get("source", ""),
            "source_name": (mm.get("name") if mm else "") or job.get("source", "") or "",
            "rounds": result.get("rounds"), "best_oos_pnl": result.get("best_oos_pnl"),
            "evolved_file": result.get("evolved_file"),
            "n_combos": result.get("n_combos"), "n_valid": result.get("n_valid"),
            "bars": result.get("bars"),
            "days_in_test": days,
            "elapsed_s": float(elapsed_s or 0),
            "best_pnl_pts": best.get("total_pnl"),
            "best_pnl_usd": pnl_usd,
            "best_pnl_per_day": (pnl_usd / days) if days else 0,
            "best_pf": best.get("profit_factor"),
            "best_win_rate": best.get("win_rate"),
            "best_trades": best.get("num_trades"),
            "best_dd_usd": (best.get("max_drawdown") or 0) * mult,
            "best_params": result.get("best_params"),
            "top10_results": result.get("top"),
            "dist": result.get("dist"),   # config-PnL spread for the distribution panel
            "points": result.get("points"),   # per-config param points for scatter / heatmap
            "equity_top": result.get("equity_top"),   # top-N equity curves (overlay)
            "equity_top_cap": result.get("equity_top_cap"),  # §7.10: {saved, tested} so 2A stays honest
            "n_evaluated": result.get("n_evaluated"),        # §7.10: true recorded-config count
            "stress": result.get("stress"),   # PnL across chronological windows
            "mae_mfe": result.get("mae_mfe"),   # per-trade adverse/favorable excursion
            "win_dist": result.get("win_dist"),   # winner's per-trade PnLs for the distribution curve
            # 1G/1H scope slices + scope tag: the walk-forward and lockbox versions of the trade
            # distribution and MAE/MFE, plus which scope the base copies cover. The engine returns
            # these but they were dropped here (same bug family as wf_alt_folds) - which is why
            # the 1G scope dropdown showed WF/LB greyed out on every saved run.
            "win_dist_wf": result.get("win_dist_wf"), "win_dist_lb": result.get("win_dist_lb"),
            "mae_mfe_wf": result.get("mae_mfe_wf"), "mae_mfe_lb": result.get("mae_mfe_lb"),
            "champ_dist_scope": result.get("champ_dist_scope"),
            "wf_mode": job.get("wf_mode"),   # rolling | anchored (walk-forward runs)
            # 1C comparison toggle: the NON-selected walk-forward scheme's folds ride along so
            # the saved run can chart BOTH schemes. The engine returns these at the result top
            # level - they were previously dropped here, which is why saved validates (e.g.
            # run #170) could never toggle their ROLLING/ANCHORED comparison side.
            "wf_alt_folds": result.get("wf_alt_folds"),
            "wf_alt_mode": result.get("wf_alt_mode"),
            "equity": equity,
            "multiplier": mult,
            # cost realism + date window so Results/roadmap can show & auto-derive them
            "commission_usd": job.get("commission_usd"),
            "slippage_pts": job.get("slippage_pts"),
            "cost_pts": job.get("cost_pts"),
            "date_from": df, "date_to": dt,
            "dsr": result.get("dsr"), "mc": result.get("mc"),
            "regime": result.get("regime"), "neighborhood": result.get("neighborhood"),
            "context": result.get("context"),   # TRADE CONTEXT (stages 1+2): feature->PnL scores
            "relationship": result.get("relationship"),   # per-param Pearson / MI / PPS (#24)
            # ── one-stop-shop report parity: carry the config-selection + gate cards + the
            #    diagnostic 'pills' into run history so the saved RUN REPORT renders the same
            #    rich view the Builder does (not just Auto-Validate runs). ──
            # BOOK runs: the pooled per-leg breakdown + lockbox split + house 8-stretch
            # count, so the RUNBOARD's BOOKS tile can render a real book row.
            "book": result.get("book"),
            "ensemble": result.get("ensemble"),        # §6 top-K blend + CCMP (grid sweeps)
            "plateau_pick": result.get("plateau_pick"),  # 3C.1 broad-high-ground vs argmax
            "surrogate": result.get("surrogate"),      # #31 P1 multi-surrogate bake-off cards (2L panel)
            "auto_expand": result.get("auto_expand"),  # #26/#30 range-widening log
            "auto_expand_summary": result.get("auto_expand_summary"),  # #30 convergence summary
            "steering": result.get("steering"),        # #36 P2 steered-search trial counts
            "ml_gate": result.get("ml_gate"),          # single-gate before/after + SHAP/calibration
            "gate_validate": result.get("gate_validate"),  # 9-candidate model×cut-off bake-off
            "selection": result.get("selection"),      # #88 OOS-checked champion selection evidence
            "power": result.get("power"),              # #94 statistical power for the lockbox verdict
            # diagnostic pills (top-level on Auto-Optimize runs; Auto-Validate keeps its own
            # copies under `validate`). Omitted keys simply don't render.
            "adversarial": result.get("adversarial"), "conformal": result.get("conformal"),
            "causal": result.get("causal"), "synthetic": result.get("synthetic"),
            "lead_lag": result.get("lead_lag"), "acf": result.get("acf"),
            "vif": result.get("vif"), "feature_select": result.get("feature_select"),
            "edge_sig": result.get("edge_sig"), "tailfit": result.get("tailfit"),
            "seasonality": result.get("seasonality"),
            "source_web": True,
        })
        if famkey is not None:
            doc["famKey"] = famkey
            doc["famSeq"] = famseq
        doc = shrink_to_fit(doc, log=log, label=f"run #{rid}")
        self.db.collection("users").document(uid).collection("runs").document(str(rid)).set(doc)
        log(f"    -> saved to Runs history (#{rid}"
            + (f" · {famkey}-{famseq}" if famkey is not None else "") + ")")
        # best-effort: save a per-trade blotter CSV next to the run (blotters/) so every
        # Auto-Validate / grid run has a downloadable trade-by-trade record. Never fail the
        # run on this — a bad master or 0-trade config just skips it.
        try:
            from api.blotter import champion_blotter, write_csv
            _bp = result.get("best_params") or (job.get("params") or {})
            # A BOOK has no single strategy file to re-run (its "strategy" is the book NAME
            # and its params are a leg list), so there is no one champion blotter to build.
            # Skip it outright rather than logging a file-not-found every book run.
            if job.get("type") == "book":
                _bp = None
            if _bp and job.get("strategy") and job.get("instrument"):
                # pin the run's exact window AND master source — an unpinned blotter
                # covers whatever the registry's first master happens to span (run #162,
                # made on the tv master, got a db_noadj blotter this way).
                _rows, _bm = champion_blotter(job.get("strategy"), job.get("instrument"),
                                              job.get("timeframe", "5m"), job.get("session", "rth"),
                                              _bp, job.get("cost_pts", 0), mult,
                                              date_from=job.get("date_from") or None,
                                              date_to=job.get("date_to") or None,
                                              source=job.get("source") or None)
                _out = os.path.join(ROOT, "blotters",
                                    f"run{rid}_{job.get('instrument')}_{job.get('timeframe','5m')}.csv")
                if write_csv(_rows, _out, meta=_bm):
                    log(f"    -> saved trade blotter ({len(_rows)} trades, "
                        f"master '{_bm.get('master')}') -> {_out}")
        except Exception as _e:
            log(f"    -> blotter skipped: {type(_e).__name__}: {_e}")

    def _save_job_doc(self, ref, patch, log=print):
        """Write the finished-job patch to its backtests doc. `patch["result"]` has
        already been through shrink_to_fit, so this should normally just work -- but
        a job must NEVER be left stuck on status='running' because a save failed (the
        g2iIT39X bug: the write raised, the exception was swallowed by the caller's
        catch-all, and the doc sat on 'running' forever). Falls back in stages if the
        write still fails: protected-fields-only, then a bare status/error doc."""
        try:
            ref.update(patch)
            return
        except Exception as e:
            log(f"  (job doc save failed even after size-guard: {type(e).__name__}: {e} "
                f"-- retrying with protected fields only)")
        try:
            result = patch.get("result")
            slim = {"status": patch.get("status", "error"),
                    "finishedAt": patch.get("finishedAt", time.time())}
            if "elapsed_s" in patch:
                slim["elapsed_s"] = patch["elapsed_s"]
            if isinstance(result, dict):
                slim["result"] = {k: v for k, v in result.items() if _is_protected_key(k)}
                slim["result"]["truncated_for_size"] = True
            ref.update(slim)
            log("  (job doc saved with protected-fields-only fallback)")
            return
        except Exception as e2:
            log(f"  (protected-fields fallback ALSO failed: {type(e2).__name__}: {e2} "
                f"-- writing bare status doc so the job doesn't stay stuck on 'running')")
        try:
            ref.update({
                "status": "error" if patch.get("status") != "cancelled" else "cancelled",
                "error": "result too large to save to Firestore (see runner.log)",
                "finishedAt": patch.get("finishedAt", time.time()),
            })
        except Exception as e3:
            log(f"  (bare status-doc save ALSO failed -- job may stay stuck on 'running': "
                f"{type(e3).__name__}: {e3})")

    def run_commands(self, log=print) -> int:
        """Poll users/{uid}/commands for queued Library file-op commands (download /
        delete / add / make_pine), execute them on THIS PC behind the uid allowlist,
        write the result back, and re-sync meta after any mutation so the web Library
        reflects the change immediately."""
        from google.cloud.firestore_v1.base_query import FieldFilter
        from api.lib_commands import process_command
        qf = FieldFilter("status", "==", "queued")
        n = 0
        for uid in (self.allow or []):
            col = self.db.collection("users").document(uid).collection("commands")
            for snap in col.where(filter=qf).stream():
                ref = snap.reference
                doc = snap.to_dict() or {}
                action = doc.get("action")
                # get_bars/get_blotter are served immediately by the parallel CommandThread
                # (started alongside the watch loop, see main()) so the web doesn't wait
                # behind a running backtest for these read-only lookups. Skip them here
                # BEFORE claiming (status->running) so the main loop and the command thread
                # never race to serve the same doc.
                if action in READONLY_ACTIONS:
                    continue
                ref.update({"status": "running"})
                # NinjaTrader trade refresh is a Firestore-write op (db+uid), so it's
                # handled here rather than in lib_commands (which is file-ops only).
                if action == "sync_trades":
                    if self.nt_fills:
                        from api import nt_sync
                        try:
                            res = {"ok": True, **nt_sync.sync_trades(self.db, uid, self.nt_fills, log)}
                        except Exception as e:
                            res = {"ok": False, "error": f"{type(e).__name__}: {e}"}
                    else:
                        res = {"ok": False, "error": "runner has no --nt-fills path configured"}
                    ref.update({"status": "done" if res.get("ok") else "error",
                                "result": json_safe(res), "finishedAt": time.time()})
                    n += 1
                    continue
                # On-demand Webull pull (the "Sync Webull now" button) — force=True bypasses
                # the once-per-NY-day gate so the user can see today's trades immediately.
                if action == "sync_webull":
                    if self.webull_keys:
                        from api import webull_sync
                        try:
                            res = {"ok": True, **webull_sync.sync_trades(
                                self.db, uid, self.webull_keys, log, force=True)}
                        except Exception as e:
                            res = {"ok": False, "error": f"{type(e).__name__}: {e}"}
                    else:
                        res = {"ok": False, "error": "runner has no --webull-keys path configured"}
                    ref.update({"status": "done" if res.get("ok") else "error",
                                "result": json_safe(res), "finishedAt": time.time()})
                    n += 1
                    continue
                # Blotter reconciliation (compute, not a file-op) — run the engine on the
                # same config+window and diff it against the pasted TV/NT export text.
                if action == "reconcile":
                    from augur_engine.reconcile import run_reconcile
                    p = doc.get("payload") or {}
                    try:
                        rec = run_reconcile(
                            p.get("strategy"), instrument=p.get("instrument"),
                            timeframe=p.get("timeframe", "5m"), session=p.get("session", "rth"),
                            params=p.get("params") or {},
                            date_from=p.get("date_from") or None, date_to=p.get("date_to") or None,
                            cost_pts=float(p.get("cost_pts", 0) or 0),
                            tv_text=p.get("tv_csv"), nt_text=p.get("nt_csv"),
                            tol_min=float(p.get("tol_min", 10) or 10))
                        res = {"ok": True, **rec}
                    except Exception as e:
                        res = {"ok": False, "error": f"{type(e).__name__}: {e}"}
                    ref.update({"status": "done" if res.get("ok") else "error",
                                "result": json_safe(res), "finishedAt": time.time()})
                    n += 1
                    continue
                # get_blotter / get_bars (compute/file-read, not a Library file-op) used to
                # be handled inline here like reconcile — now served by CommandThread in
                # parallel with running jobs (see READONLY_ACTIONS skip above).
                res = process_command(action, doc.get("payload") or doc, log)
                ref.update({"status": "done" if res.get("ok") else "error",
                            "result": json_safe(res), "finishedAt": time.time()})
                if res.get("ok") and action in ("delete", "add", "make_pine", "write_pine"):
                    try:
                        self.sync_meta(log)
                    except Exception as _e:
                        log(f"  (post-command sync_meta failed: {_e})")
                n += 1
        return n

    def run_once(self, log=print) -> int:
        from google.cloud.firestore_v1.base_query import FieldFilter
        qf = FieldFilter("status", "==", "queued")
        n = 0
        if self.allow:
            # Query each allowlisted user's own subcollection users/{uid}/backtests
            # directly. A single-collection equality filter uses Firestore's automatic
            # single-field index, so NO manual COLLECTION_GROUP index is needed. (The
            # uid is inherently the allowed one, so this is also the auth gate.)
            for uid in self.allow:
                col = self.db.collection("users").document(uid).collection(self.col)
                for snap in col.where(filter=qf).stream():
                    ref = snap.reference
                    job = snap.to_dict() or {}
                    # web STOP before the job even started -> cancel without running.
                    if job.get("control") == "stop":
                        ref.update({"status": "cancelled", "finishedAt": time.time()})
                        log(f"  cancelled {snap.id} (stopped before start)")
                        continue
                    ref.update({"status": "running", "progress": 0})
                    log(f"  running {snap.id}: {job.get('type','backtest')} "
                        f"{job.get('strategy')} {job.get('instrument')}…")
                    last = [0.0]

                    # The progress callback doubles as the STOP/PAUSE check: at the same
                    # ~1.5s cadence it reads the job's `control` flag. All control I/O is
                    # fail-safe -> any error falls through to normal running, so a flaky
                    # read can never break a backtest, only miss one stop/pause check.
                    def cb(done, total, _ref=ref, _last=last):
                        if not total or time.time() - _last[0] <= 1.5:
                            return
                        _last[0] = time.time()
                        try:
                            ctrl = (_ref.get().to_dict() or {}).get("control")
                        except Exception:
                            ctrl = None
                        while ctrl == "pause":
                            try:
                                _ref.update({"status": "paused"})
                            except Exception:
                                pass
                            time.sleep(1.0)
                            try:
                                ctrl = (_ref.get().to_dict() or {}).get("control")
                            except Exception:
                                ctrl = None
                        if ctrl == "stop":
                            raise _JobStopped()
                        try:
                            _ref.update({"status": "running", "progress": round(100 * done / total)})
                        except Exception:
                            pass
                    _t0 = time.time()
                    try:
                        patch = process_job(job, cb)
                    except _JobStopped:
                        patch = {"status": "cancelled", "finishedAt": time.time()}
                        log(f"  cancelled {snap.id} (stopped mid-run)")
                    _elapsed = time.time() - _t0
                    if patch.get("status") == "done":
                        patch["elapsed_s"] = round(_elapsed, 2)
                    if isinstance(patch.get("result"), dict):
                        shrink_to_fit(patch["result"], log=log, label=f"job {snap.id}")
                    self._save_job_doc(ref, patch, log)
                    # A completed grid sweep also lands in the Runs history, so web
                    # sweeps appear alongside the app's runs in users/{uid}/runs.
                    if job.get("type") in ("grid", "auto", "walkforward", "ai_optimize", "ai_evolve", "validate", "gate_validate", "book") and patch.get("status") == "done":
                        try:
                            self._persist_run(uid, job, patch.get("result") or {}, log, elapsed_s=_elapsed)
                        except Exception as _e:
                            log(f"  (persist-run failed: {_e})")
                    n += 1
        else:
            # No allowlist -> scan all users via collection_group (needs a one-time
            # COLLECTION_GROUP index; Firestore prints a create-link on first run).
            for snap in self.db.collection_group(self.col).where(filter=qf).stream():
                ref = snap.reference
                ref.update({"status": "running"})
                ref.update(process_job(snap.to_dict() or {}))
                n += 1
        return n


class CommandThread:
    """Daemon thread that serves READONLY_ACTIONS commands (get_bars, get_blotter,
    similar_setups)
    immediately, in parallel with a backtest job that may be running in the main watch
    loop for 30-90+ minutes. Without this, a web request for chart candles or a trade
    blotter sits queued behind the running job until it finishes — this thread polls
    independently on its own short cadence so those two read-only lookups never wait.

    Claim mechanism: an update-with-precondition write (Firestore `write_option
    (last_update_time=...)`), keyed off the exact snapshot this thread just read. If the
    doc changed since that read (e.g. another pass already claimed it), the precondition
    write is rejected and this thread backs off instead of double-serving. This is
    Firestore's normal optimistic-concurrency primitive — not a manual transaction, but
    equally atomic for a single-document claim like this one. Paired with the main loop's
    READONLY_ACTIONS skip (in run_commands) so there's no window where both loops try to
    serve the same doc.
    """

    POLL_SEC = 5.0

    def __init__(self, db, allow_uids, root, log=print):
        self.db = db
        self.allow = tuple(allow_uids or ())
        self.root = root
        self.log = log
        self._stop = False

    def _log(self, msg):
        try:
            self.log(f"  [cmd-thread] {msg}")
        except Exception:
            pass

    def _claim(self, snap):
        """Try to atomically flip one queued doc to running+claimedBy='cmdthread'.
        Returns the doc dict on success, or None if it lost the race (or any error) —
        never raises, so a flaky claim just means 'skip it, try again next poll'."""
        ref = snap.reference
        try:
            option = self.db.write_option(last_update_time=snap.update_time)
            ref.update({"status": "running", "claimedBy": "cmdthread"}, option=option)
            return snap.to_dict() or {}
        except Exception as e:
            self._log(f"claim lost (already served elsewhere): {type(e).__name__}: {e}")
            return None

    def _serve(self, ref, action, doc):
        """Serve one command exactly like the main loop's inline blocks did — same
        result/status/finishedAt shape, same json_safe."""
        payload = doc.get("payload") or {}
        if action == "get_blotter":
            from api.blotter import load_blotter_rows
            res = load_blotter_rows(self.root, payload, self._log)
        elif action == "get_bars":
            from api.bars import load_session_bars
            res = load_session_bars(self.root, payload, self._log)
        elif action == "similar_setups":
            from api.similar import find_similar_setups
            res = find_similar_setups(self.root, payload, self._log)
        elif action == "config_trades":
            from api.configs import load_config_trades
            res = load_config_trades(self.root, payload, self._log)
        else:
            res = {"ok": False, "error": f"unsupported readonly action {action!r}"}
        ref.update({"status": "done" if res.get("ok") else "error",
                    "result": json_safe(res), "finishedAt": time.time()})

    def _poll_uid(self, uid) -> int:
        from google.cloud.firestore_v1.base_query import FieldFilter
        col = self.db.collection("users").document(uid).collection("commands")
        qf = FieldFilter("status", "==", "queued")
        n = 0
        for snap in col.where(filter=qf).stream():
            doc = snap.to_dict() or {}
            action = doc.get("action")
            # filtered client-side (not a second `where`) so this stays the same simple
            # single-field status=='queued' query the main loop already uses -- adding a
            # second equality/IN clause here would need a composite index.
            if action not in READONLY_ACTIONS:
                continue
            claimed = self._claim(snap)
            if claimed is None:
                continue
            ref = snap.reference
            try:
                self._serve(ref, action, claimed)
            except Exception as e:
                # A crash inside one command must never take down the thread — mark that
                # one doc as errored and move on to the next.
                try:
                    ref.update({"status": "error", "error": f"{type(e).__name__}: {e}",
                                "finishedAt": time.time()})
                except Exception:
                    pass
                self._log(f"{action} for {uid} failed: {type(e).__name__}: {e}")
            n += 1
        return n

    def poll_once(self) -> int:
        """One pass over every allowlisted uid. Never raises — a per-uid failure (bad
        query, transient Firestore error, etc.) is logged and skipped so the rest of the
        allowlist and the next poll are unaffected."""
        n = 0
        for uid in self.allow:
            try:
                n += self._poll_uid(uid)
            except Exception as e:
                self._log(f"uid {uid} poll skipped: {type(e).__name__}: {e}")
        return n

    def run_forever(self):
        """Thread target: poll every POLL_SEC seconds until the process exits (daemon
        thread, so it never blocks shutdown). A crash anywhere in poll_once is swallowed
        here too, belt-and-suspenders on top of poll_once's own per-uid guard."""
        self._log("command thread: ON (get_bars/get_blotter/similar_setups/config_trades served in parallel with jobs)")
        while not self._stop:
            try:
                self.poll_once()
            except Exception as e:
                self._log(f"loop error (continuing): {type(e).__name__}: {e}")
            time.sleep(self.POLL_SEC)


def auto_pine(log=print, limit=25, provider=None):
    """Generate a .pine for every strategy that lacks one, via the keyless/local AI
    (module _PINE first, then claude-cli/ollama). Skips the scaffold fallback so a
    missing .pine is retried next startup if the AI was unreachable. Runs once on
    --watch start (and after auto-refresh). Once a .pine exists the strategy drops out
    of the list, so this is self-limiting."""
    from api.lib_commands import process_command
    missing = [s for s in ae.list_strategies() if not s.get("has_pine")]
    if not missing:
        log("[auto-pine] all strategies already have a .pine."); return 0
    log(f"[auto-pine] {len(missing)} strategy(ies) missing .pine — converting (keyless AI)…")
    made = 0
    for s in missing[:limit]:
        payload = {"file": s["file"], "no_scaffold": True}
        if provider:
            payload["provider"] = provider
        r = process_command("make_pine", payload, log=lambda *_: None)
        if r.get("ok"):
            made += 1; log(f"   ✓ {s['file']} -> {r.get('made')} (via {r.get('via')})")
        else:
            log(f"   – {s['file']}: {r.get('error')}")
    log(f"[auto-pine] {made}/{len(missing)} converted.")
    return made


def main(argv=None):
    ap = argparse.ArgumentParser(description="EDGELOG local job runner")
    ap.add_argument("--firestore", action="store_true", help="use Firestore queue")
    ap.add_argument("--cred", help="Firebase service-account JSON path")
    ap.add_argument("--allow-uid", action="append", default=[], help="allowlisted Firebase uid (repeatable)")
    ap.add_argument("--collection", default="backtests")
    ap.add_argument("--sync-runs", action="store_true", help="push run history to Firestore (also done on --watch start)")
    ap.add_argument("--watch", action="store_true", help="keep polling instead of one pass")
    ap.add_argument("--interval", type=float, default=3.0, help="poll seconds in --watch")
    ap.add_argument("--refresh-min", type=float, default=30.0,
                    help="auto-refresh masters (Yahoo + watch-folder ingest) every N minutes "
                         "while --watch (0 disables); also runs once on start")
    ap.add_argument("--nt-fills", default=os.environ.get("EDGELOG_NT_FILLS", r"C:\EdgeLog\fills.csv"),
                    help="path to the NinjaTrader fills CSV written by the EdgeLogExport AddOn "
                         "(default C:\\EdgeLog\\fills.csv). Synced into users/{uid}/trades.")
    ap.add_argument("--trades-sec", type=float, default=20.0,
                    help="auto-sync NinjaTrader trades every N seconds while --watch "
                         "(0 disables); also runs once on start")
    ap.add_argument("--webull-keys", default=os.environ.get("EDGELOG_WEBULL_KEYS", r"C:\EdgeLog\webull_keys.json"),
                    help="path to the Webull OpenAPI keys JSON (app_key/app_secret; kept OUTSIDE "
                         "the repo). Pull is self-gated to ONCE per NY day. Empty string disables.")
    ap.add_argument("--auto-pine", dest="auto_pine", action="store_true", default=False,
                    help="on --watch start, auto-generate a .pine for every strategy missing one "
                         "(default OFF — costs AI calls; the web MAKE PINE button is the per-click path)")
    ap.add_argument("--pine-provider", default=None,
                    help="AI provider for auto-pine: ollama (free local qwen, default) | claude-cli "
                         "(uses Claude credits) | anthropic")
    a = ap.parse_args(argv)

    def _refresh(tag="auto-refresh"):
        """Pull fresh Yahoo bars + ingest the TradingView watch-folder into masters
        (reusing optimizer.py's exact logic), then re-publish meta so the web Library
        shows the updated data + sync time. Network/IO errors never kill the runner."""
        try:
            from api.augur_refresh import run_auto_refresh
            print(f"[{tag}] refreshing masters (Yahoo + watch-folder)…")
            changes = run_auto_refresh()
            for line in changes[:12]:
                print(f"   {line}")
            print(f"[{tag}] {len(changes)} master(s) updated.")
            if a.firestore:
                q.sync_meta()
        except Exception as e:
            print(f"[{tag}] skipped: {type(e).__name__}: {e}")

    if a.firestore:
        q = FirestoreQueue(a.cred, a.collection, a.allow_uid, nt_fills=a.nt_fills,
                           webull_keys=a.webull_keys)
        print(f"EDGELOG runner v{_web_version()}: Firestore '{a.collection}', allow {a.allow_uid or 'ALL (no uid filter!)'}")
        if a.nt_fills:
            _present = os.path.exists(a.nt_fills)
            print(f"NinjaTrader trade sync: {a.nt_fills} "
                  f"({'found' if _present else 'not present yet — install the EdgeLogExport AddOn'}), "
                  f"every {a.trades_sec:g}s" if a.trades_sec > 0 else "(auto OFF)")
        if a.webull_keys:
            from api import webull_sync as _wb
            _wb_ok = _wb.load_keys(a.webull_keys) is not None
            print(f"Webull trade sync: {a.webull_keys} "
                  f"({'keys found' if _wb_ok else 'not configured yet — paste App Key/Secret into the file'}), "
                  f"once per NY day")
        if a.sync_runs or a.watch:
            print("syncing run history + meta…")
            try:
                q.sync_runs(); q.sync_meta()
            except Exception as e:
                # Don't let a transient error (e.g. Firestore 429 quota) kill the runner
                # before it reaches the watch loop — trade sync must still come up.
                print(f"[sync-runs] startup skipped: {type(e).__name__}: {e}")
        if a.sync_runs and not a.watch:
            return
    else:
        q = LocalQueue()
        print(f"EDGELOG runner v{_web_version()}: local queue at {JOBS_DIR}")

    # Trial-cache state on boot (docs/INCREMENTAL_BACKTEST_REUSE.md §3: "the runner
    # should log its epoch on boot"). Makes "is the cache actually on?" answerable
    # from runner.log alone rather than by guessing at the launcher's env.
    try:
        print(f"trial cache: {'ON' if TC.is_enabled() else 'OFF'} "
              f"(env AUGUR_TRIAL_CACHE={os.environ.get('AUGUR_TRIAL_CACHE','') or '(unset)'}, "
              f"epoch {ae.ENGINE_CACHE_EPOCH})")
    except Exception:
        pass

    if a.watch:
        # Parallel command server (item: "why do I wait behind a backtest?"): serves
        # get_bars/get_blotter off a separate daemon thread so those two web lookups
        # never queue behind a 30-90 min job in the main loop below. Firestore-only
        # (the LocalQueue test path has no commands subcollection to poll).
        if a.firestore:
            cmd_thread = CommandThread(q.db, a.allow_uid, ROOT, log=print)
            threading.Thread(target=cmd_thread.run_forever, daemon=True,
                             name="cmd-thread").start()
        # Job-queue / command listener conversion (item #36): on_snapshot listeners
        # replace the tight poll loop below with an event-driven wake, cutting idle
        # Firestore reads (~5,800/day at --interval 30 x2 queries). A slow backstop
        # poll (LISTENER_BACKSTOP_SEC) still runs underneath in case the channel
        # wedges silently — same failure mode as the web client's cmd-channel
        # (see MEMORY "EDGELOG cmd-channel lessons").
        listener_ok = False
        if a.firestore:
            try:
                listener_ok = q.start_listeners(log=print)
            except Exception as e:
                print(f"[listener] setup failed: {type(e).__name__}: {e}")
        if a.firestore:
            if listener_ok:
                print(f"queue listener: ON (backstop poll {LISTENER_BACKSTOP_SEC:g}s)")
            else:
                print(f"queue listener: FAILED -> polling every {a.interval:g}s")
        next_backstop = time.time() + LISTENER_BACKSTOP_SEC
        next_health = 0.0   # first pass runs immediately, then every HEALTH_SEC
        next_bridge = 0.0   # first pass runs immediately, then every BRIDGE_SEC
        # Auto-refresh data on start and on a timer — hands-free, like the desktop
        # app does on open. Runs in the same loop (infrequent + bounded), so it
        # briefly pauses job polling while it pulls; that's fine at a 30-min cadence.
        next_refresh = 0.0
        if a.refresh_min > 0:
            _refresh("startup"); next_refresh = time.time() + a.refresh_min * 60
        next_trades = 0.0
        if a.firestore and a.trades_sec > 0:
            try:
                q.sync_trades()
            except Exception as e:
                print(f"[nt-sync] startup skipped: {type(e).__name__}: {e}")
            try:
                q.sync_webull()
            except Exception as e:
                print(f"[webull] startup skipped: {type(e).__name__}: {e}")
            next_trades = time.time() + a.trades_sec
        if a.auto_pine:
            try:
                if auto_pine(provider=a.pine_provider) and a.firestore:
                    q.sync_meta()
            except Exception as e:
                print(f"[auto-pine] skipped: {type(e).__name__}: {e}")
        print("watching… (Ctrl+C to stop)")
        while True:
            # Decide WHY (if at all) we should hit the queued-docs query this tick:
            # a listener wake, the backstop timer, or — no listener (LocalQueue, or
            # the Firestore listener failed to come up) — every tick, same as before.
            listener_active = a.firestore and listener_ok
            if listener_active and q.wake.is_set():
                q.wake.clear()
                poll_reason = "listener"
            elif not listener_active:
                poll_reason = "poll"
            elif time.time() >= next_backstop:
                poll_reason = "backstop"
            else:
                poll_reason = None
            done = 0
            if poll_reason:
                try:
                    done = q.run_once()
                except Exception as _e:
                    print(f"[queue] skipped: {type(_e).__name__}: {_e}"); done = 0
                if a.firestore:
                    try:
                        done += q.run_commands()
                    except Exception as _e:
                        print(f"[commands] skipped: {type(_e).__name__}: {_e}")
                if poll_reason == "backstop":
                    next_backstop = time.time() + LISTENER_BACKSTOP_SEC
                    if done:
                        print(f"[backstop] found {done} job(s)/command(s) the "
                              f"listener missed -- channel may be stale")
            if a.refresh_min > 0 and time.time() >= next_refresh:
                _refresh(); next_refresh = time.time() + a.refresh_min * 60
            if a.firestore and a.trades_sec > 0 and time.time() >= next_trades:
                try:
                    done += q.sync_trades()
                except Exception as e:
                    print(f"[nt-sync] skipped: {type(e).__name__}: {e}")
                try:
                    # self-gated to once per NY day inside webull_sync — free otherwise
                    done += q.sync_webull()
                except Exception as e:
                    print(f"[webull] skipped: {type(e).__name__}: {e}")
                next_trades = time.time() + a.trades_sec
            if a.firestore and _paper is not None:
                try:
                    _paper.maybe_run_eod(q)
                except Exception as e:
                    print(f"[paper] hook error: {type(e).__name__}: {e}")
            # Data-freshness watchdog. Hourly, one tiny doc per uid — the NQ 10s capture
            # died 2026-08-11 and the Yahoo top-up had been off for six weeks, and neither
            # surfaced anywhere the owner looks. See api/data_health.py.
            if a.firestore and time.time() >= next_health:
                try:
                    from api import data_health
                    # allow_uid is argparse action="append" -> a LIST; .split() on it
                    # threw AttributeError and this block never once published.
                    for _uid in (a.allow_uid or []):
                        if _uid.strip():
                            data_health.publish(q.db, _uid.strip())
                except Exception as e:
                    print(f"[data-health] skipped: {type(e).__name__}: {e}")
                next_health = time.time() + HEALTH_SEC
            # NinjaTrader bridge watchdog. NT's own auto-update silently deleted every
            # strategy instance on 2026-08-14 and nobody could see it without alt-tabbing
            # into NT and looking. See api/nt_bridge_pub.py.
            if a.firestore and time.time() >= next_bridge:
                try:
                    from api import nt_bridge_pub
                    # a.allow_uid is already a list (argparse action="append"), not a
                    # comma string -- unlike the data_health block above, do not .split() it.
                    for _uid in (a.allow_uid or []):
                        if _uid and _uid.strip():
                            nt_bridge_pub.publish(q.db, _uid.strip())
                except Exception as e:
                    print(f"[nt-bridge] skipped: {type(e).__name__}: {e}")
                next_bridge = time.time() + BRIDGE_SEC
            if not done:
                if listener_active:
                    # Blocks until a listener wake, or a.interval elapses — whichever
                    # is first — so refresh_min/trades_sec/paper stay on their
                    # existing cadence while the queued-docs query itself stays idle
                    # (no read) unless the listener actually signals a change.
                    q.wake.wait(timeout=a.interval)
                else:
                    time.sleep(a.interval)
    else:
        done = q.run_once()
        print(f"processed {done} job(s).")


if __name__ == "__main__":
    main()
