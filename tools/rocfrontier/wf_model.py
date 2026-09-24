"""Moved from a session scratchpad 2026-09-24 (ROC frontier hunt); results in RESEARCH_LEDGER.md rows 1.15 / 2.12-2.19.
Walk-forward standalone model on the causal feature table (feats.py). Yearly expanding refit:
model for year Y is trained ONLY on decisions dated before Y-01-01. Trading: at each 30-min decision,
position = sign(pred) if |pred| > theta else 0; same-sign runs are one trade; cost 0.2665 pts per side.
$20/pt, 1 NQ. SCAN-LEVEL until it exists as a strategy file."""
import os, sys, numpy as np, pandas as pd, xgboost as xgb
CACHE = os.environ.get("EDGELOG_ROCFRONTIER", r"C:\EdgeLog\_anatomy_cache\rocfrontier")
F = pd.read_pickle(os.path.join(CACHE, sys.argv[1] if len(sys.argv) > 1 else "feats_nq5_h6.pkl"))
F["yr"] = F["date"].dt.year
X_COLS = ["tod", "dow", "r_open", "r_open_sig", "r_pc", "gap", "r30", "r60", "r120", "vwd", "rng_sf", "pos_rng",
          "or_d", "or_w", "pd_ret", "pd_clv", "pd_rng", "r5d", "tr20", "tr50", "tr200", "rv", "cvr", "sq"]
def fit_predict(train, test, depth=3, n=300, lr=0.03, seed=0):
    m = xgb.XGBRegressor(n_estimators=n, max_depth=depth, learning_rate=lr, subsample=0.8, colsample_bytree=0.8,
                         min_child_weight=50, reg_lambda=5.0, nthread=1, random_state=seed, verbosity=0)
    y = train["tgt"].clip(-1, 1)
    m.fit(train[X_COLS], y)
    return m.predict(test[X_COLS])
preds = pd.Series(np.nan, index=F.index)
for Y in range(2013, 2026):
    tr = F[F.yr < Y]; te = F[F.yr == Y]
    if len(te) == 0: continue
    preds[te.index] = fit_predict(tr, te)
    print("fit", Y, len(tr), len(te), flush=True)
F["pred"] = preds
F.to_pickle(os.path.join(CACHE, "wf_preds.pkl"))
def simulate(sig, cost_side=0.2665):
    """sig: position per decision row (-1/0/+1). Returns per-row $ pnl incl. costs, trade list."""
    pnl = np.zeros(len(F)); pos_prev = 0; d_prev = -1; trades = []; cur = 0.0
    tp = F["tgt_pts"].values; dd_ = F["d"].values
    for i in range(len(F)):
        p = int(sig[i]); d = dd_[i]
        if d != d_prev and pos_prev != 0:        # new session: previous position was closed at EOD
            pnl[i - 1] -= cost_side * abs(pos_prev); cur -= cost_side * abs(pos_prev); trades.append(cur); cur = 0.0; pos_prev = 0
        if p != pos_prev:
            c_ = cost_side * abs(p - pos_prev)
            if pos_prev != 0:
                cur -= cost_side * abs(pos_prev); trades.append(cur); cur = 0.0
                c_ -= cost_side * abs(pos_prev)
            pnl[i] -= c_ + (cost_side * abs(pos_prev) if pos_prev != 0 else 0); cur -= c_
        pnl[i] += p * tp[i]; cur += p * tp[i]
        pos_prev = p; d_prev = d
    if pos_prev != 0:
        pnl[-1] -= cost_side * abs(pos_prev); cur -= cost_side * abs(pos_prev); trades.append(cur)
    return pnl * 20, np.array(trades) * 20
def report(name, sig, y0=2016, y1=2025):
    pnl, trades = simulate(sig)
    s = pd.Series(pnl, index=F["date"]).groupby(level=0).sum()
    w = s[(s.index.year >= y0) & (s.index <= "2025-06-30")]
    yrs = (w.index[-1] - w.index[0]).days / 365.25
    cc = w.cumsum(); dd = float((cc.cummax() - cc).max())
    by = w.groupby(w.index.year).sum()
    print("%-34s %d-%d net $%9.0f  $/yr %8.0f ROC %5.1f%%  DD $%7.0f  MAR %5.2f  trades %5d  yrs+ %d/%d  | %s" % (
        name, y0, y1, w.sum(), w.sum() / yrs, 100 * w.sum() / yrs / 1e5, dd, (w.sum() / yrs) / dd if dd else 0, len(trades),
        int((by > 0).sum()), len(by), " ".join("%d:%+.0fk" % (yy, vv / 1000) for yy, vv in by.items())))
    return s
ok = F["pred"].notna()
for th in (0.0, 0.02, 0.04, 0.06, 0.08):
    sig = np.where(ok & (F["pred"] > th), 1, np.where(ok & (F["pred"] < -th), -1, 0))
    report("model |pred|>%.2f" % th, sig)
for th in (0.02, 0.04, 0.06):
    sig = np.where(ok & (F["pred"] > th), 1, 0)
    report("model long-only pred>%.2f" % th, sig)
# baselines on the same decision grid
for k in (1.0, 1.5, 2.0):
    ros = F["r_open_sig"].values
    sig = np.where(ok & (ros > k), 1, np.where(ok & (ros < -k), -1, 0))
    report("baseline noise-mom |sig|>%.1f" % k, sig)
report("baseline always long", np.where(ok, 1, 0))
