"""
INSIDER r1 (docs/INSIDER_R1.md, pre-registered before the real-direction run): long Nasdaq-100 members after an officer /
director OPEN-MARKET PURCHASE (SEC Form 4, code P), hedged with NQ micros; Stage A on the WALK-FORWARD only (2016-07-01 ..
2025-06-29). Every array is cut before 2025-06-30 before any signal; the lockbox is never loaded.

DATA (all photographs, read only): Form 4 = C:/EdgeLog/_research_cache/form4/form4_ndx_open_market.csv (tools/fetch_form4.py),
membership = tools/data/ndx_members.csv, stock bars = C:/EdgeLog/alpaca_cache/siporb/daily_split.parquet (Alpaca daily,
split-adjusted, no dividends, SIPORB pull 2026-10-03/04), hedge = the NQ 5m RTH masters (db_adj_rth for P&L, db_noadj_rth for
sizing; tools/data/rolls_NQ.csv for roll costs). Yardstick, drawdown episodes and the seat report come from tools/tvnt1_triage.py.

    python tools/tvins1_triage.py --selftest      # synthetic data only
    python tools/tvins1_triage.py --null          # family null + power line ONLY (random dates; no real-direction number)
    python tools/tvins1_triage.py --dry           # plumbing: one random-date draw through the real-run code (no real number)
    python tools/tvins1_triage.py --real          # the pre-registered Stage A (after the prereg is committed)
"""
import argparse, hashlib, json, os, sys
import numpy as np, pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tvnt1_triage as T1  # noqa: E402

SHARED = T1.SHARED
OUT = r"C:\EdgeLog\_anatomy_cache\tv_insider_r1"
FORM4 = r"C:\EdgeLog\_research_cache\form4\form4_ndx_open_market.csv"
FILINGS = r"C:\EdgeLog\_research_cache\edgar\filings_ndx.csv"
BARS = r"C:\EdgeLog\alpaca_cache\siporb\daily_split.parquet"
BARS_RAW = r"C:\EdgeLog\alpaca_cache\siporb\daily_raw.parquet"
CORP = r"C:\EdgeLog\alpaca_cache\xgap\corporate_actions_wide.csv"       # Alpaca corporate actions 2016-06 .. (cash dividends)
EXTRA = ("EA", "ATVI", "DISH", "HOLX", "QVCA", "QRTEA", "LVNTA", "WBA", "BBBY", "ENDP", "SGEN", "SRCL")   # MANAGER pull (addendum 1)
MEMBERS = os.path.join(SHARED, "tools", "data", "ndx_members.csv")
CUT, WF = T1.CUT, T1.WF
NOTL, HS, MINV = 50000.0, (5, 20, 60), (0.0, 100000.0)
STOCK_BP = 5.0                                   # per side, primary; the cost curve reports 0 / 2 / 5 / 10 / 20
MNQ_MULT, MNQ_PER = 2.0, 2.50 + 0.25 * 2.0       # $ per point; $ per micro per side (fee + one tick)
REPS, SEED = 500, 20261005
CELLS = [(h, v) for h in HS for v in MINV]


# ------------------------------------------------------------------------------------------------ data
def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def classify(D):
    """Cohen-Malloy-Pomorski 2012 classes from each insider's own P / S history (calendar years of the trade date)."""
    D = D.copy(); td = pd.to_datetime(D["trans_date"], errors="coerce"); D["y"] = td.dt.year; D["m"] = td.dt.month
    hist = D.dropna(subset=["y"]).groupby(["owner_cik", "y"])["m"].apply(set).to_dict()

    def one(o, y):
        if not np.isfinite(y):
            return "unclassified"
        prev = [hist.get((o, y - k)) for k in (1, 2, 3)]
        if any(p is None for p in prev):
            return "unclassified"
        return "routine" if (prev[0] & prev[1] & prev[2]) else "opportunistic"
    D["cls"] = [one(o, y) for o, y in zip(D["owner_cik"], D["y"])]
    return D


