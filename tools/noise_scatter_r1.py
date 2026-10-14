# -*- coding: utf-8 -*-
"""NOISE PnL SCATTER r1 (owner order 10-12 via MANAGER #86) - a REPORT on #382 / #422's own walk-forward trades.

No exit, target or filter is applied or simulated here: this reads the trades as they happened (the #304 core entries
and exits, which #382 and #422 share; they differ only in size). Seen data: the 10-05 anatomy (ledger 2.82) already
read these trades' exits, MFE and MAE.

  core     NOISE_1_0 with CT304H's _FROZEN params (#304) on the NQ 5m RTH no-adjust master, unit = 1 NQ
  #382     NOISE_1_8_CT304 (30-minute gate 16 / 1.15, 2.0x)     #422  NOISE_1_8_CT304H (60-minute gate 20 / 1.15, 1.75x)
  stretch  WF, signal dates 2016-07-01 .. 2025-06-29 (lockbox not read)
  costs    0.533 pt (house) and 0.783 pt (commission + one tick of slippage each side = the house stressed cost)
  R        entry to the trade's own initial stop (bandwidth stop 1.75 x the band excursion at the fill bar)

Per leg and cost: the FOUR numbers (ROC@$30k, DD5, DD% from the peak on $100k, daily Sortino) + win rate, avg win /
avg loss, PF. Then, on the core at 0.783: PnL against MFE (in R), MAE (in R), hold time and entry time; and the
MFE tail - how much of the net sits in trades that ran far.
    python noise_scatter_r1.py
"""
import os
import sys

import numpy as np
import pandas as pd

REPO = r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"
sys.path.insert(0, os.path.join(REPO, "tools"))
sys.path.insert(0, REPO)
os.environ.pop("AUGUR_TRIAL_CACHE", None)
import r68_noise_breakeven_triage as R                                # noqa: E402
from augur_engine.engine import run_backtest                          # noqa: E402
from augur_engine.drawdowns import dd5, dd_pct_peak                    # noqa: E402

OUT = os.path.dirname(os.path.abspath(__file__))
W0, W1 = pd.Timestamp("2016-07-01").date(), pd.Timestamp("2025-06-29").date()
YRS = 8.994
COSTS = (0.533, 0.783)
CORE = dict(lookback=40, band_mult_long=0.75, band_mult_short=1.5, exit_mode="vwap", side="Both", window="all_day",
            flat_eod=True, skip_holidays=False, stop_mode="bandwidth", stop_k=1.75, confirm_bars=1,
            daytype_mode="skip_bot_short", daytype_lo=0.2, daytype_hi=0.8, vol_skip_pct=95.0)
LEGS = (("#382", "NOISE_1_8_CT304.py", dict(gate_tf_min=30, gate_len=16, gate_ratio=1.15, tilt_mult=2.0)),
        ("#422", "NOISE_1_8_CT304H.py", dict(gate_len=20, gate_ratio=1.15, tilt_mult=1.75)))


def srt(x):
    t = sorted(x, key=lambda t: int(t[0]))
    return t


def core_trades():
    """The #304 core at zero cost (gross points), with exit kind, MFE / MAE, R, hold and entry time per trade."""
    A = R.A
    O, Hh, Lw, C = (np.asarray(A[k], float) for k in ("open", "high", "low", "close"))
    idx, day = R.IDX, np.asarray(A["day_id"])
    tr = srt(run_backtest(R.load("NOISE_1_0.py"), arrays=A, params=CORE, cost_pts=0.0, return_trades=True)["trades"])
    # the band at the fill bar, for R: re-derive from NOISE_1_0's own sigma (same lookback, same anchors)
    import importlib.util as ilu
    s = ilu.spec_from_file_location("_n10s", os.path.join(REPO, "augur_strategies", "NOISE_1_0.py"))
    N = ilu.module_from_spec(s)
    s.loader.exec_module(N)
    starts = np.r_[0, np.flatnonzero(np.diff(day)) + 1]
    ends = np.r_[starts[1:], len(day)]
    s_of = np.repeat(np.arange(len(starts)), ends - starts)
    sig = N._sigma_matrix(O, C, list(zip(starts, ends)), CORE["lookback"])
    prevC = np.r_[np.nan, C[ends[:-1] - 1]]
    rows = []
    for t in tr:
        k0, k1, gross, side, epx = int(t[0]), int(t[1]), float(t[2]), float(np.sign(t[3])), float(t[4])
        d = idx[k0 - 1].date()
        if not (W0 <= d <= W1):
            continue
        si = s_of[k0]
        a = starts[si]
        ref_hi, ref_lo = max(O[a], prevC[si]), min(O[a], prevC[si])
        j = k0 - a
        band = (ref_hi * (1 + CORE["band_mult_long"] * sig[si, j]) - ref_hi) if side > 0 else \
               (ref_lo - ref_lo * (1 - CORE["band_mult_short"] * sig[si, j]))
        r_pts = CORE["stop_k"] * band
        xpx = epx + side * gross
        last = k1 == ends[si] - 1
        kind = ("held to close" if last and abs(xpx - C[k1]) < 1e-6 else
                "VWAP exit" if abs(xpx - O[k1]) < 1e-6 else "stop")
        seg = slice(k0, k1 + 1)
        mfe = float(np.max((Hh[seg] - epx) if side > 0 else (epx - Lw[seg])))
        mae = float(np.max((epx - Lw[seg]) if side > 0 else (Hh[seg] - epx)))
        et = idx[k0]
        rows.append(dict(date=d, k0=k0, k1=k1, side=side, gross=gross, kind=kind, mfe=mfe, mae=mae, r_pts=r_pts,
                         hold_min=5 * (k1 - k0), entry_hm=et.hour * 100 + et.minute))
    return pd.DataFrame(rows)


