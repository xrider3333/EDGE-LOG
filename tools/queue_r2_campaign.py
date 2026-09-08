"""Queue the three jobs from the EV R / R-per-year campaign. Owner-approved 2026-09-05
("go with the be2.0 sibling and queue both when quota resets ... if you think it beats it,
autovalidate it"). Firestore was over its daily quota when they were approved, so this
script exists to fire them all in one go:

    python tools/queue_r2_campaign.py

It is safe to re-run only if the earlier attempt failed - it does not check for duplicates,
so do not run it twice on purpose.

--------------------------------------------------------------------------------------
WHAT IS BEING QUEUED, AND WHY EACH ONE

1. AUTO-VALIDATE of `ENGUQ_1M_ETH_R2_1_0.py` - the crowned run #309 with the trading logic
   untouched and two defaults moved: breakeven_R 3.0 -> 2.0 and stop_mult 1.3 -> 1.0.
   Measured on 2010-06-07..2026-06-30, NQ 1m ETH, cost 0.533 x $20:

                    trades      net      PF    EV R   R/YR      DD    MAR   LB  top-10  hold
       #309 crown    1,604   $591,267  1.655   0.434   43.4  $48,900  0.75   99   58%   282d
       R2 (be2.0)    1,949   $613,126  1.711   0.503   61.0  $41,534  0.92  118   56%   142d

   R2 beats the crown on EVERY read at once - more net, higher profit factor, higher EV R,
   +41% R per year, +23% MAR, -15% drawdown, more held-out trades, a cleaner tail and half
   the longest hold. Nothing is traded away, which is why it is worth a validate slot.
   Held-out year alone: 118 trades, PF 1.675, EV R 0.487, R per year 57.5, MAR 2.13, against
   the crown's 99 trades, PF 1.620, EV R 0.407, R per year 40.4, MAR 1.75.

2. BOOK: the frontier pair with the R2 leg in place of the crown. This is the first thing in
   the campaign to DOMINATE run #317 rather than trade one read for another:
   EV R 0.429 -> 0.456, R per year 202 -> 225, PF 1.526 -> 1.556, MAR 1.19 -> 1.38,
   drawdown $40,129 -> $35,399, held-out trades 520 -> 539, top-10 45% -> 43%.

3. BOOK: the frontier TRIO with the R2 leg - the pair plus a second NOISE configuration that
   trades the AFTERNOON block long-only while the incumbent NOISE leg trades the MORNING, so
   they diversify rather than duplicate. Highest R per year and best held-out MAR measured
   anywhere in this project: full window n=12,588, PF 1.500, EV R 0.415, R per year 325.2,
   MAR 1.34, drawdown $44,317, 790 held-out trades, top-10 36%; held-out year PF 1.457,
   EV R 0.376, R per year 297.0, MAR 3.32. It trades ~8% of EV R for ~45% more R per year
   against the pair, so the pair and the trio answer different questions and both are queued.

--------------------------------------------------------------------------------------
CAVEATS THAT TRAVEL WITH ALL THREE

* R2's two knobs were chosen by a sweep on the whole window. Re-scored on PRE-LOCKBOX data
  only, be1.5/stop1.0 ranks first and be2.0/stop1.0 second by a hair (MAR 0.90 vs 0.96); the
  owner chose be2.0 because it dominates on every read and wins the held-out year outright.
  Both sit inside the file's fence, so the validate sees both. The reassuring part: every
  cell that beat the crown before the lockbox also beat it inside the held-out year, so the
  ranking is stable across the split.
* R2's era split is 2-2, not 4-0: profit factor slips slightly in 2010-14 and 2018-22 and
  improves in 2014-18 and 2022-26.
* The books' NOISE legs were both found by searches on this same window, so the books inherit
  that selection. Their held-out figures are the unselected part.
* EV R and R per year can BOTH be inflated by simply sizing one leg up (0.429 -> 0.518 at 10x
  with zero extra trades). Every book here is strictly 1:1 (or 1:1:1) and annualised MAR is
  the read that catches leverage - it RISES in all three, which is the evidence the gains are
  real rather than leverage.
* Nothing here moves the paper board. #309 stays the crown and the live leg until the owner
  says otherwise.
"""
import argparse
import datetime
import os
import sys

import firebase_admin
from firebase_admin import credentials, firestore

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from queue_guard import guard, split_from_lockbox         # noqa: E402  (--guard, opt-in)

CRED = r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG\serviceAccount.json"
UID = "IO0K35JpLIcH9YK4C0pMNYUzZOM2"
WIN = {"date_from": "2010-06-07", "date_to": "2026-06-30"}

