"""Queue NOISE_1_0 (full declared ranges) on ES 5m RTH - the ES BRANCH of the NOISE family (round 39, 2026-09-08).

Pre-queue reads: tools/ryr_search.py noise_es5m (400 configs on 2010-06-07..2025-06-29, 0.30 pts/RT, $50/pt) =
41 of 400 pass the search gates; leader lookback 62 / bands 1.0-1.75 / vwap exit / both sides / all day:
n=3151 / $138,185 / PF 1.285 / DD $12,845 / MAR 10.8 / 7-of-8 / top-10 35% (ex-top-10 +$90,422 PF 1.19) =
SPREAD; plateau 26 of 28 one-step neighbours hold (the boundary exit is the one cliff). The crown card's own
NQ parameters score only PF 1.24 on ES (round 37), so the ES leg needs its own search - which is exactly what
a full-space validate is. Window pinned to the NOISE crown run #243 (read from its run doc at queue time),
12-month lockbox, 8 walk-forward folds. NOTHING from the local search is pinned into the job.

    python tools/queue_noise_es_validate.py
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


crown = u.collection("runs").document("243").get().to_dict() or {}
d_from, d_to = crown.get("date_from") or "2010-06-07", crown.get("date_to")
if not d_to:
    sys.exit("ABORT: run #243 has no date_to to pin to")
print("pinning to NOISE crown #243 window", d_from, d_to)
live = _retry(lambda: [(d.to_dict() or {}) for d in u.collection("backtests")
                       .where("status", "in", ["queued", "running"]).stream()])
print("queue depth", len(live), [str(j.get("strategy"))[:24] + ":" + str(j.get("instrument")) + ":" + str(j.get("status")) for j in live])
if len(live) > 9: sys.exit("ABORT queue too deep")
if any(j.get("strategy") == "NOISE_1_0.py" and j.get("instrument") == "ES" for j in live):
    sys.exit("ABORT NOISE_1_0 on ES already queued/running")
job = dict(type="validate", status="queued", strategy="NOISE_1_0.py",
    instrument="ES", timeframe="5m", session="rth", source="db_noadj_rth",
    cost_pts=0.30, mult=50, commission_usd=0.0, slippage_pts=0.0,
    date_from=d_from, date_to=d_to, lockbox_months=12,
    equity_points=400, min_trades=30, mc_sims=2000, n_trials=250, n_rounds=0, wf_folds=8,
    select_oos_topk=10, discover="auto", provider="ollama",
    dsr=True, neighbors=True, regime=True, pills=True, context=True, progress=0,
    preset="NOISE 1.0 full space on ES 5m RTH - the ES BRANCH of the NOISE family (round 39)",
    note=("Round 39 (tools/ryr_search.py noise_es5m, tools/ryr_neighbourhood.py). The NOISE crown card at its NQ "
          "parameters is a near miss on ES (PF 1.24, 5 of 8 slices, round 37); NOISE_1_0's own ranges searched on "
          "ES 5m RTH 2010-06-07..2025-06-29 at 0.30 points a round trip and 50 dollars a point: 41 of 400 "
          "configurations clear PF 1.25 / n 300 / 6 of 8 slices. Search leader (lookback 62, bands 1.0 long / "
          "1.75 short, VWAP exit, both sides, all day): 3,151 trades / $138,185 / PF 1.29 / DD $12,845 / "
          "n-per-DD 10.8 / 7 of 8 / EV R 0.18 / R-per-YR 38; concentration SPREAD (top-10 share 35 percent, "
          "ex-top-10 +$90,422 at PF 1.19); plateau 26 of 28 one-step neighbours hold (the boundary exit is the one "
          "cliff; flat-at-close makes no difference because the VWAP exit is flat by the close anyway). Thin in "
          "dollars (about $9k a year on one ES) but a real, spread, plateaued edge - the second crowned mechanism "
          "to branch onto ES after ENGU-Q. This validate searches the FULL declared space (nothing from the local "
          "search is pinned) with 8 folds and a 12-month lockbox, window pinned to the NOISE crown run #243 so "
          "the NQ and ES branches are comparable."))
job["createdAt"] = datetime.datetime.now(datetime.timezone.utc)
ref = u.collection("backtests").document(); _retry(lambda: ref.set(job))
print("queued", ref.id, job["strategy"], "on", job["instrument"], job["date_from"], job["date_to"])
