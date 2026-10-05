"""
Shared Stage A machinery for the ORB lane's NEW STRATEGY TYPES r1 (NT1 MACRO830, NT2 ANNPREM, NT3 SAFEHAVEN).
Pre-registration: docs/PREREG_orb_newtypes_r1_2026-10-05.md. Run the NT scripts from the shared checkout.

Every cell is a list of one-trade-per-day rows: date (Eastern session day the P&L lands on), usd (net of base cost),
usd_stress (net of stress cost), g (gross P&L in the cell's LONG direction, dollars, for the coin-flip null), side.
"""
import os
import sys

ROOT = r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"
sys.path.insert(0, ROOT)
os.chdir(ROOT)
os.environ.setdefault("AUGUR_TRIAL_CACHE", "1")
UID = "IO0K35JpLIcH9YK4C0pMNYUzZOM2"

WF = ("2016-07-01", "2025-06-29")
EARLY = ("2010-06-07", "2016-06-30")
X20 = ("2020-02-15", "2020-04-30")
X22 = ("2022-01-01", "2022-12-31")
C_WIN = ("2016-07-01", "2018-06-30")   # c from volatility: first two WF years (MANAGER edit 3)
DD_DEPTH = 14950.0
REF = dict(roc=93.81, sor=3.816, dd=44849.0)
A2_BAR = dict(roc=98.50, sor=3.816)
N_NULL = 500


def session_calendar():
    import pandas as pd
    from augur_engine.data import find_master, load_master_arrays
    A = load_master_arrays(find_master("NQ", "5m", "rth", "db_noadj_rth"), date_from="2010-06-07", date_to="2025-06-30")
    idx = pd.DatetimeIndex(A["index"])
    return pd.DatetimeIndex(sorted(set(idx.tz_localize(None).normalize())))


def book463():
    """#463's walk-forward daily valued series, rebuilt with the book engine; refuses unless the reference reproduces."""
    import numpy as np
    import pandas as pd
    import firebase_admin
    from firebase_admin import credentials, firestore
    from google.cloud.firestore_v1.base_query import FieldFilter as FF
    from augur_engine import book as B
    if not firebase_admin._apps:
        firebase_admin.initialize_app(credentials.Certificate("serviceAccount.json"))
    u = firestore.client().collection("users").document(UID)
    d = list(u.collection("backtests").where(filter=FF("run_id", "==", 463)).limit(1).stream())[0].to_dict()
    parts = []
    for leg in d["legs"]:
        tr, info = B._leg_trades(leg, d["date_from"], d["date_to"])
        m = info.get("_mtm_day")
        pairs = m if m is not None else tr
        s = pd.Series([float(a) for _, a in pairs], index=pd.to_datetime([str(x)[:10] for x, _ in pairs]))
        parts.append(s.groupby(level=0).sum())
    book = pd.concat(parts, axis=1).fillna(0).sum(axis=1).sort_index()
    sc = score(book, *WF)
    ok = abs(sc["roc"] - REF["roc"]) < 0.02 and abs(sc["sor"] - REF["sor"]) < 0.002 and abs(sc["dd"] - REF["dd"]) < 1.0
    print("PARITY #463 WF: ROC %.2f Sortino %.3f DD $%.0f (reference %.2f / %.3f / $%.0f) -> %s"
          % (sc["roc"], sc["sor"], sc["dd"], REF["roc"], REF["sor"], REF["dd"], "EXACT" if ok else "MISMATCH - stop"),
          flush=True)
    if not ok:
        sys.exit(2)
    return book


def score(s, lo, hi):
    """Unified convention: valued-daily net and DD inside the stretch, years = (last - first) / 365.25."""
    import numpy as np
    import pandas as pd
    z = s[(s.index >= pd.Timestamp(lo)) & (s.index <= pd.Timestamp(hi))]
    cum = z.cumsum()
    dd = float((cum.cummax().clip(lower=0) - cum).max())
    yrs = (z.index[-1] - z.index[0]).days / 365.25
    neg = z[z < 0]
    sor = float(z.mean() / np.sqrt((neg ** 2).sum() / len(z)) * np.sqrt(252)) if len(neg) else float("inf")
    return dict(roc=30.0 * (z.sum() / yrs) / dd if dd > 0 else float("inf"), sor=sor, dd=dd, net=float(z.sum()))


def drawdown_days(book):
    """Days after each peak through the trough of every WF drawdown episode at least DD_DEPTH deep (TV's DD-WEEK
    definition; TV counted 460 such days - printed for comparison)."""
    import pandas as pd
    z = book[(book.index >= pd.Timestamp(WF[0])) & (book.index <= pd.Timestamp(WF[1]))]
    cum = z.cumsum().values
    out, peak_i, trough_i = set(), 0, 0

    def close(p, t):
        if t > p and cum[p] - cum[t] >= DD_DEPTH:
            out.update(z.index[p + 1:t + 1])

    for k in range(1, len(cum)):
        if cum[k] >= cum[peak_i]:
            close(peak_i, trough_i)
            peak_i = trough_i = k
        elif cum[k] < cum[trough_i]:
            trough_i = k
    close(peak_i, trough_i)
    return pd.DatetimeIndex(sorted(out))


def tstat(x):
    import numpy as np
    x = np.asarray(x, float)
    return float(x.mean() / (x.std(ddof=1) / np.sqrt(len(x)))) if len(x) > 2 and x.std(ddof=1) > 0 else 0.0


