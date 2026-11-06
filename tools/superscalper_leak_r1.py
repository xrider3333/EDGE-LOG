# SUPERSCALPER 240-MINUTE LOOK-AHEAD: SIZE OF THE LEAK (MANAGER #168). MISC_SUPERSCALPER_1_0 (reads up to ~15 bars ahead in
# its 240-minute HTF gate) vs MISC_SUPERSCALPER_1_1 (the same file with that bucket ending at its natural 4-hour boundary),
# both at file defaults with the validate's mechanics (fill 'worst', FIFO pairing), on the PRE-WF rows only: NQ 1m ETH
# no-adjust master id 34, seven standalone periods 2010-06-06 .. 2016-06-30 (the r2e periods). The walk-forward window and
# the lockbox are never read. Cost 0.706 pt a round trip, $20 a point.
# Reported: trades, net PF, and the four numbers (ROC@30k, DD5@30k, DD% from peak @30k, Sortino) on the pooled pre-WF daily
# P&L for each file; and how many trades change - matched on (signal bar, side, path): only in 1_0, only in 1_1, same
# entry with a different exit or P&L, identical.
# --configs N adds the parity harness's knob points (3 targeted + N seeded lattice draws, seed 20261020): trade
# counts and changed trades per config (the validate searches every knob, so a leak that is silent at the defaults
# may still move trades elsewhere).
#   python tools/superscalper_leak_r1.py [--configs 12]
import argparse, hashlib, json, math, os, random, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
ENGINE_ROOT = r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"
F10 = os.path.join(HERE, "..", "augur_strategies", "MISC_SUPERSCALPER_1_0.py")
F11 = os.path.join(HERE, "..", "augur_strategies", "MISC_SUPERSCALPER_1_1.py")
F10_LF_SHAS = ("b8ef032f89c1adb1a57093df0a319060a9c2165ff6565c09c2a90f0d6a2955e1",   # as run 10-20
               "56026646afe78cf4ff04cf698ea9205da399c8f6c186f354bf8eb7c343d7e8d9")   # + the LEAKS header (no rule change)
F10_LF_SHA = F10_LF_SHAS[0]
OUT = r"C:\EdgeLog\_research_cache\tv_scalp\superscalper\leak_r1.json"
VALIDATE_FIRST_DAY = "2016-07-01"
PERIODS = [("2010H2", "2010-06-06", "2010-12-31"), ("2011", "2011-01-01", "2011-12-31"),
           ("2012", "2012-01-01", "2012-12-31"), ("2013", "2013-01-01", "2013-12-31"),
           ("2014", "2014-01-01", "2014-12-31"), ("2015", "2015-01-01", "2015-12-31"),
           ("2016H1", "2016-01-01", "2016-06-30")]
COST, MULT = 0.706, 20.0
MECH = dict(intrabar="worst", close_rule="fifo", _detail=True)


def lf_sha(p):
    return hashlib.sha256(open(p, "rb").read().replace(b"\r\n", b"\n")).hexdigest()


def four(daily):
    import numpy as np
    from augur_engine.drawdowns import dd5, dd_pct_peak
    v = daily.to_numpy(float)
    yrs = max((daily.index[-1] - daily.index[0]).days, 1) / 365.25
    cum = np.cumsum(v)
    dd = float(np.max(np.maximum.accumulate(np.maximum(cum, 0.0)) - cum)) if len(v) else 0.0
    roc = 30.0 * (float(v.sum()) / yrs) / dd if dd > 0 else float("inf")
    d5 = dd5(daily)
    k = 30000.0 / dd if dd > 0 else 1.0
    neg = np.minimum(v, 0.0)
    so = float(v.mean() / math.sqrt(float((neg ** 2).mean())) * math.sqrt(252)) if (neg ** 2).mean() > 0 else float("inf")
    return dict(roc30=round(roc, 2), dd5_at_30k=round(float(d5["dd5_usd"]) * k, 0), one_episode=bool(d5["one_episode"]),
                dd_pct_peak_at_30k=round(float(dd_pct_peak(daily * k, start=100000.0)), 2), sortino=round(so, 3),
                worst_dd_usd_1lot=round(dd, 0), net_usd_1lot=round(float(v.sum()), 0))


def configs(n):
    sys.path.insert(0, HERE)
    import superscalper_lite_parity as LP
    import importlib.util
    spec = importlib.util.spec_from_file_location("ss_leak_params", F10)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    rng = random.Random(20261020)
    out = [("targeted%d" % i, c) for i, c in enumerate(LP.TARGETED)]
    return out + [("random%02d" % i, LP.lattice_draw(mod.DEFAULT_PARAMS, rng)) for i in range(n)]


