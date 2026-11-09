"""STRONGBAR_1_0 POWER-FIRST GATE (owner order w119, MANAGER #197, 11-09). No trials, no tuning.

PRE-REGISTERED (frozen before any bar read; TBIS slot = NQ 5m RTH):
  Daily trend: prior day's RTH close vs SMA(trend_len) of daily closes -> above = longs only, below = shorts only.
  Signal bar (5m, bars starting 10:00..14:55 ET), all must hold, in the trend's direction:
    body/range >= b_min; close location (long: (C-L)/range, short: (H-C)/range) >= cl_min;
    range >= r_min x mean range of the prior 20 bars (expansion / follow-through bar);
    RVOL = bar volume / mean volume of the SAME bar-of-day over the prior 20 sessions >= v_min.
  Entry: next bar open, first signal of the day only. Stop: signal bar's far extreme (1R).
  ARM T (target): tgt_R x R or flat at the 15:55 bar close. ARM H (control 1): hold to 15:55 close, stop only.
  ARM X (control 2, random entry): same days, same direction, same R in points, entry at a random bar in the
  same window (seeded), hold to close with the stop - tests whether the CANDLE+VOLUME read adds anything over
  "be in the trend's direction intraday".
  Cost 0.533 pt round trip, $20/pt, 1 contract. Same bar touching stop and target = stop.
Central cell: trend_len 50, b_min 0.6, cl_min 0.8, r_min 1.5, v_min 1.5, tgt_R 2.
Hard bounds the file will carry: trend_len 20-200, b_min 0.3-0.9, cl_min 0.5-1.0, r_min 0.5-3.0, v_min 1.0-4.0,
tgt_R 1-4.
"""
import itertools
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.environ.get("EDGELOG_REPO_ROOT") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))
from augur_engine.data import find_master, load_master_arrays  # noqa: E402
from power_line import power_line, roc30  # noqa: E402

COST, M = 0.533, 20.0
LAST = "2026-09-16"
ORB314 = r"C:\EdgeLog\_anatomy_cache\frontier_combo\legs\X_orb314_raw.csv"
CENTRAL = dict(trend_len=50, b_min=0.6, cl_min=0.8, r_min=1.5, v_min=1.5, tgt=2.0)
GRID = dict(trend_len=[20, 50, 100], b_min=[0.5, 0.7], cl_min=[0.7, 0.9], r_min=[1.0, 2.0], v_min=[1.2, 2.0],
            tgt=[1.0, 2.0, 3.0])


def load():
    A = load_master_arrays(find_master("NQ", "5m", "rth", "db_noadj_rth"), date_from="2010-06-07", date_to=LAST)
    idx = pd.DatetimeIndex(A["index"])
    df = pd.DataFrame({k: np.asarray(A[k], float) for k in ("open", "high", "low", "close", "volume")}, index=idx)
    df["d"] = idx.date
    df["hm"] = idx.strftime("%H:%M")
    full = df.groupby("d")["hm"].agg(lambda s: s.iloc[0] == "09:30" and len(s) == 78)
    df = df[df["d"].map(full)]
    rng = df["high"] - df["low"]
    df["rng"] = rng
    df["rng20"] = rng.groupby(df["d"]).shift(1).rolling(20, min_periods=10).mean()  # prior bars, same day
    piv = df.pivot_table(index="d", columns="hm", values="volume")
    vavg = piv.shift(1).rolling(20, min_periods=15).mean()  # same bar-of-day, prior 20 sessions
    df["vavg"] = vavg.stack().reindex(pd.MultiIndex.from_arrays([df["d"], df["hm"]])).to_numpy()
    dc = df.groupby("d")["close"].last()
    return df, dc


def run(df, dc, trend_len, b_min, cl_min, r_min, v_min, tgt, arm="T", seed=7):
    sma = dc.rolling(trend_len).mean()
    up = (dc > sma).shift(1)
    rs = np.random.default_rng(seed)
    out = {}
    for d, g in df.groupby("d", sort=True):
        u = up.get(d)
        if u is None or pd.isna(u):
            continue
        side = 1.0 if u else -1.0
        o, h, l, c = (g[k].to_numpy() for k in ("open", "high", "low", "close"))
        rg = h - l
        hm = g["hm"].to_numpy()
        win = (hm >= "10:00") & (hm <= "14:55")
        with np.errstate(divide="ignore", invalid="ignore"):
            body = np.abs(c - o) / rg
            cl = (c - l) / rg if side > 0 else (h - c) / rg
            dirok = (c > o) if side > 0 else (c < o)
            sig = win & dirok & (body >= b_min) & (cl >= cl_min) & (rg >= r_min * g["rng20"].to_numpy()) \
                & (g["volume"].to_numpy() >= v_min * g["vavg"].to_numpy()) & (rg > 0)
        k = np.flatnonzero(sig)
        k = k[k + 1 < len(g)]
        if not len(k):
            out[d] = 0.0
            continue
        i = k[0]
        R = rg[i]
        if arm == "X":
            cand = np.flatnonzero(win[:-1])
            i = int(rs.choice(cand))
        e = o[i + 1]
        stop = e - side * R if arm == "X" else (l[i] if side > 0 else h[i])
        R = abs(e - stop)
        if R <= 0:
            out[d] = 0.0
            continue
        take = e + side * tgt * R
        px = c[-1]
        for j in range(i + 1, len(g)):
            if (side > 0 and l[j] <= stop) or (side < 0 and h[j] >= stop):
                px = stop
                break
            if arm == "T" and ((side > 0 and h[j] >= take) or (side < 0 and l[j] <= take)):
                px = take
                break
        out[d] = (side * (px - e), 1)
    return out


