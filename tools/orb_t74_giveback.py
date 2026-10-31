r"""TEST 74, ORB HALF - ORB #314 MFE GIVEBACK STUDY (owner GO 10-31, MANAGER #144 / ORB #125). Prereg: docs/PREREG_orb_t74_giveback_2026-10-31.md
(addendum to docs/PREREG_noise_t74_giveback_2026-10-31.md). The rule, simulate() and the four numbers are NOISE's tool's, unchanged;
only the leg (ORB #314, one contract) and the Webull leg filter differ.

Trigger: the 10-23 Webull ORB long saw +4.76 pts MFE, breakeven armed at 10:50, time exit 15:30 at +0.19. The question is the
GIVEBACK (MFE - final), not a target (#490, shelf 39/41 and the 10-18 re-reads closed targets).

  python tools/orb_t74_giveback.py describe       per-trade MFE / MAE / giveback: Webull ORB (box trades.csv + QQQ 1m) and
                                                  the #314 WF chain (NQ 5m, parity-checked against the stored folds)
  python tools/noise_t74_giveback.py grid         the preregistered giveback-stop grid on the WF chain only, four numbers
                                                  per cell against hold-to-exit; the lockbox is never loaded

Stop rule (prereg): once the trade's running MFE >= Y x R (R = the entry's own protective-stop distance), a stop sits at
entry + side x (1 - X) x MFE. The MFE is measured through bar j's high/low; the stop it implies acts from bar j + 1 (never
the bar that made the MFE). On a later bar: open through the stop = fill at the open, else a touch = fill at the stop. On the
trade's own exit bar it acts only when the leg's exit is NOT at that bar's open (an open exit is the same price). The leg's
size tilt and cost are kept: pts = s x (raw - cost).
"""
import json
import os
import sys

import numpy as np
import pandas as pd

REPO = r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"
sys.path.insert(0, REPO)
os.environ.pop("AUGUR_TRIAL_CACHE", None)
from augur_engine.data import find_master, load_master_arrays          # noqa: E402
from augur_engine.drawdowns import four_numbers                        # noqa: E402
from augur_engine.engine import run_backtest                           # noqa: E402
from augur_engine.fold_anchor import fold_bounds_check, BoundsDrift    # noqa: E402
from augur_engine.strategies import load_strategy                      # noqa: E402

OUT = r"C:\EdgeLog\_anatomy_cache\t74_giveback_orb"
RUN = r"C:\EdgeLog\_anatomy_cache\t74_giveback\run314.json"   # one Firestore read of run #314, cached
BOX = r"C:\EdgeLog\box_backup\2026-10-30_1445\qqq_exec\trades.csv"
QQQ1M = r"C:\EdgeLog\ohlc\QQQ_1m.csv"
Y_ARM = [0.5, 1.0, 1.5]                                # MFE arm, in R
X_GIVE = [0.33, 0.50, 0.67]                            # share of the MFE given back that exits


# ------------------------------------------------------------------------------------------- Webull leg
def webull():
    t = pd.read_csv(BOX)
    t = t[(t.leg == "ORB") & t.exit_px.notna()].copy()
    b = pd.read_csv(QQQ1M).dropna(subset=["high", "low"])
    b["ts"] = pd.to_datetime(b.time, unit="s", utc=True).dt.tz_convert("America/New_York").dt.tz_localize(None)
    b = b.set_index("ts").sort_index()
    rows = []
    for _, r in t.iterrows():
        e0, e1 = pd.Timestamp(r.entry_ts).floor("min"), pd.Timestamp(r.exit_ts)
        p = b.loc[e0:e1 - pd.Timedelta(seconds=1)]
        sd = 1 if r.side == "long" else -1
        fin = sd * (r.exit_px - r.entry_px)
        if len(p):
            mfe = max(fin, sd * ((p.high.max() if sd > 0 else p.low.min()) - r.entry_px))
            mae = min(fin, sd * ((p.low.min() if sd > 0 else p.high.max()) - r.entry_px))
        else:
            mfe = mae = np.nan
        rows.append(dict(src="webull", entry=r.entry_ts, side=r.side, shares=r.shares, final=fin, mfe=mfe, mae=mae,
                         giveback=mfe - fin, bars=len(p), exit_reason=r.exit_reason))
    return pd.DataFrame(rows)


