"""VALIDATE-GAP AUDIT (2026-09-15, owner: "has anything else not been auto validated that may need to be").

Reads every run document by id (batched get_all, not a collection stream - Firestore quota), groups by strategy
file, and lists:
  A. strategy files in augur_strategies that have NEVER had an Auto-Validate run;
  B. of those, the ones with any non-validate run (search / gate / single) showing a real result;
  C. files whose ONLY validates are FAIL/WEAK but whose best search beat their validate materially.
Writes tools/r16_results/validate_gap_audit.csv. Read-only.
"""
import os, sys, csv, re, glob
os.chdir(r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG")
import firebase_admin
from firebase_admin import credentials, firestore
if not firebase_admin._apps:
    firebase_admin.initialize_app(credentials.Certificate("serviceAccount.json"))
db = firestore.client()
u = db.collection("users").document("IO0K35JpLIcH9YK4C0pMNYUzZOM2")


def c(s): return "".join(ch for ch in str(s) if ord(ch) < 128)


MAXID = int(sys.argv[1]) if len(sys.argv) > 1 else 420
rows = []
for lo in range(1, MAXID + 1, 100):
    refs = [u.collection("runs").document(str(i)) for i in range(lo, min(lo + 100, MAXID + 1))]
    for d in db.get_all(refs, field_paths=["strategy", "scope", "famKey", "instrument", "timeframe", "best_pnl_usd",
                                           "best_dd_usd", "best_pf", "best_trades", "date_from", "date_to",
                                           "validate.verdict", "validate.lockbox", "multiplier", "cost_pts"]):
        if not d.exists:
            continue
        y = d.to_dict() or {}
        v = y.get("validate") or {}
        lb = v.get("lockbox") or {}
        rows.append(dict(id=int(d.id), strat=c(y.get("strategy") or ""), scope=c(y.get("scope") or "").strip(),
                         fam=y.get("famKey") or "", inst=y.get("instrument") or "", tf=y.get("timeframe") or "",
                         verdict=v.get("verdict") or "", net=round(y.get("best_pnl_usd") or 0),
                         dd=round(abs(y.get("best_dd_usd") or 0)), pf=round(y.get("best_pf") or 0, 3),
                         trd=y.get("best_trades") or 0, lbpnl=round(lb.get("pnl") or 0), lbpf=round(lb.get("pf") or 0, 2),
                         lbn=lb.get("trades"), mult=y.get("multiplier"), cost=y.get("cost_pts"),
                         dfrom=y.get("date_from"), dto=y.get("date_to")))
print("runs read:", len(rows), "ids", min(r["id"] for r in rows), "-", max(r["id"] for r in rows))
os.makedirs("tools/r16_results", exist_ok=True)
with open("tools/r16_results/validate_gap_all_runs.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); [w.writerow(r) for r in rows]

files = sorted(os.path.basename(p) for p in glob.glob("augur_strategies/*.py") if not os.path.basename(p).startswith("_"))
by = {}
for r in rows:
    by.setdefault(r["strat"], []).append(r)
scopes = {}
for r in rows:
    scopes[r["scope"]] = scopes.get(r["scope"], 0) + 1
print("scopes:", scopes)


def is_val(r): return r["scope"].lower().startswith("auto-valid") or bool(r["verdict"])


out = []
for fn in files:
    rs = by.get(fn, [])
    vals = [r for r in rs if is_val(r)]
    other = [r for r in rs if not is_val(r) and not r["strat"].startswith("BOOK")]
    best_other = max(other, key=lambda r: (r["pf"] if r["trd"] >= 100 else 0), default=None)
    out.append(dict(file=fn, n_runs=len(rs), n_validates=len(vals),
                    verdicts="/".join(sorted({r["verdict"] or "?" for r in vals})),
                    best_val_id=(max(vals, key=lambda r: r["net"])["id"] if vals else ""),
                    other_runs=len(other),
                    best_other_id=best_other["id"] if best_other else "",
                    best_other_scope=best_other["scope"] if best_other else "",
                    best_other_pf=best_other["pf"] if best_other else "",
                    best_other_trd=best_other["trd"] if best_other else "",
                    best_other_net=best_other["net"] if best_other else "",
                    best_other_ndd=(round(best_other["net"] / best_other["dd"], 2) if best_other and best_other["dd"] else "")))
with open("tools/r16_results/validate_gap_audit.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(out[0].keys())); w.writeheader(); [w.writerow(r) for r in out]

never = [o for o in out if o["n_validates"] == 0]
print(f"\nstrategy files: {len(files)}   never auto-validated: {len(never)}")
print("\nNEVER VALIDATED BUT HAS OTHER RUNS (best non-validate run by PF, >=100 trades):")
for o in sorted(never, key=lambda o: -(o["best_other_pf"] or 0)):
    if o["other_runs"]:
        print(f"  {o['file']:34} runs {o['other_runs']:3}  best #{o['best_other_id']} {o['best_other_scope'][:14]:14} "
              f"PF {o['best_other_pf']}  trades {o['best_other_trd']}  net {o['best_other_net']}  n/DD {o['best_other_ndd']}")
print("\nNEVER VALIDATED AND NEVER RUN AT ALL:")
print("  " + ", ".join(o["file"] for o in never if not o["other_runs"]))
