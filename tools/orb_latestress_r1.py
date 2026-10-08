"""
LATESTRESS r1 - last-half-hour momentum on STRESS days, NQ and ES. STAGE A, walk-forward only.
Pre-registration: docs/PREREG_orb_latestress_r1_2026-10-07.md (+ addendum 3: <5 qualifying years = UNDECIDABLE, VIX pair = one test; addendum 2: holiday VIX rows dropped;
addendum 1: bar g = two thirds of the WF years
holding >= 10 trades; the 6/9 reading printed as a report). Scope rank 1, docs/SCOPE_ORB_2026-10-05.md.
Run from the shared checkout:

    python tools/orb_latestress_r1.py

m = close of the 15:25 bar - the prior session's last close, in POINTS (roll-corrected 5m RTH masters, bars stamped at
the START, Eastern: the 15:25 bar closes at 15:30). Trade sign(m) from the 15:30 bar's OPEN to the 15:55 bar's CLOSE.
Cells: market {NQ, ES} x trigger {T1 VIX: prior VIX close >= the 80th pct of the 252 closes before it; T2 day move:
|m| >= 2x the median |m| of the previous 60 sessions}. Random-day family null (same count per year of non-trigger
sessions). Bars, book and diagnostics: tools/orb_nt_common.py (NT r1). Report-only: ALL days (= ledger 2.14, SEEN),
T1 and T2 together, and Gao et al.'s 15:00 -> 15:30 half-hour as the signal.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import orb_nt_common as C   # noqa: E402  (sets ROOT, cwd, env)

MKT = {"NQ": (20.0, 0.533), "ES": (50.0, 0.363)}
STRESS = 0.25
VIX_CSV = "C:/EdgeLog/_research_cache/public_series/cboe/VIX_History.csv"
SEED = 20261007
SMOKE = "--smoke" in sys.argv
PREREG = "PREREG_orb_latestress_r1_2026-10-07.md"
PREREG_SHA = "09c2997f23c83de98a99cc17578ce95f4ef23403f41dafd501f74036bb981e81"


def cme_holiday_days():
    """Addendum 2: CME US-holiday sessions (stock market closed) = RTH master sessions ending with the 12:55 or 13:00 bar
    (memory: session calendar traps; 71 in 2010-06..2025-06). NYSE early closes end at 13:10 / 13:15 and are kept."""
    import pandas as pd
    from augur_engine.data import find_master, load_master_arrays
    A = load_master_arrays(find_master("ES", "5m", "rth", "db_adj_rth"), date_from="2010-03-01", date_to=C.WF[1])
    idx = pd.DatetimeIndex(A["index"]).tz_localize(None)
    last = pd.Series(idx.strftime("%H:%M"), index=idx).groupby(idx.normalize()).last()
    return set(last[last.isin(["12:55", "13:00"])].index)


def vix_flag(sessions, drop_days=()):
    """T1 per session: the last VIX close BEFORE the session is >= the 80th pct of the 252 closes before that one.
    Addendum 2: VIX rows dated on CME-holiday sessions (the CBOE file carries 23 of them from 2022) are dropped first,
    so the 252-close window and 'the prior VIX close' count stock-market days only."""
    import pandas as pd
    v = pd.read_csv(VIX_CSV)
    v = pd.Series(v.CLOSE.astype(float).values, index=pd.to_datetime(v.DATE, format="%m/%d/%Y")).sort_index()
    n0 = len(v)
    v = v[~v.index.isin(list(drop_days))]
    print("VIX rows dropped on CME-holiday sessions: %d (%s)" % (n0 - len(v), ", ".join(
        str(d.date()) for d in sorted(set(drop_days)) if d >= pd.Timestamp("2022-01-01"))[:200]))
    p80 = v.shift(1).rolling(252, min_periods=252).quantile(0.8)
    flag = (v >= p80) & p80.notna()
    prior = flag.reindex(flag.index.union(sessions)).shift(1).ffill()   # the flag of the last VIX day before each session
    return prior.reindex(sessions).fillna(False).astype(bool)


def market_rows(mk, mult, cost, t1):
    import numpy as np
    import pandas as pd
    from augur_engine.data import find_master, load_master_arrays
    A = load_master_arrays(find_master(mk, "5m", "rth", "db_adj_rth"), date_from="2010-03-01", date_to=C.WF[1])
    idx = pd.DatetimeIndex(A["index"]).tz_localize(None)
    o = pd.Series(np.asarray(A["open"], float), index=idx)
    c = pd.Series(np.asarray(A["close"], float), index=idx)
    day = idx.normalize()
    last = c.groupby(day).last()
    hm = idx.strftime("%H:%M")

    def at(s, h):
        x = s[hm == h]
        x.index = x.index.normalize()
        return x

    c1525, c1455, o1530 = at(c, "15:25"), at(c, "14:55"), at(o, "15:30")
    path = {h: at(c, h) for h in ("15:30", "15:35", "15:40", "15:45", "15:50", "15:55")}
    prev = last.shift(1)
    d = c1525.index.intersection(o1530.index).intersection(path["15:55"].index)
    T = pd.DataFrame(dict(date=d, m=(c1525[d] - prev.reindex(d)).values, m12=(c1525[d] - c1455.reindex(d)).values,
                          en=o1530[d].values, ex=path["15:55"][d].values))
    for h, s in path.items():
        T["p" + h] = (s.reindex(d).values - T.en.values) * mult
    T = T.dropna(subset=["m"]).reset_index(drop=True)
    T = T[T.m != 0].reset_index(drop=True)
    T["g"] = (T.ex - T.en) * mult                                   # gross, LONG direction
    if SMOKE:   # plumbing check before the prereg is on main: EVERY dollar column is noise, signals and counts are real
        rs = np.random.default_rng(1)
        T["g"] = rs.normal(0.0, 400.0, len(T))
        for h in ("15:30", "15:35", "15:40", "15:45", "15:50", "15:55"):
            T["p" + h] = rs.normal(0.0, 300.0, len(T))
    T["side"] = np.sign(T.m)
    T["cost"] = cost * mult
    T["usd"] = T.side * T.g - T.cost
    T["usd_stress"] = T.side * T.g - (cost + STRESS) * mult
    med = T.m.abs().rolling(60, min_periods=60).median().shift(1)
    T["T2"] = (T.m.abs() >= 2.0 * med) & med.notna()
    T["T1"] = t1.reindex(pd.DatetimeIndex(T.date)).fillna(False).astype(bool).values
    return T


def check_prereg():
    """MANAGER #52: the run checks the prereg's LF sha256 (posted to MANAGER before the run) and prints it."""
    import hashlib
    here = os.path.dirname(os.path.abspath(__file__))
    for p in (os.path.join(here, "..", "docs", PREREG), os.path.join(C.ROOT, "docs", PREREG)):
        if os.path.exists(p):
            h = hashlib.sha256(open(p, "rb").read().replace(b"\r\n", b"\n")).hexdigest()
            print("PREREG %s LF sha256 %s -> %s" % (PREREG, h, "MATCH" if h == PREREG_SHA else "MISMATCH - stop"))
            if h != PREREG_SHA and not SMOKE:
                sys.exit(3)
            return
    print("PREREG file not found - stop")
    sys.exit(3)


