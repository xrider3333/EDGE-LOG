# Round 4 (2026-09-28): BOOK #463's daily P&L per leg, at close and valued daily, exactly as the frontier lane
# scores it (C:\EdgeLog\_anatomy_cache\adopt449\ttm458_eval.py, evalb). Saves the series so candidate legs can be
# added without re-running the engine.
import json, os, sys
REPO = r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"; sys.path.insert(0, REPO); os.chdir(REPO)
os.environ.setdefault("AUGUR_TRIAL_CACHE", "1")
import numpy as np, pandas as pd
import firebase_admin
from firebase_admin import credentials, firestore
from augur_engine import book

OUT = os.environ.get("EDGELOG_ROCFRONTIER_R4", r"C:\EdgeLog\_anatomy_cache\rocfrontier\r4")   # results stay outside git
if not firebase_admin._apps:
    firebase_admin.initialize_app(credentials.Certificate("serviceAccount.json"))
u = firestore.client().collection("users").document("IO0K35JpLIcH9YK4C0pMNYUzZOM2")
W0, W1 = "2010-06-07", "2026-06-30"
A = [dict(l.get("leg", l)) for l in u.collection("backtests").document("EmzbSsewQJ6TjEaaO4ea").get().to_dict()["legs"]]
json.dump(A, open(os.path.join(OUT, "book463_legs.json"), "w"), indent=1, default=str)
days = pd.bdate_range(W0, W1)
cols, TR = {}, []
for k, l in enumerate(A):
    tr, inf = book._leg_trades(l, W0, W1)
    m = inf.pop("_mtm_day", None) or tr
    for pr, tag in ((tr, "close"), (m, "mtm")):
        d, p = book._daily(pr)
        s = pd.Series(p, index=pd.to_datetime(d)).groupby(level=0).sum()
        days = days.union(s.index)
        cols[f"L{k}_{tag}"] = s
    TR += [(str(pd.Timestamp(d).date()), float(v), l["strategy"]) for d, v in tr]
    print(k, l["strategy"], inf.get("trades"), inf.get("net"), flush=True)
df = pd.DataFrame({c: s.reindex(days).fillna(0.0) for c, s in cols.items()})
df["close"] = df[[c for c in df if c.endswith("_close")]].sum(axis=1)
df["mtm"] = df[[c for c in df if c.endswith("_mtm")]].sum(axis=1)
df.index.name = "date"
df.to_csv(os.path.join(OUT, "book463_daily.csv"))
pd.DataFrame(TR, columns=["date", "pnl", "strategy"]).to_csv(os.path.join(OUT, "book463_trades.csv"), index=False)
print("saved", len(df), "days", flush=True)
