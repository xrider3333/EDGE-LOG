"""Q38 HARM BANDS FOR THE WEBULL LEGS (MANAGER #141 item 3, #146 / #147) per bookq/PREDATA_Q38_WEBULL_BANDS.txt: ORB_R6, NOISE_382 and DIP_424F
as the box runs them (api/cloud_signal.py), on the QQQ 5m Alpaca master, PER SHARE at $0.02 a share a round trip, booked by exit day on QQQ RTH
sessions; bands on 2022-07-01..2025-06-29 by q35_recent_bands.calibrate (copied below, with A1 checked every 5th row = one RTH week); then the
forward read from the newest pull-job folder (C:\\EdgeLog\\box_backup, qqq_exec/trades.csv) - nothing connects to the box.
    python q38_webull_bands.py run [YYYY-MM-DD]"""
import datetime as dt
import glob
import hashlib
import json
import math
import os
import sys

REPO = r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"
BQ = r"C:\EdgeLog\_anatomy_cache\bookq"
NOTE = os.path.join(BQ, "PREDATA_Q38_WEBULL_BANDS.txt")
NOTE_SHA = "64b82b397eec23acb3ccd1555ccf71d4dce0f870ea33d485713947dfedb8b656"
ADD1 = os.path.join(BQ, "PREDATA_Q38_ADD1.txt")                     # POST-DATA bug fix (NOISE plugin size), disclosed
ADD1_SHA = "bf9f50fab07ece412c9c2a51f694b05d2f16758f5878951bdd76f85247a3e5fe"
QQQ5_SHA = "782dabdd7dd7d265c9a31626f03c6940cdaaf4d7511da95bf8a8efc41fba5a1d"
BOX = os.environ.get("EDGELOG_BOX_BACKUP", r"C:\EdgeLog\box_backup")
OUT = r"C:\EdgeLog\_anatomy_cache\q38"
W0, W1 = "2022-07-01", "2025-06-29"
COST_SH_RT = 0.02                                                       # $0.01 a side, qqq_exec slippage_per_share
UNIT = {"ORB_R6": 10, "NOISE_382": 10, "DIP_424F": 6}                  # shares per trade at size 1 (NOISE x its plugin size; DIP per lot)
EXEC_LEG = {"ORB_R6": "ORB", "NOISE_382": "NOISE", "DIP_424F": "DIP"}  # trades.csv leg column, for rows without a trade_id
START = {"ORB_R6": "2026-09-09", "NOISE_382": "2026-09-24", "DIP_424F": None}   # None = the leg's first trade
WEEK = 5                                                               # A1 checks: every 5th RTH session
SEED, PATHS, BLOCK = 20261009, 2000, 20
HOL_2026 = {"2026-01-01", "2026-01-19", "2026-02-16", "2026-04-03", "2026-05-25", "2026-06-19", "2026-07-03", "2026-09-07", "2026-11-26",
            "2026-12-25"}                                              # NYSE full closes
lf = lambda p: hashlib.sha256(open(p, "rb").read().replace(b"\r\n", b"\n")).hexdigest()
sha = lambda p: hashlib.sha256(open(p, "rb").read()).hexdigest()


def calibrate(x, H, checks, np, stationary_indices):
    """q35_recent_bands.calibrate, verbatim but for H / checks passed in"""
    mu, sd = float(x.mean()), float(x.std(ddof=1))
    idx = stationary_indices(len(x), PATHS, BLOCK, np.random.default_rng(SEED))
    reps = int(np.ceil(H / idx.shape[1]))
    I = np.concatenate([idx] * reps, axis=1)[:, :H] if idx.shape[1] < H else idx[:, :H]
    P = x[I]
    S = np.cumsum(P - mu, axis=1)[:, checks - 1]
    c = float(-np.quantile((S / (sd * np.sqrt(checks))).min(axis=1), 0.025))
    q = np.cumsum(P, axis=1)
    dd = (np.maximum.accumulate(np.concatenate([np.zeros((P.shape[0], 1)), q], axis=1), axis=1)[:, 1:] - q).max(axis=1)
    Dl = float(np.quantile(dd, 0.975))
    Q = P - mu
    Sz = np.cumsum(Q - mu, axis=1)[:, checks - 1] / (sd * np.sqrt(checks))
    t1 = np.where((Sz < -c).any(axis=1), checks[np.argmax(Sz < -c, axis=1)], np.inf)
    qz = np.cumsum(Q, axis=1)
    ddz = (np.maximum.accumulate(np.concatenate([np.zeros((Q.shape[0], 1)), qz], axis=1), axis=1)[:, 1:] - qz)[:, checks - 1]
    t2 = np.where((ddz > Dl).any(axis=1), checks[np.argmax(ddz > Dl, axis=1)], np.inf)
    power = float((np.minimum(t1, t2) <= H).mean())
    return {"mu": mu, "sd": sd, "c": c, "dd_alarm": Dl, "big": None, "big_per_year": None}, power


