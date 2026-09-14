"""
BOOK ROUND 55 - every VALIDATED alternative, one slot at a time, on top of run #379 (2026-09-14).

(Named book55 so it does not collide with the NOISE family's own round 55 tools.)

Rounds 51-54 swapped each book slot to its family CROWN and gained 16 percent. Since then other sessions
have validated a batch of new alternatives that are not crowns but did PASS:

    NOISE slot    #394 crown waits two closes     PASS, overfit probability 0.063, crowned its own centre
                  #382 30-minute compression tilt  PASS
                  #387 hourly squeeze FILTER        PASS (the round-56 scorecard's top config, PF 2.35)
                  #386 hourly filter on #243        PASS
                  #388 crown settings on 15-minute  PASS (but crowned a worse neighbour)
    ENGU-Q slot   #380 the R4 file                  PASS, 2.6x the crown's trade rate
    ORB slot      #297 the F7580 filters            PASS (another session's book #375 used it: 41.12)

Each fenced file is run at its DEFAULTS, which is the centre configuration the owning session
parity-checked to the dollar - not at whatever neighbour its validate happened to crown.

PRE-REGISTERED, BEFORE RUNNING: this is about ten comparisons against one baseline, so a winner must
beat #379 by at least FIVE percent on selection-window net-over-drawdown AND hold the held-back year at
or above #379's, or it is recorded as noise. Weights other than 1 are KNOB TESTS and labelled as such.
The book window stays 2010-06-07 to 2026-06-30 so every number compares to #379.

Daily profits pooled by exit day and SORTED before any running total; each book's drawdown asserted
against the sum of its parts'. These numbers compare to EACH OTHER; the app scores any winner.
"""
import os, sys, csv
import numpy as np, pandas as pd
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT); sys.path.insert(0, os.path.join(ROOT, "tools")); os.chdir(ROOT)
import importlib.util as ilu
from augur_engine.engine import run_backtest
from augur_engine.data import find_master, load_master_arrays
try:
    from research_beacon import beacon
except Exception:                                   # the beacon is a courtesy, never a blocker
    from contextlib import contextmanager

    @contextmanager
    def beacon(*a, **k):
        class _B:
            def step(self, *a, **k): pass
        yield _B()

WIN = dict(date_from="2010-06-07", date_to="2026-06-30")
LB0 = pd.Timestamp("2025-06-30")
NOISE_CROWN = {"daytype_lo": 0.2, "window": "all_day", "confirm_bars": 1, "daytype_mode": "skip_bot_short",
               "band_mult_long": 0.75, "vol_skip_pct": 95.0, "band_mult_short": 1.5, "skip_holidays": False,
               "stop_mode": "bandwidth", "flat_eod": True, "lookback": 40, "side": "Both",
               "daytype_hi": 0.8, "stop_k": 1.75, "exit_mode": "vwap"}


def defaults(fn):
    sp = ilu.spec_from_file_location("m", fn); m = ilu.module_from_spec(sp); sp.loader.exec_module(m)
    return {k: v["default"] for k, v in m.DEFAULT_PARAMS.items()}


CACHE = {}


def daily(spec):
    fn, inst, tf, sess, cost, mult, params = spec
    key = (fn, tf, cost, repr(params))
    if key not in CACHE:
        src = "db_noadj_rth" if sess == "rth" else "db_noadj_eth"
        A = load_master_arrays(find_master(inst, tf, sess, src), **WIN)
        idx = pd.DatetimeIndex(A["index"])
        r = run_backtest(fn, arrays=A, params=(params if params is not None else defaults(fn)),
                         cost_pts=cost, return_trades=True)
        s = pd.Series([t[2] * mult for t in r["trades"]],
                      index=[idx[t[1]].tz_localize(None).normalize() for t in r["trades"]])
        CACHE[key] = s.groupby(level=0).sum().sort_index()
        CACHE[key].attrs["n"] = len(r["trades"])
        print(f"    leg {os.path.basename(fn):26} {tf:3} trades={len(r['trades']):5} net=${CACHE[key].sum():>10,.0f}",
              flush=True)
    return CACHE[key]


def dd_of(s):
    s = s.sort_index()
    assert s.index.is_monotonic_increasing, "pooled daily index is not in calendar order"
    cum = s.cumsum()
    return float((cum - cum.cummax()).min())


S = "augur_strategies/"
ORB314 = (S + "ORB_3_6_R6.py", "NQ", "5m", "rth", 0.533, 20.0, None)
ORB234 = (S + "ORB_3_6_C2.py", "NQ", "5m", "rth", 0.533, 20.0, None)
ORB297 = (S + "ORB_3_6_F7580.py", "NQ", "5m", "rth", 0.533, 20.0, None)
ENGUQ_R2 = (S + "ENGUQ_1M_ETH_R2_1_0.py", "NQ", "1m", "eth", 0.783, 20.0, None)
ENGUQ_R4 = (S + "ENGUQ_1M_ETH_R4_1_0.py", "NQ", "1m", "eth", 0.783, 20.0, None)
TTM = (S + "TTMSQZ_3_0_ES30SSOF2.py", "ES", "30m", "rth", 0.363, 50.0, None)
N_RAW = (S + "NOISE_1_1_NBHD.py", "NQ", "5m", "rth", 0.533, 20.0, NOISE_CROWN)
N_C2 = (S + "NOISE_1_1_N304C2.py", "NQ", "5m", "rth", 0.533, 20.0, None)
N_CT = (S + "NOISE_1_8_CT304.py", "NQ", "5m", "rth", 0.533, 20.0, None)
N_HSQ = (S + "NOISE_1_9_HSQ304.py", "NQ", "5m", "rth", 0.533, 20.0, None)
N_HSQ243 = (S + "NOISE_1_9_HSQ243.py", "NQ", "5m", "rth", 0.533, 20.0, None)
N_15 = (S + "NOISE_1_1_N304.py", "NQ", "15m", "rth", 0.533, 20.0, None)

