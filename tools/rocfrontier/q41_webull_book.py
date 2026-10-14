"""Q41 THE WEBULL BOOK YARDSTICK (MANAGER #158) per bookq/PREDATA_Q41_WEBULL_BOOK.txt: the live QQQ book as deployed (ORB_R6 10 sh, NOISE_382
10 sh x plugin size, DIP_424F 6 sh a lot) on the QQQ 5m Alpaca master, per-share P&L by Q38's unit_trades (imported unchanged), four numbers per
stretch (WF 2017-08-07..2025-06-29; LB 2025-06-30..2026-06-30 apart, a report). Rows V0 as deployed, V1 without DIP, V2 equal risk, each leg alone.
    python q41_webull_book.py run"""
import hashlib
import json
import os
import sys

REPO = r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"
BQ = r"C:\EdgeLog\_anatomy_cache\bookq"
NOTE = os.path.join(BQ, "PREDATA_Q41_WEBULL_BOOK.txt")
NOTE_SHA = "aef2fc1d205a63efdb9abd7efd13c97f18ec41681c05820fe67d562310212d8a"
Q38_SHA = "411ca99b6e2d6647ef035356834da3fab4fbd4958c840f7ab25de2562130dddd"    # q38_webull_bands.py as run 2 (addendum 1)
QQQ5_SHA = "782dabdd7dd7d265c9a31626f03c6940cdaaf4d7511da95bf8a8efc41fba5a1d"
OUT = r"C:\EdgeLog\_anatomy_cache\q41"
WF = ("2017-08-07", "2025-06-29")
LB = ("2025-06-30", "2026-06-30")
SIZE_WIN = ("2017-08-07", "2019-08-06")                                 # V2's sizing window: the first two WF years
lf = lambda p: hashlib.sha256(open(p, "rb").read().replace(b"\r\n", b"\n")).hexdigest()
sha = lambda p: hashlib.sha256(open(p, "rb").read()).hexdigest()


