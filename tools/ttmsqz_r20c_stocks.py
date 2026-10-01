"""TTM round 20c - the frozen #299 crown on 35 large US stocks (tools/TTM_R20_PREREG.txt addendum 2, 388fe584).

Runs only once the owner has saved the Alpaca keys (Windows user env ALPACA_API_KEY / ALPACA_SECRET_KEY);
never reads or prints them beyond handing them to the shared loader's fetch function.
Data: Alpaca SIP 30Min, split-adjusted, RTH 09:30-16:00 ET, 2016-01-04 .. 2026-06-30, cached per symbol in
C:\\EdgeLog\\alpaca_cache\\ttm_r20c (no library masters are registered). Rule: TTMSQZ_3_0.py at the frozen
crown, unchanged, gated (the candidate) and ungated (the plain twin). $25,000 of stock per fire in whole
shares at the entry price; cost $0.02 a share round trip ($0.05 stress). Shares and cost are REAL: the
bars are split-adjusted, and each trade is sized/costed at raw price = adjusted x the entry date's split
factor (raw / adjusted daily close; prereg addendum 5). Pooled daily P&L, round 19's
stretch_stats, WF 2016-01-04 .. 2025-06-30, LB 2025-07-01 .. 2026-06-30.

  python tools/ttmsqz_r20c_stocks.py                 # pull (cached) + score + verdict
  python tools/ttmsqz_r20c_stocks.py --selftest      # plumbing check on the ES 30m master (no Alpaca)
Log: tools/data/ttmsqz_r20c_stocks.txt
"""
import os
import sys
import argparse
import importlib.util

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHARED = r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"
os.chdir(SHARED)
sys.path.insert(0, SHARED)
from augur_engine.data import find_master, load_master_arrays   # noqa: E402


def _imp(name, path):
    sp = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(sp)
    sp.loader.exec_module(m)
    return m


MOD = _imp("TTMSQZ_3_0_r20c", os.path.join(SHARED, "augur_strategies", "TTMSQZ_3_0.py"))
R19 = _imp("r19a", os.path.join(HERE, "tools", "ttmsqz_r19a_multicell_sleeve.py"))

UNIVERSE = ("AAPL GOOGL MSFT XOM AMZN META GE JNJ WFC JPM T PG VZ WMT CVX PFE KO HD ORCL DIS INTC MRK "
            "CMCSA PEP BAC CSCO V C GILD IBM UNH AMGN MO CVS MA").split()
CROWN = dict(R19.CROWN)
NOTIONAL, COST_SH, STRESS_SH = 25000.0, 0.02, 0.05
D0, WF_END, LB0, D1 = "2016-01-04", "2025-06-30", "2025-07-01", "2026-06-30"
CACHE = r"C:\EdgeLog\alpaca_cache\ttm_r20c"
OUT = os.path.join(HERE, "tools", "data", "ttmsqz_r20c_stocks.txt")
L = []


def emit(x=""):
    L.append(x)
    print(x, flush=True)


def pull(sym, key, secret, loader):
    path = os.path.join(CACHE, "%s_30m_split_rth.csv" % sym)
    if os.path.exists(path) and os.path.getsize(path) > 100:
        return pd.read_csv(path)
    df = loader.fetch_bars(sym, "30Min", D0, "2026-07-01", key, secret, feed="sip", adjustment="split")
    df = loader.rth_filter(df) if len(df) else df
    if len(df):                     # never cache an empty pull - the next run would read it as data
        os.makedirs(CACHE, exist_ok=True)
        df.to_csv(path, index=False)
    return df


