"""w119 CANDLE-RVOL power-first gate, ES 5m RTH db_noadj_rth, preWF 2010-06-07..2016-06-29, 1 contract.
Daily trend: prior close vs SMA50 of daily closes (above = longs only, below = shorts only).
Signal bar 10:00-14:00 ET: body/range >= 0.6, close in the outer 25% of the bar in trend direction, relative volume
(bar volume / mean same-time volume over last 20 sessions) >= 1.5, close on trend side of session VWAP.
One trade per session, fill next open. Stop = signal bar extreme (floor 1 pt). Arms: TGT = 2R limit (through by 1 tick)
+ flat at 15:55 open; HOLD = stop only, out at the session close. Control = random bar in the window on a matching
trend-side session, same exits, 200 draws.
"""
import numpy as np
import pandas as pd
from augur_engine.data import find_master, load_master_arrays

BODY, CLOC, RV, LRV, SMA, T = 0.6, 0.25, 1.5, 20, 50, 2.0
COST, CO, PV, TICK = 0.613, 0.113, 50.0, 0.25
m = find_master("ES", "5m", "rth", "db_noadj_rth")
W = load_master_arrays(m, date_from="2010-03-01", date_to="2016-06-29")
ix = pd.DatetimeIndex(W["index"]).tz_convert("America/New_York").tz_localize(None)
df = pd.DataFrame({k: W[k] for k in ("open", "high", "low", "close", "volume")}, index=ix)
df["d"], df["t"] = ix.normalize(), ix.strftime("%H:%M")
dc = df.groupby("d").close.last()
trend = np.sign(dc - dc.rolling(SMA).mean()).shift(1)
df["tr"] = df.d.map(trend)
tp = (df.high + df.low + df.close) / 3
df["vwap"] = (tp * df.volume).groupby(df.d).cumsum() / df.volume.groupby(df.d).cumsum().replace(0, np.nan)
pv = df.pivot_table(index="d", columns="t", values="volume")
avg = pv.rolling(LRV, min_periods=LRV).mean().shift(1)
df["rv"] = df.volume.values / avg.stack().reindex(pd.MultiIndex.from_arrays([df.d, df.t])).values
rng_ = (df.high - df.low).replace(0, np.nan)
df["body"] = (df.close - df.open).abs() / rng_
df["cl"] = (df.close - df.low) / rng_
df = df[df.d >= pd.Timestamp("2010-06-07")]
O, H, L, C = (df[c].values for c in ("open", "high", "low", "close"))
T_ = df.t.values; D = df.d.values
starts = np.r_[0, np.flatnonzero(D[1:] != D[:-1]) + 1]; ends = np.r_[starts[1:], len(df)]


def trade(i0, n, j, side, sig_ext, arm):
    e = i0 + j + 1
    if e >= i0 + n:
        return None
    ep = O[e]; R = max(abs(ep - sig_ext), 1.0); stop = ep - side * R; tg = ep + side * T * R
    for b in range(e, i0 + n):
        if arm == "TGT" and T_[b] >= "15:55":
            return side * (O[b] - ep)
        if (side > 0 and L[b] <= stop) or (side < 0 and H[b] >= stop):
            px = stop if (side > 0 and O[b] > stop) or (side < 0 and O[b] < stop) else O[b]
            return side * (px - ep)
        if arm == "TGT" and ((side > 0 and H[b] >= tg + TICK) or (side < 0 and L[b] <= tg - TICK)):
            return side * (tg - ep)
    return side * (C[i0 + n - 1] - ep)


sig = {"TGT": [], "HOLD": []}; win = []
for i0, i1 in zip(starts, ends):
    n = i1 - i0; s = df.iloc[i0:i1]; side = s.tr.iloc[0]
    if not side or np.isnan(side):
        continue
    w = np.flatnonzero((s.t.values >= "10:00") & (s.t.values <= "14:00"))
    win.append((i0, n, w, int(side), D[i0]))
    for j in w:
        r = s.iloc[j]
        okc = r.cl >= 1 - CLOC if side > 0 else r.cl <= CLOC
        okv = r.close > r.vwap if side > 0 else r.close < r.vwap
        if r.body >= BODY and okc and r.rv >= RV and okv and np.sign(r.close - r.open) == side:
            ext = r.low if side > 0 else r.high
            for a in sig:
                g = trade(i0, n, j, int(side), ext, a)
                if g is not None:
                    sig[a].append((D[i0], int(side), g))
            break
yrs = (pd.Timestamp("2016-06-29") - pd.Timestamp("2010-06-07")).days / 365.25
sess = pd.Index(sorted(set(D)))
rs = np.random.default_rng(11)
for a, tl in sig.items():
    t = pd.DataFrame(tl, columns=["d", "side", "g"])
    # random-entry control: same number of trades, random trend-side session + random bar in window, same exits
    ctrl = []
    for _ in range(200):
        pick = rs.choice(len(win), len(t), replace=False); gs = []
        for k in pick:
            i0, n, w, sd, _d = win[k]; j = rs.choice(w)
            ext = L[i0 + j] if sd > 0 else H[i0 + j]
            g = trade(i0, n, j, sd, ext, a)
            if g is not None:
                gs.append(g)
        ctrl.append(np.mean(gs))
    ctrl = np.array(ctrl)
    print("%s: trades %d (%.0f/yr, long %d short %d) gross/trade %.3f pts, gross/cost %.2f, win %.1f%% | random-entry gross %.3f +/- %.3f, pctile %.0f%%" % (
        a, len(t), len(t) / yrs, (t.side > 0).sum(), (t.side < 0).sum(), t.g.mean(), t.g.mean() / COST, 100 * (t.g > 0).mean(),
        ctrl.mean(), ctrl.std(), 100 * (ctrl < t.g.mean()).mean()))
    for c in (COST, CO):
        dly = (t.assign(n=(t.g - c) * PV).groupby("d").n.sum()).reindex(sess, fill_value=0.0)
        nb = len(dly) // 20; blk = dly.values[: nb * 20].reshape(nb, 20).sum(1)
        se = np.std([rs.choice(blk, nb).sum() for _ in range(2000)]) / yrs; net = dly.sum() / yrs
        yr = dly.groupby(dly.index.year).sum()
        print("   cost %.3f: net $%.0f/yr, SE $%.0f, t %.2f, MDE80 $%.0f, years+ %d/%d" % (c, net, se, net / se, 2.8 * se, (yr > 0).sum(), len(yr)))
