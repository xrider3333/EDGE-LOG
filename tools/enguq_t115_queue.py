"""TEST 115 -- ENGU-Q on the BOARD-57 FOUR-YEAR LOCKBOX, 900 trials, desktop.

WHY. Run #556's lockbox was ONE year and it is already spent (2025-06-30..2026-06-30, -$14,674), so
a 12-month read on that span can no longer be blind. The owner GO'd (inbox #195) a deeper re-
validate on the board-57 four-year lockbox 2022-06-30..2026-06-30, which the owner had GO'd earlier
as a general rule, with the walk-forward before it, the same tape and cost, and the 900-trial budget
that is never lowered.

WHICH STRATEGY -- TWO ARMS, ONE FLAG, AND THE DEFAULT IS THE OWNER'S WORD.
  default (no flag)  ENGUQ_1M_ETH_VS_1_0.py, run #556's own file. This is what the owner named, so
                     it is the default and it runs unless MANAGER relays a swap.
  --crown            ENGUQ_1M_ETH_R2_1_0.py, the live crown's file.
ENGUQ's recommendation on record (board 180 fix 3) was the swap, because the VS line is now CLOSED
on three independent grounds -- its shuffle null (94.0th percentile, null median raw net $552,309 vs
the arm's $207,339), its lockbox (-$14,674 in a year the BASELINE made +$82,343 on the same tape),
and its drawdown (lockbox DD $44,886 against the $39,260 worst drawdown of its ENTIRE 8.7-year
walk-forward) -- so a sharper answer about it buys little. MANAGER is asking the owner. Until a swap
is relayed, the default arm is the one that runs: a lane does not quietly re-point a run the owner
asked for by name.

THE 2025-26 YEAR IS NOT BLIND AND THE RUN NOTE SAYS SO. Whatever arm runs, the last of the four
lockbox years has already been read, so the grade must judge the 2022-06..2025-06 part SEPARATELY
as the genuinely unseen stretch, and treat the four-year total as partly seen. That is in the note
so no later reader can mistake it for a clean four-year blind read.

COST IS PINNED AT 0.783 FOR THE VS ARM AND A RE-COST IS INVALID. The engine charges cost once per
trade with no notion of size (augur_engine.engine._apply_costs), so the VS file emits
`size * gross - (size - 1) * vs_cost_pts` and the engine's single subtraction completes it to
`size * (gross - cost)` ONLY at cost_pts 0.783. At any other cost each trade is mis-charged by
exactly (size - 1) * (job_cost - 0.783), and a job CHEAPER than 0.783 UNDER-charges, which FLATTERS
the run -- so any re-costed stress cell on the VS arm must be marked INVALID rather than read. The
script ABORTS if the two numbers ever disagree. The crown arm has no such identity and is pinned at
0.783 simply because that is the registered line for ENGU-Q on the adjusted master.

EXPECT THE VS ARM TO BE SLOW, AND WATCH ITS MEMORY. #556 took 39,415 s (11 h) for stage_a alone and
grew about 0.45 GB/h until MANAGER stopped it. The cause looks structural rather than a bug: the VS
file must call the parent with `return_levels=True` to read each trade's initial stop distance, and
that forces the parent's INTERPRETED walk, because the compiled loop does not expose the stop path.
The crown arm runs on the compiled loop and does not carry that cost.

    python tools/enguq_t115_queue.py --dry                  # offline: every gate but the queue read
    python tools/enguq_t115_queue.py --on-desktop           # the owner's arm, run #556's file
    python tools/enguq_t115_queue.py --on-desktop --crown   # only if MANAGER relays the swap
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
TAG = "TEST 115 ENGU-Q 4-YEAR LOCKBOX 900 (owner GO 11-23, board-57 lockbox)"
VS, CROWN = "ENGUQ_1M_ETH_VS_1_0.py", "ENGUQ_1M_ETH_R2_1_0.py"
MASTER_ID, MASTER_FILE = 66, "ADJ_NQ_1m_ETH.csv"
COST = 0.783
LB_FROM, LB_TO = "2022-06-30", "2026-06-30"
LOGDIR = r"C:\EdgeLog\_anatomy_cache\bookq\t180"


def build(strategy):
    return dict(
        type="validate", strategy=strategy,
        instrument="NQ", timeframe="1m", session="eth", source="db_adj_eth",
        commission_usd=0.0, slippage_pts=0.0, cost_pts=COST, mult=20,
        date_from="2010-06-07", date_to="2026-06-30",
        lockbox_months=48, wf_folds=8, warm_days=300,
        n_trials=900, min_trades=30, mc_sims=2000, n_rounds=0, select_oos_topk=10,
        discover="auto", provider="ollama",
        dsr=True, neighbors=True, regime=True, pills=True, context=True, equity_points=400,
    )


def note(strategy, crown):
    arm = ("the LIVE CROWN's file (MANAGER relayed the owner's swap)" if crown
           else "run #556's own file, the arm the owner named")
    n = (TAG + ". Deeper re-validate on the board-57 FOUR-YEAR lockbox %s..%s, walk-forward before "
         "it, 8 folds, warm 300, 900 trials (owner budget, never lowered), NQ 1m ETH on "
         "ADJ_NQ_1m_ETH id 66 db_adj_eth, cost 0.783, mult 20. Arm: %s (%s). THE LAST LOCKBOX YEAR "
         "IS NOT BLIND: 2025-06-30..2026-06-30 was already read as run #556 (-$14,674 over 220 "
         "trades, PF 0.90, Sortino -1.18), so judge the 2022-06..2025-06 part SEPARATELY as the "
         "genuinely unseen stretch and treat the four-year total as partly seen. "
         % (LB_FROM, LB_TO, strategy, arm))
    if not crown:
        n += ("WHY THE LANE RECOMMENDED AGAINST THIS ARM, stated before the grade: the inverse-stop "
              "sizing line is CLOSED on three independent grounds -- its own shuffle null put it at "
              "the 94.0th percentile with the null's MEDIAN raw net $552,309 against the arm's "
              "$207,339 (drawdown shape, not aim); its lockbox lost $14,674 in the very year the "
              "BASELINE #335 paper cell MADE +$82,343 on the same tape, the second-best of sixteen "
              "years with zero negative years, so the loss is the sizing and not the regime; and its "
              "lockbox drawdown $44,886, 45.7 pct of peak, EXCEEDS the $39,260 worst drawdown of its "
              "entire 8.7-year walk-forward, i.e. one unseen year out-drew nine years of WF. Round 7 "
              "(2026-08-18) had already declared the ENGU-Q sizing family closed forever at the "
              "FOURTH failure; #556 is the fifth. The run proceeds because the owner asked for it by "
              "name. COST IS PINNED AT 0.783 AND A RE-COST IS INVALID on this file: the engine "
              "charges cost once per trade with no notion of size, so the file emits "
              "size*gross-(size-1)*0.783 and the engine's single subtraction completes it to "
              "size*(gross-0.783) only at 0.783; at any other cost each trade is mis-charged by "
              "(size-1)*(job_cost-0.783) and a CHEAPER job cost UNDER-charges and FLATTERS the run, "
              "so mark any 2x-cost or 0.283 cell INVALID rather than reading it. EXPECT IT TO BE "
              "SLOW AND WATCH MEMORY: #556's stage_a took 39,415 s and grew ~0.45 GB/h, because the "
              "file must pass return_levels=True to read each trade's stop distance and that forces "
              "the parent's INTERPRETED walk (the compiled loop does not expose the stop path). ")
    else:
        n += ("This arm answers a question the house does NOT have an answer to -- whether the live "
              "crown holds up over a four-year held-out stretch -- and it runs on the compiled loop, "
              "so it does not carry the VS file's interpreted-walk cost. ")
    return n + ("Lockbox veto only. Nothing live or paper changes. Desktop workers. Driver "
                "tools/enguq_t115_queue.py.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true",
                    help="run every offline gate and print the job; makes no Firestore call at all")
    ap.add_argument("--crown", action="store_true",
                    help="swap to the live crown's file -- ONLY when MANAGER relays the owner's swap")
    add_host_args(ap)
    a = ap.parse_args()

    strategy = CROWN if a.crown else VS
    job = build(strategy)
    print("TEST 115 arm: %s%s" % (strategy, "  (SWAP relayed)" if a.crown else "  (the owner's named arm)"))

    spath = os.path.join(REPO, "augur_strategies", strategy)
    if not os.path.exists(spath):
        sys.exit("ABORT - not in the shared checkout, the runner would not see it: " + spath)
    if "_PINNED" in strategy:
        sys.exit("ABORT - Auto-Validate never runs on a pinned file")

    import importlib.util
    spec = importlib.util.spec_from_file_location("s", spath)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    dp = mod.DEFAULT_PARAMS
    numeric = [k for k, s in dp.items() if s.get("type") in ("int", "float")]
    open_knobs = [k for k in numeric if float(dp[k]["min"]) < float(dp[k]["max"])]
    if not open_knobs:
        sys.exit("ABORT - every numeric knob has min == max; this is a pinned file in disguise")
    print("file OK: %d numeric knobs, %d with a real range" % (len(numeric), len(open_knobs)))

    if not a.crown:
        for k in ("vs_target_pts", "vs_min_u", "vs_max_u", "vs_cost_pts"):
            if float(dp[k]["min"]) != float(dp[k]["max"]):
                sys.exit("ABORT - sizing knob %s has a range; the sizing must stay fixed ex ante" % k)
        if abs(float(dp["vs_cost_pts"]["default"]) - COST) > 1e-12:
            sys.exit("ABORT - cost identity broken: file vs_cost_pts %s, job cost_pts %s. Every "
                     "trade would be mis-charged by (size-1)*(job-vs) and a cheaper job cost "
                     "FLATTERS the run." % (dp["vs_cost_pts"]["default"], COST))
        print("sizing fixed OK and cost identity holds at %.3f" % COST)

    from augur_engine import data as D
    m = D.find_master(job["instrument"], job["timeframe"], job["session"], job["source"])
    if not m or m.get("filename") != MASTER_FILE or int(m.get("id") or 0) != MASTER_ID:
        sys.exit("ABORT - the roll-corrected NQ 1m ETH master is not id %s %s: %r"
                 % (MASTER_ID, MASTER_FILE, m))
    if str(m.get("date_to"))[:10] < job["date_to"]:
        sys.exit("ABORT - master ends %s, before the window end %s" % (m.get("date_to"), job["date_to"]))
    print("master OK: id %s %s rows=%s %s..%s" % (m.get("id"), m.get("filename"), m.get("rows"),
                                                  m.get("date_from"), m.get("date_to")))

    job = apply_host(dict(job, status="queued", progress=0,
                          preset="%s: %s, 4-yr lockbox %s..%s, 2025-26 already seen"
                                 % (TAG, strategy, LB_FROM, LB_TO),
                          note=note(strategy, a.crown)), a)
    if a.dry:
        print("\nDRY RUN - no Firestore call was made at all. Job:")
        for k in sorted(job):
            v = job[k]
            print("    %-16s %s" % (k, (str(v)[:150] + "...") if len(str(v)) > 150 else v))
        return

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
    clash = []
    for did, x in live:
        if TAG in str(x.get("note") or "") or TAG in str(x.get("preset") or ""):
            clash.append("%s already carries the test-115 label (%s)" % (did, x.get("status")))
        if (x.get("strategy") == strategy and str(x.get("instrument")) == job["instrument"]
                and int(x.get("lockbox_months") or 0) == 48):
            clash.append("%s: same file and a 48-month lockbox already %s" % (did, x.get("status")))
    if clash:
        sys.exit("ABORT - would double-queue:\n  " + "\n  ".join(sorted(set(clash))))
    if len(live) > 9:
        sys.exit("ABORT - queue too deep (%d)" % len(live))

    job["createdAt"] = datetime.datetime.now(datetime.timezone.utc)
    ref = u.collection("backtests").document()
    _retry(lambda: ref.set(job))
    print("queued users/%s/backtests/%s  host=%s" % (UID, ref.id, job.get("host") or "(any)"))
    os.makedirs(LOGDIR, exist_ok=True)
    with open(os.path.join(LOGDIR, "t115_queued.txt"), "a") as fh:
        fh.write("%s TEST 115 %s 4-yr lockbox %s..%s host=%s job %s\n" % (
            datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
            strategy, LB_FROM, LB_TO, job.get("host") or "any", ref.id))


if __name__ == "__main__":
    main()
