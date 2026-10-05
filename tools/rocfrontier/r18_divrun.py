# DIVRUN r1 - the RUN-UP into a large-cap stock's ex-dividend date, ES-hedged, US stocks, event-driven: cells R10 / R20 (a long $4,000 position in a REGULAR QUARTERLY PAYER of the top-500 universe, entered at the official CLOSE of the session
# 10 / 20 sessions before its PREDICTED ex-date P = E1 + (E1 - E2), with an ES hedge sold at the same 16:00 print), THREE exit rules computed for every cell on ONE entry set: the X-RULE (the close before the actual next ex-date X, else P + 10),
# NO-X (the close of P - 1: the BINDING twin of addendum [V1] - it does not know X) and P + 10 (reported). A leg for BOOK #463 that must clear the STANDALONE bars (MANAGER #56). Pre-registered:
# tools/rocfrontier/PREREG_DIVRUN_R1.txt (canonical LF sha256 806ff964...3267 = DRAFT v1 + PRE-DATA ADDENDUM 1 [V1]-[V5] + PRE-DATA ADDENDUM 2 [X1] [X2]). Every rule, threshold, window and cost below is that file; where it is silent the choice is marked CHOICE.
# DIVRUN is RESMOM r1's sibling in the same lane on the same data: r17_resmom.py is imported, never copied and never edited - and through it r15_ddw.py (World, universe, hygiene arrays, ES series, split-safe marks, cell statistics, seat measure, null
# statistics), r5_siporb (Data, read_long), r11_risk (the #463 book, stats), r12_mdl (Stretch, DO / rho_dd) and r13_attn (assert_cut, load_463, book_rows): the SIPORB cache loaders, the pinned wide corporate-actions calendar (wide_load, sha e5bc8487...),
# the dividend / spin-off arrays ([R1], [D2]), the 252-session regression convention, the A2 volatility rule and the book checks are theirs. What this file adds is the EVENT logic: cycles, P / X, the three exits, the aggregate whole-MES hedge, the two nulls.
#   python r18_divrun.py selftest    hand-made worlds, no data: the cycle rule, P snapping, entry set and every skip, the three exits, the P&L (dividend credit, ex-day drop), the aggregate whole-MES hedge against the exact one and its costs,
#                                    hygiene (removed / kept at naive raw P&L), the placebo-in-time and random-name nulls (and the null's DO), the event-time paths on a planted run-up (P axis and X axis), the yardstick, the checks, the refusals;
#                                    [X1] the REFERENCE book on stubbed RESMOM line files (the sha pin, the row-for-row dates, the registered 120.82 / 3.916 / $36,526), the incremental A2 on a planted cell, the episode table on the reference; [X2] the 0 bps row, the diagnostics tables
#   python r18_divrun.py smoke DIR   offline end-to-end on SYNTHETIC worlds (r5_siporb's fake Alpaca, a fake ES master, a fake #463, a fake RESMOM line file, a fake TBIS file, a fake wide calendar): a world with a planted run-up that Stage A must find and a world
#                                    without one where it must not; DIR's name must contain 'smoke'; every command except Stage B's read runs (Stage B is exercised on the synthetic world only by `smoke DIR stage_b`)
#   python r18_divrun.py dryload     WF inputs only (every input cut to dates < 2025-06-30): prints COUNTS - payers in the universe by year, events per cell by year and the skips, X against P, hygiene flags, trades per day, the first and
#                                    last entry dates - never a price, return, P&L or Stage A statistic
#   python r18_divrun.py stage_a     WF Stage A (per cell and per exit rule) + the event-time paths (P axis, X axis) FIRST + the nulls + A2 (an INCREMENTAL report over the REFERENCE book #463 + 0.264 x RES) + the reports + the diagnostics -> divrun_stageA.json (+ divrun_audit_candidates.csv), PRE-LOCKBOX ONLY
#   python r18_divrun.py stage_b     Stage B (lockbox, ONCE): refuses unless the lead's flag file divrun_stageB_GO.flag is on file (and a Stage A candidate with the hand audit signed off by that flag); the pass is the LEG's veto
# Reads (never writes) the SIPORB cache through r5_siporb, the ES 5m RTH masters through augur_engine.data, the #463 book through r11_risk, the sha-pinned wide corporate-actions calendar (cut at read) and - Stage A only - RESMOM's sha-pinned WF line file (the REFERENCE book). Results go to OUT (outside git). Nothing here
# pulls, commits, pushes or writes anywhere else.
import contextlib, hashlib, inspect, io, json, math, os, re, shutil, sys, tempfile, time
from collections import Counter, defaultdict
from types import SimpleNamespace
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import numpy as np, pandas as pd
import r17_resmom as M17             # the sibling harness (RESMOM r1): its loaders, calendar, dividend arrays, A2 and book checks are called wherever they fit
D15, S, R11, M12, A13 = M17.D15, M17.S, M17.R11, M17.M12, M17.A13       # r15_ddw (World, universe, cell statistics, seat), r5_siporb, r11_risk, r12_mdl, r13_attn - through r17's own imports

TS = pd.Timestamp
OUT = os.environ.get("EDGELOG_DIVRUN_R1", r"C:\EdgeLog\_anatomy_cache\rocfrontier\divrun_r1")        # results, outside git
PREREG = os.path.join(HERE, "PREREG_DIVRUN_R1.txt")
PREREG_SHA = "806ff96466944dbc5c10c4bc8000f4946260481e74eda06a8072d83dfbb63267"                      # canonical (LF) sha256 of the pre-registration: DRAFT v1 + PRE-DATA ADDENDUM 1 ([V1] the exit must not need X, [V2] nulls, [V3] hygiene inside the hold, [V4] the event-time path first, [V5] costs and the hedge as traded) + PRE-DATA ADDENDUM 2 ([X1] the book add is INCREMENTAL over the RESMOM line, [X2] deeper diagnostics); if more edits land the lead updates it before the real run
WF0, PRE_END, LB0, LB1 = M17.WF0, M17.PRE_END, M17.LB0, M17.LB1          # WF = positions EXITED 2016-07-01 .. 2025-06-29; LB = exits 2025-06-30 .. 2026-06-30 INCLUSIVE; cuts: S.LB0 / S.END
BOOK_WF, BOOK_LB, DEEPEST_WF = M17.BOOK_WF, M17.BOOK_LB, M17.DEEPEST_WF
NREP, SEED = 500, 20261005
CELLS = ("R10", "R20")                                                  # the family: 2 cells = K sessions before the predicted ex-date P
KS = {"R10": 10, "R20": 20}
EXITS = ("X", "NOX", "P10")                                             # the three exit rules, all computed for every cell on ONE entry set
EXIT_NAME = {"X": "X-rule (the close before the actual X; P + 10 if X is late or missing)", "NOX": "NO-X (the close of P - 1; the registered twin [V1])", "P10": "P + 10 (the close of P + 10; reported)"}
REGISTERED = "NOX"                                                      # [V1] if the X-rule and NO-X verdicts differ, the NO-X verdict is the registered one
NULL_EXITS = ("X", "NOX")                                               # CHOICE: the placebo-in-time null is drawn for the two rules that carry a verdict; P + 10 is a REPORTED row (its hold, 30 sessions at R20, leaves no placebo session in a typical 63-session quarter: E1 + 11 .. P - 26 - h is empty)
YEARS = D15.YEARS                                                       # the nine July-June WF years 2016-17 .. 2024-25
SUBPERIODS = (("2016-07-01 .. 2021-12-31", TS("2016-07-01"), TS("2021-12-31")), ("2022-01-01 .. 2025-06-29", TS("2022-01-01"), TS("2025-06-29")))   # [V4] the rates regime the counter-evidence names
A2_WIN = (TS("2017-03-01"), TS("2019-02-28"))                           # A2 (a REPORT): c is set on the cell's first two full years (the first predictable events need three ex-dates on a calendar that starts 2016-06-01: first entries ~2017-02) ...
A2_TARGET, A2_REPORT = 0.25, (0.5, 2.0)                                  # ... so that c x the cell's daily std = 25% of #463's over them; the book at 0.5c and 2c is reported (the book is the REFERENCE book now [X1]; the plain #463 + c x cell is a reported row)

# [X1] the REFERENCE book = #463 + 0.264 x RES (RESMOM r1's registered WF line). The file is written by r17_resmom_export.py from RESMOM's Stage A and pinned by the sha256 of its BYTES; the harness refuses a different one
REF_CSV_PINNED = r"C:\EdgeLog\_anatomy_cache\rocfrontier\resmom_r1\resmom_cells_daily_wf.csv"
REF_CSV = REF_CSV_PINNED                                                # the stages read this one (the selftest and the smoke point it at stubs: the real file is never read by a test)
REF_SHA = "bed7bf8b98d201894471cd3e72bd146bb87260c6cc8d1ac54b8167f923d41819"
REF_COLS = ("date", "book_mtm", "RES", "RAW")
REF_W = 0.264                                                           # the reference = #463 + 0.264 x RES
REF_FACTS = {"roc": 120.82, "sortino": 3.916, "max_dd": 36526.0}        # its registered WF ROC @ $30k, Sortino and worst drawdown ...
REF_TOL = {"roc": 0.01, "sortino": 0.001, "max_dd": 1.0}                # ... and the tolerances the harness refuses outside of
REF_BOOK_ATOL = 1.0                                                     # CHOICE: the file's book_mtm must equal #463's own daily P&L on every WF row to the dollar (the file is text: it may be rounded to a cent or to a dollar; another #463 differs by far more, and the registered numbers are asserted on the reference as well)
COST_BPS, STRESS_BPS = D15.COST_BPS, D15.STRESS_BPS                      # 5 bps of the notional a side on the stock (base); stress 10 and 20; no borrow (the stocks are only bought)
MES_PT, MES_PT_COST, MES_COMM_RT = 5.0, 0.363, 1.00                      # [V5] MES: $5 a point; the house micro cost = 0.363 pt x $5 + $1.00 commission per round trip ...
MES_SIDE = 0.5 * (MES_PT_COST * MES_PT + MES_COMM_RT)                    # ... so half of it, $1.4075 per MES, is paid on every contract added or removed (a side). CHOICE: the prereg gives the cost per round trip 'half a side'; read as this per contract changed (r11_risk's own ES micro round trip, 0.63 pt, is not used)
ES_EXACT_BPS = 0.5                                                       # the trade-level (exact, fractional) hedge: ES 0.5 bps of the hedge notional a side
AUDIT_N = 50                                                             # (f) the largest single-trade contributors audited by hand
SPEC = {"slot": 4000.0,          # $ per trade, fractional shares, no compounding
        "win": 252,              # the beta regression: sessions entry-251 .. entry (252 of them) ...
        "min_pairs": 230,        # ... with at least 230 split-safe (stock return, ES return) pairs (ES-hole sessions skipped), an intercept; r17_resmom's rm_scores convention
        "cyc_lo": 77, "cyc_hi": 105,     # the cycle: both gaps (E1 - E2, E2 - E3) in 77 .. 105 calendar days, inclusive
        "plus": 10,              # the fallback / third exit: P + 10 sessions
        "hyg_lead": 5,           # CHOICE: DDW r1's [T2] looks 5 sessions before the decision for flags known at it: entry-5 .. entry (all four reasons) remove the trade in BOTH readings
        "pl_lo": 11, "pl_margin": 26, "pl_tries": 20,        # the placebo: an entry session in E1 + 11 .. P - 26 - h, redrawn up to 20 times when the window touches an ex-date (CHOICE: sessions; 20 draws in all)
        "own_lead": 25,          # the random-name null: the name's own window P' - 25 .. X' must not overlap the hold
        "tau_lo": -20, "tau_hi": 10,      # CHOICE: the event-time path is on the P axis: sessions P - 20 .. (each event's own X - 1), printed from P - 20 to P + 10
        "xtau_lo": -25, "xtau_hi": 5}     # [X2] the draft's X-axis variant of the path: sessions X - 25 .. X + 5
RULES = {"n": 1000, "roc": 15.0, "net_pos": True, "stress": True, "null": True, "years": 6, "ex2020": True, "exbest": True, "best_pct": 1,      # Stage A (a) - (e); the booleans are switches only smoke() ever turns off
         "a2_roc": D15.RULES["a2_roc"], "a2_sort": D15.RULES["a2_sort"],                                                                         # A2's shadow-line bar (98.5005 / 3.816, a REPORT)
         "b_n": 100, "b_roc": BOOK_LB[0], "b_sort": BOOK_LB[1]}                                                                                   # Stage B: >= 100 trades; the book add's reference (#463's own LB 155.54 / 4.150), reported only
CHECK_BOOK = True        # refuse to judge if the #463 records / the DD structure / the cache manifest do not reproduce the registered facts; a real run always checks (only smoke() may switch it)
HYG = D15.HYG            # the four data-hygiene reasons [T2], in the order a trade's first reason is attributed: split, gap, tbis, jump
GO_FLAG, READ_FLAG = "divrun_stageB_GO.flag", "divrun_stageB_READ.flag"     # Stage B needs the lead's go-flag; CHOICE (r15's / r17's pattern): the one-shot read flag is written (exclusively) after every load and check
WIDE_CA_SHA = M17.WIDE_CA_SHA


# ------------------------------------------------------------------ guards: the prereg, the stamp, the cut, the files
def refuse(msg):
    raise SystemExit(msg)


assert_cut, peak_mb, patched, ceil_pct = A13.assert_cut, A13.peak_mb, A13.patched, A13.ceil_pct
file_sha, manifest_sha, book_checks = D15.file_sha, D15.manifest_sha, D15.book_checks      # module-level names, so a test can stub them


def prereg_ok():
    """the frozen spec this file implements must still be the registered one (a changed spec = a new file, r2): a missing or changed file refuses every stage. Also checked against the committed blob when there is one
    (r15_ddw.committed_state, pointed at this file's names for the call); until it is committed that is printed (the lead commits before the real run) and recorded in the Stage A file"""
    if not os.path.exists(PREREG):
        refuse("refused: PREREG_DIVRUN_R1.txt is not next to this file - the spec cannot be verified (nothing computed, lockbox NOT read)")
    if R11.sha_lf(PREREG) != PREREG_SHA:
        refuse("refused: PREREG_DIVRUN_R1.txt DIFFERS from the registered one - a changed spec is a new file, r2 (nothing computed, lockbox NOT read)")
    with patched(D15, PREREG=PREREG, PREREG_SHA=PREREG_SHA):
        st = D15.committed_state()
    if st == "differs":
        refuse("refused: the COMMITTED PREREG_DIVRUN_R1.txt differs from the registered sha - the file on disk is not the file in git (nothing computed, lockbox NOT read)")
    print("prereg check: PREREG_DIVRUN_R1.txt sha256 matches the registered one; committed blob: " + {"match": "matches too", "untracked": "NOT COMMITTED YET - commit it before the real run",
                                                                                                    "unknown": "git not available here (not checked)"}[st])
    return {"verified": True, "committed": st}


def stamp():
    """the version a stage ran with: this file's LF sha256 + r17_resmom's and every harness it imports numbers from (r15's data layer / marks / statistics, r5_siporb's Data / read_long, r11's book and stats, r12's DO / rho_dd, r13's helpers) + the
    pinned calendar's sha + the shared half-day list; Stage B refuses on any change, so a change to any of them after Stage A sends it through Stage A again"""
    s = M17.stamp()
    return {"harness_sha256": R11.sha_lf(os.path.abspath(__file__)), "r17_sha256": s["harness_sha256"], **{k: v for k, v in s.items() if k != "harness_sha256"}}


@contextlib.contextmanager
def spec(**kw):
    """swap SPEC entries for a block and put them back (the self-tests and the smoke shrink the windows and the size; nothing stays patched)"""
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
    """the July-June year of a date (2017-06-30 is 2016-17, 2017-07-03 is 2017-18)"""
    d = pd.DatetimeIndex(d)
    return d.year.to_numpy().astype(int) - (d.month.to_numpy() < 7).astype(int)


# ------------------------------------------------------------------ the events: regular dividends -> cycles -> P and X
def rows_of(dv, dates, ahead=False):
    """the session row of each date: the first session on / after it (a date that is not a session moves to the NEXT one: P's snapping rule, applied to every calendar date here); -1 for a missing date or one after the
    last session (outside the data). dv = the sessions as datetime64[ns]. ahead=True (used for P and nothing else; CHOICE): a date after the last session but on / before the NEXT WEEKDAY - the first session the data does not hold, the cut
    day itself in Stage A - gets row len(dv), placed by DATE ARITHMETIC alone (no price, return or session of it is read): a trade whose P is that session enters K sessions before it and exits NO-X at the data's last session, both inside
    the data, so Stage A's WF set is the very one Stage B re-reads on the longer data (without it an event with P on the cut Monday would be in Stage B's WF and not in Stage A's); any later date stays -1"""
    v = np.asarray(dates).astype("datetime64[ns]")
    r = np.searchsorted(dv, v, side="left")
    out = np.where(np.isnat(v) | (r >= len(dv)), -1, r)
    if ahead and len(dv):
        nxt = np.busday_offset(dv[-1].astype("datetime64[D]"), 1, roll="forward").astype("datetime64[ns]")
        out = np.where((r >= len(dv)) & ~np.isnat(v) & (v <= nxt), len(dv), out)
    return out


def regular_rows(div):
    """the REGULAR (non-special) cash dividends of the pinned calendar (r17_resmom.wide_load's cal.div: symbol, ex, amt, special), one row per (symbol, ex-date) - the rows of one name on one ex-date add up, as r17_resmom.div_matrix adds
    them -> a frame (symbol, ex, amt) sorted by symbol, ex-date. Special dividends never define the cycle"""
    if div is None or not len(div):
        return pd.DataFrame({"symbol": pd.Series(dtype=str), "ex": pd.Series(dtype="datetime64[ns]"), "amt": pd.Series(dtype=float)})
    reg = div[~div["special"].to_numpy(bool)]
    g = reg.groupby(["symbol", "ex"], sort=True, as_index=False)["amt"].sum()
    return g.sort_values(["symbol", "ex"], kind="stable").reset_index(drop=True)


def build_events(div, days, syms):
    """EVENT per regular ex-date E1 of a name on the grid: E2 / E3 = the name's two regular ex-dates before it, X = the first regular ex-date after it (none: NaT), the CYCLE test = both gaps (E1 - E2, E2 - E3) inside 77 .. 105
    calendar days (inclusive; monthly, semi-annual and annual payers fail it; a special dividend is never one of the three because only regular rows are read), the PREDICTED ex-date P = E1 + (E1 - E2) calendar days, moved to the NEXT session
    if it is not one (rows_of). E1 is the key: one event per regular ex-date. -> SimpleNamespace(n, col, sym, e1, e2, e3, gap1, gap2, amt1, cyc, p_date, x_date, e1_row, p_row, x_row, counts); *_row = -1 when the date is missing or after
    the last session of the data (p_row = -1: P is beyond the data - the event cannot place its entry and exits on the market calendar and is counted; p_row = T: P is the first session the data does not hold, see rows_of(ahead))"""
    sp = SPEC
    dv = np.asarray(pd.DatetimeIndex(days)).astype("datetime64[ns]")
    g = regular_rows(div)
    cnt = {"regular_rows": int(len(g)), "names_with_regular_rows": int(g["symbol"].nunique()) if len(g) else 0}
    nat = np.datetime64("NaT")
    if not len(g):
        z, zn = np.zeros(0, np.int64), np.zeros(0, "datetime64[ns]")
        return SimpleNamespace(n=0, col=z, sym=np.zeros(0, str), e1=zn, e2=zn, e3=zn, gap1=np.zeros(0), gap2=np.zeros(0), amt1=np.zeros(0), cyc=np.zeros(0, bool), p_date=zn, x_date=zn, e1_row=z, p_row=z, x_row=z,
                               counts={**cnt, "rows_not_on_the_grid": 0, "events": 0, "cycle_ok": 0, "cycle_ok_p_beyond_the_data": 0, "cycle_ok_p_on_the_next_session": 0})
    sym = g["symbol"].astype(str).to_numpy()
    ex = pd.DatetimeIndex(g["ex"]).to_numpy().astype("datetime64[ns]")
    gb = g.groupby("symbol", sort=False)["ex"]
    e2, e3, xn = (gb.shift(k).to_numpy().astype("datetime64[ns]") for k in (1, 2, -1))
    one = np.timedelta64(1, "D")
    gap1, gap2 = (ex - e2) / one, (e2 - e3) / one
    with np.errstate(invalid="ignore"):
        cyc = (gap1 >= sp["cyc_lo"]) & (gap1 <= sp["cyc_hi"]) & (gap2 >= sp["cyc_lo"]) & (gap2 <= sp["cyc_hi"])
    col = pd.Index(syms).get_indexer(sym)
    keep = col >= 0
    p_date = np.where(cyc, ex + np.where(cyc, gap1, 0.0).astype("int64").astype("timedelta64[D]"), nat).astype("datetime64[ns]")
    ev = SimpleNamespace(n=int(keep.sum()), col=col[keep], sym=sym[keep], e1=ex[keep], e2=e2[keep], e3=e3[keep], gap1=gap1[keep], gap2=gap2[keep], amt1=g["amt"].to_numpy(float)[keep], cyc=cyc[keep], p_date=p_date[keep],
                         x_date=xn[keep], e1_row=rows_of(dv, ex[keep]), p_row=rows_of(dv, p_date[keep], ahead=True), x_row=rows_of(dv, xn[keep]))
    ev.counts = {**cnt, "rows_not_on_the_grid": int((~keep).sum()), "events": ev.n, "cycle_ok": int(ev.cyc.sum()), "cycle_ok_p_beyond_the_data": int((ev.cyc & (ev.p_row < 0)).sum()),
                 "cycle_ok_p_on_the_next_session": int((ev.cyc & (ev.p_row == len(dv))).sum())}
    return ev


# ------------------------------------------------------------------ the context: events + the arrays the entry set, the hedge and the nulls read
def _cum(a, dt=np.int32):
    """(T, S) -> (T + 1, S): a zero row and the running sum, so rows a .. b of a count / flag matrix are  c[b + 1] - c[a]"""
    out = np.zeros((a.shape[0] + 1, a.shape[1]), dt)
    np.cumsum(a, axis=0, dtype=dt, out=out[1:])
    return out


def attach_es(W):
    """the ES 16:00 prints the hedge trades at, carried across the sessions that have none: esA = the roll-corrected print (P&L), esR = the unadjusted print (the level the contracts are counted on). CHOICE: a session with no print (the
    two holes of the ES masters, 2020-02-28 and 2020-06-30) repeats the last one - no hedge change is made there (it is made at the next print) and the ES move over the hole is paid at the next session in full; es_hole marks those sessions"""
    a, r = np.asarray(W.es.c16a, float), np.asarray(W.es.c16r, float)
    good = np.isfinite(a) & np.isfinite(r) & (r > 0)
    W.esA = pd.Series(np.where(good, a, np.nan)).ffill().to_numpy()
    W.esR = pd.Series(np.where(good, r, np.nan)).ffill().to_numpy()
    W.es_hole = ~good
    return W


def pair_counts(W):
    """(T, S) int32: the (return, ES return) pairs in the 252 sessions ending at each row (0 where the window is not full, i.e. before row 251) - the 230-pair rule's input, counted from which returns EXIST, never from their values (the dryload's use)"""
    win = SPEC["win"]
    ok = np.isfinite(np.asarray(W.Rd, float)) & np.isfinite(np.asarray(W.es.ret, float))[:, None]
    N = _cum(ok)
    n = np.zeros((W.T, W.S), np.int32)
    if W.T >= win:
        n[win - 1:] = N[win:] - N[:W.T - win + 1]
    return n


def rolling_beta(W):
    """(beta, n): the OLS slope of each name's split-safe TOTAL daily return (r17_resmom's W.Rd: price + the cash dividend on its ex-date, spin-off / stock-dividend sessions left out) on ES's, intercept, over the 252 sessions
    entry-251 .. entry for EVERY row at once (running sums of the pairs - the same closed form as r17_resmom.rm_scores' beta, which the selftest recomputes window by window and by least squares); NaN under 230 pairs, before row 251
    or without ES variation. ES-hole sessions are skipped (no pair). n = the pair counts. CHOICE: the prereg says 'split-safe' returns and does not say price or total return: r17_resmom's TOTAL return (its regression convention) is
    used; r17_resmom exposes no function that returns the beta, so its closed form is repeated here (and the selftest checks it against r17_resmom's and against least squares)"""
    win, minp = SPEC["win"], SPEC["min_pairs"]
    y, m = np.asarray(W.Rd, float), np.asarray(W.es.ret, float)
    T, S_ = y.shape
    ok = np.isfinite(y) & np.isfinite(m)[:, None]
    yy, xx = np.where(ok, y, 0.0), np.where(ok, m[:, None], 0.0)
    beta = np.full((T, S_), np.nan)
    n = np.zeros((T, S_), np.int32)
    if T < win:
        return beta, n
    w = lambda a, dt=float: (lambda c: c[win:] - c[:T - win + 1])(_cum(a, dt))
    nn = w(ok, np.int32)
    sy, sx, sxy, sxx = w(yy), w(xx), w(yy * xx), w(xx * xx)
    with np.errstate(invalid="ignore", divide="ignore"):
        d = np.maximum(nn, 1)
        var = sxx - sx * sx / d
        b = (sxy - sx * sy / d) / var
        good = (nn >= minp) & (var > 1e-12 * np.maximum(sxx, 1e-300))
    beta[win - 1:] = np.where(good, b, np.nan)
    n[win - 1:] = nn
    return beta, n


def ex_matrices(cal, W):
    """the calendar's ex-dates on the grid, as cumulative counts (T + 1, S) int32: spc = SPECIAL cash dividends on their ex-date session (hygiene [V3]: a special dividend inside a hold flags the trade; an ex-date that is not a session is
    not placed, as r17_resmom.div_matrix does), exc = EVERY ex-date of the name - cash dividends regular and special, spin-offs, stock dividends - moved to the next session when it is not one (CHOICE: the placebo's 'touches an ex-date'
    test stays on the safe side), and the special-dividend session matrix itself"""
    T, S_ = W.T, W.S
    dv = np.asarray(W.days).astype("datetime64[ns]")
    spc = np.zeros((T, S_), np.int32)
    exc = np.zeros((T, S_), np.int32)
    if cal is not None:
        d = cal.div
        if len(d):
            sp_ = d[d["special"].to_numpy(bool)]
            ci, di = M17.div_index(sp_, W.days, W.syms)
            ok = (ci >= 0) & (di >= 0)
            np.add.at(spc, (di[ok], ci[ok]), 1)
        for fr in (cal.div, cal.spin):
            if fr is None or not len(fr):
                continue
            ci = pd.Index(W.syms).get_indexer(fr["symbol"].astype(str))
            di = rows_of(dv, pd.DatetimeIndex(fr["ex"]).to_numpy())
            ok = (ci >= 0) & (di >= 0)
            np.add.at(exc, (di[ok], ci[ok]), 1)
    return _cum(spc), _cum(exc), spc > 0


def payer_matrix(W, ev):
    """(T, S) int32: on session t the P row of the name's ACTIVE cycle event - the event whose E1 is the name's latest regular ex-date on or before t (E1's row .. the row before X's) - when that event passes the cycle test (a
    'regular quarterly payer at the close of t'; CHOICE: the payer rule of the random-name null, the prereg names none); -1 otherwise. P beyond the data stores T + 1000 (a window that starts after the data ends)"""
    T, S_ = W.T, W.S
    out = np.full((T, S_), -1, np.int32)
    for i in np.flatnonzero(ev.cyc & (ev.e1_row >= 0)):
        a = int(ev.e1_row[i])
        b = int(ev.x_row[i]) if ev.x_row[i] >= 0 else T
        if b > a:
            out[a:b, ev.col[i]] = ev.p_row[i] if ev.p_row[i] >= 0 else T + 1000
    return out


def make_ctx(W, cal, counts_only=False):
    """everything the cells read besides the World: the events (the calendar's REGULAR dividends), the ES prints carried over holes, the rolling beta (counts_only: only the pair counts - the dryload never computes a regression), the cumulative
    ex-date / special / flag / finite-close counts and the payer matrix of the nulls; the audit's data events (none until apply_audit)"""
    attach_es(W)
    ev = build_events(None if cal is None else cal.div, W.days, W.syms)
    ctx = SimpleNamespace(ev=ev, cal=cal, aud_ev=np.zeros(ev.n, bool), counts_only=bool(counts_only))
    if counts_only:
        ctx.npair, ctx.beta = pair_counts(W), None
        ctx.bok = ctx.npair >= SPEC["min_pairs"]
    else:
        ctx.beta, ctx.npair = rolling_beta(W)
        ctx.bok = np.isfinite(ctx.beta)
    ctx.spcs, ctx.exc, spc_m = ex_matrices(cal, W)
    ctx.finc = _cum(np.isfinite(W.Ac))
    ctx.flagcs = _cum(W.fl[0] | W.fl[1] | W.fl[2] | W.fl[3] | W.SPN | spc_m)
    ctx.pay_p = payer_matrix(W, ev)
    return ctx


# ------------------------------------------------------------------ the entry set (ONE per cell, shared by the three exit rules) and the exits
ENTRY_REASONS = ("no_history", "e1_after_entry", "not_universe", "x_passed", "x_next", "no_close", "no_beta", "audit")


def entry_set(W, ctx, K):
    """the events a cell K enters, ONE set for the three exit rules. Entry session e = the session K sessions before P (P's row - K); an event is a candidate when it passes the cycle test and P is in the data. Each candidate then fails at its FIRST
    reason, in this order: no_history (e is before the data), e1_after_entry (E1 must be on or before the entry session), not_universe (DDW r1's top-500 test at the ENTRY CLOSE = the universe row of the next session, which reads sessions up to
    the entry close only; CHOICE: DDW r1's [M6] convention for 'the universe at the entry close'), x_passed (X, the first regular ex-date after E1, falls on or before the entry session: no trade), x_next (X is the NEXT session: no trade - the one piece of X-knowledge this shared set uses), no_close (no
    split-safe close at the entry), no_beta (fewer than 230 pairs / no ES variation in the 252 sessions entry-251 .. entry), audit (a hand-audit data event). -> SimpleNamespace(K, idx = event indices that enter, e, col, p, xr, e1r, beta, npair, cnt =
    {entry year: Counter of events and first reasons}). CHOICE: the order of the first reasons is the order listed (the two X skips are counted among the events that already passed the universe test)"""
    ev, T = ctx.ev, W.T
    n = ev.n
    e = ev.p_row - K
    base = ev.cyc & (ev.p_row >= 0)
    ec = np.clip(e, 0, max(T - 1, 0))
    col, xr = ev.col, ev.x_row
    uni = np.zeros(n, bool)
    m = base & (e >= 0) & (ec + 1 <= T - 1)
    uni[m] = W.U[ec[m] + 1, col[m]]
    e1_ok = ev.e1 <= np.asarray(W.days).astype("datetime64[ns]")[ec]
    reasons = [("no_history", ~(e >= 0)), ("e1_after_entry", ~e1_ok), ("not_universe", ~uni), ("x_passed", (xr >= 0) & (xr <= e)), ("x_next", (xr >= 0) & (xr == e + 1)),
               ("no_close", ~np.isfinite(W.Ac[ec, col])), ("no_beta", ~ctx.bok[ec, col]), ("audit", ctx.aud_ev)]
    bi = np.flatnonzero(base)
    first = D15.attribute([(lab, r_[bi]) for lab, r_ in reasons], len(bi))
    cnt = defaultdict(Counter)
    labels = [lab for lab, _ in reasons] + ["entry_set"]
    code = np.where(first < 0, len(reasons), first)
    yr = np.asarray(W.days.year)[ec[bi]] if len(bi) else np.zeros(0, int)
    for y in np.unique(yr):
        sel = yr == y
        c = np.bincount(code[sel], minlength=len(labels))
        cnt[int(y)] = Counter({lab: int(v) for lab, v in zip(labels, c) if v})
        cnt[int(y)]["events"] = int(sel.sum())
    idx = bi[first < 0]
    o = np.lexsort((col[idx], e[idx]))
    idx = idx[o]
    beta = ctx.beta[e[idx], col[idx]] if ctx.beta is not None else np.full(len(idx), np.nan)
    return SimpleNamespace(K=K, idx=idx, n=len(idx), e=e[idx], col=col[idx], p=ev.p_row[idx], xr=xr[idx], e1r=ev.e1_row[idx], beta=beta, npair=ctx.npair[e[idx], col[idx]], cnt=cnt)


def x_position(es):
    """where X fell against the NO-X exit session P - 1 for the events that enter: (before, at, after) - X before P - 1, on it, after it (or no X on the calendar by the data's end). Counts"""
    p, xr = es.p, es.xr
    before = (xr >= 0) & (xr < p - 1)
    at = xr == p - 1
    after = ~before & ~at
    return {"before": int(before.sum()), "at": int(at.sum()), "after": int(after.sum()), "n": int(len(p))}


def rule_exits(es, rule, T):
    """(x rows, kind, resolved) of the events that enter, per exit rule. NOX: the close of P - 1. P10: the close of P + 10. X: the close of X - 1 when X falls at least two sessions after the entry and no later than P + 10 (the entry
    set already holds no X on / before the entry or on the next session), else the close of P + 10 (kind 1 = X is late or missing: a skipped, late or cut dividend). resolved = the exit session is inside the data (a P + 10 exit past it is
    unresolved: out of the cell AND the null, counted). CHOICE: the three rules share ONE entry set but each is resolved on its own at the end of the data (NO-X needs only P; the X-rule needs X or P + 10; P + 10 needs P + 10)"""
    p, e, xr, plus = es.p, es.e, es.xr, SPEC["plus"]
    if rule == "NOX":
        x, kind = p - 1, np.zeros(len(p), int)
    elif rule == "P10":
        x, kind = p + plus, np.zeros(len(p), int)
    elif rule == "X":
        ok = (xr >= e + 2) & (xr <= p + plus)
        x, kind = np.where(ok, xr - 1, p + plus), (~ok).astype(int)
    else:
        raise ValueError(rule)
    return x, kind, x <= T - 1


def trade_set(W, ctx, es, rule, reading, lo, hi):
    """the trades of one (cell, exit rule, reading) whose exit session falls in [lo, hi] (the stretch: trades are counted by EXIT date), with data hygiene [V3] + the DATA paragraph. A trade is flagged by: DDW r1's four reasons (registered
    split, gap scan, TBIS, a raw gap beyond +-50% with no factor change) on the 5 sessions before the entry through the entry (CHOICE: known at the decision, so they remove the trade in BOTH readings) and inside the hold (sessions e+1 ..
    x: the look-ahead removal [V3]), plus a SPECIAL cash dividend or a spin-off / stock-dividend ex-date inside the hold (the price drops mechanically; CHOICE: 'inside the hold' = sessions e+1 .. x - the entry session's own ex-date is bought ex and
    belongs to the 'pre' window, the exit session is held through its close). reading 'registered' REMOVES a trade flagged inside the hold (from the cell and the
    null); 'naive' KEEPS it at its naive RAW price path (no split safety) and raw cash. A trade with no ES print at the entry or exit cannot be hedged (no_es; CHOICE: a session with no print carries the last one - attach_es - so only a session before the first print counts here). -> Tr: arrays of the kept trades in (entry, name) order + hygiene counts by entry year"""
    T, sp = W.T, SPEC
    x, kind, res = rule_exits(es, rule, T)
    dx = np.asarray(W.days).astype("datetime64[ns]")[np.clip(x, 0, T - 1)]
    inwin = res & (dx >= np.datetime64(lo)) & (dx <= np.datetime64(hi))
    sel = np.flatnonzero(inwin)
    e, xs, col = es.e[sel], x[sel], es.col[sel]
    cnt = defaultdict(Counter)
    yrs_all = np.asarray(W.days.year)[np.clip(es.e, 0, T - 1)]
    for y, c_ in zip(*np.unique(yrs_all[~res], return_counts=True)):
        cnt[int(y)]["unresolved"] += int(c_)
    pre = np.stack([(W.hcs[q][e + 1, col] - W.hcs[q][np.maximum(e - sp["hyg_lead"], 0), col]) > 0 for q in range(4)]) if len(sel) else np.zeros((4, 0), bool)
    hold = np.stack([(W.hcs[q][xs + 1, col] - W.hcs[q][e + 1, col]) > 0 for q in range(4)] + [(ctx.spcs[xs + 1, col] - ctx.spcs[e + 1, col]) > 0, (W.spcs[xs + 1, col] - W.spcs[e + 1, col]) > 0]) if len(sel) else np.zeros((6, 0), bool)
    no_es = ~(np.isfinite(W.esR[e]) & np.isfinite(W.esA[e]) & np.isfinite(W.esR[xs]) & np.isfinite(W.esA[xs])) if len(sel) else np.zeros(0, bool)
    reasons = [("no_es", no_es)] + [(f"pre_{h}", pre[q]) for q, h in enumerate(HYG)]
    if reading == "registered":
        reasons += [(f"hold_{h}", hold[q]) for q, h in enumerate(HYG)] + [("hold_special", hold[4]), ("hold_spin", hold[5])]
    first = D15.attribute(reasons, len(sel))
    yr_s = yrs_all[sel]
    labels = [lab for lab, _ in reasons] + ["trades"]
    code = np.where(first < 0, len(reasons), first)
    for y in np.unique(yr_s):
        c = np.bincount(code[yr_s == y], minlength=len(labels))
        cnt[int(y)].update({lab: int(v) for lab, v in zip(labels, c) if v})
    keep = first < 0
    hold_any = hold.any(axis=0) if len(sel) else np.zeros(0, bool)
    naive = (hold_any & keep) if reading == "naive" else np.zeros(len(sel), bool)
    for y in np.unique(yr_s[naive]):
        cnt[int(y)]["kept_naive"] += int((naive & (yr_s == y)).sum())
    k = sel[keep]
    o = np.lexsort((es.col[k], es.e[k]))
    k = k[o]
    nv = naive[keep][o]
    return SimpleNamespace(rule=rule, reading=reading, K=es.K, n=len(k), ev=es.idx[k], col=es.col[k], e=es.e[k], x=x[k], p=es.p[k], xr=es.xr[k], e1r=es.e1r[k], beta=es.beta[k], npair=es.npair[k], kind=kind[k], naive=nv, cnt=cnt,
                           lo=lo, hi=hi)


# ------------------------------------------------------------------ the engine: split-safe marks, the two hedges, the daily series, the statistics, the checks
def stock_paths(W, tr):
    """the flat marks of every trade, all trades at once: trade i holds from the CLOSE of its entry session e to the CLOSE of its exit session x ($4,000, fractional shares: $1 of entry notional = 1 / the entry close), valued at every close of rows
    e + 1 .. x on the SPLIT-SAFE close (Ac); a trade flagged and kept by the naive reading is valued on the RAW close (Cl) and the raw cash. CHOICE: a missing close CARRIES the last mark (a zero day, the move on the next: r15's convention); CHOICE: an exit with
    no close has STOPPED PRINTING and exits at its last mark. The long RECEIVES (CHOICE: booked on the ex-date session itself - no payable-date lag, no tax) the cash dividend per share held on every ex-date session t with e < t <= x (r17_resmom's D* = the amount / the session's split factor on the split-safe basis, the
    raw amount on the raw basis): the entry session's own ex-date is bought ex, the exit session's is received - so the X-rule (exit at X - 1) holds none, NO-X / P + 10 hold X when it falls on or before their exit and carry the ex-day drop in
    the price. -> flat arrays over elements (trade, row e .. x): idx, k (0 = the entry row), rows, G = the gross P&L per $1 of entry notional of that row (price change + cash; 0 on the entry row), div (the cash part), plus per trade ve (exit value
    per $1), stopped, Pe (the entry price), start / end (the element positions)"""
    n = tr.n
    ln = tr.x - tr.e
    cnt = ln + 1
    tot = int(cnt.sum())
    idx = np.repeat(np.arange(n), cnt)
    start = np.cumsum(cnt) - cnt
    k = np.arange(tot) - np.repeat(start, cnt)
    rows = tr.e[idx] + k
    col = tr.col[idx]
    nv = tr.naive[idx]
    P = np.where(nv, W.Cl[rows, col], W.Ac[rows, col])
    Dc = np.where(nv, W.Dr[rows, col], W.Dv[rows, col])
    Dc[k == 0] = 0.0
    valid = np.isfinite(P)
    if n and not valid[start].all():
        raise AssertionError("a trade without an entry close reached the engine")
    last = np.maximum.accumulate(np.where(valid, np.arange(tot), -1)) if tot else np.zeros(0, np.int64)
    Pc = P[last] if tot else P
    Pe = Pc[start][idx] if tot else P
    G = np.zeros(tot)
    if tot > 1:
        with np.errstate(invalid="ignore", divide="ignore"):
            G[1:] = (Pc[1:] - Pc[:-1] + Dc[1:]) / Pe[1:]
    G[k == 0] = 0.0
    end = start + ln
    with np.errstate(invalid="ignore", divide="ignore"):
        ve = Pc[end] / Pc[start] if n else np.zeros(0)
    return SimpleNamespace(idx=idx, k=k, rows=rows, G=G, div=np.where(k >= 1, Dc / np.where(Pe > 0, Pe, 1.0), 0.0) if tot else Dc, ve=ve, stopped=~valid[end] if n else np.zeros(0, bool), Pe=Pc[start] if n else np.zeros(0),
                           start=start, end=end)


def stock_pnl(W, tr, pa, bps):
    """the stock leg at `bps` a side of the notional (entry notional at the entry, the exit value at the exit): daily P&L (T,) booked on the session of each mark / cost, and each trade's total ($)"""
    c, slot, T = bps * 1e-4, SPEC["slot"], W.T
    m = pa.k >= 1
    daily = np.bincount(pa.rows[m], weights=slot * pa.G[m], minlength=T) if m.any() else np.zeros(T)
    daily = daily - np.bincount(tr.e, weights=np.full(tr.n, slot * c), minlength=T) - np.bincount(tr.x, weights=slot * c * pa.ve, minlength=T)
    gross = np.bincount(pa.idx, weights=pa.G, minlength=tr.n)
    return daily, slot * (gross - c - c * pa.ve)


def open_counts(tr, T):
    """positions held per session: rows e .. x of every trade (the entry session through the exit session, as r15 counts them)"""
    d = np.bincount(tr.e, minlength=T + 1) - np.bincount(tr.x + 1, minlength=T + 1)
    return np.cumsum(d)[:T].astype(float)


def round_half_away(a):
    """round to whole contracts, a half away from zero (the prereg: whole MES, 0 when under half a contract). CHOICE: that is read as round-half-away-from-zero, applied symmetrically to a negative notional (a net negative beta = long ES)"""
    a = np.asarray(a, float)
    return np.sign(a) * np.floor(np.abs(a) + 0.5)


def hedge_agg(W, tr):
    """[V5] the hedge AS TRADED: ONE aggregate short ES position. At each session's 16:00 print the ES dollar notional to hedge = the sum over the trades OPEN at that print (entry <= t < exit; CHOICE: a trade is hedged from its entry print, the
    exit print takes it off) of beta_i x $4,000; the contracts n_t = round(notional / (the unadjusted 16:00 print x $5; CHOICE: the contracts are counted on the print as quoted, the P&L runs on the roll-corrected one)) in WHOLE MES (0 when under half a contract; negative = long ES for a net negative beta); the position set at the print of t
    earns -n_t x $5 x (the roll-corrected change to the next print; CHOICE: a session with no print repeats the last, so the move over a hole is earned at the next one); each change in n pays MES_SIDE ($1.4075 = half of 0.363 pt x $5 + $1.00) per contract, booked on the session of the change. -> n (T,), pnl (T,), cost (T,), expo (T,)"""
    T = W.T
    w = tr.beta * SPEC["slot"]
    expo = np.cumsum(np.bincount(tr.e, weights=w, minlength=T + 1) - np.bincount(tr.x, weights=w, minlength=T + 1))[:T]
    lev = np.asarray(W.esR, float) * MES_PT
    with np.errstate(invalid="ignore", divide="ignore"):
        nc = np.where(np.isfinite(lev) & (lev > 0), round_half_away(expo / lev), 0.0)
    pnl = np.zeros(T)
    if T > 1:
        pnl[1:] = np.nan_to_num(-nc[:-1] * MES_PT * (np.asarray(W.esA, float)[1:] - np.asarray(W.esA, float)[:-1]), nan=0.0)
    cost = -MES_SIDE * np.abs(np.diff(nc, prepend=0.0))
    return SimpleNamespace(n=nc, pnl=pnl, cost=cost, expo=expo)


def hedge_exact(W, tr):
    """the TRADE-LEVEL hedge (best 1% of trades, the top contributors, the 20 largest gains): each trade's exact fractional hedge, fixed at its entry print: contracts_i = beta_i x $4,000 / (the entry's unadjusted print x $5) short, held to
    the exit print: P&L = -contracts_i x $5 x (the exit's roll-corrected print - the entry's), ES 0.5 bps of the hedge notional a side (CHOICE: the notional at entry, the contracts' value at the exit print). -> per-trade pnl_i (net of the cost), the
    gross pnl_i, ctr_i, and the same hedge summed to a daily series (T,) (P&L on the sessions after the entry through the exit, the costs on the entry and exit sessions) for the gap against the aggregate whole-MES one"""
    T = W.T
    w = tr.beta * SPEC["slot"]
    esA, esR = np.asarray(W.esA, float), np.asarray(W.esR, float)
    ctr = w / (esR[tr.e] * MES_PT) if tr.n else np.zeros(0)
    gross = -ctr * MES_PT * (esA[tr.x] - esA[tr.e])
    cost_e, cost_x = ES_EXACT_BPS * 1e-4 * np.abs(w), ES_EXACT_BPS * 1e-4 * np.abs(ctr) * MES_PT * esR[tr.x]
    C = np.cumsum(np.bincount(tr.e + 1, weights=ctr, minlength=T + 2) - np.bincount(tr.x + 1, weights=ctr, minlength=T + 2))[:T]
    daily = np.zeros(T)
    if T > 1:
        daily[1:] = np.nan_to_num(-C[1:] * MES_PT * (esA[1:] - esA[:-1]), nan=0.0)
    daily = daily - np.bincount(tr.e, weights=cost_e, minlength=T) - np.bincount(tr.x, weights=cost_x, minlength=T)
    return SimpleNamespace(pnl=gross - cost_e - cost_x, gross=gross, ctr=ctr, daily=daily)


def prepare(W, tr):
    """everything about a trade set that does not depend on the stock's cost: marks, the aggregate hedge, the exact hedge, the positions held"""
    return SimpleNamespace(tr=tr, pa=stock_paths(W, tr), hg=hedge_agg(W, tr), hx=hedge_exact(W, tr), cnt=open_counts(tr, W.T))


def run_bundle(W, bu, bps=COST_BPS):
    """one cell-run at `bps` a side on the stock: x = the cell's daily P&L as it is TRADED (stock + the aggregate whole-MES hedge and its costs) on the stock sessions (T,); x_unhedged = the stock leg alone (the REPORTED unhedged leg);
    x_exact = stock + the exact fractional hedge (the gap against x is reported); pos = the table of trades with the EXACT hedge in each trade's P&L (the trade-level statistics); div_usd = the cash dividends the trades received"""
    tr = bu.tr
    sd, spnl = stock_pnl(W, tr, bu.pa, bps)
    pos = SimpleNamespace(pnl=spnl + bu.hx.pnl, rec=np.arange(tr.n), col=tr.col, side=np.ones(tr.n), sig=np.zeros(tr.n), stock=spnl, hedge=bu.hx.pnl)
    return SimpleNamespace(x=sd + bu.hg.pnl + bu.hg.cost, x_unhedged=sd, x_exact=sd + bu.hx.daily, hedge_agg=bu.hg.pnl + bu.hg.cost, hedge_exact=bu.hx.daily, cnt=bu.cnt, n_pos=tr.n, n_units=tr.n, pos=pos,
                           div_usd=SPEC["slot"] * np.bincount(bu.pa.idx, weights=bu.pa.div, minlength=tr.n), tr=tr)


def stat_of(B, rows, run, lo, hi, series=None):
    """r15's cell statistics on one stretch [lo, hi] of the cell's daily series (series = another daily series on the stock sessions, e.g. the unhedged leg; the positions' table is the run's) -> (stats, the series on #463's index, the
    positions held per row)"""
    xB = D15.to_B(run.x if series is None else series, rows, B.n)
    cB = D15.to_B(run.cnt, rows, B.n)
    return D15.cell_stats(B, xB, cB, lo, hi, run), xB, cB


def sub_run(W, run, lo, hi):
    """the same cell-run with the position table cut to the trades that EXIT in [lo, hi] (a sub-period: trades are counted by exit date); the daily series keeps every row - the statistics cut it by date. CHOICE: the prereg says only 'every cell is also
    reported for' the two periods: the trade counts / trade-level numbers go by EXIT date (as the stretches do), the daily series (ROC, drawdown, years) by SESSION date, so a trade that straddles the boundary is split in the second and whole in the first"""
    dx = np.asarray(W.days).astype("datetime64[ns]")[run.tr.x]
    m = (dx >= np.datetime64(lo)) & (dx <= np.datetime64(hi))
    pos = SimpleNamespace(pnl=run.pos.pnl[m])
    return SimpleNamespace(x=run.x, cnt=run.cnt, n_pos=int(m.sum()), n_units=int(m.sum()), pos=pos)


def judge_cell(st, net10, nul):
    """(a) >= 1,000 trades; (b) WF ROC @ $30k >= 15 and net > 0 at 5 AND at 10 bps a side; (c) WF ROC above the null's 95th percentile (the max over the 2 cells, the registered placebo in time); (d) positive in >= 6 of the 9 July-June
    years and net > 0 without Feb 15 - Apr 30 2020; (e) profitable without its best 1% of DAYS and without its best 1% of TRADES (the trade-level numbers use the exact hedge). (f), the hand audit, is NEVER decided here. A NaN fails every
    comparison it enters"""
    R = RULES
    chk = {f"trades>={R['n']}": st["n_pos"] >= R["n"], f"ROC>={R['roc']:g}": st["roc"] >= R["roc"], "net>0 at 5 bps": (st["net"] > 0) if R["net_pos"] else True,
           "net>0 at 10 bps": (net10 > 0) if R["stress"] else True, "ROC>null p95": (st["roc"] > nul["roc_max"]["p95"]) if R["null"] else True,
           f"positive in >={R['years']} of 9 July-June years": st["years_pos"] >= R["years"], "net>0 without Feb 15 - Apr 30 2020": (st["net_ex2020"] > 0) if R["ex2020"] else True,
           "profitable without its best 1% of days": (st["net_ex_best_days"] > 0) if R["exbest"] else True,
           "profitable without its best 1% of trades": (st["net_ex_best_pos"] > 0) if R["exbest"] else True}
    return {k: bool(v) for k, v in chk.items()}


def registered_verdict(by_rule):
    """[V1] the registered verdict of a cell = its NO-X verdict; the X-rule's is printed beside it and, when the two differ, NO-X wins. by_rule = {rule: PASS bool} -> (registered, the X-rule's, differ)"""
    return bool(by_rule[REGISTERED]), bool(by_rule["X"]), bool(by_rule[REGISTERED]) != bool(by_rule["X"])


def plain_a2(B, xB):
    """[X1] the registered volatility rule for c and the PLAIN book (a REPORTED row now - a2_report is the incremental one over the reference): STAGE A2 (WF), MANAGER #56: #463 + c x the cell, c set by VOLATILITY on 2017-03-01 .. 2019-02-28 (the cell's first two full years) = 25% of #463's daily std over those rows / the cell's, the book at 0.5c and
    2c beside it; 'book_shadow_line' = the plain book at c would clear the draft's old bar, ROC @ $30k >= 98.5005 and Sortino >= 3.816 (reported, no longer a pass). r17_resmom's A2 code, pointed at DIVRUN's window (CHOICE: reused as it is - the rule is the same volatility rule)"""
    with patched(M17, A2_WIN=A2_WIN, A2_TARGET=A2_TARGET, A2_REPORT=A2_REPORT):
        return M17.a2_report(B, xB)
# ------------------------------------------------------------------ [X1] the REFERENCE book (#463 + 0.264 x RES): A2 as an INCREMENTAL report, the drawdown days of MANAGER #70's gate
def raw_sha(data):
    """sha256 of BYTES: the prereg pins the RESMOM line file by the hash of its bytes (no line-ending normalisation - unlike R11.sha_lf, which the text files use)"""
    return hashlib.sha256(data).hexdigest()


def ref_facts_ok(stats, facts=None, tol=None):
    """the reference book's WF numbers (r11_risk.stats: roc, sort, max_dd) against its registered ones, each within its tolerance (CHOICE: both ends inclusive; a NaN fails) -> (the three numbers, {name: ok})"""
    facts, tol = REF_FACTS if facts is None else facts, REF_TOL if tol is None else tol
    got = {"roc": float(stats["roc"]), "sortino": float(stats["sort"]), "max_dd": float(stats["max_dd"])}
    return got, {k: bool(abs(got[k] - facts[k]) <= tol[k]) for k in facts}


def ref_structure(Sx):
    """the reference's drawdown structure on MDL r1's episode rule (r12_mdl.Stretch: the episodes at least 1/3 as deep as the deepest are the qualifying ones, their days from the day after the peak to the trough are the DD days): the number of
    qualifying episodes, of all episodes, the DD days, the DD weeks, the deepest depth and the DD days by calendar year"""
    yr = Sx.dates.year.to_numpy()
    return {"episodes": int(len(Sx.qual)), "all_episodes": int(len(Sx.episodes)), "days": int(Sx.n_dd_days), "weeks": int(Sx.n_dd_weeks), "deepest": float(Sx.episodes[0]["depth"]) if Sx.episodes else float("nan"),
            "by_year": {int(y): int((Sx.dd & (yr == y)).sum()) for y in sorted(set(yr[Sx.dd]))}}


def ref_build(B, res_wf):
    """the reference book on RES's WF daily P&L (one value per row of #463's WF index, in order): raw (nb,) = #463 + 0.264 x RES on the WF rows and NaN everywhere else (CHOICE: a read past the stretch fails loudly instead of using a made-up number),
    res (nb,) the same way, S = r12_mdl.Stretch of it (the very code path r15 / r17 use for #463), stats = r11_risk.stats of the WF rows, facts / ok = those against the registered numbers, structure = ref_structure(S), rows = the WF rows"""
    k = np.flatnonzero(B.mask(WF0, PRE_END))
    res_wf = np.asarray(res_wf, float)
    assert res_wf.shape == (len(k),), (res_wf.shape, len(k))
    raw = np.full(B.n, np.nan)
    raw[k] = np.asarray(B.raw, float)[k] + REF_W * res_wf
    res = np.full(B.n, np.nan)
    res[k] = res_wf
    S_ = M12.Stretch(raw, B.index, None, WF0, PRE_END)
    st = R11.stats(raw[k], B.index[k])
    facts, ok = ref_facts_ok(st)
    return SimpleNamespace(raw=raw, res=res, S=S_, stats=st, facts=facts, ok=ok, structure=ref_structure(S_), rows=k, path=None, sha=None, n_rows=int(len(k)), max_book_diff=0.0)


def ref_load(B, path=None, check_facts=None):
    """[X1] RES's registered WF daily P&L -> the REFERENCE book. Refuses (nothing computed, lockbox NOT read) unless: the file is on file; the sha256 of its BYTES is the registered one; it has the columns date, book_mtm, RES, RAW with readable, strictly
    increasing dates and finite numbers; no date is on / after the cut; its dates ARE #463's WF index row for row (every row of the index in [2016-07-01, 2025-06-29], in order, none more); its book_mtm is #463's own daily P&L on every one of them
    (CHOICE: to REF_BOOK_ATOL dollars - the file is text and may be rounded); and, when check_facts (default CHECK_BOOK), the reference #463 + 0.264 x RES reproduces its registered WF ROC @ $30k 120.82 (+-0.01), Sortino 3.916 (+-0.001) and worst
    drawdown $36,526 (+-$1). The file is read once: the hash and the parse are of the same bytes"""
    path = REF_CSV if path is None else path
    check = CHECK_BOOK if check_facts is None else check_facts
    tail = "(nothing computed, lockbox NOT read)"
    if not os.path.exists(path):
        refuse(f"refused: the RESMOM line file {path} is not on file - the REFERENCE book (#463 + {REF_W} x RES) cannot be built {tail}")
    with open(path, "rb") as f:
        data = f.read()
    sha = raw_sha(data)
    if sha != REF_SHA:
        refuse(f"refused: the RESMOM line file {os.path.basename(path)} sha256 {sha} is not the registered {REF_SHA} - the line changed after it was registered {tail}")
    try:
        df = pd.read_csv(io.BytesIO(data), encoding="utf-8-sig")                              # CHOICE: a byte-order mark, if the exporter wrote one, is not part of the first column's name
        df.columns = [str(c).strip() for c in df.columns]
    except Exception as e:                                                                    # a file with the registered hash that is not a csv cannot happen; the refusal names it all the same
        refuse(f"refused: the RESMOM line file cannot be read as a csv ({type(e).__name__}) {tail}")
    miss = [c for c in REF_COLS if c not in df.columns]
    if miss:
        refuse(f"refused: the RESMOM line file lacks the column(s) {miss} (columns: {', '.join(REF_COLS)}) {tail}")
    dates = pd.DatetimeIndex(pd.to_datetime(df["date"].astype(str).str.strip().str[:10], format="%Y-%m-%d", errors="coerce"))
    if dates.isna().any() or not (dates.is_monotonic_increasing and dates.is_unique):
        refuse(f"refused: the RESMOM line file's dates are not readable, strictly increasing days {tail}")
    assert_cut("the RESMOM line file", dates, S.LB0)                                          # [13] nothing on / after the cut, whatever the file says
    ix, want = B.index.get_indexer(dates), np.flatnonzero(B.mask(WF0, PRE_END))
    if (ix < 0).any() or len(ix) != len(want) or not np.array_equal(ix, want):
        span = f"{B.index[want[0]]:%Y-%m-%d} .. {B.index[want[-1]]:%Y-%m-%d}" if len(want) else "none"
        refuse(f"refused: the RESMOM line file's {len(dates):,} dates are not #463's WF index row for row (the index has {len(want):,} rows in {span}; {int((ix < 0).sum())} of the file's dates are not on it) {tail}")
    mtm, res, rawc = (pd.to_numeric(df[c], errors="coerce").to_numpy(float) for c in ("book_mtm", "RES", "RAW"))
    if not (np.isfinite(mtm).all() and np.isfinite(res).all() and np.isfinite(rawc).all()):
        refuse(f"refused: the RESMOM line file has a missing or non-finite number in book_mtm / RES / RAW {tail}")
    diff = np.abs(mtm - np.asarray(B.raw, float)[want])
    if diff.max() > REF_BOOK_ATOL:
        j = int(np.argmax(diff))
        refuse(f"refused: the RESMOM line file's book_mtm is not #463's own daily P&L (it differs by ${diff.max():,.2f} on {B.index[want[j]]:%Y-%m-%d}; the tolerance is ${REF_BOOK_ATOL}) - the file was written from another #463 {tail}")
    ref = ref_build(B, res)
    ref.path, ref.sha, ref.n_rows, ref.max_book_diff = path, sha, int(len(want)), float(diff.max())
    if check and not all(ref.ok.values()):
        refuse(f"refused: the REFERENCE book (#463 + {REF_W} x RES) does not reproduce its registered WF numbers - ROC@30k {ref.facts['roc']:.2f} (registered {REF_FACTS['roc']} +-{REF_TOL['roc']}), Sortino "
               f"{ref.facts['sortino']:.3f} ({REF_FACTS['sortino']} +-{REF_TOL['sortino']}), worst drawdown ${ref.facts['max_dd']:,.0f} (${REF_FACTS['max_dd']:,.0f} +-${REF_TOL['max_dd']:.0f}) {tail}")
    return ref


def ref_record(ref):
    """the reference as Stage A's file keeps it: which file (name, sha256, the pinned one), its rows, the weight of RES, its numbers against the registered ones and the drawdown structure the #70 gate uses"""
    return {"file": None if ref.path is None else os.path.basename(ref.path), "sha256": ref.sha, "pinned_sha256": REF_SHA, "rows": ref.n_rows, "weight_of_RES": REF_W, "max_abs_book_mtm_difference": ref.max_book_diff, "facts": ref.facts,
            "registered": REF_FACTS, "tolerance": REF_TOL, "reproduced": {k: bool(v) for k, v in ref.ok.items()}, "structure": ref.structure}


def print_reference(ref):
    f, g = ref.facts, ref.structure
    name, sha = ("(no file)", "-") if ref.path is None else (os.path.basename(ref.path), ref.sha[:16] + "...")
    print(f"REFERENCE book [X1] = #463 + {REF_W} x RES (RESMOM r1's registered WF line; {name} sha256 {sha} is the registered file, its {ref.n_rows:,} dates are #463's WF index row for row, its book_mtm equals "
          f"#463's own daily P&L to ${ref.max_book_diff:.4f}): WF ROC@30k {f['roc']:.2f} Sortino {f['sortino']:.3f} worst drawdown ${f['max_dd']:,.0f} (registered {REF_FACTS['roc']} / {REF_FACTS['sortino']} / ${REF_FACTS['max_dd']:,.0f}: "
          f"{'reproduced' if all(ref.ok.values()) else 'NOT reproduced - only the smoke runs on that'})")
    print(f"  the reference's drawdown days, MDL r1's episode rule (the episodes at least 1/3 as deep as the deepest): {g['episodes']} qualifying episodes of {g['all_episodes']}, {g['days']} DD days, {g['weeks']} DD weeks, deepest "
          f"${g['deepest']:,.0f}, DD days by calendar year {g['by_year']} (#463 alone: {D15.DD_REF['episodes']} episodes, {D15.DD_REF['days']} DD days) - the basis of the #70 gate's DO, for the cell and for its null")


def ref_at(B, ref, xB, c, lo=WF0, hi=PRE_END):
    """REFERENCE + c x the cell on [lo, hi] (the rows of #463's index): ROC @ $30k / Sortino / net / max drawdown (r11_risk.stats, the house yardstick; NaN, never an exception, under 2 rows)"""
    k = B.mask(lo, hi)
    s = R11.stats((np.asarray(ref.raw, float) + c * np.asarray(xB, float))[k], B.index[k]) or {}
    nan = float("nan")
    return {"c": float(c), "roc": s.get("roc", nan), "sortino": s.get("sort", nan), "net": s.get("net", nan), "max_dd": s.get("max_dd", nan)}


def incremental_pass(at, r):
    """[X1] an incremental pass: the book's ROC @ $30k AND its Sortino BOTH above the reference's own (strictly - equal is not above; a NaN passes nothing). at = ref_at's record, r = the reference's r11_risk.stats"""
    return bool(at["roc"] > r["roc"] and at["sortino"] > r["sort"])


def a2_report(B, xB, ref):
    """STAGE A2 (WF) - a REPORT, never a pass route [X1]: the REFERENCE book + c x the cell against the reference. c stays the registered volatility rule (r17_resmom's A2 code on 2017-03-01 .. 2019-02-28: c = 25% x the std of #463's daily P&L / the
    cell's, every index row of the window - against #463's std, not the reference's); 0.5c and 2c are reported beside it. 'incremental_pass' = ROC @ $30k and Sortino both above the reference's (it opens a forward BOOK shadow line, nothing more, and
    MANAGER #70's gate then applies); 'book_shadow_line' is the same flag. The plain #463 + c x the cell book is a REPORTED row (plain_463; old_bar_cleared = it would have cleared the draft's old bar 98.5005 / 3.816)"""
    plain = plain_a2(B, xB)
    r = ref.stats
    nan = float("nan")
    out = {k: plain[k] for k in ("window", "rows", "target", "std_book", "std_cell", "c")}
    out["reference"] = {"roc": float(r["roc"]), "sortino": float(r["sort"]), "net": float(r["net"]), "max_dd": float(r["max_dd"]), "weight_of_RES": REF_W}
    out["needs"] = {"roc": float(r["roc"]), "sortino": float(r["sort"])}
    out["plain_463"] = {k: plain.get(k) for k in ("c", "roc", "sortino", "net", "max_dd", "at_half_c", "at_double_c")}
    out["plain_463"].update({"old_bar": {"roc": RULES["a2_roc"], "sortino": RULES["a2_sort"]}, "old_bar_cleared": bool(plain["book_shadow_line"])})
    c = plain["c"]
    if not (np.isfinite(c) and c > 0):
        out.update({"roc": nan, "sortino": nan, "net": nan, "max_dd": nan, "roc_gain": nan, "sortino_gain": nan, "incremental_pass": False, "book_shadow_line": False, "at_half_c": None, "at_double_c": None,
                    "error": plain.get("error", "no c: the cell has no spread over the window")})
        return out
    at = ref_at(B, ref, xB, c)
    ok = incremental_pass(at, r)
    out.update({"roc": at["roc"], "sortino": at["sortino"], "net": at["net"], "max_dd": at["max_dd"], "roc_gain": at["roc"] - float(r["roc"]), "sortino_gain": at["sortino"] - float(r["sort"]), "incremental_pass": ok, "book_shadow_line": ok,
                "at_half_c": ref_at(B, ref, xB, A2_REPORT[0] * c), "at_double_c": ref_at(B, ref, xB, A2_REPORT[1] * c)})
    return out


# ------------------------------------------------------------------ the nulls: PLACEBO IN TIME (registered) and RANDOM NAMES (reported second null)
def series_from_entries(W, dix, col, E, h, beta, D, bps=COST_BPS):
    """the cell's daily P&L (D, T) for D independent sets of trades given as flat arrays - the null engine, all draws of a block at once: draw index dix, name col, entry session E, hold h sessions (exit E + h), beta at the entry. Each trade
    is $4,000 at the entry close valued at every close through the exit on the split-safe close (the callers guarantee a finite close on every session and NO ex-date in the window, so there is no cash and no carry), 5 bps of the notional at the
    entry and of the exit value at the exit, and the draw's own AGGREGATE whole-MES hedge exactly as hedge_agg sizes, trades and charges it. The selftest proves it equals the cell engine on a dividend-free trade set"""
    T, slot, c = W.T, SPEC["slot"], bps * 1e-4
    Ac = W.Ac
    Pe = Ac[E, col]
    acc = np.zeros(D * T)
    for k in range(1, int(h.max()) + 1 if len(h) else 1):
        s = h >= k
        r = E[s] + k
        acc += np.bincount(dix[s] * T + r, weights=slot * (Ac[r, col[s]] - Ac[r - 1, col[s]]) / Pe[s], minlength=D * T)
    acc -= np.bincount(dix * T + E, weights=np.full(len(E), slot * c), minlength=D * T)
    acc -= np.bincount(dix * T + E + h, weights=slot * c * Ac[E + h, col] / Pe, minlength=D * T)
    w = beta * slot
    dd = np.bincount(dix * (T + 1) + E, weights=w, minlength=D * (T + 1)) - np.bincount(dix * (T + 1) + E + h, weights=w, minlength=D * (T + 1))
    expo = np.cumsum(dd.reshape(D, T + 1), axis=1)[:, :T]
    lev = np.asarray(W.esR, float) * MES_PT
    with np.errstate(invalid="ignore", divide="ignore"):
        nc = np.where(np.isfinite(lev) & (lev > 0), round_half_away(expo / lev), 0.0)
    hp = np.zeros((D, T))
    if T > 1:
        hp[:, 1:] = np.nan_to_num(-nc[:, :-1] * MES_PT * (np.asarray(W.esA, float)[1:] - np.asarray(W.esA, float)[:-1])[None, :], nan=0.0)
    return acc.reshape(D, T) + hp - MES_SIDE * np.abs(np.diff(nc, axis=1, prepend=0.0))


def clean_window(W, ctx, col, E, h):
    """a window E .. E + h of a name is clean when the name has a close on every session of it, NO ex-date of it (a cash dividend regular or special, a spin-off, a stock dividend; ex_matrices' exc) touches E .. E + h (CHOICE: the entry session included - the safe side), no hygiene event
    (registered split, gap scan, TBIS, a +-50% raw gap, a special dividend, a spin-off) falls on E - 5 .. E + h (the same flags that remove a real trade, [V3]) and the name has a beta at E (the hedge rule). Arrays of (name, entry, hold) -> bool"""
    x = E + h
    ok = (ctx.finc[x + 1, col] - ctx.finc[E, col]) == (h + 1)
    ok &= (ctx.exc[x + 1, col] - ctx.exc[E, col]) == 0
    ok &= (ctx.flagcs[x + 1, col] - ctx.flagcs[np.maximum(E - SPEC["hyg_lead"], 0), col]) == 0
    ok &= ctx.bok[E, col]
    return ok


def placebo_entries(W, ctx, rng, tr, D):
    """[V2] the REGISTERED null, the entries of D draws: every real trade keeps its name, its holding length h and its hedge rule but moves to an entry session drawn UNIFORMLY from E1 + 11 .. P - 26 - h (CHOICE: counted in SESSIONS, the prereg's 'E1 + 11' does not say sessions or days: the middle of the same
    quarter, after the previous ex-date's aftermath and ending before the run-up window P - 25); a placebo window that touches any ex-date of the stock (clean_window) is REDRAWN, up to 20 tries (CHOICE: 20 draws in all, the first included), else the trade is LEFT OUT of that draw (counted).
    A trade with no such session at all is left out of every draw. -> E (n trades, D) int64, -1 = left out"""
    N = tr.n
    h = tr.x - tr.e
    lo = tr.e1r + SPEC["pl_lo"]
    span = (tr.p - SPEC["pl_margin"] - h) - lo + 1
    E = np.full((N, D), -1, np.int64)
    todo = np.broadcast_to((span >= 1)[:, None], (N, D)).copy()
    for _ in range(SPEC["pl_tries"]):
        ii, dd = np.nonzero(todo)
        if not len(ii):
            break
        cand = lo[ii] + np.minimum((rng.random(len(ii)) * span[ii]).astype(np.int64), span[ii] - 1)
        ok = clean_window(W, ctx, tr.col[ii], cand, h[ii])
        E[ii[ok], dd[ok]] = cand[ok]
        todo[ii[ok], dd[ok]] = False
    return E


def null_stats(S12, Sref, acc, rows, nb):
    """a block of null series (D, T) on the stock sessions -> (the WF ROC @ $30k of every draw, on #463's stretch; the DO of every draw against Sref's drawdown days - the REFERENCE book's [X1] -, NaN without a stretch)"""
    roc = D15.null_cell(S12, acc, rows, nb)[0]
    return roc, (D15.null_cell(Sref, acc, rows, nb)[2] if Sref is not None else np.full(len(roc), np.nan))


def placebo_null(W, ctx, tr, nreps, key, S12, rows, nb, bps=COST_BPS, block=10, Sref=None):
    """the placebo-in-time null of one (cell, exit rule): the WF ROC @ $30k of nreps draws (CHOICE: 'its hedge rule' = beta x $4,000 with the beta known at the PLACEBO entry - the rule re-applied on the new date, not the real trade's beta carried over) -> (roc (nreps,), left_out (nreps,) trades left out of each draw, never_drawn = trades with no placebo session at all, do (nreps,) = each draw's DO against Sref, the REFERENCE book's drawdown days [X1] (NaN without one)). CHOICE: its own random stream
    per (cell, rule, reading), key = [the registered seed, cell, rule, reading] (the prereg gives only the seed); the draws are generated and costed in blocks so the (draw x trade x session) arrays stay small"""
    rng = np.random.default_rng(key)
    N = tr.n
    h = tr.x - tr.e
    roc, dos, left = [], [], np.zeros(nreps)
    for b0 in range(0, nreps, block):
        D = min(block, nreps - b0)
        E = placebo_entries(W, ctx, rng, tr, D)
        ii, dd = np.nonzero(E >= 0)
        Ev = E[ii, dd]
        acc = series_from_entries(W, dd, tr.col[ii], Ev, h[ii], ctx.beta[Ev, tr.col[ii]], D, bps)
        r_, d_ = null_stats(S12, Sref, acc, rows, nb)
        roc.append(r_)
        dos.append(d_)
        left[b0:b0 + D] = N - (E >= 0).sum(axis=0)
    span = (tr.p - SPEC["pl_margin"] - h) - (tr.e1r + SPEC["pl_lo"]) + 1
    cat = lambda a: np.concatenate(a) if a else np.zeros(0)
    return cat(roc), left, int((span < 1).sum()), cat(dos)


def random_name_pool(W, ctx, tr):
    """[V2] the names that may replace each trade in the REPORTED second null: a universe PAYER at the trade's entry close (CHOICE: the DDW r1 top-500 rule at the entry close + a regular quarterly cycle at that close, ctx.pay_p - the prereg names no payer rule for the null) whose OWN
    window P' - 25 .. X' does not overlap the hold e .. x (X' > e always - the name's latest regular ex-date is on or before e - so overlap means P' - 25 <= x), with a beta at e, a close on every session of the hold, no ex-date of its own and no
    hygiene event inside it (CHOICE: the replacement must be as clean over the hold as a placebo window is). -> (flat names, offset per trade, count per trade)"""
    lead, own = SPEC["hyg_lead"], SPEC["own_lead"]
    base, flat, off, cnt, pos = {}, [], np.zeros(tr.n, np.int64), np.zeros(tr.n, np.int64), 0
    for i in range(tr.n):
        e, x = int(tr.e[i]), int(tr.x[i])
        if e not in base:
            base[e] = np.flatnonzero((ctx.pay_p[e] >= 0) & W.U[e + 1] & ctx.bok[e] & np.isfinite(W.Ac[e]))
        pl = base[e]
        m = (ctx.pay_p[e, pl].astype(np.int64) - own) > x
        m &= (ctx.exc[x + 1, pl] - ctx.exc[e, pl]) == 0
        m &= (ctx.flagcs[x + 1, pl] - ctx.flagcs[max(e - lead, 0), pl]) == 0
        m &= (ctx.finc[x + 1, pl] - ctx.finc[e, pl]) == (x - e + 1)
        sel = pl[m]
        off[i], cnt[i] = pos, len(sel)
        flat.append(sel)
        pos += len(sel)
    return (np.concatenate(flat) if flat else np.zeros(0, np.int64)), off, cnt


def draw_picks(rng, flat, off, cnt, D):
    """one uniform pick per (trade, draw) from the trade's own eligible names (random_name_pool's ragged arrays): (n trades, D) int64 names, -1 where a trade has no eligible name"""
    N = len(cnt)
    u = rng.random((N, D))
    has = cnt > 0
    ix = off[:, None] + np.minimum((u * cnt[:, None]).astype(np.int64), np.maximum(cnt[:, None] - 1, 0))
    if not len(flat):
        return np.full((N, D), -1, np.int64)
    return np.where(has[:, None], flat[np.where(has[:, None], ix, 0)], -1)


def random_name_null(W, ctx, tr, nreps, key, S12, rows, nb, bps=COST_BPS, block=10, pool=None, Sref=None):
    """the second null (REPORTED, never a pass route): at the SAME entry and exit sessions every real trade is replaced by a random eligible name (random_name_pool, uniform) with the same hedge rule (the new name's beta) and costs. -> (roc
    (nreps,), left_out (nreps,) trades with no eligible name, never_drawn, do (nreps,) as the placebo's)"""
    rng = np.random.default_rng(key)
    N = tr.n
    flat, off, cnt = random_name_pool(W, ctx, tr) if pool is None else pool
    h = tr.x - tr.e
    roc, dos, left = [], [], np.zeros(nreps)
    for b0 in range(0, nreps, block):
        D = min(block, nreps - b0)
        pick = draw_picks(rng, flat, off, cnt, D)
        ii, dd = np.nonzero(pick >= 0)
        col = pick[ii, dd]
        E = tr.e[ii]
        acc = series_from_entries(W, dd, col, E, h[ii], ctx.beta[E, col], D, bps)
        r_, d_ = null_stats(S12, Sref, acc, rows, nb)
        roc.append(r_)
        dos.append(d_)
        left[b0:b0 + D] = N - (pick >= 0).sum(axis=0)
    cat = lambda a: np.concatenate(a) if a else np.zeros(0)
    return cat(roc), left, int((cnt == 0).sum()), cat(dos)


def null_summary(per_cell, per_cell_do=None):
    """per_cell {cell: ROC @ $30k of every draw} -> the statistic = the MAX over the 2 cells per draw -> p5 / p50 / p95 (and each cell's own, for the report). per_cell_do {cell: the DO of every draw against the REFERENCE book's drawdown days [X1]}
    -> the same for the DO: 'do_ref_max' = the MAX over the 2 cells per draw, 'do_ref_by_cell' (MANAGER #70's gate basis for the cell's null)"""
    roc = np.fmax.reduce(np.vstack([per_cell[c] for c in CELLS]), axis=0)
    mk = lambda a: {"p5": D15.pctl(a, 5), "p50": D15.pctl(a, 50), "p95": D15.pctl(a, 95), "finite": int(np.isfinite(a).sum())}
    out = {"draws": int(len(roc)), "seed": SEED, "roc_max": mk(roc), "by_cell": {c: mk(per_cell[c]) for c in CELLS}}
    if per_cell_do is not None:
        do = np.fmax.reduce(np.vstack([per_cell_do[c] for c in CELLS]), axis=0)
        out.update({"do_ref_max": mk(do), "do_ref_by_cell": {c: mk(per_cell_do[c]) for c in CELLS}})
    return out


# ------------------------------------------------------------------ the event-time path [V4] (printed BEFORE any cell statistic)
def event_path(W, tr):
    """[V4] the hedged, cost-free MEAN ABNORMAL RETURN per session, in event time on the P axis (CHOICE: the addendum's [V4] 'from P - 20 to X - 1' is read on the P axis, each event running to its OWN X - 1; the draft's REPORTED paragraph says 'X - 25 to X + 5', an X axis that is NOT printed; CHOICE: abnormal = the total return less the trade's ENTRY beta x ES, on the R20 entry set because it starts at P - 20): for every R20 trade of the X-rule whose X is known (kind 0: X within P + 10, so the path ends at the trade's OWN last cum-dividend close X - 1;
    the late / missing-X trades are counted apart), the session P + tau (tau = -20 .. +10) contributes  r - beta x ES  where r = the split-safe TOTAL daily return and beta the trade's entry beta (r17_resmom's W.Rd; no cost, no
    ex-day because the path stops at X - 1), an ES-hole session contributes nothing. Means are over the trades that have a value on that session (N per tau); by July-June year of P. Also the mean over trades of the SUM of the path P - 20 .. X - 1
    and the part of it in X - 2 .. X - 1 (a gain that sits wholly there is the ex-day tax trade, a different effect). Returns bps"""
    lo_t, hi_t = SPEC["tau_lo"], SPEC["tau_hi"]
    taus = np.arange(lo_t, hi_t + 1)
    m = tr.kind == 0
    p, x, col, beta = tr.p[m], tr.x[m], tr.col[m], tr.beta[m]
    T = W.T
    rows_ = p[:, None] + taus[None, :]
    rc = np.clip(rows_, 0, T - 1)
    valid = (rows_ >= 0) & (rows_ <= T - 1) & (rows_ <= x[:, None])
    with np.errstate(invalid="ignore"):
        A = np.where(valid, np.asarray(W.Rd, float)[rc, col[:, None]] - beta[:, None] * np.asarray(W.es.ret, float)[rc], np.nan)
    yr = jyear(np.asarray(W.days)[np.clip(p, 0, T - 1)]) if len(p) else np.zeros(0, int)

    def line(sel):
        a = A[sel]
        n = np.isfinite(a).sum(axis=0)
        with np.errstate(invalid="ignore"):
            mean = np.where(n > 0, np.nansum(a, axis=0) / np.maximum(n, 1), np.nan) * 1e4
        return mean, n
    mean, n = line(np.ones(len(p), bool))
    tot = np.nansum(A, axis=1) * 1e4
    j1 = np.clip(x - p - lo_t, 0, len(taus) - 1)
    ar = np.arange(len(p))
    last2 = (np.nan_to_num(A[ar, j1]) + np.nan_to_num(A[ar, np.clip(j1 - 1, 0, None)])) * 1e4
    by = {int(y): line(yr == y) for y in sorted(set(yr.tolist()))}
    cum = np.nancumsum(mean)
    return SimpleNamespace(taus=taus, mean_bps=mean, n=n, by_year={y: {"mean_bps": a_, "n": b_} for y, (a_, b_) in by.items()}, cum_bps=cum, trades=int(len(p)), late_or_missing_x_trades=int((~m).sum()),
                           total_mean_bps=float(tot.mean()) if len(p) else float("nan"), last2_mean_bps=float(last2.mean()) if len(p) else float("nan"),
                           last2_share=float(last2.mean() / tot.mean()) if len(p) and tot.mean() != 0 else float("nan"))


def print_path(pth, label=""):
    t = pth.taus
    print(f"EVENT-TIME PATH [V4]{label} - the hedged, cost-free mean abnormal return per session, bps (r - beta x ES; the P axis: session P + tau; each event runs from P - 20 to its OWN X - 1; the R20 entry set, the X-rule trades whose X is "
          f"within P + 10: {pth.trades:,} events, {pth.late_or_missing_x_trades:,} more have X late or missing and are not in it) - printed BEFORE any cell statistic:")
    print("  tau      " + " ".join(f"{int(v):>5d}" for v in t))
    print("  all      " + " ".join(f"{v:>5.1f}" if np.isfinite(v) else "    ." for v in pth.mean_bps))
    print("  N        " + " ".join(f"{int(v):>5d}" for v in pth.n))
    for y, d in pth.by_year.items():
        print(f"  {y}-{(y + 1) % 100:02d}  " + " ".join(f"{v:>5.1f}" if np.isfinite(v) else "    ." for v in d["mean_bps"]) + f"   (N {int(d['n'].max()) if len(d['n']) else 0})")
    print(f"  the path P - 20 .. X - 1 sums to a mean of {pth.total_mean_bps:+.1f} bps a trade; {pth.last2_mean_bps:+.1f} bps of it ({pth.last2_share:+.0%}) sits in X - 2 .. X - 1 "
          "(a gain wholly there is the ex-day tax trade, a different effect)")


# ------------------------------------------------------------------ one reading of Stage A: entry sets -> trade sets -> cells -> stress rows -> nulls -> checks -> A2
def entry_sets(W, ctx):
    return {c: entry_set(W, ctx, KS[c]) for c in CELLS}


def gap_report(W, run, lo, hi):
    """the daily gap between the hedge AS TRADED (aggregate, whole MES) and the exact fractional one over a stretch: the two hedges' nets, the sum of the gap (traded - exact) and the worst day"""
    m = np.asarray((W.days >= lo) & (W.days <= hi))
    g = (run.hedge_agg - run.hedge_exact)[m]
    j = int(np.argmax(np.abs(g))) if len(g) else 0
    return {"hedge_as_traded_net": float(run.hedge_agg[m].sum()), "hedge_exact_net": float(run.hedge_exact[m].sum()), "gap_sum": float(g.sum()), "worst_day": f"{W.days[m][j]:%Y-%m-%d}" if len(g) else None,
            "worst_day_gap": float(g[j]) if len(g) else float("nan"), "days": int(m.sum())}


def unhedged_run(run):
    return SimpleNamespace(x=run.x_unhedged, cnt=run.cnt, n_pos=run.n_pos, n_units=run.n_units, pos=SimpleNamespace(pnl=run.pos.stock), tr=run.tr)


def evaluate(W, ctx, B, S12, ref, rows, reading, nreps, vcode=0, full=False, es=None):
    """one reading of Stage A on the WF stretch, EVERY cell under EVERY exit rule on the cells' shared entry sets. reading 'registered' = a trade flagged inside its hold is REMOVED (from the cell and the null); 'naive' = it is kept at its
    naive raw P&L [V3]; both run the same code, so a flip between them is the hygiene's doing. ref = the REFERENCE book [X1] (#463 + 0.264 x RES): A2 is the incremental report over it and the DO of the cell - and of its null - is measured against
    ITS drawdown days (S12 = #463's own stretch: the MDL map point of the reports). Every cell also carries the 0 bps cost row [X2] (CHOICE: the STOCK's cost taken to 0 - the ES hedge keeps its own costs, nothing else moves). nreps > 0 draws the registered null (the placebo in time) for the X-rule and for NO-X (vcode picks the random
    streams); full = also the reports' rows (the unhedged leg, the hedge leg, the sub-periods, the hedge gap, the random-name null). -> (summary {rule: {cell: ...}}, objects)"""
    lo, hi = WF0, PRE_END
    es = es or entry_sets(W, ctx)
    summ, objs = {r: {} for r in EXITS}, {}
    wf = np.asarray((W.days >= lo) & (W.days <= hi))
    for rule in EXITS:
        for cell in CELLS:
            tr = trade_set(W, ctx, es[cell], rule, reading, lo, hi)
            bu = prepare(W, tr)
            base = run_bundle(W, bu)
            st, xB, cB = stat_of(B, rows, base, lo, hi)
            c = {"base": st, "cost0": stat_of(B, rows, run_bundle(W, bu, 0.0), lo, hi)[0], "stress": {f"{b:g} bps": stat_of(B, rows, run_bundle(W, bu, b), lo, hi)[0] for b in STRESS_BPS},
                 "seat": D15.seat_measure(S12, xB), "seat_ref": D15.seat_measure(ref.S, xB), "A2": a2_report(B, xB, ref)}
            if full:
                c["unhedged"] = stat_of(B, rows, unhedged_run(base), lo, hi)[0]
                c["hedge_leg"] = stat_of(B, rows, hedge_leg_run(base), lo, hi)[0]
                c["hedge_gross"], c["hedge_costs"] = float(bu.hg.pnl[wf].sum()), float(bu.hg.cost[wf].sum())
                c["sub"] = {lab: stat_of(B, rows, sub_run(W, base, a, b), a, b)[0] for lab, a, b in SUBPERIODS}
                c["hedge_gap"] = gap_report(W, base, lo, hi)
                c["hedge_contracts"] = {"max_abs": float(np.abs(bu.hg.n[wf]).max()) if tr.n else 0.0, "days_with_a_position": int((bu.hg.n != 0).sum()), "changes": int((np.diff(bu.hg.n, prepend=0.0) != 0).sum())}
            summ[rule][cell] = c
            objs[(rule, cell)] = SimpleNamespace(tr=tr, bu=bu, run=base, xB=xB)
    nul = {}
    if nreps:
        for rule in NULL_EXITS:
            qr = EXITS.index(rule)
            pc, pdo = {}, {}
            for q, cell in enumerate(CELLS):
                roc, left, never, do = placebo_null(W, ctx, objs[(rule, cell)].tr, nreps, [SEED, q, qr, 10 * vcode + 1], S12, rows, B.n, Sref=ref.S)
                pc[cell], pdo[cell] = roc, do
                summ[rule][cell]["placebo"] = {"trades_left_out_per_draw_mean": float(left.mean()), "trades_left_out_per_draw_max": float(left.max()), "trades_with_no_placebo_session": never, "trades": int(objs[(rule, cell)].tr.n)}
            nul[rule] = null_summary(pc, pdo)
            if full:
                rn, rdo = {}, {}
                for q, cell in enumerate(CELLS):
                    roc, left, never, do = random_name_null(W, ctx, objs[(rule, cell)].tr, nreps, [SEED, q, qr, 10 * vcode + 2], S12, rows, B.n, Sref=ref.S)
                    rn[cell], rdo[cell] = roc, do
                    real = summ[rule][cell]["base"]["roc"]
                    summ[rule][cell]["random_name_null"] = {"roc_p5": D15.pctl(roc, 5), "roc_p50": D15.pctl(roc, 50), "roc_p95": D15.pctl(roc, 95), "real_roc_percentile": float(100.0 * np.mean(roc < real)) if len(roc) else float("nan"),
                                                           "trades_left_out_per_draw_mean": float(left.mean()), "trades_with_no_eligible_name": never}
                nul[rule]["random_names"] = null_summary(rn, rdo)
    for rule in EXITS:
        for cell in CELLS:
            c = summ[rule][cell]
            g = {"basis": "the REFERENCE book's drawdown days (MDL r1's episode rule)", "episodes": ref.structure["episodes"], "dd_days": ref.structure["days"], "DO": c["seat_ref"]["DO"], "rho_dd": c["seat_ref"]["rho_dd"]}
            if rule in nul:                                                              # [X1] MANAGER #70's gate basis: the cell's DO beside its null's, both on the reference's drawdown days (no pass is decided here)
                p = nul[rule]["do_ref_max"]
                g.update({"null_do_p5": p["p5"], "null_do_p50": p["p50"], "null_do_p95": p["p95"], "DO_above_null_p95": bool(c["seat_ref"]["DO"] > p["p95"])})
            c["gate70"] = g
            if rule in nul:
                c["checks"] = judge_cell(c["base"], c["stress"]["10 bps"]["net"], nul[rule])
                c["PASS"] = bool(all(c["checks"].values()))
            elif rule == "P10":                                                          # REPORTED: no registered null for P + 10 (see NULL_EXITS); the checks that need none
                ck = judge_cell(c["base"], c["stress"]["10 bps"]["net"], {"roc_max": {"p95": float("-inf")}})
                c["checks_without_null"] = {k: v for k, v in ck.items() if k != "ROC>null p95"}
                c["PASS"] = None
    return {"reading": reading, "cells": summ, "null": nul}, SimpleNamespace(es=es, objs=objs)


# ------------------------------------------------------------------ the reports (never a pass route)
def trade_rows(W, ctx, run):
    """per-trade arrays of a cell-run (registered rows): symbol, entry / exit dates, the exact-hedge P&L, its stock and hedge parts, the cash received, the P&L in bps of the $4,000, the yield (CHOICE: the E1 dividend over the entry close, both on the split-safe
    basis: the amount / the E1 session's factor over the split-safe entry close)"""
    tr, ev = run.tr, ctx.ev
    with np.errstate(invalid="ignore", divide="ignore"):
        yld = (ev.amt1[tr.ev] / W.F[ev.e1_row[tr.ev], tr.col]) / W.Ac[tr.e, tr.col]
    return SimpleNamespace(sym=W.syms[tr.col], entry=np.asarray(W.days)[tr.e], exit=np.asarray(W.days)[tr.x], pnl=run.pos.pnl, stock=run.pos.stock, hedge=run.pos.hedge, div=run.div_usd,
                           bps=1e4 * run.pos.pnl / SPEC["slot"], yld=yld, month=np.asarray(W.days.month)[tr.e], kind=tr.kind)


def month_table(rw):
    """trades by calendar month (CHOICE: of the ENTRY session - the prereg does not say entry or exit): count, net $ (the exact-hedge trade P&L) and mean bps"""
    out = {}
    for mth in range(1, 13):
        m = rw.month == mth
        out[mth] = {"trades": int(m.sum()), "net": float(rw.pnl[m].sum()), "mean_bps": float(rw.bps[m].mean()) if m.any() else float("nan")}
    return out


def yield_buckets(rw):
    """the dividend yield at entry (the E1 dividend / the entry close): the TOP THIRD of the cell's trades against the rest (CHOICE: the cut is the cell's 2/3 percentile of the yield, the top third is at or above it); count, net $, mean bps; trades with no yield are counted apart"""
    ok = np.isfinite(rw.yld)
    if not ok.any():
        return {"cut": float("nan"), "no_yield": int((~ok).sum())}
    cut = float(np.percentile(rw.yld[ok], 100.0 * 2 / 3))
    top = ok & (rw.yld >= cut)
    rest = ok & ~top
    f = lambda m: {"trades": int(m.sum()), "net": float(rw.pnl[m].sum()), "mean_bps": float(rw.bps[m].mean()) if m.any() else float("nan"), "mean_yield_pct": float(100 * rw.yld[m].mean()) if m.any() else float("nan")}
    return {"cut": cut, "top_third": f(top), "rest": f(rest), "no_yield": int((~ok).sum())}


def late_exits(rw):
    """the X-rule's late / skipped / cut dividend exits (kind 1: X after P + 10 or none on the calendar -> exit at the close of P + 10): count and P&L"""
    m = rw.kind == 1
    return {"trades": int(m.sum()), "net": float(rw.pnl[m].sum()), "mean_bps": float(rw.bps[m].mean()) if m.any() else float("nan"), "of": int(len(rw.kind))}


def top_gains(rw, n=20):
    o = np.argsort(-rw.pnl, kind="stable")[:n]
    return [{"rank": q + 1, "symbol": str(rw.sym[i]), "entry": f"{pd.Timestamp(rw.entry[i]):%Y-%m-%d}", "exit": f"{pd.Timestamp(rw.exit[i]):%Y-%m-%d}", "pnl": float(rw.pnl[i]), "bps": float(rw.bps[i])} for q, i in enumerate(o)]


def candidate_rows(W, ctx, run, cell, rule, tbis_df, status, n=AUDIT_N):
    """(f) the n largest single-trade contributors of a (cell, exit rule) - CHOICE: the largest GAINS (the trades that carry the profit; a fake loss only works against a pass), on the trade-level P&L with the EXACT hedge - with what the hand audit
    needs: symbol, entry, exit, the event's P / X / E1 / E2 / E3 and the E1 amount (the CALENDAR ROW), $ (total, stock, hedge, cash received), the split factor's ratio from 252 sessions before the entry to the exit and whether a registered split
    / factor change falls inside, the largest raw overnight ratio in the hold, TBIS's rows for the symbol, the asset status and the hygiene reasons in the window. The hand audit file's key is symbol + event (the predicted ex-date P)"""
    tr, ev = run.tr, ctx.ev
    if not tr.n:
        return []
    rw = trade_rows(W, ctx, run)
    sel = np.argsort(-run.pos.pnl, kind="stable")[:n]
    tb = None if tbis_df is None or not len(tbis_df) else tbis_df
    dfmt = lambda v: "" if pd.isna(v) else f"{pd.Timestamp(v):%Y-%m-%d}"
    rows_out = []
    for rank, i in enumerate(sel, 1):
        e, x, col, iev = int(tr.e[i]), int(tr.x[i]), int(tr.col[i]), int(tr.ev[i])
        a0 = max(e - SPEC["win"], 0)
        rg = W.Rg[e + 1:x + 1, col]
        rg = rg[np.isfinite(rg)]
        big = float(rg[np.argmax(np.abs(rg - 1.0))]) if len(rg) else float("nan")
        sym = str(W.syms[col])
        ptb = [None, None, None]
        if tb is not None:
            m = tb[(tb["symbol"].astype(str) == sym) & (tb["day"] >= W.days[a0]) & (tb["day"] <= W.days[x])]
            if len(m):
                ptb = [float(m["price_ratio"].iloc[0]), float(m["vol_ratio"].iloc[0]) if pd.notna(m["vol_ratio"].iloc[0]) else float("nan"), str(m["split_like"].iloc[0])]
        pre = W.hyg(max(e - SPEC["hyg_lead"], 0), e, np.array([col]))[:, 0]
        hold = W.hyg(e + 1, x, np.array([col]))[:, 0]
        rows_out.append({"cell": cell, "rule": rule, "rank": rank, "symbol": sym, "entry": f"{W.days[e]:%Y-%m-%d}", "exit": f"{W.days[x]:%Y-%m-%d}", "event": dfmt(ev.p_date[iev]), "x_date": dfmt(ev.x_date[iev]),
                         "e1": dfmt(ev.e1[iev]), "e2": dfmt(ev.e2[iev]), "e3": dfmt(ev.e3[iev]), "e1_amount": float(ev.amt1[iev]), "calendar_row": f"E3 {dfmt(ev.e3[iev])} / E2 {dfmt(ev.e2[iev])} / E1 {dfmt(ev.e1[iev])} amt {ev.amt1[iev]:g}; P {dfmt(ev.p_date[iev])}; X {dfmt(ev.x_date[iev])}",
                         "pnl": float(run.pos.pnl[i]), "stock_pnl": float(run.pos.stock[i]), "hedge_pnl": float(run.pos.hedge[i]), "cash_received": float(run.div_usd[i]), "bps": float(rw.bps[i]), "kind": "late_or_missing_x" if tr.kind[i] else "x",
                         "split_factor_ratio_window_to_exit": float(W.F[x, col] / W.F[a0, col]), "split_or_factor_change_in_hold": bool(W.chg[e + 1:x + 1, col].any()), "max_overnight_raw_ratio_in_hold": big,
                         "tbis_price_ratio": ptb[0], "tbis_vol_ratio": ptb[1], "tbis_split_like": ptb[2], "asset_status": status.get(sym, "unknown"),
                         "flags_before_entry": "+".join(h for h, v in zip(HYG, pre) if v), "flags_in_hold": "+".join(h for h, v in zip(HYG, hold) if v), "special_dividend_in_hold": bool((ctx.spcs[x + 1, col] - ctx.spcs[e + 1, col]) > 0),
                         "spin_or_stock_dividend_in_hold": bool((W.spcs[x + 1, col] - W.spcs[e + 1, col]) > 0), "naive_raw_path": bool(tr.naive[i])})
    return rows_out


def reports(W, ctx, B, S12, ref, rows, objs, summ, tbis_df, status, legs_meta):
    """everything the prereg's REPORTED paragraph lists for the registered reading, per (exit rule, cell): the realised beta to ES in #463's drawdown weeks and the cell's $ inside every qualifying #463 drawdown, the MDL map point, trades by
    calendar month, the yield buckets, the late / skipped dividend exits (the X-rule), the 20 largest trade gains, the correlation with each #463 leg; per cell: where X fell against P - 1, R10 against R20 (printed from the summary). [X2]
    ref_episodes = a row per qualifying drawdown episode of the REFERENCE book (its dates, depth, its own P&L and the cell's inside it), trades_by_year = the trades that exited in each July-June year"""
    lo, hi = WF0, PRE_END
    rep = {"beta_to_es": {}, "episodes": {}, "map_point": {}, "corr_with_legs": {}, "months": {}, "yield_buckets": {}, "late_exits": {}, "top20_gains": {}, "x_position": {}, "ref_episodes": {}, "trades_by_year": {}}
    cands = {}
    for rule in EXITS:
        for key in ("beta_to_es", "episodes", "map_point", "corr_with_legs", "months", "yield_buckets", "late_exits", "top20_gains", "ref_episodes", "trades_by_year"):
            rep[key][rule] = {}
        for cell in CELLS:
            o = objs[(rule, cell)]
            rw = trade_rows(W, ctx, o.run)
            with np.errstate(all="ignore"):                                                  # r11's Newey-West t divides by a zero standard error when a cell holds nothing on the DD days
                rep["beta_to_es"][rule][cell] = D15.es_beta(B, S12, W, rows, o.xB)
            rep["episodes"][rule][cell] = D15.episodes_table(S12, o.xB)
            rep["ref_episodes"][rule][cell] = D15.episodes_table(ref.S, o.xB)
            ty = jyear(np.asarray(W.days)[o.tr.x]) if o.tr.n else np.zeros(0, int)
            rep["trades_by_year"][rule][cell] = {int(y): int((ty == y).sum()) for y in YEARS}
            c = summ[rule][cell]
            rep["map_point"][rule][cell] = {"standalone_roc_30k": c["base"]["roc"], "rho_dd": c["seat"]["rho_dd"], "DO": c["seat"]["DO"]}
            rep["corr_with_legs"][rule][cell] = A13.corrs(B, o.xB, legs_meta, lo, hi)
            rep["months"][rule][cell] = month_table(rw)
            rep["yield_buckets"][rule][cell] = yield_buckets(rw)
            rep["top20_gains"][rule][cell] = top_gains(rw)
            if rule == "X":
                rep["late_exits"][rule][cell] = late_exits(rw)
            if rule in ("X", REGISTERED):
                cands[(rule, cell)] = candidate_rows(W, ctx, o.run, cell, rule, tbis_df, status)
    return rep, cands


# ------------------------------------------------------------------ printing
def row(rule, cell, c):
    s, q = c["base"], c["seat"]
    return (f"{rule:<3} {cell:<3} trades {s['n_pos']:>6,} net ${s['net']:>10,.0f} ROC@30k {s['roc']:>7.1f} Sortino {s['sortino']:>5.2f} maxDD ${s['max_dd']:>8,.0f} | trade-level net ${s.get('net_pos', float('nan')):>10,.0f} | "
            f"DO {q['DO']:>+7.3f} rho_dd {q['rho_dd']:>+6.3f}")


def print_cells(res, title=""):
    cells = res["cells"]
    for rule in EXITS:
        nul = res["null"].get(rule)
        print(f"  --- exit rule {rule}: {EXIT_NAME[rule]}" + ("" if nul is None else f" - placebo-in-time null ({nul['draws']} draws, seed {nul['seed']}, the MAX over the 2 cells): ROC@30k p5 {nul['roc_max']['p5']:.1f} p50 "
              f"{nul['roc_max']['p50']:.1f} p95 {nul['roc_max']['p95']:.1f}; each cell alone p50 / p95: " + ", ".join(f"{c} {nul['by_cell'][c]['p50']:.1f} / {nul['by_cell'][c]['p95']:.1f}" for c in CELLS)) + ("" if rule in NULL_EXITS else " - REPORTED (no registered null)"))
        for cell in CELLS:
            c = cells[rule][cell]
            s2 = ", ".join(f"{k} net ${v['net']:,.0f}" for k, v in c["stress"].items())
            print("  " + row(rule, cell, c))
            print(f"        stress: {s2}; by July-June year: " + " ".join(f"{y}-{(y + 1) % 100:02d}:{v:+,.0f}" for y, v in c["base"]["by_year"].items()))
            if "checks" in c:
                fails = [k for k, v in c["checks"].items() if not v]
                print(f"        Stage A (a)-(e) {'PASS' if c['PASS'] else 'FAIL (' + ', '.join(fails) + ')'}")
            elif "checks_without_null" in c:
                fails = [k for k, v in c["checks_without_null"].items() if not v]
                print(f"        checks that need no null (REPORTED): {'all clear' if not fails else 'FAIL (' + ', '.join(fails) + ')'}")
            a2 = c["A2"]
            if a2.get("at_half_c"):
                rf, pl = a2["reference"], a2["plain_463"]
                a2s = (f"c x{a2['c']:.4g} (cell daily std ${a2['std_cell']:,.0f} vs #463's ${a2['std_book']:,.0f} over {a2['window'][0]} .. {a2['window'][1]}): REFERENCE + c x cell ROC@30k {a2['roc']:.2f} Sortino {a2['sortino']:.3f} "
                       f"against the reference's {rf['roc']:.2f} / {rf['sortino']:.3f} -> " + ("INCREMENTAL PASS (both above): a forward BOOK shadow line opens, MANAGER #70's gate follows" if a2["incremental_pass"] else "no incremental pass (it needs both above)") +
                       f"; at 0.5c ROC {a2['at_half_c']['roc']:.2f} / Sortino {a2['at_half_c']['sortino']:.3f}, at 2c ROC {a2['at_double_c']['roc']:.2f} / Sortino {a2['at_double_c']['sortino']:.3f}; "
                       f"the plain #463 + c x cell book (a reported row): ROC {pl['roc']:.2f} / Sortino {pl['sortino']:.3f}")
            else:
                a2s = f"{a2.get('error', 'no c')} -> no incremental pass"
            print(f"        A2 (a report) [X1]: {a2s}")
            g = c["gate70"]
            print(f"        #70 gate basis [X1] (the REFERENCE book's {g['episodes']} drawdown episodes, {g['dd_days']} DD days): the cell's DO {g['DO']:+.3f}, rho_dd {g['rho_dd']:+.3f}" + (
                  f"; its null's DO (the MAX over the 2 cells, placebo in time) p5 {g['null_do_p5']:+.3f} p50 {g['null_do_p50']:+.3f} p95 {g['null_do_p95']:+.3f} -> the cell's DO is {'above' if g['DO_above_null_p95'] else 'not above'} the null's p95"
                  if "null_do_p95" in g else " (no registered null for this rule)"))
            if "unhedged" in c:
                u, g, hc = c["unhedged"], c["hedge_gap"], c["hedge_contracts"]
                print(f"        UNHEDGED leg (reported): net ${u['net']:,.0f} ROC@30k {u['roc']:.1f} Sortino {u['sortino']:.2f} maxDD ${u['max_dd']:,.0f}; hedge as traded (whole MES, max {hc['max_abs']:.0f} contracts, {hc['changes']:,} changes) net ${g['hedge_as_traded_net']:,.0f} vs "
                      f"exact fractional ${g['hedge_exact_net']:,.0f}: daily gap sum ${g['gap_sum']:,.0f}, worst day {g['worst_day']} ${g['worst_day_gap']:,.0f}")
                print("        sub-periods: " + "; ".join(f"{lab}: {v['n_pos']:,} trades net ${v['net']:,.0f} ROC@30k {v['roc']:.1f}" for lab, v in c["sub"].items()))
            if "placebo" in c:
                pl = c["placebo"]
                print(f"        placebo draws: {pl['trades_with_no_placebo_session']:,} of {pl['trades']:,} trades have no placebo session (left out of every draw), {pl['trades_left_out_per_draw_mean']:,.1f} left out per draw on average (max {pl['trades_left_out_per_draw_max']:,.0f})")
            if "random_name_null" in c:
                r_ = c["random_name_null"]
                print(f"        second null (REPORTED) random names at the same entry / exit sessions: ROC@30k p5 {r_['roc_p5']:.1f} p50 {r_['roc_p50']:.1f} p95 {r_['roc_p95']:.1f}; the cell's {c['base']['roc']:.1f} is above "
                      f"{r_['real_roc_percentile']:.0f}% of its draws ({r_['trades_with_no_eligible_name']:,} trades have no eligible name)")


FUNNEL_KEYS = ("events",) + ENTRY_REASONS + ("entry_set",)


def print_funnel(es):
    """COUNTS: per cell and entry year, the events (a cycle-OK event whose P is in the data) and the first reason each fails at, then the entry set. The two X-skips are the prereg's: 'x_passed' (X on / before the entry close) and 'x_next' (X is the next session)"""
    for cell in CELLS:
        print(f"  {cell} (K = {KS[cell]}) events -> first reason -> entry set, by entry year (columns: " + " / ".join(FUNNEL_KEYS) + ")")
        for y, c in sorted(es[cell].cnt.items()):
            print(f"    {y}: " + " ".join(f"{c.get(k, 0)}" for k in FUNNEL_KEYS))


HYG_KEYS = ("no_es",) + tuple(f"pre_{h}" for h in HYG) + tuple(f"hold_{h}" for h in HYG) + ("hold_special", "hold_spin", "trades", "kept_naive", "unresolved")


def print_hygiene(label, trs):
    """COUNTS: per exit rule and cell, the trades whose exit falls in the stretch removed at their FIRST hygiene reason by entry year (the naive reading removes only the pre-entry ones and keeps the hold-flagged ones: kept_naive)"""
    for rule in EXITS:
        for cell in CELLS:
            cnt = trs[(rule, cell)].cnt
            keys = [k for k in HYG_KEYS if any(k in c for c in cnt.values())]
            print(f"  {label} {rule} {cell}: stretch trades removed at their first reason by entry year (columns: " + " / ".join(keys) + ")")
            for y, c in sorted(cnt.items()):
                print(f"    {y}: " + " ".join(f"{c.get(k, 0)}" for k in keys))


def print_reports(rep, summ):
    reg = REGISTERED
    b = rep["beta_to_es"]
    print("  realised beta to ES (the cell's daily $ P&L on ES's daily return, $ per 1% ES move; #463's DD days / DD weeks / all WF days) - " + "; ".join(
        f"{r} {c} {b[r][c]['DD days']['usd_per_1pct_es']:+,.0f} / {b[r][c]['DD weeks (every day of them)']['usd_per_1pct_es']:+,.0f} / {b[r][c]['all WF days']['usd_per_1pct_es']:+,.0f}" for r in (reg, "X") for c in CELLS))
    for r in (reg, "X"):
        for c in CELLS:
            e = rep["episodes"][r][c]
            print(f"  {r} {c}: P&L inside #463's {len(e)} qualifying drawdowns: net ${sum(x['cell_pnl'] for x in e):,.0f} over {sum(x['dd_days'] for x in e)} DD days (#463's ${sum(x['book_pnl'] for x in e):,.0f}); "
                  f"MDL map point: ROC@30k {rep['map_point'][r][c]['standalone_roc_30k']:.1f}, rho_dd {rep['map_point'][r][c]['rho_dd']:+.3f}, DO {rep['map_point'][r][c]['DO']:+.3f}")
    for r in (reg, "X"):
        a, bb = summ[r]["R10"]["base"], summ[r]["R20"]["base"]
        print(f"  R10 vs R20 under {r}: R10 {a['n_pos']:,} trades net ${a['net']:,.0f} ROC {a['roc']:.1f} mean {1e4 * a['net_pos'] / max(a['n_pos'], 1) / SPEC['slot']:+.1f} bps a trade (trade level); R20 {bb['n_pos']:,} trades net ${bb['net']:,.0f} "
              f"ROC {bb['roc']:.1f} mean {1e4 * bb['net_pos'] / max(bb['n_pos'], 1) / SPEC['slot']:+.1f} bps")
    for r in (reg,):
        for c in CELLS:
            yb, lx = rep["yield_buckets"][r][c], rep["late_exits"]["X"][c]
            mn = rep["months"][r][c]
            print(f"  {r} {c} by calendar month of entry (trades / net $): " + " ".join(f"{m}:{v['trades']}/{v['net']:+,.0f}" for m, v in mn.items()))
            if "top_third" in yb:
                print(f"  {r} {c} yield buckets (E1 dividend / entry close; top third from {100 * yb['cut']:.2f}%): top third {yb['top_third']['trades']:,} trades {yb['top_third']['mean_bps']:+.1f} bps a trade net ${yb['top_third']['net']:,.0f}; "
                      f"the rest {yb['rest']['trades']:,} trades {yb['rest']['mean_bps']:+.1f} bps net ${yb['rest']['net']:,.0f} ({yb['no_yield']} without a yield)")
            print(f"  X-rule {c} late / skipped dividend exits (X after P + 10 or none: exit at P + 10): {lx['trades']:,} of {lx['of']:,} trades, net ${lx['net']:,.0f}" + (f", {lx['mean_bps']:+.1f} bps a trade" if lx["trades"] else ""))
            for x in rep["top20_gains"][r][c][:3]:
                print(f"      {r} {c} top gain {x['rank']}: {x['symbol']} {x['entry']} -> {x['exit']} ${x['pnl']:,.0f} ({x['bps']:+.0f} bps) (the 20 largest are in the Stage A file)")
# ------------------------------------------------------------------ [X2] the diagnostics: the legs apart, the draft's X-axis event-time path, every cell under every exit rule side by side (none of it a pass route)
def hedge_leg_run(run):
    """the ES hedge leg alone, as a run for stat_of: the aggregate whole-MES hedge as traded (its costs in) is the daily series, the exact fractional hedge the trade-level one"""
    return SimpleNamespace(x=run.hedge_agg, cnt=run.cnt, n_pos=run.n_pos, n_units=run.n_units, pos=SimpleNamespace(pnl=run.pos.hedge), tr=run.tr)


def event_path_x(W, tr):
    """[X2] the DRAFT's X-axis variant of the event-time path (its REPORTED paragraph: 'the hedged, cost-free mean return from X - 25 to X + 5 sessions, all years and by year - where the run-up actually sits'), printed beside [V4]'s P axis: for every
    R20 trade of the X-rule whose X is known (kind 0 - the very events of the P-axis path, so the two are comparable), the session X + tau (tau = -25 .. +5) contributes  r - beta x ES  where r = the split-safe TOTAL daily return (r17_resmom's W.Rd:
    price + the cash dividend on its ex-date, so the ex-day is the dividend net of the drop) and beta the trade's entry beta; an ES-hole session contributes nothing and a session outside the data none. CHOICE: by July-June year of X (the axis' own
    anchor); means over the trades that have a value on that session (N per tau). Also the mean over trades of the SUM of the path X - 25 .. X - 1 (the run-up), of X - 2 .. X - 1 (the last two cum-dividend sessions: a gain wholly there is the
    ex-day tax trade) and of X .. X + 5 (the ex-day and after), all in bps"""
    lo_t, hi_t = SPEC["xtau_lo"], SPEC["xtau_hi"]
    taus = np.arange(lo_t, hi_t + 1)
    m = tr.kind == 0
    xr, col, beta = tr.xr[m], tr.col[m], tr.beta[m]
    T = W.T
    rows_ = xr[:, None] + taus[None, :]
    rc = np.clip(rows_, 0, T - 1)
    valid = (rows_ >= 0) & (rows_ <= T - 1)
    with np.errstate(invalid="ignore"):
        A = np.where(valid, np.asarray(W.Rd, float)[rc, col[:, None]] - beta[:, None] * np.asarray(W.es.ret, float)[rc], np.nan)
    yr = jyear(np.asarray(W.days)[np.clip(xr, 0, T - 1)]) if len(xr) else np.zeros(0, int)

    def line(sel):
        a = A[sel]
        n = np.isfinite(a).sum(axis=0)
        with np.errstate(invalid="ignore"):
            mean = np.where(n > 0, np.nansum(a, axis=0) / np.maximum(n, 1), np.nan) * 1e4
        return mean, n
    mean, n = line(np.ones(len(xr), bool))
    part = lambda a, b: 1e4 * np.nansum(A[:, (taus >= a) & (taus <= b)], axis=1)
    pre, last2, post, tot = part(lo_t, -1), part(-2, -1), part(0, hi_t), part(lo_t, hi_t)
    avg = lambda v: float(v.mean()) if len(v) else float("nan")
    by = {int(y): line(yr == y) for y in sorted(set(yr.tolist()))}
    return SimpleNamespace(axis="X", taus=taus, mean_bps=mean, n=n, by_year={y: {"mean_bps": a_, "n": b_} for y, (a_, b_) in by.items()}, cum_bps=np.nancumsum(mean), trades=int(len(xr)), late_or_missing_x_trades=int((~m).sum()),
                           total_mean_bps=avg(tot), pre_mean_bps=avg(pre), last2_mean_bps=avg(last2), post_mean_bps=avg(post),
                           last2_share=float(avg(last2) / avg(pre)) if len(xr) and avg(pre) != 0 else float("nan"))


def print_path_x(pth, label=""):
    t = pth.taus
    print(f"EVENT-TIME PATH [X2]{label} - the draft's X-axis variant: the hedged, cost-free mean abnormal return per session, bps (r - beta x ES with r the TOTAL return, the dividend in it on the ex-date; session X + tau, X - 25 .. X + 5; the same "
          f"R20 X-rule events as the P axis, X within P + 10: {pth.trades:,} events; by July-June year of X) - printed BEFORE any cell statistic:")
    print("  tau      " + " ".join(f"{int(v):>5d}" for v in t))
    print("  all      " + " ".join(f"{v:>5.1f}" if np.isfinite(v) else "    ." for v in pth.mean_bps))
    print("  N        " + " ".join(f"{int(v):>5d}" for v in pth.n))
    for y, d in pth.by_year.items():
        print(f"  {y}-{(y + 1) % 100:02d}  " + " ".join(f"{v:>5.1f}" if np.isfinite(v) else "    ." for v in d["mean_bps"]) + f"   (N {int(d['n'].max()) if len(d['n']) else 0})")
    print(f"  X - 25 .. X - 1 sums to a mean of {pth.pre_mean_bps:+.1f} bps a trade; {pth.last2_mean_bps:+.1f} bps of it ({pth.last2_share:+.0%}) sits in X - 2 .. X - 1 (a gain wholly there is the ex-day tax trade); "
          f"X .. X + 5 (the ex-day and after) carries {pth.post_mean_bps:+.1f}; the whole path {pth.total_mean_bps:+.1f}")


DIAG_COLS = tuple((r, c) for r in EXITS for c in CELLS)                                    # X R10, X R20, NO-X R10, NO-X R20, P+10 R10, P+10 R20: every diagnostic row carries all six
DIAG_RULE = {"X": "X-rule", "NOX": "NO-X", "P10": "P+10"}
DIAG_LW, DIAG_CW = 58, 18


def diag_line(label, vals):
    return f"  {label:<{DIAG_LW}}" + "".join(f"{v:>{DIAG_CW}}" for v in vals)


def print_diagnostics(res, rep, ref):
    """[X2] DEEPER DIAGNOSTICS of the registered reading, every cell under every exit rule side by side: the cost curve at 0 / 5 / 10 / 20 bps a side (the stock's cost; the ES hedge keeps its own), a row per July-June year (net $ of the daily series
    and the trades that exited in it), the two regime halves, a row per drawdown episode of the REFERENCE book (the cell's P&L inside it), the stock leg and the ES hedge leg apart, and the #70 gate's basis (the cell's DO against the reference's
    drawdown days beside its null's). CHOICE: 'a drawdown episode of the reference' = a QUALIFYING episode (MDL r1's rule: at least 1/3 as deep as the deepest - the episodes the #70 gate's DO is measured on); the many shallow ones are not listed. res = evaluate's record of the registered reading, rep = reports', ref = the reference book"""
    cells, cols = res["cells"], DIAG_COLS
    each = lambda f: [f(cells[r][c], r, c) for r, c in cols]
    nr = lambda s: f"{s['net']:+,.0f} / {s['roc']:.1f}"
    print("DIAGNOSTICS [X2] - the registered reading, the WF stretch, every cell under every exit rule side by side; none of this is a pass route")
    print(diag_line("", [f"{DIAG_RULE[r]} {c}" for r, c in cols]))
    print("  COST CURVE - the stock's cost a side (the ES hedge keeps its own cost): net $ / ROC@30k")
    for lab, get in (("0 bps", lambda c, r, k: c["cost0"]), ("5 bps (the base)", lambda c, r, k: c["base"]), ("10 bps", lambda c, r, k: c["stress"]["10 bps"]), ("20 bps", lambda c, r, k: c["stress"]["20 bps"])):
        print(diag_line(f"  {lab}", each(lambda c, r, k: nr(get(c, r, k)))))
    print("  BY JULY-JUNE YEAR - net $ of the daily series (trades that exited in the year)")
    for y in YEARS:
        print(diag_line(f"  {y}-{(y + 1) % 100:02d}", each(lambda c, r, k: f"{c['base']['by_year'][y]:+,.0f} ({rep['trades_by_year'][r][k].get(y, 0)})")))
    print("  THE TWO REGIME HALVES - net $ / ROC@30k, then the trades that exited in the half")
    for lab, _a, _b in SUBPERIODS:
        print(diag_line(f"  {lab}", each(lambda c, r, k: nr(c["sub"][lab]))))
        print(diag_line("    trades", each(lambda c, r, k: f"{c['sub'][lab]['n_pos']:,}")))
    g = ref.structure
    print(f"  THE REFERENCE BOOK'S DRAWDOWN EPISODES ({g['episodes']} qualifying, {g['days']} DD days; MDL r1's rule) - the cell's P&L inside each (the DD days: the day after the peak .. the trough)")
    eps = rep["ref_episodes"][cols[0][0]][cols[0][1]]
    for q, e in enumerate(eps):
        print(diag_line(f"  {e['first_dd_day']} .. {e['trough']} ${e['depth']:,.0f} ({e['dd_days']} d, ref {e['book_pnl']:+,.0f})", [f"{rep['ref_episodes'][r][k][q]['cell_pnl']:+,.0f}" for r, k in cols]))
    print(diag_line("  all the episodes (the cell's P&L over the DD days)", [f"{sum(x['cell_pnl'] for x in rep['ref_episodes'][r][k]):+,.0f}" for r, k in cols]))
    print("  THE STOCK LEG AND THE ES HEDGE LEG APART (net $; the stock leg's own cost is in the stock leg, the whole-MES hedge's in the hedge leg)")
    print(diag_line("  stock leg alone (= the unhedged leg): net $ / ROC", each(lambda c, r, k: nr(c["unhedged"]))))
    print(diag_line("  ES hedge leg alone (as traded, MES costs in): net $", each(lambda c, r, k: f"{c['hedge_leg']['net']:+,.0f}")))
    print(diag_line("    its gross P&L / its MES costs", each(lambda c, r, k: f"{c['hedge_gross']:+,.0f} / {c['hedge_costs']:+,.0f}")))
    print(diag_line("  the exact fractional hedge, net $ (trade level)", each(lambda c, r, k: f"{c['hedge_gap']['hedge_exact_net']:+,.0f}")))
    print(diag_line("  stock + hedge = the cell as traded: net $ / ROC", each(lambda c, r, k: nr(c["base"]))))
    print(f"  #70 GATE BASIS - the cell's DO against the REFERENCE book's {g['episodes']} drawdown episodes / {g['days']} DD days, beside its placebo-in-time null's (the MAX over the 2 cells; none for P+10)")
    print(diag_line("  DO (cell P&L over the DD days / the reference's loss)", each(lambda c, r, k: f"{c['gate70']['DO']:+.3f}")))
    print(diag_line("  the null's DO p95", each(lambda c, r, k: f"{c['gate70']['null_do_p95']:+.3f}" if "null_do_p95" in c["gate70"] else "-")))
    print(diag_line("  the cell's DO above the null's p95", each(lambda c, r, k: ("yes" if c["gate70"]["DO_above_null_p95"] else "no") if "null_do_p95" in c["gate70"] else "-")))


# ------------------------------------------------------------------ the hand audit (f): the harness lists, the HAND decides; a data event removes the event from the cells AND the nulls
def read_audit(path=None):
    """OUT\\divrun_audit.csv (symbol, event, cell, verdict in {keep, data_event}, note) -> a frame, or None when there is no file yet. 'event' = the predicted ex-date P of the listed trade (the 'event' column of divrun_audit_candidates.csv). A
    data_event row removes that name's event - the trades of BOTH cells under ALL exit rules, and the null - before anything is computed, and Stage A is computed again [(f)]. CHOICE: the key is symbol + event (the two cells enter one event on
    different days). Refuses a verdict / cell / date it cannot read (a mistyped row must not silently do nothing)"""
    p = path or os.path.join(OUT, "divrun_audit.csv")
    if not os.path.exists(p):
        return None
    df = pd.read_csv(p, dtype=str, keep_default_na=False)
    miss = [c for c in ("symbol", "event", "cell", "verdict") if c not in df.columns]
    if miss:
        refuse(f"refused: divrun_audit.csv lacks the column(s) {miss} (columns: symbol, event, cell, verdict, note) - nothing computed")
    df["symbol"], df["cell"], df["verdict"] = df["symbol"].str.strip(), df["cell"].str.strip().str.upper(), df["verdict"].str.strip().str.lower()
    df["event"] = pd.to_datetime(df["event"].str.strip(), errors="coerce")
    bad = df[~df["verdict"].isin(("keep", "data_event")) | ~df["cell"].isin(CELLS) | df["event"].isna() | (df["symbol"] == "")]
    if len(bad):
        refuse(f"refused: divrun_audit.csv line(s) {[int(i) + 2 for i in bad.index][:10]} have an unreadable event date / symbol, a verdict outside keep | data_event, or a cell outside {list(CELLS)} (nothing computed)")
    return df


def apply_audit(ctx, audit):
    """put the audit's data_event rows on the context as removals of events (symbol + predicted ex-date). A data_event row that matches no event of the calendar refuses: a mistyped row must not silently do nothing -> counts"""
    ev = ctx.ev
    ctx.aud_ev = np.zeros(ev.n, bool)
    if audit is None:
        return {"rows": 0, "keep": 0, "data_event": 0}
    de = audit[audit["verdict"] == "data_event"]
    bad = []
    for i, r in de.iterrows():
        hit = (ev.sym == r["symbol"]) & (ev.p_date == np.datetime64(r["event"]))
        if not hit.any():
            bad.append(int(i) + 2)
        ctx.aud_ev |= hit
    if bad:
        refuse(f"refused: divrun_audit.csv data_event line(s) {bad[:10]} match no event of the calendar (the event is the PREDICTED ex-date P of the listed trade; the symbol must be one of the grid) - fix the file (nothing computed, lockbox NOT read)")
    return {"rows": int(len(audit)), "keep": int((audit["verdict"] == "keep").sum()), "data_event": int(len(de))}


def audit_status(cands, audit):
    """per (rule, cell): how many of the listed top-50 contributors appear in divrun_audit.csv (symbol + event). INFORMATION ONLY: the harness never decides (f) - the lead's go-flag is the sign-off"""
    have = set() if audit is None else set(zip(audit["symbol"], audit["event"].dt.strftime("%Y-%m-%d")))
    return {f"{r}/{c}": {"listed": len(rows), "audited": int(sum((x["symbol"], x["event"]) in have for x in rows))} for (r, c), rows in cands.items()}


# ------------------------------------------------------------------ the lockbox cut, asserted at the point of use
def cut_checks(W, cal, cut):
    """[13] the lockbox cut at READ time. CHOICE: asserted a second time where DIVRUN holds the data: nothing on / after the stage's cut (Stage A / the dryload: 2025-06-30; Stage B: the lockbox's end) is in the World's sessions - and so in its closes,
    volumes, ES prints and flags, which live on those sessions - or in a row of the calendar (cash dividends, spin-offs / stock dividends, splits). The loaders (r17_resmom / r15_ddw) cut and assert on their own; this refuses if anything got
    through them, before a single event is built"""
    assert_cut("DIVRUN sessions", W.days, cut)
    if cal is not None:
        for nm in ("div", "spin", "split"):
            fr = getattr(cal, nm, None)
            if fr is not None and len(fr) and "ex" in fr.columns:
                assert_cut(f"DIVRUN calendar {nm} ex-dates", pd.DatetimeIndex(fr["ex"]), cut)


# ------------------------------------------------------------------ dryload: counts only
def cycle_failures(ev):
    """COUNTS: the regular ex-dates of names on the grid that fail the cycle test, by why (the first reason): a name's first two regular dividends (no E2 / E3 on the calendar), a gap under 77 days (monthly-like), over 105 days (semi-annual, annual or a gap in the calendar)"""
    has2, has3 = ~np.isnat(ev.e2), ~np.isnat(ev.e3)
    g1, g2 = ev.gap1, ev.gap2
    with np.errstate(invalid="ignore"):
        lo, hi = SPEC["cyc_lo"], SPEC["cyc_hi"]
        short = (has2 & (g1 < lo)) | (has3 & (g2 < lo))
        long_ = ~short & ((has2 & (g1 > hi)) | (has3 & (g2 > hi)))
    return {"no_e2_or_e3": int((~(has2 & has3)).sum()), "a_gap_under_77_days": int((has2 & has3 & short).sum()), "a_gap_over_105_days": int((has2 & has3 & long_).sum()), "pass": int(ev.cyc.sum())}


def x_against_p(ev):
    """COUNTS over the cycle-OK events whose P is in the data: where the actual next regular ex-date X fell against P (sessions): exactly on it, 1 .. 3 early / late, farther early / late, none on the calendar by the data's end"""
    m = ev.cyc & (ev.p_row >= 0)
    d = np.where(ev.x_row >= 0, ev.x_row - ev.p_row, 10 ** 6)[m]
    f = lambda c: int(c.sum())
    return {"events": int(m.sum()), "on_P": f(d == 0), "early_1_3": f((d < 0) & (d >= -3)), "late_1_3": f((d > 0) & (d <= 3)), "early_over_3": f(d < -3), "late_over_3": f((d > 3) & (d < 10 ** 6)), "none_by_the_end": f(d == 10 ** 6),
            "within_3_sessions_of_P": f(np.abs(d) <= 3)}


def dryload():
    """the WF inputs through every loader (cut at 2025-06-30) and COUNTS only: payers in the universe by year, events per cell by year with the skips, X against P, X against P - 1, hygiene flags by reason, trades per day, the first and last entry
    dates, the ES coverage. NO price, return, regression, P&L or Stage A statistic is computed or printed: the pair counts the 230-pair rule needs are counted from which returns EXIST, and no trade path is built"""
    prereg_ok()
    t0 = time.time()
    D = M17.load_data(S.LB0)
    nfull = len(D.syms)
    tbis = D15.load_tbis(S.LB0)
    es_frames, es_meta = D15.load_es(S.LB0)
    full_match = D15.tbis_array(D.days, D.syms, tbis)[1]
    cal, winfo = M17.wide_load(S.LB0, need=False, enforce=False)                              # CHOICE: the dryload counts on the calendar when it exists and REPORTS its sha status (only Stage A / B refuse an unregistered one)
    W = M17.build_world(D, S.LB0, es_frames, tbis, cal)
    D15.release(D)
    cut_checks(W, cal, S.LB0)
    print(f"dryload: inputs ready ({time.time() - t0:.0f}s); every input cut to dates < {S.LB0:%Y-%m-%d}; ES masters {es_meta['raw']['filename']} / {es_meta['adj']['filename']}")
    wf = (W.days >= WF0) & (W.days <= PRE_END)
    print(f"sessions: {W.T:,} on the market calendar ({W.days[0]:%Y-%m-%d} .. {W.days[-1]:%Y-%m-%d}), {int(wf.sum()):,} inside the WF stretch; symbols: {nfull:,} in the cache after SIPORB's price / volume floor, {W.S:,} ever in the universe")
    usz, yrs = W.U.sum(axis=1), W.days.year.to_numpy()
    print("universe size per session by year (sessions with a universe: min / median / max): " + "; ".join(
        f"{y}: {int((m := (yrs == y) & (usz > 0)).sum())} sessions {int(usz[m].min())} / {int(np.median(usz[m]))} / {int(usz[m].max())}" for y in sorted(set(yrs)) if ((yrs == y) & (usz > 0)).any()))
    if W.ca is None:
        print(f"wide corporate-actions calendar [R1]: not on file yet ({winfo['path']}) - DIVRUN needs it for every event; Stage A refuses until it is on file and WIDE_CA_SHA matches; this dryload counted no event")
    else:
        M17.print_wide(W.ca)
        ctx = make_ctx(W, cal, counts_only=True)
        ev = ctx.ev
        print(f"events: {ev.counts['regular_rows']:,} regular (non-special) cash-dividend ex-dates of {ev.counts['names_with_regular_rows']:,} names on the calendar, {ev.counts['rows_not_on_the_grid']:,} of names not on the grid; {ev.n:,} remain, one event per ex-date E1; "
              f"{ev.counts['cycle_ok']:,} pass the cycle test (E3 < E2 < E1, both gaps 77 .. 105 days), {ev.counts['cycle_ok_p_on_the_next_session']:,} of those have P on the first session the data does not hold (placed by date arithmetic: "
              f"their entries and NO-X exits are inside the data) and {ev.counts['cycle_ok_p_beyond_the_data']:,} have P later still")
        cf = cycle_failures(ev)
        print(f"  the others fail at their first reason: no E2 / E3 on the calendar {cf['no_e2_or_e3']:,}; a gap under 77 days (monthly-like) {cf['a_gap_under_77_days']:,}; a gap over 105 days (semi-annual, annual, a hole) {cf['a_gap_over_105_days']:,}")
        up = (ctx.pay_p[:-1] >= 0) & W.U[1:]
        by = {}
        for y in sorted(set(yrs[:-1])):
            m = yrs[:-1] == y
            c = up[m].sum(axis=1)
            by[y] = (int(m.sum()), int(c.min()), int(np.median(c)), int(c.max()), int(up[m].any(axis=0).sum()), int(W.U[1:][m].any(axis=0).sum()))
        print("payers in the universe by year (a name in the top-500 universe at the entry close AND a regular quarterly payer at it; sessions: min / median / max per session; distinct names; of distinct universe names): " + "; ".join(
            f"{y}: {a} sessions {b} / {c_} / {d} ({e_} of {f_} names)" for y, (a, b, c_, d, e_, f_) in by.items()))
        xp = x_against_p(ev)
        print(f"X against P (sessions) over the {xp['events']:,} cycle-OK events with P in the data: on P {xp['on_P']:,}, early 1-3 {xp['early_1_3']:,}, late 1-3 {xp['late_1_3']:,}, early over 3 {xp['early_over_3']:,}, late over 3 {xp['late_over_3']:,}, none on the "
              f"calendar by the data's end {xp['none_by_the_end']:,}; X within +-3 sessions of P: {xp['within_3_sessions_of_P']:,} = {xp['within_3_sessions_of_P'] / max(xp['events'], 1):.1%}")
        es = entry_sets(W, ctx)
        print("ENTRY SETS (one per cell, shared by the three exit rules): events -> the first reason they fail -> the entry set, by ENTRY year (all years in the data; the stretch is applied by exit date below)")
        print_funnel(es)
        for cell in CELLS:
            xq = x_position(es[cell])
            print(f"  {cell}: of the {xq['n']:,} events that enter, X fell before P - 1: {xq['before']:,} ({xq['before'] / max(xq['n'], 1):.1%}), on P - 1: {xq['at']:,} ({xq['at'] / max(xq['n'], 1):.1%}), after it or not on the calendar: {xq['after']:,} ({xq['after'] / max(xq['n'], 1):.1%}); "
                  f"skipped because X was the next session {sum(c.get('x_next', 0) for c in es[cell].cnt.values()):,}, because X had already passed {sum(c.get('x_passed', 0) for c in es[cell].cnt.values()):,}")
        reg = {(r, c): trade_set(W, ctx, es[c], r, "registered", WF0, PRE_END) for r in EXITS for c in CELLS}
        nav = {(r, c): trade_set(W, ctx, es[c], r, "naive", WF0, PRE_END) for r in EXITS for c in CELLS}
        wi = np.flatnonzero(wf)
        print("hygiene events on the names ever in the universe, name-sessions inside the WF stretch (the trades they touch are counted below): " + ", ".join(f"{h} {int(W.fl[q][wf].sum()):,}" for q, h in enumerate(HYG))
              + f"; special cash dividends {int((ctx.spcs[wi[-1] + 1] - ctx.spcs[wi[0]]).sum()):,}; spin-off / stock-dividend ex-dates {int(W.SPN[wf].sum()):,}")
        print("WF trades (exit in 2016-07-01 .. 2025-06-29), the REGISTERED reading (a flag inside the hold removes the trade) and the look-ahead reading (a trade flagged inside its hold is kept on its naive raw price path):")
        print_hygiene("registered", reg)
        print_hygiene("look-ahead", nav)
        for r in EXITS:
            for c in CELLS:
                tr = reg[(r, c)]
                if not tr.n:
                    print(f"  {r} {c}: no trade in WF")
                    continue
                ent = np.bincount(tr.e, minlength=W.T)[wf]
                opn = open_counts(tr, W.T)[wf]
                print(f"  {r} {c}: {tr.n:,} trades; first entry {W.days[tr.e.min()]:%Y-%m-%d}, last entry {W.days[tr.e.max()]:%Y-%m-%d}, first exit {W.days[tr.x.min()]:%Y-%m-%d}, last exit {W.days[tr.x.max()]:%Y-%m-%d}; entries per session over the sessions that "
                      f"hold one: max {int(ent.max())} / median {np.median(ent[ent > 0]):.0f} ({int((ent > 0).sum()):,} of {int(wf.sum()):,} sessions); positions open per session: max {int(opn.max())} / median {np.median(opn):.0f} (no position on {int((opn == 0).sum()):,} sessions); "
                      f"{int((W.es_hole[tr.e] | W.es_hole[tr.x]).sum())} trades enter or exit on a session with no ES 16:00 print (the hedge carries the last one)")
    print(f"TBIS flags: {len(tbis):,} symbol-days listed before the cut, {full_match:,} match a session and a cached name, {W.tbis_rows[1]:,} a name that is ever in the universe; every listed row is a flag")
    pa, pr = W.es_cov["adj_prints"], W.es_cov["raw_prints"]
    e = W.es
    print(f"ES prints on the {W.T:,} stock sessions: 09:35 price {int(np.isfinite(e.e5).sum()):,}, 16:00 adj {int(np.isfinite(e.c16a).sum()):,}, 16:00 raw {int(np.isfinite(e.c16r).sum()):,}; fallback bars: "
          f"{int((pa['close_hm'] != pa['last']).sum())} closes (adj master), {int((pr['close_hm'] != pr['last']).sum())} closes (raw master); ES return defined on {int(np.isfinite(e.ret).sum()):,} sessions")
    print(M17.es_report(W)[0])
    print(f"cache manifest sha256: {manifest_sha()}")
    pm = peak_mb()
    print(f"dryload took {time.time() - t0:.0f}s" + (f", peak memory {pm:,.0f} MB" if pm else ""))


# ------------------------------------------------------------------ Stage A
def pick_candidate(cells, passing, rule=REGISTERED):
    """CHOICE (the prereg names no tie-break between two passing cells; A2 is only a report): the passing cell with the higher WF standalone ROC @ $30k under the REGISTERED (NO-X) reading goes to Stage B (ties: R10); the other is reported"""
    return max(passing, key=lambda c: (cells[rule][c]["base"]["roc"], -CELLS.index(c))) if passing else None


def stage_a_flow(cells):
    """Stage A's bookkeeping, pure: per cell the X-rule's and NO-X's (a)-(e) verdicts and the REGISTERED one ([V1]: NO-X wins when they differ); passing = the cells whose registered verdict is PASS; the candidate = pick_candidate(passing).
    (f) is never decided here: every passing cell 'awaits the hand audit'"""
    ver = {c: dict(zip(("registered", "x_rule", "differ"), registered_verdict({r: cells[r][c]["PASS"] for r in NULL_EXITS}))) for c in CELLS}
    passing = [c for c in CELLS if ver[c]["registered"]]
    return ver, passing, pick_candidate(cells, passing)


def stage_a():
    if os.path.exists(os.path.join(OUT, READ_FLAG)):                                        # CHOICE: once the lockbox has been read Stage A is frozen (a re-run could change the cell or c after the fact)
        refuse(f"Stage A refused: Stage B has already read the lockbox - Stage A is frozen ({READ_FLAG})")
    pok = prereg_ok()
    cal, winfo = M17.wide_load(S.LB0)                                                       # refuses (nothing computed) when the wide calendar is not on file / not registered / not the registered file
    B, legs_meta = A13.load_463()                                                           # the book first: cheap, and a book that does not reproduce stops everything
    bk, dd, S12 = book_checks(B)
    print(f"BOOK #463 WF check (must be {BOOK_WF[0]} / {BOOK_WF[1]}): ROC@30k {bk['roc']:.2f} Sortino {bk['sortino']:.3f}; deepest drawdown ${dd['deepest']:,.0f} (must be ${DEEPEST_WF:,.0f}), "
          f"{dd['episodes']} qualifying episodes, {dd['days']} DD days, {dd['weeks']} DD weeks, by year {dd['by_year']}, the 2020-03-03 .. 03-27 episode {'found' if dd['episode_2020'] else 'NOT FOUND'}")
    if CHECK_BOOK and not (bk["ok"] and dd["ok"]):
        refuse("Stage A refused: the #463 records do not reproduce the registered WF numbers / drawdown structure (the prereg's [T5] facts) - fix the input first (nothing computed)")
    ref = ref_load(B)                                                                       # [X1] RESMOM's WF line -> the REFERENCE book: refuses (nothing computed) unless the file is the registered one and the reference reproduces its registered numbers
    print_reference(ref)
    msha = manifest_sha()
    print(f"SIPORB cache manifest sha256: {msha} (registered: {D15.MANIFEST_PREFIX}...)")
    if CHECK_BOOK and not (msha and msha.startswith(D15.MANIFEST_PREFIX)):
        refuse("Stage A refused: the SIPORB cache manifest is missing or is not the registered photograph of the vendor (a re-pull must never be mixed in) - nothing computed")
    t0 = time.time()
    D = M17.load_data(S.LB0)                                                                # every input is cut to dates < 2025-06-30 inside this call, before anything is computed
    tbis = D15.load_tbis(S.LB0)
    es_frames, es_meta = D15.load_es(S.LB0)
    audit = read_audit()
    W = M17.build_world(D, S.LB0, es_frames, tbis, cal)
    D15.release(D)
    cut_checks(W, cal, S.LB0)
    wf = (W.days >= WF0) & (W.days <= PRE_END)
    print(f"world ready ({time.time() - t0:.0f}s): {int(wf.sum()):,} WF sessions, {W.S:,} names ever in the universe; ES masters {es_meta['raw']['filename']} / {es_meta['adj']['filename']}", flush=True)
    es_txt, es_rec = M17.es_report(W)
    print(es_txt)
    M17.print_wide(W.ca)
    ctx = make_ctx(W, cal)
    out = {"prereg_sha256_lf": PREREG_SHA, "prereg_verified": pok["verified"], "prereg_committed": pok["committed"], **stamp(), "judged": False, "stageA": None, "candidate": None, "book_check": bk, "dd_structure": dd, "reference": ref_record(ref),
           "manifest_sha256": msha, "es_return": es_rec, "wide_calendar": W.ca, "events": ctx.ev.counts}
    aud_n = apply_audit(ctx, audit)
    asha = file_sha(os.path.join(OUT, "divrun_audit.csv"))
    print("audit file: " + ("none yet" if audit is None else f"{aud_n['rows']} rows ({aud_n['keep']} keep, {aud_n['data_event']} data_event: removed from the cells AND the null)"))
    rows = A13.book_rows(B, W)
    es = entry_sets(W, ctx)
    print("ENTRY SETS (counts): events -> the first reason they fail -> the entry set, by entry year; one set per cell, shared by the three exit rules")
    print_funnel(es)
    for cell in CELLS:
        xq = x_position(es[cell])
        print(f"  {cell}: X fell before P - 1 in {xq['before'] / max(xq['n'], 1):.1%} of the {xq['n']:,} events that enter, on P - 1 in {xq['at'] / max(xq['n'], 1):.1%}, after it or not on the calendar in {xq['after'] / max(xq['n'], 1):.1%}; "
              f"skipped because X was the next session: {sum(c.get('x_next', 0) for c in es[cell].cnt.values()):,}; because X had already passed at the entry close: {sum(c.get('x_passed', 0) for c in es[cell].cnt.values()):,}")
    # [V4] the event-time path comes BEFORE any cell statistic; [X2] the draft's X-axis variant beside it
    trx = trade_set(W, ctx, es["R20"], "X", "registered", WF0, PRE_END)
    pth = event_path(W, trx)
    print_path(pth)
    pthx = event_path_x(W, trx)
    print_path_x(pthx)
    t1 = time.time()
    resR, objR = evaluate(W, ctx, B, S12, ref, rows, "registered", NREP, 0, full=True, es=es)
    print(f"registered reading done ({time.time() - t1:.0f}s: the cells under three exit rules, the stress rows, {NREP} placebo draws per cell for the X-rule and NO-X, and the random-name null)", flush=True)
    t1 = time.time()
    resK, objK = evaluate(W, ctx, B, S12, ref, rows, "naive", NREP, 1, full=False, es=es)
    print(f"look-ahead reading (hold-flagged trades kept at naive raw P&L) done ({time.time() - t1:.0f}s)", flush=True)
    rep, cands = reports(W, ctx, B, S12, ref, rows, objR.objs, resR["cells"], tbis, D15.asset_status(), legs_meta)
    cells = resR["cells"]
    ver, passing, cand = stage_a_flow(cells)
    flips = {f"{r}/{c}": bool(resK["cells"][r][c]["PASS"]) != bool(cells[r][c]["PASS"]) for r in NULL_EXITS for c in CELLS}
    os.makedirs(OUT, exist_ok=True)
    pd.DataFrame([x for k in sorted(cands) for x in cands[k]]).to_csv(os.path.join(OUT, "divrun_audit_candidates.csv"), index=False)
    ast = audit_status(cands, audit)
    print(f"WF {WF0:%Y-%m-%d} -> {PRE_END:%Y-%m-%d} ({int(wf.sum()):,} sessions) - the REGISTERED reading (a hygiene flag inside the hold removes the trade); trades are counted by EXIT date")
    print_cells(resR)
    print("  [V1] VERDICTS (a)-(e): the X-rule reads the calendar after the fact; NO-X does not know X and is the REGISTERED verdict whenever the two differ:")
    for c in CELLS:
        v = ver[c]
        print(f"    {c}: X-rule {'PASS' if v['x_rule'] else 'FAIL'}, NO-X {'PASS' if v['registered'] else 'FAIL'} -> " + (f"the verdicts DIFFER: the registered one is NO-X = {'PASS' if v['registered'] else 'FAIL'}" if v["differ"] else
              f"the same: registered (NO-X) {'PASS' if v['registered'] else 'FAIL'}"))
    print(f"  look-ahead reading [V3] (hold-flagged trades kept at naive raw P&L): null ROC p95 X {resK['null']['X']['roc_max']['p95']:.1f} / NO-X {resK['null']['NOX']['roc_max']['p95']:.1f}")
    for r in NULL_EXITS:
        for c in CELLS:
            k = resK["cells"][r][c]
            print(f"    {r} {c}: {row(r, c, k)[7:]} | Stage A {'PASS' if k['PASS'] else 'FAIL'}" + ("   *** FLIPS the registered verdict ***" if flips[f"{r}/{c}"] else "   (same verdict)"))
    print_hygiene("registered", {k: o.tr for k, o in objR.objs.items()})
    print_hygiene("look-ahead", {k: o.tr for k, o in objK.objs.items()})
    print_reports(rep, cells)
    print_diagnostics(resR, rep, ref)
    print(f"  audit candidates (the {AUDIT_N} largest gains per cell, X-rule and NO-X, with their calendar rows) -> {os.path.join(OUT, 'divrun_audit_candidates.csv')}; the hand audit is the lead's (a data event found: a row symbol, event, cell, data_event in "
          "divrun_audit.csv and run stage_a again); audit rows found per list: " + ", ".join(f"{k} {v['audited']}/{v['listed']}" for k, v in ast.items()))
    out.update({"judged": True, "pending_hand_audit": passing,
                "stageA": {"cells": cells, "null": resR["null"], "verdicts": ver, "registered_pass_cells": passing},
                "candidate": ({"cell": cand, "rule": REGISTERED, "c": cells[REGISTERED][cand]["A2"]["c"], "std_book": cells[REGISTERED][cand]["A2"]["std_book"], "std_cell": cells[REGISTERED][cand]["A2"]["std_cell"],
                               "window": cells[REGISTERED][cand]["A2"]["window"], "a2_book_roc": cells[REGISTERED][cand]["A2"]["roc"], "a2_reference_roc": cells[REGISTERED][cand]["A2"]["reference"]["roc"], "incremental_pass": cells[REGISTERED][cand]["A2"]["incremental_pass"],
                               "book_shadow_line": cells[REGISTERED][cand]["A2"]["book_shadow_line"],
                               "also_passes": [c for c in passing if c != cand]} if cand else None),
                "parity": {f"{r}/{c}": {"net": cells[r][c]["base"]["net"], "n_pos": cells[r][c]["base"]["n_pos"]} for r in EXITS for c in CELLS},
                "event_path": {"taus": pth.taus, "mean_bps": pth.mean_bps, "n": pth.n, "cum_bps": pth.cum_bps, "by_year": pth.by_year, "trades": pth.trades, "late_or_missing_x_trades": pth.late_or_missing_x_trades,
                               "total_mean_bps": pth.total_mean_bps, "last2_mean_bps": pth.last2_mean_bps, "last2_share": pth.last2_share},
                "event_path_x": {"taus": pthx.taus, "mean_bps": pthx.mean_bps, "n": pthx.n, "cum_bps": pthx.cum_bps, "by_year": pthx.by_year, "trades": pthx.trades, "late_or_missing_x_trades": pthx.late_or_missing_x_trades,
                                 "total_mean_bps": pthx.total_mean_bps, "pre_mean_bps": pthx.pre_mean_bps, "last2_mean_bps": pthx.last2_mean_bps, "post_mean_bps": pthx.post_mean_bps, "last2_share": pthx.last2_share},
                "entry_sets": {c: {"n": es[c].n, "by_year": {y: dict(v) for y, v in sorted(es[c].cnt.items())}, "x_position": x_position(es[c])} for c in CELLS},
                "audit": aud_n, "audit_sha256": asha, "audit_status": ast,
                "look_ahead_reading": {"null": resK["null"], "cells": {r: {c: {k: resK["cells"][r][c].get(k) for k in ("PASS", "base", "stress", "seat", "checks", "A2")} for c in CELLS} for r in EXITS}, "flips": flips},
                "hygiene_counts_by_year": {"registered": {f"{r}/{c}": {y: dict(v) for y, v in sorted(o.tr.cnt.items())} for (r, c), o in objR.objs.items()},
                                           "look_ahead": {f"{r}/{c}": {y: dict(v) for y, v in sorted(o.tr.cnt.items())} for (r, c), o in objK.objs.items()}},
                "reports": rep, "es_masters": es_meta})
    dump(out, "divrun_stageA.json")
    for c in CELLS:
        v = ver[c]
        if v["registered"]:
            a2 = cells[REGISTERED][c]["A2"]
            print(f"Stage A (a)-(e) pass, (f) awaits the hand audit - cell {c} under the registered NO-X reading" + (" (the X-rule differs: its verdict is " + ("PASS" if v["x_rule"] else "FAIL") + ")" if v["differ"] else "") +
                  f"; WF ROC@30k {cells[REGISTERED][c]['base']['roc']:.1f}; A2 (a report) [X1]: c x{a2['c']:.4g} set by volatility, REFERENCE + c x cell ROC@30k {a2['roc']:.2f} / Sortino {a2['sortino']:.3f} against the reference's "
                  f"{a2['reference']['roc']:.2f} / {a2['reference']['sortino']:.3f} -> " + ("an INCREMENTAL PASS: a forward BOOK shadow line opens beside the standalone one and MANAGER #70's gate follows (the cell's DO and its null's on the reference's drawdown days)" if a2["incremental_pass"] else "no incremental pass: no book shadow line"))
    if passing:
        print(f"DIVRUN Stage A: (a)-(e) pass for {passing} under the registered NO-X reading; (f) AWAITS THE HAND AUDIT of the {AUDIT_N} largest contributors (the harness never decides it); candidate {cand}. Stage B needs the lead's go-flag {GO_FLAG} "
              "(written after the hand audit, on the stock families' one sealed-year day).")
    else:
        print("DIVRUN Stage A: FAIL - no cell passes (a)-(e) under the registered NO-X reading (" + "; ".join(f"{c}: " + ", ".join(k for k, v in cells[REGISTERED][c]["checks"].items() if not v) for c in CELLS) +
              ") - DIVRUN r1 is dead; the windows are not re-tuned (no other K, no other exit); the lockbox stays sealed.")
    pm = peak_mb()
    print(f"stage_a took {time.time() - t0:.0f}s" + (f", peak memory {pm:,.0f} MB" if pm else ""))
    return out


# ------------------------------------------------------------------ Stage B: the one read (refuses unless the lead's go-flag is on file)
def book_add_would_clear(r):
    """the REPORTED comparison of the book add on the sealed year with the old sealed-year bar (#463's own LB numbers): both the ROC and the Sortino must reach theirs (inclusive); a NaN fails. Reported, never judged"""
    return bool(r["roc"] >= RULES["b_roc"] and r["sortino"] >= RULES["b_sort"])


def b_checks(leg):
    """STAGE B's pass: the LEG's standalone veto and nothing else - >= 100 trades, net > 0, net > 0 without its top 1% of trades. It takes no book number: the book add on the lockbox year is a report, so it cannot be in this verdict.
    A NaN fails every comparison it enters -> {check name: bool}"""
    return {f"leg trades>={RULES['b_n']}": bool(leg["n_pos"] >= RULES["b_n"]), "leg net>0": bool(leg["net"] > 0), "leg net>0 without its top 1% of trades": bool(leg["net_ex_best_pos"] > 0)}


def stage_b():
    """STAGE B (LB, once, on the stock families' one sealed-year day): REFUSES unless the lead's go-flag divrun_stageB_GO.flag is on file (the lead writes it after the hand audit (f) and only on that day; CHOICE: its EXISTENCE is the sign-off - its text is stored with the read and never parsed) and a Stage A candidate is on file. The sealed
    year is the LEG's standalone veto: >= 100 trades, net > 0, net > 0 without its top 1% of trades. The book add (#463 + c x the cell at Stage A's frozen c) is computed, printed and stored as book_add_reported - NEVER part of the pass. Every refusal
    is before the read flag; the flag is written (exclusively) only after every load, every check and the whole result are in hand"""
    go, flag = os.path.join(OUT, GO_FLAG), os.path.join(OUT, READ_FLAG)
    if not os.path.exists(go):
        refuse(f"Stage B refused: the lead's go-flag {GO_FLAG} is not on file - the hand audit (f) and the sealed-year day are the lead's call; the lockbox stays sealed (nothing computed, lockbox NOT read)")
    if os.path.exists(flag):
        refuse(f"Stage B refused: the lockbox was already read once ({READ_FLAG})")
    pa = os.path.join(OUT, "divrun_stageA.json")
    sa = json.load(open(pa)) if os.path.exists(pa) else {}
    cand = sa.get("candidate")
    ok_a = isinstance(cand, dict) and sa.get("judged") is True and cand.get("cell") in ((sa.get("stageA") or {}).get("registered_pass_cells") or [])
    if not ok_a:
        refuse("Stage B refused: no Stage A candidate (a cell that passes (a)-(e) under the registered NO-X reading) is on file - the lockbox stays sealed.")
    prereg_ok()
    if sa.get("prereg_sha256_lf") != PREREG_SHA:
        refuse("Stage B refused: Stage A ran under another pre-registration (lockbox NOT read)")
    bad = [k for k, v in stamp().items() if sa.get(k) != v]
    if bad:
        refuse(f"Stage B refused: Stage A was written by a different harness version / early-close list ({', '.join(bad)} differs or is missing) - run stage_a again (lockbox NOT read)")
    if sa.get("audit_sha256") != file_sha(os.path.join(OUT, "divrun_audit.csv")):
        refuse("Stage B refused: divrun_audit.csv is not the file Stage A ran with (it changed, or went missing) - run stage_a again (lockbox NOT read)")
    cell, rule = cand["cell"], cand.get("rule", REGISTERED)
    try:
        c = float(cand["c"])
    except (TypeError, ValueError):
        c = float("nan")
    if cell not in CELLS or rule not in EXITS or not (math.isfinite(c) and c > 0):                  # c is a volatility ratio: any positive number is a frozen size, but NaN / 0 / missing is a broken file
        refuse(f"Stage B refused: the frozen cell {cand.get('cell')} / rule {cand.get('rule')} / size c {cand.get('c')} is not one of {CELLS} / {EXITS} / a positive number (lockbox NOT read)")
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
    D = M17.load_data(S.END)
    tbis = D15.load_tbis(S.END)
    es_frames, es_meta = D15.load_es(S.END)
    audit = read_audit()
    W = M17.build_world(D, S.END, es_frames, tbis, cal)
    D15.release(D)
    cut_checks(W, cal, S.END)
    ctx = make_ctx(W, cal)
    apply_audit(ctx, audit)
    rows = A13.book_rows(B, W)
    hole_txt, hole_rec = M17.es_report(W, LB0, LB1)                                            # the ES holes that reach the lockbox: printed and stored with the read
    es = entry_sets(W, ctx)
    for cc in CELLS:                                                                           # Stage A's WF numbers (and the frozen c) must reproduce on Stage B's data (a cache or code drift stops it BEFORE the read)
        tw = trade_set(W, ctx, es[cc], rule, "registered", WF0, PRE_END)
        run = run_bundle(W, prepare(W, tw))
        st = stat_of(B, rows, run, WF0, PRE_END)
        ref = sa["parity"][f"{rule}/{cc}"]
        print(f"WF re-read on Stage B's data: {rule} {cc} trades {st[0]['n_pos']:,} (Stage A {ref['n_pos']:,}), net ${st[0]['net']:,.0f} (Stage A ${ref['net']:,.0f})")
        if st[0]["n_pos"] != ref["n_pos"] or abs(st[0]["net"] - ref["net"]) > max(1.0, 1e-6 * abs(ref["net"])):
            refuse(f"Stage B refused: the WF numbers of {rule}/{cc} do not reproduce on Stage B's data - the cache or the code changed since Stage A (lockbox NOT read)")
        if cc == cell:
            c2 = plain_a2(B, st[1])["c"]
            print(f"  frozen size {cell}: c x{c:.6g} (Stage A) vs x{c2:.6g} recomputed from {A2_WIN[0]:%Y-%m-%d} .. {A2_WIN[1]:%Y-%m-%d} on Stage B's data")
            if not (math.isfinite(c2) and abs(c2 - c) <= 1e-9 * c):
                refuse(f"Stage B refused: the volatility-set size c of {cell} does not reproduce on Stage B's data - the cache or the code changed since Stage A (lockbox NOT read)")
    tl = trade_set(W, ctx, es[cell], rule, "registered", LB0, LB1)                              # CHOICE (r15's order): the whole LB result is computed, nothing shown, BEFORE the flag
    run = run_bundle(W, prepare(W, tl))
    leg, xB, cB = stat_of(B, rows, run, LB0, LB1)
    r = D15.book_at(B, xB, c, LB0, LB1)                                                        # the book add at the FROZEN c - c is never re-set on the sealed year
    would = book_add_would_clear(r)                                                            # the old sealed-year bar (#463's own LB numbers, 155.54 / 4.150): reported, never judged
    chk = b_checks(leg)
    ok = all(chk.values())                                                                     # the pass is the LEG's veto - the book add below is a report and is not in this line
    add = {"c": c, "roc": r["roc"], "sortino": r["sortino"], "net": r["net"], "max_dd": r["max_dd"], "reference": {"roc": RULES["b_roc"], "sortino": RULES["b_sort"]}, "would_have_cleared": would,
           "note": "reported, never a pass (MANAGER #48): the forward record decides any book add (owner call)"}
    cnt = {y: dict(v) for y, v in sorted(tl.cnt.items())}
    text = json.dumps({"cell": cell, "rule": rule, "c": c, "go_flag": go_text, "book_check": bk, "es_masters": es_meta, "leg": leg, "checks": chk, "pass": bool(ok), "book_add_reported": add, "es_return_lb": hole_rec, "wide_calendar": W.ca,
                       "hygiene_counts_by_year": cnt, "top_trades": candidate_rows(W, ctx, run, cell, rule, tbis, D15.asset_status(), 20), **stamp(), "prereg_sha256_lf": PREREG_SHA}, indent=1, default=R11.js)
    buf = io.StringIO()                                                                        # the whole printout is built here, before the flag: a formatting error cannot burn the lockbox
    with contextlib.redirect_stdout(buf):
        print("Stage B (lockbox, read once) - the sealed year is the LEG's standalone veto")
        print(f"  {cell} under {rule}: trades {leg['n_pos']:,}, net ${leg['net']:,.0f}, ROC@30k {leg['roc']:.1f}, Sortino {leg['sortino']:.2f}; best 1% of trades ({leg['best_pos_n']}) removed: net ${leg['net_ex_best_pos']:,.0f}")
        print("  " + hole_txt)
        print("  Stage B checks: " + ", ".join(k + (" ok" if v else " FAIL") for k, v in chk.items()) + f" -> {'PASS' if ok else 'FAIL'}")
        print(f"  book add, REPORTED and never part of the pass: #463 + {cell} x{c:.4g} (frozen): LB ROC@30k {r['roc']:.2f} Sortino {r['sortino']:.3f} net ${r['net']:,.0f} -> would "
              f"{'have' if would else 'NOT have'} cleared {RULES['b_roc']:g} / {RULES['b_sort']:g}")
        print("DIVRUN Stage B: " + ("PASS - the leg survives its sealed year: it goes to a computed no-order FORWARD SHADOW (Stage C) with its own bar, logged by research id; the book add above is a report - "
                                    "the forward record decides any book add, and opening any account is the owner's decision (owner call)." if ok else
                                    "FAIL - the leg is vetoed by its sealed year: DIVRUN r1 is dead; ledger + memory."))
    with open(flag, "x") as f:                                                                 # exclusive create: the one read starts here - what is left is two writes and a print
        f.write(pd.Timestamp.now().isoformat())
    with open(os.path.join(OUT, "divrun_stageB.json"), "w") as f:
        f.write(text)
    print(buf.getvalue().rstrip())
    pm = peak_mb()
    if pm:
        print(f"peak memory {pm:,.0f} MB")
    return ok


# ------------------------------------------------------------------ test support: hand-made worlds and calendars, and plain-python recounts of the events, the entry set, the exits, every trade's path and the hedge (independent of the vectorised code)
def close(a, b, tol=1e-9):
    return D15.close(a, b, tol)


def mk_w(Cl, es_level, div=None, spin=None, days=None, F=None, chg=None, msplit=None, tbis=None, U=None, es_off=5000.0, Od=None, es_nan=()):
    """a r15 World on hand-made arrays: Cl = the raw closes; the open = the prior close unless given; F = 1 unless given; every name is in the universe whenever it has a price unless U is given; the ES 16:00 prints: the unadjusted level
    es_level, the roll-corrected one es_level + es_off (so the market's return is the roll-corrected change over the UNADJUSTED level, as D15.es_series has it); es_nan = sessions with no ES print (the masters' holes); div / spin = calendar
    frames (symbol, ex, amt, special / symbol, ex, type) placed through r17_resmom's own div_matrix / spin_matrix, the raw input kept (W.Dr_in / W.Sp_in) for the plain-python recounts"""
    T, Sn = Cl.shape
    days = pd.bdate_range("2024-01-01", periods=T) if days is None else pd.DatetimeIndex(days)
    syms = np.array([f"N{j:02d}" for j in range(Sn)])
    esR = np.array(es_level, float)
    esA = esR + es_off
    for t in es_nan:
        esR[t] = esA[t] = np.nan
    ret = np.full(T, np.nan)
    with np.errstate(invalid="ignore"):
        ret[1:] = (esA[1:] - esA[:-1]) / esR[:-1]
    Dr = M17.div_matrix(div, days, syms)[0] if div is not None else None
    Sp = M17.spin_matrix(spin, days, syms)[0] if spin is not None else None
    zero = lambda: np.zeros((T, Sn), bool)
    Od = np.vstack([Cl[:1], Cl[:-1]]) if Od is None else Od
    F = np.ones((T, Sn)) if F is None else F
    U = (np.isfinite(Od) & np.isfinite(Cl)) if U is None else U
    es = SimpleNamespace(e5=None, c16a=esA, c16r=esR, ret=ret, gap=np.full(T, np.nan), k=np.ones(T))
    nan = np.full((T, Sn), np.nan)
    W = D15.World(days, syms, Od, Cl, np.full((T, Sn), 3e6), F, U, zero() if chg is None else chg, zero() if msplit is None else msplit, zero() if tbis is None else tbis, nan, nan, es)
    M17.with_dividends(W, Dr, Sp)
    return attach_es(W)


def cal_of(rows, spin=()):
    """a calendar as r17_resmom.wide_load hands it back: div = (symbol, ex, amt, special), spin = (symbol, ex, type); rows = (symbol, 'YYYY-MM-DD', amt, special) and (symbol, 'YYYY-MM-DD', 'spin_off' | 'stock_dividend')"""
    df = pd.DataFrame(list(rows), columns=["symbol", "ex", "amt", "special"])
    df["ex"] = pd.to_datetime(df["ex"])
    sp = pd.DataFrame(list(spin), columns=["symbol", "ex", "type"])
    sp["ex"] = pd.to_datetime(sp["ex"])
    return SimpleNamespace(div=df, spin=sp, split=pd.DataFrame({"symbol": [], "ex": [], "type": []}), info={})


def dw_world(seed=5, T=320, planted=True, mod=None):
    """the DIVRUN toy world: 320 weekday sessions (the last is 2025-03-21) from Mon 2024-01-01 x 16 names with the cycle's every case planted by hand (the regular ex-dates are Thursdays, the cycle 91 days; P = 2024-10-03 for the names with
    E1 = 2024-07-04): N00 X on P (X-rule = NO-X exit), a second cycle P' = 2025-01-02, a third event whose P (2025-04-03) is beyond the data; N01 X = P + 5 sessions (late); N02 X = P - 5 (early: inside NO-X's hold); N03 no X; N04 X after
    P + 10; N05 X before the K = 20 entry (x_passed); N06 X = the K = 10 entry + 1 (x_next); N07 monthly, N08 semi-annual (out); N09 gaps 77 / 105 (in: the edges), N10 gaps 76 / 105 and N11 gaps 105 / 106 (out); N12 two SPECIAL dividends among the
    regular ones (ignored: X is the next REGULAR one); N13 two rows on one ex-date (add up) and X = P - 1 (a Wednesday); N14 outside the universe at the entries; N15 a hole in its closes (no beta). N00 and N02 have a deterministic split-safe price
    100 x 1.001^t with an ex-day drop equal to each dividend (the total return = the growth); the other names are beta x ES + noise. mod(d) may edit the arrays / the calendar rows in place before the world is built (d: Cl, Od, F, chg, ms, tb, rows,
    spin). The caller patches spec(win=30, min_pairs=25) for the beta window (this builder does it for the context)"""
    rng = np.random.default_rng(seed)
    days = pd.bdate_range("2024-01-01", periods=T)
    Sn = 16
    es_ret = rng.normal(0.0002, 0.006, T)
    es_ret[0] = 0.0
    esl = 1500.0 * np.cumprod(1.0 + es_ret)
    beta = np.linspace(0.3, 1.5, Sn)
    ret = beta * es_ret[:, None] + rng.normal(0.0, 0.01, (T, Sn))
    ret[0] = 0.0
    Cl = 50.0 * np.cumprod(1.0 + ret, axis=0)
    A0, A1, A2 = "2024-01-04", "2024-04-04", "2024-07-04"
    reg = lambda j, dates, amt=1.0: [(f"N{j:02d}", d, amt, False) for d in dates]
    rows = (reg(0, [A0, A1, A2, "2024-10-03", "2025-01-02"]) + reg(1, [A0, A1, A2, "2024-10-10"]) + reg(2, [A0, A1, A2, "2024-09-26"]) + reg(3, [A0, A1, A2]) + reg(4, [A0, A1, A2, "2024-10-24"])
            + reg(5, [A0, A1, A2, "2024-09-04"]) + reg(6, [A0, A1, A2, "2024-09-20"]) + reg(7, [f"{TS(A0) + pd.Timedelta(days=28 * k):%Y-%m-%d}" for k in range(12)]) + reg(8, [A0, A2, "2025-01-02"])
            + reg(9, [A0, "2024-03-21", A2]) + reg(10, [A0, "2024-03-20", "2024-07-03"]) + reg(11, [A0, "2024-04-18", "2024-08-02"])
            + reg(12, [A0, A1, A2, "2024-10-03"]) + [("N12", "2024-05-16", 2.0, True), ("N12", "2024-07-18", 3.0, True)]
            + reg(13, [A0, A1, A2, "2024-10-02"]) + [("N13", A2, 0.25, False)] + reg(14, [A0, A1, A2, "2024-10-03"]) + reg(15, [A0, A1, A2, "2024-10-03"]))
    spin = []
    dr = lambda s: days.get_loc(TS(s))
    F, chg, ms, tb = np.ones((T, Sn)), np.zeros((T, Sn), bool), np.zeros((T, Sn), bool), np.zeros((T, Sn), bool)
    d = {"Cl": Cl, "F": F, "chg": chg, "ms": ms, "tb": tb, "rows": rows, "spin": spin, "days": days, "dr": dr}
    if mod is not None:
        mod(d)                                                                                 # edits that need the raw prices before the planted paths (e.g. a split's factor)
    if planted:
        for j in (0, 2):
            b = 100.0 * 1.001 ** np.arange(T)
            fac = np.ones(T)
            for _, dd_, amt, _s in sorted((r for r in rows if r[0] == f"N{j:02d}"), key=lambda r: r[1]):
                if dd_ in days:
                    r0 = dr(dd_)
                    fac[r0:] *= 1.0 - amt / (b[r0] * fac[r0 - 1])
            Cl[:, j] = b * fac
    Cl[150:166, 15] = np.nan                                                              # N15: no close on 16 sessions of its beta window
    d["Od"] = Od = np.vstack([Cl[:1], Cl[:-1]])
    if mod is not None:
        mod({**d, "stage": 2})                                                             # edits on the final prices and opens (a split, a raw jump)
    cal = cal_of(rows, spin)
    U = np.isfinite(Cl) & np.isfinite(Od)
    U[170:201, 14] = False                                                                 # N14: outside the universe at both entries (the universe row of the entry session + 1)
    W = mk_w(Cl, esl, div=cal.div, spin=cal.spin, days=days, U=U, F=F, chg=chg, msplit=ms, tbis=tb, Od=Od)
    with spec(win=30, min_pairs=25):
        ctx = make_ctx(W, cal)
    return SimpleNamespace(W=W, ctx=ctx, cal=cal, rows=rows, days=days, dr=dr)


def brute_events(div, days, syms):
    """plain python (no groupby, no searchsorted): the events of a calendar frame - for every REGULAR ex-date E1 of a name on the grid its E2 / E3 (the two regular ex-dates before it), X (the next one), the cycle test, P = E1 + (E1 - E2) days and
    the session rows (the first session on / after a date, -1 if none) -> [dict] in (symbol, E1) order"""
    by = defaultdict(lambda: defaultdict(float))
    for _, r in div.iterrows():
        if not bool(r["special"]):
            by[r["symbol"]][pd.Timestamp(r["ex"])] += float(r["amt"])
    sess = [pd.Timestamp(d) for d in days]
    nxt = sess[-1] + pd.Timedelta(days=1)
    while nxt.weekday() >= 5:
        nxt += pd.Timedelta(days=1)                                                               # the next weekday after the data's last session

    def row_of(d, ahead=False):
        r = next((i for i, s_ in enumerate(sess) if s_ >= d), -1) if d is not None else -1
        return len(sess) if (r < 0 and ahead and d is not None and d <= nxt) else r
    out = []
    for sym in sorted(by):
        if sym not in list(syms):
            continue
        exs = sorted(by[sym])
        for k, e1 in enumerate(exs):
            e2, e3 = (exs[k - 1] if k >= 1 else None), (exs[k - 2] if k >= 2 else None)
            x = exs[k + 1] if k + 1 < len(exs) else None
            cyc, p = False, None
            if e2 is not None and e3 is not None:
                g1, g2 = (e1 - e2).days, (e2 - e3).days
                cyc = 77 <= g1 <= 105 and 77 <= g2 <= 105
                p = e1 + pd.Timedelta(days=g1) if cyc else None
            out.append({"sym": sym, "col": list(syms).index(sym), "e1": e1, "e2": e2, "e3": e3, "cyc": cyc, "p_date": p, "p_row": row_of(p, True), "x_date": x, "x_row": row_of(x), "amt1": by[sym][e1], "e1_row": row_of(e1)})
    return out


def brute_beta(W, e, j):
    """plain python: the OLS slope of name j's split-safe total return on ES's over rows e-251 .. e (the windows of SPEC), by numpy's least squares on the finite pairs; NaN under min_pairs pairs, before a full window, or without ES variation"""
    win = SPEC["win"]
    if e < win - 1:
        return float("nan"), 0
    pr = [(W.Rd[t, j], W.es.ret[t]) for t in range(e - win + 1, e + 1) if math.isfinite(W.Rd[t, j]) and math.isfinite(W.es.ret[t])]
    if len(pr) < SPEC["min_pairs"] or np.ptp([p_[1] for p_ in pr]) == 0:
        return float("nan"), len(pr)
    coef = np.linalg.lstsq(np.array([[1.0, p_[1]] for p_ in pr]), np.array([p_[0] for p_ in pr]), rcond=None)[0]
    return float(coef[1]), len(pr)


def brute_entry(W, evs, K):
    """plain python: the entry set of cell K from the brute events -> (kept [dict: sym, col, e1, e, p, xr, beta], first-reason counts by entry year). The universe is W.U at the next session, the payer test is the cycle of the event, every other
    rule is re-implemented with loops"""
    T = W.T
    kept, reasons = [], defaultdict(Counter)
    for ev in evs:
        if not ev["cyc"] or ev["p_row"] < 0:
            continue
        j, e, p, xr = ev["col"], ev["p_row"] - K, ev["p_row"], ev["x_row"]
        yr = int(W.days[max(e, 0)].year)
        beta, _ = brute_beta(W, e, j) if e >= 0 else (float("nan"), 0)
        why = ("no_history" if e < 0 else "e1_after_entry" if ev["e1"] > W.days[e] else "not_universe" if not (e + 1 <= T - 1 and W.U[e + 1, j]) else "x_passed" if 0 <= xr <= e else "x_next" if xr == e + 1 and xr >= 0
               else "no_close" if not math.isfinite(W.Ac[e, j]) else "no_beta" if not math.isfinite(beta) else None)
        reasons[yr]["events"] += 1
        reasons[yr][why or "entry_set"] += 1
        if why is None:
            kept.append({"sym": ev["sym"], "col": j, "e1": ev["e1"], "e": e, "p": p, "xr": xr, "beta": beta, "e1_row": ev["e1_row"]})
    kept.sort(key=lambda d: (d["e"], d["col"]))
    return kept, reasons


def brute_exit(t, rule, T):
    """plain python: (x, kind, resolved) of a brute entry under an exit rule"""
    e, p, xr = t["e"], t["p"], t["xr"]
    if rule == "NOX":
        x, kind = p - 1, 0
    elif rule == "P10":
        x, kind = p + SPEC["plus"], 0
    else:
        x, kind = ((xr - 1, 0) if (xr >= 0 and e + 2 <= xr <= p + SPEC["plus"]) else (p + SPEC["plus"], 1))
    return x, kind, x <= T - 1


def brute_trade(W, j, e, x, naive, bps, slot=None):
    """plain python: one trade's daily booking (row -> $), its total and the cash it received. The entry at the close of e, a mark at every close of e + 1 .. x (a missing close carries the last mark), the cash dividend per share on every ex-date
    session e < t <= x (r17_resmom.brute_div_amt: the calendar's raw amount over the session's factor where the name has a close, a prior close and a factor), costs of bps a side on the entry notional and the exit value"""
    slot = SPEC["slot"] if slot is None else slot
    c = bps * 1e-4
    px = lambda t: W.Cl[t, j] if naive else W.Ac[t, j]
    entry = last = px(e)
    day, cash, gross = defaultdict(float), 0.0, 0.0
    for t in range(e + 1, x + 1):
        p = px(t)
        cur = p if math.isfinite(p) else last
        d = M17.brute_div_amt(W, t, j)
        if naive and d > 0:
            d = W.Dr_in[t, j]
        g = (cur - last + d) / entry
        day[t] += slot * g
        gross += g
        cash += slot * d / entry
        last = cur
    ve = last / entry
    day[e] -= slot * c
    day[x] -= slot * c * ve
    return day, slot * (gross - c - c * ve), cash


def brute_hedge(W, trs, slot=None):
    """plain python: the hedge as traded and the exact one. trs = [(e, x, beta)] -> (n_t, pnl_t, cost_t of the aggregate whole-MES position; per-trade exact (net pnl), the exact hedge's daily booking)"""
    slot = SPEC["slot"] if slot is None else slot
    T = W.T
    n, pnl, cost = [0.0] * T, [0.0] * T, [0.0] * T
    for t in range(T):
        expo = sum(b * slot for e, x, b in trs if e <= t < x)
        lev = W.esR[t] * MES_PT
        v = expo / lev if math.isfinite(lev) and lev > 0 else 0.0
        n[t] = math.copysign(math.floor(abs(v) + 0.5), v) if v != 0 else 0.0
    for t in range(T):
        pnl[t] = -n[t - 1] * MES_PT * (W.esA[t] - W.esA[t - 1]) if t >= 1 and math.isfinite(W.esA[t]) and math.isfinite(W.esA[t - 1]) else 0.0
        cost[t] = -MES_SIDE * abs(n[t] - (n[t - 1] if t >= 1 else 0.0))
    per, day = [], defaultdict(float)
    for e, x, b in trs:
        w = b * slot
        ctr = w / (W.esR[e] * MES_PT)
        for t in range(e + 1, x + 1):
            day[t] += -ctr * MES_PT * (W.esA[t] - W.esA[t - 1])
        ce, cx = ES_EXACT_BPS * 1e-4 * abs(w), ES_EXACT_BPS * 1e-4 * abs(ctr) * MES_PT * W.esR[x]
        day[e] -= ce
        day[x] -= cx
        per.append(-ctr * MES_PT * (W.esA[x] - W.esA[e]) - ce - cx)
    return n, pnl, cost, per, day


# ------------------------------------------------------------------ selftest: hand-made worlds, no files, no data
def t_constants():
    assert (NREP, SEED, CELLS, EXITS, REGISTERED, NULL_EXITS, AUDIT_N) == (500, 20261005, ("R10", "R20"), ("X", "NOX", "P10"), "NOX", ("X", "NOX"), 50) and KS == {"R10": 10, "R20": 20} and YEARS == tuple(range(2016, 2025))
    assert (WF0, PRE_END, LB0, LB1) == (TS("2016-07-01"), TS("2025-06-29"), TS("2025-06-30"), TS("2026-06-30")) and (S.LB0, S.END) == (LB0, R11.LBX) and (BOOK_WF, BOOK_LB, DEEPEST_WF) == ((93.81, 3.816), (155.54, 4.15), 44849.0)
    assert SPEC == {"slot": 4000.0, "win": 252, "min_pairs": 230, "cyc_lo": 77, "cyc_hi": 105, "plus": 10, "hyg_lead": 5, "pl_lo": 11, "pl_margin": 26, "pl_tries": 20, "own_lead": 25, "tau_lo": -20, "tau_hi": 10, "xtau_lo": -25, "xtau_hi": 5}, "SPEC is the prereg"
    assert (COST_BPS, STRESS_BPS, MES_PT, MES_PT_COST, MES_COMM_RT, ES_EXACT_BPS) == (5.0, (10.0, 20.0), 5.0, 0.363, 1.0, 0.5) and abs(MES_SIDE - 1.4075) < 1e-12, "[V5]: half of 0.363 pt x $5 + $1.00 = $1.4075 a MES a side"
    assert RULES["n"] == 1000 and RULES["roc"] == 15.0 and RULES["years"] == 6 and RULES["best_pct"] == D15.RULES["best_pct"] == 1 and RULES["b_n"] == 100 and (RULES["b_roc"], RULES["b_sort"]) == BOOK_LB
    assert all(RULES[k] is True for k in ("net_pos", "stress", "null", "ex2020", "exbest")) and abs(RULES["a2_roc"] - 98.5005) < 1e-9 and RULES["a2_sort"] == 3.816 and CHECK_BOOK is True, "every registered check is on (the switches are for smoke() only)"
    assert (A2_WIN, A2_TARGET, A2_REPORT) == ((TS("2017-03-01"), TS("2019-02-28")), 0.25, (0.5, 2.0)) and SUBPERIODS[0][1:] == (TS("2016-07-01"), TS("2021-12-31")) and SUBPERIODS[1][1:] == (TS("2022-01-01"), TS("2025-06-29"))
    assert HYG == ("split", "gap", "tbis", "jump") and D15.SPEC["univ"] == 500 and D15.SPEC["px_min"] == 10.0 and D15.SPEC["vol_min"] == 1e6 and D15.SPEC["atr_min"] == 0.5 and D15.SPEC["split_n"] == 14, "DDW r1's universe"
    assert WIDE_CA_SHA == M17.WIDE_CA_SHA == "e5bc8487daf94a6124823bc24b6c382e9fd00237acbab81457fa42ef3b0d83a5" and (OUT.lower().endswith("divrun_r1") or bool(os.environ.get("EDGELOG_DIVRUN_R1")))
    assert (GO_FLAG, READ_FLAG) == ("divrun_stageB_GO.flag", "divrun_stageB_READ.flag")
    assert (REF_SHA, REF_W, REF_COLS) == ("bed7bf8b98d201894471cd3e72bd146bb87260c6cc8d1ac54b8167f923d41819", 0.264, ("date", "book_mtm", "RES", "RAW")) and REF_BOOK_ATOL == 1.0
    assert (REF_FACTS, REF_TOL) == ({"roc": 120.82, "sortino": 3.916, "max_dd": 36526.0}, {"roc": 0.01, "sortino": 0.001, "max_dd": 1.0}), "[X1] the reference's registered WF numbers and tolerances"
    assert REF_CSV_PINNED.replace(chr(92), "/") == "C:/EdgeLog/_anatomy_cache/rocfrontier/resmom_r1/resmom_cells_daily_wf.csv" and os.path.basename(REF_CSV_PINNED.replace(chr(92), "/")) == "resmom_cells_daily_wf.csv"
    pre = " ".join(open(PREREG, encoding="utf-8").read().split())                                           # the registered text carries the numbers this file implements (line breaks normalised)
    for frag in ("77 .. 105", "R10: K = 10", "R20: K = 20", "NO-X = exit at the close of P - 1", "500 draws, seed 20261005", "E1 + 11 .. P - 26 - h", "0.363 pt x $5 + $1.00", "up to 20 tries", "P - 25", "$4,000", "5 / 10 / 20 bps", "PRE-DATA ADDENDUM 2", "[X1] THE BOOK-ADD REPORT IS INCREMENTAL", "[X2] DEEPER DIAGNOSTICS", REF_SHA, "0.264 x RES", "120.82", "3.916", "$36,526",
                 "the cost curve at 0 / 5 / 10 / 20 bps a side", "an incremental pass = both figures above the reference's", "(MDL r1's episode rule applied to the reference)"):
        assert frag in pre, frag
    with contextlib.redirect_stdout(open(os.devnull, "w")):
        assert prereg_ok()["verified"] is True and len(stamp()["harness_sha256"]) == 64 and set(stamp()) >= {"r17_sha256", "r15_sha256", "siporb_sha256", "r11_sha256", "r12_sha256", "r13_sha256", "wide_ca_sha256", "early_close"}
    assert round_half_away([0.49, 0.5, 1.49, 1.5, -0.49, -0.5, -1.5, 0.0]).tolist() == [0.0, 1.0, 1.0, 2.0, -0.0, -1.0, -2.0, 0.0], "whole contracts, a half away from zero; under half a contract = 0"
    assert jyear(["2017-06-30", "2017-07-03", "2016-07-01", "2025-06-27"]).tolist() == [2016, 2017, 2016, 2024]


def t_events():
    """the events: regular quarterly cycles (both gaps in 77 .. 105 days, the edges in, one day out), special dividends ignored (they neither make a cycle nor are X), monthly / semi-annual payers out, rows of one ex-date added, P = E1 +
    (E1 - E2) days snapped to the NEXT session (a weekend, a holiday), X = the next REGULAR ex-date - against a plain-python recount of every field"""
    dw = dw_world()
    W, ev = dw.W, dw.ctx.ev
    bz = brute_events(dw.cal.div, W.days, W.syms)
    assert ev.n == len(bz) and ev.n > 40, (ev.n, len(bz))
    for i, b in enumerate(bz):
        assert ev.sym[i] == b["sym"] and ev.col[i] == b["col"] and TS(ev.e1[i]) == b["e1"] and bool(ev.cyc[i]) == b["cyc"] and int(ev.p_row[i]) == b["p_row"] and int(ev.x_row[i]) == b["x_row"] and int(ev.e1_row[i]) == b["e1_row"], (i, b)
        assert (pd.isna(ev.p_date[i]) and b["p_date"] is None) or TS(ev.p_date[i]) == b["p_date"], (i, b)
        assert (pd.isna(ev.x_date[i]) and b["x_date"] is None) or TS(ev.x_date[i]) == b["x_date"], (i, b)
        assert abs(ev.amt1[i] - b["amt1"]) < 1e-12
    by = lambda sym: [i for i in range(ev.n) if ev.sym[i] == sym]
    cyc = lambda sym: [bool(ev.cyc[i]) for i in by(sym)]
    d = lambda s: np.datetime64(s)
    i0 = by("N00")
    assert [bool(ev.cyc[i]) for i in i0] == [False, False, True, True, True] and ev.p_date[i0[2]] == d("2024-10-03") and ev.x_date[i0[2]] == d("2024-10-03") and ev.p_row[i0[2]] == ev.x_row[i0[2]] == dw.dr("2024-10-03")
    assert ev.p_row[i0[3]] == dw.dr("2025-01-02") and ev.x_row[i0[3]] == dw.dr("2025-01-02") and ev.p_row[i0[4]] == -1 and ev.cyc[i0[4]] and ev.x_row[i0[4]] == -1, "the third event: E1 = 2025-01-02, P = 2025-04-03 is after the last session -> p_row -1; X none"
    assert not any(cyc("N07")) and not any(cyc("N08")), "monthly (28-day gaps) and semi-annual (182) payers are out"
    assert cyc("N09") == [False, False, True] and ev.p_date[by("N09")[2]] == d("2024-10-17") and (ev.gap1[by("N09")[2]], ev.gap2[by("N09")[2]]) == (105.0, 77.0), "77 and 105 are in: both edges, inclusive"
    assert not any(cyc("N10")) and not any(cyc("N11")) and (ev.gap1[by("N10")[2]], ev.gap2[by("N10")[2]]) == (105.0, 76.0) and (ev.gap1[by("N11")[2]], ev.gap2[by("N11")[2]]) == (106.0, 105.0), "76 and 106 are one day out"
    i12 = by("N12")
    assert len(i12) == 4 and cyc("N12") == [False, False, True, True] and ev.x_date[i12[2]] == d("2024-10-03") and ev.p_date[i12[2]] == d("2024-10-03"), "N12: the two SPECIAL dividends are neither E1 / E2 / E3 nor X"
    assert abs(ev.amt1[by("N13")[2]] - 1.25) < 1e-12 and len(by("N13")) == 4, "two regular rows on one ex-date add up and are one event"
    assert ev.x_date[by("N01")[2]] == d("2024-10-10") and ev.x_row[by("N01")[2]] - ev.p_row[by("N01")[2]] == 5 and ev.x_row[by("N02")[2]] - ev.p_row[by("N02")[2]] == -5 and ev.x_row[by("N03")[2]] == -1
    # P's snapping: a weekend P moves to the next session, a holiday too (a session missing from the data); the cases: E1 = P - 90 days, E2 = E1 - 90, E3 = E1 - 180
    cases = {}
    for nm, p_day in (("N00", "2024-09-29"), ("N01", "2024-06-12"), ("N02", "2024-09-30"), ("N03", "2024-09-28")):             # a Sunday, a missing Wednesday, a Monday (a session), a Saturday
        p_ = TS(p_day)
        cases[nm] = (p_ - pd.Timedelta(days=270), p_ - pd.Timedelta(days=180), p_ - pd.Timedelta(days=90), p_)
    days2 = pd.bdate_range("2023-10-02", periods=330)
    days2 = days2.delete(days2.get_loc(TS("2024-06-12")))                                                                       # N01's P is the missing Wednesday: the next session is Thu 06-13
    rows = []
    for nm, (a, b, c_, p_) in cases.items():
        rows += [(nm, f"{a:%Y-%m-%d}", 1.0, False), (nm, f"{b:%Y-%m-%d}", 1.0, False), (nm, f"{c_:%Y-%m-%d}", 1.0, False)]
    evs = build_events(cal_of(rows).div, days2, np.array(["N00", "N01", "N02", "N03"]))
    pr = {sy: pd.Timestamp(days2[evs.p_row[i]]) for i, sy in enumerate(evs.sym) if evs.cyc[i]}
    assert pr == {"N00": TS("2024-09-30"), "N01": TS("2024-06-13"), "N02": TS("2024-09-30"), "N03": TS("2024-09-30")}, pr
    assert {sy: pd.Timestamp(evs.p_date[i]) for i, sy in enumerate(evs.sym) if evs.cyc[i]} == {"N00": TS("2024-09-29"), "N01": TS("2024-06-12"), "N02": TS("2024-09-30"), "N03": TS("2024-09-28")}, "P's calendar date is kept; its row is the next session"
    bz2 = brute_events(cal_of(rows).div, days2, ["N00", "N01", "N02", "N03"])
    assert [b["p_row"] for b in bz2] == [int(v) for v in evs.p_row] and [b["cyc"] for b in bz2] == [bool(v) for v in evs.cyc]
    # P just after the data (rows_of ahead=True, P only): the first session the data does not hold - the next weekday after the last session - is row len(dv) by date arithmetic, any later date stays -1; the plain rule never invents a row
    dv = np.asarray(pd.bdate_range("2024-01-01", periods=10)).astype("datetime64[ns]")                          # the last session is Fri 2024-01-12
    for dd, want_ahead, want_plain in (("2024-01-12", 9, 9), ("2024-01-13", 10, -1), ("2024-01-14", 10, -1), ("2024-01-15", 10, -1), ("2024-01-16", -1, -1), ("2024-01-02", 1, 1), ("2024-01-06", 5, 5)):
        assert rows_of(dv, [np.datetime64(dd)], ahead=True)[0] == want_ahead and rows_of(dv, [np.datetime64(dd)])[0] == want_plain, dd
    assert rows_of(dv, [np.datetime64("NaT")], ahead=True)[0] == -1 and rows_of(dv[:8], [np.datetime64("2024-01-11")], ahead=True)[0] == 8 and rows_of(dv[:8], [np.datetime64("2024-01-12")], ahead=True)[0] == -1, "after a Wednesday the next weekday is Thursday only"
    # a name that is not on the grid is dropped (counted); a calendar with no rows gives no event
    ev3 = build_events(cal_of(rows + [("ZZZ", "2024-01-04", 1.0, False)]).div, days2, np.array(["N00", "N01", "N02", "N03"]))
    assert ev3.n == evs.n and ev3.counts["rows_not_on_the_grid"] == 1 and build_events(None, days2, np.array(["N00"])).n == 0 and build_events(cal_of([]).div, days2, np.array(["N00"])).n == 0


def t_entry():
    with spec(win=30, min_pairs=25):                                                                           # the toy world's beta window: 30 sessions, at least 25 pairs
        return _t_entry()


def _t_entry():
    """the entry set of each cell and the three exit rules against a plain-python recount (every event's first reason by entry year, the kept events with their rows and betas), the hand cases of the toy world (X on P / late / early / none / after
    P + 10 / passed / the next session, outside the universe, no beta, P beyond the data), the exits (X-rule incl. the P + 10 fallback, NO-X, P + 10) and where X fell against P - 1"""
    dw = dw_world()
    W, ctx = dw.W, dw.ctx
    evs = brute_events(dw.cal.div, W.days, W.syms)
    out = {}
    with spec(win=30, min_pairs=25):
        for K in (10, 20):
            es = entry_set(W, ctx, K)
            kept, reasons = brute_entry(W, evs, K)
            assert es.n == len(kept) and [(ctx.ev.sym[i], int(e_), int(p_), int(x_)) for i, e_, p_, x_ in zip(es.idx, es.e, es.p, es.xr)] == [(k["sym"], k["e"], k["p"], k["xr"]) for k in kept], K
            assert close(es.beta, [k["beta"] for k in kept], 1e-9) and (es.npair >= 25).all() and es.e1r.tolist() == [k["e1_row"] for k in kept]
            assert {y: dict(c) for y, c in es.cnt.items()} == {y: dict(c) for y, c in reasons.items()}, (K, dict(es.cnt), dict(reasons))
            out[K] = es
    sy = lambda es: [(str(ctx.ev.sym[i]), TS(ctx.ev.e1[i]).strftime("%m-%d")) for i in es.idx]
    s10, s20 = sy(out[10]), sy(out[20])
    for nm in ("N00", "N01", "N02", "N03", "N04", "N09", "N12", "N13"):
        assert (nm, "07-04") in s10, nm
    assert ("N05", "07-04") not in s10 and ("N05", "07-04") not in s20, "N05: X before both entries - no trade"
    assert ("N06", "07-04") not in s10 and ("N06", "07-04") in s20, "N06: X = the K = 10 entry + 1 (x_next: no trade); for K = 20 it is two or more sessions after the entry: a trade"
    assert ("N14", "07-04") not in s10 and ("N14", "07-04") not in s20 and ("N15", "07-04") not in s10 and ("N15", "07-04") not in s20, "N14 outside the universe at the entry close, N15 without 25 pairs"
    assert not any(nm in ("N07", "N08", "N10", "N11") for nm, _ in s10 + s20), "monthly / semi-annual / one-day-out cycles never trade"
    c10, c20 = out[10].cnt[2024], out[20].cnt[2024]
    assert c10["x_next"] == 1 and c20["x_next"] == 0 and c10["x_passed"] >= 1 and c20["x_passed"] >= 1 and c10["not_universe"] >= 1 and c10["no_beta"] >= 1 and c20["no_beta"] >= 1, (dict(c10), dict(c20))
    # the exits
    T = W.T
    es = out[10]
    pos = {(str(ctx.ev.sym[i]), TS(ctx.ev.e1[i]).strftime("%m-%d")): q for q, i in enumerate(es.idx)}
    q0, q1, q2, q3, q4 = (pos[("N00", "07-04")], pos[("N01", "07-04")], pos[("N02", "07-04")], pos[("N03", "07-04")], pos[("N04", "07-04")])
    xx, kx, rx = rule_exits(es, "X", T)
    xn, kn, rn = rule_exits(es, "NOX", T)
    xp, kp, rp = rule_exits(es, "P10", T)
    P = dw.dr("2024-10-03")
    assert es.p[q0] == P and es.e[q0] == P - 10
    assert (xx[q0], kx[q0]) == (P - 1, 0) and (xn[q0], xp[q0]) == (P - 1, P + 10), "N00: X on P - the X-rule and NO-X exit on the same close"
    assert (xx[q1], kx[q1]) == (dw.dr("2024-10-10") - 1, 0) and xn[q1] == P - 1 and xp[q1] == P + 10, "N01: X = P + 5 (late but inside P + 10): the X-rule exits at X - 1, NO-X still at P - 1"
    assert (xx[q2], kx[q2]) == (dw.dr("2024-09-26") - 1, 0) and xn[q2] == P - 1 and xp[q2] == P + 10, "N02: X = P - 5: the X-rule exits at X - 1, NO-X holds through X"
    assert (xx[q3], kx[q3]) == (P + 10, 1) and xn[q3] == P - 1, "N03: no X on the calendar: the X-rule falls back to the close of P + 10 (kind 1)"
    assert (xx[q4], kx[q4]) == (P + 10, 1), "N04: X = P + 15 > P + 10: the fallback"
    assert rx.all() and rn.all() and rp.all() and kn.sum() == 0 and kp.sum() == 0 and (ctx.ev.p_row[(ctx.ev.sym == "N00") & ctx.ev.cyc] == [P, dw.dr("2025-01-02"), -1]).all(), "T = 320: every exit is inside the data; N00's third event has P beyond it"
    bx = {i: brute_exit(k, "X", T) for i, k in enumerate(brute_entry(W, evs, 10)[0])}
    assert [(int(a), int(b)) for a, b in zip(xx, kx)] == [bx[i][:2] for i in range(es.n)]
    assert [bool(v) for v in rx] == [bx[i][2] for i in range(es.n)]
    for rule in EXITS:
        x_, k_, r_ = rule_exits(es, rule, T)
        want = [brute_exit(k, rule, T) for k in brute_entry(W, evs, 10)[0]]
        assert x_.tolist() == [w[0] for w in want] and k_.tolist() == [w[1] for w in want] and r_.tolist() == [w[2] for w in want], rule
    # a P + 10 exit past the data is unresolved (out of the cell AND the null, counted): the last event of N00 (X none, P' = 2025-01-02 = row 263 -> P' + 10 = 273 < 330 is resolved); truncate the data to see it
    es_t = SimpleNamespace(p=np.array([100, 100]), e=np.array([80, 80]), xr=np.array([-1, 104]))
    assert rule_exits(es_t, "P10", 105)[2].tolist() == [False, False] and rule_exits(es_t, "NOX", 105)[2].tolist() == [True, True] and rule_exits(es_t, "X", 105)[2].tolist() == [False, True] and rule_exits(es_t, "X", 111)[2].tolist() == [True, True], \
        "no X by the data's end and P + 10 past it: unresolved for the X-rule; X known (inside P + 10): the exit X - 1 is inside the data"
    dwu = dw_world(T=330)                                                                                      # T = 330: N00's third event has P = 2025-04-03 inside the data but P + 10 past it
    with spec(win=30, min_pairs=25):
        esu = entry_set(dwu.W, dwu.ctx, 10)
    for rule, n_unres in (("X", 1), ("NOX", 0), ("P10", 1)):
        tu = trade_set(dwu.W, dwu.ctx, esu, rule, "registered", dwu.W.days[0], dwu.W.days[-1])
        assert sum(c.get("unresolved", 0) for c in tu.cnt.values()) == n_unres and tu.n == esu.n - n_unres - sum(c.get(k, 0) for c in tu.cnt.values() for k in ("pre_split", "hold_split", "pre_gap", "hold_gap", "hold_special", "hold_spin")), (rule, dict(tu.cnt))
    xq = x_position(es)
    assert xq["n"] == es.n and xq["before"] >= 1 and xq["at"] >= 1 and xq["after"] >= 1 and xq["before"] + xq["at"] + xq["after"] == xq["n"]
    assert xq["before"] == int(((es.xr >= 0) & (es.xr < es.p - 1)).sum()) and xq["at"] == int((es.xr == es.p - 1).sum())
    # the trade sets: stretch by EXIT date (inclusive both ends), unresolved counted
    allw = trade_set(W, ctx, es, "NOX", "registered", W.days[0], W.days[-1])
    for rule in EXITS:
        tr_ = trade_set(W, ctx, es, rule, "registered", W.days[0], W.days[-1])
        unres = sum(c.get("unresolved", 0) for c in tr_.cnt.values())
        removed = sum(v for c in tr_.cnt.values() for k, v in c.items() if k not in ("trades", "unresolved", "kept_naive"))
        want = [brute_exit(k, rule, T)[2] for k in brute_entry(W, evs, 10)[0]]
        assert tr_.n == es.n - unres - removed == sum(want) and unres == len(want) - sum(want) and removed == 0 and tr_.n > 0, (rule, tr_.n, es.n, unres, removed)
    x_first = int(allw.x.min())
    inc = trade_set(W, ctx, es, "NOX", "registered", W.days[x_first], W.days[-1])
    exc = trade_set(W, ctx, es, "NOX", "registered", W.days[x_first + 1], W.days[-1])
    assert inc.n > exc.n and (inc.x >= x_first).all() and (exc.x > x_first).all() and inc.n - exc.n == int((allw.x == x_first).sum()), "trades are counted by EXIT date, both ends of the stretch inclusive"
    last_x = int(allw.x.max())
    assert trade_set(W, ctx, es, "NOX", "registered", W.days[0], W.days[last_x]).n == allw.n and trade_set(W, ctx, es, "NOX", "registered", W.days[0], W.days[last_x - 1]).n < allw.n
    return True


def t_beta():
    """the hedge's beta = r17_resmom's regression convention (OLS of the split-safe TOTAL daily return on ES's, intercept, over the 252 sessions entry-251 .. entry, ES-hole sessions skipped, spin-off / stock-dividend sessions left out, at least
    230 pairs): the rolling one-pass version equals a plain-python least-squares recount at EVERY (row, name), the pair counts equal the recount's, r17_resmom.rm_scores' closed form (dy, dm) gives the same slope, 230 pairs is in and 229 out
    (here 25 / 24 on the shrunk window), a window that is not full has none"""
    with spec(win=30, min_pairs=25):
        rng = np.random.default_rng(7)
        T, Sn = 90, 8
        es_ret = rng.normal(0.0, 0.01, T)
        es_ret[0] = 0.0
        es = 1500.0 * np.cumprod(1.0 + es_ret)
        ret = np.linspace(0.4, 1.4, Sn) * es_ret[:, None] + rng.normal(0.0, 0.012, (T, Sn))
        ret[0] = 0.0
        Cl = 40.0 * np.cumprod(1.0 + ret, axis=0)
        Cl[40:44, 1] = np.nan                                                                    # a stretch with no close: its returns are missing
        Cl[20, 2] = np.nan
        Cl[60:, 3] = np.nan                                                                      # stops printing
        Cl[[89, 75, 65], 4] = np.nan                                                             # 1 + 2 + 2 returns lost at r = 89: 25 pairs of 30 - exactly min_pairs
        Cl[[80, 75, 65], 5] = np.nan                                                             # 2 + 2 + 2 lost: 24 pairs - one under
        div = cal_of([("N06", "2024-02-22", 0.5, False), ("N06", "2024-03-14", 0.5, False), ("N07", "2024-03-01", 0.4, False)]).div
        spin = cal_of([], spin=[("N07", "2024-03-06", "spin_off"), ("N06", "2024-02-15", "stock_dividend")]).spin
        W = mk_w(Cl, es, div=div, spin=spin, es_nan=(30, 31, 50))                                # ES holes: no pair on 30, 31 (the hole and the session after it) and 50, 51
        beta, n = rolling_beta(W)
        assert beta.shape == (T, Sn) and n.dtype == np.int32 and not np.isfinite(beta[:29]).any() and (n[:29] == 0).all(), "a window that is not full has no beta"
        nfin = 0
        for r in range(T):
            for j in range(Sn):
                want, wn = brute_beta(W, r, j)
                got = beta[r, j]
                assert (math.isnan(want) and math.isnan(got)) or abs(got - want) <= 1e-9 * max(1.0, abs(want)), (r, j, got, want)
                assert n[r, j] == wn, (r, j, n[r, j], wn)
                nfin += math.isfinite(got)
        assert nfin > 200 and (pair_counts(W) == n).all(), "pair_counts counts which returns EXIST, the same numbers the regression used"
        assert n[89, 4] == 25 and np.isfinite(beta[89, 4]) and n[89, 5] == 24 and not np.isfinite(beta[89, 5]), "exactly 25 pairs is in, 24 is out"
        assert n[59, 3] >= 25 and np.isfinite(beta[59, 3]) and not np.isfinite(beta[89, 3]), "a name that stopped printing loses its beta once the window holds too few pairs"
        # r17_resmom.rm_scores' closed form on the same window (its first lines: the means over the finite pairs, dm x dy / dm x dm)
        for r, j in ((60, 0), (75, 6), (85, 7), (89, 4)):
            a = r - SPEC["win"] + 1
            R, m = np.asarray(W.Rd[a:r + 1][:, [j]]), np.asarray(W.es.ret[a:r + 1], float)
            ok = np.isfinite(R) & np.isfinite(m)[:, None]
            nn = ok.sum(axis=0)
            my, mm = np.where(ok, R, 0.0).sum(axis=0) / nn, np.where(ok, m[:, None], 0.0).sum(axis=0) / nn
            dy, dm = np.where(ok, R - my, 0.0), np.where(ok, m[:, None] - mm, 0.0)
            assert abs(float(((dm * dy).sum(axis=0) / (dm * dm).sum(axis=0))[0]) - beta[r, j]) < 1e-10, (r, j)
        # the ES-hole sessions are skipped, never filled: a hole session, the session after it (its return would span the hole) and the one after that (its denominator is the hole's print) give no pair
        assert W.es_hole.tolist() == [t in (30, 31, 50) for t in range(T)], "the ES holes are marked where the master has no 16:00 print"
        assert np.flatnonzero(~np.isfinite(W.es.ret)).tolist() == [0, 30, 31, 32, 50, 51], "no ES return across a hole"
        assert n[46, 0] == 27 and n[47, 0] == 27 and n[60, 0] == 26 and n[89, 0] == 30, "the pairs of a window spanning a hole: 30 sessions less the hole's lost returns"
        # the spin-off / stock-dividend session of a name is left out of its beta window (r17_resmom's [D2]): N07's session 2024-03-06 has no pair
        s6 = W.days.get_loc(TS("2024-03-06"))
        assert not np.isfinite(W.Rd[s6, 7]) and np.isfinite(W.Rn[s6, 7]) and n[s6, 7] == n[s6, 0] - 1 and n[s6 - 1, 7] == n[s6 - 1, 0], "the spin-off session is the one pair N07 loses"
    return True


def t_hedge():
    """[V5] the hedge as traded - ONE aggregate short ES position in whole MES at each 16:00 print: round(sum of beta x $4,000 over the trades open at that print / (the unadjusted print x $5)), 0 under half a contract, a half rounded away from
    zero, a trade hedged from its entry print to the one before its exit print, each change paying half of (0.363 pt x $5 + $1.00) = $1.4075 a contract; against the exact fractional hedge (beta x $4,000 of ES, ES 0.5 bps a side) - on hand
    numbers, then 60 random trades (negative betas too) against a plain-python recount, and an ES hole carrying the last print"""
    T = 12
    W = SimpleNamespace(T=T, es=SimpleNamespace(c16a=5000.0 + np.array([0, 10, 20, 15, 25, 35, 30, 40, 50, 45, 55, 65], float), c16r=np.full(T, 1000.0)))
    attach_es(W)
    tr = SimpleNamespace(n=4, e=np.array([1, 3, 2, 10]), x=np.array([6, 9, 4, 11]), beta=np.array([1.0, 0.55, 0.625, 0.625]))      # A, B, C, D
    hg = hedge_agg(W, tr)
    assert hg.n.tolist() == [0, 1, 1, 2, 1, 1, 0, 0, 0, 0, 1, 0], hg.n.tolist()                       # t=1: A 0.8 -> 1; t=2: A + C 1.3 -> 1; t=3: + B 1.74 -> 2; t=4: C is off (exit print): A + B 1.24 -> 1; t=6: A off: B 0.44 -> 0; t=10: D 0.5 -> 1 (a half rounds away)
    assert close(hg.expo, [0, 4000, 6500, 8700, 6200, 6200, 2200, 2200, 2200, 0, 2500, 0]) and (hg.n == round_half_away(hg.expo / 5000.0)).all()
    assert close(hg.pnl, [0, 0, -50, 25, -100, -50, 25, 0, 0, 0, 0, -50]), hg.pnl.tolist()            # -n(t-1) x $5 x the roll-corrected change
    assert close(hg.cost, [0, -1.4075, 0, -1.4075, -1.4075, 0, -1.4075, 0, 0, 0, -1.4075, -1.4075]), hg.cost.tolist()
    hx = hedge_exact(W, tr)
    assert close(hx.ctr, [0.8, 0.44, 0.5, 0.5]) and close(hx.gross, [-80.0, -66.0, -12.5, -25.0]) and close(hx.pnl, [-80.4, -66.22, -12.75, -25.25]), (hx.gross.tolist(), hx.pnl.tolist())
    assert abs(hx.daily.sum() - hx.pnl.sum()) < 1e-12, "the exact hedge's daily booking adds up to its trades' P&L"
    n_, pnl_, cost_, per_, day_ = brute_hedge(W, list(zip(tr.e.tolist(), tr.x.tolist(), tr.beta.tolist())))
    assert close(per_, hx.pnl) and close(hx.daily, [day_.get(t, 0.0) for t in range(T)]) and close(hg.n, n_) and close(hg.pnl, pnl_) and close(hg.cost, cost_)
    # random trades, negative betas included (a net negative beta is a LONG ES hedge), ES level varying
    rng = np.random.default_rng(3)
    T = 80
    lvl = 1200.0 * np.cumprod(1.0 + rng.normal(0.0, 0.01, T))
    W = SimpleNamespace(T=T, es=SimpleNamespace(c16a=lvl + 800.0, c16r=lvl))
    attach_es(W)
    with spec(slot=40000.0):                                                                           # a bigger slot so that the contracts are not all 0 / 1 / 2
        e = rng.integers(2, 60, 60)
        x = e + rng.integers(1, 15, 60)
        b = rng.uniform(-1.0, 2.0, 60)
        tr = SimpleNamespace(n=60, e=e, x=x, beta=b)
        hg, hx = hedge_agg(W, tr), hedge_exact(W, tr)
        n_, pnl_, cost_, per_, day_ = brute_hedge(W, list(zip(e.tolist(), x.tolist(), b.tolist())))
        assert close(hg.n, n_) and close(hg.pnl, pnl_) and close(hg.cost, cost_) and close(hx.pnl, per_) and close(hx.daily, [day_.get(t, 0.0) for t in range(T)]), "the vectorised hedges equal the plain-python recount"
        assert (hg.n < 0).any() and (hg.n > 0).any() and np.abs(hg.n).max() >= 3, "short and long positions, several contracts"
        gap = (hg.pnl + hg.cost) - hx.daily
        assert np.isfinite(gap).all() and np.abs(gap).max() > 1.0, "the whole-MES hedge and the exact fractional one are not the same series"
    # the rounding gap: at a flat ES level the aggregate's whole-MES count is the exact fractional hedge's contracts rounded to the nearest whole one, so on every session the two earn within half a contract's move of each other
    W2 = SimpleNamespace(T=T, es=SimpleNamespace(c16a=800.0 + np.cumsum(rng.normal(0.0, 6.0, T)), c16r=np.full(T, 1000.0)))
    attach_es(W2)
    with spec(slot=40000.0):
        hg2, hx2 = hedge_agg(W2, tr), hedge_exact(W2, tr)
    Cx = np.array([sum(hx2.ctr[i] for i in range(tr.n) if tr.e[i] + 1 <= t <= tr.x[i]) for t in range(T)])
    d_exact = np.array([0.0] + [-Cx[t] * MES_PT * (W2.esA[t] - W2.esA[t - 1]) for t in range(1, T)])
    mv = MES_PT * np.abs(np.diff(W2.esA, prepend=W2.esA[0]))
    assert (np.abs(hg2.pnl - d_exact) <= 0.5 * mv + 1e-9).all() and (np.abs(hg2.pnl - d_exact) > 0.05 * mv).any(), (np.abs(hg2.pnl - d_exact) / np.maximum(mv, 1e-12)).max()
    # an ES hole: the last print is carried, nothing earned that session, the whole move paid at the next one
    T = 12
    W = SimpleNamespace(T=T, es=SimpleNamespace(c16a=5000.0 + np.array([0, 10, 20, 15, np.nan, 35, 30, 40, 50, 45, 55, 65]), c16r=np.array([1000.0] * 4 + [np.nan] + [1000.0] * 7)))
    attach_es(W)
    assert W.es_hole.tolist() == [False] * 4 + [True] + [False] * 7 and W.esA[4] == W.esA[3] and W.esR[4] == 1000.0
    tr = SimpleNamespace(n=1, e=np.array([1]), x=np.array([8]), beta=np.array([1.0]))
    hg = hedge_agg(W, tr)
    assert hg.pnl[4] == 0.0 and abs(hg.pnl[5] - (-1 * 5.0 * (W.esA[5] - W.esA[3]))) < 1e-12 and hg.n[4] == 1 and hg.cost[4] == 0.0, "the hole session earns nothing and the next pays the move over both days"
    return True


def t_pnl():
    """the stock leg of a trade: on hand numbers - N00 (deterministic split-safe price, X on P): the X-rule / NO-X exit at P - 1 holds no dividend and no ex-day drop, P + 10 holds X: the cash is received per share held and the drop is in the
    price; N02 (X = P - 5): the X-rule exits at X - 1 (nothing), NO-X holds through X (cash + drop) - the net of the two is the growth; 5 bps of the entry notional and of the exit value; then EVERY trade of the toy world (3 exit rules x 2 cells x
    both readings x 5 / 10 bps) against the plain-python recount: per-trade totals, the daily bookings, the cash, the positions held, plus a carried missing close and an exit with no close (the trade stopped printing)"""
    c = COST_BPS * 1e-4
    with spec(win=30, min_pairs=25):
        dw = dw_world()
        W, ctx = dw.W, dw.ctx
        P, dr = dw.dr("2024-10-03"), dw.dr
        es = entry_set(W, ctx, 10)
        out = {}
        for rule in EXITS:
            tr = trade_set(W, ctx, es, rule, "registered", W.days[0], W.days[-1])
            out[rule] = (tr, run_bundle(W, prepare(W, tr)))
        idx = lambda rule, nm: next(i for i in range(out[rule][0].n) if ctx.ev.sym[out[rule][0].ev[i]] == nm and TS(ctx.ev.e1[out[rule][0].ev[i]]) == TS("2024-07-04"))
        fv = lambda rule, nm: (out[rule][1].pos.stock[idx(rule, nm)], out[rule][1].div_usd[idx(rule, nm)], int(out[rule][0].e[idx(rule, nm)]), int(out[rule][0].x[idx(rule, nm)]))
        Ac = W.Ac
        for rule, nm, e_, x_, cash in (("X", "N00", P - 10, P - 1, 0.0), ("NOX", "N00", P - 10, P - 1, 0.0), ("P10", "N00", P - 10, P + 10, 1.0), ("X", "N02", P - 10, dr("2024-09-26") - 1, 0.0),
                                       ("NOX", "N02", P - 10, P - 1, 1.0), ("P10", "N02", P - 10, P + 10, 1.0)):
            got, div, ee, xx = fv(rule, nm)
            j = int(W.syms.tolist().index(nm))
            assert (ee, xx) == (e_, x_), (rule, nm, ee, xx)
            want = 4000.0 * ((Ac[x_, j] + cash) / Ac[e_, j] - 1.0 - c - c * Ac[x_, j] / Ac[e_, j])
            assert abs(got - want) < 1e-9 and abs(div - 4000.0 * cash / Ac[e_, j]) < 1e-9, (rule, nm, got, want, div)
            if cash:
                assert abs((Ac[x_, j] + cash) / Ac[e_, j] - 1.001 ** (x_ - e_)) < 2e-3, "the dividend and the planted ex-day drop offset: the total return is the 0.1% a day growth (to the compounding on the lower price)"
            else:
                assert abs(Ac[x_, j] / Ac[e_, j] - 1.001 ** (x_ - e_)) < 2e-3
        gx, gn = fv("NOX", "N02")[0], fv("X", "N02")[0]
        assert gx > 4000.0 * (1.001 ** 9 - 1.0 - 2 * c * 1.01) - 10 and abs(gx - gn - 4000.0 * (Ac[P - 1, 2] / Ac[P - 10, 2] - Ac[dr("2024-09-25"), 2] / Ac[P - 10, 2]) - 4000.0 * c * (Ac[dr("2024-09-25"), 2] - Ac[P - 1, 2]) / Ac[P - 10, 2] - 4000.0 * 1.0 / Ac[P - 10, 2]) < 1e-6, \
            "NO-X holds 4 sessions longer than the X-rule on N02 and gets the dividend"
        # every trade of every set against the recount
        for reading in ("registered", "naive"):
            for K in (10, 20):
                es = entry_set(W, ctx, K)
                for rule in EXITS:
                    tr = trade_set(W, ctx, es, rule, reading, W.days[0], W.days[-1])
                    bu = prepare(W, tr)
                    for bps in (5.0, 10.0):
                        run = run_bundle(W, bu, bps)
                        tot, cashs, day = [], [], defaultdict(float)
                        for i in range(tr.n):
                            d_, t_, cs_ = brute_trade(W, int(tr.col[i]), int(tr.e[i]), int(tr.x[i]), bool(tr.naive[i]), bps)
                            tot.append(t_)
                            cashs.append(cs_)
                            for r_, v_ in d_.items():
                                day[r_] += v_
                        sd, sp = stock_pnl(W, tr, bu.pa, bps)
                        assert close(sp, tot, 1e-8) and close(sd, [day.get(t, 0.0) for t in range(W.T)], 1e-8), (reading, K, rule, bps)
                        assert close(run.div_usd, cashs, 1e-8) and close(run.pos.stock, tot, 1e-8) and abs(run.x_unhedged.sum() - sum(tot)) < 1e-6 and run.n_pos == tr.n
                        assert close(run.pos.pnl, np.asarray(tot) + bu.hx.pnl, 1e-8) and close(run.x, sd + bu.hg.pnl + bu.hg.cost, 1e-8) and close(run.x_exact, sd + bu.hx.daily, 1e-8)
                    cnt = np.zeros(W.T)
                    for i in range(tr.n):
                        cnt[tr.e[i]:tr.x[i] + 1] += 1
                    assert close(bu.cnt, cnt), "positions held on rows e .. x"
    # a missing close inside the hold carries the mark (a zero day, the whole move on the next), an exit with no close = stopped printing: it exits at its last mark
    def mod(d):
        if d.get("stage") == 2:
            d["Cl"][192, 1] = np.nan
            d["Cl"][197, 1] = np.nan
            d["Od"][:] = np.vstack([d["Cl"][:1], d["Cl"][:-1]])
    with spec(win=30, min_pairs=25):
        dw = dw_world(mod=mod)
        W, ctx = dw.W, dw.ctx
        es = entry_set(W, ctx, 10)
        tr = trade_set(W, ctx, es, "NOX", "registered", W.days[0], W.days[-1])
        i = next(i for i in range(tr.n) if ctx.ev.sym[tr.ev[i]] == "N01" and TS(ctx.ev.e1[tr.ev[i]]) == TS("2024-07-04"))
        pa = stock_paths(W, tr)
        e_, x_ = int(tr.e[i]), int(tr.x[i])
        assert (e_, x_) == (188, 197) and pa.stopped[i] and not pa.stopped[[q for q in range(tr.n) if q != i]].any(), "the exit session has no close: stopped printing"
        el = np.flatnonzero(pa.idx == i)
        Gi = pa.G[el]
        k192, k193, k197 = 192 - e_, 193 - e_, 197 - e_
        assert Gi[k192] == 0.0 and Gi[k193] != 0.0 and Gi[k197] == 0.0, "the missing close carries the mark: nothing on that session, the move on the next; an exit with no close books nothing"
        last = W.Ac[196, 1]
        assert abs(pa.ve[i] - last / W.Ac[e_, 1]) < 1e-12, "the exit value is the last mark"
        d_, t_, _ = brute_trade(W, 1, e_, x_, False, 5.0)
        assert abs(stock_pnl(W, tr, pa, 5.0)[1][i] - t_) < 1e-8
    return True


def t_hygiene():
    """[V3] + the DATA paragraph: a trade is flagged by a registered split / gap-scan / TBIS flag / a raw gap beyond +-50% with no factor change / a SPECIAL dividend / a spin-off or stock-dividend ex-date INSIDE its hold (sessions e + 1 .. x: the
    entry session's own is not inside it, the exit session's is); the registered reading REMOVES it, the look-ahead reading keeps it at its naive RAW price path; a flag in the 5 sessions before the entry through the entry (known at the decision)
    removes it in BOTH readings; the first-reason tally adds up; the audit's data events remove an event from both"""
    def mod(d):
        rows, F, chg, ms, tb = d["rows"], d["F"], d["chg"], d["ms"], d["tb"]
        if d.get("stage") != 2:
            rows += [("N04", "2024-09-30", 0.7, True)]                                        # N04 (e = 188, x = 197): a SPECIAL dividend inside the hold
            d["spin"] += [("N09", "2024-10-10", "spin_off"), ("N12", "2024-09-19", "stock_dividend"), ("N12", "2024-10-03", "stock_dividend"),     # N09 (e = 198, x = 207): a spin-off inside; N12 (e = 188, x = 197): one on its ENTRY session (not inside) and one on P (after the exit: not inside)
                          ("N13", "2024-10-02", "spin_off")]                                   # N13 (e = 188, x = 197): a spin-off on its EXIT session: inside
            return
        d["Cl"][:192, 0] *= 2.0                                                                # N00: a registered 2-for-1 on 2024-09-26 (row 192): raw closes double before it, F = 2 before it
        d["Od"][:192, 0] *= 2.0
        F[:192, 0] = 2.0
        chg[192, 0] = True
        ms[190, 1] = True                                                                      # N01: a gap-scan flag inside the hold
        tb[195, 2] = True                                                                      # N02: a TBIS flag inside the hold
        d["Od"][191, 3] = 1.7 * d["Cl"][190, 3]                                                # N03: a raw +70% gap, no factor change
        ms[185, 6] = True                                                                      # (N06 does not trade at K = 10: x_next)
    with spec(win=30, min_pairs=25):
        dw = dw_world(mod=mod)
        W, ctx, dr = dw.W, dw.ctx, dw.dr
        assert W.fl[3][191, 3] and not W.chg[191, 3] and W.chg[192, 0] and ctx.spcs[dr("2024-09-30") + 1, 4] - ctx.spcs[dr("2024-09-30"), 4] == 1
        es = entry_set(W, ctx, 10)
        name = lambda tr: sorted((str(ctx.ev.sym[i]), TS(ctx.ev.e1[i]).strftime("%m-%d")) for i in tr.ev)
        reg = trade_set(W, ctx, es, "NOX", "registered", W.days[0], W.days[-1])
        nav = trade_set(W, ctx, es, "NOX", "naive", W.days[0], W.days[-1])
        first = lambda tr: {nm for nm in name(tr) if nm[1] == "07-04"}
        flagged = {"N00", "N01", "N02", "N03", "N04", "N09", "N13"}
        assert not any(nm in first(reg) for nm in [(n_, "07-04") for n_ in flagged]), first(reg)
        assert all((n_, "07-04") in first(nav) for n_ in flagged - {"N13"}) and ("N13", "07-04") in first(nav), "the look-ahead reading keeps the trades flagged inside the hold"
        assert ("N12", "07-04") in first(reg) and ("N12", "07-04") in first(nav), "N12: a spin-off on the ENTRY session and one after the exit are not inside the hold"
        assert reg.n == nav.n - len(flagged) and int(nav.naive.sum()) == len(flagged), (reg.n, nav.n, int(nav.naive.sum()))
        c = reg.cnt[2024]
        assert (c["hold_split"], c["hold_gap"], c["hold_tbis"], c["hold_jump"], c["hold_special"], c["hold_spin"]) == (1, 1, 1, 1, 1, 2) and nav.cnt[2024]["kept_naive"] == 7, (dict(c), dict(nav.cnt[2024]))
        for tr_ in (reg, nav):
            tot = sum(v for y_ in tr_.cnt for k_, v in tr_.cnt[y_].items() if k_ not in ("unresolved", "kept_naive"))
            assert tot + sum(tr_.cnt[y_]["unresolved"] for y_ in tr_.cnt) == es.n, "every event of the entry set is unresolved, removed for ONE first reason, or a trade"
        assert sum(reg.cnt[y_]["trades"] for y_ in reg.cnt) == reg.n and sum(nav.cnt[y_]["trades"] for y_ in nav.cnt) == nav.n
        # the naive trade is on the RAW path: N00's 2-for-1 shows as a -50% day; the split-safe path (registered rows of other readings) does not
        i0 = next(i for i in range(nav.n) if ctx.ev.sym[nav.ev[i]] == "N00" and TS(ctx.ev.e1[nav.ev[i]]) == TS("2024-07-04"))
        run = run_bundle(W, prepare(W, nav))
        d_, t_, _ = brute_trade(W, 0, int(nav.e[i0]), int(nav.x[i0]), True, 5.0)
        assert nav.naive[i0] and abs(run.pos.stock[i0] - t_) < 1e-8 and run.pos.stock[i0] < -1500.0, (run.pos.stock[i0], t_)
        d2, t2, _ = brute_trade(W, 0, int(nav.e[i0]), int(nav.x[i0]), False, 5.0)
        assert t2 > -300.0 and abs(t2 - t_) > 1000.0, "the split-safe path of the same trade holds no fake loss"
        # a flag known at the decision (rows e - 5 .. e) removes the trade in BOTH readings; one on the row before that window does not
        def mod2(d):
            if d.get("stage") == 2:
                d["ms"][183, 5] = True                                                          # N05 does not trade; use names that do
                d["ms"][183, 12] = True                                                         # N12 (e = 188): row 183 = e - 5: inside the pre window
                d["ms"][182, 13] = True                                                         # N13 (e = 188): row 182 = e - 6: outside it
                d["tb"][188, 0] = True                                                          # N00: on the entry session itself
        dw2 = dw_world(mod=mod2)
        es2 = entry_set(dw2.W, dw2.ctx, 10)
        for rd in ("registered", "naive"):
            t2_ = trade_set(dw2.W, dw2.ctx, es2, "NOX", rd, dw2.W.days[0], dw2.W.days[-1])
            nm2 = {nm for nm in [(str(dw2.ctx.ev.sym[i]), TS(dw2.ctx.ev.e1[i]).strftime("%m-%d")) for i in t2_.ev] if nm[1] == "07-04"}
            assert ("N12", "07-04") not in nm2 and ("N00", "07-04") not in nm2 and ("N13", "07-04") in nm2, (rd, nm2)
            assert t2_.cnt[2024]["pre_gap"] == 1 and t2_.cnt[2024]["pre_tbis"] == 1, dict(t2_.cnt[2024])
    # the audit's data event removes the event from the entry set (so from every cell, rule and null)
    with spec(win=30, min_pairs=25):
        dw3 = dw_world()
        ev = dw3.ctx.ev
        before = entry_set(dw3.W, dw3.ctx, 10).n
        i = next(i for i in range(ev.n) if ev.sym[i] == "N01" and TS(ev.e1[i]) == TS("2024-07-04"))
        dw3.ctx.aud_ev[i] = True
        es3 = entry_set(dw3.W, dw3.ctx, 10)
        assert es3.n == before - 1 and es3.cnt[2024]["audit"] == 1 and all(entry_set(dw3.W, dw3.ctx, K).n for K in (10, 20))
    return True


def t_engine():
    """the null engine = the cell engine: series_from_entries on a dividend-free trade set equals the cell's daily series run_bundle gives (stock marks, costs, the aggregate whole-MES hedge), draw by draw, blocks of draws apart"""
    rng = np.random.default_rng(11)
    T, Sn = 130, 8
    es_ret = rng.normal(0.0002, 0.008, T)
    es_ret[0] = 0.0
    lvl = 1100.0 * np.cumprod(1.0 + es_ret)
    ret = rng.normal(0.0004, 0.02, (T, Sn))
    ret[0] = 0.0
    Cl = 60.0 * np.cumprod(1.0 + ret, axis=0)
    W = mk_w(Cl, lvl)
    with spec(slot=60000.0):
        D = 3
        sets = []
        for d in range(D):
            n = int(rng.integers(5, 25))
            e = rng.integers(5, 100, n)
            h = rng.integers(2, 20, n)
            col = rng.integers(0, Sn, n)
            beta = rng.uniform(-0.5, 1.8, n)
            sets.append((e, h, col, beta))
        dix = np.concatenate([np.full(len(s_[0]), d) for d, s_ in enumerate(sets)])
        E, H, C, Bt = (np.concatenate([s_[k] for s_ in sets]) for k in range(4))
        ser = series_from_entries(W, dix, C, E, H, Bt, D)
        assert ser.shape == (D, T)
        for d, (e, h, col, beta) in enumerate(sets):
            tr = SimpleNamespace(n=len(e), e=e, x=e + h, col=col, beta=beta, naive=np.zeros(len(e), bool))
            run = run_bundle(W, prepare(W, tr))
            assert close(ser[d], run.x, 1e-8), d
            assert np.abs(run.hedge_agg).max() > 10.0, "the hedge is not trivially zero in this test"
        for bps in (10.0, 20.0):
            tr = SimpleNamespace(n=len(sets[0][0]), e=sets[0][0], x=sets[0][0] + sets[0][1], col=sets[0][2], beta=sets[0][3], naive=np.zeros(len(sets[0][0]), bool))
            assert close(series_from_entries(W, np.zeros(tr.n, int), tr.col, tr.e, tr.x - tr.e, tr.beta, 1, bps)[0], run_bundle(W, prepare(W, tr), bps).x, 1e-8)
    return True


# ------------------------------------------------------------------ the nulls: a multi-phase world, the plain-python eligibility recounts, the placebo and the random-name tests
def refused(fn, *frag):
    """the call must refuse (SystemExit) with every fragment in the message; returns the message"""
    try:
        fn()
    except SystemExit as e:
        msg = str(e)
        assert all(f in msg for f in frag), (msg, frag)
        return msg
    raise AssertionError(f"expected a refusal containing {frag}")


def mp_world(seed=9, T=420, Sn=32, T_cut=None):
    """32 names in 4 phases (the quarterly ex-dates 91 days apart, each phase 21 days after the one before), every name in the universe, prices = beta x ES + noise with an ex-day drop equal to each dividend, plus the cases the nulls must handle:
    N00 two special dividends at sessions 150 and 160 (no placebo session is clean for its K = 10 NO-X trade of the 2024-07-04 event), N01 a spin-off at session 169 (15 of its 20 placebo sessions are blocked), a random scatter of
    special dividends, spin-offs, TBIS flags, gap flags and short holes in the closes. T_cut = the data and the calendar are cut at that session (its date and everything after it dropped at read, as the stage's cut does): the same
    market as T_cut = None, shorter. Returns (W, ctx, cal, days)"""
    rng = np.random.default_rng(seed)
    days = pd.bdate_range("2024-01-01", periods=T)
    es_ret = rng.normal(0.0002, 0.006, T)
    es_ret[0] = 0.0
    esl = 1500.0 * np.cumprod(1.0 + es_ret)
    beta = np.linspace(0.3, 1.5, Sn)
    ret = beta * es_ret[:, None] + rng.normal(0.0, 0.01, (T, Sn))
    ret[0] = 0.0
    base = pd.Timestamp("2024-01-04")
    rows = [(f"N{j:02d}", f"{base + pd.Timedelta(days=21 * (j % 4) + 91 * k):%Y-%m-%d}", 0.4 + 0.01 * j, False) for j in range(Sn) for k in range(7)]
    rows += [("N00", f"{days[150]:%Y-%m-%d}", 1.0, True), ("N00", f"{days[160]:%Y-%m-%d}", 1.0, True)]
    spin = [("N01", f"{days[169]:%Y-%m-%d}", "spin_off")]
    r2 = np.random.default_rng(seed + 1)
    ms, tb = np.zeros((T, Sn), bool), np.zeros((T, Sn), bool)
    for j in r2.choice(np.arange(2, Sn), 10, replace=False):
        rows.append((f"N{j:02d}", f"{days[int(r2.integers(120, 330))]:%Y-%m-%d}", 0.9, True))
    for j in r2.choice(np.arange(2, Sn), 6, replace=False):
        spin.append((f"N{j:02d}", f"{days[int(r2.integers(120, 330))]:%Y-%m-%d}", "stock_dividend"))
    for j in r2.choice(np.arange(2, Sn), 6, replace=False):
        tb[int(r2.integers(120, 330)), j] = True
    for j in r2.choice(np.arange(2, Sn), 4, replace=False):
        ms[int(r2.integers(120, 330)), j] = True
    divamt = np.zeros((T, Sn))
    pos = {d: i for i, d in enumerate(days)}
    for sym, d, amt, _sp in rows:
        t = pos.get(pd.Timestamp(d))
        if t is not None:
            divamt[t, int(sym[1:])] += amt
    Cl = np.zeros((T, Sn))
    Cl[0] = 50.0
    for t in range(1, T):
        Cl[t] = Cl[t - 1] * (1.0 + ret[t]) - divamt[t]
    for j in r2.choice(np.arange(2, Sn), 3, replace=False):
        a = int(r2.integers(130, 330))
        Cl[a:a + 3, j] = np.nan
    Tc = T if T_cut is None else int(T_cut)
    cut_day = days[Tc] if Tc < T else None
    cal = cal_of([r for r in rows if cut_day is None or pd.Timestamp(r[1]) < cut_day], [r for r in spin if cut_day is None or pd.Timestamp(r[1]) < cut_day])
    W = mk_w(Cl[:Tc], esl[:Tc], div=cal.div, spin=cal.spin, days=days[:Tc], msplit=ms[:Tc], tbis=tb[:Tc])
    with spec(win=30, min_pairs=25):
        ctx = make_ctx(W, cal)
    return SimpleNamespace(W=W, ctx=ctx, cal=cal, days=days)


def brute_ex_rows(W, cal, j):
    """plain python: the session rows of every ex-date of name j on the calendar frames (cash dividends regular and special, spin-offs, stock dividends), a date that is not a session moved to the next one (memoised per name)"""
    memo = cal.__dict__.setdefault("_ex_memo", {})
    if (id(W), j) not in memo:
        sess = [pd.Timestamp(d) for d in W.days]
        out = set()
        for fr in (cal.div, cal.spin):
            for sym, ex in zip(fr["symbol"], fr["ex"]):
                if sym == W.syms[j]:
                    t = next((i for i, s_ in enumerate(sess) if s_ >= pd.Timestamp(ex)), None)
                    if t is not None:
                        out.add(t)
        memo[(id(W), j)] = out
    return memo[(id(W), j)]


def brute_flag_rows(W, cal, j):
    """plain python: the rows where name j carries a hygiene event (a registered split, a gap-scan / TBIS / raw-gap flag, a special dividend, a spin-off or stock-dividend ex-date) (memoised per name)"""
    memo = cal.__dict__.setdefault("_flag_memo", {})
    if (id(W), j) not in memo:
        out = {t for t in range(W.T) if any(bool(W.fl[q][t, j]) for q in range(4)) or bool(W.SPN[t, j])}
        sess = [pd.Timestamp(d) for d in W.days]
        for sym, ex, sp in zip(cal.div["symbol"], cal.div["ex"], cal.div["special"]):
            if sym == W.syms[j] and bool(sp) and pd.Timestamp(ex) in sess:
                out.add(sess.index(pd.Timestamp(ex)))
        memo[(id(W), j)] = out
    return memo[(id(W), j)]


def brute_clean(W, cal, j, E, h):
    """plain python: is the window E .. E + h of name j a clean placebo / random-name window - a close on every session, no ex-date of any kind in it, no hygiene event from E - 5 through E + h, a beta at E"""
    if E < 0 or E + h >= W.T:
        return False
    if not all(math.isfinite(W.Ac[t, j]) for t in range(E, E + h + 1)):
        return False
    if any(E <= t <= E + h for t in brute_ex_rows(W, cal, j)):
        return False
    if any(max(E - SPEC["hyg_lead"], 0) <= t <= E + h for t in brute_flag_rows(W, cal, j)):
        return False
    return math.isfinite(brute_beta(W, E, j)[0])


def mp_trades(mp, K=10, rule="NOX"):
    es = entry_set(mp.W, mp.ctx, K)
    return trade_set(mp.W, mp.ctx, es, rule, "registered", mp.W.days[0], mp.W.days[-1])


def brute_series(W, ctx, col, E, X, bps=COST_BPS):
    """plain python: the daily P&L (T,) of a set of dividend-free $4,000 trades (name, entry row, exit row; a negative entry = left out) and their own aggregate whole-MES hedge at the betas of the entries"""
    acc, trs = np.zeros(W.T), []
    for j, e, x in zip(col, E, X):
        if e < 0:
            continue
        day, _tot, _cash = brute_trade(W, int(j), int(e), int(x), False, bps)
        for t, v in day.items():
            acc[t] += v
        trs.append((int(e), int(x), float(ctx.beta[int(e), int(j)])))
    if trs:
        _n, pnl, cost, _per, _day = brute_hedge(W, trs)
        acc += np.array(pnl) + np.array(cost)
    return acc


def brute_pool(W, cal, evs, e, x):
    """plain python: the names a trade held e .. x may be replaced by in the random-name null - a top-500 regular quarterly payer at the entry close (the name's latest regular ex-date on or before e starts a cycle-OK event; the universe row of the next
    session), a beta and a close at e, an own window P' - 25 .. X' that starts after the hold ends, no ex-date of any kind in e .. x, no hygiene event in e - 5 .. x, a close on every session of the hold -> [column]"""
    own, lead, want = SPEC["own_lead"], SPEC["hyg_lead"], []
    for j in range(W.S):
        mine = [d for d in evs if d["col"] == j and 0 <= d["e1_row"] <= e]
        act = max(mine, key=lambda d: d["e1_row"]) if mine else None
        if act is None or not act["cyc"]:
            continue
        pp = act["p_row"] if act["p_row"] >= 0 else 10 ** 9
        if not (W.U[e + 1, j] and math.isfinite(W.Ac[e, j]) and math.isfinite(brute_beta(W, e, j)[0])) or pp - own <= x:
            continue
        if any(e <= t <= x for t in brute_ex_rows(W, cal, j)) or any(max(e - lead, 0) <= t <= x for t in brute_flag_rows(W, cal, j)):
            continue
        if not all(math.isfinite(W.Ac[t, j]) for t in range(e, x + 1)):
            continue
        want.append(j)
    return want


def t_placebo():
    """[V2] the registered null: every real trade keeps its name, its holding length h and its hedge rule, and moves to an entry drawn UNIFORMLY from E1 + 11 .. P - 26 - h whose window E .. E + h touches no ex-date of the stock (and no hygiene event) - else
    redrawn, up to 20 attempts, else left out of that draw (counted); a trade with no such session at all is left out of every draw. On a 32-name world with planted blockers, against a plain-python recount of every window"""
    mp = mp_world()
    W, ctx, cal = mp.W, mp.ctx, mp.cal
    with spec(win=30, min_pairs=25):
        tr = mp_trades(mp, 10, "NOX")
        assert tr.n >= 40, tr.n
        h = tr.x - tr.e
        assert (h == 9).all()
        lo, hi = tr.e1r + SPEC["pl_lo"], tr.p - SPEC["pl_margin"] - h
        span = hi - lo + 1
        D = 400
        E = placebo_entries(W, ctx, np.random.default_rng(123), tr, D)
        assert E.shape == (tr.n, D) and E.dtype == np.int64
        for i in range(tr.n):
            j = int(tr.col[i])
            free = [e for e in range(int(lo[i]), int(hi[i]) + 1) if brute_clean(W, cal, j, e, int(h[i]))]
            got = E[i][E[i] >= 0]
            assert (len(got) == 0 or (got.min() >= lo[i] and got.max() <= hi[i])) and set(got.tolist()) <= set(free), (i, j, free, sorted(set(got.tolist())))
            assert all(clean_window(W, ctx, np.array([j]), np.array([e]), np.array([int(h[i])]))[0] == brute_clean(W, cal, j, e, int(h[i])) for e in range(int(lo[i]) - 3, int(hi[i]) + 4)), "the vectorised window test equals the recount"
            if span[i] >= 1:
                assert (E[i] >= 0).any() == bool(free), (i, free)
                ps = 1.0 - len(free) / span[i]
                assert abs((E[i] < 0).mean() - ps ** SPEC["pl_tries"]) < 5.0 * math.sqrt(max(ps ** SPEC["pl_tries"] * (1 - ps ** SPEC["pl_tries"]), 1e-3) / D) + 1e-9, (i, ps, (E[i] < 0).mean())
        names = [str(W.syms[c]) for c in tr.col]
        i0 = next(i for i in range(tr.n) if names[i] == "N00" and TS(ctx.ev.e1[tr.ev[i]]) == TS("2024-07-04"))
        i1 = next(i for i in range(tr.n) if names[i] == "N01" and TS(ctx.ev.e1[tr.ev[i]]) == TS("2024-07-25"))
        assert (E[i0] < 0).all() and (span[i0], tr.e1r[i0], tr.p[i0]) == (20, 133, 198), "N00's two special dividends leave no clean placebo window: left out of every draw"
        free1 = [e for e in range(int(lo[i1]), int(hi[i1]) + 1) if brute_clean(W, cal, 1, e, 9)]
        assert len(free1) == 5 and span[i1] == 20, (free1, span[i1])
        # redraws: with p of the entries blocked, a trade is left out with probability p^tries - tries is the NUMBER OF ATTEMPTS (1 attempt: p; 2 attempts: p^2, not p^3)
        ps1 = 0.75
        for tries in (1, 2, 20):
            with spec(pl_tries=tries):
                Et = placebo_entries(W, ctx, np.random.default_rng(7), tr, 800)
            frac = (Et[i1] < 0).mean()
            sd = math.sqrt(ps1 ** tries * (1 - ps1 ** tries) / 800)
            assert abs(frac - ps1 ** tries) < 5 * sd + 1e-9, (tries, frac, ps1 ** tries)
        # uniform on the clean sessions it can reach: an unblocked trade over its whole range, N01's over its 5 clean ones (conditional on being drawn)
        D2 = 2000
        Eu = placebo_entries(W, ctx, np.random.default_rng(99), tr, D2)
        i2 = next(i for i in range(tr.n) if all(brute_clean(W, cal, int(tr.col[i]), e, 9) for e in range(int(lo[i]), int(hi[i]) + 1)) and span[i] == 20)
        cnt = np.bincount(Eu[i2] - lo[i2], minlength=int(span[i2]))
        assert (Eu[i2] >= 0).all() and cnt.sum() == D2 and np.all(np.abs(cnt - D2 / 20) < 5 * math.sqrt(D2 / 20 * 19 / 20)), cnt
        c1 = np.array([(Eu[i1] == e).sum() for e in free1])
        drawn = int((Eu[i1] >= 0).sum())
        assert drawn >= 1990 and np.all(np.abs(c1 - drawn / 5) < 5 * math.sqrt(drawn / 5 * 4 / 5)), (c1, drawn)
        # the stream is the key's: the same key reproduces, another does not
        assert (placebo_entries(W, ctx, np.random.default_rng(123), tr, D) == E).all() and (placebo_entries(W, ctx, np.random.default_rng(124), tr, D) != E).any()
        # a trade with no placebo session at all (here: every other trade's event is moved to a 30-session quarter, so E1 + 11 .. P - 26 - h is empty): left out of every draw
        p2 = tr.p.copy()
        p2[::2] = tr.e1r[::2] + 30
        trm = SimpleNamespace(**{**tr.__dict__, "p": p2})
        spanm = (trm.p - SPEC["pl_margin"] - h) - (trm.e1r + SPEC["pl_lo"]) + 1
        Em = placebo_entries(W, ctx, np.random.default_rng(5), trm, 50)
        assert (spanm < 1).sum() == len(p2[::2]) and (Em[spanm < 1] < 0).all() and (Em[spanm >= 1] >= 0).any(), "an empty range leaves the trade out of every draw"
        # holding lengths of its own: the X rule's h varies by trade, every draw keeps each trade's h (the window is E .. E + h, brute-checked above for the NO-X rule; here for arbitrary h per trade)
        trh = SimpleNamespace(n=tr.n, e=tr.e, x=tr.e + np.random.default_rng(2).integers(2, 14, tr.n), col=tr.col, p=tr.p, e1r=tr.e1r)
        hh = trh.x - trh.e
        Eh = placebo_entries(W, ctx, np.random.default_rng(31), trh, 60)
        for i in range(tr.n):
            for e in Eh[i][Eh[i] >= 0][:5]:
                assert tr.e1r[i] + 11 <= e <= tr.p[i] - 26 - hh[i] and brute_clean(W, cal, int(tr.col[i]), int(e), int(hh[i])), (i, e, hh[i])
        # placebo_null: the draws' series are the cell engine's on the moved entries (same name, same h, the beta at the NEW entry), costed and hedged per draw; the left-out counts and the never-drawn count
        B, S12 = M17.synth_book(seed=3, hi="2026-06-30")
        rowsB = A13.book_rows(B, W)
        key = [SEED, 0, 1, 1]
        rb = mk_ref(B)
        roc, left, never, do = placebo_null(W, ctx, trm, 25, key, S12, rowsB, B.n, Sref=rb.S)
        rng = np.random.default_rng(key)
        ref, ref_do, ref_left = [], [], []
        for D_b in (10, 10, 5):
            Eb = placebo_entries(W, ctx, rng, trm, D_b)
            acc = np.vstack([brute_series(W, ctx, trm.col, Eb[:, d], np.where(Eb[:, d] >= 0, Eb[:, d] + h, -1)) for d in range(D_b)])
            ref.append(D15.null_cell(S12, acc, rowsB, B.n)[0])
            ref_do.append(D15.null_cell(rb.S, acc, rowsB, B.n)[2])
            ref_left.append(tr.n - (Eb >= 0).sum(axis=0))
        assert close(roc, np.concatenate(ref), 1e-9) and (left == np.concatenate(ref_left)).all() and never == int((spanm < 1).sum()) > 0 and len(roc) == 25 and np.isfinite(roc).sum() >= 20, (roc, ref)
        assert (left >= (spanm < 1).sum()).all(), "the trades with no placebo session are out of every draw"
        assert close(do, np.concatenate(ref_do), 1e-9) and len(do) == 25 and np.isfinite(do).all(), "[X1] each draw's DO is against the REFERENCE book's drawdown days"
        r0, l0, n0, d0 = placebo_null(W, ctx, trm, 25, key, S12, rowsB, B.n)
        assert close(r0, roc, 1e-12) and (l0 == left).all() and n0 == never and len(d0) == 25 and np.isnan(d0).all(), "without a stretch: the same draws, no DO"
    return True


def t_randomname():
    """the reported second null: every real trade is replaced, at the SAME entry and exit sessions, by a uniform pick from the names that were a top-500 regular quarterly payer at its entry close whose own window P' - 25 .. X' does not overlap the hold,
    with a beta, a close on every session of the hold, no ex-date of its own in it and no hygiene event in it - the eligible sets against a plain-python recount for every trade, the picks' uniformity, the draws' series against the cell engine"""
    mp = mp_world()
    W, ctx, cal = mp.W, mp.ctx, mp.cal
    with spec(win=30, min_pairs=25):
        tr = mp_trades(mp, 10, "NOX")
        flat, off, cnt = random_name_pool(W, ctx, tr)
        evs = brute_events(cal.div, W.days, W.syms)
        sizes = []
        for i in range(tr.n):
            e, x = int(tr.e[i]), int(tr.x[i])
            want = brute_pool(W, cal, evs, e, x)
            got = sorted(flat[off[i]:off[i] + cnt[i]].tolist())
            assert got == want, (i, got, want)
            sizes.append(len(want))
        assert max(sizes) >= 6 and min(sizes) >= 0 and sum(s > 0 for s in sizes) > tr.n * 0.8, sizes
        assert int(cnt.sum()) == len(flat) and (off[1:] == (off + cnt)[:-1]).all() and off[0] == 0
        # the picks: always from the trade's own eligible names, uniform among them, -1 where there are none
        D = 3000
        pick = draw_picks(np.random.default_rng(5), flat, off, cnt, D)
        assert pick.shape == (tr.n, D)
        for i in range(tr.n):
            el = set(flat[off[i]:off[i] + cnt[i]].tolist())
            assert set(np.unique(pick[i]).tolist()) <= (el if cnt[i] else {-1}) and (cnt[i] == 0) == (pick[i] == -1).all()
        i3 = int(np.argmax(cnt))
        m = int(cnt[i3])
        fr = np.array([(pick[i3] == c).sum() for c in flat[off[i3]:off[i3] + m]])
        assert fr.sum() == D and np.all(np.abs(fr - D / m) < 5 * math.sqrt(D / m * (1 - 1 / m))), (fr, m)
        # an empty pool stays empty
        assert (draw_picks(np.random.default_rng(1), np.zeros(0, np.int64), np.zeros(3, np.int64), np.zeros(3, np.int64), 4) == -1).all()
        # random_name_null: same entry / exit sessions, the NEW name's beta, its own aggregate hedge, per draw
        B, S12 = M17.synth_book(seed=3, hi="2026-06-30")
        rowsB = A13.book_rows(B, W)
        key = [SEED, 1, 1, 2]
        rb = mk_ref(B)
        roc, left, never, do = random_name_null(W, ctx, tr, 25, key, S12, rowsB, B.n, Sref=rb.S)
        rng = np.random.default_rng(key)
        ref, ref_do, ref_left = [], [], []
        for D_b in (10, 10, 5):
            pk = draw_picks(rng, flat, off, cnt, D_b)
            acc = np.vstack([brute_series(W, ctx, pk[:, d], np.where(pk[:, d] >= 0, tr.e, -1), tr.x) for d in range(D_b)])
            ref.append(D15.null_cell(S12, acc, rowsB, B.n)[0])
            ref_do.append(D15.null_cell(rb.S, acc, rowsB, B.n)[2])
            ref_left.append(tr.n - (pk >= 0).sum(axis=0))
        assert close(roc, np.concatenate(ref), 1e-9) and (left == np.concatenate(ref_left)).all() and never == int((cnt == 0).sum()) and len(roc) == 25 and np.isfinite(roc).sum() >= 20, (roc, ref)
        assert close(do, np.concatenate(ref_do), 1e-9) and len(do) == 25 and np.isfinite(do).all(), "[X1] each draw's DO is against the REFERENCE book's drawdown days"
        r0, l0, n0, d0 = random_name_null(W, ctx, tr, 25, key, S12, rowsB, B.n)
        assert close(r0, roc, 1e-12) and (l0 == left).all() and n0 == never and len(d0) == 25 and np.isnan(d0).all(), "without a stretch: the same draws, no DO"
    return True


def t_null_summary():
    """the null's statistic is the MAX over the 2 cells draw by draw (a NaN draw of one cell does not hide the other's), then p5 / p50 / p95 of the finite draws"""
    a, b = np.array([1.0, 5.0, np.nan, 3.0, np.nan]), np.array([2.0, 4.0, 7.0, np.nan, np.nan])
    s = null_summary({"R10": a, "R20": b})
    assert s["draws"] == 5 and s["seed"] == SEED and s["roc_max"]["finite"] == 4 and close([s["roc_max"][k] for k in ("p5", "p50", "p95")], [np.percentile([2, 5, 7, 3], q) for q in (5, 50, 95)])
    assert s["by_cell"]["R10"]["finite"] == 3 and s["by_cell"]["R20"]["finite"] == 3 and close(s["by_cell"]["R10"]["p50"], 3.0) and close(s["by_cell"]["R20"]["p50"], 4.0) and "do_ref_max" not in s
    # [X1] the DO of the draws against the reference's drawdown days: the MAX over the 2 cells draw by draw, the same way
    do_a, do_b = np.array([0.1, 0.5, np.nan, 0.3, np.nan]), np.array([0.2, 0.4, 0.7, np.nan, np.nan])
    s2 = null_summary({"R10": a, "R20": b}, {"R10": do_a, "R20": do_b})
    assert s2["roc_max"] == s["roc_max"] and s2["do_ref_max"]["finite"] == 4 and close([s2["do_ref_max"][k] for k in ("p5", "p50", "p95")], [np.percentile([0.2, 0.5, 0.7, 0.3], q) for q in (5, 50, 95)])
    assert set(s2["do_ref_by_cell"]) == {"R10", "R20"} and s2["do_ref_by_cell"]["R10"]["finite"] == 3 and close(s2["do_ref_by_cell"]["R20"]["p50"], 0.4)
    return True


# ------------------------------------------------------------------ the event-time path [V4] on a planted run-up
def pw_world(T=700, n_a=12, n_b=3, n_c=3, bps=80.0, since="2025-07-01"):
    """a world with ONE planted effect and no noise: returns = beta x ES (exact), plus an abnormal +bps on each of the 5 sessions P - 5 .. P - 1 of every event whose P is on / after `since` (default 2025-07-01: July-June year 2025 or later). Names:
    A (quarterly, X = P), B (one late X: X = P + 15 sessions on the 2024-07-04 event, then regular again), C (one shifted ex-date: X = P + 5 sessions for the 2024-07-04 event and X = P - 5 sessions for the next). The ex-day drop equals the dividend,
    so the split-safe total return is the planted return exactly. ctx.beta is the true beta (the regression is tested on its own)"""
    rng = np.random.default_rng(21)
    days = pd.bdate_range("2024-01-01", periods=T)
    Sn = n_a + n_b + n_c
    es_ret = rng.normal(0.0002, 0.006, T)
    es_ret[0] = 0.0
    esl = 1500.0 * np.cumprod(1.0 + es_ret)
    beta = np.linspace(0.5, 1.5, Sn)
    base = pd.Timestamp("2024-01-04")
    offs = {}
    for j in range(Sn):
        if j < n_a:
            offs[j] = [91 * k for k in range(11)]
        elif j < n_a + n_b:
            offs[j] = [0, 91, 182, 182 + 112] + [182 + 112 + 91 * k for k in range(1, 7)]
        else:
            offs[j] = [0, 91, 182, 280, 371] + [371 + 91 * k for k in range(1, 7)]
    rows = [(f"N{j:02d}", f"{base + pd.Timedelta(days=d):%Y-%m-%d}", 0.5, False) for j in range(Sn) for d in offs[j]]
    cal = cal_of(rows)
    ev = build_events(cal.div, days, np.array([f"N{j:02d}" for j in range(Sn)]))
    a = np.zeros((T, Sn))
    for i in np.flatnonzero(ev.cyc & (ev.p_row >= 0)):
        if TS(ev.p_date[i]) >= TS(since):
            a[max(ev.p_row[i] - 5, 0):ev.p_row[i], ev.col[i]] = bps * 1e-4
    r = beta * es_ret[:, None] + a
    r[0] = 0.0
    divamt = np.zeros((T, Sn))
    pos = {d: i for i, d in enumerate(days)}
    for sym, d, amt, _sp in rows:
        t = pos.get(pd.Timestamp(d))
        if t is not None:
            divamt[t, int(sym[1:])] += amt
    Cl = np.zeros((T, Sn))
    Cl[0] = 50.0
    for t in range(1, T):
        Cl[t] = Cl[t - 1] * (1.0 + r[t]) - divamt[t]
    W = mk_w(Cl, esl, div=cal.div, days=days)
    assert np.nanmax(np.abs(np.asarray(W.Rd)[1:] - r[1:])) < 1e-9, "the split-safe total return is the planted return"
    with spec(win=30, min_pairs=25):
        ctx = make_ctx(W, cal)
    ctx.beta = np.tile(beta, (T, 1))
    ctx.bok = np.ones((T, Sn), bool)
    return SimpleNamespace(W=W, ctx=ctx, cal=cal, days=days, beta=beta, kinds=(n_a, n_b, n_c))


def t_path():
    """[V4] the event-time path: P - 20 .. P + 10 on the P axis, each event running to its OWN X - 1, the hedged cost-free mean abnormal return (r - beta x ES) in bps, by July-June year of P. On a planted +80 bps run-up on the 5 sessions before P
    (July-June 2025 events only): the path shows it at tau = -5 .. -1 and nowhere else, 0 in the earlier year; the counts per tau and the late-X trades apart; the sum and its share in X - 2 .. X - 1; against a plain-python recount"""
    pw = pw_world()
    W, ctx = pw.W, pw.ctx
    with spec(win=30, min_pairs=25):
        es = entry_set(W, ctx, 20)
        tr = trade_set(W, ctx, es, "X", "registered", W.days[0], W.days[-1])
    pth = event_path(W, tr)
    taus = list(range(-20, 11))
    assert pth.taus.tolist() == taus and len(pth.mean_bps) == 31 and len(pth.n) == 31
    k0 = tr.kind == 0
    assert pth.trades == int(k0.sum()) > 50 and pth.late_or_missing_x_trades == int((~k0).sum()) >= 3, (pth.trades, pth.late_or_missing_x_trades)
    sums, ns, tot, last2 = defaultdict(float), defaultdict(int), [], []
    by = defaultdict(lambda: (defaultdict(float), defaultdict(int)))
    for i in np.flatnonzero(k0):
        p, x, j, b = int(tr.p[i]), int(tr.x[i]), int(tr.col[i]), float(tr.beta[i])
        yr = int(W.days[p].year) - (1 if W.days[p].month < 7 else 0)
        one, path = 0.0, {}
        for tau in taus:
            t = p + tau
            if 0 <= t <= W.T - 1 and t <= x and math.isfinite(W.Rd[t, j]) and math.isfinite(W.es.ret[t]):
                v = float(W.Rd[t, j] - b * W.es.ret[t])
                sums[tau] += v
                ns[tau] += 1
                by[yr][0][tau] += v
                by[yr][1][tau] += 1
                one += v
                path[t] = v
        tot.append(1e4 * one)
        last2.append(1e4 * (path.get(x, 0.0) + path.get(x - 1, 0.0)))
    for q, tau in enumerate(taus):
        want = 1e4 * sums[tau] / ns[tau] if ns[tau] else float("nan")
        assert pth.n[q] == ns[tau] and ((math.isnan(want) and math.isnan(pth.mean_bps[q])) or abs(pth.mean_bps[q] - want) < 1e-9), (tau, pth.mean_bps[q], want)
        assert abs(pth.cum_bps[q] - sum(1e4 * sums[t_] / ns[t_] for t_ in taus[:q + 1] if ns[t_])) < 1e-9
    assert abs(pth.total_mean_bps - np.mean(tot)) < 1e-9 and abs(pth.last2_mean_bps - np.mean(last2)) < 1e-9 and abs(pth.last2_share - np.mean(last2) / np.mean(tot)) < 1e-12
    assert set(pth.by_year) == set(by) == {2024, 2025, 2026}, (set(pth.by_year), set(by))
    for yr, (sm, nn) in by.items():
        for q, tau in enumerate(taus):
            want = 1e4 * sm[tau] / nn[tau] if nn[tau] else float("nan")
            got = pth.by_year[yr]["mean_bps"][q]
            assert pth.by_year[yr]["n"][q] == nn[tau] and ((math.isnan(want) and math.isnan(got)) or abs(got - want) < 1e-9), (yr, tau, got, want)
    # the planted effect itself
    for yr in (2025, 2026):
        m = pth.by_year[yr]["mean_bps"]
        for q, tau in enumerate(taus):
            if -5 <= tau <= -1:
                assert pth.by_year[yr]["n"][q] > 0 and abs(m[q] - 80.0) < 1e-6, (yr, tau, m[q])
            else:
                assert not np.isfinite(m[q]) or abs(m[q]) < 1e-6, (yr, tau, m[q])
    assert all((not np.isfinite(v)) or abs(v) < 1e-6 for v in pth.by_year[2024]["mean_bps"]), "no run-up was planted in July-June 2024"
    assert pth.n[taus.index(0)] > 0 and pth.n[taus.index(10)] == 0, "X within P + 10 ends the path at X - 1 <= P + 9: nothing at tau = +10"
    npl = sum(1 for i in np.flatnonzero(k0) if TS(W.days[int(tr.p[i])]) >= TS("2025-07-01"))
    assert abs(pth.total_mean_bps - 400.0 * npl / pth.trades) < 1e-6 and abs(pth.last2_mean_bps - 160.0 * npl / pth.trades) < 1e-6 and abs(pth.last2_share - 0.4) < 1e-9, (pth.total_mean_bps, npl, pth.trades)
    # the events end at their own X - 1: C's X = P + 5 sessions runs to tau = +4, C's X = P - 5 sessions stops at tau = -6, a late X (kind 1) is not in the path at all
    assert pth.n[taus.index(4)] > 0 and pth.n[taus.index(5)] == 0 and pth.n[taus.index(-6)] > pth.n[taus.index(-5)], (pth.n[taus.index(4)], pth.n[taus.index(5)], pth.n[taus.index(-6)], pth.n[taus.index(-5)])
    # an ES-hole session contributes nothing
    W2 = SimpleNamespace(**{**W.__dict__})
    W2.es = SimpleNamespace(**{**W.es.__dict__})
    ret2 = np.array(W.es.ret, float)
    p0 = int(tr.p[np.flatnonzero(k0)[0]])
    ret2[p0 - 3] = np.nan
    W2.es.ret = ret2
    pth2 = event_path(W2, tr)
    assert pth2.n[taus.index(-3)] < pth.n[taus.index(-3)] and pth2.n[taus.index(-4)] == pth.n[taus.index(-4)]
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        print_path(pth)
    txt = buf.getvalue()
    assert "EVENT-TIME PATH [V4]" in txt and "tau" in txt and "2025-26" in txt and "ex-day tax trade" in txt and f"{pth.trades:,} events" in txt
    return True


# ------------------------------------------------------------------ the yardstick and the stretches
def t_yardstick():
    """ONE frontier yardstick: ROC @ $30k = 30 x (net / years) / (the deepest peak-to-trough of the daily equity from a peak of 0), years = (last - first row) / 365.25 - on a hand-checked series, through r11_risk.stats and through
    stat_of's stretch cut (the rows of the stretch, not of the trades); trades are counted by EXIT date, inclusive at both ends, the sub-period cut likewise"""
    x = [100.0, -300.0, 50.0, 50.0, 250.0]
    dates = pd.DatetimeIndex(["2020-01-01", "2020-04-01", "2020-07-01", "2020-10-01", "2021-01-01"])
    st = R11.stats(x, dates)
    yrs = 366 / 365.25
    assert st["max_dd"] == 300.0 and st["net"] == 150.0 and abs(st["years"] - yrs) < 1e-12 and abs(st["roc"] - 30.0 * (150.0 / yrs) / 300.0) < 1e-12, st
    assert not math.isfinite(R11.stats([5.0, 5.0, 5.0], dates[:3])["roc"]), "a series that never draws down has no yardstick"
    # the cell's stretch through D15.cell_stats: every B row of [lo, hi] counts (the years are the stretch's, the zero days too)
    B, S12 = M17.synth_book(seed=3, hi="2026-06-30")
    dw = dw_world()
    W = dw.W
    rowsB = A13.book_rows(B, W)
    xs = np.zeros(W.T)
    xs[[40, 50, 60, 70, 80]] = [900.0, -2000.0, 500.0, 300.0, 1200.0]
    cnt = np.zeros(W.T)
    run = SimpleNamespace(x=xs, cnt=cnt, n_pos=5, n_units=5, pos=SimpleNamespace(pnl=np.array([900.0, -2000.0, 500.0, 300.0, 1200.0])))
    stt, xB, cB = stat_of(B, rowsB, run, WF0, PRE_END)
    m = np.asarray((B.index >= WF0) & (B.index <= PRE_END))
    ds = B.index[m]
    eq, peak, mdd = 0.0, 0.0, 0.0
    for v in xB[m]:
        eq += v
        peak = max(peak, eq)
        mdd = max(mdd, peak - eq)
    years = (ds[-1] - ds[0]).days / 365.25
    assert abs(stt["net"] - xs.sum()) < 1e-9 and abs(stt["max_dd"] - mdd) < 1e-9 and abs(stt["years"] - years) < 1e-12 and abs(stt["roc"] - 30.0 * (xs.sum() / years) / mdd) < 1e-9 and mdd == 2000.0, (stt, mdd)
    assert abs(years - 8.99) < 0.02, "the WF stretch is nine years: 2016-07-01 .. 2025-06-27 (the last session before 06-29)"
    assert stt["n_pos"] == 5 and abs(stt["net_pos"] - 900.0) < 1e-9, stt
    # a sub-stretch is cut by its own dates: its own years, the same net when every trade is inside it
    lo2, hi2 = TS("2024-02-01"), TS("2024-12-31")
    s2, _, _ = stat_of(B, rowsB, run, lo2, hi2)
    m2 = np.asarray((B.index >= lo2) & (B.index <= hi2))
    assert abs(s2["years"] - (B.index[m2][-1] - B.index[m2][0]).days / 365.25) < 1e-12 and abs(s2["net"] - xs.sum()) < 1e-9 and s2["years"] < 1.0
    # trades are counted by EXIT date, both ends inclusive (the NO-X trades of the 2024-07-04 events exit at P - 1 = 2024-10-02)
    with spec(win=30, min_pairs=25):
        es = entry_set(W, dw.ctx, 10)
        d_, one = TS("2024-10-02"), pd.Timedelta(days=1)
        cut = lambda lo, hi: trade_set(W, dw.ctx, es, "NOX", "registered", lo, hi)
        full, on = cut(W.days[0], W.days[-1]), cut(d_, d_)
        before, after = cut(W.days[0], d_ - one), cut(d_ + one, W.days[-1])
        assert on.n >= 5 and (on.x == dw.dr("2024-10-02")).all() and before.n + on.n + after.n == full.n and after.n >= 1, (before.n, on.n, after.n, full.n)
        assert cut(d_, W.days[-1]).n == on.n + after.n and cut(W.days[0], d_).n == before.n + on.n, "the end dates are inclusive"
        base = run_bundle(W, prepare(W, full))
        sub = sub_run(W, base, d_, d_)
        assert sub.n_pos == on.n == int((W.days[full.x] == d_).sum()) and len(sub.pos.pnl) == on.n and sub_run(W, base, d_ + one, W.days[-1]).n_pos == after.n and sub_run(W, base, W.days[0], d_ - one).n_pos == before.n
    return True


# ------------------------------------------------------------------ the checks, the files, the refusals, the cut, the whole pipeline on a hand-made world
THIS = sys.modules[__name__]


def quiet():
    return contextlib.redirect_stdout(io.StringIO())


def t_judge():
    """Stage A's (a)-(e): every bar on its own - inclusive where the prereg says '>=', strict where it says 'above' / '> 0', a NaN fails every comparison it enters - then [V1] (NO-X is the registered verdict when the two differ), the tie-break between
    two passing cells, the book-add comparison (reported) and Stage B's leg veto"""
    R = RULES
    st0 = {"n_pos": 1500, "roc": 20.0, "net": 1000.0, "years_pos": 7, "net_ex2020": 500.0, "net_ex_best_days": 100.0, "net_ex_best_pos": 100.0}
    nul0 = {"roc_max": {"p95": 10.0}}
    names = [f"trades>={R['n']}", f"ROC>={R['roc']:g}", "net>0 at 5 bps", "net>0 at 10 bps", "ROC>null p95", f"positive in >={R['years']} of 9 July-June years", "net>0 without Feb 15 - Apr 30 2020", "profitable without its best 1% of days",
             "profitable without its best 1% of trades"]
    ck = judge_cell(st0, 50.0, nul0)
    assert list(ck) == names and all(ck.values()) and all(isinstance(v, bool) for v in ck.values()), ck
    nan = float("nan")

    def broken(**kw):
        st, net10, nul = dict(st0), 50.0, nul0
        for k, v in kw.items():
            if k == "net10":
                net10 = v
            elif k == "p95":
                nul = {"roc_max": {"p95": v}}
            else:
                st[k] = v
        return {k for k, v in judge_cell(st, net10, nul).items() if not v}
    assert R["n"] == 1000 and R["roc"] == 15.0 and R["years"] == 6
    assert broken(n_pos=999) == {names[0]} and broken(n_pos=1000) == set() and broken(n_pos=0) == {names[0]}, "(a) at least 1,000 trades, inclusive"
    assert broken(roc=14.99) == {names[1]} and broken(roc=15.0) == set() and broken(roc=15.0, p95=15.0) == {names[4]} and broken(roc=15.0, p95=14.99) == set(), "(b) ROC >= 15 inclusive; (c) strictly above the null's p95"
    assert broken(net=0.0) == {names[2]} and broken(net=-1.0) == {names[2]} and broken(net10=0.0) == {names[3]} and broken(net10=-0.01) == {names[3]}, "(b) net > 0 at 5 AND at 10 bps, strict"
    assert broken(years_pos=5) == {names[5]} and broken(years_pos=6) == set() and broken(years_pos=0) == {names[5]}, "(d) at least 6 of the 9 years, inclusive"
    assert broken(net_ex2020=0.0) == {names[6]} and broken(net_ex_best_days=0.0) == {names[7]} and broken(net_ex_best_pos=-5.0) == {names[8]} and broken(net_ex_best_pos=0.0) == {names[8]}, "(d) (e) strict"
    assert broken(roc=nan) == {names[1], names[4]} and broken(net=nan) == {names[2]} and broken(net10=nan) == {names[3]} and broken(p95=nan) == {names[4]} and broken(net_ex2020=nan) == {names[6]}
    assert broken(net_ex_best_days=nan) == {names[7]} and broken(net_ex_best_pos=nan) == {names[8]} and broken(years_pos=nan) == {names[5]}, "a NaN never passes"
    assert broken(n_pos=1, roc=-3.0, net=-1.0, net10=-1.0, years_pos=0, net_ex2020=-1.0, net_ex_best_days=-1.0, net_ex_best_pos=-1.0) == set(names)
    # [V1]
    assert registered_verdict({"NOX": True, "X": False}) == (True, False, True) and registered_verdict({"NOX": False, "X": True}) == (False, True, True)
    assert registered_verdict({"NOX": True, "X": True}) == (True, True, False) and registered_verdict({"NOX": False, "X": False}) == (False, False, False)

    def mk(nox10, nox20, x10=True, x20=True, roc=(20.0, 30.0), xroc=(99.0, 1.0)):
        return {"X": {"R10": {"PASS": x10, "base": {"roc": xroc[0]}}, "R20": {"PASS": x20, "base": {"roc": xroc[1]}}},
                "NOX": {"R10": {"PASS": nox10, "base": {"roc": roc[0]}}, "R20": {"PASS": nox20, "base": {"roc": roc[1]}}}, "P10": {}}
    ver, passing, cand = stage_a_flow(mk(True, True))
    assert passing == ["R10", "R20"] and cand == "R20" and not ver["R10"]["differ"], "two passing cells: the higher NO-X ROC goes to Stage B (the X-rule's numbers do not matter)"
    assert stage_a_flow(mk(True, True, roc=(30.0, 30.0)))[2] == "R10" and stage_a_flow(mk(True, True, roc=(31.0, 30.0)))[2] == "R10" and stage_a_flow(mk(True, True, roc=(30.0, 30.5)))[2] == "R20", "ties go to R10"
    ver, passing, cand = stage_a_flow(mk(True, False, roc=(16.0, 90.0)))
    assert passing == ["R10"] and cand == "R10" and ver["R20"] == {"registered": False, "x_rule": True, "differ": True}, "a lower-ROC passing cell is still the candidate when it is the only one"
    ver, passing, cand = stage_a_flow(mk(False, False, x10=True, x20=True))
    assert passing == [] and cand is None and all(v["differ"] and not v["registered"] for v in ver.values()), "the X-rule passing is not enough: NO-X is the registered verdict"
    ver, passing, cand = stage_a_flow(mk(True, False, x10=False, x20=False))
    assert passing == ["R10"] and ver["R10"] == {"registered": True, "x_rule": False, "differ": True}
    assert pick_candidate({"NOX": {"R10": {"base": {"roc": 1.0}}}}, []) is None
    # the sealed year: the leg's veto alone; the book add is a comparison that is reported
    assert RULES["b_n"] == 100
    leg = {"n_pos": 100, "net": 1.0, "net_ex_best_pos": 0.5}
    assert all(b_checks(leg).values()) and set(b_checks(leg)) == {"leg trades>=100", "leg net>0", "leg net>0 without its top 1% of trades"}
    assert not b_checks({**leg, "n_pos": 99})["leg trades>=100"] and not b_checks({**leg, "net": 0.0})["leg net>0"] and not b_checks({**leg, "net_ex_best_pos": 0.0})["leg net>0 without its top 1% of trades"]
    assert not any(b_checks({"n_pos": 500, "net": nan, "net_ex_best_pos": nan})[k] for k in ("leg net>0", "leg net>0 without its top 1% of trades"))
    assert book_add_would_clear({"roc": RULES["b_roc"], "sortino": RULES["b_sort"]}) and not book_add_would_clear({"roc": RULES["b_roc"] - 0.01, "sortino": RULES["b_sort"] + 1}) and not book_add_would_clear({"roc": nan, "sortino": 9.0})
    return True


def t_reports():
    """the reported rows on a hand-made table of trades: calendar month of the entry, the yield buckets (the cell's top third against the rest, a trade without a yield counted apart), the late / skipped dividend exits, the largest gains"""
    rw = SimpleNamespace(pnl=np.array([40.0, -10.0, 30.0, 5.0]), bps=np.array([100.0, -25.0, 75.0, 12.5]), yld=np.array([0.01, 0.02, np.nan, 0.03]), month=np.array([1, 1, 2, 12]), kind=np.array([0, 1, 0, 1]), sym=np.array(list("ABCD")),
                         entry=np.array(["2024-01-02", "2024-01-03", "2024-02-01", "2024-12-02"], "datetime64[ns]"), exit=np.array(["2024-01-12", "2024-01-13", "2024-02-11", "2024-12-12"], "datetime64[ns]"))
    mt = month_table(rw)
    assert mt[1] == {"trades": 2, "net": 30.0, "mean_bps": 37.5} and mt[2]["trades"] == 1 and mt[12]["net"] == 5.0 and mt[3]["trades"] == 0 and math.isnan(mt[3]["mean_bps"]) and sum(v["trades"] for v in mt.values()) == 4
    yb = yield_buckets(rw)
    cut = float(np.percentile([0.01, 0.02, 0.03], 100.0 * 2 / 3))
    assert abs(yb["cut"] - cut) < 1e-15 and yb["top_third"]["trades"] == 1 and yb["top_third"]["net"] == 5.0 and yb["rest"]["trades"] == 2 and yb["rest"]["net"] == 30.0 and yb["no_yield"] == 1, yb
    assert yield_buckets(SimpleNamespace(yld=np.array([np.nan, np.nan])))["no_yield"] == 2
    lx = late_exits(rw)
    assert lx == {"trades": 2, "net": -5.0, "mean_bps": -6.25, "of": 4}, lx
    tg = top_gains(rw, 2)
    assert [(t["rank"], t["symbol"], t["entry"], t["pnl"]) for t in tg] == [(1, "A", "2024-01-02", 40.0), (2, "C", "2024-02-01", 30.0)]
    return True


def t_files():
    """(f) the hand audit's file: read and checked (a mistyped row refuses, it never silently does nothing), a data_event removes that name's event from the entry set - so from both cells, all three rules and the nulls - and the audit status counts
    which of the listed contributors the file mentions (information only: the harness never decides (f))"""
    dw = dw_world()
    with tempfile.TemporaryDirectory() as td:
        path = os.path.join(td, "divrun_audit.csv")

        def put(txt):
            with open(path, "w", newline="\n") as f:
                f.write(txt)
        assert read_audit(path) is None
        put("symbol,event,cell,verdict,note\nN00,2024-10-03,R10,data_event,a split\nN01,2024-10-10,r20,KEEP ,nothing found\n")
        au = read_audit(path)
        assert au["verdict"].tolist() == ["data_event", "keep"] and au["cell"].tolist() == ["R10", "R20"] and au["event"].tolist() == [TS("2024-10-03"), TS("2024-10-10")]
        ctx = dw.ctx
        with spec(win=30, min_pairs=25):
            before = {K: entry_set(dw.W, ctx, K) for K in (10, 20)}
            cnt = apply_audit(ctx, au)
            assert cnt == {"rows": 2, "keep": 1, "data_event": 1} and int(ctx.aud_ev.sum()) == 1
            i = int(np.flatnonzero(ctx.aud_ev)[0])
            assert ctx.ev.sym[i] == "N00" and TS(ctx.ev.p_date[i]) == TS("2024-10-03")
            removed = 0
            for K in (10, 20):
                es = entry_set(dw.W, ctx, K)
                assert es.n == before[K].n - 1 and i not in es.idx.tolist() and sum(c.get("audit", 0) for c in es.cnt.values()) == 1
                for r in EXITS:
                    ta = trade_set(dw.W, ctx, es, r, "registered", dw.W.days[0], dw.W.days[-1])
                    tb = trade_set(dw.W, ctx, before[K], r, "registered", dw.W.days[0], dw.W.days[-1])
                    assert i not in ta.ev.tolist() and ta.n == tb.n - int(i in tb.ev.tolist()), (K, r)
                    removed += int(i in tb.ev.tolist())
            assert removed >= 3, "the event's trade leaves both cells, under the exit rules that traded it"
            assert apply_audit(ctx, None) == {"rows": 0, "keep": 0, "data_event": 0} and not ctx.aud_ev.any()
        # a row that cannot be read refuses; so does a data_event that matches no event
        head = "symbol,event,cell,verdict,note\n"
        for bad, frag in ((head + "N00,2024-10-03,R10,remove,x\n", "verdict outside keep | data_event"), (head + "N00,2024-10-03,R30,keep,x\n", "a cell outside"), (head + "N00,not a date,R10,keep,x\n", "unreadable"),
                          (head + ",2024-10-03,R10,keep,x\n", "unreadable"), ("symbol,event,verdict\nN00,2024-10-03,keep\n", "lacks the column")):
            put(bad)
            assert frag in refused(lambda: read_audit(path), "refused: divrun_audit.csv"), (bad, frag)
        put(head + "ZZZ,2024-10-03,R10,data_event,not on the grid\n")
        refused(lambda: apply_audit(dw.ctx, read_audit(path)), "match no event of the calendar")
        put(head + "N00,2024-10-04,R10,data_event,not the predicted ex-date\n")
        refused(lambda: apply_audit(dw.ctx, read_audit(path)), "match no event of the calendar")
        put(head + "ZZZ,2024-10-03,R10,keep,a keep row that matches nothing is only information\n")
        assert apply_audit(dw.ctx, read_audit(path))["keep"] == 1
        put("symbol,event,cell,verdict,note\nN00,2024-10-03,R10,keep,x\n")
        cands = {("NOX", "R10"): [{"symbol": "N00", "event": "2024-10-03"}, {"symbol": "N05", "event": "2024-10-03"}], ("X", "R10"): []}
        assert audit_status(cands, read_audit(path)) == {"NOX/R10": {"listed": 2, "audited": 1}, "X/R10": {"listed": 0, "audited": 0}} and audit_status(cands, None)["NOX/R10"] == {"listed": 2, "audited": 0}
        assert file_sha(path) == R11.sha_lf(path) and file_sha(os.path.join(td, "none.csv")) is None
    return True


def t_prereg():
    """the registered text is the spec: a missing or changed file refuses every stage BEFORE anything loads (the loaders are replaced by tripwires), a CRLF checkout of the same text is the same text, the real file passes; the stamp carries this file's sha"""
    real = open(PREREG, "rb").read()
    boom = lambda *a, **k: (_ for _ in ()).throw(AssertionError("a loader was reached before the pre-registration check"))
    with tempfile.TemporaryDirectory() as td:
        miss, changed, crlf = os.path.join(td, "missing.txt"), os.path.join(td, "changed.txt"), os.path.join(td, "crlf.txt")
        with open(changed, "wb") as f:
            f.write(real + b"x")
        with open(crlf, "wb") as f:
            f.write(real.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))
        with quiet():
            assert prereg_ok()["verified"] is True
            with patched(THIS, PREREG=crlf):
                assert prereg_ok()["verified"] is True
        assert R11.sha_lf(PREREG) == PREREG_SHA == "806ff96466944dbc5c10c4bc8000f4946260481e74eda06a8072d83dfbb63267"
        with tempfile.TemporaryDirectory() as out, patched(M17, load_data=boom, wide_load=boom, build_world=boom), patched(A13, load_463=boom), patched(D15, load_tbis=boom, load_es=boom), patched(THIS, OUT=out, ref_load=boom):
            with open(os.path.join(out, GO_FLAG), "w") as f:
                f.write("go")
            for cur, frag in ((miss, "not next to this file"), (changed, "DIFFERS")):
                with patched(THIS, PREREG=cur):
                    assert "lockbox NOT read" in refused(prereg_ok, frag)
                    refused(dryload, frag)
                    refused(stage_a, frag)
            assert not os.path.exists(os.path.join(out, READ_FLAG)) and not os.path.exists(os.path.join(out, "divrun_stageA.json"))
            with patched(THIS, PREREG_SHA="0" * 64):
                refused(prereg_ok, "DIFFERS")
    st = stamp()
    assert st["harness_sha256"] == R11.sha_lf(os.path.abspath(__file__)) and st["r17_sha256"] == M17.stamp()["harness_sha256"] and set(st) >= {"r15_sha256", "r13_sha256", "r12_sha256", "r11_sha256", "siporb_sha256", "wide_ca_sha256", "early_close"}
    return True


def t_stage_b_refusals():
    """Stage B is the lead's one read: it refuses, before the read flag exists and before a single input loads, unless the lead's go-flag is on file and Stage A left a judged candidate with the same spec, the same harness versions, the same audit file
    and a sane frozen size; the read flag is never written by a refusal"""
    boom = lambda *a, **k: (_ for _ in ()).throw(AssertionError("the book was loaded"))
    good = {"candidate": {"cell": "R10", "rule": REGISTERED, "c": 0.7}, "judged": True, "stageA": {"registered_pass_cells": ["R10"]}, "prereg_sha256_lf": PREREG_SHA, "audit_sha256": None, "manifest_sha256": "m", "parity": {}, **stamp()}
    with tempfile.TemporaryDirectory() as td, patched(THIS, OUT=td), patched(A13, load_463=boom), patched(M17, load_data=boom, wide_load=boom, build_world=boom):
        go, rd, sa = os.path.join(td, GO_FLAG), os.path.join(td, READ_FLAG), os.path.join(td, "divrun_stageA.json")

        def put(obj):
            with open(sa, "w") as f:
                json.dump(obj, f)

        def must(frag):
            with quiet():
                refused(stage_b, frag)
            assert not os.path.exists(rd), "a refusal never writes the read flag"
        must("go-flag")
        assert "is not on file" in refused(stage_b, "go-flag") and "nothing computed, lockbox NOT read" in refused(stage_b, "go-flag")
        with open(go, "w") as f:
            f.write("go: hand audit done, sealed-year day")
        must("no Stage A candidate")
        for edit in (lambda j: j.update(judged=False), lambda j: j.update(candidate=None), lambda j: j["stageA"].update(registered_pass_cells=["R20"]), lambda j: j["stageA"].update(registered_pass_cells=[]), lambda j: j.pop("stageA")):
            j = json.loads(json.dumps(good))
            edit(j)
            put(j)
            must("no Stage A candidate")
        put(good)
        with patched(THIS, PREREG_SHA="0" * 64):
            must("DIFFERS")
        j = dict(good, prereg_sha256_lf="0" * 64)
        put(j)
        must("another pre-registration")
        for k in ("harness_sha256", "r17_sha256", "r15_sha256", "wide_ca_sha256"):
            put(dict(good, **{k: "0" * 64}))
            must("different harness version")
        put({k: v for k, v in good.items() if k != "r13_sha256"})
        must("different harness version")
        put(good)
        with open(os.path.join(td, "divrun_audit.csv"), "w") as f:
            f.write("symbol,event,cell,verdict,note\n")
        must("not the file Stage A ran with")
        os.remove(os.path.join(td, "divrun_audit.csv"))
        for c in (0.0, -1.0, float("nan"), None, "abc"):
            put(dict(good, candidate={"cell": "R10", "rule": REGISTERED, "c": c}))
            must("positive number")
        put(dict(good, candidate={"cell": "R10", "rule": "ZZZ", "c": 0.7}))
        must("positive number")
        put(good)
        os.remove(go)
        must("go-flag")
        with open(go, "w") as f:
            f.write("go")
        with open(rd, "w") as f:
            f.write("read")
        refused(stage_b, "already read")
        refused(stage_a, "Stage A is frozen")
        os.remove(rd)
        # every refusal above came BEFORE anything loaded; a clean file gets as far as the book (the tripwire) and not one step further
        try:
            with quiet():
                stage_b()
            raise SystemExit("stage_b did not reach the book")
        except AssertionError as e:
            assert "the book was loaded" in str(e) and not os.path.exists(rd)
    return True


def t_cut():
    """the lockbox cut at read time, asserted [13]: Stage A and the dryload hand the loaders the cut 2025-06-30 and only that (the sealed year's end appears in Stage B alone), cut_checks refuses a session or a calendar row on / after the cut, and a
    Stage A run after the read flag is refused. The loaders are replaced by recorders that stop the stage at the first read"""
    dw = dw_world()
    W, cal = dw.W, dw.cal
    assert not any("S.END" in inspect.getsource(f) for f in (stage_a, dryload, cut_checks)) and "S.END" in inspect.getsource(stage_b) and "S.LB0" in inspect.getsource(stage_a) and "S.LB0" in inspect.getsource(dryload)
    assert "ref_load" in inspect.getsource(stage_a) and not any("ref_load" in inspect.getsource(f) for f in (stage_b, dryload)), "[X1] only Stage A reads RESMOM's line file; Stage B (the sealed year) and the dryload (counts only) never do"
    cut_checks(W, cal, S.LB0)
    cut_checks(W, None, S.LB0)
    refused(lambda: cut_checks(W, cal, W.days[-1]), "DIVRUN sessions", "on/after the cut")
    for nm in ("div", "spin", "split"):
        late = SimpleNamespace(**{**cal.__dict__})
        fr = pd.DataFrame({"symbol": ["N00"], "ex": [TS("2025-06-30")], "amt": [1.0], "special": [False], "type": ["x"]})
        setattr(late, nm, pd.concat([getattr(cal, nm), fr], ignore_index=True) if len(getattr(cal, nm)) else fr)
        refused(lambda: cut_checks(W, late, S.LB0), f"calendar {nm} ex-dates")
    ok = SimpleNamespace(**{**cal.__dict__})
    ok.div = pd.concat([cal.div, pd.DataFrame({"symbol": ["N00"], "ex": [TS("2025-06-27")], "amt": [1.0], "special": [False]})], ignore_index=True)
    cut_checks(W, ok, S.LB0)
    B, _S12 = M17.synth_book(seed=3, hi="2026-06-30")
    rbs = mk_ref(B)

    class Stop(Exception):
        pass
    calls = []

    def wl(cut, need=True, enforce=True):
        calls.append(("wide_load", TS(cut)))
        return cal, {"path": "stub"}

    def ld(cut):
        calls.append(("load_data", TS(cut)))
        raise Stop
    with tempfile.TemporaryDirectory() as td, patched(THIS, OUT=td, CHECK_BOOK=False, manifest_sha=lambda: D15.MANIFEST_PREFIX + "0" * 56, ref_load=lambda B_: rbs), patched(M17, wide_load=wl, load_data=ld), patched(A13, load_463=lambda: (B, [])):
        for fn, want in ((stage_a, [("wide_load", S.LB0), ("load_data", S.LB0)]), (dryload, [("load_data", S.LB0)])):
            del calls[:]
            try:
                with quiet():
                    fn()
                raise AssertionError(f"{fn.__name__} did not read")
            except Stop:
                pass
            assert calls == want and all(c[1] < S.END for c in calls), (fn.__name__, calls)
        with open(os.path.join(td, READ_FLAG), "w") as f:
            f.write("read")
        del calls[:]
        refused(stage_a, "Stage A is frozen")
        assert not calls, "a frozen Stage A reads nothing"
    return True


def t_integration():
    """the whole pipeline on a hand-made world and a synthetic #463, every piece: the three exit rules on one entry set, the stress rows' costs against the closed form, the placebo and random-name nulls, the unhedged leg and sub-periods, the checks,
    the reports, the audit candidates (largest gains first), the printing"""
    mp = mp_world()
    W, ctx = mp.W, mp.ctx
    B, S12 = M17.synth_book(seed=3, hi="2026-06-30")
    rowsB = A13.book_rows(B, W)
    rb = mk_ref(B)
    wf = np.asarray((W.days >= WF0) & (W.days <= PRE_END))
    with spec(win=30, min_pairs=25), patched(THIS, A2_WIN=(TS("2024-06-03"), TS("2025-03-31"))):                 # A2's window moved onto the hand-made world's own year: c exists
        res, obj = evaluate(W, ctx, B, S12, rb, rowsB, "registered", 40, 0, full=True)
        cells = res["cells"]
        assert set(cells) == set(EXITS) and all(set(cells[r]) == set(CELLS) for r in EXITS) and set(res["null"]) == set(NULL_EXITS)
        for rule in EXITS:
            for cell in CELLS:
                c, o = cells[rule][cell], obj.objs[(rule, cell)]
                assert set(c) >= {"base", "cost0", "stress", "seat", "seat_ref", "A2", "gate70", "unhedged", "hedge_leg", "sub", "hedge_gap", "hedge_contracts"} and set(c["stress"]) == {"10 bps", "20 bps"} and c["base"]["n_pos"] == o.tr.n > 10, (rule, cell, c["base"]["n_pos"])
                assert {"incremental_pass", "book_shadow_line", "reference", "plain_463", "at_half_c", "at_double_c", "roc_gain", "sortino_gain"} <= set(c["A2"]) and "pass" not in c["A2"] and c["A2"]["reference"]["roc"] == rb.stats["roc"], (rule, cell)
                assert abs(c["cost0"]["net"] - c["base"]["net"] - SPEC["slot"] * 5.0 * 1e-4 * (o.tr.n + float(o.bu.pa.ve.sum()))) < 1e-6 and c["cost0"]["net"] > c["base"]["net"], "[X2] the 0 bps row: the stock's costs taken out"
                assert set(o.tr.ev.tolist()) <= set(obj.es[cell].idx.tolist()), "one entry set under all three exit rules"
                assert abs(c["base"]["net"] - float(o.run.x[wf].sum())) < 1e-6 and abs(c["unhedged"]["net"] - float(o.run.x_unhedged[wf].sum())) < 1e-6
                ve = o.bu.pa.ve
                for extra, key in ((5.0, "10 bps"), (15.0, "20 bps")):
                    want = c["base"]["net"] - SPEC["slot"] * extra * 1e-4 * (o.tr.n + float(ve.sum()))
                    assert abs(c["stress"][key]["net"] - want) < 1e-6, (rule, cell, key, c["stress"][key]["net"], want)
                assert sum(v["n_pos"] for v in c["sub"].values()) == c["base"]["n_pos"] and abs(sum(v["net"] for v in c["sub"].values()) - c["base"]["net"]) < 1e-6, "the two sub-periods partition the stretch"
                g = c["hedge_gap"]
                assert abs(g["hedge_as_traded_net"] - float((o.run.hedge_agg)[wf].sum())) < 1e-6 and abs(g["gap_sum"] - (g["hedge_as_traded_net"] - g["hedge_exact_net"])) < 1e-6
                if rule in NULL_EXITS:
                    assert len(c["checks"]) == 9 and c["PASS"] is all(c["checks"].values()) and {"placebo", "random_name_null"} <= set(c), (rule, cell)
                    assert 0 <= c["placebo"]["trades_left_out_per_draw_mean"] <= o.tr.n
                else:
                    assert c["PASS"] is None and len(c["checks_without_null"]) == 8 and "placebo" not in c
        for rule in NULL_EXITS:
            nl = res["null"][rule]
            assert nl["draws"] == 40 and nl["seed"] == SEED and nl["roc_max"]["finite"] >= 30 and nl["by_cell"]["R10"]["finite"] >= 30 and nl["random_names"]["draws"] == 40
        # the naive (look-ahead) reading is the same code with the hold-flagged trades kept: here nothing is flagged in a hold (the world has few), so it is the same cell or a superset
        resK, objK = evaluate(W, ctx, B, S12, rb, rowsB, "naive", 0, 1, full=False, es=obj.es)
        for rule in EXITS:
            for cell in CELLS:
                assert objK.objs[(rule, cell)].tr.n >= obj.objs[(rule, cell)].tr.n and ("PASS" not in resK["cells"][rule][cell]) == (rule in NULL_EXITS), (rule, cell)
        rep, cands = reports(W, ctx, B, S12, rb, rowsB, obj.objs, cells, None, {}, [])
        assert set(cands) == {(r, c) for r in ("X", REGISTERED) for c in CELLS} and set(rep["ref_episodes"]) == set(EXITS) and set(rep["trades_by_year"]) == set(EXITS)
        for (rule, cell), rows in cands.items():
            o = obj.objs[(rule, cell)]
            assert 0 < len(rows) <= AUDIT_N and [r["rank"] for r in rows] == list(range(1, len(rows) + 1)) and abs(rows[0]["pnl"] - float(o.run.pos.pnl.max())) < 1e-9
            assert all(rows[i]["pnl"] >= rows[i + 1]["pnl"] for i in range(len(rows) - 1)) and all(r["cell"] == cell and r["rule"] == rule and r["symbol"].startswith("N") for r in rows)
            r0 = rows[0]
            iev = int(o.tr.ev[int(np.argmax(o.run.pos.pnl))])
            assert r0["event"] == f"{TS(ctx.ev.p_date[iev]):%Y-%m-%d}" and f"P {r0['event']}" in r0["calendar_row"] and abs(r0["stock_pnl"] + r0["hedge_pnl"] - r0["pnl"]) < 1e-9
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            print_cells(res)
            print_funnel(obj.es)
            print_hygiene("registered", {k: o.tr for k, o in obj.objs.items()})
            print_reports(rep, cells)
            print_diagnostics(res, rep, rb)
        txt = buf.getvalue()
        for frag in ("exit rule X:", "exit rule NOX:", "exit rule P10:", "placebo-in-time null (40 draws, seed 20261005", "second null (REPORTED) random names", "UNHEDGED leg (reported)", "sub-periods:", "A2 (a report)", "R10 vs R20 under NOX",
                     "yield buckets", "late / skipped dividend exits", "realised beta to ES", "REPORTED (no registered null)", "R10 (K = 10) events", "removed at their first reason", "A2 (a report) [X1]", "#70 gate basis [X1]", "DIAGNOSTICS [X2]", "COST CURVE", "INCREMENTAL PASS" if any(c["A2"]["incremental_pass"] for r in EXITS for c in cells[r].values()) else "no incremental pass"):
            assert frag in txt, frag
        ver, passing, cand = stage_a_flow(cells)
        assert set(ver) == set(CELLS) and set(passing) <= set(CELLS) and (cand is None) == (not passing)
    return True


def t_cut_invariance():
    """the cut must not change WHICH trades Stage A and Stage B's WF re-read hold: events whose P is the first session the data does not hold (the cut Monday in the real run: a predicted ex-date on 06-28 .. 06-30) are placed there by date arithmetic, so
    their entries (K sessions before) and NO-X exits (the last session of the data) are in the cut data's WF set exactly as in the full data's, trade for trade with the same P&L; one session later (P two sessions past the data) stays out. The X-rule is
    the documented exception: an ex-date on / after the cut is not read, so those events fall back to P + 10 (unresolved) in the cut data"""
    full, cut = mp_world(T=440), mp_world(T=440, T_cut=423)
    assert cut.W.T == 423 and full.W.T == 440 and cut.W.days[-1].day_name() == "Wednesday" and full.W.days[423].day_name() == "Thursday"
    ev = cut.ctx.ev
    ph = ev.cyc & (ev.p_row == cut.W.T)
    assert ph.sum() >= 8 and (ev.p_row[ev.cyc] <= cut.W.T).sum() > 0 and ev.counts["cycle_ok_p_on_the_next_session"] == int(ph.sum()), "eight names in the phase whose ex-date is the first session the data does not hold"
    assert all(TS(ev.p_date[i]) == full.days[423] for i in np.flatnonzero(ph)) and (ev.x_row[ph] == -1).all(), "P is that session; X is not read (its row is on / after the cut)"
    with spec(win=30, min_pairs=25):
        for K in (10, 20):
            ef, ec = entry_set(full.W, full.ctx, K), entry_set(cut.W, cut.ctx, K)
            lo, hi = full.W.days[0], full.W.days[422]
            tf = trade_set(full.W, full.ctx, ef, REGISTERED, "registered", lo, hi)
            tc = trade_set(cut.W, cut.ctx, ec, REGISTERED, "registered", lo, hi)
            key = lambda W, tr: [(str(W.syms[c]), int(e), int(x), round(float(b), 12)) for c, e, x, b in zip(tr.col, tr.e, tr.x, tr.beta)]
            assert key(full.W, tf) == key(cut.W, tc) and tf.n == tc.n > 100, (K, tf.n, tc.n)
            assert (tc.x == 422).sum() >= 8 and (tc.p == 423).sum() >= 8 and (tc.e[tc.p == 423] == 423 - K).all(), "the phantom-P events enter K sessions before it and exit at the last session of the data"
            rf, rc = run_bundle(full.W, prepare(full.W, tf)), run_bundle(cut.W, prepare(cut.W, tc))
            assert usd(rf.pos.pnl, rc.pos.pnl) and usd(rf.x[:423], rc.x) and usd(rf.x[423:], 0.0), "the same P&L trade for trade and day for day"
            xf = trade_set(full.W, full.ctx, ef, "X", "registered", lo, hi)
            xc = trade_set(cut.W, cut.ctx, ec, "X", "registered", lo, hi)
            assert xf.n - xc.n == int((tc.p == 423).sum()) and sum(c.get("unresolved", 0) for c in xc.cnt.values()) == int((tc.p == 423).sum()), "the X-rule's exit of those events needs X: unread, so unresolved in the cut data"
    # one session later is out: a P two sessions past the data has no row
    assert (ev.p_row[ev.cyc & (ev.p_row > cut.W.T)]).size == 0 and int((ev.cyc & (ev.p_row < 0)).sum()) == ev.counts["cycle_ok_p_beyond_the_data"] > 0
    return True


TESTS = ("t_constants", "t_events", "t_entry", "t_beta", "t_hedge", "t_pnl", "t_hygiene", "t_engine", "t_placebo", "t_randomname", "t_null_summary", "t_path", "t_yardstick", "t_judge", "t_reports", "t_files", "t_prereg",
         "t_stage_b_refusals", "t_cut", "t_cut_invariance", "t_reference", "t_a2", "t_ref_episodes", "t_cost0", "t_diag", "t_path_x", "t_integration")


def selftest():
    """hand-made worlds and calendars, no files, no data, no network: every group of tests prints one line, the last line says how many ran"""
    t0 = time.time()
    with tempfile.TemporaryDirectory() as td, patched(THIS, REF_CSV=os.path.join(td, "no_such_dir", "resmom_cells_daily_wf.csv")):          # the real RESMOM line file is never read by a test: a read that is not stubbed lands here and refuses
        for name in TESTS:
            t1 = time.time()
            globals()[name]()
            print(f"  {name} ok ({time.time() - t1:.1f}s)", flush=True)
    print(f"selftest ok: {len(TESTS)} groups ({', '.join(t[2:] for t in TESTS)}) in {time.time() - t0:.0f}s")
# ------------------------------------------------------------------ [X1] / [X2]: the reference book, the incremental A2, the episode table on the reference, the 0 bps row, the diagnostics, the X-axis path (synthetic data only)
def plain_stats(x, dates):
    """plain python (no numpy cumulative sums): net, years, the deepest peak-to-trough of the running sum from a peak of 0, ROC @ $30k and Sortino (mean / the root mean square of the losing days x sqrt(252)) - the house yardstick, recounted"""
    eq = peak = mdd = 0.0
    for v in x:
        eq += float(v)
        peak = max(peak, eq)
        mdd = max(mdd, peak - eq)
    n, net = len(x), float(sum(float(v) for v in x))
    yrs = (pd.Timestamp(dates[-1]) - pd.Timestamp(dates[0])).days / 365.25
    dn = math.sqrt(sum(min(float(v), 0.0) ** 2 for v in x) / n)
    nan = float("nan")
    return {"net": net, "years": yrs, "max_dd": mdd, "roc": 30.0 * (net / yrs) / mdd if mdd > 0 else nan, "sortino": (net / n) / dn * math.sqrt(252.0) if dn > 0 else nan}


def plain_episodes(x):
    """plain python recount of r11_risk.underwater + r12_mdl.qualifying: the maximal runs under the running peak (from 0): (depth, i0 = the day after the peak, it = the trough, i1 = the last day under water), deepest first (ties keep time order);
    the qualifying ones are at least 1/3 as deep as the deepest"""
    eq = peak = 0.0
    dd = []
    for v in x:
        eq += float(v)
        peak = max(peak, eq)
        dd.append(peak - eq)
    eps, i, n = [], 0, len(dd)
    while i < n:
        if dd[i] <= 0:
            i += 1
            continue
        j = i
        while j + 1 < n and dd[j + 1] > 0:
            j += 1
        t = max(range(i, j + 1), key=lambda q: (dd[q], -q))
        eps.append((dd[t], i, t, j))
        i = j + 1
    eps.sort(key=lambda e: -e[0])
    return eps, ([e for e in eps if e[0] >= eps[0][0] / M12.DD_DIV] if eps else [])


def mk_ref(B, seed=11, block=True):
    """a synthetic RES line on #463's WF rows (RES ~ N(5, 300) a day and - block - a loss of $3,000 a day on the 30 rows from 2018-09-03: the reference, #463 + 0.264 x RES, then has a deep drawdown of its own in 2018 that #463 alone has not) and
    the reference book built on it (ref_build, no file)"""
    k = np.flatnonzero(B.mask(WF0, PRE_END))
    res = np.random.default_rng(seed).normal(5.0, 300.0, len(k))
    if block:
        i0 = int(np.searchsorted(B.index[k], TS("2018-09-03")))
        res[i0:i0 + 30] -= 3000.0
    return ref_build(B, res)


def write_ref_csv(path, B, res_wf, mutate=None, crlf=False, bom=False):
    """a stub of RESMOM's WF line file - date, book_mtm (#463's own daily P&L), RES, RAW on #463's WF index rows, 6 decimals (it is text: rounded) - mutate(df) edits the table before it is written -> the sha256 of its BYTES (a test's registered pin)"""
    k = np.flatnonzero(B.mask(WF0, PRE_END))
    df = pd.DataFrame({"date": [f"{d:%Y-%m-%d}" for d in B.index[k]], "book_mtm": np.asarray(B.raw, float)[k], "RES": np.asarray(res_wf, float), "RAW": 0.5 * np.asarray(res_wf, float)})
    if mutate is not None:
        df = mutate(df)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    df.to_csv(path, index=False, float_format="%.6f", lineterminator="\r\n" if crlf else "\n")
    if bom:
        with open(path, "rb") as f:
            body = f.read()
        with open(path, "wb") as f:
            f.write(b"\xef\xbb\xbf" + body)
    with open(path, "rb") as f:
        return raw_sha(f.read())


def reg_ref_series(B):
    """a series on #463's WF rows with EXACTLY the registered reference numbers - ROC @ $30k 120.82, Sortino 3.916, worst drawdown $36,526 (r11_risk.stats of the WF rows): IID noise + s2 x a telescoping noise (it adds downside without adding
    drawdown) + a drift mu; for a given s2 the drift is bisected for the ROC (ROC rises with the drift: the drawdown never deepens), then s2 for the Sortino (it falls as s2 rises), then the whole series is scaled to the drawdown (ROC and Sortino
    are scale-free). The synthetic book's own series is not involved: RES = (this - #463) / 0.264 puts it in a stub file"""
    k = np.flatnonzero(B.mask(WF0, PRE_END))
    ds = B.index[k]
    rng = np.random.default_rng(2026)
    g, e = rng.standard_normal(len(k)), rng.standard_normal(len(k) + 1)
    tele = e[1:] - e[:-1]
    st = lambda x: R11.stats(x, ds)

    def mu_for(s2, roc):
        lo, hi = -2.0, 20.0
        for _ in range(55):
            mid = 0.5 * (lo + hi)
            lo, hi = (mid, hi) if st(g + s2 * tele + mid)["roc"] < roc else (lo, mid)
        return 0.5 * (lo + hi)
    lo, hi = 0.0, 4.0
    for _ in range(55):
        mid = 0.5 * (lo + hi)
        lo, hi = (mid, hi) if st(g + mid * tele + mu_for(mid, 120.82))["sort"] > 3.916 else (lo, mid)
    s2 = 0.5 * (lo + hi)
    x = g + s2 * tele + mu_for(s2, 120.82)
    out = x * (36526.0 / st(x)["max_dd"])
    s = st(out)
    assert abs(s["roc"] - 120.82) < 1e-6 and abs(s["sort"] - 3.916) < 1e-6 and abs(s["max_dd"] - 36526.0) < 1e-6, s
    return out


def res_from_ref(B, ref_wf):
    """the RES column that makes #463 + 0.264 x RES equal the given reference series on the WF rows"""
    k = np.flatnonzero(B.mask(WF0, PRE_END))
    return (np.asarray(ref_wf, float) - np.asarray(B.raw, float)[k]) / REF_W


def t_reference():
    """[X1] RES's WF line -> the REFERENCE book (#463 + 0.264 x RES), on stubbed files only: the file is read and pinned by the sha256 of its BYTES (a CRLF copy is another file), refused when it is not on file, has another sha, lacks a column, has
    unreadable / unordered / duplicate dates, a date on / after the cut, dates that are not #463's WF index row for row (a row missing, one too many, one off the index), a missing / non-finite number, a book_mtm that is not #463's own P&L (a dollar of
    rounding is fine, five dollars is not); the registered facts (ROC 120.82 +-0.01, Sortino 3.916 +-0.001, worst drawdown $36,526 +-$1) are asserted on the reference - accepted inside the tolerances, refused outside, refused by the real constants on a stub, skipped
    only when CHECK_BOOK is off - and the comparator is exercised on the literal registered numbers"""
    B, S12 = M17.synth_book(seed=3, hi="2026-06-30")
    k = np.flatnonzero(B.mask(WF0, PRE_END))
    res_wf = mk_ref(B).res[k]
    tail = "(nothing computed, lockbox NOT read)"
    with tempfile.TemporaryDirectory() as td:
        def load(mutate=None, crlf=False, pin=None, check=False, name="resmom_cells_daily_wf.csv", res=None, bom=False, **kw):
            p = os.path.join(td, name)
            sha = write_ref_csv(p, B, res_wf if res is None else res, mutate=mutate, crlf=crlf, bom=bom)
            with patched(THIS, REF_SHA=sha if pin is None else pin, REF_CSV=p, **kw):
                return ref_load(B, check_facts=check)

        def bad(frag, **kw):
            return refused(lambda: load(**kw), "refused:", frag, tail)
        # the right file: the reference is #463 + 0.264 x RES on the WF rows and nothing outside them
        ref = load()
        ws = np.asarray(B.mask(WF0, PRE_END))
        assert ref.n_rows == len(k) == int(ws.sum()) and np.array_equal(ref.rows, k) and ref.max_book_diff < 1e-6 and len(ref.sha) == 64 and os.path.basename(ref.path) == "resmom_cells_daily_wf.csv"
        assert np.allclose(ref.raw[k], np.asarray(B.raw)[k] + 0.264 * res_wf, atol=1e-5, rtol=0) and np.isnan(ref.raw[~ws]).all() and np.isnan(ref.res[~ws]).all() and np.allclose(ref.res[k], res_wf, atol=1e-5, rtol=0)
        assert ref.S.T == len(k) and (ref.S.rows == k).all() and ref.S.dates.equals(B.index[k]) and ref.stats["roc"] == R11.stats(ref.raw[k], B.index[k])["roc"]
        sh = plain_stats(ref.raw[k], B.index[k])
        assert abs(ref.stats["roc"] - sh["roc"]) < 1e-8 and abs(ref.stats["sort"] - sh["sortino"]) < 1e-9 and abs(ref.stats["max_dd"] - sh["max_dd"]) < 1e-6
        assert set(ref.facts) == {"roc", "sortino", "max_dd"} and not all(ref.ok.values()), "the synthetic reference cannot be the registered one"
        rec = ref_record(ref)
        assert rec["sha256"] == ref.sha and rec["pinned_sha256"] == REF_SHA and rec["rows"] == len(k) and rec["registered"] == REF_FACTS and rec["weight_of_RES"] == 0.264 and json.loads(json.dumps(rec, default=R11.js))["structure"]["episodes"] == ref.structure["episodes"]
        # the sha is of the BYTES: the same table with CRLF line endings is another file (refused under the LF file's pin), and loads under its own
        sha_lf = write_ref_csv(os.path.join(td, "lf.csv"), B, res_wf)
        sha_crlf = write_ref_csv(os.path.join(td, "crlf.csv"), B, res_wf, crlf=True)
        assert sha_lf != sha_crlf and raw_sha(open(os.path.join(td, "crlf.csv"), "rb").read()) == sha_crlf and R11.sha_lf(os.path.join(td, "crlf.csv")) == R11.sha_lf(os.path.join(td, "lf.csv")) == sha_lf
        assert load(crlf=True, name="crlf2.csv").n_rows == len(k)
        msg = bad("is not the registered", crlf=True, pin=sha_lf, name="crlf3.csv")
        assert sha_crlf in msg and sha_lf in msg
        # a byte-order mark and padded column names are not part of the names
        assert load(bom=True, name="bom.csv").n_rows == len(k) and load(mutate=lambda d: d.rename(columns={"RES": " RES ", "date": "date "}), name="pad.csv").n_rows == len(k)
        # the pin: another sha refuses, the real pin refuses a stub, a missing file refuses
        assert "0" * 64 in bad("is not the registered", pin="0" * 64)
        p0 = os.path.join(td, "resmom_cells_daily_wf.csv")
        with patched(THIS, REF_CSV=p0):
            assert REF_SHA in refused(lambda: ref_load(B, check_facts=False), "RESMOM line file", "is not the registered", tail)
        refused(lambda: ref_load(B, os.path.join(td, "nope.csv"), check_facts=False), "is not on file", tail)
        # the columns and the dates
        bad("lacks the column", mutate=lambda d: d.drop(columns=["RAW"]))
        bad("lacks the column", mutate=lambda d: d.rename(columns={"RES": "res"}))
        bad("not readable", mutate=lambda d: d.assign(date=["not a date"] + d["date"].tolist()[1:]))
        bad("strictly increasing", mutate=lambda d: d.iloc[::-1].reset_index(drop=True))
        bad("strictly increasing", mutate=lambda d: pd.concat([d.iloc[:1], d], ignore_index=True))
        late = lambda d: pd.concat([d, pd.DataFrame({"date": ["2025-06-30"], "book_mtm": [0.0], "RES": [0.0], "RAW": [0.0]})], ignore_index=True)
        with patched(THIS, REF_SHA=write_ref_csv(os.path.join(td, "late.csv"), B, res_wf, mutate=late), REF_CSV=os.path.join(td, "late.csv")):
            refused(lambda: ref_load(B, check_facts=False), "RESMOM line file holds a date on/after the cut 2025-06-30")
        # the dates are #463's WF index row for row: a row missing, a row too many, a date off the index, shifted dates
        bad("row for row", mutate=lambda d: d.drop(d.index[10]).reset_index(drop=True))
        bad("row for row", mutate=lambda d: d.iloc[1:].reset_index(drop=True))
        bad("row for row", mutate=lambda d: pd.concat([pd.DataFrame({"date": ["2016-06-30"], "book_mtm": [0.0], "RES": [0.0], "RAW": [0.0]}), d], ignore_index=True))
        jf = int(np.flatnonzero(B.index[k].dayofweek == 4)[3])
        sat = f"{B.index[k][jf] + pd.Timedelta(days=1):%Y-%m-%d}"
        assert pd.Timestamp(sat).dayofweek == 5 and pd.Timestamp(sat) not in B.index
        assert "1 of the file's dates are not on it" in bad("row for row", mutate=lambda d: d.assign(date=d["date"].tolist()[:jf] + [sat] + d["date"].tolist()[jf + 1:]))
        # the numbers: missing / non-finite, and book_mtm must be #463's own daily P&L
        bad("non-finite", mutate=lambda d: d.assign(RES=[float("nan")] + d["RES"].tolist()[1:]))
        bad("non-finite", mutate=lambda d: d.assign(book_mtm=[float("inf")] + d["book_mtm"].tolist()[1:]))
        bad("non-finite", mutate=lambda d: d.assign(RAW=["abc"] + d["RAW"].tolist()[1:]))

        def bump(dv):
            return lambda d: d.assign(book_mtm=d["book_mtm"].to_numpy() + np.where(np.arange(len(d)) == 7, dv, 0.0))
        msg = bad("not #463's own daily P&L", mutate=bump(5.0))
        assert f"{B.index[k][7]:%Y-%m-%d}" in msg and "$5.00" in msg
        assert load(mutate=bump(0.005)).max_book_diff < 0.0051, "a cent of rounding is fine"
        assert abs(load(mutate=bump(0.9)).max_book_diff - 0.9) < 1e-5 and abs(load(mutate=bump(-0.9)).max_book_diff - 0.9) < 1e-5, "rounding to the dollar is fine (the tolerance is REF_BOOK_ATOL = $1)"
        bad("not #463's own daily P&L", mutate=bump(-1.2))
        bad("not #463's own daily P&L", mutate=bump(1.1))
        # the registered facts: the stub's own numbers pass, the edges of the tolerances (inclusive), the real constants refuse
        f0 = load().facts
        assert all(load(check=True, REF_FACTS=f0).ok.values())
        for key, tol in (("roc", 0.01), ("sortino", 0.001), ("max_dd", 1.0)):
            for sgn in (1, -1):
                assert all(load(check=True, REF_FACTS={**f0, key: f0[key] + sgn * 0.9 * tol}).ok.values()), (key, sgn)
                bad("does not reproduce its registered WF numbers", check=True, REF_FACTS={**f0, key: f0[key] + sgn * 1.1 * tol})
        msg = bad("does not reproduce its registered WF numbers", check=True)
        assert "120.82" in msg and "3.916" in msg and "36,526" in msg and f"ROC@30k {f0['roc']:.2f}" in msg, "the real constants refuse the stub, and the refusal shows both sides"
        with patched(THIS, CHECK_BOOK=True):
            bad("does not reproduce its registered WF numbers", check=None)
        with patched(THIS, CHECK_BOOK=False):
            assert load(check=None).n_rows == len(k), "with CHECK_BOOK off (the smoke only) the facts are not asserted - the file, the sha and the rows still are"
        # the registered numbers THEMSELVES, with the real constants and tolerances: a stub whose reference is exactly ROC 120.82 / Sortino 3.916 / worst drawdown $36,526 passes; each tolerance is accepted inside and refused outside
        T0 = reg_ref_series(B)
        s0 = R11.stats(T0, B.index[k])
        assert abs(s0["roc"] - 120.82) < 1e-6 and abs(s0["sort"] - 3.916) < 1e-6 and abs(s0["max_dd"] - 36526.0) < 1e-6, s0
        rr = load(res=res_from_ref(B, T0), check=True)
        assert all(rr.ok.values()) and abs(rr.facts["roc"] - 120.82) < 1e-4 and abs(rr.facts["sortino"] - 3.916) < 1e-5 and abs(rr.facts["max_dd"] - 36526.0) < 1e-2, rr.facts
        assert rr.structure["episodes"] >= 1 and (REF_FACTS, REF_TOL) == ({"roc": 120.82, "sortino": 3.916, "max_dd": 36526.0}, {"roc": 0.01, "sortino": 0.001, "max_dd": 1.0})
        for f_, good in ((1 + 0.9 / 36526.0, True), (1 - 0.9 / 36526.0, True), (1 + 1.1 / 36526.0, False), (1 - 1.1 / 36526.0, False)):       # scaling moves the drawdown only
            if good:
                assert all(load(res=res_from_ref(B, T0 * f_), check=True).ok.values()), f_
            else:
                bad("does not reproduce its registered WF numbers", res=res_from_ref(B, T0 * f_), check=True)

        def drifted(d_roc):                                                                  # T0 + a constant a day, the constant bisected until the ROC is 120.82 + d_roc (the drawdown restored by scaling)
            lo, hi = -2000.0, 2000.0
            for _ in range(60):
                mid = 0.5 * (lo + hi)
                lo, hi = (mid, hi) if R11.stats(T0 + mid, B.index[k])["roc"] < 120.82 + d_roc else (lo, mid)
            Td = T0 + 0.5 * (lo + hi)
            return Td * (36526.0 / R11.stats(Td, B.index[k])["max_dd"])                         # scaled back to the registered drawdown: ROC and Sortino are scale-free
        for d_roc, good in ((0.009, True), (-0.009, True), (0.0115, False), (-0.0115, False)):
            Td = drifted(d_roc)
            sd = R11.stats(Td, B.index[k])
            assert abs(sd["roc"] - (120.82 + d_roc)) < 1e-6 and abs(sd["sort"] - 3.916) < 0.001 and abs(sd["max_dd"] - 36526.0) < 1.0, (d_roc, sd)
            if good:
                assert all(load(res=res_from_ref(B, Td), check=True).ok.values()), d_roc
            else:
                bad("does not reproduce its registered WF numbers", res=res_from_ref(B, Td), check=True)
    # the comparator on the literal registered numbers: inclusive tolerances, a NaN fails
    reg = {"roc": 120.82, "sort": 3.916, "max_dd": 36526.0}
    got, ok = ref_facts_ok(reg)
    assert got == {"roc": 120.82, "sortino": 3.916, "max_dd": 36526.0} and all(ok.values()) and set(ok) == {"roc", "sortino", "max_dd"}
    for key, k_, hi_, lo_, over in (("roc", "roc", 120.8299, 120.8101, 0.0101), ("sortino", "sort", 3.9169, 3.9151, 0.0011), ("max_dd", "max_dd", 36526.9, 36525.1, 1.1)):
        assert ref_facts_ok({**reg, k_: hi_})[1][key] and ref_facts_ok({**reg, k_: lo_})[1][key], key
        base = reg[k_]
        assert not ref_facts_ok({**reg, k_: base + over})[1][key] and not ref_facts_ok({**reg, k_: base - over})[1][key], key
        assert not ref_facts_ok({**reg, k_: float("nan")})[1][key]
    assert ref_facts_ok({**reg, "roc": 120.9})[1] == {"roc": False, "sortino": True, "max_dd": True}
    assert (REF_FACTS, REF_TOL, REF_W) == ({"roc": 120.82, "sortino": 3.916, "max_dd": 36526.0}, {"roc": 0.01, "sortino": 0.001, "max_dd": 1.0}, 0.264)
    return True
def t_a2():
    """[X1] A2 as an INCREMENTAL report: the REFERENCE + c x the cell against the reference, c by the registered volatility rule against #463's std (never the reference's), the book at 0.5c and 2c, an incremental pass = ROC and Sortino both strictly
    above the reference's, the plain #463 + c x the cell book a reported row (with the draft's old bar beside it) - on a planted cell that hedges the reference's losses (it must pass) and on a losing one (it must not), every number recounted in plain
    python, the strictness at equality and for a NaN, a cell with no spread (no c), and c and the plain row unmoved by a change of reference"""
    B, S12 = M17.synth_book(seed=3, hi="2026-06-30")
    rb = mk_ref(B)
    k = np.flatnonzero(B.mask(WF0, PRE_END))
    ds, nb = B.index[k], B.n
    mw = np.asarray(B.mask(*A2_WIN))
    rng = np.random.default_rng(8)
    hedge, bad_ = np.zeros(nb), np.zeros(nb)
    hedge[k] = 0.4 * np.maximum(-rb.raw[k], 0.0) + rng.normal(0.0, 40.0, len(k))
    bad_[k] = rng.normal(-60.0, 500.0, len(k))
    ref_s = plain_stats(rb.raw[k], ds)
    for name, x, want_pass in (("hedge", hedge, True), ("losing", bad_, False)):
        a2 = a2_report(B, x, rb)
        sb, sc = float(np.std(np.asarray(B.raw)[mw], ddof=1)), float(np.std(x[mw], ddof=1))
        c = 0.25 * sb / sc
        assert abs(a2["c"] - c) <= 1e-12 * c and abs(a2["std_book"] - sb) <= 1e-12 * sb and abs(a2["std_cell"] - sc) <= 1e-12 * sc and a2["window"] == ["2017-03-01", "2019-02-28"] and a2["rows"] == int(mw.sum()) and a2["target"] == 0.25
        assert abs(a2["std_book"] - float(np.std(rb.raw[mw], ddof=1))) > 5.0, "c is set against #463's std, not the reference's (the two differ here)"
        assert abs(a2["reference"]["roc"] - ref_s["roc"]) < 1e-8 and abs(a2["reference"]["sortino"] - ref_s["sortino"]) < 1e-9 and abs(a2["reference"]["max_dd"] - ref_s["max_dd"]) < 1e-6 and a2["reference"]["weight_of_RES"] == 0.264
        assert a2["needs"] == {"roc": a2["reference"]["roc"], "sortino": a2["reference"]["sortino"]}
        for key, mult in (("", 1.0), ("at_half_c", 0.5), ("at_double_c", 2.0)):
            got = a2 if key == "" else a2[key]
            want = plain_stats((rb.raw + mult * c * x)[k], ds)
            assert abs(got["roc"] - want["roc"]) < 1e-8 and abs(got["sortino"] - want["sortino"]) < 1e-9 and abs(got["net"] - want["net"]) < 1e-6 and abs(got["max_dd"] - want["max_dd"]) < 1e-6, (name, key)
            if key:
                assert abs(got["c"] - mult * c) <= 1e-12 * c
        want_ok = bool(a2["roc"] > ref_s["roc"] and a2["sortino"] > ref_s["sortino"])
        assert a2["incremental_pass"] is want_ok is want_pass and a2["book_shadow_line"] is a2["incremental_pass"] and "pass" not in a2, (name, a2["roc"], ref_s["roc"], a2["sortino"], ref_s["sortino"])
        assert abs(a2["roc_gain"] - (a2["roc"] - ref_s["roc"])) < 1e-8 and abs(a2["sortino_gain"] - (a2["sortino"] - ref_s["sortino"])) < 1e-9 and ((a2["roc_gain"] > 0) == want_pass)
        pl = a2["plain_463"]
        wp = plain_stats((np.asarray(B.raw) + c * x)[k], ds)
        assert abs(pl["roc"] - wp["roc"]) < 1e-8 and abs(pl["sortino"] - wp["sortino"]) < 1e-9 and pl["old_bar"] == {"roc": 98.5005, "sortino": 3.816} and pl["old_bar_cleared"] is bool(wp["roc"] >= 98.5005 and wp["sortino"] >= 3.816)
        for key, mult in (("at_half_c", 0.5), ("at_double_c", 2.0)):
            w2 = plain_stats((np.asarray(B.raw) + mult * c * x)[k], ds)
            assert abs(pl[key]["roc"] - w2["roc"]) < 1e-8 and abs(pl[key]["sortino"] - w2["sortino"]) < 1e-9 and abs(pl[key]["c"] - mult * c) <= 1e-12 * c
        # a different reference moves the incremental numbers and nothing else: c, the stds and the plain row are #463's
        rb2 = mk_ref(B, seed=99, block=False)
        a2b = a2_report(B, x, rb2)
        assert a2b["c"] == a2["c"] and a2b["std_book"] == a2["std_book"] and a2b["plain_463"] == a2["plain_463"] and a2b["reference"]["roc"] != a2["reference"]["roc"] and a2b["roc"] != a2["roc"], name
    # the planted pair must be a real contrast: the hedging cell lifts BOTH figures, the losing one lowers both
    ah, al = a2_report(B, hedge, rb), a2_report(B, bad_, rb)
    assert ah["roc_gain"] > 5.0 and ah["sortino_gain"] > 0.2 and al["roc_gain"] < 0.0 and al["sortino_gain"] < 0.0, (ah["roc_gain"], ah["sortino_gain"], al["roc_gain"], al["sortino_gain"])
    # strictness: both figures strictly above, equal is not above, one is not enough, a NaN passes nothing
    r = {"roc": 120.82, "sort": 3.916}
    up = lambda dr, ds_: {"roc": r["roc"] + dr, "sortino": r["sort"] + ds_}
    assert incremental_pass(up(1e-9, 1e-9), r) and not incremental_pass(up(0.0, 0.0), r) and not incremental_pass(up(1.0, 0.0), r) and not incremental_pass(up(0.0, 1.0), r) and not incremental_pass(up(1.0, -1e-9), r)
    assert not incremental_pass(up(float("nan"), 1.0), r) and not incremental_pass(up(1.0, float("nan")), r) and not incremental_pass(up(-1.0, -1.0), r) and incremental_pass(up(5.0, 0.5), r)
    # a cell that adds nothing: no spread over the window -> no c (the registered rule), no pass, the reference and the plain row still reported
    zero = np.zeros(nb)
    az = a2_report(B, zero, rb)
    assert not math.isfinite(az["c"]) and az["incremental_pass"] is False and az["book_shadow_line"] is False and az["at_half_c"] is None and az["at_double_c"] is None and "error" in az and not math.isfinite(az["roc"])
    assert az["reference"]["roc"] == a2["reference"]["roc"] and az["plain_463"]["old_bar_cleared"] is False and az["plain_463"]["at_half_c"] is None
    # the plain rule survives for Stage B: c from plain_a2 is the same number
    assert plain_a2(B, hedge)["c"] == ah["c"] and "reference" not in plain_a2(B, hedge)
    # a reference whose own numbers are NaN (no drawdown, no losing day) cannot be beaten: nothing passes against a NaN
    flat = SimpleNamespace(**{**rb.__dict__, "stats": {"roc": float("nan"), "sort": float("nan"), "net": 0.0, "max_dd": 0.0}})
    af = a2_report(B, hedge, flat)
    assert af["incremental_pass"] is False and af["book_shadow_line"] is False and math.isfinite(af["roc"]) and not math.isfinite(af["reference"]["roc"]) and not math.isfinite(af["roc_gain"])
    return True


def t_ref_episodes():
    """[X1] the drawdown days of MANAGER #70's gate are the REFERENCE book's: its episodes by MDL r1's rule (r12_mdl.Stretch on the reference series - the code path r15 / r17 use for #463), against a plain-python recount (every run under the
    running peak, the qualifying ones at least 1/3 as deep as the deepest); the structure printed (episodes, DD days, DD weeks, by year); the table of episodes with the cell's P&L inside each (the DD days: the day after the peak .. the trough), its sum
    and the cell's DO = its P&L over the DD days / the reference's loss over them; and the reference's days are not #463's (a loss block in 2018 that #463 alone has not)"""
    B, S12 = M17.synth_book(seed=3, hi="2026-06-30")
    rb = mk_ref(B)
    k = np.flatnonzero(B.mask(WF0, PRE_END))
    ds = B.index[k]
    x_ref, S = rb.raw[k], rb.S
    eps, qual = plain_episodes(x_ref)
    assert len(S.episodes) == len(eps) and len(S.qual) == len(qual) >= 3 and len(qual) < len(eps), (len(S.episodes), len(eps), len(S.qual), len(qual))
    for e, p in zip(S.episodes, eps):
        assert (e["i0"], e["it"], e["i1"]) == (p[1], p[2], p[3]) and abs(e["depth"] - p[0]) < 1e-6, (e, p)
    mask = np.zeros(len(k), bool)
    for _d, i0, it, _i1 in qual:
        mask[i0:it + 1] = True
    assert (S.dd == mask).all() and S.n_dd_days == int(mask.sum()) and abs(S.dd_loss + float(x_ref[mask].sum())) < 1e-6
    st = rb.structure
    yr = ds.year.to_numpy()
    assert st["episodes"] == len(qual) and st["all_episodes"] == len(eps) and st["days"] == int(mask.sum()) and st["weeks"] == S.n_dd_weeks and abs(st["deepest"] - eps[0][0]) < 1e-6
    assert st["by_year"] == {int(y): int((mask & (yr == y)).sum()) for y in sorted(set(yr[mask]))} and sum(st["by_year"].values()) == st["days"]
    # the planted 2018 loss block is a qualifying episode of the reference's own, and the reference's days are not #463's
    b0 = int(np.searchsorted(ds, TS("2018-09-03")))
    assert any(i0 <= b0 + 29 and it >= b0 for _d, i0, it, _i1 in qual), "an episode of the reference overlaps the planted block"
    assert not np.array_equal(S.dd, S12.dd) and S.n_dd_days != S12.n_dd_days, (S.n_dd_days, S12.n_dd_days)
    # the table: one row per qualifying episode of the REFERENCE, the cell's P&L inside it, against a recount
    rng = np.random.default_rng(4)
    xB = np.zeros(B.n)
    xB[k] = rng.normal(20.0, 200.0, len(k))
    tab = D15.episodes_table(S, xB)
    assert len(tab) == len(qual) == len(S.qual)
    for row, (dep, i0, it, _i1) in zip(tab, qual):
        assert row["first_dd_day"] == f"{ds[i0]:%Y-%m-%d}" and row["trough"] == f"{ds[it]:%Y-%m-%d}" and row["peak"] == str(ds[i0 - 1].date() if i0 > 0 else ds[0].date()) and abs(row["depth"] - dep) < 1e-6 and row["dd_days"] == it - i0 + 1
        assert abs(row["book_pnl"] - float(x_ref[i0:it + 1].sum())) < 1e-6 and abs(row["cell_pnl"] - float(xB[k][i0:it + 1].sum())) < 1e-6 and abs(row["book_pnl"] + row["depth"]) < 1e-6, row
    tot_cell, tot_book = sum(r_["cell_pnl"] for r_ in tab), sum(r_["book_pnl"] for r_ in tab)
    assert abs(tot_cell - float(xB[k][mask].sum())) < 1e-6 and abs(tot_book - float(x_ref[mask].sum())) < 1e-6
    sm = D15.seat_measure(S, xB)
    assert abs(sm["DO"] - tot_cell / -tot_book) < 1e-9 and sm["dd_days"] == st["days"] and sm["dd_weeks"] == st["weeks"], (sm["DO"], tot_cell, tot_book)
    s463 = D15.seat_measure(S12, xB)
    assert abs(s463["DO"] - sm["DO"]) > 1e-6 and s463["dd_days"] != sm["dd_days"], "the DO against the reference's days is not the DO against #463's"
    # the null's DO uses the same days: realised() on the stretch, draw by draw
    acc = rng.normal(0.0, 100.0, (3, len(k)))
    roc_n, rho_n, do_n = D15.null_cell(S, acc, k, B.n)
    assert np.allclose(do_n, acc[:, mask].sum(axis=1) / -float(x_ref[mask].sum()), atol=1e-12, rtol=1e-9) and np.allclose(roc_n, D15.null_cell(S12, acc, k, B.n)[0], equal_nan=True), "the null's DO is on the reference's days, its ROC on the same stretch"
    # the printing: the structure line with the registered facts' status
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        print_reference(rb)
    txt = buf.getvalue()
    assert "REFERENCE book [X1]" in txt and f"{st['episodes']} qualifying episodes of {st['all_episodes']}" in txt and f"{st['days']} DD days" in txt and f"{st['weeks']} DD weeks" in txt and "NOT reproduced" in txt and "the #70 gate" in txt
    assert f"#463 alone: {D15.DD_REF['episodes']} episodes, {D15.DD_REF['days']} DD days" in txt and "(no file)" in txt
    return True


def t_cost0():
    """[X2] the cost curve's 0 bps row: the stock's cost taken to zero (the ES hedge keeps its own), on a hand-made world - the stock leg's P&L at each of 0 / 5 / 10 / 20 bps against the plain-python trade recount, the closed form net(b) = net(0) - slot x b x 1e-4 x
    (trades + the sum of the exit values per $1), the hedge leg unmoved by the stock's cost, and evaluate's 0 bps row = the same run through stat_of"""
    mp = mp_world()
    W, ctx = mp.W, mp.ctx
    B, S12 = M17.synth_book(seed=3, hi="2026-06-30")
    rowsB = A13.book_rows(B, W)
    rb = mk_ref(B)
    with spec(win=30, min_pairs=25):
        es = {c: entry_set(W, ctx, KS[c]) for c in CELLS}
        res, obj = evaluate(W, ctx, B, S12, rb, rowsB, "registered", 0, 0, full=True, es=es)
        for rule in EXITS:
            for cell in CELLS:
                tr = trade_set(W, ctx, es[cell], rule, "registered", WF0, PRE_END)
                bu = prepare(W, tr)
                assert tr.n > 10
                nets = {}
                for bps in (0.0, 5.0, 10.0, 20.0):
                    run = run_bundle(W, bu, bps)
                    want = sum(brute_trade(W, int(tr.col[i]), int(tr.e[i]), int(tr.x[i]), bool(tr.naive[i]), bps)[1] for i in range(tr.n))
                    assert abs(float(run.x_unhedged.sum()) - want) < 1e-6, (rule, cell, bps)
                    nets[bps] = float(run.x.sum())
                    assert usd(run.hedge_agg, run_bundle(W, bu, 0.0).hedge_agg) and usd(run.hedge_exact, run_bundle(W, bu, 0.0).hedge_exact), "the stock's cost does not touch the hedge leg"
                unit = SPEC["slot"] * 1e-4 * (tr.n + float(bu.pa.ve.sum()))
                for bps in (5.0, 10.0, 20.0):
                    assert abs(nets[0.0] - nets[bps] - bps * unit) < 1e-6, (rule, cell, bps)
                assert nets[0.0] > nets[5.0] > nets[10.0] > nets[20.0]
                c = res["cells"][rule][cell]
                st0, st5 = c["cost0"], c["base"]
                wf = np.asarray((W.days >= WF0) & (W.days <= PRE_END))
                assert abs(st0["net"] - float(run_bundle(W, bu, 0.0).x[wf].sum())) < 1e-6 and abs(st5["net"] - float(run_bundle(W, bu, 5.0).x[wf].sum())) < 1e-6
                assert abs(st0["net"] - st5["net"] - 5.0 * unit) < 1e-6 and st0["n_pos"] == st5["n_pos"] == tr.n and st0["years"] == st5["years"]
                assert abs(c["stress"]["10 bps"]["net"] - (st0["net"] - 10.0 * unit)) < 1e-6 and abs(c["stress"]["20 bps"]["net"] - (st0["net"] - 20.0 * unit)) < 1e-6
                want_st = stat_of(B, rowsB, run_bundle(W, bu, 0.0), WF0, PRE_END)[0]
                assert all(st0[kk] == want_st[kk] or (isinstance(want_st[kk], float) and math.isnan(want_st[kk]) and math.isnan(st0[kk])) for kk in ("net", "roc", "sortino", "max_dd", "n_pos", "years_pos")) and st0["by_year"] == want_st["by_year"]
    return True


def t_diag():
    """[X2] the diagnostics, every cell under every exit rule side by side: the stock leg and the hedge leg apart (they add up to the cell; the hedge leg is its gross and its MES costs), the July-June years (net $ and trades by exit year add up to the
    stretch), the regime halves, a row per drawdown episode of the REFERENCE book with the cell's P&L inside it, the #70 gate's basis (DO against the reference's days and the null's), and the printed table - six columns, the right number in the right
    column, against a recount"""
    mp = mp_world()
    W, ctx = mp.W, mp.ctx
    B, S12 = M17.synth_book(seed=3, hi="2026-06-30")
    rowsB = A13.book_rows(B, W)
    rb = mk_ref(B)
    wf = np.asarray((W.days >= WF0) & (W.days <= PRE_END))
    with spec(win=30, min_pairs=25), patched(THIS, A2_WIN=(TS("2024-06-03"), TS("2025-03-31"))):                 # A2's window moved onto the hand-made world's own year: c exists
        res, obj = evaluate(W, ctx, B, S12, rb, rowsB, "registered", 40, 0, full=True)
        rep, _cands = reports(W, ctx, B, S12, rb, rowsB, obj.objs, res["cells"], None, {}, [])
        cells = res["cells"]
        for rule in EXITS:
            for cell in CELLS:
                c, o = cells[rule][cell], obj.objs[(rule, cell)]
                assert abs(c["unhedged"]["net"] + c["hedge_leg"]["net"] - c["base"]["net"]) < 1e-6 and abs(c["hedge_leg"]["net"] - float(o.run.hedge_agg[wf].sum())) < 1e-6 and abs(c["unhedged"]["net"] - float(o.run.x_unhedged[wf].sum())) < 1e-6
                assert abs(c["hedge_gross"] + c["hedge_costs"] - c["hedge_leg"]["net"]) < 1e-6 and c["hedge_costs"] < 0.0 and abs(c["hedge_gross"] - float(o.bu.hg.pnl[wf].sum())) < 1e-6 and abs(c["hedge_costs"] - float(o.bu.hg.cost[wf].sum())) < 1e-6
                assert abs(sum(c["base"]["by_year"].values()) - c["base"]["net"]) < 1e-6 and sum(rep["trades_by_year"][rule][cell].values()) == o.tr.n and set(rep["trades_by_year"][rule][cell]) == set(YEARS)
                ty = jyear(np.asarray(W.days)[o.tr.x])
                assert all(rep["trades_by_year"][rule][cell][y] == int((ty == y).sum()) for y in YEARS)
                assert sum(v["n_pos"] for v in c["sub"].values()) == o.tr.n and abs(sum(v["net"] for v in c["sub"].values()) - c["base"]["net"]) < 1e-6
                eps = rep["ref_episodes"][rule][cell]
                assert len(eps) == len(rb.S.qual) and [e["first_dd_day"] for e in eps] == [e["first_dd_day"] for e in rep["ref_episodes"]["X"]["R10"]], "the episodes are the reference's, the same rows in every column"
                inside = float(o.xB[rb.S.rows][rb.S.dd].sum())
                assert abs(sum(e["cell_pnl"] for e in eps) - inside) < 1e-6 and abs(c["seat_ref"]["DO"] - inside / rb.S.dd_loss) < 1e-9
                g = c["gate70"]
                assert g["DO"] == c["seat_ref"]["DO"] and g["episodes"] == rb.structure["episodes"] and g["dd_days"] == rb.structure["days"] and g["rho_dd"] == c["seat_ref"]["rho_dd"]
                if rule in NULL_EXITS:
                    p = res["null"][rule]["do_ref_max"]
                    assert g["null_do_p5"] == p["p5"] and g["null_do_p50"] == p["p50"] and g["null_do_p95"] == p["p95"] and g["DO_above_null_p95"] is bool(g["DO"] > p["p95"]) and p["finite"] >= 30
                    assert set(res["null"][rule]["do_ref_by_cell"]) == set(CELLS) and res["null"][rule]["random_names"]["do_ref_max"]["finite"] >= 30
                else:
                    assert "null_do_p95" not in g and "DO_above_null_p95" not in g
        # the printed table: header, the section titles, six columns in the order X R10, X R20, NO-X R10, NO-X R20, P+10 R10, P+10 R20, the right number in the right column
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            print_diagnostics(res, rep, rb)
        txt = buf.getvalue()
        lines = txt.splitlines()
        assert lines[0].startswith("DIAGNOSTICS [X2]") and "none of this is a pass route" in lines[0]
        head = lines[1].split()
        assert head == ["X-rule", "R10", "X-rule", "R20", "NO-X", "R10", "NO-X", "R20", "P+10", "R10", "P+10", "R20"], head
        for frag in ("COST CURVE", "BY JULY-JUNE YEAR", "THE TWO REGIME HALVES", "THE REFERENCE BOOK'S DRAWDOWN EPISODES", "THE STOCK LEG AND THE ES HEDGE LEG APART", "#70 GATE BASIS", "all the episodes", "stock + hedge = the cell as traded"):
            assert frag in txt, frag
        cols = [(r, c) for r in EXITS for c in CELLS]

        def row_with(label):
            hits = [ln for ln in lines if ln.strip().startswith(label)]
            assert len(hits) == 1, (label, hits)
            return hits[0]
        nr = lambda s: f"{s['net']:+,.0f} / {s['roc']:.1f}"
        for lab, get in (("0 bps", lambda c: c["cost0"]), ("5 bps (the base)", lambda c: c["base"]), ("10 bps", lambda c: c["stress"]["10 bps"]), ("20 bps", lambda c: c["stress"]["20 bps"])):
            ln = row_with(lab)
            want = "".join(f"{nr(get(cells[r][c])):>{DIAG_CW}}" for r, c in cols)
            assert ln.endswith(want), (lab, ln, want)
        for y in YEARS:
            ln = row_with(f"{y}-{(y + 1) % 100:02d}")
            want = "".join(f"{cells[r][c]['base']['by_year'][y]:+,.0f} ({rep['trades_by_year'][r][c][y]})".rjust(DIAG_CW) for r, c in cols)
            assert ln.endswith(want), (y, ln, want)
        for lab, _a, _b in SUBPERIODS:
            ln = row_with(lab)
            assert ln.endswith("".join(nr(cells[r][c]["sub"][lab]).rjust(DIAG_CW) for r, c in cols)), (lab, ln)
            nxt = lines[lines.index(ln) + 1]
            assert nxt.strip().startswith("trades") and nxt.endswith("".join(f"{cells[r][c]['sub'][lab]['n_pos']:,}".rjust(DIAG_CW) for r, c in cols)), (lab, nxt)
        n_ep = len(rep["ref_episodes"]["X"]["R10"])
        ep_lines = [ln for ln in lines if re.match(r"\s+\d{4}-\d\d-\d\d \.\. \d{4}-\d\d-\d\d \$", ln)]
        assert len(ep_lines) == n_ep == len(rb.S.qual)
        for q, ln in enumerate(ep_lines):
            want = "".join(f"{rep['ref_episodes'][r][c][q]['cell_pnl']:+,.0f}".rjust(DIAG_CW) for r, c in cols)
            assert ln.endswith(want) and rep["ref_episodes"]["X"]["R10"][q]["first_dd_day"] in ln, (q, ln, want)
        ln = row_with("all the episodes")
        assert ln.endswith("".join(f"{sum(e['cell_pnl'] for e in rep['ref_episodes'][r][c]):+,.0f}".rjust(DIAG_CW) for r, c in cols))
        for lab, get in (("stock leg alone", lambda c: nr(c["unhedged"])), ("ES hedge leg alone", lambda c: f"{c['hedge_leg']['net']:+,.0f}"), ("its gross P&L / its MES costs", lambda c: f"{c['hedge_gross']:+,.0f} / {c['hedge_costs']:+,.0f}"),
                         ("the exact fractional hedge", lambda c: f"{c['hedge_gap']['hedge_exact_net']:+,.0f}"), ("stock + hedge", lambda c: nr(c["base"]))):
            ln = row_with(lab)
            assert ln.endswith("".join(get(cells[r][c]).rjust(DIAG_CW) for r, c in cols)), (lab, ln)
        ln = row_with("DO (cell P&L over the DD days")
        assert ln.endswith("".join(f"{cells[r][c]['gate70']['DO']:+.3f}".rjust(DIAG_CW) for r, c in cols))
        ln = row_with("the null's DO p95")
        assert ln.endswith("".join((f"{cells[r][c]['gate70']['null_do_p95']:+.3f}" if r in NULL_EXITS else "-").rjust(DIAG_CW) for r, c in cols))
        ln = row_with("the cell's DO above the null's p95")
        assert ln.endswith("".join((("yes" if cells[r][c]["gate70"]["DO_above_null_p95"] else "no") if r in NULL_EXITS else "-").rjust(DIAG_CW) for r, c in cols))
        # print_cells carries the incremental A2 and the gate line for every (rule, cell)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            print_cells(res)
        pc = buf.getvalue()
        n_c = sum(1 for r in EXITS for c in CELLS if cells[r][c]["A2"]["at_half_c"])
        assert n_c == 6 and pc.count("A2 (a report) [X1]:") == 6 and pc.count("#70 gate basis [X1]") == 6 and pc.count("REFERENCE + c x cell ROC@30k") == n_c and pc.count("the plain #463 + c x cell book (a reported row)") == n_c
        assert pc.count("INCREMENTAL PASS (both above)") + pc.count("no incremental pass (it needs both above)") == 6 and pc.count("INCREMENTAL PASS (both above)") == sum(1 for r in EXITS for c in CELLS if cells[r][c]["A2"]["incremental_pass"])
        for r in EXITS:
            for c in CELLS:
                a2 = cells[r][c]["A2"]
                assert a2["window"] == ["2024-06-03", "2025-03-31"] and math.isfinite(a2["c"]) and a2["c"] > 0.0 and math.isfinite(a2["roc"]) and a2["reference"]["roc"] == rb.stats["roc"], (r, c)
                assert f"c x{a2['c']:.4g}" in pc and f"{a2['roc']:.2f} Sortino {a2['sortino']:.3f} against the reference's {a2['reference']['roc']:.2f} / {a2['reference']['sortino']:.3f}" in pc, (r, c)
        assert pc.count("-> the cell's DO is") == 4 and pc.count("(no registered null for this rule)") == 2
    return True


def t_path_x():
    """[X2] the draft's X-axis variant of the event-time path (X - 25 .. X + 5, the hedged cost-free mean return, by July-June year of X) against a plain-python recount, on planted run-ups: with the +80 bps planted on the 5 sessions before the PREDICTED
    ex-date P of every event, every kind-0 trade sees exactly +400 bps inside its window - and WHERE it sits relative to X depends on the ex-date (A: X = P, so X - 5 .. X - 1; C's X = P + 5, X - 10 .. X - 6; C's X = P - 5, X .. X + 4); the late-X trades
    are not in it; on a world where X = P for everyone the X axis and the P axis agree session for session before X; an ES-hole session contributes nothing"""
    taus = list(range(-25, 6))
    ix = taus.index

    def recount(Wx, tr):
        sums, ns = defaultdict(float), defaultdict(int)
        by = defaultdict(lambda: (defaultdict(float), defaultdict(int)))
        pre, l2, post, tot = [], [], [], []
        for i in np.flatnonzero(tr.kind == 0):
            xr, j, b = int(tr.xr[i]), int(tr.col[i]), float(tr.beta[i])
            assert xr == int(tr.x[i]) + 1, "kind 0: the exit is the close before X"
            yr = int(Wx.days[xr].year) - (1 if Wx.days[xr].month < 7 else 0)
            path = {}
            for tau in taus:
                t = xr + tau
                if 0 <= t <= Wx.T - 1 and math.isfinite(Wx.Rd[t, j]) and math.isfinite(Wx.es.ret[t]):
                    v = float(Wx.Rd[t, j] - b * Wx.es.ret[t])
                    sums[tau] += v
                    ns[tau] += 1
                    by[yr][0][tau] += v
                    by[yr][1][tau] += 1
                    path[tau] = v
            pre.append(1e4 * sum(v for t_, v in path.items() if t_ <= -1))
            l2.append(1e4 * sum(v for t_, v in path.items() if t_ in (-2, -1)))
            post.append(1e4 * sum(v for t_, v in path.items() if t_ >= 0))
            tot.append(1e4 * sum(path.values()))
        return sums, ns, by, pre, l2, post, tot

    def agree(pth, Wx, tr):
        sums, ns, by, pre, l2, post, tot = recount(Wx, tr)
        for q, tau in enumerate(taus):
            want = 1e4 * sums[tau] / ns[tau] if ns[tau] else float("nan")
            assert pth.n[q] == ns[tau] and ((math.isnan(want) and math.isnan(pth.mean_bps[q])) or abs(pth.mean_bps[q] - want) < 1e-9), (tau, pth.mean_bps[q], want)
            assert abs(pth.cum_bps[q] - sum(1e4 * sums[t_] / ns[t_] for t_ in taus[:q + 1] if ns[t_])) < 1e-9
        assert abs(pth.total_mean_bps - np.mean(tot)) < 1e-9 and abs(pth.pre_mean_bps - np.mean(pre)) < 1e-9 and abs(pth.last2_mean_bps - np.mean(l2)) < 1e-9 and abs(pth.post_mean_bps - np.mean(post)) < 1e-9
        assert abs(pth.last2_share - np.mean(l2) / np.mean(pre)) < 1e-12 if np.mean(pre) != 0 else math.isnan(pth.last2_share)
        assert set(pth.by_year) == set(by), (set(pth.by_year), set(by))
        for yr, (sm, nn) in by.items():
            for q, tau in enumerate(taus):
                want = 1e4 * sm[tau] / nn[tau] if nn[tau] else float("nan")
                got = pth.by_year[yr]["mean_bps"][q]
                assert pth.by_year[yr]["n"][q] == nn[tau] and ((math.isnan(want) and math.isnan(got)) or abs(got - want) < 1e-9), (yr, tau, got, want)

    pw = pw_world(since="2024-01-01")
    W, ctx = pw.W, pw.ctx
    with spec(win=30, min_pairs=25):
        tr = trade_set(W, ctx, entry_set(W, ctx, 20), "X", "registered", W.days[0], W.days[-1])
    pth = event_path_x(W, tr)
    assert pth.axis == "X" and pth.taus.tolist() == taus and len(pth.mean_bps) == 31 and len(pth.n) == 31
    k0 = tr.kind == 0
    assert pth.trades == int(k0.sum()) > 50 and pth.late_or_missing_x_trades == int((~k0).sum()) >= 3
    agree(pth, W, tr)
    assert abs(pth.total_mean_bps - 400.0) < 1e-6, "every kind-0 trade sees the planted +80 bps x 5 sessions inside its window, wherever its ex-date is"
    assert pth.mean_bps[ix(-3)] > 0.0 and pth.mean_bps[ix(-8)] > 0.0 and pth.mean_bps[ix(2)] > 0.0, "A's run-up at X - 5 .. X - 1, C's late ex-date at X - 10 .. X - 6, C's early one at X .. X + 4"
    assert abs(pth.mean_bps[ix(-20)]) < 1e-6 and abs(pth.mean_bps[ix(-15)]) < 1e-6 and pth.pre_mean_bps < 400.0 - 1.0 and pth.post_mean_bps > 1.0 and abs(pth.pre_mean_bps + pth.post_mean_bps - 400.0) < 1e-6
    assert pth.n[ix(5)] > 0 and pth.n[ix(-25)] > 0
    # a world where X = P for everyone (A names only): the planted run-up at X - 5 .. X - 1 of the events with P on / after 2025-07-01 and nothing else - and the P axis, session for session before X
    pa = pw_world(n_a=12, n_b=0, n_c=0)
    with spec(win=30, min_pairs=25):
        tra = trade_set(pa.W, pa.ctx, entry_set(pa.W, pa.ctx, 20), "X", "registered", pa.W.days[0], pa.W.days[-1])
    px, pp = event_path_x(pa.W, tra), event_path(pa.W, tra)
    agree(px, pa.W, tra)
    assert px.trades == pp.trades > 30 and px.late_or_missing_x_trades == 0
    for yr in (2025, 2026):
        m = px.by_year[yr]["mean_bps"]
        for q, tau in enumerate(taus):
            if -5 <= tau <= -1:
                assert px.by_year[yr]["n"][q] > 0 and abs(m[q] - 80.0) < 1e-6, (yr, tau, m[q])
            else:
                assert not np.isfinite(m[q]) or abs(m[q]) < 1e-6, (yr, tau, m[q])
    assert all((not np.isfinite(v)) or abs(v) < 1e-6 for v in px.by_year[2024]["mean_bps"]), "no run-up was planted in July-June 2024"
    for tau in range(-20, 0):
        a_, b_ = px.mean_bps[ix(tau)], pp.mean_bps[list(pp.taus).index(tau)]
        assert (np.isnan(a_) and np.isnan(b_)) or abs(a_ - b_) < 1e-9, (tau, a_, b_)
    npl = sum(1 for i in np.flatnonzero(tra.kind == 0) if TS(pa.W.days[int(tra.xr[i])]) >= TS("2025-07-01"))
    assert npl > 5 and abs(px.pre_mean_bps - 400.0 * npl / px.trades) < 1e-6 and abs(px.last2_mean_bps - 160.0 * npl / px.trades) < 1e-6 and abs(px.last2_share - 0.4) < 1e-9 and abs(px.post_mean_bps) < 1e-6 and abs(px.total_mean_bps - px.pre_mean_bps) < 1e-6
    # an ES-hole session contributes nothing, a session past the data none
    W2 = SimpleNamespace(**{**W.__dict__})
    W2.es = SimpleNamespace(**{**W.es.__dict__})
    ret2 = np.array(W.es.ret, float)
    i0 = int(np.flatnonzero(k0)[0])
    ret2[int(tr.xr[i0]) - 3] = np.nan
    W2.es.ret = ret2
    pth2 = event_path_x(W2, tr)
    agree(pth2, W2, tr)
    assert pth2.n[ix(-3)] < pth.n[ix(-3)]
    late = int(tr.xr[k0].max()) + 5 > W.T - 1
    assert (not late) or pth.n[ix(5)] < pth.n[ix(-5)], "events whose X + 5 is past the data have no value there"
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        print_path_x(pth)
    txt = buf.getvalue()
    assert "EVENT-TIME PATH [X2]" in txt and "X - 25 .. X + 5" in txt and "tau" in txt and "2025-26" in txt and "ex-day tax trade" in txt and f"{pth.trades:,} events" in txt and "by July-June year of X" in txt
    return True


# ------------------------------------------------------------------ smoke: the synthetic worlds (a planted run-up and a null one) behind r5_siporb's fake transport, a fake ES master, a fake #463 and a fake wide calendar
def smoke_refusal(root):
    """r17_resmom's guards (the dir is wiped: a 'smoke' name, never OUT / CACHE / the repo / this harness / the working directory / C:\\EdgeLog, ATTN's / DDW's / RESMOM's OUT, the #463 records) + this harness's OUT"""
    why = M17.smoke_refusal(root)
    if why:
        return why
    real = lambda p: os.path.normcase(os.path.realpath(p))
    try:
        if os.path.commonpath([real(root), real(OUT)]) == real(root):
            return f"smoke refused: {root} is or holds DIVRUN OUT"
    except ValueError:
        pass
    return None


SMOKE_BUMP = 0.04                  # the planted run-up: +4% over the 19 sessions before every regular ex-date, taken back ON it (the effect the planted world carries and the null world does not)
SMOKE_Q = 91                       # the synthetic payers' cycle, calendar days


def smoke_calendar(days, seed=17):
    """the synthetic calendar of the smoke world: (div, spin, split) = (symbol, ex date 'YYYY-MM-DD', amount, special), (symbol, ex, type), (symbol, ex, type, old:new rate). Quarterly payers (the S01-S34 names but the four below, the names that carry the hygiene
    plants, and D01-D40) on a 91-day cycle with a random phase (a Monday) and an ex-date that now and then moves a week (so X is not always P); S05 / S06 monthly and S07 / S08 semi-annual (the cycle test must refuse them); special dividends a week before some
    regular ex-dates (inside the holds of the events before them); spin-offs / stock dividends two weeks before some; and the planted hygiene cases on a 91-day cycle through their date: SPL's split on 2024-03-15 inside its hold, S18's missed split
    (2024-04-22), S23's genuine +60% gap (2024-05-14), DLST's last bar (2024-05-31)"""
    rng = np.random.default_rng(seed)
    d0, d1 = pd.Timestamp("2016-06-06"), pd.Timestamp("2026-06-30")
    fmt = lambda t: f"{t:%Y-%m-%d}"
    names = [f"S{k:02d}" for k in range(1, 35)] + ["SPL", "DLST"] + [f"D{k:02d}" for k in range(1, 41)]
    special_cycle = {"SPL": pd.Timestamp("2024-03-25"), "S18": pd.Timestamp("2024-05-02"), "S23": pd.Timestamp("2024-05-23"), "DLST": pd.Timestamp("2024-06-13")}      # the predicted ex-date P of one event of each
    div, spin, split, quarterly = [], [], [(("SPL", "2024-03-15", "forward_split", (2, 1)))], []
    for nm in names:
        if nm in ("S05", "S06", "S07", "S08", "S09", "S10", "S11", "S12"):
            continue
        k = len(quarterly)
        if nm in special_cycle:
            dates = [special_cycle[nm] + pd.Timedelta(days=SMOKE_Q * m) for m in range(-40, 12)]
            dates = [t for t in dates if d0 <= t <= d1]
        else:
            t = d0 + pd.Timedelta(days=7 * int(rng.integers(0, 13)))
            dates = []
            while t <= d1:
                dates.append(t)
                t = t + pd.Timedelta(days=SMOKE_Q + 7 * int(rng.choice([-1, 0, 1], p=[0.1, 0.8, 0.1])))
        quarterly.append(nm)
        for t in dates:
            div.append((nm, fmt(t), round(0.4 + 0.012 * (k % 60) + 0.01 * float(rng.random()), 4), False))
        for t in dates[1:]:
            u = rng.random()
            if u < 0.025:
                div.append((nm, fmt(t - pd.Timedelta(days=7)), round(2.5 + float(rng.random()), 4), True))         # a special dividend a week before the regular ex-date
            elif u < 0.04:
                spin.append((nm, fmt(t - pd.Timedelta(days=14)), "spin_off" if rng.random() < 0.5 else "stock_dividend"))
    for nm, step in (("S05", 28), ("S06", 28), ("S07", 182), ("S08", 182)):                                    # monthly and semi-annual payers: out by the cycle test
        t = d0 + pd.Timedelta(days=3)
        while t <= d1:
            div.append((nm, fmt(t), 0.3, False))
            t = t + pd.Timedelta(days=step)
    div.append(("S11", "2020-03-02", 4.0, True))                                                               # a special dividend alone (no cycle)
    return div, spin, split, quarterly


def smoke_ca_text(div, spin, split):
    """r16_xgap's flat CSV (r17_resmom.CA_COLS) of the synthetic calendar plus the cases the loader counts and does not use: a name that is not on the grid, a zero amount, an undated row, a weekend ex-date of a non-payer, rows on / after the cut"""
    rows = [f"cash_dividend,{s},,,{d},{d},,,{a},,,,{sp}" for s, d, a, sp in div]
    rows += [f"{ty},{s},,{s}.W,{d},{d},,,,0.1,1,," if ty == "spin_off" else f"stock_dividend,{s},,,{d},{d},,,0.1,,,," for s, d, ty in spin]
    rows += [f"forward_split,{s},,,{d},{d},,,,{n},{o},," for s, d, ty, (n, o) in split]
    rows += ["cash_dividend,ZZZZ,,,2024-02-07,2024-02-07,,,0.9,,,,False", "cash_dividend,S09,,,2024-02-07,2024-02-07,,,0,,,,False", "cash_dividend,S10,,,,2024-02-08,,,0.5,,,,False", "cash_dividend,S12,,,2024-03-02,2024-03-02,,,0.4,,,,False",
             "cash_dividend,S09,,,2025-06-30,2025-06-30,,,0.5,,,,False", "cash_dividend,D01,,,2025-07-01,2025-07-01,,,0.5,,,,False", "spin_off,S08,,S08.W,2025-07-02,2025-07-02,,,,0.1,1,,"]
    return rows


class DivFake(S.Fake):
    """r5_siporb's fake Alpaca transport serving SYNTHETIC DAILY bars of 80 names on continuous business days (no minute bars: this family reads none): close-to-close log return = beta x the fake ES master's return + noise; a dividend of the calendar
    is taken off the OPEN of its ex-date (so the total return is the price return); `plant` > 0 puts a +plant ramp over the 19 sessions before every regular ex-date of every name and takes it back on the ex-date (the planted run-up); the same random numbers
    otherwise, so plant = 0 is the null world of the same market. The special names of S.Fake keep their plants (SPL's 2-for-1 on 2024-03-15, S18's missed x4 on 04-22, S23's +60% gap on 05-14, DLST's last bar on 05-31, S33 / S34's late starts, LOWP / LOWV /
    LOWA below the filters, RVS's reverse split). The 1Day request is served from rows built once per request key (S.daily pages one batch many times)"""
    def __init__(self, days, mkt, div, plant=0.0, page=2500):
        self.days, self.D, self.page, self.n, self.auth_fail, self._st, self._rowcache = [f"{d:%Y-%m-%d}" for d in days], len(days), page, 0, False, {}, {}
        rng = np.random.default_rng(11)
        self.names = names = [f"S{k:02d}" for k in range(1, 35)] + ["LOWP", "LOWV", "LOWA", "SPL", "RVS", "DLST"] + [f"D{k:02d}" for k in range(1, 41)]
        self.k, N, ix, dx = {n: k for k, n in enumerate(names)}, len(names), names.index, self.days.index
        D = self.D
        self.p0, self.vol = rng.uniform(150.0, 500.0, N), rng.uniform(1.5e6, 6e6, N)
        beta, idio = rng.uniform(0.5, 1.5, N), rng.uniform(0.009, 0.014, N)
        self.p0[ix("LOWP")], self.vol[ix("LOWV")], self.p0[ix("LOWA")], idio[ix("LOWA")], self.p0[ix("SPL")], self.p0[ix("RVS")] = 3.0, 3e5, 10.0, 0.0015, 400.0, 150.0
        self.vol[ix("SPL")] = 8e6                                                                 # the raw pre-split volume is half the adjusted one: keep SPL above the 1M-share floor before its split
        self.first, self.last = np.zeros(N, int), np.full(N, D - 1)
        self.first[ix("S33")], self.first[ix("S34")], self.last[ix("DLST")] = dx("2016-02-01"), dx("2024-02-01"), dx("2024-05-31")
        self.gday = {ix("SPL"): (dx("2024-03-15"), 2.0), ix("RVS"): (dx("2016-02-17"), 0.2)}
        self.msp = {ix(self.MSPLIT[0]): (dx(self.MSPLIT[1]), self.MSPLIT[2])}
        self.jump = {ix(self.GAP[0]): (dx(self.GAP[1]), self.GAP[2])}
        eps = rng.standard_normal((D, N)) * idio
        gap = rng.standard_normal((D, N)) * 0.003
        w1, w2 = np.abs(rng.standard_normal((D, N))) * 0.004, np.abs(rng.standard_normal((D, N))) * 0.004
        vn = rng.lognormal(0.0, 0.25, (D, N))
        r = beta * np.asarray(mkt, float)[:, None] + eps
        for k, (d, f) in self.jump.items():
            r[d, k] += math.log(f)
            gap[d, k] += math.log(f)
        divamt = np.zeros((D, N))
        dayidx = pd.DatetimeIndex(days)
        for sym, ex, amt, special in div:
            if sym in self.k:
                t = dayidx.searchsorted(pd.Timestamp(ex))
                if t < D and dayidx[t] == pd.Timestamp(ex):
                    divamt[t, self.k[sym]] += amt
                if plant and not special and 20 <= t < D and dayidx[t] == pd.Timestamp(ex):
                    step = math.log(1.0 + plant) / 19.0
                    r[t - 19:t, self.k[sym]] += step
                    r[t, self.k[sym]] -= 19.0 * step
        self.daily, self.f5, self.opx = np.full((N, D, 5), np.nan), np.full((N, D, 5), np.nan), np.full((N, D), np.nan)
        prev = self.p0.copy()
        for d in range(D):
            o = (prev - divamt[d]) * np.exp(gap[d])
            c = o * np.exp(r[d] - gap[d])
            live = (d >= self.first) & (d <= self.last)
            h, lo = np.maximum(o, c) * (1.0 + w1[d]), np.minimum(o, c) * (1.0 - w2[d])
            v = np.round(self.vol * vn[d]) + 1
            for q, a in enumerate((o, h, lo, c, v)):
                self.daily[:, d, q] = np.where(live, a, np.nan)
            prev = np.where(live, c, prev)
        self._valid = [np.flatnonzero(~np.isnan(self.daily[k, :, 0])) for k in range(N)]
        self._ts = [pd.Timestamp(d, tz="US/Eastern").tz_convert("UTC").strftime("%Y-%m-%dT%H:%M:%SZ") for d in self.days]

    def assets(self, p):
        return [a for a in super().assets(p) if a["symbol"] != "ZZBAD"]                          # the symbol the endpoint rejects (S.Fake's bisect plant) is not needed here: one batch, no bisection

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


def smoke_market(days):
    """the synthetic ES master (r15_ddw.ESFake on the stock sessions plus a warm-up) and its daily return on the stock sessions - the roll-corrected change of the 16:00 print over the unadjusted prior print, exactly the harness's market factor
    (0 where the master has no print): the factor the synthetic stocks load on -> (esf, mkt)"""
    es_cal = days.union(pd.bdate_range("2015-05-01", "2015-10-30"))
    esf = D15.ESFake(es_cal)
    pc = np.array([esf.p_close[d] for d in days], float)
    rc = np.array([esf.raw_close[d] for d in days], float)
    mkt = np.zeros(len(days))
    with np.errstate(invalid="ignore"):
        mkt[1:] = (pc[1:] - pc[:-1]) / rc[:-1]
    return esf, np.nan_to_num(mkt, nan=0.0)


@contextlib.contextmanager
def smoke_env(root, nrep=100, build=("plant", "null")):
    """everything the smoke patches, restored on exit: OUT and every module's output folder into `root`, CHECK_BOOK off, NREP = nrep, the wide calendar's pinned sha = the synthetic file's, r5_siporb's transport = DivFake (one cache per world), the ES
    registry = the fake master, the TBIS file, a fake #463. Builds the worlds in `build` ('plant' = the run-up, 'null' = none) through r5_siporb's own pulls. Yields a namespace: root, days, esf, div, spin, split, quarterly, fk {world: DivFake}, cache {world:
    folder}, switch(world) (points S.CACHE at it), wide_sha, wide_csv, wide_manifest"""
    root = os.path.abspath(root)
    why = smoke_refusal(root)
    if why:
        raise SystemExit(why)
    data = A13.data_mod()
    keep = dict(S=(S.OUT, S.CACHE, S.BOOK, S.SMOKE, S.PACE, S.BACKOFF, S.RETRY, S._http_get), es=(data.find_master, data.load_master_arrays), tb=(D15.TBIS_CSV, A13.TBIS_QA), wide=M17.WIDE_CA_SHA, ref=(THIS.REF_CSV, THIS.REF_SHA))
    shutil.rmtree(root, ignore_errors=True)
    os.makedirs(root)
    with contextlib.ExitStack() as es:
        es.enter_context(patched(THIS, OUT=os.path.join(root, "out"), CHECK_BOOK=False, NREP=nrep))
        es.enter_context(patched(R11, OUT=os.path.join(root, "r11")))
        es.enter_context(patched(A13, OUT=os.path.join(root, "attn_out")))
        try:
            S.OUT, S.BOOK = os.path.join(root, "siporb_out"), os.path.join(root, "r4", "book463_daily.csv")
            tbis_path = os.path.join(root, "tbis.csv")
            D15.TBIS_CSV = A13.TBIS_QA = tbis_path
            S.SMOKE, S.PACE, S.BACKOFF, S.RETRY = True, 0.0, 0.0, 0.0
            for p in (OUT, R11.OUT, A13.OUT, S.OUT):
                os.makedirs(p)
            inside = lambda p: os.path.commonpath([os.path.realpath(p), os.path.realpath(root)]) == os.path.realpath(root)
            assert all(inside(p) for p in (OUT, R11.OUT, A13.OUT, S.OUT, tbis_path)), "every path the smoke writes is inside the smoke dir"
            days = pd.bdate_range("2015-11-02", "2025-09-30")                                  # continuous sessions: 10 years, so the WF stretch is whole and the cut (2025-06-30) has days to cut
            t0 = time.time()
            esf, mkt = smoke_market(days)
            div, spin, split, quarterly = smoke_calendar(days)
            ca_rows = smoke_ca_text(div, spin, split)
            env = SimpleNamespace(root=root, days=days, esf=esf, mkt=mkt, div=div, spin=spin, split=split, quarterly=quarterly, fk={}, cache={}, wide_files={}, ca_rows=ca_rows, rows_in_calendar=len(ca_rows))
            for world in build:
                fk = DivFake(days, mkt, div, plant=SMOKE_BUMP if world == "plant" else 0.0)
                env.fk[world] = fk
                env.cache[world] = os.path.join(root, f"cache_{world}")
                S.CACHE, S._http_get = env.cache[world], fk.handle
                with contextlib.redirect_stdout(io.StringIO()):
                    S.assets()
                    S.daily()
                xd = os.path.join(env.cache[world], "xgap")
                os.makedirs(xd, exist_ok=True)
                with open(os.path.join(xd, M17.WIDE_NAME + ".csv"), "w", newline="\n") as f:
                    f.write("\n".join([",".join(M17.CA_COLS)] + ca_rows) + "\n")
                csv_p, man_p = os.path.join(xd, M17.WIDE_NAME + ".csv"), os.path.join(xd, M17.WIDE_NAME + "_manifest.json")
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
            env.ref_sha = write_ref_csv(env.ref_csv, b0, env.ref_res)
            assert inside(env.ref_csv), "the stub is inside the smoke dir"
            THIS.REF_CSV, THIS.REF_SHA = env.ref_csv, env.ref_sha
            with open(os.path.join(S.OUT, "siporb_cache_manifest.json"), "w") as f:
                json.dump({"manifest_sha256": D15.MANIFEST_PREFIX + "0" * 56, "files": 0}, f)
            with open(tbis_path, "w") as f:
                f.write("symbol,day,price_ratio,vol_ratio,split_like\nS18,2024-04-22,4.0,0.25,True\nSPL,2024-03-15,0.5,2.1,True\nS05,2024-02-13,0.5,1.0,False\nZZZZ,2024-02-14,0.5,2.0,True\nS07,2025-07-01,0.5,2.0,True\n")

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
            THIS.REF_CSV, THIS.REF_SHA = keep["ref"]


# ------------------------------------------------------------------ smoke: the world the loaders build, checked against plain-python recounts of everything this file adds
def smoke_world(env, world):
    """the World a stage reads, built through the REAL loaders with the calls stage_a makes (every input cut at 2025-06-30 at read time): (W, cal, winfo, tbis); the raw dividend / spin-off inputs are placed again by plain python from the csv
    rows (W.Dr_in / W.Sp_in) for the recounts"""
    env.switch(world)
    with quiet():
        D = M17.load_data(S.LB0)
    tbis = D15.load_tbis(S.LB0)
    es_frames, _meta = D15.load_es(S.LB0)
    with quiet():
        cal, winfo = M17.wide_load(S.LB0)
        W = M17.build_world(D, S.LB0, es_frames, tbis, cal)
    D15.release(D)
    cut_checks(W, cal, S.LB0)
    csv_path = M17.wide_paths()["csv"]
    W.Dr_in = M17.brute_div_matrix(csv_path, W.days, W.syms, S.LB0)
    W.Sp_in = M17.brute_spin_matrix(csv_path, W.days, W.syms, S.LB0)
    return W, cal, winfo, tbis


def usd(a, b, tol=1e-7):
    """two dollar series equal to the cent and far below it: relative tol, absolute 1e-7 (a running sum of positions that nets to zero leaves ~1e-16 of a contract behind, worth ~1e-12 dollars on a move)"""
    return bool(np.allclose(np.asarray(a, float), np.asarray(b, float), rtol=tol, atol=1e-7, equal_nan=True))


def brute_hyg_rows(W, cal, j):
    """plain python: (the rows where name j has any of DDW r1's four reasons, the rows with a special cash dividend or a spin-off / stock-dividend ex-date of it) - memoised per name"""
    memo = cal.__dict__.setdefault("_hyg_memo", {})
    if (id(W), j) not in memo:
        four = {t for t in range(W.T) if any(bool(W.fl[q][t, j]) for q in range(4))}
        sess = {pd.Timestamp(d): i for i, d in enumerate(W.days)}
        extra = {t for t in range(W.T) if bool(W.SPN[t, j])}
        for sym, ex, sp in zip(cal.div["symbol"], cal.div["ex"], cal.div["special"]):
            if sym == W.syms[j] and bool(sp) and pd.Timestamp(ex) in sess:
                extra.add(sess[pd.Timestamp(ex)])
        memo[(id(W), j)] = (four, extra)
    return memo[(id(W), j)]


def brute_tradeset(W, cal, kept, rule, reading, lo, hi):
    """plain python: the trades of one (cell, exit rule, reading) from the brute entry set: the exit of the rule inside the data and on a date in [lo, hi]; no ES print at the entry or the exit -> out; a reason in the 5 sessions before the entry
    through the entry -> out (both readings); a reason inside the hold (e + 1 .. x) or a special dividend / spin-off in it -> out for 'registered', kept at the naive raw price path for 'naive'"""
    out = []
    for t in kept:
        x, kind, res = brute_exit(t, rule, W.T)
        if not res or not (lo <= W.days[x] <= hi):
            continue
        j, e = t["col"], t["e"]
        four, extra = brute_hyg_rows(W, cal, j)
        if not all(math.isfinite(v) for v in (W.esR[e], W.esA[e], W.esR[x], W.esA[x])):
            continue
        if any(max(e - SPEC["hyg_lead"], 0) <= r <= e for r in four):
            continue
        hold = any(e + 1 <= r <= x for r in four) or any(e + 1 <= r <= x for r in extra)
        if hold and reading == "registered":
            continue
        out.append({"col": j, "sym": t["sym"], "e": e, "x": x, "kind": kind, "naive": bool(hold and reading == "naive"), "beta": t["beta"], "p": t["p"]})
    out.sort(key=lambda d: (d["e"], d["col"]))
    return out


def smoke_recount(W, cal):
    """everything this file adds, on the world the loaders built, against plain-python recounts: the events (cycle test, P, X) of every regular ex-date; both entry sets (every first reason by entry year, the kept events with their betas); every
    (cell, exit rule, reading) trade set (exits, hygiene removal / naive keeping, the stretch); the per-trade P&L (dividend credit, ex-day drop, costs, stopped printing), the daily stock series, the aggregate whole-MES hedge, the exact hedge; the placebo's windows and
    the random-name pool on samples -> (ctx, counts)"""
    t0 = time.time()
    Eb = np.array([[M17.brute_div_amt(W, t, j) for j in range(W.S)] for t in range(W.T)])
    assert np.allclose(W.Dv1, Eb, rtol=1e-12, atol=1e-15) and (W.SPN == W.Sp_in).all() and int((Eb > 0).sum()) > 2000, "the loaders' dividend / spin-off arrays equal the plain-python placement of the csv rows"
    ctx = make_ctx(W, cal)
    ev = ctx.ev
    evs = brute_events(cal.div, W.days, W.syms)
    assert ev.n == len(evs) > 2000
    for i, b in enumerate(evs):
        assert (str(ev.sym[i]), int(ev.col[i]), TS(ev.e1[i]), bool(ev.cyc[i]), int(ev.p_row[i]), int(ev.x_row[i]), int(ev.e1_row[i])) == (b["sym"], b["col"], b["e1"], b["cyc"], b["p_row"], b["x_row"], b["e1_row"]), (i, b)
        assert (pd.isna(ev.p_date[i]) and b["p_date"] is None) or TS(ev.p_date[i]) == b["p_date"]
        assert (pd.isna(ev.x_date[i]) and b["x_date"] is None) or TS(ev.x_date[i]) == b["x_date"]
        assert abs(ev.amt1[i] - b["amt1"]) < 1e-12
    n = {"events": ev.n, "cycle_ok": int(ev.cyc.sum())}
    es, kept = {}, {}
    for K in (10, 20):
        es[K] = entry_set(W, ctx, K)
        kept[K], reasons = brute_entry(W, evs, K)
        assert es[K].n == len(kept[K]) and [(str(ctx.ev.sym[i]), int(e_), int(p_), int(x_)) for i, e_, p_, x_ in zip(es[K].idx, es[K].e, es[K].p, es[K].xr)] == [(k["sym"], k["e"], k["p"], k["xr"]) for k in kept[K]], K
        assert close(es[K].beta, [k["beta"] for k in kept[K]], 1e-8) and es[K].e1r.tolist() == [k["e1_row"] for k in kept[K]]
        assert {y: dict(c) for y, c in es[K].cnt.items()} == {y: dict(c) for y, c in reasons.items()}, (K, dict(es[K].cnt), dict(reasons))
        n[f"entry_set_R{K}"] = es[K].n
    combos = 0
    for K in (10, 20):
        for rule in EXITS:
            for reading in ("registered", "naive"):
                tr = trade_set(W, ctx, es[K], rule, reading, WF0, PRE_END)
                bt = brute_tradeset(W, cal, kept[K], rule, reading, WF0, PRE_END)
                assert [(str(W.syms[c]), int(e_), int(x_), int(k_), bool(nv)) for c, e_, x_, k_, nv in zip(tr.col, tr.e, tr.x, tr.kind, tr.naive)] == [(d["sym"], d["e"], d["x"], d["kind"], d["naive"]) for d in bt], (K, rule, reading)
                assert close(tr.beta, [d["beta"] for d in bt], 1e-8)
                combos += 1
    n["trade_sets_recounted"] = combos
    paths = 0
    for rule, K, reading in (("X", 10, "registered"), ("NOX", 20, "registered"), ("P10", 20, "registered"), ("NOX", 10, "naive"), ("X", 20, "naive")):
        tr = trade_set(W, ctx, es[K], rule, reading, WF0, PRE_END)
        bu = prepare(W, tr)
        run = run_bundle(W, bu)
        bt = brute_tradeset(W, cal, kept[K], rule, reading, WF0, PRE_END)
        tot, cash, day = [], [], defaultdict(float)
        for d in bt:
            dd, tt, cs = brute_trade(W, d["col"], d["e"], d["x"], d["naive"], COST_BPS)
            tot.append(tt)
            cash.append(cs)
            for r_, v_ in dd.items():
                day[r_] += v_
        sd = np.array([day.get(t, 0.0) for t in range(W.T)])
        assert usd(run.pos.stock, tot) and usd(run.div_usd, cash) and usd(stock_pnl(W, tr, bu.pa, COST_BPS)[0], sd), (rule, K, reading)
        n_, pnl_, cost_, per_, dayh = brute_hedge(W, [(d["e"], d["x"], d["beta"]) for d in bt])
        assert close(bu.hg.n, n_) and usd(bu.hg.pnl, pnl_) and usd(bu.hg.cost, cost_) and usd(bu.hx.pnl, per_) and usd(bu.hx.daily, [dayh.get(t, 0.0) for t in range(W.T)]), (rule, K, reading, "hedge")
        assert usd(run.x, sd + bu.hg.pnl + bu.hg.cost) and np.abs(bu.hg.n).max() >= 1, (rule, K, reading, "the hedge holds contracts")
        paths += len(bt)
    n["trade_paths_recounted"] = paths
    n["max_contracts"] = int(max(np.abs(prepare(W, trade_set(W, ctx, es[20], "P10", "registered", WF0, PRE_END)).hg.n).max(), 0))
    # DLST stopped printing inside its hold: it exits at its last mark
    dl = list(W.syms).index("DLST")
    tr = trade_set(W, ctx, es[10], "NOX", "registered", WF0, PRE_END)
    pa = stock_paths(W, tr)
    si = np.flatnonzero(pa.stopped)
    last = int(np.flatnonzero(np.isfinite(W.Cl[:, dl]))[-1])
    assert len(si) == 1 and int(tr.col[si[0]]) == dl and abs(pa.ve[si[0]] - W.Ac[last, dl] / W.Ac[tr.e[si[0]], dl]) < 1e-12, "DLST's hold runs past its last bar: stopped printing, exits at its last mark"
    # the placebo's windows on the loaders' world: sampled (trade, draw) pairs against the plain-python window test
    trp = trade_set(W, ctx, es[20], "NOX", "registered", WF0, PRE_END)
    hp = trp.x - trp.e
    Ep = placebo_entries(W, ctx, np.random.default_rng(1), trp, 40)
    rng = np.random.default_rng(2)
    ii, dd_ = np.nonzero(Ep >= 0)
    pick = rng.choice(len(ii), 400, replace=False)
    for q in pick:
        i, d = int(ii[q]), int(dd_[q])
        assert trp.e1r[i] + SPEC["pl_lo"] <= Ep[i, d] <= trp.p[i] - SPEC["pl_margin"] - hp[i] and brute_clean(W, cal, int(trp.col[i]), int(Ep[i, d]), int(hp[i])), (i, d, Ep[i, d])
    n["placebo_windows_checked"] = len(pick)
    n["placebo_left_out_share"] = float((Ep < 0).mean())
    flat, off, cnt = random_name_pool(W, ctx, trp)
    for i in np.random.default_rng(3).choice(trp.n, 25, replace=False):
        assert sorted(flat[off[i]:off[i] + cnt[i]].tolist()) == brute_pool(W, cal, evs, int(trp.e[i]), int(trp.x[i])), int(i)
    n["random_name_pools_checked"] = 25
    n["seconds"] = round(time.time() - t0)
    return ctx, n


def dryload_text_checks(txt):
    """the dryload's printout is COUNTS: no price, return, P&L or statistic (nothing like a dollar amount, ROC, Sortino, P&L), no date on / after the cut but the one line that names the cut, the count lines it promises"""
    outcome = re.search(r"[$]\s*-?\d|ROC|Sortino|P&L|net [$]|drawdown|Stage A \(", txt)
    assert not outcome, ("the dryload printed an outcome", txt[max(outcome.start() - 80, 0):outcome.end() + 80])
    dates = [d for l in txt.splitlines() if "cut to dates <" not in l for d in re.findall(r"\b20\d\d-\d\d-\d\d\b", l)]
    assert dates and all(d < "2025-06-30" for d in dates), [d for d in dates if d >= "2025-06-30"][:5]
    for frag in ("universe size per session by year", "payers in the universe by year", "X against P (sessions)", "ENTRY SETS", "R10 (K = 10) events -> first reason", "X fell before P - 1", "registered NOX R10: stretch trades removed at their first reason",
                 "look-ahead NOX R20: stretch trades removed", "hygiene events on the names ever in the universe", "first entry", "last entry", "TBIS flags:", "ES prints on the", "ES return (", "cache manifest sha256", "events:", "pass the cycle test", "prereg check:"):
        assert frag in txt, frag


# ------------------------------------------------------------------ smoke: every command end to end on the synthetic worlds
def smoke(*a):
    """python r18_divrun.py smoke DIR [stage_b]: offline, on SYNTHETIC worlds (nothing real is read or written; DIR is wiped and its name must contain 'smoke'). Order: the selftest on the real constants; the planted world through the real loaders against
    plain-python recounts of everything this file adds; the dryload (counts only); Stage A's refusal paths; Stage A on the NULL world (must FAIL) and on the PLANTED world (the run-up must be found: (a)-(e) pass, (f) awaits the hand audit); the hand audit
    (keep / data_event) and the recomputation; Stage B's refusal paths; with the argument stage_b also the one read of Stage B on the synthetic lockbox days, the verdict = the leg's veto alone, a second read refused, Stage A frozen"""
    root = os.path.abspath(a[0] if a else os.path.join(tempfile.gettempdir(), "divrun_smoke"))
    with_b = "stage_b" in a[1:]
    why = smoke_refusal(root)
    if why:
        raise SystemExit(why)
    selftest()                                                                             # the hand-made checks first, on the real constants (before anything below is patched)
    t_start = time.time()
    dates_of = lambda txt: re.findall(r"\b20\d\d-\d\d-\d\d\b", txt)
    with smoke_env(root) as env:
        sa_path, go, rd = os.path.join(OUT, "divrun_stageA.json"), os.path.join(OUT, GO_FLAG), os.path.join(OUT, READ_FLAG)
        print(f"synthetic market: {len(env.fk['plant'].names)} names x {len(env.days):,} business days ({env.days[0]:%Y-%m-%d} .. {env.days[-1]:%Y-%m-%d}); {len(env.quarterly)} regular quarterly payers; the PLANTED world takes +{SMOKE_BUMP:.0%} over the 19 sessions "
              f"before every regular ex-date and gives it back on it, the NULL world does not; both through r5_siporb's own pulls ({env.build_seconds:.0f}s); the wide calendar: {env.rows_in_calendar:,} rows, sha256 {env.wide_sha[:16]}...")
        # ---- 1. the planted world through the REAL loaders: the cut, the planted data cases, then every pipeline step against a plain-python recount
        W, cal, winfo, tbis = smoke_world(env, "plant")
        di, ix = (lambda s: W.days.get_loc(TS(s))), list(W.syms)
        n_cut = sum(1 for r_ in env.ca_rows if ((r_.split(",")[4] or r_.split(",")[5]) >= "2025-06-30"))
        assert winfo["rows_on_file"] == env.rows_in_calendar and winfo["rows_dropped_at_the_cut"] == n_cut > 100 and winfo["pinned"]["matches"] is True and winfo["csv_sha256"] == env.wide_sha, winfo
        assert W.days.max() < S.LB0 and W.days[0] == TS("2015-11-02") and len(W.days) == len(pd.bdate_range("2015-11-02", "2025-06-27")) and cal.div["ex"].max() < S.LB0 and cal.spin["ex"].max() < S.LB0, "nothing on / after the cut"
        assert len(tbis) == 4 and tbis["day"].max() < S.LB0 and len(D15.load_tbis(S.END)) == 5, "TBIS's row on the lockbox day is cut at read time"
        spl, s18, s23, dl = (ix.index(n_) for n_ in ("SPL", "S18", "S23", "DLST"))
        assert W.chg[di("2024-03-15"), spl] and abs(W.F[di("2024-03-14"), spl] - 2.0) < 1e-3 and abs(W.F[di("2024-03-15"), spl] - 1.0) < 1e-3, "SPL's registered split: F 2 -> 1"
        assert W.fl[1][di("2024-04-22"), s18] and not W.chg[:, s18].any() and W.fl[3][di("2024-05-14"), s23] and not W.fl[1][di("2024-05-14"), s23], "S18's missed x4 is a gap-scan flag, S23's +60% gap is the jump rule"
        assert np.isfinite(W.Cl[di("2024-05-31"), dl]) and np.isnan(W.Cl[di("2024-06-03"), dl]), "DLST's last bar is 2024-05-31"
        assert np.isnan(W.es.ret[di("2024-03-05")]) and np.isnan(W.es.ret[di("2024-03-06")]) and np.isnan(W.es.c16r[di("2024-03-05")]) and np.isfinite(W.es.c16r[di("2024-03-06")]), "the ES master has no print on 2024-03-05: no return that session and the next"
        ctx, cnt = smoke_recount(W, cal)
        assert W.es_hole[di("2024-03-05")] and not W.es_hole[di("2024-03-06")] and W.esA[di("2024-03-05")] == W.esA[di("2024-03-04")], "the hedge carries the last print across the hole"
        print(f"planted cases ok through the real loaders (the cut at read, SPL / S18 / S23 / DLST, the ES hole, TBIS's lockbox row); against plain-python recounts: {cnt['events']:,} events ({cnt['cycle_ok']:,} cycle-OK), both entry sets "
              f"({cnt['entry_set_R10']:,} / {cnt['entry_set_R20']:,} events enter), {cnt['trade_sets_recounted']} trade sets (3 exits x 2 cells x 2 readings), {cnt['trade_paths_recounted']:,} trade paths with their dividend credit, ex-day drop, costs and hedges "
              f"(up to {cnt['max_contracts']} MES), {cnt['placebo_windows_checked']} placebo windows, {cnt['random_name_pools_checked']} random-name pools ({cnt['seconds']}s)")
        B, legs = A13.load_463()
        rowsB = A13.book_rows(B, W)
        es_ = {K: entry_set(W, ctx, K) for K in (10, 20)}
        # ---- 2. the dryload: COUNTS only
        before = sorted(os.listdir(OUT))
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            dryload()
        td = buf.getvalue()
        assert sorted(os.listdir(OUT)) == before, "the dryload writes nothing"
        dryload_text_checks(td)
        fb = io.StringIO()
        with contextlib.redirect_stdout(fb):
            print_funnel({"R10": es_[10], "R20": es_[20]})
        assert fb.getvalue() in td and f"{ctx.ev.n:,} remain" in td and f"{int(ctx.ev.cyc.sum()):,} pass the cycle test" in td, "the dryload's funnel and event counts are the recount's"
        for rule in EXITS:
            for cell in CELLS:
                tr = trade_set(W, ctx, es_[KS[cell]], rule, "registered", WF0, PRE_END)
                assert f"{rule} {cell}: {tr.n:,} trades; first entry {W.days[tr.e.min()]:%Y-%m-%d}, last entry {W.days[tr.e.max()]:%Y-%m-%d}, first exit {W.days[tr.x.min()]:%Y-%m-%d}, last exit {W.days[tr.x.max()]:%Y-%m-%d}" in td, (rule, cell)
        xd = os.path.dirname(env.wide_csv)
        absent = {"dir": xd, "csv": os.path.join(xd, "absent.csv"), "manifest": os.path.join(xd, "absent.json")}
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), patched(M17, wide_paths=lambda: absent):
            dryload()
        assert "not on file yet" in buf.getvalue() and "this dryload counted no event" in buf.getvalue() and "ENTRY SETS" not in buf.getvalue(), "the dryload says so when the wide calendar is absent"
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), patched(M17, WIDE_CA_SHA=None):
            dryload()
        assert "NOT registered yet" in buf.getvalue() and "ENTRY SETS" in buf.getvalue(), "the dryload reads an unregistered calendar and says so (only Stage A / B refuse)"
        dryload_text_checks(buf.getvalue())
        print("dryload ok on the synthetic world: counts only (no price, return, P&L or statistic), no lockbox date, nothing written, its funnel / events / trades-per-day lines equal the recount")
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
        must("RESMOM line file", REF_SHA="0" * 64)                                          # [X1] the line file is not the registered one: refused before any data loads
        must("is not on file - the REFERENCE book", REF_CSV=os.path.join(root, "resmom", "absent.csv"))
        real_bc = D15.book_checks

        def book_ok(B_):                                                                   # the #463 checks stubbed to pass, so that the REFERENCE's own registered numbers are the ones refused (the synthetic reference cannot reproduce them)
            bk_, dd_, S_ = real_bc(B_)
            return {**bk_, "ok": True}, {**dd_, "ok": True}, S_
        must("does not reproduce its registered WF numbers", CHECK_BOOK=True, book_checks=book_ok)
        print("Stage A refuses (and writes nothing) on: a changed pre-registration, an unregistered / other / absent wide calendar, a missing manifest, a book that does not reproduce #463, a RESMOM line file that is absent / not the registered one / whose reference "
              "does not reproduce its registered WF numbers")

        def run_stage_a(world):
            env.switch(world)
            b_ = io.StringIO()
            with contextlib.redirect_stdout(b_):
                o_ = stage_a()
            return o_, b_.getvalue()
        # ---- 4. Stage A on the NULL world: the same market without the run-up must FAIL
        t0 = time.time()
        out_n, txt_n = run_stage_a("null")
        pass_n = out_n["stageA"]["registered_pass_cells"]
        assert out_n["judged"] is True and pass_n == [] and out_n["candidate"] is None and out_n["stageA"]["null"]["X"]["draws"] == NREP == 100, (pass_n, out_n["candidate"])
        assert "DIVRUN Stage A: FAIL - no cell passes (a)-(e) under the registered NO-X reading" in txt_n and "Stage A (a)-(e) pass" not in txt_n and all(d < "2025-06-30" for d in dates_of(txt_n)), "the null world fails and prints no lockbox date"
        assert abs(out_n["event_path"]["total_mean_bps"]) < 100.0 and all(not c["PASS"] for r in NULL_EXITS for c in out_n["stageA"]["cells"][r].values()), out_n["event_path"]["total_mean_bps"]
        for r in NULL_EXITS:
            for c in CELLS:
                assert out_n["stageA"]["cells"][r][c]["base"]["roc"] < RULES["roc"], (r, c)
        assert out_n["reference"]["sha256"] == env.ref_sha == out_n["reference"]["pinned_sha256"] and not any(c["A2"]["incremental_pass"] for r in EXITS for c in out_n["stageA"]["cells"][r].values()), "the null world adds nothing to the reference"
        assert "REFERENCE book [X1]" in txt_n and "DIAGNOSTICS [X2]" in txt_n and "EVENT-TIME PATH [X2]" in txt_n and "no incremental pass" in txt_n and "INCREMENTAL PASS" not in txt_n and abs(out_n["event_path_x"]["pre_mean_bps"]) < 100.0
        os.remove(sa_path)
        print(f"Stage A on the NULL world ({time.time() - t0:.0f}s): FAIL as it must - event path {out_n['event_path']['total_mean_bps']:+.1f} bps a trade, WF ROC@30k "
              + ", ".join(f"{r} {c} {out_n['stageA']['cells'][r][c]['base']['roc']:.1f}" for r in NULL_EXITS for c in CELLS) + f"; null p95 {out_n['stageA']['null']['NOX']['roc_max']['p95']:.1f}")
        try:
            with quiet():
                stage_b()
            raise AssertionError("Stage B must refuse without the lead's go-flag")
        except SystemExit as e:
            assert "go-flag" in str(e) and not os.path.exists(rd)
        # ---- 5. Stage A on the PLANTED world: (a)-(e) pass, (f) awaits the hand audit
        t0 = time.time()
        out, txt = run_stage_a("plant")
        cells = out["stageA"]["cells"]
        ver, passing, cand = stage_a_flow(cells)
        assert out["judged"] is True and out["stageA"]["registered_pass_cells"] == passing == list(CELLS) and out["candidate"]["cell"] == cand and out["pending_hand_audit"] == passing, (passing, cand)
        assert cand == max(CELLS, key=lambda c: (cells[REGISTERED][c]["base"]["roc"], -CELLS.index(c))) and out["candidate"]["also_passes"] == [c for c in CELLS if c != cand] and out["candidate"]["rule"] == REGISTERED
        assert all(not v["differ"] and v["registered"] for v in out["stageA"]["verdicts"].values()) and all(all(cells[r][c]["checks"].values()) for r in NULL_EXITS for c in CELLS)
        for c in CELLS:
            assert f"Stage A (a)-(e) pass, (f) awaits the hand audit - cell {c} under the registered NO-X reading" in txt, c
        assert "(f) AWAITS THE HAND AUDIT" in txt and "audit complete" not in txt.lower() and "(f) pass" not in txt.lower() and all(d < "2025-06-30" for d in dates_of(txt)), "the harness never decides (f); no lockbox date"
        assert cells[REGISTERED][cand]["base"]["n_pos"] >= RULES["n"] and out["prereg_sha256_lf"] == PREREG_SHA and {k: out.get(k) for k in stamp()} == stamp() and out["manifest_sha256"] == D15.MANIFEST_PREFIX + "0" * 56
        # the planted run-up in the event-time path: ~ +20 bps a session over the 19 sessions before P, nothing at tau = -20, the null world's path flat
        ep = out["event_path"]
        mb = dict(zip(ep["taus"].tolist(), ep["mean_bps"]))
        trX = trade_set(W, ctx, es_[20], "X", "registered", WF0, PRE_END)
        pth = event_path(W, trX)
        assert ep["trades"] == int((trX.kind == 0).sum()) == pth.trades > 1000 and np.allclose(ep["mean_bps"], pth.mean_bps, equal_nan=True) and np.allclose(ep["n"], pth.n), "the stage's path is the recount's"
        ramp = float(np.mean([mb[t] for t in range(-19, 0)]))
        assert 300.0 < ep["total_mean_bps"] < 460.0 and 15.0 < ramp < 26.0 and abs(mb[-20]) < 30.0 and ep["total_mean_bps"] - out_n["event_path"]["total_mean_bps"] > 250.0, (ep["total_mean_bps"], ramp, mb[-20])
        # [X2] the draft's X-axis variant: the planted run-up sits at X - 19 .. X - 1 and its reversal ON the ex-date (tau = 0); the stage's path is the recount's, printed before any cell statistic
        pthx = event_path_x(W, trX)
        epx = out["event_path_x"]
        mbx = dict(zip(epx["taus"].tolist(), epx["mean_bps"]))
        assert epx["taus"].tolist() == list(range(-25, 6)) and epx["trades"] == pthx.trades == ep["trades"] and np.allclose(epx["mean_bps"], pthx.mean_bps, equal_nan=True) and np.allclose(epx["n"], pthx.n), "the stage's X-axis path is the recount's"
        ramp_x = float(np.mean([mbx[t] for t in range(-19, 0)]))
        assert 15.0 < ramp_x < 26.0 and abs(mbx[-25]) < 30.0 and abs(mbx[-20]) < 30.0 and mbx[0] < -300.0 and abs(mbx[3]) < 30.0, (ramp_x, mbx[-25], mbx[-20], mbx[0], mbx[3])
        assert 300.0 < pthx.pre_mean_bps < 460.0 and pthx.post_mean_bps < -300.0 and abs(pthx.total_mean_bps) < 120.0 and abs(epx["pre_mean_bps"] - pthx.pre_mean_bps) < 1e-9, (pthx.pre_mean_bps, pthx.post_mean_bps, pthx.total_mean_bps)
        # every cell's WF numbers recomputed from the recount's trade sets and the book file
        for rule in EXITS:
            for cell in CELLS:
                tr = trade_set(W, ctx, es_[KS[cell]], rule, "registered", WF0, PRE_END)
                st = stat_of(B, rowsB, run_bundle(W, prepare(W, tr)), WF0, PRE_END)[0]
                got = cells[rule][cell]["base"]
                assert st["n_pos"] == got["n_pos"] == out["parity"][f"{rule}/{cell}"]["n_pos"] and abs(st["net"] - got["net"]) < 1e-6 and abs(st["roc"] - got["roc"]) < 1e-9 and abs(st["max_dd"] - got["max_dd"]) < 1e-9, (rule, cell)
        # A2 (a report) [X1]: the REFERENCE (#463 + 0.264 x RES, rebuilt here from the book file and the stub's own RES column) + c x the cell against the reference; c = 25% of #463's daily std over the window / the cell's, from a fresh run of the cell
        mw = B.mask(*A2_WIN)
        kw_ = np.flatnonzero(B.mask(WF0, PRE_END))
        dfr = pd.read_csv(env.ref_csv)
        ref_raw = np.full(B.n, np.nan)
        ref_raw[kw_] = B.raw[kw_] + 0.264 * dfr["RES"].to_numpy(float)
        ref_s = plain_stats(ref_raw[kw_], B.index[kw_])
        for cell in CELLS:
            a2 = cells[REGISTERED][cell]["A2"]
            run_ = run_bundle(W, prepare(W, trade_set(W, ctx, es_[KS[cell]], REGISTERED, "registered", WF0, PRE_END)))
            xb_ = D15.to_B(run_.x, rowsB, B.n)
            sb_, sc_ = float(np.std(B.raw[mw], ddof=1)), float(np.std(xb_[mw], ddof=1))
            c_ = 0.25 * sb_ / sc_
            assert a2["window"] == ["2017-03-01", "2019-02-28"] and a2["rows"] == int(mw.sum()) and a2["target"] == 0.25 and "pass" not in a2 and a2["book_shadow_line"] is a2["incremental_pass"], (cell, a2)
            assert abs(a2["c"] - c_) <= 1e-9 * c_ and abs(a2["std_book"] - sb_) <= 1e-9 * sb_ and abs(a2["std_cell"] - sc_) <= 1e-9 * sc_ and a2["at_half_c"]["c"] == 0.5 * a2["c"] and a2["at_double_c"]["c"] == 2.0 * a2["c"], cell
            for got, mult in ((a2, 1.0), (a2["at_half_c"], 0.5), (a2["at_double_c"], 2.0)):
                w_ = plain_stats((ref_raw + mult * c_ * xb_)[kw_], B.index[kw_])
                assert abs(got["roc"] - w_["roc"]) < 1e-5 and abs(got["sortino"] - w_["sortino"]) < 1e-7 and abs(got["net"] - w_["net"]) < 1e-3, (cell, mult)
            wp_ = plain_stats((B.raw + c_ * xb_)[kw_], B.index[kw_])
            assert abs(a2["plain_463"]["roc"] - wp_["roc"]) < 1e-5 and abs(a2["reference"]["roc"] - ref_s["roc"]) < 1e-5 and abs(a2["reference"]["sortino"] - ref_s["sortino"]) < 1e-7
            assert a2["incremental_pass"] is bool(a2["roc"] > a2["reference"]["roc"] and a2["sortino"] > a2["reference"]["sortino"]), cell
        ca2 = cells[REGISTERED][cand]["A2"]
        assert out["candidate"] == {"cell": cand, "rule": REGISTERED, "c": ca2["c"], "std_book": ca2["std_book"], "std_cell": ca2["std_cell"], "window": ["2017-03-01", "2019-02-28"], "a2_book_roc": ca2["roc"], "a2_reference_roc": ca2["reference"]["roc"],
                                    "incremental_pass": ca2["incremental_pass"], "book_shadow_line": ca2["book_shadow_line"], "also_passes": out["candidate"]["also_passes"]} and ca2["c"] > 0, "the frozen size travels with its two stds and the window"
        # [X1] the reference and its drawdown days, [X2] the diagnostics: recounted from the book file, the stub's RES column and fresh runs of every cell under every exit rule
        eps_p, qual_p = plain_episodes(ref_raw[kw_])
        mask_p = np.zeros(len(kw_), bool)
        for _d, i0_, it_, _i1 in qual_p:
            mask_p[i0_:it_ + 1] = True
        rf_ = out["reference"]
        assert rf_["file"] == "resmom_cells_daily_wf.csv" and rf_["sha256"] == rf_["pinned_sha256"] == env.ref_sha and rf_["rows"] == len(kw_) and rf_["weight_of_RES"] == 0.264 and rf_["max_abs_book_mtm_difference"] < 1e-5
        assert abs(rf_["facts"]["roc"] - ref_s["roc"]) < 1e-5 and abs(rf_["facts"]["sortino"] - ref_s["sortino"]) < 1e-7 and abs(rf_["facts"]["max_dd"] - ref_s["max_dd"]) < 1e-4 and not all(rf_["reproduced"].values()), "the synthetic reference is not the registered one"
        assert rf_["structure"]["episodes"] == len(qual_p) >= 1 and rf_["structure"]["all_episodes"] == len(eps_p) and rf_["structure"]["days"] == int(mask_p.sum())
        assert "REFERENCE book [X1]" in txt and f"{len(qual_p)} qualifying episodes of {len(eps_p)}" in txt and "DIAGNOSTICS [X2]" in txt and "EVENT-TIME PATH [X2]" in txt and "EVENT-TIME PATH [V4]" in txt and "#70 gate basis [X1]" in txt
        assert txt.index("REFERENCE book [X1]") < txt.index("EVENT-TIME PATH [V4]") < txt.index("EVENT-TIME PATH [X2]") < txt.index("exit rule X:") < txt.index("DIAGNOSTICS [X2]"), "the reference, then both event-time paths, BEFORE any cell statistic; the diagnostics after the cells"
        wfm = np.asarray((W.days >= WF0) & (W.days <= PRE_END))
        n_inc = 0
        for rule in EXITS:
            for cell in CELLS:
                tr_ = trade_set(W, ctx, es_[KS[cell]], rule, "registered", WF0, PRE_END)
                bu_ = prepare(W, tr_)
                c2_ = cells[rule][cell]
                n_inc += int(c2_["A2"]["incremental_pass"])
                for got, bps in ((c2_["cost0"], 0.0), (c2_["base"], 5.0), (c2_["stress"]["10 bps"], 10.0), (c2_["stress"]["20 bps"], 20.0)):
                    want = stat_of(B, rowsB, run_bundle(W, bu_, bps), WF0, PRE_END)[0]
                    assert abs(got["net"] - want["net"]) < 1e-6 and abs(got["roc"] - want["roc"]) < 1e-9, (rule, cell, bps)
                assert c2_["cost0"]["net"] > c2_["base"]["net"] > c2_["stress"]["10 bps"]["net"] > c2_["stress"]["20 bps"]["net"], (rule, cell)
                run2_ = run_bundle(W, bu_)
                assert abs(c2_["unhedged"]["net"] - float(run2_.x_unhedged[wfm].sum())) < 1e-6 and abs(c2_["hedge_leg"]["net"] - float(run2_.hedge_agg[wfm].sum())) < 1e-6 and abs(c2_["unhedged"]["net"] + c2_["hedge_leg"]["net"] - c2_["base"]["net"]) < 1e-6
                assert abs(sum(c2_["base"]["by_year"].values()) - c2_["base"]["net"]) < 1e-6 and sum(out["reports"]["trades_by_year"][rule][cell].values()) == tr_.n
                xr_ = D15.to_B(run2_.x, rowsB, B.n)[kw_]
                tab = out["reports"]["ref_episodes"][rule][cell]
                assert len(tab) == len(qual_p) and all(abs(t_["cell_pnl"] - float(xr_[i0_:it_ + 1].sum())) < 1e-6 and abs(t_["depth"] - dep_) < 1e-6 for t_, (dep_, i0_, it_, _i1) in zip(tab, qual_p)), (rule, cell)
                assert abs(c2_["gate70"]["DO"] - float(xr_[mask_p].sum()) / -float(ref_raw[kw_][mask_p].sum())) < 1e-9 and c2_["seat_ref"]["dd_days"] == int(mask_p.sum()), (rule, cell)
                if rule in NULL_EXITS:
                    nl_ = out["stageA"]["null"][rule]
                    assert c2_["gate70"]["null_do_p95"] == nl_["do_ref_max"]["p95"] and nl_["do_ref_max"]["finite"] == NREP == 100 and nl_["random_names"]["do_ref_max"]["finite"] == NREP, (rule, cell)
        assert n_inc >= 2, "the planted cells lift the reference's ROC and Sortino together"
        # the hygiene readings: the registered reading removed the planted cases inside a hold, the look-ahead reading kept them at their naive raw P&L, and both readings are in the file
        hr, hk = out["hygiene_counts_by_year"]["registered"], out["hygiene_counts_by_year"]["look_ahead"]
        assert hr["NOX/R20"][2024].get("hold_split", 0) >= 1 and hr["NOX/R10"][2024].get("hold_split", 0) >= 1 and hr["NOX/R10"][2024].get("hold_gap", 0) >= 1 and hr["NOX/R10"][2024].get("hold_jump", 0) >= 1, (hr["NOX/R10"][2024], hr["NOX/R20"][2024])
        assert hk["NOX/R20"][2024].get("kept_naive", 0) >= 3 and sum(v.get("hold_split", 0) for v in hk["NOX/R20"].values()) == 0 and out["look_ahead_reading"]["null"]["X"]["draws"] == NREP and set(out["look_ahead_reading"]["flips"]) == {f"{r}/{c}" for r in NULL_EXITS for c in CELLS}
        # the audit candidates: the 50 largest gains per (rule, cell), largest first, dates before the cut, the largest equal to the recount's largest trade
        cd = pd.read_csv(os.path.join(OUT, "divrun_audit_candidates.csv"))
        assert {"symbol", "event", "x_date", "e1", "e2", "e3", "e1_amount", "calendar_row", "pnl", "stock_pnl", "hedge_pnl", "cash_received", "split_factor_ratio_window_to_exit", "tbis_price_ratio", "asset_status", "flags_in_hold"} <= set(cd.columns), list(cd.columns)
        assert set(zip(cd["rule"], cd["cell"])) == {(r, c) for r in ("X", REGISTERED) for c in CELLS} and cd.groupby(["rule", "cell"]).size().max() == AUDIT_N and cd["exit"].max() < "2025-06-30" and cd["event"].max() < "2025-07-01"
        for (rule, cell), g in cd.groupby(["rule", "cell"]):
            assert (g["pnl"].diff().dropna() <= 1e-9).all(), "largest gains first"
            tr = trade_set(W, ctx, es_[KS[cell]], rule, "registered", WF0, PRE_END)
            bu = prepare(W, tr)
            run = run_bundle(W, bu)
            assert abs(g["pnl"].iloc[0] - float(run.pos.pnl.max())) < 1e-6, (rule, cell)
            for _, r in g.head(3).iterrows():                                              # the three largest, recounted: stock leg by plain python (price path + cash + costs) and the exact hedge
                i = next(i for i in range(tr.n) if str(W.syms[tr.col[i]]) == r["symbol"] and f"{W.days[tr.e[i]]:%Y-%m-%d}" == r["entry"])
                _d, tot, cash = brute_trade(W, int(tr.col[i]), int(tr.e[i]), int(tr.x[i]), bool(tr.naive[i]), COST_BPS)
                hedge = brute_hedge(W, [(int(tr.e[i]), int(tr.x[i]), float(tr.beta[i]))])[3][0]
                assert abs(r["stock_pnl"] - tot) < 1e-6 and abs(r["hedge_pnl"] - hedge) < 1e-6 and abs(r["pnl"] - tot - hedge) < 1e-6 and abs(r["cash_received"] - cash) < 1e-6, (rule, cell, r["symbol"])
        pm = peak_mb()
        print(f"Stage A on the PLANTED world ({time.time() - t0:.0f}s): the run-up is found - event path {ep['total_mean_bps']:+.0f} bps a trade (the null world {out_n['event_path']['total_mean_bps']:+.0f}), about {ramp:+.0f} bps a session over the 19 sessions before P; "
              + ", ".join(f"{r} {c} ROC@30k {cells[r][c]['base']['roc']:.0f} ({cells[r][c]['base']['n_pos']:,} trades)" for r in NULL_EXITS for c in CELLS) + f"; (a)-(e) pass for {passing}, candidate {cand}, (f) awaits the hand audit"
              + (f"; peak memory {pm:,.0f} MB" if pm else ""))
        print(f"[X1] the REFERENCE book (#463 + 0.264 x RES, the stub's line): WF ROC@30k {ref_s['roc']:.1f} Sortino {ref_s['sortino']:.2f}, {len(qual_p)} qualifying drawdown episodes (of {len(eps_p)} in all) covering {int(mask_p.sum())} DD days; A2 (a report): R10 and R20 against the reference: "
              + ", ".join(f"{c} c x{cells[REGISTERED][c]['A2']['c']:.3g} -> ROC@30k {cells[REGISTERED][c]['A2']['roc']:.1f} / Sortino {cells[REGISTERED][c]['A2']['sortino']:.2f} ({'INCREMENTAL PASS' if cells[REGISTERED][c]['A2']['incremental_pass'] else 'no incremental pass'})" for c in CELLS)
              + f"; [X2] recounted for all 6 cell x exit-rule columns: the cost curve at 0 / 5 / 10 / 20 bps, the July-June years, the stock and hedge legs, the {len(qual_p)} episodes, the #70 gate basis; the X-axis path: ramp {ramp_x:+.0f} bps a session, ex-day {mbx[0]:+.0f} bps")
        # ---- 6. the hand audit: every listed contributor 'keep' -> the same numbers, the audit counted; then a data_event on the candidate's largest gain -> out of both cells and the null, Stage A computed again
        ap = os.path.join(OUT, "divrun_audit.csv")
        pd.DataFrame({"symbol": cd["symbol"], "event": cd["event"], "cell": cd["cell"], "verdict": "keep", "note": "smoke: nothing found"}).to_csv(ap, index=False)
        out2, txt2 = run_stage_a("plant")
        assert out2["audit"]["rows"] == len(cd) and out2["audit"]["keep"] == len(cd) and out2["audit"]["data_event"] == 0 and out2["audit_sha256"] == file_sha(ap) != out["audit_sha256"] and all(v["audited"] == v["listed"] == AUDIT_N for v in out2["audit_status"].values())
        assert out2["stageA"]["registered_pass_cells"] == passing and out2["candidate"] == out["candidate"], "a keep changes nothing"
        assert all(out2["stageA"]["cells"][r][c]["base"][k] == cells[r][c]["base"][k] for r in EXITS for c in CELLS for k in ("n_pos", "net", "roc", "max_dd", "sortino")), "a keep changes no number"
        top = cd[(cd["cell"] == cand) & (cd["rule"] == REGISTERED)].iloc[0]
        au = pd.read_csv(ap)
        au.loc[(au["symbol"] == top["symbol"]) & (au["event"] == top["event"]), "verdict"] = "data_event"
        au.to_csv(ap, index=False)
        out3, txt3 = run_stage_a("plant")
        cd3 = pd.read_csv(os.path.join(OUT, "divrun_audit_candidates.csv"))
        assert out3["audit"]["data_event"] >= 1 and not ((cd3["symbol"] == top["symbol"]) & (cd3["event"] == top["event"])).any(), "the event is gone from every list"
        ev_hit = (ctx.ev.sym == top["symbol"]) & (ctx.ev.p_date == np.datetime64(top["event"]))
        assert int(ev_hit.sum()) == 1 and out3["audit_sha256"] != out2["audit_sha256"]
        for c in CELLS:
            e_old, e_new = out["entry_sets"][c], out3["entry_sets"][c]
            delta = e_old["n"] - e_new["n"]
            assert delta in (0, 1) and (delta == 1 or c != cand) and sum(v.get("audit", 0) for v in e_new["by_year"].values()) == delta, (c, e_old["n"], e_new["n"])
            for r in EXITS:
                assert out3["stageA"]["cells"][r][c]["base"]["n_pos"] <= cells[r][c]["base"]["n_pos"] and out3["parity"][f"{r}/{c}"]["n_pos"] == out3["stageA"]["cells"][r][c]["base"]["n_pos"]
        assert out3["stageA"]["cells"][REGISTERED][cand]["base"]["n_pos"] == cells[REGISTERED][cand]["base"]["n_pos"] - 1 and out3["stageA"]["null"]["NOX"]["draws"] == NREP
        print(f"hand audit: all {len(cd)} listed rows 'keep' -> the same numbers, audit counted {AUDIT_N}/{AUDIT_N} on every list; a data_event on {top['symbol']} {top['event']} ({cand}'s largest gain, ${top['pnl']:,.0f}) -> out of both cells, all three rules and "
              f"the nulls: {cand} {cells[REGISTERED][cand]['base']['n_pos']:,} -> {out3['stageA']['cells'][REGISTERED][cand]['base']['n_pos']:,} trades, net ${cells[REGISTERED][cand]['base']['net']:,.0f} -> ${out3['stageA']['cells'][REGISTERED][cand]['base']['net']:,.0f}")
        out, cells = out3, out3["stageA"]["cells"]
        cand, c_frozen = out["candidate"]["cell"], out["candidate"]["c"]
        # ---- 7. Stage B's refusal paths: the lead's go-flag first, then a stale stamp, a changed spec, a changed audit file, a broken size, drifted inputs; none may write the read flag
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
        for k in ("harness_sha256", "r17_sha256", "r15_sha256", "r13_sha256", "wide_ca_sha256"):
            j = json.loads(js0)
            j[k] = "0" * 64
            open(sa_path, "w").write(json.dumps(j))
            must_b("different harness version")
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
            must_b("positive number")
        j = json.loads(js0)
        j["candidate"]["rule"] = "ZZZ"
        open(sa_path, "w").write(json.dumps(j))
        must_b("positive number")
        open(sa_path, "w").write(js0)
        must_b("DIFFERS", PREREG_SHA="0" * 64)
        with patched(M17, WIDE_CA_SHA="0" * 64):
            must_b("different harness version")                                           # the pinned calendar is in Stage A's stamp: another pinned sha stops it at the stamp
        au0 = open(ap).read()
        open(ap, "a").write("ZZZ,2016-11-01,R10,keep,a changed audit file\n")
        must_b("not the file Stage A ran with")
        open(ap, "w").write(au0)
        must_b("do not reproduce its LB numbers", CHECK_BOOK=True)                         # the book's LB numbers (the synthetic one cannot reproduce them)
        okbk = lambda B_, lo_, hi_, ref: {"roc": 0.0, "sortino": 0.0, "ref": list(ref), "ok": True}
        with patched(A13, book_check=okbk):
            must_b("not the one Stage A ran on", CHECK_BOOK=True, manifest_sha=lambda: "ffffffff" + "0" * 56)                    # a drifted cache manifest (the LB book check stubbed to pass so that the manifest one is reached)
        csv0 = open(env.wide_csv, "rb").read()
        with open(env.wide_csv, "ab") as f_:
            f_.write(b"cash_dividend,S01,,,2024-02-09,2024-02-09,,,0.01,,,,False\n")
        must_b("is not the registered wide calendar")                                      # the file changed after it was registered: refused before the flag
        open(env.wide_csv, "wb").write(csv0)
        assert M17.sha_raw(env.wide_csv) == env.wide_sha
        j = json.loads(js0)
        j["parity"][f"{REGISTERED}/{cand}"]["net"] += 1e6
        open(sa_path, "w").write(json.dumps(j))
        must_b("do not reproduce on Stage B's data")                                       # the WF numbers drifted since Stage A
        j = json.loads(js0)
        j["parity"][f"{REGISTERED}/{cand}"]["n_pos"] += 1
        open(sa_path, "w").write(json.dumps(j))
        must_b("do not reproduce on Stage B's data")
        j = json.loads(js0)
        j["candidate"]["c"] *= 1.0001
        open(sa_path, "w").write(json.dumps(j))
        must_b("volatility-set size c")                                                    # the frozen size is recomputed from 2017-03-01 .. 2019-02-28 on Stage B's data: a drift of 1 in 10,000 stops it
        open(sa_path, "w").write(js0)
        print("Stage B refused before the flag in every case above (the flag was never written)")
        if not with_b:
            os.remove(go)
        else:
            # ---- 8. Stage B, the one read (synthetic lockbox days only): the flag after the load and the checks, the verdict is the LEG's veto alone, a second read refused, Stage A frozen
            print("--- Stage B, the one read on the synthetic lockbox days: the flag after the load and the checks, the verdict, a second read refused")
            cap, real_cs = {}, D15.cell_stats

            def tap(Bk, xk, ck, lo_, hi_, run_, *a_, **k_):                                # sees the lockbox call of the one read: keeps the cell's daily series, to recompute the book add independently
                st_ = real_cs(Bk, xk, ck, lo_, hi_, run_, *a_, **k_)
                if lo_ == LB0:
                    cap["x"] = np.array(xk)
                return st_
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf), patched(D15, cell_stats=tap):
                ok = stage_b()
            txt_b = buf.getvalue()
            print(txt_b.rstrip())
            sb = json.load(open(os.path.join(OUT, "divrun_stageB.json")))
            assert os.path.exists(rd) and sb["pass"] == ok and sb["cell"] == cand and sb["rule"] == REGISTERED and sb["c"] == c_frozen and sb["leg"]["n_pos"] > 0 and {k: sb.get(k) for k in stamp()} == stamp() and sb["prereg_sha256_lf"] == PREREG_SHA
            assert set(sb["checks"]) == {f"leg trades>={RULES['b_n']}", "leg net>0", "leg net>0 without its top 1% of trades"} and ok is all(sb["checks"].values()), "the pass is the LEG's veto: three checks, no book"
            assert sb["wide_calendar"]["file"]["csv_sha256"] == env.wide_sha and sb["wide_calendar"]["file"]["rows_dropped_at_the_cut"] < winfo["rows_dropped_at_the_cut"] and sb["es_return_lb"]["stretch"] == ["2025-06-30", "2026-06-30"]
            add, mb_ = sb["book_add_reported"], B.mask(LB0, LB1)                           # the book add on the lockbox at the FROZEN c: reported, recomputed from the book file and the captured series
            want = R11.stats((B.raw + c_frozen * cap["x"])[mb_], B.index[mb_])
            assert add["c"] == c_frozen and abs(add["roc"] - want["roc"]) < 1e-9 and abs(add["sortino"] - want["sort"]) < 1e-9 and abs(add["net"] - want["net"]) < 1e-6 and abs(add["max_dd"] - want["max_dd"]) < 1e-9, add
            assert add["reference"] == {"roc": RULES["b_roc"], "sortino": RULES["b_sort"]} and add["would_have_cleared"] is bool(want["roc"] >= RULES["b_roc"] and want["sort"] >= RULES["b_sort"]) and "never a pass" in add["note"]
            assert "book add, REPORTED and never part of the pass" in txt_b and ("PASS - the leg survives" in txt_b) is ok and ("FAIL - the leg is vetoed" in txt_b) is not ok
            # the pass is the leg's veto ALONE: the same read again with the leg forced to pass and the book add's bar forced to miss, then the leg forced to fail and the bar forced to clear
            def reread(leg_ok, book_ok):
                os.remove(rd)
                os.remove(os.path.join(OUT, "divrun_stageB.json"))

                def forced(Bk, xk, ck, lo_, hi_, run_, *a_, **k_):
                    st_ = real_cs(Bk, xk, ck, lo_, hi_, run_, *a_, **k_)
                    if lo_ == LB0:
                        st_ = {**st_, "n_pos": 10 ** 6 if leg_ok else 0, "net": 1e6 if leg_ok else -1e6, "net_ex_best_pos": 1e6 if leg_ok else -1e6}
                    return st_
                keep_bar = (RULES["b_roc"], RULES["b_sort"])
                RULES["b_roc"], RULES["b_sort"] = (-1e9, -1e9) if book_ok else (1e9, 1e9)
                b_ = io.StringIO()
                try:
                    with contextlib.redirect_stdout(b_), patched(D15, cell_stats=forced):
                        ok_ = stage_b()
                finally:
                    RULES["b_roc"], RULES["b_sort"] = keep_bar
                return ok_, json.load(open(os.path.join(OUT, "divrun_stageB.json"))), b_.getvalue()
            for leg_ok, book_ok in ((True, False), (False, True)):
                ok2, sb2, t2 = reread(leg_ok, book_ok)
                assert ok2 is leg_ok and sb2["pass"] is leg_ok and all(sb2["checks"].values()) is leg_ok and sb2["book_add_reported"]["would_have_cleared"] is book_ok and os.path.exists(rd), (leg_ok, book_ok, sb2["checks"])
                assert abs(sb2["book_add_reported"]["roc"] - add["roc"]) < 1e-9 and sb2["book_add_reported"]["c"] == c_frozen, "the book add is the same sum whatever the verdict"
                assert ("PASS - the leg survives" in t2) is leg_ok and ("FAIL - the leg is vetoed" in t2) is not leg_ok and ("FORWARD SHADOW" in t2) is leg_ok
                print(f"  leg forced {'to pass' if leg_ok else 'to fail'}, book-add bar forced {'to clear' if book_ok else 'to miss'}: Stage B {'PASS' if ok2 else 'FAIL'}, would_have_cleared {sb2['book_add_reported']['would_have_cleared']} - the verdict is the leg's")
            refused(stage_b, "already read")
            refused(stage_a, "Stage A is frozen")
            print("Stage B wrote the flag only after the load and the checks, refused a second read, and Stage A is frozen once the lockbox has been read")
        try:                                                                               # the commands that never touch data
            main(["bogus"])
        except SystemExit:
            pass
        pm = peak_mb()
        print(f"SMOKE OK ({time.time() - t_start:.0f}s" + (f", peak memory {pm:,.0f} MB" if pm else "") + ") - synthetic numbers mean nothing; every command ran end to end offline"
              + ("" if with_b else " (Stage B's read was not run: `smoke DIR stage_b` runs it on the synthetic lockbox days)"))


def main(argv):
    cmd, args = (argv[0], argv[1:]) if argv else ("", [])
    fn = {"selftest": selftest, "smoke": smoke, "dryload": dryload, "stage_a": stage_a, "stage_b": stage_b}.get(cmd)
    if fn is None:
        print("usage: r18_divrun.py selftest | smoke DIR [stage_b] | dryload | stage_a | stage_b   (dryload: counts only; stage_a after the registered pre-registration is committed; stage_b only on the stock families' one sealed-year day, "
              "with the lead's divrun_stageB_GO.flag on file)")
        return
    if cmd in ("stage_a", "stage_b"):
        os.makedirs(OUT, exist_ok=True)
    fn(*args)


if __name__ == "__main__":
    main(sys.argv[1:])
