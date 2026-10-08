# BAB r1 (FRONTIER, book queue Q21 = scoping item B1) - betting against beta (cell BETA) and low volatility (cell VOL) in single US stocks, rebalanced
# MONTHLY on RESMOM r1's engine, read as a basket SEAT on the RESMOM line L = #463 + 0.264 x RES. Pre-registered: docs/PREREG_frontier_bab_2026-10-05.txt
# (canonical LF sha256 9928b8c3...c455, committed 0d43cc58 before any number; its ADDENDUM 1 = MANAGER #95's edits 1-4).
# r17_resmom.py is IMPORTED, never copied or edited (STRATEGY-BEATING #93): this file swaps in only (1) the two scores - r17's 'RES' slot carries BETA (score = -beta,
# so r17's "highest 50 long, lowest 50 short" longs the LOWEST betas), its 'RAW' slot carries VOL (score = -volatility); (2) the BETA cell's beta-neutral side sizes;
# (3) the family null's own streams [20261005, 21 / 22, vcode] with the BETA draws sized by the drawn names' own betas. The universe, schedule, pool, hygiene, dividends,
# fills, marks, costs, borrow, Stage A's rules (a)-(f) and r17's reports are r17's code. r17 writes into THIS family's folder (EDGELOG_BAB_R1), never into RESMOM's.
#   python r19_bab.py selftest    toy-world checks of the swapped pieces (r17's own toy world)
#   python r19_bab.py stage_a     WF Stage A through r17's flow + the FRONTIER seat read over L + addendum 1 + the diagnostics -> bab_stageA.json, bab_frontier.json
# Where the prereg is silent the choice is marked CHOICE.
import contextlib, hashlib, json, math, os, sys, time
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
OUT = os.environ.get("EDGELOG_BAB_R1", r"C:\EdgeLog\_anatomy_cache\rocfrontier\bab_r1")
os.environ["EDGELOG_RESMOM_R1"] = OUT                                    # r17 reads its OUT at import: its Stage A json / audit csv / flags land HERE, never in RESMOM's folder
sys.path.insert(0, HERE)
import numpy as np, pandas as pd
import r17_resmom as R17
D15, M12, A13, R11 = R17.D15, R17.M12, R17.A13, R17.R11
if os.path.normcase(os.path.abspath(R17.OUT)) != os.path.normcase(os.path.abspath(OUT)):
    raise SystemExit("refused: r17 was imported before EDGELOG_RESMOM_R1 pointed it at the BAB folder")

TS = pd.Timestamp
PREREG = os.path.join(REPO, "docs", "PREREG_frontier_bab_2026-10-05.txt")
PREREG_SHA = "9928b8c38111219540f92239ed26aa5d88b57ef25b4cff00c8c28e2f052dc455"
NAME = {"RES": "BETA", "RAW": "VOL"}                                    # r17's slot -> this family's cell
CODE = {"RES": 21, "RAW": 22}                                           # the null's stream per cell (prereg LOOKS)
FLOOR = 0.05                                                            # a side's mean beta <= 0.05 is floored at 0.05 (counted)
GROSS = 400000.0                                                        # RESMOM's gross: 50 + 50 x $4,000
RES_CSV = r"C:\EdgeLog\_anatomy_cache\rocfrontier\resmom_r1\resmom_cells_daily_wf.csv"
RES_SHA = "bed7bf8b"
C_RES = 0.264                                                           # L = #463 + 0.264 x RES (BOOK.md 10ab)
SEAT_WIN = (TS("2016-07-01"), TS("2018-06-29"))                         # 10ab: X's daily SD over this window = share x L's
SHARES = (0.25, 0.10)                                                   # 0.25 binds (10ab; MANAGER did not pick before Stage A), 0.10 (Q20's proposal) is reported
HALVES = ((TS("2016-07-01"), TS("2021-12-31")), (TS("2022-01-01"), R17.PRE_END))
CRASH = ("2020-04", "2020-05", "2020-06", "2020-11", "2021-01", "2021-02", "2022-01", "2023-01")
BETA_CAP, SIDE_GAP = 0.20, 0.30                                         # addendum 1 (1); WHAT COULD FOOL US (3)
WF0, PRE_END = R17.WF0, R17.PRE_END
_ORIG = {k: getattr(R17, k) for k in ("rm_scores", "cell_leg", "run_cell", "rm_null", "l1_pnl_x", "dump", "evaluate")}
SCALE, CAP = {}, {}


def prereg_ok():
    got = hashlib.sha256(open(PREREG, "rb").read().replace(b"\r\n", b"\n")).hexdigest()
    if got != PREREG_SHA:
        raise SystemExit(f"refused: {PREREG} reads {got[:16]}..., not the registered {PREREG_SHA[:16]}... (nothing computed)")
    return got