def pull_factor(sym, key, secret, loader):
    """Per-ET-date split factor = RAW daily close / split-adjusted daily close (MANAGER review 2026-09-30).

    Bars are split-adjusted so a split never looks like a crash, but shares and the $/share cost must be
    REAL: before AMZN's 2022 20:1 split an adjusted share is 1/20 of a real one, so costing adjusted
    shares overstates the cost ~20x (GE's 2021 1-for-8 reverse split understates it ~8x). A split is a
    calendar fact, so the factor on the entry date is known at the decision."""
    path = os.path.join(CACHE, "%s_1d_split_factor.csv" % sym)
    if os.path.exists(path) and os.path.getsize(path) > 50:
        f = pd.read_csv(path)
        return pd.Series(f["factor"].to_numpy(float), index=pd.to_datetime(f["date"]).dt.date)
    raw = loader.fetch_bars(sym, "1Day", D0, "2026-07-01", key, secret, feed="sip", adjustment="raw")
    adj = loader.fetch_bars(sym, "1Day", D0, "2026-07-01", key, secret, feed="sip", adjustment="split")
    if not len(raw) or not len(adj):
        return pd.Series(dtype=float)
    m = raw[["time", "close"]].merge(adj[["time", "close"]], on="time", suffixes=("_raw", "_adj"))
    m["date"] = pd.to_datetime(m["time"], unit="s", utc=True).dt.tz_convert("US/Eastern").dt.date
    m["factor"] = m["close_raw"] / m["close_adj"]
    os.makedirs(CACHE, exist_ok=True)
    m[["date", "factor"]].to_csv(path, index=False)
    return pd.Series(m["factor"].to_numpy(float), index=m["date"])


def to_arrays(df, factor=None):
    """Bar-START POSIX seconds -> the same dict shape load_master_arrays returns (+ per-bar split factor)."""
    idx = pd.DatetimeIndex(pd.to_datetime(df["time"], unit="s", utc=True)).tz_convert("US/Eastern")
    keep = (idx >= pd.Timestamp(D0, tz="US/Eastern")) & (idx < pd.Timestamp(D1, tz="US/Eastern") + pd.Timedelta(days=1))
    df, idx = df[keep], idx[keep]
    dates = pd.Series(idx).dt.date
    if factor is not None and len(factor):
        fac = dates.map(factor.to_dict()).astype(float).ffill().bfill().fillna(1.0).to_numpy()
    else:
        fac = np.ones(len(idx))
    return dict(open=df["open"].to_numpy(float), high=df["high"].to_numpy(float), low=df["low"].to_numpy(float),
                close=df["close"].to_numpy(float), index=idx,
                day_id=pd.factorize(dates)[0].astype("int64"), factor=fac)


def trades_usd(a, gated, cost_sh):
    p = dict(CROWN, gate_mode="sq_on" if gated else "none")
    r = MOD.run_backtest(a["open"], a["high"], a["low"], a["close"], day_id=a["day_id"],
                         index=a["index"], return_trades=True, **p)
    idx = pd.DatetimeIndex(a["index"]).tz_localize(None)
    out = []
    for t in (r or {}).get("trades", []):
        eb, xb, pts, side, epx = int(t[0]), int(t[1]), float(t[2]), int(t[3]), float(t[4])
        f = float(a["factor"][eb]) if "factor" in a else 1.0     # real price = adjusted x factor
        sh = np.floor(NOTIONAL / (epx * f)) if epx > 0 else 0.0  # REAL shares
        out.append((idx[xb].normalize(), sh * (pts * f - cost_sh), side))
    return out


def line(label, wf, lb):
    emit("  %-24s WF n %5d net $%10s ROC@30k %6.1f Sortino %5.2f | LB n %4d net $%9s ROC@30k %6.1f Sortino %5.2f ex-big $%9s" % (
        label, wf["n"], "{:,.0f}".format(wf["net"]), wf["roc"], wf["sortino"],
        lb["n"], "{:,.0f}".format(lb["net"]), lb["roc"], lb["sortino"], "{:,.0f}".format(lb["net_ex_biggest"])))


