"""Q49 FIXED vs KEEL on every BOOK #463 leg and on the book (MANAGER #183, owner 10-18 "more testing on things that are promising").
Pre-registered in docs/PREDATA_frontier_fixkeel_2026-10-18.txt (its LF sha256 is checked before anything runs). Report-only: nothing is
adopted; a book arm that clears the bar goes to the owner through MANAGER as a BOOK LIFT candidate for a forward line.

    python tools/rocfrontier/q49_fixkeel.py            (from the shared checkout's data; writes C:\\EdgeLog\\_anatomy_cache\\q49\\)
"""
import hashlib
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
WT = os.path.dirname(os.path.dirname(HERE))
SHARED = r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"
for p in (SHARED, os.path.join(SHARED, "tools"), os.path.join(SHARED, "tools", "rocfrontier")):
    sys.path.insert(0, p)
os.chdir(SHARED)
PREREG = os.path.join(WT, "docs", "PREDATA_frontier_fixkeel_2026-10-18.txt")
OUT = r"C:\EdgeLog\_anatomy_cache\q49"
Q37 = r"C:\EdgeLog\_anatomy_cache\q37\q37_daily.csv"


def lf_sha(path):
    return hashlib.sha256(open(path, "rb").read().replace(b"\r\n", b"\n")).hexdigest()


PREREG_SHA = os.environ.get("Q49_PREREG_SHA", "")
got = lf_sha(PREREG)
assert PREREG_SHA and got == PREREG_SHA, f"prereg sha mismatch: file {got} vs expected {PREREG_SHA!r}"
ADD1 = PREREG.replace(".txt", "_ADDENDUM1.txt")
ADD1_SHA = os.environ.get("Q49_ADD1_SHA", "")
assert ADD1_SHA and lf_sha(ADD1) == ADD1_SHA, f"addendum 1 sha mismatch: file {lf_sha(ADD1)} vs expected {ADD1_SHA!r}"
print("addendum 1 LF sha256", ADD1_SHA, "ok", flush=True)
print("prereg LF sha256", got, "ok; script LF sha256", lf_sha(os.path.abspath(__file__)), flush=True)

import numpy as np
import pandas as pd
import r11_risk as R11
from augur_engine import book as BK, ml_keel
from augur_engine.data import find_master, load_master_arrays
from augur_engine.drawdowns import four_numbers

TS = pd.Timestamp
WF0, WF1, LB0, LB1 = R11.WF0, R11.PRE_END, R11.LB0, R11.LB1
FOLDS = [(TS(f"{y}-07-01"), TS(f"{y + 1}-06-30")) for y in range(2016, 2025)]
FOLDS[-1] = (FOLDS[-1][0], WF1)
NAMES = ["ORB", "ENGU-Q", "TTM", "NOISE"]
SEED = 20261018
os.makedirs(OUT, exist_ok=True)

# ------------------------------------------------------------------ the reference book (RISK r1 records, rule U) and its parity
legs_meta = R11.load_json("build.json")["legs"]
B = R11.load_book("U", legs_meta)
IDX = B.index
ref = {NAMES[k]: pd.Series(B.Am_leg[k].T @ B.ones, index=IDX) for k in range(4)}
f463 = four_numbers(sum(ref.values())[(IDX >= WF0) & (IDX <= WF1)])
assert round(f463["roc30"], 2) == 93.81 and round(f463["sortino"], 3) == 3.816, f463
z = np.load(os.path.join(R11.OUT, "records_U.npz"))
ref_closed = {NAMES[k]: z["closed"][z["leg"] == k] for k in range(4)}


def daily(rec):
    s = R11.by_day(rec["inc_d"], rec["inc_v"])
    return s.reindex(IDX.union(s.index)).fillna(0.0)


def add(*ss):
    ix = ss[0].index
    for s in ss[1:]:
        ix = ix.union(s.index)
    return sum(s.reindex(ix).fillna(0.0) for s in ss)