# ------------------------------------------------------------------ the two scores (r17's window, pairs and 230 rule; the beta is RES's own OLS slope, recomputed)
def bab_scores(W, r, uni):
    """-> (n_ret, n_pair, -beta, -vol) for the names `uni` at the rank session r, in r17.rm_scores's shape. beta = the OLS slope (with an intercept) of the name's daily split-safe TOTAL return on ES's
    over the 252-session window's pairs - the same arithmetic r17 uses for RES's beta (selftest: RES rebuilt from this beta equals r17's). vol = the sample SD (ddof 1) of the name's finite daily total
    returns over the same 252 sessions (CHOICE: all of them, ES holes included - volatility needs no market return). NaN where undefined"""
    a = R17.windows(r)[0]
    R = W.Rd[a:r + 1][:, uni]
    m = np.asarray(W.es.ret[a:r + 1], float)
    fin = np.isfinite(R)
    ok = fin & np.isfinite(m)[:, None]
    n_ret, n_pair = fin.sum(axis=0), ok.sum(axis=0)
    with np.errstate(invalid="ignore", divide="ignore"):
        n = np.maximum(n_pair, 1)
        my, mm = np.where(ok, R, 0.0).sum(axis=0) / n, np.where(ok, m[:, None], 0.0).sum(axis=0) / n
        dy, dm = np.where(ok, R - my, 0.0), np.where(ok, m[:, None] - mm, 0.0)
        beta = (dm * dy).sum(axis=0) / (dm * dm).sum(axis=0)
        nf = np.maximum(n_ret, 1)
        mu = np.where(fin, R, 0.0).sum(axis=0) / nf
        vol = np.sqrt(np.where(fin, (R - mu) ** 2, 0.0).sum(axis=0) / np.maximum(n_ret - 1, 1))
    beta = np.where((n_pair >= 2) & np.isfinite(beta), beta, np.nan)
    vol = np.where((n_ret >= 2) & np.isfinite(vol), vol, np.nan)
    return n_ret, n_pair, -beta, -vol


def side_scales(beta_long, beta_short):
    """beta-neutral at the fill with RESMOM's gross: long notional = $400k x bH / (bL + bH), short = $400k x bL / (bL + bH) -> the per-name multipliers of the $4,000 slot (sL, sS) and
    whether a floor bit. sL x bL = sS x bH (neutral) and sL + sS = 2 (gross $400k)"""
    bL, bH = float(np.mean(beta_long)), float(np.mean(beta_short))
    fl = (bL <= FLOOR) or (bH <= FLOOR)
    bL, bH = max(FLOOR, bL), max(FLOOR, bH)
    return 2.0 * bH / (bL + bH), 2.0 * bL / (bL + bH), fl


def cell_leg_bab(L, cell):
    CL = _ORIG["cell_leg"](L, cell)
    CL.cell = cell
    return CL


def l1_pnl_scaled(U, idx, side, cfg, kt=None, sq=None):
    P = _ORIG["l1_pnl_x"](U, idx, side, cfg, kt, sq)
    s = SCALE.get(id(U))
    return P if s is None else P * (s[0] if side > 0 else s[1])


def run_cell_bab(W, CL, cfg, **kw):
    """r17.run_cell; for the BETA cell every position's P&L is multiplied by its side's beta-neutral multiplier (the rebalance's own sL / sS). The unit paths are shared by both cells, so the
    multipliers are keyed by the rebalance's path object and installed only while the BETA cell runs"""
    if getattr(CL, "cell", None) != "RES":
        return _ORIG["run_cell"](W, CL, cfg, **kw)
    SCALE.clear()
    for v in CL.recs:
        if v.traded:
            b = -v.sig
            SCALE[id(v.U)] = side_scales(b[v.long], b[v.short])[:2]
    try:
        with R17.patched(R17, l1_pnl_x=l1_pnl_scaled):
            return _ORIG["run_cell"](W, CL, cfg, **kw)
    finally:
        SCALE.clear()


