# HIGH52 r1 (FRONTIER, book queue Q25 = scoping item B3) - the 52-week-high effect in single US stocks (George-Hwang 2004), monthly on RESMOM
# r1's engine, judged under MANAGER #127's hygiene rule S1 (r17 post_mode 'close'), read as a basket SEAT on the S1 RESMOM line, INCREMENTAL over RES.
# Pre-registered: docs/PREREG_frontier_high52_2026-10-08.txt (sha below; committed before any number).
# r17_resmom.py is IMPORTED, never copied or edited: this file swaps in only the two scores (r17's 'RES' slot carries PTH, its 'RAW' slot PTHX)
# and the family null's own streams [20261005, 25 / 26, vcode]; the universe, schedule, pool, hygiene ('close'), dividends, fills, marks, costs,
# borrow and Stage A's rules (a)-(e) are r17's code. Results go to EDGELOG_HIGH52_R1 (outside git); nothing is pulled, committed or pushed.
#   python r26_high52.py selftest    toy-world checks of the swapped pieces (r17's own toy world)
#   python r26_high52.py dryload     COUNTS only (rebalances, pools, names with both scores) - no price, score or P&L
#   python r26_high52.py power       the power line + MDE in own money from the family null ALONE (no cell P&L) -> high52_power.json
#   python r26_high52.py stage_a     WF Stage A on the 'close' reading + the seat read over the S1 L + the diagnostics -> high52_stageA.json
import hashlib, json, os, sys, time
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.environ.get("EDGELOG_ROOT", os.path.dirname(os.path.dirname(HERE)))
OUT = os.environ.get("EDGELOG_HIGH52_R1", r"C:\EdgeLog\_anatomy_cache\rocfrontier\high52_r1")
RESMOM_OUT = r"C:\EdgeLog\_anatomy_cache\rocfrontier\resmom_r1"
os.environ["EDGELOG_RESMOM_R1"] = OUT                                    # anything r17 writes lands HERE, never in RESMOM's folder
sys.path.insert(0, os.environ.get("HIGH52_R17_DIR", HERE))              # HIGH52_R17_DIR: development only (an unshipped r17); the run imports r17 from this file's folder
sys.path.insert(1, HERE)
import numpy as np, pandas as pd
import r17_resmom as R17
D15, M12, A13 = R17.D15, R17.M12, R17.A13
if "close" not in getattr(R17, "POST_MODES", ()):
    raise SystemExit("refused: this r17 has no 'close' reading ([HYG-S1]) - STRATEGY-BEATING's restatement must be on main first")
R17_SHA = "3151ef0ac6229972e897cf26634b465d87d608f0bf026215ea371058a5001f7c"   # run-before-main (MANAGER #117 / #118): SB's witness branch prereg/sb-r17-close (d873fd07), LF bytes
R17_GOT = hashlib.sha256(open(R17.__file__, "rb").read().replace(b"\r\n", b"\n")).hexdigest()
if R17_GOT != R17_SHA:
    raise SystemExit(f"refused: {R17.__file__} LF sha256 {R17_GOT[:16]}... is not the pinned r17 {R17_SHA[:16]}... (nothing computed)")
if os.path.normcase(os.path.abspath(R17.OUT)) != os.path.normcase(os.path.abspath(OUT)):
    raise SystemExit("refused: r17 was imported before EDGELOG_RESMOM_R1 pointed it at the HIGH52 folder")

