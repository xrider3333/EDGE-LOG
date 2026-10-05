# Round 14 (2026-10-04): BOOK LOOKS r1 - how many lockbox looks the frontier bar has absorbed, and the margin a pass must carry to be more than luck.
# Pre-registered: tools/rocfrontier/PREREG_LOOKS_R1.txt - PREREG_SHA below is that file's canonical-LF sha256 (R11.sha_lf). Step 1 writes the csv's
# sha into the prereg as pre-data addendum 1, so PREREG_SHA and LEDGER_SHA are updated TOGETHER in that commit, before `parity` runs on the box.
# Every rule, seed, grid and list is that file; where it is silent the choice is marked CHOICE.
#   python r14_looks.py ledger            step 1: LOOKS_LEDGER_R1.csv -> canonical-LF sha, K_book / K_size / K_leg / K_lane, the ten calibration ratios
#                                         (exit 2 'ledger not yet registered' while LEDGER_SHA is "TBD"; refuses a sha that is not the registered one)
#   python r14_looks.py parity            step 2: r11's records_U.npz (its READY + hashes checked) -> raw #463 reproduces WF 93.81 / 3.816 and LB
#                                         155.54 / 4.150 within r11's P2_TOL; per-leg WF / LB trade counts; the largest LB closed trade; READY on a pass
#   python r14_looks.py run               steps 3-5: N-LEG (4 x 10,000 centred bootstrap draws) + N-SIZE (every V2 shift) -> margin curve, g*, g_adj,
#                                         ladder, past passes -> LOOKS.txt, margin_curve.csv, past_passes.csv, nulls.json, draws.npz, docs/LOOKS_R1.md;
#                                         refuses without READY or when the prereg, the ledger or the records changed after parity
#   python r14_looks.py smoke DIR [null|planted]   offline synthetic world built by r11_risk.smoke (DIR's name must contain 'smoke'); 'planted' widens
#                                         the N-LEG spread so g* moves; its numbers mean nothing
# Reuses r11_risk.py by import: Book / load_book / stats / unified / stationary_bootstrap / sha_lf / the record hashes / the windows. Results go to OUT
# (outside git) and the one-page doc; nothing here commits, pushes, queues a job or reads any candidate's sealed row.
import csv, json, math, os, sys, time
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.environ.get("EDGELOG_ROOT", r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"); sys.path.insert(0, REPO); sys.path.insert(0, HERE)
import numpy as np, pandas as pd
import r11_risk as R11

OUT = os.environ.get("EDGELOG_ROCFRONTIER_LOOKS", r"C:\EdgeLog\_anatomy_cache\rocfrontier\looks_r1")
DOC = os.environ.get("EDGELOG_LOOKS_DOC", os.path.join(REPO, "docs", "LOOKS_R1.md"))
PREREG = os.path.join(HERE, "PREREG_LOOKS_R1.txt")
PREREG_SHA = "26957d922b2cd61ce2acf8f30641511797db9b8d9fbd8a6f08423a0fdf413a62"      # canonical-LF sha256 of the prereg WITH pre-data addendum 1 (2026-10-05)
LEDGER = os.path.join(HERE, "LOOKS_LEDGER_R1.csv")
LEDGER_SHA = "f55656b4f1481917efdcef1c7e779bd6fb8f5728ac31396cb2fc86174d118f52"      # LOOKS_LEDGER_R1.csv, registered by addendum 1
COLS = ("id", "date", "source", "candidate", "type", "reference_in_force", "convention", "wf_roc", "wf_sortino", "lb_roc", "lb_sortino",
        "ref_lb_roc", "lb_ratio", "verdict_as_printed", "dup_of", "judgment")
LOOK_TYPES = ("SWAP", "ADD", "COMBO", "SIZE")
WF_BAR, LB_BAR = (98.50, 3.816), (155.54, 4.150)             # today's bar as written (prereg REFERENCE)
WF_PREM = WF_BAR[0] / R11.P2_REF["unified"]["WF"][0]         # 98.50 / 93.81: the WF clause's own premium over the reference
NLEG_B, SEED0, BLOCK, KMIN = 10000, 20261004, 21, 250
GRID = np.round(np.arange(0.0, 1.0 + 1e-9, 0.005), 3)       # 201 margins, ratio units: LB ROC >= 155.54 x (1 + g)
LEVELS = (0.025, 0.05, 0.10)
CALIB = ("#468", "#469", "#470", "Q1a", "Q1b", "Q2", "Q2ctx", "Q3", "Q5", "Q6")
PAST = (("58d", ("58d",)), ("#444", ("#444",)), ("#449", ("#449",)),
        ("round-61 best", ("round-61 best", "round 61 best", "r61best", "r61-best", "round-61")),
        ("V2", ("V2",)), ("V2-500", ("V2-500",)), ("Q4", ("Q4",)), ("Q6", ("Q6",)))
CONTEXT = {"#449": "adopted on more than the lockbox (clauses 1-8, BOOK.md 10m)", "V2": "failed RISK r1", "Q4": "post-hoc",
           "Q6": "ORB #239 in the ORB seat is a forward shadow"}
LADDER = (1, 10, 50, "K_book", 100, "2K_book", "K_ceiling", 500)        # addendum 1: K = 1, 10, 50, 71, 100, 142, 181, 500
K_CEILING = 181                                                          # addendum 1: every candidate scored on the lockbox, printed or not
# addendum 1: the cumulative K_book in force when each past pass was read (ledger order within a day; a pass that is itself a dup row
# does not add to its own count) - registered numbers, not recomputed from dates
K_THEN = {"58d": 17, "#444": 30, "#449": 31, "round-61 best": 35, "V2": 49, "V2-500": 50, "Q4": 63, "Q6": 63}
R_BAND = (0.5, 2.0)
TOP_EXPECT = ("ENGU-Q", "2026-05-12", 91152.0, 1.0)          # (leg, exit day, closed $, $ tolerance) - BOOK.md 10l addendum C
FAM = (("ENGUQ", "ENGU-Q"), ("ORB", "ORB"), ("TTM", "TTM"), ("NOISE", "NOISE"))
CHECK_REFS = True        # a real run holds the raw book to the printed figures and the uncentred null to the bar as written; only smoke() switches it
SMOKE_TBD_OK = False     # only smoke() tolerates LEDGER_SHA == "TBD"
SIZE_STEP = 1            # every shift k; smoke() thins
PLANT_SIGMA = 0.0        # smoke 'planted' only: each N-LEG draw's resampled rows + N(0, sigma) x their sd as a per-draw drift - an obviously wider spread


def asc(s):
    return str(s).encode("ascii", "backslashreplace").decode("ascii")        # console and files stay ASCII (cp1252 on the box)


def save(name, obj):
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, name), "w") as f:
        f.write(json.dumps(obj, indent=1, default=R11.js))


def _ready_path():
    return os.path.join(OUT, "READY")


def check_prereg(path=None, want=None):
    path, want = path or PREREG, want or PREREG_SHA
    got = R11.sha_lf(path)
    if want == "TBD":
        raise SystemExit(f"refused: PREREG_SHA is 'TBD' - the prereg is not registered yet (the file hashes to {got})")
    if got != want:
        raise SystemExit(f"refused: {os.path.basename(path)} sha256 {got} is not the registered {want} - the plan changed after it was registered")
    return got


# ------------------------------------------------------------------ step 1: the looks ledger
def _f(s):
    try:
        return float(str(s).replace(",", "").replace("$", "").replace("%", ""))
    except (TypeError, ValueError):
        return float("nan")


def _date(s):
    t = pd.to_datetime(s, errors="coerce") if s else pd.NaT
    return None if pd.isna(t) else pd.Timestamp(t)


def read_ledger(path=None):
    path = path or LEDGER
    if not os.path.isfile(path):
        raise SystemExit(f"refused: ledger csv not found: {path} (step 1 writes it)")
    with open(path, newline="", encoding="utf-8-sig") as f:
        rows = [{k.strip(): (v or "").strip() for k, v in r.items() if isinstance(k, str)} for r in csv.DictReader(f)]
    miss = [c for c in COLS if rows and c not in rows[0]]
    if miss:
        raise SystemExit(f"refused: ledger csv lacks column(s) {miss}; expected {list(COLS)}")
    return rows


def ledger_sha(path=None):
    path = path or LEDGER
    if not os.path.isfile(path):
        raise SystemExit(f"refused: ledger csv not found: {path}")
    return R11.sha_lf(path)


def check_ledger():
    """The csv's canonical-LF sha against the registered LEDGER_SHA; exit 2 while it is 'TBD' (smoke() tolerates that)."""
    got = ledger_sha()
    if LEDGER_SHA == "TBD":
        if SMOKE_TBD_OK:
            return got
        print(f"ledger not yet registered: LEDGER_SHA is 'TBD' (the csv hashes to {got}) - write it into the prereg as addendum 1 first", flush=True)
        raise SystemExit(2)
    if got != LEDGER_SHA:
        raise SystemExit(f"refused: ledger sha256 {got} is not the registered {LEDGER_SHA} - the ledger changed after it was registered")
    return got


