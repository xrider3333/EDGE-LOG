"""ORB GAP38 r1 (ORB lane, 2026-10-15) - does ORB do better when its breakout goes WITH the opening gap? Reading shelf No. 38. Frozen in
docs/PREREG_orb_gap38_r1_2026-10-15.md; this harness checks that note's LF sha256 first and stops on a mismatch. WF only, lockbox unread,
read-only (stdout and --out only).

    python tools/orb_gap38_r1.py [--repo <checkout with the masters>] [--out result.json]
"""
import argparse
import hashlib
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NOTE = os.path.join(HERE, "docs", "PREREG_orb_gap38_r1_2026-10-15.md")
NOTE_SHA = "64e4170c006404d654448fde4332be15698d728863c426c7a1a23f3c93be421d"
RUN0, WF0, WF1 = "2010-05-01", "2016-07-01", "2025-06-27"
MASTER = "ADJ_NQ_5m_RTH.csv"
MULT, COST = 20.0, 0.533
B, BLOCK, SEED = 2000, 20, 7


def lf_sha(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read().replace(b"\r\n", b"\n")).hexdigest()


def max_dd(v, np):
    cum = np.cumsum(v)
    return float(np.max(np.maximum.accumulate(np.maximum(cum, 0.0)) - cum))


def four(daily, yrs, np):
    from augur_engine.drawdowns import dd5, dd_pct_peak
    v = daily.to_numpy(float)
    dd = max_dd(v, np)
    roc = 30.0 * (float(v.sum()) / yrs) / dd if dd > 0 else float("inf")
    d5 = dd5(daily)
    k = 30000.0 / dd if dd > 0 else 1.0
    neg = np.minimum(v, 0.0)
    sortino = float(v.mean() / math.sqrt(float((neg ** 2).mean())) * math.sqrt(252))
    return {"roc30": round(roc, 2), "dd5_at_30k": round(float(d5["dd5_usd"]) * k, 0), "one_episode": d5["one_episode"],
            "dd_pct_peak_at_30k": dd_pct_peak(daily * k, start=100000.0), "sortino": round(sortino, 3),
            "net_per_year": round(float(v.sum()) / yrs, 0), "max_dd": round(dd, 0)}