TS = pd.Timestamp
PREREG = os.path.join(REPO, "docs", "PREREG_frontier_high52_2026-10-08.txt")
PREREG_SHA = "f1433cd4597b006444d3772fa34bf9bf5ddb1bbaa2f9ab5dcaaefcbf3cdd532d"   # the committed prereg's LF sha256 (the run refuses any other text)
NAME = {"RES": "PTH", "RAW": "PTHX"}
CODE = {"RES": 25, "RAW": 26}
MIN_FULL = 230                                                          # r17's full-window count (>= 230 own returns and ES pairs)
JUDGED = "close"
L_CSV = os.path.join(RESMOM_OUT, "resmom_cells_daily_wf_close.csv")
L_SHA = "e204dd53"                                                      # the S1-restated RESMOM line (STRATEGY-BEATING, 2026-10-07)
BAB_NPZ = r"C:\EdgeLog\_anatomy_cache\rocfrontier\bab_r1\bab_series.npz"
C_RES, SHARES = 0.264, (0.25, 0.10)
SEAT_WIN = (TS("2016-07-01"), TS("2018-06-29"))
HALVES = ((TS("2016-07-01"), TS("2021-12-31")), (TS("2022-01-01"), R17.PRE_END))
WF0, PRE_END = R17.WF0, R17.PRE_END
BETA_CAP = 0.20
STRESS_DECIDES = "10 bps"                                               # r17's own stress check (b), unchanged for this family
POWER_JSON = os.path.join(OUT, "high52_power.json")
POWER_DOC = os.path.join(REPO, "docs", "PREREG_frontier_high52_2026-10-08_power.txt")
_ORIG = {k: getattr(R17, k) for k in ("rm_scores", "rm_null")}
CAP = {}


def pins(psha, extra=None):
    """the run log's first lines (run-before-main rule (3)): every pinned hash this run checked"""
    print(f"PINS: prereg LF sha256 {psha}; harness sha256 {hashlib.sha256(open(__file__, 'rb').read()).hexdigest()}; r17 LF sha256 {R17_GOT} ({R17.__file__})"
          + (f"; power {extra}" if extra else ""), flush=True)


def prereg_ok():
    got = hashlib.sha256(open(PREREG, "rb").read().replace(b"\r\n", b"\n")).hexdigest()
    if not PREREG_SHA or got != PREREG_SHA:
        raise SystemExit(f"refused: {PREREG} reads {got[:16]}..., the registered sha is {PREREG_SHA[:16] or 'not set'} (nothing computed)")
    return got


# ------------------------------------------------------------------ the two scores
def pth_of(W, r, uni):
    """PTH = the split-safe PRICE index at the rank close / its highest close over the 252-session window r-251 .. r. The index is the product of
    (1 + the split-safe price return, no dividends: W.Rn0) - a [D2] spin-off / stock-dividend ex-date session (NaN there) counts as 0, so the
    spun-off value never reads as a fall from the high. NaN for a name with no finite return in the window"""
    a = R17.windows(r)[0]
    R = W.Rn0[a:r + 1][:, uni]
    fin = np.isfinite(R)
    I = np.cumprod(np.where(fin, 1.0 + R, 1.0), axis=0)
    with np.errstate(invalid="ignore", divide="ignore"):
        p = I[-1] / I.max(axis=0)
    return np.where(fin.any(axis=0), p, np.nan)


def high52_scores(W, r, uni):
    """-> (n_ret, n_pair, PTH, PTHX) for the names `uni` at the rank session r (r17.rm_scores's shape; the counts are r17's own, so the pool rules are
    RESMOM's). PTHX (MANAGER #116 (1): take out what L already holds) = the residual of a cross-sectional OLS of PTH on an intercept, r17's RAW
    (the 12-1 split-safe total return) AND r17's RES (RESMOM's residual-momentum score - the one L carries), over the names with a full window
    (both counts >= 230) and all three values finite; NaN elsewhere (such a name is out of the pool anyway)"""
    n_ret, n_pair, res, raw = _ORIG["rm_scores"](W, r, uni)
    pth = pth_of(W, r, uni)
    k = (n_ret >= MIN_FULL) & (n_pair >= MIN_FULL) & np.isfinite(pth) & np.isfinite(raw) & np.isfinite(res)
    pthx = np.full(len(uni), np.nan)
    if k.sum() > 3:
        X = np.column_stack([np.ones(int(k.sum())), raw[k], res[k]])
        beta = np.linalg.lstsq(X, pth[k], rcond=None)[0]
        pthx[k] = pth[k] - X @ beta
    return n_ret, n_pair, np.where(k, pth, np.nan), pthx


