r"""TEST 75 PHASE A - exit variants on the two live trades the owner flagged (MANAGER #146, owner 10-31).

IN-SAMPLE / IDEA GENERATION ONLY. Two trades are an anecdote: this table picks WHICH exits go into the Phase B prereg, it
proves nothing. Every parameter below was fixed from a textbook default BEFORE the two trades were simulated, and none
was changed after.

The trades (box backup 2026-10-30_1445, trades.csv + cloud_signal/signals.csv, read-only):
    ORB  #314  2026-10-23 long  10 sh  entry 704.60 09:50  exit 704.58 15:30 (time exit; breakeven armed 10:50)
               R = entry - its own stop 697.81 = 6.79
    NOISE #382 2026-10-30 short 15 sh  entry 692.03 12:15  exit 691.29 15:55 (close > VWAP)
               R = session VWAP at entry - entry = 3.24 (the level its own exit watches)
Bars: C:\EdgeLog\ohlc\QQQ_1m.csv, resampled to the legs' 5-minute bars. Rule for every variant: a level is set on a 5m
bar's CLOSE and acts from the NEXT 5m bar (open through it = fill at the open, else a touch = fill at the level); a
close-based exit fills at that bar's close (the legs decide at the close). The leg's own exit still applies, whichever
comes first. A partial scale-out banks the fraction at the trigger level and holds the rest to the leg's exit.

VARIANTS (parameters fixed before computing):
    V0  HOLD              the leg's own exit (what happened)
    V1  ATR TRAIL         stop = best 5m close since entry -/+ 3 x ATR(14, 5m)
    V2  CHANDELIER        stop = highest high / lowest low since entry -/+ 3 x ATR(22, 5m)
    V3  6-BAR TRAIL       stop = lowest low (long) / highest high (short) of the last 6 closed 5m bars (30 min)
    V4  VWAP CROSS        exit at the first 5m close on the wrong side of session VWAP
    V5  GIVEBACK 50%      once MFE >= 1R: stop = entry + 50% of MFE (gives back half the best open profit)
    V6  SCALE 1/2 @ 1R    bank half at 1R, rest to the leg's exit
    V7  SCALE 1/2 @ 3 pt  bank half at 3.00 QQQ points, rest to the leg's exit
    V8  TIME-DECAY TRAIL  stop = best close -/+ k x ATR(14), k = 3 x (minutes to 16:00 / 390), floor 1
    V9  BE + TRAIL        breakeven once MFE >= 1R, then 2 x ATR(14) from the best close
    python tools/t75_phaseA_exits.py   -> C:\EdgeLog\_anatomy_cache\t75_phaseA\phaseA.csv + phaseA.png
"""
import os

import numpy as np
import pandas as pd

QQQ1M = r"C:\EdgeLog\ohlc\QQQ_1m.csv"
OUT = r"C:\EdgeLog\_anatomy_cache\t75_phaseA"
TRADES = [
    dict(leg="ORB #314", day="2026-10-23", side=1, shares=10, entry=704.60, t_in="09:50", exit=704.58, t_out="15:30", R=6.79),
    dict(leg="NOISE #382", day="2026-10-30", side=-1, shares=15, entry=692.03, t_in="12:15", exit=691.29, t_out="15:55", R=3.24),
]


def bars_5m(day):
    b = pd.read_csv(QQQ1M).dropna(subset=["high", "low"])
    b["ts"] = pd.to_datetime(b.time, unit="s", utc=True).dt.tz_convert("America/New_York").dt.tz_localize(None)
    b = b.set_index("ts").sort_index()
    d0 = pd.Timestamp(day)
    b = b.loc[d0 - pd.Timedelta(days=6): d0 + pd.Timedelta(hours=16)]
    b = b.between_time("09:30", "15:59")
    f = b.resample("5min", label="left", closed="left").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}).dropna()
    tr = pd.concat([f.high - f.low, (f.high - f.close.shift()).abs(), (f.low - f.close.shift()).abs()], axis=1).max(axis=1)
    f["atr14"], f["atr22"] = tr.rolling(14).mean(), tr.rolling(22).mean()
    day_b = f[f.index.normalize() == d0].copy()
    tp = (day_b.high + day_b.low + day_b.close) / 3
    day_b["vwap"] = (tp * day_b.volume).cumsum() / day_b.volume.cumsum()
    return day_b


