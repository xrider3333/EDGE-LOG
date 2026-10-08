"""XSML r1 - a learned model as the SIGNAL on the US stock cross-section (walk-forward only; nothing after 2025-06-29).
Pre-registration: docs/PREREG_xsml_r1_2026-10-05.md (+ addendum 1, MANAGER #63; addendum 2, MANAGER review #64).

Cells: A PATTERN (weekly ranking model on price/volume characteristics), B STATARB (daily PCA residual + OU s-score),
C CRASH (monthly crash-probability classifier, beta-neutral). Each against its raw twin and a matched-risk shuffle.

    python tools/xsml_r1.py power     (step 1: shuffle nulls + #463 drawdown weeks; no cell or twin P&L read)
    python tools/xsml_r1.py power2    (step 1b, review #64: B turnover + cost per year, C's DO null; no cell P&L)
    python tools/xsml_r1.py run       (step 2: cells + twins + bars, after POWER.txt / POWER2.txt are committed)
    (cwd = the shared checkout; EDGELOG_ROOT = it; XSML_CA = the corporate-actions file, required by `run`)
"""
import hashlib
import os
import sys
import time

import numpy as np
import pandas as pd

ROOT = os.environ.get("EDGELOG_ROOT") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))

CACHE = os.environ.get("EDGELOG_ALPACA_CACHE", r"C:\EdgeLog\alpaca_cache")
DAILY = os.path.join(CACHE, "siporb", "daily_split.parquet")
FLAGS = r"C:\EdgeLog\_research_cache\split_qa\siporb_split_flags_voltest.csv"
OUT = r"C:\EdgeLog\custom_ml\xsml_r1"
END = pd.Timestamp("2025-06-29")                     # the harness never loads a later row
WF0, WF1 = pd.Timestamp("2018-01-02"), END
N_UNI, N_SIDE, GROSS = 500, 50, 1_000_000.0          # per side
COST, COST_STRESS, BORROW = 5e-4, 10e-4, 0.01
SEED, N_SHUF = 20261005, 1000
HGB = dict(max_iter=300, learning_rate=0.05, max_leaf_nodes=31, min_samples_leaf=200, l2_regularization=1.0,
           early_stopping=False, random_state=SEED)
B_FACT, B_WIN, B_RES, B_KMAX = 15, 252, 60, np.exp(-1.0 / 30.0)   # AL 2010: kappa > 252/30
B_OPEN, B_CLOSE_L, B_CLOSE_S = 1.25, -0.50, 0.75
DELIST_GAP = 5                                       # last row more than 5 sessions before END = delisted


def log(msg):
    print(time.strftime("%H:%M:%S"), msg, flush=True)


# ------------------------------------------------------------------------------------------------ data
class Data:
    def __init__(self, ca_path=None):
        self.sha = hashlib.sha256(open(DAILY, "rb").read()).hexdigest()
        d = pd.read_parquet(DAILY, columns=["symbol", "date", "o", "h", "l", "c", "v"])
        d = d[d.date <= END]
        C = d.pivot(index="date", columns="symbol", values="c")
        V = d.pivot(index="date", columns="symbol", values="v").astype(float)
        self.dates = C.index
        T = len(self.dates)
        col = {s: i for i, s in enumerate(C.columns)}
        # split quarantine (registered): every flagged stock-day removes that symbol +/- 21 sessions
        fl = pd.read_csv(FLAGS, parse_dates=["day"])
        q = np.zeros(C.shape, bool)
        for s, day in zip(fl.symbol, fl.day):
            if s in col:
                j = self.dates.searchsorted(pd.Timestamp(day))
                q[max(0, j - 21): j + 22, col[s]] = True
        self.n_quarantined = int(q.any(axis=0).sum())
        # corporate actions (addendum 3): splits are CROSS-CHECKED against the flags only (the prices are split-
        # adjusted; quarantining every listed split would use the future - a coming reverse split marks a distressed
        # name weeks early). Spin-offs and stock dividends are not price-adjusted: their ex-date session is blanked for
        # that name (a position held into it exits at the prior close, P&L stops; RESMOM [D2] in spirit), for every
        # cell, twin and null alike.
        self.ca, self.ca_check = None, {}
        if ca_path:
            self.ca = load_ca(ca_path)
            ev = self.ca["splits"]
            ev = ev[ev.ex_date <= END]
            spl = ev[ev.type.isin(["forward_split", "reverse_split", "unit_split"])]
            fset = {(s_, pd.Timestamp(x)) for s_, x in zip(fl.symbol, fl.day)}
            near = sum(any((s_, x + pd.Timedelta(days=k)) in fset for k in range(-3, 4)) for s_, x in zip(spl.symbol, spl.ex_date))
            spin = ev[ev.type.isin(["spin_off", "stock_dividend"])]
            blank = 0
            for s_, x in zip(spin.symbol, spin.ex_date):
                if s_ in col:
                    j = self.dates.searchsorted(x)
                    if j < T and self.dates[j] == x:
                        q[j, col[s_]] = True
                        blank += 1
            self.ca_check = dict(splits_listed=int(len(spl)), splits_within_3_days_of_a_flag=int(near),
                                 flags=int(len(fl)), spin_or_stock_div_ex_dates_blanked=blank)
        self.ca_extra_splits = self.ca_check.get("spin_or_stock_div_ex_dates_blanked", 0)
        last_raw = C.notna().to_numpy()[::-1].argmax(axis=0)
        last_pos = T - 1 - last_raw
        C, V = C.mask(q), V.mask(q)
        # universe at each close: close >= $5, >= 260 sessions of history, top 500 by 20-day median dollar volume
        dv = C * V
        med = dv.rolling(20, min_periods=15).median()
        hist = C.notna().cumsum()
        elig = (C >= 5.0) & (hist >= 260) & med.notna()
        rk = med.where(elig).rank(axis=1, ascending=False, method="first")
        U = rk <= N_UNI
        keep = U.any(axis=0).to_numpy()
        self.syms = C.columns[keep]
        self.last_pos = last_pos[keep]
        self.delisted = self.last_pos < T - 1 - DELIST_GAP
        log(f"loaded {d.shape[0]:,} rows, {C.shape[1]:,} symbols, {T} sessions; ever in universe {len(self.syms):,}; "
            f"quarantined symbols {self.n_quarantined}; delisted (ever in universe) {int(self.delisted.sum())}")
        qk = pd.DataFrame(q, index=self.dates, columns=C.columns).reindex(columns=self.syms).to_numpy()

        def piv(k):
            return d.pivot(index="date", columns="symbol", values=k).reindex(columns=self.syms).mask(qk)
        self.O, self.H, self.L = piv("o"), piv("h"), piv("l")
        self.C, self.V = C.reindex(columns=self.syms), V.reindex(columns=self.syms)
        self.U = U.reindex(columns=self.syms).fillna(False).astype(bool)
        self.Un = self.U.to_numpy()
        self.dv = self.C * self.V
        self.r_cc = self.C / self.C.shift(1) - 1.0
        self.r_on = self.O / self.C.shift(1) - 1.0
        self.r_id = self.C / self.O - 1.0
        self.mkt = self.r_cc.where(self.U.shift(1, fill_value=False)).mean(axis=1).fillna(0.0)
        self.On, self.Cn = self.O.to_numpy(float), self.C.to_numpy(float)
        # cash dividends per share on their ex-date (same split basis as the prices), zero where unknown
        self.div = np.zeros((T, len(self.syms)))
        self.div_counts = {}
        if self.ca is not None:
            # declared (raw-basis) amount -> the split-adjusted basis of the prices: divide by F = raw open / split open
            # on the ex-date (STRATEGY-BEATING #67); a row whose name is not a column, whose ex-date is not a session
            # or whose F cannot be formed is not placed (counted)
            dv_ = self.ca["dividends"]
            dv_ = dv_[dv_.symbol.isin(set(self.syms)) & (dv_.ex_date <= END)]
            raw = pd.read_parquet(DAILY.replace("daily_split", "daily_raw"), columns=["symbol", "date", "o"])
            raw = raw[raw.symbol.isin(set(dv_.symbol))]
            spl = d[d.symbol.isin(set(dv_.symbol))][["symbol", "date", "o"]]
            m = dv_.merge(raw.rename(columns={"date": "ex_date", "o": "o_raw"}), on=["symbol", "ex_date"], how="left") \
                   .merge(spl.rename(columns={"date": "ex_date", "o": "o_split"}), on=["symbol", "ex_date"], how="left")
            F = m.o_raw / m.o_split
            ok = np.isfinite(F) & (F > 0)
            cj = {s_: i for i, s_ in enumerate(self.syms)}
            placed = 0
            for s_, x, a, f in zip(m.symbol[ok], m.ex_date[ok], m.amount_raw[ok], F[ok]):
                j = self.dates.searchsorted(x)
                if j < T and self.dates[j] == x:
                    self.div[j, cj[s_]] += float(a) / float(f)
                    placed += 1
            self.div[~np.isfinite(self.On)] = 0.0
            self.div_counts = dict(rows_in_universe=int(len(dv_)), placed=placed, no_split_factor=int((~ok).sum()),
                                   F_not_1=int((np.abs(F[ok] - 1.0) > 0.01).sum()))
        prevC = np.vstack([np.full((1, len(self.syms)), np.nan), self.Cn[:-1]])
        with np.errstate(invalid="ignore", divide="ignore"):
            self.div_yield_on = np.nan_to_num(self.div / prevC)   # added to the overnight return on the ex-date

    def pos(self, t):
        return int(self.dates.get_loc(t))


