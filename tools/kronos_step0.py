"""KRONOS Step 0 (2026-10-01, owner GO via MANAGER #40) - docs/PREREG_kronos_step0_2026-10-01.md (a341da5d).

Does Kronos forecast the next session's RTH range better than free baselines (TRAIL5, EWMA, HAR, overnight)?
Score = QLIKE on squared ranges; one scale factor per model fitted on H1 only; Diebold-Mariano (Newey-West 5).

    python tools/kronos_step0.py baselines      build sessions + the four free forecasts, print their scores
    python tools/kronos_step0.py kronos         (needs C:\\EdgeLog\\kronos\\ - the owner-approved download) run
                                               Kronos for seeds 1-5 and judge the pre-registered bar
Run from the shared checkout (masters registry) or set EDGELOG_ROOT to it.
"""
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.environ.get("EDGELOG_ROOT") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

OUT = r"C:\EdgeLog\kronos"
T0, H2_0, T1 = pd.Timestamp("2024-07-01"), pd.Timestamp("2025-07-01"), pd.Timestamp("2026-09-30")
HAR_FIT = (pd.Timestamp("2010-07-01"), pd.Timestamp("2024-06-28"))
MIN_RTH_BARS, LAMBDA, CTX, PATHS, SEEDS = 70, 0.94, 512, 20, (1, 2, 3, 4, 5)
BASELINES = ("TRAIL5", "EWMA", "HAR", "OVN")


def sessions(sym):
    """One row per session D: 24-hour daily bar (18:00 D-1 .. 16:55 D), RTH range (09:30..15:55), overnight range
    (18:00 D-1 .. 09:25 D), RTH bar count. Roll-corrected 5m 24-hour master ADJ_<SYM>_5m_ETH (db_adj_eth)."""
    from augur_engine.data import find_master, load_master_arrays
    A = load_master_arrays(find_master(sym, "5m", "eth", "db_adj_eth"), date_from="2009-01-01")
    idx = pd.DatetimeIndex(A["index"])
    idx = idx.tz_convert("US/Eastern").tz_localize(None) if idx.tz is not None else idx
    df = pd.DataFrame({k: np.asarray(A[k], float) for k in ("open", "high", "low", "close", "volume")}, index=idx)
    df["sess"] = (df.index + pd.Timedelta(hours=6)).normalize()        # 18:00 belongs to the next session
    tm = df.index.hour * 60 + df.index.minute
    rth = (tm >= 570) & (tm <= 955)                                     # 09:30 .. 15:55 bar opens
    ovn = ~rth & ((tm >= 1080) | (tm < 570))                            # 18:00 .. 09:25
    g = df.groupby("sess")
    out = pd.DataFrame({"open": g.open.first(), "high": g.high.max(), "low": g.low.min(), "close": g.close.last(),
                        "volume": g.volume.sum()})
    r = df[rth].groupby("sess")
    out["rth_range"] = r.high.max() - r.low.min()
    out["rth_bars"] = r.size()
    o = df[ovn].groupby("sess")
    out["ovn_range"] = o.high.max() - o.low.min()
    out = out[out.index.dayofweek < 5]
    out["rth_bars"] = out.rth_bars.fillna(0)
    out["valid"] = out.rth_bars >= MIN_RTH_BARS
    return out


def baselines(S):
    """Each forecast for session D uses only sessions before D (OVN: D's own overnight, known at 09:30)."""
    v = S[S.valid].copy()
    R = v.rth_range
    f = pd.DataFrame(index=v.index)
    f["TRAIL5"] = R.shift(1).rolling(5).mean()
    ew = np.full(len(R), np.nan)
    acc = float((R.iloc[:20] ** 2).mean())
    for i in range(len(R)):
        ew[i] = acc                                                     # value BEFORE session i
        acc = LAMBDA * acc + (1 - LAMBDA) * float(R.iloc[i]) ** 2
    ew[:21] = np.nan
    f["EWMA"] = np.sqrt(ew)
    lr = np.log(R)
    X = pd.DataFrame({"d": lr.shift(1), "w": lr.shift(1).rolling(5).mean(), "m": lr.shift(1).rolling(22).mean()})
    fit = X.notna().all(axis=1) & (v.index >= HAR_FIT[0]) & (v.index <= HAR_FIT[1])
    Xm = np.column_stack([np.ones(int(fit.sum())), X[fit].to_numpy()])
    beta = np.linalg.lstsq(Xm, lr[fit].to_numpy(), rcond=None)[0]
    f["HAR"] = np.exp(beta[0] + X.to_numpy() @ beta[1:])
    f["OVN"] = v.ovn_range
    f["target"] = R
    return f, beta