def bab_null(W, L, nreps, vcode=0):
    """the family null (r17's / r15's draw: per draw and rebalance, 50 longs + 50 shorts drawn uniformly without replacement from that rebalance's pool, base costs); this family's streams
    [20261005, 21 (BETA) / 22 (VOL), vcode]. CHOICE: a BETA draw is sized like the cell - beta-neutral on the DRAWN names' own betas (sL / sS per draw), so the null is the same book with the
    names chosen at random. VOL draws are r15's null_l1 exactly (selftest). -> {slot: (nreps, T)}"""
    nn, slot = R17.SPEC["n_side"], R17.SPEC["slot"]
    cfg = D15.l1_cfg()
    acc = {}
    for cell in R17.CELLS:
        rng = np.random.default_rng([R17.SEED, CODE[cell], vcode])
        a = np.zeros((nreps, W.T))
        for rec in _ORIG["cell_leg"](L, cell).recs:
            if not rec.traded:
                continue
            idx = np.arange(len(rec.pool))
            kt = W.k[rec.f:rec.x + 1]
            PL, PS = D15.l1_pnl(rec.U, idx, 1, cfg, kt), D15.l1_pnl(rec.U, idx, -1, cfg, kt)
            o = D15.draw_order(rng, nreps, len(idx), 2 * nn)
            gl, gs = PL[o[:, :nn]].sum(axis=1), PS[o[:, nn:]].sum(axis=1)
            if cell == "RES":
                b = -rec.sig
                bL, bH = np.maximum(FLOOR, b[o[:, :nn]].mean(axis=1)), np.maximum(FLOOR, b[o[:, nn:]].mean(axis=1))
                gl, gs = gl * (2.0 * bH / (bL + bH))[:, None], gs * (2.0 * bL / (bL + bH))[:, None]
            a[:, rec.f:rec.x + 1] += slot * (gl + gs)
        acc[cell] = a
    if vcode == 0:
        CAP["acc"] = acc
    return acc


def dump_bab(obj, name):
    return _ORIG["dump"](obj, name.replace("resmom_", "bab_"))


def evaluate_bab(W, B, S12, rows, post_mode, nreps, vcode=0, full=False, drop=None):
    res, obj = _ORIG["evaluate"](W, B, S12, rows, post_mode, nreps, vcode, full, drop)
    if post_mode == "remove" and vcode == 0 and drop is None:              # the REGISTERED reading: keep its objects for the FRONTIER reads
        CAP.update(W=W, B=B, S12=S12, rows=rows, obj=obj, res=res)
    return res, obj


@contextlib.contextmanager
def bab_mode():
    with R17.patched(R17, rm_scores=bab_scores, cell_leg=cell_leg_bab, run_cell=run_cell_bab, rm_null=bab_null, dump=dump_bab, evaluate=evaluate_bab):
        yield


# ------------------------------------------------------------------ the FRONTIER reads over the RESMOM line (BOOK.md 10ab definitions; prereg THE SEAT READ + addendum 1)
def line_series(B):
    """L = #463 + 0.264 x RES on #463's own index (RES = STRATEGY-BEATING's registered daily file, sha bed7bf8b...; zero outside its WF rows) + the parity numbers"""
    h = hashlib.sha256(open(RES_CSV, "rb").read()).hexdigest()
    if not h.startswith(RES_SHA):
        raise SystemExit(f"refused: {RES_CSV} sha256 {h[:12]} is not the registered {RES_SHA}... (nothing judged)")
    D = pd.read_csv(RES_CSV, parse_dates=["date"]).set_index("date")
    idx = pd.DatetimeIndex(B.index)
    res = D["RES"].reindex(idx).fillna(0.0).to_numpy(float)
    bm = D["book_mtm"].reindex(idx)
    inwf = (idx >= WF0) & (idx <= PRE_END)
    gap = float(np.nanmax(np.abs(bm.to_numpy(float)[inwf & bm.notna().to_numpy()] - np.asarray(B.raw, float)[inwf & bm.notna().to_numpy()])))
    return res, np.asarray(B.raw, float) + C_RES * res, gap


def figs(x, years):
    m = M12.vmeas(np.asarray(x, float)[None, :], years)
    return {k: float(m[k][0]) for k in ("roc", "sort", "mdd", "net", "ann")}


def episodes_on(SL, x):
    return [{"first": f"{SL.dates[e['i0']]:%Y-%m-%d}", "trough": e["trough"], "depth": e["depth"], "x": float(x[e["i0"]:e["it"] + 1].sum())} for e in SL.qual]