CA_EVENTS = ("forward_split", "reverse_split", "unit_split", "stock_dividend", "spin_off")


def load_ca(path):
    """The WIDE Alpaca corporate-actions file (MANAGER #68, sha256 pinned in addendum 3) -> {'dividends': symbol,
    ex_date, amount_raw (dollars per share AS DECLARED, raw basis); 'splits': symbol, ex_date, type for every split,
    unit split, stock dividend and spin-off (each quarantined like a split flag); 'sha': the file's sha256}."""
    sha = hashlib.sha256(open(path, "rb").read()).hexdigest()
    ca = pd.read_csv(path, low_memory=False)
    ca["ex_date"] = pd.to_datetime(ca["ex_date"], errors="coerce")
    ca = ca[ca["ex_date"].notna() & ca["symbol"].notna()].copy()
    ca["symbol"] = ca["symbol"].astype(str)
    dv = ca[ca["type"] == "cash_dividend"].copy()
    dv["amount_raw"] = pd.to_numeric(dv["rate"], errors="coerce")
    dv = dv[dv["amount_raw"] > 0][["symbol", "ex_date", "amount_raw"]]
    ev = ca[ca["type"].isin(CA_EVENTS)][["symbol", "ex_date", "type"]]
    return {"dividends": dv.reset_index(drop=True), "splits": ev.reset_index(drop=True), "sha": sha}


# ------------------------------------------------------------------------------------------------ features
def rolling_beta_ivol(D, w):
    m = D.mkt
    r = D.r_cc
    mr = r.rolling(w, min_periods=int(0.8 * w)).mean()
    mm = m.rolling(w, min_periods=int(0.8 * w)).mean()
    cov = (r.mul(m, axis=0)).rolling(w, min_periods=int(0.8 * w)).mean() - mr.mul(mm, axis=0)
    vm = (m * m).rolling(w, min_periods=int(0.8 * w)).mean() - mm * mm
    vr = (r * r).rolling(w, min_periods=int(0.8 * w)).mean() - mr * mr
    beta = cov.div(vm, axis=0)
    ivol = np.sqrt((vr - cov.pow(2).div(vm, axis=0)).clip(lower=0.0))
    return beta, ivol