def arm_records(st, sizes):
    st2 = dict(st)
    st2["sized"] = [(t, float(m)) for (t, _), m in zip(st["sized"], sizes)]
    return R11.trade_records(st2, st["days_idx"])


# ------------------------------------------------------------------ per leg: rebuild RAW, the KEEL v12 walk (seed 42), the v12 fixed tilts
legs = R11.book_legs()
LEG, info_out = {}, {}
for k, leg in enumerate(legs):
    nm = NAMES[k]
    tr, info = BK._leg_trades(dict(leg), R11.W0, R11.W1, keep_state=True)
    st = info.pop("_state")
    raw = [t for t, _ in st["sized"]]
    ent = np.array([int(t[0]) for t in raw], np.int64)
    master = find_master(leg["instrument"], leg.get("timeframe", "5m"), info["session"], info["source"])
    arr = load_master_arrays(master, date_from=R11.W0, date_to=R11.W1)
    assert len(arr["index"]) == st["last"] + 1, f"{nm}: arrays differ from the engine's ({len(arr['index'])} vs {st['last'] + 1})"
    order = np.argsort(ent, kind="stable")
    feats = ml_keel.keel_features(arr)
    kw = ml_keel.keel_walk(arr, [raw[i] for i in order], feats=feats, seed=42, version="v12")
    m_keel = np.empty(len(raw))
    m_keel[order] = np.asarray(kw["size"], float)
    m_fix = np.asarray(ml_keel.fixed_tilt_sizes_v12(arr, ent, feats=feats), float)
    sizes = {"RAW": np.ones(len(raw)), "FIXED": m_fix, "KEEL": m_keel}
    rec = {a: arm_records(st, s) for a, s in sizes.items()}
    n_ok = len(rec["RAW"]["closed"]) == len(ref_closed[nm])
    cl_diff = float(np.abs(rec["RAW"]["closed"] - ref_closed[nm]).max()) if n_ok else float("nan")
    d_raw = daily(rec["RAW"])
    day_diff = float((d_raw - ref[nm]).abs().max()) if d_raw is not None else float("nan")
    parity = bool(n_ok and cl_diff <= 0.01 and day_diff <= 0.01)
    ent_day = pd.to_datetime(np.asarray(st["days_idx"])[np.clip(ent, 0, st["last"])])   # each trade's entry day, in the leg's own order
    wf_mask = (ent_day >= WF0) & (ent_day <= WF1)
    LEG[nm] = {"st": st, "sizes": sizes, "rec": rec, "parity": parity, "wf_mask": np.asarray(wf_mask)}
    info_out[nm] = {"trades": int(len(raw)), "parity": parity, "closed_maxdiff": cl_diff, "daily_maxdiff": day_diff,
                    "master": info.get("master"), "keel_trust_on_WF": float((np.asarray(kw["trust"])[np.argsort(order)][np.asarray(wf_mask)] > 0).mean())
                    if n_ok else None}
    print(f"{nm}: {len(raw)} trades; RAW parity vs RISK r1 records {parity} (closed {cl_diff:.4f}, daily {day_diff:.4f}); "
          f"WF mean size FIXED {m_fix[np.asarray(wf_mask)].mean():.3f}, KEEL {m_keel[np.asarray(wf_mask)].mean():.3f}", flush=True)


def leg_series(nm, arm):
    """Daily $ of one leg in one arm, ALL on today's rebuild (ADDENDUM 1: the parity gate failed on ORB / ENGU-Q / NOISE after the 10-14/15
    master repairs, so every arm is scored like-for-like on the same rebuilt trade list). CONST arms = rebuilt RAW x the arm's WF-mean size."""
    L = LEG[nm]
    if arm in ("RAW", "FIXED", "KEEL"):
        return daily(L["rec"][arm])
    base = arm[:-2]                                                    # 'FIXED_C' / 'KEEL_C'
    c = float(L["sizes"][base][L["wf_mask"]].mean())
    return daily(L["rec"]["RAW"]) * c