# ------------------------------------------------------------------------------------------- the #314 WF chain
def chain():
    """[(fold, entry_bar, exit_bar, side, entry_px, raw_pts, size=1, risk)] for every #314 WF chain trade, global bar indices, +
    the arrays. Parity: per fold the costed pts and count equal the stored oos_pnl / oos_trades."""
    d = json.load(open(RUN))
    v, win = d["validate"], d["validate"]["windows"]
    strat = load_strategy(os.path.join(REPO, "augur_strategies", d["strategy"]))
    cost, mult = float(d["cost_pts"]), float(d.get("multiplier") or 20.0)
    m = find_master(d["instrument"], d.get("timeframe", "5m"), "rth", d["data_source"])
    A = load_master_arrays(m, date_from=d["date_from"], date_to=win["optimize"][1])     # stops at the optimize end
    idx = pd.DatetimeIndex(A["index"])
    idx = idx.tz_convert("America/New_York").tz_localize(None) if idx.tz is not None else idx
    did = np.asarray(A["day_id"])
    warm = int(win.get("warm_days") or 0)
    pkeys = list(v["champion"].keys())
    rows = sorted([r for r in d["top10_results"] if "fold" in r], key=lambda r: int(r["fold"]))
    expect = int(rows[-1]["train_bars"]) + int(rows[-1]["test_bars"])

    def warm_start(a0):
        if warm <= 0 or a0 <= 0:
            return a0
        tgt = int(did[a0]) - warm
        return 0 if tgt <= int(did[0]) else int(np.searchsorted(did, tgt, side="left"))

    # The run's bounds are bar indices on the pre-10-14 master. Two NT splices since added 60 bars on 2020-02-28 and 69 on
    # 2020-06-30 (master provenance), 129 in all = today's length minus the last fold's end. A stored index past a splice
    # moves by the bars inserted before it (FOLD BOUNDS = BAR INDICES); per-fold parity below proves the mapping.
    ins = [(pd.Timestamp("2020-02-28"), 60), (pd.Timestamp("2020-06-30"), 69)]
    if len(idx) - expect != sum(n for _, n in ins):
        raise SystemExit("bar drift %d is not the two known splices" % (len(idx) - expect))
    first = {dd: int(np.searchsorted(idx.normalize(), dd, side="left")) for dd, _ in ins}

    def shift(b):
        k = b
        for dd, n in ins:                                  # old index b sits after the splice day -> +n
            if k >= first[dd] + 0 and idx[min(k, len(idx) - 1)].normalize() > dd:
                k += n
        return k

    out, ok = [], True
    for r in rows:
        s0, s1 = shift(int(r["train_bars"])), shift(int(r["train_bars"]) + int(r["test_bars"]))
        w = warm_start(s0)
        S = {k: (x[w:s1] if hasattr(x, "__len__") and not isinstance(x, (str, dict)) and len(x) == len(idx) else x)
             for k, x in A.items()}
        pp = dict({k: r[k] for k in pkeys}, return_levels=True)
        res = run_backtest(strat, arrays=S, params=pp, cost_pts=cost, return_trades=True)
        T, lv = res["trades"], res.get("levels")
        sz = res.get("trade_sizes") or [1.0] * len(T)          # ORB #314 trades one contract
        assert lv is not None and len(lv) == len(T), "levels missing"
        keep = [(t, s, l) for t, s, l in zip(T, sz, lv) if int(t[0]) >= s0 - w]
        net = sum(float(t[2]) for t, _, _ in keep)
        good = abs(net - float(r["oos_pnl"])) < 1e-6 * max(1.0, abs(net)) + 1e-6 and len(keep) == int(r["oos_trades"])
        ok &= good
        print("  fold %d: %d trades / %.2f pts (stored %d / %.2f) %s" % (int(r["fold"]), len(keep), net,
              int(r["oos_trades"]), float(r["oos_pnl"]), "OK" if good else "MISMATCH"), flush=True)
        for t, s, l in keep:
            s = float(s)
            pts = float(t[2])                                   # = s x (raw - cost) after the engine's cost
            raw = pts / s + cost
            out.append((int(r["fold"]), int(t[0]) + w, int(t[1]) + w, int(t[3]), float(t[4]), raw, s, float(l["risk"])))
    wf = v["wf_oos"]
    tot = sum(s * (raw - cost) for *_, raw, s, _ in out)
    ok &= abs(tot - float(wf["net"])) < 0.1 and len(out) == int(wf["trades"])
    print("PARITY %s: chain %.1f pts / %d trades vs stored %.1f / %d" % ("PASS" if ok else "FAIL", tot, len(out),
                                                                          wf["net"], wf["trades"]))
    if not ok:      # prereg: the study compares two exits on the SAME rebuilt trades; the drift is reported, not hidden
        print("  (not bit-exact: today's master differs from #314's in places; both arms below use these same trades)")
    return out, A, idx, dict(cost=cost, mult=mult, wf=wf)


