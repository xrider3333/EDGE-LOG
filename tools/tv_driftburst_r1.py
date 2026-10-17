# DRIFTBURST r1 (prereg docs/PREREG_tv_driftburst_r1_2026-10-16.md): fade a volatility-normalised k-minute drift burst on NQ / ES 1m,
# PRE-WF rows only (2010-06-06 .. 2016-06-30), 24 cells per market (CROSS / EXHAUST entry), direction-randomised family-wise null, MAPCHECK-F (pinned) on the
# candidate. Checks the prereg's LF sha256 and the MAPCHECK-F pins at start; nothing is computed on a mismatch.
#   python tools/tv_driftburst_r1.py
import csv, hashlib, itertools, json, math, os, sys
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
SHARED = r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"
PREREG = os.path.join(HERE, "..", "docs", "PREREG_tv_driftburst_r1_2026-10-16.md")
PREREG_LF_SHA = "03e47387374f1e602ff2b014a1dc08a403b59768c42943f2879fca9fe6f7fbed"
OUT = r"C:\EdgeLog\_research_cache\tv_scalp\driftburst_r1"
CUT = pd.Timestamp("2016-07-01 00:00", tz="US/Eastern")
FROM, TO = "2010-06-06", "2016-06-30"
YEARS = (pd.Timestamp(TO) - pd.Timestamp(FROM)).days / 365.25
MASTERS = {"NQ": (34, "NOADJ_NQ_1m_ETH.csv"), "ES": (30, "NOADJ_ES_1m_ETH.csv")}
MULT = {"NQ": 20.0, "ES": 50.0}
COST = {"NQ": 0.706, "ES": 0.582}
STRESS = 0.25
MODES, KS, CS, HS = ("CROSS", "EXHAUST"), (5, 15, 30), (4.0, 6.0), (15, 60)
CELLS = list(itertools.product(MODES, KS, CS, HS))
SCAN = 30                                                       # EXHAUST: the first counter-move within 30 bars
GAP_S, LOOKBACK, MIN_PRESENT = 300, 20, 15
SPAN_SLACK_S = 120                                              # a k-bar window may span at most k minutes + 2 (missing minutes inflate T)
MIN_MKT_TRADES = 61                                             # t2: >= 10 a year in EACH market
MACRO = set(range(510, 516)) | set(range(600, 606)) | set(range(750, 756)) | set(range(840, 846)) | set(range(855, 861))
NULL_REPS, SEED = 1000, 20261016
PINS = {os.path.join("tools", "mapcheck_f.py"): "e14ba5daaac0190a2d2d0d522b8a4bc962013f21db118e20a2ebe9daaab8bc06",
        os.path.join("tools", "rocfrontier", "r12_mdl.py"): "7675875aed479eb83d902fcf4b8385a5bbdce40cbe30b60fde9f2c0ee84562d9",
        os.path.join("tools", "rocfrontier", "r11_risk.py"): "bf8f9ca5410e947f44e1628717fd4d415bdc0707998d14a6ab5ec3656166cd6b"}
MC_ROWS = 10


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


