"""w118 NOISE-BRK-R power-first gate: one fixed mid-bounds config, preWF 2010-06-07..2016-06-29, 1 contract.
Entry: first 5m close outside the noise band (open +/- k * mean |close/open-1| at the same time of day, last L sessions),
10:00-13:30 ET, close on the trade side of session VWAP, fill next open. Stop m*ATR14 (floor 8 pts), limit T*R
(fills only if traded through by 1 tick), time stop H bars, flat at the 15:30 bar open. One trade per session.
"""
import numpy as np
import pandas as pd
from augur_engine.data import find_master, load_master_arrays

L, K, M, T, H, START, LAST, FLAT = 14, 1.0, 1.0, 2, 24, "10:00", "13:30", "15:30"
COST, CO, PV, TICK = 0.783, 0.283, 20.0, 0.25

m = find_master("NQ", "5m", "rth", "db_noadj_rth")
W = load_master_arrays(m, date_from="2010-06-07", date_to="2016-06-29")
ix = pd.DatetimeIndex(W["index"]).tz_convert("America/New_York").tz_localize(None)
df = pd.DataFrame({k: W[k] for k in ("open", "high", "low", "close", "volume")}, index=ix)
df["d"], df["t"] = ix.normalize(), ix.strftime("%H:%M")
g = df.groupby("d")
df["o0"] = g["open"].transform("first")
df["mv"] = (df["close"] / df["o0"] - 1).abs()
tp = (df.high + df.low + df.close) / 3
df["vwap"] = (tp * df.volume).groupby(df.d).cumsum() / df.volume.groupby(df.d).cumsum().replace(0, np.nan)
pc = df.close.shift()
tr = np.maximum(df.high - df.low, np.maximum((df.high - pc).abs(), (df.low - pc).abs()))
df["atr"] = tr.rolling(14).mean()
piv = df.pivot_table(index="d", columns="t", values="mv")
band = piv.rolling(L, min_periods=L).mean().shift(1)
df["band"] = band.stack().reindex(pd.MultiIndex.from_arrays([df.d, df.t])).values

O, Hh, Lo, C = (df[c].values for c in ("open", "high", "low", "close"))
trades = []
for d, sub in df.groupby("d"):
    p = np.flatnonzero(df.d.values == d) if False else None
    i0 = df.index.get_loc(sub.index[0]); n = len(sub)
    done = False
    for j in range(n - 1):
        r = sub.iloc[j]
        if done or r.t < START or r.t > LAST or np.isnan(r.band) or np.isnan(r.atr):
            continue
        up, dn = r.o0 * (1 + K * r.band), r.o0 * (1 - K * r.band)
        side = 1 if (r.close > up and r.close > r.vwap) else -1 if (r.close < dn and r.close < r.vwap) else 0
        if not side:
            continue
        done = True
        e = i0 + j + 1; ep = O[e]; R = max(M * r.atr, 8.0)
        stop, tgt = ep - side * R, ep + side * T * R
        xp = None
        for b in range(e, i0 + n):
            tt = sub.t.iloc[b - i0]
            if b - e >= H or tt >= FLAT:
                xp = O[b]; break
            if (side > 0 and Lo[b] <= stop) or (side < 0 and Hh[b] >= stop):
                xp = stop if b > e or (side > 0 and O[b] > stop) or (side < 0 and O[b] < stop) else O[b]; break
            if (side > 0 and Hh[b] >= tgt + TICK) or (side < 0 and Lo[b] <= tgt - TICK):
                xp = tgt; break
        if xp is None:
            xp = C[i0 + n - 1]
        trades.append((d, side, side * (xp - ep), R))
t = pd.DataFrame(trades, columns=["d", "side", "gross", "R"])
yrs = (pd.Timestamp("2016-06-29") - pd.Timestamp("2010-06-07")).days / 365.25
sess = pd.Index(sorted(df.d.unique()))
print("trades %d (%.0f/yr), long %d short %d" % (len(t), len(t) / yrs, (t.side > 0).sum(), (t.side < 0).sum()))
print("gross/trade %.3f pts, gross/cost %.2f, win %.1f%%, mean R %.1f" % (t.gross.mean(), t.gross.mean() / COST, 100 * (t.gross > 0).mean(), t.R.mean()))
rng = np.random.default_rng(7)
for c in (COST, CO):
    dly = (t.assign(n=(t.gross - c) * PV).groupby("d").n.sum()).reindex(sess, fill_value=0.0)
    nb = len(dly) // 20; blk = dly.values[: nb * 20].reshape(nb, 20).sum(1)
    bs = [rng.choice(blk, nb).sum() for _ in range(2000)]
    se = np.std(bs) / yrs; net = dly.sum() / yrs
    dd = (dly.cumsum().cummax() - dly.cumsum()).max()
    pf = t.gross[t.gross > c].sub(c).sum() / -t.gross[t.gross < c].sub(c).sum()
    yr = dly.groupby(dly.index.year).sum()
    print("cost %.3f: net $%.0f/yr, SE $%.0f, t %.2f, MDE80 $%.0f, PF %.2f, maxDD $%.0f, years+ %d/%d %s" % (
        c, net, se, net / se, 2.8 * se, pf, dd, (yr > 0).sum(), len(yr), dict(yr.round(0))))
