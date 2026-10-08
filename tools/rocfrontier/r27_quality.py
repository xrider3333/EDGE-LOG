# QUALITY r1 (FRONTIER, book queue Q26 = scoping item B6) - gross profitability (Novy-Marx 2013) and operating profitability in single US stocks,
# monthly on RESMOM r1's engine, judged under MANAGER #127's hygiene rule S1 (r17 post_mode 'close'), read as a basket SEAT on the S1 RESMOM line.
# Pre-registered: docs/PREREG_frontier_quality_2026-10-08.txt (sha below; committed before any number); data = SEC companyfacts as filed (held).
# r17_resmom.py is IMPORTED, never copied or edited: this file swaps in only the two scores (r17's 'RES' slot carries GPA, its 'RAW' slot OPA)
# and the family null's own streams [20261005, 27 / 28, vcode]; the universe, schedule, pool, hygiene ('close'), dividends, fills, marks, costs,
# borrow and Stage A's rules (a)-(e) are r17's code. Results go to EDGELOG_QUALITY_R1 (outside git); nothing is pulled, committed or pushed.
#   python r27_quality.py selftest    the facts table on hand-made filings + toy-world checks of the swapped pieces
#   python r27_quality.py dryload     COUNTS only (rebalances, names with a score, stale / scale counts by year) - no price, score or P&L
#   python r27_quality.py power       the power line + MDE in own money from the family null ALONE (no cell P&L) -> quality_power.json
#   python r27_quality.py stage_a     WF Stage A on the 'close' reading + the seat read over the S1 L + the diagnostics -> quality_stageA.json
import hashlib, json, os, sys, time
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.environ.get("EDGELOG_ROOT", os.path.dirname(os.path.dirname(HERE)))
OUT = os.environ.get("EDGELOG_QUALITY_R1", r"C:\EdgeLog\_anatomy_cache\rocfrontier\quality_r1")
RESMOM_OUT = r"C:\EdgeLog\_anatomy_cache\rocfrontier\resmom_r1"
os.environ["EDGELOG_RESMOM_R1"] = OUT                                    # anything r17 writes lands HERE, never in RESMOM's folder
sys.path.insert(0, os.environ.get("QUALITY_R17_DIR", HERE))             # QUALITY_R17_DIR: development only (an unshipped r17); the run imports r17 from this file's folder
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
    raise SystemExit("refused: r17 was imported before EDGELOG_RESMOM_R1 pointed it at the QUALITY folder")

TS = pd.Timestamp
PREREG = os.path.join(REPO, "docs", "PREREG_frontier_quality_2026-10-08.txt")
PREREG_SHA = "b31ced3bb9a617c3e8384cbd4df5b026593b1198506d26666a48d4d4a47541f4"   # the committed prereg's LF sha256 (the run refuses any other text)
NAME = {"RES": "GPA", "RAW": "OPA"}
CODE = {"RES": 27, "RAW": 28}
FACTS = {"income": (os.path.join(OUT, "data", "income_asfiled_wide.csv"), "e142ef058ab97bd2916ceb9fa59692f6bfdf71444b44a6833658349663dc01b3"),
         "assets": (os.path.join(OUT, "data", "assets_asfiled_wide.csv"), "83c099bda27a0842e8f1044cf3344efae43861869079b10c7ea9165543f74ac0")}
QT = {}                                                                 # the annual table, symbol -> cik, and the per-rank score cache
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
POWER_JSON = os.path.join(OUT, "quality_power.json")
POWER_DOC = os.path.join(REPO, "docs", "PREREG_frontier_quality_2026-10-08_power.txt")
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


# ------------------------------------------------------------------ the facts table (point in time; q6tools/quality_facts.py, selftested there and below)
REV = ["us-gaap:Revenues", "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax", "us-gaap:RevenueFromContractWithCustomerIncludingAssessedTax",
       "us-gaap:SalesRevenueNet", "us-gaap:SalesRevenueGoodsNet"]
COGS = ["us-gaap:CostOfRevenue", "us-gaap:CostOfGoodsAndServicesSold", "us-gaap:CostOfGoodsSold",
        "us-gaap:CostOfGoodsAndServiceExcludingDepreciationDepletionAndAmortization"]