def leg_sizes(fn, params, T):
    tr = srt(run_backtest(R.load(fn), arrays=R.A, params=params, cost_pts=0.0, return_trades=True)["trades"])
    g = {(int(t[0]), int(t[1])): float(t[2]) for t in tr}
    # size = sized gross / core gross where the core moved; the wrapper sizes are 1.0 or tilt_mult
    tm = params["tilt_mult"]
    out = []
    for k0, k1, gr in zip(T.k0, T.k1, T.gross):
        v = g[(k0, k1)]
        out.append(1.0 if abs(gr) < 1e-9 and abs(v) < 1e-9 else (tm if abs(v - tm * gr) < abs(v - gr) else 1.0))
    return np.array(out)


def four(pnl_usd, dates, sess):
    daily = pd.Series(pnl_usd, index=dates).groupby(level=0).sum().reindex(sess, fill_value=0.0)
    x = daily.to_numpy()
    cum = np.cumsum(x)
    mdd = float(np.max(np.maximum.accumulate(np.r_[0.0, cum])[1:] - cum))
    roc = 30.0 * (cum[-1] / YRS) / mdd
    d5 = dd5(daily)
    ddp = dd_pct_peak(daily)
    dn = np.sqrt(np.mean(np.minimum(x, 0.0) ** 2))
    so = x.mean() / dn * np.sqrt(len(x) / YRS)
    return roc, d5, ddp, so, mdd


def wl(p):
    w, l = p[p > 0], p[p < 0]
    return 100 * len(w) / len(p), w.mean(), -l.mean(), w.sum() / -l.sum()


