# TV SCALPER SCREEN 2 (MANAGER #187), PRE-WF rows only (to 2016-06-30); nothing tuned on WF or LB.
# A. Super Scalper 1_1, run #496 fold-5 config, entries re-priced as a LIMIT at the signal close, valid one bar, filled only if price
#    trades through by 1 tick; exits kept as run. Approximation: stops and targets are not re-based on the new fill.
# B. VWAP-RSI(3) NQ 5m: OUR READING of the public description, not the script (thresholds unknown): RSI(3) extreme with session
#    VWAP + EMA50 trend, next-open market entry, stop 1 ATR14, target 2 ATR14, <= 3 a day, flat at session end, stop first in a bar.
import json, os, sys
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import superscalper_validate_read as R
import superscalper_regime_r3 as S

OUT = r"C:\EdgeLog\_research_cache\tv_scalp\superscalper\screen2_r3.json"
TICK = 0.25
CUT = "2016-06-30"


def stats(p, cost, cal):
    return S.row(p, cal, cost, "pre-WF")


def scalper(m, load, run_backtest, params, cal):
    rows, offered = [], 0
    for d0, d1 in S.PERIODS:
        a = load(m, date_from=d0, date_to=d1)
        dd = R.bar_dates(a["index"])
        o, h, l, c = (np.asarray(a[k], float) for k in ("open", "high", "low", "close"))
        r = run_backtest(S.F11, arrays=a, master=m, params=dict(params), cost_pts=0.0, return_trades=True)
        for x in (r or {}).get("trade_detail") or []:
            offered += 1
            e, sd = int(x["entry_bar"]), int(x["side"])
            lim = c[int(x["signal_bar"])]
            through = l[e] <= lim - TICK if sd > 0 else h[e] >= lim + TICK
            if not through:
                continue
            fill = min(o[e], lim) if sd > 0 else max(o[e], lim)
            rows.append(dict(xday=dd[int(x["exit_bar"])], pts=float(x["pnl_pts"]) + (float(x["entry_price"]) - fill) * sd - S.RUN_COST))
        del a
    p = pd.DataFrame(rows)
    p["xday"] = pd.to_datetime(p.xday)
    return dict(offered=offered, filled=len(p), **{str(k): stats(p, k, cal) for k in S.COSTS})


def rsi3(c):
    d = np.diff(c, prepend=c[0])
    up = pd.Series(np.maximum(d, 0)).ewm(alpha=1 / 3, adjust=False).mean()
    dn = pd.Series(np.maximum(-d, 0)).ewm(alpha=1 / 3, adjust=False).mean()
    return (100 - 100 / (1 + up / dn.replace(0, np.nan))).to_numpy()


def vwap_rsi(a, t):
    o, h, l, c, v = (np.asarray(a[k], float) for k in ("open", "high", "low", "close", "volume"))
    dd = R.bar_dates(a["index"])
    day = np.asarray(dd.codes if hasattr(dd, "codes") else a["day_id"])
    tp = (h + l + c) / 3
    g = pd.Series(day)
    vw = (pd.Series(tp * v).groupby(g).cumsum() / pd.Series(v).groupby(g).cumsum()).to_numpy()
    ema = pd.Series(c).ewm(span=50, adjust=False).mean().to_numpy()
    tr = np.maximum(h - l, np.maximum(abs(h - np.roll(c, 1)), abs(l - np.roll(c, 1))))
    atr = pd.Series(tr).rolling(14).mean().to_numpy()
    r = rsi3(c)
    out, i, n, cnt, cur = [], 60, len(c), 0, None
    while i < n - 1:
        if day[i] != cur:
            cur, cnt = day[i], 0
        sd = 1 if r[i] <= t and c[i] > vw[i] and c[i] > ema[i] else (-1 if r[i] >= 100 - t and c[i] < vw[i] and c[i] < ema[i] else 0)
        if not sd or cnt >= 3 or day[i + 1] != day[i] or not atr[i] > 0:
            i += 1
            continue
        cnt += 1
        e = i + 1
        ep, st, tg = o[e], o[e] - sd * atr[i], o[e] + 2 * sd * atr[i]
        j = e
        while True:
            if (l[j] <= st if sd > 0 else h[j] >= st):
                xp = st
                break
            if (h[j] >= tg if sd > 0 else l[j] <= tg):
                xp = tg
                break
            if j + 1 >= n or day[j + 1] != day[e]:
                xp = c[j]
                break
            j += 1
        out.append(dict(xday=dd[j], pts=(xp - ep) * sd - S.RUN_COST))
        i = j + 1
    return out


def main():
    from augur_engine.data import find_master, load_master_arrays
    from augur_engine.engine import run_backtest
    rdoc, jdoc, jid = R.fetch(496, None)
    N = R.normalize(rdoc, jdoc, jid)
    rows = sorted([r for r in N["top"] if r.get("fold") is not None], key=lambda r: int(r["fold"]))
    import importlib.util
    spec = importlib.util.spec_from_file_location("ss11", S.F11)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    params = {k: rows[4][k] for k in mod.DEFAULT_PARAMS if k in rows[4]}
    params.update(intrabar="worst", close_rule="fifo", _detail=True)
    m1 = find_master("NQ", "1m", "eth", "db_noadj_eth")
    a = load_master_arrays(m1, date_from="2010-06-06", date_to=CUT)
    cal = pd.to_datetime(pd.Series(R.bar_dates(a["index"]).uniq))
    cal = pd.DatetimeIndex(cal[cal.dt.dayofweek < 5])
    del a
    res = dict(limit=scalper(m1, load_master_arrays, run_backtest, params, cal), vwap_rsi={})
    m5 = find_master("NQ", "5m", "rth", "db_noadj_rth")
    a = load_master_arrays(m5, date_from="2010-06-06", date_to=CUT)
    cal5 = pd.DatetimeIndex(pd.to_datetime(pd.Series(R.bar_dates(a["index"]).uniq)))
    res["m5"] = m5.get("filename")
    for t in (10, 20, 30):
        p = pd.DataFrame(vwap_rsi(a, t))
        p["xday"] = pd.to_datetime(p.xday)
        res["vwap_rsi"][str(t)] = {str(k): stats(p, k, cal5) for k in S.COSTS}
    json.dump(res, open(OUT, "w"), indent=1, default=str)
    print("DONE")


if __name__ == "__main__":
    main()
