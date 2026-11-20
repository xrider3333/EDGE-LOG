"""AUTO-VALIDATE 900 -- ENGU-Q #335 TRANSFERRED TO YM 1m ETH (owner standing order 11-20).

WHY THIS RUN EXISTS. The owner's 11-20 order is "raise the book": find adds in this family that lift
$/yr while max drawdown stays inside 20-35 percent of the account. ENGU-Q has one crown, on NQ (#335),
and two siblings that are shut: ES is CLOSED-NO (RUN 532, WEAK at 0.60 on the roll-corrected tape, PBO
0.881, ten best = 108 percent of the WF total) and RTY is PARKED on MANAGER's value call. YM had never
been tested, and TBIS registered ADJ_YM_1m_ETH (id 155) on 11-18 with every roll offset exact, so the
roll guard passes on the adjusted master.

THE FROZEN-PARAM READ CAME FIRST, and it is why this validate is queued at all. The same ranged file and
the same api.paper.ENGUQ_335 params, pointed at YM with NO re-tune, on the owner-rule window
2016-07-01..2025-06-30 (outputs in C:/EdgeLog/_anatomy_cache/bookq/ym_transfer/):
  129 trades a year, folds 8 of 8 won, net positive at 1.80 AND at the 2.40 double-cost arm
  four numbers from the house helper augur_engine.drawdowns.four_numbers: ROC@30k 16.86,
    DD5 $13,766, DD 9.62 percent from peak, Sortino 1.87
  $/yr $12,150 for one unit, worst DD $21,621 = 21.6 percent of a fixed $100k, 8.6 percent of $250k
  book add on the UNION of dates, one row per calendar day: book #463 $140,142/yr DD $52,238 becomes
    book + 1x YM $152,252/yr DD $56,263; ex-2020, $139,453 DD $38,394 becomes $152,407 DD $38,770 --
    $376 of ex-2020 drawdown buys $12,954 a year
  correlation with the NQ #335 leg -0.002 daily and -0.029 monthly; with the book -0.022 / -0.028
That passes the owner's loose screen (20+ trades a year, net > 0 after normal cost, WF > 0) on every
clause, so clause 3 of the standing order sends it straight to a 900-trial Auto-Validate.

COST, DERIVED NOT GUESSED. TBIS's RTY line is "0.213 pts RT (1 tick + fees), mult 50". YM's tick is
1.00 point on a $5 multiplier, so the same $4 of fees is 0.80 points and 1 tick + fees = 1.80 points a
round trip. In POINTS that is nine times RTY's cost line, which is the main risk in this transfer; the
frozen read clears it by 6.3x on gross per trade and still nets positive at the 2.40 arm.

THE WARNINGS, written here BEFORE the run so they cannot be discovered after a good grade. Per the
owner's 11-14 rule these are warnings and never kills, but they are why this is a candidate and not an
adoption:
  CONCENTRATION: the ten best trades are 96 percent of the frozen window's net. That is the same shape
    that closed ENGU-Q on ES (108 percent), and it is the first thing to read on this grade.
  ONE EPISODE: the house dd5 helper flags one_episode -- worst DD $21,621 is 1.57x the $13,766 DD5.
  WIN RATE 327 of 1166, 28 percent. Normal for this family, where the money is in the survivors, but it
    means a thin tail carries the leg.
  NOT THE TROUGH FIX: YM loses $2,914 in Apr-Jun 2025 and its own worst drawdown troughs 2025-04-24,
    inside the window where every capped mix already troughs. It diversifies across the whole window
    (correlation about zero) but it does NOT pay in the months that bind the book.

PRE-SET VERDICT, written before the run reads so the grade cannot be argued into a pass:
  ADOPT-CANDIDATE only on a PASS, or a WEAK whose folds hold 7 of 8 or better, AND whose ten-best share
  of the WF total is BELOW 100 percent. A grade carried by its ten best is not an adoption, whatever the
  headline says -- that is the ES lesson, and ES is closed for exactly this reason.
  Anything else and YM joins ES as closed, with the frozen read kept on file as the reason.
The lockbox is veto only and is not read in this lane's report.

CHANGES FROM THE NQ CROWN'S OWN VALIDATE, AND NOTHING ELSE: instrument NQ to YM, master db_adj_eth
ADJ_YM_1m_ETH id 155, cost 1.80, mult 5. Same ranged file ENGUQ_1M_ETH_R2_1_0.py (never a pinned copy),
same 8 folds, same 12-month lockbox, same 900 trials -- the owner budget, never lowered.

    python tools/enguq_ym335_transfer_queue.py --dry
    python tools/enguq_ym335_transfer_queue.py
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
TAG = "AUTO-VALIDATE 900 ENGU-Q #335 TRANSFER to YM 1m ETH (owner standing order 11-20)"
STRATEGY = "ENGUQ_1M_ETH_R2_1_0.py"
MASTER_ID, MASTER_FILE = 155, "ADJ_YM_1m_ETH.csv"
LOGDIR = r"C:\EdgeLog\_anatomy_cache\bookq\ym_transfer"

JOB = dict(
    type="validate", strategy=STRATEGY,
    instrument="YM", timeframe="1m", session="eth", source="db_adj_eth",
    commission_usd=0.0, slippage_pts=0.0, cost_pts=1.80, mult=5,
    date_from="2010-06-07", date_to="2026-06-30",
    lockbox_months=12, wf_folds=8, warm_days=300,
    n_trials=900, min_trades=30, mc_sims=2000, n_rounds=0, select_oos_topk=10,
    discover="auto", provider="ollama",
    dsr=True, neighbors=True, regime=True, pills=True, context=True, equity_points=400,
)

NOTE = (
    TAG + ". Frozen-param transfer read FIRST, no re-tune: api.paper.ENGUQ_335 on ADJ_YM_1m_ETH id 155, "
    "window 2016-07-01..2025-06-30, 129 trades a year, folds 8 of 8, net positive at 1.80 and at the 2.40 "
    "double-cost arm. House four numbers: ROC@30k 16.86, DD5 $13,766, DD 9.62 pct from peak, Sortino 1.87. "
    "$/yr $12,150 for one unit, worst DD $21,621 = 21.6 pct of a fixed $100k and 8.6 pct of $250k. Book add on "
    "the UNION of dates, one row per calendar day: book #463 $140,142/yr DD $52,238 becomes book + 1x YM "
    "$152,252/yr DD $56,263; ex-2020 $139,453 DD $38,394 becomes $152,407 DD $38,770, so $376 of ex-2020 "
    "drawdown buys $12,954 a year. Correlation with the NQ #335 leg -0.002 daily, -0.029 monthly. That clears "
    "the owner loose screen on every clause, so clause 3 of the 11-20 standing order sends it straight to 900 "
    "trials. COST DERIVED: YM tick 1.00 point on a $5 multiplier and $4 of fees = 0.80, so 1 tick + fees = "
    "1.80 points a round trip, nine times the RTY line in points. WARNINGS STATED BEFORE THE GRADE, warnings "
    "not kills per the owner 11-14 rule: the ten best trades are 96 pct of the frozen window net, the same "
    "shape that closed ENGU-Q on ES at 108 pct; the house dd5 helper flags one_episode, worst DD 1.57x DD5; "
    "win rate 28 pct; and YM loses $2,914 in Apr-Jun 2025 with its own worst drawdown troughing 2025-04-24, so "
    "it diversifies across the window but does NOT pay in the months that bind every capped mix. PRE-SET "
    "VERDICT: adopt-candidate only on a PASS, or a WEAK with folds 7 of 8 or better, AND a ten-best share below "
    "100 pct of the WF total; a grade carried by its ten best is not an adoption, which is why ES is closed. "
    "Otherwise YM closes too and the frozen read stays on file as the reason. CHANGES FROM THE NQ CROWN "
    "VALIDATE AND NOTHING ELSE: instrument NQ to YM, master ADJ_YM_1m_ETH id 155, cost 1.80, mult 5; same "
    "ranged file, 8 folds, 12-month lockbox, 900 trials. Lockbox veto only. Nothing live or paper changes. "
    "Driver tools/enguq_ym335_transfer_queue.py."
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
    print("file OK: %s, %d numeric knobs, %d with a real range" % (STRATEGY, len(numeric), len(open_knobs)))

    from augur_engine import data as D
    m = D.find_master(JOB["instrument"], JOB["timeframe"], JOB["session"], JOB["source"])
    if not m or m.get("filename") != MASTER_FILE or int(m.get("id") or 0) != MASTER_ID:
        sys.exit("ABORT - the roll-corrected YM 1m ETH master is not id %s %s: %r" % (MASTER_ID, MASTER_FILE, m))
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

    job = dict(JOB, status="queued", progress=0,
               preset="%s: ranged R2 file, frozen read passed the loose screen, cost 1.80" % TAG, note=NOTE)
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
        fh.write("%s ENGU-Q #335 transfer to YM 1.80 db_adj_eth job %s\n" % (
            datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"), ref.id))


if __name__ == "__main__":
    main()
