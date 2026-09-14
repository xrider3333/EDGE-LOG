"""r57 IMBALANCE PROBE -- selection-only descriptive checks behind the imbalance/candle-quality
hypotheses (2026-09-14). NOT a strategy, NOT a rule test: it reads the r57 anatomy's per-trade
table (crown = ENGUQ_1M_ETH_R2_1_0.py defaults, 1,831 SELECTION trades, signal bars recovered
exactly) and adds four signal-bar features the anatomy did not build:

  1. up-volume share with DOJIS EXCLUDED (volume on close>open bars / volume on close!=open bars)
     over the last N bars incl. the signal bar -- checks whether the anatomy's up-volume/up-bar
     reads are a tick-grid artifact (a 0.25-pt grid on a 0.8-pt ATR prints many close==open bars
     in 2010-14, which the anatomy's 'close>open' share counts as NOT up).
  2. doji share of the last 30 bars (the artifact's size, by era).
  3. clock-relative LEG volume ratio: mean clock-normalised volume per bar on the recovery leg
     (swing-low bar -> signal bar) / on the decline leg (window-high bar -> swing-low bar).
     Clock normalisation = volume / mean volume at the same ET clock minute over the prior 20
     ETH sessions (the anatomy's imb_vol_vs_clock20 convention). Every input is a closed bar at
     or before the signal bar.
  4. the composite spike cell: clock-relative signal volume >= 1.0 AND signal range >= 1.0 ATR.

INFORMATION TIME: every feature uses bars <= the signal bar (known at its close). The master is
truncated to bars before 2025-06-30 00:00 ET immediately after loading; no lockbox bar or trade
is read. Outcome columns come from the anatomy table (selection trades only).

Run from the shared checkout (master registry):  python <worktree>/tools/r57_imbalance_probe.py
"""
import os
import sys
import warnings

warnings.filterwarnings("ignore")
SHARED = r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"
sys.path.insert(0, SHARED)
import numpy as np            # noqa: E402
import pandas as pd           # noqa: E402

CSV = r"C:\EdgeLog\_anatomy_cache\r57\r57_selection_signal_features.csv"
OUT = os.path.join(os.environ.get("R57_SCRATCH", "."), "r57_imbalance_probe.txt")
WIN = ("2010-06-07", "2026-06-30")
SPLIT = "2025-06-30"
TL, AL = 206, 52
LINES = []


def say(s=""):
    print(s, flush=True)
    LINES.append(s)


