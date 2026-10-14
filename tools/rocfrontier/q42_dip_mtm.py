"""Q42 DIP_424F MARKED TO MARKET (bookq/PREDATA_Q42_DIP_MTM.txt): DIP's per-share path marked at each RTH session's last 5m close, 6 shares a lot,
$0.02 a share RT; parity with Q38's exit-day series; bands by Q38's calibrate (q35 method, A1 every 5 sessions) on 2022-07-01..2025-06-29;
beside Q38's exit-day band. Reads the QQQ 5m master only.
    python q42_dip_mtm.py run"""
import hashlib
import json
import os
import sys

REPO = r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"
BQ = r"C:\EdgeLog\_anatomy_cache\bookq"
NOTE = os.path.join(BQ, "PREDATA_Q42_DIP_MTM.txt")
NOTE_SHA = "054a7e522a8d2bce4252c4c1e78d28f1e4f1d0eedbbc0e99d98f7315dbba911a"
Q38_SHA = "411ca99b6e2d6647ef035356834da3fab4fbd4958c840f7ab25de2562130dddd"
QQQ5_SHA = "782dabdd7dd7d265c9a31626f03c6940cdaaf4d7511da95bf8a8efc41fba5a1d"
OUT = r"C:\EdgeLog\_anatomy_cache\q42"
lf = lambda p: hashlib.sha256(open(p, "rb").read().replace(b"\r\n", b"\n")).hexdigest()
sha = lambda p: hashlib.sha256(open(p, "rb").read()).hexdigest()


def run():
    for p in (REPO, os.path.join(REPO, "tools"), BQ):
        sys.path.insert(0, p)
    os.chdir(REPO)
    import numpy as np
    import pandas as pd
    import q38_webull_bands as Q38
    from api import cloud_signal as cs
    from augur_engine.data import find_master, load_master_arrays
    from augur_engine.engine import run_backtest
    from power_line import stationary_indices
    qm = find_master("QQQ", "5m", "rth", "alpaca_split_rth")
    pins = {"note": lf(NOTE), "q38": lf(os.path.join(BQ, "q38_webull_bands.py")), "qqq5m": sha(os.path.join(REPO, "augur_uploads", qm["filename"]))}
    print(f"PINS: note LF {pins['note']}; script LF {lf(__file__)}; q38 LF {pins['q38']}; QQQ 5m {qm['filename']} {pins['qqq5m']}", flush=True)
    if (pins["note"], pins["q38"], pins["qqq5m"]) != (NOTE_SHA, Q38_SHA, QQQ5_SHA):
        raise SystemExit("refused: a pinned input is not the frozen one (nothing computed)")
    os.makedirs(OUT, exist_ok=True)
    arr = load_master_arrays(qm)
    ix = pd.DatetimeIndex(arr["index"])
    ix = ix.tz_convert("America/New_York").tz_localize(None) if ix.tz is not None else ix
    day = ix.normalize()
    cal = pd.DatetimeIndex(sorted(set(day)))
    close = pd.Series(np.asarray(arr["close"], float), index=ix).groupby(day).last()
    leg = cs.SHADOW_LEGS["DIP_424F"]
    p = dict(leg["params"], cost_bps=0.0)
    r = run_backtest(leg["strategy"], arrays=arr, params=p, cost_pts=0.0, return_trades=True)
    U = float(Q38.UNIT["DIP_424F"])
    mtm = pd.Series(0.0, index=cal)
    exitday = pd.Series(0.0, index=cal)
    for t in r["trades"]:
        t0, t1, pts, px_in = int(t[0]), int(t[1]), float(t[2]), float(t[4])
        raw = pts * px_in / float(p["notional"])
        px_out = px_in + raw
        d0, d1 = day[t0], day[min(t1, len(day) - 1)]
        exitday[d1] += U * (raw - Q38.COST_SH_RT)
        if d0 == d1:
            mtm[d1] += U * (px_out - px_in - Q38.COST_SH_RT)
            continue
        held = cal[(cal >= d0) & (cal <= d1)]
        prev = px_in
        for d in held[:-1]:
            c = float(close[d])
            mtm[d] += U * (c - prev)
            prev = c
        mtm[d1] += U * (px_out - prev - Q38.COST_SH_RT)
    W0, W1 = Q38.W0, Q38.W1
    w = (cal >= W0) & (cal <= W1)
    ref = Q38.unit_trades("DIP_424F", leg, arr, run_backtest, np)
    q38s = pd.Series([v for _, v in ref], index=pd.DatetimeIndex([d for d, _ in ref])).groupby(level=0).sum().reindex(cal).fillna(0.0)
    gap_ex = abs(float(exitday[w].sum() - q38s[w].sum()))
    print(f"PARITY: exit-day rebuild vs Q38's series on the window ${gap_ex:.4f}; MTM sum - exit-day sum on the window "
          f"${float(mtm[w].sum() - exitday[w].sum()):,.2f} (trades straddling the window edges)", flush=True)
    assert gap_ex < 0.01, "parity failed - nothing further is read"
    H = int(round(36 * w.sum() / ((pd.Timestamp(W1) - pd.Timestamp(W0)).days / 30.4375)))
    checks = np.arange(Q38.WEEK, H + 1, Q38.WEEK)
    from scipy.stats import kurtosis
    out = {"pins": pins, "window": [W0, W1], "H": H}
    for nm, s in (("exit-day (Q38)", exitday), ("marked to market", mtm)):
        x = s[w].to_numpy(float)
        band, power = Q38.calibrate(x, H, checks, np, stationary_indices)
        out[nm] = {"band": band, "power_by_36m": power, "worst_day_sd": float(x.min() / x.std(ddof=1)), "kurtosis": float(kurtosis(x)),
                   "days_nonzero": int((x != 0).sum())}
        print(f"DIP_424F {nm:<17}: mu ${band['mu']:.2f}/session, sd ${band['sd']:.2f}, c {band['c']:.3f}, A2 ${band['dd_alarm']:,.0f}; worst day "
              f"{out[nm]['worst_day_sd']:.1f} sd, kurtosis {out[nm]['kurtosis']:.1f}, {out[nm]['days_nonzero']} non-zero days; power if the edge "
              f"is gone {power:.0%} by 36 months", flush=True)
    rep = out["marked to market"]["power_by_36m"] > out["exit-day (Q38)"]["power_by_36m"]
    out["reading"] = "the MTM band replaces Q38's DIP band" if rep else "Q38's DIP band stays"
    print("READING (pre-set): " + out["reading"], flush=True)
    pd.DataFrame({"exit_day": exitday, "mtm": mtm}).to_csv(os.path.join(OUT, "q42_dip_daily.csv"))
    json.dump(out, open(os.path.join(OUT, "q42_dip_mtm.json"), "w"), indent=1, default=float)
    print("wrote", os.path.join(OUT, "q42_dip_mtm.json"))


if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] != "run":
        raise SystemExit(__doc__)
    run()