def _typ(r):
    return (r.get("type") or "").strip().upper()


def counts(rows):
    """The registered COUNTING RULE: a look = a non-dup row of type SWAP / ADD / COMBO / SIZE; K_size = SIZE, K_leg = the rest; LANE rows are
    K_lane (reported, not in the formula; CHOICE: the same dup rule); REF rows are context."""
    looks = [r for r in rows if _typ(r) in LOOK_TYPES and not r.get("dup_of")]
    lane = [r for r in rows if _typ(r) == "LANE" and not r.get("dup_of")]
    size = [r for r in looks if _typ(r) == "SIZE"]
    other = [r for r in rows if _typ(r) not in LOOK_TYPES + ("LANE", "REF")]
    return {"K_book": len(looks), "K_size": len(size), "K_leg": len(looks) - len(size), "K_lane": len(lane), "n_rows": len(rows),
            "n_ref": sum(1 for r in rows if _typ(r) == "REF"), "n_dup": sum(1 for r in rows if r.get("dup_of")), "n_other_type": len(other)}, looks


def ratio_of(r):
    """The row's LB ratio to its reference: the lb_ratio column, else lb_roc / ref_lb_roc (CHOICE)."""
    v = _f(r.get("lb_ratio"))
    if not np.isfinite(v):
        a, b = _f(r.get("lb_roc")), _f(r.get("ref_lb_roc"))
        v = a / b if np.isfinite(a) and np.isfinite(b) and b > 0 else float("nan")
    return v


def _tokens(r):
    return [w for w in (t.strip("(),:;[]") for t in (r.get("candidate") or "").split()) if w]


def find_row(rows, tag):
    """The row a prereg tag names: its id, or the first token of its candidate text, then any token (a phrase matches as a substring);
    a non-dup row wins over a dup (CHOICE; `ledger` prints every resolution so the cloud lane can check it)."""
    tl = tag.lower()
    for pool in ([r for r in rows if not r.get("dup_of")], rows):
        for r in pool:
            tk = _tokens(r)
            if (r.get("id") or "").lower() == tl or (tk and tk[0].lower() == tl):
                return r
        for r in pool:
            if tl in [w.lower() for w in _tokens(r)] or (" " in tl and tl in (r.get("candidate") or "").lower()):
                return r
    return None


def find_any(rows, aliases):
    for a in aliases:
        r = find_row(rows, a)
        if r is not None:
            return r
    return None


def calibration_rows(rows):
    return [(tag, find_row(rows, tag)) for tag in CALIB]


def ledger():
    sha = ledger_sha()
    rows = read_ledger()
    K, looks = counts(rows)
    cal = calibration_rows(rows)
    print(f"prereg {os.path.basename(PREREG)} sha256 {R11.sha_lf(PREREG)} (registered {PREREG_SHA})")
    print(f"ledger {os.path.basename(LEDGER)} sha256 {sha} (registered {LEDGER_SHA}); rows {K['n_rows']}, REF {K['n_ref']}, dup {K['n_dup']}, "
          f"other types {K['n_other_type']}")
    print(f"K_book {K['K_book']} = K_leg {K['K_leg']} + K_size {K['K_size']}; K_lane {K['K_lane']} (reported, not in the formula)")
    for tag, r in cal:
        print(asc(f"  calibration {tag:6s} " + (f"ratio {ratio_of(r):.4f} ln {math.log(ratio_of(r)):+.4f}  <- row {r.get('id')} {r.get('candidate')}"
                                              if r is not None and np.isfinite(ratio_of(r)) and ratio_of(r) > 0 else "NOT FOUND / no ratio")))
    for name, aliases in PAST:
        r = find_any(rows, aliases)
        print(asc(f"  past pass   {name:14s} " + (f"ratio {ratio_of(r):.4f}  <- row {r.get('id')} {r.get('candidate')}" if r is not None else "NOT FOUND")))
    check_ledger()
    print("ledger sha accepted (smoke: TBD tolerated)" if LEDGER_SHA == "TBD" else "ledger registered and unchanged", flush=True)
    return sha, K, cal


# ------------------------------------------------------------------ step 2: parity on r11's records
def fam(name):
    u = str(name).upper()
    return next((f for key, f in FAM if key in u), str(name))


def legs_meta():
    b = R11.load_json("build.json")
    if not b.get("P1_pass"):
        raise SystemExit("refused: r11's P1 has not passed on these records")
    meta = b["legs"]
    from api.book_shadow import BOOK463_LEGS
    want = [l["strategy"] for l in BOOK463_LEGS]
    if [m["strategy"] for m in meta] != want:
        raise SystemExit(f"refused: r11 build.json legs {[m['strategy'] for m in meta]} are not BOOK463_LEGS {want}")
    return meta


def load_records():
    rp = R11._ready_path()
    if not os.path.exists(rp):
        raise SystemExit(f"refused: r11's READY is missing under {R11.OUT} - run r11_risk.py build, then parity (no other data path)")
    with open(rp) as f:
        ready = json.loads(f.read() or "{}")
    hashes = R11._record_hashes()
    if ready.get("sha256") != hashes:
        raise SystemExit("refused: r11's records do not match the hashes its READY recorded - run r11_risk.py parity again")
    meta = legs_meta()
    return R11.load_book("U", meta), meta, hashes


def trade_inc(B):
    """{trade -> (rows, $)} of every daily increment, for the trades that close in the lockbox."""
    o = np.argsort(B.inc_t, kind="stable")
    t, row, v = B.inc_t[o], B.inc_row[o], B.inc_v[o]
    cut = np.flatnonzero(np.diff(t)) + 1
    return {int(t[s]): (row[s:e], v[s:e]) for s, e in zip(np.concatenate([[0], cut]), np.concatenate([cut, [len(t)]]))}


def top_lb_trade(B, lb_trades, m=None):
    c = B.closed[lb_trades] * (1.0 if m is None else m[B.erow[lb_trades]])
    return int(lb_trades[np.argmax(c)])


def parity():
    t0 = time.time()
    check_prereg()
    lsha = check_ledger()
    B, meta, hashes = load_records()
    kWF, kLB = B.mask(R11.WF0, R11.PRE_END), B.mask(R11.LB0, R11.LB1)
    got = {"WF": R11.unified(B, B.raw, R11.WF0, R11.PRE_END), "LB": R11.unified(B, B.raw, R11.LB0, R11.LB1)}
    out = {"P2": {}, "legs": [], "pass": True, "refs_checked": CHECK_REFS}
    r11p = R11.load_json("parity.json") if os.path.exists(os.path.join(R11.OUT, "parity.json")) else None
    for s in ("WF", "LB"):
        refs = {}
        if CHECK_REFS:
            refs["printed"] = tuple(R11.P2_REF["unified"][s])
        if r11p is not None:                                   # r11's own P2 on the same records (on a smoke the only reference there is)
            refs["r11_parity"] = (r11p["P2"][f"unified_{s}"]["got"]["roc"], r11p["P2"][f"unified_{s}"]["got"]["sort"])
        oks = {k: abs(got[s]["roc"] - v[0]) < R11.P2_TOL[0] and abs(got[s]["sort"] - v[1]) < R11.P2_TOL[1] for k, v in refs.items()}
        out["P2"][s] = {"got": got[s], "refs": refs, "ok": oks}
        out["pass"] &= all(oks.values())
        print(f"P2 {s}: roc {got[s]['roc']:.3f} sort {got[s]['sort']:.4f} dd {got[s]['dd']:,.0f} net {got[s]['net']:,.0f} vs "
              + ", ".join(f"{k} {v[0]:.3f}/{v[1]:.4f} {'ok' if oks[k] else 'MISS'}" for k, v in refs.items()), flush=True)
    for i, m in enumerate(meta):
        sel = B.leg == i
        nW, nL = int((sel & kWF[B.xrow]).sum()), int((sel & kLB[B.xrow]).sum())        # a trade sits in the stretch its exit falls in (CHOICE)
        out["legs"].append({"leg": i, "family": fam(m["strategy"]), "strategy": m["strategy"], "trades_WF": nW, "trades_LB": nL})
        print(f"leg {i} {fam(m['strategy']):6s} {m['strategy']}: WF trades {nW}, LB trades {nL}")
    lb_trades = np.flatnonzero(kLB[B.xrow])
    j = top_lb_trade(B, lb_trades)
    top = {"trade": j, "leg": int(B.leg[j]), "family": fam(meta[int(B.leg[j])]["strategy"]), "entry": str(B.entry_day[j]),
           "exit": str(B.index[B.xrow[j]].date()), "closed": float(B.closed[j]), "expected": TOP_EXPECT}
    top["as_expected"] = bool(top["family"] == TOP_EXPECT[0] and top["exit"] == TOP_EXPECT[1] and abs(top["closed"] - TOP_EXPECT[2]) <= TOP_EXPECT[3])
    print(f"largest LB closed trade: {top['family']} entry {top['entry']} exit {top['exit']} ${top['closed']:,.0f} "
          f"(expected {TOP_EXPECT[0]} exit {TOP_EXPECT[1]} ${TOP_EXPECT[2]:,.0f}) -> {'ok' if top['as_expected'] else 'NOT the expected trade'}")
    if CHECK_REFS and not top["as_expected"]:                 # CHOICE: LB_x is registered on that trade, so another top trade is a parity miss
        out["pass"] = False
    out["top_lb_trade"] = top
    out["records"], out["prereg_sha256"], out["ledger_sha256"], out["seconds"] = hashes, PREREG_SHA, lsha, round(time.time() - t0, 1)
    save("parity.json", out)
    if not out["pass"]:
        if os.path.exists(_ready_path()):
            os.remove(_ready_path())
        raise SystemExit("parity FAILED - INCONCLUSIVE; see parity.json. Reconcile with r11_risk.py parity / BOOK.md 10r before anything else is computed.")
    with open(_ready_path(), "w") as f:
        f.write(json.dumps({"P2": "passed", "records": hashes, "prereg_sha256": PREREG_SHA, "ledger_sha256": lsha, "got": got}, indent=1, default=R11.js))
    print(f"parity PASS - READY ({out['seconds']}s)", flush=True)