def seat_read(B, S12, SL, rows, xB, acc_cell, res):
    """one cell X on #463's index: the book add L + c X at the 10ab sizes, X's dollars on R (the line's drawdown days) with and without its best R episode against the random-name null on R
    (the same draws, unscaled - both are $4,000-slot books), corr(X, RES), and the #70 gate on #463's 460 days (DO above the null's DO p95; dollars without the best #463 episode > 0)"""
    x = np.asarray(xB, float)[SL.rows]
    Lx, rs = SL.x, np.asarray(res, float)[SL.rows]
    d = SL.dates
    w = (d >= SEAT_WIN[0]) & (d <= SEAT_WIN[1])
    sdx, sdl = float(np.std(x[w], ddof=1)), float(np.std(Lx[w], ddof=1))
    sdx_all, sdl_all = float(np.std(x, ddof=1)), float(np.std(Lx, ddof=1))
    base = figs(Lx, SL.years)
    add = {}
    for sh in SHARES:
        c = sh * sdl / sdx if sdx > 0 else float("nan")
        cw = sh * sdl_all / sdx_all if sdx_all > 0 else float("nan")       # information: the same share on whole-WF SDs (X is flat before its first fill, 2017-01-03)
        add[f"{sh:.2f}"] = {"c": c, "line_plus": figs(Lx + c * x, SL.years), "c_whole_wf_sd": cw, "line_plus_whole_wf_sd": figs(Lx + cw * x, SL.years)}
    eps = episodes_on(SL, x)
    onR = float(x[SL.dd].sum())
    best = max(eps, key=lambda e: e["x"]) if eps else None
    Y = np.zeros((acc_cell.shape[0], B.n))
    Y[:, rows] = acc_cell
    nR = Y[:, SL.rows][:, SL.dd].sum(axis=1)
    p95R = float(np.percentile(nR, 95))
    seat = D15.seat_measure(S12, xB)
    _, _, do_n = D15.null_cell(S12, acc_cell, rows, B.n)
    do_n = np.asarray(do_n, float)
    fin = do_n[np.isfinite(do_n)]
    eps463 = D15.episodes_table(S12, xB)
    dd463 = float(np.asarray(xB, float)[S12.rows][S12.dd].sum())
    b463 = max(eps463, key=lambda e: e["cell_pnl"]) if eps463 else None
    g = {"DO": seat["DO"], "rho_dd": seat["rho_dd"], "null_DO_p95": float(np.percentile(fin, 95)) if len(fin) else float("nan"), "dd_days_usd": dd463,
         "best_episode": b463, "dd_days_usd_without_best": dd463 - (b463["cell_pnl"] if b463 else 0.0)}
    g["gate_a"] = bool(np.isfinite(g["DO"]) and g["DO"] > g["null_DO_p95"])
    g["gate_b"] = bool(g["dd_days_usd_without_best"] > 0)
    g["pass"] = g["gate_a"] and g["gate_b"]
    out = {"line": base, "book_add": add, "sd_window": [str(SEAT_WIN[0].date()), str(SEAT_WIN[1].date())], "x_dollars_on_R": onR,
           "best_R_episode": best, "x_dollars_on_R_without_best": onR - (best["x"] if best else 0.0), "null_on_R": {"p5": float(np.percentile(nR, 5)), "p50": float(np.percentile(nR, 50)), "p95": p95R},
           "R_episodes_positive": int(sum(e["x"] > 0 for e in eps)), "R_episodes": len(eps), "corr_RES_all": float(np.corrcoef(x, rs)[0, 1]), "corr_RES_on_R": float(np.corrcoef(x[SL.dd], rs[SL.dd])[0, 1]),
           "gate70": g, "episodes_R": eps}
    out["seat_earner"] = bool(onR > 0 and out["x_dollars_on_R_without_best"] > 0 and onR > p95R)
    return out


def ols_beta(y, m):
    k = np.isfinite(y) & np.isfinite(m)
    if k.sum() < 3 or np.var(m[k]) <= 0:
        return float("nan")
    return float(np.cov(y[k], m[k], ddof=1)[0, 1] / np.var(m[k], ddof=1))


def beta_checks(W, CL, run):
    """addendum 1 (1): the cell's realised beta to ES over the WF = OLS of its daily P&L per $ gross on ES's daily return (stock sessions); and the realised per-$ beta of each side over each holding
    month (WHAT COULD FOOL US (3)), averaged over the rebalances"""
    wf = (W.days >= WF0) & (W.days <= PRE_END)
    m = np.asarray(W.es.ret, float)
    cell_b = ols_beta(np.where(wf, run.x / GROSS, np.nan), m)
    cfg = D15.l1_cfg()
    side = {1: [], -1: []}
    for v in CL.recs:
        if not v.traded or not (WF0 <= W.days[v.x] <= PRE_END):
            continue
        mm = m[v.f:v.x + 1]
        for sd, idx in ((1, v.long), (-1, v.short)):
            P = D15.l1_pnl(v.U, idx, 1, cfg, W.k[v.f:v.x + 1])                 # per $1 LONG of each name: the side's own return (sign-free), so a side's beta reads as the names' beta
            side[sd].append(ols_beta(P.sum(axis=0) / len(idx), mm))
    sb = {("long" if sd > 0 else "short"): {"mean": float(np.nanmean(v)), "median": float(np.nanmedian(v)), "n": int(np.isfinite(v).sum())} for sd, v in ((s, np.array(x)) for s, x in side.items())}
    gap = sb["short"]["mean"] - sb["long"]["mean"]
    return {"cell_beta_to_es": cell_b, "credited": bool(np.isfinite(cell_b) and abs(cell_b) <= BETA_CAP), "side_beta_hold": sb, "side_gap": gap, "side_gap_flag": bool(gap > SIDE_GAP)}


