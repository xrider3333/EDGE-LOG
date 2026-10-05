"""
TV NEW-TYPE round 2 (docs/TV_NEWTYPES_R2.md, pre-registered before this file ran): Stage A on the WALK-FORWARD ONLY for
AUCTION (Treasury auction supply cycle on IEF/TLT), COT (hedging pressure across 11 markets through funds, weekly) and XASSET
(TLT's past return sets the NQ/ES side, weekly). Every array is cut before 2025-06-30 before any signal; the lockbox is never
loaded. Shares round 1's yardstick, drawdown days, judge(), seat report and the fund P&L engine (tools/tvnt1_triage.py).

    python tools/tvnt2_triage.py --selftest                 # synthetic data only
    python tools/tvnt2_triage.py --fetch                    # the two public files: Treasury auctions, CFTC COT (legacy, futures only)
    python tools/tvnt2_triage.py [AUCTION|COT|XASSET]       # the pre-registered run (all three by default)
"""
import csv, hashlib, json, os, sys, urllib.parse, urllib.request
import numpy as np, pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tvnt1_triage as T1  # noqa: E402

SHARED, CACHE = T1.SHARED, T1.CACHE
OUT = r"C:\EdgeLog\_anatomy_cache\tv_newtypes_r2"
AUC_FILE = os.path.join(CACHE, "treasury_auctions_raw.json")     # raw API responses, byte for byte (addendum 1 item 0)
COT_FILE = os.path.join(CACHE, "cot_legacy_futures_raw.json")
PROV_FILE = os.path.join(CACHE, "tvnt2_provenance.json")
CUT, WF, EARLY = T1.CUT, T1.WF, T1.EARLY
EARLY_FUT = (pd.Timestamp("2010-06-07"), T1.EARLY[1])
REPS, SEED, NOTL = 500, 20261005, 50000.0
AUC_FUND = {"5-Year": "IEF", "7-Year": "IEF", "10-Year": "IEF", "20-Year": "TLT", "30-Year": "TLT"}
COT_MKTS = {"13874A": "SPY", "209742": "QQQ", "043602": "IEF", "020601": "TLT", "088691": "GLD", "084691": "SLV",
            "067651": "USO", "099741": "FXE", "097741": "FXY", "232741": "FXA", "098662": "UUP"}
# shutdown backlogs: COT reports with these report dates were published late (conservatively: usable from the date given)
COT_LATE = [(pd.Timestamp("2013-10-01"), pd.Timestamp("2013-11-26"), pd.Timestamp("2013-12-03")),
            (pd.Timestamp("2018-12-25"), pd.Timestamp("2019-03-05"), pd.Timestamp("2019-03-12"))]
FUT = {"NQ": dict(mult=2.0, tick=0.25), "ES": dict(mult=5.0, tick=0.25)}
FEE = 2.50                                      # $ per micro per side (+ one tick of slippage per side)


# ------------------------------------------------------------------------------------------------ fetch (public files)
def _get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "EdgeLog research (TV lane)"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.read()


def fetch():
    """TreasuryDirect auction records (Fiscal Data API) and the CFTC legacy futures-only COT (public reporting API), each saved
    byte for byte as fetched, with URL, fetch time, size and sha256 in tvnt2_provenance.json (addendum 1 item 0)."""
    import datetime
    os.makedirs(CACHE, exist_ok=True)
    for p_ in (AUC_FILE, COT_FILE):
        if os.path.exists(p_):
            sys.exit("REFUSED: %s exists - a cache is a photograph, never re-fetched into a result" % p_)
    q = {"fields": "cusip,security_type,security_term,original_security_term,auction_date,announcemt_date,issue_date,reopening,"
                   "offering_amt,inflation_index_security,floating_rate",
         "filter": "security_type:in:(Note,Bond),auction_date:gte:2005-01-01", "sort": "auction_date", "page[size]": "10000"}
    u1 = "https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v1/accounting/od/auctions_query?" + urllib.parse.urlencode(q, safe=":(),[]")
    codes = ",".join("'%s'" % c for c in COT_MKTS)
    q = {"$select": "market_and_exchange_names,report_date_as_yyyy_mm_dd,cftc_contract_market_code,open_interest_all,"
                    "comm_positions_long_all,comm_positions_short_all",
         "$where": "cftc_contract_market_code in(%s) AND report_date_as_yyyy_mm_dd >= '2003-01-01T00:00:00'" % codes,
         "$order": "report_date_as_yyyy_mm_dd", "$limit": "50000"}
    u2 = "https://publicreporting.cftc.gov/resource/6dca-aqww.json?" + urllib.parse.urlencode(q)
    prov = {}
    for name, url, dst in (("treasury_auctions", u1, AUC_FILE), ("cot_legacy_futures", u2, COT_FILE)):
        raw = _get(url); at = datetime.datetime.now().astimezone().isoformat(timespec="seconds")
        with open(dst, "wb") as f:
            f.write(raw)
        prov[name] = dict(url=url, fetched_at=at, bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest(), file=dst)
        print(name, prov[name]["bytes"], "bytes", prov[name]["sha256"][:16], at)
    with open(PROV_FILE, "w") as f:
        json.dump(prov, f, indent=1)
    A = json.loads(open(AUC_FILE, "rb").read()); print("auctions rows:", len(A["data"]), "| meta:", A.get("meta", {}).get("total-count"))
    df = pd.DataFrame(json.loads(open(COT_FILE, "rb").read()))
    print("COT rows:", len(df))
    for c, g in df.groupby("cftc_contract_market_code"):
        print("  %-7s %-4s %4d weeks %s .. %s  %s" % (c, COT_MKTS.get(c), len(g), g["report_date_as_yyyy_mm_dd"].min()[:10],
              g["report_date_as_yyyy_mm_dd"].max()[:10], sorted(set(g["market_and_exchange_names"]))[:2]))


def sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()[:16]


# ------------------------------------------------------------------------------------------------ AUCTION
def easter(y):
    a = y % 19; b, c = divmod(y, 100); d, e = divmod(b, 4); f = (b + 8) // 25; g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30; i, k = divmod(c, 4); l = (32 + 2 * e + 2 * i - h - k) % 7; m = (a + 11 * h + 22 * l) // 451
    mo, da = divmod(h + l - 7 * m + 114, 31)
    return pd.Timestamp(year=y, month=mo, day=da + 1)


def early_sessions(dates):
    """Addendum 1 item 1b: the day after Thanksgiving, Dec 24, Dec 31, July 3 (when trading days) and the session before Good Friday."""
    out = set(); ds = set(dates)
    for y in range(dates[0].year, dates[-1].year + 1):
        nov = pd.Timestamp(year=y, month=11, day=1); thx = nov + pd.Timedelta(days=(3 - nov.weekday()) % 7 + 21)
        gf = easter(y) - pd.Timedelta(days=2)
        cands = [thx + pd.Timedelta(days=1), pd.Timestamp(year=y, month=12, day=24), pd.Timestamp(year=y, month=12, day=31),
                 pd.Timestamp(year=y, month=7, day=3)]
        k = int(np.searchsorted(dates.values, np.datetime64(gf))) - 1
        if k >= 0:
            cands.append(dates[k])
        out |= {int(np.searchsorted(dates.values, np.datetime64(d))) for d in cands if d in ds}
    return out


def load_auctions(dates):
    """Per fund: list of (t_idx, a_idx, size_tercile) - the auction session, the first session on/after the announcement,
    and the offering-amount tercile within the auction's original term (0 small .. 2 large)."""
    df = pd.DataFrame(json.loads(open(AUC_FILE, "rb").read())["data"])
    df = df[(df["inflation_index_security"].fillna("No") != "Yes") & (df["floating_rate"].fillna("No") != "Yes")]
    term = df["original_security_term"].where(df["original_security_term"].fillna("null") != "null", df["security_term"]).str.strip()
    df = df.assign(term=term, fund=term.map(AUC_FUND)).dropna(subset=["fund"])
    df["ad"] = pd.to_datetime(df["auction_date"]); df["an"] = pd.to_datetime(df["announcemt_date"], errors="coerce")
    df["amt"] = pd.to_numeric(df["offering_amt"], errors="coerce")
    df = df[df["ad"] < CUT].drop_duplicates(["ad", "term"])
    df["terc"] = df.groupby("term")["amt"].transform(lambda x: pd.qcut(x.rank(method="first"), 3, labels=False))
    pos = {d: i for i, d in enumerate(dates)}; ev = {"IEF": set(), "TLT": set()}; miss = 0
    for _, r in df.iterrows():
        if r["ad"] not in pos:
            miss += 1; continue
        t = pos[r["ad"]]; a = int(np.searchsorted(dates.values, np.datetime64(r["an"] if pd.notna(r["an"]) else r["ad"])))
        ev[r["fund"]].add((t, min(a, t), int(r["terc"]) if np.isfinite(r["terc"]) else 1))
    out = {f: sorted(v) for f, v in ev.items()}
    lag = (df["ad"] - df["an"]).dt.days
    return out, dict(rows=len(df), not_a_session=miss, events={f: len(v) for f, v in out.items()},
                     by_term=df["term"].value_counts().to_dict(),
                     announce_lag_days=dict(min=float(lag.min()), median=float(lag.median()), max=float(lag.max())),
                     amt_median_bn_by_term={k: round(float(v) / 1e9, 1) for k, v in df.groupby("term")["amt"].median().items()})


def keep_events(events, K, early, terc=None):
    """Addendum 1 item 1b: drop an auction whose window (t-K .. t+K) touches a listed early-close session; optional tercile filter."""
    return [e for e in events if (early is None or not any((t in early) for t in range(e[0] - K, e[0] + K + 1)))
            and (terc is None or e[2] == terc)]


