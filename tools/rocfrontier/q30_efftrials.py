"""Q30 EFFECTIVE TRIALS (MANAGER #128 item 1) - a REPORT per bookq/PREDATA_Q30_EFFTRIALS.txt (LF sha printed at start). WF only; no lockbox row.
    python q30_efftrials.py looks     rebuild the 39 rebuildable looks as daily $ (S1 WF, marked to market, book UTC stamps) -> q30/looks_daily.csv
    python q30_efftrials.py t485      re-run #485's distinct settings on its tuning window (2016-01-04..2025-06-29) -> q30/t485_daily.csv
    python q30_efftrials.py report    ONC on both families -> E, the 32-look band, #463's WF Deflated Sharpe at N = E_low / E_high / 71, #485's ratio
ONC = Lopez de Prado & Lewis 2019 as published (k-means on the rows of the distance matrix, every k = 2..N-1, 10 initialisations, silhouette
t-stat quality, recursion on below-mean clusters kept only if the mean quality improves). Distance sqrt((1 - rho) / 2)."""
import hashlib
import json
import math
import os
import sys

REPO = r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "tools"))
os.chdir(REPO)
os.environ.setdefault("AUGUR_TRIAL_CACHE", "1")
os.environ.setdefault("LOKY_MAX_CPU_COUNT", "2")                  # wmic is gone on this box (joblib's core count warns); the runner fleet shares it
os.environ.setdefault("OMP_NUM_THREADS", "2")
import numpy as np
import pandas as pd

BQ = r"C:\EdgeLog\_anatomy_cache\bookq"
sys.path.insert(0, BQ)
import seat_pipeline_final as SP

NOTE = os.path.join(BQ, "PREDATA_Q30_EFFTRIALS.txt")
NOTE_SHA = "3c02ff35e47d94f62655ce20135199c0df1abc7b574eb8880b5fc7813200d25b"
OUT = r"C:\EdgeLog\_anatomy_cache\q30"
LINE = r"C:\EdgeLog\_anatomy_cache\rocfrontier\resmom_r1\resmom_cells_daily_wf_close.csv"
REFS = r"C:\EdgeLog\_anatomy_cache\rocfrontier\mdl_r1\refs"
R62 = r"C:\EdgeLog\_anatomy_cache\adopt449\r62_agfix.py"
J485 = r"C:\EdgeLog\manager\qqq_validate_1007\stage2_job_NOISE.json"
D0, D1 = "2010-06-07", "2026-06-30"
SEED, SEED_CHECK, N_INIT = 20261009, 20261010, 10
N_RAW_LOOKS = 71
GAMMA = 0.5772156649
# group A: the looks that ARE saved book runs (LOOKS_LEDGER_R1.csv; L007 / L015 / L064 via their re-run on other data)
RUNS = {"L032": 430, "L033": 429, "L034": 431, "L039": 440, "L040": 439, "L041": 441, "L043": 445, "L046": 449, "L047": 448, "L048": 450,
        "L054": 456, "L060": 453, "L061": 454, "L081": 468, "L099": 469, "L100": 470, "L113": 473, "L114": 474, "L115": 472, "L116": 471,
        "L117": 475, "L118": 476, "L119": 477, "L120": 478, "L007": 446, "L015": 444, "L064": 457}
os.makedirs(OUT, exist_ok=True)


def pins():
    s = hashlib.sha256(open(NOTE, "rb").read().replace(b"\r\n", b"\n")).hexdigest()
    print(f"PINS: pre-data note LF sha256 {s}; script sha256 {hashlib.sha256(open(__file__, 'rb').read()).hexdigest()}", flush=True)
    if s != NOTE_SHA:
        raise SystemExit("refused: the note is not the frozen one (nothing computed)")
    return s


def wf_index():
    D = SP.load_pinned_daily(LINE, SP.LINE_FILE_SHA)
    return D, SP.window(D["book_mtm"]).index