def qlike(target, fc):
    q = (np.asarray(target, float) ** 2) / (np.asarray(fc, float) ** 2)
    return q - np.log(q) - 1.0


def scale_h1(target, fc, h1):
    """QLIKE-optimal single scale on H1: k^2 = mean(s / h) over H1 (closed form)."""
    k2 = float(np.mean((target[h1] ** 2) / (fc[h1] ** 2)))
    return np.sqrt(k2)


def dm_onesided(lk, lb, lags=5):
    """Diebold-Mariano on d = Kronos loss - baseline loss, Newey-West variance; p = P(no better | data)."""
    from scipy.stats import norm
    d = np.asarray(lk, float) - np.asarray(lb, float)
    n, m = len(d), d.mean()
    e = d - m
    var = e @ e / n
    for L in range(1, lags + 1):
        var += 2 * (1 - L / (lags + 1)) * (e[L:] @ e[:-L]) / n
    t = m / np.sqrt(var / n)
    return float(t), float(norm.cdf(t))


def score(f, models):
    """Mean QLIKE and MSE of log range per half, after the H1-fitted scale."""
    tst = f[(f.index >= T0) & (f.index <= T1)].dropna(subset=list(models) + ["target"])
    h1 = (tst.index < H2_0)
    res, scaled = {}, {}
    for m in models:
        k = scale_h1(tst.target.to_numpy(), tst[m].to_numpy(), h1)
        fc = k * tst[m].to_numpy()
        scaled[m] = fc
        L = qlike(tst.target.to_numpy(), fc)
        mse = (np.log(tst.target.to_numpy()) - np.log(fc)) ** 2
        res[m] = dict(k=k, H1=float(L[h1].mean()), H2=float(L[~h1].mean()),
                      mse_H1=float(mse[h1].mean()), mse_H2=float(mse[~h1].mean()))
    return tst, h1, res, scaled


def run_baselines():
    for sym in ("NQ", "ES"):
        S = sessions(sym)
        f, beta = baselines(S)
        os.makedirs(OUT, exist_ok=True)
        S.to_csv(os.path.join(OUT, f"sessions_{sym}.csv"))
        f.to_csv(os.path.join(OUT, f"baselines_{sym}.csv"))
        tst, h1, res, _ = score(f, BASELINES)
        print(f"{sym}: test sessions {len(tst)} (H1 {int(h1.sum())}, H2 {int((~h1).sum())}); HAR beta {np.round(beta, 3)}")
        for m, r in res.items():
            print(f"  {m:7s} scale {r['k']:.3f}  QLIKE H1 {r['H1']:.4f}  H2 {r['H2']:.4f}  | MSE(log) H1 {r['mse_H1']:.4f}  H2 {r['mse_H2']:.4f}")


# ---------------------------------------------------------------------------------------------------------------
# KRONOS ARM. Run with the isolated venv: C:\\EdgeLog\\kronos\\venv\\Scripts\\python.exe tools/kronos_step0.py kronos
# Code: github.com/shiyu-coder/Kronos @ 67b630e6 (model/ only, read before use). Weights: NeoQuasar/Kronos-small @
# 901c26c1, NeoQuasar/Kronos-Tokenizer-base @ 0e011738 (safetensors). Inference only; HF offline.
# Registered traps handled here: eval() mode (dropout off); every sampled path kept SEPARATELY (the released
# auto_regressive_inference averages paths - we re-implement its single-step body without the mean); one device
# (cuda:0) for every seed; future timestamp = the session date (public calendar), never read from the real bar.
# Path range = predicted high - predicted low, as registered; paths with high < low are COUNTED and reported.
KCODE, KHF = os.path.join(OUT, "code"), os.path.join(OUT, "hf")
TOPP, TEMP, CLIP, BATCH = 0.9, 1.0, 5.0, 8


