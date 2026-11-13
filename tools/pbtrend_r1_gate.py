"""PBTREND_1_0 POWER-FIRST GATE (owner order 11-13, board w121 PRICE-ACTION HUNT, TBIS lens). No trials.

Catalogue check: EMAPB_1_0 (1m EMA pullback, no drive condition) DEAD 27/27; DIP PB20 = daily pullback (DIP family);
"pullback entries miss 43-72% of fires" (TTM) was a pullback ENTRY on a TTM signal. This is different: an opening
DRIVE defines the day's direction, then the FIRST pullback to a mean level, entered on the resume bar.

PRE-REGISTERED (frozen before data; NQ 5m RTH db_noadj_rth, ET start-stamped bars):
  Drive: d = C(09:55 bar) - O(09:30). |d| >= k_drive x ATR14 daily (prior days) -> direction = sign(d). Else no trade.
  Level (knob): 'vwap' = session VWAP from 09:30 (typical price x volume); 'sma20' = mean of the last 20 5m closes.
  Pullback: from the 10:00 bar to the 13:00 bar, the FIRST bar whose low (long) / high (short) touches the level.
  Resume: within 6 bars after the touch (touch bar included as the prior bar), the first bar that CLOSES beyond the
  prior bar's high (long) / low (short). Cancel if price closes beyond the 09:30 open against the drive first.
  Entry: next bar's open. Stop: the pullback extreme since the touch (1R). Exit: stop or the 15:55 bar close.
  EV R = mean of (net pts / R pts) per trade. Net $/yr at 1 NQ ($20/pt, 0.533 pt round trip).
  RANDOM CONTROL (after-signal only): on every drive day (known at 10:00), enter at the open of a uniformly random bar
  from 10:05 to 13:00 in the drive direction, stop at the median real R in points, hold to close. 20 seeds.
  BOOK: book #463 WF+LB daily (cut 2025-06-30), 2016-07..2025-06, S33 book_add (scale = 0.25 x book sd / leg sd on
  2016-07..2018-06), lift = combo ROC@30k - book ROC@30k, folds of 8, P(lift), 200-draw no-edge control band.
Central: k_drive 0.3, level vwap. Grid: k_drive {0.2, 0.3, 0.5} x level {vwap, sma20}.
Hard bounds the file will carry: k_drive 0.1-1.0, resume_bars 2-12, window end 11:00-15:00.
"""
import itertools
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.environ.get("EDGELOG_REPO_ROOT") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, r"C:\EdgeLog\_anatomy_cache\opus_hunt1109\futures\S33")
from augur_engine.data import find_master, load_master_arrays  # noqa: E402
import bookadd as BA  # noqa: E402

COST, M = 0.533, 20.0
LAST = "2026-09-16"
CENTRAL = dict(k_drive=0.3, level="vwap")
GRID = dict(k_drive=[0.2, 0.3, 0.5], level=["vwap", "sma20"])


def load():
    A = load_master_arrays(find_master("NQ", "5m", "rth", "db_noadj_rth"), date_from="2010-06-07", date_to=LAST)
    idx = pd.DatetimeIndex(A["index"])
    df = pd.DataFrame({k: np.asarray(A[k], float) for k in ("open", "high", "low", "close", "volume")}, index=idx)
    df["d"] = idx.date
    df["hm"] = idx.strftime("%H:%M")
    ok = df.groupby("d")["hm"].agg(lambda s: s.iloc[0] == "09:30" and len(s) == 78)
    df = df[df["d"].map(ok)]
    tp = (df["high"] + df["low"] + df["close"]) / 3.0
    pv = (tp * df["volume"]).groupby(df["d"]).cumsum()
    vv = df["volume"].groupby(df["d"]).cumsum()
    df["vwap"] = pv / vv.replace(0, np.nan)
    df["sma20"] = df["close"].rolling(20, min_periods=20).mean()   # last 20 bars incl. prior session (causal)
    days = [(d, g) for d, g in df.groupby("d", sort=True)]
    dl = pd.DataFrame({"h": [g["high"].max() for _, g in days], "l": [g["low"].min() for _, g in days],
                       "c": [g["close"].iloc[-1] for _, g in days]}, index=[d for d, _ in days])
    pc = dl["c"].shift()
    tr = np.maximum(dl["h"] - dl["l"], np.maximum((dl["h"] - pc).abs(), (dl["l"] - pc).abs()))
    atr = tr.rolling(14).mean().shift(1)
    return days, atr


def real(days, atr, k_drive, level):
    rec, rs = {}, []
    for d, g in days:
        a = atr.get(d)
        if a is None or not np.isfinite(a):
            continue
        o, h, l, c = (g[k].to_numpy() for k in ("open", "high", "low", "close"))
        lv = g[level].to_numpy()
        hm = g["hm"].to_numpy()
        i955 = int(np.flatnonzero(hm == "09:55")[0])
        drive = c[i955] - o[0]
        if abs(drive) < k_drive * a:
            continue
        s = 1.0 if drive > 0 else -1.0
        rec[d] = None                                   # a drive day (known at 10:00)
        end = int(np.flatnonzero(hm == "13:00")[0])
        touch = None
        for j in range(i955 + 1, end + 1):
            if s * (c[j] - o[0]) < 0:
                break                                   # drive failed first
            if (s > 0 and l[j] <= lv[j]) or (s < 0 and h[j] >= lv[j]):
                touch = j
                break
        if touch is None:
            continue
        ext = l[touch] if s > 0 else h[touch]
        entry_i = None
        for j in range(touch + 1, min(touch + 7, len(c) - 1)):
            if s * (c[j] - o[0]) < 0:
                break
            ext = min(ext, l[j]) if s > 0 else max(ext, h[j])
            if (s > 0 and c[j] > h[j - 1]) or (s < 0 and c[j] < l[j - 1]):
                entry_i = j + 1
                break
        if entry_i is None or entry_i >= len(c):
            continue
        e = o[entry_i]
        R = s * (e - ext)
        if R <= 0:
            continue
        px = c[-1]
        for j in range(entry_i, len(c)):
            if (s > 0 and l[j] <= ext) or (s < 0 and h[j] >= ext):
                px = ext
                break
        pts = s * (px - e)
        rec[d] = (pts, R)
        rs.append(R)
    return rec, (float(np.median(rs)) if rs else np.nan)


