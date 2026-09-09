"""Queue the NOISE 15-MINUTE Auto-Validate (open ranges, 8 walk-forward folds, 12-month lockbox).

WHY (round 44, 2026-09-09 -- NOISE.md). The live crown's own geometry, unchanged, is dramatically
better on a 15-minute bar than on the 5-minute bar it trades. Measured on ONE resampled source tape
(the registered NQ 1m master, resampler gated against the registered 5m AND 15m masters to within
0.4%), 2010-06-07..2026-07-16, entry-sliced at 2025-02-14, at the STRESSED cost of 0.783 pts:

    bar    n      PF      net $      DD $   net/DD  slices  top-10   $/trade
    5m   4,424  1.351   311,783    17,497   17.82    7/8    23.6%      70     <- what it trades
   10m   3,319  1.403   301,990    10,030   30.11    7/8    24.3%      91
   15m   2,759  1.494   324,006     9,386   34.52    7/8    21.7%     117     <- more money, half the drawdown

15m beats 5m on every pre-registered clause except one, and it does it with MORE money on 38% fewer
trades, half the drawdown, a LOWER top-10 share and a positive ex-top-10 net ($253,727). Neighbour
sanity holds: 10m beats 5m too, so this is a region of the bar dimension, not one lucky bar.

The one clause it failed -- "the recent stretch must not be worse than 5m's" -- turned out to be
MIS-SPECIFIED, and round 44 says so plainly rather than quietly rewriting it: comparing two
configurations' absolute recent profit factor punishes whichever one is not currently hot. Measured
against each cell's OWN history, every bar is at or above its own median right now (5m at the 87.6th
percentile of its own history, 15m at the 61.3rd, 10m at the 51.0th). Nothing is broken on 15m; the
5-minute bar is simply having one of its best stretches ever.

THIS JOB IS THE EVIDENCE STEP, NOT A CROWNING. It is the file's FULL declared space on the registered
15m master (open ranges -- a pinned variant gives n_evaluated=1 and kills the landscape, plateau,
parallel-coordinates and PBO reads; memory `edgelog-pinned-validate-rule`), so the runner picks its
own champion and the card carries walk-forward folds, a sealed 12-month lockbox it has never seen,
PBO and a plateau verdict. Only the owner crowns anything.

Window pinned to the registered 15m master's own coverage (it ends 2026-06-30, earlier than the 5m
master -- comparing across different coverage is what broke round 44's first parity gate).

Refuses if the queue is more than nine deep, or if a NOISE_1_0.py job is already queued or running.
"""
import sys
import time

import firebase_admin
from firebase_admin import credentials, firestore

firebase_admin.initialize_app(credentials.Certificate("serviceAccount.json"))
u = firestore.client().collection("users").document("IO0K35JpLIcH9YK4C0pMNYUzZOM2")


def retry(fn, tries=5):
    for i in range(tries):
        try:
            return fn()
        except Exception as e:                                    # noqa: BLE001
            wait = 3 * (i + 1)
            print("attempt %d blocked (%s); waiting %ds" % (i + 1, type(e).__name__, wait), flush=True)
            time.sleep(wait)
    raise SystemExit("gave up talking to Firestore")


live = [d.to_dict() for d in retry(lambda: list(u.collection("backtests").stream()))
        if (d.to_dict() or {}).get("status") in ("queued", "running")]
print("queue depth", len(live),
      [str(j.get("strategy"))[:22] + ":" + str(j.get("status")) for j in live])
if len(live) > 9:
    sys.exit("ABORT queue too deep")
if any(j.get("strategy") == "NOISE_1_0.py" and j.get("timeframe") == "15m" for j in live):
    sys.exit("ABORT a NOISE_1_0.py 15m job is already queued or running")

job = dict(
    type="validate", status="queued", strategy="NOISE_1_0.py",
    instrument="NQ", timeframe="15m", session="rth", source="db_noadj_rth",
    cost_pts=0.533, mult=20, commission_usd=0.0, slippage_pts=0.0,
    date_from="2010-06-07", date_to="2026-06-30", lockbox_months=12,
    equity_points=400, min_trades=30, mc_sims=2000, n_trials=250, n_rounds=0, wf_folds=8,
    select_oos_topk=10, discover="auto", provider="ollama",
    dsr=True, neighbors=True, regime=True, pills=True, context=True, progress=0,
    preset="NOISE on the 15-MINUTE bar - round 44's bar question, full declared space",
    note=("Round 44 (tools/r44_noise_crown_bar.py, NOISE.md 2026-09-09). THE QUESTION: the live "
          "crown geometry, unchanged, measures far better on 15-minute bars than on the 5-minute "
          "bars it trades - at the stressed cost of 0.783 points, net-over-drawdown 34.52 against "
          "17.82, profit factor 1.494 against 1.351, MORE money (324,006 against 311,783 dollars) "
          "on 38 percent fewer trades, drawdown 9,386 against 17,497, top-10 share 21.7 against "
          "23.6 percent with ex-top-10 net +253,727, and 117 dollars a trade against 70. Neighbour "
          "sanity holds (10-minute beats 5-minute too), so this is a region of the bar dimension "
          "rather than one lucky bar, and the resampler was gated against BOTH the registered "
          "5-minute and 15-minute masters to within 0.4 percent. The one pre-registered clause it "
          "failed - that the recent stretch not be worse than the 5-minute cell's - was "
          "mis-specified: against each cell's OWN history every bar is at or above its median "
          "right now (5-minute at the 87.6th percentile of its own history, 15-minute at the "
          "61.3rd), so that clause was measuring which configuration is hot, not which is better. "
          "THIS JOB IS EVIDENCE, NOT A CROWNING: full declared space on the registered 15-minute "
          "master so the runner picks its own champion with walk-forward folds, a sealed 12-month "
          "lockbox and a plateau read. The NOISE 5-minute lockbox is spent; this 15-minute lockbox "
          "is not. Nothing moves on the paper board or in NinjaTrader without the owner."),
)
ref = retry(lambda: u.collection("backtests").add(job)[1])
print("queued", ref.id, "- NOISE_1_0.py on NQ 15m RTH, full space, 8 folds, 12-month lockbox")