def load_events(spans, sessions):
    """One EVENT = one issuer x Form 4 filing date with >= 1 officer / director open-market purchase, inside the company's
    membership spell. Known at the EARLIEST acceptance time that day; entry = the first 09:30 open at least 30 minutes after
    acceptance (addendum 1, MANAGER #68): accepted before 09:00 ET on a session day -> that session, else the next session."""
    D = classify(pd.read_csv(FORM4, low_memory=False))
    P = D[(D["code"] == "P") & D["roles"].fillna("").str.contains("Officer|Director", case=False) & D["accepted_et"].notna()].copy()
    M = pd.read_csv(MEMBERS); M["to"] = M["to"].fillna(str(CUT.date()))
    cur = pd.read_csv(FILINGS, usecols=["cik", "ticker"], low_memory=False).drop_duplicates("cik").set_index("cik")["ticker"].to_dict()
    P["acc"] = pd.to_datetime(P["accepted_et"])
    g = P.groupby(["issuer_cik", "filing_date"])
    ev = g.agg(ndx=("ndx_tickers", "first"), acc=("acc", "min"), value=("value", "sum"), n_ins=("owner_cik", "nunique"),
               cls=("cls", lambda x: "opportunistic" if (x == "opportunistic").any() else ("routine" if (x == "routine").any() else "unclassified"))).reset_index()

    def member(ndx, d):
        for t in str(ndx).split(";"):
            s = M[M["ticker"] == t]
            if ((s["from"] <= d) & (s["to"] > d)).any():
                return True
        return False

    def symbol(ndx, cik, d):
        """the ticker that was a member on the filing date AND has bars spanning it (QVCA vs LVNTA, DISCA vs DISCK: first
        alphabetically among those); else any listed ticker with bars spanning it (FB's history sits under META); else EDGAR's."""
        ts = str(ndx).split(";"); dd = pd.Timestamp(d)
        live = [t for t in ts if t in spans and spans[t][0] <= dd <= spans[t][1]]
        both = [t for t in live if member(t, d)]
        if both or live:
            return (both or live)[0]
        c = cur.get(cik)
        return c if c in spans else None

    ev = ev[[member(n, d) for n, d in zip(ev["ndx"], ev["filing_date"])]].copy()
    ev["sym"] = [symbol(n, c, d) for n, c, d in zip(ev["ndx"], ev["issuer_cik"], ev["filing_date"])]
    info = dict(member_events=len(ev), no_bars=int(ev["sym"].isna().sum()),
                no_bar_companies=sorted(ev.loc[ev["sym"].isna(), "ndx"].unique().tolist()))
    ev = ev[ev["sym"].notna()].copy()
    d0 = ev["acc"].dt.normalize(); early = ev["acc"].dt.hour * 60 + ev["acc"].dt.minute < 540
    sv = sessions.values
    k = np.searchsorted(sv, d0.values.astype("datetime64[ns]"))            # first session >= acceptance day
    same = (k < len(sv)) & (sv[np.minimum(k, len(sv) - 1)] == d0.values.astype("datetime64[ns]"))
    k = np.where(same & early.values, k, np.where(same, k + 1, k))
    ev["i"] = k
    ev = ev[(ev["i"] < len(sv))].copy()
    ev["entry"] = sv[ev["i"].values]
    ev = ev[(ev["entry"] >= np.datetime64(WF[0])) & (ev["entry"] <= np.datetime64(WF[1]))].copy()
    info["wf_events"] = len(ev)
    return ev.sort_values("entry").reset_index(drop=True), info


def extra_bars(adj="split"):
    """Daily masters the house importer wrote for EXTRA (tools/import_alpaca_stocks.py, source alpaca_<adj>_<session>) as rows
    symbol, date, o, h, l, c, v; empty when the pull has not run. Cut before the lockbox at read time."""
    os.chdir(SHARED); sys.path.insert(0, SHARED)
    from augur_engine.data import find_master, load_master_arrays
    out = []
    for sym in EXTRA:
        m = None
        for sess in ("rth", "eth"):
            m = m or find_master(sym, "1D", sess, "alpaca_%s_%s" % (adj, sess))
        if not m:
            continue
        A = load_master_arrays(m, date_to="2025-06-29")
        d = pd.DatetimeIndex(A["index"]); d = (d.tz_convert("US/Eastern") if d.tz is not None else d).normalize()
        d = d.tz_localize(None) if d.tz is not None else d
        out.append(pd.DataFrame({"symbol": sym, "date": d, "o": A["open"], "h": A["high"], "l": A["low"], "c": A["close"], "v": A["volume"]}))
    return pd.concat(out, ignore_index=True) if out else pd.DataFrame(columns=["symbol", "date", "o", "h", "l", "c", "v"])