R2_PARAMS = dict(buf_atr=0.3, tl_len=206, trail_frac=2.5, limit_atr=0.55, atr_len=52,
                 act_R=1.5, breakeven_R=2.0, ema_len=220, er_len=100, stop_mult=1.0,
                 regime_len=10, min_brk=1.6, vol_mult=1.1, er_th=0.0)
NOISE_MORNING = dict(daytype_lo=0.25, window="morning", confirm_bars=1, daytype_mode="off",
                     band_mult_long=0.75, vol_skip_pct=82.0, band_mult_short=1.5,
                     skip_holidays=True, stop_mode="bandwidth", flat_eod=True, lookback=24,
                     side="Both", daytype_hi=0.7, stop_k=1.0, exit_mode="boundary")
NOISE_AFTERNOON = dict(lookback=9, band_mult_long=0.5, band_mult_short=2.0,
                       exit_mode="boundary", side="Long Only", window="afternoon_block",
                       flat_eod=True, skip_holidays=False, stop_mode="off", confirm_bars=2,
                       daytype_mode="off", daytype_lo=0.1, daytype_hi=0.7,
                       vol_skip_pct=78.0, stop_k=2.75)

NQ5 = dict(instrument="NQ", timeframe="5m", session="rth", source="db_noadj_rth",
           cost_pts=0.533, mult=20, weight=1)
NQ1E = dict(instrument="NQ", timeframe="1m", session="eth", source="db_noadj_eth",
            cost_pts=0.533, mult=20, weight=1)

LEG_MORNING = dict(NQ5, strategy="NOISE_1_2_RYR.py", params=NOISE_MORNING)
LEG_AFTERNOON = dict(NQ5, strategy="NOISE_1_0.py", params=NOISE_AFTERNOON)
LEG_R2 = dict(NQ1E, strategy="ENGUQ_1M_ETH_R2_1_0.py", params=R2_PARAMS)

VALIDATE = dict(
    WIN, type="validate", strategy="ENGUQ_1M_ETH_R2_1_0.py", discover="auto",
    n_trials=300, n_rounds=5, dsr=True, workers=4, provider="claude-cli", min_trades=30,
    wf_folds=0, lockbox_months=12, equity_points=400, instrument="NQ", timeframe="1m",
    session="eth", source="db_noadj_eth", mult=20, cost_pts=0.533, slippage_pts=0.0,
    commission_usd=0.0,
    preset="ENGU-Q R2 - crown plus the two risk knobs (fenced) full discovery",
    note=("ENGU-Q R2 = crowned run #309, trading logic untouched, two defaults moved: breakeven_R 3.0 to 2.0 "
          "and stop_mult 1.3 to 1.0, both FENCED to the measured neighbourhood. #309's own search maximised net "
          "and drawdown, never MAR or R per year, and pushed breakeven_R to the top of its range so the stop "
          "almost never interfered - which is why 58pct of its net sat in ten trades with a 282-day hold. "
          "MEASURED 2010-06-07..2026-06-30 NQ 1m ETH cost 0.533x20 - crown n=1604 net 591267 PF 1.655 EVR 0.434 "
          "RYR 43.4 DD 48900 MAR 0.75 LB 99 top10 58pct hold 282d; R2 n=1949 net 613126 PF 1.711 EVR 0.503 "
          "RYR 61.0 DD 41534 MAR 0.92 LB 118 top10 56pct hold 142d - better on EVERY read, nothing traded away. "
          "HELD-OUT YEAR crown 99 tr PF 1.620 EVR 0.407 RYR 40.4 MAR 1.75; R2 118 tr PF 1.675 EVR 0.487 RYR 57.5 "
          "MAR 2.13. SELECTION CHECK: on pre-lockbox data only be1.5/stop1.0 ranks first and be2.0 second by a "
          "hair (MAR 0.90 vs 0.96); owner chose be2.0 for dominating every read and winning the held-out year. "
          "Every cell beating the crown pre-lockbox also beat it in the held-out year, so the ranking is stable "
          "across the split. CAVEAT: era split 2-2 not 4-0 (PF slips 2010-14 and 2018-22, improves 2014-18 and "
          "2022-26). Nothing moves on the paper board without the owner."),
    status="queued", progress=0)

BOOK_COMMON = dict(WIN, type="book", mult=1, status="queued", progress=0,
                   equity_points=400, lockbox_months=12, slices=None)