GP, OI, ASSETS = "us-gaap:GrossProfit", "us-gaap:OperatingIncomeLoss", "us-gaap:Assets"
ANNUAL_FORMS = ("10-K", "10-K/A")
DUR = (350, 380)
STALE_DAYS = 548                                             # 18 months
MAX_ABS = 3.0


def dt(s):
    return pd.to_datetime(s, errors="coerce", format="%Y-%m-%d")


def first_filed(F, keys):
    """one row per key (e.g. cik, concept, start, end): the value of its EARLIEST filing (ties: the lowest accession number) and that date"""
    F = F.sort_values(["filed", "accn"], kind="mergesort")
    return F.drop_duplicates(keys, keep="first")


def annual_income(inc):
    """the income extract -> one row per (cik, concept, fiscal year end): the first-filed annual value and its first filed date"""
    x = inc.copy()
    x["start"], x["end"], x["filed"] = dt(x["start"]), dt(x["end"]), dt(x["filed"])                       # an impossible date (e.g. year 0202) = NaT = not annual
    dur = (x["end"] - x["start"]).dt.days
    x = x[x["form"].isin(ANNUAL_FORMS) & (x["fp"] == "FY") & dur.between(*DUR) & x["filed"].notna() & np.isfinite(pd.to_numeric(x["val"], errors="coerce"))]
    x["val"] = pd.to_numeric(x["val"])
    return first_filed(x, ["cik", "concept", "end"])[["cik", "symbols", "concept", "end", "val", "filed"]]


def point_assets(ast):
    x = ast[ast["concept"] == ASSETS].copy()
    x["end"], x["filed"] = dt(x["end"]), dt(x["filed"])
    x = x[x["start"].isna() | (x["start"] == "")] if "start" in x else x
    x = x[x["end"].notna() & x["filed"].notna()]
    x["val"] = pd.to_numeric(x["val"], errors="coerce")
    x = x[np.isfinite(x["val"])]
    return first_filed(x, ["cik", "end"])[["cik", "end", "val", "filed"]]


def annual_table(inc, ast):
    """-> one row per (cik, fiscal year end E): gpa, opa, their usable dates (the latest first-filed date of their parts), the GP source
    ('reported' / 'rev-cogs'), symbols. NaN where a part is missing or assets <= 0; |score| > 3 -> NaN, flagged 'scale'"""
    A = annual_income(inc)
    S = point_assets(ast).rename(columns={"val": "assets", "filed": "f_assets"})
    piv = {c: g.set_index(["cik", "end"])[["val", "filed"]] for c, g in A.groupby("concept")}
    keys = A[["cik", "end"]].drop_duplicates().set_index(["cik", "end"]).index
    out = pd.DataFrame(index=keys)
    out["symbols"] = A.drop_duplicates(["cik", "end"]).set_index(["cik", "end"])["symbols"]

    def pick(order):
        v = pd.Series(np.nan, index=keys)
        f = pd.Series(pd.NaT, index=keys, dtype="datetime64[ns]")
        for c in order:
            if c in piv:
                p = piv[c].reindex(keys)
                take = v.isna() & p["val"].notna()
                v[take], f[take] = p["val"][take], p["filed"][take]
        return v, f

    gp_r, f_gpr = pick([GP])
    rev, f_rev = pick(REV)
    cogs, f_cogs = pick(COGS)
    oi, f_oi = pick([OI])
    gp = gp_r.where(gp_r.notna(), rev - cogs)
    f_gp = f_gpr.where(gp_r.notna(), pd.concat([f_rev, f_cogs], axis=1).max(axis=1, skipna=False))
    out["gp_source"] = np.where(gp_r.notna(), "reported", np.where(gp.notna(), "rev-cogs", ""))
    S = S.set_index(["cik", "end"]).reindex(keys)
    ok_a = S["assets"] > 0
    for nm, num, fn in (("gpa", gp, f_gp), ("opa", oi, f_oi)):
        sc = (num / S["assets"]).where(ok_a)
        out[nm + "_scale"] = sc.abs() > MAX_ABS
        out[nm] = sc.where(~out[nm + "_scale"])
        out[nm + "_usable"] = pd.concat([fn, S["f_assets"]], axis=1).max(axis=1, skipna=False).where(out[nm].notna())
    return out.reset_index()


