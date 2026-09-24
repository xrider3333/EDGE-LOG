# Moved from a session scratchpad 2026-09-24 (ROC frontier hunt); results in RESEARCH_LEDGER.md rows 1.15 / 2.12-2.19.
import json, os, datetime
import firebase_admin
from firebase_admin import credentials, firestore
from google.cloud.firestore_v1.base_query import FieldFilter
ROOT = r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"
CACHE = os.environ.get("EDGELOG_ROCFRONTIER", r"C:\EdgeLog\_anatomy_cache\rocfrontier")
firebase_admin.initialize_app(credentials.Certificate(os.path.join(ROOT, "serviceAccount.json")))
u = firestore.client().collection("users").document("IO0K35JpLIcH9YK4C0pMNYUzZOM2")
out = {}
for rid in (396, 397, 372, 366, 379):
    for d in u.collection("runs").where(filter=FieldFilter("id", "==", rid)).select(["id", "strategy", "book"]).stream():
        r = d.to_dict()
        b = r.get("book") or {}
        for L in b.get("legs") or []:
            L.pop("equity", None); L.pop("daily", None)
        out[rid] = r
json.dump(out, open(os.path.join(CACHE, "books.json"), "w"), default=str)
def y(a, b): return (datetime.date.fromisoformat(b[:10]) - datetime.date.fromisoformat(a[:10])).days / 365.25
for rid, r in sorted(out.items()):
    b = r["book"]
    lf, a, e = b.get("lockbox_from"), b.get("date_from"), b.get("date_to")
    print("\n#%s %s" % (rid, r["strategy"][:80]))
    for k, (s, t) in (("pre_lockbox", (a, lf)), ("lockbox", (lf, e)), ("whole", (a, e))):
        blk = b.get(k) or {}
        yy = y(s, t)
        net, dd = blk.get("total_pnl", 0), abs(blk.get("max_drawdown", 0))
        print("  %-11s %s..%s %5.2fy  n=%6d net $%10.0f  DD $%7.0f  PF %.3f  ROC/yr %6.1f%%  MAR %.2f" % (
            k, s, t, yy, blk.get("num_trades", 0), net, dd, blk.get("profit_factor", 0), 100 * net / yy / 1e5, (net / yy) / dd if dd else 0))
    for L in b.get("legs") or []:
        print("     leg %-28s %s %s w=%s mult=%s cost=%s net $%.0f n=%s" % (L.get("strategy"), L.get("instrument"), L.get("timeframe"), L.get("weight"), L.get("mult"), L.get("cost_pts"), L.get("net") or 0, L.get("trades")))
