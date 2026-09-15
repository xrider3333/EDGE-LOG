# -*- coding: utf-8 -*-
"""ROUND 57 PROTOCOL AUDIT -- independent recomputation of the items 2-3 clause arithmetic.

Read-only: reads the grid's cached SELECTION trade lists (C:\\EdgeLog\\_anatomy_cache\\r57\\
r57_grid_selection_trades.json), the master bar index/close, and tools/r37_results/r57_grid.json.
Recomputes every S1-S9 input and the section-5 extras WITHOUT measure() / r57_grid.py code, applies
the prereg thresholds under (a) the exact-control reading and (b) the prereg table's rounded
figures, and compares both with what r57_grid.json recorded. Runs no backtest; writes only its
own stdout. Run with cwd = the shared checkout.
"""
import json
import math
import os
import sys

ROOT = r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"
os.chdir(ROOT)
sys.path.insert(0, ROOT)
import numpy as np            # noqa: E402
import pandas as pd           # noqa: E402
from augur_engine.data import find_master, load_master_arrays  # noqa: E402

WT = r"C:\Users\xride\AppData\Local\EdgeLog-worktrees\enguq57"
G = json.load(open(os.path.join(WT, "tools", "r37_results", "r57_grid.json"), encoding="utf-8"))
C = json.load(open(r"C:\EdgeLog\_anatomy_cache\r57\r57_grid_selection_trades.json", encoding="utf-8"))["cells"]
A = load_master_arrays(find_master("NQ", "1m", "eth", "db_noadj_eth"), date_from="2010-06-07", date_to="2026-06-30")
idx = pd.DatetimeIndex(A["index"])
tz = idx.tz
SPLIT = pd.Timestamp("2025-06-30", tz=tz)
E2 = pd.Timestamp("2020-01-01", tz=tz)
n_split = int(idx.searchsorted(SPLIT))

px = pd.Series(np.asarray(A["close"], float), index=idx.tz_localize(None))
px = px[px.index < pd.Timestamp("2025-06-30")]
last = px.resample("YE").last()
bench = ((last / last.shift(1) - 1) * 100).dropna()
bench.index = bench.index.year


def pf(u):
    gl = -u[u < 0].sum()
    return u[u > 0].sum() / gl if gl > 0 else float("nan")


def win(u):
    return 100.0 * (u > 0).mean() if len(u) else float("nan")


def stats(cell):
    tr = C[cell]
    e = np.array([t[0] for t in tr], np.int64)
    x = np.array([t[1] for t in tr], np.int64)
    pts = np.array([t[2] for t in tr], float)
    epx = np.array([t[4] for t in tr], float)
    assert np.all(np.diff(e) > 0) and np.all(e < n_split), cell
    u = pts * 20.0
    ent = idx[e]
    out = dict(e=e, x=x, u=u, epx=epx, ent=ent, n=len(u), win=win(u), pf=pf(u), net=u.sum())
    cum = np.cumsum(pts)
    out["dd"] = float(np.max(np.maximum.accumulate(cum) - cum)) * 20
    yrs = max((SPLIT - ent.min()).days, 1) / 365.25
    out["mar"] = (out["net"] / yrs) / out["dd"]
    m2 = np.asarray(ent >= E2)
    for nm, mk in (("E1", ~m2), ("E2", m2)):
        uu = u[mk]
        s10 = np.sort(uu)[::-1][:10].sum()
        out[nm] = dict(n=int(mk.sum()), net=uu.sum(), pf=pf(uu), win=win(uu), top10=100 * s10 / uu.sum(),
                       ex10=uu.sum() - s10)
    cuts = [None, "2014-01-01", "2018-01-01", "2022-01-01", None]
    for k, nm in enumerate("ABCD"):
        mk = np.ones(len(u), bool)
        if cuts[k]:
            mk &= np.asarray(ent >= pd.Timestamp(cuts[k], tz=tz))
        if cuts[k + 1]:
            mk &= np.asarray(ent < pd.Timestamp(cuts[k + 1], tz=tz))
        out[nm] = dict(n=int(mk.sum()), net=u[mk].sum(), pf=pf(u[mk]), win=win(u[mk]))
    su = np.sort(u)[::-1]
    rem = u.sum() - np.cumsum(su)
    out["ttz"] = int(np.nonzero(rem <= 0)[0][0] + 1)
    k05 = max(1, int(round(0.005 * len(pts))))
    p5 = np.sort(pts)[:-k05]
    w5 = (p5 > 0).mean()
    out["evr_ex05"] = (1 - w5) * (p5[p5 > 0].sum() / -p5[p5 < 0].sum() - 1)
    yr = pd.Series(u, index=ent.year).groupby(level=0).sum()
    common = yr.index.intersection(bench.index)
    out["corr"] = float(yr[common].corr(bench[common]))
    out["ncorr"] = len(common)
    out["y2018"] = float(yr.get(2018, 0.0))
    out["y2022"] = float(yr.get(2022, 0.0))
    hm = np.asarray(ent.hour) * 60 + np.asarray(ent.minute)
    out["x0930_incl"] = (hm >= 570) & (hm <= 575)
    out["x0930_excl"] = (hm >= 570) & (hm < 575)
    return out


