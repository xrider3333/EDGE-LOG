"""AUTO-VALIDATE 900 - ENGU-Q HOLD CAP r2: the crown's full search with the cap knob opened.

Owner order 2026-10-14 via MANAGER #79: autovalidate the top candidates of the last few weeks.
This lane's cell is ENGU-Q #335 with the hold cap opened (off / 2h / 4h / 1 session / 1 week) on
top of its normal ranges. Pre-registration docs/PREREG_enguq_holdcap_r2_2026-10-14.md, written
and shipped before this script may run.

THE OBJECTION, ON RECORD AND OVERRULED: this lane advised against a cap sweep after hold cap r1
(MANAGER #946) because the cap's effect is monotone and already mapped, and because the one cell
that beat the crown on ROC failed on Sortino and on the one-episode test. The owner wants the top
candidates validated. What r1 could not do and this round can: r1 held every other knob at the
crown's values, so it only asked what a cap does to THAT cell. This asks whether a DIFFERENTLY
TUNED cell plus a cap beats the crown, and puts a lockbox under the answer.

THE BAR (prereg clauses, all six must hold): walk-forward ROC@30k beats the crown's 26.5 on the
same basis; Sortino at least matches 3.66 (the clause r1's best cell failed at 2.20); the worst
drawdown over DD5 ratio is no worse than the crown's 1.60; at least 100 WF and 50 LB trades with
the lockbox profitable without its biggest trade; the engine's verdict is not WEAK; and the
winning cell is the WALK-FORWARD CHAIN, never the full-window champion - run #489 produced a 39.6
champion read against a 10.1 chain, which is what that clause exists to prevent.

BASIS, a judgement call flagged in the prereg rather than buried: MANAGER #79 says pin to the
crown's run. Run #335's stored basis is db_noadj_eth at cost 0.533. This pins the WINDOW to that
(2010-06-07..2026-06-30) but the MASTER to db_adj_eth at 0.783, because that is the registered
roll-corrected tape and it is the basis the "4h cap 29.8 vs crown 26.5" figures were read on.
Pinning the older tape would produce a number that cannot be compared with the figure the owner
is asking about. One line to change if MANAGER wants the literal #335 basis.

Refuses to queue if any of the five named cap cells is off the declared lattice, if the strategy
file or the prereg is not on main, if the master is not the registered roll-corrected one, or if
a job on the same file and window is already live.
    python tools/enguq_queue_holdcap_r2.py --dry
    python tools/enguq_queue_holdcap_r2.py
"""
import argparse
import datetime
import importlib.util
import os
import sys
import time

REPO = r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"
os.chdir(REPO)
sys.path.insert(0, REPO)
UID = "IO0K35JpLIcH9YK4C0pMNYUzZOM2"
TAG = "AUTO-VALIDATE 900 ENGU-Q HOLD CAP r2 (cap knob open on the crown's full search)"
STRATEGY = "ENGUQ_1M_ETH_HC_1_0.py"
PREREG = "docs/PREREG_enguq_holdcap_r2_2026-10-14.md"

# the owner's five named cells, in 1-minute bars on the 23-hour overnight tape
NAMED = [("off", 0), ("2 hours", 120), ("4 hours", 240), ("1 session", 1380), ("1 week", 6900)]
# run #335's stored champion - every one of these must stay reachable too
RUN335 = {
    "buf_atr": 0.4, "tl_len": 238, "trail_frac": 4.0, "ema_len": 1340, "atr_len": 28,
    "act_R": 2.5, "breakeven_R": 1.0, "limit_atr": 0.1, "er_len": 100, "stop_mult": 1.2,
    "regime_len": 5, "min_brk": 1.4, "vol_mult": 0.0, "er_th": 0.0,
}