def by_dates(xB, idx, lo, hi):
    k = (idx >= lo) & (idx <= hi)
    return np.asarray(xB, float)[k], idx[k]


def diagnostics(W, B, S12, rows, cell, CL, xB):
    idx = pd.DatetimeIndex(B.index)
    out = {}
    for q, (lo, hi) in enumerate(HALVES):
        x, d = by_dates(xB, idx, lo, hi)
        out[f"half_{q + 1}"] = {"from": str(lo.date()), "to": str(hi.date()), **M12.pstats(x, d)}
    z = R17.run_cell(W, CL, D15.l1_cfg(bps=0))
    out["cost_0bps_net"] = float(D15.to_B(z.x, rows, B.n)[S12.rows].sum())
    sx = pd.Series(np.asarray(xB, float), index=idx)
    sx = sx[(sx.index >= WF0) & (sx.index <= PRE_END)]
    mo = sx.groupby(sx.index.to_period("M")).sum()
    out["crash_months"] = {m_: float(mo.get(pd.Period(m_), 0.0)) for m_ in CRASH}
    out["year_2022"] = float(mo[mo.index.year == 2022].sum())
    out["episodes_463"] = D15.episodes_table(S12, xB)
    path = []
    for v in CL.recs:
        if v.traded and WF0 <= W.days[v.x] <= PRE_END:
            one = R17.SimpleNamespace(**{**vars(CL), "recs": [v]})               # this rebalance alone (keeps the cell tag, so BETA stays at its side sizes)
            path.append(np.cumsum(R17.run_cell(W, one, D15.l1_cfg()).x[v.f:v.x + 1])[:20])
    n = min(len(p) for p in path) if path else 0
    out["month_path_mean_cum_usd"] = [float(np.mean([p[k] for p in path])) for k in range(n)]
    out["sectors"] = "not shown: no SIC field on the universe file (counted, prereg WHAT COULD FOOL US (1))"
    return out


def tlt_and_tv(B, S12, SL, xB_by, side_long_vol, W):
    """addendum 1 (2): VOL's low-volatility (long) side against TLT's daily return per regime half; (3): TV's fund BAB r1 cells (K5 / K3) in the same seat frame. Both read through TV's own
    harness (tools/tvnt1_triage.py, imported read-only; every array is cut before 2025-06-30 there)"""
    sys.path.insert(0, os.path.join(REPO, "tools"))
    cwd = os.getcwd()
    import tvnt1_triage as T1
    try:
        O, C, shas = T1.load()
    finally:
        os.chdir(cwd)
    tlt = C["TLT"].pct_change()
    s = pd.Series(side_long_vol, index=W.days)
    out = {"fund_files": shas}
    for q, (lo, hi) in enumerate(HALVES):
        k = (s.index >= lo) & (s.index <= hi)
        j = pd.concat([s[k], tlt], axis=1, join="inner").dropna()
        out[f"vol_long_side_corr_TLT_half_{q + 1}"] = float(np.corrcoef(j.iloc[:, 0], j.iloc[:, 1])[0, 1]) if len(j) > 2 else float("nan")
    weeks = T1.bab_betas(O, C)
    idx = pd.DatetimeIndex(B.index)
    tv = {}
    for K in (5, 3):
        d, _ = T1.run_positions(O, C, T1.bab_signals(weeks, K))
        xB = d.reindex(idx).fillna(0.0).to_numpy(float)                       # CHOICE: a fund session date = #463's row of the same date (book row D = UTC day D holds session D)
        x = xB[SL.rows]
        eps = episodes_on(SL, x)
        best = max(eps, key=lambda e: e["x"]) if eps else None
        seat = D15.seat_measure(S12, xB)
        tv[f"BAB-K{K}"] = {"wf_net": float(x.sum()), "dollars_on_R": float(x[SL.dd].sum()), "dollars_on_R_without_best": float(x[SL.dd].sum() - (best["x"] if best else 0.0)),
                           "DO_463": seat["DO"], "corr_RES_on_R": float(np.corrcoef(x[SL.dd], np.asarray(xB_by["RES_line"], float)[SL.rows][SL.dd])[0, 1])}
    out["tv_fund_bab"] = tv
    return out


