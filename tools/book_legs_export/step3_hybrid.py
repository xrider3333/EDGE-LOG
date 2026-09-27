import sys, os, json, time
import numpy as np
import pandas as pd
sys.path.insert(0, r"C:\Users\xride\AppData\Local\Temp\claude\C--Users-xride-OneDrive-Desktop\cf70e01e-1bab-4445-b5e2-10d6db1f8d89\scratchpad\book_legs_ml")
from common import load_run, get_arrays, raw_trades, entry_ts_of, slice_stats, check_block, OUTDIR
from augur_engine.ml_gate import entry_features_causal, gate_trades, _stats as gate_stats, _make_model
from augur_engine.book import _mtm_increments
from augur_engine.analytics import sortino_from_pnls

LEGS = {
    314: dict(model="tree", raw_name="ORB314_raw", ml_name="ORB314_hybdd_tree"),
    335: dict(model="rf", raw_name="ENGUQ335_raw", ml_name="ENGUQ335_hybdd_rf"),
}


def loc_ts(t, ref_tz):
    if t is None:
        return None
    ts = pd.Timestamp(t)
    if ts.tzinfo is None and ref_tz is not None:
        ts = ts.tz_localize(ref_tz)
    return ts


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


def stage_of(ts, wf0, lb0):
    if ts < wf0:
        return "IS"
    if ts < lb0:
        return "WF"
    return "LB"


def write_daily(path, incs, wf0, lb0, size_by_day=None):
    """incs: [(day(np.datetime64[D]), usd)]"""
    if not incs:
        with open(path, "w") as fh:
            fh.write("date,pnl_usd,trades,size,stage\n")
        return
    days, p = {}, {}
    for d, v in incs:
        days[d] = days.get(d, 0.0) + v
    wf0n = pd.Timestamp(wf0).tz_localize(None) if wf0.tzinfo else wf0
    lb0n = pd.Timestamp(lb0).tz_localize(None) if lb0.tzinfo else lb0
    rows = []
    for d in sorted(days.keys()):
        ts = pd.Timestamp(d)          # days_idx from _mtm_increments is tz-naive
        stg = stage_of(ts, wf0n, lb0n)
        n_tr, sz = (size_by_day.get(d, (0, None)) if size_by_day else (0, None))
        rows.append((str(pd.Timestamp(d).date()), round(days[d], 2), n_tr,
                    ("" if sz is None else round(sz, 4)), stg))
    with open(path, "w") as fh:
        fh.write("date,pnl_usd,trades,size,stage\n")
        for r in rows:
            fh.write(",".join(str(x) for x in r) + "\n")
    return rows


def write_trades(path, rows):
    with open(path, "w") as fh:
        fh.write("entry_time,exit_time,side,pnl_usd,size,stage\n")
        for r in rows:
            fh.write(",".join(str(x) for x in r) + "\n")