def rand_ctrl(days, atr, k_drive, Rmed, seed):
    rng = np.random.default_rng(seed)
    out = {}
    for d, g in days:
        a = atr.get(d)
        if a is None or not np.isfinite(a):
            continue
        o, h, l, c = (g[k].to_numpy() for k in ("open", "high", "low", "close"))
        hm = g["hm"].to_numpy()
        i955 = int(np.flatnonzero(hm == "09:55")[0])
        drive = c[i955] - o[0]
        if abs(drive) < k_drive * a:
            continue
        s = 1.0 if drive > 0 else -1.0
        i = int(rng.integers(i955 + 2, int(np.flatnonzero(hm == "13:00")[0]) + 1))   # 10:05 .. 13:00 opens
        e = o[i]
        stop = e - s * Rmed
        px = c[-1]
        for j in range(i, len(c)):
            if (s > 0 and l[j] <= stop) or (s < 0 and h[j] >= stop):
                px = stop
                break
        out[d] = (s * (px - e), Rmed)
    return out


def stats(rec, years):
    tr = [v for v in rec.values() if isinstance(v, tuple)]
    n = len(tr)
    if not n:
        return dict(n=0, per_yr=0, g_c=np.nan, evr=np.nan, net_yr=0.0, daily=pd.Series(dtype=float))
    pts = np.array([t[0] for t in tr])
    R = np.array([t[1] for t in tr])
    daily = pd.Series({pd.Timestamp(d): (v[0] - COST) * M for d, v in rec.items() if isinstance(v, tuple)}).sort_index()
    return dict(n=n, per_yr=n / years, g_c=pts.sum() / (n * COST), evr=float(np.mean((pts - COST) / R)),
                net_yr=daily.sum() / years, win=float((pts - COST > 0).mean()), daily=daily)


def main():
    days, atr = load()
    years = (pd.Timestamp(days[-1][0]) - pd.Timestamp(days[0][0])).days / 365.25
    print("NQ 5m RTH %s .. %s  sessions %d  years %.2f" % (days[0][0], days[-1][0], len(days), years))
    rec, Rmed = real(days, atr, **CENTRAL)
    S = stats(rec, years)
    ndrive = len(rec)
    print("PBTREND central: drive days %d (%.1f/yr), trades %d (%.1f/yr), win %.1f%%, gross/cost %.2f, EV R %.3f, net $/yr %.0f,"
          " median R %.1f pts" % (ndrive, ndrive / years, S["n"], S["per_yr"], 100 * S["win"], S["g_c"], S["evr"], S["net_yr"], Rmed))
    C = [stats(rand_ctrl(days, atr, CENTRAL["k_drive"], Rmed, s), years) for s in range(20)]
    cg = np.array([c["g_c"] for c in C]); ce = np.array([c["evr"] for c in C]); cn = np.array([c["net_yr"] for c in C])
    print("RANDOM after-10:00 control (20 seeds): gross/cost median %.2f [%.2f..%.2f], EV R median %.3f, net $/yr median %.0f"
          % (np.median(cg), cg.min(), cg.max(), np.median(ce), np.median(cn)))
    a = S["daily"]
    yrs = sorted({d.year for d in a.index})
    print("folds (years) net>0: %d of %d" % (sum(a[a.index.year == y].sum() > 0 for y in yrs), len(yrs)))
    book = BA.read_book()
    out, bk, lg, combo = BA.book_add(book, a)
    band = BA.control_band(book, a)
    print("BOOK #463 (2016-07..2025-06): book ROC %.2f -> combo %.2f, lift %+.2f, folds won %d/8, P(lift) %.3f, corr %.3f,"
          " no-edge band 97.5th %.2f" % (out["book"]["roc30"], out["combo"]["roc30"], out["lift"], out["folds_won"],
                                        out["p_lift"], out["corr_daily"], np.percentile(band, 97.5)))
    print("\nGRID (spread only): k_drive level -> trades/yr gross/cost EV R net$/yr | ctrl g/c (seed 0)")
    for kd, lv in itertools.product(*GRID.values()):
        r, rm = real(days, atr, kd, lv)
        s = stats(r, years)
        c0 = stats(rand_ctrl(days, atr, kd, rm, 0), years)
        print("%.1f %-5s -> %5.1f %6.2f %7.3f %8.0f | %6.2f" % (kd, lv, s["per_yr"], s["g_c"], s["evr"], s["net_yr"], c0["g_c"]))


if __name__ == "__main__":
    main()
