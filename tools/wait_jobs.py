"""Wait for a set of runner jobs to finish, then print each run's verdict, stages and held-back read.
Usage: python tools/wait_jobs.py JOBID [JOBID ...]   (polls every 60 s, gives up after 5 hours)"""
import os, sys, time, json
os.chdir(r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG")
import firebase_admin
from firebase_admin import credentials, firestore
if not firebase_admin._apps:
    firebase_admin.initialize_app(credentials.Certificate("serviceAccount.json"))
u = firestore.client().collection("users").document("IO0K35JpLIcH9YK4C0pMNYUzZOM2")
IDS = sys.argv[1:]
t0 = time.time()
while True:
    docs = {j: (u.collection("backtests").document(j).get().to_dict() or {}) for j in IDS}
    st = {j: (d.get("status"), d.get("progress")) for j, d in docs.items()}
    print(time.strftime("%H:%M:%S"), st, flush=True)
    if all(s[0] in ("done", "error", "failed", "cancelled") for s in st.values()) or time.time() - t0 > 5 * 3600:
        break
    time.sleep(60)
for j, d in docs.items():
    rid = d.get("run_id") or d.get("runId")
    print("=" * 100); print(j, d.get("strategy"), d.get("status"), "run", rid, "err", str(d.get("error"))[:300])
    if not rid:
        continue
    y = u.collection("runs").document(str(rid)).get().to_dict() or {}
    v = y.get("validate") or {}
    print("  verdict", v.get("verdict"), "| famKey", y.get("famKey"), y.get("famSeq"))
    print("  first-75%% selection: net %s dd %s pf %s trades %s win %s" % (y.get("best_pnl_usd"), y.get("best_dd_usd"),
          y.get("best_pf"), y.get("best_trades"), y.get("best_win_rate")))
    print("  champion params:", json.dumps(y.get("best_params"), default=str)[:500])
    small = {k: val for k, val in v.items() if not isinstance(val, (list, dict))}
    print("  validate scalars:", json.dumps(small, default=str)[:1500])
    for k in ("lockbox", "wf", "walk_forward", "gates", "pbo", "plateau", "summary", "checks", "stages"):
        if isinstance(v.get(k), dict):
            vv = {a: b for a, b in v[k].items() if not isinstance(b, list)}
            print("  %s:" % k, json.dumps(vv, default=str)[:900])
