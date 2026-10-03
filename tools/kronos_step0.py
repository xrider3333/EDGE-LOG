"""KRONOS Step 0 (2026-10-01, owner GO via MANAGER #40) - docs/PREREG_kronos_step0_2026-10-01.md (a341da5d).

Does Kronos forecast the next session's RTH range better than free baselines (TRAIL5, EWMA, HAR, overnight)?
Score = QLIKE on squared ranges; one scale factor per model fitted on H1 only; Diebold-Mariano (Newey-West 5).

    python tools/kronos_step0.py baselines      build sessions + the four free forecasts, print their scores
    python tools/kronos_step0.py kronos         (needs C:\\EdgeLog\\kronos\\ - the owner-approved download) run
                                               Kronos for seeds 1-5 and judge the pre-registered bar
Run from the shared checkout (masters registry) or set EDGELOG_ROOT to it.
"""
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.environ.get("EDGELOG_ROOT") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

OUT = r"C:\EdgeLog\kronos"
T0, H2_0, T1 = pd.Timestamp("2024-07-01"), pd.Timestamp("2025-07-01"), pd.Timestamp("2026-09-30")
HAR_FIT = (pd.Timestamp("2010-07-01"), pd.Timestamp("2024-06-28"))
MIN_RTH_BARS, LAMBDA, CTX, PATHS, SEEDS = 70, 0.94, 512, 20, (1, 2, 3, 4, 5)
BASELINES = ("TRAIL5", "EWMA", "HAR", "OVN")


def sessions(sym):
    """One row per session D: 24-hour daily bar (18:00 D-1 .. 16:55 D), RTH range (09:30..15:55), overnight range
    (18:00 D-1 .. 09:25 D), RTH bar count. Roll-corrected 5m 24-hour master ADJ_<SYM>_5m_ETH (db_adj_eth)."""
    from augur_engine.data import find_master, load_master_arrays
    A = load_master_arrays(find_master(sym, "5m", "eth", "db_adj_eth"), date_from="2009-01-01")
    idx = pd.DatetimeIndex(A["index"])
    idx = idx.tz_convert("US/Eastern").tz_localize(None) if idx.tz is not None else idx
    df = pd.DataFrame({k: np.asarray(A[k], float) for k in ("open", "high", "low", "close", "volume")}, index=idx)
    df["sess"] = (df.index + pd.Timedelta(hours=6)).normalize()        # 18:00 belongs to the next session
    tm = df.index.hour * 60 + df.index.minute
    rth = (tm >= 570) & (tm <= 955)                                     # 09:30 .. 15:55 bar opens
    ovn = ~rth & ((tm >= 1080) | (tm < 570))                            # 18:00 .. 09:25
    g = df.groupby("sess")
    out = pd.DataFrame({"open": g.open.first(), "high": g.high.max(), "low": g.low.min(), "close": g.close.last(),
                        "volume": g.volume.sum()})
    r = df[rth].groupby("sess")
    out["rth_range"] = r.high.max() - r.low.min()
    out["rth_bars"] = r.size()
    o = df[ovn].groupby("sess")
    out["ovn_range"] = o.high.max() - o.low.min()
    out = out[out.index.dayofweek < 5]
    out["rth_bars"] = out.rth_bars.fillna(0)
    out["valid"] = out.rth_bars >= MIN_RTH_BARS
    return out


def baselines(S):
    """Each forecast for session D uses only sessions before D (OVN: D's own overnight, known at 09:30)."""
    v = S[S.valid].copy()
    R = v.rth_range
    f = pd.DataFrame(index=v.index)
    f["TRAIL5"] = R.shift(1).rolling(5).mean()
    ew = np.full(len(R), np.nan)
    acc = float((R.iloc[:20] ** 2).mean())
    for i in range(len(R)):
        ew[i] = acc                                                     # value BEFORE session i
        acc = LAMBDA * acc + (1 - LAMBDA) * float(R.iloc[i]) ** 2
    ew[:21] = np.nan
    f["EWMA"] = np.sqrt(ew)
    lr = np.log(R)
    X = pd.DataFrame({"d": lr.shift(1), "w": lr.shift(1).rolling(5).mean(), "m": lr.shift(1).rolling(22).mean()})
    fit = X.notna().all(axis=1) & (v.index >= HAR_FIT[0]) & (v.index <= HAR_FIT[1])
    Xm = np.column_stack([np.ones(int(fit.sum())), X[fit].to_numpy()])
    beta = np.linalg.lstsq(Xm, lr[fit].to_numpy(), rcond=None)[0]
    f["HAR"] = np.exp(beta[0] + X.to_numpy() @ beta[1:])
    f["OVN"] = v.ovn_range
    f["target"] = R
    return f, beta


def qlike(target, fc):
    q = (np.asarray(target, float) ** 2) / (np.asarray(fc, float) ** 2)
    return q - np.log(q) - 1.0


def scale_h1(target, fc, h1):
    """QLIKE-optimal single scale on H1: k^2 = mean(s / h) over H1 (closed form)."""
    k2 = float(np.mean((target[h1] ** 2) / (fc[h1] ** 2)))
    return np.sqrt(k2)


def dm_onesided(lk, lb, lags=5):
    """Diebold-Mariano on d = Kronos loss - baseline loss, Newey-West variance; p = P(no better | data)."""
    from scipy.stats import norm
    d = np.asarray(lk, float) - np.asarray(lb, float)
    n, m = len(d), d.mean()
    e = d - m
    var = e @ e / n
    for L in range(1, lags + 1):
        var += 2 * (1 - L / (lags + 1)) * (e[L:] @ e[:-L]) / n
    t = m / np.sqrt(var / n)
    return float(t), float(norm.cdf(t))


def score(f, models):
    """Mean QLIKE and MSE of log range per half, after the H1-fitted scale."""
    tst = f[(f.index >= T0) & (f.index <= T1)].dropna(subset=list(models) + ["target"])
    h1 = (tst.index < H2_0)
    res, scaled = {}, {}
    for m in models:
        k = scale_h1(tst.target.to_numpy(), tst[m].to_numpy(), h1)
        fc = k * tst[m].to_numpy()
        scaled[m] = fc
        L = qlike(tst.target.to_numpy(), fc)
        mse = (np.log(tst.target.to_numpy()) - np.log(fc)) ** 2
        res[m] = dict(k=k, H1=float(L[h1].mean()), H2=float(L[~h1].mean()),
                      mse_H1=float(mse[h1].mean()), mse_H2=float(mse[~h1].mean()))
    return tst, h1, res, scaled


def run_baselines():
    for sym in ("NQ", "ES"):
        S = sessions(sym)
        f, beta = baselines(S)
        os.makedirs(OUT, exist_ok=True)
        S.to_csv(os.path.join(OUT, f"sessions_{sym}.csv"))
        f.to_csv(os.path.join(OUT, f"baselines_{sym}.csv"))
        tst, h1, res, _ = score(f, BASELINES)
        print(f"{sym}: test sessions {len(tst)} (H1 {int(h1.sum())}, H2 {int((~h1).sum())}); HAR beta {np.round(beta, 3)}")
        for m, r in res.items():
            print(f"  {m:7s} scale {r['k']:.3f}  QLIKE H1 {r['H1']:.4f}  H2 {r['H2']:.4f}  | MSE(log) H1 {r['mse_H1']:.4f}  H2 {r['mse_H2']:.4f}")


if __name__ == "__main__":
    if sys.argv[1:] == ["baselines"]:
        run_baselines()
    else:
        raise SystemExit("usage: kronos_step0.py baselines | kronos")