# ------------------------------------------------------------------ Stage A
def stage_a():
    psha = prereg_ok()
    os.makedirs(OUT, exist_ok=True)
    t0 = time.time()
    with bab_mode():
        out17 = R17.stage_a()
    if "obj" not in CAP or "acc" not in CAP:
        raise SystemExit("refused: the registered reading's objects were not captured (nothing judged)")
    W, B, S12, rows, obj, res = CAP["W"], CAP["B"], CAP["S12"], CAP["rows"], CAP["obj"], CAP["res"]
    resv, Lfull, gap = line_series(B)
    SL = M12.Stretch(Lfull, pd.DatetimeIndex(B.index), None, WF0, PRE_END)
    lf = figs(SL.x, SL.years)
    print(f"\nTHE LINE L = #463 + {C_RES} x RES: ROC@30k {lf['roc']:.2f} Sortino {lf['sort']:.3f} DD ${lf['mdd']:,.0f} | R = {len(SL.qual)} episodes / {SL.n_dd_days} days | "
          f"book vs RESMOM file max gap ${gap:.4f} (want 120.82 / 3.916, 45 / 762, gap < $0.01)")
    if not (abs(lf["roc"] - 120.82) <= 0.05 and abs(lf["sort"] - 3.916) <= 0.005 and len(SL.qual) == 45 and SL.n_dd_days == 762 and gap < 0.01):
        raise SystemExit("PARITY STOP: the RESMOM line does not reproduce Q19 (the Stage A file above stands; the seat read is not computed)")
    fr = {"prereg_sha256_lf": psha, "harness_sha256": hashlib.sha256(open(__file__, "rb").read()).hexdigest(), "r17_sha256": hashlib.sha256(open(R17.__file__, "rb").read()).hexdigest(),
          "line": lf, "cells": {}}
    xs = {cell: obj.series[cell][0] for cell in R17.CELLS}
    xs["RES_line"] = resv
    np.savez_compressed(os.path.join(OUT, "bab_series.npz"), book_index=pd.DatetimeIndex(B.index).strftime("%Y-%m-%d").to_numpy(), rows=np.asarray(rows), res=resv,
                        **{f"x_{NAME[c]}": np.asarray(xs[c], float) for c in R17.CELLS}, **{f"null_{NAME[c]}": CAP["acc"][c].astype(np.float32) for c in R17.CELLS})
    for cell in R17.CELLS:                                                  # each read is a report: a failure is printed and recorded, it never stops the others (the Stage A file above stands)
        nm = NAME[cell]
        CL = obj.cell_legs[cell]
        part = {}
        for key, fn in (("seat", lambda: seat_read(B, S12, SL, rows, xs[cell], CAP["acc"][cell], resv)), ("beta", lambda: beta_checks(W, CL, obj.runs[cell])),
                        ("diagnostics", lambda: diagnostics(W, B, S12, rows, cell, CL, xs[cell]))):
            try:
                with bab_mode():
                    part[key] = fn()
            except Exception as e:
                import traceback
                traceback.print_exc()
                part[key] = {"error": f"{type(e).__name__}: {e}"}
        st = res["cells"][cell]
        fr["cells"][nm] = {"stage_a_pass_before_audit": bool(st.get("PASS")), "audit": st.get("audit"), **part}
    try:
        with bab_mode():
            vl = R17.run_cell(W, obj.cell_legs["RAW"], D15.l1_cfg(), side=1).x
        fr["addendum1_2_3"] = tlt_and_tv(B, S12, SL, xs, vl, W)
    except Exception as e:                                                  # a report: its failure is printed, never a verdict
        fr["addendum1_2_3"] = {"error": f"{type(e).__name__}: {e}"}
    for cell in R17.CELLS:
        nm, c = NAME[cell], fr["cells"][NAME[cell]]
        s, b = c["seat"], c["beta"]
        if "error" in s or "error" in b or "error" in c["diagnostics"]:
            c["seat_line_eligible"] = False
            print(f"\n{nm}: Stage A {'PASS (audit pending)' if c['stage_a_pass_before_audit'] else 'FAIL'}; a FRONTIER read failed - seat {s.get('error', 'ok')}; beta {b.get('error', 'ok')}; "
                  f"diagnostics {c['diagnostics'].get('error', 'ok')} (not eligible until it is fixed and re-run)")
            continue
        credited = b["credited"] if nm == "BETA" else True
        c["seat_line_eligible"] = bool(c["stage_a_pass_before_audit"] and s["seat_earner"] and s["gate70"]["pass"] and credited)
        a = s["book_add"]
        print(f"\n{nm} (r17 slot {cell}): Stage A {'PASS (audit pending)' if c['stage_a_pass_before_audit'] else 'FAIL'}; WF net ${res['cells'][cell]['base']['net']:,.0f}, ROC@30k "
              f"{res['cells'][cell]['base']['roc']:.2f}")
        for sh, r_ in a.items():
            print(f"  book add at {sh} of L's SD (c {r_['c']:.3f}): L + cX = ROC {r_['line_plus']['roc']:.2f} / Sortino {r_['line_plus']['sort']:.3f} / DD ${r_['line_plus']['mdd']:,.0f} / "
                  f"${r_['line_plus']['ann']:,.0f} a year (L {lf['roc']:.2f} / {lf['sort']:.3f} / ${lf['ann']:,.0f}){'   <- binding (10ab)' if sh == '0.25' else ''}")
        print(f"  on R ({SL.n_dd_days} days): ${s['x_dollars_on_R']:,.0f}, without its best R episode ${s['x_dollars_on_R_without_best']:,.0f}; random-name null on R p50 / p95 "
              f"${s['null_on_R']['p50']:,.0f} / ${s['null_on_R']['p95']:,.0f}; {s['R_episodes_positive']} of {s['R_episodes']} R episodes positive; corr to RES {s['corr_RES_all']:+.3f} (on R {s['corr_RES_on_R']:+.3f})")
        g = s["gate70"]
        print(f"  #70 gate on #463's 460 days: DO {g['DO']:+.3f} vs null p95 {g['null_DO_p95']:+.3f} ({'above' if g['gate_a'] else 'not above'}); without the best #463 episode "
              f"${g['dd_days_usd_without_best']:,.0f} -> {'PASS' if g['pass'] else 'FAIL'}")
        print(f"  realised beta to ES {b['cell_beta_to_es']:+.3f} ({'within' if b['credited'] else 'OUTSIDE'} +-{BETA_CAP}); side betas over the hold long {b['side_beta_hold']['long']['mean']:.2f} / short "
              f"{b['side_beta_hold']['short']['mean']:.2f}{'  FLAG: sides differ by > 0.3' if b['side_gap_flag'] else ''}")
        dg = c["diagnostics"]
        print(f"  halves: {dg['half_1']['from']}..{dg['half_1']['to']} ROC {dg['half_1']['roc']:.1f} net ${dg['half_1']['net']:,.0f} | {dg['half_2']['from']}..{dg['half_2']['to']} ROC "
              f"{dg['half_2']['roc']:.1f} net ${dg['half_2']['net']:,.0f}; cost 0 bps net ${dg['cost_0bps_net']:,.0f}; 2022 ${dg['year_2022']:,.0f}; crash months "
              + ", ".join(f"{k} ${v:,.0f}" for k, v in dg["crash_months"].items()))
        print(f"  -> seat line eligible: {'YES (owner call; one line at most for the family)' if c['seat_line_eligible'] else 'NO'}")
    ad = fr["addendum1_2_3"]
    if "error" in ad:
        print(f"\naddendum 1 (2)/(3) not computed: {ad['error']}")
    else:
        print(f"\nVOL low-vol side corr to TLT: 2016-21 {ad['vol_long_side_corr_TLT_half_1']:+.3f}, 2022-25 {ad['vol_long_side_corr_TLT_half_2']:+.3f}")
        for k, v in ad["tv_fund_bab"].items():
            print(f"TV fund {k} in the seat frame: WF net ${v['wf_net']:,.0f}; on R ${v['dollars_on_R']:,.0f} (without its best ${v['dollars_on_R_without_best']:,.0f}); DO on #463 {v['DO_463']:+.3f}; "
                  f"corr to RES on R {v['corr_RES_on_R']:+.3f}")
    with open(os.path.join(OUT, "bab_frontier.json"), "w") as f:
        json.dump(fr, f, indent=1, default=lambda o: o.item() if hasattr(o, "item") else str(o))
    print(f"\nwritten {os.path.join(OUT, 'bab_frontier.json')} ({time.time() - t0:.0f}s in all)")
    return out17, fr


