# EDRIFT r1 - the DRIFT after a volume-confirmed earnings-type reaction in US large caps, rebalanced MONTHLY, dollar-neutral: cells V3 (an EVENT = a session of at least 3 x the name's normal volume) and V5 (at least 5 x); the SCORE of a name at the month-end rank close
# is the REACTION of its most recent event inside the previous 63 sessions (the abnormal return over t-1 .. t+1, the sum of split-safe total return - beta x ES return, beta = RESMOM's regression beta at the rank close); long the 50 highest, short the 50 lowest. A leg for BOOK #463
# that must clear the STANDALONE bars (MANAGER #56) and is reported INCREMENTALLY over the RESMOM reference book #463 + 0.264 x RES (owner standing order addendum 2). Pre-registered: tools/rocfrontier/PREREG_EDRIFT_R1.txt (canonical LF sha256 3325a8ca...2e76 = DRAFT v1 +
# PRE-DATA ADDENDUM 1 (MANAGER #73: [B] incremental, [E1] mechanical volume days are not news, [E2] the placebo in time, [E3] the score prints before any P&L) + ADDENDUM 2 ([X1] the RESMOM reference, [X2] deeper diagnostics) + ADDENDUM 3 ([E5], superseded) + ADDENDUM 4 ([E5'] TV's rebuilt
# EDGAR earnings calendar, sha256 8f4f9f4b..., joined on ndx_tickers)). Every rule, threshold, window and cost below is that file; where it is silent the choice is marked CHOICE.
# EDRIFT is RESMOM r1's sibling in the same lane on the same data: r17_resmom.py is imported, never copied and never edited (its loaders, the pinned wide calendar, the dividend / spin-off arrays, the monthly schedule, the 252-session regression, fills / holds / costs / borrow, the
# cell engine, the statistics, the A2 volatility rule, the hand-audit rows, the refusals) and r18_divrun.py is imported for the REFERENCE book (ref_load / ref_build / ref_at / incremental_pass / a2_report), the null statistics and the shared diagnostics. What this file adds is the EVENT logic:
# the volume rule, the [E1] exclusions, the reaction, the most-recent-event score, the 150 / thirds / 20-a-side fallback, the two nulls (random names = registered, placebo in time = reported), [E3] / [E5'] before any P&L, the event-time path, and the diagnostics table for V3 / V5.
#   python r19_edrift.py selftest    hand-made worlds, no data: the volume event rule, [E1], the reaction, the score, the fallback, both nulls, [E3] / [E5'], the event path, the reference through r18, the refusals, the recounts of every pool / score / pick / path
#   python r19_edrift.py smoke DIR   offline end-to-end on SYNTHETIC worlds (r5_siporb's fake Alpaca, a fake ES master, a fake #463, a fake RESMOM line file, a fake earnings calendar, a fake TBIS file, a fake wide calendar): a world with a planted post-event drift that Stage A must find and
#                                    a world without one where it must not; DIR's name must contain 'smoke'; every command except Stage B's read runs (`smoke DIR stage_b` also runs the one read on the synthetic lockbox days)
#   python r19_edrift.py dryload     WF inputs only (every input cut to dates < 2025-06-30): prints COUNTS - events per cell by year, the [E1] exclusions by year, scored names per rebalance, the fallback months, the [E5'] match counts - never a price, return, reaction, score or P&L
#   python r19_edrift.py stage_a     WF Stage A + the nulls + the [E3] / [E5'] reports FIRST + A2 (an INCREMENTAL report over the reference) + the reports + the diagnostics -> edrift_stageA.json (+ edrift_audit_candidates.csv), PRE-LOCKBOX ONLY
#   python r19_edrift.py stage_b     Stage B (lockbox, ONCE): refuses unless the lead's flag file edrift_stageB_GO.flag is on file (and a Stage A candidate that passed (a)-(e); the hand audit (f) is the lead's, its completion is the go-flag - r18's convention); the pass is the LEG's veto, the book add is only reported
# Reads (never writes) the SIPORB cache through r5_siporb, the ES 5m RTH masters through augur_engine.data, the #463 book through r11_risk, the sha-pinned wide corporate-actions calendar, RESMOM's sha-pinned WF line file (the reference) and TV's sha-pinned EDGAR earnings calendar (Stage A and
# the dryload only, every one cut at read). Results go to OUT (outside git). Nothing here pulls, commits, pushes or writes anywhere else.
import contextlib, io, json, math, os, re, shutil, sys, tempfile, time
from collections import Counter, defaultdict
from types import SimpleNamespace
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import numpy as np, pandas as pd
import r17_resmom as M17            # the sibling harness (RESMOM r1): its loaders, calendar, arrays, schedule, engine, statistics, A2 and audit rows are called wherever they fit
import r18_divrun as DV             # the sibling harness (DIVRUN r1): the REFERENCE book [X1], the incremental A2, the null statistics, the generic diagnostics
D15, S, R11, M12, A13 = M17.D15, M17.S, M17.R11, M17.M12, M17.A13       # r15_ddw (World, cell statistics, seat, null engine), r5_siporb, r11_risk, r12_mdl, r13_attn - through r17's own imports

TS = pd.Timestamp
OUT_DEFAULT = r"C:\EdgeLog\_anatomy_cache\rocfrontier\edrift_r1"
OUT = os.environ.get("EDGELOG_EDRIFT_R1", OUT_DEFAULT)                                                    # results, outside git
PREREG = os.path.join(HERE, "PREREG_EDRIFT_R1.txt")
PREREG_SHA = "3325a8ca11372894d71b8d3e3427f3c00670a69578e9141fb2487d497da72e76"                      # canonical (LF) sha256 of the pre-registration: DRAFT v1 + PRE-DATA ADDENDA 1-4 (addendum 4's [E5'] replaces addendum 3's [E5] file pin and join); if more edits land the lead updates it before the real run
WF0, PRE_END, LB0, LB1 = M17.WF0, M17.PRE_END, M17.LB0, M17.LB1          # WF = positions EXITED 2016-07-01 .. 2025-06-29; LB = exits 2025-06-30 .. 2026-06-30 INCLUSIVE; cuts: S.LB0 / S.END
BOOK_WF, BOOK_LB, DEEPEST_WF = M17.BOOK_WF, M17.BOOK_LB, M17.DEEPEST_WF
NREP, SEED, SEED_PLACEBO = 500, 20261005, 20261006                       # the registered null (random names) and the REPORTED second null ([E2], the placebo in time)
CELLS = ("V3", "V5")                                                     # the family: 2 cells
KS = {"V3": 3, "V5": 5}                                                  # an event = volume >= K x the name's mean volume over t-21 .. t-2
YEARS = D15.YEARS                                                        # the nine July-June WF years 2016-17 .. 2024-25 (2016-17 is short - it counts as a year)
SUBPERIODS = DV.SUBPERIODS                                               # [X2] the regime halves 2016-07-01 .. 2021-12-31 and 2022-01-01 .. 2025-06-29
A2_WIN, A2_TARGET, A2_REPORT = M17.A2_WIN, M17.A2_TARGET, M17.A2_REPORT   # A2 (a REPORT): c = 25% of #463's daily std over 2017-01-03 .. 2018-12-31 / the cell's; 0.5c and 2c reported
COST_BPS, STRESS_BPS, BORROW, BORROW_STRESS = M17.COST_BPS, M17.STRESS_BPS, M17.BORROW, M17.BORROW_STRESS     # 5 bps a side (stress 10, 20); 0.25% a year on short notional (stress 1% and 3% on k_t > 1.5 sessions)
AUDIT_N = 50                                                             # (f) the largest single-name contributors audited by hand
ES_COL = "ES return"                                                     # (label)
SPEC = {"look": 63,              # an event's session t lies in the 63 sessions before the rank close r: rows r-63 .. r-1 (t + 1 <= r)
        "age_cut": 21,           # [E3] the event age (r - t) split: 1 .. 21 sessions (the prereg's '0-21': age 0 cannot occur, t + 1 <= r) against 22 .. 63
        "base_lo": 21, "base_hi": 2, "base_min": 15,       # the volume baseline: the mean over t-21 .. t-2 (20 sessions), at least 15 of them present
        "min_scored": 150, "min_side": 20,                 # fewer than 150 scored names: the top / bottom THIRD, at least 20 a side, else nothing (counted)
        "pl_near": 3,            # [E2] a placebo window (3 sessions, centre s) needs no event day of the name on s-3 .. s+3 (no event day within 2 sessions of any session of it)
        "path_lo": 2, "path_hi": 60}                       # [X2] the event-time path: abnormal return on t+2 .. t+60
THIRD_FRIDAY_MONTHS = (3, 6, 9, 12)                                      # [E1] the index option / futures expiry (and the S&P quarterly rebalance) days
RUSSELL_DAYS = ("2016-06-24", "2017-06-23", "2018-06-22", "2019-06-28", "2020-06-26", "2021-06-25", "2022-06-24", "2023-06-23", "2024-06-28", "2025-06-27")     # [E1] the lead's list from FTSE Russell's annual calendars: the fourth Friday of June each year
CAL_CSV = os.environ.get("EDGELOG_EDGAR_CALENDAR", r"C:\EdgeLog\_research_cache\edgar\earnings_calendar_ndx.csv")           # [E5'] TV's EDGAR earnings calendar (the file the registered sha256 names)
CAL_SHA = "8f4f9f4bc61dc671a6f169f37f72c334fa3aecafff87a06af5ab250bcc85d4db"                                                   # [E5'] sha256 of the file's BYTES (refused if different)
CAL_COLS = ("ticker", "ndx_tickers", "reaction_session")                 # the columns this file reads of TV's calendar (it also holds cik, name, form, accepted_et, timing, items, accession)
MEMBERS_CSV = os.path.join(os.path.dirname(HERE), "data", "ndx_members.csv")       # the point-in-time Nasdaq-100 members file (ticker, from, to): its tickers the calendar does not hold are the foreign 6-K filers [E5']
EARN_MONTHS = ((1, 4, 7, 10), (1, 2, 4, 5, 7, 8, 10, 11))                # the 'four earnings months after quarter-ends': the first month after each quarter end (the main reading) and, beside it, the first two (a REPORTED variant)
CHECK_BOOK = True        # refuse to judge if the #463 records / the DD structure / the cache manifest / the reference do not reproduce the registered facts; a real run always checks (only smoke() may switch it)
HYG = M17.HYG            # the four data-hygiene reasons [T2]
AUD = M17.AUD            # the tag of this harness's rows in World.aud_hit (r17_resmom's: its unused_audit_rows reads it)
GO_FLAG, READ_FLAG = "edrift_stageB_GO.flag", "edrift_stageB_READ.flag"     # Stage B needs the lead's go-flag; the one-shot read flag is written (exclusively) after every load and check
RULES = M17.RULES        # Stage A (a) - (e) and Stage B's leg veto are r17_resmom's own (the booleans are switches only smoke() ever turns off)


# ------------------------------------------------------------------ guards: the prereg, the stamp, the cut, the files
def refuse(msg):
    raise SystemExit(msg)


assert_cut, peak_mb, patched, ceil_pct = A13.assert_cut, A13.peak_mb, A13.patched, A13.ceil_pct
file_sha, manifest_sha, book_checks = M17.file_sha, M17.manifest_sha, M17.book_checks      # module-level names, so a test can stub them


def prereg_ok():
    """the frozen spec this file implements must still be the registered one (a changed spec = a new file, r2): a missing or changed file refuses every stage. Also checked against the committed blob when there is one
    (r15_ddw.committed_state, pointed at this file's names for the call); until it is committed that is printed (the lead commits before the real run) and recorded in the Stage A file"""
    if not os.path.exists(PREREG):
        refuse("refused: PREREG_EDRIFT_R1.txt is not next to this file - the spec cannot be verified (nothing computed, lockbox NOT read)")
    if R11.sha_lf(PREREG) != PREREG_SHA:
        refuse("refused: PREREG_EDRIFT_R1.txt DIFFERS from the registered one - a changed spec is a new file, r2 (nothing computed, lockbox NOT read)")
    with patched(D15, PREREG=PREREG, PREREG_SHA=PREREG_SHA):
        st = D15.committed_state()
    if st == "differs":
        refuse("refused: the COMMITTED PREREG_EDRIFT_R1.txt differs from the registered sha - the file on disk is not the file in git (nothing computed, lockbox NOT read)")
    print("prereg check: PREREG_EDRIFT_R1.txt sha256 matches the registered one; committed blob: " + {"match": "matches too", "untracked": "NOT COMMITTED YET - commit it before the real run",
                                                                                                      "unknown": "git not available here (not checked)"}[st])
    return {"verified": True, "committed": st}


def stamp():
    """the version a stage ran with: this file's LF sha256 + r17_resmom's and r18_divrun's + every harness they import numbers from (r15's data layer / marks / statistics, r5_siporb's Data / read_long, r11's book and stats, r12's DO / rho_dd, r13's helpers) + the pinned wide
    calendar's sha + the pinned earnings calendar's sha + the Russell list + the shared half-day list; Stage B refuses on any change, so a change to any of them after Stage A sends it through Stage A again"""
    s7, s8 = M17.stamp(), DV.stamp()
    return {"harness_sha256": R11.sha_lf(os.path.abspath(__file__)), "r17_sha256": s7["harness_sha256"], "r18_sha256": s8["harness_sha256"], **{k: v for k, v in s7.items() if k != "harness_sha256"},
            "earnings_calendar_sha256": CAL_SHA, "russell_days": list(RUSSELL_DAYS)}


@contextlib.contextmanager
def spec(**kw):
    """swap SPEC entries (this file's) and r17_resmom.SPEC entries (the regression / formation windows, the sides, the size) for a block and put them back (the self-tests and the smoke shrink the windows and the sides; nothing stays patched)"""
    mine, theirs = {k: v for k, v in kw.items() if k in SPEC}, {k: v for k, v in kw.items() if k not in SPEC}
    old = dict(SPEC)
    SPEC.update(mine)
    try:
        with M17.spec(**theirs):
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
    return DV.jyear(d)


# ------------------------------------------------------------------ [E1] the mechanical volume days, listed date by date
def third_friday(year, month):
    """the third Friday of a month (a Timestamp)"""
    d = TS(year=year, month=month, day=1)
    return d + pd.Timedelta(days=(4 - d.dayofweek) % 7 + 14)


def mech_days(days, russell=None):
    """[E1] -> (tf, ru), each (T,) bool on the sessions `days`: tf = the third Friday of March, June, September and December (CHOICE: a third Friday that is not a session - the expiry moves to the Thursday - is the last session on / before it, within 4 calendar
    days; none of 2016 .. 2025 is one), ru = the Russell reconstitution days the lead listed (RUSSELL_DAYS: the fourth Friday of June each year). A date outside the data is not placed"""
    d = pd.DatetimeIndex(days)
    tf, ru = np.zeros(len(d), bool), np.zeros(len(d), bool)
    if len(d):
        for y in range(d[0].year, d[-1].year + 1):
            for m in THIRD_FRIDAY_MONTHS:
                t = third_friday(y, m)
                if t < d[0] or t > d[-1]:
                    continue
                i = int(d.searchsorted(t, side="right")) - 1
                if i >= 0 and (t - d[i]).days <= 4:
                    tf[i] = True
        for s_ in (RUSSELL_DAYS if russell is None else russell):
            i = d.get_indexer([TS(s_)])[0]
            if i >= 0:
                ru[i] = True
    return tf, ru


def check_russell(days, listed=None):
    """[E1] the lead's Russell list, asserted against the data: each date a Friday and, when the data covers it, a session of the data; and (CHOICE) a year whose June the data covers (from June 1 to June 28 at least) with no listed date refuses - the lockbox year's
    2026 date is not in the lead's list, so Stage B refuses until a dated addendum extends it"""
    listed = RUSSELL_DAYS if listed is None else listed
    d = pd.DatetimeIndex(days)
    tail = "(nothing computed, lockbox NOT read)"
    for s_ in listed:
        t = TS(s_)
        if t.dayofweek != 4:
            refuse(f"refused: the listed Russell reconstitution day {s_} is not a Friday {tail}")
        if len(d) and d[0] <= t <= d[-1] and t not in d:
            refuse(f"refused: the listed Russell reconstitution day {s_} is not a session of the data {tail}")
    if len(d):
        for y in range(d[0].year, d[-1].year + 1):
            if d[0] <= TS(f"{y}-06-01") and d[-1] >= TS(f"{y}-06-28") and not any(TS(s_).year == y for s_ in listed):
                refuse(f"refused: the data covers June {y} and the lead's Russell list has no date for it - a dated addendum extends the list before any number {tail}")
    return True


# ------------------------------------------------------------------ the events: the volume rule, [E1], the hygiene guard, the reaction's inputs
def attach_events(W, counts_only=False, tf=None, ru=None):
    """the EVENT arrays of a World (W.ed), every one a function of sessions t-21 .. t+1 only and of NO rank date. Volume is the SPLIT-ADJUSTED volume (CHOICE: raw volume x F - F is raw / split-adjusted open, 2 before a 2-for-1 - so a split inside the baseline window
    is not news; the prereg says 'volume'). An event of the cell with multiple K on session t: the volume on t >= K x the mean of the name's volumes over t-21 .. t-2 with at least 15 of those 20 sessions present (a baseline of zero is no baseline); [E1] t is not a third Friday of
    March / June / September / December or a listed Russell day, nor the session after one; no hygiene flag on any of t-1 .. t+1 (the four reasons: registered split, gap scan, TBIS, a +-50% raw gap); and (CHOICE) the split-safe TOTAL return and ES's return are defined on
    each of t-1 .. t+1 (the reaction needs all three - a missing close, an ES hole or a [D2] spin-off / stock-dividend ex-date session voids the event). The first reason that removes a volume event is counted: [E1] -> hygiene -> no data. counts_only: nothing is summed - the 3-day
    windows are tested for the existence of their returns only (R3 / M3 stay None) - the dryload's reading; the event sets are identical either way. -> W.ed with EV[cell] (T, S) bool, flag3, ok3, R3, M3, Va, bsum, bn, excl and the counts by year"""
    sp = SPEC
    T, S_ = W.T, W.S
    days = pd.DatetimeIndex(W.days)
    if tf is None or ru is None:
        tf, ru = mech_days(days)
    Va = np.asarray(W.Vv, float) * np.asarray(W.F, float)
    fin = np.isfinite(Va)
    c1 = np.zeros((T + 1, S_))
    np.cumsum(np.where(fin, Va, 0.0), axis=0, out=c1[1:])
    cn = np.zeros((T + 1, S_), np.int32)
    np.cumsum(fin, axis=0, dtype=np.int32, out=cn[1:])
    lo_, hi_ = sp["base_lo"], sp["base_hi"]
    bsum, bn = np.full((T, S_), np.nan), np.zeros((T, S_), np.int32)
    if T > lo_:
        bsum[lo_:] = c1[lo_ - hi_ + 1:T - hi_ + 1] - c1[0:T - lo_]                         # rows t-21 .. t-2 of every session t >= 21
        bn[lo_:] = cn[lo_ - hi_ + 1:T - hi_ + 1] - cn[0:T - lo_]
    flag3 = np.ones((T, S_), bool)                                                         # a window without all three sessions (the first and last rows) is no event window
    if T >= 3:
        f3 = np.zeros((T - 2, S_), bool)
        for h in W.hcs:
            f3 |= (h[3:T + 1] - h[0:T - 2]) > 0                                            # any hygiene reason on rows t-1 .. t+1
        flag3[1:T - 1] = f3
    Rd, es = np.asarray(W.Rd, float), np.asarray(W.es.ret, float)
    fr, fm = np.isfinite(Rd), np.isfinite(es)
    fin3 = np.zeros((T, S_), bool)
    m3f = np.zeros(T, bool)
    if T >= 3:
        fin3[1:T - 1] = fr[:-2] & fr[1:-1] & fr[2:]
        m3f[1:T - 1] = fm[:-2] & fm[1:-1] & fm[2:]
    ok3 = fin3 & m3f[:, None]
    R3, M3 = None, None
    if not counts_only:
        R3, M3 = np.full((T, S_), np.nan), np.full(T, np.nan)
        if T >= 3:
            R3[1:T - 1] = Rd[:-2] + Rd[1:-1] + Rd[2:]
            M3[1:T - 1] = es[:-2] + es[1:-1] + es[2:]
    prev = lambda a: np.r_[False, a[:-1]]
    kinds = (("third_friday", tf), ("session_after_third_friday", prev(tf)), ("russell_day", ru), ("session_after_russell_day", prev(ru)))
    excl = tf | ru | prev(tf) | prev(ru)
    yrs = days.year.to_numpy()
    ev = SimpleNamespace(EV={}, flag3=flag3, ok3=ok3, R3=R3, M3=M3, Va=Va, bsum=bsum, bn=bn, excl=excl, tf=tf, ru=ru, counts={}, counts_only=bool(counts_only))
    by_year = lambda m: {int(y): int(v) for y, v in pd.Series(m.sum(axis=1)).groupby(yrs).sum().items()}
    for c in CELLS:
        with np.errstate(invalid="ignore"):
            rule = fin & (bn >= sp["base_min"]) & (bsum > 0) & (Va * bn >= KS[c] * bsum)       # cross-multiplied: no division, no rounded ratio at the threshold
        ex_ = rule & excl[:, None]
        hy_ = rule & ~excl[:, None] & flag3
        nd_ = rule & ~excl[:, None] & ~flag3 & ~ok3
        ev.EV[c] = rule & ~excl[:, None] & ~flag3 & ok3
        cn_ = {"volume": by_year(rule), "excluded": by_year(ex_), "void_hygiene": by_year(hy_), "void_data": by_year(nd_), "valid": by_year(ev.EV[c])}
        left = np.ones(T, bool)
        for nm, kmask in kinds:                                                            # the first kind of exclusion each excluded event falls under, in this order
            m = ex_ & (kmask & left)[:, None]
            cn_["excluded_" + nm] = by_year(m)
            left &= ~kmask
        ev.counts[c] = cn_
    W.ed = ev
    return ev


# ------------------------------------------------------------------ the rebalance: the pool (r17_resmom's), the event scores, the sides
def ed_beta(W, r, uni):
    """each name's beta at the rank close r = the slope of the OLS (an intercept and a slope) of its split-safe TOTAL daily return on ES's over the regression window r-251 .. r - r17_resmom.rm_scores' own arithmetic, which returns the residual score and not the beta (the
    selftest rebuilds RES from this beta). NaN where the window has no ES variation"""
    a = M17.windows(r)[0]
    R = W.Rd[a:r + 1][:, uni]
    m = np.asarray(W.es.ret[a:r + 1], float)
    ok = np.isfinite(R) & np.isfinite(m)[:, None]
    with np.errstate(invalid="ignore", divide="ignore"):
        n = np.maximum(ok.sum(axis=0), 1)
        my, mm = np.where(ok, R, 0.0).sum(axis=0) / n, np.where(ok, m[:, None], 0.0).sum(axis=0) / n
        dy, dm = np.where(ok, R - my, 0.0), np.where(ok, m[:, None] - mm, 0.0)
        return (dm * dy).sum(axis=0) / (dm * dm).sum(axis=0)


def side_n(n):
    """the number of names a side holds when n names are scored: 50 at 150 or more; fewer: the top / bottom THIRD (CHOICE: n // 3, so the sides never touch) when that is at least 20, else nothing -> (names a side, 'top' | 'third' | 'none')"""
    if n >= SPEC["min_scored"]:
        return M17.SPEC["n_side"], "top"
    k = n // 3
    return (k, "third") if k >= SPEC["min_side"] else (0, "none")


def pick_sides(cols, score, k):
    """the k longs and k shorts among scored names: ONE ascending order by (score, symbol order) - the shorts are its first k, the longs its last k (so a tie goes to the lower symbol on the short side and to the higher symbol on the long side, and the sides never
    share a name when 2k <= n) -> (long positions, short positions) into the arrays given"""
    o = np.lexsort((np.asarray(cols), np.asarray(score, float)))
    return o[::-1][:k], o[:k]


def cell0():
    """an empty cell record of a rebalance"""
    z = np.zeros(0, np.int64)
    return SimpleNamespace(idx=z, score=np.zeros(0), tstar=z, age=z, n=0, k=0, mode="none", traded=False, long=z, short=z, U=None, ph=None)


def slice_units(U, idx):
    """r17_resmom's unit paths of the whole pool cut to the rows `idx` (a cell's scored names)"""
    out = SimpleNamespace(G=U.G[idx], ve=U.ve[idx], st=U.st[idx], mk=U.mk[idx], div=U.div[idx])
    if getattr(U, "xc", None) is not None:
        out.xc = U.xc[idx]                                                      # [HYG-S1] each position's exit column (a position closed before a spin-off / stock-dividend ex-date exits on its close's row)
    return out


def placebo_values(W, cell, r, cols, beta):
    """[E2] (len(cols), look): the placebo score of each name in each of the look sessions s = r-1-m (column m = 0 .. look-1) of the same lookback - the abnormal return over the 3-session window s-1 .. s+1, R3 - beta x M3, when that window is a NON-event one: the name has no
    valid event of the cell on any session s-3 .. s+3 that precedes the rank close (CHOICE: 'no event day within 2 sessions of it' read as of any session of the window - the stricter of the two readings - and only event days before r count: the rule never looks past the
    rank close), no hygiene flag on s-1 .. s+1 and all three returns and ES's defined; NaN otherwise"""
    sp, E = SPEC, W.ed
    look, near = sp["look"], sp["pl_near"]
    n = len(cols)
    s_rows = r - 1 - np.arange(look)
    lo0 = r - look - near
    EVw = E.EV[cell][lo0:r][:, cols]                                                      # rows lo0 .. r-1
    cs = np.zeros((EVw.shape[0] + 1, n), np.int32)
    np.cumsum(EVw, axis=0, dtype=np.int32, out=cs[1:])
    i_s = s_rows - lo0
    hi = np.minimum(i_s + near, EVw.shape[0] - 1)
    blocked = (cs[hi + 1] - cs[i_s - near]) > 0                                           # (look, n)
    ok = ~E.flag3[s_rows][:, cols] & E.ok3[s_rows][:, cols] & ~blocked
    with np.errstate(invalid="ignore"):
        val = E.R3[s_rows][:, cols] - np.asarray(beta, float)[None, :] * E.M3[s_rows][:, None]
    return np.where(ok, val, np.nan).T


POST_MODES = ("remove", "naive", "close")                                       # ed_one's in-hold readings: 'remove' the registered (look-ahead), 'naive' [O3], 'close' [HYG-S1] (r17_resmom's 'keep' is not run by this family)


def ed_one(W, r, f, x, post_mode, units=True, counts_only=False, keep_ph=False, seen=None, cover=None):
    """one rebalance: the universe at the fill session f (sessions < f only), the pool of r17_resmom's rm_one (the same removals in the same order - short history, no ES pairs, no fill, the pre / old / post hygiene windows, the [D2] spin-offs, the hand audit; CHOICE: 'no score'
    becomes 'no beta', since a name's score exists per cell), then per cell the SCORE = the reaction of the name's most recent valid event on rows r-63 .. r-1, none -> no score; the scored names are the cell's pool for the null and the picks: both sides always 50 names at 150 or
    more scored names, else the top / bottom third (at least 20 a side) or nothing (side_n). Ties: one ascending order by (score, symbol order); the shorts are its first k, the longs its last k. post_mode as r17_resmom's ('remove' = the registered reading, 'naive' = the look-ahead
    one; 'close' = [HYG-S1], MANAGER's hygiene edit S1 (#127, 2026-10-07; r17_resmom's post_mode 'close'): NO in-hold event removes a name - the pool is the look-ahead reading's, every name flagged inside the hold stays on the split-safe path (a registered or
    calendar split rides the split-adjusted series) - and a [D2] spin-off / stock-dividend ex-date e in f < e <= x CLOSES the position at the official close of the session before it, e-1 (rec.close = that row per pool name, -1 = held to the exit; M17.rm_units cuts the path,
    M17.l1_pnl_x books the exit there). Counted: kept_<reason>, kept_flagged, kept_calendar_split (when the calendar's splits are on the grid), closed_spin - over the pool, whatever the names score). counts_only: no regression, no reaction, no score - the pools and the scored sets are counted from the existence of events and returns (the dryload). seen / cover: (T, S) bool accumulators the caller keeps (events inside the windows of pool names / every window row of a pool name)"""
    if post_mode not in POST_MODES:
        raise ValueError(f"post_mode {post_mode!r}: one of {POST_MODES}")
    s, E = M17.SPEC, W.ed
    look = SPEC["look"]
    uni = np.flatnonzero(W.U[f])
    rec = SimpleNamespace(r=r, f=f, x=x, nu=len(uni), nfull=0, traded=False, pool=np.zeros(0, np.int64), naive=np.zeros(0, bool), spin_win=np.zeros(0, np.int64), spin_hold=np.zeros(0, bool), res=np.zeros(0), beta=np.zeros(0),
                          cell={c: cell0() for c in CELLS}, close=np.zeros(0, np.int64))
    cnt = Counter()
    cnt["rebalances"] += 1
    cnt["universe"] += len(uni)
    if not len(uni):
        cnt["empty"] += 1
        return rec, cnt
    a = M17.windows(r)[0]
    if counts_only:
        fr = np.isfinite(W.Rd[a:r + 1][:, uni])
        n_ret, n_pair = fr.sum(axis=0), (fr & np.isfinite(W.es.ret[a:r + 1])[:, None]).sum(axis=0)
        res, beta = None, None
    else:
        n_ret, n_pair, res, _raw = M17.rm_scores(W, r, uni)
        beta = ed_beta(W, r, uni)
    short_hist = n_ret < s["min_n"]
    no_es = ~short_hist & (n_pair < s["min_n"])
    rec.nfull = int((~short_hist & ~no_es).sum())
    m_fill = np.isfinite(W.Ao[f, uni])                                          # CHOICE (r17_resmom's): a name with no open (or no factor) at the fill session cannot be filled
    no_beta = np.zeros(len(uni), bool) if counts_only else ~np.isfinite(beta)
    lo_pre = r - s["skip"] - s["hyg_lead"] + 1
    pre = W.hyg(lo_pre, r, uni)                                                 # all four reasons, sessions r-25 .. r (r17_resmom's windows: 'hygiene exactly as RESMOM')
    old = W.hyg(a, lo_pre - 1, uni)[1:]                                         # gap, tbis, jump on sessions r-251 .. r-26
    post = W.hyg(r + 1, x, uni)                                                 # all four, inside the hold
    post_sp = M17.spn_hit(W, f + 1, x, uni)                                     # [D2] a spin-off / stock-dividend ex-date in f < t <= x
    post_cs = M17.csplit_hit(W, f + 1, x, uni) if post_mode == "close" and getattr(W, "cscs", None) is not None else np.zeros(len(uni), bool)     # [HYG-S1] an announced (calendar) split ex-date in f < t <= x: counted, never a removal
    win = (W.SPN[a:r + 1][:, uni] & np.isfinite(W.Rn[a:r + 1][:, uni])).sum(axis=0)
    pre_any, old_any, post_any = pre.any(axis=0), old.any(axis=0), post.any(axis=0) | post_sp
    aud = W.aud1[f, uni]
    W.aud_hit.update((AUD, f, int(c)) for c in uni[aud])
    reasons = [("short_history", short_hist), ("no_es_pairs", no_es), ("no_fill", ~m_fill), ("no_beta", no_beta)]
    reasons += [(f"pre_{h}", pre[q]) for q, h in enumerate(HYG)] + [(f"old_{h}", old[q]) for q, h in enumerate(HYG[1:])]
    if post_mode == "remove":
        reasons += [(f"post_{h}", post[q]) for q, h in enumerate(HYG)] + [("post_spin", post_sp)]
    D15.tally(cnt, reasons + [("audit", aud)], D15.attribute(reasons + [("audit", aud)], len(uni)))
    cnt["spin_window_names"] += int((win > 0).sum())
    cnt["spin_window_sessions"] += int(win.sum())
    cnt["spin_hold_names"] += int(post_sp.sum())
    pool_k = ~short_hist & ~no_es & m_fill & ~no_beta & ~pre_any & ~old_any & ~aud
    pool = (pool_k & ~post_any) if post_mode == "remove" else pool_k
    if post_mode == "naive":
        cnt["kept_naive"] += int((pool & post_any).sum())
    if post_mode == "close":                                                    # [HYG-S1] the pool names with an in-hold event that STAY: flagged ones and the calendar's splits on the split-safe path, a [D2] ex-date closes the position at the close before it
        for q, h in enumerate(HYG):
            cnt[f"kept_{h}"] += int((pool & post[q]).sum())
        cnt["kept_flagged"] += int((pool & post.any(axis=0)).sum())
        cnt["kept_calendar_split"] += int((pool & post_cs).sum())
        cnt["closed_spin"] += int((pool & post_sp).sum())
    pidx = np.flatnonzero(pool)
    cols = uni[pidx]
    rec.pool = cols
    rec.naive = post_any[pidx] if post_mode == "naive" else np.zeros(len(pidx), bool)
    rec.spin_win, rec.spin_hold = win[pidx], post_sp[pidx]
    rec.close = np.full(len(pidx), -1, np.int64)                                 # [HYG-S1] the row each pool name closes on: the session before its first [D2] ex-date in f < e <= x (-1 = held to the exit session)
    if post_mode == "close" and x > f and len(pidx):
        sp_h = W.SPN[f + 1:x + 1][:, cols]
        rec.close = np.where(sp_h.any(axis=0), f + sp_h.argmax(axis=0), -1).astype(np.int64)
    if not counts_only:
        rec.res, rec.beta = res[pidx], beta[pidx]
    if len(cols) and cover is not None:
        cover[np.ix_(np.arange(r - look, r), cols)] = True
    for c in CELLS:
        cc = rec.cell[c]
        if not len(cols):
            cnt[f"mode_{c}_none"] += 1                                              # an empty pool trades nothing (counted with the other fallback months)
            continue
        wv = E.EV[c][r - look:r][:, cols]                                       # (63, n): rows r-63 .. r-1
        has = wv.any(axis=0)
        kk = wv[::-1].argmax(axis=0)                                            # the most recent event: row r-1-kk
        sc = np.flatnonzero(has)
        cc.idx, cc.n = sc, int(len(sc))
        cc.tstar, cc.age = (r - 1 - kk[sc]).astype(np.int64), (kk[sc] + 1).astype(np.int64)
        if seen is not None:
            seen[c][np.ix_(np.arange(r - look, r), cols)] |= wv
        cnt[f"scored_{c}"] += cc.n
        cnt[f"no_event_{c}"] += int(len(cols) - cc.n)
        cc.k, cc.mode = side_n(cc.n)
        cnt[f"mode_{c}_{cc.mode}"] += 1
        if counts_only:
            cc.traded = cc.k > 0
            continue
        with np.errstate(invalid="ignore"):
            cc.score = E.R3[cc.tstar, cols[sc]] - rec.beta[sc] * E.M3[cc.tstar]       # the reaction of the most recent valid event
        if cc.k > 0:
            cc.long, cc.short = pick_sides(cols[sc], cc.score, cc.k)              # ascending score, ties by symbol order: the k lowest are the shorts, the k highest the longs
            cc.traded = True
        if keep_ph and cc.n:
            cc.ph = placebo_values(W, c, r, cols[sc], rec.beta[sc])
    rec.traded = any(rec.cell[c].traded for c in CELLS)
    if units and rec.traded:
        rec.U = M17.rm_units(W, f, x, rec.pool, rec.naive, rec.close)
        for c in CELLS:
            if rec.cell[c].traded:
                rec.cell[c].U = slice_units(rec.U, rec.cell[c].idx)
    return rec, cnt


def ed_build(W, lo, hi, post_mode="remove", units=True, drop=None, counts_only=False, keep_ph=False):
    """every rebalance whose position EXITS inside [lo, hi] with a full 252-session window (r17_resmom.rm_build's rules: the stretch by exit session, warm-up counted, a position whose exit is past the stage's data unresolved - out of the cell AND the null) -> Leg(kind, recs, cnt by fill
    year, seen = the events inside the windows of pool names per cell, cover = every window row of a pool name). drop = rank sessions (dates) left out of the leg - out of the cell AND the null (the [D1] reported row)"""
    r_all, f_all, x_all = M17.rm_schedule(W.days)
    drop_rows = {int(i) for i in W.days.get_indexer(pd.DatetimeIndex(drop)) if i >= 0} if drop is not None and len(drop) else set()
    recs, cnt = [], defaultdict(Counter)
    seen, cover = {c: np.zeros((W.T, W.S), bool) for c in CELLS}, np.zeros((W.T, W.S), bool)
    for r, f, x in zip(r_all.tolist(), f_all.tolist(), x_all.tolist()):
        y = int(W.days[f].year)
        if x < 0:
            cnt[y]["unresolved"] += 1
            continue
        if not (lo <= W.days[x] <= hi):
            continue
        if r < M17.SPEC["win"] - 1:
            cnt[y]["warmup"] += 1
            continue
        if r in drop_rows:
            cnt[y]["dropped_d1"] += 1
            continue
        rec, c = ed_one(W, r, f, x, post_mode, units, counts_only, keep_ph, seen, cover)
        recs.append(rec)
        cnt[y].update(c)
    return SimpleNamespace(kind="ED", recs=recs, cnt=cnt, seen=seen, cover=cover)


def cell_leg(L, cell):
    """one cell's view of a Leg in the shape r15's L1 engine reads (rec.sig = the cell's score on ITS scored pool, rec.pool = the scored names, rec.long / rec.short = its picks on that pool, rec.U = their unit paths): l1_cell and r17_resmom's run_cell run on it unchanged"""
    recs = []
    for rec in L.recs:
        cc = rec.cell[cell]
        v = SimpleNamespace(r=rec.r, f=rec.f, x=rec.x, traded=cc.traded, pool=rec.pool[cc.idx], naive=rec.naive[cc.idx], nu=rec.nu, sig=cc.score, long=cc.long, short=cc.short)
        if cc.traded and cc.U is not None:
            v.U = cc.U
        recs.append(v)
    return SimpleNamespace(kind="L1", recs=recs, cnt=L.cnt)


# ------------------------------------------------------------------ the nulls: RANDOM NAMES (registered) and the PLACEBO IN TIME ([E2], reported)
def ed_null(W, L, nreps, vcode=0):
    """the family-aware null [prereg NULL]: per draw and per rebalance the cell traded, its k longs and k shorts are replaced by the same number of names drawn uniformly without replacement from that rebalance's eligible SCORED pool (the same hygiene, sizing, fills, costs, borrow);
    each cell has its own random stream (seeds [20261005, cell, vcode]), so the MAX over the 2 cells is the better of two independent random books. r15's null_l1 draws a fixed 50 - the sides here are 50 or a third - so the draw is written out (the same draw_order, l1_pnl and
    sizing; [HYG-S1] r17_resmom's l1_pnl_x = r15's l1_pnl for every path but a closed one, whose exit cost it books on the close's row). -> {cell: (nreps, T) P&L by stock session}"""
    slot, cfg = M17.SPEC["slot"], D15.l1_cfg()
    acc = {}
    for q, c in enumerate(CELLS):
        rng = np.random.default_rng([SEED, q, vcode])
        a = np.zeros((nreps, W.T))
        for rec in L.recs:
            cc = rec.cell[c]
            if not cc.traded:
                continue
            idx, kt = np.arange(cc.n), W.k[rec.f:rec.x + 1]
            PL, PS = M17.l1_pnl_x(cc.U, idx, 1, cfg, kt), M17.l1_pnl_x(cc.U, idx, -1, cfg, kt)
            o = D15.draw_order(rng, nreps, cc.n, 2 * cc.k)
            a[:, rec.f:rec.x + 1] += slot * (PL[o[:, :cc.k]].sum(axis=1) + PS[o[:, cc.k:]].sum(axis=1))
        acc[c] = a
    return acc


def placebo_picks(ph, k, rng, nreps):
    """one rebalance of the placebo null for one cell: each scored name takes its score from a uniformly drawn valid placebo window of its own (ph (n, look), NaN = not a placebo window), nreps draws at once; a draw ranks the names that have one by (placebo score, symbol order)
    and takes the k highest as longs and the k lowest as shorts -> (longs (k, nreps), shorts (k, nreps), tradable (nreps,)); a draw with fewer than 2k names that have a window does not trade this rebalance (counted by the caller)"""
    n = ph.shape[0]
    valid = np.isfinite(ph)
    cnt = valid.sum(axis=1)
    order = np.argsort(~valid, axis=1, kind="stable")                                   # the valid windows of each name first
    pick = np.minimum((rng.random((n, nreps)) * cnt[:, None]).astype(np.int64), np.maximum(cnt[:, None] - 1, 0))
    val = ph[np.arange(n)[:, None], order[np.arange(n)[:, None], pick]]                 # (n, nreps): NaN for a name with no window
    fin = np.isfinite(val)
    nfin = fin.sum(axis=0)
    asc = np.argsort(val, axis=0, kind="stable")                                        # ascending, NaN last, ties by symbol order
    shorts = asc[:k]
    longs = np.take_along_axis(asc, np.maximum(nfin[None, :] - 1 - np.arange(k)[:, None], 0), axis=0)
    return longs, shorts, nfin >= 2 * k


def ed_placebo_null(W, L, nreps, vcode=0):
    """[E2] the PLACEBO IN TIME (REPORTED; the registered null stays the random-name one): every scored name keeps its rank date but takes its score from a random NON-event 3-session window inside the same 63-session lookback (no event day within 2 sessions of it), 500 draws,
    seed 20261006 (one stream per cell, [20261006, cell, vcode]); the picks are the same size, sizing, fills, costs and borrow as the cell's. -> ({cell: (nreps, T) P&L by stock session}, {cell: {'draws_not_trading': per rebalance mean, 'names_without_a_window': mean share}})"""
    slot, cfg = M17.SPEC["slot"], D15.l1_cfg()
    acc, info = {}, {}
    for q, c in enumerate(CELLS):
        rng = np.random.default_rng([SEED_PLACEBO, q, vcode])
        a = np.zeros((nreps, W.T))
        skipped, nowin, trades, names = 0.0, 0, 0, 0
        for rec in L.recs:
            cc = rec.cell[c]
            if not cc.traded:
                continue
            if cc.ph is None:
                raise ValueError("the leg was built without the placebo windows (keep_ph)")
            idx, kt = np.arange(cc.n), W.k[rec.f:rec.x + 1]
            PL, PS = M17.l1_pnl_x(cc.U, idx, 1, cfg, kt), M17.l1_pnl_x(cc.U, idx, -1, cfg, kt)
            lg, sh, ok = placebo_picks(cc.ph, cc.k, rng, nreps)
            g = slot * (PL[lg].sum(axis=0) + PS[sh].sum(axis=0))                        # (nreps, H)
            g[~ok] = 0.0
            a[:, rec.f:rec.x + 1] += g
            skipped += float((~ok).mean())
            nowin += int((~np.isfinite(cc.ph).any(axis=1)).sum())
            names += cc.n
            trades += 1
        acc[c] = a
        info[c] = {"rebalances": trades, "draw_share_not_trading_mean": skipped / max(trades, 1), "scored_names_without_a_placebo_window_share": nowin / max(names, 1)}
    return acc, info


def null_summary(per_cell, per_cell_do=None, seed=SEED):
    """per_cell {cell: ROC @ $30k of every draw} -> the statistic = the MAX over the 2 cells per draw -> p5 / p50 / p95 (and each cell's own, for the report). per_cell_do {cell: the DO of every draw against the REFERENCE book's drawdown days [X1]} -> the same for the DO: 'do_ref_max' = the
    MAX over the 2 cells per draw, 'do_ref_by_cell' (MANAGER #70's gate basis for the cell's null)"""
    roc = np.fmax.reduce(np.vstack([per_cell[c] for c in CELLS]), axis=0)
    mk = lambda a: {"p5": D15.pctl(a, 5), "p50": D15.pctl(a, 50), "p95": D15.pctl(a, 95), "finite": int(np.isfinite(a).sum())}
    out = {"draws": int(len(roc)), "seed": seed, "roc_max": mk(roc), "by_cell": {c: mk(per_cell[c]) for c in CELLS}}
    if per_cell_do is not None:
        do = np.fmax.reduce(np.vstack([per_cell_do[c] for c in CELLS]), axis=0)
        out.update({"do_ref_max": mk(do), "do_ref_by_cell": {c: mk(per_cell_do[c]) for c in CELLS}})
    return out


# ------------------------------------------------------------------ [E3] / [E5'] - printed BEFORE any P&L
def spearman(a, b):
    """the rank correlation (Pearson on average ranks) of two vectors on the positions where both are finite; NaN under 3 pairs or without spread"""
    a, b = np.asarray(a, float), np.asarray(b, float)
    m = np.isfinite(a) & np.isfinite(b)
    if m.sum() < 3:
        return float("nan")
    ra, rb = pd.Series(a[m]).rank().to_numpy(), pd.Series(b[m]).rank().to_numpy()
    if not (np.ptp(ra) > 0 and np.ptp(rb) > 0):
        return float("nan")
    return float(np.corrcoef(ra, rb)[0, 1])


def e3_report(W, L):
    """[E3] BEFORE ANY P&L: per cell the scores split by event age (rank close minus event session: 1 .. 21 against 22 .. 63 sessions - the drift should decay) - the count of scored names and the mean |score| in each bin, pooled over the WF rebalances and by rank year - and the
    cross-sectional rank correlation of the cell's score with RESMOM's RES score (r17_resmom.rm_scores at the same rank close and universe) at every rebalance with scored names (the literal 'every rebalance'; a month the cell does not trade counts - the number that trade is stored beside it): the mean and the range. Counts and scores of the
    scored names only - no price, no position, no P&L"""
    cut = SPEC["age_cut"]
    out = {}
    for c in CELLS:
        ages, absr, yrs, rho, ntr = [], [], [], [], 0
        for rec in L.recs:
            cc = rec.cell[c]
            if not cc.n:
                continue
            ages.append(cc.age)
            absr.append(np.abs(cc.score))
            yrs.append(np.full(cc.n, int(W.days[rec.r].year)))
            rho.append(spearman(cc.score, rec.res[cc.idx]))                                        # CHOICE: every rebalance with scored names (NaN under 3 pairs: left out), traded or not
            ntr += int(cc.traded)
        age, ab, yr = (np.concatenate(v) if v else np.zeros(0) for v in (ages, absr, yrs))
        yg = age <= cut
        mean = lambda m: float(ab[m].mean()) if m.any() else float("nan")
        o = {"young": {"label": f"1-{cut} sessions", "n": int(yg.sum()), "mean_abs_score": mean(yg)}, "old": {"label": f"{cut + 1}-{SPEC['look']} sessions", "n": int((~yg).sum()), "mean_abs_score": mean(~yg)}, "by_year": {}}
        for y in sorted(set(yr.astype(int).tolist())):
            m = yr == y
            o["by_year"][y] = {"young_n": int((yg & m).sum()), "old_n": int((~yg & m).sum()), "young_mean_abs": mean(yg & m), "old_mean_abs": mean(~yg & m)}
        rv = np.array([v for v in rho if np.isfinite(v)])
        o["rank_corr_with_RES"] = {"rebalances": int(len(rv)), "rebalances_that_trade": int(ntr), "mean": float(rv.mean()) if len(rv) else float("nan"), "min": float(rv.min()) if len(rv) else float("nan"), "max": float(rv.max()) if len(rv) else float("nan")}
        out[c] = o
    return out


def print_e3(e3):
    print("[E3] BEFORE ANY P&L - the scores by event age (rank close minus the event's session) and the rank correlation with RESMOM's RES score:")
    for c in CELLS:
        o = e3[c]
        y, ol = o["young"], o["old"]
        print(f"  {c}: scored names by event age {y['label']}: {y['n']:,}, mean |score| {y['mean_abs_score']:.4f}; {ol['label']}: {ol['n']:,}, mean |score| {ol['mean_abs_score']:.4f} (old / young {ol['mean_abs_score'] / y['mean_abs_score'] if y['mean_abs_score'] else float('nan'):.2f}); "
              + "by rank year (young n / old n, mean |score| young / old): " + "; ".join(f"{yy}: {v['young_n']:,} / {v['old_n']:,}, {v['young_mean_abs']:.4f} / {v['old_mean_abs']:.4f}" for yy, v in o["by_year"].items()))
        rc = o["rank_corr_with_RES"]
        print(f"      rank correlation of the {c} score with RES at every rebalance with scored names ({rc['rebalances']}; {rc['rebalances_that_trade']} of the months trade): mean {rc['mean']:+.3f}, range {rc['min']:+.3f} .. {rc['max']:+.3f}")


def edgar_load(cut, path=None, enforce=True):
    """[E5'] TV's EDGAR earnings calendar -> (frame, info). enforce (Stage A, the smoke): refuses - nothing computed, lockbox NOT read - when the file is not on file, its sha256 (of the bytes) is not the registered CAL_SHA or a column of CAL_COLS is missing; not enforce
    (the dryload): no refusal - a missing file is (None, {'present': False}) and another file is reported (None, ... 'matches': False) and not read. Cut at READ time and only release dates inside the walk-forward stretch are read: a row whose reaction session is not a date in
    [2016-07-01, 2025-06-29] and before `cut` is dropped (counted) and the frame is asserted to hold none. The frame: ticker (EDGAR's current), tickers (the row's ndx_tickers split on ';' - every members-file ticker the company had), rs (the reaction session)"""
    path = path or CAL_CSV
    tail = "(nothing computed, lockbox NOT read)"
    if not os.path.exists(path):
        if enforce:
            refuse(f"refused: TV's EDGAR earnings calendar is not on file ({path}) - [E5'] needs it {tail}")
        return None, {"present": False, "path": path}
    got = M17.sha_raw(path)
    if got != CAL_SHA:
        if enforce:
            refuse(f"refused: the earnings calendar {os.path.basename(path)} (sha256 {got}) is not the registered one ({CAL_SHA}) - the file changed after it was registered {tail}")
        return None, {"present": True, "path": path, "sha256": got, "matches": False}
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    miss = [c for c in CAL_COLS if c not in df.columns]
    if miss:
        refuse(f"refused: the earnings calendar lacks the column(s) {miss} {tail}")
    rs = pd.to_datetime(df["reaction_session"].str.strip(), errors="coerce")
    keep = (rs.notna() & (rs >= WF0) & (rs <= PRE_END) & (rs < TS(cut))).to_numpy()
    fr = pd.DataFrame({"ticker": df["ticker"].str.strip().to_numpy()[keep], "tickers": [[t.strip() for t in str(v).split(";") if t.strip()] for v in df["ndx_tickers"].to_numpy()[keep]], "rs": rs.to_numpy()[keep]})
    fr["rs"] = pd.to_datetime(fr["rs"])
    assert_cut("earnings calendar", fr["rs"], cut)
    info = {"present": True, "path": path, "sha256": got, "matches": True, "rows_on_file": int(len(df)), "rows_read": int(keep.sum()), "rows_not_read": int((~keep).sum()), "companies_read": int(fr["ticker"].nunique()), "first": f"{fr['rs'].min():%Y-%m-%d}" if len(fr) else None,
            "last": f"{fr['rs'].max():%Y-%m-%d}" if len(fr) else None}
    return fr, info


def members_load(cut, path=None):
    """the point-in-time Nasdaq-100 members file (ticker, from, to) -> the set of tickers that were members before `cut` (a row whose `from` is on / after the cut is dropped at read and asserted gone), or None when the file is not on file"""
    p = path or MEMBERS_CSV
    if not os.path.exists(p):
        return None
    df = pd.read_csv(p, dtype=str, keep_default_na=False)
    if not {"ticker", "from"} <= set(df.columns):
        return None
    fr = pd.to_datetime(df["from"].str.strip(), errors="coerce")
    keep = (fr.notna() & (fr < TS(cut))).to_numpy()
    assert_cut("Nasdaq-100 members file", fr[keep], cut)
    return set(df["ticker"].str.strip().to_numpy()[keep].tolist())


def earn_join(W, fr, members=None):
    """[E5'] the join: a cache symbol matches a release when it is one of the release's ndx_tickers; a reaction session that is not in the harness's session list moves to the next session that is (one past the last: dropped). -> (rel_t, rel_j = the reaction session row and cache column of
    every (release, matched symbol) pair, the counts: releases read / matched / moved / dropped, companies matched, the UNMATCHED companies (no ndx_ticker is a cache symbol of the world - listed), the members-file tickers the calendar holds no row of (the foreign 6-K filers - listed))"""
    sym = pd.Index(W.syms.astype(str))
    long = fr.assign(i=np.arange(len(fr))).explode("tickers")
    col = sym.get_indexer(long["tickers"].astype(str)) if len(long) else np.zeros(0, int)
    row = np.asarray(W.days.searchsorted(pd.DatetimeIndex(long["rs"]), side="left")) if len(long) else np.zeros(0, int)
    exact = np.asarray(W.days.get_indexer(pd.DatetimeIndex(long["rs"]))) >= 0 if len(long) else np.zeros(0, bool)
    ok = (col >= 0) & (row < W.T)
    matched_rel = set(long["i"].to_numpy()[col >= 0].tolist())
    comp_all = set(fr["ticker"].tolist())
    comp_hit = set(fr["ticker"].to_numpy()[sorted(matched_rel)].tolist()) if matched_rel else set()
    cal_tickers = {t for ts in fr["tickers"] for t in ts}
    cnt = {"releases_read": int(len(fr)), "releases_matched": int(len(matched_rel)), "pairs_matched": int(ok.sum()), "reaction_session_moved_to_the_next_session": int((ok & ~exact).sum()), "dropped_after_the_last_session": int(((col >= 0) & (row >= W.T)).sum()),
           "companies_read": int(len(comp_all)), "companies_matched": int(len(comp_hit)), "unmatched_companies": sorted(comp_all - comp_hit), "matched_symbols": int(len(set(col[ok].tolist())))}
    if members is not None:
        cnt["members_ticker_not_in_the_calendar"] = sorted(members - cal_tickers)
    return row[ok], col[ok], cnt


def earn_check(W, L, rel_t, rel_j):
    """[E5'] DO THE VOLUME DAYS MARK EARNINGS? REPORTED ONLY, per cell and July-June year: (i) the share of the cell's events (the valid events inside the windows of pool names - L.seen - of the matched symbols, counted once each) whose session t is a release's reaction session
    or the session after it; (ii) the share of the matched symbols' reaction sessions inside the 63-session event windows (L.cover) that carry NO event (CHOICE: the same rule as (i) - an event on the reaction session or the session after it; the stricter one, no event on the reaction
    session itself, is reported beside it). No return, no score, no position"""
    T, S_ = W.T, W.S
    RS = np.zeros((T, S_), bool)
    RS[rel_t, rel_j] = True
    RS1 = RS | np.vstack([np.zeros((1, S_), bool), RS[:-1]])
    M = RS.any(axis=0)
    jy = DV.jyear(W.days)
    by = lambda m: {int(y): int(v) for y, v in zip(*np.unique(jy[np.nonzero(m)[0]], return_counts=True))}
    out = {}
    for c in CELLS:
        EVc = W.ed.EV[c]
        EVn = EVc | np.vstack([EVc[1:], np.zeros((1, S_), bool)])
        ev, hit = L.seen[c] & M[None, :], L.seen[c] & RS1
        rel = RS & L.cover
        carry, strict = rel & EVn, rel & EVc
        o = {"events": by(ev), "events_on_a_release": by(ev & RS1), "releases_in_windows": by(rel), "releases_with_an_event": by(carry), "releases_with_an_event_on_the_session": by(strict)}
        yrs = sorted(set(o["events"]) | set(o["releases_in_windows"]))
        sh = lambda a, b: {y: (a.get(y, 0) / b[y] if b.get(y, 0) else float("nan")) for y in yrs}
        o["share_events_on_a_release"] = sh(o["events_on_a_release"], o["events"])
        o["share_releases_without_an_event"] = {y: (1.0 - v if np.isfinite(v) else float("nan")) for y, v in sh(o["releases_with_an_event"], o["releases_in_windows"]).items()}
        o["share_releases_without_an_event_on_the_session"] = {y: (1.0 - v if np.isfinite(v) else float("nan")) for y, v in sh(o["releases_with_an_event_on_the_session"], o["releases_in_windows"]).items()}
        n_e, n_h, n_r, n_c, n_s = int(ev.sum()), int(hit.sum()), int(rel.sum()), int(carry.sum()), int(strict.sum())
        o["total"] = {"events": n_e, "events_on_a_release": n_h, "share_events_on_a_release": n_h / n_e if n_e else float("nan"), "releases_in_windows": n_r, "releases_with_an_event": n_c,
                      "share_releases_without_an_event": 1.0 - n_c / n_r if n_r else float("nan"), "releases_with_an_event_on_the_session": n_s,
                      "share_releases_without_an_event_on_the_session": 1.0 - n_s / n_r if n_r else float("nan")}
        out[c] = o
    return out


def print_e5(info, cnt, e5=None):
    """[E5'] counts always; the shares when the cells were built (Stage A)"""
    print(f"[E5'] TV's EDGAR earnings calendar {os.path.basename(info['path'])} sha256 {info['sha256'][:16]}... (the registered file); {info['rows_on_file']:,} rows on file, {info['rows_read']:,} read (reaction sessions {info['first']} .. {info['last']}, only dates inside the "
          f"walk-forward stretch; {info['rows_not_read']:,} not read), {info['companies_read']:,} companies; joined on ndx_tickers: {cnt['releases_matched']:,} releases match a cache symbol of the world ({cnt['pairs_matched']:,} release x symbol pairs on {cnt['matched_symbols']:,} symbols; "
          f"{cnt['reaction_session_moved_to_the_next_session']:,} reaction sessions moved to the next session of the harness's list, {cnt['dropped_after_the_last_session']} dropped after its last), {cnt['companies_matched']:,} of {cnt['companies_read']:,} companies matched")
    um = cnt["unmatched_companies"]
    print(f"  unmatched companies ({len(um)}; no ndx_ticker is a symbol the world holds): " + (", ".join(um) if um else "none"))
    if "members_ticker_not_in_the_calendar" in cnt:
        ab = cnt["members_ticker_not_in_the_calendar"]
        print(f"  Nasdaq-100 members-file tickers the calendar holds no release of ({len(ab)}; foreign 6-K filers stay absent - the prereg names 13): " + (", ".join(ab) if ab else "none"))
    if e5 is not None:
        for c in CELLS:
            o = e5[c]
            t = o["total"]
            print(f"  {c}: {t['events']:,} events of matched symbols inside the pool windows, {t['events_on_a_release']:,} ({t['share_events_on_a_release']:.1%}) on a release's reaction session or the session after it; {t['releases_in_windows']:,} matched reaction sessions inside the 63-session windows, "
                  f"{t['releases_in_windows'] - t['releases_with_an_event']:,} ({t['share_releases_without_an_event']:.1%}) with no event on the reaction session or the next ({t['share_releases_without_an_event_on_the_session']:.1%} with none on the reaction session itself); by July-June year (events on a release / events | releases with no event / releases; the session itself in brackets): " + "; ".join(
                      f"{y}-{(y + 1) % 100:02d}: {o['share_events_on_a_release'][y]:.0%} of {o['events'].get(y, 0):,} | {o['share_releases_without_an_event'][y]:.0%} of {o['releases_in_windows'].get(y, 0):,} ({o['share_releases_without_an_event_on_the_session'][y]:.0%})" for y in o["share_events_on_a_release"]))


# ------------------------------------------------------------------ the statistics, the reference, A2
def stat_run(B, rows, run, lo=None, hi=None):
    """r15's cell statistics on one stretch (default WF) of a run's daily series -> (stats, the series on #463's index, the positions held per row)"""
    lo, hi = (WF0 if lo is None else lo), (PRE_END if hi is None else hi)
    xB, cB = D15.to_B(run.x, rows, B.n), D15.to_B(run.cnt, rows, B.n)
    return D15.cell_stats(B, xB, cB, lo, hi, run), xB, cB


def a2_report(B, xB, ref):
    """STAGE A2 (WF) - a REPORT, never a pass route [X1]: the REFERENCE book (#463 + 0.264 x RES) + c x the cell against the reference, c by VOLATILITY on 2017-01-03 .. 2018-12-31 (25% of #463's daily std over those rows / the cell's), 0.5c and 2c reported, the plain #463 + c x the cell a
    reported row; an incremental pass = ROC @ $30k and Sortino both strictly above the reference's. r18_divrun's a2_report with EDRIFT's window"""
    with patched(DV, A2_WIN=A2_WIN, A2_TARGET=A2_TARGET, A2_REPORT=A2_REPORT):
        return DV.a2_report(B, xB, ref)


def sub_run(W, L, run, lo, hi):
    """the same cell-run with the position table cut to the positions of the rebalances that EXIT in [lo, hi] (a sub-period: positions are counted by exit date, as the stretches are; the daily series keeps every row - the statistics cut it by date)"""
    p = run.pos
    if p is None or not len(p.rec):
        return SimpleNamespace(x=run.x, cnt=run.cnt, n_pos=0, n_units=0, pos=SimpleNamespace(pnl=np.zeros(0)))
    dx = np.asarray(W.days)[[L.recs[int(i)].x for i in p.rec]]
    m = (dx >= np.datetime64(lo)) & (dx <= np.datetime64(hi))
    return SimpleNamespace(x=run.x, cnt=run.cnt, n_pos=int(m.sum()), n_units=len({int(i) for i in p.rec[m]}), pos=SimpleNamespace(pnl=np.asarray(p.pnl, float)[m]))


def gate70(c, ref, nul):
    """MANAGER #70's gate basis [X1], REPORTED: the cell's DO on the REFERENCE book's drawdown days beside the random-name null's (the MAX over the 2 cells), and whether the cell's P&L inside the reference's qualifying episodes stays positive without its best one. No pass is decided here"""
    g = {"basis": "the REFERENCE book's drawdown days (MDL r1's episode rule)", "episodes": ref.structure["episodes"], "dd_days": ref.structure["days"], "DO": c["seat_ref"]["DO"], "rho_dd": c["seat_ref"]["rho_dd"], "episode_pnl": c.get("episode_pnl")}
    if nul is not None:
        p = nul["do_ref_max"]
        g.update({"null_do_p5": p["p5"], "null_do_p50": p["p50"], "null_do_p95": p["p95"], "DO_above_null_p95": bool(c["seat_ref"]["DO"] > p["p95"])})
    ep = c.get("episode_pnl")
    if ep:
        g["pnl_without_best_episode"] = float(sum(ep) - max(ep))
        g["positive_without_best_episode"] = bool(sum(ep) - max(ep) > 0)
    return g


def evaluate(W, B, S12, ref, rows, post_mode, nreps, vcode=0, full=False, drop=None):
    """one reading of Stage A on the WF stretch. post_mode 'remove' = the REGISTERED reading (a hygiene flag inside the hold removes the position before the ranking), 'naive' = the look-ahead variant (those positions are kept at their naive raw P&L); both run the same code, so a flip
    between them is the data hygiene's doing; 'close' = [HYG-S1] MANAGER's hygiene edit S1 (no in-hold removal; a spin-off / stock-dividend ex-date closes the position at the close before it; the null draws the same cut paths). nreps > 0 draws the registered null (random names; vcode picks its random streams) and judges (a) - (e); full = also the reports' rows (the sides apart, borrow stress, -100% / shorts at zero, the regime halves) and the REPORTED placebo null [E2].
    drop = rank sessions left out of the leg (the cell AND the null). -> (summary, objects: the leg, each cell's leg view / base run / series / side series)"""
    lo, hi = WF0, PRE_END
    L = ed_build(W, lo, hi, post_mode, drop=drop, keep_ph=bool(full and nreps))
    legs = {c: cell_leg(L, c) for c in CELLS}
    runs, series, side_x, summ = {}, {}, {}, {}
    for cell in CELLS:
        CL = legs[cell]
        base = M17.run_cell(W, CL, D15.l1_cfg(), pos=True)
        st, xB, cB = stat_run(B, rows, base)
        runs[cell], series[cell] = base, (xB, cB)
        at = lambda cfg, CL=CL, **kw: stat_run(B, rows, M17.run_cell(W, CL, cfg, **kw))[0]
        c = {"base": st, "cost0": at(D15.l1_cfg(bps=0.0)), "stress": {f"{b:g} bps": at(D15.l1_cfg(bps=b)) for b in STRESS_BPS}, "seat": D15.seat_measure(S12, xB), "seat_ref": D15.seat_measure(ref.S, xB), "A2": a2_report(B, xB, ref)}
        c["episode_pnl"] = [float(e["cell_pnl"]) for e in D15.episodes_table(ref.S, xB)]
        if full:
            c["sides"] = {}
            for nm, sd in (("long side only", 1), ("short side only", -1)):
                s_, sx, _ = stat_run(B, rows, M17.run_cell(W, CL, D15.l1_cfg(), side=sd))
                c["sides"][nm] = s_
                side_x.setdefault(cell, {})[sd] = sx
            ex = {f"borrow {BORROW_STRESS[0]:.0%} on k>1.5 sessions": D15.l1_cfg(borrow=(BORROW, BORROW_STRESS[0])), f"borrow {BORROW_STRESS[1]:.0%} on k>1.5 sessions": D15.l1_cfg(borrow=(BORROW, BORROW_STRESS[1])),
                  "longs that stop printing valued at -100%": D15.l1_cfg(lose100=True)}
            c["extra"] = {nm: at(cfg) for nm, cfg in ex.items()}
            z0 = {**D15.l1_cfg(), "short0": True}                                         # [R2] r17_resmom's row: a short in a name that stops printing valued at zero
            c["sides"][M17.R2_SIDE] = at(z0, side=-1)
            c["extra"][M17.R2_CELL] = at(z0)
            c["short_stopped"] = {"positions": int(sum(int(rec.cell[cell].U.st[rec.cell[cell].short].sum()) for rec in L.recs if rec.cell[cell].traded)), "short_positions": int(sum(rec.cell[cell].k for rec in L.recs if rec.cell[cell].traded))}
            c["sub"] = {lab: stat_run(B, rows, sub_run(W, L, base, a, b), a, b)[0] for lab, a, b in SUBPERIODS}
        summ[cell] = c
    nul = nulp = None
    if nreps:
        acc = ed_null(W, L, nreps, vcode)
        pc, pdo = {}, {}
        for cell in CELLS:
            pc[cell], pdo[cell] = DV.null_stats(S12, ref.S, acc[cell], rows, B.n)
        nul = null_summary(pc, pdo, SEED)
        if full:
            accp, pinfo = ed_placebo_null(W, L, nreps, vcode)
            qc, qdo = {}, {}
            for cell in CELLS:
                qc[cell], qdo[cell] = DV.null_stats(S12, ref.S, accp[cell], rows, B.n)
            nulp = null_summary(qc, qdo, SEED_PLACEBO)
            nulp["info"] = pinfo
            nulp["real_roc_percentile_by_cell"] = {cell: float(100.0 * np.mean(qc[cell][np.isfinite(qc[cell])] < summ[cell]["base"]["roc"])) if np.isfinite(qc[cell]).any() else float("nan") for cell in CELLS}
            nulp["real_roc_above_p95_by_cell"] = {cell: bool(summ[cell]["base"]["roc"] > nulp["roc_max"]["p95"]) for cell in CELLS}
    for cell in CELLS:
        c = summ[cell]
        if nul is not None:
            c["checks"] = M17.judge_cell(c["base"], c["stress"]["10 bps"]["net"], nul)
            c["PASS"] = bool(all(c["checks"].values()))
        c["gate70"] = gate70(c, ref, nul)
    return {"variant": post_mode, "cells": summ, "null": nul, "placebo": nulp}, SimpleNamespace(legs=L, cell_legs=legs, runs=runs, series=series, side_x=side_x)


# ------------------------------------------------------------------ the reports (never a pass route)
def ed_candidate_rows(W, L, cell, run, tbis_df, status, n=AUDIT_N):
    """the n largest single-name contributors of a cell for the hand audit (r17_resmom.rm_candidate_rows' rows: the largest GAINS with the fill date - the key edrift_audit.csv uses -, exit, side, $, score, the split factor's ratio, the largest raw overnight move, TBIS's rows, the asset
    status, the hygiene reasons; its two formation-window moves are RESMOM's and are left out) + this family's: the event's session, its age at the rank close, its volume multiple over the baseline, its reaction, the beta, the rank date, the raw and split-adjusted move over the
    event's 3-session window (a gap between the two is an unadjusted split)"""
    rows = M17.rm_candidate_rows(W, L, cell, run, tbis_df, status, n)
    p = run.pos
    if not rows:
        return rows
    E = W.ed
    sel = np.argsort(-np.asarray(p.pnl, float), kind="stable")[:n]
    for row, i in zip(rows, sel):
        rec, col = L.recs[int(p.rec[i])], int(p.col[i])
        cc = rec.cell[cell]
        q = int(np.flatnonzero(rec.pool[cc.idx] == col)[0])
        t = int(cc.tstar[q])
        with np.errstate(invalid="ignore", divide="ignore"):
            vm = float(E.Va[t, col] * E.bn[t, col] / E.bsum[t, col])
            raw_mv, adj_mv = float(W.Cl[t + 1, col] / W.Cl[t - 2, col] - 1.0), float(W.Ac[t + 1, col] / W.Ac[t - 2, col] - 1.0)
        for k_ in ("raw_move_formation", "adj_move_formation"):
            row.pop(k_, None)
        row.update({"rank_date": f"{W.days[rec.r]:%Y-%m-%d}", "event": f"{W.days[t]:%Y-%m-%d}", "event_age": int(cc.age[q]), "event_volume_multiple": vm, "reaction": float(cc.score[q]), "beta": float(rec.beta[cc.idx[q]]),
                    "raw_move_event_window": raw_mv, "adj_move_event_window": adj_mv})
    return rows


def ed_turnover(L, cell):
    """turnover per rebalance: the share of each side's names that were not on the same side at the previous traded rebalance (the registered convention charges every position its entry AND exit every month - a name that stays pays it again; the estimate of what that overstates, if only
    the names that change were traded, is 2 x 5 bps x $4,000 per retained name-month - reported, never judged)"""
    prev, rows = None, []
    for rec in L.recs:
        cc = rec.cell[cell]
        if not cc.traded:
            prev = None
            continue
        lg, sh = set(rec.pool[cc.idx[cc.long]].tolist()), set(rec.pool[cc.idx[cc.short]].tolist())
        if prev is not None:
            rows.append((1.0 - len(lg & prev[0]) / len(lg), 1.0 - len(sh & prev[1]) / len(sh), len(lg & prev[0]) + len(sh & prev[1])))
        prev = (lg, sh)
    traded = sum(rec.cell[cell].traded for rec in L.recs)
    if not rows:
        return {"traded_rebalances": int(traded), "transitions": 0}
    a = np.array(rows)
    return {"traded_rebalances": int(traded), "transitions": len(rows), "long_replaced_mean": float(a[:, 0].mean()), "short_replaced_mean": float(a[:, 1].mean()), "replaced_mean": float(a[:, :2].mean()), "replaced_median": float(np.median(a[:, :2].mean(axis=1))),
            "replaced_min": float(a[:, :2].mean(axis=1).min()), "replaced_max": float(a[:, :2].mean(axis=1).max()),
            "cost_saved_if_only_changes_traded_usd_estimate": float(a[:, 2].sum() * M17.SPEC["slot"] * 2 * COST_BPS * 1e-4)}


def ed_div_flows(L, cell):
    """[R1] the dividend cash inside a cell's registered picks over WF, in $: what the longs received and what the shorts paid, and how many positions had one"""
    out = {"long_received": 0.0, "short_paid": 0.0, "long_positions_with_a_dividend": 0, "short_positions_with_a_dividend": 0}
    for rec in L.recs:
        cc = rec.cell[cell]
        if not cc.traded:
            continue
        for key, cnt, idx in (("long_received", "long_positions_with_a_dividend", cc.long), ("short_paid", "short_positions_with_a_dividend", cc.short)):
            tot = cc.U.div[idx].sum(axis=1) if cc.U.div.shape[1] else np.zeros(len(idx))
            out[key] += float(M17.SPEC["slot"] * tot.sum())
            out[cnt] += int((tot > 0).sum())
    return out


def ed_event_stats(W, L, cell):
    """REPORTED: the events of the cell inside the windows of pool names (each event once) by calendar month of the event and per name, and the share of them in the four earnings months after quarter-ends (the first month after each quarter end - January, April, July,
    October; and, a variant, the first two)"""
    t_i, j_i = np.nonzero(L.seen[cell])
    d = W.days[t_i]
    n = len(t_i)
    per = np.bincount(j_i, minlength=W.S)
    per = per[per > 0]
    return {"events": int(n), "by_month": {int(m): int((d.month == m).sum()) for m in range(1, 13)}, "names_with_an_event": int(len(per)), "per_name_mean": float(per.mean()) if len(per) else float("nan"), "per_name_median": float(np.median(per)) if len(per) else float("nan"),
            "per_name_max": int(per.max()) if len(per) else 0, "share_in_earnings_months": float(np.isin(d.month, EARN_MONTHS[0]).mean()) if n else float("nan"), "share_in_first_two_months": float(np.isin(d.month, EARN_MONTHS[1]).mean()) if n else float("nan")}


def ed_event_path(W, L, cell):
    """[X2] the EVENT-TIME PATH: the mean abnormal return (split-safe total return - beta x ES) from t+2 to t+60, in bps, by REACTION decile (decile 1 = the most negative reaction), all years and by July-June year of the event, in event time. The events are those inside the windows
    of pool names, each once, taken at the FIRST rebalance whose window holds it with the name in its pool (CHOICE: that rebalance's beta - the beta of the rank close, as the score uses - and the cell's own events); the deciles are cut over all events pooled (CHOICE). Also the mean over
    events of the SIGNED cumulative path (the sign of the reaction x the abnormal return, t+2 .. t+60): the drift in the direction of the news, and the top-minus-bottom decile spread by year"""
    E, look = W.ed, SPEC["look"]
    lo_t, hi_t = SPEC["path_lo"], SPEC["path_hi"]
    taus = np.arange(lo_t, hi_t + 1)
    claimed = np.zeros((W.T, W.S), bool)
    tt, jj, bb = [], [], []
    for rec in L.recs:
        if not len(rec.pool):
            continue
        rows_ = np.arange(rec.r - look, rec.r)
        ix = np.ix_(rows_, rec.pool)
        new = E.EV[cell][ix] & ~claimed[ix]
        ti, ji = np.nonzero(new)
        tt.append(rec.r - look + ti)
        jj.append(rec.pool[ji])
        bb.append(rec.beta[ji])
        claimed[ix] |= E.EV[cell][ix]
    t, j, b = (np.concatenate(v) if v else np.zeros(0) for v in (tt, jj, bb))
    t, j = t.astype(np.int64), j.astype(np.int64)
    keep = t + hi_t <= W.T - 1                                                           # the whole path must lie inside the stage's data
    t, j, b = t[keep], j[keep], b[keep]
    with np.errstate(invalid="ignore"):
        react = E.R3[t, j] - b * E.M3[t]
        rws = t[:, None] + taus[None, :]
        A = np.asarray(W.Rd, float)[rws, j[:, None]] - b[:, None] * np.asarray(W.es.ret, float)[rws]
    nan = float("nan")
    out = {"taus": taus, "events": int(len(t)), "deciles": {}, "by_year": {}, "signed_cum_mean_bps": nan}
    if len(t) < 10:
        return out
    qs = np.quantile(react, np.linspace(0.0, 1.0, 11))
    dec = np.clip(np.searchsorted(qs[1:-1], react, side="right"), 0, 9)
    for d_ in range(10):
        m = dec == d_
        a = A[m]
        n = np.isfinite(a).sum(axis=0)
        mean = np.where(n > 0, np.nansum(a, axis=0) / np.maximum(n, 1), nan) * 1e4
        out["deciles"][d_ + 1] = {"events": int(m.sum()), "mean_react_bps": float(react[m].mean() * 1e4), "mean_bps": mean, "cum_bps": np.nancumsum(mean)}
    sg = np.sign(react)[:, None] * A
    out["signed_cum_mean_bps"] = float(np.nanmean(np.nansum(sg, axis=1)) * 1e4)
    yr = DV.jyear(np.asarray(W.days)[t])
    for y in sorted(set(yr.tolist())):
        m = yr == y
        row = {"events": int(m.sum()), "signed_cum_mean_bps": float(np.nanmean(np.nansum(sg[m], axis=1)) * 1e4)}
        for lab, d_ in (("top", 9), ("bottom", 0)):
            mm = m & (dec == d_)
            a = A[mm]
            n = np.isfinite(a).sum(axis=0)
            row[lab + "_cum_bps"] = np.nancumsum(np.where(n > 0, np.nansum(a, axis=0) / np.maximum(n, 1), nan) * 1e4)
            row[lab + "_events"] = int(mm.sum())
        out["by_year"][int(y)] = row
    return out


PATH_AT = (5, 10, 21, 42, 60)                                                             # the taus the printed path shows (t + tau)


def print_path(pth, cell):
    taus = list(pth["taus"])
    at = [taus.index(t_) for t_ in PATH_AT if t_ in taus]
    print(f"EVENT-TIME PATH [X2] {cell} - the mean abnormal return (r - beta x ES), cumulated from t+2 to t+tau, bps, by reaction decile (1 = most negative), {pth['events']:,} events (each once, at the first rebalance that holds it):")
    if not pth["deciles"]:
        print("  (too few events)")
        return
    print("  decile  events  mean reaction   " + " ".join(f"{'t+' + str(PATH_AT[q]):>7}" for q in range(len(at))))
    for d_, v in pth["deciles"].items():
        print(f"  {d_:>6} {v['events']:>7,} {v['mean_react_bps']:>+12.0f}   " + " ".join(f"{v['cum_bps'][i]:>+7.0f}" for i in at))
    print(f"  the mean SIGNED cumulative path t+2 .. t+60 (the sign of the reaction x the abnormal return): {pth['signed_cum_mean_bps']:+.1f} bps an event; by July-June year (events: signed mean | top-decile cum t+60 minus bottom-decile cum t+60): " + "; ".join(
        f"{y}-{(y + 1) % 100:02d}: {v['events']:,}: {v['signed_cum_mean_bps']:+.0f} | {v['top_cum_bps'][-1] - v['bottom_cum_bps'][-1]:+.0f}" for y, v in pth["by_year"].items()))


def reports(W, B, S12, ref, rows, obj, summ, tbis_df, status, legs_meta, post_mode="remove"):
    """everything the prereg's REPORTED paragraph and addendum 2's [X2] list, for the registered reading: the realised beta to ES in #463's drawdown weeks, each cell's $ inside every qualifying #463 drawdown and inside every drawdown of the REFERENCE, its place on the MDL map
    (standalone ROC, rho_dd, DO), the correlation of its daily P&L with RES and the overlap of its picks with RES's, the events per month and per name and the share in the earnings months, the event-time path by reaction decile, turnover, the 20 largest name-month gains, the
    long and short sides apart (in summ), the survivorship rows, the dividend flows"""
    L, lo, hi = obj.legs, WF0, PRE_END
    rep = {"beta_to_es": {}, "episodes": {}, "ref_episodes": {}, "map_point": {}, "corr_with_legs": {}, "corr_with_res": {}, "pick_overlap_with_res": {}, "top20_gains": {}, "months": {}, "turnover": {}, "survivorship": {}, "dividend_flows": {}, "event_stats": {}, "event_path": {}}
    cands = {}
    kw = np.flatnonzero(B.mask(lo, hi))
    resL = M17.rm_build(W, lo, hi, post_mode, units=False)                          # RESMOM's own legs at the same rebalances: its 50 / 50 picks
    res_by_r = {rec.r: rec for rec in resL.recs if rec.traded}
    for cell in CELLS:
        xB = obj.series[cell][0]
        with np.errstate(all="ignore"):
            rep["beta_to_es"][cell] = D15.es_beta(B, S12, W, rows, xB)
            rc = float(np.corrcoef(xB[kw], ref.res[kw])[0, 1]) if np.ptp(xB[kw]) > 0 and np.ptp(ref.res[kw]) > 0 else float("nan")
        rep["episodes"][cell] = D15.episodes_table(S12, xB)
        rep["ref_episodes"][cell] = D15.episodes_table(ref.S, xB)
        c = summ[cell]
        rep["map_point"][cell] = {"standalone_roc_30k": c["base"]["roc"], "rho_dd": c["seat"]["rho_dd"], "DO": c["seat"]["DO"]}
        rep["corr_with_legs"][cell] = A13.corrs(B, xB, legs_meta, lo, hi)
        rep["corr_with_res"][cell] = rc
        cands[cell] = ed_candidate_rows(W, L, cell, obj.runs[cell], tbis_df, status)
        rep["top20_gains"][cell] = cands[cell][:20]
        rep["months"][cell] = M17.month_nets(B, xB, lo, hi)
        rep["turnover"][cell] = ed_turnover(L, cell)
        rep["survivorship"][cell] = D15.survivorship(W, obj.cell_legs[cell], status)
        rep["dividend_flows"][cell] = ed_div_flows(L, cell)
        rep["event_stats"][cell] = ed_event_stats(W, L, cell)
        rep["event_path"][cell] = ed_event_path(W, L, cell)
        ov = defaultdict(list)
        for rec in L.recs:
            cc, rr = rec.cell[cell], res_by_r.get(rec.r)
            if not cc.traded or rr is None:
                continue
            lg, sh = set(rec.pool[cc.idx[cc.long]].tolist()), set(rec.pool[cc.idx[cc.short]].tolist())
            rl, rs_ = set(rr.pool[rr.pick["RES"][0]].tolist()), set(rr.pool[rr.pick["RES"][1]].tolist())
            ov["long_in_res_long"].append(len(lg & rl) / len(lg))
            ov["short_in_res_short"].append(len(sh & rs_) / len(sh))
            ov["long_in_res_short"].append(len(lg & rs_) / len(lg))
            ov["short_in_res_long"].append(len(sh & rl) / len(sh))
        rep["pick_overlap_with_res"][cell] = {k: (float(np.mean(v)) if v else float("nan")) for k, v in ov.items()} | {"rebalances": len(ov["long_in_res_long"])}
    rep["manifest_sha256"] = manifest_sha()
    return rep, cands


# ------------------------------------------------------------------ printing
def row(cell, c):
    s, q = c["base"], c["seat"]
    return (f"{cell:<3} rebalances {s['n_units']:>4,} positions {s['n_pos']:>6,} net ${s['net']:>11,.0f} ROC@30k {s['roc']:>8.1f} Sortino {s['sortino']:>6.2f} maxDD ${s['max_dd']:>9,.0f} | DO {q['DO']:>+7.3f} rho_dd {q['rho_dd']:>+6.3f}")


def print_cells(res, audit_st=None):
    nul = res["null"]
    print(f"  null: RANDOM NAMES, registered ({nul['draws']} draws, seed {nul['seed']}, the MAX over the 2 cells): ROC@30k p5 {nul['roc_max']['p5']:.1f} p50 {nul['roc_max']['p50']:.1f} p95 {nul['roc_max']['p95']:.1f}; each cell alone p50 / p95: "
          + ", ".join(f"{c} {nul['by_cell'][c]['p50']:.1f} / {nul['by_cell'][c]['p95']:.1f}" for c in CELLS))
    np_ = res.get("placebo")
    if np_:
        print(f"  second null: PLACEBO IN TIME, REPORTED ({np_['draws']} draws, seed {np_['seed']}, the MAX over the 2 cells): ROC@30k p5 {np_['roc_max']['p5']:.1f} p50 {np_['roc_max']['p50']:.1f} p95 {np_['roc_max']['p95']:.1f}; "
              + "; ".join(f"{c}: the cell's ROC is above {np_['real_roc_percentile_by_cell'][c]:.0f}% of the draws ({'above' if np_['real_roc_above_p95_by_cell'][c] else 'not above'} the p95)" for c in CELLS)
              + "; the placebo's trading: " + ", ".join(f"{c} draws not trading {np_['info'][c]['draw_share_not_trading_mean']:.1%} of the rebalances, names without a placebo window {np_['info'][c]['scored_names_without_a_placebo_window_share']:.1%}" for c in CELLS))
    for cell in CELLS:
        c = res["cells"][cell]
        fails = [k for k, v in c["checks"].items() if not v]
        s2 = ", ".join(f"{k} net ${v['net']:,.0f}" for k, v in c["stress"].items())
        print("  " + row(cell, c))
        print(f"        stress: {s2}; by July-June year: " + " ".join(f"{y}-{(y + 1) % 100:02d}:{v:+,.0f}" for y, v in c["base"]["by_year"].items()))
        a2 = c["A2"]
        if a2.get("at_half_c"):
            rf, pl = a2["reference"], a2["plain_463"]
            a2s = (f"c x{a2['c']:.4g} (cell daily std ${a2['std_cell']:,.0f} vs #463's ${a2['std_book']:,.0f} over {a2['window'][0]} .. {a2['window'][1]}): REFERENCE + c x cell ROC@30k {a2['roc']:.2f} Sortino {a2['sortino']:.3f} against the reference's {rf['roc']:.2f} / {rf['sortino']:.3f} -> "
                   + ("INCREMENTAL PASS (both above): a forward BOOK shadow line opens, MANAGER #70's gate follows" if a2["incremental_pass"] else "no incremental pass (it needs both above)")
                   + f"; at 0.5c ROC {a2['at_half_c']['roc']:.2f} / Sortino {a2['at_half_c']['sortino']:.3f}, at 2c ROC {a2['at_double_c']['roc']:.2f} / Sortino {a2['at_double_c']['sortino']:.3f}; the plain #463 + c x cell book (a reported row): ROC {pl['roc']:.2f} / Sortino {pl['sortino']:.3f}")
        else:
            a2s = f"{a2.get('error', 'no c')} -> no incremental pass"
        print(f"        Stage A (a)-(e) {'PASS' if c['PASS'] else 'FAIL (' + ', '.join(fails) + ')'}" + ("" if audit_st is None else f"; audit {audit_st[cell]['audited']}/{audit_st[cell]['listed']} of the top-{AUDIT_N} listed -> {'COMPLETE' if audit_st[cell]['audit_complete'] else 'incomplete'}"))
        print(f"        A2 (a report) [X1]: {a2s}")
        g = c["gate70"]
        print(f"        #70 gate basis [X1] (the REFERENCE book's {g['episodes']} drawdown episodes, {g['dd_days']} DD days): the cell's DO {g['DO']:+.3f}, rho_dd {g['rho_dd']:+.3f}" + (
              f"; its null's DO (random names, the MAX over the 2 cells) p5 {g['null_do_p5']:+.3f} p50 {g['null_do_p50']:+.3f} p95 {g['null_do_p95']:+.3f} -> the cell's DO is {'above' if g['DO_above_null_p95'] else 'not above'} the null's p95" if "null_do_p95" in g else "")
              + (f"; its P&L inside those episodes ${sum(g['episode_pnl']):,.0f}, ${g['pnl_without_best_episode']:,.0f} without the best one" if g.get("episode_pnl") else ""))


COUNT_KEYS = ("universe", "short_history", "no_es_pairs", "no_fill", "no_beta") + tuple(f"pre_{h}" for h in HYG) + tuple(f"old_{h}" for h in HYG[1:]) + tuple(f"post_{h}" for h in HYG) + ("post_spin", "audit", "pool", "kept_naive")
KEPT_KEYS = tuple(f"kept_{h}" for h in HYG) + ("kept_flagged", "kept_calendar_split", "closed_spin")        # [HYG-S1] the pool names with an in-hold event that STAY ('close'): not removal reasons, printed apart


def print_counts(label, cnt):
    keys = [k for k in COUNT_KEYS if any(k in c for c in cnt.values())]
    print(f"  {label} name-removals by fill year, each name counted once at its FIRST reason (columns: " + " / ".join(keys) + ")")
    for y, c in sorted(cnt.items()):
        print(f"    {y}: " + " ".join(f"{c.get(k, 0)}" for k in keys) + f"   [rebalances {c.get('rebalances', 0)}, unresolved {c.get('unresolved', 0)}, warm-up {c.get('warmup', 0)}, empty {c.get('empty', 0)}]")
    if any(c.get(k, 0) for c in cnt.values() for k in KEPT_KEYS):
        print(f"  {label}: pool names with an in-hold event that STAY [HYG-S1] (flagged / a calendar split: on the split-safe path; closed_spin: closed at the close before a spin-off / stock-dividend ex-date), by fill year (columns: " + " / ".join(KEPT_KEYS) + ")")
        for y, c in sorted(cnt.items()):
            print(f"    {y}: " + " ".join(f"{c.get(k, 0)}" for k in KEPT_KEYS))


def print_scored(label, cnt):
    """the scored names and the sides by fill year: per cell the scored names (summed over the year's rebalances), the pool names with no event, and the rebalances that trade the top 50 / the third / nothing"""
    print(f"  {label} scored names by fill year (per cell: scored / pool names with no event; rebalances trading the top {M17.SPEC['n_side']} | the top-bottom third | nothing)")
    for y, c in sorted(cnt.items()):
        if c.get("rebalances", 0):
            print(f"    {y}: " + "; ".join(f"{cl} {c.get(f'scored_{cl}', 0):,} / {c.get(f'no_event_{cl}', 0):,}, {c.get(f'mode_{cl}_top', 0)} | {c.get(f'mode_{cl}_third', 0)} | {c.get(f'mode_{cl}_none', 0)}" for cl in CELLS))


def print_events(ev):
    """[E1] and the events by year (COUNTS: name-sessions of the names ever in the universe): per cell the volume events, the excluded ones by kind, the ones voided by a hygiene flag on t-1 .. t+1 or by a missing return, and the valid events"""
    print("[E1] mechanical volume days are not news: the third Friday of March / June / September / December and the Russell reconstitution day of June (2016 .. 2025, listed in the harness) are excluded from the event set, and so is the session after each")
    print("  the days: " + f"third Fridays {int(ev.tf.sum())}, Russell days {int(ev.ru.sum())} (" + ", ".join(RUSSELL_DAYS) + ")")
    for c in CELLS:
        cn = ev.counts[c]
        yrs = sorted(y for y in cn["volume"] if any(cn[k].get(y, 0) for k in cn))
        print(f"  {c} (K = {KS[c]}) events by year of the event session (volume events / excluded by [E1] = third Friday + session after + Russell + session after / voided by a hygiene flag / voided by a missing return / valid):")
        for y in yrs:
            print(f"    {y}: {cn['volume'].get(y, 0):,} / {cn['excluded'].get(y, 0):,} = {cn['excluded_third_friday'].get(y, 0)} + {cn['excluded_session_after_third_friday'].get(y, 0)} + {cn['excluded_russell_day'].get(y, 0)} + "
                  f"{cn['excluded_session_after_russell_day'].get(y, 0)} / {cn['void_hygiene'].get(y, 0):,} / {cn['void_data'].get(y, 0):,} / {cn['valid'].get(y, 0):,}")


def print_reports(rep, summ):
    b = rep["beta_to_es"]
    print("  realised beta to ES (the cell's daily $ P&L on ES's daily return, $ per 1% ES move; #463's DD days / DD weeks / all WF days) - FIRST: " + "; ".join(
        f"{c} {b[c]['DD days']['usd_per_1pct_es']:+,.0f} / {b[c]['DD weeks (every day of them)']['usd_per_1pct_es']:+,.0f} / {b[c]['all WF days']['usd_per_1pct_es']:+,.0f}" for c in CELLS))
    for c in CELLS:
        e = rep["episodes"][c]
        print(f"  {c}: P&L inside #463's {len(e)} qualifying drawdowns: net ${sum(x['cell_pnl'] for x in e):,.0f} over {sum(x['dd_days'] for x in e)} DD days (#463's ${sum(x['book_pnl'] for x in e):,.0f}); "
              f"MDL map point: ROC@30k {rep['map_point'][c]['standalone_roc_30k']:.1f}, rho_dd {rep['map_point'][c]['rho_dd']:+.3f}, DO {rep['map_point'][c]['DO']:+.3f}")
    for c in CELLS:
        es_, ov = rep["event_stats"][c], rep["pick_overlap_with_res"][c]
        print(f"  {c} events inside the pool windows (each once): {es_['events']:,} on {es_['names_with_an_event']:,} names (per name: mean {es_['per_name_mean']:.1f}, median {es_['per_name_median']:.0f}, max {es_['per_name_max']}); by month of the event (Jan .. Dec): "
              + " ".join(f"{v:,}" for v in es_["by_month"].values()) + f"; in the four earnings months after quarter-ends (Jan, Apr, Jul, Oct) {es_['share_in_earnings_months']:.1%}, in the first two months after them {es_['share_in_first_two_months']:.1%}")
        print(f"  {c} against RES: daily P&L correlation {rep['corr_with_res'][c]:+.3f} (WF days; RES's registered line); pick overlap over {ov['rebalances']} rebalances - longs that are RES longs {ov['long_in_res_long']:.0%} / RES shorts {ov['long_in_res_short']:.0%}, "
              f"shorts that are RES shorts {ov['short_in_res_short']:.0%} / RES longs {ov['short_in_res_long']:.0%}")
    for c in CELLS:
        sd = summ[c]["sides"]
        fl = rep["dividend_flows"][c]
        print(f"  {c} dividends [R1] inside the registered picks: longs received ${fl['long_received']:,.0f} on {fl['long_positions_with_a_dividend']:,} positions, shorts paid ${fl['short_paid']:,.0f} on {fl['short_positions_with_a_dividend']:,}")
        z = sd.get(M17.R2_SIDE)
        if z is not None:
            print(f"  {c} short leg [R2]: net ${sd['short side only']['net']:,.0f} with a name that stops printing exiting at its last close (the base); ${z['net']:,.0f} with such names valued at zero "
                  f"({summ[c]['short_stopped']['positions']} of {summ[c]['short_stopped']['short_positions']:,} short positions); the whole cell with it ${summ[c]['extra'][M17.R2_CELL]['net']:,.0f} (base ${summ[c]['base']['net']:,.0f})")
        print(f"  {c} sides: long only net ${sd['long side only']['net']:,.0f}, short only net ${sd['short side only']['net']:,.0f}; borrow / survivorship rows: " + ", ".join(f"{k} ${v['net']:,.0f}" for k, v in summ[c]["extra"].items()))
        t = rep["turnover"][c]
        if t.get("transitions"):
            print(f"  {c} turnover: {t['replaced_mean']:.0%} of the names replaced per rebalance on average (median {t['replaced_median']:.0%}, range {t['replaced_min']:.0%} .. {t['replaced_max']:.0%}); if only the changes were traded: ${t['cost_saved_if_only_changes_traded_usd_estimate']:,.0f} less "
                  "in total (estimate, not judged)")
        sv = rep["survivorship"][c]
        print(f"  {c} survivorship: {sv['long_in_inactive_names']:,} of {sv['long_positions']:,} long positions ({sv['share_long_in_inactive_names']:.1%}) are in names the asset list calls inactive")
        for x in rep["top20_gains"][c][:3]:
            print(f"      {c} top gain {x['rank']}: {x['symbol']} {x['side']} filled {x['date']} -> {x['exit']} ${x['pnl']:,.0f} reaction {x['reaction']:+.3f} (event {x['event']}, age {x['event_age']}, volume x{x['event_volume_multiple']:.1f}) (the 20 largest are in the Stage A file)")


DIAG_LW, DIAG_CW = 58, 20


def diag_line(label, vals):
    return f"  {label:<{DIAG_LW}}" + "".join(f"{v:>{DIAG_CW}}" for v in vals)


def print_diagnostics(res, rep, ref):
    """[X2] DEEPER DIAGNOSTICS of the registered reading, V3 and V5 side by side: the cost curve at 0 / 5 / 10 / 20 bps a side, a row per July-June year, the two regime halves, a row per drawdown episode of the REFERENCE book (the cell's P&L inside it), the LONG and SHORT sides apart, and the #70 gate's
    basis. CHOICE: 'a drawdown episode of the reference' = a QUALIFYING episode (MDL r1's rule: at least 1/3 as deep as the deepest - the episodes the #70 gate's DO is measured on). None of it is a pass route"""
    cells = res["cells"]
    each = lambda f: [f(cells[c], c) for c in CELLS]
    nr = lambda s: f"{s['net']:+,.0f} / {s['roc']:.1f}"
    print("DIAGNOSTICS [X2] - the registered reading, the WF stretch, V3 and V5 side by side; none of this is a pass route")
    print(diag_line("", list(CELLS)))
    print("  COST CURVE - the cost a side: net $ / ROC@30k")
    for lab, get in (("0 bps", lambda c: c["cost0"]), ("5 bps (the base)", lambda c: c["base"]), ("10 bps", lambda c: c["stress"]["10 bps"]), ("20 bps", lambda c: c["stress"]["20 bps"])):
        print(diag_line(f"  {lab}", each(lambda c, k: nr(get(c)))))
    print("  BY JULY-JUNE YEAR - net $ of the daily series (long side | short side)")
    for y in YEARS:
        print(diag_line(f"  {y}-{(y + 1) % 100:02d}", each(lambda c, k: f"{c['base']['by_year'][y]:+,.0f} ({c['sides']['long side only']['by_year'][y]:+,.0f} | {c['sides']['short side only']['by_year'][y]:+,.0f})")))
    print("  THE TWO REGIME HALVES - net $ / ROC@30k, then the positions that exited in the half")
    for lab, _a, _b in SUBPERIODS:
        print(diag_line(f"  {lab}", each(lambda c, k: nr(c["sub"][lab]))))
        print(diag_line("    positions", each(lambda c, k: f"{c['sub'][lab]['n_pos']:,}")))
    g = ref.structure
    print(f"  THE REFERENCE BOOK'S DRAWDOWN EPISODES ({g['episodes']} qualifying, {g['days']} DD days; MDL r1's rule) - the cell's P&L inside each (the DD days: the day after the peak .. the trough)")
    for q, e in enumerate(rep["ref_episodes"][CELLS[0]]):
        print(diag_line(f"  {e['first_dd_day']} .. {e['trough']} ${e['depth']:,.0f} ({e['dd_days']} d, ref {e['book_pnl']:+,.0f})", [f"{rep['ref_episodes'][c][q]['cell_pnl']:+,.0f}" for c in CELLS]))
    print(diag_line("  all the episodes (the cell's P&L over the DD days)", [f"{sum(x['cell_pnl'] for x in rep['ref_episodes'][c]):+,.0f}" for c in CELLS]))
    print("  THE LONG AND SHORT SIDES APART (net $ / ROC@30k / maxDD)")
    for lab in ("long side only", "short side only"):
        print(diag_line(f"  {lab}", each(lambda c, k: f"{c['sides'][lab]['net']:+,.0f} / {c['sides'][lab]['roc']:.1f} / {c['sides'][lab]['max_dd']:,.0f}")))
    print(f"  #70 GATE BASIS - the cell's DO against the REFERENCE book's {g['episodes']} drawdown episodes / {g['days']} DD days, beside its random-name null's (the MAX over the 2 cells)")
    print(diag_line("  DO (cell P&L over the DD days / the reference's loss)", each(lambda c, k: f"{c['gate70']['DO']:+.3f}")))
    print(diag_line("  the null's DO p95", each(lambda c, k: f"{c['gate70']['null_do_p95']:+.3f}" if "null_do_p95" in c["gate70"] else "-")))
    print(diag_line("  the cell's DO above the null's p95", each(lambda c, k: ("yes" if c["gate70"]["DO_above_null_p95"] else "no") if "null_do_p95" in c["gate70"] else "-")))
    print(diag_line("  positive without the best episode", each(lambda c, k: ("yes" if c["gate70"]["positive_without_best_episode"] else "no") if "positive_without_best_episode" in c["gate70"] else "-")))


# ------------------------------------------------------------------ the hand audit (f): read, apply, status
def read_audit(path=None):
    """OUT\\edrift_audit.csv (symbol, date, cell, verdict in {keep, data_event}, note) -> a frame, or None when there is no file yet. A data_event row removes that name-month from BOTH cells AND both nulls before anything is computed [(f)]. CHOICE: the date is the
    position's FILL date - exactly the 'date' of edrift_audit_candidates.csv (r17_resmom's key); a data event belongs to the name-month, so a row covers both cells' listing of it. Refuses a verdict / cell / date it cannot read (a mistyped row must not silently do nothing)"""
    p = path or os.path.join(OUT, "edrift_audit.csv")
    if not os.path.exists(p):
        return None
    df = pd.read_csv(p, dtype=str, keep_default_na=False)
    miss = [c for c in ("symbol", "date", "cell", "verdict") if c not in df.columns]
    if miss:
        refuse(f"refused: edrift_audit.csv lacks the column(s) {miss} (columns: symbol, date, cell, verdict, note) - nothing computed")
    df["symbol"], df["cell"], df["verdict"] = df["symbol"].str.strip(), df["cell"].str.strip().str.upper(), df["verdict"].str.strip().str.lower()
    df["date"] = pd.to_datetime(df["date"].str.strip(), errors="coerce")
    bad = df[~df["verdict"].isin(("keep", "data_event")) | ~df["cell"].isin(CELLS) | df["date"].isna() | (df["symbol"] == "")]
    if len(bad):
        refuse(f"refused: edrift_audit.csv line(s) {[int(i) + 2 for i in bad.index][:10]} have an unreadable date / symbol, a verdict outside keep | data_event, or a cell outside {list(CELLS)} (nothing computed)")
    return df


apply_audit, unused_audit_rows, audit_status = M17.apply_audit, M17.unused_audit_rows, M17.audit_status      # r17_resmom's: the key is symbol + FILL date, a data_event removes the name-month from the pool (cells AND nulls); a mistyped row refuses
cut_checks = DV.cut_checks                                                                                  # r18_divrun's: nothing on / after the stage's cut in the World's sessions or the calendar's rows


@contextlib.contextmanager
def div_mode(W, on):
    """[R1] r17_resmom's div_mode (the cash dividends in / out of the daily return) + the events' reaction sums re-attached on the same series: the events themselves (volume, [E1], hygiene, finite windows) do not depend on the cash, R3 does"""
    old, was = W.ed, W.div_on
    with M17.div_mode(W, on):
        if bool(on) != bool(was):
            attach_events(W, counts_only=old.counts_only, tf=old.tf, ru=old.ru)
        try:
            yield
        finally:
            W.ed = old


def pick_candidate(cells, passing):
    """CHOICE (the prereg names no tie-break between two passing cells; A2 is only a report): the passing cell with the higher WF standalone ROC @ $30k goes to Stage B (ties: V3 first); the other is reported"""
    return max(passing, key=lambda c: (cells[c]["base"]["roc"], -CELLS.index(c))) if passing else None


def stage_a_flow(cells):
    """Stage A's bookkeeping, pure: passing = the cells that clear (a) - (e) (their checks, the registered null included); the candidate = pick_candidate(passing). (f), the hand audit, is NEVER decided here - every passing cell 'awaits the hand audit', and Stage B needs the
    lead's go-flag"""
    passing = [c for c in CELLS if cells[c]["PASS"]]
    return passing, pick_candidate(cells, passing)


# ------------------------------------------------------------------ dryload: counts only
def scored_stats(L):
    """COUNTS over a leg's rebalances: per cell the scored names per rebalance (min / median / max, over the rebalances whose pool was not empty) and the rebalances by what they trade (top 50 / the thirds / nothing), overall and by fill year"""
    out = {}
    for c in CELLS:
        ns = np.array([rec.cell[c].n for rec in L.recs if len(rec.pool)], int)
        out[c] ={"rebalances": int(len(L.recs)), "with_a_pool": int(len(ns)), "min": int(ns.min()) if len(ns) else 0, "median": float(np.median(ns)) if len(ns) else 0.0, "max": int(ns.max()) if len(ns) else 0,
                  "modes": dict(Counter(rec.cell[c].mode for rec in L.recs if len(rec.pool))), "no_pool": int(sum(1 for rec in L.recs if not len(rec.pool)))}
    return out


def print_scored_stats(label, L, W):
    st = scored_stats(L)
    print(f"  {label} scored names per rebalance (min / median / max over the {st[CELLS[0]]['with_a_pool']} rebalances with a pool of {st[CELLS[0]]['rebalances']}; rebalances trading the top {M17.SPEC['n_side']} a side / the top-bottom third / nothing): "
          + "; ".join(f"{c} {st[c]['min']} / {st[c]['median']:.0f} / {st[c]['max']}, {st[c]['modes'].get('top', 0)} / {st[c]['modes'].get('third', 0)} / {st[c]['modes'].get('none', 0)}" for c in CELLS))
    byy = {c: defaultdict(list) for c in CELLS}
    for rec in L.recs:
        if len(rec.pool):
            for c in CELLS:
                byy[c][int(W.days[rec.f].year)].append(rec.cell[c].n)
    for c in CELLS:
        print(f"    {c} by fill year (rebalances: min / median / max scored): " + "; ".join(f"{y}: {len(v)}: {min(v)} / {np.median(v):.0f} / {max(v)}" for y, v in sorted(byy[c].items())))
    return st


def dryload():
    """the WF inputs through every loader (cut at 2025-06-30) and COUNTS only: sessions, symbols, universe sizes, the [E1] exclusions and the events per cell by year (volume events, excluded, voided by a hygiene flag or a missing return, valid), the rebalances and the pool / scored names per
    rebalance, the fallback months, the hygiene removals by reason (both readings), [E5']'s match counts, TBIS rows matched, ES coverage. NO price, return, reaction, score, regression, P&L or Stage A statistic is computed or printed: the existence of events is tested on volumes alone and
    the existence of the three returns of an event window, the pools are counted from which returns EXIST (counts_only), and no unit path is built"""
    prereg_ok()
    t0 = time.time()
    D = M17.load_data(S.LB0)
    nfull = len(D.syms)
    tbis = D15.load_tbis(S.LB0)
    es_frames, es_meta = D15.load_es(S.LB0)
    full_match = D15.tbis_array(D.days, D.syms, tbis)[1]
    cal, winfo = M17.wide_load(S.LB0, need=False, enforce=False)                              # CHOICE (r18's): the dryload counts on the calendar when it exists and REPORTS its sha status (only Stage A / B refuse an unregistered one)
    W = M17.build_world(D, S.LB0, es_frames, tbis, cal)
    D15.release(D)
    cut_checks(W, cal, S.LB0)
    print(f"dryload: inputs ready ({time.time() - t0:.0f}s); every input cut to dates < {S.LB0:%Y-%m-%d}; ES masters {es_meta['raw']['filename']} / {es_meta['adj']['filename']}")
    wf = (W.days >= WF0) & (W.days <= PRE_END)
    print(f"sessions: {W.T:,} on the market calendar ({W.days[0]:%Y-%m-%d} .. {W.days[-1]:%Y-%m-%d}), {int(wf.sum()):,} inside the WF stretch; symbols: {nfull:,} in the cache after SIPORB's price / volume floor, {W.S:,} ever in the universe")
    usz, yrs = W.U.sum(axis=1), W.days.year.to_numpy()
    print("universe size per session by year (sessions with a universe: min / median / max): " + "; ".join(
        f"{y}: {int((m := (yrs == y) & (usz > 0)).sum())} sessions {int(usz[m].min())} / {int(np.median(usz[m]))} / {int(usz[m].max())}" for y in sorted(set(yrs)) if ((yrs == y) & (usz > 0)).any()))
    check_russell(W.days)
    ev = attach_events(W, counts_only=True)
    print_events(ev)
    Lr, Lk = ed_build(W, WF0, PRE_END, "remove", units=False, counts_only=True), ed_build(W, WF0, PRE_END, "naive", units=False, counts_only=True)
    r_all, f_all, x_all = M17.rm_schedule(W.days)
    inwf = [(r, f, x) for r, f, x in zip(r_all.tolist(), f_all.tolist(), x_all.tolist()) if x >= 0 and WF0 <= W.days[x] <= PRE_END]
    first_full = min((r for r, f, x in inwf if r >= M17.SPEC["win"] - 1), default=None)
    print(f"rebalances: {len(Lr.recs)} in WF (positions that exit {WF0:%Y-%m-%d} .. {PRE_END:%Y-%m-%d} with a full {M17.SPEC['win']}-session window)"
          + (f"; the first rank session with a full window is {W.days[first_full]:%Y-%m-%d} (filled {W.days[first_full + 1]:%Y-%m-%d})" if first_full is not None else "")
          + f"; {sum(1 for r, f, x in inwf if r < M17.SPEC['win'] - 1)} earlier ranks are warm-up; the stage's last rank has no next fill: unresolved, out")
    by = defaultdict(list)
    for rec in Lr.recs:
        by[int(W.days[rec.f].year)].append((rec.nu, rec.nfull, len(rec.pool)))
    print("names with a full window (>= 230 own returns and >= 230 ES pairs) per rebalance, by fill year (universe / full window / eligible pool: min - mean - max): " + "; ".join(
        f"{y}: {len(v)} rebalances, universe {min(a for a, b, c in v)}-{np.mean([a for a, b, c in v]):.0f}-{max(a for a, b, c in v)}, full {min(b for a, b, c in v)}-{np.mean([b for a, b, c in v]):.0f}-{max(b for a, b, c in v)}, "
        f"pool {min(c for a, b, c in v)}-{np.mean([c for a, b, c in v]):.0f}-{max(c for a, b, c in v)}" for y, v in sorted(by.items())))
    print_scored_stats("registered (a flag inside the hold removes the name)", Lr, W)
    print_scored(f"registered (the fallback rule: {SPEC['min_scored']} scored names or more -> {M17.SPEC['n_side']} a side, fewer -> the top / bottom third, at least {SPEC['min_side']} a side, else nothing)", Lr.cnt)
    print_scored_stats("look-ahead (names flagged inside the hold stay)", Lk, W)
    print_counts("registered (a flag inside the hold removes the name)", Lr.cnt)
    print_counts("look-ahead (names flagged inside the hold stay, on their naive raw path)", Lk.cnt)
    M17.print_spin_counts("registered", Lr.cnt)
    fr, einfo = edgar_load(S.LB0, enforce=False)
    mem = members_load(S.LB0)
    if fr is None:
        print("[E5'] TV's EDGAR earnings calendar: " + (f"not on file ({einfo['path']})" if not einfo["present"] else f"{os.path.basename(einfo['path'])} is on file with sha256 {einfo['sha256']}, NOT the registered {CAL_SHA[:16]}... - not read; Stage A refuses until it is") + "; no match was counted")
    else:
        rel_t, rel_j, jc = earn_join(W, fr, mem)
        print_e5(einfo, jc)
    print(f"TBIS flags: {len(tbis):,} symbol-days listed before the cut, {full_match:,} match a session and a cached name, {W.tbis_rows[1]:,} a name that is ever in the universe; every listed row is a flag")
    if W.ca is not None:
        M17.print_wide(W.ca)
        st0 = M17.calendar_start(W.ca["file"]["manifest"])
        print(M17.d1_report(W, st0)[1] if st0 is not None else "calendar coverage [D1]: the manifest carries no readable start date - the coverage of the first ranks' windows cannot be counted")
    else:
        print(f"wide corporate-actions calendar [R1]: not on file yet ({winfo['path']}) - Stage A refuses until MANAGER's pull is on file and WIDE_CA_SHA is set; this dryload ran without dividends")
    pa, pr = W.es_cov["adj_prints"], W.es_cov["raw_prints"]
    e = W.es
    print(f"ES prints on the {W.T:,} stock sessions: 09:35 price {int(np.isfinite(e.e5).sum()):,}, 16:00 adj {int(np.isfinite(e.c16a).sum()):,}, 16:00 raw {int(np.isfinite(e.c16r).sum()):,}; fallback bars: "
          f"{int((pa['close_hm'] != pa['last']).sum())} closes (adj master), {int((pr['close_hm'] != pr['last']).sum())} closes (raw master); ES return defined on {int(np.isfinite(e.ret).sum()):,} sessions")
    print(M17.es_report(W)[0])
    fin = np.flatnonzero(np.isfinite(W.k))
    print(f"k_t: defined from {W.days[fin[0]]:%Y-%m-%d} on ({len(fin):,} of {W.T:,} sessions); undefined on {int((~np.isfinite(W.k[wf])).sum())} WF sessions" if len(fin) else "k_t: undefined everywhere")
    print(f"cache manifest sha256: {manifest_sha()}")
    pm = peak_mb()
    print(f"dryload took {time.time() - t0:.0f}s" + (f", peak memory {pm:,.0f} MB" if pm else ""))


# ------------------------------------------------------------------ Stage A
def plain_a2(B, xB):
    """the registered volatility rule for c (r18_divrun's plain_a2 = r17_resmom's A2 code) on EDRIFT's window: 25% of #463's daily std over 2017-01-03 .. 2018-12-31 / the cell's; used by Stage B to recompute the frozen c"""
    with patched(DV, A2_WIN=A2_WIN, A2_TARGET=A2_TARGET, A2_REPORT=A2_REPORT):
        return DV.plain_a2(B, xB)


def stage_a():
    if os.path.exists(os.path.join(OUT, READ_FLAG)):                                       # CHOICE (r17's / r18's): once the lockbox has been read Stage A is frozen (a re-run could change the cell or c after the fact)
        refuse(f"Stage A refused: Stage B has already read the lockbox - Stage A is frozen ({READ_FLAG})")
    pok = prereg_ok()
    cal, winfo = M17.wide_load(S.LB0)                                                      # [R1] refuses (nothing computed) when the wide calendar is not on file / not registered / not the registered file
    fr, einfo = edgar_load(S.LB0)                                                          # [E5'] refuses (nothing computed) when TV's earnings calendar is not on file / not the registered file / lacks a column
    mem = members_load(S.LB0)
    B, legs_meta = A13.load_463()                                                          # the book first: cheap, and a book that does not reproduce stops everything
    bk, dd, S12 = book_checks(B)
    print(f"BOOK #463 WF check (must be {BOOK_WF[0]} / {BOOK_WF[1]}): ROC@30k {bk['roc']:.2f} Sortino {bk['sortino']:.3f}; deepest drawdown ${dd['deepest']:,.0f} (must be ${DEEPEST_WF:,.0f}), "
          f"{dd['episodes']} qualifying episodes, {dd['days']} DD days, {dd['weeks']} DD weeks, by year {dd['by_year']}, the 2020-03-03 .. 03-27 episode {'found' if dd['episode_2020'] else 'NOT FOUND'}")
    if CHECK_BOOK and not (bk["ok"] and dd["ok"]):
        refuse("Stage A refused: the #463 records do not reproduce the registered WF numbers / drawdown structure (the prereg's [T5] facts) - fix the input first (nothing computed)")
    ref = DV.ref_load(B, check_facts=CHECK_BOOK)                                           # [X1] RESMOM's WF line -> the REFERENCE book: refuses (nothing computed) unless the file is the registered one and the reference reproduces its registered numbers
    DV.print_reference(ref)
    msha = manifest_sha()
    print(f"SIPORB cache manifest sha256: {msha} (registered: {D15.MANIFEST_PREFIX}...)")
    if CHECK_BOOK and not (msha and msha.startswith(D15.MANIFEST_PREFIX)):
        refuse("Stage A refused: the SIPORB cache manifest is missing or is not the registered photograph of the vendor (a re-pull must never be mixed in) - nothing computed")
    t0 = time.time()
    D = M17.load_data(S.LB0)                                                               # every input is cut to dates < 2025-06-30 inside this call, before anything is computed
    tbis = D15.load_tbis(S.LB0)
    es_frames, es_meta = D15.load_es(S.LB0)
    audit = read_audit()
    W = M17.build_world(D, S.LB0, es_frames, tbis, cal)
    D15.release(D)
    cut_checks(W, cal, S.LB0)
    check_russell(W.days)                                                                  # [E1] the lead's Russell list must cover every June the data holds (refuses before any event is built)
    wf = (W.days >= WF0) & (W.days <= PRE_END)
    kmiss = int((~np.isfinite(W.k[wf])).sum())
    print(f"world ready ({time.time() - t0:.0f}s): {int(wf.sum()):,} WF sessions, {W.S:,} names ever in the universe, k_t (read only by the borrow stress rows) undefined on {kmiss} WF sessions; ES masters "
          f"{es_meta['raw']['filename']} / {es_meta['adj']['filename']}", flush=True)
    es_txt, es_rec = M17.es_report(W)
    print(es_txt)
    M17.print_wide(W.ca)
    d1rec, d1txt = M17.d1_report(W, M17.calendar_start(W.ca["file"]["manifest"]))             # [D1] (wide_load's gate guarantees a readable start)
    print(d1txt)
    out = {"prereg_sha256_lf": PREREG_SHA, "prereg_verified": pok["verified"], "prereg_committed": pok["committed"], **stamp(), "judged": False, "stageA": None, "candidate": None, "pending_hand_audit": None,
           "book_check": bk, "dd_structure": dd, "reference": DV.ref_record(ref), "manifest_sha256": msha, "es_return": es_rec, "wide_calendar": W.ca, "k_undefined_wf_sessions": kmiss, "coverage_d1": d1rec}
    aud_n = apply_audit(W, audit)
    asha = file_sha(os.path.join(OUT, "edrift_audit.csv"))
    print("audit file: " + ("none yet" if audit is None else f"{aud_n['rows']} rows ({aud_n['keep']} keep, {aud_n['data_event']} data_event: removed from the cells AND the nulls)"))
    rows = A13.book_rows(B, W)
    # ---- the events, [E1], and [E3] / [E5'] BEFORE any P&L: scores and counts only (the leg is built without unit paths, nothing is costed)
    ev = attach_events(W)
    print_events(ev)
    L0 = ed_build(W, WF0, PRE_END, "remove", units=False)
    e3 = e3_report(W, L0)
    print_e3(e3)
    rel_t, rel_j, jcnt = earn_join(W, fr, mem)
    e5 = earn_check(W, L0, rel_t, rel_j)
    print_e5(einfo, jcnt, e5)
    out.update({"events": {c: ev.counts[c] for c in CELLS}, "e3": e3, "e5": {"file": einfo, "join": jcnt, "shares": e5}})
    del L0
    t1 = time.time()
    resR, objR = evaluate(W, B, S12, ref, rows, "remove", NREP, 0, full=True)
    print(f"registered reading done ({time.time() - t1:.0f}s: the leg, the cells, the stress rows, {NREP} random-name draws and {NREP} placebo draws per cell)", flush=True)
    unused = unused_audit_rows(W, audit)
    if unused:
        print(f"  NOTE: {len(unused)} audit data_event row(s) removed nothing (the name was not in that fill session's universe): {unused[:5]}")
    t1 = time.time()
    resK, objK = evaluate(W, B, S12, ref, rows, "naive", NREP, 1, full=False)
    print(f"look-ahead reading done ({time.time() - t1:.0f}s)", flush=True)
    t1 = time.time()
    with div_mode(W, False):                                                               # [R1] the no-dividend version of both cells (the reactions, the picks and the P&L without the cash dividends): a REPORTED row, never the verdict
        resD = evaluate(W, B, S12, ref, rows, "remove", NREP, 2, full=False)[0]
    print(f"no-dividend reading done ({time.time() - t1:.0f}s)", flush=True)
    t1 = time.time()
    resF, objF = evaluate(W, B, S12, ref, rows, "remove", NREP, 3, full=False, drop=tuple(TS(x_) for x_ in M17.D1_RANKS))       # [D1] the same registered reading without the first five rebalances: a REPORTED row, never the verdict
    nF = len(objF.legs.recs)
    del objF
    print(f"without-the-first-five reading done ({time.time() - t1:.0f}s)", flush=True)
    spin = {"registered_reading": {c: ed_spin_counts(objR.legs, c) for c in CELLS}, "look_ahead_reading_kept_at_naive_price_pnl": {c: ed_spin_counts(objK.legs, c) for c in CELLS}}
    rep, cands = reports(W, B, S12, ref, rows, objR, resR["cells"], tbis, D15.asset_status(), legs_meta)
    cells = resR["cells"]
    passing, cand = stage_a_flow(cells)
    ast = audit_status(cands, audit)
    flips = {c: bool(resK["cells"][c]["PASS"]) != bool(cells[c]["PASS"]) for c in CELLS}
    os.makedirs(OUT, exist_ok=True)
    pd.DataFrame([r for c in CELLS for r in cands[c]]).to_csv(os.path.join(OUT, "edrift_audit_candidates.csv"), index=False)
    print(f"WF {WF0:%Y-%m-%d} -> {PRE_END:%Y-%m-%d} ({int(wf.sum()):,} sessions) - the REGISTERED reading (a hygiene flag inside the hold removes the position)")
    print_cells(resR, ast)
    print(f"  look-ahead reading (positions with a flag INSIDE the hold kept at naive raw P&L) [O3]: null ROC p95 {resK['null']['roc_max']['p95']:.1f}")
    for cell in CELLS:
        k = resK["cells"][cell]
        print(f"    {cell}: {row(cell, k)[4:]} | Stage A (a)-(e) {'PASS' if k['PASS'] else 'FAIL'}" + ("   *** FLIPS the registered verdict ***" if flips[cell] else "   (same verdict)"))
    print(f"  no-dividend version [R1] (the cash dividends left out of the reactions, the picks and the P&L; REPORTED, never the verdict; its own null ROC p95 {resD['null']['roc_max']['p95']:.1f}):")
    for cell in CELLS:
        k = resD["cells"][cell]
        print(f"    {cell}: {row(cell, k)[4:]} | Stage A (a)-(e) {'PASS' if k['PASS'] else 'FAIL'}; the registered, with dividends: net ${cells[cell]['base']['net']:,.0f} -> the dividends add ${cells[cell]['base']['net'] - k['base']['net']:,.0f}")
    print(f"  without the first five rebalances [D1] (their regression windows start before the calendar does: the dividends, splits and spin-offs before it count as zero there; {nF} of {len(objR.legs.recs)} rebalances remain; "
          f"REPORTED, never the verdict; its own null ROC p95 {resF['null']['roc_max']['p95']:.1f}):")
    for cell in CELLS:
        k = resF["cells"][cell]
        print(f"    {cell}: {row(cell, k)[4:]} | Stage A (a)-(e) {'PASS' if k['PASS'] else 'FAIL (' + ', '.join(q for q, v in k['checks'].items() if not v) + ')'}; the registered, all {len(objR.legs.recs)}: net ${cells[cell]['base']['net']:,.0f}, ROC@30k {cells[cell]['base']['roc']:.1f}")
    print_spin_picks(spin)
    print_reports(rep, cells)
    for c in CELLS:
        print_path(rep["event_path"][c], c)
    print_diagnostics(resR, rep, ref)
    print_counts("L (registered)", objR.legs.cnt)
    print_counts("L (look-ahead)", objK.legs.cnt)
    print_scored("L (registered)", objR.legs.cnt)
    M17.print_spin_counts("L (registered)", objR.legs.cnt)
    print(f"  audit candidates (the {AUDIT_N} largest gains per cell, with dates) -> {os.path.join(OUT, 'edrift_audit_candidates.csv')}; the hand audit is the lead's (a data event found: a row symbol, date, cell, data_event in edrift_audit.csv and run stage_a again); "
          "audit rows found per list: " + ", ".join(f"{k} {v['audited']}/{v['listed']}" for k, v in ast.items()))
    out.update({"judged": True, "pending_hand_audit": passing,
                "stageA": {"cells": cells, "null": resR["null"], "placebo_null": resR["placebo"], "pass_cells": passing},
                "candidate": ({"cell": cand, "c": cells[cand]["A2"]["c"], "std_book": cells[cand]["A2"]["std_book"], "std_cell": cells[cand]["A2"]["std_cell"], "window": cells[cand]["A2"]["window"], "a2_book_roc": cells[cand]["A2"]["roc"],
                               "a2_reference_roc": cells[cand]["A2"]["reference"]["roc"], "incremental_pass": cells[cand]["A2"]["incremental_pass"], "book_shadow_line": cells[cand]["A2"]["book_shadow_line"],
                               "also_passes": [c for c in passing if c != cand]} if cand else None),
                "parity": {c: {"net": cells[c]["base"]["net"], "n_pos": cells[c]["base"]["n_pos"], "n_units": cells[c]["base"]["n_units"]} for c in CELLS},
                "audit": aud_n, "audit_sha256": asha, "audit_status": ast,
                "without_first_five_reading": {"dropped_ranks": list(M17.D1_RANKS), "rebalances_remaining": int(nF), "of": int(len(objR.legs.recs)), "null": resF["null"],
                                              "cells": {c: {k: resF["cells"][c][k] for k in ("PASS", "base", "stress", "seat", "checks", "A2")} for c in CELLS}},
                "spin_counts": spin,
                "no_dividend_reading": {"null": resD["null"], "cells": {c: {k: resD["cells"][c][k] for k in ("PASS", "base", "stress", "seat", "checks", "A2")} for c in CELLS},
                                        "dividends_add_net": {c: cells[c]["base"]["net"] - resD["cells"][c]["base"]["net"] for c in CELLS}},
                "kept_naive_reading": {"null": resK["null"], "cells": {c: {k: resK["cells"][c][k] for k in ("PASS", "base", "seat", "checks", "A2")} for c in CELLS}, "flips": flips},
                "hygiene_counts_by_year": {"registered": {y: dict(c) for y, c in sorted(objR.legs.cnt.items())}, "look_ahead": {y: dict(c) for y, c in sorted(objK.legs.cnt.items())}},
                "reports": rep, "es_masters": es_meta})
    dump(out, "edrift_stageA.json")
    for c in passing:
        a2 = cells[c]["A2"]
        print(f"Stage A (a)-(e) pass, (f) awaits the hand audit - cell {c}; WF ROC@30k {cells[c]['base']['roc']:.1f}; A2 (a report) [X1]: c x{a2['c']:.4g} set by volatility, REFERENCE + c x cell ROC@30k {a2['roc']:.2f} / Sortino {a2['sortino']:.3f} against the reference's "
              f"{a2['reference']['roc']:.2f} / {a2['reference']['sortino']:.3f} -> " + ("an INCREMENTAL PASS: a forward BOOK shadow line opens beside the standalone one and MANAGER #70's gate follows (the cell's DO and its null's on the reference's drawdown days)"
                                                                                       if a2["incremental_pass"] else "no incremental pass: no book shadow line"))
    if passing:
        print(f"EDRIFT Stage A: (a)-(e) pass for {passing}; (f) AWAITS THE HAND AUDIT of the {AUDIT_N} largest contributors (the harness never decides it); candidate {cand}. Stage B needs the lead's go-flag {GO_FLAG} (written after the hand audit, on the stock families' "
              "one sealed-year day).")
    else:
        print("EDRIFT Stage A: FAIL - no cell passes (a)-(e) (" + "; ".join(f"{c}: " + ", ".join(k for k, v in cells[c]['checks'].items() if not v) for c in CELLS) +
              ") - EDRIFT r1 is dead; no other windows, K or horizons are tried; the lockbox stays sealed.")
    pm = peak_mb()
    print(f"stage_a took {time.time() - t0:.0f}s" + (f", peak memory {pm:,.0f} MB" if pm else ""))
    return out


def ed_spin_counts(L, cell):
    """[D2] (window, hold; long, short) over a leg's traded rebalances, for one cell's picks (r17_resmom.spin_counts for this leg's records)"""
    out = {sd: {"positions": 0, "window_positions": 0, "window_sessions": 0, "hold_positions": 0} for sd in ("long", "short")}
    for rec in L.recs:
        cc = rec.cell[cell]
        if not cc.traded:
            continue
        for sd, idx in (("long", cc.long), ("short", cc.short)):
            q = cc.idx[idx]
            o = out[sd]
            o["positions"] += int(len(q))
            o["window_positions"] += int((rec.spin_win[q] > 0).sum())
            o["window_sessions"] += int(rec.spin_win[q].sum())
            o["hold_positions"] += int(rec.spin_hold[q].sum())
    return out


def print_spin_picks(spin):
    for reading, per in spin.items():
        for cell in CELLS:
            c = per[cell]
            print(f"  {reading} [D2] {cell} picks (long / short): positions {c['long']['positions']:,} / {c['short']['positions']:,}; window (a return left out of the name's regression window) {c['long']['window_positions']:,} / "
                  f"{c['short']['window_positions']:,} positions ({c['long']['window_sessions']:,} / {c['short']['window_sessions']:,} sessions left out); hold (a spin-off / stock-dividend ex-date inside it) {c['long']['hold_positions']:,} / {c['short']['hold_positions']:,}")


# ------------------------------------------------------------------ Stage B: the one read (refuses unless the lead's go-flag is on file)
def stage_b():
    """STAGE B (LB, once, on the stock families' one sealed-year day): REFUSES unless the lead's go-flag edrift_stageB_GO.flag is on file (the lead writes it after the hand audit (f) and only on that day; CHOICE (r18's): its EXISTENCE is the sign-off - its text is stored with the read and never
    parsed) and a Stage A candidate is on file. The sealed year is the LEG's standalone veto (r17_resmom's: >= 10 monthly rebalances, net > 0, net > 0 without its top name-month). The book add (#463 + c x the cell at Stage A's frozen c) is computed, printed and stored as
    book_add_reported - NEVER part of the pass. Every refusal is before the read flag; the flag is written (exclusively) only after every load, every check and the whole result are in hand. CHOICE: the lead's Russell list must cover every June the lockbox data holds (it stops at 2025;
    a dated addendum extends it - check_russell refuses first)"""
    go, flag = os.path.join(OUT, GO_FLAG), os.path.join(OUT, READ_FLAG)
    if not os.path.exists(go):
        refuse(f"Stage B refused: the lead's go-flag {GO_FLAG} is not on file - the hand audit (f) and the sealed-year day are the lead's call; the lockbox stays sealed (nothing computed, lockbox NOT read)")
    if os.path.exists(flag):
        refuse(f"Stage B refused: the lockbox was already read once ({READ_FLAG})")
    pa = os.path.join(OUT, "edrift_stageA.json")
    sa = json.load(open(pa)) if os.path.exists(pa) else {}
    cand = sa.get("candidate")
    ok_a = isinstance(cand, dict) and sa.get("judged") is True and cand.get("cell") in ((sa.get("stageA") or {}).get("pass_cells") or [])
    if not ok_a:
        refuse("Stage B refused: no Stage A candidate (a cell that passes (a)-(e)) is on file - the lockbox stays sealed.")
    prereg_ok()
    if sa.get("prereg_sha256_lf") != PREREG_SHA:
        refuse("Stage B refused: Stage A ran under another pre-registration (lockbox NOT read)")
    bad = [k for k, v in stamp().items() if sa.get(k) != v]
    if bad:
        refuse(f"Stage B refused: Stage A was written by a different harness version / early-close list ({', '.join(bad)} differs or is missing) - run stage_a again (lockbox NOT read)")
    if sa.get("audit_sha256") != file_sha(os.path.join(OUT, "edrift_audit.csv")):
        refuse("Stage B refused: edrift_audit.csv is not the file Stage A ran with (it changed, or went missing) - run stage_a again (lockbox NOT read)")
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
    D = M17.load_data(S.END)
    tbis = D15.load_tbis(S.END)
    es_frames, es_meta = D15.load_es(S.END)
    audit = read_audit()
    W = M17.build_world(D, S.END, es_frames, tbis, cal)
    D15.release(D)
    cut_checks(W, cal, S.END)
    check_russell(W.days)
    apply_audit(W, audit)
    rows = A13.book_rows(B, W)
    hole_txt, hole_rec = M17.es_report(W, LB0, LB1)                                            # the ES holes that reach the lockbox: printed and stored with the read
    attach_events(W)
    Lw = ed_build(W, WF0, PRE_END)                                                             # Stage A's WF numbers (and the frozen c) must reproduce on Stage B's data (a cache or code drift stops it BEFORE the read)
    run = M17.run_cell(W, cell_leg(Lw, cell), D15.l1_cfg())                                    # CHOICE: only the candidate cell is re-read (it is the only one Stage B reads)
    xw = D15.to_B(run.x, rows, B.n)
    st, ref = D15.cell_stats(B, xw, D15.to_B(run.cnt, rows, B.n), WF0, PRE_END, run), sa["parity"][cell]
    print(f"WF re-read on Stage B's data: {cell} positions {st['n_pos']:,} (Stage A {ref['n_pos']:,}), net ${st['net']:,.0f} (Stage A ${ref['net']:,.0f})")
    if st["n_pos"] != ref["n_pos"] or st["n_units"] != ref["n_units"] or abs(st["net"] - ref["net"]) > max(1.0, 1e-6 * abs(ref["net"])):
        refuse(f"Stage B refused: the WF numbers of {cell} do not reproduce on Stage B's data - the cache or the code changed since Stage A (lockbox NOT read)")
    c2 = plain_a2(B, xw)["c"]
    print(f"  frozen size {cell}: c x{c:.6g} (Stage A) vs x{c2:.6g} recomputed from {A2_WIN[0]:%Y-%m-%d} .. {A2_WIN[1]:%Y-%m-%d} on Stage B's data")
    if not (math.isfinite(c2) and abs(c2 - c) <= 1e-9 * c):
        refuse(f"Stage B refused: the volatility-set size c of {cell} does not reproduce on Stage B's data - the cache or the code changed since Stage A (lockbox NOT read)")
    L = ed_build(W, LB0, LB1)                                                                  # CHOICE (r15's order): the whole LB result is computed, nothing shown, BEFORE the flag
    run = M17.run_cell(W, cell_leg(L, cell), D15.l1_cfg(), pos=True)
    xB, cB = D15.to_B(run.x, rows, B.n), D15.to_B(run.cnt, rows, B.n)
    leg = D15.cell_stats(B, xB, cB, LB0, LB1, run)
    r = D15.book_at(B, xB, c, LB0, LB1)                                                        # the book add at the FROZEN c - c is never re-set on the sealed year
    would = M17.book_add_would_clear(r)                                                        # the old sealed-year bar (#463's own LB numbers, 155.54 / 4.150): reported, never judged
    chk = M17.b_checks(leg)
    ok = all(chk.values())                                                                     # the pass is the LEG's veto - the book add below is a report and is not in this line
    add = {"c": c, "roc": r["roc"], "sortino": r["sortino"], "net": r["net"], "max_dd": r["max_dd"], "reference": {"roc": RULES["b_roc"], "sortino": RULES["b_sort"]}, "would_have_cleared": would,
           "note": "reported, never a pass (MANAGER #48): the forward record decides any book add (owner call)"}
    cnt = {y: dict(v) for y, v in sorted(L.cnt.items())}
    cands = ed_candidate_rows(W, L, cell, run, tbis, D15.asset_status(), 20)
    text = json.dumps({"cell": cell, "c": c, "go_flag": go_text, "book_check": bk, "es_masters": es_meta, "leg": leg, "checks": chk, "pass": bool(ok), "book_add_reported": add, "es_return_lb": hole_rec, "wide_calendar": W.ca,
                       "events": W.ed.counts[cell], "hygiene_counts_by_year": cnt, "top_name_months": cands, **stamp(), "prereg_sha256_lf": PREREG_SHA}, indent=1, default=R11.js)
    buf = io.StringIO()                                                                        # the whole printout is built here, before the flag: a formatting error cannot burn the lockbox
    with contextlib.redirect_stdout(buf):
        print("Stage B (lockbox, read once) - the sealed year is the LEG's standalone veto")
        print(f"  {cell}: positions {leg['n_pos']:,}, monthly rebalances {leg['n_units']:,}, net ${leg['net']:,.0f}, ROC@30k {leg['roc']:.1f}, Sortino {leg['sortino']:.2f}; its top name-month ${leg['top_pos']:,.0f}, "
              f"net without it ${leg['net_ex_top_pos']:,.0f}")
        print("  " + hole_txt)
        print("  Stage B checks: " + ", ".join(k + (" ok" if v else " FAIL") for k, v in chk.items()) + f" -> {'PASS' if ok else 'FAIL'}")
        print(f"  book add, REPORTED and never part of the pass: #463 + {cell} x{c:.4g} (frozen): LB ROC@30k {r['roc']:.2f} Sortino {r['sortino']:.3f} net ${r['net']:,.0f} -> would "
              f"{'have' if would else 'NOT have'} cleared {RULES['b_roc']:g} / {RULES['b_sort']:g}")
        print("EDRIFT Stage B: " + ("PASS - the leg survives its sealed year: it goes to a computed no-order FORWARD SHADOW (Stage C) with its own bar, logged by research id; the book add above is a report - "
                                    "the forward record decides any book add, and opening any account is the owner's decision (owner call)." if ok else
                                    "FAIL - the leg is vetoed by its sealed year: EDRIFT r1 is dead; ledger + memory."))
    with open(flag, "x") as f:                                                                 # exclusive create: the one read starts here - what is left is two writes and a print
        f.write(pd.Timestamp.now().isoformat())
    with open(os.path.join(OUT, "edrift_stageB.json"), "w") as f:
        f.write(text)
    print(buf.getvalue().rstrip())
    pm = peak_mb()
    if pm:
        print(f"peak memory {pm:,.0f} MB")
    return ok


# ------------------------------------------------------------------ test support: hand-made worlds with planted events, and plain-python recounts of every event, pool, score, pick and path (independent of the vectorised code)
THIS = sys.modules[__name__]


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


def close(a, b, tol=1e-9):
    return D15.close(a, b, tol)


def dr_(W, s):
    return W.days.get_loc(TS(s))


def brute_mech(days, russell=None):
    """plain python: the third Fridays of March / June / September / December (a Friday whose day of the month is 15 .. 21) and the listed Russell days, each as a set of Timestamps present in `days`"""
    listed = RUSSELL_DAYS if russell is None else russell
    tf = {d for d in days if d.dayofweek == 4 and d.month in (3, 6, 9, 12) and 15 <= d.day <= 21}
    ru = {d for d in days if f"{d:%Y-%m-%d}" in listed}
    return tf, ru


def brute_beta(W, r, j):
    """the OLS slope (an intercept and a slope) of name j's split-safe TOTAL daily return on ES's over the finite pairs of rows r-251 .. r, by numpy's least squares (not the closed form of ed_beta)"""
    a = M17.windows(r)[0]
    pairs = [(M17.brute_ret(W, s, j), float(W.es.ret[s])) for s in range(a, r + 1)]
    pairs = [(y, m) for y, m in pairs if math.isfinite(y) and math.isfinite(m)]
    if len(pairs) < 3:
        return float("nan")
    coef = np.linalg.lstsq(np.array([[1.0, m] for _y, m in pairs]), np.array([y for y, _m in pairs]), rcond=None)[0]
    return float(coef[1])


def brute_kind(W, cell, t, j, tf, ru):
    """plain python: what becomes of the (session t, name j) pair for the cell -> None (no volume event), 'excluded' ([E1]), 'hygiene' (a flag on t-1 .. t+1), 'data' (a return or ES's undefined on one of them) or 'valid'. The volume rule is the cross-multiplied form of
    'volume >= K x the mean of the present baseline sessions' on the split-adjusted volume (raw x F)"""
    sp = SPEC
    if t < sp["base_lo"] or t + 1 >= W.T:
        return None
    va = lambda s: float(W.Vv[s, j] * W.F[s, j])
    v = va(t)
    base = [x for x in (va(s) for s in range(t - sp["base_lo"], t - sp["base_hi"] + 1)) if math.isfinite(x)]
    if not math.isfinite(v) or len(base) < sp["base_min"] or not sum(base) > 0 or not v * len(base) >= KS[cell] * sum(base):
        return None
    d, p = W.days[t], W.days[t - 1]
    if d in tf or d in ru or p in tf or p in ru:
        return "excluded"
    if any(any(D15.brute_flags(W, s, j)) for s in (t - 1, t, t + 1)):
        return "hygiene"
    if not all(math.isfinite(M17.brute_ret(W, s, j)) and math.isfinite(float(W.es.ret[s])) for s in (t - 1, t, t + 1)):
        return "data"
    return "valid"


def brute_side(n):
    """plain python: the sides a rebalance with n scored names trades -> (names a side, mode)"""
    if n >= SPEC["min_scored"]:
        return M17.SPEC["n_side"], "top"
    k = n // 3
    return (k, "third") if k >= SPEC["min_side"] else (0, "none")


def brute_ed(W, lo, hi, post_mode="remove", russell=None):
    """every rebalance whose position exits in [lo, hi], plain python end to end (the schedule from the months of consecutive sessions, the universe taken from W.U, the pool rules re-implemented with loops, the events by brute_kind, the reaction as a plain sum with the
    beta from numpy's least squares): [{r, f, x, pool: {col: {beta, naive, res, [HYG-S1] ex = the first [D2] ex-date in the hold under 'close', else -1}}, cell: {c: {score: {col: (t, reaction)}, k, mode, long, short}}}]"""
    sp, M = SPEC, M17.SPEC
    Sp = getattr(W, "Sp_in", None)
    tf, ru = brute_mech(W.days, russell)
    key = [(W.days[i].year, W.days[i].month) for i in range(W.T)]
    ranks = [i for i in range(W.T - 1) if key[i] != key[i + 1]]
    recs = []
    for k, r in enumerate(ranks):
        f, x = r + 1, (ranks[k + 1] + 1 if k + 1 < len(ranks) else -1)
        if x < 0 or not (lo <= W.days[x] <= hi) or r < M["win"] - 1:
            continue
        a, lo_pre = M17.windows(r)[0], r - M["skip"] - M["hyg_lead"] + 1
        pool = {}
        for j in [j for j in range(W.S) if W.U[f, j]]:
            hold = Sp is not None and any(bool(Sp[s, j]) for s in range(f + 1, x + 1))
            n_ret, n_pair, res, _raw = M17.brute_scores(W, r, j)
            beta = brute_beta(W, r, j)
            if n_ret < M["min_n"] or n_pair < M["min_n"] or not math.isfinite(W.Od[f, j] / W.F[f, j]) or not math.isfinite(beta):
                continue
            pre = any(any(D15.brute_flags(W, s, j)) for s in range(max(lo_pre, 0), r + 1))
            old = any(any(D15.brute_flags(W, s, j)[1:]) for s in range(max(a, 0), lo_pre))
            post = hold or any(any(D15.brute_flags(W, s, j)) for s in range(r + 1, x + 1))
            if pre or old or W.aud1[f, j] or (post and post_mode == "remove"):
                continue
            ex = next((s for s in range(f + 1, x + 1) if Sp is not None and Sp[s, j]), -1) if post_mode == "close" else -1      # [HYG-S1] the first [D2] ex-date inside the hold: the position closes at the close before it
            pool[j] = {"beta": beta, "naive": bool(post and post_mode == "naive"), "res": res, "ex": ex}
        rec = {"r": r, "f": f, "x": x, "pool": pool, "cell": {}}
        for c in CELLS:
            sc = {}
            for j in pool:
                for t in range(r - 1, r - sp["look"] - 1, -1):                                  # the most recent valid event first: rows r-1 down to r-63
                    if brute_kind(W, c, t, j, tf, ru) == "valid":
                        sc[j] = (t, sum(M17.brute_ret(W, s, j) - pool[j]["beta"] * float(W.es.ret[s]) for s in (t - 1, t, t + 1)))
                        break
            kk, mode = brute_side(len(sc))
            order = sorted(sc, key=lambda j: (sc[j][1], j))
            rec["cell"][c] = {"score": sc, "k": kk, "mode": mode, "short": order[:kk], "long": order[::-1][:kk] if kk else []}
        recs.append(rec)
    return recs


def brute_event_counts(W, russell=None):
    """plain python: per cell the volume events / excluded (by kind) / hygiene-voided / data-voided / valid of EVERY (session, name) pair by calendar year of the session - attach_events' counts recounted"""
    tf, ru = brute_mech(W.days, russell)
    out = {}
    for c in CELLS:
        cn = {k: Counter() for k in ("volume", "excluded", "void_hygiene", "void_data", "valid", "excluded_third_friday", "excluded_session_after_third_friday", "excluded_russell_day", "excluded_session_after_russell_day")}
        for t in range(W.T):
            for j in range(W.S):
                kd = brute_kind(W, c, t, j, tf, ru)
                if kd is None:
                    continue
                y = int(W.days[t].year)
                cn["volume"][y] += 1
                if kd == "excluded":
                    cn["excluded"][y] += 1
                    d, p = W.days[t], W.days[t - 1]
                    cn["excluded_third_friday" if d in tf else "excluded_session_after_third_friday" if p in tf and d not in ru else "excluded_russell_day" if d in ru else "excluded_session_after_russell_day"][y] += 1
                elif kd == "hygiene":
                    cn["void_hygiene"][y] += 1
                elif kd == "data":
                    cn["void_data"][y] += 1
                else:
                    cn["valid"][y] += 1
        out[c] = {k: dict(v) for k, v in cn.items()}
    return out


def nz_counts(counts):
    """per cell {kind: {year: n}} with the zero entries dropped (the recount only records what it counts)"""
    return {c: {k: {y: v for y, v in d.items() if v} for k, d in counts[c].items()} for c in CELLS}


def brute_pos_ed(W, b, j, sd, **kw):
    """one recount position's daily path per $1 (kw = bps / borrow / kt / lose100): closed at the close before its spin-off / stock-dividend ex-date [HYG-S1], or held to the exit (on the path its naive flag says)"""
    ex = b["pool"][j]["ex"]
    return M17.brute_close_path(W, b["f"], b["x"], j, sd, ex, **kw)[0] if ex >= 0 else M17.brute_path(W, b["f"], b["x"], j, sd, bool(b["pool"][j]["naive"]), **kw)[0]


def compare_ed(W, L, Bz, tag, check_res=True):
    """the vectorised build against the plain-python recount: the schedule, every pool (names, betas, RES, the naive flags, [HYG-S1] the close rows), each cell's scored names with their event row, age and reaction, the mode, the picks (longs / shorts, disjoint), and the daily path of every PICKED
    name - and of every scored name closed before a spin-off / stock-dividend ex-date, picked or not - under four costings (base, 10 bps, the 3% borrow stress with k_t, longs at -100%)"""
    assert len(L.recs) == len(Bz), (tag, len(L.recs), len(Bz))
    cfgs = (("base", D15.l1_cfg(), {}), ("10 bps", D15.l1_cfg(bps=10.0), {"bps": 10.0}), ("borrow 3%", D15.l1_cfg(borrow=(BORROW, 0.03)), {"borrow": (BORROW, 0.03), "k": True}), ("lose100", D15.l1_cfg(lose100=True), {"lose100": True}))
    n_paths = 0
    for rec, b in zip(L.recs, Bz):
        assert (rec.r, rec.f, rec.x) == (b["r"], b["f"], b["x"]), tag
        assert rec.pool.tolist() == sorted(b["pool"]), (tag, rec.r, rec.pool.tolist(), sorted(b["pool"]))
        assert close(rec.beta, [b["pool"][j]["beta"] for j in rec.pool]), (tag, rec.r, "beta")
        assert not check_res or close(rec.res, [b["pool"][j]["res"] for j in rec.pool]), (tag, rec.r, "RES")
        assert rec.naive.tolist() == [b["pool"][j]["naive"] for j in rec.pool], (tag, rec.r)
        assert rec.close.tolist() == [(b["pool"][j]["ex"] - 1 if b["pool"][j]["ex"] >= 0 else -1) for j in rec.pool], (tag, rec.r, "[HYG-S1] the close rows")
        for c in CELLS:
            cc, bc = rec.cell[c], b["cell"][c]
            cols = rec.pool[cc.idx].tolist()
            assert cols == sorted(bc["score"]), (tag, rec.r, c, cols, sorted(bc["score"]))
            assert cc.tstar.tolist() == [bc["score"][j][0] for j in cols] and cc.age.tolist() == [rec.r - bc["score"][j][0] for j in cols], (tag, rec.r, c, "event row / age")
            assert close(cc.score, [bc["score"][j][1] for j in cols]), (tag, rec.r, c, "reaction")
            assert (cc.n, cc.k, cc.mode, cc.traded) == (len(cols), bc["k"], bc["mode"], bc["k"] > 0), (tag, rec.r, c)
            if not cc.traded:
                assert len(cc.long) == 0 and len(cc.short) == 0
                continue
            assert rec.pool[cc.idx[cc.long]].tolist() == bc["long"] and rec.pool[cc.idx[cc.short]].tolist() == bc["short"], (tag, rec.r, c, "picks")
            assert not set(bc["long"]) & set(bc["short"]), "a name is never on both sides"
            kt = W.k[rec.f:rec.x + 1]
            idx = np.arange(cc.n)
            for nm, cfg, kw in cfgs:
                kw2 = {"bps": kw.get("bps", COST_BPS), "borrow": kw.get("borrow", (BORROW, None)), "kt": kt if kw.get("k") else None, "lose100": kw.get("lose100", False)}
                for sd, js in ((1, bc["long"]), (-1, bc["short"])):
                    P = M17.l1_pnl_x(cc.U, idx, sd, cfg, kt)                                          # (r15's l1_pnl + [HYG-S1]'s exit column; the cells run through it too)
                    for j in js:
                        assert close(P[cols.index(j)], brute_pos_ed(W, b, int(j), sd, **kw2)), (tag, nm, rec.r, c, int(j), sd)
                        n_paths += 1
                    for i_, j in enumerate(cols):                                                      # [HYG-S1] a scored name closed before a spin-off ex-date, picked or not
                        if b["pool"][j]["ex"] >= 0 and j not in js:
                            assert close(P[i_], brute_pos_ed(W, b, int(j), sd, **kw2)), (tag, nm, rec.r, c, int(j), sd, "closed")
                            n_paths += 1
    n_close = sum(1 for b in Bz for j in b["pool"] if b["pool"][j]["ex"] >= 0)                         # [HYG-S1] the pool names closed before an ex-date (scored or not)
    assert sum(c.get("closed_spin", 0) for c in L.cnt.values()) == n_close, (tag, "closed_spin", n_close)
    return n_paths


def series_check(W, L, Bz):
    """each cell's daily series (run_cell on r15's L1 engine, $4,000 a name) equals the sum of the recount's position paths booked on rows f .. x"""
    for cell in CELLS:
        x0 = np.zeros(W.T)
        for b in Bz:
            bc = b["cell"][cell]
            for sd, js in ((1, bc["long"]), (-1, bc["short"])):
                for j in js:
                    x0[b["f"]:b["x"] + 1] += M17.SPEC["slot"] * np.array(brute_pos_ed(W, b, j, sd))
        assert close(M17.run_cell(W, cell_leg(L, cell), D15.l1_cfg()).x, x0), f"{cell} series"


# ------------------------------------------------------------------ the hand-made worlds
EVA = {"t": 50, "es_hole": None}      # world A's event session (a Monday: 2024-03-11) and its optional ES hole


def ev_world_a(T=100, es_hole=None):
    """100 weekdays from Monday 2024-01-01 x 24 names, constant volume 1,000,000, one case per name (the event session is row 50, Monday 2024-03-11, its baseline rows 29 .. 48; the third Friday of March is row 54):
    N00 3.0 x (V3 only) / N01 2.999 x (neither) / N02 5.0 x (both) / N03 4.999 x (V3 only) / N04 3.5 x with 15 of the 20 baseline sessions present (an event) / N05 the same with 14 (no event) / N06 a TBIS flag on t-1 / N07 on t+1 (voided) / N08 on t+2 / N09 on t-2 (still
    events) / N10 on t (voided) / N11 a 20 x spike inside the baseline (itself a valid event on row 40) and an event day of 4 x (no event: the baseline is 1.95 x) / N12 the same baseline and 6 x (a V3 event) / N13 zero volume everywhere but row 50 (a zero baseline is no baseline: no
    event) / N14 a missing close on t+1 (no return: voided) / N15 a 2-for-1 split on row 45 (the raw volume doubles, F 2 -> 1): 2.9 x of the ADJUSTED baseline on row 50 (no event; of the raw baseline it would be 4.8 x) and 3.6 x on row 70 (an event: its baseline holds the 2.9 x day, 1.095 x). [E1] probes with 6 x on one session each: N16 row 54 (the third Friday), N17 row 55 (the session after), N18 row 53, N19 row 56 (events), N20 row 84 (Friday 2024-04-26, a
    custom Russell day), N21 row 85 (the session after), N22 row 83, N23 row 86 (events). es_hole = a row on which ES has no return"""
    rng = np.random.default_rng(5)
    Sn = 24
    ret = rng.normal(0.0, 0.01, (T, Sn))
    ret[0] = 0.0
    es = rng.normal(0.0, 0.008, T)
    es[0] = np.nan
    if es_hole is not None:
        es[es_hole] = np.nan
    Cl = M17.prices(ret)
    Vv = np.full((T, Sn), 1.0e6)
    F, chg, tb = np.ones((T, Sn)), np.zeros((T, Sn), bool), np.zeros((T, Sn), bool)
    t = EVA["t"]
    for j, m in ((0, 3.0), (1, 2.999), (2, 5.0), (3, 4.999), (4, 3.5), (5, 3.5), (6, 3.5), (7, 3.5), (8, 3.5), (9, 3.5), (10, 3.5), (11, 4.0), (12, 6.0), (13, 1.0), (14, 3.5)):
        Vv[t, j] = m * 1.0e6
    Vv[30:35, 4], Vv[30:36, 5] = np.nan, np.nan
    tb[t - 1, 6], tb[t + 1, 7], tb[t + 2, 8], tb[t - 2, 9], tb[t, 10] = True, True, True, True, True
    Vv[40, 11] = Vv[40, 12] = 20.0e6
    Vv[:, 13] = 0.0                                                                                      # N13 trades no volume at all but one session: a zero baseline on row 50
    Vv[t, 13] = 1.0e6
    Cl[t + 1, 14] = np.nan
    F[:45, 15], chg[45, 15] = 2.0, True
    Vv[:45, 15], Vv[45:, 15], Vv[t, 15], Vv[70, 15] = 0.5e6, 1.0e6, 2.9e6, 3.6e6
    for j, row in ((16, 54), (17, 55), (18, 53), (19, 56), (20, 84), (21, 85), (22, 83), (23, 86)):
        Vv[row, j] = 6.0e6
    return M17.mk_world(Cl, es, F=F, chg=chg, tbis=tb, Vv=Vv)


EVA_RUSSELL = ("2024-04-26",)         # world A's custom Russell day (a Friday inside its 100 sessions)


def ev_world_b(seed=2, T=330, scramble_after=None):
    """the reaction world: 8 names on 330 weekdays (the first rank with a full 252-session window is row 261, 2024-12-31), every return EXACTLY beta_j x ES's plus planted shocks on the 3 sessions of each event, the volume constant 1,000,000 except the events:
    N00 events at row 250 (age 11 at the first rank, 6 x) and row 205 (age 56, 6 x - an older event the most recent one replaces), N01 row 210 (age 51, 4 x: a V3 event only), N02 row 250 at 2.5 x (no event), N03 row 261 (the rank close itself: t + 1 would be past it - not in the window of the
    first rank, in the window of the next), N04 row 260 (age 1, t + 1 = r), N05 row 198 (age 63, the window's first row), N06 row 197 (age 64: out), N07 none. Each event's three shocks (x, y, z) are chosen so that sum (m - mean m) x shock = 0 over the first rank's regression pairs: the OLS slope is then
    EXACTLY the planted beta and the reaction is exactly x + y + z (no regression to hand-solve). scramble_after = a row from which on returns, ES and volume are replaced by noise. -> (W, {(row, col): (x, y, z)}, the planted betas, the first rank's row)"""
    rng = np.random.default_rng(seed)
    Sn = 8
    m = rng.normal(0.0, 0.01, T)
    m[0] = np.nan
    beta = np.linspace(0.6, 1.5, Sn)
    ret = beta * np.nan_to_num(m)[:, None]
    ret[0] = 0.0
    Vv = np.full((T, Sn), 1.0e6)
    r0 = int(pd.bdate_range("2024-01-01", periods=T).get_loc(TS("2024-12-31")))
    a = M17.windows(r0)[0]
    mbar = float(np.mean(m[a:r0 + 1]))
    planted = {}
    plan = ((0, 250, 6.0, (0.010, 0.060)), (0, 205, 6.0, (-0.020, 0.030)), (1, 210, 4.0, (0.005, -0.045)), (2, 250, 2.5, (0.01, 0.02)), (3, 261, 6.0, (0.012, -0.050)), (4, 260, 6.0, (-0.008, 0.040)), (5, 198, 6.0, (0.004, 0.025)), (6, 197, 6.0, (0.006, 0.070)))
    for j, t, mult, (sx, sy) in plan:
        Vv[t, j] = mult * 1.0e6
        sz = -(sx * (m[t - 1] - mbar) + sy * (m[t] - mbar)) / (m[t + 1] - mbar)       # sum (m - mbar) x shock = 0: the shocks leave the OLS slope exactly beta_j
        for dt, s in ((-1, sx), (0, sy), (1, sz)):
            ret[t + dt, j] += s
        planted[(t, j)] = (sx, sy, sz)
    if scramble_after is not None:                                                                       # everything from that row on (returns, ES, volume) replaced: the rows before it are untouched
        r2 = np.random.default_rng(seed + 100)
        m = m.copy()
        m[scramble_after:] = r2.normal(0.0, 0.02, T - scramble_after)
        ret[scramble_after:] = r2.normal(0.0, 0.03, (T - scramble_after, Sn))
        Vv[scramble_after:] = r2.uniform(0.5e6, 9.0e6, (T - scramble_after, Sn))
    Cl = M17.prices(ret)
    return M17.mk_world(Cl, m, Vv=Vv), planted, beta, r0



# ------------------------------------------------------------------ selftest: hand-made worlds, no files, no data
def t_constants():
    assert (NREP, SEED, SEED_PLACEBO, CELLS, AUDIT_N) == (500, 20261005, 20261006, ("V3", "V5"), 50) and KS == {"V3": 3, "V5": 5} and YEARS == tuple(range(2016, 2025))
    assert (WF0, PRE_END, LB0, LB1) == (TS("2016-07-01"), TS("2025-06-29"), TS("2025-06-30"), TS("2026-06-30")) and (S.LB0, S.END) == (LB0, R11.LBX) and (BOOK_WF, BOOK_LB, DEEPEST_WF) == ((93.81, 3.816), (155.54, 4.15), 44849.0)
    assert SPEC == {"look": 63, "age_cut": 21, "base_lo": 21, "base_hi": 2, "base_min": 15, "min_scored": 150, "min_side": 20, "pl_near": 3, "path_lo": 2, "path_hi": 60}, "this file's SPEC is the prereg: 63-session lookback, a 20-session baseline t-21 .. t-2 with 15 present, 150 / 20"
    assert M17.SPEC == {"win": 252, "form_n": 231, "skip": 21, "min_n": 230, "n_side": 50, "slot": 4000.0, "hyg_lead": 5}, "RESMOM's machinery: 252-session regression, 230 pairs, 50 + 50 at $4,000"
    assert SPEC["base_lo"] - SPEC["base_hi"] + 1 == 20 and SPEC["age_cut"] == 21 and SPEC["look"] - SPEC["age_cut"] == 42
    assert (COST_BPS, STRESS_BPS, BORROW, BORROW_STRESS) == (5.0, (10.0, 20.0), 0.0025, (0.01, 0.03)) and HYG == ("split", "gap", "tbis", "jump") and M17.K_STRESS == 1.5
    assert RULES is M17.RULES and RULES["reb"] == 60 and RULES["roc"] == 15.0 and RULES["years"] == 6 and RULES["best_pct"] == 1 and RULES["b_reb"] == 10 and (RULES["b_roc"], RULES["b_sort"]) == BOOK_LB
    assert all(RULES[k] is True for k in ("net_pos", "stress", "null", "ex2020", "exbest")) and CHECK_BOOK is True, "every registered check is on (the switches are for smoke() only)"
    assert (A2_WIN, A2_TARGET, A2_REPORT) == ((TS("2017-01-03"), TS("2018-12-31")), 0.25, (0.5, 2.0)) and SUBPERIODS[0][1:] == (TS("2016-07-01"), TS("2021-12-31")) and SUBPERIODS[1][1:] == (TS("2022-01-01"), TS("2025-06-29"))
    assert THIRD_FRIDAY_MONTHS == (3, 6, 9, 12) and len(RUSSELL_DAYS) == 10 and RUSSELL_DAYS[0] == "2016-06-24" and RUSSELL_DAYS[-1] == "2025-06-27" and "2023-06-23" in RUSSELL_DAYS
    assert all(TS(d).dayofweek == 4 and 22 <= TS(d).day <= 28 and TS(d).month == 6 for d in RUSSELL_DAYS) and [TS(d).year for d in RUSSELL_DAYS] == list(range(2016, 2026)), "the fourth Friday of June, 2016 .. 2025"
    assert CAL_SHA == "8f4f9f4bc61dc671a6f169f37f72c334fa3aecafff87a06af5ab250bcc85d4db" and CAL_COLS == ("ticker", "ndx_tickers", "reaction_session") and os.path.basename(CAL_CSV) == "earnings_calendar_ndx.csv"
    assert (GO_FLAG, READ_FLAG) == ("edrift_stageB_GO.flag", "edrift_stageB_READ.flag") and EARN_MONTHS == ((1, 4, 7, 10), (1, 2, 4, 5, 7, 8, 10, 11)) and PATH_AT == (5, 10, 21, 42, 60)
    assert OUT_DEFAULT.replace(chr(92), "/").lower().endswith("rocfrontier/edrift_r1")
    pre = " ".join(open(PREREG, encoding="utf-8").read().split())                                          # the registered text carries every number this file implements (line breaks normalised)
    for frag in ("inside the 63 sessions before the rank close r", "volume_t >= K x the name's mean volume over t-21 .. t-2", "K = 3 or 5 by cell", "at least 15 of those 20 sessions present", "no hygiene flag on t-1 .. t+1", "t+1 <= r",
                 "a month with fewer than 150 scored names trades the top / bottom third, at least 20 a side, else nothing", "$4,000 each", "5 bps a side base, stress 10 and 20", "0.25%/yr on short notional, stress 1% and 3%/yr",
                 "500 draws, seed 20261005", "500 draws, seed 20261006", "(no event day within 2 sessions of it)", "third Friday of March, June, September or December", "the fourth Friday",
                 "0-21 vs 22-63 sessions before the rank close", "2017-01-03 .. 2018-12-31", "0.264 x RES", "120.82", "3.916", "$36,526", "the cost curve at 0 / 5 / 10 / 20 bps a side", "an incremental pass = both figures above the reference's",
                 "from t+2 to t+60, by reaction decile", "the share of EDRIFT's events whose session t is a release's reaction session or the session after it", "the join is on ndx_tickers, split on ';'", "Foreign filers on 6-K (13 names) stay absent and are listed",
                 CAL_SHA, DV.REF_SHA, "2016-07 .. 2021-12 and 2022-01 .. 2025-06"):
        assert frag in pre, frag
    with contextlib.redirect_stdout(open(os.devnull, "w")):
        assert prereg_ok()["verified"] is True
    sk = stamp()
    assert len(sk["harness_sha256"]) == 64 and set(sk) >= {"r17_sha256", "r18_sha256", "r15_sha256", "siporb_sha256", "r11_sha256", "r12_sha256", "r13_sha256", "wide_ca_sha256", "early_close", "earnings_calendar_sha256", "russell_days"}, sorted(sk)
    assert sk["earnings_calendar_sha256"] == CAL_SHA and sk["russell_days"] == list(RUSSELL_DAYS) and sk["r18_sha256"] == R11.sha_lf(DV.__file__) and sk["r17_sha256"] == R11.sha_lf(M17.__file__)
    assert jyear(["2017-06-30", "2017-07-03", "2016-07-01", "2025-06-27"]).tolist() == [2016, 2017, 2016, 2024]
    assert HERE == os.path.dirname(os.path.abspath(__file__)) and os.path.basename(PREREG) == "PREREG_EDRIFT_R1.txt"
    with spec(look=5, win=40, n_side=1):                                                                  # spec() routes a key to this file's SPEC or r17_resmom's, and puts both back
        assert SPEC["look"] == 5 and M17.SPEC["win"] == 40 and M17.SPEC["n_side"] == 1
    assert SPEC["look"] == 63 and M17.SPEC["win"] == 252 and M17.SPEC["n_side"] == 50


def t_mech():
    """[E1]: the third Friday of March / June / September / December by rule (and against the repo's own quad_witching_dates.csv), the Russell days the lead listed (the fourth Friday of June, each a Friday and a session), the session after each, a third Friday that is
    not a session moves to the last session on / before it, a Russell day outside the data is not placed, a year the data covers with no listed date refuses"""
    assert third_friday(2024, 3) == TS("2024-03-15") and third_friday(2023, 6) == TS("2023-06-16") and third_friday(2026, 6) == TS("2026-06-19") and third_friday(2020, 12) == TS("2020-12-18") and third_friday(2016, 9) == TS("2016-09-16")
    qw = os.path.join(os.path.dirname(HERE), "data", "quad_witching_dates.csv")
    if os.path.exists(qw):                                                                               # an independent list of the same dates, derived elsewhere in the repo
        rows = [l.split(",")[0] for l in open(qw).read().splitlines() if l[:2] == "20"]
        assert len(rows) > 40 and all(third_friday(TS(d).year, TS(d).month) == TS(d) for d in rows), "the rule reproduces the repo's quad-witching list"
    days = pd.bdate_range("2016-01-04", "2025-06-27")
    tf, ru = mech_days(days)
    want = {third_friday(y, m) for y in range(2016, 2026) for m in THIRD_FRIDAY_MONTHS} & set(days)
    assert tf.sum() == len(want) == 38 and {days[i] for i in np.flatnonzero(tf)} == want and ru.sum() == 10 and {f"{days[i]:%Y-%m-%d}" for i in np.flatnonzero(ru)} == set(RUSSELL_DAYS)
    assert {days[i] for i in np.flatnonzero(tf)} == brute_mech(days)[0] and {days[i] for i in np.flatnonzero(ru)} == brute_mech(days)[1]
    # a third Friday that is not a session (a holiday) -> the last session on / before it (within 4 calendar days); a Russell day outside the data is not placed
    dh = days.drop(TS("2024-03-15"))
    tfh, _ = mech_days(dh)
    assert tfh[dh.get_loc(TS("2024-03-14"))] and not tfh[dh.get_loc(TS("2024-03-18"))] and tfh.sum() == 38
    dm = days[days < TS("2024-06-28")]
    assert mech_days(dm)[1].sum() == 8 and mech_days(days, russell=("2030-06-28",))[1].sum() == 0 and mech_days(days, russell=("2024-06-28",))[1].sum() == 1
    assert mech_days(pd.DatetimeIndex([]))[0].shape == (0,)
    assert check_russell(days) is True and check_russell(pd.bdate_range("2016-01-04", "2016-05-31")) is True, "the default list covers every June 2016 .. 2025; a data span without a June needs none"
    tail = "(nothing computed, lockbox NOT read)"
    refused(lambda: check_russell(days, listed=("2024-06-27",)), "not a Friday", tail)
    refused(lambda: check_russell(days.drop(TS("2024-06-28")), listed=("2024-06-28",)), "not a session of the data", tail)
    refused(lambda: check_russell(pd.bdate_range("2016-01-04", "2026-06-30")), "the data covers June 2026 and the lead's Russell list has no date for it", tail)
    assert check_russell(pd.bdate_range("2016-01-04", "2026-05-29")) is True and check_russell(pd.bdate_range("2016-01-04", "2026-06-26"), listed=RUSSELL_DAYS + ("2026-06-26",)) is True


def t_events():
    """the volume event rule on a hand-made world, case by case: K inclusive (3.0 x is a V3 event, 2.999 x is not; 5.0 x is a V5 event, 4.999 x is not), at least 15 of the 20 baseline sessions present (15 in, 14 out), a flag on t-1 / t / t+1 voids the event and one on
    t-2 / t+2 does not, a missing return voids it, a baseline that holds a spike, a zero baseline, the SPLIT-ADJUSTED volume (raw x F), [E1] (a third Friday, a custom Russell day, the session after each: excluded and counted by kind; the sessions around them are events), the counts by
    year against a plain-python recount, an ES hole, the counts-only reading, and that an event depends on sessions t-21 .. t+1 only"""
    W = ev_world_a()
    tf, ru = mech_days(W.days, EVA_RUSSELL)
    assert W.days[54] == TS("2024-03-15") and tf[54] and not tf[53] and not tf[55] and W.days[84] == TS("2024-04-26") and ru[84] and ru.sum() == 1 and tf.sum() == 1
    ev = attach_events(W, tf=tf, ru=ru)
    t = EVA["t"]
    probes = {(53, 18), (56, 19), (83, 22), (86, 23)}
    pos = lambda m: {(int(a), int(b)) for a, b in zip(*np.nonzero(m))}
    base_ev = {(40, 11), (40, 12)}                                                                       # the 20 x spikes of N11 / N12 are themselves events (row 40), valid for both cells
    want3 = {(t, j) for j in (0, 2, 3, 4, 8, 9, 12)} | {(70, 15)} | probes | base_ev
    want5 = {(t, 2)} | probes | base_ev
    assert pos(ev.EV["V3"]) == want3, (sorted(pos(ev.EV["V3"]) ^ want3))
    assert pos(ev.EV["V5"]) == want5, (sorted(pos(ev.EV["V5"]) ^ want5))
    assert ev.bn[t, 4] == 15 and ev.bn[t, 5] == 14 and ev.bsum[t, 4] == 15.0e6 and ev.bsum[t, 12] == 39.0e6 and ev.bsum[t, 13] == 0.0 and ev.bn[t, 13] == 20 and ev.bsum[t, 15] == 20.0e6 and ev.Va[10, 15] == 1.0e6 and ev.Va[60, 15] == 1.0e6
    assert ev.flag3[t, 6] and ev.flag3[t, 7] and ev.flag3[t, 10] and not ev.flag3[t, 8] and not ev.flag3[t, 9] and ev.flag3[0].all() and ev.flag3[-1].all() and not ev.ok3[t, 14] and ev.ok3[t, 13] and not ev.ok3[0].any() and not ev.ok3[-1].any()
    assert ev.excl[54] and ev.excl[55] and ev.excl[84] and ev.excl[85] and ev.excl.sum() == 4 and not ev.excl[53] and not ev.excl[56]
    cn = ev.counts
    for c, (vol, val) in (("V3", (22, 14)), ("V5", (11, 7))):
        assert cn[c]["volume"] == {2024: vol} and cn[c]["valid"] == {2024: val} and cn[c]["excluded"] == {2024: 4}, (c, cn[c])
        assert [cn[c][k] for k in ("excluded_third_friday", "excluded_session_after_third_friday", "excluded_russell_day", "excluded_session_after_russell_day")] == [{2024: 1}] * 4
        assert cn[c]["void_hygiene"] == {2024: 3 if c == "V3" else 0} and cn[c]["void_data"] == {2024: 1 if c == "V3" else 0}, (c, cn[c])
        assert cn[c]["volume"][2024] == cn[c]["excluded"][2024] + cn[c]["void_hygiene"][2024] + cn[c]["void_data"][2024] + cn[c]["valid"][2024], "every volume event ends in exactly one of excluded / voided / valid"
    assert brute_event_counts(W, EVA_RUSSELL) == nz_counts(cn), "attach_events' counts equal the plain-python recount of every (session, name) pair"
    rule = lambda c, tt, j: brute_kind(W, c, tt, j, *brute_mech(W.days, EVA_RUSSELL))
    assert [rule("V3", t, j) for j in (6, 7, 10, 14, 0, 8, 9, 1, 5, 11, 13, 15)] == ["hygiene", "hygiene", "hygiene", "data", "valid", "valid", "valid", None, None, None, None, None], "the plain-python classifier agrees case by case"
    assert [rule("V3", *p_) for p_ in ((54, 16), (55, 17), (84, 20), (85, 21), (53, 18), (56, 19))] == ["excluded"] * 4 + ["valid"] * 2
    # an ES hole on row 51: every event whose window holds it has no reaction (void_data); the flagged ones stay hygiene voids; the sessions elsewhere are untouched
    Wh = ev_world_a(es_hole=51)
    evh = attach_events(Wh, tf=tf, ru=ru)
    assert pos(evh.EV["V3"]) == {(70, 15)} | probes | base_ev and evh.counts["V3"]["void_data"] == {2024: 8} and evh.counts["V3"]["void_hygiene"] == {2024: 3} and evh.counts["V5"]["void_data"] == {2024: 1}, evh.counts["V3"]
    assert brute_event_counts(Wh, EVA_RUSSELL) == nz_counts(evh.counts)
    # a Russell day that is also the third Friday is counted once, as the third Friday (the first kind); the session after, once
    tf2, ru2 = mech_days(W.days, ("2024-03-15",))
    ev2 = attach_events(W, tf=tf2, ru=ru2)
    assert ev2.counts["V3"]["excluded_third_friday"] == {2024: 1} and ev2.counts["V3"]["excluded_russell_day"] == {2024: 0} and ev2.counts["V3"]["excluded_session_after_third_friday"] == {2024: 1} and ev2.counts["V3"]["excluded_session_after_russell_day"] == {2024: 0}
    assert brute_event_counts(W, ("2024-03-15",)) == nz_counts(ev2.counts)
    # the counts-only reading: the same events, the same counts, no sums
    evc = attach_events(W, counts_only=True, tf=tf, ru=ru)
    assert evc.counts_only and evc.R3 is None and evc.M3 is None and all((evc.EV[c] == ev.EV[c]).all() for c in CELLS) and evc.counts == ev.counts and (evc.flag3 == ev.flag3).all() and (evc.ok3 == ev.ok3).all()
    # the reaction's inputs are sums over t-1 .. t+1 of the daily total return and of ES's return
    Rd, es = np.asarray(W.Rd, float), np.asarray(W.es.ret, float)
    assert abs(ev.R3[60, 0] - (Rd[59, 0] + Rd[60, 0] + Rd[61, 0])) < 1e-15 and abs(ev.M3[60] - (es[59] + es[60] + es[61])) < 1e-15 and np.isnan(ev.R3[0]).all() and np.isnan(ev.R3[-1]).all() and np.isnan(ev.M3[0]) and np.isnan(ev.M3[-1])
    # an event is a function of sessions t-21 .. t+1 only: the same world cut after row 51 has the same events on every row up to 50
    k = 52
    Wc = M17.mk_world(W.Cl[:k], W.es.ret[:k], F=W.F[:k], chg=W.chg[:k], tbis=W.tbis[:k], Vv=W.Vv[:k])
    evk = attach_events(Wc, tf=tf[:k], ru=ru[:k])
    assert all((evk.EV[c][:t + 1] == ev.EV[c][:t + 1]).all() for c in CELLS) and pos(evk.EV["V3"]) == {p for p in want3 if p[0] <= t}, "nothing after t+1 and nothing before t-21 enters an event"
    # a baseline needs the 20 sessions t-21 .. t-2: an early row (t < 21) and the last row can never be an event, however large the volume
    Vx = np.array(W.Vv)
    Vx[10, 0], Vx[99, 1], Vx[20, 2], Vx[21, 3] = 9.0e6, 9.0e6, 9.0e6, 9.0e6
    Wx = M17.mk_world(W.Cl, W.es.ret, F=W.F, chg=W.chg, tbis=W.tbis, Vv=Vx)
    evx = attach_events(Wx, tf=tf, ru=ru)
    assert not evx.EV["V3"][10].any() and not evx.EV["V3"][99].any() and not evx.EV["V3"][20, 2] and evx.bn[20, 2] == 0 and evx.EV["V3"][21, 3] and evx.bn[21, 3] == 20, "t = 21 is the first session with a full baseline"


def t_reaction():
    """the reaction on a world where it is known in closed form: every return is EXACTLY beta_j x ES's plus planted shocks whose OLS-orthogonal choice leaves the slope exactly beta_j, so the reaction of an event is exactly x + y + z of its three sessions - the score is the reaction of
    the MOST RECENT event (an older one never counts), the window is rows r-63 .. r-1 (age 1 .. 63: t = r-1 is in with t + 1 = r, t = r and t = r-64 are out), ages, ranking (the lowest scores short, the highest long, ties by symbol order), RES rebuilt from ed_beta, the first-reason
    counts, and that a score never reads a session after the rank close"""
    W, planted, beta, r0 = ev_world_b()
    uni = np.arange(W.S)
    b = ed_beta(W, r0, uni)
    assert all(abs(b[j] - beta[j]) < 1e-9 for j in (0, 1, 4, 5, 6)) and np.allclose(b, [brute_beta(W, r0, j) for j in uni], atol=1e-12), "OLS recovers the planted beta where the shocks are orthogonal; ed_beta is numpy's least squares"
    n_ret, n_pair, res, _raw = M17.rm_scores(W, r0, uni)
    a, fa, fe = M17.windows(r0)
    R, m = np.asarray(W.Rd, float), np.asarray(W.es.ret, float)
    for j in (0, 1, 4, 5, 6):                                                                            # RES = the sum / sample std of (return - beta x ES) over the formation rows: rebuilt from this beta
        e = np.array([R[s, j] - b[j] * m[s] for s in range(fa, fe + 1)])
        assert abs(res[j] - e.sum() / e.std(ddof=1)) < 1e-9 * max(1.0, abs(res[j])), j
    with spec(n_side=2, min_scored=5, min_side=1):
        attach_events(W)
        L = ed_build(W, W.days[0], W.days[-1], "remove")
        Bz = brute_ed(W, W.days[0], W.days[-1])
        compare_ed(W, L, Bz, "reaction world", check_res=False)
    assert [rec.r for rec in L.recs] == [r0, dr_(W, "2025-01-31"), dr_(W, "2025-02-28")] and [W.days[rec.r].strftime("%Y-%m-%d") for rec in L.recs] == ["2024-12-31", "2025-01-31", "2025-02-28"]
    rec = L.recs[0]
    assert rec.pool.tolist() == list(range(8)) and rec.nu == 8
    tot = lambda t_, j: sum(planted[(t_, j)])
    cc3, cc5 = rec.cell["V3"], rec.cell["V5"]
    assert rec.pool[cc3.idx].tolist() == [0, 1, 4, 5] and cc3.tstar.tolist() == [250, 210, 260, 198] and cc3.age.tolist() == [11, 51, 1, 63], (rec.pool[cc3.idx].tolist(), cc3.tstar.tolist(), cc3.age.tolist())
    assert rec.pool[cc5.idx].tolist() == [0, 4, 5] and cc5.tstar.tolist() == [250, 260, 198] and cc5.age.tolist() == [11, 1, 63], "V5: N01's 4 x is no V5 event"
    want = [tot(250, 0), tot(210, 1), tot(260, 4), tot(198, 5)]
    assert close(cc3.score, want, 1e-9) and close(cc5.score, [want[0], want[2], want[3]], 1e-9), "the reaction is x + y + z of the event's three sessions, exactly"
    assert abs(tot(250, 0) - tot(205, 0)) > 1e-3 and abs(cc3.score[0] - tot(205, 0)) > 1e-3, "N00 has an older event (row 205): the most recent one (row 250) is the score"
    assert 2 not in rec.pool[cc3.idx] and 3 not in rec.pool[cc3.idx] and 6 not in rec.pool[cc3.idx], "N02 (2.5 x), N03 (t = r: not in the window) and N06 (t = r - 64) have no score"
    # sides: 4 scored (< min_scored 5) -> the third (4 // 3 = 1 a side); V5 has 3 -> 1; the lowest score is the short, the highest the long
    for cc in (cc3, cc5):
        o = np.argsort(cc.score)
        assert cc.mode == "third" and cc.k == 1 and cc.traded and cc.short.tolist() == [int(o[0])] and cc.long.tolist() == [int(o[-1])], (cc.mode, cc.k)
    # the next rank (2025-01-31, row 284): the window is rows 221 .. 283 - N03's event (row 261, age 23) is in, N04's (260, age 24), N00's (250, age 34) too; N01 (210) and N05 (198) are out
    r1 = L.recs[1]
    c13 = r1.cell["V3"]
    assert r1.r == 284 and r1.pool[c13.idx].tolist() == [0, 3, 4] and c13.age.tolist() == [34, 23, 24] and c13.tstar.tolist() == [250, 261, 260], (r1.r, r1.pool[c13.idx].tolist(), c13.age.tolist())
    assert c13.n == 3 and c13.mode == "third" and c13.k == 1
    # a score never reads a session after the rank close: the same world with everything after row r0 replaced gives the same scores at r0
    W2 = ev_world_b(scramble_after=r0 + 1)[0]
    with spec(n_side=2, min_scored=5, min_side=1):
        attach_events(W2)
        ee = ed_one(W2, r0, r0 + 1, dr_(W, "2025-01-31") + 1, "remove", units=False)[0]
    assert ee.pool.tolist() == rec.pool.tolist() and close(ee.beta, rec.beta, 1e-12)
    for c in CELLS:
        assert ee.cell[c].idx.tolist() == rec.cell[c].idx.tolist() and close(ee.cell[c].score, rec.cell[c].score, 1e-12) and ee.cell[c].age.tolist() == rec.cell[c].age.tolist(), c
    # ties: ONE ascending order by (score, symbol order): the shorts are its first k, the longs its last k - a tie goes to the lower symbol on the short side and to the higher symbol on the long side
    cols, sc = np.array([5, 3, 9, 1]), np.zeros(4)
    lg, sh = pick_sides(cols, sc, 2)
    assert cols[sh].tolist() == [1, 3] and cols[lg].tolist() == [9, 5], "all scores equal: the order is the symbol order"
    lg, sh = pick_sides(np.array([7, 2, 8, 4, 6]), np.array([0.3, 0.1, 0.3, 0.2, 0.1]), 2)
    assert np.array([7, 2, 8, 4, 6])[sh].tolist() == [2, 6] and np.array([7, 2, 8, 4, 6])[lg].tolist() == [8, 7], "two ties at the ends: the lower symbol shorts first, the higher symbol longs first"
    lg, sh = pick_sides(np.array([4, 1, 3]), np.array([1.0, 2.0, 3.0]), 0)
    assert len(lg) == 0 and len(sh) == 0
    assert not set(pick_sides(np.arange(10), np.zeros(10), 5)[0].tolist()) & set(pick_sides(np.arange(10), np.zeros(10), 5)[1].tolist()), "2k <= n: the sides never share a name"


def t_sides():
    """the fallback rule: 150 or more scored names -> 50 a side; fewer -> the top / bottom third (n // 3), at least 20 a side, else nothing - at every edge, and with the sides shrunk the way the selftests and the smoke shrink them"""
    assert side_n(150) == (50, "top") and side_n(151) == (50, "top") and side_n(1000) == (50, "top") and side_n(149) == (49, "third") and side_n(100) == (33, "third") and side_n(60) == (20, "third")
    assert side_n(61) == (20, "third") and side_n(63) == (21, "third") and side_n(59) == (0, "none") and side_n(0) == (0, "none") and side_n(1) == (0, "none")
    assert all(side_n(n) == brute_side(n) for n in range(0, 400))
    with spec(n_side=3, min_scored=10, min_side=2):
        assert [side_n(n) for n in (11, 10, 9, 8, 7, 6, 5)] == [(3, "top"), (3, "top"), (3, "third"), (2, "third"), (2, "third"), (2, "third"), (0, "none")]
        assert all(side_n(n) == brute_side(n) for n in range(0, 40))
    assert side_n(150)[0] == M17.SPEC["n_side"]


def toy_events(seed=1, ev_seed=7):
    """r17_resmom's toy world (450 weekdays x 14 names with every hygiene case planted: a registered split, a gap-scan flag, a TBIS flag, a +60% gap, names that stop printing, a missing close, a short history, ES holes, dividends, spin-offs) with VOLUME events planted on top: every
    name spikes (3.4 x or 6 x its volume) every 14 .. 37 sessions, every name spikes 8 x on every third Friday / the Russell day / the ES-hole session in the range, and the flagged sessions (the split, the gap, the TBIS flag, the jump, the missing close) and their neighbours
    carry spikes too, so every branch of the event rule (excluded, voided by a flag, voided by a missing return, valid) is hit"""
    with D15.spec(univ=14):
        W = M17.toy_world(seed=seed)
    rng = np.random.default_rng(ev_seed)
    dr = lambda s: W.days.get_loc(TS(s))
    for j in range(W.S):
        t = int(rng.integers(30, 60))
        while t < W.T - 2:
            if np.isfinite(W.Vv[t, j]):
                W.Vv[t, j] *= 3.4 if rng.random() < 0.5 else 6.0
            t += int(rng.integers(14, 38))
        for s in ("2024-12-20", "2025-03-21", "2025-06-20", "2025-06-27", "2025-02-10"):               # the mechanical days (and the session ES has no return): every name
            W.Vv[dr(s), j] *= 8.0
    for s, j in (("2025-03-14", 0), ("2025-01-14", 1), ("2025-04-10", 2), ("2025-05-12", 3), ("2025-03-20", 5), ("2025-06-11", 4), ("2025-03-14", 13)):
        for dd in (-1, 0, 1):
            W.Vv[dr(s) + dd, j] = 8.0 * 3.0e6 if np.isfinite(W.Vv[dr(s) + dd, j]) else W.Vv[dr(s) + dd, j]
    return W


def t_pipeline():
    """the vectorised builds against the plain-python recount on the toy world with the REGISTERED windows (252 / 231 / 21 / 230 / 63 / 20), both readings, three fallback settings (so that the top, third and nothing modes all occur), a hand-audit removal, the counts-only build,
    and the counts of every (session, name) pair by kind and year; then the planted cases one by one"""
    n, modes, n_closed_all = 0, Counter(), 0
    for sp in (dict(n_side=2, min_scored=8, min_side=2), dict(n_side=2, min_scored=11, min_side=2), dict(n_side=3, min_scored=9, min_side=3)):
        with spec(**sp):
            W = toy_events()
            W.aud1[dr_(W, "2025-02-03"), 8] = True                                                      # N08: a hand-audit data event at fill session 2025-02-03 (the rebalance ranked 2025-01-31)
            ev = attach_events(W)
            lo, hi = W.days[0], W.days[-1]
            assert brute_event_counts(W) == nz_counts(ev.counts), "the counts of every (session, name) pair by kind and year equal the recount"
            out = {}
            for pm in ("remove", "naive", "close"):
                L = ed_build(W, lo, hi, pm)
                Bz = brute_ed(W, lo, hi, pm)
                n += compare_ed(W, L, Bz, f"toy {pm} {sp}")
                out[pm] = L
                if pm in ("remove", "close"):
                    series_check(W, L, Bz)
                for rec in L.recs:
                    for c in CELLS:
                        modes[rec.cell[c].mode] += 1
            Lr, Lk = out["remove"], out["naive"]
            for a_, b_ in zip(Lr.recs, Lk.recs):
                assert set(a_.pool.tolist()) <= set(b_.pool.tolist()), "the look-ahead reading differs from the registered one only by the in-hold names (more names, never fewer)"
                for c in CELLS:
                    assert a_.cell[c].n <= b_.cell[c].n
            # [HYG-S1] the 'close' reading = the look-ahead pool itself (no in-hold removal), never on the raw path; the pool names with a [D2] ex-date inside the hold close at the close before it
            Lc, n_cl = out["close"], 0
            for k_, c_ in zip(Lk.recs, Lc.recs):
                assert c_.pool.tolist() == k_.pool.tolist() and not c_.naive.any() and all(c_.cell[c].idx.tolist() == k_.cell[c].idx.tolist() for c in CELLS), (W.days[c_.r], c_.pool.tolist(), k_.pool.tolist())
                assert ((c_.close >= 0) == c_.spin_hold).all() and all(not W.SPN[c_.f + 1:e_ + 1, j_].any() and W.SPN[e_ + 1, j_] for j_, e_ in zip(c_.pool.tolist(), c_.close.tolist()) if e_ >= 0)
                n_cl += int((c_.close >= 0).sum())
            assert sum(c.get("closed_spin", 0) for c in Lc.cnt.values()) == n_cl and sum(c.get("post_spin", 0) + c.get("post_calendar_split", 0) + sum(c.get(f"post_{h}", 0) for h in HYG) for c in Lc.cnt.values()) == 0, ("closed_spin", n_cl)
            n_closed_all += n_cl
            for y, c in Lc.cnt.items():
                assert c["universe"] == sum(c[k_] for k_ in COUNT_KEYS[1:]), (y, dict(c))
            # the counts-only build is the same pools and scored sets, with no unit paths and no sums
            ev_c = attach_events(W, counts_only=True)
            Lc = ed_build(W, lo, hi, "remove", units=False, counts_only=True)
            attach_events(W)
            assert len(Lc.recs) == len(Lr.recs)
            for rc, rf in zip(Lc.recs, Lr.recs):
                assert rc.pool.tolist() == rf.pool.tolist() and rc.nu == rf.nu and rc.nfull == rf.nfull and not hasattr(rc, "U")
                for c in CELLS:
                    a_, b_ = rc.cell[c], rf.cell[c]
                    assert a_.idx.tolist() == b_.idx.tolist() and (a_.n, a_.k, a_.mode, a_.traded) == (b_.n, b_.k, b_.mode, b_.traded) and a_.tstar.tolist() == b_.tstar.tolist() and a_.age.tolist() == b_.age.tolist() and len(a_.score) == 0
            assert {y: {k: v for k, v in c.items() if k != "no_beta"} for y, c in Lc.cnt.items()} == {y: {k: v for k, v in c.items() if k != "no_beta"} for y, c in Lr.cnt.items()}, "the counts-only build counts the same removals and the same scored names"
            assert ev_c.counts == ev.counts
            # counts: every universe name is counted once, in a reason or in the pool; the scored counts add up
            for y, c in Lr.cnt.items():
                assert c["universe"] == sum(c[k] for k in COUNT_KEYS[1:]), (y, dict(c))
                for cl in CELLS:
                    assert c[f"scored_{cl}"] + c[f"no_event_{cl}"] == c["pool"] and c[f"mode_{cl}_top"] + c[f"mode_{cl}_third"] + c[f"mode_{cl}_none"] == c["rebalances"] - c.get("empty", 0), (y, cl, dict(c))
            assert (AUD, dr_(W, "2025-02-03"), 8) in W.aud_hit and Lr.cnt[2025]["audit"] >= 1 and 8 not in next(r for r in Lr.recs if W.days[r.r] == TS("2025-01-31")).pool.tolist()
    assert modes["top"] > 0 and modes["third"] > 0 and modes["none"] > 0, modes
    assert n_closed_all >= 3, ("[HYG-S1] the toy world's spin-off / stock-dividend names inside a hold are closed", n_closed_all)
    # the planted cases through the real arrays: the mechanical days are excluded, the flagged sessions void their events, the ES-hole session voids every name's
    with spec(n_side=2, min_scored=8, min_side=2):
        W = toy_events()
        ev = attach_events(W)
        dr = lambda s: dr_(W, s)
        assert ev.excl[dr("2025-03-21")] and ev.excl[dr("2025-03-24")] and ev.excl[dr("2025-06-27")] and ev.excl[dr("2025-06-30")] and ev.excl[dr("2024-12-20")] and ev.excl[dr("2025-06-20")] and ev.excl[dr("2025-06-23")] and not ev.excl[dr("2025-03-20")]
        assert not any(ev.EV[c][dr(s)].any() for c in CELLS for s in ("2025-03-21", "2025-03-24", "2025-06-27", "2025-06-30", "2024-12-20", "2024-12-23", "2025-06-20", "2025-06-23")), "no event on a mechanical day or the session after it"
        assert not any(ev.EV[c][dr("2025-02-10")].any() for c in CELLS) and ev.counts["V3"]["void_data"][2025] >= 14, "the ES-hole session: no name has a reaction there"
        for s, j in (("2025-03-14", 0), ("2025-01-14", 1), ("2025-04-10", 2), ("2025-05-12", 3)):
            assert not any(ev.EV[c][dr(s) + dd, j] for c in CELLS for dd in (-1, 0, 1)), (s, j, "a hygiene flag on t-1 .. t+1 voids the event")
            assert ev.flag3[dr(s) - 1, j] and ev.flag3[dr(s), j] and ev.flag3[dr(s) + 1, j], (s, j)
        assert not any(ev.EV[c][dr(s), j] for c in CELLS for s, j in (("2025-03-14", 13), ("2025-06-11", 4))) and not any(ev.EV[c][dr(s), 5] for c in CELLS for s in ("2025-03-19", "2025-03-20", "2025-03-21", "2025-03-24")),             "a missing return on t-1 .. t+1 (a name that stops printing, a missing close) voids the event"
        assert ev.counts["V3"]["void_hygiene"][2025] >= 5 and ev.counts["V5"]["void_hygiene"][2025] >= 3
        L = ed_build(W, W.days[0], W.days[-1], "remove")
        assert sum(r.traded for r in L.recs) >= 6 and L.recs[0].pool.size >= 8
    return n


def null_x0(W, L, Bz, cell, q, nr, vcode=0, placebo=False):
    """the null's draws for one cell recounted by plain python from the stream's own draw order: every drawn name's path is brute_pos_ed's (the cut path when the name is closed before a spin-off ex-date), in $ at the slot -> (nr, T)"""
    slot = M17.SPEC["slot"]
    rng = np.random.default_rng([SEED_PLACEBO if placebo else SEED, q, vcode])
    x0 = np.zeros((nr, W.T))
    for rec, b in zip(L.recs, Bz):
        cc = rec.cell[cell]
        if not cc.traded:
            continue
        cols = rec.pool[cc.idx]
        if placebo:
            lg, sh, ok = placebo_picks(cc.ph, cc.k, rng, nr)
            draws = [[(sd, [int(cols[i]) for i in ii]) for sd, ii in ((1, lg[:, d]), (-1, sh[:, d]))] if ok[d] else [] for d in range(nr)]
        else:
            o = D15.draw_order(rng, nr, cc.n, 2 * cc.k)
            draws = [[(1, [int(cols[i]) for i in o[d][:cc.k]]), (-1, [int(cols[i]) for i in o[d][cc.k:]])] for d in range(nr)]
        for d, sides in enumerate(draws):
            for sd, js in sides:
                for j in js:
                    x0[d, b["f"]:b["x"] + 1] += slot * np.array(brute_pos_ed(W, b, j, sd))
    return x0


def t_close():
    """[HYG-S1] MANAGER's hygiene edit S1 (#127, 2026-10-07), post_mode 'close', on EDRIFT's toy world (r17_resmom's: 450 weekdays x 14 names with every hygiene case, dividends and spin-offs planted, volume events on top): no in-hold event removes a name (the pool is the
    look-ahead reading's, every flagged name on the split-safe path, a calendar split counted and kept), a [D2] spin-off / stock-dividend ex-date e in f < e <= x closes the position at the official close of e-1 - nothing on rows e .. x, the exit cost on that row - for the cells'
    sides (the slices carry the exit column), the series, BOTH nulls (every draw recounted by plain python from the stream: a drawn closed name is cut too) and evaluate(); the registered 'remove' reading is untouched (no exit column anywhere, l1_pnl_x is r15's l1_pnl on its
    units bit for bit); an unknown reading is refused"""
    cfg0, slot = D15.l1_cfg(), M17.SPEC["slot"]
    with spec(n_side=2, min_scored=8, min_side=2):
        W = toy_events()
        attach_events(W)
        lo, hi = W.days[0], W.days[-1]
        # ---- (1) 'remove' and 'naive' carry no exit column: l1_pnl_x IS r15's l1_pnl on their units
        n_same = 0
        for pm in ("remove", "naive"):
            Lx = ed_build(W, lo, hi, pm)
            for rec in Lx.recs:
                assert rec.close.shape == rec.pool.shape and (rec.close == -1).all(), (pm, W.days[rec.r])
                for c in CELLS:
                    cc = rec.cell[c]
                    if not cc.traded:
                        continue
                    assert not hasattr(rec.U, "xc") and not hasattr(cc.U, "xc"), (pm, "an exit column under a reading that cuts nothing")
                    idx, kt = np.arange(cc.n), W.k[rec.f:rec.x + 1]
                    for sd in (1, -1):
                        assert np.array_equal(M17.l1_pnl_x(cc.U, idx, sd, cfg0, kt), D15.l1_pnl(cc.U, idx, sd, cfg0, kt)), (pm, W.days[rec.r], c, sd)
                        n_same += 1
        assert n_same >= 10, n_same
        # ---- (2) the 02-28 rank by hand: N12's stock dividend (03-12) and N10's spin-off (04-01 = the exit session) close their positions; N09's (03-03 = the fill session) is bought ex: held
        Lr, Lc = ed_build(W, lo, hi, "remove", keep_ph=True), ed_build(W, lo, hi, "close", keep_ph=True)
        Bc = brute_ed(W, lo, hi, "close")
        n_paths = compare_ed(W, Lc, Bc, "close")
        series_check(W, Lc, Bc)
        rec = next(r_ for r_ in Lc.recs if W.days[r_.r] == TS("2025-02-28"))
        rem = next(r_ for r_ in Lr.recs if r_.r == rec.r)
        assert (W.days[rec.f], W.days[rec.x]) == (TS("2025-03-03"), TS("2025-04-01")) and rec.traded and not rec.naive.any()
        pos = {int(j): i for i, j in enumerate(rec.pool)}
        assert {9, 10, 12} <= set(pos) and set(rem.pool.tolist()) < set(rec.pool.tolist()), "no in-hold event removes a name: the registered pool plus the names it dropped"
        for j in set(rec.pool.tolist()) - set(rem.pool.tolist()):
            assert W.hyg(rec.r + 1, rec.x, [j]).any() or M17.spn_hit(W, rec.f + 1, rec.x, [j])[0], (j, "only a name with an in-hold event is added")
        e12, e10 = dr_(W, "2025-03-12"), dr_(W, "2025-04-01")
        assert rec.close[pos[12]] == e12 - 1 and rec.close[pos[10]] == e10 - 1 == rec.x - 1 and rec.close[pos[9]] == -1 and int((rec.close >= 0).sum()) == 2, rec.close.tolist()
        U, H = rec.U, rec.x - rec.f + 1
        for j, e in ((12, e12), (10, e10)):
            i, xc = pos[j], e - 1 - rec.f
            assert U.xc[i] == xc and (U.G[i, xc + 1:] == 0).all() and (U.mk[i, xc + 1:] == 0).all() and (U.div[i, xc:] == 0).all(), j
            assert abs(U.ve[i] - W.Ac[e - 1, j] / W.Ao[rec.f, j]) < 1e-15 and not U.st[i], j
            assert abs(U.G[i].sum() - (U.ve[i] - 1.0 + U.div[i].sum())) < 1e-12, "the cut path sums to the close of e-1 over the entry open, plus the dividends before e"
        assert U.xc[pos[9]] == H - 1 and U.G[pos[9], -1] != 0.0
        c0, kt = COST_BPS * 1e-4, W.k[rec.f:rec.x + 1]
        i, xc = pos[12], e12 - 1 - rec.f
        PL = M17.l1_pnl_x(U, np.array([i]), 1, cfg0, kt)[0]
        assert (PL[xc + 1:] == 0).all() and abs(PL.sum() - (U.ve[i] - 1.0 + U.div[i].sum() - c0 - c0 * U.ve[i])) < 1e-12 and D15.l1_pnl(U, np.array([i]), 1, cfg0, kt)[0][-1] != 0.0, "the exit cost is booked on the close's row, r15's l1_pnl books it on the last"
        for c in CELLS:                                                                                 # the cells' slices carry the exit column of their names (the picks and the null read them)
            cc = rec.cell[c]
            assert cc.traded and np.array_equal(cc.U.xc, rec.U.xc[cc.idx]) and (cc.U.xc < H - 1).sum() == int((rec.close[cc.idx] >= 0).sum()) >= 1, c
        # ---- (3) the counts: the names with an in-hold event STAY (the hygiene flags by reason, a calendar split), a [D2] ex-date closes; the printout shows them under 'close' only
        cnt = sum((Counter(c_) for c_ in Lc.cnt.values()), Counter())
        want = Counter()
        for rc in Lc.recs:
            fl = W.hyg(rc.r + 1, rc.x, rc.pool)
            for q, h in enumerate(HYG):
                want[f"kept_{h}"] += int(fl[q].sum())
            want["kept_flagged"] += int(fl.any(axis=0).sum())
            want["closed_spin"] += int((rc.close >= 0).sum())
        assert all(cnt[k] == want[k] for k in KEPT_KEYS if k != "kept_calendar_split") and cnt["kept_flagged"] >= 3 and cnt["closed_spin"] >= 3 and cnt["kept_calendar_split"] == 0 and sum(cnt[k] for k in cnt if k.startswith("post_")) == 0, dict(cnt)
        j7 = 7
        M17.attach_calendar_splits(W, SimpleNamespace(split=pd.DataFrame({"symbol": [str(W.syms[j7])], "ex": [W.days[rec.f + 4]], "type": ["forward_split"]})))
        Lcs, Lrs = ed_build(W, lo, hi, "close"), ed_build(W, lo, hi, "remove")
        want_cs = sum(int(j7 in rc.pool.tolist() and W.cscs[rc.x + 1, j7] - W.cscs[rc.f + 1, j7] > 0) for rc in Lcs.recs)
        assert sum(c_.get("kept_calendar_split", 0) for c_ in Lcs.cnt.values()) == want_cs == 1
        assert [rc.pool.tolist() for rc in Lcs.recs] == [rc.pool.tolist() for rc in Lc.recs] and [rc.pool.tolist() for rc in Lrs.recs] == [rc.pool.tolist() for rc in Lr.recs] and not any("kept_calendar_split" in c_ for c_ in Lrs.cnt.values()), "a calendar split on the grid is counted under 'close' and moves no pool, 'remove' ignores it"
        del W.CSPL, W.cscs
        buf_c, buf_r = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(buf_c):
            print_counts("L", Lc.cnt)
        with contextlib.redirect_stdout(buf_r):
            print_counts("L", Lr.cnt)
        assert "STAY [HYG-S1]" in buf_c.getvalue() and "closed_spin" in buf_c.getvalue() and "STAY [HYG-S1]" not in buf_r.getvalue()
        # ---- (4) both nulls draw the cut paths: every draw recounted by plain python from the stream; r15's l1_pnl would book the closed names' exit cost on the exit row
        nr = 6
        acc, accp = ed_null(W, Lc, nr, 0), ed_placebo_null(W, Lc, nr, 0)[0]
        for q, c in enumerate(CELLS):
            assert close(acc[c], null_x0(W, Lc, Bc, c, q, nr)), f"{c}: the random-name null's draws are the recount's cut paths"
            assert close(accp[c], null_x0(W, Lc, Bc, c, q, nr, placebo=True)), f"{c}: so are the placebo's"
        with patched(M17, l1_pnl_x=D15.l1_pnl):
            wrong = ed_null(W, Lc, nr, 0)
        assert any(not np.allclose(acc[c], wrong[c], rtol=0, atol=1e-12) for c in CELLS), "r15's l1_pnl would book the exit cost of a closed name on the last row"
        # ---- (5) evaluate() runs the reading without a null: each cell's net is the recount's sum, the registered reading differs by the in-hold names
        B, S12 = M17.synth_book(seed=15)
        ref = DV.mk_ref(B)
        rows = A13.book_rows(B, W)
        with patched(THIS, A2_WIN=(TS("2024-12-02"), TS("2025-05-30"))):
            res_c, obj_c = evaluate(W, B, S12, ref, rows, "close", 0, 0)
            res_r, _obj_r = evaluate(W, B, S12, ref, rows, "remove", 0, 0)
        assert res_c["variant"] == "close" and res_c["null"] is None and res_c["placebo"] is None and res_r["variant"] == "remove"
        Bz = brute_ed(W, WF0, PRE_END, "close")
        for cell in CELLS:
            x0, n_pos = np.zeros(W.T), 0
            for b in Bz:
                for sd, js in ((1, b["cell"][cell]["long"]), (-1, b["cell"][cell]["short"])):
                    for j in js:
                        x0[b["f"]:b["x"] + 1] += slot * np.array(brute_pos_ed(W, b, j, sd))
                        n_pos += 1
            c = res_c["cells"][cell]
            assert abs(c["base"]["net"] - x0.sum()) < 1e-6 and c["base"]["n_pos"] == n_pos and abs(c["base"]["net_pos"] - x0.sum()) < 1e-6 and close(obj_c.series[cell][0][rows], x0), (cell, c["base"]["net"], x0.sum())
        assert any(abs(res_c["cells"][c]["base"]["net"] - res_r["cells"][c]["base"]["net"]) > 1e-6 for c in CELLS), "the in-hold names move the P&L in the toy world"
        # ---- (6) a reading this family does not run is refused
        for bad in ("keep", "closed", ""):
            try:
                ed_one(W, rec.r, rec.f, rec.x, bad)
                raise AssertionError(f"post_mode {bad!r} must be refused")
            except ValueError as e:
                assert "one of" in str(e)
    return n_paths


# ------------------------------------------------------------------ the nulls: random names (registered) and the placebo in time (reported)
def brute_placebo(W, cell, r, j, beta, tf, ru):
    """plain python: name j's placebo scores at rank r - for each session s = r-1-m (m = 0 .. 62) the abnormal return over s-1 .. s+1 when the window is a NON-event one (no valid event of the cell for this name on any session s-3 .. s+3 before the rank close, no hygiene flag
    on s-1 .. s+1, the three returns and ES's defined), NaN otherwise"""
    look, near = SPEC["look"], SPEC["pl_near"]
    out = []
    for m in range(look):
        s = r - 1 - m
        blocked = any(brute_kind(W, cell, u, j, tf, ru) == "valid" for u in range(s - near, s + near + 1) if u < r)
        flags = any(any(D15.brute_flags(W, q, j)) for q in (s - 1, s, s + 1))
        ys = [M17.brute_ret(W, q, j) for q in (s - 1, s, s + 1)]
        ms = [float(W.es.ret[q]) for q in (s - 1, s, s + 1)]
        ok = not blocked and not flags and all(math.isfinite(v) for v in ys + ms)
        out.append(sum(ys) - beta * sum(ms) if ok else float("nan"))
    return out


def t_nulls():
    """the registered null (random names from each rebalance's SCORED pool: every draw recounted by plain python from the stream's own draw order, drawn names are scored names, one stream per cell, seeded, the stream changes with the reading, expectation = the pool mean)
    and the REPORTED placebo in time ([E2]: every placebo window recounted by plain python - never within 2 sessions of an event; the picks of each draw recounted from the stream; draws that cannot fill 2k names do not trade), and the null's statistic"""
    with spec(n_side=2, min_scored=8, min_side=2):
        W = toy_events()
        attach_events(W)
        lo, hi = W.days[0], W.days[-1]
        L = ed_build(W, lo, hi, "remove", keep_ph=True)
        Bz = brute_ed(W, lo, hi, "remove")
    tf, ru = brute_mech(W.days)
    slot, nr = M17.SPEC["slot"], 6
    path = lambda b, j, sd: slot * np.array(M17.brute_path(W, b["f"], b["x"], int(j), sd, b["pool"][int(j)]["naive"])[0])
    # ---- the registered null
    acc = ed_null(W, L, nr, 0)
    assert set(acc) == set(CELLS) and all(a.shape == (nr, W.T) for a in acc.values()), "one (draws, sessions) P&L array per cell"
    n_draws = 0
    for q, c in enumerate(CELLS):
        rng = np.random.default_rng([SEED, q, 0])
        x0 = np.zeros((nr, W.T))
        for rec, b in zip(L.recs, Bz):
            cc, bc = rec.cell[c], b["cell"][c]
            if not cc.traded:
                continue
            o = D15.draw_order(rng, nr, cc.n, 2 * cc.k)
            cols = rec.pool[cc.idx]
            for d in range(nr):
                assert len(set(o[d].tolist())) == 2 * cc.k and 0 <= o[d].min() and o[d].max() < cc.n, "2k distinct names of the scored pool: longs and shorts never share a name"
                names = [int(cols[i]) for i in o[d]]
                assert all(j in bc["score"] for j in names), "a draw holds scored names only (names that have an event in their window)"
                for sd, js in ((1, names[:cc.k]), (-1, names[cc.k:])):
                    for j in js:
                        x0[d, b["f"]:b["x"] + 1] += path(b, j, sd)
                n_draws += 1
        assert close(acc[c], x0), f"{c}: every draw is the stream's own draw order, costed by plain python"
    assert n_draws > 20 and not (acc["V3"] == acc["V5"]).all()
    assert all((ed_null(W, L, nr, 0)[c] == acc[c]).all() for c in CELLS), "seeded"
    assert not (ed_null(W, L, nr, 1)["V3"] == acc["V3"]).all(), "the other reading draws a different stream"
    big, cfg = ed_null(W, L, 400, 0), D15.l1_cfg()
    for c in CELLS:
        exp = 0.0
        for rec in L.recs:
            cc = rec.cell[c]
            if cc.traded:
                idx, kt = np.arange(cc.n), W.k[rec.f:rec.x + 1]
                exp += slot * cc.k * float(M17.l1_pnl_x(cc.U, idx, 1, cfg, kt).mean(axis=0).sum() + M17.l1_pnl_x(cc.U, idx, -1, cfg, kt).mean(axis=0).sum())
        tot = big[c].sum(axis=1)
        assert abs(tot.mean() - exp) < 4.5 * tot.std() / math.sqrt(len(tot)), (c, tot.mean(), exp, tot.std())
        assert (big[c][:, :dr_(W, "2025-01-01")] == 0).all(), "no P&L before the first fill"
    # ---- the placebo windows
    n_fin = n_nan = n_blocked = 0
    for rec in L.recs:
        for c in CELLS:
            cc = rec.cell[c]
            assert cc.ph is None or cc.ph.shape == (cc.n, SPEC["look"])
            for i in range(cc.n):
                j = int(rec.pool[cc.idx[i]])
                want = brute_placebo(W, c, rec.r, j, rec.beta[cc.idx[i]], tf, ru)
                assert np.allclose(cc.ph[i], want, equal_nan=True, atol=1e-12), (rec.r, c, j)
                n_fin += int(np.isfinite(want).sum())
                n_nan += int((~np.isfinite(want)).sum())
                for m_, v in enumerate(want):                                                           # a finite placebo window has no valid event within 2 sessions of it (events before the rank close)
                    s = rec.r - 1 - m_
                    if np.isfinite(v):
                        assert not any(brute_kind(W, c, u, j, tf, ru) == "valid" for u in range(s - 3, s + 4) if u < rec.r), (rec.r, c, j, s)
                    elif not any(any(D15.brute_flags(W, q_, j)) for q_ in (s - 1, s, s + 1)) and all(np.isfinite(M17.brute_ret(W, q_, j)) and np.isfinite(W.es.ret[q_]) for q_ in (s - 1, s, s + 1)):
                        n_blocked += 1
    assert n_fin > 200 and n_nan > 100 and n_blocked > 20, (n_fin, n_nan, n_blocked)
    # ---- placebo_picks against a plain-python recount of the stream
    rng0 = np.random.default_rng(3)
    n, k, nd = 12, 3, 40
    ph = np.where(rng0.random((n, SPEC["look"])) < 0.3, rng0.normal(0.0, 0.05, (n, SPEC["look"])), np.nan)
    ph[4], ph[7] = np.nan, np.nan                                                                       # two names with no placebo window at all
    lg, sh, ok = placebo_picks(ph, k, np.random.default_rng(5), nd)
    u = np.random.default_rng(5).random((n, nd))
    for d in range(nd):
        vals = []
        for i in range(n):
            w = np.flatnonzero(np.isfinite(ph[i]))
            vals.append(float(ph[i, w[min(int(u[i, d] * len(w)), len(w) - 1)]]) if len(w) else float("nan"))
        fin = [i for i in range(n) if math.isfinite(vals[i])]
        order = sorted(fin, key=lambda i: (vals[i], i))
        assert bool(ok[d]) == (len(fin) >= 2 * k) and 4 not in fin and 7 not in fin
        if ok[d]:
            assert sh[:, d].tolist() == order[:k] and lg[:, d].tolist() == order[::-1][:k] and not set(sh[:, d].tolist()) & set(lg[:, d].tolist()), d
    assert ok.all(), "the number of names that have a placebo window is the same in every draw: a rebalance trades in every draw or in none"
    ph2 = np.full((12, SPEC["look"]), np.nan)
    ph2[:3, 5] = [0.01, -0.02, 0.03]                                                                    # only 3 names have a window, k = 2 needs 4: no draw trades
    assert not placebo_picks(ph2, 2, np.random.default_rng(1), 20)[2].any()
    # ---- the placebo null: the stream's picks costed by plain python; a draw that cannot fill both sides trades nothing
    accp, info = ed_placebo_null(W, L, nr, 0)
    for q, c in enumerate(CELLS):
        rng = np.random.default_rng([SEED_PLACEBO, q, 0])
        x0, share, trades = np.zeros((nr, W.T)), 0.0, 0
        for rec, b in zip(L.recs, Bz):
            cc = rec.cell[c]
            if not cc.traded:
                continue
            lg, sh, ok = placebo_picks(cc.ph, cc.k, rng, nr)
            cols = rec.pool[cc.idx]
            share, trades = share + float((~ok).mean()), trades + 1
            for d in range(nr):
                if not ok[d]:
                    continue
                for sd, ii in ((1, lg[:, d]), (-1, sh[:, d])):
                    for i in ii:
                        assert np.isfinite(cc.ph[i]).any() and int(cols[i]) in b["cell"][c]["score"]
                        x0[d, b["f"]:b["x"] + 1] += path(b, cols[i], sd)
        assert close(accp[c], x0), c
        assert info[c]["rebalances"] == trades and abs(info[c]["draw_share_not_trading_mean"] - share / max(trades, 1)) < 1e-12 and 0.0 <= info[c]["scored_names_without_a_placebo_window_share"] <= 1.0
    assert all((ed_placebo_null(W, L, nr, 0)[0][c] == accp[c]).all() for c in CELLS) and not (ed_placebo_null(W, L, nr, 1)[0]["V3"] == accp["V3"]).all() and not (accp["V3"] == acc["V3"]).all(), "seeded; another stream per reading; not the random-name stream"
    try:
        with spec(n_side=2, min_scored=8, min_side=2):
            ed_placebo_null(W, ed_build(W, lo, hi, "remove"), 4, 0)
        raise AssertionError("a leg built without keep_ph cannot draw the placebo")
    except ValueError as e:
        assert "keep_ph" in str(e)
    # ---- the statistic: the max over the 2 cells per draw, then p5 / p50 / p95
    ix = pd.bdate_range("2016-07-01", "2025-06-27")
    rng = np.random.default_rng(2)
    book = rng.normal(35.0, 650.0, len(ix))
    S12 = M12.Stretch(book, ix, None, WF0, PRE_END)
    pc = {c: D15.null_cell(S12, rng.normal(5, 100, (40, len(ix))), np.arange(len(ix)), len(ix))[0] for c in CELLS}
    pdo = {c: D15.null_cell(S12, rng.normal(5, 100, (40, len(ix))), np.arange(len(ix)), len(ix))[2] for c in CELLS}
    ns = null_summary(pc, pdo)
    mx, mo = np.max(np.vstack([pc[c] for c in CELLS]), axis=0), np.max(np.vstack([pdo[c] for c in CELLS]), axis=0)
    assert ns["draws"] == 40 and ns["seed"] == SEED and abs(ns["roc_max"]["p95"] - np.percentile(mx, 95)) < 1e-9 and abs(ns["roc_max"]["p50"] - np.percentile(mx, 50)) < 1e-9 and abs(ns["roc_max"]["p5"] - np.percentile(mx, 5)) < 1e-9
    assert abs(ns["do_ref_max"]["p95"] - np.percentile(mo, 95)) < 1e-9 and ns["roc_max"]["p95"] >= max(ns["by_cell"][c]["p95"] for c in CELLS) - 1e-9 and set(ns["do_ref_by_cell"]) == set(CELLS)
    assert null_summary(pc, seed=SEED_PLACEBO)["seed"] == SEED_PLACEBO and "do_ref_max" not in null_summary(pc)
    roc_d, do_d = DV.null_stats(S12, S12, rng.normal(5, 100, (40, len(ix))), np.arange(len(ix)), len(ix))
    assert roc_d.shape == (40,) and do_d.shape == (40,) and np.isfinite(do_d).all(), "r18's null statistics: the ROC of every draw and its DO against the reference's drawdown days"


# ------------------------------------------------------------------ [E3] and [E5']: scored on planted data, printed before any P&L
def t_e3():
    """[E3]: the rank correlation on hand numbers (and NaN / short / flat vectors), then the age split and the correlation with RES against a plain-python recount on the toy world"""
    assert abs(spearman([1, 2, 3, 4], [1, 3, 2, 4]) - 0.8) < 1e-12 and spearman([1, 2, 3], [3, 2, 1]) == -1.0 and spearman([5.0, 1.0, 3.0], [50.0, 10.0, 30.0]) == 1.0
    assert abs(spearman([1, 2, 3, 4, np.nan], [1, 3, 2, 4, 9]) - 0.8) < 1e-12 and abs(spearman([1, 2, 3, 4, 5], [1, 3, 2, 4, np.nan]) - 0.8) < 1e-12, "a pair with a NaN is left out"
    assert math.isnan(spearman([1, 2], [2, 1])) and math.isnan(spearman([1, 1, 1], [1, 2, 3])) and math.isnan(spearman([], [])), "under 3 pairs / a flat vector: no correlation"
    with spec(n_side=2, min_scored=8, min_side=2):
        W = toy_events()
        attach_events(W)
        lo, hi = W.days[0], W.days[-1]
        L = ed_build(W, lo, hi, "remove", units=False)
        Bz = brute_ed(W, lo, hi, "remove")
    e3 = e3_report(W, L)
    rk = lambda v: np.argsort(np.argsort(v)).astype(float)                                              # ranks (no ties in continuous scores): Spearman = Pearson of the ranks

    def brute_rho(Bz_, c):                                                                              # every rebalance with at least 3 scored names (traded or not) -> the correlations, and how many of the months trade
        got, ntr = [], 0
        for b in Bz_:
            bc = b["cell"][c]
            cols = sorted(bc["score"])
            ntr += int(bc["k"] > 0)
            if len(cols) >= 3:
                sc, rs = np.array([bc["score"][j][1] for j in cols]), np.array([b["pool"][j]["res"] for j in cols])
                if np.isfinite(rs).all():
                    got.append(float(np.corrcoef(rk(sc), rk(rs))[0, 1]))
        return got, ntr
    for c in CELLS:
        ages, ab, yrs = [], [], []
        for b in Bz:
            bc = b["cell"][c]
            for j in sorted(bc["score"]):
                ages.append(b["r"] - bc["score"][j][0])
                ab.append(abs(bc["score"][j][1]))
                yrs.append(int(W.days[b["r"]].year))
        rho, ntr = brute_rho(Bz, c)
        ages, ab, yrs = np.array(ages), np.array(ab), np.array(yrs)
        o = e3[c]
        assert o["young"]["n"] == int((ages <= 21).sum()) and o["old"]["n"] == int((ages > 21).sum()) and o["young"]["n"] + o["old"]["n"] == len(ages) > 30 and ages.max() <= 63 and ages.min() >= 1
        assert abs(o["young"]["mean_abs_score"] - ab[ages <= 21].mean()) < 1e-12 and abs(o["old"]["mean_abs_score"] - ab[ages > 21].mean()) < 1e-12 and o["young"]["label"] == "1-21 sessions" and o["old"]["label"] == "22-63 sessions"
        for y, v in o["by_year"].items():
            assert v["young_n"] == int(((ages <= 21) & (yrs == y)).sum()) and v["old_n"] == int(((ages > 21) & (yrs == y)).sum()) and abs(v["young_mean_abs"] - ab[(ages <= 21) & (yrs == y)].mean()) < 1e-12
        assert set(o["by_year"]) == set(yrs.tolist()) and abs(sum(v["young_n"] + v["old_n"] for v in o["by_year"].values()) - len(ages)) == 0
        rc = o["rank_corr_with_RES"]
        assert rc["rebalances_that_trade"] == ntr > 0 and rc["rebalances"] == len(rho) >= 3 and abs(rc["mean"] - np.mean(rho)) < 1e-9 and abs(rc["min"] - min(rho)) < 1e-9 and abs(rc["max"] - max(rho)) < 1e-9 and -1.0 <= rc["min"] <= rc["mean"] <= rc["max"] <= 1.0, (c, rc, rho)
    with spec(n_side=2, min_scored=10 ** 6, min_side=10 ** 6):                                          # a world where NO month trades: the correlation still covers every rebalance with scored names ('at every rebalance')
        Ln, Bn = ed_build(W, lo, hi, "remove", units=False), brute_ed(W, lo, hi, "remove")
    en = e3_report(W, Ln)
    for c in CELLS:
        rn, ntr_n = brute_rho(Bn, c)
        rc = en[c]["rank_corr_with_RES"]
        assert ntr_n == 0 and not any(r_.traded for r_ in Ln.recs) and rc["rebalances_that_trade"] == 0 and rc["rebalances"] == len(rn) >= 3 and abs(rc["mean"] - np.mean(rn)) < 1e-9 and en[c]["young"]["n"] == e3[c]["young"]["n"], (c, rc, rn)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        print_e3(e3)
    txt = buf.getvalue()
    assert "[E3] BEFORE ANY P&L" in txt and "mean |score|" in txt and "rank correlation of the V3 score with RES" in txt and "1-21 sessions" in txt and "22-63 sessions" in txt and "$" not in txt, txt
    # a cell with no scored name at all (an empty leg): the report is empty-safe
    Le = SimpleNamespace(recs=[])
    eo = e3_report(W, Le)
    assert eo["V3"]["young"]["n"] == 0 and math.isnan(eo["V3"]["young"]["mean_abs_score"]) and eo["V3"]["rank_corr_with_RES"]["rebalances"] == 0 and math.isnan(eo["V3"]["rank_corr_with_RES"]["mean"])
    with quiet():
        print_e3(eo)


def write_calendar(path, rows, header="ticker,ndx_tickers,cik,name,form,accepted_et,reaction_session,timing,items,accession"):
    """a stub of TV's earnings calendar: rows = (ticker, 'A;B' ndx_tickers, reaction_session) -> the sha256 of its BYTES"""
    with open(path, "w", newline="\n") as f:
        f.write(header + "\n")
        for k, (tk, nd, rs) in enumerate(rows):
            f.write(f'{tk},{nd},{k:010d},{tk} CORP,8-K,2024-01-01 16:00,{rs},after-close,"2.02,9.01",0001-{k:06d}\n')
    return M17.sha_raw(path)


def t_e5():
    """[E5']: TV's calendar on a stub - refused when absent / another sha / a column missing (nothing computed), only release dates inside the WF stretch and before the cut are read (the rest counted), the join on ndx_tickers split on ';' (a RENAMED ticker matches through its
    old / new members-file ticker), a reaction session that is not a session of the harness (a Saturday) moves to the next one, one past the last is dropped, unmatched companies and the foreign filers are listed, and the shares of events on a release / of releases with no event
    equal a plain-python recount per July-June year"""
    with spec(n_side=2, min_scored=8, min_side=2):
        W = toy_events()
        attach_events(W)
        lo, hi = W.days[0], W.days[-1]
        L = ed_build(W, lo, hi, "remove", units=False)
        tf, ru = brute_mech(W.days)
    syms = [str(s) for s in W.syms]
    seen = {c: sorted((int(t), int(j)) for t, j in zip(*np.nonzero(L.seen[c]))) for c in CELLS}
    ev_of = lambda j: [t for t, j_ in seen["V3"] if j_ == j]
    mondays = [t for t in ev_of(7) if W.days[t].dayofweek == 0]
    assert len(ev_of(3)) >= 3 and len(ev_of(5)) >= 3 and len(mondays) >= 1 and len(ev_of(7)) >= 3, (len(ev_of(3)), len(ev_of(5)), len(ev_of(7)))
    d = lambda t: f"{W.days[t]:%Y-%m-%d}"
    rows = [("NEWN", "OLDN;N03", d(ev_of(3)[0])),                                                        # a renamed company: EDGAR's current ticker is NEWN, the cache symbol is N03 (the second ndx_ticker): the release is ON the event session
            ("NEWN", "OLDN;N03", d(ev_of(3)[1] - 1)),                                                    # the release's reaction session is the session BEFORE the event: the event is on the session after it
            ("NEWN", "OLDN;N03", d(ev_of(3)[2] + 7)),                                                    # a release some days after an event: no event on it (the K rule misses it, unless another event is there)
            ("N05", "N05", d(ev_of(5)[0])), ("N05", "N05", d(ev_of(5)[1] + 11)),
            ("QQQ", "X1;N07;X2", f"{W.days[mondays[0]] - pd.Timedelta(days=2):%Y-%m-%d}"),               # a Saturday: not a session of the harness -> the next session (the Monday = the event)
            ("QQQ", "X1;N07;X2", d(ev_of(7)[1])),
            ("ZZZ", "ZZZ", d(ev_of(3)[0])),                                                              # no ndx_ticker is a symbol of the world: unmatched
            ("NEWN", "OLDN;N03", "2016-06-30"), ("N05", "N05", "2025-06-30"), ("N05", "N05", "2025-07-01"), ("N07", "N07", "n/a"), ("N07", "N07", "")]       # before the WF stretch / ON the cut / after it / unreadable / empty: not read
    root = tempfile.mkdtemp(prefix="edrift_selftest_")
    try:
        cp = os.path.join(root, "earnings_calendar_ndx.csv")
        sha = write_calendar(cp, rows)
        tail = "(nothing computed, lockbox NOT read)"
        with patched(THIS, CAL_SHA=sha):
            fr, info = edgar_load(S.LB0, path=cp)
            assert info["present"] and info["matches"] and info["sha256"] == sha and info["rows_on_file"] == len(rows) and info["rows_read"] == 8 and info["rows_not_read"] == 5 and info["companies_read"] == 4, info
            assert len(fr) == 8 and fr["rs"].min() >= WF0 and fr["rs"].max() < S.LB0 and fr["tickers"].iloc[0] == ["OLDN", "N03"] and fr["ticker"].iloc[0] == "NEWN" and fr["tickers"].iloc[5] == ["X1", "N07", "X2"]
            assert info["first"] == fr["rs"].min().strftime("%Y-%m-%d") and info["last"] == fr["rs"].max().strftime("%Y-%m-%d")
            frn, infn = edgar_load(S.LB0, path=os.path.join(root, "absent.csv"), enforce=False)
            assert frn is None and infn["present"] is False
            refused(lambda: edgar_load(S.LB0, path=os.path.join(root, "absent.csv")), "is not on file", tail)
            with open(os.path.join(root, "nocol.csv"), "w", newline="\n") as f_:                         # a file with the registered sha (patched to this stub's) that lacks the ndx_tickers column
                f_.write("\n".join(["ticker,cik,name,form,accepted_et,reaction_session,timing,items,accession", "NEWN,1,X,8-K,2024-01-01 16:00,2024-02-01,after-close,2.02,0001", ""]))
            with patched(THIS, CAL_SHA=M17.sha_raw(os.path.join(root, "nocol.csv"))):
                refused(lambda: edgar_load(S.LB0, path=os.path.join(root, "nocol.csv")), "lacks the column", tail)
        with patched(THIS, CAL_SHA="0" * 64):
            refused(lambda: edgar_load(S.LB0, path=cp), "is not the registered one", "0" * 64, tail)
            frx, infx = edgar_load(S.LB0, path=cp, enforce=False)
            assert frx is None and infx["matches"] is False and infx["sha256"] == sha, "the dryload reports another file and does not read it"
        with open(cp, "a") as f:
            f.write("ZZZ,ZZZ,0,Z,8-K,x,2020-01-01,x,x,x\n")
        with patched(THIS, CAL_SHA=sha):
            refused(lambda: edgar_load(S.LB0, path=cp), "is not the registered one", tail)                  # one more row = another file
        # the cut at read: a calendar read with an EARLIER cut drops the later rows (and asserts none got through)
        with patched(THIS, CAL_SHA=M17.sha_raw(cp)):
            cutd = W.days[ev_of(3)[1]]
            f2, i2 = edgar_load(cutd, path=cp)
            assert f2["rs"].max() < cutd and 2 <= i2["rows_read"] < 9 and len(f2) == i2["rows_read"] and i2["rows_read"] + i2["rows_not_read"] == i2["rows_on_file"] == len(rows) + 1
        # the join and the shares against a plain-python recount
        mp = os.path.join(root, "ndx_members.csv")
        with open(mp, "w") as f:
            f.write("ticker,from,to\nN03,2016-06-01,\nOLDN,2016-06-01,2024-03-01\nN05,2016-06-01,\nN07,2016-06-01,\nFOR1,2016-06-01,\nFOR2,2020-01-01,\nLATE,2025-07-01,\n")
        mem = members_load(S.LB0, path=mp)
        assert mem == {"N03", "OLDN", "N05", "N07", "FOR1", "FOR2"}, "a members row whose `from` is on / after the cut is not read"
        assert members_load(S.LB0, path=os.path.join(root, "absent.csv")) is None
        rel_t, rel_j, jc = earn_join(W, fr, mem)
        sym_ix = {s: i for i, s in enumerate(syms)}
        want = []
        for tk, nds, rs in ((r_["ticker"], r_["tickers"], r_["rs"]) for _, r_ in fr.iterrows()):
            row = int(np.searchsorted(np.asarray(W.days), np.datetime64(rs)))
            for t_ in nds:
                if t_ in sym_ix and row < W.T:
                    want.append((row, sym_ix[t_]))
        assert sorted(zip(rel_t.tolist(), rel_j.tolist())) == sorted(want) and len(want) == 7, (sorted(zip(rel_t.tolist(), rel_j.tolist())), sorted(want))
        assert jc["releases_read"] == 8 and jc["releases_matched"] == 7 and jc["pairs_matched"] == 7 and jc["reaction_session_moved_to_the_next_session"] == 1 and jc["dropped_after_the_last_session"] == 0
        assert jc["companies_read"] == 4 and jc["companies_matched"] == 3 and jc["unmatched_companies"] == ["ZZZ"] and jc["matched_symbols"] == 3 and jc["members_ticker_not_in_the_calendar"] == ["FOR1", "FOR2"], jc
        late = pd.DataFrame({"ticker": ["A"], "tickers": [["N03"]], "rs": [W.days[-1] + pd.Timedelta(days=3)]})
        assert earn_join(W, late)[2]["dropped_after_the_last_session"] == 1 and len(earn_join(W, late)[0]) == 0, "one past the last session of the harness: dropped (counted)"
        e5 = earn_check(W, L, rel_t, rel_j)
        jy = lambda t: int(DV.jyear([W.days[t]])[0])
        for c in CELLS:
            RS = {(int(t), int(j)) for t, j in zip(rel_t, rel_j)}
            RS1 = RS | {(t + 1, j) for t, j in RS}
            cols = {j for _t, j in RS}
            evw = {(t, j) for t, j in seen[c] if j in cols}                                             # the cell's events inside the windows of pool names, of the matched symbols
            cover = set()
            for rec in L.recs:
                for t in range(rec.r - SPEC["look"], rec.r):
                    cover |= {(t, int(j)) for j in rec.pool}
            allev = {(int(t), int(j)) for t, j in zip(*np.nonzero(W.ed.EV[c]))}
            relw = RS & cover
            carry = {p for p in relw if p in allev or (p[0] + 1, p[1]) in allev}
            strict = {p for p in relw if p in allev}
            o = e5[c]
            count = lambda s: dict(Counter(jy(t) for t, _j in s))
            assert o["events"] == count(evw) and o["events_on_a_release"] == count({p for p in evw if p in RS1}) and o["releases_in_windows"] == count(relw) and o["releases_with_an_event"] == count(carry) and o["releases_with_an_event_on_the_session"] == count(strict), (c, o)
            t_ = o["total"]
            assert t_["events"] == len(evw) and t_["events_on_a_release"] == len({p for p in evw if p in RS1}) and t_["releases_in_windows"] == len(relw) and t_["releases_with_an_event"] == len(carry) and abs(t_["share_events_on_a_release"] - t_["events_on_a_release"] / t_["events"]) < 1e-15
            assert len(evw) >= 3 and len(relw) >= 2
            assert t_["releases_with_an_event_on_the_session"] == len(strict) and abs(t_["share_releases_without_an_event_on_the_session"] - (1.0 - len(strict) / len(relw))) < 1e-15 and t_["share_releases_without_an_event_on_the_session"] >= t_["share_releases_without_an_event"] - 1e-15
            for y, v in o["share_releases_without_an_event"].items():
                if o["releases_in_windows"].get(y, 0):
                    assert abs(v - (1.0 - o["releases_with_an_event"].get(y, 0) / o["releases_in_windows"][y])) < 1e-15 and 0.0 <= v <= 1.0
                else:
                    assert math.isnan(v), "a year with no release in a window has no share"
            assert all(0.0 <= v <= 1.0 for v in o["share_events_on_a_release"].values() if math.isfinite(v))
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            print_e5(info, jc, e5)
            print_e5(info, jc)
        txt = buf.getvalue()
        assert "[E5'] TV's EDGAR earnings calendar earnings_calendar_ndx.csv" in txt and "unmatched companies (1" in txt and "ZZZ" in txt and "FOR1, FOR2" in txt and "events of matched symbols inside the pool windows" in txt and "$" not in txt, txt
    finally:
        shutil.rmtree(root, ignore_errors=True)


# ------------------------------------------------------------------ the event-time path on a planted drift
def ev_world_c(seed=4, T=450, Sn=24, drift=0.5):
    """24 names x 450 weekdays: return = beta x ES + noise (0.4% a day), an event (6 x volume) every 45 .. 59 sessions with a news shock J (+-3 .. 8%) on its session and - drift - a continuation of drift x J spread over the sessions t+2 .. t+41 (nothing before t+2): the post-event drift the
    family is after. -> (W, {(row, col): J})"""
    rng = np.random.default_rng(seed)
    m = rng.normal(0.0, 0.008, T)
    m[0] = np.nan
    beta = rng.uniform(0.5, 1.5, Sn)
    ret = beta * np.nan_to_num(m)[:, None] + rng.normal(0.0, 0.004, (T, Sn))
    ret[0] = 0.0
    Vv = np.full((T, Sn), 1.0e6)
    shocks = {}
    for j in range(Sn):
        t = int(rng.integers(40, 70))
        while t < T - 62:
            J = float(rng.choice([-1.0, 1.0]) * rng.uniform(0.03, 0.08))
            Vv[t, j] = 6.0e6
            ret[t, j] += J
            ret[t + 2:t + 42, j] += drift * J / 40.0
            shocks[(t, j)] = J
            t += int(rng.integers(45, 60))
    return M17.mk_world(M17.prices(ret), m, Vv=Vv), shocks


def brute_event_path(W, Bz, cell, tf, ru):
    """plain python: the events of a cell inside the windows of pool names, each once at the FIRST rebalance whose window holds it (that rebalance's beta), those whose whole path t+2 .. t+60 is in the data -> [(t, j, beta, reaction, [abnormal return t+2 .. t+60])]"""
    claimed, out = set(), []
    for b in Bz:
        for j in sorted(b["pool"]):
            for t in range(b["r"] - SPEC["look"], b["r"]):
                if (t, j) not in claimed and brute_kind(W, cell, t, j, tf, ru) == "valid":
                    claimed.add((t, j))
                    beta = b["pool"][j]["beta"]
                    if t + SPEC["path_hi"] <= W.T - 1:
                        react = sum(M17.brute_ret(W, s, j) - beta * float(W.es.ret[s]) for s in (t - 1, t, t + 1))
                        out.append((t, j, beta, react, [M17.brute_ret(W, t + tau, j) - beta * float(W.es.ret[t + tau]) for tau in range(SPEC["path_lo"], SPEC["path_hi"] + 1)]))
    return out


def t_path():
    """[X2] the event-time path: the mean abnormal return from t+2 to t+60 by reaction decile (all years and by July-June year), against a plain-python recount (each event once at the first rebalance that holds it, that rebalance's beta, the deciles cut over all events), and on a
    PLANTED drift: the signed cumulative path is the planted continuation (half the news move) and the top decile climbs / the bottom decile falls; a world without the drift is flat"""
    out = {}
    for lab, drift in (("drift", 0.5), ("flat", 0.0)):
        W, shocks = ev_world_c(drift=drift)
        with spec(n_side=2, min_scored=8, min_side=2):
            attach_events(W)
            lo, hi = W.days[0], W.days[-1]
            L = ed_build(W, lo, hi, "remove", units=False)
            Bz = brute_ed(W, lo, hi, "remove")
        tf, ru = brute_mech(W.days)
        c = "V3"
        pth = ed_event_path(W, L, c)
        ev = brute_event_path(W, Bz, c, tf, ru)
        assert pth["events"] == len(ev) >= 40 and list(pth["taus"]) == list(range(2, 61)), (pth["events"], len(ev))
        react = np.array([e[3] for e in ev])
        A = np.array([e[4] for e in ev])
        qs = np.quantile(react, np.linspace(0.0, 1.0, 11))
        dec = np.clip(np.searchsorted(qs[1:-1], react, side="right"), 0, 9)
        assert sum(v["events"] for v in pth["deciles"].values()) == len(ev) and set(pth["deciles"]) == set(range(1, 11))
        for d_ in range(10):
            m = dec == d_
            v = pth["deciles"][d_ + 1]
            assert v["events"] == int(m.sum()) and abs(v["mean_react_bps"] - 1e4 * react[m].mean()) < 1e-8 and np.allclose(v["mean_bps"], 1e4 * A[m].mean(axis=0), atol=1e-8) and np.allclose(v["cum_bps"], np.cumsum(1e4 * A[m].mean(axis=0)), atol=1e-8), (lab, d_)
        sg = np.sign(react)[:, None] * A
        assert abs(pth["signed_cum_mean_bps"] - 1e4 * sg.sum(axis=1).mean()) < 1e-8
        yr = DV.jyear([W.days[e[0]] for e in ev])
        assert sum(v["events"] for v in pth["by_year"].values()) == len(ev) and set(pth["by_year"]) == set(yr.tolist())
        for y, v in pth["by_year"].items():
            mm = yr == y
            assert v["events"] == int(mm.sum()) and abs(v["signed_cum_mean_bps"] - 1e4 * sg[mm].sum(axis=1).mean()) < 1e-8
            for nm, d_ in (("top", 9), ("bottom", 0)):
                sel = mm & (dec == d_)
                assert v[nm + "_events"] == int(sel.sum()) and (not sel.any() or np.allclose(v[nm + "_cum_bps"], np.cumsum(1e4 * A[sel].mean(axis=0)), atol=1e-8)), (y, nm)
        out[lab] = (pth, shocks, ev)
    pd_, sh_, ev_ = out["drift"]
    pf = out["flat"][0]
    mj = float(np.mean([abs(sh_[(e[0], e[1])]) for e in ev_]))
    assert 0.6 * 0.5 * mj * 1e4 < pd_["signed_cum_mean_bps"] < 1.4 * 0.5 * mj * 1e4, (pd_["signed_cum_mean_bps"], 0.5 * mj * 1e4)
    assert abs(pf["signed_cum_mean_bps"]) < 0.25 * pd_["signed_cum_mean_bps"] and abs(pf["signed_cum_mean_bps"]) < 120.0, (pf["signed_cum_mean_bps"], pd_["signed_cum_mean_bps"])
    top, bot = pd_["deciles"][10]["cum_bps"], pd_["deciles"][1]["cum_bps"]
    assert top[-1] > 100.0 and bot[-1] < -100.0 and top[-1] - bot[-1] > 3.0 * (pf["deciles"][10]["cum_bps"][-1] - pf["deciles"][1]["cum_bps"][-1]), "the planted drift: the top reaction decile climbs, the bottom falls; the flat world's spread is a fraction"
    assert abs(top[0]) < 100.0 and abs(bot[0]) < 100.0, "nothing before t+2: the planted drift starts there"
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        print_path(pd_, "V3")
        print_path({"taus": np.arange(2, 61), "events": 3, "deciles": {}, "by_year": {}, "signed_cum_mean_bps": float("nan")}, "V5")
    assert "EVENT-TIME PATH [X2] V3" in buf.getvalue() and "t+60" in buf.getvalue() and "(too few events)" in buf.getvalue()
    Wt = ev_world_c(Sn=2, T=300)[0]
    attach_events(Wt)
    tiny = ed_event_path(Wt, SimpleNamespace(recs=[]), "V3")
    assert tiny["events"] == 0 and tiny["deciles"] == {}, "no event: an empty path, not an error"


# ------------------------------------------------------------------ the reference book [X1], the yardstick, the checks
def t_reference():
    """[X1] through r18_divrun on stubbed files and series only: the REFERENCE book (#463 + 0.264 x RES) is read from a stub of the RESMOM line file (pinned by the sha256 of its bytes), A2 is the reference + c x the cell against the reference with c by the registered volatility
    rule on EDRIFT's OWN window (2017-01-03 .. 2018-12-31, not DIVRUN's), 0.5c and 2c beside it, the plain #463 + c x cell a reported row - every number recounted by plain python - an incremental pass needs ROC and Sortino both strictly above the reference's, and the reference
    built from a series with EXACTLY the registered numbers reproduces them (the yardstick: ROC @ $30k 120.82, Sortino 3.916, worst drawdown $36,526)"""
    B, S12 = M17.synth_book(seed=3, hi="2026-06-30")
    k = np.flatnonzero(B.mask(WF0, PRE_END))
    ref = DV.mk_ref(B)
    rng = np.random.default_rng(8)
    mw = B.mask(*A2_WIN)
    assert int(mw.sum()) > 400 and B.index[mw][0] == TS("2017-01-03") and B.index[mw][-1] == TS("2018-12-31")
    for lab, xB in (("profitable and quiet", 40.0 + rng.normal(0.0, 50.0, B.n)), ("losing", -30.0 + rng.normal(0.0, 300.0, B.n)), ("noise", rng.normal(5.0, 300.0, B.n))):
        a2 = a2_report(B, xB, ref)
        sb, sc = float(np.std(B.raw[mw], ddof=1)), float(np.std(xB[mw], ddof=1))
        c_ = 0.25 * sb / sc
        assert a2["window"] == ["2017-01-03", "2018-12-31"] and a2["rows"] == int(mw.sum()) and a2["target"] == 0.25 and abs(a2["c"] - c_) <= 1e-9 * c_ and abs(a2["std_book"] - sb) <= 1e-9 * sb and abs(a2["std_cell"] - sc) <= 1e-9 * sc, (lab, a2["window"], a2["c"], c_)
        assert a2["at_half_c"]["c"] == 0.5 * a2["c"] and a2["at_double_c"]["c"] == 2.0 * a2["c"] and a2["book_shadow_line"] is a2["incremental_pass"] and "pass" not in a2
        ref_s = DV.plain_stats(ref.raw[k], B.index[k])
        assert abs(a2["reference"]["roc"] - ref_s["roc"]) < 1e-5 and abs(a2["reference"]["sortino"] - ref_s["sortino"]) < 1e-7 and a2["reference"]["weight_of_RES"] == 0.264
        for got, mult in ((a2, 1.0), (a2["at_half_c"], 0.5), (a2["at_double_c"], 2.0)):
            w_ = DV.plain_stats((ref.raw + mult * c_ * xB)[k], B.index[k])
            assert abs(got["roc"] - w_["roc"]) < 1e-5 and abs(got["sortino"] - w_["sortino"]) < 1e-7 and abs(got["net"] - w_["net"]) < 1e-3, (lab, mult)
        wp_ = DV.plain_stats((B.raw + c_ * xB)[k], B.index[k])
        assert abs(a2["plain_463"]["roc"] - wp_["roc"]) < 1e-5 and abs(a2["plain_463"]["sortino"] - wp_["sortino"]) < 1e-7, "the plain #463 + c x cell book is a reported row"
        assert a2["incremental_pass"] is bool(a2["roc"] > a2["reference"]["roc"] and a2["sortino"] > a2["reference"]["sortino"]), lab
        if lab == "profitable and quiet":
            assert a2["incremental_pass"] is True and a2["roc_gain"] > 0 and a2["sortino_gain"] > 0
        if lab == "losing":
            assert a2["incremental_pass"] is False and a2["roc_gain"] < 0
    flat = np.zeros(B.n)
    ax = a2_report(B, flat, ref)
    assert ax["incremental_pass"] is False and "error" in ax and ax["at_half_c"] is None, "a cell with no spread over the window has no c: no incremental pass, never an exception"
    at = {"roc": 100.0, "sortino": 3.0}
    assert DV.incremental_pass(at, {"roc": 99.99, "sort": 2.99}) is True and DV.incremental_pass(at, {"roc": 100.0, "sort": 2.0}) is False and DV.incremental_pass(at, {"roc": 90.0, "sort": 3.0}) is False
    assert DV.incremental_pass({"roc": float("nan"), "sortino": 3.0}, {"roc": 1.0, "sort": 1.0}) is False, "equal is not above; a NaN passes nothing"
    # the stub of RESMOM's line file: pinned by the sha256 of its bytes; the real file is never read
    root = tempfile.mkdtemp(prefix="edrift_selftest_")
    try:
        p = os.path.join(root, "resmom_cells_daily_wf.csv")
        res_wf = np.random.default_rng(31).normal(6.0, 320.0, len(k))
        sha = DV.write_ref_csv(p, B, res_wf)
        with patched(DV, REF_SHA=sha, REF_CSV=p):
            r1 = DV.ref_load(B, check_facts=False)
            assert r1.n_rows == len(k) and np.allclose(r1.raw[k], np.asarray(B.raw)[k] + 0.264 * res_wf, atol=1e-5) and os.path.basename(r1.path) == "resmom_cells_daily_wf.csv" and r1.sha == sha
            refused(lambda: DV.ref_load(B, check_facts=True), "does not reproduce its registered WF numbers", "(nothing computed, lockbox NOT read)")
        with patched(DV, REF_SHA="0" * 64, REF_CSV=p):
            refused(lambda: DV.ref_load(B, check_facts=False), "RESMOM line file", "is not the registered", "(nothing computed, lockbox NOT read)")
        with patched(DV, REF_SHA=sha, REF_CSV=os.path.join(root, "absent.csv")):
            refused(lambda: DV.ref_load(B, check_facts=False), "is not on file")
        # the yardstick: a series with EXACTLY the registered reference numbers is read back as 120.82 / 3.916 / $36,526, accepted by the real constants, and its drawdown days are the gate's basis
        reg = DV.reg_ref_series(B)
        sha2 = DV.write_ref_csv(p, B, DV.res_from_ref(B, reg))
        with patched(DV, REF_SHA=sha2, REF_CSV=p):
            r2 = DV.ref_load(B, check_facts=True)
        assert all(r2.ok.values()) and abs(r2.facts["roc"] - 120.82) < 0.01 and abs(r2.facts["sortino"] - 3.916) < 0.001 and abs(r2.facts["max_dd"] - 36526.0) < 1.0, r2.facts
        assert r2.structure["episodes"] == len(r2.S.qual) >= 1 and r2.structure["days"] == r2.S.n_dd_days
        with quiet():
            DV.print_reference(r2)
    finally:
        shutil.rmtree(root, ignore_errors=True)
    # MANAGER #70's gate basis on hand numbers
    ref_g = SimpleNamespace(structure={"episodes": 3, "days": 41})
    cg = {"seat_ref": {"DO": 0.20, "rho_dd": 0.1}, "episode_pnl": [100.0, -20.0, 50.0]}
    nul = {"do_ref_max": {"p5": -0.1, "p50": 0.05, "p95": 0.15}}
    g = gate70(cg, ref_g, nul)
    assert g["DO"] == 0.20 and g["DO_above_null_p95"] is True and g["pnl_without_best_episode"] == 30.0 and g["positive_without_best_episode"] is True and g["episodes"] == 3 and g["dd_days"] == 41 and g["null_do_p95"] == 0.15
    g = gate70({**cg, "seat_ref": {"DO": 0.15, "rho_dd": 0.0}, "episode_pnl": [100.0, -80.0, 10.0]}, ref_g, nul)
    assert g["DO_above_null_p95"] is False, "equal is not above"
    assert g["pnl_without_best_episode"] == -70.0 and g["positive_without_best_episode"] is False
    assert "null_do_p95" not in gate70(cg, ref_g, None) and "pnl_without_best_episode" not in gate70({"seat_ref": {"DO": 0.1, "rho_dd": 0.0}}, ref_g, None)


def t_yardstick():
    """ONE frontier yardstick: ROC @ $30k = 30 x (net / years) / (the deepest peak-to-trough of the daily equity from a peak of 0), years = (last - first row) / 365.25 - on a hand-checked series, through r11_risk.stats and through stat_run's stretch cut (the rows of the stretch, not of
    the positions); positions are counted by EXIT date, inclusive at both ends, the sub-period cut likewise"""
    x = [100.0, -300.0, 50.0, 50.0, 250.0]
    dates = pd.DatetimeIndex(["2020-01-01", "2020-04-01", "2020-07-01", "2020-10-01", "2021-01-01"])
    st = R11.stats(x, dates)
    yrs = 366 / 365.25
    assert st["max_dd"] == 300.0 and st["net"] == 150.0 and abs(st["years"] - yrs) < 1e-12 and abs(st["roc"] - 30.0 * (150.0 / yrs) / 300.0) < 1e-12, st
    assert not math.isfinite(R11.stats([5.0, 5.0, 5.0], dates[:3])["roc"]), "a series that never draws down has no yardstick"
    pl = DV.plain_stats(x, dates)
    assert abs(pl["roc"] - st["roc"]) < 1e-12 and abs(pl["sortino"] - st["sort"]) < 1e-12 and pl["max_dd"] == 300.0
    B, S12 = M17.synth_book(seed=3, hi="2026-06-30")
    with spec(n_side=2, min_scored=8, min_side=2):
        W = toy_events()
        attach_events(W)
        lo, hi = W.days[0], W.days[-1]
        L = ed_build(W, lo, hi, "remove")
    rowsB = A13.book_rows(B, W)
    xs = np.zeros(W.T)
    xs[[40, 50, 60, 70, 80]] = [900.0, -2000.0, 500.0, 300.0, 1200.0]
    run = SimpleNamespace(x=xs, cnt=np.zeros(W.T), n_pos=5, n_units=5, pos=SimpleNamespace(pnl=np.array([900.0, -2000.0, 500.0, 300.0, 1200.0])))
    stt, xB, cB = stat_run(B, rowsB, run)
    m = np.asarray((B.index >= WF0) & (B.index <= PRE_END))
    ds = B.index[m]
    eq, peak, mdd = 0.0, 0.0, 0.0
    for v in xB[m]:
        eq += v
        peak = max(peak, eq)
        mdd = max(mdd, peak - eq)
    years = (ds[-1] - ds[0]).days / 365.25
    assert abs(stt["net"] - xs.sum()) < 1e-9 and abs(stt["max_dd"] - mdd) < 1e-9 and abs(stt["years"] - years) < 1e-12 and abs(stt["roc"] - 30.0 * (xs.sum() / years) / mdd) < 1e-9 and mdd == 2000.0, (stt, mdd)
    assert abs(years - 8.99) < 0.02 and stt["n_pos"] == 5 and abs(stt["net_pos"] - 900.0) < 1e-9
    s2, _, _ = stat_run(B, rowsB, run, TS("2024-02-01"), TS("2024-12-31"))
    m2 = np.asarray((B.index >= TS("2024-02-01")) & (B.index <= TS("2024-12-31")))
    assert abs(s2["years"] - (B.index[m2][-1] - B.index[m2][0]).days / 365.25) < 1e-12 and abs(s2["net"] - xs.sum()) < 1e-9 and s2["years"] < 1.0
    # sub_run: the positions that EXIT in [lo, hi], inclusive at both ends, the daily series untouched
    cell = "V3"
    base = M17.run_cell(W, cell_leg(L, cell), D15.l1_cfg(), pos=True)
    exits = sorted({W.days[rec.x] for rec in L.recs if rec.cell[cell].traded})
    assert len(exits) >= 4
    per = {d: sum(2 * rec.cell[cell].k for rec in L.recs if rec.cell[cell].traded and W.days[rec.x] == d) for d in exits}
    one = sub_run(W, L, base, exits[1], exits[1])
    assert one.n_pos == per[exits[1]] > 0 and len(one.pos.pnl) == one.n_pos and one.n_units == 1 and one.x is base.x
    two = sub_run(W, L, base, exits[1], exits[2])
    assert two.n_pos == per[exits[1]] + per[exits[2]] and two.n_units == 2
    allr = sub_run(W, L, base, W.days[0], W.days[-1])
    assert allr.n_pos == base.n_pos == sum(per.values()) and abs(allr.pos.pnl.sum() - base.pos.pnl.sum()) < 1e-9
    before, after = sub_run(W, L, base, W.days[0], exits[1] - pd.Timedelta(days=1)), sub_run(W, L, base, exits[1] + pd.Timedelta(days=1), W.days[-1])
    assert before.n_pos + one.n_pos + after.n_pos == base.n_pos, "the end dates are inclusive: every position is in exactly one of before / on / after"
    assert sub_run(W, L, base, W.days[-1] + pd.Timedelta(days=5), W.days[-1] + pd.Timedelta(days=9)).n_pos == 0
    z = sub_run(W, L, SimpleNamespace(x=xs, cnt=np.zeros(W.T), pos=None), lo, hi)
    assert z.n_pos == 0 and len(z.pos.pnl) == 0


def t_judge():
    """Stage A's (a)-(e): every bar on its own - inclusive where the prereg says '>=', strict where it says 'above' / '> 0', a NaN fails every comparison it enters - then the tie-break between two passing cells, (f) never decided, the book-add comparison (reported) and Stage B's leg veto"""
    R = RULES
    st0 = {"n_units": 100, "roc": 20.0, "net": 1000.0, "years_pos": 7, "net_ex2020": 500.0, "net_ex_best_days": 100.0, "net_ex_best_pos": 100.0}
    nul0 = {"roc_max": {"p95": 10.0}}
    names = [f"rebalances>={R['reb']}", f"ROC>={R['roc']:g}", "net>0 at 5 bps", "net>0 at 10 bps", "ROC>null p95", f"positive in >={R['years']} of 9 July-June years", "net>0 without Feb 15 - Apr 30 2020", "profitable without its best 1% of days", "profitable without its best 1% of name-months"]
    ck = M17.judge_cell(st0, 50.0, nul0)
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
        return {k for k, v in M17.judge_cell(st, net10, nul).items() if not v}
    assert R["reb"] == 60 and R["roc"] == 15.0 and R["years"] == 6
    assert broken(n_units=59) == {names[0]} and broken(n_units=60) == set() and broken(n_units=0) == {names[0]}, "(a) at least 60 monthly rebalances, inclusive"
    assert broken(roc=14.99) == {names[1]} and broken(roc=15.0) == set() and broken(roc=15.0, p95=15.0) == {names[4]} and broken(roc=15.0, p95=14.99) == set(), "(b) ROC >= 15 inclusive; (c) strictly above the null's p95"
    assert broken(net=0.0) == {names[2]} and broken(net=-1.0) == {names[2]} and broken(net10=0.0) == {names[3]} and broken(net10=-0.01) == {names[3]}, "(b) net > 0 at 5 AND at 10 bps, strict"
    assert broken(years_pos=5) == {names[5]} and broken(years_pos=6) == set() and broken(years_pos=0) == {names[5]}, "(d) at least 6 of the 9 years, inclusive"
    assert broken(net_ex2020=0.0) == {names[6]} and broken(net_ex_best_days=0.0) == {names[7]} and broken(net_ex_best_pos=-5.0) == {names[8]} and broken(net_ex_best_pos=0.0) == {names[8]}, "(d) (e) strict"
    assert broken(roc=nan) == {names[1], names[4]} and broken(net=nan) == {names[2]} and broken(net10=nan) == {names[3]} and broken(p95=nan) == {names[4]} and broken(net_ex2020=nan) == {names[6]}
    assert broken(net_ex_best_days=nan) == {names[7]} and broken(net_ex_best_pos=nan) == {names[8]} and broken(years_pos=nan) == {names[5]}, "a NaN never passes"
    assert broken(n_units=1, roc=-3.0, net=-1.0, net10=-1.0, years_pos=0, net_ex2020=-1.0, net_ex_best_days=-1.0, net_ex_best_pos=-1.0) == set(names)
    mk = lambda v3, v5, roc=(20.0, 30.0): {"V3": {"PASS": v3, "base": {"roc": roc[0]}}, "V5": {"PASS": v5, "base": {"roc": roc[1]}}}
    passing, cand = stage_a_flow(mk(True, True))
    assert passing == ["V3", "V5"] and cand == "V5", "two passing cells: the higher WF ROC goes to Stage B"
    assert stage_a_flow(mk(True, True, roc=(30.0, 30.0)))[1] == "V3" and stage_a_flow(mk(True, True, roc=(31.0, 30.0)))[1] == "V3" and stage_a_flow(mk(True, True, roc=(30.0, 30.5)))[1] == "V5", "ties go to V3"
    passing, cand = stage_a_flow(mk(True, False, roc=(16.0, 90.0)))
    assert passing == ["V3"] and cand == "V3", "a lower-ROC passing cell is still the candidate when it is the only one; a failing cell is never the candidate"
    assert stage_a_flow(mk(False, False)) == ([], None) and pick_candidate({"V3": {"base": {"roc": 1.0}}}, []) is None
    leg = {"n_units": 10, "net": 1.0, "net_ex_top_pos": 0.5}
    assert all(M17.b_checks(leg).values()) and set(M17.b_checks(leg)) == {"leg monthly rebalances>=10", "leg net>0", "leg net>0 without its top name-month"}
    assert not M17.b_checks({**leg, "n_units": 9})["leg monthly rebalances>=10"] and not M17.b_checks({**leg, "net": 0.0})["leg net>0"] and not M17.b_checks({**leg, "net_ex_top_pos": 0.0})["leg net>0 without its top name-month"]
    assert not any(M17.b_checks({"n_units": 50, "net": nan, "net_ex_top_pos": nan})[k] for k in ("leg net>0", "leg net>0 without its top name-month"))
    assert M17.book_add_would_clear({"roc": RULES["b_roc"], "sortino": RULES["b_sort"]}) and not M17.book_add_would_clear({"roc": RULES["b_roc"] - 0.01, "sortino": RULES["b_sort"] + 1}) and not M17.book_add_would_clear({"roc": nan, "sortino": 9.0})


# ------------------------------------------------------------------ the audit file, the candidates, the turnover and the dividend flows
def t_files():
    """(f) the hand audit's file: read and checked (a mistyped row refuses, it never silently does nothing), a data_event removes that name-month from the pool - so from both cells and the nulls -, the audit status counts; the 50 largest gains (the hand-audit CSV) against the
    recount of the leg (event session, age, volume multiple, reaction, beta, the raw and split-adjusted move over the event window), turnover and the dividend flows recounted"""
    root = tempfile.mkdtemp(prefix="edrift_selftest_")
    try:
        with spec(n_side=2, min_scored=8, min_side=2):
            W = toy_events()
        ap = os.path.join(root, "edrift_audit.csv")
        assert read_audit(ap) is None
        open(ap, "w").write(f"symbol,date,cell,verdict,note\nN08,{W.days[270]:%Y-%m-%d},V3,data_event,split\nN01,{W.days[280]:%Y-%m-%d},v5,KEEP,fine\nN09,{W.days[300]:%Y-%m-%d},V5,data_event,bad print\n")
        au = read_audit(ap)
        assert au["verdict"].tolist() == ["data_event", "keep", "data_event"] and au["cell"].tolist() == ["V3", "V5", "V5"]
        cnt = apply_audit(W, au)
        assert cnt == {"rows": 3, "keep": 1, "data_event": 2} and W.aud1[270, 8] and W.aud1[300, 9] and W.aud1.sum() == 2, "a data_event row removes the name-month (by fill session)"
        assert apply_audit(W, None)["rows"] == 0 and not W.aud1.any()
        for bad in (f"N08,{W.days[270]:%Y-%m-%d},V3,maybe,x\n", "N08,not-a-date,V3,keep,x\n", f"N08,{W.days[270]:%Y-%m-%d},RES,keep,x\n", f",{W.days[270]:%Y-%m-%d},V3,keep,x\n"):
            open(ap, "w").write("symbol,date,cell,verdict,note\n" + bad)
            refused(lambda: read_audit(ap), "line(s) [2]")
        open(ap, "w").write("symbol,date\nN08,2024-01-01\n")
        refused(lambda: read_audit(ap), "lacks the column")
        for sym, d in (("ZZZ", W.days[270]), ("N08", pd.Timestamp("2025-01-04"))):                              # a data_event row that matches no name / no session must not silently do nothing
            open(ap, "w").write(f"symbol,date,cell,verdict,note\n{sym},{d:%Y-%m-%d},V3,data_event,x\n")
            refused(lambda: apply_audit(W, read_audit(ap)), "match no session or no name")
        open(ap, "w").write(f"symbol,date,cell,verdict,note\nN08,{W.days[270]:%Y-%m-%d},V3,data_event,x\nN05,{W.days[270]:%Y-%m-%d},V3,data_event,x\n")
        au = read_audit(ap)
        apply_audit(W, au)
        assert unused_audit_rows(W, au) == [f"N08 {W.days[270]:%Y-%m-%d} V3", f"N05 {W.days[270]:%Y-%m-%d} V3"], "no build has run yet: both rows are unused until a build hits them"
        W.aud_hit.add((AUD, 270, 8))
        assert unused_audit_rows(W, au) == [f"N05 {W.days[270]:%Y-%m-%d} V3"]
        d0 = f"{W.days[270]:%Y-%m-%d}"
        cands = {"V3": [{"symbol": "N08", "date": d0}], "V5": [{"symbol": "N08", "date": d0}, {"symbol": "N05", "date": "2024-01-01"}]}
        st = audit_status(cands, au)
        assert st["V3"] == {"listed": 1, "audited": 1, "audit_complete": True} and st["V5"] == {"listed": 2, "audited": 1, "audit_complete": False}
    finally:
        shutil.rmtree(root, ignore_errors=True)
    # a data_event removes the name-month from BOTH cells and from the nulls' pools
    with spec(n_side=2, min_scored=8, min_side=2):
        W = toy_events()
        attach_events(W)
        lo, hi = W.days[0], W.days[-1]
        L0 = ed_build(W, lo, hi, "remove")
        rec = next(r for r in L0.recs if W.days[r.r] == TS("2025-01-31"))
        j = int(rec.pool[rec.cell["V3"].idx[rec.cell["V3"].long[0]]])
        W.aud1[rec.f, j] = True
        L1 = ed_build(W, lo, hi, "remove", keep_ph=True)
        r1 = next(r for r in L1.recs if r.r == rec.r)
        assert j in rec.pool.tolist() and j not in r1.pool.tolist() and all(j not in r1.pool[r1.cell[c].idx].tolist() for c in CELLS) and L1.cnt[2025]["audit"] >= 1, "the name-month is out of the pool: of both cells' scored names"
        acc = ed_null(W, L1, 12, 0)
        assert all(a.shape == (12, W.T) for a in acc.values())
        W.aud1[:] = False
    # the candidates, turnover, dividend flows on the toy leg
    with spec(n_side=2, min_scored=8, min_side=2):
        W = toy_events()
        attach_events(W)
        lo, hi = W.days[0], W.days[-1]
        L = ed_build(W, lo, hi, "remove")
        Bz = brute_ed(W, lo, hi, "remove")
        by_r = {b["r"]: b for b in Bz}
        for cell in CELLS:
            run = M17.run_cell(W, cell_leg(L, cell), D15.l1_cfg(), pos=True)
            cd = ed_candidate_rows(W, L, cell, run, None, {})
            pnl = [x["pnl"] for x in cd]
            n_pos = sum(2 * r.cell[cell].k for r in L.recs if r.cell[cell].traded)
            assert len(cd) == min(AUDIT_N, n_pos) and pnl == sorted(pnl, reverse=True) and abs(pnl[0] - float(run.pos.pnl.max())) < 1e-9, "the largest gains first"
            assert {"symbol", "date", "exit", "side", "pnl", "score", "rank_date", "event", "event_age", "event_volume_multiple", "reaction", "beta", "raw_move_event_window", "adj_move_event_window", "factor_ratio_window_to_exit", "tbis_price_ratio", "asset_status", "flags_in_window"} <= set(cd[0])
            assert "raw_move_formation" not in cd[0] and "adj_move_formation" not in cd[0], "RESMOM's formation-window moves are left out"
            for x_ in cd:
                j = list(W.syms).index(x_["symbol"])
                rr = next(r for r in L.recs if f"{W.days[r.f]:%Y-%m-%d}" == x_["date"])
                b = by_r[rr.r]
                t, react = b["cell"][cell]["score"][j]
                assert x_["rank_date"] == f"{W.days[rr.r]:%Y-%m-%d}" and x_["event"] == f"{W.days[t]:%Y-%m-%d}" and x_["event_age"] == rr.r - t and abs(x_["reaction"] - react) < 1e-9 and abs(x_["score"] - react) < 1e-9 and abs(x_["beta"] - b["pool"][j]["beta"]) < 1e-9, (cell, x_["symbol"], x_["date"])
                va = lambda s: float(W.Vv[s, j] * W.F[s, j])
                base = [v for v in (va(s) for s in range(t - 21, t - 1)) if math.isfinite(v)]
                assert abs(x_["event_volume_multiple"] - va(t) / (sum(base) / len(base))) < 1e-9 and x_["event_volume_multiple"] >= KS[cell] - 1e-9
                assert abs(x_["raw_move_event_window"] - (W.Cl[t + 1, j] / W.Cl[t - 2, j] - 1.0)) < 1e-12 and abs(x_["adj_move_event_window"] - (W.Ac[t + 1, j] / W.Ac[t - 2, j] - 1.0)) < 1e-12
                assert x_["side"] in ("long", "short") and x_["date"] < x_["exit"]
            # turnover: the share of each side's names not on the same side at the previous traded rebalance
            tn = ed_turnover(L, cell)
            sets = [(set(rec.pool[rec.cell[cell].idx[rec.cell[cell].long]].tolist()), set(rec.pool[rec.cell[cell].idx[rec.cell[cell].short]].tolist()), rec.cell[cell].k) for rec in L.recs if rec.cell[cell].traded]
            rows = [(1.0 - len(b_[0] & a_[0]) / b_[2], 1.0 - len(b_[1] & a_[1]) / b_[2], len(b_[0] & a_[0]) + len(b_[1] & a_[1])) for a_, b_ in zip(sets[:-1], sets[1:])]
            assert tn["traded_rebalances"] == len(sets) and tn["transitions"] == len(rows) and abs(tn["long_replaced_mean"] - np.mean([r_[0] for r_ in rows])) < 1e-12 and abs(tn["short_replaced_mean"] - np.mean([r_[1] for r_ in rows])) < 1e-12
            assert abs(tn["cost_saved_if_only_changes_traded_usd_estimate"] - sum(r_[2] for r_ in rows) * 4000 * 2 * 5e-4) < 1e-9 and tn["replaced_min"] <= tn["replaced_mean"] <= tn["replaced_max"]
            # [R1] the dividend flows inside the picks, recounted by plain python
            fl = ed_div_flows(L, cell)
            wl = ws = 0.0
            nl = ns = 0
            for b in Bz:
                for sd, js in ((1, b["cell"][cell]["long"]), (-1, b["cell"][cell]["short"])):
                    for j in js:
                        d_ = sum(M17.brute_div(W, b["f"], b["x"], j, b["pool"][j]["naive"]))
                        if sd > 0:
                            wl, nl = wl + 4000.0 * d_, nl + (d_ > 0)
                        else:
                            ws, ns = ws + 4000.0 * d_, ns + (d_ > 0)
            assert abs(fl["long_received"] - wl) < 1e-9 and abs(fl["short_paid"] - ws) < 1e-9 and fl["long_positions_with_a_dividend"] == nl and fl["short_positions_with_a_dividend"] == ns, (cell, fl, wl, ws)
            # events per month / name, the earnings-month shares
            es_ = ed_event_stats(W, L, cell)
            tt, jj = np.nonzero(L.seen[cell])
            mo = W.days[tt].month
            assert es_["events"] == len(tt) and sum(es_["by_month"].values()) == len(tt) and es_["names_with_an_event"] == len(set(jj.tolist())) and abs(es_["share_in_earnings_months"] - np.isin(mo, (1, 4, 7, 10)).mean()) < 1e-12
            assert abs(es_["share_in_first_two_months"] - np.isin(mo, (1, 2, 4, 5, 7, 8, 10, 11)).mean()) < 1e-12 and es_["per_name_max"] == max(Counter(jj.tolist()).values())
        assert sum(ed_div_flows(L, c)["long_received"] + ed_div_flows(L, c)["short_paid"] for c in CELLS) > 0, "the toy world's picks do carry dividends"
        sp = {c: ed_spin_counts(L, c) for c in CELLS}
        for c in CELLS:
            tot = 0
            for rec in L.recs:
                cc = rec.cell[c]
                if cc.traded:
                    tot += len(cc.long) + len(cc.short)
            assert sp[c]["long"]["positions"] + sp[c]["short"]["positions"] == tot and sp[c]["long"]["hold_positions"] == sp[c]["short"]["hold_positions"] == 0, "the registered reading removed every name with an ex-date inside the hold"
        with quiet():
            print_spin_picks({"registered reading": sp})


# ------------------------------------------------------------------ the whole thing on a hand-made world: evaluate, reports, printing
def t_integration():
    """evaluate / reports / candidate rows on the toy world, a synthetic #463 and a synthetic reference (no files): every statistic is the independent sum, the cost curve and the sides add up, both nulls run, A2 is incremental over the reference, MANAGER #70's gate basis and the
    diagnostics carry every row of the prereg's REPORTED paragraph and addendum 2's list, everything is JSON-serialisable, and the printout puts [E3] / [E5'] before any P&L"""
    B, S12 = M17.synth_book(seed=15)
    ref = DV.mk_ref(B)
    with spec(n_side=2, min_scored=8, min_side=2):
        W = toy_events()
        attach_events(W)
        rows = A13.book_rows(B, W)
        spy, real_judge = [], M17.judge_cell

        def judge_spy(st, net10, nul):
            spy.append((st, net10, nul))
            return real_judge(st, net10, nul)
        with patched(THIS, A2_WIN=(TS("2024-12-02"), TS("2025-05-30"))), patched(M17, judge_cell=judge_spy):                # the toy world's own positions, so c exists
            res, obj = evaluate(W, B, S12, ref, rows, "remove", 40, 0, full=True)
        assert [(a_[0], a_[1]) for a_ in spy] == [(res["cells"][c]["base"], res["cells"][c]["stress"]["10 bps"]["net"]) for c in CELLS] and all(a_[2] is res["null"] for a_ in spy), "judge_cell reads each cell's own base stats, its 10 bps net and the registered null"
        with patched(THIS, A2_WIN=(TS("2024-12-02"), TS("2025-05-30"))):
            resK, objK = evaluate(W, B, S12, ref, rows, "naive", 40, 1, full=False)
            with div_mode(W, False):
                resD = evaluate(W, B, S12, ref, rows, "remove", 40, 2, full=False)[0]
            first_rank = W.days[obj.legs.recs[0].r]
            resF, objF = evaluate(W, B, S12, ref, rows, "remove", 40, 3, full=False, drop=(first_rank,))
        Bz = brute_ed(W, WF0, PRE_END, "remove")                                                    # the stretch's rebalances: positions that exit by 2025-06-29
        slot = M17.SPEC["slot"]
        for cell in CELLS:
            c = res["cells"][cell]
            x0 = np.zeros(W.T)
            n_pos = 0
            for b in Bz:
                for sd, js in ((1, b["cell"][cell]["long"]), (-1, b["cell"][cell]["short"])):
                    for j in js:
                        x0[b["f"]:b["x"] + 1] += slot * np.array(M17.brute_path(W, b["f"], b["x"], j, sd, b["pool"][j]["naive"])[0])
                        n_pos += 1
            inwf = [b for b in Bz if b["cell"][cell]["k"] > 0]
            assert abs(c["base"]["net"] - x0.sum()) < 1e-6 and c["base"]["n_units"] == len(inwf) and c["base"]["n_pos"] == n_pos and abs(c["base"]["net_pos"] - x0.sum()) < 1e-6, (cell, c["base"]["net"], x0.sum())
            assert set(c["stress"]) == {"10 bps", "20 bps"} and c["cost0"]["net"] > c["base"]["net"] > c["stress"]["10 bps"]["net"] > c["stress"]["20 bps"]["net"], "the cost curve: more cost, less P&L (every position pays at both ends)"
            assert abs((c["sides"]["long side only"]["net"] + c["sides"]["short side only"]["net"]) - c["base"]["net"]) < 1e-6
            assert set(c["extra"]) == {"borrow 1% on k>1.5 sessions", "borrow 3% on k>1.5 sessions", "longs that stop printing valued at -100%", M17.R2_CELL} and c["extra"]["borrow 3% on k>1.5 sessions"]["net"] <= c["extra"]["borrow 1% on k>1.5 sessions"]["net"] + 1e-9 <= c["base"]["net"] + 1e-9
            assert set(c["sub"]) == {s[0] for s in SUBPERIODS} and c["sub"][SUBPERIODS[0][0]]["n_pos"] == 0 and c["sub"][SUBPERIODS[1][0]]["n_pos"] == c["base"]["n_pos"] and abs(c["sub"][SUBPERIODS[1][0]]["net"] - c["base"]["net"]) < 1e-6
            assert set(c["checks"]) == set(real_judge(c["base"], 1.0, res["null"])) and c["PASS"] is False, "the toy world cannot clear the bars (5 rebalances)"
            a2 = c["A2"]
            assert a2["window"] == ["2024-12-02", "2025-05-30"] and math.isfinite(a2["c"]) and abs(a2["c"] * a2["std_cell"] - 0.25 * a2["std_book"]) <= 1e-9 * a2["std_book"] and "reference" in a2 and "plain_463" in a2 and "pass" not in a2
            assert c["seat_ref"]["dd_days"] == ref.structure["days"] and len(c["episode_pnl"]) == len(ref.S.qual) and c["gate70"]["DO"] == c["seat_ref"]["DO"] and c["gate70"]["episodes"] == ref.structure["episodes"]
            assert c["gate70"]["null_do_p95"] == res["null"]["do_ref_max"]["p95"] and c["gate70"]["DO_above_null_p95"] is bool(c["seat_ref"]["DO"] > res["null"]["do_ref_max"]["p95"]) and "positive_without_best_episode" in c["gate70"]
            assert c["short_stopped"]["short_positions"] == sum(r.cell[cell].k for r in obj.legs.recs if r.cell[cell].traded)
        assert res["null"]["draws"] == 40 and resK["null"]["draws"] == 40 and res["null"]["seed"] == SEED and set(res["null"]["by_cell"]) == set(CELLS) and res["null"]["do_ref_max"]["finite"] == 40
        pl = res["placebo"]
        assert pl["draws"] == 40 and pl["seed"] == SEED_PLACEBO and set(pl["real_roc_percentile_by_cell"]) == set(CELLS) and set(pl["info"]) == set(CELLS) and resK["placebo"] is None and resD["placebo"] is None and all(isinstance(v, bool) for v in pl["real_roc_above_p95_by_cell"].values())
        assert resD["null"]["draws"] == 40 and resF["null"]["draws"] == 40 and len(objF.legs.recs) == len(obj.legs.recs) - 1 and sum(c_.get("dropped_d1", 0) for c_ in objF.legs.cnt.values()) == 1, "[D1]: the dropped rank is out of the cell AND the null, counted"
        assert any(abs(res["cells"][c]["base"]["net"] - resD["cells"][c]["base"]["net"]) > 1e-6 for c in CELLS), "the dividends move the picks / P&L in the toy world"
        # the no-dividend reading's events are re-attached on the same returns without the cash: R3 differs where a dividend fell in an event window, the events themselves do not
        e_div = W.ed
        with div_mode(W, False):
            assert W.ed is not e_div and all((W.ed.EV[c] == e_div.EV[c]).all() for c in CELLS) and not np.allclose(np.nan_to_num(W.ed.R3), np.nan_to_num(e_div.R3))
        assert W.ed is e_div and W.div_on is True, "div_mode puts the dividends and the events back"
        rep, cands = reports(W, B, S12, ref, rows, obj, res["cells"], None, {}, [])
        for key in ("beta_to_es", "episodes", "ref_episodes", "map_point", "corr_with_legs", "corr_with_res", "pick_overlap_with_res", "top20_gains", "months", "turnover", "survivorship", "dividend_flows", "event_stats", "event_path", "manifest_sha256"):
            assert key in rep, key
        assert list(rep["beta_to_es"]["V3"]) == ["DD days", "DD weeks (every day of them)", "all WF days"] and rep["map_point"]["V5"]["standalone_roc_30k"] == res["cells"]["V5"]["base"]["roc"]
        for cell in CELLS:
            xs = obj.series[cell][0]
            kw = np.flatnonzero(B.mask(WF0, PRE_END))
            assert abs(rep["corr_with_res"][cell] - float(np.corrcoef(xs[kw], ref.res[kw])[0, 1])) < 1e-12 and len(rep["ref_episodes"][cell]) == len(ref.S.qual)
            ov = rep["pick_overlap_with_res"][cell]
            assert 0.0 <= ov["long_in_res_long"] <= 1.0 and 0.0 <= ov["short_in_res_short"] <= 1.0 and ov["rebalances"] >= 1
            mn = rep["months"][cell]
            assert abs(sum(mn.values()) - res["cells"][cell]["base"]["net"]) < 1e-6
            assert rep["event_path"][cell]["events"] >= 0
        assert json.loads(json.dumps({"res": res, "rep": rep}, default=R11.js)) is not None
        ast = {c: {"listed": 5, "audited": 0, "audit_complete": False} for c in CELLS}
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            print_events(W.ed)
            print_cells(res, ast)
            print_reports(rep, res["cells"])
            for c in CELLS:
                print_path(rep["event_path"][c], c)
            print_diagnostics(res, rep, ref)
            print_counts("registered", obj.legs.cnt)
            print_scored("registered", obj.legs.cnt)
        txt = buf.getvalue()
        for frag in ("[E1] mechanical volume days are not news", "null: RANDOM NAMES, registered (40 draws, seed 20261005", "second null: PLACEBO IN TIME, REPORTED (40 draws, seed 20261006", "#70 gate basis [X1]", "DIAGNOSTICS [X2]", "COST CURVE", "BY JULY-JUNE YEAR",
                     "THE TWO REGIME HALVES", "THE LONG AND SHORT SIDES APART", "EVENT-TIME PATH [X2] V3", "A2 (a report) [X1]", "realised beta to ES", "turnover", "against RES: daily P&L correlation", "events inside the pool windows", "dividends [R1]", "short leg [R2]", "survivorship"):
            assert frag in txt, frag
    # the printout of Stage A puts [E3] / [E5'] before any P&L: its order is fixed in stage_a itself (checked end to end in the smoke); here the pieces: an e3 / e5 print has no dollar amount
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        print_e3(e3_report(W, objF.legs))
    assert "$" not in buf.getvalue() and "net" not in buf.getvalue().lower().replace("magnitude", "")


def t_stage_b_refusals():
    """every Stage B refusal that needs no data, none of which may write the read flag: the lead's go-flag FIRST (nothing computed), then no Stage A candidate (each broken piece), the flag already there, a changed spec / harness / audit, a broken frozen size"""
    root = tempfile.mkdtemp(prefix="edrift_selftest_")
    try:
        out = os.path.join(root, "out")
        os.makedirs(out)
        go, flag, sap = os.path.join(out, GO_FLAG), os.path.join(out, READ_FLAG), os.path.join(out, "edrift_stageA.json")
        good = {"judged": True, "prereg_sha256_lf": PREREG_SHA, **stamp(), "audit_sha256": None, "candidate": {"cell": "V5", "c": 0.8317}, "stageA": {"cells": {"V5": {"PASS": True}}, "pass_cells": ["V5"]}, "parity": {}}

        def must(frag, sa=None, **kw):
            with open(sap, "w") as f:
                json.dump(good if sa is None else sa, f)
            try:
                with contextlib.redirect_stdout(io.StringIO()), patched(THIS, OUT=out, **kw):
                    stage_b()
                raise AssertionError(f"Stage B must refuse ({frag})")
            except SystemExit as e:
                assert frag in str(e), (frag, str(e))
                assert not os.path.exists(flag) or frag == "already read", "a refused Stage B must not burn the lockbox"
        try:                                                                                    # no go-flag: refused before anything is read
            with patched(THIS, OUT=out):
                stage_b()
            raise AssertionError("no go-flag")
        except SystemExit as e:
            assert GO_FLAG in str(e) and "go-flag" in str(e) and "nothing computed, lockbox NOT read" in str(e)
        with open(sap, "w") as f:
            json.dump(good, f)
        with patched(THIS, OUT=out):                                                            # a Stage A file that says pass is not the go-flag
            refused(stage_b, "go-flag")
        assert not os.path.exists(flag)
        with open(go, "w") as f:
            f.write("the lead's go-flag: hand audit done")
        try:                                                                                    # go-flag but no Stage A file at all
            os.remove(sap)
            with patched(THIS, OUT=out):
                stage_b()
            raise AssertionError("no Stage A file")
        except SystemExit as e:
            assert "no Stage A candidate" in str(e)
        mut = lambda f: (lambda d: (f(d), d)[1])(json.loads(json.dumps(good)))
        for nm, sa in (("not judged", mut(lambda d: d.update(judged=False))), ("no candidate", mut(lambda d: d.update(candidate=None))), ("a pending audit", mut(lambda d: d.update(judged=None))),
                       ("cell not a pass cell", mut(lambda d: d["stageA"].update(pass_cells=["V3"]))), ("no pass cells", mut(lambda d: d["stageA"].update(pass_cells=[]))), ("no stageA", mut(lambda d: d.update(stageA=None)))):
            must("no Stage A candidate", sa)
        open(flag, "w").write("x")
        must("already read", good)
        os.remove(flag)
        must("DIFFERS", good, PREREG_SHA="0" * 64)
        must("another pre-registration", mut(lambda d: d.update(prereg_sha256_lf="0" * 64)))
        for nm, edit in (("harness", lambda d: d.update(harness_sha256="0" * 64)), ("r17", lambda d: d.update(r17_sha256="0" * 64)), ("r18", lambda d: d.update(r18_sha256="0" * 64)), ("early close", lambda d: d.update(early_close=d["early_close"][1:])),
                         ("r15", lambda d: d.update(r15_sha256="0" * 64)), ("r13", lambda d: d.pop("r13_sha256")), ("the calendar", lambda d: d.update(earnings_calendar_sha256="0" * 64)), ("the Russell list", lambda d: d.update(russell_days=d["russell_days"][1:])),
                         ("no stamp", lambda d: [d.pop(k) for k in stamp()])):
            must("different harness version", mut(edit))
        must("not the file Stage A ran with", mut(lambda d: d.update(audit_sha256="0" * 64)))
        with open(os.path.join(out, "edrift_audit.csv"), "w") as f:
            f.write("symbol,date,cell,verdict,note\n")
        sha = file_sha(os.path.join(out, "edrift_audit.csv"))
        for badc in (0.0, -1.0, None, "abc", float("nan"), float("inf")):                      # c is a volatility ratio: any positive number is a frozen size; NaN / 0 / negative / missing / text is a broken file
            must("positive number", mut(lambda d, b=badc: d.update(audit_sha256=sha, candidate={"cell": "V5", "c": b})))
        must("not one of", mut(lambda d: d.update(audit_sha256=sha, candidate={"cell": "V9", "c": 0.8317}, stageA={"cells": {"V9": {"PASS": True}}, "pass_cells": ["V9"]})))
        assert not os.path.exists(flag), "no refusal wrote the flag"
    finally:
        shutil.rmtree(root, ignore_errors=True)


def t_cut():
    """Stage A asks for data cut at 2025-06-30 and refuses a session on / after it (the loaders and the book are stubbed; nothing real is read); a changed pre-registration, an absent / other earnings calendar, the manifest, the book and the reference gates all refuse before any
    data is asked for; the World's cut; Stage A is frozen once the lockbox was read"""
    seen = {}

    def stub(t_end, open5=True):
        assert t_end == S.LB0 and open5 is False, "Stage A must ask for data cut at 2025-06-30 and read no 09:30 bar"
        seen["t"], seen["open5"] = t_end, open5
        return SimpleNamespace(days=pd.DatetimeIndex(["2025-06-27", "2025-06-30"]))
    S12 = SimpleNamespace(qual=[])
    okbk = ({"roc": 0.0, "sortino": 0.0, "ref": [0, 0], "ok": True}, {"deepest": 0.0, "episodes": 0, "days": 0, "weeks": 0, "by_year": {}, "episode_2020": True, "ok": True}, S12)
    devnull = lambda: contextlib.redirect_stdout(open(os.devnull, "w"))
    Bs, _ = M17.synth_book(seed=3, hi="2026-06-30")
    ref0 = DV.mk_ref(Bs)
    no_wide = lambda *a, **k: (SimpleNamespace(div=None, split=None, info={}), {})                               # the wide calendar's own gates are tested in r17_resmom; here it is stubbed
    root = tempfile.mkdtemp(prefix="edrift_selftest_")
    out = os.path.join(root, "out")
    os.makedirs(out)
    cp = os.path.join(root, "earnings_calendar_ndx.csv")
    sha = write_calendar(cp, [("AAA", "AAA", "2024-02-01")])

    def bad_ref(B, check_facts=None):
        refuse("refused: the RESMOM line file x is not the registered y (nothing computed, lockbox NOT read)")

    def must(frag, **kw):
        seen.clear()
        with devnull(), patched(THIS, **kw):
            refused(stage_a, frag)
        assert not os.path.exists(os.path.join(out, "edrift_stageA.json")) and not os.path.exists(os.path.join(out, READ_FLAG)), "a refusal writes nothing"
        return dict(seen)
    try:
        with patched(S, Data=stub), patched(A13, load_463=lambda: (Bs, [])), patched(M17, wide_load=no_wide), patched(DV, ref_load=lambda B, check_facts=None: ref0),                 patched(THIS, book_checks=lambda B: okbk, manifest_sha=lambda: D15.MANIFEST_PREFIX + "0" * 56, OUT=out, CAL_CSV=cp, CAL_SHA=sha, MEMBERS_CSV=os.path.join(root, "no_members.csv")):
            assert "t" not in must("DIFFERS", PREREG_SHA="0" * 64), "a changed pre-registration refuses before any data is asked for"
            assert "t" not in must("TV's EDGAR earnings calendar is not on file", CAL_CSV=os.path.join(root, "x", "absent.csv"))
            assert "t" not in must("is not the registered one", CAL_SHA="0" * 64)
            seen.clear()
            with devnull():
                try:
                    stage_a()
                    raise AssertionError("Stage A must refuse a session on/after the cut")
                except SystemExit as e:
                    assert "on/after the cut" in str(e) and seen["t"] == S.LB0 and seen["open5"] is False, (str(e), seen)
            for mf, frag in ((lambda: None, "manifest is missing"), (lambda: "ffff" + "0" * 60, "not the registered photograph")):
                assert "t" not in must(frag, manifest_sha=mf)
            assert "t" not in must("do not reproduce", book_checks=lambda B: ({"roc": 1.0, "sortino": 1.0, "ref": [0, 0], "ok": False}, okbk[1], S12))
            assert "t" not in must("do not reproduce", book_checks=lambda B: (okbk[0], {**okbk[1], "ok": False}, S12))
            with patched(DV, ref_load=bad_ref):
                assert "t" not in must("RESMOM line file")
            with open(os.path.join(out, READ_FLAG), "w") as f:
                f.write("x")
            refused(stage_a, "Stage A is frozen")
    finally:
        shutil.rmtree(root, ignore_errors=True)
    # the World's cut: a session on / after the stage's cut is refused; so is a calendar row on / after it
    cut_checks(SimpleNamespace(days=pd.DatetimeIndex(["2025-06-26", "2025-06-27"])), None, S.LB0)
    refused(lambda: cut_checks(SimpleNamespace(days=pd.DatetimeIndex(["2025-06-27", "2025-06-30"])), None, S.LB0), "on/after the cut")
    refused(lambda: cut_checks(SimpleNamespace(days=pd.DatetimeIndex(["2025-06-27"])), SimpleNamespace(div=pd.DataFrame({"ex": pd.DatetimeIndex(["2025-06-30"])}), spin=None, split=None), S.LB0), "on/after the cut")
    # book_checks on a synthetic book that does not match the registered structure: ok False, with the numbers
    B, _ = M17.synth_book(seed=2, hi="2025-06-27", deep=False)
    bk, dd, S12b = D15.book_checks(B)
    assert bk["ok"] is False and dd["ok"] is False and dd["days"] == S12b.n_dd_days and dd["episodes"] == len(S12b.qual)


# ------------------------------------------------------------------ smoke: an offline end-to-end run on SYNTHETIC worlds (every number means nothing)
SMOKE_DRIFT = 0.5                                  # the planted continuation: half of the news move J spread over the 40 sessions t+2 .. t+41 - in the PLANTED world only
SMOKE_SPEC = {"n_side": 15, "min_scored": 45, "min_side": 10}      # the synthetic market has ~65 scored names a month, not the 150 .. 500 of the real one: 15 a side (the top / bottom third below 45 scored names, at least 10 a side)
SMOKE_RELEASE = (0.8, 0.1)                         # of the planted events: a release on the event session / on the session before it (the rest: none)
SMOKE_EXTRA = 0.3                                  # a release the K rule misses (no event on it), per planted event


def smoke_refusal(root):
    """r17_resmom's guards (the dir is wiped: a 'smoke' name, never OUT / CACHE / the repo / this harness / the working directory / C:\\EdgeLog, the other families' OUTs, the #463 records) + this harness's OUT"""
    why = M17.smoke_refusal(root)
    if why:
        return why
    real = lambda p: os.path.normcase(os.path.realpath(p))
    try:
        if os.path.commonpath([real(root), real(OUT)]) == real(root):
            return f"smoke refused: {root} is or holds EDRIFT OUT"
    except ValueError:
        pass
    return None


class EdFake(DV.DivFake):
    """r18_divrun's synthetic daily market (80 names on continuous business days through r5_siporb's fake Alpaca transport, close-to-close log return = beta x the fake ES master's return + noise, the calendar's dividends taken off the open of the ex-date, the special names of S.Fake
    with their plants: SPL's 2-for-1 on 2024-03-15, S18's missed x4 on 04-22, S23's +60% gap on 05-14, DLST's last bar on 05-31, S33 / S34's late starts, LOWP / LOWV / LOWA below the filters, RVS's reverse split) with EVENTS in place of the dividend run-up: every name (but the LOW* ones)
    has a news session every 18 .. 43 sessions - a volume of 4 x (35%) or 7 x its normal and a shock J of +-3 .. 8% on that session's return - and with drift > 0 the market continues in the direction of the news: drift x J spread over the sessions t+2 .. t+41 (the PLANTED world; the
    NULL world has the same events and shocks and no continuation). Every name also trades 4.5 x its volume on the third Friday of March / June / September / December and 6 x on the Russell days (the mechanical days [E1] must exclude), and the flagged sessions of the special
    names (SPL's split day, S18's missed-split day, S23's gap day) carry a 7 x spike that a hygiene flag must void. self.plan = [(session row, name column, multiple, J)]"""
    def __init__(self, days, mkt, div, drift=0.0, page=2500):
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
        for sym, ex, amt, _special in div:
            if sym in self.k:
                t = dayidx.searchsorted(pd.Timestamp(ex))
                if t < D and dayidx[t] == pd.Timestamp(ex):
                    divamt[t, self.k[sym]] += amt
        # the events (their own stream: the planted and the null world draw the same ones)
        rngE = np.random.default_rng(23)
        news = np.ones((D, N))
        self.plan = []
        for k in range(N):
            if names[k].startswith("LOW"):
                continue
            t = int(self.first[k]) + int(rngE.integers(30, 60))
            while t < min(D - 62, int(self.last[k]) - 62):
                J = float(rngE.choice([-1.0, 1.0]) * rngE.uniform(0.03, 0.08))
                mult = float(rngE.choice([4.0, 7.0], p=[0.35, 0.65]))
                news[t, k] = mult
                r[t, k] += J
                if drift:
                    r[t + 2:t + 42, k] += drift * J / 40.0
                self.plan.append((t, k, mult, J))
                t += int(rngE.integers(18, 44))
        tf, ru = mech_days(dayidx)
        news[tf] *= 4.5
        news[ru] *= 6.0
        for nm, s in (("SPL", "2024-03-15"), ("S18", "2024-04-22"), ("S23", "2024-05-14")):         # a spike ON a flagged session: voided by the hygiene flag
            news[dx(s), ix(nm)] = 7.0
        self.daily, self.f5, self.opx = np.full((N, D, 5), np.nan), np.full((N, D, 5), np.nan), np.full((N, D), np.nan)
        prev = self.p0.copy()
        for d in range(D):
            o = (prev - divamt[d]) * np.exp(gap[d])
            c = o * np.exp(r[d] - gap[d])
            live = (d >= self.first) & (d <= self.last)
            h, lo = np.maximum(o, c) * (1.0 + w1[d]), np.minimum(o, c) * (1.0 - w2[d])
            v = np.round(self.vol * vn[d] * news[d]) + 1
            for q, a in enumerate((o, h, lo, c, v)):
                self.daily[:, d, q] = np.where(live, a, np.nan)
            prev = np.where(live, c, prev)
        self._valid = [np.flatnonzero(~np.isnan(self.daily[k, :, 0])) for k in range(N)]
        self._ts = [pd.Timestamp(d, tz="US/Eastern").tz_convert("UTC").strftime("%Y-%m-%dT%H:%M:%SZ") for d in self.days]


def smoke_releases(days, names, plan, seed=29):
    """the synthetic earnings calendar (ticker, ndx_tickers, reaction_session) from the plan: 80% of the events have a release on their session, 10% on the session before it, 10% none; 30% of the events also have a release some sessions later that carries no event; S05 is a RENAMED
    company (EDGAR's current ticker NEW05, members-file tickers OLD05;S05); a company no cached name matches (ZZZZ), a release before the walk-forward stretch, on the cut and after it, one in the lockbox"""
    rng = np.random.default_rng(seed)
    rows = []
    for t, k, _mult, _J in plan:
        sym = names[k]
        tk, nd = (f"NEW{sym[1:]}", f"OLD{sym[1:]};{sym}") if sym == "S05" else (sym, sym)
        u = rng.random()
        if u < SMOKE_RELEASE[0]:
            rows.append((tk, nd, f"{days[t]:%Y-%m-%d}"))
        elif u < SMOKE_RELEASE[0] + SMOKE_RELEASE[1]:
            rows.append((tk, nd, f"{days[t - 1]:%Y-%m-%d}"))
        if rng.random() < SMOKE_EXTRA and t + 25 < len(days):
            rows.append((tk, nd, f"{days[t + int(rng.integers(5, 25))]:%Y-%m-%d}"))
    rows += [("ZZZZ", "ZZZZ", f"{days[400]:%Y-%m-%d}"), ("S01", "S01", "2016-06-30"), ("S01", "S01", "2025-06-30"), ("S01", "S01", "2025-07-01"), ("S02", "S02", "2025-09-15")]
    return rows


@contextlib.contextmanager
def smoke_env(root, nrep=100, build=("plant", "null")):
    """everything the smoke patches, restored on exit: OUT and every module's output folder into `root`, CHECK_BOOK off, NREP = nrep, SPEC shrunk to the synthetic market, the wide calendar's pinned sha = the synthetic file's, the earnings calendar's path / sha / the members file,
    r5_siporb's transport = EdFake (one cache per world), the ES registry = the fake master, the TBIS file, a fake #463, a stub of RESMOM's line file as the registered one. Builds the worlds in `build` ('plant' = the continuation, 'null' = none) through r5_siporb's own pulls. Yields
    a namespace: root, days, esf, div, spin, split, fk {world: EdFake}, cache {world: folder}, switch(world), wide_sha, wide_csv, wide_manifest, ref_csv, ref_sha, cal_rows, cal_csv, cal_sha, members"""
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
        es.enter_context(spec(**SMOKE_SPEC))
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
            esf, mkt = DV.smoke_market(days)
            div, spin, split, _quarterly = DV.smoke_calendar(days)
            ca_rows = DV.smoke_ca_text(div, spin, split)
            env = SimpleNamespace(root=root, days=days, esf=esf, mkt=mkt, div=div, spin=spin, split=split, fk={}, cache={}, wide_files={}, ca_rows=ca_rows, rows_in_calendar=len(ca_rows))
            for world in build:
                fk = EdFake(days, mkt, div, drift=SMOKE_DRIFT if world == "plant" else 0.0)
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
            env.ref_sha = DV.write_ref_csv(env.ref_csv, b0, env.ref_res)
            assert inside(env.ref_csv), "the stub is inside the smoke dir"
            DV.REF_CSV, DV.REF_SHA = env.ref_csv, env.ref_sha
            with open(os.path.join(S.OUT, "siporb_cache_manifest.json"), "w") as f:
                json.dump({"manifest_sha256": D15.MANIFEST_PREFIX + "0" * 56, "files": 0}, f)
            with open(tbis_path, "w") as f:
                f.write("symbol,day,price_ratio,vol_ratio,split_like\nS18,2024-04-22,4.0,0.25,True\nSPL,2024-03-15,0.5,2.1,True\nS05,2024-02-13,0.5,1.0,False\nZZZZ,2024-02-14,0.5,2.0,True\nS07,2025-07-01,0.5,2.0,True\n")
            # [E5'] a synthetic earnings calendar from the plan (never TV's file), registered by its sha for this run; the Nasdaq-100 members file with two foreign filers the calendar holds no release of
            env.cal_rows = smoke_releases(days, env.fk[build[0]].names, env.fk[build[0]].plan)
            env.cal_csv = os.path.join(root, "edgar", "earnings_calendar_ndx.csv")
            os.makedirs(os.path.dirname(env.cal_csv))
            env.cal_sha = write_calendar(env.cal_csv, env.cal_rows)
            assert inside(env.cal_csv), "the stub calendar is inside the smoke dir"
            env.members = os.path.join(root, "edgar", "ndx_members.csv")
            tick = sorted({t for _tk, nd, _d in env.cal_rows for t in nd.split(";")})
            with open(env.members, "w") as f:
                f.write("ticker,from,to\n" + "".join(f"{t},2016-06-01,\n" for t in tick) + "FORX,2016-06-01,\nFORY,2018-01-01,2023-01-01\nFUTR,2025-07-01,\n")
            es.enter_context(patched(THIS, CAL_CSV=env.cal_csv, CAL_SHA=env.cal_sha, MEMBERS_CSV=env.members))

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
    """the World a stage reads, built through the REAL loaders with the calls stage_a makes (every input cut at 2025-06-30 at read time): (W, cal, winfo, tbis); the raw dividend / spin-off inputs are placed again by plain python from the csv rows (W.Dr_in / W.Sp_in) for the recounts"""
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


def dryload_text_checks(txt):
    """the dryload's printout is COUNTS: no price, return, reaction, score, P&L or statistic (nothing like a dollar amount, ROC, Sortino, P&L, a drawdown), no date on / after the cut but the one line that names the cut, the count lines it promises"""
    outcome = re.search(r"[$]\s*-?\d|ROC|Sortino|P&L|net [$]|drawdown|Stage A \(|reaction [+-]?\d|score [+-]?\d", txt)
    assert not outcome, ("the dryload printed an outcome", txt[max(outcome.start() - 80, 0):outcome.end() + 80])
    dates = [d for l in txt.splitlines() if "cut to dates <" not in l for d in re.findall(r"\b20\d\d-\d\d-\d\d\b", l)]
    assert dates and all(d < "2025-06-30" for d in dates), [d for d in dates if d >= "2025-06-30"][:5]
    for frag in ("universe size per session by year", "[E1] mechanical volume days are not news", "events by year of the event session", "scored names per rebalance", "registered (a flag inside the hold removes the name)", "look-ahead (names flagged inside the hold stay)", "[E5'] TV's EDGAR earnings calendar",
                 "TBIS flags:", "ES prints on the", "ES return (", "cache manifest sha256", "prereg check:", "rebalances:", "names with a full window", "the fallback rule"):
        assert frag in txt, frag


def smoke(*a):
    """python r19_edrift.py smoke DIR [stage_b]: offline, on SYNTHETIC worlds (nothing real is read or written; DIR is wiped and its name must contain 'smoke'). Order: the selftest on the real constants; the planted world through the real loaders against plain-python recounts of
    everything this file adds (events, pools, scores, picks, paths); the dryload (counts only); Stage A's refusal paths; Stage A on the NULL world (must FAIL: the same events and shocks, no continuation) and on the PLANTED world (the continuation must be found: (a)-(e) pass, (f) awaits
    the hand audit; [E3] / [E5'] print before any P&L); the hand audit (keep / data_event) and the recomputation; Stage B's refusal paths; with the argument stage_b also the one read of Stage B on the synthetic lockbox days, the verdict = the leg's veto alone, a second read refused,
    Stage A frozen"""
    root = os.path.abspath(a[0] if a else os.path.join(tempfile.gettempdir(), "edrift_smoke"))
    with_b = "stage_b" in a[1:]
    why = smoke_refusal(root)
    if why:
        raise SystemExit(why)
    selftest()                                                                             # the hand-made checks first, on the real constants (before anything below is patched)
    t_start = time.time()
    dates_of = lambda txt: re.findall(r"\b20\d\d-\d\d-\d\d\b", txt)
    with smoke_env(root) as env:
        sa_path, go, rd = os.path.join(OUT, "edrift_stageA.json"), os.path.join(OUT, GO_FLAG), os.path.join(OUT, READ_FLAG)
        plan = env.fk["plant"].plan
        print(f"synthetic market: {len(env.fk['plant'].names)} names x {len(env.days):,} business days ({env.days[0]:%Y-%m-%d} .. {env.days[-1]:%Y-%m-%d}); {len(plan):,} planted news sessions (4 x or 7 x volume, a shock of 3 .. 8% on the session), 4.5 x / 6 x volume on every third Friday / Russell day; "
              f"the PLANTED world continues {SMOKE_DRIFT:.0%} of each shock over the next 40 sessions (from t+2), the NULL world does not; both through r5_siporb's own pulls ({env.build_seconds:.0f}s); the earnings calendar: {len(env.cal_rows):,} rows, sha256 {env.cal_sha[:16]}...; "
              f"the wide calendar: {env.rows_in_calendar:,} rows; SPEC shrunk to {SMOKE_SPEC}")
        # ---- 1. the planted world through the REAL loaders: the cut, the planted data cases, the events and every pipeline step against plain-python recounts
        W, cal, winfo, tbis = smoke_world(env, "plant")
        di, ix = (lambda s: W.days.get_loc(TS(s))), list(W.syms)
        assert W.days.max() < S.LB0 and W.days[0] == TS("2015-11-02") and len(W.days) == len(pd.bdate_range("2015-11-02", "2025-06-27")) and len(tbis) == 4 and len(D15.load_tbis(S.END)) == 5, "nothing on / after the cut; TBIS's row on the lockbox day is cut at read time"
        spl, s18, s23, dl = (ix.index(n_) for n_ in ("SPL", "S18", "S23", "DLST"))
        assert W.chg[di("2024-03-15"), spl] and W.fl[1][di("2024-04-22"), s18] and not W.chg[:, s18].any() and W.fl[3][di("2024-05-14"), s23] and np.isfinite(W.Cl[di("2024-05-31"), dl]) and np.isnan(W.Cl[di("2024-06-03"), dl]), "the planted hygiene cases arrive through the loaders"
        assert np.isnan(W.es.ret[di("2024-03-05")]) and np.isnan(W.es.ret[di("2024-03-06")]), "the ES master has no print on 2024-03-05: no return that session and the next"
        check_russell(W.days)
        ev = attach_events(W)
        assert ev.tf.sum() == 39 and ev.ru.sum() == 10 and {W.days[i] for i in np.flatnonzero(ev.tf)} == brute_mech(W.days)[0] and {W.days[i] for i in np.flatnonzero(ev.ru)} == brute_mech(W.days)[1], (int(ev.tf.sum()), int(ev.ru.sum()))
        tf_, ru_ = brute_mech(W.days)
        sub = [ix.index(n_) for n_ in ("SPL", "S18", "S23", "DLST", "S33", "S34", "S01", "S02", "S05", "D01", "D17", "D40")]
        n_chk = 0
        for c in CELLS:                                                                    # the volume event rule on the real arrays, a dozen names x every session: valid events equal the plain-python classifier's
            for j in sub:
                got = set(np.flatnonzero(ev.EV[c][:, j]).tolist())
                want = {t for t in range(W.T) if brute_kind(W, c, t, j, tf_, ru_) == "valid"}
                assert got == want, (c, ix[j], sorted(got ^ want)[:5])
                n_chk += W.T
        for nm, s in (("SPL", "2024-03-15"), ("S18", "2024-04-22"), ("S23", "2024-05-14")):    # a spike ON a flagged session never survives
            assert not any(ev.EV[c][di(s) + d_, ix.index(nm)] for c in CELLS for d_ in (-1, 0, 1)), (nm, s)
        mech = ev.excl[np.flatnonzero(ev.tf | ev.ru)]
        assert mech.all() and not any(ev.EV[c][ev.excl].any() for c in CELLS), "no event on a mechanical day or the session after it"
        for c in CELLS:
            cn = ev.counts[c]
            assert sum(cn["excluded"].values()) > 150 and sum(cn["void_hygiene"].values()) >= 2 and sum(cn["valid"].values()) > 1000 and sum(cn["excluded_russell_day"].values()) >= 100 and sum(cn["excluded_third_friday"].values()) >= 300, (c, {k: sum(v.values()) for k, v in cn.items()})
        lo_, hi_ = TS("2023-06-01"), TS("2024-08-31")
        Bz_r, Bz_k = brute_ed(W, lo_, hi_, "remove"), brute_ed(W, lo_, hi_, "naive")
        Lr, Lk = ed_build(W, lo_, hi_, "remove"), ed_build(W, lo_, hi_, "naive")
        n_paths = compare_ed(W, Lr, Bz_r, "smoke remove") + compare_ed(W, Lk, Bz_k, "smoke naive")
        series_check(W, Lr, Bz_r)
        ntr = sum(r.traded for r in Lr.recs)
        assert ntr >= 12 and len(Lr.recs) == len(Bz_r) >= 12 and all(Lr.recs[q].cell["V3"].mode == "top" for q in range(len(Lr.recs))) and any(r.cell["V5"].n >= 45 for r in Lr.recs), (ntr, len(Lr.recs))
        flagged = [(ix.index(nm), di(s_)) for nm, s_ in (("SPL", "2024-03-15"), ("S18", "2024-04-22"), ("S23", "2024-05-14"))]
        n_hold = n_pre = 0
        for rr_, kk_ in zip(Lr.recs, Lk.recs):                                             # the registered reading removes a name flagged inside the hold, the look-ahead reading keeps it on its naive raw path; a flag in the pre-window (r-24 .. r) removes it from both
            assert rr_.r == kk_.r
            lo_pre = rr_.r - M17.SPEC["skip"] - M17.SPEC["hyg_lead"] + 1
            for j, d_ in flagged:
                if rr_.r + 1 <= d_ <= rr_.x:
                    assert j not in rr_.pool.tolist(), (ix[j], W.days[rr_.r])
                    if j in kk_.pool.tolist():
                        assert kk_.naive[kk_.pool.tolist().index(j)], (ix[j], W.days[kk_.r], "kept at its naive raw P&L")
                        n_hold += 1
                if lo_pre <= d_ <= rr_.r:
                    assert j not in rr_.pool.tolist() and j not in kk_.pool.tolist(), (ix[j], W.days[rr_.r], "a flag in the pre-window removes the name in both readings")
                    n_pre += 1
        assert n_hold >= 2 and n_pre >= 2, (n_hold, n_pre)
        print(f"planted cases ok through the real loaders (the cut at read, SPL / S18 / S23 / DLST, the ES hole, TBIS's lockbox row); against plain-python recounts: the event rule on {n_chk:,} name-sessions, {len(Bz_r)} rebalances in both readings "
              f"(every pool, beta, RES, event row, age, reaction, mode, pick and {n_paths:,} pick paths), the [E1] exclusions ({int(ev.tf.sum())} third Fridays, {int(ev.ru.sum())} Russell days)")
        Bz_c, Lc_ = brute_ed(W, lo_, hi_, "close"), ed_build(W, lo_, hi_, "close")                 # [HYG-S1] MANAGER's hygiene edit S1 on the same window: no in-hold removal, a [D2] ex-date closes the position at the close before it
        n_close_paths = compare_ed(W, Lc_, Bz_c, "smoke close")
        series_check(W, Lc_, Bz_c)
        n_flag_kept = sum(1 for rr_, cc_ in zip(Lr.recs, Lc_.recs) for j, d_ in flagged if rr_.r + 1 <= d_ <= rr_.x and j not in rr_.pool.tolist() and j in cc_.pool.tolist() and not cc_.naive[cc_.pool.tolist().index(j)])
        assert n_flag_kept >= 2, n_flag_kept
        print(f"[HYG-S1] the same {len(Bz_c)} rebalances under 'close' (MANAGER's hygiene edit S1): {sum(int((r_.close >= 0).sum()) for r_ in Lc_.recs)} pool names closed at the close before a spin-off / stock-dividend ex-date, {n_flag_kept} planted in-hold flags kept on the split-safe path, "
              f"every pool, close row and {n_close_paths:,} path recounted by plain python")
        B, legs = A13.load_463()
        rowsB = A13.book_rows(B, W)
        # ---- 2. the dryload: COUNTS only
        before = sorted(os.listdir(OUT))
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            dryload()
        td = buf.getvalue()
        assert sorted(os.listdir(OUT)) == before, "the dryload writes nothing"
        dryload_text_checks(td)
        evc = attach_events(W, counts_only=True)
        fb = io.StringIO()
        with contextlib.redirect_stdout(fb):
            print_events(evc)
        assert fb.getvalue() in td and evc.counts == ev.counts, "the dryload's [E1] / event counts are the full computation's"
        Lc = ed_build(W, WF0, PRE_END, "remove", units=False, counts_only=True)
        fc = io.StringIO()
        with contextlib.redirect_stdout(fc):
            print_scored_stats("registered (a flag inside the hold removes the name)", Lc, W)
        assert fc.getvalue() in td, "the dryload's scored-names-per-rebalance lines are the recount's"
        attach_events(W)
        assert re.search(rf"\[E5'\] TV's EDGAR earnings calendar earnings_calendar_ndx.csv sha256 {env.cal_sha[:16]}", td) and "unmatched companies (1" in td and "ZZZZ" in td and "FORX" in td and "FUTR" not in td, "[E5']'s match counts, the unmatched company and the foreign filer"
        with contextlib.redirect_stdout(io.StringIO()):
            attach_events(W)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), patched(THIS, CAL_SHA="0" * 64):
            dryload()
        assert "NOT the registered" in buf.getvalue() and "no match was counted" in buf.getvalue(), "the dryload reports another calendar and does not read it"
        dryload_text_checks(buf.getvalue())
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), patched(THIS, CAL_CSV=os.path.join(root, "edgar", "absent.csv")):
            dryload()
        assert "not on file" in buf.getvalue() and "no match was counted" in buf.getvalue()
        print("dryload ok on the synthetic world: counts only (no price, return, reaction, score, P&L or statistic), no lockbox date, nothing written, its [E1] / events / scored-names lines equal the recount; a missing / other earnings calendar is reported, not read")
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
        must("TV's EDGAR earnings calendar is not on file", CAL_CSV=os.path.join(root, "edgar", "absent.csv"))
        must("is not the registered one", CAL_SHA="0" * 64)
        must("do not reproduce", CHECK_BOOK=True)
        with patched(DV, REF_SHA="0" * 64):
            must("RESMOM line file")
        with patched(DV, REF_CSV=os.path.join(root, "resmom", "absent.csv")):
            must("is not on file - the REFERENCE book")
        must("no date for it", RUSSELL_DAYS=tuple(d_ for d_ in RUSSELL_DAYS if not d_.startswith("2024")))                  # the lead's Russell list must cover every June the data holds
        print("Stage A refuses (and writes nothing) on: a changed pre-registration, an unregistered wide calendar, an absent / other earnings calendar, a book that does not reproduce #463, a RESMOM line file that is absent / not the registered one, a Russell list that misses a June of the data")

        def run_stage_a(world):
            env.switch(world)
            b_ = io.StringIO()
            with contextlib.redirect_stdout(b_):
                o_ = stage_a()
            return o_, b_.getvalue()
        # ---- 4. Stage A on the NULL world: the same events and shocks without the continuation must FAIL
        t0 = time.time()
        out_n, txt_n = run_stage_a("null")
        cells_n = out_n["stageA"]["cells"]
        assert out_n["judged"] is True and out_n["stageA"]["pass_cells"] == [] and out_n["candidate"] is None and out_n["stageA"]["null"]["draws"] == NREP == 100 and out_n["stageA"]["placebo_null"]["draws"] == NREP, (out_n["stageA"]["pass_cells"], out_n["candidate"])
        assert "EDRIFT Stage A: FAIL - no cell passes (a)-(e)" in txt_n and "Stage A (a)-(e) pass" not in txt_n and all(d < "2025-06-30" for d in dates_of(txt_n)), "the null world fails and prints no lockbox date"
        assert all(not c["PASS"] and c["base"]["roc"] < RULES["roc"] for c in cells_n.values()) and not any(c["A2"]["incremental_pass"] for c in cells_n.values()), {k: c["base"]["roc"] for k, c in cells_n.items()}
        pn = out_n["reports"]["event_path"]["V3"]
        assert abs(pn["signed_cum_mean_bps"]) < 120.0 and pn["events"] > 500, pn["signed_cum_mean_bps"]
        os.remove(sa_path)
        print(f"Stage A on the NULL world ({time.time() - t0:.0f}s): FAIL as it must - the signed event path {pn['signed_cum_mean_bps']:+.1f} bps an event, WF ROC@30k "
              + ", ".join(f"{c} {cells_n[c]['base']['roc']:.1f}" for c in CELLS) + f"; null p95 {out_n['stageA']['null']['roc_max']['p95']:.1f}; the placebo null's p95 {out_n['stageA']['placebo_null']['roc_max']['p95']:.1f}")
        refused(stage_b, "go-flag")
        assert not os.path.exists(rd)
        # ---- 5. Stage A on the PLANTED world: the continuation must be found - (a)-(e) pass, (f) awaits the hand audit
        t0 = time.time()
        out, txt = run_stage_a("plant")
        cells = out["stageA"]["cells"]
        passing, cand = stage_a_flow(cells)
        assert out["judged"] is True and out["stageA"]["pass_cells"] == passing and len(passing) >= 1 and out["candidate"]["cell"] == cand and out["pending_hand_audit"] == passing, (passing, cand, {c: (cells[c]["base"]["roc"], [k for k, v in cells[c]["checks"].items() if not v]) for c in CELLS})
        assert cand == max(passing, key=lambda c: (cells[c]["base"]["roc"], -CELLS.index(c))) and out["candidate"]["also_passes"] == [c for c in passing if c != cand]
        for c in passing:
            assert f"Stage A (a)-(e) pass, (f) awaits the hand audit - cell {c}" in txt and all(cells[c]["checks"].values()), c
        assert "(f) AWAITS THE HAND AUDIT" in txt and "EDRIFT Stage A: (a)-(e) pass" in txt and "audit complete" not in txt.lower() and all(d < "2025-06-30" for d in dates_of(txt)), "the harness never decides (f); no lockbox date"
        assert out["prereg_sha256_lf"] == PREREG_SHA and {k: out.get(k) for k in stamp()} == stamp() and out["manifest_sha256"] == D15.MANIFEST_PREFIX + "0" * 56 and out["stageA"]["null"]["draws"] == NREP
        # [E3] and [E5'] print BEFORE any P&L; [E1] with them; the null's and the diagnostics' rows after
        i_e1, i_e3, i_e5 = txt.index("[E1] mechanical volume days are not news"), txt.index("[E3] BEFORE ANY P&L"), txt.index("[E5'] TV's EDGAR earnings calendar")
        i_pl = txt.index("the REGISTERED reading (a hygiene flag inside the hold removes the position)")           # the first line that carries a cell's P&L
        assert i_e1 < i_e3 < i_e5 < txt.index("registered reading done") < i_pl and txt.index("REFERENCE book [X1]") < i_e1, "[E1] / [E3] / [E5'] come before any cell statistic or P&L"
        outcome = re.search(r"[$]\s*-?\d|ROC|Sortino|net [$]|drawdown", txt[i_e1:i_pl])                           # (the [E3] header itself says BEFORE ANY P&L)
        assert not outcome, ("a P&L figure was printed before the registered reading's table", txt[max(i_e1 + outcome.start() - 80, 0):i_e1 + outcome.end() + 80])
        pth = out["reports"]["event_path"]["V3"]
        assert pth["signed_cum_mean_bps"] > 150.0 and pth["signed_cum_mean_bps"] - pn["signed_cum_mean_bps"] > 150.0 and pth["deciles"][10]["cum_bps"][-1] > 100.0 and pth["deciles"][1]["cum_bps"][-1] < -100.0, (pth["signed_cum_mean_bps"], pn["signed_cum_mean_bps"])
        print(f"Stage A on the PLANTED world ({time.time() - t0:.0f}s): the continuation is found - signed event path {pth['signed_cum_mean_bps']:+.0f} bps an event (the null world {pn['signed_cum_mean_bps']:+.0f}), top reaction decile {pth['deciles'][10]['cum_bps'][-1]:+.0f} / bottom {pth['deciles'][1]['cum_bps'][-1]:+.0f} bps by t+60; "
              + ", ".join(f"{c} ROC@30k {cells[c]['base']['roc']:.0f} ({cells[c]['base']['n_pos']:,} positions, {cells[c]['base']['n_units']} rebalances)" for c in CELLS) + f"; (a)-(e) pass for {passing}, candidate {cand}, (f) awaits the hand audit")
        # [E3] / [E5'] in the file, recounted from the planted world's own legs and calendar rows
        e3 = out["e3"]
        L0 = ed_build(W, WF0, PRE_END, "remove", units=False)
        e3_py = e3_report(W, L0)
        assert all(e3[c]["young"]["n"] == e3_py[c]["young"]["n"] and e3[c]["old"]["n"] == e3_py[c]["old"]["n"] and abs(e3[c]["young"]["mean_abs_score"] - e3_py[c]["young"]["mean_abs_score"]) < 1e-12 for c in CELLS) and e3["V3"]["young"]["n"] > 300, e3["V3"]["young"]
        exp_read = sum(1 for _tk, _nd, d_ in env.cal_rows if WF0 <= TS(d_) <= PRE_END and TS(d_) < S.LB0)
        e5 = out["e5"]
        assert e5["file"]["rows_on_file"] == len(env.cal_rows) and e5["file"]["rows_read"] == exp_read and e5["file"]["rows_not_read"] == len(env.cal_rows) - exp_read and e5["file"]["sha256"] == env.cal_sha
        assert e5["join"]["unmatched_companies"] == ["ZZZZ"] and e5["join"]["members_ticker_not_in_the_calendar"] == ["FORX", "FORY"] and e5["join"]["releases_matched"] == exp_read - 1, e5["join"]
        t5 = e5["shares"]["V3"]["total"]
        assert 0.8 < t5["share_events_on_a_release"] < 1.0 and 0.05 < t5["share_releases_without_an_event"] < 0.6 and t5["events"] > 1000, t5
        print(f"[E3] (V3: {e3['V3']['young']['n']:,} scored names aged 1-21 sessions, {e3['V3']['old']['n']:,} aged 22-63; rank correlation with RES {e3['V3']['rank_corr_with_RES']['mean']:+.3f}) and [E5'] ({exp_read:,} releases read, {t5['share_events_on_a_release']:.0%} of the events sit on a release, "
              f"{t5['share_releases_without_an_event']:.0%} of the releases carry no event) recounted and printed before any P&L")
        # every cell's WF numbers recomputed from fresh legs, the stress rows, the cost curve and A2 (against the reference, c by volatility on EDRIFT's own window)
        for cell in CELLS:
            Lw = ed_build(W, WF0, PRE_END, "remove")
            run_ = M17.run_cell(W, cell_leg(Lw, cell), D15.l1_cfg(), pos=True)
            st = stat_run(B, rowsB, run_)[0]
            got = cells[cell]["base"]
            assert st["n_pos"] == got["n_pos"] == out["parity"][cell]["n_pos"] and abs(st["net"] - got["net"]) < 1e-6 and abs(st["roc"] - got["roc"]) < 1e-9 and abs(st["max_dd"] - got["max_dd"]) < 1e-9, cell
            for b_, got_ in ((0.0, cells[cell]["cost0"]), (10.0, cells[cell]["stress"]["10 bps"]), (20.0, cells[cell]["stress"]["20 bps"])):
                want_ = stat_run(B, rowsB, M17.run_cell(W, cell_leg(Lw, cell), D15.l1_cfg(bps=b_)))[0]
                assert abs(got_["net"] - want_["net"]) < 1e-6 and abs(got_["roc"] - want_["roc"]) < 1e-9, (cell, b_)
            assert cells[cell]["cost0"]["net"] > got["net"] > cells[cell]["stress"]["10 bps"]["net"] > cells[cell]["stress"]["20 bps"]["net"]
            xb_ = D15.to_B(run_.x, rowsB, B.n)
            mw = B.mask(*A2_WIN)
            sb_, sc_ = float(np.std(B.raw[mw], ddof=1)), float(np.std(xb_[mw], ddof=1))
            a2 = cells[cell]["A2"]
            assert a2["window"] == ["2017-01-03", "2018-12-31"] and a2["rows"] == int(mw.sum()) and abs(a2["c"] - 0.25 * sb_ / sc_) <= 1e-9 * a2["c"] and a2["incremental_pass"] is bool(a2["roc"] > a2["reference"]["roc"] and a2["sortino"] > a2["reference"]["sortino"]), cell
        ref_ = DV.ref_load(B, check_facts=False)
        assert out["reference"]["sha256"] == env.ref_sha == out["reference"]["pinned_sha256"] and out["reference"]["rows"] == ref_.n_rows and "REFERENCE book [X1]" in txt and "DIAGNOSTICS [X2]" in txt and "EVENT-TIME PATH [X2] V3" in txt and "#70 gate basis [X1]" in txt
        ca2 = cells[cand]["A2"]
        assert out["candidate"] == {"cell": cand, "c": ca2["c"], "std_book": ca2["std_book"], "std_cell": ca2["std_cell"], "window": ["2017-01-03", "2018-12-31"], "a2_book_roc": ca2["roc"], "a2_reference_roc": ca2["reference"]["roc"],
                                    "incremental_pass": ca2["incremental_pass"], "book_shadow_line": ca2["book_shadow_line"], "also_passes": out["candidate"]["also_passes"]} and ca2["c"] > 0, "the frozen size travels with its two stds and the window"
        for key in ("sides", "extra", "sub", "gate70", "seat_ref", "episode_pnl"):
            assert all(key in cells[c] for c in CELLS), key
        pl = out["stageA"]["placebo_null"]
        assert set(pl["real_roc_percentile_by_cell"]) == set(CELLS) == set(pl["real_roc_above_p95_by_cell"]) == set(pl["info"]) and pl["draws"] == NREP and pl["seed"] == SEED_PLACEBO and all(pl["info"][c]["rebalances"] > 12 for c in CELLS), pl["info"]
        # the hygiene readings: the registered reading removed the planted cases inside a hold, the look-ahead reading kept them at their naive raw P&L, both readings are in the file
        hr, hk = out["hygiene_counts_by_year"]["registered"], out["hygiene_counts_by_year"]["look_ahead"]
        assert sum(v.get("post_split", 0) + v.get("post_gap", 0) + v.get("post_jump", 0) for v in hr.values()) >= 2 and sum(v.get("kept_naive", 0) for v in hk.values()) >= 2 and sum(v.get("kept_naive", 0) for v in hr.values()) == 0, (hr[2024], hk[2024])
        assert set(out["kept_naive_reading"]["flips"]) == set(CELLS) and out["kept_naive_reading"]["null"]["draws"] == NREP and out["no_dividend_reading"]["null"]["draws"] == NREP and out["without_first_five_reading"]["null"]["draws"] == NREP
        assert all(c_["base"]["net"] != cells[c]["base"]["net"] for c, c_ in out["no_dividend_reading"]["cells"].items()), "the cash dividends move the P&L"
        cd = pd.read_csv(os.path.join(OUT, "edrift_audit_candidates.csv"))
        assert {"symbol", "date", "exit", "side", "pnl", "score", "rank_date", "event", "event_age", "event_volume_multiple", "reaction", "beta", "raw_move_event_window", "adj_move_event_window", "factor_ratio_window_to_exit", "tbis_price_ratio", "asset_status", "flags_in_window"} <= set(cd.columns), list(cd.columns)
        assert set(cd["cell"]) == set(CELLS) and cd.groupby("cell").size().max() == AUDIT_N and cd["exit"].max() < "2025-06-30" and cd["event"].max() < "2025-06-30" and cd["rank_date"].max() < "2025-06-30"
        for cell, g in cd.groupby("cell"):
            assert (g["pnl"].diff().dropna() <= 1e-9).all() and abs(g["pnl"].iloc[0] - float(M17.run_cell(W, cell_leg(ed_build(W, WF0, PRE_END, "remove"), cell), D15.l1_cfg(), pos=True).pos.pnl.max())) < 1e-6, "largest gains first; the first is the cell's largest"
        pm = peak_mb()
        print(f"audit candidates: the {AUDIT_N} largest gains per cell with their event, age, volume multiple and reaction -> edrift_audit_candidates.csv" + (f"; peak memory {pm:,.0f} MB" if pm else ""))
        # ---- 6. the hand audit: every listed contributor 'keep' -> the same numbers, the audit counted; a data_event on the candidate's largest gain -> out of both cells and the nulls
        ap = os.path.join(OUT, "edrift_audit.csv")
        pd.DataFrame({"symbol": cd["symbol"], "date": cd["date"], "cell": cd["cell"], "verdict": "keep", "note": "smoke: nothing found"}).to_csv(ap, index=False)
        out2, txt2 = run_stage_a("plant")
        assert out2["audit"]["rows"] == len(cd) and out2["audit"]["keep"] == len(cd) and out2["audit"]["data_event"] == 0 and out2["audit_sha256"] == file_sha(ap) != out["audit_sha256"] and all(v["audited"] == v["listed"] == AUDIT_N for v in out2["audit_status"].values())
        assert out2["stageA"]["pass_cells"] == passing and out2["candidate"] == out["candidate"] and all(out2["stageA"]["cells"][c]["base"][k] == cells[c]["base"][k] for c in CELLS for k in ("n_pos", "net", "roc", "max_dd", "sortino")), "a keep changes no number"
        top = cd[cd["cell"] == cand].iloc[0]
        au = pd.read_csv(ap)
        au.loc[(au["symbol"] == top["symbol"]) & (au["date"] == top["date"]), "verdict"] = "data_event"
        au.to_csv(ap, index=False)
        out3, txt3 = run_stage_a("plant")
        cd3 = pd.read_csv(os.path.join(OUT, "edrift_audit_candidates.csv"))
        assert out3["audit"]["data_event"] >= 1 and not ((cd3["symbol"] == top["symbol"]) & (cd3["date"] == top["date"])).any() and out3["audit_sha256"] != out2["audit_sha256"], "the name-month is gone from every list"
        n3 = out3["stageA"]["cells"][cand]["base"]
        assert n3["net"] != cells[cand]["base"]["net"] and n3["n_pos"] == cells[cand]["base"]["n_pos"] and out3["parity"][cand]["n_pos"] == n3["n_pos"], "the slot goes to the next name in the order: the same number of positions, another P&L"
        assert out3["stageA"]["null"]["draws"] == NREP and out3["stageA"]["null"]["roc_max"]["p95"] != out2["stageA"]["null"]["roc_max"]["p95"] and out3["stageA"]["placebo_null"]["roc_max"]["p95"] != out2["stageA"]["placebo_null"]["roc_max"]["p95"], "the name-month is out of both nulls too"
        print(f"hand audit: all {len(cd)} listed rows 'keep' -> the same numbers, audit counted {AUDIT_N}/{AUDIT_N} on every list; a data_event on {top['symbol']} {top['date']} ({cand}'s largest gain, ${top['pnl']:,.0f}) -> out of both cells and both nulls "
              f"(the slot goes to the next name: {n3['n_pos']:,} positions either way): {cand} net ${cells[cand]['base']['net']:,.0f} -> ${n3['net']:,.0f}, null p95 {out2['stageA']['null']['roc_max']['p95']:.2f} -> {out3['stageA']['null']['roc_max']['p95']:.2f}")
        out, cells = out3, out3["stageA"]["cells"]
        passing, cand = stage_a_flow(cells)
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
        for k in ("harness_sha256", "r17_sha256", "r18_sha256", "r15_sha256", "r13_sha256", "wide_ca_sha256", "earnings_calendar_sha256"):
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
        for edit in (lambda j: j.update(judged=False), lambda j: j.update(candidate=None), lambda j: j["stageA"].update(pass_cells=[]), lambda j: j["stageA"].update(pass_cells=[c for c in CELLS if c != j["candidate"]["cell"]])):
            j = json.loads(js0)
            edit(j)
            open(sa_path, "w").write(json.dumps(j))
            must_b("no Stage A candidate")
        for badc in (0.0, -1.0, float("nan"), None):
            j = json.loads(js0)
            j["candidate"]["c"] = badc
            open(sa_path, "w").write(json.dumps(j))
            must_b("positive number")
        open(sa_path, "w").write(js0)
        must_b("DIFFERS", PREREG_SHA="0" * 64)
        with patched(M17, WIDE_CA_SHA="0" * 64):
            must_b("different harness version")                                           # the pinned calendar is in Stage A's stamp: another pinned sha stops it at the stamp
        with patched(THIS, CAL_SHA="0" * 64):
            must_b("different harness version")                                           # so is the pinned earnings calendar
        au0 = open(ap).read()
        open(ap, "a").write("ZZZ,2016-11-01,V3,keep,a changed audit file\n")
        must_b("not the file Stage A ran with")
        open(ap, "w").write(au0)
        must_b("do not reproduce its LB numbers", CHECK_BOOK=True)                        # the book's LB numbers (the synthetic one cannot reproduce them)
        okbk = lambda B_, lo_, hi_, ref: {"roc": 0.0, "sortino": 0.0, "ref": list(ref), "ok": True}
        with patched(A13, book_check=okbk):
            must_b("not the one Stage A ran on", CHECK_BOOK=True, manifest_sha=lambda: "ffffffff" + "0" * 56)
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
        must_b("volatility-set size c")                                                    # the frozen size is recomputed from 2017-01-03 .. 2018-12-31 on Stage B's data: a drift of 1 in 10,000 stops it
        open(sa_path, "w").write(js0)
        with patched(THIS, RUSSELL_DAYS=RUSSELL_DAYS[:-1]):
            must_b("different harness version")
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
            sb = json.load(open(os.path.join(OUT, "edrift_stageB.json")))
            assert os.path.exists(rd) and sb["pass"] == ok and sb["cell"] == cand and sb["c"] == c_frozen and sb["leg"]["n_pos"] > 0 and {k: sb.get(k) for k in stamp()} == stamp() and sb["prereg_sha256_lf"] == PREREG_SHA
            assert set(sb["checks"]) == {f"leg monthly rebalances>={RULES['b_reb']}", "leg net>0", "leg net>0 without its top name-month"} and ok is all(sb["checks"].values()), "the pass is the LEG's veto: three checks, no book"
            assert sb["es_return_lb"]["stretch"] == ["2025-06-30", "2026-06-30"] and sb["go_flag"].startswith("smoke: the lead's go-flag")
            add, mb_ = sb["book_add_reported"], B.mask(LB0, LB1)                           # the book add on the lockbox at the FROZEN c: reported, recomputed from the book file and the captured series
            want = R11.stats((B.raw + c_frozen * cap["x"])[mb_], B.index[mb_])
            assert add["c"] == c_frozen and abs(add["roc"] - want["roc"]) < 1e-9 and abs(add["sortino"] - want["sort"]) < 1e-9 and abs(add["net"] - want["net"]) < 1e-6, add
            assert add["reference"] == {"roc": RULES["b_roc"], "sortino": RULES["b_sort"]} and add["would_have_cleared"] is bool(want["roc"] >= RULES["b_roc"] and want["sort"] >= RULES["b_sort"]) and "never a pass" in add["note"]
            assert "book add, REPORTED and never part of the pass" in txt_b and ("PASS - the leg survives" in txt_b) is ok and ("FAIL - the leg is vetoed" in txt_b) is not ok

            def reread(leg_ok, book_ok):                                                    # the pass is the leg's veto ALONE: the leg forced to pass with the book add's bar forced to miss, then the leg forced to fail with the bar forced to clear
                os.remove(rd)
                os.remove(os.path.join(OUT, "edrift_stageB.json"))

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
                return ok_, json.load(open(os.path.join(OUT, "edrift_stageB.json"))), b_.getvalue()
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


# ------------------------------------------------------------------ the commands
TESTS = ("t_constants", "t_mech", "t_events", "t_reaction", "t_sides", "t_pipeline", "t_close", "t_nulls", "t_e3", "t_e5", "t_path", "t_reference", "t_yardstick", "t_judge", "t_files", "t_integration", "t_stage_b_refusals", "t_cut")


def selftest():
    """hand-made worlds and calendars, no files, no data, no network: every group of tests prints one line, the last line says how many ran"""
    t0 = time.time()
    with tempfile.TemporaryDirectory() as td, patched(THIS, OUT=os.path.join(td, "out"), CAL_CSV=os.path.join(td, "no_such_dir", "earnings_calendar_ndx.csv")), patched(DV, REF_CSV=os.path.join(td, "no_such_dir", "resmom_cells_daily_wf.csv")):
        for name in TESTS:                                       # the real calendar / RESMOM line file / OUT are never read or written by a test: a read that is not stubbed lands in the temp dir and refuses
            t1 = time.time()
            globals()[name]()
            print(f"  {name} ok ({time.time() - t1:.1f}s)", flush=True)
    print(f"selftest ok: {len(TESTS)} groups ({', '.join(t[2:] for t in TESTS)}) in {time.time() - t0:.0f}s")


def main(argv):
    cmd, args = (argv[0], argv[1:]) if argv else ("", [])
    fn = {"selftest": selftest, "smoke": smoke, "dryload": dryload, "stage_a": stage_a, "stage_b": stage_b}.get(cmd)
    if fn is None:
        print("usage: r19_edrift.py selftest | smoke DIR [stage_b] | dryload | stage_a | stage_b   (dryload: counts only; stage_a after the registered pre-registration is committed; stage_b only on the stock families' one sealed-year day, "
              "with the lead's edrift_stageB_GO.flag on file)")
        return
    if cmd in ("stage_a", "stage_b"):
        os.makedirs(OUT, exist_ok=True)
    fn(*args)


if __name__ == "__main__":
    main(sys.argv[1:])
