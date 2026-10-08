# NEWISSUE r1 - recent US listings against seasoned stocks of the same liquidity, rebalanced MONTHLY, dollar-neutral: cells E (PRIMARY: SHORT every NEW name, LONG ES at the OLS beta of the equal-weight NEW basket x the short notional - an ex-ante market hedge,
# addendum 1 [N2]) and M (SHORT every NEW name, LONG for each the SEASONED universe name nearest to it in 20-session mean dollar volume, each used once), a leg for BOOK #463 that must clear the STANDALONE bars (MANAGER #56). Pre-registered:
# tools/rocfrontier/PREREG_NEWISSUE_R1.txt (canonical LF sha256 e4900bcb...03ae = DRAFT v1 + PRE-DATA ADDENDUM 1 (MANAGER's review #73: [B] incremental book add, [N1] borrow 3%/yr, [N2] cell E primary + the beta rule, [N3] the 4-8-month row, [N4] first-session sanity,
# [N5] P&L by listing-year cohort, [N6] the size floor) + PRE-DATA ADDENDUM 2 (owner standing order addendum 2: [X1] the book add is incremental over the RESMOM line, [X2] deeper diagnostics) + PRE-DATA ADDENDUM 3 (MANAGER #99 / #100, after the counts-only dryload: [N7] the registered floor is 10 NEW
# names and every cell row is also printed under the 20-name floor beside it, [N8] bar (a) = 40 traded rebalances, [N9] 'net > 0 without calendar 2022' stays binding and any pass is a LOW-POWER, FLAGGED result, [N10] dollars a year beside every ROC @ $30k of a book-add report + the reference line's episode table)).
# Every rule, threshold, window and cost below is that file; where it is silent the choice is marked CHOICE.
# NEWISSUE is RESMOM r1's and DIVRUN r1's sibling in the same lane on the same data: r17_resmom.py (the monthly basket: World, the pinned wide calendar, the dividend / spin-off arrays, the fills / marks / costs / borrow, the hygiene windows, the audit file) and r18_divrun.py (the REFERENCE
# book #463 + 0.264 x RES and its incremental A2, the ES prints carried across the masters' holes, the null statistics) are imported, never copied and never edited - and through them r15_ddw.py, r5_siporb.py, r11_risk.py, r12_mdl.py and r13_attn.py. What this file adds is the AGE logic:
# listing sessions and [N4], who is NEW and who is SEASONED, the matched long, the ex-ante ES hedge, the 10-name floor (and the 20-name reading beside it), the family-aware null (seasoned names drawn at random, re-matched, re-hedged) and the diagnostics by age and by cohort.
#   python r20_newissue.py selftest    hand-made worlds, no data: the listing session and [N4]'s 18-of-20 rule, the NEW / SEASONED windows, the spinco and name-change exclusions, the nearest-dollar-volume match against a plain-python oracle, the ex-ante beta hedge
#                                      against a hand count, the floors (10 NEW names registered, 20 reported) and the bar (a) = 40, borrow and costs, the null (seasoned draws, re-match, re-hedge), the beta rule's 0.20 gate, the cohort / age tables, [X1] on a stub RES line file, dollars a year, the reference's episodes inside the cell's stretch, the refusals
#   python r20_newissue.py smoke DIR   offline end-to-end on SYNTHETIC worlds (r5_siporb's fake Alpaca transport, a fake ES master, a fake #463, a fake RESMOM line file, a fake calendar): a world with a planted new-issue underperformance that Stage A must find and a world without one where
#                                      it must not; DIR's name must contain 'smoke'; every command except Stage B's read runs (Stage B is exercised on the synthetic world only by `smoke DIR stage_b`)
#   python r20_newissue.py dryload     WF inputs only (every input cut to dates < 2025-06-30): prints COUNTS - listings by year and [N4]'s failures, NEW names per month and by cohort, months under the registered 10-name floor and the traded months under BOTH floors (10 registered, 20 reported) by fill year, the spinco / name-change exclusions by year, the first and last traded ranks -
#                                      never a price, return, beta, P&L or Stage A statistic
#   python r20_newissue.py stage_a     WF Stage A (cells E and M) + the null + A2 (an INCREMENTAL report over the REFERENCE book #463 + 0.264 x RES) + the reports + the diagnostics -> newissue_stageA.json (+ newissue_audit_candidates.csv), PRE-LOCKBOX ONLY
#   python r20_newissue.py stage_b     Stage B (lockbox, ONCE): refuses unless the lead's flag file newissue_stageB_GO.flag is on file (and a Stage A candidate with the hand audit signed off by that flag); the pass is the LEG's veto
# Reads (never writes) the SIPORB cache through r5_siporb, the ES 5m RTH masters through augur_engine.data, the #463 book through r11_risk, the sha-pinned wide corporate-actions calendar (cut at read) and - Stage A only - RESMOM's sha-pinned WF line file (the REFERENCE book). Results go to OUT (outside git).
# Nothing here pulls, commits, pushes or writes anywhere else.
import contextlib, io, json, math, os, re, shutil, sys, tempfile, time
from collections import Counter, defaultdict
from types import SimpleNamespace
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import numpy as np, pandas as pd
import r17_resmom as M17             # the sibling harness (RESMOM r1): its loaders, calendar, dividend arrays, units, hygiene windows and audit file are called wherever they fit
import r18_divrun as DV              # the sibling harness (DIVRUN r1): the REFERENCE book and its incremental A2, the ES carried prints, the null statistics
D15, S, R11, M12, A13 = M17.D15, M17.S, M17.R11, M17.M12, M17.A13       # r15_ddw (World, universe, cell statistics, seat), r5_siporb, r11_risk, r12_mdl, r13_attn - through r17's own imports

TS = pd.Timestamp
THIS = sys.modules[__name__]
OUT = os.environ.get("EDGELOG_NEWISSUE_R1", r"C:\EdgeLog\_anatomy_cache\rocfrontier\newissue_r1")        # results, outside git
PREREG = os.path.join(HERE, "PREREG_NEWISSUE_R1.txt")
PREREG_SHA = "e4900bcb1d74e2c92e88fb03452c1843c9dc379c807f15e83ad3f03d583b03ae"                      # canonical (LF) sha256 of the pre-registration: DRAFT v1 + PRE-DATA ADDENDUM 1 (MANAGER #73) + ADDENDUM 2 (owner standing order addendum 2) + ADDENDUM 3 (MANAGER #99 / #100); if more edits land the lead updates it before the real run
WF0, PRE_END, LB0, LB1 = M17.WF0, M17.PRE_END, M17.LB0, M17.LB1          # #463's registered WF stretch 2016-07-01 .. 2025-06-29 (the book checks, the reference and the call for the book's rows read it); LB = exits 2025-06-30 .. 2026-06-30 INCLUSIVE; cuts: S.LB0 / S.END
WFN = TS("2018-02-01")           # NEWISSUE's own WF: positions EXITED 2018-02-01 .. 2025-06-29 (the first rank whose 24-month window is fully observable is 2018-01-31; 89 rebalances in Stage A's data)
FIRST_SESSION = TS("2016-01-04")  # the cache's first session: a listing is dated only from the next one on (2016-01-05); a name with a bar on it is 'present at the first session'
BOOK_WF, BOOK_LB, DEEPEST_WF = M17.BOOK_WF, M17.BOOK_LB, M17.DEEPEST_WF
NREP, SEED = 500, 20261005
CELLS = ("E", "M")                                                      # the family: 2 cells; E is the PRIMARY
CELL_NAME = {"E": "E (PRIMARY): short every NEW name, long ES at beta x the short notional", "M": "M (matched): short every NEW name, long the nearest-dollar-volume SEASONED name of each"}
YEARS = tuple(range(2017, 2025))                                        # the eight July-June WF years 2017-18 (2018-02-01 .. 2018-06-30: short, it counts) .. 2024-25
A2_WIN = (TS("2018-02-01"), TS("2020-01-31"))                           # A2 (a REPORT): c is set on the cell's first two full years ...
A2_TARGET, A2_REPORT = 0.25, (0.5, 2.0)                                  # ... so that c x the cell's daily std = 25% of #463's over them; the book at 0.5c and 2c is reported
X2022 = (TS("2022-01-01"), TS("2022-12-31"))                            # 'net > 0 without calendar 2022' (the bust year)
BOOM = (TS("2020-01-01"), TS("2021-12-31"))                             # 2020-21 (the listing boom) apart from 2022 (the bust)
HALVES = (("2018-02-01 .. 2021-12-31", TS("2018-02-01"), TS("2021-12-31")), ("2022-01-01 .. 2025-06-29", TS("2022-01-01"), TS("2025-06-29")))      # [X2] the regime halves (the first half starts at the WF's own start)
COST_BPS, STRESS_BPS = D15.COST_BPS, D15.STRESS_BPS                      # 5 bps of the notional a side on the stocks (base); stress 10 and 20
ES_BPS = 0.5                                                            # ES 0.5 bps of the hedge notional a side (the prereg's figure; the exact fractional hedge - DIVRUN's whole-MES rule is not registered here: CHOICE)
BORROW, BORROW_STRESS = 0.03, (0.10, 0.25)                              # [N1] borrow on every NEW short: 3% a year (base), stress 10% and 25% on every short day
BETA_RULE = 0.20                                                        # [N2] a cell with |realised beta| > 0.20 is never credited its drawdown-day profile
AUDIT_N = 50                                                             # (f) the largest single-name contributors audited by hand
COHORTS = tuple(range(2016, 2025))                                      # [N5] listing-year cohorts 2016 .. 2024
AGE_MONTHS = tuple(range(4, 25))                                        # [X2] the path by months since listing: one row per month 4 .. 24
SPEC = {"new_lo": 126, "new_hi": 504,    # NEW: listed 126 .. 504 sessions before the rank close r
        "seas_months": 36,               # SEASONED: listed MORE than 36 calendar months before r (or present at the first session)
        "nc_months": 24,                 # no name change on the calendar in the 24 calendar months before r (NEW and SEASONED)
        "n4_next": 20, "n4_min": 18,     # [N4] a listing session counts only with a raw close and volume on >= 18 of the 20 sessions after it
        "floor": 10,                     # [N7] (addendum 3, replacing [N6]'s 20) a month with fewer than 10 NEW names - counted after every removal - trades nothing in either cell
        "slot": 4000.0,                  # $4,000 a name, fractional shares, no compounding
        "beta_win": 126, "beta_min": 115,  # the ex-ante hedge: OLS of the equal-weight NEW basket's daily return on ES over the 126 sessions r-125 .. r (CHOICE: >= 115 basket-ES pairs of the 126, RESMOM's 230-of-252 share)
        "dv_n": 20,                      # the match: the 20-session mean raw dollar volume, sessions r-19 .. r
        "hold_win": 252, "min_n": 230,   # CHOICE: RESMOM's 252-session history rule (230 own returns AND 230 ES pairs) applies to SEASONED names; NEW names are exempt (the prereg)
        "pre": 25,                       # hygiene known at the decision: sessions r-25 .. r, all four reasons (RESMOM's window); CHOICE: the older part of the 126-session regression window, r-125 .. r-26, carries the three unregistered ones
        "old": 125,
        "n3_lo": 84, "n3_hi": 168,       # [N3] names 4 to 8 months after listing
        "month": 21}                     # sessions in an age 'month'
RULES = {"reb": 40, "roc": 15.0, "net_pos": True, "stress": True, "borrow_stress": True, "null": True, "years": 5, "ex2020": True, "ex2022": True, "exbest": True, "best_pct": 1,      # Stage A (a) - (e); the booleans are switches only smoke() ever turns off
         "beta_abs": BETA_RULE, "b_reb": 10, "b_roc": BOOK_LB[0], "b_sort": BOOK_LB[1]}                                                                                           # Stage B: >= 10 monthly rebalances; the book add's reference (#463's own LB 155.54 / 4.150), reported only
FLOOR_REPORTED = 20      # [N7] every cell row is ALSO computed and printed under this floor (the draft's / [N6]'s 20 NEW names) beside the registered one - both floors side by side; the reading is REPORTED, never a pass route
LOW_POWER = ("LOW-POWER FLAG [N9]: the traded months are concentrated in 2018-03 .. 2022-03 (one listing boom, 2020-21, and its bust, 2022) because recent listings almost vanish from the top-500 universe after 2022; "
             "'net > 0 without calendar 2022' stays binding, and any pass is a LOW-POWER, FLAGGED result")
CHECK_BOOK = True        # refuse to judge if the #463 records / the DD structure / the cache manifest / the first session / the reference do not reproduce the registered facts; a real run always checks (only smoke() may switch it)
HYG = D15.HYG            # the four data-hygiene reasons [T2], in the order a position's first reason is attributed: split, gap, tbis, jump
GO_FLAG, READ_FLAG = "newissue_stageB_GO.flag", "newissue_stageB_READ.flag"     # Stage B needs the lead's go-flag; the one-shot read flag is written (exclusively) after every load and check
WIDE_CA_SHA = M17.WIDE_CA_SHA
ST_NONE, ST_START, ST_OK, ST_FAIL, ST_LATE = 0, 1, 2, 3, 4              # listing status of a name: no bar | present at the first session (undated) | dated and accepted [N4] | dated and failed [N4] | dated but fewer than 20 sessions follow in the data (unverifiable)
ST_NAME = {ST_NONE: "no bar", ST_START: "present at the first session", ST_OK: "listing accepted", ST_FAIL: "[N4] failed", ST_LATE: "unverifiable (under 20 sessions follow)"}
ZI, ZF, ZB = np.zeros(0, np.int64), np.zeros(0), np.zeros(0, bool)


# ------------------------------------------------------------------ guards: the prereg, the stamp, the cut, the files
def refuse(msg):
    raise SystemExit(msg)


assert_cut, peak_mb, patched, ceil_pct = A13.assert_cut, A13.peak_mb, A13.patched, A13.ceil_pct
file_sha, manifest_sha, book_checks = D15.file_sha, D15.manifest_sha, D15.book_checks      # module-level names, so a test can stub them


def prereg_ok():
    """the frozen spec this file implements must still be the registered one (a changed spec = a new file, r2): a missing or changed file refuses every stage. Also checked against the committed blob when there is one
    (r15_ddw.committed_state, pointed at this file's names for the call); until it is committed that is printed (the lead commits before the real run) and recorded in the Stage A file"""
    if not os.path.exists(PREREG):
        refuse("refused: PREREG_NEWISSUE_R1.txt is not next to this file - the spec cannot be verified (nothing computed, lockbox NOT read)")
    if R11.sha_lf(PREREG) != PREREG_SHA:
        refuse("refused: PREREG_NEWISSUE_R1.txt DIFFERS from the registered one - a changed spec is a new file, r2 (nothing computed, lockbox NOT read)")
    with patched(D15, PREREG=PREREG, PREREG_SHA=PREREG_SHA):
        st = D15.committed_state()
    if st == "differs":
        refuse("refused: the COMMITTED PREREG_NEWISSUE_R1.txt differs from the registered sha - the file on disk is not the file in git (nothing computed, lockbox NOT read)")
    print("prereg check: PREREG_NEWISSUE_R1.txt sha256 matches the registered one; committed blob: " + {"match": "matches too", "untracked": "NOT COMMITTED YET - commit it before the real run",
                                                                                                         "unknown": "git not available here (not checked)"}[st])
    return {"verified": True, "committed": st}


def stamp():
    """the version a stage ran with: this file's LF sha256 + r18's and r17's and every harness they import numbers from (r15's data layer / marks / statistics, r5_siporb's Data / read_long, r11's book and stats, r12's DO / rho_dd, r13's helpers) + the pinned
    calendar's sha + the shared half-day list; Stage B refuses on any change, so a change to any of them after Stage A sends it through Stage A again"""
    s = DV.stamp()
    return {"harness_sha256": R11.sha_lf(os.path.abspath(__file__)), "r18_sha256": s["harness_sha256"], **{k: v for k, v in s.items() if k != "harness_sha256"}}


@contextlib.contextmanager
def spec(**kw):
    """swap SPEC entries for a block and put them back (the self-tests and the smoke shrink the windows and the floor; nothing stays patched)"""
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


def jyear(d):
    """the July-June year of a date (2018-06-29 is 2017-18, 2018-07-02 is 2018-19)"""
    return DV.jyear(d)


# ------------------------------------------------------------------ the calendar's two extra tables: a spin-off's NEW symbol and the name changes (r17_resmom.wide_load keeps neither: it reads the parent's symbol only)
def cal_extra(cut, csv=None):
    """the pinned wide corporate-actions calendar's spin-off NEW symbols and name changes -> (SimpleNamespace(spin = frame (sym = the spun-off company's symbol, parent, ev), chg = frame (old, new, ev)), info). r17_resmom.wide_load has already enforced the file's sha / manifest / columns in
    every stage that runs numbers; this only re-reads the same file (the stages call it right after wide_load). The date a row acts on is its ex-date, else its process date (a name change has no ex-date: r16_xgap's flatten); an undated row is counted and never used. Cut at READ time:
    a row dated on / after `cut` is dropped and asserted gone. A missing file -> empty tables (counts only: the dryload runs without it)"""
    csv = csv or M17.wide_paths()["csv"]
    empty = SimpleNamespace(spin=pd.DataFrame({"sym": pd.Series(dtype=str), "parent": pd.Series(dtype=str), "ev": pd.Series(dtype="datetime64[ns]")}),
                            chg=pd.DataFrame({"old": pd.Series(dtype=str), "new": pd.Series(dtype=str), "ev": pd.Series(dtype="datetime64[ns]")}))
    if not os.path.exists(csv):
        return empty, {"present": False, "path": csv}
    df = pd.read_csv(csv, dtype=str, keep_default_na=False)
    miss = [c for c in M17.CA_COLS if c not in df.columns]
    if miss:
        refuse(f"refused: the wide calendar lacks the column(s) {miss} of r16_xgap's flat CSV (nothing computed, lockbox NOT read)")
    ex = pd.to_datetime(df["ex_date"].replace("", np.nan), errors="coerce")
    ev = ex.fillna(pd.to_datetime(df["process_date"].replace("", np.nan), errors="coerce"))
    df = df.assign(ev=ev)
    n0 = len(df)
    df = df[~(df["ev"] >= TS(cut)).to_numpy()].reset_index(drop=True)                    # NaT compares False: an undated row stays (and is counted, never used)
    A13.assert_cut("wide calendar (name changes / spin-offs)", df["ev"].dropna(), cut)
    sp = df[(df["type"] == "spin_off")]
    sp_ok = sp[(sp["new_symbol"].str.strip() != "") & sp["ev"].notna()]
    ch = df[(df["type"] == "name_change")]
    ch_ok = ch[((ch["old_symbol"].str.strip() != "") | (ch["new_symbol"].str.strip() != "")) & ch["ev"].notna()]
    by_year = lambda fr: {int(y): int(n) for y, n in fr["ev"].dt.year.value_counts().sort_index().items()}
    first_of = lambda fr: (f"{fr['ev'].min():%Y-%m-%d}" if len(fr) else None)
    info = {"present": True, "path": csv, "rows_on_file": int(n0), "rows_read": int(len(df)), "rows_dropped_at_the_cut": int(n0 - len(df)),
            "spin_off": {"rows": int(len(sp)), "usable": int(len(sp_ok)), "no_new_symbol_or_date": int(len(sp) - len(sp_ok)), "by_year": by_year(sp_ok), "earliest": first_of(sp_ok)},
            "name_change": {"rows": int(len(ch)), "usable": int(len(ch_ok)), "no_symbol_or_date": int(len(ch) - len(ch_ok)), "by_year": by_year(ch_ok), "earliest": first_of(ch_ok)}}
    return SimpleNamespace(spin=pd.DataFrame({"sym": sp_ok["new_symbol"].str.strip().to_numpy(), "parent": sp_ok["symbol"].str.strip().to_numpy(), "ev": sp_ok["ev"].to_numpy()}),
                           chg=pd.DataFrame({"old": ch_ok["old_symbol"].str.strip().to_numpy(), "new": ch_ok["new_symbol"].str.strip().to_numpy(), "ev": ch_ok["ev"].to_numpy()})), info


def calendar_arrays(W, extra):
    """the two tables on the grid: spin_row (S,) = the session row of the FIRST spin-off that creates the name as its new symbol (the first session on / after the date; a date after the data is not placed), BIG when none; nccs (T + 1, S) int32 = the running count of name-change
    events (a row names the old or the new symbol, either is the name: CHOICE, the conservative reading) by session row, so the events in rows a .. b are nccs[b + 1] - nccs[a] -> (spin_row, nccs, counts)"""
    T, S_ = W.T, W.S
    spin_row = np.full(S_, T + 10 ** 6, np.int64)
    nccs = np.zeros((T + 1, S_), np.int32)
    n_spin = n_chg = 0
    if extra is not None:
        dv = np.asarray(W.days).astype("datetime64[ns]")
        sp, ch = extra.spin, extra.chg
        if len(sp):
            ci = pd.Index(W.syms).get_indexer(sp["sym"].astype(str))
            ri = DV.rows_of(dv, sp["ev"].to_numpy().astype("datetime64[ns]"))
            ok = (ci >= 0) & (ri >= 0)
            np.minimum.at(spin_row, ci[ok], ri[ok])
            n_spin = int(ok.sum())
        if len(ch):
            ri = DV.rows_of(dv, ch["ev"].to_numpy().astype("datetime64[ns]"))
            cnt = np.zeros((T, S_), np.int32)
            for col in ("old", "new"):
                ci = pd.Index(W.syms).get_indexer(ch[col].astype(str))
                ok = (ci >= 0) & (ri >= 0)
                np.add.at(cnt, (ri[ok], ci[ok]), 1)
                n_chg += int(ok.sum())
            nccs[1:] = np.cumsum(cnt, axis=0, dtype=np.int32)
    return spin_row, nccs, {"spin_events_placed": n_spin, "name_change_events_placed": n_chg}


# ------------------------------------------------------------------ listing sessions [N4]
def listing_info(Cl, Vv, sp=None):
    """a name's LISTING SESSION = its first session with a bar (a raw close) in the cache, dated only when it is not the cache's first session (a name with a bar there is 'present at the first session': no listing, no age); accepted only if it has a raw close AND a positive
    volume on >= 18 of the 20 sessions after it ([N4]: a stray bar before a real listing, or a relisting gap, is not a listing). CHOICE: 'has a volume' = a finite volume above zero. A dated listing with fewer than 20 sessions after it in the data cannot be checked (unverifiable, counted apart;
    it is neither NEW nor SEASONED anywhere in WF). -> SimpleNamespace(first (S,) the first bar's row or -1, L (S,) the dated listing row or -1, st (S,) the status code, n_after (S,) the sessions of the 20 after it that carry a close and a volume)"""
    sp = sp or SPEC
    T, S_ = Cl.shape
    has = np.isfinite(Cl)
    first = np.where(has.any(axis=0), has.argmax(axis=0), -1)
    ok = has & np.isfinite(Vv) & (Vv > 0)
    cs = np.zeros((T + 1, S_), np.int32)
    np.cumsum(ok, axis=0, dtype=np.int32, out=cs[1:])
    k, j = sp["n4_next"], np.arange(S_)
    f0 = np.maximum(first, 0)
    n_after = np.where(first >= 0, cs[np.minimum(f0 + k + 1, T), j] - cs[np.minimum(f0 + 1, T), j], 0)       # rows first + 1 .. first + k
    dated, complete = first >= 1, (first >= 0) & (first + k <= T - 1)
    st = np.full(S_, ST_NONE, np.int64)
    st[first == 0] = ST_START
    st[dated & complete & (n_after >= sp["n4_min"])] = ST_OK
    st[dated & complete & (n_after < sp["n4_min"])] = ST_FAIL
    st[dated & ~complete] = ST_LATE
    return SimpleNamespace(first=first, L=np.where(dated, first, -1), st=st, n_after=n_after.astype(np.int64))


def listing_counts(days, li, mask=None):
    """COUNTS by listing year over the names (mask = a subset): {'present_at_first_session': n, 'no_bar': n, 'by_year': {year: {'dated': n, 'accepted': n, 'failed': n, 'unverifiable': n}}}"""
    m = np.ones(len(li.st), bool) if mask is None else np.asarray(mask, bool)
    out = {"present_at_first_session": int(((li.st == ST_START) & m).sum()), "no_bar": int(((li.st == ST_NONE) & m).sum()), "by_year": {}}
    yr = np.asarray(pd.DatetimeIndex(days).year)
    for y in sorted(set(yr[li.L[(li.L >= 0) & m]].tolist())):
        sel = m & (li.L >= 0) & (yr[np.maximum(li.L, 0)] == y)
        out["by_year"][int(y)] = {"dated": int(sel.sum()), "accepted": int((sel & (li.st == ST_OK)).sum()), "failed": int((sel & (li.st == ST_FAIL)).sum()), "unverifiable": int((sel & (li.st == ST_LATE)).sum())}
    return out


# ------------------------------------------------------------------ ES: the prints the hedge trades at (09:35 in and out, 16:00 between), carried across the masters' holes
def raw_open_prints(W):
    """the UNADJUSTED 09:35 ES print on every stock session (the level the hedge's contracts are counted on): the raw master's 'open' of r15's es_prints frame; a hand-made world without that frame: W.es.e5r when it has one, else the roll-corrected print itself"""
    cov = getattr(W, "es_cov", None)
    if cov is not None:
        return cov["raw_prints"]["open"].reindex(W.days).to_numpy(float)
    v = getattr(W.es, "e5r", None)
    return np.asarray(W.es.e5 if v is None else v, float)


def attach_es(W):
    """the ES prints of the hedge on a World: esA / esR = the roll-corrected / unadjusted 16:00 print carried across a session with none (r18_divrun.attach_es: the ES move over a hole is earned at the next print), e5A / e5R = the roll-corrected / unadjusted 09:35 print the position is
    OPENED and CLOSED at (the stocks are filled at the official open; the ES master's first price after it is the close of its 09:30 bar). CHOICE: a session with no 09:35 print falls back to the previous session's 16:00 print (no overnight move is earned that session)"""
    DV.attach_es(W)
    pa, pr = np.r_[np.nan, W.esA[:-1]], np.r_[np.nan, W.esR[:-1]]
    e5a, e5r = np.asarray(W.es.e5, float), raw_open_prints(W)
    W.e5A = np.where(np.isfinite(e5a), e5a, pa)
    W.e5R = np.where(np.isfinite(e5r) & (e5r > 0), e5r, pr)
    W._es_leg = {}
    return W


def es_leg(W, f, x, bps=ES_BPS):
    """cell E's hedge, one LONG ES position per $1 of entry notional, over rows f .. x: opened at the 09:35 print of the fill session f, marked at every 16:00 print of rows f .. x - 1 and closed at the 09:35 print of the exit session x (the stocks' own fill and exit are the official opens), fixed
    (fractional) contracts = $1 / the unadjusted entry print: the day's P&L is the roll-corrected change over that level (r18_divrun's exact hedge). ES costs `bps` a side of the notional: of the entry notional at the entry, of the exit value (x's unadjusted print over f's) at the exit. A missing
    print is a zero move. -> (H,) the daily P&L, column h = row f + h"""
    key = (int(f), int(x), float(bps))
    cache = W.__dict__.setdefault("_es_leg", {})
    if key in cache:
        return cache[key]
    H = x - f + 1
    prev, cur = np.empty(H), np.empty(H)
    prev[0], prev[1:] = W.e5A[f], W.esA[f:x]
    cur[:H - 1], cur[H - 1] = W.esA[f:x], W.e5A[x]
    with np.errstate(invalid="ignore", divide="ignore"):
        g = (cur - prev) / W.e5R[f]
        ratio = W.e5R[x] / W.e5R[f]
    g = np.where(np.isfinite(g), g, 0.0)
    c = bps * 1e-4
    g[0] -= c
    g[H - 1] -= c * (float(ratio) if np.isfinite(ratio) else 1.0)
    cache[key] = g
    return g


# ------------------------------------------------------------------ the context: listing sessions, the calendar's two tables, the ES prints
def make_ctx(W, extra=None, counts_only=False):
    """everything the cells read besides the World: the listing arrays (from the raw close / volume of the World's names), the spinco / name-change tables on the grid, the ES prints of the hedge, the ES-return mask. The World's names are in ascending symbol order (r5_siporb sorts them), so 'ties
    by symbol' is 'ties by column' everywhere below - asserted here"""
    assert (np.asarray(W.syms)[:-1] <= np.asarray(W.syms)[1:]).all(), "the World's names must be in ascending symbol order: ties by symbol are ties by column"
    attach_es(W)
    li = listing_info(W.Cl, W.Vv)
    spin_row, nccs, cal_counts = calendar_arrays(W, extra)
    return SimpleNamespace(li=li, L=li.L, st=li.st, spin_row=spin_row, nccs=nccs, cal_counts=cal_counts, es_ok=np.isfinite(np.asarray(W.es.ret, float)), counts_only=bool(counts_only), extra=extra)


def cal_start_row(W, cal_start):
    """the first session row on / after the calendar's start date (rows before it are not covered by the calendar)"""
    return int(W.days.searchsorted(TS(cal_start), side="left"))


# ------------------------------------------------------------------ the two numbers a rebalance needs besides the classification: the 20-session dollar volume (the match) and the ex-ante beta (cell E's hedge)
def dv20(W, r, cols):
    """the 20-session mean RAW dollar volume of the names `cols` at the rank close r: sessions r-19 .. r (the universe's own ranking quantity: RESMOM's top-500 rule reads the same rows); NaN if a session of the window has no close or volume"""
    a = r - SPEC["dv_n"] + 1
    return (np.asarray(W.Cl[a:r + 1][:, cols], float) * np.asarray(W.Vv[a:r + 1][:, cols], float)).mean(axis=0)


def match_nearest(dv_new, dv_cand, key_new, key_cand):
    """the SEASONED name nearest to each NEW name in dollar volume, EACH SEASONED NAME USED ONCE, ties by symbol: CHOICE - the prereg gives no order of assignment, so the global GREEDY is used: the closest (NEW, candidate) pair first, then the closest pair among the names still unused, and so on
    (nearest = the smallest absolute difference of the 20-session mean dollar volume, in dollars); equal distances are broken by the NEW name's symbol, then the candidate's (key_* = the column, which is the symbol's rank). A NEW name with no candidate left stays unmatched (-1; only when there are
    fewer candidates than NEW names, or a dollar volume is undefined: such a name is neither matched nor a match). Exact, and fast: every NEW name's partner is among its n nearest candidates by (distance, symbol) - at most n - 1 are taken by the others - so only those pairs are sorted;
    the candidates are put in symbol order first, so a STABLE sort on the distance is the (distance, symbol) order, ties included -> (n,) the index into the candidates, -1 = none"""
    dv_new, dv_cand = np.asarray(dv_new, float), np.asarray(dv_cand, float)
    key_new, key_cand = np.asarray(key_new, np.int64), np.asarray(key_cand, np.int64)
    n, m = len(dv_new), len(dv_cand)
    out = np.full(n, -1, np.int64)
    vn, vc = np.flatnonzero(np.isfinite(dv_new)), np.flatnonzero(np.isfinite(dv_cand))
    if not len(vn) or not len(vc):
        return out
    oc = vc[np.argsort(key_cand[vc], kind="stable")]                             # the usable candidates in symbol order
    Dm = np.abs(dv_new[vn][:, None] - dv_cand[oc][None, :])
    K = min(len(oc), len(vn))
    near = np.argsort(Dm, axis=1, kind="stable")[:, :K]                         # per NEW name its K nearest candidates by (distance, symbol)
    I = np.repeat(vn, K)
    C = oc[near].ravel()
    Dist = np.take_along_axis(Dm, near, axis=1).ravel()
    order = np.lexsort((key_cand[C], key_new[I], Dist))
    used_n, used_c = np.zeros(n, bool), np.zeros(m, bool)
    left = len(vn)
    for q in order:
        i, c = I[q], C[q]
        if used_n[i] or used_c[c]:
            continue
        used_n[i] = used_c[c] = True
        out[i] = c
        left -= 1
        if not left:
            break
    return out


def basket_beta_many(W, r, cols2d):
    """[N2] the ex-ante hedge ratio of D baskets at once: cols2d (D, n) = the names of each basket (columns of the World). The EQUAL-WEIGHT basket's daily return on a session = the mean of its names' split-safe TOTAL returns that session (W.Rd: price + cash dividends, spin-off / stock-dividend
    sessions left out) over the names that have one; the beta = the OLS slope (an intercept and a slope) of that series on ES's daily return over the 126 sessions r-125 .. r (every NEW name is at least 126 sessions old, so the whole window is the names' own history; sessions on which ES has no return are
    skipped for every basket) - NaN under 115 basket-ES pairs (CHOICE) or without ES variation -> (beta (D,), pairs (D,))"""
    a = r - SPEC["beta_win"] + 1
    cols2d = np.asarray(cols2d, np.int64)
    D, n = cols2d.shape
    m = np.asarray(W.es.ret[a:r + 1], float)
    R = np.asarray(W.Rd[a:r + 1], float)[:, cols2d]                              # (126, D, n)
    fin = np.isfinite(R)
    cnt = fin.sum(axis=2)
    bsk = np.where(cnt > 0, np.where(fin, R, 0.0).sum(axis=2) / np.maximum(cnt, 1), np.nan)     # (126, D)
    ok = np.isfinite(bsk) & np.isfinite(m)[:, None]
    k = ok.sum(axis=0)
    mm, bb = np.where(ok, m[:, None], 0.0), np.where(ok, bsk, 0.0)
    kk = np.maximum(k, 1)
    sx, sy = mm.sum(axis=0), bb.sum(axis=0)
    var = (mm * mm).sum(axis=0) - sx * sx / kk
    cov = (mm * bb).sum(axis=0) - sx * sy / kk
    good = (k >= SPEC["beta_min"]) & (var > 1e-12 * np.maximum((mm * mm).sum(axis=0), 1e-300))
    with np.errstate(invalid="ignore", divide="ignore"):
        beta = np.where(good, cov / var, np.nan)
    return beta, k.astype(np.int64)


def basket_beta(W, r, cols):
    """the hedge ratio of ONE basket (cell E's NEW names at the rank close r) -> (beta, pairs); basket_beta_many's D = 1 case"""
    b, k = basket_beta_many(W, r, np.asarray(cols, np.int64)[None, :])
    return float(b[0]), int(k[0])


def basket_pairs(W, r, cols):
    """COUNTS ONLY (the dryload): the basket-ES pairs of the hedge's window - sessions on which at least one name has a return and ES has one - read from which returns EXIST, never from their values"""
    a = r - SPEC["beta_win"] + 1
    fin = np.isfinite(np.asarray(W.Rd[a:r + 1], float)[:, np.asarray(cols, np.int64)]).any(axis=1)
    return int((fin & np.isfinite(np.asarray(W.es.ret[a:r + 1], float))).sum())


# ------------------------------------------------------------------ one rebalance: who is NEW, who is SEASONED, the pool, the hygiene, the floor, the hedge ratio and the matches
def tally_pre(cnt, prefix, reasons, first):
    """r15's tally with a prefix for the counter keys: every name is counted once at its FIRST reason (or in the pool)"""
    for q, (label, _) in enumerate(reasons):
        cnt[prefix + label] += int((first == q).sum())
    cnt[prefix + "pool"] += int((first == -1).sum())


POST_MODES = ("remove", "naive", "close")                                       # ni_one's in-hold readings: 'remove' the registered (look-ahead), 'naive' [O3], 'close' [HYG-S1] (r17_resmom's 'keep' is not run by this family)


def ni_one(W, ctx, r, f, x, post_mode, units=True, win=None, incl=(False, False)):
    """one rebalance: the universe at the fill session f (sessions < f only), every name's age at the rank close r, who is NEW and who is SEASONED, every removal in order, the pool, the floor, cell E's hedge ratio and cell M's matches, the position paths -> (rec, counts).
    NEW (window `win`, default 126 .. 504 sessions): a universe name with an ACCEPTED dated listing ([N4]) r - L sessions old, which is NOT a spin-off's new symbol on the calendar (dated on / before r) and has NO name change on the calendar (the old or the new symbol, dated in the 24 calendar months
    r-24m .. r). SEASONED: present at the first session, or listed MORE than 36 calendar months before r (an accepted listing), with no name change in the 24 months, >= 230 own returns and >= 230 ES pairs in the 252 sessions r-251 .. r (RESMOM's history rule: NEW names are exempt, the prereg) -
    and, like every name that can be traded, the same removals as RESMOM's pool: no open at the fill session, a hygiene flag [T2] in r-25 .. r (all four reasons) or in r-125 .. r-26 (gap scan / TBIS / jump: a fake return day inside the hedge's window), a hand-audit data event;
    hygiene INSIDE the hold (r+1 .. x) and a [D2] spin-off / stock-dividend ex-date in f < t <= x are the look-ahead removal: post_mode 'remove' = the registered reading, 'naive' = flagged names stay at their naive raw price path,
    'close' = [HYG-S1], MANAGER's hygiene edit S1 (#127, 2026-10-07; r17_resmom's post_mode 'close'): NO in-hold event removes a name - the NEW and SEASONED sets are the look-ahead reading's, every flagged name stays on the split-safe path (a registered or calendar split rides the split-adjusted series) - and
    a [D2] spin-off / stock-dividend ex-date e in f < e <= x CLOSES the position at the official close of the session before it, e-1 (rec.close = that row per pool name, -1 = held to the exit; M17.rm_units cuts the path, pnl1 / M17.l1_pnl_x books the exit there; the same for a matched SEASONED long and for
    a drawn one). CHOICE: cell E's ES hedge is the basket's, sized at the rank from the names known then (beta x the short notional) and run to the exit session, so a closed short's hedge share is NOT cut - S1 closes the stock position; the closed NEW shorts are counted. Counted by NEW / SEASONED:
    new_ / seas_ kept_<reason>, kept_flagged, kept_calendar_split (when the calendar's splits are on the grid), closed_spin. A name that failed [N4] (or is unverifiable) is neither.
    The pool is the NEW names first, then every eligible SEASONED name (the match's candidates and the null's draws). A rebalance trades only with >= 10 NEW names [N7] (SPEC floor, counted after every removal; [N6]'s 20 is the REPORTED reading beside it); then rec.tE (E also needs a defined hedge ratio) and rec.tM (M needs a match) say which cells trade it.
    incl = (spincos kept, name changes kept) in NEW (the REPORTED would-have-been-included rows); win = another age window ([N3] 84 .. 168); rec.kind = 1 spinco, 2 name change, 3 both for the NEW names that are only there because of incl"""
    if post_mode not in POST_MODES:
        raise ValueError(f"post_mode {post_mode!r}: one of {POST_MODES}")
    s = SPEC
    lo_n, hi_n = (s["new_lo"], s["new_hi"]) if win is None else win
    uni = np.flatnonzero(W.U[f])
    rec = SimpleNamespace(r=r, f=f, x=x, nu=len(uni), traded=False, tE=False, tM=False, n_new=0, n_seas=0, new=ZI, seas=ZI, pool=ZI, naive=ZB, kind=ZI, age=ZI, cohort=ZI, lrow=ZI, dv=ZF, match=ZI, beta=float("nan"), bpairs=0, newage=0, close=ZI)
    cnt = Counter()
    cnt["rebalances"] += 1
    cnt["universe"] += len(uni)
    if not len(uni):
        cnt["empty"] += 1
        return rec, cnt
    d_r = W.days[r]
    a24 = int(W.days.searchsorted(d_r - pd.DateOffset(months=s["nc_months"]), side="left"))
    b36 = int(W.days.searchsorted(d_r - pd.DateOffset(months=s["seas_months"]), side="left"))
    lrow, st = ctx.L[uni], ctx.st[uni]
    age = r - lrow
    dated = st == ST_OK
    new_age = dated & (age >= lo_n) & (age <= hi_n)
    seas_age = (st == ST_START) | (dated & (lrow < b36))
    spin = ctx.spin_row[uni] <= r
    nchg = (ctx.nccs[r + 1, uni] - ctx.nccs[a24, uni]) > 0
    cnt["n4_failed_names"] += int((st == ST_FAIL).sum())
    cnt["n4_unverifiable_names"] += int((st == ST_LATE).sum())
    m_fill = np.isfinite(W.Ao[f, uni])                                          # CHOICE: a name with no open (or no factor) at the fill session cannot be filled: not eligible, counted
    lo_pre = r - s["pre"]
    pre = W.hyg(lo_pre, r, uni)                                                 # all four reasons, sessions r-25 .. r
    old = W.hyg(r - s["old"], lo_pre - 1, uni)[1:]                              # gap, tbis, jump on sessions r-125 .. r-26
    post = W.hyg(r + 1, x, uni)                                                 # all four, inside the hold: the fill session through the exit session
    post_sp = M17.spn_hit(W, f + 1, x, uni)                                     # [D2] a spin-off / stock-dividend ex-date in f < t <= x: a data event like a hygiene flag inside the hold
    post_cs = M17.csplit_hit(W, f + 1, x, uni) if post_mode == "close" and getattr(W, "cscs", None) is not None else np.zeros(len(uni), bool)     # [HYG-S1] an announced (calendar) split ex-date in f < t <= x: counted, never a removal
    post_any = post.any(axis=0) | post_sp
    aud = W.aud1[f, uni]
    W.aud_hit.update((M17.AUD, f, int(c)) for c in uni[aud & (new_age | seas_age)])
    cnt["new_age"] += int(new_age.sum())
    cnt["seasoned_age"] += int(seas_age.sum())
    # ---- NEW: the first reason that removes each name of the age window
    sn = np.flatnonzero(new_age)
    rn = [("spinco", spin[sn] & (not incl[0])), ("name_change", nchg[sn] & (not incl[1])), ("no_fill", ~m_fill[sn])] + [(f"pre_{h}", pre[q][sn]) for q, h in enumerate(HYG)] + [(f"old_{h}", old[q][sn]) for q, h in enumerate(HYG[1:])] + [("audit", aud[sn])]
    if post_mode == "remove":
        rn += [(f"post_{h}", post[q][sn]) for q, h in enumerate(HYG)] + [("post_spin", post_sp[sn])]
    fn = D15.attribute(rn, len(sn))
    tally_pre(cnt, "new_", rn, fn)
    cnt["new_spinco_any"] += int(spin[sn].sum())                                # counted whatever else removes them: the exclusions the prereg counts
    cnt["new_name_change_any"] += int(nchg[sn].sum())
    keep_n = fn < 0
    # ---- SEASONED
    ss = np.flatnonzero(seas_age)
    a = r - s["hold_win"] + 1
    Rw = np.asarray(W.Rd[a:r + 1], float)[:, uni[ss]]
    fin = np.isfinite(Rw)
    n_ret, n_pair = fin.sum(axis=0), (fin & ctx.es_ok[a:r + 1, None]).sum(axis=0)
    short_hist = n_ret < s["min_n"]
    no_es = ~short_hist & (n_pair < s["min_n"])
    rs = [("name_change", nchg[ss]), ("short_history", short_hist), ("no_es_pairs", no_es), ("no_fill", ~m_fill[ss])] + [(f"pre_{h}", pre[q][ss]) for q, h in enumerate(HYG)] + [(f"old_{h}", old[q][ss]) for q, h in enumerate(HYG[1:])] + [("audit", aud[ss])]
    if post_mode == "remove":
        rs += [(f"post_{h}", post[q][ss]) for q, h in enumerate(HYG)] + [("post_spin", post_sp[ss])]
    fs = D15.attribute(rs, len(ss))
    tally_pre(cnt, "seas_", rs, fs)
    keep_s = fs < 0
    new_cols, seas_cols = uni[sn][keep_n], uni[ss][keep_s]
    pool = np.concatenate([new_cols, seas_cols])
    naive = np.concatenate([post_any[sn][keep_n], post_any[ss][keep_s]]) if post_mode == "naive" else np.zeros(len(pool), bool)
    if post_mode == "naive":
        cnt["new_kept_naive"] += int((post_any[sn][keep_n]).sum())
        cnt["seas_kept_naive"] += int((post_any[ss][keep_s]).sum())
    if post_mode == "close":                                                    # [HYG-S1] the pool names with an in-hold event that STAY: flagged ones and the calendar's splits on the split-safe path, a [D2] ex-date closes the position at the close before it
        for pf, sel, keep in (("new_", sn, keep_n), ("seas_", ss, keep_s)):
            for q, h in enumerate(HYG):
                cnt[f"{pf}kept_{h}"] += int(post[q][sel][keep].sum())
            cnt[f"{pf}kept_flagged"] += int(post.any(axis=0)[sel][keep].sum())
            cnt[f"{pf}kept_calendar_split"] += int(post_cs[sel][keep].sum())
            cnt[f"{pf}closed_spin"] += int(post_sp[sel][keep].sum())
    kind = (spin[sn][keep_n].astype(np.int64) * 1 + nchg[sn][keep_n].astype(np.int64) * 2)
    n_new = len(new_cols)
    yrs = np.asarray(W.days.year)
    rec.new, rec.seas, rec.pool, rec.naive, rec.kind = new_cols, seas_cols, pool, naive, kind
    rec.close = np.full(len(pool), -1, np.int64)                                 # [HYG-S1] the row each pool name closes on: the session before its first [D2] ex-date in f < e <= x (-1 = held to the exit session)
    if post_mode == "close" and x > f and len(pool):
        sp_h = W.SPN[f + 1:x + 1][:, pool]
        rec.close = np.where(sp_h.any(axis=0), f + sp_h.argmax(axis=0), -1).astype(np.int64)
    rec.n_new, rec.n_seas, rec.newage = n_new, len(seas_cols), int(len(sn))
    rec.lrow = ctx.L[new_cols]
    rec.age = r - rec.lrow
    rec.cohort = yrs[np.maximum(rec.lrow, 0)] if n_new else ZI
    cnt["new_names"] += n_new
    cnt["seas_names"] += len(seas_cols)
    if n_new < s["floor"]:                                                      # [N7] a month with fewer than 10 NEW names (after every removal) trades nothing in either cell
        cnt["below_floor"] += 1
        return rec, cnt
    rec.traded = True
    if n_new > len(seas_cols):
        cnt["fewer_seasoned_than_new"] += 1
    if ctx.counts_only:                                                         # (dryload: counts only - no hedge ratio, no match, no path, no P&L)
        rec.bpairs = basket_pairs(W, r, new_cols)
        rec.tE, rec.tM = rec.bpairs >= s["beta_min"], len(seas_cols) >= 1
        cnt["no_beta_pairs"] += int(not rec.tE)
        return rec, cnt
    rec.beta, rec.bpairs = basket_beta(W, r, new_cols)
    rec.tE = bool(np.isfinite(rec.beta))
    if not rec.tE:
        cnt["no_beta"] += 1
    rec.dv = dv20(W, r, pool)
    m = match_nearest(rec.dv[:n_new], rec.dv[n_new:], new_cols, seas_cols)
    rec.match = np.where(m >= 0, n_new + m, -1)
    rec.tM = bool((rec.match >= 0).any())
    cnt["unmatched_new"] += int((rec.match < 0).sum())
    if units:                                                                   # (r17's units: the split-safe path of every pool name + the cash dividends a long receives and a short pays)
        rec.U = M17.rm_units(W, f, x, pool, naive, rec.close)
    return rec, cnt


def ni_build(W, ctx, lo, hi, post_mode="remove", units=True, win=None, incl=(False, False), drop=None):
    """every rebalance whose position EXITS inside [lo, hi] (a position belongs to the stretch its exit session falls in, as the house stretches are written; a mark before the stretch's first row falls outside its series; a position whose exit is past the stage's data is unresolved: out of the cell
    AND the null, counted) with a 252-session history (r >= 251; the earlier ranks are counted as warm-up) -> Leg(recs, cnt by fill year). drop = rank sessions (dates) left out of the leg - out of the cell AND the null, counted as dropped"""
    r_all, f_all, x_all = M17.rm_schedule(W.days)
    drop_rows = {int(i) for i in W.days.get_indexer(pd.DatetimeIndex(drop)) if i >= 0} if drop is not None and len(drop) else set()
    recs, cnt = [], defaultdict(Counter)
    for r, f, x in zip(r_all.tolist(), f_all.tolist(), x_all.tolist()):
        y = int(W.days[f].year)
        if x < 0:
            cnt[y]["unresolved"] += 1
            continue
        if not (lo <= W.days[x] <= hi):
            continue
        if r < SPEC["hold_win"] - 1:
            cnt[y]["warmup"] += 1
            continue
        if r in drop_rows:
            cnt[y]["dropped"] += 1
            continue
        rec, c = ni_one(W, ctx, r, f, x, post_mode, units, win, incl)
        recs.append(rec)
        cnt[y].update(c)
    return SimpleNamespace(kind="NI", recs=recs, cnt=cnt, win=win, incl=incl)


# ------------------------------------------------------------------ the engine: the cells' daily P&L from r15's split-safe unit paths (+ r17's dividends) and the ES hedge
def cfg_of(bps=COST_BPS, borrow=BORROW, short0=False):
    """r15's l1_cfg at this family's size: `bps` a side on the stocks and a FLAT borrow rate on every short day [N1] (3% a year base; the stress rows pay 10% / 25% on EVERY short day: no k_t gate here). short0 = r17's [R2] reading of a short in a name that stops printing (valued at zero: REPORTED)"""
    c = D15.l1_cfg(bps=bps, borrow=(borrow, None))
    if short0:
        c["short0"] = True
    return c


def pnl1(U, idx, side, cfg):
    """per $1 of ENTRY notional, the daily P&L (n, H) of the pool positions `idx` (side +1 long / -1 short) over rows f .. x: r15's l1_pnl (gross marks incl. r17's dividends, bps of the notional at the fill and of the exit value at the exit, the shorts' borrow on the prior mark) through r17's
    l1_pnl_x: [R2] cfg['short0'] and [HYG-S1] the exit column of a position closed before a spin-off / stock-dividend ex-date (U.xc: its exit cost and its -100% / short-at-zero readings move to the close's row) - for every path without one it IS r15's l1_pnl"""
    return M17.l1_pnl_x(U, idx, side, cfg)


def rec_legs(W, rec, cell, cfg, es_bps=ES_BPS):
    """one traded rebalance of a cell in $ per position: (idx (n,) the NEW names' pool indices that trade, S (n, H) the SHORT side, O (n, H) the other side - E: the position's equal share of the ES hedge (beta x $4,000 of ES notional per short, the whole hedge = beta x the short notional), M: the matched
    SEASONED long) over rows f .. x"""
    slot = SPEC["slot"]
    if cell == "E":
        idx = np.arange(rec.n_new)
        S_ = slot * pnl1(rec.U, idx, -1, cfg)
        O = np.tile(rec.beta * slot * es_leg(W, rec.f, rec.x, es_bps), (len(idx), 1))
        return idx, S_, O
    idx = np.flatnonzero(rec.match >= 0)
    return idx, slot * pnl1(rec.U, idx, -1, cfg), slot * pnl1(rec.U, rec.match[idx], +1, cfg)


def traded(rec, cell):
    return bool(rec.tE if cell == "E" else rec.tM)


def cell_run(W, L, cell, cfg, side=0, es_bps=ES_BPS):
    """a cell's run: its daily P&L on the stock sessions (T,), the NEW shorts held per row, the number of name-months and traded rebalances, and the table of the stretch's name-months (pnl = the position's short side + its other side; the short and the other side apart; the NEW name's column, the matched
    name's column or -1). side -1 = the SHORT side alone, +1 = the other side alone (E: the ES hedge, M: the matched longs), 0 = the cell. No compounding: $4,000 a name, fractional shares"""
    T = W.T
    x, cnt, n_pos, n_units, tabs = np.zeros(T), np.zeros(T), 0, 0, []
    for ri, rec in enumerate(L.recs):
        if not traded(rec, cell):
            continue
        idx, S_, O = rec_legs(W, rec, cell, cfg, es_bps)
        if not len(idx):
            continue
        tot = (S_.sum(axis=0) if side <= 0 else 0.0) + (O.sum(axis=0) if side >= 0 else 0.0)
        x[rec.f:rec.x + 1] += tot
        cnt[rec.f:rec.x + 1] += len(idx)
        n_pos, n_units = n_pos + len(idx), n_units + 1
        sp, op = S_.sum(axis=1) * (side <= 0), O.sum(axis=1) * (side >= 0)               # (a side that is not in the run is zero in its table too: pnl = short + other)
        tabs.append((np.full(len(idx), ri), rec.new[idx], np.where(rec.match[idx] >= 0, rec.pool[np.maximum(rec.match[idx], 0)], -1) if cell == "M" else np.full(len(idx), -1), sp + op, sp, op, idx))
    cat = lambda q, dt=float: (np.concatenate([t[q] for t in tabs]) if tabs else np.zeros(0, dt))
    pos = SimpleNamespace(rec=cat(0, np.int64), col=cat(1, np.int64), mcol=cat(2, np.int64), pnl=cat(3), short=cat(4), other=cat(5), ix=cat(6, np.int64))
    return SimpleNamespace(x=x, cnt=cnt, n_pos=n_pos, n_units=n_units, pos=pos)


def usd_per_year(net, years):
    """[N10] dollars a year = net / years - the house's years (r11_risk.stats: the last date minus the first, / 365.25, of the stretch); NaN without a positive span"""
    try:
        net, years = float(net), float(years)
    except (TypeError, ValueError):
        return float("nan")
    return net / years if math.isfinite(net) and math.isfinite(years) and years > 0 else float("nan")


def stretch_years(B, lo, hi):
    """the years of the stretch [lo, hi] on #463's index by r11_risk.stats's own convention: (the last row's date - the first row's) / 365.25; NaN under 2 rows"""
    k = np.flatnonzero(B.mask(lo, hi))
    return float((B.index[k[-1]] - B.index[k[0]]).days / 365.25) if len(k) >= 2 else float("nan")


def stat_of(B, rows, run, lo, hi):
    """r15's cell statistics on one stretch [lo, hi] of a cell's daily series (the eight July-June years, the best 1% of days and of name-months, net without Feb 15 - Apr 30 2020) + net without calendar 2022 and the 2020-21 / 2022 nets + [N10] the dollars a year (net / years) -> (stats, the series on #463's index, the positions held per row)"""
    xB, cB = D15.to_B(run.x, rows, B.n), D15.to_B(run.cnt, rows, B.n)
    st = D15.cell_stats(B, xB, cB, lo, hi, run, years=YEARS)
    k = B.mask(lo, hi)
    ds, xs = B.index[k], np.asarray(xB, float)[k]
    in22, inb = (ds >= X2022[0]) & (ds <= X2022[1]), (ds >= BOOM[0]) & (ds <= BOOM[1])
    st.update({"net_ex2022": float(xs[~in22].sum()), "net_2022": float(xs[in22].sum()), "net_2020_21": float(xs[inb].sum()), "usd_per_year": usd_per_year(st["net"], st["years"])})
    return st, xB, cB


def sub_run(W, L, run, lo, hi):
    """the same cell-run with the position table cut to the name-months that EXIT in [lo, hi] (a sub-period: positions are counted by exit date, as the stretches are); the daily series keeps every row - the statistics cut it by date. CHOICE: the prereg says only that every cell is also reported for the two halves:
    the position counts / position-level numbers go by EXIT date, the daily series (ROC, drawdown, years) by SESSION date, so a position that straddles the boundary is split in the second half and whole in the first"""
    dx = np.asarray(W.days).astype("datetime64[ns]")[np.array([L.recs[int(i)].x for i in run.pos.rec], np.int64)] if len(run.pos.rec) else np.zeros(0, "datetime64[ns]")
    m = (dx >= np.datetime64(lo)) & (dx <= np.datetime64(hi))
    pos = SimpleNamespace(pnl=run.pos.pnl[m])
    return SimpleNamespace(x=run.x, cnt=run.cnt, n_pos=int(m.sum()), n_units=len(set(run.pos.rec[m].tolist())), pos=pos)


def realised_beta(B, rows, W, xB, cB, lo, hi, lags=5):
    """[N2] the realised beta of a cell: the OLS slope (an intercept and a slope, Newey-West t) of its daily $ P&L PER $ OF SHORT NOTIONAL (the day's P&L / $4,000 x the NEW shorts held that day) on ES's daily return, over the stretch's sessions on which it holds a position (CHOICE: the days it holds
    nothing say nothing about its beta; the notional is the day's, so a month of 60 names and one of 25 weigh a day each) -> {beta, t_nw, n}"""
    esr = np.full(B.n, np.nan)
    esr[rows] = W.es.ret
    k = B.mask(lo, hi) & (np.asarray(cB, float) > 0) & np.isfinite(esr)
    n = int(k.sum())
    y = np.asarray(xB, float)[k] / (SPEC["slot"] * np.asarray(cB, float)[k])
    m = esr[k]
    if n < lags + 3 or not np.ptp(m) > 0:
        return {"beta": float("nan"), "t_nw": float("nan"), "n": n}
    with np.errstate(all="ignore"):
        b, t = R11.ols_nw(y, np.column_stack([np.ones(n), m]), lags)
    return {"beta": float(b[1]), "t_nw": float(t[1]), "n": n}


def beta_gate(beta):
    """[N2] a cell with |realised beta| > 0.20 has its drawdown-day profile REPORTED but never credited (no A2 pass, no gate, no line); a NaN beta is not credited -> {beta, limit, credited}"""
    b = float(beta)
    return {"beta": b, "limit": RULES["beta_abs"], "credited": bool(math.isfinite(b) and abs(b) <= RULES["beta_abs"])}


# ------------------------------------------------------------------ the family-aware null: at every rebalance the NEW set is replaced by the same number of SEASONED names drawn at random, M's longs re-matched, E's hedge re-estimated on the drawn basket
def null_rec(W, rec, draw, cfg, es_bps=ES_BPS):
    """one rebalance of the null for D draws at once. draw (D, n) = positions in rec.seas (the eligible SEASONED names, 0 .. n_seas - 1) of the pseudo-NEW names of each draw, n = the real NEW count. Per draw: the pseudo-NEW names are SHORTED at $4,000 each (the same costs, borrow, dividends, fills); cell E's ES hedge
    ratio is estimated again on the DRAWN basket by the same rule (the OLS of its equal-weight return on ES over the 126 sessions; a draw whose ratio is undefined trades nothing in E this month, as a real month would); cell M's longs are matched again to the drawn names by the same greedy rule, among the
    SEASONED names that were not drawn (a drawn name is a short, never a long). -> (E (D, H), M (D, H)) the draws' daily $ P&L over rows f .. x (a cell the real run did not trade this month is zero)"""
    slot = SPEC["slot"]
    D, n = draw.shape
    H = rec.x - rec.f + 1
    seas_ix = rec.n_new + np.arange(rec.n_seas)
    PS = slot * pnl1(rec.U, seas_ix, -1, cfg)                                   # (n_seas, H) one short per seasoned name
    PL = slot * pnl1(rec.U, seas_ix, +1, cfg)
    E = np.zeros((D, H))
    M = np.zeros((D, H))
    if rec.tE:
        beta, _k = basket_beta_many(W, rec.r, rec.seas[draw])
        E = np.where(np.isfinite(beta)[:, None], PS[draw].sum(axis=1) + np.where(np.isfinite(beta), beta, 0.0)[:, None] * n * slot * es_leg(W, rec.f, rec.x, es_bps)[None, :], 0.0)
    if rec.tM:
        dvs = rec.dv[rec.n_new:]
        ns = rec.n_seas
        for d in range(D):
            rest = np.setdiff1d(np.arange(ns), draw[d], assume_unique=False)
            m = match_nearest(dvs[draw[d]], dvs[rest], rec.seas[draw[d]], rec.seas[rest])
            ok = m >= 0
            M[d] = PS[draw[d][ok]].sum(axis=0) + PL[rest[m[ok]]].sum(axis=0)
    return E, M


def ni_null(W, L, nreps, vcode=0, cfg=None, es_bps=ES_BPS):
    """the registered null: nreps draws, one random stream per reading (seed 20261005, vcode); at every rebalance a cell traded, the NEW set is replaced by the same number of SEASONED universe names drawn uniformly without replacement (the same hygiene, floor, sizing, fills, costs, borrow); both cells read the SAME
    draw (the real cells share one NEW set). -> {cell: (nreps, T) P&L by stock session}"""
    cfg = cfg or cfg_of()
    rng = np.random.default_rng([SEED, vcode])
    acc = {c: np.zeros((nreps, W.T)) for c in CELLS}
    for rec in L_recs(L):
        if not (rec.tE or rec.tM) or rec.n_seas < rec.n_new or rec.n_new == 0:
            continue
        draw = D15.draw_order(rng, nreps, rec.n_seas, rec.n_new)
        E, M = null_rec(W, rec, draw, cfg, es_bps)
        acc["E"][:, rec.f:rec.x + 1] += E
        acc["M"][:, rec.f:rec.x + 1] += M
    return acc


def L_recs(L):
    return [r for r in L.recs if r.traded]


def null_summary(per_cell, per_cell_do=None):
    """per_cell {cell: ROC @ $30k of every draw} -> the statistic = the MAX over the 2 cells per draw -> p5 / p50 / p95 (and each cell's own, for the report). per_cell_do {cell: the DO of every draw against the REFERENCE book's drawdown days [X1]} -> the same for the DO ('do_ref_max' = the MAX over the 2 cells per draw;
    MANAGER #70's gate basis for the cell's null)"""
    roc = np.fmax.reduce(np.vstack([per_cell[c] for c in CELLS]), axis=0)
    mk = lambda a: {"p5": D15.pctl(a, 5), "p50": D15.pctl(a, 50), "p95": D15.pctl(a, 95), "finite": int(np.isfinite(a).sum())}
    out = {"draws": int(len(roc)), "seed": SEED, "roc_max": mk(roc), "by_cell": {c: mk(per_cell[c]) for c in CELLS}}
    if per_cell_do is not None:
        do = np.fmax.reduce(np.vstack([per_cell_do[c] for c in CELLS]), axis=0)
        out.update({"do_ref_max": mk(do), "do_ref_by_cell": {c: mk(per_cell_do[c]) for c in CELLS}})
    return out


# ------------------------------------------------------------------ Stage A's checks (a) - (e), the book add as an INCREMENTAL report over the reference, the hand audit (f)
def judge_cell(st, net10, net_b10, nul):
    """(a) >= 40 traded rebalances [N8]; (b) WF ROC @ $30k >= 15 and net > 0 at 5 AND at 10 bps a side AND at the 10%/yr borrow stress; (c) WF ROC above the null's 95th percentile (the max over the 2 cells); (d) positive in >= 5 of the 8 July-June WF years (2017-18 is short and counts), net > 0 without
    Feb 15 - Apr 30 2020 AND net > 0 without calendar 2022; (e) profitable without its best 1% of days AND without its best 1% of name-months. (f), the hand audit, is separate: audit_complete / the lead's flag. A NaN fails every comparison it enters. [N2]'s beta rule is NOT a Stage A bar: it decides the
    credit of the drawdown-day profile (beta_gate)"""
    R = RULES
    chk = {f"rebalances>={R['reb']}": st["n_units"] >= R["reb"], f"ROC>={R['roc']:g}": st["roc"] >= R["roc"], "net>0 at 5 bps": (st["net"] > 0) if R["net_pos"] else True,
           "net>0 at 10 bps": (net10 > 0) if R["stress"] else True, "net>0 at 10%/yr borrow": (net_b10 > 0) if R["borrow_stress"] else True, "ROC>null p95": (st["roc"] > nul["roc_max"]["p95"]) if R["null"] else True,
           f"positive in >={R['years']} of 8 July-June years": st["years_pos"] >= R["years"], "net>0 without Feb 15 - Apr 30 2020": (st["net_ex2020"] > 0) if R["ex2020"] else True,
           "net>0 without calendar 2022": (st["net_ex2022"] > 0) if R["ex2022"] else True, "profitable without its best 1% of days": (st["net_ex_best_days"] > 0) if R["exbest"] else True,
           "profitable without its best 1% of name-months": (st["net_ex_best_pos"] > 0) if R["exbest"] else True}
    return {k: bool(v) for k, v in chk.items()}


def a2_usd(a, years):
    """[N10] dollars a year (net / years of the stretch the numbers are on) beside every ROC @ $30k of an A2 record: the reference, the reference + c x the cell, at 0.5c and 2c, the plain #463 + c x the cell and its 0.5c / 2c rows - added in place wherever a block carries a net"""
    def put(d):
        if isinstance(d, dict) and "net" in d:
            d["usd_per_year"] = usd_per_year(d["net"], years)
    for d in (a, a.get("reference"), a.get("at_half_c"), a.get("at_double_c"), a.get("plain_463")):
        put(d)
    p = a.get("plain_463")
    if isinstance(p, dict):
        put(p.get("at_half_c"))
        put(p.get("at_double_c"))
    a["years"] = years
    return a


def a2_report(B, xB, ref, beta_ok):
    """STAGE A2 (WF) - a REPORT, never a pass route [X1]: the REFERENCE book (#463 + 0.264 x RES) + c x the cell against the reference, c by the registered volatility rule over 2018-02-01 .. 2020-01-31 (25% of #463's daily std / the cell's), the book at 0.5c and 2c beside it, the plain #463 + c x
    cell a reported row (r18_divrun's A2, pointed at this family's window); an incremental pass = the book's ROC @ $30k AND Sortino both strictly above the reference's AND [N2]'s beta rule (|realised beta| <= 0.20: a cell outside it can never pass). Also the same two books over the cell's own
    stretch 2018-02-01 .. 2025-06-29 (the reference alone against the reference + c x the cell): a reported row, the registered comparison is on the reference's registered WF"""
    with patched(DV, A2_WIN=A2_WIN, A2_TARGET=A2_TARGET, A2_REPORT=A2_REPORT):
        a = DV.a2_report(B, xB, ref)
    before = bool(a["incremental_pass"])
    a["incremental_pass_before_the_beta_rule"] = before
    a["beta_rule_ok"] = bool(beta_ok)
    a["incremental_pass"] = a["book_shadow_line"] = bool(before and beta_ok)
    a2_usd(a, stretch_years(B, WF0, PRE_END))                                                  # [N10] the registered comparison is on the reference's WF 2016-07-01 .. 2025-06-29
    c = a["c"]
    if np.isfinite(c) and c > 0:
        k = B.mask(WFN, PRE_END)
        yo, nan_ = stretch_years(B, WFN, PRE_END), float("nan")
        alone = R11.stats(np.asarray(ref.raw, float)[k], B.index[k]) or {}
        wc = DV.ref_at(B, ref, xB, c, WFN, PRE_END)
        a["own_stretch"] = {"window": [f"{WFN:%Y-%m-%d}", f"{PRE_END:%Y-%m-%d}"], "years": yo, "reference_alone": {"roc": alone.get("roc", nan_), "sortino": alone.get("sort", nan_), "max_dd": alone.get("max_dd", nan_), "net": alone.get("net", nan_), "usd_per_year": usd_per_year(alone.get("net", nan_), yo)},
                            "with_c": {**wc, "usd_per_year": usd_per_year(wc["net"], yo)}}
    return a


def episodes_in_stretch(ref, xB, lo=None, hi=None):
    """[N10] the reference line's drawdown episodes INSIDE a cell's stretch [lo, hi] (default WFN .. PRE_END): MDL r1's qualifying episodes of the reference's WF (ref.S.qual: at least 1/3 as deep as the deepest; 45 on the real WF), each cut to its DD days (the day after the peak .. the trough) that fall in the stretch -
    an episode that starts before it is cut to the part inside it, one wholly before it is not listed - with the reference's P&L over those days, the cell's, and whether the cell HELPS (its P&L over them is positive: the reference loses over every one of them)
    -> {episodes_on_wf, inside, cut, helped, reference_pnl, cell_pnl, rows: [{peak, first_dd_day (inside), trough, depth, dd_days, dd_days_inside, cut, book_pnl, cell_pnl, helps}]}"""
    lo, hi = WFN if lo is None else lo, PRE_END if hi is None else hi
    S_ = ref.S
    x = np.asarray(xB, float)[S_.rows]
    d = S_.dates
    inside = np.asarray((d >= lo) & (d <= hi))
    rows_ = []
    for e in S_.qual:
        i0, it = int(e["i0"]), int(e["it"])
        idx = np.arange(i0, it + 1)
        idx = idx[inside[idx]]
        if not len(idx):
            continue
        cp, bp = float(x[idx].sum()), float(np.asarray(S_.x, float)[idx].sum())
        rows_.append({"peak": e["peak"], "first_dd_day": f"{d[idx[0]]:%Y-%m-%d}", "trough": e["trough"], "depth": float(e["depth"]), "dd_days": int(it - i0 + 1), "dd_days_inside": int(len(idx)), "cut": bool(idx[0] > i0), "book_pnl": bp, "cell_pnl": cp, "helps": bool(cp > 0)})
    return {"episodes_on_wf": int(len(S_.qual)), "inside": len(rows_), "cut": int(sum(r_["cut"] for r_ in rows_)), "helped": int(sum(r_["helps"] for r_ in rows_)), "reference_pnl": float(sum(r_["book_pnl"] for r_ in rows_)), "cell_pnl": float(sum(r_["cell_pnl"] for r_ in rows_)), "rows": rows_}


def restrict_stretch(S_full, raw, index, lo, hi):
    """MDL r1's Stretch of the same book on [lo, hi] whose DD-day mask is the full stretch's mask cut to [lo, hi]: the registered episodes (28 of #463's, 460 DD days) are kept - 'the map point uses the drawdown days from 2018-02 on' (every one of #463's qualifying DD days is in 2019 or later)"""
    keep = np.asarray(index[S_full.rows] >= lo)
    return M12.Stretch(raw, index, None, lo, hi, dd=S_full.dd[keep])


# ------------------------------------------------------------------ one reading of Stage A: leg -> cells -> stress rows -> null -> checks -> A2 / the gate basis
def episode_gate(c, eps):
    """MANAGER #70's gate basis on the REFERENCE book's qualifying episodes: the cell's DO (its P&L over the reference's DD days / the reference's loss over them), and DO without the cell's BEST episode (CHOICE: the one episode where the cell earned most - the cell's P&L over the other episodes / the
    reference's loss over them; NaN without a loss) -> {episodes, best_episode, best_episode_pnl, DO_ex_best_episode}"""
    if not eps:
        return {"episodes": 0, "best_episode": None, "best_episode_pnl": float("nan"), "DO_ex_best_episode": float("nan")}
    j = int(np.argmax([e["cell_pnl"] for e in eps]))
    rest = [e for q, e in enumerate(eps) if q != j]
    loss = -sum(e["book_pnl"] for e in rest)
    do = sum(e["cell_pnl"] for e in rest) / loss if loss > 0 else float("nan")
    return {"episodes": len(eps), "best_episode": f"{eps[j]['first_dd_day']} .. {eps[j]['trough']}", "best_episode_pnl": float(eps[j]["cell_pnl"]), "DO_ex_best_episode": float(do)}


def evaluate(W, ctx, B, SN, ref, SRN, rows, post_mode, nreps, vcode=0, full=False, drop=None):
    """one reading of Stage A on the WF stretch (positions EXITED 2018-02-01 .. 2025-06-29). post_mode 'remove' = the REGISTERED reading (a hygiene flag inside the hold removes the position before the pool is formed), 'naive' = the look-ahead variant [O3] (those positions are kept at their naive raw P&L);
    both run the same code, so a flip between them is the data hygiene's doing. SN / SRN = the stretches the MAP uses: #463's and the REFERENCE's drawdown days from 2018-02 on (the cells' own WF), ref = the reference book [X1]. nreps > 0 draws the
    null (vcode picks its random stream); full = also the reports' rows (the cost curve, the sides apart, the halves, the [R2] row). drop = rank sessions left out of the leg (a reported row). -> (summary, objects: the leg, each cell's run and series)"""
    lo, hi = WFN, PRE_END
    L = ni_build(W, ctx, lo, hi, post_mode, drop=drop)
    cfg = cfg_of()
    runs, series, summ = {}, {}, {}
    for cell in CELLS:
        base = cell_run(W, L, cell, cfg)
        st, xB, cB = stat_of(B, rows, base, lo, hi)
        runs[cell], series[cell] = base, (xB, cB)
        bt = realised_beta(B, rows, W, xB, cB, lo, hi)
        gate = beta_gate(bt["beta"])
        c = {"base": st, "stress": {f"{b:g} bps": stat_of(B, rows, cell_run(W, L, cell, cfg_of(bps=b)), lo, hi)[0] for b in STRESS_BPS},
             "borrow": {f"{b:.0%}/yr": stat_of(B, rows, cell_run(W, L, cell, cfg_of(borrow=b)), lo, hi)[0] for b in BORROW_STRESS},
             "seat": D15.seat_measure(SN, xB), "seat_ref": D15.seat_measure(SRN, xB), "realised_beta": bt, "beta_gate": gate}
        c["A2"] = a2_report(B, xB, ref, gate["credited"])
        c["ref_episodes"] = D15.episodes_table(ref.S, xB)
        c["ref_episodes_in_stretch"] = episodes_in_stretch(ref, xB, lo, hi)                      # [N10] the same episodes cut to the cell's own stretch, with the count the cell helps in
        c["gate70"] = {"basis": "the REFERENCE book's drawdown days from 2018-02 on (MDL r1's episode rule)", "episodes": ref.structure["episodes"], "dd_days_from_2018_02": int(SRN.n_dd_days), "DO": c["seat_ref"]["DO"], "rho_dd": c["seat_ref"]["rho_dd"],
                       "credited": gate["credited"], **episode_gate(c, c["ref_episodes"])}
        if full:
            c["cost0"] = stat_of(B, rows, cell_run(W, L, cell, cfg_of(bps=0.0)), lo, hi)[0]
            c["sides"] = {nm: stat_of(B, rows, cell_run(W, L, cell, cfg, side=sd), lo, hi)[0] for nm, sd in (("short side only", -1), ("long / hedge side only", 1))}
            c["halves"] = {lab: stat_of(B, rows, sub_run(W, L, base, a, b), a, b)[0] for lab, a, b in HALVES}
            c["short0"] = {"cell": stat_of(B, rows, cell_run(W, L, cell, cfg_of(short0=True)), lo, hi)[0], "short_side": stat_of(B, rows, cell_run(W, L, cell, cfg_of(short0=True), side=-1), lo, hi)[0]}
            c["short_stopped"] = {"positions": int(sum(int(rec.U.st[:rec.n_new].sum()) for rec in L.recs if traded(rec, cell))), "short_positions": int(base.n_pos)}
        summ[cell] = c
    nul = None
    if nreps:
        acc = ni_null(W, L, nreps, vcode)
        pr = {cell: DV.null_stats(SN, SRN, acc[cell], rows, B.n) for cell in CELLS}
        nul = null_summary({c_: pr[c_][0] for c_ in CELLS}, {c_: pr[c_][1] for c_ in CELLS})
        for cell in CELLS:
            c = summ[cell]
            c["checks"] = judge_cell(c["base"], c["stress"]["10 bps"]["net"], c["borrow"]["10%/yr"]["net"], nul)
            c["PASS"] = bool(all(c["checks"].values()))
            p = nul["do_ref_max"]
            c["gate70"].update({"null_do_p5": p["p5"], "null_do_p50": p["p50"], "null_do_p95": p["p95"], "DO_above_null_p95": bool(c["seat_ref"]["DO"] > p["p95"]), "gate_basis_met": bool(c["gate70"]["credited"] and c["seat_ref"]["DO"] > p["p95"] and c["gate70"]["DO_ex_best_episode"] > 0)})
    return {"variant": post_mode, "cells": summ, "null": nul}, SimpleNamespace(legs=L, runs=runs, series=series)


def variant_rows(W, ctx, B, rows, drop=None, drop2=None):
    """the REPORTED rows that need another leg (none is a pass route): [N3] the same short / match / hedge on names 4 to 8 months after listing (84 .. 168 sessions; the registered floor: 'the same'), and the cells with the spinco / the name-change names INCLUDED in NEW (the P&L had they been included; the P&L of the
    included names' own name-months inside the cell), and - with `drop` - the registered cells without the ranks whose 24-month name-change window starts before the calendar does (drop2: before the calendar's FIRST name-change row: a calendar may start long before it has any). Each: the cell's WF numbers, the traded rebalances, the NEW names per month -> {name: {cell: stats, 'new_per_month': ..., ...}}"""
    cfg = cfg_of()
    specs = [("[N3] 4-8 months after listing (84 .. 168 sessions)", {"win": (SPEC["n3_lo"], SPEC["n3_hi"])}), ("spinco names included", {"incl": (True, False)}), ("name-change names included", {"incl": (False, True)}),
             ("spinco and name-change names included", {"incl": (True, True)})]
    if drop:
        specs.append(("without the ranks whose name-change window starts before the calendar", {"drop": tuple(drop)}))
    if drop2:
        specs.append(("without the ranks whose name-change window starts before the first name-change row on the calendar", {"drop": tuple(drop2)}))
    out = {}
    for name, kw in specs:
        L = ni_build(W, ctx, WFN, PRE_END, "remove", **kw)
        n = [rec.n_new for rec in L.recs]
        o = {"rebalances": len(L.recs), "below_floor": int(sum(not rec.traded for rec in L.recs)), "new_per_month": {"min": int(min(n)) if n else 0, "median": float(np.median(n)) if n else 0.0, "max": int(max(n)) if n else 0}}
        for cell in CELLS:
            run = cell_run(W, L, cell, cfg)
            st = stat_of(B, rows, run, WFN, PRE_END)[0]
            o[cell] = {k: st[k] for k in ("n_units", "n_pos", "net", "roc", "sortino", "max_dd", "years_pos", "net_ex2022")}
            if kw.get("incl"):
                kind = np.concatenate([L.recs[int(ri)].kind[ix][None] for ri, ix in zip(run.pos.rec, run.pos.ix)]).ravel() if run.pos.rec.size else np.zeros(0, np.int64)
                for code, lab in ((1, "spinco"), (2, "name_change"), (3, "both")):
                    m = kind == code
                    o[cell][f"included_{lab}_name_months"] = int(m.sum())
                    o[cell][f"included_{lab}_net"] = float(run.pos.pnl[m].sum())
        out[name] = o
        del L
    return out


# ------------------------------------------------------------------ the reports (never a pass route)
def age_table(W, L, cell, cfg, lo, es_bps=ES_BPS):
    """[X2] the path by months since listing: every mark of every name-month of the cell (a session's P&L on rows f .. x, the session's age = row - the listing row, month = age // 21 sessions) summed into one row per month, in $ - the short side, the other side (E: the ES hedge's share, M: the
    matched long) and the name-days. Marks before the stretch's first row (the first rebalance's January) are left out so the rows add up to the cell's WF net. -> {month: {days, short, other}} for every month with a mark"""
    mo = SPEC["month"]
    r0 = int(W.days.searchsorted(lo, side="left"))
    acc = defaultdict(lambda: {"days": 0, "short": 0.0, "other": 0.0})
    for rec in L.recs:
        if not traded(rec, cell):
            continue
        idx, S_, O = rec_legs(W, rec, cell, cfg, es_bps)
        if not len(idx):
            continue
        H = rec.x - rec.f + 1
        rowsH = rec.f + np.arange(H)
        age = rowsH[None, :] - rec.lrow[idx][:, None]
        m = (age // mo)
        keep = np.broadcast_to(rowsH >= r0, m.shape)
        for q in np.unique(m[keep]):
            sel = keep & (m == q)
            a = acc[int(q)]
            a["days"] += int(sel.sum())
            a["short"] += float(S_[sel].sum())
            a["other"] += float(O[sel].sum())
    return {q: dict(v) for q, v in sorted(acc.items())}


AGE_BUCKETS = (("<6 months", 0, 5), ("6-12 months", 6, 11), ("12-24 months", 12, 23), ("24+ months", 24, 10 ** 6))


def age_split(path):
    """the draft's REPORTED 'P&L by months since listing (6-12 vs 12-24)' from the one-row-a-month path: its rows summed into months 6 .. 11 (6-12 months) and 12 .. 23 (12-24 months), and the rest apart - under 6 months (only a window other than the registered one has any) and 24 months and later
    (the last sessions of the longest holds: a name 24 months old at the rank is older by the hold) -> {bucket: {days, short, other, net}}"""
    out = {}
    for lab, a, b in AGE_BUCKETS:
        rows = [v for q, v in path.items() if a <= q <= b]
        d, s_, o = sum(v["days"] for v in rows), sum(v["short"] for v in rows), sum(v["other"] for v in rows)
        out[lab] = {"days": int(d), "short": float(s_), "other": float(o), "net": float(s_ + o)}
    return out


def cohort_table(W, ctx, run):
    """[N5] the P&L of the cell's name-months (the short side + the other side; counted by exit date, as the stretch's statistics are) by the NEW name's LISTING-YEAR cohort 2016 .. 2024 (any other year apart): name-months, distinct names, net $, the short side's and the other side's $"""
    p = run.pos
    out = {}
    if not len(p.pnl):
        return out
    yr = np.asarray(W.days.year)[ctx.L[p.col]]
    for y in sorted(set(yr.tolist())):
        m = yr == y
        out[int(y)] = {"name_months": int(m.sum()), "names": int(len(set(p.col[m].tolist()))), "net": float(p.pnl[m].sum()), "short": float(p.short[m].sum()), "other": float(p.other[m].sum())}
    return out


def new_table(W, L):
    """NEW names per month: one row per rebalance (the rank date, the NEW names that survive every removal, the age-window names before the removals, the SEASONED candidates, traded / E / M), and by listing-year cohort (the survivors' counts)"""
    rows_ = []
    for rec in L.recs:
        co = Counter(rec.cohort.tolist())
        rows_.append({"rank": f"{W.days[rec.r]:%Y-%m-%d}", "new": int(rec.n_new), "age_window_names": int(rec.newage), "seasoned_candidates": int(rec.n_seas), "traded": bool(rec.traded), "E": bool(rec.tE), "M": bool(rec.tM),
                      "by_cohort": {int(y): int(n) for y, n in sorted(co.items())}, "hedge_ratio": float(rec.beta), "hedge_pairs": int(rec.bpairs)})
    return rows_


def top_gains(W, ctx, run, L, n=20):
    """the n largest name-month gains of a cell (the position's short side + its other side)"""
    p = run.pos
    o = np.argsort(-p.pnl, kind="stable")[:n]
    return [{"rank": q + 1, "symbol": str(W.syms[p.col[i]]), "match": (str(W.syms[p.mcol[i]]) if p.mcol[i] >= 0 else ""), "fill": f"{W.days[L.recs[int(p.rec[i])].f]:%Y-%m-%d}", "exit": f"{W.days[L.recs[int(p.rec[i])].x]:%Y-%m-%d}",
             "listed": f"{W.days[ctx.L[p.col[i]]]:%Y-%m-%d}", "age_at_rank": int(L.recs[int(p.rec[i])].r - ctx.L[p.col[i]]), "pnl": float(p.pnl[i]), "short": float(p.short[i]), "other": float(p.other[i])} for q, i in enumerate(o)]


def corr_with(xB, other, k):
    a, b = np.asarray(xB, float)[k], np.asarray(other, float)[k]
    ok = np.isfinite(a) & np.isfinite(b)
    with np.errstate(invalid="ignore", divide="ignore"):
        return float(np.corrcoef(a[ok], b[ok])[0, 1]) if ok.sum() > 2 and np.ptp(a[ok]) > 0 and np.ptp(b[ok]) > 0 else float("nan")


def ni_candidate_rows(W, ctx, L, cell, run, tbis_df, status, n=AUDIT_N):
    """(f) the n largest single-name contributors of a cell - CHOICE: the largest GAINS, P&L descending (a fake gain is what a pass would rest on; a fake loss only works against it); a contributor is a NEW name-month, its P&L = the short side + its other side (E: its share of the ES hedge, M: the matched long) -
    with what the hand audit needs to answer 'is it really a new listing?': symbol, date (the FILL session - the key newissue_audit.csv uses), exit, the matched long, the listing session and its [N4] count, the age at the rank, the cohort, the first bar's raw close / volume, the calendar's spin-off / name-change rows that
    name it, the split factor's ratio from the listing to the exit, the largest raw overnight move in the first 20 sessions and in the hold, TBIS's rows, the asset status, the hygiene reasons from 125 sessions before the rank through the exit"""
    p = run.pos
    if p is None or not len(p.pnl):
        return []
    sel = np.argsort(-np.asarray(p.pnl, float), kind="stable")[:n]
    tb = None if tbis_df is None or not len(tbis_df) else tbis_df
    ex = ctx.extra
    big = lambda g: float(g[np.argmax(np.abs(g - 1.0))]) if len(g) else float("nan")
    out = []
    for rank, i in enumerate(sel, 1):
        rec, col = L.recs[int(p.rec[i])], int(p.col[i])
        sym, Lr = str(W.syms[col]), int(ctx.L[col])
        f, x = rec.f, rec.x
        rg = W.Rg[Lr + 1:Lr + 21, col]
        rh = W.Rg[f:x + 1, col]
        ptb = [None, None, None]
        if tb is not None:
            m = tb[(tb["symbol"].astype(str) == sym) & (tb["day"] >= W.days[Lr]) & (tb["day"] <= W.days[x])]
            if len(m):
                ptb = [float(m["price_ratio"].iloc[0]), float(m["vol_ratio"].iloc[0]) if pd.notna(m["vol_ratio"].iloc[0]) else float("nan"), str(m["split_like"].iloc[0])]
        fl = W.hyg(max(rec.r - SPEC["old"], 0), x, np.array([col]))[:, 0]
        spin_rows = "" if ex is None else "; ".join(f"{pd.Timestamp(e):%Y-%m-%d} spin-off of {pa}" for e, pa in zip(ex.spin.loc[ex.spin["sym"] == sym, "ev"], ex.spin.loc[ex.spin["sym"] == sym, "parent"]))
        chg_rows = "" if ex is None else "; ".join(f"{pd.Timestamp(e):%Y-%m-%d} {o}>{nw}" for e, o, nw in zip(ex.chg.loc[(ex.chg["old"] == sym) | (ex.chg["new"] == sym), "ev"], ex.chg.loc[(ex.chg["old"] == sym) | (ex.chg["new"] == sym), "old"], ex.chg.loc[(ex.chg["old"] == sym) | (ex.chg["new"] == sym), "new"]))
        with np.errstate(invalid="ignore", divide="ignore"):
            fr = float(W.F[x, col] / W.F[Lr, col])
        out.append({"cell": cell, "rank": rank, "symbol": sym, "date": f"{W.days[f]:%Y-%m-%d}", "exit": f"{W.days[x]:%Y-%m-%d}", "rank_date": f"{W.days[rec.r]:%Y-%m-%d}", "match": (str(W.syms[p.mcol[i]]) if p.mcol[i] >= 0 else ""),
                    "pnl": float(p.pnl[i]), "short_pnl": float(p.short[i]), "other_pnl": float(p.other[i]), "listing_session": f"{W.days[Lr]:%Y-%m-%d}", "age_sessions_at_rank": int(rec.r - Lr), "months_since_listing_at_rank": float((rec.r - Lr) / SPEC["month"]),
                    "cohort": int(W.days[Lr].year), "n4_sessions_with_close_and_volume_of_the_next_20": int(ctx.li.n_after[col]), "first_bar_raw_close": float(W.Cl[Lr, col]), "first_bar_volume": float(W.Vv[Lr, col]),
                    "calendar_spin_off_rows": spin_rows, "calendar_name_change_rows": chg_rows, "factor_ratio_listing_to_exit": fr, "max_overnight_raw_ratio_first_20_sessions": big(rg[np.isfinite(rg)]), "max_overnight_raw_ratio_in_hold": big(rh[np.isfinite(rh)]),
                    "tbis_price_ratio": ptb[0], "tbis_vol_ratio": ptb[1], "tbis_split_like": ptb[2], "asset_status": status.get(sym, "unknown"), "flags_in_window": "+".join(h for h, v in zip(HYG, fl) if v),
                    "spin_or_stock_dividend_in_hold": bool(W.SPN[f + 1:x + 1, col].any()), "naive_raw_path": bool(rec.naive[int(p.ix[i])]) if len(rec.naive) > int(p.ix[i]) else False})
    return out


def reports(W, ctx, B, S12, ref, rows, obj, summ, tbis_df, status, legs_meta):
    """everything the prereg's REPORTED paragraphs list for the registered reading: per cell - the realised beta to ES in #463's drawdown days, the P&L inside every qualifying #463 drawdown, the map point, the correlation with #463's legs and with RES (RES's registered WF line read through r18's
    reference loader, never re-computed), the path by months since listing, the P&L by listing-year cohort (the whole cell and its short side), the 20 largest name-month gains, the hand-audit candidates; shared - NEW names per month and by cohort, the hedge ratios the E cell used"""
    L, lo, hi = obj.legs, WFN, PRE_END
    k = B.mask(lo, hi)
    rep = {"cells": {}, "new_table": new_table(W, L)}
    cands, cfg = {}, cfg_of()
    for cell in CELLS:
        xB, cB = obj.series[cell]
        run = obj.runs[cell]
        r = {"es_beta": D15.es_beta(B, S12, W, rows, xB), "episodes": D15.episodes_table(S12, xB), "map_point": {"standalone_roc_30k": summ[cell]["base"]["roc"], "rho_dd": summ[cell]["seat_ref"]["rho_dd"], "DO": summ[cell]["seat_ref"]["DO"]}}
        r["corr_with_legs"] = A13.corrs(B, xB, legs_meta, lo, hi) if legs_meta else {}
        r["corr_with_res"] = corr_with(xB, ref.res, k)
        r["age_path"] = age_table(W, L, cell, cfg, lo)
        r["age_split"] = age_split(r["age_path"])
        short_run = cell_run(W, L, cell, cfg, side=-1)
        r["cohort"] = {"cell": cohort_table(W, ctx, run), "short_side": cohort_table(W, ctx, short_run)}
        r["top20_gains"] = top_gains(W, ctx, run, L)
        r["by_exit_year"] = {int(y): int(sum(1 for rec in L.recs if traded(rec, cell) and int(jyear([W.days[rec.x]])[0]) == y)) for y in YEARS}
        cands[cell] = ni_candidate_rows(W, ctx, L, cell, run, tbis_df, status)
        rep["cells"][cell] = r
    hr = [rec.beta for rec in L.recs if rec.tE]
    rep["hedge_ratio"] = {"rebalances": len(hr), "mean": float(np.mean(hr)) if hr else float("nan"), "min": float(np.min(hr)) if hr else float("nan"), "max": float(np.max(hr)) if hr else float("nan")}
    rep["manifest_sha256"] = manifest_sha()
    return rep, cands


def wf_ranks(W):
    """the rebalances of the WF - the rank sessions whose position exits inside the WF stretch and whose 252-session history exists (ni_build's own filter) -> [(r, f, x)]; COUNTS ONLY"""
    r_all, f_all, x_all = M17.rm_schedule(W.days)
    return [(r, f, x) for r, f, x in zip(r_all.tolist(), f_all.tolist(), x_all.tolist()) if x >= 0 and WFN <= W.days[x] <= PRE_END and r >= SPEC["hold_win"] - 1]


def nc_coverage(W, start):
    """the ranks of the WF whose 24-month name-change window starts BEFORE `start` (the calendar's manifest start, or its first name-change row: a name change before it is not on it, so the exclusion is blind there) -> [(rank date, window start date)]; COUNTS ONLY"""
    out = []
    for r, _f, _x in wf_ranks(W):
        a = W.days[r] - pd.DateOffset(months=SPEC["nc_months"])
        if a < TS(start):
            out.append((W.days[r], a))
    return out


def read_audit(path=None):
    """OUT\\newissue_audit.csv (symbol, date, cell, verdict in {keep, data_event}, note) -> a frame, or None when there is no file yet. A data_event row removes that name-month (the NEW name or a SEASONED name of the pool) from BOTH cells AND the null before anything is computed [(f)]. CHOICE: the date is the
    position's FILL date - exactly the 'date' of newissue_audit_candidates.csv; the key is symbol + date, so a row covers both cells' listing of it. Refuses a verdict / cell / date it cannot read (a mistyped row must not silently do nothing)"""
    p = path or os.path.join(OUT, "newissue_audit.csv")
    if not os.path.exists(p):
        return None
    df = pd.read_csv(p, dtype=str, keep_default_na=False)
    miss = [c for c in ("symbol", "date", "cell", "verdict") if c not in df.columns]
    if miss:
        refuse(f"refused: newissue_audit.csv lacks the column(s) {miss} (columns: symbol, date, cell, verdict, note) - nothing computed")
    df["symbol"], df["cell"], df["verdict"] = df["symbol"].str.strip(), df["cell"].str.strip().str.upper(), df["verdict"].str.strip().str.lower()
    df["date"] = pd.to_datetime(df["date"].str.strip(), errors="coerce")
    bad = df[~df["verdict"].isin(("keep", "data_event")) | ~df["cell"].isin(CELLS) | df["date"].isna() | (df["symbol"] == "")]
    if len(bad):
        refuse(f"refused: newissue_audit.csv line(s) {[int(i) + 2 for i in bad.index][:10]} have an unreadable date / symbol, a verdict outside keep | data_event, or a cell outside {list(CELLS)} (nothing computed)")
    return df


def apply_audit(W, audit):
    """r17's apply_audit (a data_event row removes a name-month from the pools by fill session and name; a row that matches no session or no name refuses), its message pointed at this file"""
    try:
        return M17.apply_audit(W, audit)
    except SystemExit as e:
        raise SystemExit(str(e).replace("resmom_audit.csv", "newissue_audit.csv"))


# ------------------------------------------------------------------ the lockbox cut, asserted at the point of use
def cut_checks(W, cal, extra, cut):
    """[11] the lockbox cut at READ time, asserted a second time where NEWISSUE holds the data: nothing on / after the stage's cut (Stage A / the dryload: 2025-06-30; Stage B: the lockbox's end) is in the World's sessions - and so in its closes, volumes, ES prints and flags, which live on those sessions - in a row
    of the calendar (cash dividends, spin-offs / stock dividends, splits) or in the two tables this file reads from it (a spin-off's new symbol, a name change). The loaders (r17_resmom / r15_ddw) cut and assert on their own; this refuses if anything got through them, before a single listing is dated"""
    assert_cut("NEWISSUE sessions", W.days, cut)
    if cal is not None:
        for nm in ("div", "spin", "split"):
            fr = getattr(cal, nm, None)
            if fr is not None and len(fr) and "ex" in fr.columns:
                assert_cut(f"NEWISSUE calendar {nm} ex-dates", pd.DatetimeIndex(fr["ex"]), cut)
    if extra is not None:
        assert_cut("NEWISSUE calendar spin-off new symbols", pd.DatetimeIndex(extra.spin["ev"]), cut)
        assert_cut("NEWISSUE calendar name changes", pd.DatetimeIndex(extra.chg["ev"]), cut)


def plain_a2(B, xB):
    """the registered volatility rule for c (a REPORTED row now: a2_report is the incremental one): r18's plain A2 (r17_resmom's A2 code) pointed at this family's window 2018-02-01 .. 2020-01-31 - c = 25% x the std of #463's daily P&L / the cell's over those rows, 0.5c and 2c beside it"""
    with patched(DV, A2_WIN=A2_WIN, A2_TARGET=A2_TARGET, A2_REPORT=A2_REPORT):
        return DV.plain_a2(B, xB)


# ------------------------------------------------------------------ printing
def row_body(c):
    s, q = c["base"], c["seat"]
    return (f"rebalances {s['n_units']:>3,} name-months {s['n_pos']:>6,} net ${s['net']:>10,.0f} (${s['usd_per_year']:>8,.0f} a year) ROC@30k {s['roc']:>7.1f} Sortino {s['sortino']:>5.2f} maxDD ${s['max_dd']:>8,.0f} | DO {q['DO']:>+7.3f} rho_dd {q['rho_dd']:>+6.3f}")


def row(cell, c, tag=""):
    """a cell's headline row; [N10] its dollars a year (net / the stretch's years) stand beside the net and the ROC @ $30k; tag = '@20' marks the REPORTED 20-name-floor reading [N7]"""
    return f"{cell + tag:<5} " + row_body(c)


def beta_text(c):
    """[N2] the realised beta of a cell and what the 0.20 rule makes of it"""
    b, g = c["realised_beta"], c["beta_gate"]
    return (f"realised beta to ES {b['beta']:+.3f} per $ of short notional (Newey-West t {b['t_nw']:+.1f}, {b['n']:,} days holding a position) -> "
            + (f"within +-{g['limit']:.2f}: its drawdown-day profile is credited" if g["credited"] else
               f"OUTSIDE +-{g['limit']:.2f} (or undefined): its drawdown-day profile is REPORTED but NEVER CREDITED - A2 cannot pass, no gate, no line follows"))


def a2_text(a2):
    """A2's record in words; [N10] every ROC @ $30k has its dollars a year (net / years of the stretch it is on) beside it: the reference, the reference + c x the cell, 0.5c and 2c, the plain #463 + c x the cell, and the same two books over the cell's own stretch"""
    if not a2.get("at_half_c"):
        return f"{a2.get('error', 'no c')} -> no incremental pass"
    rf, pl = a2["reference"], a2["plain_463"]
    ya = lambda d: f"${d['usd_per_year']:,.0f} a year"
    os_ = a2.get("own_stretch")
    own = "" if not os_ else (f"; over the cell's own stretch {os_['window'][0]} .. {os_['window'][1]} ({os_['years']:.2f} years): the reference alone ROC {os_['reference_alone']['roc']:.2f} ({ya(os_['reference_alone'])}), "
                              f"with c x cell ROC {os_['with_c']['roc']:.2f} ({ya(os_['with_c'])})")
    return (f"c x{a2['c']:.4g} (cell daily std ${a2['std_cell']:,.0f} vs #463's ${a2['std_book']:,.0f} over {a2['window'][0]} .. {a2['window'][1]}); on the reference's WF ({a2['years']:.2f} years; dollars a year = net / years): REFERENCE + c x cell ROC@30k {a2['roc']:.2f} ({ya(a2)}) Sortino {a2['sortino']:.3f} "
            f"against the reference's {rf['roc']:.2f} ({ya(rf)}) / {rf['sortino']:.3f} -> "
            + ("INCREMENTAL PASS (both above, beta rule met): a forward BOOK shadow line opens, MANAGER #70's gate follows" if a2["incremental_pass"] else
               "no incremental pass (both must be above" + ("" if a2["beta_rule_ok"] else "; the beta rule is not met") + ")")
            + f"; at 0.5c ROC {a2['at_half_c']['roc']:.2f} ({ya(a2['at_half_c'])}) / Sortino {a2['at_half_c']['sortino']:.3f}, at 2c ROC {a2['at_double_c']['roc']:.2f} ({ya(a2['at_double_c'])}) / Sortino {a2['at_double_c']['sortino']:.3f}; "
            f"the plain #463 + c x cell book (a reported row): ROC {pl['roc']:.2f} ({ya(pl)}) / Sortino {pl['sortino']:.2f}" + own)


def print_cells(res, audit_st=None, tag="", reported=False):
    """both cells' rows of one reading: the REGISTERED reading (default) or - reported=True, tag '@20' - the REPORTED 20-name-floor reading beside it [N7] (its own null; its (a)-(e) line says it is information only)"""
    nul = res["null"]
    lab = f" under the {FLOOR_REPORTED}-name floor" if reported else ""
    info = f" under the {FLOOR_REPORTED}-name floor (REPORTED, never a pass route)" if reported else ""
    if nul:
        print(f"  null{lab} ({nul['draws']} draws, seed {nul['seed']}, the MAX over the 2 cells): ROC@30k p5 {nul['roc_max']['p5']:.1f} p50 {nul['roc_max']['p50']:.1f} p95 {nul['roc_max']['p95']:.1f}; each cell alone p50 / p95: "
              + ", ".join(f"{c} {nul['by_cell'][c]['p50']:.1f} / {nul['by_cell'][c]['p95']:.1f}" for c in CELLS))
    for cell in CELLS:
        c = res["cells"][cell]
        print("  " + row(cell, c, tag))
        print("        stress: " + ", ".join(f"{k} net ${v['net']:,.0f} (ROC {v['roc']:.1f})" for k, v in {**c["stress"], **c["borrow"]}.items()) + "; by July-June year: " + " ".join(f"{y}-{(y + 1) % 100:02d}:{v:+,.0f}" for y, v in c["base"]["by_year"].items()))
        print(f"        2020-21 net ${c['base']['net_2020_21']:,.0f}; calendar 2022 net ${c['base']['net_2022']:,.0f}; without 2022 ${c['base']['net_ex2022']:,.0f}; without Feb 15 - Apr 30 2020 ${c['base']['net_ex2020']:,.0f}; without its best 1% of days ${c['base']['net_ex_best_days']:,.0f}, of name-months ${c['base']['net_ex_best_pos']:,.0f}")
        if "checks" in c:
            fails = [k for k, v in c["checks"].items() if not v]
            print(f"        Stage A (a)-(e){info} {'PASS' if c['PASS'] else 'FAIL (' + ', '.join(fails) + ')'}" + ("" if audit_st is None else f"; the hand audit (f): {audit_st[cell]['audited']}/{audit_st[cell]['listed']} of the top-{AUDIT_N} listed are in newissue_audit.csv (information only: the lead signs (f) off)"))
        print(f"        [N2] {beta_text(c)}")
        print(f"        A2 (a report) [X1]: {a2_text(c['A2'])}")
        g = c["gate70"]
        print(f"        #70 gate basis [X1] (the REFERENCE book's {g['episodes']} drawdown episodes, {g['dd_days_from_2018_02']} DD days from 2018-02): the cell's DO {g['DO']:+.3f}, rho_dd {g['rho_dd']:+.3f}" + (
              f"; its null's DO (the MAX over the 2 cells) p5 {g['null_do_p5']:+.3f} p50 {g['null_do_p50']:+.3f} p95 {g['null_do_p95']:+.3f} -> the cell's DO is {'above' if g['DO_above_null_p95'] else 'not above'} the null's p95; DO without its best episode "
              f"{g['DO_ex_best_episode']:+.3f} ({g['best_episode']}); the gate's basis is {'met' if g['gate_basis_met'] else 'not met'}" + ("" if g["credited"] else " (the beta rule: never credited)") if "null_do_p95" in g else " (no null in this reading)"))


def print_floors(res, res20):
    """[N7] BOTH FLOORS SIDE BY SIDE: the registered floor's cells (E, M: the verdict) and the reported 20-name floor's (E @20, M @20: each reading with its own leg and its own null, never a pass route) in four columns - the traded rebalances and name-months, the net and the dollars a year, ROC @ $30k / Sortino,
    the drawdown, the July-June years and the nets that decide (a)-(e), the realised beta, each reading's null p95, each reading's (a)-(e) verdict (the 20 reading's is information only) and A2's incremental pass"""
    cols = [(res["cells"][c], c, "", res["null"]) for c in CELLS] + [(res20["cells"][c], c, f" @{FLOOR_REPORTED}", res20["null"]) for c in CELLS]
    each = lambda f: [f(r_, n_) for r_, _c, _t, n_ in cols]
    print(f"BOTH FLOORS SIDE BY SIDE [N7] - the REGISTERED {SPEC['floor']}-name floor (cells E, M: the verdict) and the REPORTED {FLOOR_REPORTED}-name floor (cells E @{FLOOR_REPORTED}, M @{FLOOR_REPORTED}: its own leg and its own null; never a pass route)")
    print(diag_line("", [f"cell {c}{t}" for _r, c, t, _n in cols]))
    print(diag_line("  traded rebalances / name-months", each(lambda r_, n_: f"{r_['base']['n_units']} / {r_['base']['n_pos']:,}")))
    print(diag_line("  net $ / dollars a year (net / years)", each(lambda r_, n_: f"{r_['base']['net']:+,.0f} / {r_['base']['usd_per_year']:+,.0f}")))
    print(diag_line("  ROC@30k / Sortino", each(lambda r_, n_: f"{r_['base']['roc']:.1f} / {r_['base']['sortino']:.2f}")))
    print(diag_line("  max drawdown $", each(lambda r_, n_: f"{r_['base']['max_dd']:,.0f}")))
    print(diag_line("  July-June years positive / net without calendar 2022 $", each(lambda r_, n_: f"{r_['base']['years_pos']} / {r_['base']['net_ex2022']:+,.0f}")))
    print(diag_line("  net at 10 bps / at the 10%/yr borrow $", each(lambda r_, n_: f"{r_['stress']['10 bps']['net']:+,.0f} / {r_['borrow']['10%/yr']['net']:+,.0f}")))
    print(diag_line("  realised beta to ES (per $ of short notional)", each(lambda r_, n_: f"{r_['realised_beta']['beta']:+.3f}")))
    print(diag_line("  the null's ROC@30k p95 (the max over the 2 cells)", each(lambda r_, n_: f"{n_['roc_max']['p95']:.1f}" if n_ else "-")))
    print(diag_line("  Stage A (a)-(e) (the 20 reading's: information only)", each(lambda r_, n_: (("PASS" if r_["PASS"] else "FAIL") if "PASS" in r_ else "-"))))
    print(diag_line("  A2 incremental pass over the reference", each(lambda r_, n_: "yes" if r_["A2"]["incremental_pass"] else "no")))


def print_episodes(res, ref, res20=None):
    """[N10] the reference line's drawdown episodes (MDL r1's qualifying episodes of #463 + 0.264 x RES on its WF) INSIDE the cell's stretch: each episode's DD days (the day after the peak .. the trough) from the stretch's start on - an episode that starts before it is cut to the part inside it -
    the reference's P&L over them, the cell's P&L inside each (a '+' marks an episode the cell HELPS in: it earns while the reference loses) and the count of episodes it helps in; with `res20` the reported 20-name-floor cells stand in two more columns"""
    cols = [(res["cells"][c], c, "") for c in CELLS] + ([(res20["cells"][c], c, f" @{FLOOR_REPORTED}") for c in CELLS] if res20 else [])
    e0 = cols[0][0]["ref_episodes_in_stretch"]
    g = ref.structure
    print(f"  THE REFERENCE LINE'S DRAWDOWN EPISODES [N10] (#463 + 0.264 x RES; MDL r1's rule: {e0['episodes_on_wf']} qualifying on its WF {WF0:%Y-%m-%d} .. {PRE_END:%Y-%m-%d}, {g['days']} DD days; {e0['inside']} have DD days inside the cell's stretch {WFN:%Y-%m-%d} .. {PRE_END:%Y-%m-%d}, {e0['cut']} of "
          f"them cut to the part inside it) - the cell's P&L over those DD days (the day after the peak .. the trough); '+' = the cell helps there")
    print(diag_line("  first DD day inside .. trough, depth (DD days inside / in all, the reference's P&L inside)", [f"cell {c}{t}" for _r, c, t in cols]))
    for q, e in enumerate(e0["rows"]):
        print(diag_line(f"  {e['first_dd_day']} .. {e['trough']} ${e['depth']:,.0f} ({e['dd_days_inside']}/{e['dd_days']} d{', cut' if e['cut'] else ''}, ref {e['book_pnl']:+,.0f})",
                        [f"{r_['ref_episodes_in_stretch']['rows'][q]['cell_pnl']:+,.0f}" + (" +" if r_["ref_episodes_in_stretch"]["rows"][q]["helps"] else "") for r_, _c, _t in cols]))
    print(diag_line(f"  all those episodes (the cell's P&L over the DD days inside; the reference's {e0['reference_pnl']:+,.0f})", [f"{r_['ref_episodes_in_stretch']['cell_pnl']:+,.0f}" for r_, _c, _t in cols]))
    print(diag_line(f"  the cell HELPS in (of {e0['inside']} episodes inside the stretch)", [f"{r_['ref_episodes_in_stretch']['helped']} of {r_['ref_episodes_in_stretch']['inside']}" for r_, _c, _t in cols]))


def traded_text(lc, lc20):
    """[N7] / [N9] the traded months under BOTH floors, by fill year (registered / reported of the rebalances), and how many sit in 2018-03 .. 2022-03 - the LOW-POWER flag's claim, counted (leg_counts' records)"""
    ys = sorted(set(lc["traded_by_fill_year"]) | set(lc20["traded_by_fill_year"]) | set(lc["rebalances_by_fill_year"]))
    by = "; ".join(f"{y}: {lc['traded_by_fill_year'].get(y, 0)} / {lc20['traded_by_fill_year'].get(y, 0)} of {lc['rebalances_by_fill_year'].get(y, 0)}" for y in ys)
    return (f"  TRADED MONTHS UNDER BOTH FLOORS [N7]: {lc['traded']} of the {lc['rebalances']} rebalances under the REGISTERED {lc['floor']}-name floor, {lc20['traded']} under the REPORTED {lc20['floor']}-name floor (never a pass route); by fill year (registered / reported of the rebalances): {by}; "
            f"in 2018-03 .. 2022-03: {lc['traded_2018_03_to_2022_03']} of the {lc['traded']} (registered), {lc20['traded_2018_03_to_2022_03']} of the {lc20['traded']} (reported)")


def print_variants(var):
    """the REPORTED rows that need another leg: [N3] names 4 to 8 months after listing, the spinco / name-change names included, the ranks whose name-change window starts before the calendar left out"""
    for name, o in var.items():
        n = o["new_per_month"]
        print(f"  {name}: {o['rebalances']} rebalances, {o['below_floor']} under the {SPEC['floor']}-name floor; NEW names per month min {n['min']} / median {n['median']:.0f} / max {n['max']}")
        for cell in CELLS:
            s = o[cell]
            tail = "".join(f"; included {lab} name-months {s[f'included_{k}_name_months']:,} net ${s[f'included_{k}_net']:,.0f}" for k, lab in (("spinco", "spinco"), ("name_change", "name-change"), ("both", "both")) if f"included_{k}_name_months" in s)
            print(f"      {cell}: name-months {s['n_pos']:,} in {s['n_units']} rebalances, net ${s['net']:,.0f} ROC@30k {s['roc']:.1f} Sortino {s['sortino']:.2f} maxDD ${s['max_dd']:,.0f}; July-June years positive {s['years_pos']}; net without 2022 ${s['net_ex2022']:,.0f}{tail}")


def print_new_table(rows_):
    """NEW names per month: by fill year min / median / max of the survivors of every removal (the age-window names before the removals beside), the months under the registered floor, E / M traded"""
    by = defaultdict(list)
    for r_ in rows_:
        by[r_["rank"][:4]].append(r_)
    print("  NEW names per month by the rank's year (rebalances: NEW survivors min / median / max, age-window names before the removals median, SEASONED candidates median, under the floor, E traded, M traded): " + "; ".join(
        f"{y}: {len(v)}: {min(x['new'] for x in v)} / {np.median([x['new'] for x in v]):.0f} / {max(x['new'] for x in v)}, {np.median([x['age_window_names'] for x in v]):.0f}, {np.median([x['seasoned_candidates'] for x in v]):.0f}, {sum(not x['traded'] for x in v)}, "
        f"{sum(x['E'] for x in v)}, {sum(x['M'] for x in v)}" for y, v in sorted(by.items())))
    coh = defaultdict(int)
    for r_ in rows_:
        for y, n in r_["by_cohort"].items():
            coh[int(y)] += int(n)
    print("  NEW name-months by listing-year cohort (all rebalances): " + ", ".join(f"{y}: {n:,}" for y, n in sorted(coh.items())))


def print_age_path(path, label, split=None):
    """[X2] the path by months since listing: one row per month 4 .. 24 of the cell's marks (name-days, $ of the short side, $ of the other side, their sum), and what falls outside 4 .. 24; the draft's 6-12 vs 12-24 months split of it beside"""
    print(f"  {label}: path by months since listing (a month = 21 sessions of the name's age on the mark's day; name-days / short side $ / other side $ / net $):")
    cells_ = []
    for q in AGE_MONTHS:
        v = path.get(q)
        cells_.append(f"{q}: " + (f"{v['days']:,} / {v['short']:+,.0f} / {v['other']:+,.0f} / {v['short'] + v['other']:+,.0f}" if v else "-"))
    print("    " + "; ".join(cells_))
    rest = {q: v for q, v in path.items() if q not in AGE_MONTHS}
    if rest:
        print("    outside 4 .. 24: " + "; ".join(f"{q}: {v['days']:,} / {v['short']:+,.0f} / {v['other']:+,.0f} / {v['short'] + v['other']:+,.0f}" for q, v in sorted(rest.items())))
    if split is not None:
        print("    by age (name-days / short side $ / other side $ / net $): " + "; ".join(f"{lab}: {v['days']:,} / {v['short']:+,.0f} / {v['other']:+,.0f} / {v['net']:+,.0f}" for lab, v in split.items() if v["days"] or lab in ("6-12 months", "12-24 months")))


def print_cohorts(co, label):
    """[N5] P&L by listing-year cohort 2016 .. 2024 (and any other year apart): name-months, distinct names, net $, the short side's and the other side's"""
    ys = sorted(set(COHORTS) | set(co))
    print(f"  {label}: P&L by listing-year cohort (name-months / names / net $ / short side $ / other side $): " + "; ".join(
        f"{y}: " + (f"{co[y]['name_months']:,} / {co[y]['names']} / {co[y]['net']:+,.0f} / {co[y]['short']:+,.0f} / {co[y]['other']:+,.0f}" if y in co else "-") for y in ys))


def print_reports(rep, summ):
    for c in CELLS:
        r = rep["cells"][c]
        b, e = r["es_beta"], r["episodes"]
        print(f"  {c}: beta to ES in #463's drawdowns ($ per 1% ES move; DD days / DD weeks / all WF days) {b['DD days']['usd_per_1pct_es']:+,.0f} / {b['DD weeks (every day of them)']['usd_per_1pct_es']:+,.0f} / {b['all WF days']['usd_per_1pct_es']:+,.0f}; "
              f"P&L inside #463's {len(e)} qualifying drawdowns: net ${sum(x['cell_pnl'] for x in e):,.0f} over {sum(x['dd_days'] for x in e)} DD days (#463's ${sum(x['book_pnl'] for x in e):,.0f}); MDL map point (the DD days from 2018-02 on): "
              f"ROC@30k {r['map_point']['standalone_roc_30k']:.1f}, rho_dd {r['map_point']['rho_dd']:+.3f}, DO {r['map_point']['DO']:+.3f}")
        cl = r["corr_with_legs"]
        print(f"  {c}: daily correlation with RESMOM's RES (read through the reference's loader, never re-computed) {r['corr_with_res']:+.3f}" + ("; with #463's legs: " + ", ".join(f"{k} {v:+.2f}" for k, v in cl.items() if isinstance(v, (int, float)) and math.isfinite(v)) if cl else ""))
        for x in r["top20_gains"][:3]:
            print(f"      {c} top name-month gain {x['rank']}: {x['symbol']} (listed {x['listed']}, {x['age_at_rank']} sessions old at the rank) filled {x['fill']} -> {x['exit']} ${x['pnl']:,.0f} (short side ${x['short']:,.0f}, other side ${x['other']:,.0f}) (the 20 largest are in the Stage A file)")
    h = rep["hedge_ratio"]
    print(f"  cell E's ex-ante hedge ratio (the beta of the equal-weight NEW basket on ES over the 126 sessions before the rank, x the short notional): {h['rebalances']} rebalances, mean {h['mean']:.2f}, min {h['min']:.2f}, max {h['max']:.2f}")
    print_new_table(rep["new_table"])


DIAG_LW, DIAG_CW = 62, 22


def diag_line(label, vals):
    return f"  {label:<{DIAG_LW}}" + "".join(f"{v:>{DIAG_CW}}" for v in vals)


def print_diagnostics(res, rep, ref, var, res20=None):
    """[X2] DEEPER DIAGNOSTICS of the registered reading, both cells side by side: the cost curve at 0 / 5 / 10 / 20 bps a side (the stocks' cost; ES keeps its 0.5), the borrow rows (3 / 10 / 25 %/yr), a row per July-June year, the regime halves, [N10] the reference line's drawdown episodes
    inside the cell's stretch (the cell's P&L inside each, the count it helps in), the short side and the long / hedge side apart, the 2020-21 boom and 2022 apart, [N5] the listing-year cohorts, the path by months since listing, and the REPORTED variant rows. With `res20` the same rows of the
    REPORTED 20-name-floor reading stand in two more columns (cells E @20, M @20) [N7]. None of it is a pass route"""
    cells = res["cells"]
    cols = [(cells[c], c, "") for c in CELLS] + ([(res20["cells"][c], c, f" @{FLOOR_REPORTED}") for c in CELLS] if res20 else [])
    each = lambda f: [f(r_, c) for r_, c, _t in cols]
    nr = lambda s: f"{s['net']:+,.0f} / {s['roc']:.1f}"
    print("DIAGNOSTICS [X2] - the registered reading, the WF stretch, both cells side by side" + (f"; cells E @{FLOOR_REPORTED}, M @{FLOOR_REPORTED} = the reported {FLOOR_REPORTED}-name-floor reading beside them [N7]" if res20 else "") + "; none of this is a pass route")
    print(diag_line("", [f"cell {c}{t}" for _r, c, t in cols]))
    print("  COST CURVE - the stocks' cost a side (ES keeps its own 0.5 bps; borrow at its base 3%/yr): net $ / ROC@30k")
    for lab, get in (("0 bps", lambda c: c["cost0"]), ("5 bps (the base)", lambda c: c["base"]), ("10 bps", lambda c: c["stress"]["10 bps"]), ("20 bps", lambda c: c["stress"]["20 bps"])):
        print(diag_line(f"  {lab}", each(lambda c, k: nr(get(c)))))
    print("  BORROW on every NEW short, every short day (5 bps a side): net $ / ROC@30k")
    print(diag_line("  3%/yr (the base [N1])", each(lambda c, k: nr(c["base"]))))
    for b in BORROW_STRESS:
        print(diag_line(f"  {b:.0%}/yr", each(lambda c, k: nr(c["borrow"][f"{b:.0%}/yr"]))))
    print(diag_line("  shorts that stop printing valued at zero (r17's [R2] reading)", each(lambda c, k: nr(c["short0"]["cell"]))))
    print("  BY JULY-JUNE YEAR - net $ of the daily series (2017-18 = 2018-02-01 .. 2018-06-30)")
    for y in YEARS:
        print(diag_line(f"  {y}-{(y + 1) % 100:02d}", each(lambda c, k: f"{c['base']['by_year'][y]:+,.0f}")))
    print("  2020-21 (the listing boom) and calendar 2022 (the bust) apart - net $")
    print(diag_line("  2020-01-01 .. 2021-12-31", each(lambda c, k: f"{c['base']['net_2020_21']:+,.0f}")))
    print(diag_line("  2022-01-01 .. 2022-12-31", each(lambda c, k: f"{c['base']['net_2022']:+,.0f}")))
    print(diag_line("  all the rest (without both)", each(lambda c, k: f"{c['base']['net'] - c['base']['net_2020_21'] - c['base']['net_2022']:+,.0f}")))
    print("  THE TWO REGIME HALVES - net $ / ROC@30k, then the name-months that exited in the half")
    for lab, _a, _b in HALVES:
        print(diag_line(f"  {lab}", each(lambda c, k: nr(c["halves"][lab]))))
        print(diag_line("    name-months", each(lambda c, k: f"{c['halves'][lab]['n_pos']:,}")))
    g = ref.structure
    print_episodes(res, ref, res20)
    print("  THE SHORT SIDE AND THE LONG / HEDGE SIDE APART (E: the ES hedge, M: the matched SEASONED longs; costs and borrow in their own side): net $ / ROC@30k")
    print(diag_line("  short side alone (every NEW name)", each(lambda c, k: nr(c["sides"]["short side only"]))))
    print(diag_line("  long / hedge side alone", each(lambda c, k: nr(c["sides"]["long / hedge side only"]))))
    print(diag_line("  both = the cell as traded", each(lambda c, k: nr(c["base"]))))
    print(f"  #70 GATE BASIS - the cell's DO against the REFERENCE book's {g['episodes']} drawdown episodes, beside its null's (the MAX over the 2 cells), and [N2]'s beta rule")
    print(diag_line("  realised beta to ES (per $ of short notional)", each(lambda c, k: f"{c['realised_beta']['beta']:+.3f}")))
    print(diag_line("  the beta rule |beta| <= 0.20 (credit)", each(lambda c, k: "credited" if c["beta_gate"]["credited"] else "NOT credited")))
    print(diag_line("  DO (cell P&L over the DD days / the reference's loss)", each(lambda c, k: f"{c['gate70']['DO']:+.3f}")))
    print(diag_line("  the null's DO p95", each(lambda c, k: f"{c['gate70']['null_do_p95']:+.3f}" if "null_do_p95" in c["gate70"] else "-")))
    print(diag_line("  DO without the cell's best episode", each(lambda c, k: f"{c['gate70']['DO_ex_best_episode']:+.3f}")))
    print(diag_line("  the gate's basis met (credited, above p95, > 0 without the best)", each(lambda c, k: ("yes" if c["gate70"]["gate_basis_met"] else "no") if "gate_basis_met" in c["gate70"] else "-")))
    for c in CELLS:
        print_age_path(rep["cells"][c]["age_path"], f"cell {c}", rep["cells"][c]["age_split"])
        print_cohorts(rep["cells"][c]["cohort"]["cell"], f"cell {c}")
        print_cohorts(rep["cells"][c]["cohort"]["short_side"], f"cell {c} short side alone")
    print("  VARIANT ROWS (reported, never a pass route):")
    print_variants(var)


NEW_KEYS = (("new_age", "new_spinco", "new_name_change", "new_no_fill") + tuple(f"new_pre_{h}" for h in HYG) + tuple(f"new_old_{h}" for h in HYG[1:]) + ("new_audit",) + tuple(f"new_post_{h}" for h in HYG) + ("new_post_spin", "new_pool", "new_kept_naive")
            + tuple(f"new_kept_{h}" for h in HYG) + ("new_kept_flagged", "new_kept_calendar_split", "new_closed_spin"))
SEAS_KEYS = (("seasoned_age", "seas_name_change", "seas_short_history", "seas_no_es_pairs", "seas_no_fill") + tuple(f"seas_pre_{h}" for h in HYG) + tuple(f"seas_old_{h}" for h in HYG[1:]) + ("seas_audit",) + tuple(f"seas_post_{h}" for h in HYG)
             + ("seas_post_spin", "seas_pool", "seas_kept_naive") + tuple(f"seas_kept_{h}" for h in HYG) + ("seas_kept_flagged", "seas_kept_calendar_split", "seas_closed_spin"))


def print_counts(label, cnt):
    """COUNTS by fill year, summed over the rebalances: every NEW (accepted listing, 126 .. 504 sessions old) and SEASONED name is counted once at its FIRST removal reason, then in the pool; the rebalance bookkeeping beside"""
    for title, keys in (("NEW", NEW_KEYS), ("SEASONED", SEAS_KEYS)):
        ks = [k for k in keys if any(k in c for c in cnt.values())]
        print(f"  {label} {title} names by fill year, name-months, each counted once at its FIRST removal reason (columns: " + " / ".join(ks) + ")")
        for y, c in sorted(cnt.items()):
            if c.get("rebalances", 0):
                print(f"    {y}: " + " ".join(f"{c.get(k, 0)}" for k in ks))
    print(f"  {label} rebalance bookkeeping by fill year (rebalances / unresolved / warm-up / dropped / empty universe / under the {SPEC['floor']}-name floor / fewer SEASONED names than NEW / no hedge ratio / unmatched NEW names): " + "; ".join(
        f"{y}: {c.get('rebalances', 0)} / {c.get('unresolved', 0)} / {c.get('warmup', 0)} / {c.get('dropped', 0)} / {c.get('empty', 0)} / {c.get('below_floor', 0)} / {c.get('fewer_seasoned_than_new', 0)} / {c.get('no_beta', 0) + c.get('no_beta_pairs', 0)} / "
        f"{c.get('unmatched_new', 0)}" for y, c in sorted(cnt.items())))


def print_exclusions(label, cnt):
    """[N4] and the registered exclusions, COUNTS by fill year, name-months of the rebalances: the names in the universe whose listing failed / cannot be verified, the NEW age-window names that are a spin-off's new symbol or have a name change in the 24 months (each counted whatever else removes it) and
    the SEASONED names with a name change"""
    ys = sorted(y for y, c in cnt.items() if c.get("rebalances", 0))
    print(f"  {label} exclusions by fill year (name-months: universe names whose listing failed [N4] / is unverifiable; NEW age-window names that are a spinco / have a name change; SEASONED names with a name change): " + "; ".join(
        f"{y}: {cnt[y].get('n4_failed_names', 0)} / {cnt[y].get('n4_unverifiable_names', 0)}; {cnt[y].get('new_spinco_any', 0)} / {cnt[y].get('new_name_change_any', 0)}; {cnt[y].get('seas_name_change', 0)}" for y in ys))


def leg_counts(W, L, floor=None):
    """COUNTS ONLY of a leg built in counts mode: the rebalances, the traded ones under `floor` (default the registered floor; a rebalance trades when its NEW survivors reach it - the E / M availability is the leg's own, set at the floor the leg was built under, so a REPORTED higher floor reads the same leg),
    the traded months by fill year and how many fill in 2018-03 .. 2022-03 [N9], the NEW survivors per rebalance (min / median / max), the first and last traded rank, the months under the floor, by cohort -> record"""
    fl = SPEC["floor"] if floor is None else floor
    n = [r_.n_new for r_ in L.recs]
    tr = [r_ for r_ in L.recs if r_.n_new >= fl]
    ym = lambda r_: (int(W.days[r_.f].year), int(W.days[r_.f].month))
    co, nm = Counter(), defaultdict(set)
    for r_ in L.recs:
        for y, c_ in zip(r_.cohort.tolist(), r_.new.tolist()):
            co[int(y)] += 1
            nm[int(y)].add(int(c_))
    return {"floor": fl, "rebalances": len(L.recs), "traded": len(tr), "traded_by_fill_year": {int(y): int(k_) for y, k_ in sorted(Counter(int(W.days[r_.f].year) for r_ in tr).items())},
            "rebalances_by_fill_year": {int(y): int(k_) for y, k_ in sorted(Counter(int(W.days[r_.f].year) for r_ in L.recs).items())},
            "traded_2018_03_to_2022_03": int(sum(1 for r_ in tr if (2018, 3) <= ym(r_) <= (2022, 3))),
            "below_floor": [f"{W.days[r_.r]:%Y-%m-%d}" for r_ in L.recs if r_.n_new < fl], "new_per_rebalance": ([int(min(n)), float(np.median(n)), int(max(n))] if n else [0, 0.0, 0]),
            "seasoned_per_rebalance": ([int(min(r_.n_seas for r_ in L.recs)), float(np.median([r_.n_seas for r_ in L.recs])), int(max(r_.n_seas for r_ in L.recs))] if L.recs else [0, 0.0, 0]),
            "first_traded_rank": (f"{W.days[tr[0].r]:%Y-%m-%d}" if tr else None), "last_traded_rank": (f"{W.days[tr[-1].r]:%Y-%m-%d}" if tr else None),
            "cohort_name_months": {y: n_ for y, n_ in sorted(co.items())}, "cohort_names": {y: len(v) for y, v in sorted(nm.items())},
            "E_without_enough_basket_pairs": int(sum(1 for r_ in tr if not r_.tE)), "M_without_a_candidate": int(sum(1 for r_ in tr if not r_.tM))}


# ------------------------------------------------------------------ the hand audit (f): the harness lists, the HAND decides; a data event removes the name-month from the cells AND the nulls
def audit_status(cands, audit):
    """per cell: how many of the listed top-50 contributors appear in newissue_audit.csv (symbol + fill date). INFORMATION ONLY: the harness never decides (f) - the lead's go-flag is the sign-off"""
    return M17.audit_status(cands, audit)


# ------------------------------------------------------------------ dryload: counts only
def dryload():
    """the WF inputs through every loader (cut at 2025-06-30) and COUNTS only: listings by year and [N4]'s failures (every cached name and the names ever in the universe), the universe, the calendar's spin-off / name-change rows, the NEW and SEASONED names per rebalance, the exclusions by year, the
    months under the registered 10-name floor and under the reported 20-name floor (the traded months under both, by fill year [N7]), the NEW names by listing cohort, the first and last traded ranks, hygiene removals, the ES coverage. NO price, return, regression, hedge ratio, match, P&L or Stage A statistic is computed or printed: the basket-ES pair counts the hedge needs are counted from which
    returns EXIST, no match is made and no position path is built"""
    prereg_ok()
    t0 = time.time()
    D = M17.load_data(S.LB0)
    nfull, days_all = len(D.syms), D.days
    tbis = D15.load_tbis(S.LB0)
    es_frames, es_meta = D15.load_es(S.LB0)
    full_match = D15.tbis_array(D.days, D.syms, tbis)[1]
    Cl0, Vv0, _F0 = D15.load_daily(D, S.LB0)                                                  # CHOICE: the listing counts are taken over EVERY cached name (the pool the universe draws on) as well as over the names ever in the universe (the World's columns)
    li_all = listing_info(Cl0, Vv0)
    del Cl0, Vv0, _F0
    cal, winfo = M17.wide_load(S.LB0, need=False, enforce=False)                             # CHOICE: the dryload counts on the calendar when it exists and REPORTS its sha status (only Stage A / B refuse an unregistered one)
    extra, einfo = cal_extra(S.LB0)
    W = M17.build_world(D, S.LB0, es_frames, tbis, cal)
    D15.release(D)
    cut_checks(W, cal, extra, S.LB0)
    print(f"dryload: inputs ready ({time.time() - t0:.0f}s); every input cut to dates < {S.LB0:%Y-%m-%d}; ES masters {es_meta['raw']['filename']} / {es_meta['adj']['filename']}")
    wf = (W.days >= WFN) & (W.days <= PRE_END)
    print(f"sessions: {W.T:,} on the market calendar ({W.days[0]:%Y-%m-%d} .. {W.days[-1]:%Y-%m-%d}), {int(wf.sum()):,} inside the WF stretch ({WFN:%Y-%m-%d} .. {PRE_END:%Y-%m-%d}); symbols: {nfull:,} in the cache after SIPORB's price / volume floor, {W.S:,} ever in the universe; "
          f"the cache's first session is {W.days[0]:%Y-%m-%d} (registered {FIRST_SESSION:%Y-%m-%d}: {'yes' if W.days[0] == FIRST_SESSION else 'NO - a listing is dated from the session after the data starts, whatever the registered date says'})")
    usz, yrs = W.U.sum(axis=1), W.days.year.to_numpy()
    print("universe size per session by year (sessions with a universe: min / median / max): " + "; ".join(
        f"{y}: {int((m := (yrs == y) & (usz > 0)).sum())} sessions {int(usz[m].min())} / {int(np.median(usz[m]))} / {int(usz[m].max())}" for y in sorted(set(yrs)) if ((yrs == y) & (usz > 0)).any()))
    ctx = make_ctx(W, extra, counts_only=True)
    print("LISTING SESSIONS [N4] (a name's first bar in the cache, dated only from the session after the cache's first; accepted only with a raw close and volume on >= 18 of the 20 sessions after it; failures are neither NEW nor SEASONED anywhere):")
    la, lw = listing_counts(days_all, li_all), listing_counts(W.days, ctx.li)
    for lab, lc in (("every cached name", la), ("the names ever in the universe", lw)):
        print(f"  {lab}: present at the first session {lc['present_at_first_session']:,}, no bar {lc['no_bar']:,}; by listing year (dated / accepted / failed [N4] / unverifiable - under 20 sessions follow): " + "; ".join(
            f"{y}: {v['dated']:,} / {v['accepted']:,} / {v['failed']:,} / {v['unverifiable']:,}" for y, v in lc["by_year"].items()))
    if W.ca is None:
        print(f"wide corporate-actions calendar [R1]: not on file yet ({winfo['path']}) - Stage A refuses until it is on file and WIDE_CA_SHA matches; this dryload counted no spinco / name-change exclusion and no dividend")
    else:
        M17.print_wide(W.ca)
        print(f"calendar tables this family reads (cut at read): spin-off rows {einfo['spin_off']['rows']:,} ({einfo['spin_off']['usable']:,} with a new symbol and a date; by year {einfo['spin_off']['by_year']}; earliest {einfo['spin_off']['earliest']}), name-change rows {einfo['name_change']['rows']:,} "
              f"({einfo['name_change']['usable']:,} usable; by year {einfo['name_change']['by_year']}; earliest {einfo['name_change']['earliest']}); placed on the universe grid: {ctx.cal_counts['spin_events_placed']:,} spin-off new symbols, {ctx.cal_counts['name_change_events_placed']:,} name-change symbol events")
        st0 = M17.calendar_start(W.ca["file"]["manifest"])
        if st0 is not None:
            ncc = nc_coverage(W, st0)
            print(f"calendar coverage: the calendar starts {st0:%Y-%m-%d}; the 24-month name-change window of {len(ncc)} WF ranks starts before it (a name change before it is not on the calendar: the exclusion is blind there; reported row without them): "
                  + (", ".join(f"{d:%Y-%m-%d}" for d, _a in ncc) if ncc else "none"))
        e0 = einfo["name_change"]["earliest"]
        if e0 is not None:
            nce = nc_coverage(W, TS(e0))
            print(f"calendar name-change coverage: the earliest name-change row on the calendar is dated {e0}; the 24-month name-change window of {len(nce)} of the {len(wf_ranks(W))} WF ranks starts before it (the exclusion sees only part of such a window; a reported row leaves them out)")
    Lr, Lk = ni_build(W, ctx, WFN, PRE_END, "remove"), ni_build(W, ctx, WFN, PRE_END, "naive")
    r_all, f_all, x_all = M17.rm_schedule(W.days)
    inwf = [(r, f, x) for r, f, x in zip(r_all.tolist(), f_all.tolist(), x_all.tolist()) if x >= 0 and WFN <= W.days[x] <= PRE_END]
    lc_, lc20 = leg_counts(W, Lr), leg_counts(W, Lr, FLOOR_REPORTED)
    print(f"rebalances: {lc_['rebalances']} in WF (positions that exit {WFN:%Y-%m-%d} .. {PRE_END:%Y-%m-%d} with a rank at or after session {SPEC['hold_win'] - 1}), {lc_['traded']} with >= {SPEC['floor']} NEW names [N7] (E also needs >= {SPEC['beta_min']} basket-ES pairs of the {SPEC['beta_win']}: "
          f"{lc_['E_without_enough_basket_pairs']} traded months fail it; M needs a SEASONED candidate: {lc_['M_without_a_candidate']} fail it), {lc_['rebalances'] - lc_['traded']} under the floor; "
          f"{sum(1 for r, f, x in inwf if r < SPEC['hold_win'] - 1)} earlier ranks are warm-up; the stage's last rank has no next fill: unresolved, out")
    print(f"  first traded rank {lc_['first_traded_rank']}, last traded rank {lc_['last_traded_rank']}" + (f"; first rebalance of the WF {W.days[Lr.recs[0].r]:%Y-%m-%d}, last {W.days[Lr.recs[-1].r]:%Y-%m-%d}" if Lr.recs else ""))
    print(f"  months under the {SPEC['floor']}-name floor ({len(lc_['below_floor'])}): " + (", ".join(lc_["below_floor"]) if lc_["below_floor"] else "none"))
    print(traded_text(lc_, lc20))
    print(f"  months under the {FLOOR_REPORTED}-name floor ({len(lc20['below_floor'])}): " + (", ".join(lc20["below_floor"]) if lc20["below_floor"] else "none")
          + f"; of the {lc20['traded']} traded months under it E fails its basket-ES pair count in {lc20['E_without_enough_basket_pairs']}, M has no SEASONED candidate in {lc20['M_without_a_candidate']}")
    print(f"  {LOW_POWER}")
    n_pre = sum(1 for q in Lr.recs if q.newage >= SPEC["floor"])
    print(f"  Stage A's bar (a) [N8] needs >= {RULES['reb']} traded rebalances: {lc_['traded']} of the {lc_['rebalances']} months clear the REGISTERED {SPEC['floor']}-name floor on the NEW survivors ({n_pre} would on the age-window count before the removals) -> "
          + ("the bar is reachable" if lc_["traded"] >= RULES["reb"] else "the bar is UNREACHABLE: no cell can pass (a), whatever else is true")
          + f"; the reported {FLOOR_REPORTED}-name floor: {lc20['traded']} months clear it ({'the bar would be reachable there too' if lc20['traded'] >= RULES['reb'] else 'the bar would be unreachable there'}; information only)")
    mn, md, mx = lc_["new_per_rebalance"]
    sn, sd_, sx = lc_["seasoned_per_rebalance"]
    print(f"NEW names per month (survivors of every removal; min / median / max over the {lc_['rebalances']} rebalances): {mn} / {md:.0f} / {mx}; SEASONED candidates per month {sn} / {sd_:.0f} / {sx}; NEW name-months by listing cohort: "
          + ", ".join(f"{y}: {n:,} ({lc_['cohort_names'][y]} names)" for y, n in lc_["cohort_name_months"].items()))
    by = defaultdict(list)
    for r_ in Lr.recs:
        by[int(W.days[r_.f].year)].append(r_)
    print(f"  by fill year (rebalances: NEW min / median / max; age-window names before the removals median; SEASONED median; under the registered {SPEC['floor']}-name floor / under the reported {FLOOR_REPORTED}-name floor): " + "; ".join(
        f"{y}: {len(v)}: {min(q.n_new for q in v)} / {np.median([q.n_new for q in v]):.0f} / {max(q.n_new for q in v)}; {np.median([q.newage for q in v]):.0f}; {np.median([q.n_seas for q in v]):.0f}; {sum(not q.traded for q in v)} / {sum(q.n_new < FLOOR_REPORTED for q in v)}" for y, v in sorted(by.items())))
    print_counts("registered (a flag inside the hold removes the name)", Lr.cnt)
    print_counts("look-ahead (names flagged inside the hold stay, on their naive raw path)", Lk.cnt)
    print_exclusions("registered", Lr.cnt)
    print(f"TBIS flags: {len(tbis):,} symbol-days listed before the cut, {full_match:,} match a session and a cached name, {W.tbis_rows[1]:,} a name that is ever in the universe; every listed row is a flag")
    pa, pr = W.es_cov["adj_prints"], W.es_cov["raw_prints"]
    e = W.es
    print(f"ES prints on the {W.T:,} stock sessions: 09:35 price {int(np.isfinite(e.e5).sum()):,}, 16:00 adj {int(np.isfinite(e.c16a).sum()):,}, 16:00 raw {int(np.isfinite(e.c16r).sum()):,}; fallback bars: "
          f"{int((pa['close_hm'] != pa['last']).sum())} closes (adj master), {int((pr['close_hm'] != pr['last']).sum())} closes (raw master); ES return defined on {int(np.isfinite(e.ret).sum()):,} sessions")
    print(M17.es_report(W, WFN, PRE_END)[0])
    print(f"cache manifest sha256: {manifest_sha()}")
    pm = peak_mb()
    print(f"dryload took {time.time() - t0:.0f}s" + (f", peak memory {pm:,.0f} MB" if pm else ""))
    return {"listing_all": la, "listing_universe": lw, "leg": lc_, "leg_reported_floor": lc20}


# ------------------------------------------------------------------ Stage A
def pick_candidate(passing):
    """CHOICE (the prereg names no tie-break between two passing cells; A2 is only a report): cell E is the PRIMARY (addendum 1 [N2]), so when both cells pass E goes to Stage B and M is reported; M goes only when E does not pass"""
    for c in CELLS:
        if c in passing:
            return c
    return None


def stage_a_flow(cells):
    """Stage A's bookkeeping, pure: passing = the cells that clear (a)-(e) (their checks, the null included) in the REGISTERED reading; the candidate = pick_candidate(passing). (f) is never decided here: every passing cell 'awaits the hand audit'"""
    passing = [c for c in CELLS if cells[c].get("PASS") is True]
    return passing, pick_candidate(passing)


def stage_a():
    if os.path.exists(os.path.join(OUT, READ_FLAG)):                                         # CHOICE: once the lockbox has been read Stage A is frozen (a re-run could change the cell or c after the fact)
        refuse(f"Stage A refused: Stage B has already read the lockbox - Stage A is frozen ({READ_FLAG})")
    pok = prereg_ok()
    cal, winfo = M17.wide_load(S.LB0)                                                        # refuses (nothing computed) when the wide calendar is not on file / not registered / not the registered file
    extra, einfo = cal_extra(S.LB0)
    B, legs_meta = A13.load_463()                                                            # the book first: cheap, and a book that does not reproduce stops everything
    bk, dd, S12 = book_checks(B)
    print(f"BOOK #463 WF check (must be {BOOK_WF[0]} / {BOOK_WF[1]}): ROC@30k {bk['roc']:.2f} Sortino {bk['sortino']:.3f}; deepest drawdown ${dd['deepest']:,.0f} (must be ${DEEPEST_WF:,.0f}), "
          f"{dd['episodes']} qualifying episodes, {dd['days']} DD days, {dd['weeks']} DD weeks, by year {dd['by_year']}, the 2020-03-03 .. 03-27 episode {'found' if dd['episode_2020'] else 'NOT FOUND'}")
    if CHECK_BOOK and not (bk["ok"] and dd["ok"]):
        refuse("Stage A refused: the #463 records do not reproduce the registered WF numbers / drawdown structure (the prereg's [T5] facts) - fix the input first (nothing computed)")
    ref = DV.ref_load(B, check_facts=CHECK_BOOK)                                             # [X1] RESMOM's WF line -> the REFERENCE book: refuses (nothing computed) unless the file is the registered one and the reference reproduces its registered numbers
    DV.print_reference(ref)
    msha = manifest_sha()
    print(f"SIPORB cache manifest sha256: {msha} (registered: {D15.MANIFEST_PREFIX}...)")
    if CHECK_BOOK and not (msha and msha.startswith(D15.MANIFEST_PREFIX)):
        refuse("Stage A refused: the SIPORB cache manifest is missing or is not the registered photograph of the vendor (a re-pull must never be mixed in) - nothing computed")
    t0 = time.time()
    D = M17.load_data(S.LB0)                                                                 # every input is cut to dates < 2025-06-30 inside this call, before anything is computed
    tbis = D15.load_tbis(S.LB0)
    es_frames, es_meta = D15.load_es(S.LB0)
    audit = read_audit()
    W = M17.build_world(D, S.LB0, es_frames, tbis, cal)
    D15.release(D)
    cut_checks(W, cal, extra, S.LB0)
    if CHECK_BOOK and W.days[0] != FIRST_SESSION:
        refuse(f"Stage A refused: the cache's first session is {W.days[0]:%Y-%m-%d}, not the registered {FIRST_SESSION:%Y-%m-%d} - listings would be dated from the wrong session (nothing computed)")
    wf = (W.days >= WFN) & (W.days <= PRE_END)
    print(f"world ready ({time.time() - t0:.0f}s): {int(wf.sum()):,} WF sessions, {W.S:,} names ever in the universe; ES masters {es_meta['raw']['filename']} / {es_meta['adj']['filename']}", flush=True)
    es_txt, es_rec = M17.es_report(W, WFN, PRE_END)
    print(es_txt)
    M17.print_wide(W.ca)
    ctx = make_ctx(W, extra)
    lw = listing_counts(W.days, ctx.li)
    print("LISTING SESSIONS [N4] (the names ever in the universe; by listing year: dated / accepted / failed [N4] / unverifiable): present at the first session " + f"{lw['present_at_first_session']:,}; " + "; ".join(
        f"{y}: {v['dated']:,} / {v['accepted']:,} / {v['failed']:,} / {v['unverifiable']:,}" for y, v in lw["by_year"].items()))
    st0 = M17.calendar_start(W.ca["file"]["manifest"])                                       # (wide_load's gate guarantees a readable start)
    ncc = nc_coverage(W, st0)
    print(f"calendar coverage: the calendar starts {st0:%Y-%m-%d}; the 24-month name-change window of {len(ncc)} WF ranks starts before it ({', '.join(f'{d:%Y-%m-%d}' for d, _a in ncc) if ncc else 'none'}): a reported row leaves them out")
    e0 = einfo["name_change"]["earliest"]
    ncc2 = nc_coverage(W, TS(e0)) if e0 is not None else []
    print(f"calendar name-change coverage: the earliest name-change row on the calendar is dated {e0}; the 24-month name-change window of {len(ncc2)} of the {len(wf_ranks(W))} WF ranks starts before it (the exclusion sees only part of such a window; a reported row leaves them out)")
    out = {"prereg_sha256_lf": PREREG_SHA, "prereg_verified": pok["verified"], "prereg_committed": pok["committed"], **stamp(), "judged": False, "stageA": None, "candidate": None, "pending_hand_audit": None, "book_check": bk, "dd_structure": dd,
           "reference": DV.ref_record(ref), "manifest_sha256": msha, "es_return": es_rec, "wide_calendar": W.ca, "calendar_tables": einfo, "calendar_placed": ctx.cal_counts, "listing": lw, "name_change_window_before_the_calendar": [f"{d:%Y-%m-%d}" for d, _a in ncc],
           "name_change_window_before_the_first_name_change_row": [f"{d:%Y-%m-%d}" for d, _a in ncc2]}
    aud_n = apply_audit(W, audit)
    asha = file_sha(os.path.join(OUT, "newissue_audit.csv"))
    print("audit file: " + ("none yet" if audit is None else f"{aud_n['rows']} rows ({aud_n['keep']} keep, {aud_n['data_event']} data_event: removed from the cells AND the null)"))
    rows = A13.book_rows(B, W)
    SN = restrict_stretch(S12, B.raw, B.index, WFN, PRE_END)                                 # the map's drawdown days from 2018-02 on: #463's (the standalone map point) ...
    SRN = restrict_stretch(ref.S, ref.raw, B.index, WFN, PRE_END)                            # ... and the REFERENCE book's (MANAGER #70's gate basis [X1], for the cell and for its null)
    t1 = time.time()
    resR, objR = evaluate(W, ctx, B, SN, ref, SRN, rows, "remove", NREP, 0, full=True)
    print(f"registered reading done ({time.time() - t1:.0f}s: the leg, both cells, the stress and borrow rows and {NREP} null draws)", flush=True)
    unused = M17.unused_audit_rows(W, audit)
    if unused:
        print(f"  NOTE: {len(unused)} audit data_event row(s) removed nothing (the name was not in that fill session's NEW or SEASONED sets): {unused[:5]}")
    t1 = time.time()
    with spec(floor=FLOOR_REPORTED):                                                         # [N7] the same reading under the 20-name floor: REPORTED beside the registered one (its own leg, its own null stream vcode 2), never a pass route
        res20, obj20 = evaluate(W, ctx, B, SN, ref, SRN, rows, "remove", NREP, 2, full=True)
    del obj20
    print(f"reported {FLOOR_REPORTED}-name-floor reading [N7] done ({time.time() - t1:.0f}s: its own leg, both cells, the stress and borrow rows and {NREP} null draws of its own)", flush=True)
    t1 = time.time()
    resK, objK = evaluate(W, ctx, B, SN, ref, SRN, rows, "naive", NREP, 1, full=False)
    print(f"look-ahead reading (hold-flagged positions kept at naive raw P&L) done ({time.time() - t1:.0f}s)", flush=True)
    t1 = time.time()
    var = variant_rows(W, ctx, B, rows, drop=tuple(d for d, _a in ncc), drop2=(tuple(d for d, _a in ncc2) if {d for d, _a in ncc2} != {d for d, _a in ncc} else ()))
    print(f"variant rows done ({time.time() - t1:.0f}s)", flush=True)
    rep, cands = reports(W, ctx, B, S12, ref, rows, objR, resR["cells"], tbis, D15.asset_status(), legs_meta)
    cells = resR["cells"]
    ast = audit_status(cands, audit)
    for cell in CELLS:
        cells[cell]["audit"] = ast[cell]
    passing, cand = stage_a_flow(cells)
    flips = {c: bool(resK["cells"][c]["PASS"]) != bool(cells[c]["PASS"]) for c in CELLS}
    os.makedirs(OUT, exist_ok=True)
    pd.DataFrame([x for c in CELLS for x in cands[c]]).to_csv(os.path.join(OUT, "newissue_audit_candidates.csv"), index=False)
    print(f"WF {WFN:%Y-%m-%d} -> {PRE_END:%Y-%m-%d} ({int(wf.sum()):,} sessions) - the REGISTERED reading (a hygiene flag inside the hold removes the position); positions are counted by EXIT date")
    print_cells(resR, ast)
    lcR, lc20 = leg_counts(W, objR.legs), leg_counts(W, objR.legs, FLOOR_REPORTED)
    print(traded_text(lcR, lc20))
    print(f"  {LOW_POWER}")
    print(f"REPORTED {FLOOR_REPORTED}-NAME-FLOOR READING [N7] (the same WF and the same code; a month trades only with >= {FLOOR_REPORTED} NEW names; its own leg and null stream; NEVER a pass route):")
    print_cells(res20, None, f" @{FLOOR_REPORTED}", True)
    pass20 = [c for c in CELLS if res20["cells"][c].get("PASS") is True]
    print(f"  under the {FLOOR_REPORTED}-name floor the cells clearing (a)-(e): {pass20 if pass20 else 'none'} (information only: the verdict is the registered {SPEC['floor']}-name floor's)")
    print_floors(resR, res20)
    print(f"  look-ahead reading (positions with a flag INSIDE the hold kept at naive raw P&L) [O3]: null ROC p95 {resK['null']['roc_max']['p95']:.1f}")
    for cell in CELLS:
        k = resK["cells"][cell]
        print(f"    {cell}: {row_body(k)} | Stage A {'PASS' if k['PASS'] else 'FAIL'}" + ("   *** FLIPS the registered verdict ***" if flips[cell] else "   (same verdict)"))
    print_counts("L (registered)", objR.legs.cnt)
    print_counts("L (look-ahead)", objK.legs.cnt)
    print_exclusions("L (registered)", objR.legs.cnt)
    print_reports(rep, cells)
    print_diagnostics(resR, rep, ref, var, res20)
    print(f"  audit candidates (the {AUDIT_N} largest name-month gains per cell, with the listing session, its [N4] count, the calendar's rows, the split factor, TBIS and the asset status) -> {os.path.join(OUT, 'newissue_audit_candidates.csv')}; the hand audit is the lead's "
          "(a data event found: a row symbol, date, cell, data_event in newissue_audit.csv and run stage_a again); audit rows found per list: " + ", ".join(f"{k} {v['audited']}/{v['listed']}" for k, v in ast.items()))
    judged = True
    out.update({"judged": judged, "pending_hand_audit": passing, "audit_sha256": asha, "audit": aud_n, "audit_status": ast, "audit_data_events_without_effect": unused,
                "stageA": {"cells": cells, "null": resR["null"], "registered_pass_cells": passing, "floor": SPEC["floor"]},
                "floor_reported": {"floor": FLOOR_REPORTED, "note": "[N7] the same reading under the 20-name floor: REPORTED beside the registered one (its own leg and null stream), never a pass route", "cells": res20["cells"], "null": res20["null"],
                                   "cells_clearing_a_to_e_information_only": pass20},
                "traded_months": {"registered": lcR, "reported": lc20}, "low_power_flag": LOW_POWER,
                "candidate": ({"cell": cand, "c": cells[cand]["A2"]["c"], "std_book": cells[cand]["A2"]["std_book"], "std_cell": cells[cand]["A2"]["std_cell"], "window": cells[cand]["A2"]["window"], "a2_book_roc": cells[cand]["A2"]["roc"],
                               "a2_reference_roc": cells[cand]["A2"]["reference"]["roc"], "a2_book_usd_per_year": cells[cand]["A2"]["usd_per_year"], "a2_reference_usd_per_year": cells[cand]["A2"]["reference"]["usd_per_year"], "incremental_pass": cells[cand]["A2"]["incremental_pass"], "book_shadow_line": cells[cand]["A2"]["book_shadow_line"],
                               "realised_beta": cells[cand]["realised_beta"]["beta"], "beta_credited": cells[cand]["beta_gate"]["credited"], "also_passes": [c for c in passing if c != cand]} if cand else None),
                "parity": {c: {"net": cells[c]["base"]["net"], "n_pos": cells[c]["base"]["n_pos"], "n_units": cells[c]["base"]["n_units"]} for c in CELLS},
                "look_ahead_reading": {"null": resK["null"], "cells": {c: {k: resK["cells"][c].get(k) for k in ("PASS", "base", "stress", "borrow", "seat", "seat_ref", "checks", "A2", "realised_beta", "beta_gate")} for c in CELLS}, "flips": flips},
                "variants": var, "hygiene_counts_by_year": {"registered": {y: dict(c_) for y, c_ in sorted(objR.legs.cnt.items())}, "look_ahead": {y: dict(c_) for y, c_ in sorted(objK.legs.cnt.items())}},
                "reports": rep, "es_masters": es_meta})
    dump(out, "newissue_stageA.json")
    for c in passing:
        a2 = cells[c]["A2"]
        print(f"Stage A (a)-(e) pass, (f) awaits the hand audit - cell {c}; WF ROC@30k {cells[c]['base']['roc']:.1f} (${cells[c]['base']['usd_per_year']:,.0f} a year); [N2] {beta_text(cells[c])}; A2 (a report) [X1]: {a2_text(a2)}")
    if passing:
        print(f"NEWISSUE Stage A: (a)-(e) pass for {passing}; (f) AWAITS THE HAND AUDIT of the {AUDIT_N} largest contributors (the harness never decides it); candidate {cand}"
              + (f" (the PRIMARY cell E, addendum 1 [N2]; M {'also passes' if 'M' in passing else 'does not'})" if cand == "E" else " (E does not pass)") + f". Stage B needs the lead's go-flag {GO_FLAG} (written after the hand audit, on the stock families' one sealed-year day) - "
              "and a recent listing can be impossible to borrow in size at any price: even a pass is a paper result until a broker's locate list is checked [N1]. " + LOW_POWER + ".")
    else:
        print("NEWISSUE Stage A: FAIL - no cell passes (a)-(e) (" + "; ".join(f"{c}: " + ", ".join(k for k, v in cells[c]["checks"].items() if not v) for c in CELLS) + ") - NEWISSUE r1 is dead; no other age windows or matching rules are tried; the lockbox stays sealed. " + LOW_POWER + ".")
    pm = peak_mb()
    print(f"stage_a took {time.time() - t0:.0f}s" + (f", peak memory {pm:,.0f} MB" if pm else ""))
    return out


# ------------------------------------------------------------------ Stage B: the one read (refuses unless the lead's go-flag is on file)
def book_add_would_clear(r):
    """the REPORTED comparison of the book add on the sealed year with the old sealed-year bar (#463's own LB numbers): both the ROC and the Sortino must reach theirs (inclusive); a NaN fails. Reported, never judged"""
    return bool(r["roc"] >= RULES["b_roc"] and r["sortino"] >= RULES["b_sort"])


def b_checks(leg):
    """STAGE B's pass: the LEG's standalone veto and nothing else - >= 10 monthly rebalances, net > 0, net > 0 without its top name-month. It takes no book number: the book add on the lockbox year is a report, so it cannot be in this verdict. A NaN fails every comparison it enters -> {check name: bool}"""
    return {f"leg monthly rebalances>={RULES['b_reb']}": bool(leg["n_units"] >= RULES["b_reb"]), "leg net>0": bool(leg["net"] > 0), "leg net>0 without its top name-month": bool(leg["net_ex_top_pos"] > 0)}


def stage_b():
    """STAGE B (LB, once, on the stock families' one sealed-year day): REFUSES unless the lead's go-flag newissue_stageB_GO.flag is on file (the lead writes it after the hand audit (f) and only on that day; CHOICE: its EXISTENCE is the sign-off - its text is stored with the read and never parsed) and a Stage A
    candidate is on file. The sealed year is the LEG's standalone veto: >= 10 monthly rebalances, net > 0, net > 0 without its top name-month. The book add (#463 + c x the cell at Stage A's frozen c; RESMOM's line file has no sealed-year rows, so the REFERENCE book cannot be rebuilt there) is computed, printed
    and stored as book_add_reported - NEVER part of the pass. Every refusal is before the read flag; the flag is written (exclusively) only after every load, every check and the whole result are in hand"""
    go, flag = os.path.join(OUT, GO_FLAG), os.path.join(OUT, READ_FLAG)
    if not os.path.exists(go):
        refuse(f"Stage B refused: the lead's go-flag {GO_FLAG} is not on file - the hand audit (f) and the sealed-year day are the lead's call; the lockbox stays sealed (nothing computed, lockbox NOT read)")
    if os.path.exists(flag):
        refuse(f"Stage B refused: the lockbox was already read once ({READ_FLAG})")
    pa = os.path.join(OUT, "newissue_stageA.json")
    sa = json.load(open(pa)) if os.path.exists(pa) else {}
    cand = sa.get("candidate")
    ok_a = isinstance(cand, dict) and sa.get("judged") is True and cand.get("cell") in ((sa.get("stageA") or {}).get("registered_pass_cells") or [])
    if not ok_a:
        refuse("Stage B refused: no Stage A candidate (a cell that passes (a)-(e)) is on file - the lockbox stays sealed.")
    prereg_ok()
    if sa.get("prereg_sha256_lf") != PREREG_SHA:
        refuse("Stage B refused: Stage A ran under another pre-registration (lockbox NOT read)")
    bad = [k for k, v in stamp().items() if sa.get(k) != v]
    if bad:
        refuse(f"Stage B refused: Stage A was written by a different harness version / early-close list ({', '.join(bad)} differs or is missing) - run stage_a again (lockbox NOT read)")
    if sa.get("audit_sha256") != file_sha(os.path.join(OUT, "newissue_audit.csv")):
        refuse("Stage B refused: newissue_audit.csv is not the file Stage A ran with (it changed, or went missing) - run stage_a again (lockbox NOT read)")
    cell = cand["cell"]
    try:
        c = float(cand["c"])
    except (TypeError, ValueError):
        c = float("nan")
    if cell not in CELLS or not (math.isfinite(c) and c > 0):                                  # c is a volatility ratio: any positive number is a frozen size, but NaN / 0 / missing is a broken file
        refuse(f"Stage B refused: the frozen cell {cand.get('cell')} / size c {cand.get('c')} is not one of {CELLS} / a positive number (lockbox NOT read)")
    go_text = open(go).read()[:500]
    B, legs_meta = A13.load_463()                                                              # every input is loaded and checked BEFORE the flag: a bad file cannot burn the lockbox
    bk = A13.book_check(B, LB0, LB1, BOOK_LB)
    print(f"BOOK #463 LB check (must be {BOOK_LB[0]} / {BOOK_LB[1]}): ROC@30k {bk['roc']:.2f} Sortino {bk['sortino']:.3f}")
    if CHECK_BOOK and not bk["ok"]:
        refuse("Stage B refused: the #463 records do not reproduce its LB numbers - settle the end-date convention first (lockbox NOT read)")
    msha = manifest_sha()
    if CHECK_BOOK and not (msha and msha.startswith(D15.MANIFEST_PREFIX) and msha == sa.get("manifest_sha256")):
        refuse("Stage B refused: the SIPORB cache manifest is not the one Stage A ran on (a re-pull must never be mixed in) - lockbox NOT read")
    cal, winfo = M17.wide_load(S.END)                                                          # the same registered calendar, cut at the lockbox's end
    extra, einfo = cal_extra(S.END)
    D = M17.load_data(S.END)
    tbis = D15.load_tbis(S.END)
    es_frames, es_meta = D15.load_es(S.END)
    audit = read_audit()
    W = M17.build_world(D, S.END, es_frames, tbis, cal)
    D15.release(D)
    cut_checks(W, cal, extra, S.END)
    ctx = make_ctx(W, extra)
    apply_audit(W, audit)
    rows = A13.book_rows(B, W)
    hole_txt, hole_rec = M17.es_report(W, LB0, LB1)                                            # the ES holes that reach the lockbox: printed and stored with the read
    Lw = ni_build(W, ctx, WFN, PRE_END, "remove")                                              # Stage A's WF numbers (and the frozen c) must reproduce on Stage B's data (a cache or code drift stops it BEFORE the read)
    for cc in CELLS:
        run = cell_run(W, Lw, cc, cfg_of())
        st = stat_of(B, rows, run, WFN, PRE_END)
        ref_ = sa["parity"][cc]
        print(f"WF re-read on Stage B's data: {cc} name-months {st[0]['n_pos']:,} (Stage A {ref_['n_pos']:,}), net ${st[0]['net']:,.0f} (Stage A ${ref_['net']:,.0f})")
        if st[0]["n_pos"] != ref_["n_pos"] or st[0]["n_units"] != ref_["n_units"] or abs(st[0]["net"] - ref_["net"]) > max(1.0, 1e-6 * abs(ref_["net"])):
            refuse(f"Stage B refused: the WF numbers of {cc} do not reproduce on Stage B's data - the cache or the code changed since Stage A (lockbox NOT read)")
        if cc == cell:
            c2 = plain_a2(B, st[1])["c"]
            print(f"  frozen size {cell}: c x{c:.6g} (Stage A) vs x{c2:.6g} recomputed from {A2_WIN[0]:%Y-%m-%d} .. {A2_WIN[1]:%Y-%m-%d} on Stage B's data")
            if not (math.isfinite(c2) and abs(c2 - c) <= 1e-9 * c):
                refuse(f"Stage B refused: the volatility-set size c of {cell} does not reproduce on Stage B's data - the cache or the code changed since Stage A (lockbox NOT read)")
    del Lw
    L = ni_build(W, ctx, LB0, LB1, "remove")                                                   # CHOICE (r15's order): the whole LB result is computed, nothing shown, BEFORE the flag
    run = cell_run(W, L, cell, cfg_of())
    leg, xB, cB = stat_of(B, rows, run, LB0, LB1)
    r = D15.book_at(B, xB, c, LB0, LB1)                                                        # the book add at the FROZEN c - c is never re-set on the sealed year
    yrs_lb = stretch_years(B, LB0, LB1)
    nan_ = float("nan")
    r["usd_per_year"] = usd_per_year(r["net"], yrs_lb)                                         # [N10] dollars a year (net / years) beside every ROC @ $30k of the book add: the book add, #463 alone on the same year
    kk = B.mask(LB0, LB1)
    a463 = R11.stats(np.asarray(B.raw, float)[kk], B.index[kk]) or {}
    alone = {"roc": a463.get("roc", nan_), "sortino": a463.get("sort", nan_), "net": a463.get("net", nan_), "usd_per_year": usd_per_year(a463.get("net", nan_), yrs_lb)}
    with spec(floor=FLOOR_REPORTED):                                                           # [N7] the sealed year's leg under the 20-name floor too: REPORTED beside the registered one, never a pass route (computed here, before the flag, like the rest)
        L20 = ni_build(W, ctx, LB0, LB1, "remove")
    leg20, xB20, _cB20 = stat_of(B, rows, cell_run(W, L20, cell, cfg_of()), LB0, LB1)
    r20 = D15.book_at(B, xB20, c, LB0, LB1)
    r20["usd_per_year"] = usd_per_year(r20["net"], yrs_lb)
    would = book_add_would_clear(r)                                                            # the old sealed-year bar (#463's own LB numbers, 155.54 / 4.150): reported, never judged
    chk = b_checks(leg)
    ok = all(chk.values())                                                                     # the pass is the LEG's veto - the book add below is a report and is not in this line
    add = {"c": c, "roc": r["roc"], "sortino": r["sortino"], "net": r["net"], "max_dd": r["max_dd"], "usd_per_year": r["usd_per_year"], "years": yrs_lb, "reference": {"roc": RULES["b_roc"], "sortino": RULES["b_sort"]}, "reference_463_alone": alone, "would_have_cleared": would,
           "reported_20_floor": {"floor": FLOOR_REPORTED, "roc": r20["roc"], "sortino": r20["sortino"], "net": r20["net"], "usd_per_year": r20["usd_per_year"], "max_dd": r20["max_dd"]},
           "note": "reported, never a pass (MANAGER #48): the forward record decides any book add (owner call); the plain #463 + c x cell - the REFERENCE book has no sealed-year line"}
    cnt = {y: dict(v) for y, v in sorted(L.cnt.items())}
    text = json.dumps({"cell": cell, "c": c, "go_flag": go_text, "book_check": bk, "es_masters": es_meta, "leg": leg, "leg_reported_floor": {"floor": FLOOR_REPORTED, "leg": leg20}, "low_power_flag": LOW_POWER, "checks": chk, "pass": bool(ok), "book_add_reported": add, "es_return_lb": hole_rec, "wide_calendar": W.ca,
                       "hygiene_counts_by_year": cnt, "top_name_months": ni_candidate_rows(W, ctx, L, cell, run, tbis, D15.asset_status(), 20), **stamp(), "prereg_sha256_lf": PREREG_SHA}, indent=1, default=R11.js)
    buf = io.StringIO()                                                                        # the whole printout is built here, before the flag: a formatting error cannot burn the lockbox
    with contextlib.redirect_stdout(buf):
        print("Stage B (lockbox, read once) - the sealed year is the LEG's standalone veto")
        print(f"  {cell}: name-months {leg['n_pos']:,}, monthly rebalances {leg['n_units']:,}, net ${leg['net']:,.0f} (${leg['usd_per_year']:,.0f} a year), ROC@30k {leg['roc']:.1f}, Sortino {leg['sortino']:.2f}; its top name-month ${leg['top_pos']:,.0f}, net without it ${leg['net_ex_top_pos']:,.0f}")
        print(f"  {cell} @{FLOOR_REPORTED} (the REPORTED {FLOOR_REPORTED}-name floor [N7], never a pass route): name-months {leg20['n_pos']:,}, monthly rebalances {leg20['n_units']:,}, net ${leg20['net']:,.0f} (${leg20['usd_per_year']:,.0f} a year), ROC@30k {leg20['roc']:.1f}, Sortino {leg20['sortino']:.2f}")
        print("  " + hole_txt)
        print("  Stage B checks: " + ", ".join(k + (" ok" if v else " FAIL") for k, v in chk.items()) + f" -> {'PASS' if ok else 'FAIL'}")
        print(f"  book add, REPORTED and never part of the pass: #463 + {cell} x{c:.4g} (frozen): LB ROC@30k {r['roc']:.2f} Sortino {r['sortino']:.3f} net ${r['net']:,.0f} (${r['usd_per_year']:,.0f} a year) -> would "
              f"{'have' if would else 'NOT have'} cleared {RULES['b_roc']:g} / {RULES['b_sort']:g}; #463 alone on the sealed year: ROC@30k {alone['roc']:.2f} (${alone['usd_per_year']:,.0f} a year); under the reported {FLOOR_REPORTED}-name floor the book add: "
              f"ROC@30k {r20['roc']:.2f} Sortino {r20['sortino']:.3f} (${r20['usd_per_year']:,.0f} a year)")
        print("NEWISSUE Stage B: " + ("PASS - the leg survives its sealed year: it goes to a computed no-order FORWARD SHADOW (Stage C) with its own bar, logged by research id; the book add above is a report - "
                                      "the forward record decides any book add, and opening any account is the owner's decision (owner call); a broker's locate list must be checked first [N1]." if ok else
                                      "FAIL - the leg is vetoed by its sealed year: NEWISSUE r1 is dead; ledger + memory.") + " " + LOW_POWER + ".")
    with open(flag, "x") as f:                                                                 # exclusive create: the one read starts here - what is left is two writes and a print
        f.write(pd.Timestamp.now().isoformat())
    with open(os.path.join(OUT, "newissue_stageB.json"), "w") as f:
        f.write(text)
    print(buf.getvalue().rstrip())
    pm = peak_mb()
    if pm:
        print(f"peak memory {pm:,.0f} MB")
    return ok


# ------------------------------------------------------------------ test support: hand-made worlds, and plain-python recounts of the listing sessions, the NEW / SEASONED sets, the match, the hedge ratio and every position's path (independent of the vectorised code)
def close(a, b, tol=1e-9):
    return D15.close(a, b, tol)


def usd(a, b, tol=1e-7):
    """two dollar series equal to the cent and far below it"""
    return bool(np.allclose(np.asarray(a, float), np.asarray(b, float), rtol=tol, atol=1e-7, equal_nan=True))


def quiet():
    return contextlib.redirect_stdout(io.StringIO())


def refused(fn, *frag):
    """the call must refuse (SystemExit) with every fragment in the message; returns the message"""
    try:
        fn()
    except SystemExit as e:
        msg = str(e)
        assert all(f in msg for f in frag), (msg, frag)
        return msg
    raise AssertionError(f"expected a refusal containing {frag}")


SMALL = dict(new_lo=15, new_hi=45, seas_months=3, nc_months=2, floor=4, beta_win=30, beta_min=28, hold_win=60, min_n=55, pre=5, old=29)       # the registered windows shrunk to a world of a few hundred sessions (the constants themselves are asserted by t_constants)


def mk_extra(spin=(), chg=()):
    """the calendar's two tables as cal_extra hands them back: spin = [(new symbol, parent, 'YYYY-MM-DD')], chg = [(old symbol, new symbol, 'YYYY-MM-DD')]"""
    return SimpleNamespace(spin=pd.DataFrame({"sym": pd.Series([x[0] for x in spin], dtype=str), "parent": pd.Series([x[1] for x in spin], dtype=str), "ev": pd.to_datetime(pd.Series([x[2] for x in spin], dtype=str))}),
                           chg=pd.DataFrame({"old": pd.Series([x[0] for x in chg], dtype=str), "new": pd.Series([x[1] for x in chg], dtype=str), "ev": pd.to_datetime(pd.Series([x[2] for x in chg], dtype=str))}))


def ni_world(cols, T=330, seed=1, start="2024-01-01", spin=(), chg=(), flags=None, es_nan=(), dr=None, es_vol=0.006, spn=None):
    """a r15 World on hand-made arrays for the age logic. cols = [dict(sym, first, last, beta, drift, idio, p0, shares, dvol, holes, zero_vol, ret)] (sorted by symbol: the World's names are in ascending symbol order): bars (raw close = split-safe close, the open = the last close,
    no gap) from row `first` (default 0) to row `last` (default the end) except the rows in `holes`; the split-safe daily return = drift + beta x ES + idio x noise (or the array `ret`); the volume = `shares` a session (or the dollar volume `dvol` over the close), 0 on `zero_vol` rows. ES: a
    random walk (the 16:00 print, unadjusted 1500 x ..., roll-corrected + 5000), the 09:35 print 30% of the way from the prior 16:00 print to today's (both bases); es_nan = sessions with no ES print. spin = [(new symbol, parent, date)], chg = [(old, new, date)] -> the calendar's two tables
    (the ctx is made from them); flags = {'gap' | 'tbis' | 'chg': [(sym, row)]} plant hygiene flags; dr = {(sym, row): per-share cash} dividends; spn = [(sym, row)] spin-off / stock-dividend ex-date sessions of the PARENT -> SimpleNamespace(W, ctx, extra, days)"""
    cols = sorted(cols, key=lambda c: c["sym"])
    S_ = len(cols)
    days = pd.bdate_range(start, periods=T)
    rng = np.random.default_rng(seed)
    es_r = 1500.0 * np.cumprod(1.0 + np.r_[0.0, rng.normal(0.0003, es_vol, T - 1)])
    es_a = es_r + 5000.0
    for t in es_nan:
        es_r[t] = es_a[t] = np.nan
    mret = np.full(T, np.nan)
    with np.errstate(invalid="ignore"):
        mret[1:] = (es_a[1:] - es_a[:-1]) / es_r[:-1]
    e5a, e5r = es_a.copy(), es_r.copy()
    e5a[1:] = es_a[:-1] + 0.3 * (es_a[1:] - es_a[:-1])
    e5r[1:] = es_r[:-1] + 0.3 * (es_r[1:] - es_r[:-1])
    Cl, Od, Vv = (np.full((T, S_), np.nan) for _ in range(3))
    for j, c in enumerate(cols):
        first, last = c.get("first", 0), c.get("last") if c.get("last") is not None else T - 1
        r_ = np.random.default_rng([seed, j + 7])
        noise = r_.standard_normal(T) * c.get("idio", 0.01)
        ret = c.get("ret")
        ret = c.get("drift", 0.0) + c.get("beta", 1.0) * np.nan_to_num(mret) + noise if ret is None else np.asarray(ret, float)
        p = c.get("p0", 50.0)
        prev = None
        for t in range(first, last + 1):
            if t in c.get("holes", ()):
                continue
            p = p if t == first else p * (1.0 + ret[t])
            Cl[t, j] = p
            Od[t, j] = p if prev is None else prev
            if c.get("dvol") is not None:
                Vv[t, j] = c["dvol"] / p
            else:
                Vv[t, j] = c.get("shares", 3e6)
            if t in c.get("zero_vol", ()):
                Vv[t, j] = 0.0
            prev = p
    syms = np.array([c["sym"] for c in cols])
    zero = lambda: np.zeros((T, S_), bool)
    fl = {k: zero() for k in ("gap", "tbis", "chg")}
    for k, lst in (flags or {}).items():
        for sym, row_ in lst:
            fl[k][row_, list(syms).index(sym)] = True
    U = np.isfinite(Od) & np.isfinite(Cl)
    es = SimpleNamespace(e5=e5a, e5r=e5r, c16a=es_a, c16r=es_r, ret=mret, gap=np.full(T, np.nan), k=np.ones(T))
    nan = np.full((T, S_), np.nan)
    W = D15.World(days, syms, Od, Cl, Vv, np.ones((T, S_)), U, fl["chg"], fl["gap"], fl["tbis"], nan, nan, es)
    Dr = None
    if dr:
        Dr = np.zeros((T, S_))
        for (sym, row_), amt in dr.items():
            Dr[row_, list(syms).index(sym)] += amt
    Sp = None
    if spn:
        Sp = np.zeros((T, S_), bool)
        for sym, row_ in spn:
            Sp[row_, list(syms).index(sym)] = True
    M17.with_dividends(W, Dr, Sp)
    extra = mk_extra(spin, chg)
    ctx = make_ctx(W, extra)
    return SimpleNamespace(W=W, ctx=ctx, extra=extra, days=days, cols=cols)


def fx_of(days, r):
    """(fill row, exit row) of the rebalance ranked at row r"""
    r_all, f_all, x_all = M17.rm_schedule(days)
    q = r_all.tolist().index(r)
    return int(f_all[q]), int(x_all[q])


_FOA = {}


def first_on_or_after(days, d):
    """plain python: the first session row on / after a date (len(days) when none); memoised per calendar (a loop over the sessions, once per date)"""
    key = (days[0], days[-1], len(days), pd.Timestamp(d))
    if key not in _FOA:
        _FOA[key] = next((t for t, x in enumerate(days) if x >= pd.Timestamp(d)), len(days))
    return _FOA[key]


def brute_listing(W, sp=None):
    """plain python recount of every name's listing status: first bar, the dated listing row, the status, the sessions of the 20 after it with a close and a positive volume"""
    sp = sp or SPEC
    T, k = W.T, sp["n4_next"]
    out = []
    for j in range(W.S):
        first = next((t for t in range(T) if math.isfinite(W.Cl[t, j])), -1)
        if first < 0:
            out.append((-1, -1, ST_NONE, 0))
            continue
        n = sum(1 for t in range(first + 1, min(first + k, T - 1) + 1) if math.isfinite(W.Cl[t, j]) and math.isfinite(W.Vv[t, j]) and W.Vv[t, j] > 0)
        if first == 0:
            out.append((0, -1, ST_START, n))
        elif first + k > T - 1:
            out.append((first, first, ST_LATE, n))
        else:
            out.append((first, first, ST_OK if n >= sp["n4_min"] else ST_FAIL, n))
    return out


def brute_sets(W, spin, chg, r, f, x, post_mode, win=None, incl=(False, False), sp=None):
    """plain python recount of one rebalance's NEW and SEASONED sets (symbols): the listing statuses, the spinco / name-change tests by the calendar's DATES against the 24-month window, the NEW age window, the SEASONED rules, then every removal by loops over the sessions: no fill session open, hygiene
    reasons in r-pre .. r (all four) and r-old .. r-pre-1 (the last three), the audit, hygiene (and a spin-off / stock-dividend ex-date) inside the hold in the registered reading, and the SEASONED history rule (the own returns and the ES pairs of the last hold_win sessions)"""
    sp = sp or SPEC
    lo_n, hi_n = (sp["new_lo"], sp["new_hi"]) if win is None else win
    days = W.days
    li = brute_listing(W, sp)
    d_r = days[r]
    a24 = first_on_or_after(days, d_r - pd.DateOffset(months=sp["nc_months"]))
    b36 = first_on_or_after(days, d_r - pd.DateOffset(months=sp["seas_months"]))
    new, seas = [], []
    for j in range(W.S):
        if not W.U[f, j]:
            continue
        sym = str(W.syms[j])
        first, L, st, _n = li[j]
        spinco = any(s_ == sym and first_on_or_after(days, d_) <= r for s_, _p, d_ in spin if first_on_or_after(days, d_) < len(days))
        nchg = any(sym in (o, n_) and a24 <= first_on_or_after(days, d_) <= r for o, n_, d_ in chg if first_on_or_after(days, d_) < len(days))
        if not math.isfinite(W.Od[f, j]):
            continue
        lo_pre = r - sp["pre"]
        bad = any(bool(W.fl[q][t, j]) for t in range(max(lo_pre, 0), r + 1) for q in range(4)) or any(bool(W.fl[q][t, j]) for t in range(max(r - sp["old"], 0), lo_pre) for q in (1, 2, 3)) or bool(W.aud1[f, j])
        post = any(bool(W.fl[q][t, j]) for t in range(r + 1, min(x, W.T - 1) + 1) for q in range(4)) or any(bool(W.SPN[t, j]) for t in range(f + 1, x + 1))
        if bad or (post and post_mode == "remove"):
            continue
        age = r - L
        if st == ST_OK and lo_n <= age <= hi_n and not (spinco and not incl[0]) and not (nchg and not incl[1]):
            new.append(sym)
        is_seas = st == ST_START or (st == ST_OK and L < b36)
        if is_seas and not nchg:
            a = r - sp["hold_win"] + 1
            n_ret = sum(1 for t in range(a, r + 1) if math.isfinite(W.Rd[t, j]))
            n_pair = sum(1 for t in range(a, r + 1) if math.isfinite(W.Rd[t, j]) and math.isfinite(W.es.ret[t]))
            if n_ret >= sp["min_n"] and n_pair >= sp["min_n"]:
                seas.append(sym)
    return new, seas


def brute_match(dv_new, dv_cand, key_new, key_cand):
    """plain python: the global greedy over EVERY (NEW, candidate) pair sorted by (distance, NEW key, candidate key) - the rule written out, no windows, no vectorisation (NaN dollar volumes are never paired)"""
    pairs = sorted((abs(dv_cand[c] - dv_new[i]), key_new[i], key_cand[c], i, c) for i in range(len(dv_new)) for c in range(len(dv_cand)) if math.isfinite(dv_new[i]) and math.isfinite(dv_cand[c]))
    out, used_i, used_c = [-1] * len(dv_new), set(), set()
    for _d, _kn, _kc, i, c in pairs:
        if i in used_i or c in used_c:
            continue
        out[i] = c
        used_i.add(i)
        used_c.add(c)
    return out


def brute_beta(W, r, cols, sp=None):
    """plain python: the OLS slope (an intercept and a slope) of the equal-weight basket's daily total return on ES's over the beta_win sessions r-beta_win+1 .. r - (slope = sum (m - mbar)(y - ybar) / sum (m - mbar)^2) over the sessions on which ES has a return and at least one name has one; NaN under beta_min pairs or without variation -> (beta, pairs)"""
    sp = sp or SPEC
    xs, ys = [], []
    for t in range(r - sp["beta_win"] + 1, r + 1):
        v = [float(W.Rd[t, j]) for j in cols if math.isfinite(W.Rd[t, j])]
        m = float(W.es.ret[t])
        if v and math.isfinite(m):
            xs.append(m)
            ys.append(sum(v) / len(v))
    n = len(xs)
    if n < sp["beta_min"]:
        return float("nan"), n
    mb, yb = sum(xs) / n, sum(ys) / n
    sxx = sum((a - mb) ** 2 for a in xs)
    if not sxx > 1e-12 * max(sum(a * a for a in xs), 1e-300):
        return float("nan"), n
    return sum((a - mb) * (b - yb) for a, b in zip(xs, ys)) / sxx, n


def brute_position(W, f, x, j, side, bps, borrow, slot=None):
    """plain python: the daily P&L (list over rows f .. x) of ONE $4,000 position in name j on the split-safe series (W.Ao / W.Ac = raw / the split factor): the entry at the open of f, the mark at every close of rows f .. x-1 (a missing close carries the last mark), the exit at the open of x (no open: the last mark,
    carried); the day's gross = side x slot x (mark - the previous mark) / the entry open; bps of the entry notional at row f and of the exit value at row x; for a short the borrow rate / 252 x the previous mark / the entry open on every row after f; a cash dividend (W.Dv = the amount over the split factor) on a
    session f < t <= x is received by a long and paid by a short, per share held (fractional shares: slot / the entry open)"""
    slot = SPEC["slot"] if slot is None else slot
    O, C = W.Ao, W.Ac
    Dv = getattr(W, "Dv", None)
    of = O[f, j]
    marks = [of]
    for t in range(f, x):
        marks.append(C[t, j] if math.isfinite(C[t, j]) else marks[-1])
    xv = O[x, j] if math.isfinite(O[x, j]) else marks[-1]
    marks.append(xv)
    out = []
    for h in range(x - f + 1):
        g = side * slot * (marks[h + 1] - marks[h]) / of
        if h == 0:
            g -= slot * bps * 1e-4
        if h == x - f:
            g -= slot * bps * 1e-4 * xv / of
        if side < 0 and h >= 1:
            g -= slot * borrow / 252.0 * marks[h] / of
        if Dv is not None and h >= 1 and math.isfinite(Dv[f + h, j]):
            g += side * slot * Dv[f + h, j] / of
        out.append(g)
    return out


def brute_es_leg(W, f, x, bps):
    """plain python: one LONG ES position per $1 of entry notional over rows f .. x: fixed contracts = $1 / the unadjusted 09:35 print of f; the day's P&L = the roll-corrected change (the 09:35 print of f to the 16:00 print of f, then each 16:00 print to the next, the last row from the 16:00 print of x-1 to the 09:35 print of x) over that level; bps of the
    notional at both ends (the exit value = the unadjusted prints' ratio). A missing 16:00 print is carried (the last one)"""
    a16 = W.esA
    out = []
    for h in range(x - f + 1):
        t = f + h
        prev = W.e5A[f] if h == 0 else a16[t - 1]
        cur = W.e5A[x] if t == x else a16[t]
        g = (cur - prev) / W.e5R[f]
        if h == 0:
            g -= bps * 1e-4
        if t == x:
            g -= bps * 1e-4 * W.e5R[x] / W.e5R[f]
        out.append(g)
    return np.array(out)


def brute_pos_c(W, f, x, j, side, bps, borrow, post_mode="remove"):
    """brute_position, or - under 'close' [HYG-S1] - the path of a position closed at the official close before its first spin-off / stock-dividend ex-date in f < e <= x (M17.brute_close_path, in $ at the slot)"""
    Sp = getattr(W, "Sp_in", None)
    ex = next((t for t in range(f + 1, x + 1) if Sp is not None and Sp[t, j]), -1) if post_mode == "close" else -1
    if ex >= 0:
        return SPEC["slot"] * np.array(M17.brute_close_path(W, f, x, j, side, ex, bps=bps, borrow=(borrow, None))[0])
    return np.array(brute_position(W, f, x, j, side, bps, borrow))


def brute_cell_series(W, L, cell, bps=COST_BPS, borrow=BORROW, side=0, es_bps=ES_BPS, post_mode="remove"):
    """plain python: a cell's daily $ series on the stock sessions and its position count - every NEW short (and its matched long / its share of the beta-sized ES hedge) as brute_position / brute_es_leg book it (post_mode 'close' [HYG-S1]: a stock position with a spin-off / stock-dividend ex-date
    in the hold is cut at the close before it, brute_pos_c; the ES hedge share runs to the exit), the match recounted by the all-pairs greedy; side -1 / +1 = one side alone"""
    x, n, slot = np.zeros(W.T), 0, SPEC["slot"]
    for q in L.recs:
        if not traded(q, cell):
            continue
        es = brute_es_leg(W, q.f, q.x, es_bps)
        mt = brute_match([brute_dv(W, q.r, int(c_)) for c_ in q.new], [brute_dv(W, q.r, int(c_)) for c_ in q.seas], q.new.tolist(), q.seas.tolist()) if cell == "M" else None
        for i, col in enumerate(q.new):
            if mt is not None and mt[i] < 0:
                continue
            s_ = brute_pos_c(W, q.f, q.x, int(col), -1, bps, borrow, post_mode)
            o_ = q.beta * slot * es if cell == "E" else brute_pos_c(W, q.f, q.x, int(q.seas[mt[i]]), +1, bps, borrow, post_mode)
            x[q.f:q.x + 1] += (s_ if side <= 0 else 0.0) + (o_ if side >= 0 else 0.0)
            n += 1
    return x, n


def brute_dv(W, r, j):
    """plain python: the 20-session mean raw dollar volume of name j at the rank close r"""
    v = [W.Cl[t, j] * W.Vv[t, j] for t in range(r - SPEC["dv_n"] + 1, r + 1)]
    return sum(v) / len(v) if all(math.isfinite(a) for a in v) else float("nan")


# ------------------------------------------------------------------ selftest: hand-made worlds, no files, no data
def t_constants():
    """the constants are the registered ones (prereg draft v1 + addenda 1, 2 and 3), the pre-registration on disk is the registered file (its LF sha256, and the committed blob when git is there)"""
    assert (NREP, SEED, CELLS, AUDIT_N) == (500, 20261005, ("E", "M"), 50) and YEARS == tuple(range(2017, 2025)) and COHORTS == tuple(range(2016, 2025)) and AGE_MONTHS == tuple(range(4, 25))
    assert (SPEC["new_lo"], SPEC["new_hi"], SPEC["seas_months"], SPEC["nc_months"], SPEC["n4_next"], SPEC["n4_min"], SPEC["floor"], SPEC["slot"], SPEC["beta_win"], SPEC["dv_n"], SPEC["n3_lo"], SPEC["n3_hi"]) == (126, 504, 36, 24, 20, 18, 10, 4000.0, 126, 20, 84, 168)
    assert SPEC["hold_win"] == 252 and SPEC["min_n"] == 230 and SPEC["pre"] == 25 and SPEC["old"] == 125 and SPEC["month"] == 21 and SPEC["beta_min"] == 115
    assert (BORROW, BORROW_STRESS, COST_BPS, tuple(STRESS_BPS), ES_BPS, BETA_RULE) == (0.03, (0.10, 0.25), 5.0, (10.0, 20.0), 0.5, 0.20)
    assert (A2_WIN, A2_TARGET, A2_REPORT, WFN, FIRST_SESSION, X2022, BOOM) == ((TS("2018-02-01"), TS("2020-01-31")), 0.25, (0.5, 2.0), TS("2018-02-01"), TS("2016-01-04"), (TS("2022-01-01"), TS("2022-12-31")), (TS("2020-01-01"), TS("2021-12-31")))
    assert (WF0, PRE_END, LB0, LB1) == (TS("2016-07-01"), TS("2025-06-29"), TS("2025-06-30"), TS("2026-06-30")) and (S.LB0, S.END) == (LB0, R11.LBX) and (BOOK_WF, BOOK_LB, DEEPEST_WF) == ((93.81, 3.816), (155.54, 4.15), 44849.0)
    assert FLOOR_REPORTED == 20 > SPEC["floor"] == 10, "[N7] the registered floor is 10 NEW names; the 20-name reading is printed beside every cell row"
    assert all(s in LOW_POWER for s in ("LOW-POWER FLAG [N9]", "2018-03 .. 2022-03", "listing boom", "2020-21", "2022", "after 2022", "top-500 universe", "net > 0 without calendar 2022", "stays binding", "any pass is a LOW-POWER, FLAGGED result"))
    assert RULES["reb"] == 40 and RULES["roc"] == 15.0 and RULES["years"] == 5 and RULES["best_pct"] == 1 and RULES["beta_abs"] == 0.20 and RULES["b_reb"] == 10 and (RULES["b_roc"], RULES["b_sort"]) == BOOK_LB
    assert HALVES[0][1:] == (TS("2018-02-01"), TS("2021-12-31")) and HALVES[1][1:] == (TS("2022-01-01"), TS("2025-06-29")) and CHECK_BOOK is True
    assert (ST_NONE, ST_START, ST_OK, ST_FAIL, ST_LATE) == (0, 1, 2, 3, 4) and set(ST_NAME) == {0, 1, 2, 3, 4}
    assert HYG == ("split", "gap", "tbis", "jump") and GO_FLAG == "newissue_stageB_GO.flag" and READ_FLAG == "newissue_stageB_READ.flag"
    assert R11.sha_lf(PREREG) == PREREG_SHA == "e4900bcb1d74e2c92e88fb03452c1843c9dc379c807f15e83ad3f03d583b03ae"
    with quiet():
        assert prereg_ok()["verified"] is True
    txt = open(PREREG, encoding="utf-8", newline="").read()
    for frag in ("[N1] BORROW", "3%/yr", "PRIMARY", "0.20", "126 .. 504", "[N6] SIZE FLOOR", "fewer than 20 NEW names", "seed 20261005", "500 draws", "[X1]", "[X2]", "18 of the 20", "PRE-DATA ADDENDUM 3", "[N7] FLOOR 10", "fewer than 10 NEW names (counted after every removal)", "[N8] BAR (a) = at least 40 traded rebalances", "[N9]", "stays BINDING", "2018-03 .. 2022-03", "any pass is a LOW-POWER, FLAGGED result",
                 "[N10] (MANAGER #100)", "dollars a year (net / years)", "45 on the walk-forward", "both floors side by side"):
        assert frag in txt or frag.replace("[N1] ", "") in txt, frag
    return True


def t_listing():
    """a listing session = a name's first bar, dated only from the cache's second session on; accepted only with a raw close AND a positive volume on >= 18 of the 20 sessions after it ([N4]): exactly 18 is in, 17 is out, a zero or missing volume is a missing session, a stray bar before a real listing
    fails, a listing with fewer than 20 sessions after it is unverifiable (neither accepted nor failed); the status codes, the by-year counts and the plain-python recount"""
    T = 60
    Cl, Vv = np.full((T, 13), np.nan), np.full((T, 13), np.nan)

    def bars(j, first, last=T - 1, holes=(), zero=(), nanv=()):
        for t in range(first, last + 1):
            if t not in holes:
                Cl[t, j] = 50.0
                Vv[t, j] = 0.0 if t in zero else (np.nan if t in nanv else 1e6)
    bars(0, 0, holes=(10, 11, 12))                   # present at the first session, with a hole: undated, no age
    bars(1, 5)                                       # 20 of 20: accepted
    bars(2, 5, holes=(7, 20))                        # 18 of 20 (rows 6 .. 25): accepted - the edge
    bars(3, 5, holes=(7, 8, 20))                     # 17 of 20: failed
    bars(4, 5, zero=(6, 7))                          # a zero volume is a missing session: 18: accepted
    bars(5, 5, zero=(6, 7, 8))                       # 17: failed
    bars(6, 5, nanv=(6, 7, 8))                       # a missing volume (the close is there): 17: failed
    bars(7, 50)                                      # 9 sessions follow: unverifiable
    bars(9, 3, holes=tuple(range(4, 30)))            # a stray bar at row 3, bars again from row 30: the first bar is the listing: failed
    bars(10, 1)                                      # the second session: a dated listing
    bars(11, 39)                                     # rows 40 .. 59: exactly 20 follow: complete, accepted
    bars(12, 40)                                     # 19 follow: unverifiable
    li = listing_info(Cl, Vv)
    assert li.first.tolist() == [0, 5, 5, 5, 5, 5, 5, 50, -1, 3, 1, 39, 40] and li.L.tolist() == [-1, 5, 5, 5, 5, 5, 5, 50, -1, 3, 1, 39, 40]
    assert li.st.tolist() == [ST_START, ST_OK, ST_OK, ST_FAIL, ST_OK, ST_FAIL, ST_FAIL, ST_LATE, ST_NONE, ST_FAIL, ST_OK, ST_OK, ST_LATE], li.st.tolist()
    assert li.n_after.tolist()[1:7] == [20, 18, 17, 18, 17, 17] and li.n_after[0] == 17 and li.n_after[9] == 0 and li.n_after[11] == 20 and li.n_after[8] == 0
    W = SimpleNamespace(Cl=Cl, Vv=Vv, T=T, S=13)
    bl = brute_listing(W)
    assert [b[0] for b in bl] == li.first.tolist() and [b[1] for b in bl] == li.L.tolist() and [b[2] for b in bl] == li.st.tolist() and [b[3] for b in bl] == li.n_after.tolist(), bl
    # other windows: 10 sessions, 9 needed
    sp = dict(SPEC, n4_next=10, n4_min=9)
    li2 = listing_info(Cl, Vv, sp)
    assert li2.st[2] == ST_OK and li2.st[3] == ST_FAIL and li2.st[7] == ST_LATE and li2.st[12] == ST_OK and li2.n_after[2] == 10 - 1 and li2.n_after[3] == 8, (li2.st.tolist(), li2.n_after.tolist())
    assert [b[2] for b in brute_listing(W, sp)] == li2.st.tolist()
    # the by-year counts on planted calendar years: row 5 = 2023-12-25 (a Monday), rows >= 7 are 2024
    days = pd.bdate_range("2023-12-20", periods=T)
    lc = listing_counts(days, li)
    yrs = [days[l_].year for l_ in li.L if l_ >= 0]
    assert lc["present_at_first_session"] == 1 and lc["no_bar"] == 1 and sorted(lc["by_year"]) == sorted(set(yrs))
    for y, v in lc["by_year"].items():
        sel = [j for j in range(13) if li.L[j] >= 0 and days[li.L[j]].year == y]
        assert v == {"dated": len(sel), "accepted": sum(li.st[j] == ST_OK for j in sel), "failed": sum(li.st[j] == ST_FAIL for j in sel), "unverifiable": sum(li.st[j] == ST_LATE for j in sel)}, (y, v)
    sub = np.zeros(13, bool)
    sub[[1, 3, 8]] = True
    lc2 = listing_counts(days, li, sub)
    assert lc2["present_at_first_session"] == 0 and lc2["no_bar"] == 1 and sum(v["dated"] for v in lc2["by_year"].values()) == 2
    return True


def t_calendar():
    """the calendar's two extra tables from r16_xgap's flat CSV: a spin-off's NEW symbol (the row's `new_symbol`; `symbol` is the parent) and the name changes (`old_symbol` / `new_symbol`, process date only); the date a row acts on = its ex-date, else its process date; an undated or symbol-less row is counted and
    never used; rows on / after the cut are dropped at read; a missing file gives empty tables, a missing column refuses. Then the grid: the first spin-off row per new symbol, the name-change counts by session (either symbol is the name), a date that is not a session moves to the next one"""
    hdr = ",".join(M17.CA_COLS)
    rows = ["spin_off,PAR1,,SPN1,2024-03-01,2024-03-04,,,,0.1,1,,", "spin_off,PAR2,,SPN2,,2024-05-06,,,,0.1,1,,", "spin_off,PAR3,,,2024-03-05,2024-03-05,,,,0.1,1,,", "spin_off,PAR4,,SPN4,,,,,,0.1,1,,", "spin_off,PAR5,,SPN5,2025-06-30,2025-06-30,,,,0.1,1,,",
            "name_change,,OLDA,NEWA,,2024-02-05,,,,,,,", "name_change,,OLDB,,,2024-04-08,,,,,,,", "name_change,,,,,2024-04-09,,,,,,,", "name_change,,OLDC,NEWC,,,,,,,,,", "name_change,,OLDD,NEWD,,2025-07-01,,,,,,,",
            "cash_dividend,XYZ,,,2024-03-01,2024-03-01,,,0.5,,,,False"]
    with tempfile.TemporaryDirectory() as td:
        p = os.path.join(td, "ca.csv")
        with open(p, "w", newline="\n") as f:
            f.write("\n".join([hdr] + rows) + "\n")
        ex, info = cal_extra(TS("2025-06-30"), csv=p)
        assert info["present"] and info["rows_on_file"] == 11 and info["rows_dropped_at_the_cut"] == 2 and info["rows_read"] == 9, info
        assert info["spin_off"] == {"rows": 4, "usable": 2, "no_new_symbol_or_date": 2, "by_year": {2024: 2}, "earliest": "2024-03-01"} and info["name_change"] == {"rows": 4, "usable": 2, "no_symbol_or_date": 2, "by_year": {2024: 2}, "earliest": "2024-02-05"}, info
        _e1, info1 = cal_extra(TS("2024-01-01"), csv=p)                                      # a cut before every dated row: nothing usable, no earliest date
        assert info1["spin_off"]["usable"] == 0 and info1["spin_off"]["earliest"] is None and info1["name_change"]["earliest"] is None and info1["rows_dropped_at_the_cut"] == 9 and info1["rows_read"] == 2, info1
        assert ex.spin["sym"].tolist() == ["SPN1", "SPN2"] and ex.spin["parent"].tolist() == ["PAR1", "PAR2"] and ex.spin["ev"].tolist() == [TS("2024-03-01"), TS("2024-05-06")], "the ex-date, else the process date"
        assert ex.chg["old"].tolist() == ["OLDA", "OLDB"] and ex.chg["new"].tolist() == ["NEWA", ""] and ex.chg["ev"].tolist() == [TS("2024-02-05"), TS("2024-04-08")]
        ex2, info2 = cal_extra(TS("2025-07-02"), csv=p)                                      # a later cut keeps the rows between
        assert info2["rows_dropped_at_the_cut"] == 0 and len(ex2.spin) == 3 and len(ex2.chg) == 3
        e0, i0 = cal_extra(TS("2025-06-30"), csv=os.path.join(td, "absent.csv"))
        assert i0["present"] is False and len(e0.spin) == 0 and len(e0.chg) == 0
        with open(os.path.join(td, "bad.csv"), "w", newline="\n") as f:
            f.write("type,symbol\nspin_off,X\n")
        refused(lambda: cal_extra(TS("2025-06-30"), csv=os.path.join(td, "bad.csv")), "lacks the column", "lockbox NOT read")
    # the grid
    cols = [dict(sym="NEW1", first=0), dict(sym="OLD2", first=0), dict(sym="NEW2", first=0), dict(sym="S1", first=0), dict(sym="S2", first=0)]
    spin = [("S1", "P", "2024-01-10"), ("S1", "P2", "2024-01-05"), ("S2", "P", "2024-01-06"), ("NOTONGRID", "P", "2024-01-05"), ("S2", "P", "2030-01-02")]          # the earlier of S1's two; a Saturday -> Monday; a name off the grid; a date after the data
    chg = [("OLD1", "NEW1", "2024-01-09"), ("OLD2", "NEW2", "2024-01-12"), ("NEW1", "", "2024-01-30"), ("X", "Y", "2023-12-01")]                                       # one symbol on the grid; both on the grid; the same name twice; neither
    w = ni_world(cols, T=60, spin=spin, chg=chg)
    W = w.W
    sp_row, nccs, counts = calendar_arrays(W, w.extra)
    days = W.days
    j = lambda s: list(W.syms).index(s)
    assert sp_row[j("S1")] == days.get_loc(TS("2024-01-05")) and sp_row[j("S2")] == days.get_loc(TS("2024-01-08")) and sp_row[j("NEW1")] >= W.T, (sp_row.tolist(), days.get_loc(TS("2024-01-08")))
    assert counts == {"spin_events_placed": 3, "name_change_events_placed": 4}, counts                  # S1 x 2, S2's Monday; NEW1, OLD2, NEW2, NEW1 again (X / Y / OLD1 are off the grid; the X / Y row's date is before the data: a session on / after it is row 0)
    ev = lambda s, a, b: int(nccs[b + 1, j(s)] - nccs[a, j(s)])
    r9, r12, r30 = days.get_loc(TS("2024-01-09")), days.get_loc(TS("2024-01-12")), days.get_loc(TS("2024-01-30"))
    assert ev("NEW1", 0, r9 - 1) == 0 and ev("NEW1", r9, r9) == 1 and ev("NEW1", r9, r30 - 1) == 1 and ev("NEW1", r9, r30) == 2 and ev("OLD2", r12, r12) == 1 and ev("NEW2", 0, r12 - 1) == 0 and ev("NEW2", r12, W.T - 1) == 1 and ev("S1", 0, W.T - 1) == 0
    return True


def t_match():
    """the matched long: the SEASONED name nearest in 20-session mean dollar volume, each used once, ties by symbol - the GLOBAL greedy (the closest (NEW, candidate) pair first, then the closest among the unused, ties by the NEW name's symbol then the candidate's), exact against a plain-python all-pairs
    recount on 600 random worlds with heavy ties and missing values; hand cases where the order of assignment matters; fewer candidates than NEW names; dv20 against a hand count"""
    f = lambda dn, dc, kn, kc: match_nearest(np.array(dn, float), np.array(dc, float), np.array(kn), np.array(kc)).tolist()
    assert f([100, 100], [100, 100, 90], [0, 1], [5, 6, 7]) == [0, 1], "equal distances: the lower symbol first (NEW 0 takes candidate 0, NEW 1 the next)"
    assert f([100, 100], [100, 100, 90], [0, 1], [6, 5, 7]) == [1, 0], "ties by symbol: candidate 1 has the lower key (5)"
    assert f([100, 100], [100, 100, 90], [1, 0], [5, 6, 7]) == [1, 0], "ties by the NEW name's symbol: NEW 1 has the higher key (1 against 0): NEW 0 (the second row) goes first"
    assert f([10, 12], [11, 30], [0, 1], [2, 3]) == [0, 1], "each candidate once: NEW 1 cannot also take the 11"
    assert f([10, 12], [11.5, 30], [0, 1], [2, 3]) == [1, 0], "the closest PAIR first (12 and 11.5), not the first NEW name"
    assert f([10, 11], [10.4, 20], [0, 1], [2, 3]) == [0, 1]
    assert f([10, 12, 14], [11, 30], [0, 1, 2], [5, 6]) == [0, -1, 1] or f([10, 12, 14], [11, 30], [0, 1, 2], [5, 6]) == [0, 1, -1] or True
    out = f([10, 12, 14], [11, 30], [0, 1, 2], [5, 6])
    assert sorted(out) == [-1, 0, 1] and out[0] == 0 and len([v for v in out if v >= 0]) == 2, out
    assert f([5], [], [0], []) == [-1] and f([], [3], [], [1]) == [] and f([float("nan"), 5], [5, float("nan")], [0, 1], [2, 3]) == [-1, 0], "a missing dollar volume is never paired"
    rng = np.random.default_rng(12)
    for trial in range(600):
        n, m = int(rng.integers(0, 11)), int(rng.integers(0, 15))
        dn, dc = rng.integers(0, 9, n).astype(float), rng.integers(0, 9, m).astype(float)
        if trial % 3 == 0:
            dn[rng.random(n) < 0.1] = np.nan
            dc[rng.random(m) < 0.1] = np.nan
        keys = rng.permutation(n + m)
        kn, kc = keys[:n], keys[n:]
        got = match_nearest(dn, dc, kn, kc).tolist()
        want = brute_match(dn.tolist(), dc.tolist(), kn.tolist(), kc.tolist())
        assert got == want, (trial, dn, dc, kn, kc, got, want)
        assert len([v for v in got if v >= 0]) == len(set(v for v in got if v >= 0)), "each candidate used once"
    # real-valued dollar volumes (no ties), a larger world
    for _ in range(30):
        n, m = int(rng.integers(5, 40)), int(rng.integers(5, 120))
        dn, dc = rng.lognormal(16, 1, n), rng.lognormal(16, 1, m)
        keys = rng.permutation(n + m)
        assert match_nearest(dn, dc, keys[:n], keys[n:]).tolist() == brute_match(dn.tolist(), dc.tolist(), keys[:n].tolist(), keys[n:].tolist())
    # dv20 = the mean over sessions r-19 .. r of the raw close x the raw volume
    w = ni_world([dict(sym="A", first=0, p0=10.0, shares=1e6, ret=np.r_[0.0, np.full(79, 0.01)]), dict(sym="B", first=0, dvol=5e7)], T=80)
    r = 60
    a = [w.W.Cl[t, 0] * w.W.Vv[t, 0] for t in range(r - 19, r + 1)]
    assert np.allclose(dv20(w.W, r, np.array([0, 1])), [sum(a) / 20, 5e7], rtol=1e-12) and dv20(w.W, r, np.array([0, 1]))[0] != w.W.Cl[r, 0] * w.W.Vv[r, 0]
    return True


def planted_sets_world():
    """the NEW / SEASONED rules with every case planted, the registered windows shrunk (SMALL: NEW 15 .. 45 sessions, SEASONED > 3 calendar months, a name change within 2 months, 20-session [N4] with 18). Rank r = a month-end; returns (w, r, f, x, expected NEW (registered), expected NEW (look-ahead), expected SEASONED, spin, chg)"""
    days = pd.bdate_range("2024-01-01", periods=330)
    r_all, f_all, x_all = M17.rm_schedule(days)
    q = [i for i, r_ in enumerate(r_all) if r_ >= 120][0]
    r, f, x = int(r_all[q]), int(f_all[q]), int(x_all[q])
    a24 = first_on_or_after(days, days[r] - pd.DateOffset(months=SMALL["nc_months"]))
    b36 = first_on_or_after(days, days[r] - pd.DateOffset(months=SMALL["seas_months"]))
    d = lambda row: f"{days[row]:%Y-%m-%d}"
    cols = [dict(sym=f"A{k:02d}", first=0) for k in range(12)]                             # SEASONED: present at the first session
    cols += [dict(sym="B_E14", first=r - 14), dict(sym="B_E15", first=r - 15), dict(sym="B_E45", first=r - 45), dict(sym="B_E46", first=r - 46)]       # the NEW window's edges
    cols += [dict(sym="C_SA", first=b36 - 1), dict(sym="C_SB", first=b36)]                  # the SEASONED edge: listed MORE than 3 months before r
    cols += [dict(sym="D_SPIN", first=r - 30), dict(sym="D_SPIN2", first=r - 30), dict(sym="D_SPIN3", first=r - 30)]                                     # spinco: dated before r / after r / on r
    cols += [dict(sym=f"E_NC{k}", first=r - 30) for k in (1, 2, 3, 4)]                      # name change: on the window's first row / just before it / after r / on r
    cols += [dict(sym="F_SNC", first=0), dict(sym="F_SNC2", first=0)]                       # a SEASONED name with a name change inside / outside the window
    cols += [dict(sym="G_17", first=r - 25, holes=(r - 23, r - 20, r - 16)), dict(sym="G_18", first=r - 25, holes=(r - 23, r - 20)), dict(sym="G_ZV", first=r - 25, zero_vol=(r - 23, r - 20, r - 16)),
             dict(sym="G_STRAY", first=r - 30, holes=tuple(range(r - 29, r - 5)))]          # [N4]: 17 of 20 / exactly 18 / a zero volume counts as missing / a stray bar
    cols += [dict(sym="J_PRE", first=r - 30), dict(sym="J_OLD", first=r - 30), dict(sym="J_OLDCHG", first=r - 30), dict(sym="J_POST", first=r - 30), dict(sym="J_SPNPOST", first=r - 30), dict(sym="K_PLAIN", first=r - 20)]
    spin = [("D_SPIN", "PARENT", d(r - 10)), ("D_SPIN2", "PARENT", d(r + 5)), ("D_SPIN3", "PARENT", d(r))]
    chg = [("OLD1", "E_NC1", d(a24)), ("E_NC2", "OLD2", d(a24 - 1)), ("OLD3", "E_NC3", d(r + 1)), ("E_NC4", "OLD4", d(r)), ("OLD5", "F_SNC", d(r - 5)), ("OLD6", "F_SNC2", d(a24 - 40))]
    flags = {"gap": [("J_PRE", r - 3), ("J_OLD", r - 20), ("J_POST", f + 3)], "chg": [("J_OLDCHG", r - 20)]}
    w = ni_world(cols, T=330, spin=spin, chg=chg, flags=flags, spn=[("J_SPNPOST", f + 2)])
    new = ["B_E15", "B_E45", "D_SPIN2", "E_NC2", "E_NC3", "G_18", "J_OLDCHG", "K_PLAIN"]
    seas = [f"A{k:02d}" for k in range(12)] + ["C_SA", "F_SNC2"]
    return w, r, f, x, new, sorted(new + ["J_POST", "J_SPNPOST"]), seas, spin, chg


def t_sets():
    """who is NEW and who is SEASONED: the window edges (125 / 126, 504 / 505 sessions - shrunk here), the SEASONED edge (listed more than 36 months before r; present at the first session), the spinco exclusion (dated on / before r), the name-change exclusion (the 24-month window's first row .. r, either symbol, for NEW
    and SEASONED), the [N4] failures out of both, hygiene before the decision removes in both readings and inside the hold only in the registered one, the counts - on a planted world and against a plain-python recount on random worlds in both readings, with the [N3] window and the included variants"""
    with spec(**SMALL):
        w, r, f, x, new, new_k, seas, spin, chg = planted_sets_world()
        W, ctx = w.W, w.ctx
        rec, cnt = ni_one(W, ctx, r, f, x, "remove", units=False)
        assert sorted(map(str, W.syms[rec.new])) == sorted(new) and sorted(map(str, W.syms[rec.seas])) == sorted(seas), (sorted(map(str, W.syms[rec.new])), sorted(map(str, W.syms[rec.seas])))
        assert rec.n_new == len(new) and rec.n_seas == len(seas) and rec.traded and rec.pool.tolist() == rec.new.tolist() + rec.seas.tolist()
        assert (W.days[rec.lrow] .year == 2024).all() and (rec.age == r - rec.lrow).all() and ((rec.age >= 15) & (rec.age <= 45)).all() and rec.cohort.tolist() == [2024] * len(new) and (rec.kind == 0).all()
        rk, cnk = ni_one(W, ctx, r, f, x, "naive", units=False)
        assert sorted(map(str, W.syms[rk.new])) == sorted(new_k) and sorted(map(str, W.syms[rk.seas])) == sorted(seas), "the look-ahead reading keeps the names flagged inside the hold"
        assert rk.naive[[list(map(str, W.syms[rk.new])).index(n_) for n_ in ("J_POST", "J_SPNPOST")]].all() and rk.naive.sum() == 2 and cnk["new_kept_naive"] == 2
        # the counts: the age-window names (accepted listings), the spinco / name-change names counted whatever else removes them, the [N4] failures
        assert cnt["new_age"] == 16 and rec.newage == 16 and cnt["new_spinco_any"] == 2 and cnt["new_name_change_any"] == 2 and cnt["n4_failed_names"] == 3 and cnt["n4_unverifiable_names"] == 0, dict(cnt)
        assert cnt["new_spinco"] == 2 and cnt["new_name_change"] == 2 and cnt["new_pre_gap"] == 1 and cnt["new_old_gap"] == 1 and cnt["new_post_gap"] == 1 and cnt["new_post_spin"] == 1 and cnt["new_pool"] == len(new), dict(cnt)
        assert cnt["seas_name_change"] == 1 and cnt["seasoned_age"] == len(seas) + 1 and cnt["seas_pool"] == len(seas), dict(cnt)
        # the registered rules, name by name
        names = lambda ids: set(map(str, W.syms[ids]))
        assert {"B_E14", "B_E46", "C_SB"} & names(rec.new) == set() and {"B_E14", "B_E46", "C_SB"} & names(rec.seas) == set(), "outside both windows"
        assert {"G_17", "G_ZV", "G_STRAY"} & (names(rec.new) | names(rec.seas)) == set(), "[N4] failures are neither NEW nor SEASONED"
        assert "F_SNC" not in names(rec.seas) and "F_SNC2" in names(rec.seas) and "C_SA" in names(rec.seas), "a name change inside the window leaves SEASONED; one before it does not"
        # the brute-force recount, registered and look-ahead
        for mode, got in (("remove", rec), ("naive", rk)):
            bn, bs = brute_sets(W, spin, chg, r, f, x, mode)
            assert sorted(map(str, W.syms[got.new])) == sorted(bn) and sorted(map(str, W.syms[got.seas])) == sorted(bs), mode
        # the same r a session earlier / later: the window edges move with r, the spinco dated r + 5 is a spinco from r + 5 on, the name change dated r + 1 counts from r + 1
        r2, f2, x2 = r + 5, r + 6, x
        rec2, _c2 = ni_one(W, ctx, r2, f2, x2, "remove", units=False)
        bn2, bs2 = brute_sets(W, spin, chg, r2, f2, x2, "remove")
        assert sorted(map(str, W.syms[rec2.new])) == sorted(bn2) and sorted(map(str, W.syms[rec2.seas])) == sorted(bs2) and "D_SPIN2" not in names(rec2.new) and "D_SPIN2" in set(map(str, W.syms)), "D_SPIN2's spin-off (r + 5) is known at r + 5"
        assert "E_NC3" not in set(map(str, W.syms[rec2.new])), "E_NC3's name change (r + 1) is known at r + 5"
        # the variants: [N3] 84 .. 168 sessions (shrunk: a different window), spincos / name changes included
        for kw in (dict(win=(10, 30)), dict(incl=(True, False)), dict(incl=(False, True)), dict(incl=(True, True))):
            recv, _cv = ni_one(W, ctx, r, f, x, "remove", units=False, **kw)
            bnv, bsv = brute_sets(W, spin, chg, r, f, x, "remove", win=kw.get("win"), incl=kw.get("incl", (False, False)))
            assert sorted(map(str, W.syms[recv.new])) == sorted(bnv) and sorted(map(str, W.syms[recv.seas])) == sorted(bsv), kw
            if "incl" in kw:
                kinds = {str(W.syms[c_]): int(k_) for c_, k_ in zip(recv.new, recv.kind)}
                assert kinds.get("D_SPIN", 0) == (1 if kw["incl"][0] else 0) or "D_SPIN" not in kinds, kinds
                assert (kinds.get("E_NC1", 0) == 2) == bool(kw["incl"][1]) or "E_NC1" not in kinds, kinds
    # random worlds: every rebalance of ni_build, both readings, the [N3] window, the included variants, against the plain-python sets
    n_chk = 0
    with spec(**SMALL):
        for seed in (1, 2, 3):
            rng = np.random.default_rng(seed)
            T = 330
            cols = []
            for k in range(46):
                first = 0 if rng.random() < 0.3 else int(rng.integers(1, T - 40))
                holes = tuple(int(v) for v in rng.integers(first + 1, T, int(rng.integers(0, 6)))) if rng.random() < 0.5 else ()
                zero = tuple(int(v) for v in rng.integers(first + 1, T, int(rng.integers(0, 4)))) if rng.random() < 0.3 else ()
                cols.append(dict(sym=f"R{k:02d}", first=first, holes=holes, zero_vol=zero, last=(T - 1 if rng.random() < 0.85 else int(rng.integers(first + 30, T)))))
            days = pd.bdate_range("2024-01-01", periods=T)
            syms = [c["sym"] for c in cols]
            spin = [(str(rng.choice(syms)), "P", f"{days[int(rng.integers(0, T + 20))]:%Y-%m-%d}") for _ in range(8)]
            chg = [(str(rng.choice(syms + ["ZZ1", "ZZ2"])), str(rng.choice(syms + ["ZZ3"])), f"{days[int(rng.integers(0, T))]:%Y-%m-%d}") for _ in range(10)]
            flags = {"gap": [(str(rng.choice(syms)), int(rng.integers(0, T))) for _ in range(25)], "tbis": [(str(rng.choice(syms)), int(rng.integers(0, T))) for _ in range(10)], "chg": [(str(rng.choice(syms)), int(rng.integers(0, T))) for _ in range(6)]}
            spn = [(str(rng.choice(syms)), int(rng.integers(0, T))) for _ in range(6)]
            wr = ni_world(cols, T=T, seed=seed, spin=spin, chg=chg, flags=flags, spn=spn)
            Wr = wr.W
            Wr.aud1[int(rng.integers(100, 300)), int(rng.integers(0, 40))] = True                       # an audit data event somewhere
            for mode in ("remove", "naive"):
                for kw in (dict(), dict(win=(10, 30)), dict(incl=(True, True))):
                    L = ni_build(Wr, wr.ctx, days[0], days[-1], mode, units=False, **kw)
                    assert len(L.recs) >= 8
                    for rc in L.recs:
                        bn, bs = brute_sets(Wr, spin, chg, rc.r, rc.f, rc.x, mode, win=kw.get("win"), incl=kw.get("incl", (False, False)))
                        assert sorted(map(str, Wr.syms[rc.new])) == sorted(bn) and sorted(map(str, Wr.syms[rc.seas])) == sorted(bs), (seed, mode, kw, rc.r)
                        n_chk += 1
    # the schedule edges of ni_build: warm-up ranks (r < hold_win - 1) and the unresolved last rank are counted, not built; positions are counted by EXIT date inside [lo, hi]
    with spec(**SMALL):
        wr = ni_world([dict(sym=f"A{k:02d}", first=0) for k in range(6)], T=330)
        r_all, f_all, x_all = M17.rm_schedule(wr.W.days)
        L = ni_build(wr.W, wr.ctx, wr.W.days[0], wr.W.days[-1], units=False)
        want = [(int(r_), int(f_), int(x_)) for r_, f_, x_ in zip(r_all, f_all, x_all) if x_ >= 0 and r_ >= SMALL["hold_win"] - 1]
        assert [(c.r, c.f, c.x) for c in L.recs] == want and sum(v["warmup"] for v in L.cnt.values()) == sum(1 for r_, x_ in zip(r_all, x_all) if x_ >= 0 and r_ < SMALL["hold_win"] - 1) and sum(v["unresolved"] for v in L.cnt.values()) == 1
        lo, hi = wr.W.days[x_all[5]], wr.W.days[x_all[8]]
        L2 = ni_build(wr.W, wr.ctx, lo, hi, units=False)
        assert all(lo <= wr.W.days[c.x] <= hi for c in L2.recs) and len(L2.recs) == sum(1 for r_, x_ in zip(r_all, x_all) if x_ >= 0 and r_ >= SMALL["hold_win"] - 1 and lo <= wr.W.days[x_] <= hi)
        drop = [wr.W.days[L.recs[2].r], wr.W.days[L.recs[3].r]]
        L3 = ni_build(wr.W, wr.ctx, wr.W.days[0], wr.W.days[-1], units=False, drop=drop)
        assert len(L3.recs) == len(L.recs) - 2 and sum(v["dropped"] for v in L3.cnt.values()) == 2 and all(c.r not in (L.recs[2].r, L.recs[3].r) for c in L3.recs)
    return n_chk


def pipe_world(seed=3, n_new=52, n_seas=22, T=330, drift_new=-0.0015, es_nan=(), start="2024-01-01"):
    """the cells' world: SMALL windows; n_seas SEASONED names present from the first session and n_new NEW names listed every 4 sessions from row 60 (so every month-end from the first usable rank holds several NEW names), all with their own dollar volume; the NEW names drift down (drift_new a day:
    a planted new-issue underperformance); planted cases at the first rank r1 (= the first month-end at or after row 120): STOP is NEW, stops printing 8 sessions into the hold (no open at the exit session: it exits at its last mark), HOLE has no close 5 sessions into it (the mark is carried) -> (w, r1)"""
    days = pd.bdate_range(start, periods=T)
    r_all, f_all, x_all = M17.rm_schedule(days)
    r1 = int([r_ for r_ in r_all if r_ >= 120][0])
    rng = np.random.default_rng(seed)
    cols = [dict(sym=f"A{k:02d}", first=0, beta=float(rng.uniform(0.6, 1.4)), dvol=float(np.exp(rng.uniform(np.log(2e7), np.log(4e8))))) for k in range(n_seas)]
    cols += [dict(sym=f"N{k:02d}", first=60 + 4 * k, beta=float(rng.uniform(0.8, 1.8)), drift=drift_new, dvol=float(np.exp(rng.uniform(np.log(2e7), np.log(4e8))))) for k in range(n_new)]
    cols += [dict(sym="STOP", first=r1 - 30, last=r1 + 8, beta=1.2, drift=drift_new, dvol=1e8), dict(sym="HOLE", first=r1 - 25, holes=(r1 + 5,), beta=1.2, drift=drift_new, dvol=9e7)]
    return ni_world(cols, T=T, seed=seed, es_nan=es_nan, start=start), r1


def t_beta_hedge():
    """cell E's ex-ante hedge: the OLS slope (an intercept and a slope) of the equal-weight NEW basket's daily total return on ES's over the 126 sessions before the rank (shrunk here) = a plain-python slope on random baskets with missing returns and ES holes; an exact linear basket recovers its slope whatever
    the intercept; fewer than 115 (shrunk: 28) basket-ES pairs -> no hedge ratio; the hedge's P&L per $1 against a hand count on an ES that rises 10 points a session (the 09:35 print in, the 16:00 prints between, the 09:35 print out) with the ES cost at both ends, the hole carry, and the hedge = beta x the short notional"""
    with spec(**SMALL):
        # (1) exact: two names with returns 0.001 + 1.0 m and 0.003 + 1.4 m -> the equal-weight basket is 0.002 + 1.2 m
        w = ni_world([dict(sym="X1", first=0, beta=1.0, drift=0.001, idio=0.0), dict(sym="X2", first=0, beta=1.4, drift=0.003, idio=0.0), dict(sym="X3", first=0, beta=0.2, drift=0.0, idio=0.02)], T=200, seed=5)
        W = w.W
        b, k = basket_beta(W, 150, np.array([0, 1]))
        assert abs(b - 1.2) < 1e-9 and k == SMALL["beta_win"], (b, k)
        b1, _k1 = basket_beta(W, 150, np.array([0]))
        assert abs(b1 - 1.0) < 1e-9 and abs(basket_beta(W, 150, np.array([1]))[0] - 1.4) < 1e-9
        # (2) against the plain-python slope on random baskets: missing returns (holes), ES holes, several ranks and baskets at once
        rng = np.random.default_rng(4)
        cols = [dict(sym=f"R{j:02d}", first=0, holes=tuple(int(v) for v in rng.integers(1, 200, int(rng.integers(0, 8)))), beta=float(rng.uniform(0.2, 2.0)), drift=float(rng.normal(0, 0.001))) for j in range(24)]
        w2 = ni_world(cols, T=200, seed=6, es_nan=(130, 140, 141))
        W2 = w2.W
        for r in (100, 135, 150, 170, 199):
            sz = int(rng.integers(1, 12))
            baskets = [rng.choice(24, sz, replace=False) for _ in range(6)]
            many, kn = basket_beta_many(W2, r, np.array(baskets))
            for bk, bm, km in zip(baskets, many, kn):
                bb, kk = brute_beta(W2, r, bk.tolist())
                one, ko = basket_beta(W2, r, bk)
                assert (math.isnan(bb) and math.isnan(bm) and math.isnan(one)) or (abs(bb - bm) < 1e-10 and abs(bb - one) < 1e-10), (r, bk, bb, bm, one)
                assert kk == km == ko, (r, kk, km, ko)
        # (3) the pair count: ES-hole sessions (no ES return that session and the next) are skipped; fewer than beta_min pairs: no ratio
        w3 = ni_world([dict(sym="X1", first=0, beta=1.0, idio=0.0)], T=200, seed=5, es_nan=(130,))
        assert basket_beta(w3.W, 150, np.array([0]))[1] == SMALL["beta_win"] - 2 and abs(basket_beta(w3.W, 150, np.array([0]))[0] - 1.0) < 1e-9, "one ES hole skips two sessions"
        w4 = ni_world([dict(sym="X1", first=0, beta=1.0, idio=0.0)], T=200, seed=5, es_nan=(130, 140, 145))
        b4, k4 = basket_beta(w4.W, 150, np.array([0]))
        assert k4 == SMALL["beta_win"] - 6 and math.isnan(b4) and basket_pairs(w4.W, 150, np.array([0])) == k4, "26 pairs < 28: no hedge ratio; the dryload's count is the same number"
        assert basket_pairs(W, 150, np.array([0, 1])) == SMALL["beta_win"]
        # a flat ES (no variation) has no slope
        wf = ni_world([dict(sym="X1", first=0, beta=1.0)], T=200, seed=5, es_vol=0.0)
        assert math.isnan(basket_beta(wf.W, 150, np.array([0]))[0]), "no ES variation: no slope"
    # (4) the hedge's P&L on an ES that rises 10 points a session
    T = 200
    es_levels = 1000.0 + 10.0 * np.arange(T)
    w5 = ni_world([dict(sym="X1", first=0, ret=np.zeros(T))], T=T, seed=5)
    W5 = w5.W
    esR = es_levels.copy()
    W5.es.c16r, W5.es.c16a = esR, esR + 5000.0
    e5a, e5r = np.empty(T), np.empty(T)
    e5a[0], e5r[0] = esR[0] + 5000.0, esR[0]
    e5a[1:], e5r[1:] = (esR[:-1] + 5000.0) + 3.0, esR[:-1] + 3.0
    W5.es.e5, W5.es.e5r = e5a, e5r
    attach_es(W5)
    f, x = 100, 121
    leg0 = es_leg(W5, f, x, 0.0)
    e5Rf, e5Rx = 1000 + 10 * (f - 1) + 3.0, 1000 + 10 * (x - 1) + 3.0
    want = np.r_[7.0, np.full(x - f - 1, 10.0), 3.0] / e5Rf
    assert np.allclose(leg0, want, rtol=1e-12, atol=0) and abs(leg0.sum() - 10.0 * (x - f) / e5Rf) < 1e-12, (leg0[:3], want[:3])
    leg = es_leg(W5, f, x, ES_BPS)
    c = ES_BPS * 1e-4
    assert abs(leg[0] - (want[0] - c)) < 1e-15 and abs(leg[-1] - (want[-1] - c * e5Rx / e5Rf)) < 1e-15 and np.allclose(leg[1:-1], want[1:-1]) and abs((leg0 - leg).sum() - c * (1.0 + e5Rx / e5Rf)) < 1e-14
    assert np.allclose(leg, brute_es_leg(W5, f, x, ES_BPS), rtol=1e-12) and es_leg(W5, f, x, ES_BPS) is es_leg(W5, f, x, ES_BPS), "cached per (f, x, bps)"
    # a hole in the hold: the 16:00 print is carried, the move over the hole is earned at the next print
    esR2 = es_levels.copy()
    w6 = ni_world([dict(sym="X1", first=0, ret=np.zeros(T))], T=T, seed=5, es_nan=(110,))
    W6 = w6.W
    W6.es.c16r, W6.es.c16a = np.where(np.arange(T) == 110, np.nan, esR2), np.where(np.arange(T) == 110, np.nan, esR2 + 5000.0)
    W6.es.e5, W6.es.e5r = e5a, e5r
    attach_es(W6)
    lg = es_leg(W6, f, x, 0.0)
    assert abs(lg[110 - f]) < 1e-15 and abs(lg[111 - f] - 20.0 / e5Rf) < 1e-12 and abs(lg.sum() - 10.0 * (x - f) / e5Rf) < 1e-12 and W6.es_hole[110] and not W6.es_hole[111]
    # (5) the hedge = beta x the short notional: the sum over the positions of the other side = beta x $4,000 x n x the per-$1 leg
    with spec(**SMALL):
        wp, r1 = pipe_world()
        Wp = wp.W
        rec, _c = ni_one(Wp, wp.ctx, r1, r1 + 1, fx_of(Wp.days, r1)[1], "remove")
        bb, kk = brute_beta(Wp, r1, rec.new.tolist())
        assert abs(rec.beta - bb) < 1e-10 and rec.bpairs == kk and rec.tE and math.isfinite(rec.beta), (rec.beta, bb)
        idx, S_, O = rec_legs(Wp, rec, "E", cfg_of())
        assert idx.tolist() == list(range(rec.n_new)) and S_.shape == O.shape == (rec.n_new, rec.x - rec.f + 1)
        assert np.allclose(O.sum(axis=0), rec.beta * SPEC["slot"] * rec.n_new * brute_es_leg(Wp, rec.f, rec.x, ES_BPS), rtol=1e-9, atol=1e-9) and np.allclose(O, O[0][None, :]), "every short carries an equal share of the hedge"
        assert abs(O.sum(axis=0).sum() / (SPEC["slot"] * rec.n_new) - rec.beta * brute_es_leg(Wp, rec.f, rec.x, ES_BPS).sum()) < 1e-9
    return True


def t_costs():
    """costs, borrow and the stress rows on hand numbers: a flat-priced short pays 2 x the cost in bps (entry and exit value) and rate / 252 x the prior mark on every row after the fill (3% a year base, 10% and 25% the stress rows - every short day), a long pays no borrow, the stress costs 10 / 20 bps, a cash
    dividend inside the hold is paid by a short, and a short in a name that stops printing is valued at zero by the [R2] reading"""
    T, f, x = 200, 100, 121
    H = x - f + 1
    ret = np.zeros(T)
    w = ni_world([dict(sym="FLAT", first=0, ret=ret, p0=100.0), dict(sym="STOP", first=0, last=x - 3, ret=ret, p0=100.0), dict(sym="PAYS", first=0, ret=ret, p0=100.0)], T=T, seed=2, dr={("PAYS", f + 5): 1.0})
    W = w.W
    j = {s: i for i, s in enumerate(W.syms)}
    U = M17.rm_units(W, f, x, np.array([j["FLAT"], j["STOP"], j["PAYS"]]))
    c = COST_BPS * 1e-4
    for rate in (0.03, 0.10, 0.25):
        P = pnl1(U, np.array([0]), -1, cfg_of(borrow=rate))
        want = np.full(H, -rate / 252.0)
        want[0] = -c
        want[-1] -= c
        assert np.allclose(P[0], want, rtol=1e-12, atol=1e-15) and abs(P.sum() - (-2 * c - (H - 1) * rate / 252.0)) < 1e-14, rate
        S_ = SPEC["slot"] * P
        assert abs(S_.sum() - SPEC["slot"] * (-2 * c - (H - 1) * rate / 252.0)) < 1e-9
        assert np.allclose(S_[0], brute_position(W, f, x, j["FLAT"], -1, COST_BPS, rate), rtol=1e-12, atol=1e-9)
    for bps in (0.0, 5.0, 10.0, 20.0):
        Pl = pnl1(U, np.array([0]), +1, cfg_of(bps=bps, borrow=0.25))
        assert abs(Pl.sum() + 2 * bps * 1e-4) < 1e-14 and np.allclose(Pl[0, 1:-1], 0.0), "a long pays no borrow, only the cost at both ends"
        Ps = pnl1(U, np.array([0]), -1, cfg_of(bps=bps))
        assert abs(Ps.sum() - (-2 * bps * 1e-4 - (H - 1) * BORROW / 252.0)) < 1e-14
    # a cash dividend of $1 on a $100 name inside the hold: a short pays it (the entry open is 100): -0.01 per $1
    Pd = pnl1(U, np.array([2]), -1, cfg_of())
    assert abs(Pd.sum() - (-2 * c - (H - 1) * BORROW / 252.0 - 0.01)) < 1e-13 and abs(Pd[0, 5] - (-BORROW / 252.0 - 0.01)) < 1e-14, (Pd[0, 5], Pd.sum())
    # a short in a name that stops printing (no open at the exit session): the base exits at the last mark; the [R2] reading values it at zero - the full +1 per $1, no exit cost
    assert U.st[1] and not U.st[0]
    Pb = pnl1(U, np.array([1]), -1, cfg_of())
    P0 = pnl1(U, np.array([1]), -1, cfg_of(short0=True))
    assert abs(P0.sum() - Pb.sum() - (1.0 + c)) < 1e-13 and cfg_of(short0=True)["short0"] is True and "short0" not in cfg_of()
    assert cfg_of()["borrow"] == (0.03, None) and cfg_of(bps=10.0)["bps"] == 10.0 and cfg_of(borrow=0.25)["borrow"] == (0.25, None)
    # the ES leg's cost: 0.5 bps of the notional at both ends (the exit value at the unadjusted prints' ratio)
    e0, e5 = es_leg(W, f, x, 0.0), es_leg(W, f, x, ES_BPS)
    ratio = W.e5R[x] / W.e5R[f]
    assert abs((e0 - e5).sum() - 0.5e-4 * (1.0 + ratio)) < 1e-15
    return True


def t_floor():
    """[N7] a month with fewer than 10 NEW names (the registered floor; 20 is the reported reading's) trades nothing in either cell: 9 NEW names -> not traded, counted, both cells hold nothing; 10 -> traded (19 trades under the registered floor and not under the reported one). E also needs a defined hedge ratio (an ES history with too few pairs: E trades nothing, M still does); M needs a SEASONED candidate (none: M trades nothing,
    E does); fewer SEASONED names than NEW names leaves the rest unmatched and unshorted in M"""
    def world(n_new, n_seas, es_nan=()):
        days = pd.bdate_range("2024-01-01", periods=330)
        r_all, _f, _x = M17.rm_schedule(days)
        r = int([r_ for r_ in r_all if r_ >= 120][0])
        cols = [dict(sym=f"A{k:02d}", first=0, dvol=1e7 * (k + 1)) for k in range(n_seas)] + [dict(sym=f"N{k:02d}", first=r - 40 + k, dvol=1e7 * (k + 1) + 3e6, drift=-0.001) for k in range(n_new)]
        return ni_world(cols, T=330, seed=4, es_nan=es_nan), r
    for fl, cases in ((10, ((9, False), (10, True), (19, True))), (FLOOR_REPORTED, ((19, False), (20, True)))):
        with spec(**{**SMALL, "floor": fl}):
            for n_new, traded_ in cases:
                w, r = world(n_new, 14)
                L = ni_build(w.W, w.ctx, w.W.days[0], w.W.days[-1])
                rec = next(q for q in L.recs if q.r == r)
                assert rec.n_new == n_new and rec.traded is traded_ and rec.tE is traded_ and rec.tM is traded_, (fl, n_new, rec.n_new, rec.traded)
                assert sum(v["below_floor"] for v in L.cnt.values()) >= (0 if traded_ else 1)
                lcx = leg_counts(w.W, SimpleNamespace(recs=[rec]))
                assert lcx["floor"] == fl and lcx["traded"] == int(traded_) and (lcx["below_floor"] == []) is traded_, (fl, n_new)
    with spec(**{**SMALL, "floor": 20}):
        for n_new, traded_ in ((19, False), (20, True)):
            w, r = world(n_new, 14)
            L = ni_build(w.W, w.ctx, w.W.days[0], w.W.days[-1])
            rec = next(q for q in L.recs if q.r == r)
            assert rec.n_new == n_new and rec.traded is traded_ and rec.tE is traded_ and rec.tM is traded_, (n_new, rec.n_new, rec.traded)
            assert sum(v["below_floor"] for v in L.cnt.values()) >= (0 if traded_ else 1)
            for cell in CELLS:
                run = cell_run(w.W, L, cell, cfg_of())
                if not traded_:
                    assert rec.r not in [L.recs[int(i)].r for i in run.pos.rec], "a month under the floor holds nothing"
                else:
                    assert rec.r in [L.recs[int(i)].r for i in run.pos.rec]
            assert [q.r for q in L_recs(L)] == [q.r for q in L.recs if q.traded]
        w, r = world(20, 14)
        rec = next(q for q in ni_build(w.W, w.ctx, w.W.days[0], w.W.days[-1]).recs if q.r == r)
        lc = leg_counts(w.W, SimpleNamespace(recs=[rec]))
        assert lc["traded"] == 1 and lc["below_floor"] == [] and lc["new_per_rebalance"] == [20, 20.0, 20] and lc["first_traded_rank"] == lc["last_traded_rank"] == f"{w.W.days[r]:%Y-%m-%d}"
        # E needs a defined hedge ratio: three ES holes in the beta window leave 24 pairs of the 28 needed
        wn, r = world(20, 14, es_nan=(r - 10, r - 20, r - 5))
        with spec(min_n=50):                                                                   # (the SEASONED history rule reads the same ES pairs: 54 of 60 here)
            Ln = ni_build(wn.W, wn.ctx, wn.W.days[0], wn.W.days[-1])
        recn = next(q for q in Ln.recs if q.r == r)
        assert recn.traded and not recn.tE and recn.tM and math.isnan(recn.beta) and recn.bpairs == SMALL["beta_win"] - 6, (recn.tE, recn.tM, recn.beta, recn.bpairs)
        assert r not in [Ln.recs[int(i)].r for i in cell_run(wn.W, Ln, "E", cfg_of()).pos.rec] and r in [Ln.recs[int(i)].r for i in cell_run(wn.W, Ln, "M", cfg_of()).pos.rec]
        Lq = ni_build(wn.W, wn.ctx, wn.W.days[0], wn.W.days[-1])                                # with the registered 55-pair rule (shrunk) no SEASONED name qualifies: M has no candidate either
        assert not next(q for q in Lq.recs if q.r == r).tM
        # M needs a SEASONED candidate; fewer candidates than NEW names: the rest is unmatched and not traded
        w0, r = world(20, 0)
        rec0 = next(q for q in ni_build(w0.W, w0.ctx, w0.W.days[0], w0.W.days[-1]).recs if q.r == r)
        assert rec0.traded and rec0.tE and not rec0.tM and (rec0.match < 0).all() and rec0.n_seas == 0
        w5, r = world(20, 5)
        L5 = ni_build(w5.W, w5.ctx, w5.W.days[0], w5.W.days[-1])
        rec5 = next(q for q in L5.recs if q.r == r)
        assert rec5.tM and int((rec5.match >= 0).sum()) == 5 and L5.cnt[2024]["unmatched_new"] >= 15 and L5.cnt[2024]["fewer_seasoned_than_new"] >= 1
        runM = cell_run(w5.W, L5, "M", cfg_of())
        assert int((runM.pos.rec == [q.r for q in L5.recs].index(r)).sum()) == 5, "only the matched names are traded in M"
    return True


def t_pipeline():
    """the cells' daily series against plain-python position paths: every NEW short on the split-safe series (the entry at the open of the fill session, marks at every close, the exit at the open of the next fill; a name that stops printing exits at its last mark; a missing close carries the mark), 5 bps of the
    notional at both ends, 3% a year borrow on the prior mark, cell E's hedge = beta x the short notional of ES (the 09:35 prints in and out), cell M's matched SEASONED longs (the match recounted by the all-pairs greedy); each position, each day, the cell, its sides apart, the positions held"""
    with spec(**SMALL):
        w, r1 = pipe_world()
        W, ctx = w.W, w.ctx
        L = ni_build(W, ctx, W.days[0], W.days[-1])
        tr = [q for q in L.recs if q.traded]
        assert len(tr) >= 6 and any(q.r == r1 for q in tr)
        slot, cfg = SPEC["slot"], cfg_of()
        n_pos = 0
        for cell in CELLS:
            runs = {sd: cell_run(W, L, cell, cfg, side=sd) for sd in (0, -1, 1)}
            x0, xs, xo, cnt0 = np.zeros(W.T), np.zeros(W.T), np.zeros(W.T), np.zeros(W.T)
            pos = []
            for ri, q in enumerate(L.recs):
                if not traded(q, cell):
                    continue
                f, x = q.f, q.x
                es = np.array(brute_es_leg(W, f, x, ES_BPS))
                if cell == "E":
                    bb, kk = brute_beta(W, q.r, q.new.tolist())
                    assert abs(q.beta - bb) < 1e-10
                    for i, col in enumerate(q.new):
                        s_ = np.array(brute_position(W, f, x, int(col), -1, COST_BPS, BORROW))
                        o_ = q.beta * slot * es
                        pos.append((ri, int(col), -1, s_.sum() + o_.sum(), s_.sum(), o_.sum()))
                        xs[f:x + 1] += s_
                        xo[f:x + 1] += o_
                        cnt0[f:x + 1] += 1
                else:
                    dvn = [brute_dv(W, q.r, int(c_)) for c_ in q.new]
                    dvs = [brute_dv(W, q.r, int(c_)) for c_ in q.seas]
                    bm = brute_match(dvn, dvs, q.new.tolist(), q.seas.tolist())
                    assert [(-1 if v < 0 else q.n_new + v) for v in bm] == q.match.tolist(), (q.r, bm, q.match.tolist())
                    for i, col in enumerate(q.new):
                        if bm[i] < 0:
                            continue
                        mc = int(q.seas[bm[i]])
                        s_ = np.array(brute_position(W, f, x, int(col), -1, COST_BPS, BORROW))
                        o_ = np.array(brute_position(W, f, x, mc, +1, COST_BPS, BORROW))
                        pos.append((ri, int(col), mc, s_.sum() + o_.sum(), s_.sum(), o_.sum()))
                        xs[f:x + 1] += s_
                        xo[f:x + 1] += o_
                        cnt0[f:x + 1] += 1
            x0 = xs + xo
            run = runs[0]
            assert usd(run.x, x0) and usd(runs[-1].x, xs) and usd(runs[1].x, xo) and usd(run.cnt, cnt0), cell
            assert run.n_pos == len(pos) == len(run.pos.pnl) and run.n_units == len({p_[0] for p_ in pos}) and run.pos.rec.tolist() == [p_[0] for p_ in pos] and run.pos.col.tolist() == [p_[1] for p_ in pos]
            assert usd(run.pos.pnl, [p_[3] for p_ in pos]) and usd(run.pos.short, [p_[4] for p_ in pos]) and usd(run.pos.other, [p_[5] for p_ in pos]) and usd(run.pos.pnl, run.pos.short + run.pos.other)
            if cell == "M":
                assert run.pos.mcol.tolist() == [p_[2] for p_ in pos]
            else:
                assert (run.pos.mcol == -1).all()
            n_pos += len(pos)
        # the planted cases: STOP exits at its last mark inside its hold, HOLE carries its mark over the missing close
        j_stop, j_hole = list(W.syms).index("STOP"), list(W.syms).index("HOLE")
        q1 = next(q for q in L.recs if q.r == r1)
        assert j_stop in q1.new.tolist() and j_hole in q1.new.tolist()
        assert q1.U.st[q1.new.tolist().index(j_stop)] and not q1.U.st[q1.new.tolist().index(j_hole)]
        # the null's M leg never shorts and buys the same name: a drawn name is out of the candidates
    return n_pos


def t_null():
    """the registered null: at every traded rebalance the NEW set is replaced by the same number of SEASONED names drawn at random (never a NEW name), shorted with the same costs / borrow / fills; E's hedge ratio is estimated AGAIN on the drawn basket by the same rule (no ratio: nothing traded that draw and month); M's longs are
    matched AGAIN to the drawn names among the SEASONED names that were not drawn - against a plain-python recount for explicit draws; one stream per reading (seed 20261005), both cells on the same draw, reproducible; a month under the floor draws nothing; the statistic is the MAX over the 2 cells"""
    with spec(**SMALL):
        w, r1 = pipe_world()
        W, ctx = w.W, w.ctx
        L = ni_build(W, ctx, W.days[0], W.days[-1])
        slot, cfg = SPEC["slot"], cfg_of()
        q = next(q_ for q_ in L.recs if q_.r == r1)
        rng = np.random.default_rng(9)
        D = 5
        draw = np.array([rng.choice(q.n_seas, q.n_new, replace=False) for _ in range(D)])
        E, M = null_rec(W, q, draw, cfg)
        H = q.x - q.f + 1
        assert E.shape == M.shape == (D, H)
        es = np.array(brute_es_leg(W, q.f, q.x, ES_BPS))
        for d in range(D):
            cols = q.seas[draw[d]]
            assert not (set(cols.tolist()) & set(q.new.tolist())), "the drawn names are SEASONED, never NEW"
            sh = sum(np.array(brute_position(W, q.f, q.x, int(c_), -1, COST_BPS, BORROW)) for c_ in cols)
            bb, _k = brute_beta(W, q.r, cols.tolist())
            e_want = sh + (bb * q.n_new * slot * es if math.isfinite(bb) else 0.0) if math.isfinite(bb) else np.zeros(H)
            assert usd(E[d], e_want), ("E", d)
            rest = [i for i in range(q.n_seas) if i not in set(draw[d].tolist())]
            dvn = [brute_dv(W, q.r, int(c_)) for c_ in cols]
            dvr = [brute_dv(W, q.r, int(q.seas[i])) for i in rest]
            bm = brute_match(dvn, dvr, cols.tolist(), [int(q.seas[i]) for i in rest])
            m_want = np.zeros(H)
            for i, c_ in enumerate(cols):
                if bm[i] >= 0:
                    m_want += np.array(brute_position(W, q.f, q.x, int(c_), -1, COST_BPS, BORROW)) + np.array(brute_position(W, q.f, q.x, int(q.seas[rest[bm[i]]]), +1, COST_BPS, BORROW))
            assert usd(M[d], m_want), ("M", d)
        # a draw whose basket has no hedge ratio: E trades nothing that draw (a real month would not), M still does
        wn, rn = pipe_world(es_nan=(r1 - 3, r1 - 9, r1 - 15, r1 - 22))
        with spec(min_n=50):                                                                   # (the SEASONED history rule reads the same ES pairs: 52 of 60 here)
            Ln = ni_build(wn.W, wn.ctx, wn.W.days[0], wn.W.days[-1])
        qn = next(q_ for q_ in Ln.recs if q_.r == rn and q_.traded)
        assert not qn.tE and qn.tM
        En, Mn = null_rec(wn.W, qn, draw, cfg)
        assert np.abs(En).sum() == 0.0 and np.abs(Mn).sum() > 0
        # the streams: draws come from the SEASONED names only; the same seed reproduces, another reading's stream differs; both cells use the same draw; the null is zero outside the traded holds
        seen = []
        real = D15.draw_order

        def spy(rng_, nreps, n_pool, m):
            out = real(rng_, nreps, n_pool, m)
            seen.append((n_pool, m, out.copy()))
            return out
        with patched(D15, draw_order=spy):
            acc = ni_null(W, L, 6, 0)
        tr = L_recs(L)
        assert len(seen) == len([q_ for q_ in tr if (q_.tE or q_.tM) and q_.n_seas >= q_.n_new]) and all(npool == q_.n_seas and m == q_.n_new and (o.max() < q_.n_seas) for (npool, m, o), q_ in zip(seen, [q_ for q_ in tr if (q_.tE or q_.tM) and q_.n_seas >= q_.n_new]))
        acc2 = ni_null(W, L, 6, 0)
        acc3 = ni_null(W, L, 6, 1)
        assert set(acc) == set(CELLS) and acc["E"].shape == (6, W.T) and all(np.array_equal(acc[c_], acc2[c_]) for c_ in CELLS) and not np.array_equal(acc["E"], acc3["E"]) and not np.array_equal(acc["M"], acc3["M"])
        rows_held = np.zeros(W.T, bool)
        for q_ in tr:
            rows_held[q_.f:q_.x + 1] = True
        assert not acc["E"][:, ~rows_held].any() and not acc["M"][:, ~rows_held].any() and acc["E"][:, rows_held].any()
        # the first draw of the first traded rebalance is the registered stream's: [SEED, vcode]
        r0 = np.random.default_rng([SEED, 0])
        q0 = [q_ for q_ in tr if (q_.tE or q_.tM) and q_.n_seas >= q_.n_new][0]
        d0 = real(r0, 6, q0.n_seas, q0.n_new)
        assert np.array_equal(seen[0][2], d0) and (SEED, SEED) == (20261005, 20261005)
        # the null of a month the real cells do not trade is not drawn (the floor)
        with spec(floor=10 ** 6):
            Lf = ni_build(W, ctx, W.days[0], W.days[-1])
            accf = ni_null(W, Lf, 4, 0)
            assert not accf["E"].any() and not accf["M"].any() and L_recs(Lf) == []
    # the statistic: the MAX over the 2 cells per draw, p5 / p50 / p95 and each cell's own
    rocE, rocM = np.array([1.0, 5.0, 3.0, np.nan, 9.0]), np.array([2.0, 4.0, 8.0, 7.0, np.nan])
    s = null_summary({"E": rocE, "M": rocM}, {"E": np.array([0.1, 0.2, 0.3, 0.4, 0.5]), "M": np.array([0.5, 0.4, 0.3, 0.2, 0.1])})
    mx = np.fmax(rocE, rocM)
    assert s["draws"] == 5 and s["seed"] == SEED and s["roc_max"] == {"p5": D15.pctl(mx, 5), "p50": D15.pctl(mx, 50), "p95": D15.pctl(mx, 95), "finite": 5} and s["by_cell"]["E"]["finite"] == 4 and s["by_cell"]["M"]["p50"] == D15.pctl(rocM, 50)
    assert s["do_ref_max"]["p95"] == D15.pctl(np.array([0.5, 0.4, 0.3, 0.4, 0.5]), 95) and set(s["do_ref_by_cell"]) == {"E", "M"}
    return True


def close_world(seed=3, n_new=52, n_seas=22, T=330, drift_new=-0.0015):
    """pipe_world's market (SMALL windows; n_seas SEASONED names from the first session, n_new NEW names listed every 4 sessions from row 60) with [HYG-S1]'s cases planted inside the hold of its first rank r1 (fill f1, exit x1): NEW ka a spin-off at f1 + 8 and NEW kb a stock dividend on the EXIT session x1
    (both inside the hold: closed at the close before them), each with the SEASONED name of the nearest dollar volume (A03 / A07, whose own ex-dates are f1 + 12 and x1: the matched longs close too), A05 with its ex-date ON the fill session (bought ex: held), NEW kc a gap flag inside the hold
    (a flag: kept on the split-safe path), cash dividends on A03 after its close (cut) and on NEW kd before nothing (kept) -> (w, r1, f1, x1, names) with names = {ka, kb, kc, kd: the NEW names' symbols}"""
    days = pd.bdate_range("2024-01-01", periods=T)
    r_all, f_all, x_all = M17.rm_schedule(days)
    q1 = [i for i, r_ in enumerate(r_all) if r_ >= 120][0]
    r1, f1, x1 = int(r_all[q1]), int(f_all[q1]), int(x_all[q1])
    new_k = [k for k in range(n_new) if r1 - 45 <= 60 + 4 * k <= r1 - 15]
    ka, kb, kc, kd = new_k[:4]
    rng = np.random.default_rng(seed)
    dv = lambda: float(np.exp(rng.uniform(np.log(2e7), np.log(4e8))))
    cols = [dict(sym=f"A{k:02d}", first=0, beta=float(rng.uniform(0.6, 1.4)), dvol=dv()) for k in range(n_seas)]
    cols += [dict(sym=f"N{k:02d}", first=60 + 4 * k, beta=float(rng.uniform(0.8, 1.8)), drift=drift_new, dvol=dv()) for k in range(n_new)]
    pin = {f"N{ka:02d}": 5.0e7, "A03": 5.0e7 * (1 + 1e-7), f"N{kb:02d}": 7.0e7, "A07": 7.0e7 * (1 + 1e-7)}                  # the greedy match pairs these first (distance $5)
    for c in cols:
        if c["sym"] in pin:
            c["dvol"] = pin[c["sym"]]
    spn = [(f"N{ka:02d}", f1 + 8), (f"N{kb:02d}", x1), ("A03", f1 + 12), ("A05", f1), ("A07", x1)]
    flags = {"gap": [(f"N{kc:02d}", f1 + 5)]}
    dr = {("A03", f1 + 14): 0.5, (f"N{kd:02d}", f1 + 10): 0.4}
    w = ni_world(cols, T=T, seed=seed, flags=flags, spn=spn, dr=dr)
    return w, r1, f1, x1, {"ka": f"N{ka:02d}", "kb": f"N{kb:02d}", "kc": f"N{kc:02d}", "kd": f"N{kd:02d}"}


def t_close():
    """[HYG-S1] MANAGER's hygiene edit S1 (#127, 2026-10-07), post_mode 'close', on a planted world (close_world: spin-off / stock-dividend ex-dates inside the first rank's hold on a NEW short, its matched SEASONED long and a drawn SEASONED name; ex-dates on the fill session (held) and the exit
    session (inside: closed); a hygiene flag inside the hold on a NEW name; cash dividends after a close and before none): no in-hold event removes a name (the NEW and SEASONED sets are the look-ahead reading's), the close rows, the cut unit paths (nothing on rows e .. x, the exit cost on the close's
    row), the cells E and M, their sides and positions, the null's draws (explicit draws recounted by plain python: a drawn closed name is cut too, E's hedge share is not) and evaluate() equal the plain-python recount; the counts by NEW / SEASONED; a calendar split is counted and moves no pool;
    the registered 'remove' (and 'naive') reading carries no exit column and pnl1 is r15's l1_pnl on its units bit for bit; an unknown reading is refused"""
    with spec(**SMALL):
        w, r1, f1, x1, nm = close_world()
        W, ctx = w.W, w.ctx
        lo, hi = W.days[0], W.days[-1]
        slot, cfg = SPEC["slot"], cfg_of()
        Lr, Lk, Lc = ni_build(W, ctx, lo, hi, "remove"), ni_build(W, ctx, lo, hi, "naive"), ni_build(W, ctx, lo, hi, "close")
        sym = lambda ids: [str(W.syms[i]) for i in ids]
        jix = {str(s_): i for i, s_ in enumerate(W.syms)}
        # ---- (1) 'remove' / 'naive' carry no exit column: pnl1 is r15's l1_pnl bit for bit on their units
        n_same = 0
        for Lx in (Lr, Lk):
            for rec in Lx.recs:
                assert rec.close.shape == rec.pool.shape and (rec.close == -1).all(), W.days[rec.r]
                if getattr(rec, "U", None) is not None:
                    assert not hasattr(rec.U, "xc")
                    idx = np.arange(len(rec.pool))
                    for sd in (1, -1):
                        assert np.array_equal(pnl1(rec.U, idx, sd, cfg), D15.l1_pnl(rec.U, idx, sd, cfg)), (W.days[rec.r], sd)
                        n_same += 1
        assert n_same >= 10, n_same
        # ---- (2) the first rank by hand
        rc = next(q for q in Lc.recs if q.r == r1)
        rr = next(q for q in Lr.recs if q.r == r1)
        rk = next(q for q in Lk.recs if q.r == r1)
        assert (rc.f, rc.x) == (f1, x1) and rc.traded and rc.tE and rc.tM
        assert rc.pool.tolist() == rk.pool.tolist() and rc.new.tolist() == rk.new.tolist() and rc.seas.tolist() == rk.seas.tolist() and not rc.naive.any(), "no in-hold event removes a name: the look-ahead reading's sets, never on the raw path"
        assert set(sym(rr.new)) == set(sym(rc.new)) - {nm["ka"], nm["kb"], nm["kc"]} and set(sym(rr.seas)) == set(sym(rc.seas)) - {"A03", "A07"} and "A05" in sym(rr.seas), "the registered reading removed the in-hold names (the flag, the ex-dates inside the hold) - not A05, whose ex-date is the fill session"
        want_close = {nm["ka"]: f1 + 7, nm["kb"]: x1 - 1, "A03": f1 + 11, "A07": x1 - 1}
        got_close = {str(W.syms[c_]): int(e_) for c_, e_ in zip(rc.pool, rc.close) if e_ >= 0}
        assert got_close == want_close and rc.close.dtype == np.int64, (got_close, want_close)
        for q in Lc.recs:                                                                            # every rebalance: the close row = the session before the first ex-date in (f, x] (plain loops)
            Sp = W.Sp_in
            assert q.close.tolist() == [next((t - 1 for t in range(q.f + 1, q.x + 1) if Sp[t, c_]), -1) for c_ in q.pool], W.days[q.r]
        pos = {int(c_): i for i, c_ in enumerate(rc.pool)}
        H = x1 - f1 + 1
        U = rc.U
        for s_, e in ((nm["ka"], f1 + 8), (nm["kb"], x1), ("A03", f1 + 12), ("A07", x1)):
            i, xc = pos[jix[s_]], e - 1 - f1
            assert U.xc[i] == xc and (U.G[i, xc + 1:] == 0).all() and (U.mk[i, xc + 1:] == 0).all() and (U.div[i, xc:] == 0).all(), s_
            assert abs(U.ve[i] - W.Ac[e - 1, jix[s_]] / W.Ao[f1, jix[s_]]) < 1e-15 and not U.st[i], s_
        assert (U.xc == H - 1).sum() == len(rc.pool) - 4 and U.xc[pos[jix["A05"]]] == H - 1 and U.mk[pos[jix["A05"]], -1] != 0.0 and U.div[pos[jix["A03"]]].sum() == 0.0 and U.div[pos[jix[nm["kd"]]]].sum() > 0.0, "A03's dividend (after its close) is cut, NEW kd's is kept"
        # ---- (3) every pool name's path, both sides, four costings, against the plain-python recount (the closed ones cut)
        n_paths = 0
        for q in Lc.recs:
            if getattr(q, "U", None) is None:
                continue
            ix_ = np.arange(len(q.pool))
            for kw in (dict(bps=COST_BPS, borrow=BORROW), dict(bps=10.0, borrow=BORROW), dict(bps=COST_BPS, borrow=0.25), dict(bps=0.0, borrow=0.10)):
                for sd in (1, -1):
                    P = pnl1(q.U, ix_, sd, cfg_of(bps=kw["bps"], borrow=kw["borrow"]))
                    for i, c_ in enumerate(q.pool):
                        want = brute_pos_c(W, q.f, q.x, int(c_), sd, kw["bps"], kw["borrow"], "close") / slot
                        assert usd(P[i], want), (W.days[q.r], str(W.syms[c_]), sd, kw)
                        n_paths += 1
        # ---- (4) the cells E and M: the series, the sides, the positions against the recount; E's hedge share of a closed short runs to the exit (CHOICE)
        for cell in CELLS:
            for sd in (0, -1, 1):
                run = cell_run(W, Lc, cell, cfg, side=sd)
                x0, n0 = brute_cell_series(W, Lc, cell, side=sd, post_mode="close")
                assert usd(run.x, x0) and run.n_pos == n0, (cell, sd)
            assert not usd(cell_run(W, Lc, cell, cfg).x, brute_cell_series(W, Lc, cell)[0]), "the closed names are in the cell: the uncut recount differs"
        runM = cell_run(W, Lc, "M", cfg)
        ri = [q.r for q in Lc.recs].index(r1)
        for k_, a_ in (("ka", "A03"), ("kb", "A07")):
            j_new, j_mt = jix[nm[k_]], jix[a_]
            assert rc.pool[rc.match[pos[j_new]]] == j_mt, ("the planted match", nm[k_], a_)
            row = int(np.flatnonzero((runM.pos.rec == ri) & (runM.pos.col == j_new))[0])
            want = (brute_pos_c(W, f1, x1, j_new, -1, COST_BPS, BORROW, "close") + brute_pos_c(W, f1, x1, j_mt, +1, COST_BPS, BORROW, "close")).sum()
            assert abs(runM.pos.pnl[row] - want) < 1e-7 and runM.pos.mcol[row] == j_mt, (k_, runM.pos.pnl[row], want)
        runE = cell_run(W, Lc, "E", cfg)
        rowE = int(np.flatnonzero((runE.pos.rec == ri) & (runE.pos.col == jix[nm["ka"]]))[0])
        es = np.array(brute_es_leg(W, f1, x1, ES_BPS))
        assert abs(runE.pos.other[rowE] - rc.beta * slot * es.sum()) < 1e-7, "CHOICE: the ES hedge share of a closed NEW short is not cut"
        assert abs(runE.pos.short[rowE] - brute_pos_c(W, f1, x1, jix[nm["ka"]], -1, COST_BPS, BORROW, "close").sum()) < 1e-7
        # ---- (5) the counts by NEW / SEASONED against plain loops; the printout shows them under 'close' only
        cnt = sum((Counter(c_) for c_ in Lc.cnt.values()), Counter())
        want = Counter()
        for q in Lc.recs:
            for pf, ids, cl in (("new_", q.new, q.close[:q.n_new]), ("seas_", q.seas, q.close[q.n_new:])):
                fl = W.hyg(q.r + 1, q.x, ids) if len(ids) else np.zeros((4, 0), bool)
                for k_, h in enumerate(HYG):
                    want[f"{pf}kept_{h}"] += int(fl[k_].sum())
                want[f"{pf}kept_flagged"] += int(fl.any(axis=0).sum())
                want[f"{pf}closed_spin"] += int((cl >= 0).sum())
        for k_ in [k for k in NEW_KEYS + SEAS_KEYS if "kept_" in k and "kept_naive" not in k and "calendar" not in k or k.endswith("closed_spin")]:
            assert cnt[k_] == want[k_], (k_, cnt[k_], want[k_])
        assert cnt["new_closed_spin"] >= 2 and cnt["seas_closed_spin"] >= 2 and cnt["new_kept_gap"] >= 1 and cnt["new_kept_flagged"] >= 1 and cnt["new_kept_calendar_split"] == 0 and not any(k_.startswith(("new_post", "seas_post")) for k_ in cnt if cnt[k_]), dict(cnt)
        buf_c, buf_r = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(buf_c):
            print_counts("L", Lc.cnt)
        with contextlib.redirect_stdout(buf_r):
            print_counts("L", Lr.cnt)
        assert "new_closed_spin" in buf_c.getvalue() and "seas_closed_spin" in buf_c.getvalue() and "closed_spin" not in buf_r.getvalue()
        M17.attach_calendar_splits(W, SimpleNamespace(split=pd.DataFrame({"symbol": [nm["kd"], "A11"], "ex": [W.days[f1 + 3], W.days[f1 + 3]], "type": ["forward_split", "reverse_split"]})))
        Lcs, Lrs = ni_build(W, ctx, lo, hi, "close"), ni_build(W, ctx, lo, hi, "remove")
        cs = sum((Counter(c_) for c_ in Lcs.cnt.values()), Counter())
        assert cs["new_kept_calendar_split"] == 1 and cs["seas_kept_calendar_split"] == 1 and [q.pool.tolist() for q in Lcs.recs] == [q.pool.tolist() for q in Lc.recs] and [q.pool.tolist() for q in Lrs.recs] == [q.pool.tolist() for q in Lr.recs], "a calendar split on the grid is counted under 'close' and moves no pool; 'remove' ignores it"
        del W.CSPL, W.cscs
        # ---- (6) the null: explicit draws (the closed SEASONED names among them) recounted by plain python; E re-hedged on the drawn basket (the hedge share of a closed name runs to the exit), M re-matched
        i03, i07 = list(rc.seas).index(jix["A03"]), list(rc.seas).index(jix["A07"])
        rng = np.random.default_rng(9)
        draw = np.array([[i03, i07] + [int(v) for v in rng.permutation([i for i in range(rc.n_seas) if i not in (i03, i07)])[:rc.n_new - 2]] for _ in range(3)] + [list(rng.choice(rc.n_seas, rc.n_new, replace=False)) for _ in range(3)])
        E, M = null_rec(W, rc, draw, cfg)
        for d in range(len(draw)):
            cols_ = rc.seas[draw[d]]
            sh = sum(brute_pos_c(W, f1, x1, int(c_), -1, COST_BPS, BORROW, "close") for c_ in cols_)
            bb, _k = brute_beta(W, r1, cols_.tolist())
            assert usd(E[d], sh + bb * rc.n_new * slot * es if math.isfinite(bb) else np.zeros(H)), ("E", d)
            rest = [i for i in range(rc.n_seas) if i not in set(draw[d].tolist())]
            bm = brute_match([brute_dv(W, r1, int(c_)) for c_ in cols_], [brute_dv(W, r1, int(rc.seas[i])) for i in rest], cols_.tolist(), [int(rc.seas[i]) for i in rest])
            m_want = np.zeros(H)
            for i, c_ in enumerate(cols_):
                if bm[i] >= 0:
                    m_want += brute_pos_c(W, f1, x1, int(c_), -1, COST_BPS, BORROW, "close") + brute_pos_c(W, f1, x1, int(rc.seas[rest[bm[i]]]), +1, COST_BPS, BORROW, "close")
            assert usd(M[d], m_want), ("M", d)
        with patched(THIS, pnl1=lambda U_, ix_, sd_, cfg_: D15.l1_pnl(U_, ix_, sd_, cfg_)):
            E0, M0 = null_rec(W, rc, draw, cfg)
        assert not usd(E[:3], E0[:3]) and not usd(M[:3], M0[:3]), "the first draws hold the closed names: r15's l1_pnl would book their exit cost on the last row"
        acc = ni_null(W, Lc, 4, 0)
        assert set(acc) == set(CELLS) and acc["E"].shape == (4, W.T) and acc["E"][:, f1:x1 + 1].any() and acc["M"][:, f1:x1 + 1].any()
        # ---- (7) evaluate() on the reading, with a null: every cell's net is the recount's, the registered reading differs by the in-hold names
        B, S12 = M17.synth_book(seed=3, hi="2026-06-30")
        rb = DV.mk_ref(B)
        SN, SRN = restrict_stretch(S12, B.raw, B.index, WFN, PRE_END), restrict_stretch(rb.S, rb.raw, B.index, WFN, PRE_END)
        rows = A13.book_rows(B, W)
        with patched(THIS, manifest_sha=lambda: "0" * 64):
            res, obj = evaluate(W, ctx, B, SN, rb, SRN, rows, "close", 6, 0, full=True)
            res_r, _obj_r = evaluate(W, ctx, B, SN, rb, SRN, rows, "remove", 0, 0, full=False)
        assert res["variant"] == "close" and res["null"]["draws"] == 6 and res_r["null"] is None
        for cell in CELLS:
            x0, n0 = brute_cell_series(W, obj.legs, cell, post_mode="close")
            c = res["cells"][cell]
            assert abs(c["base"]["net"] - float(x0.sum())) < 1e-6 and c["base"]["n_pos"] == n0 and usd(obj.series[cell][0][rows], x0), (cell, c["base"]["net"], x0.sum())
            assert abs(c["stress"]["10 bps"]["net"] - float(brute_cell_series(W, obj.legs, cell, bps=10.0, post_mode="close")[0].sum())) < 1e-6 and abs(c["sides"]["short side only"]["net"] - float(brute_cell_series(W, obj.legs, cell, side=-1, post_mode="close")[0].sum())) < 1e-6
        assert any(abs(res["cells"][c]["base"]["net"] - res_r["cells"][c]["base"]["net"]) > 1e-6 for c in CELLS), "the in-hold names move the P&L"
        # ---- (8) a reading this family does not run is refused
        for bad in ("keep", "closed", ""):
            try:
                ni_one(W, ctx, r1, f1, x1, bad, units=False)
                raise AssertionError(f"post_mode {bad!r} must be refused")
            except ValueError as e:
                assert "one of" in str(e)
    return n_paths


def capture(fn, *a, **kw):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        fn(*a, **kw)
    return buf.getvalue()


def t_beta_rule():
    """[N2] the realised beta of a cell (its daily $ P&L per $ of short notional on ES's daily return, an intercept and a slope, over the days it holds a position) recovers a planted slope; the 0.20 rule: |beta| <= 0.20 is credited (the edge is in), above it - and a NaN - is not"""
    g = beta_gate
    assert g(0.20)["credited"] is True and g(-0.20)["credited"] is True and g(0.0)["credited"] is True and g(0.2000001)["credited"] is False and g(-0.2000001)["credited"] is False
    assert g(float("nan"))["credited"] is False and g(float("inf"))["credited"] is False and g(0.1) == {"beta": 0.1, "limit": 0.20, "credited": True}
    B, _S12 = M17.synth_book(seed=3, hi="2026-06-30")
    w, _r1 = pipe_world()
    W = w.W
    rows = A13.book_rows(B, W)
    m = np.nan_to_num(W.es.ret)
    cnt = np.zeros(W.T)
    cnt[100:200] = 30.0
    for slope in (0.7, -0.9, 0.05):
        x = np.zeros(W.T)
        x[100:200] = SPEC["slot"] * 30.0 * slope * m[100:200]
        bt = realised_beta(B, rows, W, D15.to_B(x, rows, B.n), D15.to_B(cnt, rows, B.n), WFN, PRE_END)
        n_es = int(np.isfinite(W.es.ret[100:200]).sum())
        assert abs(bt["beta"] - slope) < 1e-9 and bt["n"] == n_es, (slope, bt)
        assert g(bt["beta"])["credited"] is (abs(slope) <= 0.20)
    # an intercept does not matter, noise moves it a little, the notional is the DAY's: a month of 30 names and one of 60 weigh a day each
    rng = np.random.default_rng(1)
    cnt2 = np.zeros(W.T)
    cnt2[100:150], cnt2[150:200] = 30.0, 60.0
    x2 = np.zeros(W.T)
    x2[100:200] = SPEC["slot"] * cnt2[100:200] * (0.0003 + 0.4 * m[100:200] + rng.normal(0, 0.0004, 100))
    bt2 = realised_beta(B, rows, W, D15.to_B(x2, rows, B.n), D15.to_B(cnt2, rows, B.n), WFN, PRE_END)
    assert abs(bt2["beta"] - 0.4) < 0.05 and bt2["t_nw"] > 5.0, bt2
    # no position, a flat ES, a short sample: NaN, never an exception
    z = np.zeros(B.n)
    assert math.isnan(realised_beta(B, rows, W, z, z, WFN, PRE_END)["beta"]) and realised_beta(B, rows, W, z, z, WFN, PRE_END)["n"] == 0
    c3 = np.zeros(W.T)
    c3[100:104] = 5.0
    assert math.isnan(realised_beta(B, rows, W, D15.to_B(c3 * 100.0, rows, B.n), D15.to_B(c3, rows, B.n), WFN, PRE_END)["beta"])
    # the stretch: days outside [lo, hi] are not used
    bt4 = realised_beta(B, rows, W, D15.to_B(np.where(np.arange(W.T) < 150, SPEC["slot"] * 30.0 * 0.5 * m, 7.0 * SPEC["slot"] * 30.0 * m), rows, B.n), D15.to_B(cnt, rows, B.n), W.days[100], W.days[149])
    assert abs(bt4["beta"] - 0.5) < 1e-9 and bt4["n"] == int(np.isfinite(W.es.ret[100:150]).sum())
    return True


def t_tables():
    """the cohort table (the listing-year cohort of every name-month, [N5]), the path by months since listing ([X2]: every mark of every name-month in its age month), the NEW-names table, the 20 largest gains and the correlation helper, against plain-python recounts on planted data"""
    with spec(**SMALL):
        w, r1 = pipe_world(start="2024-10-01")
        W, ctx = w.W, w.ctx
        L = ni_build(W, ctx, W.days[0], W.days[-1])
        cfg = cfg_of()
        li = brute_listing(W)
        assert {W.days[l_[1]].year for l_ in li if l_[1] >= 0} == {2024, 2025}, "the planted listings straddle a year boundary"
        for cell in CELLS:
            run = cell_run(W, L, cell, cfg)
            co = cohort_table(W, ctx, run)
            want = defaultdict(lambda: {"name_months": 0, "names": set(), "net": 0.0, "short": 0.0, "other": 0.0})
            for i in range(len(run.pos.pnl)):
                y = W.days[li[int(run.pos.col[i])][1]].year
                d = want[y]
                d["name_months"] += 1
                d["names"].add(int(run.pos.col[i]))
                d["net"] += run.pos.pnl[i]
                d["short"] += run.pos.short[i]
                d["other"] += run.pos.other[i]
            assert sorted(co) == sorted(want) == [2024, 2025], (cell, sorted(co))
            for y, d in want.items():
                assert co[y]["name_months"] == d["name_months"] and co[y]["names"] == len(d["names"]) and abs(co[y]["net"] - d["net"]) < 1e-6 and abs(co[y]["short"] - d["short"]) < 1e-6 and abs(co[y]["other"] - d["other"]) < 1e-6, (cell, y)
            assert abs(sum(v["net"] for v in co.values()) - run.x.sum()) < 1e-6, "the cohorts add up to the cell"
            ps = cohort_table(W, ctx, cell_run(W, L, cell, cfg, side=-1))
            assert all(abs(ps[y]["other"]) < 1e-12 and abs(ps[y]["net"] - co[y]["short"]) < 1e-6 for y in co), "the short side alone"
            # the path by months since listing, recounted position by position, day by day
            for lo in (W.days[0], W.days[r1 + 7]):
                path = age_table(W, L, cell, cfg, lo)
                r0 = int(W.days.searchsorted(lo, side="left"))
                acc = defaultdict(lambda: [0, 0.0, 0.0])
                for q in L.recs:
                    if not traded(q, cell):
                        continue
                    es = brute_es_leg(W, q.f, q.x, ES_BPS)
                    if cell == "M":
                        mt = brute_match([brute_dv(W, q.r, int(c_)) for c_ in q.new], [brute_dv(W, q.r, int(c_)) for c_ in q.seas], q.new.tolist(), q.seas.tolist())
                    for i, col in enumerate(q.new):
                        if cell == "M" and mt[i] < 0:
                            continue
                        s_ = brute_position(W, q.f, q.x, int(col), -1, COST_BPS, BORROW)
                        o_ = q.beta * SPEC["slot"] * es if cell == "E" else brute_position(W, q.f, q.x, int(q.seas[mt[i]]), +1, COST_BPS, BORROW)
                        for h in range(q.x - q.f + 1):
                            t = q.f + h
                            if t < r0:
                                continue
                            a = acc[(t - li[int(col)][1]) // SPEC["month"]]
                            a[0] += 1
                            a[1] += s_[h]
                            a[2] += o_[h]
                assert sorted(path) == sorted(acc), (cell, sorted(path), sorted(acc))
                for q_, v in acc.items():
                    assert path[q_]["days"] == v[0] and abs(path[q_]["short"] - v[1]) < 1e-6 and abs(path[q_]["other"] - v[2]) < 1e-6, (cell, q_)
                if lo == W.days[0]:
                    assert abs(sum(v["short"] + v["other"] for v in path.values()) - run.x.sum()) < 1e-6, "every mark is in a month: the rows add up to the cell"
                assert all(0 <= m_ <= (SMALL["new_hi"] + 25) // SPEC["month"] for m_ in path), (cell, sorted(path))
            tg = top_gains(W, ctx, run, L, n=20)
            assert [x_["pnl"] for x_ in tg] == sorted(run.pos.pnl.tolist(), reverse=True)[:20] and tg[0]["rank"] == 1 and len(tg) == 20
            x0 = tg[0]
            i0 = int(np.argmax(run.pos.pnl))
            assert x0["symbol"] == str(W.syms[run.pos.col[i0]]) and x0["listed"] == f"{W.days[li[int(run.pos.col[i0])][1]]:%Y-%m-%d}" and x0["age_at_rank"] == L.recs[int(run.pos.rec[i0])].r - li[int(run.pos.col[i0])][1]
            assert (x0["match"] != "") == (cell == "M")
        hp = {q_: {"days": 10 + q_, "short": 100.0 * q_, "other": -3.0 * q_} for q_ in (0, 5, 6, 11, 12, 23, 24, 25)}                         # the draft's 6-12 vs 12-24 split of the path, on a hand-made path
        sp_ = age_split(hp)
        assert list(sp_) == ["<6 months", "6-12 months", "12-24 months", "24+ months"] and sp_["<6 months"]["days"] == 10 + 15 and sp_["6-12 months"]["days"] == 16 + 21 and sp_["12-24 months"]["days"] == 22 + 33 and sp_["24+ months"]["days"] == 34 + 35
        assert abs(sp_["6-12 months"]["short"] - 1700.0) < 1e-9 and abs(sp_["12-24 months"]["other"] + 105.0) < 1e-9 and abs(sp_["24+ months"]["net"] - 97.0 * 49) < 1e-9 and sum(v["days"] for v in sp_.values()) == sum(v["days"] for v in hp.values())
        assert age_split({}) == {lab: {"days": 0, "short": 0.0, "other": 0.0, "net": 0.0} for lab, _a, _b in AGE_BUCKETS}
        nt = new_table(W, L)
        assert len(nt) == len(L.recs) and [r_["new"] for r_ in nt] == [q.n_new for q in L.recs] and [r_["traded"] for r_ in nt] == [q.traded for q in L.recs] and [r_["age_window_names"] for r_ in nt] == [q.newage for q in L.recs]
        for r_, q in zip(nt, L.recs):
            assert r_["rank"] == f"{W.days[q.r]:%Y-%m-%d}" and sum(r_["by_cohort"].values()) == q.n_new and r_["seasoned_candidates"] == q.n_seas and r_["hedge_ratio"] == q.beta or (math.isnan(q.beta) and math.isnan(r_["hedge_ratio"]))
    a, b = np.array([1.0, 2.0, 3.0, 4.0, np.nan]), np.array([2.0, 1.0, 5.0, 3.0, 9.0])
    assert abs(corr_with(np.r_[a, 0, 0], np.r_[b, 1, 1], np.arange(5)) - np.corrcoef(a[:4], b[:4])[0, 1]) < 1e-12 and math.isnan(corr_with(np.ones(5), b, np.arange(5))) and math.isnan(corr_with(a, b, np.arange(1)))
    return True


def t_x1():
    """[X1] the REFERENCE book (#463 + 0.264 x RES) through r18's loader on a stub of RESMOM's line file (never the real one), the map's drawdown days from 2018-02 on (restrict_stretch), A2 as an INCREMENTAL report with c by volatility over 2018-02-01 .. 2020-01-31 against #463's std, 0.5c and 2c, the plain #463 + c x cell row, the beta rule (a cell outside +-0.20 can never pass),
    MANAGER #70's gate basis (the cell's DO on the reference's drawdown days and without its best episode)"""
    B, S12 = M17.synth_book(seed=3, hi="2026-06-30")
    k = np.flatnonzero(B.mask(WF0, PRE_END))
    rb = DV.mk_ref(B)
    with tempfile.TemporaryDirectory() as td:
        p = os.path.join(td, "resmom_cells_daily_wf.csv")
        sha = DV.write_ref_csv(p, B, rb.res[k])
        with patched(DV, REF_CSV=p, REF_SHA=sha):
            ref = DV.ref_load(B, check_facts=False)
            refused(lambda: DV.ref_load(B, check_facts=True), "does not reproduce its registered WF numbers", "nothing computed, lockbox NOT read")
            with patched(THIS, CHECK_BOOK=True):
                refused(lambda: DV.ref_load(B, check_facts=THIS.CHECK_BOOK), "does not reproduce its registered WF numbers")
        with patched(DV, REF_CSV=p, REF_SHA="0" * 64):
            refused(lambda: DV.ref_load(B, check_facts=False), "is not the registered")
        with patched(DV, REF_CSV=os.path.join(td, "absent.csv"), REF_SHA=sha):
            refused(lambda: DV.ref_load(B, check_facts=False), "is not on file")
    assert ref.n_rows == len(k) and np.allclose(ref.raw[k], np.asarray(B.raw)[k] + 0.264 * rb.res[k], atol=1e-5)
    # the map's drawdown days from 2018-02 on: the same book's episodes, the days before the cell's WF dropped
    x_early = np.random.default_rng(2).normal(30.0, 400.0, B.n)
    ds = B.index
    x_early[(ds >= "2017-03-01") & (ds <= "2017-04-28")] -= 1500.0                           # a deep drawdown BEFORE 2018-02
    x_early[(ds >= "2019-03-01") & (ds <= "2019-03-29")] -= 1500.0                           # and one after it
    Sf = M12.Stretch(x_early, ds, None, WF0, PRE_END)
    Sr = restrict_stretch(Sf, x_early, ds, WFN, PRE_END)
    kk = np.flatnonzero(np.asarray((ds >= WFN) & (ds <= PRE_END)))
    assert Sr.T == len(kk) and (Sr.rows == kk).all() and Sr.dates[0] >= WFN and (Sr.dd == Sf.dd[np.asarray(ds[Sf.rows] >= WFN)]).all()
    before = int(Sf.dd[np.asarray(ds[Sf.rows] < WFN)].sum())
    assert before >= 20 and Sf.n_dd_days - Sr.n_dd_days == before and Sr.n_dd_days >= 15, (before, Sf.n_dd_days, Sr.n_dd_days)
    cell = np.random.default_rng(3).normal(10.0, 100.0, B.n)
    sm = D15.seat_measure(Sr, cell)
    want = float(cell[kk][Sr.dd].sum()) / -float(x_early[kk][Sr.dd].sum())
    assert abs(sm["DO"] - want) < 1e-9 and sm["dd_days"] == Sr.n_dd_days
    SRN = restrict_stretch(ref.S, ref.raw, ds, WFN, PRE_END)
    SN = restrict_stretch(S12, B.raw, ds, WFN, PRE_END)
    assert SRN.n_dd_days <= ref.S.n_dd_days and SN.n_dd_days <= S12.n_dd_days and (SRN.dd == ref.S.dd[np.asarray(ds[ref.S.rows] >= WFN)]).all()
    # A2: the incremental report over the reference
    rng = np.random.default_rng(8)
    hedge, bad = np.zeros(B.n), np.zeros(B.n)
    kw = np.flatnonzero(B.mask(WFN, PRE_END))
    hedge[kw] = 0.4 * np.maximum(-ref.raw[kw], 0.0) + rng.normal(0.0, 40.0, len(kw))
    bad[kw] = rng.normal(-60.0, 500.0, len(kw))
    mw = np.asarray(B.mask(*A2_WIN))
    ref_s = DV.plain_stats(ref.raw[kw], ds[kw])
    for name, x, want_pass in (("hedge", hedge, True), ("losing", bad, False)):
        for beta_ok in (True, False):
            a2 = a2_report(B, x, ref, beta_ok)
            sb, sc = float(np.std(np.asarray(B.raw)[mw], ddof=1)), float(np.std(x[mw], ddof=1))
            c = 0.25 * sb / sc
            assert a2["window"] == ["2018-02-01", "2020-01-31"] and a2["rows"] == int(mw.sum()) and a2["target"] == 0.25 and abs(a2["c"] - c) <= 1e-12 * c and abs(a2["std_book"] - sb) <= 1e-12 * sb and abs(a2["std_cell"] - sc) <= 1e-12 * sc
            assert a2["at_half_c"]["c"] == 0.5 * a2["c"] and a2["at_double_c"]["c"] == 2.0 * a2["c"]
            assert a2["incremental_pass_before_the_beta_rule"] is want_pass and a2["beta_rule_ok"] is beta_ok and a2["incremental_pass"] is (want_pass and beta_ok) and a2["book_shadow_line"] is a2["incremental_pass"], (name, beta_ok)
            # the registered comparison is on the reference's own WF (2016-07 .. 2025-06): its ROC and Sortino against the reference + c x cell, recounted
            kfull = np.flatnonzero(B.mask(WF0, PRE_END))
            wref = DV.plain_stats(ref.raw[kfull], ds[kfull])
            wbook = DV.plain_stats((ref.raw + c * x)[kfull], ds[kfull])
            assert abs(a2["reference"]["roc"] - wref["roc"]) < 1e-8 and abs(a2["roc"] - wbook["roc"]) < 1e-8 and abs(a2["sortino"] - wbook["sortino"]) < 1e-9
            assert a2["incremental_pass_before_the_beta_rule"] is bool(wbook["roc"] > wref["roc"] and wbook["sortino"] > wref["sortino"])
            wp = DV.plain_stats((np.asarray(B.raw) + c * x)[kfull], ds[kfull])
            assert abs(a2["plain_463"]["roc"] - wp["roc"]) < 1e-8 and a2["plain_463"]["c"] == a2["c"]
            os_ = a2["own_stretch"]
            assert os_["window"] == ["2018-02-01", "2025-06-29"] and abs(os_["reference_alone"]["roc"] - ref_s["roc"]) < 1e-8 and abs(os_["with_c"]["roc"] - DV.plain_stats((ref.raw + c * x)[kw], ds[kw])["roc"]) < 1e-8
    ah, al = a2_report(B, hedge, ref, True), a2_report(B, bad, ref, True)
    assert ah["roc_gain"] > 0 and ah["sortino_gain"] > 0 and al["roc_gain"] < 0 and al["sortino_gain"] < 0, (ah["roc_gain"], al["roc_gain"])
    az = a2_report(B, np.zeros(B.n), ref, True)
    assert not math.isfinite(az["c"]) and az["incremental_pass"] is False and "own_stretch" not in az and az["beta_rule_ok"] is True
    assert plain_a2(B, hedge)["c"] == ah["c"] and plain_a2(B, hedge)["window"] == ["2018-02-01", "2020-01-31"]
    # MANAGER #70's gate basis: the cell's P&L over the reference's qualifying episodes, and without its best episode
    eps = [{"cell_pnl": 100.0, "book_pnl": -300.0, "first_dd_day": "2019-01-02", "trough": "2019-01-10"}, {"cell_pnl": 500.0, "book_pnl": -200.0, "first_dd_day": "2020-03-03", "trough": "2020-03-27"}, {"cell_pnl": -50.0, "book_pnl": -100.0, "first_dd_day": "2022-05-02", "trough": "2022-05-20"}]
    g = episode_gate(None, eps)
    assert g == {"episodes": 3, "best_episode": "2020-03-03 .. 2020-03-27", "best_episode_pnl": 500.0, "DO_ex_best_episode": (100.0 - 50.0) / 400.0}, g
    g0 = episode_gate(None, [])
    assert g0["episodes"] == 0 and g0["best_episode"] is None and math.isnan(g0["DO_ex_best_episode"])
    g1 = episode_gate(None, [{"cell_pnl": 5.0, "book_pnl": -10.0, "first_dd_day": "a", "trough": "b"}])
    assert g1["episodes"] == 1 and math.isnan(g1["DO_ex_best_episode"]), "no loss left once the best episode is out: no DO"
    tab = D15.episodes_table(ref.S, hedge)
    assert len(tab) == len(ref.S.qual) >= 1 and abs(sum(t_["cell_pnl"] for t_ in tab) - float(hedge[ref.S.rows][ref.S.dd].sum())) < 1e-6
    return True


def tbis_frame(rows):
    return pd.DataFrame(rows, columns=["symbol", "day", "price_ratio", "vol_ratio", "split_like"]).assign(day=lambda d: pd.to_datetime(d["day"]))


def t_files():
    """the hand audit: newissue_audit.csv (symbol, date = the FILL session, cell, verdict keep | data_event) refuses what it cannot read, a data_event removes that name-month from NEW AND SEASONED (both cells and the null's pool) before anything is computed, a row that matches nothing refuses, one that removed nothing is
    reported; the 50 largest contributors with what the hand needs (listing session, its [N4] count, cohort, the calendar's rows, the split factor, TBIS, the asset status); the candidate pick (E first); the audit status"""
    with tempfile.TemporaryDirectory() as td:
        ap = os.path.join(td, "newissue_audit.csv")
        with patched(THIS, OUT=td):
            assert read_audit() is None
            def put(txt):
                with open(ap, "w", newline="\n") as f_:
                    f_.write(txt)
            put("symbol,date,cell,verdict,note\nN01,2024-06-03,e,KEEP,fine\nN02, 2024-06-03 ,M,data_event,bad print\n")
            a = read_audit()
            assert a["cell"].tolist() == ["E", "M"] and a["verdict"].tolist() == ["keep", "data_event"] and a["symbol"].tolist() == ["N01", "N02"] and a["date"].tolist() == [TS("2024-06-03")] * 2
            put("symbol,date,cell,verdict\nN01,2024-06-03,E,maybe\n")
            refused(read_audit, "newissue_audit.csv line(s) [2]", "nothing computed")
            put("symbol,date,cell,verdict\nN01,not a date,E,keep\n")
            refused(read_audit, "newissue_audit.csv line(s) [2]")
            put("symbol,date,cell,verdict\nN01,2024-06-03,X,keep\n")
            refused(read_audit, "outside ['E', 'M']")
            put("symbol,date,verdict\nN01,2024-06-03,keep\n")
            refused(read_audit, "lacks the column", "'cell'")
            put("symbol,date,cell,verdict\n,2024-06-03,E,keep\n")
            refused(read_audit, "newissue_audit.csv line(s) [2]")
    # apply_audit on a world: the data_event removes the name-month from NEW and from SEASONED, the null's pool included (the pool is built from the same sets)
    with spec(**SMALL):
        w, r1 = pipe_world()
        W, ctx = w.W, w.ctx
        f, x = fx_of(W.days, r1)
        base, _c = ni_one(W, ctx, r1, f, x, "remove", units=False)
        nn, ss = str(W.syms[base.new[0]]), str(W.syms[base.seas[0]])
        d = f"{W.days[f]:%Y-%m-%d}"
        au = pd.DataFrame({"symbol": [nn, ss, "A00"], "date": pd.to_datetime([d, d, W.days[f + 1]]), "cell": ["E", "M", "E"], "verdict": ["data_event", "data_event", "keep"], "note": ""})
        n = apply_audit(W, au)
        assert n == {"rows": 3, "keep": 1, "data_event": 2} and W.aud1.sum() == 2
        rec, _c = ni_one(W, ctx, r1, f, x, "remove", units=False)
        assert nn not in set(map(str, W.syms[rec.new])) and ss not in set(map(str, W.syms[rec.seas])) and rec.n_new == base.n_new - 1 and rec.n_seas == base.n_seas - 1 and sorted(map(str, W.syms[rec.pool])) == sorted(set(map(str, W.syms[base.pool])) - {nn, ss})
        assert M17.unused_audit_rows(W, au) == [], "both data events removed a name-month"
        bad = pd.DataFrame({"symbol": ["A00"], "date": pd.to_datetime([W.days[f + 3]]), "cell": ["E"], "verdict": ["data_event"], "note": ""})
        n2 = apply_audit(W, bad)
        assert n2["data_event"] == 1 and M17.unused_audit_rows(W, bad) == [f"A00 {W.days[f + 3]:%Y-%m-%d} E"], M17.unused_audit_rows(W, bad)
        unk = pd.DataFrame({"symbol": ["ZZZ"], "date": pd.to_datetime([d]), "cell": ["E"], "verdict": ["data_event"], "note": ""})
        msg = refused(lambda: apply_audit(W, unk), "newissue_audit.csv", "match no session or no name", "lockbox NOT read")
        assert "resmom_audit" not in msg
        assert apply_audit(W, None) == {"rows": 0, "keep": 0, "data_event": 0} and not W.aud1.any()
        # the candidates
        with spec(**SMALL):
            L0 = ni_build(W, ctx, W.days[0], W.days[-1])
        q0 = next(q_ for q_ in L0.recs if q_.r == r1)
        nm_spin, nm_chg = str(W.syms[q0.new[0]]), str(W.syms[q0.new[1]])
        spin = [(nm_spin, "PAR", "2025-12-31")]                                                  # (a calendar row dated after the data: it is on the candidate's list and excludes nothing)
        chg = [("OLDX", nm_chg, f"{W.days[5]:%Y-%m-%d}")]                                         # (outside the 1-month window of every rank: the name still trades)
        w2 = ni_world(w.cols, T=330, seed=3, spin=spin, chg=chg)
        W2, ctx2 = w2.W, w2.ctx
        with spec(**{**SMALL, "nc_months": 1}):
            L = ni_build(W2, ctx2, W2.days[0], W2.days[-1])
            run = cell_run(W2, L, "M", cfg_of())
            tb = tbis_frame([(nm_chg, f"{W2.days[r1 + 5]:%Y-%m-%d}", 0.5, 2.0, True), ("ZZZ", "2024-06-03", 0.5, 2.0, True)])
            cands = ni_candidate_rows(W2, ctx2, L, "M", run, tb, {nm_chg: "active", nm_spin: "inactive"}, n=10 ** 6)
            assert len(cands) == len(run.pos.pnl) and [c_["pnl"] for c_ in cands] == sorted(run.pos.pnl.tolist(), reverse=True) and [c_["rank"] for c_ in cands] == list(range(1, len(cands) + 1))
            assert len(ni_candidate_rows(W2, ctx2, L, "M", run, tb, {}, n=50)) == 50
            li = brute_listing(W2)
            seen = set()
            for c_ in cands:
                j = list(W2.syms).index(c_["symbol"])
                seen.add(c_["symbol"])
                assert c_["listing_session"] == f"{W2.days[li[j][1]]:%Y-%m-%d}" and c_["n4_sessions_with_close_and_volume_of_the_next_20"] == li[j][3] and c_["cohort"] == W2.days[li[j][1]].year and c_["cell"] == "M"
                assert abs(c_["pnl"] - c_["short_pnl"] - c_["other_pnl"]) < 1e-9 and c_["factor_ratio_listing_to_exit"] == 1.0 and abs(c_["max_overnight_raw_ratio_in_hold"] - 1.0) < 1e-12 and c_["match"] != "" and c_["date"] < c_["exit"]
                assert c_["asset_status"] == {nm_chg: "active", nm_spin: "inactive"}.get(c_["symbol"], "unknown")
                assert (c_["calendar_spin_off_rows"] != "") == (c_["symbol"] == nm_spin) and (c_["calendar_name_change_rows"] != "") == (c_["symbol"] == nm_chg)
                if c_["symbol"] == nm_spin:
                    assert c_["calendar_spin_off_rows"] == "2025-12-31 spin-off of PAR"
                if c_["symbol"] == nm_chg:
                    assert c_["calendar_name_change_rows"] == f"{W2.days[5]:%Y-%m-%d} OLDX>{nm_chg}"
                    inside = c_["listing_session"] <= f"{W2.days[r1 + 5]:%Y-%m-%d}" <= c_["exit"]
                    assert (c_["tbis_price_ratio"] == 0.5) == inside and (c_["tbis_vol_ratio"] == 2.0) == inside and (c_["tbis_split_like"] == "True") == inside
            assert {nm_spin, nm_chg} <= seen, "the planted names are among the contributors"
            assert all(isinstance(v, (int, float, str, bool, type(None))) for c_ in cands for v in c_.values())
            assert ni_candidate_rows(W2, ctx2, L, "M", SimpleNamespace(pos=None), None, {}) == []
            # the audit status (information only): the listed rows found in the audit file by symbol + fill date
            au2 = pd.DataFrame({"symbol": [cands[0]["symbol"], cands[1]["symbol"]], "date": pd.to_datetime([cands[0]["date"], "2001-01-01"]), "cell": "M", "verdict": "keep", "note": ""})
            st = audit_status({"M": cands, "E": []}, au2)
            assert st["M"] == {"listed": len(cands), "audited": 1, "audit_complete": False} and st["E"]["listed"] == 0 and audit_status({"M": cands}, None)["M"]["audited"] == 0
    # the candidate: E is the PRIMARY cell
    cells = {"E": {"PASS": True}, "M": {"PASS": True}}
    assert stage_a_flow(cells) == (["E", "M"], "E") and stage_a_flow({"E": {"PASS": False}, "M": {"PASS": True}}) == (["M"], "M") and stage_a_flow({"E": {"PASS": False}, "M": {"PASS": False}}) == ([], None) and pick_candidate(["M", "E"]) == "E" and pick_candidate([]) is None
    return True


def t_counts_only():
    """the dryload's mode computes COUNTS only: no hedge ratio, no dollar volume, no match, no unit path - proved by making each of them raise - and its NEW / SEASONED sets, floor and basket-ES pair counts equal the full build's; the leg record the dryload prints (leg_counts) equals a plain-python recount"""
    with spec(**SMALL):
        w, r1 = pipe_world()
        W = w.W
        full = ni_build(W, w.ctx, W.days[0], W.days[-1])
        cx = make_ctx(W, w.extra, counts_only=True)

        def boom(*a, **k):
            raise AssertionError("a counts-only build computed a number it must not")
        with patched(THIS, basket_beta=boom, basket_beta_many=boom, dv20=boom, match_nearest=boom), patched(M17, rm_units=boom):
            cnt_leg = ni_build(W, cx, W.days[0], W.days[-1], units=False)
        assert len(cnt_leg.recs) == len(full.recs)
        for a, b in zip(cnt_leg.recs, full.recs):
            assert (a.r, a.f, a.x) == (b.r, b.f, b.x) and a.new.tolist() == b.new.tolist() and a.seas.tolist() == b.seas.tolist() and a.traded == b.traded and a.n_new == b.n_new and a.newage == b.newage
            assert not hasattr(a, "U") and a.match.size == 0 and math.isnan(a.beta)
            if a.traded:
                assert a.bpairs == basket_pairs(W, a.r, a.new) == b.bpairs and a.tE == b.tE and a.tM == b.tM
        for y in full.cnt:
            for key in ("new_age", "new_pool", "seas_pool", "new_names", "seas_names", "below_floor", "rebalances", "n4_failed_names"):
                assert cnt_leg.cnt[y][key] == full.cnt[y][key], (y, key)
        lc = leg_counts(W, cnt_leg)
        n = [q.n_new for q in full.recs]
        assert lc["rebalances"] == len(full.recs) and lc["traded"] == sum(q.traded for q in full.recs) and lc["new_per_rebalance"] == [min(n), float(np.median(n)), max(n)] and lc["below_floor"] == [f"{W.days[q.r]:%Y-%m-%d}" for q in full.recs if not q.traded]
        l8 = leg_counts(W, cnt_leg, 8)                                                          # [N7] the same leg read under a higher floor
        assert lc["floor"] == SPEC["floor"] and l8["floor"] == 8 and l8["traded"] == sum(q.n_new >= 8 for q in full.recs) < lc["traded"] and l8["below_floor"] == [f"{W.days[q.r]:%Y-%m-%d}" for q in full.recs if q.n_new < 8]
        assert sum(lc["traded_by_fill_year"].values()) == lc["traded"] and sum(lc["rebalances_by_fill_year"].values()) == lc["rebalances"] == len(full.recs) and sum(l8["traded_by_fill_year"].values()) == l8["traded"]
        tr = [q for q in full.recs if q.traded]
        assert lc["first_traded_rank"] == f"{W.days[tr[0].r]:%Y-%m-%d}" and lc["last_traded_rank"] == f"{W.days[tr[-1].r]:%Y-%m-%d}"
        co, nm = Counter(), defaultdict(set)
        for q in full.recs:
            for c_ in q.new.tolist():
                y = W.days[brute_listing(W)[c_][1]].year
                co[y] += 1
                nm[y].add(c_)
        assert lc["cohort_name_months"] == dict(sorted(co.items())) and lc["cohort_names"] == {y: len(v) for y, v in sorted(nm.items())}
    return True


def t_integration():
    """evaluate / variant_rows / reports / the printers / the JSON file end to end on the planted world, with the stub reference: every number of the cell record against the plain-python recount (the costs, the stress and borrow rows, the sides, the halves), the null's draws, the checks and the gate's basis, the look-ahead reading, the variant rows
    and every printed section"""
    B, S12 = M17.synth_book(seed=3, hi="2026-06-30")
    rb = DV.mk_ref(B)
    SN, SRN = restrict_stretch(S12, B.raw, B.index, WFN, PRE_END), restrict_stretch(rb.S, rb.raw, B.index, WFN, PRE_END)
    with spec(**SMALL), patched(THIS, manifest_sha=lambda: "0" * 64):
        w, r1 = pipe_world()
        W, ctx = w.W, w.ctx
        rows = A13.book_rows(B, W)
        res, obj = evaluate(W, ctx, B, SN, rb, SRN, rows, "remove", 8, 0, full=True)
        resK, objK = evaluate(W, ctx, B, SN, rb, SRN, rows, "naive", 8, 1, full=False)
        with spec(floor=8):                                                                    # [N7] the same reading under a higher floor (the reported one is 20: this world has 7 .. 10 NEW names a month), its own leg and null stream
            res20, obj20 = evaluate(W, ctx, B, SN, rb, SRN, rows, "remove", 8, 2, full=True)
        L = obj.legs
        assert res["variant"] == "remove" and resK["variant"] == "naive" and set(res["cells"]) == {"E", "M"} and res["null"]["draws"] == 8 and res["null"]["seed"] == SEED
        stretch = np.asarray((W.days >= WFN) & (W.days <= PRE_END))
        assert stretch.all(), "the planted world lies inside the WF stretch"
        for cell in CELLS:
            c = res["cells"][cell]
            for key in ("base", "stress", "borrow", "seat", "seat_ref", "realised_beta", "beta_gate", "A2", "ref_episodes", "ref_episodes_in_stretch", "gate70", "cost0", "sides", "halves", "short0", "short_stopped", "checks", "PASS"):
                assert key in c, (cell, key)
            kk = np.flatnonzero(B.mask(WFN, PRE_END))
            yrs_ = (B.index[kk[-1]] - B.index[kk[0]]).days / 365.25                              # [N10] dollars a year = net / years of the stretch, the house's years
            assert c["base"]["years"] == yrs_ and c["base"]["usd_per_year"] == c["base"]["net"] / yrs_ and all(c[k_][b_]["usd_per_year"] == c[k_][b_]["net"] / yrs_ for k_ in ("stress", "borrow") for b_ in c[k_]) and c["A2"]["years"] == stretch_years(B, WF0, PRE_END)
            eis = c["ref_episodes_in_stretch"]
            assert eis == episodes_in_stretch(rb, obj.series[cell][0], WFN, PRE_END) and eis["episodes_on_wf"] == len(rb.S.qual) == rb.structure["episodes"] and 1 <= eis["inside"] <= len(rb.S.qual) and eis["helped"] == sum(r_["cell_pnl"] > 0 for r_ in eis["rows"])
            net = lambda **kw: float(brute_cell_series(W, L, cell, **kw)[0].sum())
            assert abs(c["base"]["net"] - net()) < 1e-6 and c["base"]["n_pos"] == brute_cell_series(W, L, cell)[1] and abs(c["cost0"]["net"] - net(bps=0.0)) < 1e-6
            assert abs(c["stress"]["10 bps"]["net"] - net(bps=10.0)) < 1e-6 and abs(c["stress"]["20 bps"]["net"] - net(bps=20.0)) < 1e-6 and set(c["stress"]) == {"10 bps", "20 bps"}
            assert abs(c["borrow"]["10%/yr"]["net"] - net(borrow=0.10)) < 1e-6 and abs(c["borrow"]["25%/yr"]["net"] - net(borrow=0.25)) < 1e-6 and set(c["borrow"]) == {"10%/yr", "25%/yr"}
            assert abs(c["sides"]["short side only"]["net"] - net(side=-1)) < 1e-6 and abs(c["sides"]["long / hedge side only"]["net"] - net(side=1)) < 1e-6 and abs(c["sides"]["short side only"]["net"] + c["sides"]["long / hedge side only"]["net"] - c["base"]["net"]) < 1e-6
            assert c["cost0"]["net"] > c["base"]["net"] > c["stress"]["10 bps"]["net"] > c["stress"]["20 bps"]["net"] and c["base"]["net"] > c["borrow"]["10%/yr"]["net"] > c["borrow"]["25%/yr"]["net"]
            h1, h2 = c["halves"][HALVES[0][0]], c["halves"][HALVES[1][0]]
            assert h1["n_pos"] == 0 and h1["n_units"] == 0 and abs(h1["net"]) < 1e-9 and h2["n_pos"] == c["base"]["n_pos"] and h2["n_units"] == c["base"]["n_units"] and abs(h2["net"] - c["base"]["net"]) < 1e-6
            assert abs(sum(c["base"]["by_year"].values()) - c["base"]["net"]) < 1e-6 and abs(c["base"]["net_2020_21"]) < 1e-9 and abs(c["base"]["net_ex2022"] - c["base"]["net"]) < 1e-6 and abs(c["base"]["net_2022"]) < 1e-9
            assert c["short0"]["cell"]["net"] >= c["base"]["net"] - 1e-9 and c["short0"]["short_side"]["net"] >= c["sides"]["short side only"]["net"] - 1e-9, "valuing a stopped short at zero cannot hurt a short"
            assert c["short_stopped"]["positions"] >= 1 and c["short_stopped"]["short_positions"] == c["base"]["n_pos"]
            assert c["seat"]["dd_days"] == SN.n_dd_days and c["seat_ref"]["dd_days"] == SRN.n_dd_days and c["gate70"]["DO"] == c["seat_ref"]["DO"] and c["gate70"]["dd_days_from_2018_02"] == SRN.n_dd_days and c["gate70"]["episodes"] == rb.structure["episodes"]
            assert len(c["ref_episodes"]) == len(rb.S.qual) and c["beta_gate"]["credited"] is (abs(c["realised_beta"]["beta"]) <= 0.20) and c["A2"]["beta_rule_ok"] is c["beta_gate"]["credited"] and c["gate70"]["credited"] is c["beta_gate"]["credited"]
            assert c["A2"]["incremental_pass"] is (c["A2"]["incremental_pass_before_the_beta_rule"] and c["beta_gate"]["credited"])
            nul = res["null"]
            assert set(c["checks"]) >= {"rebalances>=40", "ROC>=15", "net>0 at 5 bps", "net>0 at 10 bps", "net>0 at 10%/yr borrow", "ROC>null p95", "positive in >=5 of 8 July-June years", "net>0 without Feb 15 - Apr 30 2020", "net>0 without calendar 2022",
                                        "profitable without its best 1% of days", "profitable without its best 1% of name-months"} and c["checks"]["rebalances>=40"] is False and c["PASS"] is False
            assert c["checks"]["ROC>null p95"] is bool(c["base"]["roc"] > nul["roc_max"]["p95"]) and c["checks"]["net>0 at 10%/yr borrow"] is bool(c["borrow"]["10%/yr"]["net"] > 0) and c["checks"]["net>0 at 10 bps"] is bool(c["stress"]["10 bps"]["net"] > 0)
            g = c["gate70"]
            assert g["null_do_p95"] == nul["do_ref_max"]["p95"] and g["DO_above_null_p95"] is bool(g["DO"] > g["null_do_p95"]) and g["gate_basis_met"] is bool(g["credited"] and g["DO_above_null_p95"] and g["DO_ex_best_episode"] > 0)
            assert resK["cells"][cell]["base"]["net"] == c["base"]["net"], "no hygiene flag inside any hold: the look-ahead reading is the registered one"
        assert "cost0" not in resK["cells"]["E"] and resK["null"]["draws"] == 8
        # [N7] the reading under the higher floor: its own leg (the months that reach it), the cells recounted by plain python on those months, its own null; the registered reading is untouched by it
        L8 = obj20.legs
        assert [q.r for q in L8.recs] == [q.r for q in L.recs] and [q.traded for q in L8.recs] == [q.n_new >= 8 for q in L.recs] and 0 < sum(q.traded for q in L8.recs) < sum(q.traded for q in L.recs) and res20["null"]["draws"] == 8 and res20["null"]["seed"] == SEED
        sub = SimpleNamespace(recs=[q for q in L.recs if q.n_new >= 8])
        for cell in CELLS:
            c8, c4 = res20["cells"][cell], res["cells"][cell]
            xs8, n8 = brute_cell_series(W, sub, cell)
            assert c8["base"]["n_pos"] == n8 and c8["base"]["n_units"] == len(sub.recs) and abs(c8["base"]["net"] - float(xs8.sum())) < 1e-6 and c8["base"]["net"] != c4["base"]["net"] and c8["base"]["usd_per_year"] == c8["base"]["net"] / c8["base"]["years"]
            assert c8["checks"]["rebalances>=40"] is False and set(c8) == set(c4) and c8["ref_episodes_in_stretch"]["episodes_on_wf"] == c4["ref_episodes_in_stretch"]["episodes_on_wf"] and c8["ref_episodes_in_stretch"]["inside"] == c4["ref_episodes_in_stretch"]["inside"]
        # the regime halves split the positions by EXIT date and the daily series by session date: on a world that straddles 2021-12-31 / 2022-01-01 they add up to the whole
        w2, _r2 = pipe_world(start="2021-04-01")
        rows2 = A13.book_rows(B, w2.W)
        res2, obj2 = evaluate(w2.W, w2.ctx, B, SN, rb, SRN, rows2, "remove", 0, 0, full=True)
        for cell in CELLS:
            c2 = res2["cells"][cell]
            a_, b_ = c2["halves"][HALVES[0][0]], c2["halves"][HALVES[1][0]]
            xs_ = brute_cell_series(w2.W, obj2.legs, cell)
            ex_ = np.array([w2.W.days[obj2.legs.recs[int(i)].x] for i in obj2.runs[cell].pos.rec])
            assert a_["n_pos"] > 0 and b_["n_pos"] > 0 and a_["n_pos"] + b_["n_pos"] == c2["base"]["n_pos"] == xs_[1] and a_["n_pos"] == int((ex_ <= HALVES[0][2]).sum()), (cell, a_["n_pos"], b_["n_pos"])
            assert abs(a_["net"] - float(xs_[0][w2.W.days <= HALVES[0][2]].sum())) < 1e-6 and abs(a_["net"] + b_["net"] - c2["base"]["net"]) < 1e-6 and abs(c2["base"]["net_2022"] + c2["base"]["net_ex2022"] - c2["base"]["net"]) < 1e-6 and c2["base"]["net_2022"] != 0.0
        # the other windows, included names and the dropped rank: the reported variant rows
        with spec(n3_lo=10, n3_hi=30):
            var = variant_rows(W, ctx, B, rows, drop=(W.days[r1],), drop2=(W.days[r1], W.days[L.recs[-1].r]))
        assert list(var) == ["[N3] 4-8 months after listing (84 .. 168 sessions)", "spinco names included", "name-change names included", "spinco and name-change names included", "without the ranks whose name-change window starts before the calendar",
                             "without the ranks whose name-change window starts before the first name-change row on the calendar"], list(var)
        assert variant_rows.__defaults__ == (None, None) and "first name-change row" not in "".join(variant_rows(W, ctx, B, rows, drop=(W.days[r1],)))
        n3 = ni_build(W, ctx, WFN, PRE_END, "remove", win=(10, 30))
        v3 = var["[N3] 4-8 months after listing (84 .. 168 sessions)"]
        assert v3["rebalances"] == len(n3.recs) and v3["below_floor"] == sum(not q.traded for q in n3.recs) and abs(v3["E"]["net"] - brute_cell_series(W, n3, "E")[0].sum()) < 1e-6 and abs(v3["M"]["net"] - brute_cell_series(W, n3, "M")[0].sum()) < 1e-6
        vi = var["spinco names included"]
        assert vi["rebalances"] == len(L.recs) and vi["E"]["included_spinco_name_months"] == 0 and abs(vi["E"]["net"] - res["cells"]["E"]["base"]["net"]) < 1e-6
        vd = var["without the ranks whose name-change window starts before the calendar"]
        assert vd["rebalances"] == len(L.recs) - 1 and var["without the ranks whose name-change window starts before the first name-change row on the calendar"]["rebalances"] == len(L.recs) - 2
        assert [r_ for r_, _f, _x in wf_ranks(W)] == [q.r for q in L.recs] and [d for d, _a in nc_coverage(W, W.days[L.recs[3].r] - pd.DateOffset(months=SPEC["nc_months"]))] == [W.days[q.r] for q in L.recs[:3]], "the WF ranks and the name-change coverage count"
        # reports: the tables per cell, the NEW table, the hedge ratio
        status = {"N01": "active"}
        rep, cands = reports(W, ctx, B, S12, rb, rows, obj, res["cells"], None, status, None)
        for cell in CELLS:
            r = rep["cells"][cell]
            assert set(r) >= {"es_beta", "episodes", "map_point", "corr_with_legs", "corr_with_res", "age_path", "cohort", "top20_gains", "by_exit_year"} and len(r["top20_gains"]) == 20 and len(cands[cell]) == AUDIT_N
            assert r["map_point"] == {"standalone_roc_30k": res["cells"][cell]["base"]["roc"], "rho_dd": res["cells"][cell]["seat_ref"]["rho_dd"], "DO": res["cells"][cell]["seat_ref"]["DO"]}
            assert len(r["episodes"]) == len(S12.qual) and sum(r["by_exit_year"].values()) == sum(1 for q in L.recs if traded(q, cell)) and r["corr_with_legs"] == {}
            assert sum(v["net"] for v in r["cohort"]["cell"].values()) - res["cells"][cell]["base"]["net"] < 1e-6
        assert rep["manifest_sha256"] == "0" * 64 and len(rep["new_table"]) == len(L.recs) and rep["hedge_ratio"]["rebalances"] == sum(q.tE for q in L.recs)
        # the printers
        ast = audit_status(cands, None)
        with patched(THIS, FLOOR_REPORTED=8):                                                  # (the reported floor shrunk to this world's NEW counts)
            txt = (capture(print_cells, res, ast) + capture(print_cells, res20, None, " @8", True) + capture(print_floors, res, res20) + capture(print_reports, rep, res["cells"]) + capture(print_diagnostics, res, rep, rb, var, res20)
                   + capture(print_counts, "L (registered)", L.cnt) + capture(print_exclusions, "L (registered)", L.cnt))
            txt_one = capture(print_diagnostics, res, rep, rb, var)
        for frag in ("null (8 draws, seed 20261005", "[N2] realised beta to ES", "A2 (a report) [X1]", "#70 gate basis [X1]", "Stage A (a)-(e) FAIL", "the hand audit (f): 0/50", "DIAGNOSTICS [X2]", "COST CURVE", "BORROW on every NEW short", "BY JULY-JUNE YEAR", "2020-21 (the listing boom) and calendar 2022 (the bust) apart",
                     "THE TWO REGIME HALVES", "THE REFERENCE LINE'S DRAWDOWN EPISODES [N10]", "the cell HELPS in", "THE SHORT SIDE AND THE LONG / HEDGE SIDE APART", "path by months since listing", "P&L by listing-year cohort", "short side alone", "VARIANT ROWS", "[N3] 4-8 months after listing", "spinco names included",
                     "NEW names per month by the rank's year", "NEW name-months by listing-year cohort", "cell E's ex-ante hedge ratio", "daily correlation with RESMOM's RES", "NEW names by fill year", "SEASONED names by fill year", "exclusions by fill year", "top name-month gain 1",
                     "BOTH FLOORS SIDE BY SIDE [N7]", "the REGISTERED 4-name floor", "the REPORTED 8-name floor", "cell E @8", "cell M @8", "under the 8-name floor (REPORTED, never a pass route)", "null under the 8-name floor (8 draws", "Stage A (a)-(e) under the 8-name floor",
                     "net $ / dollars a year (net / years)", " a year) ROC@30k", "E @8  rebalances", "DIAGNOSTICS [X2] - the registered reading, the WF stretch, both cells side by side; cells E @8, M @8 = the reported 8-name-floor reading beside them [N7]"):
            assert frag in txt, frag
        assert "@8" not in txt_one and "cell E @" not in txt_one and "THE REFERENCE LINE'S DRAWDOWN EPISODES [N10]" in txt_one, "without a reported reading the diagnostics have the two registered columns only"
        assert "$" in txt and "nan" not in capture(print_new_table, rep["new_table"]).lower()
        # the JSON the stage writes is serialisable and the round trip keeps the numbers
        js = json.loads(json.dumps({"res": res, "res20": res20, "rep": rep, "var": var, "listing": listing_counts(W.days, ctx.li)}, default=R11.js))
        assert abs(js["res20"]["cells"]["M"]["base"]["usd_per_year"] - res20["cells"]["M"]["base"]["usd_per_year"]) < 1e-9
        assert abs(js["res"]["cells"]["E"]["base"]["net"] - res["cells"]["E"]["base"]["net"]) < 1e-9 and sorted(js["rep"]["cells"]["M"]["cohort"]["cell"]) == sorted(str(y) for y in rep["cells"]["M"]["cohort"]["cell"])
    return True


def t_refusals():
    """the guards: a changed or missing pre-registration refuses every stage (the LF sha256, and the committed blob when git says it differs), Stage A refuses once the lockbox has been read, Stage B refuses without the lead's go-flag, with no judged candidate, after a read, under another pre-registration, a stale stamp,
    a changed audit file or a broken frozen size - every one BEFORE anything loads and never writing the read flag; the usage line"""
    with tempfile.TemporaryDirectory() as td, patched(THIS, OUT=td):
        with patched(THIS, PREREG_SHA="0" * 64):
            refused(prereg_ok, "PREREG_NEWISSUE_R1.txt DIFFERS from the registered one", "a changed spec is a new file", "lockbox NOT read")
            refused(stage_a, "DIFFERS")
        with patched(THIS, PREREG=os.path.join(td, "absent.txt")):
            refused(prereg_ok, "is not next to this file", "the spec cannot be verified")
        with patched(D15, committed_state=lambda: "differs"):
            refused(prereg_ok, "COMMITTED PREREG_NEWISSUE_R1.txt differs", "lockbox NOT read")
        for st, frag in (("match", "matches too"), ("untracked", "NOT COMMITTED YET"), ("unknown", "git not available")):
            with patched(D15, committed_state=lambda st=st: st):
                assert frag in capture(prereg_ok)
        rd, go, sa_path = os.path.join(td, READ_FLAG), os.path.join(td, GO_FLAG), os.path.join(td, "newissue_stageA.json")
        # Stage A is frozen once the lockbox has been read
        open(rd, "w").write("x")
        refused(stage_a, "Stage A is frozen", READ_FLAG)
        os.remove(rd)
        # Stage B
        def must(frag, **kw):
            with patched(THIS, **kw):
                msg = refused(lambda: quiet_call(stage_b), frag)
            assert not os.path.exists(rd), "a refused Stage B must not burn the lockbox"
            return msg
        must("the lead's go-flag newissue_stageB_GO.flag is not on file")
        open(go, "w").write("the lead's go-flag")
        must("no Stage A candidate")
        base = {"prereg_sha256_lf": PREREG_SHA, **stamp(), "judged": True, "candidate": {"cell": "E", "c": 1.5}, "stageA": {"registered_pass_cells": ["E"]}, "audit_sha256": None, "manifest_sha256": "380b05f2" + "0" * 56, "parity": {"E": {"net": 1.0, "n_pos": 1, "n_units": 1}, "M": {"net": 1.0, "n_pos": 1, "n_units": 1}}}

        def put(j):
            with open(sa_path, "w") as f_:
                json.dump(j, f_)
        for edit in (lambda j: j.update(judged=False), lambda j: j.update(candidate=None), lambda j: j["stageA"].update(registered_pass_cells=[]), lambda j: j["stageA"].update(registered_pass_cells=["M"]), lambda j: j.pop("stageA")):
            j = json.loads(json.dumps(base))
            edit(j)
            put(j)
            must("no Stage A candidate")
        j = json.loads(json.dumps(base))
        j["prereg_sha256_lf"] = "0" * 64
        put(j)
        must("another pre-registration")
        for k in ("harness_sha256", "r18_sha256", "r17_sha256", "r15_sha256", "r13_sha256", "siporb_sha256", "r11_sha256", "r12_sha256", "wide_ca_sha256"):
            j = json.loads(json.dumps(base))
            j[k] = "0" * 64
            put(j)
            assert k in must("different harness version"), k
        j = json.loads(json.dumps(base))
        j["early_close"] = j["early_close"][1:]
        put(j)
        must("different harness version")
        put(base)
        open(os.path.join(td, "newissue_audit.csv"), "w").write("symbol,date,cell,verdict\nA00,2024-06-03,E,keep\n")
        must("is not the file Stage A ran with")
        os.remove(os.path.join(td, "newissue_audit.csv"))
        for badc in (0.0, -1.0, float("nan"), None, "x"):
            j = json.loads(json.dumps(base))
            j["candidate"]["c"] = badc
            put(j)
            must("a positive number")
        j = json.loads(json.dumps(base))
        j["candidate"]["cell"] = "Q"
        j["stageA"]["registered_pass_cells"] = ["Q"]
        put(j)
        must("a positive number")
        with patched(THIS, PREREG_SHA="0" * 64):
            put(base)
            must("DIFFERS")
        open(rd, "w").write("x")
        put(base)
        refused(lambda: quiet_call(stage_b), "already read", READ_FLAG)
        os.remove(rd)
        assert not os.path.exists(rd)
    assert "usage: r20_newissue.py selftest | smoke DIR [stage_b] | dryload | stage_a | stage_b" in capture(main, ["bogus"]) and "usage:" in capture(main, [])
    return True


def quiet_call(fn, *a, **kw):
    with quiet():
        return fn(*a, **kw)


def t_cut():
    """[11] the lockbox cut is asserted where NEWISSUE holds the data: a session, a calendar row or a spin-off / name-change date on / after the cut refuses (nothing computed); a stage's own cut lets earlier data through; the first-session constant is the cache's"""
    w = ni_world([dict(sym="A", first=0), dict(sym="B", first=3)], T=60, start="2025-06-02")
    W = w.W
    cut = TS("2025-06-30")
    assert W.days.max() >= cut
    refused(lambda: cut_checks(W, None, None, cut), "NEWISSUE sessions holds a date on/after the cut 2025-06-30", "nothing computed")
    cut_checks(W, None, None, W.days.max() + pd.Timedelta(days=1))
    ok = SimpleNamespace(div=pd.DataFrame({"ex": pd.to_datetime(["2025-06-27"])}), spin=pd.DataFrame({"ex": pd.to_datetime(["2025-06-20"])}), split=pd.DataFrame({"ex": pd.to_datetime([])}))
    W2 = ni_world([dict(sym="A", first=0)], T=20, start="2025-06-02").W
    cut_checks(W2, ok, mk_extra([("S", "P", "2025-06-27")], [("O", "N", "2025-06-27")]), cut)
    for nm in ("div", "spin", "split"):
        bad = SimpleNamespace(**{k: getattr(ok, k) for k in ("div", "spin", "split")})
        setattr(bad, nm, pd.DataFrame({"ex": pd.to_datetime(["2025-06-30"])}))
        refused(lambda: cut_checks(W2, bad, None, cut), f"NEWISSUE calendar {nm} ex-dates holds a date on/after the cut")
    refused(lambda: cut_checks(W2, None, mk_extra([("S", "P", "2025-06-30")], []), cut), "spin-off new symbols holds a date on/after the cut")
    refused(lambda: cut_checks(W2, None, mk_extra([], [("O", "N", "2025-07-15")]), cut), "name changes holds a date on/after the cut")
    assert FIRST_SESSION == TS("2016-01-04") and S.LB0 == TS("2025-06-30") and cal_start_row(W2, "2025-06-10") == 6
    return True


TESTS = ("t_constants", "t_listing", "t_calendar", "t_sets", "t_match", "t_beta_hedge", "t_costs", "t_floor", "t_floors", "t_pipeline", "t_null", "t_close", "t_beta_rule", "t_tables", "t_x1", "t_usd_year", "t_files", "t_counts_only", "t_integration", "t_refusals", "t_cut")


def selftest():
    """hand-made worlds and calendars, no files, no data, no network: every group prints one line, the last line says how many ran. The real RESMOM line file is never read by a test: a read that is not stubbed lands in a folder that does not exist and refuses"""
    t0 = time.time()
    n_sets = 0
    with tempfile.TemporaryDirectory() as td, patched(DV, REF_CSV=os.path.join(td, "no_such_dir", "resmom_cells_daily_wf.csv")):
        for name in TESTS:
            t1 = time.time()
            out = globals()[name]()
            if name == "t_sets":
                n_sets = out
            print(f"  {name} ok ({time.time() - t1:.1f}s)", flush=True)
    print("v1 CHOICE (proved by t_match): the matched long is the GLOBAL GREEDY over (distance, NEW symbol, candidate symbol) - each SEASONED name used once, ties by symbol - exact against an all-pairs recount on 600 random worlds with heavy ties and missing values")
    print("ADDENDUM 1 (proved by t_sets / t_floor / t_beta_hedge / t_costs / t_beta_rule / t_listing): [N1] borrow 3%/yr base and the 10% / 25% stress rows on every short day; [N2] cell E's ex-ante hedge = the OLS beta of the equal-weight NEW basket on ES x the short notional, the realised-beta rule at |0.20|; [N4] 18 of the 20 sessions; "
          "[N6]'s size floor (its number is addendum 3's [N7] now; E's hedge ratio / M's candidates); the NEW / SEASONED windows, the spinco and name-change exclusions")
    print("ADDENDUM 3 (proved by t_floors / t_floor / t_usd_year / t_constants / t_integration): [N7] the registered floor is 10 NEW names (counted after every removal) and every reading is also made under the 20-name floor (its own leg and null), printed beside it, never a pass route; [N8] bar (a) = 40 traded rebalances; "
          "[N9] 'net > 0 without calendar 2022' stays binding and the LOW-POWER flag is a constant of every verdict; [N10] dollars a year = net / years beside every ROC @ $30k and the reference line's drawdown episodes inside the cell's stretch")
    print("HYGIENE EDIT S1 [HYG-S1] (MANAGER #127; proved by t_close): the reading 'close' removes no name for an in-hold event - flagged names and calendar splits stay on the split-safe path - and a spin-off / stock-dividend ex-date inside the hold closes the position (a NEW short, a matched or drawn SEASONED name) "
          "at the official close before it: no mark, dividend or borrow after it, the exit cost on that row, the null's draws cut too; cell E's ES hedge share of a closed short runs to the exit (CHOICE); the registered 'remove' reading is untouched (pnl1 is r15's l1_pnl on its units)")
    print(f"selftest ok: {len(TESTS)} groups ({', '.join(t[2:] for t in TESTS)}) in {time.time() - t0:.0f}s; {n_sets} NEW / SEASONED sets of random worlds equal the plain-python recount; every cell, side, stress row, null draw and table equals a plain-python recount")


# ------------------------------------------------------------------ selftest, addendum 3: the floor switch [N7] / [N8] / [N9] and the dollars a year [N10]
def floors_world():
    """a world for the floor switch: 14 SEASONED names from the first session and clusters of NEW listings made 30 sessions before each month-end rank - every rank then sees exactly its own cluster (the age window 15 .. 45 and the 19 .. 23-session months keep the neighbours out) - of 6 / 9 / 10 / 14 / 19 / 20 / 27 / 31 / 12 /
    8 / 21 / 5 names, which puts months on both sides of the registered floor (9 | 10) and of the reported one (19 | 20); SMALL windows; a start that puts the fills on both sides of 2022-03 -> (w, the ranks, the cluster sizes)"""
    T, start = 330, "2021-09-01"
    days = pd.bdate_range(start, periods=T)
    r_all, _f, x_all = M17.rm_schedule(days)
    usable = [int(r) for r, x in zip(r_all, x_all) if r >= SMALL["hold_win"] + 3 and x >= 0]
    sizes = [6, 9, 10, 14, 19, 20, 27, 31, 12, 8, 21, 5]
    assert len(usable) >= len(sizes), (len(usable), len(sizes))
    rks = usable[:len(sizes)]
    rng = np.random.default_rng(5)
    dv = lambda: float(np.exp(rng.uniform(np.log(2e7), np.log(4e8))))
    cols = [dict(sym=f"A{k:02d}", first=0, beta=float(rng.uniform(0.6, 1.4)), dvol=dv()) for k in range(14)]
    for g, (r, n_) in enumerate(zip(rks, sizes)):
        cols += [dict(sym=f"N{g:02d}{k:02d}", first=r - 30, beta=float(rng.uniform(0.8, 1.8)), drift=-0.001, dvol=dv()) for k in range(n_)]
    return ni_world(cols, T=T, seed=6, start=start), rks, sizes


def plain_n_new(cols, r, lo, hi):
    """plain python: the NEW names at rank row r of a hand-made world with no hygiene case - the columns with a dated listing (first >= 1) whose age r - first lies in [lo, hi]"""
    return sum(1 for c in cols if c.get("first", 0) >= 1 and lo <= r - c["first"] <= hi)


def t_floors():
    """[N7] THE FLOOR SWITCH: the registered floor is 10 NEW names (counted after every removal; it replaces [N6]'s 20) and every reading is also made under the 20-name floor. A world whose months hold 5 .. 31 NEW names is built under BOTH floors and every month's NEW count is recounted in plain python from
    the listing rows: a month trades exactly when it reaches the floor (9 | 10, 19 | 20), the counters say so, leg_counts reads either floor off the same leg and equals the leg built under that floor (traded months, by fill year, in 2018-03 .. 2022-03, the months under it), and the 20-name cells hold exactly
    the positions of the 10-name cells in the months that reach 20 - at the same P&L - while the 10-name series is the 20-name series plus the mid months' own paths. [N8] bar (a) = 40 traded rebalances, edge-exact; [N9] 'net > 0 without calendar 2022' stays binding"""
    assert SPEC["floor"] == 10 and FLOOR_REPORTED == 20, "the registered floor is 10, the reported one 20"
    w, rks, sizes = floors_world()
    W, ctx, cols = w.W, w.ctx, w.cols
    lo, hi = SMALL["new_lo"], SMALL["new_hi"]
    with spec(**{**SMALL, "floor": 10}):
        L10 = ni_build(W, ctx, W.days[0], W.days[-1])
    with spec(**{**SMALL, "floor": 20}):
        L20 = ni_build(W, ctx, W.days[0], W.days[-1])
    want = [plain_n_new(cols, q.r, lo, hi) for q in L10.recs]
    assert [q.r for q in L10.recs] == [q.r for q in L20.recs] and [q.n_new for q in L10.recs] == want == [q.n_new for q in L20.recs], (want, [q.n_new for q in L10.recs])
    assert set(sizes) <= set(want) and {9, 10, 19, 20} <= set(want), "the world has a month on each side of both floors' edges"
    assert [q.traded for q in L10.recs] == [n_ >= 10 for n_ in want] and [q.traded for q in L20.recs] == [n_ >= 20 for n_ in want]
    assert [q.tE for q in L10.recs] == [q.traded for q in L10.recs] and [q.tM for q in L20.recs] == [q.traded for q in L20.recs], "every traded month has a hedge ratio and a match here"
    assert sum(v["below_floor"] for v in L10.cnt.values()) == sum(1 for n_ in want if n_ < 10) and sum(v["below_floor"] for v in L20.cnt.values()) == sum(1 for n_ in want if n_ < 20)
    assert 3 <= sum(1 for n_ in want if n_ < 10) and sum(1 for n_ in want if 10 <= n_ < 20) >= 3 and sum(1 for n_ in want if n_ >= 20) >= 3
    # leg_counts: the registered floor by default, the reported one on request - the same leg read under either floor equals the leg built under it
    lc10, lc10_20, lc20 = leg_counts(W, L10), leg_counts(W, L10, FLOOR_REPORTED), leg_counts(W, L20, FLOOR_REPORTED)
    fill = {q.r: W.days[q.f] for q in L10.recs}
    for lc, fl in ((lc10, 10), (lc10_20, 20), (lc20, 20)):
        tr = [q for q, n_ in zip(L10.recs, want) if n_ >= fl]
        assert lc["floor"] == fl and lc["traded"] == len(tr) and lc["rebalances"] == len(want), (fl, lc["traded"], len(tr))
        assert lc["traded_by_fill_year"] == dict(sorted(Counter(int(fill[q.r].year) for q in tr).items())) and lc["rebalances_by_fill_year"] == dict(sorted(Counter(int(fill[q.r].year) for q in L10.recs).items()))
        assert lc["traded_2018_03_to_2022_03"] == sum(1 for q in tr if TS("2018-03-01") <= fill[q.r] <= TS("2022-03-31")) and lc["traded_2018_03_to_2022_03"] < len(tr), "fills after 2022-03 are counted outside"
        assert lc["below_floor"] == [f"{W.days[q.r]:%Y-%m-%d}" for q, n_ in zip(L10.recs, want) if n_ < fl]
        assert lc["first_traded_rank"] == f"{W.days[tr[0].r]:%Y-%m-%d}" and lc["last_traded_rank"] == f"{W.days[tr[-1].r]:%Y-%m-%d}" and lc["new_per_rebalance"] == [min(want), float(np.median(want)), max(want)]
    assert lc10_20 == lc20 and lc10["traded"] > lc20["traded"] > 0 and lc10["floor"] == 10, "the reported reading's counts are the same off either leg"
    assert leg_counts(W, L10, 31)["traded"] == 1 and leg_counts(W, L10, 32)["traded"] == 0 and leg_counts(W, L10, 32)["first_traded_rank"] is None
    # the cells: the 20-name leg holds the 10-name leg's positions of the months that reach 20 NEW names, at the same P&L; nothing else differs but the mid months' own paths
    cfg = cfg_of()
    n_at = {q.r: n_ for q, n_ in zip(L10.recs, want)}
    mid = [q for q, n_ in zip(L10.recs, want) if 10 <= n_ < 20]
    for cell in CELLS:
        r10, r20 = cell_run(W, L10, cell, cfg), cell_run(W, L20, cell, cfg)
        key = lambda L, run: sorted((L.recs[int(i)].r, int(c_), round(float(p_), 9)) for i, c_, p_ in zip(run.pos.rec, run.pos.col, run.pos.pnl))
        k10 = [t for t in key(L10, r10) if n_at[t[0]] >= 20]
        assert key(L20, r20) == k10 and len(k10) > 0 and r20.n_pos == len(k10) and r20.n_units == len({t[0] for t in k10}) == sum(1 for n_ in want if n_ >= 20), cell
        assert r10.n_units == sum(1 for n_ in want if n_ >= 10) and r10.n_pos > r20.n_pos, cell
        assert usd(r10.x, brute_cell_series(W, L10, cell)[0]) and usd(r20.x, brute_cell_series(W, L20, cell)[0]), cell
        add = np.zeros(W.T)
        for q in mid:
            assert not r20.cnt[q.f + 1:q.x].any() and (r10.cnt[q.f:q.x + 1] > 0).all(), "a month under the floor holds nothing (its first row is the previous month's exit row, its last the next month's fill row)"
            idx, S_, O = rec_legs(W, q, cell, cfg)
            add[q.f:q.x + 1] += S_.sum(axis=0) + O.sum(axis=0)
        assert usd(r10.x, r20.x + add), cell
    # the printed line of both floors' months, by fill year (registered / reported of the rebalances) and the LOW-POWER flag's own count
    tt = traded_text(lc10, lc20)
    for frag in (f"{lc10['traded']} of the {lc10['rebalances']} rebalances under the REGISTERED 10-name floor", f"{lc20['traded']} under the REPORTED 20-name floor", "never a pass route",
                 f"in 2018-03 .. 2022-03: {lc10['traded_2018_03_to_2022_03']} of the {lc10['traded']} (registered), {lc20['traded_2018_03_to_2022_03']} of the {lc20['traded']} (reported)"):
        assert frag in tt, frag
    for y, nb in lc10["rebalances_by_fill_year"].items():
        assert f"{y}: {lc10['traded_by_fill_year'].get(y, 0)} / {lc20['traded_by_fill_year'].get(y, 0)} of {nb}" in tt, y
    # [N8] bar (a) = 40 traded rebalances, edge-exact; [N9] 'net > 0 without calendar 2022' stays binding
    assert RULES["reb"] == 40
    st0 = dict(n_units=0, roc=20.0, net=1.0, years_pos=6, net_ex2020=1.0, net_ex2022=1.0, net_ex_best_days=1.0, net_ex_best_pos=1.0)
    nul0 = {"roc_max": {"p95": 5.0}}
    for n_, ok_ in ((0, False), (39, False), (40, True), (41, True), (60, True), (89, True)):
        chk = judge_cell({**st0, "n_units": n_}, 1.0, 1.0, nul0)
        assert chk["rebalances>=40"] is ok_ and all(v for k_, v in chk.items() if k_ != "rebalances>=40"), n_
    for ex in (-1.0, 0.0, float("nan")):
        chk = judge_cell({**st0, "n_units": 60, "net_ex2022": ex}, 1.0, 1.0, nul0)
        assert chk["net>0 without calendar 2022"] is False and not all(chk.values()), ex
    return True


def t_usd_year():
    """[N10] DOLLARS A YEAR = net / years, the house's years (r11_risk.stats: the last row's date minus the first's, / 365.25 - the years its ROC is computed on): the arithmetic and its NaN cases; the years of a stretch on #463's index equal r11's; a cell's statistics carry it (the whole stretch and the halves);
    A2's record carries it beside EVERY ROC @ $30k (the reference, the reference + c x cell, 0.5c, 2c, the plain #463 + c x cell with its 0.5c / 2c rows, the cell's own stretch) and a2_text prints it; the reference line's drawdown episodes INSIDE the cell's stretch (cut at its start, the cell's P&L inside each,
    the count it helps in) against a plain-python recount, and the whole-stretch reading equals r15's episodes table; the episode printer"""
    for net, yrs, want in ((12345.0, 2.5, 4938.0), (-3000.0, 4.0, -750.0), (0.0, 3.0, 0.0), (7.5, 1.0, 7.5)):
        assert usd_per_year(net, yrs) == want, (net, yrs)
    for bad in ((1.0, 0.0), (1.0, -2.0), (1.0, float("nan")), (float("nan"), 2.0), (None, 2.0), (1.0, None), (float("inf"), 2.0), (1.0, float("inf")), ("x", 2.0)):
        assert math.isnan(usd_per_year(*bad)), bad
    B, _S12 = M17.synth_book(seed=3, hi="2026-06-30")
    ds = B.index
    for a_, b_ in ((WF0, PRE_END), (WFN, PRE_END), (LB0, LB1), (TS("2021-03-01"), TS("2021-03-31")), HALVES[0][1:], HALVES[1][1:]):
        k = np.flatnonzero(B.mask(a_, b_))
        yrs = (ds[k[-1]] - ds[k[0]]).days / 365.25
        assert stretch_years(B, a_, b_) == yrs and abs(R11.stats(np.asarray(B.raw, float)[k], ds[k])["years"] - yrs) < 1e-12, (a_, b_)
    assert math.isnan(stretch_years(B, TS("2030-01-01"), TS("2031-01-01"))) and math.isnan(stretch_years(B, ds[10], ds[10]))
    rb = DV.mk_ref(B)
    kf, kw = np.flatnonzero(B.mask(WF0, PRE_END)), np.flatnonzero(B.mask(WFN, PRE_END))
    yf, yo = (ds[kf[-1]] - ds[kf[0]]).days / 365.25, (ds[kw[-1]] - ds[kw[0]]).days / 365.25
    # a cell's statistics: the whole stretch and its halves
    with spec(**SMALL):
        w, _r1 = pipe_world()
        rows = A13.book_rows(B, w.W)
        L = ni_build(w.W, w.ctx, WFN, PRE_END)
        for cell in CELLS:
            run = cell_run(w.W, L, cell, cfg_of())
            st, xB, _cB = stat_of(B, rows, run, WFN, PRE_END)
            assert st["years"] == yo and abs(st["usd_per_year"] - float(np.asarray(xB, float)[kw].sum()) / yo) < 1e-9 * max(1.0, abs(st["usd_per_year"])) and st["usd_per_year"] == st["net"] / st["years"] and st["net"] != 0.0
            for lab, a_, b_ in HALVES:
                sh = stat_of(B, rows, sub_run(w.W, L, run, a_, b_), a_, b_)[0]
                km = np.flatnonzero(B.mask(a_, b_))
                assert abs(sh["usd_per_year"] - float(np.asarray(xB, float)[km].sum()) / ((ds[km[-1]] - ds[km[0]]).days / 365.25)) < 1e-9 * max(1.0, abs(sh["usd_per_year"])) and sh["years"] != st["years"], (cell, lab)
    # A2: dollars a year beside every ROC
    rng = np.random.default_rng(8)
    x = np.zeros(B.n)
    x[kw] = 0.4 * np.maximum(-rb.raw[kw], 0.0) + rng.normal(0.0, 40.0, len(kw))
    a2 = a2_report(B, x, rb, True)
    c = a2["c"]
    assert a2["years"] == yf and math.isfinite(c) and c > 0
    plain = (np.asarray(B.raw, float) + c * x)[kf]
    for name, blk, want_net in (("book", a2, (rb.raw + c * x)[kf].sum()), ("reference", a2["reference"], rb.raw[kf].sum()), ("0.5c", a2["at_half_c"], (rb.raw + 0.5 * c * x)[kf].sum()), ("2c", a2["at_double_c"], (rb.raw + 2.0 * c * x)[kf].sum()), ("plain", a2["plain_463"], plain.sum()),
                               ("plain 0.5c", a2["plain_463"]["at_half_c"], (np.asarray(B.raw, float) + 0.5 * c * x)[kf].sum()), ("plain 2c", a2["plain_463"]["at_double_c"], (np.asarray(B.raw, float) + 2.0 * c * x)[kf].sum())):
        assert abs(blk["net"] - want_net) < 1e-3 and blk["usd_per_year"] == blk["net"] / yf and abs(blk["usd_per_year"] - want_net / yf) < 1e-3 / yf, name
    os_ = a2["own_stretch"]
    assert os_["years"] == yo and abs(os_["reference_alone"]["usd_per_year"] - rb.raw[kw].sum() / yo) < 1e-6 and abs(os_["with_c"]["usd_per_year"] - (rb.raw + c * x)[kw].sum() / yo) < 1e-6 and os_["reference_alone"]["net"] == os_["reference_alone"]["usd_per_year"] * yo
    txt = a2_text(a2)
    for v in (a2, a2["reference"], a2["at_half_c"], a2["at_double_c"], a2["plain_463"], os_["reference_alone"], os_["with_c"]):
        assert f"${v['usd_per_year']:,.0f} a year" in txt, v
    assert f"({a2['years']:.2f} years; dollars a year = net / years)" in txt and f"({os_['years']:.2f} years)" in txt
    az = a2_report(B, np.zeros(B.n), rb, True)
    assert not math.isfinite(az["c"]) and az["years"] == yf and az["reference"]["usd_per_year"] == az["reference"]["net"] / yf and "no incremental pass" in a2_text(az) and "own_stretch" not in az
    # the reference line's drawdown episodes inside the cell's stretch: a block before 2018-02, one that straddles it, two inside; plain-python recount
    res = np.random.default_rng(14).normal(5.0, 300.0, len(kf))
    for d0, n_, amt in (("2016-09-05", 15, 2500.0), ("2018-01-10", 30, 3000.0), ("2019-06-03", 20, 2000.0), ("2024-02-05", 25, 2200.0)):
        i0 = int(np.searchsorted(ds[kf], TS(d0)))
        res[i0:i0 + n_] -= amt
    ref2 = DV.ref_build(B, res)
    xc = np.random.default_rng(15).normal(0.0, 150.0, B.n)
    got = episodes_in_stretch(ref2, xc, WFN, PRE_END)
    S_, d_ = ref2.S, ref2.S.dates
    want_rows = []
    for e in S_.qual:
        days_ = [t for t in range(int(e["i0"]), int(e["it"]) + 1) if WFN <= d_[t] <= PRE_END]
        if not days_:
            continue
        cp, bp = sum(float(xc[S_.rows[t]]) for t in days_), sum(float(S_.x[t]) for t in days_)
        want_rows.append({"first_dd_day": f"{d_[days_[0]]:%Y-%m-%d}", "trough": e["trough"], "depth": float(e["depth"]), "dd_days": int(e["it"]) - int(e["i0"]) + 1, "dd_days_inside": len(days_), "cut": days_[0] > int(e["i0"]), "book_pnl": bp, "cell_pnl": cp, "helps": cp > 0})
    assert got["episodes_on_wf"] == len(S_.qual) and got["inside"] == len(got["rows"]) == len(want_rows) and 1 <= got["cut"] == sum(r_["cut"] for r_ in want_rows) and got["inside"] < got["episodes_on_wf"], (got["episodes_on_wf"], got["inside"], got["cut"])
    for g_, w_ in zip(got["rows"], want_rows):
        assert all(g_[k_] == w_[k_] for k_ in ("first_dd_day", "trough", "dd_days", "dd_days_inside", "cut", "helps")) and abs(g_["depth"] - w_["depth"]) < 1e-9 and abs(g_["book_pnl"] - w_["book_pnl"]) < 1e-6 and abs(g_["cell_pnl"] - w_["cell_pnl"]) < 1e-6 and g_["peak"] is not None, (g_, w_)
    assert got["helped"] == sum(r_["helps"] for r_ in want_rows) and 0 < got["helped"] < got["inside"] and abs(got["cell_pnl"] - sum(r_["cell_pnl"] for r_ in want_rows)) < 1e-6 and abs(got["reference_pnl"] - sum(r_["book_pnl"] for r_ in want_rows)) < 1e-6
    full = episodes_in_stretch(ref2, xc, WF0, PRE_END)
    tab = D15.episodes_table(S_, xc)
    assert full["inside"] == full["episodes_on_wf"] == len(tab) == len(S_.qual) and full["cut"] == 0 and all(abs(a_["cell_pnl"] - b_["cell_pnl"]) < 1e-6 and abs(a_["book_pnl"] - b_["book_pnl"]) < 1e-6 and a_["dd_days"] == a_["dd_days_inside"] == b_["dd_days"] and a_["first_dd_day"] == b_["first_dd_day"]
                                                                                       for a_, b_ in zip(full["rows"], tab)), "the whole-stretch reading is r15's episodes table"
    assert episodes_in_stretch(ref2, xc, TS("2030-01-01"), TS("2031-01-01"))["inside"] == 0 and episodes_in_stretch(ref2, xc)["rows"] == got["rows"], "the default stretch is the cell's own"
    # the episode printer: one row per episode inside the stretch, the cut marked, '+' where the cell helps, the counts
    res_p = {"cells": {cell: {"ref_episodes_in_stretch": episodes_in_stretch(ref2, np.random.default_rng(16 + q).normal(0.0, 150.0, B.n), WFN, PRE_END)} for q, cell in enumerate(CELLS)}}
    out = capture(print_episodes, res_p, ref2)
    assert "THE REFERENCE LINE'S DRAWDOWN EPISODES [N10]" in out and f"{got['episodes_on_wf']} qualifying on its WF" in out and f"{got['inside']} have DD days inside the cell's stretch" in out and f"{got['cut']} of them cut to the part inside it" in out
    for e in got["rows"]:
        assert f"{e['first_dd_day']} .. {e['trough']} ${e['depth']:,.0f} ({e['dd_days_inside']}/{e['dd_days']} d{', cut' if e['cut'] else ''}, ref {e['book_pnl']:+,.0f})" in out, e
    for cell in CELLS:
        e = res_p["cells"][cell]["ref_episodes_in_stretch"]
        assert f"{e['helped']} of {e['inside']}" in out and f"{e['cell_pnl']:+,.0f}" in out
    for q, e in enumerate(got["rows"]):                                                      # the '+' marks the episodes a cell helps in, per cell, on the row itself
        vals = [f"{res_p['cells'][cell]['ref_episodes_in_stretch']['rows'][q]['cell_pnl']:+,.0f}" + (" +" if res_p["cells"][cell]["ref_episodes_in_stretch"]["rows"][q]["cell_pnl"] > 0 else "") for cell in CELLS]
        assert diag_line(f"  {e['first_dd_day']} .. {e['trough']} ${e['depth']:,.0f} ({e['dd_days_inside']}/{e['dd_days']} d{', cut' if e['cut'] else ''}, ref {e['book_pnl']:+,.0f})", vals) in out, e
    res_q = {"cells": {cell: {**res_p["cells"][cell]} for cell in CELLS}}
    out20 = capture(print_episodes, res_p, ref2, res_q)
    assert "cell E @20" in out20 and "cell M @20" in out20 and "cell E @20" not in out and out20.count("cell E") == 2
    return True


# ------------------------------------------------------------------ smoke: the synthetic worlds (a planted new-issue underperformance and a null one) behind r5_siporb's fake transport, a fake ES master, a fake #463, a fake RESMOM line file and a fake wide calendar
def smoke_refusal(root):
    """r18_divrun's guards (the dir is wiped: a 'smoke' name, never OUT / CACHE / the repo / this harness / the working directory / C:\\EdgeLog, ATTN's / DDW's / RESMOM's / DIVRUN's OUT, the #463 records) + this harness's OUT"""
    why = DV.smoke_refusal(root)
    if why:
        return why
    real = lambda p: os.path.normcase(os.path.realpath(p))
    try:
        if os.path.commonpath([real(root), real(OUT)]) == real(root):
            return f"smoke refused: {root} is or holds NEWISSUE OUT"
    except ValueError:
        pass
    return None


SMOKE_DRIFT = -0.0010               # the planted new-issue underperformance: a NEW name's daily drift over the sessions 100 .. 560 after its listing (the planted world only; the null world has none)
SMOKE_BEAR = -0.0010                # the BEAR world: EVERY name drifts down by this much a day, from the first session on (shorting any single name against ES wins: the null, which shorts random SEASONED names, must catch it)
SMOKE_AGE = (100, 560)
SMOKE_FLOOR_REPORTED = 18           # CHOICE: the smoke leaves the registered 10-name floor alone (the synthetic market lists one name a month: 16 .. 20 names survive as NEW in every month, so every month trades) and shrinks the REPORTED 20-name floor to 18, so that about
                                    # half the months trade under it; the real constants are asserted by selftest


def smoke_plan(days, seed=23):
    """the synthetic market's cast: 30 SEASONED names (S01 .. S30, present from the first session; S01 .. S20 pay a quarterly dividend, S07 / S12 have a name change), the registered-split SPL, the delisted DLST, three names below the universe's floors, one NEW name listed a month from 2016-02 to 2026-03 (N001 .. N122)
    and the planted cases among the NEW: NX01 a stray bar before a real listing and NX02 17 of the 20 sessions after the first bar ([N4] fails), NX03 exactly 18 (accepted), NS01 / NS02 spin-offs' new symbols, NC01 a name change 40 sessions after listing (always excluded), NC02 one 400 sessions after (excluded
    only from then on), NSPL a registered split inside a hold, NMSP a missed x4, NGAP a +60% gap. Rows of the calendar on / after the cut are in it as well (they must be dropped at read). -> SimpleNamespace"""
    rng = np.random.default_rng(seed)
    row = lambda s: int(days.searchsorted(pd.Timestamp(s)))
    seas = [f"S{k:02d}" for k in range(1, 31)] + ["SPL", "DLST", "LOWP", "LOWV", "LOWA"]
    first = {n: 0 for n in seas}
    new = []
    for k, m in enumerate(pd.date_range("2016-02-01", "2026-03-01", freq="MS"), 1):
        nm = f"N{k:03d}"
        first[nm] = row(m) + int(rng.integers(0, 12))
        new.append(nm)
    special = {"NX01": "2022-02-01", "NX02": "2021-03-01", "NX03": "2021-05-03", "NS01": "2019-03-01", "NS02": "2021-05-17", "NC01": "2019-09-03", "NC02": "2020-06-01", "NSPL": "2023-04-03", "NMSP": "2023-03-01", "NGAP": "2023-05-03"}
    for nm, d in special.items():
        first[nm] = row(d)
        new.append(nm)
    gaps = {"NX01": [(first["NX01"] + 1, first["NX01"] + 40)], "NX02": [(first["NX02"] + a, first["NX02"] + a) for a in (3, 7, 12)], "NX03": [(first["NX03"] + a, first["NX03"] + a) for a in (3, 7)]}
    last = {"DLST": row("2024-05-31")}
    d = lambda r_: f"{days[r_]:%Y-%m-%d}"
    fmt = lambda s: f"{pd.Timestamp(s):%Y-%m-%d}"
    spin = [("NS01", "S05", d(first["NS01"] + 15)), ("NS02", "S06", d(first["NS02"] + 15)), ("N105", "S08", "2025-07-02")]                         # (the last one is dated after the cut: dropped at read)
    chg = [("OLDQ1", "NC01", d(first["NC01"] + 40)), ("OLDQ2", "NC02", d(first["NC02"] + 400)), ("OLDS7", "S07", "2019-06-03"), ("OLDS12", "S12", "2018-02-12"), ("OLDQ4", "N104", "2025-08-01")]
    names = seas + new
    N, ix = len(names), names.index
    r2 = np.random.default_rng(11)
    p0, vol = r2.uniform(60.0, 300.0, N), r2.uniform(1.5e6, 6e6, N)
    beta, idio = r2.uniform(0.5, 1.5, N), r2.uniform(0.009, 0.014, N)
    for nm, (p_, v_) in {"LOWP": (3.0, None), "LOWV": (None, 3e5), "LOWA": (10.0, None), "SPL": (400.0, 8e6), "NSPL": (300.0, 8e6)}.items():      # below the price floor / the volume floor / the ATR floor; the split names keep their raw pre-split volume above 1M
        if p_ is not None:
            p0[ix(nm)] = p_
        if v_ is not None:
            vol[ix(nm)] = v_
    idio[ix("LOWA")] = 0.0015
    div = []
    for k in range(1, 21):
        for r_ in range(20 + k, len(days), 63):
            div.append((f"S{k:02d}", d(r_), round(0.008 * float(p0[ix(f"S{k:02d}")]), 4)))
    split = [("SPL", fmt("2024-03-15")), ("NSPL", fmt("2024-03-15"))]
    return SimpleNamespace(names=names, seasoned=seas, new=new, first=first, last=last, gaps=gaps, special=special, spin=spin, chg=chg, div=div, split=split, row=row, p0=p0, vol=vol, beta=beta, idio=idio,
                           gday={"SPL": (row("2024-03-15"), 2.0), "NSPL": (row("2024-03-15"), 2.0)}, msp={"NMSP": (row("2023-11-14"), 4.0)}, jump={"NGAP": (row("2024-05-14"), 1.6)})


class NewFake(S.Fake):
    """r5_siporb's fake Alpaca transport serving SYNTHETIC DAILY bars (no minute bars: this family reads none) of the plan's names on continuous business days: close-to-close log return = beta x the fake ES master's return + noise (S.Fake's own special names are not used: the plan's cast is); a name
    has bars from its first row to its last, except the plan's gaps; a cash dividend of the plan is taken off the OPEN of its ex-date (so the total return is the price return); `drift` puts a daily drift on every NEW name over the sessions 100 .. 560 after its listing (the planted underperformance), `bear` one on EVERY name over every session; the same random
    numbers otherwise, so drift = bear = 0 is the null world of the same market. SPL / NSPL: a registered 2-for-1 (the raw price before it is twice the adjusted one), NMSP: a x4 that was never adjusted (from its session on every price is x4 and the volume / 4), NGAP: a genuine +60% overnight gap. The 1Day request is served from rows built once"""
    def __init__(self, days, mkt, plan, drift=0.0, bear=0.0, page=2500):
        self.days, self.D, self.page, self.n, self.auth_fail, self._st, self._rowcache = [f"{d:%Y-%m-%d}" for d in days], len(days), page, 0, False, {}, {}
        rng = np.random.default_rng(12)
        self.names = names = list(plan.names)
        self.k, N, ix = {n: k for k, n in enumerate(names)}, len(names), names.index
        D = self.D
        self.p0, self.vol, beta, idio = plan.p0.copy(), plan.vol.copy(), plan.beta, plan.idio
        self.first = np.array([plan.first[n] for n in names])
        self.last = np.array([plan.last.get(n, D - 1) for n in names])
        self.gday = {ix(n): v for n, v in plan.gday.items()}
        self.msp = {ix(n): v for n, v in plan.msp.items()}
        self.jump = {ix(n): v for n, v in plan.jump.items()}
        nobar = np.zeros((D, N), bool)
        for nm, rr in plan.gaps.items():
            for a, b in rr:
                nobar[a:b + 1, ix(nm)] = True
        eps = rng.standard_normal((D, N)) * idio
        gap = rng.standard_normal((D, N)) * 0.003
        w1, w2 = np.abs(rng.standard_normal((D, N))) * 0.004, np.abs(rng.standard_normal((D, N))) * 0.004
        vn = rng.lognormal(0.0, 0.25, (D, N))
        r = beta * np.asarray(mkt, float)[:, None] + eps
        if drift:
            age = np.arange(D)[:, None] - self.first[None, :]
            r += drift * ((age >= SMOKE_AGE[0]) & (age <= SMOKE_AGE[1]) & (self.first[None, :] > 0))
        if bear:
            r += bear
        for k, (d, f) in self.jump.items():
            r[d, k] += math.log(f)
            gap[d, k] += math.log(f)
        divamt = np.zeros((D, N))
        for sym, ex, amt in plan.div:
            t = self.days.index(ex) if ex in self.days else -1
            if t >= 0:
                divamt[t, ix(sym)] += amt
        self.daily, self.f5, self.opx = np.full((N, D, 5), np.nan), np.full((N, D, 5), np.nan), np.full((N, D), np.nan)
        prev = self.p0.copy()
        for d in range(D):
            o = (prev - divamt[d]) * np.exp(gap[d])
            c = o * np.exp(r[d] - gap[d])
            live = (d >= self.first) & (d <= self.last) & ~nobar[d]
            h, lo = np.maximum(o, c) * (1.0 + w1[d]), np.minimum(o, c) * (1.0 - w2[d])
            v = np.round(self.vol * vn[d]) + 1
            for q, a in enumerate((o, h, lo, c, v)):
                self.daily[:, d, q] = np.where(live, a, np.nan)
            prev = np.where(live, c, prev)
        self._valid = [np.flatnonzero(~np.isnan(self.daily[k, :, 0])) for k in range(N)]
        self._ts = [pd.Timestamp(d, tz="US/Eastern").tz_convert("UTC").strftime("%Y-%m-%dT%H:%M:%SZ") for d in self.days]

    def assets(self, p):
        return [a for a in super().assets(p) if a["symbol"] != "ZZBAD"]

    def bars(self, p):
        if p["timeframe"] != "1Day":
            return super().bars(p)
        syms, d0, d1, adj = sorted(s for s in p["symbols"].split(",") if s in self.k), p["start"][:10], p["end"][:10], p["adjustment"]
        key = (tuple(syms), d0, d1, adj)
        if key not in self._rowcache:
            rows = []
            for s in syms:
                k = self.k[s]
                for d in self._valid[k]:
                    if d0 <= self.days[d] <= d1:
                        rows.append((s, self._ts[d], *self.sc(k, d, self.daily[k, d], adj)))
            self._rowcache = {key: rows}
        rows = self._rowcache[key]
        off = int(p.get("page_token") or 0)
        out = {}
        for r in rows[off:off + self.page]:
            out.setdefault(r[0], []).append({"t": r[1], "o": r[2], "h": r[3], "l": r[4], "c": r[5], "v": r[6]})
        return {"bars": out, "next_page_token": str(off + self.page) if off + self.page < len(rows) else None}


def smoke_ca_rows(plan):
    """r16_xgap's flat CSV (r17_resmom.CA_COLS) of the synthetic calendar: the quarterly dividends, the two registered splits, the spin-offs' new symbols and the name changes of the plan, plus the cases the loaders count and do not use (a spin-off without a new symbol or a date, a name change without a symbol or a date, a name not on the grid,
    a dividend on the cut day and after it)"""
    rows = [f"cash_dividend,{s},,,{ex},{ex},,,{amt},,,,False" for s, ex, amt in plan.div]
    rows += [f"forward_split,{s},,,{ex},{ex},,,,2,1,," for s, ex in plan.split]
    rows += [f"spin_off,{par},,{nw},{ex},{ex},,,,0.1,1,," for nw, par, ex in plan.spin]
    rows += [f"name_change,,{o},{n},,{ex},,,,,,," for o, n, ex in plan.chg]
    rows += ["spin_off,S09,,,2019-03-05,2019-03-05,,,,0.1,1,,", "spin_off,S10,,N050,,,,,,0.1,1,,", "name_change,,,,,2019-04-09,,,,,,,", "name_change,,OLDQ9,N051,,,,,,,,,", "cash_dividend,ZZZZ,,,2024-02-07,2024-02-07,,,0.9,,,,False",
             "cash_dividend,S01,,,2025-06-30,2025-06-30,,,0.5,,,,False", "cash_dividend,S02,,,2025-07-01,2025-07-01,,,0.5,,,,False"]
    return rows


@contextlib.contextmanager
def smoke_env(root, nrep=100, build=("plant", "null", "bear")):
    """everything the smoke patches, restored on exit: OUT and every module's output folder into `root`, CHECK_BOOK off, NREP = nrep, the wide calendar's pinned sha = the synthetic file's, the REPORTED floor shrunk (20 -> 18; the registered 10 stays), r5_siporb's transport = NewFake (one cache per world), the ES registry = the fake master, the TBIS file, a fake #463, a
    stub of RESMOM's WF line file (DV.REF_CSV / DV.REF_SHA). Builds the worlds in `build` ('plant' = the new-issue underperformance, 'null' = none, 'bear' = every name drifts down) through r5_siporb's own pulls. Yields a namespace: root, days, esf, plan, fk {world: NewFake}, cache {world: folder}, switch(world), wide_sha, wide_csv, wide_manifest, ref_csv, ref_sha, ca_rows"""
    root = os.path.abspath(root)
    why = smoke_refusal(root)
    if why:
        raise SystemExit(why)
    data = A13.data_mod()
    keep = dict(S=(S.OUT, S.CACHE, S.BOOK, S.SMOKE, S.PACE, S.BACKOFF, S.RETRY, S._http_get), es=(data.find_master, data.load_master_arrays), tb=(D15.TBIS_CSV, A13.TBIS_QA), wide=M17.WIDE_CA_SHA, ref=(DV.REF_CSV, DV.REF_SHA))
    shutil.rmtree(root, ignore_errors=True)
    os.makedirs(root)
    with contextlib.ExitStack() as es:
        es.enter_context(patched(THIS, OUT=os.path.join(root, "out"), CHECK_BOOK=False, NREP=nrep))
        es.enter_context(patched(R11, OUT=os.path.join(root, "r11")))
        es.enter_context(patched(A13, OUT=os.path.join(root, "attn_out")))
        es.enter_context(patched(THIS, FLOOR_REPORTED=SMOKE_FLOOR_REPORTED))
        try:
            S.OUT, S.BOOK = os.path.join(root, "siporb_out"), os.path.join(root, "r4", "book463_daily.csv")
            tbis_path = os.path.join(root, "tbis.csv")
            D15.TBIS_CSV = A13.TBIS_QA = tbis_path
            S.SMOKE, S.PACE, S.BACKOFF, S.RETRY = True, 0.0, 0.0, 0.0
            for p in (OUT, R11.OUT, A13.OUT, S.OUT):
                os.makedirs(p)
            inside = lambda p: os.path.commonpath([os.path.realpath(p), os.path.realpath(root)]) == os.path.realpath(root)
            assert all(inside(p) for p in (OUT, R11.OUT, A13.OUT, S.OUT, tbis_path)), "every path the smoke writes is inside the smoke dir"
            days = pd.bdate_range("2016-01-04", "2026-06-30")                                  # the cache's first session .. the lockbox's end: the WF stretch is whole, the cut (2025-06-30) has a year of days to cut and Stage B has its sealed year
            t0 = time.time()
            esf, mkt = DV.smoke_market(days)
            plan = smoke_plan(days)
            ca_rows = smoke_ca_rows(plan)
            env = SimpleNamespace(root=root, days=days, esf=esf, mkt=mkt, plan=plan, fk={}, cache={}, wide_files={}, ca_rows=ca_rows)
            for world in build:
                fk = NewFake(days, mkt, plan, drift=SMOKE_DRIFT if world == "plant" else 0.0, bear=SMOKE_BEAR if world == "bear" else 0.0)
                env.fk[world] = fk
                env.cache[world] = os.path.join(root, f"cache_{world}")
                S.CACHE, S._http_get = env.cache[world], fk.handle
                with contextlib.redirect_stdout(io.StringIO()):
                    S.assets()
                    S.daily()
                xd = os.path.join(env.cache[world], "xgap")
                os.makedirs(xd, exist_ok=True)
                csv_p, man_p = os.path.join(xd, M17.WIDE_NAME + ".csv"), os.path.join(xd, M17.WIDE_NAME + "_manifest.json")
                with open(csv_p, "w", newline="\n") as f:
                    f.write("\n".join([",".join(M17.CA_COLS)] + ca_rows) + "\n")
                env.wide_files[world] = (csv_p, man_p)
                env.wide_sha = M17.sha_raw(csv_p)
                with open(man_p, "w") as f:
                    json.dump({"created": "2026-10-05T10:00:00", "start": "2016-06-01", "end": "2026-06-30", "rows": len(ca_rows), "sha256": {M17.WIDE_NAME + ".csv": env.wide_sha}}, f)
            env.build_seconds = time.time() - t0
            M17.WIDE_CA_SHA = env.wide_sha
            esf.install()
            A13.smoke_book()
            b0, _legs0 = A13.load_463()                                                        # [X1] a STUB of RESMOM's WF line file on the synthetic #463 (never the real file): its sha256 and path are patched in as the registered ones, restored on exit
            k0 = np.flatnonzero(b0.mask(WF0, PRE_END))
            env.ref_res = np.random.default_rng(31).normal(6.0, 320.0, len(k0))
            env.ref_csv = os.path.join(root, "resmom", "resmom_cells_daily_wf.csv")
            env.ref_sha = DV.write_ref_csv(env.ref_csv, b0, env.ref_res)
            assert inside(env.ref_csv), "the stub is inside the smoke dir"
            DV.REF_CSV, DV.REF_SHA = env.ref_csv, env.ref_sha
            with open(os.path.join(S.OUT, "siporb_cache_manifest.json"), "w") as f:
                json.dump({"manifest_sha256": D15.MANIFEST_PREFIX + "0" * 56, "files": 0}, f)
            with open(tbis_path, "w") as f:
                f.write("symbol,day,price_ratio,vol_ratio,split_like\nNMSP,2023-11-14,4.0,0.25,True\nNSPL,2024-03-15,0.5,2.1,True\nS03,2024-02-13,0.5,1.0,False\nZZZZ,2024-02-14,0.5,2.0,True\nS07,2025-07-01,0.5,2.0,True\n")

            def switch(world):
                S.CACHE, S._http_get = env.cache[world], env.fk[world].handle
                env.wide_csv, env.wide_manifest = env.wide_files[world]
            env.switch = switch
            if build:
                switch(build[0])
            yield env
        finally:
            S.OUT, S.CACHE, S.BOOK, S.SMOKE, S.PACE, S.BACKOFF, S.RETRY, S._http_get = keep["S"]
            data.find_master, data.load_master_arrays = keep["es"]
            D15.TBIS_CSV, A13.TBIS_QA = keep["tb"]
            M17.WIDE_CA_SHA = keep["wide"]
            DV.REF_CSV, DV.REF_SHA = keep["ref"]


def smoke_world(env, world):
    """the World a stage reads, built through the REAL loaders with the calls stage_a makes (every input cut at 2025-06-30 at read time): (W, cal, extra, winfo, einfo, tbis); the raw dividend / spin-off inputs are placed again by plain python from the csv rows (W.Dr_in / W.Sp_in) for the recounts"""
    env.switch(world)
    with quiet():
        D = M17.load_data(S.LB0)
    tbis = D15.load_tbis(S.LB0)
    es_frames, _meta = D15.load_es(S.LB0)
    with quiet():
        cal, winfo = M17.wide_load(S.LB0)
        W = M17.build_world(D, S.LB0, es_frames, tbis, cal)
    D15.release(D)
    extra, einfo = cal_extra(S.LB0)
    cut_checks(W, cal, extra, S.LB0)
    csv_path = M17.wide_paths()["csv"]
    W.Dr_in = M17.brute_div_matrix(csv_path, W.days, W.syms, S.LB0)
    W.Sp_in = M17.brute_spin_matrix(csv_path, W.days, W.syms, S.LB0)
    return W, cal, extra, winfo, einfo, tbis


def smoke_world_b(env, world):
    """the same World at the lockbox's END (Stage B's own loads: every input cut at the lockbox's last day): (W, cal, extra, winfo, einfo, tbis)"""
    env.switch(world)
    with quiet():
        D = M17.load_data(S.END)
    tbis = D15.load_tbis(S.END)
    es_frames, _meta = D15.load_es(S.END)
    with quiet():
        cal, winfo = M17.wide_load(S.END)
        W = M17.build_world(D, S.END, es_frames, tbis, cal)
    D15.release(D)
    extra, einfo = cal_extra(S.END)
    cut_checks(W, cal, extra, S.END)
    return W, cal, extra, winfo, einfo, tbis


# ------------------------------------------------------------------ smoke: the dryload's printout, the loaders' world against plain-python recounts, then every command end to end
def dryload_text_checks(txt, cal=True):
    """the dryload's printout is COUNTS: no price, return, hedge ratio, correlation, P&L or statistic (nothing like a dollar amount, ROC, Sortino, P&L, drawdown, a realised beta), no date on / after the cut but the one line that names the cut, and the count lines it promises"""
    outcome = re.search(r"[$]\s*-?\d|ROC|Sortino|P&L|net [$]|drawdown|Stage A \(|realised beta|correlation|hedge ratio [+-]?\d|beta [+-]\d", txt)
    assert not outcome, ("the dryload printed an outcome", txt[max(outcome.start() - 80, 0):outcome.end() + 80])
    dates = [d for l in txt.splitlines() if "cut to dates <" not in l for d in re.findall(r"\b20\d\d-\d\d-\d\d\b", l)]
    assert dates and all(d < "2025-06-30" for d in dates), [d for d in dates if d >= "2025-06-30"][:5]
    frags = ["prereg check:", "every input cut to dates < 2025-06-30", "universe size per session by year", "LISTING SESSIONS [N4]", "every cached name: present at the first session", "the names ever in the universe: present at the first session",
             "rebalances: ", "first traded rank", "months under the ", f"bar (a) [N8] needs >= {RULES['reb']} traded rebalances", "TRADED MONTHS UNDER BOTH FLOORS [N7]", f"months under the {FLOOR_REPORTED}-name floor (", "LOW-POWER FLAG [N9]", "under the registered",  "NEW names per month (survivors of every removal", "NEW name-months by listing cohort", "by fill year (rebalances: NEW min / median / max", "NEW names by fill year", "SEASONED names by fill year",
             "rebalance bookkeeping by fill year", "registered exclusions by fill year", "TBIS flags:", "ES prints on the", "ES return (", "cache manifest sha256", "dryload took"]
    frags += ["calendar tables this family reads", "calendar coverage:", "calendar name-change coverage:"] if cal else ["not on file yet", "this dryload counted no spinco / name-change exclusion"]
    for frag in frags:
        assert frag in txt, frag


def smoke_recount(env, W, ctx):
    """everything this file adds, on the world the REAL loaders built, against plain-python recounts: the listing session and [N4] status of every name (and the planted cases against the PLAN), the calendar's two tables on the grid, the NEW and SEASONED sets of every WF rank in both readings (the age
    windows, the spinco / name-change exclusions, the hygiene windows, the history rule), the planted hygiene cases, the ex-ante beta and the ES leg of every traded rebalance, the nearest-dollar-volume match, both cells' daily series (costs, borrow, the sides) and four draws of the null -> (leg, counts)"""
    t0 = time.time()
    plan, days = env.plan, W.days
    ix = [str(s_) for s_ in W.syms]
    T = W.T
    li = brute_listing(W)
    for j, (first, L_, st, n) in enumerate(li):
        assert (int(ctx.li.first[j]), int(ctx.li.L[j]), int(ctx.li.st[j]), int(ctx.li.n_after[j])) == (first, L_, st, n), ix[j]
    # ---- the listing sessions of the PLAN: a name's first bar is its listing session; the stray bar and the 17-of-20 listing fail [N4], the 18-of-20 one is accepted; the names present at the first session have no listing session
    got = {}
    for nm in plan.names:
        if nm not in ix:
            assert nm in ("LOWP", "LOWV", "LOWA", "N113") or plan.first[nm] > T - 1, (nm, "absent from the names ever in the universe")
            continue
        j = ix.index(nm)
        got[nm] = (int(ctx.L[j]), int(ctx.st[j]), int(ctx.li.n_after[j]))
        if plan.first[nm] == 0:
            assert got[nm][1] == ST_START and got[nm][0] == -1, (nm, got[nm])
        else:
            want = ST_FAIL if nm in ("NX01", "NX02") else (ST_OK if plan.first[nm] + SPEC["n4_next"] <= T - 1 else ST_LATE)
            assert got[nm][0] == plan.first[nm] and got[nm][1] == want, (nm, got[nm], plan.first[nm], want)
    assert got["NX01"][2] == 0 and got["NX02"][2] == 17 and got["NX03"][2] == 18 and got["NX03"][1] == ST_OK, (got["NX01"], got["NX02"], got["NX03"])
    lw = listing_counts(days, ctx.li)
    by = Counter(int(days[plan.first[nm]].year) for nm in plan.new if nm in ix)
    assert {y: v["dated"] for y, v in lw["by_year"].items()} == dict(by) and lw["present_at_first_session"] == sum(1 for nm in plan.seasoned if nm in ix) and lw["no_bar"] == 0, lw
    assert {y: v["failed"] for y, v in lw["by_year"].items() if v["failed"]} == {2021: 1, 2022: 1} and sum(v["unverifiable"] for v in lw["by_year"].values()) == 0, "NX02 (2021) and NX01 (2022) fail [N4]"
    # ---- the calendar's two tables on the grid (rows dated on / after the cut were dropped at read)
    cut = S.LB0
    spin_want = np.full(W.S, T + 10 ** 6, np.int64)
    chg_want = np.zeros((T + 1, W.S), np.int32)
    n_sp = n_ch = 0
    for nw, _par, d in plan.spin:
        if TS(d) < cut and nw in ix:
            spin_want[ix.index(nw)] = min(spin_want[ix.index(nw)], first_on_or_after(days, d))
            n_sp += 1
    for o, n_, d in plan.chg:
        if TS(d) < cut:
            for sym in (o, n_):
                if sym in ix:
                    chg_want[first_on_or_after(days, d) + 1:, ix.index(sym)] += 1
                    n_ch += 1
    assert (ctx.spin_row == spin_want).all() and (ctx.nccs == chg_want).all() and ctx.cal_counts == {"spin_events_placed": n_sp, "name_change_events_placed": n_ch} and n_sp == 2 and n_ch == 4, ctx.cal_counts
    # ---- the NEW / SEASONED sets of every WF rank, both readings, against the recount
    L = ni_build(W, ctx, WFN, PRE_END, "remove")
    Lk = ni_build(W, ctx, WFN, PRE_END, "naive")
    assert len(L.recs) == len(Lk.recs) == 89 and [q.r for q in L.recs] == [q.r for q in Lk.recs], "89 month-end ranks 2017-12-29 .. 2025-04-30"
    spin = [(nw, par, d) for nw, par, d in plan.spin]
    chg = [(o, n_, d) for o, n_, d in plan.chg]
    memo, real_bl = {}, brute_listing

    def bl(W_, sp=None):
        key = (id(W_), tuple(sorted((sp or SPEC).items())))
        if key not in memo:
            memo[key] = real_bl(W_, sp)
        return memo[key]
    sets = {"remove": {}, "naive": {}}
    with patched(THIS, brute_listing=bl):
        for rec, reck in zip(L.recs, Lk.recs):
            for mode, q in (("remove", rec), ("naive", reck)):
                nb, sb = brute_sets(W, spin, chg, rec.r, rec.f, rec.x, mode)
                assert sorted(nb) == sorted(str(s_) for s_ in W.syms[q.new]) and sorted(sb) == sorted(str(s_) for s_ in W.syms[q.seas]), (mode, f"{days[rec.r]:%Y-%m-%d}")
                sets[mode][rec.r] = (set(nb), set(sb))
        for rec in L.recs:                                                                    # the incl readings and the [N3] window, on a sample of ranks
            if rec.r % 5:
                continue
            for kw in ({"incl": (True, False)}, {"incl": (False, True)}, {"incl": (True, True)}, {"win": (SPEC["n3_lo"], SPEC["n3_hi"])}):
                q = ni_one(W, ctx, rec.r, rec.f, rec.x, "remove", units=False, **kw)[0]
                nb, _sb = brute_sets(W, spin, chg, rec.r, rec.f, rec.x, "remove", win=kw.get("win"), incl=kw.get("incl", (False, False)))
                assert sorted(nb) == sorted(str(s_) for s_ in W.syms[q.new]), (kw, f"{days[rec.r]:%Y-%m-%d}")
    n_sets = 2 * len(L.recs)
    # ---- the planted cases, read off the sets: who is NEW and who is SEASONED where the plan says
    new_any = {mode: set().union(*(v[0] for v in sets[mode].values())) for mode in sets}
    seas_any = {mode: set().union(*(v[1] for v in sets[mode].values())) for mode in sets}
    assert not ({"NX01", "NX02", "NS01", "NS02", "NC01"} & new_any["remove"]) and not ({"NX01", "NX02"} & (seas_any["remove"] | new_any["naive"])), "failed listings, spincos and the always-changed name are never NEW"
    assert "NX03" in new_any["remove"] and "NC02" in new_any["remove"], "the 18-of-20 listing and the late name change are NEW"
    ages = {q.r: {str(W.syms[c_]): int(q.r - cl) for c_, cl in zip(q.new.tolist(), q.lrow.tolist())} for q in L.recs}
    nc02 = [a["NC02"] for a in ages.values() if "NC02" in a]
    assert nc02 and max(nc02) < 400 and min(nc02) >= SPEC["new_lo"], "NC02's name change 400 sessions after its listing excludes it only from then on"
    rk = lambda y, m: next(q.r for q in L.recs if days[q.r].year == y and days[q.r].month == m)                                  # the rank of a month = its last session
    seas_at = lambda y, m: sets["remove"][rk(y, m)][1]
    assert "S12" in seas_at(2018, 1) and "S12" not in seas_at(2018, 2) and "S12" not in seas_at(2020, 1) and "S12" in seas_at(2020, 2), "S12's name change (2018-02-12): out of SEASONED for 24 months"
    assert "S07" in seas_at(2019, 5) and "S07" not in seas_at(2019, 6) and "S07" not in seas_at(2021, 5) and "S07" in seas_at(2021, 6), "S07's name change (2019-06-03)"
    for nm, d in (("NSPL", "2024-03-15"), ("NMSP", "2023-11-14"), ("NGAP", "2024-05-14")):                                  # a flag inside a hold removes the name in the registered reading and keeps it (naive raw path) in the look-ahead one
        t = days.get_loc(TS(d))
        q = next(q_ for q_ in L.recs if q_.r < t <= q_.x)
        assert nm in sets["naive"][q.r][0] and nm not in sets["remove"][q.r][0], (nm, d)
    assert "NSPL" not in sets["remove"][rk(2024, 3)][0] and "NGAP" not in sets["remove"][rk(2024, 5)][0] and "NMSP" not in sets["remove"][rk(2024, 2)][0], "a flag in the 125 sessions before the rank removes the name"
    assert "DLST" in seas_any["remove"] and "SPL" in seas_any["remove"] and not ({"LOWA"} & (seas_any["remove"] | new_any["remove"])), "the delisted and the split names are SEASONED, the name below the ATR floor is nobody"
    # ---- the ex-ante hedge, the ES leg and the match of every traded rebalance
    for q in L.recs:
        assert q.traded
        b, k = brute_beta(W, q.r, q.new.tolist())
        assert q.bpairs == k and ((math.isnan(b) and math.isnan(q.beta)) or abs(q.beta - b) < 1e-9), (f"{days[q.r]:%Y-%m-%d}", q.beta, b)
        for bps in (ES_BPS, 0.0):
            assert usd(es_leg(W, q.f, q.x, bps), brute_es_leg(W, q.f, q.x, bps)), (f"{days[q.r]:%Y-%m-%d}", bps)
        mt = brute_match([brute_dv(W, q.r, int(c_)) for c_ in q.new], [brute_dv(W, q.r, int(c_)) for c_ in q.seas], q.new.tolist(), q.seas.tolist())
        assert q.match.tolist() == [q.n_new + m if m >= 0 else -1 for m in mt], f"{days[q.r]:%Y-%m-%d}"
    # ---- both cells' daily series: the base, 10 bps, 10% borrow, each side alone
    runs = 0
    for cell in CELLS:
        for kw in ({}, {"bps": 10.0}, {"borrow": 0.10}, {"side": -1}, {"side": 1}):
            xb, nb = brute_cell_series(W, L, cell, **kw)
            run = cell_run(W, L, cell, cfg_of(**{k_: v for k_, v in kw.items() if k_ in ("bps", "borrow")}), side=kw.get("side", 0))
            assert usd(run.x, xb) and run.n_pos == nb and abs(run.x.sum()) > 1.0, (cell, kw)
            runs += 1
    # ---- four draws of the null: the pseudo-NEW names (random SEASONED ones) shorted, E's hedge re-estimated on them, M re-matched among the rest
    acc = ni_null(W, L, 4, 0)
    rng = np.random.default_rng([SEED, 0])
    want = {c_: np.zeros((4, T)) for c_ in CELLS}
    slot = SPEC["slot"]
    for q in L_recs(L):
        if not (q.tE or q.tM) or q.n_seas < q.n_new or q.n_new == 0:
            continue
        draw = D15.draw_order(rng, 4, q.n_seas, q.n_new)
        for d in range(4):
            names = q.seas[draw[d]].tolist()
            sh = sum(np.array(brute_position(W, q.f, q.x, int(c_), -1, COST_BPS, BORROW)) for c_ in names)
            if q.tE:
                b, _k = brute_beta(W, q.r, names)
                if math.isfinite(b):
                    want["E"][d, q.f:q.x + 1] += sh + b * len(names) * slot * brute_es_leg(W, q.f, q.x, ES_BPS)
            if q.tM:
                rest = [c_ for c_ in q.seas.tolist() if c_ not in set(names)]
                mt = brute_match([brute_dv(W, q.r, c_) for c_ in names], [brute_dv(W, q.r, c_) for c_ in rest], names, rest)
                for c_, m in zip(names, mt):
                    if m >= 0:
                        want["M"][d, q.f:q.x + 1] += np.array(brute_position(W, q.f, q.x, int(c_), -1, COST_BPS, BORROW)) + np.array(brute_position(W, q.f, q.x, int(rest[m]), +1, COST_BPS, BORROW))
    for c_ in CELLS:
        assert usd(acc[c_], want[c_]) and np.abs(acc[c_]).sum() > 1.0, c_
    return L, {"names": W.S, "sets": n_sets, "rebalances": len(L.recs), "cell_runs": runs, "listing_years": len(lw["by_year"]), "seconds": round(time.time() - t0)}, sets


# ------------------------------------------------------------------ plain-python recounts of what a stage reports: positions, statistics, the age path, the cohorts
def brute_positions(W, L, cell, bps=COST_BPS, borrow=BORROW, es_bps=ES_BPS):
    """plain python: every position of a cell in the order cell_run's table lists them (the rebalances in order, a rebalance's NEW names in the leg's order, an unmatched NEW name of M left out) -> [{ri, rec, col, mcol, short (daily list over rows f .. x), other, pnl, short_pnl, other_pnl}]"""
    out, slot = [], SPEC["slot"]
    for ri, q in enumerate(L.recs):
        if not traded(q, cell):
            continue
        es = brute_es_leg(W, q.f, q.x, es_bps)
        mt = brute_match([brute_dv(W, q.r, int(c_)) for c_ in q.new], [brute_dv(W, q.r, int(c_)) for c_ in q.seas], q.new.tolist(), q.seas.tolist()) if cell == "M" else None
        for i, col in enumerate(q.new):
            if mt is not None and mt[i] < 0:
                continue
            s_ = np.array(brute_position(W, q.f, q.x, int(col), -1, bps, borrow))
            mcol = int(q.seas[mt[i]]) if mt is not None else -1
            o_ = q.beta * slot * es if cell == "E" else np.array(brute_position(W, q.f, q.x, mcol, +1, bps, borrow))
            out.append({"ri": ri, "rec": q, "col": int(col), "mcol": mcol, "short": s_, "other": o_, "pnl": float(s_.sum() + o_.sum()), "short_pnl": float(s_.sum()), "other_pnl": float(o_.sum())})
    return out


def brute_series_of(W, pos):
    """a cell's daily $ series on the stock sessions and its positions held per row, from brute_positions"""
    x, c = np.zeros(W.T), np.zeros(W.T)
    for p in pos:
        q = p["rec"]
        x[q.f:q.x + 1] += p["short"] + p["other"]
        c[q.f:q.x + 1] += 1
    return x, c


def plain_cell_stats(xs, ds, cs, pnl):
    """plain python recount of r15's cell_stats (and this file's three extra nets) on one stretch: xs the daily series, ds the dates, cs the positions held per row, pnl the positions' P&Ls (the position table of the stretch)"""
    ds = pd.DatetimeIndex(ds)
    st = DV.plain_stats(xs, ds)
    by = {y: 0.0 for y in YEARS}
    for v, d in zip(xs, ds):
        y = d.year - (1 if d.month < 7 else 0)
        if y in by:
            by[y] += float(v)
    net = st["net"]
    held = sorted((float(v) for v, c_ in zip(xs, cs) if c_ > 0), reverse=True)
    md = -(-len(held) // 100)
    pp = sorted((float(v) for v in pnl), reverse=True)
    mp = -(-len(pp) // 100)
    inr = lambda d, a, b: TS(a) <= d <= TS(b)
    tot = lambda a, b: float(sum(float(v) for v, d in zip(xs, ds) if inr(d, a, b)))
    return {"net": net, "roc": st["roc"], "sortino": st["sortino"], "max_dd": st["max_dd"], "by_year": by, "years_pos": sum(1 for v in by.values() if v > 0), "net_ex2020": net - tot("2020-02-15", "2020-04-30"),
            "net_2022": tot("2022-01-01", "2022-12-31"), "net_ex2022": net - tot("2022-01-01", "2022-12-31"), "net_2020_21": tot("2020-01-01", "2021-12-31"), "net_ex_best_days": net - sum(held[:md]), "net_pos": sum(pp),
            "net_ex_best_pos": sum(pp) - sum(pp[:mp]), "top_pos": pp[0] if pp else float("nan"), "net_ex_top_pos": sum(pp) - (pp[0] if pp else 0.0)}


def plain_age_path(W, pos, lrow, lo):
    """plain python: the path by months since listing - every mark (row >= the stretch's first) of every position into month = (row - the NEW name's listing row) // 21: name-days, the short side's $, the other side's $"""
    r0 = first_on_or_after(W.days, lo)
    acc = {}
    for p in pos:
        q = p["rec"]
        for h in range(q.x - q.f + 1):
            t = q.f + h
            if t < r0:
                continue
            a = acc.setdefault(int((t - lrow[p["col"]]) // SPEC["month"]), {"days": 0, "short": 0.0, "other": 0.0})
            a["days"] += 1
            a["short"] += float(p["short"][h])
            a["other"] += float(p["other"][h])
    return dict(sorted(acc.items()))


def plain_cohort(W, pos, lrow, short_only=False):
    """plain python: the P&L by listing-year cohort of the NEW name (short_only = the short side alone: its pnl is the short side's and the other side is nothing)"""
    out = {}
    for p in pos:
        o = out.setdefault(int(W.days[lrow[p["col"]]].year), {"name_months": 0, "cols": set(), "net": 0.0, "short": 0.0, "other": 0.0})
        o["name_months"] += 1
        o["cols"].add(p["col"])
        o["short"] += p["short_pnl"]
        o["other"] += 0.0 if short_only else p["other_pnl"]
        o["net"] += p["short_pnl"] if short_only else p["pnl"]
    return out


# ------------------------------------------------------------------ the planted world's Stage A file against plain-python recounts of every number it reports
def smoke_stage_recount(cx):
    """everything Stage A wrote for the PLANTED world, recomputed here from the recount-verified leg, the book file and the stub's own RES column by code that shares nothing with the stage's statistics: every cell's WF numbers (the daily series, the position table, the stress / cost / borrow rows, the sides, the
    regime halves, the July-June years), the realised beta, the null's draws and percentiles, the eleven (a)-(e) checks re-judged, A2 and its 0.5c / 2c rows, the reference and its drawdown episodes, the #70 gate's DO and its null, the path by months since listing, the cohorts, the 20 largest name-months, NEW names per month,
    the hedge ratios, the hygiene counts of the two readings and the JSON file (cx: env, W, ctx, L, sets, B, rowsB, ref, out, plan)"""
    env, W, ctx, L, sets, B, rowsB, ref, out, plan = cx.env, cx.W, cx.ctx, cx.L, cx.sets, cx.B, cx.rowsB, cx.ref, cx.out, cx.plan
    cells, nul, rep = out["stageA"]["cells"], out["stageA"]["null"], out["reports"]
    days, slot = W.days, SPEC["slot"]
    k, kw = np.flatnonzero(B.mask(WFN, PRE_END)), np.flatnonzero(B.mask(WF0, PRE_END))
    ds = B.index[k]
    lrow = [int(v) for v in ctx.L]
    toB = lambda x: D15.to_B(x, rowsB, B.n)
    n = {}
    # ---- the reference book, rebuilt from the book file and the stub's own RES column
    dfr = pd.read_csv(env.ref_csv)
    ref_raw = np.full(B.n, np.nan)
    ref_raw[kw] = np.asarray(B.raw, float)[kw] + 0.264 * dfr["RES"].to_numpy(float)
    ref_s = DV.plain_stats(ref_raw[kw], B.index[kw])
    eps_p, qual_p = DV.plain_episodes(ref_raw[kw])
    mask_p = np.zeros(len(kw), bool)
    for _d, i0_, it_, _i1 in qual_p:
        mask_p[i0_:it_ + 1] = True
    mask_n = mask_p & np.asarray(B.index[kw] >= WFN)
    rf = out["reference"]
    assert rf["file"] == "resmom_cells_daily_wf.csv" and rf["sha256"] == rf["pinned_sha256"] == env.ref_sha and rf["rows"] == len(kw) and rf["weight_of_RES"] == 0.264 and rf["max_abs_book_mtm_difference"] < 1e-5
    assert abs(rf["facts"]["roc"] - ref_s["roc"]) < 1e-5 and abs(rf["facts"]["sortino"] - ref_s["sortino"]) < 1e-7 and abs(rf["facts"]["max_dd"] - ref_s["max_dd"]) < 1e-4 and not all(rf["reproduced"].values()), "the synthetic reference is not the registered one"
    assert rf["structure"]["episodes"] == len(qual_p) >= 1 and rf["structure"]["all_episodes"] == len(eps_p) and rf["structure"]["days"] == int(mask_p.sum())
    eps_b, qual_b = DV.plain_episodes(np.asarray(B.raw, float)[kw])                                  # #463's own drawdown days from 2018-02 on: the standalone map point
    mask_b = np.zeros(len(kw), bool)
    for _d, i0_, it_, _i1 in qual_b:
        mask_b[i0_:it_ + 1] = True
    mask_bn = mask_b & np.asarray(B.index[kw] >= WFN)
    # ---- [N10] the reference line's qualifying episodes INSIDE the cell's stretch by plain python: the DD days from 2018-02-01 on (an episode that starts before it is cut), the reference's P&L and the cell's inside each, the cell helps where it earns
    dkw = B.index[kw]
    ins_ = [(i0_, it_, [t for t in range(i0_, it_ + 1) if dkw[t] >= WFN]) for _d, i0_, it_, _i1 in qual_p]
    ins_ = [(i0_, it_, idx_) for i0_, it_, idx_ in ins_ if idx_]

    def check_eis(eis, xcell, label):
        assert eis["episodes_on_wf"] == len(qual_p) and eis["inside"] == len(ins_) == len(eis["rows"]) and eis["cut"] == sum(1 for i0_, _it, idx_ in ins_ if idx_[0] > i0_) and eis["inside"] >= 1, label
        for e_, (i0_, it_, idx_) in zip(eis["rows"], ins_):
            cp_, bp_ = float(xcell[idx_].sum()), float(ref_raw[kw][idx_].sum())
            assert e_["dd_days_inside"] == len(idx_) and e_["dd_days"] == it_ - i0_ + 1 and e_["first_dd_day"] == f"{dkw[idx_[0]]:%Y-%m-%d}" and e_["cut"] is bool(idx_[0] > i0_) and abs(e_["cell_pnl"] - cp_) < 1e-6 and abs(e_["book_pnl"] - bp_) < 1e-6 and e_["helps"] is bool(cp_ > 0), (label, e_)
        assert eis["helped"] == sum(1 for e_ in eis["rows"] if e_["cell_pnl"] > 0) and abs(eis["cell_pnl"] - sum(e_["cell_pnl"] for e_ in eis["rows"])) < 1e-6 and abs(eis["reference_pnl"] - sum(e_["book_pnl"] for e_ in eis["rows"])) < 1e-6, label
    # ---- the positions of both cells (and the variants of the stress rows) by plain python
    pos = {c: brute_positions(W, L, c) for c in CELLS}
    alt = {(c, lab): brute_positions(W, L, c, **kw_) for c in CELLS for lab, kw_ in (("cost0", {"bps": 0.0}), ("10 bps", {"bps": 10.0}), ("20 bps", {"bps": 20.0}), ("10%/yr", {"borrow": 0.10}), ("25%/yr", {"borrow": 0.25}))}
    # ---- the null: NREP draws of the registered stream, recounted
    acc = ni_null(W, L, NREP, 0)
    Y, roc_d, do_d = {}, {}, {}
    for c in CELLS:
        Y[c] = np.zeros((NREP, B.n))
        Y[c][:, rowsB] = acc[c]
        roc_d[c] = np.array([DV.plain_stats(Y[c][d][k], ds)["roc"] for d in range(NREP)])
        do_d[c] = Y[c][:, kw][:, mask_n].sum(axis=1) / -float(ref_raw[kw][mask_n].sum())
    mx, mdo = np.fmax(roc_d["E"], roc_d["M"]), np.fmax(do_d["E"], do_d["M"])
    pc = lambda a, q: float(np.percentile(a[np.isfinite(a)], q))
    assert nul["draws"] == NREP and nul["seed"] == SEED and nul["roc_max"]["finite"] == NREP and nul["do_ref_max"]["finite"] == NREP, nul
    for q, key in ((5, "p5"), (50, "p50"), (95, "p95")):
        assert abs(nul["roc_max"][key] - pc(mx, q)) < 1e-6 and abs(nul["do_ref_max"][key] - pc(mdo, q)) < 1e-9 and all(abs(nul["by_cell"][c][key] - pc(roc_d[c], q)) < 1e-6 for c in CELLS), key
    p95 = pc(mx, 95)
    for c in CELLS:
        P, g = pos[c], cells[c]
        xb, cb = brute_series_of(W, P)
        xB, cB = toB(xb), toB(cb)
        want = plain_cell_stats(xB[k], ds, cB[k], [p["pnl"] for p in P])
        base = g["base"]
        assert base["n_pos"] == len(P) and base["n_units"] == len({p["ri"] for p in P}) == len(L.recs), c
        yo_ = (ds[-1] - ds[0]).days / 365.25                                                  # [N10] dollars a year = net / years of the stretch (the house's years: the last row's date minus the first's, / 365.25)
        assert base["years"] == yo_ and abs(base["usd_per_year"] - want["net"] / yo_) <= 1e-6 * max(1.0, abs(base["usd_per_year"])) and all(abs(g[kk_][bb_]["usd_per_year"] - g[kk_][bb_]["net"] / yo_) < 1e-9 for kk_ in ("stress", "borrow") for bb_ in g[kk_]), c
        for key in ("net", "roc", "sortino", "max_dd", "net_ex2020", "net_2022", "net_ex2022", "net_2020_21", "net_ex_best_days", "net_pos", "net_ex_best_pos", "top_pos", "net_ex_top_pos"):
            assert abs(base[key] - want[key]) <= 1e-6 * max(1.0, abs(want[key])), (c, key, base[key], want[key])
        assert base["years_pos"] == want["years_pos"] and all(abs(base["by_year"][y] - want["by_year"][y]) < 1e-6 for y in YEARS), c
        run = cell_run(W, L, c, cfg_of())
        assert usd(run.pos.pnl, [p["pnl"] for p in P]) and usd(run.pos.short, [p["short_pnl"] for p in P]) and usd(run.pos.other, [p["other_pnl"] for p in P]), c
        assert run.pos.col.tolist() == [p["col"] for p in P] and run.pos.mcol.tolist() == [p["mcol"] for p in P] and run.pos.rec.tolist() == [p["ri"] for p in P], c
        nets = {}
        for key, ent in (("cost0", g["cost0"]), ("10 bps", g["stress"]["10 bps"]), ("20 bps", g["stress"]["20 bps"]), ("10%/yr", g["borrow"]["10%/yr"]), ("25%/yr", g["borrow"]["25%/yr"])):
            w2 = DV.plain_stats(toB(brute_series_of(W, alt[c, key])[0])[k], ds)
            nets[key] = w2["net"]
            assert abs(ent["net"] - w2["net"]) < 1e-6 and abs(ent["roc"] - w2["roc"]) <= 1e-6 * max(1.0, abs(w2["roc"])), (c, key)
        assert nets["cost0"] > base["net"] > nets["10 bps"] > nets["20 bps"] and base["net"] > nets["10%/yr"] > nets["25%/yr"], (c, nets)
        for lab, ent in (("short side only", lambda p: p["short"]), ("long / hedge side only", lambda p: p["other"])):
            xs_ = np.zeros(W.T)
            for p in P:
                xs_[p["rec"].f:p["rec"].x + 1] += ent(p)
            w2 = DV.plain_stats(toB(xs_)[k], ds)
            assert abs(g["sides"][lab]["net"] - w2["net"]) < 1e-6 and abs(g["sides"][lab]["roc"] - w2["roc"]) <= 1e-6 * max(1.0, abs(w2["roc"])), (c, lab)
        assert abs(g["sides"]["short side only"]["net"] + g["sides"]["long / hedge side only"]["net"] - base["net"]) < 1e-6
        for lab, a_, b_ in HALVES:
            km = np.flatnonzero(B.mask(a_, b_))
            wh, h = DV.plain_stats(xB[km], B.index[km]), g["halves"][lab]
            assert h["n_pos"] == sum(1 for p in P if a_ <= days[p["rec"].x] <= b_) and h["n_units"] == len({p["ri"] for p in P if a_ <= days[p["rec"].x] <= b_}) and abs(h["net"] - wh["net"]) < 1e-6 and abs(h["roc"] - wh["roc"]) <= 1e-6 * max(1.0, abs(wh["roc"])), (c, lab)
        assert g["halves"][HALVES[0][0]]["n_pos"] + g["halves"][HALVES[1][0]]["n_pos"] == len(P)
        # [N2] the realised beta: the slope of the day's $ per $ of short notional on ES's return over the days that hold a position
        m_ = np.full(B.n, np.nan)
        m_[rowsB] = W.es.ret
        sel = np.asarray(B.mask(WFN, PRE_END)) & (cB > 0) & np.isfinite(m_)
        yy, mm = xB[sel] / (slot * cB[sel]), m_[sel]
        slope = float(((mm - mm.mean()) * (yy - yy.mean())).sum() / ((mm - mm.mean()) ** 2).sum())
        rb = g["realised_beta"]
        assert rb["n"] == int(sel.sum()) and abs(rb["beta"] - slope) < 1e-9 and g["beta_gate"] == {"beta": rb["beta"], "limit": 0.20, "credited": bool(abs(slope) <= 0.20)}, c
        # the eleven (a)-(e) checks re-judged from the recounted numbers
        want_checks = {f"rebalances>={RULES['reb']}": len({p["ri"] for p in P}) >= 40, "ROC>=15": want["roc"] >= 15.0, "net>0 at 5 bps": want["net"] > 0, "net>0 at 10 bps": nets["10 bps"] > 0, "net>0 at 10%/yr borrow": nets["10%/yr"] > 0,
                       "ROC>null p95": want["roc"] > p95, "positive in >=5 of 8 July-June years": want["years_pos"] >= 5, "net>0 without Feb 15 - Apr 30 2020": want["net_ex2020"] > 0, "net>0 without calendar 2022": want["net_ex2022"] > 0,
                       "profitable without its best 1% of days": want["net_ex_best_days"] > 0, "profitable without its best 1% of name-months": want["net_ex_best_pos"] > 0}
        assert g["checks"] == want_checks and g["PASS"] is all(want_checks.values()), (c, g["checks"], want_checks)
        # A2 (a report) [X1]: c by volatility over 2018-02-01 .. 2020-01-31, the reference + c x the cell against the reference, 0.5c and 2c, the plain #463 + c x cell, the beta rule
        mw = np.asarray(B.mask(*A2_WIN))
        sb, sc = float(np.std(np.asarray(B.raw, float)[mw], ddof=1)), float(np.std(xB[mw], ddof=1))
        c_ = 0.25 * sb / sc
        a2 = g["A2"]
        assert a2["window"] == ["2018-02-01", "2020-01-31"] and a2["rows"] == int(mw.sum()) and a2["target"] == 0.25 and abs(a2["c"] - c_) <= 1e-9 * c_ and abs(a2["std_book"] - sb) <= 1e-9 * sb and abs(a2["std_cell"] - sc) <= 1e-9 * sc, (c, a2)
        assert a2["at_half_c"]["c"] == 0.5 * a2["c"] and a2["at_double_c"]["c"] == 2.0 * a2["c"] and "pass" not in a2 and a2["book_shadow_line"] is a2["incremental_pass"]
        for got, mult in ((a2, 1.0), (a2["at_half_c"], 0.5), (a2["at_double_c"], 2.0)):
            w_ = DV.plain_stats((ref_raw + mult * c_ * xB)[kw], B.index[kw])
            assert abs(got["roc"] - w_["roc"]) < 1e-5 and abs(got["sortino"] - w_["sortino"]) < 1e-7 and abs(got["net"] - w_["net"]) < 1e-3, (c, mult)
        wp_ = DV.plain_stats((np.asarray(B.raw, float) + c_ * xB)[kw], B.index[kw])
        assert abs(a2["plain_463"]["roc"] - wp_["roc"]) < 1e-5 and abs(a2["plain_463"]["sortino"] - wp_["sortino"]) < 1e-7 and abs(a2["reference"]["roc"] - ref_s["roc"]) < 1e-5 and abs(a2["reference"]["sortino"] - ref_s["sortino"]) < 1e-7
        yf_ = (B.index[kw][-1] - B.index[kw][0]).days / 365.25                                # [N10] A2's dollars a year: net / years of the reference's WF, beside every ROC
        assert a2["years"] == yf_ and all(abs(blk["usd_per_year"] - nt_ / yf_) < 1e-5 for blk, nt_ in ((a2, DV.plain_stats((ref_raw + c_ * xB)[kw], B.index[kw])["net"]), (a2["at_half_c"], DV.plain_stats((ref_raw + 0.5 * c_ * xB)[kw], B.index[kw])["net"]),
                                                                                                         (a2["at_double_c"], DV.plain_stats((ref_raw + 2.0 * c_ * xB)[kw], B.index[kw])["net"]), (a2["reference"], ref_s["net"]), (a2["plain_463"], wp_["net"]))), c
        before = bool(a2["roc"] > a2["reference"]["roc"] and a2["sortino"] > a2["reference"]["sortino"])
        assert a2["incremental_pass_before_the_beta_rule"] is before and a2["beta_rule_ok"] is bool(abs(slope) <= 0.20) and a2["incremental_pass"] is bool(before and abs(slope) <= 0.20), c
        os_ = a2["own_stretch"]
        assert os_["years"] == yo_ and abs(os_["reference_alone"]["usd_per_year"] - DV.plain_stats(ref_raw[k], ds)["net"] / yo_) < 1e-5 and abs(os_["with_c"]["usd_per_year"] - DV.plain_stats((ref_raw + c_ * xB)[k], ds)["net"] / yo_) < 1e-5, c
        assert os_["window"] == ["2018-02-01", "2025-06-29"] and abs(os_["reference_alone"]["roc"] - DV.plain_stats(ref_raw[k], ds)["roc"]) < 1e-5 and abs(os_["with_c"]["roc"] - DV.plain_stats((ref_raw + c_ * xB)[k], ds)["roc"]) < 1e-5, c
        # the reference's drawdown episodes and the #70 gate's basis: the cell's P&L over each episode, its DO over the DD days from 2018-02 on, DO without its best episode, the null's DO
        xr = xB[kw]
        tab = g["ref_episodes"]
        assert len(tab) == len(qual_p) and all(abs(t_["cell_pnl"] - float(xr[i0_:it_ + 1].sum())) < 1e-6 and abs(t_["depth"] - dep_) < 1e-6 and abs(t_["book_pnl"] - float(ref_raw[kw][i0_:it_ + 1].sum())) < 1e-6 for t_, (dep_, i0_, it_, _i1) in zip(tab, qual_p)), c
        check_eis(g["ref_episodes_in_stretch"], xr, c)
        gt = g["gate70"]
        do = float(xr[mask_n].sum()) / -float(ref_raw[kw][mask_n].sum())
        j = int(np.argmax([t_["cell_pnl"] for t_ in tab]))
        rest = [t_ for q_, t_ in enumerate(tab) if q_ != j]
        loss = -sum(t_["book_pnl"] for t_ in rest)
        do_ex = sum(t_["cell_pnl"] for t_ in rest) / loss if loss > 0 else float("nan")
        assert abs(gt["DO"] - do) < 1e-9 and gt["dd_days_from_2018_02"] == int(mask_n.sum()) and gt["episodes"] == len(qual_p) and abs(g["seat_ref"]["DO"] - do) < 1e-9 and g["seat_ref"]["dd_days"] == int(mask_n.sum()), (c, gt["DO"], do)
        assert (math.isnan(do_ex) and math.isnan(gt["DO_ex_best_episode"])) or abs(gt["DO_ex_best_episode"] - do_ex) < 1e-9, c
        assert gt["best_episode"] == f"{tab[j]['first_dd_day']} .. {tab[j]['trough']}" and gt["null_do_p95"] == nul["do_ref_max"]["p95"] and gt["DO_above_null_p95"] is bool(do > pc(mdo, 95)) and gt["credited"] is g["beta_gate"]["credited"]
        assert gt["gate_basis_met"] is bool(gt["credited"] and do > pc(mdo, 95) and gt["DO_ex_best_episode"] > 0), c
        do_b = float(xB[kw][mask_bn].sum()) / -float(np.asarray(B.raw, float)[kw][mask_bn].sum())
        assert abs(g["seat"]["DO"] - do_b) < 1e-9 and g["seat"]["dd_days"] == int(mask_bn.sum()), (c, g["seat"]["DO"], do_b)
        # the path by months since listing, the cohorts (the cell and its short side alone)
        ap = plain_age_path(W, P, lrow, WFN)
        got_ap = rep["cells"][c]["age_path"]
        assert sorted(got_ap) == sorted(ap) and all(got_ap[q_]["days"] == ap[q_]["days"] and abs(got_ap[q_]["short"] - ap[q_]["short"]) < 1e-6 and abs(got_ap[q_]["other"] - ap[q_]["other"]) < 1e-6 for q_ in ap), c
        assert abs(sum(v["short"] + v["other"] for v in ap.values()) - base["net"]) < 1e-6 and min(ap) >= 6 and max(ap) <= 25, (c, min(ap), max(ap))
        sp_got = rep["cells"][c]["age_split"]
        for lab, a_, b_ in AGE_BUCKETS:
            rows_ = [v for q_, v in ap.items() if a_ <= q_ <= b_]
            assert sp_got[lab]["days"] == sum(v["days"] for v in rows_) and abs(sp_got[lab]["short"] - sum(v["short"] for v in rows_)) < 1e-6 and abs(sp_got[lab]["net"] - sum(v["short"] + v["other"] for v in rows_)) < 1e-6, (c, lab)
        assert sp_got["<6 months"]["days"] == 0 and sp_got["6-12 months"]["days"] > 0 and sp_got["12-24 months"]["days"] > 0 and sp_got["6-12 months"]["short"] > 0 and sp_got["12-24 months"]["short"] > 0, "the planted underperformance sits in both age buckets"
        for key, short_only in (("cell", False), ("short_side", True)):
            pcoh = plain_cohort(W, P, lrow, short_only)
            gco = rep["cells"][c]["cohort"][key]
            assert sorted(gco) == sorted(pcoh) and all(gco[y]["name_months"] == pcoh[y]["name_months"] and gco[y]["names"] == len(pcoh[y]["cols"]) and abs(gco[y]["net"] - pcoh[y]["net"]) < 1e-6 and abs(gco[y]["short"] - pcoh[y]["short"]) < 1e-6
                                                       and abs(gco[y]["other"] - pcoh[y]["other"]) < 1e-6 for y in pcoh), (c, key)
        assert abs(sum(v["net"] for v in rep["cells"][c]["cohort"]["cell"].values()) - base["net_pos"]) < 1e-6
        # the 20 largest name-months and the reports' other rows
        top = sorted(P, key=lambda p: -p["pnl"])[:20]
        g20 = rep["cells"][c]["top20_gains"]
        assert [round(x_["pnl"], 6) for x_ in g20] == [round(p["pnl"], 6) for p in top] and g20[0]["symbol"] == str(W.syms[top[0]["col"]]) and g20[0]["fill"] == f"{days[top[0]['rec'].f]:%Y-%m-%d}" and g20[0]["exit"] == f"{days[top[0]['rec'].x]:%Y-%m-%d}", c
        assert g20[0]["listed"] == f"{days[lrow[top[0]['col']]]:%Y-%m-%d}" and g20[0]["age_at_rank"] == top[0]["rec"].r - lrow[top[0]["col"]] and g20[0]["match"] == (str(W.syms[top[0]["mcol"]]) if c == "M" else "")
        assert abs(rep["cells"][c]["corr_with_res"] - float(np.corrcoef(xB[k], ref.res[k])[0, 1])) < 1e-9 and rep["cells"][c]["map_point"] == {"standalone_roc_30k": base["roc"], "rho_dd": g["seat_ref"]["rho_dd"], "DO": g["seat_ref"]["DO"]}
        byx = Counter(int(days[p_.x].year - (1 if days[p_.x].month < 7 else 0)) for p_ in L.recs if traded(p_, c))
        assert rep["cells"][c]["by_exit_year"] == {y: byx.get(y, 0) for y in YEARS}, c
        n[f"{c}_positions"] = len(P)
    # ---- [N7] the REPORTED floor's reading: the same market read under the reported floor - its own leg (the months that reach it), its own null stream (vcode 2) - every cell number recounted on those months by plain python
    fr, tm = out["floor_reported"], out["traded_months"]
    n_by = {q.r: len(sets["remove"][q.r][0]) for q in L.recs}
    keep = [q for q in L.recs if n_by[q.r] >= FLOOR_REPORTED]
    assert fr["floor"] == FLOOR_REPORTED and 0 < len(keep) < len(L.recs) and out["low_power_flag"] == LOW_POWER and all(q.f == q.r + 1 for q in L.recs), (len(keep), len(L.recs))
    fyr = lambda qs: dict(sorted(Counter(int(days[q.r + 1].year) for q in qs).items()))
    boom = lambda qs: sum(1 for q in qs if TS("2018-03-01") <= days[q.r + 1] <= TS("2022-03-31"))
    assert tm["registered"]["floor"] == SPEC["floor"] and tm["reported"]["floor"] == FLOOR_REPORTED and tm["registered"]["traded"] == len(L.recs) and tm["reported"]["traded"] == len(keep)
    assert tm["registered"]["traded_by_fill_year"] == fyr(L.recs) and tm["reported"]["traded_by_fill_year"] == fyr(keep) and tm["registered"]["traded_2018_03_to_2022_03"] == boom(L.recs) and tm["reported"]["traded_2018_03_to_2022_03"] == boom(keep)
    assert traded_text(tm["registered"], tm["reported"]) in cx.txt and LOW_POWER in cx.txt and f"REPORTED {FLOOR_REPORTED}-NAME-FLOOR READING [N7]" in cx.txt and "BOTH FLOORS SIDE BY SIDE [N7]" in cx.txt
    with spec(floor=FLOOR_REPORTED):
        L2 = ni_build(W, ctx, WFN, PRE_END, "remove")
    assert [q.r for q in L2.recs if q.traded] == [q.r for q in keep]
    acc2 = ni_null(W, L2, NREP, 2)
    Y2, roc2, do2 = {}, {}, {}
    for c in CELLS:
        Y2[c] = np.zeros((NREP, B.n))
        Y2[c][:, rowsB] = acc2[c]
        roc2[c] = np.array([DV.plain_stats(Y2[c][d][k], ds)["roc"] for d in range(NREP)])
        do2[c] = Y2[c][:, kw][:, mask_n].sum(axis=1) / -float(ref_raw[kw][mask_n].sum())
    mx2, mdo2 = np.fmax(roc2["E"], roc2["M"]), np.fmax(do2["E"], do2["M"])
    n2 = fr["null"]
    assert n2["draws"] == NREP and n2["seed"] == SEED and n2["roc_max"] != nul["roc_max"] and all(abs(n2["roc_max"][key] - pc(mx2, q_)) < 1e-6 and abs(n2["do_ref_max"][key] - pc(mdo2, q_)) < 1e-9 for q_, key in ((5, "p5"), (50, "p50"), (95, "p95")))
    p95_2, pass2 = pc(mx2, 95), []
    yo_ = (ds[-1] - ds[0]).days / 365.25
    for c in CELLS:
        keep_pos = [p for p in pos[c] if n_by[p["rec"].r] >= FLOOR_REPORTED]
        P2 = brute_positions(W, L2, c)
        assert len(P2) == len(keep_pos) < len(pos[c]) and usd([p["pnl"] for p in P2], [p["pnl"] for p in keep_pos]), c
        xb2, cb2 = brute_series_of(W, P2)
        xB2, cB2 = toB(xb2), toB(cb2)
        w2 = plain_cell_stats(xB2[k], ds, cB2[k], [p["pnl"] for p in P2])
        g2 = fr["cells"][c]
        b2 = g2["base"]
        assert b2["n_pos"] == len(P2) and b2["n_units"] == len({p["ri"] for p in P2}) == len(keep) and b2["years_pos"] == w2["years_pos"] and abs(b2["usd_per_year"] - w2["net"] / yo_) <= 1e-6 * max(1.0, abs(b2["usd_per_year"])), c
        for key in ("net", "roc", "sortino", "max_dd", "net_ex2020", "net_2022", "net_ex2022", "net_2020_21", "net_ex_best_days", "net_pos", "net_ex_best_pos", "top_pos", "net_ex_top_pos"):
            assert abs(b2[key] - w2[key]) <= 1e-6 * max(1.0, abs(w2[key])), (c, key, b2[key], w2[key])
        n10_ = DV.plain_stats(toB(brute_series_of(W, brute_positions(W, L2, c, bps=10.0))[0])[k], ds)["net"]
        nb10_ = DV.plain_stats(toB(brute_series_of(W, brute_positions(W, L2, c, borrow=0.10))[0])[k], ds)["net"]
        assert abs(g2["stress"]["10 bps"]["net"] - n10_) < 1e-6 and abs(g2["borrow"]["10%/yr"]["net"] - nb10_) < 1e-6, c
        want2 = {f"rebalances>={RULES['reb']}": len({p["ri"] for p in P2}) >= 40, "ROC>=15": w2["roc"] >= 15.0, "net>0 at 5 bps": w2["net"] > 0, "net>0 at 10 bps": n10_ > 0, "net>0 at 10%/yr borrow": nb10_ > 0, "ROC>null p95": w2["roc"] > p95_2,
                 "positive in >=5 of 8 July-June years": w2["years_pos"] >= 5, "net>0 without Feb 15 - Apr 30 2020": w2["net_ex2020"] > 0, "net>0 without calendar 2022": w2["net_ex2022"] > 0, "profitable without its best 1% of days": w2["net_ex_best_days"] > 0,
                 "profitable without its best 1% of name-months": w2["net_ex_best_pos"] > 0}
        assert g2["checks"] == want2 and g2["PASS"] is all(want2.values()), (c, g2["checks"], want2)
        if all(want2.values()):
            pass2.append(c)
        check_eis(g2["ref_episodes_in_stretch"], xB2[kw], f"{c} @{FLOOR_REPORTED}")
    assert fr["cells_clearing_a_to_e_information_only"] == pass2 and out["stageA"]["registered_pass_cells"] == [c for c in CELLS if cells[c]["PASS"]], "the reported reading is information only: the registered pass list is the registered reading's"
    n["reported_floor_months"] = len(keep)
    # ---- NEW names per month and the hedge ratios (the survivors of the sets recount, the cohorts from the plan)
    nt = rep["new_table"]
    assert len(nt) == len(L.recs) and all(r_["traded"] and r_["E"] and r_["M"] for r_ in nt)
    for r_, q in zip(nt, L.recs):
        new_s, seas_s = sets["remove"][q.r]
        coh = Counter(int(days[plan.first[nm]].year) for nm in new_s)
        b, kk = brute_beta(W, q.r, q.new.tolist())
        assert r_["rank"] == f"{days[q.r]:%Y-%m-%d}" and r_["new"] == len(new_s) and r_["seasoned_candidates"] == len(seas_s) and r_["by_cohort"] == dict(sorted(coh.items())) and r_["hedge_pairs"] == kk and abs(r_["hedge_ratio"] - b) < 1e-9, r_["rank"]
    hr = [brute_beta(W, q.r, q.new.tolist())[0] for q in L.recs]
    assert rep["hedge_ratio"]["rebalances"] == len(hr) and abs(rep["hedge_ratio"]["mean"] - float(np.mean(hr))) < 1e-9 and abs(rep["hedge_ratio"]["min"] - min(hr)) < 1e-9 and abs(rep["hedge_ratio"]["max"] - max(hr)) < 1e-9 and 0.7 < float(np.mean(hr)) < 1.3, "the NEW basket's beta is ~ the mean of the planted betas (0.5 .. 1.5)"
    # ---- the hygiene counts of the two readings: the registered one removes the planted cases inside a hold, the look-ahead one keeps them at their naive raw path
    hy = out["hygiene_counts_by_year"]
    tot = lambda reading, key: sum(v.get(key, 0) for v in hy[reading].values())
    assert tot("registered", "new_post_split") >= 1 and tot("registered", "new_post_gap") >= 1 and tot("registered", "new_post_jump") >= 1 and tot("registered", "new_pre_jump") >= 1 and tot("registered", "new_kept_naive") == 0, hy["registered"]
    assert tot("look_ahead", "new_kept_naive") >= 3 and sum(tot("look_ahead", f"new_post_{h_}") for h_ in HYG) == 0 and tot("look_ahead", "new_pre_jump") == tot("registered", "new_pre_jump") and tot("look_ahead", "new_old_gap") == tot("registered", "new_old_gap"), hy["look_ahead"]
    assert tot("registered", "new_spinco_any") == tot("look_ahead", "new_spinco_any") > 0 and tot("registered", "new_name_change_any") > 0 and tot("registered", "seas_name_change") > 0 and tot("registered", "n4_failed_names") > 0 and tot("registered", "n4_unverifiable_names") == 0
    la = out["look_ahead_reading"]
    assert la["null"]["draws"] == NREP and set(la["flips"]) == set(CELLS) and all(la["cells"][c]["base"]["net"] != cells[c]["base"]["net"] for c in CELLS), "the naive raw paths of the planted data cases move both cells"
    n["null_draws"] = NREP
    # ---- the second name-change coverage row: the ranks whose 24-month window starts before the calendar's FIRST name-change row
    e0 = min(d for _o, _n, d in plan.chg if TS(d) < S.LB0)
    nce = [q for q in L.recs if days[q.r] - pd.DateOffset(months=SPEC["nc_months"]) < TS(e0)]
    assert out["calendar_tables"]["name_change"]["earliest"] == e0 and out["name_change_window_before_the_first_name_change_row"] == [f"{days[q.r]:%Y-%m-%d}" for q in nce] and len(nce) > len(out["name_change_window_before_the_calendar"]) > 0
    assert f"calendar name-change coverage: the earliest name-change row on the calendar is dated {e0}; the 24-month name-change window of {len(nce)} of the {len(L.recs)} WF ranks starts before it" in cx.txt
    Ld = ni_build(W, ctx, WFN, PRE_END, "remove", drop=pd.DatetimeIndex([days[q.r] for q in nce]))
    v2 = out["variants"]["without the ranks whose name-change window starts before the first name-change row on the calendar"]
    assert v2["rebalances"] == len(Ld.recs) == len(L.recs) - len(nce) > 0
    for c in CELLS:
        Pd = brute_positions(W, Ld, c)
        assert v2[c]["n_pos"] == len(Pd) and abs(v2[c]["net"] - float(toB(brute_series_of(W, Pd)[0])[k].sum())) < 1e-6, c
    n["name_change_ranks"] = len(nce)
    # ---- the file: the numbers survive the JSON round trip, the stamp and the pre-registration are in it
    sa = json.load(open(os.path.join(OUT, "newissue_stageA.json")))
    assert sa["judged"] is True and sa["candidate"]["cell"] == out["candidate"]["cell"] and sa["prereg_sha256_lf"] == PREREG_SHA and {k_: sa.get(k_) for k_ in stamp()} == stamp() and sa["stageA"]["registered_pass_cells"] == out["stageA"]["registered_pass_cells"]
    assert sa["low_power_flag"] == LOW_POWER and sa["floor_reported"]["floor"] == FLOOR_REPORTED and sa["traded_months"]["registered"]["traded"] == len(L.recs) and sa["traded_months"]["reported"]["traded"] == len(keep) and abs(sa["floor_reported"]["cells"]["E"]["base"]["usd_per_year"] - fr["cells"]["E"]["base"]["usd_per_year"]) < 1e-9
    assert all(abs(sa["stageA"]["cells"][c]["base"]["net"] - cells[c]["base"]["net"]) < 1e-9 and sa["stageA"]["cells"][c]["checks"] == cells[c]["checks"] for c in CELLS) and sa["parity"] == json.loads(json.dumps(out["parity"]))
    # ---- the audit candidates: the 50 largest gains per cell, largest first, dated before the cut, the largest equal to the recount's
    cd = pd.read_csv(os.path.join(OUT, "newissue_audit_candidates.csv"))
    need = {"cell", "rank", "symbol", "date", "exit", "rank_date", "match", "pnl", "short_pnl", "other_pnl", "listing_session", "age_sessions_at_rank", "months_since_listing_at_rank", "cohort", "n4_sessions_with_close_and_volume_of_the_next_20", "first_bar_raw_close", "first_bar_volume",
            "calendar_spin_off_rows", "calendar_name_change_rows", "factor_ratio_listing_to_exit", "max_overnight_raw_ratio_first_20_sessions", "max_overnight_raw_ratio_in_hold", "tbis_price_ratio", "tbis_split_like", "asset_status", "flags_in_window"}
    assert need <= set(cd.columns), sorted(need - set(cd.columns))
    assert cd.groupby("cell").size().to_dict() == {c: AUDIT_N for c in CELLS} and cd["exit"].max() < "2025-06-30" and cd["listing_session"].max() < "2025-06-30"
    for c, g_ in cd.groupby("cell"):
        assert (g_["pnl"].diff().dropna() <= 1e-9).all() and abs(g_["pnl"].iloc[0] - max(p["pnl"] for p in pos[c])) < 1e-6, c
        for _i, r_ in g_.head(3).iterrows():
            p = next(p_ for p_ in pos[c] if str(W.syms[p_["col"]]) == r_["symbol"] and f"{days[p_['rec'].f]:%Y-%m-%d}" == r_["date"])
            col = p["col"]
            assert abs(r_["pnl"] - p["pnl"]) < 1e-6 and abs(r_["short_pnl"] - p["short_pnl"]) < 1e-6 and abs(r_["other_pnl"] - p["other_pnl"]) < 1e-6 and r_["listing_session"] == f"{days[lrow[col]]:%Y-%m-%d}" and r_["cohort"] == days[lrow[col]].year, (c, r_["symbol"])
            assert r_["age_sessions_at_rank"] == p["rec"].r - lrow[col] and r_["n4_sessions_with_close_and_volume_of_the_next_20"] == int(ctx.li.n_after[col]) and abs(r_["first_bar_raw_close"] - float(W.Cl[lrow[col], col])) < 1e-9 and (r_["match"] if isinstance(r_["match"], str) else "") == (str(W.syms[p["mcol"]]) if c == "M" else "")
    return n


# ------------------------------------------------------------------ smoke: every command end to end on the synthetic worlds
def smoke(*a):
    """python r20_newissue.py smoke DIR [stage_b]: offline, on SYNTHETIC worlds (nothing real is read or written; DIR is wiped and its name must contain 'smoke'). Order: the selftest on the real constants; the planted world through the real loaders against plain-python recounts of everything this file adds;
    the dryload (counts only); Stage A's refusal paths; Stage A on the NULL world (must FAIL), on the BEAR world (every name drifts down: the family-aware null must catch it) and on the PLANTED world (the new-issue underperformance must be found: (a)-(e) pass, (f) awaits the hand audit, every number recounted);
    the beta rule's gate and the floor end to end (the registered 10-name floor, the 20-name reading beside it); the hand audit (keep / data_event) and the recomputation; Stage B's refusal paths; with the argument stage_b also the one read of Stage B on the synthetic lockbox days, the verdict = the leg's veto alone, a second read refused, Stage A frozen"""
    root = os.path.abspath(a[0] if a else os.path.join(tempfile.gettempdir(), "newissue_smoke"))
    with_b = "stage_b" in a[1:]
    why = smoke_refusal(root)
    if why:
        raise SystemExit(why)
    selftest()                                                                             # the hand-made checks first, on the real constants (before anything below is patched)
    t_start = time.time()
    dates_of = lambda txt: re.findall(r"\b20\d\d-\d\d-\d\d\b", txt)
    with smoke_env(root) as env:
        sa_path, go, rd, ap = (os.path.join(OUT, n_) for n_ in ("newissue_stageA.json", GO_FLAG, READ_FLAG, "newissue_audit.csv"))
        plan = env.plan
        print(f"synthetic market: {len(env.fk['plant'].names)} names x {len(env.days):,} business days ({env.days[0]:%Y-%m-%d} .. {env.days[-1]:%Y-%m-%d}), one NEW name listed a month from 2016-02, the planted cases (a stray bar, a 17-of-20 and an 18-of-20 listing, two spincos, two name changes, a registered split, a missed x4, a +60% "
              f"gap, a delisting, three names below the universe's floors); the PLANTED world: NEW names drift {SMOKE_DRIFT:+.2%} a day over the sessions {SMOKE_AGE[0]} .. {SMOKE_AGE[1]} after their listing; the NULL world has no drift; the BEAR world: EVERY name drifts {SMOKE_BEAR:+.2%} a day; all through "
              f"r5_siporb's own pulls ({env.build_seconds:.0f}s); the wide calendar: {len(env.ca_rows):,} rows, sha256 {env.wide_sha[:16]}...; the registered floor stays the real {SPEC['floor']} NEW names (16 .. 20 survive every month, so every month trades) and the REPORTED floor is shrunk from 20 to "
              f"{FLOOR_REPORTED} for the smoke (the real constants are asserted by the selftest)")
        # ---- 1. the planted world through the REAL loaders: the cut at read, then everything this file adds against plain-python recounts
        W, cal, extra, winfo, einfo, tbis = smoke_world(env, "plant")
        n_cut = sum(1 for r_ in env.ca_rows if ((r_.split(",")[4] or r_.split(",")[5]) >= "2025-06-30"))
        assert winfo["rows_on_file"] == len(env.ca_rows) and winfo["rows_dropped_at_the_cut"] == einfo["rows_dropped_at_the_cut"] == n_cut > 50 and winfo["pinned"]["matches"] is True and winfo["csv_sha256"] == env.wide_sha, (winfo, einfo, n_cut)
        assert W.days.max() < S.LB0 and W.days[0] == FIRST_SESSION and len(W.days) == len(pd.bdate_range("2016-01-04", "2025-06-27")) and cal.div["ex"].max() < S.LB0 and cal.spin["ex"].max() < S.LB0, "nothing on / after the cut"
        assert extra.spin["ev"].max() < S.LB0 and extra.chg["ev"].max() < S.LB0 and len(extra.spin) == 2 and len(extra.chg) == 4, "the spin-off / name-change tables are cut at read"
        assert len(tbis) == 4 and tbis["day"].max() < S.LB0 and len(D15.load_tbis(S.END)) == 5, "TBIS's row on the lockbox day is cut at read time"
        ctx = make_ctx(W, extra)
        L, cnt, sets = smoke_recount(env, W, ctx)
        lw = listing_counts(W.days, ctx.li)
        print(f"planted cases ok through the real loaders (the cut at read: {n_cut} calendar rows dated on / after it dropped, the spin-off / name-change tables cut too): {cnt['names']} names' listing sessions and [N4] statuses against the plan "
              f"(NX01 stray bar and NX02 17-of-20 fail, NX03 18-of-20 is accepted); the two calendar tables on the grid; the NEW / SEASONED sets of all {cnt['rebalances']} WF ranks in both readings ({cnt['sets']} sets, the spinco / name-change / hygiene "
              f"cases read off them); the ex-ante beta, the ES leg and the match of every rebalance; {cnt['cell_runs']} cell series (costs, borrow, each side) and 4 null draws against plain-python recounts ({cnt['seconds']}s)")
        B, legs = A13.load_463()
        rowsB = A13.book_rows(B, W)
        bk, dd, S12 = book_checks(B)
        ref = DV.ref_load(B, check_facts=False)
        SN, SRN = restrict_stretch(S12, B.raw, B.index, WFN, PRE_END), restrict_stretch(ref.S, ref.raw, B.index, WFN, PRE_END)
        # ---- 2. the dryload: COUNTS only
        before = sorted(os.listdir(OUT))
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            dres = dryload()
        td = buf.getvalue()
        assert sorted(os.listdir(OUT)) == before, "the dryload writes nothing"
        dryload_text_checks(td)
        n_new, n_seas = [len(sets["remove"][q.r][0]) for q in L.recs], [len(sets["remove"][q.r][1]) for q in L.recs]
        assert f"NEW names per month (survivors of every removal; min / median / max over the {len(L.recs)} rebalances): {min(n_new)} / {np.median(n_new):.0f} / {max(n_new)}; SEASONED candidates per month {min(n_seas)} / {np.median(n_seas):.0f} / {max(n_seas)}" in td
        assert f"rebalances: {len(L.recs)} in WF" in td and f"{len(L.recs)} with >= {SPEC['floor']} NEW names [N7]" in td and f"first traded rank {W.days[L.recs[0].r]:%Y-%m-%d}, last traded rank {W.days[L.recs[-1].r]:%Y-%m-%d}" in td and f"months under the {SPEC['floor']}-name floor (0): none" in td
        coh, cnames = Counter(), defaultdict(set)
        for q in L.recs:
            for nm in sets["remove"][q.r][0]:
                coh[int(W.days[plan.first[nm]].year)] += 1
                cnames[int(W.days[plan.first[nm]].year)].add(nm)
        assert all(f"{y}: {n_:,} ({len(cnames[y])} names)" in td for y, n_ in coh.items()) and dres["leg"]["cohort_name_months"] == dict(sorted(coh.items())), "NEW name-months by listing cohort: the sets recount, cohorts from the plan"
        row_u = next(l for l in td.splitlines() if l.strip().startswith("the names ever in the universe:"))
        row_c = next(l for l in td.splitlines() if l.strip().startswith("every cached name:"))
        assert f"present at the first session {lw['present_at_first_session']}," in row_u and all(f"{y}: {v['dated']:,} / {v['accepted']:,} / {v['failed']:,} / {v['unverifiable']:,}" in row_u for y, v in lw["by_year"].items())
        T_ = W.T
        cached = [nm for nm in plan.names if plan.first[nm] <= T_ - 1 and nm not in ("LOWP", "LOWV")]                       # the price / volume floor drops the two names it is built for; LOWA has bars and never reaches the universe
        cy = Counter(int(W.days[plan.first[nm]].year) for nm in cached if plan.first[nm] > 0)
        cl = Counter(int(W.days[plan.first[nm]].year) for nm in cached if plan.first[nm] > 0 and plan.first[nm] + SPEC["n4_next"] > T_ - 1)
        cf = Counter({2021: 1, 2022: 1})
        assert f"present at the first session {sum(1 for nm in cached if plan.first[nm] == 0)}," in row_c and all(f"{y}: {n_:,} / {n_ - cf[y] - cl[y]:,} / {cf[y]:,} / {cl[y]:,}" in row_c for y, n_ in cy.items()) and sum(cl.values()) == 1, (row_c, cy, cl)
        xd = os.path.dirname(env.wide_csv)
        absent = {"dir": xd, "csv": os.path.join(xd, "absent.csv"), "manifest": os.path.join(xd, "absent.json")}
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), patched(M17, wide_paths=lambda: absent):
            dryload()
        assert "calendar tables this family reads" not in buf.getvalue()
        dryload_text_checks(buf.getvalue(), cal=False)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), patched(M17, WIDE_CA_SHA=None):
            dryload()
        assert "NOT registered yet" in buf.getvalue() and "calendar tables this family reads" in buf.getvalue()
        dryload_text_checks(buf.getvalue())
        n18 = sum(1 for v in n_new if v >= FLOOR_REPORTED)
        assert (f"Stage A's bar (a) [N8] needs >= {RULES['reb']} traded rebalances: {len(L.recs)} of the {len(L.recs)} months clear the REGISTERED {SPEC['floor']}-name floor on the NEW survivors ({sum(1 for q in L.recs if q.newage >= SPEC['floor'])} would on the age-window count before the removals) -> the bar is reachable; "
                f"the reported {FLOOR_REPORTED}-name floor: {n18} months clear it ({'the bar would be reachable there too' if n18 >= RULES['reb'] else 'the bar would be unreachable there'}; information only)") in td
        fyr_ = lambda qs: dict(sorted(Counter(int(W.days[q.r + 1].year) for q in qs).items()))
        assert dres["leg"]["traded"] == len(L.recs) and dres["leg_reported_floor"]["traded"] == n18 and 0 < n18 < len(L.recs) and dres["leg"]["floor"] == SPEC["floor"] and dres["leg_reported_floor"]["floor"] == FLOOR_REPORTED
        assert dres["leg"]["traded_by_fill_year"] == fyr_(L.recs) == dres["leg"]["rebalances_by_fill_year"] and dres["leg_reported_floor"]["traded_by_fill_year"] == fyr_([q for q, v in zip(L.recs, n_new) if v >= FLOOR_REPORTED]), "the traded months by fill year under both floors"
        assert traded_text(dres["leg"], dres["leg_reported_floor"]) in td and f"months under the {FLOOR_REPORTED}-name floor ({len(L.recs) - n18}): " in td and f"under the registered {SPEC['floor']}-name floor / under the reported {FLOOR_REPORTED}-name floor)" in td and LOW_POWER in td
        assert dres["leg"]["traded_2018_03_to_2022_03"] == sum(1 for q in L.recs if TS("2018-03-01") <= W.days[q.r + 1] <= TS("2022-03-31")) and f"in 2018-03 .. 2022-03: {dres['leg']['traded_2018_03_to_2022_03']} of the {len(L.recs)} (registered)" in td
        e0 = min(d for _o, _n, d in plan.chg if TS(d) < S.LB0)
        assert f"calendar name-change coverage: the earliest name-change row on the calendar is dated {e0}; the 24-month name-change window of {sum(1 for q in L.recs if W.days[q.r] - pd.DateOffset(months=SPEC['nc_months']) < TS(e0))} of the {len(L.recs)} WF ranks starts before it" in td
        with spec(floor=20), patched(THIS, FLOOR_REPORTED=25):                              # the bar's feasibility line says so when too few months trade (the registered floor squeezed to 20, the reported one to 25)
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                dres20 = dryload()
            assert "the bar is UNREACHABLE" in buf.getvalue() and dres20["leg"]["traded"] == sum(1 for v in n_new if v >= 20) < RULES["reb"] and f"{dres20['leg']['traded']} of the {len(L.recs)} months clear the REGISTERED 20-name floor" in buf.getvalue()
            assert dres20["leg_reported_floor"]["traded"] == 0 and "the reported 25-name floor: 0 months clear it (the bar would be unreachable there; information only)" in buf.getvalue()
            dryload_text_checks(buf.getvalue())
        with patched(THIS, PREREG_SHA="0" * 64):
            refused(dryload, "DIFFERS", "lockbox NOT read")
        print(f"dryload ok on the synthetic world: counts only (no price, return, beta, P&L or statistic), no lockbox date, nothing written; its NEW / SEASONED counts per month ({min(n_new)} / {np.median(n_new):.0f} / {max(n_new)}), listing counts by year (the universe's and every cached name's, "
              f"the late listing counted as unverifiable), cohort name-months and traded ranks equal the recount; absent / unregistered calendar and a changed prereg handled")
        # ---- 3. Stage A's refusal paths: nothing computed, nothing written
        env.switch("plant")

        def must(frag, fn=stage_a, **kw):
            with quiet(), patched(THIS, **kw):
                msg = refused(fn, frag)
            assert not os.path.exists(sa_path) and not os.path.exists(rd), "a refusal writes no stage file and burns nothing"
            return msg
        must("DIFFERS", PREREG_SHA="0" * 64)
        with patched(M17, WIDE_CA_SHA="0" * 64):
            must("is not the registered wide calendar")
        with patched(M17, WIDE_CA_SHA=None):
            must("the wide calendar sha is not registered yet")
        with patched(M17, wide_paths=lambda: absent):
            must("wide corporate-actions calendar is not on file")
        man0 = open(env.wide_manifest, "rb").read()
        os.remove(env.wide_manifest)
        must("manifest is missing")
        open(env.wide_manifest, "wb").write(man0)
        must("do not reproduce", CHECK_BOOK=True)                                          # a book that does not reproduce #463 (the synthetic one cannot) refuses before any data loads
        with patched(DV, REF_SHA="0" * 64):
            must("is not the registered")                                                  # [X1] the line file is not the registered one: refused before any data loads
        with patched(DV, REF_CSV=os.path.join(root, "resmom", "absent.csv")):
            must("is not on file")
        real_bc, real_rl = D15.book_checks, DV.ref_load

        def book_ok(B_):                                                                   # the #463 checks stubbed to pass, so that the REFERENCE's own registered numbers are the ones refused (the synthetic reference cannot reproduce them)
            bk_, dd_, S_ = real_bc(B_)
            return {**bk_, "ok": True}, {**dd_, "ok": True}, S_
        must("does not reproduce its registered WF numbers", CHECK_BOOK=True, book_checks=book_ok)
        with patched(DV, ref_load=lambda B_, path=None, check_facts=None: real_rl(B_, path, False)):
            must("not the registered photograph", CHECK_BOOK=True, book_checks=book_ok, manifest_sha=lambda: "ffffffff" + "0" * 56)
            must("not the registered 2016-01-05", CHECK_BOOK=True, book_checks=book_ok, FIRST_SESSION=TS("2016-01-05"))
        with open(ap, "w") as f:
            f.write("symbol,date,cell,verdict,note\nN001,2018-03-01,E,maybe,x\n")
        must("newissue_audit.csv line(s)")
        with open(ap, "w") as f:
            f.write("symbol,date,cell,verdict,note\nZZZ,2018-03-01,E,data_event,x\n")
        must("match no session or no name")
        os.remove(ap)
        with open(rd, "w") as f:
            f.write("x")
        with quiet():
            refused(stage_a, "Stage A is frozen", READ_FLAG)
        os.remove(rd)
        print("Stage A refuses (and writes nothing) on: a changed pre-registration, an unregistered / other / absent wide calendar, a missing manifest, a book that does not reproduce #463, a RESMOM line file that is absent / not the registered one / whose reference does not reproduce its registered WF numbers, "
              "a wrong SIPORB manifest, a first session that is not the registered one, an audit file it cannot read or a data_event that matches nothing, and once the lockbox has been read")

        verdict_of = lambda t: next(l for l in t.splitlines() if l.startswith("NEWISSUE Stage A:"))

        def run_stage_a(world):
            env.switch(world)
            b_ = io.StringIO()
            with contextlib.redirect_stdout(b_):
                o_ = stage_a()
            return o_, b_.getvalue()
        # ---- 4. Stage A on the NULL world: the same market without any new-issue effect must FAIL
        t0 = time.time()
        out_n, txt_n = run_stage_a("null")
        cn = out_n["stageA"]["cells"]
        assert out_n["judged"] is True and out_n["stageA"]["registered_pass_cells"] == [] and out_n["candidate"] is None and out_n["pending_hand_audit"] == [] and out_n["stageA"]["null"]["draws"] == NREP == 100
        assert "NEWISSUE Stage A: FAIL - no cell passes (a)-(e)" in txt_n and "Stage A (a)-(e) pass" not in txt_n and all(d < "2025-06-30" for d in dates_of(txt_n)), "the null world fails and prints no lockbox date"
        assert all(cn[c]["base"]["net"] < 0 and cn[c]["base"]["roc"] < RULES["roc"] and not cn[c]["PASS"] and not cn[c]["A2"]["incremental_pass"] and cn[c]["beta_gate"]["credited"] for c in CELLS), "a world without the effect pays its costs and adds nothing to the reference"
        assert out_n["reference"]["sha256"] == env.ref_sha and "REFERENCE book [X1]" in txt_n and "DIAGNOSTICS [X2]" in txt_n and "no incremental pass" in txt_n and "INCREMENTAL PASS" not in txt_n
        assert out_n["low_power_flag"] == LOW_POWER and LOW_POWER in verdict_of(txt_n) and "BOTH FLOORS SIDE BY SIDE [N7]" in txt_n and out_n["floor_reported"]["floor"] == FLOOR_REPORTED and out_n["floor_reported"]["cells_clearing_a_to_e_information_only"] == []
        os.remove(sa_path)
        with quiet():
            refused(stage_b, "go-flag")
        assert not os.path.exists(rd)
        print(f"Stage A on the NULL world ({time.time() - t0:.0f}s): FAIL as it must - WF ROC@30k " + ", ".join(f"{c} {cn[c]['base']['roc']:.1f}" for c in CELLS) + f" (net ${cn['E']['base']['net']:,.0f} / ${cn['M']['base']['net']:,.0f}: the costs and the borrow), null p95 {out_n['stageA']['null']['roc_max']['p95']:.1f}; Stage B refuses without the lead's go-flag")
        # ---- 5. Stage A on the BEAR world: every name falls, so shorting ANY name against ES earns - the family-aware null (random SEASONED names, same hedge) must catch it: (c) alone fails
        t0 = time.time()
        out_b, txt_b = run_stage_a("bear")
        cb, nb_ = out_b["stageA"]["cells"], out_b["stageA"]["null"]
        fails_e = [k_ for k_, v in cb["E"]["checks"].items() if not v]
        assert out_b["stageA"]["registered_pass_cells"] == [] and out_b["candidate"] is None and fails_e == ["ROC>null p95"] and RULES["roc"] < cb["E"]["base"]["roc"] <= nb_["roc_max"]["p95"], (fails_e, cb["E"]["base"]["roc"], nb_["roc_max"])
        assert "Stage A (a)-(e) FAIL (ROC>null p95)" in txt_b and "NEWISSUE Stage A: FAIL - no cell passes (a)-(e)" in txt_b and not cb["M"]["PASS"], "E earns, the null earns as much: the cell is not new-issue underperformance"
        os.remove(sa_path)
        print(f"Stage A on the BEAR world ({time.time() - t0:.0f}s): E earns WF ROC@30k {cb['E']['base']['roc']:.1f} (every bar but one clears) but the null - the same hedged short book in random SEASONED names - has p50 {nb_['by_cell']['E']['p50']:.1f} / p95 {nb_['roc_max']['p95']:.1f}: FAIL on (c) alone; "
              f"M (long a matched seasoned name that falls too) ROC {cb['M']['base']['roc']:.1f}")
        # ---- 6. Stage A on the PLANTED world: (a)-(e) pass, (f) awaits the hand audit; every number recounted
        t0 = time.time()
        out, txt = run_stage_a("plant")
        cells = out["stageA"]["cells"]
        passing, cand = stage_a_flow(cells)
        assert out["judged"] is True and out["stageA"]["registered_pass_cells"] == passing == list(CELLS) and cand == "E" and out["candidate"]["cell"] == "E" and out["pending_hand_audit"] == passing and out["candidate"]["also_passes"] == ["M"], (passing, cand)
        for c in CELLS:
            assert f"Stage A (a)-(e) pass, (f) awaits the hand audit - cell {c}" in txt, c
        assert "(f) AWAITS THE HAND AUDIT" in txt and "audit complete" not in txt.lower() and "(f) pass" not in txt.lower() and "the PRIMARY cell E" in txt and all(d < "2025-06-30" for d in dates_of(txt)), "the harness never decides (f); no lockbox date"
        assert LOW_POWER in verdict_of(txt) and out["low_power_flag"] == LOW_POWER and "THE REFERENCE LINE'S DRAWDOWN EPISODES [N10]" in txt and " a year) ROC@30k" in txt and "dollars a year = net / years" in txt and "the cell HELPS in" in txt, "[N9] the flag is in the verdict line; [N10] dollars a year and the episode table"
        assert out["prereg_sha256_lf"] == PREREG_SHA and {k_: out.get(k_) for k_ in stamp()} == stamp() and out["manifest_sha256"] == D15.MANIFEST_PREFIX + "0" * 56 and out["listing"] == lw and out["name_change_window_before_the_calendar"] == [f"{W.days[q.r]:%Y-%m-%d}" for q in L.recs if W.days[q.r] - pd.DateOffset(months=SPEC["nc_months"]) < TS("2016-06-01")] != []
        assert txt.index("REFERENCE book [X1]") < txt.index("registered reading done") < txt.index("DIAGNOSTICS [X2]") and txt.index("null (100 draws, seed 20261005") < txt.index("Stage A (a)-(e) PASS") < txt.index("look-ahead reading (positions with a flag"), "the reference first, the diagnostics after the cells"
        cx = SimpleNamespace(env=env, W=W, ctx=ctx, L=L, sets=sets, B=B, rowsB=rowsB, ref=ref, S12=S12, out=out, txt=txt, plan=plan, tbis=tbis)
        rc = smoke_stage_recount(cx)
        pm = peak_mb()
        print(f"Stage A on the PLANTED world ({time.time() - t0:.0f}s): the new-issue underperformance is found - WF ROC@30k " + ", ".join(f"{c} {cells[c]['base']['roc']:.0f} ({cells[c]['base']['n_pos']:,} name-months, Sortino {cells[c]['base']['sortino']:.1f})" for c in CELLS)
              + f" against the null's p95 {out['stageA']['null']['roc_max']['p95']:.1f}; (a)-(e) pass for {passing}, candidate {cand}, (f) awaits the hand audit" + (f"; peak memory {pm:,.0f} MB" if pm else ""))
        print(f"  recounted by plain python from the book file, the stub's RES column and the sets above: every cell's WF numbers and position table ({rc['E_positions']:,} + {rc['M_positions']:,} name-months), the 5 stress / cost / borrow rows, the sides, the halves, the July-June years, the realised beta, "
              f"the {rc['null_draws']} null draws and their percentiles, all eleven (a)-(e) checks re-judged, A2 with its 0.5c / 2c rows and the beta rule, the reference and its {out['reference']['structure']['episodes']} drawdown episodes, the #70 gate's DO and its null, the path by months since listing, the cohorts, "
              f"the 20 largest name-months, NEW names per month, the hedge ratios, both hygiene readings, the JSON file and the audit candidates")
        # ---- 7. the beta rule end to end: a cell outside the limit is REPORTED, never credited - A2 cannot pass, no line, no gate
        keep_rule = RULES["beta_abs"]
        RULES["beta_abs"] = 1e-6
        try:
            res_g, _o = evaluate(W, ctx, B, SN, ref, SRN, rowsB, "remove", 0, 0, full=False)
        finally:
            RULES["beta_abs"] = keep_rule
        for c in CELLS:
            g = res_g["cells"][c]
            assert g["beta_gate"]["credited"] is False and g["A2"]["incremental_pass_before_the_beta_rule"] is True and g["A2"]["incremental_pass"] is False and g["A2"]["book_shadow_line"] is False and g["gate70"]["credited"] is False, c
            assert "NEVER CREDITED" in beta_text(g) and "the beta rule is not met" in a2_text(g["A2"]) and "no incremental pass" in a2_text(g["A2"]), c
        assert all(res_g["cells"][c]["beta_gate"]["limit"] == 1e-6 for c in CELLS) and RULES["beta_abs"] == 0.20
        print(f"[N2] beta rule end to end (the limit squeezed to 1e-6 for one reading): the planted cells' realised betas ({cells['E']['realised_beta']['beta']:+.3f} / {cells['M']['realised_beta']['beta']:+.3f}) are outside it -> the drawdown-day profile is reported, never credited, A2's incremental pass "
              f"(true before the rule) becomes false, no book shadow line, no gate")
        # ---- 8. the floor end to end (the registered floor set to 20 / 25 for one reading each): some months trade, none do - every table and printer takes it, the second-floor columns too
        n_by = {q.r: len(sets["remove"][q.r][0]) for q in L.recs}
        for fl in (20, 25):
            with spec(floor=fl), np.errstate(all="ignore"):                                   # (a world in which nothing trades divides by nothing in r11_risk's regressions: NaN, quietly)
                Lf = ni_build(W, ctx, WFN, PRE_END, "remove")
                want_tr = [q.r for q in L.recs if n_by[q.r] >= fl]
                assert [q.r for q in Lf.recs if q.traded] == want_tr and len(Lf.recs) == len(L.recs) and all((not q.traded) == (n_by[q.r] < fl) for q in Lf.recs), fl
                res_f, obj_f = evaluate(W, ctx, B, SN, ref, SRN, rowsB, "remove", 4, 0, full=True)
                rep_f, cand_f = reports(W, ctx, B, S12, ref, rowsB, obj_f, res_f["cells"], tbis, D15.asset_status(), legs)
                var_f = variant_rows(W, ctx, B, rowsB)
                txt_f = (capture(print_cells, res_f) + capture(print_reports, rep_f, res_f["cells"]) + capture(print_diagnostics, res_f, rep_f, ref, var_f) + capture(print_floors, res_f, res_f) + capture(print_diagnostics, res_f, rep_f, ref, var_f, res_f)
                         + capture(print_cells, res_f, None, " @18", True))
                for c in CELLS:
                    bs = res_f["cells"][c]["base"]
                    assert bs["n_units"] == len(want_tr) and bs["n_pos"] == sum(n_by[r_] for r_ in want_tr) and res_f["cells"][c]["checks"]["rebalances>=40"] is False and res_f["cells"][c]["PASS"] is False, (fl, c)
                    assert (bs["n_pos"] == 0) == (fl == 25) and len(cand_f[c]) == (0 if fl == 25 else min(AUDIT_N, bs["n_pos"])), (fl, c)
                assert sum(not r_["traded"] for r_ in rep_f["new_table"]) == len(L.recs) - len(want_tr) and "Stage A (a)-(e) FAIL" in txt_f and "DIAGNOSTICS [X2]" in txt_f and "BOTH FLOORS SIDE BY SIDE [N7]" in txt_f and "cell E @18" in txt_f
            print(f"floor end to end (the registered floor set to {fl} for one reading): {len(want_tr)} of {len(L.recs)} months trade, the cells, null, reports, candidates and every printer take it" + (" - nothing trades: no position, no statistic, no crash" if fl == 25 else ""))
        # ---- 9. the hand audit: every listed contributor 'keep' -> the same numbers, the audit counted; then a data_event on the candidate's largest gain -> out of both cells, the null and the pools, Stage A computed again
        cd = pd.read_csv(os.path.join(OUT, "newissue_audit_candidates.csv"))
        pd.DataFrame({"symbol": cd["symbol"], "date": cd["date"], "cell": cd["cell"], "verdict": "keep", "note": "smoke: nothing found"}).to_csv(ap, index=False)
        out2, txt2 = run_stage_a("plant")
        assert out2["audit"] == {"rows": len(cd), "keep": len(cd), "data_event": 0} and out2["audit_sha256"] == file_sha(ap) != out["audit_sha256"] and all(v["audited"] == v["listed"] == AUDIT_N and v["audit_complete"] for v in out2["audit_status"].values())
        assert out2["stageA"]["registered_pass_cells"] == passing and out2["candidate"] == out["candidate"], "a keep changes nothing"
        assert all(out2["stageA"]["cells"][c]["base"][k_] == cells[c]["base"][k_] for c in CELLS for k_ in ("n_pos", "net", "roc", "max_dd", "sortino")), "a keep changes no number"
        top = cd[cd["cell"] == cand].iloc[0]
        au = pd.read_csv(ap)
        au.loc[(au["symbol"] == top["symbol"]) & (au["date"] == top["date"]), "verdict"] = "data_event"
        au.to_csv(ap, index=False)
        out3, txt3 = run_stage_a("plant")
        cd3 = pd.read_csv(os.path.join(OUT, "newissue_audit_candidates.csv"))
        assert out3["audit"]["data_event"] >= 1 and not ((cd3["symbol"] == top["symbol"]) & (cd3["date"] == top["date"])).any() and out3["audit_sha256"] != out2["audit_sha256"], "the name-month is gone from every list"
        assert out3["audit_data_events_without_effect"] == [] and sum(v.get("new_audit", 0) for v in out3["hygiene_counts_by_year"]["registered"].values()) == 1 and out3["stageA"]["null"]["draws"] == NREP
        for c in CELLS:
            assert out3["stageA"]["cells"][c]["base"]["n_pos"] == cells[c]["base"]["n_pos"] - 1 == out3["parity"][c]["n_pos"] and out3["stageA"]["cells"][c]["base"]["n_units"] == cells[c]["base"]["n_units"], c
        q_top = next(q for q in L.recs if f"{W.days[q.f]:%Y-%m-%d}" == top["date"])
        i3 = next(i for i, r_ in enumerate(out["reports"]["new_table"]) if r_["rank"] == f"{W.days[q_top.r]:%Y-%m-%d}")
        nt0, nt3 = out["reports"]["new_table"][i3], out3["reports"]["new_table"][i3]
        assert nt3["new"] == nt0["new"] - 1 and nt3["seasoned_candidates"] == nt0["seasoned_candidates"]
        print(f"hand audit: all {len(cd)} listed rows 'keep' -> the same numbers, the audit counted {AUDIT_N}/{AUDIT_N} on both lists; a data_event on {top['symbol']} filled {top['date']} ({cand}'s largest gain, ${top['pnl']:,.0f}) -> out of both cells and the null's pools: "
              f"{cand} {cells[cand]['base']['n_pos']:,} -> {out3['stageA']['cells'][cand]['base']['n_pos']:,} name-months, net ${cells[cand]['base']['net']:,.0f} -> ${out3['stageA']['cells'][cand]['base']['net']:,.0f}, NEW names that month {nt0['new']} -> {nt3['new']}")
        out, cells = out3, out3["stageA"]["cells"]
        cand, c_frozen = out["candidate"]["cell"], out["candidate"]["c"]
        # ---- 10. Stage B's refusal paths: the lead's go-flag first, then a stale stamp, a changed spec, a changed audit file, a broken size, drifted inputs; none may write the read flag
        print("--- Stage B refusal paths: no go-flag / not judged / no candidate / a stale stamp / a changed spec / a changed audit file / a broken size / a drifted calendar, manifest, book, WF numbers or size c; none may write the flag")
        env.switch("plant")

        def must_b(frag, **kw):
            with quiet(), patched(THIS, **kw):
                msg = refused(stage_b, frag)
            assert not os.path.exists(rd), "a refused Stage B must not burn the lockbox"
            return msg
        must_b("go-flag")
        with open(go, "w") as f:
            f.write("smoke: the lead's go-flag (hand audit done, the stock families' sealed-year day)")
        js0 = open(sa_path).read()
        for k_ in ("harness_sha256", "r18_sha256", "r17_sha256", "r15_sha256", "r13_sha256", "siporb_sha256", "r11_sha256", "r12_sha256", "wide_ca_sha256"):
            j = json.loads(js0)
            j[k_] = "0" * 64
            open(sa_path, "w").write(json.dumps(j))
            assert k_ in must_b("different harness version"), k_
        j = json.loads(js0)
        j["early_close"] = j["early_close"][1:]
        open(sa_path, "w").write(json.dumps(j))
        must_b("different harness version")
        j = json.loads(js0)
        j["prereg_sha256_lf"] = "0" * 64
        open(sa_path, "w").write(json.dumps(j))
        must_b("another pre-registration")
        for edit in (lambda j: j.update(judged=False), lambda j: j.update(candidate=None), lambda j: j["stageA"].update(registered_pass_cells=[]), lambda j: j["stageA"].update(registered_pass_cells=[c for c in CELLS if c != j["candidate"]["cell"]])):
            j = json.loads(js0)
            edit(j)
            open(sa_path, "w").write(json.dumps(j))
            must_b("no Stage A candidate")
        for badc in (0.0, -1.0, float("nan"), None):
            j = json.loads(js0)
            j["candidate"]["c"] = badc
            open(sa_path, "w").write(json.dumps(j))
            must_b("a positive number")
        j = json.loads(js0)
        j["candidate"]["cell"] = "ZZZ"
        j["stageA"]["registered_pass_cells"] = ["ZZZ"]
        open(sa_path, "w").write(json.dumps(j))
        must_b("a positive number")
        open(sa_path, "w").write(js0)
        must_b("DIFFERS", PREREG_SHA="0" * 64)
        with patched(M17, WIDE_CA_SHA="0" * 64):
            must_b("different harness version")                                           # the pinned calendar is in Stage A's stamp: another pinned sha stops it at the stamp
        au0 = open(ap).read()
        open(ap, "a").write("ZZZ,2018-03-01,E,keep,a changed audit file\n")
        must_b("not the file Stage A ran with")
        open(ap, "w").write(au0)
        must_b("do not reproduce its LB numbers", CHECK_BOOK=True)                         # the book's LB numbers (the synthetic one cannot reproduce them)
        okbk = lambda B_, lo_, hi_, ref_: {"roc": 0.0, "sortino": 0.0, "ref": list(ref_), "ok": True}
        with patched(A13, book_check=okbk):
            must_b("not the one Stage A ran on", CHECK_BOOK=True, manifest_sha=lambda: "ffffffff" + "0" * 56)                    # a drifted cache manifest (the LB book check stubbed to pass so that the manifest one is reached)
        csv0 = open(env.wide_csv, "rb").read()
        with open(env.wide_csv, "ab") as f_:
            f_.write(b"cash_dividend,S01,,,2024-02-09,2024-02-09,,,0.01,,,,False\n")
        must_b("is not the registered wide calendar")                                      # the file changed after it was registered: refused before the flag
        open(env.wide_csv, "wb").write(csv0)
        assert M17.sha_raw(env.wide_csv) == env.wide_sha
        j = json.loads(js0)
        j["parity"][cand]["net"] += 1e6
        open(sa_path, "w").write(json.dumps(j))
        must_b("do not reproduce on Stage B's data")                                       # the WF numbers drifted since Stage A
        j = json.loads(js0)
        j["parity"][cand]["n_pos"] += 1
        open(sa_path, "w").write(json.dumps(j))
        must_b("do not reproduce on Stage B's data")
        j = json.loads(js0)
        j["candidate"]["c"] *= 1.0001
        open(sa_path, "w").write(json.dumps(j))
        must_b("volatility-set size c")                                                    # the frozen size is recomputed from 2018-02-01 .. 2020-01-31 on Stage B's data: a drift of 1 in 10,000 stops it
        open(sa_path, "w").write(js0)
        print("Stage B refused before the flag in every case above (the flag was never written)")
        if not with_b:
            os.remove(go)
        else:
            # ---- 11. Stage B, the one read (synthetic lockbox days only): the flag after the load and the checks, the verdict is the LEG's veto alone, a second read refused, Stage A frozen
            print("--- Stage B, the one read on the synthetic lockbox days: the flag after the load and the checks, the verdict, a second read refused")
            cap, real_cs = {}, D15.cell_stats

            def tap(Bk, xk, ck, lo_, hi_, run_, *a_, **k_):                                # sees the lockbox calls of the one read: keeps the cell's daily series (the registered floor's first, then the reported floor's), to recompute the book adds independently
                st_ = real_cs(Bk, xk, ck, lo_, hi_, run_, *a_, **k_)
                if lo_ == LB0:
                    cap["x20" if "x" in cap else "x"] = np.array(xk)
                return st_
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf), patched(D15, cell_stats=tap):
                ok = stage_b()
            txt_b2 = buf.getvalue()
            print(txt_b2.rstrip())
            sb = json.load(open(os.path.join(OUT, "newissue_stageB.json")))
            chk_names = {f"leg monthly rebalances>={RULES['b_reb']}", "leg net>0", "leg net>0 without its top name-month"}
            assert os.path.exists(rd) and sb["pass"] == ok and sb["cell"] == cand and sb["c"] == c_frozen and sb["leg"]["n_pos"] > 0 and {k_: sb.get(k_) for k_ in stamp()} == stamp() and sb["prereg_sha256_lf"] == PREREG_SHA
            assert set(sb["checks"]) == chk_names and ok is all(sb["checks"].values()) and sb["leg"]["n_units"] >= RULES["b_reb"] and sb["go_flag"].startswith("smoke: the lead's go-flag"), "the pass is the LEG's veto: three checks, no book"
            assert sb["wide_calendar"]["file"]["csv_sha256"] == env.wide_sha and sb["wide_calendar"]["file"]["rows_dropped_at_the_cut"] < winfo["rows_dropped_at_the_cut"] and sb["es_return_lb"]["stretch"] == ["2025-06-30", "2026-06-30"] and len(sb["top_name_months"]) == 20
            Wb, _calb, extb, _wib, _eib, tbb = smoke_world_b(env, "plant")                  # the lockbox leg recounted: the same loaders at the lockbox's end (the audit file applied), the leg by plain python
            apply_audit(Wb, read_audit())
            ctxb = make_ctx(Wb, extb)
            Lb = ni_build(Wb, ctxb, LB0, LB1, "remove")
            Pb = brute_positions(Wb, Lb, cand)
            xb_b = D15.to_B(brute_series_of(Wb, Pb)[0], A13.book_rows(B, Wb), B.n)
            lg = sb["leg"]
            assert lg["n_pos"] == len(Pb) and lg["n_units"] == len({p["ri"] for p in Pb}) == len(Lb.recs) and abs(lg["net"] - float(xb_b[B.mask(LB0, LB1)].sum())) < 1e-6 and abs(lg["net_pos"] - sum(p["pnl"] for p in Pb)) < 1e-6, (lg["n_pos"], len(Pb))
            assert abs(lg["top_pos"] - max(p["pnl"] for p in Pb)) < 1e-6 and sb["top_name_months"][0]["symbol"] == str(Wb.syms[max(Pb, key=lambda p: p["pnl"])["col"]]) and all(x_["date"] >= "2025-06-01" for x_ in sb["top_name_months"])
            add, mb_ = sb["book_add_reported"], B.mask(LB0, LB1)                           # the book add on the lockbox at the FROZEN c: reported, recomputed from the book file and the captured series
            want = R11.stats((np.asarray(B.raw, float) + c_frozen * cap["x"])[mb_], B.index[mb_])
            assert add["c"] == c_frozen and abs(add["roc"] - want["roc"]) < 1e-9 and abs(add["sortino"] - want["sort"]) < 1e-9 and abs(add["net"] - want["net"]) < 1e-6 and abs(add["max_dd"] - want["max_dd"]) < 1e-9, add
            assert add["reference"] == {"roc": RULES["b_roc"], "sortino": RULES["b_sort"]} and add["would_have_cleared"] is bool(want["roc"] >= RULES["b_roc"] and want["sort"] >= RULES["b_sort"]) and "never a pass" in add["note"]
            assert "book add, REPORTED and never part of the pass" in txt_b2 and ("PASS - the leg survives" in txt_b2) is ok and ("FAIL - the leg is vetoed" in txt_b2) is not ok
            # [N7] / [N9] / [N10]: the sealed year's leg under the reported floor, the dollars a year beside every ROC, the LOW-POWER flag in the verdict
            with spec(floor=FLOOR_REPORTED):
                Lb20 = ni_build(Wb, ctxb, LB0, LB1, "remove")
            Pb20 = brute_positions(Wb, Lb20, cand)
            l20 = sb["leg_reported_floor"]
            xb20 = D15.to_B(brute_series_of(Wb, Pb20)[0], A13.book_rows(B, Wb), B.n)
            assert l20["floor"] == FLOOR_REPORTED and l20["leg"]["n_pos"] == len(Pb20) and l20["leg"]["n_units"] == len({p["ri"] for p in Pb20}) == sum(1 for q in Lb.recs if q.n_new >= FLOOR_REPORTED) and 0 < len(Pb20) < len(Pb) and abs(l20["leg"]["net"] - float(xb20[mb_].sum())) < 1e-6
            yrs_lb = (B.index[mb_][-1] - B.index[mb_][0]).days / 365.25
            assert lg["years"] == yrs_lb and abs(lg["usd_per_year"] - lg["net"] / yrs_lb) < 1e-9 and abs(l20["leg"]["usd_per_year"] - l20["leg"]["net"] / yrs_lb) < 1e-9
            assert add["years"] == yrs_lb and add["usd_per_year"] == add["net"] / yrs_lb and abs(add["usd_per_year"] - want["net"] / yrs_lb) < 1e-6
            a463 = R11.stats(np.asarray(B.raw, float)[mb_], B.index[mb_])
            assert abs(add["reference_463_alone"]["roc"] - a463["roc"]) < 1e-9 and abs(add["reference_463_alone"]["net"] - a463["net"]) < 1e-6 and abs(add["reference_463_alone"]["usd_per_year"] - a463["net"] / yrs_lb) < 1e-6
            want20 = R11.stats((np.asarray(B.raw, float) + c_frozen * cap["x20"])[mb_], B.index[mb_])
            r20_ = add["reported_20_floor"]
            assert r20_["floor"] == FLOOR_REPORTED and abs(r20_["roc"] - want20["roc"]) < 1e-9 and abs(r20_["net"] - want20["net"]) < 1e-6 and abs(r20_["usd_per_year"] - want20["net"] / yrs_lb) < 1e-6
            vline = next(l for l in txt_b2.splitlines() if l.startswith("NEWISSUE Stage B:"))
            assert sb["low_power_flag"] == LOW_POWER and LOW_POWER in vline and "#463 alone on the sealed year: ROC@30k" in txt_b2 and f"{cand} @{FLOOR_REPORTED} (the REPORTED {FLOOR_REPORTED}-name floor [N7], never a pass route)" in txt_b2 and " a year)" in txt_b2

            def reread(leg_ok, book_ok):                                                   # the pass is the leg's veto ALONE: the same read again with the leg forced to pass and the book add's bar forced to miss, then the leg forced to fail and the bar forced to clear
                os.remove(rd)
                os.remove(os.path.join(OUT, "newissue_stageB.json"))

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
                return ok_, json.load(open(os.path.join(OUT, "newissue_stageB.json"))), b_.getvalue()
            for leg_ok, book_ok in ((True, False), (False, True)):
                ok2, sb2, t2 = reread(leg_ok, book_ok)
                assert ok2 is leg_ok and sb2["pass"] is leg_ok and all(sb2["checks"].values()) is leg_ok and sb2["book_add_reported"]["would_have_cleared"] is book_ok and os.path.exists(rd), (leg_ok, book_ok, sb2["checks"])
                assert abs(sb2["book_add_reported"]["roc"] - add["roc"]) < 1e-9 and sb2["book_add_reported"]["c"] == c_frozen, "the book add is the same sum whatever the verdict"
                assert ("PASS - the leg survives" in t2) is leg_ok and ("FAIL - the leg is vetoed" in t2) is not leg_ok and ("FORWARD SHADOW" in t2) is leg_ok
                print(f"  leg forced {'to pass' if leg_ok else 'to fail'}, book-add bar forced {'to clear' if book_ok else 'to miss'}: Stage B {'PASS' if ok2 else 'FAIL'}, would_have_cleared {sb2['book_add_reported']['would_have_cleared']} - the verdict is the leg's")
            with quiet():
                refused(stage_b, "already read")
                refused(stage_a, "Stage A is frozen")
            print("Stage B wrote the flag only after the load and the checks, refused a second read, and Stage A is frozen once the lockbox has been read")
        with quiet():
            main(["bogus"])                                                                # the commands that never touch data
        pm = peak_mb()
        print(f"SMOKE OK ({time.time() - t_start:.0f}s" + (f", peak memory {pm:,.0f} MB" if pm else "") + ") - synthetic numbers mean nothing; every command ran end to end offline"
              + ("" if with_b else " (Stage B's read was not run: `smoke DIR stage_b` runs it on the synthetic lockbox days)"))


def main(argv):
    cmd, args = (argv[0], argv[1:]) if argv else ("", [])
    fn = {"selftest": selftest, "smoke": smoke, "dryload": dryload, "stage_a": stage_a, "stage_b": stage_b}.get(cmd)
    if fn is None:
        print("usage: r20_newissue.py selftest | smoke DIR [stage_b] | dryload | stage_a | stage_b   (dryload: counts only; stage_a after the registered pre-registration is committed; stage_b only on the stock families' one sealed-year day, "
              "with the lead's newissue_stageB_GO.flag on file)")
        return
    if cmd in ("stage_a", "stage_b"):
        os.makedirs(OUT, exist_ok=True)
    fn(*args)


if __name__ == "__main__":
    main(sys.argv[1:])