def features_A(D):
    C, r = D.C, D.r_cc
    lon, lid = np.log1p(D.r_on), np.log1p(D.r_id)
    rng = (D.H - D.L)
    ibs = ((D.C - D.L) / rng.where(rng > 0)).fillna(0.5)
    return {
        "r1": r, "r5": C / C.shift(5) - 1, "r21": C / C.shift(21) - 1,
        "mom12": C.shift(21) / C.shift(252) - 1, "mom6": C.shift(21) / C.shift(126) - 1,
        "on5": lon.rolling(5).sum(), "on21": lon.rolling(21).sum(),
        "id5": lid.rolling(5).sum(), "id21": lid.rolling(21).sum(),
        "vol21": r.rolling(21).std(), "vol63": r.rolling(63).std(),
        "max21": r.rolling(21).max(), "min21": r.rolling(21).min(),
        "ibs": ibs, "ibs5": ibs.rolling(5).mean(),
        "dhi": C / C.rolling(252).max() - 1, "ldv": np.log(D.dv.rolling(21).mean()),
        "vratio": D.V.rolling(5).mean() / D.V.rolling(63).mean(),
        "amihud": (r.abs() / D.dv).rolling(21).mean(),
    }


def features_C(D):
    C, r = D.C, D.r_cc
    _, ivol63 = rolling_beta_ivol(D, 63)
    _, ivol21 = rolling_beta_ivol(D, 21)
    beta252, _ = rolling_beta_ivol(D, 252)
    return {
        "ivol21": ivol21, "ivol63": ivol63, "max21": r.rolling(21).max(), "skew63": r.rolling(63).skew(),
        "min21": r.rolling(21).min(), "dhi": C / C.rolling(252).max() - 1, "ldv": np.log(D.dv.rolling(21).mean()),
        "turn": D.V.rolling(21).mean() / D.V.rolling(252).mean(), "mom12": C.shift(21) / C.shift(252) - 1,
        "beta": beta252, "on21": np.log1p(D.r_on).rolling(21).sum(), "id21": np.log1p(D.r_id).rolling(21).sum(),
    }, beta252


def xs_rank(F, t, names):
    """Cross-sectional ranks in [-0.5, 0.5] at date t for `names` (NaN kept)."""
    X = np.column_stack([f.loc[t, names].to_numpy(float) for f in F.values()])
    out = np.full_like(X, np.nan)
    for k in range(X.shape[1]):
        v = X[:, k]
        ok = np.isfinite(v)
        if ok.sum() > 1:
            out[ok, k] = pd.Series(v[ok]).rank(pct=True).to_numpy() - 0.5
    return out


# ------------------------------------------------------------------------------------------------ calendars
def decision_dates(D, kind):
    s = pd.Series(D.dates, index=D.dates)
    if kind == "weekly":
        last = s.groupby(D.dates.to_period("W-FRI")).max()
    else:
        last = s.groupby(D.dates.to_period("M")).max()
    t = pd.DatetimeIndex(last.values)
    p = np.array([D.pos(x) for x in t])
    keep = p + 1 < len(D.dates)
    return t[keep]


# ------------------------------------------------------------------------------------------------ book P&L
class Acc:
    """Optional per-unit P&L collectors (name-periods, decision periods, per-symbol totals, short-leg daily)."""
    def __init__(self, T):
        self.name_periods, self.dec_periods, self.by_sym = [], [], {}
        self.short = np.zeros(T)


def periodic_book(D, books, cost=0.0, borrow=0.0, acc=None, delist=None):
    """books: list of (decision t, {sym_index: signed dollars}); each fills at t+1 OPEN and is held to the next
    book's fill (the last to END's close). Shares fixed at the fill; dividends paid to holders of record (ex-dates
    after the fill through the exit open); a name whose price goes missing exits at its last close, or - with
    delist='long0' / 'short0' / 'both0' - a DELISTED name (no row after it, more than 5 sessions before END) held long /
    short goes to zero the session after its last row. Returns the daily P&L Series (gross if cost = borrow = 0)."""
    T = len(D.dates)
    pnl = np.zeros(T)
    On, Cn, Dv = D.On, D.Cn, D.div
    fills = [D.pos(t) + 1 for t, _ in books]
    wf0 = D.dates.searchsorted(WF0)
    prev_sh = {}
    for k, (t, pos) in enumerate(books):
        f = fills[k]
        e = fills[k + 1] if k + 1 < len(books) else None
        j = np.array(list(pos.keys()), int)
        dol = np.array(list(pos.values()), float)
        o = On[f, j] if len(j) else np.array([])
        ok = np.isfinite(o) & (o > 0)
        j, dol, o = j[ok], dol[ok], o[ok]
        sh = dol / o
        tc = 0.0
        if cost:
            # turnover at the fill: new dollars vs the old shares valued at this open (a name that went missing
            # already exited at its last close and counts as 0 here - its exit cost is not charged; rare)
            new = dict(zip(j.tolist(), dol.tolist()))
            turn = 0.0
            for n in set(new) | set(prev_sh):
                old = prev_sh.get(n, 0.0) * On[f, n]
                turn += abs(new.get(n, 0.0) - (old if np.isfinite(old) else 0.0))
            tc = cost * turn
            pnl[f] -= tc
        prev_sh = dict(zip(j.tolist(), sh.tolist()))
        if not len(j):
            continue
        last = (e - 1) if e is not None else T - 1
        # marks: O_f, C_f, C_f+1 .. C_last, then O_e at day e
        path = np.vstack([On[f, j], Cn[f:last + 1, j]] + ([On[e, j][None, :]] if e is not None else []))
        alive = np.isfinite(path)
        path = pd.DataFrame(path).ffill().to_numpy()
        ch = np.diff(path, axis=0) * sh                        # rows: day f, f+1, ..., last, (e)
        days = np.array(list(range(f, last + 1)) + ([e] if e is not None else []))
        # dividends: ex-dates in (f, e] while the name still trades
        dv = Dv[days[1:], :][:, j] * sh * alive[2:2 + len(days) - 1] if len(days) > 1 else np.zeros((0, len(j)))
        if len(days) > 1:
            ch[1:] += dv
        if delist:
            dl = D.delisted[j] & (D.last_pos[j] + 1 >= f + 1) & (D.last_pos[j] + 1 <= days[-1])
            side_ok = {"long0": dol > 0, "short0": dol < 0, "both0": np.ones(len(j), bool)}[delist]
            for i in np.flatnonzero(dl & side_ok):
                r = int(np.searchsorted(days, D.last_pos[j[i]] + 1))
                ch[r, i] += -path[-1, i] * sh[i]                # last close -> 0
        pnl[days] += ch.sum(axis=1)
        brw = 0.0
        if borrow:
            short = -dol[dol < 0].sum()
            brw = borrow / 252.0 * short
            pnl[f:last + 1] -= brw
        if acc is not None:
            acc.short[days] += ch[:, dol < 0].sum(axis=1)
            if f >= wf0:
                npnl = ch.sum(axis=0) - 2.0 * cost * np.abs(dol)    # name-period net of a round trip
                acc.name_periods.extend(npnl.tolist())
                acc.dec_periods.append(float(ch.sum() - tc - brw * (last + 1 - f)))
                for n, v in zip(j.tolist(), npnl.tolist()):
                    acc.by_sym[n] = acc.by_sym.get(n, 0.0) + v
    return pd.Series(pnl, index=D.dates)                     # the final book is marked to END's close