# ------------------------------------------------------------------ selftest (r17's own toy world, its registered windows; n_side 3)
def selftest():
    prereg_ok()
    n = 0
    with R17.spec(n_side=3), D15.spec(univ=14):
        W = R17.toy_world()
        r = W.days.get_loc(TS("2025-02-28"))
        uni = np.flatnonzero(W.U[r + 1])
        nr, npair, sb, sv = bab_scores(W, r, uni)
        nr0, np0, res0, raw0 = _ORIG["rm_scores"](W, r, uni)
        assert (nr == nr0).all() and (npair == np0).all(), "the counts are r17's"
        a, fa, fe = R17.windows(r)
        R, m = W.Rd[a:r + 1][:, uni], np.asarray(W.es.ret[a:r + 1], float)
        ok = np.isfinite(R) & np.isfinite(m)[:, None]
        for j in range(len(uni)):                                           # RES rebuilt from THIS beta (r17's v2 residual, alpha kept) equals r17's RES: the beta is RES's own
            if not np.isfinite(res0[j]):
                continue
            e = np.where(ok[:, j], R[:, j] - (-sb[j]) * m, np.nan)[fa - a:fe - a + 1]
            e = e[np.isfinite(e)]
            assert abs(e.sum() / np.std(e, ddof=1) - res0[j]) < 1e-9, (j, e.sum() / np.std(e, ddof=1), res0[j])
            x = R[:, j][np.isfinite(R[:, j])]
            assert abs(-sv[j] - np.std(x, ddof=1)) < 1e-12, "vol = the sample SD of the finite returns"
            n += 1
        assert n >= 8, n
        with bab_mode():
            L = R17.rm_build(W, W.days[0], W.days[-1])
            CLb, CLv = R17.cell_leg(L, "RES"), R17.cell_leg(L, "RAW")
            assert CLb.cell == "RES" and CLv.cell == "RAW"
            tr = [v for v in CLb.recs if v.traded]
            assert len(tr) >= 6, len(tr)
            for v in tr:
                b = -v.sig
                assert b[v.long].max() <= b[v.short].min() + 1e-12, "BETA longs the lowest betas, shorts the highest"
                o = np.argsort(b, kind="stable")
                assert set(b[v.long].round(12)) == set(np.sort(b)[:3].round(12)), "the 3 lowest betas are the longs"
                sL, sS, _ = side_scales(b[v.long], b[v.short])
                bl, bh = max(FLOOR, b[v.long].mean()), max(FLOOR, b[v.short].mean())
                assert abs(sL * bl - sS * bh) < 1e-12 and abs(sL + sS - 2.0) < 1e-12, "beta-neutral at the fill, gross $400k"
            for v in (w for w in CLv.recs if w.traded):
                vv = -v.sig
                assert vv[v.long].max() <= vv[v.short].min() + 1e-12, "VOL longs the calmest names"
            cfg = D15.l1_cfg()
            runb, runv = R17.run_cell(W, CLb, cfg), R17.run_cell(W, CLv, cfg)
            ref = np.zeros(W.T)
            for v in tr:
                b = -v.sig
                sL, sS, _ = side_scales(b[v.long], b[v.short])
                kt = W.k[v.f:v.x + 1]
                ref[v.f:v.x + 1] += R17.SPEC["slot"] * (sL * _ORIG["l1_pnl_x"](v.U, v.long, 1, cfg, kt).sum(axis=0) + sS * _ORIG["l1_pnl_x"](v.U, v.short, -1, cfg, kt).sum(axis=0))
            assert np.allclose(runb.x, ref, atol=1e-9), "the BETA cell = each side at its beta-neutral size"
            assert not SCALE, "the multipliers are removed after the BETA run"
            assert np.allclose(runv.x, _ORIG["run_cell"](W, CLv, cfg).x), "VOL runs at r17's $4,000 slots, unscaled"
            acc = bab_null(W, L, 40, 7)
            with D15.spec(l1_slot=R17.SPEC["slot"], l1_n=R17.SPEC["n_side"]):
                v0 = D15.null_l1(W, _ORIG["cell_leg"](L, "RAW"), 40, np.random.default_rng([R17.SEED, 22, 7]))[0]
            assert np.allclose(acc["RAW"], v0), "the VOL null is r15's null_l1 on the family's stream"
            acc2 = bab_null(W, L, 40, 7)
            assert np.allclose(acc2["RES"], acc["RES"]), "the null is reproducible on its seeds"
            assert not np.allclose(acc["RES"], 0.0)
    print(f"r19_bab selftest OK ({n} names: BETA's beta rebuilds r17's RES exactly; picks, beta-neutral sizes, VOL = r17 unscaled, the VOL null = r15's, seeds reproduce)")


def main(argv):
    cmd = argv[0] if argv else "selftest"
    if cmd == "selftest":
        selftest()
    elif cmd == "stage_a":
        selftest()
        stage_a()
    else:
        raise SystemExit(__doc__ or "usage: r19_bab.py selftest | stage_a")


if __name__ == "__main__":
    main(sys.argv[1:])