# ------------------------------------------------------------------ steps 3-4: the two nulls and the margin arithmetic
def shifts(n):
    return np.arange(KMIN, n - KMIN + 1, SIZE_STEP)


def excess(v, med):
    """Centred log-excess vs the leg's own draw median; a draw with no positive value never passes (-inf)."""
    v = np.asarray(v, float)
    e = np.full(len(v), -np.inf)
    ok = np.isfinite(v) & (v > 0)
    if np.isfinite(med) and med > 0:
        e[ok] = np.log(v[ok]) - math.log(med)
    return e


def pass_centred(e, sort_ok, prem=1.0):
    """Draws passing at every grid g: e >= ln(prem x (1 + g)) and the Sortino clause."""
    es = np.sort(np.asarray(e, float)[np.asarray(sort_ok, bool) & np.isfinite(e)])
    return len(es) - np.searchsorted(es, np.log(prem * (1.0 + GRID)), side="left")


def pass_uncentred(val, sort, bar):
    """Shifts passing at every grid g, read as printed: val >= bar[0] x (1 + g) and sort >= bar[1]."""
    val, sort = np.asarray(val, float), np.asarray(sort, float)
    vs = np.sort(val[np.isfinite(val) & np.isfinite(sort) & (sort >= bar[1])])
    return len(vs) - np.searchsorted(vs, bar[0] * (1.0 + GRID), side="left")


def fwer(p_leg, p_size, k_leg, k_size):
    return 1.0 - (1.0 - np.asarray(p_leg, float)) ** k_leg * (1.0 - np.asarray(p_size, float)) ** k_size


def g_star(F, level=0.05):
    """The smallest grid g with FWER(g) <= level; None when no grid g reaches it (printed '> 1.0')."""
    i = np.flatnonzero(np.asarray(F, float) <= level)
    return float(GRID[i[0]]) if len(i) else None


def gfmt(g):
    return "> 1.0" if g is None else f"{g:.3f}"


def g_adj(gs, r):
    """g* x max(1, r): the null's spread is scaled UP to the real swaps' when they are noisier, never down (r unknown -> 1)."""
    return None if gs is None else gs * max(1.0, r if np.isfinite(r) else 1.0)


def calibration(ratios, e_pool):
    lr = np.log([x for x in ratios if np.isfinite(x) and x > 0])
    ef = np.asarray(e_pool, float)
    n_all = int(len(ef))
    ef = ef[np.isfinite(ef)]
    sd_real = float(np.std(lr, ddof=1)) if len(lr) >= 2 else float("nan")          # CHOICE: sample sd (ddof 1) on both sides
    sd_null = float(np.std(ef, ddof=1)) if len(ef) >= 2 else float("nan")
    r = sd_real / sd_null if np.isfinite(sd_real) and np.isfinite(sd_null) and sd_null > 0 else float("nan")
    return {"n_real": int(len(lr)), "n_null": int(len(ef)), "n_null_dropped": n_all - int(len(ef)), "sd_real": sd_real, "sd_null": sd_null, "r": r,
            "flag": bool(not np.isfinite(r) or not (R_BAND[0] <= r <= R_BAND[1]))}


def k_split(k, K):
    """A ladder K split into leg / size looks in the ledger's own proportions (CHOICE; g*(K_book) is then g* exactly)."""
    return (k * K["K_leg"] / K["K_book"], k * K["K_size"] / K["K_book"]) if K["K_book"] > 0 else (float(k), 0.0)


def k_then(looks, name, row=None):
    """The looks in force when past pass `name` was read: the REGISTERED cumulative count K_THEN[name] (addendum 1), split into leg / size
    as the FIRST K looks in ledger order. `row` only feeds the cross-check: the count by date (looks dated on or before the row) is
    returned beside it, never used."""
    k = K_THEN[name]
    sel = looks[:k]
    ks = sum(1 for r in sel if _typ(r) == "SIZE")
    if k > len(looks) and looks:                                       # a shorter ledger than the registered count (smoke): split the rest by proportion
        ks += (k - len(looks)) * sum(1 for r in looks if _typ(r) == "SIZE") / len(looks)
    out = {"K_book": k, "K_leg": k - ks, "K_size": ks}
    if row is not None:
        d = _date(row.get("date"))
        out["K_by_date"] = len([r for r in looks if _date(r.get("date")) is None or (d is not None and _date(r.get("date")) <= d)])
    return out


def judge(ratio, g):
    """'Survives' = ratio >= 1 + g_adj; beyond the grid (g None, i.e. > 1.0) only a ratio under 2 is decided."""
    if not np.isfinite(ratio):
        return None
    if g is None:
        return False if ratio < 2.0 else None
    return bool(ratio >= 1.0 + g)


def nleg(B, fams, lstar, xvec, kWF, kLB):
    """N-LEG: for each leg, NLEG_B draws (seed SEED0 + i): a block-21 stationary bootstrap of the leg's own valued-daily rows within WF and
    within LB separately (CHOICE: WF drawn first, then LB, one rng), placed in order, the other legs' rows fixed; WF / LB / LB_x scored.
    LB_x removes the top trade's rows from the fixed legs - not computed for the top trade's own seat (lstar)."""
    dWF, dLB = B.index[kWF], B.index[kLB]
    nWF, nLB = int(kWF.sum()), int(kLB.sum())
    legx = [B.Am_leg[i].T @ B.ones for i in range(len(fams))]
    out = {}
    for i, f in enumerate(fams):
        rng = np.random.default_rng(SEED0 + i)
        oth = B.raw - legx[i]
        oW, oL, oLx = oth[kWF], oth[kLB], (oth - xvec)[kLB]
        wW, wL = legx[i][kWF], legx[i][kLB]
        rec = {k: np.full(NLEG_B, np.nan) for k in ("wf_roc", "wf_sort", "wf_cdr", "lb_roc", "lb_sort", "lb_cdr", "lbx_roc", "lbx_sort")}
        for b in range(NLEG_B):
            iw = R11.stationary_bootstrap(nWF, BLOCK, rng)
            il = R11.stationary_bootstrap(nLB, BLOCK, rng)
            rw, rl = wW[iw], wL[il]
            if PLANT_SIGMA:
                rw = rw + rng.normal(0.0, PLANT_SIGMA) * float(wW.std())
                rl = rl + rng.normal(0.0, PLANT_SIGMA) * float(wL.std())
            sw, sl = R11.stats(oW + rw, dWF), R11.stats(oL + rl, dLB)
            rec["wf_roc"][b], rec["wf_sort"][b], rec["wf_cdr"][b] = sw["roc"], sw["sort"], sw["cdr"]
            rec["lb_roc"][b], rec["lb_sort"][b], rec["lb_cdr"][b] = sl["roc"], sl["sort"], sl["cdr"]
            if i != lstar:
                sx = R11.stats(oLx + rl, dLB)
                rec["lbx_roc"][b], rec["lbx_sort"][b] = sx["roc"], sx["sort"]
        out[f] = rec
        print(f"N-LEG {f:6s}: {NLEG_B:,} draws, median LB roc {np.nanmedian(rec['lb_roc']):.2f}, WF roc {np.nanmedian(rec['wf_roc']):.2f}", flush=True)
    return out


