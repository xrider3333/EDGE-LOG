# SUPERSCALPER r2 EXPLORE (prereg docs/PREREG_tv_superscalper_r2_explore_2026-10-15.md): development data only (NQ / ES 2024,
# 2023 as the second development year). E0 = the r1 pick on 2023; E1 = time-of-day windows (decomposition, close_rule 'any');
# E2 = the port on ES. Refuses unless the prereg and the port carry their pinned LF sha256s. OUR PORT, not the published script.
#   python tools/superscalper_explore_r2.py
import hashlib, json, math, os, sys, time
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
PREREG = os.path.join(HERE, "..", "docs", "PREREG_tv_superscalper_r2_explore_2026-10-15.md")
PREREG_LF_SHA = "d5e421ac42778bbdbc454ef8af8ba890dd0f9e1e0f49806cfef877db6872b27c"
ROOT = r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"
PORT_CANDIDATES = [os.path.join(ROOT, "augur_strategies", "MISC_SUPERSCALPER_1_0.py"),
                   r"C:\Users\xride\AppData\Local\EdgeLog-worktrees\superscalp\augur_strategies\MISC_SUPERSCALPER_1_0.py"]
PORT_LF_SHA = "8566c2c14e68291807e79854c040cf2ad156006f6b47a7e637f4eca5240fe918"
OUT = r"C:\EdgeLog\_research_cache\tv_scalp\superscalper\explore_r2.json"
COST = {"NQ": 0.706, "ES": 0.582}
MULT = {"NQ": 20.0, "ES": 50.0}
STRESS = 0.25
AS_PORTED = dict(sl_cap_atr="off", sl_scale=1.0, tp_scale=1.0, max_hold_bars=0, be_trigger=0.0, vix_feed="none")
ES_SCALED = dict(tp_buffer=0.25, min_profit=1.25, min_atr_pts=1.25)
WINDOWS = (("W1 open 09:30-10:59", 570, 660), ("W2 midday 11:00-13:59", 660, 840), ("W3 close 14:00-15:59", 840, 960))
Y24, Y23 = ("2024-01-01", "2024-12-31"), ("2023-01-01", "2023-12-31")


def lf_sha(p):
    return hashlib.sha256(open(p, "rb").read().replace(b"\r\n", b"\n")).hexdigest()


def stats(g, cost):
    net = np.asarray(g, float) - cost
    w, l = net[net > 0], net[net <= 0]
    return dict(trades=len(net), win_rate=round(float((net > 0).mean()), 4) if len(net) else None,
                avg_win=round(float(w.mean()), 2) if len(w) else 0.0, avg_loss=round(float(-l.mean()), 2) if len(l) else 0.0,
                net_pf=round(float(w.sum() / -l.sum()), 4) if l.sum() < 0 else None, net_pts=round(float(net.sum()), 1))


def four(daily):
    """tools/orb_relay_r1.py four(): ROC %/yr at a $30k worst DD, DD5 and DD% from peak at that sizing, daily Sortino."""
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


class Runner:
    def __init__(self, port):
        sys.path.insert(0, ROOT)
        sys.dont_write_bytecode = True
        from augur_engine.engine import run_backtest
        from augur_engine.data import find_master, load_master_arrays
        self.run_bt, self.port, self.cache = run_backtest, port, {}
        self.fm, self.load = find_master, load_master_arrays

    def arrays(self, inst, yr):
        key = (inst, yr)
        if key not in self.cache:
            m = self.fm(inst, "1m", "eth", "db_noadj_eth")
            want = {"NQ": (34, "NOADJ_NQ_1m_ETH.csv"), "ES": (30, "NOADJ_ES_1m_ETH.csv")}[inst]
            if not m or (int(m.get("id") or 0), m.get("filename")) != want:
                sys.exit("refused: %s master is not id %s %s" % (inst, want[0], want[1]))
            self.cache[key] = (m, self.load(m, date_from=yr[0], date_to=yr[1]))
        return self.cache[key]

    def trades(self, inst, yr, params):
        m, a = self.arrays(inst, yr)
        r = self.run_bt(self.port, arrays=a, master=m, params=dict(params, intrabar="worst", _detail=True), cost_pts=0.0,
                        return_trades=True)
        rows = (r or {}).get("trade_detail") or []
        idx = pd.DatetimeIndex(a["index"])
        if idx.tz is None:
            idx = idx.tz_localize("America/New_York", ambiguous="NaT", nonexistent="shift_forward")
        et = idx.tz_convert("America/New_York")
        day = pd.Series(et.normalize().tz_localize(None))
        days = pd.DatetimeIndex(sorted(day.unique()))
        df = pd.DataFrame({"pnl": [x["pnl_pts"] for x in rows],
                           "sig_min": [et[x["signal_bar"]].hour * 60 + et[x["signal_bar"]].minute for x in rows],
                           "exit_day": [day.iloc[x["exit_bar"]] for x in rows]})
        return df, days

    def read(self, inst, df, days, label):
        cost = COST[inst]
        s = stats(df["pnl"], cost)
        s["stress_pf"] = stats(df["pnl"], cost + STRESS)["net_pf"]
        daily = ((df["pnl"] - cost) * MULT[inst]).groupby(df["exit_day"]).sum().reindex(days, fill_value=0.0)
        s.update(four(daily) if len(df) else {})
        s["label"] = label
        print("  %-48s %s" % (label, json.dumps({k: s[k] for k in s if k != "label"})), flush=True)
        return s