def welch(x, y, np):
    from scipy import stats
    x, y = np.asarray(x, float), np.asarray(y, float)
    mx, my = float(x.mean()), float(y.mean())
    vx, vy = float(x.var(ddof=1)) / len(x), float(y.var(ddof=1)) / len(y)
    se = math.sqrt(vx + vy)
    df = (vx + vy) ** 2 / (vx ** 2 / (len(x) - 1) + vy ** 2 / (len(y) - 1))
    hw = float(stats.t.ppf(0.975, df)) * se
    d = mx - my
    return {"n_agree": int(len(x)), "n_against": int(len(y)), "mean_agree_pct": round(100 * mx, 5), "mean_against_pct": round(100 * my, 5),
            "diff_pct": round(100 * d, 5), "ci95_pct": [round(100 * (d - hw), 5), round(100 * (d + hw), 5)], "t": round(d / se, 3)}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG")
    ap.add_argument("--out")
    a = ap.parse_args(argv)
    got = lf_sha(NOTE)
    print("PIN note LF sha256 %s (frozen %s); harness LF sha256 %s" % (got, NOTE_SHA, lf_sha(os.path.abspath(__file__))), flush=True)
    if got != NOTE_SHA:
        raise SystemExit("refused: the prereg note is not the frozen one (nothing computed)")
    sys.path.insert(0, a.repo)
    os.chdir(a.repo)
    os.environ.setdefault("AUGUR_TRIAL_CACHE", "0")
    import numpy as np
    import pandas as pd
    from api import cloud_signal as cs
    from augur_engine.data import find_master, load_master_arrays
    from augur_engine.engine import run_backtest
    leg = cs.CROWN_LEGS["ORB_R6"]
    m = find_master("NQ", "5m", "rth", "db_adj_rth")
    if m is None or m.get("filename") != MASTER:
        raise SystemExit("refused: the db_adj_rth NQ 5m master is %r, not the frozen %s" % (m and m.get("filename"), MASTER))
    arr = load_master_arrays(m, date_from=RUN0, date_to=WF1)
    r = run_backtest(leg["strategy"], arrays=arr, params=dict(leg["params"]), cost_pts=COST, return_trades=True)
    ix = pd.DatetimeIndex(arr["index"])
    ix = ix.tz_convert("America/New_York").tz_localize(None) if ix.tz is not None else ix
    day = ix.normalize()
    bars = pd.DataFrame({"o": np.asarray(arr["open"], float), "h": np.asarray(arr["high"], float), "l": np.asarray(arr["low"], float),
                         "c": np.asarray(arr["close"], float)}, index=ix)
    g = bars.groupby(day)
    D = pd.DataFrame({"o": g["o"].first(), "h": g["h"].max(), "l": g["l"].min(), "c": g["c"].last()})
    D["gap"] = (D["o"] - D["c"].shift(1)) / (D["h"] - D["l"]).shift(1).rolling(10).mean()
    T0, T1 = pd.Timestamp(WF0), pd.Timestamp(WF1)
    print("leg %s %s on %s; engine trades %d" % (leg["strategy"], leg["params"], m["filename"], len(r["trades"])), flush=True)
    rows = []
    for t in r["trades"]:
        ei, xi, pts, d, e = int(t[0]), int(t[1]), float(t[2]), int(t[3]), float(t[4])
        if not (T0 <= day[ei] <= T1):
            continue
        gp = float(D["gap"].get(day[ei], float("nan")))
        sd = 1 if d > 0 else -1
        rows.append({"entry_day": day[ei], "exit_day": day[min(xi, len(day) - 1)], "usd": pts * MULT, "ret": pts / e, "side": sd, "gap": gp,
                     "grp": "agree" if sd * gp > 0 else "against" if sd * gp < 0 else "neutral"})
    T = pd.DataFrame(rows)
    nan_gap = int(T["gap"].isna().sum())
    T.loc[T["gap"].isna(), "grp"] = "neutral"
    yrs = (T1 - T0).days / 365.25
    print("WF trades %d (%.0f a year): agree %d, against %d, neutral %d (no gap value %d)" % (len(T), len(T) / yrs, (T["grp"] == "agree").sum(),
          (T["grp"] == "against").sum(), (T["grp"] == "neutral").sum(), nan_gap), flush=True)
    res = {"trades": int(len(T)), "groups": T["grp"].value_counts().to_dict(), "nan_gap": nan_gap}
    res["split"] = welch(T.loc[T["grp"] == "agree", "ret"], T.loc[T["grp"] == "against", "ret"], np)
    big = T["gap"].abs() >= 0.25
    res["split_big_gap"] = welch(T.loc[big & (T["grp"] == "agree"), "ret"], T.loc[big & (T["grp"] == "against"), "ret"], np)
    for k in ("split", "split_big_gap"):
        s = res[k]
        print("%s: agree n %d mean %.4f%% | against n %d mean %.4f%% | diff %.4f%% (95%% %s) t %.2f" % (k.upper(), s["n_agree"], s["mean_agree_pct"],
              s["n_against"], s["mean_against_pct"], s["diff_pct"], s["ci95_pct"], s["t"]), flush=True)
    # arms: daily $ by exit day on every RTH session in the window
    cal = pd.DatetimeIndex(sorted(set(day)))
    cal = cal[(cal >= T0) & (cal <= T1)]
    w = {"A": np.ones(len(T)), "B": np.where(T["grp"] == "against", 0.0, 1.0), "C": np.where(T["grp"] == "against", 0.5, 1.0)}
    daily = {}
    for k, wt in w.items():
        s = pd.Series(T["usd"].to_numpy() * wt, index=pd.DatetimeIndex(T["exit_day"])).groupby(level=0).sum()
        daily[k] = s.reindex(cal).fillna(0.0)
        res["four_" + k] = four(daily[k], yrs, np)
        res["four_" + k]["trades_per_year"] = round(float((wt > 0).sum()) / yrs, 1)
        f = res["four_" + k]
        print("ARM %s: ROC@30k %s | DD5 $%s | DD%% from peak %s | Sortino %s | net/yr $%s | %s trades/yr%s" % (k, f["roc30"], f["dd5_at_30k"],
              f["dd_pct_peak_at_30k"], f["sortino"], f["net_per_year"], f["trades_per_year"], " (one episode)" if f["one_episode"] else ""), flush=True)
    # block bootstrap of the ROC differences, the same draws for every arm
    rng = np.random.default_rng(SEED)
    n = len(cal)
    X = {k: v.to_numpy(float) for k, v in daily.items()}
    dif = {"B": [], "C": []}
    for _ in range(B):
        idx = []
        while len(idx) < n:
            s0 = int(rng.integers(0, n))
            idx.extend(range(s0, min(n, s0 + BLOCK)))
        idx = np.asarray(idx[:n])
        roc = {}
        for k in ("A", "B", "C"):
            v = X[k][idx]
            dd = max_dd(v, np)
            roc[k] = 30.0 * (v.sum() / yrs) / dd if dd > 0 else float("nan")
        for k in ("B", "C"):
            dif[k].append(roc[k] - roc["A"])
    for k in ("B", "C"):
        lo, hi = np.nanpercentile(dif[k], [5, 95])
        res["roc_diff_" + k] = {"point": round(res["four_" + k]["roc30"] - res["four_A"]["roc30"], 2), "ci90": [round(float(lo), 2), round(float(hi), 2)]}
        print("ROC %s - A: %+.2f (90%% block bootstrap %+.2f .. %+.2f)" % (k, res["roc_diff_" + k]["point"], lo, hi), flush=True)
    # map: the WF top-26 money days
    dayp = T.groupby("exit_day")["usd"].sum().sort_values(ascending=False)
    top = T[T["exit_day"].isin(set(dayp.index[:26]))]
    res["top26_against"] = [int((top["grp"] == "against").sum()), int(len(top))]
    print("MAP: WF top-26 money days: %d of %d trades on them went AGAINST the gap" % tuple(res["top26_against"]), flush=True)
    lo, hi = res["split"]["ci95_pct"]
    verdict = "WITH THE GAP PAYS" if lo > 0 else "AGAINST THE GAP PAYS" if hi < 0 else "NO GAP EFFECT"
    res["verdict"] = verdict
    res["lift"] = {k: bool(verdict == "WITH THE GAP PAYS" and res["roc_diff_" + k]["ci90"][0] > 0) for k in ("B", "C")}
    print("VERDICT: %s; arm lifts: B %s, C %s" % (verdict, res["lift"]["B"], res["lift"]["C"]), flush=True)
    if a.out:
        with open(a.out, "w", encoding="utf-8") as fh:
            json.dump(res, fh, indent=1, default=str)
    return res


if __name__ == "__main__":
    main(sys.argv[1:])