def score_at(T, d, col):
    """the scores known at a rank date d -> {cik: (score, fiscal year end, usable date)}: per cik the latest fiscal year whose `col` is usable
    strictly before d and whose year ended no more than 18 months before d"""
    k = T[col + "_usable"].notna() & (T[col + "_usable"] < d) & (T["end"] >= d - pd.Timedelta(days=STALE_DAYS))
    t = T[k].sort_values("end").drop_duplicates("cik", keep="last")
    return {r.cik: (float(getattr(r, col)), r.end, getattr(r, col + "_usable")) for r in t.itertuples()}


def load_facts():
    """the two pinned extracts -> the annual table + symbol -> cik (a symbol on several CIKs over time: the CIK whose facts cover the rank is used
    through the table itself - each CIK row carries its ';' symbol list)"""
    kw = dict(dtype={c: str for c in ("cik", "accn", "fp", "form", "start", "end", "filed", "symbols", "frame")})
    parts = {}
    for k, (p, h) in FACTS.items():
        got = hashlib.sha256(open(p, "rb").read()).hexdigest()
        if got != h:
            raise SystemExit(f"refused: {p} sha256 {got[:16]}... is not the pinned {h[:16]}... (nothing computed)")
        parts[k] = pd.read_csv(p, **kw)
    set_table(annual_table(parts["income"], parts["assets"]))
    return {k: len(v) for k, v in parts.items()}


def set_table(T):
    s2c = {}
    for cik, sy in T[["cik", "symbols"]].drop_duplicates().itertuples(index=False):
        for x in str(sy).split(";"):
            if x and x != "nan":
                s2c.setdefault(x, set()).add(cik)
    QT.clear()
    QT.update(T=T, s2c=s2c, cache={})


def scores_on(W, r):
    """-> (gpa, opa) over ALL of W's symbols at the rank session r (NaN = no usable score); a symbol on several CIKs with a usable score = NaN (counted)"""
    if r in QT["cache"]:
        return QT["cache"][r]
    d = pd.Timestamp(W.days[r])
    out = []
    for col in ("gpa", "opa"):
        sc = score_at(QT["T"], d, col)
        v = np.full(len(W.syms), np.nan)
        for j, sym in enumerate(W.syms):
            hit = [sc[c][0] for c in QT["s2c"].get(str(sym), ()) if c in sc]
            if len(hit) == 1:
                v[j] = hit[0]
        out.append(v)
    QT["cache"][r] = tuple(out)
    return QT["cache"][r]


def quality_scores(W, r, uni):
    """-> (n_ret, n_pair, GPA, OPA) for the names `uni` at the rank session r (r17.rm_scores's shape; the counts are r17's own, so the pool rules
    are RESMOM's; a name needs both scores, so the two cells rank one shared pool)"""
    n_ret, n_pair, _, _ = _ORIG["rm_scores"](W, r, uni)
    gpa, opa = scores_on(W, r)
    return n_ret, n_pair, gpa[uni], opa[uni]


def quality_null(W, L, nreps, vcode=0):
    """r15's null_l1 per cell (r17.rm_null's draw) on this family's streams [20261005, 23 / 24, vcode]"""
    acc = {}
    with D15.spec(l1_slot=R17.SPEC["slot"], l1_n=R17.SPEC["n_side"]):
        for cell in R17.CELLS:
            acc[cell] = D15.null_l1(W, R17.cell_leg(L, cell), nreps, np.random.default_rng([R17.SEED, CODE[cell], vcode]))[0]
    if vcode == 0:
        CAP["acc"] = acc
    return acc


class quality_mode:
    def __enter__(self):
        self.cm = R17.patched(R17, rm_scores=quality_scores, rm_null=quality_null)
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


NAMED = {"2020-03": ("2020-03-01", "2020-03-31"), "junk rally 2020-04..2021-02": ("2020-04-01", "2021-02-28"), "2022": ("2022-01-01", "2022-12-31")}


