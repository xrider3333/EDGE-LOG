"""Queue WEBULL_PAPER_TODO item 6, step 1: the ML filter bake-off (GATE VALIDATE) on NOISE crown #304.

Owner 2026-09-21: "yes plan the ML for webull, start with NOISE", then "go, run it as a twin beside
NOISE". No ML filter has ever been tested on #304 - the PC's live NOISE filters for NinjaTrader sit on
retired configs (#225 tree, #231 rf, #243 et) - so this is the pass/fail test that decides whether a
NOISE-ML twin gets built for the Webull book at all.

PINNED TO RUN #304. The settings are read off run #304's own document at queue time and asserted
against the values below, so a changed doc stops the queue instead of silently testing something
else: NOISE_1_1_NBHD.py, NQ 5m RTH no-adjust master (db_noadj_rth), 2010-06-07..2026-08-12,
0.533 points a round trip, x20, and #304's own 15 parameters.

THE SEARCH is the owner's standing gate grid (edgelog-gate-floor-rule, 2026-08-03): five model types
(logistic, rf, xgb, tree, et) x cut-offs 45/50/55/60, causal features, candidates ranked on the
pre-held-out data by net dollars among those within 80% of the best MAR, one look at the held-out
stretch for the winner only. The runner's own defaults are narrower (3 models x 50/55/60), so both
lists are passed explicitly. Held-out stretch = the engine default 12 months (the 36-month proposal
in RESEARCH.md item 9 is not adopted yet).

PRE-REGISTERED PASS (WEBULL_PAPER_TODO item 6, written before the result): the chosen filter makes
MORE money than raw #304 on BOTH the walk-forward stretch and the held-out stretch - a resizing
(hybrid) line judged at equal drawdown, so leverage cannot fake a win. Less money with a smaller
drawdown is a "drawdown dial": reported, not adopted.

    python tools/queue_noise304_gate_validate.py            # dry run: prints the job, queues nothing
    python tools/queue_noise304_gate_validate.py --queue    # queues it on the PC runner
"""
import datetime
import json
import os
import sys
import time

os.chdir(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import firebase_admin  # noqa: E402
from firebase_admin import credentials, firestore  # noqa: E402
from google.api_core import exceptions as _gx  # noqa: E402

UID = "IO0K35JpLIcH9YK4C0pMNYUzZOM2"
RUN = "304"
EXPECT = {"strategy": "NOISE_1_1_NBHD.py", "instrument": "NQ", "timeframe": "5m",
          "data_source": "db_noadj_rth", "date_from": "2010-06-07", "date_to": "2026-08-12",
          "cost_pts": 0.533, "multiplier": 20.0}
GATES = ["logistic", "rf", "xgb", "tree", "et"]
THRESHOLDS = [0.45, 0.50, 0.55, 0.60]
LOCKBOX_MONTHS = 12


def _retry(fn, tries=4, wait=300):
    for i in range(tries):
        try:
            return fn()
        except (_gx.ResourceExhausted, _gx.ServiceUnavailable, _gx.DeadlineExceeded) as e:
            print("attempt %d blocked (%s); waiting %ds" % (i + 1, type(e).__name__, wait), flush=True)
            if i == tries - 1:
                raise
            time.sleep(wait)


def main():
    if not firebase_admin._apps:
        firebase_admin.initialize_app(credentials.Certificate("serviceAccount.json"))
    u = firestore.client().collection("users").document(UID)
    fields = list(EXPECT) + ["best_params", "commission_usd", "slippage_pts"]
    run = _retry(lambda: u.collection("runs").document(RUN).get(field_paths=fields)).to_dict() or {}
    bad = {k: (run.get(k), v) for k, v in EXPECT.items() if run.get(k) != v}
    if bad:
        sys.exit(f"ABORT run #{RUN} no longer carries the settings this test is pinned to: {bad}")
    params = run.get("best_params") or {}
    if len(params) != 15:
        sys.exit(f"ABORT run #{RUN} best_params has {len(params)} keys, expected 15: {sorted(params)}")

    live = _retry(lambda: [(d.id, d.to_dict() or {}) for d in u.collection("backtests")
                           .where("status", "in", ["queued", "running", "paused"]).stream()])
    print("queue depth", len(live), [f"{j.get('type')}:{str(j.get('strategy'))[:24]}:{j.get('status')}"
                                     for _i, j in live])
    if any(j.get("type") == "gate_validate" and j.get("strategy") == EXPECT["strategy"] for _i, j in live):
        sys.exit("ABORT a gate bake-off on NOISE_1_1_NBHD.py is already queued or running")

    job = dict(type="gate_validate", status="queued", strategy=EXPECT["strategy"],
               instrument=EXPECT["instrument"], timeframe=EXPECT["timeframe"], session="rth",
               source=EXPECT["data_source"], cost_pts=EXPECT["cost_pts"], mult=EXPECT["multiplier"],
               commission_usd=run.get("commission_usd"), slippage_pts=run.get("slippage_pts"),
               date_from=EXPECT["date_from"], date_to=EXPECT["date_to"], params=params,
               gates=GATES, thresholds=THRESHOLDS, lockbox_months=LOCKBOX_MONTHS, progress=0,
               preset="NOISE #304 ML filter bake-off - Webull to-do item 6 step 1",
               note=("WEBULL_PAPER_TODO item 6, step 1 (owner 2026-09-21: go, run it as a twin beside "
                     "NOISE). First ML filter ever tested on NOISE crown #304, pinned to run #304's own "
                     "window, master, cost and 15 parameters. Five model types x cut-offs 45/50/55/60, "
                     "causal features, 12-month held-out stretch. PRE-REGISTERED PASS: the chosen filter "
                     "makes MORE money than raw #304 on BOTH the walk-forward and the held-out stretch "
                     "(a resizing hybrid judged at equal drawdown); less money with a smaller drawdown is "
                     "a drawdown dial, reported and not adopted. A pass leads to a NOISE-ML twin beside "
                     "raw NOISE on the Webull book; a fail stops NOISE there."))
    print(json.dumps({k: v for k, v in job.items() if k != "note"}, indent=1, default=str))
    if "--queue" not in sys.argv:
        print("dry run - nothing queued (pass --queue)")
        return
    job["createdAt"] = datetime.datetime.now(datetime.timezone.utc)
    ref = u.collection("backtests").document()
    _retry(lambda: ref.set(job))
    print("queued", ref.id, job["strategy"], "gate bake-off")


if __name__ == "__main__":
    main()