def load_kronos(device="cuda:0"):
    os.environ["HF_HUB_OFFLINE"] = "1"
    sys.path.insert(0, KCODE)
    from model import Kronos, KronosTokenizer
    tok = KronosTokenizer.from_pretrained(os.path.join(KHF, "Kronos-Tokenizer-base")).to(device).eval()
    mdl = Kronos.from_pretrained(os.path.join(KHF, "Kronos-small")).to(device).eval()
    return tok, mdl


def stamps(dates):
    d = pd.DatetimeIndex(dates)
    return np.stack([d.minute, d.hour, d.weekday, d.day, d.month], axis=1).astype(np.float32)


def kronos_paths(tok, mdl, xs, xst, yst, n_paths, device="cuda:0"):
    """One-step forecast for a batch of normalised windows; returns (batch, n_paths, 6) normalised predictions,
    every path kept (body of the released auto_regressive_inference for pred_len = 1, minus its mean)."""
    import torch
    sys.path.insert(0, KCODE)
    from model.kronos import sample_from_logits
    with torch.no_grad():
        x = torch.clip(torch.from_numpy(xs).to(device), -CLIP, CLIP)
        x_stamp = torch.from_numpy(xst).to(device)
        y_stamp = torch.from_numpy(yst).to(device)
        B, L = x.shape[0], x.shape[1]
        x = x.unsqueeze(1).repeat(1, n_paths, 1, 1).reshape(-1, L, x.shape[2])
        x_stamp = x_stamp.unsqueeze(1).repeat(1, n_paths, 1, 1).reshape(-1, L, x_stamp.shape[2])
        y_stamp = y_stamp.unsqueeze(1).repeat(1, n_paths, 1, 1).reshape(-1, 1, y_stamp.shape[2])
        s1, s2 = tok.encode(x, half=True)
        s1_logits, context = mdl.decode_s1(s1, s2, x_stamp)
        pre = sample_from_logits(s1_logits[:, -1, :], temperature=TEMP, top_k=0, top_p=TOPP, sample_logits=True)
        s2_logits = mdl.decode_s2(context, pre)
        post = sample_from_logits(s2_logits[:, -1, :], temperature=TEMP, top_k=0, top_p=TOPP, sample_logits=True)
        full_pre = torch.cat([s1, pre], dim=1)[:, -L:]
        full_post = torch.cat([s2, post], dim=1)[:, -L:]
        z = tok.decode([full_pre.contiguous(), full_post.contiguous()], half=True)
        return z[:, -1, :].reshape(B, n_paths, -1).cpu().numpy()


def run_kronos(seeds=SEEDS, syms=("NQ", "ES")):
    import random
    import torch
    tok, mdl = load_kronos()
    for sym in syms:
        S = pd.read_csv(os.path.join(OUT, f"sessions_{sym}.csv"), index_col=0, parse_dates=True)
        S["amount"] = S.volume * S.close
        cols = ["open", "high", "low", "close", "volume", "amount"]
        test = S.index[S.valid & (S.index >= T0) & (S.index <= T1)]
        pos = {d: i for i, d in enumerate(S.index)}
        X = S[cols].to_numpy(np.float32)
        for seed in seeds:
            random.seed(seed); np.random.seed(seed); torch.manual_seed(seed); torch.cuda.manual_seed_all(seed)
            rows = []
            for b0 in range(0, len(test), BATCH):
                days = test[b0:b0 + BATCH]
                xs, xst, yst, mu, sd = [], [], [], [], []
                for d in days:
                    i = pos[d]
                    w = X[i - CTX:i]                                   # the 512 sessions BEFORE D
                    assert len(w) == CTX and S.index[i - 1] < d
                    m, s = w.mean(axis=0), w.std(axis=0)
                    xs.append((w - m) / (s + 1e-5)); mu.append(m); sd.append(s)
                    xst.append(stamps(S.index[i - CTX:i])); yst.append(stamps([d]))
                z = kronos_paths(tok, mdl, np.stack(xs).astype(np.float32), np.stack(xst), np.stack(yst), PATHS)
                for j, d in enumerate(days):
                    p = z[j] * (sd[j] + 1e-5) + mu[j]                  # (paths, 6) back in price units
                    rng = p[:, 1] - p[:, 2]
                    rows.append(dict(sess=d, fc=float(rng.mean()), neg_paths=int((rng < 0).sum()),
                                     **{f"p{k}": float(rng[k]) for k in range(PATHS)}))
            out = pd.DataFrame(rows).set_index("sess")
            out.to_csv(os.path.join(OUT, f"kronos_{sym}_seed{seed}.csv"))
            print(f"{sym} seed {seed}: {len(out)} forecasts, paths with high<low {int(out.neg_paths.sum())}, "
                  f"forecasts <= 0: {int((out.fc <= 0).sum())}", flush=True)