def auction_pos(n, events, K, part="both"):
    """Position per interval i (close i-1 -> close i): -1 in the K intervals ending at the auction close (opened no earlier
    than the announcement session's close), +1 in the K after; the short beats the long where they overlap."""
    lg, sh = np.zeros(n, bool), np.zeros(n, bool)
    for e in events:
        t, a = e[0], e[1]
        if part in ("both", "post"):
            lg[t + 1: min(n, t + K + 1)] = True
        if part in ("both", "pre"):
            s0 = max(t - K, a)
            if s0 < t:
                sh[s0 + 1: t + 1] = True
    p = np.zeros(n); p[lg] = 1.0; p[sh] = -1.0
    return p


def pos_pnl(C, fund, pos, stress=False, notl=NOTL):
    """Close-to-close P&L of a +-1 position path at fixed notional; costs at each change, borrow on shorts.
    Returns (daily Series, trades [(exit_date, pnl, fund)])."""
    dates = C.index; c = C[fund].values; n = len(c)
    r = np.zeros(n); r[1:] = c[1:] / c[:-1] - 1.0; r[~np.isfinite(r)] = 0.0
    days = np.ones(n); days[1:] = np.maximum(1, (dates[1:] - dates[:-1]).days)
    pnl = notl * pos * r
    pnl -= np.where(pos < 0, notl * T1.BORROW * days, 0.0)
    chg = np.abs(np.diff(np.concatenate([[0.0], pos, [0.0]])))
    cost = chg * notl * T1.bps(fund, stress)
    daily = pnl - cost[:n]
    trades = []; i = 0
    while i < n:
        if pos[i] == 0:
            i += 1; continue
        j = i
        while j + 1 < n and pos[j + 1] == pos[i]:
            j += 1
        tp = pnl[i:j + 1].sum() - notl * T1.bps(fund, stress) * 2
        trades.append((dates[j], float(tp), fund)); i = j + 1
    return pd.Series(daily, index=dates), trades


def auction_cell(C, ev, K, part="both", stress=False, early=None, terc=None):
    d, tr = None, []
    for f in ("IEF", "TLT"):
        x, t = pos_pnl(C, f, auction_pos(len(C), keep_events(ev[f], K, early, terc), K, part), stress)
        d = x if d is None else d + x; tr += t
    return d, tr


def auction_shift(ev, n, rng):
    out = {}
    for f, v in ev.items():
        w = []
        for e in v:
            t, a = e[0], e[1]
            s = int(rng.integers(8, 16)) * (1 if rng.random() < 0.5 else -1); t2 = t + s
            if 1 <= t2 < n - 1:
                w.append((t2, max(0, t2 - (t - a)), e[2]))
        out[f] = w
    return out


def month_end_row(C):
    dates = C.index; ym = dates.year * 12 + dates.month; last2 = np.zeros(len(dates), bool)
    nxt = np.r_[ym[1:], -1]; nxt2 = np.r_[ym[2:], -1, -1]
    last2[(ym != nxt) | (ym != nxt2)] = True
    d = None
    for f in ("IEF", "TLT"):
        x, _ = pos_pnl(C, f, last2.astype(float)); d = x if d is None else d + x
    return d