def prepare(o, c, idx, sw):
    """per bar: secs, NY date, trade date, minute-of-day, segment id, r, and the diurnal variance v (the previous 20 dates on
    which that minute traded, >= 15 of them inside the last 20 such dates; roll-switch bars never enter it)."""
    et = idx.tz_convert("US/Eastern")
    keep = et < CUT
    o, c, et = o[keep], c[keep], et[keep]
    secs = (et.tz_convert("UTC").asi8 // 10**9).astype(np.int64)
    date = et.normalize().tz_localize(None)
    mod = (et.hour * 60 + et.minute).to_numpy()
    gap = np.r_[True, np.diff(secs) > GAP_S]
    seg = np.cumsum(gap)
    lc = np.log(c)
    r = np.r_[0.0, np.diff(lc)]
    r[gap] = 0.0
    roll_bar = np.r_[False, np.searchsorted(sw, secs[1:], side="right") != np.searchsorted(sw, secs[:-1], side="right")]
    r2 = np.where(gap | roll_bar, np.nan, r * r)              # a segment's first bar and a roll-switch bar give no return
    df = pd.DataFrame({"date": date, "m": mod, "r2": r2})
    piv = df.pivot_table(index="date", columns="m", values="r2", aggfunc="mean")
    V = pd.DataFrame(np.nan, index=piv.index, columns=piv.columns)
    for col in piv.columns:                                   # per minute: only the dates on which that minute traded
        sc = piv[col].dropna()
        V.loc[sc.index, col] = sc.shift(1).rolling(LOOKBACK, min_periods=MIN_PRESENT).mean().to_numpy()
    di = V.index.get_indexer(date)
    mi = V.columns.get_indexer(mod)
    v = V.to_numpy()[di, mi]
    tdate = (et + pd.Timedelta(hours=6)).normalize().tz_localize(None)   # CME trade date: 18:00 ET and later books to the next date
    rth = (mod >= 570) & (mod < 960)
    return dict(o=o, c=c, lc=lc, r=r, secs=secs, date=date, tdate=tdate, rth_dates=pd.DatetimeIndex(sorted(set(date[rth]))),
                mod=mod, seg=seg, v=v, n=len(c))


def drift_t(P, k):
    lc, seg, v = P["lc"], P["seg"], P["v"]
    n = P["n"]
    T = np.full(n, np.nan)
    if n <= k:
        return T
    bad = ~np.isfinite(v)
    vs = np.r_[0.0, np.cumsum(np.where(bad, 0.0, v))]
    ns = np.r_[0, np.cumsum(bad)]
    vsum = vs[k + 1:] - vs[1:n - k + 1]                                       # sum of v over bars t-k+1 .. t, for t = k .. n-1
    nbad = ns[k + 1:] - ns[1:n - k + 1]                                       # any missing v inside the window kills it
    span_ok = (P["secs"][k:] - P["secs"][:-k]) <= 60 * k + SPAN_SLACK_S
    same = (seg[k:] == seg[:-k]) & (nbad == 0) & span_ok
    num = lc[k:] - lc[:-k]
    with np.errstate(invalid="ignore", divide="ignore"):
        tt = num / np.sqrt(vsum)
    tt[~same | ~np.isfinite(tt) | (vsum <= 0)] = np.nan
    T[k:] = tt
    return T


def trades_for(P, sw, mkt, mode, k, cth, H):
    T = drift_t(P, k)
    n, secs, o, r, seg = P["n"], P["secs"], P["o"], P["r"], P["seg"]
    prev = np.r_[np.nan, T[:-1]]
    fresh = (np.abs(T) >= cth) & np.isfinite(prev) & (np.abs(prev) < cth)     # the prereg: |T_t-1| < c, so T_t-1 must exist
    cand = np.flatnonzero(fresh)
    out, flat_from = [], 0
    for t in cand:
        if t < flat_from or t - k < 0:
            continue
        side = -1.0 if T[t] > 0 else 1.0
        if mode == "CROSS":
            j = t
        else:
            j = None
            for q in range(t + 1, min(t + 1 + SCAN, n)):
                if seg[q] != seg[t]:
                    break
                if r[q] * side > 0:                                           # a 1-minute return against the drift (with the fade)
                    j = q
                    break
            if j is None:
                flat_from = min(t + 1 + SCAN, n)                              # the scanned burst is spent; its window is closed
                continue
        skip_to = j + 1 if mode == "EXHAUST" else flat_from                   # a skipped EXHAUST trade still owns its scan window
        if j + 1 + H >= n or secs[j + 1] - secs[j] > GAP_S:                  # no entry bar right after the trigger bar
            flat_from = skip_to
            continue
        e, x = j + 1, j + 1 + H
        if seg[x] != seg[e]:                                                  # the hold would cross a gap / the daily halt / a weekend
            flat_from = skip_to
            continue
        lo_w, hi_w = secs[t - k], secs[j]
        if np.searchsorted(sw, lo_w, side="right") != np.searchsorted(sw, hi_w, side="right"):
            flat_from = skip_to
            continue                                                          # the signal window straddles a roll switch
        if np.searchsorted(sw, secs[e], side="right") != np.searchsorted(sw, secs[x], side="right"):
            flat_from = skip_to
            continue                                                          # the hold would straddle a roll switch
        move = o[x] - o[e]
        out.append((t, e, x, side, move, P["tdate"][x], P["mod"][t], secs[e], secs[x]))
        flat_from = x
    df = pd.DataFrame(out, columns=["t", "e", "x", "side", "move", "exit_day", "sig_mod", "e_sec", "x_sec"])
    df["mkt"] = mkt
    df["net"] = df["side"] * df["move"] - COST[mkt]
    df["net_usd"] = df["net"] * MULT[mkt]
    df["stress_net"] = df["net"] - STRESS
    return df


def four(daily):
    from augur_engine.drawdowns import dd5, dd_pct_peak
    v = daily.to_numpy(float)
    yrs = max((daily.index[-1] - daily.index[0]).days, 1) / 365.25
    eq = np.concatenate([[0.0], v.cumsum()])
    dd = float((np.maximum.accumulate(eq) - eq).max())
    roc = 30.0 * (v.sum() / yrs) / dd if dd > 0 else float("inf")
    d5 = dd5(daily)
    k = 30000.0 / dd if dd > 0 else 1.0
    neg = np.minimum(v, 0.0)
    so = float(v.mean() / math.sqrt(float((neg ** 2).mean())) * math.sqrt(252)) if (neg ** 2).mean() > 0 else float("inf")
    return dict(roc30=round(roc, 2), dd5_at_30k=round(float(d5["dd5_usd"]) * k, 0), one_episode=bool(d5["one_episode"]),
                dd_pct_peak_at_30k=round(float(dd_pct_peak(daily * k, start=100000.0)), 2), sortino=round(so, 3),
                net_per_year=round(float(v.sum()) / yrs, 0), worst_dd=round(dd, 0))


def stats(df, col, cal):
    g = df[col].to_numpy(float)
    n = len(g)
    if n < 3:
        return dict(trades=n)
    w, l = g[g > 0], g[g <= 0]
    m, s = g.mean(), g.std(ddof=1)
    tpy = n / YEARS
    yrs = df.groupby(pd.DatetimeIndex(df["exit_day"]).year)[col].sum()
    usd = df["net_usd"] if col == "net" else df["net_usd"] - STRESS * df["mkt"].map(MULT)
    daily = usd.groupby(pd.DatetimeIndex(df["exit_day"])).sum().reindex(cal, fill_value=0.0).astype(float)
    macro = df["sig_mod"].isin(MACRO).mean()
    out = dict(trades=n, trades_per_year=tpy, win_rate=float((g > 0).mean()), avg_win=float(w.mean()) if len(w) else 0.0,
               avg_loss=float(-l.mean()) if len(l) else 0.0, net_pf=float(w.sum() / -l.sum()) if l.sum() < 0 else float("inf"),
               net_sum=float(g.sum()), mean=float(m), t=float(m / (s / math.sqrt(n))) if s > 0 else None,
               yearly_sharpe=float(m / s * math.sqrt(tpy)) if s > 0 else None,
               years_pos="%d/%d" % (int((yrs > 0).sum()), len(yrs)), macro_minute_share=float(macro))
    out.update(four(daily))
    return out


def clusters(frames):
    """global burst clusters: trades (any cell, either market) whose holds overlap in time share one id"""
    allt = pd.concat(frames, ignore_index=True)[["e_sec", "x_sec"]].sort_values("e_sec")
    gid = np.zeros(len(allt), np.int64)
    cur, end = -1, -1
    for pos, (a, b) in enumerate(zip(allt["e_sec"].to_numpy(), allt["x_sec"].to_numpy())):
        if a > end:
            cur += 1
            end = b
        else:
            end = max(end, b)
        gid[pos] = cur
    out = pd.Series(gid, index=allt.index)
    return out, cur + 1


def cell_clusters(df):
    """one row per global cluster inside the cell: summed gross $, cost $, net $ (NQ and ES on one burst = one event)"""
    gross = df["side"] * df["move"] * df["mkt"].map(MULT)
    cost = df["mkt"].map(COST) * df["mkt"].map(MULT)
    g = pd.DataFrame({"gid": df["gid"], "gross": gross, "cost": cost}).groupby("gid").sum()
    g["net"] = g["gross"] - g["cost"]
    return g


def tstat(x):
    x = np.asarray(x, float)
    if len(x) < 3:
        return None
    sd = x.std(ddof=1)
    return float(x.mean() / (sd / math.sqrt(len(x)))) if sd > 0 else None


def finite(x):
    if isinstance(x, dict):
        return {str(k): finite(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [finite(v) for v in x]
    if isinstance(x, (float, np.floating)):
        return float(x) if math.isfinite(x) else str(x)
    if isinstance(x, np.integer):
        return int(x)
    if isinstance(x, np.bool_):
        return bool(x)
    return x


def main():
    got = lf_sha(PREREG)
    print("prereg LF sha256 %s (frozen %s); harness LF sha256 %s" % (got, PREREG_LF_SHA, lf_sha(os.path.abspath(__file__))), flush=True)
    if got != PREREG_LF_SHA:
        sys.exit("STOP: the prereg is not the frozen one (nothing computed)")
    for rel, want in PINS.items():
        have = lf_sha(os.path.join(SHARED, rel))
        print("pin %s %s" % (rel, have), flush=True)
        if have != want:
            sys.exit("STOP: %s is not the pinned MAPCHECK-F code (nothing computed)" % rel)
    os.chdir(SHARED)
    sys.path.insert(0, SHARED)
    sys.path.insert(0, os.path.join(SHARED, "tools"))
    from augur_engine.data import find_master, load_master_arrays
    os.makedirs(OUT, exist_ok=True)
    T_ALL, cal = {}, None
    for mkt, want in MASTERS.items():
        m = find_master(mkt, "1m", "eth", "db_noadj_eth")
        if not m or (int(m.get("id") or 0), m.get("filename")) != want:
            sys.exit("STOP: %s master is not id %s %s: %r" % (mkt, want[0], want[1], m))
        A = load_master_arrays(m, date_from=FROM, date_to=TO)
        idx = pd.DatetimeIndex(A["index"])
        assert idx.tz is not None
        sw = switches(mkt)
        P = prepare(np.asarray(A["open"], float), np.asarray(A["close"], float), idx, sw)
        del A
        days = P["rth_dates"]                                  # the daily calendar: NY dates with RTH bars (+ every exit date below)
        cal = days if cal is None else cal.union(days)
        print("%s: id %s %s, %d bars %s .. %s, v present %.1f%%" % (mkt, m["id"], m["filename"], P["n"], days[0].date(),
                                                                   days[-1].date(), 100 * np.isfinite(P["v"]).mean()), flush=True)
        for cell in CELLS:
            T_ALL[(mkt,) + cell] = trades_for(P, sw, mkt, *cell)
        del P
    frames = [f for f in T_ALL.values() if len(f)]
    for f in frames:
        cal = cal.union(pd.DatetimeIndex(f["exit_day"].unique()))
    gid, n_clusters = clusters(frames)
    gidv = gid.sort_index().to_numpy()                        # back in concat order (frames in order)
    off = 0
    for f in frames:
        f["gid"] = gidv[off:off + len(f)]
        off += len(f)
    print("global burst clusters (overlapping holds, any cell, either market): %d" % n_clusters, flush=True)
    res, CC = {}, {}
    for cell in CELLS:
        key = "%s k%d c%g H%d" % cell
        res[key] = {}
        for mkt in MASTERS:
            df = T_ALL[(mkt,) + cell]
            res[key][mkt] = dict(house=stats(df, "net", cal), stress=stats(df, "stress_net", cal)) if len(df) >= 3 else dict(trades=len(df))
        both = pd.concat([T_ALL[(mk,) + cell] for mk in MASTERS if len(T_ALL[(mk,) + cell])], ignore_index=True)
        cc = cell_clusters(both) if len(both) else pd.DataFrame(columns=["gross", "cost", "net"])
        CC[key] = cc
        res[key]["pooled_t_usd"] = tstat(cc["net"]) if len(cc) > 2 else None              # one event per burst cluster
        res[key]["pooled_mean_net_usd"] = float(cc["net"].mean()) if len(cc) else None
        res[key]["pooled_events_per_year"] = len(cc) / YEARS
        res[key]["pooled_trades_per_year"] = len(both) / YEARS
        res[key]["momentum_mirror_t_gross"] = tstat(-cc["gross"]) if len(cc) > 2 else None
        print("%-22s NQ %s | ES %s | pooled t %s, %.0f events/yr" % (key, json.dumps(finite({x: res[key]["NQ"].get("house", {}).get(x) for x in ("trades", "net_pf", "mean", "t")})),
              json.dumps(finite({x: res[key]["ES"].get("house", {}).get(x) for x in ("trades", "net_pf", "mean", "t")})),
              res[key]["pooled_t_usd"], res[key]["pooled_events_per_year"]), flush=True)

    # family-wise null: ONE random sign per global burst cluster (shared by both markets and all cells), cost unchanged;
    # the statistic is the max over the 24 cells of the pooled cluster t - the same statistic the candidate is picked on
    rng = np.random.default_rng(SEED)
    signs = rng.choice([-1.0, 1.0], size=(NULL_REPS, n_clusters))
    mx = np.full(NULL_REPS, -np.inf)
    for key, cc in CC.items():
        if len(cc) < 3:
            continue
        g = signs[:, cc.index.to_numpy(np.int64)] * cc["gross"].to_numpy(float)[None, :] - cc["cost"].to_numpy(float)[None, :]
        sd = g.std(1, ddof=1)
        tt = np.where(sd > 0, g.mean(1) / (sd / math.sqrt(len(cc))), -np.inf)
        mx = np.maximum(mx, tt)
    null95 = float(np.quantile(mx, 0.95))
    cand = max((k for k in res if res[k]["pooled_t_usd"] is not None), key=lambda k: res[k]["pooled_t_usd"])
    C = res[cand]
    print("\nCANDIDATE %s: pooled cluster t %.3f vs family-wise null 95th pct %.3f; %.1f events/yr" % (
        cand, C["pooled_t_usd"], null95, C["pooled_events_per_year"]), flush=True)
    parts = cand.split()
    cell = (parts[0],) + tuple(int(x[1:]) if x[0] != "c" else float(x[1:]) for x in parts[1:])
    both = pd.concat([T_ALL[(mk,) + cell] for mk in MASTERS if len(T_ALL[(mk,) + cell])], ignore_index=True)
    ev = CC[cand]["net"].to_numpy(float)
    tpy = len(ev) / YEARS                                                     # events (burst clusters) a year, not trades
    ysh = float(ev.mean() / ev.std(ddof=1) * math.sqrt(tpy)) if len(ev) > 2 and ev.std(ddof=1) > 0 else 0.0
    daily = both["net_usd"].groupby(pd.DatetimeIndex(both["exit_day"])).sum().reindex(cal, fill_value=0.0).astype(float)
    C["pooled_four"] = four(daily)
    C["pooled_yearly_sharpe_usd"] = ysh
    print("candidate pooled four numbers (pre-WF draft read): %s; yearly Sharpe %.3f" % (json.dumps(finite(C["pooled_four"])), ysh), flush=True)

    import mapcheck_f as MC
    if len(MC.PRIORS) != MC_ROWS:
        sys.exit("STOP: MAPCHECK-F holds %d prior rows, the prereg froze %d" % (len(MC.PRIORS), MC_ROWS))
    MC.OUT = OUT
    lab = "DRIFTBURST %s (halved)" % cand
    print("MAPCHECK-F row k=%d seed [%d, %d, 0/1]: %s n %.2f s_mid %.4f" % (len(MC.PRIORS), MC.SEED0, len(MC.PRIORS), lab, tpy, max(0.0, ysh / 2)), flush=True)
    MC.PRIORS.append(dict(name=lab, n=tpy, s_mid=max(0.0, ysh / 2.0), s_sd=0.25, rho_dd=0.0, rho_out="zero", tails="t3", vol="clustered",
                          src="DRIFTBURST r1 pre-WF rows 2010-06..2016-06, NQ+ES pooled, yearly Sharpe %.3f after cost, halved" % ysh))
    MC.main([lab])
    mc = pd.read_csv(os.path.join(OUT, "MAPCHECK_F.csv")).set_index("name")
    mv = str(mc.loc[lab, "verdict"])
    tests = dict(t1_null=bool(C["pooled_t_usd"] > null95 and (C["pooled_mean_net_usd"] or 0) > 0),
                 t2_both=bool(all((C[mk].get("house", {}).get("trades") or 0) >= MIN_MKT_TRADES
                                  and (C[mk].get("house", {}).get("net_pf") or 0) > 1.0 for mk in MASTERS)),
                 t3_count=bool(C["pooled_events_per_year"] >= 50), t4_map=mv.startswith("CLEARS"))
    names = dict(t1_null="not above the family-wise null with a positive net", t2_both="does not earn in both markets (>= 61 trades each)",
                 t3_count="too thin (< 50 events a year)", t4_map="MAPCHECK-F: %s" % mv)
    verdict = "CLEARS - full prereg" if all(tests.values()) else "CLOSED AT DRAFT: " + "; ".join(names[k] for k, v in tests.items() if not v)
    print("VERDICT:", verdict, flush=True)
    json.dump(finite(dict(prereg_lf_sha=got, harness_lf_sha=lf_sha(os.path.abspath(__file__)), cells=res, null95=null95,
                          candidate=cand, tests=tests, verdict=verdict)), open(os.path.join(OUT, "result.json"), "w"), indent=1,
              default=str, allow_nan=False)
    print("wrote", OUT, flush=True)


if __name__ == "__main__":
    main()
