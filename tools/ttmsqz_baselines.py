"""
TTM SQUEEZE BASELINES — John Carter's TTM Squeeze (augur_strategies/TTMSQZ_1_0.py) read
across timeframes and both index contracts, owner ask 2026-08-22.

Window PINNED to 2010-06-07 .. 2026-06-30 on every row (the 15m masters end 2026-06-30,
and the NQ 1m master has a hole 2026-07-17..08-05), lockbox = last 12 months
(2025-07-01 .. 2026-06-30), IS = everything before it. 30m and 60m bars are built from
the 5m master (session-anchored at 09:30 ET) because no master exists at those sizes.

Costs: NQ 0.533 pts/RT x $20 ; ES 0.363 pts/RT x $50 (house numbers).

Usage:  python tools/ttmsqz_baselines.py [quick]     quick = skip 1m/2m
Output: tools/data/ttmsqz_baselines.csv + a printed table.
"""
import os, sys, time, importlib.util
import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UP = os.path.join(ROOT, "augur_uploads")
if not os.path.exists(os.path.join(UP, "NOADJ_NQ_5m_RTH.csv")):
    UP = r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG\augur_uploads"

DATE_FROM, LB_FROM, DATE_TO = "2010-06-07", "2025-07-01", "2026-06-30"
COST = {"NQ": 0.533, "ES": 0.363}
MULT = {"NQ": 20.0, "ES": 50.0}

sp = importlib.util.spec_from_file_location("ttm", os.path.join(ROOT, "augur_strategies", "TTMSQZ_1_0.py"))
ttm = importlib.util.module_from_spec(sp); sp.loader.exec_module(ttm)

CONFIGS = [
    ("published (fade 1, stop 2 ATR)", {}),
    ("zero-cross exit", dict(exit_mode="zero")),
    ("flip exit (opposite fire)", dict(exit_mode="flip")),
    ("fade 2 bars", dict(fade_bars=2)),
    ("min 6-bar squeeze", dict(min_sq_bars=6)),
    ("tight squeeze kc 2.0", dict(kc_mult=2.0)),
    ("wide stop 3 ATR", dict(stop_atr=3.0)),
    ("long only", dict(direction="long")),
    ("short only", dict(direction="short")),
]