def build_leg(rid, model, raw_name, ml_name):
    t0 = time.time()
    d = load_run(rid)
    arr, _ = get_arrays(d)
    T, res = raw_trades(d, arr)   # 5-tuples (E,X,P,side,entry_px), sorted by entry
    mult = float(d["multiplier"])
    gv = d["gate_validate"]
    wf0s, lb1s = gv["wf_range"]
    lb0s = gv["lockbox_from"]
    idx = arr["index"]
    ref_tz = idx.tz if hasattr(idx, "tz") else None
    wf0 = loc_ts(wf0s, ref_tz); lb0 = loc_ts(lb0s, ref_tz)
    entry_ts = entry_ts_of(arr, T)
    pre_m = entry_ts < lb0
    wf_m = (entry_ts >= wf0) & (entry_ts < lb0)
    lb_m = entry_ts >= lb0

    feats = entry_features_causal(arr)[0]
    T3 = [(t[0], t[1], t[2]) for t in T]
    g0 = gate_trades(arr, T3, model=model, threshold=0.0, min_history=30, refit_every=25,
                     seed=42, feats=feats)
    prob_online = np.asarray(g0["prob"], float)

    # ---- FREEZE (rule b): fit ONE model on pre-lockbox trades only, score every
    # lockbox trade with it (no further refits inside the lockbox).
    E = np.array([t[0] for t in T]); P = np.array([t[2] for t in T], float)
    nb = len(feats)
    X = feats[np.clip(E, 0, nb - 1)]
    y = (P > 0).astype(int)
    Xpre, ypre, wpre = X[pre_m], y[pre_m], np.abs(P[pre_m]) + 1e-9
    mdl = _make_model(model, 42)
    mdl.fit(Xpre, ypre, clf__sample_weight=wpre)
    prob_lb_frozen = mdl.predict_proba(X[~pre_m])[:, 1]
    prob_final = prob_online.copy()
    prob_final[~pre_m] = prob_lb_frozen

    hth = float(gv["chosen"]["threshold"])
    keep_o, w_o, hp_o = hybridize(prob_online, hth, pre_m, P)
    keep_f, w_f, hp_f = hybridize(prob_final, hth, pre_m, P)

    # cross-check vs stored hybrid row (pre-lockbox / WF unaffected by the freeze)
    hs = next(h for h in gv["hybrids"] if h["model"] == model)
    pre_stat = gate_stats(hp_f[keep_f & pre_m])
    ok, msg = check_block(f"{ml_name}.pre (frozen, should match stored pre)", pre_stat, hs["pre"])
    print(msg)

    # ---- DD-scale factor from the WALK-FORWARD stretch only (knowable pre-lockbox) ----
    ung_wf_stat = gate_stats(P[wf_m])
    hyb_wf_stat = gate_stats(hp_f[keep_f & wf_m])
    ung_wf_dd = abs(ung_wf_stat["max_drawdown"])
    hyb_wf_dd = abs(hyb_wf_stat["max_drawdown"])
    factor = ung_wf_dd / hyb_wf_dd if hyb_wf_dd > 1e-9 else 1.0
    print(f"#{rid} {model}: DD-scale factor (WF-derived) = {factor:.4f} "
         f"(ungated WF dd {ung_wf_dd:.2f} pts / hybrid WF dd {hyb_wf_dd:.2f} pts)")

    final_pts = hp_f * factor  # only meaningful where keep_f True

    # ---- build kept-trade record list (5-tuple + scaled pnl_usd + size) ----
    kept_idx = np.where(keep_f)[0]
    T_kept = [T[i] for i in kept_idx]
    size_kept = (w_f * factor)[kept_idx]
    pnl_pts_kept = final_pts[kept_idx]
    ts_kept = entry_ts[kept_idx]

    sized = [(T_kept[i], float(size_kept[i])) for i in range(len(T_kept))]
    incs, marked, unmarked = _mtm_increments(np.asarray(idx, dtype="datetime64[D]"),
                                             np.asarray(arr["close"], float), sized,
                                             mult, 1.0, plugin_marks=None, usd_units=False)
    tot_closed = sum(pnl_pts_kept) * mult
    tot_mtm = sum(v for _, v in incs)
    print(f"#{rid} {ml_name}: marked={marked} unmarked={unmarked} closed_total=${tot_closed:,.2f} "
         f"mtm_total=${tot_mtm:,.2f} diff=${abs(tot_closed-tot_mtm):,.4f}")

    # size-by-day (mean size of entries that day) for the ML leg + trade count
    day_of_entry = np.asarray(idx, dtype="datetime64[D]")[np.clip([t[0] for t in T_kept], 0, len(idx) - 1)]
    day_size = {}
    for dday, sz in zip(day_of_entry, size_kept):
        n0, s0 = day_size.get(dday, (0, 0.0))
        day_size[dday] = (n0 + 1, s0 + sz)
    day_size_mean = {k: (v[0], v[1] / v[0]) for k, v in day_size.items()}

    write_daily(os.path.join(OUTDIR, f"{ml_name}_daily.csv"), incs, wf0, lb0, size_by_day=day_size_mean)

    trade_rows = []
    for i in range(len(T_kept)):
        e, x, p, side, px = T_kept[i]
        et = str(idx[min(e, len(idx) - 1)])
        xt = str(idx[min(x, len(idx) - 1)])
        sd = "long" if side > 0 else "short"
        stg = stage_of(loc_ts(entry_ts[kept_idx[i]], ref_tz), wf0, lb0)
        trade_rows.append((et, xt, sd, round(pnl_pts_kept[i] * mult, 2), round(size_kept[i], 4), stg))
    write_trades(os.path.join(OUTDIR, f"{ml_name}_trades.csv"), trade_rows)

    # ---- RAW twin (size=1, same mtm machinery) ----
    sized_raw = [(t, 1.0) for t in T]
    incs_raw, marked_r, unmarked_r = _mtm_increments(np.asarray(idx, dtype="datetime64[D]"),
                                                      np.asarray(arr["close"], float), sized_raw,
                                                      mult, 1.0, plugin_marks=None, usd_units=False)
    day_of_entry_r = np.asarray(idx, dtype="datetime64[D]")[np.clip([t[0] for t in T], 0, len(idx) - 1)]
    day_size_r = {}
    for dday in day_of_entry_r:
        n0, s0 = day_size_r.get(dday, (0, 0.0))
        day_size_r[dday] = (n0 + 1, s0 + 1.0)
    day_size_r_mean = {k: (v[0], v[1] / v[0]) for k, v in day_size_r.items()}
    write_daily(os.path.join(OUTDIR, f"{raw_name}_daily.csv"), incs_raw, wf0, lb0, size_by_day=day_size_r_mean)
    trade_rows_r = []
    for i, (e, x, p, side, px) in enumerate(T):
        et = str(idx[min(e, len(idx) - 1)]); xt = str(idx[min(x, len(idx) - 1)])
        sd = "long" if side > 0 else "short"
        stg = stage_of(loc_ts(entry_ts[i], ref_tz), wf0, lb0)
        trade_rows_r.append((et, xt, sd, round(p * mult, 2), 1.0, stg))
    write_trades(os.path.join(OUTDIR, f"{raw_name}_trades.csv"), trade_rows_r)

    # ---- summary numbers for the README ----
    years = lambda a, b: (b - a).total_seconds() / (365.25 * 86400.0)
    idx0 = pd.Timestamp(entry_ts.min()); idxN = pd.Timestamp(idx[-1])
    yrs_wf = years(wf0, lb0); yrs_lb = years(lb0, idxN)

    def blk(mask, pts_or_usd, is_usd):
        s = pts_or_usd[mask]
        gwl = gate_stats(s if not is_usd else s)  # gate_stats works fine on $ too (scale-free)
        return s, gwl

    raw_wf = P[wf_m] * mult; raw_lb = P[lb_m] * mult
    ml_wf_mask = keep_f & wf_m; ml_lb_mask = keep_f & lb_m
    ml_wf = final_pts[ml_wf_mask] * mult; ml_lb = final_pts[ml_lb_mask] * mult

    def stat_usd(arrv):
        s = gate_stats(arrv)
        return s["total_pnl"], abs(s["max_drawdown"])

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

    # ML at matched drawdown (per-stretch OWN ratio, independent of the export's own DD factor)
    scale_wf = raw_wf_dd / ml_wf_dd if ml_wf_dd > 1e-9 else None
    scale_lb = raw_lb_dd / ml_lb_dd if ml_lb_dd > 1e-9 else None
    matched_wf_net = ml_wf_net * scale_wf if scale_wf else None
    matched_lb_net = ml_lb_net * scale_lb if scale_lb else None

    summary = dict(
        rid=rid, model=model, factor=factor,
        raw_wf_net=raw_wf_net, raw_wf_dd=raw_wf_dd, raw_wf_mar=mar(raw_wf_net, raw_wf_dd, yrs_wf),
        raw_lb_net=raw_lb_net, raw_lb_dd=raw_lb_dd, raw_lb_mar=mar(raw_lb_net, raw_lb_dd, yrs_lb),
        ml_wf_net=ml_wf_net, ml_wf_dd=ml_wf_dd, ml_wf_mar=mar(ml_wf_net, ml_wf_dd, yrs_wf),
        ml_lb_net=ml_lb_net, ml_lb_dd=ml_lb_dd, ml_lb_mar=mar(ml_lb_net, ml_lb_dd, yrs_lb),
        sortino_raw_wf=sortino_raw_wf, sortino_raw_lb=sortino_raw_lb,
        sortino_ml_wf=sortino_ml_wf, sortino_ml_lb=sortino_ml_lb,
        matched_wf_net=matched_wf_net, matched_lb_net=matched_lb_net,
        scale_wf=scale_wf, scale_lb=scale_lb,
        yrs_wf=yrs_wf, yrs_lb=yrs_lb,
        n_kept=int(keep_f.sum()), n_total=len(T),
    )
    print(json.dumps(summary, indent=1, default=str))
    with open(os.path.join(OUTDIR, f"_summary_{ml_name}.json"), "w") as fh:
        json.dump(summary, fh, indent=1, default=str)
    print(f"#{rid} done in {time.time()-t0:.1f}s")


if __name__ == "__main__":
    only = sys.argv[1:] and [int(x) for x in sys.argv[1:]] or list(LEGS.keys())
    for rid in only:
        cfg = LEGS[rid]
        build_leg(rid, cfg["model"], cfg["raw_name"], cfg["ml_name"])
