"""AUTO-VALIDATE 900 -- ENGU-Q #335 TRANSFERRED TO RTY 1m ETH (MANAGER ruling 2026-11-20).

WHY THIS RUN EXISTS, AND IT IS A RULE AND NOT A RECOMMENDATION. The owner's standing order is that a
loose-screen pass goes to a validate and that luck statistics are warnings, never kills. The frozen
RTY read PASSED that screen on every clause. My own recommendation was to close it without a
validate, because of the warnings written out below; MANAGER's ruling (2026-11-20) is that the
screen is the gate and the validate decides, not the lane. So it is queued, behind YM, with the
warnings recorded HERE, before it runs, and with a pre-set verdict that cannot be loosened after a
grade arrives. If it fails, that is the expected outcome and not a surprise to be argued with.

THE FROZEN-PARAM READ, no re-tune: the same ranged file and the same api.paper.ENGUQ_335 params the
NQ crown runs, pointed at ADJ_RTY_1m_ETH id 153 (outputs in
C:/EdgeLog/_anatomy_cache/bookq/rty_transfer/):
  138.4 trades a year, 5 of 8 folds won, gross per trade 0.7433 points against the 0.213 cost line
  net $34,338 at cost and still $20,546 at the 0.426 double-cost arm
  four numbers: ROC@30k 13.5 percent a year, DD5 $13,728, worst DD $18,823 (18.8 percent of a
    fixed $100k, 7.5 percent of $250k), Sortino 0.42
  $/yr $4,046 for one unit over 7.99 years

THE WINDOW IS SHORTER THAN THE OWNER WINDOW AND THAT IS NOT A CHOICE. The RTY master starts
2017-07-09, so this job's window starts there instead of 2016-07-01. Every figure above is on
2017-07-09..2025-06-30, and the run must not be compared to an NQ or YM figure as though the spans
matched: the missing first year reads as flat days on a union of dates, which is the same trap that
makes ENGU-Q #407 look better than it is. The job's date_from is set to the master's own start so
the queue script's master guard passes honestly rather than by widening the window.

THE WARNINGS, written BEFORE the grade so they cannot be discovered after a good one. Warnings and
never kills, per the owner's 11-14 rule -- but all three say the same thing, which is why my own
read was a fail:
  ONE FOLD IS THE WHOLE LEG. Window net $32,320. Fold 4 (2020-07..2021-07) alone is $29,321 = 91
    percent of it. The three losing folds sum to -$17,975.
  CONCENTRATION WORSE THAN THE ES LEG THAT CLOSED THE FAMILY'S LAST TRANSFER. The ten best trades
    are 245 percent of the window net and the ten best DAYS are 218 percent. ENGU-Q on ES was
    closed at 108 percent. Win rate is 287 of 1,132, 25 percent.
  IT IS DEAD AFTER 2020, which is the opposite of what the book now needs. Early half
    (2017-07..2020-12, 3.57 years) $7,971 a year; late half (2021-01..2025-06, 4.42 years) $872 a
    year; fold 8 is -$12,288. All five of its worst drawdown episodes fall in 2021-25 and the
    largest ($18,823, peaked 2024-12-02) is still OPEN at the walk-forward end, the same shape as
    the June-2025 open-drawdown trap. The house dd5 helper flags one_episode.
  NOT A TROUGH LEG EITHER. It loses in both windows that now bind the book: 2024 spring -$1,646
    over 6 non-zero days of 19, 2022 autumn -$68 over 4 of 11.
  BOOK ADD IS A DECLINE ON ROUTE A AND ROUTE C. +$3,592 a year for +$5,097 of drawdown = $0.70 of
    annual profit per $1 of drawdown, against the book's own $2.68. DD excluding 2020 moves $0.

PRE-SET VERDICT, MANAGER's wording, fixed before the run reads:
  ADOPT-CANDIDATE only on a PASS, or a WEAK whose folds hold 7 of 8 or better, AND a ten-best share
  BELOW 100 percent of the walk-forward total, AND a late half (2021-2025) whose net is above zero.
  Anything else and RTY closes, with this frozen read kept on file as the reason.
The lockbox is veto only and is not read in this lane's report.

WHICH MACHINE RUNS IT. MANAGER asked for "Razer only, RTY is not on the desktop yet". The host pin
cannot express that: a pin names an EDGELOG_HOST_TAG, the desktop's tag is "desktop", and the Razer
runs UNTAGGED -- host_pin_verdict() refuses a pinned job on an untagged runner, so pinning this to
"razer" would strand it for the 6-hour fallback and then be claimed by whatever is alive anyway. So
the job carries NO host field, exactly like the YM arm. If the desktop ever picks it up it will fail
on the master guard (it has no RTY master) rather than run on the wrong data, and MANAGER can pin it
deliberately with tools/job_host.py once the desktop has the master.

CHANGES FROM THE NQ CROWN'S VALIDATE, AND NOTHING ELSE: instrument NQ to RTY, master db_adj_eth
ADJ_RTY_1m_ETH id 153, cost 0.213, mult 50, window start at the master's own first bar. Same ranged
file ENGUQ_1M_ETH_R2_1_0.py (never a pinned copy), same 8 folds, same 12-month lockbox, same 900
trials -- the owner budget, never lowered.

    python tools/enguq_rty335_transfer_queue.py --dry
    python tools/enguq_rty335_transfer_queue.py
"""
import argparse
import datetime
import os
import sys
import time

