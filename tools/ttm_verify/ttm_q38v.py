"""TTM (house verifier, MANAGER #89 / #108): BLIND re-check of Q38's CALIBRATION - the harm bands of the three live Webull legs
(ORB_R6, NOISE_382, DIP_424F) - plus each leg's four numbers at the owner's real cost at its live unit. Built from
docs/PREDATA_frontier_wbbands_2026-10-10.txt (+ _add1, which touches only the forward read) and the strategy files; Q38's
q38_webull_bands.py / q38_bands.json are NOT read until this output's sha256 is posted. The band math follows the note's
"q35_recent_bands.calibrate exactly" (a house function, read) with tools/power_line.stationary_indices; the per-leg daily
series - the part a verifier can get wrong independently - is mine. The forward read is NOT re-done.
Prereg: prereg/ttm-verify-q38 (docs/PREREG_TTM_VERIFY_Q38_2026-10-14.txt). Writes only into C:/EdgeLog/_anatomy_cache/ttm_q38v/."""
import hashlib
import json
import os
import sys
import types

import numpy as np
import pandas as pd

REPO = "C:/Users/xride/OneDrive/Desktop/EDGE-LOG"
OUT = "C:/EdgeLog/_anatomy_cache/ttm_q38v"
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "tools"))
os.chdir(REPO)
os.environ["AUGUR_TRIAL_CACHE"] = "0"
from augur_engine.data import list_masters, load_master_arrays   # noqa: E402
from augur_engine.engine import run_backtest                     # noqa: E402
from augur_engine.drawdowns import dd5, dd_pct_peak               # noqa: E402
from power_line import stationary_indices                          # noqa: E402
from api import cloud_signal as CS                                # noqa: E402
from api.paper import ORB_314                                     # noqa: E402

MASTER = "master_ac263357.csv"
PIN_MASTER = "782dabdd7dd7d265c9a31626f03c6940cdaaf4d7511da95bf8a8efc41fba5a1d"
CAL = (pd.Timestamp("2022-07-01"), pd.Timestamp("2025-06-29"))
WF = (pd.Timestamp("2016-06-30"), pd.Timestamp("2025-06-30"))
COST_SH = 0.02                       # $ a share a round trip (0.01 a side) = the owner's real cost on Webull ($0 commission)
UNIT = {"ORB_R6": 10.0, "NOISE_382": 10.0, "DIP_424F": 6.0}
WEEK_ROWS = 5
SEED, PATHS, BLOCK = 20261009, 2000, 20


def sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def load_mod(fn):
    fp = os.path.join(REPO, "augur_strategies", fn)
    m = types.ModuleType("ttm_q38v_" + fn.replace(".", "_"))
    m.__file__ = fp
    exec(compile(open(fp, encoding="utf-8").read(), fp, "exec"), m.__dict__)
    return m, sha(fp)


def leg_trades(A, idx):
    """per leg: DataFrame(entry, exit (ET timestamps), unit_usd net of real cost, per_share gross, size)."""
    out, shas = {}, {}
    m, shas["ORB_3_6_R6.py"] = load_mod("ORB_3_6_R6.py")
    r = run_backtest(m, instrument="QQQ", arrays=A, params=dict(ORB_314), cost_pts=0.0, return_trades=True)
    T = r["trades"]
    g = np.array([float(t[2]) for t in T])
    out["ORB_R6"] = pd.DataFrame({"entry": idx[[t[0] for t in T]], "exit": idx[[t[1] for t in T]], "per_share": g,
                                  "size": 1.0, "unit_usd": UNIT["ORB_R6"] * (g - COST_SH)})
    m, shas["NOISE_1_8_CT304.py"] = load_mod("NOISE_1_8_CT304.py")
    r = run_backtest(m, instrument="QQQ", arrays=A, params=dict(CS.NOISE_382_PARAMS), cost_pts=0.0, return_trades=True)
    T, s, k = r["trades"], np.asarray(r["trade_sizes"], float), float(r["size_cost_pts"])
    pts = np.array([float(t[2]) for t in T])
    raw = (pts + (s - 1.0) * k) / s                                  # undo the plugin's size fold: pts = s*raw - (s-1)*k
    out["NOISE_382"] = pd.DataFrame({"entry": idx[[t[0] for t in T]], "exit": idx[[t[1] for t in T]], "per_share": raw,
                                     "size": s, "unit_usd": UNIT["NOISE_382"] * s * (raw - COST_SH)})
    m, shas["NQDIP_1_1.py"] = load_mod("NQDIP_1_1.py")
    P = dict(CS.DIP_424_PARAMS, asset="ETF", cost_bps=0.0)
    r = run_backtest(m, instrument="QQQ", arrays=A, params=P, cost_pts=0.0, return_trades=True)
    T = r["trades"]
    ps = np.array([float(t[2]) / (P["notional"] / float(t[4])) for t in T])   # $ per share
    chk = np.array([float(t[5]) - float(t[4]) for t in T])              # exit - entry price, a cross-check of ps
    out["DIP_424F"] = pd.DataFrame({"entry": idx[[t[0] for t in T]], "exit": idx[[t[1] for t in T]], "per_share": ps,
                                    "size": 1.0, "unit_usd": UNIT["DIP_424F"] * (ps - COST_SH), "px_move": chk})
    return out, shas


def daily(df, days):
    d = pd.DatetimeIndex(df["exit"]).tz_localize(None).normalize()
    return pd.Series(df["unit_usd"].to_numpy(float), index=d).groupby(level=0).sum().reindex(days, fill_value=0.0)


