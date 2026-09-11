"""Queue the NOISE COMPRESSION-TILT-ON-THE-LIVE-CROWN Auto-Validate (24 fenced cells).

WHY (round 54, 2026-09-11 -- NOISE.md). Run #333 validated the hourly-compression size tilt on
NOISE and it is the only size tilt in the family that survives the shift null. But #333, and both
deployed paper legs, freeze their core to NOISE_1_1_SBS_V90.py's defaults -- lookback 44 and
volatility skip 90 -- which is run #243, the crown the family RETIRED on 2026-09-05 when run #304
moved those two knobs to 40 and 95. So the best validated improvement to NOISE forward-tests on a
base that is no longer traded, while the base that IS traded forward-tests without it. That was
found the same way the KEEL staleness was found the day before: by reading which base a leg pins
rather than which base its name suggests.

WHAT THE HAND BATTERY ALREADY SAYS (tools/tilt_guard.py, shift null, 2000 permutations). The tilt
is REAL on the live crown: it beats its own exposure-matched flat control on both stretches and at
both sizes, and 2.1% of shifts match it. It also FAILS the house drawdown clause there -- sealed-
year drawdown grows 17.9% against a 10% tolerance at 1.5x, and 35.8% at 2.0x. On the retired #243
base the identical tilt PASSES the whole battery clean at 1.5x, drawdown growing only 6.0%, with
0.0% of shifts matching. The reason looks structural rather than accidental: #304 loosened the
volatility skip from the 90th percentile to the 95th, so it takes about 400 more trades in noisier
conditions, and sizing those up inside a compressed hour compounds the drawdown that the looser
skip already bought. The tighter skip and the tilt are complementary; the looser skip and the tilt
are not.

THAT IS WHY THIS JOB EXISTS. The hand battery is one harness with one drawdown tolerance. This
hands the same question to the house instrument -- the runner's own search over the fenced grid,
eight walk-forward folds and a twelve-month lockbox it has never seen -- with the tilt switched
OFF (1.0x) inside the admissible set as its own parity control. If the search lands on 1.0x it
says the tilt does not belong on the live crown and the deployed legs are right where they are.

`augur_strategies/NOISE_1_8_CT304.py` writes run #304's champion out literally rather than reading
any file's defaults: NOISE_1_1_NBHD.py still defaults to 44/90 and only its RANGES span the crown,
so reading defaults would silently rebuild #243 a second time. Parity checked before queueing --
at 1.0x it reproduces the live crown's 4,833 trades bar for bar with a worst per-trade gap of
zero.

Nothing is adopted by this job. The crown stays run #304 raw; only the owner crowns anything.

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
if any(j.get("strategy") == "NOISE_1_8_CT304.py" for j in live):
    sys.exit("ABORT NOISE_1_8_CT304.py is already queued or running")

job = dict(
    type="validate", status="queued", strategy="NOISE_1_8_CT304.py",
    instrument="NQ", timeframe="5m", session="rth", source="db_noadj_rth",
    cost_pts=0.533, mult=20, commission_usd=0.0, slippage_pts=0.0,
    date_from="2010-06-07", date_to="2026-07-16", lockbox_months=12,
    equity_points=400, min_trades=30, mc_sims=2000, n_trials=120, n_rounds=0, wf_folds=8,
    select_oos_topk=10, discover="auto", provider="ollama",
    dsr=True, neighbors=True, regime=True, pills=True, context=True, progress=0,
    preset="NOISE compression size tilt on the LIVE crown - 24 fenced cells",
    note=("Round 54 (NOISE.md 2026-09-11). THE QUESTION: run #333 validated the hourly-compression "
          "size tilt on NOISE, the only size tilt in the family that survives the shift null - but "
          "it froze its core to lookback 44 and volatility skip 90, which is run #243, the crown "
          "the family retired on 2026-09-05. Both deployed compression paper legs pin the same "
          "retired base. So the best validated improvement to NOISE forward-tests on a base nobody "
          "trades while the traded base forward-tests without it. This file is that tilt with the "
          "core re-based onto run #304, written out literally rather than read from defaults - the "
          "parent file still defaults to 44 and 90 and only its ranges span the crown, so reading "
          "defaults would rebuild the retired base a second time. Parity checked before queueing: "
          "at size 1.0 it reproduces the live crown 4833 trades bar for bar, worst per-trade gap "
          "zero. HAND BATTERY, shift null, 2000 permutations: on the live crown the tilt beats its "
          "own exposure-matched flat control on both stretches at both sizes and 2.1 percent of "
          "shifts match it, but sealed-year drawdown grows 17.9 percent against a 10 percent "
          "tolerance at 1.5x and 35.8 percent at 2.0x. On the retired base the identical tilt "
          "passes clean at 1.5x with drawdown growing 6.0 percent and zero of 2000 shifts matching. "
          "The likely reason is structural: the live crown loosened the volatility skip from the "
          "90th percentile to the 95th and so takes about 400 more trades in noisier conditions, "
          "and sizing those up inside a compressed hour compounds the drawdown the looser skip "
          "already bought. THE BAR, pre-registered in the strategy file docstring and never re-cut: "
          "verdict PASS, or WEAK where the overfit check is the only failing gate; AND the sealed "
          "year earns at least the live crown 84,580 dollars at a sealed-year drawdown no more than "
          "25 percent above the crown; AND annualised MAR at least the crown. Size 1.0 is inside "
          "the admissible set as the parity control - a search that lands there says the tilt does "
          "not belong on the live crown and the deployed legs are right where they are. Because "
          "runs #331 and #333 both showed a realised drawdown shallower than 94 to 98 percent of "
          "their own resampled paths, judge the drawdown clause against the resampled 95th "
          "percentile as well as the realised one. Nothing moves without the owner."),
)
ref = retry(lambda: u.collection("backtests").add(job)[1])
print("queued", ref.id, "- NOISE_1_8_CT304.py on NQ 5m RTH, 24 fenced cells, 8 folds, 12-month lockbox")
