"""
ROUND 65 - breakout-bar participation SIZE tilt on ORB #314 (crown) and #234 (BOOK #463's ORB leg). PRE-REGISTERED.
Rule and bar: docs/PREREG_orb_rvol_tilt_2026-10-04.md (reviewed by MANAGER before any figure existed).

    python tools/orb_r65_rvol_tilt.py            STAGE A of the pre-registered run (walk-forward only; no lockbox)
    python tools/orb_r65_rvol_tilt.py --smoke    code-path check on PERMUTED volumes (no real effect can show)

RVOL = the breakout bar's volume / mean volume of the same bar slot over the previous 20 sessions. The entry
fills at that bar's CLOSE (close_confirm=True, ORB_3_6.py: entry = sc[k]), so its volume is final at entry -
as known as the close that triggers the trade. Size = RVOL's third among the arm's previous 250 trades (earlier
trades only): top 1.5x, bottom 0.5x, middle 1x; the first 250 trades and any trade without a reference are 1x.
Judged on ROC dollars at a $30k daily-valued drawdown (unified convention), walk-forward and lockbox apart, plus
the family-aware null (per-trade shuffle AND circular time-shift of the arm's own sizes). MANAGER's regime question
is answered descriptively (no bar). Run from the shared checkout (BACKTEST_SPEED rule 3).
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
BOOK_WF = ("2016-07-13", "2025-06-29")
BOOK_LB = ("2025-06-30", "2026-06-30")
REF_SESSIONS, RANK_WINDOW, HI, LO = 20, 250, 1.5, 0.5
N_SHUFFLE, N_BOOT, SEED = 500, 1000, 65
SMOKE = "--smoke" in sys.argv
if SMOKE:
    N_SHUFFLE = 10
BASE = dict(or_bars=2, trade_mode="First-candle dir", close_confirm=True, partial_exit_R=0.0, trail_bars=0,
            flat_eod=True, skip_holidays=True, breakout_buf=0.25, stop_frac=2.0, target_R=5.5,
            be_after_R=1.0, atr_filter=0.7, vpace_filter=0.7)
P234 = dict(BASE)
P314 = dict(BASE, stop_frac=2.5, target_R=5.0, be_after_R=0.5, atr_filter=0.75, vpace_filter=0.8)
ARMS = [("P1", "#314 crown + breakout-bar volume tilt", "#314", P314, 168, 4605.081),
        ("P2", "#234 (BOOK #463 leg) + breakout-bar volume tilt", "#234", P234, 178, 4447.126)]


def main():
    import numpy as np
    import pandas as pd
    from augur_engine.engine import run_backtest
    from augur_engine.data import find_master, load_master_arrays

    M = find_master("NQ", "5m", "rth", "db_noadj_rth")
    A = load_master_arrays(M, date_from=WINDOW[0], date_to=WINDOW[1])
    A_cold = load_master_arrays(M, date_from=LB[0], date_to=LB[1])
    idx = pd.DatetimeIndex(A["index"])
    day = (idx.tz_localize(None) if idx.tz is not None else idx).normalize()
    H, L, V = (np.asarray(A[k], float) for k in ("high", "low", "volume"))
    if SMOKE:   # code-path check only: volumes permuted, so no real effect can show; figures are meaningless
        V = np.random.default_rng(0).permutation(V)
        print("SMOKE RUN - volumes PERMUTED, every figure below is meaningless", flush=True)
    pos = pd.Series(np.arange(len(idx)))
    first_bar = pos.groupby(day.values).min()
    slot = (pos - first_bar.reindex(day.values).values).values.astype(int)       # bar number after 09:30
    cal = pd.DatetimeIndex(sorted(set(day)))
    # session states known BEFORE the session (REPORTED ONLY - MANAGER's regime question)
    C = np.asarray(A["close"], float)
    sess = pd.DataFrame({"d": day, "h": H, "l": L, "c": C}).groupby("d").agg(h=("h", "max"), l=("l", "min"), c=("c", "last"))
    rv20 = np.log(sess.c).diff().rolling(20).std().shift(1)
    rv_third = pd.Series("none", index=sess.index, dtype=object)
    for n in range(250, len(sess)):
        prior, x = rv20.iloc[n - 250:n].dropna(), rv20.iloc[n]
        if len(prior) >= 125 and x == x:
            q1, q2 = np.quantile(prior, [1 / 3, 2 / 3])
            rv_third.iloc[n] = "high" if x > q2 else ("low" if x < q1 else "mid")
    srng = sess.h - sess.l
    a5, m60 = srng.shift(1).rolling(5).mean(), srng.shift(1).rolling(60).median()
    rolls = pd.read_csv(os.path.join(ROOT, "tools", "data", "rolls_NQ.csv"))
    roll_wk = pd.Series(False, index=sess.index)
    for sw in pd.to_datetime(rolls.switch_et.str[:10]):
        after = sess.index[sess.index > sw][:5]
        roll_wk.loc[after] = True
    # causal per-slot reference: mean of the same slot over the PREVIOUS 20 sessions (NaN-aware)
    piv = pd.DataFrame({"d": day, "s": slot, "v": V}).pivot_table(index="d", columns="s", values="v", aggfunc="sum")
    ref = piv.rolling(REF_SESSIONS, min_periods=REF_SESSIONS // 2).mean().shift(1)   # NaN-aware, like the pace gate

    def trades(params, arrays=A):
        r = run_backtest(FN, arrays=arrays, params=params, cost_pts=COST, return_trades=True)
        rows = []
        for (ei, xi, pnl, side, entry) in r["trades"]:
            fb = int(first_bar[day[ei]])
            rng = H[fb:fb + params["or_bars"]].max() - L[fb:fb + params["or_bars"]].min()
            rf = ref.at[day[ei], slot[ei]] if slot[ei] in ref.columns else np.nan
            rows.append(dict(ei=int(ei), d=day[xi], usd=pnl * MULT, pts=pnl, side=side, orw=rng,
                             rvol=V[ei] / rf if rf == rf and rf > 0 else np.nan))
        T = pd.DataFrame(rows).sort_values("ei").reset_index(drop=True)
        size, third = np.ones(len(T)), np.full(len(T), "none", dtype=object)
        rv = T.rvol.values
        for n in range(len(T)):
            prior = rv[max(0, n - RANK_WINDOW):n]
            prior = prior[prior == prior]
            if n < RANK_WINDOW or len(prior) < RANK_WINDOW // 2 or rv[n] != rv[n]:
                continue
            lo_q, hi_q = np.quantile(prior, [1 / 3, 2 / 3])
            third[n] = "top" if rv[n] > hi_q else ("bottom" if rv[n] < lo_q else "middle")
            size[n] = HI if third[n] == "top" else (LO if third[n] == "bottom" else 1.0)
        T["size"], T["third"] = size, third
        return T

    def stretch(T, col, lo, hi):
        c = cal[(cal >= pd.Timestamp(lo)) & (cal <= pd.Timestamp(hi))]
        s = T.groupby("d")[col].sum().reindex(c, fill_value=0.0)
        cum = s.cumsum()
        dd = float((cum.cummax().clip(lower=0) - cum).max())
        yrs = (c[-1] - c[0]).days / 365.25
        neg = s[s < 0]
        sub = T[(T.d >= pd.Timestamp(lo)) & (T.d <= pd.Timestamp(hi))]
        return dict(roc=30.0 * (s.sum() / yrs) / dd if dd > 0 else np.inf,
                    sor=float(s.mean() / np.sqrt((neg ** 2).sum() / len(s)) * np.sqrt(252)) if len(neg) else np.inf,
                    net=float(s.sum()), dd=dd, n=len(sub), yrs=yrs)

    rng_ = np.random.default_rng(SEED)
    out = {}
    PRE = ("2010-06-07", "2016-07-12")
    X20 = ("2020-02-01", "2020-04-30")

    def daily(T, col, lo, hi, drop=None):
        c = cal[(cal >= pd.Timestamp(lo)) & (cal <= pd.Timestamp(hi))]
        if drop is not None:
            c = c[(c < pd.Timestamp(drop[0])) | (c > pd.Timestamp(drop[1]))]
        return T.groupby("d")[col].sum().reindex(c, fill_value=0.0)

    def roc_of(x, yrs):
        cum = np.cumsum(x, axis=-1)
        dd = (np.maximum.accumulate(np.maximum(cum, 0), axis=-1) - cum).max(axis=-1)
        return 30.0 * (x.sum(axis=-1) / yrs) / dd

    for key, label, twin, params, n_lb, pts_lb in ARMS:
        cold = run_backtest(FN, arrays=A_cold, params=params, cost_pts=COST, return_trades=True)["trades"]
        ok = len(cold) == n_lb and abs(sum(t[2] for t in cold) - pts_lb) < 0.01
        print("PARITY %s cold lockbox replica: %d trades, %.3f points (stored %d / %.3f) -> %s  (count + sum only; no "
              "lockbox figure is computed for the arm in Stage A)"
              % (twin, len(cold), sum(t[2] for t in cold), n_lb, pts_lb, "EXACT" if ok else "MISMATCH - stop"), flush=True)
        if not ok:
            sys.exit(2)
        T = trades(params)
        T["arm"] = T.usd * T["size"]
        out[key] = T
        print("\n== STAGE A (walk-forward only)  %s  %s   (raw twin %s)" % (key, label, twin))
        wf_t, wf_a = stretch(T, "usd", *WF), stretch(T, "arm", *WF)
        for nm, w in (("twin " + twin, wf_t), ("arm", wf_a)):
            print("  %-12s WF ROC@$30k %6.1f%%/yr  Sortino %5.2f  net $%9.0f  DD $%7.0f  trades %4d"
                  % (nm, w["roc"], w["sor"], w["net"], w["dd"], w["n"]))
        wfm = (T.d >= pd.Timestamp(WF[0])) & (T.d <= pd.Timestamp(WF[1]))
        c = float(T.loc[wfm, "size"].mean())
        print("  WF mean size c = %.3f | thirds in WF: %s" % (c, T.loc[wfm, "third"].value_counts().to_dict()))
        gain = wf_a["roc"] - wf_t["roc"]
        # family null (a): per-trade shuffle of the arm's own WF sizes; (b): circular time-shift >= 50 trades
        gains, sh, wsz, nw = [], [], T.loc[wfm, "size"].values, int(wfm.sum())
        for _ in range(N_SHUFFLE):
            S = T.copy()
            S.loc[wfm, "size"] = rng_.permutation(wsz)
            S["arm"] = S.usd * S["size"]
            gains.append(stretch(S, "arm", *WF)["roc"] - wf_t["roc"])
        for _ in range(N_SHUFFLE):
            S = T.copy()
            S.loc[wfm, "size"] = np.roll(wsz, int(rng_.integers(50, nw - 50)))
            S["arm"] = S.usd * S["size"]
            sh.append(stretch(S, "arm", *WF)["roc"] - wf_t["roc"])
        g95, s95 = float(np.percentile(gains, 95)), float(np.percentile(sh, 95))
        print("  WF ROC gain %+.2f | null (a) shuffle 95th %+.2f (median %+.2f) | null (b) time-shift 95th %+.2f (median %+.2f)"
              % (gain, g95, float(np.median(gains)), s95, float(np.median(sh))))
        # block bootstrap of the paired daily series (20-session blocks, 1,000 draws)
        da, dt = daily(T, "arm", *WF).values, daily(T, "usd", *WF).values
        n, yrs = len(da), wf_t["yrs"]
        nb = int(np.ceil(n / 20))
        starts = rng_.integers(0, n - 20 + 1, size=(N_BOOT, nb))
        ix = (starts[:, :, None] + np.arange(20)[None, None, :]).reshape(N_BOOT, -1)[:, :n]
        bdiff = roc_of(da[ix], yrs) - roc_of(dt[ix], yrs)
        b5 = float(np.percentile(bdiff, 5))
        print("  block bootstrap (20 sessions, %d draws): WF ROC difference 5th pct %+.2f, median %+.2f"
              % (N_BOOT, b5, float(np.median(bdiff))))
        # breadth: paired d = (size - c) x one-contract P&L, by WF year (nine years from 2016-07-13)
        W = T[wfm].copy()
        W["dd_"] = (W["size"] - c) * W.usd
        W["yr"] = np.minimum(((W.d - pd.Timestamp(WF[0])).dt.days / 365.25).astype(int), 8)
        by = W.groupby("yr").dd_.sum().reindex(range(9), fill_value=0.0)
        print("  breadth: paired d > 0 in %d of 9 WF years  (%s)"
              % (int((by > 0).sum()), " ".join("y%d:%+.0fk" % (k + 1, v / 1000) for k, v in by.items())))
        # without Feb-Apr 2020
        xa, xt = daily(T, "arm", *WF, drop=X20).values, daily(T, "usd", *WF, drop=X20).values
        g_x20 = float(roc_of(xa, yrs) - roc_of(xt, yrs))
        print("  WF ROC gain without Feb-Apr 2020: %+.2f (full %+.2f)" % (g_x20, gain))
        bars = [gain > 0, wf_a["sor"] > wf_t["sor"], wf_a["n"] >= 100, gain > g95 and gain > s95, b5 > 0,
                int((by > 0).sum()) >= 6, g_x20 > 0]
        print("  STAGE A BAR: ROC %s | Sortino %s | 100 trades %s | family null %s | block bootstrap %s | breadth %s | "
              "ex Feb-Apr 2020 %s -> %s"
              % tuple(["PASS" if x else "FAIL" for x in bars]
                      + ["PASSES STAGE A - Stage B (fenced Auto-Validate = the one lockbox read)" if all(bars)
                         else "FAILS STAGE A - no lockbox read"]))
        # REPORTED ONLY
        p_t, p_a = stretch(T, "usd", *PRE), stretch(T, "arm", *PRE)
        print("  (reported) 2010-06..2016-07 block: twin ROC %.1f / arm ROC %.1f (gain %+.1f; the tilt starts after 250 trades)"
              % (p_t["roc"], p_a["roc"], p_a["roc"] - p_t["roc"]))
        TW = T[T.d <= pd.Timestamp(WF[1])]                 # no lockbox-period trade enters any Stage A print
        yr_share = TW.groupby(TW.d.dt.year)["size"].agg(lambda z: "%d%%/%d%%" % (100 * (z == HI).mean(), 100 * (z == LO).mean()))
        print("  (reported) share at 1.5x / 0.5x by year: %s" % " ".join("%d:%s" % (y, v) for y, v in yr_share.items()))
        parts = []
        for th in ("bottom", "middle", "top", "none"):
            x = W[W.third == th].usd
            pf = x[x > 0].sum() / -x[x < 0].sum() if (x < 0).any() else np.inf
            parts.append("%s %d $%+.0f PF %.2f" % (th, len(x), x.mean() if len(x) else 0, pf))
        print("  (reported) WF by RVOL third: %s" % " | ".join(parts))
        tb, bb = W[W.third == "top"].usd, W[W.third == "bottom"].usd
        se = np.sqrt(tb.var(ddof=1) / len(tb) + bb.var(ddof=1) / len(bb))
        print("  (reported) power: WF top-minus-bottom $%+.0f a trade, standard error $%.0f (%.1f SE)"
              % (tb.mean() - bb.mean(), se, (tb.mean() - bb.mean()) / se))
        ok_r = T.rvol.notna()
        print("  (reported) rank corr RVOL vs opening-range width %.3f"
              % T.loc[ok_r, "rvol"].corr(T.loc[ok_r, "orw"], method="spearman"))
        F = T.copy()
        F["flt"] = np.where(F.third == "bottom", 0.0, F.usd)
        fw = stretch(F, "flt", *WF)
        print("  (reported, never adopted) skip-bottom-third FILTER: WF ROC %.1f Sortino %.2f" % (fw["roc"], fw["sor"]))

    book(out)


def book(out):
    """BOOK #463 with its ORB seat sized by the tilt (P2 = the seat's own #234 trades; P1 reported). Round 63 bar."""
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
    lo, hi = pd.Timestamp(dfrom), pd.Timestamp(dto)
    T = out["P2"]
    mine = T[(T.d >= lo) & (T.d <= hi)].groupby("d").usd.sum()
    diff = mine.sub(marked[oi], fill_value=0).abs().max()
    print("\nPARITY BOOK: the round's #234 trades vs #463's stored ORB leg, max daily difference $%.2f -> %s"
          % (diff, "EXACT" if diff < 1.0 else "MISMATCH - book part skipped"))
    if diff >= 1.0:
        return
    books = {"#463 as stored (#234 leg)": rest.add(marked[oi], fill_value=0).sort_index()}
    for key, nm in (("P2", "P2 #234 + volume tilt"), ("P1", "P1 #314 + volume tilt (reported)")):
        Z = out[key]
        books[nm] = rest.add(Z[(Z.d >= lo) & (Z.d <= hi)].groupby("d").arm.sum(), fill_value=0).sort_index()

    def score(s, a, b):
        z = s[(s.index >= pd.Timestamp(a)) & (s.index <= pd.Timestamp(b))]
        cum = z.cumsum()
        dd = float((cum.cummax().clip(lower=0) - cum).max())
        yrs = (z.index[-1] - z.index[0]).days / 365.25
        neg = z[z < 0]
        return 30.0 * (z.sum() / yrs) / dd, float(z.mean() / np.sqrt((neg ** 2).sum() / len(z)) * np.sqrt(252)), dd

    print("== BOOK #463 with the ORB seat sized - STAGE A, WALK-FORWARD ONLY on the book's own WF window %s..%s"
          % BOOK_WF)
    print("   (reference WF 93.8 at $30k; the book's lockbox 2025-06-30..2026-06-30 is read ONCE, by FRONTIER, after Stage B)")
    inc = books["#463 as stored (#234 leg)"]
    inc_wf = score(inc, *BOOK_WF)
    pre = lambda z: z[(z.index >= pd.Timestamp("2011-01-01")) & (z.index <= pd.Timestamp(BOOK_WF[1]))]
    inc_y = pre(inc).groupby(pre(inc).index.year).sum()
    for name, s in books.items():
        wf = score(s, *BOOK_WF)
        print("  %-34s WF ROC@$30k %6.1f  Sortino %4.2f  DD $%7.0f" % ((name,) + wf))
        if name.startswith("#"):
            continue
        dy = (pre(s).groupby(pre(s).index.year).sum() - inc_y).reindex(range(2011, 2026)).fillna(0)
        bars = [wf[0] > inc_wf[0], wf[1] > inc_wf[1], dy.sum() >= 0]
        print("    by calendar year 2011..2025-06-29 $%+.0f (%d of 15 better) | book WF readout: ROC %s, Sortino %s, years %s"
              % (dy.sum(), int((dy > 0).sum()), *["PASS" if x else "FAIL" for x in bars]))

if __name__ == "__main__":
    main()