def evaluate(cells, null_sets, book, cal, ddd, family, report_only=()):
    """cells: {name: DataFrame(date, usd, usd_stress)}; null_sets: list (N_NULL) of {name: DataFrame(date, usd)}.
    Prints Stage A per cell and returns the pass list."""
    import numpy as np
    import pandas as pd
    wf_cal = cal[(cal >= pd.Timestamp(WF[0])) & (cal <= pd.Timestamp(WF[1]))]
    ddi = set(ddd)

    def wf(df, col="usd"):
        return df[(df.date >= pd.Timestamp(WF[0])) & (df.date <= pd.Timestamp(WF[1]))]

    def daily(df, col="usd", lo=WF[0], hi=WF[1]):
        c = cal[(cal >= pd.Timestamp(lo)) & (cal <= pd.Timestamp(hi))]
        return df.groupby("date")[col].sum().reindex(c, fill_value=0.0)

    max_t, max_dd = [], []
    for ns in null_sets:
        max_t.append(max(tstat(wf(df).usd) for df in ns.values()))
        max_dd.append(max(float(wf(df)[wf(df).date.isin(ddi)].usd.sum()) for df in ns.values()))
    t95, dd95 = float(np.percentile(max_t, 95)), float(np.percentile(max_dd, 95))
    print("\n%s family null (%d reps): 95th pct of max WF t %.2f | of max drawdown-day sum $%.0f | #463 drawdown days %d"
          % (family, len(null_sets), t95, dd95, len(ddi)))
    passes = []
    for name, df in cells.items():
        W = wf(df)
        s = daily(df)
        sc = score(s, *WF)
        ss = score(daily(df, "usd_stress"), *WF)
        gp, gl = W.usd[W.usd > 0].sum(), -W.usd[W.usd < 0].sum()
        pf = gp / gl if gl > 0 else float("inf")
        t = tstat(W.usd)
        yrs = W.groupby(np.minimum(((W.date - pd.Timestamp(WF[0])).dt.days / 365.25).astype(int), 8)).usd.sum()
        yrs = yrs.reindex(range(9), fill_value=0.0)
        Wd = W[W.date.isin(ddi)].groupby("date").usd.sum()
        dsum = float(Wd.sum())
        dsum_x3 = float(Wd.sort_values().iloc[:-3].sum()) if len(Wd) > 3 else 0.0
        x20 = W[(W.date < pd.Timestamp(X20[0])) | (W.date > pd.Timestamp(X20[1]))].usd.sum()
        E = df[(df.date >= pd.Timestamp(EARLY[0])) & (df.date <= pd.Timestamp(EARLY[1]))]
        early = float(E.usd.sum()) if len(E) else float("nan")
        best_day = s.max()
        earner = dsum > 0 and dsum_x3 > 0 and dsum > dd95
        x22 = W[(W.date < pd.Timestamp(X22[0])) | (W.date > pd.Timestamp(X22[1]))].usd.sum()
        bw = book[(book.index >= pd.Timestamp(C_WIN[0])) & (book.index <= pd.Timestamp(C_WIN[1]))]
        sw = s[(s.index >= pd.Timestamp(C_WIN[0])) & (s.index <= pd.Timestamp(C_WIN[1]))]
        c0 = 0.25 * float(bw.std()) / float(sw.std()) if float(sw.std()) > 0 else 0.0
        a2 = []
        for c in (c0, 0.5 * c0, 2.0 * c0):
            b = book.add(c * s, fill_value=0.0)
            a2.append((c,) + tuple(score(b, *WF)[k] for k in ("roc", "sor")))
        best = a2[0]                                   # judged at c (volatility only); 0.5c and 2c reported
        bars = {
            "a 100 trades": len(W) >= 100,
            "b map": sc["roc"] >= 15 or (sc["roc"] >= 5 and earner),
            "c PF 1.05": pf >= 1.05,
            "d t + null": t >= 2.0 and t > t95,
            "e stress net": ss["net"] > 0,
            "f ex best day": sc["net"] - best_day > 0,
            "g 6/9 years": int((yrs > 0).sum()) >= 6,
            "i ex Feb-Apr 2020": x20 > 0,
            "j 2010-16": (early > 0) if early == early else True,
            "k A2 book": best[1] >= A2_BAR["roc"] and best[2] >= A2_BAR["sor"],
        }
        ok = all(bars.values()) and name not in report_only
        print("\n== %s | WF trades %d net $%.0f ROC@$30k %.1f Sortino %.2f DD $%.0f PF %.2f t %.2f | stress net $%.0f"
              % (name, len(W), sc["net"], sc["roc"], sc["sor"], sc["dd"], pf, t, ss["net"]))
        print("   years %s | drawdown days $%.0f (ex 3 best $%.0f, null 95th $%.0f) | ex Feb-Apr 2020 $%.0f | ex 2022 $%.0f | 2010-16 %s"
              % (" ".join("%+.0fk" % (v / 1000) for v in yrs.values), dsum, dsum_x3, dd95, x20, x22,
                 "n/a (no data)" if early != early else "$%.0f" % early))
        print("   A2 book at c from volatility, then 0.5c, 2c (c, WF ROC, Sortino): %s" % " | ".join("%.3f: %.1f / %.3f" % r for r in a2))
        print("   BAR: %s -> %s" % (" | ".join("%s %s" % (k, "PASS" if v else "FAIL") for k, v in bars.items()),
                                    "REPORT ONLY (dilution check, cannot pass)" if name in report_only else
                                    ("PASSES STAGE A" if ok else "FAILS STAGE A")))
        if ok:
            passes.append(name)
    return passes
