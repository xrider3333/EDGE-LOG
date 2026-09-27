"""Round 18c - restate every structural-stop TTM leg after the same-bar gap-stop fix (MANAGER audit
2026-09-27). BEFORE = the shared checkout's files, AFTER = this worktree's (or main once shipped).

The bug: when the open gapped past the setup's stop, the entry-bar stop check booked the exit AT the
stop price, which then sat on the far side of the entry - a profit at a price the bar never traded.
The fix fills at the open (flat at entry, pays the cost), as the file already does on any later bar.

Log: tools/data/ttmsqz_r18c_samebar_stop_fix.txt
"""
import os, sys, importlib.util
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHARED = r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"
BEFORE_DIR = os.environ.get("BEFORE_DIR", os.path.join(SHARED, "augur_strategies"))
AFTER_DIR = os.path.join(HERE, "augur_strategies")
sys.path.insert(0, SHARED)
from augur_engine.data import find_master, load_master_arrays

COST, MULT, YRS, LB = 0.363, 50.0, 16.06, "2025-07-01"
LEGS = [  # (label, file, params)
    ("#353 / TTM_299_SS", "TTMSQZ_3_0_ES30SS20.py", dict(kc_mult=1.5, eod_cutoff=1)),
    ("#352 / TTM_299_SSL", "TTMSQZ_3_0_ES30SS.py", dict(kc_mult=1.5, eod_cutoff=1, gate_len=16)),
    ("#364 / TTM_299_SSF2", "TTMSQZ_3_0_ES30SSF2.py", dict(kc_mult=1.5, eod_cutoff=1)),
    ("#368 / TTM_299_SSO", "TTMSQZ_3_0_ES30SSO.py", dict(kc_mult=1.5, eod_cutoff=1)),
    ("#369 / TTM_299_SSOF2 (book leg)", "TTMSQZ_3_0_ES30SSOF2.py", dict(kc_mult=1.5, eod_cutoff=1)),
    ("#369 cell guarded / TTM_299_SSOF2R", "TTMSQZ_3_0_ES30SSOF2R.py", dict(kc_mult=1.5, eod_cutoff=1)),
    ("#428 / TTM_299_SSOF2R5", "TTMSQZ_3_0_ES30SSOF2R.py", dict(kc_mult=1.5, eod_cutoff=5)),
    ("#455 staged book leg (3/4/7)", "TTMSQZ_3_0_ES30SSOF2R347.py", dict(kc_mult=1.5, eod_cutoff=5)),
]
ARR = load_master_arrays(find_master("ES", "30m", "rth"), date_from="2010-06-07", date_to="2026-06-30")
IX = pd.DatetimeIndex(ARR["index"])


def load(d, fn, tag):
    sp = importlib.util.spec_from_file_location("%s_%s" % (fn[:-3], tag), os.path.join(d, fn))
    m = importlib.util.module_from_spec(sp); sp.loader.exec_module(m); return m


def score(m, fn, p):
    t = m.run_backtest(ARR["open"], ARR["high"], ARR["low"], ARR["close"], day_id=ARR["day_id"],
                       index=ARR["index"], return_trades=True, **p)["trades"]
    H, L = ARR["high"].astype(float), ARR["low"].astype(float)
    if "SSOF2R" in fn:
        add = (m._guard if hasattr(m, "_guard") else m).roll_offsets(ARR["index"]); H, L = H + add, L + add
    bad = sum(1 for x in t if not (L[int(x[1])] - 1e-9 <= float(x[5]) <= H[int(x[1])] + 1e-9))
    u = np.array([(float(x[2]) - COST) * MULT for x in t])
    cum = np.concatenate([[0], np.cumsum(u)]); dd = -(cum - np.maximum.accumulate(cum)).min()
    xd = IX[[int(x[1]) for x in t]]
    lbm = xd >= pd.Timestamp(LB, tz=xd.tz)
    lb = u[lbm]; lcum = np.concatenate([[0], np.cumsum(lb)]); ldd = -(lcum - np.maximum.accumulate(lcum)).min()
    pf = u[u > 0].sum() / -u[u < 0].sum()
    lpf = lb[lb > 0].sum() / -lb[lb < 0].sum() if (lb < 0).any() else 99.0
    return dict(n=len(u), net=u.sum(), pf=pf, dd=dd, mar=u.sum() / YRS / dd, lbn=int(lbm.sum()),
                lb=lb.sum(), lbpf=lpf, lbdd=ldd, bad=bad)


def main():
    L = ["TTM round 18c - same-bar gap-stop fix, every structural-stop leg restated (pinned window, ES 30m RTH db_noadj_rth)",
         "BEFORE: %s    AFTER: %s" % (BEFORE_DIR, AFTER_DIR), ""]
    H = "  %-36s %-6s %4s %10s %5s %8s %5s  %3s %9s %6s %7s  %s"
    L.append(H % ("leg", "", "n", "net $", "PF", "DD $", "MAR", "LBn", "LB $", "LB PF", "LB DD", "impossible exits"))
    for lab, fn, p in LEGS:
        for tag, d in (("before", BEFORE_DIR), ("after", AFTER_DIR)):
            s = score(load(d, fn, tag), fn, p)
            L.append(H % (lab if tag == "before" else "", tag, s["n"], "{:,.0f}".format(s["net"]), "%.2f" % s["pf"],
                          "{:,.0f}".format(s["dd"]), "%.2f" % s["mar"], s["lbn"], "{:,.0f}".format(s["lb"]),
                          "%.2f" % min(s["lbpf"], 99), "{:,.0f}".format(s["lbdd"]), s["bad"]))
            print(L[-1], flush=True)
    out = os.path.join(HERE, "tools", "data", "ttmsqz_r18c_samebar_stop_fix.txt")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    open(out, "w", encoding="utf-8").write("\n".join(L) + "\n")
    print("log ->", out)


if __name__ == "__main__":
    main()
