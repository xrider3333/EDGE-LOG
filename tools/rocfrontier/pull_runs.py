# Moved from a session scratchpad 2026-09-24 (ROC frontier hunt); results in RESEARCH_LEDGER.md rows 1.15 / 2.12-2.19.
# One Firestore read of every run's walk-forward-test block + lockbox, for the ROC/yr frontier.
import json, os, sys
import firebase_admin
from firebase_admin import credentials, firestore
ROOT = r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"
CACHE = os.environ.get("EDGELOG_ROCFRONTIER", r"C:\EdgeLog\_anatomy_cache\rocfrontier")
OUT = os.path.join(CACHE, "runs_roc.json")
firebase_admin.initialize_app(credentials.Certificate(os.path.join(ROOT, "serviceAccount.json")))
u = firestore.client().collection("users").document("IO0K35JpLIcH9YK4C0pMNYUzZOM2")
F = ["id", "strategy", "famKey", "famSeq", "instrument", "timeframe", "session", "cost_pts", "multiplier",
     "date_from", "date_to", "data_source", "best_params",
     "validate.wf_oos", "validate.verdict", "validate.lockbox", "validate.windows", "validate.pbo",
     "validate.n_pass", "validate.n_gates", "validate.folds_held", "validate.n_folds",
     "gate_validate.ungated_wf", "gate_validate.ungated_lockbox", "gate_validate.ungated_full",
     "gate_validate.ungated_is", "gate_validate.wf_range", "gate_validate.lockbox_from", "gate_validate.span"]
out = []
for d in u.collection("runs").select(F).stream():
    r = d.to_dict() or {}
    r["_doc"] = d.id
    w = ((r.get("validate") or {}).get("wf_oos") or {})
    w.pop("equity", None)
    out.append(r)
json.dump(out, open(OUT, "w"), default=str)
print(len(out), "runs ->", OUT)