def paths(tr, A):
    """MFE / MAE (pts) per chain trade and whether its exit is at the exit bar's open."""
    O, H, L = (np.asarray(A[k], float) for k in ("open", "high", "low"))
    rows = []
    for f, e, x, sd, ep, raw, s, risk in tr:
        xp = ep + sd * raw
        at_open = abs(xp - O[x]) < 1e-9
        hi = x if at_open else x + 1
        seg_h, seg_l = H[e:hi], L[e:hi]
        mfe = max(raw, sd * ((seg_h.max() if sd > 0 else seg_l.min()) - ep)) if hi > e else raw
        mae = min(raw, sd * ((seg_l.min() if sd > 0 else seg_h.max()) - ep)) if hi > e else raw
        rows.append(dict(fold=f, e=e, x=x, side=sd, entry=ep, raw=raw, size=s, risk=risk, mfe=mfe, mae=mae,
                         giveback=mfe - raw, at_open=at_open))
    return pd.DataFrame(rows)


def simulate(tr, A, y, xg):
    """raw pts per trade under the giveback stop (Y in R, X share given back)."""
    O, H, L = (np.asarray(A[k], float) for k in ("open", "high", "low"))
    out = []
    for f, e, x, sd, ep, raw, s, risk in tr:
        xp = ep + sd * raw
        at_open = abs(xp - O[x]) < 1e-9
        run, res = 0.0, raw
        last = x if not at_open else x - 1                  # last bar on which the overlay may act before the leg's exit
        for j in range(e, x + 1):
            if j > e and run >= y * risk and risk > 0 and j <= last:
                lvl = ep + sd * (1.0 - xg) * run
                if sd > 0:
                    if O[j] < lvl:
                        res = O[j] - ep
                        break
                    if L[j] <= lvl:
                        res = lvl - ep
                        break
                else:
                    if O[j] > lvl:
                        res = ep - O[j]
                        break
                    if H[j] >= lvl:
                        res = ep - lvl
                        break
            if j >= x:
                break
            run = max(run, sd * ((H[j] if sd > 0 else L[j]) - ep))
        out.append(res)
    return np.asarray(out)


def daily_four(tr, raws, idx, meta):
    cost, mult, wf = meta["cost"], meta["mult"], meta["wf"]
    s = np.asarray([t[6] for t in tr])
    usd = s * (np.asarray(raws) - cost) * mult
    dates = [idx[t[1] - 1].normalize() for t in tr]                 # the decision bar's date, as noise_chain_read
    sess = pd.Index(sorted({x.normalize() for x in idx if pd.Timestamp(wf["from"]) <= x.normalize() <= pd.Timestamp(wf["to"])}))
    daily = pd.Series(usd, index=dates).groupby(level=0).sum().reindex(sess, fill_value=0.0)
    f = four_numbers(daily, years=float(wf["years"]))
    folds = pd.Series(usd).groupby([t[0] for t in tr]).sum()
    return f, folds, usd


