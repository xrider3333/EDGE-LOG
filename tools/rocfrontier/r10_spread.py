# Round 10 (2026-10-02): SPREAD r2 - NQ vs ES first-hour relative strength, beta-neutral, held 10:30 -> 15:55 (CONTINUATION; the reversal mirror is the control).
# Pre-registered: tools/rocfrontier/PREREG_SPREAD_R2.txt (commit 18a9bae2; sha256 of its LF text bf588e8e...1954), written before any spread return was
# computed. Every rule, threshold and window below is that file or its task brief; where they are silent the choice is marked CHOICE.
# NEW ROC convention (house, 2026-10-01, BOOK.md 10r): valued-daily net and drawdown inside each stretch, years = (last - first).days / 365.25 - NOT r9's.
#   python r10_spread.py count        outcome-free: eligible sessions per stretch and how many the roll guard dropped (no signal, no P&L is computed)
#   python r10_spread.py A            Stage A (+ A2 if a cell passes), PRE-LOCKBOX ONLY (every array is cut to bars before 2025-06-30 before anything is computed)
#   python r10_spread.py B            Stage B (book lockbox, once) - refuses unless A2 passed; the READ flag is written only after the lockbox data has loaded,
#                                     the frozen cell's trades are computed and #463's own LB numbers reproduce
#   python r10_spread.py smoke DIR    offline self-test on SYNTHETIC masters + a synthetic book (DIR's name must contain 'smoke'); its numbers mean nothing
# Stage C of the prereg (the house Auto-Validate strategy file) is NOT in this harness. Results go to OUT (outside git); nothing here commits, pushes or writes elsewhere.
import contextlib, hashlib, io, json, math, os, re, shutil, sys, tempfile
from functools import reduce
REPO = os.environ.get("EDGELOG_ROOT", r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"); sys.path.insert(0, REPO)
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.environ.get("EDGELOG_ROCFRONTIER_R10", r"C:\EdgeLog\_anatomy_cache\rocfrontier\r10")   # results stay outside git
BOOK = os.path.join(os.path.dirname(OUT), "r4", "book463_daily.csv")       # + book463_trades.csv next to it
PREREG = os.path.join(HERE, "PREREG_SPREAD_R2.txt")
PREREG_SHA = "bf588e8e22e6c21d0ebf54ccd4fd4080e012e249d8a42433b897c25b2b281954"   # canonical (LF) sha256 of the pre-registration as committed (18a9bae2)
TS = pd.Timestamp
WF0, LB0, LB1, LBX = (TS(x) for x in ("2016-07-01", "2025-06-30", "2026-06-30", "2026-07-01"))   # WF = [WF0, LB0); LB = [LB0, LB1] INCLUSIVE; LBX = the exclusive load cut
A_D0, B_D0 = "2010-06-01", "2024-10-01"                                    # first load date: Stage A / Stage B (60 + 60 sessions of look-back are enough from 2024-10-01)
SRC_RAW, SRC_ADJ = "db_noadj_rth", "db_adj_rth"
IDS = {("NQ", SRC_RAW): 37, ("ES", SRC_RAW): 33, ("NQ", SRC_ADJ): 73, ("ES", SRC_ADJ): 63}   # registry ids named in the prereg
NB, B_FIRST, B_LAST = 78, 570, 955          # 78 five-minute bars 09:30..15:55, minute of day on the ET clock, bar START stamps
I_SIG, I_ENT, I_EXIT = 11, 12, 76           # signal bar = 10:25 (closes 10:30); entry = open of the 10:30 bar; exit = close of the 15:50 bar (= 15:55)
NQ_X, ES_X = 20.0, 50.0                      # $ per point
NQ_PTS, ES_PTS, STRESS = 0.533, 0.363, 0.25  # round-trip cost in points (house rule); stress = +0.25 pt per contract per market
GUARD_TOL = 1e-6                             # roll guard: (adj - raw) may not move by more than this inside a session
KS, LOOK, MINLOOK, NREP, SEED = (0, 1, 2), 60, 40, 500, 20261002
BOOK_WF, BOOK_LB, TOL = (93.81, 3.816), (155.54, 4.150), (0.006, 0.0006)   # #463's reference ROC@30k / Sortino on the NEW convention (WF, LB) and the match tolerance
BOOK_COLS = ("L0_mtm", "L1_mtm", "L2_mtm", "L3_mtm", "mtm")
RULES = {"n": 100, "roc30": 15.0, "pf": 1.10, "t": 2.0, "years_pos": 0.60,              # Stage A a, b, c, d (also t > the null p95), g
         "a2_roc": 98.50, "a2_sort": BOOK_WF[1], "b_roc": BOOK_LB[0], "b_sort": BOOK_LB[1], "b_n": 50}   # A2 (1.05 x 93.81, 3.816); Stage B (the book's own LB, 50 LB trades)
RULE_TEXT = {"a_n": "WF trades >= 100", "b_roc": "WF ROC at $30k drawdown >= 15 %/yr", "c_pf": "WF profit factor >= 1.10",
             "d_t": "WF per-trade t >= 2.0 AND above the null max-t 95th percentile", "e_stress": "WF net > 0 at the stress cost (+0.25 pt per contract per market)",
             "f_exbig": "WF net without its single biggest trade > 0", "g_years": "positive in >= 60% of the WF calendar years", "h_early": "EARLY net > 0"}
CHECK_BOOK = True       # a real run ALWAYS checks that the book file reproduces #463's numbers; only smoke() can switch it (its synthetic book cannot)


def js(o):
    if isinstance(o, np.bool_): return bool(o)
    if isinstance(o, np.integer): return int(o)
    if isinstance(o, np.floating): return float(o)
    if isinstance(o, np.ndarray): return o.tolist()
    if isinstance(o, pd.Timestamp): return str(o)[:10]
    return str(o)


def rd(path, mode="r"):
    with open(path, mode) as f:
        return f.read()


def wr(path, data, mode="w"):
    with open(path, mode) as f:
        f.write(data)


def save(name, obj):
    wr(os.path.join(OUT, name), json.dumps(obj, indent=1, default=js))


def sha_lf(path):
    """sha256 of a text file with CRLF -> LF (the prereg's canonical hash)"""
    return hashlib.sha256(rd(path, "rb").replace(b"\r\n", b"\n")).hexdigest()


def sha_raw(path):
    return hashlib.sha256(rd(path, "rb")).hexdigest()


def nz(x):
    return -np.inf if x != x else x


# ------------------------------------------------------------------ data: the four masters, cut at the lockbox BEFORE anything is computed
def data_mod():
    from augur_engine import data
    return data


def load(t_end, d0=A_D0):
    """The four 5-minute RTH masters (NQ / ES x raw / roll-corrected), every array cut to bars BEFORE t_end (midnight US/Eastern) and asserted so before anything is
    computed. Returns {(inst, 'raw'|'adj'): (DataFrame[open, close] on the tz-aware bar-START index, master row)}."""
    data = data_mod()
    t_end = TS(t_end)
    cut = t_end.tz_localize("US/Eastern")
    d1 = str((t_end - pd.Timedelta(days=1)).date())
    L = {}
    for inst in ("NQ", "ES"):
        for tag, src in (("raw", SRC_RAW), ("adj", SRC_ADJ)):
            m = data.find_master(inst, "5m", "rth", src)
            assert m is not None and m.get("source") == src, f"no {src} 5m RTH master for {inst}"
            assert int(m["id"]) == IDS[(inst, src)], f"{inst} {src}: registry id {m['id']}, the pre-registration names {IDS[(inst, src)]}"     # CHOICE: the named ids are enforced
            a = data.load_master_arrays(m, d0, d1)
            ix = pd.DatetimeIndex(a["index"])
            keep = np.asarray(ix < cut)
            df = pd.DataFrame({k: np.asarray(a[k], float)[keep] for k in ("open", "close")}, index=ix[keep])
            assert len(df) and df.index.max() < cut, f"{inst} {src}: the cut failed"
            L[(inst, tag)] = (df, m)
    return L


def grid(df):
    """One master -> (days, O, C, ok): per calendar day a 78-slot matrix of the 09:30..15:55 bar opens / closes; ok = exactly one bar in every slot, no other bar
    inside the window, every price finite. CHOICE: a duplicated timestamp or an off-grid bar inside the window makes the day not-ok (the prereg says 'all 78 bars')."""
    ix = df.index
    hm = ix.hour.to_numpy() * 60 + ix.minute.to_numpy()
    day = ix.tz_localize(None).normalize().to_numpy()
    w = (hm >= B_FIRST) & (hm <= B_LAST)
    hm, day = hm[w], day[w]
    o, c = df["open"].to_numpy(float)[w], df["close"].to_numpy(float)[w]
    days, di = np.unique(day, return_inverse=True)
    on = ((hm - B_FIRST) % 5) == 0
    slot = (hm - B_FIRST) // 5
    cnt = np.zeros((len(days), NB), int)
    np.add.at(cnt, (di[on], slot[on]), 1)
    extra = np.bincount(di[~on], minlength=len(days))
    O, C = np.full((len(days), NB), np.nan), np.full((len(days), NB), np.nan)
    O[di[on], slot[on]] = o[on]
    C[di[on], slot[on]] = c[on]
    ok = (cnt == 1).all(axis=1) & (extra == 0) & np.isfinite(O).all(axis=1) & np.isfinite(C).all(axis=1)
    return days, O, C, ok


def build_sessions(L):
    """Eligible sessions: all 78 bars on all four masters AND the roll guard - on each market (adj - raw) constant inside the session (max - min <= 1e-6) for the
    opens and for the closes. CHOICE: four separate checks (NQ open, NQ close, ES open, ES close); the open and close constants are not required to agree.
    Arrays are the RAW (contract) prices, shape (S, 78), in date order."""
    G = {key: grid(df) for key, (df, m) in L.items()}
    any_days = reduce(np.union1d, [g[0] for g in G.values()])
    common = reduce(np.intersect1d, [g[0][g[3]] for g in G.values()])
    row = {key: np.searchsorted(g[0], common) for key, g in G.items()}
    guard = np.ones(len(common), bool)
    for inst in ("NQ", "ES"):
        for j in (1, 2):                                                       # 1 = opens, 2 = closes
            d = G[(inst, "adj")][j][row[(inst, "adj")]] - G[(inst, "raw")][j][row[(inst, "raw")]]
            guard &= (d.max(axis=1) - d.min(axis=1)) <= GUARD_TOL
    pick = lambda inst, j: G[(inst, "raw")][j][row[(inst, "raw")]][guard]
    return {"dates": pd.DatetimeIndex(common[guard]), "oN": pick("NQ", 1), "cN": pick("NQ", 2), "oE": pick("ES", 1), "cE": pick("ES", 2),
            "n_any": len(any_days), "n_complete": len(common), "n_guard": int((~guard).sum()), "guard_dates": pd.DatetimeIndex(common[~guard])}


# ------------------------------------------------------------------ the signal (strictly causal: session i uses sessions < i for beta and scale)
def rnd1(x):
    """CHOICE: Python's round(x, 1) on the float (half-even on the decimal repr); the same function in the harness and in smoke's brute-force check"""
    return round(float(x), 1)


def hedge(beta, c_nq, c_es):
    """h = beta x (NQ price x 20) / (ES price x 50) at the 10:25 closes, rounded to 0.1 contract, at least 0.1"""
    return max(0.1, rnd1(beta * (c_nq * NQ_X) / (c_es * ES_X)))


def signal(oN, cN, oE, cE):
    """Every per-session quantity, as arrays of length S (NaN where undefined). beta_i = OLS slope (with intercept) of NQ on ES 5-minute returns pooled over the previous
    60 ELIGIBLE sessions (>= 40 else undefined; CHOICE: the window counts eligible sessions, not calendar days); s_i = rN1 - beta_i x rE1; scale_i = median |s| over
    the previous 60 eligible sessions that have a defined s (>= 40 else undefined; CHOICE: an undefined scale means no trade for EVERY k, k = 0 included)."""
    S = len(cN)
    nan = np.full(S, np.nan)
    assert all((a > 0).all() and np.isfinite(a).all() for a in (oN, cN, oE, cE)), "a non-positive or non-finite price in an eligible session"
    rN = cN[:, 1:] / cN[:, :-1] - 1.0                                         # the 77 intra-session returns (no overnight)
    rE = cE[:, 1:] / cE[:, :-1] - 1.0
    beta = nan.copy()
    for i in range(MINLOOK, S):
        lo = max(0, i - LOOK)
        x, y = rE[lo:i].ravel(), rN[lo:i].ravel()
        xd, yd = x - x.mean(), y - y.mean()
        v = float((xd * xd).sum())
        if v > 0:
            beta[i] = float((xd * yd).sum()) / v
    rN1 = cN[:, I_SIG] / oN[:, 0] - 1.0
    rE1 = cE[:, I_SIG] / oE[:, 0] - 1.0
    s = rN1 - beta * rE1
    a_s = np.abs(s)
    scale = nan.copy()
    for i in range(S):
        w = a_s[max(0, i - LOOK):i]
        w = w[np.isfinite(w)]
        if len(w) >= MINLOOK:
            scale[i] = float(np.median(w))
    h = nan.copy()
    for i in np.flatnonzero(np.isfinite(beta)):
        h[i] = hedge(beta[i], cN[i, I_SIG], cE[i, I_SIG])
    gross_plus = NQ_X * (cN[:, I_EXIT] - oN[:, I_ENT]) - ES_X * h * (cE[:, I_EXIT] - oE[:, I_ENT])      # long 1 NQ, short h ES, $
    cost = NQ_PTS * NQ_X + h * ES_PTS * ES_X
    add = STRESS * NQ_X + h * STRESS * ES_X
    ok = np.isfinite(beta) & np.isfinite(s) & np.isfinite(scale) & np.isfinite(h)
    return {"beta": beta, "s": s, "scale": scale, "h": h, "gross_plus": gross_plus, "cost": cost, "add": add, "ok": ok,
            "es_move": ES_X * (cE[:, I_EXIT] - oE[:, I_ENT])}


def trade_mask(sig, k):
    with np.errstate(invalid="ignore"):
        return sig["ok"] & (sig["s"] != 0) & (np.abs(sig["s"]) >= k * sig["scale"])


def cell_trades(S, sig, k, mirror=False):
    """One cell's trades: a trade day iff the signal chain is defined, s != 0 and |s| >= k x scale. CONT side = sign(s); mirror (REV, the control) = -sign(s)."""
    ix = np.flatnonzero(trade_mask(sig, k))
    side = np.sign(sig["s"][ix])
    if mirror:
        side = -side
    pnl = side * sig["gross_plus"][ix] - sig["cost"][ix]
    return pd.DataFrame({"date": S["dates"][ix], "i": ix, "side": side, "s": sig["s"][ix], "beta": sig["beta"][ix], "h": sig["h"][ix], "scale": sig["scale"][ix],
                         "gross_plus": sig["gross_plus"][ix], "cost": sig["cost"][ix], "pnl": pnl, "pnl_stress": pnl - sig["add"][ix], "es_move": sig["es_move"][ix]})


# ------------------------------------------------------------------ stats (house convention 2026-10-01)
def ddmax(x):
    q = np.cumsum(np.asarray(x, float))
    return float((np.maximum.accumulate(np.concatenate([[0.0], q]))[1:] - q).max()) if len(q) else 0.0      # the peak starts at 0


def so(x):
    x = np.asarray(x, float)
    dn = np.sqrt(np.mean(np.minimum(x, 0.0) ** 2)) if len(x) else 0.0
    return float(x.mean() / dn * np.sqrt(252)) if dn > 0 else float("nan")


def corr(a, b):
    a, b = np.asarray(a, float), np.asarray(b, float)
    if len(a) < 3 or len(a) != len(b) or a.std() == 0 or b.std() == 0:
        return float("nan")
    return float(np.corrcoef(a, b)[0, 1])


def stats(tr, days, t0, t1):
    """One cell on the stretch [t0, t1). daily = EVERY eligible session in the stretch (zeros where no trade); years = (last session - first session).days / 365.25.
    CHOICE: no loss at all -> pf = inf; the sessions before the first possible trade stay in the daily series (zeros) and in years."""
    d = days[(days >= t0) & (days < t1)]
    t = tr[(tr["date"] >= t0) & (tr["date"] < t1)]
    daily = t.groupby("date")["pnl"].sum().reindex(d).fillna(0.0)
    x, p = daily.to_numpy(float), t["pnl"].to_numpy(float)
    n, net, ddv = len(p), float(x.sum()), ddmax(x)
    yrs = (d[-1] - d[0]).days / 365.25 if len(d) > 1 else float("nan")
    gw, gl = float(p[p > 0].sum()), float(-p[p < 0].sum())
    sd = float(p.std(ddof=1)) if n > 1 else float("nan")
    by = daily.groupby(daily.index.year).sum()                                  # every calendar year with eligible sessions in the stretch, partial years included
    return {"days": len(d), "first": d[0] if len(d) else None, "last": d[-1] if len(d) else None, "n": n, "net": net,
            "per_trade": net / n if n else float("nan"), "win": float((p > 0).mean()) if n else float("nan"),
            "pf": gw / gl if gl > 0 else (float("inf") if gw > 0 else float("nan")), "dd_daily": ddv, "years": yrs,
            "roc30": 30.0 * (net / yrs) / ddv if ddv > 0 and yrs > 0 else float("nan"), "sortino": so(x),
            "t": float(p.mean() / (sd / np.sqrt(n))) if n > 1 and sd > 0 else float("nan"),
            "years_pos": float((by > 0).mean()) if len(by) else 0.0, "net_ex_big": net - float(p.max()) if n else float("nan"),
            "stress_net": float(t["pnl_stress"].sum()) if "pnl_stress" in t else float("nan")}


def null_dist(S, sig):
    """Family-wide null: per rep ONE fair coin (+1 / -1) per eligible session, shared by the three k cells; pnl = coin x gross_plus - cost on each cell's unchanged trade
    days; statistic = the MAX over the 3 cells of the WF per-trade t. CHOICE: each rep is one rng.choice([-1.0, 1.0], size = ALL eligible sessions loaded) draw."""
    days = S["dates"]
    wf = (days >= WF0) & (days < LB0)
    masks = [wf & trade_mask(sig, k) for k in KS]
    rng = np.random.default_rng(SEED)
    out = np.full(NREP, np.nan)
    for r in range(NREP):
        pnl = rng.choice([-1.0, 1.0], size=len(days)) * sig["gross_plus"] - sig["cost"]
        best = -np.inf
        for m in masks:
            x = pnl[m]
            if len(x) > 1 and x.std(ddof=1) > 0:
                best = max(best, float(x.mean() / (x.std(ddof=1) / np.sqrt(len(x)))))
        out[r] = best if np.isfinite(best) else np.nan
    return out


def judge(r, p95):
    """Rules a-h on WF (+ EARLY for h); a NaN fails. Returns ({rule: bool}, all)."""
    w, e, R = r["WF"], r["EARLY"], RULES
    chk = {"a_n": w["n"] >= R["n"], "b_roc": w["roc30"] >= R["roc30"], "c_pf": w["pf"] >= R["pf"], "d_t": w["t"] >= R["t"] and w["t"] > p95,
           "e_stress": w["stress_net"] > 0, "f_exbig": w["net_ex_big"] > 0, "g_years": w["years_pos"] >= R["years_pos"], "h_early": e["net"] > 0}
    chk = {k: bool(v) for k, v in chk.items()}
    return chk, all(chk.values())


# ------------------------------------------------------------------ the book (#463), new convention: valued-daily mtm, years from the selected rows
def bookroc(extra, t0, t1, inclusive=False):
    """#463's daily mtm (+ extra, a Series by date, reindexed on the union of dates, fill 0) on [t0, t1) or [t0, t1] (inclusive):
    net = sum, dd = max drawdown (peak starts at 0), years = (last - first).days / 365.25 of the selected rows, roc30 = 30 x (net / years) / dd."""
    b = pd.read_csv(BOOK, parse_dates=["date"]).set_index("date").sort_index()
    idx = b.index.union(extra.index) if extra is not None else b.index
    M = b["mtm"].reindex(idx).fillna(0.0)
    if extra is not None:
        M = M + extra.reindex(idx).fillna(0.0)
    m = M[(idx >= t0) & ((idx <= t1) if inclusive else (idx < t1))]
    if not len(m):
        return {"net": float("nan"), "dd_daily": float("nan"), "years": float("nan"), "roc30": float("nan"), "sortino": float("nan"), "n": 0, "first": None, "last": None}
    net, ddv, yrs = float(m.sum()), ddmax(m.values), (m.index[-1] - m.index[0]).days / 365.25
    return {"net": net, "dd_daily": ddv, "years": yrs, "roc30": 30.0 * (net / yrs) / ddv if ddv > 0 and yrs > 0 else float("nan"), "sortino": so(m.values),
            "n": len(m), "first": m.index[0], "last": m.index[-1]}


def book_ok(r, ref):
    return abs(r["roc30"] - ref[0]) < TOL[0] and abs(r["sortino"] - ref[1]) < TOL[1]


def a2_pass(r):
    """A2: the book + leg WF ROC@30k >= 98.50 (1.05 x 93.81) AND its WF Sortino >= 3.816"""
    return bool(r["roc30"] >= RULES["a2_roc"] and r["sortino"] >= RULES["a2_sort"])


def b_checks(r, big, leg_net, leg_n):
    """Stage B: book(+leg) LB ROC@30k >= 155.54 AND LB Sortino >= 4.150 AND (book LB net - the biggest single trade) > 0 AND the leg's own LB net > 0 AND >= 50 LB trades"""
    return {"roc": bool(r["roc30"] >= RULES["b_roc"]), "sortino": bool(r["sortino"] >= RULES["b_sort"]), "net_ex_big": bool(r["net"] - big > 0),
            "leg_net": bool(leg_net > 0), "leg_n": bool(leg_n >= RULES["b_n"])}


def book_trades_path():
    return os.path.join(os.path.dirname(BOOK), "book463_trades.csv")


# ------------------------------------------------------------------ Stage A
def reports(S, sig, trs):
    """Reported, never a pass route: WF daily correlation with each #463 leg and the book (union of dates, fill 0), the per-trade correlation of CONT pnl with ES's own
    10:30-15:55 move (CHOICE: reported as asked - the unsigned move - and also side-signed, the residual market exposure), mean beta and h over the WF trade days."""
    days = S["dates"]
    book = None
    if os.path.exists(BOOK):
        b = pd.read_csv(BOOK, parse_dates=["date"]).set_index("date").sort_index()
        book = b[(b.index >= WF0) & (b.index < LB0)]
    rep = {"book_file": book is not None, "book_corr": {}, "es_corr": {}, "mean_beta": {}, "mean_h": {}}
    for k in KS:
        name = f"k{k}|CONT"
        t = trs[("CONT", k)]
        w = t[(t["date"] >= WF0) & (t["date"] < LB0)]
        rep["es_corr"][name] = {"unsigned": corr(w["pnl"], w["es_move"]), "side_signed": corr(w["pnl"], w["side"] * w["es_move"])}
        rep["mean_beta"][name] = float(w["beta"].mean()) if len(w) else float("nan")
        rep["mean_h"][name] = float(w["h"].mean()) if len(w) else float("nan")
        if book is not None:
            daily = w.groupby("date")["pnl"].sum().reindex(days[(days >= WF0) & (days < LB0)]).fillna(0.0)
            ix = book.index.union(daily.index)
            d = daily.reindex(ix).fillna(0.0).to_numpy()
            rep["book_corr"][name] = {c: corr(d, book[c].reindex(ix).fillna(0.0).to_numpy()) for c in BOOK_COLS}
    return rep


def top10(t):
    w = t[(t["date"] >= WF0) & (t["date"] < LB0)]
    w = w.reindex(w["pnl"].abs().sort_values(ascending=False).index[:10])
    return [(str(d.date()), float(p)) for d, p in zip(w["date"], w["pnl"])]


def stage_a_core():
    """Everything Stage A computes, nothing printed or saved. Inputs are cut at the lockbox inside load() before anything below runs."""
    L = load(LB0)
    S = build_sessions(L)
    days = S["dates"]
    assert len(days) and days.max() < LB0, "Stage A sessions reach the lockbox"
    masters = {f"{i}|{t}": {"id": int(m["id"]), "source": m["source"], "bars": len(df), "first": df.index.min(), "last": df.index.max()} for (i, t), (df, m) in sorted(L.items())}
    sig = signal(S["oN"], S["cN"], S["oE"], S["cE"])
    cells, trs = {}, {}
    for k in KS:
        for role, mir in (("CONT", False), ("REV", True)):
            t = cell_trades(S, sig, k, mirror=mir)
            assert len(t) == 0 or t["date"].max() < LB0
            trs[(role, k)] = t
            cells[f"k{k}|{role}"] = {"role": role, "k": k, "WF": stats(t, days, WF0, LB0), "EARLY": stats(t, days, days[0], WF0)}
    null = null_dist(S, sig)
    p95, med = float(np.nanpercentile(null, 95)), float(np.nanmedian(null))               # CHOICE: numpy's default (linear) interpolation for the 95th percentile
    for name, r in cells.items():
        r["rules"], r["PASS"] = judge(r, p95) if r["role"] == "CONT" else ({}, False)          # the reversal mirror is a control: never a pass route
    passes = [n for n, r in cells.items() if r["PASS"]]
    nw, ne = int(((days >= WF0) & (days < LB0)).sum()), int((days < WF0).sum())
    counts = {"eligible": len(days), "early": ne, "wf": nw, "first": days[0], "last": days[-1], "any": S["n_any"], "complete": S["n_complete"], "guard_dropped": S["n_guard"]}
    return {"S": S, "sig": sig, "trs": trs, "cells": cells, "null": null, "p95": p95, "median": med, "passes": passes, "counts": counts, "masters": masters,
            "rep": reports(S, sig, trs), "top10_k0": top10(trs[("CONT", 0)])}


def a2(R):
    """Book add, pre-lockbox: the Stage-A pass with the highest WF ROC added to #463's daily mtm on the WF stretch at c in {1, 2, 3}; c = the best by book WF ROC, then frozen.
    CHOICE: a tie goes to the smaller c; the WF rows of the book file are [2016-07-01, 2025-06-30), weekend-dated rows included (that is what reproduces 93.81 / 3.816)."""
    try:
        base = bookroc(None, WF0, LB0)
    except FileNotFoundError:
        print("A2 NOT judged: the book file is missing")
        return {"pass": False, "error": "book file missing"}
    print(f"BOOK #463 WF (check {BOOK_WF[0]} / {BOOK_WF[1]}): ROC@30k {base['roc30']:.2f} Sortino {base['sortino']:.3f} DD ${base['dd_daily']:,.0f}")
    if CHECK_BOOK and not book_ok(base, BOOK_WF):
        print("A2 NOT judged: the book file does not reproduce #463's WF numbers (93.81 / 3.816) - fix the input first")
        return {"pass": False, "error": "book check mismatch", "book_wf": base}
    pick = max(R["passes"], key=lambda p: nz(R["cells"][p]["WF"]["roc30"]))
    t = R["trs"][("CONT", R["cells"][pick]["k"])]
    leg = t[(t["date"] >= WF0) & (t["date"] < LB0)].groupby("date")["pnl"].sum()
    by_c = {c: bookroc(leg * c, WF0, LB0) for c in (1, 2, 3)}
    cb = max(by_c, key=lambda c: nz(by_c[c]["roc30"]))
    ok = a2_pass(by_c[cb])
    for c, r in by_c.items():
        print(f"  #463 + {pick} x{c}: WF ROC@30k {r['roc30']:.2f} Sortino {r['sortino']:.3f} DD ${r['dd_daily']:,.0f}")
    print("A2:", f"PASS (x{cb}, cell {pick})" if ok else f"FAIL (needs ROC >= {RULES['a2_roc']} and Sortino >= {RULES['a2_sort']})")
    return {"cell": pick, "c": cb, "pass": bool(ok), "book_wf": base, "by_c": {str(c): r for c, r in by_c.items()}}


def stage_a():
    if os.path.exists(os.path.join(OUT, "stageB_READ.flag")):                  # CHOICE (an addition): after the one read the Stage A record is frozen - a change is a new file (r3)
        print("Stage A refused: the lockbox was already read - stageA.json and the trade files are the frozen record (any change = a new file)")
        return None
    os.makedirs(OUT, exist_ok=True)
    if not (os.path.exists(PREREG) and sha_lf(PREREG) == PREREG_SHA):              # the frozen spec must be the committed one (a changed spec = a new file, r3)
        print("Stage A refused: PREREG_SPREAD_R2.txt is missing or differs from the committed pre-registration (18a9bae2)")
        return None
    R = stage_a_core()
    cells, trs, p95, cn = R["cells"], R["trs"], R["p95"], R["counts"]
    for (role, k), t in trs.items():
        t.to_csv(os.path.join(OUT, f"trades_k{k}_{role.lower()}.csv"), index=False)
    pd.DataFrame({"rep": np.arange(NREP), "max_t": R["null"]}).to_csv(os.path.join(OUT, "null.csv"), index=False)
    rows = []
    for name, r in cells.items():
        w, e = r["WF"], r["EARLY"]
        rows.append((name, "CONT" if r["role"] == "CONT" else "REV control", w["n"], w["net"], w["per_trade"], w["win"], w["pf"], w["dd_daily"], w["roc30"], w["sortino"],
                     w["t"], w["years_pos"], w["stress_net"], w["net_ex_big"], e["n"], e["net"], bool(r["PASS"])))
    tab = pd.DataFrame(rows, columns=["cell", "role", "wf_n", "wf_net", "per_trade", "win", "pf", "dd_daily", "roc30", "sortino", "t", "years_pos", "stress_net",
                                      "net_ex_big", "early_n", "early_net", "PASS"])
    tab.to_csv(os.path.join(OUT, "stageA_table.csv"), index=False)
    print(f"SPREAD r2 Stage A, pre-lockbox: {cn['eligible']:,} eligible sessions {cn['first']:%Y-%m-%d} .. {cn['last']:%Y-%m-%d} (EARLY {cn['early']:,}, WF {cn['wf']:,}); "
          f"{cn['complete']:,} complete, {cn['guard_dropped']} dropped by the roll guard; first possible trade = session {2 * MINLOOK + 1}")
    pd.set_option("display.width", 250); pd.set_option("display.max_columns", 50)
    print(tab.round(3).to_string(index=False))
    print(f"null max-t (500 reps, seed {SEED}): p95 {p95:.3f}, median {R['median']:.3f}")
    for name, r in cells.items():
        if r["role"] == "CONT":
            bad = [k for k, v in r["rules"].items() if not v]
            print(f"  {name}: " + ("clears rules a-h" if not bad else "fails " + ", ".join(bad)))
    rep = R["rep"]
    for name in rep["es_corr"]:
        ec = rep["es_corr"][name]
        print(f"  {name} reported: corr(pnl, ES move) per trade {ec['unsigned']:.3f} (side-signed {ec['side_signed']:.3f}); mean beta {rep['mean_beta'][name]:.3f}, mean h {rep['mean_h'][name]:.3f}"
              + ("; WF daily corr with " + ", ".join(f"{c} {v:.3f}" for c, v in rep["book_corr"][name].items()) if rep["book_file"] else "; book file missing"))
    print("  k0|CONT ten biggest |pnl| WF days: " + ", ".join(f"{d} ${p:,.0f}" for d, p in R["top10_k0"]))
    out = {"prereg_file": "PREREG_SPREAD_R2.txt", "prereg_sha256_lf": sha_lf(PREREG) if os.path.exists(PREREG) else None, "harness_sha256": sha_raw(os.path.abspath(__file__)),
           "harness_sha256_lf": sha_lf(os.path.abspath(__file__)), "rules": {"thresholds": dict(RULES), "text": RULE_TEXT}, "null": {"reps": NREP, "seed": SEED, "p95": p95, "median": R["median"]}, "counts": cn, "masters": R["masters"],
           "cells": cells, "passes": R["passes"], "reported": {**rep, "top10_k0": R["top10_k0"]}, "A2": None}
    if R["passes"]:
        out["A2"] = a2(R)
    else:
        print("Stage A passes: none - SPREAD r2 dead; the lockbox stays sealed")
    save("stageA.json", out)
    return out


# ------------------------------------------------------------------ Stage B (book lockbox, read ONCE)
def refuse(why):
    print("Stage B refused: " + why)
    return {"status": "refused", "why": why}


def tail_check(S, tr, k):
    """CHOICE (an addition, protects the one read): the pre-lockbox tail of the frozen cell recomputed from the lockbox load (Stage B starts later, 2024-10-01) must equal
    Stage A's saved trade file, over the sessions whose beta AND scale windows are complete in both runs (index >= 2 x 60 in this load)."""
    if len(S["dates"]) <= 2 * LOOK:
        return False, f"only {len(S['dates'])} sessions loaded - the 60 + 60 session windows are not complete"
    p = os.path.join(OUT, f"trades_k{k}_cont.csv")
    if not os.path.exists(p):
        return False, "Stage A's trade file for the frozen cell is missing"
    lo = S["dates"][2 * LOOK]
    a = pd.read_csv(p, parse_dates=["date"])
    a = a[(a["date"] >= lo) & (a["date"] < LB0)].reset_index(drop=True)
    b = tr[(tr["date"] >= lo) & (tr["date"] < LB0)].reset_index(drop=True)
    cols = ["side", "h", "pnl"]
    if len(a) != len(b) or not (a["date"].to_numpy() == b["date"].to_numpy()).all() or not np.allclose(a[cols].to_numpy(float), b[cols].to_numpy(float), rtol=0.0, atol=1e-6):
        return False, "the pre-lockbox tail recomputed from the lockbox load differs from Stage A's trade file"
    return True, f"{len(a)} pre-lockbox trades from {lo:%Y-%m-%d} identical to Stage A's file"


def stage_b():
    pa = os.path.join(OUT, "stageA.json")
    if not os.path.exists(pa):
        return refuse("no stageA.json on file - the lockbox stays sealed")
    res = json.loads(rd(pa))
    pre = res.get("A2") or {}
    if not pre.get("pass"):
        return refuse("no Stage A2 pass on file - the lockbox stays sealed")
    flag = os.path.join(OUT, "stageB_READ.flag")
    if os.path.exists(flag):
        return refuse("the lockbox was already read once")
    cell, c = pre["cell"], int(pre["c"])                                       # the FROZEN pre-registered cell and c (not re-picked, not the validate's tuned setting)
    k = int(cell.split("|")[0][1:])
    # CHOICE (order): load -> compute the frozen cell's trades in memory -> every check -> flag -> evaluate; everything that can fail comes BEFORE the flag, so a crash or a
    # refusal above or here leaves the lockbox unread, and nothing from the lockbox is printed or saved until the flag is down
    S = build_sessions(load(LBX, B_D0))                                        # loads first; nothing is computed yet
    days = S["dates"]
    if not ((days >= LB0) & (days <= LB1)).any():                              # CHOICE (an addition): a load with no lockbox session must not burn the one read
        return refuse("no lockbox sessions were loaded (lockbox NOT read)")
    sig = signal(S["oN"], S["cN"], S["oE"], S["cE"])
    tr = cell_trades(S, sig, k)                                                # in memory only: nothing from the lockbox is printed or saved until the flag is down
    ok_tail, why = tail_check(S, tr, k)
    if not ok_tail:
        return refuse(why + " (lockbox NOT read)")
    try:
        base = bookroc(None, LB0, LB1, inclusive=True)                         # #463's own LB numbers are public (prereg): checked before the family's lockbox is read
        bt = pd.read_csv(book_trades_path(), parse_dates=["date"])             # CHOICE (an addition): read before the flag too - a missing book file refuses and must not burn the read
    except FileNotFoundError as e:
        return refuse(f"a book file is missing ({os.path.basename(str(e.filename))}) (lockbox NOT read)")
    if CHECK_BOOK and not book_ok(base, BOOK_LB):
        return refuse(f"the book file does not reproduce #463's LB numbers ({BOOK_LB[0]} / {BOOK_LB[1]}; got {base['roc30']:.2f} / {base['sortino']:.3f}) (lockbox NOT read)")
    os.makedirs(OUT, exist_ok=True)
    wr(flag, pd.Timestamp.now().isoformat())                                   # the one read starts here
    print(f"Stage B: lockbox data loaded; #463's own LB numbers {base['roc30']:.2f} / {base['sortino']:.3f} " + ("reproduce the reference" if CHECK_BOOK else "(book check waived: smoke only)")
          + " - READ flag written, reading the lockbox once")
    lt = tr[(tr["date"] >= LB0) & (tr["date"] <= LB1)]
    leg = lt.groupby("date")["pnl"].sum() * c
    r = bookroc(leg, LB0, LB1, inclusive=True)
    bl = bt[(bt["date"] >= LB0) & (bt["date"] <= LB1)]["pnl"]
    big_book = float(bl.max()) if len(bl) else 0.0
    big_leg = float(lt["pnl"].max() * c) if len(lt) else 0.0
    big = max(big_book, big_leg)
    leg_net = float(lt["pnl"].sum())                                           # CHOICE: "the leg's own LB net" = the unscaled (c = 1) leg's net; the sign is the same at any c > 0
    chk = b_checks(r, big, leg_net, len(lt))
    ok = all(chk.values())
    print(f"Stage B: frozen {cell} x{c}: book LB ROC@30k {r['roc30']:.2f} Sortino {r['sortino']:.3f} | book LB net ${r['net']:,.0f}, biggest trade ${big:,.0f} | "
          f"leg LB {len(lt)} trades ${leg_net:,.0f} -> {'PASS' if ok else 'FAIL'} ({', '.join(k_ for k_, v in chk.items() if not v) or 'all clear'})")
    lt.to_csv(os.path.join(OUT, "stageB_trades.csv"), index=False)
    out = {"status": "read", "cell": cell, "c": c, "B": r, "book_lb_alone": base, "leg_n": len(lt), "leg_net": leg_net, "leg_net_x_c": float(leg.sum()), "biggest_book_trade": big_book,
           "biggest_leg_trade_x_c": big_leg, "biggest_single_trade": big, "checks": chk, "pass": bool(ok), "tail_check": why, "rules": dict(RULES),
           "harness_sha256": {"stageA": res.get("harness_sha256"), "stageB": sha_raw(os.path.abspath(__file__)), "stageA_lf": res.get("harness_sha256_lf"), "stageB_lf": sha_lf(os.path.abspath(__file__))},
           "prereg_sha256_lf": sha_lf(PREREG) if os.path.exists(PREREG) else None}
    save("stageB.json", out)
    return out


# ------------------------------------------------------------------ count (outcome-free)
def count():
    L = load(LB0)
    S = build_sessions(L)
    d = S["dates"]
    print("SPREAD r2 session count (outcome-free: bars before the cut only; no signal, no P&L is computed)")
    for (inst, tag), (df, m) in sorted(L.items()):
        print(f"  master {inst} {tag}: registry id {m['id']}, {len(df):,} bars {df.index.min():%Y-%m-%d} .. {df.index.max():%Y-%m-%d}")
    n_e, n_w = int((d < WF0).sum()), int(((d >= WF0) & (d < LB0)).sum())
    print(f"  dates with any 09:30-15:55 bar on any master: {S['n_any']:,}")
    print(f"  complete (all 78 bars on all four masters):    {S['n_complete']:,}   (partial, dropped: {S['n_any'] - S['n_complete']:,})")
    print(f"  dropped by the roll guard:                     {S['n_guard']:,}" + ("   " + ", ".join(f"{x:%Y-%m-%d}" for x in S["guard_dates"][:10]) if S["n_guard"] else ""))
    print(f"  ELIGIBLE sessions:                             {len(d):,}   first {d[0]:%Y-%m-%d}, last {d[-1]:%Y-%m-%d}")
    print(f"  EARLY (first eligible .. before 2016-07-01):   {n_e:,}")
    print(f"  WF    (2016-07-01 .. before the cut):          {n_w:,}")
    return {"eligible": len(d), "early": n_e, "wf": n_w, "guard": S["n_guard"], "complete": S["n_complete"], "any": S["n_any"]}


# ------------------------------------------------------------------ smoke: offline self-test on SYNTHETIC masters + a synthetic book (every number means nothing)
class World:
    """Synthetic NQ / ES 5-minute RTH masters (raw + roll-corrected twins) for smoke(). ES is a random walk; NQ = beta_true x ES + noise; a planted continuation (GAMMA x the
    first-hour NQ-vs-ES move arrives after 10:30) so the CONT cells earn; adj = raw + a per-session constant. Planted bad sessions (self.plan) must be dropped.
    post_seed changes ONLY the sessions on/after the Stage A cut (smoke proves Stage A cannot see them); leaky = load_master_arrays ignores date_to, so only load()'s own
    cut stands between Stage A and the later bars."""
    GAMMA, BETAS = 0.5, (1.15, 1.35)

    def __init__(self, post_seed=1, leaky=True):
        rng = np.random.default_rng(11)

        def pick(a, b, n):
            d = pd.bdate_range(a, b)
            return d[np.sort(rng.choice(len(d), size=min(n, len(d)), replace=False))]
        early, sparse = pick("2014-01-02", "2016-06-30", 130), pick("2016-07-01", "2024-09-30", 240)
        dense, lb, post = pd.bdate_range("2024-10-01", "2025-06-27"), pd.bdate_range("2025-06-30", "2026-06-30"), pick("2026-07-01", "2026-08-31", 25)
        days = early.union(sparse).union(dense).union(lb).union(post).union(pd.DatetimeIndex(["2016-06-30", "2016-07-01", "2026-07-01"]))
        self.days, self.leaky = days, leaky
        self.plan = {"nq_raw_gap": sparse[100], "es_adj_gap": dense[30], "nq_adj_gap": early[90], "es_raw_dup": sparse[180], "early_close": lb[40],
                     "guard_nq_both": sparse[150], "guard_nq_open": dense[60], "guard_es_close": early[100], "jitter_ok": sparse[220], "jitter_bad": dense[90],
                     "nq_adj_dup": early[60], "es_raw_offgrid": dense[120]}
        self.role = {d: r for r, d in self.plan.items()}
        self.partial = {self.plan[r] for r in ("nq_raw_gap", "es_adj_gap", "nq_adj_gap", "es_raw_dup", "early_close", "nq_adj_dup", "es_raw_offgrid")}
        self.guard = {self.plan[r] for r in ("guard_nq_both", "guard_nq_open", "guard_es_close", "jitter_bad")}
        rng_pre, rng_post = np.random.default_rng(5), np.random.default_rng(1000 + post_seed)
        T, O, C = ({k: [] for k in IDS} for _ in range(3))
        es_px, nq_px = 4500.0, 15500.0
        self.beta_true, self.px = {}, {}
        for i, d in enumerate(days):
            r = rng_post if d >= LB0 else rng_pre
            beta = self.BETAS[0] if i < len(days) // 2 else self.BETAS[1]
            self.beta_true[d] = beta
            gap = r.normal(0, 0.004)
            e0, n0 = es_px * (1 + gap), nq_px * (1 + beta * gap + r.normal(0, 0.002))
            rE = r.normal(0, 0.0007, NB)
            noise = r.normal(0, 0.0003, NB)
            noise[:12] *= 2.0
            drift = np.zeros(NB)
            drift[12:77] = self.GAMMA * noise[:12].sum() / 65.0                 # the planted continuation of the first-hour idiosyncratic NQ move
            cE = e0 * np.cumprod(1.0 + rE)
            cN = n0 * np.cumprod(1.0 + beta * rE + noise + drift)
            oE, oN = np.concatenate([[e0], cE[:-1]]), np.concatenate([[n0], cN[:-1]])
            es_px, nq_px = cE[-1], cN[-1]
            self.px[d] = (oN.copy(), cN.copy(), oE.copy(), cE.copy())
            off_n, off_e = -1500.0 - 0.4 * i, -50.0 - 0.05 * i
            bars = {("NQ", SRC_RAW): [oN.copy(), cN.copy()], ("NQ", SRC_ADJ): [oN + off_n, cN + off_n],
                    ("ES", SRC_RAW): [oE.copy(), cE.copy()], ("ES", SRC_ADJ): [oE + off_e, cE + off_e]}
            slots = {k: np.arange(NB) for k in bars}
            role = self.role.get(d)
            if role == "nq_raw_gap": slots[("NQ", SRC_RAW)] = np.delete(np.arange(NB), 30)
            if role == "es_adj_gap": slots[("ES", SRC_ADJ)] = np.delete(np.arange(NB), 5)
            if role == "nq_adj_gap": slots[("NQ", SRC_ADJ)] = np.delete(np.arange(NB), 60)
            if role == "es_raw_dup": slots[("ES", SRC_RAW)] = np.array(list(range(40)) + [41, 41] + list(range(42, NB)))    # 78 rows, slot 40 missing, slot 41 twice
            if role == "nq_adj_dup": slots[("NQ", SRC_ADJ)] = np.array(list(range(71)) + [70] + list(range(71, NB)))      # all 78 slots present, slot 70 twice (79 rows)
            if role == "early_close": slots = {k: np.arange(46) for k in bars}
            if role == "guard_nq_both": bars[("NQ", SRC_ADJ)][0][40:] += 6.25; bars[("NQ", SRC_ADJ)][1][40:] += 6.25
            if role == "guard_nq_open": bars[("NQ", SRC_ADJ)][0][40:] += 6.25
            if role == "guard_es_close": bars[("ES", SRC_ADJ)][1][40:] += 1.0
            if role == "jitter_ok": bars[("ES", SRC_ADJ)][1][40:] += 5e-7                 # inside the 1e-6 tolerance: stays eligible
            if role == "jitter_bad": bars[("ES", SRC_ADJ)][0][40:] += 2e-6                # outside it: dropped
            for key, (o, c) in bars.items():
                sl = slots[key]
                ts, oo, cc = d.to_datetime64() + (B_FIRST + 5 * sl).astype("timedelta64[m]"), o[sl], c[sl]
                if role == "es_raw_offgrid" and key == ("ES", SRC_RAW):                   # 78 grid bars plus one extra bar at 10:42, off the 5-minute grid
                    ts, oo, cc = np.append(ts, d.to_datetime64() + np.timedelta64(B_FIRST + 5 * 14 + 2, "m")), np.append(oo, oo[14]), np.append(cc, cc[14])
                T[key].append(ts)
                O[key].append(oo)
                C[key].append(cc)
        self.tab = {k: (pd.DatetimeIndex(np.concatenate(T[k])).tz_localize("US/Eastern"), np.concatenate(O[k]), np.concatenate(C[k])) for k in IDS}

    def install(self):
        data, w = data_mod(), self

        def find(instrument, timeframe, session=None, source=None):
            assert (instrument, timeframe, session, source) in {(i, "5m", "rth", s) for i in ("NQ", "ES") for s in (SRC_RAW, SRC_ADJ)}, (instrument, timeframe, session, source)
            return {"id": IDS[(instrument, source)], "instrument": instrument, "timeframe": timeframe, "session": session, "source": source, "filename": "SMOKE"}

        def arrays(master, date_from=None, date_to=None):
            idx, o, c = w.tab[(master["instrument"], master["source"])]
            keep = np.ones(len(idx), bool)
            if date_from:
                keep &= np.asarray(idx >= TS(date_from, tz="US/Eastern"))
            if date_to and not w.leaky:
                keep &= np.asarray(idx < TS(date_to, tz="US/Eastern") + pd.Timedelta(days=1))
            return {"index": idx[keep], "open": o[keep], "close": c[keep], "meta": master}
        data.find_master, data.load_master_arrays = find, arrays


def hand_world():
    """88 quiet sessions (NQ = ES + tiny noise, beta ~ 1, ES ~5000, NQ ~20000) and two sessions priced BY HAND (86: first hour up, 87: first hour down)."""
    rng = np.random.default_rng(3)
    n = 88
    rE = rng.normal(0, 0.0007, (n, NB))
    rN = rE + rng.normal(0, 2e-5, (n, NB))
    cE, cN = 5000.0 * np.cumprod(1.0 + rE, axis=1), 20000.0 * np.cumprod(1.0 + rN, axis=1)
    oE, oN = np.concatenate([np.full((n, 1), 5000.0), cE[:, :-1]], axis=1), np.concatenate([np.full((n, 1), 20000.0), cN[:, :-1]], axis=1)
    for i, (n0, n11, n76, e0, e11, e76) in ((86, (19800.0, 20000.0, 20100.0, 4995.0, 5000.0, 5020.0)), (87, (20200.0, 20000.0, 19900.0, 5001.0, 5000.0, 4990.0))):
        for o, c, p0, p11, p76 in ((oN, cN, n0, n11, n76), (oE, cE, e0, e11, e76)):
            first = p0 + (p11 - p0) * np.arange(1, 13) / 12.0                      # closes of bars 0..11 climb (or fall) from p0 to p11
            later = p11 + (p76 - p11) * np.arange(1, 66) / 65.0                    # closes of bars 12..76 run from p11 to p76
            c[i] = np.concatenate([first, later, [p76]])
            o[i] = np.concatenate([[p0], c[i][:-1]])
    return oN, cN, oE, cE


def brute(oN, cN, oE, cE):
    """Independent plain-Python recomputation (lists and loops only, no numpy vector shortcuts) of beta, s, scale, h, gross_plus, cost, add and every cell's trades."""
    S = len(cN)
    f = lambda a: [[float(v) for v in row] for row in a]
    oN, cN, oE, cE = f(oN), f(cN), f(oE), f(cE)
    rN = [[row[j] / row[j - 1] - 1.0 for j in range(1, 78)] for row in cN]
    rE = [[row[j] / row[j - 1] - 1.0 for j in range(1, 78)] for row in cE]
    beta, s, scale, h = [None] * S, [None] * S, [None] * S, [None] * S
    for i in range(S):
        lo = max(0, i - 60)
        if i - lo < 40:
            continue
        xs = [v for row in rE[lo:i] for v in row]
        ys = [v for row in rN[lo:i] for v in row]
        mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
        sxy = sxx = 0.0
        for x, y in zip(xs, ys):
            sxy += (x - mx) * (y - my)
            sxx += (x - mx) * (x - mx)
        beta[i] = sxy / sxx
        s[i] = (cN[i][11] / oN[i][0] - 1.0) - beta[i] * (cE[i][11] / oE[i][0] - 1.0)
        h[i] = max(0.1, round(beta[i] * (cN[i][11] * 20.0) / (cE[i][11] * 50.0), 1))
    for i in range(S):
        w = sorted(abs(s[j]) for j in range(max(0, i - 60), i) if s[j] is not None)
        if len(w) >= 40:
            m = len(w)
            scale[i] = w[m // 2] if m % 2 else (w[m // 2 - 1] + w[m // 2]) / 2.0
    gp, cost, add = [None] * S, [None] * S, [None] * S
    tr = {(role, k): [] for role in ("CONT", "REV") for k in (0, 1, 2)}
    for i in range(S):
        if h[i] is None:
            continue
        gp[i] = 20.0 * (cN[i][76] - oN[i][12]) - 50.0 * h[i] * (cE[i][76] - oE[i][12])
        cost[i] = 0.533 * 20.0 + h[i] * 0.363 * 50.0
        add[i] = 0.25 * 20.0 + h[i] * 0.25 * 50.0
        if scale[i] is None or s[i] == 0:
            continue
        for k in (0, 1, 2):
            if abs(s[i]) >= k * scale[i]:
                side = 1.0 if s[i] > 0 else -1.0
                for role, sd in (("CONT", side), ("REV", -side)):
                    p = sd * gp[i] - cost[i]
                    tr[(role, k)].append((i, sd, p, p - add[i]))
    return {"beta": beta, "s": s, "scale": scale, "h": h, "gross_plus": gp, "cost": cost, "add": add, "trades": tr}


def selftest(root):
    """Hand checks that need no data: stats / rules / book convention / hedge rounding / hash, and the one-session P&L arithmetic on hand-priced sessions."""
    global BOOK
    # the pre-registered constants, literally (a typo in a seed, a window, a cost or a bar must fail here)
    assert (KS, LOOK, MINLOOK, NREP, SEED) == ((0, 1, 2), 60, 40, 500, 20261002) and (NB, B_FIRST, B_LAST, I_SIG, I_ENT, I_EXIT) == (78, 570, 955, 11, 12, 76)
    assert (NQ_X, ES_X, NQ_PTS, ES_PTS, STRESS, GUARD_TOL) == (20.0, 50.0, 0.533, 0.363, 0.25, 1e-6) and (A_D0, B_D0) == ("2010-06-01", "2024-10-01")
    assert (WF0, LB0, LB1, LBX) == (TS("2016-07-01"), TS("2025-06-30"), TS("2026-06-30"), TS("2026-07-01")) and (SRC_RAW, SRC_ADJ) == ("db_noadj_rth", "db_adj_rth")
    assert RULES == {"n": 100, "roc30": 15.0, "pf": 1.10, "t": 2.0, "years_pos": 0.60, "a2_roc": 98.50, "a2_sort": 3.816, "b_roc": 155.54, "b_sort": 4.150, "b_n": 50}
    assert (BOOK_WF, BOOK_LB, TOL) == ((93.81, 3.816), (155.54, 4.150), (0.006, 0.0006)) and BOOK_COLS == ("L0_mtm", "L1_mtm", "L2_mtm", "L3_mtm", "mtm")
    assert IDS == {("NQ", "db_noadj_rth"): 37, ("ES", "db_noadj_rth"): 33, ("NQ", "db_adj_rth"): 73, ("ES", "db_adj_rth"): 63} and CHECK_BOOK is True, "a real run always checks the book"
    # 6. stats on a hand-made daily series. Sessions: 4 in 2016 H2, 4 in 2017 Q1, plus one outside each end (must be excluded: [t0, t1) is half-open).
    days = pd.DatetimeIndex(["2016-06-30", "2016-07-05", "2016-07-06", "2016-07-07", "2016-07-08", "2017-01-03", "2017-01-04", "2017-01-05", "2017-01-06", "2017-01-09"])
    pnl = {"2016-06-30": 1000.0, "2016-07-05": 100.0, "2016-07-06": -50.0, "2016-07-08": 200.0, "2017-01-03": -150.0, "2017-01-04": 50.0, "2017-01-06": -50.0, "2017-01-09": -1000.0}
    tr = pd.DataFrame({"date": pd.DatetimeIndex(list(pnl)), "pnl": list(pnl.values())})
    tr["pnl_stress"] = tr["pnl"] - 10.0
    s = stats(tr, days, TS("2016-07-01"), TS("2017-01-09"))                       # t1 = 2017-01-09 is EXCLUDED, 2016-06-30 is before t0
    # hand arithmetic: trades [100, -50, 200, -150, 50, -50] (n 6, net 100, wins 350, losses 250); daily over the 8 sessions in the stretch
    # [100, -50, 0, 200, -150, 50, 0, -50] -> cumulative [100, 50, 50, 250, 100, 150, 150, 100], peak from 0 [100, 100, 100, 250, 250, 250, 250, 250] -> max dd 150;
    # years = (2017-01-06 - 2016-07-05) = 185 days / 365.25; Sortino = (100/8) / sqrt((50^2 + 150^2 + 50^2) / 8) x sqrt(252); per-trade t: mean 100/6, sum sq dev 78333.33, sd = sqrt(78333.33 / 5)
    assert s["days"] == 8 and s["n"] == 6 and abs(s["net"] - 100) < 1e-9 and abs(s["dd_daily"] - 150) < 1e-9, s
    assert abs(s["years"] - 185 / 365.25) < 1e-12 and abs(s["roc30"] - 30 * (100 / (185 / 365.25)) / 150) < 1e-9, s
    assert abs(s["sortino"] - (100 / 8) / math.sqrt(27500 / 8) * math.sqrt(252)) < 1e-9 and abs(s["pf"] - 350 / 250) < 1e-12 and abs(s["win"] - 0.5) < 1e-12, s
    assert abs(s["t"] - (100 / 6) / (math.sqrt(78333.3333333333 / 5) / math.sqrt(6))) < 1e-9 and abs(s["net_ex_big"] - (100 - 200)) < 1e-9, s
    assert abs(s["years_pos"] - 0.5) < 1e-12 and abs(s["stress_net"] - (100 - 60)) < 1e-9 and s["first"] == TS("2016-07-05") and s["last"] == TS("2017-01-06"), s
    z = pd.DataFrame({"date": pd.DatetimeIndex(["2018-03-05", "2018-03-06"]), "pnl": [50.0, -50.0]})
    z["pnl_stress"] = z["pnl"]
    assert stats(z, pd.DatetimeIndex(z["date"]), TS("2018-01-01"), TS("2019-01-01"))["years_pos"] == 0.0, "a calendar year whose daily sum is exactly 0 is not a positive year"
    q = np.array([-10.0, 5.0])
    assert abs(ddmax(q) - 10) < 1e-12 and ddmax([]) == 0.0 and math.isnan(so([1.0, 2.0])) and math.isnan(stats(tr.iloc[:0], days, TS("2020-01-01"), TS("2021-01-01"))["roc30"])
    assert stats(tr[tr.pnl > 0], days, TS("2016-07-01"), TS("2017-01-09"))["pf"] == float("inf")
    # the rules, one at a time, at their boundaries (>= for a b c g, > for e f h and for t vs the null p95)
    base = {"WF": {"n": 100, "roc30": 15.0, "pf": 1.10, "t": 2.0, "stress_net": 1.0, "net_ex_big": 1.0, "years_pos": 0.6}, "EARLY": {"net": 1.0}}
    assert judge(base, 1.99)[1], judge(base, 1.99)
    for rule, edit in (("a_n", ("WF", "n", 99)), ("b_roc", ("WF", "roc30", 14.99)), ("c_pf", ("WF", "pf", 1.0999)), ("d_t", ("WF", "t", 1.999)), ("e_stress", ("WF", "stress_net", 0.0)),
                       ("f_exbig", ("WF", "net_ex_big", 0.0)), ("g_years", ("WF", "years_pos", 0.59)), ("h_early", ("EARLY", "net", 0.0)), ("d_t", ("WF", "t", float("nan")))):
        r = json.loads(json.dumps(base)); r[edit[0]][edit[1]] = edit[2]
        chk, ok = judge(r, 1.99)
        assert not ok and not chk[rule] and sum(not v for v in chk.values()) == 1, (rule, chk)
    assert not judge(base, 2.0)[1] and judge(base, 2.0)[0]["d_t"] is False, "t must be strictly above the null p95"
    # the A2 and Stage B decisions at their boundaries: >= for the ROC / Sortino / trade-count bars, strictly > 0 for the two nets
    assert a2_pass({"roc30": 98.50, "sortino": 3.816}) and not a2_pass({"roc30": 98.4999, "sortino": 3.9}) and not a2_pass({"roc30": 120.0, "sortino": 3.8159}) and not a2_pass({"roc30": float("nan"), "sortino": 5.0})
    good = ({"roc30": 155.54, "sortino": 4.150, "net": 1000.0}, 999.0, 1.0, 50)
    assert all(b_checks(*good).values())
    for name, bad in (("roc", ({"roc30": 155.5399, "sortino": 4.150, "net": 1000.0}, 999.0, 1.0, 50)), ("sortino", ({"roc30": 155.54, "sortino": 4.1499, "net": 1000.0}, 999.0, 1.0, 50)),
                      ("net_ex_big", ({"roc30": 155.54, "sortino": 4.150, "net": 1000.0}, 1000.0, 1.0, 50)), ("leg_net", ({"roc30": 155.54, "sortino": 4.150, "net": 1000.0}, 999.0, 0.0, 50)),
                      ("leg_n", ({"roc30": 155.54, "sortino": 4.150, "net": 1000.0}, 999.0, 1.0, 49))):
        chk = b_checks(*bad)
        assert not chk[name] and sum(not v for v in chk.values()) == 1, (name, chk)
    # the book convention on a hand-made file: half-open vs inclusive upper end, and the extra series on the union of dates
    p = os.path.join(root, "hand_book.csv")
    pd.DataFrame({"date": ["2016-06-30", "2016-07-01", "2016-07-02", "2016-07-05", "2016-07-06", "2016-07-07"], "mtm": [999.0, 100.0, -20.0, 50.0, -80.0, 40.0]}).to_csv(p, index=False)
    keep, BOOK = BOOK, p
    try:
        r = bookroc(None, TS("2016-07-01"), TS("2016-07-06"))                      # rows 07-01, 07-02, 07-05
        assert r["n"] == 3 and abs(r["net"] - 130) < 1e-9 and abs(r["dd_daily"] - 20) < 1e-9 and abs(r["years"] - 4 / 365.25) < 1e-12, r
        assert abs(r["roc30"] - 30 * (130 / (4 / 365.25)) / 20) < 1e-9 and abs(r["sortino"] - (130 / 3) / math.sqrt(400 / 3) * math.sqrt(252)) < 1e-9, r
        r = bookroc(None, TS("2016-07-01"), TS("2016-07-06"), inclusive=True)      # + 07-06
        assert r["n"] == 4 and abs(r["net"] - 50) < 1e-9 and abs(r["dd_daily"] - 80) < 1e-9 and abs(r["roc30"] - 30 * (50 / (5 / 365.25)) / 80) < 1e-9, r
        ex = pd.Series([100.0, 7.0], index=pd.DatetimeIndex(["2016-07-06", "2016-07-03"]))      # 07-03 is not a book row: the union adds it with a book value of 0
        r = bookroc(ex, TS("2016-07-01"), TS("2016-07-06"), inclusive=True)
        assert r["n"] == 5 and abs(r["net"] - 157) < 1e-9 and abs(r["dd_daily"] - 20) < 1e-9 and abs(r["years"] - 5 / 365.25) < 1e-12, r
        assert book_ok({"roc30": 93.8056, "sortino": 3.81650}, BOOK_WF) and not book_ok({"roc30": 93.8161, "sortino": 3.8165}, BOOK_WF)           # |diff| < 0.006 / < 0.0006
        assert not book_ok({"roc30": 93.81, "sortino": 3.8167}, BOOK_WF) and not book_ok({"roc30": 93.81, "sortino": float("nan")}, BOOK_WF) and book_ok({"roc30": 155.535, "sortino": 4.1503}, BOOK_LB)
    finally:
        BOOK = keep
    # the hedge: rounding to 0.1 contract, floor 0.1; the LF hash ignores CRLF
    assert hedge(1.0, 20000.0, 5000.0) == 1.6 and hedge(0.01, 20000.0, 5000.0) == 0.1 and hedge(-0.5, 20000.0, 5000.0) == 0.1 and hedge(1.2, 20000.0, 5000.0) == 1.9, "hedge"
    for name, body in (("lf.txt", b"a\nb\n"), ("crlf.txt", b"a\r\nb\r\n")):
        wr(os.path.join(root, name), body, "wb")
    assert sha_lf(os.path.join(root, "lf.txt")) == sha_lf(os.path.join(root, "crlf.txt")) == hashlib.sha256(b"a\nb\n").hexdigest() and sha_raw(os.path.join(root, "crlf.txt")) != sha_lf(os.path.join(root, "crlf.txt"))
    print("ok 6  stats on a hand-made series (net, dd, years, ROC@30k, Sortino, pf, t, years_pos, net ex biggest, stress net; half-open stretch), the Stage A rules and the A2 / Stage B")
    print("      decisions at their boundaries, the book convention (half-open vs inclusive, extra series on the union of dates), the hedge rounding and the LF hash")
    # 4. one-session P&L arithmetic on hand-priced sessions (known prices -> known dollars)
    oN, cN, oE, cE = hand_world()
    sg = signal(oN, cN, oE, cE)
    Sh = {"dates": pd.bdate_range("2020-01-01", periods=len(cN))}
    for i, side, gross in ((86, 1.0, 400.0), (87, -1.0, -1200.0)):
        # NQ +100 pt = +$2,000 and ES +20 pt on h = 1.6 = -$1,600 -> gross 400 (86); NQ -100 = -$2,000 and ES -10 on h = 1.6 = +$800 -> gross -1200 (87); cost 10.66 + 1.6 x 18.15 = 39.70; stress +5 + 1.6 x 12.5 = 25
        assert sg["ok"][i] and sg["h"][i] == 1.6 and abs(sg["beta"][i] - 1.0) < 0.02 and abs(np.sign(sg["s"][i]) - side) < 1e-12, (i, sg["h"][i], sg["beta"][i], sg["s"][i])
        assert abs(sg["gross_plus"][i] - gross) < 1e-6 and abs(sg["cost"][i] - 39.70) < 1e-9 and abs(sg["add"][i] - 25.0) < 1e-9, (i, sg["gross_plus"][i], sg["cost"][i])
        for k in KS:
            c, r = cell_trades(Sh, sg, k).set_index("i").loc[i], cell_trades(Sh, sg, k, mirror=True).set_index("i").loc[i]
            assert c["side"] == side and abs(c["pnl"] - (side * gross - 39.70)) < 1e-6 and abs(c["pnl_stress"] - (side * gross - 64.70)) < 1e-6 and r["side"] == -side
            assert abs(r["pnl"] - (-side * gross - 39.70)) < 1e-6 and abs(c["es_move"] - (1000.0 if i == 86 else -500.0)) < 1e-9
    assert abs(cell_trades(Sh, sg, 0).set_index("i").loc[86, "pnl"] - 360.30) < 1e-6 and abs(cell_trades(Sh, sg, 0).set_index("i").loc[87, "pnl"] - 1160.30) < 1e-6
    assert abs(cell_trades(Sh, sg, 0, mirror=True).set_index("i").loc[86, "pnl"] + 439.70) < 1e-6
    assert not sg["ok"][:80].any() and sg["ok"][80:].all() and np.isnan(sg["scale"][:80]).all(), "no trade before the 81st session (40 for beta + 40 defined s)"
    print("ok 4  hand-priced sessions: CONT +$360.30 (long NQ +100 pt, short 1.6 ES +20 pt, cost $39.70) and +$1,160.30 (the short side), REV -$439.70 / -$1,239.70, stress cost -$25 more;")
    print("      first possible trade is session 81 (index 80)")


def smoke(*a):
    global OUT, BOOK, CHECK_BOOK
    root = os.path.abspath(a[0] if a else os.path.join(tempfile.gettempdir(), "r10_spread_smoke"))
    assert "smoke" in os.path.basename(root).lower() and not os.path.normcase(root).startswith(os.path.normcase(r"C:\EdgeLog")), "smoke needs its own scratch folder (name contains 'smoke'), never a real cache"
    keep = (OUT, BOOK, CHECK_BOOK, dict(RULES))
    data = data_mod()
    keep_data = (data.find_master, data.load_master_arrays)
    real_load = load
    recap = []
    os.makedirs(root, exist_ok=True)

    def fresh(name):
        p = os.path.join(root, name)
        shutil.rmtree(p, ignore_errors=True)
        os.makedirs(p)
        return p

    def clone(src, name):
        p = os.path.join(root, name)
        shutil.rmtree(p, ignore_errors=True)
        shutil.copytree(src, p)
        return p

    def cap(fn, *args):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            r = fn(*args)
        return r, buf.getvalue()
    try:
        print("=" * 130 + "\nSMOKE TEST - SYNTHETIC masters and a synthetic book: every number below is MEANINGLESS, only the code paths matter\n" + "=" * 130)
        selftest(root)
        recap.append("4  hand-priced sessions -> known dollars: CONT +360.30 / +1,160.30, REV -439.70 / -1,239.70, stress -25 more; first trade = session 81")
        recap.append("6  hand-made daily series -> net, dd, years, ROC@30k, Sortino, pf, t, years_pos; the rules at their boundaries; the book convention")
        w1 = World(post_seed=1)
        w1.install()
        r4 = fresh("r4")
        rng = np.random.default_rng(5)                                                       # a synthetic BOOK #463 (the real files are never touched)
        idx = pd.bdate_range("2010-06-07", "2026-06-30").union(pd.DatetimeIndex(["2016-07-02", "2018-03-03", "2025-06-29", "2026-06-27"]))   # weekend rows, like the real file
        cols = {}
        for j in range(4):
            cl = rng.normal(10, 150, len(idx))
            cols[f"L{j}_close"], cols[f"L{j}_mtm"] = cl, cl + rng.normal(0, 30, len(idx))
        bk = pd.DataFrame(cols, index=idx)
        bk["close"], bk["mtm"] = bk[[c for c in bk if c.endswith("_close")]].sum(axis=1), bk[[c for c in bk if c.endswith("_mtm")]].sum(axis=1)
        bk.index.name = "date"
        bk.to_csv(os.path.join(r4, "book463_daily.csv"))
        kb = rng.random(len(idx)) < 0.3
        pd.DataFrame({"date": idx[kb], "pnl": bk["close"].to_numpy()[kb], "strategy": "FAKE"}).to_csv(os.path.join(r4, "book463_trades.csv"), index=False)
        BOOK = os.path.join(r4, "book463_daily.csv")
        # ---- loader, sessions, roll guard
        a = data.load_master_arrays(data.find_master("NQ", "5m", "rth", SRC_RAW), A_D0, "2025-06-29")
        assert pd.DatetimeIndex(a["index"]).max() >= LB0.tz_localize("US/Eastern"), "the leaky stand-in must hand over later bars, so load()'s own cut is what is tested"
        L = load(LB0)
        for key, (df, m) in L.items():
            assert df.index.max() < LB0.tz_localize("US/Eastern") and m["id"] == IDS[(key[0], SRC_RAW if key[1] == "raw" else SRC_ADJ)]
        w1.leaky = False                                                                      # a master that honours date_to (like the real loader) must give the SAME bars
        L2 = load(LB0)
        Lx = load(TS("2025-06-27"))                                                           # cut at a Friday midnight: Thursday's last bar (15:55) must survive (d1 = the whole day)
        w1.leaky = True
        Lx2 = load(TS("2025-06-27"))
        assert all(L2[k][0].equals(L[k][0]) and Lx[k][0].equals(Lx2[k][0]) for k in L), "load() must not depend on whether the master slices at date_to"
        assert all(Lx[k][0].index.max() == TS("2025-06-26 15:55", tz="US/Eastern") for k in Lx), "d1 must keep the last day whole"
        S = build_sessions(L)
        pre = pd.DatetimeIndex([d for d in w1.days if d < LB0])
        exp = pd.DatetimeIndex([d for d in pre if d not in w1.partial and d not in w1.guard])
        assert S["dates"].equals(exp), "eligible = every pre-cut session minus the planted partial and roll-guard sessions (the 5e-7 jitter stays)"
        assert S["n_guard"] == len([d for d in w1.guard if d < LB0]) == 4 and set(S["guard_dates"]) == {d for d in w1.guard if d < LB0}
        assert S["n_complete"] == len(exp) + 4 and S["n_any"] == len(pre) and S["n_any"] - S["n_complete"] == len([d for d in w1.partial if d < LB0]) == 6
        assert S["oN"].shape == (len(exp), NB) and np.isfinite(S["cE"]).all() and S["dates"].max() < LB0
        assert all(np.array_equal(S["oN"][i], w1.px[d][0]) and np.array_equal(S["cN"][i], w1.px[d][1]) and np.array_equal(S["oE"][i], w1.px[d][2]) and np.array_equal(S["cE"][i], w1.px[d][3])
                   for i, d in enumerate(S["dates"])), "the session arrays must be the RAW contract prices of the right market, never the roll-corrected twins"
        real_find, bad_id = data.find_master, []
        data.find_master = lambda *a_, **k_: {**real_find(*a_, **k_), "id": 999}
        try:
            load(LB0)
        except AssertionError as e_:
            bad_id.append(str(e_))
        finally:
            data.find_master = real_find
        assert bad_id and "registry id 999" in bad_id[0], "a master with another registry id must be refused"
        ok_cnt, txt = cap(count)
        assert ok_cnt["eligible"] == len(exp) and ok_cnt["guard"] == 4 and ok_cnt["early"] + ok_cnt["wf"] == len(exp) and "ELIGIBLE sessions" in txt
        print(f"ok    loader + sessions: {len(pre)} synthetic sessions before the cut -> {len(exp)} eligible; 6 partial (a missing NQ-raw / ES-adj / NQ-adj bar, a duplicated timestamp with a")
        print(f"      slot missing, a pure duplicate, an off-grid bar) and 4 roll-guard sessions (NQ both / NQ open / ES close / a 2e-6 jitter) dropped, a 5e-7 jitter kept; count says EARLY {ok_cnt['early']}, WF {ok_cnt['wf']}, guard {ok_cnt['guard']}")
        arrs = (S["oN"], S["cN"], S["oE"], S["cE"])
        sig = signal(*arrs)
        n = len(exp)
        # ---- 1. beta tracks beta_true
        bt = np.array([w1.beta_true[d] for d in S["dates"]])
        m = np.isfinite(sig["beta"])
        err = np.abs(sig["beta"][m] - bt[m])
        assert m.sum() == n - 40 and np.median(err) < 0.05, (m.sum(), np.median(err))
        print(f"ok 1  beta: {m.sum()} defined estimates, median |beta - beta_true| {np.median(err):.4f}, 95th pct {np.percentile(err, 95):.4f} (true beta moves 1.15 -> 1.35 half way)")
        recap.append(f"1  beta tracks beta_true: median |error| {np.median(err):.4f} over {m.sum()} sessions")
        # ---- 2. causality
        keys = ("beta", "s", "scale", "h", "gross_plus", "cost", "add", "es_move")
        same = lambda x, y: np.array_equal(x, y, equal_nan=True)
        pr = np.random.default_rng(99)

        def jig(arr, i, lo, hi):
            arr = arr.copy()
            arr[i, lo:hi] *= 1.0 + pr.normal(0, 0.01, hi - lo)
            return arr
        tested = (45, 80, 130, 260, n // 2, n - 2, n - 1)
        for i in tested:
            late = signal(*[jig(x, i, 12, NB) for x in arrs])                                  # session i's bars after 10:25 (bar 12 on)
            for key in ("s", "beta", "scale", "h"):
                assert same(late[key][i], sig[key][i]), (i, key)
            for key in keys:
                assert same(late[key][:i], sig[key][:i]), (i, key, "late bars, earlier sessions")
            full = signal(*[jig(x, i, 0, NB) for x in arrs])                                   # ANY bar of session i
            assert same(full["beta"][i], sig["beta"][i]) and same(full["scale"][i], sig["scale"][i]), i
            for key in keys:
                assert same(full[key][:i], sig[key][:i]), (i, key)                              # nothing earlier moves
            first = signal(*[jig(x, i, 0, 12) for x in arrs])                                  # power: the first hour DOES move s_i, and a later session's beta moves too
            assert not same(first["s"][i], sig["s"][i]) and (i + 1 >= n or not same(full["beta"][i + 1], sig["beta"][i + 1])), i
            cut = signal(*[x[:i + 1] for x in arrs])                                           # truncation: the future is not needed
            for key in keys:
                assert same(cut[key], sig[key][:i + 1]), (i, key, "truncation")
        print(f"ok 2  causality at {len(tested)} sessions: perturbing bars 12..77 of session i leaves s, beta, scale, h of i unchanged; perturbing any bar leaves beta_i and scale_i")
        print("      unchanged and nothing for sessions < i; truncating the history after i changes nothing up to i (and the first hour does move s_i, a later beta moves: the test has power)")
        recap.append(f"2  causality at {len(tested)} sessions: late bars, any bar, earlier sessions, truncation")
        # ---- 3. brute force
        bf = brute(*arrs)

        def close(py, vec):
            for i, v in enumerate(py):
                assert (v is None and math.isnan(vec[i])) or (v is not None and abs(v - vec[i]) < 1e-9), (i, v, vec[i])
        for key in ("beta", "s", "scale", "h", "gross_plus", "cost", "add"):
            close(bf[key], sig[key])
        nt = 0
        for (role, k), rows in bf["trades"].items():
            h_ = cell_trades(S, sig, k, mirror=role == "REV")
            assert [r_[0] for r_ in rows] == h_["i"].tolist(), (role, k)
            for r_, (_, hr) in zip(rows, h_.iterrows()):
                assert r_[1] == hr["side"] and abs(r_[2] - hr["pnl"]) < 1e-9 and abs(r_[3] - hr["pnl_stress"]) < 1e-9
            nt += len(rows)
        # the null: its first three reps recomputed in plain Python from the same coin stream
        nl = null_dist(S, sig)
        crng = np.random.default_rng(SEED)
        wfi = [i for i, d in enumerate(S["dates"]) if WF0 <= d < LB0]
        for rep_ in range(3):
            coin = crng.choice([-1.0, 1.0], size=n)
            best = None
            for k in KS:
                x = [coin[i] * bf["gross_plus"][i] - bf["cost"][i] for i in wfi if bf["h"][i] is not None and bf["scale"][i] is not None and bf["s"][i] != 0 and abs(bf["s"][i]) >= k * bf["scale"][i]]
                mu = sum(x) / len(x)
                sd = math.sqrt(sum((v - mu) ** 2 for v in x) / (len(x) - 1))
                best = mu / (sd / math.sqrt(len(x))) if best is None else max(best, mu / (sd / math.sqrt(len(x))))
            assert abs(best - nl[rep_]) < 1e-9, (rep_, best, nl[rep_])
        assert np.array_equal(nl, null_dist(S, sig), equal_nan=True) and np.isfinite(nl).all()
        print(f"ok 3  brute force: a plain-Python loop over all {n} sessions matches beta, s, scale, h, gross_plus, cost, stress add and all 6 cells' {nt} trades to 1e-9;")
        print("      the null's first 3 reps (max over 3 cells of the WF per-trade t, one coin per session) recomputed independently match; the null is deterministic")
        recap.append(f"3  brute force over {n} sessions: beta, s, scale, h, gross_plus, cost, add and {nt} trades match to 1e-9; the null's first 3 reps match")
        # ---- 5. the Stage A cut: nothing on/after 2025-06-30 reaches Stage A, even though the stand-in hands over later bars
        w2 = World(post_seed=2)
        assert any(not np.array_equal(w1.tab[k][1][len(w1.tab[k][1]) - 500:], w2.tab[k][1][len(w2.tab[k][1]) - 500:]) for k in IDS) and all(
            np.array_equal(w1.tab[k][1][:200], w2.tab[k][1][:200]) for k in IDS), "the two worlds must differ ONLY after the cut"
        OUT = fresh("cut1")
        R1 = stage_a_core()
        w2.install()
        R2 = stage_a_core()
        w1.install()
        pub = lambda R: json.dumps({k: R[k] for k in ("cells", "counts", "masters", "p95", "median", "passes", "rep", "top10_k0")} | {"null": R["null"].tolist(), "dates": [str(d) for d in R["S"]["dates"]]}, default=js, sort_keys=True)
        assert pub(R1) == pub(R2), "Stage A changed when only post-cut bars changed: a leak"
        assert R1["p95"] == float(np.percentile(R1["null"], 95)) and R1["median"] == float(np.median(R1["null"])) and len(R1["null"]) == NREP
        assert R1["S"]["dates"].max() < LB0 and all(len(t) == 0 or t["date"].max() < LB0 for t in R1["trs"].values())
        assert all(len(t) == 0 or t["date"].max() < LB0 for t in R1["trs"].values()) and R1["counts"]["last"] < LB0
        print("ok 5  Stage A cut: the stand-in hands over bars through 2026-08, yet the loaded arrays, sessions and every trade end before the lockbox, and Stage A's cells / null / passes /")
        print("      reported numbers are IDENTICAL to the last digit when every post-cut bar is replaced by a different random world")
        recap.append("5  Stage A cut: arrays, sessions, trades all end before the lockbox; results identical when every post-cut bar changes")
        # ---- 7. Stage A end to end: book check ON (synthetic book cannot reproduce 93.81) -> A2 NOT judged; none pass; then book check OFF -> A2 runs
        CHECK_BOOK = True
        OUT = fresh("A_checkon")
        out_on, txt = cap(stage_a)
        assert out_on["passes"] and "A2 NOT judged" in txt and out_on["A2"]["pass"] is False and out_on["A2"]["error"] == "book check mismatch"
        print("ok 7a Stage A with the book check ON: " + [ln for ln in txt.splitlines() if ln.startswith("A2 NOT judged")][0])
        keep_rules = dict(RULES)
        RULES["roc30"] = 1e9
        OUT = fresh("A_none")
        out_none, txt = cap(stage_a)
        assert out_none["passes"] == [] and out_none["A2"] is None and "Stage A passes: none" in txt
        RULES.update(keep_rules)
        print("ok 7b Stage A with an unreachable ROC bar: no passes, A2 not run, " + txt.strip().splitlines()[-1])
        real_judge = judge
        globals()["judge"] = lambda r, p95: ({}, True)                                          # every rule waived: the reversal control must STILL never be a pass route
        try:
            OUT = fresh("A_judgeall")
            Rj = stage_a_core()
        finally:
            globals()["judge"] = real_judge
        assert Rj["passes"] == [f"k{k}|CONT" for k in KS] and not any(Rj["cells"][f"k{k}|REV"]["PASS"] for k in KS)
        CHECK_BOOK = False
        OUT = fresh("A_pass")
        out_a, txt = cap(stage_a)
        print(txt.rstrip())
        for f in ("stageA.json", "stageA_table.csv", "null.csv") + tuple(f"trades_k{k}_{r_}.csv" for k in KS for r_ in ("cont", "rev")):
            assert os.path.exists(os.path.join(OUT, f)), f
        ja = json.loads(rd(os.path.join(OUT, "stageA.json")))
        assert ja["prereg_sha256_lf"] == sha_lf(PREREG) and ja["harness_sha256"] == sha_raw(os.path.abspath(__file__)) and ja["harness_sha256_lf"] == sha_lf(os.path.abspath(__file__)) and ja["rules"]["thresholds"] == RULES and set(ja["rules"]["text"]) == set(RULE_TEXT)
        assert set(ja["null"]) >= {"p95", "median", "reps", "seed"} and set(ja["masters"]) == {f"{i}|{t}" for i in ("NQ", "ES") for t in ("raw", "adj")} and ja["masters"]["NQ|raw"]["id"] == 37
        assert set(ja["cells"]) == {f"k{k}|{r_}" for k in KS for r_ in ("CONT", "REV")} and ja["passes"] and ja["A2"]["pass"] and ja["A2"]["cell"] in ja["passes"] and ja["A2"]["c"] in (1, 2, 3)
        assert all(not ja["cells"][f"k{k}|REV"]["PASS"] for k in KS), "the reversal mirror is never a pass route"
        pick = max(ja["passes"], key=lambda p: ja["cells"][p]["WF"]["roc30"])
        assert ja["A2"]["cell"] == pick and ja["A2"]["c"] == max((1, 2, 3), key=lambda c: ja["A2"]["by_c"][str(c)]["roc30"])
        kk0 = int(ja["A2"]["cell"].split("|")[0][1:])                                           # A2 arithmetic: the book at x c = the book + c x the picked cell's WF net
        leg_t = pd.read_csv(os.path.join(OUT, f"trades_k{kk0}_cont.csv"), parse_dates=["date"])
        legwf = leg_t[(leg_t["date"] >= WF0) & (leg_t["date"] < LB0)]["pnl"].sum()
        assert all(abs(ja["A2"]["by_c"][str(c)]["net"] - (ja["A2"]["book_wf"]["net"] + c * legwf)) < 1e-6 for c in (1, 2, 3))
        t0_ = pd.read_csv(os.path.join(OUT, "trades_k0_cont.csv"), parse_dates=["date"])
        w0_ = t0_[(t0_["date"] >= WF0) & (t0_["date"] < LB0)]
        assert [round(p_, 6) for _, p_ in ja["reported"]["top10_k0"]] == sorted((round(v, 6) for v in w0_["pnl"]), key=abs, reverse=True)[:10]
        def ind(m):                                                                              # plain-Python book numbers: net, max drawdown (peak from 0), years, ROC@30k, Sortino
            v = [float(x_) for x_ in m.values]
            cum = peak = dd_ = 0.0
            for x_ in v:
                cum += x_
                peak = max(peak, cum)
                dd_ = max(dd_, peak - cum)
            yrs_ = (m.index[-1] - m.index[0]).days / 365.25
            return sum(v), dd_, yrs_, 30.0 * (sum(v) / yrs_) / dd_, (sum(v) / len(v)) / math.sqrt(sum(min(x_, 0.0) ** 2 for x_ in v) / len(v)) * math.sqrt(252)
        bw = bk.loc[(bk.index >= WF0) & (bk.index < LB0), "mtm"]
        bf_ = ind(bw)
        got = ja["A2"]["book_wf"]
        assert all(abs(a_ - g_) < 1e-6 for a_, g_ in zip(bf_, (got["net"], got["dd_daily"], got["years"], got["roc30"], got["sortino"]))) and got["n"] == len(bw)
        legm = leg_t[(leg_t["date"] >= WF0) & (leg_t["date"] < LB0)].set_index("date")["pnl"]
        for c in (1, 2, 3):
            m2 = bw.reindex(bw.index.union(legm.index)).fillna(0.0)
            m2.loc[legm.index] += c * legm.to_numpy()
            gc = ja["A2"]["by_c"][str(c)]
            assert all(abs(a_ - g_) < 1e-6 for a_, g_ in zip(ind(m2), (gc["net"], gc["dd_daily"], gc["years"], gc["roc30"], gc["sortino"]))), c
        for k in KS:                                                                             # the reported numbers: ES-move correlation, mean beta / h, WF daily correlation with the book legs
            tw = pd.read_csv(os.path.join(OUT, f"trades_k{k}_cont.csv"), parse_dates=["date"])
            tw = tw[(tw["date"] >= WF0) & (tw["date"] < LB0)]
            assert np.allclose(tw["es_move"], 50.0 * (S["cE"][tw["i"], 76] - S["oE"][tw["i"], 12])), "es_move = 50 x (ES close of the 15:50 bar - ES open of the 10:30 bar)"
            rr = ja["reported"]
            assert abs(np.corrcoef(tw["pnl"], tw["es_move"])[0, 1] - rr["es_corr"][f"k{k}|CONT"]["unsigned"]) < 1e-9
            assert abs(np.corrcoef(tw["pnl"], tw["side"] * tw["es_move"])[0, 1] - rr["es_corr"][f"k{k}|CONT"]["side_signed"]) < 1e-9
            assert abs(tw["beta"].mean() - rr["mean_beta"][f"k{k}|CONT"]) < 1e-9 and abs(tw["h"].mean() - rr["mean_h"][f"k{k}|CONT"]) < 1e-9
            wf_days = pd.DatetimeIndex([d_ for d_ in S["dates"] if WF0 <= d_ < LB0])
            ix_ = bw.index.union(wf_days)
            dly = pd.Series(0.0, index=ix_)
            dly.loc[tw["date"]] = tw["pnl"].to_numpy()
            for col in BOOK_COLS:
                e_ = np.corrcoef(dly.to_numpy(), bk.loc[(bk.index >= WF0) & (bk.index < LB0), col].reindex(ix_).fillna(0.0).to_numpy())[0, 1]
                assert abs(e_ - rr["book_corr"][f"k{k}|CONT"][col]) < 1e-9, (k, col)
        blob = rd(os.path.join(OUT, "stageA.json")) + rd(os.path.join(OUT, "stageA_table.csv")) + txt
        assert all(d < "2025-06-30" for d in re.findall(r"\b20\d\d-\d\d-\d\d\b", blob)), "Stage A printed or saved a lockbox date"
        tcsv = [pd.read_csv(os.path.join(OUT, f"trades_k{k}_{r_}.csv"), parse_dates=["date"]) for k in KS for r_ in ("cont", "rev")]
        assert all(t["date"].max() < LB0 for t in tcsv) and len(pd.read_csv(os.path.join(OUT, "null.csv"))) == NREP
        print(f"ok 7c Stage A end to end (book check OFF): files written (stageA.json with rules, null, cells, passes, prereg LF sha256 {ja['prereg_sha256_lf'][:12]}.., harness sha256 {ja['harness_sha256'][:12]}..,")
        print(f"      stageA_table.csv, 6 trade CSVs, null.csv); A2 picked {ja['A2']['cell']} at x{ja['A2']['c']}; no date on/after the cut anywhere in the files or the print; REV rows are controls")
        recap.append("7  Stage A end to end: check ON -> 'A2 NOT judged'; unreachable bar -> no passes; check OFF -> files written, A2 picks the best pass and c")
        # ---- 8. Stage B: every refusal leaves NO flag; with the checks waived it runs once, writes the flag, and a second call refuses
        flagp = lambda o: os.path.join(o, "stageB_READ.flag")
        OUT = fresh("B_nofile")
        r_, txt = cap(stage_b)
        assert r_["status"] == "refused" and "no stageA.json" in txt and not os.path.exists(flagp(OUT)) and not os.path.exists(os.path.join(OUT, "stageB.json"))
        OUT = os.path.join(root, "A_checkon")                                                    # A2 on file but not passed
        r_, txt = cap(stage_b)
        assert r_["status"] == "refused" and "no Stage A2 pass" in txt and not os.path.exists(flagp(OUT))
        OUT = os.path.join(root, "A_none")                                                       # A2 is null
        r_, txt = cap(stage_b)
        assert r_["status"] == "refused" and "no Stage A2 pass" in txt and not os.path.exists(flagp(OUT))
        src = os.path.join(root, "A_pass")
        OUT = clone(src, "B_flagged")                                                            # flag already present
        wr(flagp(OUT), "earlier read")
        r_, txt = cap(stage_b)
        assert r_["status"] == "refused" and "already read" in txt and rd(flagp(OUT)) == "earlier read" and not os.path.exists(os.path.join(OUT, "stageB.json"))
        CHECK_BOOK = True
        OUT = clone(src, "B_mismatch")                                                           # the lockbox data loads, #463's LB numbers do not reproduce: refused, no flag
        r_, txt = cap(stage_b)
        assert r_["status"] == "refused" and "does not reproduce #463's LB numbers" in txt and "lockbox NOT read" in txt and not os.path.exists(flagp(OUT)) and not os.path.exists(os.path.join(OUT, "stageB.json"))
        assert "leg LB" not in txt and "Stage B:" not in txt, "nothing from the lockbox may be printed before the flag"
        CHECK_BOOK = False
        OUT = clone(src, "B_nolb")                                                               # the load holds no lockbox session (cut moved back to the first LB day): refused, no flag
        keep_lbx, globals()["LBX"] = LBX, LB0
        try:
            r_, txt = cap(stage_b)
        finally:
            globals()["LBX"] = keep_lbx
        assert r_["status"] == "refused" and "no lockbox sessions" in txt and not os.path.exists(flagp(OUT))
        OUT = clone(src, "B_tamper")                                                             # Stage A's trade file no longer matches the lockbox load's pre-lockbox tail
        kk = int(ja["A2"]["cell"].split("|")[0][1:])
        tf = os.path.join(OUT, f"trades_k{kk}_cont.csv")
        tt = pd.read_csv(tf)
        tt.loc[len(tt) - 1, "pnl"] += 1.0
        tt.to_csv(tf, index=False)
        r_, txt = cap(stage_b)
        assert r_["status"] == "refused" and "differs from Stage A's trade file" in txt and not os.path.exists(flagp(OUT))
        OUT = clone(src, "B_loadfail")                                                           # the lockbox load itself fails: no flag
        globals()["load"] = lambda *x, **y: (_ for _ in ()).throw(RuntimeError("simulated: the lockbox data cannot be loaded"))
        try:
            cap(stage_b)
            raise AssertionError("a failed lockbox load must stop Stage B")
        except RuntimeError:
            pass
        finally:
            globals()["load"] = real_load
        assert not os.path.exists(flagp(OUT))
        OUT = clone(src, "B_run")                                                                # the one read
        r_, txt = cap(stage_b)
        print(txt.rstrip())
        assert r_["status"] == "read" and os.path.exists(flagp(OUT)) and os.path.exists(os.path.join(OUT, "stageB.json")) and os.path.exists(os.path.join(OUT, "stageB_trades.csv"))
        jb = json.loads(rd(os.path.join(OUT, "stageB.json")))
        assert jb["cell"] == ja["A2"]["cell"] and jb["c"] == ja["A2"]["c"] and jb["leg_n"] >= RULES["b_n"] and jb["pass"] is True and jb["tail_check"].endswith("identical to Stage A's file")
        btd = pd.read_csv(os.path.join(r4, "book463_trades.csv"), parse_dates=["date"])
        bl_max = float(btd[(btd["date"] >= LB0) & (btd["date"] <= LB1)]["pnl"].max())
        lbt = pd.read_csv(os.path.join(OUT, "stageB_trades.csv"), parse_dates=["date"])
        assert abs(jb["biggest_book_trade"] - bl_max) < 1e-9 and abs(jb["biggest_single_trade"] - max(bl_max, lbt["pnl"].max() * jb["c"])) < 1e-9 and abs(jb["leg_net"] - lbt["pnl"].sum()) < 1e-9
        bl_ = bk.loc[(bk.index >= LB0) & (bk.index <= LB1), "mtm"]
        got = jb["book_lb_alone"]
        assert all(abs(a_ - g_) < 1e-6 for a_, g_ in zip(ind(bl_), (got["net"], got["dd_daily"], got["years"], got["roc30"], got["sortino"]))) and got["n"] == len(bl_)
        lm = lbt.set_index("date")["pnl"]
        m3 = bl_.reindex(bl_.index.union(lm.index)).fillna(0.0)
        m3.loc[lm.index] += jb["c"] * lm.to_numpy()
        got = jb["B"]
        assert all(abs(a_ - g_) < 1e-6 for a_, g_ in zip(ind(m3), (got["net"], got["dd_daily"], got["years"], got["roc30"], got["sortino"])))
        assert lbt["date"].min() >= LB0 and lbt["date"].max() <= LB1 and (lbt["date"] == LB0).any() and (lbt["date"] == LB1).any() and len(lbt) == jb["leg_n"], "LB = 2025-06-30 .. 2026-06-30 inclusive"
        before = rd(os.path.join(OUT, "stageB.json"))
        r_, txt = cap(stage_b)
        assert r_["status"] == "refused" and "already read" in txt and rd(os.path.join(OUT, "stageB.json")) == before
        keep_a = rd(os.path.join(OUT, "stageA.json"))
        assert stage_a() is None and rd(os.path.join(OUT, "stageA.json")) == keep_a, "Stage A must not overwrite its record once the lockbox has been read"        # OUT = B_run: its flag is down
        OUT = clone(src, "B_c3")                                                                 # a frozen c of 3 (the pick above is x1): the leg's LB trades enter the book at x3
        jj = json.loads(rd(os.path.join(OUT, "stageA.json")))
        jj["A2"]["c"] = 3
        wr(os.path.join(OUT, "stageA.json"), json.dumps(jj, default=js))
        r_, txt = cap(stage_b)
        j3 = json.loads(rd(os.path.join(OUT, "stageB.json")))
        lt3 = pd.read_csv(os.path.join(OUT, "stageB_trades.csv"))
        assert r_["status"] == "read" and j3["c"] == 3 and abs(j3["B"]["net"] - (j3["book_lb_alone"]["net"] + 3 * j3["leg_net"])) < 1e-6 and abs(j3["leg_net_x_c"] - 3 * j3["leg_net"]) < 1e-6
        assert abs(j3["biggest_leg_trade_x_c"] - 3 * lt3["pnl"].max()) < 1e-6 and j3["leg_n"] == jb["leg_n"] and abs(j3["leg_net"] - jb["leg_net"]) < 1e-9
        assert abs(j3["biggest_single_trade"] - max(bl_max, 3 * lt3["pnl"].max())) < 1e-9
        for tag, extra_rows in (("lo", [("2025-06-27", 9e6), ("2025-06-30", 1e6)]), ("hi", [("2026-06-30", 1e6), ("2026-07-01", 9e6)])):      # the book's biggest LB trade sits ON a window edge; 9e6 just outside it
            r4x = os.path.join(root, "r4_big" + tag)
            shutil.rmtree(r4x, ignore_errors=True)
            shutil.copytree(r4, r4x)
            tb = pd.concat([pd.read_csv(os.path.join(r4x, "book463_trades.csv")), pd.DataFrame({"date": [x_[0] for x_ in extra_rows], "pnl": [x_[1] for x_ in extra_rows], "strategy": "FAKE"})], ignore_index=True)
            tb.to_csv(os.path.join(r4x, "book463_trades.csv"), index=False)
            BOOK = os.path.join(r4x, "book463_daily.csv")
            OUT = clone(src, "B_big" + tag)
            r_, txt = cap(stage_b)
            jx = json.loads(rd(os.path.join(OUT, "stageB.json")))
            assert r_["status"] == "read" and jx["biggest_book_trade"] == 1e6 and jx["biggest_single_trade"] == 1e6 and jx["checks"]["net_ex_big"] is False and jx["pass"] is False, (tag, jx["biggest_book_trade"])
        for gone in ("book463_trades.csv", "book463_daily.csv"):                                  # a missing book file refuses before the flag (it must not burn the read)
            r4m = os.path.join(root, "r4_no_" + gone[:-4])
            shutil.rmtree(r4m, ignore_errors=True)
            shutil.copytree(r4, r4m)
            os.remove(os.path.join(r4m, gone))
            BOOK = os.path.join(r4m, "book463_daily.csv")
            OUT = clone(src, "B_no_" + gone[:-4])
            r_, txt = cap(stage_b)
            assert r_["status"] == "refused" and gone in txt and "lockbox NOT read" in txt and not os.path.exists(flagp(OUT)), (gone, txt)
        BOOK = os.path.join(r4, "book463_daily.csv")
        OUT = clone(src, "B_fail")                                                               # the FAIL path: an unreachable LB ROC bar
        RULES["b_roc"] = 1e9
        r_, txt = cap(stage_b)
        RULES.update(keep_rules)
        assert r_["status"] == "read" and r_["pass"] is False and "roc" in txt and os.path.exists(flagp(OUT))
        print("ok 8  Stage B, ten refusals / failures and none writes a flag: no stageA.json / A2 not passed / A2 null / flag present (the old flag stays) / #463 LB mismatch /")
        print("      a changed Stage A trade file / a failed data load / no lockbox session in the load / missing book trades file / missing book daily file; nothing of the lockbox is")
        print("      printed before the flag; checks waived: it runs ONCE (flag, stageB.json, LB trades 2025-06-30 .. 2026-06-30 inclusive), a second call refuses, Stage A will not overwrite")
        print("      its record afterwards; a frozen c of 3 adds 3x the leg's LB P&L; the book's biggest LB trade counts on both window edges and not outside; an unreachable bar gives FAIL")
        recap.append("8  Stage B: ten refusals / failures, none leaves a flag; checks waived -> one read (flag, stageB.json, LB trades 2025-06-30 .. 2026-06-30 inclusive), second call refuses; c = 3; FAIL path")
        print("=" * 130 + "\nSMOKE RECAP - every pre-registered assertion group passed (synthetic world, synthetic book):")
        for ln in sorted(recap):
            print("  " + ln)
        print("SMOKE OK - nothing above says anything about NQ, ES or BOOK #463\n" + "=" * 130)
    finally:
        OUT, BOOK, CHECK_BOOK = keep[0], keep[1], keep[2]
        RULES.clear()
        RULES.update(keep[3])
        data.find_master, data.load_master_arrays = keep_data
        globals()["load"] = real_load


if __name__ == "__main__":
    cmd = sys.argv[1:2]
    if cmd == ["smoke"]:
        smoke(*sys.argv[2:])
    elif cmd == ["A"]:
        stage_a()
    elif cmd == ["B"]:
        stage_b()
    elif cmd == ["count"]:
        count()
    else:
        print("usage: r10_spread.py count | A | B | smoke DIR")
