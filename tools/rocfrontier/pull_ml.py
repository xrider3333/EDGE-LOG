# Moved from a session scratchpad 2026-09-24 (ROC frontier hunt); results in RESEARCH_LEDGER.md rows 1.15 / 2.12-2.19.
# One Firestore read of every run's ML rows (tilts / keel / hybrids), equity curves dropped.
import json, os
import firebase_admin
from firebase_admin import credentials, firestore
ROOT = r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"
CACHE = os.environ.get("EDGELOG_ROCFRONTIER", r"C:\EdgeLog\_anatomy_cache\rocfrontier")
OUT = os.path.join(CACHE, "runs_ml.json")
firebase_admin.initialize_app(credentials.Certificate(os.path.join(ROOT, "serviceAccount.json")))
u = firestore.client().collection("users").document("IO0K35JpLIcH9YK4C0pMNYUzZOM2")
F = ["id", "strategy", "famKey", "famSeq", "multiplier", "date_to",
     "gate_validate.hybrids", "gate_validate.tilts", "gate_validate.keel", "gate_validate.chosen",
     "gate_validate.ungated_wf", "gate_validate.ungated_lockbox", "gate_validate.ungated_pre",
     "gate_validate.wf_range", "gate_validate.lockbox_from", "gate_validate.span", "validate.verdict"]
out = []
for d in u.collection("runs").select(F).stream():
    r = d.to_dict() or {}
    gv = r.get("gate_validate") or {}
    for row in (gv.get("hybrids") or []) + (gv.get("tilts") or []) + [gv.get("keel") or {}]:
        if isinstance(row, dict):
            row.pop("equity", None)
            for k in list(row.keys()):
                if isinstance(row[k], dict):
                    row[k].pop("equity", None)
    out.append(r)
json.dump(out, open(OUT, "w"), default=str)
print(len(out), "runs ->", OUT, os.path.getsize(OUT) // 1024, "KB")
