"""
ROUND 64 - "breakeven at +1R, then ride" on ORB #314 (crown) and #234 (BOOK #463's ORB leg). PRE-REGISTERED.
Rule and bar: docs/PREREG_orb_be1r_ride_2026-10-02.md (pushed before any figure for the new exit existed).

    python tools/orb_r64_be1r_ride.py          leg-level bar for P1 and P2, decomposition, then BOOK #463 (P2 seat)

Owner idea 2026-10-02 via MANAGER: once a bar CLOSES at +1R, move the stop to entry, then ride to the
strategy's normal exit / the close instead of a fixed target. ORB_3_6.py already does both: be_after_R arms on
a finished bar's close and acts from the next bar; target_R = 0 means no take-profit (stop or session close).
Judged on ROC dollars at a $30k daily-valued drawdown, walk-forward and lockbox apart, never on R figures.
Run from the shared checkout (BACKTEST_SPEED rule 3: worktrees have no master registry).
"""
import os
import sys

ROOT = r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"
sys.path.insert(0, ROOT)
os.chdir(ROOT)
os.environ.setdefault("AUGUR_TRIAL_CACHE", "1")
UID = "IO0K35JpLIcH9YK4C0pMNYUzZOM2"

FN = "augur_strategies/ORB_3_6.py"
COST, MULT = 0.533, 20.0
WINDOW = ("2010-06-07", "2026-08-13")
WF = ("2016-07-13", "2025-08-12")
LB = ("2025-08-13", "2026-08-13")
BASE = dict(or_bars=2, trade_mode="First-candle dir", close_confirm=True, partial_exit_R=0.0, trail_bars=0,
            flat_eod=True, skip_holidays=True, breakout_buf=0.25, stop_frac=2.0, target_R=5.5,
            be_after_R=1.0, atr_filter=0.7, vpace_filter=0.7)
P234 = dict(BASE)
P314 = dict(BASE, stop_frac=2.5, target_R=5.0, be_after_R=0.5, atr_filter=0.75, vpace_filter=0.8)
PARITY = {"#314": (P314, 168, 4605.081), "#234": (P234, 178, 4447.126)}      # stored lockbox trades / points
ARMS = [("P1", "#314 + breakeven 1.0R + ride (no target)", "#314", dict(P314, be_after_R=1.0, target_R=0.0), True),
        ("P2", "#234 + ride (no target; breakeven already 1.0R)", "#234", dict(P234, target_R=0.0), True),
        ("D1", "#314 + breakeven 1.0R, 5.0R target kept (REPORTED ONLY)", "#314", dict(P314, be_after_R=1.0), False),
        ("D2", "#314 breakeven 0.5R kept + ride (REPORTED ONLY)", "#314", dict(P314, target_R=0.0), False)]

# BOOK #463 stretches (round 63) on the unified convention (BOOK.md 10r): reference WF 93.8 / LB 155.5
BOOK_WF = ("2016-07-13", "2025-06-29")
BOOK_LB = ("2025-06-30", "2026-06-30")


