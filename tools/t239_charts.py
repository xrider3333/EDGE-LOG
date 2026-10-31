r"""TEST 239 CHARTS (was test 75; MANAGER #149, owner 10-31: "show me the chart of how it would have looked").

Pictures only - no new verdict; the Phase B result (docs/RESULTS_noise_t75b_exits_2026-10-31.md) stands.
    phaseB_1030_trade.png   the 10-30 NOISE #382 short on QQQ 1m bars, each exit's stop line and exit point marked
    phaseB_oos_curves.png   OOS 2022-01 .. 2025-07-15 cumulative $ for hold vs the 5 Phase B trails (lockbox never loaded)
    phaseB_mfe_scatter.png  per-trade MFE vs banked (pts), hold vs BE 1R + 2 ATR trail, diagonal = kept everything
Exit rules are the Phase A / Phase B ones unchanged (tools/t75_phaseA_exits.py, tools/noise_t75b_exits.py): a level is
set on a 5m close and acts from the next 5m bar.

    python tools/t239_charts.py   -> C:\EdgeLog\_anatomy_cache\t75_phaseB\*.png
"""
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import t75_phaseA_exits as pa  # noqa: E402
import noise_t75b_exits as pb  # noqa: E402
import noise_t74_giveback as t74  # noqa: E402

OUT = r"C:\EdgeLog\_anatomy_cache\t75_phaseB"
OOS0 = pd.Timestamp("2022-01-01")
TRAILS = {"V1": ("E1", "ATR trail 3x14", "#4c9be8"), "V2": ("E2", "Chandelier 3x22", "#a07be0"),
          "V3": ("E3", "6-bar trail", "#9a9a9a"), "V8": ("E4", "Time-decay ATR trail", "#e8a33c"),
          "V9": ("E5", "BE 1R + 2 ATR trail", "#3cc48a")}
HOLD_C = "#e0505a"
plt.rcParams.update({"figure.facecolor": "white", "axes.facecolor": "white", "font.size": 10})


def trace(t, variant, B):
    """(exit ts, pts banked, stop series) for one trade - the Phase A run() with its stop line kept."""
    sd, ep, R = t["side"], t["entry"], t["R"]
    t_in = pd.Timestamp(t["day"] + " " + t["t_in"]).floor("5min")
    t_out = pd.Timestamp(t["day"] + " " + t["t_out"]).floor("5min")
    seg = B.loc[t_in: t_out - pd.Timedelta(minutes=5)]
    stop, best_c, mfe, be_on, line = None, ep, 0.0, False, {}
    for i, (ts, r) in enumerate(seg.iterrows()):
        if i > 0 and stop is not None:
            line[ts] = stop
            if sd * (r.open - stop) <= 0:
                return ts, sd * (r.open - ep), pd.Series(line)
            if sd * ((r.low if sd > 0 else r.high) - stop) <= 0:
                return ts + pd.Timedelta(minutes=4), sd * (stop - ep), pd.Series(line)
        mfe = max(mfe, sd * ((r.high if sd > 0 else r.low) - ep))
        best_c = max(best_c, r.close) if sd > 0 else min(best_c, r.close)
        ext = seg.loc[:ts]
        if variant == "V1":
            stop = best_c - sd * 3 * r.atr14
        elif variant == "V2":
            stop = (ext.high.max() - 3 * r.atr22) if sd > 0 else (ext.low.min() + 3 * r.atr22)
        elif variant == "V3":
            w = B.loc[:ts].tail(6)
            stop = w.low.min() if sd > 0 else w.high.max()
        elif variant == "V8":
            left = (pd.Timestamp(t["day"] + " 16:00") - (ts + pd.Timedelta(minutes=5))).total_seconds() / 60
            stop = best_c - sd * max(1.0, 3.0 * left / 390.0) * r.atr14
        elif variant == "V9":
            if mfe >= R:
                be_on = True
            if be_on:
                tr = best_c - sd * 2 * r.atr14
                stop = max(ep, tr) if sd > 0 else min(ep, tr)
    return pd.Timestamp(t["day"] + " " + t["t_out"]), sd * (t["exit"] - ep), pd.Series(line)