def run():
    for p in (REPO, os.path.join(REPO, "tools"), BQ):
        sys.path.insert(0, p)
    os.chdir(REPO)
    import numpy as np
    import pandas as pd
    import q38_webull_bands as Q38
    import seat_pipeline_final as SP
    from api import cloud_signal as cs
    from augur_engine.data import find_master, load_master_arrays
    from augur_engine.drawdowns import dd5, dd_pct_peak
    from augur_engine.engine import run_backtest
    qm = find_master("QQQ", "5m", "rth", "alpaca_split_rth")
    pins = {"note": lf(NOTE), "q38": lf(os.path.join(BQ, "q38_webull_bands.py")), "qqq5m": sha(os.path.join(REPO, "augur_uploads", qm["filename"]))}
    print(f"PINS: note LF {pins['note']}; script LF {lf(__file__)}; q38 LF {pins['q38']}; QQQ 5m {qm['filename']} {pins['qqq5m']}", flush=True)
    if (pins["note"], pins["q38"], pins["qqq5m"]) != (NOTE_SHA, Q38_SHA, QQQ5_SHA):
        raise SystemExit("refused: a pinned input is not the frozen one (nothing computed)")
    os.makedirs(OUT, exist_ok=True)
    arr = load_master_arrays(qm)
    ix = pd.DatetimeIndex(arr["index"])
    ix = ix.tz_convert("America/New_York").tz_localize(None) if ix.tz is not None else ix
    cal = pd.DatetimeIndex(sorted(set(ix.normalize())))
    legs = {"ORB_R6": cs.CROWN_LEGS["ORB_R6"], "NOISE_382": cs.CROWN_LEGS["NOISE_382"], "DIP_424F": cs.SHADOW_LEGS["DIP_424F"]}
    S = {}
    for name, leg in legs.items():
        tr = Q38.unit_trades(name, leg, arr, run_backtest, np)
        s = pd.Series([v for _, v in tr], index=pd.DatetimeIndex([d for d, _ in tr])).groupby(level=0).sum()
        S[name] = s.reindex(cal).fillna(0.0)
    S = pd.DataFrame(S)
    S.to_csv(os.path.join(OUT, "q41_legs_daily.csv"))

    def four(x, a, b):
        w = x[(x.index >= a) & (x.index <= b)]
        v = w.to_numpy(float)
        yrs = (pd.Timestamp(b) - pd.Timestamp(a)).days / 365.25
        q = np.cumsum(v)
        dd = float((np.maximum.accumulate(np.concatenate([[0.0], q]))[1:] - q).max()) if len(v) else 0.0
        r5 = dd5(w)
        p = dd_pct_peak(v, 100_000)
        p = float(p["dd_pct"] if isinstance(p, dict) else p)
        npy = float(v.sum()) / yrs
        return {"roc30": npy * 30.0 / dd if dd > 0 else float("nan"), "dd5": float(r5["dd5_usd"]), "dd_pct_peak": p, "sortino": SP.sortino(v),
                "net_per_year": npy, "worst_dd": dd, "one_episode": bool(r5["one_episode"])}

    sw = S[(S.index >= SIZE_WIN[0]) & (S.index <= SIZE_WIN[1])]
    sd = sw.std(ddof=1)
    V0 = S.sum(axis=1)
    V1 = S[["ORB_R6", "NOISE_382"]].sum(axis=1)
    eq = (S / sd).sum(axis=1)
    k = float(V0[(V0.index >= SIZE_WIN[0]) & (V0.index <= SIZE_WIN[1])].std(ddof=1) / eq[(eq.index >= SIZE_WIN[0]) & (eq.index <= SIZE_WIN[1])].std(ddof=1))
    V2 = eq * k
    w2 = {c: float(k / sd[c]) for c in S.columns}
    rows = {"V0 as deployed": V0, "V1 without DIP": V1, "V2 equal risk": V2, "ORB_R6 alone (10 sh)": S["ORB_R6"],
            "NOISE_382 alone (10 sh x plugin)": S["NOISE_382"], "DIP_424F alone (6 sh a lot)": S["DIP_424F"]}
    out = {"pins": pins, "WF": WF, "LB": LB, "size_window": SIZE_WIN, "V2_multipliers_on_deployed_units": w2, "rows": {}}
    print(f"V2 multipliers on the deployed units (sized on {SIZE_WIN[0]}..{SIZE_WIN[1]}): " + ", ".join(f"{c} x{v:.2f}" for c, v in w2.items()), flush=True)
    for nm, x in rows.items():
        out["rows"][nm] = {"WF": four(x, *WF), "LB": four(x, *LB)}
        a, b = out["rows"][nm]["WF"], out["rows"][nm]["LB"]
        print(f"{nm:<34} WF: ROC@30k {a['roc30']:6.2f} | DD5 ${a['dd5']:>7,.0f} | DD% {a['dd_pct_peak']:5.2f} | Sortino {a['sortino']:4.2f} | "
              f"${a['net_per_year']:>7,.0f}/yr{' | 1 EP' if a['one_episode'] else ''}   LB (report): ROC@30k {b['roc30']:6.2f} | DD5 ${b['dd5']:>6,.0f} | "
              f"DD% {b['dd_pct_peak']:5.2f} | Sortino {b['sortino']:4.2f} | ${b['net_per_year']:>7,.0f}/yr", flush=True)
    C = S[(S.index >= WF[0]) & (S.index <= WF[1])].corr()
    out["wf_corr"] = C.round(3).to_dict()
    print("WF daily $ correlation: " + ", ".join(f"{a}-{b} {C.loc[a, b]:.2f}" for i, a in enumerate(C.columns) for b in C.columns[i + 1:]), flush=True)
    lift = out["rows"]["V0 as deployed"]["WF"]["roc30"] > out["rows"]["V1 without DIP"]["WF"]["roc30"]
    out["reading"] = "DIP lifts the book" if lift else "DIP adds dollars, not ROC per drawdown"
    print("READING (pre-set words): " + out["reading"], flush=True)
    json.dump(out, open(os.path.join(OUT, "q41_webull_book.json"), "w"), indent=1, default=float)
    print("wrote", os.path.join(OUT, "q41_webull_book.json"))


if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] != "run":
        raise SystemExit(__doc__)
    run()