def side_books(D, t, names_idx, score, n=N_SIDE, beta=None):
    """Long the n LOWEST scores, short the n HIGHEST (score = predicted badness). Dollar- or beta-neutral."""
    ok = np.isfinite(score)
    idx, sc = names_idx[ok], score[ok]
    if len(sc) < 2 * n:
        return {}
    order = np.argsort(sc, kind="stable")
    lo, hi = idx[order[:n]], idx[order[-n:]]
    L = S = GROSS
    if beta is not None:
        bl, bs = np.nanmean(beta[lo]), np.nanmean(beta[hi])
        if np.isfinite(bl) and np.isfinite(bs) and bl > 0 and bs > 0:
            L, S = 2 * GROSS * bs / (bl + bs), 2 * GROSS * bl / (bl + bs)
    out = {int(i): L / n for i in lo}
    out.update({int(i): -S / n for i in hi})
    return out


# ------------------------------------------------------------------------------------------------ yardstick
def roc_sortino(x, lo=WF0, hi=WF1, drop=None):
    x = x[(x.index >= lo) & (x.index <= hi)]
    if drop is not None:
        x = x[~((x.index >= drop[0]) & (x.index <= drop[1]))]
    yrs = (x.index.max() - x.index.min()).days / 365.25
    q = np.cumsum(x.to_numpy())
    dd = float((np.maximum.accumulate(np.concatenate([[0.0], q]))[1:] - q).max())
    dn = np.sqrt(np.mean(np.minimum(x.to_numpy(), 0.0) ** 2))
    return (30.0 * (x.sum() / yrs) / dd if dd > 0 else float("nan"),
            float(x.mean() / dn * np.sqrt(252)) if dn > 0 else float("nan"))


def book463_ddweeks():
    """#463's WF daily P&L (built to 2025-06-29, parity asserted) and its drawdown days / weeks (DDW r1 [T5])."""
    from api.book_shadow import book463_valued_daily
    b = book463_valued_daily("2010-06-07", "2025-06-29")
    r, s = roc_sortino(b, pd.Timestamp("2016-07-01"), pd.Timestamp("2025-06-29"))
    assert abs(r - 93.81) < 0.01 and abs(s - 3.816) < 0.001, f"#463 parity failed {r} {s}"
    w = b[(b.index >= pd.Timestamp("2016-07-01")) & (b.index <= pd.Timestamp("2025-06-29"))]
    q = w.cumsum().to_numpy()
    eps, peak_i, peak_v, trough_i = [], -1, 0.0, None
    for i, v in enumerate(q):
        if v >= peak_v:
            if trough_i is not None:
                eps.append((peak_i, trough_i, peak_v - q[trough_i]))
            peak_i, peak_v, trough_i = i, v, None
        elif trough_i is None or v < q[trough_i]:
            trough_i = i
    if trough_i is not None:
        eps.append((peak_i, trough_i, peak_v - q[trough_i]))
    deep = max(e[2] for e in eps)
    eps = [e for e in eps if e[2] >= deep / 3.0]
    days = []
    for p, t, _ in eps:
        days += list(w.index[p + 1: t + 1])
    days = pd.DatetimeIndex(sorted(set(days)))
    wk = pd.Series(1, index=days).groupby(days.to_period("W-SUN")).sum()
    weeks = wk.index[wk >= 3]                                   # ISO weeks (Mon-Sun), as DDW r1
    assert (len(eps), len(days), len(weeks)) == (28, 460, 92), (len(eps), len(days), len(weeks))
    return w, days, weeks, len(eps), deep


def dd_stats(x, w463, days, weeks):
    xw = x.groupby(x.index.to_period("W-SUN")).sum().reindex(weeks).fillna(0.0)
    bw = w463.groupby(w463.index.to_period("W-SUN")).sum().reindex(weeks).fillna(0.0)
    rho = float(np.corrcoef(xw, bw)[0, 1])
    loss = -float(w463.reindex(days).fillna(0.0).sum())
    do = float(x.reindex(days).fillna(0.0).sum()) / loss if loss > 0 else float("nan")
    return rho, do


# ------------------------------------------------------------------------------------------------ cells A and C
def model_scores(D, F, dates, horizon, target, classify=False):
    """Walk-forward predictions at each decision date: refit every 1 January on decisions whose target exit
    (fill + horizon) is before that date. target(t_pos, names_idx) -> values (NaN = not trainable)."""
    from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor
    rows = {}
    for t in dates:
        p = D.pos(t)
        names = np.flatnonzero(D.Un[p])
        rows[t] = (names, xs_rank(F, t, D.syms[names]))
    preds, fits = {}, {}
    for t in dates:
        fill = D.dates[D.pos(t) + 1]
        if fill < WF0:
            continue
        Y = fill.year
        if Y not in fits:
            cut = pd.Timestamp(f"{Y}-01-01")
            Xs, ys = [], []
            for u in dates:
                pu = D.pos(u)
                ex = pu + 1 + horizon
                if ex >= len(D.dates) or D.dates[ex] >= cut:
                    continue
                names, X = rows[u]
                y = target(pu, names)
                ok = np.isfinite(y)
                if ok.sum() > 50:
                    Xs.append(X[ok]); ys.append(y[ok])
            Xt, yt = np.vstack(Xs), np.concatenate(ys)
            m = (HistGradientBoostingClassifier if classify else HistGradientBoostingRegressor)(**HGB)
            fits[Y] = m.fit(Xt, yt.astype(int) if classify else yt)
            log(f"  refit {Y}: {len(yt):,} rows from {len(Xs)} decisions")
        names, X = rows[t]
        m = fits[Y]
        preds[t] = (names, m.predict_proba(X)[:, 1] if classify else m.predict(X))
    return preds