def load(inst, tf):
    src_tf = tf if tf in ("1m", "2m", "5m", "15m") else "5m"
    df = pd.read_csv(os.path.join(UP, f"NOADJ_{inst}_{src_tf}_RTH.csv"))
    dt = pd.to_datetime(df["time"], unit="s", utc=True).dt.tz_convert("US/Eastern")
    df = df.assign(_dt=dt).sort_values("time").reset_index(drop=True)
    df = df[(df["_dt"].dt.date >= pd.Timestamp(DATE_FROM).date()) & (df["_dt"].dt.date <= pd.Timestamp(DATE_TO).date())]
    if tf in ("30m", "60m"):
        m = int(tf[:-1])
        mins = df["_dt"].dt.hour * 60 + df["_dt"].dt.minute - 570       # minutes since 09:30
        key = df["_dt"].dt.date.astype(str) + "_" + (mins // m).astype(str).str.zfill(3)
        g = df.groupby(key, sort=True)
        df = pd.DataFrame({"open": g["open"].first(), "high": g["high"].max(), "low": g["low"].min(),
                           "close": g["close"].last(), "volume": g["volume"].sum(), "_dt": g["_dt"].first()}).reset_index(drop=True)
    df["day_id"] = pd.factorize(df["_dt"].dt.date)[0]
    return df


def stats(trades, idx, mult, cost):
    """trades = (entry_bar, exit_bar, pnl_pts, side, ep, xp). Returns full/IS/LB dollar stats."""
    if not trades:
        return None
    t = pd.DataFrame(trades, columns=["eb", "xb", "pnl", "side", "ep", "xp"])
    t["usd"] = (t["pnl"] - cost) * mult
    t["date"] = pd.DatetimeIndex(idx)[t["xb"].values].date
    t["year"] = pd.DatetimeIndex(idx)[t["xb"].values].year

    def block(x):
        if len(x) == 0:
            return dict(net=0.0, pf=0.0, dd=0.0, n=0, wr=0.0)
        u = x["usd"].values
        cum = np.cumsum(u); dd = float((cum - np.maximum.accumulate(cum)).min())
        gw = u[u > 0].sum(); gl = -u[u < 0].sum()
        return dict(net=float(u.sum()), pf=float(gw / gl) if gl > 0 else 99.0, dd=-dd, n=int(len(u)),
                    wr=float(100 * (u > 0).mean()))
    lb = t[t["date"] >= pd.Timestamp(LB_FROM).date()]
    is_ = t[t["date"] < pd.Timestamp(LB_FROM).date()]
    yr = t.groupby("year")["usd"].sum()
    full = block(t); full.update(yplus=int((yr > 0).sum()), yminus=int((yr <= 0).sum()))
    return dict(full=full, IS=block(is_), LB=block(lb))


def main():
    quick = "quick" in sys.argv
    grid = [("NQ", "1m"), ("NQ", "2m"), ("NQ", "5m"), ("NQ", "15m"), ("NQ", "30m"), ("NQ", "60m"),
            ("ES", "5m"), ("ES", "15m"), ("ES", "30m"), ("ES", "60m")]
    if quick:
        grid = [g for g in grid if g[1] not in ("1m", "2m")]
    rows = []
    for inst, tf in grid:
        t0 = time.time(); df = load(inst, tf)
        print(f"\n== {inst} {tf}  bars={len(df):,}  sessions={df['day_id'].max()+1:,}  ({time.time()-t0:.0f}s load)", flush=True)
        print("%-34s %6s %5s %6s %11s %9s %6s | %11s %6s | %11s %6s %5s" % (
            "config", "trades", "WR%", "PF", "net $", "maxDD $", "MAR", "IS $", "IS PF", "LB $", "LB PF", "yrs+"))
        for label, kw in CONFIGS:
            r = ttm.run_backtest(df["open"].values, df["high"].values, df["low"].values, df["close"].values,
                                 day_id=df["day_id"].values, index=df["_dt"], return_trades=True, **kw)
            s = stats(r["trades"] if r else [], df["_dt"], MULT[inst], COST[inst])
            if s is None:
                print("%-34s  NO TRADES" % label); continue
            f = s["full"]; mar = f["net"] / f["dd"] if f["dd"] > 0 else 0.0
            print("%-34s %6d %5.1f %6.2f %11s %9s %6.2f | %11s %6.2f | %11s %6.2f %2d/%-2d" % (
                label, f["n"], f["wr"], min(f["pf"], 99), f"{f['net']:,.0f}", f"{f['dd']:,.0f}", mar,
                f"{s['IS']['net']:,.0f}", min(s["IS"]["pf"], 99), f"{s['LB']['net']:,.0f}", min(s["LB"]["pf"], 99),
                f["yplus"], f["yminus"]), flush=True)
            rows.append(dict(instrument=inst, timeframe=tf, config=label, params=str(kw), trades=f["n"], wr=round(f["wr"], 1),
                             pf=round(f["pf"], 3), net=round(f["net"]), dd=round(f["dd"]), mar=round(mar, 2),
                             is_net=round(s["IS"]["net"]), is_pf=round(s["IS"]["pf"], 3), is_trades=s["IS"]["n"],
                             lb_net=round(s["LB"]["net"]), lb_pf=round(s["LB"]["pf"], 3), lb_trades=s["LB"]["n"],
                             yplus=f["yplus"], yminus=f["yminus"]))
    out = os.path.join(ROOT, "tools", "data", "ttmsqz_baselines.csv")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    pd.DataFrame(rows).to_csv(out, index=False)
    print("\nwrote", out)


if __name__ == "__main__":
    main()