def main():
    from augur_engine.data import find_master, load_master_arrays
    T = pd.read_csv(CSV)
    m = find_master("NQ", "1m", "eth", "db_noadj_eth")
    arr = load_master_arrays(m, date_from=WIN[0], date_to=WIN[1])
    idx = pd.DatetimeIndex(arr["index"])
    n_split = int(idx.searchsorted(pd.Timestamp(SPLIT, tz=idx.tz)))
    O = np.asarray(arr["open"][:n_split], float); H = np.asarray(arr["high"][:n_split], float)
    L = np.asarray(arr["low"][:n_split], float); C = np.asarray(arr["close"][:n_split], float)
    V = np.asarray(arr["volume"][:n_split], float); ix = idx[:n_split]
    del arr
    n = len(C)
    s = T["signal_bar"].to_numpy(np.int64)
    assert s.max() < n, "a signal bar sits at/after the split"
    # mapping check: the anatomy table's signal_time must equal the bar timestamp
    mism = int((ix[s].astype(str).str[:19] != T["signal_time"].astype(str).str[:19]).sum())
    say("bars before split %d | trades %d | signal_time mismatches %d" % (n, len(T), mism))

    tr = np.empty(n); tr[0] = H[0] - L[0]
    tr[1:] = np.maximum(H[1:] - L[1:], np.maximum(np.abs(H[1:] - C[:-1]), np.abs(L[1:] - C[:-1])))
    cs = np.cumsum(tr); atr = np.full(n, np.nan)
    atr[AL - 1:] = (cs[AL - 1:] - np.concatenate([[0], cs[:-AL]])) / AL
    atr = np.where(np.isnan(atr), tr, atr); del cs
    lim_chk = np.nanmax(np.abs((C[s] - 0.55 * atr[s]) - T["limit"].to_numpy()))
    say("limit reconstruction max abs error (pts): %.6f" % lim_chk)

    up = C > O; dn = C < O; dj = C == O
    Vu = np.cumsum(np.where(up, V, 0.0)); Vd = np.cumsum(np.where(dn, V, 0.0)); Dj = np.cumsum(dj)

    def wsum(cum, N):
        return cum[s] - np.where(s - N >= 0, cum[np.clip(s - N, 0, None)], 0.0)
    for N in (10, 20, 30):
        u = wsum(Vu, N); d = wsum(Vd, N)
        T["uvsx%d" % N] = np.where(u + d > 0, u / np.maximum(u + d, 1e-9), np.nan)
    T["doji30"] = wsum(Dj.astype(float), 30) / 30.0

    # clock baseline: ETH day (rolls 18:00 ET) x clock minute, prior 20 sessions (anatomy convention)
    dkey = (ix + pd.Timedelta(hours=6)).tz_localize(None).normalize().asi8
    did = pd.factorize(dkey)[0].astype(np.int64); del dkey
    nd = int(did.max()) + 1
    cm = (ix.hour.to_numpy() * 60 + ix.minute.to_numpy()).astype(np.int64)
    M = np.zeros((nd, 1440), np.float32); Cn = np.zeros((nd, 1440), np.float32)
    M[did, cm] = V; Cn[did, cm] = 1.0
    csZ = np.cumsum(M, axis=0, dtype=np.float64); csN = np.cumsum(Cn, axis=0, dtype=np.float64)
    del M, Cn

    def base_of(k):
        d0 = did[k]; d1 = d0 - 21
        sv = np.where(d0 >= 1, csZ[np.clip(d0 - 1, 0, None), cm[k]], 0.0) - np.where(d1 >= 0, csZ[np.clip(d1, 0, None), cm[k]], 0.0)
        cv = np.where(d0 >= 1, csN[np.clip(d0 - 1, 0, None), cm[k]], 0.0) - np.where(d1 >= 0, csN[np.clip(d1, 0, None), cm[k]], 0.0)
        return np.where((d0 >= 21) & (cv >= 10), sv / np.maximum(cv, 1.0), np.nan)

    T["vclock"] = V[s] / base_of(s)
    T["rng_atr"] = (H[s] - L[s]) / atr[s]
    vc_chk = np.nanmax(np.abs(T["vclock"] - T["imb_vol_vs_clock20"]))
    say("clock-volume reconstruction vs anatomy imb_vol_vs_clock20, max abs diff: %.4g" % vc_chk)

    legr = np.full(len(s), np.nan); leg_ok = np.zeros(len(s), bool)
    for q, k in enumerate(s):
        hi_i = k - TL + int(np.argmax(H[k - TL:k]))
        lo_i = k - TL + int(np.argmin(L[k - TL:k + 1]))
        if hi_i < lo_i < k:
            dn_leg = np.arange(hi_i + 1, lo_i + 1); up_leg = np.arange(lo_i + 1, k + 1)
            bd = base_of(dn_leg); bu = base_of(up_leg)
            rd = V[dn_leg] / bd; ru = V[up_leg] / bu
            if np.isfinite(rd).sum() >= 5 and np.isfinite(ru).sum() >= 5:
                legr[q] = np.nanmean(ru) / max(np.nanmean(rd), 1e-9); leg_ok[q] = True
    T["leg_vr"] = legr
    say("leg ratio defined (window high precedes swing low): %.1f%% of trades" % (100 * leg_ok.mean()))

    def rd_(x):
        w = x.Rg[x.Rg > 0].sum(); l_ = -x.Rg[x.Rg < 0].sum()
        return "n=%4d win=%5.1f%% PF(R)=%.2f meanRg=%+.3f" % (len(x), 100 * x.win.mean(), w / max(l_, 1e-9), x.Rg.mean())

    say("\nBASE  all: " + rd_(T) + " | E1: " + rd_(T[T.era2 == 0]) + " | E2: " + rd_(T[T.era2 == 1]))
    say("\nDOJI SHARE of the last 30 bars at the signal, by era (the tick-grid artifact size):")
    for e in (0, 1):
        say("  era2=%d median %.3f  p90 %.3f" % (e, T.loc[T.era2 == e, "doji30"].median(), T.loc[T.era2 == e, "doji30"].quantile(.9)))
    say("  spearman(anatomy upbar_share20, doji30) = %.2f ; spearman(anatomy upvol_share10, doji30) = %.2f"
        % (T[["imb_upbar_share20", "doji30"]].corr("spearman").iloc[0, 1], T[["imb_upvol_share10", "doji30"]].corr("spearman").iloc[0, 1]))

    def by_q(col, label):
        say("\n%s -- within-era quintiles (cuts fit inside each era; descriptive, selection only)" % label)
        for e in (0, 1):
            x = T[(T.era2 == e) & T[col].notna()].copy()
            x["q"] = pd.qcut(x[col].rank(method="first"), 5, labels=False)
            cuts = x.groupby("q")[col].min().round(3).tolist()
            say("  E%d cuts(min per Q) %s" % (e + 1, cuts))
            for qq in range(5):
                say("    Q%d %s" % (qq + 1, rd_(x[x.q == qq])))
    by_q("imb_upvol_share10", "ANATOMY up-volume share 10 (dojis counted as not-up)")
    by_q("uvsx10", "DOJI-EXCLUDED up-volume share 10")
    by_q("uvsx20", "DOJI-EXCLUDED up-volume share 20")
    by_q("uvsx30", "DOJI-EXCLUDED up-volume share 30")
    by_q("leg_vr", "CLOCK-RELATIVE LEG VOLUME RATIO (recovery leg / decline leg)")
    by_q("rng_atr", "SIGNAL RANGE in ATR(52)")

    say("\nCOMPOSITE SPIKE CELLS (clock-relative volume floor x range floor), by era:")
    for vc in (0.0, 1.0, 1.5):
        for rg in (0.0, 1.0, 1.5):
            keep = (T.vclock.fillna(0) >= vc) & (T.rng_atr >= rg)
            say("  vclock>=%.1f rng>=%.1f keep %4.1f%% | E1 %s | E2 %s" % (
                vc, rg, 100 * keep.mean(), rd_(T[keep & (T.era2 == 0)]), rd_(T[keep & (T.era2 == 1)])))
    say("\nspearman with volatility level (ctx_atr_pct_price): uvsx10 %.2f uvsx30 %.2f leg_vr %.2f vclock %.2f rng_atr %.2f"
        % tuple(T[[c, "ctx_atr_pct_price"]].corr("spearman").iloc[0, 1] for c in ("uvsx10", "uvsx30", "leg_vr", "vclock", "rng_atr")))
    # leg-ratio cap (climax veto) descriptive read + tail retention, selection only
    topR = T.nlargest(36, "Rg").index; topU = T.nlargest(20, "usd").index
    for cap in (1.0, 1.15, 1.3, 1.5):
        veto = T.leg_vr >= cap
        keep = ~veto
        say("  leg cap %.2f: vetoes %4.1f%% | kept E1 %s | kept E2 %s | vetoed E1 %s | vetoed E2 %s | R-tail36 kept %d | top20$ kept %d"
            % (cap, 100 * veto.mean(), rd_(T[keep & (T.era2 == 0)]), rd_(T[keep & (T.era2 == 1)]),
               rd_(T[veto & (T.era2 == 0)]) if (veto & (T.era2 == 0)).any() else "-",
               rd_(T[veto & (T.era2 == 1)]) if (veto & (T.era2 == 1)).any() else "-",
               int(keep[topR].sum()), int(keep[topU].sum())))
    T[["signal_bar", "era2", "win", "Rg", "usd", "uvsx10", "uvsx20", "uvsx30", "doji30", "vclock", "rng_atr", "leg_vr"]] \
        .to_csv(os.path.join(os.path.dirname(CSV), "r57_imbalance_probe_features.csv"), index=False)
    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write("\n".join(LINES) + "\n")
    say("\nwrote " + OUT)


if __name__ == "__main__":
    main()