def fwd_total(D, p, names, horizon):
    """Total return from the fill open (p+1) to the exit open (p+1+horizon), dividends with ex-dates after the fill
    through the exit added back (review #64 edit 3)."""
    a, b = p + 1, p + 1 + horizon
    divs = D.div[a + 1: b + 1, :][:, names].sum(axis=0)
    return (D.On[b, names] + divs) / D.On[a, names] - 1.0


def fwd_rank(D, horizon):
    def f(p, names):
        r = fwd_total(D, p, names, horizon)
        out = np.full(len(names), np.nan)
        ok = np.isfinite(r)
        out[ok] = pd.Series(r[ok]).rank(pct=True).to_numpy() - 0.5
        return out
    return f


def fwd_crash(D, horizon):
    def f(p, names):
        r = fwd_total(D, p, names, horizon)
        out = np.full(len(names), np.nan)
        ok = np.isfinite(r)
        if ok.sum() > 20:
            out[ok] = (r[ok] <= np.percentile(r[ok], 5)).astype(float)
        return out
    return f


def wf_decisions(D, dates):
    return [t for t in dates if D.dates[D.pos(t) + 1] >= WF0]


# ------------------------------------------------------------------------------------------------ cell B
def statarb_scores(D, z_raw=False):
    """Daily s-scores (AL 2010) for each universe name, or the raw twin's z-score of the 5-day return.
    Returns {date: (names_idx, s, tradable)}."""
    R = D.r_cc.to_numpy(float)
    out = {}
    start = max(B_WIN, 260)
    r5 = (D.C / D.C.shift(5) - 1.0).to_numpy(float)
    for p in range(start, len(D.dates)):
        t = D.dates[p]
        if D.dates[min(p + 1, len(D.dates) - 1)] < WF0 - pd.Timedelta(days=10):
            continue
        names = np.flatnonzero(D.Un[p])
        if z_raw:
            w = r5[p - B_RES + 1: p + 1, names]
            mu, sd = np.nanmean(w, axis=0), np.nanstd(w, axis=0)
            s = (r5[p, names] - mu) / np.where(sd > 0, sd, np.nan)
            out[t] = (names, s, np.isfinite(s))
            continue
        W = R[p - B_WIN + 1: p + 1, names]
        good = np.isfinite(W).sum(axis=0) >= B_WIN - 12
        names, W = names[good], W[:, good]
        mu, sd = np.nanmean(W, axis=0), np.nanstd(W, axis=0)
        Z = np.nan_to_num((W - mu) / np.where(sd > 0, sd, 1.0))
        corr = Z.T @ Z / B_WIN
        ev, vec = np.linalg.eigh(corr)
        V = vec[:, -B_FACT:] / np.where(sd > 0, sd, 1.0)[:, None]       # eigenportfolio weights v_i / sigma_i
        Fr = np.nan_to_num(W) @ V                                         # factor returns, B_WIN x 15
        Y, X = np.nan_to_num(W[-B_RES:]), np.column_stack([np.ones(B_RES), Fr[-B_RES:]])
        beta, *_ = np.linalg.lstsq(X, Y, rcond=None)
        eps = Y - X @ beta
        Xc = np.cumsum(eps, axis=0)
        x0, x1 = Xc[:-1], Xc[1:]
        mx0, mx1 = x0.mean(axis=0), x1.mean(axis=0)
        b = ((x0 - mx0) * (x1 - mx1)).sum(axis=0) / ((x0 - mx0) ** 2).sum(axis=0)
        a = mx1 - b * mx0
        zeta = x1 - (a + b * x0)
        with np.errstate(invalid="ignore", divide="ignore"):
            m = a / (1.0 - b)
            seq = np.sqrt(zeta.var(axis=0) / (1.0 - b * b))
            s = (Xc[-1] - m) / seq
        trad = (b > 0) & (b < B_KMAX) & np.isfinite(s)
        out[t] = (names, s, trad)
    return out


def statarb_book(D, scores, cost=0.0, borrow=0.0, perm_rng=None, open_thr=B_OPEN, acc=None, delist=None,
                 turnover=None):
    """Daily state machine (signal at close t, trade at open t+1), equal gross per side, rescaled daily. Dividends
    enter the overnight return on the ex-date; a delisted name held on the side named by `delist` goes to zero."""
    T, N = len(D.dates), len(D.syms)
    state = np.zeros(N)
    w_prev = np.zeros(N)
    pnl = np.zeros(T)
    r_on = np.nan_to_num(D.r_on.to_numpy(float)) + D.div_yield_on
    r_id = np.nan_to_num(D.r_id.to_numpy(float))
    valid = np.isfinite(D.On) & np.isfinite(D.Cn)
    wf0 = D.dates.searchsorted(WF0)
    days = sorted(scores)
    nlong = []
    for t in days:
        p = D.pos(t)
        if p + 1 >= T:
            break
        names, s, trad = scores[t]
        s = s.copy()
        if perm_rng is not None:
            perm = perm_rng.permutation(len(s))
            s, trad = s[perm], trad[perm]
        inu = np.zeros(N, bool); inu[names] = True
        sv = np.full(N, np.nan); sv[names] = s
        tv = np.zeros(N, bool); tv[names] = trad
        # exits
        state[(state != 0) & ~inu] = 0
        state[(state > 0) & (sv > B_CLOSE_L)] = 0
        state[(state < 0) & (sv < B_CLOSE_S)] = 0
        state[(state != 0) & ~np.isfinite(sv)] = 0
        # entries
        flat = (state == 0) & tv
        state[flat & (sv < -open_thr)] = 1
        state[flat & (sv > open_thr)] = -1
        f = p + 1
        state[~valid[f]] = 0
        nl, ns = (state > 0).sum(), (state < 0).sum()
        w = np.zeros(N)
        if nl: w[state > 0] = GROSS / nl
        if ns: w[state < 0] = -GROSS / ns
        held = w_prev * (1 + r_id[f - 1])
        contrib = held * r_on[f] + w * r_id[f]
        if delist:
            gone = (w_prev != 0) & ~valid[f] & D.delisted & (D.last_pos == f - 1)
            side = {"long0": w_prev > 0, "short0": w_prev < 0, "both0": np.ones(N, bool)}[delist]
            contrib[gone & side] -= held[gone & side]
        tc = np.abs(w - held * (1 + r_on[f])) * cost
        contrib -= tc
        if borrow:
            contrib[w < 0] -= borrow / 252.0 * (-w[w < 0])
        pnl[f] += contrib.sum()
        if turnover is not None:
            turnover.append(float(np.abs(w - held * (1 + r_on[f])).sum()))
        if acc is not None:
            acc.short[f] += contrib[(w < 0) | (w_prev < 0)].sum()
            if f >= wf0:
                nz = (w != 0) | (w_prev != 0)
                acc.name_periods.extend(contrib[nz].tolist())          # name-days for B
                for n in np.flatnonzero(nz):
                    acc.by_sym[n] = acc.by_sym.get(n, 0.0) + contrib[n]
        w_prev = w
        nlong.append((nl, ns))
    ser = pd.Series(pnl, index=D.dates)
    if acc is not None:
        acc.dec_periods = ser[(ser.index >= WF0) & (ser.index <= WF1)].tolist()   # B's decision periods = days
    return ser, np.array(nlong)