def sweep(n, m, load_master_arrays, run_backtest):
    res = []
    cfgs = configs(n)
    for name, d0, d1 in PERIODS:
        a = load_master_arrays(m, date_from=d0, date_to=d1)
        for cname, cfg in cfgs:
            got = {}
            for tag, path in (("1_0", F10), ("1_1", F11)):
                r = run_backtest(path, arrays=a, master=m, params=dict(cfg, **MECH), cost_pts=0.0, return_trades=True)
                got[tag] = {(x["signal_bar"], x["side"], x["path"]): (x["exit_bar"], x["entry_price"], x["exit_price"])
                            for x in ((r or {}).get("trade_detail") or [])}
            k10, k11 = got["1_0"], got["1_1"]
            both = set(k10) & set(k11)
            row = dict(period=name, config=cname, trades_1_0=len(k10), trades_1_1=len(k11),
                       only_1_0=len(set(k10) - set(k11)), only_1_1=len(set(k11) - set(k10)),
                       same_entry_diff_exit=sum(1 for k in both if k10[k] != k11[k]))
            res.append(row)
            print("  sweep %-7s %-10s 1_0 %5d 1_1 %5d  only10 %d only11 %d diffexit %d" % (
                name, cname, row["trades_1_0"], row["trades_1_1"], row["only_1_0"], row["only_1_1"],
                row["same_entry_diff_exit"]), flush=True)
        del a
    return dict(configs=dict(cfgs), rows=res)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--configs", type=int, default=0)
    args = ap.parse_args()
    if lf_sha(F10) not in F10_LF_SHAS:
        sys.exit("refused: 1_0 is not one of the pinned LFs %s" % (F10_LF_SHAS,))
    assert all(p[2] < VALIDATE_FIRST_DAY for p in PERIODS)
    sys.path.insert(0, ENGINE_ROOT)
    sys.dont_write_bytecode = True
    import numpy as np
    import pandas as pd
    from augur_engine.engine import run_backtest
    from augur_engine.data import find_master, load_master_arrays
    m = find_master("NQ", "1m", "eth", "db_noadj_eth")
    if not m or (int(m.get("id") or 0), m.get("filename")) != (34, "NOADJ_NQ_1m_ETH.csv"):
        sys.exit("refused: NQ master is not id 34 NOADJ_NQ_1m_ETH.csv: %r" % (m,))
    f11_sha = lf_sha(F11)
    print("1_0 LF %s OK; 1_1 LF %s; harness LF %s" % (lf_sha(F10)[:12], f11_sha[:12], lf_sha(os.path.abspath(__file__))[:12]),
          flush=True)
    rows = {"1_0": [], "1_1": []}
    days_all = []
    per = []
    for name, d0, d1 in PERIODS:
        a = load_master_arrays(m, date_from=d0, date_to=d1)
        idx = pd.DatetimeIndex(a["index"])
        if idx.tz is None:
            idx = idx.tz_localize("America/New_York", ambiguous="NaT", nonexistent="shift_forward")
        et = idx.tz_convert("America/New_York")
        day = et.normalize().tz_localize(None)
        days_all.append(pd.DatetimeIndex(sorted(set(day))))
        got = {}
        for tag, path in (("1_0", F10), ("1_1", F11)):
            t0 = time.time()
            r = run_backtest(path, arrays=a, master=m, params=dict(MECH), cost_pts=0.0, return_trades=True)
            tr = (r or {}).get("trade_detail") or []
            for x in tr:
                x["exit_day"] = day[x["exit_bar"]]
                x["period"] = name
                x["sig_ct"] = int((((et[x["signal_bar"]].hour * 60 + et[x["signal_bar"]].minute) - 60) % 1440))
            got[tag] = tr
            rows[tag].extend(tr)
            print("  %-7s %s  trades %5d  %.0fs" % (name, tag, len(tr), time.time() - t0), flush=True)
        k10 = {(x["signal_bar"], x["side"], x["path"]): x for x in got["1_0"]}
        k11 = {(x["signal_bar"], x["side"], x["path"]): x for x in got["1_1"]}
        only10 = sorted(set(k10) - set(k11)); only11 = sorted(set(k11) - set(k10))
        both = set(k10) & set(k11)
        changed = [k for k in both if (k10[k]["exit_bar"], k10[k]["exit_price"], k10[k]["entry_price"])
                   != (k11[k]["exit_bar"], k11[k]["exit_price"], k11[k]["entry_price"])]
        per.append(dict(period=name, bars=len(a["close"]), trades_1_0=len(k10), trades_1_1=len(k11),
                        only_1_0=len(only10), only_1_1=len(only11), same_entry_diff_exit=len(changed),
                        identical=len(both) - len(changed),
                        only_sig_ct_minutes=sorted({k10[k]["sig_ct"] for k in only10} | {k11[k]["sig_ct"] for k in only11})[:40]))
        del a
    days = pd.DatetimeIndex(sorted(set().union(*[set(d) for d in days_all])))
    res = dict(f10_lf=lf_sha(F10), f11_lf=f11_sha, cost=COST, periods=per, files={})
    for tag in ("1_0", "1_1"):
        df = pd.DataFrame(rows[tag])
        g = df["pnl_pts"] - COST
        wins = g[g > 0].sum(); losses = -g[g < 0].sum()
        daily = (g * MULT).groupby(df["exit_day"]).sum().reindex(days, fill_value=0.0)
        s = dict(trades=int(len(df)), trades_per_year=round(len(df) / max((days[-1] - days[0]).days / 365.25, 1e-9), 1),
                 net_pf=round(float(wins / losses), 4) if losses > 0 else None,
                 net_pts=round(float(g.sum()), 1), win_rate=round(float((g > 0).mean()) * 100, 2))
        s.update(four(daily))
        res["files"][tag] = s
    tot = {k: sum(p[k] for p in per) for k in ("trades_1_0", "trades_1_1", "only_1_0", "only_1_1",
                                               "same_entry_diff_exit", "identical")}
    res["totals"] = tot
    if args.configs:
        res["sweep"] = sweep(args.configs, m, load_master_arrays, run_backtest)
        sw = res["sweep"]["rows"]
        res["sweep_totals"] = {k: sum(r[k] for r in sw) for k in ("trades_1_0", "trades_1_1", "only_1_0", "only_1_1",
                                                                  "same_entry_diff_exit")}
        print("SWEEP TOTALS", json.dumps(res["sweep_totals"]), flush=True)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(res, open(OUT, "w"), indent=1, default=str)
    print(json.dumps(dict(files=res["files"], totals=tot), indent=1), flush=True)


if __name__ == "__main__":
    main()