JOB = dict(
    type="validate", strategy=STRATEGY,
    instrument="NQ", timeframe="1m", session="eth", source="db_adj_eth",
    commission_usd=0.0, slippage_pts=0.0, cost_pts=0.783, mult=20,
    date_from="2010-06-07", date_to="2026-06-30",
    lockbox_months=12, wf_folds=8, warm_days=300,
    n_trials=900, min_trades=30, mc_sims=2000, n_rounds=0, select_oos_topk=10,
    discover="auto", provider="ollama",
    dsr=True, neighbors=True, regime=True, pills=True, context=True, equity_points=400,
)
LOGDIR = r"C:\EdgeLog\_anatomy_cache\enguq_holdcap_r2"

NOTE = (
    "%s. Owner order 2026-10-14 via MANAGER #79 (autovalidate the top candidates of the last few "
    "weeks). Pre-registration %s. File %s = crown #335's mechanism with the engine's existing "
    "hold cap exposed; cap OFF reproduces the crown trade for trade, 2,053 vs 2,053. Cap fence "
    "RE-CUT 2026-10-14 from 0..20000 step 5 to 0..6900 step 60 - one-hour resolution capped at "
    "one week, 116 lattice points, holding all five named cells exactly (off, 2h=120, 4h=240, "
    "1 session=1380, 1 week=6900) and 0=off still in the space; a re-cut, not a pinning, because "
    "4,001 points for one knob inside a 900-trial search over fourteen knobs spends trials the "
    "other knobs need. All of run #335's champion settings stay reachable on the parent's own "
    "fences. BASIS: window pinned to the crown's run 2010-06-07..2026-06-30, but master "
    "db_adj_eth at cost 0.783 rather than #335's original db_noadj_eth at 0.533 - the registered "
    "roll-corrected tape, and the basis the '4h cap 29.8 vs crown 26.5' figures were read on; "
    "flagged in the prereg, one line to change. 12-month lockbox, 8 folds, warm 300 days, 900 "
    "trials (OWNER RULE, never lowered). THE BAR: WF ROC@30k beats the crown's 26.5; Sortino at "
    "least 3.66 (the clause hold cap r1's best cell failed, at 2.20); worst DD over DD5 no worse "
    "than the crown's 1.60; at least 100 WF and 50 LB trades, lockbox profitable without its "
    "biggest trade; verdict not WEAK; and the WALK-FORWARD CHAIN decides, never the full-window "
    "champion. PRE-REGISTERED PRIOR: this lane expects a cap near 4 hours to win on ROC and to "
    "FAIL on Sortino, because the family's money is in multi-day survivors (490 trades held 24h+ "
    "made $1.03M while 1,563 shorter ones lost $539k) and a cap converts survivors into "
    "non-survivors. The lane advised against this sweep and was overruled; that objection is on "
    "record and the round runs in full. Nothing live or paper changes; crown #335 frozen and "
    "still the incumbent. Driver tools/enguq_queue_holdcap_r2.py."
    % (TAG, PREREG, STRATEGY)
)