# ------------------------------------------------------------------------------------------------ steps
def build(D):
    log("features A")
    FA = features_A(D)
    wk = decision_dates(D, "weekly")
    mo = decision_dates(D, "monthly")
    log("features C")
    FC, beta252 = features_C(D)
    return FA, FC, beta252.to_numpy(float), wk, mo


def random_books(D, dates, rng, beta=None):
    books = []
    for t in dates:
        p = D.pos(t)
        names = np.flatnonzero(D.Un[p])
        books.append((t, side_books(D, t, names, rng.random(len(names)), beta=None if beta is None else beta[p])))
    return books


def shuffles_periodic(D, dates, rng, beta=None):
    return np.array([roc_sortino(periodic_book(D, random_books(D, dates, rng, beta)))[0] for _ in range(N_SHUF)])


def ca_path_required():
    ca = os.environ.get("XSML_CA")
    assert ca and os.path.exists(ca), "XSML_CA = the wide corporate-actions file is required (review #64)"
    return ca


def power():
    os.makedirs(OUT, exist_ok=True)
    D = Data(ca_path_required())
    FA, FC, beta, wk, mo = build(D)
    w463, days, weeks, n_eps, deep = book463_ddweeks()
    lines = [f"data sha256 {D.sha}; {len(D.syms):,} symbols ever in the universe; {D.n_quarantined} quarantined; "
             f"corporate actions sha256 {D.ca['sha']}; {D.ca_check}; dividends {D.div_counts}",
             f"#463 parity 93.81 / 3.816 OK; WF drawdown episodes >= 1/3 of ${deep:,.0f}: {n_eps}; DD days {len(days)}; "
             f"DD weeks {len(weeks)} (DDW r1 printed 28 / 460 / 92)",
             "POWER LINE - matched-risk shuffles (random books, same rule, GROSS), no cell or twin P&L read:"]
    rng = np.random.default_rng(SEED)
    wA = wf_decisions(D, wk)
    zA = shuffles_periodic(D, wA, rng)
    lines.append(f"  A PATTERN  ({len(wA)} weekly decisions): gross WF ROC 50th {np.median(zA):+.1f}  95th "
                 f"{np.percentile(zA, 95):+.1f}")
    wC = wf_decisions(D, mo)
    zC = shuffles_periodic(D, wC, rng, beta=beta)
    lines.append(f"  C CRASH    ({len(wC)} monthly decisions): gross WF ROC 50th {np.median(zC):+.1f}  95th "
                 f"{np.percentile(zC, 95):+.1f}")
    log("B s-scores (model signal only)")
    SB = statarb_scores(D)
    zB = np.array([roc_sortino(statarb_book(D, SB, perm_rng=rng)[0])[0] for _ in range(N_SHUF)])
    lines.append(f"  B STATARB  ({len(SB)} daily decisions): gross WF ROC 50th {np.median(zB):+.1f}  95th "
                 f"{np.percentile(zB, 95):+.1f}")
    lines.append("Map bar: net WF ROC @ $30k >= 15 with rho_dd <= 0.15 (or DO > 0 and rho_dd <= -0.15 for C).")
    txt = "\n".join(lines)
    print(txt)
    open(os.path.join(OUT, "POWER.txt"), "w", encoding="utf-8").write(txt + "\n")
    pd.DataFrame({"A": zA, "B": zB, "C": zC}).to_csv(os.path.join(OUT, "nulls.csv"), index=False)


def power2():
    """Review #64 edits 4 + 5, before any cell number: B's turnover and cost per year (positions only, no P&L read),
    and the DO null for C's earner route (DO of the same 1,000 random beta-neutral books, re-drawn with seed + 2)."""
    D = Data(ca_path_required())
    FA, FC, beta, wk, mo = build(D)
    w463, days, weeks, _, _ = book463_ddweeks()
    SB = statarb_scores(D)
    turn = []
    _, nl = statarb_book(D, SB, turnover=turn)
    fdays = [D.dates[D.pos(t) + 1] for t in sorted(SB) if D.pos(t) + 1 < len(D.dates)]
    sd = pd.Series(turn, index=fdays[:len(turn)])
    sd = sd[(sd.index >= WF0) & (sd.index <= WF1)]
    yrs = (WF1 - WF0).days / 365.25
    lines = [f"B STATARB turnover (positions only): {sd.mean() / (2 * GROSS):.1%} of the $2M gross a day; "
             f"${sd.sum() / yrs:,.0f} traded a year -> cost ${COST * sd.sum() / yrs:,.0f}/yr at 5 bps a side "
             f"(${COST_STRESS * sd.sum() / yrs:,.0f} at 10 bps); avg names long / short "
             f"{nl[:, 0].mean():.1f} / {nl[:, 1].mean():.1f}"]
    rng = np.random.default_rng(SEED + 2)
    wC = wf_decisions(D, mo)
    dos = []
    for _ in range(N_SHUF):
        x = periodic_book(D, random_books(D, wC, rng, beta))
        dos.append(dd_stats(x, w463, days, weeks))
    dos = np.array(dos)
    lines.append(f"C CRASH earner-route null (1,000 random beta-neutral books, gross): DO 50th {np.median(dos[:, 1]):+.3f} "
                 f"95th {np.percentile(dos[:, 1], 95):+.3f}; rho_dd 5th {np.percentile(dos[:, 0], 5):+.3f} "
                 f"50th {np.median(dos[:, 0]):+.3f}")
    txt = "\n".join(lines)
    print(txt)
    open(os.path.join(OUT, "POWER2.txt"), "w", encoding="utf-8").write(txt + "\n")
    pd.DataFrame({"C_rho": dos[:, 0], "C_do": dos[:, 1]}).to_csv(os.path.join(OUT, "nulls_do.csv"), index=False)


