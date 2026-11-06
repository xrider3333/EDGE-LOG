# SUPERSCALPER r3 SCREEN (MANAGER #187, owner 11-06): two cost rows on run #496's walk-forward chain, what regime its winning
# folds 3-6 sat in, and whether that regime separates net P&L on the PRE-WF rows (2010-06..2016-06), which never saw the choice.
# Lockbox trades are dropped; only prior-day regime features are used. Port entries are MARKET orders, so the 0.283 row
# (commission only) is an upper bound, not a tradable cost.
#   python tools/superscalper_regime_r3.py
import json, os, sys
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import superscalper_validate_read as R

SHARED = R.SHARED
OUT = r"C:\EdgeLog\_research_cache\tv_scalp\superscalper\regime_r3.json"
RUN_COST, COSTS, MULT = 0.706, (0.783, 0.283), 20.0
F11 = os.path.join(SHARED, "augur_strategies", "MISC_SUPERSCALPER_1_1.py")
PERIODS = [("2010-06-06", "2010-12-31"), ("2011-01-01", "2011-12-31"), ("2012-01-01", "2012-12-31"), ("2013-01-01", "2013-12-31"),
           ("2014-01-01", "2014-12-31"), ("2015-01-01", "2015-12-31"), ("2016-01-01", "2016-06-30")]
FEATS = ("rv20", "atr20_pct", "atr20_pts", "trend50")


def features(m, load):
    fr = []
    for d0, d1 in (("2010-01-01", "2016-06-30"), ("2016-07-01", "2025-06-29")):
        a = load(m, date_from=d0, date_to=d1)
        ix = pd.DatetimeIndex(a["index"])
        ix = ix.tz_convert("America/New_York").tz_localize(None) if ix.tz is not None else ix
        fr.append(pd.DataFrame(dict(h=a["high"], l=a["low"], c=a["close"]), index=ix))
    df = pd.concat(fr)
    d = df.groupby(df.index.normalize()).agg(h=("h", "max"), l=("l", "min"), c=("c", "last"))
    d = d[d.index.dayofweek < 5]
    f = pd.DataFrame(index=d.index)
    f["rv20"] = d.c.pct_change().rolling(20).std() * np.sqrt(252) * 100
    f["atr20_pts"] = (d.h - d.l).rolling(20).mean()
    f["atr20_pct"] = f.atr20_pts / d.c * 100
    f["trend50"] = (d.c / d.c.rolling(50).mean() - 1) * 100
    return f.shift(1)            # known before the session opens


def row(g, cal, cost, label):
    net = g["pts"] + RUN_COST - cost
    daily = (net * MULT).groupby(g["xday"]).sum().reindex(cal, fill_value=0.0)
    yrs = max((cal[-1] - cal[0]).days, 1) / 365.25
    f = R.four(daily.to_numpy(float).tolist(), yrs)
    top = daily.nlargest(5).sum()
    return dict(label=label, cost=cost, trades=int(len(g)), net=round(float(daily.sum())), four=f,
                top5_share=round(float(top / daily.sum()), 3) if daily.sum() > 0 else None, pts_per_trade=round(float(net.mean()), 3))


def buckets(g, cost, cuts):
    out = {}
    for k, (a, b) in cuts.items():
        s = g[(g.rv20 >= a) & (g.rv20 < b)]
        n = s["pts"] + RUN_COST - cost
        w, l = n[n > 0].sum(), -n[n < 0].sum()
        out[k] = dict(trades=int(len(s)), pts_per_trade=round(float(n.mean()), 3) if len(s) else None, pf=round(float(w / l), 3) if l > 0 else None)
    return out


def main():
    rdoc, jdoc, jid = R.fetch(496, None)
    N = R.normalize(rdoc, jdoc, jid)
    cap, cap_dates, orig_ft, orig_bd = [], [], R.fold_trades, R.bar_dates

    def ft(*a):
        o = orig_ft(*a)
        cap.append(o)
        return o

    def bd(ix):
        o = orig_bd(ix)
        cap_dates.append(o)
        return o

    R.fold_trades, R.bar_dates = ft, bd
    rep = R.replay(N, SHARED)
    if not rep["wf"]["ok"]:
        sys.exit("WF parity failed")
    nf = len(rep["wf"]["folds"])
    dates = cap_dates[0]
    wf = [dict(fold=i + 1, eday=dates[int(t[0])], xday=dates[min(int(t[1]), len(dates) - 1)], pts=float(t[2]))
          for i, tr in enumerate(cap[:nf]) for t in tr]            # cap[nf] = lockbox: dropped, never read
    g = pd.DataFrame(wf)
    g["eday"], g["xday"] = pd.to_datetime(g.eday), pd.to_datetime(g.xday)

    from augur_engine.data import find_master, load_master_arrays
    from augur_engine.engine import run_backtest
    m = find_master("NQ", "1m", "eth", "db_noadj_eth")
    F = features(m, load_master_arrays)
    g = g.join(F, on="eday")
    cal = F.loc["2020-02-24":"2025-06-27"].index
    res = dict(wf={str(c): row(g, cal, c, "WF") for c in COSTS}, folds=[])
    for f, s in g.groupby("fold"):
        res["folds"].append(dict(fold=int(f), **{str(c): round(float(((s.pts + RUN_COST - c) * MULT).sum())) for c in COSTS},
                                 trades=int(len(s)), **{k: round(float(s[k].mean()), 2) for k in FEATS}))
    q = g.rv20.quantile([1 / 3, 2 / 3]).tolist()
    cuts = dict(low=(0, q[0]), mid=(q[0], q[1]), high=(q[1], 1e9))
    res["rv20_cuts_wf"] = q
    res["wf_rv"] = {str(c): buckets(g, c, cuts) for c in COSTS}

    # PRE-WF: the winning folds' most common config (folds 5 and 6 = fold 4's params), fixed rules 1_1
    rows = sorted([r for r in N["top"] if r.get("fold") is not None], key=lambda r: int(r["fold"]))
    import importlib.util
    spec = importlib.util.spec_from_file_location("ss11", F11)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    params = {k: rows[4][k] for k in mod.DEFAULT_PARAMS if k in rows[4]}
    params.update(intrabar="worst", close_rule="fifo", _detail=True)
    pre = []
    for d0, d1 in PERIODS:
        a = load_master_arrays(m, date_from=d0, date_to=d1)
        dd = R.bar_dates(a["index"])
        r = run_backtest(F11, arrays=a, master=m, params=dict(params), cost_pts=0.0, return_trades=True)
        for x in (r or {}).get("trade_detail") or []:
            pre.append(dict(eday=dd[int(x["signal_bar"])], xday=dd[int(x["exit_bar"])], pts=float(x["pnl_pts"]) - RUN_COST))
        del a
    p = pd.DataFrame(pre)
    p["eday"], p["xday"] = pd.to_datetime(p.eday), pd.to_datetime(p.xday)
    p = p.join(F, on="eday")
    cal0 = F.loc["2010-06-06":"2016-06-30"].index
    res["prewf"] = {str(c): row(p, cal0, c, "pre-WF") for c in COSTS}
    res["prewf_rv"] = {str(c): buckets(p, c, cuts) for c in COSTS}
    res["prewf_params_fold"] = 5
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(res, open(OUT, "w"), indent=1, default=str)
    print(json.dumps(res, indent=1, default=str))


if __name__ == "__main__":
    main()