def nsize(B, m, kWF, kLB, lb_trades, inc):
    """N-SIZE: every circular shift k in [KMIN, N - KMIN] of the multiplier rows, applied trade by trade through Book.sized; LB_x removes the
    sized book's largest LB closed trade at that shift."""
    dWF, dLB = B.index[kWF], B.index[kLB]
    ks = shifts(B.n)
    rec = {k: np.full(len(ks), np.nan) for k in ("wf_roc", "wf_sort", "lb_roc", "lb_sort", "lb_cdr", "lbx_roc", "lbx_sort")}
    top = np.zeros(len(ks), np.int64)
    for q, k in enumerate(ks):
        mk = np.roll(m, int(k))
        x = B.sized(mk)
        sw, sl = R11.stats(x[kWF], dWF), R11.stats(x[kLB], dLB)
        j = top_lb_trade(B, lb_trades, mk)
        rows, vals = inc[j]
        xx = x.copy()
        np.subtract.at(xx, rows, vals * mk[B.erow[j]])
        sx = R11.stats(xx[kLB], dLB)
        rec["wf_roc"][q], rec["wf_sort"][q] = sw["roc"], sw["sort"]
        rec["lb_roc"][q], rec["lb_sort"][q], rec["lb_cdr"][q] = sl["roc"], sl["sort"], sl["cdr"]
        rec["lbx_roc"][q], rec["lbx_sort"][q] = sx["roc"], sx["sort"]
        top[q] = j
    rec["shift"], rec["top_trade"] = ks, top
    return rec


def _nleg_pass(L, key, sortkey, prem=1.0):
    """Per-leg centred pass counts over the grid, each leg vs its own medians; pooled = the sum (equal draws per leg)."""
    per = {}
    for f, rec in L.items():
        v, s = rec[key], rec[sortkey]
        if not np.isfinite(v).any():
            continue
        med_v, med_s = float(np.nanmedian(v)), float(np.nanmedian(s))
        e = excess(v, med_v)
        per[f] = {"n": int(len(v)), "pass": pass_centred(e, np.isfinite(s) & (s - med_s >= 0.0), prem), "e": e, "median": med_v, "median_sort": med_s}
    return per


def _size_pass(S, key, sortkey, bar):
    return {"n": int(len(S[key])), "pass": pass_uncentred(S[key], S[sortkey], bar)}


def share(n, d):
    return f"{(n / d if d else float('nan')):.5f} ({int(n):,} of {int(d):,})"


def at_g(c, g):
    """The pass counts a clause's curve carries at grid margin g (None when g is beyond the grid)."""
    if g is None:
        return None
    i = int(round(g / 0.005))
    return {"g": g, "n_leg_pass": int(c["c_leg"][i]), "n_leg": int(c["n_leg"]), "n_size_pass": int(c["c_size"][i]), "n_size": int(c["n_size"]),
            "FWER": float(c["F"][i])}