def main():
    mode = (sys.argv[1:] or ["describe"])[0]
    os.makedirs(OUT, exist_ok=True)
    tr, A, idx, meta = chain()
    if mode == "describe":
        w = webull()
        w.to_csv(os.path.join(OUT, "webull_orb_mfe.csv"), index=False)
        p = paths(tr, A)
        p.to_csv(os.path.join(OUT, "chain_314_mfe.csv"), index=False)
        for lab, df, unit in (("WEBULL ORB (QQQ $/share)", w, 1.0), ("WF CHAIN #314 (NQ pts)", p, 1.0)):
            g = df.giveback
            pos = df[df.mfe > 0]
            print("\n%s: %d trades | final mean %.2f | MFE median %.2f p90 %.2f | MAE median %.2f | giveback median %.2f "
                  "p75 %.2f p90 %.2f | median giveback / MFE (MFE>0) %.0f%% | trades whose MFE >= 2x their final and "
                  "final <= 0: %d" % (lab, len(df), df.final.mean() if "final" in df else df.raw.mean(), df.mfe.median(),
                                      df.mfe.quantile(.9), df.mae.median(), g.median(), g.quantile(.75), g.quantile(.9),
                                      100 * (pos.giveback / pos.mfe).median(),
                                      int(((df.mfe > 0) & ((df.final if "final" in df else df.raw) <= 0)).sum())))
        p["mfe_R"], p["give_R"] = p.mfe / p.risk, p.giveback / p.risk
        print("chain in R: MFE median %.2f p90 %.2f | giveback median %.2f p90 %.2f | MFE>=0.5R %.0f%% >=1R %.0f%% >=1.5R %.0f%%"
              % (p.mfe_R.median(), p.mfe_R.quantile(.9), p.give_R.median(), p.give_R.quantile(.9),
                 100 * (p.mfe_R >= .5).mean(), 100 * (p.mfe_R >= 1).mean(), 100 * (p.mfe_R >= 1.5).mean()))
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots(1, 2, figsize=(11, 4))
        ax[0].hist(w.giveback.dropna(), bins=20, color="#555")
        ax[0].set_title("Webull ORB: giveback (MFE - final), $/share, n=%d" % len(w))
        ax[1].hist(p.give_R.clip(upper=5), bins=40, color="#555")
        ax[1].set_title("#314 WF chain: giveback in R (clipped at 5), n=%d" % len(p))
        fig.tight_layout()
        fig.savefig(os.path.join(OUT, "giveback_hist.png"), dpi=110)
        print("wrote", OUT)
        return 0
    if mode == "grid":
        raw0 = np.asarray([t[5] for t in tr])
        base, bf, _ = daily_four(tr, raw0, idx, meta)
        rows = [dict(cell="HOLD (leg as is)", y=None, x=None, **{k: base[k] for k in ("roc30", "dd5_usd", "dd_pct_peak", "sortino", "one_episode", "max_dd", "net")}, folds_won="-")]
        for y in Y_ARM:
            for xg in X_GIVE:
                r = simulate(tr, A, y, xg)
                f, ff, _ = daily_four(tr, r, idx, meta)
                won = int((ff > bf + 1e-9).sum())
                rows.append(dict(cell="Y%.1fR X%d%%" % (y, round(100 * xg)), y=y, x=xg,
                                 **{k: f[k] for k in ("roc30", "dd5_usd", "dd_pct_peak", "sortino", "one_episode", "max_dd", "net")},
                                 folds_won="%d/%d" % (won, len(bf)), changed=int((np.abs(r - raw0) > 1e-9).sum())))
        g = pd.DataFrame(rows)
        g.to_csv(os.path.join(OUT, "grid_wf.csv"), index=False)
        pd.set_option("display.width", 200)
        print(g.round(3).to_string(index=False))
        return 0


if __name__ == "__main__":
    sys.exit(main())
