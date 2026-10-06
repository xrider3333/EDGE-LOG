"""FRONTIER #97 follow-up: is there a one-day stamp lag between #463's UTC-day rows and RESMOM's stock-session P&L?
Reads only the pinned WF file (resmom_cells_daily_wf.csv, sha bed7bf8b) and ES RTH daily closes (WF dates only; no lockbox).
(1) ES lag test: which session lag of ES's daily move each series co-moves with (the book's rows folded onto sessions).
(2) the line's numbers and RES's DO with RES shifted -1 / 0 / +1 session.
(3) weekly resolution: the line on weekly marks and DO over whole DD weeks (a one-day shift inside a week cannot move them)."""
import hashlib, os, sys
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import r11_risk as R11  # noqa: E402
import r12_mdl as R12  # noqa: E402

F = r"C:\EdgeLog\_anatomy_cache\rocfrontier\resmom_r1\resmom_cells_daily_wf.csv"
SHA = "bed7bf8b98d201894471cd3e72bd146bb87260c6cc8d1ac54b8167f923d41819"
ESF = r"C:\EdgeLog\_anatomy_cache\rocfrontier\ES_daily_rth.csv"
W = 0.264
raw = open(F, "rb").read()
assert hashlib.sha256(raw).hexdigest() == SHA, "pinned file changed"
df = pd.read_csv(F)
dates = pd.DatetimeIndex(pd.to_datetime(df["date"].astype(str).str[:10]))
book, res, rawm = (df[c].to_numpy(float) for c in ("book_mtm", "RES", "RAW"))
assert dates.max() < pd.Timestamp("2025-06-30")


def st(x, d=dates):
    s = R11.stats(x, d)
    return f"ROC {s['roc']:.2f} Sortino {s['sort']:.3f} DD ${s['max_dd']:,.0f} net/yr ${s['net'] / s['years']:,.0f}"


print("rows", len(df), dates.min().date(), "..", dates.max().date(), "| weekday rows", int((dates.weekday < 5).sum()),
      "| Sat", int((dates.weekday == 5).sum()), "| Sun", int((dates.weekday == 6).sum()))
print("RES / RAW non-zero on weekend rows:", int((res[dates.weekday >= 5] != 0).sum()), int((rawm[dates.weekday >= 5] != 0).sum()),
      "| book non-zero on Sat / Sun rows:", int((book[dates.weekday == 5] != 0).sum()), int((book[dates.weekday == 6] != 0).sum()))
print("#463 alone      :", st(book))
print("#463 + 0.264 RES:", st(book + W * res))
S = R12.Stretch(book, dates, None, dates.min(), dates.max())
print(R12.describe("#463 WF", S))
rho, do = R12.realised(np.vstack([res, W * res, rawm]), S)
print(f"RES rho_dd {rho[0]:+.3f} | DO at 1x {do[0]:.3f}, at 0.264x {do[1]:.3f} | RES $ over DD days {res[S.dd].sum():,.0f} | RAW DO {do[2]:.3f}")

# ---- (1) ES lag test on the session calendar
E = pd.read_csv(ESF)
E["d"] = pd.to_datetime(E["d"])
E = E[(E["d"] >= dates.min() - pd.Timedelta(days=10)) & (E["d"] <= dates.max())].sort_values("d").reset_index(drop=True)
seam = E["seam"].astype(str).str.lower().eq("true").to_numpy()
dc = E["c"].diff().to_numpy()
print("ES sessions", len(E), "| seam rows", int(seam.sum()), "| median |move| on seams", np.nanmedian(np.abs(dc[seam])) if seam.any() else None,
      "elsewhere", np.nanmedian(np.abs(dc[~seam])))
dc[seam] = np.nan                                         # a seam move may carry the roll gap: left out
sess = pd.DatetimeIndex(E["d"])
ses_set = set(sess)
on_session = np.array([d in ses_set for d in dates])
print("book rows on an ES session:", int(on_session.sum()), "| weekday rows that are not ES sessions:",
      int(((dates.weekday < 5) & ~on_session).sum()), "| RES non-zero there:", int((res[(dates.weekday < 5) & ~on_session] != 0).sum()))


def fold(x, nxt=True):
    """book rows -> ES sessions: a session row is itself; any other row joins the NEXT session (nxt) or the PREVIOUS one"""
    k = sess.searchsorted(dates, side="left" if nxt else "right") - (0 if nxt else 1)
    ok = (k >= 0) & (k < len(sess))
    return np.bincount(k[ok], weights=np.asarray(x, float)[ok], minlength=len(sess))