ROWS = []
BASE = {}


def score(label, legs, kind):
    parts = [daily(spec) * w for spec, w in legs]
    s = pd.concat(parts, axis=1).sort_index().fillna(0).sum(axis=1)
    bound = sum(-dd_of(p) for p in parts)
    out = {"book": label, "kind": kind}
    line = []
    for stage, sel in (("pre", s.index < LB0), ("lb", s.index >= LB0), ("whole", s.index == s.index)):
        z = s[sel]; net = float(z.sum()); dd = -dd_of(z)
        pos = z[z > 0].sum(); neg = -z[z < 0].sum()
        srt = np.array(sorted(z.values, reverse=True))
        out[stage + "_net"] = round(net); out[stage + "_dd"] = round(dd)
        out[stage + "_mar"] = round(net / dd, 2) if dd > 0 else 99
        out[stage + "_pf"] = round(pos / neg, 3) if neg else 99
        out[stage + "_top10"] = round(100 * float(srt[:10].sum()) / net) if net > 0 else 999
        line.append(f"{stage} ${net:>10,.0f}/DD${dd:>7,.0f}={net/dd if dd else 99:6.2f}")
    assert -dd_of(s) <= bound + 1
    if not BASE:
        BASE.update(out)
    out["sel_vs_379_pct"] = round(100 * (out["pre_mar"] / BASE["pre_mar"] - 1), 1)
    out["lb_vs_379_pct"] = round(100 * (out["lb_mar"] / BASE["lb_mar"] - 1), 1)
    clears = out["sel_vs_379_pct"] >= 5.0 and out["lb_mar"] >= BASE["lb_mar"]
    out["clears_bar"] = bool(clears) and kind == "swap"
    ROWS.append(out)
    flag = "  <<< CLEARS" if out["clears_bar"] else ""
    print(f"  {label:44} " + " | ".join(line) +
          f"  PF {out['whole_pf']:.3f}  sel {out['sel_vs_379_pct']:+5.1f}%  lb {out['lb_vs_379_pct']:+5.1f}%"
          f"  lbTop10 {out['lb_top10']}%{flag}", flush=True)


def book(orb=ORB314, enguq=ENGUQ_R2, ttm_w=3.0, noise=((N_RAW, 1.0),)):
    return [(orb, 1.0), (enguq, 1.0), (TTM, ttm_w)] + list(noise)


if __name__ == "__main__":
    PLAN = [
        ("RUN #379 baseline (all four crowns)", book(), "base"),
        ("ORB slot: #234 control", book(orb=ORB234), "swap"),
        ("ORB slot: #297 F7580 filters", book(orb=ORB297), "swap"),
        ("ENGU-Q slot: R4 file (#380)", book(enguq=ENGUQ_R4), "swap"),
        ("NOISE slot: waits two closes (#394)", book(noise=((N_C2, 1.0),)), "swap"),
        ("NOISE slot: 30-min compression tilt (#382)", book(noise=((N_CT, 1.0),)), "swap"),
        ("NOISE slot: hourly squeeze filter (#387)", book(noise=((N_HSQ, 1.0),)), "swap"),
        ("NOISE slot: hourly filter on #243 (#386)", book(noise=((N_HSQ243, 1.0),)), "swap"),
        ("NOISE slot: crown settings on 15m (#388)", book(noise=((N_15, 1.0),)), "swap"),
        ("KNOB: hourly filter at weight 2", book(noise=((N_HSQ, 2.0),)), "knob"),
        ("KNOB: hourly filter at weight 3", book(noise=((N_HSQ, 3.0),)), "knob"),
        ("TILT: raw NOISE + hourly filter on top", book(noise=((N_RAW, 1.0), (N_HSQ, 1.0))), "tilt"),
        ("TILT: raw NOISE + 30-min tilt file on top", book(noise=((N_RAW, 1.0), (N_CT, 1.0))), "tilt"),
    ]
    print("building legs and scoring\n")
    with beacon("BOOK round 55 - validated alternatives per slot", total=len(PLAN)) as b:
        for i, (label, legs, kind) in enumerate(PLAN, 1):
            score(label, legs, kind)
            b.step(i)
    print("\ncorrelation of each NOISE alternative with the raw crown, daily, zeros filled:")
    raw = daily(N_RAW).rename("raw")
    for nm, spec in (("waits2", N_C2), ("ct30", N_CT), ("hourlySQ", N_HSQ), ("hsq243", N_HSQ243), ("15m", N_15)):
        c = pd.concat([raw, daily(spec).rename(nm)], axis=1).sort_index().fillna(0)
        print(f"    {nm:9} corr {c.raw.corr(c[nm]):.3f}   trades {daily(spec).attrs['n']}")
    c = pd.concat([daily(ENGUQ_R2).rename("r2"), daily(ENGUQ_R4).rename("r4")], axis=1).sort_index().fillna(0)
    print(f"    ENGU-Q R2 vs R4 corr {c.r2.corr(c.r4):.3f}")
    os.makedirs("tools/r16_results", exist_ok=True)
    with open("tools/r16_results/book55_slot_audit.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(ROWS[0].keys())); w.writeheader()
        for r in ROWS: w.writerow(r)
    print("\nsaved tools/r16_results/book55_slot_audit.csv")
