"""Backfill the KEEL row onto existing run docs (2026-09-06).

Every Auto-Validate that runs from v73.534 on carries `gate_validate.keel` (see
augur_engine/ml_keel.py). Runs validated before that have no row, so the 2C table would stay
empty for the crowns the owner actually looks at until each is re-validated (hours each).
This re-runs a run's CHAMPION over the run's own window and writes ONLY the new key
`gate_validate.keel` - nothing else on the doc is touched.

Reproduction is checked before anything is written: the reproduced ungated pre-lockbox block
must match the doc's own `gate_validate.ungated_pre` (trade count exact, net within 0.5%),
otherwise the run is skipped and reported.

Usage:  python tools/backfill_keel.py 243 234 265 [--write]     (default = dry run)
"""
import os, sys, json, time
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT); sys.path.insert(0, ROOT)
from augur_engine.data import find_master, load_master_arrays      # noqa: E402
from augur_engine.engine import run_backtest                       # noqa: E402
from augur_engine.ml_gate import gate_validate                     # noqa: E402
import augur_engine.data as _data                                  # noqa: E402
if os.environ.get("EDGELOG_UPLOADS"):        # run from a worktree against the shared masters
    _data.UPLOADS = os.environ["EDGELOG_UPLOADS"]

UID = "IO0K35JpLIcH9YK4C0pMNYUzZOM2"
SESSION = {"db_noadj_rth": "rth", "db_noadj_eth": "eth"}


def _db():
    import firebase_admin
    from firebase_admin import credentials, firestore
    if not firebase_admin._apps:
        firebase_admin.initialize_app(credentials.Certificate("serviceAccount.json"))
    return firestore.client()


def one(db, run_id, write):
    ref = db.collection("users").document(UID).collection("runs").document(str(run_id))
    d = ref.get().to_dict()
    if not d:
        print(f"#{run_id}: no doc"); return
    gv = d.get("gate_validate") or {}
    if not gv.get("ungated_pre"):
        print(f"#{run_id}: no gate_validate block on the doc - skip"); return
    if isinstance(gv.get("keel"), dict) and not gv["keel"].get("error"):
        print(f"#{run_id}: already has a keel row ({gv['keel'].get('version')}) - skip"); return
    params = (d.get("validate") or {}).get("champion") or d.get("best_params")
    src = d.get("data_source"); sess = SESSION.get(src)
    if not params or not sess:
        print(f"#{run_id}: missing champion params or unknown data_source {src} - skip"); return
    t0 = time.time()
    arr = load_master_arrays(find_master(d["instrument"], d["timeframe"], sess, src),
                             date_from=d.get("date_from"), date_to=d.get("date_to"))
    res = run_backtest(d["strategy"], arrays=arr, params=params,
                       cost_pts=float(d.get("cost_pts") or 0.0), return_trades=True)
    trades = list(res.get("trades") or [])
    # scoring pass only: no gate models, just the keel row + the ungated blocks
    out = gate_validate(arr, trades, gates=(), thresholds=(), lb_from=gv.get("lockbox_from"),
                        wf_from=(gv.get("wf_range") or [None, None])[0],
                        wf_to=(gv.get("wf_range") or [None, None])[1], keel=True)
    rep, doc_pre = out["ungated_pre"], gv["ungated_pre"]
    n_ok = int(rep["num_trades"]) == int(doc_pre["num_trades"])
    net_ok = abs(rep["total_pnl"] - doc_pre["total_pnl"]) <= 0.005 * max(1.0, abs(doc_pre["total_pnl"]))
    print(f"#{run_id} {d['strategy']} {d['instrument']} {d['timeframe']} {d.get('date_from')}..{d.get('date_to')} "
          f"LB {gv.get('lockbox_from')}: reproduced pre n {rep['num_trades']} vs doc {doc_pre['num_trades']}, "
          f"net {rep['total_pnl']:.1f} vs {doc_pre['total_pnl']:.1f} pts ({time.time()-t0:.0f}s)")
    if not (n_ok and net_ok):
        print(f"#{run_id}: REPRODUCTION MISMATCH - not written"); return
    row = out.get("keel")
    if not isinstance(row, dict) or row.get("error"):
        print(f"#{run_id}: keel row failed: {row}"); return
    m = float(d.get("multiplier") or 1.0)
    print(f"#{run_id}: keel pre ${row['pre']['total_pnl']*m:,.0f} (ungated ${doc_pre['total_pnl']*m:,.0f}) "
          f"DD ${row['pre']['max_drawdown']*m:,.0f} vs ${doc_pre['max_drawdown']*m:,.0f} | "
          f"LB ${row['lockbox']['total_pnl']*m:,.0f} vs ${gv['ungated_lockbox']['total_pnl']*m:,.0f} | "
          f"trust on {row['trust_on']*100:.0f}% avg size {row['avg_size']}")
    if write:
        row = json.loads(json.dumps(row))          # plain json types only
        row["backfilled"] = "2026-09-06 tools/backfill_keel.py"
        ref.update({"gate_validate.keel": row})
        print(f"#{run_id}: WRITTEN gate_validate.keel")
    else:
        print(f"#{run_id}: dry run - not written (pass --write)")


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    write = "--write" in sys.argv
    db = _db()
    for rid in args:
        try:
            one(db, int(rid), write)
        except Exception as e:
            print(f"#{rid}: FAILED {type(e).__name__}: {e}")