S = {c: stats(c) for c in C}
ctl = S["CTRL"]

# ---- 1. raw rows vs r57_grid.json
print("1. RAW ROWS: independent recompute vs r57_grid.json rows (max relative mismatch per cell)")
worst = 0.0
for c, s in S.items():
    R = G["rows"][c]
    pairs = [(s["n"], R["sel"]["n"]), (s["win"], R["sel"]["wr"]), (s["pf"], R["sel"]["pf"]), (s["net"], R["sel"]["net"]),
             (s["dd"], R["sel"]["dd"]), (s["mar"], R["sel"]["mar"]), (s["E1"]["top10"], R["era1"]["top10"]),
             (s["E2"]["top10"], R["era2"]["top10"]), (s["E1"]["ex10"], R["era1"]["ex10"]), (s["E2"]["ex10"], R["era2"]["ex10"]),
             (s["E2"]["pf"], R["era2"]["pf"]), (s["ttz"], R["ttz"]), (s["evr_ex05"], R["evr_ex05"]), (s["corr"], R["corr_sel"]),
             (s["y2018"], R["y2018"]), (s["y2022"], R["y2022"])]
    rel = max(abs(a - b) / max(1.0, abs(b)) for a, b in pairs)
    worst = max(worst, rel)
    print("   %-22s max rel diff %.2e  (corr years %d)" % (c, rel, s["ncorr"]))
print("   worst %.2e" % worst)

# ---- 2. thresholds, two readings
EX = dict(S1=ctl["win"] + 1.0, S2=ctl["pf"] + 0.02, S3=0.95 * ctl["net"], S4=0.95 * ctl["mar"],
          S5a1=ctl["E1"]["top10"] + 2, S5a2=ctl["E2"]["top10"] + 2, S5c=ctl["ttz"] - 2, S5d=ctl["evr_ex05"],
          S7=ctl["corr"] + 0.05, S9pf=ctl["pf"] + 0.01, S9net=0.90 * ctl["net"])
RD = dict(S1=30.4, S2=1.737, S3=498508.0, S4=0.86, S5a1=64.1, S5a2=66.6, S5c=30, S5d=ctl["evr_ex05"], S7=0.549,
          S9pf=1.727, S9net=472271.0)
RD_ABS_S4 = ctl["mar"] - 0.05
print("\n2. THRESHOLDS exact-control vs r57_grid.json: " + ", ".join(
    "%s %.6g/%.6g" % (k, EX[k], G["thresholds"][k]) for k in ("S1", "S2", "S3", "S4", "S5a1", "S5a2", "S5c", "S5d", "S7", "S9pf", "S9net")))
print("   S4 absolute reading (control MAR - 0.05) = %.5f" % RD_ABS_S4)