def window_of(m):
    for name, a, b in WINDOWS:
        if a <= m < b:
            return name
    return "W4 outside RTH"


def main():
    got = lf_sha(PREREG)
    print("prereg LF sha256", got, "OK" if got == PREREG_LF_SHA else "MISMATCH", flush=True)
    if got != PREREG_LF_SHA:
        sys.exit("refused: prereg is not the pinned one")
    port = next((p for p in PORT_CANDIDATES if os.path.exists(p) and lf_sha(p) == PORT_LF_SHA), None)
    if port is None:
        sys.exit("refused: no port file with LF sha %s" % PORT_LF_SHA)
    print("port", port, "OK; harness LF sha256", lf_sha(os.path.abspath(__file__)), flush=True)
    R = Runner(port)
    out = {}
    t0 = time.time()

    print("\nE0 - the r1 pick on the second development year (NQ 2023)", flush=True)
    imp = R.read("NQ", *R.trades("NQ", Y23, {}), "NQ 2023 IMPROVED_R1 (file defaults)")
    asp = R.read("NQ", *R.trades("NQ", Y23, AS_PORTED), "NQ 2023 AS_PORTED")
    holds = bool(imp["net_pf"] is not None and imp["net_pf"] >= 1.0 and imp["net_pf"] > (asp["net_pf"] or 0))
    print("  E0 VERDICT: r1 pick %s on 2023" % ("HOLDS" if holds else "DOES NOT HOLD"), flush=True)
    out["E0"] = dict(improved=imp, as_ported=asp, holds=holds)

    print("\nE1 - time-of-day windows (NQ 2024, file defaults, close_rule 'any'; tagged at the signal bar)", flush=True)
    dfa, days = R.trades("NQ", Y24, dict(close_rule="any"))
    dff, _ = R.trades("NQ", Y24, {})
    print("  totals check: 'any' %.2f pt vs 'fifo' %.2f pt (gross), trades %d vs %d" % (dfa["pnl"].sum(), dff["pnl"].sum(),
                                                                                        len(dfa), len(dff)), flush=True)
    dfa["win"] = dfa["sig_min"].map(window_of)
    e1 = {"all": R.read("NQ", dfa, days, "NQ 2024 all windows ('any')")}
    for name in [w[0] for w in WINDOWS] + ["W4 outside RTH"]:
        e1[name] = R.read("NQ", dfa[dfa["win"] == name], days, "NQ 2024 " + name)
    cands = [n for n, s in e1.items() if n != "all" and s["trades"] >= 300 and (s["net_pf"] or 0) >= 1.10]
    print("  E1 candidates (2024 net PF >= 1.10, >= 300 trades):", cands or "none", flush=True)
    e1_23 = {}
    if cands:
        d23, days23 = R.trades("NQ", Y23, dict(close_rule="any"))
        d23["win"] = d23["sig_min"].map(window_of)
        for name in cands:
            s = R.read("NQ", d23[d23["win"] == name], days23, "NQ 2023 " + name)
            s["confirmed"] = bool((s["net_pf"] or 0) >= 1.05 and s.get("roc30", 0) >= 15)
            print("    %s: %s" % (name, "CONFIRMED" if s["confirmed"] else "not confirmed"), flush=True)
            e1_23[name] = s
    out["E1"] = dict(y2024=e1, candidates=cands, y2023=e1_23)

    print("\nE2 - the port on ES (2024; ES / QQQ helper feeds off on ES)", flush=True)
    cells = {"a AS_PORTED": AS_PORTED, "b IMPROVED_R1 (file defaults)": {}, "c IMPROVED_R1 + ES-scaled point knobs": ES_SCALED}
    e2 = {k: R.read("ES", *R.trades("ES", Y24, p), "ES 2024 " + k) for k, p in cells.items()}
    ec = [k for k, s in e2.items() if s["trades"] >= 500 and (s["net_pf"] or 0) >= 1.05]
    print("  E2 candidates (2024 net PF >= 1.05, >= 500 trades):", ec or "none", flush=True)
    e2_23 = None
    if ec:
        best = max(ec, key=lambda k: e2[k]["net_pf"])
        e2_23 = R.read("ES", *R.trades("ES", Y23, cells[best]), "ES 2023 " + best)
        e2_23["confirmed"] = bool((e2_23["net_pf"] or 0) >= 1.0 and e2_23.get("roc30", 0) >= 15)
        print("    %s: %s" % (best, "CONFIRMED" if e2_23["confirmed"] else "not confirmed"), flush=True)
    out["E2"] = dict(y2024=e2, candidates=ec, y2023=e2_23)
    json.dump(out, open(OUT, "w"), indent=1, default=str)
    print("\nwrote %s (%.0f s)" % (OUT, time.time() - t0), flush=True)


if __name__ == "__main__":
    main()