def all_bars(adj="split", cols=None):
    B = pd.read_parquet(BARS if adj == "split" else BARS_RAW)
    X = extra_bars(adj)
    X = X[~X["symbol"].isin(set(B["symbol"].unique()))]
    B = pd.concat([B, X], ignore_index=True) if len(X) else B
    return B[cols] if cols else B


def load_bars(syms):
    B = all_bars("split"); B = B[B["symbol"].isin(syms) & (B["date"] < CUT)]
    O = B.pivot(index="date", columns="symbol", values="o").sort_index(); C = B.pivot(index="date", columns="symbol", values="c").sort_index()
    have = C.notna()
    C = C.ffill(); O = O.where(O.notna(), C.shift(1)).where(O.notna() | C.shift(1).notna(), C)
    return O, C, have


def div_yield(syms, sessions):
    """sessions x symbols: cash dividend / previous RAW close, placed on the ex-date session (0 elsewhere). A position held at the
    close before the ex-date earns it on its held notional (shares x split-adjusted close), so no split factor is needed."""
    A = pd.read_csv(CORP, low_memory=False)
    A = A[(A["type"] == "cash_dividend") & A["symbol"].isin(syms)].copy()
    A["ex"] = pd.to_datetime(A["ex_date"], errors="coerce"); A = A[A["ex"].notna() & (A["ex"] < CUT)]
    R = all_bars("raw"); R = R[R["symbol"].isin(syms) & (R["date"] < CUT)]
    RC = R.pivot(index="date", columns="symbol", values="c").sort_index().reindex(sessions).ffill()
    DY = pd.DataFrame(0.0, index=sessions, columns=sorted(syms))
    for sym, ex, rate in zip(A["symbol"], A["ex"], pd.to_numeric(A["rate"], errors="coerce")):
        k = sessions.searchsorted(ex)
        if 0 < k < len(sessions) and np.isfinite(rate) and sym in RC and np.isfinite(RC[sym].iloc[k - 1]) and RC[sym].iloc[k - 1] > 0:
            DY.iloc[k, DY.columns.get_loc(sym)] += rate / RC[sym].iloc[k - 1]
    return DY


