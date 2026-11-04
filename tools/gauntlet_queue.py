"""GAUNTLET queue door (scope C3, owner GO 11-03): one prereg -> one co-tuned Auto-Validate job.

The prereg's knob must already be IN the strategy file's DEFAULT_PARAMS with a real range, so the
900-trial search tunes it together with every crown knob (never frozen at a grid best). The job
is the house standard: 900 trials (OWNER RULE, never lowered), 8 walk-forward folds, 12-month
lockbox, a PINNED end date (a blank one slides with every top-up - test 196, 11-02), the master
selected by its registered source tag.

Refuses when: the prereg file is missing; the strategy is not in the shared checkout (the runner
reads it); the knob is not a ranged DEFAULT_PARAMS entry; the master is not registered; the same
strategy + instrument + window is already queued / running / paused; the queue is deeper than 12.

    python tools/gauntlet_queue.py --prereg <file.md> --strategy X.py --knob t_end_min \
        --instrument NQ --timeframe 1m --session eth --source db_noadj_eth --cost 0.783 \
        --mult 20 --date-from 2015-07-01 --date-to 2026-06-30 [--dry]
"""
import argparse
import datetime
import os
import sys
import time

REPO = r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"
UID = "IO0K35JpLIcH9YK4C0pMNYUzZOM2"
PREREG_DIR = r"C:\EdgeLog\manager\prereg"
LOG = r"C:\EdgeLog\_anatomy_cache\gauntlet\queued.txt"
MAX_DEPTH = 12


def build_job(a):
    return dict(
        type="validate", strategy=a.strategy,
        instrument=a.instrument, timeframe=a.timeframe, session=a.session, source=a.source,
        commission_usd=0.0, slippage_pts=0.0, cost_pts=a.cost, mult=a.mult,
        date_from=a.date_from, date_to=a.date_to, date_to_pinned=a.date_to,
        lockbox_months=12, wf_folds=8, warm_days=300,
        n_trials=900, min_trades=30, mc_sims=2000, n_rounds=0, select_oos_topk=10,
        discover="auto", provider="ollama",
        dsr=True, neighbors=True, regime=True, pills=True, context=True, equity_points=400,
    )


def check_knob(strategy_path, knob):
    sys.path.insert(0, REPO)
    from augur_engine.strategies import load_strategy
    mod = load_strategy(strategy_path)
    spec = (getattr(mod, "DEFAULT_PARAMS", {}) or {}).get(knob)
    if not isinstance(spec, dict):
        return "knob %r is not in %s DEFAULT_PARAMS" % (knob, os.path.basename(strategy_path))
    if spec.get("min") is None or spec.get("max") is None or spec["min"] == spec["max"]:
        return "knob %r has no range (min %r max %r) - it would be frozen, not co-tuned" % (
            knob, spec.get("min"), spec.get("max"))
    return None


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--prereg", required=True)
    ap.add_argument("--strategy", required=True)
    ap.add_argument("--knob", required=True, action="append")
    ap.add_argument("--instrument", required=True)
    ap.add_argument("--timeframe", required=True)
    ap.add_argument("--session", required=True)
    ap.add_argument("--source", required=True)
    ap.add_argument("--cost", type=float, required=True)
    ap.add_argument("--mult", type=float, required=True)
    ap.add_argument("--date-from", required=True)
    ap.add_argument("--date-to", required=True)
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args(argv)

    pre = a.prereg if os.path.isabs(a.prereg) else os.path.join(PREREG_DIR, a.prereg)
    if not os.path.isfile(pre):
        sys.exit("ABORT - no prereg file %s (no run without one, scope C1)" % pre)
    sp = os.path.join(REPO, "augur_strategies", a.strategy)
    if not os.path.isfile(sp):
        sys.exit("ABORT - %s is not in the shared checkout; ship it first" % a.strategy)
    for k in a.knob:
        err = check_knob(sp, k)
        if err:
            sys.exit("ABORT - " + err)

    os.chdir(REPO)
    from augur_engine import data as D
    m = D.find_master(a.instrument, a.timeframe, a.session, a.source)
    if not m or m.get("source") != a.source:
        sys.exit("ABORT - no registered master %s %s %s %s" % (
            a.instrument, a.timeframe, a.session, a.source))
    print("master %s id %s %s..%s" % (m.get("filename"), m.get("id"), m.get("date_from"),
                                      m.get("date_to")))

    tag = "GAUNTLET %s co-tuned [%s]" % (os.path.splitext(os.path.basename(pre))[0],
                                         ",".join(a.knob))
    job = build_job(a)
    job.update(status="queued", progress=0, preset=tag,
               note=("%s. Prereg %s. Knob(s) %s IN the search space next to every crown knob "
                     "(scope C3). %s %s %s %s, window %s..%s pinned, 12-month lockbox, 8 folds, "
                     "900 trials (OWNER RULE), cost %s pts x %s. Verdict by tools/verdict.py; "
                     "lockbox veto-only. Driver tools/gauntlet_queue.py."
                     % (tag, pre, ",".join(a.knob), a.instrument, a.timeframe, a.session,
                        a.source, a.date_from, a.date_to, a.cost, a.mult)))
    if a.dry:
        for k in sorted(job):
            print("    %-16s %s" % (k, job[k]))
        return

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
                print("attempt %d blocked (%s); waiting %ds" % (i + 1, type(e).__name__, wait))
                if i == tries - 1:
                    raise
                time.sleep(wait)

    live = _retry(lambda: [(d.id, d.to_dict() or {}) for st in ("queued", "running", "paused")
                           for d in u.collection("backtests")
                           .where(filter=_FF("status", "==", st)).stream()])
    for did, x in live:
        if (x.get("strategy") == a.strategy and x.get("instrument") == a.instrument
                and str(x.get("date_from")) == a.date_from
                and str(x.get("date_to")) == a.date_to):
            sys.exit("ABORT - %s already %s for this window" % (did, x.get("status")))
    if len(live) >= MAX_DEPTH:
        sys.exit("ABORT - queue too deep (%d)" % len(live))
    job["createdAt"] = datetime.datetime.now(datetime.timezone.utc)
    ref = u.collection("backtests").document()
    _retry(lambda: ref.set(job))
    print("queued %s (queue depth before: %d)" % (ref.id, len(live)))
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    with open(LOG, "a") as fh:
        fh.write("%s %s %s\n" % (datetime.datetime.now(datetime.timezone.utc)
                                 .isoformat(timespec="seconds"), ref.id, tag))


if __name__ == "__main__":
    main()
