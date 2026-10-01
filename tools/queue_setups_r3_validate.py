"""Queue the SETUPS round 3 Auto-Validate: CBU-Q 2.0 (CBU rules v1) on NQ 1m 24h, roll-corrected
(SETUPS_PREREG_R3_CBU_V1.md sections 4, 4a and 9).

Triage (tools/setups_r3_triage.py, 16 cells fixed in eb6bf3e8 before the run): exactly one cell passes and
advances. That cell is NQ base any / window am / exit ride (vol 1.5x, range 1.2 ATR, body 0.7 ATR):
  - n=1,320, $9,786 for one MNQ after 1.20 pts a round trip;
  - PF 1.59, net/DD 10.6, 6 of 8 slices, top-10 share 54% (ex-top-10 +$4,496);
  - stress PF 1.53, 6 of 7 one-step neighbours >= 1.15.
NOISE #382 overlap, said out loud: 84% of its trades are on #382 days, 97% of them in the same direction,
and it loses on #382-flat days. That makes it a candidate for that crown's factor; the validate grades it.

Job as pre-registered:
  - 900 trials, 8 walk-forward folds, window 2010-06-07..2026-04-06 with a 9-month lockbox
    (2025-07-07..2026-04-06, so no journal trade sits in it);
  - the FADJ (roll-corrected) master;
  - micro cost (MNQ 1.20 pts at $2);
  - the file's declared ranges only (auto_expand off), transfer to ES.

    python tools/queue_setups_r3_validate.py [--dry]
"""
import datetime
import os
import sys
import time

os.chdir(r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG")
STRAT = "CBUQ_2_0.py"
JOB = dict(type="validate", status="queued", strategy=STRAT,
           instrument="NQ", timeframe="1m", session="eth", source="db_fadj_eth",
           cost_pts=1.20, mult=2, commission_usd=0.0, slippage_pts=0.0,
           date_from="2010-06-07", date_to="2026-04-06", lockbox_months=9,
           equity_points=400, min_trades=30, mc_sims=2000, n_trials=900, n_rounds=0, wf_folds=8,
           select_oos_topk=10, oos_sample_k=0, auto_expand=False, transfer_to="ES",
           discover="auto", provider="ollama",
           dsr=True, neighbors=True, regime=True, pills=True, context=True, progress=0,
           preset="SETUPS round 3 - CBU-Q 2.0 on NQ 1m 24h (CBU rules v1, written from the owner journal)",
           note=("CBU rules v1 (SETUPS_PREREG_R3_CBU_V1.md): the owner's CBU written as rules from his own journal. "
                 "Long only, 1-minute bars: above the 5- and 30-minute 200 EMA and yesterday's high, a big green "
                 "candle on 1.5x volume closes at a new high of the day; stop one tick under it, breakeven at 1R. "
                 "Micro cost, 1 MNQ. 1 of 16 triage cells passes: NQ any-base, 09:30-10:59, ride - 1,320 trades, "
                 "PF 1.59, net/DD 10.6, 6 of 8 slices, stress PF 1.53, 6 of 7 neighbours. NOISE OVERLAP, said out "
                 "loud: 84 percent of its trades are on NOISE #382 days, 97 percent the same direction, and it "
                 "loses on NOISE-flat days. Lockbox 9 months (2025-07-07 to 2026-04-06), so no journal trade "
                 "sits in it."))


def main():
    if "--dry" in sys.argv:
        for k, v in JOB.items():
            print("%-16s %s" % (k, v))
        return
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
    print("queue depth", len(live))
    if len(live) > 9:
        sys.exit("ABORT queue too deep")
    if any(j.get("strategy") == STRAT and j.get("instrument") == "NQ" for j in live):
        sys.exit("ABORT CBU-Q 2.0 on NQ already queued/running")
    job = dict(JOB, createdAt=datetime.datetime.now(datetime.timezone.utc))
    ref = u.collection("backtests").document()
    _retry(lambda: ref.set(job))
    print("queued", ref.id, job["strategy"], "on", job["instrument"])


if __name__ == "__main__":
    main()
