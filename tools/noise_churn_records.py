r"""NOISE churn r1 + r2: re-measure every reported cell with a daily series and write run records (MANAGER #172).

    python tools/noise_churn_records.py          prints each row, writes nothing
    python tools/noise_churn_records.py --write  appends the records (then tools/run_records_sync.py --write)

Same code path as tools/noise_churn_r2.py: pre-WF crown once, the WF chain with fold champions and 2020 splices mapped, the
lockbox crown. Every cost is the same trades re-costed per contract.
"""
import json
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import noise_churn_r1 as R1                                            # noqa: E402
import noise_churn_r2 as R2                                            # noqa: E402
import run_record                                                      # noqa: E402
from augur_engine.data import find_master, load_master_arrays           # noqa: E402

LANE = "NOISE"
ALL = {"HOLD": {}, "cap 1": dict(max_entries=1), "cap 2": dict(max_entries=2), "cap 3": dict(max_entries=3),
       "confirm": dict(reentry_confirm=True), "buf 0.10": dict(vwap_buf_k=0.1), "buf 0.25": dict(vwap_buf_k=0.25),
       "buf 0.50": dict(vwap_buf_k=0.5), **R2.CELLS}
READ = ["HOLD", "cap 1", "cap 2", "confirm", "C3 A+B3"]        # the cells of the WF and lockbox reads
WRITE = "--write" in sys.argv
count = [0]


def emit(stage, name, tr, dates, sess, mult, costs):
    for c in costs:
        d = R2.daily(dates, tr, sess, mult, c)
        note = "churn r1/r2 cell, re-costed per contract, PREREG_noise_churn_r2_2026-11-04"
        strat = "NOISE #382 churn: %s" % name
        rec = run_record.build_record(LANE, "lane", stage, strategy=strat, family="NOISE", instrument="NQ", timeframe="5m",
                                      daily=d, trades=len(tr), cost_pt=c, note=note)
        print("%-6s %-10s cost %.3f tr %5d ROC %7.2f DD5 %7.0f DD%% %6.2f Sort %5.2f" % (stage, name, c, len(tr), rec["roc30k"] or 0, rec["dd5"], rec["ddpct"], rec["sortino"] or 0), flush=True)
        if WRITE:
            run_record.append_record(rec)
        count[0] += 1


def main():
    s = R1.strat(R2.FILE)
    d, A, idx, mult = R1.setup()
    c = R1.crown_of(d)
    sess = pd.Index(sorted(set(idx.normalize())))
    for name, cell in ALL.items():
        tr = R2.sized(s, A, dict(c, **cell))
        emit("preWF", name, tr, [idx[t[0]].normalize() for t in tr], sess, mult, (0.533, 0.783, 1.033, 1.35))

    v, win = d["validate"], d["validate"]["windows"]
    m = find_master(d["instrument"], d.get("timeframe", "5m"), "rth", d["data_source"])
    W = load_master_arrays(m, date_from=d["date_from"], date_to=win["optimize"][1])
    ix = pd.DatetimeIndex(W["index"])
    ix = ix.tz_convert("America/New_York").tz_localize(None) if ix.tz is not None else ix
    rows = sorted([r for r in d["top10_results"] if "fold" in r], key=lambda r: int(r["fold"]))
    keys = list(v["champion"].keys())
    ins = [(pd.Timestamp("2020-02-28"), 60), (pd.Timestamp("2020-06-30"), 69)]

    def shift(b):
        for dd, n in ins:
            if ix[min(b, len(ix) - 1)].normalize() > dd:
                b += n
        return b
    w0, w1 = pd.Timestamp(v["wf_oos"]["from"]), pd.Timestamp(v["wf_oos"]["to"])
    wsess = pd.Index(sorted({x.normalize() for x in ix if w0 <= x.normalize() <= w1}))
    for name in READ:
        tr = []
        for r in rows:
            s0, s1 = shift(int(r["train_bars"])), shift(int(r["train_bars"]) + int(r["test_bars"]))
            sl = {k: (x[s0:s1] if hasattr(x, "__len__") and not isinstance(x, (str, dict)) and len(x) == len(ix) else x) for k, x in W.items()}
            tr += [(t[0] + s0, t[1] + s0, t[2], t[3]) for t in R2.sized(s, sl, dict({k: r[k] for k in keys}, **ALL[name]))]
        emit("WF", name, tr, [ix[t[0] - 1].normalize() for t in tr], wsess, mult, (0.533, 0.783, 1.35))

    B = load_master_arrays(m, date_from=d["date_from"], date_to=win["lockbox"][1])
    bi = pd.DatetimeIndex(B["index"])
    bi = bi.tz_convert("America/New_York").tz_localize(None) if bi.tz is not None else bi
    lo, hi = pd.Timestamp(win["lockbox"][0]), pd.Timestamp(win["lockbox"][1])
    lsess = pd.Index(sorted({x.normalize() for x in bi if lo <= x.normalize() <= hi}))
    for name in READ:
        tr = [t for t in R2.sized(s, B, dict(c, **ALL[name])) if lo <= bi[t[0] - 1].normalize() <= hi]
        emit("LB", name, tr, [bi[t[0] - 1].normalize() for t in tr], lsess, mult, (0.533, 0.783, 1.35))
    print("RECORDS %d %s" % (count[0], "written" if WRITE else "(dry)"))


if __name__ == "__main__":
    main()
