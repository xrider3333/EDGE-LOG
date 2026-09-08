"""Queue the GAPGO 1.0 family-seed Auto-Validate (open ranges, 8 WF folds, 12-month lockbox).

Pre-queue gates already run (2026-09-08): parity with the round-33b harness cell is exact
(n=2007 / $151,024 / PF 1.341 / DD $16,672), tools/concentration_check.py = CONCENTRATED
(top-10 share 50%, ex-top-10 +$74,781 at PF 1.17 -> queueable, said out loud on the card),
and tools/gapgo_vs_orb_overlap.py measured the overlap with the ORB crown (see the note).
Window pinned to the ORB crown's certified window (2010-06-07 .. 2026-08-13) so the two
are comparable; lockbox = the last 12 months of it, never opened locally.

    python tools/queue_gapgo_validate.py

Refuses if the queue is more than nine deep. Idempotent guard: refuses if a GAPGO_1_0 job
is already queued or running.
"""
import os, sys, datetime, time
os.chdir(r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG")
import firebase_admin
from firebase_admin import credentials, firestore
from google.api_core import exceptions as _gx
if not firebase_admin._apps:
    firebase_admin.initialize_app(credentials.Certificate("serviceAccount.json"))
u = firestore.client().collection("users").document("IO0K35JpLIcH9YK4C0pMNYUzZOM2")


def _retry(fn, tries=4, wait=300):
    for i in range(tries):
        try:
            return fn()
        except (_gx.ResourceExhausted, _gx.ServiceUnavailable, _gx.DeadlineExceeded) as e:
            print("attempt %d blocked (%s); waiting %ds" % (i + 1, type(e).__name__, wait), flush=True)
            if i == tries - 1:
                raise
            time.sleep(wait)


live = _retry(lambda: [(d.to_dict() or {}) for d in u.collection("backtests")
                       .where("status", "in", ["queued", "running"]).stream()])
print("queue depth", len(live), [str(j.get("strategy"))[:24] + ":" + str(j.get("status")) for j in live])
if len(live) > 9: sys.exit("ABORT queue too deep")
if any(j.get("strategy") == "GAPGO_1_0.py" for j in live): sys.exit("ABORT GAPGO_1_0 already queued/running")
job = dict(type="validate", status="queued", strategy="GAPGO_1_0.py",
    instrument="NQ", timeframe="5m", session="rth", source="db_noadj_rth",
    cost_pts=0.533, mult=20, commission_usd=0.0, slippage_pts=0.0,
    date_from="2010-06-07", date_to="2026-08-13", lockbox_months=12,
    equity_points=400, min_trades=30, mc_sims=2000, n_trials=250, n_rounds=0, wf_folds=8,
    select_oos_topk=10, discover="auto", provider="ollama",
    dsr=True, neighbors=True, regime=True, pills=True, context=True, progress=0,
    preset="GAPGO 1.0 - FAMILY SEED: overnight-gap direction + first-bar confirmation (round 33)",
    note=("Round 33 family seed (tools/r33_family_seeds2.py, tools/r33b_ovngo_controls.py). NEW "
          "MECHANISM: trade the direction of the overnight gap (open minus prior RTH close, at least "
          "gap_mult x the 20-day average daily range) once a bar CLOSES beyond the first 5-minute "
          "bar in that direction; stop = stop_mult x first-bar range, breakeven at 1R (PINNED - a "
          "searched breakeven games EV R), flat at the close, roll-seam days skipped by the calendar "
          "detector. Triage centre (gap 0.15 / stop 0.75 / 1 bar) on 2010-06-07..2025-06-29: n=2007 "
          "/ $151,024 / PF 1.341 / DD $16,672 / n-per-DD 9.06 / 8-of-8 chronological slices / EV R "
          "0.26 / R-per-YR 35. CONTROLS say the gap direction is the edge: plain 5-minute ORB both "
          "sides PF 1.10 and 4-of-8; AGAINST the gap loses once its ten biggest winners are removed; "
          "any-size gap direction PF 1.20 and 8-of-8. CONCENTRATION (said out loud): top-10 share "
          "50 percent, ex-top-10 +$74,781 at PF 1.17 = queueable, not spread. Open knobs: gap_mult "
          "0.10-0.30, stop_mult 0.5-1.0, or_bars 1-3 (45 cells). Window pinned to the ORB crown's "
          "(#234/#314) so the two are comparable; the lockbox has never been loaded locally. This is "
          "OVERLAP WITH THE ORB CROWN (tools/gapgo_vs_orb_overlap.py): 63 percent of its trade days are ORB days, same direction on 61 percent of them, daily-PnL correlation 0.19 (0.35 on shared days), and $136,164 of its $151,024 is earned on ORB days - a new TRIGGER on the same opening-momentum factor, not a diversifier (ORB+GAPGO 1:1 n-per-DD 10.03 vs ORB alone 10.32). "
          "a SEED, not a challenger: the ask is whether the mechanism survives a walk-forward and a "
          "sealed year, so another session can develop the family."))
job["createdAt"] = datetime.datetime.now(datetime.timezone.utc)
ref = u.collection("backtests").document(); _retry(lambda: ref.set(job))
print("queued", ref.id, job["strategy"])