def score(td, cal):
    td2 = [(d, u) for d, u, *_ in td]
    return R19.stretch_stats(td2, cal, D0, WF_END), R19.stretch_stats(td2, cal, LB0, D1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    emit("TTM round 20c - frozen #299 crown on %d large US stocks (prereg addendum 2, 388fe584)%s" % (
        len(UNIVERSE), "  [SELFTEST on ES 30m - not a result]" if args.selftest else ""))
    data = {}
    if args.selftest:
        es = load_master_arrays(find_master("ES", "30m", "rth", "db_noadj_rth"), date_from=D0, date_to=D1)
        data["ES30m"] = dict(es)
    else:
        loader = _imp("import_alpaca_stocks", os.path.join(SHARED, "tools", "import_alpaca_stocks.py"))
        key, secret = loader.load_keys()
        if not (key and secret):
            emit("Alpaca keys not saved - nothing pulled, nothing scored.")
            return
        for s in UNIVERSE:
            df = pull(s, key, secret, loader)
            first = str(pd.to_datetime(df["time"].iloc[0], unit="s", utc=True).date()) if len(df) else "-"
            emit("  %s: %d bars from %s%s" % (s, len(df), first,
                 "  <- SHORT HISTORY, kept as-is (no substitution)" if (len(df) < 1000 or first > "2016-02-01") else ""))
            if len(df):
                fac = pull_factor(s, key, secret, loader)
                if not len(fac):
                    emit("  %s: no daily split factor - costed at adjusted shares (factor 1)" % s)
                data[s] = to_arrays(df, fac)
    cal = R19.full_calendar([pd.DatetimeIndex(a["index"]).tz_localize(None) for a in data.values()], D0, D1)
    es = load_master_arrays(find_master("ES", "30m", "rth", "db_noadj_rth"), date_from=D0, date_to=D1)
    es_idx = pd.DatetimeIndex(es["index"]).tz_localize(None)
    es_r = MOD.run_backtest(es["open"], es["high"], es["low"], es["close"], day_id=es["day_id"],
                            index=es["index"], return_trades=True, **CROWN)
    es_td = [(es_idx[int(t[1])].normalize(), (float(t[2]) - 0.363) * 50.0, int(t[3])) for t in es_r["trades"]]
    book = {}
    for lab, g, cs in (("GATED (candidate)", True, COST_SH), ("UNGATED (plain twin)", False, COST_SH),
                       ("GATED at $0.05 cost", True, STRESS_SH)):
        emit("")
        emit(lab)
        allt = []
        for s, a in data.items():
            td = trades_usd(a, g, cs)
            allt += td
            if g and cs == COST_SH:
                line(s, *score(td, cal))
        book[lab] = allt
        line("POOLED BOOK", *score(allt, cal))
        if g and cs == COST_SH:
            for side, nm in ((1, "longs only"), (-1, "shorts only")):
                line("  " + nm, *score([x for x in allt if x[2] == side], cal))
    emit("")
    emit("REFERENCE (no clause): ES 30m crown cell, same stretches, 1 contract")
    line("ES 30m #299 settings", *score(es_td, cal))
    s_g = pd.Series(dict(pd.DataFrame([(d, u) for d, u, _ in book["GATED (candidate)"]]).groupby(0)[1].sum())).reindex(cal, fill_value=0.0)
    s_e = pd.Series(dict(pd.DataFrame([(d, u) for d, u, _ in es_td]).groupby(0)[1].sum())).reindex(cal, fill_value=0.0)
    emit("  daily correlation, gated stock book vs ES 30m cell: %.2f" % s_g.corr(s_e))
    gw, gl = score(book["GATED (candidate)"], cal)
    uw, ul = score(book["UNGATED (plain twin)"], cal)
    sw, sl = score(book["GATED at $0.05 cost"], cal)
    cl = [("(a) >=100 WF / 50 LB trades", gw["n"] >= 100 and gl["n"] >= 50),
          ("(b) ROC@30k >= ungated WF and LB", gw["roc"] >= uw["roc"] and gl["roc"] >= ul["roc"]),
          ("(c) WF Sortino >= 1.0 and LB ROC > 0", gw["sortino"] >= 1.0 and gl["roc"] > 0),
          ("(d) LB ex-biggest > 0", gl["net_ex_biggest"] > 0),
          ("(e) positive WF and LB at $0.05", sw["net"] > 0 and sl["net"] > 0)]
    emit("")
    emit("VERDICT: %s -> %s" % ("; ".join("%s %s" % (k, "yes" if v else "NO") for k, v in cl),
                               "PASS (triage) -> Frontier book test" if all(v for _, v in cl) else "FAIL"))
    if not args.selftest:
        os.makedirs(os.path.dirname(OUT), exist_ok=True)
        open(OUT, "w", encoding="utf-8").write("\n".join(L) + "\n")
        print("log ->", OUT)


if __name__ == "__main__":
    main()
