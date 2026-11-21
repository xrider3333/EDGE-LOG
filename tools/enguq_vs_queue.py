"""AUTO-VALIDATE 900 -- ENGU-Q 1m ETH VS: the crown's signal scored at CONSTANT DOLLAR RISK.

WHY THIS RUN EXISTS, AND WHY IT EXISTS OVER TWO CLOSE VOTES. Arm C of the 11-21 sizing round sizes
each trade at 35 points divided by that trade's OWN initial stop distance (clamped 0.25-4.0 units),
so every trade risks about the same number of dollars instead of the same number of contracts. On
the frozen #335 crown over 2016-07-01..2025-06-30 that took the worst drawdown from 38.9 percent of
a fixed $100k down to 15.3 percent, while net fell from $379,469 to $203,513 -- so at the owner's
35 percent drawdown cap it scales to about $464k against the base's $341,671, roughly +36 percent,
and net per $1 of drawdown goes 9.76 -> 13.29.

Both this lane and VERIFIER voted to CLOSE it, because the house shuffle null says the gain is
drawdown SHAPE and not aim (see WARNINGS). MANAGER ruled the other way on the owner's 11-14
standing rule -- luck and null statistics are WARNINGS, not kills, and the book is judged on $/yr
at the drawdown cap -- on the grounds that a drawdown-shape gain fixed EX ANTE, with no look-ahead,
is a legitimate book lift even when it is not aim alpha. That ruling is why this is queued, and the
null below is printed beside the grade rather than used to kill it.

THE WARNINGS, WRITTEN HERE BEFORE THE RUN SO THEY CANNOT BE DISCOVERED AFTER A GOOD GRADE.
  THE SHUFFLE NULL. 2,000 permutations keep the arm's own size multiset and re-aim it at random
    (the house rule from fixed-sizing r1, 2026-09-28). Arm C sits at the 94.0th percentile and
    beats 1,879 of 2,000 -- below the 95th. Worse than the percentile: the null's MEDIAN RAW NET is
    $552,309 against the arm's $207,339, because permuting the sizes barely moves net, it moves the
    drawdown. 499 of 2,000 random aims also beat the base at the cap. Report explicitly whether the
    graded run beats the null's 95th percentile at the cap ($476,311 on the frozen read).
  WHY THE NET FALLS. ENGU-Q's biggest winners ARE its wide-stop trades, so sizing inversely to the
    stop shrinks exactly the trades that carry the leg. That is the mechanism, and it is also the
    finding already sent to Book: this leg's drawdown cannot be cut by weight without giving up the
    money nearly 1 for 1.
  THE 10-NQ CAP. At the 35 percent scale the arm needs 3.3 NQ on average and 9.1 NQ at its peak,
    which is most of the owner's 10-contract ceiling before any other NQ leg is counted. A pass here
    does not mean it fits the book at that scale.
  THE EQUAL-DRAWDOWN READ IS POST-HOC ON THE SCREEN. The screen was designed around net; the
    equal-drawdown comparison that makes C look good was applied after the arms were run. It is
    PRE-REGISTERED here, which is the point of this file, but the frozen read itself is not a
    confirmation of it.

PRE-SET GRADE, written before the run reads so it cannot be argued into a pass:
  PRIMARY  equal-drawdown net versus the base's $341,671 at the 35 percent cap. Above it on the
           walk-forward stretch is the lift; below it the arm is closed.
  BESIDE IT  walk-forward folds won, DD5 from augur_engine.drawdowns, and the null line above,
           including whether it clears the null's 95th at the cap. The null never kills (owner
           11-14) but it is always printed.
  Lockbox is veto only and is not read in this lane's report.

COST IS PINNED AT 0.783 AND A RE-COST IS INVALID, NOT MERELY DIFFERENT. The engine charges cost
ONCE PER TRADE with no notion of size (augur_engine.engine._apply_costs), so the strategy emits
`size * gross - (size - 1) * vs_cost_pts` and the engine's own single subtraction completes it to
`size * (gross - cost)`. That identity holds ONLY when the job's cost_pts equals the file's
vs_cost_pts, 0.783. At any other cost each trade is mis-charged by exactly
(size - 1) * (job_cost - vs_cost), and a job CHEAPER than 0.783 UNDER-charges, which FLATTERS the
run. So a double-cost or 0.283 stress cell on this file is INVALID and must be marked invalid
rather than read. The correct way to stress the cost here is to re-ship the file with a new
vs_cost_pts default and run it at a matching cost_pts, not to move the job's cost alone.
This is pinned by tests/test_enguq_vs_sizing.py::test_a_cost_mismatch_is_visible_and_signed.

WHAT IS SEARCHED AND WHAT IS FIXED. The four sizing knobs are FIXED (min == max): vs_target_pts
35.0, vs_min_u 0.25, vs_max_u 4.0, vs_cost_pts 0.783. The 14 parent entry knobs keep the crown's
own ranges exactly, unchanged, so the search explores the crown's space and the SIZING is not
tuned -- that is the whole point of the arm, and tuning the sizing is how arm A bought net with
leverage. The file is therefore not a pinned single-config file and Auto-Validate accepts it.

CHANGES FROM THE CROWN'S OWN VALIDATE, AND NOTHING ELSE: the strategy file, from
ENGUQ_1M_ETH_R2_1_0.py to its sibling ENGUQ_1M_ETH_VS_1_0.py (v91.66, 7e3eff99, VERIFIER PASS,
0 must-fix). Same instrument NQ 1m ETH, same master ADJ_NQ_1m_ETH id 66, same cost 0.783, same
mult 20, same window, same 8 folds, same 12-month lockbox, same 900 trials -- the owner budget,
never lowered. Runs on the DESKTOP workers per MANAGER.

    python tools/enguq_vs_queue.py --dry --on-desktop
    python tools/enguq_vs_queue.py --on-desktop
"""
import argparse
import datetime
import os
import sys
import time