def evaluate(x, band, np):
    """harm_monitor.evaluate's A1 / A2 core with A1 checked every WEEK rows"""
    x = np.asarray(x, float)
    n = len(x)
    if n == 0:
        return {"days": 0, "net": 0.0, "a1": False, "a2": False, "a1_z": None, "a1_worst_z": None, "dd": 0.0, "dd_max": 0.0, "checks": 0}
    s = np.cumsum(x - band["mu"])
    chk = np.arange(WEEK, n + 1, WEEK)
    z = s[chk - 1] / (band["sd"] * np.sqrt(chk))
    q = np.cumsum(x)
    dd = np.maximum.accumulate(np.concatenate([[0.0], q]))[1:] - q
    return {"days": n, "net": float(x.sum()), "a1": bool((z < -band["c"]).any()), "a2": bool((dd > band["dd_alarm"]).any()),
            "a1_z": float(s[-1] / (band["sd"] * math.sqrt(n))), "a1_worst_z": float(z.min()) if len(z) else None, "checks": int(len(z)),
            "dd": float(dd[-1]), "dd_max": float(dd.max()), "expected_net": float(band["mu"] * n)}


def unit_trades(name, leg, arr, run_backtest, np):
    """-> list of (exit_day, unit $) for every engine trade, gross from the engine, then $0.02 a share a round trip"""
    import pandas as pd
    p = dict(leg["params"])
    if name == "DIP_424F":
        p["cost_bps"] = 0.0
    r = run_backtest(leg["strategy"], arrays=arr, params=p, cost_pts=0.0, return_trades=True)
    tr = r["trades"]
    ix = pd.DatetimeIndex(arr["index"])
    ix = ix.tz_convert("America/New_York").tz_localize(None) if ix.tz is not None else ix
    sizes = r.get("trade_sizes")
    out, chk = [], []
    for i, t in enumerate(tr):
        t0, t1, pts = int(t[0]), int(t[1]), float(t[2])
        if name == "ORB_R6":
            sh, raw = UNIT[name], pts
        elif name == "NOISE_382":
            s = float(sizes[i]) if sizes is not None else 1.0
            sh, raw = UNIT[name] * s, (pts + (s - 1.0) * float(r.get("size_cost_pts") or 0.0)) / s
        else:
            px = float(t[4])
            chk.append(abs(px - float(arr["open"][t0])) / px if "open" in arr else float("nan"))
            sh, raw = UNIT[name], pts * px / float(p["notional"])
        out.append((ix[min(t1, len(ix) - 1)].normalize(), sh * (raw - COST_SH_RT)))
    if chk:
        print(f"   DIP entry price vs the entry bar's open: median rel. diff {float(np.nanmedian(chk)):.2e} (0 = filled at that open)", flush=True)
    if name == "NOISE_382" and sizes is not None:
        print(f"   NOISE plugin sizes: {dict(zip(*np.unique(np.asarray(sizes, float), return_counts=True)))}", flush=True)
    return out


def latest_folder(asof):
    best = None
    for p in sorted(glob.glob(os.path.join(BOX, "20??-??-??_????"))):
        stamp = dt.datetime.strptime(os.path.basename(p), "%Y-%m-%d_%H%M")
        if stamp.date() <= asof and os.path.exists(os.path.join(p, "qqq_exec", "trades.csv")):
            best = (p, stamp)
    return best


def sessions(d0, d1):
    import pandas as pd
    return [d for d in pd.bdate_range(d0, d1) if str(d.date()) not in HOL_2026]