def leg_mtm(leg, d0, d1, cache={}):
    """one leg's marked-to-market daily $ on the book's UTC stamps (augur_engine.book, the code path a BOOK job uses), cached by its definition"""
    from augur_engine import book
    key = json.dumps(leg, sort_keys=True, default=str) + d0 + d1
    if key not in cache:
        tr, inf = book._leg_trades(dict(leg), d0, d1)
        d_, v_ = book._daily(inf.pop("_mtm_day", None) or tr)
        cache[key] = (pd.Series(v_, index=pd.to_datetime(d_)).groupby(level=0).sum() if len(d_) else pd.Series(dtype=float),
                      float(sum(p for _, p in tr)))
    return cache[key]


def looks():
    pins()
    from book_dd_attribution import run_job
    D, idx = wf_index()
    cols, repro = {}, {}
    for lid, rid in RUNS.items():
        job = run_job(rid)
        legs = [dict(l.get("leg", l)) for l in job["legs"]]
        d0, d1 = str(job.get("date_from") or D0)[:10], str(job.get("date_to") or D1)[:10]
        tot, closed = pd.Series(0.0, index=idx), 0.0
        for leg in legs:
            s, c = leg_mtm(leg, d0, d1)
            tot = tot.add(s.reindex(idx).fillna(0.0), fill_value=0.0)
            closed += c
        want = (((job.get("result") or {}).get("book") or {}).get("whole") or {}).get("total_pnl")
        repro[lid] = {"run": rid, "legs": len(legs), "window": [d0, d1], "closed_net": closed, "run_whole_net": want,
                      "match": (want is not None and abs(closed - float(want)) <= max(1.0, 0.001 * abs(float(want))))}
        cols[lid] = tot
        print(f"  {lid} = #{rid}: {len(legs)} legs {d0}..{d1}; closed net ${closed:,.0f} vs the run's ${want if want is None else round(float(want))} -> "
              f"{'reproduces' if repro[lid]['match'] else 'DOES NOT reproduce (kept, flagged)'}", flush=True)
    # group B: arithmetic on #463 (the pinned line file's book column) and the cached refs
    from api.book_shadow import BOOK463_LEGS
    B = SP.window(D["book_mtm"])
    noise = [l for l in BOOK463_LEGS if l["strategy"].startswith("NOISE")][0]
    nz = leg_mtm(noise, D0, D1)[0].reindex(idx).fillna(0.0)
    cols["L134"], cols["L135"] = B + 0.25 * nz, B + 1.0 * nz
    for lid, f in (("L136", "ENGUQ_S2_swap.csv"), ("L137", "DIP_NQ_433.csv"), ("L138", "DIP_ES_452.csv")):
        r = pd.read_csv(os.path.join(REFS, f), parse_dates=["date"]).groupby("date")["pnl"].sum()
        cols[lid] = B + r.reindex(idx).fillna(0.0)
    # round 62's sizing rules and the agreement tilt: r62_agfix.py's own per-trade machinery, run up to its scoring loop
    src = open(R62, encoding="utf-8").read()
    cut = src.index("\nR = {")
    ns = {"__name__": "r62_for_q30", "__file__": R62}
    exec(compile(src[:cut], R62, "exec"), ns)
    M = lambda sizes: ns["book_series"](sizes)[1].reindex(idx).fillna(0.0)
    m0 = M(ns["BASE"])
    gap = float((m0 - B).abs().max())
    print(f"  round-62 machinery: base vs #463's book column max gap ${gap:,.2f}", flush=True)
    cols["L084"] = M(ns["vol_sizes"](20, 0.5, 2.0)[0])
    cols["L085"] = M(ns["vol2_sizes"](20, 250))
    cols["L086"] = M(ns["vol2_sizes"](20, 500))
    cols["L087"] = M(ns["vol2_sizes"](60, 250))
    cols["L088"] = M(ns["overlap_sizes"](0.5)[0])
    cols["L089"] = M(ns["overlap_sizes"](0.0)[0])
    cols["L121"] = M(ns["overlap_sizes_fill"](1.5)[0])
    df = pd.DataFrame(cols).reindex(idx).fillna(0.0)
    df.index.name = "date"
    df.to_csv(os.path.join(OUT, "looks_daily.csv"))
    json.dump({"reproduction": repro, "r62_base_gap": gap, "n_looks": int(df.shape[1])}, open(os.path.join(OUT, "looks_meta.json"), "w"), indent=1, default=float)
    print(f"wrote {df.shape[1]} looks x {df.shape[0]} WF days -> {os.path.join(OUT, 'looks_daily.csv')}")