def load_nq(sessions):
    os.chdir(SHARED); sys.path.insert(0, SHARED)
    from augur_engine.data import find_master, load_master_arrays
    A = load_master_arrays(find_master("NQ", "5m", "rth", "db_adj_rth"), date_to="2025-06-29")
    Bm = load_master_arrays(find_master("NQ", "5m", "rth", "db_noadj_rth"), date_to="2025-06-29")
    ia = pd.DatetimeIndex(A["index"]); et = ia.tz_convert("US/Eastern")
    raw = pd.Series(np.asarray(Bm["close"], float), index=pd.DatetimeIndex(Bm["index"])).reindex(ia).values
    df = pd.DataFrame({"date": et.normalize().tz_localize(None), "m": et.hour * 60 + et.minute,
                       "o": np.asarray(A["open"], float), "c": np.asarray(A["close"], float), "r": raw})
    op = df[df["m"] == 570].set_index("date")["o"]; cl = df[df["m"] == 955].set_index("date")
    S = pd.DataFrame({"o": op, "c": cl["c"], "r": cl["r"]}).reindex(sessions)
    S["c"] = S["c"].ffill(); S["r"] = S["r"].ffill(); S["o"] = S["o"].fillna(S["c"].shift(1)).fillna(S["c"])
    sw = []
    import csv
    with open(os.path.join(SHARED, "tools", "data", "rolls_NQ.csv"), newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r.get("kind") != "not_a_roll" and r.get("old") and r.get("new"):
                sw.append(pd.Timestamp(int(r["switch_sec"]), unit="s", tz="UTC").tz_convert("US/Eastern").tz_localize(None).normalize())
    roll = pd.Series(0, index=sessions);
    for d in sw:
        k = sessions.searchsorted(d)
        if 0 < k < len(sessions):
            roll.iloc[k] += 1                                             # the hedge crosses a roll into this session's open
    return S, roll.values


# ------------------------------------------------------------------------------------------------ engine
def positions(ev, H, minv, n):
    """No stacking: one position per company at a time; an event in a company already held RESTARTS the clock (exit = the new
    entry + H sessions), size unchanged. Returns [(sym, i_entry, i_exit, event_rows)] - entry at open i, exit at open i_exit."""
    out = []
    for sym, g in ev[ev["value"] >= minv].groupby("sym"):
        cur = None
        for i, r in zip(g["i"].values, g.index.values):
            if cur and i < cur[2]:
                cur[2] = min(i + H, n - 1); cur[3].append(r)
            else:
                if cur:
                    out.append(tuple(cur))
                cur = [sym, int(i), int(min(i + H, n - 1)), [r]]
        if cur:
            out.append(tuple(cur))
    return [p for p in out if p[2] > p[1]]


DIV = {"DY": None}                                  # set by main(); None = no dividends (the addendum-1 'without' report)


def run(pos, O, C, nq, roll, stock_bp=STOCK_BP, hedge=True, divs=True):
    """Daily P&L (stock leg, hedge leg) on the session calendar, plus one trade row per position (exit date, pnl, sym)."""
    n = len(O); cols = {s: k for k, s in enumerate(O.columns)}; Ov, Cv = O.values, C.values
    stock = np.zeros(n); notl_open = np.zeros(n); trades = []
    o = nq["o"].values
    for sym, i, j, rows in pos:                      # entry at open i, exit at open j (j > i)
        k = cols[sym]; sh = NOTL / Ov[i, k]
        seg = np.empty(j - i + 1); seg[0] = Cv[i, k] - Ov[i, k]
        if j - i > 1:
            seg[1:j - i] = Cv[i + 1:j, k] - Cv[i:j - 1, k]
        seg[j - i] = Ov[j, k] - Cv[j - 1, k]
        p = sh * seg; p[0] -= NOTL * stock_bp / 1e4; p[-1] -= sh * Ov[j, k] * stock_bp / 1e4
        if divs and DIV["DY"] is not None:                # ex-dates i+1 .. j: held at the previous close
            p[1:] += sh * Cv[i:j, k] * DIV["DY"][i + 1:j + 1, k]
        stock[i:j + 1] += p
        notl_open[i] += NOTL
        if j - i > 1:
            notl_open[i + 1:j] += sh * Cv[i:j - 1, k]
        h_est = -NOTL * (o[j] / o[i] - 1.0) if hedge else 0.0              # the trade's share of the pooled hedge (for trade rows)
        trades.append([j, float(p.sum()) + h_est, sym])
    hed = np.zeros(n)
    if hedge:
        c, r = nq["c"].values, nq["r"].values
        q = -np.round(notl_open / (np.r_[r[0], r[:-1]] * MNQ_MULT))     # micros held from open t to open t+1, sized on the raw close
        hed += q * MNQ_MULT * (c - o)
        hed[1:] += q[:-1] * MNQ_MULT * (o[1:] - c[:-1])
        hed -= np.abs(np.diff(np.r_[0.0, q])) * MNQ_PER
        hed -= roll * np.abs(np.r_[0.0, q[:-1]]) * MNQ_PER * 2
    idx = O.index
    return pd.Series(stock, index=idx), pd.Series(hed, index=idx), [(idx[j], p, s) for j, p, s in trades]


def cell_stats(stock, hed, trades):
    d = T1.window(stock + hed, *WF)
    y = T1.yard(d); y["n"] = sum(1 for (x, p, g) in trades if WF[0] <= x <= WF[1])
    return y


# ------------------------------------------------------------------------------------------------ family null
def eligible(ev, O, have):
    """Per company: the sessions a random event may land on - inside a membership spell, inside WF, with a real bar."""
    M = pd.read_csv(MEMBERS); M["to"] = M["to"].fillna(str(CUT.date())); idx = O.index; out = {}
    wf = (idx >= WF[0]) & (idx <= WF[1])
    for (sym, ndx), _ in ev.groupby(["sym", "ndx"]):
        ok = np.zeros(len(idx), bool)
        for t in str(ndx).split(";"):
            for _, s in M[M["ticker"] == t].iterrows():
                ok |= (idx >= pd.Timestamp(s["from"])) & (idx < pd.Timestamp(s["to"]))
        out[sym] = np.flatnonzero(ok & wf & have[sym].values)
    return out


def null(ev, O, C, have, nq, roll, reps=REPS, seed=SEED):
    rng = np.random.default_rng(seed); el = eligible(ev, O, have); n = len(O); best = []
    for r in range(reps):
        e = ev.copy()
        for sym, g in e.groupby("sym"):
            e.loc[g.index, "i"] = rng.choice(el[sym], size=len(g), replace=True)
        e = e.sort_values("i")
        vals = []
        for H, v in CELLS:
            s, h, tr = run(positions(e, H, v, n), O, C, nq, roll)
            vals.append(cell_stats(s, h, tr)["roc30"])
        best.append(np.nanmax(vals))
        if r % 50 == 0:
            print("  null draw %d / %d: max-cell ROC30 %.2f" % (r, reps, best[-1]), flush=True)
    b = np.array(best)
    return dict(p50=float(np.nanpercentile(b, 50)), p95=float(np.nanpercentile(b, 95)), power_line=float(np.nanpercentile(b, 95) - np.nanpercentile(b, 50)),
                draws=[round(float(x), 3) for x in b])


# ------------------------------------------------------------------------------------------------ selftest
def selftest():
    idx = pd.bdate_range("2016-01-04", "2025-06-27"); t = np.arange(len(idx), dtype=float)
    O = pd.DataFrame({"AAA": 100.0 + t, "BBB": 50.0 + 2 * t}, index=idx); C = O + 0.5   # open rises 1 (2) a session, close = open + 0.5
    nq = pd.DataFrame({"o": 10000.0, "c": 10000.0, "r": 10000.0}, index=idx); roll = np.zeros(len(idx))
    i0 = int(idx.searchsorted(pd.Timestamp("2017-01-03")))
    ev = pd.DataFrame({"sym": ["AAA", "AAA", "BBB"], "i": [i0, i0 + 2, i0], "value": [5e5, 5e5, 5e4]})
    pos = positions(ev, 5, 0.0, len(idx))
    a = [p for p in pos if p[0] == "AAA"][0]
    assert len(pos) == 2 and a[2] == i0 + 7, pos                                          # restart: exit = second entry + 5
    assert len(positions(ev, 5, 1e5, len(idx))) == 1                                     # value filter drops BBB
    s, h, tr = run(pos, O, C, nq, roll, stock_bp=0.0)
    want = NOTL / (100.0 + i0) * 7 + NOTL / (50.0 + 2 * i0) * 2 * 5                      # open-to-open: shares x (O[j] - O[i])
    assert abs(s.sum() - want) < 1e-6, (s.sum(), want)
    notl = np.zeros(len(idx))                                                             # flat NQ: hedge P&L = - rebalance costs exactly
    for sym, i, j, _ in pos:
        sh = NOTL / O[sym].values[i]; notl[i] += NOTL
        if j - i > 1:
            notl[i + 1:j] += sh * C[sym].values[i:j - 1]
    qq = -np.round(notl / (10000.0 * MNQ_MULT))
    assert abs(h.sum() + np.abs(np.diff(np.r_[0.0, qq])).sum() * MNQ_PER) < 1e-6, (h.sum(), qq[qq != 0][:5])
    s5, _, _ = run(pos, O, C, nq, roll, stock_bp=5.0)
    assert s5.sum() < s.sum()
    print("selftest OK (open-to-open P&L, restart rule, value filter, flat hedge = costs only, cost applied)")


# ------------------------------------------------------------------------------------------------ main
def main(mode):
    os.makedirs(OUT, exist_ok=True)
    B = all_bars("split", ["symbol", "date"]); sessions = pd.DatetimeIndex(sorted(pd.read_parquet(BARS, columns=["date"]).query("date < @CUT")["date"].unique()))
    sp = B.groupby("symbol")["date"].agg(["min", "max"]); ev, info = load_events({k: (r["min"], r["max"]) for k, r in sp.iterrows()}, sessions)
    O, C, have = load_bars(sorted(ev["sym"].unique()))
    O, C, have = O.reindex(sessions), C.reindex(sessions).ffill(), have.reindex(sessions, fill_value=False)
    O = O.fillna(C.shift(1)).fillna(C)
    ev["i"] = sessions.get_indexer(pd.DatetimeIndex(ev["entry"]))
    nq, roll = load_nq(sessions)
    DIV["DY"] = div_yield(list(O.columns), sessions).reindex(columns=O.columns, fill_value=0.0).values
    shas = {k: sha(p) for k, p in (("form4", FORM4), ("bars", BARS), ("bars_raw", BARS_RAW), ("corporate_actions", CORP), ("members", MEMBERS))}
    info["extra_symbols_with_bars"] = sorted(set(EXTRA) & set(O.columns))
    info.update(companies=int(ev["sym"].nunique()), per_cell_positions={"H%d_v%d" % (h, v): len(positions(ev, h, v, len(sessions))) for h, v in CELLS})
    print(json.dumps(info, indent=1))
    if mode == "null":
        nl = null(ev, O, C, have, nq, roll)
        res = dict(info=info, shas=shas, null={k: v for k, v in nl.items() if k != "draws"})
        json.dump(dict(res, draws=nl["draws"]), open(os.path.join(OUT, "null_power.json"), "w"), indent=1)
        print("FAMILY NULL (max over %d cells, %d draws, seed %d): p50 %.2f  p95 %.2f  power line %.2f" % (len(CELLS), REPS, SEED, nl["p50"], nl["p95"], nl["power_line"]))
        return res
    nl = json.load(open(os.path.join(OUT, "null_power.json")))["null"]
    if mode == "dry":                     # plumbing check: ONE random-date draw through the real-run code; no real-direction number
        rng = np.random.default_rng(1); el = eligible(ev, O, have)
        for sym, g in ev.groupby("sym"):
            ev.loc[g.index, "i"] = rng.choice(el[sym], size=len(g), replace=True)
        ev = ev.sort_values("i")
        r = real(ev, O, C, nq, roll, nl)
        print("DRY RUN OK (random dates): keys", sorted(r), "| best", r["best"]["cell"], "| verdict", r["verdict"][:60])
        return r
    res = real(ev, O, C, nq, roll, nl)
    res.update(info=info, shas=shas, null=nl)
    json.dump(res, open(os.path.join(OUT, "stage_a.json"), "w"), indent=1, default=str)
    print(json.dumps({k: res[k] for k in ("cells", "best", "verdict")}, indent=1, default=str))
    return res


def july_years():
    return [(WF[0] + pd.DateOffset(years=k), WF[0] + pd.DateOffset(years=k + 1) - pd.Timedelta(days=1)) for k in range(9)]


def real(ev, O, C, nq, roll, nl):
    """The pre-registered Stage A (docs/INSIDER_R1.md): six cells, the best judged on the bars, every diagnostic REPORTED."""
    n = len(O); cells = {}; runs = {}
    path = event_path(ev, O, C, nq)                                       # addendum 1 item 4: printed FIRST
    print("EVENT-TIME PATH (all events, mean cumulative stock - NQ, %, from the close before entry):", path, flush=True)
    for H, v in CELLS:
        pos = positions(ev, H, v, n); s, h, tr = run(pos, O, C, nq, roll)
        y = cell_stats(s, h, tr); cells["H%d_v%d" % (H, v)] = {k: (round(x, 3) if isinstance(x, float) else x) for k, x in y.items()}
        runs[(H, v)] = (pos, s, h, tr)
    key = max(cells, key=lambda k: -1e9 if not np.isfinite(cells[k]["roc30"]) else cells[k]["roc30"])
    H, v = [int(x[1:]) for x in key.split("_")]; pos, s, h, tr = runs[(H, v)]; d = T1.window(s + h, *WF); b = cells[key]
    ex20 = d[(d.index < "2020-02-01") | (d.index > "2020-04-30")].sum()
    years = {"%d-%02d" % (a.year, z.year % 100): round(float(d[(d.index >= a) & (d.index <= z)].sum())) for a, z in july_years()}
    tp = sorted([p for (x, p, g) in tr if WF[0] <= x <= WF[1]], reverse=True)
    by_co = pd.Series([p for (x, p, g) in tr if WF[0] <= x <= WF[1]], index=[g for (x, p, g) in tr if WF[0] <= x <= WF[1]]).groupby(level=0).sum()
    loco = {c: round(float(d.sum() - by_co[c])) for c in by_co.index}
    checks = dict(roc30_ge_15=b["roc30"] >= 15, above_null_p95=b["roc30"] > nl["p95"], trades_ge_100=b["n"] >= 100,
                  ex_feb_apr_2020=bool(ex20 > 0), years_6_of_9=sum(1 for x in years.values() if x > 0) >= 6,
                  ex_top_trade=bool(sum(tp[1:]) > 0), loco_all_positive=all(x > 0 for x in loco.values()))
    rep = dict(ex_feb_apr_2020=round(float(ex20)), years=years, top10_trade_share=round(sum(tp[:10]) / sum(tp), 3) if sum(tp) else None,
               top10_company_share=round(float(by_co.sort_values(ascending=False).head(10).sum() / by_co.sum()), 3) if by_co.sum() else None,
               worst_loco=min(loco.items(), key=lambda kv: kv[1]) if loco else None,
               stock_leg=round(float(T1.window(s, *WF).sum())), hedge_leg=round(float(T1.window(h, *WF).sum())))
    halves = {}
    for nm, a, z in (("2016-21", WF[0], pd.Timestamp("2021-06-30")), ("2021-25", pd.Timestamp("2021-07-01"), WF[1])):
        halves[nm] = T1.yard(T1.window(s + h, a, z)) if len(T1.window(s, a, z)) > 20 else None
    curve = {}
    for bp in (0.0, 2.0, 5.0, 10.0, 20.0):
        s2, h2, t2 = run(pos, O, C, nq, roll, stock_bp=bp); curve["%gbp" % bp] = round(cell_stats(s2, h2, t2)["roc30"], 2)
    s3, h3, t3 = run(pos, O, C, nq, roll, hedge=False); unhedged = cell_stats(s3, h3, t3)
    splits = {}
    for nm, sub in (("opportunistic", ev[ev["cls"] == "opportunistic"]), ("routine", ev[ev["cls"] == "routine"]),
                    ("unclassified", ev[ev["cls"] == "unclassified"]), ("clustered", ev[ev["n_ins"] >= 2])):
        if len(sub):
            s4, h4, t4 = run(positions(sub, H, v, n), O, C, nq, roll); y4 = cell_stats(s4, h4, t4)
            splits[nm] = dict(n=y4["n"], net=round(y4["net"]), roc30=round(y4["roc30"], 2))
    s0, h0, t0 = run(pos, O, C, nq, roll, divs=False); nodiv = cell_stats(s0, h0, t0)
    seat = None
    try:
        bk = pd.read_csv(T1.BOOK, parse_dates=["date"]).set_index("date"); bwf = T1.window(bk, *WF)
        c = T1.vol_c(bwf, d); seat = T1.seat(bwf, d, c)
    except Exception as e:                                                # report only; never blocks the verdict
        seat = dict(error=str(e))
    verdict = "PASS (Stage A)" if all(checks.values()) else "FAIL: " + ", ".join(k for k, x in checks.items() if not x)
    return dict(cells=cells, best=dict(cell=key, **b), checks=checks, report=rep, halves=halves, cost_curve=curve,
                unhedged=dict(roc30=round(unhedged["roc30"], 2), net=round(unhedged["net"])), splits=splits, event_path=path,
                seat=seat, without_dividends=dict(roc30=round(nodiv["roc30"], 2), net=round(nodiv["net"])), verdict=verdict)


def event_path(ev, O, C, nq, lo=-10, hi=60):
    """Mean cumulative (stock - NQ) close-to-close return from the close before entry, sessions lo .. hi (report only)."""
    rs = C.pct_change(); cols = {s: k for k, s in enumerate(C.columns)}; R = rs.values
    rn = (nq["c"].diff() / nq["r"].shift(1)).values     # point move / previous RAW close (the back-adjusted level is not a price)
    acc = np.zeros(hi - lo + 1); cnt = np.zeros(hi - lo + 1)
    for sym, i in zip(ev["sym"], ev["i"]):
        k = cols[sym]
        for off in range(lo, hi + 1):
            t = i + off
            if 1 <= t < len(R) and np.isfinite(R[t, k]) and np.isfinite(rn[t]):
                acc[off - lo] += R[t, k] - rn[t]; cnt[off - lo] += 1
    m = np.where(cnt > 0, acc / np.maximum(cnt, 1), 0.0)
    cum = np.cumsum(m) - np.cumsum(m)[-lo - 1]                            # zero at the close before entry (offset -1)
    return {str(lo + j): round(float(cum[j]) * 100, 3) for j in range(0, hi - lo + 1, 5)}


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--selftest", action="store_true"); ap.add_argument("--null", action="store_true")
    ap.add_argument("--real", action="store_true"); ap.add_argument("--dry", action="store_true"); a = ap.parse_args()
    if a.selftest:
        selftest()
    elif a.null:
        main("null")
    elif a.dry:
        main("dry")
    elif a.real:
        main("real")