def named_windows(B, xB):
    """each cell's net in the prereg's named windows (2020-03, the 2020-04 .. 2021-02 junk rally, 2022), from #463's rows"""
    idx = pd.DatetimeIndex(B.index)
    return {k: float(np.asarray(xB, float)[(idx >= TS(a)) & (idx <= TS(b))].sum()) for k, (a, b) in NAMED.items()}


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
    out["named_windows"] = named_windows(B, xB)
    out["turnover"] = R17.turnover(L, cell)
    out["episodes_463"] = D15.episodes_table(S12, xB)
    return out


# ------------------------------------------------------------------ dryload (COUNTS only: no price, return, score or P&L is printed)
def load_world():
    nf = load_facts()
    print(f"facts: income {nf['income']:,} rows, assets {nf['assets']:,} rows (pinned); annual table {len(QT['T']):,} firm-years, {QT['T'].cik.nunique():,} firms", flush=True)
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
    with quality_mode():
        L = R17.rm_build(W, WF0, PRE_END, JUDGED, units=False)
    by = {}
    for rec in L.recs:
        uni = np.flatnonzero(W.U[rec.f])
        g, o = scores_on(W, rec.r)
        by.setdefault(int(W.days[rec.f].year), []).append((len(uni), int(np.isfinite(g[uni]).sum()), int(np.isfinite(o[uni]).sum()), len(rec.pool), bool(rec.traded)))
    print(f"rebalances: {len(L.recs)} in WF, {sum(r.traded for r in L.recs)} traded (pool >= 2 x {R17.SPEC['n_side']}); first fill {W.days[L.recs[0].f]:%Y-%m-%d}" if L.recs else "rebalances: none")
    for y, v in sorted(by.items()):
        a = np.array(v, float)
        print(f"  fill year {y}: {len(v)} rebalances, {int(a[:, 4].sum())} traded; universe {a[:, 0].mean():.0f}; with GPA {a[:, 1].mean():.0f}, with OPA {a[:, 2].mean():.0f}; "
              f"pool (both) {a[:, 3].min():.0f}-{a[:, 3].mean():.0f}-{a[:, 3].max():.0f}")
    T = QT["T"]
    print(f"facts: scale errors (|score| > 3, out) GPA {int(T.gpa_scale.sum())} / OPA {int(T.opa_scale.sum())} firm-years; GP source {T.gp_source.value_counts().to_dict()}")
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
    h = hashlib.sha256(open(L_CSV, "rb").read()).hexdigest()
    if not h.startswith(L_SHA):
        raise SystemExit(f"refused: {L_CSV} sha {h[:12]} is not the S1 line {L_SHA}...")
    Ld = pd.read_csv(L_CSV, parse_dates=["date"]).set_index("date")
    idx = pd.DatetimeIndex(B.index)
    res_line = Ld["RES"].reindex(idx).fillna(0.0).to_numpy(float)
    SL = M12.Stretch(np.asarray(B.raw, float) + C_RES * res_line, idx, None, WF0, PRE_END)
    lf = figs(SL.x, SL.years)
    print(f"THE S1 LINE L: ROC@30k {lf['roc']:.2f} Sortino {lf['sort']:.3f} DD ${lf['mdd']:,.0f} | R {len(SL.qual)} episodes / {SL.n_dd_days} days (want 121.06 / 3.926 / 36,526, 45 / 762)")
    if not (abs(lf["roc"] - 121.06) <= 0.01 and abs(lf["sort"] - 3.926) <= 0.001 and len(SL.qual) == 45 and SL.n_dd_days == 762):
        raise SystemExit("PARITY STOP: the S1 line does not reproduce (nothing judged)")
    return SL, res_line, lf


