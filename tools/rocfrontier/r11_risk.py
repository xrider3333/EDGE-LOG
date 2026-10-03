# Round 11 (2026-10-03): RISK r1 - is book round 62's V2 volatility target a TIMING MECHANISM or two lucky drawdowns?
# Pre-registered: tools/rocfrontier/PREREG_RISK_R1.txt (commit 2d0f6f9 on main, written before the harness 6686b1a; sha256 b7d9c5dc...d017), then three dated PRE-DATA addenda: this
# harness's own synthetic power check and an independent code review (E2 on rule U, strict p <= 0.05, verdict spans ALL / ALLX, the
# INCONCLUSIVE reading), and the relation to round 62 V3 (R5 report-only). PREREG_SHA below is the file with all three.
# Every rule, threshold and window is that file; where it is silent the choice is marked CHOICE.
#   python r11_risk.py build        one engine pass over #463's legs -> per-trade records under both day rules (U = engine UTC stamp, S = ET session day)
#                                   + P1 (records re-sum to the engine's own series) + the list of round-62 output files already on disk
#   python r11_risk.py parity       P2 (raw #463 reproduces 10r / 10o), P3 (V2 reproduces 10o's printed row), P4 (the engine's book_sizing run
#                                   equals this harness) - writes READY only when all four pass; these are the ONLY reads past 2025-06-29
#   python r11_risk.py run          E1-E3 (primary) + R1-R5 (reported) -> VERDICT.txt; refuses without READY; asserts no row after 2025-06-29
#   python r11_risk.py smoke DIR [null|planted]  offline self-test on a SYNTHETIC world through the engine's real leg runner with a faked data layer
#                                   (DIR's name must contain 'smoke'); its numbers mean nothing
# Results go to OUT (outside git). Nothing here commits, pushes, queues a job or writes anywhere else.
import glob, hashlib, json, math, os, sys
REPO = os.environ.get("EDGELOG_ROOT", r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"); sys.path.insert(0, REPO)
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.environ.get("EDGELOG_ROCFRONTIER_R11", r"C:\EdgeLog\_anatomy_cache\rocfrontier\r11")
R62_DIR = os.environ.get("EDGELOG_R62_DIR", r"C:\EdgeLog\_anatomy_cache\adopt449")
PREREG = os.path.join(HERE, "PREREG_RISK_R1.txt")
PREREG_SHA = "aeb228725526e4070697013e29e45f3f1d1711b29d0d385adab2012dcfa5b5df"
TS = pd.Timestamp
W0, W1 = "2010-06-07", "2026-06-30"                                  # #463's window (its job's own)
IS0, IS1 = TS("2011-01-03"), TS("2016-06-30")                         # IS* (2010 is V2's warm-up)
WF0, PRE_END = TS("2016-07-01"), TS("2025-06-29")                     # WF = [WF0, PRE_END] inclusive; nothing after PRE_END outside parity
LB0, LB1, LBX = TS("2025-06-30"), TS("2026-06-30"), TS("2026-07-01")
X20 = (TS("2020-02-15"), TS("2020-04-30"))                           # the rows EX / ALLX remove
VT = {"lo": 0.5, "hi": 2.0, "decimals": 1}
CELLS = {"V2": (20, 250), "V2-500": (20, 500), "V2-60": (60, 250)}   # (vol lookback, REF rows); REF needs ref // 2 rows (125 / 250)
P2_REF = {"unified": {"WF": (93.81, 3.816), "LB": (155.54, 4.150)}, "old": {"WF": (92.70, 3.816), "LB": (164.76, 4.150)}}
P2_TOL = (0.006, 0.0006)
P3_REF = {"WF": (116.1, 3.91, 35304.0), "LB": (259.3, 4.79, 32941.0)}
P3_TOL = (0.06, 0.006, 1.0)
KMIN, NBOOT, BLOCK, SEED = 250, 999, 60, 20261003
MICRO_RT = {"NQ": 1.20 * 2.0, "ES": 0.63 * 5.0}                     # $ a micro round trip (MNQ 1.20 pts x $2, MES 0.63 pts x $5)
CHECK_REFS = True        # a real run ALWAYS checks P2 / P3 against the printed numbers; only smoke() can switch it (a synthetic world cannot match them)
SMOKE_NULL_STEP = 1      # every shift k is evaluated; smoke() may thin it


def js(o):
    if isinstance(o, (np.bool_,)): return bool(o)
    if isinstance(o, np.integer): return int(o)
    if isinstance(o, np.floating): return float(o)
    if isinstance(o, np.ndarray): return o.tolist()
    if isinstance(o, (pd.Timestamp, np.datetime64)): return str(pd.Timestamp(o).date())
    return str(o)


def save(name, obj):
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, name), "w") as f:
        f.write(json.dumps(obj, indent=1, default=js))


def load_json(name):
    with open(os.path.join(OUT, name)) as f:
        return json.load(f)


def sha_lf(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read().replace(b"\r\n", b"\n")).hexdigest()


def check_prereg():
    got = sha_lf(PREREG)
    if got != PREREG_SHA:
        raise SystemExit(f"refused: PREREG_RISK_R1.txt sha256 {got} is not the registered {PREREG_SHA} - the plan changed after it was registered")


# ------------------------------------------------------------------ build: one engine pass -> per-trade records under both day rules
def book_legs():
    from api.book_shadow import BOOK463_LEGS
    return [dict(l) for l in BOOK463_LEGS]


def trade_records(st, days):
    """Per trade of one leg (in the leg's own order): entry day, exit day, closed $, and its valued-daily increments on `days` (a per-bar day
    array: the engine's UTC stamp or the session day). Mirrors book._closed_series and book._mtm_increments exactly (P1 proves it against the
    engine's own series); `ends` is computed once instead of once per trade."""
    last = st["last"]
    close = np.asarray(st["close"], float) if st.get("close") is not None else None
    ends = np.flatnonzero(days[1:] != days[:-1])
    pm, usd_units = st.get("plugin_marks"), bool(st.get("usd_units"))
    fsz = st.get("file_sizes") or {}
    ent, ext, clo, it, idd, iv, fs = [], [], [], [], [], [], []
    for j, (t, size) in enumerate(st["sized"]):
        try:
            e = min(max(int(t[0]), 0), last)
            x = min(int(t[1]), last)
            scale = float(st["mult"]) * float(st["weight"]) * float(size)
            usd = float(t[2]) * scale
        except Exception:
            continue
        n = len(ent)
        ent.append(days[e]); ext.append(days[x]); clo.append(usd); fs.append(float(fsz.get(id(t), 1.0)) * float(size))
        pieces = None
        if x <= e or days[e] == days[x] or st.get("mtm_failed"):
            pieces = [(days[x], usd)]
        elif pm is not None and pm.get(id(t)) is not None:
            pts = sorted((int(k), float(v)) for k, v in pm[id(t)])
            if pts and all(e <= k < x and np.isfinite(v) for k, v in pts):
                prev, pieces = 0.0, []
                for k, v in pts:
                    pieces.append((days[k], v * scale - prev)); prev = v * scale
                pieces.append((days[x], usd - prev))
            else:
                pieces = [(days[x], usd)]
        elif usd_units:
            pieces = [(days[x], usd)]
        else:
            try:
                side, px = float(t[3]), float(t[4])
                ok = close is not None and abs(side) == 1.0 and np.isfinite(px) and px > 0
            except Exception:
                ok = False
            if not ok:
                pieces = [(days[x], usd)]
            else:
                prev, pieces = 0.0, []
                for k in ends[np.searchsorted(ends, e, side="left"):np.searchsorted(ends, x, side="left")]:
                    val = side * (float(close[k]) - px) * scale
                    pieces.append((days[k], val - prev)); prev = val
                pieces.append((days[x], usd - prev))
        for d, v in pieces:
            it.append(n); idd.append(d); iv.append(v)
    D = lambda a: np.asarray(a, dtype="datetime64[D]")
    return {"entry": D(ent), "exit": D(ext), "closed": np.asarray(clo, float), "inc_t": np.asarray(it, np.int64),
            "inc_d": D(idd), "inc_v": np.asarray(iv, float), "fsize": np.asarray(fs, float)}


