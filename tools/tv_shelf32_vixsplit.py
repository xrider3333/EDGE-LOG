# SHELF No. 32 (Bondarenko and Muravyev 2023, "Market Return Around the Clock") - the VIX split of the European-open hold,
# power-first draft read on PRE-WF rows only (TV, 2026-10-16). Spec: docs/PREREG_tv_shelf32_vixsplit_2026-10-16.md (checked
# by LF sha256 at start; nothing is computed on a mismatch). Every master array is cut before 2016-07-01 00:00 ET before a
# signal exists; the walk-forward and the lockbox are not read. tools/mapcheck_f.py is imported unchanged and writes to TV's
# own folder.
#   python tools/tv_shelf32_vixsplit.py            (run from the worktree; data read from the shared checkout)
import csv, hashlib, json, math, os, sys
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
SHARED = r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"
PREREG = os.path.join(HERE, "..", "docs", "PREREG_tv_shelf32_vixsplit_2026-10-16.md")
PREREG_LF_SHA = "0bc4cfb7c864ba3e60fffcb8ec47915ca57828f4340afabf37af1c42ed9bb0d8"
OUT = r"C:\EdgeLog\_research_cache\tv_shelf\paper32_vixsplit"
CUT = pd.Timestamp("2016-07-01 00:00", tz="US/Eastern")
VIX = (r"C:\EdgeLog\_research_cache\public_series\cboe\VIX_History.csv",
       "6edc3e3928c4b164b9e4ed1ec874e0ed53c7d52997557adebb7d6b7451db565a")
MULT = {"NQ": 20.0, "ES": 50.0}
COST = {"NQ": 0.706, "ES": 0.582}
STRESS, ROLL_PT = 0.25, 0.25
# window: (entry day offset, entry hh:mm, latest entry hh:mm, exit day offset, exit hh:mm); exits are taken however late
WINDOWS = {"W1": (0, (23, 30), (23, 59), 1, (3, 30)), "W2": (1, (1, 30), (1, 59), 1, (4, 0))}
CANDIDATE = "W2"                                                  # the 2.13 window; W1 is context only
PINS = {os.path.join("tools", "mapcheck_f.py"): "e14ba5daaac0190a2d2d0d522b8a4bc962013f21db118e20a2ebe9daaab8bc06",
        os.path.join("tools", "rocfrontier", "r12_mdl.py"): "7675875aed479eb83d902fcf4b8385a5bbdce40cbe30b60fde9f2c0ee84562d9",
        os.path.join("tools", "rocfrontier", "r11_risk.py"): "bf8f9ca5410e947f44e1628717fd4d415bdc0707998d14a6ab5ec3656166cd6b"}
MC_ROWS = 10                                                      # MAPCHECK-F's own PRIORS rows before ours are appended
GATE1_T, S_SD = 2.0, 0.15


def lf_sha(p):
    return hashlib.sha256(open(p, "rb").read().replace(b"\r\n", b"\n")).hexdigest()