def power():
    """the family null on the 'close' pools (the same draws Stage A's evaluate makes: same streams, same pools) - NO cell is run"""
    psha = prereg_ok()
    pins(psha)
    t0 = time.time()
    B, _ = A13.load_463()
    bk, dd, S12 = R17.book_checks(B)
    if not (bk["ok"] and dd["ok"]):
        raise SystemExit("refused: #463 does not reproduce the registered WF numbers / drawdown structure (nothing computed)")
    W, aud, csi = load_world()
    rows = A13.book_rows(B, W)
    SL, _, _ = load_line(B)
    with quality_mode():
        L = R17.rm_build(W, WF0, PRE_END, JUDGED)
        acc = quality_null(W, L, R17.NREP, 0)
    pw = power_read(B, S12, SL, rows, acc)
    pw.update({"prereg_sha256_lf": psha, "harness_sha256": hashlib.sha256(open(__file__, "rb").read()).hexdigest(), "rebalances": len(L.recs), "traded": int(sum(v.traded for v in L.recs))})
    os.makedirs(OUT, exist_ok=True)
    with open(POWER_JSON, "w") as f:
        json.dump(pw, f, indent=1, default=lambda o: o.item() if hasattr(o, "item") else str(o))
    print(f"\nQUALITY r1 POWER LINE (the family null alone, {pw['draws']} draws; no cell was run): bar {pw['bar_rule']} = {pw['bar_roc']:.2f}"
          f" (= ${pw['bar_roc'] * 1000:,.0f} a year at a $30k worst drawdown); null MAX p50 {pw['null']['roc_max']['p50']:.2f}")
    for nm, c in pw["cells"].items():
        print(f"  {nm}: the true edge it takes to clear the bar - 50% power ${c['mde50_usd_per_year_own_size']:,.0f} a year, 80% power ${c['mde80_usd_per_year_own_size']:,.0f} a year "
              f"(own size: 50 a side at $4,000, {c['active_days']} active WF days); seat on R: null p50 ${c['null_on_R']['p50']:,.0f} / p95 ${c['null_on_R']['p95']:,.0f} / SD ${c['null_on_R']['sd']:,.0f} -> "
              f"a seat needs ${c['seat_mde50_on_R_own_size']:,.0f} (50%) / ${c['seat_mde80_on_R_own_size']:,.0f} (80%) more on R at own size, "
              f"${c['seat_mde50_on_R_at_0.25']:,.0f} / ${c['seat_mde80_on_R_at_0.25']:,.0f} at the 0.25 seat (c ~ {c['seat_c_at_0.25_median_over_draws']:.3f})")
    print(f"written {POWER_JSON} ({time.time() - t0:.0f}s) - commit these lines as {os.path.basename(POWER_DOC)} BEFORE stage_a")
    return pw


def power_committed():
    """stage_a's gate: the power addendum is committed in the repo and quotes this power file's sha256"""
    import subprocess
    if not (os.path.exists(POWER_JSON) and os.path.exists(POWER_DOC)):
        raise SystemExit(f"refused: run `power` and commit {os.path.basename(POWER_DOC)} first (MANAGER #115 (1): the power line is committed before any cell P&L)")
    ph = hashlib.sha256(open(POWER_JSON, "rb").read()).hexdigest()
    if ph[:16] not in open(POWER_DOC, encoding="utf-8").read():
        raise SystemExit(f"refused: {os.path.basename(POWER_DOC)} does not quote the power file's sha256 {ph[:16]}...")
    r = subprocess.run(["git", "-C", REPO, "log", "-1", "--format=%H %ci", "--", os.path.relpath(POWER_DOC, REPO).replace(os.sep, "/")], capture_output=True, text=True)
    if r.returncode or not r.stdout.strip():
        raise SystemExit(f"refused: {os.path.basename(POWER_DOC)} is not committed")
    return {"power_sha256": ph, "power_doc_commit": r.stdout.strip()}