def years_ok(x):
    ys = []
    for y in range(2018, 2025):
        lo, hi = pd.Timestamp(f"{y}-07-01"), pd.Timestamp(f"{y + 1}-06-30")
        ys.append(float(x[(x.index >= lo) & (x.index <= hi)].sum()))
    return ys


def judge(name, D, net, net_s, gross, twin, null95, w463, days, weeks, info, pf, nbrs, acc, worst, short0, do95):
    r, s = roc_sortino(net)
    rs, _ = roc_sortino(net_s)
    rg, _ = roc_sortino(gross)
    rt, st = roc_sortino(twin)
    rw, _ = roc_sortino(worst)
    rho, do = dd_stats(net, w463, days, weeks)
    wf = net[(net.index >= WF0) & (net.index <= WF1)]
    tot = float(wf.sum())
    from augur_engine.drawdowns import dd5
    d5 = dd5(wf)
    tw = twin[(twin.index >= WF0) & (twin.index <= WF1)]
    d5t = dd5(tw)
    no20 = float(wf[~((wf.index >= "2020-02-01") & (wf.index <= "2020-04-30"))].sum())
    ys = years_ok(net)
    h1 = float(wf[wf.index <= "2021-06-30"].sum())
    h2 = float(wf[wf.index >= "2021-07-01"].sum())
    npd = np.sort(np.asarray(acc.name_periods, float))[::-1]
    k1 = max(1, int(round(0.01 * len(npd))))
    no_top1 = tot - float(npd[:k1].sum())
    no_top5 = tot - float(np.sort(np.asarray(acc.dec_periods, float))[::-1][:5].sum())
    earner = name.startswith("C") and do > do95 and rho <= -0.15
    map_ok = r >= 15 and rho <= 0.15
    bars = {
        "1 net WF ROC@$30k >= 15 (or C's earner route: DO > its null's 95th AND rho_dd <= -0.15) AND net > 0 at stress":
            bool((r >= 15 or earner) and tot > 0 and net_s[(net_s.index >= WF0)].sum() > 0),
        "2 NET WF ROC above the matched-risk shuffle's 95th pct (gross null)": bool(r > null95),
        "3 beats its raw twin on net WF ROC AND Sortino": bool(r > rt and s > st),
        "5 RISK r1: no Feb-Apr 2020 > 0, >= 5 of 7 years > 0, both halves > 0, > 0 without the best 1% of name-periods "
        "and without the best 5 decision periods":
            bool(no20 > 0 and sum(v > 0 for v in ys) >= 5 and h1 > 0 and h2 > 0 and no_top1 > 0 and no_top5 > 0),
        "6 >= 100 name-positions and >= 26 decision dates": bool(info["positions"] >= 100 and info["decisions"] >= 26),
        "7 PF >= 1.0 (A/C name-periods net of a round trip; B daily)": bool(pf >= 1.0),
        "8 both neighbours net WF ROC > 0": bool(all(v > 0 for v in nbrs.values())),
    }
    top = sorted(acc.by_sym.items(), key=lambda kv: -abs(kv[1]))[:30]
    sw = short0[(short0.index >= WF0) & (short0.index <= WF1)]
    lines = [f"\n{name}: net WF ROC@$30k {r:.1f} Sortino {s:.2f} | stress {rs:.1f} | gross {rg:.1f} | shuffle 95th "
             f"{null95:.1f}: NET lead {r - null95:+.1f}, gross lead {rg - null95:+.1f} | raw twin net {rt:.1f} / {st:.2f} "
             f"| WF net ${tot:,.0f}",
             f"  DD5 (MANAGER #77): worst WF DD ${d5['max_dd']:,.0f}, DD5 ${d5['dd5_usd']:,.0f}"
             + (" - ROC DRIVEN BY ONE EPISODE" if d5["one_episode"] else "")
             + f" | twin worst ${d5t['max_dd']:,.0f} DD5 ${d5t['dd5_usd']:,.0f}"
             + (" (twin: one episode)" if d5t["one_episode"] else ""),
             "  July-June years: " + ", ".join(f"{2018 + i}/{(2019 + i) % 100:02d} ${v:,.0f}" for i, v in enumerate(ys))
             + f" | no-2020 ${no20:,.0f} | halves ${h1:,.0f} / ${h2:,.0f} | without best 1% name-periods "
             f"(k={k1}) ${no_top1:,.0f} | without best 5 decision periods ${no_top5:,.0f}",
             "  " + ", ".join(f"{k} {v}" for k, v in info.items()) + f" | PF {pf:.3f} | neighbours "
             + ", ".join(f"{k} {v:.1f}" for k, v in nbrs.items()),
             f"  DELISTING (review #64 edit 2): delisted LONGS to zero -> net WF ROC {rw:.1f} (base {r:.1f}); short leg WF "
             f"${float(acc.short[(net.index >= WF0) & (net.index <= WF1)].sum()):,.0f} base vs ${float(sw.sum()):,.0f} "
             f"with delisted SHORTS to zero",
             f"  REPORT (book-add information, MANAGER #63 - not a gate): rho_dd {rho:+.2f} (map wants <= +0.15: "
             f"{map_ok}), DO {do:+.3f}" + (f" (C's DO null 95th {do95:+.3f})" if name.startswith("C") else ""),
             "  30 largest single-name contributors (hand-audit list if a pass is spoken): "
             + ", ".join(f"{D.syms[n]} ${v:,.0f}" for n, v in top)]
    lines += [f"  [{'PASS' if v else 'fail'}] {k}" for k, v in bars.items()]
    lines.append(f"  -> {name}: " + ("STAGE A PASS -> hand audit of the 30 names, then MANAGER (research row; the leg's "
                                      "own sealed-year veto on the one stock day; forward shadow decides)"
                                      if all(bars.values()) else "dead (no variants)"))
    return lines, all(bars.values())


