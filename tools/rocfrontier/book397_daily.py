"""Moved from a session scratchpad 2026-09-24 (ROC frontier hunt); results in RESEARCH_LEDGER.md rows 1.15 / 2.12-2.19.
Rebuild frontier book leg dailies from the JOB docs (with the legs' real params) via book_parts,
check they reproduce the run's own numbers, save CSV for comparisons."""
import os, sys, json
os.environ.setdefault("AUGUR_TRIAL_CACHE", "1")
ROOT = r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"
sys.path.insert(0, ROOT); sys.path.insert(0, os.path.join(ROOT, "tools"))
os.chdir(ROOT)
import pandas as pd
from book_dd_attribution import book_parts, sum_parts, score
CACHE = os.environ.get("EDGELOG_ROCFRONTIER", r"C:\EdgeLog\_anatomy_cache\rocfrontier")
if __name__ == "__main__":
    J = json.load(open(os.path.join(CACHE, "book_jobs.json")))
    for rid in sys.argv[1:] or ["397"]:
        job = J[rid]
        parts = book_parts(job["legs"], job["date_from"], job["date_to"])
        df = pd.DataFrame(parts).fillna(0.0).sort_index()
        df.to_csv(os.path.join(CACHE, "book%s_legs_daily.csv" % rid))
        tot = df.sum(axis=1)
        pre = tot[tot.index < "2025-06-30"]; lb = tot[tot.index >= "2025-06-30"]
        def dd(s):
            c = s.cumsum(); return float((c.cummax() - c).max())
        print(rid, "pre net %.0f DD %.0f | LB net %.0f DD %.0f | whole %.0f" % (pre.sum(), dd(pre), lb.sum(), dd(lb), tot.sum()))
        print(score(tot, "2025-06-30"))