ARMS_LEG = ["RAW", "FIXED", "KEEL", "FIXED_C", "KEEL_C"]


def cut(s, lo, hi):
    return s[(s.index >= lo) & (s.index <= hi)]


def folds(s):
    out = []
    for lo, hi in FOLDS:
        w = cut(s, lo, hi).to_numpy(float)
        c = np.cumsum(w)
        dd = float((np.maximum.accumulate(np.concatenate([[0.0], c]))[1:] - c).max())
        yrs = (hi - lo).days / 365.25
        out.append({"fold": f"{lo.year}-{lo.year + 1}", "net": float(w.sum()), "dd": dd, "roc30": 30.0 * (w.sum() / yrs) / dd if dd > 0 else None})
    return out


def paired_sd(a, b, seed):
    """Paired 21-day block bootstrap of WF ROC@30k(b) - ROC@30k(a); the same blocks for both each draw (shelf 13)."""
    a, b = a.to_numpy(float), b.to_numpy(float)
    n, Lb = len(a), 21
    yrs = (cut(sum(ref.values()), WF0, WF1).index[-1] - cut(sum(ref.values()), WF0, WF1).index[0]).days / 365.25

    def roc(v):
        c = np.cumsum(v)
        dd = float((np.maximum.accumulate(np.concatenate([[0.0], c]))[1:] - c).max())
        return 30.0 * (v.sum() / yrs) / dd if dd > 0 else np.nan

    rng = np.random.default_rng(seed)
    d = []
    for _ in range(2000):
        st = rng.integers(0, n - Lb + 1, size=n // Lb + 1)
        ii = np.concatenate([np.arange(s, s + Lb) for s in st])[:n]
        d.append(roc(b[ii]) - roc(a[ii]))
    d = np.asarray(d)
    return float(np.nanstd(d)), float(np.nanmean(d >= 4.69))


res = {"prereg_sha": got, "legs_info": info_out, "legs": {}, "book": {}, "dip": {}}
# ------------------------------------------------------------------ legs alone
for nm in NAMES:
    res["legs"][nm] = {}
    for arm in ARMS_LEG:
        s = leg_series(nm, arm)
        if s is None:
            res["legs"][nm][arm] = "not mappable (RAW parity failed)"
            continue
        r = {"WF": four_numbers(cut(s, WF0, WF1)), "LB": four_numbers(cut(s, LB0, LB1)), "folds": folds(s)}
        res["legs"][nm][arm] = r
        print(f"LEG {nm:<6} {arm:<8} WF {r['WF']['roc30']:7.2f} / ${r['WF']['dd5_usd']:>7,.0f} / {r['WF']['dd_pct_peak']:5.2f}% / {r['WF']['sortino']:5.3f}"
              f"{' 1EP' if r['WF']['one_episode'] else ''} | LB {r['LB']['roc30'] if r['LB']['roc30'] is None else round(r['LB']['roc30'], 2)}", flush=True)

# ------------------------------------------------------------------ the book: every leg in one arm, and one leg swapped at a time
book_arms = {"RAW": {n: "RAW" for n in NAMES}}
for arm in ("FIXED", "KEEL", "FIXED_C", "KEEL_C"):
    book_arms[f"ALL {arm}"] = {n: arm for n in NAMES}
    for n in NAMES:
        book_arms[f"{n} {arm}"] = {m: (arm if m == n else "RAW") for m in NAMES}
pub = sum(ref.values())                                                # #463 as published (RISK r1 records)
res["book"]["#463 published (RISK r1 records)"] = {"WF": four_numbers(cut(pub, WF0, WF1)), "LB": four_numbers(cut(pub, LB0, LB1)), "folds": folds(pub)}
raw_book = add(*[leg_series(n, "RAW") for n in NAMES])                  # ADDENDUM 1: the bar is read against the REBUILT RAW book
RB = four_numbers(cut(raw_book, WF0, WF1))
for name, spec in book_arms.items():
    s = add(*[leg_series(n, a) for n, a in spec.items()])
    r = {"WF": four_numbers(cut(s, WF0, WF1)), "LB": four_numbers(cut(s, LB0, LB1)), "folds": folds(s)}
    if name != "RAW":
        r["paired_sd_vs_raw"], _ = paired_sd(cut(raw_book, WF0, WF1).reindex(cut(s, WF0, WF1).index).fillna(0.0), cut(s, WF0, WF1), SEED)
        twin = name.replace("FIXED", "FIXED_C").replace("KEEL", "KEEL_C") if not name.endswith("_C") else None
        r["twin"] = twin
        w = r["WF"]
        r["bar"] = {"roc": w["roc30"] >= 1.05 * RB["roc30"], "sortino": w["sortino"] >= RB["sortino"], "dd5": w["dd5_usd"] <= RB["dd5_usd"],
                    "not_one_episode": not w["one_episode"], "beyond_paired_1.96sd": (w["roc30"] - RB["roc30"]) > 1.96 * r["paired_sd_vs_raw"]}
    r["fold_wins_vs_raw"] = sum(1 for a, b in zip(r["folds"], folds(raw_book)) if a["net"] > b["net"]) if name != "RAW" else None
    res["book"][name] = r
for name, r in res["book"].items():
    if isinstance(r, dict) and r.get("twin") and isinstance(res["book"].get(r["twin"]), dict):
        t = res["book"][r["twin"]]["WF"]
        r["bar"]["beats_const_twin"] = r["WF"]["roc30"] > t["roc30"] and r["WF"]["sortino"] >= t["sortino"]
        r["LIFT"] = all(r["bar"].values())
    elif isinstance(r, dict) and "bar" in r:
        r["LIFT"] = False                                              # a CONST twin is a leverage control, never a candidate
for name, r in res["book"].items():
    if isinstance(r, dict):
        w = r["WF"]
        print(f"BOOK {name:<16} WF {w['roc30']:7.2f} / ${w['dd5_usd']:>7,.0f} / {w['dd_pct_peak']:5.2f}% / {w['sortino']:5.3f}{' 1EP' if w['one_episode'] else ''}"
              f" | LB {r['LB']['roc30']:.2f} | folds won {r.get('fold_wins_vs_raw')} | paired SD {r.get('paired_sd_vs_raw', float('nan')):.2f}"
              f" | {'BOOK LIFT' if r.get('LIFT') else ''}", flush=True)

# ------------------------------------------------------------------ DIP #424 (not in #463): the T11 arms from Q37's daily file (NQ, exit-day)
q = pd.read_csv(Q37, index_col=0, parse_dates=True)
for col, tag in (("NQ RAW", "RAW"), ("NQ F fixed at s_bar", "F (const at KEEL mean)"), ("NQ FT fixed tilts only", "FT (fixed tilts)"),
                 ("NQ KEEL v12 (today's walk)", "KEEL v12")):
    s = q[col].astype(float)
    s = s[(s.index >= TS("2017-08-07")) & (s.index <= TS("2025-08-23"))]
    res["dip"][tag] = {"WF_common": four_numbers(s), "folds": [
        {"fold": f"{lo.year}-{lo.year + 1}", "net": float(cut(s, lo, hi).sum())} for lo, hi in FOLDS if hi >= TS("2017-08-07")]}
    f = res["dip"][tag]["WF_common"]
    print(f"DIP {tag:<24} {f['roc30']:7.2f} / ${f['dd5_usd']:>8,.0f} / {f['dd_pct_peak']:6.2f}% / {f['sortino']:5.3f}{' 1EP' if f['one_episode'] else ''}", flush=True)

json.dump(res, open(os.path.join(OUT, "q49_fixkeel.json"), "w"), indent=1, default=float)
lifts = [n for n, r in res["book"].items() if isinstance(r, dict) and r.get("LIFT")]
print("BOOK LIFT candidates:", lifts or "none", flush=True)
