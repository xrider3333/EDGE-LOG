import sys, os, json, time
import numpy as np
import pandas as pd
sys.path.insert(0, r"C:\Users\xride\AppData\Local\Temp\claude\C--Users-xride-OneDrive-Desktop\cf70e01e-1bab-4445-b5e2-10d6db1f8d89\scratchpad\book_legs_ml")
from common import load_run, get_arrays, raw_trades, entry_ts_of, slice_stats, check_block, OUTDIR
from augur_engine import ml_keel
from augur_engine.ml_gate import _stats as gate_stats
from augur_engine.book import _mtm_increments
from augur_engine.analytics import sortino_from_pnls

RID = 368
VERSION = "v12"
RAW_NAME = "TTM368_raw"
ML_NAME = "TTM368_keel"


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
        ts = pd.Timestamp(d)          # days_idx from _mtm_increments is tz-naive
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


def main():
    t0 = time.time()
    d = load_run(RID)
    arr, _ = get_arrays(d)
    T, res = raw_trades(d, arr)
    mult = float(d["multiplier"])
    gv = d["gate_validate"]
    wf0s, wf1s = gv["wf_range"]
    lb0s = gv["lockbox_from"]
    idx = arr["index"]
    ref_tz = idx.tz if hasattr(idx, "tz") else None
    wf0 = loc_ts(wf0s, ref_tz); lb0 = loc_ts(lb0s, ref_tz)
    entry_ts = entry_ts_of(arr, T)
    pre_m = entry_ts < lb0
    wf_m = (entry_ts >= wf0) & (entry_ts < lb0)
    lb_m = entry_ts >= lb0

    feats_keel = ml_keel.keel_features(arr)
    T3 = [(t[0], t[1], t[2]) for t in T]
    T_pre = [t for t, m in zip(T3, pre_m) if m]
    T_lb = [t for t, m in zip(T3, pre_m) if not m]
    print(f"#{RID}: {len(T3)} trades total, {len(T_pre)} pre-lockbox, {len(T_lb)} lockbox")

    # ---- REPRODUCTION CHECK: standard online keel_walk over the whole series should
    # match the stored (unfrozen) gate_validate.keel block (rule a). ----
    kw_full = ml_keel.keel_walk(arr, T3, feats=feats_keel, seed=42, version=VERSION)
    P = kw_full["P"]; sizes_online = kw_full["size"]
    hp_online = P * sizes_online
    for nm, mask, stored_key in (("pre", pre_m, "pre"), ("wf_rng", wf_m, "wf_rng"),
                                 ("lockbox", lb_m, "lockbox"), ("full", np.ones(len(P), bool), "full")):
        rep = gate_stats(hp_online[mask])
        ok, msg = check_block(f"keel.{nm}", rep, gv["keel"][stored_key])
        print(("OK  " if ok else "FAIL"), msg)

    # ---- FREEZE (rule b): build the KEEL state on PRE-LOCKBOX trades only, score
    # every lockbox trade with that frozen state (no further refits inside lockbox). ----
    state = ml_keel.keel_build_state(arr, T_pre, feats=feats_keel, seed=42, version=VERSION)
    kw_pre = ml_keel.keel_walk(arr, T_pre, feats=feats_keel, seed=42, version=VERSION)
    sizes_pre = kw_pre["size"]     # aligned with T_pre / T[pre_m], both entry-sorted
    sizes_lb = []
    for t in T_lb:
        sz, diag = ml_keel.keel_score_from_state(state, arr, entry_bar=t[0], feats=feats_keel,
                                                 cross_series=False)
        sizes_lb.append(sz)
    sizes_lb = np.array(sizes_lb, float)
    sizes_final = np.concatenate([sizes_pre, sizes_lb])
    assert len(sizes_final) == len(T)
    pnl_final_pts = P * sizes_final

    pre_stat_check = gate_stats(pnl_final_pts[pre_m])
    ok, msg = check_block("keel.pre (frozen path, should equal online pre)", pre_stat_check, gv["keel"]["pre"])
    print(("OK  " if ok else "FAIL"), msg)
    print(f"KEEL lockbox: ONLINE(unfrozen) net ${hp_online[lb_m].sum()*mult:,.2f} "
         f"vs FROZEN net ${pnl_final_pts[lb_m].sum()*mult:,.2f} "
         f"(stored doc reads ${gv['keel']['lockbox']['total_pnl']*mult:,.2f} online)")

    # ---- write CSVs: KEEL leg (frozen at lockbox) ----
    sized = [(T[i], float(sizes_final[i])) for i in range(len(T))]
    incs, marked, unmarked = _mtm_increments(np.asarray(idx, dtype="datetime64[D]"),
                                             np.asarray(arr["close"], float), sized,
                                             mult, 1.0, plugin_marks=None, usd_units=False)
    tot_closed = sum(pnl_final_pts) * mult
    tot_mtm = sum(v for _, v in incs)
    print(f"KEEL mtm: marked={marked} unmarked={unmarked} closed=${tot_closed:,.2f} mtm=${tot_mtm:,.2f} "
         f"diff=${abs(tot_closed-tot_mtm):,.4f}")

    day_of_entry = np.asarray(idx, dtype="datetime64[D]")[np.clip([t[0] for t in T], 0, len(idx) - 1)]
    day_size = {}
    for dday, sz in zip(day_of_entry, sizes_final):
        n0, s0 = day_size.get(dday, (0, 0.0))
        day_size[dday] = (n0 + 1, s0 + sz)
    day_size_mean = {k: (v[0], v[1] / v[0]) for k, v in day_size.items()}
    write_daily(os.path.join(OUTDIR, f"{ML_NAME}_daily.csv"), incs, wf0, lb0, size_by_day=day_size_mean)

    trade_rows = []
    for i, (e, x, p, side, px) in enumerate(T):
        et = str(idx[min(e, len(idx) - 1)]); xt = str(idx[min(x, len(idx) - 1)])
        sd = "long" if side > 0 else "short"
        stg = stage_of(entry_ts[i], wf0, lb0)
        trade_rows.append((et, xt, sd, round(pnl_final_pts[i] * mult, 2), round(sizes_final[i], 4), stg))
    write_trades(os.path.join(OUTDIR, f"{ML_NAME}_trades.csv"), trade_rows)

    # ---- RAW twin ----
    sized_raw = [(t, 1.0) for t in T]
    incs_raw, mr, ur = _mtm_increments(np.asarray(idx, dtype="datetime64[D]"),
                                       np.asarray(arr["close"], float), sized_raw, mult, 1.0)
    day_size_r = {}
    for dday in day_of_entry:
        n0, s0 = day_size_r.get(dday, (0, 0.0))
        day_size_r[dday] = (n0 + 1, s0 + 1.0)
    day_size_r_mean = {k: (v[0], v[1] / v[0]) for k, v in day_size_r.items()}
    write_daily(os.path.join(OUTDIR, f"{RAW_NAME}_daily.csv"), incs_raw, wf0, lb0, size_by_day=day_size_r_mean)
    trade_rows_r = []
    P_raw = np.array([t[2] for t in T], float)
    for i, (e, x, p, side, px) in enumerate(T):
        et = str(idx[min(e, len(idx) - 1)]); xt = str(idx[min(x, len(idx) - 1)])
        sd = "long" if side > 0 else "short"
        stg = stage_of(entry_ts[i], wf0, lb0)
        trade_rows_r.append((et, xt, sd, round(p * mult, 2), 1.0, stg))
    write_trades(os.path.join(OUTDIR, f"{RAW_NAME}_trades.csv"), trade_rows_r)

    # ---- summary ----
    years = lambda a, b: (b - a).total_seconds() / (365.25 * 86400.0)
    idxN = pd.Timestamp(idx[-1])
    yrs_wf = years(wf0, lb0); yrs_lb = years(lb0, idxN)

    def stat_usd(arrv):
        s = gate_stats(arrv)
        return s["total_pnl"], abs(s["max_drawdown"])

    raw_wf = P_raw[wf_m] * mult; raw_lb = P_raw[lb_m] * mult
    ml_wf = pnl_final_pts[wf_m] * mult; ml_lb = pnl_final_pts[lb_m] * mult
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
        rid=RID, model="keel", version=VERSION,
        raw_wf_net=raw_wf_net, raw_wf_dd=raw_wf_dd, raw_wf_mar=mar(raw_wf_net, raw_wf_dd, yrs_wf),
        raw_lb_net=raw_lb_net, raw_lb_dd=raw_lb_dd, raw_lb_mar=mar(raw_lb_net, raw_lb_dd, yrs_lb),
        ml_wf_net=ml_wf_net, ml_wf_dd=ml_wf_dd, ml_wf_mar=mar(ml_wf_net, ml_wf_dd, yrs_wf),
        ml_lb_net=ml_lb_net, ml_lb_dd=ml_lb_dd, ml_lb_mar=mar(ml_lb_net, ml_lb_dd, yrs_lb),
        sortino_raw_wf=sortino_raw_wf, sortino_raw_lb=sortino_raw_lb,
        sortino_ml_wf=sortino_ml_wf, sortino_ml_lb=sortino_ml_lb,
        matched_wf_net=matched_wf_net, matched_lb_net=matched_lb_net,
        scale_wf=scale_wf, scale_lb=scale_lb,
        yrs_wf=yrs_wf, yrs_lb=yrs_lb,
        online_lb_net_usd=hp_online[lb_m].sum() * mult,
        frozen_lb_net_usd=pnl_final_pts[lb_m].sum() * mult,
        n_total=len(T),
    )
    print(json.dumps(summary, indent=1, default=str))
    with open(os.path.join(OUTDIR, f"_summary_{ML_NAME}.json"), "w") as fh:
        json.dump(summary, fh, indent=1, default=str)
    print(f"done in {time.time()-t0:.1f}s")


if __name__ == "__main__":
    main()
