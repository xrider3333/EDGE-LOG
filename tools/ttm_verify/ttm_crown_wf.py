"""TTM (house verifier, MANAGER #110): BLIND re-check of an Auto-Validate CROWN as it lands - the champion re-run on its own run's
master and window on TTM's own path, parity against the run doc's stored champion figures, then the WF four numbers the validate
store lacks (ROC@30k, DD5, DD% from peak, Sortino) at the run's cost and at the owner's real cost.
Usage: python ttm_crown_wf.py <run number | backtests job id>
Prereg: prereg/ttm-verify-crowns (docs/PREREG_TTM_VERIFY_CROWNS_2026-10-14.txt), written while both target validates were still running.
Reads ONE run doc (by id) from Firestore; never writes to it. Writes only into C:/EdgeLog/_anatomy_cache/ttm_crownwf/."""
import hashlib
import json
import os
import sys
import types

import numpy as np
import pandas as pd

REPO = "C:/Users/xride/OneDrive/Desktop/EDGE-LOG"
OUT = "C:/EdgeLog/_anatomy_cache/ttm_crownwf"
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "tools"))
os.chdir(REPO)
os.environ["AUGUR_TRIAL_CACHE"] = "0"
from augur_engine.data import find_master, load_master_arrays   # noqa: E402
from augur_engine.engine import run_backtest                     # noqa: E402
from augur_engine.drawdowns import dd5, dd_pct_peak               # noqa: E402
import runboard_watch as RW                                       # noqa: E402

REAL_COST_PTS = {"NQ": 0.7825, "ES": 0.6130}     # owner rule: $5.65 commission + 1 tick each side, per contract round trip
F = ["strategy", "instrument", "data_source", "source_name", "timeframe", "date_from", "date_to", "cost_pts", "multiplier",
     "validate.champion", "validate.windows", "validate.wf_oos", "selection"]


def sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def run_doc(key):
    db = RW.real_client()
    if not key.isdigit():
        j = RW._user(db).collection("backtests").document(key).get().to_dict()
        rn = j.get("run_number") or j.get("run_id")
        assert rn, "job %s has no saved run yet (status %s)" % (key, j.get("status"))
        key = str(rn)
    return key, RW.run_ref(db, int(key)).get(field_paths=F).to_dict()


def leg_rows(r, idx, c_pts, mult):
    """per trade: entry/exit ET, net $ at cost c_pts (the size fold undone where the file reports it), side, entry px, size."""
    T = r["trades"]
    pts = np.array([float(t[2]) for t in T])
    s = np.asarray(r.get("trade_sizes") or [1.0] * len(T), float)
    k = float(r.get("size_cost_pts") or 0.0)
    raw = (pts + (s - 1.0) * k) / s
    return pd.DataFrame({"entry": idx[[t[0] for t in T]].tz_localize(None), "exit": idx[[t[1] for t in T]].tz_localize(None),
                         "eb": [int(t[0]) for t in T], "xb": [int(t[1]) for t in T], "side": [float(t[3]) for t in T],
                         "epx": [float(t[4]) for t in T], "size": s, "raw": raw, "usd": s * (raw - c_pts) * mult})


def daily_closed(df, days):
    return pd.Series(df["usd"].to_numpy(float), index=df["exit"].dt.normalize()).groupby(level=0).sum() \
        .reindex(days, fill_value=0.0).to_numpy(float)


def daily_mtm(df, days, closes, idx_naive, mult):
    """valued daily: an open position is marked at the last bar of each ET date before its exit date; cost lands on exit."""
    dates = idx_naive.normalize()
    last_bar = pd.Series(np.arange(len(dates)), index=dates).groupby(level=0).max()
    out = pd.Series(0.0, index=days)
    for e in df.itertuples(index=False):
        prev = 0.0
        d0, d1 = e.entry.normalize(), e.exit.normalize()
        for D in last_bar.index[(last_bar.index >= d0) & (last_bar.index < d1)]:
            m = e.side * (closes[last_bar[D]] - e.epx) * e.size * mult
            if D in out.index:
                out[D] += m - prev
            prev = m
        if d1 in out.index:
            out[d1] += e.usd - prev
    return out.to_numpy(float)


def four(x, days):
    x = np.asarray(x, float)
    eq = np.cumsum(x)
    mdd = float(np.max(np.maximum.accumulate(np.concatenate([[0.0], eq]))[1:] - eq))
    yrs = (days[-1] - days[0]).days / 365.25
    down = np.sqrt(np.mean(np.minimum(x, 0.0) ** 2))
    s = pd.Series(x, index=days)
    r = dd5(s)
    return {"net": float(x.sum()), "per_yr": float(x.sum()) / yrs, "years": yrs, "max_dd": mdd,
            "roc30": 30.0 * (x.sum() / yrs) / mdd if mdd > 0 else float("nan"), "dd5": float(r["dd5_usd"]),
            "one_episode": bool(r["one_episode"]), "dd_pct_peak": float(dd_pct_peak(s, start=100_000)),
            "sortino": float(x.mean() / down * np.sqrt(252.0)) if down > 0 else float("nan")}