def run(t, variant, B):
    """pts banked per share (side-adjusted)."""
    sd, ep, R = t["side"], t["entry"], t["R"]
    t_in = pd.Timestamp(t["day"] + " " + t["t_in"]).floor("5min")
    t_out = pd.Timestamp(t["day"] + " " + t["t_out"]).floor("5min")
    leg = sd * (t["exit"] - ep)
    seg = B.loc[t_in: t_out - pd.Timedelta(minutes=5)]          # bars the trade lives through before the leg's exit bar
    stop, best_c, mfe, be_on, half = None, ep, 0.0, False, None
    for i, (ts, r) in enumerate(seg.iterrows()):
        if i > 0 and stop is not None:                          # a level acts from the bar after it was set
            if sd * (r.open - stop) <= 0:
                return _fin(half, sd * (r.open - ep), leg)
            if sd * ((r.low if sd > 0 else r.high) - stop) <= 0:
                return _fin(half, sd * (stop - ep), leg)
        if i > 0 and variant in ("V6", "V7") and half is None:
            trig = R if variant == "V6" else 3.0
            if sd * ((r.high if sd > 0 else r.low) - ep) >= trig:
                half = trig
        fav = sd * ((r.high if sd > 0 else r.low) - ep)
        mfe = max(mfe, fav)
        best_c = max(best_c, r.close) if sd > 0 else min(best_c, r.close)
        ext = seg.loc[:ts]
        if variant == "V1":
            stop = best_c - sd * 3 * r.atr14
        elif variant == "V2":
            stop = (ext.high.max() - 3 * r.atr22) if sd > 0 else (ext.low.min() + 3 * r.atr22)
        elif variant == "V3":
            w = B.loc[:ts].tail(6)
            stop = w.low.min() if sd > 0 else w.high.max()
        elif variant == "V4":
            if sd * (r.close - r.vwap) < 0:
                return _fin(None, sd * (r.close - ep), leg)
        elif variant == "V5":
            if mfe >= R:
                stop = ep + sd * 0.5 * mfe
        elif variant == "V8":
            left = (pd.Timestamp(t["day"] + " 16:00") - (ts + pd.Timedelta(minutes=5))).total_seconds() / 60
            k = max(1.0, 3.0 * left / 390.0)
            stop = best_c - sd * k * r.atr14
        elif variant == "V9":
            if mfe >= R:
                be_on = True
            if be_on:
                tr = best_c - sd * 2 * r.atr14
                stop = max(ep, tr) if sd > 0 else min(ep, tr)
    return _fin(half, leg, leg)


def _fin(half, rest, leg):
    return rest if half is None else 0.5 * half + 0.5 * leg


def main():
    os.makedirs(OUT, exist_ok=True)
    names = {"V0": "HOLD (leg's own exit)", "V1": "ATR trail 3x14", "V2": "Chandelier 3x22", "V3": "6-bar low/high trail",
             "V4": "VWAP cross exit", "V5": "Giveback 50% after 1R", "V6": "Scale 1/2 at 1R", "V7": "Scale 1/2 at 3 pts",
             "V8": "Time-decay ATR trail", "V9": "Breakeven 1R + 2 ATR trail"}
    rows = []
    for t in TRADES:
        B = bars_5m(t["day"])
        t_in = pd.Timestamp(t["day"] + " " + t["t_in"]).floor("5min")
        t_out = pd.Timestamp(t["day"] + " " + t["t_out"]).floor("5min")
        seg = B.loc[t_in: t_out - pd.Timedelta(minutes=5)]
        mfe = t["side"] * ((seg.high.max() if t["side"] > 0 else seg.low.min()) - t["entry"])
        for v in names:
            p = t["side"] * (t["exit"] - t["entry"]) if v == "V0" else run(t, v, B)
            rows.append(dict(leg=t["leg"], day=t["day"], variant=v, name=names[v], pts=round(p, 2),
                             usd=round(p * t["shares"], 2), pct_mfe=round(100 * p / mfe, 0), mfe=round(mfe, 2)))
    df = pd.DataFrame(rows)
    df.to_csv(os.path.join(OUT, "phaseA.csv"), index=False)
    wide = df.pivot_table(index=["variant", "name"], columns="leg", values=["pts", "usd", "pct_mfe"], aggfunc="first")
    pd.set_option("display.width", 200)
    print(wide.to_string())
    print("MFE:", df.groupby("leg").mfe.first().to_dict())
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(10, 4.5))
    piv = df.pivot(index="name", columns="leg", values="pct_mfe").reindex(list(names.values()))
    piv.plot.barh(ax=ax, color=["#333", "#999"])
    ax.axvline(0, color="k", lw=0.8)
    ax.set_xlabel("% of the trade's best open profit banked (in-sample, 2 trades - idea generation only)")
    ax.invert_yaxis()
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, "phaseA.png"), dpi=110)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