def calibrate(x, H):
    """the note's 'q35_recent_bands.calibrate exactly', with A1 checked every WEEK_ROWS rows."""
    checks = np.arange(WEEK_ROWS, H + 1, WEEK_ROWS)
    mu, sd = float(x.mean()), float(x.std(ddof=1))
    idx = stationary_indices(len(x), PATHS, BLOCK, np.random.default_rng(SEED))
    reps = int(np.ceil(H / idx.shape[1]))
    I = np.concatenate([idx] * reps, axis=1)[:, :H] if idx.shape[1] < H else idx[:, :H]
    Pm = x[I]
    S = np.cumsum(Pm - mu, axis=1)[:, checks - 1]
    c = float(-np.quantile((S / (sd * np.sqrt(checks))).min(axis=1), 0.025))
    q = np.cumsum(Pm, axis=1)
    dd = (np.maximum.accumulate(np.concatenate([np.zeros((Pm.shape[0], 1)), q], axis=1), axis=1)[:, 1:] - q).max(axis=1)
    Dl = float(np.quantile(dd, 0.975))
    Q = Pm - mu
    Sz = np.cumsum(Q - mu, axis=1)[:, checks - 1] / (sd * np.sqrt(checks))
    t1 = np.where((Sz < -c).any(axis=1), checks[np.argmax(Sz < -c, axis=1)], np.inf)
    qz = np.cumsum(Q, axis=1)
    ddz = (np.maximum.accumulate(np.concatenate([np.zeros((Q.shape[0], 1)), qz], axis=1), axis=1)[:, 1:] - qz)[:, checks - 1]
    t2 = np.where((ddz > Dl).any(axis=1), checks[np.argmax(ddz > Dl, axis=1)], np.inf)
    return {"mu": mu, "sd": sd, "c": c, "A2": Dl, "power_36m": float((np.minimum(t1, t2) <= H).mean()),
            "mu_per_year": mu * len(x) / ((CAL[1] - CAL[0]).days / 365.25)}


def four(x, days):
    x = np.asarray(x, float)
    eq = np.cumsum(x)
    mdd = float(np.max(np.maximum.accumulate(np.concatenate([[0.0], eq]))[1:] - eq))
    yrs = (days[-1] - days[0]).days / 365.25
    down = np.sqrt(np.mean(np.minimum(x, 0.0) ** 2))
    s = pd.Series(x, index=days)
    r = dd5(s)
    return {"per_yr": float(x.sum()) / yrs, "max_dd": mdd, "roc30": 30.0 * (x.sum() / yrs) / mdd if mdd > 0 else float("nan"),
            "dd5": float(r["dd5_usd"]), "one_episode": bool(r["one_episode"]), "dd_pct_peak": float(dd_pct_peak(s, start=100_000)),
            "sortino": float(x.mean() / down * np.sqrt(252.0)), "years": yrs}


def main():
    row = [x for x in list_masters() if x.get("filename") == MASTER]
    assert len(row) == 1 and sha(os.path.join(REPO, "augur_uploads", MASTER)) == PIN_MASTER
    A = load_master_arrays(row[0])
    idx = pd.DatetimeIndex(A["index"])
    sessions = pd.DatetimeIndex(sorted(set(idx.tz_localize(None).normalize())))
    L, shas = leg_trades(A, idx)
    res = {"file_sha256": shas, "unit_shares": UNIT, "cost_per_share_rt": COST_SH}
    cal_days = sessions[(sessions >= CAL[0]) & (sessions <= CAL[1])]
    H = int(round(36 * len(cal_days) / ((CAL[1] - CAL[0]).days / 30.4375)))
    res["cal_rows"], res["H_rows_36m"] = len(cal_days), H
    for nm, df in L.items():
        e = {"n_trades_all": int(len(df)), "first_entry": str(df["entry"].min()), "last_exit": str(df["exit"].max())}
        if "px_move" in df:
            e["dip_per_share_vs_px_move_maxabs"] = float(np.max(np.abs(df["per_share"] - df["px_move"])))
        if nm == "NOISE_382":
            e["size_counts"] = {str(k): int(v) for k, v in df["size"].value_counts().sort_index().items()}
        xd = pd.DatetimeIndex(df["exit"]).tz_localize(None).normalize()
        e["n_trades_cal"] = int(((xd >= CAL[0]) & (xd <= CAL[1])).sum())
        e["band"] = calibrate(daily(df, cal_days).to_numpy(float), H)
        first = pd.DatetimeIndex(df["entry"]).tz_localize(None).normalize().min()
        wf_days = sessions[(sessions >= max(WF[0], first)) & (sessions <= WF[1])]
        wk = (xd >= wf_days[0]) & (xd <= WF[1])
        e["n_trades_wf"] = int(wk.sum())
        e["wf_four_at_unit_real_cost"] = four(daily(df, wf_days).to_numpy(float), wf_days)
        e["wf_window"] = [str(wf_days[0].date()), str(wf_days[-1].date())]
        w = df[wk]["unit_usd"]
        e["wf_win_rate"] = float((w > 0).mean())
        e["wf_avg_win_loss"] = [float(w[w > 0].mean()), float(-w[w <= 0].mean())]
        res[nm] = e
    s = json.dumps(res, indent=1, sort_keys=True, default=float)
    print(s)
    open(os.path.join(OUT, "ttm_q38v.json"), "w", encoding="utf-8", newline="\n").write(s + "\n")
    print("output sha256", hashlib.sha256((s + "\n").encode()).hexdigest())


if __name__ == "__main__":
    main()