def forward(asof, np):
    import pandas as pd
    f = latest_folder(asof)
    if f is None:
        return None, "no pull-job folder on or before %s" % asof
    path, stamp = f
    end = stamp.date() if stamp.time() >= dt.time(14, 30) else stamp.date() - dt.timedelta(days=1)   # 14:30 MST = 16:30 ET
    T = pd.read_csv(os.path.join(path, "qqq_exec", "trades.csv"))
    S = pd.read_csv(os.path.join(path, "cloud_signal", "signals.csv"))
    T["day"] = pd.to_datetime(T["exit_ts"]).dt.normalize()
    pre = T["trade_id"].fillna("").str.split("-").str[0]
    res = {"folder": os.path.basename(path), "end": str(end), "legs": {}}
    for name in UNIT:
        m = pre.eq(name)
        start = START[name] or (str(T.loc[m, "day"].min().date()) if m.any() else None)
        if start is None:
            res["legs"][name] = {"rows": 0, "note": "no trades yet"}
            continue
        loose = pre.eq("") & T["leg"].eq(EXEC_LEG[name]) & (T["day"] >= start)
        x = T[(m | loose) & (T["day"] >= start) & (T["day"] <= pd.Timestamp(end))].copy()
        if name == "NOISE_382":                                        # ADDENDUM 1: size = SENT size (plugin x KEEL) -> plugin = size / keel
            eng_k = S[(S["event"] == "ENTRY") & S["trade_id"].notna()].drop_duplicates("trade_id", keep="last").set_index("trade_id")["keel_size"]
            k = x["keel_size"].where(x["keel_size"].notna(), x["trade_id"].map(eng_k))
            no_keel = int(k.isna().sum())
            size = x["size"].fillna(1.0) / k.fillna(1.0)
        else:
            size, no_keel = 1.0, 0
        x["unit"] = x["pnl"] / x["shares"] * UNIT[name] * size
        cal = sessions(start, end)
        daily = x.groupby("day")["unit"].sum().reindex(cal).fillna(0.0)
        off = sorted(set(x["day"]) - set(cal))
        eng = S[(S["leg"] == name) & (S["event"] == "EXIT") & (pd.to_datetime(S["ref_time"], utc=True).dt.tz_convert("America/New_York")
                                                                 .dt.tz_localize(None).dt.normalize() >= start)]
        leg = {"start": start, "rows": int(len(daily)), "trades": int(len(x)), "no_trade_id": int(loose[x.index].sum()) if len(x) else 0,
               "engine_exits": int(len(eng)), "days_off_calendar": [str(d.date()) for d in off], "no_keel_size": no_keel, "series": daily}
        if name == "NOISE_382" and len(x):
            leg["keel_scale"] = float(x["pnl"].sum() / x["unit"].sum()) if abs(x["unit"].sum()) > 1e-9 else None
        res["legs"][name] = leg
    return res, None