def t485():
    pins()
    from augur_engine.data import find_master, load_master_arrays
    from augur_engine.engine import run_backtest
    J = json.load(open(J485))
    R = J["result"]
    win = R["validate"]["windows"]["optimize"]
    keys = sorted(R["best_params"].keys())
    m = find_master("QQQ", J["timeframe"], "rth", "alpaca_split_rth")
    assert m and int(m.get("id")) == 113, m
    arr = load_master_arrays(m, date_from=J["date_from"], date_to=win[1])
    ix = pd.DatetimeIndex(arr["index"])
    day = (ix.tz_localize(None) if ix.tz is not None else ix).normalize()
    seen, cfgs = set(), []
    for p in R["points"]:
        cfg = {k: p[k] for k in keys if k in p}
        sig = json.dumps(cfg, sort_keys=True)
        if len(cfg) == len(keys) and sig not in seen:
            seen.add(sig)
            cfgs.append(cfg)
    best = json.dumps({k: R["best_params"][k] for k in keys}, sort_keys=True)
    cols, ntr = {}, {}
    sess = pd.DatetimeIndex(sorted(set(day[(day >= pd.Timestamp(J["date_from"])) & (day <= pd.Timestamp(win[1]))])))
    for i, cfg in enumerate(cfgs):
        bt = run_backtest(J["strategy"], arrays=arr, params=cfg, cost_pts=float(J["cost_pts"]), return_trades=True)
        tr = bt.get("trades") or []
        s = pd.Series([float(t[2]) * float(J["mult"]) for t in tr], index=[day[min(int(t[1]), len(day) - 1)] for t in tr]).groupby(level=0).sum()
        nm = "champion" if json.dumps(cfg, sort_keys=True) == best else f"s{i:03d}"
        cols[nm], ntr[nm] = s.reindex(sess).fillna(0.0), len(tr)
        if (i + 1) % 25 == 0:
            print(f"   {i + 1}/{len(cfgs)} settings", flush=True)
    df = pd.DataFrame(cols)
    df.index.name = "date"
    valid = [c for c in df.columns if ntr[c] >= int(J["min_trades"])]
    df[valid].to_csv(os.path.join(OUT, "t485_daily.csv"))
    json.dump({"distinct": len(cfgs), "valid": len(valid), "run_n_valid": R["n_valid"], "window": [J["date_from"], win[1]], "trades": ntr,
               "champion_in": "champion" in valid}, open(os.path.join(OUT, "t485_meta.json"), "w"), indent=1)
    print(f"#485: {len(cfgs)} distinct settings, {len(valid)} with >= {J['min_trades']} trades (the run counted {R['n_valid']}); champion found: {'champion' in cols}")


# ------------------------------------------------------------------ ONC (Lopez de Prado & Lewis 2019; MLAM snippets 4.1 / 4.2)
def _tstat(s):
    s = np.asarray(s, float)
    if len(s) < 2 or s.std() == 0:
        return math.inf                                                # a singleton cannot be improved by re-clustering
    return float(s.mean() / s.std())


def onc_base(corr, max_k, n_init, rng):
    from sklearn.cluster import KMeans
    from sklearn.metrics import silhouette_samples
    x = np.sqrt(np.clip((1.0 - corr.fillna(0).to_numpy()) / 2.0, 0.0, None))
    best_s, best_lab, best_q = None, None, -math.inf
    for _ in range(n_init):
        for k in range(2, max_k + 1):
            km = KMeans(n_clusters=k, n_init=1, random_state=int(rng.integers(0, 2 ** 31 - 1))).fit(x)
            if len(set(km.labels_)) < 2:
                continue
            s = silhouette_samples(x, km.labels_)
            q = s.mean() / s.std() if s.std() > 0 else -math.inf
            if q > best_q:
                best_s, best_lab, best_q = s, km.labels_, q
    cl = {int(c): list(corr.columns[np.where(best_lab == c)[0]]) for c in np.unique(best_lab)}
    return cl, pd.Series(best_s, index=corr.columns)