PAIR_NAME = "BOOK: FRONTIER PAIR with the R2 leg"
BOOK_PAIR = dict(
    BOOK_COMMON, strategy=PAIR_NAME, preset=PAIR_NAME,
    book_name="2-LEG - NOISE morning (RYR) + ENGU-Q R2, 1:1",
    legs=[LEG_MORNING, LEG_R2],
    note=("The run #317 frontier pair with its ENGU-Q leg upgraded from the #309 crown to R2 (breakeven 2.0, "
          "stop 1.0). First thing in this campaign to DOMINATE #317 instead of trading one read for another: "
          "EVR 0.429 to 0.456, RYR 202.1 to 224.7, PF 1.526 to 1.556, MAR 1.19 to 1.38, DD 40129 to 35399, "
          "held-out trades 520 to 539, top10 44.6 to 43.3pct, longest hold 282d to 142d. One contract per leg, "
          "no leg selection; the #317 anchor reproduces to the dollar (DD 40129) which is the check the pooling "
          "is right. CAVEAT: both legs were search-selected on this window, so the held-out figures are the "
          "unselected part; and EV R / R per year can be inflated by leg weighting, so this is strictly 1:1 and "
          "MAR is the guard - it rises here."))

TRIO_NAME = "BOOK: FRONTIER TRIO with the R2 leg"
BOOK_TRIO = dict(
    BOOK_COMMON, strategy=TRIO_NAME, preset=TRIO_NAME,
    book_name="3-LEG - NOISE morning (RYR) + NOISE afternoon (EV R) + ENGU-Q R2, 1:1:1",
    legs=[LEG_MORNING, LEG_AFTERNOON, LEG_R2],
    note=("The pair above plus a second NOISE configuration from an EV R-objective search (250 configs, 2 cleared "
          "the gates). It trades the AFTERNOON block long-only while the incumbent NOISE leg trades the MORNING, "
          "which is why they diversify rather than duplicate. Highest R per year and best held-out MAR measured "
          "anywhere in this project. FULL WINDOW n=12588 net 955659 PF 1.500 EVR 0.415 RYR 325.2 DD 44317 MAR 1.34 "
          "LB 790 top10 35.7pct. HELD-OUT YEAR PF 1.457 EVR 0.376 RYR 297.0 MAR 3.32 (the pair reads 198.8 and 2.31). "
          "Against the pair it trades about 8pct of EV R for about 45pct more R per year, so the two answer "
          "different questions and both are queued. CAVEAT: two of three legs were search-selected on this window; "
          "strictly 1:1:1 weighting, MAR is the guard against leverage and it rises."))


def _guard_legs(label, job):
    """--guard (2026-09-07, opt-in, default OFF): run tools/queue_guard.py's continuous-lockbox
    check on every leg of a BOOK job before it is queued. Refuses (raises) if any leg comes
    back ARTIFACT -- the #310 empty-continuous-lockbox shape, or the ex-top-10-net-goes-negative
    shape two BOOK legs showed on 2026-09-05 (see queue_guard.py's module docstring). SUSPECT
    is printed but does not block: concentration alone must never fail a leg on its own
    (ENGUQ.md section 1.0 -- the deployed ENGU-Q leg runs an 80% top-10 share, NOISE crowns
    22-42%). A job with no "legs" (the plain VALIDATE search job) is a no-op."""
    legs = job.get("legs")
    if not legs:
        return
    split = split_from_lockbox(job["date_to"], job.get("lockbox_months", 12))
    for leg in legs:
        res = guard(leg["strategy"], leg.get("params") or {}, instrument=leg["instrument"],
                   timeframe=leg["timeframe"], session=leg["session"], source=leg["source"],
                   cost_pts=leg["cost_pts"], mult=leg["mult"], date_from=job["date_from"],
                   date_to=job["date_to"], split=split, label=f"{label} :: {leg['strategy']}")
        if res["verdict"] == "ARTIFACT":
            sys.exit(f"ABORT -- {label} leg {leg['strategy']} is ARTIFACT, refusing to queue "
                     f"(see the guard printout above)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--guard", action="store_true",
                    help="run tools/queue_guard.py on every BOOK leg first; refuse to queue "
                         "any job whose leg comes back ARTIFACT (default off, behaviour "
                         "otherwise unchanged)")
    args = ap.parse_args()
    if not firebase_admin._apps:
        firebase_admin.initialize_app(credentials.Certificate(CRED))
    col = firestore.client().collection("users").document(UID).collection("backtests")
    now = datetime.datetime.now(datetime.timezone.utc)
    for label, job in (("R2 auto-validate", VALIDATE),
                       ("BOOK pair + R2", BOOK_PAIR),
                       ("BOOK trio + R2", BOOK_TRIO)):
        if args.guard:
            _guard_legs(label, job)
        ref = col.add(dict(job, createdAt=now))[1]
        print("queued %-18s %s" % (label, ref.id))


if __name__ == "__main__":
    main()