def high52_null(W, L, nreps, vcode=0):
    """r15's null_l1 per cell (r17.rm_null's draw) on this family's streams [20261005, 23 / 24, vcode]"""
    acc = {}
    with D15.spec(l1_slot=R17.SPEC["slot"], l1_n=R17.SPEC["n_side"]):
        for cell in R17.CELLS:
            acc[cell] = D15.null_l1(W, R17.cell_leg(L, cell), nreps, np.random.default_rng([R17.SEED, CODE[cell], vcode]))[0]
    if vcode == 0:
        CAP["acc"] = acc
    return acc


class high52_mode:
    def __enter__(self):
        self.cm = R17.patched(R17, rm_scores=high52_scores, rm_null=high52_null)
        return self.cm.__enter__()

    def __exit__(self, *a):
        return self.cm.__exit__(*a)


# ------------------------------------------------------------------ the reads (house definitions: BOOK.md 10ab via the seat pipeline's arithmetic)
def figs(x, years):
    m = M12.vmeas(np.asarray(x, float)[None, :], years)
    return {k: float(m[k][0]) for k in ("roc", "sort", "mdd", "net", "ann")}


def dd5_of(x, dates):
    from augur_engine.drawdowns import dd5
    r = dd5(pd.Series(np.asarray(x, float), index=pd.DatetimeIndex(dates)))
    return {"dd5": r["dd5_usd"], "one_episode": bool(r["one_episode"]), "max_dd": r["max_dd"]}


def seat_read(B, S12, SL, rows, xB, acc_cell, res_line, others):
    x = np.asarray(xB, float)[SL.rows]
    Lx, rs = SL.x, np.asarray(res_line, float)[SL.rows]
    d = SL.dates
    w = (d >= SEAT_WIN[0]) & (d <= SEAT_WIN[1])
    sdx, sdl = float(np.std(x[w], ddof=1)), float(np.std(Lx[w], ddof=1))
    out = {"line": figs(Lx, SL.years), "book_add": {}}
    for sh in SHARES:
        c = sh * sdl / sdx if sdx > 0 else float("nan")
        out["book_add"][f"{sh:.2f}"] = {"c": c, "line_plus": {**figs(Lx + c * x, SL.years), **dd5_of(Lx + c * x, d)} if np.isfinite(c) else {"error": "the seat has no variance in the sizing window"}}
    eps = [{"first": f"{d[e['i0']]:%Y-%m-%d}", "trough": e["trough"], "x": float(x[e["i0"]:e["it"] + 1].sum())} for e in SL.qual]
    onR = float(x[SL.dd].sum())
    best = max(eps, key=lambda e: e["x"]) if eps else None
    Y = np.zeros((acc_cell.shape[0], B.n))
    Y[:, rows] = acc_cell
    nR = Y[:, SL.rows][:, SL.dd].sum(axis=1)
    seat = D15.seat_measure(S12, xB)
    do_n = np.asarray(D15.null_cell(S12, acc_cell, rows, B.n)[2], float)
    fin = do_n[np.isfinite(do_n)]
    e463 = D15.episodes_table(S12, xB)
    dd463 = float(np.asarray(xB, float)[S12.rows][S12.dd].sum())
    b463 = max(e463, key=lambda e: e["cell_pnl"]) if e463 else None
    g = {"DO": seat["DO"], "null_DO_p95": float(np.percentile(fin, 95)) if len(fin) else float("nan"), "dd_days_usd": dd463,
         "dd_days_usd_without_best": dd463 - (b463["cell_pnl"] if b463 else 0.0)}
    g["pass"] = bool(np.isfinite(g["DO"]) and g["DO"] > g["null_DO_p95"] and g["dd_days_usd_without_best"] > 0)
    out.update({"x_on_R": onR, "x_on_R_without_best": onR - (best["x"] if best else 0.0), "best_R_episode": best,
                "null_on_R": {"p50": float(np.percentile(nR, 50)), "p95": float(np.percentile(nR, 95))},
                "R_episodes_positive": int(sum(e["x"] > 0 for e in eps)), "R_episodes": len(eps), "gate70": g,
                "corr_RES_all": float(np.corrcoef(x, rs)[0, 1]), "corr_RES_on_R": float(np.corrcoef(x[SL.dd], rs[SL.dd])[0, 1])})
    for nm, o in others.items():
        oo = np.asarray(o, float)[SL.rows]
        out[f"corr_{nm}_on_R"] = float(np.corrcoef(x[SL.dd], oo[SL.dd])[0, 1])
    out["seat_earner"] = bool(onR > 0 and out["x_on_R_without_best"] > 0 and onR > out["null_on_R"]["p95"])
    return out