def main():
    import numpy as np
    import pandas as pd
    from augur_engine.engine import run_backtest
    from augur_engine.data import find_master, load_master_arrays

    A = load_master_arrays(find_master("NQ", "5m", "rth", "db_noadj_rth"), date_from=WINDOW[0], date_to=WINDOW[1])
    idx = pd.DatetimeIndex(A["index"])
    day = (idx.tz_localize(None) if idx.tz is not None else idx).normalize()
    H, L = np.asarray(A["high"], float), np.asarray(A["low"], float)
    first_bar = pd.Series(np.arange(len(idx))).groupby(day.values).min()
    cal = pd.DatetimeIndex(sorted(set(day)))

    def trades(params):
        r = run_backtest(FN, arrays=A, params=params, cost_pts=COST, return_trades=True)
        rows = []
        for (ei, xi, pnl, side, entry) in r["trades"]:
            fb = int(first_bar[day[ei]])
            rng = H[fb:fb + params["or_bars"]].max() - L[fb:fb + params["or_bars"]].min()
            risk = params["stop_frac"] * rng
            rows.append(dict(ei=int(ei), xi=int(xi), d=day[xi], pts=pnl, usd=pnl * MULT, risk=risk,
                             R=pnl / risk if risk > 0 else np.nan, eod=bool(xi == len(idx) - 1 or day[xi + 1] != day[xi]),
                             tgt=bool(params["target_R"] > 0 and abs(pnl - (params["target_R"] * risk - COST)) < 1e-6)))
        return pd.DataFrame(rows)

    def stretch(T, lo, hi):
        c = cal[(cal >= pd.Timestamp(lo)) & (cal <= pd.Timestamp(hi))]
        s = T.groupby("d").usd.sum().reindex(c, fill_value=0.0)
        cum = s.cumsum()
        dd = float((cum.cummax().clip(lower=0) - cum).max())
        yrs = (c[-1] - c[0]).days / 365.25
        neg = s[s < 0]
        sor = float(s.mean() / np.sqrt((neg ** 2).sum() / len(s)) * np.sqrt(252)) if len(neg) else np.inf
        sub = T[(T.d >= pd.Timestamp(lo)) & (T.d <= pd.Timestamp(hi))]
        roc = 30.0 * (s.sum() / yrs) / dd if dd > 0 else np.inf
        return dict(roc=roc, sor=sor, net=float(s.sum()), dd=dd, n=len(sub),
                    ex_top=float(sub.usd.sum() - sub.usd.max()) if len(sub) else 0.0)

    # ── PARITY: each twin's COLD lockbox replica (data from the lockbox's first day - how #314's stored
    #    figure was measured, before the v73.841 warm-start fix) reproduces the stored lockbox to 0.01 points,
    #    or the round stops (prereg addendum 1). The round itself uses the warm series from 2010.
    A_cold = load_master_arrays(find_master("NQ", "5m", "rth", "db_noadj_rth"), date_from=LB[0], date_to=LB[1])
    twins = {}
    for name, (p, n_lb, pts_lb) in PARITY.items():
        rc = run_backtest(FN, arrays=A_cold, params=p, cost_pts=COST, return_trades=True)["trades"]
        ok = len(rc) == n_lb and abs(sum(t[2] for t in rc) - pts_lb) < 0.01
        T = trades(p)
        lb = T[(T.d >= pd.Timestamp(LB[0])) & (T.d <= pd.Timestamp(LB[1]))]
        print("PARITY %s cold lockbox replica: %d trades, %.3f points (stored %d / %.3f) -> %s | warm lockbox used: %d / %.3f"
              % (name, len(rc), sum(t[2] for t in rc), n_lb, pts_lb, "EXACT" if ok else "MISMATCH - stop",
                 len(lb), lb.pts.sum()), flush=True)
        if not ok:
            sys.exit(2)
        twins[name] = T

    def show(label, T):
        w, l = stretch(T, *WF), stretch(T, *LB)
        print("  %-44s WF ROC@$30k %6.1f%%/yr Sortino %5.2f net $%9.0f DD $%7.0f n %4d | LB ROC@$30k %6.1f Sortino %5.2f "
              "net $%8.0f DD $%7.0f n %3d ex-top $%+8.0f" % (label, w["roc"], w["sor"], w["net"], w["dd"], w["n"],
                                                              l["roc"], l["sor"], l["net"], l["dd"], l["n"], l["ex_top"]))
        return w, l

    def r_figs(T):
        los = T[T.usd < 0]
        return ("avg R %+.3f | avg loss $%.0f | scratches (|P&L| < 1 pt) %d | target hits %d | session-close exits %d"
                % (T.R.mean(), los.usd.mean() if len(los) else 0, int((T.pts.abs() < 1.0).sum()), int(T.tgt.sum()),
                   int(T.eod.sum())))

    arms = {}
    for key, label, twin, params, gated in ARMS:
        T, Tw = trades(params), twins[twin]
        arms[key] = T
        print("\n== %s  %s   (twin %s)" % (key, label, twin))
        tw_w, tw_l = show("twin " + twin, Tw)
        a_w, a_l = show("arm", T)
        print("  R figures (NEVER judge - the breakeven trap): twin %s" % r_figs(Tw))
        print("                                               arm  %s" % r_figs(T))
        m = Tw[["ei", "usd"]].merge(T[["ei", "usd"]], on="ei", suffixes=("_t", "_a"))
        d = m.usd_a - m.usd_t
        t = d.mean() / (d.std(ddof=1) / np.sqrt(len(d))) if d.std(ddof=1) > 0 else 0.0
        print("  paired per trade: %d matched of %d/%d, mean %+.1f, t %.2f, total %+.0f, without the best %+.0f, %d changed"
              % (len(m), len(Tw), len(T), d.mean(), t, d.sum(), d.sum() - d.max(), int((d.abs() > 1e-9).sum())))
        yd = (T.groupby(T.d.dt.year).usd.sum() - Tw.groupby(Tw.d.dt.year).usd.sum()).reindex(range(2011, 2026)).fillna(0)
        print("  vs twin by calendar year 2011-2025: $%+.0f, %d of 15 years better; %s"
              % (yd.sum(), int((yd > 0).sum()), " ".join("%d:%+.0fk" % (y, v / 1000) for y, v in yd.items())))
        if not gated:
            print("  (REPORTED ONLY - no bar)")
            continue
        bars = [a_w["roc"] > tw_w["roc"] and a_l["roc"] > tw_l["roc"],
                a_w["sor"] > tw_w["sor"] and a_l["sor"] > tw_l["sor"],
                a_w["n"] >= 100 and a_l["n"] >= 50,
                a_l["ex_top"] > 0]
        print("  BAR: ROC both %s | Sortino both %s | 100/50 trades %s | lockbox ex-top > 0 %s -> %s"
              % tuple(["PASS" if b else "FAIL" for b in bars]
                      + ["CLEARS - goes to Auto-Validate" if all(bars) else "DOES NOT CLEAR"]))

    book(arms)