def on_lattice(value, lo, hi, step):
    """Reachable as lo + step*k within [lo, hi], compared with a tolerance."""
    if step in (None, 0):
        return lo <= value <= hi
    if not (lo - 1e-9 <= value <= hi + 1e-9):
        return False
    k = round((value - lo) / step)
    return k >= 0 and abs(lo + step * k - value) <= max(1e-9, abs(step) * 1e-6)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args()

    spath = os.path.join(REPO, "augur_strategies", STRATEGY)
    for need in (spath, os.path.join(REPO, PREREG)):
        if not os.path.exists(need):
            sys.exit("ABORT - not in the shared checkout, so the runner would not see it: "
                     + need)

    spec = importlib.util.spec_from_file_location("hc", spath)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    DP = mod.DEFAULT_PARAMS

    # GATE 1 - the five named cap cells must be reachable. This lane has shipped an unreachable
    # cell twice and nearly a third time; the check sits here because here is what runs.
    cap = DP["max_hold_bars"]
    print("cap fence: %s..%s step %s (%d points)"
          % (cap["min"], cap["max"], cap["step"],
             int((cap["max"] - cap["min"]) / cap["step"]) + 1))
    bad = [("%s=%d" % (lab, b)) for lab, b in NAMED
           if not on_lattice(b, cap["min"], cap["max"], cap["step"])]
    for lab, b in NAMED:
        print("   %-10s %5d  %s" % (lab, b, "reachable"
                                    if not any(lab in x for x in bad) else "UNREACHABLE"))
    if bad:
        sys.exit("ABORT - the search could never evaluate: " + ", ".join(bad))

    # GATE 2 - run #335's own champion must stay reachable, or the comparison is against a cell
    # the search cannot express (the defect that nearly voided ENGU-Q RTH r1).
    off = []
    for k, v in RUN335.items():
        s = DP.get(k)
        if s is None:
            off.append("%s missing from the file" % k)
        elif s.get("type") in ("int", "float") and not on_lattice(
                v, s["min"], s["max"], s.get("step")):
            off.append("%s=%s not on %s..%s step %s" % (k, v, s["min"], s["max"], s.get("step")))
    if off:
        sys.exit("ABORT - run #335's champion is unreachable: " + "; ".join(off))
    print("run #335's champion: all %d settings reachable" % len(RUN335))

    # GATE 3 - the master must be the registered roll-corrected one
    from augur_engine import data as D
    m = D.find_master("NQ", "1m", "eth", JOB["source"])
    if not m:
        sys.exit("ABORT - no %s master registered" % JOB["source"])
    print("master OK: %s rows=%s %s..%s"
          % (m.get("filename"), m.get("rows"), m.get("date_from"), m.get("date_to")))

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
                print("attempt %d blocked (%s); waiting %ds" % (i + 1, type(e).__name__, wait),
                      flush=True)
                if i == tries - 1:
                    raise
                time.sleep(wait)

    live = _retry(lambda: [(d.id, d.to_dict() or {}) for st in ("queued", "running", "paused")
                           for d in u.collection("backtests")
                           .where(filter=_FF("status", "==", st)).stream()])
    print("queue depth", len(live))
    for did, x in live:
        print("  live %s %-8s %-26s %-5s %s..%s"
              % (did, x.get("status"), str(x.get("strategy"))[:26], x.get("instrument"),
                 x.get("date_from"), x.get("date_to")))
    clash = []
    for did, x in live:
        if TAG in str(x.get("note") or "") or TAG in str(x.get("preset") or ""):
            clash.append("%s already carries this label (%s)" % (did, x.get("status")))
        if (x.get("strategy") == STRATEGY
                and str(x.get("date_from")) == JOB["date_from"]
                and str(x.get("date_to")) == JOB["date_to"]):
            clash.append("%s: same file and window already %s" % (did, x.get("status")))
    if clash:
        sys.exit("ABORT - would double-queue:\n  " + "\n  ".join(sorted(set(clash))))
    if len(live) > 9:
        sys.exit("ABORT - queue too deep (%d)" % len(live))

    job = dict(JOB, status="queued", progress=0,
               preset="%s: cap off / 2h / 4h / 1 session / 1 week" % TAG, note=NOTE)
    if a.dry:
        for k in sorted(job):
            print("    %-16s %s" % (k, job[k]))
        return
    job["createdAt"] = datetime.datetime.now(datetime.timezone.utc)
    ref = u.collection("backtests").document()
    _retry(lambda: ref.set(job))
    print("queued users/%s/backtests/%s" % (UID, ref.id))
    os.makedirs(LOGDIR, exist_ok=True)
    with open(os.path.join(LOGDIR, "holdcap_r2_queued.txt"), "a") as fh:
        fh.write("%s ENGU-Q HOLD CAP r2 %s\n"
                 % (datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
                    ref.id))


if __name__ == "__main__":
    main()