def onc(corr, n_init=N_INIT, seed=SEED, rng=None):
    """-> {cluster id: [members]}"""
    from sklearn.metrics import silhouette_samples
    rng = rng or np.random.default_rng(seed)
    n = corr.shape[1]
    if n <= 2:
        return {i: [c] for i, c in enumerate(corr.columns)}
    cl, silh = onc_base(corr, n - 1, n_init, rng)
    ts = {i: _tstat(silh[m]) for i, m in cl.items()}
    fin = [v for v in ts.values() if math.isfinite(v)]
    mean_t = float(np.mean(fin)) if fin else math.inf
    redo = [i for i, v in ts.items() if v < mean_t]
    if len(redo) <= 1:
        return cl
    keys = [m for i in redo for m in cl[i]]
    cl2 = onc(corr.loc[keys, keys], n_init, rng=rng)
    new = {j: m for j, m in enumerate([cl[i] for i in cl if i not in redo] + list(cl2.values()))}
    x = np.sqrt(np.clip((1.0 - corr.fillna(0).to_numpy()) / 2.0, 0.0, None))
    lab = np.zeros(n, int)
    for j, m in new.items():
        lab[[corr.columns.get_loc(c) for c in m]] = j
    s_new = pd.Series(silhouette_samples(x, lab), index=corr.columns) if len(new) > 1 else pd.Series(0.0, index=corr.columns)
    new_t = [_tstat(s_new[m]) for m in new.values()]
    new_mean = float(np.mean([v for v in new_t if math.isfinite(v)])) if any(math.isfinite(v) for v in new_t) else math.inf
    old_mean = float(np.mean([ts[i] for i in redo]))
    return new if new_mean > old_mean else cl


def cluster_series(df, cl):
    """each cluster's series = the inverse-variance-weighted mean of its members"""
    out = {}
    for i, m in cl.items():
        v = df[m].var(ddof=1).replace(0, np.nan)
        w = (1.0 / v) / (1.0 / v).sum()
        out[i] = (df[m] * w).sum(axis=1)
    return pd.DataFrame(out)


def dsr(x, N, V):
    """Bailey & Lopez de Prado 2014 on a daily series x (Sharpe not annualised), N trials, V = the variance of the trials' Sharpe ratios"""
    from scipy.stats import kurtosis, norm, skew
    x = np.asarray(x, float)
    T = len(x)
    sr = x.mean() / x.std(ddof=1)
    g3, g4 = float(skew(x)), float(kurtosis(x, fisher=False))
    sr0 = 0.0 if N <= 1 else math.sqrt(V) * ((1 - GAMMA) * norm.ppf(1 - 1.0 / N) + GAMMA * norm.ppf(1 - 1.0 / (N * math.e)))
    z = (sr - sr0) * math.sqrt(T - 1) / math.sqrt(1 - g3 * sr + (g4 - 1) / 4.0 * sr ** 2)
    return {"N": N, "sr_daily": sr, "sr_annual": sr * math.sqrt(252), "sr0_daily": sr0, "skew": g3, "kurt": g4, "T": T, "dsr": float(norm.cdf(z))}


def family(df, name):
    corr = df.corr()
    cl = onc(corr, seed=SEED)
    cl_chk = onc(corr, seed=SEED_CHECK)
    C = cluster_series(df, cl)
    srs = C.mean() / C.std(ddof=1)
    V = float(srs.var(ddof=1)) if len(srs) > 1 else float((df.mean() / df.std(ddof=1)).var(ddof=1))
    print(f"{name}: N = {df.shape[1]} series, median pairwise rho {float(np.nanmedian(corr.where(~np.eye(len(corr), dtype=bool)).to_numpy())):.3f}; "
          f"ONC E = {len(cl)} (check seed: {len(cl_chk)}); V of the cluster Sharpes {V:.3e}{'' if len(srs) > 1 else ' (one cluster: V from the members - fallback)'}")
    for i, m in cl.items():
        print(f"   cluster {i}: {len(m)} - {', '.join(m[:12])}{' ...' if len(m) > 12 else ''}")
    return {"n": int(df.shape[1]), "E": len(cl), "E_check_seed": len(cl_chk), "V": V, "clusters": {int(i): m for i, m in cl.items()}}