def run(asof):
    sys.path.insert(0, REPO)
    sys.path.insert(0, os.path.join(REPO, "tools"))
    os.chdir(REPO)
    import numpy as np
    import pandas as pd
    from api import cloud_signal as cs
    from augur_engine.data import find_master, load_master_arrays
    from augur_engine.engine import run_backtest
    from power_line import stationary_indices
    qm = find_master("QQQ", "5m", "rth", "alpaca_split_rth")
    qpath = os.path.join(REPO, "augur_uploads", qm["filename"])
    pins = {"note": lf(NOTE), "qqq5m": sha(qpath)}
    print(f"PINS: note LF {pins['note']}; script LF {lf(__file__)}; QQQ 5m {qm['filename']} {pins['qqq5m']}", flush=True)
    pins["add1"] = lf(ADD1)
    print(f"PINS: addendum 1 LF {pins['add1']}", flush=True)
    if (pins["note"], pins["qqq5m"], pins["add1"]) != (NOTE_SHA, QQQ5_SHA, ADD1_SHA):
        raise SystemExit("refused: a pinned input is not the frozen one (nothing computed)")
    os.makedirs(OUT, exist_ok=True)
    legs = {"ORB_R6": cs.CROWN_LEGS["ORB_R6"], "NOISE_382": cs.CROWN_LEGS["NOISE_382"], "DIP_424F": cs.SHADOW_LEGS["DIP_424F"]}
    for k, v in legs.items():
        print(f"{k}: {v['strategy']} {v['timeframe']} params {v['params']}" + (f" keel {v.get('keel')}" if v.get("keel") else ""), flush=True)
    arr = load_master_arrays(qm)
    ix = pd.DatetimeIndex(arr["index"])
    ix = ix.tz_convert("America/New_York").tz_localize(None) if ix.tz is not None else ix
    cal = pd.DatetimeIndex(sorted(set(ix.normalize())))
    cal = cal[(cal >= W0) & (cal <= W1)]
    H = int(round(36 * len(cal) / ((pd.Timestamp(W1) - pd.Timestamp(W0)).days / 30.4375)))
    checks = np.arange(WEEK, H + 1, WEEK)
    yrs = (pd.Timestamp(W1) - pd.Timestamp(W0)).days / 365.25
    print(f"window {W0}..{W1}: {len(cal)} QQQ RTH sessions; 36 months = {H} rows; A1 checks every {WEEK} rows", flush=True)
    fw, why = forward(asof, np)
    print(f"forward: {why or ('folder ' + fw['folder'] + ', sessions through ' + fw['end'])}", flush=True)
    out = {"note_sha256_lf": pins["note"], "window": [W0, W1], "unit_shares": UNIT, "cost_per_share_rt": COST_SH_RT, "week_rows": WEEK,
           "H": H, "legs": {}}
    for name, leg in legs.items():
        tr = unit_trades(name, leg, arr, run_backtest, np)
        s = pd.Series([v for _, v in tr], index=pd.DatetimeIndex([d for d, _ in tr])).groupby(level=0).sum()
        x = s.reindex(cal).fillna(0.0).to_numpy(float)
        band, power = calibrate(x, H, checks, np, stationary_indices)
        if name == "ORB_R6":
            q = float(np.quantile(x, 0.99))
            band.update({"big": q, "big_per_year": float((x > q).sum()) / yrs})
        n_tr = int(((s.index >= W0) & (s.index <= W1)).sum())
        o = {"band": band, "power_by_36m": power, "trade_days_in_window": n_tr, "net_a_year": float(x.sum() / yrs)}
        line = (f"{name:<9} unit {UNIT[name]} sh: mu ${band['mu']:,.2f}/session, sd ${band['sd']:,.2f}, c {band['c']:.3f}, A2 ${band['dd_alarm']:,.0f}, "
                f"net ${o['net_a_year']:,.0f}/yr on {n_tr} trade days; power if the edge is gone {power:.0%} by 36 months"
                + (f"; big day > ${band['big']:,.0f} ({band['big_per_year']:.2f}/yr, watch only)" if band.get("big") else ""))
        if fw and fw["legs"].get(name, {}).get("rows"):
            L = fw["legs"][name]
            r = evaluate(L["series"].to_numpy(float), band, np)
            o["forward"] = {k: v for k, v in L.items() if k != "series"} | {"read": r}
            line += (f"\n          forward from {L['start']}: {L['rows']} sessions, {L['trades']} trades ({L['no_trade_id']} without a trade id; engine "
                     f"exits {L['engine_exits']}), net ${r['net']:,.0f} vs pace ${r['expected_net']:,.0f}; A1 z {r['a1_z']:.2f} (worst check "
                     f"{'n/a' if r['a1_worst_z'] is None else '%.2f' % r['a1_worst_z']} vs -{band['c']:.2f}, {r['checks']} checks); dd ${r['dd']:,.0f} "
                     f"(deepest ${r['dd_max']:,.0f} vs ${band['dd_alarm']:,.0f}); {'TRIP' if (r['a1'] or r['a2']) else 'clear'}"
                     + (f"; KEEL scale term {L['keel_scale']:.3f}" if L.get("keel_scale") is not None else "")
                     + (f"; {L['no_keel_size']} rows with no keel_size anywhere (KEEL taken as 1.0)" if L.get("no_keel_size") else "")
                     + (f"; days off the session calendar {L['days_off_calendar']}" if L["days_off_calendar"] else ""))
        elif fw:
            line += "\n          forward: no trades yet"
        print(line, flush=True)
        out["legs"][name] = o
    json.dump(out, open(os.path.join(OUT, "q38_bands.json"), "w"), indent=1, default=float)
    print("wrote", os.path.join(OUT, "q38_bands.json"))


if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] != "run":
        raise SystemExit(__doc__)
    run(dt.date.fromisoformat(sys.argv[2]) if len(sys.argv) > 2 else dt.date.today())
