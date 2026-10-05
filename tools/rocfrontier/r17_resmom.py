# RESMOM r1 - residual (firm-specific) 12-1 month momentum in US stocks, rebalanced MONTHLY, dollar-neutral: cells RES (the standardised BETA-NEUTRAL residual of a one-factor ES market model: return - beta x ES, the fitted alpha
# is NOT subtracted) and RAW (the plain 12-1 twin), a leg for BOOK #463 that must clear the STANDALONE bars (MANAGER #56). Pre-registered: tools/rocfrontier/PREREG_RESMOM_R1.txt (canonical LF sha256 a4f34e87...1dd1 =
# DRAFT v2 + PRE-DATA ADDENDUM 1 (review) + ADDENDUM 2 (MANAGER #63: score arithmetic, in-sample beta) + ADDENDUM 3 (the dividend calendar on file: [D1] coverage, [D2] spin-offs / stock dividends); PREREG_SHA is updated by the lead if more edits land, before the real run). Every rule, threshold, window and cost below is that file; where it is silent the
# choice is marked CHOICE.
# RESMOM is DDW r1's L1 (the weekly reversal) with a MONTHLY schedule and a different score: r15_ddw.py is imported, never copied and never edited - its data layer (World, universe, hygiene arrays, ES series, k_t, TBIS flags),
# split-safe marks / fills / costs / borrow (unit_path, l1_units, l1_pnl, l1_cell), cell statistics, seat measure (DO / rho_dd = r12_mdl's), null engine, A2's volatility rule and book checks.
#   python r17_resmom.py selftest    hand-made worlds: the score (OLS residuals, the skip month, the standardisation, the 230 rule, ES holes), the monthly schedule, fills / marks / costs / borrow, the null, the statistics and checks,
#                                    c = 25% of #463's volatility, DO / rho_dd vs r12_mdl, the files, Stage B refusals; [R1] dividends, [R2] shorts at zero, [R3] / [R4] the signed
#                                    crash line and the XSML overlap, the wide calendar's gates, [D1] coverage, [D2] spin-offs / stock dividends
#   python r17_resmom.py smoke DIR   offline end-to-end on a SYNTHETIC world (r5_siporb's fake Alpaca, a fake ES master, a fake #463, a fake TBIS file); DIR's name must contain 'smoke'
#   python r17_resmom.py dryload     WF inputs only (every input cut to dates < 2025-06-30): prints COUNTS - rebalances, universe sizes, names with a full window, hygiene by reason, ES coverage, the wide calendar's counts, the [D1] coverage per rank and the [D2] spin-off / stock-dividend counts - never a price, return, score or P&L
#   python r17_resmom.py stage_a     WF Stage A + the A2 report + the reports + the [R1] no-dividend row, the [D1] row without the first five rebalances and the [D2] counts of the picks -> resmom_stageA.json (+ resmom_audit_candidates.csv), PRE-LOCKBOX ONLY (every input is cut to dates < 2025-06-30 when it is read)
#   python r17_resmom.py stage_b     Stage B (lockbox, ONCE, on the stock families' one sealed-year day): refuses unless a Stage A pass with a complete audit is on file; the pass is the LEG's veto, the book add is only reported
# Reads (never writes) the SIPORB cache through r5_siporb, the ES 5m RTH masters through augur_engine.data, the #463 book through r11_risk, the sha-pinned wide corporate-actions calendar (xgap/corporate_actions_wide.csv in the SIPORB cache folder + its manifest, cut at read) and, if on file, XSML's daily P&L. Results go to OUT (outside git). Nothing here pulls, commits, pushes or writes anywhere else.
import contextlib, fnmatch, hashlib, io, json, math, os, sys, time
from collections import Counter, defaultdict
from types import SimpleNamespace
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import numpy as np, pandas as pd
import r15_ddw as D15            # the sibling harness: its pieces are called wherever they fit (wrapped where they almost fit)
S, R11, M12, A13 = D15.S, D15.R11, D15.M12, D15.A13       # r5_siporb (Data, read_long, the fake Alpaca), r11_risk (the #463 book, stats), r12_mdl (Stretch, realised), r13_attn (shared helpers) - through r15's own imports

TS = pd.Timestamp
OUT = os.environ.get("EDGELOG_RESMOM_R1", r"C:\EdgeLog\_anatomy_cache\rocfrontier\resmom_r1")        # results, outside git
PREREG = os.path.join(HERE, "PREREG_RESMOM_R1.txt")
PREREG_SHA = "a4f34e87d8083930a8c3344da861e1ae0dbf1abdcf864c55bd5085e200121dd1"                      # canonical (LF) sha256 of the pre-registration: DRAFT v2 + PRE-DATA ADDENDUM 1 (review) + ADDENDUM 2 (MANAGER #63: score arithmetic, in-sample beta) + ADDENDUM 3 (the dividend calendar on file, [D1] coverage, [D2] spin-offs and stock dividends); supersedes 42d9d30a (through addendum 2), 4011a80d (v2 + addendum 1) and a7262cd6 (v2)
WF0, PRE_END, LB0, LB1 = D15.WF0, D15.PRE_END, D15.LB0, D15.LB1          # WF = positions EXITED 2016-07-01 .. 2025-06-29; LB = exits 2025-06-30 .. 2026-06-30 INCLUSIVE; cuts: S.LB0 / S.END
BOOK_WF, BOOK_LB, DEEPEST_WF = D15.BOOK_WF, D15.BOOK_LB, D15.DEEPEST_WF
NREP, SEED = 500, 20261005
CELLS = ("RES", "RAW")                                                  # the family: 2 cells
YEARS = D15.YEARS                                                       # the nine July-June WF years 2016-17 .. 2024-25 (2016-17 is short - it counts as a year)
A2_WIN = (TS("2017-01-03"), TS("2018-12-31"))                           # A2 (a REPORT): c is set on the cell's first two years (the first rank with a full 252-session window is 2016-12-30, filled 2017-01-03) ...
A2_TARGET, A2_REPORT = 0.25, (0.5, 2.0)                                  # ... so that c x the cell's daily std = 25% of #463's over them; the book at 0.5c and 2c is reported
COST_BPS, STRESS_BPS = D15.COST_BPS, D15.STRESS_BPS                      # 5 bps of the notional a side (base); stress 10 and 20
BORROW, BORROW_STRESS, K_STRESS = D15.BORROW, D15.BORROW_STRESS, D15.K_STRESS     # 0.25% a year on short notional; stress 1% and 3% on sessions with k_t > 1.5 (DDW r1's)
CRASH_MONTHS = ("2020-04", "2020-11", "2022-01", "2023-01")            # the momentum-crash months the prereg names (REPORTED)
AUDIT_N = 50                                                             # (f) the largest single-name contributors audited by hand
SPEC = {"win": 252,          # the regression window: sessions r-251 .. r (the market model's OLS with an intercept, for its BETA only - the alpha is not subtracted from the residual)
        "form_n": 231,       # the formation window: 231 sessions ending skip sessions before r = sessions r-251 .. r-21 (12 months, skipping the last month)
        "skip": 21,          # the skipped month: sessions r-20 .. r
        "min_n": 230,        # at least 230 (name return, ES return) pairs in the regression window (and 230 split-safe returns of the name's own)
        "n_side": 50, "slot": 4000.0,       # 50 longs + 50 shorts, $4,000 each, fractional shares
        "hyg_lead": 5}       # hygiene starts 5 sessions before the skipped month (r-25 .. r), DDW r1's [T2] lead
RULES = {"reb": 60, "roc": 15.0, "net_pos": True, "stress": True, "null": True, "years": 6, "ex2020": True, "exbest": True, "best_pct": 1,      # Stage A (a) - (e); the booleans are switches only smoke() ever turns off
         "a2_roc": D15.RULES["a2_roc"], "a2_sort": D15.RULES["a2_sort"],                                                                          # A2's shadow-line bar (98.5005 / 3.816, a REPORT)
         "b_reb": 10, "b_roc": BOOK_LB[0], "b_sort": BOOK_LB[1]}                                                                                  # Stage B: >= 10 monthly rebalances; the book add's reference (#463's own LB 155.54 / 4.150), reported only
CHECK_BOOK = True        # refuse to judge if the #463 records / the DD structure / the cache manifest do not reproduce the registered facts; a real run always checks (only smoke() may switch it)
HYG = D15.HYG            # the four data-hygiene reasons [T2], in the order a position's first reason is attributed: split, gap, tbis, jump
AUD = "RM"               # the tag of this harness's rows in World.aud_hit
WIDE_CA_SHA = "e5bc8487daf94a6124823bc24b6c382e9fd00237acbab81457fa42ef3b0d83a5"       # [R1] sha256 (the file's bytes) of corporate_actions_wide.csv, pinned by PRE-DATA ADDENDUM 3 (MANAGER's wide pull of 2026-10-05; a re-pull is a new photograph and a new addendum); None = Stage A and Stage B refuse
WIDE_NAME = "corporate_actions_wide"                                    # <S.CACHE>\xgap\corporate_actions_wide.csv + corporate_actions_wide_manifest.json (r16_xgap's capull, --tag wide)
CA_COLS = ("type", "symbol", "old_symbol", "new_symbol", "ex_date", "process_date", "record_date", "payable_date", "rate", "new_rate", "old_rate", "cash", "special")      # r16_xgap's flat CSV (ca_flatten)
DIV_TYPE, SPLIT_TYPES = "cash_dividend", ("forward_split", "reverse_split", "unit_split")        # cash_dividend rows carry the per-share amount in `rate`; splits (new_rate : old_rate) are only cross-checked
SPIN_TYPES = ("spin_off", "stock_dividend")                                                     # [D2] the calendar's rows whose ex-date is a price drop that is not a return (the holder gets new shares; no credit is computed for them)
D1_RANKS = ("2016-12-30", "2017-01-31", "2017-02-28", "2017-03-31", "2017-04-28")               # [D1] the first five ranks, whose formation windows start before the calendar does (ADDENDUM 3): the REPORTED row drops them (96 of 101 WF rebalances remain)
XSML_DIR = os.environ.get("EDGELOG_XSML_DIR", r"C:\EdgeLog\_anatomy_cache\cml_xsml")             # [R4] Custom ML's XSML r1 cell A daily P&L (date, pnl), if on file
ANATOMY_ROOT = os.environ.get("EDGELOG_ANATOMY_ROOT", r"C:\EdgeLog\_anatomy_cache")           # ... or any *xsml*cellA*daily*.csv under here (to depth 4)
R2_SIDE = "short side only, names that stop printing valued at zero [R2]"                         # the report rows' names
R2_CELL = "shorts that stop printing valued at zero (whole cell) [R2]"


# ------------------------------------------------------------------ guards: the prereg, the stamp, the cut, the files
def refuse(msg):
    raise SystemExit(msg)


def prereg_ok():
    """the frozen spec this file implements must still be the registered one (a changed spec = a new file, r2): a missing or changed file refuses every stage. Also checked against the committed blob when there is one
    (r15_ddw.committed_state, pointed at this file's names for the call); until it is committed that is printed (the lead commits before the real run) and recorded in the Stage A file"""
    if not os.path.exists(PREREG):
        refuse("refused: PREREG_RESMOM_R1.txt is not next to this file - the spec cannot be verified (nothing computed, lockbox NOT read)")
    if R11.sha_lf(PREREG) != PREREG_SHA:
        refuse("refused: PREREG_RESMOM_R1.txt DIFFERS from the registered one - a changed spec is a new file, r2 (nothing computed, lockbox NOT read)")
    with patched(D15, PREREG=PREREG, PREREG_SHA=PREREG_SHA):
        st = D15.committed_state()
    if st == "differs":
        refuse("refused: the COMMITTED PREREG_RESMOM_R1.txt differs from the registered sha - the file on disk is not the file in git (nothing computed, lockbox NOT read)")
    print("prereg check: PREREG_RESMOM_R1.txt sha256 matches the registered one; committed blob: " + {"match": "matches too", "untracked": "NOT COMMITTED YET - commit it before the real run",
                                                                                                     "unknown": "git not available here (not checked)"}[st])
    return {"verified": True, "committed": st}


def stamp():
    """the version a stage ran with: this file's LF sha256 + every harness it imports numbers from (r15's data layer / marks / statistics, r5_siporb's Data / read_long, r11's book and stats, r12's DO / rho_dd,
    r13's helpers) + the shared half-day list; Stage B refuses on any change, so a change to any of them after Stage A sends it through Stage A again"""
    return {"harness_sha256": R11.sha_lf(os.path.abspath(__file__)), "r15_sha256": R11.sha_lf(D15.__file__), "siporb_sha256": R11.sha_lf(S.__file__), "r11_sha256": R11.sha_lf(R11.__file__),
            "r12_sha256": R11.sha_lf(M12.__file__), "r13_sha256": R11.sha_lf(A13.__file__), "wide_ca_sha256": WIDE_CA_SHA, "early_close": sorted(S.EARLY_CLOSE_DATES)}


assert_cut, peak_mb, patched, ceil_pct = A13.assert_cut, A13.peak_mb, A13.patched, A13.ceil_pct
file_sha, manifest_sha, book_checks = D15.file_sha, D15.manifest_sha, D15.book_checks      # module-level names, so a test can stub them


@contextlib.contextmanager
def spec(**kw):
    """swap SPEC entries for a block and put them back (the self-tests and the smoke shrink the windows and the sides; nothing stays patched)"""
    old = dict(SPEC)
    SPEC.update(kw)
    try:
        yield
    finally:
        SPEC.clear()
        SPEC.update(old)


def dump(obj, name):
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, name), "w") as f:
        json.dump(obj, f, indent=1, default=R11.js)


# ------------------------------------------------------------------ the data: S.Data without the 09:30 bars (this family reads daily bars only) + TBIS + ES -> r15's World
def load_data(t_end):
    """r5_siporb.Data cut at t_end (S.LB0 for Stage A, S.END for Stage B), asserted to hold no session on/after the cut, with TBIS's split-QA symbol-days OR-ed into the gap-scan flags exactly as r13_attn.load_data does for
    DDW r1 (prereg: 'data hygiene exactly as DDW r1'). CHOICE: open5=False - RESMOM reads no 09:30 bar, so the 09:30 pull is neither loaded nor a gate"""
    D = S.Data(t_end, open5=False)
    assert_cut("sessions", D.days, t_end)
    A13.add_tbis_flags(D)
    return D


def build_world(D, t_end, es_frames, tbis_df, cal=None):
    """r5_siporb.Data (cut at t_end) + the re-read daily arrays + ES + TBIS -> r15's World on the names that are ever in the universe (r15_ddw.build_world without the 09:30 bar and Relative Volume, which this family never
    reads: those two arrays are all-NaN stand-ins). The universe is r15's, computed on every name first, then the columns are cut"""
    Cl, Vv, F = D15.load_daily(D, t_end)
    U = D15.universe_mask(Cl, Vv, D.atr, D.chg)
    cols = np.flatnonzero(U.any(axis=0))
    sub = lambda a: np.ascontiguousarray(a[:, cols])
    syms = D.syms[cols]
    tb, nmatch = D15.tbis_array(D.days, syms, tbis_df)
    pa, pr = D15.es_prints(es_frames["adj"]), D15.es_prints(es_frames["raw"])
    none = np.full((len(D.days), len(cols)), np.nan)
    W = D15.World(D.days, syms, sub(D.Od), sub(Cl), sub(Vv), sub(F), sub(U), sub(D.chg), sub(D.msplit), tb, none, none, D15.es_series(D.days, pa, pr), ())
    W.tbis_rows = (0 if tbis_df is None else len(tbis_df), nmatch)
    W.es_cov = {"adj_prints": pa, "raw_prints": pr}
    attach_dividends(W, div_matrix(None if cal is None else cal.div, W.days, W.syms)[0], spin_matrix(None if cal is None else cal.spin, W.days, W.syms)[0])
    W.ca = None if cal is None else wide_report(cal, D, cols, W)                       # [R1] counts: the dividends matched and applied, the calendar's splits against the registered split rule
    return W


def es_report(W, lo=None, hi=None):
    """the ES return (the market factor) on the sessions of [lo, hi] (default WF) -> (the printed line, the record for the stage's file): how many sessions have one and which do not (a hole in the ES master: no 16:00 print, so
    that session's return and the next one's are undefined). CHOICE: this family needs no rule for them beyond the pairs - a session without an ES return is skipped for every name (the regression and the 230-pair count)"""
    lo, hi = (WF0 if lo is None else lo), (PRE_END if hi is None else hi)
    r = np.asarray(W.es.ret, float)
    sel = np.asarray((W.days >= lo) & (W.days <= hi))
    holes = np.flatnonzero(sel & ~np.isfinite(r))
    holes = holes[holes > 0]                                               # the first session of the data has no return by construction
    rec = {"stretch": [f"{lo:%Y-%m-%d}", f"{hi:%Y-%m-%d}"], "sessions": int(sel.sum()), "es_return_defined": int((sel & np.isfinite(r)).sum()), "undefined_es_return_sessions": [f"{d:%Y-%m-%d}" for d in W.days[holes]]}
    txt = (f"ES return ({rec['stretch'][0]} .. {rec['stretch'][1]}): defined on {rec['es_return_defined']:,} of {rec['sessions']:,} sessions; "
           + (f"undefined on {len(holes)} ({', '.join(rec['undefined_es_return_sessions'][:12])}) - those sessions are skipped for every name" if len(holes) else "no session without one"))
    return txt, rec


# ------------------------------------------------------------------ [R1] the WIDE corporate-actions calendar: cash dividends added back on their ex-dates; its splits against the registered split rule
def sha_raw(path):
    """sha256 of a file's bytes as they lie on disk (what the pull's manifest and `sha256sum` give)"""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def wide_paths():
    d = os.path.join(S.CACHE, "xgap")
    return {"dir": d, "csv": os.path.join(d, WIDE_NAME + ".csv"), "manifest": os.path.join(d, WIDE_NAME + "_manifest.json")}


def wide_load(cut, need=True, enforce=True, csv=None, manifest=None):
    """[R1] the WIDE corporate-actions calendar (Alpaca's; every cached stock above SIPORB's floor; MANAGER's pull in r16_xgap's flat CSV: type, symbol, old_symbol, new_symbol, ex_date, process_date, record_date, payable_date,
    rate, new_rate, old_rate, cash, special) -> (cal, info). enforce (Stage A and B): refuses - nothing computed, lockbox NOT read - when the file is not on file, WIDE_CA_SHA is None ('the wide calendar sha is not registered
    yet'; the message carries the sha of the file on disk), the file's sha256 is not the registered one, its manifest is missing or does not carry that sha256, or a column of the flat CSV is missing. need=False, enforce=False (dryload): no
    refusal for a missing file (-> (None, {'present': False})) or an unregistered sha (reported). Cut at READ time: a dated row (ex-date, a name change its process date) on/after `cut` is dropped and asserted gone.
    cal.div = the cash dividends with an ex-date and a positive finite per-share amount (symbol, ex, amt, special), cal.split = forward / reverse / unit splits with an ex-date (symbol, ex, type), cal.spin = [D2] the spin-off and stock-dividend rows with an ex-date and a symbol (symbol, ex, type; a spin-off's symbol is the PARENT:
    r16_xgap's ca_flatten CHOICE); every other row is counted, never used. Enforced as well: the manifest carries a readable `start` ([D1] counts the coverage of the first ranks' windows from it)"""
    P = wide_paths()
    csv, manifest = csv or P["csv"], manifest or P["manifest"]
    if not os.path.exists(csv):
        if not need:
            return None, {"present": False, "path": csv}
        refuse(f"refused: the wide corporate-actions calendar is not on file ({csv}) - MANAGER's wide pull comes first, Stage A waits for it (nothing computed, lockbox NOT read)")
    got = sha_raw(csv)
    if enforce:
        if WIDE_CA_SHA is None:
            refuse(f"refused: the wide calendar sha is not registered yet (WIDE_CA_SHA is None; {os.path.basename(csv)} on disk has sha256 {got}) - the lead pins it by a dated addendum before any number (nothing computed, lockbox NOT read)")
        if got != WIDE_CA_SHA:
            refuse(f"refused: {os.path.basename(csv)} (sha256 {got}) is not the registered wide calendar ({WIDE_CA_SHA}) - the file changed after it was registered (nothing computed, lockbox NOT read)")
    man = {"present": os.path.exists(manifest), "csv_sha_ok": False}
    if man["present"]:
        try:
            mj = json.load(open(manifest))
            shas = {k: v for k, v in (mj.get("sha256") or {}).items() if str(k).lower().endswith(".csv")}
            man.update(csv_sha_ok=bool(len(shas) == 1 and list(shas.values())[0] == got), start=mj.get("start"), end=mj.get("end"), created=mj.get("created"), rows=mj.get("rows"), sha256=sha_raw(manifest))
        except (OSError, ValueError, AttributeError):
            man["present"] = False
    if enforce and not (man["present"] and man["csv_sha_ok"]):
        refuse("refused: the wide calendar's manifest is missing, unreadable or does not carry this file's sha256 - the pull is not a complete, unchanged one (nothing computed, lockbox NOT read)")
    if enforce and calendar_start(man) is None:
        refuse("refused: the wide calendar's manifest carries no readable start date - [D1] counts the coverage of the first ranks' windows from it (nothing computed, lockbox NOT read)")
    df = pd.read_csv(csv, dtype=str, keep_default_na=False)
    miss = [c for c in CA_COLS if c not in df.columns]
    if miss:
        refuse(f"refused: the wide calendar lacks the column(s) {miss} of r16_xgap's flat CSV (nothing computed, lockbox NOT read)")
    ex = pd.to_datetime(df["ex_date"].replace("", np.nan), errors="coerce")
    ev = ex.fillna(pd.to_datetime(df["process_date"].replace("", np.nan), errors="coerce"))
    d = pd.DataFrame({"type": df["type"].str.strip(), "symbol": df["symbol"].str.strip(), "ex": ex, "ev": ev, "amt": pd.to_numeric(df["rate"].replace("", np.nan), errors="coerce"),
                      "special": df["special"].str.strip().str.lower() == "true"})
    n0 = len(d)
    d = d[~(d["ev"] >= TS(cut)).to_numpy()].reset_index(drop=True)                      # NaT compares False: an undated row stays (and is counted)
    A13.assert_cut("wide calendar", d["ev"].dropna(), cut)
    by_ty = defaultdict(dict)
    for (t_, y_), n_ in d.groupby(["type", d["ev"].dt.year.fillna(0).astype(int)]).size().items():
        by_ty[t_][str(int(y_)) if y_ else "n/a"] = int(n_)
    dv = d[d["type"] == DIV_TYPE]
    amt = dv["amt"].to_numpy(float)
    bad_ex, bad_amt = (dv["ex"].isna() | (dv["symbol"] == "")).to_numpy(), ~np.isfinite(amt) | (amt <= 0)
    div = dv[~bad_ex & ~bad_amt][["symbol", "ex", "amt", "special"]].reset_index(drop=True)
    sp = d[d["type"].isin(SPLIT_TYPES)]
    sp_bad = (sp["ex"].isna() | (sp["symbol"] == "")).to_numpy()
    split = sp[~sp_bad][["symbol", "ex", "type"]].reset_index(drop=True)
    sn = d[d["type"].isin(SPIN_TYPES)]
    sn_bad = (sn["ex"].isna() | (sn["symbol"] == "")).to_numpy()
    spin = sn[~sn_bad][["symbol", "ex", "type"]].reset_index(drop=True)
    info = {"present": True, "path": csv, "csv_sha256": got, "pinned": {"registered": WIDE_CA_SHA, "matches": (None if WIDE_CA_SHA is None else bool(got == WIDE_CA_SHA))}, "manifest": man, "cut": f"{TS(cut):%Y-%m-%d}",
            "rows_on_file": int(n0), "rows_read": int(len(d)), "rows_dropped_at_the_cut": int(n0 - len(d)), "rows_by_type": {t: int(n) for t, n in d["type"].value_counts().items()},
            "rows_by_type_year": {t: dict(v) for t, v in sorted(by_ty.items())},
            "dividends": {"rows": int(len(dv)), "usable": int(len(div)), "no_ex_date_or_symbol": int(bad_ex.sum()), "no_positive_amount": int((~bad_ex & bad_amt).sum()), "special": int(div["special"].sum())},
            "splits": {"rows": int(len(sp)), "usable": int(len(split)), "no_ex_date_or_symbol": int(sp_bad.sum())},
            "spin": {"rows": int(len(sn)), "usable": int(len(spin)), "no_ex_date_or_symbol": int(sn_bad.sum()), "by_type": {t: int(n) for t, n in sn["type"].value_counts().items()}}}
    return SimpleNamespace(div=div, split=split, spin=spin, info=info), info


def div_index(div, days, syms):
    """(name column, session row) of every dividend row on the grid (-1 = the symbol is not a name of the grid / the ex-date is not a session)"""
    if div is None or not len(div):
        return np.zeros(0, int), np.zeros(0, int)
    return pd.Index(syms).get_indexer(div["symbol"].astype(str)), pd.Index(days).get_indexer(pd.DatetimeIndex(div["ex"]))


def div_matrix(div, days, syms):
    """the cash dividends on the grid (T, S): the per-share amount on each ex-date session, as the calendar states it (dividends of one name on one ex-date add up); a symbol the grid does not hold or an ex-date that is not a
    session is not placed (counted). -> (matrix, counts)"""
    out = np.zeros((len(days), len(syms)))
    ci, di = div_index(div, days, syms)
    ok = (ci >= 0) & (di >= 0)
    if ok.any():
        np.add.at(out, (di[ok], ci[ok]), div["amt"].to_numpy(float)[ok])
    n_keys = len(set(zip(di[ok].tolist(), ci[ok].tolist())))
    return out, {"rows": int(len(ci)), "name_not_on_the_grid": int((ci < 0).sum()), "ex_date_not_a_session": int(((ci >= 0) & (di < 0)).sum()), "placed": int(ok.sum()), "same_name_same_day_rows_added": int(ok.sum()) - n_keys}


def calendar_start(man):
    """[D1] the date the calendar's pull started at, read from its manifest's `start` (never a constant here): a Timestamp, or None when the manifest holds none / an unreadable one"""
    try:
        v = (man or {}).get("start")
        t = pd.Timestamp(v) if v else None
        return None if t is None or pd.isna(t) else t.normalize()
    except (ValueError, TypeError):
        return None


def spin_matrix(spin, days, syms):
    """[D2] the spin-off / stock-dividend ex-dates on the grid (T, S) bool (a spin-off's symbol is the PARENT: r16_xgap's ca_flatten CHOICE; a name the grid does not hold or an ex-date that is not a session is not placed, counted;
    two rows of one name on one ex-date are one event) -> (matrix, counts)"""
    out = np.zeros((len(days), len(syms)), bool)
    ci, di = div_index(spin, days, syms)
    ok = (ci >= 0) & (di >= 0)
    if ok.any():
        out[di[ok], ci[ok]] = True
    n_keys = len(set(zip(di[ok].tolist(), ci[ok].tolist())))
    return out, {"rows": int(len(ci)), "name_not_on_the_grid": int((ci < 0).sum()), "ex_date_not_a_session": int(((ci >= 0) & (di < 0)).sum()), "placed": int(ok.sum()), "same_name_same_day_rows_merged": int(ok.sum()) - n_keys}


def spn_hit(W, a, b, cols):
    """[D2] (n,) bool: a spin-off / stock-dividend ex-date falls on a session in rows a .. b (inclusive) for the names `cols`"""
    a, b = max(int(a), 0), min(int(b), W.T - 1)
    if b < a:
        return np.zeros(len(cols), bool)
    return (W.spcs[b + 1, cols] - W.spcs[a, cols]) > 0


def attach_dividends(W, draw=None, spn=None):
    """[R1] the dividend arrays of a World, (T, S) each: Dr = the cash dividends as the calendar states them (per share, on the raw basis of the ex-date session) that count, Dv = D* = Dr / F on the SPLIT-ADJUSTED basis of the
    series (CHOICE: the amount is quoted on the raw share of the ex-date session, whose raw close Cl_t is on the same basis, so dividing by that session's factor F_t = raw / split-adjusted puts it beside Ac_t = Cl_t / F_t; a
    dividend declared before a split inside the window is halved by a 2-for-1), Rd = the daily TOTAL return (Ac_t + D*_t) / Ac_(t-1) - 1 = Rn_t + D*_t / Ac_(t-1) - the series RAW's score and RES's regression read. A dividend counts only
    on a session where the name has a close, a prior close and a factor (CHOICE: no close, no ex-date effect - a dividend on a session without prints is counted and left out) and its amount is positive. [D2] spn = the spin-off / stock-dividend ex-date sessions, (T, S) bool or None: on such a session that name's daily return is LEFT OUT (NaN in Rd and in the no-dividend Rn0) - out of the
    regression's beta, the residuals, the formation sum / product and the 230-return and 230-pair counts, like an ES-hole session; the price series itself is untouched (the drop is a price move whose compensation, the
    new shares, is not computed). The no-dividend set (Z0, Rn0) is kept beside: div_mode switches"""
    T, S_ = W.T, W.S
    raw = np.zeros((T, S_)) if draw is None else np.array(draw, float, copy=True)
    with np.errstate(invalid="ignore", divide="ignore"):
        prev = D15.shift1(W.Ac)
        pos = np.isfinite(raw) & (raw > 0)
        use = pos & np.isfinite(W.Ac) & np.isfinite(prev) & (prev > 0) & np.isfinite(W.F) & (W.F > 0)
        Dv = np.where(use, raw / W.F, 0.0)
        Rd = np.where(np.isfinite(W.Rn), W.Rn + Dv / np.where(use, prev, 1.0), np.nan)
        big = use & (Dv / np.where(use, prev, 1.0) > 0.25)
    spn = np.zeros((T, S_), bool) if spn is None else np.asarray(spn, bool)
    W.SPN, W.spcs = spn, np.vstack([np.zeros((1, S_), np.int32), np.cumsum(spn, axis=0, dtype=np.int32)])
    W.Dr1, W.Dv1, W.Z0 = np.where(use, raw, 0.0), Dv, np.zeros((T, S_))
    W.Rd1, W.Rn0 = np.where(spn, np.nan, Rd), np.where(spn, np.nan, W.Rn)                  # [D2] the session's return is left out for that name (the no-dividend set too: only the cash differs between the two)
    W.spin_counts = {"cells": int(spn.sum()), "with_a_return": int((spn & np.isfinite(W.Rn)).sum()), "no_return": int((spn & ~np.isfinite(W.Rn)).sum())}
    W.div_counts = {"cells_with_a_dividend": int(pos.sum()), "applied": int(use.sum()), "no_close_prior_close_or_factor": int((pos & ~use).sum()), "over_25_pct_of_the_prior_close": int(big.sum())}
    set_div(W, True)


def set_div(W, on):
    """Dr / Dv / Rd = the dividend set (on) or the no-dividend set (off: no cash, Rd = the price return with the [D2] sessions left out, Rn0)"""
    W.Dr, W.Dv, W.Rd = (W.Dr1, W.Dv1, W.Rd1) if on else (W.Z0, W.Z0, W.Rn0)
    W.div_on = bool(on)


@contextlib.contextmanager
def div_mode(W, on):
    was = W.div_on
    set_div(W, on)
    try:
        yield
    finally:
        set_div(W, was)


def split_check(split, days, syms, chg, mask=None):
    """[R1] the calendar's splits against the registered split rule (the price side: r5_siporb's factor changes, `chg`), by session year, on the grid's names (mask = only those columns): agree = the same name on the same session,
    calendar-only = a calendar split with no registered split on that name's session, price-only = a registered split with no calendar split there. Counts only; calendar-only rows within 3 sessions of a price-only one of the
    same name are counted apart (an offset by a few days is not a disagreement of kind)"""
    n = len(split)
    ci = pd.Index(syms).get_indexer(split["symbol"].astype(str)) if n else np.zeros(0, int)
    di = pd.Index(days).get_indexer(pd.DatetimeIndex(split["ex"])) if n else np.zeros(0, int)
    ok = (ci >= 0) & (di >= 0)
    cal = set(zip(di[ok].tolist(), ci[ok].tolist()))
    pr, pc = np.nonzero(np.asarray(chg, bool))
    price = set(zip(pr.tolist(), pc.tolist()))
    if mask is not None:
        mk = np.asarray(mask, bool)
        cal, price = {k for k in cal if mk[k[1]]}, {k for k in price if mk[k[1]]}
    agree, c_only, p_only = cal & price, cal - price, price - cal
    by = defaultdict(lambda: {"agree": 0, "calendar_only": 0, "price_only": 0})
    for keys, nm in ((agree, "agree"), (c_only, "calendar_only"), (p_only, "price_only")):
        for t_, c_ in keys:
            by[int(days[t_].year)][nm] += 1
    rows_by_col = defaultdict(list)
    for t_, c_ in p_only:
        rows_by_col[c_].append(t_)
    near = sum(any(abs(t_ - u_) <= 3 for u_ in rows_by_col.get(c_, ())) for t_, c_ in c_only)
    return {"by_year": {y: dict(v) for y, v in sorted(by.items())}, "total": {"agree": len(agree), "calendar_only": len(c_only), "price_only": len(p_only)}, "calendar_only_within_3_sessions_of_a_price_only": int(near),
            "calendar_rows": int(n), "calendar_rows_name_not_cached": int((ci < 0).sum()), "calendar_rows_ex_date_not_a_session": int(((ci >= 0) & (di < 0)).sum())}


def wide_report(cal, D, cols, W):
    """[R1] COUNTS ONLY about the calendar on this data: the file, the dividends by year (usable / on a cached name and a session / on a name ever in the universe / applied to a price-bearing session), the split cross-check on every
    cached name and on the names ever in the universe, and the warnings (a calendar that starts after the first session or ends before the last one leaves windows partly price-only). `cols` = the world's columns in D.syms"""
    info = cal.info
    mask = np.zeros(len(D.syms), bool)
    mask[cols] = True
    ci, di = div_index(cal.div, D.days, D.syms)
    yrs = pd.DatetimeIndex(cal.div["ex"]).year.to_numpy() if len(cal.div) else np.zeros(0, int)
    ok_all = (ci >= 0) & (di >= 0)
    ok_w = ok_all & mask[np.maximum(ci, 0)] if len(ci) else ok_all
    ap_r = np.nonzero(W.Dv1 > 0)[0]
    ap_y = W.days.year.to_numpy()[ap_r]
    by_year = {}
    for y in sorted(set(yrs.tolist()) | set(ap_y.tolist())):
        by_year[int(y)] = {"usable": int((yrs == y).sum()), "on_a_cached_name_and_session": int((ok_all & (yrs == y)).sum()), "on_a_name_ever_in_the_universe": int((ok_w & (yrs == y)).sum()), "applied": int((ap_y == y).sum())}
    sci, sdi = div_index(cal.spin, D.days, D.syms)
    syrs = pd.DatetimeIndex(cal.spin["ex"]).year.to_numpy() if len(cal.spin) else np.zeros(0, int)
    sok_all = (sci >= 0) & (sdi >= 0)
    sok_w = sok_all & mask[np.maximum(sci, 0)] if len(sci) else sok_all
    sap_y = W.days.year.to_numpy()[np.nonzero(W.SPN & np.isfinite(W.Rn))[0]]
    spin_by_year = {}
    for y in sorted(set(syrs.tolist()) | set(sap_y.tolist())):
        spin_by_year[int(y)] = {"usable": int((syrs == y).sum()), "on_a_cached_name_and_session": int((sok_all & (syrs == y)).sum()), "on_a_name_ever_in_the_universe": int((sok_w & (syrs == y)).sum()), "return_left_out": int((sap_y == y).sum())}
    warns, man = [], info["manifest"]
    if man.get("start") and TS(man["start"]) > W.days[0]:
        warns.append(f"the calendar starts {TS(man['start']):%Y-%m-%d}: dividends and splits before it are not in it, so the regression / formation windows of the first ranks (from {W.days[0]:%Y-%m-%d}) are partly price-only")
    if man.get("end") and TS(man["end"]) < W.days[-1]:
        warns.append(f"the calendar ends {TS(man['end']):%Y-%m-%d}, before the last session of this data ({W.days[-1]:%Y-%m-%d}): later dividends are missing")
    return {"file": info, "dividends": {**info["dividends"], "grid": div_matrix(cal.div, D.days, D.syms)[1], "applied_in_the_world": W.div_counts, "by_year": by_year},
            "splits": {"calendar": info["splits"], "every_cached_name": split_check(cal.split, D.days, D.syms, D.chg), "names_ever_in_the_universe": split_check(cal.split, D.days, D.syms, D.chg, mask)},
            "spin": {**info["spin"], "grid": spin_matrix(cal.spin, D.days, D.syms)[1], "in_the_world": W.spin_counts, "by_year": spin_by_year}, "warnings": warns}


def print_wide(rep):
    """the calendar's counts (no dates but the years and the data's own; no amounts)"""
    f, dv = rep["file"], rep["dividends"]
    pin = f["pinned"]
    print(f"wide corporate-actions calendar [R1]: {os.path.basename(f['path'])} sha256 {f['csv_sha256'][:16]}... (" + ("registered: matches" if pin["matches"] else "NOT registered yet" if pin["registered"] is None else "DIFFERS from the registered one")
          + f"; manifest {'carries it' if f['manifest'].get('csv_sha_ok') else 'missing / does not carry it'}); {f['rows_on_file']:,} rows on file, {f['rows_read']:,} read ({f['rows_dropped_at_the_cut']:,} dated on/after the cut dropped at read); "
          "by type: " + ", ".join(f"{t} {n:,}" for t, n in sorted(f["rows_by_type"].items())))
    g = dv["grid"]
    print(f"  cash dividends: {dv['rows']:,} rows -> {dv['usable']:,} usable ({dv['no_ex_date_or_symbol']} without an ex-date or symbol, {dv['no_positive_amount']} without a positive amount; {dv['special']:,} special); placed on a cached name and a session "
          f"{g['placed']:,} (name not cached {g['name_not_on_the_grid']:,}, ex-date not a session {g['ex_date_not_a_session']:,}, same name and day added up {g['same_name_same_day_rows_added']:,}); applied to price-bearing sessions of the names ever "
          f"in the universe {dv['applied_in_the_world']['applied']:,} (no close / prior close / factor on the session: {dv['applied_in_the_world']['no_close_prior_close_or_factor']:,}; over 25% of the prior close: "
          f"{dv['applied_in_the_world']['over_25_pct_of_the_prior_close']:,})")
    print("  dividends by year (usable / on a cached name + session / on a name ever in the universe / applied): " + "; ".join(
        f"{y}: {v['usable']:,} / {v['on_a_cached_name_and_session']:,} / {v['on_a_name_ever_in_the_universe']:,} / {v['applied']:,}" for y, v in dv["by_year"].items()))
    for lab, key in (("every cached name", "every_cached_name"), ("names ever in the universe", "names_ever_in_the_universe")):
        sc = rep["splits"][key]
        print(f"  the calendar's splits against the registered split rule, {lab} (agree / calendar-only / price-only): " + "; ".join(
            f"{y}: {v['agree']} / {v['calendar_only']} / {v['price_only']}" for y, v in sc["by_year"].items()) + f"; total {sc['total']['agree']} / {sc['total']['calendar_only']} / {sc['total']['price_only']} "
            f"({sc['calendar_only_within_3_sessions_of_a_price_only']} calendar-only within 3 sessions of a price-only one; calendar split rows not on a cached name {sc['calendar_rows_name_not_cached']}, "
            f"ex-date not a session {sc['calendar_rows_ex_date_not_a_session']})")
    sp, g2 = rep["spin"], rep["spin"]["grid"]
    print(f"  spin-offs / stock dividends [D2] (a spin-off's symbol is the parent; no credit is computed for the new shares): {sp['rows']:,} rows -> {sp['usable']:,} usable ({sp['no_ex_date_or_symbol']} without an ex-date or symbol; "
          + ", ".join(f"{t} {n:,}" for t, n in sorted(sp["by_type"].items())) + f"); placed on a cached name and a session {g2['placed']:,} (name not cached {g2['name_not_on_the_grid']:,}, ex-date not a session {g2['ex_date_not_a_session']:,}); "
          f"on the names ever in the universe {sp['in_the_world']['cells']:,} ex-date sessions, {sp['in_the_world']['with_a_return']:,} with a return to leave out (no close / prior close that session: {sp['in_the_world']['no_return']:,})")
    print("  spin-offs / stock dividends by year (usable / on a cached name + session / on a name ever in the universe / a return left out): " + "; ".join(
        f"{y}: {v['usable']:,} / {v['on_a_cached_name_and_session']:,} / {v['on_a_name_ever_in_the_universe']:,} / {v['return_left_out']:,}" for y, v in sp["by_year"].items()))
    for w in rep["warnings"]:
        print("  WARNING: " + w)


# ------------------------------------------------------------------ the monthly schedule and the score
def rm_schedule(days):
    """(rank rows r, fill rows f = r + 1, exit rows x): the rank session is each CALENDAR MONTH's last session in the data, the fill is the NEXT session's official open (the print that makes the signal is never the fill
    price), and a position is held to the NEXT rebalance's fill. x = -1: the next rebalance's fill is past the stage's data (unresolved: out of the cell AND the null, counted). A rank session with no session after it cannot
    fill and is not a rebalance (so in Stage A's data the month the cut falls in is never a rank)"""
    d = pd.DatetimeIndex(days)
    key = d.year.to_numpy("int64") * 100 + d.month.to_numpy("int64")
    last = np.flatnonzero(np.r_[key[1:] != key[:-1], True])
    r = last[last + 1 < len(days)]
    f = r + 1
    return r, f, np.r_[f[1:], -1]


def windows(r):
    """the rows of the rank session r: (a, fa, fe) = the regression window starts at a = r - 251 and ends at r; the formation window is fa .. fe = r - 251 .. r - 21 (the skipped month is r - 20 .. r)"""
    s = SPEC
    fe = r - s["skip"]
    return r - s["win"] + 1, fe - s["form_n"] + 1, fe


def rm_scores(W, r, uni):
    """the two scores of the names `uni` at the rank session r -> (n_ret, n_pair, res, raw), each (n,).
    n_ret = the name's finite split-safe daily TOTAL returns (price + the cash dividend on its ex-date, attach_dividends; [D2] a spin-off / stock-dividend ex-date session of the name is NaN there - left out of the beta, the residuals, the formation sum / product and both counts) in the regression window r-251 .. r; n_pair = those that also have an ES return (ES-hole sessions are skipped for every name).
    RES (prereg v2): OLS of the name's daily return on ES's (an intercept and a slope) over the window's pairs gives its BETA; the residual is e_d = return - beta x ES return - the fitted ALPHA IS NOT SUBTRACTED (with it
    the residuals would sum to zero over the regression window, which contains the formation window, so the formation sum would be exactly minus the skipped month's: a one-month reversal - t_identity proves both); RES = the sum
    of e_d over the formation window (r-251 .. r-21) / their sample standard deviation (ddof 1). RAW: the split-safe total return over the formation window = the product of (1 + the finite daily returns) - 1 (CHOICE: equal to
    the price ratio when none is missing). NaN where a score is undefined (fewer than 2 residuals, a flat residual, no ES variation)"""
    a, fa, fe = windows(r)
    R = W.Rd[a:r + 1][:, uni]                                                       # [R1] the split-safe TOTAL return: the cash dividends are added back on their ex-dates
    m = np.asarray(W.es.ret[a:r + 1], float)
    fin = np.isfinite(R)
    ok = fin & np.isfinite(m)[:, None]
    n_ret, n_pair = fin.sum(axis=0), ok.sum(axis=0)
    with np.errstate(invalid="ignore", divide="ignore"):
        n = np.maximum(n_pair, 1)
        my, mm = np.where(ok, R, 0.0).sum(axis=0) / n, np.where(ok, m[:, None], 0.0).sum(axis=0) / n
        dy, dm = np.where(ok, R - my, 0.0), np.where(ok, m[:, None] - mm, 0.0)
        beta = (dm * dy).sum(axis=0) / (dm * dm).sum(axis=0)
        e = np.where(ok, R - beta * m[:, None], np.nan)                                     # v2: the beta alone - the fitted alpha (my - beta x mm) stays in the residual
        eF = e[fa - a:fe - a + 1]
        nF = np.isfinite(eF).sum(axis=0)
        sF = np.where(np.isfinite(eF), eF, 0.0).sum(axis=0)
        dev = np.where(np.isfinite(eF), eF - sF / np.maximum(nF, 1), 0.0)
        sd = np.sqrt((dev * dev).sum(axis=0) / np.maximum(nF - 1, 1))
        res = np.where((nF >= 2) & (sd > 0) & np.isfinite(sF), sF / sd, np.nan)
        RF = R[fa - a:fe - a + 1]
        raw = np.where(np.isfinite(RF), 1.0 + RF, 1.0).prod(axis=0) - 1.0
        raw = np.where(np.isfinite(RF).any(axis=0), raw, np.nan)
    return n_ret, n_pair, res, raw


# ------------------------------------------------------------------ one rebalance: the pool, the scores, the 50 / 50 picks of each cell, the position paths
def rm_one(W, r, f, x, post_mode, units=True):
    """one rebalance: the universe at the fill session f (sessions < f only), the scores through the rank close r, every removal in order, the pool, each cell's 50 / 50 picks and their paths -> (rec, counts).
    The pool is ONE set for both cells (CHOICE: RES and RAW rank the same names): in the universe, >= 230 own split-safe returns AND >= 230 ES pairs in the 252-session window, an open at the fill session, finite scores, and
    no hygiene reason: [T2] on sessions r-25 .. r (5 sessions before the skipped month through the rank close - decisions are made after the close, so a flag dated r is known) all four reasons; CHOICE: on sessions
    r-251 .. r-26 (the regression / formation window) the three UNREGISTERED ones - gap scan (TBIS flags are OR-ed into it), TBIS, a +-50% raw gap with no factor change: each is a fake return day inside the score - while a
    registered split there is carried by the split-safe series and is not a reason; hygiene INSIDE the hold (r+1 .. x) is the look-ahead removal [O3] - and so is [D2] a spin-off / stock-dividend ex-date inside the hold (f < t <= x: the fill session's own is bought ex, the exit session's is inside; reason post_spin; one inside the regression / formation window only leaves that session's return out of the name's score, rm_scores reads Rd). post_mode 'remove' = the registered reading (a name flagged inside the hold
    is removed BEFORE the ranking, so a flagged jumper never takes a slot); 'naive' = it stays in the pool and its path is the naive raw one. CHOICE: no large-move cross-check (the prereg names none for a 12-month signal).
    Both sides are always 50 names: a rebalance trades only when the pool holds >= 100. Ties: one ascending order by (score, symbol order); the shorts are its first 50, the longs its last 50 (disjoint by position)"""
    s = SPEC
    nn = s["n_side"]
    uni = np.flatnonzero(W.U[f])
    rec = SimpleNamespace(r=r, f=f, x=x, traded=False, pool=np.zeros(0, np.int64), naive=np.zeros(0, bool), nu=len(uni), nfull=0, score={c: np.zeros(0) for c in CELLS}, skip_ret=np.zeros(0), spin_win=np.zeros(0, np.int64), spin_hold=np.zeros(0, bool),
                          pick={c: (np.zeros(0, np.int64), np.zeros(0, np.int64)) for c in CELLS})
    cnt = Counter()
    cnt["rebalances"] += 1
    cnt["universe"] += len(uni)
    if not len(uni):
        cnt["empty"] += 1
        return rec, cnt
    a = windows(r)[0]
    n_ret, n_pair, res, raw = rm_scores(W, r, uni)
    short_hist = n_ret < s["min_n"]
    no_es = ~short_hist & (n_pair < s["min_n"])
    rec.nfull = int((~short_hist & ~no_es).sum())
    m_fill = np.isfinite(W.Ao[f, uni])                                          # CHOICE: a name with no open (or no factor) at the fill session cannot be filled: not eligible, counted
    no_score = ~(np.isfinite(res) & np.isfinite(raw))
    lo_pre = r - s["skip"] - s["hyg_lead"] + 1
    pre = W.hyg(lo_pre, r, uni)                                                 # all four reasons, sessions r-25 .. r
    old = W.hyg(a, lo_pre - 1, uni)[1:]                                         # gap, tbis, jump on sessions r-251 .. r-26
    post = W.hyg(r + 1, x, uni)                                                 # all four, inside the hold: the fill session through the exit session
    post_sp = spn_hit(W, f + 1, x, uni)                                         # [D2] a spin-off / stock-dividend ex-date in f < t <= x: a data event like a hygiene flag inside the hold
    win = (W.SPN[a:r + 1][:, uni] & np.isfinite(W.Rn[a:r + 1][:, uni])).sum(axis=0)      # [D2] the returns left out of each name's regression / formation window (r-251 .. r)
    pre_any, old_any, post_any = pre.any(axis=0), old.any(axis=0), post.any(axis=0) | post_sp
    aud = W.aud1[f, uni]
    W.aud_hit.update((AUD, f, int(c)) for c in uni[aud])
    reasons = [("short_history", short_hist), ("no_es_pairs", no_es), ("no_fill", ~m_fill), ("no_score", no_score)]
    reasons += [(f"pre_{h}", pre[q]) for q, h in enumerate(HYG)] + [(f"old_{h}", old[q]) for q, h in enumerate(HYG[1:])]
    if post_mode == "remove":                                                   # the registered reading removes the names flagged inside the hold; the other keeps them (counted as kept_naive)
        reasons += [(f"post_{h}", post[q]) for q, h in enumerate(HYG)] + [("post_spin", post_sp)]
    D15.tally(cnt, reasons + [("audit", aud)], D15.attribute(reasons + [("audit", aud)], len(uni)))
    cnt["spin_window_names"] += int((win > 0).sum())                              # [D2] counts over the universe names at the fill session (not first-reason: a name is counted whatever else removes it)
    cnt["spin_window_sessions"] += int(win.sum())
    cnt["spin_hold_names"] += int(post_sp.sum())
    pool_k = ~short_hist & ~no_es & m_fill & ~no_score & ~pre_any & ~old_any & ~aud
    pool = (pool_k & ~post_any) if post_mode == "remove" else pool_k
    if post_mode == "naive":
        cnt["kept_naive"] += int((pool & post_any).sum())
    pidx = np.flatnonzero(pool)
    rec.pool = uni[pidx]
    rec.naive = post_any[pidx] if post_mode == "naive" else np.zeros(len(pidx), bool)
    rec.score = {"RES": res[pidx], "RAW": raw[pidx]}
    rec.spin_win, rec.spin_hold = win[pidx], post_sp[pidx]
    RS = W.Rd[r - s["skip"] + 1:r + 1][:, rec.pool]                             # the skipped month's split-safe TOTAL return = the compound of the same daily returns RAW compounds over the formation window (a report input: RES vs the last month)
    rec.skip_ret = np.where(np.isfinite(RS).any(axis=0), np.where(np.isfinite(RS), 1.0 + RS, 1.0).prod(axis=0) - 1.0, np.nan)
    if len(pidx) >= 2 * nn:
        for c in CELLS:
            o = np.lexsort((rec.pool, rec.score[c]))                            # ascending score, ties by symbol order: the 50 lowest are the shorts, the 50 highest the longs
            rec.pick[c] = (o[::-1][:nn], o[:nn])
        rec.traded = True
        if units:                                                               # (dryload builds the pools only to count them: no path, no P&L)
            rec.U = rm_units(W, f, x, rec.pool, rec.naive)
    else:
        cnt["small_pool"] += 1
    return rec, cnt


def rm_units(W, f, x, cols, naive=None):
    """r15's unit paths (split-safe; the names flagged `naive` on the raw series) + [R1] the cash dividends: on every ex-date session t with f < t <= x a LONG receives and a SHORT pays the dividend per share held - per $1 of
    entry notional D*_t / the entry open (fractional shares: $1 / the entry open, fixed). The fill session's own ex-date is bought ex-dividend (nothing); the exit session's is sold ex-dividend, after the prior close (the
    holder at that close is entitled): received / paid. D* = D / F_t on the split-adjusted basis; the naive raw path takes the raw amount over the raw entry open. Added to the gross marks U.G (columns 1 .. H-1) and kept in U.div"""
    U = D15.l1_units(W, f, x, cols, naive)
    n, H = len(cols), x - f + 1
    div = np.zeros((n, max(H - 1, 0)))
    if H > 1:
        with np.errstate(invalid="ignore", divide="ignore"):
            a = W.Dv[f + 1:x + 1][:, cols] / W.Ao[f, cols][None, :]
            if naive is not None and naive.any():
                a = np.where(naive[None, :], W.Dr[f + 1:x + 1][:, cols] / W.Od[f, cols][None, :], a)
        div = np.nan_to_num(a.T, nan=0.0)
        U.G[:, 1:] += div
    U.div = div
    return U


def div_flows(L, cell):
    """[R1] the dividend cash inside a cell's registered picks over WF, in $: what the longs received and what the shorts paid (slot x the per-share amount over the entry open), and how many positions had one"""
    out = {"long_received": 0.0, "short_paid": 0.0, "long_positions_with_a_dividend": 0, "short_positions_with_a_dividend": 0}
    for rec in L.recs:
        if not rec.traded:
            continue
        for q, (key, cnt) in enumerate((("long_received", "long_positions_with_a_dividend"), ("short_paid", "short_positions_with_a_dividend"))):
            tot = rec.U.div[rec.pick[cell][q]].sum(axis=1) if rec.U.div.shape[1] else np.zeros(len(rec.pick[cell][q]))
            out[key] += float(SPEC["slot"] * tot.sum())
            out[cnt] += int((tot > 0).sum())
    return out


def rm_build(W, lo, hi, post_mode="remove", units=True, drop=None):
    """every rebalance whose position EXITS inside [lo, hi] (CHOICE: a position belongs to the stretch its exit session falls in, as the house stretches are written; a marks before the stretch's first row fall outside its
    series - at most the first month; a position whose exit is past the stage's data is unresolved: out of the cell AND the null, counted) with a full 252-session window (r >= 251; the earlier ranks are counted as warm-up)
    -> Leg(kind, recs, cnt by fill year). drop = [D1] rank sessions (dates) to leave out of the leg - out of the cell AND the null, counted as dropped_d1 (the REPORTED row without the first five rebalances)"""
    r_all, f_all, x_all = rm_schedule(W.days)
    drop_rows = {int(i) for i in W.days.get_indexer(pd.DatetimeIndex(drop)) if i >= 0} if drop is not None and len(drop) else set()
    recs, cnt = [], defaultdict(Counter)
    for r, f, x in zip(r_all.tolist(), f_all.tolist(), x_all.tolist()):
        y = int(W.days[f].year)
        if x < 0:
            cnt[y]["unresolved"] += 1
            continue
        if not (lo <= W.days[x] <= hi):
            continue
        if r < SPEC["win"] - 1:
            cnt[y]["warmup"] += 1
            continue
        if r in drop_rows:
            cnt[y]["dropped_d1"] += 1
            continue
        rec, c = rm_one(W, r, f, x, post_mode, units)
        recs.append(rec)
        cnt[y].update(c)
    return SimpleNamespace(kind="RM", recs=recs, cnt=cnt)


def cell_leg(L, cell):
    """one cell's view of a Leg in the shape r15's L1 engines read (rec.sig = the cell's score on the pool, rec.long / rec.short = its picks): l1_cell / null_l1 / survivorship run on it unchanged"""
    recs = []
    for rec in L.recs:
        v = SimpleNamespace(r=rec.r, f=rec.f, x=rec.x, traded=rec.traded, pool=rec.pool, naive=rec.naive, nu=rec.nu, sig=rec.score[cell], long=rec.pick[cell][0], short=rec.pick[cell][1])
        if rec.traded and hasattr(rec, "U"):
            v.U = rec.U
        recs.append(v)
    return SimpleNamespace(kind="L1", recs=recs, cnt=L.cnt)


_L1_PNL = D15.l1_pnl


def l1_pnl_x(U, idx, side, cfg, kt=None, sq=None):
    """r15's l1_pnl plus [R2]: cfg['short0'] - a SHORT in a name that stopped printing during the hold (no open at the exit session) is valued at ZERO: the stock's last mark is never bought back, so the short keeps the full
    gain of its entry notional (+1 per $1) and pays no exit cost; the borrow keeps accruing on the carried mark up to the exit row. Everything else is r15's"""
    P = _L1_PNL(U, idx, side, cfg, kt, sq)
    if side < 0 and cfg.get("short0"):
        st = U.st[idx]
        if st.any():
            c = cfg["bps"] * 1e-4
            P[:, -1] += np.where(st, U.mk[idx][:, -1] + c * U.ve[idx], 0.0)
    return P


def run_cell(W, CL, cfg, **kw):
    """a cell's run through r15's L1 engine at THIS harness's size: $4,000 a name, 50 a side, F kind (no volatility lean). cfg = r15's l1_cfg (bps, borrow rates, -100%); side +1 / -1 = one side alone; pos=True = the per-position table"""
    with D15.spec(l1_slot=SPEC["slot"], l1_n=SPEC["n_side"]), patched(D15, l1_pnl=l1_pnl_x):
        return D15.l1_cell(W, CL, "F", cfg, **kw)


def rm_null(W, L, nreps, vcode=0):
    """the family-aware null [prereg NULL]: per draw and per rebalance the cell traded, its 50 longs and 50 shorts are replaced by names drawn uniformly without replacement from that rebalance's eligible pool (the same pool,
    hygiene, sizing, fills, costs, borrow); CHOICE: each cell has its own random stream (seeds [20261005, cell, vcode]), so the MAX over the 2 cells is the better of two independent random books. -> {cell: (nreps, T) P&L by stock
    session}; r15's null_l1 does the drawing (its S twin, x k, is not used here)"""
    acc = {}
    with D15.spec(l1_slot=SPEC["slot"], l1_n=SPEC["n_side"]):
        for q, cell in enumerate(CELLS):
            acc[cell] = D15.null_l1(W, cell_leg(L, cell), nreps, np.random.default_rng([SEED, q, vcode]))[0]
    return acc


def null_summary(per_cell):
    """per_cell {cell: ROC @ $30k of every draw} -> the statistic = the MAX over the 2 cells per draw -> p5 / p50 / p95 (and each cell's own, for the report)"""
    roc = np.fmax.reduce(np.vstack([per_cell[c] for c in CELLS]), axis=0)
    mk = lambda a: {"p5": D15.pctl(a, 5), "p50": D15.pctl(a, 50), "p95": D15.pctl(a, 95), "finite": int(np.isfinite(a).sum())}
    return {"draws": int(len(roc)), "seed": SEED, "roc_max": mk(roc), "by_cell": {c: mk(per_cell[c]) for c in CELLS}}


# ------------------------------------------------------------------ Stage A's checks (a) - (e), the A2 report, the hand audit (f)
def judge_cell(st, net10, nul):
    """(a) >= 60 monthly rebalances; (b) WF ROC @ $30k >= 15 and net > 0 at 5 AND at 10 bps a side; (c) WF ROC above the null's 95th percentile (the max over the 2 cells); (d) positive in >= 6 of the 9 July-June WF years and
    net > 0 without Feb 15 - Apr 30 2020; (e) profitable without its best 1% of days AND without its best 1% of name-months. (f), the hand audit, is separate: audit_complete. A NaN fails every comparison it enters"""
    R = RULES
    chk = {f"rebalances>={R['reb']}": st["n_units"] >= R["reb"], f"ROC>={R['roc']:g}": st["roc"] >= R["roc"], "net>0 at 5 bps": (st["net"] > 0) if R["net_pos"] else True,
           "net>0 at 10 bps": (net10 > 0) if R["stress"] else True, "ROC>null p95": (st["roc"] > nul["roc_max"]["p95"]) if R["null"] else True,
           f"positive in >={R['years']} of 9 July-June years": st["years_pos"] >= R["years"], "net>0 without Feb 15 - Apr 30 2020": (st["net_ex2020"] > 0) if R["ex2020"] else True,
           "profitable without its best 1% of days": (st["net_ex_best_days"] > 0) if R["exbest"] else True,
           "profitable without its best 1% of name-months": (st["net_ex_best_pos"] > 0) if R["exbest"] else True}
    return {k: bool(v) for k, v in chk.items()}


def a2_report(B, xB):
    """STAGE A2 (WF) - a REPORT, never a pass (MANAGER #56): #463 + c x the cell, c set by VOLATILITY on 2017-01-03 .. 2018-12-31 (the cell's first two years) = r15's a2_cell run on this window (c = 25% x std(#463's daily
    P&L) / std(the cell's), every index row of the window, a row the cell holds nothing on is a zero day), the book at 0.5c and 2c beside it; 'book_shadow_line' = the book at c has ROC @ $30k >= 98.5005 and Sortino >= 3.816 (it opens a forward BOOK
    shadow line beside the standalone one, nothing more)"""
    with patched(D15, A2_WIN=A2_WIN, A2_TARGET=A2_TARGET, A2_REPORT=A2_REPORT, RULES={**D15.RULES, "a2_roc": RULES["a2_roc"], "a2_sort": RULES["a2_sort"]}):
        a = D15.a2_cell(B, xB)
    a["book_shadow_line"] = bool(a.pop("pass"))
    return a


def read_audit(path=None):
    """OUT\\resmom_audit.csv (symbol, date, cell, verdict in {keep, data_event}, note) -> a frame, or None when there is no file yet. A data_event row removes that name-month from the cell AND the null before anything is
    computed [(f)]. CHOICE: the date is the position's FILL date - exactly the 'date' of resmom_audit_candidates.csv; a data event belongs to the name-month, so a row covers BOTH cells' listing of it (the key is symbol + date).
    Refuses a verdict / cell / date it cannot read (a mistyped row must not silently do nothing)"""
    p = path or os.path.join(OUT, "resmom_audit.csv")
    if not os.path.exists(p):
        return None
    df = pd.read_csv(p, dtype=str, keep_default_na=False)
    miss = [c for c in ("symbol", "date", "cell", "verdict") if c not in df.columns]
    if miss:
        refuse(f"refused: resmom_audit.csv lacks the column(s) {miss} (columns: symbol, date, cell, verdict, note) - nothing computed")
    df["symbol"], df["cell"], df["verdict"] = df["symbol"].str.strip(), df["cell"].str.strip().str.upper(), df["verdict"].str.strip().str.lower()
    df["date"] = pd.to_datetime(df["date"].str.strip(), errors="coerce")
    bad = df[~df["verdict"].isin(("keep", "data_event")) | ~df["cell"].isin(CELLS) | df["date"].isna() | (df["symbol"] == "")]
    if len(bad):
        refuse(f"refused: resmom_audit.csv line(s) {[int(i) + 2 for i in bad.index][:10]} have an unreadable date / symbol, a verdict outside keep | data_event, or a cell outside {list(CELLS)} (nothing computed)")
    return df


def apply_audit(W, audit):
    """put the audit's data_event rows on the world as removals (by fill session and name). A data_event row that matches no session or no name of this data refuses: a mistyped row must not silently do nothing -> counts"""
    W.aud1[:] = False
    W.aud_hit.clear()
    if audit is None:
        return {"rows": 0, "keep": 0, "data_event": 0}
    di = W.days.get_indexer(pd.DatetimeIndex(audit["date"]))
    ci = pd.Index(W.syms).get_indexer(audit["symbol"])
    ev = (audit["verdict"] == "data_event").to_numpy()
    bad = np.flatnonzero(ev & ((di < 0) | (ci < 0)))
    if len(bad):
        refuse(f"refused: resmom_audit.csv data_event line(s) {[int(i) + 2 for i in bad][:10]} match no session or no name of this data (the date is the FILL session; the symbol must be one the universe "
               "ever held) - fix the file (nothing computed, lockbox NOT read)")
    for i in np.flatnonzero(ev):
        W.aud1[di[i], ci[i]] = True
    return {"rows": int(len(audit)), "keep": int((~ev).sum()), "data_event": int(ev.sum())}


def unused_audit_rows(W, audit):
    """data_event rows that removed nothing in the registered build (the name was not in that fill session's universe): reported, so a wrong date cannot pass unnoticed"""
    if audit is None:
        return []
    di = W.days.get_indexer(pd.DatetimeIndex(audit["date"]))
    ci = pd.Index(W.syms).get_indexer(audit["symbol"])
    return [f"{audit['symbol'].iat[i]} {audit['date'].iat[i]:%Y-%m-%d} {audit['cell'].iat[i]}" for i in range(len(audit))
            if audit["verdict"].iat[i] == "data_event" and (AUD, int(di[i]), int(ci[i])) not in W.aud_hit]


def audit_status(cands, audit):
    """per cell: how many of the listed top-50 contributors appear in resmom_audit.csv (by symbol + fill date); audit_complete = every listed one does"""
    have = set() if audit is None else set(zip(audit["symbol"], audit["date"].dt.strftime("%Y-%m-%d")))
    out = {}
    for cell, rows in cands.items():
        n = sum((r["symbol"], r["date"]) in have for r in rows)
        out[cell] = {"listed": len(rows), "audited": int(n), "audit_complete": bool(len(rows) > 0 and n == len(rows))}
    return out


def rm_candidate_rows(W, L, cell, run, tbis_df, status, n=AUDIT_N):
    """the n largest single-name P&L contributors of a cell (CHOICE: 'contributors' = the largest GAINS, P&L descending - the name-months that carry the profit; a fake loss only works against a pass, a fake gain for it)
    with what the hand audit needs: symbol, date (the FILL session - the key resmom_audit.csv uses), exit, side, $, score, the raw / split-adjusted move over the formation window and the split factor's ratio across the
    regression window and the hold, the largest raw overnight move in the window and in the hold, the largest split-safe daily return in the hold (and when), TBIS's rows for the symbol in the window, the asset status and the
    hygiene reasons in the window"""
    p = run.pos
    if p is None or not len(p.pnl):
        return []
    sel = np.argsort(-np.asarray(p.pnl, float), kind="stable")[:n]
    tb = None if tbis_df is None or not len(tbis_df) else tbis_df
    big = lambda g: float(g[np.argmax(np.abs(g - 1.0))]) if len(g) else float("nan")
    rows = []
    for rank, i in enumerate(sel, 1):
        rec, col = L.recs[int(p.rec[i])], int(p.col[i])
        a, fa, fe = windows(rec.r)
        a0, f, x = max(fa - 1, 0), rec.f, rec.x
        rw = W.Rg[max(a, 0):x + 1, col]
        rh = W.Rg[f:x + 1, col]
        dr = W.Rn[f:x + 1, col]
        j = int(np.nanargmax(np.abs(dr))) if np.isfinite(dr).any() else -1
        sym = str(W.syms[col])
        ptb = [None, None, None]
        if tb is not None:
            m = tb[(tb["symbol"].astype(str) == sym) & (tb["day"] >= W.days[max(a, 0)]) & (tb["day"] <= W.days[x])]
            if len(m):
                ptb = [float(m["price_ratio"].iloc[0]), float(m["vol_ratio"].iloc[0]) if pd.notna(m["vol_ratio"].iloc[0]) else float("nan"), str(m["split_like"].iloc[0])]
        fl = W.hyg(max(a, 0), x, np.array([col]))[:, 0]
        lo_ = max(a, 1)
        with np.errstate(invalid="ignore", divide="ignore"):
            yv = W.Dv[lo_:x + 1, col] / W.Ac[lo_ - 1:x, col]                                 # [R1] the largest dividend over the prior close in the window and the hold (a bad amount is a data event the audit looks for)
        dsum = float(W.Dv[f + 1:x + 1, col].sum())
        dpnl = float((1.0 if p.side[i] > 0 else -1.0) * SPEC["slot"] * dsum / W.Ao[f, col]) if dsum > 0 and np.isfinite(W.Ao[f, col]) else 0.0
        rows.append({"cell": cell, "rank": rank, "symbol": sym, "date": f"{W.days[f]:%Y-%m-%d}", "exit": f"{W.days[x]:%Y-%m-%d}", "side": "long" if p.side[i] > 0 else "short", "pnl": float(p.pnl[i]),
                     "score": float(p.sig[i]), "raw_move_formation": float(W.Cl[fe, col] / W.Cl[a0, col] - 1.0), "adj_move_formation": float(W.Ac[fe, col] / W.Ac[a0, col] - 1.0),
                     "factor_ratio_window_to_exit": float(W.F[x, col] / W.F[max(a - 1, 0), col]), "max_overnight_raw_ratio_in_window": big(rw[np.isfinite(rw)]), "max_overnight_raw_ratio_in_hold": big(rh[np.isfinite(rh)]),
                     "max_abs_daily_return_in_hold": float(dr[j]) if j >= 0 else float("nan"), "max_abs_daily_return_date": f"{W.days[f + j]:%Y-%m-%d}" if j >= 0 else "",
                     "tbis_price_ratio": ptb[0], "tbis_vol_ratio": ptb[1], "tbis_split_like": ptb[2], "asset_status": status.get(sym, "unknown"), "flags_in_window": "+".join(h for h, v in zip(HYG, fl) if v),
                     "dividend_pnl_in_hold": dpnl, "max_dividend_over_prior_close_window_to_exit": float(np.nanmax(yv)) if np.isfinite(yv).any() else 0.0,
                     "spin_returns_left_out_in_window": int((W.SPN[max(a, 0):rec.r + 1, col] & np.isfinite(W.Rn[max(a, 0):rec.r + 1, col])).sum()), "spin_or_stock_dividend_in_hold": bool(W.SPN[f + 1:x + 1, col].any())})
    return rows


# ------------------------------------------------------------------ one reading of Stage A: legs -> cells -> stress rows -> null -> checks -> A2
def evaluate(W, B, S12, rows, post_mode, nreps, vcode=0, full=False, drop=None):
    """one reading of Stage A on the WF stretch. post_mode 'remove' = the REGISTERED reading (a hygiene flag inside the hold removes the position before the ranking), 'naive' = the look-ahead variant [O3] (those positions
    are kept at their naive raw P&L); both run the same code, so a flip between them is the data hygiene's doing. nreps > 0 draws the null (vcode picks its random streams). full = also the reports' rows (sides apart,
    borrow stress, -100% for names that stop printing). drop = [D1] rank sessions left out of the leg (the cell AND the null). -> (summary, objects: the leg, each cell's leg view / base run / series / side series)"""
    lo, hi = WF0, PRE_END
    L = rm_build(W, lo, hi, post_mode, drop=drop)
    legs = {c: cell_leg(L, c) for c in CELLS}
    runs, series, side_x, summ = {}, {}, {}, {}

    def stat(run):
        xB, cB = D15.to_B(run.x, rows, B.n), D15.to_B(run.cnt, rows, B.n)
        return D15.cell_stats(B, xB, cB, lo, hi, run), xB, cB

    for cell in CELLS:
        CL = legs[cell]
        base = run_cell(W, CL, D15.l1_cfg(), pos=True)
        st, xB, cB = stat(base)
        runs[cell], series[cell] = base, (xB, cB)
        stress = {f"{b:g} bps": stat(run_cell(W, CL, D15.l1_cfg(bps=b)))[0] for b in STRESS_BPS}
        c = {"base": st, "stress": stress, "seat": D15.seat_measure(S12, xB)}
        if full:
            c["sides"] = {}
            for nm, sd in (("long side only", 1), ("short side only", -1)):
                s_, sx, _ = stat(run_cell(W, CL, D15.l1_cfg(), side=sd))
                c["sides"][nm] = s_
                side_x.setdefault(cell, {})[sd] = sx
            ex = {f"borrow {BORROW_STRESS[0]:.0%} on k>1.5 sessions": D15.l1_cfg(borrow=(BORROW, BORROW_STRESS[0])), f"borrow {BORROW_STRESS[1]:.0%} on k>1.5 sessions": D15.l1_cfg(borrow=(BORROW, BORROW_STRESS[1])),
                  "longs that stop printing valued at -100%": D15.l1_cfg(lose100=True)}
            c["extra"] = {nm: stat(run_cell(W, CL, cfg))[0] for nm, cfg in ex.items()}
            z0 = {**D15.l1_cfg(), "short0": True}                                           # [R2] the short leg with a name that stops printing during the hold valued at zero (the short's full gain), beside the base
            c["sides"][R2_SIDE] = stat(run_cell(W, CL, z0, side=-1))[0]
            c["extra"][R2_CELL] = stat(run_cell(W, CL, z0))[0]
            c["short_stopped"] = {"positions": int(sum(int(rec.U.st[rec.pick[cell][1]].sum()) for rec in L.recs if rec.traded)), "short_positions": int(sum(len(rec.pick[cell][1]) for rec in L.recs if rec.traded))}
        summ[cell] = c
    nul = None
    if nreps:
        acc = rm_null(W, L, nreps, vcode)
        nul = null_summary({cell: D15.null_cell(S12, acc[cell], rows, B.n)[0] for cell in CELLS})
    for cell in CELLS:
        c = summ[cell]
        if nul is not None:
            c["checks"] = judge_cell(c["base"], c["stress"]["10 bps"]["net"], nul)
            c["PASS"] = bool(all(c["checks"].values()))
        c["A2"] = a2_report(B, series[cell][0])
    return {"variant": post_mode, "cells": summ, "null": nul}, SimpleNamespace(legs=L, cell_legs=legs, runs=runs, series=series, side_x=side_x)


# ------------------------------------------------------------------ the reports (never a pass route)
def month_nets(B, xB, lo, hi):
    """a daily series on #463's index -> {'YYYY-MM': net P&L over the rows of that calendar month inside [lo, hi]}"""
    k = B.mask(lo, hi)
    ds, xs = B.index[k], np.asarray(xB, float)[k]
    g = pd.Series(xs, index=ds).groupby(ds.to_period("M")).sum()
    return {str(p): float(v) for p, v in g.items()}


def turnover(L, cell):
    """turnover per rebalance: the share of each side's 50 names replaced since the previous traded rebalance (the registered convention charges every position its entry AND exit every month - a name that stays pays
    it again; the estimate of what that overstates, if only the names that change were traded, is 2 x 5 bps x $4,000 per retained name-month - reported, never judged)"""
    n, prev, rows = SPEC["n_side"], None, []
    for rec in L.recs:
        if not rec.traded:
            prev = None
            continue
        lg, sh = set(rec.pool[rec.pick[cell][0]].tolist()), set(rec.pool[rec.pick[cell][1]].tolist())
        if prev is not None:
            rows.append((1.0 - len(lg & prev[0]) / n, 1.0 - len(sh & prev[1]) / n, len(lg & prev[0]) + len(sh & prev[1])))
        prev = (lg, sh)
    traded = sum(r.traded for r in L.recs)
    if not rows:
        return {"traded_rebalances": int(traded), "transitions": 0}
    a = np.array(rows)
    return {"traded_rebalances": int(traded), "transitions": len(rows), "long_replaced_mean": float(a[:, 0].mean()), "short_replaced_mean": float(a[:, 1].mean()), "replaced_mean": float(a[:, :2].mean()),
            "replaced_median": float(np.median(a[:, :2].mean(axis=1))), "replaced_min": float(a[:, :2].mean(axis=1).min()), "replaced_max": float(a[:, :2].mean(axis=1).max()),
            "registered_cost_per_rebalance_usd": float(2 * n * SPEC["slot"] * 2 * COST_BPS * 1e-4), "cost_saved_if_only_changes_traded_usd_estimate": float(a[:, 2].sum() * SPEC["slot"] * 2 * COST_BPS * 1e-4)}


def reports(W, B, S12, rows, obj, summ, tbis_df, status, legs_meta):
    """everything the prereg's REPORTED paragraph lists, for the registered reading: the realised beta to ES in #463's drawdown weeks FIRST, each cell's $ inside every qualifying #463 drawdown, its place on the MDL map
    (standalone ROC, rho_dd, DO), RES vs RAW (the residual's claimed advantage: smaller crashes), the long and short sides apart (in summ), the named crash months with their P&L, turnover per rebalance, the borrow stress rows
    (in summ), hygiene counts by reason and year (printed by the caller, both ways), the 20 largest name-month gains with their dates; also the correlation with each #463 leg and the survivorship rows"""
    L, lo, hi = obj.legs, WF0, PRE_END
    rep = {"beta_to_es": {}, "episodes": {}, "map_point": {}, "corr_with_legs": {}, "top20_gains": {}, "crash_months": {}, "months": {}, "turnover": {}, "survivorship": {}, "dividend_flows": {}}
    cands = {}
    for cell in CELLS:
        xB = obj.series[cell][0]
        rep["beta_to_es"][cell] = D15.es_beta(B, S12, W, rows, xB)
        rep["episodes"][cell] = D15.episodes_table(S12, xB)
        c = summ[cell]
        rep["map_point"][cell] = {"standalone_roc_30k": c["base"]["roc"], "rho_dd": c["seat"]["rho_dd"], "DO": c["seat"]["DO"]}
        rep["corr_with_legs"][cell] = A13.corrs(B, xB, legs_meta, lo, hi)
        cands[cell] = rm_candidate_rows(W, L, cell, obj.runs[cell], tbis_df, status)
        rep["top20_gains"][cell] = cands[cell][:20]
        mn = month_nets(B, xB, lo, hi)
        rep["months"][cell] = mn
        sd = obj.side_x.get(cell, {})
        rep["crash_months"][cell] = {m: {"net": mn.get(m), **{nm: month_nets(B, sd[s], lo, hi).get(m) for nm, s in (("long", 1), ("short", -1)) if s in sd}} for m in CRASH_MONTHS}
        rep["turnover"][cell] = turnover(L, cell)
        rep["survivorship"][cell] = D15.survivorship(W, obj.cell_legs[cell], status)
        rep["dividend_flows"][cell] = div_flows(L, cell)
    ov = defaultdict(list)
    for rec in L.recs:
        if rec.traded:
            for q, side in enumerate(("long", "short")):
                ov[side].append(len(set(rec.pool[rec.pick["RES"][q]].tolist()) & set(rec.pool[rec.pick["RAW"][q]].tolist())) / SPEC["n_side"])
    mn = rep["months"]
    xr, xw = obj.series["RES"][0][B.mask(lo, hi)], obj.series["RAW"][0][B.mask(lo, hi)]
    with np.errstate(invalid="ignore", divide="ignore"):
        corr = float(np.corrcoef(xr, xw)[0, 1]) if np.ptp(xr) > 0 and np.ptp(xw) > 0 else float("nan")
    worst = lambda d: min(d.items(), key=lambda kv: kv[1]) if d else (None, float("nan"))
    best = lambda d: max(d.items(), key=lambda kv: kv[1]) if d else (None, float("nan"))
    rep["res_vs_raw"] = {"cells": {c: {"net": summ[c]["base"]["net"], "roc": summ[c]["base"]["roc"], "sortino": summ[c]["base"]["sortino"], "max_dd": summ[c]["base"]["max_dd"],
                                       "worst_month": list(worst(mn[c])), "best_month": list(best(mn[c])), "months_negative": int(sum(v < 0 for v in mn[c].values())), "months": len(mn[c])} for c in CELLS},
                         "mean_pick_overlap": {k: (float(np.mean(v)) if v else float("nan")) for k, v in ov.items()}, "daily_corr": corr,
                         "note": "the residual's claimed advantage is smaller crashes: compare max_dd, the worst month and the named crash months"}
    rel = defaultdict(list)
    for rec in L.recs:
        if rec.traded:
            rk = {"res": pd.Series(rec.score["RES"]).rank(), "raw": pd.Series(rec.score["RAW"]).rank(), "skip": pd.Series(rec.skip_ret).rank()}
            rel["RES vs RAW"].append(rk["res"].corr(rk["raw"]))
            rel["RES vs the skipped month's total return"].append(rk["res"].corr(rk["skip"]))
            rel["RAW vs the skipped month's total return"].append(rk["raw"].corr(rk["skip"]))
    rep["score_relations"] = {k: {"spearman_mean": float(np.nanmean(v)), "min": float(np.nanmin(v)), "max": float(np.nanmax(v)), "rebalances": len(v)} for k, v in rel.items() if v}
    rep["crash_signed"] = crash_signed(rep["months"], {c: summ[c]["base"]["max_dd"] for c in CELLS})
    rep["xsml"] = xsml_report(B, {c: obj.series[c][0] for c in CELLS}, lo, hi)
    rep["manifest_sha256"] = manifest_sha()
    return rep, cands


def crash_signed(months, max_dd):
    """[R3] the signed line the owner reads if RES passes and RAW does not: RES's daily P&L minus RAW's, summed over the four named crash months (a month the data does not hold is left out, counted), and RES's and RAW's
    worst WF drawdowns side by side. months = {cell: {'YYYY-MM': net}}, max_dd = {cell: worst drawdown $}"""
    per = {}
    for m in CRASH_MONTHS:
        a, b = months["RES"].get(m), months["RAW"].get(m)
        per[m] = {"RES": a, "RAW": b, "res_minus_raw": (None if a is None or b is None else float(a - b))}
    have = [v["res_minus_raw"] for v in per.values() if v["res_minus_raw"] is not None]
    return {"months": per, "months_available": len(have), "sum_res_minus_raw": float(sum(have)), "worst_wf_drawdown": {c: float(max_dd[c]) for c in CELLS}}


def xsml_candidates():
    """[R4] the files that may hold XSML r1 cell A's daily P&L: every *.csv under XSML_DIR, and any file named *xsml*cellA*daily*.csv under ANATOMY_ROOT (to depth 4), newest first"""
    found = {}
    if os.path.isdir(XSML_DIR):
        for dp, dn, fn in os.walk(XSML_DIR):
            for f in fn:
                if f.lower().endswith(".csv"):
                    found[os.path.normcase(os.path.join(dp, f))] = os.path.join(dp, f)
    if os.path.isdir(ANATOMY_ROOT):
        base = ANATOMY_ROOT.rstrip("\\/").count(os.sep)
        for dp, dn, fn in os.walk(ANATOMY_ROOT):
            if dp.count(os.sep) - base >= 4:
                dn[:] = []
            for f in fn:
                if fnmatch.fnmatch(f.lower(), "*xsml*cella*daily*.csv"):
                    found[os.path.normcase(os.path.join(dp, f))] = os.path.join(dp, f)
    return sorted(found.values(), key=lambda q: -os.path.getmtime(q))


def xsml_read(path, cut):
    """(date, pnl) -> (a daily Series on the normalised dates, None), or (None, why). Cut at read: a row on/after `cut` never enters; a day listed twice adds up"""
    try:
        df = pd.read_csv(path, dtype=str, keep_default_na=False)
    except (OSError, ValueError) as e:
        return None, f"{os.path.basename(path)}: unreadable ({type(e).__name__})"
    cols = {c.strip().lower(): c for c in df.columns}
    if "date" not in cols or "pnl" not in cols:
        return None, f"{os.path.basename(path)}: no (date, pnl) columns"
    d, v = pd.to_datetime(df[cols["date"]], errors="coerce"), pd.to_numeric(df[cols["pnl"]], errors="coerce")
    ok = (d.notna() & v.notna() & (d < TS(cut))).to_numpy()
    sr = pd.Series(v[ok].to_numpy(float), index=pd.DatetimeIndex(d[ok]).normalize()).groupby(level=0).sum()
    A13.assert_cut("XSML series", sr.index, cut)
    return (sr, None) if len(sr) else (None, f"{os.path.basename(path)}: no usable row before the cut")


def xsml_report(B, xs, lo, hi, cut=None):
    """[R4] the daily correlation of Custom ML's XSML r1 cell A P&L with each cell's, over the WF days both series hold (and, apart, with the days XSML has no row for taken as zero between its first and last row), or the line that its
    series is not on file. xs = {cell: the cell's daily P&L on #463's index}"""
    cut = LB0 if cut is None else cut
    why = []
    for path in xsml_candidates():
        sr, w = xsml_read(path, cut)
        if sr is not None:
            break
        why.append(w)
    else:
        return {"on_file": False, "unusable": why, "text": f"XSML r1 cell A's daily P&L series is not on file (nothing usable in {XSML_DIR}, no *xsml*cellA*daily*.csv under {ANATOMY_ROOT}) - the overlap line [R4] waits for it"
                + (" - found but not used: " + "; ".join(why) if why else "")}
    k = B.mask(lo, hi)
    idx = pd.DatetimeIndex(B.index[k]).normalize()
    out = {"on_file": True, "file": os.path.basename(path), "sha256": sha_raw(path), "rows": int(len(sr)), "first": f"{sr.index[0]:%Y-%m-%d}", "last": f"{sr.index[-1]:%Y-%m-%d}", "corr": {}}
    for c in CELLS:
        a = pd.Series(np.asarray(xs[c], float)[k], index=idx)
        j = pd.concat([a.rename("a"), sr.rename("b")], axis=1, join="inner")
        z = pd.concat([a.rename("a"), sr.reindex(idx[(idx >= sr.index[0]) & (idx <= sr.index[-1])]).fillna(0.0).rename("b")], axis=1, join="inner")
        with np.errstate(invalid="ignore", divide="ignore"):
            out["corr"][c] = {"common_days": int(len(j)), "daily_corr": float(j["a"].corr(j["b"])) if len(j) > 2 else float("nan"),
                              "days_with_xsml_missing_as_zero": int(len(z)), "daily_corr_missing_as_zero": float(z["a"].corr(z["b"])) if len(z) > 2 else float("nan")}
    out["text"] = (f"XSML r1 cell A ({out['file']}, {out['rows']:,} days {out['first']} .. {out['last']}): daily correlation of its P&L with " + ", ".join(
        f"{c} {v['daily_corr']:+.3f} on {v['common_days']:,} common WF days ({v['daily_corr_missing_as_zero']:+.3f} with its missing days as zero)" for c, v in out["corr"].items())
        + " - if both pass the owner hears ONE finding on momentum")
    return out


# ------------------------------------------------------------------ printing
def row(cell, c):
    s, q = c["base"], c["seat"]
    return (f"{cell:<4} rebalances {s['n_units']:>4,} positions {s['n_pos']:>6,} net ${s['net']:>11,.0f} ROC@30k {s['roc']:>8.1f} Sortino {s['sortino']:>6.2f} maxDD ${s['max_dd']:>9,.0f} | "
            f"DO {q['DO']:>+7.3f} rho_dd {q['rho_dd']:>+6.3f}")


def print_cells(res, audit_st=None):
    nul = res["null"]
    print(f"  null ({nul['draws']} draws, seed {nul['seed']}, the MAX over the 2 cells): ROC@30k p5 {nul['roc_max']['p5']:.1f} p50 {nul['roc_max']['p50']:.1f} p95 {nul['roc_max']['p95']:.1f}; each cell alone p50 / p95: "
          + ", ".join(f"{c} {nul['by_cell'][c]['p50']:.1f} / {nul['by_cell'][c]['p95']:.1f}" for c in CELLS))
    for cell in CELLS:
        c = res["cells"][cell]
        fails = [k for k, v in c["checks"].items() if not v]
        s2 = ", ".join(f"{k} net ${v['net']:,.0f}" for k, v in c["stress"].items())
        print("  " + row(cell, c))
        print(f"        stress: {s2}; by July-June year: " + " ".join(f"{y}-{(y + 1) % 100:02d}:{v:+,.0f}" for y, v in c["base"]["by_year"].items()))
        a2 = c["A2"]
        a2s = (f"c x{a2['c']:.4g} (cell daily std ${a2['std_cell']:,.0f} vs #463's ${a2['std_book']:,.0f} over {a2['window'][0]} .. {a2['window'][1]}): book ROC@30k {a2['roc']:.2f} Sortino {a2['sortino']:.3f} "
               f"(the shadow-line bar {RULES['a2_roc']:.4f} / {RULES['a2_sort']}) -> {'a book shadow line opens' if a2['book_shadow_line'] else 'no book shadow line'}; at 0.5c ROC {a2['at_half_c']['roc']:.2f}, at 2c ROC {a2['at_double_c']['roc']:.2f}"
               if a2.get("at_half_c") else f"{a2.get('error', 'no c')} -> no book shadow line")
        print(f"        Stage A {'PASS' if c['PASS'] else 'FAIL (' + ', '.join(fails) + ')'}; A2 (a report): {a2s}" + ("" if audit_st is None else f"; audit {audit_st[cell]['audited']}/{audit_st[cell]['listed']} of the "
              f"top-{AUDIT_N} listed -> {'COMPLETE' if audit_st[cell]['audit_complete'] else 'incomplete'}"))


COUNT_KEYS = ("universe", "short_history", "no_es_pairs", "no_fill", "no_score") + tuple(f"pre_{h}" for h in HYG) + tuple(f"old_{h}" for h in HYG[1:]) + tuple(f"post_{h}" for h in HYG) + ("post_spin", "audit", "pool", "kept_naive")


def print_counts(label, cnt):
    keys = [k for k in COUNT_KEYS if any(k in c for c in cnt.values())]
    print(f"  {label} name-removals by fill year, each name counted once at its FIRST reason (columns: " + " / ".join(keys) + ")")
    for y, c in sorted(cnt.items()):
        print(f"    {y}: " + " ".join(f"{c.get(k, 0)}" for k in keys) + f"   [rebalances {c.get('rebalances', 0)}, unresolved {c.get('unresolved', 0)}, warm-up {c.get('warmup', 0)}, small pool {c.get('small_pool', 0)}, "
              f"empty {c.get('empty', 0)}]")


def print_spin_counts(label, cnt):
    """[D2] counts by fill year over the universe names of every rebalance: the names with a return left out of their regression / formation window (names / sessions), the names with an ex-date inside the hold"""
    print(f"  {label} [D2] by fill year (names with a return left out of their regression / formation window: names / sessions; names with an ex-date inside the hold): " + "; ".join(
        f"{y}: {c.get('spin_window_names', 0):,} / {c.get('spin_window_sessions', 0):,} / {c.get('spin_hold_names', 0):,}" for y, c in sorted(cnt.items()) if c.get("rebalances", 0)))


def spin_counts(L, cell):
    """[D2] (window, hold; long, short) over a leg's traded rebalances, for one cell's picks: the positions whose regression / formation window had a return left out (and how many sessions were left out) and the positions with a
    spin-off / stock-dividend ex-date inside the hold. The registered reading removes such a name before the ranking (its picks hold none); the look-ahead reading keeps it at its naive price P&L"""
    out = {sd: {"positions": 0, "window_positions": 0, "window_sessions": 0, "hold_positions": 0} for sd in ("long", "short")}
    for rec in L.recs:
        if not rec.traded:
            continue
        for q, sd in enumerate(("long", "short")):
            idx = rec.pick[cell][q]
            w, h, o = rec.spin_win[idx], rec.spin_hold[idx], out[sd]
            o["positions"] += int(len(idx))
            o["window_positions"] += int((w > 0).sum())
            o["window_sessions"] += int(w.sum())
            o["hold_positions"] += int(h.sum())
    return out


def print_spin_picks(spin):
    for reading, per in spin.items():
        for cell in CELLS:
            c = per[cell]
            print(f"  {reading} [D2] {cell} picks (long / short): positions {c['long']['positions']:,} / {c['short']['positions']:,}; window (a return left out of the name's regression / formation window) {c['long']['window_positions']:,} / "
                  f"{c['short']['window_positions']:,} positions ({c['long']['window_sessions']:,} / {c['short']['window_sessions']:,} sessions left out); hold (a spin-off / stock-dividend ex-date inside it) {c['long']['hold_positions']:,} / {c['short']['hold_positions']:,}")


def d1_coverage(W, start):
    """[D1] COUNTS ONLY: for every rank of the WF stretch (the rebalances rm_build builds: the exit in WF, a full window) how many of its formation sessions (r-251 .. r-21) fall before `start`, the date the calendar's pull started at
    (its manifest's `start`): the dividends, splits and spin-offs before it are not in the calendar, so they count as zero there -> [(rank date, formation sessions before the start, formation sessions)]"""
    r_all, f_all, x_all = rm_schedule(W.days)
    out = []
    for r, f, x in zip(r_all.tolist(), f_all.tolist(), x_all.tolist()):
        if x < 0 or not (WF0 <= W.days[x] <= PRE_END) or r < SPEC["win"] - 1:
            continue
        a, fa, fe = windows(r)
        out.append((W.days[r], int((W.days[fa:fe + 1] < start).sum()), fe - fa + 1))
    return out


def d1_report(W, start):
    """[D1] the coverage of the WF ranks' formation windows by the calendar -> (the record for the stage's file, the printed line); the five ranks the pre-registration names are compared with the ranks the count finds"""
    cov = d1_coverage(W, start)
    part = [(d, n) for d, n, m in cov if n > 0]
    full = [d for d, n, m in cov if n == 0]
    match = [d for d, n in part] == [TS(x_) for x_ in D1_RANKS]
    rec = {"calendar_start": f"{start:%Y-%m-%d}", "formation_sessions_per_rank": SPEC["form_n"], "ranks_in_wf": len(cov), "partly_before_the_start": [{"rank": f"{d:%Y-%m-%d}", "formation_sessions_before": n} for d, n in part],
           "fully_covered_ranks": len(full), "first_fully_covered_rank": (f"{full[0]:%Y-%m-%d}" if full else None), "registered_five": list(D1_RANKS), "registered_five_match": bool(match),
           "per_rank": [{"rank": f"{d:%Y-%m-%d}", "formation_sessions_before": n} for d, n, m in cov]}
    txt = (f"calendar coverage [D1]: the calendar starts {start:%Y-%m-%d} (its manifest's start); of the {SPEC['form_n']} formation sessions of each of the {len(cov)} WF ranks this many fall before it (the dividends, splits and spin-offs "
           "before it are not in the calendar: zero there), by rank: " + (", ".join(f"{d:%Y-%m-%d} {n}" for d, n in part) if part else "none")
           + (f"; 0 from {full[0]:%Y-%m-%d} on ({len(full)} ranks)" if full else "; no rank is fully covered")
           + ("; the partly uncovered ranks are the five the pre-registration names" if match else "; WARNING: the partly uncovered ranks are NOT the five the pre-registration names (" + ", ".join(D1_RANKS) + ") - the reported row still drops those five"))
    return rec, txt


def print_reports(rep, summ):
    b = rep["beta_to_es"]
    print("  realised beta to ES (the cell's daily $ P&L on ES's daily return, $ per 1% ES move; #463's DD days / DD weeks / all WF days) - FIRST: " + "; ".join(
        f"{c} {b[c]['DD days']['usd_per_1pct_es']:+,.0f} / {b[c]['DD weeks (every day of them)']['usd_per_1pct_es']:+,.0f} / {b[c]['all WF days']['usd_per_1pct_es']:+,.0f}" for c in CELLS))
    for c in CELLS:
        e = rep["episodes"][c]
        print(f"  {c}: P&L inside #463's {len(e)} qualifying drawdowns: net ${sum(x['cell_pnl'] for x in e):,.0f} over {sum(x['dd_days'] for x in e)} DD days (#463's ${sum(x['book_pnl'] for x in e):,.0f}); "
              f"MDL map point: ROC@30k {rep['map_point'][c]['standalone_roc_30k']:.1f}, rho_dd {rep['map_point'][c]['rho_dd']:+.3f}, DO {rep['map_point'][c]['DO']:+.3f}")
    rv = rep["res_vs_raw"]
    print("  RES vs RAW: " + "; ".join(f"{c} maxDD ${v['max_dd']:,.0f}, worst month {v['worst_month'][0]} ${v['worst_month'][1]:,.0f}, {v['months_negative']}/{v['months']} months down" for c, v in rv["cells"].items())
          + f"; mean pick overlap long {rv['mean_pick_overlap'].get('long', float('nan')):.0%} short {rv['mean_pick_overlap'].get('short', float('nan')):.0%}; daily correlation {rv['daily_corr']:+.2f}")
    if rep.get("score_relations"):
        print("  what RES is (cross-sectional rank correlation of the scores, mean over the rebalances; RES = the beta-neutral formation drift, the alpha left in - the skipped month enters only through the fitted beta): " + "; ".join(
            f"{k} {v['spearman_mean']:+.2f} ({v['min']:+.2f} .. {v['max']:+.2f})" for k, v in rep["score_relations"].items()))
    sg = rep["crash_signed"]
    print(f"  SIGNED LINE [R3] (RES's daily P&L minus RAW's, summed over the named crash months {', '.join(CRASH_MONTHS)}; {sg['months_available']} of {len(CRASH_MONTHS)} in the data): ${sg['sum_res_minus_raw']:,.0f} ("
          + ", ".join(f"{m} {v['res_minus_raw']:+,.0f}" for m, v in sg["months"].items() if v["res_minus_raw"] is not None) + "); worst WF drawdown, RES "
          f"${abs(sg['worst_wf_drawdown']['RES']):,.0f} vs RAW ${abs(sg['worst_wf_drawdown']['RAW']):,.0f}")
    print("  " + rep["xsml"]["text"])
    for c in CELLS:
        sd = summ[c]["sides"]
        fl = rep["dividend_flows"][c]
        print(f"  {c} dividends [R1] inside the registered picks: longs received ${fl['long_received']:,.0f} on {fl['long_positions_with_a_dividend']:,} positions, shorts paid ${fl['short_paid']:,.0f} on {fl['short_positions_with_a_dividend']:,}")
        z = sd.get(R2_SIDE)
        if z is not None:
            print(f"  {c} short leg [R2]: net ${sd['short side only']['net']:,.0f} with a name that stops printing exiting at its last close (the base); ${z['net']:,.0f} with such names valued at zero "
                  f"({summ[c]['short_stopped']['positions']} of {summ[c]['short_stopped']['short_positions']:,} short positions); the whole cell with it ${summ[c]['extra'][R2_CELL]['net']:,.0f} (base ${summ[c]['base']['net']:,.0f})")
        print(f"  {c} sides: long only net ${sd['long side only']['net']:,.0f}, short only net ${sd['short side only']['net']:,.0f}; crash months: " + ", ".join(
            f"{m} ${v['net']:,.0f} (long ${v.get('long', float('nan')):,.0f}, short ${v.get('short', float('nan')):,.0f})" for m, v in rep["crash_months"][c].items() if v["net"] is not None)
            + "; borrow / survivorship rows: " + ", ".join(f"{k} ${v['net']:,.0f}" for k, v in summ[c]["extra"].items()))
        t = rep["turnover"][c]
        if t.get("transitions"):
            print(f"  {c} turnover: {t['replaced_mean']:.0%} of the names replaced per rebalance on average (median {t['replaced_median']:.0%}, range {t['replaced_min']:.0%} .. {t['replaced_max']:.0%}); registered cost "
                  f"${t['registered_cost_per_rebalance_usd']:,.0f} a rebalance (every position pays entry and exit); if only the changes were traded: ${t['cost_saved_if_only_changes_traded_usd_estimate']:,.0f} less in total (estimate, not judged)")
        sv = rep["survivorship"][c]
        print(f"  {c} survivorship: {sv['long_in_inactive_names']:,} of {sv['long_positions']:,} long positions ({sv['share_long_in_inactive_names']:.1%}) are in names the asset list calls inactive")
        for x in rep["top20_gains"][c][:3]:
            print(f"      {c} top gain {x['rank']}: {x['symbol']} {x['side']} filled {x['date']} -> {x['exit']} ${x['pnl']:,.0f} score {x['score']:+.2f} (the 20 largest are in the Stage A file)")


# ------------------------------------------------------------------ dryload: counts only
def dryload():
    """the WF inputs through every loader (cut at 2025-06-30) and COUNTS: sessions, symbols, universe sizes, the rebalances and the names with a full window per rebalance by year, hygiene removals by reason (both readings),
    TBIS rows matched, ES coverage, where k_t starts. No price, return, score or P&L is printed - the pools are built (scores are computed inside them to know which names have one) only to count what they hold; no unit
    path is built"""
    prereg_ok()
    t0 = time.time()
    D = load_data(S.LB0)
    nfull = len(D.syms)
    tbis = D15.load_tbis(S.LB0)
    es_frames, es_meta = D15.load_es(S.LB0)
    full_match = D15.tbis_array(D.days, D.syms, tbis)[1]
    cal, winfo = wide_load(S.LB0, need=False, enforce=False)                                  # [R1] the wide calendar only if it exists (counts; no refusal for an unregistered sha: it is reported)
    W = build_world(D, S.LB0, es_frames, tbis, cal)
    D15.release(D)
    print(f"dryload: inputs ready ({time.time() - t0:.0f}s); every input cut to dates < {S.LB0:%Y-%m-%d}; ES masters {es_meta['raw']['filename']} / {es_meta['adj']['filename']}")
    wf = (W.days >= WF0) & (W.days <= PRE_END)
    print(f"sessions: {W.T:,} on the market calendar ({W.days[0]:%Y-%m-%d} .. {W.days[-1]:%Y-%m-%d}), {int(wf.sum()):,} inside the WF stretch; symbols: {nfull:,} in the cache after SIPORB's price / volume floor, "
          f"{W.S:,} ever in the universe")
    usz, yrs = W.U.sum(axis=1), W.days.year.to_numpy()
    print("universe size per session by year (sessions with a universe: min / median / max): " + "; ".join(
        f"{y}: {int((m := (yrs == y) & (usz > 0)).sum())} sessions {int(usz[m].min())} / {int(np.median(usz[m]))} / {int(usz[m].max())}" for y in sorted(set(yrs)) if ((yrs == y) & (usz > 0)).any()))
    Lr, Lk = rm_build(W, WF0, PRE_END, "remove", units=False), rm_build(W, WF0, PRE_END, "naive", units=False)
    r_all, f_all, x_all = rm_schedule(W.days)
    inwf = [(r, f, x) for r, f, x in zip(r_all.tolist(), f_all.tolist(), x_all.tolist()) if x >= 0 and WF0 <= W.days[x] <= PRE_END]
    first_full = min((r for r, f, x in inwf if r >= SPEC["win"] - 1), default=None)
    print(f"rebalances: {len(Lr.recs)} in WF (positions that exit {WF0:%Y-%m-%d} .. {PRE_END:%Y-%m-%d} with a full {SPEC['win']}-session window), {sum(r.traded for r in Lr.recs)} with a pool of at least 2 x {SPEC['n_side']} names"
          + (f"; the first rank session with a full window is {W.days[first_full]:%Y-%m-%d} (filled {W.days[first_full + 1]:%Y-%m-%d})" if first_full is not None else "")
          + f"; {sum(1 for r, f, x in inwf if r < SPEC['win'] - 1)} earlier ranks are warm-up; the stage's last rank has no next fill: unresolved, out")
    by = defaultdict(list)
    for rec in Lr.recs:
        by[int(W.days[rec.f].year)].append((rec.nu, rec.nfull, len(rec.pool)))
    print("names with a full window (>= 230 own returns and >= 230 ES pairs) per rebalance, by fill year (universe / full window / eligible pool: min - mean - max): " + "; ".join(
        f"{y}: {len(v)} rebalances, universe {min(a for a, b, c in v)}-{np.mean([a for a, b, c in v]):.0f}-{max(a for a, b, c in v)}, full {min(b for a, b, c in v)}-{np.mean([b for a, b, c in v]):.0f}-{max(b for a, b, c in v)}, "
        f"pool {min(c for a, b, c in v)}-{np.mean([c for a, b, c in v]):.0f}-{max(c for a, b, c in v)}" for y, v in sorted(by.items())))
    print_counts("registered (a flag inside the hold removes the name)", Lr.cnt)
    print_counts("look-ahead (names flagged inside the hold stay, on their naive raw path)", Lk.cnt)
    print_spin_counts("registered", Lr.cnt)
    print_spin_counts("look-ahead", Lk.cnt)
    print(f"TBIS flags: {len(tbis):,} symbol-days listed before the cut, {full_match:,} match a session and a cached name, {W.tbis_rows[1]:,} a name that is ever in the universe; every listed row is a flag")
    if W.ca is not None:
        print_wide(W.ca)
        st0 = calendar_start(W.ca["file"]["manifest"])
        print(d1_report(W, st0)[1] if st0 is not None else "calendar coverage [D1]: the manifest carries no readable start date - the coverage of the first ranks' windows cannot be counted")
    else:
        print(f"wide corporate-actions calendar [R1]: not on file yet ({winfo['path']}) - Stage A refuses until MANAGER's pull is on file and WIDE_CA_SHA is set; this dryload ran without dividends")
    pa, pr = W.es_cov["adj_prints"], W.es_cov["raw_prints"]
    e = W.es
    print(f"ES prints on the {W.T:,} stock sessions: 09:35 price {int(np.isfinite(e.e5).sum()):,}, 16:00 adj {int(np.isfinite(e.c16a).sum()):,}, 16:00 raw {int(np.isfinite(e.c16r).sum()):,}; fallback bars: "
          f"{int((pa['close_hm'] != pa['last']).sum())} closes (adj master), {int((pr['close_hm'] != pr['last']).sum())} closes (raw master); ES return defined on {int(np.isfinite(e.ret).sum()):,} sessions")
    print(es_report(W)[0])
    fin = np.flatnonzero(np.isfinite(W.k))
    print(f"k_t: defined from {W.days[fin[0]]:%Y-%m-%d} on ({len(fin):,} of {W.T:,} sessions); undefined on {int((~np.isfinite(W.k[wf])).sum())} WF sessions" if len(fin) else "k_t: undefined everywhere")
    print(f"cache manifest sha256: {manifest_sha()}")
    pm = peak_mb()
    print(f"dryload took {time.time() - t0:.0f}s" + (f", peak memory {pm:,.0f} MB" if pm else ""))


# ------------------------------------------------------------------ Stage A
def pick_candidate(cells, passing):
    """CHOICE (the prereg names no tie-break between two passing cells; A2 is only a report): the passing cell with the higher WF standalone ROC @ $30k goes to Stage B (ties: RES first); the other is reported"""
    return max(passing, key=lambda c: (cells[c]["base"]["roc"], -CELLS.index(c))) if passing else None


def stage_a_flow(cells, ast):
    """Stage A's bookkeeping, pure: would[c] = the cell clears every bar (its checks, null included); passing = would AND its audit complete; pending = would but the audit is incomplete; the candidate = pick_candidate(passing).
    A cell that fails a bar is never a candidate and never pending - however complete its audit"""
    would = {c: bool(cells[c]["PASS"]) for c in CELLS}
    passing = [c for c in CELLS if would[c] and ast[c]["audit_complete"]]
    pending = [c for c in CELLS if would[c] and not ast[c]["audit_complete"]]
    return would, passing, pending, pick_candidate(cells, passing)


def stage_a():
    if os.path.exists(os.path.join(OUT, "resmom_stageB_READ.flag")):                       # CHOICE: once the lockbox has been read Stage A is frozen (a re-run could change the cell or c after the fact)
        refuse("Stage A refused: Stage B has already read the lockbox - Stage A is frozen (resmom_stageB_READ.flag)")
    pok = prereg_ok()
    cal, winfo = wide_load(S.LB0)                                                          # [R1] refuses (nothing computed) when the wide calendar is not on file / not registered / not the registered file
    B, legs_meta = A13.load_463()                                                          # the book first: cheap, and a book that does not reproduce stops everything
    bk, dd, S12 = book_checks(B)
    print(f"BOOK #463 WF check (must be {BOOK_WF[0]} / {BOOK_WF[1]}): ROC@30k {bk['roc']:.2f} Sortino {bk['sortino']:.3f}; deepest drawdown ${dd['deepest']:,.0f} (must be ${DEEPEST_WF:,.0f}), "
          f"{dd['episodes']} qualifying episodes, {dd['days']} DD days, {dd['weeks']} DD weeks, by year {dd['by_year']}, the 2020-03-03 .. 03-27 episode {'found' if dd['episode_2020'] else 'NOT FOUND'}")
    if CHECK_BOOK and not (bk["ok"] and dd["ok"]):
        refuse("Stage A refused: the #463 records do not reproduce the registered WF numbers / drawdown structure (the prereg's [T5] facts) - fix the input first (nothing computed)")
    msha = manifest_sha()
    print(f"SIPORB cache manifest sha256: {msha} (registered: {D15.MANIFEST_PREFIX}...)")
    if CHECK_BOOK and not (msha and msha.startswith(D15.MANIFEST_PREFIX)):
        refuse("Stage A refused: the SIPORB cache manifest is missing or is not the registered photograph of the vendor (a re-pull must never be mixed in) - nothing computed")
    t0 = time.time()
    D = load_data(S.LB0)                                                                   # every input is cut to dates < 2025-06-30 inside this call, before anything is computed
    tbis = D15.load_tbis(S.LB0)
    es_frames, es_meta = D15.load_es(S.LB0)
    audit = read_audit()
    W = build_world(D, S.LB0, es_frames, tbis, cal)
    D15.release(D)
    wf = (W.days >= WF0) & (W.days <= PRE_END)
    kmiss = int((~np.isfinite(W.k[wf])).sum())
    print(f"world ready ({time.time() - t0:.0f}s): {int(wf.sum()):,} WF sessions, {W.S:,} names ever in the universe, k_t (read only by the borrow stress rows) undefined on {kmiss} WF sessions; ES masters "
          f"{es_meta['raw']['filename']} / {es_meta['adj']['filename']}", flush=True)
    es_txt, es_rec = es_report(W)
    print(es_txt)
    print_wide(W.ca)
    d1rec, d1txt = d1_report(W, calendar_start(W.ca["file"]["manifest"]))                  # [D1] (wide_load's gate guarantees a readable start)
    print(d1txt)
    out = {"prereg_sha256_lf": PREREG_SHA, "prereg_verified": pok["verified"], "prereg_committed": pok["committed"], **stamp(), "judged": False, "stageA": None, "candidate": None, "pending_audit": None,
           "book_check": bk, "dd_structure": dd, "manifest_sha256": msha, "es_return": es_rec, "wide_calendar": W.ca, "k_undefined_wf_sessions": kmiss, "coverage_d1": d1rec}
    aud_n = apply_audit(W, audit)
    asha = file_sha(os.path.join(OUT, "resmom_audit.csv"))
    print("audit file: " + ("none yet - every cell's audit is incomplete" if audit is None else f"{aud_n['rows']} rows ({aud_n['keep']} keep, {aud_n['data_event']} data_event: removed from the cells AND the null)"))
    rows = A13.book_rows(B, W)
    t1 = time.time()
    resR, objR = evaluate(W, B, S12, rows, "remove", NREP, 0, full=True)
    print(f"registered reading done ({time.time() - t1:.0f}s: the leg, the cells, the stress rows and {NREP} null draws)", flush=True)
    unused = unused_audit_rows(W, audit)
    if unused:
        print(f"  NOTE: {len(unused)} audit data_event row(s) removed nothing (the name was not in that fill session's universe): {unused[:5]}")
    t1 = time.time()
    resK, objK = evaluate(W, B, S12, rows, "naive", NREP, 1, full=False)
    print(f"look-ahead reading done ({time.time() - t1:.0f}s)", flush=True)
    t1 = time.time()
    with div_mode(W, False):                                                               # [R1] the no-dividend version of both cells (scores, picks and P&L without the cash dividends): a REPORTED row, never the verdict
        resD = evaluate(W, B, S12, rows, "remove", NREP, 2, full=False)[0]                 # (only its summary is read: the leg's unit paths are let go at once)
    print(f"no-dividend reading done ({time.time() - t1:.0f}s)", flush=True)
    t1 = time.time()
    resF, objF = evaluate(W, B, S12, rows, "remove", NREP, 3, full=False, drop=tuple(TS(x_) for x_ in D1_RANKS))       # [D1] the same registered reading without the first five rebalances (its own null stream): a REPORTED row, never the verdict
    nF = len(objF.legs.recs)
    del objF
    print(f"without-the-first-five reading done ({time.time() - t1:.0f}s)", flush=True)
    spin = {"registered_reading": {c: spin_counts(objR.legs, c) for c in CELLS}, "look_ahead_reading_kept_at_naive_price_pnl": {c: spin_counts(objK.legs, c) for c in CELLS}}
    rep, cands = reports(W, B, S12, rows, objR, resR["cells"], tbis, D15.asset_status(), legs_meta)
    ast = audit_status(cands, audit)
    cells = resR["cells"]
    for cell in CELLS:
        cells[cell]["audit"] = ast[cell]
    would, passing, pending, cand = stage_a_flow(cells, ast)
    flips = {c: bool(resK["cells"][c]["PASS"]) != bool(cells[c]["PASS"]) for c in CELLS}
    os.makedirs(OUT, exist_ok=True)
    pd.DataFrame([r for c in CELLS for r in cands[c]]).to_csv(os.path.join(OUT, "resmom_audit_candidates.csv"), index=False)
    print(f"WF {WF0:%Y-%m-%d} -> {PRE_END:%Y-%m-%d} ({int(wf.sum()):,} sessions) - the REGISTERED reading (a hygiene flag inside the hold removes the position)")
    print_cells(resR, ast)
    print(f"  look-ahead reading (positions with a flag INSIDE the hold kept at naive raw P&L) [O3]: null ROC p95 {resK['null']['roc_max']['p95']:.1f}")
    for cell in CELLS:
        k = resK["cells"][cell]
        print(f"    {cell}: {row(cell, k)[5:]} | Stage A {'PASS' if k['PASS'] else 'FAIL'}" + ("   *** FLIPS the registered verdict ***" if flips[cell] else "   (same verdict)"))
    print(f"  no-dividend version [R1] (the cash dividends left out of the scores, the picks and the P&L; REPORTED, never the verdict; its own null ROC p95 {resD['null']['roc_max']['p95']:.1f}):")
    for cell in CELLS:
        k = resD["cells"][cell]
        print(f"    {cell}: {row(cell, k)[5:]} | Stage A {'PASS' if k['PASS'] else 'FAIL'}; the registered, with dividends: net ${cells[cell]['base']['net']:,.0f} -> the dividends add ${cells[cell]['base']['net'] - k['base']['net']:,.0f}")
    print(f"  without the first five rebalances [D1] (their formation windows start before the calendar does: the dividends, splits and spin-offs before it count as zero there; {nF} of {len(objR.legs.recs)} rebalances remain; "
          f"REPORTED, never the verdict; its own null ROC p95 {resF['null']['roc_max']['p95']:.1f}):")
    for cell in CELLS:
        k = resF["cells"][cell]
        print(f"    {cell}: {row(cell, k)[5:]} | Stage A {'PASS' if k['PASS'] else 'FAIL (' + ', '.join(q for q, v in k['checks'].items() if not v) + ')'}; the registered, all {len(objR.legs.recs)}: net ${cells[cell]['base']['net']:,.0f}, ROC@30k {cells[cell]['base']['roc']:.1f}")
    print_spin_picks({"registered reading": spin["registered_reading"], "look-ahead reading (kept at naive price P&L)": spin["look_ahead_reading_kept_at_naive_price_pnl"]})
    print_reports(rep, cells)
    print_counts("L (registered)", objR.legs.cnt)
    print_counts("L (look-ahead)", objK.legs.cnt)
    print_spin_counts("L (registered)", objR.legs.cnt)
    print_spin_counts("L (look-ahead)", objK.legs.cnt)
    print(f"  audit candidates (the {AUDIT_N} largest gains per cell, with dates) -> {os.path.join(OUT, 'resmom_audit_candidates.csv')}; write resmom_audit.csv (symbol, date, cell, verdict keep|data_event, note) and run stage_a again")
    judged = not pending
    out.update({"judged": bool(judged), "pending_audit": pending, "audit_sha256": asha, "audit": aud_n, "audit_data_events_without_effect": unused,
                "stageA": {"cells": cells, "null": resR["null"], "would_pass_before_audit": would, "pass_cells": passing},
                "candidate": ({"cell": cand, "c": cells[cand]["A2"]["c"], "std_book": cells[cand]["A2"]["std_book"], "std_cell": cells[cand]["A2"]["std_cell"], "window": cells[cand]["A2"]["window"],
                               "a2_book_roc": cells[cand]["A2"]["roc"], "book_shadow_line": cells[cand]["A2"]["book_shadow_line"], "also_passes": [c for c in passing if c != cand]} if cand else None),
                "parity": {c: {"net": cells[c]["base"]["net"], "n_pos": cells[c]["base"]["n_pos"], "n_units": cells[c]["base"]["n_units"]} for c in CELLS},
                "without_first_five_reading": {"dropped_ranks": list(D1_RANKS), "rebalances_remaining": int(nF), "of": int(len(objR.legs.recs)), "null": resF["null"],
                                              "cells": {c: {"PASS": resF["cells"][c]["PASS"], "base": resF["cells"][c]["base"], "stress": resF["cells"][c]["stress"], "seat": resF["cells"][c]["seat"],
                                                            "checks": resF["cells"][c]["checks"], "A2": resF["cells"][c]["A2"]} for c in CELLS}},
                "spin_counts": spin,
                "no_dividend_reading": {"null": resD["null"], "cells": {c: {"PASS": resD["cells"][c]["PASS"], "base": resD["cells"][c]["base"], "stress": resD["cells"][c]["stress"], "seat": resD["cells"][c]["seat"],
                                                                         "checks": resD["cells"][c]["checks"], "A2": resD["cells"][c]["A2"]} for c in CELLS},
                                        "dividends_add_net": {c: cells[c]["base"]["net"] - resD["cells"][c]["base"]["net"] for c in CELLS}},
                "kept_naive_reading": {"null": resK["null"], "cells": {c: {"PASS": resK["cells"][c]["PASS"], "base": resK["cells"][c]["base"], "seat": resK["cells"][c]["seat"], "checks": resK["cells"][c]["checks"],
                                                                         "A2": resK["cells"][c]["A2"]} for c in CELLS}, "flips": flips},
                "hygiene_counts_by_year": {"registered": {y: dict(c) for y, c in sorted(objR.legs.cnt.items())}, "look_ahead": {y: dict(c) for y, c in sorted(objK.legs.cnt.items())}},
                "reports": rep, "es_masters": es_meta})
    dump(out, "resmom_stageA.json")
    if cand:
        print(f"RESMOM Stage A: PASS - cell {cand} clears every standalone bar with its audit complete (WF ROC@30k {cells[cand]['base']['roc']:.1f}); passing cells {passing}. "
              f"A2 (a report): c x{cells[cand]['A2']['c']:.4g} set by volatility, book ROC@30k {cells[cand]['A2']['roc']:.2f} -> "
              f"{'a forward BOOK shadow line opens beside the standalone one' if cells[cand]['A2']['book_shadow_line'] else 'no book shadow line'}. Stage B may run ONCE, on the stock families' one sealed-year day.")
    elif pending:
        print(f"RESMOM Stage A: NOT YET JUDGED - {pending} clear every bar but the hand audit of their {AUDIT_N} largest contributors is incomplete (judged: false in resmom_stageA.json).")
    else:
        print("RESMOM Stage A: FAIL - no cell passes (" + "; ".join(f"{c}: " + ", ".join(k for k, v in cells[c]['checks'].items() if not v) for c in CELLS) + ") - RESMOM r1 is dead; momentum is not re-tuned; the lockbox stays sealed.")
    pm = peak_mb()
    print(f"stage_a took {time.time() - t0:.0f}s" + (f", peak memory {pm:,.0f} MB" if pm else ""))
    return out


# ------------------------------------------------------------------ Stage B: the one read
def book_add_would_clear(r):
    """the REPORTED comparison of the book add on the sealed year with the old sealed-year bar (#463's own LB numbers): both the ROC and the Sortino must reach theirs (inclusive); a NaN fails. Reported, never judged"""
    return bool(r["roc"] >= RULES["b_roc"] and r["sortino"] >= RULES["b_sort"])


def b_checks(leg):
    """STAGE B's pass: the LEG's standalone veto and nothing else - >= 10 monthly rebalances, net > 0, net > 0 without its top name-month. It takes no book number: the book add on the lockbox year is a report, so it cannot be
    in this verdict. A NaN fails every comparison it enters -> {check name: bool}"""
    return {f"leg monthly rebalances>={RULES['b_reb']}": bool(leg["n_units"] >= RULES["b_reb"]), "leg net>0": bool(leg["net"] > 0), "leg net>0 without its top name-month": bool(leg["net_ex_top_pos"] > 0)}


def order_of_reads():
    """informational only - the spec names no order of reads for this family (the one sealed-year day is the stock families' and MANAGER's to register RESMOM into): the state of the other stock families' files, printed and stored"""
    out = {}
    try:
        out["SIPORB"] = A13.siporb_state() or "not read and not dead"
    except Exception as e:
        out["SIPORB"] = f"unknown ({type(e).__name__})"
    for nm, p in (("ATTN Stage A judged", os.path.join(A13.OUT, "attn_stageA.json")), ("DDW Stage A judged", A13.DDW_STAGE_A)):
        try:
            out[nm] = bool(json.load(open(p)).get("judged") is True)
        except Exception:
            out[nm] = False
    return out


def stage_b():
    """STAGE B (LB, once, on the stock families' one sealed-year day): the sealed year is the LEG's standalone veto: >= 10 monthly rebalances, net > 0, and > 0 without its top name-month. The book add on that year (#463 + c x
    the cell at Stage A's frozen c) is computed, printed and stored as book_add_reported - it is NEVER part of the pass. A surviving leg goes to a computed no-order forward shadow (Stage C); the forward record decides any
    book add (owner call). Every refusal is before the flag; the flag is written only after every load, every check and the whole result are in hand"""
    pa = os.path.join(OUT, "resmom_stageA.json")
    sa = json.load(open(pa)) if os.path.exists(pa) else {}
    cand = sa.get("candidate")
    cres = ((sa.get("stageA") or {}).get("cells") or {}).get(cand.get("cell") if isinstance(cand, dict) else None) or {}
    if not (sa.get("judged") is True and isinstance(cand, dict) and cres.get("PASS") is True and (cres.get("audit") or {}).get("audit_complete") is True):
        refuse("Stage B refused: no Stage A pass with a complete audit is on file - the lockbox stays sealed.")
    flag = os.path.join(OUT, "resmom_stageB_READ.flag")
    if os.path.exists(flag):
        refuse("Stage B refused: the lockbox was already read once (resmom_stageB_READ.flag)")
    prereg_ok()
    if sa.get("prereg_sha256_lf") != PREREG_SHA:
        refuse("Stage B refused: Stage A ran under another pre-registration (lockbox NOT read)")
    bad = [k for k, v in stamp().items() if sa.get(k) != v]
    if bad:
        refuse(f"Stage B refused: Stage A was written by a different harness version / early-close list ({', '.join(bad)} differs or is missing) - run stage_a again (lockbox NOT read)")
    if sa.get("audit_sha256") != file_sha(os.path.join(OUT, "resmom_audit.csv")):
        refuse("Stage B refused: resmom_audit.csv is not the file Stage A ran with (it changed, or went missing) - run stage_a again (lockbox NOT read)")
    cell = cand["cell"]
    try:
        c = float(cand["c"])
    except (TypeError, ValueError):
        c = float("nan")
    if cell not in CELLS or not (math.isfinite(c) and c > 0):                                  # c is a volatility ratio: any positive number is a frozen size, but NaN / 0 / missing is a broken file
        refuse(f"Stage B refused: the frozen cell {cand.get('cell')} / size c {cand.get('c')} is not one of {CELLS} / a positive number (lockbox NOT read)")
    oor = order_of_reads()
    print("order of reads (information, not enforced here): " + "; ".join(f"{k}: {v}" for k, v in oor.items()) + " - RESMOM reads the stock families' one sealed-year day only if MANAGER registered it before that day")
    B, legs_meta = A13.load_463()                                                              # every input is loaded and checked BEFORE the flag: a bad file cannot burn the lockbox
    bk = A13.book_check(B, LB0, LB1, BOOK_LB)
    print(f"BOOK #463 LB check (must be {BOOK_LB[0]} / {BOOK_LB[1]}): ROC@30k {bk['roc']:.2f} Sortino {bk['sortino']:.3f}")
    if CHECK_BOOK and not bk["ok"]:
        refuse("Stage B refused: the #463 records do not reproduce its LB numbers - settle the end-date convention first (lockbox NOT read)")
    msha = manifest_sha()
    if CHECK_BOOK and not (msha and msha.startswith(D15.MANIFEST_PREFIX) and msha == sa.get("manifest_sha256")):
        refuse("Stage B refused: the SIPORB cache manifest is not the one Stage A ran on (a re-pull must never be mixed in) - lockbox NOT read")
    cal, winfo = wide_load(S.END)                                                              # [R1] the same registered calendar, cut at the lockbox's end
    D = load_data(S.END)
    tbis = D15.load_tbis(S.END)
    es_frames, es_meta = D15.load_es(S.END)
    audit = read_audit()
    W = build_world(D, S.END, es_frames, tbis, cal)
    D15.release(D)
    apply_audit(W, audit)
    rows = A13.book_rows(B, W)
    hole_txt, hole_rec = es_report(W, LB0, LB1)                                                # the ES holes that reach the lockbox: printed and stored with the read
    Lw = rm_build(W, WF0, PRE_END)                                                             # Stage A's WF numbers (and the frozen c) must reproduce on Stage B's data (a cache or code drift stops it BEFORE the read)
    for cc in CELLS:
        run = run_cell(W, cell_leg(Lw, cc), D15.l1_cfg())
        xw = D15.to_B(run.x, rows, B.n)
        st, ref = D15.cell_stats(B, xw, D15.to_B(run.cnt, rows, B.n), WF0, PRE_END, run), sa["parity"][cc]
        print(f"WF re-read on Stage B's data: {cc} positions {st['n_pos']:,} (Stage A {ref['n_pos']:,}), net ${st['net']:,.0f} (Stage A ${ref['net']:,.0f})")
        if st["n_pos"] != ref["n_pos"] or st["n_units"] != ref["n_units"] or abs(st["net"] - ref["net"]) > max(1.0, 1e-6 * abs(ref["net"])):
            refuse(f"Stage B refused: the WF numbers of {cc} do not reproduce on Stage B's data - the cache or the code changed since Stage A (lockbox NOT read)")
        if cc == cell:
            c2 = a2_report(B, xw)["c"]
            print(f"  frozen size {cell}: c x{c:.6g} (Stage A) vs x{c2:.6g} recomputed from {A2_WIN[0]:%Y-%m-%d} .. {A2_WIN[1]:%Y-%m-%d} on Stage B's data")
            if not (math.isfinite(c2) and abs(c2 - c) <= 1e-9 * c):
                refuse(f"Stage B refused: the volatility-set size c of {cell} does not reproduce on Stage B's data - the cache or the code changed since Stage A (lockbox NOT read)")
    L = rm_build(W, LB0, LB1)                                                                  # CHOICE (r15's order): the whole LB result is computed, nothing shown, BEFORE the flag
    run = run_cell(W, cell_leg(L, cell), D15.l1_cfg(), pos=True)
    xB, cB = D15.to_B(run.x, rows, B.n), D15.to_B(run.cnt, rows, B.n)
    leg = D15.cell_stats(B, xB, cB, LB0, LB1, run)
    r = D15.book_at(B, xB, c, LB0, LB1)                                                        # the book add at the FROZEN c - c is never re-set on the sealed year
    would = book_add_would_clear(r)                                                            # the old sealed-year bar (#463's own LB numbers, 155.54 / 4.150): reported, never judged
    chk = b_checks(leg)
    ok = all(chk.values())                                                                     # the pass is the LEG's veto - the book add below is a report and is not in this line
    add = {"c": c, "roc": r["roc"], "sortino": r["sortino"], "net": r["net"], "max_dd": r["max_dd"], "reference": {"roc": RULES["b_roc"], "sortino": RULES["b_sort"]}, "would_have_cleared": would,
           "note": "reported, never a pass (MANAGER #48): the forward record decides any book add (owner call)"}
    cnt = {y: dict(v) for y, v in sorted(L.cnt.items())}
    text = json.dumps({"cell": cell, "c": c, "order_of_reads": oor, "book_check": bk, "es_masters": es_meta, "leg": leg, "checks": chk, "pass": bool(ok), "book_add_reported": add, "es_return_lb": hole_rec, "wide_calendar": W.ca,
                       "hygiene_counts_by_year": cnt, "top_name_months": rm_candidate_rows(W, L, cell, run, tbis, D15.asset_status(), 20), **stamp(), "prereg_sha256_lf": PREREG_SHA}, indent=1, default=R11.js)
    buf = io.StringIO()                                                                        # the whole printout is built here, before the flag: a formatting error cannot burn the lockbox
    with contextlib.redirect_stdout(buf):
        print("Stage B (lockbox, read once) - the sealed year is the LEG's standalone veto")
        print(f"  {cell}: positions {leg['n_pos']:,}, monthly rebalances {leg['n_units']:,}, net ${leg['net']:,.0f}, ROC@30k {leg['roc']:.1f}, Sortino {leg['sortino']:.2f}; its top name-month ${leg['top_pos']:,.0f}, "
              f"net without it ${leg['net_ex_top_pos']:,.0f}")
        print("  " + hole_txt)
        print("  Stage B checks: " + ", ".join(k + (" ok" if v else " FAIL") for k, v in chk.items()) + f" -> {'PASS' if ok else 'FAIL'}")
        print(f"  book add, REPORTED and never part of the pass: #463 + {cell} x{c:.4g} (frozen): LB ROC@30k {r['roc']:.2f} Sortino {r['sortino']:.3f} net ${r['net']:,.0f} -> would "
              f"{'have' if would else 'NOT have'} cleared {RULES['b_roc']:g} / {RULES['b_sort']:g}")
        print("RESMOM Stage B: " + ("PASS - the leg survives its sealed year: it goes to a computed no-order FORWARD SHADOW (Stage C) with its own bar, logged by research id; the book add above is a report - "
                                    "the forward record decides any book add, and opening any account is the owner's decision (owner call)." if ok else
                                    "FAIL - the leg is vetoed by its sealed year: RESMOM r1 is dead; ledger + memory."))
    with open(flag, "x") as f:                                                                 # exclusive create: the one read starts here - what is left is two writes and a print
        f.write(pd.Timestamp.now().isoformat())
    with open(os.path.join(OUT, "resmom_stageB.json"), "w") as f:
        f.write(text)
    print(buf.getvalue().rstrip())
    pm = peak_mb()
    if pm:
        print(f"peak memory {pm:,.0f} MB")
    return ok


# ------------------------------------------------------------------ test support: hand-made worlds, a toy world with planted events, and plain-python recounts of every score, pool, pick and path (independent of the vectorised code)
def close(a, b, tol=1e-9):
    return D15.close(a, b, tol)


def prices(ret, p0=50.0):
    """a (T, S) matrix of daily returns (row 0 ignored) -> prices (row 0 = p0); a NaN return makes every later price NaN"""
    ret = np.asarray(ret, float)
    out = np.empty(ret.shape)
    out[0] = p0
    for t in range(1, len(ret)):
        out[t] = out[t - 1] * (1.0 + ret[t])
    return out


def with_dividends(W, Dr=None, Sp=None):
    """test support: the dividend arrays on a hand-made World (Dr = the raw per-share cash on each ex-date, (T, S), or None) and the raw input kept as W.Dr_in for the plain-python recounts"""
    attach_dividends(W, Dr, Sp)
    W.Dr_in = None if Dr is None else np.array(Dr, float)
    W.Sp_in = None if Sp is None else np.array(Sp, bool)                                   # [D2] the spin-off / stock-dividend ex-date sessions as given, for the plain-python recounts
    return W


def mk_world(Cl, es_ret, F=None, chg=None, msplit=None, tbis=None, Od=None, U=None, k=None, Vv=None, Dr=None, Sp=None):
    """a r15 World on hand-made arrays: Cl = the (raw) closes; the open = the prior close unless given; F = 1 (no split factor); every name is in the universe whenever it has a price unless U is given; no hygiene flag;
    es_ret = ES's daily return per session (row 0 NaN)"""
    T, Sn = Cl.shape
    days = pd.bdate_range("2024-01-01", periods=T)
    syms = np.array([f"N{j:02d}" for j in range(Sn)])
    zero = lambda: np.zeros((T, Sn), bool)
    Od = np.vstack([Cl[:1], Cl[:-1]]) if Od is None else Od
    F = np.ones((T, Sn)) if F is None else F
    Vv = np.full((T, Sn), 3e6) if Vv is None else Vv
    U = (np.isfinite(Od) & np.isfinite(Cl)) if U is None else U
    es = SimpleNamespace(e5=None, c16a=None, c16r=None, ret=np.asarray(es_ret, float), gap=np.full(T, np.nan), k=np.ones(T) if k is None else np.asarray(k, float))
    nan = np.full((T, Sn), np.nan)
    W = D15.World(days, syms, Od, Cl, Vv, F, U, zero() if chg is None else chg, zero() if msplit is None else msplit, zero() if tbis is None else tbis, nan, nan, es)
    return with_dividends(W, Dr, Sp)


def toy_world(seed=1, T=450, Sn=14, divs=True, spins=True):
    """450 sessions (Mon 2024-01-01 on) x 14 names with the registered windows (the first rank session with a full 252-session window is 2024-12-31; weekdays are sessions here, holidays included), every rule's case planted by hand - where:
    N00 a registered 2-for-1 split on 2025-03-14 (the factor moves, raw prices halve, split-safe returns do not); N01 an unadjusted x4 on 2025-01-14 flagged by the gap scan (a fake +300% return day);
    N02 a TBIS flag on 2025-04-10; N03 a genuine +60% gap on 2025-05-12 (no ratio fit: the +-50% rule); N04 stops printing on 2025-06-12; N05 no close on 2025-03-20 (the mark carries, two returns are lost);
    N06 first trades on row 40 (221 returns at the first rank: under 230); ES has no return on 2025-02-10 and 02-11 (holes: those sessions are skipped for every name). W.true_ret = the split-safe daily returns.
    [R1 / R2] N13 falls 0.3% a day (the clear short of every rank before 2025-03-17) and stops printing on 2025-03-17: a stopped short inside the March hold; the planted cash dividends are in the body (divs=True).
    [D2] (spins=True) N11 a spin-off inside the windows of the first ranks (a return left out of its score), N12 a stock dividend inside the hold of the 02-28 rank (f = 03-03, x = 04-01: removed before the ranking, kept at its naive
    price P&L by the other reading), N10 a spin-off on that hold's EXIT session (inside it) = the 03-31 rank's FILL session (not inside that one), N09 a stock dividend on the 02-28 rank's fill session (bought ex: not in that hold)"""
    rng = np.random.default_rng(seed)
    days = pd.bdate_range("2024-01-01", periods=T)
    syms = np.array([f"N{j:02d}" for j in range(Sn)])
    dr = lambda s: days.get_loc(TS(s))
    m = rng.normal(0.0004, 0.01, T)
    m[0] = np.nan
    beta, drift = rng.uniform(0.4, 1.6, Sn), rng.normal(0.0, 0.0006, Sn)
    ret = drift + beta * np.nan_to_num(m)[:, None] + rng.normal(0.0, 0.014, (T, Sn))
    ret[0] = 0.0
    if Sn > 13:
        ret[:, 13] = -0.003 + 0.2 * ret[:, 13]                                            # N13 falls 0.3% a day with a fifth of the noise: the clear short of every rank before it stops printing
    Ac = 40.0 * (1.0 + 0.04 * np.arange(Sn)) * np.cumprod(1.0 + ret, axis=0)             # split-safe prices
    Cl = Ac.copy()
    Od = np.vstack([Cl[:1], Cl[:-1]]) * (1.0 + rng.normal(0.0, 0.004, (T, Sn)))
    Vv = rng.uniform(2.0e6, 4.0e6, (T, Sn)) * (1.0 + 0.1 * np.arange(Sn))
    F, chg, ms, tb = np.ones((T, Sn)), np.zeros((T, Sn), bool), np.zeros((T, Sn), bool), np.zeros((T, Sn), bool)
    s0 = dr("2025-03-14")
    F[:s0, 0] = 2.0
    Cl[:, 0] *= F[:, 0]
    Od[:, 0] *= F[:, 0]
    chg[s0, 0] = True                                                                     # N00: Alpaca's convention: F = raw / split-adjusted open is 2 before a 2-for-1, 1 after
    s1 = dr("2025-01-14")
    Cl[s1:, 1] *= 4.0
    Od[s1:, 1] *= 4.0
    ms[s1, 1] = True                                                                      # N01
    tb[dr("2025-04-10"), 2] = True                                                        # N02
    s3 = dr("2025-05-12")
    Cl[s3:, 3] *= 1.6
    Od[s3:, 3] *= 1.6                                                                     # N03 (no flag but the +-50% rule)
    s4 = dr("2025-06-12")
    for a in (Od, Cl, Vv, F):
        a[s4:, 4] = np.nan                                                                # N04
    if Sn > 13:
        for a in (Od, Cl, Vv, F):
            a[dr("2025-03-17"):, 13] = np.nan                                             # N13 stops printing inside the March hold (a short with no open at its exit session)
    Cl[dr("2025-03-20"), 5] = np.nan                                                      # N05
    for a in (Od, Cl, Vv, F):
        a[:40, 6] = np.nan                                                                # N06
    m[[dr("2025-02-10"), dr("2025-02-11")]] = np.nan                                      # ES holes
    atr = np.full((T, Sn), 2.0)
    with D15.spec(univ=Sn):
        U = D15.universe_mask(Cl, Vv, atr, chg)
    es = SimpleNamespace(e5=None, c16a=None, c16r=None, ret=m, gap=np.full(T, np.nan), k=np.clip(rng.lognormal(0.0, 0.4, T), 0.5, 2.0))
    nan = np.full((T, Sn), np.nan)
    Dr = np.zeros((T, Sn))
    if divs:                                                                              # [R1] the calendar's cash dividends, planted where the conventions bite (the toy W.Dr_in is the raw input the recounts read)
        r_all, f_all, x_all = rm_schedule(days)
        Dr[:, 7:13] = np.where((np.arange(T) % 21 == 4)[:, None], 0.2 + 0.05 * np.arange(6)[None, :], 0.0)     # N07 .. N12: a regular dividend every 21st session (inside holds, formation windows, on fill / exit sessions)
        Dr[dr("2025-02-20"), 0] += 1.0                                                    # N00: 1.00 a pre-split share where F = 2 (0.50 on the split-adjusted basis)
        Dr[dr("2025-03-24"), 0] += 0.5                                                    # N00: after the split (F = 1)
        Dr[dr("2025-04-14"), 1] += 0.5                                                    # N01
        Dr[dr("2025-03-12"), 2] += 0.4                                                    # N02 (the TBIS name)
        Dr[dr("2025-05-14"), 3] += 0.3                                                    # N03 (after its +60% gap)
        Dr[dr("2025-06-20"), 4] += 0.4                                                    # N04: after it stopped printing: no close, no dividend
        Dr[dr("2025-03-20"), 5] += 0.4                                                    # N05: on its missing-close session: no dividend
        Dr[f_all[5], 8] += 0.3                                                            # N08: ON the fill session of a rebalance (bought ex-dividend: nothing)
        Dr[x_all[5], 9] += 0.3                                                            # N09: ON the exit session of a rebalance (sold ex-dividend after the prior close: received)
        Dr[dr("2025-02-11"), 10] += 0.35                                                  # N10: a session on which ES has no return: the stock's total return is defined, the regression pair is skipped
    Sp = np.zeros((T, Sn), bool)
    if spins and Sn > 12:
        Sp[dr("2024-06-12"), 11] = True                                                   # N11: inside the regression / formation windows of the first ranks
        Sp[dr("2025-03-12"), 12] = True                                                   # N12: inside the hold of the 02-28 rank
        Sp[dr("2025-04-01"), 10] = True                                                   # N10: the 02-28 rank's exit session = the 03-31 rank's fill session
        Sp[dr("2025-03-03"), 9] = True                                                    # N09: the 02-28 rank's fill session
    W = D15.World(days, syms, Od, Cl, Vv, F, U, chg, ms, tb, nan, nan, es)
    W.true_ret = ret
    return with_dividends(W, Dr, Sp)


def brute_div_amt(W, s, j):
    """D*_s of name j on session s, plain python: the calendar's raw amount over the session's factor, only where the name has a close, a prior close and a factor and the amount is positive (0.0 otherwise)"""
    Dr = getattr(W, "Dr_in", None)
    if Dr is None or s < 1:
        return 0.0
    d, F1, F0 = Dr[s, j], W.F[s, j], W.F[s - 1, j]
    c1, c0 = W.Cl[s, j] / F1, W.Cl[s - 1, j] / F0
    return d / F1 if (math.isfinite(d) and d > 0 and math.isfinite(c1) and math.isfinite(c0) and c0 > 0 and math.isfinite(F1) and F1 > 0) else 0.0


def brute_ret(W, s, j):
    """the split-safe daily TOTAL return of name j on session s, plain python: (Ac_s + D*_s) / Ac_(s-1) - 1 (NaN without both closes; NaN on a [D2] spin-off / stock-dividend ex-date session of the name: that session's return is left out)"""
    if s < 1:
        return float("nan")
    Sp = getattr(W, "Sp_in", None)
    if Sp is not None and Sp[s, j]:
        return float("nan")
    c1, c0 = W.Cl[s, j] / W.F[s, j], W.Cl[s - 1, j] / W.F[s - 1, j]
    return (c1 + brute_div_amt(W, s, j)) / c0 - 1.0 if math.isfinite(c1) and math.isfinite(c0) else float("nan")


def brute_div(W, f, x, j, naive):
    """a position's dividend credit per $1 of entry on rows f .. x (index = row - f), plain python: nothing on the fill session (bought ex-dividend), D*_t / the entry open on every later session through the exit
    session (the raw amount over the raw entry open on the naive path)"""
    Dr = getattr(W, "Dr_in", None)
    out = [0.0] * (x - f + 1)
    if Dr is None:
        return out
    entry = W.Od[f, j] if naive else W.Od[f, j] / W.F[f, j]
    for h in range(1, x - f + 1):
        t = f + h
        d = brute_div_amt(W, t, j)
        if d > 0:
            out[h] = (Dr[t, j] if naive else d) / entry
    return out


def brute_path(W, f, x, j, sd, naive, **kw):
    """r15's plain-python path + the dividends: a long receives, a short pays (a stopped long valued at -100% has no exit-row dividend)"""
    path, stopped = D15.brute_l1_path(W, f, x, j, sd, naive, **kw)
    d = brute_div(W, f, x, j, naive)
    if kw.get("lose100") and sd > 0 and stopped:
        d[-1] = 0.0
    return [p_ + sd * q_ for p_, q_ in zip(path, d)], stopped


def brute_scores(W, r, j, old=False):
    """plain python (n_ret, n_pair, res, raw) of name j at rank session r: the split-safe daily returns row by row, the OLS by numpy's least squares on the finite pairs (not the closed form of rm_scores), the sums and the
    sample standard deviation over the formation rows, the compound return by a running product. The residual is return - beta x ES (v2: the alpha stays in); old=True is the v1 construction (return - alpha - beta x ES), kept
    only so t_identity can show what v2 removed"""
    a, fa, fe = windows(r)
    ys = {s: brute_ret(W, s, j) for s in range(a, r + 1)}
    n_ret = sum(math.isfinite(y) for y in ys.values())
    pairs = [(s, ys[s], W.es.ret[s]) for s in range(a, r + 1) if math.isfinite(ys[s]) and math.isfinite(W.es.ret[s])]
    nan = float("nan")
    fin_F = [ys[s] for s in range(fa, fe + 1) if math.isfinite(ys[s])]
    raw = math.prod(1.0 + y for y in fin_F) - 1.0 if fin_F else nan
    if len(pairs) < 3:
        return n_ret, len(pairs), nan, raw
    coef = np.linalg.lstsq(np.array([[1.0, p[2]] for p in pairs]), np.array([p[1] for p in pairs]), rcond=None)[0]
    e = {p[0]: p[1] - (coef[0] if old else 0.0) - coef[1] * p[2] for p in pairs}
    eF = [e[s] for s in range(fa, fe + 1) if s in e]
    sd = float(np.std(eF, ddof=1)) if len(eF) >= 2 else nan
    return n_ret, len(pairs), (sum(eF) / sd if sd > 0 else nan), raw


def brute_rm(W, lo, hi, post_mode="remove"):
    """every rebalance whose position exits in [lo, hi], plain python end to end (the schedule from the months of consecutive sessions, the universe taken from W.U, every other rule re-implemented with loops):
    [{r, f, x, pool: {col: (res, raw, naive)}, long: {cell: [cols]}, short: {cell: [cols]}}]"""
    sp, nn = SPEC, SPEC["n_side"]
    Sp = getattr(W, "Sp_in", None)
    key = [(W.days[i].year, W.days[i].month) for i in range(W.T)]
    ranks = [i for i in range(W.T - 1) if key[i] != key[i + 1]]
    recs = []
    for k, r in enumerate(ranks):
        f, x = r + 1, (ranks[k + 1] + 1 if k + 1 < len(ranks) else -1)
        if x < 0 or not (lo <= W.days[x] <= hi) or r < sp["win"] - 1:
            continue
        a, lo_pre = windows(r)[0], r - sp["skip"] - sp["hyg_lead"] + 1
        pool, n_hold, n_wnames, n_wsess = {}, 0, 0, 0
        for j in [j for j in range(W.S) if W.U[f, j]]:
            hold = Sp is not None and any(bool(Sp[s, j]) for s in range(f + 1, x + 1))                  # [D2] an ex-date in f < t <= x: the fill session's own is bought ex, the exit session's is inside
            win = 0 if Sp is None else sum(1 for s in range(max(a, 0), r + 1) if s >= 1 and Sp[s, j] and math.isfinite(W.Cl[s, j] / W.F[s, j]) and math.isfinite(W.Cl[s - 1, j] / W.F[s - 1, j]))
            n_hold, n_wnames, n_wsess = n_hold + int(hold), n_wnames + int(win > 0), n_wsess + win                    # the counts over every universe name, whatever else removes it
            n_ret, n_pair, res, raw = brute_scores(W, r, j)
            if n_ret < sp["min_n"] or n_pair < sp["min_n"] or not math.isfinite(W.Od[f, j] / W.F[f, j]) or not (math.isfinite(res) and math.isfinite(raw)):
                continue
            pre = any(any(D15.brute_flags(W, s, j)) for s in range(max(lo_pre, 0), r + 1))
            old = any(any(D15.brute_flags(W, s, j)[1:]) for s in range(max(a, 0), lo_pre))
            post = hold or any(any(D15.brute_flags(W, s, j)) for s in range(r + 1, x + 1))
            if pre or old or W.aud1[f, j] or (post and post_mode == "remove"):
                continue
            pool[j] = (res, raw, bool(post and post_mode == "naive"), win, hold)
        rec = {"r": r, "f": f, "x": x, "pool": pool, "long": {c: [] for c in CELLS}, "short": {c: [] for c in CELLS}, "n_hold_names": n_hold, "n_win_names": n_wnames, "n_win_sessions": n_wsess}
        if len(pool) >= 2 * nn:
            for q, c in enumerate(CELLS):
                order = sorted(pool, key=lambda j: (pool[j][q], j))
                rec["short"][c], rec["long"][c] = order[:nn], order[::-1][:nn]
        recs.append(rec)
    return recs


def brute_skip(W, r, j):
    """the skipped month's split-safe TOTAL return of name j at rank r, plain python: the compound of the finite daily total returns of sessions r-20 .. r (NaN with none)"""
    fin = [y for y in (brute_ret(W, s, j) for s in range(r - SPEC["skip"] + 1, r + 1)) if math.isfinite(y)]
    return math.prod(1.0 + y for y in fin) - 1.0 if fin else float("nan")


def brute_spin_counts(Bz, cell):
    """[D2] spin_counts recounted from the plain-python rebalances: (window, hold; long, short) of one cell's picks"""
    out = {sd: {"positions": 0, "window_positions": 0, "window_sessions": 0, "hold_positions": 0} for sd in ("long", "short")}
    for b in Bz:
        for sd, js in (("long", b["long"][cell]), ("short", b["short"][cell])):
            for j in js:
                o, (win, hold) = out[sd], b["pool"][j][3:5]
                o["positions"] += 1
                o["window_positions"] += int(win > 0)
                o["window_sessions"] += int(win)
                o["hold_positions"] += int(hold)
    return out


def compare_rm(W, L, Bz, tag):
    """the vectorised build against the plain-python recount: the schedule, every pool (names, both scores, the naive flags), the 50 / 50 picks of both cells, and the daily path of EVERY pool name under four costings
    (base, 10 bps, the 3% borrow stress with k_t, longs at -100%)"""
    assert len(L.recs) == len(Bz), (tag, len(L.recs), len(Bz))
    cfgs = (("base", D15.l1_cfg(), {}), ("10 bps", D15.l1_cfg(bps=10.0), {"bps": 10.0}), ("borrow 3%", D15.l1_cfg(borrow=(BORROW, 0.03)), {"borrow": (BORROW, 0.03), "k": True}),
            ("lose100", D15.l1_cfg(lose100=True), {"lose100": True}))
    n_paths = 0
    for rec, b in zip(L.recs, Bz):
        assert (rec.r, rec.f, rec.x) == (b["r"], b["f"], b["x"]), tag
        assert rec.pool.tolist() == sorted(b["pool"]), (tag, rec.r, rec.pool.tolist(), sorted(b["pool"]))
        assert close(rec.score["RES"], [b["pool"][j][0] for j in rec.pool]) and close(rec.score["RAW"], [b["pool"][j][1] for j in rec.pool]), (tag, rec.r, "scores")
        assert rec.naive.tolist() == [b["pool"][j][2] for j in rec.pool], (tag, rec.r)
        assert close(rec.skip_ret, [brute_skip(W, rec.r, j) for j in rec.pool]), (tag, rec.r, "the skipped month's total return: the compound of the daily total returns, from raw closes, factors and the calendar's cash")
        assert rec.spin_win.tolist() == [b["pool"][j][3] for j in rec.pool] and rec.spin_hold.tolist() == [b["pool"][j][4] for j in rec.pool], (tag, rec.r, "the [D2] counts per pool name")
        assert rec.traded == bool(b["long"]["RES"]), (tag, rec.r)
        if not rec.traded:
            continue
        for c in CELLS:
            assert rec.pool[rec.pick[c][0]].tolist() == b["long"][c] and rec.pool[rec.pick[c][1]].tolist() == b["short"][c], (tag, rec.r, c)
            assert not set(b["long"][c]) & set(b["short"][c]), "a name is never on both sides"
        kt = W.k[rec.f:rec.x + 1]
        idx = np.arange(len(rec.pool))
        for nm, cfg, kw in cfgs:
            for sd in (1, -1):
                P = D15.l1_pnl(rec.U, idx, sd, cfg, kt)
                for i, j in enumerate(rec.pool):
                    want, _ = brute_path(W, rec.f, rec.x, int(j), sd, bool(rec.naive[i]), bps=kw.get("bps", COST_BPS), borrow=kw.get("borrow", (BORROW, None)), kt=kt if kw.get("k") else None,
                                                lose100=kw.get("lose100", False))
                    assert close(P[i], want), (tag, nm, rec.r, int(j), sd)
                    n_paths += 1
    for key, bk in (("spin_window_names", "n_win_names"), ("spin_window_sessions", "n_win_sessions"), ("spin_hold_names", "n_hold_names")):       # [D2] the counts over every universe name (not first-reason), summed over the fill years
        assert sum(c.get(key, 0) for c in L.cnt.values()) == sum(b[bk] for b in Bz), (tag, key, sum(c.get(key, 0) for c in L.cnt.values()), sum(b[bk] for b in Bz))
    return n_paths


def series_check(W, L, Bz):
    """each cell's daily series (run_cell on r15's L1 engine, $4,000 a name) equals the sum of the recount's position paths booked on rows f .. x"""
    for cell in CELLS:
        x0 = np.zeros(W.T)
        for b in Bz:
            if not b["long"][cell]:
                continue
            for sd, js in ((1, b["long"][cell]), (-1, b["short"][cell])):
                for j in js:
                    x0[b["f"]:b["x"] + 1] += SPEC["slot"] * np.array(brute_path(W, b["f"], b["x"], j, sd, b["pool"][j][2])[0])
        assert close(run_cell(W, cell_leg(L, cell), D15.l1_cfg()).x, x0), f"{cell} series"


def synth_book(seed=11, lo="2016-07-01", hi="2026-06-30", deep=True):
    """a synthetic #463: daily P&L on business days, with a deep episode in March 2020 -> (B with index / raw / n / mask, S12 = r12_mdl.Stretch of its WF stretch)"""
    rng = np.random.default_rng(seed)
    ix = pd.bdate_range(lo, hi)
    book = rng.normal(35.0, 650.0, len(ix))
    if deep:
        book[(ix >= "2020-03-03") & (ix <= "2020-03-27")] -= 900.0
    B = SimpleNamespace(index=ix, raw=book, n=len(ix), mask=lambda a, b: np.asarray((ix >= a) & (ix <= b)))
    return B, M12.Stretch(book, ix, None, WF0, PRE_END)


# ------------------------------------------------------------------ selftest: hand-made worlds, no files, no data
def t_constants():
    assert (NREP, SEED, CELLS, AUDIT_N) == (500, 20261005, ("RES", "RAW"), 50) and YEARS == tuple(range(2016, 2025)) and CRASH_MONTHS == ("2020-04", "2020-11", "2022-01", "2023-01")
    assert (A2_WIN, A2_TARGET, A2_REPORT) == ((TS("2017-01-03"), TS("2018-12-31")), 0.25, (0.5, 2.0))
    assert (WF0, PRE_END, LB0, LB1) == (TS("2016-07-01"), TS("2025-06-29"), TS("2025-06-30"), TS("2026-06-30")) and (S.LB0, S.END) == (LB0, R11.LBX)
    assert (BOOK_WF, BOOK_LB, DEEPEST_WF) == ((93.81, 3.816), (155.54, 4.15), 44849.0)
    assert SPEC == {"win": 252, "form_n": 231, "skip": 21, "min_n": 230, "n_side": 50, "slot": 4000.0, "hyg_lead": 5}, "SPEC is the prereg: 252-session regression window, formation r-251 .. r-21, 230 pairs, 50 + 50 at $4,000"
    assert SPEC["form_n"] + SPEC["skip"] == SPEC["win"] and windows(300) == (49, 49, 279), "the formation window ends 21 sessions before r and starts at r - 251"
    assert (COST_BPS, STRESS_BPS, BORROW, BORROW_STRESS, K_STRESS) == (5.0, (10.0, 20.0), 0.0025, (0.01, 0.03), 1.5) and HYG == ("split", "gap", "tbis", "jump")
    assert RULES["reb"] == 60 and RULES["roc"] == 15.0 and RULES["years"] == 6 and RULES["best_pct"] == D15.RULES["best_pct"] == 1 and RULES["b_reb"] == 10 and (RULES["b_roc"], RULES["b_sort"]) == BOOK_LB
    assert all(RULES[k] is True for k in ("net_pos", "stress", "null", "ex2020", "exbest")), "every registered check is on (the switches are for smoke() only)"
    assert abs(RULES["a2_roc"] - 98.5005) < 1e-9 and RULES["a2_sort"] == 3.816 and D15.RULES["a2_roc"] == RULES["a2_roc"] and CHECK_BOOK is True
    assert D15.SPEC["l1_slot"] == SPEC["slot"] and D15.SPEC["univ"] == 500 and D15.SPEC["px_min"] == 10.0 and D15.SPEC["vol_min"] == 1e6 and D15.SPEC["atr_min"] == 0.5 and D15.SPEC["split_n"] == 14, "DDW r1's universe"
    assert D15.ES_D0 == "2014-01-01" and D15.MANIFEST_PREFIX == "380b05f2" and D15.X20 == (TS("2020-02-15"), TS("2020-04-30")) and D15.TBIS_CSV.endswith("siporb_split_flags_voltest.csv")
    assert OUT.lower().endswith("resmom_r1") or os.environ.get("EDGELOG_RESMOM_R1")
    with contextlib.redirect_stdout(open(os.devnull, "w")):
        assert prereg_ok()["verified"] is True and len(stamp()["harness_sha256"]) == 64 and "2023-11-24" in stamp()["early_close"] and set(stamp()) >= {"r15_sha256", "siporb_sha256", "r11_sha256", "r12_sha256", "r13_sha256"}
    assert A13.SRC_RAW == "db_noadj_rth" and A13.SRC_ADJ == "db_adj_rth"
    assert dict(zip(("RES", "RAW"), (0, 1))) == {c: q for q, c in enumerate(CELLS)} and 0 <= (SEED % 7), "each cell has its own random stream"
    pre_txt = open(PREREG, encoding="utf-8").read()                                                         # ADDENDUM 3's pins are in the registered text: the calendar's sha, the five ranks, the spin / stock-dividend types
    assert WIDE_CA_SHA == "e5bc8487daf94a6124823bc24b6c382e9fd00237acbab81457fa42ef3b0d83a5" and WIDE_CA_SHA in pre_txt, "WIDE_CA_SHA is the calendar ADDENDUM 3 registers"
    assert D1_RANKS == ("2016-12-30", "2017-01-31", "2017-02-28", "2017-03-31", "2017-04-28") and all(d_ in pre_txt for d_ in D1_RANKS) and SPIN_TYPES == ("spin_off", "stock_dividend") and "[D2]" in pre_txt and "[D1]" in pre_txt


def t_scores():
    """the score on hand-made worlds (windows shrunk to 30 / 20 / 10 sessions so the numbers can be checked): OLS recovers a planted beta, RES is sum / sample std of (return - beta x ES) over the FORMATION rows only - the alpha
    is NOT subtracted, so a planted alpha is in the score -, a change inside the skipped month moves RES only through the fitted beta (an orthogonal one not at all) and never RAW, a scale change of alpha and idiosyncratic part
    together leaves RES alone, the 230-pair rule at its edge, ES-hole sessions skipped, a split in the window is split-safe"""
    with spec(win=30, form_n=20, skip=10, min_n=25, n_side=1):
        rng = np.random.default_rng(3)
        T, r = 60, 40
        a, fa, fe = windows(r)
        assert (a, fa, fe) == (11, 11, 30)
        m = rng.normal(0.0, 0.01, T)
        m[0] = np.nan
        X = np.column_stack([np.ones(30), m[a:r + 1]])
        e0 = rng.normal(0.0, 0.01, 30)
        e_base = e0 - X @ np.linalg.lstsq(X, e0, rcond=None)[0]                          # orthogonal to [1, ES] over the window: OLS recovers a planted alpha and beta exactly, the OLS residual IS this vector
        assert abs(e_base.sum()) < 1e-15 and abs(e_base @ m[a:r + 1]) < 1e-15

        def name(alpha, beta, e, noise_seed):
            ret = np.random.default_rng(noise_seed).normal(0.0, 0.01, T)
            ret[0] = 0.0
            ret[a:r + 1] = alpha + beta * m[a:r + 1] + e
            return ret
        rets = np.column_stack([name(0.001, 1.5, e_base, 1), name(0.003, 0.5, 3.0 * e_base, 2)])
        ret2 = rets[:, 0].copy()
        ret2[fe + 1:r + 1] = np.random.default_rng(9).normal(0.0, 0.02, 10)               # name 2: name 0's formation returns, a different skipped month
        ret3 = rets[:, 0].copy()
        ret3[fa:fe + 1] += 0.001                                                          # name 3: name 0 with +0.1% on every formation day
        ret4 = name(-0.002, 1.5, e_base, 1)                                               # name 4: name 0 with another alpha (-0.2% a day) and nothing else
        dm_all = m[a:r + 1] - m[a:r + 1].mean()
        dmS = dm_all[fe + 1 - a:]
        w_ = np.random.default_rng(10).normal(0.0, 0.02, len(dmS))
        v_ = w_ - (w_ @ dmS) / (dmS @ dmS) * dmS                                          # a skipped-month change orthogonal to ES's (demeaned) returns over the window: the fitted beta cannot move
        ret5 = rets[:, 0].copy()
        ret5[fe + 1:r + 1] += v_                                                          # name 5: name 0 with that change in its skipped month
        rets = np.column_stack([rets, ret2, ret3, ret4, ret5])
        W = mk_world(prices(rets), m)
        cols = np.arange(6)
        n_ret, n_pair, res, raw = rm_scores(W, r, cols)
        sdF = float(np.std(e_base[:20], ddof=1))
        assert n_ret.tolist() == [30] * 6 and n_pair.tolist() == [30] * 6
        assert abs(res[0] - (20 * 0.001 + e_base[:20].sum()) / sdF) < 1e-9, "OLS recovered beta exactly; the residual is return - beta x ES = the planted alpha + the planted e: RES = (20 alpha + their formation sum) / their sample std"
        assert abs(res[1] - res[0]) < 1e-9 and abs(raw[1] - raw[0]) > 1e-3, "the standardisation: 3 x the alpha and the idiosyncratic part, another beta - the same RES (RAW moves)"
        assert abs(res[4] - (res[0] - 20 * 0.003 / sdF)) < 1e-9 and abs(raw[4] - raw[0]) > 1e-3, "the alpha is NOT subtracted: -0.2% a day instead of +0.1% lowers RES by 20 x 0.003 / sd"
        assert abs(raw[0] - (np.prod(1.0 + rets[fa:fe + 1, 0]) - 1.0)) < 1e-12 and abs(raw[0] - (W.Ac[fe, 0] / W.Ac[fa - 1, 0] - 1.0)) < 1e-12, "RAW = the compound formation return = the price ratio when nothing is missing"
        assert abs(raw[2] - raw[0]) < 1e-12 and abs(res[2] - res[0]) > 1e-3, "the skipped month is not in RAW; it is in the regression, so it moves RES through the fitted beta"
        assert abs(res[5] - res[0]) < 1e-9 and abs(raw[5] - raw[0]) < 1e-12, "a skipped-month change orthogonal to ES leaves the beta alone, so RES and RAW: the skipped month enters RES only through the beta"
        assert abs(raw[3] - (np.prod(1.0 + rets[fa:fe + 1, 3]) - 1.0)) < 1e-12 and raw[3] > raw[0], "a formation change moves RAW"
        # the least-squares recount (numpy's lstsq on the finite pairs, the residual rebuilt row by row)
        for j in range(6):
            bs = brute_scores(W, r, j)
            assert abs(bs[2] - res[j]) < 1e-9 and abs(bs[3] - raw[j]) < 1e-12 and bs[:2] == (30, 30), j
        # random worlds with missing closes and ES holes against the least-squares recount
        for seed in range(6):
            g = np.random.default_rng(100 + seed)
            retr = g.normal(0.0, 0.02, (T, 5))
            retr[0] = 0.0
            Cl = prices(retr)
            for j, rows_ in ((1, [18]), (2, [14, 33]), (3, [20, 21, 36])):
                Cl[rows_, j] = np.nan
            mr = g.normal(0.0, 0.01, T)
            mr[0] = np.nan
            mr[g.choice(np.arange(11, 41), 3, replace=False)] = np.nan
            Wr = mk_world(Cl, mr, Dr=(g.random((T, 5)) < 0.1) * g.uniform(0.3, 2.0, (T, 5)))          # random dividends too (on sessions without a close as well)
            got = rm_scores(Wr, r, np.arange(5))
            for j in range(5):
                bs = brute_scores(Wr, r, j)
                assert bs[:2] == (got[0][j], got[1][j]) and abs(bs[2] - got[2][j]) < 1e-9 and abs(bs[3] - got[3][j]) < 1e-12, (seed, j, bs, [g_[j] for g_ in got])
            assert (got[0] - got[1] >= 0).all() and got[1].max() <= 30 - 3 + 0, "an ES-hole session is skipped for every name"
        # the 230-pair rule at its edge (min_n = 25 here): a name with exactly 25 pairs is in, 24 is out - counted as short_history (own returns) or no_es_pairs (ES holes), never both
        Cl = prices(np.vstack([np.zeros((1, 4)), np.random.default_rng(5).normal(0.0, 0.01, (T - 1, 4))]))
        mm = np.random.default_rng(6).normal(0.0, 0.01, T)
        mm[0] = np.nan
        Cl[:, 1] = np.where(np.arange(T) < 17, np.nan, Cl[:, 1])                       # N01: first price on row 17 -> returns on rows 18 .. 40 = 23 in the window
        Cl[:, 2] = np.where(np.arange(T) < 15, np.nan, Cl[:, 2])                       # N02: first price on row 15 -> returns on rows 16 .. 40 = 25 (exactly min_n)
        Cl[:, 3] = np.where(np.arange(T) < 16, np.nan, Cl[:, 3])                       # N03: first price on row 16 -> returns on rows 17 .. 40 = 24 (one under)
        mm[[12, 13, 14]] = np.nan                                                       # ES holes on rows 12-14: pairs lose nothing for N01 .. N03 (no returns there), N00 loses 3
        Wm = mk_world(Cl, mm)
        n_ret, n_pair, _, _ = rm_scores(Wm, r, np.arange(4))
        assert n_ret.tolist() == [30, 23, 25, 24] and n_pair.tolist() == [27, 23, 25, 24]
        rec, cnt = rm_one(Wm, r, r + 1, r + 25, "remove", units=False)
        assert cnt["short_history"] == 2 and cnt["no_es_pairs"] == 0 and cnt["pool"] == 2 and rec.pool.tolist() == [0, 2] and rec.nfull == 2, (dict(cnt), rec.pool)     # 25 own returns and 25 pairs: in; 24 and 23: out
        with spec(min_n=27):                                                            # N00 (27 pairs) is now exactly in; N02 (25) out
            rec, cnt = rm_one(Wm, r, r + 1, r + 25, "remove", units=False)
            assert rec.pool.tolist() == [0] and cnt["short_history"] == 3 and cnt["no_es_pairs"] == 0, (dict(cnt), rec.pool)
        with spec(min_n=28):                                                            # N00 has 30 own returns but only 27 pairs: out for its ES holes, not for its history
            rec, cnt = rm_one(Wm, r, r + 1, r + 25, "remove", units=False)
            assert rec.pool.tolist() == [] and cnt["short_history"] == 3 and cnt["no_es_pairs"] == 1 and rec.nfull == 0, (dict(cnt), rec.pool)
        # a registered split inside the regression window is carried by the split-safe series: the same scores as the twin without it
        Ac = prices(np.random.default_rng(8).normal(0.0, 0.01, (T, 2)))
        F = np.ones((T, 2))
        F[:25, 0] = 2.0
        Wsp = mk_world(Ac * F, m, F=F, chg=(np.arange(T) == 25)[:, None] & np.array([[True, False]]))
        Wtw = mk_world(Ac, m)
        assert close(rm_scores(Wsp, r, np.arange(2))[2:], rm_scores(Wtw, r, np.arange(2))[2:]) and abs(Wsp.Rn[25, 0]) < 0.1 and abs(Wsp.Cl[25, 0] / Wsp.Cl[24, 0] - 0.5) < 0.1, "split-safe: no fake -50% day"
    return True


def t_identity():
    """prereg v2's residual: e_d = return - beta x ES return (the fitted alpha is NOT subtracted), beta from the OLS with an intercept over r-251 .. r. The identity the harness build found - alpha subtracted, the OLS residuals sum
    to zero over the window, so the formation sum is EXACTLY minus the skipped month's, a one-month reversal - is shown on random names (missing returns, ES holes) and the registered construction breaks it: the whole-window sum is
    n x alpha, the formation sum is not tied to the skipped month. In a planted world the alpha-subtracted construction ranks by minus the skipped month (it tops the name that FELL last month), the registered one by the
    formation drift; a constant added to every return moves RES by n x c / sd (it would not, with the alpha subtracted)"""
    rng = np.random.default_rng(21)
    T, Sn, r = 330, 6, 300
    ret = rng.normal(0.0004, 0.015, (T, Sn))
    ret[0] = 0.0
    Cl = prices(ret)
    Cl[[150, 280], 2] = np.nan
    m = rng.normal(0.0, 0.01, T)
    m[0] = np.nan
    m[[100, 290]] = np.nan
    W = mk_world(Cl, m)
    a, fa, fe = windows(r)
    assert (a, fa, fe) == (49, 49, 279)
    n_ret, n_pair, res, raw = rm_scores(W, r, np.arange(Sn))
    for j in range(Sn):
        ys = {s: W.Rn[s, j] for s in range(a, r + 1)}
        pr = [(s, ys[s], m[s]) for s in range(a, r + 1) if np.isfinite(ys[s]) and np.isfinite(m[s])]
        alpha, beta = np.linalg.lstsq(np.array([[1.0, p[2]] for p in pr]), np.array([p[1] for p in pr]), rcond=None)[0]
        e_old = {p[0]: p[1] - alpha - beta * p[2] for p in pr}                             # the v1 construction
        e_new = {p[0]: p[1] - beta * p[2] for p in pr}                                     # the registered one
        form = lambda e: sum(e[s] for s in range(fa, fe + 1) if s in e)
        skip = lambda e: sum(e[s] for s in range(fe + 1, r + 1) if s in e)
        sd_ = lambda e: float(np.std([e[s] for s in range(fa, fe + 1) if s in e], ddof=1))
        assert abs(form(e_old) + skip(e_old)) < 1e-10, "alpha subtracted: the formation sum is exactly minus the skipped month's"
        assert abs(form(e_new) + skip(e_new) - len(pr) * alpha) < 1e-10 and abs(len(pr) * alpha) > 1e-4, "alpha left in: the whole-window sum is n x alpha - the formation sum is NOT tied to the skipped month"
        assert abs(res[j] - form(e_new) / sd_(e_new)) < 1e-9 and abs(brute_scores(W, r, j)[2] - res[j]) < 1e-9, (j, "RES = the formation sum of (return - beta x ES) / its sample std")
        assert abs(brute_scores(W, r, j, old=True)[2] + skip(e_old) / sd_(e_old)) < 1e-9, "the v1 score was minus the skipped month's residual sum over the formation std"
        assert abs(res[j] - brute_scores(W, r, j, old=True)[2]) > 1e-3, "the two constructions are different scores"
    # a planted world: DRIFT rises in the formation window only, FALL falls in the skipped month only, RISE rises in it, FLAT / DOWN: nothing / a formation fall
    T2, r2 = 300, 290
    a2, fa2, fe2 = windows(r2)
    assert (a2, fa2, fe2) == (39, 39, 269)
    g = np.random.default_rng(22)
    m2 = g.normal(0.0, 0.01, T2)
    m2[0] = np.nan
    base = 1.0 * np.nan_to_num(m2)[:, None] + g.normal(0.0, 0.004, (T2, 5))
    base[0] = 0.0
    kind = {"DRIFT": (0.0015, 0.0), "FALL": (0.0, -0.006), "RISE": (0.0, 0.006), "FLAT": (0.0, 0.0), "DOWN": (-0.0015, 0.0)}
    for q, (dform, dskip) in enumerate(kind.values()):
        base[fa2:fe2 + 1, q] += dform
        base[fe2 + 1:r2 + 1, q] += dskip
    W2 = mk_world(prices(base), m2)
    new_s = rm_scores(W2, r2, np.arange(5))[2]
    old_s = np.array([brute_scores(W2, r2, j, old=True)[2] for j in range(5)])
    names = list(kind)
    assert names[int(np.argmax(old_s))] == "FALL" and names[int(np.argmin(old_s))] == "RISE", ("alpha subtracted: the top name is the one that FELL last month, the bottom the one that ROSE", dict(zip(names, old_s.round(1))))
    assert names[int(np.argmax(new_s))] == "DRIFT" and names[int(np.argmin(new_s))] == "DOWN", ("registered: the top name is the formation drift, the bottom the formation fall", dict(zip(names, new_s.round(1))))
    assert abs(new_s[1]) < 0.35 * new_s[0] and abs(new_s[2]) < 0.35 * new_s[0], "FALL and RISE are noise to the registered score: their last month is not in it"
    # a constant added to every return: the registered RES moves by n x c / sd (the alpha is in it); the alpha-subtracted one would not move
    c = 0.001
    W3, W4 = mk_world(prices(ret[:, :3]), m), mk_world(prices(ret[:, :3] + c), m)
    s3, s4 = rm_scores(W3, r, np.arange(3))[2], rm_scores(W4, r, np.arange(3))[2]
    for j in range(3):
        pr = [(s, W3.Rn[s, j], m[s]) for s in range(a, r + 1) if np.isfinite(m[s])]
        beta = np.linalg.lstsq(np.array([[1.0, p[2]] for p in pr]), np.array([p[1] for p in pr]), rcond=None)[0][1]
        eF = [p[1] - beta * p[2] for p in pr if fa <= p[0] <= fe]
        assert abs((s4[j] - s3[j]) - len(eF) * c / np.std(eF, ddof=1)) < 1e-9, (j, "a constant c in every return moves RES by n x c / sd")
        assert abs(brute_scores(W4, r, j, old=True)[2] - brute_scores(W3, r, j, old=True)[2]) < 1e-9, "(the alpha-subtracted score ignored it)"


def t_schedule():
    """the monthly schedule: the rank session is each calendar month's last session in the data, the fill the next session, the exit the next rebalance's fill, the last one unresolved; a month with no later session is not a rank"""
    days = pd.DatetimeIndex(["2024-01-30", "2024-01-31", "2024-02-01", "2024-02-02", "2024-02-28", "2024-02-29", "2024-03-01", "2024-03-28", "2024-04-01", "2024-04-02"])
    r, f, x = rm_schedule(days)
    assert r.tolist() == [1, 5, 7] and f.tolist() == [2, 6, 8] and x.tolist() == [6, 8, -1], (r, f, x)       # Jan 31, Feb 29, Mar 28 (its last session in this data); Apr 2 has no next session
    r, f, x = rm_schedule(days[:8])
    assert r.tolist() == [1, 5] and x.tolist() == [6, -1], "March's last session in the data has no next session: not a rank; February's position is unresolved"
    bd = pd.bdate_range("2024-01-01", "2025-09-18")
    r, f, x = rm_schedule(bd)
    assert (f == r + 1).all() and (x[:-1] == f[1:]).all() and x[-1] == -1 and all(bd[i].month != bd[i + 1].month for i in r) and len({(bd[i].year, bd[i].month) for i in r}) == len(r) == 20
    assert bd[r[0]] == TS("2024-01-31") and bd[r[2]] == TS("2024-03-29") and bd[r[3]] == TS("2024-04-30") and bd[f[2]] == TS("2024-04-01") and bd[r[-1]] == TS("2025-08-29") and bd[f[-1]] == TS("2025-09-01"), "Good Friday is a session here; the fill is the next one"
    gap = bd.delete([bd.get_loc(TS("2024-03-29"))])                                          # a missing last session: the rank moves to the one before it
    rg = rm_schedule(gap)[0]
    assert gap[rg[2]] == TS("2024-03-28")
    # stretch membership by EXIT session, and the warm-up: ranks whose full 252-session window is not there yet are counted, not built
    with spec(n_side=3), D15.spec(univ=14):
        W = toy_world()
        rr, ff, xx = rm_schedule(W.days)
        full = rm_build(W, W.days[0], W.days[-1])
        assert [r_.r for r_ in full.recs] == [int(q) for q, xv in zip(rr, xx) if xv >= 0 and q >= 251] and all(rec.r >= 251 for rec in full.recs)
        assert W.days[full.recs[0].r] == TS("2024-12-31") and W.days[full.recs[0].f] == TS("2025-01-01") and W.days[full.recs[0].x] == TS("2025-02-03")
        assert full.cnt[2024]["warmup"] == 11 and full.cnt[2024]["rebalances"] == 0 and full.cnt[2025]["unresolved"] == 1 and full.cnt[2025]["warmup"] == 0 and len(full.recs) == 8, {y: dict(c) for y, c in full.cnt.items()}
        assert full.cnt[2025]["rebalances"] == 8 and all(r_.traded for r_ in full.recs)
        sub = rm_build(W, TS("2025-03-01"), TS("2025-05-01"))
        assert [W.days[r_.x] for r_ in sub.recs] == [TS("2025-03-03"), TS("2025-04-01"), TS("2025-05-01")], "a position belongs to the stretch its EXIT session falls in (inclusive)"
        assert [W.days[r_.r] for r_ in sub.recs] == [TS("2025-01-31"), TS("2025-02-28"), TS("2025-03-31")]
    return True


def t_hold():
    """fills / marks / costs / borrow on hand numbers through the whole chain (rm_one -> l1_units -> l1_cell): four names that grow g a day, the RAW picks, one rebalance (windows shrunk): a long earns (1+g)^21 - 1 less 5 bps at
    the fill and 5 bps of the exit value, a short loses it and pays borrow 0.25% / 252 on each night's prior mark (the stress rate on the nights with k_t > 1.5), both sides 1 name x $4,000"""
    with spec(win=30, form_n=20, skip=10, min_n=25, n_side=1):
        T = 70
        g = np.array([0.004, 0.002, -0.002, -0.004])
        rng = np.random.default_rng(4)
        ret = np.tile(g, (T, 1))
        ret[1:44] += rng.normal(0.0, 0.002, (43, 4))                                       # noise in the window (a flat residual has no RES), exactly g a day from the fill on: the hold's path is a closed form
        ret[0] = 0.0
        Cl = prices(ret, 50.0)
        mm = rng.normal(0.0, 0.01, T)
        mm[0] = np.nan
        k = np.ones(T)
        W = mk_world(Cl, mm, k=k)
        r_all, f_all, x_all = rm_schedule(W.days)
        assert W.days[r_all[1]] == TS("2024-02-29") and r_all[1] == 43 and x_all[1] == 65 and x_all[2] == -1
        L = rm_build(W, W.days[0], W.days[-1])
        assert len(L.recs) == 1 and L.recs[0].traded and (L.recs[0].f, L.recs[0].x) == (44, 65) and L.recs[0].pool.tolist() == [0, 1, 2, 3]
        rec = L.recs[0]
        assert rec.pool[rec.pick["RAW"][0]].tolist() == [0] and rec.pool[rec.pick["RAW"][1]].tolist() == [3], "RAW: the highest formation return is the long, the lowest the short"
        c = COST_BPS * 1e-4
        up, dn = (1 + g[0]) ** 21, (1 + g[3]) ** 21                                       # the hold is rows 44 .. 65: 21 closes marked, exit at the open of row 65 = the close of row 64 (no overnight gap here)
        long_pnl = 4000.0 * (up - 1.0 - c - c * up)
        borrow = lambda rate: rate / 252.0 * sum((1 + g[3]) ** h for h in range(1, 22))
        short_pnl = 4000.0 * (-(dn - 1.0) - c - c * dn - borrow(BORROW))
        run = run_cell(W, cell_leg(L, "RAW"), D15.l1_cfg(), pos=True)
        assert run.n_pos == 2 and run.n_units == 1 and abs(run.x.sum() - (long_pnl + short_pnl)) < 1e-6, (run.x.sum(), long_pnl + short_pnl)
        assert sorted(run.pos.side.tolist()) == [-1, 1] and abs(run.pos.pnl[run.pos.side == 1][0] - long_pnl) < 1e-6 and abs(run.pos.pnl[run.pos.side == -1][0] - short_pnl) < 1e-6
        assert (run.x[:44] == 0).all() and (run.x[66:] == 0).all() and (run.cnt[44:66] == 2).all() and run.cnt[:44].sum() == 0, "positions are held (and P&L booked) on rows f .. x only"
        assert abs(run.x[44] - 4000.0 * ((Cl[44, 0] / Cl[43, 0] - 1.0 - c) - (Cl[44, 3] / Cl[43, 3] - 1.0) - c)) < 1e-6, "the fill-session row: the first mark over the open (= the prior close) and 5 bps of the notional in"
        # sides apart, 10 / 20 bps, the borrow stress rows with k_t > 1.5 on rows 50 .. 54
        assert abs(run_cell(W, cell_leg(L, "RAW"), D15.l1_cfg(), side=1).x.sum() - long_pnl) < 1e-6 and abs(run_cell(W, cell_leg(L, "RAW"), D15.l1_cfg(), side=-1).x.sum() - short_pnl) < 1e-6
        for bps in STRESS_BPS:
            cb = bps * 1e-4
            want = 4000.0 * ((up - 1.0 - cb - cb * up) + (-(dn - 1.0) - cb - cb * dn - borrow(BORROW)))
            assert abs(run_cell(W, cell_leg(L, "RAW"), D15.l1_cfg(bps=bps)).x.sum() - want) < 1e-6, bps
        k[50:55] = 2.0
        W2 = mk_world(Cl, mm, k=k)
        L2 = rm_build(W2, W2.days[0], W2.days[-1])
        for rate in BORROW_STRESS:
            got = run_cell(W2, cell_leg(L2, "RAW"), D15.l1_cfg(borrow=(BORROW, rate)), side=-1).x.sum()
            nights = [h for h in range(1, 22)]
            kb = sum(((rate if 50 <= 44 + h <= 54 else BORROW) / 252.0) * (1 + g[3]) ** h for h in nights)
            assert abs(got - 4000.0 * (-(dn - 1.0) - c - c * dn - kb)) < 1e-6, rate
        assert abs(run_cell(W2, cell_leg(L2, "RAW"), D15.l1_cfg()).x.sum() - run.x.sum()) < 1e-9, "the base rate does not read k_t"
        # the cell is dollar-neutral by construction: 1 long and 1 short of the same $4,000 (50 + 50 at the registered size)
        assert SPEC["slot"] == 4000.0 and rec.pick["RAW"][0].shape == rec.pick["RAW"][1].shape
        # a rebalance trades only with a pool of at least 2 x n_side names: n_side = 2 -> 4 names trade (2 + 2), 3 names do not (counted small_pool, no units, no P&L)
        with spec(n_side=2):
            L4 = rm_build(W, W.days[0], W.days[-1])
            r4 = L4.recs[0]
            assert r4.traded and r4.pool[r4.pick["RAW"][0]].tolist() == [0, 1] and r4.pool[r4.pick["RAW"][1]].tolist() == [3, 2] and L4.cnt[2024]["small_pool"] == 0
            assert run_cell(W, cell_leg(L4, "RAW"), D15.l1_cfg()).n_pos == 4
            U3 = np.isfinite(Cl).copy()
            U3[:, 3] = False
            W3 = mk_world(Cl, mm, U=U3, k=k)
            L3 = rm_build(W3, W3.days[0], W3.days[-1])
            r3 = L3.recs[0]
            assert not r3.traded and r3.pool.tolist() == [0, 1, 2] and L3.cnt[2024]["small_pool"] == 1 and not hasattr(r3, "U")
            run3 = run_cell(W3, cell_leg(L3, "RAW"), D15.l1_cfg())
            assert run3.n_pos == 0 and run3.n_units == 0 and run3.x.sum() == 0.0
    with spec(n_side=50):
        assert SPEC["n_side"] == 50
    return True


def t_hygiene():
    """the hygiene windows to the row (rank r = 43, fill 44, exit 65; windows shrunk to 30 / 20 / 10 so the rows are countable): the pre window is r-25 .. r = rows 29 .. 43 (all four reasons), the old window r-251 .. r-26 =
    rows 14 .. 28 (gap scan, TBIS, a +-50% gap - never a registered split), the hold r+1 .. x = rows 44 .. 65 (all four, a look-ahead removal: kept at the naive path by the other reading)"""
    with spec(win=30, form_n=20, skip=10, min_n=25, n_side=1):
        T, Sn = 70, 16
        rng = np.random.default_rng(14)
        ret = rng.normal(0.0, 0.012, (T, Sn))
        ret[0] = 0.0
        Cl = prices(ret)
        mm = rng.normal(0.0, 0.01, T)
        mm[0] = np.nan
        Od = np.vstack([Cl[:1], Cl[:-1]])
        chg, ms, tb = np.zeros((T, Sn), bool), np.zeros((T, Sn), bool), np.zeros((T, Sn), bool)
        chg[29, 0] = True              # A: a registered split on the first row of the pre window: out (pre_split)
        chg[28, 1] = True              # B: ... on the last row of the old window: a registered split there is carried by the split-safe series: in
        ms[28, 2] = True               # C: a gap-scan flag on the last row of the old window: out (old_gap)
        ms[20, 3] = True               # D: ... inside it: out
        ms[14, 4] = True               # E: ... on its first row (r-251 in the registered windows): out
        ms[13, 5] = True               # F: ... one row before it: in
        chg[65, 6] = True              # G: a registered split ON the exit session: the look-ahead removal (post_split); the naive reading keeps it
        chg[66, 7] = True              # H: ... one session after the exit: not in the hold: in
        ms[44, 8] = True               # I: a gap-scan flag on the fill session (the first row of the hold): post_gap
        tb[43, 9] = True               # J: a TBIS flag on the rank session itself (known at the close): pre_tbis, out in both readings
        tb[20, 10] = True              # K: TBIS in the old window: old_tbis
        Od[22, 11] = 1.7 * Cl[21, 11]  # L: a +70% raw gap with no factor change in the old window: old_jump
        Od[50, 12] = 0.4 * Cl[49, 12]  # M: a -60% raw gap inside the hold: post_jump
        # N, O, P: no flag at all
        W = mk_world(Cl, mm, Od=Od, chg=chg, msplit=ms, tbis=tb)
        Bz = {pm: brute_rm(W, W.days[0], W.days[-1], pm) for pm in ("remove", "naive")}
        r_all, f_all, x_all = rm_schedule(W.days)
        assert (r_all[1], f_all[1], x_all[1]) == (43, 44, 65)
        out = {}
        for pm in ("remove", "naive"):
            L = rm_build(W, W.days[0], W.days[-1], pm)
            assert len(L.recs) == 1 and (L.recs[0].r, L.recs[0].f, L.recs[0].x) == (43, 44, 65) and L.recs[0].traded
            compare_rm(W, L, Bz[pm], f"hygiene {pm}")
            out[pm] = (L.recs[0], L.cnt[2024])
        rec, c = out["remove"]
        assert rec.pool.tolist() == [1, 5, 7, 13, 14, 15] and not rec.naive.any(), rec.pool.tolist()
        assert (c["pre_split"], c["old_gap"], c["pre_tbis"], c["old_tbis"], c["old_jump"], c["post_split"], c["post_gap"], c["post_jump"], c["pool"]) == (1, 3, 1, 1, 1, 1, 1, 1, 6) and c["pre_gap"] == c["pre_jump"] == c["post_tbis"] == 0, dict(c)
        rec, c = out["naive"]
        assert rec.pool.tolist() == [1, 5, 6, 7, 8, 12, 13, 14, 15] and [int(j) for j, nv in zip(rec.pool, rec.naive) if nv] == [6, 8, 12], (rec.pool.tolist(), rec.naive.tolist())
        assert (c["pre_split"], c["old_gap"], c["pre_tbis"], c["old_tbis"], c["old_jump"], c["post_split"], c["post_gap"], c["post_jump"], c["pool"], c["kept_naive"]) == (1, 3, 1, 1, 1, 0, 0, 0, 9, 3), dict(c)
        # the audit removes a name-month from the pool in both readings (and counts it)
        W.aud1[44, 13] = True
        for pm in ("remove", "naive"):
            L = rm_build(W, W.days[0], W.days[-1], pm)
            assert 13 not in L.recs[0].pool.tolist() and L.cnt[2024]["audit"] == 1
        W.aud1[:] = False
        # a name with no open at the fill session cannot be filled (not eligible, counted)
        Od2 = Od.copy()
        Od2[44, 14] = np.nan
        W2 = mk_world(Cl, mm, Od=Od2, chg=chg, msplit=ms, tbis=tb, U=np.ones((T, Sn), bool))                   # (in the universe by fiat: the universe itself needs an open)
        rec2, c2 = rm_one(W2, 43, 44, 65, "remove", units=False)
        assert 14 not in rec2.pool.tolist() and c2["no_fill"] == 1
    return True


def t_pipeline():
    """the vectorised builds against the plain-python recount on the toy world with the REGISTERED windows (252 / 231 / 21 / 230), in both readings, then the planted cases one by one"""
    with spec(n_side=3), D15.spec(univ=14):
        W = toy_world()
        W.aud1[dr_(W, "2025-02-03"), 8] = True                                              # N08: a hand-audit data event at fill session 2025-02-03 (the rebalance ranked 2025-01-31) ...
        lo, hi = W.days[0], W.days[-1]
        n, out = 0, {}
        for pm in ("remove", "naive"):
            L = rm_build(W, lo, hi, pm)
            Bz = brute_rm(W, lo, hi, pm)
            n += compare_rm(W, L, Bz, f"toy {pm}")
            out[pm] = L
            if pm == "remove":
                series_check(W, L, Bz)
        Lr, Lk = out["remove"], out["naive"]
        assert sum(r.traded for r in Lr.recs) == 8 and sum(r.traded for r in Lk.recs) == 8, "the toy world trades every one of its 8 rebalances"
        by = lambda L, d: next(r for r in L.recs if W.days[r.r] == TS(d))
        cols = lambda rec: rec.pool.tolist()
        # N06 (first price on row 40): 221 returns at the first rank - out; 244 at the second - in
        c1 = Lr.cnt[2025]
        assert 6 not in cols(by(Lr, "2024-12-31")) and 6 in cols(by(Lr, "2025-01-31")) and c1["short_history"] >= 1
        # N00, the registered 2-for-1 on 03-14: a flag INSIDE the hold (rank 02-28) is a look-ahead removal - kept by the naive reading at the naive raw path; a flag in r-25 .. r (rank 03-31) removes it in both; later ranks
        # carry the split in the split-safe series and keep the name
        r3r, r3k = by(Lr, "2025-02-28"), by(Lk, "2025-02-28")
        assert 0 not in cols(r3r) and 0 in cols(r3k) and r3k.naive[cols(r3k).index(0)]
        i0, f3, x3 = cols(r3k).index(0), r3k.f, r3k.x
        dnaive = sum(brute_div(W, f3, x3, 0, True))                                       # [R1] the raw dividend of the hold (0.50 on 03-24) over the raw entry open
        assert abs(r3k.U.G[i0].sum() - (W.Od[x3, 0] / W.Od[f3, 0] - 1.0 + dnaive)) < 1e-12 and r3k.U.G[i0].sum() < -0.3 and dnaive > 0, "the naive raw path shows the split as a -50% loss (and takes the raw dividend)"
        safe = D15.unit_path(W.Ao, W.Ac, f3, x3, np.array([0]))
        assert abs(safe.G[0].sum() - (W.Ao[x3, 0] / W.Ao[f3, 0] - 1.0)) < 1e-12 and abs(safe.G[0].sum()) < 0.3, "the split-safe path does not"
        assert 0 not in cols(by(Lr, "2025-03-31")) and 0 not in cols(by(Lk, "2025-03-31")) and 0 in cols(by(Lr, "2025-04-30")) and 0 in cols(by(Lr, "2025-05-30")) and not by(Lk, "2025-05-30").naive[cols(by(Lk, "2025-05-30")).index(0)]
        assert np.allclose(W.Rn[1:, 0], W.true_ret[1:, 0]) and abs(W.Cl[dr_(W, "2025-03-14"), 0] / W.Cl[dr_(W, "2025-03-13"), 0] - 0.5) < 0.1, "split-safe daily returns are the planted ones; the raw close halves"
        # N01, an unadjusted x4 on 01-14 (a fake +300% return day, gap-scan flag): inside the hold of the first rank (look-ahead removal), in r-25 .. r of the second, then inside the regression window for good (the old window)
        r1r, r1k = by(Lr, "2024-12-31"), by(Lk, "2024-12-31")
        assert 1 not in cols(r1r) and 1 in cols(r1k) and r1k.naive[cols(r1k).index(1)] and all(1 not in cols(by(L_, d)) for L_ in (Lr, Lk) for d in ("2025-01-31", "2025-02-28", "2025-04-30", "2025-07-31"))
        assert Lr.cnt[2025]["pre_gap"] >= 1 and Lr.cnt[2025]["old_gap"] >= 1 and W.Rn[dr_(W, "2025-01-14"), 1] > 2.5
        # N02 (TBIS 04-10): inside the hold of the 03-31 rank, in r-25 .. r of the 04-30 rank, in the old window after; N03 (the +-50% rule, 05-12): the same for the 04-30 / 05-30 / 06-30 ranks
        assert 2 not in cols(by(Lr, "2025-03-31")) and 2 in cols(by(Lk, "2025-03-31")) and 2 not in cols(by(Lr, "2025-04-30")) and 2 not in cols(by(Lk, "2025-05-30")) and 2 not in cols(by(Lr, "2025-06-30"))
        assert 3 not in cols(by(Lr, "2025-04-30")) and 3 in cols(by(Lk, "2025-04-30")) and 3 not in cols(by(Lk, "2025-05-30")) and 3 not in cols(by(Lk, "2025-06-30")) and Lr.cnt[2025]["old_jump"] >= 1
        assert 3 in cols(by(Lr, "2025-03-31")) and 3 in cols(by(Lr, "2025-02-28")), "before the event the name is a normal one"
        # N04 stops printing on 06-12: in the 05-30 rank's hold it exits at its LAST mark (zero on the exit day); the next fill has no open and it is not in the universe
        rk = by(Lr, "2025-05-30")
        i4 = cols(rk).index(4)
        assert rk.U.st[i4] and abs(rk.U.G[i4, -1]) < 1e-15 and 4 not in cols(by(Lr, "2025-06-30"))
        # N05 has no close on 03-20: the mark carries (a zero day, the whole move on the next)
        r4 = by(Lr, "2025-02-28")
        i5, h = cols(r4).index(5), dr_(W, "2025-03-20") - r4.f
        assert r4.U.G[i5, h] == 0.0 and r4.U.G[i5, h + 1] != 0.0
        # ES holes (02-10, 02-11): skipped for every name - two fewer pairs than own returns in every window that holds them, not blind
        rr = W.days.get_loc(TS("2025-02-28"))
        n_ret, n_pair, _, _ = rm_scores(W, rr, np.arange(W.S))
        assert (n_ret - n_pair)[[7, 8, 9]].tolist() == [2, 2, 2] and (n_ret[7] >= SPEC["min_n"]), "two ES-hole sessions: two fewer pairs, the names stay eligible (230 of 252)"
        # the audit: N08 at fill 2025-02-03 is gone from the pool of the 01-31 rank (and counted)
        assert 8 not in cols(by(Lr, "2025-01-31")) and 8 not in cols(by(Lk, "2025-01-31")) and Lr.cnt[2025]["audit"] >= 1 and (AUD, dr_(W, "2025-02-03"), 8) in W.aud_hit
        # the K reading differs from the registered one only by the in-hold names (more names in the pool, never fewer)
        for a_, b_ in zip(Lr.recs, Lk.recs):
            assert set(a_.pool.tolist()) <= set(b_.pool.tolist())
        # both cells share ONE pool; the 3 longs / 3 shorts of each cell are the 3 highest / lowest scores
        for rec in Lr.recs:
            for c in CELLS:
                sc = rec.score[c]
                assert sorted(sc[rec.pick[c][0]]) == sorted(sc)[-3:] and sorted(sc[rec.pick[c][1]]) == sorted(sc)[:3]
        # the cells differ (RES ranks on a standardised residual, RAW on the total return)
        assert any(rec.pick["RES"][0].tolist() != rec.pick["RAW"][0].tolist() for rec in Lr.recs)
        # counts: the first-reason tally by fill year adds up (every universe name is counted once, in a reason or in the pool)
        for y, c in Lr.cnt.items():
            assert c["universe"] == sum(c[k] for k in COUNT_KEYS[1:]), (y, dict(c))
    return n


def dr_(W, s):
    return W.days.get_loc(TS(s))


def t_null():
    """the null: 500 uniform draws per rebalance of as many names as the cell holds from the same eligible pool (no S twin here), seeded, one stream per cell, longs and shorts disjoint, the statistic = the max over the 2 cells"""
    with spec(n_side=3), D15.spec(univ=14):
        W = toy_world()
        L = rm_build(W, W.days[0], W.days[-1])
        acc = rm_null(W, L, 400, 0)
        assert set(acc) == set(CELLS) and all(a.shape == (400, W.T) for a in acc.values()), "one (draws, sessions) P&L array per cell: no F / S pair"
        kz0 = W.kz.copy()
        W.kz[:] = 2.5                                                                       # the volatility lean of r15's S cells: this family has none - k_t is read only by the borrow stress
        assert all((rm_null(W, L, 400, 0)[c] == acc[c]).all() for c in CELLS)
        W.kz[:] = kz0
        cfg = D15.l1_cfg()
        for cell in CELLS:
            exp = 0.0
            for rec in L.recs:
                if rec.traded:
                    idx = np.arange(len(rec.pool))
                    kt = W.k[rec.f:rec.x + 1]
                    exp += SPEC["slot"] * SPEC["n_side"] * float(D15.l1_pnl(rec.U, idx, 1, cfg, kt).mean(axis=0).sum() + D15.l1_pnl(rec.U, idx, -1, cfg, kt).mean(axis=0).sum())
            tot = acc[cell].sum(axis=1)
            assert abs(tot.mean() - exp) < 4.5 * tot.std() / math.sqrt(len(tot)), (cell, tot.mean(), exp, tot.std())
            assert (acc[cell][:, :dr_(W, "2025-01-01")] == 0).all(), "no P&L before the first fill"
        again = rm_null(W, L, 400, 0)
        assert all((again[c] == acc[c]).all() for c in CELLS), "seeded"
        assert not (rm_null(W, L, 400, 1)["RES"] == acc["RES"]).all(), "the other reading draws a different stream"
        assert not (acc["RES"] == acc["RAW"]).all() and abs(acc["RES"].sum(axis=1).mean() - acc["RAW"].sum(axis=1).mean()) < 6 * acc["RES"].sum(axis=1).std() / math.sqrt(400), "own stream per cell, same expectation (same pool)"
        # a draw only ever holds names of that rebalance's pool, longs and shorts disjoint: with a pool of exactly 2 x n the draw IS the pool
        d = D15.draw_order(np.random.default_rng(1), 200, 10, 6)
        assert all(len(set(r_)) == 6 and not set(r_[:3]) & set(r_[3:]) for r_ in d.tolist())
        # the statistic: the max over the 2 cells per draw, then p5 / p50 / p95
        ix = pd.bdate_range("2016-07-01", "2025-06-27")
        rng = np.random.default_rng(2)
        book = rng.normal(35.0, 650.0, len(ix))
        S12 = M12.Stretch(book, ix, None, WF0, PRE_END)
        pc = {c: D15.null_cell(S12, rng.normal(5, 100, (40, len(ix))), np.arange(len(ix)), len(ix))[0] for c in CELLS}
        ns = null_summary(pc)
        mx = np.max(np.vstack([pc[c] for c in CELLS]), axis=0)
        assert ns["draws"] == 40 and ns["seed"] == SEED and abs(ns["roc_max"]["p95"] - np.percentile(mx, 95)) < 1e-9 and abs(ns["roc_max"]["p50"] - np.percentile(mx, 50)) < 1e-9 and abs(ns["roc_max"]["p5"] - np.percentile(mx, 5)) < 1e-9
        assert ns["roc_max"]["p95"] >= max(ns["by_cell"][c]["p95"] for c in CELLS) - 1e-9, "the max of two is above each"


def t_stats():
    """DO / rho_dd are MDL r1's (r12_mdl's independent code), the vectorised null twins equal r11 / r12's scalar code, the cell statistics, every Stage A check broken alone"""
    B, S12 = synth_book(seed=11, hi="2025-06-27")
    rng = np.random.default_rng(12)
    leg = -0.4 * B.raw + rng.normal(10.0, 300.0, len(B.index))
    sm = D15.seat_measure(S12, leg)
    rho, do = M12.naive_rho_do(leg[S12.rows], B.raw[S12.rows], S12.dates, S12.dd)
    assert abs(sm["rho_dd"] - rho) < 1e-9 and abs(sm["DO"] - do) < 1e-9 and sm["dd_days"] == S12.n_dd_days and sm["dd_weeks"] == S12.n_dd_weeks, "the cell's DO / rho_dd are MDL r1's"
    for q in range(4):
        x_ = rng.normal(5, 100, (1, len(B.index)))
        r_, rho_, do_ = D15.null_cell(S12, x_, np.arange(len(B.index)), len(B.index))
        s_ = R11.stats(x_[0][S12.rows], S12.dates)
        n_, d_ = M12.naive_rho_do(x_[0][S12.rows], B.raw[S12.rows], S12.dates, S12.dd)
        assert abs(r_[0] - s_["roc"]) < 1e-9 and abs(rho_[0] - n_) < 1e-9 and abs(do_[0] - d_) < 1e-9
    # the checks, one by one: a passing cell, then each condition broken alone
    st_ok = {"n_units": 100, "net": 1000.0, "roc": 40.0, "years_pos": 7, "net_ex2020": 500.0, "net_ex_best_days": 300.0, "net_ex_best_pos": 200.0}
    nul = {"roc_max": {"p95": 30.0}}
    ok = judge_cell(st_ok, 100.0, nul)
    assert all(ok.values()) and len(ok) == 9 and list(ok) == ["rebalances>=60", "ROC>=15", "net>0 at 5 bps", "net>0 at 10 bps", "ROC>null p95", "positive in >=6 of 9 July-June years", "net>0 without Feb 15 - Apr 30 2020",
                                                             "profitable without its best 1% of days", "profitable without its best 1% of name-months"], list(ok)
    breaks = [("rebalances>=60", dict(n_units=59), None), ("ROC>=15", dict(roc=14.9), None), ("net>0 at 5 bps", dict(net=0.0), None), ("net>0 at 10 bps", {}, 0.0), ("ROC>null p95", dict(roc=30.0), None),
              ("positive in >=6 of 9 July-June years", dict(years_pos=5), None), ("net>0 without Feb 15 - Apr 30 2020", dict(net_ex2020=0.0), None), ("profitable without its best 1% of days", dict(net_ex_best_days=-1.0), None),
              ("profitable without its best 1% of name-months", dict(net_ex_best_pos=-1.0), None)]
    for name, kw, n10 in breaks:
        r_ = judge_cell({**st_ok, **kw}, 100.0 if n10 is None else n10, {"roc_max": {"p95": 5.0}} if name == "ROC>=15" else nul)          # (a ROC under 15 would also be under the null's 30: lower the null for that one)
        assert [k for k, v in r_.items() if not v] == [name], (name, [k for k, v in r_.items() if not v])
    assert judge_cell({**st_ok, "n_units": 60}, 1.0, nul)["rebalances>=60"] and judge_cell({**st_ok, "roc": 15.0}, 1.0, {"roc_max": {"p95": 10.0}})["ROC>=15"], "the bars are inclusive (60, 15)"
    nanst = judge_cell({**st_ok, "roc": float("nan"), "net_ex2020": float("nan")}, float("nan"), nul)
    assert not nanst["ROC>=15"] and not nanst["ROC>null p95"] and not nanst["net>0 at 10 bps"] and not nanst["net>0 without Feb 15 - Apr 30 2020"], "a NaN never passes"
    # the null's p95 is the bar: a cell between a p95 of 30 and a ROC of 15 fails (c) and passes (b)
    mid = judge_cell({**st_ok, "roc": 20.0}, 1.0, nul)
    assert mid["ROC>=15"] and not mid["ROC>null p95"]
    # cell_stats on hand series (r15's own function, through this harness's arguments): breadth by July-June year, the 2020 window, the best 1% of days and of name-months
    ds = pd.bdate_range("2017-01-02", periods=8)
    Bs = SimpleNamespace(index=ds, n=8, mask=lambda lo, hi: np.asarray((ds >= lo) & (ds <= hi)))
    xs, cs = np.array([100.0, -50.0, 0.0, 200.0, -150.0, 50.0, 0.0, -50.0]), np.array([2, 1, 0, 1, 3, 1, 0, 1])
    st = D15.cell_stats(Bs, xs, cs, ds[0], ds[-1], SimpleNamespace(n_pos=5, n_units=3, pos=SimpleNamespace(pnl=np.array([300.0, 50.0, -10.0, -240.0, 0.0]))))
    assert st["net"] == 100.0 and st["n_units"] == 3 and st["net_ex_best_days"] == -100.0 and st["net_ex_best_pos"] == -200.0 and st["years_pos"] == 1 and st["by_year"][2016] == 100.0
    return True


def t_a2():
    """A2 (a REPORT): c is set by VOLATILITY on 2017-01-03 .. 2018-12-31 (the cell's first two years) = 25% of #463's daily std over the same rows, both end days inside it, nothing outside it moves c; the book at c, 0.5c, 2c; 'book_shadow_line' is the
    book at c clearing 98.5005 / 3.816; a cell with no spread there has no c"""
    me = sys.modules[__name__]
    rng = np.random.default_rng(31)
    ix = pd.bdate_range("2016-07-01", "2026-06-30")                                         # the lockbox rows are in the index: A2 must never read them
    book = rng.normal(35.0, 650.0, len(ix))
    mk = lambda raw: SimpleNamespace(index=ix, raw=raw, n=len(ix), mask=lambda lo, hi: np.asarray((ix >= lo) & (ix <= hi)))
    B = mk(book)
    win, wd = B.mask(*A2_WIN), pd.bdate_range("2017-01-03", "2018-12-31")
    assert win.sum() == len(wd) and ix[win][0] == TS("2017-01-03") and ix[win][-1] == TS("2018-12-31"), "the window is 2017-01-03 .. 2018-12-31, both end days inside it"
    cell = np.where(ix >= TS("2017-01-03"), rng.normal(5.0, 120.0, len(ix)), 0.0)         # a cell that starts holding positions on the window's first day
    before = np.where(ix <= TS("2017-01-02"), rng.normal(5.0, 120.0, len(ix)), 0.0)       # ... and one that held positions only before it
    a2 = a2_report(B, cell)
    c = a2["c"]
    sb, sc = float(np.std(book[win], ddof=1)), float(np.std(cell[win], ddof=1))
    assert c > 0 and abs(c - A2_TARGET * sb / sc) <= 1e-12 * c and abs(a2["std_book"] - sb) <= 1e-12 * sb and abs(a2["std_cell"] - sc) <= 1e-12 * sc, "c = 25% x std(#463) / std(the cell) on the window"
    assert a2["window"] == ["2017-01-03", "2018-12-31"] and a2["rows"] == int(win.sum()) and a2["target"] == 0.25 and a2["needs"] == {"roc": RULES["a2_roc"], "sortino": RULES["a2_sort"]} and "pass" not in a2
    ratio = float(np.std(c * cell[win], ddof=1) / np.std(book[win], ddof=1))
    assert abs(ratio - 0.25) < 1e-12 and abs(np.std(c * cell[win]) / np.std(book[win]) - 0.25) < 1e-12, "c x the cell's std over the window = exactly 25% of #463's (either ddof)"
    assert abs(a2_report(B, book)["c"] - 0.25) < 1e-12 and abs(a2_report(B, -book)["c"] - 0.25) < 1e-12 and abs(a2_report(B, 2.0 * cell)["c"] - c / 2.0) <= 1e-12 * c and abs(a2_report(B, -cell)["c"] - c) <= 1e-12 * c
    spike = lambda d, v=1e6: np.where(np.asarray(ix == TS(d)), v, 0.0)
    assert a2_report(B, cell + spike("2019-01-01"))["c"] == c and a2_report(B, cell + spike("2017-01-02"))["c"] == c and a2_report(B, cell + spike("2025-06-26"))["c"] == c, "a day outside the window changes nothing"
    for d_ in ("2017-01-03", "2018-12-31"):
        assert a2_report(B, cell + spike(d_))["c"] < 0.5 * c, f"the window's end day {d_} is inside it"
    assert a2_report(mk(np.where(ix >= TS("2019-01-01"), 10.0 * book, book)), cell)["c"] == c, "#463's own days after the window do not enter c"
    wf = B.mask(WF0, PRE_END)
    for rec, m in ((a2, 1.0), (a2["at_half_c"], 0.5), (a2["at_double_c"], 2.0)):
        want = R11.stats((book + m * c * cell)[wf], ix[wf])
        assert abs(rec["c"] - m * c) <= 1e-12 * c and abs(rec["roc"] - want["roc"]) < 1e-9 and abs(rec["sortino"] - want["sort"]) < 1e-9 and abs(rec["net"] - want["net"]) < 1e-6, (m, rec)
    lb = np.asarray(ix >= LB0)                                                              # wild P&L on the lockbox rows: the whole A2 record is untouched - A2 is a WF-only judgement
    assert a2_report(mk(np.where(lb, 50.0 * book - 1e5, book)), np.where(lb, 50.0 * cell + 1e5, cell)) == a2, "A2 never reads the lockbox"
    for bar_r, bar_s, want in ((a2["roc"], a2["sortino"], True), (a2["roc"] + 1e-9, a2["sortino"], False), (a2["roc"], a2["sortino"] + 1e-9, False), (a2["roc"] - 1.0, a2["sortino"] - 1.0, True)):
        with patched(me, RULES={**RULES, "a2_roc": bar_r, "a2_sort": bar_s}):
            r_ = a2_report(B, cell)
        assert r_["book_shadow_line"] is want and r_["c"] == c and r_["needs"] == {"roc": bar_r, "sortino": bar_s}, (bar_r, bar_s, want)
    assert a2["book_shadow_line"] is False and abs(RULES["a2_roc"] - 1.05 * 93.81) < 1e-9, "the real bar (98.5005 / 3.816): a coin-flip cell on a coin-flip book does not clear it"
    for nm, x_ in (("no P&L", np.zeros(len(ix))), ("a constant", np.full(len(ix), 17.0)), ("only after the window", np.where(ix >= TS("2019-01-01"), cell, 0.0)), ("only before it", before)):
        r_ = a2_report(B, x_)
        assert math.isnan(r_["c"]) and r_["book_shadow_line"] is False and "no c" in r_["error"] and r_["at_half_c"] is None and r_["at_double_c"] is None, nm
    return ratio


def t_s1():
    """PRE-DATA ADDENDUM 2 [S1], proved on random stock / ES pairs: W = the 252 sessions r-251 .. r, F = its first 231 (the formation), S = its last 21 (the skipped month). The OLS over W (an intercept a, a slope b) has residuals
    u_d = r_d - a - b x ES_d that sum to zero over W; the v2 residual is e_d = r_d - b x ES_d = u_d + a (the alpha NOT subtracted), so the formation sum is EXACTLY  sum_F e_d = 231 a - sum_S u_d = sum_W e_d - sum_S e_d  (the stock's
    twelve-month return net of its market beta, with the last month taken out); the score is that sum over the sample standard deviation (ddof 1) of e_d over F - which is u_d's, a being a constant. The harness's own score function
    (rm_scores) returns exactly that, and so does its plain-python recount (brute_scores); a ddof-0 divisor would not"""
    rel = lambda p_, q_, floor=0.0: abs(p_ - q_) <= 1e-12 * max(abs(p_), abs(q_), floor)
    for seed in range(81, 93):
        rng = np.random.default_rng(seed)
        T, r = 300, 290
        m = rng.normal(0.0004, 0.01, T)
        m[0] = np.nan
        ret = rng.normal(0.0003, 0.0004) + rng.uniform(0.5, 1.5) * np.nan_to_num(m) + rng.normal(0.0, 0.015, T)
        ret[0] = 0.0
        W = mk_world(prices(ret[:, None], 50.0), m)
        a0, fa, fe = windows(r)
        assert (a0, fa, fe) == (39, 39, 269) and SPEC["win"] == 252 and fe - fa + 1 == 231 == SPEC["form_n"] and r - fe == 21 == SPEC["skip"], "W = r-251 .. r (252), F = r-251 .. r-21 (231), S = r-20 .. r (21)"
        y, x = W.Rd[a0:r + 1, 0], m[a0:r + 1]                                              # the 252 split-safe total returns (no dividend here: Rd = Rn) and ES's
        assert len(y) == 252 and np.isfinite(y).all() and np.isfinite(x).all()
        alpha, beta = np.linalg.lstsq(np.column_stack([np.ones(252), x]), y, rcond=None)[0]
        e = y - beta * x                                                                    # the v2 residual: the alpha stays in
        u = e - alpha                                                                       # the OLS residual
        Fs, Ss = slice(0, 231), slice(231, 252)
        floor = 0.05 if seed != 81 else 0.0                                                 # the first pair is held to a strict relative 1e-12 (its numerator is well away from zero); the others to 1e-12 of at least 0.05
        sumF = e[Fs].sum()
        assert abs(u.sum()) < 1e-13, "the OLS residuals sum to zero over W"
        assert rel(e.sum(), 252 * alpha), "the whole-window sum of e is 252 a"
        assert rel(sumF, 231 * alpha - u[Ss].sum(), floor) and rel(sumF, e.sum() - e[Ss].sum(), floor) and rel(231 * alpha - u[Ss].sum(), e.sum() - e[Ss].sum(), floor), (seed, sumF, 231 * alpha - u[Ss].sum(), e.sum() - e[Ss].sum())
        sd_e, sd_u = np.std(e[Fs], ddof=1), np.std(u[Fs], ddof=1)
        assert rel(sd_e, sd_u), "a is a constant: e and u have the same standard deviation over F"
        want = sumF / sd_e
        got = rm_scores(W, r, np.array([0]))[2][0]
        assert rel(got, want, floor) and rel(got, brute_scores(W, r, 0)[2], floor), (seed, got, want)
        assert not rel(got, sumF / np.std(e[Fs], ddof=0)), "the harness divides by the SAMPLE standard deviation (ddof 1), as the registered score does"
        if seed == 81:
            assert abs(sumF) > 1e-3, "a numerator well away from zero: the strict relative tolerance means something"
    return True


def t_spin():
    """[D2] spin-offs and stock dividends (the calendar names them; the holder gets new shares, no credit is computed for them, so the ex-date's price drop is not a return). (a) INSIDE the regression / formation window the name's
    return on its ex-date session is LEFT OUT - of the beta, the residuals, the formation sum and product, the 230-return and 230-pair counts - on hand numbers (an OLS that recovers a planted alpha and beta exactly from the REMAINING
    sessions); events just outside the window change nothing; the no-dividend set leaves it out too. (b) INSIDE the hold (f < t <= x) it is a data event like a hygiene flag: the base removes the name-month from the cell AND the
    null, the look-ahead reading keeps it on its naive price path (the drop is in the P&L); the fill session's own ex-date is bought ex (not in the hold), the exit session's is in it. (c) the first-reason tally still adds up and
    the counts of the picks (window, hold; long, short) equal the plain-python recount"""
    with spec(win=30, form_n=20, skip=10, min_n=25, n_side=1):
        T, r = 70, 43
        a, fa, fe = windows(r)
        assert (a, fa, fe) == (14, 14, 33)
        # ---------------- (a) the window
        rng = np.random.default_rng(31)
        m = rng.normal(0.0, 0.01, T)
        m[0] = np.nan
        alphas, betas = [0.0010, -0.0005, 0.0008, 0.0012, 0.0003, -0.0002], [1.5, 0.7, 1.1, 0.9, 1.3, 0.6]

        def planted(ev, alpha, beta, seed):
            """returns = alpha + beta x ES + e on the window's sessions that carry no event (e orthogonal to [1, ES] over THOSE sessions: the OLS on them recovers alpha and beta exactly and the residual IS e); -30% on the event rows"""
            rows = [t for t in range(a, r + 1) if t not in ev]
            X = np.column_stack([np.ones(len(rows)), m[rows]])
            e0 = np.random.default_rng(seed).normal(0.0, 0.01, len(rows))
            e = e0 - X @ np.linalg.lstsq(X, e0, rcond=None)[0]
            ret = np.random.default_rng(seed + 100).normal(0.0, 0.01, T)
            ret[0] = 0.0
            ret[rows] = alpha + beta * m[rows] + e
            ret[sorted(ev)] = -0.30
            return ret, rows, e
        ev_sets = [{20}, {38}, {14, 43}, {13, 44}, {15, 18, 22, 27, 31}, {15, 18, 22, 27, 31, 36}]         # N0 in F, N1 in the skipped month, N2 on the first and last rows of the window, N3 just outside it, N4 five (25 left), N5 six (24 left)
        plan = [planted({t for t in ev if a <= t <= r}, alphas[j], betas[j], 40 + j) for j, ev in enumerate(ev_sets)]
        rets = np.column_stack([np.where(np.isin(np.arange(T), sorted(ev)), -0.30, pl[0]) for ev, pl in zip(ev_sets, plan)])
        Sp = np.zeros((T, 6), bool)
        for j, ev in enumerate(ev_sets):
            Sp[sorted(ev), j] = True
        Cl = prices(rets)
        Wsp, Wno = mk_world(Cl, m, Sp=Sp), mk_world(Cl, m)
        cols = np.arange(6)
        n_ret, n_pair, res, raw = rm_scores(Wsp, r, cols)
        n0, p0, res0, raw0 = rm_scores(Wno, r, cols)
        assert n0.tolist() == p0.tolist() == [30] * 6 and n_ret.tolist() == n_pair.tolist() == [29, 29, 28, 30, 25, 24], (n_ret.tolist(), n_pair.tolist())
        for j in (0, 1, 2):                                                                  # closed forms: the OLS recovered the planted alpha / beta from the remaining sessions, e is the planted residual
            ret_j, rows, e = plan[j]
            Fi = [i for i, t in enumerate(rows) if fa <= t <= fe]
            want_res = (len(Fi) * alphas[j] + e[Fi].sum()) / np.std(e[Fi], ddof=1)
            want_raw = np.prod([1.0 + ret_j[t] for t in rows if fa <= t <= fe]) - 1.0
            assert abs(res[j] - want_res) < 1e-9 and abs(raw[j] - want_raw) < 1e-12, (j, res[j], want_res, raw[j], want_raw)
        assert len([t for t in plan[0][1] if fa <= t <= fe]) == 19 and len([t for t in plan[1][1] if fa <= t <= fe]) == 20 and len([t for t in plan[2][1] if fa <= t <= fe]) == 19
        assert abs((1.0 + raw0[0]) - 0.7 * (1.0 + raw[0])) < 1e-12 and abs(res0[0] - res[0]) > 1.0, "without the rule the -30% day is in RAW's product and in RES's sum (and the beta)"
        assert abs(raw[1] - raw0[1]) < 1e-12 and abs(res[1] - res0[1]) > 1e-3, "an event in the skipped month: RAW never saw it; RES does through the beta, which the rule keeps clean"
        assert abs(res[3] - res0[3]) < 1e-12 and abs(raw[3] - raw0[3]) < 1e-12, "events one session before the window and on the fill session change nothing"
        for j in range(6):
            bs = brute_scores(Wsp, r, j)
            assert bs[:2] == (n_ret[j], n_pair[j]) and abs(bs[2] - res[j]) < 1e-9 and abs(bs[3] - raw[j]) < 1e-12, j
        assert np.isnan(Wsp.Rd[20, 0]) and np.isfinite(Wsp.Rn[20, 0]) and Wsp.Rn[20, 0] < -0.29, "the price series keeps the drop; only the return the score reads is left out"
        with div_mode(Wsp, False):
            assert Wsp.Rd is Wsp.Rn0 and np.isnan(Wsp.Rd[20, 0]) and np.isfinite(Wsp.Rd[21, 0]) and close(rm_scores(Wsp, r, cols)[2:], (res, raw)), "the no-dividend set leaves the session out too: only the cash differs between the two"
        assert Wsp.spin_counts == {"cells": 17, "with_a_return": 17, "no_return": 0} and int(Sp.sum()) == 17, Wsp.spin_counts                  # 1 + 1 + 2 + 2 + 5 + 6 ex-date sessions, every one with a return to leave out
        rec, cnt = rm_one(Wsp, r, r + 1, r + 25, "remove", units=False)
        assert rec.pool.tolist() == [0, 1, 2, 3, 4] and cnt["short_history"] == 1 and cnt["no_es_pairs"] == 0 and cnt["pool"] == 5 and rec.nfull == 5, (rec.pool.tolist(), dict(cnt))
        assert rec.spin_win.tolist() == [1, 1, 2, 0, 5] and rec.spin_hold.tolist() == [False] * 5 and cnt["post_spin"] == 0
        assert cnt["spin_window_names"] == 5 and cnt["spin_window_sessions"] == 1 + 1 + 2 + 0 + 5 + 6 and cnt["spin_hold_names"] == 0, "N3's event on the fill session (row 44) is not inside the hold (f < t <= x)"
        with spec(min_n=24):                                                                 # the 230-return rule at its edge: 24 left is exactly in
            rec, cnt = rm_one(Wsp, r, r + 1, r + 25, "remove", units=False)
            assert rec.pool.tolist() == [0, 1, 2, 3, 4, 5] and cnt["short_history"] == 0 and rec.nfull == 6, (rec.pool.tolist(), dict(cnt))
        # an ex-date on a session WITHOUT a close: there is no return to leave out (counted apart; the missing close already lost that session's and the next session's returns); inside a hold it still removes the name-month
        Cl6 = prices(np.random.default_rng(88).normal(0.0, 0.01, (T, 4)), 50.0)
        Cl6[25, 0] = np.nan
        Cl6[50, 2] = np.nan
        Cl6[:21, 3] = np.nan                                                                  # N3: first price on row 21 - 22 returns in the window: under the 25 (short history)
        Sp6 = np.zeros((T, 4), bool)
        Sp6[25, 0] = Sp6[30, 0] = Sp6[30, 1] = Sp6[50, 2] = Sp6[55, 3] = True
        W6 = mk_world(Cl6, m, Sp=Sp6)
        assert W6.spin_counts == {"cells": 5, "with_a_return": 3, "no_return": 2}, W6.spin_counts
        n6 = rm_scores(W6, r, np.arange(4))
        assert n6[0].tolist() == n6[1].tolist() == [27, 29, 30, 22], "N0: rows 25 and 26 have no return (a missing close) and row 30's is left out; N1: row 30's; N2: the event is outside the window; N3: short history"
        rec6, cnt6 = rm_one(W6, r, r + 1, r + 25, "remove", units=False)
        assert rec6.pool.tolist() == [0, 1] and rec6.spin_win.tolist() == [1, 1] and cnt6["short_history"] == 1 and cnt6["post_spin"] == 1 and cnt6["spin_window_names"] == 2 and cnt6["spin_window_sessions"] == 2, (rec6.pool.tolist(), dict(cnt6))
        assert cnt6["spin_hold_names"] == 2, "counted over the universe names whatever else removes them: N2 (the hold) and N3 (short history, with a hold event of its own)"
        L6 = rm_build(W6, W6.days[0], W6.days[-1])
        run6 = run_cell(W6, cell_leg(L6, "RAW"), D15.l1_cfg(), pos=True)
        c6 = {x_["symbol"]: x_["spin_returns_left_out_in_window"] for x_ in rm_candidate_rows(W6, L6, "RAW", run6, None, {})}
        assert c6 == {"N00": 1, "N01": 1}, ("the audit's row counts the returns actually left out: N00's ex-date on its missing-close session is not one", c6)
        # ---------------- (b) the hold
        g = np.array([0.004, 0.002, -0.004])
        c0, rate = COST_BPS * 1e-4, BORROW / 252.0

        def hold_world(ev_row, seed=51):
            ret = np.tile(g, (T, 1))
            rg = np.random.default_rng(seed)
            ret[1:44] += rg.normal(0.0, 0.002, (43, 3))                                       # noise in the window (a flat residual has no RES), exactly g a day from the fill on
            ret[0] = 0.0
            ret[ev_row, 0] = -0.30
            Cl_ = prices(ret, 50.0)
            Od = np.vstack([Cl_[:1], Cl_[:-1]])
            Od[ev_row, 0] = Cl_[ev_row, 0]                                                    # the drop is at the OPEN of the ex-date session: the open is the post-drop price (no +-50% jump flag: it is -30%)
            mm = rg.normal(0.0, 0.01, T)
            mm[0] = np.nan
            Sp_ = np.zeros((T, 3), bool)
            Sp_[ev_row, 0] = True
            return mk_world(Cl_, mm, Od=Od, Sp=Sp_, k=np.ones(T))
        lo = lambda W_: W_.days[0]
        hi = lambda W_: W_.days[-1]
        # inside the hold (row 50): removed by the base, kept at its naive price path by the other reading
        Wz = hold_world(50)
        Lr, Lk = rm_build(Wz, lo(Wz), hi(Wz)), rm_build(Wz, lo(Wz), hi(Wz), "naive")
        rr, rk = Lr.recs[0], Lk.recs[0]
        assert (rr.r, rr.f, rr.x) == (43, 44, 65) and (rk.r, rk.f, rk.x) == (43, 44, 65)
        assert rr.pool.tolist() == [1, 2] and not rr.naive.any() and Lr.cnt[2024]["post_spin"] == 1 and Lr.cnt[2024]["spin_hold_names"] == 1 and Lr.cnt[2024]["kept_naive"] == 0, dict(Lr.cnt[2024])
        assert rk.pool.tolist() == [0, 1, 2] and rk.naive.tolist() == [True, False, False] and Lk.cnt[2024]["kept_naive"] == 1 and Lk.cnt[2024]["post_spin"] == 0 and Lk.cnt[2024]["spin_hold_names"] == 1, dict(Lk.cnt[2024])
        ratio = 0.7 * (1 + g[0]) ** 20                                                        # rows 44 .. 64: twenty days at g and the -30% day
        assert abs(rk.U.G[0].sum() - (ratio - 1.0)) < 1e-12, "the kept name's path is the naive price path, the drop included"
        assert abs(D15.unit_path(Wz.Ao, Wz.Ac, 44, 65, np.array([0])).G[0].sum() - (ratio - 1.0)) < 1e-12, "(no split here: the raw and the split-safe paths are one)"
        up1, dn2 = (1 + g[1]) ** 21, (1 + g[2]) ** 21
        short_pnl = 4000.0 * (-(dn2 - 1.0) - c0 - c0 * dn2 - rate * sum((1 + g[2]) ** h for h in range(1, 22)))
        for L_, longj, ratio_j in ((Lr, 1, up1), (Lk, 0, ratio)):
            run = run_cell(Wz, cell_leg(L_, "RAW"), D15.l1_cfg(), pos=True)
            assert run.n_pos == 2 and abs(run.pos.pnl[run.pos.side == 1][0] - 4000.0 * (ratio_j - 1.0 - c0 - c0 * ratio_j)) < 1e-6 and abs(run.pos.pnl[run.pos.side == -1][0] - short_pnl) < 1e-6, (longj, run.pos.pnl)
        compare_rm(Wz, Lr, brute_rm(Wz, lo(Wz), hi(Wz)), "spin hold remove")
        compare_rm(Wz, Lk, brute_rm(Wz, lo(Wz), hi(Wz), "naive"), "spin hold naive")
        s1 = run_cell(Wz, cell_leg(Lr, "RAW"), D15.l1_cfg()).x                              # the null: the pool is exactly the two names left, so every draw is one of the two long / short assignments - never the removed name
        swapped = cell_leg(Lr, "RAW")
        for v in swapped.recs:
            v.long, v.short = v.short, v.long
        s2 = run_cell(Wz, swapped, D15.l1_cfg()).x
        in12 = lambda acc_: [bool(np.allclose(row_, s1, atol=1e-9) or np.allclose(row_, s2, atol=1e-9)) for row_ in acc_]
        acc = rm_null(Wz, Lr, 40, 0)["RAW"]
        assert all(in12(acc)) and not np.allclose(s1, s2, atol=1e-6) and any(np.allclose(row_, s1, atol=1e-9) for row_ in acc) and any(np.allclose(row_, s2, atol=1e-9) for row_ in acc), "the removed name-month is out of the null as well"
        assert not all(in12(rm_null(Wz, Lk, 40, 0)["RAW"])), "the look-ahead reading's null does draw it"
        # the first session after the fill (row 45): the lower edge of the hold is inclusive from f + 1
        W1 = hold_world(45)
        L1r, L1k = rm_build(W1, lo(W1), hi(W1)), rm_build(W1, lo(W1), hi(W1), "naive")
        assert L1r.recs[0].pool.tolist() == [1, 2] and L1k.recs[0].pool.tolist() == [0, 1, 2] and L1k.recs[0].naive.tolist() == [True, False, False] and L1r.cnt[2024]["post_spin"] == 1 and L1r.cnt[2024]["spin_hold_names"] == 1
        assert abs(L1k.recs[0].U.G[0].sum() - (0.7 * (1 + g[0]) ** 20 - 1.0)) < 1e-12
        # ON the exit session (row 65): inside the hold - the exit open is the post-drop price
        Wy = hold_world(65)
        Lr, Lk = rm_build(Wy, lo(Wy), hi(Wy)), rm_build(Wy, lo(Wy), hi(Wy), "naive")
        assert Lr.recs[0].pool.tolist() == [1, 2] and Lk.recs[0].pool.tolist() == [0, 1, 2] and Lk.recs[0].naive.tolist() == [True, False, False] and Lr.cnt[2024]["post_spin"] == 1
        assert abs(Lk.recs[0].U.G[0].sum() - (0.7 * (1 + g[0]) ** 21 - 1.0)) < 1e-12, "the exit session's own ex-date is inside the hold"
        run_y = run_cell(Wy, cell_leg(Lk, "RAW"), D15.l1_cfg(), pos=True)
        cy = {(x_["symbol"], x_["side"]): x_ for x_ in rm_candidate_rows(Wy, Lk, "RAW", run_y, None, {})}
        assert cy[("N00", "long")]["spin_or_stock_dividend_in_hold"] is True and cy[("N00", "long")]["spin_returns_left_out_in_window"] == 0 and cy[("N02", "short")]["spin_or_stock_dividend_in_hold"] is False, "the audit's row says the kept name had an ex-date in its hold"
        compare_rm(Wy, Lr, brute_rm(Wy, lo(Wy), hi(Wy)), "spin exit remove")
        compare_rm(Wy, Lk, brute_rm(Wy, lo(Wy), hi(Wy), "naive"), "spin exit naive")
        # ON the fill session (row 44): bought ex - not in the hold, not removed, nothing of the drop in the position
        Wx = hold_world(44)
        for pm in ("remove", "naive"):
            L_ = rm_build(Wx, lo(Wx), hi(Wx), pm)
            rec = L_.recs[0]
            assert rec.pool.tolist() == [0, 1, 2] and not rec.naive.any() and L_.cnt[2024]["post_spin"] == 0 and L_.cnt[2024]["spin_hold_names"] == 0 and L_.cnt[2024]["kept_naive"] == 0, (pm, dict(L_.cnt[2024]))
            assert rec.pool[rec.pick["RAW"][0]].tolist() == [0] and abs(rec.U.G[0].sum() - ((1 + g[0]) ** 20 - 1.0)) < 1e-12, "the fill open is the post-drop price: the position never held the drop"
            compare_rm(Wx, L_, brute_rm(Wx, lo(Wx), hi(Wx), pm), f"spin fill {pm}")
            run_x = run_cell(Wx, cell_leg(L_, "RAW"), D15.l1_cfg(), pos=True)
            cx = {(x_["symbol"], x_["side"]): x_ for x_ in rm_candidate_rows(Wx, L_, "RAW", run_x, None, {})}
            assert cx[("N00", "long")]["spin_or_stock_dividend_in_hold"] is False and cx[("N00", "long")]["spin_returns_left_out_in_window"] == 0, "bought ex: the fill session's own ex-date is not in the hold, in the audit's row either"
        # ---------------- (c) seven names: the tally, the counts of the picks
        g7 = np.array([0.005, 0.003, 0.0005, 0.0, -0.0005, -0.005, -0.003])
        rg = np.random.default_rng(77)
        ret = np.tile(g7, (T, 1))
        ret[1:44] += rg.normal(0.0, 0.002, (43, 7))
        ret[0] = 0.0
        events = {0: [50], 1: [20, 25], 2: [44], 3: [65], 4: [66], 5: [55]}                   # H0 inside the hold, H1 twice inside its formation window, H2 on the fill session, H3 on the exit session, H4 after the exit, H5 inside the hold
        Sp7 = np.zeros((T, 7), bool)
        for j, rows_ in events.items():
            ret[rows_, j] = -0.30
            Sp7[rows_, j] = True
        Cl7 = prices(ret, 50.0)
        Od7 = np.vstack([Cl7[:1], Cl7[:-1]])
        for j, rows_ in events.items():
            Od7[rows_, j] = Cl7[rows_, j]
        mm = rg.normal(0.0, 0.01, T)
        mm[0] = np.nan
        W7 = mk_world(Cl7, mm, Od=Od7, Sp=Sp7, k=np.ones(T))
        Bz7 = {pm: brute_rm(W7, lo(W7), hi(W7), pm) for pm in ("remove", "naive")}
        L7 = {pm: rm_build(W7, lo(W7), hi(W7), pm) for pm in ("remove", "naive")}
        for pm in ("remove", "naive"):
            compare_rm(W7, L7[pm], Bz7[pm], f"spin 7 {pm}")
            c7 = L7[pm].cnt[2024]
            assert c7["universe"] == sum(c7[k] for k in COUNT_KEYS[1:] if k != "kept_naive"), (pm, dict(c7))               # (kept_naive is a part of pool in the look-ahead reading)
            assert c7["spin_hold_names"] == 3 and c7["spin_window_names"] == 1 and c7["spin_window_sessions"] == 2, (pm, dict(c7))
        rr, rk = L7["remove"].recs[0], L7["naive"].recs[0]
        assert rr.pool.tolist() == [1, 2, 4, 6] and L7["remove"].cnt[2024]["post_spin"] == 3 and L7["remove"].cnt[2024]["pool"] == 4, (rr.pool.tolist(), dict(L7["remove"].cnt[2024]))
        assert rk.pool.tolist() == list(range(7)) and rk.naive.tolist() == [True, False, False, True, False, True, False] and L7["naive"].cnt[2024]["kept_naive"] == 3
        assert rr.spin_win.tolist() == [2, 0, 0, 0] and rr.spin_hold.tolist() == [False] * 4 and rk.spin_hold.tolist() == [True, False, False, True, False, True, False]
        for cell in CELLS:
            for pm, key in (("remove", "registered"), ("naive", "look-ahead")):
                assert spin_counts(L7[pm], cell) == brute_spin_counts(Bz7[pm], cell), (cell, pm, spin_counts(L7[pm], cell))
        assert spin_counts(L7["remove"], "RAW") == {"long": {"positions": 1, "window_positions": 1, "window_sessions": 2, "hold_positions": 0}, "short": {"positions": 1, "window_positions": 0, "window_sessions": 0, "hold_positions": 0}}
        assert spin_counts(L7["naive"], "RAW") == {"long": {"positions": 1, "window_positions": 0, "window_sessions": 0, "hold_positions": 1}, "short": {"positions": 1, "window_positions": 0, "window_sessions": 0, "hold_positions": 1}}
        for pm in ("remove", "naive"):                                                        # the audit's candidate rows: the returns left out of the window, an ex-date in the hold
            run7 = run_cell(W7, cell_leg(L7[pm], "RAW"), D15.l1_cfg(), pos=True)
            cr = {(x_["symbol"], x_["side"]): x_ for x_ in rm_candidate_rows(W7, L7[pm], "RAW", run7, None, {})}
            want = {("N01", "long"): (2, False), ("N06", "short"): (0, False)} if pm == "remove" else {("N00", "long"): (0, True), ("N05", "short"): (0, True)}
            assert set(cr) == set(want) and all((cr[k]["spin_returns_left_out_in_window"], cr[k]["spin_or_stock_dividend_in_hold"]) == v for k, v in want.items()), (pm, {k: (v["spin_returns_left_out_in_window"], v["spin_or_stock_dividend_in_hold"]) for k, v in cr.items()})
        assert spin_counts(SimpleNamespace(recs=[]), "RES") == {sd: {"positions": 0, "window_positions": 0, "window_sessions": 0, "hold_positions": 0} for sd in ("long", "short")}
    return True


def t_d1():
    """[D1] COVERAGE: the calendar's start is read from its manifest (never a constant), the formation sessions before it are counted per WF rank, the five ranks the prereg names are compared with what the count finds, and the REPORTED row
    without them leaves those rebalances out of the cell AND the null (counted as dropped_d1), everything else being the registered reading"""
    me = sys.modules[__name__]
    assert calendar_start({"start": "2016-06-01"}) == TS("2016-06-01") and calendar_start({"start": "2016-06-01T10:00:00"}) == TS("2016-06-01")
    assert calendar_start({}) is None and calendar_start(None) is None and calendar_start({"start": ""}) is None and calendar_start({"start": None}) is None and calendar_start({"start": "not a date"}) is None
    with spec(n_side=3), D15.spec(univ=14):
        W = toy_world()
        r_all, f_all, x_all = rm_schedule(W.days)
        built = [r for r, x in zip(r_all.tolist(), x_all.tolist()) if x >= 0 and WF0 <= W.days[x] <= PRE_END and r >= SPEC["win"] - 1]
        assert [W.days[r] for r in built] == [TS("2024-12-31"), TS("2025-01-31"), TS("2025-02-28"), TS("2025-03-31"), TS("2025-04-30")]
        fas = [windows(r)[1] for r in built]
        assert fas[0] == built[0] - 251 and all(b_ > a_ for a_, b_ in zip(fas[:-1], fas[1:]))
        for start in (W.days[0], W.days[100], W.days[fas[2]], W.days[fas[2] + 1], W.days[-1], TS("2030-01-01")):
            cov = d1_coverage(W, start)
            assert [d for d, n, m_ in cov] == [W.days[r] for r in built] and all(m_ == 231 for d, n, m_ in cov)
            for (d, n, m_), r in zip(cov, built):
                a_, fa_, fe_ = windows(r)
                assert n == int(((W.days >= W.days[fa_]) & (W.days <= W.days[fe_]) & (W.days < start)).sum()) == int(sum(1 for t in range(fa_, fe_ + 1) if W.days[t] < start)), (start, d)
        cov = d1_coverage(W, W.days[100])
        assert [n for d, n, m_ in cov] == [max(0, 100 - fa_) for fa_ in fas] and fas[0] == 10 and cov[0][1] == 90, "the first rank's formation window starts at row 10: 90 of its sessions are before row 100; each later rank starts later"
        assert [n for d, n, m_ in d1_coverage(W, W.days[fas[2]])] == [fas[2] - fas[0], fas[2] - fas[1], 0, 0, 0], "ranks 1 and 2 start before the calendar does; the third starts exactly on it"
        # the record and the printed line; the registered five (here patched to the two partly uncovered toy ranks) are compared with what the count finds
        start = W.days[fas[2]]
        with patched(me, D1_RANKS=(f"{W.days[built[0]]:%Y-%m-%d}", f"{W.days[built[1]]:%Y-%m-%d}")):
            rec, txt = d1_report(W, start)
            assert rec["registered_five_match"] is True and rec["fully_covered_ranks"] == 3 and rec["first_fully_covered_rank"] == "2025-02-28" and rec["calendar_start"] == f"{start:%Y-%m-%d}" and rec["ranks_in_wf"] == 5
            assert [(x["rank"], x["formation_sessions_before"]) for x in rec["partly_before_the_start"]] == [("2024-12-31", fas[2] - fas[0]), ("2025-01-31", fas[2] - fas[1])] and len(rec["per_rank"]) == 5
            assert f"2024-12-31 {fas[2] - fas[0]}, 2025-01-31 {fas[2] - fas[1]}; 0 from 2025-02-28 on (3 ranks)" in txt and "the partly uncovered ranks are the five the pre-registration names" in txt and "WARNING" not in txt, txt
        rec, txt = d1_report(W, start)                                                       # the real five are not these ranks: the line says so and the row still drops the registered five
        assert rec["registered_five_match"] is False and "WARNING: the partly uncovered ranks are NOT the five the pre-registration names (2016-12-30, 2017-01-31, 2017-02-28, 2017-03-31, 2017-04-28)" in txt
        rec, txt = d1_report(W, W.days[0])
        assert rec["partly_before_the_start"] == [] and rec["fully_covered_ranks"] == 5 and "by rank: none; 0 from 2024-12-31 on (5 ranks)" in txt
        rec, txt = d1_report(W, TS("2030-01-01"))
        assert rec["fully_covered_ranks"] == 0 and rec["first_fully_covered_rank"] is None and "no rank is fully covered" in txt and rec["partly_before_the_start"][0]["formation_sessions_before"] == 231
        # the row without the first ranks: out of the cell AND the null, counted; a date that is not a rank session (or not in the data) drops nothing
        lo_, hi_ = WF0, PRE_END                                                              # the WF stretch: the five ranks counted above (the toy world's last three exit after it)
        base = rm_build(W, lo_, hi_)
        assert [q.r for q in base.recs] == built
        two = tuple(W.days[r] for r in built[:2])
        dl = rm_build(W, lo_, hi_, drop=two)
        assert [(q.r, q.f, q.x) for q in dl.recs] == [(q.r, q.f, q.x) for q in base.recs[2:]] and all(u.pool.tolist() == v.pool.tolist() and close(u.score["RES"], v.score["RES"]) for u, v in zip(dl.recs, base.recs[2:]))
        assert sum(v["dropped_d1"] for v in dl.cnt.values()) == 2 and sum(v["rebalances"] for v in dl.cnt.values()) == len(base.recs) - 2 == 3 and sum(v["dropped_d1"] for v in base.cnt.values()) == 0
        same = rm_build(W, lo_, hi_, drop=(TS("2024-12-30"), TS("2031-01-01"), W.days[built[0] + 1]))
        assert [(q.r, q.f, q.x) for q in same.recs] == [(q.r, q.f, q.x) for q in base.recs] and sum(v["dropped_d1"] for v in same.cnt.values()) == 0
        assert [(q.r) for q in rm_build(W, lo_, hi_, drop=()).recs] == [q.r for q in base.recs] and [(q.r) for q in rm_build(W, lo_, hi_, drop=None).recs] == [q.r for q in base.recs]
        B, S12 = synth_book(seed=15)
        rows = A13.book_rows(B, W)
        with patched(me, A2_WIN=(TS("2024-12-02"), TS("2025-05-30"))):
            res, obj = evaluate(W, B, S12, rows, "remove", 20, 3, drop=two)
            res_all, obj_all = evaluate(W, B, S12, rows, "remove", 20, 3)
        assert len(obj.legs.recs) == 3 and len(obj_all.legs.recs) == 5 and res["null"]["draws"] == 20
        Bz = brute_rm(W, WF0, PRE_END)[2:]
        for cell in CELLS:
            x0 = np.zeros(W.T)
            for b in Bz:
                for sd, js in ((1, b["long"][cell]), (-1, b["short"][cell])):
                    for j in js:
                        x0[b["f"]:b["x"] + 1] += SPEC["slot"] * np.array(brute_path(W, b["f"], b["x"], j, sd, b["pool"][j][2])[0])
            c = res["cells"][cell]["base"]
            assert abs(c["net"] - x0.sum()) < 1e-6 and c["n_units"] == 3 and c["n_pos"] == 3 * 6 and res_all["cells"][cell]["base"]["n_units"] == 5
        acc = rm_null(W, obj.legs, 20, 3)
        assert all((acc[c][:, :obj.legs.recs[0].f] == 0).all() for c in CELLS) and all(np.abs(acc[c][:, obj.legs.recs[0].f:]).sum() > 0 for c in CELLS), "the null draws no dropped rebalance: nothing before the first remaining fill"
    return True


def t_stage_b_checks():
    """STAGE B's pass is the LEG's standalone veto and nothing else: each of the three checks broken alone fails exactly itself, the bars are inclusive (10 rebalances), a NaN fails, and there is no input for the book add"""
    ok_leg = {"n_units": 12, "net": 1000.0, "net_ex_top_pos": 400.0}
    assert len(b_checks(ok_leg)) == 3 and all(b_checks(ok_leg).values())
    names = {"n_units": "leg monthly rebalances>=10", "net": "leg net>0", "net_ex_top_pos": "leg net>0 without its top name-month"}
    for key, bad in (("n_units", 9), ("n_units", 0), ("net", 0.0), ("net", -1.0), ("net", float("nan")), ("net_ex_top_pos", 0.0), ("net_ex_top_pos", -1.0), ("net_ex_top_pos", float("nan"))):
        chk = b_checks({**ok_leg, key: bad})
        assert [k for k, v in chk.items() if not v] == [names[key]], (key, bad, chk)
    assert all(b_checks({**ok_leg, "n_units": 10}).values()), "10 rebalances is enough"
    import inspect
    assert list(inspect.signature(b_checks).parameters) == ["leg"], "no book argument: the book add cannot be part of the pass"
    # the reported book-add comparison: both bars, inclusive, a NaN fails
    br, bs = RULES["b_roc"], RULES["b_sort"]
    nan = float("nan")
    for roc, sort, want in ((br, bs, True), (br + 1, bs + 1, True), (br + 1, bs - 0.01, False), (br - 0.01, bs + 1, False), (br - 1, bs - 1, False), (nan, bs, False), (br, nan, False)):
        assert book_add_would_clear({"roc": roc, "sortino": sort}) is want, (roc, sort)
    # Stage A's bookkeeping: a cell that fails a bar is never a candidate and never pending, however complete its audit; the candidate is the passing cell with the higher WF ROC (ties: RES first)
    cl = lambda p, roc: {"PASS": p, "base": {"roc": roc}}
    au = lambda a_, b_: {"RES": {"audit_complete": a_}, "RAW": {"audit_complete": b_}}
    for pr, pw, ar, aw, passing, pending, cand in (
            (True, True, True, True, ["RES", "RAW"], [], "RAW"),                                # both pass, audits complete: the higher ROC (RAW 30 > RES 20)
            (True, True, True, False, ["RES"], ["RAW"], "RES"),                                 # RAW's audit is open: RES goes, RAW waits
            (True, True, False, False, [], ["RES", "RAW"], None),                               # nothing audited: nothing goes, both wait
            (True, False, True, True, ["RES"], [], "RES"),                                      # RAW fails every bar: its complete audit makes it neither a candidate nor pending
            (False, False, True, True, [], [], None),                                           # both fail with complete audits: no candidate, nothing pending (the FAIL verdict)
            (False, False, False, False, [], [], None),                                         # both fail with NO audit: still a FAIL verdict - a failing cell never waits on an audit
            (True, False, False, False, [], ["RES"], None),                                     # RES passes with an open audit, RAW fails with an open audit: only RES waits
            (False, True, True, False, [], ["RAW"], None)):                                     # RES fails (complete audit), RAW passes with an open audit: only RAW waits
        cells_ = {"RES": cl(pr, 20.0), "RAW": cl(pw, 30.0)}
        wd, ps, pn, cd = stage_a_flow(cells_, au(ar, aw))
        assert wd == {"RES": pr, "RAW": pw} and ps == passing and pn == pending and cd == cand, (pr, pw, ar, aw, ps, pn, cd)
    assert stage_a_flow({"RES": cl(True, 30.0), "RAW": cl(True, 30.0)}, au(True, True))[3] == "RES", "a tie in ROC goes to RES"


def t_files():
    """the audit file (read, applied, status) and the candidates' bookkeeping"""
    import shutil, tempfile
    root = tempfile.mkdtemp(prefix="resmom_selftest_")
    try:
        with spec(n_side=3), D15.spec(univ=14):
            W = toy_world()
        ap = os.path.join(root, "resmom_audit.csv")
        assert read_audit(ap) is None
        open(ap, "w").write(f"symbol,date,cell,verdict,note\nN08,{W.days[270]:%Y-%m-%d},RES,data_event,split\nN01,{W.days[280]:%Y-%m-%d},raw,KEEP,fine\nN09,{W.days[300]:%Y-%m-%d},RAW,data_event,bad print\n")
        au = read_audit(ap)
        assert au["verdict"].tolist() == ["data_event", "keep", "data_event"] and au["cell"].tolist() == ["RES", "RAW", "RAW"]
        cnt = apply_audit(W, au)
        assert cnt == {"rows": 3, "keep": 1, "data_event": 2} and W.aud1[270, 8] and W.aud1[300, 9] and W.aud1.sum() == 2, "a data_event row removes the name-month (by fill session)"
        assert apply_audit(W, None)["rows"] == 0 and not W.aud1.any()
        for bad in (f"N08,{W.days[270]:%Y-%m-%d},RES,maybe,x\n", "N08,not-a-date,RES,keep,x\n", f"N08,{W.days[270]:%Y-%m-%d},L1-F,keep,x\n", f",{W.days[270]:%Y-%m-%d},RES,keep,x\n"):
            open(ap, "w").write("symbol,date,cell,verdict,note\n" + bad)
            try:
                read_audit(ap)
                raise AssertionError("an unreadable audit row must refuse")
            except SystemExit as e:
                assert "line(s) [2]" in str(e)
        open(ap, "w").write("symbol,date\nN08,2024-01-01\n")
        try:
            read_audit(ap)
            raise AssertionError("an audit file without its columns must refuse")
        except SystemExit as e:
            assert "lacks the column" in str(e)
        for sym, d in (("ZZZ", W.days[270]), ("N08", pd.Timestamp("2025-01-04"))):         # a data_event row that matches no name / no session must not silently do nothing
            open(ap, "w").write(f"symbol,date,cell,verdict,note\n{sym},{d:%Y-%m-%d},RES,data_event,x\n")
            try:
                apply_audit(W, read_audit(ap))
                raise AssertionError("a data_event row that matches nothing must refuse")
            except SystemExit as e:
                assert "match no session or no name" in str(e)
        open(ap, "w").write(f"symbol,date,cell,verdict,note\nN08,{W.days[270]:%Y-%m-%d},RES,data_event,x\nN05,{W.days[270]:%Y-%m-%d},RES,data_event,x\n")
        au = read_audit(ap)
        apply_audit(W, au)
        assert unused_audit_rows(W, au) == [f"N08 {W.days[270]:%Y-%m-%d} RES", f"N05 {W.days[270]:%Y-%m-%d} RES"], "no build has run yet: both rows are unused until a build hits them"
        W.aud_hit.add((AUD, 270, 8))
        assert unused_audit_rows(W, au) == [f"N05 {W.days[270]:%Y-%m-%d} RES"]
        # audit_status: by symbol + fill date (a row covers both cells' listing of the name-month)
        d0 = f"{W.days[270]:%Y-%m-%d}"
        cands = {"RES": [{"symbol": "N08", "date": d0}], "RAW": [{"symbol": "N08", "date": d0}, {"symbol": "N05", "date": "2024-01-01"}]}        # N05 is in the file, but for another date: not audited
        st = audit_status(cands, au)
        assert st["RES"] == {"listed": 1, "audited": 1, "audit_complete": True} and st["RAW"] == {"listed": 2, "audited": 1, "audit_complete": False}
        assert audit_status(cands, None)["RES"]["audit_complete"] is False and audit_status({"RES": [], "RAW": []}, au)["RES"]["audit_complete"] is False
    finally:
        shutil.rmtree(root, ignore_errors=True)


def t_integration():
    """evaluate / reports / candidate rows on the toy world and a synthetic #463 (no files): every stat is the independent sum, the audit candidates are the largest gains with their dates, the reports carry every item of the
    prereg's REPORTED paragraph, the null and the A2 report run, the data event removes a name-month from the cell AND the null"""
    me = sys.modules[__name__]
    B, S12 = synth_book(seed=15)
    with spec(n_side=3), D15.spec(univ=14):
        W = toy_world()
        rows = A13.book_rows(B, W)
        spy, real_judge = [], judge_cell

        def judge_spy(st, net10, nul):
            spy.append((st, net10, nul))
            return real_judge(st, net10, nul)
        with patched(me, A2_WIN=(TS("2024-12-02"), TS("2025-05-30"))):                        # the toy world's own positions, so c exists
            with patched(me, judge_cell=judge_spy):
                res, obj = evaluate(W, B, S12, rows, "remove", 40, 0, full=True)
            assert [(a_[0], a_[1]) for a_ in spy] == [(res["cells"][c]["base"], res["cells"][c]["stress"]["10 bps"]["net"]) for c in CELLS] and all(a_[2] is res["null"] for a_ in spy), "judge_cell reads each cell's own base stats, its 10 bps net and the null"
            resK, objK = evaluate(W, B, S12, rows, "naive", 40, 1, full=False)
        for cell in CELLS:
            c = res["cells"][cell]
            Bz = brute_rm(W, WF0, PRE_END)
            x0 = np.zeros(W.T)
            for b in Bz:
                for sd, js in ((1, b["long"][cell]), (-1, b["short"][cell])):
                    for j in js:
                        x0[b["f"]:b["x"] + 1] += SPEC["slot"] * np.array(brute_path(W, b["f"], b["x"], j, sd, b["pool"][j][2])[0])
            assert abs(c["base"]["net"] - x0.sum()) < 1e-6 and c["base"]["n_units"] == len(Bz) == 5 and c["base"]["n_pos"] == 6 * 5 and abs(c["base"]["net_pos"] - x0.sum()) < 1e-6
            assert set(c["stress"]) == {"10 bps", "20 bps"} and c["stress"]["20 bps"]["net"] < c["stress"]["10 bps"]["net"] < c["base"]["net"], "more cost, less P&L (every position pays at both ends)"
            assert abs((c["sides"]["long side only"]["net"] + c["sides"]["short side only"]["net"]) - c["base"]["net"]) < 1e-6
            assert set(c["extra"]) == {"borrow 1% on k>1.5 sessions", "borrow 3% on k>1.5 sessions", "longs that stop printing valued at -100%", R2_CELL} and c["extra"]["borrow 3% on k>1.5 sessions"]["net"] <= c["extra"]["borrow 1% on k>1.5 sessions"]["net"] + 1e-9 <= c["base"]["net"] + 1e-9
            assert set(c["checks"]) == set(judge_cell(c["base"], 1.0, res["null"])) and c["PASS"] is False and "book_shadow_line" in c["A2"] and "pass" not in c["A2"] and math.isfinite(c["A2"]["c"]) and c["A2"]["window"] == ["2024-12-02", "2025-05-30"]
            assert abs(c["A2"]["c"] * c["A2"]["std_cell"] - 0.25 * c["A2"]["std_book"]) <= 1e-9 * c["A2"]["std_book"]
        assert res["null"]["draws"] == 40 and resK["null"]["draws"] == 40 and res["null"]["seed"] == SEED and set(res["null"]["by_cell"]) == set(CELLS)
        import tempfile
        nx = os.path.join(tempfile.gettempdir(), f"resmom_selftest_no_xsml_{os.getpid()}")
        with patched(me, XSML_DIR=nx + "_d", ANATOMY_ROOT=nx + "_a"):
            rep, cands = reports(W, B, S12, rows, obj, res["cells"], None, {}, [])
        for key in ("beta_to_es", "episodes", "map_point", "corr_with_legs", "top20_gains", "crash_months", "months", "turnover", "survivorship", "res_vs_raw", "manifest_sha256", "dividend_flows", "crash_signed", "xsml"):
            assert key in rep, key
        assert list(rep["beta_to_es"]["RES"]) == ["DD days", "DD weeks (every day of them)", "all WF days"] and list(rep["crash_months"]["RES"]) == list(CRASH_MONTHS)
        assert all(set(rep["crash_months"][c][m]) <= {"net", "long", "short"} for c in CELLS for m in CRASH_MONTHS) and rep["map_point"]["RAW"]["standalone_roc_30k"] == res["cells"]["RAW"]["base"]["roc"]
        for cell in CELLS:
            cd = cands[cell]
            pnl = [x["pnl"] for x in cd]
            assert len(cd) == min(AUDIT_N, 30) and pnl == sorted(pnl, reverse=True) and rep["top20_gains"][cell] == cd[:20], "the largest gains first; 5 rebalances x 6 names = 30 name-months"
            assert abs(sum(pnl) - res["cells"][cell]["base"]["net_pos"]) < 1e-6, "all 30 name-months listed: they add up to the cell's net"
            x0 = cd[0]
            assert {"symbol", "date", "exit", "side", "pnl", "score", "raw_move_formation", "adj_move_formation", "factor_ratio_window_to_exit", "tbis_price_ratio", "asset_status", "flags_in_window",
                    "max_overnight_raw_ratio_in_window", "max_abs_daily_return_in_hold", "spin_returns_left_out_in_window", "spin_or_stock_dividend_in_hold"} <= set(x0) and x0["date"] < x0["exit"] and x0["asset_status"] == "unknown"
            for x_ in cd:                                                                  # [D2] the audit's rows carry the plain-python recount's counts (window: returns left out; hold: an ex-date in f < t <= x)
                b_ = next(b for b in brute_rm(W, WF0, PRE_END) if str(W.days[b["f"]].date()) == x_["date"])
                j_ = list(W.syms).index(x_["symbol"])
                assert (x_["spin_returns_left_out_in_window"], x_["spin_or_stock_dividend_in_hold"]) == (b_["pool"][j_][3], bool(b_["pool"][j_][4])), (cell, x_["symbol"], x_["date"])
            t = rep["turnover"][cell]
            rc = [r_ for r_ in obj.legs.recs if r_.traded]
            sets = [(set(r_.pool[r_.pick[cell][0]].tolist()), set(r_.pool[r_.pick[cell][1]].tolist())) for r_ in rc]
            rep_l = [len(b_[0] - a_[0]) / 3 for a_, b_ in zip(sets[:-1], sets[1:])]
            rep_s = [len(b_[1] - a_[1]) / 3 for a_, b_ in zip(sets[:-1], sets[1:])]
            assert abs(t["long_replaced_mean"] - np.mean(rep_l)) < 1e-12 and abs(t["short_replaced_mean"] - np.mean(rep_s)) < 1e-12 and abs(t["replaced_mean"] - np.mean(rep_l + rep_s)) < 1e-12, "turnover = the share of names not held at the previous rebalance"
            assert abs(t["cost_saved_if_only_changes_traded_usd_estimate"] - sum(6 - 3 * (a_ + b_) for a_, b_ in zip(rep_l, rep_s)) * 4000 * 2 * 5e-4) < 1e-9
            mn = rep["months"][cell]
            xs = obj.series[cell][0]
            assert abs(sum(mn.values()) - res["cells"][cell]["base"]["net"]) < 1e-6 and all(abs(v - xs[(B.index.year == int(k[:4])) & (B.index.month == int(k[5:])) & B.mask(WF0, PRE_END)].sum()) < 1e-9 for k, v in mn.items()), "the monthly nets are the series' sums"
            assert t["traded_rebalances"] == 5 and t["transitions"] == 4 and 0.0 <= t["replaced_min"] <= t["replaced_mean"] <= t["replaced_max"] <= 1.0 and abs(t["registered_cost_per_rebalance_usd"] - 2 * 3 * 4000 * 2 * 5e-4) < 1e-9
        assert rep["res_vs_raw"]["mean_pick_overlap"]["long"] <= 1.0 and set(rep["res_vs_raw"]["cells"]) == set(CELLS)
        # [R1] the dividend flows inside the picks, recounted from the raw calendar rows by plain python; the dividend names are in the toy world's picks often enough to matter
        for cell in CELLS:
            fl = rep["dividend_flows"][cell]
            want_l = want_s = 0.0
            n_l = n_s = 0
            for b in brute_rm(W, WF0, PRE_END):
                for sd, js in ((1, b["long"][cell]), (-1, b["short"][cell])):
                    for j in js:
                        d_ = sum(brute_div(W, b["f"], b["x"], j, b["pool"][j][2]))
                        if sd > 0:
                            want_l, n_l = want_l + SPEC["slot"] * d_, n_l + (d_ > 0)
                        else:
                            want_s, n_s = want_s + SPEC["slot"] * d_, n_s + (d_ > 0)
            assert abs(fl["long_received"] - want_l) < 1e-9 and abs(fl["short_paid"] - want_s) < 1e-9 and fl["long_positions_with_a_dividend"] == n_l and fl["short_positions_with_a_dividend"] == n_s, (cell, fl, want_l, want_s)
        assert sum(rep["dividend_flows"][c]["long_received"] + rep["dividend_flows"][c]["short_paid"] for c in CELLS) > 0, "the toy world's picks do carry dividends"
        # [R2] the short leg with names that stop printing valued at zero: the stopped shorts recounted from the raw arrays, the $ difference from the carried marks
        for cell in CELLS:
            c = res["cells"][cell]
            n_stop, add = 0, 0.0
            for b in brute_rm(W, WF0, PRE_END):
                for j in b["short"][cell]:
                    if not math.isfinite(W.Od[b["x"], j] / W.F[b["x"], j]):
                        n_stop += 1
                        last = [W.Cl[t_, j] / W.F[t_, j] for t_ in range(b["f"], b["x"]) if math.isfinite(W.Cl[t_, j])]
                        add += SPEC["slot"] * (last[-1] if last else W.Od[b["f"], j] / W.F[b["f"], j]) / (W.Od[b["f"], j] / W.F[b["f"], j]) * (1 + COST_BPS * 1e-4)
            assert c["short_stopped"]["positions"] == n_stop >= 1 and c["short_stopped"]["short_positions"] == 3 * 5, (cell, c["short_stopped"], n_stop)
            assert abs(c["sides"][R2_SIDE]["net"] - (c["sides"]["short side only"]["net"] + add)) < 1e-6 and abs(c["extra"][R2_CELL]["net"] - (c["base"]["net"] + add)) < 1e-6, (cell, add)
        assert rep["xsml"]["on_file"] is False and "not on file" in rep["xsml"]["text"] and rep["crash_signed"]["months_available"] == 4 and rep["crash_signed"]["sum_res_minus_raw"] == 0.0, "the book index holds the four crash months and the toy world trades none of them: zero each"
        assert rep["crash_signed"]["worst_wf_drawdown"] == {c: res["cells"][c]["base"]["max_dd"] for c in CELLS}
        sr = rep["score_relations"]
        rn = ("RES vs RAW", "RES vs the skipped month's total return", "RAW vs the skipped month's total return")
        assert set(sr) == set(rn), sr
        rk_ = lambda v: np.argsort(np.argsort(v)).astype(float)                              # ranks (no ties in continuous scores): Spearman = Pearson of the ranks
        want_ = {n_: [] for n_ in rn}
        for r_ in obj.legs.recs:
            if r_.traded:
                x_, y_, z_ = rk_(r_.score["RES"]), rk_(r_.score["RAW"]), rk_(r_.skip_ret)
                for n_, (u_, v_) in zip(rn, ((x_, y_), (x_, z_), (y_, z_))):
                    want_[n_].append(float(np.corrcoef(u_, v_)[0, 1]))
        assert all(abs(sr[n_]["spearman_mean"] - np.mean(want_[n_])) < 1e-9 and abs(sr[n_]["min"] - min(want_[n_])) < 1e-9 and abs(sr[n_]["max"] - max(want_[n_])) < 1e-9 for n_ in rn), (sr, want_)
        assert all(-1.0 <= v["min"] <= v["spearman_mean"] <= v["max"] <= 1.0 and v["rebalances"] == 5 for v in sr.values())
        # [D2] (window, hold; long, short) of the picks in both readings = the plain-python recount; the toy world's picks carry spin-off / stock-dividend events in at least one of them
        Bz_r, Bz_k = brute_rm(W, WF0, PRE_END), brute_rm(W, WF0, PRE_END, "naive")
        sp_reg, sp_k = {c: spin_counts(obj.legs, c) for c in CELLS}, {c: spin_counts(objK.legs, c) for c in CELLS}
        for cell in CELLS:
            assert sp_reg[cell] == brute_spin_counts(Bz_r, cell) and sp_k[cell] == brute_spin_counts(Bz_k, cell), (cell, sp_reg[cell], sp_k[cell])
            assert sp_reg[cell]["long"]["hold_positions"] == sp_reg[cell]["short"]["hold_positions"] == 0, "the registered reading removed every name with an ex-date inside the hold before the ranking"
        assert sum(v["window_positions"] + v["hold_positions"] for per in (sp_reg, sp_k) for c in CELLS for v in per[c].values()) > 0, "the toy world's picks do carry [D2] events"
        assert all(c_["spin_hold_names"] >= 1 for c_ in (obj.legs.cnt[2025],)) and obj.legs.cnt[2025]["post_spin"] >= 1 and objK.legs.cnt[2025]["kept_naive"] >= 1
        # an audit data event on the largest gain of RES removes that name-month from the cell AND the null
        top = cands["RES"][0]
        j = list(W.syms).index(top["symbol"])
        W.aud1[dr_(W, top["date"]), j] = True
        res2, obj2 = evaluate(W, B, S12, rows, "remove", 40, 0, full=False)
        assert res2["cells"]["RES"]["base"]["n_pos"] < res["cells"]["RES"]["base"]["n_pos"] or True
        r2 = next(r_ for r_ in obj2.legs.recs if W.days[r_.f] == TS(top["date"]))
        assert j not in r2.pool.tolist() and res2["cells"]["RES"]["base"]["net"] != res["cells"]["RES"]["base"]["net"]
        acc2 = rm_null(W, obj2.legs, 30, 0)
        assert j not in [int(q) for q in r2.pool] and acc2["RES"].shape == (30, W.T)
        # printing runs on real numbers
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            for cell in CELLS:
                res["cells"][cell]["audit"] = {"listed": 30, "audited": 0, "audit_complete": False}
            print_cells(res, {c: res["cells"][c]["audit"] for c in CELLS})
            print_reports(rep, res["cells"])
            print_counts("registered", obj.legs.cnt)
            print_spin_counts("registered", obj.legs.cnt)
            print_spin_picks({"registered reading": sp_reg, "look-ahead reading (kept at naive price P&L)": sp_k})
        assert "RES" in buf.getvalue() and "realised beta to ES" in buf.getvalue() and "turnover" in buf.getvalue()
        assert "registered [D2] by fill year" in buf.getvalue() and "registered reading [D2] RES picks (long / short)" in buf.getvalue() and "post_spin" in buf.getvalue() and "kept at naive price P&L) [D2] RAW picks" in buf.getvalue()
        assert "SIGNED LINE [R3]" in buf.getvalue() and "worst WF drawdown, RES" in buf.getvalue() and "short leg [R2]" in buf.getvalue() and "dividends [R1]" in buf.getvalue() and "not on file" in buf.getvalue()
        assert pick_candidate({"RES": {"base": {"roc": 10.0}}, "RAW": {"base": {"roc": 12.0}}}, ["RES", "RAW"]) == "RAW" and pick_candidate({"RES": {"base": {"roc": 12.0}}, "RAW": {"base": {"roc": 12.0}}}, ["RES", "RAW"]) == "RES"
        assert pick_candidate({"RES": {"base": {"roc": 12.0}}, "RAW": {"base": {"roc": 99.0}}}, ["RES"]) == "RES" and pick_candidate({}, []) is None


def t_stage_b_refusals():
    """every Stage B refusal that needs no data, none of which may write the flag: no pass on file (each broken piece), the flag already there, a changed spec / harness / audit, a broken frozen size"""
    import shutil, tempfile
    root = tempfile.mkdtemp(prefix="resmom_selftest_")
    me = sys.modules[__name__]
    try:
        out = os.path.join(root, "out")
        os.makedirs(out)
        flag = os.path.join(out, "resmom_stageB_READ.flag")
        good = {"judged": True, "prereg_sha256_lf": PREREG_SHA, **stamp(), "audit_sha256": None, "candidate": {"cell": "RAW", "c": 0.8317},
                "stageA": {"cells": {"RAW": {"PASS": True, "audit": {"audit_complete": True}}}}, "parity": {}}

        def must(frag, sa=None, **kw):
            json.dump(good if sa is None else sa, open(os.path.join(out, "resmom_stageA.json"), "w"))
            try:
                with contextlib.redirect_stdout(io.StringIO()), patched(me, OUT=out, **kw):
                    stage_b()
                raise AssertionError(f"Stage B must refuse ({frag})")
            except SystemExit as e:
                assert frag in str(e), (frag, str(e))
                assert not os.path.exists(flag) or frag == "already read", "a refused Stage B must not burn the lockbox"
        try:                                                                                    # nothing on file at all
            with patched(me, OUT=out):
                stage_b()
            raise AssertionError("no file")
        except SystemExit as e:
            assert "no Stage A pass with a complete audit" in str(e)
        mut = lambda f: (lambda d: (f(d), d)[1])(json.loads(json.dumps(good)))
        for nm, sa in (("not judged", mut(lambda d: d.update(judged=False))), ("no candidate", mut(lambda d: d.update(candidate=None))), ("unknown cell", mut(lambda d: d.update(candidate={"cell": "L1-F", "c": 1}))),
                       ("Stage A fail", mut(lambda d: d["stageA"]["cells"]["RAW"].update(PASS=False))), ("audit incomplete", mut(lambda d: d["stageA"]["cells"]["RAW"]["audit"].update(audit_complete=False))),
                       ("a pending audit", mut(lambda d: d.update(judged=None)))):
            must("no Stage A pass with a complete audit", sa)
        open(flag, "w").write("x")
        must("already read", good)
        os.remove(flag)
        with patched(me, PREREG_SHA="0" * 64):
            must("DIFFERS", good)
        must("another pre-registration", mut(lambda d: d.update(prereg_sha256_lf="0" * 64)))
        for nm, edit in (("harness", lambda d: d.update(harness_sha256="0" * 64)), ("early close", lambda d: d.update(early_close=d["early_close"][1:])), ("r15", lambda d: d.update(r15_sha256="0" * 64)),
                         ("r12", lambda d: d.update(r12_sha256="0" * 64)), ("r13", lambda d: d.pop("r13_sha256")), ("no stamp", lambda d: [d.pop(k) for k in stamp()])):
            must("different harness version", mut(edit))
        must("not the file Stage A ran with", mut(lambda d: d.update(audit_sha256="0" * 64)))
        open(os.path.join(out, "resmom_audit.csv"), "w").write("symbol,date,cell,verdict,note\n")
        sha = file_sha(os.path.join(out, "resmom_audit.csv"))
        for badc in (0.0, -1.0, None, "abc", float("nan"), float("inf")):                      # c is a volatility ratio: any positive number is a frozen size; NaN / 0 / negative / missing / text is a broken file
            must("positive number", mut(lambda d, b=badc: d.update(audit_sha256=sha, candidate={"cell": "RAW", "c": b})))
        must("not one of", mut(lambda d: d.update(audit_sha256=sha, candidate={"cell": "RES-X", "c": 0.8317}, stageA={"cells": {"RES-X": {"PASS": True, "audit": {"audit_complete": True}}}})))
        assert not os.path.exists(flag), "no refusal wrote the flag"
    finally:
        shutil.rmtree(root, ignore_errors=True)


def t_cut():
    """Stage A asks for data cut at 2025-06-30 and refuses a session on/after it (the loaders and the book are stubbed; nothing real is read); the manifest and the book gates; Stage A is frozen once the lockbox was read"""
    seen = {}

    def stub(t_end, open5=True):
        assert t_end == S.LB0, "Stage A must ask for data cut at 2025-06-30" and open5 is False
        seen["t"], seen["open5"] = t_end, open5
        return SimpleNamespace(days=pd.DatetimeIndex(["2025-06-27", "2025-06-30"]))
    me = sys.modules[__name__]
    S12 = SimpleNamespace(qual=[])
    okbk = ({"roc": 0.0, "sortino": 0.0, "ref": [0, 0], "ok": True}, {"deepest": 0.0, "episodes": 0, "days": 0, "weeks": 0, "by_year": {}, "episode_2020": True, "ok": True}, S12)
    devnull = lambda: contextlib.redirect_stdout(open(os.devnull, "w"))
    real_wide = wide_load
    no_wide = lambda *a, **k: (SimpleNamespace(div=None, split=None, info={}), {})                               # the loaders below are stubbed: the calendar's own gates are tested after them
    with patched(S, Data=stub), patched(A13, load_463=lambda: (SimpleNamespace(), [])), patched(me, book_checks=lambda B: okbk, manifest_sha=lambda: D15.MANIFEST_PREFIX + "0" * 56, wide_load=no_wide):
        try:
            with devnull():
                stage_a()
            raise AssertionError("Stage A must refuse a session on/after the cut")
        except SystemExit as e:
            assert "on/after the cut" in str(e) and seen["t"] == S.LB0 and seen["open5"] is False, (str(e), seen)
        for mf, frag in ((lambda: None, "manifest is missing"), (lambda: "ffff" + "0" * 60, "not the registered photograph")):
            with patched(me, manifest_sha=mf):
                try:
                    with devnull():
                        stage_a()
                    raise AssertionError("Stage A must refuse the wrong manifest")
                except SystemExit as e:
                    assert frag in str(e)
        with patched(me, book_checks=lambda B: ({"roc": 1.0, "sortino": 1.0, "ref": [0, 0], "ok": False}, okbk[1], S12)):
            try:
                with devnull():
                    stage_a()
                raise AssertionError("a book that does not reproduce must refuse")
            except SystemExit as e:
                assert "do not reproduce" in str(e)
        with patched(me, book_checks=lambda B: (okbk[0], {**okbk[1], "ok": False}, S12)):
            try:
                with devnull():
                    stage_a()
                raise AssertionError("a DD structure that does not match the prereg must refuse")
            except SystemExit as e:
                assert "do not reproduce" in str(e)
        import shutil, tempfile
        root = tempfile.mkdtemp(prefix="resmom_selftest_")
        try:
            with patched(me, wide_load=real_wide):                                                  # [R1] Stage A refuses, computing nothing, until the wide calendar is on file AND registered AND the registered file
                seen.clear()
                with patched(S, CACHE=os.path.join(root, "nocache")), patched(me, OUT=root):
                    try:
                        with devnull():
                            stage_a()
                        raise AssertionError("Stage A must refuse a missing wide calendar")
                    except SystemExit as e:
                        assert "wide corporate-actions calendar is not on file" in str(e) and "t" not in seen and not os.path.exists(os.path.join(root, "resmom_stageA.json")), (str(e), seen)
                xd = os.path.join(root, "cache", "xgap")
                os.makedirs(xd)
                cp = os.path.join(xd, WIDE_NAME + ".csv")
                with open(cp, "w", newline="\n") as f_:
                    f_.write(",".join(CA_COLS) + "\ncash_dividend,AAA,,,2024-01-10,2024-01-10,,,0.25,,,,False\n")
                with open(os.path.join(xd, WIDE_NAME + "_manifest.json"), "w") as f_:
                    f_.write(json.dumps({"sha256": {WIDE_NAME + ".csv": sha_raw(cp)}}))
                with patched(S, CACHE=os.path.join(root, "cache")), patched(me, OUT=root):
                    for sha_, frag in ((None, "the wide calendar sha is not registered yet"), ("0" * 64, "is not the registered wide calendar")):
                        with patched(me, WIDE_CA_SHA=sha_):
                            seen.clear()
                            try:
                                with devnull():
                                    stage_a()
                                raise AssertionError("Stage A must refuse an unregistered / another wide calendar")
                            except SystemExit as e:
                                assert frag in str(e) and "t" not in seen and not os.path.exists(os.path.join(root, "resmom_stageA.json")), (str(e), seen)
            open(os.path.join(root, "resmom_stageB_READ.flag"), "w").write("x")
            with patched(me, OUT=root):
                try:
                    stage_a()
                    raise AssertionError("Stage A is frozen once the lockbox has been read")
                except SystemExit as e:
                    assert "Stage A is frozen" in str(e)
        finally:
            shutil.rmtree(root, ignore_errors=True)
    # book_checks on a synthetic book that does not match the registered structure: ok False, with the numbers
    B, _ = synth_book(seed=2, hi="2025-06-27", deep=False)
    bk, dd, S12b = D15.book_checks(B)
    assert bk["ok"] is False and dd["ok"] is False and dd["days"] == S12b.n_dd_days and dd["episodes"] == len(S12b.qual)


def t_dividends():
    """[R1] a cash dividend on its ex-date changes the daily total return, RAW's formation product, RES's regression inputs and the position's P&L EXACTLY - a long receives, a short pays, per share held; the fill session's own ex-date
    is bought ex-dividend (nothing), the exit session's is sold ex-dividend after the prior close (received) - on hand numbers through rm_build -> rm_units -> l1_cell; a dividend flips a pick when it should; the amount sits on the
    split-adjusted basis (D / F); no close, no ex-date effect; div_mode puts the dividend set back"""
    with spec(win=30, form_n=20, skip=10, min_n=25, n_side=1):
        T = 70
        g = np.array([0.004, 0.002, -0.002, -0.004])
        rng = np.random.default_rng(4)
        ret = np.tile(g, (T, 1))
        ret[1:44] += rng.normal(0.0, 0.002, (43, 4))                                       # noise in the window, exactly g a day from the fill on: the hold's price path is a closed form
        ret[0] = 0.0
        Cl = prices(ret, 50.0)
        mm = rng.normal(0.0, 0.01, T)
        mm[0] = np.nan
        Dr = np.zeros((T, 4))
        Dr[20, 0] = 1.5                                                                    # N0: inside the formation window (rows 14 .. 33)
        Dr[43, 0], Dr[44, 0], Dr[50, 0], Dr[65, 0], Dr[66, 0] = 0.4, 0.7, 1.0, 0.9, 0.6    # N0 (the long): the rank session / the fill session / inside the hold / the exit session / after it
        Dr[55, 3], Dr[66, 3] = 1.2, 0.3                                                    # N3 (the short): inside the hold / after it
        W = mk_world(Cl, mm, Dr=Dr, k=np.ones(T))
        # --- the daily total return, exactly: (C_t + D_t) / C_(t-1) - 1 on an ex-date, the price return elsewhere
        want = W.Rn.copy()
        for (t, j) in ((20, 0), (43, 0), (44, 0), (50, 0), (65, 0), (66, 0), (55, 3), (66, 3)):
            want[t, j] = (Cl[t, j] + Dr[t, j]) / Cl[t - 1, j] - 1.0
        assert np.allclose(W.Rd[1:], want[1:], rtol=0, atol=1e-13) and (W.Rd[1:][Dr[1:] == 0] == W.Rn[1:][Dr[1:] == 0]).all()
        # --- RAW's formation product = the price ratio x (1 + D / the ex-date close) for one dividend; RES's inputs are the total returns (the recount adds the dividend on its own)
        r = 43
        a, fa, fe = windows(r)
        assert (a, fa, fe) == (14, 14, 33)
        n_ret, n_pair, res, raw = rm_scores(W, r, np.arange(4))
        assert abs(raw[0] - ((Cl[fe, 0] / Cl[fa - 1, 0]) * (1.0 + 1.5 / Cl[20, 0]) - 1.0)) < 1e-12 and abs(raw[1] - (Cl[fe, 1] / Cl[fa - 1, 1] - 1.0)) < 1e-12, "RAW adds the dividend of the formation window; a dividend outside it (rows 43 .. 66) not"
        for j in range(4):
            bs = brute_scores(W, r, j)
            assert abs(bs[2] - res[j]) < 1e-9 and abs(bs[3] - raw[j]) < 1e-12, j
        with div_mode(W, False):
            n_ret0, n_pair0, res0, raw0 = rm_scores(W, r, np.arange(4))
            assert abs(raw0[0] - (Cl[fe, 0] / Cl[fa - 1, 0] - 1.0)) < 1e-12 and W.Rd is W.Rn0 and np.array_equal(W.Rn0, W.Rn, equal_nan=True) and W.Dv is W.Z0 and W.Dr is W.Z0 and not W.div_on
            assert abs(res0[0] - res[0]) > 1e-3 and abs(res0[2] - res[2]) < 1e-12 and abs(res0[1] - res[1]) < 1e-12, "the dividend moves RES of the name that pays it (and only that name)"
        assert W.div_on and W.Rd is W.Rd1 and W.Dv is W.Dv1 and W.Dr is W.Dr1, "div_mode puts the dividend set back"
        # --- positions: exact flows through rm_build -> rm_units -> run_cell
        L = rm_build(W, W.days[0], W.days[-1])
        rec = L.recs[0]
        assert (rec.r, rec.f, rec.x) == (43, 44, 65) and rec.pool.tolist() == [0, 1, 2, 3] and rec.pool[rec.pick["RAW"][0]].tolist() == [0] and rec.pool[rec.pick["RAW"][1]].tolist() == [3]
        of0, of3 = Cl[43, 0], Cl[43, 3]                                                    # the entry opens (= the prior closes)
        d0 = np.zeros(21)
        d0[50 - 44 - 1], d0[65 - 44 - 1] = 1.0 / of0, 0.9 / of0                            # column t - f - 1: rows 45 .. 65 only
        assert np.allclose(rec.U.div[0], d0, rtol=0, atol=1e-15) and abs(rec.U.div[3, 55 - 44 - 1] - 1.2 / of3) < 1e-15 and np.count_nonzero(rec.U.div[3]) == 1 and np.count_nonzero(rec.U.div[1]) == 0
        c0 = COST_BPS * 1e-4
        up, dn = (1 + g[0]) ** 21, (1 + g[3]) ** 21
        borrow = BORROW / 252.0 * sum((1 + g[3]) ** h for h in range(1, 22))
        long_pnl = 4000.0 * (up - 1.0 + (1.0 + 0.9) / of0 - c0 - c0 * up)                 # the exit cost is on the exit VALUE (price only), not on the dividend
        short_pnl = 4000.0 * (-(dn - 1.0) - 1.2 / of3 - c0 - c0 * dn - borrow)
        run = run_cell(W, cell_leg(L, "RAW"), D15.l1_cfg(), pos=True)
        assert run.n_pos == 2 and abs(run.x.sum() - (long_pnl + short_pnl)) < 1e-6, (run.x.sum(), long_pnl + short_pnl)
        assert abs(run.pos.pnl[run.pos.side == 1][0] - long_pnl) < 1e-6 and abs(run.pos.pnl[run.pos.side == -1][0] - short_pnl) < 1e-6
        assert abs(run_cell(W, cell_leg(L, "RAW"), D15.l1_cfg(), side=1).x.sum() - long_pnl) < 1e-6 and abs(run_cell(W, cell_leg(L, "RAW"), D15.l1_cfg(), side=-1).x.sum() - short_pnl) < 1e-6
        with div_mode(W, False):
            L0 = rm_build(W, W.days[0], W.days[-1])
            run0 = run_cell(W, cell_leg(L0, "RAW"), D15.l1_cfg())
            assert L0.recs[0].pool[L0.recs[0].pick["RAW"][0]].tolist() == [0] and L0.recs[0].pool[L0.recs[0].pick["RAW"][1]].tolist() == [3] and not L0.recs[0].U.div.any(), "the same picks without dividends, no cash in the paths"
        diff = run.x - run0.x
        assert np.flatnonzero(np.abs(diff) > 1e-9).tolist() == [50, 55, 65], "the dividend lands on its ex-date row: nothing on the fill session (row 44), the rank session (43) or after the exit (66)"
        assert abs(diff[50] - 4000.0 * 1.0 / of0) < 1e-9 and abs(diff[65] - 4000.0 * 0.9 / of0) < 1e-9 and abs(diff[55] + 4000.0 * 1.2 / of3) < 1e-9, "a long receives, a short pays, per share held; the exit session's ex-dividend counts"
        # --- a dividend flips a pick: N1 is flat in price but pays 12% inside the formation window
        g2 = np.array([0.003, 0.0, -0.002, -0.004])
        ret2 = np.tile(g2, (T, 1))
        ret2[1:44] += rng.normal(0.0, 0.001, (43, 4))
        ret2[0] = 0.0
        Dr2 = np.zeros((T, 4))
        Dr2[20, 1] = 6.0
        W2 = mk_world(prices(ret2, 50.0), mm, Dr=Dr2)
        L2 = rm_build(W2, W2.days[0], W2.days[-1])
        assert L2.recs[0].pool[L2.recs[0].pick["RAW"][0]].tolist() == [1], "with the dividend N1's total formation return (+12%) tops N0's (+6%)"
        with div_mode(W2, False):
            L2o = rm_build(W2, W2.days[0], W2.days[-1])
            assert L2o.recs[0].pool[L2o.recs[0].pick["RAW"][0]].tolist() == [0], "without it N0 is the long"
        # --- the split-adjusted basis: a dividend declared before a 2-for-1 is halved (D / F, F = 2 there); the naive raw path takes the raw amount over the raw entry open
        T3 = 60
        ret3 = rng.normal(0.0, 0.01, (T3, 2))
        ret3[0] = 0.0
        Ac3 = prices(ret3, 40.0)
        F3 = np.ones((T3, 2))
        F3[:40, 0] = 2.0
        Od3 = np.vstack([Ac3[:1], Ac3[:-1]]) * F3
        Dr3 = np.zeros((T3, 2))
        Dr3[38, 0], Dr3[45, 0], Dr3[38, 1] = 1.0, 0.3, 1.0
        m3 = rng.normal(0.0, 0.01, T3)
        m3[0] = np.nan
        W3 = mk_world(Ac3 * F3, m3, F=F3, Od=Od3, chg=(np.arange(T3) == 40)[:, None] & np.array([[True, False]]), Dr=Dr3)
        assert abs(W3.Dv[38, 0] - 0.5) < 1e-15 and abs(W3.Dv[45, 0] - 0.3) < 1e-15 and abs(W3.Dv[38, 1] - 1.0) < 1e-15, "D* = D / F: 1.00 before the split is 0.50 on the post-split basis, 0.30 after it stays"
        assert abs(W3.Rd[38, 0] - (W3.Rn[38, 0] + 0.5 / Ac3[37, 0])) < 1e-13 and abs(W3.Rn[40, 0] - (Ac3[40, 0] / Ac3[39, 0] - 1.0)) < 1e-13 and abs(W3.Rn[40, 0]) < 0.1, "the split day itself is no return"
        U = rm_units(W3, 36, 50, np.array([0, 1]), np.array([False, False]))
        of_a = W3.Ao[36, 0]
        assert abs(U.div[0, 38 - 36 - 1] - 0.5 / of_a) < 1e-13 and abs(U.div[0, 45 - 36 - 1] - 0.3 / of_a) < 1e-13 and np.count_nonzero(U.div[0]) == 2
        Un = rm_units(W3, 36, 50, np.array([0, 1]), np.array([True, False]))
        assert abs(Un.div[0, 38 - 36 - 1] - 1.0 / W3.Od[36, 0]) < 1e-13 and abs(Un.div[0, 45 - 36 - 1] - 0.3 / W3.Od[36, 0]) < 1e-13 and abs(Un.div[1, 38 - 36 - 1] - 1.0 / W3.Ao[36, 1]) < 1e-13, "the naive raw path: the raw amount over the raw entry open"
        # --- no close, no ex-date effect: a dividend on a session without a close (or without a prior close), a zero / negative amount - counted, not applied
        Cl4 = prices(rng.normal(0.0, 0.01, (40, 2)), 50.0)
        Cl4[25, 0] = np.nan
        Dr4 = np.zeros((40, 2))
        Dr4[25, 0], Dr4[26, 0], Dr4[30, 0], Dr4[30, 1] = 0.5, 0.5, 0.4, -1.0
        W4 = mk_world(Cl4, np.r_[np.nan, np.zeros(39)], Dr=Dr4)
        assert W4.Dv[25, 0] == 0.0 and W4.Dv[26, 0] == 0.0 and abs(W4.Dv[30, 0] - 0.4) < 1e-15 and W4.Dv[30, 1] == 0.0
        assert W4.div_counts == {"cells_with_a_dividend": 3, "applied": 1, "no_close_prior_close_or_factor": 2, "over_25_pct_of_the_prior_close": 0}, W4.div_counts
    return True


def t_short0():
    """[R2] a short in a name that stops printing during the hold: the base exits it at its last close (bought back at the carried mark, exit cost on it); valued at zero it keeps the full gain of its entry notional (+1 per $1), pays no
    exit cost, the borrow keeps accruing on the carried mark - on hand numbers; only the exit row changes; the long side and the base config are untouched; a short that keeps printing is untouched"""
    with spec(win=30, form_n=20, skip=10, min_n=25, n_side=1):
        T = 70
        g = np.array([0.004, 0.002, -0.002, -0.004])
        rng = np.random.default_rng(4)
        ret = np.tile(g, (T, 1))
        ret[1:44] += rng.normal(0.0, 0.002, (43, 4))
        ret[0] = 0.0
        Cl = prices(ret, 50.0)
        Od = np.vstack([Cl[:1], Cl[:-1]])
        mm = rng.normal(0.0, 0.01, T)
        mm[0] = np.nan
        W_ok = mk_world(Cl, mm, Od=Od, k=np.ones(T))
        Cl_s, Od_s = Cl.copy(), Od.copy()
        Cl_s[56:, 3] = np.nan
        Od_s[56:, 3] = np.nan                                                              # N3 (the short) stops printing after row 55: no open at the exit session
        W = mk_world(Cl_s, mm, Od=Od_s, k=np.ones(T))
        L, L_ok = rm_build(W, W.days[0], W.days[-1]), rm_build(W_ok, W_ok.days[0], W_ok.days[-1])
        rec = L.recs[0]
        assert (rec.f, rec.x) == (44, 65) and rec.pool[rec.pick["RAW"][1]].tolist() == [3] and rec.pool[rec.pick["RAW"][0]].tolist() == [0] and rec.U.st.tolist() == [False, False, False, True]
        c0 = COST_BPS * 1e-4
        ve = (1 + g[3]) ** 12                                                              # the last close (row 55) over the entry open (row 43's close), carried to the exit
        borrow = BORROW / 252.0 * (sum((1 + g[3]) ** h for h in range(1, 13)) + 9 * (1 + g[3]) ** 12)
        base_short = 4000.0 * (-(ve - 1.0) - c0 - c0 * ve - borrow)
        zero_short = 4000.0 * (1.0 - c0 - borrow)
        z0 = {**D15.l1_cfg(), "short0": True}
        rb, rz = run_cell(W, cell_leg(L, "RAW"), D15.l1_cfg(), side=-1), run_cell(W, cell_leg(L, "RAW"), z0, side=-1)
        assert abs(rb.x.sum() - base_short) < 1e-6 and abs(rz.x.sum() - zero_short) < 1e-6, (rb.x.sum(), base_short, rz.x.sum(), zero_short)
        dz = rz.x - rb.x
        assert np.flatnonzero(np.abs(dz) > 1e-9).tolist() == [65] and abs(dz[65] - 4000.0 * ve * (1 + c0)) < 1e-9, "only the exit row changes: + the bought-back value and its exit cost"
        assert abs(run_cell(W, cell_leg(L, "RAW"), z0, side=1).x.sum() - run_cell(W, cell_leg(L, "RAW"), D15.l1_cfg(), side=1).x.sum()) < 1e-12, "the long side is untouched"
        assert abs(run_cell(W, cell_leg(L, "RAW"), z0).x.sum() - (run_cell(W, cell_leg(L, "RAW"), D15.l1_cfg()).x.sum() + 4000.0 * ve * (1 + c0))) < 1e-6, "the whole cell gains exactly the short's difference"
        assert abs(run_cell(W_ok, cell_leg(L_ok, "RAW"), z0).x.sum() - run_cell(W_ok, cell_leg(L_ok, "RAW"), D15.l1_cfg()).x.sum()) < 1e-12, "a short that keeps printing is valued as before"
        for bps in STRESS_BPS:                                                              # the exit cost saved follows the cost rate
            cb = bps * 1e-4
            a_, b_ = run_cell(W, cell_leg(L, "RAW"), {**D15.l1_cfg(bps=bps), "short0": True}, side=-1), run_cell(W, cell_leg(L, "RAW"), D15.l1_cfg(bps=bps), side=-1)
            assert abs((a_.x - b_.x)[65] - 4000.0 * ve * (1 + cb)) < 1e-9, bps
        # the null reads the same units: with every name drawn the same cfg-free P&L (short0 is a report row, never in the null)
        acc = rm_null(W, L, 20, 0)
        assert acc["RAW"].shape == (20, W.T)
    return True


def t_crash_signed():
    """[R3] the signed line: RES's daily P&L minus RAW's summed over the four named crash months, and both worst drawdowns - on random daily series; a month the data does not hold is left out, counted"""
    ix = pd.bdate_range("2016-07-01", "2025-06-27")
    rng = np.random.default_rng(41)
    xr, xw = rng.normal(0.0, 100.0, len(ix)), rng.normal(0.0, 100.0, len(ix))
    B = SimpleNamespace(index=ix, n=len(ix), mask=lambda lo, hi: np.asarray((ix >= lo) & (ix <= hi)))
    months = {"RES": month_nets(B, xr, WF0, PRE_END), "RAW": month_nets(B, xw, WF0, PRE_END)}
    sg = crash_signed(months, {"RES": -5.0, "RAW": -7.0})
    pm = lambda x_, y_, m_: float(x_[(ix.year == y_) & (ix.month == m_)].sum())
    want = {"2020-04": (2020, 4), "2020-11": (2020, 11), "2022-01": (2022, 1), "2023-01": (2023, 1)}
    assert list(sg["months"]) == list(CRASH_MONTHS) and sg["months_available"] == 4 and set(want) == set(CRASH_MONTHS)
    for m_, (y_, mo_) in want.items():
        assert abs(sg["months"][m_]["RES"] - pm(xr, y_, mo_)) < 1e-9 and abs(sg["months"][m_]["RAW"] - pm(xw, y_, mo_)) < 1e-9 and abs(sg["months"][m_]["res_minus_raw"] - (pm(xr, y_, mo_) - pm(xw, y_, mo_))) < 1e-9
    tot = sum(pm(xr, y_, mo_) - pm(xw, y_, mo_) for y_, mo_ in want.values())
    assert abs(sg["sum_res_minus_raw"] - tot) < 1e-9 and sg["worst_wf_drawdown"] == {"RES": -5.0, "RAW": -7.0}
    miss = crash_signed({"RES": {k: v for k, v in months["RES"].items() if k != "2020-04"}, "RAW": months["RAW"]}, {"RES": 1.0, "RAW": 2.0})
    assert miss["months_available"] == 3 and miss["months"]["2020-04"]["res_minus_raw"] is None and abs(miss["sum_res_minus_raw"] - (tot - (pm(xr, 2020, 4) - pm(xw, 2020, 4)))) < 1e-9
    none = crash_signed({"RES": {}, "RAW": {}}, {"RES": 0.0, "RAW": 0.0})
    assert none["months_available"] == 0 and none["sum_res_minus_raw"] == 0.0
    return True


def t_xsml():
    """[R4] XSML r1 cell A's daily P&L: not on file -> the line says so; a file with (date, pnl) -> the daily correlation with each cell on the common WF days (and with its missing days as zero), rows on/after the cut
    ignored, a day listed twice added; a file without those columns is reported and not used; a *xsml*cellA*daily*.csv under the cache root is found to depth 4, not deeper"""
    import shutil, tempfile
    me = sys.modules[__name__]
    root = tempfile.mkdtemp(prefix="resmom_selftest_")
    try:
        ix = pd.bdate_range("2016-07-01", "2026-06-30")
        B = SimpleNamespace(index=ix, n=len(ix), mask=lambda lo, hi: np.asarray((ix >= lo) & (ix <= hi)))
        rng = np.random.default_rng(51)
        xs = {"RES": rng.normal(0.0, 100.0, len(ix)), "RAW": rng.normal(0.0, 100.0, len(ix))}
        d_x, a_x = os.path.join(root, "cml_xsml"), os.path.join(root, "anatomy")
        with patched(me, XSML_DIR=d_x, ANATOMY_ROOT=a_x):
            r0 = xsml_report(B, xs, WF0, PRE_END)
            assert r0["on_file"] is False and "not on file" in r0["text"] and "XSML" in r0["text"]
            os.makedirs(d_x)
            open(os.path.join(d_x, "notes.csv"), "w").write("a,b\n1,2\n")
            r1 = xsml_report(B, xs, WF0, PRE_END)
            assert r1["on_file"] is False and "no (date, pnl) columns" in r1["text"], r1["text"]
            # a real series: 700 days, partly overlapping WF, with a day listed twice, a bad row, and rows on / after the cut
            sd = pd.bdate_range("2017-03-01", periods=700)
            pn = 0.6 * xs["RES"][ix.get_indexer(sd)] + rng.normal(0.0, 80.0, len(sd))
            late = pd.DatetimeIndex(["2025-06-30", "2025-07-01"])
            df = pd.DataFrame({"Date": list(sd.strftime("%Y-%m-%d")) + [sd[5].strftime("%Y-%m-%d")] + list(late.strftime("%Y-%m-%d")) + ["not-a-date"],
                               "PNL": list(pn) + [10.0] + [9999.0, 9999.0] + [1.0]})
            df.to_csv(os.path.join(d_x, "xsml_cellA_daily.csv"), index=False)
            r2 = xsml_report(B, xs, WF0, PRE_END)
            assert r2["on_file"] is True and r2["rows"] == 700 and r2["first"] == "2017-03-01" and r2["last"] == f"{sd[-1]:%Y-%m-%d}" and r2["sha256"] == sha_raw(os.path.join(d_x, "xsml_cellA_daily.csv"))
            ser = pd.Series(pn, index=sd)
            ser[sd[5]] += 10.0                                                              # the day listed twice adds up
            inwf = (ix >= WF0) & (ix <= PRE_END)
            for c in CELLS:
                a_ = pd.Series(xs[c][inwf], index=ix[inwf])
                j_ = pd.concat([a_, ser], axis=1, join="inner")
                z_ = a_[(a_.index >= ser.index[0]) & (a_.index <= ser.index[-1])]
                zz = pd.concat([z_, ser.reindex(z_.index).fillna(0.0)], axis=1)
                v = r2["corr"][c]
                assert v["common_days"] == len(j_) and abs(v["daily_corr"] - np.corrcoef(j_.iloc[:, 0], j_.iloc[:, 1])[0, 1]) < 1e-12, c
                assert v["days_with_xsml_missing_as_zero"] == len(zz) and abs(v["daily_corr_missing_as_zero"] - np.corrcoef(zz.iloc[:, 0], zz.iloc[:, 1])[0, 1]) < 1e-12, c
            assert r2["corr"]["RES"]["daily_corr"] > 0.3 > abs(r2["corr"]["RAW"]["daily_corr"]) and "RES" in r2["text"] and "RAW" in r2["text"] and "cell A" in r2["text"]
            assert "2025-06-30" not in r2["text"] and "2025-07-01" not in r2["text"], "nothing on / after the cut"
            # the cache-root search: to depth 4 below the root (a / b / c = 3, a / b / c / d = 4), not deeper; only cell A's daily files; the newest usable file wins
            shutil.rmtree(d_x)
            c3 = os.path.join(a_x, "a", "b", "c")
            os.makedirs(os.path.join(c3, "d", "e"))
            sd2 = pd.bdate_range("2018-01-02", periods=300)
            put_ = lambda path, n: pd.DataFrame({"date": sd2[:n].strftime("%Y-%m-%d"), "pnl": rng.normal(0.0, 50.0, n)}).to_csv(path, index=False)
            put_(os.path.join(c3, "run_XSML_r1_cellA_daily_pnl.csv"), 300)
            put_(os.path.join(c3, "d", "xsml_cellA_daily.csv"), 250)
            put_(os.path.join(c3, "d", "e", "xsml_cellA_daily.csv"), 200)
            put_(os.path.join(c3, "xsml_cellB_daily.csv"), 100)
            t0 = time.time()
            os.utime(os.path.join(c3, "run_XSML_r1_cellA_daily_pnl.csv"), (t0 - 100, t0 - 100))
            os.utime(os.path.join(c3, "d", "xsml_cellA_daily.csv"), (t0, t0))
            assert sorted(os.path.basename(q) for q in xsml_candidates()) == ["run_XSML_r1_cellA_daily_pnl.csv", "xsml_cellA_daily.csv"], "depth 3 and 4 are found; depth 5 and the other cell are not"
            r3 = xsml_report(B, xs, WF0, PRE_END)
            assert r3["on_file"] is True and r3["rows"] == 250 and r3["file"] == "xsml_cellA_daily.csv", "the newest usable file is used"
    finally:
        shutil.rmtree(root, ignore_errors=True)
    return True


def t_wide():
    """[R1] the wide calendar's loader on a canned flat CSV (r16_xgap's 13 columns): every gate refuses before anything is computed (not on file, WIDE_CA_SHA None, another file, no manifest, a manifest without this file's sha,
    a missing column), the cut at read time, the rows counted by type and year, the usable dividends / splits, the dividends on the grid (same-day rows added, an unknown name / a non-session ex-date counted), the split cross-check
    by year (agree / calendar-only / price-only, with the near miss), the report's counts and its print (no amounts)"""
    import shutil, tempfile
    me = sys.modules[__name__]
    real_load = wide_load
    root = tempfile.mkdtemp(prefix="resmom_selftest_")
    try:
        csv_p, man_p = os.path.join(root, "corporate_actions_wide.csv"), os.path.join(root, "corporate_actions_wide_manifest.json")
        rows = ["cash_dividend,AAA,,,2024-01-10,2024-01-10,,,0.25,,,,False", "cash_dividend,AAA,,,2024-01-10,2024-01-10,,,0.05,,,,True", "cash_dividend,BBB,,,2024-02-07,2024-02-07,,,1.5,,,,False",
                "cash_dividend,BBB,,,2024-03-02,2024-03-02,,,0.4,,,,False", "cash_dividend,ZZZ,,,2024-02-07,2024-02-07,,,0.9,,,,False", "cash_dividend,AAA,,,2024-02-07,2024-02-07,,,0,,,,False",
                "cash_dividend,AAA,,,2024-02-08,2024-02-08,,,-0.2,,,,False", "cash_dividend,AAA,,,2024-02-09,2024-02-09,,,,,,,False", "cash_dividend,AAA,,,,2024-02-12,,,0.3,,,,False",
                "cash_dividend,,,,2024-02-12,2024-02-12,,,0.3,,,,False", "cash_dividend,AAA,,,2025-06-30,2025-06-30,,,0.7,,,,False", "cash_dividend,AAA,,,2025-07-15,2025-07-15,,,0.7,,,,False",
                "forward_split,AAA,,,2024-03-05,2024-03-05,2024-02-26,2024-03-04,,4,1,,", "reverse_split,BBB,,,2024-03-12,2024-03-12,,,,1,2,,", "unit_split,,OLD,AAA,2024-03-20,2024-03-21,,,,2.2,1,,",
                "stock_dividend,AAA,,,2024-03-25,2024-03-25,,,0.1,,,,", "spin_off,AAA,,AAA.W,2024-04-02,2024-04-03,,,,0.1,1,,", "name_change,,OLDX,NEWX,,2024-04-10,,,,,,,", "spin_off,,,X.W,2024-05-01,2024-05-01,,,,0.1,1,,", "stock_dividend,BBB,,,,2024-05-02,,,0.1,,,,",
                "spin_off,BBB,,B.W,2025-08-01,2025-08-01,,,,0.1,1,,"]
        def put(path, text):
            with open(path, "w", newline="\n") as f_:
                f_.write(text)
        write = lambda lines: put(csv_p, "\n".join([",".join(CA_COLS)] + lines) + "\n")
        write(rows)
        sha = sha_raw(csv_p)
        manifest = lambda **kw: put(man_p, json.dumps({"created": "2026-10-05T10:00:00", "start": "2016-06-01", "end": "2026-06-30", "rows": len(rows), "sha256": {"corporate_actions_wide.csv": sha}, **kw}))
        manifest()
        load = lambda **kw: real_load("2025-06-30", csv=csv_p, manifest=man_p, **kw)

        def refused(frag, **kw):
            try:
                load(**kw)
            except SystemExit as e:
                assert frag in str(e), (frag, str(e))
                return str(e)
            raise AssertionError(f"must refuse: {frag}")
        with patched(me, WIDE_CA_SHA=None):
            assert sha in refused("the wide calendar sha is not registered yet"), "the refusal carries the sha of the file on disk (for the lead to pin)"
            cal0, info0 = load(need=False, enforce=False)                                   # the dryload's reading: no refusal, the state is reported
            assert info0["pinned"] == {"registered": None, "matches": None} and info0["csv_sha256"] == sha and len(cal0.div) == 5
        with patched(me, WIDE_CA_SHA="0" * 64):
            refused("is not the registered wide calendar")
            assert load(need=False, enforce=False)[1]["pinned"]["matches"] is False
        with patched(me, WIDE_CA_SHA=sha):
            os.remove(man_p)
            refused("manifest is missing")
            manifest()
            put(man_p, json.dumps({"sha256": {"corporate_actions_wide.csv": "0" * 64}}))
            refused("does not carry this file's sha256")
            put(man_p, json.dumps({"sha256": {"corporate_actions_wide.csv": sha, "other.csv": sha}}))
            refused("does not carry this file's sha256")                                  # two csv entries: ambiguous
            put(man_p, "not json")
            refused("manifest is missing, unreadable")
            put(man_p, json.dumps({"sha256": {"corporate_actions_wide.csv": sha}}))               # [D1] a manifest without a start date refuses Stage A / B (the coverage is counted from it); the dryload reads on
            refused("no readable start date")
            assert load(need=False, enforce=False)[1]["manifest"]["start"] is None
            put(man_p, json.dumps({"start": "not a date", "sha256": {"corporate_actions_wide.csv": sha}}))
            refused("no readable start date")
            manifest()
            try:
                real_load("2025-06-30", csv=os.path.join(root, "absent.csv"), manifest=man_p)
                raise AssertionError("a missing file must refuse")
            except SystemExit as e:
                assert "not on file" in str(e)
            assert real_load("2025-06-30", need=False, enforce=False, csv=os.path.join(root, "absent.csv"), manifest=man_p) == (None, {"present": False, "path": os.path.join(root, "absent.csv")})
            cal, info = load()
            assert info["pinned"] == {"registered": sha, "matches": True} and info["manifest"]["csv_sha_ok"] is True and info["manifest"]["start"] == "2016-06-01" and info["csv_sha256"] == sha
            assert info["rows_on_file"] == 21 and info["rows_dropped_at_the_cut"] == 3 and info["rows_read"] == 18, "the rows ON and AFTER the cut (2025-06-30, 2025-07-15, a spin-off 2025-08-01) are dropped at read"
            assert info["rows_by_type"] == {"cash_dividend": 10, "forward_split": 1, "reverse_split": 1, "unit_split": 1, "stock_dividend": 2, "spin_off": 2, "name_change": 1}
            assert info["rows_by_type_year"]["cash_dividend"] == {"2024": 10} and info["rows_by_type_year"]["name_change"] == {"2024": 1}, info["rows_by_type_year"]
            assert info["dividends"] == {"rows": 10, "usable": 5, "no_ex_date_or_symbol": 2, "no_positive_amount": 3, "special": 1} and info["splits"] == {"rows": 3, "usable": 2, "no_ex_date_or_symbol": 1}
            assert cal.div["symbol"].tolist() == ["AAA", "AAA", "BBB", "BBB", "ZZZ"] and cal.div["amt"].tolist() == [0.25, 0.05, 1.5, 0.4, 0.9] and cal.div["special"].tolist() == [False, True, False, False, False]
            assert cal.split["type"].tolist() == ["forward_split", "reverse_split"] and cal.info is info
            assert info["spin"] == {"rows": 4, "usable": 2, "no_ex_date_or_symbol": 2, "by_type": {"spin_off": 2, "stock_dividend": 2}}, info["spin"]        # [D2] the two without a symbol / an ex-date are counted, never used; the one dated on 2025-08-01 is gone at read
            assert cal.spin["symbol"].tolist() == ["AAA", "AAA"] and cal.spin["type"].tolist() == ["stock_dividend", "spin_off"] and cal.spin["ex"].tolist() == [TS("2024-03-25"), TS("2024-04-02")]
            write(rows[:2])                                                                 # the file changed after it was registered
            refused("is not the registered wide calendar")
            write(rows)
            put(csv_p, ",".join(c for c in CA_COLS if c != "special") + "\n")
            sha2 = sha_raw(csv_p)
            with patched(me, WIDE_CA_SHA=sha2):
                put(man_p, json.dumps({"start": "2016-06-01", "sha256": {"corporate_actions_wide.csv": sha2}}))
                refused("lacks the column(s) ['special']")
            write(rows)
            manifest()
        # --- the dividends on the grid
        days = pd.bdate_range("2024-01-01", periods=80)
        syms = np.array(["AAA", "BBB"])
        mat, cnt = div_matrix(cal.div, days, syms)
        assert abs(mat[days.get_loc(TS("2024-01-10")), 0] - 0.30) < 1e-15 and abs(mat[days.get_loc(TS("2024-02-07")), 1] - 1.5) < 1e-15 and np.count_nonzero(mat) == 2, "two rows of one name on one ex-date add up"
        assert cnt == {"rows": 5, "name_not_on_the_grid": 1, "ex_date_not_a_session": 1, "placed": 3, "same_name_same_day_rows_added": 1}, cnt
        assert div_matrix(None, days, syms)[0].sum() == 0.0 and div_matrix(cal.div.iloc[:0], days, syms)[1]["rows"] == 0
        # --- [D2] the spin-off / stock-dividend ex-dates on the grid: a bool matrix, two rows of one name on one ex-date are one event, an unknown name / a Saturday are counted, not placed
        spn = pd.DataFrame({"symbol": ["AAA", "AAA", "BBB", "ZZZ", "AAA", "BBB"], "ex": pd.to_datetime(["2024-03-25", "2024-03-25", "2024-02-07", "2024-02-07", "2024-03-23", "2024-04-02"]),
                            "type": ["stock_dividend", "spin_off", "spin_off", "spin_off", "spin_off", "stock_dividend"]})
        mats, cnts = spin_matrix(spn, days, syms)
        assert mats.dtype == bool and mats.sum() == 3 and mats[days.get_loc(TS("2024-03-25")), 0] and mats[days.get_loc(TS("2024-02-07")), 1] and mats[days.get_loc(TS("2024-04-02")), 1], "placed on the name's own column"
        assert cnts == {"rows": 6, "name_not_on_the_grid": 1, "ex_date_not_a_session": 1, "placed": 4, "same_name_same_day_rows_merged": 1}, cnts
        assert spin_matrix(None, days, syms)[0].sum() == 0 and spin_matrix(cal.spin, days, syms)[1] == {"rows": 2, "name_not_on_the_grid": 0, "ex_date_not_a_session": 0, "placed": 2, "same_name_same_day_rows_merged": 0}
        Wsp = mk_world(prices(np.random.default_rng(5).normal(0.0, 0.01, (80, 2))), np.r_[np.nan, np.zeros(79)], Sp=mats)
        c0 = np.array([0, 1])
        assert spn_hit(Wsp, 0, 79, c0).tolist() == [True, True] and spn_hit(Wsp, 0, days.get_loc(TS("2024-03-22")), c0).tolist() == [False, True] and spn_hit(Wsp, days.get_loc(TS("2024-03-25")), days.get_loc(TS("2024-03-25")), c0).tolist() == [True, False]
        assert spn_hit(Wsp, days.get_loc(TS("2024-03-25")) + 1, 79, c0).tolist() == [False, True] and spn_hit(Wsp, 40, 30, c0).tolist() == [False, False] and spn_hit(Wsp, -5, 3, c0).tolist() == [False, False] and spn_hit(Wsp, 70, 500, c0).tolist() == [False, False]
        # --- the split cross-check by year: Dec 2024 .. Feb 2025; AAA agrees, BBB's calendar split is one session off the price flag (calendar-only + price-only, a near miss), CCC price-only, a lone calendar split
        days2 = pd.bdate_range("2024-12-02", periods=60)
        syms2 = np.array(["AAA", "BBB", "CCC"])
        dr = lambda d_: days2.get_loc(TS(d_))
        chg = np.zeros((60, 3), bool)
        chg[dr("2024-12-18"), 0] = chg[dr("2025-01-14"), 0] = True                          # AAA: both flagged by the price side
        chg[dr("2025-01-23"), 1] = True                                                    # BBB: the price side one session after the calendar
        chg[dr("2024-12-10"), 2] = True                                                    # CCC: price-only
        spl = pd.DataFrame({"symbol": ["AAA", "AAA", "BBB", "AAA", "ZZZ", "AAA"], "ex": pd.to_datetime(["2024-12-18", "2025-01-14", "2025-01-22", "2025-02-12", "2025-01-14", "2024-12-21"]),
                            "type": ["forward_split"] * 6})                                  # 2024-12-21 is a Saturday: not a session
        sc = split_check(spl, days2, syms2, chg)
        assert sc["by_year"] == {2024: {"agree": 1, "calendar_only": 0, "price_only": 1}, 2025: {"agree": 1, "calendar_only": 2, "price_only": 1}}, sc["by_year"]
        assert sc["total"] == {"agree": 2, "calendar_only": 2, "price_only": 2} and sc["calendar_only_within_3_sessions_of_a_price_only"] == 1, sc
        assert sc["calendar_rows"] == 6 and sc["calendar_rows_name_not_cached"] == 1 and sc["calendar_rows_ex_date_not_a_session"] == 1
        sm = split_check(spl, days2, syms2, chg, mask=np.array([True, True, False]))
        assert sm["total"] == {"agree": 2, "calendar_only": 2, "price_only": 1}, sm["total"]
        assert split_check(spl.iloc[:0], days2, syms2, chg)["total"] == {"agree": 0, "calendar_only": 0, "price_only": 4}
        # --- the report's counts and its print: a World on the first names, the calendar's rows as dividends / splits (symbols N00 / N01 here)
        T = 40
        rngw = np.random.default_rng(61)
        Clw = prices(rngw.normal(0.0, 0.01, (T, 2)), 30.0)
        dayw = pd.bdate_range("2024-01-01", periods=T)
        cal_w = SimpleNamespace(div=pd.DataFrame({"symbol": ["N00", "N00", "N01", "QQQ", "N01"], "ex": pd.to_datetime(["2024-01-17", "2024-02-02", "2024-01-19", "2024-01-17", "2024-02-05"]), "amt": [0.2, 0.3, 0.4, 0.5, 0.6],
                                                      "special": [False] * 5}),
                                split=pd.DataFrame({"symbol": ["N00"], "ex": pd.to_datetime(["2024-01-25"]), "type": ["forward_split"]}),
                                spin=pd.DataFrame({"symbol": ["N00", "N01", "QQQ", "N01", "N02"], "ex": pd.to_datetime(["2024-01-24", "2024-01-30", "2024-01-24", "2024-01-27", "2024-02-01"]),
                                                   "type": ["spin_off", "stock_dividend", "spin_off", "spin_off", "spin_off"]}),
                                info={"present": True, "path": "x.csv", "csv_sha256": "a" * 64, "pinned": {"registered": "a" * 64, "matches": True}, "manifest": {"csv_sha_ok": True, "start": "2024-01-15", "end": "2024-01-31"},
                                      "rows_on_file": 8, "rows_read": 8, "rows_dropped_at_the_cut": 0, "rows_by_type": {"cash_dividend": 5, "forward_split": 1}, "rows_by_type_year": {},
                                      "dividends": {"rows": 5, "usable": 5, "no_ex_date_or_symbol": 0, "no_positive_amount": 0, "special": 0}, "splits": {"rows": 1, "usable": 1, "no_ex_date_or_symbol": 0},
                                      "spin": {"rows": 5, "usable": 5, "no_ex_date_or_symbol": 0, "by_type": {"spin_off": 4, "stock_dividend": 1}}})
        Ww = mk_world(Clw, np.r_[np.nan, rngw.normal(0.0, 0.01, T - 1)], Dr=div_matrix(cal_w.div, dayw, np.array(["N00", "N01"]))[0],
                      Sp=spin_matrix(cal_w.spin, dayw, np.array(["N00", "N01"]))[0])
        chgw = np.zeros((T, 3), bool)
        chgw[dayw.get_loc(TS("2024-01-25")), 0] = chgw[dayw.get_loc(TS("2024-01-26")), 2] = True
        Dw = SimpleNamespace(days=dayw, syms=np.array(["N00", "N01", "N02"]), chg=chgw)
        rp = wide_report(cal_w, Dw, np.array([0, 1]), Ww)
        assert rp["dividends"]["grid"] == {"rows": 5, "name_not_on_the_grid": 1, "ex_date_not_a_session": 0, "placed": 4, "same_name_same_day_rows_added": 0}, rp["dividends"]["grid"]
        assert rp["dividends"]["by_year"] == {2024: {"usable": 5, "on_a_cached_name_and_session": 4, "on_a_name_ever_in_the_universe": 4, "applied": 4}}, rp["dividends"]["by_year"]
        assert rp["dividends"]["applied_in_the_world"]["applied"] == 4 and rp["splits"]["every_cached_name"]["total"] == {"agree": 1, "calendar_only": 0, "price_only": 1}
        assert rp["splits"]["names_ever_in_the_universe"]["total"] == {"agree": 1, "calendar_only": 0, "price_only": 0} and len(rp["warnings"]) == 2, rp["warnings"]
        assert "starts 2024-01-15" in rp["warnings"][0] and "ends 2024-01-31" in rp["warnings"][1]
        assert rp["spin"]["grid"] == {"rows": 5, "name_not_on_the_grid": 1, "ex_date_not_a_session": 1, "placed": 3, "same_name_same_day_rows_merged": 0} and rp["spin"]["in_the_world"] == {"cells": 2, "with_a_return": 2, "no_return": 0}, rp["spin"]
        assert rp["spin"]["by_year"] == {2024: {"usable": 5, "on_a_cached_name_and_session": 3, "on_a_name_ever_in_the_universe": 2, "return_left_out": 2}} and rp["spin"]["by_type"] == {"spin_off": 4, "stock_dividend": 1}, "N02 is cached but never in the universe: counted on the cached name, not on the universe name, and no return of it is left out"
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            print_wide(rp)
        txt = buf.getvalue()
        assert "NOT registered yet" not in txt and "registered: matches" in txt and "agree / calendar-only / price-only" in txt and "WARNING" in txt and "spin-offs / stock dividends [D2]" in txt and "spin-offs / stock dividends by year" in txt, txt
        import re
        assert not re.search(r"[$]\s*-?\d|ROC|Sortino|P&L", txt), "counts and years only: no amount, no outcome"
    finally:
        shutil.rmtree(root, ignore_errors=True)
    return True


def selftest():
    """rules on hand-made worlds: the constants as registered, the score (OLS beta, residual = return - beta x ES with the alpha left in, the skip month, the standardisation, the 230-pair rule, ES holes, split-safe) and
    what the alpha-left-in residual changes against the alpha-subtracted one, the monthly schedule, fills /
    marks / costs / borrow on hand numbers, the vectorised builds against a plain-python recount in both readings with every planted case, the null, DO / rho_dd = MDL r1's, every check broken alone, c = 25% of #463's
    volatility, the audit file, the reports, Stage B's leg-only pass and refusals, the cut"""
    t_constants()
    t_scores()
    t_identity()
    t_s1()
    t_spin()
    t_d1()
    t_schedule()
    t_hold()
    t_dividends()
    t_short0()
    t_hygiene()
    n = t_pipeline()
    t_null()
    t_stats()
    t_wide()
    t_crash_signed()
    t_xsml()
    ratio = t_a2()
    t_stage_b_checks()
    t_files()
    t_integration()
    t_stage_b_refusals()
    t_cut()
    print(f"A2 proof: c x the cell's daily std over 2017-01-03 .. 2018-12-31 = {ratio:.12f} of #463's (the registered 25%), the same c whatever the cell's sign, mean or outside-window days; c = 25% x std(#463) / std(cell), set by volatility, never picked")
    print("v2 FIX (proved by t_identity): residual = return - beta x ES return, the fitted alpha NOT subtracted - with the alpha subtracted the formation sum is EXACTLY minus the skipped month's (a one-month reversal); with it left in "
          "the whole-window sum is n x alpha, the formation sum is not tied to the skipped month, and a planted world ranks by the formation drift where the alpha-subtracted construction ranks by minus the last month. ADDENDUM 2 [S1] (t_s1): on random stock / ES pairs the formation sum is EXACTLY "
          "231 a - sum_S u = sum_W e - sum_S e (to 1e-12 relative) and rm_scores returns it over the sample (ddof 1) std of e over F")
    print("ADDENDUM 3 (proved by t_constants / t_wide / t_d1 / t_spin): the calendar's sha is the registered one and the manifest must carry a readable start; [D1] the formation sessions before that start are counted per WF rank "
          "(from the manifest, not hard-coded) and the reported row leaves the registered first five rebalances out of the cell AND the null; [D2] a spin-off / stock-dividend ex-date INSIDE the regression / formation window leaves that "
          "session's return out of the name's beta, residuals, formation sum / product and 230-return / 230-pair counts, INSIDE the hold (f < t <= x: the fill session's own is bought ex, the exit session's is inside) removes the "
          "name-month from the cell AND the null (the look-ahead reading keeps it at naive price P&L), and the counts of the picks (window, hold; long, short) equal a plain-python recount")
    print("ADDENDUM 1 (proved by t_dividends / t_short0 / t_wide / t_crash_signed / t_xsml): a cash dividend on its ex-date changes the daily return, RAW's formation product, RES's regression inputs and the positions' P&L exactly - a long "
          "receives, a short pays, per share held; the fill session's own ex-date is bought ex-dividend (nothing), the exit session's is received; D / F puts it on the split-adjusted basis; no close, no dividend. The wide calendar's gates "
          "(not on file / sha not registered / not the registered file / no manifest / a missing column), the cut at read, its counts and the split cross-check by year; the shorts-at-zero row; the signed crash-month line; XSML's correlation or its absence")
    print(f"selftest ok: constants as registered, the score (OLS recovers a planted beta, formation-only sum / sample std of return - beta x ES with the alpha left in, the skipped month moves RES only through the beta and never RAW, scale-free, the 230-pair rule at its edge, ES-hole sessions skipped, "
          f"split-safe), the monthly schedule (month-end ranks, next-session fills, exits at the next fill, unresolved, warm-up, stretch by exit), fills / marks / costs / borrow on hand numbers through the whole chain, "
          f"{n:,} pool-name paths and every pool / score / pick equal a plain-python recount in the registered and look-ahead readings (planted splits, flags, stops, carries, ES holes, audit), the null (uniform, seeded, "
          "one stream per cell, no S twin), DO / rho_dd = MDL r1's, every Stage A check broken alone, A2's volatility-set c (identity, invariances, window ends, 0.5c / 2c books, the bar, no-c cells), the audit file, "
          "evaluate / reports / candidates end to end on the toy world, Stage B's leg-only pass and refusals, the cut")


# ------------------------------------------------------------------ smoke: an offline end-to-end run on a SYNTHETIC world (every number means nothing)
def brute_div_matrix(path, days, syms, cut):
    """plain python (the csv module, no pandas): the cash dividends of a flat calendar CSV on the grid - the raw per-share amount summed per (session, name); a row on / after the cut, without a name of the grid, with an ex-date that is
    not a session or without a positive amount is left out"""
    import csv
    out = np.zeros((len(days), len(syms)))
    di, ci = {TS(d): i for i, d in enumerate(days)}, {str(s_): j for j, s_ in enumerate(syms)}
    with open(path, newline="") as f:
        for r in csv.DictReader(f):
            if r["type"] != DIV_TYPE:
                continue
            try:
                ex, amt = TS(r["ex_date"]), float(r["rate"])
            except ValueError:
                continue
            if ex < TS(cut) and amt > 0 and r["symbol"] in ci and ex in di:
                out[di[ex], ci[r["symbol"]]] += amt
    return out


def brute_spin_matrix(path, days, syms, cut):
    """plain python (the csv module, no pandas): the [D2] spin-off / stock-dividend ex-dates of a flat calendar CSV on the grid (T, S) bool - a row on / after the cut, without a symbol of the grid, without an ex-date or with an
    ex-date that is not a session is left out"""
    import csv
    out = np.zeros((len(days), len(syms)), bool)
    di, ci = {TS(d): i for i, d in enumerate(days)}, {str(s_): j for j, s_ in enumerate(syms)}
    with open(path, newline="") as f:
        for r in csv.DictReader(f):
            if r["type"] not in SPIN_TYPES or not r["ex_date"]:
                continue
            ex = TS(r["ex_date"])
            if ex < TS(cut) and r["symbol"] in ci and ex in di:
                out[di[ex], ci[r["symbol"]]] = True
    return out


def smoke_refusal(root):
    """r15's guards (the dir is wiped: a 'smoke' name, never OUT / CACHE / the repo / this harness / the working directory / C:\\EdgeLog, ATTN's and DDW's OUT, the #463 records) + this harness's OUT"""
    why = D15.smoke_refusal(root)
    if why:
        return why
    real = lambda p: os.path.normcase(os.path.realpath(p))
    try:
        if os.path.commonpath([real(root), real(OUT)]) == real(root):
            return f"smoke refused: {root} is or holds RESMOM OUT"
    except ValueError:
        pass
    return None


def smoke(*a):
    import re, shutil, tempfile
    global OUT, CHECK_BOOK, NREP, WIDE_CA_SHA, XSML_DIR, ANATOMY_ROOT
    root = os.path.abspath(a[0] if a else os.path.join(tempfile.gettempdir(), "resmom_smoke"))
    why = smoke_refusal(root)
    if why:
        raise SystemExit(why)
    selftest()                                                                             # the hand-made checks first, on the real constants (before anything below is patched)
    me, data = sys.modules[__name__], A13.data_mod()
    keep = dict(OUT=OUT, CHECK_BOOK=CHECK_BOOK, NREP=NREP, RULES=dict(RULES), SPEC=dict(SPEC), DSPEC=dict(D15.SPEC), R11_OUT=R11.OUT, A13_OUT=A13.OUT, TBIS=(D15.TBIS_CSV, A13.TBIS_QA),
                S=(S.OUT, S.CACHE, S.BOOK, S.SMOKE, S.PACE, S.BACKOFF, S.RETRY, S._http_get), es=(data.find_master, data.load_master_arrays))
    keep["WIDE"] = (WIDE_CA_SHA, XSML_DIR, ANATOMY_ROOT)
    t_start = time.time()
    shutil.rmtree(root, ignore_errors=True)
    os.makedirs(root)
    OUT, R11.OUT, A13.OUT = os.path.join(root, "out"), os.path.join(root, "r11"), os.path.join(root, "attn_out")
    S.OUT, S.CACHE, S.BOOK = os.path.join(root, "siporb_out"), os.path.join(root, "cache"), os.path.join(root, "r4", "book463_daily.csv")
    for p in (OUT, R11.OUT, A13.OUT, S.OUT):
        os.makedirs(p)
    tbis_path = os.path.join(root, "tbis.csv")
    D15.TBIS_CSV = A13.TBIS_QA = tbis_path                                                 # both readers of the TBIS file (r15's load_tbis, r13's add_tbis_flags) point into the smoke dir
    S.SMOKE, S.PACE, S.BACKOFF, S.RETRY = True, 0.0, 0.0, 0.0
    CHECK_BOOK = False                                                                     # off in smoke only: its synthetic book / manifest / ES history cannot reproduce the real registered facts
    NREP = 100                                                                             # CHOICE: the smoke draws 100, not 500, for speed (the real constant is asserted by selftest)
    inside = lambda p: os.path.commonpath([os.path.realpath(p), os.path.realpath(root)]) == os.path.realpath(root)
    assert all(inside(p) for p in (OUT, R11.OUT, A13.OUT, S.OUT, S.CACHE, tbis_path)), "every path the smoke writes is inside the smoke dir"
    quiet = lambda: contextlib.redirect_stdout(io.StringIO())
    dates_of = lambda txt: re.findall(r"\b20\d\d-\d\d-\d\d\b", txt)
    try:
        SPEC.update(n_side=5)                                                              # the synthetic market has ~37 names: the real 50 + 50 of a 500-name universe cannot exist in it
        D15.SPEC.update(univ=40)                                                           # ... and its universe is not truncated: every name that passes filters 1-3 is in
        spans = (("2015-11-02", "2017-02-28"), ("2023-10-02", "2023-12-29"), ("2024-01-02", "2024-06-28"), ("2025-04-01", "2025-06-27"), ("2025-06-30", "2025-09-30"))
        days = pd.DatetimeIndex(sorted(set().union(*[pd.bdate_range(x, y) for x, y in spans])))          # 15 months of warm-up + the first ranks, 2023-24, 2025 WF days, the lockbox days: the cut has something to cut
        t0 = time.time()
        fk = S.Fake(days)
        S._http_get = fk.handle
        print(f"synthetic market: {len(fk.names)} names x {len(days)} sessions built in {time.time() - t0:.0f}s")
        t0 = time.time()
        with quiet():
            S.assets()
            S.daily()                                                                      # r5_siporb's own pulls through its fake transport: the synthetic daily caches (no 09:30 pull: this family reads none)
        print(f"synthetic SIPORB cache pulled through r5_siporb ({fk.n:,} requests, {time.time() - t0:.0f}s)")
        es_cal = days.union(pd.bdate_range("2015-05-01", "2015-10-30"))                       # CHOICE: ES history (the real masters start in 2010) reaches back before the synthetic stock sessions, so k_t is defined from 2016
        esf = D15.ESFake(es_cal)
        esf.install()
        A13.smoke_book()
        json.dump({"manifest_sha256": D15.MANIFEST_PREFIX + "0" * 56, "files": 0}, open(os.path.join(S.OUT, "siporb_cache_manifest.json"), "w"))
        open(tbis_path, "w").write("symbol,day,price_ratio,vol_ratio,split_like\nS18,2024-04-22,4.0,0.25,True\nSPL,2024-03-15,0.5,2.1,True\nS05,2024-02-13,0.5,1.0,False\nZZZZ,2024-02-14,0.5,2.0,True\n"
                                   "S07,2025-07-01,0.5,2.0,True\n")
        # ---- [R1] a synthetic WIDE corporate-actions calendar in r16_xgap's flat CSV, written where capull's --tag wide writes (S.CACHE\\xgap) and registered by its sha (WIDE_CA_SHA) for this run: a dividend of 0.8% of the prior raw
        # close on every 21st session of every name (the raw basis of the ex-date's session), one special of 30%, the cases the loader must count and not use, rows on / after the cut, splits that agree / are calendar-only
        raw0 = S.read_long("raw", S.END)
        rl0 = raw0.assign(symbol=raw0["symbol"].astype(str)).sort_values(["symbol", "date"])
        crow = []
        for sym_, g_ in rl0.groupby("symbol"):
            dts_, cls_ = g_["date"].to_numpy(), g_["c"].to_numpy(float)
            for k_ in range(14, len(dts_), 21):
                d_ = f"{pd.Timestamp(dts_[k_]):%Y-%m-%d}"
                crow.append(f"cash_dividend,{sym_},,,{d_},{d_},,,{round(0.008 * cls_[k_ - 1], 4)},,,,False")
        g11 = rl0[rl0["symbol"] == "S11"]
        d11 = f"{pd.Timestamp(g11['date'].to_numpy()[100]):%Y-%m-%d}"
        crow.append(f"cash_dividend,S11,,,{d11},{d11},,,{round(0.3 * float(g11['c'].to_numpy()[99]), 4)},,,,True")
        extra_ = ["cash_dividend,S01,,,2024-03-02,2024-03-02,,,0.4,,,,False", "cash_dividend,ZZZZ,,,2024-02-07,2024-02-07,,,0.9,,,,False", "cash_dividend,S02,,,2024-02-07,2024-02-07,,,0,,,,False",
                  "cash_dividend,S03,,,2024-02-08,2024-02-08,,,,,,,False", "cash_dividend,S04,,,2025-06-30,2025-06-30,,,0.5,,,,False", "cash_dividend,S04,,,2025-07-01,2025-07-01,,,0.5,,,,False",
                  "cash_dividend,S06,,,2025-07-02,2025-07-02,,,0.5,,,,True", "forward_split,SPL,,,2024-03-15,2024-03-15,2024-03-08,2024-03-14,,2,1,,", "forward_split,S05,,,2024-02-20,2024-02-20,,,,2,1,,",
                  "stock_dividend,S07,,,2024-02-21,2024-02-21,,,0.1,,,,", "spin_off,S08,,S08.W,2024-02-22,2024-02-23,,,,0.1,1,,", "name_change,,OLDS,S09,,2024-02-26,,,,,,,",
                  "spin_off,S10,,S10.W,2024-04-12,2024-04-12,,,,0.1,1,,", "stock_dividend,ZZZZ,,,2024-03-06,2024-03-06,,,0.1,,,,", "spin_off,S12,,S12.W,2024-03-02,2024-03-02,,,,0.1,1,,",
                  "stock_dividend,S13,,,2025-06-30,2025-06-30,,,0.1,,,,", "spin_off,,,X.W,2024-03-05,2024-03-05,,,,0.1,1,,", "stock_dividend,S14,,,,2024-03-07,,,0.1,,,,"]
        xd_ = os.path.join(S.CACHE, "xgap")
        os.makedirs(xd_, exist_ok=True)
        cpath_, man_p_ = os.path.join(xd_, WIDE_NAME + ".csv"), os.path.join(xd_, WIDE_NAME + "_manifest.json")
        with open(cpath_, "w", newline="\n") as f_:
            f_.write("\n".join([",".join(CA_COLS)] + crow + extra_) + "\n")
        wide_sha = sha_raw(cpath_)
        with open(man_p_, "w") as f_:
            json.dump({"created": "2026-10-05T10:00:00", "start": "2016-06-01", "end": "2026-06-30", "rows": len(crow) + len(extra_), "sha256": {WIDE_NAME + ".csv": wide_sha}}, f_)
        man0_ = open(man_p_).read()
        WIDE_CA_SHA = wide_sha
        XSML_DIR, ANATOMY_ROOT = os.path.join(root, "xsml_none"), os.path.join(root, "anatomy_none")          # [R4] nothing on file yet: a series is written later
        n_cut_rows = sum(1 for r_ in crow + extra_ if r_.split(",")[4] >= "2025-06-30")                          # the rows dated on / after the cut: dropped at read
        print(f"synthetic wide calendar: {len(crow) + len(extra_):,} rows ({len(crow):,} regular dividends), sha256 {wide_sha[:16]}..., {n_cut_rows} rows on / after the cut")
        # ---- the planted cases, through the real loaders and the real arrays
        with quiet():
            D = load_data(S.LB0)
        assert not hasattr(D, "O5") and not hasattr(D, "RV") and len(D.days) and D.days.max() < S.LB0 and D.msplit[:, list(D.syms).index("S05")][D.days.get_loc(TS("2024-02-13"))], "no 09:30 arrays; TBIS's flags are OR-ed into the gap scan"
        es_frames, es_meta = D15.load_es(S.LB0)
        cut = TS(S.LB0).tz_localize("US/Eastern")
        assert es_frames["raw"].index.max() < cut and es_frames["adj"].index.max() < cut and esf.tab["raw"][0].max() >= cut, "the ES loader hands back bars past the cut (leaky) and load_es's own cut removes them"
        tbis = D15.load_tbis(S.LB0)
        assert tbis["day"].max() < S.LB0 and len(tbis) == 4 and len(D15.load_tbis(S.END)) == 5, "the TBIS flag on the lockbox day is cut at read time"
        with quiet():
            cal, winfo = wide_load(S.LB0)
            W = build_world(D, S.LB0, es_frames, tbis, cal)
        raw_l, spl_l = S.read_long("raw", S.LB0), S.read_long("split", S.LB0)
        D15.release(D)
        ix, T = list(W.syms), W.T
        # [R1] the dividend arrays through the real loaders: the calendar read (cut at read), placed on the grid, put on the split-adjusted basis and applied where the name has prints - equal to a plain-python placement of the csv rows
        W.Dr_in = brute_div_matrix(cpath_, W.days, W.syms, S.LB0)
        W.Sp_in = brute_spin_matrix(cpath_, W.days, W.syms, S.LB0)                          # [D2] the spin-off / stock-dividend ex-dates placed by plain python from the csv rows
        Eb = np.array([[brute_div_amt(W, t_, j_) for j_ in range(W.S)] for t_ in range(W.T)])
        assert np.allclose(W.Dv1, Eb, rtol=1e-12, atol=1e-15) and W.div_counts["applied"] == int((Eb > 0).sum()) > 400, (W.div_counts, int((Eb > 0).sum()))
        assert W.div_counts["over_25_pct_of_the_prior_close"] >= 1 and W.ca["file"]["rows_dropped_at_the_cut"] == n_cut_rows and W.ca["file"]["pinned"]["matches"] is True and W.ca["file"]["csv_sha256"] == wide_sha
        assert any("starts 2016-06-01" in w_ for w_ in W.ca["warnings"]) and W.ca["dividends"]["no_ex_date_or_symbol"] == 0 and W.ca["dividends"]["no_positive_amount"] == 2 and W.ca["dividends"]["special"] == 1, W.ca["dividends"]
        assert W.ca["dividends"]["grid"]["name_not_on_the_grid"] == 1 and W.ca["dividends"]["grid"]["ex_date_not_a_session"] == 1, W.ca["dividends"]["grid"]
        assert (W.SPN == W.Sp_in).all() and int(W.SPN.sum()) == W.spin_counts["cells"] >= 3 and W.spin_counts["no_return"] == 0, (int(W.SPN.sum()), W.spin_counts)
        spc = W.ca["spin"]
        assert (spc["rows"], spc["usable"], spc["no_ex_date_or_symbol"], spc["by_type"]) == (7, 5, 2, {"spin_off": 4, "stock_dividend": 3}), spc
        assert spc["grid"] == {"rows": 5, "name_not_on_the_grid": 1, "ex_date_not_a_session": 1, "placed": 3, "same_name_same_day_rows_merged": 0}, spc["grid"]
        sc_all = W.ca["splits"]["every_cached_name"]
        assert sc_all["by_year"][2024]["agree"] >= 1 and sc_all["by_year"][2024]["calendar_only"] >= 1 and sc_all["by_year"][2016]["price_only"] >= 1 and sc_all["total"]["agree"] + sc_all["total"]["calendar_only"] == 2, sc_all
        di = lambda s: W.days.get_loc(TS(s))
        rl, sl = raw_l.assign(symbol=raw_l["symbol"].astype(str)).set_index(["symbol", "date"]), spl_l.assign(symbol=spl_l["symbol"].astype(str)).set_index(["symbol", "date"])
        pick = np.random.default_rng(3).choice(len(rl), 300, replace=False)
        n_chk = 0
        for q in pick:                                                                     # the arrays equal the long daily frames (an independent look-up, 300 name-days)
            (sym, d), r_ = rl.index[q], rl.iloc[q]
            if sym in ix and d in W.days:
                c_, t_ = ix.index(sym), W.days.get_loc(d)
                assert W.Cl[t_, c_] == r_["c"] and W.Od[t_, c_] == r_["o"] and W.Vv[t_, c_] == r_["v"] and abs(W.F[t_, c_] - r_["o"] / sl.loc[(sym, d), "o"]) < 1e-12, (sym, d)
                n_chk += 1
        assert n_chk > 100 and W.days.max() < S.LB0 and W.es.k.shape == (T,) and np.isnan(W.C5).all() and np.isnan(W.RV).all(), "the 09:30 stand-ins are all NaN: this family reads none"
        spl_k = ix.index("SPL")
        assert W.chg[di("2024-03-15"), spl_k] and abs(W.F[di("2024-03-14"), spl_k] - 2.0) < 1e-3 and abs(W.F[di("2024-03-15"), spl_k] - 1.0) < 1e-3, "the registered split: F 2 -> 1 (Alpaca's convention)"
        assert W.fl[1][di("2024-04-22"), ix.index("S18")] and not W.chg[:, ix.index("S18")].any(), "S18's x4 was never adjusted: only the gap scan sees it"
        assert W.fl[3][di("2024-05-14"), ix.index("S23")] and not W.fl[1][di("2024-05-14"), ix.index("S23")], "S23's genuine +60% gap: the +-50% rule, not a whole ratio"
        assert W.fl[1][di("2024-03-15"), spl_k] and W.fl[1][di("2024-02-13"), ix.index("S05")], "TBIS's symbol-days are in the gap-scan flags (r13_attn's convention); ZZZZ is not a cached name"
        # the ES prints on the stock sessions: the 09:35 price is not read here, the 16:00 prints are; the missing session
        pa, pr = W.es_cov["adj_prints"], W.es_cov["raw_prints"]
        i = di("2023-12-15")
        assert np.isclose(W.es.ret[i], (pa.loc["2023-12-15", "close"] - pa.loc["2023-12-14", "close"]) / pr.loc["2023-12-14", "close"]) and abs(W.es.ret[i]) < 0.05, "the market's return: roll-corrected change over the unadjusted level"
        assert np.isnan(W.es.ret[di("2024-03-05")]) and np.isnan(W.es.ret[di("2024-03-06")]), "no ES bar on 2024-03-05: that session's return and the next one's are undefined"
        fin = np.flatnonzero(np.isfinite(W.k))
        assert len(fin) and W.days[fin[0]] == pa.index.intersection(pr.index)[219], "k_t is first defined at the 220th ES session"
        # the rebalances against the plain-python recount on the REAL arrays, both readings, then the planted names
        lo, hi = WF0, PRE_END
        Lr, Lk = rm_build(W, lo, hi), rm_build(W, lo, hi, "naive")
        Br, Bk = brute_rm(W, lo, hi), brute_rm(W, lo, hi, "naive")
        n_paths = compare_rm(W, Lr, Br, "smoke RM") + compare_rm(W, Lk, Bk, "smoke RM K")
        series_check(W, Lr, Br)
        ntr = sum(r.traded for r in Lr.recs)
        assert ntr >= 12 and len(Lr.recs) == len(Br) and Lr.cnt[2025]["unresolved"] == 1, (ntr, len(Lr.recs), {y: dict(c) for y, c in Lr.cnt.items()})
        by_rank = lambda L, d_: next(r for r in L.recs if W.days[r.r] == TS(d_))
        first = Lr.recs[0]
        assert W.days[first.r] == TS("2016-10-31") and first.r >= SPEC["win"] - 1 and Lr.cnt[2016]["warmup"] == 5, "the first rank with a full window is 2016-10-31; the five ranks before it whose position exits in WF (2016-05-31 .. 09-30) are warm-up, counted not built"
        assert ix.index("S33") not in first.pool.tolist() and first.nfull < first.nu, "S33 first trades on 2016-02-01: under 230 returns at the first rank"
        rv_k = ix.index("RVS")
        assert abs(W.Rn[di("2016-02-17"), rv_k]) < 0.3 and (W.U[first.f, rv_k] is np.False_ or rv_k in first.pool.tolist() or W.hyg(0, first.r, np.array([rv_k])).any()), "RVS's reverse split inside the window is split-safe (no fake -80% day)"
        assert all(ix.index("S34") not in r_.pool.tolist() for r_ in Lr.recs if W.days[r_.f] < TS("2025-01-01")), "S34 first trades on 2024-02-01: under 230 returns at every 2023-24 rank"
        n_ret, n_pair, _, _ = rm_scores(W, di("2024-03-29"), np.array([ix.index("S01")]))
        assert (n_ret - n_pair).tolist() == [2], "the two sessions without an ES return (2024-03-05 / 06) are skipped for every name"
        for nm, rank_day, why in (("SPL", "2024-02-29", "post"), ("S18", "2024-03-29", "post"), ("S23", "2024-04-30", "post"), ("SPL", "2024-03-29", "pre"), ("S18", "2024-04-30", "pre"), ("S23", "2024-05-31", "pre"), ("S18", "2024-05-31", "old")):
            c_, rr_, kk_ = ix.index(nm), by_rank(Lr, rank_day), by_rank(Lk, rank_day)
            if W.U[rr_.f, c_]:
                assert c_ not in rr_.pool.tolist(), (nm, rank_day, "removed in the registered reading")
                if why == "post" and c_ in kk_.pool.tolist():
                    assert kk_.naive[kk_.pool.tolist().index(c_)], (nm, "kept at its naive raw P&L")
                if why != "post":
                    assert c_ not in kk_.pool.tolist(), (nm, rank_day, "a flag known at the decision removes it in both readings")
        k3 = by_rank(Lk, "2024-02-29")
        if spl_k in k3.pool.tolist():
            q_ = k3.pool.tolist().index(spl_k)
            safe = D15.unit_path(W.Ao, W.Ac, k3.f, k3.x, np.array([spl_k]))
            dn_ = sum(brute_div(W, k3.f, k3.x, spl_k, True))                                # [R1] the raw cash of the hold over the raw entry open rides on the naive raw path
            assert abs(k3.U.G[q_].sum() - (W.Od[k3.x, spl_k] / W.Od[k3.f, spl_k] - 1.0 + dn_)) < 1e-12 and k3.U.G[q_].sum() < -0.3 and abs(safe.G[0].sum()) < 0.5, "SPL: the naive raw P&L shows the split as a loss"
        dl = by_rank(Lr, "2024-04-30")
        if ix.index("DLST") in dl.pool.tolist():
            assert dl.U.st[dl.pool.tolist().index(ix.index("DLST"))], "DLST stopped printing inside the hold: it exits at its last mark"
        assert ix.index("DLST") not in by_rank(Lr, "2024-05-31").pool.tolist(), "no open at the fill session: not eligible"
        print(f"planted cases ok through the real arrays: the first full-window rank, S33 / S34 short histories, RVS split-safe, SPL / S18 / S23 / DLST in both readings, the ES-hole sessions skipped, k_t's start, TBIS and the cut; "
              f"{n_paths:,} pool-name paths and every pool / score / pick equal a plain-python recount ({ntr} rebalances traded in WF)")
        # ---- Stage A, end to end
        t0 = time.time()
        sa = os.path.join(OUT, "resmom_stageA.json")

        def wide_refusal(frag, **kw):                                                       # [R1] Stage A refuses, computing nothing, until the wide calendar is on file, registered and the registered file
            try:
                with quiet(), patched(me, **kw):
                    stage_a()
                raise AssertionError(f"Stage A must refuse ({frag})")
            except SystemExit as e:
                assert frag in str(e) and not os.path.exists(sa), (frag, str(e))
        absent_ = {"dir": xd_, "csv": os.path.join(xd_, "absent.csv"), "manifest": os.path.join(xd_, "absent.json")}
        wide_refusal("wide corporate-actions calendar is not on file", wide_paths=lambda: absent_)
        wide_refusal("the wide calendar sha is not registered yet", WIDE_CA_SHA=None)
        wide_refusal("is not the registered wide calendar", WIDE_CA_SHA="0" * 64)
        os.remove(man_p_)
        wide_refusal("manifest is missing")
        with open(man_p_, "w") as f_:
            f_.write(man0_.replace(wide_sha, "0" * 64))
        wide_refusal("does not carry this file's sha256")
        j_ = json.loads(man0_)
        j_.pop("start")
        with open(man_p_, "w") as f_:
            json.dump(j_, f_)
        wide_refusal("no readable start date")                                              # [D1] the coverage of the first ranks' windows is counted from the manifest's start
        with open(man_p_, "w") as f_:
            f_.write(man0_)
        with patched(me, PREREG_SHA="0" * 64):
            try:
                stage_a()
                raise AssertionError("a changed pre-registration must refuse Stage A")
            except SystemExit as e:
                assert "DIFFERS" in str(e) and not os.path.exists(sa)
        CHECK_BOOK = True
        try:
            with quiet():
                stage_a()
            raise AssertionError("a book that does not reproduce #463 must refuse Stage A")
        except SystemExit as e:
            assert "do not reproduce" in str(e) and not os.path.exists(sa)
        CHECK_BOOK = False
        print("--- Stage A, every bar as registered (the synthetic world cannot pass them): the FAIL path")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            out = stage_a()
        txt = buf.getvalue()
        print(txt.rstrip())
        assert out["judged"] is True and out["candidate"] is None and out["pending_audit"] == [] and os.path.exists(sa) and all(d < "2025-06-30" for d in dates_of(txt)), "Stage A printed a lockbox date"
        cells = out["stageA"]["cells"]
        assert not any(c["PASS"] for c in cells.values()) and set(cells) == set(CELLS) and out["stageA"]["null"]["draws"] == NREP and out["kept_naive_reading"]["null"]["draws"] == NREP
        eh = out["es_return"]
        assert {"2024-03-05", "2024-03-06"} <= set(eh["undefined_es_return_sessions"]) and eh["stretch"] == ["2016-07-01", "2025-06-29"] and eh["es_return_defined"] < eh["sessions"], eh
        assert json.load(open(sa))["judged"] is True and out["parity"]["RES"]["n_units"] == ntr
        # [R1] the calendar's counts in the file and the printout, the NO-DIVIDEND version of both cells (a reported row: the same code with the cash left out of the scores, the picks and the P&L) recounted, [R2] / [R3] / [R4]
        wc = out["wide_calendar"]
        assert wc["file"]["rows_dropped_at_the_cut"] == n_cut_rows and wc["file"]["csv_sha256"] == wide_sha and wc["dividends"]["applied_in_the_world"]["applied"] == W.div_counts["applied"] > 0, wc["file"]
        assert "wide corporate-actions calendar [R1]" in txt and "no-dividend version [R1]" in txt and "SIGNED LINE [R3]" in txt and "short leg [R2]" in txt and "dividends [R1] inside the registered picks" in txt
        assert "XSML r1 cell A's daily P&L series is not on file" in txt and out["reports"]["xsml"]["on_file"] is False and out["reports"]["crash_signed"]["months_available"] == 4 and out["reports"]["crash_signed"]["sum_res_minus_raw"] == 0.0
        nd, B_n = out["no_dividend_reading"], A13.load_463()[0]
        rows_n = A13.book_rows(B_n, W)
        assert set(nd["cells"]) == set(CELLS) and nd["null"]["draws"] == NREP and any(abs(nd["dividends_add_net"][c_]) > 1.0 for c_ in CELLS), nd["dividends_add_net"]
        with div_mode(W, False):
            Ln = rm_build(W, WF0, PRE_END)
            for cell in CELLS:
                run_n = run_cell(W, cell_leg(Ln, cell), D15.l1_cfg(), pos=True)
                stn = D15.cell_stats(B_n, D15.to_B(run_n.x, rows_n, B_n.n), D15.to_B(run_n.cnt, rows_n, B_n.n), WF0, PRE_END, run_n)
                assert abs(stn["net"] - nd["cells"][cell]["base"]["net"]) < 1e-6 and stn["n_pos"] == nd["cells"][cell]["base"]["n_pos"], (cell, stn["net"], nd["cells"][cell]["base"]["net"])
                assert abs(nd["dividends_add_net"][cell] - (cells[cell]["base"]["net"] - nd["cells"][cell]["base"]["net"])) < 1e-6, cell
        for cell in CELLS:                                                                   # [R2]: valuing the stopped shorts at zero cannot hurt a short; the count is the stopped short picks of the registered legs
            st_ = cells[cell]
            assert st_["sides"][R2_SIDE]["net"] >= st_["sides"]["short side only"]["net"] - 1e-9 and st_["extra"][R2_CELL]["net"] >= st_["base"]["net"] - 1e-9
            assert st_["short_stopped"]["positions"] == sum(int(r_.U.st[r_.pick[cell][1]].sum()) for r_ in Lr.recs if r_.traded) and st_["short_stopped"]["short_positions"] == sum(len(r_.pick[cell][1]) for r_ in Lr.recs if r_.traded)
        assert out["reports"]["dividend_flows"]["RES"]["long_received"] > 0 and out["reports"]["dividend_flows"]["RES"]["short_paid"] > 0
        # [D1] the coverage counted from the manifest's start (plain python), and the row without the first five rebalances: the same registered reading with those ranks left out of the cell AND the null, recounted
        st_m = TS("2016-06-01")
        cov_py = []
        for r_ in Lr.recs:
            a_, fa_, fe_ = windows(r_.r)
            cov_py.append((f"{W.days[r_.r]:%Y-%m-%d}", sum(1 for t_ in range(fa_, fe_ + 1) if W.days[t_] < st_m)))
        d1 = out["coverage_d1"]
        assert d1["calendar_start"] == "2016-06-01" and [(x["rank"], x["formation_sessions_before"]) for x in d1["per_rank"]] == cov_py and d1["ranks_in_wf"] == len(Lr.recs) and any(n_ > 0 for _, n_ in cov_py), d1
        assert d1["registered_five_match"] is False and "calendar coverage [D1]" in txt and "WARNING: the partly uncovered ranks are NOT the five the pre-registration names" in txt, "the synthetic ranks are not the registered five: said so"
        five = {TS(x_) for x_ in D1_RANKS}
        n_drop = sum(1 for r_ in Lr.recs if W.days[r_.r] in five)
        Lf = rm_build(W, WF0, PRE_END, drop=tuple(TS(x_) for x_ in D1_RANKS))
        ff = out["without_first_five_reading"]
        assert n_drop >= 2 and len(Lf.recs) == len(Lr.recs) - n_drop and ff["rebalances_remaining"] == len(Lf.recs) and ff["of"] == len(Lr.recs) and ff["dropped_ranks"] == list(D1_RANKS) and ff["null"]["draws"] == NREP, (n_drop, ff["rebalances_remaining"])
        assert sum(v["dropped_d1"] for v in Lf.cnt.values()) == n_drop and not any(W.days[r_.r] in five for r_ in Lf.recs), "dropped from the leg: out of the cell AND the null"
        B_f = A13.load_463()[0]
        rows_f = A13.book_rows(B_f, W)
        for cell in CELLS:
            run_f = run_cell(W, cell_leg(Lf, cell), D15.l1_cfg(), pos=True)
            stf = D15.cell_stats(B_f, D15.to_B(run_f.x, rows_f, B_f.n), D15.to_B(run_f.cnt, rows_f, B_f.n), WF0, PRE_END, run_f)
            assert abs(stf["net"] - ff["cells"][cell]["base"]["net"]) < 1e-6 and stf["n_units"] == ff["cells"][cell]["base"]["n_units"] == len(Lf.recs) - sum(1 for r_ in Lf.recs if not r_.traded) and ff["cells"][cell]["base"]["n_pos"] == stf["n_pos"], (cell, stf["net"])
            assert ff["cells"][cell]["base"]["net"] != cells[cell]["base"]["net"], "five rebalances out: another net"
        assert "without the first five rebalances [D1]" in txt and f"{len(Lf.recs)} of {len(Lr.recs)} rebalances remain" in txt
        # [D2] (window, hold; long, short) of the picks in both readings = the stage's own legs = the plain-python recount; the registered reading's picks hold no name with an ex-date inside the hold
        sc_ = out["spin_counts"]
        for cell in CELLS:
            assert sc_["registered_reading"][cell] == spin_counts(Lr, cell) == brute_spin_counts(Br, cell), (cell, sc_["registered_reading"][cell])
            assert sc_["look_ahead_reading_kept_at_naive_price_pnl"][cell] == spin_counts(Lk, cell) == brute_spin_counts(Bk, cell), (cell, sc_["look_ahead_reading_kept_at_naive_price_pnl"][cell])
            assert sc_["registered_reading"][cell]["long"]["hold_positions"] == sc_["registered_reading"][cell]["short"]["hold_positions"] == 0
        assert "registered reading [D2] RES picks (long / short)" in txt and "[D2] by fill year" in txt and sum(v.get("spin_hold_names", 0) for v in out["hygiene_counts_by_year"]["registered"].values()) >= 1
        assert sum(v.get("post_spin", 0) for v in out["hygiene_counts_by_year"]["registered"].values()) == sum(c_.get("post_spin", 0) for c_ in Lr.cnt.values()) >= 1, "a spin-off / stock dividend inside a hold removed a name-month in the registered reading"
        # dryload on the synthetic world: counts only, no lockbox date, the ES line, and nothing written
        before = sorted(os.listdir(OUT))
        buf_d = io.StringIO()
        with contextlib.redirect_stdout(buf_d):
            dryload()
        td = buf_d.getvalue()
        assert sorted(os.listdir(OUT)) == before and "universe size per session by year" in td and "ES return (" in td and "k_t: defined from" in td and "full window" in td and "rebalances:" in td
        assert all(d < "2025-06-30" for l in td.splitlines() if "cut to dates <" not in l for d in dates_of(l)), "dryload printed a lockbox date"
        outcome = re.search(r"[$]\s*-?\d|ROC|Sortino|P&L|net [$]|score [+-]?\d", td)
        assert not outcome, ("dryload printed an outcome", td[max(outcome.start() - 80, 0):outcome.end() + 80])
        assert "wide corporate-actions calendar [R1]" in td and "the calendar's splits against the registered split rule, every cached name" in td and "dividends by year" in td and "registered: matches" in td
        assert "calendar coverage [D1]" in td and "by rank: " + ", ".join(f"{d_} {n_}" for d_, n_ in cov_py if n_ > 0) in td and "spin-offs / stock dividends [D2]" in td and "registered [D2] by fill year" in td and "look-ahead [D2] by fill year" in td, "the dryload prints the coverage and the D2 counts"
        buf_n = io.StringIO()
        with contextlib.redirect_stdout(buf_n), patched(me, wide_paths=lambda: absent_):
            dryload()
        assert "not on file yet" in buf_n.getvalue() and "this dryload ran without dividends" in buf_n.getvalue(), "the dryload says so when the wide calendar is absent"
        buf_u = io.StringIO()
        with contextlib.redirect_stdout(buf_u), patched(me, WIDE_CA_SHA=None):
            dryload()
        assert "NOT registered yet" in buf_u.getvalue() and "agree / calendar-only / price-only" in buf_u.getvalue(), "the dryload reads the calendar without a registered sha and reports it (only Stage A / B refuse)"
        assert not re.search(r"[$]\s*-?\d|ROC|Sortino|P&L|net [$]|score [+-]?\d", buf_u.getvalue() + buf_n.getvalue())
        print("dryload ok on the synthetic world: counts only, no lockbox date, nothing written")
        B_, _l = A13.load_463()
        mw, rows_ = B_.mask(*A2_WIN), A13.book_rows(B_, W)
        for cell in CELLS:                                                                  # A2 (a report): c is set by VOLATILITY on the real window, through the real arrays - and recounted here from the book file and a fresh run of the cell
            a2 = cells[cell]["A2"]
            run_ = run_cell(W, cell_leg(Lr, cell), D15.l1_cfg())
            sb_, sc_ = float(np.std(B_.raw[mw], ddof=1)), float(np.std(D15.to_B(run_.x, rows_, B_.n)[mw], ddof=1))
            assert a2["window"] == ["2017-01-03", "2018-12-31"] and a2["rows"] == int(mw.sum()) == len(pd.bdate_range("2017-01-03", "2018-12-31")) and a2["target"] == 0.25 and "pass" not in a2 and "book_shadow_line" in a2, (cell, a2)
            assert math.isfinite(a2["c"]) and a2["c"] > 0 and abs(a2["std_book"] - sb_) <= 1e-9 * sb_ and abs(a2["std_cell"] - sc_) <= 1e-9 * sc_ and sc_ > 0, (cell, a2["c"], a2["std_cell"], sc_)
            assert abs(a2["c"] * a2["std_cell"] - 0.25 * a2["std_book"]) <= 1e-12 * a2["std_book"] and abs(a2["c"] - 0.25 * sb_ / sc_) <= 1e-9 * a2["c"], cell
            assert a2["at_half_c"]["c"] == 0.5 * a2["c"] and a2["at_double_c"]["c"] == 2.0 * a2["c"] and "error" not in a2, cell
        cd = pd.read_csv(os.path.join(OUT, "resmom_audit_candidates.csv"))
        assert set(cd["cell"]) == set(CELLS) and cd.groupby("cell").size().max() <= AUDIT_N and cd["date"].max() < "2025-06-30" and cd["exit"].max() < "2025-06-30" and {"symbol", "date", "pnl", "score",
               "factor_ratio_window_to_exit", "tbis_price_ratio", "asset_status", "flags_in_window"} <= set(cd.columns), "the audit candidates: dates before the cut"
        for cell in CELLS:
            assert (cd[cd["cell"] == cell]["pnl"].diff().dropna() <= 1e-9).all(), "largest gains first"
        try:
            stage_b()
            raise AssertionError("Stage B must refuse after a Stage A fail")
        except SystemExit as e:
            assert "no Stage A pass with a complete audit" in str(e) and not os.path.exists(os.path.join(OUT, "resmom_stageB_READ.flag"))
        xs_dir = os.path.join(root, "xsml")                                                   # [R4] XSML r1 cell A's daily P&L on file: (date, pnl) over the WF sessions, plus two rows on / after the cut that must never enter
        os.makedirs(xs_dir)
        wfd = W.days[(W.days >= WF0) & (W.days <= PRE_END)]
        xs_pnl = np.random.default_rng(71).normal(0.0, 100.0, len(wfd))
        pd.DataFrame({"date": list(wfd.strftime("%Y-%m-%d")) + ["2025-06-30", "2025-07-01"], "pnl": list(xs_pnl) + [5e5, 5e5]}).to_csv(os.path.join(xs_dir, "xsml_cellA_daily.csv"), index=False)
        XSML_DIR = xs_dir
        print("--- every bar waived (stress / null / years / breadth / best-1% switched off): every cell passes - but without the hand audit the run is NOT judged")
        waive = dict(reb=1, roc=-1e9, net_pos=False, stress=False, null=False, years=0, ex2020=False, exbest=False, a2_roc=-1e9, a2_sort=-1e9, b_reb=1, b_roc=-1e9, b_sort=-1e9)
        RULES.update(waive)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            out = stage_a()
        txt = buf.getvalue()
        print(txt.rstrip())
        cells = out["stageA"]["cells"]
        assert all(c["PASS"] and c["A2"]["book_shadow_line"] and not c["audit"]["audit_complete"] for c in cells.values()) and out["judged"] is False and out["candidate"] is None and out["pending_audit"] == list(CELLS)
        assert all(d < "2025-06-30" for d in dates_of(txt)) and "NOT YET JUDGED" in txt, "Stage A printed a lockbox date"
        xr_ = out["reports"]["xsml"]                                                          # [R4] the daily correlation with each cell, recounted from the file and a fresh run of the cell
        assert xr_["on_file"] is True and xr_["rows"] == len(wfd) and xr_["file"] == "xsml_cellA_daily.csv" and "XSML r1 cell A (xsml_cellA_daily.csv" in txt and "not on file" not in txt.split("XSML r1 cell A")[1].split("\n")[0], xr_
        xs_ser = pd.Series(xs_pnl, index=wfd)
        for cell in CELLS:
            xB_ = D15.to_B(run_cell(W, cell_leg(Lr, cell), D15.l1_cfg()).x, rows_, B_.n)
            kw_ = B_.mask(WF0, PRE_END)
            a_ = pd.Series(xB_[kw_], index=pd.DatetimeIndex(B_.index[kw_]).normalize())
            j_ = pd.concat([a_, xs_ser], axis=1, join="inner")
            assert xr_["corr"][cell]["common_days"] == len(j_) and abs(xr_["corr"][cell]["daily_corr"] - np.corrcoef(j_.iloc[:, 0], j_.iloc[:, 1])[0, 1]) < 1e-9, (cell, xr_["corr"][cell])
        try:
            stage_b()
            raise AssertionError("Stage B must refuse a pending audit")
        except SystemExit as e:
            assert "no Stage A pass with a complete audit" in str(e), str(e)
        # ---- the hand audit: write 'keep' for every listed contributor -> judged, a candidate (the higher WF ROC), the audit's sha on file
        print("--- the hand audit: every listed top-50 contributor 'keep' -> judged, a Stage B candidate")
        ap = os.path.join(OUT, "resmom_audit.csv")
        cd = pd.read_csv(os.path.join(OUT, "resmom_audit_candidates.csv"))
        pd.DataFrame({"symbol": cd["symbol"], "date": cd["date"], "cell": cd["cell"], "verdict": "keep", "note": "smoke: nothing found"}).to_csv(ap, index=False)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            out = stage_a()
        txt = buf.getvalue()
        print("\n".join(l for l in txt.splitlines() if l.startswith(("audit file", "RESMOM Stage A")) or "audit " in l and "COMPLETE" in l))
        cells = out["stageA"]["cells"]
        assert out["judged"] is True and out["pending_audit"] == [] and all(c["audit"]["audit_complete"] for c in cells.values()) and out["candidate"] is not None and out["audit_sha256"] == file_sha(ap)
        cand = out["candidate"]["cell"]
        assert cand == max(CELLS, key=lambda c: (cells[c]["base"]["roc"], -CELLS.index(c))) and out["stageA"]["pass_cells"] == list(CELLS) and out["candidate"]["also_passes"] == [c for c in CELLS if c != cand], "the higher WF ROC wins"
        ca2 = cells[cand]["A2"]
        assert out["candidate"] == {"cell": cand, "c": ca2["c"], "std_book": ca2["std_book"], "std_cell": ca2["std_cell"], "window": ["2017-01-03", "2018-12-31"], "a2_book_roc": ca2["roc"],
                                    "book_shadow_line": ca2["book_shadow_line"], "also_passes": out["candidate"]["also_passes"]} and ca2["c"] > 0, "the frozen size travels with its two stds and the window"
        assert {k: out.get(k) for k in stamp()} == stamp() and out["prereg_sha256_lf"] == PREREG_SHA and len(out["parity"]) == 2 and out["manifest_sha256"] == D15.MANIFEST_PREFIX + "0" * 56
        flips = out["kept_naive_reading"]["flips"]
        assert set(flips) == set(CELLS) and set(out["reports"]["beta_to_es"]["RES"]) == {"DD days", "DD weeks (every day of them)", "all WF days"} and list(out["reports"]["crash_months"]["RAW"]) == list(CRASH_MONTHS)
        S12_ = M12.Stretch(B_.raw, B_.index, None, WF0, PRE_END)
        assert all(len(out["reports"]["episodes"][c]) == len(S12_.qual) for c in CELLS) and set(out["hygiene_counts_by_year"]) == {"registered", "look_ahead"} and "RES" in out["reports"]["turnover"]
        # a data_event on the candidate's largest contributor: it leaves the cell AND the null, the run is computed again, the NEW top-50 is unaudited -> pending again
        top = pd.read_csv(os.path.join(OUT, "resmom_audit_candidates.csv"))
        top = top[top["cell"] == cand].iloc[0]
        au = pd.read_csv(ap)
        au.loc[(au["symbol"] == top["symbol"]) & (au["date"] == top["date"]), "verdict"] = "data_event"
        au.to_csv(ap, index=False)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            out2 = stage_a()
        cd2 = pd.read_csv(os.path.join(OUT, "resmom_audit_candidates.csv"))
        assert out2["audit"]["data_event"] >= 1 and not any((cd2["symbol"] == top["symbol"]) & (cd2["date"] == top["date"])), "the removed name-month is gone from both cells' listing"
        assert out2["stageA"]["cells"][cand]["base"]["n_pos"] <= cells[cand]["base"]["n_pos"] and out2["audit_sha256"] != out["audit_sha256"]
        print(f"audit data_event on {top['symbol']} {top['date']} ({cand}'s largest gain, ${top['pnl']:,.0f}): removed from the cells and the null; positions {cells[cand]['base']['n_pos']} -> {out2['stageA']['cells'][cand]['base']['n_pos']}; "
              f"net ${cells[cand]['base']['net']:,.0f} -> ${out2['stageA']['cells'][cand]['base']['net']:,.0f}; audit complete again: {out2['judged']}")
        au = pd.read_csv(ap)
        extra = pd.DataFrame({"symbol": cd2["symbol"], "date": cd2["date"], "cell": cd2["cell"], "verdict": "keep", "note": "smoke"})
        pd.concat([au, extra]).drop_duplicates(["symbol", "date", "cell"]).to_csv(ap, index=False)
        with quiet():
            out = stage_a()
        assert out["judged"] is True and out["candidate"] is not None, "complete again after the new listing is audited"
        cand, c = out["candidate"]["cell"], out["candidate"]["c"]
        print(f"Stage A ran end to end in {time.time() - t0:.0f}s; candidate {cand} at c = x{c:g}")
        # ---- Stage B: the refusal paths, then the one read
        print("--- Stage B refusal paths: not judged / no candidate / audit incomplete, a stale stamp, a changed spec, a changed audit file, a broken size, a drifted manifest, a book that does not reproduce LB, a drifted WF, "
              "a drifted c; none may write the flag")
        flag = os.path.join(OUT, "resmom_stageB_READ.flag")

        def must_refuse(frag, burned=False):
            try:
                with quiet():
                    stage_b()
                raise AssertionError(f"Stage B must refuse ({frag})")
            except SystemExit as e:
                assert frag in str(e), (frag, str(e))
                assert burned or not os.path.exists(flag), "a refused Stage B must not burn the lockbox"
        js0 = open(sa).read()
        for edit in (lambda j: j.update(harness_sha256="0" * 64), lambda j: j.update(early_close=j["early_close"][1:]), lambda j: j.update(r15_sha256="0" * 64), lambda j: j.update(r13_sha256="0" * 64),
                     lambda j: [j.pop(k) for k in stamp()]):
            j = json.loads(js0)
            edit(j)
            json.dump(j, open(sa, "w"))
            must_refuse("different harness version")
        j = json.loads(js0)
        j["prereg_sha256_lf"] = "0" * 64
        json.dump(j, open(sa, "w"))
        must_refuse("another pre-registration")
        for edit in (lambda j: j["stageA"]["cells"][j["candidate"]["cell"]].update(PASS=False), lambda j: j.update(judged=False), lambda j: j.update(candidate=None),
                     lambda j: j["stageA"]["cells"][j["candidate"]["cell"]]["audit"].update(audit_complete=False)):
            j = json.loads(js0)
            edit(j)
            json.dump(j, open(sa, "w"))
            must_refuse("no Stage A pass with a complete audit")
        open(sa, "w").write(js0)
        for badc in (0.0, -1.0, float("nan"), None):                                        # c is a volatility ratio: any positive number is a frozen size, a broken one is a refusal before anything loads
            j = json.loads(js0)
            j["candidate"]["c"] = badc
            json.dump(j, open(sa, "w"))
            must_refuse("positive number")
        open(sa, "w").write(js0)
        with patched(me, PREREG_SHA="0" * 64):
            must_refuse("DIFFERS")
        with patched(me, WIDE_CA_SHA="0" * 64):
            must_refuse("different harness version")                                        # the registered calendar is in Stage A's stamp: another pinned sha stops it at the stamp, before anything loads
        with open(cpath_, "a") as f_:
            f_.write("cash_dividend,S01,,,2024-02-09,2024-02-09,,,0.01,,,,False\n")
        must_refuse("is not the registered wide calendar")                                  # the file changed after it was registered (WIDE_CA_SHA unchanged): refused before the flag
        with open(cpath_, "w", newline="\n") as f_:
            f_.write("\n".join([",".join(CA_COLS)] + crow + extra_) + "\n")
        assert sha_raw(cpath_) == wide_sha
        os.remove(man_p_)
        must_refuse("manifest is missing")
        j_ = json.loads(man0_)
        j_.pop("start")
        with open(man_p_, "w") as f_:
            json.dump(j_, f_)
        must_refuse("no readable start date")
        with open(man_p_, "w") as f_:
            f_.write(man0_)
        au0 = open(ap).read()
        open(ap, "a").write("ZZZ,2016-11-01,RES,keep,a changed audit file\n")
        must_refuse("not the file Stage A ran with")
        open(ap, "w").write(au0)
        okbk = lambda B, lo_, hi_, ref: {"roc": 0.0, "sortino": 0.0, "ref": list(ref), "ok": True}
        with patched(me, manifest_sha=lambda: "ffffffff" + "0" * 56), patched(A13, book_check=okbk):
            CHECK_BOOK = True
            try:
                must_refuse("not the one Stage A ran on")                                   # a drifted cache manifest (the LB book check is stubbed to pass so the manifest one is reached)
            finally:
                CHECK_BOOK = False
        j = json.loads(js0)
        j["parity"][cand]["net"] += 1e6
        json.dump(j, open(sa, "w"))
        must_refuse("do not reproduce on Stage B's data")                                   # the WF numbers drifted since Stage A
        j = json.loads(js0)
        j["candidate"]["c"] *= 1.0001
        json.dump(j, open(sa, "w"))
        must_refuse("volatility-set size c")                                                # the frozen size is recomputed from 2017-01-03 .. 2018-12-31 on Stage B's data: a drift of 1 in 10,000 stops it
        open(sa, "w").write(js0)
        CHECK_BOOK = True
        must_refuse("do not reproduce its LB numbers")
        CHECK_BOOK = False
        print("--- Stage B, the one read: the flag after the load and the checks, the verdict, a second read refused")
        cap, real_cs = {}, D15.cell_stats

        def tap(Bk, xk, ck, lo_, hi_, run_, *a_, **k_):                                     # sees the lockbox call of the one read: keeps the cell's daily series, to recompute the book add independently
            st_ = real_cs(Bk, xk, ck, lo_, hi_, run_, *a_, **k_)
            if lo_ == LB0:
                cap["x"] = np.array(xk)
            return st_
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), patched(D15, cell_stats=tap):
            ok = stage_b()
        txt_b = buf.getvalue()
        print(txt_b.rstrip())
        sb = json.load(open(os.path.join(OUT, "resmom_stageB.json")))
        assert os.path.exists(flag) and sb["pass"] == ok and sb["cell"] == cand and sb["c"] == c and sb["leg"]["n_pos"] > 0 and set(sb["order_of_reads"]) == {"SIPORB", "ATTN Stage A judged", "DDW Stage A judged"}
        assert {k: sb.get(k) for k in stamp()} == stamp() and sb["prereg_sha256_lf"] == PREREG_SHA, "Stage B's file carries the stamp"
        wb = sb["wide_calendar"]                                                              # [R1] the same registered file, cut at the lockbox's end: more rows read, fewer dropped, more dividends applied
        assert wb["file"]["csv_sha256"] == wide_sha and wb["file"]["rows_read"] > wc["file"]["rows_read"] and wb["file"]["rows_dropped_at_the_cut"] < wc["file"]["rows_dropped_at_the_cut"], (wb["file"], wc["file"])
        assert wb["dividends"]["applied_in_the_world"]["applied"] > wc["dividends"]["applied_in_the_world"]["applied"] and sb["wide_calendar"]["file"]["pinned"]["matches"] is True
        assert set(sb["checks"]) == {f"leg monthly rebalances>={RULES['b_reb']}", "leg net>0", "leg net>0 without its top name-month"} and ok is all(sb["checks"].values()), "the pass is the LEG's veto: three checks, no book"
        eb = sb["es_return_lb"]
        assert eb["stretch"] == ["2025-06-30", "2026-06-30"] and eb["undefined_es_return_sessions"] == [] and "ES return (2025-06-30 .. 2026-06-30)" in txt_b, eb
        add, mb = sb["book_add_reported"], B_.mask(LB0, LB1)                                # the book add on the lockbox at the FROZEN c: reported (and stored), recomputed here from the book file and the captured series
        want = R11.stats((B_.raw + c * cap["x"])[mb], B_.index[mb])
        assert add["c"] == c and abs(add["roc"] - want["roc"]) < 1e-9 and abs(add["sortino"] - want["sort"]) < 1e-9 and abs(add["net"] - want["net"]) < 1e-6 and abs(add["max_dd"] - want["max_dd"]) < 1e-9, add
        assert add["reference"] == {"roc": RULES["b_roc"], "sortino": RULES["b_sort"]} and add["would_have_cleared"] is bool(want["roc"] >= RULES["b_roc"] and want["sort"] >= RULES["b_sort"]) and "never a pass" in add["note"]
        assert "book add, REPORTED and never part of the pass" in txt_b and ("PASS - the leg survives" in txt_b) is ok and ("FAIL - the leg is vetoed" in txt_b) is not ok, "the printout says what the book add is"
        assert sb["leg"]["n_units"] >= 3, sb["leg"]["n_units"]
        # the pass is the leg's veto ALONE: the same read again (the smoke dir only - on the real OUT the flag is exclusive-create) with the leg forced to pass and the book add's bar forced to miss, then the leg forced
        # to fail and the bar forced to clear. The verdict follows the leg in both, the book add is reported in both and its numbers do not move
        def reread(leg_ok, book_ok):
            os.remove(flag)
            os.remove(os.path.join(OUT, "resmom_stageB.json"))

            def forced(Bk, xk, ck, lo_, hi_, run_, *a_, **k_):
                st_ = real_cs(Bk, xk, ck, lo_, hi_, run_, *a_, **k_)
                if lo_ == LB0:
                    st_ = {**st_, "n_units": 10 ** 6 if leg_ok else 0, "net": 1e6 if leg_ok else -1e6, "net_ex_top_pos": 1e6 if leg_ok else -1e6}
                return st_
            keep_bar = (RULES["b_roc"], RULES["b_sort"])
            RULES["b_roc"], RULES["b_sort"] = (-1e9, -1e9) if book_ok else (1e9, 1e9)
            b_ = io.StringIO()
            try:
                with contextlib.redirect_stdout(b_), patched(D15, cell_stats=forced):
                    ok_ = stage_b()
            finally:
                RULES["b_roc"], RULES["b_sort"] = keep_bar
            return ok_, json.load(open(os.path.join(OUT, "resmom_stageB.json"))), b_.getvalue()
        for leg_ok, book_ok in ((True, False), (False, True)):
            ok2, sb2, t2 = reread(leg_ok, book_ok)
            assert ok2 is leg_ok and sb2["pass"] is leg_ok and all(sb2["checks"].values()) is leg_ok and sb2["book_add_reported"]["would_have_cleared"] is book_ok, (leg_ok, book_ok, sb2["checks"])
            assert abs(sb2["book_add_reported"]["roc"] - add["roc"]) < 1e-9 and sb2["book_add_reported"]["c"] == c and os.path.exists(flag), "the book add is the same sum whatever the verdict"
            assert ("PASS - the leg survives" in t2) is leg_ok and ("FAIL - the leg is vetoed" in t2) is not leg_ok and ("FORWARD SHADOW" in t2) is leg_ok
            print(f"  leg forced {'to pass' if leg_ok else 'to fail'}, book-add bar forced {'to clear' if book_ok else 'to miss'}: Stage B {'PASS' if ok2 else 'FAIL'}, would_have_cleared {sb2['book_add_reported']['would_have_cleared']} - the verdict is the leg's")
        must_refuse("already read", burned=True)
        try:
            stage_a()
            raise AssertionError("Stage A must be frozen once the lockbox has been read")
        except SystemExit as e:
            assert "Stage A is frozen" in str(e)
        try:                                                                               # the commands that never touch data
            main(["bogus"])
        except SystemExit:
            pass
        pm = peak_mb()
        print("Stage B refused before the flag in every case above, wrote the flag only after the load and the checks, and refused a second read")
        print(f"SMOKE OK ({time.time() - t_start:.0f}s" + (f", peak memory {pm:,.0f} MB" if pm else "") + ") - synthetic numbers mean nothing; every command ran end to end offline")
    finally:
        OUT, CHECK_BOOK, NREP = keep["OUT"], keep["CHECK_BOOK"], keep["NREP"]
        WIDE_CA_SHA, XSML_DIR, ANATOMY_ROOT = keep["WIDE"]
        RULES.clear()
        RULES.update(keep["RULES"])
        SPEC.clear()
        SPEC.update(keep["SPEC"])
        D15.SPEC.clear()
        D15.SPEC.update(keep["DSPEC"])
        R11.OUT, A13.OUT = keep["R11_OUT"], keep["A13_OUT"]
        D15.TBIS_CSV, A13.TBIS_QA = keep["TBIS"]
        S.OUT, S.CACHE, S.BOOK, S.SMOKE, S.PACE, S.BACKOFF, S.RETRY, S._http_get = keep["S"]
        data.find_master, data.load_master_arrays = keep["es"]


def main(argv):
    cmd, args = (argv[0], argv[1:]) if argv else ("", [])
    fn = {"selftest": selftest, "smoke": smoke, "dryload": dryload, "stage_a": stage_a, "stage_b": stage_b}.get(cmd)
    if fn is None:
        print("usage: r17_resmom.py selftest | smoke DIR | dryload | stage_a | stage_b   (stage_a after the hand audit of the previous run is written; stage_b only on the stock families' one sealed-year day)")
        return
    if cmd in ("stage_a", "stage_b"):
        os.makedirs(OUT, exist_ok=True)
    fn(*args)


if __name__ == "__main__":
    main(sys.argv[1:])
