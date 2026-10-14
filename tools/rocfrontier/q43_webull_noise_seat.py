"""Q43 THE WEBULL BOOK'S NOISE SEAT (bookq/PREDATA_Q43_WEBULL_NOISE_SEAT.txt): S422 (NOISE_422_PLAIN, CT304H) vs S382 (NOISE_382, CT304) on QQQ,
per share at 10 sh x plugin size; alone, in ORB + NOISE and in ORB + NOISE + DIP (Q41's saved ORB / DIP series); paired block bootstrap of the
book ROC@30k difference. WF 2017-08-07..2025-06-29; LB apart, a report.
    python q43_webull_noise_seat.py run"""
import hashlib
import json
import os
import sys

REPO = r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"
BQ = r"C:\EdgeLog\_anatomy_cache\bookq"
NOTE = os.path.join(BQ, "PREDATA_Q43_WEBULL_NOISE_SEAT.txt")
NOTE_SHA = "87d6d3635390a476d8c6ca83cfeb94c923172a6fb2deee597a5e5826233dc648"
QQQ5_SHA = "782dabdd7dd7d265c9a31626f03c6940cdaaf4d7511da95bf8a8efc41fba5a1d"
Q41_DAILY = r"C:\EdgeLog\_anatomy_cache\q41\q41_legs_daily.csv"
Q41_JSON = r"C:\EdgeLog\_anatomy_cache\q41\q41_webull_book.json"
OUT = r"C:\EdgeLog\_anatomy_cache\q43"
WF = ("2017-08-07", "2025-06-29")
LB = ("2025-06-30", "2026-06-30")
COST_SH_RT, UNIT = 0.02, 10.0
SEED, DRAWS, BLOCK = 20261014, 2000, 20
lf = lambda p: hashlib.sha256(open(p, "rb").read().replace(b"\r\n", b"\n")).hexdigest()
sha = lambda p: hashlib.sha256(open(p, "rb").read()).hexdigest()


def noise_unit(leg, arr, run_backtest, np, pd, day):
    """per-share P&L x 10 sh x plugin size, net of $0.02 a share RT, by exit day (Q38's NOISE branch, for either file)"""
    r = run_backtest(leg["strategy"], arrays=arr, params=dict(leg["params"]), cost_pts=0.0, return_trades=True)
    sizes, scp = r.get("trade_sizes"), float(r.get("size_cost_pts") or 0.0)
    assert sizes is None or len(sizes) == len(r["trades"]), "size list out of step"
    if sizes is not None and any(float(s) > 1.0 for s in sizes):
        assert scp > 0, "sized trades without size_cost_pts - the fold cannot be inverted (NOISE review #155)"
    rows = []
    for i, t in enumerate(r["trades"]):
        s = float(sizes[i]) if sizes is not None else 1.0
        raw = (float(t[2]) + (s - 1.0) * scp) / s
        rows.append((day[min(int(t[1]), len(day) - 1)], UNIT * s * (raw - COST_SH_RT)))
    print(f"   {leg['strategy']}: {len(rows)} trades; sizes {dict(zip(*np.unique(np.asarray(sizes if sizes is not None else [1.0], float), return_counts=True)))}",
          flush=True)
    return pd.Series([v for _, v in rows], index=pd.DatetimeIndex([d for d, _ in rows])).groupby(level=0).sum()