HYP = {"H-A": ("quiet_pct", 20, [10, 30], 18), "H-B": ("stretch_max", 1.5, [2, 1], 17),
       "H-C": ("rec_min", 0.45, [0.35, 0.55], 17), "H-D": ("vol_clock", 1.25, [1, 1.5], 17)}


def cid(h, v):
    return "%s %s=%g" % (h, HYP[h][0], v)


def retention(V, k):
    order = np.argsort(-ctl["u"], kind="stable")[:k]
    ve = np.sort(V["e"])
    kept = 0
    for j in order:
        p = np.searchsorted(ve, ctl["e"][j])
        kept += int(p < len(ve) and ve[p] <= ctl["x"][j])
    return kept


def centre_clauses(s, T, s8min, s4thr=None):
    s4 = T["S4"] if s4thr is None else s4thr
    lifts = [s[k]["pf"] - ctl[k]["pf"] for k in "ABCD"]
    return {"S1": s["win"] >= T["S1"], "S2": s["pf"] >= T["S2"], "S3": s["net"] >= T["S3"], "S4": s["mar"] >= s4,
            "S5a-E1": s["E1"]["top10"] <= T["S5a1"], "S5a-E2": s["E2"]["top10"] <= T["S5a2"],
            "S5b-E1": s["E1"]["ex10"] > 0, "S5b-E2": s["E2"]["ex10"] > 0, "S5c": s["ttz"] >= T["S5c"],
            "S5d": s["evr_ex05"] >= T["S5d"], "S6a": sum(v > 0 for v in lifts) >= 3,
            "S6b": s["E2"]["pf"] - ctl["E2"]["pf"] > 0, "S6c": s["E1"]["win"] - ctl["E1"]["win"] > 0,
            "S6d": s["E2"]["win"] - ctl["E2"]["win"] > 0, "S7a": s["corr"] <= T["S7"], "S7b": s["y2018"] >= 0,
            "S7c": s["y2022"] >= 0, "S8": retention(s, 20) >= s8min}


def s9(s, T):
    return {"win": s["win"] - ctl["win"] >= 0.5, "pf": s["pf"] >= T["S9pf"], "net": s["net"] >= T["S9net"],
            "E2pf": s["E2"]["pf"] - ctl["E2"]["pf"] >= 0}


print("\n3. CLAUSES per hypothesis (exact reading | rounded-table reading | S4 absolute) and A0")
for h, (knob, cen, nbrs, s8min) in HYP.items():
    s = S[cid(h, cen)]
    rec = G["results"][h]
    a0 = (s["win"] - ctl["win"] > 3.0) or (s["pf"] - ctl["pf"] > 0.30) or (s["net"] / ctl["net"] > 1.10)
    print("  %s centre %s: win lift %+.4f PF lift %+.5f net %.3f%% | A0 tripped %s (json %s)"
          % (h, cid(h, cen), s["win"] - ctl["win"], s["pf"] - ctl["pf"], 100 * s["net"] / ctl["net"], a0,
             rec["a0"]["tripped"]))
    for label, T, s4 in (("exact", EX, None), ("rounded", RD, None), ("S4-abs", EX, RD_ABS_S4)):
        cc = centre_clauses(s, T, s8min, s4)
        nb = {v: s9(S[cid(h, v)], T) for v in nbrs}
        fails = [k for k, ok in cc.items() if not ok] + ["S9-%s(%g)" % (k, v) for v in nbrs for k, ok in nb[v].items() if not ok]
        print("     %-7s fails: %s" % (label, fails))
    json_fail_centre = [c["clause"] for c in rec["centre_clauses"] if not c["passed"]]
    mine = [k for k, ok in centre_clauses(s, EX, s8min).items() if not ok]
    print("     json centre fails %s | identical to recompute: %s" % (json_fail_centre, json_fail_centre == mine))
    print("     top-20 retained %d (json %s), top-10 retained %d"
          % (retention(s, 20), [c["value"] for c in rec["centre_clauses"] if c["clause"] == "S8"], retention(s, 10)))