def main():
    import numpy as np
    import pandas as pd
    from augur_engine.drawdowns import dd5
    check_prereg()

    book, cal = C.book463(), C.session_calendar()
    ddd = C.drawdown_days(book)
    print("#463 drawdown days: %d (TV counted 460)" % len(ddd))
    sess_all = pd.DatetimeIndex(cal)
    t1 = vix_flag(sess_all, drop_days=cme_holiday_days())
    rows = {mk: market_rows(mk, *MKT[mk], t1) for mk in MKT}
    cells, pools = {}, {}
    for mk, T in rows.items():
        for tg in ("T1", "T2"):
            cells["%s %s" % (mk, tg)] = T[T[tg]].reset_index(drop=True)
            pools["%s %s" % (mk, tg)] = T[~T[tg]].reset_index(drop=True)

    def wf(df):
        return df[(df.date >= pd.Timestamp(C.WF[0])) & (df.date <= pd.Timestamp(C.WF[1]))]

    # ---- printed FIRST: trigger counts and the power line (unsigned moves only) ----
    print("\nTRIGGER COUNTS (walk-forward, per year 2016H2..2025H1):")
    for name, X in cells.items():
        W = wf(X)
        print("  %s: %d WF trades | %s | 2010-16 %d" % (name, len(W), " ".join(
            str(int(v)) for v in W.groupby(W.date.dt.year).size().reindex(range(2016, 2026), fill_value=0).values),
            int(((X.date >= pd.Timestamp(C.EARLY[0])) & (X.date <= pd.Timestamp(C.EARLY[1]))).sum())))
    print("POWER LINE (sd of the unsigned 15:30->16:00 dollar move on trigger days; MDE = 2.8 sd / sqrt(N)):")
    for name, X in cells.items():
        W = wf(X)
        n, sd = len(W), float(W.g.std(ddof=1))
        per_yr = n / 9.0
        print("  %s: N %d sd $%.0f -> MDE $%.0f a trade | needed for $5k a year (earner floor at a $30k DD) $%.0f, "
              "for $15k a year $%.0f" % (name, n, sd, 2.8 * sd / np.sqrt(n), 5000 / per_yr, 15000 / per_yr))

    rng = np.random.default_rng(SEED)
    nulls = []
    for _ in range(C.N_NULL):
        ns = {}
        for name, X in cells.items():
            P = pools[name]
            pick = []
            for y, n in X.groupby(X.date.dt.year).size().items():
                cand = np.flatnonzero(P.date.dt.year.values == y)
                pick.extend(rng.choice(cand, size=min(n, len(cand)), replace=False))
            ns[name] = P.iloc[sorted(pick)]
        nulls.append(ns)
    def breadth_10(W, yrs, nyr):          # addendum 1 + 3: two thirds of the WF years holding >= 10 of the cell's trades
        held = nyr[nyr >= 10].index
        if len(held) < 5:
            return False, "UNDECIDABLE (%d qualifying WF years < 5) = NOT a pass" % len(held)
        pos = int((yrs.reindex(held) > 0).sum())
        ok = pos / len(held) >= 2.0 / 3.0
        return ok, "%s (%d of %d qualifying WF years positive)" % ("PASS" if ok else "FAIL", pos, len(held))

    passes = C.evaluate(cells, nulls, book, cal, ddd, "LATESTRESS",
                        breadth=("g 2/3 of WF years with >= 10 trades", breadth_10))

    # ---- REPORTED ONLY ----
    bk = book[(book.index >= pd.Timestamp(C.WF[0])) & (book.index <= pd.Timestamp(C.WF[1]))]
    eps = dd5(bk)["episodes"][:5]
    for name, X in cells.items():
        W = wf(X)
        path = " ".join("%s %+.0f" % (h, (W.side * W["p" + h]).mean()) for h in
                        ("15:30", "15:35", "15:40", "15:45", "15:50", "15:55"))
        print("\n(reported) %s event-time path, mean signed $ from the 15:30 open to each bar close: %s" % (name, path))
        print("(reported) %s on #463's five deepest WF episodes: %s" % (name, " | ".join(
            "%s..%s $%+.0f" % (e["peak"], e["trough"],
                               W[(W.date > pd.Timestamp(e["peak"])) & (W.date <= pd.Timestamp(e["trough"]))].usd.sum())
            for e in eps)))
        u = W.usd.values
        if len(u) > 20:
            b, means = 10, []
            k = int(np.ceil(len(u) / b))
            for _ in range(2000):
                st = rng.integers(0, len(u), size=k)
                means.append(np.concatenate([np.take(u, range(s, s + b), mode="wrap") for s in st])[:len(u)].mean())
            print("(reported) %s block-bootstrap t (blocks of %d trades): %.2f vs plain t %.2f"
                  % (name, b, u.mean() / np.std(means, ddof=1), C.tstat(u)))
        W12 = W.assign(s12=np.sign(W.m12))
        W12 = W12[W12.s12 != 0]
        f12 = W12.s12 * W12.g - W12.cost
        print("(reported) %s with the 15:00->15:30 half-hour as the signal: %d trades, $%+.0f, t %.2f"
              % (name, len(f12), f12.sum(), C.tstat(f12)))
    for mk, T in rows.items():
        W = wf(T)
        both = W[W.T1 & W.T2]
        print("\n(reported, SEEN as ledger 2.14) %s ALL days: %d trades, $%+.0f, mean $%+.1f, t %.2f"
              % (mk, len(W), W.usd.sum(), W.usd.mean(), C.tstat(W.usd)))
        print("(reported) %s T1 and T2 together: %d trades, $%+.0f, t %.2f" % (mk, len(both), both.usd.sum(), C.tstat(both.usd)))
    print("\nVIX PAIR (one test, addendum 3): NQ T1 %s | ES T1 %s" % ("PASS" if "NQ T1" in passes else "FAIL",
                                                                      "PASS" if "ES T1" in passes else "FAIL"))
    print("DAY-MOVE cells: NQ T2 %s | ES T2 %s" % ("PASS" if "NQ T2" in passes else "FAIL",
                                                  "PASS" if "ES T2" in passes else "FAIL"))
    print("\nLATESTRESS verdict: %s" % ("PASS: %s" % ", ".join(passes) if passes else "DEAD at Stage A (0 of 4 cells)"))


if __name__ == "__main__":
    main()
