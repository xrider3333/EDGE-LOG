"""Moved from a session scratchpad 2026-09-24 (ROC frontier hunt); results in RESEARCH_LEDGER.md rows 1.15 / 2.12-2.19.
Causal feature table for a standalone intraday direction model on NQ 5m RTH (db_noadj_rth).

INFORMATION TIME (the sentence the scan->file rule demands): every feature for decision k is computed
from bars that have CLOSED at or before bar k's close (bar timestamps are OPEN times; bar k closes at
ts[k] + 5 min). Daily quantities (ATR, SMA, prior-day stats) use COMPLETED prior sessions only. The
trade fills at bar k+1's OPEN. The target is the move from bar k+1's open to the open H bars later
(or the session's last close if that comes first). Nothing here reads a bar after k except the target.

Decision bars: the bars whose CLOSE lands on :00 / :30 from 10:00 to 15:30 ET (12 per full session).
"""
import sys, numpy as np, pandas as pd
sys.path.insert(0, r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG")
from augur_engine.data import find_master, load_master_arrays

def build(date_from="2010-06-07", date_to="2025-06-30", H=6, inst="NQ"):
    A = load_master_arrays(find_master(inst, "5m", "rth", "db_noadj_rth"), date_from=date_from, date_to=date_to)
    ts = pd.DatetimeIndex(A["index"]).tz_localize(None)
    o, h, l, c, v = A["open"], A["high"], A["low"], A["close"], A["volume"]
    day = A["day_id"]; n = len(c)
    # session bounds
    starts = np.r_[0, np.nonzero(np.diff(day))[0] + 1]; ends = np.r_[starts[1:], n]
    D = len(starts)
    dO = o[starts]; dC = c[ends - 1]
    dH = np.array([h[a:b].max() for a, b in zip(starts, ends)]); dL = np.array([l[a:b].min() for a, b in zip(starts, ends)])
    dN = ends - starts
    prevC = np.r_[np.nan, dC[:-1]]
    tr = np.maximum(dH - dL, np.maximum(np.abs(dH - prevC), np.abs(dL - prevC)))
    atr20 = pd.Series(tr).rolling(20).mean().shift(1).values          # prior 20 COMPLETED sessions
    atr5 = pd.Series(tr).rolling(5).mean().shift(1).values
    sma20 = pd.Series(dC).rolling(20).mean().shift(1).values
    sma50 = pd.Series(dC).rolling(50).mean().shift(1).values
    sma200 = pd.Series(dC).rolling(200).mean().shift(1).values
    pday_ret = np.r_[np.nan, (dC - dO)[:-1]]
    pday_clv = np.r_[np.nan, ((dC - dL) / np.maximum(dH - dL, 1e-9))[:-1]]
    pday_rng = np.r_[np.nan, (dH - dL)[:-1]]
    ret5d = pd.Series(dC).diff(5).shift(1).values
    # per-bar cumulative session state
    cum_v = np.zeros(n); cum_pv = np.zeros(n); hi_sf = np.zeros(n); lo_sf = np.zeros(n)
    for a, b in zip(starts, ends):
        tp = (h[a:b] + l[a:b] + c[a:b]) / 3.0
        cum_v[a:b] = np.cumsum(v[a:b]); cum_pv[a:b] = np.cumsum(tp * v[a:b])
        hi_sf[a:b] = np.maximum.accumulate(h[a:b]); lo_sf[a:b] = np.minimum.accumulate(l[a:b])
    vwap = cum_pv / np.maximum(cum_v, 1e-9)
    di = np.repeat(np.arange(D), dN)                 # session index of each bar
    k_in = np.arange(n) - starts[di]                 # bar-of-session
    # time-of-day relative volume: cum volume at this bar-of-session vs mean of prior 20 sessions at same k
    cv_tab = np.full((D, 80), np.nan)
    for d, (a, b) in enumerate(zip(starts, ends)):
        m = min(b - a, 80); cv_tab[d, :m] = cum_v[a:a + m]
    cv_ref = pd.DataFrame(cv_tab).rolling(20, min_periods=10).mean().shift(1).values
    # NOISE-style sigma: mean over prior 14 sessions of |close_k/open_day - 1| at the same bar-of-session
    mv_tab = np.full((D, 80), np.nan)
    for d, (a, b) in enumerate(zip(starts, ends)):
        m = min(b - a, 80); mv_tab[d, :m] = np.abs(c[a:a + m] / o[a] - 1.0)
    sig_ref = pd.DataFrame(mv_tab).rolling(14, min_periods=10).mean().shift(1).values
    # opening range = first 2 bars (10 min)
    orh = np.array([h[a:a + 2].max() for a in starts]); orl = np.array([l[a:a + 2].min() for a in starts])
    # 60-minute squeeze ratio on COMPLETED hourly RTH blocks (9:30-10:30,...) : BB(20,2) width / KC(20,1.5) width
    rows = []
    tod_close = (ts + pd.Timedelta(minutes=5))
    dec_mask = ((tod_close.minute % 30) == 0) & (tod_close.hour * 60 + tod_close.minute >= 600) & (tod_close.hour * 60 + tod_close.minute <= 930)
    idxs = np.nonzero(dec_mask)[0]
    # hourly closes list for squeeze: take bars closing on the half-hour boundary 10:30, 11:30, ... (RTH hours)
    hr_mask = ((tod_close.minute == 30) & (tod_close.hour >= 10) & (tod_close.hour <= 15)) | ((tod_close.hour == 16) & (tod_close.minute == 0))
    hr_idx = np.nonzero(hr_mask)[0]
    hr_c = c[hr_idx]
    # hourly high/low over each hourly block
    hr_h = np.array([h[max(0, j - 11):j + 1].max() for j in hr_idx]); hr_l = np.array([l[max(0, j - 11):j + 1].min() for j in hr_idx])
    sc = pd.Series(hr_c)
    bbw = 4 * sc.rolling(20).std()
    trh = np.maximum(hr_h - hr_l, np.maximum(np.abs(hr_h - np.r_[np.nan, hr_c[:-1]]), np.abs(hr_l - np.r_[np.nan, hr_c[:-1]])))
    kcw = 3.0 * pd.Series(trh).rolling(20).mean()
    sq_ratio = (bbw / kcw).values
    pos_hr = np.searchsorted(hr_idx, idxs, side="right") - 1      # last hourly block that CLOSED at or before k
    for j, k in enumerate(idxs):
        d = di[k]; a = starts[d]; b = ends[d]
        if k + 1 >= b:          # no next bar in session
            continue
        A20 = atr20[d]
        if not np.isfinite(A20) or A20 <= 0:
            continue
        e = min(k + 1 + H, b - 1)                   # exit bar open index (or last bar close)
        exit_px = o[e] if e < b - 1 or (k + 1 + H) <= b - 1 else c[b - 1]
        if k + 1 + H >= b:
            exit_px = c[b - 1]
        tgt = (exit_px - o[k + 1]) / A20
        kk = k_in[k]
        cvr = cum_v[k] / cv_ref[d, kk] if kk < 80 and np.isfinite(cv_ref[d, kk]) and cv_ref[d, kk] > 0 else np.nan
        sgr = sig_ref[d, kk] if kk < 80 else np.nan
        ph = pos_hr[j]
        sq = sq_ratio[ph] if ph >= 0 else np.nan
        rows.append(dict(
            k=k, d=d, date=ts[starts[d]].normalize(), tod=int((tod_close[k].hour * 60 + tod_close[k].minute - 600) // 30),
            dow=ts[k].dayofweek,
            r_open=(c[k] - o[a]) / A20, r_open_sig=((c[k] / o[a] - 1.0) / sgr) if (sgr and np.isfinite(sgr) and sgr > 0) else np.nan,
            r_pc=(c[k] - prevC[d]) / A20, gap=(o[a] - prevC[d]) / A20,
            r30=(c[k] - c[max(a, k - 6)]) / A20, r60=(c[k] - c[max(a, k - 12)]) / A20, r120=(c[k] - c[max(a, k - 24)]) / A20,
            vwd=(c[k] - vwap[k]) / A20, rng_sf=(hi_sf[k] - lo_sf[k]) / A20,
            pos_rng=(c[k] - lo_sf[k]) / max(hi_sf[k] - lo_sf[k], 1e-9),
            or_d=(c[k] - (orh[d] + orl[d]) / 2) / max(orh[d] - orl[d], 1e-9), or_w=(orh[d] - orl[d]) / A20,
            pd_ret=pday_ret[d] / A20, pd_clv=pday_clv[d], pd_rng=pday_rng[d] / A20, r5d=ret5d[d] / A20,
            tr20=(c[k] - sma20[d]) / A20, tr50=(c[k] - sma50[d]) / A20, tr200=(c[k] - sma200[d]) / A20,
            rv=atr5[d] / A20, cvr=cvr, sq=sq, atr_pts=A20,
            tgt=tgt, tgt_pts=exit_px - o[k + 1], fill=o[k + 1], exit_i=e))
    F = pd.DataFrame(rows)
    return F

if __name__ == "__main__":
    import time, os
    t0 = time.time()
    F = build()
    CACHE = os.environ.get("EDGELOG_ROCFRONTIER", r"C:\EdgeLog\_anatomy_cache\rocfrontier")
    out = os.path.join(CACHE, "feats_nq5_h6.pkl")
    F.to_pickle(out)
    print(F.shape, "built in %.0fs ->" % (time.time() - t0), out)
    print(F.describe().T[["mean", "std", "min", "max"]].round(3).to_string())
