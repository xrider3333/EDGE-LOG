# -*- coding: utf-8 -*-
"""NOISE ROUND 62 - is NOISE #422 + KEEL v12 a sound live configuration?

Owner's pick (via MANAGER, 2026-09-27): make the live Webull NOISE leg #422 + KEEL v12 if it has the best walk-forward
and lockbox P&L. The in-lane question: #422 sizes compressed-hour trades 1.75x (hourly squeeze, length 20, threshold
1.15) and KEEL v12 carries its OWN hourly-squeeze 1.5x on top of its model size, so the same bet is counted twice.
Round 60 found KEEL lowered walk-forward return per drawdown on every squeeze-sized base it was put on.

Measured here, one continuous tape 2010-06-07 .. 2026-09-16 (last Databento bar), cost 0.533, #422's own stretches
(WF 2016-06-30 .. 2025-07-16, LB .. 2026-07-16, fresh tail after):
  #422 alone | #422 + KEEL v12 | #422 + KEEL v12 WITHOUT its squeeze 1.5x (the double count removed)
  - the two KEEL rows at three model seeds, because Custom ML found KEEL's walk-forward edge is seed-sensitive;
  #304 + KEEL v12 and #382 + KEEL v12 (the current live stack) for reference.
Judged on return per dollar of drawdown and Sortino: sizing a base up and down moves money and drawdown together and
leaves both unchanged, so a stack that cannot beat its own base on them is leverage (the exposure-matched control).
Also: how often the two squeezes fire together, and the combined size the live share cap would see.

  python tools/r62_noise_422_keel_doublecount.py  -> tools/r37_results/r62_422_keel_doublecount.txt
"""
import os
import sys

for _v in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS"):
    os.environ.setdefault(_v, "1")
ROOT = os.environ.get("EDGELOG_REPO_ROOT") or r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"
os.environ["EDGELOG_REPO_ROOT"] = ROOT
sys.path.insert(0, ROOT)
os.chdir(ROOT)

import numpy as np                                                     # noqa: E402
import pandas as pd                                                    # noqa: E402

LAST = "2026-09-16"
WF0, LB0, LB1 = (pd.Timestamp(x).date() for x in ("2016-06-30", "2025-07-16", "2026-07-16"))
M, ACCT, COST = 20.0, 100000.0, 0.533
CROWN = dict(lookback=40, band_mult_long=0.75, band_mult_short=1.5, exit_mode="vwap", side="Both",
             window="all_day", flat_eod=True, skip_holidays=False, stop_mode="bandwidth", stop_k=1.75,
             confirm_bars=1, daytype_mode="skip_bot_short", daytype_lo=0.2, daytype_hi=0.8, vol_skip_pct=95.0)
BASES = {"#422": ("NOISE_1_8_CT304H.py", dict(gate_len=20, gate_ratio=1.15, tilt_mult=1.75)),
         "#304": ("NOISE_1_0.py", CROWN),
         "#382": ("NOISE_1_8_CT304.py", dict(gate_tf_min=30, gate_len=16, gate_ratio=1.15, tilt_mult=2.0))}
SEEDS = (None, 11, 23)                     # None = KEEL's own default seed (the one every validate row uses)
JOBS = ([("#422", "v12", s) for s in SEEDS] + [("#422", "v12_nosq", s) for s in SEEDS]
        + [("#304", "v12", None), ("#382", "v12", None)])


def _setup():
    import importlib.util as ilu
    from augur_engine import ml_keel as K
    from augur_engine.data import find_master, load_master_arrays
    from augur_engine.engine import run_backtest
    if "v12_nosq" not in K.CFG:
        K.CFG["v12_nosq"] = dict(K.CFG["v12"], comp=None)      # KEEL v12 exactly, minus its squeeze multiplier
    A = load_master_arrays(find_master("NQ", "5m", "rth", "db_noadj_rth"), date_from="2010-06-07", date_to=LAST)

    def mod(fn):
        sp = ilu.spec_from_file_location(fn[:-3] + "_r62", os.path.join(ROOT, "augur_strategies", fn))
        m = ilu.module_from_spec(sp)
        sp.loader.exec_module(m)
        return m

    def base(name):
        fn, params = BASES[name]
        r = run_backtest(mod(fn), arrays=A, params=params, cost_pts=COST, return_trades=True)
        t = r["trades"]
        s = r.get("trade_sizes")
        s = np.asarray(s, float) if s is not None and len(s) == len(t) else np.ones(len(t))
        o = np.argsort([int(x[0]) for x in t], kind="stable")
        return [t[i] for i in o], s[o]
    return K, A, base