def run():
    for f in ("POWER.txt", "POWER2.txt"):
        assert os.path.exists(os.path.join(OUT, f)), f"run the power steps first and commit {f}"
    ca = ca_path_required()
    nulls = pd.read_csv(os.path.join(OUT, "nulls.csv"))
    do95 = float(np.percentile(pd.read_csv(os.path.join(OUT, "nulls_do.csv")).C_do, 95))
    D = Data(ca)
    FA, FC, beta, wk, mo = build(D)
    w463, days, weeks, _, _ = book463_ddweeks()
    lines = [open(os.path.join(OUT, f), encoding="utf-8").read().rstrip() for f in ("POWER.txt", "POWER2.txt")]
    lines.append(f"corporate actions: {ca} sha256 {D.ca['sha']}; cross-check {D.ca_check}; dividends {D.div_counts}; "
                 f"dividend name-days {int((D.div != 0).sum()):,}")
    verdict = {}
    T = len(D.dates)

    def pf_of(v):
        v = np.asarray(v, float)
        return float(v[v > 0].sum() / -v[v < 0].sum()) if (v < 0).any() else float("inf")

    def periodic_cell(name, books, twin, nbr_books, null_key, do95_):
        acc = Acc(T)
        net = periodic_book(D, books, COST, BORROW, acc=acc)
        acc0 = Acc(T)
        periodic_book(D, books, COST, BORROW, acc=acc0, delist="short0")
        nbrs = {k: roc_sortino(periodic_book(D, b, COST, BORROW))[0] for k, b in nbr_books.items()}
        info = dict(decisions=len(books), positions=sum(len(b) for _, b in books))
        return judge(name, D, net, periodic_book(D, books, COST_STRESS, BORROW), periodic_book(D, books),
                     periodic_book(D, twin, COST, BORROW), float(np.percentile(nulls[null_key], 95)), w463, days, weeks,
                     info, pf_of(acc.name_periods), nbrs, acc,
                     periodic_book(D, books, COST, BORROW, delist="long0"), pd.Series(acc0.short, index=D.dates), do95_)

    # ---- A PATTERN ----
    log("A: walk-forward model")
    PA = model_scores(D, FA, list(wk), 5, fwd_rank(D, 5))
    wA = [t for t in wf_decisions(D, wk) if t in PA]

    def books_A(n):
        return [(t, side_books(D, t, PA[t][0], -PA[t][1], n=n)) for t in wA]
    r5, m12 = FA["r5"], FA["mom12"]
    twinA = []
    for t in wA:
        names = PA[t][0]
        x = xs_rank({"a": -r5, "b": m12}, t, D.syms[names])
        twinA.append((t, side_books(D, t, names, -np.nanmean(x, axis=1))))
    L, verdict["A"] = periodic_cell("A PATTERN", books_A(N_SIDE), twinA, {"n=25": books_A(25), "n=100": books_A(100)},
                                    "A", float("nan"))
    lines += L

    # ---- C CRASH ----
    log("C: walk-forward classifier")
    PC = model_scores(D, FC, list(mo), 21, fwd_crash(D, 21), classify=True)
    wC = [t for t in wf_decisions(D, mo) if t in PC]

    def books_C(n):
        return [(t, side_books(D, t, PC[t][0], PC[t][1], n=n, beta=beta[D.pos(t)])) for t in wC]
    iv = FC["ivol63"]
    twinC = [(t, side_books(D, t, PC[t][0], iv.loc[t, D.syms[PC[t][0]]].to_numpy(float), beta=beta[D.pos(t)]))
             for t in wC]
    L, verdict["C"] = periodic_cell("C CRASH", books_C(N_SIDE), twinC, {"n=25": books_C(25), "n=100": books_C(100)},
                                    "C", do95)
    lines += L

    # ---- B STATARB ----
    log("B: s-scores + twin")
    SB, SBt = statarb_scores(D), statarb_scores(D, z_raw=True)
    acc, acc0 = Acc(T), Acc(T)
    net, nl = statarb_book(D, SB, COST, BORROW, acc=acc)
    statarb_book(D, SB, COST, BORROW, acc=acc0, delist="short0")
    nbB = {f"open {o}": roc_sortino(statarb_book(D, SB, COST, BORROW, open_thr=o)[0])[0] for o in (1.0, 1.5)}
    infoB = dict(decisions=len(SB), positions=int(nl.sum()), avg_long=round(float(nl[:, 0].mean()), 1),
                 avg_short=round(float(nl[:, 1].mean()), 1))
    wfB = net[(net.index >= WF0) & (net.index <= WF1)]
    L, verdict["B"] = judge("B STATARB", D, net, statarb_book(D, SB, COST_STRESS, BORROW)[0], statarb_book(D, SB)[0],
                            statarb_book(D, SBt, COST, BORROW)[0], float(np.percentile(nulls.B, 95)), w463, days,
                            weeks, infoB, pf_of(wfB.to_numpy()), nbB, acc,
                            statarb_book(D, SB, COST, BORROW, delist="long0")[0],
                            pd.Series(acc0.short, index=D.dates), float("nan"))
    lines += L

    lines.append("\nSTAGE A: " + (", ".join(k for k, v in verdict.items() if v) or "no cell passes")
                 + " (walk-forward only; nothing after 2025-06-29 loaded; no variants)")
    txt = "\n".join(lines)
    print(txt)
    open(os.path.join(OUT, "STAGE_A.txt"), "w", encoding="utf-8").write(txt + "\n")
    return verdict


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    if mode == "power":
        power()
    elif mode == "power2":
        power2()
    elif mode == "run":
        run()
    else:
        raise SystemExit("usage: xsml_r1.py power | power2 | run")