def ols_beta(y, m):
    k = np.isfinite(y) & np.isfinite(m)
    return float(np.cov(y[k], m[k], ddof=1)[0, 1] / np.var(m[k], ddof=1)) if k.sum() > 2 and np.var(m[k]) > 0 else float("nan")


def crash_months(B, xB):
    """each cell's net in RESMOM's named momentum-crash months (r17.CRASH_MONTHS), from #463's rows"""
    mn = R17.month_nets(B, xB, WF0, PRE_END)
    return {m: mn.get(m, 0.0) for m in R17.CRASH_MONTHS}


def diagnostics(W, B, S12, rows, L, cell, CL, run, xB, res_cell):
    idx = pd.DatetimeIndex(B.index)
    out = {}
    for q, (lo, hi) in enumerate(HALVES):
        k = (idx >= lo) & (idx <= hi)
        out[f"half_{q + 1}"] = {"from": str(lo.date()), "to": str(hi.date()), **M12.pstats(np.asarray(xB, float)[k], idx[k])}
    out["cost_0bps_net"] = float(D15.to_B(R17.run_cell(W, CL, D15.l1_cfg(bps=0)).x, rows, B.n)[S12.rows].sum())
    out["cost_net"] = {"0": out["cost_0bps_net"], "5": res_cell["base"]["net"], **{k.split()[0]: v["net"] for k, v in res_cell["stress"].items()}}
    wf = (W.days >= WF0) & (W.days <= PRE_END)
    out["beta_to_es"] = ols_beta(np.where(wf, run.x / (2 * R17.SPEC["n_side"] * R17.SPEC["slot"]), np.nan), np.asarray(W.es.ret, float))
    out["beta_credited"] = bool(np.isfinite(out["beta_to_es"]) and abs(out["beta_to_es"]) <= BETA_CAP)
    out["by_wf_year"] = res_cell["base"].get("by_year")
    out["crash_months"] = crash_months(B, xB)
    out["turnover"] = R17.turnover(L, cell)
    out["episodes_463"] = D15.episodes_table(S12, xB)
    return out


# ------------------------------------------------------------------ dryload (COUNTS only: no price, return, score or P&L is printed)
def load_world():
    cal, _ = R17.wide_load(R17.S.LB0)
    D = R17.load_data(R17.S.LB0)
    tbis = D15.load_tbis(R17.S.LB0)
    es_frames, _ = D15.load_es(R17.S.LB0)
    W = R17.build_world(D, R17.S.LB0, es_frames, tbis, cal)
    D15.release(D)
    aud = R17.read_audit(os.path.join(RESMOM_OUT, "resmom_audit.csv"))       # RESMOM's hand-audit data events (same data, same name-months), if any
    R17.apply_audit(W, aud)
    csi = R17.attach_calendar_splits(W, cal)
    return W, aud, csi


