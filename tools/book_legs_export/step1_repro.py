import sys, time
sys.path.insert(0, r"C:\Users\xride\AppData\Local\Temp\claude\C--Users-xride-OneDrive-Desktop\cf70e01e-1bab-4445-b5e2-10d6db1f8d89\scratchpad\book_legs_ml")
from common import load_run, get_arrays, raw_trades, entry_ts_of, slice_stats, check_block

RUNS = [314, 335, 368]

for rid in RUNS:
    t0 = time.time()
    d = load_run(rid)
    arr, m = get_arrays(d)
    T, res = raw_trades(d, arr)
    ts = entry_ts_of(arr, T)
    pnls = [t[2] for t in T]
    gv = d["gate_validate"]
    wf0, wf1 = gv["wf_range"]
    lb0 = gv["lockbox_from"]
    full_s, _ = slice_stats(ts, pnls, None, None)
    pre_s, _ = slice_stats(ts, pnls, None, lb0)
    wf_s, _ = slice_stats(ts, pnls, wf0, lb0)
    lb_s, _ = slice_stats(ts, pnls, lb0, None)
    print(f"=== #{rid} {d['strategy']} {d['instrument']} {d['timeframe']} bars={len(arr['index'])} trades={len(T)} ({time.time()-t0:.1f}s)")
    for nm, r, s in (("full", full_s, gv["ungated_full"]), ("pre", pre_s, gv["ungated_pre"]),
                    ("wf", wf_s, gv["ungated_wf"]), ("lockbox", lb_s, gv["ungated_lockbox"])):
        ok, msg = check_block(nm, r, s)
        print(("  OK  " if ok else "  FAIL"), msg)