def work(job):
    name, version, seed = job
    K, A, base = _setup()
    t, plug = base(name)
    kw = K.keel_walk(A, t, version=version) if seed is None else K.keel_walk(A, t, version=version, seed=seed)
    E = np.asarray(kw["E"], int)
    assert np.array_equal(E, np.array([int(x[0]) for x in t])), "KEEL walk reordered the trades"
    names = None
    try:
        F, names = K.keel_features(A)
        sq = F[np.clip(E, 0, len(F) - 1), names.index("sq60_on")] > 0
    except Exception:                                           # noqa: BLE001
        sq = np.zeros(len(E), bool)
    return dict(job=job, E=E, P=np.asarray(kw["P"], float), size=np.asarray(kw["size"], float), plug=plug, sq=sq)


def stretch_stats(d, p):
    out = {}
    for nm, a, b in (("WF", WF0, LB0), ("LB", LB0, LB1), ("tail", LB1, None)):
        m = (d >= a) & ((d < b) if b is not None else True)
        q = p[m]
        y = ((pd.Timestamp(b or LAST) - pd.Timestamp(a)).days / 365.25)
        cum = np.cumsum(q)
        dd = float((np.maximum.accumulate(np.concatenate([[0.0], cum]))[1:] - cum).max()) if len(q) else 0.0
        down = np.sqrt(np.mean(np.minimum(q, 0.0) ** 2)) if len(q) else 0.0
        out[nm] = dict(net=float(q.sum()), dd=dd, roc=100 * q.sum() / y / ACCT,
                       mar=(q.sum() / y / dd) if dd > 0 else 0.0,
                       so=(q.mean() / down) * np.sqrt(len(q) / y) if down > 0 else 0.0)
    return out


def show(label, st, size):
    w, l_, t = st["WF"], st["LB"], st["tail"]
    print("%-44s %4.2fx | WF $%8s DD $%6s %5.1f%%/yr MAR %4.2f Sort %4.2f | LB $%7s DD $%6s %5.1f%%/yr MAR %4.2f "
          "Sort %4.2f | tail $%7s" % (label, size, format(int(w["net"]), ","), format(int(w["dd"]), ","), w["roc"],
                                      w["mar"], w["so"], format(int(l_["net"]), ","), format(int(l_["dd"]), ","),
                                      l_["roc"], l_["mar"], l_["so"], format(int(t["net"]), ",")))


if __name__ == "__main__":
    from multiprocessing import Pool
    with Pool(4) as pool:
        res = pool.map(work, JOBS)
    import pandas as _pd
    from augur_engine.data import find_master, load_master_arrays
    A = load_master_arrays(find_master("NQ", "5m", "rth", "db_noadj_rth"), date_from="2010-06-07", date_to=LAST)
    IDX = _pd.DatetimeIndex(A["index"])
    print("tape 2010-06-07 .. %s, cost %.3f; ROC on $%d; KEEL seeds: default, 11, 23\n" % (IDX[-1].date(), COST, ACCT))
    done = set()
    for r in res:
        name, version, seed = r["job"]
        d = np.array([IDX[max(e - 1, 0)].date() for e in r["E"]])
        if name not in done:
            show("%s alone" % name, stretch_stats(d, r["P"] * M), float(r["plug"].mean()))
            done.add(name)
        lab = "%s + KEEL %s%s" % (name, "v12" if version == "v12" else "v12 minus its squeeze",
                                  "" if seed is None else " (seed %d)" % seed)
        show(lab, stretch_stats(d, r["P"] * r["size"] * M), float((r["plug"] * r["size"]).mean()))
        if name == "#422" and version == "v12" and seed is None:
            tilt = r["plug"] > 1.0
            both = tilt & r["sq"]
            comb = r["plug"] * r["size"]
            print("   overlap: #422 tilts %d of %d trades; KEEL's squeeze fires on %d; BOTH on %d (%.0f%% of #422's tilted "
                  "trades). Combined size mean %.2fx, 95th pct %.2fx, max %.2fx; %d trades above 2.5x"
                  % (tilt.sum(), len(tilt), r["sq"].sum(), both.sum(), 100 * both.sum() / max(tilt.sum(), 1),
                     comb.mean(), np.percentile(comb, 95), comb.max(), int((comb > 2.5).sum())))