# ------------------------------------------------------------------------------------------------ COT
def load_cot():
    df = pd.DataFrame(json.loads(open(COT_FILE, "rb").read()))
    df["rd"] = pd.to_datetime(df["report_date_as_yyyy_mm_dd"].str[:10])
    for c in ("open_interest_all", "comm_positions_long_all", "comm_positions_short_all"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df["hp"] = (df["comm_positions_long_all"] - df["comm_positions_short_all"]) / df["open_interest_all"]
    df["avail"] = df["rd"] + pd.Timedelta(days=7)
    for a, b, late in COT_LATE:
        m = (df["rd"] >= a) & (df["rd"] <= b); df.loc[m, "avail"] = df.loc[m, "avail"].clip(lower=late)
    df = df[df["avail"] < CUT]
    return {COT_MKTS[c]: g.sort_values("rd").drop_duplicates("rd") for c, g in df.groupby("cftc_contract_market_code") if c in COT_MKTS}


def cot_weeks(O, C, cot, W):
    """Per rebalance session r: {fund: (percentile, notional)} from the reports usable at r's open."""
    dates = O.index; rets = C.pct_change()
    ser = {}
    for f, g in cot.items():
        hp = g["hp"].values
        pct = np.full(len(hp), np.nan)
        for k in range(W, len(hp)):
            prev = hp[k - W:k]
            if np.isfinite(hp[k]) and np.isfinite(prev).sum() >= int(0.8 * W):
                pct[k] = float(np.mean(prev[np.isfinite(prev)] < hp[k]))
        ai = np.searchsorted(dates.values, g["avail"].values.astype("datetime64[ns]"))
        ser[f] = (ai, pct)
    sessions = sorted(set(int(i) for f in ser for i in ser[f][0] if i < len(dates)))
    out = []
    for r in sessions:
        if r < 61:
            continue
        row = {}
        for f, (ai, pct) in ser.items():
            k = int(np.searchsorted(ai, r, side="right")) - 1
            if k < 0 or not np.isfinite(pct[k]) or f not in C:
                continue
            sd = rets[f].iloc[r - 60:r].std()
            if np.isfinite(sd) and sd > 0 and np.isfinite(O[f].iloc[r]):
                row[f] = (pct[k], min(1000.0 / sd, 50000.0))
        out.append((r, row))
    return out


def cot_legs(weeks, n, sign=1.0, rng=None):
    legs = []
    for wi, (r, row) in enumerate(weeks):
        j = weeks[wi + 1][0] if wi + 1 < len(weeks) else n - 1
        if len(row) < 8 or j <= r:
            continue
        names = sorted(row, key=lambda f: (row[f][0], f))
        if rng is not None:
            names = list(rng.permutation(names))
        lo, hi = names[:3], names[-3:]
        for f in lo:
            legs.append((r, j, f, sign * row[f][1], f))
        for f in hi:
            legs.append((r, j, f, -sign * row[f][1], f))
    return legs


def per_week(tr):
    wk = {}
    for (x, p, g) in tr:
        wk[x] = wk.get(x, 0.0) + p
    return [(x, p, "week") for x, p in sorted(wk.items())]


def currency_cluster(legs):
    """Addendum 1 item 2b: share of weeks in which 2+ of UUP / FXE / FXY express the SAME dollar direction."""
    wk = {}
    for (i, j, f, nt, g) in legs:
        if f in ("UUP", "FXE", "FXY"):
            usd = float(np.sign(nt)) * (1.0 if f == "UUP" else -1.0)
            wk.setdefault(i, []).append(usd)
    weeks = len(set(l[0] for l in legs))
    same = sum(1 for v in wk.values() if max(v.count(1.0), v.count(-1.0)) >= 2)
    return same / weeks if weeks else float("nan")


def tsmom_overlap(C, legs):
    agree = tot = 0
    for (i, j, f, nt, g) in legs:
        if i < 260:
            continue
        r12 = C[f].iloc[i - 22] / C[f].iloc[i - 253] - 1.0
        if np.isfinite(r12):
            tot += 1; agree += int((r12 > 0) == (nt > 0))
    return agree / tot if tot else float("nan")


# ------------------------------------------------------------------------------------------------ XASSET
def load_futures():
    os.chdir(SHARED); sys.path.insert(0, SHARED)
    from augur_engine.data import find_master, load_master_arrays
    out = {}
    for mkt in FUT:
        A = load_master_arrays(find_master(mkt, "5m", "rth", "db_adj_rth"), date_to="2025-06-29")
        B = load_master_arrays(find_master(mkt, "5m", "rth", "db_noadj_rth"), date_to="2025-06-29")
        ia = pd.DatetimeIndex(A["index"]); et = ia.tz_convert("US/Eastern")
        raw = pd.Series(np.asarray(B["close"], float), index=pd.DatetimeIndex(B["index"])).reindex(ia).values
        df = pd.DataFrame({"date": et.normalize().tz_localize(None), "m": et.hour * 60 + et.minute,
                           "o": np.asarray(A["open"], float), "c": np.asarray(A["close"], float), "r": raw})
        op = df[df["m"] == 570].set_index("date")["o"]; cl = df[df["m"] == 955].set_index("date")
        S = pd.DataFrame({"o": op, "c": cl["c"], "r": cl["r"]}).dropna()
        S = S[S.index < CUT]
        S["t16"] = [int(pd.Timestamp(d).tz_localize("US/Eastern").value // 10**9) + 16 * 3600 for d in S.index]
        out[mkt] = S
    return out


def switches(root):
    p = os.path.join(SHARED, "tools", "data", "rolls_%s.csv" % root)
    out = []
    with open(p, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r.get("kind") == "not_a_roll" or not (r.get("old") and r.get("new")):
                continue
            out.append(int(r["switch_sec"]))
    return np.array(sorted(out), dtype=np.int64)


def week_starts(dates):
    return [i for i in range(1, len(dates)) if dates[i].weekday() < dates[i - 1].weekday() or (dates[i] - dates[i - 1]).days > 3]


def sig_series(series, L, points=False):
    """The L-session change skipping the latest 5, stamped at each session's close: v[k] = P[k-5] vs P[k-5-L]."""
    a, b = series.shift(5 + L), series.shift(5)
    return (b - a) if points else (b / a - 1.0)


def sig_at(sig, day):
    """The signal value at the last session BEFORE `day` (Friday's close for a Monday entry)."""
    k = int(np.searchsorted(sig.index.values, np.datetime64(day))) - 1
    return sig.iloc[k] if k >= 0 else np.nan


def fut_run(S, mkt, sides, sw, stress=False):
    """sides: per week start index -> +1 / -1 / 0. Weekly holdings Monday open -> next Monday open, marked at 16:00 closes,
    whole micros sized from the RAW close before entry. Returns (daily Series, weekly trades [(exit_date, pnl, mkt)])."""
    mult, tick = FUT[mkt]["mult"], FUT[mkt]["tick"]; per = (FEE + tick * mult) * (2.0 if stress else 1.0)
    o, c, rw, t16 = S["o"].values, S["c"].values, S["r"].values, S["t16"].values; n = len(S); dates = S.index
    ws = sorted(sides); daily = np.zeros(n); trades = []; q_prev = 0
    for wi, i in enumerate(ws):
        j = ws[wi + 1] if wi + 1 < len(ws) else n
        s = sides[i]; q = int(s * max(1, round(50000.0 / (rw[i - 1] * mult)))) if s else 0
        daily[i] += q_prev * mult * (o[i] - c[i - 1])             # the old holding's gap into this open
        daily[i] -= abs(q - q_prev) * per
        wk = 0.0
        if q:
            seg = np.empty(j - i); seg[0] = c[i] - o[i]; seg[1:] = c[i + 1:j] - c[i:j - 1]
            daily[i:j] += q * mult * seg; wk += float(q * mult * seg.sum())
            rolls = int(((sw > t16[i - 1]) & (sw <= t16[j - 1])).sum())
            daily[j - 1] -= rolls * abs(q) * per * 2; wk -= rolls * abs(q) * per * 2
            if j < n:
                wk += q * mult * (o[j] - c[j - 1])
            trades.append((dates[j - 1], wk, mkt))
        q_prev = q
    return pd.Series(daily, index=dates), trades


def xasset_sides(S, sig, L, mode="xasset"):
    """sig: the TLT signal Series (sig_series of TLT closes) - ignored for the own-asset twin and buy-and-hold."""
    ws = week_starts(S.index); out = {}
    if mode == "own":
        sig = sig_series(pd.Series(S["c"].values, index=S.index), L, points=True)
    for i in ws:
        v = 1.0 if mode == "hold" else sig_at(sig, S.index[i])
        out[i] = 0 if not np.isfinite(v) or v == 0 else (1 if v > 0 else -1)
    return out


def xasset_cell(F, SW, sig, L, mode="xasset", stress=False):
    d, tr, per_mkt = None, [], {}
    for mkt, S in F.items():
        x, t = fut_run(S, mkt, xasset_sides(S, sig, L, mode), SW[mkt], stress)
        per_mkt[mkt] = x; d = x if d is None else d.add(x, fill_value=0.0); tr += t
    return d.sort_index(), tr, per_mkt


# ------------------------------------------------------------------------------------------------ run
def beta_spy(C, daily, notional=100000.0):
    d = T1.window(daily, *WF); r = C["SPY"].pct_change().reindex(d.index) * notional; ok = r.notna() & d.notna()
    return float(np.cov(d[ok], r[ok])[0, 1] / np.var(r[ok], ddof=1)) if ok.sum() > 50 else float("nan")


def common(v, w, e, ws_net, n95, nmin):
    return {"n>=%d" % nmin: w.get("n", 0) >= nmin, "ROC>=15": w.get("roc30", -1) >= 15, "PF>=1.10": w.get("pf", 0) >= 1.10,
            "t>=2 & >null95": w.get("t", 0) >= 2 and w.get("roc30", -1) > n95, "stress>0": (ws_net or -1) > 0,
            "ex-top>0": w.get("ex_top", -1) > 0, "6/9 yrs": w.get("years_pos", 0) >= 6,
            "ex 2020 crash>0": w.get("ex_2020", -1) > 0, "EARLY>0": e.get("net", -1) > 0}


def describe(bwf, bdd, C, daily, trades, daily_s, early=EARLY):
    w = T1.judge(daily, trades, *WF, bdd=bdd); e = T1.judge(daily, trades, *early); ws = T1.judge(daily_s, [], *WF)
    corr = float(np.corrcoef(T1.window(daily, *WF).reindex(bwf.index, fill_value=0.0), bwf["mtm"])[0, 1]) if w.get("n") else float("nan")
    c = T1.vol_c(bwf, daily); y = T1.book_add(bwf, daily, c) if np.isfinite(c) else {}
    return dict(wf=w, early=e, wf_stress_net=ws.get("net"), corr_book=corr, beta_spy_100k=beta_spy(C, daily),
                seat=T1.seat(bwf, daily, c) if np.isfinite(c) else {},
                a2=dict(c=c, roc30=y.get("roc30"), sortino=y.get("sortino"), dd=y.get("dd"),
                        above_463=bool(y and y["roc30"] >= T1.BOOK_ROC and y["sortino"] >= T1.BOOK_SORT)))


def main(which, O, C, bwf, F=None, SW=None, ev=None, cot=None):
    bdd = T1.dd_days(bwf["mtm"]); rng = np.random.default_rng(SEED); out = {"dd_days": len(bdd)}
    if "AUCTION" in which:
        res = {}; n = len(C); early = early_sessions(C.index)
        H1, H2 = (WF[0], pd.Timestamp("2019-12-31")), (pd.Timestamp("2020-01-01"), WF[1])
        for K in (3, 5):
            d, tr = auction_cell(C, ev, K, early=early); ds, _ = auction_cell(C, ev, K, stress=True, early=early)
            v = describe(bwf, bdd, C, d, tr, ds); v["_daily"] = d
            v["parts"] = {p: round(float(T1.window(auction_cell(C, ev, K, part=p, early=early)[0], *WF).sum())) for p in ("pre", "post")}
            v["funds_wf"] = {f: round(sum(p for (x, p, g) in tr if g == f and WF[0] <= x <= WF[1])) for f in ("IEF", "TLT")}
            v["size_terciles_wf"] = {("small", "mid", "large")[q]: round(float(T1.window(auction_cell(C, ev, K, early=early, terc=q)[0], *WF).sum()))
                                     for q in range(3)}
            v["halves_wf"] = {"2016-19": round(float(T1.window(d, *H1).sum())), "2020-25": round(float(T1.window(d, *H2).sum()))}
            v["skipped_early_close"] = {f: len(ev[f]) - len(keep_events(ev[f], K, early)) for f in ev}
            allv = auction_cell(C, ev, K)[0]
            v["all_auctions_row"] = dict(T1.yard(T1.window(allv, *WF)), net=float(T1.window(allv, *WF).sum()))
            res["AUCTION-K%d" % K] = v
        nmax = []
        for _ in range(REPS):
            sh = auction_shift(ev, n, rng)
            nmax.append(max(T1.yard(T1.window(auction_cell(C, sh, K, early=early)[0], *WF))["roc30"] for K in (3, 5)))
        n95 = float(np.percentile(nmax, 95))
        for k, v in res.items():
            v["checks"] = common(v, v["wf"], v["early"], v["wf_stress_net"], n95, 100)
            v["checks"]["both funds>0"] = all(x > 0 for x in v["funds_wf"].values())
        me = month_end_row(C)
        out["AUCTION"] = dict(cells=res, null95=n95, null50=float(np.percentile(nmax, 50)),
                              month_end_row=T1.yard(T1.window(me, *WF)) | {"net": float(T1.window(me, *WF).sum())})
    if "COT" in which:
        res = {}; n = len(O); wk = {}
        for W in (52, 156):
            weeks = cot_weeks(O, C, cot, W); wk[W] = weeks
            legs = cot_legs(weeks, n)
            d, tr = T1.run_positions(O, C, legs); ds, _ = T1.run_positions(O, C, legs, stress=True)
            v = describe(bwf, bdd, C, d, per_week(tr), ds); v["_daily"] = d
            mk = {}
            for (x, p, g) in tr:
                if WF[0] <= x <= WF[1]:
                    mk[g] = mk.get(g, 0.0) + p
            v["markets_wf"] = {g: round(p) for g, p in sorted(mk.items())}
            v["opposite_sign"] = T1.yard(T1.window(T1.run_positions(O, C, cot_legs(weeks, n, sign=-1.0))[0], *WF))
            v["tsmom_overlap"] = tsmom_overlap(C, legs)
            v["currency_cluster"] = currency_cluster(legs)
            gw = {}
            for (i, j, f, nt, g) in legs:
                if WF[0] <= O.index[i] <= WF[1]:
                    gw[i] = gw.get(i, 0.0) + abs(nt)
            gv = np.array(list(gw.values())) if gw else np.array([np.nan])
            v["gross_per_week"] = dict(min=round(float(gv.min())), median=round(float(np.median(gv))), max=round(float(gv.max())))
            res["COT-W%d" % W] = v
        nmax = []
        for _ in range(REPS):
            nmax.append(max(T1.yard(T1.window(T1.run_positions(O, C, cot_legs(wk[W], n, rng=rng))[0], *WF))["roc30"] for W in (52, 156)))
        n95 = float(np.percentile(nmax, 95))
        for k, v in res.items():
            v["checks"] = common(v, v["wf"], v["early"], v["wf_stress_net"], n95, 400)
            v["checks"]["ex-best-market>0"] = (sum(v["markets_wf"].values()) - max(v["markets_wf"].values())) > 0 if v["markets_wf"] else False
        out["COT"] = dict(cells=res, null95=n95, null50=float(np.percentile(nmax, 50)))
    if "XASSET" in which:
        res = {}; tlt = C["TLT"].dropna(); SG = {L: sig_series(tlt, L) for L in (21, 252)}
        for L in (21, 252):
            d, tr, pm = xasset_cell(F, SW, SG[L], L); ds, _, _ = xasset_cell(F, SW, SG[L], L, stress=True)
            v = describe(bwf, bdd, C, d, per_week(tr), ds, early=EARLY_FUT); v["_daily"] = d
            v["markets_wf"] = {m: round(float(T1.window(x, *WF).sum())) for m, x in pm.items()}
            od = xasset_cell(F, SW, None, L, mode="own")[0]
            v["own_twin"] = dict(T1.yard(T1.window(od, *WF)), dd_sum=T1.judge(od, [], *WF, bdd=bdd).get("dd_sum"))
            v["long_share"] = float(np.mean([s_ > 0 for S in F.values() for s_ in xasset_sides(S, SG[L], L).values()]))
            spy_sig = sig_series(C["SPY"].dropna(), L); ws = week_starts(O.index); legs = []
            for wi, i in enumerate(ws[:-1]):
                x = sig_at(spy_sig, O.index[i])
                if np.isfinite(x) and x != 0:
                    legs.append((i, ws[wi + 1], "TLT", -np.sign(x) * NOTL, "TLT"))
            v["bond_mirror"] = T1.yard(T1.window(T1.run_positions(O, C, legs)[0], *WF))
            res["XASSET-L%d" % L] = v
        hold = T1.yard(T1.window(xasset_cell(F, SW, None, 21, mode="hold")[0], *WF))
        nmax = []
        for _ in range(REPS):
            k = int(rng.integers(252, 2001))      # one shift per null world, applied to each cell's own signal series
            nmax.append(max(T1.yard(T1.window(xasset_cell(F, SW, pd.Series(np.roll(SG[L].values, k), index=SG[L].index), L)[0], *WF))["roc30"]
                            for L in (21, 252)))
        n95 = float(np.percentile(nmax, 95))
        for k, v in res.items():
            v["checks"] = common(v, v["wf"], v["early"], v["wf_stress_net"], n95, 400)
            v["checks"]["beats own twin + hold"] = v["wf"].get("roc30", -1) > max(v["own_twin"]["roc30"], hold["roc30"])
            v["checks"]["both NQ, ES>0"] = all(x > 0 for x in v["markets_wf"].values())
        out["XASSET"] = dict(cells=res, null95=n95, null50=float(np.percentile(nmax, 50)), buy_hold=hold)
    for fam in which:
        out[fam]["passes"] = [k for k, v in out[fam]["cells"].items() if all(v["checks"].values())]
    return out


def report(out):
    for fam in ("AUCTION", "COT", "XASSET"):
        if fam not in out:
            continue
        F = out[fam]
        print("\n%s  null 95th pct ROC@30k %.1f (50th %.1f; power line ~ %.1f ROC points)" % (fam, F["null95"], F["null50"], F["null95"] - F["null50"]))
        for k, v in F["cells"].items():
            w, s, a2 = v["wf"], v["seat"], v["a2"]
            print("  %-14s n %5s ROC@30k %6.1f net $%s DD $%s Sort %5.2f PF %4.2f t %5.2f yrs+ %s EARLY $%s corr %.2f beta/100k %.2f %s" % (
                k, w.get("n"), w.get("roc30", float("nan")), f"{w.get('net', 0):,.0f}", f"{w.get('dd', 0):,.0f}", w.get("sortino", float("nan")),
                w.get("pf", 0), w.get("t", 0), w.get("years_pos"), f"{v['early'].get('net', 0):,.0f}", v["corr_book"], v["beta_spy_100k"],
                "PASS" if all(v["checks"].values()) else "fails " + ", ".join(c for c, ok in v["checks"].items() if not ok)))
            for extra in ("parts", "funds_wf", "size_terciles_wf", "halves_wf", "skipped_early_close", "markets_wf", "tsmom_overlap",
                          "currency_cluster", "gross_per_week", "long_share"):
                if extra in v:
                    print("    %s: %s" % (extra, v[extra]))
            for extra in ("opposite_sign", "own_twin", "bond_mirror", "all_auctions_row"):
                if extra in v:
                    dd_ = v[extra].get("dd_sum")
                    print("    %s: ROC@30k %.1f net $%s%s" % (extra, v[extra]["roc30"], f"{v[extra]['net']:,.0f}",
                          ("  DD-day $%s (cell $%s)" % (f"{dd_:,.0f}", f"{w.get('dd_sum', 0):,.0f}")) if dd_ is not None else ""))
            if s:
                print("    seat: DD-day $%s over %d episodes, without the best $%s; vol share %.3f; years %s" % (
                    f"{s['dd_sum']:,.0f}", s["episodes"], f"{s['dd_ex_best_episode']:,.0f}", s["vol_share"], s["years"]))
                print("    A2 report: c %.2f -> book ROC@30k %.2f Sort %.3f%s" % (a2["c"], a2["roc30"], a2["sortino"], "  (above #463)" if a2["above_463"] else ""))
        for extra in ("month_end_row", "buy_hold"):
            if extra in F:
                print("  %s: ROC@30k %.1f net $%s" % (extra, F[extra]["roc30"], f"{F[extra]['net']:,.0f}"))
        print("  passes:", F["passes"] or "none")


def selftest():
    global REPS, WF, EARLY, EARLY_FUT
    rng = np.random.default_rng(5)
    dates = pd.bdate_range("2012-01-02", "2019-12-31"); n = len(dates)
    names = ["SPY", "QQQ", "IEF", "TLT", "GLD", "SLV", "USO", "FXE", "FXY", "FXA", "UUP"]
    O = pd.DataFrame(index=dates); C = pd.DataFrame(index=dates)
    for t in names:
        lp = 4 + np.cumsum(rng.normal(0.0001, 0.009, n)); C[t] = np.exp(lp)
        O[t] = C[t].shift(1).fillna(C[t].iloc[0]) * np.exp(rng.normal(0, 0.002, n))
    bwf = pd.DataFrame({"mtm": rng.normal(60, 600, n)}, index=dates)
    WF = (pd.Timestamp("2016-01-01"), pd.Timestamp("2019-12-31")); EARLY = (pd.Timestamp("2013-01-01"), pd.Timestamp("2015-12-31"))
    EARLY_FUT = EARLY; T1.WF, T1.EARLY = WF, EARLY; REPS = 3; bwf = T1.window(bwf, *WF)
    ev = {"IEF": [(t, t - 6, t % 3) for t in range(30, n - 10, 21)], "TLT": [(t, t - 2, t % 3) for t in range(40, n - 10, 21)]}
    assert len(early_sessions(dates)) >= 4 * 7, "early-close list must find ~4-5 sessions a year"
    assert keep_events([(100, 98, 0)], 3, {102}) == [] and keep_events([(100, 98, 0)], 3, {104}) == [(100, 98, 0)]
    p = auction_pos(n, [(100, 98)], 5)
    assert p[99] == -1 and p[98] == 0 and p[101] == 1 and p[105] == 1 and p[106] == 0, "short must not open before the announcement close"
    cot = {}
    for f in names:
        rd = pd.date_range("2011-01-04", "2019-12-31", freq="7D")
        cot[f] = pd.DataFrame({"rd": rd, "hp": np.cumsum(rng.normal(0, 0.02, len(rd))), "avail": rd + pd.Timedelta(days=7)})
    F = {}
    for m in FUT:
        c = 1000 + np.cumsum(rng.normal(0, 10, n)); o = np.r_[c[0], c[:-1]] + rng.normal(0, 3, n)
        F[m] = pd.DataFrame({"o": o, "c": c, "r": c, "t16": [int(d.value // 10**9) for d in dates]}, index=dates)
    SW = {m: np.array([], dtype=np.int64) for m in FUT}
    out = main(["AUCTION", "COT", "XASSET"], O, C, bwf, F, SW, ev, cot)
    report(out)
    for fam in out:
        if isinstance(out[fam], dict) and "cells" in out[fam]:
            for k, v in out[fam]["cells"].items():
                assert v["wf"].get("n", 0) > 0, k + " must trade on synthetic data"
                assert v["wf"].get("pf", 9) < 1.6, k + " looks like an edge on random data"
    print("SELFTEST OK - synthetic only, no real data read")


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        selftest(); sys.exit(0)
    if "--fetch" in sys.argv:
        fetch(); sys.exit(0)
    which = [a for a in sys.argv[1:] if a in ("AUCTION", "COT", "XASSET")] or ["AUCTION", "COT", "XASSET"]
    O, C, shas = T1.load()
    bk = pd.read_csv(T1.BOOK, parse_dates=["date"]).set_index("date"); bwf = T1.window(bk, *WF)
    base = T1.yard(bwf["mtm"])
    print("#463 WF: %.2f / %.3f / $%s (must be 93.81 / 3.816 / $44,849)" % (base["roc30"], base["sortino"], f"{base['dd']:,.0f}"))
    if not (abs(base["roc30"] - 93.81) < 0.01 and abs(base["sortino"] - 3.816) < 0.001 and abs(base["dd"] - 44849) < 1):
        sys.exit("STOP: #463 does not reproduce")
    ev = cot = F = SW = None
    if "AUCTION" in which:
        ev, info = load_auctions(C.index); shas["treasury_auctions"] = sha(AUC_FILE); print("auctions:", info)
    if "COT" in which:
        cot = load_cot(); shas["cot_legacy_futures"] = sha(COT_FILE)
        print("COT markets:", {f: (len(g), str(g["rd"].min().date()), str(g["rd"].max().date())) for f, g in cot.items()})
    if "XASSET" in which:
        F = load_futures(); SW = {m: switches(m) for m in F}
        print("futures sessions:", {m: (len(S), str(S.index[0].date()), str(S.index[-1].date())) for m, S in F.items()})
    print("data:", shas)
    out = main(which, O, C, bwf, F, SW, ev, cot)
    report(out)
    os.makedirs(OUT, exist_ok=True)
    slim = {fam: ({k: ({kk: vv for kk, vv in v.items() if kk != "_daily"} if k == "cells" else v) for k, v in F_.items()}
                  if isinstance(F_, dict) else F_) for fam, F_ in out.items()}
    for fam in slim:
        if isinstance(slim[fam], dict) and "cells" in slim[fam]:
            slim[fam]["cells"] = {k: {kk: vv for kk, vv in v.items() if kk != "_daily"} for k, v in out[fam]["cells"].items()}
    slim["shas"] = shas
    with open(os.path.join(OUT, "stage_a_%s.json" % "_".join(which)), "w") as f:
        json.dump(slim, f, default=float, indent=1)
    print("written", OUT)