# ------------------------------------------------------------------ Stage A
def stage_a():
    psha = prereg_ok()
    pgate = power_committed()
    pins(psha, pgate)
    pok = R17.prereg_ok()
    t0 = time.time()
    B, _ = A13.load_463()
    bk, dd, S12 = R17.book_checks(B)
    if not (bk["ok"] and dd["ok"]):
        raise SystemExit("refused: #463 does not reproduce the registered WF numbers / drawdown structure (nothing computed)")
    W, aud, csi = load_world()
    rows = A13.book_rows(B, W)
    SL, res_line, lf = load_line(B)                                     # the S1 line's parity first: a stop here computes no cell
    print(f"RESMOM prereg {'verified' if pok['verified'] else 'NOT verified'}; world ready ({time.time() - t0:.0f}s); calendar splits on the grid: {csi}; RESMOM audit rows: {0 if aud is None else len(aud)}", flush=True)
    with quality_mode():
        res, obj = R17.evaluate(W, B, S12, rows, JUDGED, R17.NREP, 0, full=True)
    print(f"the '{JUDGED}' reading + its {R17.NREP}-draw null done ({time.time() - t0:.0f}s)", flush=True)
    idx = pd.DatetimeIndex(B.index)
    others = {}
    if os.path.exists(BAB_NPZ):
        z = np.load(BAB_NPZ, allow_pickle=True)
        bi = pd.to_datetime(z["book_index"])
        for nm in ("BETA", "VOL"):
            others[f"BAB_{nm}"] = pd.Series(z[f"x_{nm}"], index=bi).reindex(idx).fillna(0.0).to_numpy(float)
    fr = {"prereg_sha256_lf": psha, "harness_sha256": hashlib.sha256(open(__file__, "rb").read()).hexdigest(), "r17_sha256": hashlib.sha256(open(R17.__file__, "rb").read()).hexdigest(),
          "judged_reading": JUDGED, "line": lf, "null": res["null"], "power": pgate, "stress_decides": STRESS_DECIDES, "facts": FACTS, "cells": {}}
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
                with quality_mode():
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
                os.path.join(OUT, f"quality_audit_candidates_{nm}.csv"), index=False)
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "quality_stageA.json"), "w") as f:
        json.dump(fr, f, indent=1, default=lambda o: o.item() if hasattr(o, "item") else str(o))
    print(f"\nQUALITY r1 Stage A ('{JUDGED}' reading, WF; null p95 MAX over the 2 cells {res['null']['roc_max']['p95']:.2f}):")
    for nm, p in fr["cells"].items():
        st = p["stage_a"]
        b = st["base"]
        print(f"  {nm}: ROC@30k {b['roc']:.2f} / DD5 ${st['dd5']['dd5']:,.0f}{' (ONE EPISODE)' if st['dd5']['one_episode'] else ''} | Sortino {b['sortino']:.3f} | worst DD ${b['max_dd']:,.0f} | net ${b['net']:,.0f} | "
              f"Stage A {'PASS (audit pending)' if st['PASS'] else 'FAIL'}" + ("" if st["PASS"] else " - fails " + ", ".join(k for k, v in st["checks"].items() if not v)))
        s = p.get("seat", {})
        if "error" not in s:
            a = s["book_add"]["0.25"]["line_plus"]
            print(f"     seat (report): L + cX at 0.25 = {a['roc']:.2f} / DD5 ${a['dd5']:,.0f} (L {lf['roc']:.2f}); on R ${s['x_on_R']:,.0f} (without best ${s['x_on_R_without_best']:,.0f}; null p95 "
                  f"${s['null_on_R']['p95']:,.0f}); #70 gate {'PASS' if s['gate70']['pass'] else 'FAIL'}; corr RES {s['corr_RES_all']:+.3f}")
        dg = p.get("diagnostics", {})
        if "error" not in dg:
            print(f"     BETA TO ES {dg['beta_to_es']:+.3f}{'' if dg['beta_credited'] else ' (|beta| > 0.20: drawdown-day money REPORTED, NEVER CREDITED)'}; halves ROC {dg['half_1']['roc']:.1f} / {dg['half_2']['roc']:.1f}; cost nets {dg['cost_net']} with turnover {dg['turnover'].get('replaced_mean', float('nan')):.0%} of names a month; named windows {dg['named_windows']}")
    print(f"written {os.path.join(OUT, 'quality_stageA.json')} ({time.time() - t0:.0f}s)")
    return fr


