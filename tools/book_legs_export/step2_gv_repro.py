import sys, time, json
sys.path.insert(0, r"C:\Users\xride\AppData\Local\Temp\claude\C--Users-xride-OneDrive-Desktop\cf70e01e-1bab-4445-b5e2-10d6db1f8d89\scratchpad\book_legs_ml")
from common import load_run, get_arrays, raw_trades, check_block
from augur_engine.ml_gate import gate_validate

TARGETS = {314: "tree", 335: "rf"}

for rid, model in TARGETS.items():
    t0 = time.time()
    d = load_run(rid)
    arr, _ = get_arrays(d)
    T, res = raw_trades(d, arr)
    T3 = [(t[0], t[1], t[2]) for t in T]
    gv = d["gate_validate"]
    wf0, wf1 = gv["wf_range"]
    lb0 = gv["lockbox_from"]
    gvr = gate_validate(arr, T3, gates=tuple(gv["gates"]), thresholds=tuple(gv["thresholds"]),
                        lockbox_months=int(gv["lockbox_months"]), min_kept=int(gv["min_kept"]),
                        min_keep_frac=float(gv["min_keep_frac"]), windows=int(gv["windows"]),
                        wf_from=wf0, wf_to=wf1, seed=42, lb_from=lb0, keel=False)
    print(f"=== #{rid} {d['strategy']} ({time.time()-t0:.1f}s)")
    print("  chosen repro:", gvr["chosen"])
    print("  chosen stored:", gv["chosen"])
    # find hybrid rows
    hr = next((h for h in gvr["hybrids"] if h["model"] == model), None)
    hs = next((h for h in gv["hybrids"] if h["model"] == model), None)
    if hr is None or hs is None:
        print(f"  hybrid {model}: MISSING repro={hr is not None} stored={hs is not None}")
        continue
    for blk in ("pre", "wf_rng", "lockbox", "full"):
        ok, msg = check_block(f"hybrid[{model}].{blk}", hr[blk], hs[blk])
        print(("  OK  " if ok else "  FAIL"), msg)
    with open(rf"C:\Users\xride\AppData\Local\Temp\claude\C--Users-xride-OneDrive-Desktop\cf70e01e-1bab-4445-b5e2-10d6db1f8d89\scratchpad\book_legs_ml\gvr_{rid}.json", "w") as fh:
        json.dump(gvr, fh, default=str, indent=1)