def dryload():
    pins(prereg_ok())
    t0 = time.time()
    W, aud, csi = load_world()
    print(f"dryload: world ready ({time.time() - t0:.0f}s); sessions {W.T:,} ({W.days[0]:%Y-%m-%d} .. {W.days[-1]:%Y-%m-%d}); calendar splits on the grid: {csi}; RESMOM audit rows: {0 if aud is None else len(aud)}")
    with high52_mode():
        L = R17.rm_build(W, WF0, PRE_END, JUDGED, units=False)
    by = {}
    for rec in L.recs:
        uni = np.flatnonzero(W.U[rec.f])
        nr, npair, pth, pthx = high52_scores(W, rec.r, uni) if len(uni) else (np.zeros(0),) * 4
        by.setdefault(int(W.days[rec.f].year), []).append((len(uni), int(np.isfinite(pthx).sum()), len(rec.pool), bool(rec.traded)))
    print(f"rebalances: {len(L.recs)} in WF, {sum(r.traded for r in L.recs)} traded (pool >= 2 x {R17.SPEC['n_side']}); first fill {W.days[L.recs[0].f]:%Y-%m-%d}" if L.recs else "rebalances: none")
    for y, v in sorted(by.items()):
        a = np.array(v, float)
        print(f"  fill year {y}: {len(v)} rebalances, {int(a[:, 3].sum())} traded; universe {a[:, 0].mean():.0f}; names with both scores {a[:, 1].min():.0f}-{a[:, 1].mean():.0f}-{a[:, 1].max():.0f}; "
              f"pool {a[:, 2].min():.0f}-{a[:, 2].mean():.0f}-{a[:, 2].max():.0f}")
    R17.print_counts(f"the '{JUDGED}' reading", L.cnt)
    print(f"dryload took {time.time() - t0:.0f}s")


# ------------------------------------------------------------------ the power line (MANAGER #115 (1)): from the family null ALONE, before any cell P&L
def shift_to(Y, active, years, bar, q):
    """the smallest daily drift mu ($ a day on the active rows) such that the q-th percentile of the draws' ROC @ $30k reaches the bar (bisection)"""
    def at(mu):
        Z = Y + mu * active[None, :]
        return float(np.nanpercentile(M12.vmeas(Z, years)["roc"], q))
    lo, hi = 0.0, 50.0
    while at(hi) < bar:
        hi *= 2.0
        if hi > 1e7:
            return float("nan")
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        lo, hi = (mid, hi) if at(mid) < bar else (lo, mid)
    return hi


def power_read(B, S12, SL, rows, acc):
    """-> the bar a cell must clear (the MAX-over-cells null p95 and ROC >= 15) and, per cell, the true edge it needs to clear it half the time
    (50% power) and four times in five (80%): as a daily drift added to the null's random books on the cell's active rows, in $ a year at the
    cell's own size and as the ROC @ $30k it buys ($ a year at a $30k worst drawdown = ROC x $1,000). The seat line: the null's dollars on R
    (L's drawdown days) - p50 / p95 / SD - and the lead on R a seat needs (p95 - p50 at 50% power; + 0.842 SD at 80%)"""
    per = {cell: D15.null_cell(S12, acc[cell], rows, B.n)[0] for cell in R17.CELLS}
    nul = R17.null_summary(per)
    bar = max(R17.RULES["roc"], nul["roc_max"]["p95"])
    out = {"draws": nul["draws"], "null": nul, "bar_roc": bar, "bar_rule": f"ROC @ $30k >= max(15, the null's MAX-over-cells p95 {nul['roc_max']['p95']:.2f})", "cells": {}}
    for cell in R17.CELLS:
        Y = np.zeros((acc[cell].shape[0], B.n))
        Y[:, rows] = acc[cell]
        Yw = Y[:, S12.rows]
        live = np.flatnonzero(np.abs(Yw).sum(axis=0) > 0)
        active = np.zeros(Yw.shape[1])
        if len(live):
            active[live[0]:live[-1] + 1] = 1.0
        m50, m80 = shift_to(Yw, active, S12.years, bar, 50), shift_to(Yw, active, S12.years, bar, 20)
        per_yr = lambda mu: float(mu * active.sum() / S12.years)
        YL = Y[:, SL.rows]
        onR = YL[:, SL.dd].sum(axis=1)
        p50, p95, sd = float(np.percentile(onR, 50)), float(np.percentile(onR, 95)), float(np.std(onR, ddof=1))
        d = SL.dates
        w = (d >= SEAT_WIN[0]) & (d <= SEAT_WIN[1])
        sdx = np.std(YL[:, w], axis=1, ddof=1)
        c_med = float(np.median(SHARES[0] * np.std(SL.x[w], ddof=1) / sdx[sdx > 0])) if (sdx > 0).any() else float("nan")
        out["cells"][NAME[cell]] = {
            "null_roc": nul["by_cell"][cell], "active_days": int(active.sum()),
            "mde50_usd_per_year_own_size": per_yr(m50), "mde80_usd_per_year_own_size": per_yr(m80),
            "mde50_usd_per_year_at_30k": bar * 1000.0, "mde80_note": "80% power: the drift at which four draws in five clear the bar",
            "null_on_R": {"p50": p50, "p95": p95, "sd": sd}, "seat_mde50_on_R_own_size": p95 - p50, "seat_mde80_on_R_own_size": p95 - p50 + 0.842 * sd,
            "seat_c_at_0.25_median_over_draws": c_med, "seat_mde50_on_R_at_0.25": (p95 - p50) * c_med, "seat_mde80_on_R_at_0.25": (p95 - p50 + 0.842 * sd) * c_med}
    return out


