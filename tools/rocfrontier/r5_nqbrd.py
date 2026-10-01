# ALPACA r1 family B - NQBRD: an NQ trend-day trigger from Nasdaq-100 breadth at 10:00 ET.
# Pre-registered: tools/rocfrontier/PREREG_ALPACA_R1.txt (canonical sha256 = committed blob a038a85c...0ee3, main 2ba5b3db, + its pre-data
# ADDENDUM of 2026-09-30 evening -> canonical LF sha256 bda72203...f41d).
# Membership: tools/data/ndx_members.csv (tools/rocfrontier/build_ndx_members.py), built before any stock bar existed.
#   python r5_nqbrd.py pull     needs the owner's Alpaca keys (env ALPACA_API_KEY / ALPACA_SECRET_KEY); 09:30-10:00 5-minute
#                               bars of each day's members -> research cache (never a library master); ~15 minutes; a day that
#                               returns no bars at all is recorded in empty_days.txt ('never pulled' vs 'nothing there')
#   python r5_nqbrd.py A        breadth + Stage A + A2, PRE-LOCKBOX ONLY (nothing on/after 2025-06-30 is computed); stops if any WF
#                               session of the NQ master is neither pulled nor recorded empty; a day counts only if >= 80% of its
#                               members returned both bars (prereg addendum 2); A2 needs BOOK #463's WF numbers to reproduce
#   python r5_nqbrd.py B        Stage B (lockbox, once) - refuses unless A2 passed; the READ flag is written only after the lockbox
#                               data has loaded and BOOK #463's LB numbers reproduce
import json, os, sys, time
REPO = os.environ.get("EDGELOG_ROOT", r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"); sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "tools")); sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np, pandas as pd

OUT = os.environ.get("EDGELOG_ALPACA_R1", r"C:\EdgeLog\_anatomy_cache\rocfrontier\alpaca_r1")   # results, outside git
CACHE = os.environ.get("EDGELOG_ALPACA_CACHE", r"C:\EdgeLog\alpaca_cache")                     # raw research pulls
BOOK = os.path.join(os.path.dirname(OUT), "r4", "book463_daily.csv")
BW0, WF0, LB0, LB1 = (pd.Timestamp(x) for x in ("2010-06-07", "2016-07-01", "2025-06-30", "2026-06-30"))
LBX, LBY = pd.Timestamp("2026-07-01"), (LB1 - LB0).days / 365.25   # LB = 06-30 .. 06-30 INCLUSIVE, frontier years
THETAS, COST, MULT, STRESS, NREP = (0.70, 0.80), 0.533, 20.0, 0.25, 500
COVER = 0.80                                              # coverage guard (prereg addendum 2): a day counts only if >= 80% of its members have both bars
BOOK_WF, BOOK_LB = (92.70, 3.816), (164.76, 4.150)        # BOOK #463 ROC@30k, Sortino (prereg); the book file must reproduce them (within 0.006 / 0.0006)
rng = np.random.default_rng(20260930)


# ------------------------------------------------------------------ pull (keys required)
def fetch_window(symbols, day, key, secret):
    """09:30-10:00 ET 5-minute bars for many symbols on one day; asof=day maps renamed tickers (FB -> META)."""
    import requests
    t0 = pd.Timestamp(f"{day} 09:30", tz="US/Eastern").tz_convert("UTC")
    t1 = pd.Timestamp(f"{day} 10:00", tz="US/Eastern").tz_convert("UTC")
    heads = {"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret}
    rows, token = [], None
    while True:
        params = {"symbols": ",".join(symbols), "timeframe": "5Min", "start": t0.isoformat(), "end": t1.isoformat(),
                  "limit": 10000, "adjustment": "raw", "feed": "sip", "sort": "asc"}
        if not getattr(fetch_window, "no_asof", False):
            params["asof"] = day
        if token:
            params["page_token"] = token
        r = requests.get("https://data.alpaca.markets/v2/stocks/bars", headers=heads, params=params, timeout=60)
        if r.status_code == 429:
            time.sleep(20); continue
        if r.status_code in (401, 403):
            raise SystemExit(f"AUTH FAILED ({r.status_code}) - check the Alpaca keys")
        if r.status_code in (400, 422) and "asof" in params and "asof" in r.text.lower():
            print("  endpoint rejected asof - continuing without it (renamed tickers may then miss bars)", flush=True)
            fetch_window.no_asof = True
            params.pop("asof"); continue
        if r.status_code != 200:
            raise RuntimeError(f"HTTP {r.status_code}: {r.text[:300]}")
        js = r.json()
        for sym, bars in (js.get("bars") or {}).items():
            rows += [(sym, b["t"], b["o"], b["c"]) for b in bars]
        token = js.get("next_page_token")
        time.sleep(0.31)                                   # ~195 requests a minute, under the free plan's 200
        if not token:
            return rows


def master_days(d0, d1):
    """session days (YYYY-MM-DD) of the NQ 5m RTH master between two dates inclusive; `pull` and the coverage check use the same list"""
    from augur_engine import data
    m = data.find_master("NQ", "5m", "rth", "db_adj_rth")
    return sorted({str(d.date()) for d in pd.DatetimeIndex(data.load_master_arrays(m, d0, d1)["index"]).tz_localize(None).normalize()})


def pulled_days(last=None):
    """(days with bars in the pull cache, days recorded empty = the request ran and nothing came back), cut to days <= `last` if given"""
    p, e = os.path.join(CACHE, "nqbrd", "open_bars.csv"), os.path.join(CACHE, "nqbrd", "empty_days.txt")
    got = set(pd.read_csv(p, usecols=["day"])["day"]) if os.path.exists(p) else set()
    empty = {x.strip() for x in open(e) if x.strip()} if os.path.exists(e) else set()
    return tuple({d for d in s if last is None or d <= last} for s in (got, empty))


def missing_days(d0, d1):
    """session days of the NQ master in [d0, d1] that are neither in the pull cache nor recorded empty (prereg addendum 2)"""
    got, empty = pulled_days(d1)
    return [d for d in master_days(d0, d1) if d not in got and d not in empty]


def pull():
    from import_alpaca_stocks import load_keys            # the shared loader's key lookup (env first)
    from build_ndx_members import members_on
    key, secret = load_keys()
    if not (key and secret):
        raise SystemExit("No Alpaca keys yet - the owner saves ALPACA_API_KEY / ALPACA_SECRET_KEY (ALPACA_STAGE_R1.md).")
    days = master_days("2016-06-01", "2026-09-30")
    os.makedirs(os.path.join(CACHE, "nqbrd"), exist_ok=True)
    path, epath = os.path.join(CACHE, "nqbrd", "open_bars.csv"), os.path.join(CACHE, "nqbrd", "empty_days.txt")
    done = set().union(*pulled_days())                    # bars on file + days that came back empty (not asked again)
    for i, day in enumerate(d for d in days if d not in done):
        rows = fetch_window(members_on(day), day, key, secret)
        if rows:
            pd.DataFrame(rows, columns=["symbol", "t", "o", "c"]).assign(day=day).to_csv(path, mode="a", header=not os.path.exists(path), index=False)
        else:
            open(epath, "a").write(day + "\n"); print(day, "no bars returned - recorded in empty_days.txt", flush=True)    # asked, nothing came back: recorded, so 'never pulled' and 'nothing there' differ
        if i % 100 == 0:
            print(day, len(rows), "bars", flush=True)


# ------------------------------------------------------------------ breadth and the NQ leg
def breadth(t_end):
    """-> (B and n by day, days dropped by the coverage guard)"""
    from build_ndx_members import members_on
    raw = pd.read_csv(os.path.join(CACHE, "nqbrd", "open_bars.csv"))
    raw = raw[pd.to_datetime(raw["day"]) < t_end]                              # cut BEFORE anything is computed
    t = pd.to_datetime(raw["t"], utc=True).dt.tz_convert("US/Eastern")
    raw["hm"] = t.dt.hour * 60 + t.dt.minute
    o = raw[raw.hm == 570].set_index(["day", "symbol"])["o"]
    c = raw[raw.hm == 595].set_index(["day", "symbol"])["c"]
    j = pd.concat([o, c], axis=1, join="inner").dropna()
    b = (j["c"] > j["o"]).groupby(level=0).mean()
    n = j.groupby(level=0).size()
    # coverage guard (prereg addendum 2): a day counts only if >= 80% of that day's members returned both bars; the rest get no trade
    need = {}
    for d in n.index:                                                          # membership is monthly: one lookup a month
        if d[:7] not in need:
            need[d[:7]] = len(members_on(d))
    ok = np.array([k >= COVER * need[d[:7]] - 1e-9 for d, k in n.items()], bool)
    dropped = [str(d) for d in n.index[~ok]]
    b, n = b[ok], n[ok]
    return pd.DataFrame({"B": b, "n": n}).rename_axis("day").set_index(pd.to_datetime(b.index)), dropped


def nq_days(t0, t1):
    from augur_engine import data
    m = data.find_master("NQ", "5m", "rth", "db_adj_rth")
    a = data.load_master_arrays(m, str(t0.date()), str((t1 - pd.Timedelta(days=1)).date()))
    df = pd.DataFrame({k: np.asarray(a[k], float) for k in ("open", "close")}, index=a["index"])
    df = df[(df.index >= t0.tz_localize("US/Eastern")) & (df.index < t1.tz_localize("US/Eastern"))]
    hm = df.index.hour * 60 + df.index.minute
    day = df.index.tz_localize(None).normalize()
    g = pd.DataFrame({"day": day, "hm": hm, "open": df["open"].to_numpy(), "close": df["close"].to_numpy()})
    piv = {k: g[g.hm == h].set_index("day")[col] for k, h, col in (("o930", 570, "open"), ("c955", 595, "close"),
                                                                   ("o1000", 600, "open"), ("c1555", 955, "close"))}
    return pd.DataFrame(piv).dropna()


def trades(nq, sign, cost_add=0.0):
    s = sign[sign != 0]
    x = nq.reindex(s.index).dropna()
    s = s.reindex(x.index)
    pnl = (s * (x["c1555"] - x["o1000"]) - COST - cost_add) * MULT
    return pd.DataFrame({"date": x.index, "side": s.values, "gross": (s * (x["c1555"] - x["o1000"])).values, "pnl": pnl.values})


def ddmax(x):
    q = np.cumsum(x)
    return float((np.maximum.accumulate(np.concatenate([[0.0], q]))[1:] - q).max()) if len(q) else 0.0


def so(x):
    x = np.asarray(x, float)
    dn = np.sqrt(np.mean(np.minimum(x, 0.0) ** 2)) if len(x) else 0.0
    return float(x.mean() / dn * np.sqrt(252)) if dn > 0 else float("nan")


def stats(tr, days, t0, t1):
    t = tr[(tr.date >= t0) & (tr.date < t1)]
    d = t.groupby("date")["pnl"].sum().reindex(days[(days >= t0) & (days < t1)]).fillna(0.0)
    yrs, n, net = (t1 - t0).days / 365.25, len(t), float(t["pnl"].sum())
    gw, gl, ddv = float(t.pnl[t.pnl > 0].sum()), float(-t.pnl[t.pnl < 0].sum()), ddmax(d.values)
    sd = float(t.pnl.std(ddof=1)) if n > 1 else float("nan")
    by = t.groupby(t.date.dt.year)["pnl"].sum()
    return {"n": n, "net": net, "pf": gw / gl if gl > 0 else float("inf"), "dd_daily": ddv,
            "roc30": 30.0 * (net / yrs) / ddv if ddv > 0 else float("nan"), "sortino": so(d.values),
            "t": float(t.pnl.mean() / (sd / np.sqrt(n))) if n > 1 and sd > 0 else float("nan"),
            "years_pos": float((by > 0).mean()) if len(by) else 0.0, "net_ex_big": net - (float(t.pnl.max()) if n else 0.0)}


def book(extra, t0, t1, yrs=None):
    b = pd.read_csv(BOOK, parse_dates=["date"]).set_index("date")
    idx = b.index.union(extra.index) if extra is not None else b.index
    M, C = b["mtm"].reindex(idx).fillna(0.0), b["close"].reindex(idx).fillna(0.0)
    if extra is not None:
        e = extra.reindex(idx).fillna(0.0); M, C = M + e, C + e
    sel = (idx >= t0) & (idx < t1)
    yrs, net, ddv = yrs or (t1 - t0).days / 365.25, float(C[sel].sum()), ddmax(M[sel].values)
    return {"net": net, "roc30": net / yrs / 1000 * 30000 / ddv, "sortino": so(M[sel].values), "big": float(C[sel].max())}


def stage_a():
    last = f"{LB0 - pd.Timedelta(days=1):%Y-%m-%d}"                           # 2025-06-29, the last pre-lockbox day
    miss = missing_days(f"{WF0:%Y-%m-%d}", last)                              # prereg addendum 2: every WF session must be pulled or recorded empty
    if miss:
        raise SystemExit(f"Stage A refused: {len(miss)} WF session days of the NQ master are neither in the pull cache nor recorded empty "
                         f"(first {miss[0]}, last {miss[-1]}) - run `pull` first; nothing was computed")
    empty = sorted(pulled_days(last)[1])
    br, dropped = breadth(LB0)
    nq = nq_days(WF0 - pd.Timedelta(days=400), LB0)
    days = nq.index
    br = br.reindex(days)
    print(f"breadth days {br.B.notna().sum()} of {len(days)}; coverage guard dropped {len(dropped)} pulled days (< {COVER:.0%} of that day's members "
          f"returned both bars; no trade), {len(empty)} days recorded empty; members with bars per day median {br.n.median():.0f} (min {br.n.min():.0f})")
    res, tr = {}, {}
    ret30 = nq["c955"] - nq["o930"]
    for th in THETAS:
        sign = pd.Series(np.where(br.B >= th, 1, np.where(br.B <= 1 - th, -1, 0)), index=days)
        tr[th] = trades(nq, sign)
        # control: NQ's own first-half-hour direction on the same number of days per year, largest |move| first
        ctrl = pd.Series(0, index=days)
        per_year = tr[th].groupby(tr[th].date.dt.year).size()
        for y, k in per_year.items():
            r = ret30[ret30.index.year == y]
            pick = r.abs().sort_values(ascending=False).index[:k]
            ctrl.loc[pick] = np.sign(r.loc[pick]).astype(int)
        tc = trades(nq, ctrl)
        ts_ = trades(nq, sign, STRESS)
        res[th] = {"WF": stats(tr[th], days, WF0, LB0), "control": stats(tc, days, WF0, LB0),
                   "stress_net": float(ts_[ts_.date >= WF0].pnl.sum())}
    null = []
    for _ in range(NREP):
        best = -np.inf
        for th in THETAS:
            t = tr[th][tr[th].date >= WF0]
            x = (rng.choice([-1.0, 1.0], size=len(t)) * t.gross.values - COST) * MULT
            if len(x) > 1 and x.std(ddof=1) > 0:
                best = max(best, float(x.mean() / (x.std(ddof=1) / np.sqrt(len(x)))))
        null.append(best)
    p95 = float(np.percentile(null, 95))
    passes = []
    for th in THETAS:
        w, c = res[th]["WF"], res[th]["control"]
        ok = (w["n"] >= 100 and w["roc30"] >= 15 and w["pf"] >= 1.10 and w["t"] >= 2.0 and w["t"] > p95
              and w["roc30"] > c["roc30"] and res[th]["stress_net"] > 0 and w["net_ex_big"] > 0 and w["years_pos"] >= 0.60)
        res[th]["PASS"] = bool(ok)
        print(f"theta {th}: WF n {w['n']} net ${w['net']:,.0f} PF {w['pf']:.2f} ROC@30k {w['roc30']:.1f} Sortino {w['sortino']:.2f} "
              f"t {w['t']:.2f} years+ {w['years_pos']:.0%} | control ROC@30k {c['roc30']:.1f} | stress ${res[th]['stress_net']:,.0f} -> {'PASS' if ok else 'fail'}")
        if ok:
            passes.append(th)
    print(f"null max-t p95 {p95:.2f}")
    out = {"stageA": {str(k): v for k, v in res.items()}, "null_p95": p95, "passes": passes, "A2": None,
           "coverage": {"guard": f"day kept only if members with both bars >= {COVER} x members_on(day)", "breadth_days": int(br.B.notna().sum()), "sessions": len(days),
                        "guard_dropped": len(dropped), "guard_dropped_days": dropped, "recorded_empty": len(empty), "recorded_empty_days": empty}}
    if passes:
        base = book(None, WF0, LB0)
        print(f"BOOK #463 WF check (must be {BOOK_WF[0]} / {BOOK_WF[1]}): ROC@30k {base['roc30']:.2f} Sortino {base['sortino']:.3f}")
        if not (abs(base["roc30"] - BOOK_WF[0]) < 0.006 and abs(base["sortino"] - BOOK_WF[1]) < 0.0006):
            print("A2 NOT judged: the book file does not reproduce #463's prereg numbers - fix the input first")
            out["A2"] = {"pass": False, "error": "book check mismatch", "book_wf": base}
            json.dump(out, open(os.path.join(OUT, "nqbrd_stageA.json"), "w"), indent=1, default=str); return
        th = max(passes, key=lambda k: res[k]["WF"]["roc30"])
        leg = tr[th].groupby("date")["pnl"].sum()
        by_c = {c: book(leg * c, WF0, LB0) for c in (1, 2, 3)}
        cb = max(by_c, key=lambda c: by_c[c]["roc30"])
        ok = by_c[cb]["roc30"] >= 97.3 and by_c[cb]["sortino"] >= 3.816
        for c, r in by_c.items():
            print(f"  #463 + NQBRD theta {th} x{c}: WF ROC@30k {r['roc30']:.2f} Sortino {r['sortino']:.3f}")
        out["A2"] = {"theta": th, "c": cb, "pass": bool(ok), "by_c": {str(k): v for k, v in by_c.items()}}
        print("A2:", f"PASS (theta {th}, x{cb})" if ok else "FAIL (needs >= 97.3 and Sortino >= 3.816)")
    else:
        print("Stage A passes: none - NQBRD dead; lockbox stays sealed")
    json.dump(out, open(os.path.join(OUT, "nqbrd_stageA.json"), "w"), indent=1, default=str)


def stage_b():
    pa = os.path.join(OUT, "nqbrd_stageA.json")
    if not os.path.exists(pa):
        print("Stage B refused: nqbrd_stageA.json is missing - run `A` first; the lockbox stays sealed."); return
    res = json.load(open(pa))
    if not (res.get("A2") or {}).get("pass"):
        print("Stage B refused: no Stage A2 pass on file - the lockbox stays sealed."); return
    flag = os.path.join(OUT, "nqbrd_stageB_READ.flag")
    assert not os.path.exists(flag), "Stage B was already read once"
    th, c = float(res["A2"]["theta"]), int(res["A2"]["c"])
    miss = missing_days(f"{LB0:%Y-%m-%d}", f"{LB1:%Y-%m-%d}")                 # every lockbox session pulled or recorded empty, else the one read is wasted
    if miss:
        print(f"Stage B refused: {len(miss)} lockbox session days of the NQ master are neither in the pull cache nor recorded empty - run `pull` first (lockbox NOT read)"); return
    br, _ = breadth(LBX)                                                      # the lockbox data loads here; nothing is computed or shown from it yet
    nq = nq_days(LB0, LBX)
    bb = book(None, LB0, LBX, yrs=LBY)                                        # the book's own LB numbers are public (prereg); checked BEFORE the family's lockbox is read
    print(f"BOOK #463 LB check (must be {BOOK_LB[0]} / {BOOK_LB[1]}): ROC@30k {bb['roc30']:.2f} Sortino {bb['sortino']:.3f}")
    if not (abs(bb["roc30"] - BOOK_LB[0]) < 0.006 and abs(bb["sortino"] - BOOK_LB[1]) < 0.0006):
        print("Stage B refused: the book file's LB window does not reproduce #463's prereg LB numbers - settle the end-date convention first (lockbox NOT read)"); return
    open(flag, "w").write(pd.Timestamp.now().isoformat())                     # the one read starts here (a crash above leaves the lockbox unread)
    br = br.reindex(nq.index)
    sign = pd.Series(np.where(br.B >= th, 1, np.where(br.B <= 1 - th, -1, 0)), index=nq.index)
    t = trades(nq, sign)
    leg = t.groupby("date")["pnl"].sum() * c
    r = book(leg, LB0, LBX, yrs=LBY)
    bt = pd.read_csv(os.path.join(os.path.dirname(BOOK), "book463_trades.csv"), parse_dates=["date"])
    big = max(float(bt[bt.date >= LB0]["pnl"].max()), float(t["pnl"].max() * c) if len(t) else 0.0)
    r["big"] = big
    ok = r["roc30"] >= 164.76 and r["sortino"] >= 4.150 and r["net"] - big > 0 and leg.sum() > 0
    print(f"Stage B: book LB ROC@30k {r['roc30']:.2f} Sortino {r['sortino']:.3f} | leg LB {len(t)} trades ${leg.sum():,.0f} -> {'PASS' if ok else 'FAIL'}")
    json.dump({"B": r, "leg_n": len(t), "leg_net": float(leg.sum()), "pass": bool(ok)}, open(os.path.join(OUT, "nqbrd_stageB.json"), "w"), indent=1)


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    cmd = sys.argv[1:2]
    {"pull": pull, "A": stage_a, "B": stage_b}.get(cmd[0] if cmd else "", lambda: print("usage: r5_nqbrd.py pull | A | B"))()