def book(arms):
    """BOOK #463 with its ORB leg swapped (reported; P2 is the book leg). Same machinery as round 63."""
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
    legs, dfrom, dto = d["legs"], d["date_from"], d["date_to"]
    oi = [i for i, l in enumerate(legs) if str(l["strategy"]).startswith("ORB")]
    assert len(oi) == 1
    oi = oi[0]

    def series(pairs):
        s = pd.Series([float(a) for _, a in pairs], index=pd.to_datetime([str(x)[:10] for x, _ in pairs]))
        return s.groupby(level=0).sum().sort_index()

    marked = []
    for leg in legs:
        tr, info = B._leg_trades(leg, dfrom, dto)
        m = info.get("_mtm_day")
        marked.append(series(m if m is not None else tr))
    rest = pd.concat([m for i, m in enumerate(marked) if i != oi], axis=1).fillna(0).sum(axis=1)
    books = {"#463 as stored (#234 leg)": rest.add(marked[oi], fill_value=0).sort_index()}
    for key, p in (("#234 re-run through ORB_3_6.py (sanity)", P234), ("P2 #234 + ride", dict(P234, target_R=0.0)),
                   ("P1 #314 + BE 1.0 + ride (reported)", dict(P314, be_after_R=1.0, target_R=0.0))):
        tr, info = B._leg_trades(dict(legs[oi], strategy="ORB_3_6.py", params=p), dfrom, dto)
        books[key] = rest.add(series(tr), fill_value=0).sort_index()

    def score(s, lo, hi):        # unified convention: valued-daily net + DD inside the stretch, (last-first)/365.25
        z = s[(s.index >= pd.Timestamp(lo)) & (s.index <= pd.Timestamp(hi))]
        cum = z.cumsum()
        dd = float((cum.cummax().clip(lower=0) - cum).max())
        yrs = (z.index[-1] - z.index[0]).days / 365.25
        neg = z[z < 0]
        return 30.0 * (z.sum() / yrs) / dd, float(z.mean() / np.sqrt((neg ** 2).sum() / len(z)) * np.sqrt(252)), z.sum(), dd

    print("\n== BOOK #463 with the ORB leg swapped (reference WF 93.8 / LB 155.5 %/yr at $30k)")
    inc = books["#463 as stored (#234 leg)"]
    inc_sc = {k: score(inc, *w) for k, w in (("WF", BOOK_WF), ("LB", BOOK_LB))}
    inc_y = inc.groupby(inc.index.year).sum()
    for name, s in books.items():
        sc = {k: score(s, *w) for k, w in (("WF", BOOK_WF), ("LB", BOOK_LB))}
        print("  %-42s WF ROC@$30k %6.1f Sortino %4.2f DD $%7.0f | LB ROC@$30k %6.1f Sortino %4.2f DD $%7.0f"
              % ((name,) + sc["WF"][:2] + (sc["WF"][3],) + sc["LB"][:2] + (sc["LB"][3],)))
        if name.startswith("#"):
            continue
        dy = (s.groupby(s.index.year).sum() - inc_y).reindex(range(2011, 2026)).fillna(0)
        bars = [sc["WF"][0] > inc_sc["WF"][0] and sc["LB"][0] > inc_sc["LB"][0],
                sc["WF"][1] > inc_sc["WF"][1] and sc["LB"][1] > inc_sc["LB"][1], dy.sum() >= 0]
        print("    by calendar year 2011-2025 $%+.0f (%d of 15 better) | book bar: ROC both %s, Sortino both %s, years %s"
              % (dy.sum(), int((dy > 0).sum()), *["PASS" if b else "FAIL" for b in bars]))


if __name__ == "__main__":
    main()
