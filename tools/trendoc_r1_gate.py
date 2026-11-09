"""TRENDOC_1_0 POWER-FIRST GATE (w120, MANAGER #199, 11-09). No trials, no tuning.

Motivation: STRONGBAR r1 showed random intraday entry IN THE DAILY TREND DIRECTION earned ROC@30k ~10 on NQ 5m,
while the candle trigger lost it. Test the plain version directly and ask whether the trend filter adds anything
over always-long intraday beta.

PRE-REGISTERED (frozen before data):
  Direction: prior day's RTH close vs SMA(trend_len) of daily closes (strictly prior days) -> long above, short below.
  Entry: open of the 09:35 bar (skips the opening auction print). Exit: 15:55 bar close. Stop: entry -/+ k_stop x
  ATR14 daily (prior days). Optional skip: gap (09:30 open vs prior close) AGAINST the trend > g_skip x ATR (0 = off).
  CONTROL A: always long, same entry/exit/stop.   CONTROL B: random direction (20 seeds), same rules.
  Cost 0.533 pt, $20/pt, 1 contract. Gate: gross/cost, ROC@30k >= 15, beat CONTROL A by year (count folds),
  bootstrap power line on the lead over A.
Central: trend_len 50, k_stop 1.0, g_skip 0.
Hard bounds the file will carry: trend_len 10-250, k_stop 0.25-3.0, g_skip 0-2.0.
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
CENTRAL = dict(trend_len=50, k_stop=1.0, g_skip=0.0)
GRID = dict(trend_len=[10, 20, 50, 100, 200], k_stop=[0.5, 1.0, 2.0], g_skip=[0.0, 0.5])


def load():
    A = load_master_arrays(find_master("NQ", "5m", "rth", "db_noadj_rth"), date_from="2010-06-07", date_to=LAST)
    idx = pd.DatetimeIndex(A["index"])
    df = pd.DataFrame({k: np.asarray(A[k], float) for k in ("open", "high", "low", "close")}, index=idx)
    df["d"] = idx.date
    df["hm"] = idx.strftime("%H:%M")
    ok = df.groupby("d")["hm"].agg(lambda s: s.iloc[0] == "09:30" and len(s) == 78)
    df = df[df["d"].map(ok)]
    days = [(d, g) for d, g in df.groupby("d", sort=True)]
    dl = pd.DataFrame({"o": [g["open"].iloc[0] for _, g in days], "h": [g["high"].max() for _, g in days],
                       "l": [g["low"].min() for _, g in days], "c": [g["close"].iloc[-1] for _, g in days]},
                      index=[d for d, _ in days])
    pc = dl["c"].shift()
    tr = np.maximum(dl["h"] - dl["l"], np.maximum((dl["h"] - pc).abs(), (dl["l"] - pc).abs()))
    dl["atr"] = tr.rolling(14).mean().shift(1)
    dl["pc"] = pc
    paths = {d: (g["open"].to_numpy()[1], g["high"].to_numpy()[1:], g["low"].to_numpy()[1:], g["close"].to_numpy()[-1])
             for d, g in days}
    return dl, paths


def run(dl, paths, trend_len, k_stop, g_skip, mode="T", seed=0):
    sma = dl["c"].rolling(trend_len).mean()
    up = (dl["c"] > sma).shift(1)
    rs = np.random.default_rng(seed)
    out = {}
    for d in dl.index:
        a, u = dl.at[d, "atr"], up.get(d)
        if not np.isfinite(a) or u is None or pd.isna(u) or not np.isfinite(sma.shift(1).get(d, np.nan)):
            continue
        side = {"T": 1.0 if u else -1.0, "A": 1.0, "B": float(rs.choice([-1.0, 1.0]))}[mode]
        if mode == "T" and g_skip > 0 and side * (dl.at[d, "o"] - dl.at[d, "pc"]) < -g_skip * a:
            out[d] = 0.0
            continue
        e, hh, ll, cl = paths[d]
        stop = e - side * k_stop * a
        hit = (ll <= stop).any() if side > 0 else (hh >= stop).any()
        px = stop if hit else cl
        out[d] = side * (px - e)
    return out


def summ(rec, years):
    s = pd.Series(rec).sort_index()
    traded = s[s != 0.0] if (s == 0.0).sum() < len(s) else s
    n = int((s != 0.0).sum())
    g = s.sum()
    daily = (s - COST * (s != 0.0)) * M
    return dict(n=n, per_yr=n / years, g_c=g / (n * COST) if n else np.nan, net_yr=daily.sum() / years,
                roc30=float(roc30(daily.to_numpy()[None, :], years)[0]), daily=daily)


def main():
    dl, paths = load()
    years = (pd.Timestamp(dl.index[-1]) - pd.Timestamp(dl.index[0])).days / 365.25
    print("NQ 5m RTH %s .. %s  sessions %d  years %.2f" % (dl.index[0], dl.index[-1], len(dl), years))
    T = summ(run(dl, paths, **CENTRAL), years)
    A = summ(run(dl, paths, mode="A", **CENTRAL), years)
    B = [summ(run(dl, paths, mode="B", seed=s, **CENTRAL), years) for s in range(20)]
    for nm, r in (("TREND (central)", T), ("CONTROL A always-long", A)):
        print("%-22s n %5d (%5.1f/yr)  gross/cost %6.2f  net $/yr %8.0f  ROC@30k %6.2f"
              % (nm, r["n"], r["per_yr"], r["g_c"], r["net_yr"], r["roc30"]))
    br = np.array([b["roc30"] for b in B])
    print("CONTROL B random dir (20 seeds): ROC@30k median %.2f [%.2f..%.2f]" % (np.median(br), br.min(), br.max()))
    a, b = T["daily"], A["daily"].reindex(T["daily"].index).fillna(0.0)
    yrs = sorted({pd.Timestamp(d).year for d in a.index})
    pos = beat = 0
    print("\nYEAR   TREND$   LONG$")
    for y in yrs:
        m = np.array([pd.Timestamp(d).year == y for d in a.index])
        pos += a[m].sum() > 0
        beat += a[m].sum() > b[m].sum()
        print("%d %9.0f %9.0f" % (y, a[m].sum(), b[m].sum()))
    print("folds: TREND > 0 in %d of %d; beats always-long in %d of %d" % (pos, len(yrs), beat, len(yrs)))
    pl = power_line(a.to_numpy(), b.to_numpy(), years)
    print("power line lead vs always-long: 80%% line %.2f  observed %.2f" % (pl["line_80pct"], T["roc30"] - A["roc30"]))
    print("\nGRID (spread only): trend k_stop g_skip -> n/yr g/c net$/yr ROC30   [always-long ROC30 same k_stop]")
    rows = []
    for p in itertools.product(*GRID.values()):
        kw = dict(zip(GRID, p))
        t = summ(run(dl, paths, **kw), years)
        al = summ(run(dl, paths, mode="A", **kw), years)
        rows.append((t["roc30"], al["roc30"]))
        print("%3d %.2f %.1f -> %5.1f %6.2f %8.0f %6.2f   [%6.2f]" % (p + (t["per_yr"], t["g_c"], t["net_yr"],
                                                                         t["roc30"], al["roc30"])))
    r = np.array(rows)
    print("grid: %d cells; TREND ROC30 median %.2f, cells >=15: %d; beats always-long in %d of %d cells"
          % (len(r), np.nanmedian(r[:, 0]), (r[:, 0] >= 15).sum(), (r[:, 0] > r[:, 1]).sum(), len(r)))


if __name__ == "__main__":
    main()