def summ(rec, years):
    pts = [v[0] for v in rec.values() if isinstance(v, tuple)]
    n = len(pts)
    gw, gl = sum(p for p in pts if p > 0), -sum(p for p in pts if p < 0)
    daily = pd.Series({d: ((v[0] - COST) * M if isinstance(v, tuple) else 0.0) for d, v in rec.items()}).sort_index()
    return dict(n=n, per_yr=n / years, g_c=(gw - gl) / (n * COST) if n else np.nan,
                pf=(gw - n * COST / 2) / (gl + n * COST / 2) if n else np.nan,
                net_yr=daily.sum() / years, roc30=float(roc30(daily.to_numpy()[None, :], years)[0]), daily=daily)


def main():
    df, dc = load()
    years = (pd.Timestamp(dc.index[-1]) - pd.Timestamp(dc.index[0])).days / 365.25
    print("NQ 5m RTH %s .. %s  sessions %d  years %.2f" % (dc.index[0], dc.index[-1], len(dc), years))
    arms = {a: summ(run(df, dc, arm=a, **CENTRAL), years) for a in ("T", "H")}
    xs = [summ(run(df, dc, arm="X", seed=s, **CENTRAL), years) for s in range(20)]
    for a, r in arms.items():
        print("ARM %s  n %5d (%5.1f/yr)  gross/cost %6.2f  net $/yr %8.0f  ROC@30k %6.2f"
              % (a, r["n"], r["per_yr"], r["g_c"], r["net_yr"], r["roc30"]))
    xr = np.array([x["roc30"] for x in xs])
    xg = np.array([x["g_c"] for x in xs])
    print("ARM X random entry (20 seeds): gross/cost median %.2f [%.2f..%.2f]  ROC@30k median %.2f [%.2f..%.2f]"
          % (np.median(xg), xg.min(), xg.max(), np.median(xr), xr.min(), xr.max()))
    best = arms["T"] if arms["T"]["roc30"] >= arms["H"]["roc30"] else arms["H"]
    a, b = best["daily"], xs[0]["daily"].reindex(best["daily"].index).fillna(0.0)
    yrs = sorted({pd.Timestamp(d).year for d in a.index})
    pos = beat = 0
    print("\nYEAR   best-arm$  random$")
    for y in yrs:
        m = np.array([pd.Timestamp(d).year == y for d in a.index])
        pos += a[m].sum() > 0
        beat += a[m].sum() > b[m].sum()
        print("%d %9.0f %9.0f" % (y, a[m].sum(), b[m].sum()))
    print("folds: best arm > 0 in %d of %d; beats random (seed 0) in %d of %d" % (pos, len(yrs), beat, len(yrs)))
    pl = power_line(a.to_numpy(), b.to_numpy(), years)
    print("power line lead vs random: 80%% line %.2f  observed %.2f" % (pl["line_80pct"], best["roc30"] - xs[0]["roc30"]))
    o = pd.read_csv(ORB314, parse_dates=["date"])
    o = o[o["trades"] > 0]
    o314 = set(o["date"].dt.date)
    td = [d for d, v in arms["T"]["daily"].items() if v != 0.0]
    print("#314 overlap: %d of %d trade days (%.0f%%)" % (sum(d in o314 for d in td), len(td),
                                                         100.0 * sum(d in o314 for d in td) / max(len(td), 1)))
    print("\nGRID (spread only): trend b cl r v tgt -> n/yr g/c(T) ROC30(T) ROC30(H)")
    rows = []
    for p in itertools.product(*GRID.values()):
        kw = dict(zip(GRID, p))
        t, hh = summ(run(df, dc, arm="T", **kw), years), summ(run(df, dc, arm="H", **kw), years)
        rows.append((t["per_yr"], t["g_c"], t["roc30"], hh["roc30"]))
        print("%3d %.1f %.1f %.1f %.1f %.0fR -> %5.1f %6.2f %6.2f %6.2f" % (p + rows[-1]))
    r = np.array(rows)
    ok = r[:, 0] >= 50
    print("grid: %d cells, %d with >=50 trades/yr; ROC30 T median %.2f, H median %.2f; cells >=15 & >=50/yr: T %d H %d"
          % (len(r), ok.sum(), np.nanmedian(r[:, 2]), np.nanmedian(r[:, 3]),
             ((r[:, 2] >= 15) & ok).sum(), ((r[:, 3] >= 15) & ok).sum()))


if __name__ == "__main__":
    main()