def load_line(B):
    SL, res_line, lf = load_line(B)
    idx = pd.DatetimeIndex(B.index)
    others = {}
    if os.path.exists(BAB_NPZ):
        z = np.load(BAB_NPZ, allow_pickle=True)
        bi = pd.to_datetime(z["book_index"])
        for nm in ("BETA", "VOL"):
            others[f"BAB_{nm}"] = pd.Series(z[f"x_{nm}"], index=bi).reindex(idx).fillna(0.0).to_numpy(float)
    fr = {"prereg_sha256_lf": psha, "harness_sha256": hashlib.sha256(open(__file__, "rb").read()).hexdigest(), "r17_sha256": hashlib.sha256(open(R17.__file__, "rb").read()).hexdigest(),
          "judged_reading": JUDGED, "line": lf, "null": res["null"], "power": pgate, "stress_decides": STRESS_DECIDES, "cells": {}}
    for cell in R17.CELLS:
        nm, c, CL, run = NAME[cell], res["cells"][cell], obj.cell_legs[cell], obj.runs[cell]
        xB = obj.series[cell][0]
        d5 = dd5_of(np.asarray(xB, float)[S12.rows], S12.dates)
        chk = {k: v for k, v in c["checks"].items() if k != "net>0 at 10 bps"}
        chk[f"net>0 at {STRESS_DECIDES}"] = bool(c["stress"][STRESS_DECIDES]["net"] > 0)       # r17's own check, kept
        part = {"stage_a": {"PASS": bool(all(chk.values())), "checks": chk, "r17_checks": c["checks"], "base": c["base"], "stress": c["stress"], "sides": c.get("sides"), "dd5": d5}}
        for key, fn in (("seat", lambda: seat_read(B, S12, SL, rows, xB, CAP["acc"][cell], res_line, others)),
                        ("diagnostics", lambda: diagnostics(W, B, S12, rows, obj.legs, cell, CL, run, xB, c))):
            try:
                with high52_mode():
                    part[key] = fn()
            except Exception as e:
                import traceback
                traceback.print_exc()
                part[key] = {"error": f"{type(e).__name__}: {e}"}
        fr["cells"][nm] = part
        pos = getattr(run, "pos", None)
        if pos is not None and len(pos.pnl):
            o = np.argsort(-pos.pnl)[:R17.AUDIT_N]
            pd.DataFrame({"symbol": np.asarray(W.syms)[pos.col[o]], "fill": [f"{W.days[CL.recs[int(i)].f]:%Y-%m-%d}" for i in pos.rec[o]], "side": pos.side[o], "pnl": pos.pnl[o]}).to_csv(
                os.path.join(OUT, f"high52_audit_candidates_{nm}.csv"), index=False)
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "high52_stageA.json"), "w") as f:
        json.dump(fr, f, indent=1, default=lambda o: o.item() if hasattr(o, "item") else str(o))
    print(f"\nHIGH52 r1 Stage A ('{JUDGED}' reading, WF; null p95 MAX over the 2 cells {res['null']['roc_max']['p95']:.2f}):")
    for nm, p in fr["cells"].items():
        st = p["stage_a"]
        b = st["base"]
        print(f"  {nm}: ROC@30k {b['roc']:.2f} / DD5 ${st['dd5']['dd5']:,.0f}{' (ONE EPISODE)' if st['dd5']['one_episode'] else ''} | Sortino {b['sortino']:.3f} | worst DD ${b['max_dd']:,.0f} | net ${b['net']:,.0f} | "
              f"Stage A {'PASS (audit pending)' if st['PASS'] else 'FAIL'}" + ("" if st["PASS"] else " - fails " + ", ".join(k for k, v in st["checks"].items() if not v)))
        s = p.get("seat", {})
        if "error" not in s:
            a = s["book_add"]["0.25"]["line_plus"]
            print(f"     seat (report): L + cX at 0.25 = {a['roc']:.2f} / DD5 ${a['dd5']:,.0f} (L {lf['roc']:.2f}); on R ${s['x_on_R']:,.0f} (without best ${s['x_on_R_without_best']:,.0f}; null p95 "
                  f"${s['null_on_R']['p95']:,.0f}); #70 gate {'PASS' if s['gate70']['pass'] else 'FAIL'}; corr RES {s['corr_RES_all']:+.3f}, on R {s['corr_RES_on_R']:+.3f}"
                  + (" = THE SAME SEAT AS RES (corr on R > 0.7)" if s['corr_RES_on_R'] > 0.7 else ""))
        dg = p.get("diagnostics", {})
        if "error" not in dg:
            print(f"     beta to ES {dg['beta_to_es']:+.3f}; halves ROC {dg['half_1']['roc']:.1f} / {dg['half_2']['roc']:.1f}; cost nets {dg['cost_net']} with turnover {dg['turnover'].get('replaced_mean', float('nan')):.0%} of names a month; crash months {dg['crash_months']}")
    print(f"written {os.path.join(OUT, 'high52_stageA.json')} ({time.time() - t0:.0f}s)")
    return fr


