# Round 8 (2026-09-30): TRANSFER r2 - the ORB, NOISE and TTM crowns, UNCHANGED, on ETF proxies (IEF FXE USO GLD; ORB also IWM DIA).
# Pre-registered: tools/rocfrontier/PREREG_TRANSFER_R2.txt (commit 854955a0), written before any ETF intraday bar existed.
#   python r8_transfer_etf.py pull      needs the owner's Alpaca keys: 5Min + 30Min RTH masters through the shared loader, daily bars -> research cache
#   python r8_transfer_etf.py gates     section 10 data gates on the registered fund masters, PRE-LOCKBOX ONLY
#   python r8_transfer_etf.py ttmcheck  TTM wrapper acceptance vs the real ES file (local data, no fund needed) - must pass before A
#   python r8_transfer_etf.py A         Stage A, PRE-LOCKBOX ONLY (nothing on/after 2025-06-30 is loaded into a strategy, computed or printed)
#   python r8_transfer_etf.py B --ledger-ok   Stage B (lockbox, once, after Stage A is in the ledger) - refuses unless a Stage A pass is on file
#   python r8_transfer_etf.py C         Stage C (book add vs BOOK #463) - refuses unless a Stage B survivor is on file
#   python r8_transfer_etf.py smoke [DIR]   offline self-test on stand-in funds cut from the ES / NQ masters (numbers mean nothing)
# Run from anywhere; imports augur_engine from the shared checkout (EDGELOG_ROOT overrides) and never chdirs into a worktree.
import datetime as dt, hashlib, importlib.util, inspect, json, math, os, subprocess, sys, time, warnings, zlib
REPO = os.environ.get("EDGELOG_ROOT", r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"); sys.path.insert(0, REPO)
import numpy as np, pandas as pd
warnings.filterwarnings("ignore", message="Mean of empty slice", category=RuntimeWarning)       # ORB_3_6's volume-pace warm-up; benign

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.environ.get("EDGELOG_ROCFRONTIER_R8", r"C:\EdgeLog\_anatomy_cache\rocfrontier\r8")    # results, outside git
CACHE = os.environ.get("EDGELOG_ALPACA_CACHE", r"C:\EdgeLog\alpaca_cache")                      # raw research pulls (daily bars)
R4 = os.environ.get("EDGELOG_ROCFRONTIER_R4", r"C:\EdgeLog\_anatomy_cache\rocfrontier\r4")      # BOOK #463's daily + trade files
D0, PRE = "2016-01-04", "2025-06-29"                                   # data start / last pre-lockbox day (date_to of every Stage A load)
WF0, LB0, LB1 = (pd.Timestamp(x) for x in ("2016-07-01", "2025-06-30", "2026-06-30"))
LBX, LBY = pd.Timestamp("2026-07-01"), (LB1 - LB0).days / 365.25      # LB = 06-30 .. 06-30 INCLUSIVE, frontier years (365 / 365.25)
LBT = LB0.tz_localize("US/Eastern")
COST, STRESS, USD, ES_COST = 0.02, 0.04, 100_000.0, 0.363              # $ a share round trip; the unit's notional; TTM's ES cost constant
RULE = dict(n=100, roc=15.0, pf=1.10, t=2.69, years=0.60, lb_n=50, miss=0.01, cent=0.01, rel=0.001, ndaily=10)     # section 6 / 7 / 10 thresholds
FUNDS = {"IEF": ("ORB", "NOISE", "TTM"), "FXE": ("ORB", "NOISE", "TTM"), "USO": ("ORB", "NOISE", "TTM"), "GLD": ("ORB", "NOISE", "TTM"),
         "IWM": ("ORB",), "DIA": ("ORB",)}                              # 14 cells
FMAP = None                                                             # smoke only: {fund: {tf: (instrument, source)}} of stand-in masters
CHECK_BOOK = True                                                       # smoke only: the synthetic book cannot reproduce #463's numbers

# the crown settings, exactly as written in the pre-registration (section 1); every knob is passed explicitly
ORB_P = {"or_bars": 2, "trade_mode": "First-candle dir", "stop_frac": 2.5, "breakout_buf": 0.25, "close_confirm": True, "partial_exit_R": 0.0,
         "trail_bars": 0, "be_after_R": 0.5, "target_R": 5.0, "atr_filter": 0.75, "vpace_filter": 0.8, "flat_eod": True, "skip_holidays": True}
NOISE_P = {"lookback": 40, "band_mult_long": 0.75, "band_mult_short": 1.5, "exit_mode": "vwap", "side": "Both", "window": "all_day", "flat_eod": True,
           "skip_holidays": False, "stop_mode": "bandwidth", "stop_k": 1.75, "confirm_bars": 1, "daytype_mode": "skip_bot_short", "daytype_lo": 0.2,
           "daytype_hi": 0.8, "vol_skip_pct": 95.0}
TTM_P = {"kc_mult": 1.5, "eod_cutoff": 5}
STRAT = {"ORB": ("ORB_3_6_R6.py", ORB_P, "5m"), "NOISE": ("NOISE_1_1_NBHD.py", NOISE_P, "5m"), "TTM": ("TTMSQZ_3_0_ES30SSOF2R347.py", TTM_P, "30m")}
STACK = {"ORB": ["ORB_3_6_R6.py", "ORB_3_6.py"], "NOISE": ["NOISE_1_1_NBHD.py", "NOISE_1_0.py"],
         "TTM": ["TTMSQZ_1_0.py", "TTMSQZ_3_0.py", "TTMSQZ_3_0_ES30SS.py", "TTMSQZ_3_0_ES30SSO.py", "TTMSQZ_3_0_ES30SSOF2.py",
                 "TTMSQZ_3_0_ES30SSOF2R.py", "TTMSQZ_3_0_ES30SSOF2R347.py"]}


def js(o):
    if isinstance(o, np.bool_): return bool(o)
    if isinstance(o, np.integer): return int(o)
    if isinstance(o, np.floating): return float(o)
    if isinstance(o, np.ndarray): return o.tolist()
    if isinstance(o, (pd.Timestamp, dt.date, dt.datetime)): return str(o)[:10]
    return str(o)


def save(name, obj):
    json.dump(obj, open(os.path.join(OUT, name), "w"), indent=1, default=js)


def need_json(name, why):
    p = os.path.join(OUT, name)
    if not os.path.exists(p):
        print(f"refused: {name} is missing - {why}")
        return None
    return json.load(open(p))


def sha(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def stack_shas(*strats):
    return {n: sha(os.path.join(REPO, "augur_strategies", n)) for s in (strats or STACK) for n in STACK[s]}


_E = []
def eng():
    if not _E:
        from augur_engine import book as B, data as D, engine as E
        _E.extend((B, D, E))
    return _E


# ------------------------------------------------------------------ stats (the owner's yardstick, r5_nqbrd.py's helpers)
def ddmax(x):
    q = np.cumsum(x)
    return float((np.maximum.accumulate(np.concatenate([[0.0], q]))[1:] - q).max()) if len(q) else 0.0


def so(x):
    x = np.asarray(x, float)
    dn = np.sqrt(np.mean(np.minimum(x, 0.0) ** 2)) if len(x) else 0.0
    return float(x.mean() / dn * np.sqrt(252)) if dn > 0 else float("nan")


def daily_pnl(t, days, t0, t1):
    """Daily P&L over EVERY session day of the window, zeros on flat days (a trade date missing from `days` is added, never dropped)."""
    dw = days[(days >= t0) & (days < t1)].union(pd.DatetimeIndex(t["date"].unique()))
    return t.groupby("date")["pnl"].sum().reindex(dw).fillna(0.0)


def stats(df, days, t0, t1, yrs=None):
    t = df[(df.date >= t0) & (df.date < t1)]
    d = daily_pnl(t, days, t0, t1)
    yrs, n, net = yrs or (t1 - t0).days / 365.25, len(t), float(t["pnl"].sum())
    gw, gl, ddv = float(t.pnl[t.pnl > 0].sum()), float(-t.pnl[t.pnl < 0].sum()), ddmax(d.values)
    sd = float(d.std(ddof=1)) if len(d) > 1 else float("nan")
    by = t.groupby(t.date.dt.year)["pnl"].sum().reindex(range(t0.year, (t1 - pd.Timedelta(days=1)).year + 1)).fillna(0.0)   # no-trade years count as not positive
    big = float(t.pnl.max()) if n else 0.0
    return {"n": n, "net": net, "pf": gw / gl if gl > 0 else (float("inf") if gw > 0 else 0.0), "dd_daily": ddv,
            "roc30": 30.0 * (net / yrs) / ddv if ddv > 0 else float("nan"), "sortino": so(d.values),
            "t": float(d.mean() / (sd / np.sqrt(len(d)))) if sd > 0 else float("nan"), "days": len(d), "years_pos": float((by > 0).mean()),
            "net_ex_big": net - big, "big": big, "win_rate": float((t.pnl > 0).mean()) if n else 0.0}


def book(extra, t0, t1, yrs=None):
    b = pd.read_csv(os.path.join(R4, "book463_daily.csv"), parse_dates=["date"]).set_index("date")
    idx = b.index.union(extra.index) if extra is not None else b.index
    M, C = b["mtm"].reindex(idx).fillna(0.0), b["close"].reindex(idx).fillna(0.0)
    if extra is not None:
        e = extra.reindex(idx).fillna(0.0); M, C = M + e, C + e
    sel = (idx >= t0) & (idx < t1)
    yrs, net, ddv = yrs or (t1 - t0).days / 365.25, float(C[sel].sum()), ddmax(M[sel].values)
    return {"net": net, "roc30": net / yrs / 1000 * 30000 / ddv, "sortino": so(M[sel].values), "dd_daily": ddv}


def stouffer(cells):
    out = {}
    for s in STRAT:
        z = [c["WF"]["t"] for c in cells.values() if c["strat"] == s and np.isfinite(c["WF"]["t"])]
        if z:
            Z = sum(z) / math.sqrt(len(z))                      # daily t on ~2,200 days: t = z to two decimals
            out[s] = {"k": len(z), "Z": Z, "p_one_sided": 0.5 * math.erfc(Z / math.sqrt(2))}
    return out


def judge_a(c, rule):
    w = c["WF"]
    chk = {"n": w["n"] >= rule["n"], "roc": w["roc30"] >= rule["roc"], "pf": w["pf"] >= rule["pf"], "t": w["t"] >= rule["t"],
           "stress": c["stress_net"] > 0, "exbig": w["net_ex_big"] > 0, "years": w["years_pos"] >= rule["years"]}
    return chk, bool(all(chk.values()))


def judge_b(lb, strat, rule):
    chk = {"n": strat == "TTM" or lb["n"] >= rule["lb_n"], "net": lb["net"] > 0, "exbig": lb["net_ex_big"] > 0}     # TTM: judged only inside a book
    return chk, bool(all(chk.values()))


def judge_c(wf, lb, bwf, blb, big):
    chk = {"roc_wf": wf["roc30"] > bwf["roc30"], "roc_lb": lb["roc30"] > blb["roc30"], "so_wf": wf["sortino"] > bwf["sortino"],
           "so_lb": lb["sortino"] > blb["sortino"], "lb_exbig": lb["net"] - big > 0}
    return chk, bool(all(chk.values()))


# ------------------------------------------------------------------ NYSE cash-session calendar (no calendar package is installed)
def _easter(y):
    a, b, c = y % 19, y // 100, y % 100
    d, e = divmod(b, 4); f = (b + 8) // 25; g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30; i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7; m = (a + 11 * h + 22 * l) // 451
    mo, da = divmod(h + l - 7 * m + 114, 31)
    return dt.date(y, mo, da + 1)


def _nth(y, mo, wd, n):
    d = dt.date(y, mo, 1)
    return d + dt.timedelta(days=(wd - d.weekday()) % 7 + 7 * (n - 1))


def _last(y, mo, wd):
    d = dt.date(y + (mo == 12), mo % 12 + 1, 1) - dt.timedelta(days=1)
    return d - dt.timedelta(days=(d.weekday() - wd) % 7)


def _obs(d):                                                           # Saturday -> Friday, Sunday -> Monday
    return d - dt.timedelta(days=1) if d.weekday() == 5 else d + dt.timedelta(days=1) if d.weekday() == 6 else d


def nyse_sessions(d0, d1):
    """{date: close minute after midnight (960 full day, 780 early close)} for every NYSE session in [d0, d1]."""
    H, E = set(), set()
    for y in range(d0.year, d1.year + 1):
        ny = dt.date(y, 1, 1)
        if ny.weekday() == 6: H.add(ny + dt.timedelta(days=1))
        elif ny.weekday() != 5: H.add(ny)                              # a Saturday New Year is NOT observed on the Friday (year end)
        H |= {_nth(y, 1, 0, 3), _nth(y, 2, 0, 3), _easter(y) - dt.timedelta(days=2), _last(y, 5, 0), _obs(dt.date(y, 7, 4)),
              _nth(y, 9, 0, 1), _nth(y, 11, 3, 4), _obs(dt.date(y, 12, 25)), dt.date(2018, 12, 5), dt.date(2025, 1, 9)}     # last two: days of mourning
        if y >= 2022: H.add(_obs(dt.date(y, 6, 19)))
        E.add(_nth(y, 11, 3, 4) + dt.timedelta(days=1))
        E |= {d for d in (dt.date(y, 7, 3), dt.date(y, 12, 24)) if d.weekday() < 4 and d not in H}
    out, d = {}, d0
    while d <= d1:
        if d.weekday() < 5 and d not in H:
            out[d] = 780 if d in E else 960
        d += dt.timedelta(days=1)
    return out


def cal_selftest():
    s = nyse_sessions(dt.date(2016, 1, 1), dt.date(2026, 12, 31))
    iso = dt.date.fromisoformat
    for d in ("2016-07-04", "2016-12-26", "2017-01-02", "2018-12-05", "2020-04-10", "2020-07-03", "2021-12-24", "2022-06-20", "2022-12-26", "2023-01-02",
              "2025-01-09", "2025-04-18", "2026-07-03"):
        assert iso(d) not in s, f"{d} must be closed"
    for d in ("2016-11-25", "2017-07-03", "2018-12-24", "2019-07-03", "2020-12-24", "2023-07-03", "2024-11-29", "2025-12-24"):
        assert s[iso(d)] == 780, f"{d} must be an early close"
    for d in ("2021-12-31", "2020-07-02", "2022-07-01", "2016-12-23", "2024-07-05"):
        assert s[iso(d)] == 960, f"{d} must be a full session"
    assert len(nyse_sessions(dt.date(2016, 7, 1), dt.date(2025, 6, 29))) == 2260   # also = the ES / NQ RTH masters' NYSE-open days, checked 2026-09-30


def bar_gate(arr, d0, d1, tf=5):
    """Expected vs present RTH bar slots over [d0, d1] (ET dates) on the NYSE calendar: 78 a full 5-minute session, 42 on an early close."""
    ix = pd.DatetimeIndex(arr["index"]).tz_localize(None)
    day, mn = ix.normalize(), np.asarray(ix.hour * 60 + ix.minute)
    cm = pd.Series({pd.Timestamp(k): v for k, v in nyse_sessions(d0.date(), d1.date()).items()}, dtype=float)
    w = (day >= d0) & (day <= d1)
    day, mn = day[w], mn[w]
    c = cm.reindex(day).to_numpy()
    fin = np.isfinite(c)
    slot = fin & (mn >= 570) & (mn < np.where(fin, c, 0)) & ((mn - 570) % tf == 0)
    have = pd.DataFrame({"d": day[slot], "m": mn[slot]}).drop_duplicates().groupby("d").size().reindex(cm.index).fillna(0)
    need = (cm - 570) // tf
    miss = (need - have).clip(lower=0)
    exp, mis = int(need.sum()), int(miss.sum())
    return {"expected": exp, "missing": mis, "missing_pct": mis / exp if exp else float("nan"), "sessions": len(cm), "sessions_no_bars": int((have == 0).sum()),
            "misaligned_bars": int(((mn - 570) % tf != 0).sum()), "extra_bars": int((~slot).sum()), "extra_after_early_close": int(((~slot) & fin & (c == 780) & (mn >= 780)).sum()),
            "worst": [(str(k.date()), int(v)) for k, v in miss[miss > 0].sort_values(ascending=False).head(5).items()]}


def half_day_info(arr):
    """How ORB's own holiday rule (skip a session shorter than 70% of the median session length, median over every loaded session) treats the real
    data: it is told to us before any P&L exists. Counts bars only."""
    ix = pd.DatetimeIndex(arr["index"]).tz_localize(None)
    lens = pd.Series(1, index=ix.normalize()).groupby(level=0).size()
    thr = 0.70 * float(lens.median())
    skipped = set(lens.index[lens < thr])
    early = [pd.Timestamp(k) for k, v in nyse_sessions(WF0.date(), pd.Timestamp(PRE).date()).items() if v == 780]
    return {"median_bars": float(lens.median()), "threshold": thr, "sessions_skipped": len(skipped), "sessions_skipped_in_WF": sum(1 for d in skipped if d >= WF0),
            "early_closes_in_WF": len(early), "early_closes_skipped": sum(1 for d in early if d in skipped),
            "early_close_bar_counts": {str(d.date()): int(lens.get(d, 0)) for d in early}}


# ------------------------------------------------------------------ fund masters, legs, the TTM wrapper
def src_of(f, tf):
    """(instrument, source) the fund's master is registered under; the shared loader tags them `alpaca_split_rth` under the FUND ticker."""
    return FMAP[f][tf] if FMAP else (f, "alpaca_split_rth")


def load(f, tf, d1):
    B, D, E = eng()
    inst, src = src_of(f, tf)
    m = D.find_master(inst, tf, "rth", src)
    if m is None:
        raise SystemExit(f"no master for {f} {tf} ({inst}, rth, {src}) - run `pull` first")
    a = D.load_master_arrays(m, D0, d1)
    if d1 < "2025-06-30":
        assert len(a["index"]) and a["index"].max() < LBT, "a pre-lockbox load reached the lockbox"
    for k in ("open", "high", "low", "close", "volume", "day_id"):
        if isinstance(a.get(k), np.ndarray): a[k].setflags(write=False)     # a strategy writing into shared arrays must fail loudly
    return a


def assert_volume(a, f):
    v = a.get("volume")
    if v is None or not np.isfinite(v).all() or (v > 0).mean() < 0.99:
        raise SystemExit(f"{f}: no usable volume - ORB's volume-pace gate and NOISE's VWAP exit would silently change")


def run_leg(leg, d0, d1, arr=None):
    """book._leg_trades for ONE leg (same engine call, same exit-day stamping, same dollars) but keeping the per-trade table.
    leg['strategy'] may be a file name or an already-imported module object (the TTM wrapper); `arr` = a preloaded master window."""
    B, D, E = eng()
    if arr is None:
        m = D.find_master(leg["instrument"], leg["timeframe"], leg.get("session") or "rth", leg.get("source"))
        if m is None:
            raise ValueError(f"no data for leg {leg['instrument']} {leg['timeframe']} {leg.get('source')}")
        arr = D.load_master_arrays(m, d0, d1)
    res = E.run_backtest(leg["strategy"], arrays=arr, params=leg.get("params") or {}, cost_pts=float(leg.get("cost_pts", 0) or 0), return_trades=True)
    tr = list((res or {}).get("trades") or [])
    ix = pd.DatetimeIndex(arr["index"]).tz_localize(None)
    last, mult, wt = len(ix) - 1, float(leg["mult"]), float(leg.get("weight", 1) or 1)
    e, x = np.array([int(t[0]) for t in tr], int), np.array([min(int(t[1]), last) for t in tr], int)
    pts = np.array([float(t[2]) for t in tr], float)
    return pd.DataFrame({"entry": ix[e], "exit": ix[x], "date": ix[x].normalize(), "side": [int(t[3]) for t in tr],
                         "px": [float(t[4]) for t in tr], "pts": pts, "pnl": pts * mult * wt})


def same_as_book(leg, d0, d1, arr=None):
    """run_leg vs book._leg_trades on the same leg: exit dates and dollars must be identical."""
    B, D, E = eng()
    tr, _ = B._leg_trades(leg, d0, d1)
    mine = run_leg(leg, d0, d1, arr)
    dd, uu = np.array([t[0] for t in tr], dtype="datetime64[D]"), np.array([t[1] for t in tr], float)
    ok = len(tr) == len(mine) and bool((dd == mine.date.values.astype("datetime64[D]")).all()) and bool((uu == mine.pnl.values).all())
    return {"ok": ok, "n": len(tr), "net": float(uu.sum())}


_NO_ROLLS = lambda: (np.zeros(0, np.int64), np.zeros(0))
BOOK_TTM_LEG = {"strategy": "TTMSQZ_3_0_ES30SSOF2.py", "params": {"eod_cutoff": 1, "kc_mult": 1.5}, "instrument": "ES", "timeframe": "30m", "session": "rth",
                "source": "db_adj_rth", "cost_pts": 0.363, "mult": 50, "weight": 3}          # BOOK #463's real TTM leg (book463_legs.json, leg 2)
IDENT, BOOK_LADDER, UNIT_LADDER = {1.0: 1.0, 1.5: 1.5, 2.25: 2.25}, {1.0: 3, 1.5: 4, 2.25: 7}, {1.0: 1, 1.5: 1, 2.25: 1}


class TTMWrap:
    """The TTM transfer wrapper, in memory. It loads its OWN private copy of TTMSQZ_3_0_ES30SSOF2R347.py (which loads private copies of
    the 2R / OF2 / SSO / SS / 3_0 / 1_0 files) and overrides, at call time, exactly the five places the constants live:
      deep-squeeze tilt 1.5   ss._TILT_MULT   (TTMSQZ_3_0_ES30SS.py; read per trade by ss and by SSO)
      open-bar tilt 1.5       so._OPEN_MULT   (TTMSQZ_3_0_ES30SSO.py; read per trade)
      3/4/7 ladder            top._LADDER     (TTMSQZ_3_0_ES30SSOF2R347.py; read per trade)
      cost constant 0.363     ss._COST_PTS    (TTMSQZ_3_0_ES30SS.py; read by ss, SSO and 347 - priced-at-size-s trades only)
      roll table              guard._switches (TTMSQZ_3_0_ES30SSOF2R.py; the function roll_offsets() calls to read tools/data/rolls_ES.csv)
    Nothing else is touched: entries, exits, stops, the hourly gate, fade_bars 2 (frozen by OF2 at import) and eod_cutoff come from the files."""
    STRATEGY_NAME = "TTM transfer wrapper (r8, in memory)"

    def __init__(self, deep, openb, ladder, cost, rolls):
        spec = importlib.util.spec_from_file_location("r8_ttm347", os.path.join(REPO, "augur_strategies", "TTMSQZ_3_0_ES30SSOF2R347.py"))
        self.top = importlib.util.module_from_spec(spec); spec.loader.exec_module(self.top)
        self.guard = self.top._guard; self.so = self.guard._base._so; self.ss = self.so._ss
        self.switches = self.guard._switches                           # the real ES roll-table reader, kept so ES mode can restore it
        self.deep, self.openb, self.ladder, self.cost, self.rolls = deep, openb, dict(ladder), float(cost), rolls

    @classmethod
    def fund(cls, cost):                                               # the pre-registered transfer wrapper
        return cls(1.0, 1.0, UNIT_LADDER, cost, False)

    @classmethod
    def es(cls, ladder=IDENT):                                         # every constant back to the ES value (acceptance test)
        return cls(1.5, 1.5, ladder, ES_COST, True)

    def apply(self):
        self.ss._TILT_MULT, self.so._OPEN_MULT, self.ss._COST_PTS = self.deep, self.openb, self.cost
        self.top._LADDER = dict(self.ladder)
        self.guard._switches = self.switches if self.rolls else _NO_ROLLS

    def run_backtest(self, opens, highs, lows, closes, volumes=None, day_id=None, index=None, return_trades=False, **kw):
        self.apply()
        return self.top.run_backtest(opens, highs, lows, closes, volumes=volumes, day_id=day_id, index=index, return_trades=return_trades, **kw)

    def describe(self):
        self.apply()
        return {"deep_tilt": self.ss._TILT_MULT, "open_tilt": self.so._OPEN_MULT, "ladder": self.top._LADDER, "cost_const": self.ss._COST_PTS,
                "roll_rows": int(len(self.guard._switches()[0])), "fade_bars": self.ss._FROZEN["fade_bars"], "gate_len": self.so._GATE_LEN}


def wrapper_sha():
    """Fingerprint of the wrapper's own code and constants: ttmcheck's pass is only valid for THIS wrapper."""
    return hashlib.sha256((inspect.getsource(TTMWrap) + repr((IDENT, BOOK_LADDER, UNIT_LADDER, ES_COST, COST))).encode()).hexdigest()


def effective(strat):
    """The settings a strategy will really run with: signature defaults, then the file's own champion core, then the pre-registered params."""
    B, D, E = eng()
    name, P, tf = STRAT[strat]
    if strat == "TTM":
        return dict(P, **TTMWrap.fund(COST).describe())
    from augur_engine.strategies import load_strategy
    mod = load_strategy(name)
    base = getattr(mod, "_base", mod)
    sig = inspect.signature(base.run_backtest).parameters
    bad = [k for k in P if k not in sig]
    assert not bad, f"{name}: params the strategy does not have (they would be silently dropped): {bad}"
    skip = {"opens", "highs", "lows", "closes", "volumes", "day_id", "index", "return_trades", "_stop_event", "_pause_event", "return_levels",
            "session_in_progress", "vol_prior_ranges"}
    eff = {k: p.default for k, p in sig.items() if k not in skip and p.default is not inspect.Parameter.empty}
    eff.update(getattr(mod, "_CHAMP", {}))
    eff.update(P)
    return eff


# ------------------------------------------------------------------ find_master lookups (the 2026-09 adjusted-masters incident)
LK_KEYS = (("NQ", "5m", "rth"), ("NQ", "5m", "eth"), ("ES", "30m", "rth"), ("ES", "5m", "rth"), ("NQ", "1m", "eth"))
LK_SRC = (None, "db_noadj_rth", "db_noadj_eth", "db_adj_rth", "db_adj_eth", "db_fadj_rth", "db_fadj_eth")


def lookups():
    """What find_master answers for the NQ / ES keys (each with no source and with every house source) + every NQ / ES master row's identity."""
    B, D, E = eng()
    ident = lambda m: None if m is None else {k: m.get(k) for k in ("id", "filename", "source", "session")}
    snap = {"lookups": {f"{i}|{t}|{s}|{src}": ident(D.find_master(i, t, s, src)) for i, t, s in LK_KEYS for src in LK_SRC},
            "inventory": sorted([m["id"], m["instrument"], m["timeframe"], m["session"], m["source"], m["filename"]]
                                for m in D.list_masters() if m["instrument"] in ("NQ", "ES"))}
    return json.loads(json.dumps(snap, default=js))                    # plain types, so a saved baseline compares equal


def lookup_diff(a, b):
    d = [k for k in sorted(set(a["lookups"]) | set(b["lookups"])) if a["lookups"].get(k) != b["lookups"].get(k)]
    return d + (["inventory of NQ / ES masters"] if a["inventory"] != b["inventory"] else [])


# ------------------------------------------------------------------ pull (keys required; the smoke test only prints the commands)
def pull_commands():
    loader = os.path.join(REPO, "tools", "import_alpaca_stocks.py")
    base = ["--start", D0, "--end", "2026-06-30T23:59:59Z", "--rth", "--adjustment", "split", "--feed", "sip"]     # end must include the 06-30 session
    return [[sys.executable, loader, "--symbols", ",".join(FUNDS), "--timeframe", tf] + base for tf in ("5Min", "30Min")]


def pull():
    sys.path.insert(0, os.path.join(REPO, "tools"))
    from import_alpaca_stocks import load_keys, fetch_bars
    key, secret = load_keys()
    if not (key and secret):
        raise SystemExit("No Alpaca keys yet - the owner saves ALPACA_API_KEY / ALPACA_SECRET_KEY (ALPACA_STAGE_R1.md).")
    B, D, E = eng()
    from augur_engine.paths import UPLOADS
    bf, now = os.path.join(OUT, "pull_lookups_before.json"), lookups()
    before = json.load(open(bf)) if os.path.exists(bf) else now       # a re-run keeps the baseline taken before the FIRST registration
    if not os.path.exists(bf):
        save("pull_lookups_before.json", before)
    if lookup_diff(before, now):
        raise SystemExit(f"STOP: find_master already differs from the baseline before any registration: {lookup_diff(before, now)}")
    for cmd in pull_commands():
        print("pull:", " ".join(cmd[1:]), flush=True)
        subprocess.run(cmd, check=True)                                # the loader logs a failed symbol and exits 0, so every master is verified below
    reg, bad = {}, []
    for f in FUNDS:
        for tf in ("5m", "30m"):
            m = D.find_master(f, tf, "rth", "alpaca_split_rth")
            if m is None or str(m["date_from"]) > "2016-01-08" or str(m["date_to"]) != "2026-06-30":
                bad.append((f, tf, None if m is None else (str(m["date_from"]), str(m["date_to"]))))
                continue
            reg[f"{f}|{tf}"] = {"filename": m["filename"], "rows": int(m["rows"]), "date_from": str(m["date_from"]), "date_to": str(m["date_to"]),
                                "sha256": sha(os.path.join(UPLOADS, m["filename"]))}
    os.makedirs(os.path.join(CACHE, "etf_daily"), exist_ok=True)       # daily bars = a research cache file per fund, never a master; frozen on first pull
    for f in FUNDS:
        p = os.path.join(CACHE, "etf_daily", f"{f}_1Day_split.csv")
        if not os.path.exists(p):
            df = fetch_bars(f, "1Day", D0 + "T00:00:00Z", "2026-06-30T23:59:59Z", key, secret, "sip", "split")
            if df.empty:
                bad.append((f, "1Day", "no bars")); continue
            d = pd.to_datetime(df["time"], unit="s", utc=True).dt.tz_convert("US/Eastern").dt.tz_localize(None).dt.normalize()
            pd.DataFrame({"date": d, "open": df["open"], "high": df["high"], "low": df["low"], "close": df["close"], "volume": df["volume"]}).to_csv(p, index=False)
        reg[f"{f}|1Day"] = {"file": p, "rows": int(len(pd.read_csv(p))), "sha256": sha(p)}
    save("pull.json", {"registered": reg, "problems": bad, "at": pd.Timestamp.now().isoformat()})
    diff = lookup_diff(before, lookups())
    if diff:
        raise SystemExit(f"STOP: find_master for NQ / ES changed after registering the funds: {diff}")
    if bad:
        raise SystemExit(f"STOP: the pull did not register / cache everything: {bad}")
    print(f"pull ok: {len(reg)} fund files; find_master for NQ / ES unchanged ({len(before['lookups'])} lookups, {len(before['inventory'])} master rows)")


# ------------------------------------------------------------------ gates (section 10)
def daily_gate(f, arr):
    """5-minute bars summed to days vs Alpaca's own split-adjusted daily bars: open and close within one cent or 0.10% (prereg addendum) on 10 random sessions."""
    p = os.path.join(CACHE, "etf_daily", f"{f}_1Day_split.csv")
    if not os.path.exists(p):
        return {"ok": False, "why": "no daily cache file - run pull", "rows": []}
    dd = pd.read_csv(p, parse_dates=["date"])
    dd = dd[dd["date"] < LB0].set_index("date")                        # cut BEFORE anything is computed
    ix = pd.DatetimeIndex(arr["index"]).tz_localize(None)
    g = pd.DataFrame({"day": ix.normalize(), "o": arr["open"], "h": arr["high"], "l": arr["low"], "c": arr["close"]}).groupby("day").agg(
        o=("o", "first"), h=("h", "max"), l=("l", "min"), c=("c", "last"))
    cand = g.index[(g.index >= WF0) & g.index.isin(dd.index)]
    k = min(RULE["ndaily"], len(cand))
    pick = cand[np.sort(np.random.default_rng(20260930 + zlib.crc32(f.encode())).choice(len(cand), size=k, replace=False))] if k else cand[:0]
    rows = [{"date": d, "d_open": float(dd.open[d]), "m_open": float(g.o[d]), "d_close": float(dd.close[d]), "m_close": float(g.c[d]),
             "open_diff": round(abs(dd.open[d] - g.o[d]), 6), "close_diff": round(abs(dd.close[d] - g.c[d]), 6),
             "high_diff": round(abs(dd.high[d] - g.h[d]), 6), "low_diff": round(abs(dd.low[d] - g.l[d]), 6)} for d in pick]
    tol = lambda px: max(RULE["cent"], RULE["rel"] * abs(px))                      # prereg ADDENDUM: one cent or 0.10%, whichever is larger
    ok = k >= RULE["ndaily"] and all(r["open_diff"] <= tol(r["d_open"]) and r["close_diff"] <= tol(r["d_close"]) for r in rows)
    return {"ok": bool(ok), "rows": rows}


def lookups_gate():
    bf = os.path.join(OUT, "pull_lookups_before.json")
    diff = lookup_diff(json.load(open(bf)), lookups()) if os.path.exists(bf) else ["no baseline on file - `pull` records find_master's answers before registering anything"]
    return {"ok": not diff, "diff": diff}


def gates():
    B, D, E = eng()
    cal_selftest()
    lk = lookups_gate()
    res = {"created": pd.Timestamp.now().isoformat(), "window": [str(WF0.date()), PRE], "lookups": lk, "funds": {}}
    print(f"gate 3 (NQ / ES lookups unchanged): {'ok' if lk['ok'] else 'FAIL ' + str(lk['diff'])}")
    for f in FUNDS:
        try:
            a5 = load(f, "5m", PRE)
        except SystemExit as e:
            res["funds"][f] = {"pass": False, "why": str(e)}; print(f"{f}: FAIL - {e}"); continue
        w, warm = bar_gate(a5, WF0, pd.Timestamp(PRE)), bar_gate(a5, pd.Timestamp(D0), WF0 - pd.Timedelta(days=1))
        dg = daily_gate(f, a5)
        ix = pd.DatetimeIndex(a5["index"]).tz_localize(None)
        on = (ix.normalize() == pd.Timestamp("2016-06-30"))
        close0 = float(a5["close"][on][-1]) if on.any() else None
        v = a5.get("volume")
        hd = half_day_info(a5)
        r = {"missing_ok": bool(w["missing_pct"] <= RULE["miss"]), "daily_ok": dg["ok"], "close_2016_06_30": close0, "WF_bars": w, "warmup_bars": warm, "daily": dg, "orb_half_day_rule": hd,
             "volume_ok": bool(v is not None and (v > 0).mean() >= 0.99), "fp5": a5["fingerprint"]}
        if "TTM" in FUNDS[f]:
            try:
                a30 = load(f, "30m", PRE)
                r["WF_bars_30m_info"], r["fp30"] = bar_gate(a30, WF0, pd.Timestamp(PRE), 30), a30["fingerprint"]
            except SystemExit as e:
                r["why30"] = str(e)
        r["pass"] = bool(r["missing_ok"] and r["daily_ok"] and close0 is not None)
        res["funds"][f] = r
        bad = [n for n, ok in (("missing bars > 1%", r["missing_ok"]), ("daily bars differ by more than a cent / 0.10%", r["daily_ok"]), ("no bar on 2016-06-30", close0 is not None)) if not ok]
        print(f"{f}: {'PASS' if r['pass'] else 'FAIL (' + '; '.join(bad) + ')'} | WF expected {w['expected']:,} missing {w['missing']:,} ({w['missing_pct']:.3%}), "
              f"sessions without bars {w['sessions_no_bars']}, extra bars {w['extra_bars']:,} (after an early close {w['extra_after_early_close']:,}) | daily rows "
              f"{sum(1 for x in dg['rows'] if x['open_diff'] <= max(RULE['cent'], RULE['rel'] * x['d_open']) and x['close_diff'] <= max(RULE['cent'], RULE['rel'] * x['d_close']))}/{len(dg['rows'])} within tolerance "
              f"(max open {max([x['open_diff'] for x in dg['rows']] or [float('nan')]):.3f}, close {max([x['close_diff'] for x in dg['rows']] or [float('nan')]):.3f}) | "
              f"warm-up missing {warm['missing_pct']:.3%} | ORB half-day rule (< {hd['threshold']:.0f} bars of a median {hd['median_bars']:.0f}) skips {hd['sessions_skipped_in_WF']} WF sessions, "
              f"{hd['early_closes_skipped']} of the {hd['early_closes_in_WF']} early closes", flush=True)
    save("gates.json", res)


# ------------------------------------------------------------------ ttmcheck (the wrapper's acceptance test, runs on local ES data)
def cmp_trades(a, b):
    same = len(a) == len(b) and all(x[0] == y[0] and x[1] == y[1] and x[3] == y[3] for x, y in zip(a, b))
    mx = max((abs(x[2] - y[2]) for x, y in zip(a, b)), default=0.0) if len(a) == len(b) else float("nan")
    return {"n": (len(a), len(b)), "same_bars_and_sides": bool(same), "max_abs_pts": mx, "bit_exact": bool(a == b)}


def ttmcheck():
    B, D, E = eng()
    leg = lambda s, src, eod: {"strategy": s, "params": {"kc_mult": 1.5, "eod_cutoff": eod}, "instrument": "ES", "timeframe": "30m", "session": "rth",
                               "source": src, "cost_pts": ES_COST, "mult": 50, "weight": 1}
    res, ok_all = {"created": pd.Timestamp.now().isoformat(), "stack_sha256": stack_shas("TTM"), "wrapper_sha256": wrapper_sha(), "combos": []}, True
    for src in ("db_noadj_rth", "db_adj_rth"):                          # the 2R / 347 files are carried on noadj; the book's TTM leg reads adj
        arr = D.load_master_arrays(D.find_master("ES", "30m", "rth", src), "2010-06-07", PRE)
        for eod in (5, 1):                                               # 5 = the pre-registered TTM cell, 1 = the book leg's setting
            L = leg("TTMSQZ_3_0_ES30SSOF2R.py", src, eod)
            ref = E.run_backtest(L["strategy"], arrays=arr, params=L["params"], cost_pts=ES_COST, return_trades=True)
            w = E.run_backtest(TTMWrap.es(IDENT), arrays=arr, params=L["params"], cost_pts=ES_COST, return_trades=True)
            c = cmp_trades(ref["trades"], w["trades"])
            net_r, net_w = ref["total_pnl"] * 50, w["total_pnl"] * 50
            tr_ref, _ = B._leg_trades(L, "2010-06-07", PRE)              # the real 2R file through book._leg_trades, dollars at $50 a point
            LW = dict(L, strategy=TTMWrap.es(IDENT))
            mine = run_leg(LW, "2010-06-07", PRE, arr)
            via_book = same_as_book(LW, "2010-06-07", PRE, arr)          # wrapper through book._leg_trades vs through run_leg
            u_ref = np.array([t[1] for t in tr_ref], float)
            cent = len(u_ref) == len(mine) and bool(np.allclose(u_ref, mine.pnl.values, rtol=0, atol=0.005)) and bool(
                (np.array([t[0] for t in tr_ref], dtype="datetime64[D]") == mine.date.values.astype("datetime64[D]")).all())
            r347 = E.run_backtest(leg("TTMSQZ_3_0_ES30SSOF2R347.py", src, eod)["strategy"], arrays=arr, params=L["params"], cost_pts=ES_COST, return_trades=True)
            c347 = cmp_trades(r347["trades"], E.run_backtest(TTMWrap.es(BOOK_LADDER), arrays=arr, params=L["params"], cost_pts=ES_COST, return_trades=True)["trades"])
            ok = bool(c["same_bars_and_sides"] and c["max_abs_pts"] * 50 < 0.005 and abs(net_r - net_w) < 0.005 and cent and via_book["ok"]
                      and c347["same_bars_and_sides"] and c347["max_abs_pts"] * 50 < 0.005)
            ok_all &= ok
            res["combos"].append({"source": src, "eod_cutoff": eod, "trades_2R": len(ref["trades"]), "net_2R_usd": net_r, "net_wrapper_usd": net_w, "vs_2R": c,
                                  "book_leg_dollars_to_the_cent": cent, "wrapper_same_via_book_leg_trades": via_book, "vs_347_with_3_4_7_ladder": c347, "ok": ok})
            print(f"ES 30m RTH {src} eod_cutoff {eod}: 2R {len(ref['trades'])} trades ${net_r:,.2f} | wrapper (ES constants, tilts, roll table) {len(w['trades'])} trades "
                  f"${net_w:,.2f} | same trades {c['same_bars_and_sides']} bit-exact {c['bit_exact']} max |d pnl| {c['max_abs_pts']:.1e} pts | "
                  f"via book._leg_trades to the cent {cent} | wrapper with the 3/4/7 ladder = the real 347 file: {c347['same_bars_and_sides']} "
                  f"(bit-exact {c347['bit_exact']}) -> {'OK' if ok else 'FAIL'}", flush=True)
    from augur_engine.strategies import load_strategy             # run_leg vs book._leg_trades on BOOK #463's real ES leg: by file name, and as an imported module object
    pk = {"by_name": same_as_book(BOOK_TTM_LEG, "2010-06-07", PRE), "as_module": same_as_book(dict(BOOK_TTM_LEG, strategy=load_strategy(BOOK_TTM_LEG["strategy"])), "2010-06-07", PRE)}
    ok_all &= all(v["ok"] for v in pk.values())
    res["run_leg_vs_book_leg_trades_real_ES_leg"] = pk
    print(f"run_leg identical to book._leg_trades on the real book TTM leg (ES30SSOF2, adj, weight 3; {pk['by_name']['n']} trades, ${pk['by_name']['net']:,.2f}): "
          f"by name {pk['by_name']['ok']}, as a module object {pk['as_module']['ok']}")
    # each of the five overrides must actually bite: flip ONE constant from its ES value to its fund value and the ES-mode result must move
    arr = D.load_master_arrays(D.find_master("ES", "30m", "rth", "db_noadj_rth"), "2010-06-07", PRE)
    run1 = lambda w: E.run_backtest(w, arrays=arr, params=TTM_P, cost_pts=ES_COST, return_trades=True)["total_pnl"] * 50
    base, flips = run1(TTMWrap.es(IDENT)), {}
    for name, w in (("deep_tilt", TTMWrap(1.0, 1.5, IDENT, ES_COST, True)), ("open_tilt", TTMWrap(1.5, 1.0, IDENT, ES_COST, True)),
                    ("ladder", TTMWrap(1.5, 1.5, UNIT_LADDER, ES_COST, True)), ("cost_const", TTMWrap(1.5, 1.5, IDENT, COST, True)),
                    ("roll_table", TTMWrap(1.5, 1.5, IDENT, ES_COST, False))):
        flips[name] = run1(w)
    bite = all(abs(v - base) > 1e-6 for v in flips.values())
    ok_all &= bite
    res["each_override_bites"] = {"es_mode_net_usd": base, "one_flip_net_usd": flips, "ok": bite}
    print(f"each override bites (ES-mode net ${base:,.0f}; one constant flipped at a time -> " + ", ".join(f"{k} ${v:,.0f}" for k, v in flips.items()) + f") -> {'OK' if bite else 'FAIL - an override is inert'}")
    # fund mode on ES arrays: must run, price every trade at exactly one unit, and carry an empty roll table (the numbers mean nothing)
    arr = D.load_master_arrays(D.find_master("ES", "30m", "rth", "db_noadj_rth"), D0, PRE)
    fw = TTMWrap.fund(COST)
    r = E.run_backtest(fw, arrays=arr, params=TTM_P, cost_pts=COST, return_trades=True)
    tr = r["trades"]
    one = all(abs(t[2] - (t[3] * (t[5] - t[4]) - COST)) < 1e-9 for t in tr)
    fund_ok = bool(len(tr) > 0 and one and fw.describe()["roll_rows"] == 0)
    ok_all &= fund_ok
    res["fund_mode_on_ES_arrays"] = {"trades": len(tr), "net_pts": r["total_pnl"], "every_trade_one_unit": one, "config": fw.describe(), "ok": fund_ok}
    print(f"fund mode (tilts 1.0, 1 unit, cost {COST}, empty roll table) on ES arrays, no error: {len(tr)} trades, net {r['total_pnl']:.2f} pts (meaningless); "
          f"every trade priced at exactly one unit {one}; config {fw.describe()} -> {'OK' if fund_ok else 'FAIL'}")
    res["pass"] = bool(ok_all)
    save("ttmcheck.json", res)
    print("ttmcheck:", "PASS - the wrapper reproduces TTMSQZ_3_0_ES30SSOF2R.py to the cent" if ok_all else "FAIL - no fund run may use this wrapper")


# ------------------------------------------------------------------ Stage A
def sess_days(*arrs):
    return pd.DatetimeIndex(sorted(set().union(*[set(pd.DatetimeIndex(a["index"]).tz_localize(None).normalize()) for a in arrs])))


def close_on(a, day):
    ix = pd.DatetimeIndex(a["index"]).tz_localize(None)
    on = ix.normalize() == pd.Timestamp(day)
    return float(a["close"][on][-1]) if on.any() else None


def leg_of(f, strat, unit, cost):
    """One cell as a BOOK leg dict (the shape book._leg_trades reads; ORB / NOISE by file name, TTM as the wrapper object)."""
    name, P, tf = STRAT[strat]
    inst, src = src_of(f, tf)
    return {"strategy": TTMWrap.fund(cost) if strat == "TTM" else name, "params": P, "instrument": inst, "timeframe": tf, "session": "rth", "source": src,
            "cost_pts": cost, "mult": unit, "weight": 1}


def run_cell(f, strat, arrs, unit, cost, d1):
    return run_leg(leg_of(f, strat, unit, cost), D0, d1, arrs[STRAT[strat][2]])


def book_corr(d):
    """Reported only: the cell's WF daily P&L vs each BOOK #463 leg's daily marks (L0 ORB, L1 ENGU-Q, L2 TTM, L3 NOISE) and the book."""
    p = os.path.join(R4, "book463_daily.csv")
    if not os.path.exists(p):
        return None
    b = pd.read_csv(p, parse_dates=["date"]).set_index("date")
    b = b[(b.index >= WF0) & (b.index < LB0)]                          # WF only: the lockbox rows never enter a Stage A number
    idx = b.index.union(d.index)
    out = {}
    for k in ("L0_mtm", "L1_mtm", "L2_mtm", "L3_mtm", "mtm"):
        x, y = d.reindex(idx).fillna(0.0), b[k].reindex(idx).fillna(0.0)
        out[k] = float(np.corrcoef(x, y)[0, 1]) if x.std() > 0 and y.std() > 0 else float("nan")
    return out


def gate_why(r):
    return r.get("why") or "; ".join(n for n, k in (("missing bars > 1%", "missing_ok"), ("daily bars off by more than a cent", "daily_ok")) if not r.get(k)) or "no bar on 2016-06-30"


def gate_state():
    gj = need_json("gates.json", "run `gates` first")
    if gj is None:
        return None
    if not gj["lookups"]["ok"]:
        print(f"refused: gate 3 failed - find_master for NQ / ES changed: {gj['lookups']['diff']}")
        return None
    return gj


def compute_cells():
    B, D, E = eng()
    gj = gate_state()
    tj = need_json("ttmcheck.json", "run `ttmcheck` first - the wrapper's acceptance must pass before any fund run")
    if gj is None or tj is None:
        return None
    if not tj["pass"] or tj["stack_sha256"] != stack_shas("TTM") or tj.get("wrapper_sha256") != wrapper_sha():
        print("refused: ttmcheck did not pass, or a TTM file or the wrapper changed since it ran - re-run `ttmcheck`")
        return None
    if os.path.exists(os.path.join(OUT, "stageB_READ.flag")):
        print("refused: the lockbox was already read - Stage A is frozen")
        return None
    keep = [f for f in FUNDS if gj["funds"].get(f, {}).get("pass")]
    drop = [f"{f} ({gate_why(gj['funds'].get(f, {}))})" for f in FUNDS if f not in keep]
    print(f"TRANSFER r2 Stage A - PRE-LOCKBOX ONLY (every load ends {PRE}); harness sha256 {sha(os.path.abspath(__file__))[:12]}, prereg sha256 (LF) {(prereg_sha() or 'n/a')[:12]}")
    print(f"funds kept by the gates: {' '.join(keep) or 'none'}; DROPPED by the gates (their cells are not run): {', '.join(drop) or 'none'}")
    eff = {s: effective(s) for s in STRAT}
    for s in STRAT:
        print(f"effective {s}: {eff[s]}")
    files = stack_shas()
    cells, funds = {}, {}
    for f in keep:
        a5 = load(f, "5m", PRE)
        if a5["fingerprint"] != gj["funds"][f]["fp5"]:
            print(f"refused: {f}'s 5-minute master changed since the gates ran - re-run `gates`"); return None
        assert_volume(a5, f)
        arrs, close0 = {"5m": a5}, close_on(a5, "2016-06-30")
        unit = int(math.floor(USD / close0))
        if "TTM" in FUNDS[f]:
            arrs["30m"] = load(f, "30m", PRE)
            if arrs["30m"]["fingerprint"] != gj["funds"][f].get("fp30"):
                print(f"refused: {f}'s 30-minute master changed since the gates ran (or was not gated) - re-run `gates`"); return None
        days = sess_days(*arrs.values())
        funds[f] = {"close_2016_06_30": close0, "unit": unit, "sessions": len(days)}
        for s in FUNDS[f]:
            t0 = time.time()
            base, st = run_cell(f, s, arrs, unit, COST, PRE), run_cell(f, s, arrs, unit, STRESS, PRE)
            assert len(base) == len(st) and (base.entry.values == st.entry.values).all() and (base.exit.values == st.exit.values).all(), "the stress cost changed the trade list"
            base["pnl_stress"] = st.pnl.values
            base["wf"] = base.date >= WF0
            base.to_csv(os.path.join(OUT, f"A_{s}_{f}_trades.csv"), index=False)
            w = stats(base, days, WF0, LB0)
            cells[f"{s}|{f}"] = {"strat": s, "fund": f, "unit": unit, "WF": w, "stress_net": float(base.pnl_stress[base.wf].sum()),
                                 "corr_book463": book_corr(daily_pnl(base[base.wf], days, WF0, LB0)), "seconds": round(time.time() - t0, 1)}
            print(f"  {s} {f}: {w['n']} WF trades, unit {unit} shares @ ${close0:.2f}", flush=True)
    return {"cells": cells, "funds": funds, "files_sha256": files, "effective": eff, "gates": {f: {k: v.get(k) for k in ("pass", "missing_ok", "daily_ok")} for f, v in gj["funds"].items()}}


def judge_save(run):
    cells = run["cells"]
    rows, passes = [], []
    for k, c in cells.items():
        chk, ok = judge_a(c, RULE)
        c["checks"], c["PASS"] = chk, ok
        w = c["WF"]
        print(f"{c['strat']:5s} {c['fund']}: WF n {w['n']} net ${w['net']:,.0f} PF {w['pf']:.2f} ROC@30k {w['roc30']:.1f} Sortino {w['sortino']:.2f} t {w['t']:.2f} "
              f"years+ {w['years_pos']:.0%} | stress ${c['stress_net']:,.0f} ex-biggest ${w['net_ex_big']:,.0f} | "
              f"{'PASS' if ok else 'fail (' + ','.join(n for n, v in chk.items() if not v) + ')'}")
        rows.append({"cell": k, **{n: w[n] for n in ("n", "net", "pf", "dd_daily", "roc30", "sortino", "t", "years_pos", "net_ex_big")},
                     "stress_net": c["stress_net"], "PASS": ok})
        if ok:
            passes.append(k)
    st = stouffer(cells)
    for s, v in st.items():
        print(f"Stouffer Z {s}: {v['Z']:.2f} over {v['k']} funds (one-sided p {v['p_one_sided']:.3f}; reported only, never a pass route)")
    for k, c in cells.items():
        if c["corr_book463"]:
            print(f"  corr with BOOK #463 legs (WF daily) {k}: " + " ".join(f"{n} {v:+.2f}" for n, v in c["corr_book463"].items()))
    pd.DataFrame(rows).to_csv(os.path.join(OUT, "stageA_table.csv"), index=False)
    out = {"prereg": "PREREG_TRANSFER_R2.txt @854955a0", "prereg_sha256_lf": prereg_sha(), "harness_sha256": sha(os.path.abspath(__file__)), "rules": RULE,
           "window": {"WF": [str(WF0.date()), PRE], "date_to": PRE}, "params": {"ORB": ORB_P, "NOISE": NOISE_P, "TTM": TTM_P}, "effective": run["effective"], "costs": {"base": COST, "stress": STRESS},
           "files_sha256": run["files_sha256"], "gates": run["gates"], "funds": run["funds"], "cells": cells, "stouffer": st, "passes": passes}
    save("stageA.json", out)
    print("Stage A passes: " + (", ".join(passes) if passes else "none - TRANSFER r2 DEAD; ledger + memory, the lockbox stays sealed, stop"))


def prereg_sha():
    p = os.path.join(HERE, "PREREG_TRANSFER_R2.txt")
    return hashlib.sha256(open(p, "rb").read().replace(b"\r\n", b"\n")).hexdigest() if os.path.exists(p) else None


def stage_a():
    run = compute_cells()
    if run:
        judge_save(run)


# ------------------------------------------------------------------ Stage B (lockbox, once) and Stage C (book add)
def stage_b(*a):
    sa = need_json("stageA.json", "run `A` first")
    if sa is None or not sa["passes"]:
        print("Stage B refused: no Stage A pass on file - the lockbox stays sealed.")
        return
    if a != ("--ledger-ok",):                                          # prereg section 4: the LB is read once, AFTER Stage A is in the ledger
        print("Stage B refused: the pre-registration reads the lockbox only after Stage A is in the ledger - record it, then run `B --ledger-ok`.")
        return
    flag = os.path.join(OUT, "stageB_READ.flag")
    assert not os.path.exists(flag), "Stage B was already read once"
    open(flag, "w").write(pd.Timestamp.now().isoformat())
    B, D, E = eng()
    res = {}
    print(f"Stage B - the lockbox {LB0.date()} .. {LB1.date()} inclusive, read ONCE for: {', '.join(sa['passes'])}")
    for k in sa["passes"]:
        s, f = k.split("|")
        arrs = {"5m": load(f, "5m", "2026-06-30")}
        if s == "TTM":
            arrs["30m"] = load(f, "30m", "2026-06-30")
        unit = sa["funds"][f]["unit"]
        df = run_cell(f, s, arrs, unit, COST, "2026-06-30")
        days = sess_days(*arrs.values())
        a = pd.read_csv(os.path.join(OUT, f"A_{s}_{f}_trades.csv"), parse_dates=["date"])
        wf = df[df.date < LB0]
        same = len(wf) == len(a) and bool(np.allclose(wf.pnl.values, a.pnl.values, rtol=0, atol=1e-6))
        lb = df[(df.date >= LB0) & (df.date < LBX)]
        r = stats(df, days, LB0, LBX, yrs=LBY)
        chk, ok = judge_b(r, s, RULE)
        lb.to_csv(os.path.join(OUT, f"B_{s}_{f}_trades_LB.csv"), index=False)
        res[k] = {"LB": r, "checks": chk, "PASS": ok, "wf_part_identical_to_stageA": same}
        print(f"  {s} {f}: LB n {r['n']} net ${r['net']:,.0f} PF {r['pf']:.2f} ROC@30k {r['roc30']:.1f} Sortino {r['sortino']:.2f} ex-biggest ${r['net_ex_big']:,.0f} | "
              f"warm-up trades before the LB identical to Stage A: {same} | {'PASS' if ok else 'fail (' + ','.join(n for n, v in chk.items() if not v) + ')'}")
    surv = [k for k, v in res.items() if v["PASS"]]
    save("stageB.json", {"cells": res, "survivors": surv, "harness_sha256": sha(os.path.abspath(__file__))})
    print("Stage B survivors: " + (", ".join(surv) if surv else "none"))
    if surv:
        print("Section 9 (runner job, not run here): ONE Auto-Validate per survivor at the 900-trial budget on its fund master, this window and lockbox; evidence only.")


def stage_c():
    sb = need_json("stageB.json", "run `B` first")
    if sb is None or not sb["survivors"]:
        print("Stage C refused: no Stage B survivor on file.")
        return
    bwf, blb = book(None, WF0, LB0), book(None, LB0, LBX, yrs=LBY)
    print(f"BOOK #463: WF ROC@30k {bwf['roc30']:.2f} Sortino {bwf['sortino']:.3f} | LB ROC@30k {blb['roc30']:.2f} Sortino {blb['sortino']:.3f} (prereg: 92.70 / 3.816 | 164.76 / 4.150)")
    if CHECK_BOOK:
        assert (round(bwf["roc30"], 2), round(bwf["sortino"], 3), round(blb["roc30"], 2), round(blb["sortino"], 3)) == (92.70, 3.816, 164.76, 4.150), \
            "book463_daily.csv no longer reproduces the pre-registered #463 numbers - stop"
    bt = pd.read_csv(os.path.join(R4, "book463_trades.csv"), parse_dates=["date"])
    bmax = float(bt[(bt.date >= LB0) & (bt.date < LBX)]["pnl"].max())
    legs, big = {}, {}
    for k in sb["survivors"]:
        s, f = k.split("|")
        a = pd.read_csv(os.path.join(OUT, f"A_{s}_{f}_trades.csv"), parse_dates=["date"])
        a = a[(a.date >= WF0) & (a.date < LB0)]
        b = pd.read_csv(os.path.join(OUT, f"B_{s}_{f}_trades_LB.csv"), parse_dates=["date"])
        legs[k] = pd.concat([a, b]).groupby("date")["pnl"].sum()       # ONE unit, weight 1.0: no size or weight search
        big[k] = float(b.pnl.max()) if len(b) else 0.0
    books = {k: [k] for k in legs}
    if len(legs) > 1:
        books["ALL"] = list(legs)
    out = {}
    for name, ks in books.items():
        extra = pd.concat([legs[k] for k in ks], axis=1).fillna(0.0).sum(axis=1)
        wf, lb = book(extra, WF0, LB0), book(extra, LB0, LBX, yrs=LBY)
        chk, ok = judge_c(wf, lb, bwf, blb, max([bmax] + [big[k] for k in ks]))
        out[name] = {"legs": ks, "WF": wf, "LB": lb, "checks": chk, "PASS": ok}
        print(f"  #463 + {name}: WF ROC@30k {wf['roc30']:.2f} Sortino {wf['sortino']:.3f} | LB ROC@30k {lb['roc30']:.2f} Sortino {lb['sortino']:.3f} | "
              f"{'PASS' if ok else 'fail (' + ','.join(n for n, v in chk.items() if not v) + ')'}")
    save("stageC.json", {"base": {"WF": bwf, "LB": blb}, "books": out, "passes": [n for n, v in out.items() if v["PASS"]]})
    print("Stage C: " + ("a pass goes to MANAGER for the owner's call (a Webull paper shadow is the natural next step); nothing is adopted here."
                         if any(v["PASS"] for v in out.values()) else "no book beats #463 - TRANSFER r2 closes for the ETF route"))


# ------------------------------------------------------------------ smoke (offline; stand-in funds)
def selftest():
    cal_selftest()
    t = pd.DataFrame({"date": pd.to_datetime(["2016-07-05", "2016-07-06", "2016-07-07", "2016-07-08"]), "pnl": [10.0, -5.0, 20.0, -10.0]})
    days = pd.DatetimeIndex(list(t.date) + [pd.Timestamp("2016-07-11")])
    s = stats(t, days, pd.Timestamp("2016-07-01"), pd.Timestamp("2016-08-01"))
    yrs = 31 / 365.25
    assert s["n"] == 4 and abs(s["net"] - 15) < 1e-9 and abs(s["pf"] - 2.0) < 1e-9 and abs(s["dd_daily"] - 10) < 1e-9 and s["days"] == 5
    assert abs(s["roc30"] - 30 * (15 / yrs) / 10) < 1e-9 and abs(s["sortino"] - 3 / 5 * np.sqrt(252)) < 1e-9 and abs(s["t"] - 3 / (np.sqrt(145) / np.sqrt(5))) < 1e-9
    assert s["years_pos"] == 1.0 and abs(s["net_ex_big"] - (-5)) < 1e-9
    assert stouffer({"a": {"strat": "ORB", "WF": {"t": 2.0}}, "b": {"strat": "ORB", "WF": {"t": 4.0}}})["ORB"]["Z"] == 6 / math.sqrt(2)
    print("selftest ok: NYSE calendar (2,260 sessions, early closes, observed holidays), stats / Sortino / t / Stouffer on a hand-made example")


def smoke(*a):
    global OUT, CACHE, R4, FMAP, FUNDS, CHECK_BOOK, judge_a, judge_b
    import shutil, tempfile
    root = os.path.abspath(a[0] if a else os.path.join(tempfile.gettempdir(), "r8_smoke"))
    assert "smoke" in os.path.basename(root).lower() and not root.lower().startswith(r"c:\edgelog"), "smoke needs its own scratch folder (name contains 'smoke'), never a real cache"
    keep = (OUT, CACHE, R4, FMAP, FUNDS, CHECK_BOOK, judge_a, judge_b)
    B, D, E = eng()
    try:
        OUT, CACHE, R4 = (os.path.join(root, x) for x in ("out", "cache", "r4"))
        for p in (OUT, CACHE, R4):
            shutil.rmtree(p, ignore_errors=True); os.makedirs(p)
        print("=" * 110 + "\nSMOKE TEST - stand-in funds cut from the local ES / NQ masters: every number below is MEANINGLESS, only the code paths matter\n" + "=" * 110)
        selftest()
        FUNDS = {"FUND1": ("ORB", "NOISE", "TTM"), "FUND2": ("ORB", "NOISE", "TTM"), "FUND3": ("ORB",)}
        FMAP = {"FUND1": {tf: ("ES", "db_noadj_rth") for tf in ("5m", "30m")}, "FUND2": {tf: ("NQ", "db_noadj_rth") for tf in ("5m", "30m")},
                "FUND3": {tf: ("ES", "db_adj_rth") for tf in ("5m", "30m")}}      # FUND3 gets a doctored daily file: it must fail the gates and be dropped
        print("pull is never run here; its command lines would be:")
        for c in pull_commands():
            print("  " + " ".join(c[1:]))
        os.makedirs(os.path.join(CACHE, "etf_daily"))
        for f in FMAP:                                                   # synthetic daily bars from the 5-minute stand-ins, through 2026-06-30 (the gate must cut at the lockbox)
            a5 = load(f, "5m", "2026-06-30")
            ix = pd.DatetimeIndex(a5["index"]).tz_localize(None)
            g = pd.DataFrame({"date": ix.normalize(), "open": a5["open"], "high": a5["high"], "low": a5["low"], "close": a5["close"], "volume": a5["volume"]}).groupby("date").agg(
                open=("open", "first"), high=("high", "max"), low=("low", "min"), close=("close", "last"), volume=("volume", "sum")).reset_index()
            g["open"] += 0.004; g["close"] -= 0.004                                          # inside a cent
            if f == "FUND3":
                g["close"] *= 1.01                                                           # off by 1% on every session (a wrong adjustment)
            g.to_csv(os.path.join(CACHE, "etf_daily", f"{f}_1Day_split.csv"), index=False)
        base = lookups()
        save("pull_lookups_before.json", base)
        bad = json.loads(json.dumps(base)); k0 = next(k for k, v in bad["lookups"].items() if v)
        bad["lookups"][k0]["id"] = -1
        assert lookup_diff(base, bad) == [k0] and not lookup_diff(base, lookups()), "lookup comparison"
        assert lookups_gate()["ok"]
        bp = os.path.join(OUT, "pull_lookups_before.json"); json.dump(bad, open(bp, "w"))
        assert not lookups_gate()["ok"] and lookups_gate()["diff"] == [k0], "a tampered baseline must fail gate 3"
        os.remove(bp)
        assert not lookups_gate()["ok"], "no baseline must fail gate 3"
        save("pull_lookups_before.json", base)
        print("lookups: baseline saved; a tampered baseline and a missing baseline both fail gate 3, the live registry matches")
        gates()
        gj = json.load(open(os.path.join(OUT, "gates.json")))
        assert gj["lookups"]["ok"] and not gj["funds"]["FUND3"]["pass"], "FUND3's doctored daily bars must fail the gates"
        for f in ("FUND1", "FUND2"):
            if not gj["funds"][f]["pass"]:
                print(f"smoke: {f} failed the real gates on its stand-in data; forcing it through so Stage A has cells to run"); gj["funds"][f]["pass"] = True
        save("gates.json", gj)
        ttmcheck()
        assert json.load(open(os.path.join(OUT, "ttmcheck.json")))["pass"], "ttmcheck must pass on the real ES data"
        rng = np.random.default_rng(5)                                   # synthetic BOOK #463 files (the real ones are never read)
        bd = pd.bdate_range("2010-06-07", "2026-06-30")
        cols = {}
        for i in range(4):
            c = rng.normal(10, 300, len(bd)); cols[f"L{i}_close"] = c; cols[f"L{i}_mtm"] = c + rng.normal(0, 50, len(bd))
        df = pd.DataFrame(cols, index=bd); df["close"] = df[[c for c in df if c.endswith("_close")]].sum(axis=1); df["mtm"] = df[[c for c in df if c.endswith("_mtm")]].sum(axis=1)
        df.index.name = "date"; df.to_csv(os.path.join(R4, "book463_daily.csv"))
        k = rng.random(len(bd)) < 0.3
        pd.DataFrame({"date": bd[k], "pnl": df["close"].values[k], "strategy": "FAKE"}).to_csv(os.path.join(R4, "book463_trades.csv"), index=False)
        CHECK_BOOK = False
        stage_b("--ledger-ok"); stage_c()                                # nothing on file yet: both must refuse
        for what, name, edit in (("ttmcheck not passed", "ttmcheck.json", lambda j: j.update({"pass": False})),
                                 ("a TTM file changed since ttmcheck", "ttmcheck.json", lambda j: j.update(stack_sha256={"x": "0"})),
                                 ("the wrapper changed since ttmcheck", "ttmcheck.json", lambda j: j.update(wrapper_sha256="0")),
                                 ("gate 3 failed", "gates.json", lambda j: j["lookups"].update(ok=False, diff=["tampered"]))):
            p = os.path.join(OUT, name); orig = json.load(open(p)); j = json.loads(json.dumps(orig)); edit(j); json.dump(j, open(p, "w"))
            assert compute_cells() is None, f"Stage A must refuse when {what}"
            json.dump(orig, open(p, "w"))
        a5 = load("FUND1", "5m", PRE); u1 = int(math.floor(USD / close_on(a5, "2016-06-30")))
        for s in FUNDS["FUND1"]:                                         # the mirror (run_leg) must equal book._leg_trades leg by leg: ORB / NOISE by name, TTM as the wrapper object
            r = same_as_book(leg_of("FUND1", s, u1, COST), D0, PRE)
            assert r["ok"], f"run_leg differs from book._leg_trades on the {s} leg"
            print(f"run_leg identical to book._leg_trades on the {s} leg of FUND1 (stand-in for a fund): {r['n']} trades, ${r['net']:,.2f}")
        run = compute_cells()
        assert run and set(run["funds"]) == {"FUND1", "FUND2"} and len(run["cells"]) == 6, "Stage A must run 3 strategies on each of the two surviving stand-ins"
        print("--- Stage A judged by the pre-registered rules:")
        judge_save(run)
        print("--- Stage A judged with every rule waived, so Stage B and C have cells to run end to end (smoke only):")
        judge_a = lambda c, rule: ({"waived": True}, True)
        judge_save(run)
        judge_b = lambda lb, strat, rule: ({"waived": True}, True)
        stage_b()                                                        # Stage A is on file but nobody attested the ledger: must refuse, no flag file
        assert not os.path.exists(os.path.join(OUT, "stageB_READ.flag")), "B without --ledger-ok must not touch the lockbox"
        stage_b("--ledger-ok")
        try:
            stage_b("--ledger-ok"); raise AssertionError("a second lockbox read must be refused")
        except AssertionError as e:
            assert "already read" in str(e)
        print("a second Stage B read is refused (flag file); Stage C on the survivors:")
        stage_c()
        print("=" * 110 + "\nSMOKE DONE - synthetic book, stand-in funds, waived rules: nothing above says anything about the ETFs or about BOOK #463\n" + "=" * 110)
    finally:
        OUT, CACHE, R4, FMAP, FUNDS, CHECK_BOOK, judge_a, judge_b = keep


CMDS = {"pull": pull, "gates": gates, "ttmcheck": ttmcheck, "A": stage_a, "B": stage_b, "C": stage_c, "smoke": smoke}

if __name__ == "__main__":
    a = sys.argv[1:]
    if a and a[0] in CMDS:
        if a[0] != "smoke":
            os.makedirs(OUT, exist_ok=True)
        CMDS[a[0]](*a[1:])
    else:
        print("usage: r8_transfer_etf.py pull | gates | ttmcheck | A | B --ledger-ok | C | smoke [DIR]   (pull needs the owner's Alpaca keys; A needs gates + ttmcheck first)")
