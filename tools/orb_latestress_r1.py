"""
LATESTRESS r1 - last-half-hour momentum on STRESS days, NQ and ES. STAGE A, walk-forward only.
Pre-registration: docs/PREREG_orb_latestress_r1_2026-10-07.md (scope rank 1, docs/SCOPE_ORB_2026-10-05.md).
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


def vix_flag(sessions):
    """T1 per session: the last VIX close BEFORE the session is >= the 80th pct of the 252 closes before that one."""
    import pandas as pd
    v = pd.read_csv(VIX_CSV)
    v = pd.Series(v.CLOSE.astype(float).values, index=pd.to_datetime(v.DATE, format="%m/%d/%Y")).sort_index()
    p80 = v.shift(1).rolling(252, min_periods=252).quantile(0.8)
    flag = (v >= p80) & p80.notna()
    prior = flag.reindex(flag.index.union(sessions)).shift(1).ffill()   # the flag of the last VIX day before each session
    return prior.reindex(sessions).fillna(False).astype(bool)


def market_rows(mk, mult, cost):
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
    T["T1"] = vix_flag(pd.DatetimeIndex(T.date)).values
    return T


def main():
    import numpy as np
    import pandas as pd
    from augur_engine.drawdowns import dd5

    book, cal = C.book463(), C.session_calendar()
    ddd = C.drawdown_days(book)
    print("#463 drawdown days: %d (TV counted 460)" % len(ddd))
    rows = {mk: market_rows(mk, *MKT[mk]) for mk in MKT}
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
    passes = C.evaluate(cells, nulls, book, cal, ddd, "LATESTRESS")

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
    print("\nLATESTRESS verdict: %s" % ("PASS: %s" % ", ".join(passes) if passes else "DEAD at Stage A (0 of 4 cells)"))


if __name__ == "__main__":
    main()
