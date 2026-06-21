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

import augur_engine as ae
from .util import json_safe

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JOBS_DIR = os.path.join(ROOT, "augur_jobs")


def _anthropic_key():
    """Read the Anthropic API key from local augur_config.json (never from a job doc)."""
    try:
        cfg = json.load(open(os.path.join(ROOT, "augur_config.json"), encoding="utf-8"))
        return cfg.get("anthropic_key") or None
    except Exception:
        return None


def process_job(job: dict, progress_cb=None) -> dict:
    """Run one job through the engine; return a result patch to merge back.
    job['type']: 'backtest' (default, single config) or 'grid' (param sweep)."""
    jtype = job.get("type", "backtest")
    # optional date-range window (YYYY-MM-DD); blank/missing => full master.
    df_from = job.get("date_from") or None
    df_to = job.get("date_to") or None
    try:
        if jtype == "grid":
            r = ae.run_grid(
                job["strategy"], instrument=job.get("instrument"),
                timeframe=job.get("timeframe", "5m"), session=job.get("session", "rth"),
                source=job.get("source"), preset=job.get("preset"), grid=job.get("grid"),
                date_from=df_from, date_to=df_to,
                cost_pts=float(job.get("cost_pts", 0) or 0),
                min_trades=int(job.get("min_trades", 30)), top_n=int(job.get("top_n", 10)),
                workers=int(job.get("workers", 1)), progress_cb=progress_cb,
                compute_dsr=bool(job.get("dsr", False)), mc_sims=int(job.get("mc_sims", 0)),
                compute_regime=bool(job.get("regime", True)),
                compute_neighbors=bool(job.get("neighbors", True)))
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
                compute_dsr=bool(job.get("dsr", False)), mc_sims=int(job.get("mc_sims", 0)),
                compute_regime=bool(job.get("regime", True)),
                compute_neighbors=bool(job.get("neighbors", True)))
        elif jtype == "validate":
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
                thresholds=job.get("thresholds"), progress_cb=progress_cb)
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
                mc_sims=int(job.get("mc_sims", 0)))
    except Exception as e:
        return {"status": "error", "error": f"{type(e).__name__}: {e}",
                "finishedAt": time.time()}
    if r is None:
        return {"status": "error", "error": "no result (0 trades or invalid window)",
                "finishedAt": time.time()}
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

    def __init__(self, cred_path=None, collection="backtests", allow_uids=()):
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

    def sync_runs(self, log=print) -> int:
        """Push run history from optimizer_history.db up to users/{uid}/runs so the web
        UI can browse it. One doc per run (keyed by run id), with detail blobs parsed.
        Skips the equity/full_results blobs on any run whose doc would exceed ~900KB."""
        import json as _json
        total = 0
        for uid in (self.allow or []):
            col = self.db.collection("users").document(uid).collection("runs")
            batch = self.db.batch(); pending = 0
            for r in ae.list_runs():
                doc = ae.get_run(r["id"])
                if doc is None:
                    continue
                doc = json_safe(doc)
                if len(_json.dumps(doc, default=str)) > 900_000:
                    doc.pop("full_results", None); doc.pop("equity", None)
                batch.set(col.document(str(r["id"])), doc)
                pending += 1; total += 1
                if pending >= 400:          # Firestore batch cap is 500
                    batch.commit(); batch = self.db.batch(); pending = 0
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
                strats.append({**s, "presets": presets, "params": pspec,
                               "roadmap": _roadmaps.get(s["file"], {})})
            meta.document("strategies").set(json_safe({"list": strats}))
            keep = ("name", "instrument", "timeframe", "session", "source",
                    "rows", "date_from", "date_to")
            masters = [{k: m.get(k) for k in keep} for m in ae.list_masters()]
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

    def _persist_run(self, uid, job, result, log=print):
        """Save a completed web grid sweep into users/{uid}/runs (Runs history),
        shaped like the app's synced runs so the Runs tab renders it identically."""
        mult = float(job.get("mult", 20) or 20)
        best = result.get("best") or {}
        rid = int(time.time())
        doc = json_safe({
            "id": rid,
            "timestamp": time.strftime("%Y-%m-%d %H:%M"),
            "strategy": job.get("strategy", ""),
            "instrument": job.get("instrument", ""),
            "timeframe": job.get("timeframe", ""),
            "scope": ({"ai_optimize": "AI optimize", "ai_evolve": "AI evolve",
                       "auto": "Auto-Optimize", "walkforward": "Walk-Forward",
                       "validate": "🧭 Auto-Validate"}
                      .get(job.get("type"), job.get("preset", "web sweep"))),
            # carry the validate report card into run history so Results/Library can show it
            "validate": result.get("validate"),
            "data_source": job.get("source", ""),
            "rounds": result.get("rounds"), "best_oos_pnl": result.get("best_oos_pnl"),
            "evolved_file": result.get("evolved_file"),
            "n_combos": result.get("n_combos"), "n_valid": result.get("n_valid"),
            "bars": result.get("bars"),
            "best_pnl_pts": best.get("total_pnl"),
            "best_pnl_usd": (best.get("total_pnl") or 0) * mult,
            "best_pf": best.get("profit_factor"),
            "best_win_rate": best.get("win_rate"),
            "best_trades": best.get("num_trades"),
            "best_dd_usd": (best.get("max_drawdown") or 0) * mult,
            "best_params": result.get("best_params"),
            "top10_results": result.get("top"),
            "equity": result.get("equity"),
            "multiplier": mult,
            # cost realism + date window so Results/roadmap can show & auto-derive them
            "commission_usd": job.get("commission_usd"),
            "slippage_pts": job.get("slippage_pts"),
            "cost_pts": job.get("cost_pts"),
            "date_from": job.get("date_from") or result.get("date_from"),
            "date_to": job.get("date_to") or result.get("date_to"),
            "dsr": result.get("dsr"), "mc": result.get("mc"),
            "regime": result.get("regime"), "neighborhood": result.get("neighborhood"),
            "source_web": True,
        })
        self.db.collection("users").document(uid).collection("runs").document(str(rid)).set(doc)
        log(f"    -> saved to Runs history (#{rid})")

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
                ref.update({"status": "running"})
                doc = snap.to_dict() or {}
                action = doc.get("action")
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
                    ref.update({"status": "running", "progress": 0})
                    job = snap.to_dict() or {}
                    log(f"  running {snap.id}: {job.get('type','backtest')} "
                        f"{job.get('strategy')} {job.get('instrument')}…")
                    last = [0.0]

                    def cb(done, total, _ref=ref, _last=last):
                        if total and time.time() - _last[0] > 1.5:
                            _last[0] = time.time()
                            try:
                                _ref.update({"progress": round(100 * done / total)})
                            except Exception:
                                pass
                    patch = process_job(job, cb)
                    ref.update(patch)
                    # A completed grid sweep also lands in the Runs history, so web
                    # sweeps appear alongside the app's runs in users/{uid}/runs.
                    if job.get("type") in ("grid", "auto", "walkforward", "ai_optimize", "ai_evolve", "validate") and patch.get("status") == "done":
                        try:
                            self._persist_run(uid, job, patch.get("result") or {}, log)
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
    ap = argparse.ArgumentParser(description="AUGUR local job runner")
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
        q = FirestoreQueue(a.cred, a.collection, a.allow_uid)
        print(f"AUGUR runner: Firestore '{a.collection}', allow {a.allow_uid or 'ALL (no uid filter!)'}")
        if a.sync_runs or a.watch:
            print("syncing run history + meta…"); q.sync_runs(); q.sync_meta()
        if a.sync_runs and not a.watch:
            return
    else:
        q = LocalQueue()
        print(f"AUGUR runner: local queue at {JOBS_DIR}")

    if a.watch:
        # Auto-refresh data on start and on a timer — hands-free, like the desktop
        # app does on open. Runs in the same loop (infrequent + bounded), so it
        # briefly pauses job polling while it pulls; that's fine at a 30-min cadence.
        next_refresh = 0.0
        if a.refresh_min > 0:
            _refresh("startup"); next_refresh = time.time() + a.refresh_min * 60
        if a.auto_pine:
            try:
                if auto_pine(provider=a.pine_provider) and a.firestore:
                    q.sync_meta()
            except Exception as e:
                print(f"[auto-pine] skipped: {type(e).__name__}: {e}")
        print("watching… (Ctrl+C to stop)")
        while True:
            done = q.run_once()
            if a.firestore:
                try:
                    done += q.run_commands()
                except Exception as _e:
                    print(f"[commands] skipped: {type(_e).__name__}: {_e}")
            if a.refresh_min > 0 and time.time() >= next_refresh:
                _refresh(); next_refresh = time.time() + a.refresh_min * 60
            if not done:
                time.sleep(a.interval)
    else:
        done = q.run_once()
        print(f"processed {done} job(s).")


if __name__ == "__main__":
    main()