REPO = r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"
os.chdir(REPO)
sys.path.insert(0, REPO)
from tools.job_host import add_host_args, apply_host          # noqa: E402

UID = "IO0K35JpLIcH9YK4C0pMNYUzZOM2"
TAG = "AUTO-VALIDATE 900 ENGU-Q VS constant dollar risk (sizing round 11-21, MANAGER ruling (a))"
STRATEGY = "ENGUQ_1M_ETH_VS_1_0.py"
PARENT = "ENGUQ_1M_ETH_R2_1_0.py"
MASTER_ID, MASTER_FILE = 66, "ADJ_NQ_1m_ETH.csv"
VS_COST = 0.783
LOGDIR = r"C:\EdgeLog\_anatomy_cache\bookq\enguq_screen_abc"

JOB = dict(
    type="validate", strategy=STRATEGY,
    instrument="NQ", timeframe="1m", session="eth", source="db_adj_eth",
    commission_usd=0.0, slippage_pts=0.0, cost_pts=VS_COST, mult=20,
    date_from="2010-06-07", date_to="2026-06-30",
    lockbox_months=12, wf_folds=8, warm_days=300,
    n_trials=900, min_trades=30, mc_sims=2000, n_rounds=0, select_oos_topk=10,
    discover="auto", provider="ollama",
    dsr=True, neighbors=True, regime=True, pills=True, context=True, equity_points=400,
)