# ---- 4. section-5 extras recomputed
print("\n4. SECTION-5 EXTRAS")
sb = S[cid("H-B", 1.5)]
print("  H-B era D net ratio %.5f (>=0.90) | win lift C %+.3f D %+.3f"
      % (sb["D"]["net"] / ctl["D"]["net"], sb["C"]["win"] - ctl["C"]["win"], sb["D"]["win"] - ctl["D"]["win"]))
sc = S[cid("H-C", 0.45)]
print("  H-C win lift %+.4f (kill < +0.75) | era D ratio %.5f" % (sc["win"] - ctl["win"], sc["D"]["net"] / ctl["D"]["net"]))
sa = S[cid("H-A", 20)]
print("  H-A win lift %+.4f (kill < +0.55) | top-10 retained %d | top-20 retained %d (>= 18)"
      % (sa["win"] - ctl["win"], retention(sa, 10), retention(sa, 20)))
sd = S[cid("H-D", 1.25)]
lo, hi = math.ceil(0.6 * ctl["n"]), math.floor(1.4 * ctl["n"])
print("  H-D count %d within %d..%d: %s" % (sd["n"], lo, hi, lo <= sd["n"] <= hi))
ck = set(zip(ctl["e"].tolist(), ctl["x"].tolist(), np.round(ctl["epx"], 6).tolist()))
vk = set(zip(sd["e"].tolist(), sd["x"].tolist(), np.round(sd["epx"], 6).tolist()))
removed = np.array([k not in vk for k in zip(ctl["e"].tolist(), ctl["x"].tolist(), np.round(ctl["epx"], 6).tolist())])
# reading used: no control ENTRY inside the variant span
ce = np.sort(ctl["e"])
p = np.searchsorted(ce, sd["e"])
added_entry = ~((p < len(ce)) & (ce[np.minimum(p, len(ce) - 1)] <= sd["x"]))
# alternative reading: no control trade whose [entry, exit] OVERLAPS the variant span
added_overlap = np.array([not np.any((ctl["e"] <= xb) & (ctl["x"] >= eb)) for eb, xb in zip(sd["e"], sd["x"])])
# alternative removed: control trade with no variant ENTRY in its span (the S8 test)
ve = np.sort(sd["e"])
q = np.searchsorted(ve, ctl["e"])
removed_span = ~((q < len(ve)) & (ve[np.minimum(q, len(ve) - 1)] <= ctl["x"]))
m2v, m2c = np.asarray(sd["ent"] >= E2), np.asarray(ctl["ent"] >= E2)
for lab, add, rem in (("driver reading (entry-in-span added, identical-trade removed)", added_entry, removed),
                      ("overlap added, identical-trade removed", added_overlap, removed),
                      ("overlap added, span removed", added_overlap, removed_span)):
    print("  H-D %s:" % lab)
    for nm, mv, mc in (("E1", ~m2v, ~m2c), ("E2", m2v, m2c), ("all", np.ones(len(m2v), bool), np.ones(len(m2c), bool))):
        au, ru = sd["u"][add & mv], ctl["u"][rem & mc]
        print("     %-3s added n=%d PF %.4f | removed n=%d PF %.4f -> added>=removed %s%s"
              % (nm, len(au), pf(au), len(ru), pf(ru), pf(au) >= pf(ru), (" | added PF>=1 %s" % (pf(au) >= 1)) if nm == "all" else ""))
for lab, key in (("09:30<=t<=09:35", "x0930_incl"), ("09:30<=t<09:35", "x0930_excl")):
    print("  H-D PF lift ex %s: %+.5f" % (lab, pf(sd["u"][~sd[key]]) - pf(ctl["u"][~ctl[key]])))
print("  H-D PF lift signs: " + ", ".join("%g %+.4f" % (v, S[cid("H-D", v)]["pf"] - ctl["pf"]) for v in (1, 1.25, 1.5)))
print("\nsurvivors in r57_grid.json: %s" % G["survivors"])
