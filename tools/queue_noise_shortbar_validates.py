"""Queue the round-37 SHORT-BAR NOISE Auto-Validates: NOISE_1_0.py, full declared space, on the
NQ 2m RTH master and on the NQ 1m RTH master (owner 2026-09-08: "focus more on the shorter side
like scalping").

Why the PARENT file and not a pinned leader: the house rule (CLAUDE.md, "Auto-Validate = FULL
search space, never a pinned file"). The round-37 search leader on 2m is evidence the space is
worth searching there; the runner's own search is the judge.

Pre-queue gates already run (2026-09-08, tools/r37_results/):
  2m search leader (tools/ryr_search.py noise2m, 300 configs, selection window 2010-06-07..
  2025-06-29): n=5,340 / $213,549 / PF 1.477 / DD $10,917 / MAR 19.6 / EV R 0.40 / R/YR 140.6 /
  6-of-8 slices / median hold 4 minutes. Plateau (ryr_neighbourhood.py): 30/30 one-step
  neighbours PF >= 1.25, 27/30 keep >= 50% of the leader's R/YR, median neighbour 139.
  Concentration: top-10 share 34%, ex-top-10 +$141,865 at PF 1.32 -> a spread edge.
  Reference: the paper crown #243's own config on 2m bars = MAR 24.8 / R/YR 96.9 vs 18.2 / 72.9
  on its native 5m bars, so the bar size itself is the lever.

Windows: 2m master ends 2026-07-16 (registered resample), so its window is 2010-06-07..2026-07-16
with a 17-month lockbox (~2025-02-16 on); 1m gets the NOISE crown window 2010-06-07..2026-08-12 with
the same 18-month lockbox as run #305 (2025-02-11 on). SAID OUT LOUD ON BOTH CARDS: this lockbox is
the NOISE family's SPENT lockbox (read repeatedly since 2026-08-12); a different bar size is a
different view of the same market days, not new data. The walk-forward folds are the fresh evidence.

    python tools/queue_noise_shortbar_validates.py [2m|1m|both]

Refuses if the queue is more than nine deep; refuses a duplicate (same file + timeframe queued or
running).
"""
import os, sys, datetime, time
os.chdir(r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG")
import firebase_admin
from firebase_admin import credentials, firestore
from google.api_core import exceptions as _gx
if not firebase_admin._apps:
    firebase_admin.initialize_app(credentials.Certificate("serviceAccount.json"))
u = firestore.client().collection("users").document("IO0K35JpLIcH9YK4C0pMNYUzZOM2")

WHICH = (sys.argv[1] if len(sys.argv) > 1 else "both").lower()


def _retry(fn, tries=4, wait=300):
    for i in range(tries):
        try:
            return fn()
        except (_gx.ResourceExhausted, _gx.ServiceUnavailable, _gx.DeadlineExceeded) as e:
            print("attempt %d blocked (%s); waiting %ds" % (i + 1, type(e).__name__, wait), flush=True)
            if i == tries - 1:
                raise
            time.sleep(wait)


COMMON = dict(type="validate", status="queued", strategy="NOISE_1_0.py",
    instrument="NQ", session="rth", source="db_noadj_rth",
    cost_pts=0.533, mult=20, commission_usd=0.0, slippage_pts=0.0,
    equity_points=400, min_trades=30, mc_sims=2000, n_trials=250, n_rounds=0, wf_folds=8,
    select_oos_topk=10, discover="auto", provider="ollama",
    dsr=True, neighbors=True, regime=True, pills=True, context=True, progress=0)

SPENT = ("LOCKBOX CAVEAT, said out loud: this is the NOISE family's SPENT lockbox (the same market "
         "days runs #243/#305/#319 were graded on, read repeatedly since 2026-08-12); a different "
         "bar size is another view of the same tape, not new data. The walk-forward folds are the "
         "fresh evidence on this card; read the lockbox as confirmatory only.")

JOBS = {
    "2m": dict(COMMON, timeframe="2m", date_from="2010-06-07", date_to="2026-07-16", lockbox_months=17,
        preset="NOISE 1.0 on 2-MINUTE bars - round 37 scalp hunt (full space, the bar size is the lever)",
        note=("Round 37 (tools/r37_scalp_triage.py, tools/ryr_search.py noise2m, ryr_neighbourhood.py). "
              "Owner asked for the SHORTER side. Every new short-hold mechanism on 1m died (0 of 39 "
              "cells: fixed 1R/2R targets cannot pay twice the cost; only ride-to-close variants earn, "
              "and those are not scalps). What DOES shorten is the NOISE band itself: the paper crown "
              "#243's own config on 2m bars = n 6,431 / PF 1.338 / DD $12,873 / MAR 24.8 / R/YR 96.9 / "
              "median hold 12 min, against 18.2 / 72.9 / 40 min on its native 5m. A 300-config search of "
              "this file's own ranges on 2m found a leader at n=5,340 / $213,549 / PF 1.477 / DD $10,917 "
              "/ MAR 19.6 / EV R 0.40 / R/YR 140.6 / 6-of-8 slices / median hold 4 MINUTES (boundary exit, "
              "ATR stop 3.5, confirm 4, skip-top-long); plateau 30/30 neighbours PF >= 1.25, 27/30 keep "
              "half its R/YR; concentration top-10 34%, ex-top-10 +$141,865 at PF 1.32. The NOISE R/YR "
              "record before this was 102.6 (#319, WEAK). This card runs the PARENT file's full space on "
              "the 2m master so the runner picks its own champion; window ends 2026-07-16 because the 2m "
              "master (a registered resample of the 1m tape) ends there; lockbox 17 months from about "
              "2025-02-16 to match #305's start. " + SPENT)),
    "1m": dict(COMMON, timeframe="1m", date_from="2010-06-07", date_to="2026-08-12", lockbox_months=18,
        preset="NOISE 1.0 on 1-MINUTE bars - round 37 scalp hunt (full space, crown window #305)",
        note=("Round 37 (tools/r37_scalp_triage.py, tools/ryr_search.py noise1m). The 1-minute twin of the "
              "2m card: same file, same full space, the NOISE crown window and 18-month lockbox of run #305 "
              "(2010-06-07..2026-08-12, lockbox 2025-02-11 on). Reference on 1m: the #243 crown config = "
              "n 9,516 / PF 1.255 / DD $15,408 / MAR 18.0 / R/YR 113 / median hold 3 min but only 5-of-8 "
              "slices and $29 a trade (2.7x cost) - the 1m tape pays less per trade, so this card asks "
              "whether the runner's own search can find a 1m cell that clears the folds. " + SPENT)),
}

live = _retry(lambda: [(d.to_dict() or {}) for d in u.collection("backtests")
                       .where("status", "in", ["queued", "running"]).stream()])
print("queue depth", len(live), [str(j.get("strategy"))[:20] + "/" + str(j.get("timeframe")) + ":" + str(j.get("status")) for j in live])
if len(live) > 9:
    sys.exit("ABORT queue too deep")
for key in (("2m", "1m") if WHICH == "both" else (WHICH,)):
    job = dict(JOBS[key])
    if any(j.get("strategy") == "NOISE_1_0.py" and str(j.get("timeframe")) == key for j in live):
        print("SKIP %s: NOISE_1_0 %s already queued/running" % (key, key)); continue
    job["createdAt"] = datetime.datetime.now(datetime.timezone.utc)
    ref = u.collection("backtests").document(); _retry(lambda: ref.set(job))
    print("queued", ref.id, job["strategy"], job["timeframe"], job["date_from"], job["date_to"], "lockbox", job["lockbox_months"])