def judge():
    """The registered bar, read once."""
    verdict, lines = True, []
    for sym in ("NQ", "ES"):
        f = pd.read_csv(os.path.join(OUT, f"baselines_{sym}.csv"), index_col=0, parse_dates=True)
        per_seed = [pd.read_csv(os.path.join(OUT, f"kronos_{sym}_seed{s}.csv"), index_col=0, parse_dates=True).fc
                    for s in SEEDS]
        f["KRONOS"] = pd.concat(per_seed, axis=1).mean(axis=1)
        for s, fc in zip(SEEDS, per_seed):
            f[f"K{s}"] = fc
        models = BASELINES + ("KRONOS",) + tuple(f"K{s}" for s in SEEDS)
        tst, h1, res, scaled = score(f, models)
        lines.append(f"{sym}: {len(tst)} sessions (H1 {int(h1.sum())}, H2 {int((~h1).sum())})")
        for m in BASELINES + ("KRONOS",):
            lines.append(f"  {m:7s} scale {res[m]['k']:.3f}  QLIKE H1 {res[m]['H1']:.4f}  H2 {res[m]['H2']:.4f}  "
                         f"| MSE(log) H1 {res[m]['mse_H1']:.4f}  H2 {res[m]['mse_H2']:.4f}")
        tgt = tst.target.to_numpy()
        for half, mask in (("H1", h1), ("H2", ~h1)):
            best = min(BASELINES, key=lambda m: res[m][half])
            lk = qlike(tgt[mask], scaled["KRONOS"][mask])
            lb = qlike(tgt[mask], scaled[best][mask])
            gain = 1 - lk.mean() / lb.mean()
            t, p = dm_onesided(lk, lb)
            lines.append(f"  {half}: best baseline {best} {lb.mean():.4f}; Kronos {lk.mean():.4f}; gain {100 * gain:+.1f}% "
                         f"(need >= +5.0%); DM t {t:+.2f}, one-sided p {p:.3f} (need < 0.05)")
            if sym == "NQ":
                verdict &= (gain >= 0.05) and (p < 0.05)
            if sym == "ES" and half == "H2":
                verdict &= lk.mean() < lb.mean()
                lines.append(f"  ES check (Kronos below best baseline in H2): {lk.mean() < lb.mean()}")
            if sym == "NQ" and half == "H2":
                seeds_ok = [res[f"K{s}"]["H2"] < res[best]["H2"] for s in SEEDS]
                verdict &= all(seeds_ok)
                lines.append(f"  NQ H2 per seed beats {best}: {seeds_ok}")
        hh = qlike(tgt[~h1], scaled["KRONOS"][~h1]).mean() / qlike(tgt[~h1], scaled["HAR"][~h1]).mean() - 1
        lines.append(f"  head to head H2: Kronos QLIKE {100 * hh:+.1f}% vs HAR")
    lines.append("VERDICT: " + ("PASS" if verdict else "FAIL - Kronos is closed for good (registered)"))
    print("\n".join(lines))
    open(os.path.join(OUT, "VERDICT.txt"), "w", encoding="utf-8").write("\n".join(lines) + "\n")
    return verdict


if __name__ == "__main__":
    if sys.argv[1:] == ["baselines"]:
        run_baselines()
    elif sys.argv[1:] == ["kronos"]:
        run_kronos()
    elif sys.argv[1:] == ["judge"]:
        judge()
    else:
        raise SystemExit("usage: kronos_step0.py baselines | kronos | judge")