def run():
    for p in (REPO, os.path.join(REPO, "tools"), BQ):
        sys.path.insert(0, p)
    os.chdir(REPO)
    import numpy as np
    import pandas as pd
    import seat_pipeline_final as SP
    from api import cloud_signal as cs
    from augur_engine.data import find_master, load_master_arrays
    from augur_engine.drawdowns import dd5, dd_pct_peak
    from augur_engine.engine import run_backtest
    from power_line import stationary_indices
    qm = find_master("QQQ", "5m", "rth", "alpaca_split_rth")
    pins = {"note": lf(NOTE), "qqq5m": sha(os.path.join(REPO, "augur_uploads", qm["filename"])), "q41_daily": sha(Q41_DAILY)}
    print(f"PINS: note LF {pins['note']}; script LF {lf(__file__)}; QQQ 5m {qm['filename']} {pins['qqq5m']}; q41 daily {pins['q41_daily']}", flush=True)
    if (pins["note"], pins["qqq5m"]) != (NOTE_SHA, QQQ5_SHA):
        raise SystemExit("refused: a pinned input is not the frozen one (nothing computed)")
    os.makedirs(OUT, exist_ok=True)
    arr = load_master_arrays(qm)
    ix = pd.DatetimeIndex(arr["index"])
    ix = ix.tz_convert("America/New_York").tz_localize(None) if ix.tz is not None else ix
    day = ix.normalize()
    L = pd.read_csv(Q41_DAILY, index_col=0, parse_dates=True)
    cal = L.index
    S382 = noise_unit(cs.CROWN_LEGS["NOISE_382"], arr, run_backtest, np, pd, day).reindex(cal).fillna(0.0)
    S422 = noise_unit(cs.SHADOW_LEGS["NOISE_422_PLAIN"], arr, run_backtest, np, pd, day).reindex(cal).fillna(0.0)
    gap = float((S382 - L["NOISE_382"]).abs().max())
    print(f"PARITY: S382 vs Q41's saved NOISE_382 series, max |daily diff| ${gap:.4f}", flush=True)
    assert gap < 1.0, "parity failed - nothing further is read"

    def four(x, a, b):
        w = x[(x.index >= a) & (x.index <= b)]
        v = w.to_numpy(float)
        yrs = (pd.Timestamp(b) - pd.Timestamp(a)).days / 365.25
        q = np.cumsum(v)
        dd = float((np.maximum.accumulate(np.concatenate([[0.0], q]))[1:] - q).max()) if len(v) else 0.0
        r5 = dd5(w)
        p = dd_pct_peak(v, 100_000)
        p = float(p["dd_pct"] if isinstance(p, dict) else p)
        npy = float(v.sum()) / yrs
        return {"roc30": npy * 30.0 / dd if dd > 0 else float("nan"), "dd5": float(r5["dd5_usd"]), "dd_pct_peak": p, "sortino": SP.sortino(v),
                "net_per_year": npy, "worst_dd": dd, "one_episode": bool(r5["one_episode"])}

    O, D = L["ORB_R6"], L["DIP_424F"]
    rows = {"S382 alone": S382, "S422 alone": S422, "ORB + S382 (= Q41 V1)": O + S382, "ORB + S422": O + S422,
            "ORB + S382 + DIP (= Q41 V0)": O + S382 + D, "ORB + S422 + DIP": O + S422 + D}
    q41 = json.load(open(Q41_JSON))["rows"]
    for mine, theirs in (("ORB + S382 (= Q41 V1)", "V1 without DIP"), ("ORB + S382 + DIP (= Q41 V0)", "V0 as deployed")):
        a, b = four(rows[mine], *WF)["net_per_year"], q41[theirs]["WF"]["net_per_year"]
        print(f"PARITY: {mine} $ a year {a:,.2f} vs Q41 {b:,.2f}", flush=True)
        assert abs(a - b) < 1.0, "parity with Q41 failed - nothing further is read"
    out = {"pins": pins, "WF": WF, "LB": LB, "rows": {}}
    for nm, x in rows.items():
        out["rows"][nm] = {"WF": four(x, *WF), "LB": four(x, *LB)}
        a, b = out["rows"][nm]["WF"], out["rows"][nm]["LB"]
        print(f"{nm:<28} WF: ROC@30k {a['roc30']:6.2f} | DD5 ${a['dd5']:>6,.0f} | DD% {a['dd_pct_peak']:4.2f} | Sortino {a['sortino']:4.2f} | "
              f"${a['net_per_year']:>6,.0f}/yr{' | 1 EP' if a['one_episode'] else ''}   LB (report): ROC@30k {b['roc30']:6.2f} | "
              f"Sortino {b['sortino']:4.2f} | ${b['net_per_year']:>6,.0f}/yr", flush=True)
    w = (cal >= WF[0]) & (cal <= WF[1])
    yrs = (pd.Timestamp(WF[1]) - pd.Timestamp(WF[0])).days / 365.25
    idx = stationary_indices(int(w.sum()), DRAWS, BLOCK, np.random.default_rng(SEED))

    def roc(M):
        q = np.cumsum(M, axis=1)
        dd = (np.maximum.accumulate(np.concatenate([np.zeros((M.shape[0], 1)), q], axis=1), axis=1)[:, 1:] - q).max(axis=1)
        return (M.sum(axis=1) / yrs) * 30.0 / np.where(dd > 0, dd, np.nan)

    out["paired"] = {}
    for tag, base in (("without DIP", O), ("with DIP", O + D)):
        A = (base + S422)[w].to_numpy(float)[idx]
        B = (base + S382)[w].to_numpy(float)[idx]
        dlt = roc(A) - roc(B)
        p5, p50, p95 = (float(np.nanpercentile(dlt, q)) for q in (5, 50, 95))
        word = ("the #422 seat lifts the Webull book" if p5 > 0 else "the #422 seat lowers it" if p95 < 0 else "not distinguishable on the walk-forward")
        out["paired"][tag] = {"p5": p5, "p50": p50, "p95": p95, "width_90": p95 - p5, "verdict": word}
        print(f"PAIRED BOOTSTRAP ({tag}): S422 - S382 book ROC@30k: p5 {p5:+.2f} / p50 {p50:+.2f} / p95 {p95:+.2f} (90% width {p95 - p5:.2f}) => {word}",
              flush=True)
    pd.DataFrame({"S382": S382, "S422": S422}).to_csv(os.path.join(OUT, "q43_noise_daily.csv"))
    json.dump(out, open(os.path.join(OUT, "q43_webull_noise_seat.json"), "w"), indent=1, default=float)
    print("wrote", os.path.join(OUT, "q43_webull_noise_seat.json"))


if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] != "run":
        raise SystemExit(__doc__)
    run()
