"""Queue the NOISE EXIT-MANAGEMENT Auto-Validate (fenced to two knobs, 8 folds, 12-month lockbox).

WHY (round 52, 2026-09-09 -- NOISE.md). Both other crowned families manage their exits: ORB rides
with a breakeven and a trail, ENGU-Q has a breakeven and a trail. NOISE sets its protective stop
once at entry and never moves it, and until this round nobody had tested whether it should.

`augur_strategies/NOISE_1_7_EXIT.py` adds the two devices, each in multiples of the trade's own
initial risk, each reading the PREVIOUS bar's finished extreme. With both off it reproduces the
parent to the cent, and its DEFAULT_PARAMS are FENCED so every other knob is pinned to the live
crown's value -- the defaults ARE the crown. Only `be_r` (0 to 2.0) and `trail_frac` (0 to 4.0)
are open: 9 x 17 = 153 cells.

What the hand measurement found, at the stressed 0.783 points a round turn:
  * every TRAIL is worse, and tighter is worse still -- 1.0R costs 0.035 of profit factor and takes
    net-over-drawdown from 19.14 to 17.96;
  * the BREAKEVEN is a genuine wash -- at 1.0R it buys about 5% of drawdown (19,493 -> 18,579, so
    net-over-drawdown 19.14 -> 20.01) for a hair less money, profit factor moving in the fourth
    decimal, and every variant is slightly worse across 2010-2023 and slightly better since 2024.

THAT NEAR-MISS IS WHY THIS JOB EXISTS. It is exactly the sort of thing a human eye should not
adjudicate: a 5% drawdown improvement with everything else level, on a spent 5-minute lockbox. This
job hands it to the strongest instrument available -- the runner's own search over the fenced grid,
with eight walk-forward folds and a twelve-month lockbox it has never seen. A non-zero breakeven
that passes is real evidence. A search that lands on zero closes the question for good.

Nothing is adopted by this job. The crown stays run #304 with its stop set once and left alone;
only the owner crowns anything.

Refuses if the queue is more than nine deep, or if this file is already queued or running.
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
        except Exception as e:                                      # noqa: BLE001
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
if any(j.get("strategy") == "NOISE_1_7_EXIT.py" for j in live):
    sys.exit("ABORT NOISE_1_7_EXIT.py is already queued or running")

job = dict(
    type="validate", status="queued", strategy="NOISE_1_7_EXIT.py",
    instrument="NQ", timeframe="5m", session="rth", source="db_noadj_rth",
    cost_pts=0.533, mult=20, commission_usd=0.0, slippage_pts=0.0,
    date_from="2010-06-07", date_to="2026-07-16", lockbox_months=12,
    equity_points=400, min_trades=30, mc_sims=2000, n_trials=200, n_rounds=0, wf_folds=8,
    select_oos_topk=10, discover="auto", provider="ollama",
    dsr=True, neighbors=True, regime=True, pills=True, context=True, progress=0,
    preset="NOISE exit management - breakeven and trail, fenced to two knobs",
    note=("Round 52 (tools/r52 harness, NOISE.md 2026-09-09). THE QUESTION: NOISE is the only one of "
          "the three crowned families whose protective stop is set once at entry and never moved - "
          "ORB and ENGU-Q both use a breakeven and a trail. The fork adds both, each in multiples of "
          "the trade own initial risk, each reading the PREVIOUS bar finished extreme so nothing is "
          "read early. With both knobs off it reproduces the parent to the cent, and its defaults "
          "are FENCED to the live crown values so only be_r (0 to 2.0) and trail_frac (0 to 4.0) are "
          "open - 153 cells. HAND MEASUREMENT AT THE STRESSED COST: every trail is worse and tighter "
          "is worse still, one multiple costing 0.035 of profit factor and taking net-over-drawdown "
          "from 19.14 to 17.96, because the NOISE edge is a slow drift back toward the session VWAP "
          "and a trail cuts it off. The breakeven is a genuine wash - at one multiple it buys about "
          "five percent of drawdown, 19,493 dollars to 18,579, for a hair less money with profit "
          "factor moving in the fourth decimal, and every variant is slightly worse across 2010 to "
          "2023 and slightly better since 2024. THAT NEAR-MISS IS WHY THIS JOB EXISTS: it is not "
          "something an eye should settle. Eight walk-forward folds and a twelve-month lockbox the "
          "search has never seen. A non-zero breakeven that passes is real evidence; a search that "
          "lands on zero closes the question. Ranked on profit factor and net-over-drawdown, never "
          "EV R - an early breakeven inflates EV R while losing money. Nothing moves without the "
          "owner."),
)
ref = retry(lambda: u.collection("backtests").add(job)[1])
print("queued", ref.id, "- NOISE_1_7_EXIT.py on NQ 5m RTH, 153 fenced cells, 8 folds, 12-month lockbox")