def main():
    T = core_trades()
    sess = pd.Index(sorted({R.IDX[i].date() for i in range(len(R.IDX)) if W0 <= R.IDX[i].date() <= W1}))
    print("NOISE PnL SCATTER r1 - #304 core trades, WF signal dates %s .. %s: %d trades (%.0f a year), %d sessions" % (
        W0, W1, len(T), len(T) / YRS, len(sess)))
    print("exit kinds:", T.kind.value_counts().to_dict())
    print("\nA. THE LEGS, WF (four numbers + win rate; DD%% on $100k at the traded size; Sortino daily)")
    for name, fn, params in (("core 1x", None, None),) + LEGS:
        s = np.ones(len(T)) if fn is None else leg_sizes(fn, params, T)
        for c in COSTS:
            p = s * (T.gross.to_numpy() - c) * R.M
            roc, d5, ddp, so, mdd = four(p, T.date.to_numpy(), sess)
            wr, aw, al, pf = wl(p)
            print("  %-8s cost %.3f  ROC@30k %6.2f  DD5 $%6.0f%s  DD%% %5.2f  Sortino %4.2f | win %4.1f%%  avg win $%4.0f"
                  "  avg loss $%4.0f  (%.2fx)  PF %.3f  net $%.0f/yr" % (
                      name, c, roc, d5["dd5_usd"], " (1 EPISODE)" if d5["one_episode"] else "", ddp, so, wr, aw, al,
                      aw / al, pf, p.sum() / YRS))
    c = COSTS[1]
    T["pnl"] = (T.gross - c) * R.M
    T["mfe_r"] = T.mfe / T.r_pts
    T["mae_r"] = T.mae / T.r_pts
    net = T.pnl.sum()
    print("\n  R (entry to initial stop): median %.1f pt, p10 %.1f, p90 %.1f" % (
        T.r_pts.median(), T.r_pts.quantile(.1), T.r_pts.quantile(.9)))

    def tab(col, bins, labels, title):
        print("\n%s (core 1x, cost %.3f)" % (title, c))
        g = pd.cut(T[col], bins, labels=labels, right=False)
        for lab in labels:
            sub = T[g == lab]
            if not len(sub):
                continue
            wr = 100 * (sub.pnl > 0).mean()
            mix = sub.kind.value_counts(normalize=True)
            print("  %-14s n %5d (%4.1f%%)  win %5.1f%%  $/trade %+6.0f  share of net %+6.1f%%  | close %3.0f%% VWAP %3.0f%%"
                  " stop %3.0f%%" % (lab, len(sub), 100 * len(sub) / len(T), wr, sub.pnl.mean(), 100 * sub.pnl.sum() / net,
                                    100 * mix.get("held to close", 0), 100 * mix.get("VWAP exit", 0),
                                    100 * mix.get("stop", 0)))

    tab("mfe_r", [0, .25, .5, 1, 2, 3, 99], ["MFE <0.25R", "0.25-0.5R", "0.5-1R", "1-2R", "2-3R", ">=3R"],
        "B. PnL against MFE (best open profit, in R)")
    tab("mae_r", [0, .25, .5, .75, 1.0001, 99], ["MAE <0.25R", "0.25-0.5R", "0.5-0.75R", "0.75-1R", "past 1R (gap)"],
        "C. PnL against MAE (worst open loss, in R)")
    tab("hold_min", [0, 10, 30, 60, 120, 240, 999], ["<10 min", "10-30", "30-60", "60-120", "120-240", ">=240"],
        "D. PnL against hold time")
    tab("entry_hm", [930, 1000, 1100, 1200, 1300, 1400, 1500, 1600],
        ["09:30-10:00", "10-11", "11-12", "12-13", "13-14", "14-15", "15-16"], "E. PnL against entry time")
    print("\nF. By exit kind (core 1x, cost %.3f): MFE in R, median / p75 / p90" % c)
    for k, sub in T.groupby("kind"):
        wr, aw, al, _ = wl(sub.pnl.to_numpy())
        print("  %-14s n %5d  win %5.1f%%  avg win $%5.0f  avg loss $%5.0f  net $%+9.0f  MFE %.2f / %.2f / %.2f R  "
              "hold median %d min" % (k, len(sub), wr, aw if wr > 0 else 0, al if wr < 100 else 0, sub.pnl.sum(),
                                      sub.mfe_r.median(), sub.mfe_r.quantile(.75), sub.mfe_r.quantile(.9),
                                      sub.hold_min.median()))
    v = T[T.kind == "VWAP exit"]
    for lv in (0.5, 1.0, 2.0):
        g = v[(v.mfe_r >= lv) & (v.pnl <= 0)]
        print("  giveback: VWAP exits that ran >= %.1fR and closed at a loss: %d (%.1f%% of trades), $%.0f" % (
            lv, len(g), 100 * len(g) / len(T), g.pnl.sum()))
    top = T.sort_values("pnl", ascending=False)
    for k in (10, 50, 100, 250):
        print("  top %3d trades = %5.1f%% of net (%.1f%% of trades)" % (k, 100 * top.pnl.iloc[:k].sum() / net,
                                                                    100 * k / len(T)))
    T.to_csv(os.path.join(OUT, "noise_scatter_r1_trades.csv"), index=False)
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        plt.rcParams.update({"font.size": 8, "axes.edgecolor": "#888", "axes.labelcolor": "#ddd", "xtick.color": "#bbb",
                             "ytick.color": "#bbb", "text.color": "#eee"})
        fig, ax = plt.subplots(1, 4, figsize=(15, 3.8), facecolor="#111")
        y = T.pnl.to_numpy()
        col = np.where(y > 0, "#f2f2f2", "#777777")
        for a_, (xc, lab, logx) in zip(ax, (("mfe_r", "MFE (R)", False), ("mae_r", "MAE (R)", False),
                                            ("hold_min", "hold (min)", True), ("entry_hm", "entry time (hhmm)", False))):
            a_.set_facecolor("#111")
            xv = T[xc].to_numpy(float)
            a_.scatter(np.maximum(xv, 1) if logx else xv, y, s=3, c=col, alpha=.5, lw=0)
            if logx:
                a_.set_xscale("log")
            a_.axhline(0, color="#555", lw=.6)
            a_.set_xlabel(lab)
            a_.set_yscale("symlog", linthresh=200)
        ax[0].set_ylabel("PnL $ a trade (1 NQ, cost 0.783)")
        fig.suptitle("NOISE #304 core (= #382 / #422 entries and exits), WF 2016-07..2025-06, %d trades - white wins, "
                     "grey losses" % len(T), color="#eee")
        fig.tight_layout()
        fig.savefig(os.path.join(OUT, "noise_scatter_r1.png"), dpi=130, facecolor="#111")
        print("\nchart: noise_scatter_r1.png")
    except Exception as e:                                           # the chart is optional
        print("chart skipped:", e)


if __name__ == "__main__":
    main()