def by_day(days, vals):
    s = pd.Series(np.asarray(vals, float), index=pd.to_datetime(np.asarray(days, dtype="datetime64[D]")))
    return s.groupby(level=0).sum()


def series_equal(a, b, tol=0.01):
    idx = a.index.union(b.index)
    d = (a.reindex(idx).fillna(0.0) - b.reindex(idx).fillna(0.0)).abs()
    return bool((d <= tol).all()), float(d.max()) if len(d) else 0.0


def _ready_path():
    return os.path.join(OUT, "READY")


def _sha_file(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def _record_hashes():
    return {n: _sha_file(os.path.join(OUT, n)) for n in ("records_U.npz", "records_S.npz", "build.json")}


def build():
    """One engine pass; records for rules U and S; P1. Revokes any earlier READY first (review 2026-10-03)."""
    check_prereg()
    if os.path.exists(_ready_path()):
        os.remove(_ready_path())
    from augur_engine import book as B, book_sizing as BS
    legs = book_legs()
    rec = {"U": [], "S": []}
    p1, meta = [], []
    for k, leg in enumerate(legs):
        tr, info = B._leg_trades(dict(leg), W0, W1, keep_state=True)
        st = info.pop("_state")
        mtm_u, sess = info.pop("_mtm_day"), info.pop("_session_day")
        BS.signal_guard([leg], [info], [0])                                  # pinned master, valuation ok, nothing unmarked
        dU = st["days_idx"]
        dS = st["sess_idx"] if st["sess_idx"] is not None else st["days_idx"]
        for rule, days in (("U", dU), ("S", dS)):
            r = trade_records(st, days)
            r["leg"] = np.full(len(r["closed"]), k, np.int64)
            rec[rule].append(r)
        rU, rS = rec["U"][-1], rec["S"][-1]
        okm, dm = series_equal(by_day(rU["inc_d"], rU["inc_v"]), by_day([d for d, _ in mtm_u], [v for _, v in mtm_u]))
        okc, dc = series_equal(by_day(rU["exit"], rU["closed"]), by_day([d for d, _ in tr], [v for _, v in tr]))
        oks, ds = series_equal(by_day(rS["exit"], rS["closed"]), by_day([d for d, _ in sess], [v for _, v in sess]))
        p1.append({"leg": leg["strategy"], "trades": int(len(rU["closed"])), "mtm_U_ok": okm, "mtm_U_maxdiff": dm, "closed_U_ok": okc,
                   "closed_U_maxdiff": dc, "closed_S_ok": oks, "closed_S_maxdiff": ds, "source": info.get("source"), "master": info.get("master")})
        meta.append({"strategy": leg["strategy"], "instrument": leg["instrument"], "mult": float(st["mult"]), "weight": float(st["weight"]),
                     "cost_pts": float(leg.get("cost_pts") or 0.0)})
        print(k, leg["strategy"], len(rU["closed"]), "trades", "P1", okm and okc and oks, flush=True)
    for rule in ("U", "S"):
        cat = {key: np.concatenate([r[key] for r in rec[rule]]) for key in ("entry", "exit", "closed", "leg", "inc_d", "inc_v", "fsize")}
        off = np.cumsum([0] + [len(r["closed"]) for r in rec[rule]])[:-1]
        cat["inc_t"] = np.concatenate([r["inc_t"] + o for r, o in zip(rec[rule], off)])
        os.makedirs(OUT, exist_ok=True)
        np.savez_compressed(os.path.join(OUT, f"records_{rule}.npz"), **{k: (v.astype("int64") if v.dtype.kind == "M" else v) for k, v in cat.items()})
    seen = []
    for p in sorted(glob.glob(os.path.join(R62_DIR, "*"))):
        n = os.path.basename(p).lower()
        if os.path.isfile(p) and ("r62" in n or "62" in n and "prereg" in n):
            seen.append({"file": os.path.basename(p), "bytes": os.path.getsize(p), "sha256": hashlib.sha256(open(p, "rb").read()).hexdigest()})
    ok = all(x["mtm_U_ok"] and x["closed_U_ok"] and x["closed_S_ok"] for x in p1)
    save("build.json", {"P1": p1, "P1_pass": ok, "legs": meta, "round62_files_seen": seen if os.path.isdir(R62_DIR) else "R62_DIR not found",
                        "prereg_sha256": PREREG_SHA})
    if not ok:
        raise SystemExit("P1 FAILED - the per-trade records do not re-sum to the engine's own series; see build.json")
    print("build ok; round-62 files listed:", len(seen) if isinstance(seen, list) else seen, flush=True)


# ------------------------------------------------------------------ the book as sparse matrices: entry row x P&L row
class Book:
    """Records of one day rule -> index (business days of the window + every day with P&L), each trade's entry ROW (an off-index entry day
    reads the next row, the engine's / shadow's rule), and sparse matrices A[entry_row, day_row] of unsized dollars. A multiplier vector m
    over rows sizes every trade by its entry row: daily = A.T @ m - closed dollars and every daily mark, trade for trade."""

    def __init__(self, rec, legs_meta):
        from scipy import sparse
        self.meta = legs_meta
        ent, ext = rec["entry"].astype("datetime64[D]"), rec["exit"].astype("datetime64[D]")
        incd = rec["inc_d"].astype("datetime64[D]")
        have = pd.to_datetime(np.unique(incd))
        self.index = pd.bdate_range(W0, W1).union(have).sort_values()
        ix = self.index.values.astype("datetime64[D]")
        n = len(ix)
        self.n = n
        self.erow = np.searchsorted(ix, ent, side="left")
        assert (self.erow < n).all(), "an entry after the last index day"
        drow = np.searchsorted(ix, incd, side="left")
        xrow = np.searchsorted(ix, ext, side="left")
        assert (ix[drow] == incd).all() and (ix[xrow] == ext).all()
        self.xrow, self.leg, self.closed = xrow, rec["leg"], rec["closed"]
        self.entry_day = ent                                                 # the raw entry stamp of the rule (R4)
        self.fsize = rec["fsize"] if "fsize" in rec else np.ones(len(ent))   # the file's own per-trade size x any gate size (R3)
        self.pre_trade = self.index[xrow] <= PRE_END                         # trades closed before the lockbox
        self.inc_t, self.inc_row, self.inc_v = rec["inc_t"], drow, rec["inc_v"]
        t = self.inc_t
        self.Am = sparse.csr_matrix((self.inc_v, (self.erow[t], drow)), shape=(n, n))
        self.Ac = sparse.csr_matrix((self.closed, (self.erow, xrow)), shape=(n, n))
        self.Am_leg, self.Ac_leg = [], []
        for k in range(len(legs_meta)):
            mk = self.leg[t] == k
            self.Am_leg.append(sparse.csr_matrix((self.inc_v[mk], (self.erow[t[mk]], drow[mk])), shape=(n, n)))
            mc = self.leg == k
            self.Ac_leg.append(sparse.csr_matrix((self.closed[mc], (self.erow[mc], xrow[mc])), shape=(n, n)))
        self.ones = np.ones(n)
        self.raw = self.Am.T @ self.ones
        self.raw_closed = self.Ac.T @ self.ones
        self.pre_n = int(np.searchsorted(ix, np.datetime64(PRE_END.date()), side="right"))   # rows <= 2025-06-29

    def mult(self, cell):
        from augur_engine.book_sizing import vt_multipliers
        L, R = CELLS[cell]
        return vt_multipliers(pd.Series(self.raw, index=self.index), L, R, VT["lo"], VT["hi"], VT["decimals"]).to_numpy(float)

    def sized(self, m):
        return self.Am.T @ m

    def sized_closed(self, m):
        return self.Ac.T @ m

    def mask(self, lo, hi, excise=None):
        d = self.index
        k = (d >= lo) & (d <= hi)
        if excise is not None:
            k &= ~((d >= excise[0]) & (d <= excise[1]))
        return np.asarray(k)


def load_book(rule, legs_meta):
    z = np.load(os.path.join(OUT, f"records_{rule}.npz"))
    rec = {k: z[k] for k in z.files}
    for k in ("entry", "exit", "inc_d"):
        rec[k] = rec[k].astype("datetime64[D]")
    return Book(rec, legs_meta)


# ------------------------------------------------------------------ statistics (prereg STATISTICS; unified convention)
def ddpath(x):
    c = np.cumsum(np.asarray(x, float))
    return np.maximum.accumulate(np.concatenate([[0.0], c]))[1:] - c         # peak starts at 0


def stats(x, dates):
    x = np.asarray(x, float)
    if len(x) < 2:
        return None
    dd = ddpath(x)
    yrs = (pd.Timestamp(dates[-1]) - pd.Timestamp(dates[0])).days / 365.25
    net = float(x.sum())
    mdd = float(dd.max())
    q = max(1, int(math.ceil(0.05 * len(dd))))
    cdar = float(np.sort(dd)[-q:].mean())
    ulcer = float(np.sqrt(np.mean(dd ** 2)))
    dn = float(np.sqrt(np.mean(np.minimum(x, 0.0) ** 2)))
    ann = net / yrs if yrs > 0 else float("nan")
    return {"net": net, "years": yrs, "max_dd": mdd, "cdar95": cdar, "ulcer": ulcer,
            "roc": 30.0 * ann / mdd if mdd > 0 else float("nan"), "sort": float(x.mean() / dn * np.sqrt(252)) if dn > 0 else float("nan"),
            "cdr": 30.0 * ann / cdar if cdar > 0 else float("nan"), "upi": ann / ulcer if ulcer > 0 else float("nan")}


def st_on(B, x, lo, hi, excise=None):
    k = B.mask(lo, hi, excise)
    assert not (B.index[k] > PRE_END).any(), "a stage past P3 read a row after 2025-06-29"
    return stats(np.asarray(x)[k], B.index[k])


def old_convention(B, mtm, closed, t0, t1_excl, years):
    """Round 56/62's convention: net from closed trades, drawdown and Sortino valued daily, rows [t0, t1), fixed years."""
    k = np.asarray((B.index >= t0) & (B.index < t1_excl))
    x = np.asarray(mtm)[k]
    dd = float(ddpath(x).max())
    net = float(np.asarray(closed)[k].sum())
    dn = float(np.sqrt(np.mean(np.minimum(x, 0.0) ** 2)))
    return {"roc": 30.0 * (net / years) / dd, "sort": float(x.mean() / dn * np.sqrt(252)), "dd": dd, "net": net}


def unified(B, mtm, t0, t1_incl):
    k = np.asarray((B.index >= t0) & (B.index <= t1_incl))
    s = stats(np.asarray(mtm)[k], B.index[k])
    return {"roc": s["roc"], "sort": s["sort"], "dd": s["max_dd"], "net": s["net"]}


# ------------------------------------------------------------------ parity P2-P4 (the only reads past 2025-06-29: numbers already printed)
def parity():
    check_prereg()
    b = load_json("build.json")
    if not b.get("P1_pass"):
        raise SystemExit("refused: P1 has not passed (run build)")
    B = load_book("U", b["legs"])
    WFY, LBY = (LB0 - WF0).days / 365.25, (LB1 - LB0).days / 365.25
    out = {"P2": {}, "P3": {}, "P4": {}}
    raw_u = {"WF": unified(B, B.raw, WF0, PRE_END), "LB": unified(B, B.raw, LB0, LB1)}
    raw_o = {"WF": old_convention(B, B.raw, B.raw_closed, WF0, LB0, WFY), "LB": old_convention(B, B.raw, B.raw_closed, LB0, LBX, LBY)}
    p2 = True
    for conv, got in (("unified", raw_u), ("old", raw_o)):
        for s in ("WF", "LB"):
            ref = P2_REF[conv][s]
            ok = abs(got[s]["roc"] - ref[0]) < P2_TOL[0] and abs(got[s]["sort"] - ref[1]) < P2_TOL[1]
            out["P2"][f"{conv}_{s}"] = {"got": got[s], "ref": ref, "ok": ok}
            p2 &= ok or not CHECK_REFS
    m = B.mult("V2")
    v2m, v2c = B.sized(m), B.sized_closed(m)
    v2o = {"WF": old_convention(B, v2m, v2c, WF0, LB0, WFY), "LB": old_convention(B, v2m, v2c, LB0, LBX, LBY)}
    p3 = True
    for s in ("WF", "LB"):
        ref = P3_REF[s]
        g = v2o[s]
        ok = abs(g["roc"] - ref[0]) < P3_TOL[0] and abs(g["sort"] - ref[1]) < P3_TOL[1] and abs(g["dd"] - ref[2]) <= P3_TOL[2]
        out["P3"][s] = {"got": g, "ref": ref, "ok": ok}
        p3 &= ok or not CHECK_REFS
    out["P3"]["avg_size_trades_pre_lockbox"] = float(m[B.erow[B.index[B.erow] <= PRE_END]].mean())
    if not (p2 and p3):                     # a P2 / P3 miss stops the round before anything else is computed (P4 holds E1 inputs)
        out["pass"], out["refs_checked"] = False, CHECK_REFS
        save("parity.json", out)
        if os.path.exists(_ready_path()):
            os.remove(_ready_path())
        raise SystemExit("parity FAILED at P2/P3 - see parity.json; reconcile with round 62's own scripts and write a dated addendum to "
                         "PREREG_RISK_R1.txt before anything else is computed.")
    # P4: the engine's own sized run
    from augur_engine import book as BK
    stretches = [{"name": "IS*", "from": str(IS0.date()), "to": str(IS1.date())}, {"name": "WF", "from": str(WF0.date()), "to": str(PRE_END.date())}]
    r = BK.run_book(book_legs(), date_from=W0, date_to=W1, lockbox_months=12, book_sizing={"mode": "vt", "stretches": stretches})
    bs = r["book"]["book_sizing"]
    lb_from = np.datetime64(r["book"]["lockbox_from"][:10]) if r["book"].get("lockbox_from") else None

    has_inc = np.zeros(B.n, bool)
    has_inc[np.unique(B.inc_row)] = True                                    # run_book's _daily holds exactly the days that carry an increment

    def curve(x, keep):
        xs = np.asarray(x)[keep & has_inc]
        c = np.cumsum(xs)
        return round(float(xs.sum()), 2), round(abs(float((c - np.maximum.accumulate(c)).min())) if len(c) else 0.0, 2)

    ixd = B.index.values.astype("datetime64[D]")
    allk = np.ones(B.n, bool)
    prek = ixd < lb_from if lb_from is not None else allk
    eng = r["book"]["mtm"]
    p4 = {"whole": [curve(v2m, allk), (eng["whole"]["total_pnl"], eng["whole"]["max_drawdown"])],
          "pre_lockbox": [curve(v2m, prek), (eng["pre_lockbox"]["total_pnl"], eng["pre_lockbox"]["max_drawdown"])]}
    ok4 = all(abs(a[0] - b_[0]) <= 0.01 + 1e-9 and abs(a[1] - b_[1]) <= 0.01 + 1e-9 for a, b_ in p4.values())
    for sname, (lo, hi) in (("IS*", (IS0, IS1)), ("WF", (WF0, PRE_END))):
        mine = unified(B, v2m, lo, hi)
        theirs = [x for x in bs["stretches"] if x["name"] == sname][0]["sized"]
        okk = abs(mine["roc"] - theirs["roc_30k"]) <= 0.001 and abs(mine["sort"] - theirs["sortino"]) <= 0.0001   # as registered
        p4[f"stretch_{sname}"] = {"harness": mine, "engine": theirs, "ok": okk}
        ok4 &= okk
    out["P4"] = {"checks": p4, "ok": bool(ok4), "engine_avg_multiplier_trades": bs.get("avg_multiplier_trades")}
    out["pass"] = bool(p2 and p3 and ok4)
    out["refs_checked"] = CHECK_REFS
    save("parity.json", out)
    ready = _ready_path()
    if out["pass"]:
        with open(ready, "w") as f:
            f.write(json.dumps({"P1-P4": "passed", "sha256": _record_hashes()}, indent=1))
        print("parity PASS - READY", flush=True)
    else:
        if os.path.exists(ready):
            os.remove(ready)
        raise SystemExit("parity FAILED - see parity.json. If P3 missed, reconcile with round 62's own scripts and write a dated addendum to "
                         "PREREG_RISK_R1.txt before anything else is computed.")


# ------------------------------------------------------------------ E1-E3 helpers
def underwater(x, dates):
    """Maximal runs below the running peak (from 0) -> [{depth, peak, trough, end}] deepest first."""
    dd = ddpath(x)
    out, i, n = [], 0, len(dd)
    while i < n:
        if dd[i] <= 0:
            i += 1
            continue
        j = i
        while j + 1 < n and dd[j + 1] > 0:
            j += 1
        t = i + int(np.argmax(dd[i:j + 1]))
        out.append({"depth": float(dd[t]), "peak": str(pd.Timestamp(dates[i - 1]).date()) if i > 0 else str(pd.Timestamp(dates[0]).date()),
                    "trough": str(pd.Timestamp(dates[t]).date()), "end": str(pd.Timestamp(dates[j]).date()), "i0": i, "it": t, "i1": j})
        i = j + 1
    return sorted(out, key=lambda r: -r["depth"])


def stationary_bootstrap(n, block, rng):
    p = 1.0 / block
    idx = np.empty(n, np.int64)
    idx[0] = rng.integers(n)
    jump = rng.random(n) < p
    starts = rng.integers(n, size=n)
    for i in range(1, n):
        idx[i] = starts[i] if jump[i] else (idx[i - 1] + 1) % n
    return idx


def ols_nw(y, X, lags):
    y, X = np.asarray(y, float), np.asarray(X, float)
    n, k = X.shape
    XtX_inv = np.linalg.inv(X.T @ X)
    b = XtX_inv @ X.T @ y
    e = y - X @ b
    S = (X * e[:, None]).T @ (X * e[:, None])
    for L in range(1, lags + 1):
        w = 1.0 - L / (lags + 1.0)
        G = (X[L:] * e[L:, None]).T @ (X[:-L] * e[:-L, None])
        S += w * (G + G.T)
    V = XtX_inv @ S @ XtX_inv
    se = np.sqrt(np.diag(V))
    return b, b / se


def dm_hln(d, h, lags):
    """Diebold-Mariano on loss differential d (positive = challenger better), Newey-West variance, Harvey-Leybourne-Newbold correction, one-sided."""
    from scipy import stats as sst
    d = np.asarray(d, float)
    n = len(d)
    mu = d.mean()
    e = d - mu
    v = float(e @ e) / n
    for L in range(1, lags + 1):
        v += 2.0 * (1.0 - L / (lags + 1.0)) * float(e[L:] @ e[:-L]) / n
    dm = mu / math.sqrt(v / n) if v > 0 else float("nan")
    k = math.sqrt((n + 1 - 2 * h + h * (h - 1) / n) / n)
    stat = dm * k
    return stat, float(1.0 - sst.t.cdf(stat, n - 1))


# ------------------------------------------------------------------ the round
def e1(B, ms):
    raw = st_on(B, B.raw, IS0, IS1)
    v2 = st_on(B, B.sized(ms["V2"]), IS0, IS1)
    return {"raw": raw, "v2": v2, "pass": bool(v2["roc"] > raw["roc"] and v2["sort"] > raw["sort"] and v2["cdr"] > raw["cdr"])}


def e2(B, ms):
    out = {}
    pre = B.pre_n
    rng = np.random.default_rng(SEED)
    boots = [stationary_bootstrap(pre, BLOCK, rng) for _ in range(NBOOT)]
    # addendum 2: the verdict spans are ALL / ALLX (2011-01-03..2025-06-29, without the 2020 rows for ALLX) - ~60% more volatility
    # regimes than WF alone; WF / EX are computed and reported beside them
    for name, lo, ex in (("ALL", IS0, None), ("ALLX", IS0, X20), ("WF", WF0, None), ("EX", WF0, X20)):
        k = B.mask(lo, PRE_END, ex)
        assert not (B.index[k] > PRE_END).any()
        dates = B.index[k]
        base = {s: stats(B.raw[k], dates)[s] for s in ("cdr", "roc")}

        def T(mdict):
            st = {c: stats(B.sized(m)[k], dates) for c, m in mdict.items()}
            r = {}
            for s in ("cdr", "roc"):
                vals = {c: st[c][s] - base[s] for c in mdict}
                r[s] = (max(vals.values()), vals["V2"])
            return r

        real = T(ms)
        nullA = {"cdr": [], "roc": [], "cdr_v2": [], "roc_v2": []}
        ks = list(range(KMIN, pre - KMIN + 1, SMOKE_NULL_STEP))
        for sh in ks:
            r = T({c: np.concatenate([np.roll(m[:pre], sh), m[pre:]]) for c, m in ms.items()})
            for s in ("cdr", "roc"):
                nullA[s].append(r[s][0]); nullA[s + "_v2"].append(r[s][1])
        nullB = {"cdr": [], "roc": [], "cdr_v2": [], "roc_v2": []}
        for ix in boots:
            r = T({c: np.concatenate([m[:pre][ix], m[pre:]]) for c, m in ms.items()})
            for s in ("cdr", "roc"):
                nullB[s].append(r[s][0]); nullB[s + "_v2"].append(r[s][1])
        res = {"real": {s: {"family_max": real[s][0], "v2": real[s][1]} for s in ("cdr", "roc")}, "n_shifts": len(ks), "n_boot": NBOOT}
        for tag, nl in (("A", nullA), ("B", nullB)):
            res["null" + tag] = {
                "p95_cdr_family": float(np.percentile(nl["cdr"], 95)),
                "p_cdr_family": float(np.mean(np.asarray(nl["cdr"]) >= real["cdr"][0])),   # share of null draws at or above the real T
                "pct_cdr_family": float(np.mean(np.asarray(nl["cdr"]) < real["cdr"][0]) * 100),
                "pct_cdr_v2": float(np.mean(np.asarray(nl["cdr_v2"]) < real["cdr"][1]) * 100),
                "pct_roc_family": float(np.mean(np.asarray(nl["roc"]) < real["roc"][0]) * 100),
                "pct_roc_v2": float(np.mean(np.asarray(nl["roc_v2"]) < real["roc"][1]) * 100),
                "dist_cdr_family": nl["cdr"]}
        # addendum 2: ">= the 95th percentile" read strictly - at most 5% of the null draws at or above T (p <= 0.05), no interpolation
        res["pass"] = bool(res["nullA"]["p_cdr_family"] <= 0.05 and res["nullB"]["p_cdr_family"] <= 0.05)
        out[name] = res
    out["pass"] = bool(out["ALL"]["pass"] and out["ALLX"]["pass"])
    return out


def e3(B, ms, engq_leg):
    out = {}
    m = ms["V2"]
    v2 = B.sized(m)
    for name, ex in (("ALL", None), ("ALLX", X20)):
        k = B.mask(IS0, PRE_END, ex)
        rows = np.flatnonzero(k)
        dates = B.index[k]
        xr, xv = B.raw[k], v2[k]
        nr, nv = float(xr.sum()), float(xv.sum())
        if nv <= 0 or nr <= 0:                                         # equal-net scaling needs both books to make money on the span
            out[name] = {"pass": False, "note": f"net <= 0 on the span (RAW {nr:,.0f}, V2 {nv:,.0f}) - cannot be scaled to equal net"}
            continue
        c = nr / nv
        ur, uv = underwater(xr, dates)[:5], underwater(c * xv, dates)[:5]
        dr = [u["depth"] for u in ur] + [0.0] * (5 - len(ur))
        dv = [u["depth"] for u in uv] + [0.0] * (5 - len(uv))
        wins = int(sum(1 for a, b_ in zip(dv, dr) if a < b_))
        # the 58b mechanism inside each of V2's five: ENGU-Q positions entered at m > 1, open at the peak
        diag = []
        for u in uv:
            pr, tr_ = rows[max(u["i0"] - 1, 0)], rows[u["it"]]
            sel_t = np.flatnonzero((B.leg == engq_leg) & (m[B.erow] > 1.0) & (B.erow <= pr) & (B.xrow > pr))
            if len(sel_t):
                inc = np.isin(B.inc_t, sel_t) & (B.inc_row > pr) & (B.inc_row <= tr_)
                lost = float(c * (B.inc_v[inc] * m[B.erow[B.inc_t[inc]]]).sum())
            else:
                lost = 0.0
            diag.append({"peak": u["peak"], "trough": u["trough"], "depth": u["depth"], "engq_upsized_open_trades": int(len(sel_t)),
                         "engq_upsized_pnl_in_drawdown": lost})
        out[name] = {"c": c, "raw_top5": [{kk: u[kk] for kk in ("depth", "peak", "trough", "end")} for u in ur],
                     "v2_top5": [{kk: u[kk] for kk in ("depth", "peak", "trough", "end")} for u in uv], "ranks_v2_shallower": wins,
                     "sum_raw": float(sum(dr)), "sum_v2": float(sum(dv)), "diag_58b": diag,
                     "pass": bool(wins >= 4 and sum(dv) < sum(dr))}
    out["pass"] = bool(out["ALL"]["pass"] and out["ALLX"]["pass"])
    # V2's own deepest WF drawdown (10o's $35,304), named, unscaled
    kw = B.mask(WF0, PRE_END)
    uw = underwater(v2[kw], B.index[kw])
    out["v2_wf_deepest_unscaled"] = {kk: uw[0][kk] for kk in ("depth", "peak", "trough", "end")} if uw else None
    if uw:
        a, z = TS(uw[0]["peak"]), TS(uw[0]["trough"])
        kk = B.mask(a, z)
        out["v2_wf_deepest_unscaled"]["raw_change_same_dates"] = float(B.raw[kk].sum())
    return out


def reports(B, ms, BS_other, legs_meta):
    rep = {}
    m = ms["V2"]
    v2 = B.sized(m)
    legx = [B.Am_leg[k].T @ B.ones for k in range(len(legs_meta))]
    # R1 spanning
    r1 = {}
    for name, lo, hi, ex in (("IS*", IS0, IS1, None), ("WF", WF0, PRE_END, None), ("EX", WF0, PRE_END, X20)):
        k = B.mask(lo, hi, ex)
        y = v2[k]
        X1 = np.column_stack([np.ones(k.sum()), B.raw[k]])
        b1, t1 = ols_nw(y, X1, 10)
        X4 = np.column_stack([np.ones(k.sum())] + [lx[k] for lx in legx])
        b4, t4 = ols_nw(y, X4, 10)
        r1[name] = {"book": {"a_per_day": float(b1[0]), "t_a": float(t1[0]), "b": float(b1[1])},
                    "legs": {"a_per_day": float(b4[0]), "t_a": float(t4[0]), "b": [float(x) for x in b4[1:]]}}
    rep["R1_spanning"] = r1
    # R2 dissection
    engq = [k for k, l in enumerate(legs_meta) if "ENGUQ" in l["strategy"].upper()]
    parts = {"engq_only": engq, "intraday_only": [k for k in range(len(legs_meta)) if k not in engq]}
    r2 = {}
    for pname, ks in parts.items():
        x = sum((B.Am_leg[k].T @ (m if k in ks else B.ones)) for k in range(len(legs_meta)))
        sel = np.isin(B.leg, ks) & B.pre_trade                               # no lockbox trade (review 2026-10-03)
        up, dn = sel & (m[B.erow] > 1.0), sel & (m[B.erow] < 1.0)
        pf = lambda msk: float(B.closed[msk][B.closed[msk] > 0].sum() / -B.closed[msk][B.closed[msk] < 0].sum()) if (B.closed[msk] < 0).any() else float("nan")
        r2[pname] = {"IS*": st_on(B, x, IS0, IS1), "WF": st_on(B, x, WF0, PRE_END), "EX": st_on(B, x, WF0, PRE_END, X20),
                     "pf_sized_up": pf(up), "pf_sized_down": pf(dn), "n_up": int(up.sum()), "n_down": int(dn.sum())}
    rep["R2_dissection"] = r2
    # R3 micros
    from scipy import sparse
    s = np.array([legs_meta[k]["weight"] for k in B.leg]) * B.fsize * m[B.erow]   # contracts actually traded (NOISE's own tilt included)
    full = np.floor(s + 1e-9)
    frac = s - full
    micros = np.round(frac * 10.0)
    full_rt = np.array([legs_meta[k]["cost_pts"] * legs_meta[k]["mult"] for k in B.leg])
    micro_rt = np.array([MICRO_RT.get(legs_meta[k]["instrument"], MICRO_RT["NQ"]) for k in B.leg])
    extra = micros * micro_rt - frac * full_rt
    xc = v2 - np.bincount(B.xrow, weights=extra, minlength=B.n)
    rep["R3_micros"] = {"IS*": st_on(B, xc, IS0, IS1), "WF": st_on(B, xc, WF0, PRE_END), "extra_cost_total_pre": float(extra[B.pre_trade].sum()),
                        "trades_with_micros_pre": int(((micros > 0) & B.pre_trade).sum())}
    # R4 clocks (needs the S book)
    if BS_other is not None:
        mS = BS_other.mult("V2")
        assert len(B.erow) == len(BS_other.erow) and (B.leg == BS_other.leg).all(), "U and S records are not the same trades in the same order"
        pre = B.pre_trade & BS_other.pre_trade
        engq_t = np.isin(B.leg, engq) & pre
        differs = B.entry_day != BS_other.entry_day                          # the raw stamps, not the index rows they map to
        rep["R4_clocks"] = {"engq_entries_pre": int(engq_t.sum()), "engq_entry_day_differs": int((differs & engq_t).sum()),
                            "engq_share_differs": float((differs & engq_t).sum() / max(1, engq_t.sum())),
                            "sizes_differ_pre": int(((m[B.erow] != mS[BS_other.erow]) & pre).sum()), "trades_pre": int(pre.sum()),
                            "share_sizes_differ_pre": float(((m[B.erow] != mS[BS_other.erow]) & pre).sum() / max(1, pre.sum()))}
    # R5 the forecast question (+ Kronos step 0 beside it, if it has reported)
    rep["R5_forecast"] = r5(B)
    rep["R5_forecast"]["kronos_step0"] = kronos_result()
    return rep


def kronos_result():
    """Kronos step 0 (docs/PREREG_kronos_step0_2026-10-01.md) has no fixed result path in git; report whatever result it has left."""
    found = []
    doc = os.path.join(REPO, "docs", "PREREG_kronos_step0_2026-10-01.md")
    if os.path.exists(doc):
        import re
        txt = open(doc, encoding="utf-8", errors="replace").read()
        hit = re.search(r"(?im)^\s*#*\s*RESULT\b", txt)                  # a RESULT heading / line, not a passing mention
        if hit:
            found.append({"source": doc, "excerpt": txt[hit.start():hit.start() + 1500]})
    for p in sorted(glob.glob(os.path.join(os.environ.get("EDGELOG_KRONOS_DIR", r"C:\EdgeLog\kronos"), "**", "*result*"), recursive=True))[:5]:
        found.append({"source": p, "excerpt": open(p, encoding="utf-8", errors="replace").read()[:1500]})
    return found or "no Kronos step-0 result found"


def r5(B):
    x = B.raw[:B.pre_n]
    dates = B.index[:B.pre_n]
    n = len(x)
    x2 = x ** 2
    H = 20
    RV = np.full(n, np.nan)
    cs = np.concatenate([[0.0], np.cumsum(x2)])
    RV[:n - H + 1] = (cs[H:] - cs[:-H]) / H                        # RV_t = mean(x_t^2 .. x_(t+19)^2)
    naive = pd.Series(x).shift(1).rolling(20, min_periods=20).std().to_numpy() ** 2
    f1 = np.concatenate([[np.nan], x2[:-1]])
    f5 = pd.Series(x2).shift(1).rolling(5, min_periods=5).mean().to_numpy()
    f22 = pd.Series(x2).shift(1).rolling(22, min_periods=22).mean().to_numpy()
    har = np.full(n, np.nan)
    years = sorted(set(dates.year))
    for Y in years:
        if Y < 2013:
            continue
        r0 = int(np.searchsorted(dates.values, np.datetime64(f"{Y}-01-01"), side="left"))
        r1_ = int(np.searchsorted(dates.values, np.datetime64(f"{Y + 1}-01-01"), side="left"))
        tr = np.arange(22, max(22, r0 - H + 1))                       # target ended before the refit date: t + 19 < r0
        tr = tr[np.isfinite(RV[tr]) & np.isfinite(f1[tr]) & np.isfinite(f5[tr]) & np.isfinite(f22[tr])]
        X = np.column_stack([np.ones(len(tr)), f1[tr], f5[tr], f22[tr]])
        b = np.linalg.lstsq(X, RV[tr], rcond=None)[0]
        for t in range(r0, min(r1_, n)):
            h = b[0] + b[1] * f1[t] + b[2] * f5[t] + b[3] * f22[t]
            known = RV[max(0, t - H - 249):max(0, t - H + 1)]            # CHOICE: the floor's median uses only RVs fully realised before t (s + 19 <= t - 1)
            known = known[np.isfinite(known)]
            floor = 0.1 * float(np.median(known)) if len(known) else 0.0
            har[t] = max(h, floor)
    def ql(rv, h):
        r = rv / h
        return r - np.log(r) - 1.0
    out = {}
    for name, lo, hi in (("2013-2016H1", TS("2013-01-02"), IS1), ("WF", WF0, PRE_END)):
        k = np.asarray((dates >= lo) & (dates <= hi)) & np.isfinite(RV) & (RV > 0) & np.isfinite(naive) & (naive > 0) & np.isfinite(har) & (har > 0)
        Ln, Lh = ql(RV[k], naive[k]), ql(RV[k], har[k])               # CHOICE: rows where either forecast is not positive are dropped (recorded as n)
        stat, p = dm_hln(Ln - Lh, H, 19)
        gain = float((Ln.mean() - Lh.mean()) / Ln.mean() * 100.0)
        out[name] = {"n": int(k.sum()), "qlike_naive": float(Ln.mean()), "qlike_har": float(Lh.mean()), "gain_pct": gain, "dm_hln": stat, "p_one_sided": p,
                     "clears": bool(gain >= 5.0 and p < 0.05)}
    out["better_forecast_exists"] = bool(out["2013-2016H1"]["clears"] and out["WF"]["clears"])
    out["read"] = ("a better risk forecast exists for this book (report only - the house's test of that question is round 62 V3, addendum 3)"
                   if out["better_forecast_exists"] else
                   "no better risk forecast than V2's own on this read (report only - round 62 V3 is the house's test, addendum 3)")
    return out


def run():
    check_prereg()
    if not os.path.exists(_ready_path()):
        raise SystemExit("refused: parity (P1-P4) has not passed - run build, then parity")
    with open(_ready_path()) as f:
        ready = json.loads(f.read() or "{}")
    if ready.get("sha256") != _record_hashes():
        raise SystemExit("refused: the records changed after parity passed (build was re-run?) - run parity again")
    b = load_json("build.json")
    if not b.get("P1_pass"):
        raise SystemExit("refused: P1 has not passed on these records")
    legs_meta = b["legs"]
    engq_leg = [k for k, l in enumerate(legs_meta) if "ENGUQ" in l["strategy"].upper()]
    engq_leg = engq_leg[0] if engq_leg else -1
    books = {r: load_book(r, legs_meta) for r in ("U", "S")}
    res = {"E1": {}, "E2": {}, "E3": {}}
    for rule, B in books.items():
        ms = {c: B.mult(c) for c in CELLS}
        res["E1"][rule] = e1(B, ms)
        res["E2"][rule] = e2(B, ms)
        res["E3"][rule] = e3(B, ms, engq_leg)
        print(rule, "E1", res["E1"][rule]["pass"], "E2", res["E2"][rule]["pass"], "E3", res["E3"][rule]["pass"], flush=True)
    E = {t: bool(all(res[t][r]["pass"] for r in ("U", "S"))) for t in ("E1", "E3")}
    E["E2"] = bool(res["E2"]["U"]["pass"])                                   # addendum 2026-10-03: E2 on rule U; rule S reported
    verdict = "PASS" if all(E.values()) else ("INCONCLUSIVE" if E["E1"] and E["E3"] else "FAIL")   # addendum 2
    rep = reports(books["U"], {c: books["U"].mult(c) for c in CELLS}, books["S"], legs_meta)
    save("e1.json", res["E1"]); save("e2.json", res["E2"]); save("e3.json", res["E3"]); save("reports.json", rep)
    lines = [f"RISK r1 - PRIMARY VERDICT: {verdict}   (E1 {E['E1']}, E2 {E['E2']}, E3 {E['E3']}; E1 and E3 on rule U AND rule S, E2 on rule U - addendum)",
             f"prereg sha256 {PREREG_SHA}",
             {"PASS": "PASS -> an explicit owner question: adopt V2 sizing on #463 now as a real BOOK run (book_sizing block), rather than wait for "
                      "the 12-month VT read.",
              "INCONCLUSIVE": "INCONCLUSIVE -> V2 helps on the IS* read and at equal net on the five deepest drawdowns, but its timing is not "
                              "distinguishable from chance with ~15 years of regimes; no adoption from the backtest, the VT shadow decides.",
              "FAIL": "FAIL -> the backtest case for V2 is closed; the VT line stays a forward shadow under its own pre-registration."}[verdict],
             "R5 (risk forecast, the only ML role this round funds): " + rep["R5_forecast"]["read"]]
    for rule in ("U", "S"):
        e1r, e2r, e3r = res["E1"][rule], res["E2"][rule], res["E3"][rule]
        lines.append(f"[{rule}] E1 IS*: RAW roc {e1r['raw']['roc']:.1f} sort {e1r['raw']['sort']:.3f} cdr {e1r['raw']['cdr']:.1f} | "
                     f"V2 roc {e1r['v2']['roc']:.1f} sort {e1r['v2']['sort']:.3f} cdr {e1r['v2']['cdr']:.1f} -> {e1r['pass']}")
        for s in ("ALL", "ALLX", "WF", "EX"):
            q = e2r[s]
            lines.append(f"[{rule}] E2 {s}{'' if rule == 'U' and s in ('ALL', 'ALLX') else ' (reported)'}: family-max dCDR {q['real']['cdr']['family_max']:+.2f}; "
                         f"p nullA {q['nullA']['p_cdr_family']:.3f} nullB {q['nullB']['p_cdr_family']:.3f} (pct V2 alone "
                         f"{q['nullA']['pct_cdr_v2']:.1f}/{q['nullB']['pct_cdr_v2']:.1f}) -> {q['pass']}")
        for s in ("ALL", "ALLX"):
            q = e3r[s]
            if "ranks_v2_shallower" in q:
                lines.append(f"[{rule}] E3 {s}: V2 shallower at {q['ranks_v2_shallower']}/5 ranks, top-5 sum ${q['sum_v2']:,.0f} vs ${q['sum_raw']:,.0f} -> {q['pass']}")
            else:
                lines.append(f"[{rule}] E3 {s}: {q.get('note')} -> False")
    with open(os.path.join(OUT, "VERDICT.txt"), "w") as f:
        f.write("\n".join(lines) + "\n")
    print("\n".join(lines), flush=True)
    return verdict


# ------------------------------------------------------------------ smoke: a synthetic world through the engine's real leg runner
def smoke(d, world="null"):
    """Synthetic legs shaped like #463's (intraday NQ legs, a multi-day ENGU-Q-like leg with evening fills, a 3-contract ES leg), clustered
    volatility with a constant edge per unit of risk; the data layer and the strategy run are faked, everything else is the house code path.
    Checks: P1 and P4 pass; one null draw rebuilt trade by trade through augur_engine.book_sizing.resize equals the sparse matrices; the
    refusals fire. world="planted" makes the edge negative when volatility is high (the mechanism V2 needs) and asserts E2 passes on
    rule U and the whole primary verdict passes - the test has power; world="null" keeps a constant edge per unit of risk. Its numbers mean nothing.""" 
    global OUT, CHECK_REFS, SMOKE_NULL_STEP, NBOOT, R62_DIR
    root = os.path.abspath(d)
    assert "smoke" in os.path.basename(root).lower() and not os.path.normcase(root).startswith(os.path.normcase(r"C:\EdgeLog")), \
        "smoke needs its own scratch folder (name contains 'smoke'), never a real cache"
    os.makedirs(root, exist_ok=True)
    OUT, R62_DIR = root, os.path.join(root, "no_r62_here")
    CHECK_REFS, SMOKE_NULL_STEP, NBOOT = False, 40, 60
    import augur_engine.book as BK
    import augur_engine.strategies as STR
    from augur_engine import book_sizing as BSZ
    rng = np.random.default_rng(7)
    idx = pd.date_range("2010-06-01 00:00", "2026-07-02 23:30", freq="30min", tz="US/Eastern")
    idx = idx[idx.dayofweek != 5]
    days = idx.tz_localize(None).normalize()
    udays = days.unique()
    lv = np.zeros(len(udays))                                          # persistent log-vol, one value a day
    for i in range(1, len(udays)):
        lv[i] = 0.985 * lv[i - 1] + rng.normal(0, 0.12)
    sig_day = pd.Series(np.exp(lv), index=udays)
    sig_bar = sig_day.reindex(days).to_numpy()
    close = 5000.0 + np.cumsum(rng.normal(0.02, 6.0, len(idx)) * sig_bar)
    ARR = {"index": idx, "open": close, "high": close + 3, "low": close - 3, "close": close, "volume": np.ones(len(idx)),
           "day_id": pd.factorize(days)[0], "meta": {"name": "synthetic"}}
    bar_of = pd.Series(np.arange(len(idx)), index=idx)
    trades = {}
    legs = book_legs()
    for k, leg in enumerate(legs):
        r = np.random.default_rng(100 + k)
        tl = []
        for dday in pd.bdate_range("2010-06-08", "2026-06-29"):
            s = float(sig_day.get(dday, 1.0))
            if "ENGUQ" in leg["strategy"]:
                if r.random() > 0.08:
                    continue
                e_ts, x_ts = pd.Timestamp(f"{dday.date()} 21:00", tz="US/Eastern"), pd.Timestamp(f"{(dday + pd.Timedelta(days=int(r.integers(1, 9)))).date()} 22:00", tz="US/Eastern")
            else:
                if r.random() > (0.3 if "TTM" in leg["strategy"] else 0.8):
                    continue
                e_ts, x_ts = pd.Timestamp(f"{dday.date()} 10:00", tz="US/Eastern"), pd.Timestamp(f"{dday.date()} 15:30", tz="US/Eastern")
            if e_ts not in bar_of.index or x_ts not in bar_of.index:
                continue
            e, x = int(bar_of[e_ts]), int(bar_of[x_ts])
            side = 1 if r.random() < 0.55 else -1
            if world == "planted":                                     # the mechanism, planted: the edge turns negative when vol is high
                pts = float(s * (r.normal(0.45 - 0.5 * max(0.0, s - 2.0), 2.5)) * 4.0)
            else:                                                      # null world: a constant edge per unit of risk
                pts = float(s * (r.normal(0.25, 2.5)) * 4.0)
            tl.append((e, x, pts, side, float(close[e])))
        trades[leg["strategy"]] = tl
    saved = (BK.run_backtest, BK.find_master, BK.load_master_arrays, STR.load_strategy)
    BK.run_backtest = lambda strategy, arrays=None, params=None, cost_pts=0.0, return_trades=True: {"trades": list(trades[strategy])}
    BK.find_master = lambda inst, tf, sess, src: {"name": "synthetic", "source": src}
    BK.load_master_arrays = lambda master, date_from=None, date_to=None: ARR

    def _nostrat(name):
        raise ImportError(name)
    STR.load_strategy = _nostrat
    try:
        build()
        b = load_json("build.json")
        assert b["P1_pass"], "smoke: P1 must pass on the house code path"
        parity()
        p = load_json("parity.json")
        assert p["P4"]["ok"], f"smoke: the engine's book_sizing run must equal the harness: {p['P4']}"
        # brute force: one shifted null draw, rebuilt trade by trade through the engine's own re-pricing
        Bm = load_book("U", b["legs"])
        m = Bm.mult("V2")
        pre = Bm.pre_n
        msh = np.concatenate([np.roll(m[:pre], 777), m[pre:]])
        fast = Bm.sized(msh)
        slow = pd.Series(0.0, index=Bm.index)
        ixd = Bm.index.values.astype("datetime64[D]")
        for k, leg in enumerate(legs):
            tr, info = BK._leg_trades(dict(leg), W0, W1, keep_state=True)
            st = info["_state"]
            look = lambda t, _st=st: msh[int(np.searchsorted(ixd, BSZ.entry_day(_st, t), side="left"))]
            mt = BSZ.resize(st, look)[2]
            slow = slow.add(BSZ.daily_series(mt, Bm.index), fill_value=0.0)
        dmax = float(np.abs(slow.reindex(Bm.index).fillna(0.0).to_numpy() - fast).max())
        assert dmax < 1e-6, f"smoke: sparse rebuild differs from the engine's re-pricing by {dmax}"
        # stats sanity on a hand example
        s = stats(np.array([10.0, -5.0, -5.0, 20.0]), pd.bdate_range("2020-01-01", periods=4))
        assert abs(s["max_dd"] - 10.0) < 1e-12 and abs(s["net"] - 20.0) < 1e-12
        u = underwater(np.array([5.0, -3.0, -4.0, 10.0, -1.0, 2.0]), pd.bdate_range("2020-01-01", periods=6))
        assert [round(x["depth"], 6) for x in u] == [7.0, 1.0]
        verdict = run()
        if world == "planted":
            assert verdict == "PASS", "smoke: a planted volatility mechanism must clear the primary verdict (power check)"
        else:
            assert load_json("e2.json")["U"]["ALL"]["nullA"]["p_cdr_family"] > 0.2, "smoke: the null world must sit far from the E2 bar"
        # refusals: records changed after parity, then no READY at all
        with open(_ready_path(), "w") as f:
            f.write(json.dumps({"P1-P4": "passed", "sha256": {"records_U.npz": "0" * 64}}))
        try:
            run()
            raise AssertionError("smoke: run() must refuse when the records are not the ones parity passed")
        except SystemExit:
            pass
        os.remove(_ready_path())
        try:
            run()
            raise AssertionError("smoke: run() must refuse without READY")
        except SystemExit:
            pass
        print(f"SMOKE OK (brute-force max diff {dmax:.2e}; synthetic verdict {verdict} - meaningless)", flush=True)
    finally:
        BK.run_backtest, BK.find_master, BK.load_master_arrays, STR.load_strategy = saved


if __name__ == "__main__":
    cmd = sys.argv[1:]
    if cmd == ["build"]:
        build()
    elif cmd == ["parity"]:
        parity()
    elif cmd == ["run"]:
        run()
    elif len(cmd) in (2, 3) and cmd[0] == "smoke":
        smoke(cmd[1], *(cmd[2:] or ["null"]))
    else:
        print(__doc__ or "usage: r11_risk.py build | parity | run | smoke DIR")
        sys.exit(2)