# ------------------------------------------------------------------ selftest (r17's toy world; n_side 3)
def selftest():
    with R17.spec(n_side=3), D15.spec(univ=14):
        W = R17.toy_world()
        n = 0
        for r in range(251, W.T - 1, 17):
            uni = np.flatnonzero(W.U[r + 1])
            if not len(uni):
                continue
            nr, npair, pth, pthx = high52_scores(W, r, uni)
            nr0, np0, res, raw = _ORIG["rm_scores"](W, r, uni)
            assert (nr == nr0).all() and (npair == np0).all(), "the pool counts are r17's"
            for j, c in enumerate(uni):                                        # PTH by brute force: the price level walked forward, the window's highest close
                lvl, hi = 1.0, -np.inf
                for t in range(r - 251, r + 1):
                    v = W.Rn0[t, c]
                    lvl *= 1.0 + (v if np.isfinite(v) else 0.0)
                    hi = max(hi, lvl)
                full = nr[j] >= MIN_FULL and npair[j] >= MIN_FULL and np.isfinite(raw[j]) and np.isfinite(res[j])
                want = lvl / hi if full and np.isfinite(W.Rn0[r - 251:r + 1, c]).any() else np.nan
                assert (np.isnan(want) and np.isnan(pth[j])) or abs(want - pth[j]) < 1e-12, (r, j, want, pth[j])
                assert np.isnan(pth[j]) or 0.0 < pth[j] <= 1.0 + 1e-12
                n += 1
            k = np.isfinite(pthx)
            if k.sum() > 3:                                                     # the residual: mean zero and orthogonal to BOTH RAW and RES over the names it covers
                assert abs(pthx[k].mean()) < 1e-10
                assert abs(np.dot(pthx[k], raw[k] - raw[k].mean())) < 1e-9 and abs(np.dot(pthx[k], res[k] - res[k].mean())) < 1e-9, "PTHX orthogonal to RAW and RES"
        assert n >= 10, n
        with high52_mode():
            L = R17.rm_build(W, W.days[0], W.days[-1], JUDGED)
            tr = [v for v in R17.cell_leg(L, "RES").recs if v.traded]
            assert len(tr) >= 3, len(tr)
            for v in tr:
                assert v.sig[v.long].min() >= v.sig[v.short].max() - 1e-12, "longs = the highest scores"
            acc = high52_null(W, L, 30, 7)
            with D15.spec(l1_slot=R17.SPEC["slot"], l1_n=R17.SPEC["n_side"]):
                ref = D15.null_l1(W, R17.cell_leg(L, "RAW"), 30, np.random.default_rng([R17.SEED, 26, 7]))[0]
            assert np.allclose(acc["RAW"], ref), "the PTHX null is r15's null_l1 on the family stream"
        B, S12 = R17.synth_book(seed=15)
        rows = A13.book_rows(B, W)
        with high52_mode(), R17.patched(R17, A2_WIN=(TS("2024-12-02"), TS("2025-05-30"))), R17.patched(sys.modules[__name__], SEAT_WIN=(TS("2025-01-01"), TS("2025-06-27"))):
            res, obj = R17.evaluate(W, B, S12, rows, JUDGED, 20, 0, full=True)
            assert res["null"]["draws"] == 20 and set(CAP["acc"]) == set(R17.CELLS)
            rng = np.random.default_rng(5)
            res_line = rng.normal(0.0, 300.0, B.n)
            SL = M12.Stretch(np.asarray(B.raw, float) + C_RES * res_line, pd.DatetimeIndex(B.index), None, WF0, PRE_END)
            for cell in R17.CELLS:
                CL, run, c = obj.cell_legs[cell], obj.runs[cell], res["cells"][cell]
                xB = obj.series[cell][0]
                dg = diagnostics(W, B, S12, rows, obj.legs, cell, CL, run, xB, c)
                assert set(dg["crash_months"]) == set(R17.CRASH_MONTHS)
                assert dg["turnover"]["traded_rebalances"] == sum(v.traded for v in CL.recs)
                assert abs(dg["cost_net"]["5"] - c["base"]["net"]) < 1e-9 and np.isfinite(dg["beta_to_es"])
                sr = seat_read(B, S12, SL, rows, xB, CAP["acc"][cell], res_line, {"BAB_BETA": rng.normal(0.0, 50.0, B.n)})
                assert set(sr["book_add"]) == {"0.25", "0.10"} and "dd5" in sr["book_add"]["0.25"]["line_plus"] and isinstance(sr["gate70"]["pass"], bool)
            pw = power_read(B, S12, SL, rows, CAP["acc"])
            assert pw["bar_roc"] >= 15.0 and set(pw["cells"]) == set(NAME.values())
            for nm, cpw in pw["cells"].items():
                assert np.isfinite(cpw["mde50_usd_per_year_own_size"]) and cpw["mde80_usd_per_year_own_size"] >= cpw["mde50_usd_per_year_own_size"] - 1e-6
    print(f"r26_high52 selftest OK ({n} name-ranks: PTH by brute force in (0, 1], PTHX mean-zero and orthogonal to RAW and RES, longs = highest scores, the null on its stream; "
          f"the '{JUDGED}' Stage A + seat read + diagnostics + power read run end to end on the toy world)")


def main(argv):
    cmd = argv[0] if argv else "selftest"
    if cmd == "selftest":
        selftest()
    elif cmd == "power":
        selftest()
        power()
    elif cmd == "dryload":
        dryload()
    elif cmd == "stage_a":
        selftest()
        stage_a()
    else:
        raise SystemExit("usage: r26_high52.py selftest | dryload | power | stage_a")


if __name__ == "__main__":
    main(sys.argv[1:])
