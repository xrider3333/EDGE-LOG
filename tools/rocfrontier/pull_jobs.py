# Moved from a session scratchpad 2026-09-24 (ROC frontier hunt); results in RESEARCH_LEDGER.md rows 1.15 / 2.12-2.19.
import json, os
import firebase_admin
from firebase_admin import credentials, firestore
from google.cloud.firestore_v1.base_query import FieldFilter
ROOT = r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"
CACHE = os.environ.get("EDGELOG_ROCFRONTIER", r"C:\EdgeLog\_anatomy_cache\rocfrontier")
firebase_admin.initialize_app(credentials.Certificate(os.path.join(ROOT, "serviceAccount.json")))
u = firestore.client().collection("users").document("IO0K35JpLIcH9YK4C0pMNYUzZOM2")
out = {}
for rid in (396, 397, 372):
    for d in u.collection("backtests").where(filter=FieldFilter("run_id", "==", rid)).stream():
        j = d.to_dict() or {}
        j.pop("result", None)
        out[rid] = j
        print(rid, d.id, j.get("strategy"), j.get("date_from"), j.get("date_to"), j.get("lockbox_months"))
        for L in j.get("legs") or []:
            print("   ", L.get("strategy"), L.get("instrument"), L.get("timeframe"), L.get("weight"), L.get("cost_pts"), "params:", json.dumps(L.get("params"))[:300])
json.dump(out, open(os.path.join(CACHE, "book_jobs.json"), "w"), default=str)