def run():
    t0 = time.time()
    check_prereg()
    lsha = check_ledger()
    if not os.path.exists(_ready_path()):
        raise SystemExit("refused: parity has not passed - run parity")
    with open(_ready_path()) as f:
        ready = json.loads(f.read() or "{}")
    if ready.get("prereg_sha256") != PREREG_SHA:
        raise SystemExit("refused: the prereg changed after parity passed - run parity again")
    if ready.get("ledger_sha256") != lsha:
        raise SystemExit("refused: the ledger changed after parity passed - run parity again")
    B, meta, hashes = load_records()
    if ready.get("records") != hashes:
        raise SystemExit("refused: r11's records changed after parity passed - run parity again")
    rows = read_ledger()
    K, looks = counts(rows)
    fams = [fam(m["strategy"]) for m in meta]
    kWF, kLB = B.mask(R11.WF0, R11.PRE_END), B.mask(R11.LB0, R11.LB1)
    dWF, dLB = B.index[kWF], B.index[kLB]
    lb_trades = np.flatnonzero(kLB[B.xrow])
    inc = trade_inc(B)
    jtop = top_lb_trade(B, lb_trades)
    lstar = int(B.leg[jtop])
    xvec = np.zeros(B.n)
    np.add.at(xvec, inc[jtop][0], inc[jtop][1])
    ref = {"WF": R11.stats(B.raw[kWF], dWF), "LB": R11.stats(B.raw[kLB], dLB), "LBx": R11.stats((B.raw - xvec)[kLB], dLB)}
    # the bar the uncentred shifts and the past passes are held to: as written on a real run, the raw book's own on a smoke (CHOICE)
    bar = {"WF": WF_BAR, "LB": LB_BAR} if CHECK_REFS else {"WF": (ref["WF"]["roc"] * WF_PREM, ref["WF"]["sort"]), "LB": (ref["LB"]["roc"], ref["LB"]["sort"])}
    bar["LBx"], bar["CDR"] = (ref["LBx"]["roc"], ref["LBx"]["sort"]), (ref["LB"]["cdr"], ref["LB"]["sort"])     # no printed figures: the raw book's own (CHOICE)
    top = {"family": fams[lstar], "entry": str(B.entry_day[jtop]), "exit": str(B.index[B.xrow[jtop]].date()), "closed": float(B.closed[jtop])}
    print(f"reference raw #463: WF {ref['WF']['roc']:.2f}/{ref['WF']['sort']:.3f} LB {ref['LB']['roc']:.2f}/{ref['LB']['sort']:.3f} cdr {ref['LB']['cdr']:.2f}; "
          f"LB_x {ref['LBx']['roc']:.2f}/{ref['LBx']['sort']:.3f} (top trade {top['family']} {top['entry']}..{top['exit']} ${top['closed']:,.0f}); "
          f"K_book {K['K_book']} = {K['K_leg']} leg + {K['K_size']} size", flush=True)
    t1 = time.time()
    L = nleg(B, fams, lstar, xvec, kWF, kLB)
    t2 = time.time()
    ms = {c: B.mult(c) for c in R11.CELLS}
    S = {c: nsize(B, ms[c], kWF, kLB, lb_trades, inc) for c in R11.CELLS}
    t3 = time.time()
    print(f"N-SIZE: {len(S['V2']['shift']):,} shifts per cell (k in [{KMIN}, {B.n - KMIN}], step {SIZE_STEP}); N-LEG {t2 - t1:.0f}s, N-SIZE {t3 - t2:.0f}s", flush=True)
    kl, ks = K["K_leg"], K["K_size"]
    # the LB clause (primary), LB_x, CDR, and the WF analogue - each a pooled N-LEG count + an N-SIZE count over the grid
    curves = {}
    for name, key, skey, bkey, prem in (("LB", "lb_roc", "lb_sort", "LB", 1.0), ("LBx", "lbx_roc", "lbx_sort", "LBx", 1.0),
                                        ("CDR", "lb_cdr", "lb_sort", "CDR", 1.0), ("WF", "wf_roc", "wf_sort", "WF", WF_PREM)):
        per = _nleg_pass(L, key, skey, prem)
        n_leg = sum(p["n"] for p in per.values())
        c_leg = sum(p["pass"] for p in per.values()) if per else np.zeros(len(GRID))
        sz = _size_pass(S["V2"], key, skey, bar[bkey])
        p_leg, p_size = c_leg / max(1, n_leg), sz["pass"] / max(1, sz["n"])
        F = fwer(p_leg, p_size, kl, ks)
        curves[name] = {"per_leg": per, "n_leg": n_leg, "c_leg": c_leg, "p_leg": p_leg, "n_size": sz["n"], "c_size": sz["pass"], "p_size": p_size,
                        "F": F, "g": {lv: g_star(F, lv) for lv in LEVELS},
                        "g_per_leg": {f: g_star(fwer(p["pass"] / p["n"], p_size, kl, ks)) for f, p in per.items()},
                        "cells": {c: _size_pass(S[c], key, skey, bar[bkey]) for c in R11.CELLS if c != "V2"}}
    C = curves["LB"]
    gs = C["g"][0.05]
    lad = [(lab, (K["K_book"] if lab == "K_book" else 2 * K["K_book"] if lab == "2K_book" else K_CEILING if lab == "K_ceiling" else int(lab)))
           for lab in LADDER]
    ladder = [{"label": str(lab), "K": k, "g_star": g_star(fwer(C["p_leg"], C["p_size"], *k_split(k, K)))} for lab, k in lad]
    cal_rows = calibration_rows(rows)
    cal = calibration([ratio_of(r) for _, r in cal_rows if r is not None], np.concatenate([p["e"] for p in C["per_leg"].values()]))
    cal["rows"] = [{"tag": t, "id": r.get("id") if r else None, "ratio": ratio_of(r) if r else None} for t, r in cal_rows]
    ga = g_adj(gs, cal["r"])
    at_gs = at_g(C, gs)
    past = []
    for name, aliases in PAST:
        r = find_any(rows, aliases)
        if r is None:
            past.append({"candidate": name, "found": False, "context": CONTEXT.get(name, "")})
            continue
        kt = k_then(looks, name, r)
        g_then = g_adj(g_star(fwer(C["p_leg"], C["p_size"], kt["K_leg"], kt["K_size"])), cal["r"])
        ratio = ratio_of(r)
        past.append({"candidate": name, "found": True, "id": r.get("id"), "date": r.get("date"), "ratio": ratio, "verdict_as_printed": r.get("verdict_as_printed"),
                     "K_then": kt["K_book"], "K_then_leg": kt["K_leg"], "K_then_size": kt["K_size"], "K_by_date": kt.get("K_by_date"),
                     "g_adj_then": g_then, "survives_then": judge(ratio, g_then),
                     "K_now": K["K_book"], "g_adj_now": ga, "survives_now": judge(ratio, ga), "context": CONTEXT.get(name, "")})
    f0 = float(C["F"][0])
    h0 = f0 <= 0.05
    # ---- files
    cols = {"g": GRID}
    for name, c in curves.items():
        cols[f"{name}_n_leg_pass"], cols[f"{name}_p_leg"], cols[f"{name}_n_size_pass"], cols[f"{name}_p_size"], cols[f"{name}_FWER"] = \
            c["c_leg"], c["p_leg"], c["c_size"], c["p_size"], c["F"]
        for f, p in c["per_leg"].items():
            cols[f"{name}_{f}_n_pass"] = p["pass"]
    os.makedirs(OUT, exist_ok=True)
    pd.DataFrame(cols).to_csv(os.path.join(OUT, "margin_curve.csv"), index=False)
    pd.DataFrame([{k: (gfmt(v) if k.startswith("g_adj") else v) for k, v in p.items()} for p in past]).to_csv(os.path.join(OUT, "past_passes.csv"), index=False)
    v2 = {s: R11.unified(B, B.sized(ms["V2"]), *w) for s, w in (("WF", (R11.WF0, R11.PRE_END)), ("LB", (R11.LB0, R11.LB1)))}
    summ = {"prereg_sha256": PREREG_SHA, "ledger_sha256": lsha, "records": hashes, "K": K, "reference": ref, "bar": bar, "top_lb_trade": top,
            "nleg": {"draws_per_leg": NLEG_B, "block": BLOCK, "seeds": {f: SEED0 + i for i, f in enumerate(fams)}, "lb_x_not_computed_for": fams[lstar],
                     "plant_sigma": PLANT_SIGMA,
                     "per_leg": {f: {"median_lb_roc": p["median"], "median_shift_vs_ref": p["median"] / ref["LB"]["roc"] - 1.0 if ref["LB"]["roc"] else None,
                                     "median_lb_sort": p["median_sort"], "n": p["n"], "pass_at_0": int(p["pass"][0]), "p_at_0": float(p["pass"][0] / p["n"]),
                                     "g_star": C["g_per_leg"][f], "n_nan_roc": int((~np.isfinite(L[f]["lb_roc"])).sum())} for f, p in C["per_leg"].items()},
                     "median_wf_roc": {f: p["median"] for f, p in curves["WF"]["per_leg"].items()}},
            "nsize": {"shifts": int(C["n_size"]), "k_range": [int(KMIN), int(B.n - KMIN)], "step": SIZE_STEP, "n_rows": int(B.n),
                      "cells": {c: {"pass_at_0": int(C["cells"][c]["pass"][0]), "n": C["cells"][c]["n"],
                                    "g_star_in_place_of_V2": g_star(fwer(C["p_leg"], C["cells"][c]["pass"] / C["cells"][c]["n"], kl, ks))} for c in C["cells"]},
                      "v2_unshifted_context_10o": v2},
            "clauses": {name: {"p_leg_0": float(c["p_leg"][0]), "n_leg_pass_0": int(c["c_leg"][0]), "n_leg": c["n_leg"], "p_size_0": float(c["p_size"][0]),
                               "n_size_pass_0": int(c["c_size"][0]), "n_size": c["n_size"], "FWER_0": float(c["F"][0]),
                               "g_star": {str(lv): g for lv, g in c["g"].items()}, "g_star_per_leg": c["g_per_leg"]} for name, c in curves.items()},
            "H0": {"FWER_0": f0, "holds": h0, "reading": "the bar stands as written" if h0 else
                   "the bar does NOT control the family-wise false-pass rate at the looks already spent; the FAIL is not a discovery - the product is g_adj and the tables"},
            "g_star": gs, "at_g_star": at_gs, "band": {"0.025": C["g"][0.025], "0.10": C["g"][0.10]}, "g_star_x": curves["LBx"]["g"][0.05], "g_star_cdr": curves["CDR"]["g"][0.05],
            "wf_analogue": {"p_leg_0": float(curves["WF"]["p_leg"][0]), "p_size_0": float(curves["WF"]["p_size"][0]), "FWER_0": float(curves["WF"]["F"][0]),
                            "g_at_0.05": curves["WF"]["g"][0.05], "premium_in_bar": WF_PREM},
            "ladder": ladder, "calibration": cal, "g_adj": ga, "past_passes": past,
            "rule_proposed": (f"for any BACKTEST candidate judged on the spent lockbox year from now on: LB ROC >= {bar['LB'][0]:.2f} x (1 + g_adj {gfmt(ga)}) = "
                              + (f"{bar['LB'][0] * (1 + ga):.2f} %/yr" if ga is not None else "beyond the 0..1.0 grid (more than 2 x the reference)")
                              + f" at a $30k drawdown, Sortino >= {bar['LB'][1]:.3f} unchanged"
                              + (f" (or the ex-top-trade form: g*_x {gfmt(curves['LBx']['g'][0.05])} < g* {gfmt(gs)})" if
                                 (curves["LBx"]["g"][0.05] is not None and (gs is None or curves["LBx"]["g"][0.05] < gs)) else "")
                              + "; a candidate that clears WF but not that margin is 'not refuted', never 'a pass'; FORWARD reads are untouched; an owner decision via MANAGER"),
            "seconds": {"nleg": round(t2 - t1, 1), "nsize": round(t3 - t2, 1), "total": round(time.time() - t0, 1)}}
    save("nulls.json", summ)
    np.savez_compressed(os.path.join(OUT, "draws.npz"), **{f"leg_{f}_{k}": v for f, rec in L.items() for k, v in rec.items()},
                        **{f"size_{c}_{k}": v for c, rec in S.items() for k, v in rec.items()})
    lines = looks_lines(summ)
    with open(os.path.join(OUT, "LOOKS.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    write_doc(DOC, summ)
    print("\n".join(lines), flush=True)
    return summ


def looks_lines(s):
    K, C, cal = s["K"], s["clauses"], s["calibration"]
    ref, bar, top = s["reference"], s["bar"], s["top_lb_trade"]
    lb = C["LB"]
    out = [f"BOOK LOOKS r1 - FWER(0) = {s['H0']['FWER_0']:.4f} -> H0 {'HOLDS' if s['H0']['holds'] else 'FAILS'}: {s['H0']['reading']}",
           f"prereg sha256 {s['prereg_sha256']}; ledger sha256 {s['ledger_sha256']}; records {s['records'].get('records_U.npz', '')[:16]}...",
           f"K_book {K['K_book']} = K_leg {K['K_leg']} + K_size {K['K_size']}; K_lane {K['K_lane']} reported, not in the formula",
           f"reference raw #463 (unified): WF {ref['WF']['roc']:.2f} / {ref['WF']['sort']:.3f}; LB {ref['LB']['roc']:.2f} / {ref['LB']['sort']:.3f} (CDR {ref['LB']['cdr']:.2f}); "
           f"LB_x {ref['LBx']['roc']:.2f} / {ref['LBx']['sort']:.3f} without {top['family']} {top['entry']}..{top['exit']} ${top['closed']:,.0f}; bar LB {bar['LB'][0]:.2f} / {bar['LB'][1]:.3f}",
           f"p_leg(0) {share(lb['n_leg_pass_0'], lb['n_leg'])}; p_size(0) {share(lb['n_size_pass_0'], lb['n_size'])}; FWER(0) {lb['FWER_0']:.4f} at K_leg {K['K_leg']}, K_size {K['K_size']}"]
    for f, p in s["nleg"]["per_leg"].items():
        out.append(f"N-LEG {f:6s}: {p['n']:,} draws (seed {s['nleg']['seeds'][f]}, block {s['nleg']['block']}); median LB roc {p['median_lb_roc']:.2f} = "
                   f"{p['median_shift_vs_ref']:+.1%} vs the reference (alignment artefact, centred away); pass at g=0 {share(p['pass_at_0'], p['n'])}; per-leg g* {gfmt(p['g_star'])}"
                   + ("" if p["n_nan_roc"] == 0 else f"; {p['n_nan_roc']} draws without a ROC"))
    ns = s["nsize"]
    out.append(f"N-SIZE V2: {ns['shifts']:,} shifts (k in [{ns['k_range'][0]}, {ns['k_range'][1]}] of {ns['n_rows']} rows, step {ns['step']}), uncentred at the bar as written; "
               + "; ".join(f"{c} {share(v['pass_at_0'], v['n'])} -> g* {gfmt(v['g_star_in_place_of_V2'])} in V2's place (reported, not pooled)" for c, v in ns["cells"].items())
               + f"; real V2 unshifted (10o, context) WF {ns['v2_unshifted_context_10o']['WF']['roc']:.2f} LB {ns['v2_unshifted_context_10o']['LB']['roc']:.2f}")
    g = lb["g_star"]
    a = s["at_g_star"]
    out.append(f"g* = {gfmt(g['0.05'])}" + (f" (FWER {a['FWER']:.4f}: p_leg {share(a['n_leg_pass'], a['n_leg'])}, p_size {share(a['n_size_pass'], a['n_size'])})" if a else "")
               + f"; band: FWER 0.025 at {gfmt(g['0.025'])}, 0.10 at {gfmt(g['0.1'])}; per leg " + ", ".join(f"{f} {gfmt(v)}" for f, v in lb["g_star_per_leg"].items()))
    for name, lab in (("LBx", "g*_x (top trade removed; N-LEG on the three other seats"), ("CDR", "g*_CDR (CDR in place of ROC")):
        c = C[name]
        out.append(f"{lab}; p_leg(0) {share(c['n_leg_pass_0'], c['n_leg'])}, p_size(0) {share(c['n_size_pass_0'], c['n_size'])}) = {gfmt(c['g_star']['0.05'])}")
    w = s["wf_analogue"]
    cw = C["WF"]
    out.append(f"WF analogue (report only; the WF clause keeps its {WF_PREM - 1:.2%} premium): p_WF(0) leg {share(cw['n_leg_pass_0'], cw['n_leg'])}, "
               f"size {share(cw['n_size_pass_0'], cw['n_size'])}; FWER_WF(0) {w['FWER_0']:.4f}; WF margin at FWER 0.05 {gfmt(w['g_at_0.05'])}")
    out.append("ladder g*(K): " + ", ".join(f"K={r['K']}{'' if str(r['label']).isdigit() else ' (' + r['label'] + ')'} {gfmt(r['g_star'])}" for r in s["ladder"]))
    out.append(f"calibration: sd_real {cal['sd_real']:.4f} (n {cal['n_real']} of {len(CALIB)}) / sd_null {cal['sd_null']:.4f} (n {cal['n_null']:,}, "
               f"{cal['n_null_dropped']:,} draws without a positive LB ROC dropped) = r {cal['r']:.3f}; "
               f"g_adj = g* x max(1, r) = {gfmt(s['g_adj'])}" + (f" - FLAG: r outside [{R_BAND[0]}, {R_BAND[1]}], the null does not describe the real swaps' spread" if cal["flag"] else ""))
    for p in s["past_passes"]:
        if not p["found"]:
            out.append(f"past pass {p['candidate']:14s}: NOT IN THE LEDGER")
            continue
        out.append(f"past pass {p['candidate']:14s}: LB ratio {p['ratio']:.4f} (printed {asc(p['verdict_as_printed'])}); K then {p['K_then']} (registered; "
                   f"{p['K_then_leg']} leg + {p['K_then_size']} size; by date {p['K_by_date']}) g_adj {gfmt(p['g_adj_then'])} -> "
                   f"{'survives' if p['survives_then'] else 'does not survive' if p['survives_then'] is False else 'undecided'}; K now {p['K_now']} g_adj {gfmt(p['g_adj_now'])} -> "
                   f"{'survives' if p['survives_now'] else 'does not survive' if p['survives_now'] is False else 'undecided'}" + (f" ({p['context']})" if p["context"] else ""))
    out.append("rule proposed: " + s["rule_proposed"])
    out.append(f"wall time: N-LEG {s['seconds']['nleg']}s, N-SIZE {s['seconds']['nsize']}s, total {s['seconds']['total']}s")
    return [asc(x) for x in out]


def write_doc(path, s):
    """docs/LOOKS_R1.md - one page, plain English, the dollars / percent sentence first, every number with its count."""
    K, lb, cal, bar = s["K"], s["clauses"]["LB"], s["calibration"], s["bar"]
    ga, gs = s["g_adj"], s["g_star"]
    roc_adj = bar["LB"][0] * (1.0 + ga) if ga is not None else None
    dollars = ga * bar["LB"][0] * 1000.0 if ga is not None else None       # ROC %/yr at a $30k drawdown = $1,000 a year per point on $100k sized to that drawdown
    first = (f"**After {K['K_book']} printed looks at #463's lockbox year ({K['K_leg']} seat swaps / adds / combinations and {K['K_size']} sizing rules in "
             f"LOOKS_LEDGER_R1.csv), a future backtest candidate must beat the lockbox by {ga:.1%} - LB ROC at least {roc_adj:.2f} %/yr at a $30k drawdown "
             f"instead of {bar['LB'][0]:.2f}, which is about ${dollars:,.0f} a year more on $100k sized to a $30k drawdown - for its pass to be more than luck "
             f"(family-wise false-pass rate 5 %); the Sortino clause ({bar['LB'][1]:.3f}) is unchanged.**" if ga is not None else
             f"**After {K['K_book']} printed looks at #463's lockbox year ({K['K_leg']} leg looks, {K['K_size']} sizing looks), no margin on the grid up to "
             f"100 % brings a no-edge candidate's family-wise false-pass rate under 5 % - the lockbox clause cannot be rescued by a margin at this K.**")
    L = [f"# BOOK LOOKS r1 - how sure a lockbox pass must be ({time.strftime('%Y-%m-%d')})", "", first, "",
         f"**What the nulls say.** At today's bar a no-edge candidate has ALREADY cleared the lockbox somewhere in the pile with probability "
         f"FWER(0) = {s['H0']['FWER_0']:.3f}: a no-information seat swap / add passes it with p_leg(0) = {share(lb['n_leg_pass_0'], lb['n_leg'])} "
         f"and a no-information sizing rule with p_size(0) = {share(lb['n_size_pass_0'], lb['n_size'])}. The registered reading of H0 (\"today's bar "
         f"controls the family-wise false-pass rate\"): **{'HOLDS' if s['H0']['holds'] else 'FAILS'}** - {s['H0']['reading']}.", "",
         (f"**The margin.** g* = {gs:.3f} is the smallest margin with FWER <= 0.05" if gs is not None else
          "**The margin.** No margin on the 0..1.0 grid brings FWER under 0.05 (g* > 1.0)")
         + (f" (there p_leg = {share(s['at_g_star']['n_leg_pass'], s['at_g_star']['n_leg'])}, p_size = {share(s['at_g_star']['n_size_pass'], s['at_g_star']['n_size'])})" if s["at_g_star"] else "")
         + f"; band: {gfmt(s['band']['0.025'])} at 0.025, {gfmt(s['band']['0.10'])} at 0.10. "
         f"Per seat: " + ", ".join(f"{f} {gfmt(v)}" for f, v in lb["g_star_per_leg"].items()) + f". With the top lockbox trade removed g*_x = {gfmt(s['g_star_x'])}; "
         f"with CDR in place of ROC g*_CDR = {gfmt(s['g_star_cdr'])}. The walk-forward analogue (report only): p_WF(0) = {share(s['clauses']['WF']['n_leg_pass_0'], s['clauses']['WF']['n_leg'])} leg / "
         f"{share(s['clauses']['WF']['n_size_pass_0'], s['clauses']['WF']['n_size'])} size, WF margin at 5 % = {gfmt(s['wf_analogue']['g_at_0.05'])}.", "",
         f"**Calibration.** The ten real one-change reads spread sd_real = {cal['sd_real']:.3f} in ln(LB ratio) (n = {cal['n_real']} of {len(CALIB)}); the null's "
         f"centred spread is sd_null = {cal['sd_null']:.3f} (n = {cal['n_null']:,} draws, {cal['n_null_dropped']:,} without a positive LB ROC dropped); "
         f"r = {cal['r']:.2f}, so g_adj = g* x max(1, r) = {gfmt(ga)}"
         + (f". **FLAG: r is outside [{R_BAND[0]}, {R_BAND[1]}] - the null does not describe the real swaps' spread.**" if cal["flag"] else "."), "",
         "**What a future read costs (margin ladder, FWER 5 %).**", "", "| K looks | g*(K) |", "|---|---|"]
    L += [f"| {r['K']}{'' if str(r['label']).isdigit() else ' (' + r['label'] + ')'} | {gfmt(r['g_star'])} |" for r in s["ladder"]]
    L += ["", "**Past passes, re-judged at g_adj (context lines, not re-verdicts).**", "",
          "| candidate | LB ratio | printed | K then | g_adj then | survives | K now | g_adj now | survives | context |", "|---|---|---|---|---|---|---|---|---|---|"]
    for p in s["past_passes"]:
        if not p["found"]:
            L.append(f"| {p['candidate']} | not in the ledger | | | | | | | | {p['context']} |")
            continue
        yn = lambda v: "yes" if v else "no" if v is False else "undecided"
        L.append(f"| {p['candidate']} | {p['ratio']:.3f} | {asc(p['verdict_as_printed'])} | {p['K_then']} | {gfmt(p['g_adj_then'])} | {yn(p['survives_then'])} | "
                 f"{p['K_now']} | {gfmt(p['g_adj_now'])} | {yn(p['survives_now'])} | {p['context']} |")
    ns, top = s["nsize"], s["top_lb_trade"]
    L += ["", f"**The nulls.** N-LEG: {s['nleg']['draws_per_leg']:,} draws per seat (block {s['nleg']['block']}, seeds " + ", ".join(f"{f} {v}" for f, v in s["nleg"]["seeds"].items())
          + "), centred on each seat's own draw median; the medians sit " + ", ".join(f"{f} {p['median_shift_vs_ref']:+.1%}" for f, p in s["nleg"]["per_leg"].items())
          + f" from the reference (the alignment artefact the centring removes). N-SIZE: {ns['shifts']:,} circular shifts of the V2 multipliers "
          f"(k in [{ns['k_range'][0]}, {ns['k_range'][1]}] of {ns['n_rows']} rows), uncentred at the bar as written; V2-500 and V2-60 cells: "
          + "; ".join(f"{c} {share(v['pass_at_0'], v['n'])}" for c, v in ns["cells"].items())
          + f" (reported, not pooled). Largest lockbox trade: {top['family']} {top['entry']}..{top['exit']} ${top['closed']:,.0f}; LB_x not computed for the {s['nleg']['lb_x_not_computed_for']} seat.",
          "", f"**The rule this round proposes (an owner decision via MANAGER, never automatic).** {s['rule_proposed']}.", "",
          "**Not claimed.** The nulls stand in for a candidate of that type with no information, not for any particular candidate; K counts printed looks, so it is a "
          "floor and FWER(0) a lower bound; one realised history (block-21 bootstrap keeps three-week structure, not regimes; the shifts keep everything but the timing).", "",
          f"Files: {OUT} (LOOKS.txt, margin_curve.csv, past_passes.csv, nulls.json, draws.npz). prereg sha256 {s['prereg_sha256']}; ledger sha256 {s['ledger_sha256']}; "
          f"wall time {s['seconds']['total']}s."]
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(asc(x) for x in L) + "\n")


# ------------------------------------------------------------------ smoke: r11's synthetic world, then this harness end to end
SMOKE_LEDGER = [  # id, date, source, candidate, type, ref, conv, wf_roc, wf_sort, lb_roc, lb_sort, ref_lb_roc, lb_ratio, verdict, dup_of, judgment
    ("L001", "2026-09-20", "BOOK.md 10a", "#463 reference re-run", "REF", "#463", "unified", "93.81", "3.816", "155.54", "4.150", "155.54", "1.0", "-", "", "context"),
    ("L002", "2026-09-21", "BOOK.md 10e", "58d ENGU-Q et@0.55 cut + NOISE #422", "COMBO", "#366", "old", "103.3", "3.9", "321.0", "4.4", "252.1", "1.273", "passed, refuted", "", "look"),
    ("L003", "2026-09-27", "BOOK.md 10k", "#444 NOISE = run #422", "SWAP", "#397", "old", "96.4", "4.21", "309.8", "6.48", "293.3", "1.056", "misses clause 3", "", "look"),
    ("L004", "2026-09-27", "BOOK.md 10k", "#449 #436 with NOISE #422", "SWAP", "#397", "old", "97.5", "4.18", "310.8", "6.42", "293.3", "1.060", "clears", "", "look"),
    ("L005", "2026-09-27", "BOOK.md 10l", "round-61 best #457", "COMBO", "#449", "old", "99.1", "4.2", "293.1", "4.5", "295.0", "0.994", "fails clause 4", "", "look"),
    ("L006", "2026-09-28", "BOOK.md 10n", "#468 TTM #458 in the TTM seat", "SWAP", "#463", "old", "72.1", "3.18", "163.6", "4.12", "164.8", "0.993", "FAIL", "", "look"),
    ("L007", "2026-09-29", "BOOK.md 10p", "#469 sleeve in place of TTM x3", "SWAP", "#463", "old", "82.9", "3.90", "149.1", "3.89", "164.3", "0.907", "FAIL", "", "look"),
    ("L008", "2026-09-29", "BOOK.md 10p", "#470 sleeve added", "ADD", "#463", "old", "82.6", "4.08", "166.9", "4.37", "164.3", "1.016", "FAIL", "", "look"),
    ("L009", "2026-09-30", "BOOK.md 10o", "V2 book vol target", "SIZE", "#463", "old", "116.1", "3.91", "259.3", "4.79", "164.8", "1.573", "beats both", "", "look"),
    ("L010", "2026-09-30", "BOOK.md 10o", "V2-500 ref 500", "SIZE", "#463", "old", "110.0", "3.8", "240.0", "4.5", "164.8", "1.456", "beats both", "", "look"),
    ("L011", "2026-10-01", "BOOK.md 10r", "Q1a ORB #314 in the ORB seat", "SWAP", "#463", "unified", "125.6", "3.95", "147.3", "3.95", "155.5", "0.947", "FAIL", "", "look"),
    ("L012", "2026-10-01", "BOOK.md 10r", "Q1b ORB #257 in the ORB seat", "SWAP", "#463", "unified", "108.5", "3.93", "146.3", "3.89", "155.5", "0.941", "FAIL", "", "look"),
    ("L013", "2026-10-01", "BOOK.md 10r", "Q2 NOISE #398 in the NOISE seat", "SWAP", "#463", "unified", "69.6", "3.30", "169.0", "3.75", "155.5", "1.087", "FAIL", "", "look"),
    ("L014", "2026-10-01", "BOOK.md 10r", "Q2ctx NOISE #304 raw in the NOISE seat", "SWAP", "#463", "unified", "85.1", "3.54", "145.6", "3.94", "155.5", "0.936", "context", "", "look"),
    ("L015", "2026-10-01", "BOOK.md 10r", "Q3 ENGU-Q gate S1 in the ENGU-Q seat", "SWAP", "#463", "unified", "84.5", "3.89", "188.4", "4.61", "155.5", "1.212", "FAIL", "", "look"),
    ("L016", "2026-10-01", "BOOK.md 10r", "Q4 ORB #314 + ENGU-Q gate S1 (post-hoc)", "COMBO", "#463", "unified", "111.0", "4.03", "177.6", "4.37", "155.5", "1.142", "PASS (post-hoc)", "", "look"),
    ("L017", "2026-10-01", "BOOK.md 10r", "Q5 + ENGU-Q on ES #442 as a fifth leg", "ADD", "#463", "unified", "103.1", "3.49", "149.6", "3.68", "155.5", "0.962", "FAIL", "", "look"),
    ("L018", "2026-10-01", "BOOK.md 10r", "Q6 ORB #239 in the ORB seat", "SWAP", "#463", "unified", "101.8", "3.84", "158.7", "4.23", "155.5", "1.021", "PASS", "", "look"),
    ("L019", "2026-10-02", "ORB lane", "Q6 ORB #239 in the ORB seat (re-read)", "SWAP", "#463", "unified", "101.8", "3.84", "158.7", "4.23", "155.5", "1.021", "PASS", "L018", "dup"),
    ("L020", "2026-10-02", "TTM lane", "TTM #299 leg lockbox read", "LANE", "#463", "unified", "", "", "", "", "", "", "-", "", "lane"),
    ("L021", "2026-10-03", "MDL r1", "S2 ENGU-Q seat reference", "SWAP", "#463", "unified", "90.0", "3.8", "150.0", "4.0", "155.5", "0.965", "FAIL", "", "look"),
]


def write_smoke_ledger(path, rows=None):
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(COLS)
        w.writerows(rows or SMOKE_LEDGER)


def smoke(d, world="null"):
    """r11_risk.smoke builds the synthetic world (its records, build.json and a passing parity.json under DIR; its own refusal test ends with its
    READY removed, restored here from that pass - CHOICE), then: ledger (TBD tolerated, a synthetic csv), parity, run, the refusals.
    world="planted" adds a per-draw drift of N(0, 0.2) x the leg's daily sd to each N-LEG draw's resampled rows, so the null's spread, the
    pass counts at large margins and g* move off the unplanted twin's; the numbers mean nothing."""
    global OUT, DOC, LEDGER, LEDGER_SHA, CHECK_REFS, SMOKE_TBD_OK, NLEG_B, SIZE_STEP, PLANT_SIGMA
    root = os.path.abspath(d)
    assert "smoke" in os.path.basename(root).lower() and not os.path.normcase(root).startswith(os.path.normcase(r"C:\EdgeLog")), \
        "smoke needs its own scratch folder (name contains 'smoke'), never a real cache"
    os.makedirs(root, exist_ok=True)
    t0 = time.time()
    R11.smoke(root, "null")
    p = R11.load_json("parity.json")
    assert p.get("pass"), "smoke: r11's parity must have passed on the synthetic world"
    with open(R11._ready_path(), "w") as f:
        f.write(json.dumps({"P1-P4": "passed", "sha256": R11._record_hashes()}, indent=1))
    OUT, DOC, LEDGER = os.path.join(root, "looks"), os.path.join(root, "looks", "LOOKS_R1.md"), os.path.join(root, "LOOKS_LEDGER_R1_smoke.csv")
    LEDGER_SHA, CHECK_REFS, SMOKE_TBD_OK, NLEG_B, SIZE_STEP = "TBD", False, True, 300, 40
    PLANT_SIGMA = 0.6 if world == "planted" else 0.0
    os.makedirs(OUT, exist_ok=True)
    write_smoke_ledger(LEDGER)
    sha, K, cal = ledger()
    assert (K["K_book"], K["K_leg"], K["K_size"], K["K_lane"], K["n_ref"], K["n_dup"]) == (18, 16, 2, 1, 1, 1), K
    assert all(r is not None for _, r in cal), "smoke: every calibration tag must resolve on the synthetic csv"
    # refusals before parity: no READY; a TBD ledger without the smoke tolerance; a changed prereg
    try:
        run()
        raise AssertionError("smoke: run() must refuse without READY")
    except SystemExit:
        pass
    SMOKE_TBD_OK = False
    try:
        check_ledger()
        raise AssertionError("smoke: check_ledger() must refuse a TBD ledger outside the smoke")
    except SystemExit as ex:
        assert ex.code == 2
    SMOKE_TBD_OK = True
    probe = os.path.join(root, "prereg_probe.txt")
    with open(probe, "w") as f:
        f.write("probe\n")
    for want, ok in (("TBD", False), ("0" * 64, False), (R11.sha_lf(probe), True)):
        try:
            check_prereg(probe, want)
            assert ok, "smoke: check_prereg must refuse"
        except SystemExit:
            assert not ok, "smoke: check_prereg must pass the right sha"
    parity()
    pj = json.load(open(os.path.join(OUT, "parity.json")))
    assert pj["pass"] and all(pj["P2"][s]["ok"].get("r11_parity") for s in ("WF", "LB")), "smoke: P2 must reproduce r11's own parity on the same records"
    s0 = None
    if world == "planted":                                  # an unplanted twin first, so the planted curve has something to sit above
        PLANT_SIGMA = 0.0
        s0 = run()
        c0 = pd.read_csv(os.path.join(OUT, "margin_curve.csv"))
        PLANT_SIGMA = 0.2
    s = run()
    cv = pd.read_csv(os.path.join(OUT, "margin_curve.csv"))
    assert len(cv) == len(GRID) == 201
    if s0 is not None:                                      # the planted spread shows: wider null sd, more draws past every large margin, g* no lower
        assert s["calibration"]["sd_null"] > s0["calibration"]["sd_null"], (s["calibration"]["sd_null"], s0["calibration"]["sd_null"])
        assert int(cv["LB_n_leg_pass"].iloc[-1]) > int(c0["LB_n_leg_pass"].iloc[-1]), (cv["LB_n_leg_pass"].iloc[-1], c0["LB_n_leg_pass"].iloc[-1])
        assert s0["g_star"] is None or (s["g_star"] is None or s["g_star"] >= s0["g_star"])
    # the margin curve, g* and FWER(0) re-done by hand on the saved draws (no searchsorted, no shared code path)
    z = np.load(os.path.join(OUT, "draws.npz"))
    meta = legs_meta()
    B = R11.load_book("U", meta)
    fams = [fam(m["strategy"]) for m in meta]
    K = s["K"]
    pooled = np.zeros(len(GRID), int)
    for f in fams:
        v, so = z[f"leg_{f}_lb_roc"], z[f"leg_{f}_lb_sort"]
        e = excess(v, float(np.nanmedian(v)))
        ok_s = so - np.nanmedian(so) >= 0
        assert np.sum(e >= 0) >= NLEG_B // 2 and np.sum(e > 0) <= NLEG_B // 2                # centred: half at or above the median, none past it by definition
        cnt = np.array([int(np.sum((e >= math.log(1.0 + g)) & ok_s)) for g in GRID])
        assert (cnt == cv[f"LB_{f}_n_pass"].to_numpy()).all(), f
        pooled += cnt
    assert (pooled == cv["LB_n_leg_pass"].to_numpy()).all() and pooled[0] == s["clauses"]["LB"]["n_leg_pass_0"]
    bar = s["bar"]["LB"]
    roc, so = z["size_V2_lb_roc"], z["size_V2_lb_sort"]
    szc = np.array([int(np.sum((roc >= bar[0] * (1.0 + g)) & (so >= bar[1]))) for g in GRID])
    assert (szc == cv["LB_n_size_pass"].to_numpy()).all() and szc[0] == s["clauses"]["LB"]["n_size_pass_0"]
    F = 1 - (1 - pooled / (4 * NLEG_B)) ** K["K_leg"] * (1 - szc / len(roc)) ** K["K_size"]
    assert np.allclose(F, cv["LB_FWER"].to_numpy()) and abs(F[0] - s["H0"]["FWER_0"]) < 1e-12
    hit = np.flatnonzero(F <= 0.05)
    assert (float(GRID[hit[0]]) if len(hit) else None) == s["g_star"]
    assert s["clauses"]["LB"]["n_leg"] == 4 * NLEG_B
    ks = shifts(B.n)
    assert ks[0] == KMIN and ks[-1] <= B.n - KMIN and len(ks) == s["nsize"]["shifts"] == len(roc)
    # one N-SIZE shift rebuilt increment by increment (no sparse matrix): sized LB and LB_x must match the saved draw
    q = len(ks) // 3
    mk = np.roll(B.mult("V2"), int(ks[q]))
    w = B.inc_v * mk[B.erow[B.inc_t]]
    x = np.bincount(B.inc_row, weights=w, minlength=B.n)
    kLB = B.mask(R11.LB0, R11.LB1)
    j = int(z["size_V2_top_trade"][q])
    xx = np.bincount(B.inc_row[B.inc_t != j], weights=w[B.inc_t != j], minlength=B.n)
    st, stx = R11.stats(x[kLB], B.index[kLB]), R11.stats(xx[kLB], B.index[kLB])
    assert abs(st["roc"] - roc[q]) < 1e-9 and abs(stx["roc"] - z["size_V2_lbx_roc"][q]) < 1e-9, "smoke: brute-force shift differs"
    assert kLB[B.xrow[j]] and B.closed[j] * mk[B.erow[j]] >= (B.closed * mk[B.erow])[kLB[B.xrow]].max() - 1e-9
    gl = [s["clauses"]["LB"]["g_star"][k] for k in ("0.025", "0.05", "0.1")]
    assert all(a is None or b is None or a >= b for a, b in zip(gl, gl[1:])), gl                  # a stricter level never needs less margin
    assert s["ladder"][3]["label"] == "K_book" and s["ladder"][3]["g_star"] == s["g_star"]           # g*(K_book) is g*
    assert [r["K"] for r in s["ladder"]][-2:] == [K_CEILING, 500] and s["ladder"][6]["label"] == "K_ceiling"
    assert all(os.path.exists(os.path.join(OUT, n)) for n in ("LOOKS.txt", "margin_curve.csv", "past_passes.csv", "nulls.json", "READY")) and os.path.exists(DOC)
    for n in ("LOOKS.txt", "LOOKS_R1.md"):
        open(os.path.join(OUT, n), encoding="utf-8").read().encode("ascii")
    pp = pd.read_csv(os.path.join(OUT, "past_passes.csv"))
    assert len(pp) == len(PAST) and pp["found"].all()
    # refusals after a pass: the ledger changed after parity; READY gone
    write_smoke_ledger(LEDGER, SMOKE_LEDGER + [("L099", "2026-10-04", "x", "#999 late look", "SWAP", "#463", "unified", "", "", "", "", "", "1.0", "FAIL", "", "look")])
    try:
        run()
        raise AssertionError("smoke: run() must refuse when the ledger changed after parity")
    except SystemExit:
        pass
    write_smoke_ledger(LEDGER)
    os.remove(_ready_path())
    try:
        run()
        raise AssertionError("smoke: run() must refuse without READY")
    except SystemExit:
        pass
    print(f"SMOKE OK ({world}; g* {gfmt(s['g_star'])}, g_adj {gfmt(s['g_adj'])}, sd_null {s['calibration']['sd_null']:.3f}, FWER(0) {s['H0']['FWER_0']:.3f} - "
          f"meaningless; {time.time() - t0:.0f}s)", flush=True)


if __name__ == "__main__":
    cmd = sys.argv[1:]
    if cmd == ["ledger"]:
        ledger()
    elif cmd == ["parity"]:
        parity()
    elif cmd == ["run"]:
        run()
    elif len(cmd) in (2, 3) and cmd[0] == "smoke":
        smoke(cmd[1], *(cmd[2:] or ["null"]))
    else:
        print("usage: r14_looks.py ledger | parity | run | smoke DIR [null|planted]")
        sys.exit(2)