def switches(root):
    out = []
    with open(os.path.join(SHARED, "tools", "data", "rolls_%s.csv" % root), newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r.get("kind") == "not_a_roll" or not (r.get("old") and r.get("new")):
                continue
            out.append(int(r["switch_sec"]))
    return np.array(sorted(out), dtype=np.int64)


def vix_change():
    """date -> CLOSE(that VIX date) - CLOSE(the VIX date before it); the series is indexed by VIX date."""
    p, sha = VIX
    if hashlib.sha256(open(p, "rb").read()).hexdigest() != sha:
        sys.exit("STOP: the VIX photograph is not its pinned sha (nothing computed)")
    v = pd.read_csv(p)
    v["d"] = pd.to_datetime(v["DATE"], format="%m/%d/%Y")
    v = v.set_index("d")["CLOSE"].astype(float).sort_index()
    v = v[v.index < CUT.tz_localize(None)]
    return v.diff().dropna()


def nights(mkt, o, idx, sw, vchg):
    et = idx.tz_convert("US/Eastern")
    keep = et < CUT
    o, et = o[keep], et[keep]
    secs = (et.tz_convert("UTC").asi8 // 10**9).astype(np.int64)
    day = et.normalize().tz_localize(None)
    mins = (et.hour * 60 + et.minute).to_numpy()
    tdays = pd.DatetimeIndex(sorted(set(day[(mins >= 570) & (mins < 960)])))     # dates with RTH bars = the daily P&L calendar
    vd = vchg.index.values
    rows, skipped_cut = [], {wk: 0 for wk in WINDOWS}
    cal = pd.DatetimeIndex(sorted(set(day)))
    for D in cal:
        # the VIX change known at D's 23:30: the last VIX date on or before D
        j = np.searchsorted(vd, np.datetime64(D), side="right") - 1
        v = float(vchg.iloc[j]) if j >= 0 else np.nan
        def wall(off, hm, sec=0):
            # wall-clock time first, THEN the zone: adding hours to a zoned midnight drifts an hour on a DST Sunday
            return (D + pd.Timedelta(days=off, hours=hm[0], minutes=hm[1], seconds=sec)).tz_localize("US/Eastern")

        def first_at(off, hm, lim):
            p = et.searchsorted(wall(off, hm))
            return p if (p < len(et) and et[p] <= wall(off, lim, 59)) else None
        if first_at(0, (23, 30), (23, 59)) is None:
            continue                                           # not a night: no 23:30 bar on D (decided before any entry)
        for wk, (eo, eh, el, xo, xh) in WINDOWS.items():
            pe = first_at(eo, eh, el)
            if pe is None:
                continue                                       # no entry bar in the entry window: never entered
            tgt = wall(xo, xh)
            px = et.searchsorted(tgt)                          # the exit: first bar at or after the target, however late
            if px >= len(et):
                skipped_cut[wk] += 1                           # the exit lies beyond the pre-WF cut (the last night only)
                continue
            nsw = int(((sw > secs[pe]) & (sw <= secs[px])).sum())
            rows.append(dict(mkt=mkt, win=wk, night=D, exit_day=day[px], v=v, ent=o[pe], ex=o[px], sw=nsw,
                             late=int((et[px] - tgt) >= pd.Timedelta(minutes=30))))
    N = pd.DataFrame(rows)
    print("  %s: entered nights whose exit lies beyond the cut (dropped): %s" % (mkt, skipped_cut), flush=True)
    return N, tdays


def pnl(N, mkt, stress=False):
    return ((N["ex"] - N["ent"]) - COST[mkt] - (STRESS if stress else 0.0) - ROLL_PT * N["sw"]) * MULT[mkt]


def cell_stats(g, nights_dates, yrs):
    g = np.asarray(g, float)
    n = len(g)
    if n < 3:
        return dict(trades=n)
    m, s = g.mean(), g.std(ddof=1)
    by_year = pd.Series(g, index=pd.DatetimeIndex(nights_dates)).groupby(lambda d: d.year).sum()
    tpy = n / yrs
    sh = m / s if s > 0 else float("nan")
    return dict(trades=n, usd_per_trade=round(m, 2), t=round(m / (s / math.sqrt(n)), 2), per_trade_sharpe=round(sh, 4),
                trades_per_year=round(tpy, 1), yearly_sharpe=round(sh * math.sqrt(tpy), 3),
                years_pos="%d/%d" % (int((by_year > 0).sum()), len(by_year)), net=round(g.sum(), 0),
                _tpy=tpy, _ysh=sh * math.sqrt(tpy))           # unrounded, for the gates


def four(daily):
    from augur_engine.drawdowns import dd5, dd_pct_peak
    v = daily.to_numpy(float)
    yrs = (daily.index[-1] - daily.index[0]).days / 365.25
    eq = np.concatenate([[0.0], v.cumsum()])
    dd = float((np.maximum.accumulate(eq) - eq).max())
    roc = 30.0 * (v.sum() / yrs) / dd if dd > 0 else float("nan")
    d5 = dd5(daily)
    k = 30000.0 / dd if dd > 0 else 1.0
    neg = np.minimum(v, 0.0)
    so = float(v.mean() / math.sqrt(float((neg ** 2).mean())) * math.sqrt(252)) if (neg ** 2).mean() > 0 else float("inf")
    return {"roc30": round(roc, 2), "dd5_at_30k": round(float(d5["dd5_usd"]) * k, 0), "one_episode": d5["one_episode"],
            "dd_pct_peak_at_30k": round(dd_pct_peak(daily * k, start=100000.0), 2), "sortino": round(so, 3),
            "net_per_year": round(float(v.sum()) / yrs, 0), "worst_dd": round(dd, 0)}


def main():
    got = lf_sha(PREREG)
    print("prereg LF sha256 %s (frozen %s); harness LF sha256 %s" % (got, PREREG_LF_SHA, lf_sha(os.path.abspath(__file__))), flush=True)
    if got != PREREG_LF_SHA:
        sys.exit("STOP: the prereg is not the frozen one (nothing computed)")
    for rel, want in PINS.items():
        have = lf_sha(os.path.join(SHARED, rel))
        print("pin %s LF sha256 %s" % (rel, have), flush=True)
        if have != want:
            sys.exit("STOP: %s is not the pinned MAPCHECK-F code (nothing computed)" % rel)
    os.chdir(SHARED)
    sys.path.insert(0, SHARED)
    sys.path.insert(0, os.path.join(SHARED, "tools"))
    from augur_engine.data import find_master, load_master_arrays
    vchg = vix_change()
    res, prior_rows, fours = {}, [], {}
    for mkt in ("NQ", "ES"):
        m = find_master(mkt, "5m", "eth", "db_adj_eth")
        assert m["filename"] == "ADJ_%s_5m_ETH.csv" % mkt and int(m["id"]) == {"NQ": 71, "ES": 62}[mkt], m
        A = load_master_arrays(m, date_to="2016-06-30")
        idx = pd.DatetimeIndex(A["index"])
        assert idx.tz is not None, "master index must be tz-aware"
        N, tdays = nights(mkt, np.asarray(A["open"], float), idx, switches(mkt), vchg)
        assert N["exit_day"].max() < CUT.tz_localize(None)
        tdays = tdays.union(pd.DatetimeIndex(N["exit_day"].unique()))       # every exit date is on the daily calendar
        yrs = (tdays[-1] - tdays[0]).days / 365.25
        print("%s: master id %s %s, %s .. %s, %.2f years, nights W1 %d W2 %d, late exits (30+ min) W1 %d W2 %d" % (
            mkt, m["id"], m["filename"], tdays[0].date(), tdays[-1].date(), yrs, (N["win"] == "W1").sum(), (N["win"] == "W2").sum(),
            N[N["win"] == "W1"]["late"].sum(), N[N["win"] == "W2"]["late"].sum()))
        for wk in WINDOWS:
            W = N[N["win"] == wk].reset_index(drop=True)
            g, gs = pnl(W, mkt).values, pnl(W, mkt, stress=True).values
            sel = {"ALL": np.ones(len(W), bool), "UP": (W["v"] > 0).values, "DOWN": (W["v"] < 0).values}
            for sk, s in sel.items():
                st = cell_stats(g[s], W["night"][s], yrs)
                st["stress_usd_per_trade"] = round(float(gs[s].mean()), 2)
                res["%s-%s-%s" % (mkt, wk, sk)] = st
                print("  %s %s %-4s %s" % (mkt, wk, sk, json.dumps({k: v for k, v in st.items() if not k.startswith("_")})))
            a, b = g[sel["UP"]], g[sel["DOWN"]]
            diff = float(a.mean() - b.mean())
            se = math.sqrt(a.var(ddof=1) / len(a) + b.var(ddof=1) / len(b))
            wt = diff / se
            res["%s-%s-UPminusDOWN" % (mkt, wk)] = dict(usd=round(diff, 2), welch_t=round(wt, 3), v_zero=int((W["v"] == 0).sum()))
            print("  %s %s UP-DOWN %+.2f $/trade, Welch t %.3f (v = 0 nights: %d)" % (mkt, wk, diff, wt, (W["v"] == 0).sum()))
            daily = pd.Series(g[sel["UP"]], index=pd.DatetimeIndex(W["exit_day"][sel["UP"]])).groupby(level=0).sum()
            daily = daily.reindex(tdays, fill_value=0.0).astype(float)
            fours["%s-%s-UP" % (mkt, wk)] = four(daily)
            print("  %s %s-UP four numbers (pre-WF, draft read): %s" % (mkt, wk, json.dumps(fours["%s-%s-UP" % (mkt, wk)])))
            if wk == CANDIDATE:
                up = res["%s-%s-UP" % (mkt, wk)]
                prior_rows.append(dict(mkt=mkt, n=float(up["_tpy"]), s=float(up["_ysh"]), welch_t=float(wt),
                                       gate1=bool(diff > 0 and wt >= GATE1_T)))
    os.makedirs(OUT, exist_ok=True)
    import mapcheck_f as MC
    if len(MC.PRIORS) != MC_ROWS:
        sys.exit("STOP: MAPCHECK-F holds %d prior rows, the prereg froze %d (seeds would shift)" % (len(MC.PRIORS), MC_ROWS))
    MC.OUT = OUT
    names, upper = [], []
    for r in prior_rows:
        rows = (("SHELF32-%s-%s-UP (halved)" % (r["mkt"], CANDIDATE), max(0.0, r["s"] / 2.0)),
                ("SHELF32-%s-%s-UP (unhalved, upper bound)" % (r["mkt"], CANDIDATE), r["s"]))
        for lab, s_mid in rows:
            print("MAPCHECK-F row k=%d seed [%d, %d, 0/1]: %s n %.2f s_mid %.4f s_sd %.2f" % (
                len(MC.PRIORS), MC.SEED0, len(MC.PRIORS), lab, r["n"], s_mid, S_SD), flush=True)
            MC.PRIORS.append(dict(name=lab, n=r["n"], s_mid=s_mid, s_sd=S_SD, rho_dd=0.0, rho_out="zero", tails="t3",
                                  vol="clustered",
                                  src="shelf 32 pre-WF rows (2010-06 .. 2016-06): %s 01:30 -> 04:00 ET long on VIX-up nights, yearly "
                                      "Sharpe %.3f after cost%s" % (r["mkt"], r["s"], ", halved" if "(halved)" in lab else "")))
            names.append(lab)
        upper.append(rows[1][0])
    MC.main(names)
    csvp = os.path.join(OUT, "MAPCHECK_F.csv")
    mc = pd.read_csv(csvp).set_index("name")
    for lab in upper:                                          # the prereg: the upper-bound row is printed, never judged
        mc.loc[lab, "verdict"] = "upper bound - not judged (the map alone said: %s)" % mc.loc[lab, "verdict"]
    mc.reset_index().to_csv(csvp, index=False)
    with open(os.path.join(OUT, "MAPCHECK_F.txt"), "a", encoding="utf-8") as fh:
        fh.write("\nNOTE (shelf 32 prereg): the '(unhalved, upper bound)' rows are printed, never judged; their '->' lines above are "
                 "the map's mechanical output, not a verdict.\n")
    verdict = {}
    for r in prior_rows:
        v = str(mc.loc["SHELF32-%s-%s-UP (halved)" % (r["mkt"], CANDIDATE), "verdict"])
        clears = v.startswith("CLEARS") and r["gate1"]
        verdict[r["mkt"]] = ("CLEARS - full prereg" if clears else "CLOSE AT DRAFT (gate 1 split t %.2f %s 2.0; gate 2 map: %s)" % (
            r["welch_t"], ">=" if r["gate1"] else "<", v))
        print("VERDICT %s: %s" % (r["mkt"], verdict[r["mkt"]]))
    clean = {k: {kk: vv for kk, vv in v.items() if not kk.startswith("_")} for k, v in res.items()}
    json.dump(dict(prereg_lf_sha=got, harness_lf_sha=lf_sha(os.path.abspath(__file__)), cells=clean, four_up=fours,
                   priors=prior_rows, verdict=verdict), open(os.path.join(OUT, "result.json"), "w"), indent=1, default=float)
    print("wrote", OUT)


if __name__ == "__main__":
    main()