def main(key):
    run, d = run_doc(key)
    v = d["validate"]
    w = v["windows"]
    sess = "rth" if str(d["data_source"]).endswith("rth") else "eth"
    M = find_master(d["instrument"], d["timeframe"], sess, d["data_source"])
    # the validate's own champion read (selection.candidates[].cal) runs on the PRE-lockbox window and slices by ENTRY bar
    A = load_master_arrays(M, date_from=d["date_from"], date_to=w["optimize"][1])
    idx = pd.DatetimeIndex(A["index"])
    idxn = idx.tz_localize(None)
    fp = os.path.join(REPO, "augur_strategies", d["strategy"])
    m = types.ModuleType("ttm_crownwf_%s" % run)
    m.__file__ = fp
    exec(compile(open(fp, encoding="utf-8").read(), fp, "exec"), m.__dict__)
    P = dict(v["champion"])
    defaults = {k: s.get("default") for k, s in getattr(m, "DEFAULT_PARAMS", {}).items()}
    res = {"run": int(run), "strategy": d["strategy"], "strategy_sha256": sha(fp), "master": M.get("filename"),
           "master_sha256": sha(os.path.join(REPO, "augur_uploads", M["filename"])), "window": [d["date_from"], d["date_to"]],
           "windows": w, "champion": P, "file_defaults_differing": {k: defaults.get(k) for k in P if defaults.get(k) != P[k]},
           "cost_pts_run": d["cost_pts"], "multiplier": d["multiplier"]}
    r = run_backtest(m, instrument=d["instrument"], arrays=A, params=P, cost_pts=0.0, return_trades=True)
    mult = float(d["multiplier"])
    H = leg_rows(r, idx, float(d["cost_pts"]), mult)
    Rl = leg_rows(r, idx, REAL_COST_PTS[d["instrument"]], mult)
    # PARITY against the validate's own read of the crowned settings: the candidate whose params == champion, cal.is / cal.wf
    wf0, opt1 = pd.Timestamp(w["wf_split"]), pd.Timestamp(w["optimize"][1])
    cands = [c for c in (d.get("selection") or {}).get("candidates", []) if c.get("params") == P]
    st = cands[0].get("cal", {}) if cands else {}
    b0 = int(np.searchsorted(idxn, wf0))                   # first bar on/after wf_split = the validate's _wfB0
    mine = {"is": H[H["eb"] < b0], "wf": H[H["eb"] >= b0]}
    par = {}
    for nm in ("is", "wf"):
        x = st.get(nm) or {}
        par[nm] = {"stored_trades": x.get("num_trades"), "stored_pts": x.get("total_pnl"), "mine_trades": int(len(mine[nm])),
                   "mine_pts": round(float((mine[nm]["usd"] / mult).sum()), 4)}
        par[nm]["ok"] = bool(x) and par[nm]["mine_trades"] == x.get("num_trades") and abs(par[nm]["mine_pts"] - float(x.get("total_pnl"))) < 0.01
    res["parity"] = {"n_matching_candidates": len(cands), "crowned_flag": cands[0].get("crowned") if cands else None, **par,
                     "PARITY_OK": all(par[k]["ok"] for k in par)}
    # WF: trades entered in [wf_split, optimize end]; calendar = the master's ET dates in it UNION the kept exit dates
    keep = H["eb"] >= b0
    ex = H["exit"][keep].dt.normalize()
    cal = pd.DatetimeIndex(sorted(set(idxn.normalize()[(idxn >= wf0) & (idxn < opt1 + pd.Timedelta(days=1))]) | set(ex)))
    res["wf"] = {"from": str(wf0.date()), "to": str(opt1.date()), "trades": int(keep.sum()), "n_days": len(cal)}
    for lab, D in (("house_cost", H[keep]), ("real_cost", Rl[keep])):
        u = D["usd"]
        res["wf"][lab] = {"closed": four(daily_closed(D, cal), cal),
                          "valued_daily": four(daily_mtm(D, cal, np.asarray(A["close"], float), idxn, mult), cal),
                          "win_rate": float((u > 0).mean()), "avg_win_loss": [float(u[u > 0].mean()), float(-u[u <= 0].mean())]}
    res["store_wf_oos_stitched_refolds"] = v.get("wf_oos") and {k: v["wf_oos"].get(k) for k in ("from", "to", "net", "trades", "max_drawdown", "sortino", "mode")}
    s = json.dumps(res, indent=1, sort_keys=True, default=float)
    print(s)
    p = os.path.join(OUT, "ttm_crown_wf_%s.json" % run)
    open(p, "w", encoding="utf-8", newline="\n").write(s + "\n")
    print("output sha256", hashlib.sha256((s + "\n").encode()).hexdigest())


if __name__ == "__main__":
    main(sys.argv[1])
