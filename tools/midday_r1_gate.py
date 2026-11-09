"""MIDDAY_1_0 POWER-FIRST GATE (MANAGER #196/#197, 11-09). No trials, no tuning.

Design (posted to MANAGER #2207 before any bar was read):
  NQ 5m RTH no-adjust master, ET start-stamped bars. At the 10:30 ET close (close of the 10:25 bar), if
  |C(10:30) - O(09:30)| >= k_drive x ATR14(daily, prior days) go WITH the first-hour move. Stop = entry -/+
  k_stop x first-hour range (= 1R). Target = tgt_R x R. Time stop = t_exit ET. Same bar touching stop and
  target = STOP (conservative). CONTROL = same entry, same stop, no target, held to the 15:55 bar close.
  Cost 0.533 pt round trip, $20/pt, 1 contract.

Reports for the central cell (pre-registered: k_drive 0.4, k_stop 0.5, tgt 2R, t_exit 13:00) and the whole
small design grid (spread, not a pick): trades/yr, gross/cost, net $/yr, ROC@30k, per-year fold signs,
lead over the control by fold, bootstrap power line for the lead, and #314 overlap (shared trade days +
daily P&L correlation) from the cached #314 raw leg.
"""
import itertools
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.environ.get("EDGELOG_REPO_ROOT") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))
from augur_engine.data import find_master, load_master_arrays  # noqa: E402
from power_line import power_line, roc30  # noqa: E402

COST, M = 0.533, 20.0
LAST = "2026-09-16"
ORB314 = r"C:\EdgeLog\_anatomy_cache\frontier_combo\legs\X_orb314_raw.csv"
CENTRAL = (0.4, 0.5, 2.0, "13:00")
GRID = dict(k_drive=[0.2, 0.4, 0.6], k_stop=[0.5, 1.0], tgt=[1.0, 2.0, 3.0, 4.0], t_exit=["12:00", "13:00", "14:00"])


def days_table():
    A = load_master_arrays(find_master("NQ", "5m", "rth", "db_noadj_rth"), date_from="2010-06-07", date_to=LAST)
    idx = pd.DatetimeIndex(A["index"])
    df = pd.DataFrame({k: np.asarray(A[k], float) for k in ("open", "high", "low", "close")}, index=idx)
    df["d"] = idx.date
    df["hm"] = idx.strftime("%H:%M")
    out = []
    for d, g in df.groupby("d", sort=True):
        if g["hm"].iloc[0] != "09:30" or (g["hm"] == "10:25").sum() != 1 or len(g) < 70:
            continue  # partial / holiday sessions
        out.append((d, g))
    daily = pd.DataFrame({"h": [g["high"].max() for _, g in out], "l": [g["low"].min() for _, g in out],
                          "c": [g["close"].iloc[-1] for _, g in out]}, index=[d for d, _ in out])
    tr = np.maximum(daily["h"] - daily["l"], np.maximum((daily["h"] - daily["c"].shift()).abs(),
                                                         (daily["l"] - daily["c"].shift()).abs()))
    atr = tr.rolling(14).mean().shift(1)  # prior days only
    return out, atr


def simulate(days, atr, k_drive, k_stop, tgt, t_exit, control=False):
    rec = {}
    for d, g in days:
        a = atr.get(d)
        if a is None or not np.isfinite(a):
            continue
        fh = g[g["hm"] <= "10:25"]
        o, c = fh["open"].iloc[0], fh["close"].iloc[-1]
        move = c - o
        if abs(move) < k_drive * a:
            rec[d] = 0.0
            continue
        side = 1.0 if move > 0 else -1.0
        r = k_stop * (fh["high"].max() - fh["low"].min())
        if r <= 0:
            rec[d] = 0.0
            continue
        stop, take = c - side * r, c + side * tgt * r
        end = "15:55" if control else t_exit
        rest = g[(g["hm"] > "10:25") & (g["hm"] < end)] if not control else g[g["hm"] > "10:25"]
        px = None
        for _, b in rest.iterrows():
            if (side > 0 and b["low"] <= stop) or (side < 0 and b["high"] >= stop):
                px = stop
                break
            if not control and ((side > 0 and b["high"] >= take) or (side < 0 and b["low"] <= take)):
                px = take
                break
        if px is None:
            if control:
                px = g["close"].iloc[-1]
            else:
                last = g[g["hm"] < end]
                px = last["close"].iloc[-1]
        rec[d] = (side * (px - c), 1)
    return rec


