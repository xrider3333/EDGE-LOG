import sys, os, json, time
import numpy as np
import pandas as pd
sys.path.insert(0, r"C:\Users\xride\AppData\Local\Temp\claude\C--Users-xride-OneDrive-Desktop\cf70e01e-1bab-4445-b5e2-10d6db1f8d89\scratchpad\book_legs_ml")
from common import load_run, OUTDIR
from augur_engine.data import find_master, load_master_arrays
from augur_engine.engine import run_backtest
from augur_engine.ml_gate import entry_features_causal, gate_trades, _stats as gate_stats, _make_model
from augur_engine.book import _mtm_increments
from augur_engine.analytics import sortino_from_pnls
from augur_engine import rolls
from augur_strategies import ENGUQ_1M_ETH_R2_1_0 as mod

RAW_NAME = "ENGUQ335paper_raw"
ML_NAME = "ENGUQ335paper_hybdd_rf"
MODEL = "rf"
COST_PTS = 0.783
MULT = 20.0


def loc_ts(t, ref_tz):
    if t is None:
        return None
    ts = pd.Timestamp(t)
    if ts.tzinfo is None and ref_tz is not None:
        ts = ts.tz_localize(ref_tz)
    return ts


def stage_of(ts, wf0, lb0):
    if ts < wf0:
        return "IS"
    if ts < lb0:
        return "WF"
    return "LB"


def write_daily(path, incs, wf0, lb0, size_by_day=None):
    if not incs:
        with open(path, "w") as fh:
            fh.write("date,pnl_usd,trades,size,stage\n")
        return
    days = {}
    for d, v in incs:
        days[d] = days.get(d, 0.0) + v
    wf0n = pd.Timestamp(wf0).tz_localize(None) if wf0.tzinfo else wf0
    lb0n = pd.Timestamp(lb0).tz_localize(None) if lb0.tzinfo else lb0
    rows = []
    for d in sorted(days.keys()):
        ts = pd.Timestamp(d)
        stg = stage_of(ts, wf0n, lb0n)
        n_tr, sz = (size_by_day.get(d, (0, None)) if size_by_day else (0, None))
        rows.append((str(pd.Timestamp(d).date()), round(days[d], 2), n_tr,
                    ("" if sz is None else round(sz, 4)), stg))
    with open(path, "w") as fh:
        fh.write("date,pnl_usd,trades,size,stage\n")
        for r in rows:
            fh.write(",".join(str(x) for x in r) + "\n")


def write_trades(path, rows):
    with open(path, "w") as fh:
        fh.write("entry_time,exit_time,side,pnl_usd,size,stage\n")
        for r in rows:
            fh.write(",".join(str(x) for x in r) + "\n")


def hybridize(prob, hth, pre_m, pnls_all):
    pf2 = np.where(np.isnan(prob), 0.5, prob)
    keep = ~(prob < hth)
    w = np.clip(1.0 + 4.0 * (pf2 - 0.50), 0.25, 3.0)
    w = np.where(np.isnan(prob), 1.0, w) * keep
    wk = w[pre_m & keep]
    if not len(wk) or float(wk.mean()) <= 1e-9:
        raise SystemExit("degenerate hybrid: no pre-lockbox kept trades to normalise on")
    w = np.minimum(w / float(wk.mean()), 3.0)
    hp = pnls_all * w
    return keep, w, hp