def chart_trade():
    t = next(x for x in pa.TRADES if x["leg"].startswith("NOISE"))
    B = pa.bars_5m(t["day"])
    m = pd.read_csv(pa.QQQ1M).dropna(subset=["high", "low"])
    m["ts"] = pd.to_datetime(m.time, unit="s", utc=True).dt.tz_convert("America/New_York").dt.tz_localize(None)
    m = m.set_index("ts").sort_index().loc[t["day"] + " 11:30": t["day"] + " 16:00"]
    fig, ax = plt.subplots(figsize=(13, 6.5))
    ax.plot(m.index, m.close, color="#333333", lw=0.9, label="QQQ 1m close")
    ax.fill_between(m.index, m.low, m.high, color="#bbbbbb", alpha=0.35, lw=0)
    t_in = pd.Timestamp(t["day"] + " " + t["t_in"])
    seg = m.loc[t_in: t["day"] + " " + t["t_out"]]
    mfe_ts = seg.low.idxmin()
    ax.scatter([t_in], [t["entry"]], marker="v", s=140, color="black", zorder=5, label="Short entry %.2f" % t["entry"])
    ax.scatter([mfe_ts], [seg.low.min()], marker="*", s=220, color="#e8a33c", edgecolor="black", zorder=5,
               label="Best point (MFE) %.2f = +%.2f" % (seg.low.min(), t["entry"] - seg.low.min()))
    hx = pd.Timestamp(t["day"] + " " + t["t_out"])
    ax.scatter([hx], [t["exit"]], marker="X", s=150, color=HOLD_C, zorder=6,
               label="HOLD exit %.2f: +%.2f pts" % (t["exit"], t["entry"] - t["exit"]))
    for v, (_, name, col) in TRAILS.items():
        xts, pts, line = trace(t, v, B)
        main = v in ("V8", "V9")
        a = 1.0 if main else 0.35
        if len(line):
            ax.step(line.index, line.values, where="post", color=col, lw=2.0 if main else 1.0, alpha=a,
                    ls="-" if main else "--")
        ax.scatter([xts], [t["entry"] - pts], marker="X", s=150 if main else 70, color=col, alpha=a, zorder=6,
                   label="%s exit: %+.2f pts" % (name, pts))
    ax.axhline(t["entry"], color="black", lw=0.6, ls=":")
    ax.set_title("NOISE #382 short, 2026-10-30 - where each exit would have closed (stop lines drawn; 5m-close rule)")
    ax.set_ylabel("QQQ price")
    ax.legend(loc="upper left", fontsize=8.5, framealpha=0.92)
    ax.grid(alpha=0.25)
    fig.autofmt_xdate()
    fig.tight_layout()
    p = os.path.join(OUT, "phaseB_1030_trade.png")
    fig.savefig(p, dpi=130)
    plt.close(fig)
    return p


def charts_oos():
    tr, A, idx, meta = pb.full_trades()                       # lockbox never loaded (asserted inside)
    s = np.asarray([x[6] for x in tr])
    dates = pd.DatetimeIndex([idx[x[2] - 1].normalize() for x in tr])
    m = dates >= OOS0
    raw0 = np.asarray([x[5] for x in tr])
    usd = lambda r: s * (np.asarray(r) - meta["cost"]) * meta["mult"]  # noqa: E731
    fig, ax = plt.subplots(figsize=(13, 6.5))
    curves = {"HOLD (leg as is)": (raw0, HOLD_C, 2.6)}
    sims = {}
    for v, (e, name, col) in TRAILS.items():
        sims[e] = pb.simulate(tr, A, idx, e)
        curves[name] = (sims[e], col, 1.6)
    for name, (r, col, lw) in curves.items():
        c = pd.Series(usd(r)[m], index=dates[m]).groupby(level=0).sum().cumsum()
        ax.plot(c.index, c.values, color=col, lw=lw, label="%s  $%s" % (name, format(int(round(c.iloc[-1])), ",")))
    ax.set_title("NOISE #382 out-of-sample 2022-01 .. 2025-07-15: cumulative $ - hold vs the 5 trails (lockbox not loaded)")
    ax.set_ylabel("cumulative net $ (fees in)")
    ax.legend(loc="upper left", fontsize=9)
    ax.grid(alpha=0.25)
    fig.tight_layout()
    p1 = os.path.join(OUT, "phaseB_oos_curves.png")
    fig.savefig(p1, dpi=130)
    plt.close(fig)

    mfe = t74.paths(tr, A).mfe.to_numpy()[m]
    fig, axs = plt.subplots(1, 2, figsize=(13, 6.2), sharex=True, sharey=True)
    for ax, (name, r, col) in zip(axs, [("HOLD (leg as is)", raw0, HOLD_C), ("BE 1R + 2 ATR trail", sims["E5"], "#3cc48a")]):
        b = np.asarray(r)[m]
        ax.scatter(mfe, b, s=9, alpha=0.45, color=col)
        lim = [min(0, b.min()), max(mfe.max(), b.max())]
        ax.plot(lim, lim, color="black", lw=0.8, ls="--", label="kept everything (banked = MFE)")
        ax.axhline(0, color="#888888", lw=0.6)
        pos = mfe > 0
        ax.set_title("%s: kept %.1f%% of MFE, median giveback %.2f pts" % (name, 100 * b[pos].sum() / mfe[pos].sum(),
                                                                            float(np.median(mfe - b))))
        ax.set_xlabel("MFE - best open profit (NQ pts)")
        ax.grid(alpha=0.25)
        ax.legend(loc="upper left", fontsize=8.5)
    axs[0].set_ylabel("banked at exit (NQ pts, before cost)")
    fig.suptitle("NOISE #382 OOS 2022-01 .. 2025-07-15, %d trades: each dot = one trade (distance below the line = giveback)"
                 % int(m.sum()))
    fig.tight_layout()
    p2 = os.path.join(OUT, "phaseB_mfe_scatter.png")
    fig.savefig(p2, dpi=130)
    plt.close(fig)
    return p1, p2


def main():
    os.makedirs(OUT, exist_ok=True)
    for p in (chart_trade(),) + charts_oos():
        print(p)
    return 0


if __name__ == "__main__":
    sys.exit(main())