def report():
    psha = pins()
    D, idx = wf_index()
    B = SP.window(D["book_mtm"])
    SP.check_parity(B, "book463")
    Lk = pd.read_csv(os.path.join(OUT, "looks_daily.csv"), parse_dates=["date"]).set_index("date")
    T5 = pd.read_csv(os.path.join(OUT, "t485_daily.csv"), parse_dates=["date"]).set_index("date")
    fa, fb = family(Lk, "(a) book looks (39 rebuildable of 71)"), family(T5, "(b) #485 settings")
    e_lo, e_hi = fa["E"], fa["E"] + (N_RAW_LOOKS - fa["n"])
    out = {"note_sha256_lf": psha, "looks": fa, "t485": fb, "E_low": e_lo, "E_high": e_hi, "dsr_463": {}, "dsr_485": {}}
    for tag, N in (("E_low", e_lo), ("E_high", e_hi), ("raw_71", N_RAW_LOOKS)):
        out["dsr_463"][tag] = dsr(B.to_numpy(float), N, fa["V"])
    for tag, N in (("E", fb["E"]), ("raw", fb["n"])):
        out["dsr_485"][tag] = dsr(T5["champion"].to_numpy(float), N, fb["V"])
    champ_cl = [m for m in fb["clusters"].values() if "champion" in m]
    out["t485_champion_cluster_size"] = len(champ_cl[0]) if champ_cl else None
    print(f"#485: the champion's own cluster holds {out['t485_champion_cluster_size']} of the {fb['n']} settings (MANAGER #133)")
    print(f"\nEFFECTIVE TRIALS: book looks E = {fa['E']} of the 39 rebuilt -> band E_low {e_lo} / E_high {e_hi} vs 71 raw; #485 E = {fb['E']} of {fb['n']} "
          f"(independence ratio {fb['E'] / fb['n']:.3f})")
    for tag, r in out["dsr_463"].items():
        print(f"  #463 WF Deflated Sharpe at N = {r['N']:>3} ({tag}): DSR {r['dsr']:.4f} (Sharpe {r['sr_annual']:.2f} a year; expected max of N trials {r['sr0_daily'] * math.sqrt(252):.2f} a year; T {r['T']})")
    for tag, r in out["dsr_485"].items():
        print(f"  #485 champion (daily, tuning window) at N = {r['N']:>3} ({tag}): DSR {r['dsr']:.4f} (Sharpe {r['sr_annual']:.2f}; expected max {r['sr0_daily'] * math.sqrt(252):.2f})")
    json.dump(out, open(os.path.join(OUT, "q30_report.json"), "w"), indent=1, default=float)
    print("wrote", os.path.join(OUT, "q30_report.json"))


def selftest():
    rng = np.random.default_rng(1)
    base = rng.normal(size=(500, 3))
    cols = {}
    for g in range(3):
        for j in range(6):
            cols[f"g{g}_{j}"] = base[:, g] + 0.3 * rng.normal(size=500)
    df = pd.DataFrame(cols)
    cl = onc(df.corr(), n_init=3, seed=7)
    assert len(cl) == 3 and all(len({c[:2] for c in m}) == 1 for m in cl.values()), cl
    r = dsr(rng.normal(0.05, 1.0, 2000), 1, 0.0)
    assert r["sr0_daily"] == 0.0 and 0.9 < r["dsr"] <= 1.0
    r10 = dsr(rng.normal(0.05, 1.0, 2000), 10, 0.01 ** 2)
    assert r10["sr0_daily"] > 0
    print("q30 selftest OK (ONC recovers 3 planted clusters; DSR: N = 1 -> no deflation, N > 1 -> a positive expected max)")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "selftest"
    {"selftest": selftest, "looks": looks, "t485": t485, "report": report}[cmd]()