def lagcorr(a, b, lags=range(-3, 4)):
    out = {}
    for L in lags:                                         # corr(a[s], b[s + L])
        if L >= 0:
            x, y = a[:len(a) - L], b[L:]
        else:
            x, y = a[-L:], b[:len(b) + L]
        m = np.isfinite(x) & np.isfinite(y)
        out[L] = np.corrcoef(x[m], y[m])[0, 1]
    return " ".join(f"{L:+d}:{v:+.3f}" for L, v in out.items())


inwf = (sess >= dates.min()) & (sess <= dates.max())
for lab, nxt in (("weekend/holiday rows -> NEXT session", True), ("weekend/holiday rows -> PREVIOUS session", False)):
    bS, rS, aS = fold(book, nxt), fold(res, nxt), fold(rawm, nxt)
    es = np.where(inwf, dc, np.nan)
    print(f"[{lab}] corr(series[s], ES move[s+L]):")
    print("   #463 book:", lagcorr(np.where(inwf, bS, np.nan), es))
    print("   RES      :", lagcorr(np.where(inwf, rS, np.nan), es))
    print("   RAW      :", lagcorr(np.where(inwf, aS, np.nan), es))
    print("   corr(book[s], RES[s+L]):", lagcorr(np.where(inwf, bS, np.nan), np.where(inwf, rS, np.nan)))

# ---- (2) the line with RES shifted by whole sessions (on session rows only)
srow = np.flatnonzero(on_session)                         # book rows that are ES sessions, in order
for sh in (-1, 0, 1):
    r2 = np.zeros(len(res))
    v = res[srow]
    if sh > 0:
        r2[srow[sh:]] = v[:-sh]                          # RES of session s booked on session s+1 (RES one day LATE)
    elif sh < 0:
        r2[srow[:sh]] = v[-sh:]                          # RES of session s booked on session s-1 (one day EARLY)
    else:
        r2 = res.copy()
    rho2, do2 = R12.realised(np.vstack([r2]), S)
    print(f"RES shifted {sh:+d} session: line {st(book + W * r2)} | DO {do2[0]:.3f} rho_dd {rho2[0]:+.3f} | $ on DD days {r2[S.dd].sum():,.0f}")

# ---- (3) weekly resolution
wk = pd.Series(dates).dt.to_period("W-FRI")               # Sat / Sun rows join the week that ends the NEXT Friday
wkS = pd.Series(book).groupby(wk.values).sum(); wkR = pd.Series(res).groupby(wk.values).sum()
wd = pd.DatetimeIndex([p.end_time.normalize() for p in wkS.index])
for lab, x in (("#463 alone", wkS.to_numpy()), ("#463 + 0.264 RES", (wkS + W * wkR).to_numpy())):
    s = R11.stats(x, wd)
    dn = np.sqrt(np.mean(np.minimum(x, 0) ** 2))
    print(f"WEEKLY marks {lab}: ROC {s['roc']:.2f} DD ${s['max_dd']:,.0f} net/yr ${s['net'] / s['years']:,.0f} weekly Sortino x sqrt(52) {x.mean() / dn * np.sqrt(52):.3f}")
wr = S.wk_rows
print(f"DO over whole ISO DD weeks ({S.n_dd_weeks} weeks, {len(wr)} rows): RES {res[wr].sum() / -book[wr].sum():.3f} "
      f"(RES $ {res[wr].sum():,.0f} vs book loss ${-book[wr].sum():,.0f}) | daily-DD-day DO {do[0]:.3f}")
Sw = R12.Stretch(wkS.to_numpy(), wd, None, wd.min(), wd.max())
print(R12.describe("#463 on weekly marks (Fri-ending weeks)", Sw))
print(f"RES over the weekly-mark DD weeks: ${wkR.to_numpy()[Sw.dd].sum():,.0f} of the book's ${-wkS.to_numpy()[Sw.dd].sum():,.0f} loss -> DO "
      f"{wkR.to_numpy()[Sw.dd].sum() / -wkS.to_numpy()[Sw.dd].sum():.3f}; episodes helped {sum(1 for e in Sw.qual if wkR.to_numpy()[e['i0']:e['it'] + 1].sum() > 0)} of {len(Sw.qual)}")