# ------------------------------------------------------------------ selftest (the facts table on hand-made filings; r17's toy world; n_side 3)
def selftest():
    for f in ("dryload", "power", "power_committed", "stage_a", "load_line", "load_world", "power_read", "seat_read", "diagnostics"):
        assert callable(globals().get(f)), f"the command function {f} is missing"
    import inspect
    assert "load_line(B)" not in inspect.getsource(globals()["load_line"]).split("\n", 1)[1], "load_line calls itself"
    assert "evaluate(" in inspect.getsource(globals()["stage_a"]) and "quality_null(" in inspect.getsource(globals()["power"])
    ts = pd.Timestamp
    row = lambda cik, con, val, start, end, filed, form="10-K", fp="FY", accn="a": dict(cik=cik, symbols="S" + cik, concept=con, unit="USD", val=val,
                                                                                        start=start, end=end, accn=accn, fy=2019, fp=fp, form=form, filed=filed, frame="")
    inc = pd.DataFrame([row("1", GP, 40.0, "2019-01-01", "2019-12-31", "2020-02-20"), row("1", GP, 44.0, "2019-01-01", "2019-12-31", "2021-02-20", accn="b"),
                        row("1", OI, 10.0, "2019-01-01", "2019-12-31", "2020-02-20"), row("1", GP, 9.0, "2019-10-01", "2019-12-31", "2020-02-20", fp="Q4"),
                        row("2", "us-gaap:Revenues", 100.0, "2019-01-01", "2019-12-31", "2020-03-01"),
                        row("2", "us-gaap:SalesRevenueNet", 999.0, "2019-01-01", "2019-12-31", "2020-03-01"),
                        row("2", "us-gaap:CostOfRevenue", 70.0, "2019-01-01", "2019-12-31", "2020-03-05", form="10-K/A"),
                        row("3", GP, 5.0, "2019-01-01", "2019-12-31", "2020-02-01"), row("4", GP, 500.0, "2019-01-01", "2019-12-31", "2020-02-01"),
                        row("5", GP, 1.0, "2019-01-01", "2019-12-31", "0202-02-01")])
    ast = pd.DataFrame([dict(cik=c, symbols="S" + c, concept=ASSETS, unit="USD", val=v, start=None, end="2019-12-31", accn="a", fy=2019, fp="FY",
                             form="10-K", filed=f, frame="") for c, v, f in (("1", 200.0, "2020-02-20"), ("2", 50.0, "2020-03-01"), ("4", 100.0, "2020-02-01"))])
    T = annual_table(inc, ast)
    t1, t2 = T[T.cik == "1"].iloc[0], T[T.cik == "2"].iloc[0]
    assert abs(t1.gpa - 0.2) < 1e-12 and abs(t1.opa - 0.05) < 1e-12 and t1.gp_source == "reported" and t1.gpa_usable == ts("2020-02-20"), "first-filed value, not the restatement"
    assert abs(t2.gpa - 0.6) < 1e-12 and t2.gp_source == "rev-cogs" and t2.gpa_usable == ts("2020-03-05") and np.isnan(t2.opa), "rev - cogs, in order, usable at the later part"
    assert np.isnan(T[T.cik == "3"].iloc[0].gpa) and bool(T[T.cik == "4"].iloc[0].gpa_scale) and "5" not in set(T.cik), "no assets / scale error / impossible date"
    assert score_at(T, ts("2020-02-20"), "gpa") == {} and set(score_at(T, ts("2020-02-21"), "gpa")) == {"1"} and set(score_at(T, ts("2020-03-06"), "gpa")) == {"1", "2"}
    assert score_at(T, ts("2021-07-15"), "gpa") == {} and set(score_at(T, ts("2021-06-15"), "gpa")) == {"1", "2"}, "stale after 18 months"
    with R17.spec(n_side=3), D15.spec(univ=14):
        W = R17.toy_world()
        rng = np.random.default_rng(3)
        rowsI, rowsA = [], []
        for j, sym in enumerate(W.syms):                                       # one firm per toy symbol, a 10-K each year filed ~50 days after its year end
            for y in range(2023, 2026):
                e, f = f"{y - 1}-12-31", (ts(f"{y}-01-01") + pd.Timedelta(days=int(rng.integers(40, 60)))).strftime("%Y-%m-%d")
                rowsI += [dict(cik=str(j), symbols=str(sym), concept=GP, unit="USD", val=float(rng.uniform(5, 60)), start=f"{y - 1}-01-01", end=e, accn="a", fy=y, fp="FY", form="10-K", filed=f, frame=""),
                          dict(cik=str(j), symbols=str(sym), concept=OI, unit="USD", val=float(rng.uniform(-5, 20)), start=f"{y - 1}-01-01", end=e, accn="a", fy=y, fp="FY", form="10-K", filed=f, frame="")]
                rowsA.append(dict(cik=str(j), symbols=str(sym), concept=ASSETS, unit="USD", val=100.0, start=None, end=e, accn="a", fy=y, fp="FY", form="10-K", filed=f, frame=""))
        set_table(annual_table(pd.DataFrame(rowsI), pd.DataFrame(rowsA)))
        n = 0
        for r in range(251, W.T - 1, 17):
            uni = np.flatnonzero(W.U[r + 1])
            if not len(uni):
                continue
            nr, npair, g, o = quality_scores(W, r, uni)
            nr0, np0, _, _ = _ORIG["rm_scores"](W, r, uni)
            assert (nr == nr0).all() and (npair == np0).all(), "the pool counts are r17's"
            d = W.days[r]
            for k, c in enumerate(uni):                                          # brute force: the latest 10-K filed strictly before the rank, within 18 months
                cand = [x for x in rowsI if x["cik"] == str(c) and x["concept"] == GP and ts(x["filed"]) < d and ts(x["end"]) >= d - pd.Timedelta(days=STALE_DAYS)]
                want = max(cand, key=lambda x: x["end"])["val"] / 100.0 if cand else np.nan
                assert (np.isnan(want) and np.isnan(g[k])) or abs(want - g[k]) < 1e-12, (r, c, want, g[k])
                n += 1
        assert n >= 10, n
        with quality_mode():
            L = R17.rm_build(W, W.days[0], W.days[-1], JUDGED)
            tr = [v for v in R17.cell_leg(L, "RES").recs if v.traded]
            assert len(tr) >= 3, len(tr)
            for v in tr:
                assert v.sig[v.long].min() >= v.sig[v.short].max() - 1e-12, "longs = the highest scores"
            acc = quality_null(W, L, 30, 7)
            with D15.spec(l1_slot=R17.SPEC["slot"], l1_n=R17.SPEC["n_side"]):
                ref = D15.null_l1(W, R17.cell_leg(L, "RAW"), 30, np.random.default_rng([R17.SEED, 28, 7]))[0]
            assert np.allclose(acc["RAW"], ref), "the OPA null is r15's null_l1 on the family stream"
        B, S12 = R17.synth_book(seed=15)
        rows = A13.book_rows(B, W)
        with quality_mode(), R17.patched(R17, A2_WIN=(TS("2024-12-02"), TS("2025-05-30"))), R17.patched(sys.modules[__name__], SEAT_WIN=(TS("2025-01-01"), TS("2025-06-27"))):
            res, obj = R17.evaluate(W, B, S12, rows, JUDGED, 20, 0, full=True)
            assert res["null"]["draws"] == 20 and set(CAP["acc"]) == set(R17.CELLS)
            res_line = rng.normal(0.0, 300.0, B.n)
            SL = M12.Stretch(np.asarray(B.raw, float) + C_RES * res_line, pd.DatetimeIndex(B.index), None, WF0, PRE_END)
            for cell in R17.CELLS:
                CL, run, c = obj.cell_legs[cell], obj.runs[cell], res["cells"][cell]
                xB = obj.series[cell][0]
                dg = diagnostics(W, B, S12, rows, obj.legs, cell, CL, run, xB, c)
                assert set(dg["named_windows"]) == set(NAMED) and isinstance(dg["beta_credited"], bool)
                assert dg["turnover"]["traded_rebalances"] == sum(v.traded for v in CL.recs)
                sr = seat_read(B, S12, SL, rows, xB, CAP["acc"][cell], res_line, {"BAB_BETA": rng.normal(0.0, 50.0, B.n)})
                assert set(sr["book_add"]) == {"0.25", "0.10"} and "dd5" in sr["book_add"]["0.25"]["line_plus"]
            pw = power_read(B, S12, SL, rows, CAP["acc"])
            assert pw["bar_roc"] >= 15.0 and set(pw["cells"]) == set(NAME.values())
    QT.clear()
    print(f"r27_quality selftest OK (the facts table: first-filed values, restatements ignored, annual only, rev - cogs fallback, strictly before the rank, "
          f"18-month stale cut, scale / date errors out; {n} toy name-ranks by brute force; longs = highest scores; the null on its stream; "
          f"the '{JUDGED}' Stage A + seat read + diagnostics + power read end to end)")


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
        raise SystemExit("usage: r27_quality.py selftest | dryload | power | stage_a")


if __name__ == "__main__":
    main(sys.argv[1:])