NOTE = (
    TAG + ". The crown's own signal scored at CONSTANT DOLLAR RISK: each trade sized 35 points "
    "divided by its OWN initial stop distance, clamped 0.25-4.0 units, so every trade risks about "
    "the same dollars instead of the same contracts. Frozen read on #335, window "
    "2016-07-01..2025-06-30: worst drawdown falls from 38.9 pct of a fixed $100k to 15.3 pct while "
    "net falls from $379,469 to $203,513, so at the owner 35 pct cap it scales to $464,331 against "
    "the base's $341,671, about +36 pct; net per $1 of drawdown 9.76 to 13.29. GRADE AS "
    "PRE-REGISTERED: primary is equal-drawdown net versus $341,671 at the 35 pct cap, with "
    "walk-forward folds won and DD5 beside it. WARNINGS STATED BEFORE THE GRADE, warnings and never "
    "kills per the owner 11-14 rule, which is why this is queued over two close votes: on 2,000 "
    "shuffles of its own size multiset re-aimed at random the arm sits at the 94.0th percentile, "
    "BELOW the 95th; the null's MEDIAN RAW NET is $552,309 against the arm's $207,339, because "
    "permuting the sizes barely moves net, it moves the drawdown; and 499 of 2,000 random aims also "
    "beat the base at the cap. Report explicitly whether the graded run clears the null's 95th at "
    "the cap, $476,311 on the frozen read. The mechanism is that ENGU-Q's biggest winners ARE its "
    "wide-stop trades, so inverse-stop sizing shrinks exactly the trades that carry the leg. Also at "
    "the 35 pct scale the arm needs 3.3 NQ mean and 9.1 NQ peak, most of the owner's 10-contract "
    "ceiling before any other NQ leg. COST IS PINNED AT 0.783 AND A RE-COST IS INVALID: the engine "
    "charges cost once per trade with no notion of size, so the file emits size*gross - "
    "(size-1)*vs_cost_pts and the engine's single subtraction completes it to size*(gross-cost) ONLY "
    "at cost_pts 0.783. At any other cost each trade is mis-charged by exactly "
    "(size-1)*(job_cost-0.783), and a cheaper job cost UNDER-charges and FLATTERS the run, so any "
    "re-costed stress cell such as 2x cost or 0.283 must be marked INVALID rather than read; stress "
    "the cost by re-shipping the file with a new vs_cost_pts and a matching cost_pts. The four "
    "sizing knobs are FIXED (min == max) and the 14 parent entry knobs keep the crown's ranges "
    "exactly, so the search explores the crown's space and the sizing is never tuned -- tuning the "
    "sizing is how arm A bought net with leverage and was parked. CHANGES FROM THE CROWN'S VALIDATE "
    "AND NOTHING ELSE: the strategy file, ENGUQ_1M_ETH_R2_1_0.py to its sibling "
    "ENGUQ_1M_ETH_VS_1_0.py at v91.66 7e3eff99 (VERIFIER PASS, 0 must-fix); same NQ 1m ETH, master "
    "ADJ_NQ_1m_ETH id 66, cost 0.783, mult 20, window, 8 folds, 12-month lockbox and 900 trials, the "
    "owner budget never lowered. Lockbox veto only. Nothing live or paper changes. Desktop workers "
    "per MANAGER. Driver tools/enguq_vs_queue.py."
)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true")
    add_host_args(ap)
    a = ap.parse_args()

    spath = os.path.join(REPO, "augur_strategies", STRATEGY)
    if not os.path.exists(spath):
        sys.exit("ABORT - not in the shared checkout, the runner would not see it: " + spath)
    if "_PINNED" in STRATEGY:
        sys.exit("ABORT - Auto-Validate never runs on a pinned file")

    import importlib.util
    spec = importlib.util.spec_from_file_location("vs", spath)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    dp = mod.DEFAULT_PARAMS
    numeric = [k for k, s in dp.items() if s.get("type") in ("int", "float")]
    open_knobs = [k for k in numeric if float(dp[k]["min"]) < float(dp[k]["max"])]
    if not open_knobs:
        sys.exit("ABORT - every numeric knob has min == max; this is a pinned file in disguise")
    print("file OK: %s, %d numeric knobs, %d with a real range" % (STRATEGY, len(numeric), len(open_knobs)))

    # the sizing must NOT be searchable - that is what separates this arm from arm A's leverage
    for k in ("vs_target_pts", "vs_min_u", "vs_max_u", "vs_cost_pts"):
        if float(dp[k]["min"]) != float(dp[k]["max"]):
            sys.exit("ABORT - sizing knob %s has a range; the sizing must be fixed ex ante" % k)
    # the cost identity only holds when the job's cost equals the file's declared cost
    if abs(float(dp["vs_cost_pts"]["default"]) - float(JOB["cost_pts"])) > 1e-12:
        sys.exit("ABORT - cost identity broken: file vs_cost_pts %s, job cost_pts %s. Every trade "
                 "would be mis-charged by (size-1)*(job-vs) and a cheaper job cost FLATTERS the run."
                 % (dp["vs_cost_pts"]["default"], JOB["cost_pts"]))
    print("sizing fixed OK: target %s, clamp %s-%s, cost %s == job cost %s"
          % (dp["vs_target_pts"]["default"], dp["vs_min_u"]["default"], dp["vs_max_u"]["default"],
             dp["vs_cost_pts"]["default"], JOB["cost_pts"]))

    # the entry space must be the crown's own, unchanged
    pspec = importlib.util.spec_from_file_location("pa", os.path.join(REPO, "augur_strategies", PARENT))
    pmod = importlib.util.module_from_spec(pspec)
    pspec.loader.exec_module(pmod)
    drift = []
    for k, v in pmod.DEFAULT_PARAMS.items():
        if not isinstance(v.get("min"), (int, float)):
            continue
        mine = dp.get(k)
        if not mine or (mine["min"], mine["max"], mine["default"]) != (v["min"], v["max"], v["default"]):
            drift.append(k)
    if drift:
        sys.exit("ABORT - the parent's ranges were not carried over unchanged: %s" % drift)
    print("parent ranges OK: %s knobs identical to %s" % (len(pmod.DEFAULT_PARAMS), PARENT))

    from augur_engine import data as D
    m = D.find_master(JOB["instrument"], JOB["timeframe"], JOB["session"], JOB["source"])
    if not m or m.get("filename") != MASTER_FILE or int(m.get("id") or 0) != MASTER_ID:
        sys.exit("ABORT - the roll-corrected NQ 1m ETH master is not id %s %s: %r" % (MASTER_ID, MASTER_FILE, m))
    if str(m.get("date_to"))[:10] < JOB["date_to"]:
        sys.exit("ABORT - master ends %s, before the window end %s" % (m.get("date_to"), JOB["date_to"]))
    if str(m.get("date_from"))[:10] > JOB["date_from"]:
        sys.exit("ABORT - master starts %s, after the window start %s" % (m.get("date_from"), JOB["date_from"]))
    print("master OK: id %s %s rows=%s %s..%s" % (m.get("id"), m.get("filename"), m.get("rows"),
                                                  m.get("date_from"), m.get("date_to")))

    import firebase_admin
    from firebase_admin import credentials, firestore
    from google.api_core import exceptions as _gx
    from google.cloud.firestore_v1.base_query import FieldFilter as _FF
    if not firebase_admin._apps:
        firebase_admin.initialize_app(credentials.Certificate(os.path.join(REPO, "serviceAccount.json")))
    u = firestore.client().collection("users").document(UID)

    def _retry(fn, tries=4, wait=90):
        for i in range(tries):
            try:
                return fn()
            except (_gx.ResourceExhausted, _gx.ServiceUnavailable, _gx.DeadlineExceeded) as e:
                print("attempt %d blocked (%s); waiting %ds" % (i + 1, type(e).__name__, wait), flush=True)
                if i == tries - 1:
                    raise
                time.sleep(wait)

    live = _retry(lambda: [(d.id, d.to_dict() or {}) for st in ("queued", "running", "paused")
                           for d in u.collection("backtests").where(filter=_FF("status", "==", st)).stream()])
    print("queue depth", len(live))
    for did, x in live:
        print("  live %s %-8s %-28s %-4s %s..%s" % (did, x.get("status"), str(x.get("strategy"))[:28],
                                                    x.get("instrument"), x.get("date_from"), x.get("date_to")))
    clash = []
    for did, x in live:
        if TAG in str(x.get("note") or "") or TAG in str(x.get("preset") or ""):
            clash.append("%s already carries this label (%s)" % (did, x.get("status")))
        if (x.get("strategy") == STRATEGY and str(x.get("instrument")) == JOB["instrument"]
                and str(x.get("date_from")) == JOB["date_from"] and str(x.get("date_to")) == JOB["date_to"]):
            clash.append("%s: same file, instrument and window already %s" % (did, x.get("status")))
    if clash:
        sys.exit("ABORT - would double-queue:\n  " + "\n  ".join(sorted(set(clash))))
    if len(live) > 9:
        sys.exit("ABORT - queue too deep (%d)" % len(live))

    job = apply_host(dict(JOB, status="queued", progress=0,
                          preset="%s: sizing FIXED ex ante, parent ranges unchanged, cost pinned 0.783" % TAG,
                          note=NOTE), a)
    if a.dry:
        print("\nDRY RUN - nothing written. Job:")
        for k in sorted(job):
            v = job[k]
            print("    %-16s %s" % (k, (str(v)[:150] + "...") if len(str(v)) > 150 else v))
        return
    job["createdAt"] = datetime.datetime.now(datetime.timezone.utc)
    ref = u.collection("backtests").document()
    _retry(lambda: ref.set(job))
    print("queued users/%s/backtests/%s  host=%s" % (UID, ref.id, job.get("host") or "(any)"))
    os.makedirs(LOGDIR, exist_ok=True)
    with open(os.path.join(LOGDIR, "validate_queued.txt"), "a") as fh:
        fh.write("%s ENGU-Q VS constant dollar risk, cost 0.783 db_adj_eth host=%s job %s\n" % (
            datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
            job.get("host") or "any", ref.id))


if __name__ == "__main__":
    main()

# QUEUED 2026-11-21: job CoqUIxwkGdG2jWnvsb5o, host=desktop, queue depth 0 at launch.
