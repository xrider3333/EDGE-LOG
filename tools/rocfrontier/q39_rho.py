"""Q39 FAMILY LUCK BAR PRE-WORK - the effective-trial ratio rho per family (MANAGER #142 (b)), per bookq/PREDATA_Q39_RHO.txt. For one validate
per family: re-run every stored setting on the run's tuning window, keep the settings valid by the run's own rule, ONC-cluster their daily $
(Q30's onc, unchanged) -> E, rho = E / valid. Then E_fam = rho x the family's valid configs, with and without ancestors. No Sharpe of any
crown is computed.
    python q39_rho.py run"""
import hashlib
import json
import os
import sys

BQ = r"C:\EdgeLog\_anatomy_cache\bookq"
sys.path.insert(0, BQ)
import numpy as np
import pandas as pd
import q30_efftrials as Q30                                           # onc(), unchanged (its import sets REPO paths / env, nothing else)

NOTE = os.path.join(BQ, "PREDATA_Q39_RHO.txt")
NOTE_SHA = "a8f353a259fbb995add1e40bbc50c576a06bca6d0b95b1e799ffefac19c0438a"
RUNS = {"ORB": 314, "ENGU-Q": 335, "NOISE": 395, "TTM": 479, "DIP": 358}
DOC_DIRS = (r"C:\EdgeLog\_anatomy_cache\runs", r"C:\EdgeLog\_anatomy_cache\luckbar\runs")
SUMMARY = r"C:\EdgeLog\_anatomy_cache\luckbar\runs_summary.csv"
OUT = r"C:\EdgeLog\_anatomy_cache\luckbar"
SESSION = {"rth": "rth", "eth": "eth"}
lf = lambda p: hashlib.sha256(open(p, "rb").read().replace(b"\r\n", b"\n")).hexdigest()


def load_doc(n):
    for d0 in DOC_DIRS:
        p = os.path.join(d0, f"{n}.json")
        if os.path.exists(p):
            return json.load(open(p, encoding="utf-8"))
    raise SystemExit(f"run #{n}: no doc")


def session_of(d):
    src = str(d.get("data_source") or "")
    return "eth" if src.endswith("_eth") else "rth"


def measure(fam, n):
    from augur_engine.data import find_master, load_master_arrays
    from augur_engine.engine import run_backtest
    d = load_doc(n)
    v = d.get("validate") or {}
    win = (v.get("windows") or {}).get("optimize")
    split = pd.Timestamp((v.get("windows") or {}).get("wf_split"))
    min_tr = 30                                                       # auto.py min_trades default (no doc stores another)
    bp = d.get("best_params") or {}
    if isinstance(bp, str):
        bp = json.loads(bp.replace("'", '"').replace("True", "true").replace("False", "false"))
    keys = sorted(bp.keys())
    m = find_master(d["instrument"], d["timeframe"], session_of(d), d.get("data_source"))
    arr = load_master_arrays(m, date_from=d.get("date_from"), date_to=win[1])
    ix = pd.DatetimeIndex(arr["index"])
    day = (ix.tz_localize(None) if ix.tz is not None else ix).normalize()
    seen, cfgs = set(), []
    for p in d.get("points") or []:
        cfg = {k: p[k] for k in keys if k in p}
        sig = json.dumps(cfg, sort_keys=True, default=str)
        if len(cfg) == len(keys) and sig not in seen:
            seen.add(sig)
            cfgs.append(cfg)
    mult = float(d.get("multiplier") or 1.0)
    cost = float(d.get("cost_pts") or 0.0)
    sess = pd.DatetimeIndex(sorted(set(day[day <= pd.Timestamp(win[1])])))
    cols, n_is = {}, {}
    for i, cfg in enumerate(cfgs):
        bt = run_backtest(d["strategy"], arrays=arr, params=cfg, cost_pts=cost, return_trades=True)
        tr = bt.get("trades") or []
        s = pd.Series([float(t[2]) * mult for t in tr], index=[day[min(int(t[1]), len(day) - 1)] for t in tr]).groupby(level=0).sum()
        cols[f"s{i:03d}"] = s.reindex(sess).fillna(0.0)
        n_is[f"s{i:03d}"] = sum(1 for t in tr if day[min(int(t[1]), len(day) - 1)] < split)
        if (i + 1) % 100 == 0:
            print(f"   {fam} #{n}: {i + 1}/{len(cfgs)} settings", flush=True)
    df = pd.DataFrame(cols)
    valid = [c for c in df.columns if n_is[c] >= min_tr and df[c].std() > 0]
    corr = df[valid].corr()
    cl = Q30.onc(corr, seed=Q30.SEED)
    cl2 = Q30.onc(corr, seed=Q30.SEED_CHECK)
    out = {"run": n, "strategy": d["strategy"], "master": m["filename"], "window": [d.get("date_from"), win[1]], "is_split": str(split.date()),
           "min_trades": min_tr, "points": len(d.get("points") or []), "distinct": len(cfgs), "valid_rebuilt": len(valid),
           "run_n_valid": d.get("n_valid"), "median_rho_pair": float(np.nanmedian(corr.to_numpy()[np.triu_indices(len(valid), 1)])) if len(valid) > 1 else None,
           "E": len(cl), "E_check": len(cl2), "rho": len(cl) / len(valid) if valid else None}
    print(f"{fam} #{n} ({d['strategy']}, {m['filename']}, {out['window'][0]}..{out['window'][1]}): {out['points']} points, {out['distinct']} distinct, "
          f"{out['valid_rebuilt']} valid (run's own {out['run_n_valid']}); median pair correlation {out['median_rho_pair']:.3f}; E = {out['E']} "
          f"(check seed {out['E_check']}); rho = {out['rho']:.3f}", flush=True)
    return out


def run():
    note_sha = lf(NOTE)
    print(f"PINS: note LF {note_sha}; script LF {lf(__file__)}; q30 LF {lf(os.path.join(BQ, 'q30_efftrials.py'))}", flush=True)
    if note_sha != NOTE_SHA:
        raise SystemExit("refused: the note is not the frozen one (nothing computed)")
    res = {fam: measure(fam, n) for fam, n in RUNS.items()}
    S = pd.read_csv(SUMMARY)
    S["lin"] = S["lin"].replace({"NQDIP": "DIP", "ETFDIP": "DIP"})
    print("\nE_fam = rho x valid configs (with / without ancestors; the ENGU grid ancestors at rho(ENGU-Q #335), the harsh bound):")
    fam_out = {}
    for fam, r in res.items():
        x = S[S["lin"] == fam]
        n_all = float(x["n_valid"].sum())
        n_no = float(x[~x["ancestor"]]["n_valid"].sum())
        e_all, e_no = r["rho"] * n_all, r["rho"] * n_no
        fam_out[fam] = {"rho": r["rho"], "N_with_ancestors": n_all, "N_without": n_no, "E_with_ancestors": e_all, "E_without": e_no, "runs": int(len(x))}
        print(f"  {fam:<7} rho {r['rho']:.3f}: N {n_no:,.0f} -> E {e_no:,.0f} without ancestors" +
              (f"; N {n_all:,.0f} -> E {e_all:,.0f} with ENGU's grid runs" if n_all != n_no else " (no ancestors)"))
    json.dump({"note_sha256_lf": note_sha, "runs": res, "families": fam_out}, open(os.path.join(OUT, "q39_rho.json"), "w"), indent=1, default=float)
    print("wrote", os.path.join(OUT, "q39_rho.json"))


if __name__ == "__main__":
    run()