def summarize(rec, years):
    pts = [v[0] for v in rec.values() if isinstance(v, tuple)]
    n = len(pts)
    gross = sum(p for p in pts if p > 0) - sum(-p for p in pts if p < 0)
    daily = pd.Series({d: ((v[0] - COST) * M if isinstance(v, tuple) else 0.0) for d, v in rec.items()}).sort_index()
    net_yr = daily.sum() / years
    r30 = float(roc30(daily.to_numpy()[None, :], years)[0])
    return {"n": n, "per_yr": n / years, "gross_pts": gross, "cost_pts": n * COST,
            "gross_over_cost": gross / (n * COST) if n else float("nan"), "net_yr": net_yr, "roc30": r30,
            "daily": daily}


def main():
    days, atr = days_table()
    d0, d1 = days[0][0], days[-1][0]
    years = (pd.Timestamp(d1) - pd.Timestamp(d0)).days / 365.25
    print("NQ 5m RTH %s .. %s  sessions %d  years %.2f" % (d0, d1, len(days), years))
    k, s, t, x = CENTRAL
    cen = summarize(simulate(days, atr, k, s, t, x), years)
    ctl = summarize(simulate(days, atr, k, s, t, x, control=True), years)
    for name, r in (("MIDDAY central", cen), ("CONTROL hold-to-close", ctl)):
        print("%-22s n %5d (%5.1f/yr)  gross/cost %6.2f  net $/yr %9.0f  ROC@30k %6.2f"
              % (name, r["n"], r["per_yr"], r["gross_over_cost"], r["net_yr"], r["roc30"]))
    # folds = calendar years
    a, b = cen["daily"], ctl["daily"].reindex(cen["daily"].index).fillna(0.0)
    yrs = sorted(set(pd.Timestamp(d).year for d in a.index))
    print("\nYEAR  MIDDAY$   CONTROL$   lead$   ROC30(M)  ROC30(C)")
    wins = pos = 0
    for y in yrs:
        m = [pd.Timestamp(d).year == y for d in a.index]
        am, bm = a[m], b[m]
        yy = max(len(am) / 252.0, 1e-9)
        rm, rc = roc30(am.to_numpy()[None, :], yy)[0], roc30(bm.to_numpy()[None, :], yy)[0]
        wins += am.sum() > bm.sum()
        pos += am.sum() > 0
        print("%d %9.0f %9.0f %8.0f %8.2f %8.2f" % (y, am.sum(), bm.sum(), am.sum() - bm.sum(), rm, rc))
    print("folds: MIDDAY > 0 in %d of %d; beats CONTROL in %d of %d" % (pos, len(yrs), wins, len(yrs)))
    pl = power_line(a.to_numpy(), b.to_numpy(), years)
    print("power line (lead ROC@30k vs control): sd %.2f  5%% line %.2f  80%% line %.2f  observed lead %.2f"
          % (pl["sd"], pl["line_5pct"], pl["line_80pct"], cen["roc30"] - ctl["roc30"]))
    # #314 overlap
    o = pd.read_csv(ORB314, parse_dates=["date"])
    o = o[o["trades"] > 0]
    o314 = pd.Series(o["pnl_usd"].to_numpy(), index=o["date"].dt.date)
    mtd = [d for d, v in cen["daily"].items() if v != 0.0]
    shared = [d for d in mtd if d in o314.index]
    j = pd.concat([cen["daily"], o314], axis=1).fillna(0.0)
    j = j[(j.index >= min(o314.index)) & (j.index <= max(o314.index))]
    print("\n#314 overlap: MIDDAY trade days %d, also #314 trade days %d (%.0f%%); daily P&L corr %.2f"
          % (len(mtd), len(shared), 100.0 * len(shared) / max(len(mtd), 1), j.corr().iloc[0, 1]))
    # grid spread
    print("\nGRID (spread only, no pick): k_drive k_stop tgt t_exit -> n/yr gross/cost net$/yr ROC30")
    rows = []
    for kd, ks, tg, te in itertools.product(*GRID.values()):
        r = summarize(simulate(days, atr, kd, ks, tg, te), years)
        rows.append((kd, ks, tg, te, r["per_yr"], r["gross_over_cost"], r["net_yr"], r["roc30"]))
        print("%.1f %.1f %.0fR %s -> %5.1f %6.2f %9.0f %6.2f" % rows[-1])
    g = np.array([r[5] for r in rows])
    roc = np.array([r[7] for r in rows])
    print("grid: gross/cost median %.2f, %d of %d cells > 1.5; ROC30 median %.2f, %d of %d >= 15"
          % (np.nanmedian(g), (g > 1.5).sum(), len(g), np.nanmedian(roc), (roc >= 15).sum(), len(roc)))


if __name__ == "__main__":
    main()