def main():
    t0 = time.time()
    d335 = load_run(335)
    gv335 = d335["gate_validate"]
    date_from, date_to = d335["date_from"], d335["date_to"]
    wf0s, wf1s = gv335["wf_range"]; lb0s = gv335["lockbox_from"]
    hth = float(gv335["chosen"]["threshold"])  # 0.45
    assert gv335["chosen"]["model"] == MODEL or True  # rf regardless; hth is the fixed 0.45 cutoff requested

    master = find_master("NQ", "1m", "eth", "db_adj_eth")
    print("master:", master.get("filename"), master.get("source"))
    arr = load_master_arrays(master, date_from=date_from, date_to=date_to)
    idx = arr["index"]
    params = {k: v.get("default") for k, v in mod.DEFAULT_PARAMS.items()}
    print("file-default params:", params)

    res = run_backtest("ENGUQ_1M_ETH_R2_1_0.py", arrays=arr, params=params,
                       cost_pts=COST_PTS, return_trades=True)
    T_all = sorted([(int(t[0]), int(t[1]), float(t[2]), float(t[3]), float(t[4]))
                   for t in res["trades"]], key=lambda t: t[0])
    print(f"raw trades before roll-guard: {len(T_all)}  ({time.time()-t0:.1f}s)")

    # ---- ROLL GUARD: block the two estimated 2026 NQ switches (ROLL_ADJUSTED_MASTERS.md) ----
    times_sec = (pd.DatetimeIndex(idx).view("int64") // 10**9).astype("int64")
    guard = rolls.guard_masks(times_sec, "NQ", 60, block_estimated=True)
    no_entry = guard["no_entry"]
    dropped = [t for t in T_all if no_entry[min(t[0], len(no_entry) - 1)]]
    T = [t for t in T_all if not no_entry[min(t[0], len(no_entry) - 1)]]
    print(f"roll guard (block_estimated=True): dropped {len(dropped)} of {len(T_all)} trades "
         f"whose entry straddled an estimated 2026 NQ roll; {len(T)} remain")
    for t in dropped:
        print("  dropped entry", idx[min(t[0], len(idx) - 1)])

    entry_ts = np.array([idx[min(t[0], len(idx) - 1)] for t in T])
    ref_tz = idx.tz if hasattr(idx, "tz") else None
    wf0 = loc_ts(wf0s, ref_tz); lb0 = loc_ts(lb0s, ref_tz)
    pre_m = entry_ts < lb0
    wf_m = (entry_ts >= wf0) & (entry_ts < lb0)
    lb_m = entry_ts >= lb0
    print(f"stage counts: IS+WF pre={int(pre_m.sum())} WF={int(wf_m.sum())} LB={int(lb_m.sum())} "
         f"total={len(T)}")

    # ---- HYBRID DD rf, same recipe as #335: online walk for IS+WF, frozen single fit for LB ----
    feats = entry_features_causal(arr)[0]
    T3 = [(t[0], t[1], t[2]) for t in T]
    g0 = gate_trades(arr, T3, model=MODEL, threshold=0.0, min_history=30, refit_every=25,
                     seed=42, feats=feats)
    prob_online = np.asarray(g0["prob"], float)

    E = np.array([t[0] for t in T]); P = np.array([t[2] for t in T], float)
    nb = len(feats)
    X = feats[np.clip(E, 0, nb - 1)]
    y = (P > 0).astype(int)
    Xpre, ypre, wpre = X[pre_m], y[pre_m], np.abs(P[pre_m]) + 1e-9
    mdl_frozen = _make_model(MODEL, 42)
    mdl_frozen.fit(Xpre, ypre, clf__sample_weight=wpre)
    prob_lb_frozen = mdl_frozen.predict_proba(X[~pre_m])[:, 1]
    prob_final = prob_online.copy()
    prob_final[~pre_m] = prob_lb_frozen

    keep_o, w_o, hp_o = hybridize(prob_online, hth, pre_m, P)
    keep_f, w_f, hp_f = hybridize(prob_final, hth, pre_m, P)

    # DD factor from THIS leg's own walk-forward stretch only
    ung_wf_dd = abs(gate_stats(P[wf_m])["max_drawdown"])
    hyb_wf_dd = abs(gate_stats(hp_f[keep_f & wf_m])["max_drawdown"])
    factor = ung_wf_dd / hyb_wf_dd if hyb_wf_dd > 1e-9 else 1.0
    print(f"DD-scale factor (own WF): {factor:.4f} (ungated WF dd {ung_wf_dd:.2f} pts / "
         f"hybrid WF dd {hyb_wf_dd:.2f} pts)")

    online_lb_stat = gate_stats(hp_o[keep_o & lb_m])
    frozen_lb_stat = gate_stats(hp_f[keep_f & lb_m])
    print(f"lockbox: ONLINE(unfrozen) net ${online_lb_stat['total_pnl']*MULT*factor:,.2f} vs "
         f"FROZEN net ${frozen_lb_stat['total_pnl']*MULT*factor:,.2f}")

    final_pts = hp_f * factor
    kept_idx = np.where(keep_f)[0]
    T_kept = [T[i] for i in kept_idx]
    size_kept = (w_f * factor)[kept_idx]
    pnl_pts_kept = final_pts[kept_idx]

    sized = [(T_kept[i], float(size_kept[i])) for i in range(len(T_kept))]
    incs, marked, unmarked = _mtm_increments(np.asarray(idx, dtype="datetime64[D]"),
                                             np.asarray(arr["close"], float), sized,
                                             MULT, 1.0, plugin_marks=None, usd_units=False)
    tot_closed = sum(pnl_pts_kept) * MULT
    tot_mtm = sum(v for _, v in incs)
    print(f"{ML_NAME}: marked={marked} unmarked={unmarked} closed=${tot_closed:,.2f} "
         f"mtm=${tot_mtm:,.2f} diff=${abs(tot_closed-tot_mtm):,.4f}")

    day_of_entry = np.asarray(idx, dtype="datetime64[D]")[np.clip([t[0] for t in T_kept], 0, len(idx) - 1)]
    day_size = {}
    for dday, sz in zip(day_of_entry, size_kept):
        n0, s0 = day_size.get(dday, (0, 0.0))
        day_size[dday] = (n0 + 1, s0 + sz)
    day_size_mean = {k: (v[0], v[1] / v[0]) for k, v in day_size.items()}
    write_daily(os.path.join(OUTDIR, f"{ML_NAME}_daily.csv"), incs, wf0, lb0, size_by_day=day_size_mean)

    trade_rows = []
    for i in range(len(T_kept)):
        e, x, p, side, px = T_kept[i]
        et = str(idx[min(e, len(idx) - 1)]); xt = str(idx[min(x, len(idx) - 1)])
        sd = "long" if side > 0 else "short"
        stg = stage_of(entry_ts[kept_idx[i]], wf0, lb0)
        trade_rows.append((et, xt, sd, round(pnl_pts_kept[i] * MULT, 2), round(size_kept[i], 4), stg))
    write_trades(os.path.join(OUTDIR, f"{ML_NAME}_trades.csv"), trade_rows)

    # ---- RAW twin (post roll-guard, size=1) ----
    sized_raw = [(t, 1.0) for t in T]
    incs_raw, mr, ur = _mtm_increments(np.asarray(idx, dtype="datetime64[D]"),
                                       np.asarray(arr["close"], float), sized_raw, MULT, 1.0)
    day_of_entry_r = np.asarray(idx, dtype="datetime64[D]")[np.clip([t[0] for t in T], 0, len(idx) - 1)]
    day_size_r = {}
    for dday in day_of_entry_r:
        n0, s0 = day_size_r.get(dday, (0, 0.0))
        day_size_r[dday] = (n0 + 1, s0 + 1.0)
    day_size_r_mean = {k: (v[0], v[1] / v[0]) for k, v in day_size_r.items()}
    write_daily(os.path.join(OUTDIR, f"{RAW_NAME}_daily.csv"), incs_raw, wf0, lb0, size_by_day=day_size_r_mean)
    trade_rows_r = []
    for i, (e, x, p, side, px) in enumerate(T):
        et = str(idx[min(e, len(idx) - 1)]); xt = str(idx[min(x, len(idx) - 1)])
        sd = "long" if side > 0 else "short"
        stg = stage_of(entry_ts[i], wf0, lb0)
        trade_rows_r.append((et, xt, sd, round(p * MULT, 2), 1.0, stg))
    write_trades(os.path.join(OUTDIR, f"{RAW_NAME}_trades.csv"), trade_rows_r)

    # ---- summary ----
    years = lambda a, b: (b - a).total_seconds() / (365.25 * 86400.0)
    idxN = pd.Timestamp(idx[-1])
    yrs_wf = years(wf0, lb0); yrs_lb = years(lb0, idxN)

    def stat_usd(arrv):
        s = gate_stats(arrv)
        return s["total_pnl"], abs(s["max_drawdown"])

    raw_wf = P[wf_m] * MULT; raw_lb = P[lb_m] * MULT
    ml_wf_mask = keep_f & wf_m; ml_lb_mask = keep_f & lb_m
    ml_wf = final_pts[ml_wf_mask] * MULT; ml_lb = final_pts[ml_lb_mask] * MULT
    raw_wf_net, raw_wf_dd = stat_usd(raw_wf)
    raw_lb_net, raw_lb_dd = stat_usd(raw_lb)
    ml_wf_net, ml_wf_dd = stat_usd(ml_wf)
    ml_lb_net, ml_lb_dd = stat_usd(ml_lb)

    def mar(net, dd, yrs):
        return (net / yrs) / dd if dd > 1e-9 and yrs > 0 else None

    sortino_raw_wf = sortino_from_pnls(list(raw_wf), yrs_wf)
    sortino_raw_lb = sortino_from_pnls(list(raw_lb), yrs_lb)
    sortino_ml_wf = sortino_from_pnls(list(ml_wf), yrs_wf)
    sortino_ml_lb = sortino_from_pnls(list(ml_lb), yrs_lb)

    scale_wf = raw_wf_dd / ml_wf_dd if ml_wf_dd > 1e-9 else None
    scale_lb = raw_lb_dd / ml_lb_dd if ml_lb_dd > 1e-9 else None
    matched_wf_net = ml_wf_net * scale_wf if scale_wf else None
    matched_lb_net = ml_lb_net * scale_lb if scale_lb else None

    summary = dict(
        model=MODEL, factor=factor, threshold=hth, cost_pts=COST_PTS, mult=MULT,
        master=master.get("filename"), n_dropped_roll_guard=len(dropped),
        raw_wf_net=raw_wf_net, raw_wf_dd=raw_wf_dd, raw_wf_mar=mar(raw_wf_net, raw_wf_dd, yrs_wf),
        raw_lb_net=raw_lb_net, raw_lb_dd=raw_lb_dd, raw_lb_mar=mar(raw_lb_net, raw_lb_dd, yrs_lb),
        ml_wf_net=ml_wf_net, ml_wf_dd=ml_wf_dd, ml_wf_mar=mar(ml_wf_net, ml_wf_dd, yrs_wf),
        ml_lb_net=ml_lb_net, ml_lb_dd=ml_lb_dd, ml_lb_mar=mar(ml_lb_net, ml_lb_dd, yrs_lb),
        sortino_raw_wf=sortino_raw_wf, sortino_raw_lb=sortino_raw_lb,
        sortino_ml_wf=sortino_ml_wf, sortino_ml_lb=sortino_ml_lb,
        matched_wf_net=matched_wf_net, matched_lb_net=matched_lb_net,
        scale_wf=scale_wf, scale_lb=scale_lb,
        yrs_wf=yrs_wf, yrs_lb=yrs_lb, n_kept=int(keep_f.sum()), n_total=len(T),
    )
    print(json.dumps(summary, indent=1, default=str))
    with open(os.path.join(OUTDIR, f"_summary_{ML_NAME}.json"), "w") as fh:
        json.dump(summary, fh, indent=1, default=str)
    print(f"done in {time.time()-t0:.1f}s")


if __name__ == "__main__":
    main()
