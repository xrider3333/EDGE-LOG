# NETISS r1 - NET SHARE ISSUANCE in US large caps, rebalanced MONTHLY, dollar-neutral: cells N12 (ISS_1 = ln of the change in SPLIT-ADJUSTED shares outstanding over one year) and N24 (two years); at each month-end rank close
# long the 50 LOWEST ISS (the biggest shrinkers), short the 50 HIGHEST (the biggest issuers). The share counts are read from SEC XBRL facts AS FILED (the first filed date of every value, known at filed + 1 session), the split factor is the SIPORB cache's.
# A leg for BOOK #463 that must clear the STANDALONE bars (MANAGER #56) and is reported INCREMENTALLY over the RESMOM reference book #463 + 0.264 x RES. Pre-registered: tools/rocfrontier/PREREG_NETISS_R1.txt (canonical LF sha256 f2f69cd9...910ab = DRAFT v1 +
# PRE-DATA ADDENDUM 1 ([A1]-[A7]: the pinned bulk extract and map, known at filed + 1 session, splits cross-checked with the calendar, foreign filers out, deciles, the |beta| <= 0.20 credit rule + ES-hedged twin, the Daniel-Titman composite twin) + ADDENDUM 2 ([A8]-[A12]: TV's
# reviewed map / share-count additions read as ONE table, the two-way split check, the |ISS| > ln(1.5) audit flag, the ADR / IFRS / mid-window prints, dollars a year + the reference's episode table) + ADDENDUM 3 ([A13]-[A17]: ONE SHARE CLASS PER FIRM - at every rank, among the pool names with a score,
# only the class with the larger mean raw dollar volume of the 20 sessions before the fill keeps its score; the hand audit's scope - the 50 largest contributors and every PICKED [A10]-flagged name-rank, grouped by (symbol, the two facts' accession numbers); the readings this file chose, adopted as
# registered; the first ranks as found; Stage B's share facts from the same photographed zip)). Every rule, threshold, window and cost below is that file; where it is silent the choice is marked CHOICE.
# NETISS is RESMOM r1's sibling in the same lane on the same data: r17_resmom.py is imported, never copied and never edited (its loaders, the pinned wide calendar, the dividend / spin-off arrays, the monthly schedule, fills / holds / costs / borrow, the cell engine, the statistics, the hygiene
# windows, the audit rows, the refusals) and r18_divrun.py is imported for the REFERENCE book (ref_load / ref_build / ref_at / incremental_pass / a2_report), the null statistics and the shared helpers. NETISS's SCORE replaces RESMOM's; everything after the score is RESMOM's code path.
# What this file adds is the FILINGS logic: the pinned XBRL tables read as one, the first-filed rule, the point-in-time S(r) / S' search, the split cross-check, the ISS, [A13]'s one share class per firm, the 150 / thirds / 20-a-side fallback, the deciles, the composite twin, the ES-hedged twin,
# the hand audit's rows grouped by their two filings [A14], and the reports.
#   python r21_netiss.py selftest    hand-made worlds + hand-made filings, no data: the first-filed rule, the +1 session rule, the same-concept rule and the concept fallback, the +-35-day S' search, a split cancelling through F, [A3] both ways, the ln(10) / ln(1.5) rules, the foreign-filer
#                                    exclusion, the one-table merge, [A13]'s second share class (the more liquid class is scored, the other counted and never picked, drawn or cut into deciles; a volume tie goes to the lower symbol), [A14]'s audit groups, the 150 / thirds / 20 fallback,
#                                    the null, the deciles, the composite twin, the hedge, dollars a year, the refusals (the wrong sha of every pinned file), every pool / score / pick / path against a plain-python recount
#   python r21_netiss.py smoke DIR   offline end-to-end on SYNTHETIC worlds (r5_siporb's fake Alpaca, a fake ES master, a fake #463, a fake RESMOM line file, fake XBRL tables + maps, a fake TBIS file, a fake wide calendar): a world with a planted issuance effect that Stage A must find and a world
#                                    without one where it must not; DIR's name must contain 'smoke'; every command except Stage B's read runs
#   python r21_netiss.py dryload     WF inputs only (every input cut to dates < 2025-06-30): prints COUNTS - mapped / unmapped names by reason, scored names per rank and cell by year, every no-score reason by year (the [A13] second share classes with them, per rank and by year, and the CIKs
#                                    they fire on), the concept split, the [A10] flag count, the fallback months - never an ISS value, return or P&L
#   python r21_netiss.py stage_a     WF Stage A + the [A1]-[A13] prints FIRST + the nulls + A2 (INCREMENTAL over the reference, [A6]'s beta credit rule) + the reports + the diagnostics -> netiss_stageA.json (+ netiss_audit_candidates.csv, netiss_a10_flags.csv with the picked
#                                    cell / side and the group of every flagged name-rank [A14]), PRE-LOCKBOX ONLY
#   python r21_netiss.py stage_b     Stage B (lockbox, ONCE): refuses unless the lead's flag file netiss_stageB_GO.flag is on file (and a Stage A candidate that passed (a)-(e)); the pass is the LEG's veto, the book add is only reported
# Reads (never writes) the SIPORB cache through r5_siporb, the ES 5m RTH masters through augur_engine.data, the #463 book through r11_risk, the sha-pinned wide corporate-actions calendar, RESMOM's sha-pinned WF line file (the reference) and the four sha-pinned XBRL / map files, every one cut at read.
# Results go to OUT (outside git). Nothing here pulls, commits, pushes or writes anywhere else, and nothing here makes a network call.
import bisect, contextlib, io, json, math, os, re, shutil, sys, tempfile, time
from collections import Counter, defaultdict
from types import SimpleNamespace
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import numpy as np, pandas as pd
import r17_resmom as M17            # the sibling harness (RESMOM r1): its loaders, calendar, arrays, schedule, engine, statistics, A2 and audit rows are called wherever they fit
import r18_divrun as DV             # the sibling harness (DIVRUN r1): the REFERENCE book [X1], the incremental A2, the null statistics, the generic diagnostics, the synthetic market of the smoke
D15, S, R11, M12, A13 = M17.D15, M17.S, M17.R11, M17.M12, M17.A13       # r15_ddw (World, cell statistics, seat, null engine), r5_siporb, r11_risk, r12_mdl, r13_attn - through r17's own imports
from augur_engine.drawdowns import dd5 as _dd5                         # noqa: E402  [A19] the owner's DD5 (MANAGER #120; the repo root is on the path through r11_risk)
# [A21] THE REFERENCE IS THE RESTATED L (MANAGER #116: once the RESMOM restatement landed - ledger 2.93, 2026-10-07 - it replaces the registered L everywhere): r18_divrun's loader reads the restated line file (the
# same columns, #463's WF index row for row) and refuses unless its sha256 and its WF numbers are these. Set at import so NETISS and SHORTINT (which imports this file) read the same L; the selftests and the smokes
# still point the loader at their stubs. r18_divrun itself (DIVRUN r1, closed) keeps the registered file.
DV.REF_CSV = DV.REF_CSV_PINNED = r"C:\EdgeLog\_anatomy_cache\rocfrontier\resmom_r1\resmom_cells_daily_wf_keep.csv"
DV.REF_SHA = "86721fda625ce24eeae6735f58b2247a2043693bcacb8ede9290f8ce6f6de3e6"
DV.REF_FACTS = {"roc": 120.95, "sortino": 3.921, "max_dd": 36526.0}

TS = pd.Timestamp
THIS = sys.modules[__name__]
OUT_DEFAULT = r"C:\EdgeLog\_anatomy_cache\rocfrontier\netiss_r1"
OUT = os.environ.get("EDGELOG_NETISS_R1", OUT_DEFAULT)                                                    # results, outside git
PREREG = os.path.join(HERE, "PREREG_NETISS_R1.txt")
PREREG_SHA = "cd52f51189da546d73d87b842488d56027fecba961173d5c6984f0383f7b1f38"                      # canonical (LF) sha256 of the pre-registration: DRAFT v1 + PRE-DATA ADDENDA 1-3 + POST-DATA BUG FIX ADDENDUM 4 ([A18] the judged reading keeps in-hold flags, [A19] DD5, [A20] caveats, [A21] the restated L); supersedes f2f69cd9 (draft + addenda 1-3)
WF0, PRE_END, LB0, LB1 = M17.WF0, M17.PRE_END, M17.LB0, M17.LB1          # WF = positions EXITED 2016-07-01 .. 2025-06-29; LB = exits 2025-06-30 .. 2026-06-30 INCLUSIVE; cuts: S.LB0 / S.END
BOOK_WF, BOOK_LB, DEEPEST_WF = M17.BOOK_WF, M17.BOOK_LB, M17.DEEPEST_WF
NREP, SEED = 500, 20261008                                               # the registered null: 500 draws of random names from each rebalance's eligible SCORED pool
CELLS = ("N12", "N24")                                                   # the family: 2 cells
KS = {"N12": 1, "N24": 2}                                                # the horizon in years: ISS_k compares S(r) with the value about k years before its as-of date
YEARS = D15.YEARS                                                        # the nine July-June WF years 2016-17 .. 2024-25 (2016-17 is short - it counts as a year)
SUBPERIODS = DV.SUBPERIODS                                               # [X2] the regime halves 2016-07-01 .. 2021-12-31 and 2022-01-01 .. 2025-06-29
A2_WINS = {"N12": (TS("2017-02-01"), TS("2019-01-31")), "N24": (TS("2018-02-01"), TS("2020-01-31"))}     # A2 (a REPORT): c by volatility on the cell's first two FULLY COVERED years (the prereg's own dates - they stay, [A16]: their first month holds no position), 25% of #463's daily std / the cell's
A2_TARGET, A2_REPORT = M17.A2_TARGET, M17.A2_REPORT                      # 25% of #463's std; the book at 0.5c and 2c is reported
COST_BPS, STRESS_BPS, BORROW, BORROW_STRESS = M17.COST_BPS, M17.STRESS_BPS, M17.BORROW, M17.BORROW_STRESS     # 5 bps a side (stress 10, 20); 0.25% a year on short notional (stress 1% and 3% on k_t > 1.5 sessions)
AUDIT_N = 50                                                             # (f) the largest single-name contributors audited by hand
LN10, LN15 = math.log(10.0), math.log(1.5)                               # the exclusion (a unit / scale error or a merger) and the audit flag [A10]
BAND_DAYS = 35                                                           # S' = the usable value whose as-of date is closest to a - k years, inside +-35 days
SPLIT_TOL, SPLIT_NEAR = 0.01, 3                                          # [A3] an F change above 1%, matched with a calendar split within +-3 sessions (both ways)
STALE_DAYS = 60                                                          # the staleness print: the share of S(r) values first filed in the last 60 days before r
BETA_CAP = 0.20                                                          # [A6] a cell with |realised beta| above it (per $ of one side's notional) is never credited
CACHE_FIRST_SESSION = TS("2016-01-04")                                   # the cache's first session: no split history is held before it (a real run asserts the World starts here)
CONCEPTS = ("dei:EntityCommonStockSharesOutstanding", "us-gaap:CommonStockSharesOutstanding")      # the concept order: the cover page first, else the balance sheet
WA_CONCEPT = "us-gaap:WeightedAverageNumberOfSharesOutstandingBasic"     # a reported cross-check only
CONCEPT_KEY = ("dei", "gaap")
CONCEPT_LABEL = {"dei": "cover page (dei)", "gaap": "balance sheet (us-gaap)"}
FOREIGN_FORMS = ("20-F", "20-F/A", "40-F", "40-F/A", "6-K", "6-K/A")     # [A4] a CIK whose share facts come ONLY from these forms is a foreign filer
ALLOWED_METHODS = ("current_ticker", "name_exact")                       # [A1] the base map's usable rows: the current-ticker rows that passed TV's name check and the exact former-name rows
ADD_METHODS = ("reviewed_same_firm",)                                    # [A8] TV's reviewed additions
MAP_COLS = ("symbol", "cik", "method")
FACT_COLS = ("cik", "symbols", "concept", "unit", "val", "start", "end", "accn", "form", "filed")      # the flat file's columns this harness reads (fy, fp, frame are not)
XBRL_DIR = os.environ.get("EDGELOG_XBRL_DIR", r"C:\EdgeLog\_research_cache\xbrl_companyfacts")
EDGAR_DIR = os.environ.get("EDGELOG_EDGAR_DIR", r"C:\EdgeLog\_research_cache\edgar")
FILES = {"facts": os.path.join(XBRL_DIR, "shares_asfiled_wide.csv"), "facts_add": os.path.join(XBRL_DIR, "shares_asfiled_additions_reviewed.csv"),
         "map": os.path.join(EDGAR_DIR, "symbol_cik_map_wide_symbols_siporb_floor_2016_2025.csv"), "map_add": os.path.join(EDGAR_DIR, "symbol_cik_map_wide_additions_reviewed.csv")}
FILE_SHA = {"facts": "02387a4f1140c41872a7b46cf6b9657abec90ef90d09a0a2ee47ff882c2f4433", "facts_add": "d10626d8694b180dae991c9d83502c27352b285e46b1e84c9d29b610958f2871",
            "map": "19adc9badc8e9c2b999d818c9aa4b78f257835e19eacd418cdf55c0fc93f1909", "map_add": "6bf8dfabc0a945bcf6c30f1d6bca201703d8a67d1e8f48daccfba4c6ca23c866"}
FILE_LABEL = {"facts": "share-count flat file (shares_asfiled_wide.csv)", "facts_add": "reviewed share-count additions", "map": "symbol -> CIK map", "map_add": "reviewed map additions"}
LB_FACTS = None          # [A17] Stage B: the lockbox year's share facts (filed 2025-06-30 .. 2026-06-30) are NOT in the pinned files (they stop at filed 2025-06-27): they come from the SAME photographed zip (db35d36b), extracted by TV with the same tool, only after a Stage A pass, and a dated addendum pins that second extract by sha256 here before Stage B can read one fact; None = Stage B refuses
CHECK_BOOK = True        # refuse to judge if the #463 records / the DD structure / the cache manifest / the reference / the cache's first session do not reproduce the registered facts; a real run always checks (only smoke() may switch it)
HYG = M17.HYG            # the four data-hygiene reasons [T2]
AUD = M17.AUD            # the tag of this harness's rows in World.aud_hit (r17_resmom's: its unused_audit_rows reads it)
JUDGED = "keep"          # [A18] POST-DATA BUG FIX (2026-10-07; MANAGER #116 / #118 / #119, TTM #117): the judged reading and its null keep a name flagged INSIDE the hold, on the split-safe path; only an announced (calendar) split or a [D2] ex-date inside the hold removes it. 'remove' (the leaky reading Stage A first ran on 2026-10-06) is REPORTED, null-less
LAB_J = "judged (names flagged inside the hold stay, on the split-safe path; only an announced split or a [D2] ex-date inside the hold removes a name) [A18]"
LAB_R = "the leaky 'remove' reading (a flag inside the hold removed the name before the ranking; REPORTED, never the verdict) [A18]"
GO_FLAG, READ_FLAG = "netiss_stageB_GO.flag", "netiss_stageB_READ.flag"     # Stage B needs the lead's go-flag; the one-shot read flag is written (exclusively) after every load and check
RULES = M17.RULES        # Stage A (a) - (e) and Stage B's leg veto are r17_resmom's own (the booleans are switches only smoke() ever turns off)
SPEC = {"min_scored": 150, "min_side": 20,          # fewer than 150 scored names: the bottom / top THIRD, at least 20 a side, else nothing (counted)
        "dec_n": 10, "dec_min": 10,                 # [A5] ten equal-count deciles; a rank with fewer than 10 scored names has none (counted)
        "hedge_win": 252, "hedge_min": 230}         # [A6] the ES hedge ratio: OLS (with an intercept) of the cell's own daily P&L on ES over the 252 sessions before the rank, >= 230 pairs, zero before 252 sessions of the cell's own exist
R_SCORED, R_NOT_IN_MAP, R_MAP_MISMATCH, R_MAP_AMBIGUOUS, R_MAP_UNMAPPED, R_MAP_NONCOMMON, R_MAP_OTHER, R_NO_FACTS, R_FOREIGN, R_NO_FACT, R_NO_BAND, R_NOT_POS, R_BEFORE_CACHE, R_NO_FACTOR, R_ISS10, R_SPLIT_C, R_SPLIT_F, R_SECOND_CLASS = range(18)
REASONS = ("scored", "not_in_map", "map_mismatch", "map_ambiguous", "map_unmapped", "map_non_common", "map_other", "no_facts_for_cik", "foreign_filer", "no_usable_fact", "no_band_pair", "value_not_positive", "a_prime_before_cache",
           "no_split_factor", "iss_over_ln10", "split_calendar_not_in_F", "split_F_not_in_calendar", "second_share_class")      # the last is [A13]'s and POOL-level: score_rank never assigns it (a name is a second class only among the pool names that have a score), ni_one counts it
REASON_TEXT = {"scored": "scored", "not_in_map": "symbol not in the map", "map_mismatch": "map: current ticker, name does not agree", "map_ambiguous": "map: name ambiguous", "map_unmapped": "map: unmapped", "map_non_common": "map: debenture / preferred / unit",
               "map_other": "map: another method", "no_facts_for_cik": "CIK with no share fact", "foreign_filer": "[A4] foreign filer (20-F / 40-F / 6-K only)", "no_usable_fact": "[A4] no usable fact at the rank",
               "no_band_pair": "no S' inside the +-35-day band", "value_not_positive": "a value not positive", "a_prime_before_cache": "a' before the cache's first session", "no_split_factor": "no split factor on an as-of date",
               "iss_over_ln10": "|ISS| > ln(10)", "split_calendar_not_in_F": "[A3] a calendar split F does not show", "split_F_not_in_calendar": "[A3] an F change the calendar does not show",
               "second_share_class": "[A13] second share class of a CIK (the other class has the larger dollar volume)"}
MAP_REASON = {"current_ticker_name_mismatch": R_MAP_MISMATCH, "name_ambiguous": R_MAP_AMBIGUOUS, "unmapped": R_MAP_UNMAPPED, "non_common": R_MAP_NONCOMMON}
DAY0 = int(np.datetime64("1900-01-01").astype(np.int64))                  # day numbers are days since 1970-01-01; DAY0 shifts them positive for the composite sort key
KEYMUL = 10 ** 6
TAIL = "(nothing computed, lockbox NOT read)"


# ------------------------------------------------------------------ guards: the prereg, the stamp, the cut, the files
def refuse(msg):
    raise SystemExit(msg)


assert_cut, peak_mb, patched, ceil_pct = A13.assert_cut, A13.peak_mb, A13.patched, A13.ceil_pct
file_sha, manifest_sha, book_checks = M17.file_sha, M17.manifest_sha, M17.book_checks      # module-level names, so a test can stub them


def prereg_ok():
    """the frozen spec this file implements must still be the registered one (a changed spec = a new file, r2): a missing or changed file refuses every stage. Also checked against the committed blob when there is one
    (r15_ddw.committed_state, pointed at this file's names for the call); until it is committed that is printed (the lead commits before the real run) and recorded in the Stage A file"""
    if not os.path.exists(PREREG):
        refuse("refused: PREREG_NETISS_R1.txt is not next to this file - the spec cannot be verified (nothing computed, lockbox NOT read)")
    if R11.sha_lf(PREREG) != PREREG_SHA:
        refuse("refused: PREREG_NETISS_R1.txt DIFFERS from the registered one - a changed spec is a new file, r2 (nothing computed, lockbox NOT read)")
    with patched(D15, PREREG=PREREG, PREREG_SHA=PREREG_SHA):
        st = D15.committed_state()
    if st == "differs":
        refuse("refused: the COMMITTED PREREG_NETISS_R1.txt differs from the registered sha - the file on disk is not the file in git (nothing computed, lockbox NOT read)")
    print("prereg check: PREREG_NETISS_R1.txt sha256 matches the registered one; committed blob: " + {"match": "matches too", "untracked": "NOT COMMITTED YET - commit it before the real run",
                                                                                                    "unknown": "git not available here (not checked)"}[st])
    return {"verified": True, "committed": st}


def stamp():
    """the version a stage ran with: this file's LF sha256 + r17_resmom's and r18_divrun's + every harness they import numbers from (r15's data layer / marks / statistics, r5_siporb's Data / read_long, r11's book and stats, r12's DO / rho_dd, r13's helpers) + the pinned wide
    calendar's sha + the four pinned XBRL / map files' shas + the shared half-day list; Stage B refuses on any change, so a change to any of them after Stage A sends it through Stage A again"""
    s7, s8 = M17.stamp(), DV.stamp()
    return {"harness_sha256": R11.sha_lf(os.path.abspath(__file__)), "r17_sha256": s7["harness_sha256"], "r18_sha256": s8["harness_sha256"], **{k: v for k, v in s7.items() if k != "harness_sha256"},
            "facts_sha256": FILE_SHA["facts"], "facts_add_sha256": FILE_SHA["facts_add"], "map_sha256": FILE_SHA["map"], "map_add_sha256": FILE_SHA["map_add"]}


@contextlib.contextmanager
def spec(**kw):
    """swap SPEC entries (this file's) and r17_resmom.SPEC entries (the regression window, the sides, the size) for a block and put them back (the self-tests and the smoke shrink the windows and the sides; nothing stays patched)"""
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


def day_i(d):
    """dates -> int64 days since 1970-01-01 (a scalar, a Timestamp, a DatetimeIndex or a datetime64 array)"""
    return np.asarray(d).astype("datetime64[D]").astype(np.int64)


def years_back(days, k):
    """day numbers -> the same calendar date k years earlier (a 29 February moves to the 28th), as day numbers"""
    d = np.asarray(days, np.int64).astype("datetime64[D]")
    m = d.astype("datetime64[M]")
    dom = (d - m.astype("datetime64[D]")).astype(np.int64)
    m2 = m - np.timedelta64(12 * k, "M")
    first2 = m2.astype("datetime64[D]")
    last2 = (m2 + np.timedelta64(1, "M")).astype("datetime64[D]") - np.timedelta64(1, "D")
    return np.minimum(first2 + dom.astype("timedelta64[D]"), last2).astype(np.int64)


def row_le(days_i, d):
    """the row of the last session on or before each date in `d` (day numbers); -1 before the first session"""
    return np.searchsorted(days_i, np.asarray(d, np.int64), side="right") - 1


# ------------------------------------------------------------------ [A1] / [A8] the pinned files: the sha gate, the map read as ONE table, the flat file read as ONE table, cut at read
def check_pinned(key):
    """the sha256 (of the BYTES) of one pinned file: refuses - nothing computed, lockbox NOT read - when it is not on file or is another file than the registered one"""
    p = FILES[key]
    if not os.path.exists(p):
        refuse(f"refused: the pinned {FILE_LABEL[key]} {p} is not on file {TAIL}")
    got = M17.sha_raw(p)
    if got != FILE_SHA[key]:
        refuse(f"refused: {os.path.basename(p)} (sha256 {got}) is not the registered {FILE_LABEL[key]} ({FILE_SHA[key]}) - the file changed after it was registered {TAIL}")
    return got


def load_map():
    """[A1] / [A8] the symbol -> CIK map: the pinned base map (sha 19adc9ba) and TV's reviewed additions (sha 6bf8dfab) read as ONE map, each refused if its sha differs. Only the base map's current-ticker rows that passed TV's name check and its exact former-name rows are
    usable ([A1]), and the additions' reviewed rows ([A8], a CIK and the method reviewed_same_firm required); every other row (unmapped, ambiguous, mismatched, debenture / preferred / unit) gives no score and is counted by its method. A symbol twice in one file refuses.
    CHOICE ([A8] 'a symbol present in both is refused', read as: present in both AS A USABLE ROW - adopted as registered, [A15]): TV's 14 additions are symbols the base map lists WITHOUT a CIK (mismatch / ambiguous / unmapped), so a literal reading would refuse the pinned files themselves; a symbol that
    has a usable row in BOTH files refuses, an additions row over an unusable base row supersedes it (counted by the base row's method). -> SimpleNamespace(df = one row per symbol: symbol, cik, method, source, usable; info = counts)"""
    shas = {k: check_pinned(k) for k in ("map", "map_add")}
    base = pd.read_csv(FILES["map"], dtype=str, keep_default_na=False)
    add = pd.read_csv(FILES["map_add"], dtype=str, keep_default_na=False)
    for nm, df in (("map", base), ("map_add", add)):
        miss = [c for c in MAP_COLS if c not in df.columns]
        if miss:
            refuse(f"refused: the {FILE_LABEL[nm]} lacks the column(s) {miss} {TAIL}")
        for c in MAP_COLS:
            df[c] = df[c].str.strip()
        dup = df["symbol"][df["symbol"].duplicated()].tolist()
        if dup:
            refuse(f"refused: the {FILE_LABEL[nm]} lists a symbol more than once ({dup[:5]}) {TAIL}")
    bad_add = add[(add["cik"] == "") | ~add["method"].isin(ADD_METHODS)]
    if len(bad_add):
        refuse(f"refused: the reviewed map additions hold a row without a CIK or with a method outside {list(ADD_METHODS)} ({bad_add['symbol'].tolist()[:5]}) {TAIL}")
    ub = (base["cik"] != "") & base["method"].isin(ALLOWED_METHODS)
    both = set(base["symbol"]) & set(add["symbol"])
    clash = sorted(s for s in both if bool(ub[base["symbol"] == s].iloc[0]))
    if clash:
        refuse(f"refused: the symbol(s) {clash[:5]} have a usable row in BOTH the pinned map and its reviewed additions - no silent overlap {TAIL}")
    sup = Counter(base.loc[base["symbol"].isin(both), "method"].tolist())
    keep = base[~base["symbol"].isin(both)].assign(source="base")
    df = pd.concat([keep, add.assign(source="additions")], ignore_index=True)[["symbol", "cik", "method", "source"]]
    df["usable"] = (df["cik"] != "") & df["method"].isin(ALLOWED_METHODS + ADD_METHODS)
    cs = df[df["usable"]].groupby("cik")["symbol"].nunique()
    info = {"sha256": shas, "base_rows": int(len(base)), "additions_rows": int(len(add)), "additions_superseding_unusable_base_rows": dict(sup), "rows": int(len(df)), "by_method": dict(Counter(df["method"].tolist())),
            "usable_symbols": int(df["usable"].sum()), "usable_ciks": int(df.loc[df["usable"], "cik"].nunique()), "ciks_with_two_or_more_symbols": int((cs > 1).sum())}
    return SimpleNamespace(df=df, info=info)


def load_facts(cut, strict_cut=True):
    """[A1] / [A8] the share-count flat file: the pinned file (sha 02387a4f) and TV's reviewed additions (sha d10626d8) read as ONE table, each refused if its sha differs and a fact row (cik, concept, end, accn, val, filed) - or a CIK, whose rows are its
    whole extraction - present in both refused (no silent overlap). Only the columns this harness reads are read, with explicit dtypes. Cut at READ time: the extract holds nothing filed on / after 2025-06-30 and a row that is [strict_cut: refuses - the file is not the one
    registered; else] dropped and counted; rows whose as-of date (`end`) is on / after the cut (a typo year) are dropped and counted; the table is asserted to hold none. A row with an unreadable date or number, a unit other than 'shares' or a concept other than the three
    is dropped and counted. -> (the rows: cik, concept, val, start, end, accn, form, filed as typed columns; the counts)"""
    shas = {k: check_pinned(k) for k in ("facts", "facts_add")}
    parts, info = [], {"sha256": shas, "files": {}}
    for key in ("facts", "facts_add"):
        hdr = pd.read_csv(FILES[key], nrows=0)
        miss = [c for c in FACT_COLS if c not in hdr.columns]
        if miss:
            refuse(f"refused: the {FILE_LABEL[key]} lacks the column(s) {miss} {TAIL}")
        d = pd.read_csv(FILES[key], usecols=list(FACT_COLS), dtype={c: str for c in FACT_COLS}, keep_default_na=False)
        info["files"][key] = int(len(d))
        parts.append(d)
    a, b = parts
    ov = a.merge(b[["cik", "concept", "end", "accn", "val", "filed"]], on=["cik", "concept", "end", "accn", "val", "filed"], how="inner") if len(b) and len(a) else a.iloc[:0]
    if len(ov):
        refuse(f"refused: {len(ov):,} fact row(s) are in BOTH the pinned flat file and its reviewed additions (e.g. CIK {ov['cik'].iloc[0]}, {ov['concept'].iloc[0]}, end {ov['end'].iloc[0]}) - no silent overlap {TAIL}")
    both_cik = sorted(set(a["cik"]) & set(b["cik"]))
    if both_cik:
        refuse(f"refused: the CIK(s) {both_cik[:5]} have rows in BOTH the pinned flat file and its reviewed additions - an extraction of one CIK is whole in one file {TAIL}")
    d = pd.concat([a, b], ignore_index=True)
    info["rows_read"] = int(len(d))
    d["val"] = pd.to_numeric(d["val"], errors="coerce").astype(float)
    d["filed"] = pd.to_datetime(d["filed"].str.strip(), format="%Y-%m-%d", errors="coerce")
    d["end"] = pd.to_datetime(d["end"].str.strip(), format="%Y-%m-%d", errors="coerce")
    d["start"] = pd.to_datetime(d["start"].str.strip(), format="%Y-%m-%d", errors="coerce")
    cutt = TS(cut)
    late = (d["filed"] >= cutt).to_numpy()
    info["rows_filed_on_or_after_the_cut"] = int(late.sum())
    if late.any() and strict_cut:
        refuse(f"refused: {int(late.sum()):,} row(s) of the pinned share-count files are filed on / after the cut {cutt:%Y-%m-%d} - the extract must hold none (the sealed year) {TAIL}")
    bad_date = (d["filed"].isna() | d["end"].isna()).to_numpy()
    late_end = (~bad_date & ~late & (d["end"] >= cutt).to_numpy())
    bad_unit = (d["unit"].str.strip() != "shares").to_numpy()
    bad_con = ~d["concept"].isin(CONCEPTS + (WA_CONCEPT,)).to_numpy()
    info.update({"rows_unreadable_date": int(bad_date.sum()), "rows_end_on_or_after_the_cut": int(late_end.sum()), "rows_unit_not_shares": int(bad_unit.sum()), "rows_other_concept": int(bad_con.sum()),
                 "rows_value_missing": int(d["val"].isna().sum())})
    d = d[~(late | bad_date | late_end | bad_unit | bad_con)].reset_index(drop=True)
    assert_cut("share-count facts (filed)", d["filed"], cut)
    assert_cut("share-count facts (as-of date)", d["end"], cut)
    d["cik"] = d["cik"].str.strip()
    d["form"] = d["form"].str.strip().str.upper()
    d["accn"] = d["accn"].str.strip()
    info["rows"] = int(len(d))
    info["rows_by_concept"] = {k: int(v) for k, v in d["concept"].value_counts().items()}
    info["rows_by_form"] = {k: int(v) for k, v in d["form"].value_counts().head(20).items()}
    return d[["cik", "concept", "val", "start", "end", "accn", "form", "filed"]], info


# ------------------------------------------------------------------ [A2] the entries: per (cik, concept, end) the value of its FIRST filed row, the first filed date, and what makes an entry unusable
def entries_of(x):
    """one concept's rows (cik, val, end, accn, form, filed; typed) -> the ENTRIES, one per (cik, end), sorted by (cik, end): the value is the one of the FIRST filed row (the earliest `filed` over the rows of that end - later filings, amendments and restatements never
    replace it), f1 = that first filed date; ties on the first filed date (two accns on one day) take the smallest accn, and when they carry more than one value the entry is AMBIGUOUS and unusable. CHOICE (adopted as registered, [A15]): an entry is also unusable when its value is
    missing or its as-of date is after its own first filed date (a typo year: it would otherwise win 'the latest end'); a value that is zero or negative stays - it gives 'a value not positive' (no score, 459 N12 / 36 N24 name-months in the dryload), never a fallback to an older value.
    -> (DataFrame with cik, end, f1, val, accn, form, ok, and the counts)"""
    x = x.sort_values(["cik", "end", "filed", "accn"], kind="mergesort")
    x = x.assign(f1=x.groupby(["cik", "end"], sort=False)["filed"].transform("min"))
    at = x[x["filed"] == x["f1"]]
    nv = at.groupby(["cik", "end"], sort=False)["val"].nunique()
    first = at.drop_duplicates(["cik", "end"], keep="first").set_index(["cik", "end"])
    first["ambiguous"] = nv.reindex(first.index).to_numpy() > 1
    e = first.reset_index().sort_values(["cik", "end"], kind="mergesort").reset_index(drop=True)
    e["end_after_filed"] = e["end"] > e["f1"]
    e["val_missing"] = ~np.isfinite(e["val"].to_numpy(float))
    e["ok"] = ~(e["ambiguous"] | e["end_after_filed"] | e["val_missing"])
    cnt = {"entries": int(len(e)), "ambiguous": int(e["ambiguous"].sum()), "end_after_filed": int(e["end_after_filed"].sum()), "value_missing": int(e["val_missing"].sum()), "value_not_positive": int((e["ok"] & ~(e["val"] > 0)).sum()),
           "later_filing_carries_another_value": int((x.groupby(["cik", "end"], sort=False)["val"].nunique() > 1).sum())}
    return e[["cik", "end", "f1", "val", "accn", "form", "ok"]], cnt


def ent_arrays(e, cix):
    """the entry frame -> arrays on the CIK index: ck int64, end / f1 as day numbers, val, ok, accn / form (object). Sorted by (ck, end)"""
    ck = np.asarray([cix[c] for c in e["cik"]], np.int64) if len(e) else np.zeros(0, np.int64)
    o = np.lexsort((day_i(e["end"].to_numpy()), ck)) if len(e) else np.zeros(0, np.int64)
    return SimpleNamespace(ck=ck[o], end=day_i(e["end"].to_numpy())[o], f1=day_i(e["f1"].to_numpy())[o], val=e["val"].to_numpy(float)[o], ok=e["ok"].to_numpy(bool)[o],
                           accn=e["accn"].to_numpy(object)[o], form=e["form"].to_numpy(object)[o], n=len(e))


def build_facts(d):
    """the typed rows of load_facts -> the Facts the scoring reads: the CIK index; per score concept (the cover page, the balance sheet) its entries; the weighted-average concept's ANNUAL entries (a duration of 340 .. 380 days; a reported cross-check only);
    every entry's (cik, end, first filed) over the three concepts (the first share fact of a CIK, [A11]); and per CIK whether its share facts come ONLY from 20-F / 40-F / 6-K forms ([A4]; CHOICE: the whole table, all three concepts, decides - the extract holds only the
    dei and us-gaap taxonomies, so the IFRS test cannot be made apart)"""
    ciks = np.array(sorted(d["cik"].unique())) if len(d) else np.array([], dtype=str)
    cix = {c: i for i, c in enumerate(ciks)}
    nonfor = set(d.loc[~d["form"].isin(FOREIGN_FORMS), "cik"])
    foreign_only = np.array([c not in nonfor for c in ciks], bool)
    fx = SimpleNamespace(ciks=ciks, cix=cix, foreign_only=foreign_only, info={})
    for key, con in zip(CONCEPT_KEY, CONCEPTS):
        e, cnt = entries_of(d[d["concept"] == con])
        setattr(fx, key, ent_arrays(e, cix))
        fx.info[key] = cnt
    wa = d[d["concept"] == WA_CONCEPT]
    dur = (wa["end"] - wa["start"]).dt.days
    e, cnt = entries_of(wa[(dur >= 340) & (dur <= 380)])
    fx.wa = ent_arrays(e, cix)
    fx.info["wa_annual"] = cnt
    ee, _ = entries_of(d)                                                                   # one entry per (cik, end) over all concepts: only its first filed date and its as-of date are used
    fx.allent = ent_arrays(ee.assign(ok=ee["end"] <= ee["f1"]), cix)
    fx.info["ciks"] = int(len(ciks))
    fx.info["ciks_foreign_only"] = int(foreign_only.sum())
    fx.info["ciks_without_a_score_concept_entry"] = int(len(set(range(len(ciks))) - set(fx.dei.ck.tolist()) - set(fx.gaap.ck.tolist())))
    return fx


# ------------------------------------------------------------------ the World's NETISS arrays: names -> CIKs, the [A3] split arrays, the [A7] dividend log-sums
def bind(ent, days_i):
    """an entry table bound to a World's sessions: urow = the first session STRICTLY AFTER the first filed date - [A2] a value is usable at a rank close r iff urow <= r (the first session after its first filed date is on or before r); a date on / after the data's
    last session is never usable in the data"""
    return SimpleNamespace(**ent.__dict__, urow=np.searchsorted(days_i, ent.f1, side="right"))


def name_codes(syms, mp, fx):
    """(CIK index per name, -1 = none; the STATIC reason code per name, 0 = mapped and has share facts): a symbol not in the map; a map row of a method the prereg does not use (counted by method: mismatch / ambiguous / unmapped / debenture-preferred-unit / other);
    a mapped CIK with no share fact in the tables; [A4] a CIK whose share facts come only from 20-F / 40-F / 6-K forms"""
    syms = np.asarray(syms).astype(str)
    df = mp.df
    ix = pd.Index(df["symbol"]).get_indexer(syms)
    take = np.maximum(ix, 0)
    method, usable, cik = df["method"].to_numpy(object)[take], df["usable"].to_numpy(bool)[take], df["cik"].to_numpy(object)[take]
    code = np.zeros(len(syms), np.int8)
    code[ix < 0] = R_NOT_IN_MAP
    for i in np.flatnonzero((ix >= 0) & ~usable):
        code[i] = MAP_REASON.get(method[i], R_MAP_OTHER)
    cik_ix = np.full(len(syms), -1, np.int64)
    for i in np.flatnonzero((ix >= 0) & usable):
        j = fx.cix.get(cik[i], -1)
        if j < 0:
            code[i] = R_NO_FACTS
        else:
            cik_ix[i] = j
            if fx.foreign_only[j]:
                code[i] = R_FOREIGN
    return cik_ix, code


def dilate(a, n):
    """a (T, S) bool dilated by +-n rows: True where the column is True on any of the rows t-n .. t+n"""
    T = a.shape[0]
    c = np.vstack([np.zeros((1, a.shape[1]), np.int32), np.cumsum(a, axis=0, dtype=np.int32)])
    t = np.arange(T)
    return (c[np.minimum(t + n, T - 1) + 1] - c[np.maximum(t - n, 0)]) > 0


def split_arrays(W, cal):
    """[A3] / [A9] the two-way split check's arrays on the World's grid. fchg = a change of more than 1% between two consecutive FINITE values of the cache's split factor F (a split in a gap of missing bars shows nowhere and is caught the other way); calrow = a split of the
    pinned calendar (forward / reverse / unit splits) on its ex-date session (a date that is not a session moves to the next one). A change in F with no calendar split within +-3 sessions, and a calendar split with no change in F within +-3 sessions, are 'unmatched'. Returned as
    running counts (T + 1, S) so any window (a', a] is two look-ups: (the unmatched F changes, the unmatched calendar splits, every F change - the 'straddles a split' count)"""
    F = np.asarray(W.F, float)
    T, S_ = F.shape
    prev = np.vstack([np.full((1, S_), np.nan), F[:-1]])
    with np.errstate(invalid="ignore", divide="ignore"):
        ratio = F / prev - 1.0
    fchg = np.isfinite(ratio) & (np.abs(ratio) > SPLIT_TOL)
    calrow = np.zeros((T, S_), bool)
    sp = None if cal is None else getattr(cal, "split", None)
    if sp is not None and len(sp):
        ci = pd.Index(np.asarray(W.syms).astype(str)).get_indexer(sp["symbol"].astype(str))
        ri = np.searchsorted(day_i(W.days), day_i(pd.DatetimeIndex(sp["ex"])), side="left")
        ok = (ci >= 0) & (ri < T)
        calrow[ri[ok], ci[ok]] = True
    unF, unC = fchg & ~dilate(calrow, SPLIT_NEAR), calrow & ~dilate(fchg, SPLIT_NEAR)
    cs = lambda a: np.vstack([np.zeros((1, S_), np.int32), np.cumsum(a, axis=0, dtype=np.int32)])
    return cs(unF), cs(unC), cs(fchg)


def attach_netiss(W, fx, mp, cal):
    """everything the score reads besides the World's own arrays -> W.ni: the entry tables bound to the sessions, the names' CIKs and static reasons, the calendar's first date (the split check is applied only to windows that start on / after it; before it F alone
    stands, counted), the [A3] running counts, the [A7] cumulative log(1 + dividend / close) on the split-adjusted basis (net issuance less the part of the return paid out: ln(total return / price return) over a window is the sum of the ex-date terms), the [A13] mean raw dollar
    volume of the previous 20 sessions (r15_ddw.roll_prev on the raw close x volume - the helper the universe's own ranking uses)"""
    di = day_i(W.days)
    ni = SimpleNamespace(fx=fx, mp=mp, days_i=di, cache={}, fe_cache={})
    ni.dei, ni.gaap, ni.wa, ni.allent = (bind(getattr(fx, k), di) for k in ("dei", "gaap", "wa", "allent"))
    ni.ent = {"dei": ni.dei, "gaap": ni.gaap}
    ni.off = {"dei": 0, "gaap": ni.dei.n}
    cat = lambda f: np.concatenate([getattr(ni.dei, f), getattr(ni.gaap, f)])
    ni.E_end, ni.E_f1, ni.E_val, ni.E_accn, ni.E_form = cat("end"), cat("f1"), cat("val"), cat("accn"), cat("form")
    ni.cik_ix, ni.static = name_codes(W.syms, mp, fx)
    man = None if cal is None or getattr(cal, "info", None) is None else cal.info.get("manifest")
    cs0 = M17.calendar_start(man) if man else None
    ni.cal_start, ni.cal_start_i = cs0, (None if cs0 is None else int(day_i(cs0)))
    ni.cs_unF, ni.cs_unC, ni.cs_f = split_arrays(W, cal)
    ni.csplit = M17.attach_calendar_splits(W, cal)                                     # [A18] the calendar's split ex-dates on the grid (W.CSPL / W.cscs): the judged reading's one in-hold removal besides [D2]
    Dv, Ac = np.asarray(W.Dv1, float), np.asarray(W.Ac, float)
    with np.errstate(invalid="ignore", divide="ignore"):
        term = np.where((Dv > 0) & np.isfinite(Ac) & (Ac > 0), np.log1p(Dv / np.where(Ac > 0, Ac, 1.0)), 0.0)
    ni.cs_div = np.vstack([np.zeros((1, W.S)), np.cumsum(term, axis=0)])
    ni.dv20 = D15.roll_prev(np.asarray(W.Cl, float) * np.asarray(W.Vv, float), D15.SPEC["dv_n"])      # [A13] row t = the mean RAW dollar volume of rows t-20 .. t-1, all 20 present: r15_ddw.universe_mask's own quantity (its `dvn = roll_prev(Cl * Vv, dv_n)`, the one the universe ranks its 500 on) on the World's raw close and volume
    W.ni = ni
    return ni


# ------------------------------------------------------------------ [A2] S(r) and S': the point-in-time search, one concept at a time
def pairs_for_concept(ent, r, k, cn):
    """for every element of cn (a CIK index per name, -1 = none): the entry index of S(r) = the USABLE entry of the concept with the latest as-of date (a hit of the unusable ones - ambiguous, a value missing, an as-of date after its own first filing - is never a candidate)
    and of S' = the usable entry whose as-of date a' is closest to a - k years, inside +-35 days (a tie goes to the earlier date - adopted as registered, [A15]) -> (s, sp), -1 where there is none. Usable at r: its first filed date's next session is on or before r (ent.urow <= r)"""
    n = len(cn)
    s, sp = np.full(n, -1, np.int64), np.full(n, -1, np.int64)
    ui = np.flatnonzero(ent.ok & (ent.urow <= r))
    if not len(ui) or not (cn >= 0).any():
        return s, sp
    ck, ed = ent.ck[ui], ent.end[ui]
    last = np.r_[ck[1:] != ck[:-1], True]
    s_of = np.full(int(ck.max()) + 1, -1, np.int64)
    s_of[ck[last]] = ui[last]
    has_c = (cn >= 0) & (cn <= int(ck.max()))
    s = np.where(has_c, s_of[np.where(has_c, cn, 0)], -1)
    has = s >= 0
    tgt = years_back(ent.end[np.where(has, s, 0)], k)
    key = ck * KEYMUL + (ed - DAY0)
    q = np.where(has, cn, 0) * KEYMUL + (tgt - DAY0)
    pos = np.searchsorted(key, q)
    m = len(ui)
    li, ri = np.clip(pos - 1, 0, m - 1), np.clip(pos, 0, m - 1)
    far = 10 ** 9
    dl = np.where((pos - 1 >= 0) & (ck[li] == cn), tgt - ed[li], far)
    dr = np.where((pos < m) & (ck[ri] == cn), ed[ri] - tgt, far)
    left = dl <= dr
    best, bi = np.where(left, dl, dr), np.where(left, li, ri)
    sp = np.where(has & (best <= BAND_DAYS), ui[bi], -1)
    return s, sp


def score_rank(W, r):
    """the NETISS score of every name of the World (every column, whether or not it is in a rebalance's universe) at the rank close r, for both cells. Per name and cell, in this order: the STATIC reasons (map / CIK / facts / [A4] foreign); no usable fact at r of either concept [A4];
    the concept order - the cover page, else the balance sheet - where the concept used is the FIRST that has BOTH S(r) and S' (CHOICE, adopted as registered [A15]: 'else' = the first concept that yields a complete pair, so a cover page with a value now and none a year ago falls to the balance sheet, counted;
    the two values of one score are never from two concepts); no complete pair; a value not positive (no score, no fallback [A15]); a' before the cache's first session (F unknown); no split factor on an as-of date (F = the World's split factor on the as-of date, the previous session if it is not one); then
    ISS = ln(S x F(a) / (S' x F(a'))); [A3] the two-way split check where the calendar covers the window (a' on / after its start; before it F alone, counted); |ISS| > ln(10). CHOICE: the first reason is attributed in the order  not positive, a' before the cache, no factor, |ISS| > ln(10),
    a calendar split F does not show, an F change the calendar does not show - each of the last three is also LISTED on its own, whatever else fails. The score is universe-wide and pool-blind: [A13]'s one share class per firm is decided later, among the POOL names that have a score
    (ni_one), so no code here is ever R_SECOND_CLASS. -> {cell: SimpleNamespace(iss, iota, code, use, sg, pg, a, ap, fa, fap, flag10, a10, straddle, stale, fallback, f_alone, ln10, a3c, a3f)}, each (S,)"""
    ni, S_ = W.ni, W.S
    cached = ni.cache.get(r)
    if cached is not None:
        return cached
    cn = np.where(ni.static == R_SCORED, ni.cik_ix, -1)
    dr_i = int(ni.days_i[r])
    j_ = np.arange(S_)
    out = {}
    for cell, k in KS.items():
        use, sg, pg = np.zeros(S_, np.int8), np.full(S_, -1, np.int64), np.full(S_, -1, np.int64)
        any_s, dei_s = np.zeros(S_, bool), np.zeros(S_, bool)
        for q, key in enumerate(CONCEPT_KEY, 1):
            s, sp = pairs_for_concept(ni.ent[key], r, k, cn)
            any_s |= s >= 0
            if q == 1:
                dei_s = s >= 0
            take = (use == 0) & (s >= 0) & (sp >= 0)
            use[take], sg[take], pg[take] = q, s[take] + ni.off[key], sp[take] + ni.off[key]
        code = ni.static.astype(np.int64).copy()
        alive = code == R_SCORED

        def drop(mask, reason):
            hit = alive & mask
            code[hit] = reason
            alive[hit] = False
        drop(~any_s, R_NO_FACT)
        drop(use == 0, R_NO_BAND)
        sgc, pgc = np.where(sg >= 0, sg, 0), np.where(pg >= 0, pg, 0)
        sv, pv, a, ap = ni.E_val[sgc], ni.E_val[pgc], ni.E_end[sgc], ni.E_end[pgc]
        with np.errstate(invalid="ignore"):
            drop(~((sv > 0) & (pv > 0)), R_NOT_POS)
        drop(ap < ni.days_i[0], R_BEFORE_CACHE)
        ia, iap = row_le(ni.days_i, a), row_le(ni.days_i, ap)
        ia0, iap0 = np.maximum(ia, 0), np.maximum(iap, 0)
        fa, fap = np.asarray(W.F, float)[ia0, j_], np.asarray(W.F, float)[iap0, j_]
        drop(~(np.isfinite(fa) & np.isfinite(fap) & (fa > 0) & (fap > 0) & (ia >= 0) & (iap >= 0)), R_NO_FACTOR)
        with np.errstate(invalid="ignore", divide="ignore"):
            iss = np.log(sv * fa / (pv * fap))
            big10 = np.abs(iss) > LN10
        valid = alive.copy()
        covered = valid & (ni.cal_start_i is not None) & (ap >= (ni.cal_start_i if ni.cal_start_i is not None else 0))
        unC, unF = ni.cs_unC[ia0 + 1, j_] - ni.cs_unC[iap0 + 1, j_], ni.cs_unF[ia0 + 1, j_] - ni.cs_unF[iap0 + 1, j_]
        a3c, a3f = covered & (unC > 0), covered & (unF > 0)
        drop(big10, R_ISS10)
        drop(a3c, R_SPLIT_C)
        drop(a3f, R_SPLIT_F)
        scored = alive
        with np.errstate(invalid="ignore"):
            iota = iss - (ni.cs_div[ia0 + 1, j_] - ni.cs_div[iap0 + 1, j_])
        out[cell] = SimpleNamespace(iss=np.where(scored, iss, np.nan), iota=np.where(scored, iota, np.nan), code=code.astype(np.int8), use=np.where(scored, use, 0).astype(np.int8), sg=sg, pg=pg, a=a, ap=ap, fa=fa, fap=fap,
                                    flag10=scored & (np.abs(np.where(scored, iss, 0.0)) > LN15), straddle=scored & ((ni.cs_f[ia0 + 1, j_] - ni.cs_f[iap0 + 1, j_]) > 0), stale=scored & ((dr_i - ni.E_f1[sgc]) <= STALE_DAYS),
                                    fallback=scored & (use == 2) & dei_s, f_alone=valid & ~covered, ln10=valid & big10, a3c=a3c, a3f=a3f, scored=scored)
    ni.cache[r] = out
    return out


def first_end_at(W, r):
    """per CIK index: the earliest as-of date (day number) of any share fact (the three concepts, usable at r), a huge number where there is none - [A11] the CIKs whose first share fact starts inside a window (a holding-company reorganisation)"""
    ni = W.ni
    if r in ni.fe_cache:
        return ni.fe_cache[r]
    e = ni.allent
    fe = np.full(len(ni.fx.ciks), 10 ** 9, np.int64)
    ui = np.flatnonzero(e.ok & (e.urow <= r))
    if len(ui):
        ck = e.ck[ui]
        first = np.r_[True, ck[1:] != ck[:-1]]
        fe[ck[first]] = e.end[ui][first]
    ni.fe_cache[r] = fe
    return fe


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


def wa_cross(W, r, uni):
    """the weighted-average concept as a REPORTED cross-check (never an input): for the universe names scored in N12, the annual weighted-average basic shares (a 340 .. 380-day duration, the first filed value, usable at r) of the latest year and of the year before it
    (+-35 days), split-adjusted by F on their end dates, give ln(WA_t / WA_t-1); compared with ISS_1 -> (names with both, the rank correlation, the share on the same side of zero among those with both |.| above 1%)"""
    ni = W.ni
    sc = score_rank(W, r)["N12"]
    m = sc.scored[uni] & (ni.cik_ix[uni] >= 0)
    cols = uni[m]
    if not len(cols):
        return {"n": 0, "spearman": float("nan"), "same_side": float("nan")}
    s, sp = pairs_for_concept(ni.wa, r, 1, ni.cik_ix[cols])
    ok = (s >= 0) & (sp >= 0)
    s0, p0 = np.where(ok, s, 0), np.where(ok, sp, 0)
    ea, eb = ni.wa.end[s0], ni.wa.end[p0]
    ia, ib = row_le(ni.days_i, ea), row_le(ni.days_i, eb)
    fa, fb = np.asarray(W.F, float)[np.maximum(ia, 0), cols], np.asarray(W.F, float)[np.maximum(ib, 0), cols]
    good = ok & (ia >= 0) & (ib >= 0) & np.isfinite(fa) & np.isfinite(fb) & (ni.wa.val[s0] > 0) & (ni.wa.val[p0] > 0)
    with np.errstate(invalid="ignore", divide="ignore"):
        wa = np.where(good, np.log(ni.wa.val[s0] * fa / (ni.wa.val[p0] * fb)), np.nan)
    iss = sc.iss[cols]
    both = good & np.isfinite(iss)
    mat = both & (np.abs(wa) > 0.01) & (np.abs(iss) > 0.01)
    return {"n": int(both.sum()), "spearman": spearman(iss, wa), "same_side": float((np.sign(iss[mat]) == np.sign(wa[mat])).mean()) if mat.any() else float("nan")}


# ------------------------------------------------------------------ the ranks, and what is printed BEFORE any P&L: scored names, the concept split, the no-score reasons, the exclusions and flags, ISS per year, staleness, ADR / mid-window counts
def built_ranks(W, lo, hi):
    """the ranks r17_resmom.rm_build builds for the stretch [lo, hi]: every rebalance whose position EXITS inside it and whose rank has a full 252-session window -> [(r, f, x)]"""
    r_all, f_all, x_all = M17.rm_schedule(W.days)
    return [(r, f, x) for r, f, x in zip(r_all.tolist(), f_all.tolist(), x_all.tolist()) if x >= 0 and lo <= W.days[x] <= hi and r >= M17.SPEC["win"] - 1]


def score_report(W, ranks, values=True):
    """the pre-P&L record of every rank: the universe at the fill session, per cell the scored names, the names lost to each rule, the concept split (and the cover-page-to-balance-sheet fallbacks), the [A10] flags, the windows that straddle a split, the S(r) values first filed in the last
    60 days, the windows that rest on F alone, the [A11] ADR / IFRS filers and the CIKs whose first share fact starts inside the window, the names excluded at |ISS| > ln(10) and by [A3] (LISTED by symbol); values=True also keeps the scored ISS values (for the per-year median and the 5th / 95th
    percentiles: Stage A prints them, the dryload never does). This is the UNIVERSE's record, before the pool and before [A13] (a second share class is a POOL-level no-score reason: second_class_summary counts it from the pool). -> [one dict per rank]"""
    ni, rows = W.ni, []
    for r, f, x in ranks:
        uni = np.flatnonzero(W.U[f])
        rec = {"rank": f"{W.days[r]:%Y-%m-%d}", "year": int(W.days[f].year), "universe": int(len(uni)), "cells": {}}
        sc_all = score_rank(W, r)
        fe = first_end_at(W, r)
        for cell, k in KS.items():
            sc = sc_all[cell]
            cnt = np.bincount(sc.code[uni].astype(np.int64), minlength=len(REASONS))
            s = sc.scored[uni]
            cik = ni.cik_ix[uni]
            mid = (cik >= 0) & (fe[np.maximum(cik, 0)] > years_back(np.full(len(uni), ni.days_i[r]), k)) & (fe[np.maximum(cik, 0)] < 10 ** 9)
            c = {"scored": int(cnt[0]), "reasons": {REASONS[q]: int(cnt[q]) for q in range(1, R_SECOND_CLASS)}, "dei": int((sc.use[uni] == 1).sum()), "gaap": int((sc.use[uni] == 2).sum()), "fallback_to_gaap": int(sc.fallback[uni].sum()),
                 "a10_flags": int(sc.flag10[uni].sum()), "straddle": int(sc.straddle[uni].sum()), "stale": int(sc.stale[uni].sum()), "f_alone": int(sc.f_alone[uni].sum()), "mid_window_ciks": int(mid.sum()),
                 "mid_window_ciks_unscored": int((mid & ~s).sum()), "ln10_names": [str(q) for q in np.asarray(W.syms)[uni][sc.ln10[uni]]], "split_calendar_not_in_F_names": [str(q) for q in np.asarray(W.syms)[uni][sc.a3c[uni]]],
                 "split_F_not_in_calendar_names": [str(q) for q in np.asarray(W.syms)[uni][sc.a3f[uni]]]}
            if values:
                c["iss"] = sc.iss[uni][s]
            rec["cells"][cell] = c
        rows.append(rec)
    return rows


def unscored_by_name(W, ranks):
    """[A4] / [D1] the names that get no score for a reason that is not about the horizon - the symbol is not in the map, its map row is not usable (mismatch / ambiguous / unmapped / debenture-preferred-unit / another method), its CIK has no share fact, it is a foreign filer (20-F / 40-F / 6-K
    only) or it has no usable fact of either concept at the rank - counted BY NAME: the number of the ranks it is in the universe at (the fill session's universe). The codes are the same in both cells -> {reason: {symbol: ranks}}"""
    out = defaultdict(Counter)
    codes = (R_NOT_IN_MAP, R_MAP_MISMATCH, R_MAP_AMBIGUOUS, R_MAP_UNMAPPED, R_MAP_NONCOMMON, R_MAP_OTHER, R_NO_FACTS, R_FOREIGN, R_NO_FACT)
    syms = np.asarray(W.syms).astype(str)
    for r, f, _x in ranks:
        uni = np.flatnonzero(W.U[f])
        cd = score_rank(W, r)[CELLS[0]].code[uni]
        for q in codes:
            for s_ in syms[uni[cd == q]]:
                out[REASONS[q]][str(s_)] += 1
    return {k: dict(v) for k, v in out.items()}


def print_unscored_by_name(by):
    """[A4] the names with no score whatever the horizon, LISTED by name in full (symbol x the ranks it is in the universe at; the same in both cells)"""
    print("  [A4] names with no score whatever the horizon, LISTED by name (symbol x the ranks it is in the universe at; the same in both cells):")
    for reason in REASONS[1:]:
        if reason in by:
            print(f"    {REASON_TEXT[reason]} - {len(by[reason])} names: " + ", ".join(f"{s} x{n}" for s, n in sorted(by[reason].items())))


def pctl_text(a, qs=(5, 50, 95)):
    a = np.asarray(a, float)
    a = a[np.isfinite(a)]
    return [float(np.percentile(a, q)) for q in qs] if len(a) else [float("nan")] * len(qs)


def coverage_firsts(rows, cal_start):
    """per cell, from the ranks printed: the first rank with ANY scored name; the first rank whose date is at least k years after the cache's first session (every window can then start inside the cache: the prereg's 'first fully covered' one, about 2017-01-31 for N12 and 2018-01-31
    for N24); the first rank at least k years after the calendar's start ([A3]'s cross-check then covers every window - before it F alone stands, counted by rank as 'resting on F alone') -> {cell: {name: 'YYYY-MM-DD' | None}}. [A16] facts as found in the dryload: N12's first rank
    with any score is 2017-01-31 (22 names, no trade; first traded fill 2017-03-01), N24's 2018-01-31 (18 names; first fill 2018-03-01); the registered A2 windows stay (their first month holds no position - c is about 2% larger, not worth a change)"""
    out = {}
    for c, k in KS.items():
        dates = [TS(r["rank"]) for r in rows]
        first = lambda ok: next((f"{d_:%Y-%m-%d}" for d_ in dates if ok(d_)), None)
        out[c] = {"first_rank_with_a_score": first(lambda d_: any(r["cells"][c]["scored"] > 0 for r in rows if TS(r["rank"]) == d_)),
                  "first_rank_k_years_after_the_cache_start": first(lambda d_: d_ >= CACHE_FIRST_SESSION + pd.DateOffset(years=k)),
                  "first_rank_k_years_after_the_calendar_start": None if cal_start is None else first(lambda d_: d_ >= TS(cal_start) + pd.DateOffset(years=k))}
    return out


def print_score_report(rows, cal_start=None, names=True):
    """[A1]-[A11] BEFORE ANY P&L, in the prereg's order: the scored names per rank and per cell with the concept split, [A3]'s coverage and [A10]'s count beside them; the names lost to each no-score rule; the names excluded at |ISS| > ln(10) (listed by symbol when names=True, counted
    otherwise); the median and the 5th / 95th percentiles of ISS per year (when the values are kept: the dryload keeps none); the share of scores whose two as-of dates straddle a split; the share of S(r) values filed in the last 60 days (staleness); then the addenda's lists - [A3]'s two-way
    split failures, [A11]'s ADRs / IFRS filers and mid-window CIKs per rank"""
    print("BEFORE ANY P&L - the share-count score [A1]-[A11]: the universe at the fill session and the scored names of each cell (N12 / N24), by rank")
    fr = coverage_firsts(rows, cal_start)
    for c in CELLS:
        f = fr[c]
        print(f"  {c} coverage: the first rank with any scored name {f['first_rank_with_a_score']}; the first rank {KS[c]} year(s) after the cache's first session {CACHE_FIRST_SESSION:%Y-%m-%d} (the prereg's 'first fully covered' one) {f['first_rank_k_years_after_the_cache_start']}; "
              f"the first rank {KS[c]} year(s) after the calendar's start {'-' if cal_start is None else f'{TS(cal_start):%Y-%m-%d}'} (before it [A3] has no calendar and F alone stands) {f['first_rank_k_years_after_the_calendar_start']}")
        print(f"  {c} per rank (rank date: universe / scored | cover page / balance sheet (of which fallback) | [A10] flags | windows straddling a split | S(r) first filed in the last {STALE_DAYS} days | windows resting on F alone [A3]):")
        for rec in rows:
            x = rec["cells"][c]
            print(f"    {rec['rank']}: {rec['universe']} / {x['scored']} | {x['dei']} / {x['gaap']} ({x['fallback_to_gaap']}) | {x['a10_flags']} | {x['straddle']} | {x['stale']} | {x['f_alone']}")
    print("  names lost to each rule, by rank (counts of universe names, the first reason of each; the map / CIK / foreign reasons are static - every rank's):")
    for c in CELLS:
        print(f"  {c}: " + "; ".join(f"{rec['rank']}: " + ", ".join(f"{k} {v}" for k, v in rec["cells"][c]["reasons"].items() if v) for rec in rows))
    def lst(L):
        """the failing name-ranks (sorted symbol, rank), counted and - with names - LISTED BY NAME in full: every name once, the ranks it fails and its first and last one"""
        by = defaultdict(list)
        for q, d in L:
            by[q].append(d)
        head = f"{len(L)} name-ranks on {len(by)} names"
        if not L or not names:
            return head
        return head + " - " + "; ".join(f"{q} x{len(ds)} ({ds[0]}" + (f" .. {ds[-1]})" if len(ds) > 1 else ")") for q, ds in sorted(by.items()))
    for c in CELLS:
        l10 = sorted({(q, rec["rank"]) for rec in rows for q in rec["cells"][c]["ln10_names"]})
        print(f"  {c} excluded at |ISS| > ln(10) and {'LISTED' if names else 'counted'}: {lst(l10)}")
    if rows and "iss" in rows[0]["cells"][CELLS[0]]:
        for c in CELLS:
            byy = defaultdict(list)
            for rec in rows:
                byy[rec["year"]].append(rec["cells"][c]["iss"])
            print(f"  {c} ISS per fill year (scored names pooled over the year's ranks: n, 5th / median / 95th percentile): " + "; ".join(
                f"{y}: {sum(len(v) for v in vs):,}, " + " / ".join(f"{q:+.3f}" for q in pctl_text(np.concatenate(vs))) for y, vs in sorted(byy.items()) if vs))
    for c in CELLS:
        tot = lambda k: sum(rec["cells"][c][k] for rec in rows)
        n = max(tot("scored"), 1)
        print(f"  {c} over every rank: {tot('scored'):,} scored name-ranks; {tot('straddle'):,} ({tot('straddle') / n:.1%}) have a window that straddles a split (the split cancels through F); {tot('stale'):,} ({tot('stale') / n:.1%}) use an S(r) first filed in the last {STALE_DAYS} days; "
              f"{tot('f_alone'):,} windows start before the calendar and rest on F alone; {tot('a10_flags'):,} [A10] flags (|ISS| > ln(1.5): listed for the hand audit, never a filter)")
    for c in CELLS:
        a3c = sorted({(q, rec["rank"]) for rec in rows for q in rec["cells"][c]["split_calendar_not_in_F_names"]})
        a3f = sorted({(q, rec["rank"]) for rec in rows for q in rec["cells"][c]["split_F_not_in_calendar_names"]})
        print(f"  {c} [A3] a calendar split the cache's factor F does not show: {lst(a3c)}; an F change the calendar does not show: {lst(a3f)}")
    print("  [A11] unscored ADRs / IFRS filers (20-F / 40-F / 6-K only) per rank: " + "; ".join(f"{rec['rank']}: {rec['cells'][CELLS[0]]['reasons']['foreign_filer']}" for rec in rows))
    for c in CELLS:
        print(f"  [A11] {c}: CIKs whose first share fact starts inside the window (a holding-company reorganisation) per rank (and how many of them are unscored): " + "; ".join(
            f"{rec['rank']}: {rec['cells'][c]['mid_window_ciks']} ({rec['cells'][c]['mid_window_ciks_unscored']})" for rec in rows))


# ------------------------------------------------------------------ the sides: the 50 lowest ISS long, the 50 highest short; fewer than 150 scored names -> the bottom / top third, at least 20 a side, else nothing
def side_n(n):
    """the number of names a side holds when n names are scored (after [A13]'s one share class per firm): 50 at 150 or more; fewer: the top / bottom THIRD (CHOICE, adopted as registered [A15]: n // 3 a side, so the sides never touch; it never fires on the real data - N12 trades the full 50 a
    side in 99 rebalances, N24 in 87) when that is at least 20, else nothing -> (names a side, 'top' | 'third' | 'none')"""
    if n >= SPEC["min_scored"]:
        return M17.SPEC["n_side"], "top"
    k = n // 3
    return (k, "third") if k >= SPEC["min_side"] else (0, "none")


def pick_sides(cols, score, k):
    """the k longs and k shorts among the scored names: the longs the k LOWEST scores (the biggest shrinkers), the shorts the k HIGHEST (the biggest issuers). One ascending order by (-score, symbol order) - RESMOM's tie convention with the sign turned: the shorts are its first k
    (a tie goes to the lower symbol on the short side and to the higher symbol on the long side), the longs its last k, and the sides never share a name when 2k <= n -> (long positions, short positions) into the arrays given"""
    o = np.lexsort((np.asarray(cols), -np.asarray(score, float)))
    return o[::-1][:k], o[:k]


def decile_labels(cols, score):
    """[A5] ten equal-count deciles of the scored names by ISS: 0 = the lowest ISS (the biggest shrinkers) .. 9 = the highest; ties by symbol order; the remainder of n / 10 goes to the first deciles (np.array_split)"""
    order = np.lexsort((np.asarray(cols), np.asarray(score, float)))
    lab = np.zeros(len(order), np.int8)
    for d, part in enumerate(np.array_split(order, SPEC["dec_n"])):
        lab[part] = d
    return lab


def cell0():
    """an empty cell record of a rebalance: idx = the scored names among the pool (positions into rec.pool; [A13]: with the second share classes already out), score = their ISS, iota = their composite twin's score, k / mode = the side size and what the month trades, long / short = the
    picks by ISS and long_i / short_i by iota (positions into idx), dec = the deciles, U = the unit paths of the scored names; n_pre = the pool names with a score before [A13], second = the World columns of the second share classes taken out and kept = the column of the class that stays
    for each of them (same order)"""
    z = np.zeros(0, np.int64)
    return SimpleNamespace(idx=z, score=np.zeros(0), iota=np.zeros(0), n=0, n_pre=0, k=0, mode="none", traded=False, long=z, short=z, long_i=z, short_i=z, dec=None, U=None, second=z, kept=z)


def share_classes(W, f, cols, idx):
    """[A13] ONE SHARE CLASS PER FIRM. cols[idx] are the pool names that have a score in one cell (World columns); the names among them that share a CIK are classes of ONE firm and read the same two facts (GOOG / GOOGL, FOX / FOXA ...), so they would always be picked together - twice the
    size on one firm. Only the class with the LARGER mean RAW dollar volume over the 20 sessions before the fill (rows f-20 .. f-1 = W.ni.dv20[f], r15_ddw.roll_prev on the raw close x volume: the quantity the universe ranks its 500 names on) keeps its score; a tie goes to the LOWER SYMBOL
    (the symbol itself, not the column); a class whose dollar volume is undefined ranks last (it cannot happen on the real universe - a name needs all 20 sessions to be in it at all - and is counted). Decided per cell and per rank among the names that HAVE a score there: a class with
    no score in this cell is not a candidate and never takes the other's place. -> (keep (len(idx),) bool, the dropped columns, the kept column of each dropped one (same order), the groups decided with an undefined dollar volume)"""
    ni, cl = W.ni, np.asarray(cols)[idx]
    ck = ni.cik_ix[cl]
    keep, dropped, kept, nan_dv = np.ones(len(idx), bool), [], [], 0
    ok = np.flatnonzero(ck >= 0)
    if len(ok) > 1:
        _u, inv, n = np.unique(ck[ok], return_inverse=True, return_counts=True)
        for g in np.flatnonzero(n > 1):
            m = ok[inv == g]
            dv = ni.dv20[f, cl[m]]
            nan_dv += int(not np.isfinite(dv).all())
            rank = [(-float(dv[q]) if np.isfinite(dv[q]) else math.inf, str(W.syms[cl[m[q]]])) for q in range(len(m))]
            win = min(range(len(m)), key=rank.__getitem__)
            for q in range(len(m)):
                if q != win:
                    keep[m[q]] = False
                    dropped.append(int(cl[m[q]]))
                    kept.append(int(cl[m[win]]))
    return keep, np.asarray(dropped, np.int64), np.asarray(kept, np.int64), nan_dv


def slice_units(U, idx):
    """r17_resmom's unit paths of the whole pool cut to the rows `idx` (a cell's scored names)"""
    return SimpleNamespace(G=U.G[idx], ve=U.ve[idx], st=U.st[idx], mk=U.mk[idx], div=U.div[idx])


# ------------------------------------------------------------------ one rebalance: RESMOM's pool, NETISS's score, the picks
def ni_one(W, r, f, x, post_mode, units=True, counts_only=False):
    """one rebalance: the universe at the fill session f (sessions < f only) and the pool of r17_resmom's rm_one - the same removals in the same order (short history, no ES pairs, no fill, the pre / old / post hygiene windows, the [D2] spin-offs, the hand audit; CHOICE: RESMOM's
    'no score' is gone - a name's NETISS score exists per cell, so the pool is common to both cells and each cell's scored names are the pool names with a score, [A13]: less the second share classes - of two names that share a CIK only the more liquid keeps its score, per cell
    and rank, see share_classes). Per cell the scored names are the cell's pool for the null and the picks: both sides are always 50 names at 150 or
    more scored names, else the bottom / top third (at least 20 a side) or nothing (side_n); the 50 LOWEST ISS are the longs, the 50 HIGHEST the shorts. The composite twin's picks [A7] (by iota) and the deciles [A5] are cut on the same scored names. post_mode as r17_resmom's ('remove' =
    the leaky reading first registered, 'naive' = the look-ahead one, 'keep' = [A18] the JUDGED reading since the post-data bug fix: a name flagged inside the hold stays, on the split-safe path; only an
    announced (calendar) split or a [D2] ex-date in f < t <= x removes it). counts_only: no unit path, no pick - the pools and the scored sets are counted (the dryload)"""
    s = M17.SPEC
    uni = np.flatnonzero(W.U[f])
    rec = SimpleNamespace(r=r, f=f, x=x, nu=len(uni), nfull=0, traded=False, pool=np.zeros(0, np.int64), naive=np.zeros(0, bool), spin_win=np.zeros(0, np.int64), spin_hold=np.zeros(0, bool), cell={c: cell0() for c in CELLS}, sc=None, U=None)
    cnt = Counter()
    cnt["rebalances"] += 1
    cnt["universe"] += len(uni)
    if not len(uni):
        cnt["empty"] += 1
        return rec, cnt
    a = M17.windows(r)[0]
    fr = np.isfinite(W.Rd[a:r + 1][:, uni])
    n_ret, n_pair = fr.sum(axis=0), (fr & np.isfinite(W.es.ret[a:r + 1])[:, None]).sum(axis=0)
    short_hist = n_ret < s["min_n"]
    no_es = ~short_hist & (n_pair < s["min_n"])
    rec.nfull = int((~short_hist & ~no_es).sum())
    m_fill = np.isfinite(W.Ao[f, uni])                                          # CHOICE (r17_resmom's): a name with no open (or no factor) at the fill session cannot be filled
    lo_pre = r - s["skip"] - s["hyg_lead"] + 1
    pre = W.hyg(lo_pre, r, uni)                                                 # all four reasons, sessions r-25 .. r (r17_resmom's windows: 'hygiene exactly as RESMOM')
    old = W.hyg(a, lo_pre - 1, uni)[1:]                                         # gap, tbis, jump on sessions r-251 .. r-26
    post = W.hyg(r + 1, x, uni)                                                 # all four, inside the hold
    post_sp = M17.spn_hit(W, f + 1, x, uni)                                     # [D2] a spin-off / stock-dividend ex-date in f < t <= x
    post_cs = M17.csplit_hit(W, f + 1, x, uni) if post_mode == "keep" else np.zeros(len(uni), bool)     # [A18] an announced (calendar) split ex-date in f < t <= x: known at the rank
    win = (W.SPN[a:r + 1][:, uni] & np.isfinite(W.Rn[a:r + 1][:, uni])).sum(axis=0)
    pre_any, old_any, post_any = pre.any(axis=0), old.any(axis=0), post.any(axis=0) | post_sp
    aud = W.aud1[f, uni]
    W.aud_hit.update((AUD, f, int(c)) for c in uni[aud])
    reasons = [("short_history", short_hist), ("no_es_pairs", no_es), ("no_fill", ~m_fill)]
    reasons += [(f"pre_{h}", pre[q]) for q, h in enumerate(HYG)] + [(f"old_{h}", old[q]) for q, h in enumerate(HYG[1:])]
    if post_mode == "remove":
        reasons += [(f"post_{h}", post[q]) for q, h in enumerate(HYG)] + [("post_spin", post_sp)]
    elif post_mode == "keep":                                                   # [A18] only the events known at the rank remove a name
        reasons += [("post_calendar_split", post_cs), ("post_spin", post_sp)]
    D15.tally(cnt, reasons + [("audit", aud)], D15.attribute(reasons + [("audit", aud)], len(uni)))
    cnt["spin_window_names"] += int((win > 0).sum())
    cnt["spin_window_sessions"] += int(win.sum())
    cnt["spin_hold_names"] += int(post_sp.sum())
    pool_k = ~short_hist & ~no_es & m_fill & ~pre_any & ~old_any & ~aud
    pool = (pool_k & ~post_any) if post_mode == "remove" else (pool_k & ~post_cs & ~post_sp) if post_mode == "keep" else pool_k
    if post_mode == "naive":
        cnt["kept_naive"] += int((pool & post_any).sum())
    if post_mode == "keep":                                                     # [A18] the names flagged inside the hold that stay, on the split-safe path, per reason
        for q, h in enumerate(HYG):
            cnt[f"kept_{h}"] += int((pool & post[q]).sum())
        cnt["kept_flagged"] += int((pool & post.any(axis=0)).sum())
    pidx = np.flatnonzero(pool)
    cols = uni[pidx]
    rec.pool = cols
    rec.naive = post_any[pidx] if post_mode == "naive" else np.zeros(len(pidx), bool)
    rec.spin_win, rec.spin_hold = win[pidx], post_sp[pidx]
    rec.sc = score_rank(W, r)
    for c in CELLS:
        cc, sc = rec.cell[c], rec.sc[c]
        if not len(cols):
            cnt[f"mode_{c}_none"] += 1                                          # an empty pool trades nothing (counted with the other fallback months)
            continue
        iss = sc.iss[cols]
        idx0 = np.flatnonzero(np.isfinite(iss))
        keep, cc.second, cc.kept, nan_dv = share_classes(W, f, cols, idx0)         # [A13] one share class per firm: among the pool names WITH a score (this cell, after every removal) only the more liquid class keeps it
        idx = idx0[keep]
        cc.n_pre, cc.idx, cc.n, cc.score, cc.iota = int(len(idx0)), idx, int(len(idx)), iss[idx], sc.iota[cols][idx]
        cnt[f"scored_{c}"] += cc.n
        cnt[f"no_score_{c}"] += int(len(cols) - cc.n)
        for q in range(1, R_SECOND_CLASS):
            cnt[f"ns_{c}_{REASONS[q]}"] += int((sc.code[cols] == q).sum())
        cnt[f"ns_{c}_{REASONS[R_SECOND_CLASS]}"] += int(len(cc.second))
        cnt[f"nan_dv_{c}"] += nan_dv
        cc.k, cc.mode = side_n(cc.n)
        cnt[f"mode_{c}_{cc.mode}"] += 1
        if cc.n >= SPEC["dec_min"]:
            cnt[f"dec_{c}"] += 1
            if not counts_only:
                cc.dec = decile_labels(cols[idx], cc.score)
        else:
            cnt[f"dec_none_{c}"] += 1
        if counts_only:
            cc.traded = cc.k > 0
            continue
        if cc.k > 0:
            cc.long, cc.short = pick_sides(cols[idx], cc.score, cc.k)              # the k lowest ISS are the longs, the k highest the shorts
            cc.long_i, cc.short_i = pick_sides(cols[idx], cc.iota, cc.k)           # [A7] the same rule on the composite twin's score
            cc.traded = True
    rec.traded = any(rec.cell[c].traded for c in CELLS)
    if units and len(cols) and any(rec.cell[c].traded or rec.cell[c].dec is not None for c in CELLS):
        rec.U = M17.rm_units(W, f, x, rec.pool, rec.naive)
        for c in CELLS:
            if rec.cell[c].traded or rec.cell[c].dec is not None:
                rec.cell[c].U = slice_units(rec.U, rec.cell[c].idx)
    return rec, cnt


def ni_build(W, lo, hi, post_mode="remove", units=True, counts_only=False):
    """every rebalance whose position EXITS inside [lo, hi] with a full 252-session window (r17_resmom.rm_build's rules: the stretch by exit session, warm-up counted, a position whose exit is past the stage's data unresolved - out of the cell AND the null) -> Leg(kind, recs, cnt by
    fill year)"""
    r_all, f_all, x_all = M17.rm_schedule(W.days)
    recs, cnt = [], defaultdict(Counter)
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
        rec, c = ni_one(W, r, f, x, post_mode, units, counts_only)
        recs.append(rec)
        cnt[y].update(c)
    return SimpleNamespace(kind="NI", recs=recs, cnt=cnt)


def cell_leg(L, cell, alt=False):
    """one cell's view of a Leg in the shape r15's L1 engine reads (rec.sig = the cell's score on ITS scored pool, rec.pool = the scored names, rec.long / rec.short = its picks on that pool, rec.U = their unit paths): l1_cell and r17_resmom's run_cell run on it unchanged.
    alt=True: the composite twin [A7] - the same view with the picks and the score of iota"""
    recs = []
    for rec in L.recs:
        cc = rec.cell[cell]
        v = SimpleNamespace(r=rec.r, f=rec.f, x=rec.x, traded=cc.traded, pool=rec.pool[cc.idx], naive=rec.naive[cc.idx], nu=rec.nu, sig=cc.iota if alt else cc.score, long=cc.long_i if alt else cc.long, short=cc.short_i if alt else cc.short)
        if cc.traded and cc.U is not None:
            v.U = cc.U
        recs.append(v)
    return SimpleNamespace(kind="L1", recs=recs, cnt=L.cnt)


def second_class_summary(L, W):
    """[A13] what the one-share-class rule did, COUNTED from a leg's records (no score, no value of any kind): per rank and cell the pool names with a score, the second share classes taken out and the names left; per cell and fill year the second-class name-ranks (the cnt keys the other
    no-score reasons use); per CIK the symbols involved and, per cell, how many name-ranks each was dropped and how many it was kept over a dropped sibling (one per class it beat); the groups decided with an undefined dollar volume. A counts-only leg is enough
    -> {"ranks": [{rank, year, cells: {cell: {pool_scored, second, scored}}}], "by_year": {cell: {year: n}}, "total": {cell: n}, "ciks": {cik: {symbol: {cell: {dropped, kept}}}}, "nan_dv": {cell: n}}"""
    ni, ranks, ciks = W.ni, [], {}
    by_year, total = {c: defaultdict(int) for c in CELLS}, {c: 0 for c in CELLS}
    for rec in L.recs:
        ent = {"rank": f"{W.days[rec.r]:%Y-%m-%d}", "year": int(W.days[rec.f].year), "cells": {}}
        for c in CELLS:
            cc = rec.cell[c]
            ent["cells"][c] = {"pool_scored": int(cc.n_pre), "second": int(len(cc.second)), "scored": int(cc.n)}
            by_year[c][ent["year"]] += len(cc.second)
            total[c] += len(cc.second)
            for d, k in zip(cc.second.tolist(), cc.kept.tolist()):
                g = ciks.setdefault(str(ni.fx.ciks[int(ni.cik_ix[d])]), {})
                g.setdefault(str(W.syms[d]), {}).setdefault(c, {"dropped": 0, "kept": 0})["dropped"] += 1
                g.setdefault(str(W.syms[k]), {}).setdefault(c, {"dropped": 0, "kept": 0})["kept"] += 1
        ranks.append(ent)
    nan_dv = {c: int(sum(v.get(f"nan_dv_{c}", 0) for v in L.cnt.values())) for c in CELLS}
    return {"ranks": ranks, "by_year": {c: dict(sorted(by_year[c].items())) for c in CELLS}, "total": total, "ciks": dict(sorted(ciks.items())), "nan_dv": nan_dv}


# ------------------------------------------------------------------ the null: RANDOM NAMES from each rebalance's eligible SCORED pool
def ni_null(W, L, nreps, vcode=0):
    """the family-aware null [prereg NULL]: per draw and per rebalance the cell traded, its k longs and k shorts are replaced by the same number of names drawn uniformly without replacement from that rebalance's eligible SCORED pool ([A13]: the names the cell scores - a second share class
    is no name of it: its unit paths are never cut into cc.U, so it cannot be drawn) (the same hygiene, sizing, fills, costs, borrow); each cell
    has its own random stream (seeds [20261008, cell, vcode]), so the MAX over the 2 cells is the better of two independent random books. r15's null_l1 draws a fixed 50 - the sides here are 50 or a third - so the draw is written out (the same draw_order, l1_pnl and sizing). -> {cell: (nreps, T)
    P&L by stock session}"""
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
            PL, PS = D15.l1_pnl(cc.U, idx, 1, cfg, kt), D15.l1_pnl(cc.U, idx, -1, cfg, kt)
            o = D15.draw_order(rng, nreps, cc.n, 2 * cc.k)
            a[:, rec.f:rec.x + 1] += slot * (PL[o[:, :cc.k]].sum(axis=1) + PS[o[:, cc.k:]].sum(axis=1))
        acc[c] = a
    return acc


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


# ------------------------------------------------------------------ the statistics, the judge, A2 over the reference, the gate, the beta credit rule [A6], dollars a year [A12]
def stat_run(B, rows, run, lo=None, hi=None):
    """r15's cell statistics on one stretch (default WF) of a run's daily series -> (stats, the series on #463's index, the positions held per row)"""
    lo, hi = (WF0 if lo is None else lo), (PRE_END if hi is None else hi)
    xB, cB = D15.to_B(run.x, rows, B.n), D15.to_B(run.cnt, rows, B.n)
    return D15.cell_stats(B, xB, cB, lo, hi, run), xB, cB


def per_year(net, years):
    """[A12] dollars a year = net / years (the house yardstick's years: the stretch's first to last row / 365.25)"""
    return float(net) / float(years) if years and np.isfinite(years) and years > 0 else float("nan")


def years_held(B, cB):
    """the July-June WF years in which the cell holds a position on at least one day (its own years: N24 has none in 2016-17; [A15]: (d) counts these years - N12 needs 6 of its 9, N24 6 of its 8)"""
    k = B.mask(WF0, PRE_END)
    c = np.asarray(cB)[k]
    return sorted({int(y) for y, v in zip(jyear(B.index[k]), c) if v > 0})


def judge_cell(st, net10, nul, cell, n_years):
    """(a) >= 60 monthly rebalances; (b) WF ROC @ $30k >= 15 and net > 0 at 5 AND at 10 bps a side; (c) WF ROC above the null's 95th percentile (the max over the 2 cells); (d) positive in >= 6 of the cell's July-June WF years (N24: at least TWO THIRDS of its years, rounded up - n_years
    are the years the cell holds positions in; adopted as registered, [A15]: N12 needs 6 of its 9, N24 6 of its 8) and net > 0 without Feb 15 - Apr 30 2020; (e) profitable without its best 1% of days AND without its best 1% of name-months. (f), the hand audit, is separate (the lead's). A NaN fails every comparison it enters"""
    R = RULES
    need = R["years"] if cell == "N12" else -(-2 * int(n_years) // 3)
    chk = {f"rebalances>={R['reb']}": st["n_units"] >= R["reb"], f"ROC>={R['roc']:g}": st["roc"] >= R["roc"], "net>0 at 5 bps": (st["net"] > 0) if R["net_pos"] else True,
           "net>0 at 10 bps": (net10 > 0) if R["stress"] else True, "ROC>null p95": (st["roc"] > nul["roc_max"]["p95"]) if R["null"] else True,
           f"positive in >={need} of {int(n_years)} July-June years": st["years_pos"] >= need, "net>0 without Feb 15 - Apr 30 2020": (st["net_ex2020"] > 0) if R["ex2020"] else True,
           "profitable without its best 1% of days": (st["net_ex_best_days"] > 0) if R["exbest"] else True,
           "profitable without its best 1% of name-months": (st["net_ex_best_pos"] > 0) if R["exbest"] else True}
    return {k: bool(v) for k, v in chk.items()}


def dd5_rec(B, x, lo=None, hi=None):
    """[A19] DD5 beside a ROC @ $30k (owner rule of 2026-10-07): the mean depth of the 5 deepest non-overlapping drawdown episodes of the daily series x (on #463's index) over [lo, hi] (default WF), its worst drawdown and
    the one-episode flag (worst > 1.3 x DD5: the ROC is 'driven by one episode'). Reported, never a pass condition"""
    k = B.mask(WF0 if lo is None else lo, PRE_END if hi is None else hi)
    r = _dd5(pd.Series(np.asarray(x, float)[k], index=B.index[k]))
    return {"dd5": float(r["dd5_usd"]), "n": int(r["n"]), "max_dd": float(r["max_dd"]), "one_episode": bool(r["one_episode"])}


def dd5_txt(d):
    return f"DD5 ${d['dd5']:,.0f}" + (" - driven by one episode" if d["one_episode"] else "")


def a2_report(B, xB, ref, cell):
    """STAGE A2 (WF) - a REPORT, never a pass route [X1]: the REFERENCE book (#463 + 0.264 x RES) + c x the cell against the reference, c by VOLATILITY on the cell's OWN first two fully covered years (N12 2017-02-01 .. 2019-01-31, N24 2018-02-01 .. 2020-01-31: 25% of #463's daily std
    over those rows / the cell's), 0.5c and 2c reported, the plain #463 + c x the cell a reported row; an incremental pass = ROC @ $30k and Sortino both strictly above the reference's. r18_divrun's a2_report with the cell's window. [A12] the dollars a year (net / years) beside
    every ROC: the reference's, the reference + c x the cell at c / 0.5c / 2c, the plain #463 + c x the cell"""
    with patched(DV, A2_WIN=A2_WINS[cell], A2_TARGET=A2_TARGET, A2_REPORT=A2_REPORT):
        a = DV.a2_report(B, xB, ref)
    yrs = float(ref.stats["years"])
    a["reference"]["usd_year"] = per_year(a["reference"]["net"], yrs)
    for key in ("at_half_c", "at_double_c"):
        if a.get(key):
            a[key]["usd_year"] = per_year(a[key]["net"], yrs)
    if np.isfinite(a.get("net", float("nan"))):
        a["usd_year"] = per_year(a["net"], yrs)
    pl = a.get("plain_463") or {}
    if np.isfinite(pl.get("net", float("nan"))):
        pl["usd_year"] = per_year(pl["net"], yrs)
    raw, xb = np.asarray(ref.raw, float), np.asarray(xB, float)                     # [A19] DD5 beside every ROC: the reference, the reference + c x the cell at c / 0.5c / 2c, the plain #463 + c x the cell
    a["reference"]["dd5"] = dd5_rec(B, raw)
    c = a.get("c", float("nan"))
    if np.isfinite(c) and c > 0:
        a["dd5"] = dd5_rec(B, raw + c * xb)
        for key, m in (("at_half_c", A2_REPORT[0]), ("at_double_c", A2_REPORT[1])):
            if a.get(key):
                a[key]["dd5"] = dd5_rec(B, raw + m * c * xb)
        if pl:
            pl["dd5"] = dd5_rec(B, np.asarray(B.raw, float) + c * xb)
    return a


def plain_a2(B, xB, cell):
    """the registered volatility rule for c (r18_divrun's plain_a2 = r17_resmom's A2 code) on the cell's window; used by Stage B to recompute the frozen c"""
    with patched(DV, A2_WIN=A2_WINS[cell], A2_TARGET=A2_TARGET, A2_REPORT=A2_REPORT):
        return DV.plain_a2(B, xB)


def beta_credit(B, S12, W, rows, xB):
    """[A6] the cell's realised beta to ES (its daily $ P&L on ES's daily return, per $ of ONE SIDE's notional = n_side x slot) on #463's drawdown days and on every WF day, and whether the cell may be CREDITED: CHOICE (adopted as registered, [A15]) - BOTH betas must be within +-0.20 per $200,000 (one side: 50 x $4,000) (the prereg says 'a cell with
    |realised beta| > 0.20' and prints two: the stricter reading never credits what either reading refuses); a beta that cannot be computed refuses the credit. A cell without credit has its drawdown-day profile REPORTED but gets no incremental A2 pass, no gate, no line"""
    side = M17.SPEC["n_side"] * M17.SPEC["slot"]
    with np.errstate(all="ignore"):
        eb = D15.es_beta(B, S12, W, rows, xB)
    dd, al = eb["DD days"]["usd_per_1.00_es"] / side, eb["all WF days"]["usd_per_1.00_es"] / side
    ok = bool(np.isfinite(dd) and np.isfinite(al) and abs(dd) <= BETA_CAP and abs(al) <= BETA_CAP)
    return {"side_notional": float(side), "beta_dd_days": float(dd), "beta_all_days": float(al), "cap": BETA_CAP, "within_cap": ok, "es_beta": eb}


def gate70(c, ref, nul):
    """MANAGER #70's gate basis [X1], REPORTED: the cell's DO on the REFERENCE book's drawdown days beside the random-name null's (the MAX over the 2 cells), and whether the cell's P&L inside the reference's qualifying episodes stays positive without its best one; with the [A6] credit:
    'credited' is False for a cell the beta rule refuses. No pass is decided here"""
    g = {"basis": "the REFERENCE book's drawdown days (MDL r1's episode rule)", "episodes": ref.structure["episodes"], "dd_days": ref.structure["days"], "DO": c["seat_ref"]["DO"], "rho_dd": c["seat_ref"]["rho_dd"], "episode_pnl": c.get("episode_pnl")}
    if nul is not None:
        p = nul["do_ref_max"]
        g.update({"null_do_p5": p["p5"], "null_do_p50": p["p50"], "null_do_p95": p["p95"], "DO_above_null_p95": bool(c["seat_ref"]["DO"] > p["p95"])})
    ep = c.get("episode_pnl")
    if ep:
        g["pnl_without_best_episode"] = float(sum(ep) - max(ep))
        g["positive_without_best_episode"] = bool(sum(ep) - max(ep) > 0)
        g["episodes_helped"] = int(sum(1 for v in ep if v > 0))
    g["credited"] = bool(c["beta"]["within_cap"])
    return g


def pick_candidate(cells, passing):
    """CHOICE (the prereg names no tie-break between two passing cells; A2 is only a report; adopted as registered, [A15]): the passing cell with the higher WF standalone ROC @ $30k goes to Stage B (ties: N12 first); the other is reported"""
    return max(passing, key=lambda c: (cells[c]["base"]["roc"], -CELLS.index(c))) if passing else None


def stage_a_flow(cells):
    """Stage A's bookkeeping, pure: passing = the cells that clear (a) - (e) (their checks, the registered null included); the candidate = pick_candidate(passing). (f), the hand audit, is NEVER decided here - every passing cell 'awaits the hand audit', and Stage B needs the lead's
    go-flag"""
    passing = [c for c in CELLS if cells[c]["PASS"]]
    return passing, pick_candidate(cells, passing)


# ------------------------------------------------------------------ [A5] deciles, [A6] the ES-hedged twin
def decile_series(W, L, cell):
    """[A5] the ten ISS deciles of the cell as equal-weight LONG-ONLY baskets at $4,000 a name, marked like the cells (next-open fills, holds to the next fill, the dividends, 5 bps a side, no borrow) -> (x (10, T) the baskets' daily P&L by stock session, spread (10, T) the same
    less the ES position of the same notional - CHOICE: 'their spread over ES' = the basket's P&L minus (names x $4,000) x ES's daily return on every session of the hold, a beta-1 hedge -, names (10,) the name-months held, ranks cut)"""
    slot, cfg, nd = M17.SPEC["slot"], D15.l1_cfg(), SPEC["dec_n"]
    x, sp, nn, nr = np.zeros((nd, W.T)), np.zeros((nd, W.T)), np.zeros(nd), 0
    esr = np.nan_to_num(np.asarray(W.es.ret, float))
    for rec in L.recs:
        cc = rec.cell[cell]
        if cc.dec is None or cc.U is None:
            continue
        nr += 1
        kt = W.k[rec.f:rec.x + 1]
        for d in range(nd):
            idx = np.flatnonzero(cc.dec == d)
            if not len(idx):
                continue
            g = slot * D15.l1_pnl(cc.U, idx, 1, cfg, kt).sum(axis=0)
            x[d, rec.f:rec.x + 1] += g
            sp[d, rec.f:rec.x + 1] += g - slot * len(idx) * esr[rec.f:rec.x + 1]
            nn[d] += len(idx)
    return x, sp, nn, nr


def decile_stats(B, rows, W, L, cell):
    """[A5] per decile (1 = the biggest shrinkers .. 10 = the biggest issuers): the WF net, ROC @ $30k and dollars a year of the long-only basket, and of its spread over ES"""
    x, sp, nn, nr = decile_series(W, L, cell)
    k = B.mask(WF0, PRE_END)
    out = []
    for d in range(x.shape[0]):
        row = {"decile": d + 1, "name_months": int(nn[d])}
        for lab, ser in (("", x[d]), ("spread_", sp[d])):
            s = R11.stats(D15.to_B(ser, rows, B.n)[k], B.index[k]) or {}
            row.update({lab + "net": float(s.get("net", float("nan"))), lab + "roc": float(s.get("roc", float("nan"))), lab + "usd_year": per_year(s.get("net", float("nan")), s.get("years", float("nan")))})
        out.append(row)
    return {"ranks_cut": int(nr), "deciles": out}


def hedge_ratios(W, x, L, cell):
    """[A6] the ES overlay's ratio at every traded rebalance of a cell: the OLS slope (an intercept and a slope, the finite pairs, >= 230 of them) of the cell's OWN daily $ P&L on ES's daily return over the 252 sessions r-251 .. r - ex ante, known at the rank close - in $ per 1.00
    of ES return; ZERO until 252 sessions of the cell's own P&L exist before the rank (its first fill is row f0: r - 251 >= f0) -> {rec index: ratio}"""
    es = np.asarray(W.es.ret, float)
    traded = [i for i, rec in enumerate(L.recs) if rec.cell[cell].traded]
    out = {}
    if not traded:
        return out
    f0, win = L.recs[traded[0]].f, SPEC["hedge_win"]
    for i in traded:
        r = L.recs[i].r
        b = 0.0
        if r - win + 1 >= f0:
            y, m = np.asarray(x, float)[r - win + 1:r + 1], es[r - win + 1:r + 1]
            ok = np.isfinite(y) & np.isfinite(m)
            if ok.sum() >= SPEC["hedge_min"] and np.ptp(m[ok]) > 0:
                dm = m[ok] - m[ok].mean()
                b = float((dm * (y[ok] - y[ok].mean())).sum() / (dm * dm).sum())
        out[i] = b
    return out


def hedged_series(W, x, L, cell):
    """[A6] the cell's daily P&L with the ES overlay: short b x ES's daily return on every session of each hold (b = hedge_ratios, in $ per 1.00; a session without an ES return earns nothing), the futures cost DV.ES_EXACT_BPS of |b| a side at the fill and at the exit
    (CHOICE: the prereg gives no cost for the overlay; adopted as registered, [A15]: 0.5 bps a side) -> (the hedged series (T,), the ratios)"""
    es = np.nan_to_num(np.asarray(W.es.ret, float))
    br = hedge_ratios(W, x, L, cell)
    h = np.asarray(x, float).copy()
    c = DV.ES_EXACT_BPS * 1e-4
    for i, b in br.items():
        rec = L.recs[i]
        h[rec.f:rec.x + 1] -= b * es[rec.f:rec.x + 1]
        h[rec.f] -= c * abs(b)
        h[rec.x] -= c * abs(b)
    return h, br


# ------------------------------------------------------------------ one reading of Stage A: legs -> cells -> stress rows -> null -> checks -> A2
def evaluate(W, B, S12, ref, rows, post_mode, nreps, vcode=0, full=False):
    """one reading of Stage A on the WF stretch. post_mode 'remove' = the REGISTERED reading (a hygiene flag inside the hold removes the position before the ranking), 'naive' = the look-ahead variant (those positions are kept at their naive raw P&L); both run the same code, so a flip
    between them is the data hygiene's doing. nreps > 0 draws the registered null (random names from the scored pool; vcode picks its random streams) and judges (a) - (e); full = also the reports' rows (the sides apart, borrow stress, -100% / shorts at zero, the regime halves, the
    deciles [A5], the composite twin [A7], the ES-hedged twin [A6]). -> (summary, objects: the leg, each cell's leg view / base run / series / side series)"""
    lo, hi = WF0, PRE_END
    L = ni_build(W, lo, hi, post_mode)
    legs = {c: cell_leg(L, c) for c in CELLS}
    runs, series, side_x, summ = {}, {}, {}, {}
    for cell in CELLS:
        CL = legs[cell]
        base = M17.run_cell(W, CL, D15.l1_cfg(), pos=True)
        st, xB, cB = stat_run(B, rows, base)
        runs[cell], series[cell] = base, (xB, cB)
        at = lambda cfg, CL=CL, **kw: stat_run(B, rows, M17.run_cell(W, CL, cfg, **kw))[0]
        c = {"base": st, "cost0": at(D15.l1_cfg(bps=0.0)), "stress": {f"{b:g} bps": at(D15.l1_cfg(bps=b)) for b in STRESS_BPS}, "seat": D15.seat_measure(S12, xB), "seat_ref": D15.seat_measure(ref.S, xB), "years_held": years_held(B, cB),
             "A2": a2_report(B, xB, ref, cell), "beta": beta_credit(B, S12, W, rows, xB)}
        c["usd_year"] = per_year(st["net"], st["years"])
        c["dd5"] = dd5_rec(B, xB)                                                          # [A19] DD5 beside the cell's ROC @ $30k
        c["episode_pnl"] = [float(e["cell_pnl"]) for e in D15.episodes_table(ref.S, xB)]
        c["A2"]["credited"] = bool(c["beta"]["within_cap"])
        c["A2"]["incremental_credit"] = bool(c["A2"]["incremental_pass"] and c["beta"]["within_cap"])
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
            c["deciles"] = decile_stats(B, rows, W, L, cell)
            run_i = M17.run_cell(W, cell_leg(L, cell, alt=True), D15.l1_cfg(), pos=True)                 # [A7] the composite-issuance twin: the same picks rule on iota
            st_i, xi, _ = stat_run(B, rows, run_i)
            ov = defaultdict(list)
            for rec in L.recs:
                cc = rec.cell[cell]
                if cc.traded:
                    cols = rec.pool[cc.idx]
                    ov["long"].append(len(set(cols[cc.long].tolist()) & set(cols[cc.long_i].tolist())) / cc.k)
                    ov["short"].append(len(set(cols[cc.short].tolist()) & set(cols[cc.short_i].tolist())) / cc.k)
            c["composite"] = {"base": st_i, "usd_year": per_year(st_i["net"], st_i["years"]), "pick_overlap_with_iss_picks": {k_: (float(np.mean(v)) if v else float("nan")) for k_, v in ov.items()},
                              "scores_with_window_before_the_calendar": int(sum(int(rec.sc[cell].f_alone[rec.pool[rec.cell[cell].idx]].sum()) for rec in L.recs))}
            xh, br = hedged_series(W, base.x, L, cell)                                           # [A6] the ES-hedged twin of the cell
            sth = D15.cell_stats(B, D15.to_B(xh, rows, B.n), cB, lo, hi, base)
            c["hedged"] = {"base": sth, "usd_year": per_year(sth["net"], sth["years"]), "ratios_nonzero": int(sum(1 for v in br.values() if v != 0.0)), "ratios": int(len(br)),
                           "beta": beta_credit(B, S12, W, rows, D15.to_B(xh, rows, B.n))}
        summ[cell] = c
    nul = None
    if nreps:
        acc = ni_null(W, L, nreps, vcode)
        pc, pdo = {}, {}
        for cell in CELLS:
            pc[cell], pdo[cell] = DV.null_stats(S12, ref.S, acc[cell], rows, B.n)
        nul = null_summary(pc, pdo, SEED)
    for cell in CELLS:
        c = summ[cell]
        if nul is not None:
            c["checks"] = judge_cell(c["base"], c["stress"]["10 bps"]["net"], nul, cell, len(c["years_held"]))
            c["PASS"] = bool(all(c["checks"].values()))
        c["gate70"] = gate70(c, ref, nul)
    return {"variant": post_mode, "cells": summ, "null": nul}, SimpleNamespace(legs=L, cell_legs=legs, runs=runs, series=series, side_x=side_x)


def sub_run(W, L, run, lo, hi):
    """the same cell-run with the position table cut to the positions of the rebalances that EXIT in [lo, hi] (a sub-period: positions are counted by exit date, as the stretches are; the daily series keeps every row - the statistics cut it by date)"""
    p = run.pos
    if p is None or not len(p.rec):
        return SimpleNamespace(x=run.x, cnt=run.cnt, n_pos=0, n_units=0, pos=SimpleNamespace(pnl=np.zeros(0)))
    dx = np.asarray(W.days)[[L.recs[int(i)].x for i in p.rec]]
    m = (dx >= np.datetime64(lo)) & (dx <= np.datetime64(hi))
    return SimpleNamespace(x=run.x, cnt=run.cnt, n_pos=int(m.sum()), n_units=len({int(i) for i in p.rec[m]}), pos=SimpleNamespace(pnl=np.asarray(p.pnl, float)[m]))


# ------------------------------------------------------------------ the hand audit's rows (f) / [A10]: every contributor and every flagged name-rank with its two share facts, their filings and the split factor
def dstr(d):
    """a day number -> 'YYYY-MM-DD'"""
    return str(np.datetime64(int(d), "D"))


def group_key(W, r, cell, col):
    """[A14] the GROUP of a name-rank: the symbol and the accession numbers of the two facts behind its score, 'symbol|accn_now|accn_prior' - every rank that uses the same two filings has the same key, so one audit row covers them all; '' where the name has no pair at that rank"""
    ni = W.ni
    sc = score_rank(W, r)[cell]
    sg, pg = int(sc.sg[col]), int(sc.pg[col])
    return f"{W.syms[col]}|{ni.E_accn[sg]}|{ni.E_accn[pg]}" if sg >= 0 and pg >= 0 else ""


def fact_fields(W, r, cell, col):
    """the two share facts behind one name's score at the rank close r: the NEWER value S(r) and the OLDER S' with their as-of dates, FIRST filed dates, accession numbers and forms, the concept they come from, the split factor F on each as-of date, the score, the composite twin's
    score and the flags, and the [A14] group (symbol + the two accession numbers) - the columns of the hand audit's files (f) / [A10]; blank where the name has no pair at that rank"""
    ni = W.ni
    sc = score_rank(W, r)[cell]
    sg, pg = int(sc.sg[col]), int(sc.pg[col])
    j = int(ni.cik_ix[col])
    out = {"rank_date": f"{W.days[r]:%Y-%m-%d}", "cik": str(ni.fx.ciks[j]) if j >= 0 else "", "concept": CONCEPTS[0 if sg < ni.dei.n else 1] if sg >= 0 else "", "iss": float(sc.iss[col]), "iota": float(sc.iota[col]),
           "flag_over_ln1.5": bool(sc.flag10[col]), "straddles_a_split": bool(sc.straddle[col]), "window_rests_on_F_alone": bool(sc.f_alone[col])}
    for tag, g, fv in (("now", sg, sc.fa[col]), ("prior", pg, sc.fap[col])):
        ok = g >= 0
        out.update({f"shares_{tag}": float(ni.E_val[g]) if ok else float("nan"), f"asof_{tag}": dstr(ni.E_end[g]) if ok else "", f"first_filed_{tag}": dstr(ni.E_f1[g]) if ok else "", f"accn_{tag}": str(ni.E_accn[g]) if ok else "",
                    f"form_{tag}": str(ni.E_form[g]) if ok else "", f"F_{tag}": float(fv) if ok else float("nan")})
    out["group"] = group_key(W, r, cell, col)
    return out


def ni_candidate_rows(W, L, cell, run, tbis_df, status, n=AUDIT_N):
    """the n largest single-name contributors of a cell for the hand audit (r17_resmom.rm_candidate_rows' rows: the largest GAINS with the fill date - the key netiss_audit.csv uses -, exit, side, $, the score, the split factor's ratio across the hold, the largest raw overnight move,
    TBIS's rows, the asset status, the hygiene reasons, the dividends; its two formation-window moves are RESMOM's and are left out) + this family's: the rank date, the concept and the two share facts with their filings and the split factor on each as-of date (fact_fields)"""
    rows = M17.rm_candidate_rows(W, L, cell, run, tbis_df, status, n)
    p = run.pos
    if not rows:
        return rows
    sel = np.argsort(-np.asarray(p.pnl, float), kind="stable")[:n]
    for row, i in zip(rows, sel):
        rec, col = L.recs[int(p.rec[i])], int(p.col[i])
        for k_ in ("raw_move_formation", "adj_move_formation"):
            row.pop(k_, None)
        row.update(fact_fields(W, rec.r, cell, col))
    return rows


def picks_by_name_month(L):
    """the REGISTERED picks of a leg by name-month: {(fill row, World column): ['N12/long', 'N24/short', ...]} - the cells' ISS picks (the composite twin's picks, the deciles and the null's draws are not picks)"""
    out = defaultdict(list)
    for rec in L.recs:
        for c in CELLS:
            cc = rec.cell[c]
            if not cc.traded:
                continue
            cols = rec.pool[cc.idx]
            for sd, sel in (("long", cc.long), ("short", cc.short)):
                for j in cols[sel]:
                    out[(rec.f, int(j))].append(f"{c}/{sd}")
    return out


def a10_rows(W, ranks, L):
    """[A10] every scored name-rank above |ISS| > ln(1.5) among the universe names of each rank, per cell, with the key of the audit file (symbol + the FILL date), [A14] whether it is PICKED - the cell / side of every pick of that name-month in the registered leg L, either side and either cell
    ('N12/short, N24/short'; blank when it is not picked) - and fact_fields (the group among them): ALL of them are listed, for information, in netiss_a10_flags.csv; the hand audit (f) covers the picked ones, grouped by their two filings (never a filter)"""
    pk = picks_by_name_month(L)
    rows = []
    for r, f, x in ranks:
        uni = np.flatnonzero(W.U[f])
        sc_all = score_rank(W, r)
        for cell in CELLS:
            for col in uni[sc_all[cell].flag10[uni]]:
                rows.append({"cell": cell, "symbol": str(W.syms[col]), "date": f"{W.days[f]:%Y-%m-%d}", "picked": ", ".join(pk.get((f, int(col)), [])), **fact_fields(W, r, cell, int(col))})
    return rows


def fill_ranks(W):
    """[(rank row, fill row)] of every rebalance the builders can use (a full 252-session window before the rank): the rows a group can be found on"""
    r_all, f_all, _x = M17.rm_schedule(W.days)
    return [(int(r), int(f)) for r, f in zip(r_all, f_all) if r >= M17.SPEC["win"] - 1]


def name_month_keys(W, f, col):
    """[A14] the group keys of one name-month (fill row f, World column col): one per cell in which the name has a pair at the rank before f; empty when f is not the fill session of a rebalance the builders use (a mistyped date - apply_audit's own check says so)"""
    if (f - 1, f) not in set(fill_ranks(W)):
        return set()
    return {k for k in (group_key(W, f - 1, c, col) for c in CELLS) if k}


def group_members(W, col, keys):
    """[A14] the fill rows of every name-month of the World column `col` whose group, in either cell, is one of `keys` - one scan over the rebalances: 'every rank that uses the same two filings'"""
    return [f for r, f in fill_ranks(W) if any(group_key(W, r, c, col) in keys for c in CELLS)]


def audit_keys(W, audit):
    """the group keys the audit file's rows cover (every row, keep or data_event): the union of their name-months' keys. CHOICE (the cell column of a row stays a label, as it always was - a data event belongs to the name-month): a row covers the name-month's group in EACH cell where it has a pair"""
    out = set()
    if audit is None:
        return out
    ci = pd.Index(W.syms).get_indexer(audit["symbol"])
    di = W.days.get_indexer(pd.DatetimeIndex(audit["date"]))
    for c_, d_ in zip(ci.tolist(), di.tolist()):
        if c_ >= 0 and d_ >= 0:
            out |= name_month_keys(W, d_, c_)
    return out


def audit_status(W, cands, a10, audit):
    """the hand audit's bookkeeping [A14], REPORTED only (the harness never decides (f)). An audit row covers its own name-month AND every other name-month that uses the same two filings (the same group, 'symbol|accn_now|accn_prior', in either cell). Per cell: listed / audited = the listed
    top-50 contributors and how many are covered (a row of the same symbol + fill date, or of their group), groups = the distinct groups among them; a10_flagged = the [A10] flagged name-ranks (all of them are in netiss_a10_flags.csv), a10_picked those of them that are PICKED, a10_listed /
    a10_audited the distinct picked GROUPS and how many are covered (a group is covered when a row covers it or covers any name-month of it) and the completeness flags -> {cell: {listed, audited, audit_complete, groups, a10_flagged, a10_picked, a10_listed, a10_audited, a10_complete}}"""
    have = set() if audit is None else set(zip(audit["symbol"], audit["date"].dt.strftime("%Y-%m-%d")))
    cov = audit_keys(W, audit)
    out = {}
    for cell in CELLS:
        rows = cands.get(cell, [])
        n = sum(((r["symbol"], r["date"]) in have) or (r.get("group", "") != "" and r["group"] in cov) for r in rows)
        flagged = [r for r in a10 if r["cell"] == cell]
        members = defaultdict(list)
        for r in flagged:
            members[r.get("group") or f"{r['symbol']}|{r['date']}"].append((r["symbol"], r["date"]))
        pg = {(r.get("group") or f"{r['symbol']}|{r['date']}") for r in flagged if r.get("picked")}
        n_a = sum((g in cov) or any(m in have for m in members[g]) for g in pg)
        out[cell] = {"listed": len(rows), "audited": int(n), "audit_complete": bool(len(rows) > 0 and n == len(rows)), "groups": len({r["group"] for r in rows if r.get("group")}), "a10_flagged": len(flagged),
                     "a10_picked": int(sum(1 for r in flagged if r.get("picked"))), "a10_listed": int(len(pg)), "a10_audited": int(n_a), "a10_complete": bool(n_a == len(pg))}
    return out


# ------------------------------------------------------------------ turnover, persistence, dividends, [D2] counts
def ni_turnover(L, cell):
    """turnover and PERSISTENCE per rebalance: the share of each side's names that were not on the same side at the previous traded rebalance (the registered convention charges every position its entry AND exit every month - a name that stays pays it again; the estimate of what
    that overstates, if only the names that change were traded, is 2 x 5 bps x $4,000 per retained name-month), and the score's persistence = the share of the PREVIOUS rebalance's side that is still on the same side now (a name that is no longer scored or eligible has left the tail).
    Reported, never judged"""
    prev, rows = None, []
    for rec in L.recs:
        cc = rec.cell[cell]
        if not cc.traded:
            prev = None
            continue
        lg, sh = set(rec.pool[cc.idx[cc.long]].tolist()), set(rec.pool[cc.idx[cc.short]].tolist())
        if prev is not None:
            rows.append((1.0 - len(lg & prev[0]) / len(lg), 1.0 - len(sh & prev[1]) / len(sh), len(lg & prev[0]) + len(sh & prev[1]), len(lg & prev[0]) / len(prev[0]), len(sh & prev[1]) / len(prev[1])))
        prev = (lg, sh)
    traded = sum(rec.cell[cell].traded for rec in L.recs)
    if not rows:
        return {"traded_rebalances": int(traded), "transitions": 0}
    a = np.array(rows)
    return {"traded_rebalances": int(traded), "transitions": len(rows), "long_replaced_mean": float(a[:, 0].mean()), "short_replaced_mean": float(a[:, 1].mean()), "replaced_mean": float(a[:, :2].mean()),
            "replaced_median": float(np.median(a[:, :2].mean(axis=1))), "replaced_min": float(a[:, :2].mean(axis=1).min()), "replaced_max": float(a[:, :2].mean(axis=1).max()),
            "persistence_long_mean": float(a[:, 3].mean()), "persistence_short_mean": float(a[:, 4].mean()), "persistence_mean": float(a[:, 3:5].mean()),
            "cost_saved_if_only_changes_traded_usd_estimate": float(a[:, 2].sum() * M17.SPEC["slot"] * 2 * COST_BPS * 1e-4)}


def ni_div_flows(L, cell):
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


def ni_spin_counts(L, cell):
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


# ------------------------------------------------------------------ the reports (never a pass route)
def reports(W, B, S12, ref, rows, obj, summ, tbis_df, status, legs_meta, srows, post_mode="remove"):
    """everything the prereg's DIAGNOSTICS paragraph and the addenda list, for the registered reading: the realised beta to ES on #463's drawdown days and all WF days FIRST ([A6]'s credit rule is in summ), each cell's $ inside every qualifying #463 drawdown and inside every drawdown
    episode of the REFERENCE book ([A12]: with the cell's P&L inside each and which episodes it helps), its place on the MDL map, the correlation of its daily P&L with RES's registered line and the overlap of its picks with RESMOM's (issuers are often recent winners), the score's
    persistence and the turnover, the concept used per rank, the 20 largest name-month gains, the dividend flows, survivorship. The deciles [A5], the composite twin [A7] and the ES-hedged twin [A6] are in summ"""
    L, lo, hi = obj.legs, WF0, PRE_END
    rep = {"beta_to_es": {}, "episodes": {}, "ref_episodes": {}, "map_point": {}, "corr_with_legs": {}, "corr_with_res": {}, "pick_overlap_with_res": {}, "top20_gains": {}, "months": {}, "turnover": {}, "survivorship": {}, "dividend_flows": {}, "concept_by_rank": {}}
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
        cands[cell] = ni_candidate_rows(W, L, cell, obj.runs[cell], tbis_df, status)
        rep["top20_gains"][cell] = cands[cell][:20]
        rep["months"][cell] = M17.month_nets(B, xB, lo, hi)
        rep["turnover"][cell] = ni_turnover(L, cell)
        rep["survivorship"][cell] = D15.survivorship(W, obj.cell_legs[cell], status)
        rep["dividend_flows"][cell] = ni_div_flows(L, cell)
        rep["concept_by_rank"][cell] = [{"rank": r_["rank"], "dei": r_["cells"][cell]["dei"], "gaap": r_["cells"][cell]["gaap"], "fallback_to_gaap": r_["cells"][cell]["fallback_to_gaap"]} for r_ in srows]
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
    return (f"{cell:<3} rebalances {s['n_units']:>4,} positions {s['n_pos']:>6,} net ${s['net']:>11,.0f} (${c['usd_year']:>8,.0f} a year) ROC@30k {s['roc']:>8.1f} / {dd5_txt(c['dd5'])} Sortino {s['sortino']:>6.2f} maxDD ${s['max_dd']:>9,.0f} | DO {q['DO']:>+7.3f} rho_dd {q['rho_dd']:>+6.3f}")


def print_cells(res, audit_st=None):
    nul = res["null"]
    print(f"  null: RANDOM NAMES from each rebalance's eligible SCORED pool, registered ({nul['draws']} draws, seed {nul['seed']}, the MAX over the 2 cells): ROC@30k p5 {nul['roc_max']['p5']:.1f} p50 {nul['roc_max']['p50']:.1f} p95 {nul['roc_max']['p95']:.1f}; each cell alone p50 / p95: "
          + ", ".join(f"{c} {nul['by_cell'][c]['p50']:.1f} / {nul['by_cell'][c]['p95']:.1f}" for c in CELLS))
    for cell in CELLS:
        c = res["cells"][cell]
        fails = [k for k, v in c["checks"].items() if not v]
        s2 = ", ".join(f"{k} net ${v['net']:,.0f}" for k, v in c["stress"].items())
        print("  " + row(cell, c))
        print(f"        stress: {s2}; by July-June year: " + " ".join(f"{y}-{(y + 1) % 100:02d}:{v:+,.0f}" for y, v in c["base"]["by_year"].items()) + f"; years with a position: {len(c['years_held'])}")
        b = c["beta"]
        print(f"        realised beta to ES [A6] (the cell's daily $ P&L on ES's daily return per $ of one side's notional ${b['side_notional']:,.0f}): #463's DD days {b['beta_dd_days']:+.3f}, all WF days {b['beta_all_days']:+.3f} - the credit cap is |beta| <= {b['cap']:.2f} on BOTH -> "
              + ("the drawdown-day profile may be credited" if b["within_cap"] else "NOT CREDITED: the profile is reported, no incremental A2 pass, no gate, no line"))
        a2 = c["A2"]
        if a2.get("at_half_c"):
            rf, pl = a2["reference"], a2["plain_463"]
            a2s = (f"c x{a2['c']:.4g} (cell daily std ${a2['std_cell']:,.0f} vs #463's ${a2['std_book']:,.0f} over {a2['window'][0]} .. {a2['window'][1]}): REFERENCE + c x cell ROC@30k {a2['roc']:.2f} / {dd5_txt(a2['dd5'])} (${a2['usd_year']:,.0f} a year) Sortino {a2['sortino']:.3f} against the reference's "
                   f"{rf['roc']:.2f} / {dd5_txt(rf['dd5'])} (${rf['usd_year']:,.0f} a year) / {rf['sortino']:.3f} -> " + ("INCREMENTAL PASS (both above): a forward BOOK shadow line opens, MANAGER #70's gate follows" if a2["incremental_credit"] else
                                                                                                    ("incremental numbers pass but the beta rule refuses the credit: no line" if a2["incremental_pass"] else "no incremental pass (it needs both above)"))
                   + f"; at 0.5c ROC {a2['at_half_c']['roc']:.2f} / {dd5_txt(a2['at_half_c']['dd5'])} (${a2['at_half_c']['usd_year']:,.0f} a year) / Sortino {a2['at_half_c']['sortino']:.3f}, at 2c ROC {a2['at_double_c']['roc']:.2f} / {dd5_txt(a2['at_double_c']['dd5'])} (${a2['at_double_c']['usd_year']:,.0f} a year) / Sortino "
                   f"{a2['at_double_c']['sortino']:.3f}; the plain #463 + c x cell book (a reported row): ROC {pl['roc']:.2f} / {dd5_txt(pl['dd5'])} (${pl.get('usd_year', float('nan')):,.0f} a year) / Sortino {pl['sortino']:.3f}")
        else:
            a2s = f"{a2.get('error', 'no c')} -> no incremental pass"
        au = None if audit_st is None else audit_st[cell]
        print(f"        Stage A (a)-(e) {'PASS' if c['PASS'] else 'FAIL (' + ', '.join(fails) + ')'}" + ("" if au is None else
              f"; audit [A14] {au['audited']}/{au['listed']} of the top-{AUDIT_N} listed ({au['groups']} groups), {au['a10_audited']}/{au['a10_listed']} of the picked [A10] groups ({au['a10_picked']} picked of {au['a10_flagged']} flagged name-ranks) -> "
              f"top-50 {'COMPLETE' if au['audit_complete'] else 'incomplete'}, picked groups {'COMPLETE' if au['a10_complete'] else 'incomplete'}"))
        print(f"        A2 (a report) [X1]: {a2s}")
        g = c["gate70"]
        print(f"        #70 gate basis [X1] (the REFERENCE book's {g['episodes']} drawdown episodes, {g['dd_days']} DD days): the cell's DO {g['DO']:+.3f}, rho_dd {g['rho_dd']:+.3f}" + (
              f"; its null's DO (random names, the MAX over the 2 cells) p5 {g['null_do_p5']:+.3f} p50 {g['null_do_p50']:+.3f} p95 {g['null_do_p95']:+.3f} -> the cell's DO is {'above' if g['DO_above_null_p95'] else 'not above'} the null's p95" if "null_do_p95" in g else "")
              + (f"; its P&L inside those episodes ${sum(g['episode_pnl']):,.0f} (${g['pnl_without_best_episode']:,.0f} without the best one; it helps {g['episodes_helped']} of {len(g['episode_pnl'])})" if g.get("episode_pnl") else "")
              + ("" if g["credited"] else "; the beta rule: NOT credited"))


def print_deciles(res):
    """[A5] the ten ISS deciles of each cell as equal-weight long-only baskets: each decile's WF net, ROC @ $30k and dollars a year, and the same for its spread over ES (1 = the biggest shrinkers .. 10 = the biggest issuers)"""
    print("ISS DECILES [A5] - the scored universe cut into ten equal-count deciles at every rank (1 = the lowest ISS, the biggest shrinkers .. 10 = the highest, the biggest issuers), each an equal-weight LONG-ONLY basket at $4,000 a name marked like the cells; "
          "the spread = the basket less an ES position of the same notional (reported, never a pass route)")
    for c in CELLS:
        d = res["cells"][c]["deciles"]
        print(f"  {c} ({d['ranks_cut']} ranks cut) decile: name-months | net $ / ROC@30k / $ a year | spread over ES net $ / ROC@30k / $ a year")
        for q in d["deciles"]:
            print(f"    {q['decile']:>2}: {q['name_months']:>7,} | {q['net']:>+11,.0f} / {q['roc']:>8.1f} / {q['usd_year']:>+9,.0f} | {q['spread_net']:>+11,.0f} / {q['spread_roc']:>8.1f} / {q['spread_usd_year']:>+9,.0f}")


def print_twins(res):
    """[A7] the composite-issuance twin and [A6] the ES-hedged twin of each cell, beside the cell: net $, ROC @ $30k, $ a year, the picks' overlap, the hedge ratios used, the hedged twin's realised beta"""
    print("TWINS - REPORTED beside each cell, never a pass route")
    for c in CELLS:
        x = res["cells"][c]
        k, t, h = x["base"], x["composite"], x["hedged"]
        print(f"  {c}: the cell net ${k['net']:,.0f} ROC@30k {k['roc']:.1f} (${x['usd_year']:,.0f} a year); [A7] composite-issuance twin (iota = ISS - ln(total return / price return) over the window; the same picks rule) net ${t['base']['net']:,.0f} ROC@30k "
              f"{t['base']['roc']:.1f} (${t['usd_year']:,.0f} a year), the twin's picks share {t['pick_overlap_with_iss_picks'].get('long', float('nan')):.0%} of the longs / {t['pick_overlap_with_iss_picks'].get('short', float('nan')):.0%} of the shorts with the cell's "
              f"({t['scores_with_window_before_the_calendar']:,} scores rest on F alone); [A6] ES-hedged twin (an ES overlay sized ex ante by the OLS beta of the cell's own daily P&L on ES over the 252 sessions before each rank, zero before 252 sessions exist; "
              f"{h['ratios_nonzero']} of {h['ratios']} rebalances hedged) net ${h['base']['net']:,.0f} ROC@30k {h['base']['roc']:.1f} (${h['usd_year']:,.0f} a year), its realised beta DD days {h['beta']['beta_dd_days']:+.3f} / all days {h['beta']['beta_all_days']:+.3f}")


COUNT_KEYS = ("universe", "short_history", "no_es_pairs", "no_fill") + tuple(f"pre_{h}" for h in HYG) + tuple(f"old_{h}" for h in HYG[1:]) + tuple(f"post_{h}" for h in HYG) + ("post_spin", "post_calendar_split", "audit", "pool", "kept_naive")
KEPT_KEYS = tuple(f"kept_{h}" for h in HYG) + ("kept_flagged",)        # [A18] the names flagged inside the hold that STAY (the judged reading): not removal reasons, printed apart


def print_counts(label, cnt):
    keys = [k for k in COUNT_KEYS if any(k in c for c in cnt.values())]
    print(f"  {label} name-removals by fill year, each name counted once at its FIRST reason (columns: " + " / ".join(keys) + ")")
    for y, c in sorted(cnt.items()):
        print(f"    {y}: " + " ".join(f"{c.get(k, 0)}" for k in keys) + f"   [rebalances {c.get('rebalances', 0)}, unresolved {c.get('unresolved', 0)}, warm-up {c.get('warmup', 0)}, empty {c.get('empty', 0)}]")
    if any(c.get(k, 0) for c in cnt.values() for k in KEPT_KEYS):
        print(f"  {label}: names flagged inside the hold that STAY in the pool on the split-safe path [A18], by fill year (columns: " + " / ".join(KEPT_KEYS) + ")")
        for y, c in sorted(cnt.items()):
            print(f"    {y}: " + " ".join(f"{c.get(k, 0)}" for k in KEPT_KEYS))


def print_scored(label, cnt):
    """the scored names and the sides by fill year: per cell the pool's scored names (summed over the year's rebalances), the pool names with no score by the first reason, and the rebalances that trade the top 50 / the third / nothing"""
    print(f"  {label} scored names by fill year (per cell: scored / pool names with no score; rebalances trading the top {M17.SPEC['n_side']} a side | the top-bottom third | nothing)")
    for y, c in sorted(cnt.items()):
        if c.get("rebalances", 0):
            print(f"    {y}: " + "; ".join(f"{cl} {c.get(f'scored_{cl}', 0):,} / {c.get(f'no_score_{cl}', 0):,}, {c.get(f'mode_{cl}_top', 0)} | {c.get(f'mode_{cl}_third', 0)} | {c.get(f'mode_{cl}_none', 0)}" for cl in CELLS))
    print(f"  {label} the pool's no-score names by the first reason, by fill year (" + ", ".join(REASONS[1:]) + "):")
    for cl in CELLS:
        for y, c in sorted(cnt.items()):
            if c.get("rebalances", 0):
                print(f"    {cl} {y}: " + " ".join(f"{c.get(f'ns_{cl}_{rs}', 0)}" for rs in REASONS[1:]))


def print_second_classes(sm):
    """[A13] ONE SHARE CLASS PER FIRM, COUNTED (a counts-only leg is enough): per rank, per cell, the pool names with a score -> the second share classes taken out -> the scored names left; the same by fill year; the CIKs it fires on with their symbols and, per cell, how many name-ranks each
    symbol was dropped and how many it was kept over a dropped class. Counts and the symbols of the CIKs involved - no share count, no ISS value"""
    print("  [A13] ONE SHARE CLASS PER FIRM: among the pool names WITH a score (per cell, after every removal) the names that share a CIK are classes of one firm; only the class with the larger mean raw dollar volume of the 20 sessions before the fill keeps its score (a tie: the lower symbol), "
          "the others get the no-score reason 'second share class' - out of the picks, the deciles, the composite twin and the null's pool")
    print("  [A13] per rank (rank date: pool names with a score -> second share classes taken out -> scored names left; N12 | N24):")
    for r_ in sm["ranks"]:
        print(f"    {r_['rank']}: " + " | ".join(f"{r_['cells'][c]['pool_scored']} -> {r_['cells'][c]['second']} -> {r_['cells'][c]['scored']}" for c in CELLS))
    for c in CELLS:
        by = sm["by_year"][c]
        print(f"  [A13] {c} second-share-class name-ranks taken out, by fill year: " + (", ".join(f"{y}: {n}" for y, n in by.items()) if by else "none") + f" (total {sm['total'][c]:,})")
    print(f"  [A13] the {len(sm['ciks'])} CIKs it fires on (per symbol and cell, name-ranks dropped / name-ranks kept over a dropped class; {CELLS[0]} | {CELLS[1]}):")
    for cik, syms in sm["ciks"].items():
        print(f"    {cik}: " + "; ".join(f"{s} " + " | ".join(f"{d.get(c, {}).get('dropped', 0)} / {d.get(c, {}).get('kept', 0)}" for c in CELLS) for s, d in sorted(syms.items())))
    print("  [A13] groups decided with an undefined dollar volume (none on the real universe: a name needs all 20 sessions to be in it): " + ", ".join(f"{c} {sm['nan_dv'][c]}" for c in CELLS))


def print_spin_picks(spin):
    for reading, per in spin.items():
        for cell in CELLS:
            c = per[cell]
            print(f"  {reading} [D2] {cell} picks (long / short): positions {c['long']['positions']:,} / {c['short']['positions']:,}; window (a return left out of the name's own series) {c['long']['window_positions']:,} / "
                  f"{c['short']['window_positions']:,} positions ({c['long']['window_sessions']:,} / {c['short']['window_sessions']:,} sessions left out); hold (a spin-off / stock-dividend ex-date inside it) {c['long']['hold_positions']:,} / {c['short']['hold_positions']:,}")


def print_reports(rep, summ):
    b = rep["beta_to_es"]
    print("  realised beta to ES (the cell's daily $ P&L on ES's daily return, $ per 1% ES move; #463's DD days / DD weeks / all WF days) - FIRST: " + "; ".join(
        f"{c} {b[c]['DD days']['usd_per_1pct_es']:+,.0f} / {b[c]['DD weeks (every day of them)']['usd_per_1pct_es']:+,.0f} / {b[c]['all WF days']['usd_per_1pct_es']:+,.0f}" for c in CELLS))
    for c in CELLS:
        e = rep["episodes"][c]
        print(f"  {c}: P&L inside #463's {len(e)} qualifying drawdowns: net ${sum(x['cell_pnl'] for x in e):,.0f} over {sum(x['dd_days'] for x in e)} DD days (#463's ${sum(x['book_pnl'] for x in e):,.0f}); "
              f"MDL map point: ROC@30k {rep['map_point'][c]['standalone_roc_30k']:.1f}, rho_dd {rep['map_point'][c]['rho_dd']:+.3f}, DO {rep['map_point'][c]['DO']:+.3f}")
    for c in CELLS:
        ov, t = rep["pick_overlap_with_res"][c], rep["turnover"][c]
        print(f"  {c} against RES: daily P&L correlation {rep['corr_with_res'][c]:+.3f} (WF days; RES's registered line); pick overlap over {ov['rebalances']} rebalances - longs that are RES longs {ov['long_in_res_long']:.0%} / RES shorts {ov['long_in_res_short']:.0%}, "
              f"shorts that are RES shorts {ov['short_in_res_short']:.0%} / RES longs {ov['short_in_res_long']:.0%}")
        if t.get("transitions"):
            print(f"  {c} persistence: {t['persistence_mean']:.0%} of the names are still in the same tail one rebalance later (long tail {t['persistence_long_mean']:.0%}, short tail {t['persistence_short_mean']:.0%}); turnover: {t['replaced_mean']:.0%} of the names replaced per rebalance on average "
                  f"(median {t['replaced_median']:.0%}, range {t['replaced_min']:.0%} .. {t['replaced_max']:.0%}); if only the changes were traded: ${t['cost_saved_if_only_changes_traded_usd_estimate']:,.0f} less in total (estimate, not judged)")
        cb = rep["concept_by_rank"][c]
        print(f"  {c} concept used (cover page / balance sheet, of which the cover-page-to-balance-sheet fallbacks) over the {len(cb)} ranks: {sum(x['dei'] for x in cb):,} / {sum(x['gaap'] for x in cb):,} ({sum(x['fallback_to_gaap'] for x in cb):,}); "
              "per rank in the Stage A file and in the lines above")
    for c in CELLS:
        sd = summ[c]["sides"]
        fl = rep["dividend_flows"][c]
        print(f"  {c} dividends [R1] inside the registered picks: longs received ${fl['long_received']:,.0f} on {fl['long_positions_with_a_dividend']:,} positions, shorts paid ${fl['short_paid']:,.0f} on {fl['short_positions_with_a_dividend']:,}")
        z = sd.get(M17.R2_SIDE)
        if z is not None:
            print(f"  {c} short leg [R2]: net ${sd['short side only']['net']:,.0f} with a name that stops printing exiting at its last close (the base); ${z['net']:,.0f} with such names valued at zero "
                  f"({summ[c]['short_stopped']['positions']} of {summ[c]['short_stopped']['short_positions']:,} short positions); the whole cell with it ${summ[c]['extra'][M17.R2_CELL]['net']:,.0f} (base ${summ[c]['base']['net']:,.0f})")
        print(f"  {c} sides: long only net ${sd['long side only']['net']:,.0f}, short only net ${sd['short side only']['net']:,.0f}; borrow / survivorship rows: " + ", ".join(f"{k} ${v['net']:,.0f}" for k, v in summ[c]["extra"].items()))
        sv = rep["survivorship"][c]
        print(f"  {c} survivorship: {sv['long_in_inactive_names']:,} of {sv['long_positions']:,} long positions ({sv['share_long_in_inactive_names']:.1%}) are in names the asset list calls inactive")
        for x in rep["top20_gains"][c][:3]:
            print(f"      {c} top gain {x['rank']}: {x['symbol']} {x['side']} filled {x['date']} -> {x['exit']} ${x['pnl']:,.0f} ISS {x['iss']:+.3f} ({x['concept']}: {x['shares_prior']:,.0f} on {x['asof_prior']} -> {x['shares_now']:,.0f} on {x['asof_now']}, F {x['F_prior']:.4g} -> {x['F_now']:.4g}) (the 20 largest are in the Stage A file)")


DIAG_LW, DIAG_CW = 66, 32


def diag_line(label, vals):
    return f"  {label:<{DIAG_LW}}" + "".join(f"{v:>{DIAG_CW}}" for v in vals)


def print_diagnostics(res, rep, ref):
    """[X2] DEEPER DIAGNOSTICS of the registered reading, N12 and N24 side by side: the cost curve at 0 / 5 / 10 / 20 bps a side, a row per July-June year, the two regime halves, a row per drawdown episode of the REFERENCE book (the cell's P&L inside it, [A12]), the LONG and SHORT sides apart, and
    the #70 gate's basis; the dollars a year beside every ROC. CHOICE: 'a drawdown episode of the reference' = a QUALIFYING episode (MDL r1's rule: at least 1/3 as deep as the deepest - the episodes the #70 gate's DO is measured on). None of it is a pass route"""
    cells = res["cells"]
    each = lambda f: [f(cells[c], c) for c in CELLS]
    nr = lambda s: f"{s['net']:+,.0f} / {s['roc']:.1f} / {per_year(s['net'], s['years']):+,.0f}"
    print("DIAGNOSTICS [X2] - the registered reading, the WF stretch, N12 and N24 side by side; none of this is a pass route (cells: net $ / ROC@30k / $ a year)")
    print(diag_line("", list(CELLS)))
    print("  COST CURVE - the cost a side")
    for lab, get in (("0 bps", lambda c: c["cost0"]), ("5 bps (the base)", lambda c: c["base"]), ("10 bps", lambda c: c["stress"]["10 bps"]), ("20 bps", lambda c: c["stress"]["20 bps"])):
        print(diag_line(f"  {lab}", each(lambda c, k: nr(get(c)))))
    print("  BY JULY-JUNE YEAR - net $ of the daily series (long side | short side)")
    for y in YEARS:
        print(diag_line(f"  {y}-{(y + 1) % 100:02d}", each(lambda c, k: f"{c['base']['by_year'][y]:+,.0f} ({c['sides']['long side only']['by_year'][y]:+,.0f} | {c['sides']['short side only']['by_year'][y]:+,.0f})")))
    print("  THE TWO REGIME HALVES - then the positions that exited in the half")
    for lab, _a, _b in SUBPERIODS:
        print(diag_line(f"  {lab}", each(lambda c, k: nr(c["sub"][lab]))))
        print(diag_line("    positions", each(lambda c, k: f"{c['sub'][lab]['n_pos']:,}")))
    g = ref.structure
    print(f"  THE REFERENCE BOOK'S DRAWDOWN EPISODES [A12] ({g['episodes']} qualifying, {g['days']} DD days; MDL r1's rule) - the cell's P&L inside each (the DD days: the day after the peak .. the trough) and the episodes it helps")
    for q, e in enumerate(rep["ref_episodes"][CELLS[0]]):
        print(diag_line(f"  {e['first_dd_day']} .. {e['trough']} ${e['depth']:,.0f} ({e['dd_days']} d, ref {e['book_pnl']:+,.0f})", [f"{rep['ref_episodes'][c][q]['cell_pnl']:+,.0f}" for c in CELLS]))
    print(diag_line("  all the episodes (the cell's P&L over the DD days)", [f"{sum(x['cell_pnl'] for x in rep['ref_episodes'][c]):+,.0f}" for c in CELLS]))
    print(diag_line("  the episodes the cell helps (cell P&L > 0) of the total", [f"{sum(1 for x in rep['ref_episodes'][c] if x['cell_pnl'] > 0)} of {len(rep['ref_episodes'][c])}" for c in CELLS]))
    print("  THE LONG AND SHORT SIDES APART (net $ / ROC@30k / maxDD)")
    for lab in ("long side only", "short side only"):
        print(diag_line(f"  {lab}", each(lambda c, k: f"{c['sides'][lab]['net']:+,.0f} / {c['sides'][lab]['roc']:.1f} / {c['sides'][lab]['max_dd']:,.0f}")))
    print(f"  #70 GATE BASIS - the cell's DO against the REFERENCE book's {g['episodes']} drawdown episodes / {g['days']} DD days, beside its random-name null's (the MAX over the 2 cells)")
    print(diag_line("  DO (cell P&L over the DD days / the reference's loss)", each(lambda c, k: f"{c['gate70']['DO']:+.3f}")))
    print(diag_line("  the null's DO p95", each(lambda c, k: f"{c['gate70']['null_do_p95']:+.3f}" if "null_do_p95" in c["gate70"] else "-")))
    print(diag_line("  the cell's DO above the null's p95", each(lambda c, k: ("yes" if c["gate70"]["DO_above_null_p95"] else "no") if "null_do_p95" in c["gate70"] else "-")))
    print(diag_line("  positive without the best episode", each(lambda c, k: ("yes" if c["gate70"]["positive_without_best_episode"] else "no") if "positive_without_best_episode" in c["gate70"] else "-")))
    print(diag_line("  credited by the beta rule [A6] (both betas within 0.20)", each(lambda c, k: "yes" if c["beta"]["within_cap"] else "no")))


# ------------------------------------------------------------------ the hand audit (f): read, apply, status
def read_audit(path=None):
    """OUT\\netiss_audit.csv (symbol, date, cell, verdict in {keep, data_event}, note) -> a frame, or None when there is no file yet. A data_event row removes that name-month from BOTH cells AND both nulls before anything is computed [(f)]. CHOICE: the date is the position's
    FILL date - exactly the 'date' of netiss_audit_candidates.csv and netiss_a10_flags.csv (r17_resmom's key); a data event belongs to the name-month, so a row covers both cells' listing of it. [A14] ONE ROW COVERS A GROUP: every other name-month that uses the same symbol and the
    same two filings (the 'group' column of the two lists) - a data_event row removes all of them (apply_audit), a keep row counts them all as audited (audit_status). Refuses a verdict / cell / date it cannot read (a mistyped row must not silently do nothing)"""
    p = path or os.path.join(OUT, "netiss_audit.csv")
    if not os.path.exists(p):
        return None
    df = pd.read_csv(p, dtype=str, keep_default_na=False)
    miss = [c for c in ("symbol", "date", "cell", "verdict") if c not in df.columns]
    if miss:
        refuse(f"refused: netiss_audit.csv lacks the column(s) {miss} (columns: symbol, date, cell, verdict, note) - nothing computed")
    df["symbol"], df["cell"], df["verdict"] = df["symbol"].str.strip(), df["cell"].str.strip().str.upper(), df["verdict"].str.strip().str.lower()
    df["date"] = pd.to_datetime(df["date"].str.strip(), errors="coerce")
    bad = df[~df["verdict"].isin(("keep", "data_event")) | ~df["cell"].isin(CELLS) | df["date"].isna() | (df["symbol"] == "")]
    if len(bad):
        refuse(f"refused: netiss_audit.csv line(s) {[int(i) + 2 for i in bad.index][:10]} have an unreadable date / symbol, a verdict outside keep | data_event, or a cell outside {list(CELLS)} (nothing computed)")
    return df


unused_audit_rows = M17.unused_audit_rows                                      # r17_resmom's: a data_event row that removed nothing (the name was not in that fill session's universe) is reported, so a wrong date cannot pass unnoticed


def apply_audit(W, audit):
    """the audit file's data_event rows put on the World as removals before anything is built: r17_resmom's own (the key is symbol + FILL date, the name-month leaves the pool - cells AND nulls; a row that matches no session or no name refuses) PLUS [A14]'s groups: a data_event row
    also removes every other name-month that uses the same two filings (the same group in either cell, group_members) - 'a data_event row for a group removes every name-month of that group'. Needs W.ni (attach_netiss first). -> {rows, keep, data_event, group_name_months = the name-months
    removed through a group beyond the rows' own}"""
    cnt = dict(M17.apply_audit(W, audit))
    extra = 0
    if audit is not None and cnt["data_event"]:
        ev = audit[audit["verdict"] == "data_event"]
        ci = pd.Index(W.syms).get_indexer(ev["symbol"]).tolist()
        di = W.days.get_indexer(pd.DatetimeIndex(ev["date"])).tolist()
        for c_, d_ in zip(ci, di):
            keys = name_month_keys(W, d_, c_)
            for f_ in (group_members(W, c_, keys) if keys else ()):
                if not W.aud1[f_, c_]:
                    W.aud1[f_, c_] = True
                    extra += 1
    cnt["group_name_months"] = extra
    return cnt


cut_checks = DV.cut_checks                                                   # r18_divrun's: nothing on / after the stage's cut in the World's sessions or the calendar's rows
div_mode = M17.div_mode                                                       # [R1] the cash dividends in / out of the daily return (the score and the composite twin read the same World arrays either way)


# ------------------------------------------------------------------ dryload: counts only
def nan_or(x, fmt):
    """a number in the format given, 'n/a' when it is not finite"""
    return format(x, fmt) if math.isfinite(x) else "n/a"


def scored_stats(L):
    """COUNTS over a leg's rebalances: per cell the scored names per rebalance (min / median / max, over the rebalances whose pool was not empty) and the rebalances by what they trade (top 50 / the thirds / nothing)"""
    out = {}
    for c in CELLS:
        ns = np.array([rec.cell[c].n for rec in L.recs if len(rec.pool)], int)
        out[c] = {"rebalances": int(len(L.recs)), "with_a_pool": int(len(ns)), "min": int(ns.min()) if len(ns) else 0, "median": float(np.median(ns)) if len(ns) else 0.0, "max": int(ns.max()) if len(ns) else 0,
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


def print_data_counts(mp, finfo, fx, W=None):
    """[A1] / [A8] COUNTS of the pinned files as read - the map, the flat file, the entries - and, when a World is given, the names it holds by their static map / CIK / foreign reason; no share count, no value of any kind"""
    mi, fi = mp.info, finfo
    print(f"[A1] / [A8] pinned files (each refused if its sha256 differs): facts {FILE_SHA['facts'][:16]}... + additions {FILE_SHA['facts_add'][:16]}... read as ONE table ({fi['files']['facts']:,} + {fi['files']['facts_add']:,} rows); "
          f"map {FILE_SHA['map'][:16]}... + additions {FILE_SHA['map_add'][:16]}... read as ONE map ({mi['base_rows']:,} + {mi['additions_rows']} rows)")
    print(f"  map: {mi['rows']:,} symbols by method {mi['by_method']}; usable rows {mi['usable_symbols']:,} on {mi['usable_ciks']:,} CIKs ({mi['ciks_with_two_or_more_symbols']} CIKs carry two or more symbols); "
          f"additions that superseded an unusable base row (by the base row's method): {mi['additions_superseding_unusable_base_rows']}")
    print(f"  facts: {fi['rows_read']:,} rows read; filed on / after the cut {fi['rows_filed_on_or_after_the_cut']:,} (the extract holds none); as-of date on / after the cut {fi['rows_end_on_or_after_the_cut']:,}; unreadable date {fi['rows_unreadable_date']:,}; unit not 'shares' {fi['rows_unit_not_shares']:,}; "
          f"another concept {fi['rows_other_concept']:,}; value missing {fi['rows_value_missing']:,}; kept {fi['rows']:,} by concept {fi['rows_by_concept']}; by form (the 20 largest) {fi['rows_by_form']}")
    for key, lab in (("dei", "cover page (dei)"), ("gaap", "balance sheet (us-gaap)"), ("wa_annual", "weighted-average basic shares, annual (a reported cross-check only)")):
        c = fx.info[key]
        print(f"  entries {lab}: {c['entries']:,} (cik, as-of date) pairs; ambiguous at the first filed date {c['ambiguous']:,}; as-of date after its own first filing {c['end_after_filed']:,}; value missing {c['value_missing']:,}; value not positive {c['value_not_positive']:,}; "
              f"a later filing carries another value {c['later_filing_carries_another_value']:,} (the first-filed value stands)")
    print(f"  CIKs with a share fact {fx.info['ciks']:,}; foreign filers (only 20-F / 40-F / 6-K forms) {fx.info['ciks_foreign_only']:,}; without a cover-page or balance-sheet entry {fx.info['ciks_without_a_score_concept_entry']:,}")
    if W is not None:
        st = Counter(REASONS[int(c)] for c in W.ni.static)
        print(f"  the {W.S:,} names ever in the universe by their static reason: " + ", ".join(f"{k} {v:,}" for k, v in sorted(st.items(), key=lambda kv: -kv[1])))


def dryload():
    """the WF inputs through every loader (cut at 2025-06-30) and COUNTS only: the pinned files as read, sessions, symbols, universe sizes, the rebalances and the pool / scored names per rebalance, the no-score reasons by rank and by year, the concept split, the [A10] flag count, the fallback
    months, the hygiene removals by reason (both readings), [A13]'s second share classes (per rank, by year, and the CIKs they fire on), TBIS rows matched, ES coverage. NO share count, ISS value, return, P&L or Stage A statistic is printed: the scores are computed in memory only to COUNT the names each rule
    removes, no unit path is built, and the only names listed are the symbols of the CIKs [A13] fires on"""
    prereg_ok()
    t0 = time.time()
    mp = load_map()
    d, finfo = load_facts(S.LB0)
    fx = build_facts(d)
    del d
    D = M17.load_data(S.LB0)
    nfull = len(D.syms)
    tbis = D15.load_tbis(S.LB0)
    es_frames, es_meta = D15.load_es(S.LB0)
    full_match = D15.tbis_array(D.days, D.syms, tbis)[1]
    cal, winfo = M17.wide_load(S.LB0, need=False, enforce=False)                              # CHOICE (r18's): the dryload counts on the calendar when it exists and REPORTS its sha status (only Stage A / B refuse an unregistered one)
    W = M17.build_world(D, S.LB0, es_frames, tbis, cal)
    D15.release(D)
    cut_checks(W, cal, S.LB0)
    ni = attach_netiss(W, fx, mp, cal)
    print(f"dryload: inputs ready ({time.time() - t0:.0f}s); every input cut to dates < {S.LB0:%Y-%m-%d}; ES masters {es_meta['raw']['filename']} / {es_meta['adj']['filename']}")
    wf = (W.days >= WF0) & (W.days <= PRE_END)
    print(f"sessions: {W.T:,} on the market calendar ({W.days[0]:%Y-%m-%d} .. {W.days[-1]:%Y-%m-%d}; the cache's first session is {CACHE_FIRST_SESSION:%Y-%m-%d}), {int(wf.sum()):,} inside the WF stretch; symbols: {nfull:,} in the cache after SIPORB's price / volume floor, {W.S:,} ever in the universe")
    usz, yrs = W.U.sum(axis=1), W.days.year.to_numpy()
    print("universe size per session by year (sessions with a universe: min / median / max): " + "; ".join(
        f"{y}: {int((m := (yrs == y) & (usz > 0)).sum())} sessions {int(usz[m].min())} / {int(np.median(usz[m]))} / {int(usz[m].max())}" for y in sorted(set(yrs)) if ((yrs == y) & (usz > 0)).any()))
    print_data_counts(mp, finfo, fx, W)
    print(f"  the calendar's start (the first date [A3]'s cross-check covers): {ni.cal_start if ni.cal_start is None else f'{ni.cal_start:%Y-%m-%d}'}")
    ranks = built_ranks(W, WF0, PRE_END)
    print_score_report(score_report(W, ranks, values=False), ni.cal_start, names=False)
    Lr, Lk = ni_build(W, WF0, PRE_END, JUDGED, units=False, counts_only=True), ni_build(W, WF0, PRE_END, "remove", units=False, counts_only=True)     # [A18] the judged reading and the leaky one beside it
    print_second_classes(second_class_summary(Lr, W))                                                # [A13] the second share classes: per rank, by year, the CIKs (counts and symbols only)
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
    print_scored_stats(LAB_J, Lr, W)
    print_scored(f"judged [A18] (the fallback rule: {SPEC['min_scored']} scored names or more -> {M17.SPEC['n_side']} a side, fewer -> the top / bottom third, at least {SPEC['min_side']} a side, else nothing)", Lr.cnt)
    print_scored_stats(LAB_R, Lk, W)
    print_counts(LAB_J, Lr.cnt)
    print_counts(LAB_R, Lk.cnt)
    M17.print_spin_counts("judged [A18]", Lr.cnt)
    print(f"TBIS flags: {len(tbis):,} symbol-days listed before the cut, {full_match:,} match a session and a cached name, {W.tbis_rows[1]:,} a name that is ever in the universe; every listed row is a flag")
    if W.ca is not None:
        M17.print_wide(W.ca)
    else:
        print(f"wide corporate-actions calendar [R1]: not on file yet ({winfo['path']}) - Stage A refuses until MANAGER's pull is on file and WIDE_CA_SHA is set; this dryload ran without dividends and without [A3]'s calendar side")
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
def stage_a():
    if os.path.exists(os.path.join(OUT, READ_FLAG)):                                       # CHOICE (r17's / r18's): once the lockbox has been read Stage A is frozen (a re-run could change the cell or c after the fact)
        refuse(f"Stage A refused: Stage B has already read the lockbox - Stage A is frozen ({READ_FLAG})")
    pok = prereg_ok()
    cal, winfo = M17.wide_load(S.LB0)                                                      # [R1] refuses (nothing computed) when the wide calendar is not on file / not registered / not the registered file
    mp = load_map()                                                                        # [A1] / [A8] refuses (nothing computed) when a pinned file is not on file / not the registered file / overlaps its additions
    d, finfo = load_facts(S.LB0)
    fx = build_facts(d)
    del d
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
    if CHECK_BOOK and W.days[0] != CACHE_FIRST_SESSION:                                    # [A] F is unknown before the cache's first session: the rule 'a' before 2016-01-04' is written for a World that starts there
        refuse(f"Stage A refused: the World starts {W.days[0]:%Y-%m-%d}, not at the cache's registered first session {CACHE_FIRST_SESSION:%Y-%m-%d} (nothing computed)")
    ni = attach_netiss(W, fx, mp, cal)
    wf = (W.days >= WF0) & (W.days <= PRE_END)
    kmiss = int((~np.isfinite(W.k[wf])).sum())
    print(f"world ready ({time.time() - t0:.0f}s): {int(wf.sum()):,} WF sessions, {W.S:,} names ever in the universe, k_t (read only by the borrow stress rows) undefined on {kmiss} WF sessions; ES masters "
          f"{es_meta['raw']['filename']} / {es_meta['adj']['filename']}", flush=True)
    es_txt, es_rec = M17.es_report(W)
    print(es_txt)
    M17.print_wide(W.ca)
    out = {"prereg_sha256_lf": PREREG_SHA, "prereg_verified": pok["verified"], "prereg_committed": pok["committed"], **stamp(), "judged": False, "stageA": None, "candidate": None, "pending_hand_audit": None,
           "book_check": bk, "dd_structure": dd, "reference": DV.ref_record(ref), "manifest_sha256": msha, "es_return": es_rec, "wide_calendar": W.ca, "k_undefined_wf_sessions": kmiss, "files": {k: FILE_SHA[k] for k in FILE_SHA},
           "facts": {k: v for k, v in finfo.items() if k != "sha256"}, "map": {k: v for k, v in mp.info.items() if k != "sha256"}, "entries": fx.info}
    aud_n = apply_audit(W, audit)
    asha = file_sha(os.path.join(OUT, "netiss_audit.csv"))
    print("audit file: " + ("none yet" if audit is None else f"{aud_n['rows']} rows ({aud_n['keep']} keep, {aud_n['data_event']} data_event: removed from the cells AND the nulls, and with them {aud_n['group_name_months']} more name-month(s) of the same groups [A14] - the same symbol and the same two filings)"))
    rows = A13.book_rows(B, W)
    # ---- BEFORE ANY P&L: the score's counts and facts (the leg is never built, nothing is costed)
    ranks = built_ranks(W, WF0, PRE_END)
    print_data_counts(mp, finfo, fx, W)
    srows = score_report(W, ranks, values=True)
    print_score_report(srows, ni.cal_start, names=True)
    unsc = unscored_by_name(W, ranks)
    print_unscored_by_name(unsc)
    sc2 = second_class_summary(ni_build(W, WF0, PRE_END, JUDGED, units=False, counts_only=True), W)     # [A13] counts only: the pool and the scored names, no unit path, no pick (the audit's removals are already on the World)
    print_second_classes(sc2)
    wa = {r_: wa_cross(W, r_, np.flatnonzero(W.U[f_])) for r_, f_, _x in ranks[::6]}
    print("  the weighted-average concept as a cross-check only (every 6th rank: names with both, rank correlation with ISS_1, the share on the same side of zero): " + "; ".join(
        f"{W.days[r_]:%Y-%m-%d} {v['n']} / {nan_or(v['spearman'], '+.2f')} / {nan_or(v['same_side'], '.0%')}" for r_, v in wa.items()))
    out.update({"score_by_rank": [{k: v for k, v in r_.items() if k != "cells"} | {"cells": {c: {k: (v if k != "iss" else None) for k, v in x.items()} for c, x in r_["cells"].items()}} for r_ in srows],
                "iss_percentiles_by_year": {c: {int(y): pctl_text(np.concatenate([r_["cells"][c]["iss"] for r_ in srows if r_["year"] == y])) for y in sorted({r_["year"] for r_ in srows})} for c in CELLS},
                "first_ranks": coverage_firsts(srows, ni.cal_start), "unscored_by_name": unsc, "weighted_average_cross_check": {f"{W.days[r_]:%Y-%m-%d}": v for r_, v in wa.items()}, "second_share_class": sc2})
    t1 = time.time()
    resR, objR = evaluate(W, B, S12, ref, rows, JUDGED, NREP, 0, full=True)
    print(f"judged reading [A18] done ({time.time() - t1:.0f}s: the leg, the cells, the stress rows, {NREP} random-name draws per cell from the kept pool, the deciles, the twins)", flush=True)
    unused = unused_audit_rows(W, audit)
    if unused:
        print(f"  NOTE: {len(unused)} audit data_event row(s) removed nothing (the name was not in that fill session's universe): {unused[:5]}")
    t1 = time.time()
    resK, objK = evaluate(W, B, S12, ref, rows, "remove", 0, 1, full=False)               # [A18] the leaky reading, REPORTED beside the judged one, without a null
    print(f"the leaky 'remove' reading done ({time.time() - t1:.0f}s)", flush=True)
    t1 = time.time()
    with div_mode(W, False):                                                               # [R1] the no-dividend version of both cells (the picks stay; the P&L without the cash dividends): a REPORTED row, never the verdict
        resD = evaluate(W, B, S12, ref, rows, JUDGED, NREP, 2, full=False)[0]
    print(f"no-dividend reading done ({time.time() - t1:.0f}s)", flush=True)
    spin = {"judged_reading": {c: ni_spin_counts(objR.legs, c) for c in CELLS}, "leaky_remove_reading": {c: ni_spin_counts(objK.legs, c) for c in CELLS}}
    rep, cands = reports(W, B, S12, ref, rows, objR, resR["cells"], tbis, D15.asset_status(), legs_meta, srows, post_mode=JUDGED)
    cells = resR["cells"]
    passing, cand = stage_a_flow(cells)
    a10 = a10_rows(W, ranks, objR.legs)                                                    # [A14] every flagged name-rank, with whether the registered leg PICKED it (so after the leg)
    ast = audit_status(W, cands, a10, audit)
    os.makedirs(OUT, exist_ok=True)
    pd.DataFrame([r_ for c in CELLS for r_ in cands[c]]).to_csv(os.path.join(OUT, "netiss_audit_candidates.csv"), index=False)
    pd.DataFrame(a10).to_csv(os.path.join(OUT, "netiss_a10_flags.csv"), index=False)
    print(f"WF {WF0:%Y-%m-%d} -> {PRE_END:%Y-%m-%d} ({int(wf.sum()):,} sessions) - the JUDGED reading [A18] (a name flagged inside the hold stays, on the split-safe path; only an announced split or a [D2] ex-date inside the hold removes it; the null draws from the kept pool)")
    print_cells(resR, ast)
    print(f"  {LAB_R}, no null:")
    for cell in CELLS:
        k = resK["cells"][cell]
        print(f"    {cell}: {row(cell, k)[4:]} | the judged net ${cells[cell]['base']['net']:,.0f} against the leaky reading's ${k['base']['net']:,.0f}")
    print(f"  no-dividend version [R1] (the cash dividends left out of the P&L; REPORTED, never the verdict; its own null ROC p95 {resD['null']['roc_max']['p95']:.1f}):")
    for cell in CELLS:
        k = resD["cells"][cell]
        print(f"    {cell}: {row(cell, k)[4:]} | Stage A (a)-(e) {'PASS' if k['PASS'] else 'FAIL (' + ', '.join(q for q, v in k['checks'].items() if not v) + ')'}; the registered, with dividends: net ${cells[cell]['base']['net']:,.0f} -> the dividends {'add' if cells[cell]['base']['net'] >= k['base']['net'] else 'cost'} ${abs(cells[cell]['base']['net'] - k['base']['net']):,.0f}")
    print_spin_picks(spin)
    print_deciles(resR)
    print_twins(resR)
    print_reports(rep, cells)
    print_diagnostics(resR, rep, ref)
    print_counts("L (judged [A18])", objR.legs.cnt)
    print_counts("L (the leaky 'remove' reading, reported)", objK.legs.cnt)
    print_scored("L (judged [A18])", objR.legs.cnt)
    M17.print_spin_counts("L (judged [A18])", objR.legs.cnt)
    print(f"  audit candidates (the {AUDIT_N} largest gains per cell, with the two share facts, their filings, F and group) -> {os.path.join(OUT, 'netiss_audit_candidates.csv')}; every [A10] flagged name-rank ({len(a10):,}; picked: {sum(1 for r_ in a10 if r_['picked']):,}, in "
          f"{len({r_['group'] for r_ in a10 if r_['picked']}):,} groups) with the cell / side that picked it and its group -> {os.path.join(OUT, 'netiss_a10_flags.csv')}; [A14] the hand audit (f) covers the {AUDIT_N} largest contributors per cell and every PICKED flagged name-rank, grouped by (symbol, the two facts' "
          "accession numbers): ONE row covers every rank that uses the same two filings, and a data_event row removes them all; the hand audit is the lead's (a data event found: a row symbol, date, cell, data_event in netiss_audit.csv and run stage_a again); audit rows found per list: " + ", ".join(
              f"{k} top-{AUDIT_N} {v['audited']}/{v['listed']}, picked [A10] groups {v['a10_audited']}/{v['a10_listed']}" for k, v in ast.items()))
    out.update({"judged": True, "pending_hand_audit": passing,
                "stageA": {"cells": cells, "null": resR["null"], "pass_cells": passing},
                "candidate": ({"cell": cand, "c": cells[cand]["A2"]["c"], "std_book": cells[cand]["A2"]["std_book"], "std_cell": cells[cand]["A2"]["std_cell"], "window": cells[cand]["A2"]["window"], "a2_book_roc": cells[cand]["A2"]["roc"],
                               "a2_reference_roc": cells[cand]["A2"]["reference"]["roc"], "incremental_pass": cells[cand]["A2"]["incremental_pass"], "incremental_credit": cells[cand]["A2"]["incremental_credit"],
                               "book_shadow_line": cells[cand]["A2"]["incremental_credit"], "beta_within_cap": cells[cand]["beta"]["within_cap"], "also_passes": [c for c in passing if c != cand]} if cand else None),
                "parity": {c: {"net": cells[c]["base"]["net"], "n_pos": cells[c]["base"]["n_pos"], "n_units": cells[c]["base"]["n_units"]} for c in CELLS},
                "audit": aud_n, "audit_sha256": asha, "audit_status": ast, "a10_flags": len(a10), "a10_picked_flags": int(sum(1 for r_ in a10 if r_["picked"])), "a10_picked_groups": int(len({r_["group"] for r_ in a10 if r_["picked"]})),
                "spin_counts": spin,
                "no_dividend_reading": {"null": resD["null"], "cells": {c: {k: resD["cells"][c][k] for k in ("PASS", "base", "stress", "seat", "checks", "A2")} for c in CELLS},
                                        "dividends_add_net": {c: cells[c]["base"]["net"] - resD["cells"][c]["base"]["net"] for c in CELLS}},
                "judged_post_mode": JUDGED, "calendar_splits_on_grid": W.ni.csplit,
                "leaky_remove_reading": {"null": resK["null"], "cells": {c: {k: resK["cells"][c][k] for k in ("base", "seat", "A2", "usd_year")} for c in CELLS}},
                "hygiene_counts_by_year": {"judged": {y: dict(c) for y, c in sorted(objR.legs.cnt.items())}, "leaky_remove": {y: dict(c) for y, c in sorted(objK.legs.cnt.items())}},
                "reports": rep, "es_masters": es_meta})
    dump(out, "netiss_stageA.json")
    for c in passing:
        a2 = cells[c]["A2"]
        print(f"Stage A (a)-(e) pass, (f) awaits the hand audit - cell {c}; WF ROC@30k {cells[c]['base']['roc']:.1f} (${cells[c]['usd_year']:,.0f} a year); A2 (a report) [X1]: c x{a2['c']:.4g} set by volatility, REFERENCE + c x cell ROC@30k {a2['roc']:.2f} / Sortino {a2['sortino']:.3f} against the "
              f"reference's {a2['reference']['roc']:.2f} / {a2['reference']['sortino']:.3f} -> " + ("an INCREMENTAL PASS: a forward BOOK shadow line opens beside the standalone one and MANAGER #70's gate follows (the cell's DO and its null's on the reference's drawdown days)"
                                                                                                 if a2["incremental_credit"] else "no credited incremental pass: no book shadow line" + (" (the numbers pass, the beta rule refuses the credit)" if a2["incremental_pass"] else "")))
    if passing:
        print(f"NETISS Stage A: (a)-(e) pass for {passing}; (f) AWAITS THE HAND AUDIT of the {AUDIT_N} largest contributors and the picked [A10] flagged name-ranks, grouped by their two filings [A14] (the harness never decides it); candidate {cand}. Stage B needs the lead's go-flag {GO_FLAG} (written after the hand audit, on the stock "
              "families' one sealed-year day) and a pinned lockbox-year share-fact extract (LB_FACTS: [A17] the same photographed zip, extracted by TV, pinned by sha256 in a dated addendum).")
    else:
        print("NETISS Stage A: FAIL - no cell passes (a)-(e) (" + "; ".join(f"{c}: " + ", ".join(k for k, v in cells[c]['checks'].items() if not v) for c in CELLS) +
              ") - NETISS r1 is dead; no other horizons, thresholds or concepts are tried; the lockbox stays sealed.")
    pm = peak_mb()
    print(f"stage_a took {time.time() - t0:.0f}s" + (f", peak memory {pm:,.0f} MB" if pm else ""))
    return out


# ------------------------------------------------------------------ Stage B: the one read (refuses unless the lead's go-flag is on file)
def stage_b():
    """STAGE B (LB, once, on the stock families' one sealed-year day): REFUSES unless the lead's go-flag netiss_stageB_GO.flag is on file (the lead writes it after the hand audit (f) and only on that day; CHOICE (r18's): its EXISTENCE is the sign-off - its text is stored with the read and
    never parsed), a Stage A candidate is on file AND the lockbox year's share facts are pinned (LB_FACTS: the pinned extract stops at filed 2025-06-27, so [A17] the sealed year's share facts come from the SAME photographed zip (db35d36b), extracted by TV with the same tool, only after a
    Stage A pass, and a dated addendum must pin that second extract by sha256 - the same two files' columns, filed through 2026-06-30 - before Stage B can read one fact of the sealed year; None = refuse). The sealed year is the LEG's standalone veto (r17_resmom's: >= 10 monthly rebalances, net > 0, net > 0 without its top name-month). The book add (#463 + c x the cell at Stage A's frozen c) is computed, printed and stored as book_add_reported -
    NEVER part of the pass. Every refusal is before the read flag; the flag is written (exclusively) only after every load, every check and the whole result are in hand"""
    go, flag = os.path.join(OUT, GO_FLAG), os.path.join(OUT, READ_FLAG)
    if not os.path.exists(go):
        refuse(f"Stage B refused: the lead's go-flag {GO_FLAG} is not on file - the hand audit (f) and the sealed-year day are the lead's call; the lockbox stays sealed (nothing computed, lockbox NOT read)")
    if os.path.exists(flag):
        refuse(f"Stage B refused: the lockbox was already read once ({READ_FLAG})")
    pa = os.path.join(OUT, "netiss_stageA.json")
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
    if sa.get("audit_sha256") != file_sha(os.path.join(OUT, "netiss_audit.csv")):
        refuse("Stage B refused: netiss_audit.csv is not the file Stage A ran with (it changed, or went missing) - run stage_a again (lockbox NOT read)")
    cell = cand["cell"]
    try:
        c = float(cand["c"])
    except (TypeError, ValueError):
        c = float("nan")
    if cell not in CELLS or not (math.isfinite(c) and c > 0):                                  # c is a volatility ratio: any positive number is a frozen size, but NaN / 0 / missing is a broken file
        refuse(f"Stage B refused: the frozen cell {cand.get('cell')} / size c {cand.get('c')} is not one of {CELLS} / a positive number (lockbox NOT read)")
    if not (isinstance(LB_FACTS, dict) and set(LB_FACTS) == {"facts", "facts_add"}):
        refuse("Stage B refused: the lockbox year's share facts are not pinned (LB_FACTS is None: the pinned extract stops at filed 2025-06-27 - [A17] the sealed year's facts come from the same photographed zip (db35d36b), extracted by TV with the same tool after a Stage A pass, and a dated "
               "pre-data addendum must pin that second extract by sha256, filed through 2026-06-30, before Stage B can read one fact of the sealed year) - lockbox NOT read")
    go_text = open(go).read()[:500]
    lb_files, lb_shas = {**FILES, **{k: v[0] for k, v in LB_FACTS.items()}}, {**FILE_SHA, **{k: v[1] for k, v in LB_FACTS.items()}}
    B, legs_meta = A13.load_463()                                                              # every input is loaded and checked BEFORE the flag: a bad file cannot burn the lockbox
    bk = A13.book_check(B, LB0, LB1, BOOK_LB)
    print(f"BOOK #463 LB check (must be {BOOK_LB[0]} / {BOOK_LB[1]}): ROC@30k {bk['roc']:.2f} Sortino {bk['sortino']:.3f}")
    if CHECK_BOOK and not bk["ok"]:
        refuse("Stage B refused: the #463 records do not reproduce its LB numbers - settle the end-date convention first (lockbox NOT read)")
    msha = manifest_sha()
    if CHECK_BOOK and not (msha and msha.startswith(D15.MANIFEST_PREFIX) and msha == sa.get("manifest_sha256")):
        refuse("Stage B refused: the SIPORB cache manifest is not the one Stage A ran on (a re-pull must never be mixed in) - lockbox NOT read")
    cal, winfo = M17.wide_load(S.END)                                                          # the same registered calendar, cut at the lockbox's end
    mp = load_map()
    with patched(THIS, FILES=lb_files, FILE_SHA=lb_shas):                                      # the lockbox year's extract is read through the same loader, under its own pinned shas
        d, finfo = load_facts(S.END)
    fx = build_facts(d)
    del d
    D = M17.load_data(S.END)
    tbis = D15.load_tbis(S.END)
    es_frames, es_meta = D15.load_es(S.END)
    audit = read_audit()
    W = M17.build_world(D, S.END, es_frames, tbis, cal)
    D15.release(D)
    cut_checks(W, cal, S.END)
    attach_netiss(W, fx, mp, cal)
    apply_audit(W, audit)
    rows = A13.book_rows(B, W)
    hole_txt, hole_rec = M17.es_report(W, LB0, LB1)                                            # the ES holes that reach the lockbox: printed and stored with the read
    Lw = ni_build(W, WF0, PRE_END, JUDGED)                                                     # Stage A's WF numbers (and the frozen c) must reproduce on Stage B's data (a cache or code drift stops it BEFORE the read)
    run = M17.run_cell(W, cell_leg(Lw, cell), D15.l1_cfg())                                    # CHOICE: only the candidate cell is re-read (it is the only one Stage B reads)
    xw = D15.to_B(run.x, rows, B.n)
    st, ref = D15.cell_stats(B, xw, D15.to_B(run.cnt, rows, B.n), WF0, PRE_END, run), sa["parity"][cell]
    print(f"WF re-read on Stage B's data: {cell} positions {st['n_pos']:,} (Stage A {ref['n_pos']:,}), net ${st['net']:,.0f} (Stage A ${ref['net']:,.0f})")
    if st["n_pos"] != ref["n_pos"] or st["n_units"] != ref["n_units"] or abs(st["net"] - ref["net"]) > max(1.0, 1e-6 * abs(ref["net"])):
        refuse(f"Stage B refused: the WF numbers of {cell} do not reproduce on Stage B's data - the cache or the code changed since Stage A (lockbox NOT read)")
    c2 = plain_a2(B, xw, cell)["c"]
    print(f"  frozen size {cell}: c x{c:.6g} (Stage A) vs x{c2:.6g} recomputed from {A2_WINS[cell][0]:%Y-%m-%d} .. {A2_WINS[cell][1]:%Y-%m-%d} on Stage B's data")
    if not (math.isfinite(c2) and abs(c2 - c) <= 1e-9 * c):
        refuse(f"Stage B refused: the volatility-set size c of {cell} does not reproduce on Stage B's data - the cache or the code changed since Stage A (lockbox NOT read)")
    L = ni_build(W, LB0, LB1, JUDGED)                                                          # CHOICE (r15's order): the whole LB result is computed, nothing shown, BEFORE the flag
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
    cands = ni_candidate_rows(W, L, cell, run, tbis, D15.asset_status(), 20)
    text = json.dumps({"cell": cell, "c": c, "go_flag": go_text, "book_check": bk, "es_masters": es_meta, "leg": leg, "checks": chk, "pass": bool(ok), "book_add_reported": add, "es_return_lb": hole_rec, "wide_calendar": W.ca,
                       "lockbox_facts": {k: v for k, v in finfo.items() if k != "sha256"}, "lockbox_facts_sha256": {k: lb_shas[k] for k in ("facts", "facts_add")}, "hygiene_counts_by_year": cnt, "top_name_months": cands, **stamp(), "prereg_sha256_lf": PREREG_SHA},
                      indent=1, default=R11.js)
    buf = io.StringIO()                                                                        # the whole printout is built here, before the flag: a formatting error cannot burn the lockbox
    with contextlib.redirect_stdout(buf):
        print("Stage B (lockbox, read once) - the sealed year is the LEG's standalone veto")
        print(f"  {cell}: positions {leg['n_pos']:,}, monthly rebalances {leg['n_units']:,}, net ${leg['net']:,.0f}, ROC@30k {leg['roc']:.1f}, Sortino {leg['sortino']:.2f}; its top name-month ${leg['top_pos']:,.0f}, "
              f"net without it ${leg['net_ex_top_pos']:,.0f}")
        print("  " + hole_txt)
        print("  Stage B checks: " + ", ".join(k + (" ok" if v else " FAIL") for k, v in chk.items()) + f" -> {'PASS' if ok else 'FAIL'}")
        print(f"  book add, REPORTED and never part of the pass: #463 + {cell} x{c:.4g} (frozen): LB ROC@30k {r['roc']:.2f} Sortino {r['sortino']:.3f} net ${r['net']:,.0f} -> would "
              f"{'have' if would else 'NOT have'} cleared {RULES['b_roc']:g} / {RULES['b_sort']:g}")
        print("NETISS Stage B: " + ("PASS - the leg survives its sealed year: it goes to a computed no-order FORWARD SHADOW (Stage C) with its own bar, logged by research id; the book add above is a report - "
                                    "the forward record decides any book add, and opening any account is the owner's decision (owner call)." if ok else
                                    "FAIL - the leg is vetoed by its sealed year: NETISS r1 is dead; ledger + memory."))
    with open(flag, "x") as f:                                                                 # exclusive create: the one read starts here - what is left is two writes and a print
        f.write(pd.Timestamp.now().isoformat())
    with open(os.path.join(OUT, "netiss_stageB.json"), "w") as f:
        f.write(text)
    print(buf.getvalue().rstrip())
    pm = peak_mb()
    if pm:
        print(f"peak memory {pm:,.0f} MB")
    return ok


# ------------------------------------------------------------------ test support: hand-made filings, hand-made worlds, and plain-python recounts of every score, pool, pick and path (independent of the vectorised code)
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


DEI, GAAP, WAC = CONCEPTS[0], CONCEPTS[1], WA_CONCEPT
FACT_FRAME_COLS = ["cik", "concept", "val", "start", "end", "accn", "form", "filed"]


def fr(rows):
    """hand-made filings -> the typed frame load_facts returns. A row = (cik, concept, val, end, filed[, accn[, form[, start]]]); the accession defaults to a unique string, the form to 10-Q"""
    out = []
    for r in rows:
        cik, con, val, end, filed = r[:5]
        accn = r[5] if len(r) > 5 and r[5] is not None else f"A-{cik}-{con[-6:]}-{end}-{filed}"
        form = r[6] if len(r) > 6 and r[6] is not None else "10-Q"
        start = r[7] if len(r) > 7 else None
        out.append((cik, con, float(val), pd.NaT if start is None else TS(start), TS(end), accn, form, TS(filed)))
    return pd.DataFrame(out, columns=FACT_FRAME_COLS)


def mp_of(rows):
    """hand-made map rows (symbol, cik, method) -> the map load_map returns (usable by the registered rule)"""
    df = pd.DataFrame(rows, columns=["symbol", "cik", "method"])
    df["source"] = "base"
    df["usable"] = (df["cik"] != "") & df["method"].isin(ALLOWED_METHODS + ADD_METHODS)
    return SimpleNamespace(df=df, info={})


def cal_of(splits=(), start="2016-06-01"):
    """a hand-made wide calendar: (symbol, ex date, type) splits and the manifest's start (None = the manifest holds none)"""
    sp = pd.DataFrame([(s, TS(d), t) for s, d, t in splits], columns=["symbol", "ex", "type"])
    return SimpleNamespace(split=sp, div=None, spin=None, info={"manifest": ({"start": start} if start else {})})


def score_world(days, syms, F=None, Ac=None, Dv=None, Vv=None):
    """a minimal World for the score alone (no price series): sessions, names, the split factor F (T, S), the split-adjusted closes and the cash dividends on the split-adjusted basis (for the composite twin), the raw close ($100) and volume (3M, [A13]'s dollar volume reads them);
    every name is in the universe"""
    days = pd.DatetimeIndex(days)
    T, S_ = len(days), len(syms)
    return SimpleNamespace(days=days, syms=np.array(syms), S=S_, T=T, F=np.ones((T, S_)) if F is None else np.array(F, float), Ac=np.full((T, S_), 100.0) if Ac is None else np.array(Ac, float),
                           Dv1=np.zeros((T, S_)) if Dv is None else np.array(Dv, float), U=np.ones((T, S_), bool), Cl=np.full((T, S_), 100.0), Vv=np.full((T, S_), 3e6) if Vv is None else np.array(Vv, float))


def score_setup(days, syms, rows, ciks=None, methods=None, F=None, splits=(), cal_start="2016-06-01", Ac=None, Dv=None):
    """hand-made filings + names -> a score world with W.ni attached. ciks / methods: per-name map entries (default: name i -> CIK 'C{i}', method current_ticker)"""
    W = score_world(days, syms, F, Ac, Dv)
    mrows = [(s, (ciks[i] if ciks else f"C{i}"), (methods[i] if methods else "current_ticker")) for i, s in enumerate(syms)]
    attach_netiss(W, build_facts(fr(rows)), mp_of(mrows), cal_of(splits, cal_start))
    return W


def brute_entries(rows, cik, concept):
    """plain python: {end: (first filed date, value, usable)} of one CIK and concept - the value of the row filed FIRST (ties: the smallest accession), ambiguous when the rows of that first date carry more than one value, unusable when ambiguous, when the as-of date is after its
    own first filed date or when the value is missing"""
    by = defaultdict(list)
    for (c, con, val, start, end, accn, form, filed) in rows.itertuples(index=False):
        if c == cik and con == concept:
            by[end].append((filed, accn, val))
    out = {}
    for end, lst in by.items():
        f1 = min(f for f, _a, _v in lst)
        at = sorted((a, v) for f, a, v in lst if f == f1)
        vals = {v for _a, v in at if math.isfinite(v)}
        out[end] = (f1, at[0][1], bool(len(vals) <= 1 and len({v for _a, v in at}) <= 1 and not end > f1 and math.isfinite(at[0][1])))
    return out


def years_back_py(d, k):
    """the same calendar date k years earlier (29 February -> 28 February)"""
    try:
        return d.replace(year=d.year - k)
    except ValueError:
        return d.replace(year=d.year - k, day=28)


def dlist(W):
    """the World's sessions as a plain list of Timestamps (cached on the World)"""
    if getattr(W, "_dl", None) is None:
        W._dl = list(W.days)
    return W._dl


def brute_pair(ent, W, r, k):
    """plain python: (S entry, S' entry) of one concept at rank row r - the usable entries are those whose first session STRICTLY AFTER the first filed date exists and is on or before r; S = the latest as-of date; S' = the as-of date closest to a - k years
    inside +-35 days, a tie to the earlier one; entry = (end, value) or None"""
    dl = dlist(W)
    use = {}
    for end, (f1, v, ok) in ent.items():
        after = bisect.bisect_right(dl, f1)                    # the index of the first session strictly after the first filed date
        if ok and after < len(dl) and after <= r:
            use[end] = v
    if not use:
        return None, None
    a = max(use)
    tgt = years_back_py(a, k)
    near = sorted((abs((e - tgt).days), e) for e in use if abs((e - tgt).days) <= BAND_DAYS)
    return (a, use[a]), ((near[0][1], use[near[0][1]]) if near else None)


def brute_fchg(W, j):
    """plain python: the sessions on which the split factor of name j moves by more than 1% from the previous session's (both finite)"""
    out = set()
    for s in range(1, W.T):
        a, b = W.F[s, j], W.F[s - 1, j]
        if math.isfinite(a) and math.isfinite(b) and abs(a / b - 1.0) > SPLIT_TOL:
            out.add(s)
    return out


def brute_calrows(W, cal, j):
    """plain python: the sessions of the calendar's splits of name j (an ex-date that is not a session moves to the next one; past the data: not placed)"""
    out = set()
    for sym, ex, _ty in cal.split.itertuples(index=False):
        if sym == W.syms[j]:
            s = bisect.bisect_left(dlist(W), ex)
            if s < W.T:
                out.add(s)
    return out


def brute_score(W, rows, cal, j, cik, static, r, k, cache=None):
    """plain python NETISS score of name j at rank row r for horizon k years -> a SimpleNamespace (code, iss, use, fallback, flag10, straddle, stale, f_alone, ln10, a3c, a3f): the registered order of rules written out with loops - the static reason; no usable fact of either concept; the
    concept order with a COMPLETE pair from one concept; a value not positive; a' before the cache's first session; no split factor; ISS = ln(S F(a) / (S' F(a'))); |ISS| > ln(10); the two-way split check where the calendar covers a' (a' on / after its start). The first reason is
    attributed in that order (ln(10), then a calendar split F does not show, then an F change the calendar does not show) and each of the three is also flagged on its own"""
    nan = float("nan")
    out = SimpleNamespace(code=static, iss=nan, use=0, fallback=False, flag10=False, straddle=False, stale=False, f_alone=False, ln10=False, a3c=False, a3f=False, ia=-1, iap=-1)
    if static != R_SCORED:
        return out
    cache = {} if cache is None else cache
    ents = []
    for con in (DEI, GAAP):
        if (cik, con) not in cache:
            cache[(cik, con)] = brute_entries(rows, cik, con)
        ents.append(cache[(cik, con)])
    pairs = [brute_pair(e, W, r, k) for e in ents]
    if all(p[0] is None for p in pairs):
        out.code = R_NO_FACT
        return out
    use = next((q for q, p in enumerate(pairs, 1) if p[0] is not None and p[1] is not None), 0)
    if not use:
        out.code = R_NO_BAND
        return out
    out.use = use
    (a, sv), (ap, pv) = pairs[use - 1]
    if not (sv > 0 and pv > 0):
        out.code = R_NOT_POS
        return out
    if ap < W.days[0]:
        out.code = R_BEFORE_CACHE
        return out
    ia, iap = bisect.bisect_right(dlist(W), a) - 1, bisect.bisect_right(dlist(W), ap) - 1
    if ia < 0 or iap < 0 or not all(math.isfinite(W.F[i, j]) and W.F[i, j] > 0 for i in (ia, iap)):
        out.code = R_NO_FACTOR
        return out
    out.ia, out.iap = ia, iap
    iss = math.log(sv * W.F[ia, j] / (pv * W.F[iap, j]))
    cs = cal_start_of(cal)
    covered = cs is not None and ap >= cs
    fch, crow = brute_fchg(W, j), brute_calrows(W, cal, j)
    near = lambda s, ss: any(abs(s - t) <= SPLIT_NEAR for t in ss)
    un_f = [s for s in fch if iap < s <= ia and not near(s, crow)]
    un_c = [s for s in crow if iap < s <= ia and not near(s, fch)]
    out.f_alone, out.ln10, out.a3c, out.a3f = not covered, abs(iss) > LN10, bool(covered and un_c), bool(covered and un_f)
    out.code = R_ISS10 if out.ln10 else R_SPLIT_C if out.a3c else R_SPLIT_F if out.a3f else R_SCORED
    if out.code == R_SCORED:
        f1_now = next(v[0] for e, v in ents[use - 1].items() if e == a)
        out.iss, out.fallback = iss, bool(use == 2 and pairs[0][0] is not None)
        out.flag10, out.straddle, out.stale = abs(iss) > LN15, any(iap < s <= ia for s in fch), bool((W.days[r] - f1_now).days <= STALE_DAYS)
    return out


def cal_start_of(cal):
    return M17.calendar_start(cal.info.get("manifest"))


def static_of(W, ni, j):
    return int(ni.static[j])


# ------------------------------------------------------------------ selftest: hand-made worlds and hand-made filings, no files, no data
def t_constants():
    assert (NREP, SEED, CELLS, KS, AUDIT_N) == (500, 20261008, ("N12", "N24"), {"N12": 1, "N24": 2}, 50) and YEARS == tuple(range(2016, 2025))
    assert A2_WINS == {"N12": (TS("2017-02-01"), TS("2019-01-31")), "N24": (TS("2018-02-01"), TS("2020-01-31"))} and (A2_TARGET, A2_REPORT) == (0.25, (0.5, 2.0)) == (M17.A2_TARGET, M17.A2_REPORT)
    assert (WF0, PRE_END, LB0, LB1) == (TS("2016-07-01"), TS("2025-06-29"), TS("2025-06-30"), TS("2026-06-30")) and (S.LB0, S.END) == (LB0, R11.LBX) and CACHE_FIRST_SESSION == TS("2016-01-04")
    assert (BOOK_WF, BOOK_LB, DEEPEST_WF) == ((93.81, 3.816), (155.54, 4.15), 44849.0) and DV.REF_W == 0.264 and DV.REF_FACTS == {"roc": 120.95, "sortino": 3.921, "max_dd": 36526.0} and DV.REF_SHA.startswith("86721fda") and DV.REF_CSV_PINNED.endswith("resmom_cells_daily_wf_keep.csv")
    assert (COST_BPS, STRESS_BPS, BORROW, BORROW_STRESS) == (5.0, (10.0, 20.0), 0.0025, (0.01, 0.03)) and M17.SPEC == {"win": 252, "form_n": 231, "skip": 21, "min_n": 230, "n_side": 50, "slot": 4000.0, "hyg_lead": 5}
    assert SPEC == {"min_scored": 150, "min_side": 20, "dec_n": 10, "dec_min": 10, "hedge_win": 252, "hedge_min": 230}, "150 scored names or the thirds, at least 20 a side, ten deciles, a 252-session hedge window"
    assert (LN10, LN15, BAND_DAYS, SPLIT_TOL, SPLIT_NEAR, STALE_DAYS, BETA_CAP) == (math.log(10.0), math.log(1.5), 35, 0.01, 3, 60, 0.20)
    assert CONCEPTS == ("dei:EntityCommonStockSharesOutstanding", "us-gaap:CommonStockSharesOutstanding") and WA_CONCEPT == "us-gaap:WeightedAverageNumberOfSharesOutstandingBasic" and FOREIGN_FORMS == ("20-F", "20-F/A", "40-F", "40-F/A", "6-K", "6-K/A")
    assert ALLOWED_METHODS == ("current_ticker", "name_exact") and ADD_METHODS == ("reviewed_same_firm",) and RULES is M17.RULES and CHECK_BOOK is True and LB_FACTS is None and (GO_FLAG, READ_FLAG) == ("netiss_stageB_GO.flag", "netiss_stageB_READ.flag")
    assert FILE_SHA == {"facts": "02387a4f1140c41872a7b46cf6b9657abec90ef90d09a0a2ee47ff882c2f4433", "facts_add": "d10626d8694b180dae991c9d83502c27352b285e46b1e84c9d29b610958f2871",
                        "map": "19adc9badc8e9c2b999d818c9aa4b78f257835e19eacd418cdf55c0fc93f1909", "map_add": "6bf8dfabc0a945bcf6c30f1d6bca201703d8a67d1e8f48daccfba4c6ca23c866"}
    assert [REASONS[i] for i in (R_SCORED, R_NOT_IN_MAP, R_NO_FACTS, R_FOREIGN, R_NO_FACT, R_NO_BAND, R_NOT_POS, R_BEFORE_CACHE, R_NO_FACTOR, R_ISS10, R_SPLIT_C, R_SPLIT_F)] == [
        "scored", "not_in_map", "no_facts_for_cik", "foreign_filer", "no_usable_fact", "no_band_pair", "value_not_positive", "a_prime_before_cache", "no_split_factor", "iss_over_ln10", "split_calendar_not_in_F", "split_F_not_in_calendar"]
    assert len(REASONS) == len(REASON_TEXT) == 18 and set(REASONS) == set(REASON_TEXT) and REASONS[0] == "scored" and all(MAP_REASON[k] in range(17) for k in MAP_REASON)
    assert R_SECOND_CLASS == 17 and REASONS[R_SECOND_CLASS] == "second_share_class" and REASONS[-1] == "second_share_class" and "[A13]" in REASON_TEXT["second_share_class"], "[A13]'s pool-level reason is the last code"
    assert D15.SPEC["dv_n"] == 20, "[A13]: the 20 sessions before the fill are the universe's own dollar-volume window"
    assert set(MAP_REASON) == {"current_ticker_name_mismatch", "name_ambiguous", "unmapped", "non_common"}
    txt = open(PREREG, encoding="utf-8").read()                                                             # the registered text carries every number this file hard-codes
    for frag in ("20261008", "500 draws", "ln(10)", "ln(1.5)", "+-35-day", "2016-01-04", "2016-06-01", "+-3 sessions", "more than 1%", "0.20", "252 sessions", "N12 2017-02-01", "N24 2018-02-01", "2019-01-31", "2020-01-31", "bed7bf8b", "120.82 / Sortino 3.916", "$36,526",
                 "02387a4f1140c41872a7b46cf6b9657abec90ef90d09a0a2ee47ff882c2f4433", "19adc9badc8e9c2b999d818c9aa4b78f257835e19eacd418cdf55c0fc93f1909", "6bf8dfabc0a945bcf6c30f1d6bca201703d8a67d1e8f48daccfba4c6ca23c866", "d10626d8694b180dae991c9d83502c27352b285e46b1e84c9d29b610958f2871",
                 "two thirds", "fewer than 150 scored names", "at least 20 a side", "dollars a year", "45 on the walk-forward", "[A10] AUDIT FLAG", "e5bc8487", "380b05f2"):
        assert frag in txt, frag
    for frag in ("[A13] ONE SHARE CLASS PER FIRM", "31 CIKs carry", "the larger mean raw dollar volume over the", "20 sessions before the fill is scored", "counted per", "'second share class'",                                  # ADDENDUM 3: the rules this file implements
                 "[A14] THE HAND AUDIT'S SCOPE", "PICKED (either side, either cell)", "grouped by (symbol, the two facts' accession numbers)", "uses the same two filings", "553 flagged name-ranks for N12 and 953 for N24",
                 "[A15] READINGS FIXED NOW", "a USABLE row in", "459 N12 and 36 N24 name-months", "n // 3 a side", "N12 needs 6 of its 9, N24 6 of its 8", "BOTH realised betas", "0.5 bps a side", "(a tie: N12)",
                 "[A16] FACTS AS FOUND", "2017-01-31 (22 names: no trade)", "first traded fill 2017-03-01", "2018-01-31 (18) and 2018-03-01", "[A17] STAGE B'S FACTS", "photographed zip (db35d36b)", "pinned by sha256 in a dated"):
        assert frag in txt, frag
    with quiet():
        assert prereg_ok()["verified"] is True
    st = stamp()
    assert len(st["harness_sha256"]) == 64 and st["facts_sha256"] == FILE_SHA["facts"] and st["map_add_sha256"] == FILE_SHA["map_add"] and set(st) >= {"r17_sha256", "r18_sha256", "r15_sha256", "siporb_sha256", "r11_sha256", "r12_sha256", "r13_sha256", "wide_ca_sha256", "early_close"}
    assert st["r17_sha256"] == R11.sha_lf(M17.__file__) and st["r18_sha256"] == R11.sha_lf(DV.__file__) and st["harness_sha256"] == R11.sha_lf(os.path.abspath(__file__))
    assert OUT_DEFAULT == "C:" + chr(92) + "EdgeLog" + chr(92) + "_anatomy_cache" + chr(92) + "rocfrontier" + chr(92) + "netiss_r1", "the default results folder (outside git); a test run never touches it: selftest() points OUT at a temp dir"
    for a, b in ((DAY0, int(np.datetime64("1900-01-01").astype(np.int64))),):
        assert a == b and KEYMUL > 10 ** 5, "the composite sort key: CIK index x 10^6 + (day number - 1900-01-01) never collides (a day number is under 10^5 + 25,567)"
    a = years_back(day_i(["2024-02-29", "2020-02-29", "2024-03-31", "2016-02-28"]), 1)
    assert [dstr(x) for x in a] == ["2023-02-28", "2019-02-28", "2023-03-31", "2015-02-28"] and [dstr(x) for x in years_back(day_i(["2024-02-29", "2024-05-31"]), 2)] == ["2022-02-28", "2022-05-31"]
    ds = pd.DatetimeIndex(["2024-01-02", "2024-01-03", "2024-01-05"]).values.astype("datetime64[D]").astype(np.int64)
    assert row_le(ds, day_i(["2024-01-01", "2024-01-02", "2024-01-04", "2024-01-06"])).tolist() == [-1, 0, 1, 2]


def t_entries():
    """[A2] the first-filed rule on hand-made filings: the value of the FIRST filed row stands (an amendment, a restatement and a later comparative never replace it); two accessions on the first day with the same value are one entry (the smallest accession), with different values AMBIGUOUS and
    unusable; an as-of date after its own first filing and a missing value are unusable; a value of zero stays (it gives 'not positive', never a fallback to an older one); the entries are sorted by (CIK, as-of date); every field recounted by plain python"""
    rows = [("1", DEI, 100, "2018-03-31", "2018-05-02", "a1", "10-Q"), ("1", DEI, 120, "2018-03-31", "2018-08-02", "a2", "10-Q"),                         # a later comparative with another value
            ("1", DEI, 999, "2018-03-31", "2018-09-10", "a3", "10-Q/A"),                                                                                  # an amendment
            ("1", DEI, 90, "2017-12-31", "2018-02-20", "b1", "10-K"), ("1", DEI, 91, "2017-12-31", "2018-02-20", "b0", "10-K"),                          # the same day, two accessions, two values: ambiguous
            ("2", DEI, 50, "2018-03-31", "2018-05-02", "c1", "10-Q"), ("2", DEI, 50, "2018-03-31", "2018-05-02", "c0", "10-Q"),                          # the same day, two accessions, the same value: one entry
            ("2", DEI, 60, "2018-06-30", "2018-05-15", "c2", "10-Q"),                                                                                      # as-of date after its own filing: unusable
            ("2", DEI, 0, "2017-12-31", "2018-02-20", "c3", "10-K"),                                                                                       # zero stays (usable: 'not positive' later)
            ("3", DEI, float("nan"), "2018-03-31", "2018-05-02", "d1", "10-Q"), ("3", DEI, 70, "2018-06-30", "2018-08-01", "d2", "10-Q"),                  # a missing value: unusable
            ("1", GAAP, 80, "2018-03-31", "2018-05-02", "e1", "10-Q")]
    d = fr(rows)
    e, cnt = entries_of(d[d["concept"] == DEI])
    assert list(e.columns) == ["cik", "end", "f1", "val", "accn", "form", "ok"] and e[["cik", "end"]].values.tolist() == sorted(e[["cik", "end"]].values.tolist()), "sorted by (CIK, as-of date)"
    got = {(r.cik, r.end): (r.f1, r.val, r.ok) for r in e.itertuples()}
    want = {}
    for cik in ("1", "2", "3"):
        for end, (f1, v, ok) in brute_entries(d, cik, DEI).items():
            want[(cik, end)] = (f1, v, ok)
    assert set(got) == set(want) and all(got[k][0] == want[k][0] and ((got[k][1] == want[k][1]) or (math.isnan(got[k][1]) and math.isnan(want[k][1]))) and got[k][2] == want[k][2] for k in got), (got, want)
    assert got[("1", TS("2018-03-31"))] == (TS("2018-05-02"), 100.0, True), "the first filed value stands: no later filing - comparative, restatement or amendment - replaces it"
    assert got[("1", TS("2017-12-31"))][2] is False and got[("2", TS("2018-03-31"))] == (TS("2018-05-02"), 50.0, True) and e[(e["cik"] == "2") & (e["end"] == TS("2018-03-31"))]["accn"].iloc[0] == "c0", "same day, same value: one entry, the smallest accession"
    assert got[("2", TS("2018-06-30"))][2] is False and got[("3", TS("2018-03-31"))][2] is False and got[("2", TS("2017-12-31"))] == (TS("2018-02-20"), 0.0, True)
    assert cnt == {"entries": 7, "ambiguous": 1, "end_after_filed": 1, "value_missing": 1, "value_not_positive": 1, "later_filing_carries_another_value": 2}, cnt
    fx = build_facts(d)
    assert list(fx.ciks) == ["1", "2", "3"] and fx.cix == {"1": 0, "2": 1, "3": 2} and fx.dei.n == 7 and fx.gaap.n == 1 and fx.info["dei"] == cnt and fx.info["gaap"]["entries"] == 1
    assert np.array_equal(fx.dei.ck, np.sort(fx.dei.ck)) and fx.dei.ok.sum() == 4 and fx.allent.n == 7 and not fx.foreign_only.any(), "every CIK has a non-foreign filing"
    assert fx.info["ciks_without_a_score_concept_entry"] == 0
    # [A4] a CIK whose share facts come ONLY from 20-F / 40-F / 6-K filings is a foreign filer; one 10-Q makes it a domestic one
    fx2 = build_facts(fr([("7", DEI, 10, "2018-03-31", "2018-05-02", None, "20-F"), ("7", GAAP, 10, "2018-03-31", "2018-05-02", None, "6-K/A"), ("8", DEI, 10, "2018-03-31", "2018-05-02", None, "20-F"), ("8", DEI, 11, "2018-06-30", "2018-08-02", None, "10-Q"),
                          ("9", WAC, 10, "2018-03-31", "2018-05-02", None, "10-K", "2017-04-01")]))
    assert fx2.foreign_only.tolist() == [True, False, False] and fx2.info["ciks_foreign_only"] == 1 and fx2.info["ciks_without_a_score_concept_entry"] == 1, "CIK 9 holds only the weighted-average concept: no score concept entry"
    # the weighted-average concept keeps only ANNUAL durations (340 .. 380 days); a quarterly one is not an entry
    fx3 = build_facts(fr([("1", WAC, 10, "2018-12-31", "2019-02-20", None, "10-K", "2018-01-01"), ("1", WAC, 11, "2018-12-31", "2019-02-20", "x2", "10-K", "2018-10-01"), ("1", WAC, 12, "2017-12-31", "2018-02-20", None, "10-K", "2017-01-01"),
                          ("1", DEI, 5, "2018-12-31", "2019-02-20", None, "10-K")]))
    assert fx3.wa.n == 2 and fx3.wa.val.tolist() == [12.0, 10.0], (fx3.wa.n, fx3.wa.val)
    # bind: a fact is usable at r iff the first session STRICTLY AFTER its first filed date is on or before r
    days = pd.DatetimeIndex(["2018-05-01", "2018-05-02", "2018-05-03", "2018-05-04", "2018-05-07"])           # 05-05 / 05-06 are a weekend
    di = day_i(days)
    f1s = day_i(["2018-04-30", "2018-05-01", "2018-05-02", "2018-05-04", "2018-05-05", "2018-05-06", "2018-05-07", "2018-04-01"])
    ent = SimpleNamespace(ck=np.zeros(len(f1s), np.int64), end=f1s - 40, f1=f1s, val=np.ones(len(f1s)), ok=np.ones(len(f1s), bool), accn=np.array([""] * len(f1s), object), form=np.array([""] * len(f1s), object), n=len(f1s))
    assert bind(ent, di).urow.tolist() == [0, 1, 2, 4, 4, 4, 5, 0], "filed before the first session -> the first session; on a session -> the next session; on a weekend -> the next session; on the last session -> past the data (never usable)"
    ub = bind(ent, di)
    for r_, want_ in ((0, [0, 7]), (1, [0, 1, 7]), (2, [0, 1, 2, 7]), (3, [0, 1, 2, 7]), (4, [0, 1, 2, 3, 4, 5, 7])):
        assert [i for i in range(len(f1s)) if ub.urow[i] <= r_] == want_, r_
    assert 6 not in [i for i in range(len(f1s)) if ub.urow[i] <= 4], "a filing on the data's last session is never usable inside the data"


def q_rows(cik, concept, items, form="10-Q"):
    """(end, filed, value) triples of one CIK and concept -> filing rows"""
    return [(cik, concept, v, e, f, None, form) for e, f, v in items]


def compare_scores(W, frame, cal, names, cik_of, ranks):
    """the vectorised score of every name of the World at every rank, both cells, against the plain-python recount: the reason code, the concept, ISS and every flag -> the number of (name, cell, rank) triples checked"""
    ni, n_chk, cache = W.ni, 0, {}
    for rk in ranks:
        s_ = score_rank(W, rk)
        for c, k in KS.items():
            for j, n in enumerate(names):
                b = brute_score(W, frame, cal, j, cik_of.get(n, ""), int(ni.static[j]), rk, k, cache)
                assert int(s_[c].code[j]) == b.code, (c, n, W.days[rk], REASONS[int(s_[c].code[j])], REASONS[b.code])
                for f_ in ("flag10", "straddle", "stale", "fallback", "f_alone", "ln10", "a3c", "a3f"):
                    assert bool(getattr(s_[c], f_)[j]) == getattr(b, f_), (c, n, W.days[rk], f_)
                assert (b.code != R_SCORED and not math.isfinite(float(s_[c].iss[j]))) or abs(float(s_[c].iss[j]) - b.iss) < 1e-12, (c, n, W.days[rk])
                assert int(s_[c].use[j]) == (b.use if b.code == R_SCORED else 0)
                n_chk += 1
    return n_chk


def score_case():
    """the hand-made world of t_score: 31 names on 1,300 sessions 2016-01-04 .. 2020-12-31 with a planted case each -> (days, names, rows, map rows, F, calendar)"""
    days = pd.bdate_range("2016-01-04", "2020-12-31")
    di = lambda s: int(days.get_loc(TS(s)))
    names = ["AAA", "BBB", "CCC", "DDD", "EEE", "FFF", "GGG", "HHH", "III", "JJJ", "KKK", "LLL", "MMM", "M2", "M3", "M4", "M5", "NNN", "OOO", "PPP", "QQQ", "SSS", "TTT", "UUU", "VVV", "WWW", "XXX", "YYY", "A01", "BEF", "ADR"]
    ix = {n: i for i, n in enumerate(names)}
    rows = []
    add = lambda cik, con, items, form="10-Q": rows.extend(q_rows(cik, con, items, form))
    add("C0", DEI, [("2016-04-29", "2016-05-04", 90), ("2017-04-28", "2017-05-03", 100), ("2018-01-26", "2018-02-01", 105), ("2018-04-27", "2018-05-02", 110)])                      # a clean issuer; filed 58 days before r: stale
    add("C1", DEI, [("2017-04-28", "2017-05-03", 50), ("2018-04-27", "2018-05-02", 105)])                                                                                                # a 2-for-1 split (F and the calendar both show it): ISS = ln(105 / (50 x 2))
    add("C2", DEI, [("2017-04-28", "2017-05-03", 800), ("2018-04-27", "2018-05-02", 100)])                                                                                               # GE: a 1-for-8 reverse split F does not show, the calendar does
    add("C3", DEI, [("2017-04-28", "2017-05-03", 30), ("2018-04-27", "2018-05-02", 93)])                                                                                                 # an F change (x3) the calendar does not show
    add("C4", DEI, [("2016-04-29", "2016-05-04", 40), ("2017-04-28", "2017-05-03", 80), ("2018-04-27", "2018-05-02", 84)])                                                              # a split before the calendar's start: F alone for N24
    add("C5", DEI, [("2017-04-28", "2017-05-03", 10), ("2018-04-27", "2018-05-02", 150)])                                                                                                # |ISS| = ln(15) > ln(10)
    add("C6", DEI, [("2017-04-28", "2017-05-03", 100), ("2018-04-27", "2018-05-02", 170)])                                                                                               # ln(1.7) > ln(1.5): flagged, scored
    add("C7", GAAP, [("2017-04-28", "2017-05-03", 200), ("2018-04-27", "2018-05-02", 190)])                                                                                              # balance sheet only: no fallback (no cover-page value at all)
    add("C8", DEI, [("2017-12-29", "2018-01-04", 95), ("2018-04-27", "2018-05-02", 100)])                                                                                                # a cover-page value now, none a year ago ...
    add("C8", GAAP, [("2017-03-31", "2017-05-03", 90), ("2018-03-31", "2018-05-02", 99)], "10-K")                                                                                         # ... the balance sheet has the pair: the fallback
    add("C9", DEI, [("2018-04-27", "2018-05-02", 100)])
    add("C9", GAAP, [("2017-04-28", "2017-05-03", 80)])                                                                                                                                  # S from one concept, S' from the other: never mixed -> no pair
    add("C13", DEI, [("2017-04-28", "2017-05-03", 100), ("2018-04-27", "2018-05-02", 110)])                                                                                              # unmapped / mismatched / ambiguous / non-common names have facts too: still no score
    add("C14", DEI, [("2017-04-28", "2017-05-03", 100), ("2018-04-27", "2018-05-02", 110)], "20-F")                                                                                      # a foreign filer
    add("C15", DEI, [("2018-04-27", "2018-07-10", 100)])                                                                                                                                 # filed after r: no usable fact
    add("C16", DEI, [("2017-04-28", "2017-05-03", 100), ("2018-04-27", "2018-05-02", 0)])                                                                                                # S = 0: not positive
    add("C18", DEI, [("2017-04-28", "2017-05-03", 100), ("2018-04-27", "2018-05-02", 110)])                                                                                              # no split factor on a' (NaN F)
    add("C19", DEI, [("2017-03-23", "2017-04-28", 100), ("2018-04-27", "2018-05-02", 110)])                                                                                              # S' 35 days before the target (2017-04-27): inside the band
    add("C20", DEI, [("2017-03-22", "2017-04-28", 100), ("2018-04-27", "2018-05-02", 110)])                                                                                              # 36 days: outside
    add("C21", DEI, [("2017-04-17", "2017-05-02", 100), ("2017-05-07", "2017-05-12", 120), ("2018-04-27", "2018-05-02", 130)])                                                           # two entries 10 days either side of the target: the earlier
    add("C22", DEI, [("2017-04-28", "2017-05-03", 80), ("2018-04-27", "2018-05-02", 100), ("2018-04-27", "2018-05-20", 250)], "10-K/A")                                                    # an amendment with another value: the first filed stands
    add("C23", DEI, [("2017-06-27", "2017-07-03", 90), ("2018-04-27", "2018-05-02", 100), ("2018-06-27", "2018-06-28", 130)])                                                           # filed the day before r (a Friday): usable at r's close
    add("C24", DEI, [("2017-04-28", "2017-05-03", 80), ("2018-04-27", "2018-05-02", 100), ("2018-06-28", "2018-06-29", 400)])                                                           # filed ON r's date: not yet usable
    add("C26", DEI, [("2017-01-27", "2017-02-02", 100), ("2018-01-26", "2018-01-30", 110)])                                                                                              # S first filed 150 days before r: not stale
    add("C27", DEI, [("2015-12-18", "2015-12-23", 50), ("2016-12-16", "2016-12-21", 60)])                                                                                                # S' before the cache's first session at the 2017-01-31 rank
    add("C28", DEI, [("2017-04-28", "2017-05-03", 100), ("2018-04-27", "2018-05-02", 110)], "6-K")                                                                                       # foreign filer (a 6-K only)
    mrows = [("AAA", "C0", "current_ticker"), ("BBB", "C1", "name_exact"), ("CCC", "C2", "current_ticker"), ("DDD", "C3", "current_ticker"), ("EEE", "C4", "current_ticker"), ("FFF", "C5", "current_ticker"), ("GGG", "C6", "current_ticker"),
             ("HHH", "C7", "current_ticker"), ("III", "C8", "current_ticker"), ("JJJ", "C9", "current_ticker"), ("LLL", "", "unmapped"), ("MMM", "C13", "current_ticker_name_mismatch"), ("M2", "", "name_ambiguous"), ("M3", "C13", "non_common"),
             ("M4", "C13", "odd_method"), ("M5", "C13", "name_exact"), ("NNN", "C99", "current_ticker"), ("OOO", "C14", "current_ticker"), ("PPP", "C15", "current_ticker"), ("QQQ", "C16", "current_ticker"), ("SSS", "C18", "current_ticker"),
             ("TTT", "C19", "current_ticker"), ("UUU", "C20", "current_ticker"), ("VVV", "C21", "current_ticker"), ("WWW", "C22", "current_ticker"), ("XXX", "C23", "current_ticker"), ("YYY", "C24", "current_ticker"), ("A01", "C26", "current_ticker"),
             ("BEF", "C27", "current_ticker"), ("ADR", "C28", "current_ticker")]                                                                                                          # KKK is not in the map at all
    F = np.ones((len(days), len(names)))
    F[:di("2017-09-15"), ix["BBB"]] = 2.0
    F[:di("2017-10-02"), ix["DDD"]] = 3.0
    F[:di("2016-05-16"), ix["EEE"]] = 2.0
    F[di("2017-04-20"):di("2017-05-05"), ix["SSS"]] = np.nan
    cal = cal_of([("BBB", "2017-09-15", "forward_split"), ("CCC", "2017-11-15", "reverse_split"), ("ZZZ", "2017-09-15", "forward_split"), ("AAA", "2030-01-02", "forward_split")])
    return days, names, rows, mrows, F, cal


def t_score():
    """the score on hand-made filings and a hand-made split factor, every rule on its own planted case with the exact ISS written out, then every field of every name at several ranks against the plain-python recount: S(r) = the usable value with the latest as-of date, S' the one closest to a - k
    years inside +-35 days (a tie to the earlier), the same-concept rule (the cover page first, else the balance sheet, never one value of each), the +1 session rule, the first-filed rule (an amendment never replaces), a split cancelling through F, [A3]'s two-way check (a calendar split F does not
    show - GE's 1-for-8 reverse split -, an F change the calendar does not show, F alone before the calendar's start), the ln(10) exclusion and the ln(1.5) flag, the static reasons, the foreign-filer exclusion, a' before the cache"""
    days, names, rows, mrows, F, cal = score_case()
    di = lambda s: int(days.get_loc(TS(s)))
    ix = {n: i for i, n in enumerate(names)}
    r = di("2018-06-29")
    W = score_world(days, names, F)
    frame = fr(rows)
    ni = attach_netiss(W, build_facts(frame), mp_of(mrows), cal)
    sc = score_rank(W, r)
    assert score_rank(W, r) is sc and ni.cal_start == TS("2016-06-01") and ni.cik_ix[ix["KKK"]] == -1
    code = lambda c, n: REASONS[int(sc[c].code[ix[n]])]
    iss = lambda c, n: float(sc[c].iss[ix[n]])
    exp = {"N12": {"AAA": ("scored", math.log(110 / 100)), "BBB": ("scored", math.log(105 / 100)), "CCC": ("split_calendar_not_in_F", None), "DDD": ("split_F_not_in_calendar", None), "EEE": ("scored", math.log(84 / 80)), "FFF": ("iss_over_ln10", None),
                    "GGG": ("scored", math.log(1.7)), "HHH": ("scored", math.log(190 / 200)), "III": ("scored", math.log(99 / 90)), "JJJ": ("no_band_pair", None), "KKK": ("not_in_map", None), "LLL": ("map_unmapped", None),
                    "MMM": ("map_mismatch", None), "M2": ("map_ambiguous", None), "M3": ("map_non_common", None), "M4": ("map_other", None), "M5": ("scored", math.log(110 / 100)), "NNN": ("no_facts_for_cik", None), "OOO": ("foreign_filer", None),
                    "PPP": ("no_usable_fact", None), "QQQ": ("value_not_positive", None), "SSS": ("no_split_factor", None), "TTT": ("scored", math.log(110 / 100)), "UUU": ("no_band_pair", None), "VVV": ("scored", math.log(130 / 100)),
                    "WWW": ("scored", math.log(100 / 80)), "XXX": ("scored", math.log(130 / 90)), "YYY": ("scored", math.log(100 / 80)), "A01": ("scored", math.log(110 / 100)), "BEF": ("a_prime_before_cache", None), "ADR": ("foreign_filer", None)},
           "N24": {"AAA": ("scored", math.log(110 / 90)), "BBB": ("no_band_pair", None), "EEE": ("scored", math.log(84 / 80)), "MMM": ("map_mismatch", None), "ADR": ("foreign_filer", None), "GGG": ("no_band_pair", None)}}
    for c, d in exp.items():
        for n, (want_code, want_iss) in d.items():
            assert code(c, n) == want_code, (c, n, code(c, n), want_code)
            if want_iss is not None:
                assert abs(iss(c, n) - want_iss) < 1e-12, (c, n, iss(c, n), want_iss)
            else:
                assert not math.isfinite(iss(c, n)), (c, n)
    # N24's one planted case with F alone: EEE's window (2016-04-29, 2018-04-27] starts before the calendar - the F change of 2016-05-16 stands on F alone and cancels: ln(84 / (40 x 2)); N12's window is covered and has no F change
    assert sc["N24"].f_alone[ix["EEE"]] and sc["N24"].straddle[ix["EEE"]] and not sc["N12"].f_alone[ix["EEE"]] and not sc["N12"].straddle[ix["EEE"]] and abs(iss("N24", "EEE") - math.log(84 / 80)) < 1e-12, "F alone before the calendar's start, counted"
    assert sc["N12"].straddle[ix["BBB"]] and abs(iss("N12", "BBB") - math.log(1.05)) < 1e-12 and not sc["N12"].f_alone[ix["BBB"]] and not sc["N12"].a3c[ix["BBB"]] and not sc["N12"].a3f[ix["BBB"]], "a split cancels through F and its calendar entry agrees"
    assert sc["N12"].a3c[ix["CCC"]] and not sc["N12"].a3f[ix["CCC"]] and abs(sc["N12"].fa[ix["CCC"]] - 1.0) < 1e-12 and abs(math.log(100 / 800) + 2.0794415416798357) < 1e-12 and abs(math.log(100 / 800)) < LN10, "GE's 1-for-8: the raw ISS ln(1/8) = -2.08 sits inside the ln(10) guard, the calendar check catches it"
    assert sc["N12"].a3f[ix["DDD"]] and not sc["N12"].a3c[ix["DDD"]]
    assert sc["N12"].ln10[ix["FFF"]] and abs(math.log(150 / 10)) > LN10 and not sc["N12"].scored[ix["FFF"]]
    assert sc["N12"].flag10[ix["GGG"]] and not sc["N12"].flag10[ix["AAA"]] and int(sc["N12"].flag10.sum()) == 1, "[A10] flags a scored |ISS| > ln(1.5), never a filter: GGG stays scored"
    assert sc["N12"].use[ix["AAA"]] == 1 and sc["N12"].use[ix["HHH"]] == 2 and sc["N12"].use[ix["III"]] == 2 and sc["N12"].fallback[ix["III"]] and not sc["N12"].fallback[ix["HHH"]], "the concept order: cover page first, else the balance sheet (a fallback only when the cover page has a value now)"
    assert sc["N12"].sg[ix["III"]] >= ni.dei.n and sc["N12"].pg[ix["III"]] >= ni.dei.n, "both values of a score come from the SAME concept (balance-sheet entries sit after the cover-page ones)"
    assert sc["N12"].stale[ix["AAA"]] and not sc["N12"].stale[ix["A01"]], "58 days before r is stale (<= 60), 150 days is not"
    assert sc["N12"].a[ix["XXX"]] == day_i("2018-06-27") and sc["N12"].a[ix["YYY"]] == day_i("2018-04-27"), "filed on the Thursday before r: usable at r; filed on r's own date: not yet"
    assert sc["N12"].sg[ix["WWW"]] >= 0 and ni.E_val[sc["N12"].sg[ix["WWW"]]] == 100.0, "the amendment (250) never replaces the first filed value"
    # the earlier ranks: a' before the cache's first session, and the first ranks that are partly unscored
    r2 = di("2017-01-31")
    s2 = score_rank(W, r2)
    assert REASONS[int(s2["N12"].code[ix["BEF"]])] == "a_prime_before_cache", REASONS[int(s2["N12"].code[ix["BEF"]])]
    assert brute_score(W, frame, cal, ix["BEF"], "C27", R_SCORED, r2, 1).code == R_BEFORE_CACHE
    # every field of every name at several ranks against the plain-python recount
    cik_of = {n: c for n, c, _m in mrows}
    n_chk = compare_scores(W, frame, cal, names, cik_of, [di("2016-12-30"), r2, di("2017-12-29"), di("2018-02-28"), r, di("2018-07-02"), di("2019-06-28"), di("2020-06-30")])
    assert n_chk == 8 * 2 * len(names)
    # the static reasons by method, and the mapped-without-facts / foreign counts
    st = {names[i]: REASONS[int(ni.static[i])] for i in range(len(names))}
    assert st["LLL"] == "map_unmapped" and st["NNN"] == "no_facts_for_cik" and st["OOO"] == st["ADR"] == "foreign_filer" and st["M5"] == "scored" and st["KKK"] == "not_in_map" and st["AAA"] == "scored"
    # a score world with no calendar start at all: every window rests on F alone (counted), the two-way check never fires
    W2 = score_world(days, names, F)
    ni2 = attach_netiss(W2, build_facts(frame), mp_of(mrows), cal_of([("CCC", "2017-11-15", "reverse_split")], start=None))
    s3 = score_rank(W2, r)
    assert ni2.cal_start is None and s3["N12"].f_alone[ix["CCC"]] and REASONS[int(s3["N12"].code[ix["CCC"]])] == "scored" and REASONS[int(s3["N12"].code[ix["DDD"]])] == "scored" and s3["N12"].f_alone[ix["DDD"]], "without a calendar the check is F alone"


def random_case(seed, S_=14):
    """RANDOM hand-made filings, split factors and calendars for the recount: quarterly cover-page filings with jittered dates (weekends included) and values, balance-sheet filings, later comparatives that restate, amendments, missing / zero / typo values, same-day duplicate
    accessions with another value, foreign filers, forward and reverse splits that F and the calendar both show (the calendar a few sessions off now and then), only F shows or only the calendar shows (GE's case), calendar splits with no change anywhere, and a calendar that starts
    at a random date or not at all; the rows are shuffled (the first-filed rule must not depend on the file's order) -> (days, names, rows frame, map rows, F, calendar)"""
    rng = np.random.default_rng(seed)
    days = pd.bdate_range("2016-01-04", "2019-12-31")
    T = len(days)
    names = [f"R{j:02d}" for j in range(S_)]
    rows, mrows, F, splits, n_acc = [], [], np.ones((T, S_)), [], [0]
    for j in range(S_):
        cik = f"K{j}"
        mrows.append((names[j], cik, "current_ticker"))
        form = "20-F" if rng.random() < 0.1 else "10-Q"
        s0, g = rng.uniform(50.0, 500.0), rng.normal(0.0, 0.08)
        mult = []
        if rng.random() < 0.4:
            s, m, u = int(rng.integers(150, T - 150)), float(rng.choice([2.0, 3.0, 4.0, 0.5, 0.2, 0.125])), rng.random()
            ty = "forward_split" if m > 1 else "reverse_split"
            if u < 0.6:                                                                    # F and the calendar both show it
                F[:s, j] = m
                splits.append((names[j], days[min(T - 1, max(0, s + int(rng.integers(-2, 3))))], ty))
            elif u < 0.75:                                                                 # F shows it, the calendar does not
                F[:s, j] = m
            elif u < 0.9:                                                                  # the calendar shows it, F does not
                splits.append((names[j], days[s], ty))
            mult.append((days[s], m))
        if rng.random() < 0.1:
            splits.append((names[j], days[int(rng.integers(100, T - 100))], "forward_split"))
        shares = lambda t_: float(round(s0 * math.exp(g * (t_ - TS("2016-01-01")).days / 365.25) * (1.0 + rng.normal(0.0, 0.02)) * math.prod(m for d_, m in mult if d_ <= t_)))

        def value(t_):
            u = rng.random()
            return float("nan") if u < 0.03 else 0.0 if u < 0.05 else shares(t_)

        def put(con, end, filed, val):
            n_acc[0] += 1
            rows.append((cik, con, val, end, filed, f"{cik}-{n_acc[0]:04d}", form))
        for q in range(-2, 19):
            qe = TS("2015-12-31") + pd.DateOffset(months=3 * q)
            if rng.random() < 0.85:
                end = qe + pd.Timedelta(days=int(rng.integers(15, 45)))
                filed = end + pd.Timedelta(days=int(rng.integers(1, 8))) if rng.random() > 0.02 else end - pd.Timedelta(days=5)
                v = value(end)
                put(DEI, end, filed, v)
                if rng.random() < 0.08:
                    put(DEI, end, filed + pd.Timedelta(days=int(rng.integers(10, 60))), v * float(rng.uniform(0.5, 2.0)))                       # an amendment: another value, later
                if rng.random() < 0.02:
                    put(DEI, end, filed, v * 1.1)                                                                                           # the same day, another accession, another value
            if rng.random() < 0.75:
                filed = qe + pd.Timedelta(days=int(rng.integers(25, 60)))
                v = value(qe)
                put(GAAP, qe, filed, v)
                if rng.random() < 0.15:
                    put(GAAP, qe - pd.DateOffset(months=12), filed, shares(qe - pd.DateOffset(months=12)) * float(rng.uniform(0.9, 1.1)))   # a later comparative that restates the year-old value
    perm = rng.permutation(len(rows))
    cal_start = [None, "2016-06-01", "2017-02-01"][int(rng.integers(0, 3))]
    return days, names, fr([rows[i] for i in perm]), mrows, F, cal_of(splits, cal_start)


def t_pairs():
    """the point-in-time search on RANDOM filings against the plain-python recount: every name, both cells, six random ranks of each of five worlds - the reason code, the concept, ISS and every flag; the rows' order is shuffled, the dates fall on weekends, values go missing, zero or typo, amendments and
    comparatives restate, splits are shown by F, by the calendar, by both or by neither, the calendar starts at a random date or not at all"""
    n_chk, kinds = 0, Counter()
    for seed in (1, 2, 3, 4, 5):
        days, names, frame, mrows, F, cal = random_case(seed)
        W = score_world(days, names, F)
        fx = build_facts(frame)
        ni = attach_netiss(W, fx, mp_of(mrows), cal)
        rng = np.random.default_rng(seed + 100)
        ranks = sorted(int(x) for x in rng.choice(np.arange(60, W.T - 2), 6, replace=False))
        n_chk += compare_scores(W, frame, cal, names, {n: c for n, c, _m in mrows}, ranks)
        for rk in ranks:
            for c in CELLS:
                kinds.update(REASONS[int(v)] for v in score_rank(W, rk)[c].code)
        # the order of the rows never matters: the same World built from the sorted frame scores identically
        fx2 = build_facts(frame.sort_values(["cik", "end", "filed", "accn"]).reset_index(drop=True))
        W2 = score_world(days, names, F)
        attach_netiss(W2, fx2, mp_of(mrows), cal)
        for c in CELLS:
            a, b = score_rank(W, ranks[3])[c], score_rank(W2, ranks[3])[c]
            assert np.array_equal(a.code, b.code) and np.array_equal(np.nan_to_num(a.iss, nan=9.0), np.nan_to_num(b.iss, nan=9.0)), (seed, c)
        assert ni.fx.info["ciks"] == S_CHK(names)
    assert n_chk == 5 * 6 * 2 * 14 and kinds["scored"] > 200, (n_chk, kinds)
    assert all(kinds[k] > 0 for k in ("foreign_filer", "a_prime_before_cache", "no_band_pair", "value_not_positive", "split_calendar_not_in_F", "split_F_not_in_calendar")), kinds
    # pairs_for_concept itself on a hand-made entry table: S = the latest usable as-of date, S' the closest to a - k years (ties: the earlier), the band edges, unusable entries never candidates
    days = pd.bdate_range("2017-01-02", "2019-12-31")
    di = day_i(days)

    def tab(items):                                      # (cik index, end, first filed, value, usable)
        a = sorted(items, key=lambda x: (x[0], x[1]))
        ent = SimpleNamespace(ck=np.array([x[0] for x in a], np.int64), end=day_i([x[1] for x in a]), f1=day_i([x[2] for x in a]), val=np.array([x[3] for x in a], float), ok=np.array([x[4] for x in a], bool),
                              accn=np.array([""] * len(a), object), form=np.array([""] * len(a), object), n=len(a))
        return bind(ent, di)
    ent = tab([(0, "2018-04-27", "2018-05-02", 110, True), (0, "2017-04-27", "2017-05-02", 100, True), (0, "2017-03-23", "2017-04-01", 90, True), (0, "2017-05-31", "2017-06-02", 95, True), (1, "2018-04-27", "2018-05-02", 10, True),
               (1, "2017-03-22", "2017-04-01", 9, True), (2, "2018-06-30", "2018-07-03", 7, True), (2, "2018-04-27", "2018-05-02", 6, True), (2, "2017-04-27", "2017-05-02", 5, False), (2, "2017-04-30", "2017-05-02", 4, True)])
    r = int(days.get_loc(TS("2018-06-29")))
    s, sp = pairs_for_concept(ent, r, 1, np.array([0, 1, 2, -1, 5]))
    assert ent.end[s[0]] == day_i("2018-04-27") and ent.end[sp[0]] == day_i("2017-04-27") and ent.val[sp[0]] == 100.0, "S' = the exact one-year-back date wins over entries 35 and 34 days off"
    assert ent.end[s[1]] == day_i("2018-04-27") and sp[1] == -1, "36 days off: outside the band"
    assert ent.end[s[2]] == day_i("2018-04-27") and ent.end[sp[2]] == day_i("2017-04-30") and ent.val[sp[2]] == 4.0, "the 2018-06-30 entry is first filed after r: S is the 2018-04-27 one; the unusable 2017-04-27 entry is never a candidate; the 2017-04-30 one is"
    assert s[3] == -1 and sp[3] == -1 and s[4] == -1 and sp[4] == -1, "no CIK / a CIK with no entry"
    s2_, sp2 = pairs_for_concept(ent, r, 2, np.array([0, 1, 2]))
    assert s2_.tolist() == s.tolist()[:3] and sp2.tolist() == [-1, -1, -1], "no entry two years back"
    e2 = tab([(0, "2018-04-27", "2018-05-02", 110, True), (0, "2017-04-17", "2017-05-02", 100, True), (0, "2017-05-07", "2017-05-12", 120, True)])
    s, sp = pairs_for_concept(e2, r, 1, np.array([0]))
    assert e2.val[sp[0]] == 100.0, "ten days either side of the target: the earlier"
    e3 = tab([(0, "2018-04-27", "2018-06-28", 110, True), (0, "2017-04-27", "2017-05-02", 100, True)])
    assert pairs_for_concept(e3, r, 1, np.array([0]))[0][0] == 1 and pairs_for_concept(e3, r - 1, 1, np.array([0]))[0][0] == 0, "filed Thursday 06-28: usable at Friday's close (the first session after it is Friday), not before it"
    e4 = tab([(0, "2018-04-27", "2018-06-29", 110, True), (0, "2017-04-27", "2017-05-02", 100, True)])
    assert e4.val[pairs_for_concept(e4, r, 1, np.array([0]))[0][0]] == 100.0, "filed on r's own date: not usable at r's close"
    assert pairs_for_concept(tab([]), r, 1, np.array([0, 1]))[0].tolist() == [-1, -1]


def S_CHK(names):
    return len(names)


def t_sides():
    """the sides: 150 scored names or more -> 50 a side, fewer -> the top / bottom THIRD (floor) when that is at least 20 a side, else nothing; the longs are the k LOWEST ISS and the shorts the k HIGHEST (ties: the shorts take the lower symbol, the longs the higher), the sides never share
    a name; ten equal-count ISS deciles (the remainder of n / 10 to the first deciles, ties by symbol order)"""
    assert [side_n(n) for n in (500, 150, 149, 100, 61, 60, 59, 20, 1, 0)] == [(50, "top"), (50, "top"), (49, "third"), (33, "third"), (20, "third"), (20, "third"), (0, "none"), (0, "none"), (0, "none"), (0, "none")]
    with spec(n_side=15, min_scored=45, min_side=10):
        assert [side_n(n) for n in (100, 45, 44, 30, 29)] == [(15, "top"), (15, "top"), (14, "third"), (10, "third"), (0, "none")]
    cols = np.array([10, 11, 12, 13, 14, 15])
    score = np.array([0.1, 0.1, 0.5, 0.5, -0.2, -0.2])
    lg, sh = pick_sides(cols, score, 2)
    assert sorted(lg.tolist()) == [4, 5] and sorted(sh.tolist()) == [2, 3], "the 2 lowest are the longs, the 2 highest the shorts"
    lg, sh = pick_sides(cols, score, 1)
    assert lg.tolist() == [5] and sh.tolist() == [2], "a tie: the short takes the LOWER symbol, the long the HIGHER"
    rng = np.random.default_rng(3)
    for n, k in ((30, 10), (47, 15), (150, 50), (151, 50), (20, 10)):
        sc_ = np.round(rng.normal(0.0, 0.2, n), 1)                                   # rounding makes ties
        cs_ = np.sort(rng.choice(np.arange(1000), n, replace=False))
        lg, sh = pick_sides(cs_, sc_, k)
        order = sorted(range(n), key=lambda i: (-sc_[i], cs_[i]))                      # highest first, ties by symbol
        want_sh = order[:k]
        want_lg = sorted(range(n), key=lambda i: (sc_[i], -cs_[i]))[:k]
        assert sorted(sh.tolist()) == sorted(want_sh) and sorted(lg.tolist()) == sorted(want_lg) and not set(lg.tolist()) & set(sh.tolist()), (n, k)
        assert len(set(lg.tolist())) == len(lg) == k == len(sh)
    for n in (10, 23, 99, 150):
        sc_ = np.round(rng.normal(0.0, 0.2, n), 2)
        cs_ = np.sort(rng.choice(np.arange(1000), n, replace=False))
        lab = decile_labels(cs_, sc_)
        want = np.zeros(n, int)
        o = sorted(range(n), key=lambda i: (sc_[i], cs_[i]))
        sizes = [n // 10 + (1 if d < n % 10 else 0) for d in range(10)]
        pos = 0
        for d, sz in enumerate(sizes):
            for i in o[pos:pos + sz]:
                want[i] = d
            pos += sz
        assert lab.tolist() == want.tolist() and np.bincount(lab, minlength=10).tolist() == sizes, n
        assert all(sc_[lab == d].max() <= sc_[lab == d + 1].min() for d in range(9)), "deciles are ordered: 0 = the lowest ISS"
    c0 = cell0()
    assert c0.n == 0 and c0.k == 0 and c0.mode == "none" and not c0.traded and len(c0.idx) == 0 and c0.dec is None and c0.U is None
    U = SimpleNamespace(G=np.arange(12.0).reshape(4, 3), ve=np.arange(4.0), st=np.array([True, False, False, True]), mk=np.arange(12.0).reshape(4, 3) + 1, div=np.arange(8.0).reshape(4, 2))
    u2 = slice_units(U, np.array([3, 1]))
    assert u2.G.tolist() == [[9.0, 10.0, 11.0], [3.0, 4.0, 5.0]] and u2.ve.tolist() == [3.0, 1.0] and u2.st.tolist() == [True, False] and u2.div.tolist() == [[6.0, 7.0], [2.0, 3.0]] and u2.mk.shape == (2, 3)


def ni_toy(seed=1, T=620, Sn=14, twin=()):
    """r17_resmom's toy world (14 names, the registered windows, the planted hygiene / dividend / spin-off / stopped-print cases) on T sessions (from 2024-01-01, so the cache's first session is 2024-01-01 and N24 is scored from the 2026-01 ranks) with hand-made filings: quarterly cover-page
    values with an annual issuance rate each (N13 the highest: the clear short), and the planted cases - N00 a 2-for-1 split on 2025-03-14 (F shows it, the calendar too: it cancels), N02 a foreign filer (20-F), N03 not in the map, N04 in the map with no filing, N05 a x100 scale error in one
    filing (|ISS| > ln(10)), N06 balance-sheet only, N08 a cover page that starts 2024-10 (the balance sheet stands in: the fallback), N09 an amendment with another value (the first filed stands), N10 a x1.7 stock-paid jump (the [A10] flag), N11 a filing on a weekend, N12 a filing the day
    before a rank's close; N00 .. N13 early (filings from 2023-10: N24 can score them) or late (from 2024-10) -> SimpleNamespace(W, frame, mrows, cal, cik_of). Sn > 14 adds plain early filers (N14 ..); twin = ((a, b), ..): [A13] the symbol N{b} is a second share class of N{a} - it
    maps to N{a}'s CIK and has no filing of its own (the same two facts: the same ISS wherever both are scored)"""
    W = M17.toy_world(seed, T=T, Sn=Sn)
    rng = np.random.default_rng(seed + 50)
    syms = [str(s) for s in W.syms]
    g = np.linspace(-0.15, 0.45, Sn)[np.random.default_rng(seed).permutation(Sn)]
    g[13] = 0.60
    base = rng.uniform(80.0, 400.0, Sn) * 1e6
    early = {0, 1, 3, 5, 6, 7, 9, 10, 11, 12, 13} | set(range(14, Sn))
    second = {b: a for a, b in twin}
    rows, mrows = [], []
    n_acc = [0]

    def put(cik, con, val, end, filed, form="10-Q"):
        n_acc[0] += 1
        rows.append((cik, con, float(val), end, filed, f"{cik}-{n_acc[0]:04d}", form))
    for j, sym in enumerate(syms):
        cik = f"K{second.get(j, j)}"
        if j != 3:
            mrows.append((sym, cik, "current_ticker"))
        if j == 4 or j in second:
            continue
        t = TS("2023-10-20") if j in early else TS("2024-10-20")
        if j == 8:
            t = TS("2024-10-20")
        while t < W.days[-1] + pd.Timedelta(days=20):
            val = base[j] * math.exp(g[j] * (t - TS("2023-01-01")).days / 365.25) * (1.0 + rng.normal(0.0, 0.004))
            if sym == "N00" and t >= TS("2025-03-14"):
                val *= 2.0
            if sym == "N10" and t >= TS("2025-03-20"):
                val *= 2.0
            filed = t + pd.Timedelta(days=4)
            if sym == "N05" and TS("2025-01-01") <= t <= TS("2025-03-31"):
                val *= 100.0
            if sym == "N11":
                filed = t + pd.Timedelta(days=int((5 - t.dayofweek) % 7 or 7))                                  # a Saturday
            if sym == "N12":
                filed = t + pd.Timedelta(days=int(rng.integers(1, 4)))
            con, form = (GAAP, "10-K") if sym == "N06" else (DEI, "20-F" if sym == "N02" else "10-Q")
            if sym == "N08":
                put(cik, GAAP, val * 0.999, t - pd.Timedelta(days=20), filed)                                       # the balance sheet at the quarter end, filed with the cover
            if not (sym == "N07" and t >= TS("2025-02-01")):
                put(cik, con, val, t, filed, form)
            if sym == "N09":
                put(cik, con, val * 1.5, t, filed + pd.Timedelta(days=30), "10-Q/A")
            t += pd.Timedelta(days=91 + int(rng.integers(0, 7)))
        if sym == "N08":                                                                                         # N08's balance sheet starts a year earlier than its cover page
            for q in range(4):
                put(cik, GAAP, base[j] * math.exp(g[j] * (TS("2023-10-01") + pd.Timedelta(days=91 * q) - TS("2023-01-01")).days / 365.25), TS("2023-10-01") + pd.Timedelta(days=91 * q) - pd.Timedelta(days=20), TS("2023-10-01") + pd.Timedelta(days=91 * q) + pd.Timedelta(days=4))
    cal = cal_of([("N00", "2025-03-14", "forward_split")], start="2024-01-01")
    return SimpleNamespace(W=W, frame=fr(rows), mrows=mrows, cal=cal, cik_of={n: c for n, c, _m in mrows})


def brute_side(n):
    """plain python: (names a side, mode) for n scored names"""
    if n >= SPEC["min_scored"]:
        return M17.SPEC["n_side"], "top"
    k = n // 3
    return (k, "third") if k >= SPEC["min_side"] else (0, "none")


def brute_iota(W, j, b):
    """plain python: iota = ISS - ln(total return / price return) over the window (a', a] = the sum over its sessions of ln(1 + D* / the split-adjusted close of that session), the dividends the calendar states on the split-adjusted basis (M17.brute_div_amt)"""
    tot = 0.0
    for s in range(b.iap + 1, b.ia + 1):
        d, ac = M17.brute_div_amt(W, s, j), W.Cl[s, j] / W.F[s, j]
        if d > 0 and math.isfinite(ac) and ac > 0:
            tot += math.log1p(d / ac)
    return b.iss - tot


def brute_dv(W, f, j):
    """plain python [A13]: the mean RAW dollar volume of the 20 sessions before the fill (rows f-20 .. f-1) of the World column j - NaN unless all 20 are present"""
    v = [float(W.Cl[s, j]) * float(W.Vv[s, j]) for s in range(f - 20, f)]
    return sum(v) / 20.0 if all(math.isfinite(x) for x in v) else float("nan")


def brute_second(W, f, sc, cik_of):
    """plain python [A13]: of the scored names (World columns) that share a CIK, every one but the winner - a tournament on 'the larger dollar volume wins, an undefined one loses to any defined one, a tie goes to the lower SYMBOL' -> {dropped column: kept column}"""
    by = defaultdict(list)
    for j in sorted(sc):
        cik = cik_of.get(str(W.syms[j]), "")
        if cik:
            by[cik].append(j)
    out = {}
    for _cik, js in by.items():
        best = js[0]
        for j in js[1:]:
            dj, db = brute_dv(W, f, j), brute_dv(W, f, best)
            dj, db = (dj if math.isfinite(dj) else -math.inf), (db if math.isfinite(db) else -math.inf)
            if dj > db or (dj == db and str(W.syms[j]) < str(W.syms[best])):
                best = j
        out.update({j: best for j in js if j != best})
    return out


def brute_ni(W, frame, cal, cik_of, lo, hi, post_mode="remove"):
    """every rebalance whose position exits in [lo, hi], plain python end to end - the schedule from the months of consecutive sessions, the universe from W.U, the pool re-implemented with loops (>= 230 own returns and ES pairs, an open at the fill, the pre / old / post hygiene windows and the [D2]
    spin-offs, the audit), each cell's score by brute_score (the filings, the splits and the calendar), the sides by brute_side, the picks by plain sorts, the composite twin's score and picks, the deciles: [{r, f, x, pool: {col: (naive, window spins, hold spin)}, cell: {c: {...}}, counts}]"""
    sp = M17.SPEC
    Sp = getattr(W, "Sp_in", None)
    key = [(W.days[i].year, W.days[i].month) for i in range(W.T)]
    ranks = [i for i in range(W.T - 1) if key[i] != key[i + 1]]
    cache, recs = {}, []
    for k, r in enumerate(ranks):
        f, x = r + 1, (ranks[k + 1] + 1 if k + 1 < len(ranks) else -1)
        if x < 0 or not (lo <= W.days[x] <= hi) or r < sp["win"] - 1:
            continue
        a, lo_pre = M17.windows(r)[0], r - sp["skip"] - sp["hyg_lead"] + 1
        pool, n_hold, n_wnames, n_wsess = {}, 0, 0, 0
        for j in [j for j in range(W.S) if W.U[f, j]]:
            hold = Sp is not None and any(bool(Sp[s, j]) for s in range(f + 1, x + 1))
            win = 0 if Sp is None else sum(1 for s in range(max(a, 0), r + 1) if s >= 1 and Sp[s, j] and math.isfinite(W.Cl[s, j] / W.F[s, j]) and math.isfinite(W.Cl[s - 1, j] / W.F[s - 1, j]))
            n_hold, n_wnames, n_wsess = n_hold + int(hold), n_wnames + int(win > 0), n_wsess + win
            rets = [(s, M17.brute_ret(W, s, j)) for s in range(a, r + 1)]
            n_ret = sum(math.isfinite(y) for _s, y in rets)
            n_pair = sum(math.isfinite(y) and math.isfinite(float(W.es.ret[s])) for s, y in rets)
            if n_ret < sp["min_n"] or n_pair < sp["min_n"] or not math.isfinite(W.Od[f, j] / W.F[f, j]):
                continue
            pre = any(any(D15.brute_flags(W, s, j)) for s in range(max(lo_pre, 0), r + 1))
            old = any(any(D15.brute_flags(W, s, j)[1:]) for s in range(max(a, 0), lo_pre))
            post = hold or any(any(D15.brute_flags(W, s, j)) for s in range(r + 1, x + 1))
            Cs = getattr(W, "CSPL", None)
            known = hold or (Cs is not None and any(bool(Cs[s, j]) for s in range(f + 1, x + 1)))              # [A18] an announced split / a [D2] ex-date inside the hold
            if pre or old or W.aud1[f, j] or (post and post_mode == "remove") or (known and post_mode == "keep"):
                continue
            pool[j] = (bool(post and post_mode == "naive"), win, hold)
        rec = {"r": r, "f": f, "x": x, "pool": pool, "cell": {}, "n_hold_names": n_hold, "n_win_names": n_wnames, "n_win_sessions": n_wsess}
        for c, kk in KS.items():
            sc, codes = {}, {}
            for j in pool:
                b = brute_score(W, frame, cal, j, cik_of.get(str(W.syms[j]), ""), int(W.ni.static[j]), r, kk, cache)
                codes[j] = b.code
                if b.code == R_SCORED:
                    sc[j] = b
            n_pre, second = len(sc), brute_second(W, f, sc, cik_of)                    # [A13] among the pool names WITH a score, one class per CIK
            for j in second:
                codes[j] = R_SECOND_CLASS
                del sc[j]
            iota = {j: brute_iota(W, j, sc[j]) for j in sc}
            k_side, mode = brute_side(len(sc))
            o = {"scored": sc, "codes": codes, "iota": iota, "k": k_side, "mode": mode, "long": [], "short": [], "long_i": [], "short_i": [], "dec": {}, "second": second, "n_pre": n_pre}
            if k_side > 0:
                o["short"] = sorted(sc, key=lambda j: (-sc[j].iss, j))[:k_side]
                o["long"] = sorted(sc, key=lambda j: (sc[j].iss, -j))[:k_side]
                o["short_i"] = sorted(sc, key=lambda j: (-iota[j], j))[:k_side]
                o["long_i"] = sorted(sc, key=lambda j: (iota[j], -j))[:k_side]
            if len(sc) >= SPEC["dec_min"]:
                order = sorted(sc, key=lambda j: (sc[j].iss, j))
                sizes = [len(sc) // SPEC["dec_n"] + (1 if d < len(sc) % SPEC["dec_n"] else 0) for d in range(SPEC["dec_n"])]
                pos = 0
                for d, sz in enumerate(sizes):
                    for j in order[pos:pos + sz]:
                        o["dec"][j] = d
                    pos += sz
            rec["cell"][c] = o
        recs.append(rec)
    return recs


def compare_ni(W, L, Bz, tag):
    """the vectorised build against the plain-python recount: the schedule, every pool (names, naive flags, [D2] counts), per cell every scored name with its ISS and composite iota, the mode and side size, the picks of both rules, the deciles, the first-reason counts, and the daily path of EVERY scored
    name under four costings (base, 10 bps, the 3% borrow stress with k_t, longs at -100%) -> the number of paths checked"""
    assert len(L.recs) == len(Bz), (tag, len(L.recs), len(Bz))
    cfgs = (("base", D15.l1_cfg(), {}), ("10 bps", D15.l1_cfg(bps=10.0), {"bps": 10.0}), ("borrow 3%", D15.l1_cfg(borrow=(BORROW, 0.03)), {"borrow": (BORROW, 0.03), "k": True}), ("lose100", D15.l1_cfg(lose100=True), {"lose100": True}))
    n_paths = 0
    want_cnt = defaultdict(Counter)
    for rec, b in zip(L.recs, Bz):
        assert (rec.r, rec.f, rec.x) == (b["r"], b["f"], b["x"]), tag
        assert rec.pool.tolist() == sorted(b["pool"]), (tag, rec.r, rec.pool.tolist(), sorted(b["pool"]))
        assert rec.naive.tolist() == [b["pool"][j][0] for j in rec.pool], (tag, rec.r)
        assert rec.spin_win.tolist() == [b["pool"][j][1] for j in rec.pool] and rec.spin_hold.tolist() == [b["pool"][j][2] for j in rec.pool], (tag, rec.r, "the [D2] counts per pool name")
        y = int(W.days[b["f"]].year)
        for c in CELLS:
            cc, bc = rec.cell[c], b["cell"][c]
            cols = rec.pool[cc.idx]
            assert cols.tolist() == sorted(bc["scored"]), (tag, rec.r, c, cols.tolist(), sorted(bc["scored"]))
            assert close(cc.score, [bc["scored"][j].iss for j in cols]) and close(cc.iota, [bc["iota"][j] for j in cols]), (tag, rec.r, c, "ISS / iota")
            assert (cc.k, cc.mode, cc.n) == (bc["k"], bc["mode"], len(bc["scored"])) and cc.traded == (bc["k"] > 0), (tag, rec.r, c, cc.k, cc.mode, cc.n, bc["k"], bc["mode"])
            assert dict(zip(cc.second.tolist(), cc.kept.tolist())) == bc["second"] and cc.n_pre == len(bc["scored"]) + len(bc["second"]) and len(cc.second) == len(cc.kept), (tag, rec.r, c, "[A13] the second share classes", cc.second.tolist(), bc["second"])
            assert not set(cc.second.tolist()) & set(cols.tolist()) and set(cc.kept.tolist()) <= set(cols.tolist()), (tag, rec.r, c, "a second class is out of the scored names, the class that stays is in")
            want_cnt[y][f"scored_{c}"] += len(bc["scored"])
            want_cnt[y][f"no_score_{c}"] += len(b["pool"]) - len(bc["scored"])
            want_cnt[y][f"mode_{c}_{bc['mode']}"] += 1 if len(b["pool"]) else 0
            for j, code in bc["codes"].items():
                if code != R_SCORED:
                    want_cnt[y][f"ns_{c}_{REASONS[code]}"] += 1
            if len(b["pool"]) and len(bc["scored"]) >= SPEC["dec_min"]:
                want_cnt[y][f"dec_{c}"] += 1
            elif len(b["pool"]):
                want_cnt[y][f"dec_none_{c}"] += 1
            if len(bc["scored"]) >= SPEC["dec_min"]:
                assert cc.dec.tolist() == [bc["dec"][j] for j in cols], (tag, rec.r, c, "deciles")
            else:
                assert cc.dec is None
            if not cc.traded:
                continue
            assert cols[cc.long].tolist() == bc["long"] and cols[cc.short].tolist() == bc["short"], (tag, rec.r, c, "the picks")
            assert cols[cc.long_i].tolist() == bc["long_i"] and cols[cc.short_i].tolist() == bc["short_i"], (tag, rec.r, c, "the composite twin's picks")
            assert not set(bc["long"]) & set(bc["short"]) and not set(bc["long_i"]) & set(bc["short_i"]), "a name is never on both sides"
            assert sorted(cc.score[cc.long]) == sorted(cc.score)[:cc.k] and sorted(cc.score[cc.short]) == sorted(cc.score)[-cc.k:], "the longs are the k LOWEST ISS, the shorts the k HIGHEST"
            kt = W.k[rec.f:rec.x + 1]
            idx = np.arange(cc.n)
            for nm, cfg, kw in cfgs:
                for sd in (1, -1):
                    P = D15.l1_pnl(cc.U, idx, sd, cfg, kt)
                    for i, j in enumerate(cols):
                        want, _ = M17.brute_path(W, rec.f, rec.x, int(j), sd, bool(rec.naive[cc.idx[i]]), bps=kw.get("bps", COST_BPS), borrow=kw.get("borrow", (BORROW, None)), kt=kt if kw.get("k") else None, lose100=kw.get("lose100", False))
                        assert close(P[i], want), (tag, nm, rec.r, c, int(j), sd)
                        n_paths += 1
    for key, bk in (("spin_window_names", "n_win_names"), ("spin_window_sessions", "n_win_sessions"), ("spin_hold_names", "n_hold_names")):
        assert sum(c.get(key, 0) for c in L.cnt.values()) == sum(b[bk] for b in Bz), (tag, key)
    for y, w in want_cnt.items():
        for k_, v in w.items():
            assert L.cnt[y][k_] == v, (tag, y, k_, L.cnt[y][k_], v)
    return n_paths


def series_check_ni(W, L, Bz):
    """each cell's daily series (run_cell on r15's L1 engine, $4,000 a name) and the composite twin's equal the sum of the recount's position paths booked on rows f .. x"""
    for cell in CELLS:
        for alt in (False, True):
            x0 = np.zeros(W.T)
            for b in Bz:
                bc = b["cell"][cell]
                if bc["k"] == 0:
                    continue
                for sd, js in ((1, bc["long_i" if alt else "long"]), (-1, bc["short_i" if alt else "short"])):
                    for j in js:
                        x0[b["f"]:b["x"] + 1] += M17.SPEC["slot"] * np.array(M17.brute_path(W, b["f"], b["x"], j, sd, b["pool"][j][0])[0])
            assert close(M17.run_cell(W, cell_leg(L, cell, alt=alt), D15.l1_cfg()).x, x0), f"{cell} series (composite twin {alt})"


def t_pipeline():
    """the vectorised build against the plain-python recount on the toy world with the REGISTERED windows (252 / 230), in both readings, 3 names a side (the 150 / thirds / 20 rule shrunk to 8 / 2), then the planted cases one by one: every pool, every score, the sides, both rules' picks, the
    deciles, the counts and the daily path of every scored name"""
    with spec(n_side=3, min_scored=8, min_side=2, dec_min=7), D15.spec(univ=14):
        tt = ni_toy()
        W = tt.W
        attach_netiss(W, build_facts(tt.frame), mp_of(tt.mrows), tt.cal)
        W.aud1[W.days.get_loc(TS("2025-02-03")), 8] = True                                  # N08: a hand-audit data event at fill session 2025-02-03 (the rebalance ranked 2025-01-31)
        lo, hi = W.days[0], W.days[-1]
        out, n = {}, 0
        for pm in ("remove", "naive", "keep"):
            L = ni_build(W, lo, hi, pm)
            Bz = brute_ni(W, tt.frame, tt.cal, tt.cik_of, lo, hi, pm)
            n += compare_ni(W, L, Bz, f"toy {pm}")
            out[pm] = (L, Bz)
            if pm == "remove":
                series_check_ni(W, L, Bz)
        Lr, Lk = out["remove"][0], out["naive"][0]
        by = lambda L_, d: next(r_ for r_ in L_.recs if W.days[r_.r] == TS(d))
        modes = Counter((c, rec.cell[c].mode) for rec in Lr.recs for c in CELLS if len(rec.pool))
        assert modes[("N12", "top")] >= 3 and modes[("N12", "third")] >= 1 and modes[("N12", "none")] >= 3 and modes[("N24", "none")] >= 1 and modes[("N24", "third")] >= 1, modes      # the toy world exercises the top-n side, the thirds and the nothing months
        scored12, scored24 = [rec.cell["N12"].n for rec in Lr.recs], [rec.cell["N24"].n for rec in Lr.recs]
        assert max(scored12) >= 8 and max(scored24) >= 6 and scored24[0] == 0 and scored12[0] == 0, (scored12, scored24)
        # the first ranks: the cache's first session is 2024-01-01, so nothing is scored before a' can fall on or after it (N12: ranks from 2025-02 on; N24 from 2026-02)
        assert all(rec.cell["N12"].n == 0 for rec in Lr.recs if W.days[rec.r] < TS("2025-02-01")) and all(rec.cell["N24"].n == 0 for rec in Lr.recs if W.days[rec.r] < TS("2026-02-01"))
        # the planted cases through the whole pipeline
        s_all = {rec.r: score_rank(W, rec.r)["N12"] for rec in Lr.recs}
        r_ = by(Lr, "2025-05-30")
        sc = s_all[r_.r]
        cd = lambda n_: REASONS[int(sc.code[n_])]
        assert cd(2) == "foreign_filer" and cd(3) == "not_in_map" and cd(4) == "no_facts_for_cik" and cd(0) == "scored" and sc.straddle[0], "N00's split cancels through F (and the calendar agrees)"
        cols = r_.pool[r_.cell["N12"].idx].tolist()
        assert all(j not in cols for j in (2, 3, 4)) and 0 in cols
        assert any(REASONS[int(s_.code[5])] == "iss_over_ln10" for s_ in s_all.values()), "N05's x100 filing is excluded at |ISS| > ln(10) at some rank"
        assert any(s_.flag10[10] for s_ in s_all.values()), "N10's x2 stock-paid jump is an [A10] flag at some rank"
        assert any(s_.fallback[8] for s_ in s_all.values()) and any(s_.use[6] == 2 for s_ in s_all.values()), "the balance sheet stands in for N08 (a fallback) and is N06's only concept"
        # the K reading differs from the registered one only by the in-hold names (more names in the pool, never fewer)
        for a_, b_ in zip(Lr.recs, Lk.recs):
            assert set(a_.pool.tolist()) <= set(b_.pool.tolist())
        # [A18] the judged 'keep' reading = the look-ahead pool less the names with an announced split / a [D2] ex-date inside the hold, never on the raw path; kept_flagged counts the flagged names that stay
        LK, n_kept = out["keep"][0], 0
        for b_, k_ in zip(Lk.recs, LK.recs):
            known = set(np.flatnonzero(np.asarray(W.CSPL[k_.f + 1:k_.x + 1]).any(axis=0)).tolist()) | {int(j) for j in b_.pool[b_.spin_hold]}
            assert set(k_.pool.tolist()) == set(b_.pool.tolist()) - known and not k_.naive.any(), (W.days[k_.r], k_.pool.tolist(), b_.pool.tolist(), sorted(known))
            n_kept += len({int(j) for j in b_.pool[b_.naive]} - known)
        assert sum(c.get("kept_flagged", 0) for c in LK.cnt.values()) == n_kept, ("kept_flagged", n_kept)
        for y, c in LK.cnt.items():
            assert c["universe"] == sum(c[k_] for k_ in COUNT_KEYS[1:]), (y, dict(c))
        # the audit: N08 at fill 2025-02-03 is gone from the pool of the 01-31 rank (and counted)
        assert 8 not in by(Lr, "2025-01-31").pool.tolist() and Lr.cnt[2025]["audit"] >= 1 and (AUD, int(W.days.get_loc(TS("2025-02-03"))), 8) in W.aud_hit
        # a counts-only build keeps no unit path and no pick but counts the same scored names and modes
        Lc = ni_build(W, lo, hi, "remove", units=False, counts_only=True)
        assert [rec.pool.tolist() for rec in Lc.recs] == [rec.pool.tolist() for rec in Lr.recs] and all(rec.U is None and not len(rec.cell["N12"].long) for rec in Lc.recs)
        for y, c in Lr.cnt.items():
            for k_ in [k2 for k2 in c if k2.startswith(("scored_", "no_score_", "mode_", "ns_", "dec_"))]:
                assert Lc.cnt[y][k_] == c[k_], (y, k_)
            assert c["universe"] == sum(c[k_] for k_ in COUNT_KEYS[1:]), (y, dict(c))
        assert sum(rec.cell[c].traded for rec in Lc.recs for c in CELLS) == sum(rec.cell[c].traded for rec in Lr.recs for c in CELLS)
        W.aud1[:] = False
    return n


def toy_ready(**kw):
    """the toy world with its filings attached, built under the shrunk SPEC the callers hold -> (W, the facts frame, the calendar, the CIK map)"""
    tt = ni_toy(**kw)
    attach_netiss(tt.W, build_facts(tt.frame), mp_of(tt.mrows), tt.cal)
    return tt


def t_nulls():
    """the family-aware null: 500 uniform draws per rebalance of as many names as the cell holds from the same eligible SCORED pool (here 3 / 2 a side), seeded, one stream per cell (and per reading), longs and shorts disjoint, no P&L before the first fill, the mean over the draws equal to the
    pool's mean path, three whole draws recounted by plain python (the draw's names from the same stream, every path and the sizing recomputed), the statistic = the MAX over the 2 cells per draw -> p5 / p50 / p95, and the DO of every draw against the reference's drawdown days"""
    with spec(n_side=3, min_scored=8, min_side=2), D15.spec(univ=14):
        tt = toy_ready()
        W = tt.W
        L = ni_build(W, W.days[0], W.days[-1])
        acc = ni_null(W, L, 400, 0)
        assert set(acc) == set(CELLS) and all(a.shape == (400, W.T) for a in acc.values())
        kz0 = W.kz.copy()
        W.kz[:] = 2.5                                                                       # the volatility lean of r15's S cells: this family has none - k_t is read only by the borrow stress
        assert all((ni_null(W, L, 400, 0)[c] == acc[c]).all() for c in CELLS)
        W.kz[:] = kz0
        cfg, slot = D15.l1_cfg(), M17.SPEC["slot"]
        first_fill = min(rec.f for rec in L.recs if any(rec.cell[c].traded for c in CELLS))
        for cell in CELLS:
            exp = 0.0
            for rec in L.recs:
                cc = rec.cell[cell]
                if cc.traded:
                    idx = np.arange(cc.n)
                    kt = W.k[rec.f:rec.x + 1]
                    exp += slot * cc.k * float(D15.l1_pnl(cc.U, idx, 1, cfg, kt).mean(axis=0).sum() + D15.l1_pnl(cc.U, idx, -1, cfg, kt).mean(axis=0).sum())
            tot = acc[cell].sum(axis=1)
            assert abs(tot.mean() - exp) < 4.5 * tot.std() / math.sqrt(len(tot)), (cell, tot.mean(), exp, tot.std())
            assert (acc[cell][:, :first_fill] == 0).all(), "no P&L before the first fill"
        again = ni_null(W, L, 400, 0)
        assert all((again[c] == acc[c]).all() for c in CELLS), "seeded"
        assert not (ni_null(W, L, 400, 1)["N12"] == acc["N12"]).all(), "the other reading draws a different stream"
        assert not (acc["N12"] == acc["N24"]).all() or not any(rec.cell["N24"].traded for rec in L.recs), "own stream per cell"
        # three whole draws recounted: the stream's names for each traded rebalance in order, every path by plain python
        for q, cell in enumerate(CELLS):
            rng = np.random.default_rng([SEED, q, 0])
            draws = []
            for rec in L.recs:
                cc = rec.cell[cell]
                if cc.traded:
                    draws.append((rec, D15.draw_order(rng, 400, cc.n, 2 * cc.k)))
            for d in (0, 1, 399):
                x0 = np.zeros(W.T)
                for rec, o in draws:
                    cc = rec.cell[cell]
                    cols = rec.pool[cc.idx]
                    names = o[d]
                    assert len(set(names.tolist())) == 2 * cc.k and not set(names[:cc.k].tolist()) & set(names[cc.k:].tolist()), "a draw's longs and shorts are disjoint names of the scored pool"
                    for sd, sel in ((1, names[:cc.k]), (-1, names[cc.k:])):
                        for i in sel:
                            x0[rec.f:rec.x + 1] += slot * np.array(M17.brute_path(W, rec.f, rec.x, int(cols[i]), sd, bool(rec.naive[cc.idx[i]]))[0])
                assert close(acc[cell][d], x0), (cell, d)
    # the statistic: the max over the 2 cells per draw, then p5 / p50 / p95; the DO the same way
    ix = pd.bdate_range("2016-07-01", "2025-06-27")
    rng = np.random.default_rng(2)
    book = rng.normal(35.0, 650.0, len(ix))
    S12 = M12.Stretch(book, ix, None, WF0, PRE_END)
    pc = {c: D15.null_cell(S12, rng.normal(5, 100, (40, len(ix))), np.arange(len(ix)), len(ix))[0] for c in CELLS}
    pdo = {c: rng.normal(0.0, 0.2, 40) for c in CELLS}
    ns = null_summary(pc, pdo, SEED)
    mx = np.max(np.vstack([pc[c] for c in CELLS]), axis=0)
    mdo = np.max(np.vstack([pdo[c] for c in CELLS]), axis=0)
    assert ns["draws"] == 40 and ns["seed"] == SEED and all(abs(ns["roc_max"][k] - np.percentile(mx, v)) < 1e-9 for k, v in (("p5", 5), ("p50", 50), ("p95", 95)))
    assert all(abs(ns["do_ref_max"][k] - np.percentile(mdo, v)) < 1e-9 for k, v in (("p5", 5), ("p50", 50), ("p95", 95))) and set(ns["do_ref_by_cell"]) == set(CELLS) and ns["roc_max"]["p95"] >= max(ns["by_cell"][c]["p95"] for c in CELLS) - 1e-9
    assert "do_ref_max" not in null_summary(pc) and null_summary(pc)["seed"] == SEED


def t_twins():
    """[A5] the ten deciles of ISS as long-only baskets and their spread over ES (every session of every hold recounted by plain python, the baskets' name-months add up to the scored names), [A7] the composite-issuance twin's score on hand dividends (iota = ISS - the sum of ln(1 + D / close) over
    the window's sessions), [A6] the ES hedge's ratio (the OLS slope with an intercept of the cell's own daily P&L on ES over the 252 sessions before the rank, zero before 252 sessions of its own exist, zero under 230 pairs) and the hedged series on hand numbers (the overlay's P&L and its cost)"""
    with spec(n_side=3, min_scored=8, min_side=2, dec_min=7), D15.spec(univ=14):
        tt = toy_ready()
        W, slot = tt.W, M17.SPEC["slot"]
        L = ni_build(W, W.days[0], W.days[-1])
        cell = "N12"
        x, sp, nn, nr = decile_series(W, L, cell)
        assert x.shape == sp.shape == (10, W.T) and nn.shape == (10,) and nr == sum(1 for rec in L.recs if rec.cell[cell].dec is not None) > 3
        assert int(nn.sum()) == sum(rec.cell[cell].n for rec in L.recs if rec.cell[cell].dec is not None), "every scored name is in exactly one decile"
        Bz = brute_ni(W, tt.frame, tt.cal, tt.cik_of, W.days[0], W.days[-1], "remove")
        want, want_sp = np.zeros((10, W.T)), np.zeros((10, W.T))
        es = np.nan_to_num(np.asarray(W.es.ret, float))
        for b in Bz:
            bc = b["cell"][cell]
            if len(bc["scored"]) < SPEC["dec_min"]:
                continue
            for d in range(10):
                js = [j for j, v in bc["dec"].items() if v == d]
                if not js:
                    continue
                g = sum(slot * np.array(M17.brute_path(W, b["f"], b["x"], j, 1, b["pool"][j][0])[0]) for j in js)
                want[d, b["f"]:b["x"] + 1] += g
                want_sp[d, b["f"]:b["x"] + 1] += g - slot * len(js) * es[b["f"]:b["x"] + 1]
        assert close(x, want) and close(sp, want_sp), "the deciles' baskets and their spread over ES, from raw closes, factors and the calendar's cash"
        # the deciles' mean ISS rises with the decile (the labels are an ISS sort)
        for rec in L.recs:
            cc = rec.cell[cell]
            if cc.dec is not None:
                means = [cc.score[cc.dec == d].mean() for d in range(10) if (cc.dec == d).any()]
                assert means == sorted(means)
        B, _S12 = M17.synth_book(seed=15)
        rowsB = A13.book_rows(B, W)
        ds = decile_stats(B, rowsB, W, L, cell)
        assert ds["ranks_cut"] == nr and [q["decile"] for q in ds["deciles"]] == list(range(1, 11)) and sum(q["name_months"] for q in ds["deciles"]) == int(nn.sum())
        k = B.mask(WF0, PRE_END)
        s0 = R11.stats(D15.to_B(x[0], rowsB, B.n)[k], B.index[k])
        assert abs(ds["deciles"][0]["net"] - s0["net"]) < 1e-9 and abs(ds["deciles"][0]["usd_year"] - s0["net"] / s0["years"]) < 1e-9
    # [A7] iota on hand dividends: ln(total return / price return) over (a', a] = the sum of ln(1 + D* / Ac) on the dividend sessions inside the window
    days = pd.bdate_range("2016-01-04", "2019-12-31")
    di = lambda s_: int(days.get_loc(TS(s_)))
    rows = [("C0", DEI, 100, "2017-04-28", "2017-05-03"), ("C0", DEI, 110, "2018-04-27", "2018-05-02"), ("C1", DEI, 100, "2017-04-28", "2017-05-03"), ("C1", DEI, 110, "2018-04-27", "2018-05-02")]
    Ac = np.full((len(days), 2), 50.0)
    Dv = np.zeros((len(days), 2))
    for s_ in ("2017-06-15", "2017-09-15", "2017-12-15", "2018-03-15", "2017-04-27", "2018-04-30"):          # 2017-04-27 is a' - 1 day... the window is (a', a] = (2017-04-28, 2018-04-27]
        Dv[di(s_), 0] = 1.0
    Ac[di("2017-09-15"), 0] = 40.0
    W2 = score_setup(days, ["AAA", "BBB"], rows, F=None, Ac=Ac, Dv=Dv)
    sc = score_rank(W2, di("2018-06-29"))["N12"]
    iss = math.log(1.1)
    inside = [("2017-06-15", 50.0), ("2017-09-15", 40.0), ("2017-12-15", 50.0), ("2018-03-15", 50.0)]
    want = iss - sum(math.log1p(1.0 / ac) for _d, ac in inside)
    assert abs(sc.iss[0] - iss) < 1e-12 and abs(sc.iota[0] - want) < 1e-12 and abs(sc.iss[1] - sc.iota[1]) < 1e-15, "iota = ISS - the dividends of the window's sessions (a' and the sessions before / after the window never count)"
    assert sc.iota[0] < sc.iss[0], "cash distributions count as negative issuance"
    # [A6] the hedge ratio: OLS (intercept + slope) of the cell's own daily P&L on ES over the 252 sessions r-251 .. r, zero until 252 sessions of the cell's own P&L exist before the rank, zero under 230 pairs
    T = 700
    rng = np.random.default_rng(5)
    es_r = rng.normal(0.0003, 0.01, T)
    es_r[0] = np.nan
    xs = 2500.0 * es_r + 40.0 + rng.normal(0.0, 150.0, T)
    xs[:300] = 0.0
    xs = np.nan_to_num(xs)
    rec = lambda r_, f_, x_, tr=True: SimpleNamespace(r=r_, f=f_, x=x_, cell={"N12": SimpleNamespace(traded=tr)})
    recs = [rec(299, 300, 320), rec(540, 541, 560), rec(551, 552, 570), rec(600, 601, 640), rec(650, 651, 690, tr=False)]
    Wh = SimpleNamespace(es=SimpleNamespace(ret=es_r), T=T)
    Lh = SimpleNamespace(recs=recs)
    br = hedge_ratios(Wh, xs, Lh, "N12")
    assert set(br) == {0, 1, 2, 3} and br[0] == 0.0 and br[1] == 0.0, "no ratio before 252 sessions of the cell's own P&L exist (the first fill is row 300: ranks from row 551 on)"
    for i in (2, 3):
        r_ = recs[i].r
        pairs = [(xs[s], es_r[s]) for s in range(r_ - 251, r_ + 1) if np.isfinite(es_r[s])]
        coef = np.linalg.lstsq(np.array([[1.0, m] for _y, m in pairs]), np.array([y for y, _m in pairs]), rcond=None)[0]
        assert abs(br[i] - coef[1]) < 1e-8 * max(1.0, abs(coef[1])) and 0.0 < br[i] < 5000.0, (i, br[i], coef[1])
    es_h = es_r.copy()
    es_h[(np.arange(T) > 400) & (np.arange(T) < 520)] = np.nan                                           # 119 holes in the window of rank 600 -> 133 pairs: under 230 -> no hedge
    assert hedge_ratios(SimpleNamespace(es=SimpleNamespace(ret=es_h), T=T), xs, Lh, "N12")[3] == 0.0
    # the hedged series: short b x ES's return on every session of the hold, 0.5 bps of |b| at the fill and at the exit (a session with no ES return earns nothing)
    hs, br2 = hedged_series(Wh, xs, Lh, "N12")
    want = xs.copy()
    c = DV.ES_EXACT_BPS * 1e-4
    for i, b_ in br2.items():
        r_ = recs[i]
        for s in range(r_.f, r_.x + 1):
            want[s] -= b_ * (es_r[s] if np.isfinite(es_r[s]) else 0.0)
        want[r_.f] -= c * abs(b_)
        want[r_.x] -= c * abs(b_)
    assert close(hs, want) and br2 == br and not np.array_equal(hs, xs) and close(hs[:552], xs[:552]) and close(hs[700 - 1:], xs[700 - 1:])


def t_judge():
    """Stage A's (a)-(e) as r17_resmom's with the cell's own years: N12 needs 6 positive July-June years, N24 two thirds of the years it holds a position in, rounded up (n = 7 -> 5, 8 -> 6, 9 -> 6, 3 -> 2, 1 -> 1); the null is the max over the 2 cells; the tie-break between two passing
    cells; [A6]'s credit rule on hand betas (both within 0.20, inclusive; NaN never credited); MANAGER #70's gate on hand numbers with the credit; dollars a year"""
    R = RULES
    st0 = {"n_units": 100, "roc": 20.0, "net": 1000.0, "years_pos": 7, "net_ex2020": 500.0, "net_ex_best_days": 100.0, "net_ex_best_pos": 100.0}
    nul0 = {"roc_max": {"p95": 10.0}}
    ck = judge_cell(st0, 50.0, nul0, "N12", 9)
    names = [f"rebalances>={R['reb']}", f"ROC>={R['roc']:g}", "net>0 at 5 bps", "net>0 at 10 bps", "ROC>null p95", f"positive in >={R['years']} of 9 July-June years", "net>0 without Feb 15 - Apr 30 2020", "profitable without its best 1% of days", "profitable without its best 1% of name-months"]
    assert list(ck) == names and all(ck.values()) and all(isinstance(v, bool) for v in ck.values()), ck
    nan = float("nan")

    def broken(cell="N12", n_years=9, **kw):
        st, net10, nul = dict(st0), 50.0, nul0
        for k, v in kw.items():
            if k == "net10":
                net10 = v
            elif k == "p95":
                nul = {"roc_max": {"p95": v}}
            else:
                st[k] = v
        return {k for k, v in judge_cell(st, net10, nul, cell, n_years).items() if not v}
    assert broken(n_units=59) == {names[0]} and broken(n_units=60) == set() and broken(roc=14.99) == {names[1]} and broken(roc=15.0) == set() and broken(roc=15.0, p95=15.0) == {names[4]} and broken(roc=15.0, p95=14.99) == set()
    assert broken(net=0.0) == {names[2]} and broken(net10=0.0) == {names[3]} and broken(net_ex2020=0.0) == {names[6]} and broken(net_ex_best_days=0.0) == {names[7]} and broken(net_ex_best_pos=0.0) == {names[8]}
    assert broken(years_pos=5) == {names[5]} and broken(years_pos=6) == set(), "N12: at least 6 positive years, inclusive"
    assert broken(roc=nan) == {names[1], names[4]} and broken(net=nan) == {names[2]} and broken(years_pos=nan) == {names[5]} and broken(net_ex_best_pos=nan) == {names[8]}, "a NaN never passes"
    for n, need in ((9, 6), (8, 6), (7, 5), (6, 4), (3, 2), (2, 2), (1, 1)):
        lab = f"positive in >={need} of {n} July-June years"
        assert lab in judge_cell(st0, 50.0, nul0, "N24", n), (n, need, list(judge_cell(st0, 50.0, nul0, "N24", n)))
        assert broken("N24", n, years_pos=need - 1) == {lab} and broken("N24", n, years_pos=need) == set() and broken("N24", n, years_pos=n) == set(), (n, need)
    assert judge_cell({**st0, "years_pos": 5}, 50.0, nul0, "N24", 7)["positive in >=5 of 7 July-June years"] and not judge_cell({**st0, "years_pos": 5}, 50.0, nul0, "N12", 7)["positive in >=6 of 7 July-June years"], "N12's 6 is fixed, N24's follows its years"
    # the tie-break and Stage A's bookkeeping
    mk = lambda v12, v24, roc=(20.0, 30.0): {"N12": {"PASS": v12, "base": {"roc": roc[0]}}, "N24": {"PASS": v24, "base": {"roc": roc[1]}}}
    assert stage_a_flow(mk(True, True)) == (["N12", "N24"], "N24") and stage_a_flow(mk(True, True, roc=(30.0, 30.0)))[1] == "N12" and stage_a_flow(mk(True, False, roc=(16.0, 90.0))) == (["N12"], "N12") and stage_a_flow(mk(False, False)) == ([], None)
    # [A6] the credit rule: BOTH betas within +-0.20 of one side's notional ($200,000 = 50 x $4,000)
    def with_betas(dd, al):
        stub = lambda B_, S12_, W_, rows_, xB_: {"DD days": {"usd_per_1.00_es": dd}, "all WF days": {"usd_per_1.00_es": al}}
        with patched(D15, es_beta=stub):
            return beta_credit(None, None, None, None, None)
    side = M17.SPEC["n_side"] * M17.SPEC["slot"]
    b = with_betas(30000.0, 20000.0)
    assert b["side_notional"] == side == 200000.0 and abs(b["beta_dd_days"] - 0.15) < 1e-12 and abs(b["beta_all_days"] - 0.10) < 1e-12 and b["within_cap"] is True and b["cap"] == 0.20
    assert with_betas(40000.0, 0.0)["within_cap"] is True and with_betas(-40000.0, 0.0)["within_cap"] is True, "|beta| = 0.20 exactly is within the cap"
    assert with_betas(40001.0, 0.0)["within_cap"] is False and with_betas(0.0, -41000.0)["within_cap"] is False and with_betas(nan, 0.0)["within_cap"] is False and with_betas(0.0, nan)["within_cap"] is False, "either beta over 0.20, or one that cannot be computed: no credit"
    # MANAGER #70's gate on hand numbers, with the credit
    ref_g = SimpleNamespace(structure={"episodes": 3, "days": 41})
    cg = {"seat_ref": {"DO": 0.20, "rho_dd": 0.1}, "episode_pnl": [100.0, -20.0, 50.0], "beta": {"within_cap": True}}
    nul = {"do_ref_max": {"p5": -0.1, "p50": 0.05, "p95": 0.15}}
    g = gate70(cg, ref_g, nul)
    assert g["DO"] == 0.20 and g["DO_above_null_p95"] is True and g["pnl_without_best_episode"] == 30.0 and g["positive_without_best_episode"] is True and g["episodes_helped"] == 2 and g["credited"] is True and g["null_do_p95"] == 0.15
    g = gate70({**cg, "seat_ref": {"DO": 0.15, "rho_dd": 0.0}, "episode_pnl": [100.0, -80.0, 10.0], "beta": {"within_cap": False}}, ref_g, nul)
    assert g["DO_above_null_p95"] is False and g["positive_without_best_episode"] is False and g["pnl_without_best_episode"] == -70.0 and g["credited"] is False and g["episodes_helped"] == 2
    assert "null_do_p95" not in gate70(cg, ref_g, None)
    # dollars a year = net / years (the house yardstick's years); NaN where there are none
    assert per_year(1000.0, 4.0) == 250.0 and not math.isfinite(per_year(1000.0, 0.0)) and not math.isfinite(per_year(1000.0, nan)) and per_year(-30.0, 3.0) == -10.0
    # years_held: the July-June years in which the cell holds a position on at least one WF day
    ix = pd.bdate_range("2016-07-01", "2025-06-27")
    Bq = SimpleNamespace(index=ix, n=len(ix), mask=lambda a, b_: np.asarray((ix >= a) & (ix <= b_)))
    cnt = np.zeros(len(ix))
    cnt[(ix >= "2018-03-01") & (ix <= "2018-03-31")] = 5
    cnt[(ix >= "2019-07-01") & (ix <= "2019-07-31")] = 5
    assert years_held(Bq, cnt) == [2017, 2019], "March 2018 is the 2017-18 year, July 2019 the 2019-20 year"
    assert years_held(Bq, np.zeros(len(ix))) == []


def t_reference():
    """[X1] / [A12] through r18_divrun on stubbed series only: A2 is the reference (#463 + 0.264 x RES) + c x the cell against the reference with c by the registered volatility rule on EACH CELL'S OWN window (N12 2017-02-01 .. 2019-01-31, N24 2018-02-01 .. 2020-01-31: 25% of #463's daily std /
    the cell's), 0.5c and 2c reported, the plain #463 + c x cell a reported row; the dollars a year (net / years) beside every ROC - the reference's, the reference + c x the cell at c / 0.5c / 2c and the plain book - recounted by plain python; an incremental pass needs ROC and Sortino both
    strictly above the reference's; the beta rule is the credit"""
    B, S12 = M17.synth_book(seed=3, hi="2026-06-30")
    k = np.flatnonzero(B.mask(WF0, PRE_END))
    ref = DV.mk_ref(B)
    rng = np.random.default_rng(8)
    for cell, (w0, w1) in A2_WINS.items():
        mw = B.mask(w0, w1)
        assert int(mw.sum()) > 400 and B.index[mw][0] == w0 and B.index[mw][-1] == w1
        for lab, xB in (("profitable and quiet", 40.0 + rng.normal(0.0, 50.0, B.n)), ("losing", -30.0 + rng.normal(0.0, 300.0, B.n)), ("noise", rng.normal(5.0, 300.0, B.n))):
            a2 = a2_report(B, xB, ref, cell)
            sb, sc = float(np.std(B.raw[mw], ddof=1)), float(np.std(xB[mw], ddof=1))
            c_ = 0.25 * sb / sc
            assert a2["window"] == [f"{w0:%Y-%m-%d}", f"{w1:%Y-%m-%d}"] and a2["rows"] == int(mw.sum()) and a2["target"] == 0.25 and abs(a2["c"] - c_) <= 1e-9 * c_ and abs(a2["std_book"] - sb) <= 1e-9 * sb and abs(a2["std_cell"] - sc) <= 1e-9 * sc, (cell, lab, a2["window"], a2["c"], c_)
            assert a2["at_half_c"]["c"] == 0.5 * a2["c"] and a2["at_double_c"]["c"] == 2.0 * a2["c"] and a2["book_shadow_line"] is a2["incremental_pass"]
            ref_s = DV.plain_stats(ref.raw[k], B.index[k])
            yrs = float(ref.stats["years"])
            assert abs(a2["reference"]["roc"] - ref_s["roc"]) < 1e-5 and abs(a2["reference"]["usd_year"] - ref_s["net"] / yrs) < 1e-6 and a2["reference"]["weight_of_RES"] == 0.264
            for got, mult in ((a2, 1.0), (a2["at_half_c"], 0.5), (a2["at_double_c"], 2.0)):
                w_ = DV.plain_stats((ref.raw + mult * c_ * xB)[k], B.index[k])
                assert abs(got["roc"] - w_["roc"]) < 1e-5 and abs(got["sortino"] - w_["sortino"]) < 1e-7 and abs(got["net"] - w_["net"]) < 1e-3 and abs(got["usd_year"] - w_["net"] / yrs) < 1e-6, (cell, lab, mult)
            wp_ = DV.plain_stats((B.raw + c_ * xB)[k], B.index[k])
            assert abs(a2["plain_463"]["roc"] - wp_["roc"]) < 1e-5 and abs(a2["plain_463"]["usd_year"] - wp_["net"] / yrs) < 1e-6, "the plain #463 + c x cell book is a reported row with its dollars a year"
            assert a2["incremental_pass"] is bool(a2["roc"] > a2["reference"]["roc"] and a2["sortino"] > a2["reference"]["sortino"]), lab
            if lab == "profitable and quiet":
                assert a2["incremental_pass"] is True and a2["roc_gain"] > 0 and a2["sortino_gain"] > 0
            if lab == "losing":
                assert a2["incremental_pass"] is False and a2["roc_gain"] < 0
            assert plain_a2(B, xB, cell)["c"] == a2["c"] and plain_a2(B, xB, cell)["window"] == a2["window"], "Stage B recomputes the frozen c on the cell's own window"
        ax = a2_report(B, np.zeros(B.n), ref, cell)
        assert ax["incremental_pass"] is False and "error" in ax and ax["at_half_c"] is None, "a cell with no spread over the window has no c: no incremental pass, never an exception"
    assert A2_WINS["N12"][0] != A2_WINS["N24"][0] and plain_a2(B, 40.0 + rng.normal(0.0, 50.0, B.n), "N12")["window"] != plain_a2(B, 40.0 + rng.normal(0.0, 50.0, B.n), "N24")["window"], "the two cells have their own windows"


FACT_HDR = ["cik", "symbols", "concept", "unit", "val", "start", "end", "accn", "fy", "fp", "form", "filed", "frame"]


def write_facts(path, rows, header=None, crlf=False):
    """a flat share-count file in the registered layout (13 columns); a row = (cik, concept, val, end, filed[, form[, accn[, unit[, start]]]]); val / end / filed are written as given (a test may write garbage)"""
    hdr = FACT_HDR if header is None else header
    out = []
    for r in rows:
        cik, con, val, end, filed = r[:5]
        form = r[5] if len(r) > 5 and r[5] is not None else "10-Q"
        accn = r[6] if len(r) > 6 and r[6] is not None else f"{cik}-{end}-{filed}-{con[-4:]}"
        unit = r[7] if len(r) > 7 and r[7] is not None else "shares"
        start = r[8] if len(r) > 8 and r[8] is not None else ""
        d = {"cik": cik, "symbols": "S;T", "concept": con, "unit": unit, "val": val, "start": start, "end": end, "accn": accn, "fy": "2018", "fp": "Q1", "form": form, "filed": filed, "frame": ""}
        out.append(",".join(str(d[c]) for c in hdr))
    with open(path, "w", newline="") as f:
        f.write(("\r\n" if crlf else "\n").join([",".join(hdr)] + out) + ("\r\n" if crlf else "\n"))
    return M17.sha_raw(path)


def write_map(path, rows, header=("symbol", "cik", "method", "name")):
    with open(path, "w", newline="\n") as f:
        f.write("\n".join([",".join(header)] + [",".join(list(r) + [f"{r[0]} Inc"]) if len(header) == 4 else ",".join(r) for r in rows]) + "\n")
    return M17.sha_raw(path)


def t_files():
    """[A1] / [A8] the four pinned files on hand-made copies: each refused if its sha256 differs or it is not on file; the map read as ONE map (a symbol with a usable row in both refused, an additions row over an unusable base row supersedes it and is counted by the base row's method, a symbol twice
    in one file refused, the symbol 'NA' is a symbol, only current-ticker / exact-name / reviewed rows with a CIK are usable); the flat file read as ONE table (a fact row or a CIK in both refused; the cut at read: a row filed on / after it refused - dropped and counted when the extract is not strict -,
    an as-of date on / after it, an unreadable date, a unit other than 'shares' and a concept other than the three dropped and counted, a missing value kept for the first-filed rule to refuse; the columns checked; the table asserted free of the sealed year)"""
    root = tempfile.mkdtemp(prefix="netiss_selftest_")
    try:
        p = lambda n: os.path.join(root, n)
        files = {"facts": p("shares_asfiled_wide.csv"), "facts_add": p("shares_asfiled_additions_reviewed.csv"), "map": p("map_wide.csv"), "map_add": p("map_additions.csv")}
        base_f = [("0000000001", DEI, 100, "2018-03-31", "2018-05-02"), ("0000000001", DEI, 105, "2018-06-30", "2018-08-02"), ("0000000002", GAAP, 50, "2018-03-31", "2018-05-02", "10-K"), ("0000000002", WAC, 49, "2018-03-31", "2018-05-02", "10-K", None, "shares", "2017-04-01")]
        add_f = [("0000000003", DEI, 70, "2018-03-31", "2018-05-02"), ("0000000003", DEI, 71, "2018-06-30", "2018-08-02")]
        base_m = [("AAA", "0000000001", "current_ticker"), ("BBB", "0000000002", "name_exact"), ("CCC", "", "unmapped"), ("NA", "0000000009", "current_ticker"), ("DDD", "0000000001", "current_ticker"), ("EEE", "0000000004", "name_ambiguous")]
        add_m = [("CCC", "0000000003", "reviewed_same_firm")]

        def pin(bf=base_f, af=add_f, bm=base_m, am=add_m):
            shas = {"facts": write_facts(files["facts"], bf), "facts_add": write_facts(files["facts_add"], af), "map": write_map(files["map"], bm), "map_add": write_map(files["map_add"], am)}
            return patched(THIS, FILES=dict(files), FILE_SHA=shas)
        with pin():
            mp = load_map()
            df = mp.df.set_index("symbol")
            assert sorted(df.index) == ["AAA", "BBB", "CCC", "DDD", "EEE", "NA"] and df.loc["CCC", "source"] == "additions" and df.loc["CCC", "cik"] == "0000000003" and df.loc["AAA", "source"] == "base", "NA is a symbol, not a missing value"
            assert df["usable"].to_dict() == {"AAA": True, "BBB": True, "CCC": True, "DDD": True, "EEE": False, "NA": True}
            i = mp.info
            assert i["base_rows"] == 6 and i["additions_rows"] == 1 and i["rows"] == 6 and i["usable_symbols"] == 5 and i["usable_ciks"] == 4 and i["ciks_with_two_or_more_symbols"] == 1 and i["additions_superseding_unusable_base_rows"] == {"unmapped": 1}
            assert i["by_method"] == {"current_ticker": 3, "name_exact": 1, "name_ambiguous": 1, "reviewed_same_firm": 1} and i["sha256"] == {k: M17.sha_raw(files[k]) for k in ("map", "map_add")}
            d, fi = load_facts(S.LB0)
            assert len(d) == 6 and fi["files"] == {"facts": 4, "facts_add": 2} and fi["rows_read"] == 6 and fi["rows"] == 6 and fi["rows_filed_on_or_after_the_cut"] == 0 and fi["rows_by_concept"] == {DEI: 4, GAAP: 1, WAC: 1}
            assert str(d["filed"].dtype).startswith("datetime64") and str(d["end"].dtype).startswith("datetime64") and d["cik"].tolist().count("0000000003") == 2 and d["val"].dtype == float and list(d.columns) == FACT_FRAME_COLS
            assert d.loc[d["concept"] == WAC, "start"].iloc[0] == TS("2017-04-01") and fi["rows_by_form"] == {"10-Q": 4, "10-K": 2}
            fx = build_facts(d)
            assert fx.ciks.tolist() == ["0000000001", "0000000002", "0000000003"] and fx.dei.n == 4 and fx.gaap.n == 1 and fx.wa.n == 1
        # the map: a symbol with a usable row in BOTH files, a symbol twice in a file, a row without a CIK / with another method in the additions, a missing column, another sha, an absent file
        with pin(am=[("AAA", "0000000008", "reviewed_same_firm")]):
            refused(load_map, "AAA", "BOTH", "(nothing computed, lockbox NOT read)")
        with pin(bm=base_m + [("AAA", "0000000007", "current_ticker")]):
            refused(load_map, "more than once", "AAA")
        with pin(am=[("CCC", "0000000003", "reviewed_same_firm"), ("CCC", "0000000004", "reviewed_same_firm")]):
            refused(load_map, "more than once")
        with pin(am=[("GGG", "", "reviewed_same_firm")]):
            refused(load_map, "without a CIK or with a method outside")
        with pin(am=[("GGG", "0000000003", "current_ticker")]):
            refused(load_map, "without a CIK or with a method outside")
        with pin():
            sh = write_map(files["map"], base_m, header=("symbol", "cik"))
            with patched(THIS, FILE_SHA={**FILE_SHA, "map": sh}):
                refused(load_map, "lacks the column", "method")
        with pin():
            with patched(THIS, FILE_SHA={**FILE_SHA, "map": "0" * 64}):
                refused(load_map, "is not the registered", "symbol -> CIK map", "(nothing computed, lockbox NOT read)")
            with patched(THIS, FILES={**FILES, "map_add": p("absent.csv")}):
                refused(load_map, "is not on file", "reviewed map additions")
        # the flat file: the same checks, the cut at read time, the rows that are not read
        with pin(af=add_f + [("0000000003", DEI, 72, "2025-06-30", "2025-06-30")]):
            refused(lambda: load_facts(S.LB0), "filed on / after the cut", "(nothing computed, lockbox NOT read)")
            d, fi = load_facts(S.LB0, strict_cut=False)
            assert fi["rows_filed_on_or_after_the_cut"] == 1 and len(d) == 6 and d["filed"].max() < S.LB0, "dropped and counted, the table is asserted free of the sealed year"
        with pin(bf=base_f + [("0000000001", DEI, 1, "2018-09-30", "2025-07-02")]):
            refused(lambda: load_facts(S.LB0), "filed on / after the cut")
        junk = [("0000000005", DEI, 10, "2099-01-01", "2018-05-02"), ("0000000005", DEI, 10, "2018-03-31", "not-a-date"), ("0000000005", DEI, 10, "", "2018-05-02"), ("0000000005", DEI, 10, "2018-03-31", "2018-05-02", "10-Q", None, "USD"),
                ("0000000005", "us-gaap:Foo", 10, "2018-03-31", "2018-05-02"), ("0000000005", DEI, "", "2018-06-30", "2018-08-02"), ("0000000005", DEI, "abc", "2018-09-30", "2018-11-02"), ("0000000005", DEI, 12, "2018-12-31", "2019-02-02", " 10-k ")]
        with pin(bf=base_f + junk):
            d, fi = load_facts(S.LB0)
            assert fi["rows_end_on_or_after_the_cut"] == 1 and fi["rows_unreadable_date"] == 2 and fi["rows_unit_not_shares"] == 1 and fi["rows_other_concept"] == 1 and fi["rows_value_missing"] == 2 and fi["rows_read"] == 6 + 8 and fi["rows"] == 6 + 3, fi
            assert d[d["cik"] == "0000000005"]["val"].isna().sum() == 2 and (d["form"] == "10-K").sum() == 3, "a missing value is kept (the first-filed rule makes the entry unusable); the form is stripped and upper-cased"
            e, c = entries_of(d[(d["concept"] == DEI) & (d["cik"] == "0000000005")])
            assert c["value_missing"] == 2 and not e["ok"].iloc[[0, 1]].any()
        row0 = base_f[2]
        with pin(af=[(row0[0], row0[1], row0[2], row0[3], row0[4], row0[5], f"{row0[0]}-{row0[3]}-{row0[4]}-{row0[1][-4:]}")]):
            refused(lambda: load_facts(S.LB0), "fact row(s) are in BOTH", "no silent overlap", "(nothing computed, lockbox NOT read)")
        with pin(af=[("0000000002", DEI, 55, "2018-12-31", "2019-02-02")]):
            refused(lambda: load_facts(S.LB0), "have rows in BOTH", "0000000002")
        with pin(bf=base_f):
            with patched(THIS, FILE_SHA={**FILE_SHA, "facts": "0" * 64}):
                refused(lambda: load_facts(S.LB0), "is not the registered", "share-count flat file", "(nothing computed, lockbox NOT read)")
            with patched(THIS, FILE_SHA={**FILE_SHA, "facts_add": "f" * 64}):
                refused(lambda: load_facts(S.LB0), "is not the registered", "reviewed share-count additions")
            with patched(THIS, FILES={**FILES, "facts": p("absent.csv")}):
                refused(lambda: load_facts(S.LB0), "is not on file")
            sh = write_facts(files["facts"], base_f, header=[c for c in FACT_HDR if c != "concept"])
            with patched(THIS, FILE_SHA={**FILE_SHA, "facts": sh}):
                refused(lambda: load_facts(S.LB0), "lacks the column", "concept")
        with pin(af=[]):
            d, fi = load_facts(S.LB0)
            assert len(d) == 4 and fi["files"]["facts_add"] == 0, "an empty additions file is fine"
        with pin():                                                                           # a CRLF copy is another file (the pin is of the bytes); the loader reads either
            sh = write_facts(files["facts"], base_f, crlf=True)
            assert sh != FILE_SHA["facts"]
            with patched(THIS, FILE_SHA={**FILE_SHA, "facts": sh}):
                assert len(load_facts(S.LB0)[0]) == 6
        # the real files' registered shas are the constants the prereg prints; check_pinned returns the sha of the bytes it checked
        with pin():
            assert check_pinned("map") == FILE_SHA["map"] == M17.sha_raw(files["map"])
    finally:
        shutil.rmtree(root, ignore_errors=True)
    # the audit's file (f): read and checked (a mistyped row refuses, it never silently does nothing), a data_event removes that name-month from the pool - so from both cells and the nulls
    root = tempfile.mkdtemp(prefix="netiss_selftest_")
    try:
        with spec(n_side=3, min_scored=8, min_side=2, dec_min=7), D15.spec(univ=14):
            tt = toy_ready()
            W = tt.W
            ap = os.path.join(root, "netiss_audit.csv")
            assert read_audit(ap) is None
            open(ap, "w").write(f"symbol,date,cell,verdict,note\nN08,{W.days[270]:%Y-%m-%d},N12,data_event,split\nN01,{W.days[280]:%Y-%m-%d},n24,KEEP,fine\nN09,{W.days[300]:%Y-%m-%d},N24,data_event,bad filing\n")
            au = read_audit(ap)
            assert au["verdict"].tolist() == ["data_event", "keep", "data_event"] and au["cell"].tolist() == ["N12", "N24", "N24"]
            cnt = apply_audit(W, au)
            assert cnt == {"rows": 3, "keep": 1, "data_event": 2, "group_name_months": 0} and W.aud1[270, 8] and W.aud1[300, 9] and W.aud1.sum() == 2, "mid-month sessions are no rebalance's fill: no group, only the rows' own name-months"
            assert apply_audit(W, None)["rows"] == 0 and not W.aud1.any()
            for bad in (f"N08,{W.days[270]:%Y-%m-%d},N12,maybe,x\n", "N08,not-a-date,N12,keep,x\n", f"N08,{W.days[270]:%Y-%m-%d},RES,keep,x\n", f",{W.days[270]:%Y-%m-%d},N12,keep,x\n"):
                open(ap, "w").write("symbol,date,cell,verdict,note\n" + bad)
                refused(lambda: read_audit(ap), "line(s) [2]")
            open(ap, "w").write("symbol,date\nN08,2024-01-01\n")
            refused(lambda: read_audit(ap), "lacks the column")
            for sym, d_ in (("ZZZ", W.days[270]), ("N08", pd.Timestamp("2025-01-04"))):
                open(ap, "w").write(f"symbol,date,cell,verdict,note\n{sym},{d_:%Y-%m-%d},N12,data_event,x\n")
                refused(lambda: apply_audit(W, read_audit(ap)), "match no session or no name")
            # a data_event removes the name-month from BOTH cells and from the nulls' pools
            L0 = ni_build(W, W.days[0], W.days[-1])
            rec = next(r_ for r_ in L0.recs if W.days[r_.r] == TS("2025-11-28"))
            j = int(rec.pool[rec.cell["N12"].idx[rec.cell["N12"].long[0]]])
            W.aud1[rec.f, j] = True
            L1 = ni_build(W, W.days[0], W.days[-1])
            r1 = next(r_ for r_ in L1.recs if r_.r == rec.r)
            assert j in rec.pool.tolist() and j not in r1.pool.tolist() and all(j not in r1.pool[r1.cell[c].idx].tolist() for c in CELLS) and L1.cnt[2025]["audit"] >= 1, "the name-month is out of the pool: of both cells' scored names"
            acc = ni_null(W, L1, 12, 0)
            assert all(a.shape == (12, W.T) for a in acc.values())
            W.aud1[:] = False
            W.aud_hit.clear()
            ap2 = os.path.join(root, "a2.csv")
            d0 = f"{W.days[rec.f]:%Y-%m-%d}"
            open(ap2, "w").write(f"symbol,date,cell,verdict,note\nN08,{d0},N12,data_event,x\nN05,{d0},N12,data_event,x\n")
            au2 = read_audit(ap2)
            apply_audit(W, au2)
            assert unused_audit_rows(W, au2) == [f"N08 {d0} N12", f"N05 {d0} N12"]
            W.aud_hit.add((AUD, rec.f, 8))
            assert unused_audit_rows(W, au2) == [f"N05 {d0} N12"]
            cands = {"N12": [{"symbol": "N08", "date": d0}], "N24": [{"symbol": "N08", "date": d0}, {"symbol": "N05", "date": "2024-01-01"}]}
            a10 = [{"cell": "N12", "symbol": "N08", "date": d0, "picked": "N12/long"}, {"cell": "N12", "symbol": "N03", "date": d0, "picked": "N12/short"}, {"cell": "N12", "symbol": "N09", "date": d0, "picked": ""},
                   {"cell": "N24", "symbol": "N05", "date": d0, "picked": "N24/long"}, {"cell": "N24", "symbol": "N05", "date": d0, "picked": "N24/long"}]       # rows without a group key: each picked (symbol, date) is its own group
            st = audit_status(W, cands, a10, au2)
            assert st["N12"] == {"listed": 1, "audited": 1, "audit_complete": True, "groups": 0, "a10_flagged": 3, "a10_picked": 2, "a10_listed": 2, "a10_audited": 1, "a10_complete": False}, st["N12"]
            assert st["N24"] == {"listed": 2, "audited": 1, "audit_complete": False, "groups": 0, "a10_flagged": 2, "a10_picked": 2, "a10_listed": 1, "a10_audited": 1, "a10_complete": True}, st["N24"]
            assert audit_status(W, {"N12": [], "N24": []}, [], None)["N12"] == {"listed": 0, "audited": 0, "audit_complete": False, "groups": 0, "a10_flagged": 0, "a10_picked": 0, "a10_listed": 0, "a10_audited": 0, "a10_complete": True}
    finally:
        shutil.rmtree(root, ignore_errors=True)


def brute_facts(W, frame, cik, r, k, use):
    """plain python: the two facts behind a scored name's ISS at rank row r: for the concept used, S = the usable value with the latest as-of date and S' the one closest to a - k years (brute_pair), each with its as-of date, FIRST filed date and the accession and form of its first-filed row
    (the smallest accession on that day) -> {now: (value, as-of, first filed, accn, form), prior: ...}"""
    con = (DEI, GAAP)[use - 1]
    ent = brute_entries(frame, cik, con)
    (a, sv), (ap, pv) = brute_pair(ent, W, r, k)
    out = {}
    for tag, end, v in (("now", a, sv), ("prior", ap, pv)):
        f1 = ent[end][0]
        rs = frame[(frame["cik"] == cik) & (frame["concept"] == con) & (frame["end"] == end) & (frame["filed"] == f1)].sort_values("accn")
        out[tag] = (v, end, f1, rs["accn"].iloc[0], rs["form"].iloc[0])
    return out


def t_rows():
    """the hand audit's rows and the reports' counts on the toy leg against plain-python recounts: the 50 largest gains with each one's two share facts (value, as-of date, FIRST filed date, accession, form) and the split factor on each as-of date, every [A10] flagged name-rank, the turnover and the
    score's persistence, the dividend flows and the [D2] counts of the picks"""
    with spec(n_side=3, min_scored=8, min_side=2, dec_min=7), D15.spec(univ=14):
        tt = toy_ready()
        W, frame = tt.W, tt.frame
        lo, hi = W.days[0], W.days[-1]
        L = ni_build(W, lo, hi)
        Bz = brute_ni(W, frame, tt.cal, tt.cik_of, lo, hi, "remove")
        by_r = {b["r"]: b for b in Bz}
        cache = {}
        for cell in CELLS:
            run = M17.run_cell(W, cell_leg(L, cell), D15.l1_cfg(), pos=True)
            cd = ni_candidate_rows(W, L, cell, run, None, {})
            pnl = [x["pnl"] for x in cd]
            n_pos = sum(2 * r_.cell[cell].k for r_ in L.recs if r_.cell[cell].traded)
            assert len(cd) == min(AUDIT_N, n_pos) and pnl == sorted(pnl, reverse=True) and abs(pnl[0] - float(run.pos.pnl.max())) < 1e-9, "the largest gains first"
            need = {"symbol", "date", "exit", "side", "pnl", "score", "rank_date", "cik", "concept", "iss", "iota", "shares_now", "asof_now", "first_filed_now", "accn_now", "form_now", "shares_prior", "asof_prior", "first_filed_prior", "accn_prior", "form_prior",
                    "F_now", "F_prior", "flag_over_ln1.5", "straddles_a_split", "window_rests_on_F_alone", "factor_ratio_window_to_exit", "tbis_price_ratio", "asset_status", "flags_in_window", "dividend_pnl_in_hold"}
            assert need <= set(cd[0]) and "raw_move_formation" not in cd[0] and "adj_move_formation" not in cd[0], "RESMOM's formation-window moves are left out"
            for x_ in cd:
                j = list(W.syms).index(x_["symbol"])
                rr = next(r_ for r_ in L.recs if f"{W.days[r_.f]:%Y-%m-%d}" == x_["date"])
                b = by_r[rr.r]["cell"][cell]["scored"][j]
                assert x_["rank_date"] == f"{W.days[rr.r]:%Y-%m-%d}" and abs(x_["iss"] - b.iss) < 1e-12 and abs(x_["score"] - b.iss) < 1e-12 and abs(x_["iota"] - brute_iota(W, j, b)) < 1e-12, (cell, x_["symbol"], x_["date"])
                bf = brute_facts(W, frame, tt.cik_of[x_["symbol"]], rr.r, KS[cell], b.use)
                assert x_["cik"] == tt.cik_of[x_["symbol"]] and x_["concept"] == (DEI, GAAP)[b.use - 1]
                for tag in ("now", "prior"):
                    v, end, f1, accn, form = bf[tag]
                    assert x_[f"shares_{tag}"] == v and x_[f"asof_{tag}"] == f"{end:%Y-%m-%d}" and x_[f"first_filed_{tag}"] == f"{f1:%Y-%m-%d}" and x_[f"accn_{tag}"] == accn and x_[f"form_{tag}"] == form, (cell, x_["symbol"], tag)
                ia, iap = b.ia, b.iap
                assert x_["F_now"] == W.F[ia, j] and x_["F_prior"] == W.F[iap, j] and x_["flag_over_ln1.5"] is bool(b.flag10) and x_["straddles_a_split"] is bool(b.straddle) and x_["window_rests_on_F_alone"] is bool(b.f_alone)
                assert abs(math.log(x_["shares_now"] * x_["F_now"] / (x_["shares_prior"] * x_["F_prior"])) - x_["iss"]) < 1e-12, "the score IS the ratio of the two facts through F"
                assert x_["side"] in ("long", "short") and x_["date"] < x_["exit"]
            # turnover and persistence: the share of each side's names not on the same side at the previous traded rebalance, the share of the previous side still there
            tn = ni_turnover(L, cell)
            sets = [(set(rec.pool[rec.cell[cell].idx[rec.cell[cell].long]].tolist()), set(rec.pool[rec.cell[cell].idx[rec.cell[cell].short]].tolist()), rec.cell[cell].k) for rec in L.recs if rec.cell[cell].traded]
            rows = [(1.0 - len(b_[0] & a_[0]) / b_[2], 1.0 - len(b_[1] & a_[1]) / b_[2], len(b_[0] & a_[0]) + len(b_[1] & a_[1]), len(b_[0] & a_[0]) / a_[2], len(b_[1] & a_[1]) / a_[2]) for a_, b_ in zip(sets[:-1], sets[1:])]
            assert tn["traded_rebalances"] == len(sets) and tn["transitions"] == len(rows)
            if rows:
                assert abs(tn["long_replaced_mean"] - np.mean([r_[0] for r_ in rows])) < 1e-12 and abs(tn["short_replaced_mean"] - np.mean([r_[1] for r_ in rows])) < 1e-12 and abs(tn["persistence_long_mean"] - np.mean([r_[3] for r_ in rows])) < 1e-12
                assert abs(tn["persistence_short_mean"] - np.mean([r_[4] for r_ in rows])) < 1e-12 and abs(tn["persistence_mean"] - np.mean([[r_[3], r_[4]] for r_ in rows])) < 1e-12 and abs(tn["cost_saved_if_only_changes_traded_usd_estimate"] - sum(r_[2] for r_ in rows) * 4000 * 2 * 5e-4) < 1e-9
                assert tn["replaced_min"] <= tn["replaced_mean"] <= tn["replaced_max"]
                if len({r_.cell[cell].k for r_ in L.recs if r_.cell[cell].traded}) == 1:
                    assert abs(tn["persistence_mean"] - (1.0 - tn["replaced_mean"])) < 1e-12, "with a constant side size persistence = 1 - turnover"
            # [R1] the dividend flows inside the picks, recounted by plain python
            fl = ni_div_flows(L, cell)
            wl = ws = 0.0
            nl = ns = 0
            for b in Bz:
                bc = b["cell"][cell]
                for sd, js in ((1, bc["long"]), (-1, bc["short"])):
                    for j in js:
                        d_ = sum(M17.brute_div(W, b["f"], b["x"], j, b["pool"][j][0]))
                        if sd > 0:
                            wl, nl = wl + 4000.0 * d_, nl + (d_ > 0)
                        else:
                            ws, ns = ws + 4000.0 * d_, ns + (d_ > 0)
            assert abs(fl["long_received"] - wl) < 1e-9 and abs(fl["short_paid"] - ws) < 1e-9 and fl["long_positions_with_a_dividend"] == nl and fl["short_positions_with_a_dividend"] == ns, (cell, fl, wl, ws)
        sp = {c: ni_spin_counts(L, c) for c in CELLS}
        for c in CELLS:
            tot = sum(len(rec.cell[c].long) + len(rec.cell[c].short) for rec in L.recs if rec.cell[c].traded)
            assert sp[c]["long"]["positions"] + sp[c]["short"]["positions"] == tot and sp[c]["long"]["hold_positions"] == sp[c]["short"]["hold_positions"] == 0, "the registered reading removed every name with an ex-date inside the hold"
            bw = sum(1 for b in Bz for j in b["cell"][c]["long"] + b["cell"][c]["short"] if b["pool"][j][1] > 0)
            assert sp[c]["long"]["window_positions"] + sp[c]["short"]["window_positions"] == bw
        with quiet():
            print_spin_picks({"registered reading": sp})
        # [A10]: every scored name-rank above ln(1.5) among the universe names, with the audit key (symbol + FILL date)
        ranks = built_ranks(W, lo, hi)
        a10 = a10_rows(W, ranks, L)
        want = set()
        for r, f, x in ranks:
            for c, kk in KS.items():
                for j in np.flatnonzero(W.U[f]):
                    b = brute_score(W, frame, tt.cal, int(j), tt.cik_of.get(str(W.syms[j]), ""), int(W.ni.static[j]), r, kk, cache)
                    if b.flag10:
                        want.add((c, str(W.syms[j]), f"{W.days[f]:%Y-%m-%d}", f"{W.days[r]:%Y-%m-%d}"))
        got = {(x_["cell"], x_["symbol"], x_["date"], x_["rank_date"]) for x_ in a10}
        assert got == want and len(a10) == len(want) > 0, (sorted(got ^ want)[:5], len(a10))
        assert all(x_["flag_over_ln1.5"] and abs(x_["iss"]) > LN15 and abs(x_["iss"]) <= LN10 and x_["date"] > x_["rank_date"] for x_ in a10)
        # [A4] the names with no score whatever the horizon, counted by NAME, against the recount from the plain-python codes
        static_codes = {R_NOT_IN_MAP, R_MAP_MISMATCH, R_MAP_AMBIGUOUS, R_MAP_UNMAPPED, R_MAP_NONCOMMON, R_MAP_OTHER, R_NO_FACTS, R_FOREIGN, R_NO_FACT}
        want_u = defaultdict(Counter)
        for r, f, x in ranks:
            for j in np.flatnonzero(W.U[f]):
                b = brute_score(W, frame, tt.cal, int(j), tt.cik_of.get(str(W.syms[j]), ""), int(W.ni.static[j]), r, 1, cache)
                if b.code in static_codes:
                    want_u[REASONS[b.code]][str(W.syms[j])] += 1
        got_u = unscored_by_name(W, ranks)
        assert got_u == {k_: dict(v_) for k_, v_ in want_u.items()} and got_u and all(isinstance(n_, int) and n_ > 0 for d_ in got_u.values() for n_ in d_.values()), (got_u, dict(want_u))
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            print_unscored_by_name(got_u)
        for reason, d_ in got_u.items():
            assert f"{REASON_TEXT[reason]} - {len(d_)} names: " in buf.getvalue() and all(f"{s_} x{n_}" in buf.getvalue() for s_, n_ in d_.items()), reason
        # a name with no pair at the rank: blank facts, never an exception
        ff = fact_fields(W, ranks[0][0], "N12", list(W.syms).index("N03"))
        assert ff["cik"] == "" and ff["concept"] == "" and not math.isfinite(ff["shares_now"]) and ff["asof_prior"] == "" and ff["rank_date"] == f"{W.days[ranks[0][0]]:%Y-%m-%d}"
        # the score report's counts (BEFORE ANY P&L) recounted from the codes
        sr = score_report(W, ranks, values=False)
        for rec, (r, f, x) in zip(sr, ranks):
            uni = np.flatnonzero(W.U[f])
            for c in CELLS:
                s_ = score_rank(W, r)[c]
                cn = rec["cells"][c]
                assert cn["scored"] == int(s_.scored[uni].sum()) and cn["dei"] == int((s_.use[uni] == 1).sum()) and cn["gaap"] == int((s_.use[uni] == 2).sum()) and cn["fallback_to_gaap"] == int(s_.fallback[uni].sum())
                assert cn["a10_flags"] == int(s_.flag10[uni].sum()) and cn["straddle"] == int(s_.straddle[uni].sum()) and cn["stale"] == int(s_.stale[uni].sum()) and cn["f_alone"] == int(s_.f_alone[uni].sum())
                assert sum(cn["reasons"].values()) + cn["scored"] == len(uni) and cn["reasons"]["foreign_filer"] == int((s_.code[uni] == R_FOREIGN).sum()) and "iss" not in cn
                assert cn["ln10_names"] == [str(q) for q in W.syms[uni][s_.ln10[uni]]]
        srv = score_report(W, ranks, values=True)
        assert all(np.array_equal(a["cells"][c]["iss"], score_rank(W, r)[c].iss[np.flatnonzero(W.U[f])][score_rank(W, r)[c].scored[np.flatnonzero(W.U[f])]]) for a, (r, f, x) in zip(srv, ranks) for c in CELLS)
        fr0 = coverage_firsts(srv, W.ni.cal_start)
        assert fr0["N12"]["first_rank_with_a_score"] == min(rec["rank"] for rec in srv if rec["cells"]["N12"]["scored"] > 0) and fr0["N24"]["first_rank_with_a_score"] == min(rec["rank"] for rec in srv if rec["cells"]["N24"]["scored"] > 0)
        assert fr0["N12"]["first_rank_k_years_after_the_cache_start"] == srv[0]["rank"] == fr0["N24"]["first_rank_k_years_after_the_cache_start"], "the toy's ranks all lie years after the REGISTERED cache start (2016-01-04)"
        assert fr0["N12"]["first_rank_k_years_after_the_calendar_start"] == "2025-01-31" and fr0["N24"]["first_rank_k_years_after_the_calendar_start"] == "2026-01-30" and coverage_firsts(srv, None)["N12"]["first_rank_k_years_after_the_calendar_start"] is None
        mk = lambda d, n12, n24: {"rank": d, "cells": {"N12": {"scored": n12}, "N24": {"scored": n24}}}
        hand = [mk("2016-12-30", 3, 0), mk("2017-01-31", 200, 0), mk("2017-02-28", 300, 0), mk("2018-01-31", 400, 5), mk("2018-02-28", 400, 300)]
        f_ = coverage_firsts(hand, "2016-06-01")
        assert f_["N12"] == {"first_rank_with_a_score": "2016-12-30", "first_rank_k_years_after_the_cache_start": "2017-01-31", "first_rank_k_years_after_the_calendar_start": "2018-01-31"}, f_
        assert f_["N24"] == {"first_rank_with_a_score": "2018-01-31", "first_rank_k_years_after_the_cache_start": "2018-01-31", "first_rank_k_years_after_the_calendar_start": None}, f_
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            print_score_report(srv, W.ni.cal_start, names=True)
        txt = buf.getvalue()
        i0 = [txt.index(s_) for s_ in ("BEFORE ANY P&L", "names lost to each rule", "excluded at |ISS| > ln(10) and LISTED", "ISS per fill year", "have a window that straddles a split", "[A3] a calendar split", "[A11] unscored ADRs", "[A11] N12: CIKs whose first share fact")]
        assert i0 == sorted(i0), "the prints come in the prereg's order"
        for c in CELLS:                                                                    # every name excluded at |ISS| > ln(10) / by [A3] is LISTED, with its ranks - none cut off
            for lab, key in (("excluded at |ISS| > ln(10) and LISTED", "ln10_names"), ("a calendar split the cache's factor F does not show", "split_calendar_not_in_F_names"), ("an F change the calendar does not show", "split_F_not_in_calendar_names")):
                want = defaultdict(list)
                for rec in srv:
                    for q in rec["cells"][c][key]:
                        want[q].append(rec["rank"])
                line = [l_ for l_ in txt.splitlines() if f"  {c} " in l_[:6] and lab in l_][0]
                seg = line.split(lab)[1] if key == "ln10_names" else (line.split(lab)[1].split("; an F change")[0] if key == "split_calendar_not_in_F_names" else line.split(lab)[-1])
                assert f"{sum(len(v) for v in want.values())} name-ranks on {len(want)} names" in seg and all(f"{q} x{len(ds)} ({ds[0]}" in seg for q, ds in want.items()), (c, key, dict(want), seg)
        assert sum(len(rec["cells"][c]["ln10_names"]) for rec in srv for c in CELLS) > 0, "the toy world has a name excluded at |ISS| > ln(10)"
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            print_score_report(sr, W.ni.cal_start, names=False)
        assert "counted" in buf.getvalue() and "ISS per fill year" not in buf.getvalue() and "excluded at |ISS| > ln(10) and counted" in buf.getvalue()


def t_integration():
    """evaluate / reports / candidate rows on the toy world, a synthetic #463 and a synthetic reference (no files), the stretch moved onto the toy's own days (2024-01-02 .. 2026-06-30) so both cells trade inside it: every statistic is the independent sum, the cost curve and the sides add up, the null runs,
    A2 is incremental over the reference with the cell's own window, the deciles / the composite twin / the hedged twin / the beta rule are on the cell, MANAGER #70's gate basis and the diagnostics carry every row of the prereg's DIAGNOSTICS paragraph and the addenda, everything is JSON-serialisable"""
    wf = (TS("2024-01-02"), TS("2026-06-30"))
    wins = {"N12": (TS("2025-06-02"), TS("2026-03-31")), "N24": (TS("2026-03-02"), TS("2026-04-30"))}
    B, _s = M17.synth_book(seed=15, lo="2024-01-01", hi="2026-06-30", deep=False)
    ref_at0 = DV.ref_at
    ref_at_toy = lambda B_, ref_, xB_, c_, lo=wf[0], hi=wf[1]: ref_at0(B_, ref_, xB_, c_, lo, hi)               # (ref_at's default window was bound when r18_divrun was imported: the real WF)
    with spec(n_side=3, min_scored=8, min_side=2, dec_min=7), D15.spec(univ=14), patched(THIS, WF0=wf[0], PRE_END=wf[1], A2_WINS=wins), patched(D15, WF0=wf[0], PRE_END=wf[1]), patched(DV, WF0=wf[0], PRE_END=wf[1], ref_at=ref_at_toy):
        S12 = M12.Stretch(B.raw, B.index, None, wf[0], wf[1])
        ref = DV.mk_ref(B)
        tt = toy_ready()
        W = tt.W
        rows = A13.book_rows(B, W)
        spy, real_judge = [], judge_cell

        def judge_spy(st, net10, nul, cell, n_years):
            spy.append((st, net10, nul, cell, n_years))
            return real_judge(st, net10, nul, cell, n_years)
        with patched(THIS, judge_cell=judge_spy):
            res, obj = evaluate(W, B, S12, ref, rows, JUDGED, 40, 0, full=True)
        assert [(a_[0], a_[1], a_[3]) for a_ in spy] == [(res["cells"][c]["base"], res["cells"][c]["stress"]["10 bps"]["net"], c) for c in CELLS] and all(a_[2] is res["null"] for a_ in spy), "judge_cell reads each cell's own base stats, its 10 bps net, the registered null and its own years"
        assert [a_[4] for a_ in spy] == [len(res["cells"][c]["years_held"]) for c in CELLS] and res["cells"]["N12"]["years_held"] == [2024, 2025] and res["cells"]["N24"]["years_held"] == [2025], "the toy cells hold positions in the July-June years 2024-25 / 2025-26 (N24 only in the second)"
        resK, objK = evaluate(W, B, S12, ref, rows, "remove", 0, 1, full=False)
        with div_mode(W, False):
            resD = evaluate(W, B, S12, ref, rows, JUDGED, 40, 2, full=False)[0]
        Bz = brute_ni(W, tt.frame, tt.cal, tt.cik_of, wf[0], wf[1], JUDGED)
        slot = M17.SPEC["slot"]
        for cell in CELLS:
            c = res["cells"][cell]
            x0 = np.zeros(W.T)
            n_pos = 0
            for b in Bz:
                bc = b["cell"][cell]
                for sd, js in ((1, bc["long"]), (-1, bc["short"])):
                    for j in js:
                        x0[b["f"]:b["x"] + 1] += slot * np.array(M17.brute_path(W, b["f"], b["x"], j, sd, b["pool"][j][0])[0])
                        n_pos += 1
            traded = [b for b in Bz if b["cell"][cell]["k"] > 0]
            assert abs(c["base"]["net"] - x0.sum()) < 1e-6 and c["base"]["n_units"] == len(traded) > 0 and c["base"]["n_pos"] == n_pos and abs(c["base"]["net_pos"] - x0.sum()) < 1e-6 and abs(c["usd_year"] - c["base"]["net"] / c["base"]["years"]) < 1e-9, (cell, c["base"]["net"], x0.sum())
            assert set(c["stress"]) == {"10 bps", "20 bps"} and c["cost0"]["net"] > c["base"]["net"] > c["stress"]["10 bps"]["net"] > c["stress"]["20 bps"]["net"], "the cost curve: more cost, less P&L (every position pays at both ends)"
            assert abs((c["sides"]["long side only"]["net"] + c["sides"]["short side only"]["net"]) - c["base"]["net"]) < 1e-6
            assert set(c["extra"]) == {"borrow 1% on k>1.5 sessions", "borrow 3% on k>1.5 sessions", "longs that stop printing valued at -100%", M17.R2_CELL} and c["extra"]["borrow 3% on k>1.5 sessions"]["net"] <= c["extra"]["borrow 1% on k>1.5 sessions"]["net"] + 1e-9 <= c["base"]["net"] + 1e-9
            assert set(c["sub"]) == {s_[0] for s_ in SUBPERIODS} and sum(v["n_pos"] for v in c["sub"].values()) <= c["base"]["n_pos"]
            assert set(c["checks"]) == set(real_judge(c["base"], 1.0, res["null"], cell, len(c["years_held"]))) and c["PASS"] is False, "the toy world cannot clear the bars (a handful of rebalances)"
            a2 = c["A2"]
            assert a2["window"] == [f"{wins[cell][0]:%Y-%m-%d}", f"{wins[cell][1]:%Y-%m-%d}"] and math.isfinite(a2["c"]) and abs(a2["c"] * a2["std_cell"] - 0.25 * a2["std_book"]) <= 1e-9 * a2["std_book"] and "reference" in a2 and "plain_463" in a2 and "usd_year" in a2["reference"] and "pass" not in a2
            assert a2["credited"] is c["beta"]["within_cap"] and a2["incremental_credit"] is bool(a2["incremental_pass"] and c["beta"]["within_cap"])
            assert c["seat_ref"]["dd_days"] == ref.structure["days"] and len(c["episode_pnl"]) == len(ref.S.qual) and c["gate70"]["DO"] == c["seat_ref"]["DO"] and c["gate70"]["episodes"] == ref.structure["episodes"] and c["gate70"]["credited"] is c["beta"]["within_cap"]
            assert c["gate70"]["null_do_p95"] == res["null"]["do_ref_max"]["p95"] and c["gate70"]["DO_above_null_p95"] is bool(c["seat_ref"]["DO"] > res["null"]["do_ref_max"]["p95"]) and "positive_without_best_episode" in c["gate70"] and "episodes_helped" in c["gate70"]
            assert c["short_stopped"]["short_positions"] == sum(r.cell[cell].k for r in obj.legs.recs if r.cell[cell].traded)
            assert set(c["beta"]) == {"side_notional", "beta_dd_days", "beta_all_days", "cap", "within_cap", "es_beta"} and c["beta"]["side_notional"] == 3 * 4000.0 and isinstance(c["beta"]["within_cap"], bool)
            d = c["deciles"]
            assert [q["decile"] for q in d["deciles"]] == list(range(1, 11)) and d["ranks_cut"] == sum(1 for r in obj.legs.recs if r.cell[cell].dec is not None) and all(k_ in d["deciles"][0] for k_ in ("net", "roc", "usd_year", "spread_net", "spread_roc", "spread_usd_year", "name_months"))
            tw = c["composite"]
            assert set(tw) >= {"base", "usd_year", "pick_overlap_with_iss_picks", "scores_with_window_before_the_calendar"} and 0.0 <= tw["pick_overlap_with_iss_picks"]["long"] <= 1.0 and tw["base"]["n_units"] == c["base"]["n_units"]
            hd = c["hedged"]
            assert hd["ratios"] == c["base"]["n_units"] and hd["ratios_nonzero"] == 0 and abs(hd["base"]["net"] - c["base"]["net"]) < 1e-6 * max(1.0, abs(c["base"]["net"])) + 1.0, "under 252 sessions of the cell's own P&L the hedge is zero: the twin IS the cell (the toy has 12 months)"
        assert res["null"]["draws"] == 40 and resK["null"] is None and res["null"]["seed"] == SEED and set(res["null"]["by_cell"]) == set(CELLS) and res["null"]["do_ref_max"]["finite"] == 40 and resD["null"]["draws"] == 40
        assert any(abs(res["cells"][c]["base"]["net"] - resD["cells"][c]["base"]["net"]) > 1e-6 for c in CELLS), "the dividends move the P&L in the toy world"
        srows = score_report(W, built_ranks(W, wf[0], wf[1]), values=True)
        rep, cands = reports(W, B, S12, ref, rows, obj, res["cells"], None, {}, [], srows, post_mode=JUDGED)
        for key in ("beta_to_es", "episodes", "ref_episodes", "map_point", "corr_with_legs", "corr_with_res", "pick_overlap_with_res", "top20_gains", "months", "turnover", "survivorship", "dividend_flows", "concept_by_rank", "manifest_sha256"):
            assert key in rep, key
        assert list(rep["beta_to_es"]["N12"]) == ["DD days", "DD weeks (every day of them)", "all WF days"] and rep["map_point"]["N24"]["standalone_roc_30k"] == res["cells"]["N24"]["base"]["roc"]
        for cell in CELLS:
            xs = obj.series[cell][0]
            kw = np.flatnonzero(B.mask(wf[0], wf[1]))
            assert abs(rep["corr_with_res"][cell] - float(np.corrcoef(xs[kw], ref.res[kw])[0, 1])) < 1e-12 and len(rep["ref_episodes"][cell]) == len(ref.S.qual)
            ov = rep["pick_overlap_with_res"][cell]
            assert 0.0 <= ov["long_in_res_long"] <= 1.0 and 0.0 <= ov["short_in_res_short"] <= 1.0 and ov["rebalances"] >= 1
            assert abs(sum(rep["months"][cell].values()) - res["cells"][cell]["base"]["net"]) < 1e-6 and len(rep["concept_by_rank"][cell]) == len(srows) and rep["turnover"][cell]["traded_rebalances"] == res["cells"][cell]["base"]["n_units"]
        assert json.loads(json.dumps({"res": res, "rep": rep, "srows": [{k: v for k, v in r_.items() if k != "cells"} for r_ in srows]}, default=R11.js)) is not None
        ast = {c: {"listed": 5, "audited": 0, "audit_complete": False, "groups": 4, "a10_flagged": 9, "a10_picked": 6, "a10_listed": 3, "a10_audited": 1, "a10_complete": False} for c in CELLS}
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            print_score_report(srows, W.ni.cal_start, names=True)
            print_cells(res, ast)
            print_deciles(res)
            print_twins(res)
            print_reports(rep, res["cells"])
            print_diagnostics(res, rep, ref)
            print_counts("registered", obj.legs.cnt)
            print_scored("registered", obj.legs.cnt)
        txt = buf.getvalue()
        for frag in ("BEFORE ANY P&L", "null: RANDOM NAMES from each rebalance's eligible SCORED pool, registered (40 draws, seed 20261008", "#70 gate basis [X1]", "DIAGNOSTICS [X2]", "COST CURVE", "BY JULY-JUNE YEAR", "THE TWO REGIME HALVES", "THE LONG AND SHORT SIDES APART", "A2 (a report) [X1]",
                     "realised beta to ES [A6]", "ISS DECILES [A5]", "TWINS - REPORTED", "composite-issuance twin", "ES-hedged twin", "persistence", "against RES: daily P&L correlation", "concept used", "dividends [R1]", "short leg [R2]", "survivorship", "a year)", "THE REFERENCE BOOK'S DRAWDOWN EPISODES [A12]",
                     "the episodes the cell helps", "credited by the beta rule [A6]", "audit [A14] 0/5 of the top-50 listed (4 groups), 1/3 of the picked [A10] groups (6 picked of 9 flagged name-ranks) -> top-50 incomplete, picked groups incomplete"):
            assert frag in txt, frag


def t_stage_b_refusals():
    """every Stage B refusal that needs no data, none of which may write the read flag: the lead's go-flag FIRST (nothing computed), then no Stage A candidate (each broken piece), the flag already there, a changed spec / harness / audit, a broken frozen size, and the lockbox year's share
    facts not pinned (LB_FACTS is None: the pinned extract stops at filed 2025-06-27, so Stage B cannot read one fact of the sealed year until a dated addendum pins a second extract)"""
    root = tempfile.mkdtemp(prefix="netiss_selftest_")
    try:
        out = os.path.join(root, "out")
        os.makedirs(out)
        go, flag, sap, aud = os.path.join(out, GO_FLAG), os.path.join(out, READ_FLAG), os.path.join(out, "netiss_stageA.json"), os.path.join(out, "netiss_audit.csv")
        good = {"judged": True, "prereg_sha256_lf": PREREG_SHA, **stamp(), "audit_sha256": None, "candidate": {"cell": "N24", "c": 0.8317}, "stageA": {"cells": {"N24": {"PASS": True}}, "pass_cells": ["N24"]}, "parity": {}}

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
                       ("cell not a pass cell", mut(lambda d: d["stageA"].update(pass_cells=["N12"]))), ("no pass cells", mut(lambda d: d["stageA"].update(pass_cells=[]))), ("no stageA", mut(lambda d: d.update(stageA=None)))):
            must("no Stage A candidate", sa)
        open(flag, "w").write("x")
        must("already read", good)
        os.remove(flag)
        must("DIFFERS", good, PREREG_SHA="0" * 64)
        must("another pre-registration", mut(lambda d: d.update(prereg_sha256_lf="0" * 64)))
        for nm, edit in (("harness", lambda d: d.update(harness_sha256="0" * 64)), ("r17", lambda d: d.update(r17_sha256="0" * 64)), ("r18", lambda d: d.update(r18_sha256="0" * 64)), ("early close", lambda d: d.update(early_close=d["early_close"][1:])),
                         ("r15", lambda d: d.update(r15_sha256="0" * 64)), ("r13", lambda d: d.pop("r13_sha256")), ("the facts file", lambda d: d.update(facts_sha256="0" * 64)), ("the facts additions", lambda d: d.update(facts_add_sha256="0" * 64)),
                         ("the map", lambda d: d.update(map_sha256="0" * 64)), ("the map additions", lambda d: d.update(map_add_sha256="0" * 64)), ("the wide calendar", lambda d: d.update(wide_ca_sha256="0" * 64)),
                         ("no stamp", lambda d: [d.pop(k) for k in stamp()])):
            must("different harness version", mut(edit))
        must("not the file Stage A ran with", mut(lambda d: d.update(audit_sha256="0" * 64)))
        with open(aud, "w") as f:
            f.write("symbol,date,cell,verdict,note\n")
        sha = file_sha(aud)
        for badc in (0.0, -1.0, None, "abc", float("nan"), float("inf")):                      # c is a volatility ratio: any positive number is a frozen size; NaN / 0 / negative / missing / text is a broken file
            must("positive number", mut(lambda d, b=badc: d.update(audit_sha256=sha, candidate={"cell": "N24", "c": b})))
        must("not one of", mut(lambda d: d.update(audit_sha256=sha, candidate={"cell": "N99", "c": 0.8317}, stageA={"cells": {"N99": {"PASS": True}}, "pass_cells": ["N99"]})))
        ok = mut(lambda d: d.update(audit_sha256=sha))
        must("the lockbox year's share facts are not pinned", ok)                               # everything else is in order: the sealed year's facts are the one thing missing
        must("the lockbox year's share facts are not pinned", ok, LB_FACTS={"facts": ("a", "b")})
        assert LB_FACTS is None and not os.path.exists(flag), "no refusal wrote the flag"
    finally:
        shutil.rmtree(root, ignore_errors=True)


def t_cut():
    """Stage A asks for data cut at 2025-06-30 and refuses a session on / after it (the loaders and the book are stubbed; nothing real is read); a changed pre-registration, an unreadable map / facts file, the manifest, the book and the reference gates all refuse before any data is asked for;
    the World's cut; every table the score reads - the flat file's rows and as-of dates, the entries, the World's arrays - holds nothing on / after the cut; Stage A is frozen once the lockbox was read"""
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
    ok_map = lambda: mp_of([("AAA", "C0", "current_ticker")])
    ok_facts = lambda cut, strict_cut=True: (fr([("C0", DEI, 100, "2018-03-31", "2018-05-02")]), {"sha256": {}, "files": {"facts": 1, "facts_add": 0}, "rows": 1, "rows_read": 1})
    root = tempfile.mkdtemp(prefix="netiss_selftest_")
    out = os.path.join(root, "out")
    os.makedirs(out)

    def bad_ref(B, check_facts=None):
        refuse("refused: the RESMOM line file x is not the registered y (nothing computed, lockbox NOT read)")

    def must(frag, **kw):
        seen.clear()
        with devnull(), patched(THIS, **kw):
            refused(stage_a, frag)
        assert not os.path.exists(os.path.join(out, "netiss_stageA.json")) and not os.path.exists(os.path.join(out, READ_FLAG)), "a refusal writes nothing"
        return dict(seen)
    try:
        with patched(S, Data=stub), patched(A13, load_463=lambda: (Bs, [])), patched(M17, wide_load=no_wide), patched(DV, ref_load=lambda B, check_facts=None: ref0), patched(THIS, book_checks=lambda B: okbk, manifest_sha=lambda: D15.MANIFEST_PREFIX + "0" * 56, OUT=out, load_map=ok_map, load_facts=ok_facts):
            assert "t" not in must("DIFFERS", PREREG_SHA="0" * 64), "a changed pre-registration refuses before any data is asked for"
            assert "t" not in must("symbol -> CIK map", load_map=lambda: refuse("refused: the pinned symbol -> CIK map x is not on file (nothing computed, lockbox NOT read)"))
            assert "t" not in must("share-count flat file", load_facts=lambda cut, strict_cut=True: refuse("refused: x is not the registered share-count flat file (nothing computed, lockbox NOT read)"))
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
    # the sealed year in the flat file: the table the score reads holds nothing filed or as-of on / after the cut, and a filing on the cut's own date is refused
    root = tempfile.mkdtemp(prefix="netiss_selftest_")
    try:
        files = {"facts": os.path.join(root, "f.csv"), "facts_add": os.path.join(root, "fa.csv"), "map": os.path.join(root, "m.csv"), "map_add": os.path.join(root, "ma.csv")}
        rows = [("0000000001", DEI, 100, "2025-03-31", "2025-05-02"), ("0000000001", DEI, 101, "2025-06-27", "2025-06-27"), ("0000000001", DEI, 102, "2025-06-30", "2025-06-27"), ("0000000001", DEI, 103, "2025-06-29", "2025-06-29"),
                ("0000000001", DEI, 104, "2025-09-30", "2025-10-02"), ("0000000001", DEI, 105, "2026-01-31", "2026-02-03")]
        shas = {"facts": write_facts(files["facts"], rows), "facts_add": write_facts(files["facts_add"], []), "map": write_map(files["map"], [("AAA", "0000000001", "current_ticker")]), "map_add": write_map(files["map_add"], [])}
        with patched(THIS, FILES=files, FILE_SHA=shas):
            refused(lambda: load_facts(S.LB0), "filed on / after the cut")
            d, fi = load_facts(S.LB0, strict_cut=False)
            assert fi["rows_filed_on_or_after_the_cut"] == 2 and fi["rows_end_on_or_after_the_cut"] == 1 and len(d) == 3 and d["filed"].max() < S.LB0 and d["end"].max() < S.LB0, fi
            assert sorted(d["filed"].dt.strftime("%Y-%m-%d").tolist()) == ["2025-05-02", "2025-06-27", "2025-06-29"], "filed on 2025-06-29 (the day before the cut) stays; the row with an as-of date on the cut (a typo year) goes; the two filed after it are the sealed year"
        fx = build_facts(d)
        assert fx.dei.f1.max() < int(day_i(S.LB0)) and fx.dei.end.max() < int(day_i(S.LB0)) and fx.allent.end.max() < int(day_i(S.LB0)) and fx.gaap.n == 0 and fx.wa.n == 0
    finally:
        shutil.rmtree(root, ignore_errors=True)
    # book_checks on a synthetic book that does not match the registered structure: ok False, with the numbers
    B, _ = M17.synth_book(seed=2, hi="2025-06-27", deep=False)
    bk, dd, S12b = D15.book_checks(B)
    assert bk["ok"] is False and dd["ok"] is False and dd["days"] == S12b.n_dd_days and dd["episodes"] == len(S12b.qual)


# ------------------------------------------------------------------ [A13] one share class per firm, [A14] the hand audit's groups
def class_world(syms, cik_ix, dv):
    """a stand-in World for share_classes(): it reads only W.syms, W.ni.cik_ix and row f of W.ni.dv20 (here f = 1; row 0 holds a decoy that must not be read)"""
    return SimpleNamespace(syms=np.asarray(syms), ni=SimpleNamespace(cik_ix=np.asarray(cik_ix, np.int64), dv20=np.vstack([np.full(len(syms), -1.0), np.asarray(dv, float)])))


def ni_twin_toy(flip="2026-04-01"):
    """the toy world with an [A13] pair: N15 is a second share class of N14 (the same CIK K14 and N14's filings, no filing of its own: the same two facts, the same ISS wherever both are scored), 16 names, 700 sessions (N24 is scored from the 2026-02 ranks). N15's volume is scaled x0.3 before
    `flip` and x3 from it: N14 is the more liquid class well before the flip and N15 well after it (the ranks whose 20-session window straddles the flip are decided by the recount, not by hand). The scaling is on the raw arrays BEFORE attach_netiss reads them"""
    tt = ni_toy(seed=3, T=700, Sn=16, twin=((14, 15),))
    cut = tt.W.days.get_loc(TS(flip))
    tt.W.Vv[:cut, 15] *= 0.3
    tt.W.Vv[cut:, 15] *= 3.0
    return tt


def t_share_class():
    """[A13] ONE SHARE CLASS PER FIRM: (1) share_classes on hand numbers - the larger dollar volume keeps the score, flipping the volumes flips the winner, a tie goes to the LOWER SYMBOL (the symbol, not the column), an undefined dollar volume loses (and is counted), three classes keep one,
    the decision is per cell (a class with no score in the cell is not a candidate), names without a CIK are never grouped, the columns returned are World columns; (2) the whole pipeline on a toy world with a pair of classes against the plain-python recount in both readings - every pool, score,
    pick of both rules, decile, count and daily path, and the series - and by hand: the pair reads the same facts (identical ISS), only one of them is scored per rank in each cell, the winner is the more liquid class, the other is counted as 'second share class' and is never in the scored
    names, a pick, a decile, the composite twin or the null's draws (three draws recounted from the stream); (3) an exact volume tie (identical market arrays) goes to the lower symbol at every rank; (4) the counts: per rank, by year, per CIK, the printout, a counts-only build"""
    sc = lambda syms, ck, dv, cols, idx: share_classes(class_world(syms, ck, dv), 1, np.asarray(cols, np.int64), np.asarray(idx, np.int64))
    syms = ["GOOG", "GOOGL", "AAA", "FOX", "FOXA", "ZZ1", "ZZ2", "ZZ3"]
    ck, allc = [0, 0, 1, 2, 2, 3, 3, 3], list(range(8))
    keep, dr, kp, nd = sc(syms, ck, [5, 7, 4, 4, 4, 3, 8, 8], allc, allc)
    assert keep.tolist() == [False, True, True, True, False, False, True, False] and dict(zip(dr.tolist(), kp.tolist())) == {0: 1, 4: 3, 5: 6, 7: 6} and nd == 0, "GOOGL is the more liquid, FOX wins the tie by symbol, ZZ2 wins the tie of three"
    assert dr.dtype == np.int64 and kp.dtype == np.int64 and keep.dtype == bool
    keep, dr, kp, nd = sc(syms, ck, [9, 7, 4, 4, 4, 3, 8, 8], allc, allc)
    assert dict(zip(dr.tolist(), kp.tolist())) == {1: 0, 4: 3, 5: 6, 7: 6} and keep.tolist()[:2] == [True, False], "flipping the volumes flips the winner"
    keep, dr, kp, nd = sc(syms, ck, [5, 7, 4, 5, 4, 3, 8, 8], allc, allc)
    assert dict(zip(dr.tolist(), kp.tolist())) == {0: 1, 4: 3, 5: 6, 7: 6}, "FOX with the larger volume wins outright"
    keep, dr, kp, nd = sc(["FOXA", "FOX"], [0, 0], [4, 4], [0, 1], [0, 1])
    assert dr.tolist() == [0] and kp.tolist() == [1] and keep.tolist() == [False, True], "a tie goes to the lower SYMBOL (FOX, in column 1), never to the lower column"
    keep, dr, kp, nd = sc(["AA", "BB"], [0, 0], [float("nan"), 5.0], [0, 1], [0, 1])
    assert dr.tolist() == [0] and kp.tolist() == [1] and nd == 1, "an undefined dollar volume loses to a defined one and is counted"
    keep, dr, kp, nd = sc(["AA", "BB"], [0, 0], [float("nan"), float("nan")], [0, 1], [0, 1])
    assert dr.tolist() == [1] and kp.tolist() == [0] and nd == 1, "both undefined: the lower symbol"
    keep, dr, kp, nd = sc(["GOOG", "GOOGL", "AAA"], [0, 0, 1], [5.0, 7.0, 1.0], [0, 1, 2], [0, 2])
    assert keep.all() and not len(dr) and not len(kp) and nd == 0, "a cell where only one class has a score drops nothing - the more liquid class that has no score there never takes its place"
    keep, dr, kp, nd = sc(["GOOG", "GOOGL", "AAA"], [0, 0, 1], [5.0, 7.0, 1.0], [0, 1, 2], [1, 2])
    assert keep.all() and not len(dr), "the other cell, the other class"
    keep, dr, kp, nd = sc(["U1", "U2", "V"], [-1, -1, 0], [5.0, 7.0, 1.0], [0, 1, 2], [0, 1, 2])
    assert keep.all() and not len(dr), "names without a CIK are never grouped"
    keep, dr, kp, nd = sc(syms, ck, [5, 7, 4, 4, 4, 3, 8, 8], [7, 4, 1, 0, 3], [0, 1, 3, 4])
    assert keep.tolist() == [True, False, True, True] and dr.tolist() == [4] and kp.tolist() == [3], "positions into the pool, columns of the World: cols[idx] = ZZ3, FOXA, GOOG, FOX -> FOXA (column 4) is dropped for FOX (column 3); GOOG's sibling is not scored here"
    assert not len(sc(syms, ck, [1.0] * 8, [], [])[1]) and sc(syms, ck, [1.0] * 8, [0, 1], [])[0].shape == (0,), "nothing scored, nothing to decide"
    with spec(n_side=3, min_scored=8, min_side=2, dec_min=7), D15.spec(univ=16):
        # ---- (2) the pipeline on the twin world against the plain-python recount
        tt = ni_twin_toy()
        W = tt.W
        attach_netiss(W, build_facts(tt.frame), mp_of(tt.mrows), tt.cal)
        lo, hi = W.days[0], W.days[-1]
        j14, j15 = list(W.syms).index("N14"), list(W.syms).index("N15")
        assert tt.cik_of["N14"] == tt.cik_of["N15"] == "K14" and W.ni.cik_ix[j14] == W.ni.cik_ix[j15] >= 0 and int((W.ni.cik_ix >= 0).sum()) == 14 and len(set(W.ni.cik_ix[W.ni.cik_ix >= 0].tolist())) == 13, "14 mapped names with facts on 13 CIKs"
        assert np.array_equal(W.ni.dv20, D15.roll_prev(W.Cl * W.Vv, 20), equal_nan=True), "the dollar volume IS r15_ddw's own (the quantity the universe ranks on)"
        out = {}
        for pm in ("remove", "naive", "keep"):
            L = ni_build(W, lo, hi, pm)
            Bz = brute_ni(W, tt.frame, tt.cal, tt.cik_of, lo, hi, pm)
            compare_ni(W, L, Bz, f"twin {pm}")
            if pm == "remove":
                series_check_ni(W, L, Bz)
            out[pm] = (L, Bz)
        Lr, Bzr = out["remove"]
        drop = {c: Counter(int(d) for rec in Lr.recs for d in rec.cell[c].second) for c in CELLS}
        assert sum(drop["N12"].values()) >= 12 and sum(drop["N24"].values()) >= 4 and all(set(drop[c]) == {j14, j15} for c in CELLS), ("the rule fires in both cells and each class loses somewhere", drop)
        cut = W.days.get_loc(TS("2026-04-01"))
        n_hand = 0
        for rec in Lr.recs:
            f = rec.f
            for c in CELLS:
                cc, sc_ = rec.cell[c], rec.sc[c]
                cols = rec.pool[cc.idx]
                both = [j for j in (j14, j15) if j in rec.pool.tolist() and math.isfinite(sc_.iss[j])]
                assert len(both) - len({j14, j15} & set(cols.tolist())) == len(cc.second), (rec.r, c, "one class stays of a pair with two scores")
                if len(both) == 2:
                    assert sc_.iss[j14] == sc_.iss[j15], "the two classes read the same facts: the same ISS"
                    dv = {j: float(np.mean(W.Cl[f - 20:f, j] * W.Vv[f - 20:f, j])) for j in both}
                    assert abs(W.ni.dv20[f, j14] - dv[j14]) <= 1e-9 * dv[j14] and abs(W.ni.dv20[f, j15] - dv[j15]) <= 1e-9 * dv[j15], "rows f-20 .. f-1, the raw close x the raw volume"
                    win = j14 if dv[j14] > dv[j15] else j15
                    assert cc.kept.tolist() == [win] and cc.second.tolist() == [j14 + j15 - win], (rec.r, c, "the more liquid class keeps its score")
                    if f < cut - 25 or f > cut + 25:
                        assert win == (j14 if f < cut else j15), "N14 before the flip, N15 after it - by the construction of the volumes"
                        n_hand += 1
                else:
                    assert not len(cc.second)
                dropped = set(cc.second.tolist())
                picks = set()
                if cc.traded:
                    for sel in (cc.long, cc.short, cc.long_i, cc.short_i):
                        picks |= set(cols[sel].tolist())
                    assert cc.U.G.shape[0] == cc.n == len(cols)
                assert not dropped & set(cols.tolist()) and not dropped & picks and (cc.dec is None or len(cc.dec) == cc.n), (rec.r, c, "a second class is never scored, picked, cut into a decile or in the null's pool")
        assert n_hand >= 8, n_hand
        # the null: three whole draws per cell recounted from the stream - the drawn names are scored names, never a second class, every path recomputed
        acc = ni_null(W, Lr, 6, 0)
        slot = M17.SPEC["slot"]
        for q, cell in enumerate(CELLS):
            rng = np.random.default_rng([SEED, q, 0])
            draws = [(rec, D15.draw_order(rng, 6, rec.cell[cell].n, 2 * rec.cell[cell].k)) for rec in Lr.recs if rec.cell[cell].traded]
            assert len(draws) >= 5
            for d in (0, 3, 5):
                x0 = np.zeros(W.T)
                for rec, o in draws:
                    cc = rec.cell[cell]
                    cols = rec.pool[cc.idx]
                    assert not set(cols[o[d]].tolist()) & set(cc.second.tolist()), "a second class is never drawn"
                    for sd, sel in ((1, o[d][:cc.k]), (-1, o[d][cc.k:])):
                        for i in sel:
                            x0[rec.f:rec.x + 1] += slot * np.array(M17.brute_path(W, rec.f, rec.x, int(cols[i]), sd, bool(rec.naive[cc.idx[i]]))[0])
                assert close(acc[cell][d], x0), (cell, d)
        # ---- (4) the counts: per rank, by year, per CIK against the recount; the counts-only build is the same; the printout
        sm = second_class_summary(Lr, W)
        assert [r_["rank"] for r_ in sm["ranks"]] == [f"{W.days[b['r']]:%Y-%m-%d}" for b in Bzr]
        for r_, b in zip(sm["ranks"], Bzr):
            assert r_["year"] == W.days[b["f"]].year and all(r_["cells"][c] == {"pool_scored": b["cell"][c]["n_pre"], "second": len(b["cell"][c]["second"]), "scored": len(b["cell"][c]["scored"])} for c in CELLS), r_
        want = {}
        by_year = {c: Counter() for c in CELLS}
        for b in Bzr:
            for c in CELLS:
                for d, k in b["cell"][c]["second"].items():
                    ck_ = tt.cik_of[str(W.syms[d])]
                    for s_, key in ((str(W.syms[d]), "dropped"), (str(W.syms[k]), "kept")):
                        want.setdefault(ck_, {}).setdefault(s_, {}).setdefault(c, {"dropped": 0, "kept": 0})[key] += 1
                    by_year[c][int(W.days[b["f"]].year)] += 1
        years = sorted({int(W.days[b["f"]].year) for b in Bzr})
        assert sm["ciks"] == want and list(want) == ["K14"] and {c: {y: by_year[c].get(y, 0) for y in years} for c in CELLS} == sm["by_year"] and sm["total"] == {c: sum(by_year[c].values()) for c in CELLS} and sm["nan_dv"] == {"N12": 0, "N24": 0}
        for y, cn in Lr.cnt.items():
            for c in CELLS:
                assert cn[f"ns_{c}_second_share_class"] == by_year[c].get(y, 0), (y, c)
        Lc = ni_build(W, lo, hi, "remove", units=False, counts_only=True)
        assert second_class_summary(Lc, W) == sm and [(rec.cell[c].second.tolist(), rec.cell[c].kept.tolist(), rec.cell[c].n_pre, rec.cell[c].n) for rec in Lc.recs for c in CELLS] == [(rec.cell[c].second.tolist(), rec.cell[c].kept.tolist(), rec.cell[c].n_pre, rec.cell[c].n) for rec in Lr.recs for c in CELLS]
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            print_second_classes(sm)
            print_scored("registered", Lr.cnt)
        txt = buf.getvalue()
        assert "[A13] ONE SHARE CLASS PER FIRM" in txt and "the 1 CIKs it fires on" in txt and not re.search(r"[$]\s*-?\d|ROC|Sortino|P&L|net [$]|drawdown|Stage A \(|[+-]\d\.\d{3}\b|ISS per fill year", txt), "counts and the symbols of the CIKs only"
        for r_ in sm["ranks"]:
            assert f"    {r_['rank']}: " + " | ".join(f"{r_['cells'][c]['pool_scored']} -> {r_['cells'][c]['second']} -> {r_['cells'][c]['scored']}" for c in CELLS) in txt.splitlines()
        g = want["K14"]
        assert f"    K14: N14 {g['N14']['N12']['dropped']} / {g['N14']['N12']['kept']} | {g['N14']['N24']['dropped']} / {g['N14']['N24']['kept']}; N15 {g['N15']['N12']['dropped']} / {g['N15']['N12']['kept']} | {g['N15']['N24']['dropped']} / {g['N15']['N24']['kept']}" in txt.splitlines()
        for c in CELLS:
            assert f"[A13] {c} second-share-class name-ranks taken out, by fill year: " + ", ".join(f"{y}: {n}" for y, n in sm["by_year"][c].items()) + f" (total {sm['total'][c]:,})" in txt
            for y, v in sm["by_year"][c].items():
                line = [l_ for l_ in txt.splitlines() if l_.startswith(f"    {c} {y}: ")][0]
                assert int(line.split()[-1]) == v, "the no-score reasons by year carry the new column last"
        assert txt.count("second_share_class") == 1 and "second_share_class):" in txt
        sr = score_report(W, built_ranks(W, lo, hi), values=False)
        assert all("second_share_class" not in r_["cells"][c]["reasons"] for r_ in sr for c in CELLS), "the universe-level report is before the pool and before [A13]"
        # ---- (3) an exact volume tie: N15 a clone of N14 in every market array - the lower symbol (N14) is scored at every rank where both are
        tt2 = ni_twin_toy()
        W2 = tt2.W
        for a in (W2.Od, W2.Cl, W2.Vv, W2.F, W2.U, W2.chg, W2.msplit, W2.tbis):
            a[:, 15] = a[:, 14]
        W2.derive()
        attach_netiss(W2, build_facts(tt2.frame), mp_of(tt2.mrows), tt2.cal)
        assert np.array_equal(W2.ni.dv20[:, 14], W2.ni.dv20[:, 15], equal_nan=True)
        L2 = ni_build(W2, lo, hi, units=False, counts_only=True)
        n_tie = 0
        for rec in L2.recs:
            for c in CELLS:
                cc = rec.cell[c]
                both = [j for j in (j14, j15) if j in rec.pool.tolist() and math.isfinite(rec.sc[c].iss[j])]
                assert len(both) in (0, 2), "clones share their pool membership and their score"
                if both:
                    assert cc.second.tolist() == [j15] and cc.kept.tolist() == [j14], (rec.r, c, "a tie goes to the lower symbol")
                    n_tie += 1
        assert n_tie >= 15, n_tie
        Bz2 = brute_ni(W2, tt2.frame, tt2.cal, tt2.cik_of, lo, hi, "remove")
        assert [dict(zip(rec.cell[c].second.tolist(), rec.cell[c].kept.tolist())) for rec in L2.recs for c in CELLS] == [b["cell"][c]["second"] for b in Bz2 for c in CELLS]


def brute_group(W, frame, cal, cik_of, j, r, cell, cache):
    """plain python [A14]: the group key of the name-rank (World column j, rank row r, cell): 'symbol|accn_now|accn_prior' of the two facts behind its score - '' where the name has no pair at that rank (no complete pair of one concept)"""
    sym = str(W.syms[j])
    b = brute_score(W, frame, cal, j, cik_of.get(sym, ""), int(W.ni.static[j]), r, KS[cell], cache)
    if not b.use:
        return ""
    bf = brute_facts(W, frame, cik_of[sym], r, KS[cell], b.use)
    return f"{sym}|{bf['now'][3]}|{bf['prior'][3]}"


def t_audit_groups():
    """[A14] the hand audit's scope on the toy world: every flagged name-rank carries the cell / side of its picks (either side, either cell - recounted from the plain-python picks) and its GROUP (symbol + the accession numbers of the two facts, recounted from the filings); a group holds the
    consecutive ranks that use the same two filings (the same ISS); an audit row covers its whole group - audit_status counts the picked groups and the top-50 contributors through it, and a data_event row removes every name-month of its group from the pool (the plain-python members), not one more"""
    with spec(n_side=3, min_scored=8, min_side=2, dec_min=7), D15.spec(univ=14):
        tt = toy_ready()
        W, frame, cal, cik_of = tt.W, tt.frame, tt.cal, tt.cik_of
        lo, hi = W.days[0], W.days[-1]
        L = ni_build(W, lo, hi)
        ranks = built_ranks(W, lo, hi)
        Bz = brute_ni(W, frame, cal, cik_of, lo, hi, "remove")
        sym_ix = {str(s): j for j, s in enumerate(W.syms)}
        cache = {}
        want_pick = defaultdict(list)
        for b in Bz:
            for c in CELLS:
                for sd in ("long", "short"):
                    for j in b["cell"][c][sd]:
                        want_pick[(b["f"], j)].append(f"{c}/{sd}")
        assert dict(picks_by_name_month(L)) == dict(want_pick) and len(want_pick) > 20, "the registered picks by name-month: the cells' ISS picks, cell / side, in the order N12 long, N12 short, N24 long, N24 short"
        a10 = a10_rows(W, ranks, L)
        for row in a10:
            j, f = sym_ix[row["symbol"]], W.days.get_loc(TS(row["date"]))
            assert row["picked"] == ", ".join(want_pick.get((f, j), [])), row
            assert row["group"] == brute_group(W, frame, cal, cik_of, j, f - 1, row["cell"], cache) != "", row
        groups = defaultdict(list)
        for row in a10:
            groups[(row["cell"], row["group"])].append(row)
        assert len(a10) == 21 and sum(1 for x in a10 if x["picked"]) == 18 and len(groups) == 9, "the toy's flagged name-ranks: 21, 18 of them picked, in 9 groups"
        assert all(len({x["iss"] for x in g}) == 1 and len({x["symbol"] for x in g}) == 1 and len({x["accn_now"] for x in g}) == 1 and len({x["accn_prior"] for x in g}) == 1 for g in groups.values()), "one group = one symbol on the same two filings = one score"
        mixed = [(k, g) for k, g in groups.items() if any(x["picked"] for x in g) and any(not x["picked"] for x in g)]
        assert mixed and max(len(g) for g in groups.values()) == 3, "a group of three month-ends on the same two filings, picked in only one of them"
        other = [x for x in a10 if x["picked"] and not any(p.startswith(x["cell"]) for p in x["picked"].split(", "))]
        assert other, "a flagged name-rank of one cell picked only in the OTHER cell counts as picked (either cell)"
        (kc, kg), g1 = mixed[0]
        assert kc == "N12" and [x["picked"] for x in g1] == ["", "", "N12/short"], (kc, kg, [x["picked"] for x in g1])
        unp = [x for x in a10 if not x["picked"] and (x["cell"], x["group"]) != (kc, kg)]
        assert unp and all(x["symbol"] == "N13" for x in unp), "the only other unpicked flagged name-rank is N13's (it stops printing inside the hold: removed before the ranking)"
        picked_groups = {c: {k[1] for k, g in groups.items() if k[0] == c and any(x["picked"] for x in g)} for c in CELLS}
        # --- audit rows: one 'keep' on an UNPICKED member of a picked group covers the group; a row covers the name-month's groups in both cells
        d_unp, sym1 = g1[0]["date"], g1[0]["symbol"]
        n01 = [x for x in a10 if x["symbol"] == "N01"]
        assert n01 and all(x["cell"] == "N24" and x["picked"] == "N12/short" for x in n01)
        au1 = pd.DataFrame({"symbol": [sym1, "N01"], "date": pd.to_datetime([d_unp, n01[0]["date"]]), "cell": ["N12", "N24"], "verdict": ["keep", "keep"], "note": ["", ""]})
        keys1 = audit_keys(W, au1)
        want_keys = set()
        for sym_, d_ in ((sym1, d_unp), ("N01", n01[0]["date"])):
            f_ = W.days.get_loc(TS(d_))
            want_keys |= {k for k in (brute_group(W, frame, cal, cik_of, sym_ix[sym_], f_ - 1, c, cache) for c in CELLS) if k}
        assert keys1 == want_keys and kg in keys1 and n01[0]["group"] in keys1 and len(keys1) >= 3, (keys1, want_keys)
        cands = {}
        for cell in CELLS:
            run = M17.run_cell(W, cell_leg(L, cell), D15.l1_cfg(), pos=True)
            cands[cell] = ni_candidate_rows(W, L, cell, run, None, {}, n=1000)                                  # every position, so the picked members of a group are among them
            assert all(x["group"] == brute_group(W, frame, cal, cik_of, sym_ix[x["symbol"]], W.days.get_loc(TS(x["date"])) - 1, cell, cache) for x in cands[cell]), "the contributors carry their group too"
        st = audit_status(W, cands, a10, au1)
        have = {(sym1, d_unp), ("N01", n01[0]["date"])}
        for cell in CELLS:
            rows = cands[cell]
            n_cov = sum(((x["symbol"], x["date"]) in have) or x["group"] in want_keys for x in rows)
            fl = [x for x in a10 if x["cell"] == cell]
            pg = {x["group"] for x in fl if x["picked"]}
            assert st[cell] == {"listed": len(rows), "audited": n_cov, "audit_complete": bool(rows and n_cov == len(rows)), "groups": len({x["group"] for x in rows}), "a10_flagged": len(fl), "a10_picked": sum(1 for x in fl if x["picked"]),
                                "a10_listed": len(pg), "a10_audited": len(pg & want_keys), "a10_complete": pg <= want_keys}, (cell, st[cell])
        assert st["N12"]["a10_listed"] == len(picked_groups["N12"]) == 5 and st["N12"]["a10_audited"] == 1 and st["N24"]["a10_listed"] == len(picked_groups["N24"]) == 3 and st["N24"]["a10_audited"] == 1, st
        assert any(x["group"] == kg and (x["symbol"], x["date"]) not in have for x in cands["N12"]) and st["N12"]["audited"] >= 1, "a contributor of the group is audited through the row of another month on the same two filings"
        d3 = [x["date"] for x in a10 if x["symbol"] == "N10" and x["cell"] == "N24"][0]
        au2 = pd.concat([au1, pd.DataFrame({"symbol": ["N10"], "date": pd.to_datetime([d3]), "cell": ["N12"], "verdict": ["keep"], "note": [""]})], ignore_index=True)
        st2 = audit_status(W, cands, a10, au2)
        assert st2["N12"]["a10_audited"] == 2 and st2["N24"]["a10_audited"] == 2, "one row covers the name-month's group in each cell: N10's N12 group and its N24 group"
        assert audit_status(W, cands, a10, None)["N12"]["a10_audited"] == 0 and audit_status(W, cands, a10, None)["N12"]["a10_listed"] == 5
        # --- a data_event row removes every name-month of its group - the plain-python members, no more - from the pool
        au3 = pd.DataFrame({"symbol": [sym1], "date": pd.to_datetime([d_unp]), "cell": ["N12"], "verdict": ["data_event"], "note": ["x"]})
        cnt = apply_audit(W, au3)
        j1 = sym_ix[sym1]
        keys_g = want_keys_of(W, frame, cal, cik_of, j1, d_unp, cache)
        members = sorted(r + 1 for r in range(W.T - 1) if (W.days[r].year, W.days[r].month) != (W.days[r + 1].year, W.days[r + 1].month) and r >= M17.SPEC["win"] - 1
                         and any(brute_group(W, frame, cal, cik_of, j1, r, c, cache) in keys_g for c in CELLS))
        assert len(members) == 3 and members == sorted(W.days.get_loc(TS(x["date"])) for x in g1), "the group's name-months: the month-ends on the same two filings"
        assert cnt == {"rows": 1, "keep": 0, "data_event": 1, "group_name_months": 2} and set(zip(*np.nonzero(W.aud1))) == {(f, j1) for f in members}, (cnt, np.argwhere(W.aud1).tolist())
        L3 = ni_build(W, lo, hi)
        for rec0, rec3 in zip(L.recs, L3.recs):
            if rec3.f in members:
                assert j1 not in rec3.pool.tolist() and set(rec0.pool.tolist()) - {j1} == set(rec3.pool.tolist()), "the name-month is out of the pool (so of both cells and both nulls), nobody else is"
            else:
                assert rec0.pool.tolist() == rec3.pool.tolist()
        assert sum(v["audit"] for v in L3.cnt.values()) == sum(1 for rec in L.recs if rec.f in members and j1 in rec.pool.tolist()) >= 1, "counted at the first reason: a member the hold's hygiene removes anyway is counted there"
        assert any(j1 in rec.pool.tolist() for rec in L.recs if rec.f in members) and any(j1 not in rec.pool.tolist() for rec in L.recs if rec.f in members), "the group holds a member in the pool and members the pool never had"
        assert unused_audit_rows(W, au3) == [], "the row's own name-month was in the universe, so it removed something"
        W.aud1[:] = False
        W.aud_hit.clear()


def want_keys_of(W, frame, cal, cik_of, j, date, cache):
    """plain python: the group keys of the name-month (World column j, fill date) in both cells"""
    f = W.days.get_loc(TS(date))
    return {k for k in (brute_group(W, frame, cal, cik_of, j, f - 1, c, cache) for c in CELLS) if k}


# ------------------------------------------------------------------ smoke: an offline end-to-end run on SYNTHETIC worlds (every number means nothing)
SMOKE_THETA = 1.0                                  # the planted effect: a daily drift of -theta x (the name's annual net-issuance rate) / 252 - in the PLANTED world only; the NULL world has the same share counts and no drift
SMOKE_SPEC = {"n_side": 15, "min_scored": 45, "min_side": 10}      # the synthetic market has ~65 scored names a month, not the 150 .. 500 of the real one: 15 a side (the top / bottom third below 45 scored names, at least 10 a side)
SMOKE_CUT = "2025-06-30"
SMOKE_NAMES = [f"S{k:02d}" for k in range(1, 35)] + ["LOWP", "LOWV", "LOWA", "SPL", "RVS", "DLST"] + [f"D{k:02d}" for k in range(1, 41)]      # r5_siporb's fake Alpaca + r18_divrun's 40 payers
SMOKE_NOFILE = {"S03"}                             # in the cache, facts on file, NOT in the map
SMOKE_BASE_MAP = {"S04": ("", "name_ambiguous"), "S05": ("", "unmapped"), "S06": (None, "current_ticker_name_mismatch"), "S07": (None, "non_common"), "D37": ("", "name_ambiguous"), "D38": ("", "unmapped"), "D39": (None, "current_ticker_name_mismatch")}
SMOKE_DUAL = ("D04", "D11")                        # [A13] the synthetic market's one pair of share classes: (the name that files, the second class that reads ITS CIK and so the same two facts) - two payers that are in the pool at every rank, with dollar volumes that cross (each is the more liquid class at some ranks)
SMOKE_ADDITIONS = ("D37", "D38", "D39")            # TV's reviewed additions: usable rows over unusable base rows, their facts in the additions file


def smoke_refusal(root):
    """r17_resmom's guards (the dir is wiped: a 'smoke' name, never OUT / CACHE / the repo / this harness / the working directory / C:\\EdgeLog, the other families' OUTs, the #463 records) + this harness's OUT"""
    why = M17.smoke_refusal(root)
    if why:
        return why
    real = lambda p: os.path.normcase(os.path.realpath(p))
    try:
        if os.path.commonpath([real(root), real(OUT)]) == real(root):
            return f"smoke refused: {root} is or holds NETISS OUT"
    except ValueError:
        pass
    return None


def smoke_shares(seed=41):
    """the synthetic net-issuance world: per name an annual log growth of its share count (a persistent rate in -10% .. +18% and a yearly noise of 3%), an initial count; log_shares(k, t) integrates the rates piecewise by calendar year from 2014-01-01"""
    rng = np.random.default_rng(seed)
    N = len(SMOKE_NAMES)
    base = rng.uniform(-0.10, 0.18, N)
    g = {k: {y: float(base[k] + rng.normal(0.0, 0.03)) for y in range(2014, 2027)} for k in range(N)}
    s0 = rng.uniform(40.0, 900.0, N) * 1e6
    return SimpleNamespace(base=base, g=g, s0=s0)


def log_shares(sh, k, t):
    """log of the name's organic share count on date t (no split): log S0 + the sum over the years of rate x the fraction of that year elapsed since 2014-01-01"""
    t = TS(t)
    out, y = math.log(sh.s0[k]), 2014
    while y <= t.year:
        a, b = TS(f"{y}-01-01"), min(TS(f"{y + 1}-01-01"), t)
        if b > a:
            out += sh.g[k][y] * (b - a).days / 365.25
        y += 1
    return out


def smoke_drift(days, sh, theta):
    """the planted drift of every name-session: -theta x (the name's annual rate in that calendar year) / 252"""
    g = np.array([[sh.g[k][int(y)] for k in range(len(SMOKE_NAMES))] for y in days.year])
    return -theta * g / 252.0


class NetFake(DV.DivFake):
    """r18_divrun's synthetic daily market (80 names on continuous business days through r5_siporb's fake Alpaca transport, close-to-close log return = beta x the fake ES master's return + noise, the calendar's dividends taken off the open of the ex-date, the special names of S.Fake with their
    plants: SPL's 2-for-1 on 2024-03-15, S18's x4 that no adjustment shows on 04-22, S23's +60% gap on 05-14, DLST's last bar on 05-31, S33 / S34's late starts, LOWP / LOWV / LOWA below the filters, RVS's reverse split) + S20's 3-for-1 on 2023-03-15 that only the price factor F shows (the calendar
    has none) and `drift` (D, N) added to every name's daily log return: the planted issuance effect (zeros = the null world: the same random numbers, no effect)"""
    def __init__(self, days, mkt, div, drift=None, page=2500):
        self.days, self.D, self.page, self.n, self.auth_fail, self._st, self._rowcache = [f"{d:%Y-%m-%d}" for d in days], len(days), page, 0, False, {}, {}
        rng = np.random.default_rng(11)
        self.names = names = list(SMOKE_NAMES)
        self.k, N, ix, dx = {n: k for k, n in enumerate(names)}, len(names), names.index, self.days.index
        D = self.D
        self.p0, self.vol = rng.uniform(150.0, 500.0, N), rng.uniform(1.5e6, 6e6, N)
        beta, idio = rng.uniform(0.5, 1.5, N), rng.uniform(0.009, 0.014, N)
        self.p0[ix("LOWP")], self.vol[ix("LOWV")], self.p0[ix("LOWA")], idio[ix("LOWA")], self.p0[ix("SPL")], self.p0[ix("RVS")] = 3.0, 3e5, 10.0, 0.0015, 400.0, 150.0
        self.vol[ix("SPL")] = 8e6                                                                 # the raw pre-split volume is half the adjusted one: keep SPL above the 1M-share floor before its split
        self.vol[ix("S20")] = 8e6                                                                 # ... and a third of it for S20
        self.first, self.last = np.zeros(N, int), np.full(N, D - 1)
        self.first[ix("S33")], self.first[ix("S34")], self.last[ix("DLST")] = dx("2016-02-01"), dx("2024-02-01"), dx("2024-05-31")
        self.gday = {ix("SPL"): (dx("2024-03-15"), 2.0), ix("RVS"): (dx("2016-02-17"), 0.2), ix("S20"): (dx("2023-03-15"), 3.0)}
        self.msp = {ix(self.MSPLIT[0]): (dx(self.MSPLIT[1]), self.MSPLIT[2])}
        self.jump = {ix(self.GAP[0]): (dx(self.GAP[1]), self.GAP[2])}
        eps = rng.standard_normal((D, N)) * idio
        gap = rng.standard_normal((D, N)) * 0.003
        w1, w2 = np.abs(rng.standard_normal((D, N))) * 0.004, np.abs(rng.standard_normal((D, N))) * 0.004
        vn = rng.lognormal(0.0, 0.25, (D, N))
        r = beta * np.asarray(mkt, float)[:, None] + eps
        if drift is not None:
            r = r + drift
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


def smoke_cik(name):
    """the synthetic CIK of a symbol (SMOKE_DUAL's second name shares the first's: a dual-class pair)"""
    k = 1 + SMOKE_NAMES.index(SMOKE_DUAL[0] if name == SMOKE_DUAL[1] else name)
    return f"{100000 + k:010d}"


def smoke_filings(sh, seed=53):
    """the synthetic filings of every name: quarterly cover-page (dei) and balance-sheet (us-gaap) share counts from the organic path (log_shares) times the splits that name has (SPL x2 from 2024-03-15, RVS x0.2 from 2016-02-17, S20 x3 from 2023-03-15 - F shows both and the calendar one;
    S18 x0.25 from 2024-04-22 - the calendar shows it and F does not), the annual weighted-average rows, 10-K rows for the fourth quarter, later comparatives that restate and amendments, and the planted cases: S02 a foreign filer (20-F), S09 balance sheet only, S10 a cover page that starts in 2018 (the fallback), S11 a x100
    scale error, S12 a x2 stock-paid jump from 2021-03-15, S13 two accessions of one day with two values, S14 an amendment for every filing, S15 half its balance-sheet rows, S16 whose first fact is in 2020, S17 a 100-day filer, S19 a zero, S21 a Saturday filer, S08 no filing at all.
    -> rows [(cik, concept, val, end, filed, form, accn, unit, start)] with dates 'YYYY-MM-DD', every row (the callers cut them); the quarter-ends reach 2025-09-30 (the sealed year's filings are in the full file only)"""
    rng = np.random.default_rng(seed)
    rows, n_acc = [], [0]
    ds = lambda t: f"{TS(t):%Y-%m-%d}"
    mult = {"SPL": [("2024-03-15", 2.0)], "RVS": [("2016-02-17", 0.2)], "S20": [("2023-03-15", 3.0)], "S18": [("2024-04-22", 0.25)], "S12": [("2021-03-15", 2.0)]}
    for k, nm in enumerate(SMOKE_NAMES):
        if nm in ("S08", SMOKE_DUAL[1], "LOWP", "LOWV", "LOWA") or nm in ("S04", "S05"):
            continue
        cik, off = smoke_cik(nm), k % 3
        foreign = nm == "S02"
        qf, yf = ("20-F", "20-F") if foreign else ("10-Q", "10-K")
        val_at = lambda t, nm=nm, k=k: float(round(math.exp(log_shares(sh, k, t)) * math.prod(m for d_, m in mult.get(nm, []) if TS(d_) <= TS(t)) * (1.0 + rng.normal(0.0, 0.002))))

        def put(con, val, end, filed, form, start=None, accn=None):
            n_acc[0] += 1
            rows.append((cik, con, val, ds(end), ds(filed), form, accn or f"{cik}-{n_acc[0]:06d}", "shares", "" if start is None else ds(start)))
        for q in range(0, 46):
            qe = TS("2014-12-31") + pd.DateOffset(months=3 * q - off)
            if qe > TS("2025-09-30"):
                break
            tenk = q % 4 == 0                                                                           # the fiscal year-end is every fourth quarter-end: a 10-K, filed later than a 10-Q
            cover = qe + pd.Timedelta(days=int(rng.integers(55, 70)) if tenk else int(rng.integers(20, 45)))
            filed = cover + pd.Timedelta(days=int(rng.integers(1, 7)))
            form = yf if tenk else qf
            if nm == "S17":
                filed = cover + pd.Timedelta(days=100)
            if nm == "S21":
                filed = cover + pd.Timedelta(days=int((5 - cover.dayofweek) % 7 or 7))
            cv, bs = val_at(cover), val_at(qe)
            if nm == "S11" and TS("2020-04-15") <= cover <= TS("2020-07-31"):
                cv *= 100.0
            if nm == "S19" and TS("2022-04-01") <= cover <= TS("2022-07-31"):
                cv = bs = 0.0
            if nm != "S09" and not (nm == "S10" and cover < TS("2018-01-01")) and not (nm == "S16" and cover < TS("2020-01-01")):
                put(DEI, cv, cover, filed, form)
                if nm == "S13" and TS("2019-04-01") <= cover <= TS("2019-07-31"):
                    put(DEI, cv * 1.1, cover, filed, form)                                               # the same day, another accession, another value: ambiguous
                if nm == "S14" or rng.random() < 0.03:
                    put(DEI, cv * float(rng.uniform(0.5, 1.5)), cover, filed + pd.Timedelta(days=40), form + "/A")      # an amendment: another value, later - the first filed stands
            if not (nm == "S15" and rng.random() < 0.5) and not (nm == "S16" and qe < TS("2019-12-31")):
                put(GAAP, bs, qe, filed, form)
                if tenk and rng.random() < 0.3:
                    put(GAAP, bs * float(rng.uniform(0.95, 1.05)), qe, filed + pd.Timedelta(days=360), form)        # a later comparative that restates the year-old value
            if tenk and not (nm == "S16" and qe < TS("2019-12-31")):
                put(WAC, val_at(qe - pd.Timedelta(days=180)), qe, filed, form, start=qe - pd.Timedelta(days=364))
    return rows


def smoke_maps():
    """the synthetic symbol -> CIK maps: the base map (every cached name; the planted unusable methods; S03 absent) and TV's additions (usable rows over D37 / D38 / D39's unusable ones) -> (base rows, additions rows, the CIKs whose facts go to the additions file)"""
    base, add = [], []
    for nm in SMOKE_NAMES:
        if nm in SMOKE_NOFILE:
            continue
        cik, meth = SMOKE_BASE_MAP.get(nm, (None, "current_ticker"))
        cik = smoke_cik(nm) if cik is None else cik
        base.append((nm, cik, meth))
    for nm in SMOKE_ADDITIONS:
        add.append((nm, smoke_cik(nm), "reviewed_same_firm"))
    return base, add, {smoke_cik(nm) for nm in SMOKE_ADDITIONS}


def smoke_write_files(root, sh):
    """the four pinned files as the real ones are laid out (and the sealed-year-extended twins of the two flat files for Stage B): the base facts without a row filed on / after the cut, TV's additions' facts (the CIKs of SMOKE_ADDITIONS) the same way, the two maps; the `_full` facts files hold every row
    filed before the lockbox's end (2026-07-01) - the second extract a dated addendum would pin (LB_FACTS) -> namespace (files, shas, full_files, full_shas, rows_all, rows_cut, base_map, add_map)"""
    d = os.path.join(root, "xbrl")
    os.makedirs(d)
    rows = smoke_filings(sh)
    base_m, add_m, add_ciks = smoke_maps()
    before = lambda rs, day: [r for r in rs if r[4] < day]
    base_r, add_r = [r for r in rows if r[0] not in add_ciks], [r for r in rows if r[0] in add_ciks]
    files = {"facts": os.path.join(d, "shares_asfiled_wide.csv"), "facts_add": os.path.join(d, "shares_asfiled_additions_reviewed.csv"), "map": os.path.join(d, "symbol_cik_map_wide_symbols_siporb_floor_2016_2025.csv"),
             "map_add": os.path.join(d, "symbol_cik_map_wide_additions_reviewed.csv")}
    full = {"facts": os.path.join(d, "shares_asfiled_wide_to_2026-06-30.csv"), "facts_add": os.path.join(d, "shares_asfiled_additions_reviewed_to_2026-06-30.csv")}
    cut, end = f"{S.LB0:%Y-%m-%d}", f"{S.END:%Y-%m-%d}"
    shas = {"facts": write_facts(files["facts"], before(base_r, cut)), "facts_add": write_facts(files["facts_add"], before(add_r, cut)), "map": write_map(files["map"], base_m), "map_add": write_map(files["map_add"], add_m)}
    full_shas = {"facts": write_facts(full["facts"], before(base_r, end)), "facts_add": write_facts(full["facts_add"], before(add_r, end))}
    return SimpleNamespace(files=files, shas=shas, full_files=full, full_shas=full_shas, rows_all=rows, rows_cut=before(rows, cut), base_map=base_m, add_map=add_m, add_ciks=add_ciks, dir=d)


@contextlib.contextmanager
def smoke_env(root, nrep=100, build=("plant", "null")):
    """everything the smoke patches, restored on exit: OUT and every module's output folder into `root`, CHECK_BOOK off, NREP = nrep, SPEC shrunk to the synthetic market, the wide calendar's pinned sha = the synthetic file's, the four pinned XBRL / map files = the synthetic ones (FILES / FILE_SHA),
    r5_siporb's transport = NetFake (one cache per world), the ES registry = the fake master, the TBIS file, a fake #463, a stub of RESMOM's line file as the registered one. Builds the worlds in `build` ('plant' = the planted issuance effect, 'null' = none, the same share counts and the same
    random numbers) through r5_siporb's own pulls. Yields a namespace: root, days, esf, div, spin, split, fk {world: NetFake}, cache {world: folder}, switch(world), wide_sha, wide_csv, wide_manifest, ref_csv, ref_sha, sh (the share-count world), xb (the synthetic files), lb_facts (the
    second extract Stage B would pin)"""
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
            ca_rows = DV.smoke_ca_text(div, spin, split) + [SMOKE_REVERSE_ROW]                   # + S18's reverse split: the calendar shows it, the cache's factor F does not ([A3]'s calendar side)
            sh = smoke_shares()
            drift = smoke_drift(days, sh, SMOKE_THETA)
            env = SimpleNamespace(root=root, days=days, esf=esf, mkt=mkt, div=div, spin=spin, split=split, fk={}, cache={}, wide_files={}, ca_rows=ca_rows, rows_in_calendar=len(ca_rows), sh=sh)
            for world in build:
                fk = NetFake(days, mkt, div, drift=drift if world == "plant" else None)
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
            # [A1] / [A8] the four pinned files, SYNTHETIC (never the real extract), registered for this run by their shas; the sealed-year extension Stage B would pin
            env.xb = smoke_write_files(root, sh)
            assert all(inside(p) for p in list(env.xb.files.values()) + list(env.xb.full_files.values())), "the synthetic XBRL / map files are inside the smoke dir"
            env.lb_facts = {k: (env.xb.full_files[k], env.xb.full_shas[k]) for k in ("facts", "facts_add")}
            es.enter_context(patched(THIS, FILES=dict(env.xb.files), FILE_SHA=dict(env.xb.shas)))

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


SMOKE_REVERSE_ROW = "reverse_split,S18,,,2024-04-22,2024-04-22,,,,1,4,,"      # the wide calendar's row for S18's 1-for-4 reverse split (the cache's factor never adjusted it)


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
    """the dryload's printout is COUNTS: no share count, ISS value, price, return, P&L or statistic (nothing like a dollar amount, ROC, Sortino, a drawdown, a signed three-decimal number - the shape every ISS percentile is printed in), no date on / after the cut but the one line that names the
    cut, the count lines it promises"""
    body = "\n".join(l for l in txt.splitlines() if "BEFORE ANY P&L" not in l)                         # (the score block's own heading says 'before any P&L')
    outcome = re.search(r"[$]\s*-?\d|ROC|Sortino|P&L|net [$]|drawdown|Stage A \(|[+-]\d\.\d{3}\b|ISS per fill year", body)
    assert not outcome, ("the dryload printed an outcome", body[max(outcome.start() - 80, 0):outcome.end() + 80])
    dates = [d for l in txt.splitlines() if "cut to dates <" not in l for d in re.findall(r"\b20\d\d-\d\d-\d\d\b", l)]
    assert dates and all(d < "2025-06-30" for d in dates), [d for d in dates if d >= "2025-06-30"][:5]
    for frag in ("universe size per session by year", "[A1] / [A8] pinned files", "map:", "facts:", "entries cover page (dei)", "BEFORE ANY P&L", "names lost to each rule", "excluded at |ISS| > ln(10) and counted", "[A3] a calendar split", "[A11] unscored ADRs", "scored names per rebalance",
                 LAB_J, LAB_R, "TBIS flags:", "ES prints on the", "ES return (", "cache manifest sha256", "prereg check:", "rebalances:", "names with a full window", "the fallback rule",
                 "[A13] ONE SHARE CLASS PER FIRM", "[A13] per rank (rank date: pool names with a score -> second share classes taken out -> scored names left", "second-share-class name-ranks taken out, by fill year", "CIKs it fires on", "groups decided with an undefined dollar volume"):
        assert frag in txt, frag


SMOKE_RANK_MONTHS = ("2017-01", "2017-06", "2018-01", "2019-06", "2019-09", "2020-06", "2020-07", "2020-09", "2021-06", "2022-06", "2022-09", "2023-04", "2023-06", "2024-03", "2024-04", "2024-05", "2025-03", "2025-04")      # the ranks whose scores the smoke recounts name by name, every planted case among them


def smoke_plant_checks(W, ni, mp, frame, finfo, fx, cal, env):
    """the planted world through the REAL loaders: the cut, the planted hygiene / split / map / filing cases, the score of EVERY name at 18 ranks (both cells) against the plain-python recount, and the pre-P&L report's lists -> (srows, the recount counts)"""
    ix = list(W.syms)
    di = lambda s: W.days.get_loc(TS(s))
    cik_of = dict(zip(mp.df["symbol"], mp.df["cik"]))
    xb = env.xb
    assert W.days.max() < S.LB0 and W.days[0] == TS("2015-11-02") and len(W.days) == len(pd.bdate_range("2015-11-02", "2025-06-27")), "nothing on / after the cut"
    spl, s18, s20, s23, dl = (ix.index(n_) for n_ in ("SPL", "S18", "S20", "S23", "DLST"))
    assert W.chg[di("2024-03-15"), spl] and W.fl[1][di("2024-04-22"), s18] and not W.chg[:, s18].any() and W.chg[di("2023-03-15"), s20] and W.fl[3][di("2024-05-14"), s23] and np.isfinite(W.Cl[di("2024-05-31"), dl]) and np.isnan(W.Cl[di("2024-06-03"), dl]), \
        "the planted hygiene / split cases arrive through the loaders (S20's x3 is in the cache's factor and not in the calendar, S18's x4 is in the calendar and not in the factor)"
    assert abs(W.F[di("2023-03-14"), s20] / W.F[di("2023-03-15"), s20] - 3.0) < 1e-6 and abs(W.F[di("2024-03-14"), spl] / W.F[di("2024-03-15"), spl] - 2.0) < 1e-6 and (W.F[:, s18] == 1.0).all(), "the split factor F carries the two forward splits and not the reversal"
    assert cal.split[cal.split["symbol"] == "S18"]["type"].tolist() == ["reverse_split"] and cal.split[cal.split["symbol"] == "S20"].empty and cal.split[cal.split["symbol"] == "SPL"]["type"].tolist() == ["forward_split"], "the calendar's splits"
    # [A1] / [A8] the pinned files read as ONE table / ONE map
    mi = mp.info
    assert mi["base_rows"] == len(xb.base_map) and mi["additions_rows"] == 3 and mi["additions_superseding_unusable_base_rows"] == {"name_ambiguous": 1, "unmapped": 1, "current_ticker_name_mismatch": 1} and mi["ciks_with_two_or_more_symbols"] == 1, mi
    assert finfo["files"]["facts"] + finfo["files"]["facts_add"] == finfo["rows_read"] == finfo["rows"] == len(xb.rows_cut) and finfo["files"]["facts_add"] == sum(1 for r in xb.rows_cut if r[0] in xb.add_ciks) > 0, finfo
    assert finfo["rows_filed_on_or_after_the_cut"] == 0 and finfo["rows_end_on_or_after_the_cut"] == 0 and finfo["rows_unit_not_shares"] == 0 and finfo["rows_other_concept"] == 0 and finfo["rows_value_missing"] == 0 and finfo["rows_unreadable_date"] == 0, finfo
    assert max(r[4] for r in xb.rows_all) > "2025-12-01" > "2025-06-30" > max(r[4] for r in xb.rows_cut), "the synthetic world holds filings of the sealed year and the pinned files hold none"
    code = {n_: REASONS[int(ni.static[ix.index(n_)])] for n_ in ("S02", "S03", "S04", "S05", "S06", "S07", "S08", "S01", "D37", "D38", "D39") + SMOKE_DUAL}
    assert code == {"S02": "foreign_filer", "S03": "not_in_map", "S04": "map_ambiguous", "S05": "map_unmapped", "S06": "map_mismatch", "S07": "map_non_common", "S08": "no_facts_for_cik", "S01": "scored", "D37": "scored", "D38": "scored", "D39": "scored", SMOKE_DUAL[0]: "scored", SMOKE_DUAL[1]: "scored"}, code
    assert ni.cik_ix[ix.index(SMOKE_DUAL[0])] == ni.cik_ix[ix.index(SMOKE_DUAL[1])] >= 0 and fx.info["ciks_foreign_only"] == 1 and fx.info["dei"]["ambiguous"] >= 1 and fx.info["dei"]["later_filing_carries_another_value"] >= 10 and fx.info["wa_annual"]["entries"] > 100, fx.info
    # the score of every name at every chosen rank against the plain-python recount
    ranks = built_ranks(W, WF0, PRE_END)
    by_month = {f"{W.days[r]:%Y-%m}": r for r, _f, _x in ranks}
    chosen = [by_month[m] for m in SMOKE_RANK_MONTHS]
    t0 = time.time()
    n_score = compare_scores(W, frame, cal, ix, cik_of, chosen)
    assert n_score == len(chosen) * 2 * len(ix), n_score
    srows = score_report(W, ranks, values=True)
    named = lambda c, key: {n_ for r_ in srows for n_ in r_["cells"][c][key]}
    for c in CELLS:
        assert "S11" in named(c, "ln10_names"), (c, "the x100 scale error is excluded and listed")
        assert "S20" in named(c, "split_F_not_in_calendar_names") and "S18" in named(c, "split_calendar_not_in_F_names"), (c, "[A3] both ways")
        assert not {"SPL", "RVS", "S12", "S01"} & (named(c, "split_F_not_in_calendar_names") | named(c, "split_calendar_not_in_F_names") | named(c, "ln10_names")), (c, "a split F and the calendar both show is no failure; a real issuance jump (S12) stays")
        tot = lambda k: sum(r_["cells"][c][k] for r_ in srows)
        assert tot("scored") > 4000 and tot("straddle") > 0 and tot("stale") > 0 and tot("fallback_to_gaap") >= 3 and tot("f_alone") > 0 and tot("a10_flags") > 0 and tot("mid_window_ciks") > 0 and tot("gaap") > 0, (c, {k: tot(k) for k in ("scored", "straddle", "stale", "fallback_to_gaap", "f_alone", "a10_flags", "mid_window_ciks", "gaap")})
        assert max(r_["cells"][c]["reasons"]["foreign_filer"] for r_ in srows) == 1 and min(r_["cells"][c]["reasons"]["not_in_map"] for r_ in srows) >= 1 and sum(r_["cells"][c]["reasons"]["value_not_positive"] for r_ in srows) >= 1, c
    rvs = ix.index("RVS")
    sp_ = score_rank(W, by_month["2024-05"])["N12"]
    assert sp_.scored[spl] and sp_.straddle[spl] and abs(sp_.fa[spl] - 1.0) < 1e-4 and abs(sp_.fap[spl] - 2.0) < 1e-4 and abs(sp_.iss[spl]) < 0.4 and not sp_.f_alone[spl], \
        ("SPL's 2-for-1 cancels through F (the factor is raw / adjusted: 2 before the split, 1 after): the ISS is the organic one, not ln 2 / ln 4", sp_.iss[spl], sp_.fa[spl], sp_.fap[spl])
    early = [score_rank(W, r_)["N12"] for r_, _f, _x in ranks if "2016-12" <= f"{W.days[r_]:%Y-%m}" <= "2017-03"]
    assert any(s_.scored[rvs] and s_.straddle[rvs] and s_.f_alone[rvs] and abs(s_.fap[rvs] - 0.2) < 1e-4 and abs(s_.fa[rvs] - 1.0) < 1e-4 and abs(s_.iss[rvs]) < 0.4 for s_ in early), \
        "RVS's 1-for-5 reverse split (before the calendar starts: F alone stands) cancels through F as well"
    a10 = a10_rows(W, ranks, ni_build(W, WF0, PRE_END, JUDGED, units=False, counts_only=True))                   # a counts-only leg has no picks: every row's `picked` is blank here
    assert any(r_["symbol"] == "S12" and r_["cell"] == "N12" for r_ in a10) and not any(r_["picked"] for r_ in a10) and all(abs(r_["iss"]) > LN15 and r_["symbol"] not in ("S11", "S02") for r_ in a10), "[A10] lists the real issuance jump (S12), never a name that is not scored"
    n_a10 = len({(r_["symbol"], r_["date"]) for r_ in a10})
    print(f"planted cases ok through the real loaders (the cut at read, S18 / S20 / SPL / RVS / S23 / DLST, the pinned files as ONE table and ONE map); against the plain-python recount: the score of every name at {len(chosen)} ranks x 2 cells ({n_score:,} scores, {time.time() - t0:.0f}s), "
          f"the planted filing cases (foreign filer, x100 scale error, zero, ambiguous day, amendments, 100-day filer, Saturday filer, late starts), {n_a10} [A10] flagged name-months")
    return srows, ranks, cik_of


def smoke(*a):
    """python r21_netiss.py smoke DIR [stage_b]: offline, on SYNTHETIC worlds (nothing real is read or written; DIR is wiped and its name must contain 'smoke'). Order: the selftest on the real constants; the planted world through the real loaders against plain-python recounts of everything this file
    adds (every score at 18 ranks, then every pool, pick, decile and daily path over 15 rebalances in both readings); the dryload (counts only); Stage A's refusal paths (every pinned file: another sha, absent, overlapping, a row of the sealed year); Stage A on the NULL world (must FAIL: the same share
    counts and the same random numbers, no issuance effect) and on the PLANTED world (the effect must be found: (a)-(e) pass, (f) awaits the hand audit; the score block prints before any P&L); the hand audit (keep / data_event) and the recomputation; Stage B's refusal paths (the lead's go-flag, the
    pinned lockbox extract, stale stamps, drifted inputs); with the argument stage_b also the one read of Stage B on the synthetic lockbox days, the verdict = the leg's veto alone, a second read refused, Stage A frozen"""
    root = os.path.abspath(a[0] if a else os.path.join(tempfile.gettempdir(), "netiss_smoke"))
    with_b = "stage_b" in a[1:]
    why = smoke_refusal(root)
    if why:
        raise SystemExit(why)
    selftest()                                                                             # the hand-made checks first, on the real constants (before anything below is patched)
    t_start = time.time()
    dates_of = lambda txt: re.findall(r"\b20\d\d-\d\d-\d\d\b", txt)
    with smoke_env(root) as env:
        sa_path, go, rd = os.path.join(OUT, "netiss_stageA.json"), os.path.join(OUT, GO_FLAG), os.path.join(OUT, READ_FLAG)
        n_rows, n_names = len(env.xb.rows_all), len(env.fk["plant"].names)
        print(f"synthetic market: {n_names} names x {len(env.days):,} business days ({env.days[0]:%Y-%m-%d} .. {env.days[-1]:%Y-%m-%d}); share counts: quarterly cover-page and balance-sheet filings of every name from a persistent annual rate in -10% .. +18% and a yearly noise of 3% "
              f"({n_rows:,} filing rows, {len(env.xb.rows_cut):,} filed before the cut, the rest in the sealed year), foreign / zero / x100 / ambiguous / amended / 100-day / Saturday / late-start / split cases planted; the PLANTED world drifts every name by -{SMOKE_THETA:g} x its issuance rate a year, the NULL "
              f"world does not; both through r5_siporb's own pulls ({env.build_seconds:.0f}s); the wide calendar {env.rows_in_calendar:,} rows; SPEC shrunk to {SMOKE_SPEC}")
        # ---- 1. the planted world through the REAL loaders: the cut, the planted cases and every pipeline step against plain-python recounts
        W, cal, winfo, tbis = smoke_world(env, "plant")
        assert len(tbis) == 4 and len(D15.load_tbis(S.END)) == 5, "TBIS's row on the lockbox day is cut at read time"
        assert np.isnan(W.es.ret[W.days.get_loc(TS("2024-03-05"))]) and np.isnan(W.es.ret[W.days.get_loc(TS("2024-03-06"))]), "the ES master has no print on 2024-03-05: no return that session and the next"
        mp = load_map()
        frame, finfo = load_facts(S.LB0)
        fx = build_facts(frame)
        ni = attach_netiss(W, fx, mp, cal)
        srows, ranks, cik_of = smoke_plant_checks(W, ni, mp, frame, finfo, fx, cal, env)
        ix = list(W.syms)
        lo_, hi_ = TS("2023-06-01"), TS("2024-08-31")
        t0 = time.time()
        Bz_r, Bz_k, Bz_j = brute_ni(W, frame, cal, cik_of, lo_, hi_, "remove"), brute_ni(W, frame, cal, cik_of, lo_, hi_, "naive"), brute_ni(W, frame, cal, cik_of, lo_, hi_, JUDGED)
        Lr, Lk, Lj = ni_build(W, lo_, hi_, "remove"), ni_build(W, lo_, hi_, "naive"), ni_build(W, lo_, hi_, JUDGED)
        n_paths = compare_ni(W, Lr, Bz_r, "smoke remove") + compare_ni(W, Lk, Bz_k, "smoke naive") + compare_ni(W, Lj, Bz_j, "smoke keep")
        series_check_ni(W, Lr, Bz_r)
        j1_, j2_ = ix.index(SMOKE_DUAL[0]), ix.index(SMOKE_DUAL[1])                         # [A13] the one pair of share classes of the synthetic market: the second reads the first's CIK, so the same two facts
        n_dual = Counter()
        for r_ in Lr.recs:
            for c in CELLS:
                cc_ = r_.cell[c]
                assert not {j1_, j2_} <= set(r_.pool[cc_.idx].tolist()), (c, W.days[r_.r], "one class of a firm is scored, never both")
                assert set(cc_.second.tolist()) <= {j1_, j2_}, f"{SMOKE_DUAL[0]} / {SMOKE_DUAL[1]} are the only two names that share a CIK"
                n_dual[c] += int(len(cc_.second))
        assert all(n_dual[c] >= 5 for c in CELLS), n_dual
        ntr = {c: sum(r_.cell[c].traded for r_ in Lr.recs) for c in CELLS}
        modes = {c: Counter(r_.cell[c].mode for r_ in Lr.recs) for c in CELLS}
        assert len(Lr.recs) == len(Bz_r) >= 12 and all(ntr[c] >= 10 for c in CELLS) and all(r_.cell[c].n >= 30 for r_ in Lr.recs for c in CELLS) and sum(modes[c].get("top", 0) for c in CELLS) >= 8, (ntr, modes)
        flagged = [(ix.index(nm), W.days.get_loc(TS(s_))) for nm, s_ in (("SPL", "2024-03-15"), ("S18", "2024-04-22"), ("S23", "2024-05-14"))]
        n_hold = n_pre = 0
        for rr_, kk_ in zip(Lr.recs, Lk.recs):                                             # the registered reading removes a name flagged inside the hold, the look-ahead reading keeps it on its naive raw path; a flag in the pre-window removes it from both
            assert rr_.r == kk_.r
            lo_pre = rr_.r - M17.SPEC["skip"] - M17.SPEC["hyg_lead"] + 1
            for j, d_ in flagged:
                if rr_.r + 1 <= d_ <= rr_.x:
                    assert j not in rr_.pool.tolist(), (ix[j], W.days[rr_.r])
                    if j in kk_.pool.tolist():
                        assert kk_.naive[kk_.pool.tolist().index(j)], (ix[j], W.days[kk_.r], "kept at its naive raw path")
                        n_hold += 1
                if lo_pre <= d_ <= rr_.r:
                    assert j not in rr_.pool.tolist() and j not in kk_.pool.tolist(), (ix[j], W.days[rr_.r], "a flag in the pre-window removes the name in both readings")
                    n_pre += 1
        assert n_hold >= 2 and n_pre >= 2, (n_hold, n_pre)
        print(f"  {len(Bz_r)} rebalances ({lo_:%Y-%m-%d} .. {hi_:%Y-%m-%d}) in both readings against the recount ({time.time() - t0:.0f}s): every pool, ISS, composite twin, mode, pick, decile, first-reason count and {n_paths:,} pick paths; rebalances trading the top 15 / the third / nothing: "
              + "; ".join(f"{c} {modes[c].get('top', 0)} / {modes[c].get('third', 0)} / {modes[c].get('none', 0)}" for c in CELLS))
        print(f"  [A13] the synthetic market's one pair of share classes ({SMOKE_DUAL[0]} / {SMOKE_DUAL[1]} read one CIK): {n_dual['N12']} / {n_dual['N24']} second-class name-ranks taken out of the scored names (N12 / N24) - one class scored at every rank, each decision against the recount")
        lo2, hi2 = TS("2016-11-01"), TS("2017-04-30")                                      # the first rebalances: 2, 11, 13, 35, 56 and 67 scored names - the 'nothing', 'third' and 'top 15' modes of the fallback rule, N24 with nothing scored yet
        Bz_e, Le = brute_ni(W, frame, cal, cik_of, lo2, hi2, "remove"), ni_build(W, lo2, hi2, "remove")
        n_early = compare_ni(W, Le, Bz_e, "smoke early")
        series_check_ni(W, Le, Bz_e)
        modes_e = {c: Counter(r_.cell[c].mode for r_ in Le.recs) for c in CELLS}
        assert len(Le.recs) == len(Bz_e) >= 5 and modes_e["N12"].get("none", 0) >= 1 and modes_e["N12"].get("third", 0) >= 1 and modes_e["N12"].get("top", 0) >= 1 and modes_e["N24"].get("none", 0) >= 1, modes_e
        print(f"  the first {len(Bz_e)} rebalances ({lo2:%Y-%m-%d} .. {hi2:%Y-%m-%d}) against the recount too ({n_early:,} pick paths): the sides by the fallback rule - top 15 / third / nothing: "
              + "; ".join(f"{c} {modes_e[c].get('top', 0)} / {modes_e[c].get('third', 0)} / {modes_e[c].get('none', 0)}" for c in CELLS))
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
        fb = io.StringIO()
        with contextlib.redirect_stdout(fb):
            print_data_counts(mp, finfo, fx, W)
        assert fb.getvalue() in td, "the dryload's file / map / entry counts are the full computation's"
        Lc = ni_build(W, WF0, PRE_END, JUDGED, units=False, counts_only=True)
        fc = io.StringIO()
        with contextlib.redirect_stdout(fc):
            print_scored_stats(LAB_J, Lc, W)
        assert fc.getvalue() in td, "the dryload's scored-names-per-rebalance lines are the recount's"
        f2 = io.StringIO()
        with contextlib.redirect_stdout(f2):
            print_second_classes(second_class_summary(Lc, W))
        assert f2.getvalue() in td and "the 1 CIKs it fires on" in td and f"    {smoke_cik(SMOKE_DUAL[0])}: {SMOKE_DUAL[0]} " in td and f"; {SMOKE_DUAL[1]} " in td, "the dryload's [A13] block is the recount's: the second share classes per rank, by year, and the CIK they fire on"
        fr_ = io.StringIO()
        with contextlib.redirect_stdout(fr_):
            print_score_report(score_report(W, ranks, values=False), ni.cal_start, names=False)
        assert fr_.getvalue() in td and "scored name-ranks" in td, "the dryload's score block is the report without a value or a name"
        assert td.count("[A3] a calendar split the cache's factor F does not show: ") == 2, "[A3]'s two lists are counted for both cells"
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), patched(M17, WIDE_CA_SHA="0" * 64):
            dryload()
        assert "DIFFERS from the registered one" in buf.getvalue(), "the dryload reports an unregistered calendar (and counts on it)"
        dryload_text_checks(buf.getvalue())
        print("dryload ok on the synthetic world: counts only (no share count, ISS value, price, return, P&L or statistic, no signed three-decimal number), no lockbox date, nothing written, its file / map / score / scored-names lines equal the full computation's")
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
        for key in FILES:                                                                  # every pinned file: another sha refuses, an absent file refuses
            must("is not the registered", FILE_SHA={**FILE_SHA, key: "0" * 64})
            must("is not on file", FILES={**FILES, key: os.path.join(root, "xbrl", "absent.csv")})
        xd = os.path.join(root, "xbrl_bad")
        os.makedirs(xd)

        def pinned_copy(key, name, extra=None, drop_last=0):
            """a copy of one pinned file in xbrl_bad with extra lines appended (and the last lines dropped), registered under its own sha for the block"""
            lines = open(env.xb.files[key], newline="").read().split("\n")
            lines = [l_ for l_ in lines if l_ != ""]
            lines = lines[:len(lines) - drop_last] + list(extra or [])
            p = os.path.join(xd, name)
            with open(p, "w", newline="\n") as f_:
                f_.write("\n".join(lines) + "\n")
            return p, M17.sha_raw(p)
        cik1 = smoke_cik("S01")
        p1, s1 = pinned_copy("map_add", "map_add_overlap.csv", ["S01," + cik1 + ",reviewed_same_firm,S01 Inc"])
        must("usable row in BOTH", FILES={**FILES, "map_add": p1}, FILE_SHA={**FILE_SHA, "map_add": s1})
        p2, s2 = pinned_copy("map_add", "map_add_dup.csv", ["D37," + smoke_cik("D37") + ",reviewed_same_firm,D37 Inc"])
        must("more than once", FILES={**FILES, "map_add": p2}, FILE_SHA={**FILE_SHA, "map_add": s2})
        hdr_n = len(FACT_HDR)
        base_line = open(env.xb.files["facts"], newline="").read().split("\n")[1]
        p3, s3 = pinned_copy("facts_add", "facts_add_overlap.csv", [base_line])
        must("in BOTH the pinned flat file", FILES={**FILES, "facts_add": p3}, FILE_SHA={**FILE_SHA, "facts_add": s3})
        cells_ = base_line.split(",")
        late_line = ",".join(cells_[:FACT_HDR.index("filed")] + ["2025-07-02"] + cells_[FACT_HDR.index("filed") + 1:])
        assert len(cells_) == hdr_n
        p4, s4 = pinned_copy("facts", "facts_late.csv", [late_line])
        must("filed on / after the cut", FILES={**FILES, "facts": p4}, FILE_SHA={**FILE_SHA, "facts": s4})
        p5, s5 = pinned_copy("map", "map_nocol.csv")
        lines5 = open(p5).read().replace("symbol,cik,method,name", "symbol,cik,how,name", 1)
        open(p5, "w", newline="\n").write(lines5)
        must("lacks the column", FILES={**FILES, "map": p5}, FILE_SHA={**FILE_SHA, "map": M17.sha_raw(p5)})
        must("do not reproduce", CHECK_BOOK=True)
        with patched(DV, REF_SHA="0" * 64):
            must("RESMOM line file")
        with patched(DV, REF_CSV=os.path.join(root, "resmom", "absent.csv")):
            must("is not on file - the REFERENCE book")
        print("Stage A refuses (and writes nothing) on: a changed pre-registration, an unregistered wide calendar, every pinned file with another sha or absent, a map symbol with a usable row in both files, a symbol twice in one file, a fact row in both flat files, a row filed on / after the cut, "
              "a map without its columns, a book that does not reproduce #463, a RESMOM line file that is absent / not the registered one")

        def run_stage_a(world):
            env.switch(world)
            b_ = io.StringIO()
            with contextlib.redirect_stdout(b_):
                o_ = stage_a()
            return o_, b_.getvalue()
        # ---- 4. Stage A on the NULL world: the same share counts and random numbers without the issuance effect must FAIL
        t0 = time.time()
        out_n, txt_n = run_stage_a("null")
        cells_n = out_n["stageA"]["cells"]
        assert out_n["judged"] is True and out_n["stageA"]["pass_cells"] == [] and out_n["candidate"] is None and out_n["stageA"]["null"]["draws"] == NREP == 100, (out_n["stageA"]["pass_cells"], out_n["candidate"])
        assert "NETISS Stage A: FAIL - no cell passes (a)-(e)" in txt_n and "Stage A (a)-(e) pass" not in txt_n and all(d < "2025-06-30" for d in dates_of(txt_n)), "the null world fails and prints no lockbox date"
        assert all(not c["PASS"] for c in cells_n.values()) and not any(c["A2"]["incremental_credit"] for c in cells_n.values()), {k: c["base"]["roc"] for k, c in cells_n.items()}
        dn = {c: [q["net"] for q in cells_n[c]["deciles"]["deciles"]] for c in CELLS}
        sn = {c: float(np.corrcoef(np.arange(10), dn[c])[0, 1]) for c in CELLS}
        os.remove(sa_path)
        print(f"Stage A on the NULL world ({time.time() - t0:.0f}s): FAIL as it must - WF ROC@30k " + ", ".join(f"{c} {cells_n[c]['base']['roc']:.1f}" for c in CELLS) + f"; null p95 {out_n['stageA']['null']['roc_max']['p95']:.1f}; decile nets against the decile number (rank correlation of the net with the decile) "
              + ", ".join(f"{c} {sn[c]:+.2f}" for c in CELLS))
        refused(stage_b, "go-flag")
        assert not os.path.exists(rd)
        # ---- 5. Stage A on the PLANTED world: the effect must be found - (a)-(e) pass, (f) awaits the hand audit
        t0 = time.time()
        out, txt = run_stage_a("plant")
        cells = out["stageA"]["cells"]
        passing, cand = stage_a_flow(cells)
        assert out["judged"] is True and out["stageA"]["pass_cells"] == passing and len(passing) >= 1 and out["candidate"]["cell"] == cand and out["pending_hand_audit"] == passing, (passing, cand, {c: (cells[c]["base"]["roc"], [k for k, v in cells[c]["checks"].items() if not v]) for c in CELLS})
        assert cand == max(passing, key=lambda c: (cells[c]["base"]["roc"], -CELLS.index(c))) and out["candidate"]["also_passes"] == [c for c in passing if c != cand]
        for c in passing:
            assert f"Stage A (a)-(e) pass, (f) awaits the hand audit - cell {c}" in txt and all(cells[c]["checks"].values()), c
        assert "(f) AWAITS THE HAND AUDIT" in txt and "NETISS Stage A: (a)-(e) pass" in txt and "audit complete" not in txt.lower() and all(d < "2025-06-30" for d in dates_of(txt)), "the harness never decides (f); no lockbox date"
        assert out["prereg_sha256_lf"] == PREREG_SHA and {k: out.get(k) for k in stamp()} == stamp() and out["manifest_sha256"] == D15.MANIFEST_PREFIX + "0" * 56 and out["stageA"]["null"]["draws"] == NREP
        # the score block prints BEFORE any cell's P&L, in the prereg's order
        order = ("BEFORE ANY P&L - the share-count score", "coverage: the first rank with any scored name", "per rank (rank date: universe / scored", "names lost to each rule, by rank", "excluded at |ISS| > ln(10) and LISTED", "ISS per fill year", "over every rank:", "[A3] a calendar split the cache's factor F does not show",
                 "[A11] unscored ADRs / IFRS filers (20-F / 40-F / 6-K only) per rank", "CIKs whose first share fact starts inside the window", "[A4] names with no score whatever the horizon, LISTED by name", "[A13] ONE SHARE CLASS PER FIRM", "the weighted-average concept as a cross-check only", "judged reading [A18] done")
        seq = [txt.index(s_) for s_ in order]
        i_pl = txt.index("the JUDGED reading [A18] (a name flagged inside the hold stays")          # the first line that carries a cell's P&L
        assert seq == sorted(seq) and seq[-1] < i_pl and txt.index("REFERENCE book [X1]") < seq[0], ("the score block is out of the prereg's order", seq)
        outcome = re.search(r"[$]\s*-?\d|ROC|Sortino|net [$]|drawdown", txt[seq[0]:i_pl])
        assert not outcome, ("a P&L figure was printed before the registered reading's table", txt[max(seq[0] + outcome.start() - 80, 0):seq[0] + outcome.end() + 80])
        a4 = txt[txt.index("[A4] names with no score whatever the horizon, LISTED by name"):txt.index("the weighted-average concept as a cross-check only")]
        for frag in ("S02 x", "S03 x", "S04 x", "S05 x", "S06 x", "S07 x", "S08 x", "foreign filer", "symbol not in the map", "CIK with no share fact"):
            assert frag in a4, ("[A4]'s list of names", frag)
        assert out["unscored_by_name"]["foreign_filer"].keys() == {"S02"} and out["unscored_by_name"]["not_in_map"].keys() == {"S03"} and out["unscored_by_name"]["no_facts_for_cik"].keys() == {"S08"}, out["unscored_by_name"]
        sc2 = out["second_share_class"]                                                    # [A13] the one pair of share classes of the synthetic market, counted before any P&L
        assert list(sc2["ciks"]) == [smoke_cik(SMOKE_DUAL[0])] and set(sc2["ciks"][smoke_cik(SMOKE_DUAL[0])]) == set(SMOKE_DUAL) and all(sc2["total"][c] >= 20 for c in CELLS) and sc2["nan_dv"] == {"N12": 0, "N24": 0} and len(sc2["ranks"]) == len(ranks), (sc2["total"], list(sc2["ciks"]))
        a13 = txt[txt.index("[A13] ONE SHARE CLASS PER FIRM"):txt.index("the weighted-average concept as a cross-check only")]
        assert all(f"    {r_['rank']}: " in a13 for r_ in sc2["ranks"]) and f"    {smoke_cik(SMOKE_DUAL[0])}: {SMOKE_DUAL[0]} " in a13 and not re.search(r"[$]\s*-?\d|ROC|Sortino|net [$]|drawdown", a13), "the [A13] block lists every rank and the CIK before any P&L, counts only"
        assert {c: sum(v.get(f"ns_{c}_second_share_class", 0) for v in out["hygiene_counts_by_year"]["judged"].values()) for c in CELLS} == sc2["total"], "the full leg's by-year counts are the pre-P&L block's"
        lst10 = txt[txt.index("excluded at |ISS| > ln(10) and LISTED"):].split("\n")[0]
        assert "S11" in lst10 and "name-ranks on" in lst10, "the x100 scale error is LISTED by name before any P&L"
        i_a3 = txt[txt.index("[A3] a calendar split the cache's factor F does not show"):].split("\n")[0]
        assert "S18" in i_a3 and "S20" in i_a3, "[A3]'s two lists name S18 (the calendar's split) and S20 (the factor's)"
        # the effect: the planted world's deciles fall from the biggest shrinkers to the biggest issuers, the null world's do not
        dp = {c: [q["net"] for q in cells[c]["deciles"]["deciles"]] for c in CELLS}
        sp = {c: float(np.corrcoef(np.arange(10), dp[c])[0, 1]) for c in CELLS}
        assert all(sp[c] < -0.7 and dp[c][0] > dp[c][9] for c in CELLS) and all(len(cells[c]["deciles"]["deciles"]) == 10 and cells[c]["deciles"]["ranks_cut"] > 50 for c in CELLS), (sp, sn)
        print(f"Stage A on the PLANTED world ({time.time() - t0:.0f}s): the effect is found - deciles fall from the biggest shrinkers to the biggest issuers (rank correlation of the net with the decile "
              + ", ".join(f"{c} {sp[c]:+.2f}" for c in CELLS) + f", the null world {sn['N12']:+.2f} / {sn['N24']:+.2f}); " + ", ".join(f"{c} ROC@30k {cells[c]['base']['roc']:.0f} (${cells[c]['usd_year']:,.0f} a year, {cells[c]['base']['n_pos']:,} positions, {cells[c]['base']['n_units']} rebalances)" for c in CELLS)
              + f"; (a)-(e) pass for {passing}, candidate {cand}, (f) awaits the hand audit")
        # every cell's WF numbers recomputed from fresh legs, the stress rows, the cost curve, the dollars a year, A2 over the reference, the beta rule, the twins
        Lw = ni_build(W, WF0, PRE_END, JUDGED)
        ref_ = DV.ref_load(B, check_facts=False)
        for cell in CELLS:
            run_ = M17.run_cell(W, cell_leg(Lw, cell), D15.l1_cfg(), pos=True)
            st, xb_, _cb = stat_run(B, rowsB, run_)
            got = cells[cell]["base"]
            assert st["n_pos"] == got["n_pos"] == out["parity"][cell]["n_pos"] and abs(st["net"] - got["net"]) < 1e-6 and abs(st["roc"] - got["roc"]) < 1e-9 and abs(st["max_dd"] - got["max_dd"]) < 1e-9, cell
            assert abs(cells[cell]["usd_year"] - got["net"] / got["years"]) < 1e-6 and got["years"] > 8.0, "[A12] dollars a year beside the ROC"
            for b_, got_ in ((0.0, cells[cell]["cost0"]), (10.0, cells[cell]["stress"]["10 bps"]), (20.0, cells[cell]["stress"]["20 bps"])):
                want_ = stat_run(B, rowsB, M17.run_cell(W, cell_leg(Lw, cell), D15.l1_cfg(bps=b_)))[0]
                assert abs(got_["net"] - want_["net"]) < 1e-6 and abs(got_["roc"] - want_["roc"]) < 1e-9, (cell, b_)
            assert cells[cell]["cost0"]["net"] > got["net"] > cells[cell]["stress"]["10 bps"]["net"] > cells[cell]["stress"]["20 bps"]["net"]
            mw = B.mask(*A2_WINS[cell])
            sb_, sc_ = float(np.std(B.raw[mw], ddof=1)), float(np.std(xb_[mw], ddof=1))
            a2 = cells[cell]["A2"]
            assert a2["window"] == [f"{A2_WINS[cell][0]:%Y-%m-%d}", f"{A2_WINS[cell][1]:%Y-%m-%d}"] and a2["rows"] == int(mw.sum()) and abs(a2["c"] - A2_TARGET * sb_ / sc_) <= 1e-9 * a2["c"], (cell, a2["window"], a2["rows"], int(mw.sum()))
            assert a2["incremental_pass"] is bool(a2["roc"] > a2["reference"]["roc"] and a2["sortino"] > a2["reference"]["sortino"]) and a2["incremental_credit"] is bool(a2["incremental_pass"] and cells[cell]["beta"]["within_cap"]) and a2["credited"] is cells[cell]["beta"]["within_cap"], cell
            yrs = float(ref_.stats["years"])
            assert abs(a2["usd_year"] - a2["net"] / yrs) < 1e-6 and abs(a2["reference"]["usd_year"] - a2["reference"]["net"] / yrs) < 1e-6 and abs(a2["at_half_c"]["usd_year"] - a2["at_half_c"]["net"] / yrs) < 1e-6 and abs(a2["at_double_c"]["usd_year"] - a2["at_double_c"]["net"] / yrs) < 1e-6 \
                and abs(a2["plain_463"]["usd_year"] - a2["plain_463"]["net"] / yrs) < 1e-6, "[A12] the dollars a year beside every ROC of A2"
            bt = cells[cell]["beta"]
            assert bt["side_notional"] == M17.SPEC["n_side"] * M17.SPEC["slot"] and bt["cap"] == BETA_CAP and bt["within_cap"] is bool(abs(bt["beta_dd_days"]) <= BETA_CAP and abs(bt["beta_all_days"]) <= BETA_CAP), bt
            g70 = cells[cell]["gate70"]
            assert g70["credited"] is bt["within_cap"] and abs(sum(cells[cell]["episode_pnl"]) - sum(e_["cell_pnl"] for e_ in out["reports"]["ref_episodes"][cell])) < 1e-6 and len(out["reports"]["ref_episodes"][cell]) == ref_.structure["episodes"], "[A12] the reference's episode table"
        assert out["reference"]["sha256"] == env.ref_sha == out["reference"]["pinned_sha256"] and out["reference"]["rows"] == ref_.n_rows and "REFERENCE book [X1]" in txt and "DIAGNOSTICS [X2]" in txt and "ISS DECILES [A5]" in txt and "TWINS - REPORTED" in txt and "#70 gate basis [X1]" in txt, "the reference and the reports"
        for frag in ("COST CURVE", "BY JULY-JUNE YEAR", "THE TWO REGIME HALVES", "THE REFERENCE BOOK'S DRAWDOWN EPISODES [A12]", "THE LONG AND SHORT SIDES APART", "realised beta to ES", "persistence:", "pick overlap over", "concept used (cover page / balance sheet", "short leg [R2]", "survivorship:", "a year)"):
            assert frag in txt, frag
        ca2 = cells[cand]["A2"]
        assert out["candidate"] == {"cell": cand, "c": ca2["c"], "std_book": ca2["std_book"], "std_cell": ca2["std_cell"], "window": ca2["window"], "a2_book_roc": ca2["roc"], "a2_reference_roc": ca2["reference"]["roc"], "incremental_pass": ca2["incremental_pass"],
                                    "incremental_credit": ca2["incremental_credit"], "book_shadow_line": ca2["incremental_credit"], "beta_within_cap": cells[cand]["beta"]["within_cap"], "also_passes": out["candidate"]["also_passes"]} and ca2["c"] > 0, "the frozen size travels with its two stds and the window"
        for key in ("sides", "extra", "sub", "gate70", "seat_ref", "episode_pnl", "deciles", "composite", "hedged", "beta", "years_held"):
            assert all(key in cells[c] for c in CELLS), key
        # the twins: the composite twin has its own picks and numbers, the hedged twin its own ratios (zero before 252 sessions of the cell's own P&L)
        for c in CELLS:
            cp, hg = cells[c]["composite"], cells[c]["hedged"]
            assert cp["base"]["n_pos"] > 0 and 0.0 < cp["pick_overlap_with_iss_picks"]["long"] <= 1.0 and 0.0 < cp["pick_overlap_with_iss_picks"]["short"] <= 1.0, (c, cp["pick_overlap_with_iss_picks"])
            assert hg["ratios"] == cells[c]["base"]["n_units"] and 0 < hg["ratios_nonzero"] < hg["ratios"] and abs(hg["usd_year"] - hg["base"]["net"] / hg["base"]["years"]) < 1e-6 and np.isfinite(hg["beta"]["beta_all_days"]), (c, hg["ratios"], hg["ratios_nonzero"])
        rp = out["reports"]
        for c in CELLS:
            t_ = rp["turnover"][c]
            assert t_["transitions"] > 50 and 0.0 < t_["persistence_mean"] < 1.0 and abs(t_["persistence_mean"] - (t_["persistence_long_mean"] + t_["persistence_short_mean"]) / 2) < 1e-9 and rp["pick_overlap_with_res"][c]["rebalances"] > 50, (c, t_)
            assert len(rp["concept_by_rank"][c]) == len(out["score_by_rank"]) == len(ranks) and rp["top20_gains"][c] and len(rp["top20_gains"][c]) == 20 and np.isfinite(rp["corr_with_res"][c]), c
        wa = out["weighted_average_cross_check"]
        assert wa and max(v["n"] for v in wa.values()) >= 20, "the weighted-average concept is a reported cross-check"
        # [A18] the hygiene readings: the judged reading keeps the planted in-hold flags on the split-safe path (only an announced split / a [D2] ex-date removes a name), the leaky 'remove' reading removed them; both are in the file, the leaky one without a null
        hj, hl = out["hygiene_counts_by_year"]["judged"], out["hygiene_counts_by_year"]["leaky_remove"]
        assert sum(v.get("post_split", 0) + v.get("post_gap", 0) + v.get("post_jump", 0) for v in hl.values()) >= 2 and sum(v.get("post_split", 0) + v.get("post_gap", 0) + v.get("post_jump", 0) for v in hj.values()) == 0 and sum(v.get("kept_flagged", 0) for v in hj.values()) >= 1, (hj.get(2024), hl.get(2024))
        assert out["judged_post_mode"] == "keep" and out["leaky_remove_reading"]["null"] is None and set(out["leaky_remove_reading"]["cells"]) == set(CELLS) and out["no_dividend_reading"]["null"]["draws"] == NREP
        assert all(c_["base"]["net"] != cells[c]["base"]["net"] for c, c_ in out["no_dividend_reading"]["cells"].items()), "the cash dividends move the P&L"
        cd = pd.read_csv(os.path.join(OUT, "netiss_audit_candidates.csv"))
        a10f = pd.read_csv(os.path.join(OUT, "netiss_a10_flags.csv"))
        assert {"symbol", "date", "exit", "side", "pnl", "cell", "rank_date", "cik", "concept", "iss", "shares_now", "shares_prior", "asof_now", "asof_prior", "first_filed_now", "first_filed_prior", "accn_now", "accn_prior", "form_now", "form_prior", "F_now", "F_prior", "asset_status", "group"} <= set(cd.columns), list(cd.columns)
        assert {"cell", "symbol", "date", "picked", "rank_date", "iss", "shares_now", "shares_prior", "F_now", "F_prior", "accn_now", "accn_prior", "group"} <= set(a10f.columns) and len(a10f) == out["a10_flags"] > 0 and (a10f["iss"].abs() > LN15).all(), list(a10f.columns)
        assert set(cd["cell"]) == set(CELLS) and cd.groupby("cell").size().max() == AUDIT_N and cd["exit"].max() < "2025-06-30" and a10f["date"].max() < "2025-06-30" and cd["rank_date"].max() < "2025-06-30"
        # [A14] netiss_a10_flags.csv keeps ALL flagged name-ranks and says which are PICKED (cell / side, either cell) and which group each is in: the registered leg's picks recounted
        a10f["picked"] = a10f["picked"].fillna("")
        assert (cd["group"].str.split("|").str.len() == 3).all() and (a10f["group"].str.split("|").str.len() == 3).all() and (a10f["group"] == a10f["symbol"] + "|" + a10f["accn_now"] + "|" + a10f["accn_prior"]).all() and (cd["group"] == cd["symbol"] + "|" + cd["accn_now"] + "|" + cd["accn_prior"]).all()
        pkw, ixw = picks_by_name_month(Lw), {n_: i_ for i_, n_ in enumerate(W.syms)}
        assert all(r_["picked"] == ", ".join(pkw.get((W.days.get_loc(TS(r_["date"])), ixw[r_["symbol"]]), [])) for r_ in a10f.to_dict("records")), "every flagged name-rank's picked column is the registered leg's picks of that name-month"
        assert int((a10f["picked"] != "").sum()) == out["a10_picked_flags"] > 0 and a10f.loc[a10f["picked"] != "", "group"].nunique() == out["a10_picked_groups"] > 0 and int((a10f["picked"] == "").sum()) == len(a10f) - out["a10_picked_flags"], "every flagged name-rank is listed, the picked ones named (in the synthetic market every flagged name is an extreme one and so picked; the toy world of the selftest has unpicked ones)"
        assert a10f.loc[a10f["picked"] != "", "group"].nunique() < int((a10f["picked"] != "").sum()), "groups: fewer checks than picked name-ranks (a name stays on the same two filings for months)"
        for cell, g in cd.groupby("cell"):
            assert (g["pnl"].diff().dropna() <= 1e-9).all() and abs(g["pnl"].iloc[0] - float(M17.run_cell(W, cell_leg(Lw, cell), D15.l1_cfg(), pos=True).pos.pnl.max())) < 1e-6, "largest gains first; the first is the cell's largest"
            assert (g["shares_now"] > 0).all() and (g["shares_prior"] > 0).all() and (g["asof_prior"] < g["asof_now"]).all() and (g["first_filed_now"] > g["asof_now"]).all(), "every contributor carries its two share facts, their dates and filings"
        pm = peak_mb()
        print(f"audit candidates: the {AUDIT_N} largest gains per cell with the two share facts, their filings and F -> netiss_audit_candidates.csv; every [A10] flagged name-rank ({len(a10f)}) -> netiss_a10_flags.csv" + (f"; peak memory {pm:,.0f} MB" if pm else ""))
        # ---- 6. the hand audit: every listed contributor and [A10] flag 'keep' -> the same numbers, the audit counted; a data_event on the candidate's largest gain -> out of both cells and the nulls
        ap = os.path.join(OUT, "netiss_audit.csv")
        one_per_group = a10f[a10f["picked"] != ""].drop_duplicates("group")                 # [A14] ONE row per picked group (one member of it), not one per flagged name-rank
        keys = pd.concat([cd[["symbol", "date", "cell"]], one_per_group[["symbol", "date", "cell"]]]).drop_duplicates().reset_index(drop=True)
        assert len(keys) < len(cd) + int((a10f["picked"] != "").sum()), "grouping saves rows"
        keys.assign(verdict="keep", note="smoke: nothing found").to_csv(ap, index=False)
        out2, txt2 = run_stage_a("plant")
        assert out2["audit"]["rows"] == len(keys) and out2["audit"]["keep"] == len(keys) and out2["audit"]["data_event"] == 0 and out2["audit"]["group_name_months"] == 0 and out2["audit_sha256"] == file_sha(ap) != out["audit_sha256"], out2["audit"]
        assert all(v["audited"] == v["listed"] == AUDIT_N and v["a10_audited"] == v["a10_listed"] > 0 and v["audit_complete"] and v["a10_complete"] and v["a10_picked"] > v["a10_listed"] for v in out2["audit_status"].values()), out2["audit_status"]
        assert all(v["a10_flagged"] >= v["a10_picked"] for v in out2["audit_status"].values()) and sum(v["a10_flagged"] for v in out2["audit_status"].values()) == len(a10f)
        assert out2["stageA"]["pass_cells"] == passing and out2["candidate"] == out["candidate"] and all(out2["stageA"]["cells"][c]["base"][k] == cells[c]["base"][k] for c in CELLS for k in ("n_pos", "net", "roc", "max_dd", "sortino")), "a keep changes no number"
        top = cd[cd["cell"] == cand].iloc[0]
        au = pd.read_csv(ap)
        au.loc[(au["symbol"] == top["symbol"]) & (au["date"] == top["date"]), "verdict"] = "data_event"
        au.to_csv(ap, index=False)
        out3, txt3 = run_stage_a("plant")
        cd3 = pd.read_csv(os.path.join(OUT, "netiss_audit_candidates.csv"))
        jtop, ftop = ix.index(top["symbol"]), W.days.get_loc(TS(top["date"]))
        mem = group_members(W, jtop, name_month_keys(W, ftop, jtop))                       # [A14] every name-month on the same two filings as the audited one
        mem_dates = {f"{W.days[f_]:%Y-%m-%d}" for f_ in mem}
        assert ftop in mem and len(mem) >= 2 and out3["audit"]["group_name_months"] == len(set(mem) - {ftop}), (len(mem), out3["audit"])
        assert out3["audit"]["data_event"] >= 1 and not ((cd3["symbol"] == top["symbol"]) & cd3["date"].isin(mem_dates)).any() and out3["audit_sha256"] != out2["audit_sha256"], "the name-month, and every other name-month of its group, is gone from every list"
        n3 = out3["stageA"]["cells"][cand]["base"]
        assert n3["net"] != cells[cand]["base"]["net"] and n3["n_pos"] == cells[cand]["base"]["n_pos"] and out3["parity"][cand]["n_pos"] == n3["n_pos"], "the slot goes to the next name in the order: the same number of positions, another P&L"
        assert out3["stageA"]["null"]["draws"] == NREP and out3["stageA"]["null"]["roc_max"]["p95"] != out2["stageA"]["null"]["roc_max"]["p95"], "the name-month is out of both nulls too"
        print(f"hand audit [A14]: {len(keys)} rows 'keep' (the {AUDIT_N} largest contributors per cell + ONE row per picked [A10] group: {len(one_per_group)} groups cover {int((a10f['picked'] != '').sum())} picked flagged name-ranks, {len(a10f)} flagged in all) -> the same numbers, audit counted {AUDIT_N}/{AUDIT_N} and every picked group; "
              f"a data_event on {top['symbol']} {top['date']} ({cand}'s largest gain, ${top['pnl']:,.0f}) -> out of both cells and both nulls, with {out3['audit']['group_name_months']} more name-month(s) of its group "
              f"(the slot goes to the next name: {n3['n_pos']:,} positions either way): {cand} net ${cells[cand]['base']['net']:,.0f} -> ${n3['net']:,.0f}, null p95 {out2['stageA']['null']['roc_max']['p95']:.2f} -> {out3['stageA']['null']['roc_max']['p95']:.2f}")
        out, cells = out3, out3["stageA"]["cells"]
        passing, cand = stage_a_flow(cells)
        cand, c_frozen = out["candidate"]["cell"], out["candidate"]["c"]
        # ---- 7. Stage B's refusal paths: the lead's go-flag first, then the lockbox extract, a stale stamp, a changed audit file, a broken size, drifted inputs; none may write the read flag
        print("--- Stage B refusal paths: no go-flag / no pinned lockbox extract / not judged / no candidate / a stale stamp / a changed audit file / a broken size / a drifted calendar, manifest, book, WF numbers or size c / a bad lockbox extract; none may write the flag")
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
        st0 = stamp()
        for k in st0:
            j = json.loads(js0)
            j[k] = ["x"] if isinstance(st0[k], list) else "0" * 64
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
        must_b("lockbox year's share facts are not pinned")                                # a valid stage file, the lead's flag - and no second extract pinned: the sealed year's share facts cannot be read
        must_b("lockbox year's share facts are not pinned", LB_FACTS={"facts": env.lb_facts["facts"]})
        must_b("DIFFERS", PREREG_SHA="0" * 64, LB_FACTS=env.lb_facts)
        with patched(M17, WIDE_CA_SHA="0" * 64):
            must_b("different harness version", LB_FACTS=env.lb_facts)                     # the pinned calendar is in Stage A's stamp: another pinned sha stops it at the stamp
        for key in FILES:
            must_b("different harness version", LB_FACTS=env.lb_facts, FILE_SHA={**FILE_SHA, key: "0" * 64})          # so is every pinned file
        au0 = open(ap).read()
        open(ap, "a").write("ZZZ,2016-11-01,N12,keep,a changed audit file\n")
        must_b("not the file Stage A ran with", LB_FACTS=env.lb_facts)
        open(ap, "w").write(au0)
        must_b("do not reproduce its LB numbers", CHECK_BOOK=True, LB_FACTS=env.lb_facts)           # the book's LB numbers (the synthetic one cannot reproduce them)
        okbk = lambda B_, lo_, hi_, ref: {"roc": 0.0, "sortino": 0.0, "ref": list(ref), "ok": True}
        with patched(A13, book_check=okbk):
            must_b("not the one Stage A ran on", CHECK_BOOK=True, LB_FACTS=env.lb_facts, manifest_sha=lambda: "ffffffff" + "0" * 56)
        csv0 = open(env.wide_csv, "rb").read()
        with open(env.wide_csv, "ab") as f_:
            f_.write(b"cash_dividend,S01,,,2024-02-09,2024-02-09,,,0.01,,,,False\n")
        must_b("is not the registered wide calendar", LB_FACTS=env.lb_facts)                # the file changed after it was registered: refused before the flag
        open(env.wide_csv, "wb").write(csv0)
        assert M17.sha_raw(env.wide_csv) == env.wide_sha
        bad_lb = {k: (v[0], "0" * 64) for k, v in env.lb_facts.items()}
        must_b("is not the registered", LB_FACTS=bad_lb)                                    # the lockbox extract is not the file the addendum pinned
        late_row = open(env.lb_facts["facts"][0], newline="").read().split("\n")[1].split(",")
        late_row[FACT_HDR.index("filed")] = "2026-07-02"
        pl_ = os.path.join(xd, "lb_facts_late.csv")
        with open(pl_, "w", newline="\n") as f_:
            f_.write(open(env.lb_facts["facts"][0], newline="").read().rstrip("\n") + "\n" + ",".join(late_row) + "\n")
        must_b("filed on / after the cut", LB_FACTS={**env.lb_facts, "facts": (pl_, M17.sha_raw(pl_))})              # a fact filed after the lockbox's own end is refused
        j = json.loads(js0)
        j["parity"][cand]["net"] += 1e6
        open(sa_path, "w").write(json.dumps(j))
        must_b("do not reproduce on Stage B's data", LB_FACTS=env.lb_facts)                # the WF numbers drifted since Stage A
        j = json.loads(js0)
        j["parity"][cand]["n_pos"] += 1
        open(sa_path, "w").write(json.dumps(j))
        must_b("do not reproduce on Stage B's data", LB_FACTS=env.lb_facts)
        j = json.loads(js0)
        j["candidate"]["c"] *= 1.0001
        open(sa_path, "w").write(json.dumps(j))
        must_b("volatility-set size c", LB_FACTS=env.lb_facts)                              # the frozen size is recomputed on the cell's own window on Stage B's data: a drift of 1 in 10,000 stops it
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
            with contextlib.redirect_stdout(buf), patched(D15, cell_stats=tap), patched(THIS, LB_FACTS=env.lb_facts):
                ok = stage_b()
            txt_b = buf.getvalue()
            print(txt_b.rstrip())
            sb = json.load(open(os.path.join(OUT, "netiss_stageB.json")))
            assert os.path.exists(rd) and sb["pass"] == ok and sb["cell"] == cand and sb["c"] == c_frozen and sb["leg"]["n_pos"] > 0 and {k: sb.get(k) for k in stamp()} == stamp() and sb["prereg_sha256_lf"] == PREREG_SHA
            assert set(sb["checks"]) == {f"leg monthly rebalances>={RULES['b_reb']}", "leg net>0", "leg net>0 without its top name-month"} and ok is all(sb["checks"].values()), "the pass is the LEG's veto: three checks, no book"
            assert sb["es_return_lb"]["stretch"] == ["2025-06-30", "2026-06-30"] and sb["go_flag"].startswith("smoke: the lead's go-flag")
            assert sb["lockbox_facts_sha256"] == {k: env.lb_facts[k][1] for k in ("facts", "facts_add")} and sb["lockbox_facts"]["rows_filed_on_or_after_the_cut"] == 0 and sb["lockbox_facts"]["rows"] > finfo["rows"], "Stage B read the pinned lockbox extract"
            add, mb_ = sb["book_add_reported"], B.mask(LB0, LB1)                           # the book add on the lockbox at the FROZEN c: reported, recomputed from the book file and the captured series
            want = R11.stats((B.raw + c_frozen * cap["x"])[mb_], B.index[mb_])
            assert add["c"] == c_frozen and abs(add["roc"] - want["roc"]) < 1e-9 and abs(add["sortino"] - want["sort"]) < 1e-9 and abs(add["net"] - want["net"]) < 1e-6, add
            assert add["reference"] == {"roc": RULES["b_roc"], "sortino": RULES["b_sort"]} and add["would_have_cleared"] is bool(want["roc"] >= RULES["b_roc"] and want["sort"] >= RULES["b_sort"]) and "never a pass" in add["note"]
            assert "book add, REPORTED and never part of the pass" in txt_b and ("PASS - the leg survives" in txt_b) is ok and ("FAIL - the leg is vetoed" in txt_b) is not ok

            def reread(leg_ok, book_ok):                                                    # the pass is the leg's veto ALONE: the leg forced to pass with the book add's bar forced to miss, then the leg forced to fail with the bar forced to clear
                os.remove(rd)
                os.remove(os.path.join(OUT, "netiss_stageB.json"))

                def forced(Bk, xk, ck, lo_, hi_, run_, *a_, **k_):
                    st_ = real_cs(Bk, xk, ck, lo_, hi_, run_, *a_, **k_)
                    if lo_ == LB0:
                        st_ = {**st_, "n_units": 10 ** 6 if leg_ok else 0, "net": 1e6 if leg_ok else -1e6, "net_ex_top_pos": 1e6 if leg_ok else -1e6}
                    return st_
                keep_bar = (RULES["b_roc"], RULES["b_sort"])
                RULES["b_roc"], RULES["b_sort"] = (-1e9, -1e9) if book_ok else (1e9, 1e9)
                b_ = io.StringIO()
                try:
                    with contextlib.redirect_stdout(b_), patched(D15, cell_stats=forced), patched(THIS, LB_FACTS=env.lb_facts):
                        ok_ = stage_b()
                finally:
                    RULES["b_roc"], RULES["b_sort"] = keep_bar
                return ok_, json.load(open(os.path.join(OUT, "netiss_stageB.json"))), b_.getvalue()
            for leg_ok, book_ok in ((True, False), (False, True)):
                ok2, sb2, t2 = reread(leg_ok, book_ok)
                assert ok2 is leg_ok and sb2["pass"] is leg_ok and all(sb2["checks"].values()) is leg_ok and sb2["book_add_reported"]["would_have_cleared"] is book_ok and os.path.exists(rd), (leg_ok, book_ok, sb2["checks"])
                assert abs(sb2["book_add_reported"]["roc"] - add["roc"]) < 1e-9 and sb2["book_add_reported"]["c"] == c_frozen, "the book add is the same sum whatever the verdict"
                assert ("PASS - the leg survives" in t2) is leg_ok and ("FAIL - the leg is vetoed" in t2) is not leg_ok and ("FORWARD SHADOW" in t2) is leg_ok
                print(f"  leg forced {'to pass' if leg_ok else 'to fail'}, book-add bar forced {'to clear' if book_ok else 'to miss'}: Stage B {'PASS' if ok2 else 'FAIL'}, would_have_cleared {sb2['book_add_reported']['would_have_cleared']} - the verdict is the leg's")
            with patched(THIS, LB_FACTS=env.lb_facts):
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
TESTS = ("t_constants", "t_entries", "t_score", "t_pairs", "t_sides", "t_files", "t_pipeline", "t_nulls", "t_twins", "t_judge", "t_reference", "t_rows", "t_share_class", "t_audit_groups", "t_integration", "t_stage_b_refusals", "t_cut")


def selftest():
    """hand-made worlds and filings, no files, no data, no network: every group of tests prints one line, the last line says how many ran"""
    t0 = time.time()
    with tempfile.TemporaryDirectory() as td, patched(THIS, OUT=os.path.join(td, "out")), patched(DV, REF_CSV=os.path.join(td, "no_such_dir", "resmom_cells_daily_wf.csv")):
        for name in TESTS:                                       # the real xbrl files / wide calendar / RESMOM line file / OUT are never read or written by a test: a read that is not stubbed lands in the temp dir and refuses
            t1 = time.time()
            globals()[name]()
            print(f"  {name} ok ({time.time() - t1:.1f}s)", flush=True)
    print(f"selftest ok: {len(TESTS)} groups ({', '.join(t[2:] for t in TESTS)}) in {time.time() - t0:.0f}s")


def main(argv):
    cmd, args = (argv[0], argv[1:]) if argv else ("", [])
    fn = {"selftest": selftest, "smoke": smoke, "dryload": dryload, "stage_a": stage_a, "stage_b": stage_b}.get(cmd)
    if fn is None:
        print("usage: r21_netiss.py selftest | smoke DIR [stage_b] | dryload | stage_a | stage_b   (dryload: counts only; stage_a after the registered pre-registration is committed; stage_b only on the stock families' one sealed-year day, "
              "with the lead's netiss_stageB_GO.flag on file and the lockbox year's share facts pinned)")
        return
    if cmd in ("stage_a", "stage_b"):
        os.makedirs(OUT, exist_ok=True)
    fn(*args)


if __name__ == "__main__":
    main(sys.argv[1:])
