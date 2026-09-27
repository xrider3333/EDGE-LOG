import os, sys, json
os.chdir(r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG")
sys.path.insert(0, os.getcwd())
import firebase_admin
from firebase_admin import credentials, firestore

UID = "IO0K35JpLIcH9YK4C0pMNYUzZOM2"
if not firebase_admin._apps:
    firebase_admin.initialize_app(credentials.Certificate("serviceAccount.json"))
db = firestore.client()
u = db.collection("users").document(UID)

OUT = r"C:\Users\xride\AppData\Local\Temp\claude\C--Users-xride-OneDrive-Desktop\cf70e01e-1bab-4445-b5e2-10d6db1f8d89\scratchpad\book_legs_ml"

for rid in (314, 335, 368):
    snap = u.collection("runs").document(str(rid)).get()
    if not snap.exists:
        print(f"#{rid}: NO RUN DOC")
        continue
    d = snap.to_dict() or {}
    with open(os.path.join(OUT, f"run_{rid}_full.json"), "w", encoding="utf-8") as fh:
        json.dump(d, fh, default=str, indent=2)
    # print a compact summary of top-level keys and key params
    print(f"#{rid}: top-level keys = {sorted(d.keys())}")
    for k in ("strategy_name","strategy","data_source","instrument","timeframe","session",
              "source","date_from","date_to","cost_pts","multiplier","mult","best_params"):
        if k in d:
            print(f"   {k} = {d[k]}")
    gv = ((d.get("validate") or {}).get("gate_validate"))
    print(f"   has validate.gate_validate = {gv is not None}")
    if gv:
        print(f"   gate_validate keys = {sorted(gv.keys())}")