REPO = r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"
os.chdir(REPO)
sys.path.insert(0, REPO)
UID = "IO0K35JpLIcH9YK4C0pMNYUzZOM2"
TAG = "AUTO-VALIDATE 900 ENGU-Q #335 TRANSFER to RTY 1m ETH (MANAGER ruling 11-20)"
STRATEGY = "ENGUQ_1M_ETH_R2_1_0.py"
MASTER_ID, MASTER_FILE = 153, "ADJ_RTY_1m_ETH.csv"
LOGDIR = r"C:\EdgeLog\_anatomy_cache\bookq\rty_transfer"

JOB = dict(
    type="validate", strategy=STRATEGY,
    instrument="RTY", timeframe="1m", session="eth", source="db_adj_eth",
    commission_usd=0.0, slippage_pts=0.0, cost_pts=0.213, mult=50,
    date_from="2017-07-09", date_to="2026-06-30",
    lockbox_months=12, wf_folds=8, warm_days=300,
    n_trials=900, min_trades=30, mc_sims=2000, n_rounds=0, select_oos_topk=10,
    discover="auto", provider="ollama",
    dsr=True, neighbors=True, regime=True, pills=True, context=True, equity_points=400,
)

NOTE = (
    TAG + ". QUEUED ON MANAGER'S RULING, NOT ON THIS LANE'S RECOMMENDATION: the frozen read passed "
    "the owner loose screen on every clause (138.4 trades a year, profitable, 5 of 8 folds won), and "
    "the standing order says a loose-screen pass goes to a validate with luck stats as warnings not "
    "kills, so the validate decides. This lane's own read was a FAIL. Frozen-param transfer, no "
    "re-tune: api.paper.ENGUQ_335 on ADJ_RTY_1m_ETH id 153, gross per trade 0.7433 points against the "
    "0.213 cost line, net $34,338 at cost and $20,546 at the 0.426 double-cost arm. Four numbers: "
    "ROC@30k 13.5, DD5 $13,728, worst DD $18,823 = 18.8 pct of a fixed $100k and 7.5 pct of $250k, "
    "Sortino 0.42. $/yr $4,046 for one unit. WINDOW IS SHORTER AND NOT BY CHOICE: the RTY master "
    "starts 2017-07-09, so this is 2017-07-09..2025-06-30, about 8 years not 9, and it must not be "
    "compared to an NQ or YM figure as if the spans matched - the missing first year reads as flat "
    "days on a union of dates, the same trap that flatters ENGU-Q #407. COST DERIVED: RTY tick 0.10 "
    "point on a $50 multiplier plus $4 of fees (0.08) = 0.213 points a round trip per TBIS, far "
    "lighter in points than YM's 1.80. WARNINGS STATED BEFORE THE GRADE, warnings not kills per the "
    "owner 11-14 rule, and all three say the same thing: ONE FOLD IS THE LEG - window net $32,320, "
    "fold 4 alone $29,321 = 91 pct, the three losing folds sum to -$17,975; CONCENTRATION WORSE THAN "
    "THE ES LEG THAT CLOSED - ten best trades 245 pct of the window net and ten best days 218 pct, "
    "against the 108 pct that closed ENGU-Q on ES, win rate 25 pct; DEAD AFTER 2020 - early half "
    "(2017-07..2020-12) $7,971/yr, late half (2021-01..2025-06) $872/yr, fold 8 -$12,288, all five "
    "worst drawdown episodes in 2021-25 and the largest ($18,823, peaked 2024-12-02) still OPEN at "
    "the walk-forward end, dd5 flags one_episode. NOT A TROUGH LEG: loses in both windows that now "
    "bind the book (2024 spring -$1,646 over 6 non-zero days of 19; 2022 autumn -$68 over 4 of 11). "
    "BOOK ADD IS A DECLINE: +$3,592/yr for +$5,097 of drawdown = $0.70 per $1 against the book's own "
    "$2.68, DD ex-2020 +$0. PRE-SET VERDICT: adopt-candidate ONLY on a PASS, or a WEAK with folds 7 "
    "of 8 or better, AND a ten-best share below 100 pct of the WF total, AND a late half (2021-2025) "
    "net above zero. Anything else and RTY closes with this frozen read on file as the reason. NO "
    "HOST PIN: MANAGER asked for Razer-only, but a pin names an EDGELOG_HOST_TAG and the Razer runs "
    "untagged, so a pin would strand the job for the 6 h fallback; a desktop pickup fails the master "
    "guard rather than running wrong data. CHANGES FROM THE NQ CROWN VALIDATE AND NOTHING ELSE: "
    "instrument NQ to RTY, master ADJ_RTY_1m_ETH id 153, cost 0.213, mult 50, window start at the "
    "master's first bar; same ranged file, 8 folds, 12-month lockbox, 900 trials. Lockbox veto only. "
    "Nothing live or paper changes. Driver tools/enguq_rty335_transfer_queue.py."
)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args()

    spath = os.path.join(REPO, "augur_strategies", STRATEGY)
    if not os.path.exists(spath):
        sys.exit("ABORT - not in the shared checkout, the runner would not see it: " + spath)
    if "_PINNED" in STRATEGY:
        sys.exit("ABORT - Auto-Validate never runs on a pinned file")

    # the file must still have a real search space (owner rule: no 1-config validates)
    import importlib.util
    spec = importlib.util.spec_from_file_location("eq", spath)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    dp = mod.DEFAULT_PARAMS
    numeric = [k for k, s in dp.items() if s.get("type") in ("int", "float")]
    open_knobs = [k for k in numeric if float(dp[k]["min"]) < float(dp[k]["max"])]
    if not open_knobs:
        sys.exit("ABORT - every numeric knob has min == max; this is a pinned file in disguise")
    print("file OK: %s, %d numeric knobs, %d with a real range"
          % (STRATEGY, len(numeric), len(open_knobs)))

    from augur_engine import data as D
    m = D.find_master(JOB["instrument"], JOB["timeframe"], JOB["session"], JOB["source"])
    if not m or m.get("filename") != MASTER_FILE or int(m.get("id") or 0) != MASTER_ID:
        sys.exit("ABORT - the roll-corrected RTY 1m ETH master is not id %s %s: %r"
                 % (MASTER_ID, MASTER_FILE, m))
    if str(m.get("date_to"))[:10] < JOB["date_to"]:
        sys.exit("ABORT - master ends %s, before the window end %s"
                 % (m.get("date_to"), JOB["date_to"]))
    if str(m.get("date_from"))[:10] > JOB["date_from"]:
        sys.exit("ABORT - master starts %s, after the window start %s"
                 % (m.get("date_from"), JOB["date_from"]))
    print("master OK: id %s %s rows=%s %s..%s" % (m.get("id"), m.get("filename"), m.get("rows"),
                                                  m.get("date_from"), m.get("date_to")))

    import firebase_admin
    from firebase_admin import credentials, firestore
    from google.api_core import exceptions as _gx
    from google.cloud.firestore_v1.base_query import FieldFilter as _FF
    if not firebase_admin._apps:
        firebase_admin.initialize_app(
            credentials.Certificate(os.path.join(REPO, "serviceAccount.json")))
    u = firestore.client().collection("users").document(UID)

    def _retry(fn, tries=4, wait=90):
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
        print("  live %s %-8s %-28s %-4s %s..%s" % (did, x.get("status"),
                                                    str(x.get("strategy"))[:28],
                                                    x.get("instrument"), x.get("date_from"),
                                                    x.get("date_to")))
    clash = []
    for did, x in live:
        if TAG in str(x.get("note") or "") or TAG in str(x.get("preset") or ""):
            clash.append("%s already carries this label (%s)" % (did, x.get("status")))
        if (x.get("strategy") == STRATEGY and str(x.get("instrument")) == JOB["instrument"]
                and str(x.get("date_from")) == JOB["date_from"]
                and str(x.get("date_to")) == JOB["date_to"]):
            clash.append("%s: same file, instrument and window already %s" % (did, x.get("status")))
    if clash:
        sys.exit("ABORT - would double-queue:\n  " + "\n  ".join(sorted(set(clash))))
    if len(live) > 9:
        sys.exit("ABORT - queue too deep (%d)" % len(live))

    # MANAGER: behind YM. The runner takes queued jobs oldest createdAt first, so a job created
    # while the YM validate is still live is necessarily claimed after it.
    ym = [did for did, x in live if str(x.get("instrument")) == "YM"
          and x.get("strategy") == STRATEGY]
    print("YM arm live: %s" % (", ".join(ym) or "none (it has already finished)"))

    job = dict(JOB, status="queued", progress=0,
               preset=("%s: ranged R2 file, frozen read passed the loose screen on 138 trades a "
                       "year, queued on MANAGER's ruling over this lane's fail read, cost 0.213"
                       % TAG),
               note=NOTE)
    if a.dry:
        print("\nDRY RUN - nothing written. Job:")
        for k in sorted(job):
            v = job[k]
            print("    %-16s %s" % (k, (str(v)[:150] + "...") if len(str(v)) > 150 else v))
        return
    job["createdAt"] = datetime.datetime.now(datetime.timezone.utc)
    ref = u.collection("backtests").document()
    _retry(lambda: ref.set(job))
    print("queued users/%s/backtests/%s" % (UID, ref.id))
    os.makedirs(LOGDIR, exist_ok=True)
    with open(os.path.join(LOGDIR, "validate_queued.txt"), "a") as fh:
        fh.write("%s ENGU-Q #335 transfer to RTY 0.213 db_adj_eth job %s\n" % (
            datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"), ref.id))


if __name__ == "__main__":
    main()
