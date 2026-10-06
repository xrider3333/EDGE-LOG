# SHORTINT r1 - SHORT INTEREST in US large caps, rebalanced MONTHLY, dollar-neutral: cells D1 (DAYS TO COVER = FINRA's short interest at the latest settlement date known at the rank close / the cache's own mean RAW daily share volume of the 20 sessions ending at it) and S1 (the
# SHORT-INTEREST RATIO = the same short interest / NETISS r1's point-in-time shares outstanding, carried to that settlement date by the split factor); at each month-end rank close long the 50 LOWEST (the least-shorted), short the 50 HIGHEST (the crowded shorts).
# A leg for BOOK #463 that must clear the STANDALONE bars (MANAGER #56) and is reported INCREMENTALLY over the RESMOM reference book L = #463 + 0.264 x RES on THIS family's SHORTER walk-forward (positions exited 2018-08-01 .. 2025-06-29: the FINRA archive starts 2018-06).
# Pre-registered: tools/rocfrontier/PREREG_SHORTINT_R1.txt (canonical LF sha256 d30027e6...ac13 = DRAFT v1 + PRE-DATA ADDENDUM 1 ([A1]-[A6]: funds out, FINRA's market codes and the 90% coverage start rule, dissemination at the later of s + 12 sessions and the photographed date, each side's beta,
# stale counts, the power line first) + ADDENDUM 2 ([A7]-[A11]: the pinned FINRA pull - the flat file, its manifest, the photographed schedule, the provenance, the date probe -, the quarantined sealed-year file, the known-at rule as found, coverage as found, FINRA-revised rows)). Every rule, threshold,
# window and cost below is that file; where it is silent the choice is marked CHOICE.
# SHORTINT is NETISS r1's sibling in the same lane on the same data: r17_resmom.py is imported, never copied and never edited (the loaders, the pinned wide calendar, the dividend / spin-off arrays, the monthly schedule, fills / holds / costs / borrow, the cell engine, the statistics, the hygiene windows,
# the audit rows, the refusals), r18_divrun.py for the REFERENCE book (ref_load / ref_build / ref_at / incremental_pass / a2_report), the null statistics and the shared helpers, and r21_netiss.py for the SHARE-COUNT machinery (the pinned XBRL tables and maps read as one, the first-filed rule, the
# point-in-time S search, the split factor, [A3]'s two-way split check, the null's draw, the beta credit rule, the gate, the hedged twin, the turnover / dividend / spin counts). What this file adds is the FINRA logic: the pinned short-interest files, the known-at rule, the ticker walk-back and its refusals,
# the funds filter, the coverage rule, the two scores, the ADV tie-break, the stretch that starts at the first covered rank, and the reports.
#   python r22_shortint.py selftest    hand-made worlds + hand-made FINRA files, no data: the known-at rule (s + 12 sessions against a later photographed date), the ticker walk-back and the shared-ticker refusal, the funds filter, the 90% start rule and NOT JUDGEABLE, D1 (15 of 20 sessions, a split inside the window,
#                                      SI = 0), S1 (the carry by F, the 200-day limit, ln(1000)), revised rows, the 150 / thirds / 20 fallback and the ADV tie-break, the flat 3% borrow, the null with the power line printed first, the refusals (the wrong sha of every pinned file), every pool / score / pick / path against a plain-python recount
#   python r22_shortint.py smoke DIR   offline end-to-end on SYNTHETIC worlds (r5_siporb's fake Alpaca, a fake ES master, a fake #463, a fake RESMOM line file, fake XBRL tables + maps, a fake FINRA pull with its manifest / schedule / provenance / probe, a fake asset list, a fake wide calendar with name changes):
#                                      a world with a planted short-interest effect that Stage A must find and a world without one where it must not; DIR's name must contain 'smoke'; every command except Stage B's read runs
#   python r22_shortint.py dryload     WF inputs only (every input cut to dates < 2025-06-30): prints COUNTS - the files and their market codes, the coverage per rank and the WF start rank, the symbols matched / unmatched by reason, the funds removed, the scored names per rank and cell by year, every no-score reason by year,
#                                      the revised-row counts - never a score value, return or P&L
#   python r22_shortint.py stage_a     WF Stage A + the BEFORE-ANY-P&L prints FIRST + the power line (the null) + the cells + A2 (INCREMENTAL over the reference, on this stretch) + the reports + the diagnostics -> shortint_stageA.json (+ shortint_audit_candidates.csv, shortint_funds_out.csv), PRE-LOCKBOX ONLY
#   python r22_shortint.py stage_b     Stage B (lockbox, ONCE): refuses unless the lead's flag file shortint_stageB_GO.flag is on file (and a Stage A candidate that passed (a)-(e)) and the lockbox year's FINRA files are pinned; the pass is the LEG's veto, the book add is only reported
# Reads (never writes) the SIPORB cache through r5_siporb, the ES 5m RTH masters through augur_engine.data, the #463 book through r11_risk, the sha-pinned wide corporate-actions calendar (and its name-change rows), RESMOM's sha-pinned WF line file (the reference), the four sha-pinned XBRL / map files, the five sha-pinned FINRA
# files and the sha-pinned SIPORB asset list, every one cut at read. Results go to OUT (outside git). Nothing here pulls, commits, pushes or writes anywhere else, and nothing here makes a network call.
import bisect, contextlib, hashlib, io, json, math, os, re, shutil, sys, tempfile, time
from collections import Counter, defaultdict
from types import SimpleNamespace
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import numpy as np, pandas as pd
import r17_resmom as M17            # the sibling harness (RESMOM r1): its loaders, calendar, arrays, schedule, engine, statistics, A2 and audit rows are called wherever they fit
import r18_divrun as DV             # the sibling harness (DIVRUN r1): the REFERENCE book [X1], the incremental A2, the null statistics, the generic diagnostics, the synthetic market of the smoke
import r21_netiss as NI             # the sibling harness (NETISS r1): the share-count machinery, the null's draw, the beta credit rule, the gate, the hedged twin, the synthetic share counts of the smoke
D15, S, R11, M12, A13 = M17.D15, M17.S, M17.R11, M17.M12, M17.A13       # r15_ddw (World, cell statistics, seat, null engine), r5_siporb, r11_risk, r12_mdl, r13_attn - through r17's own imports
day_i, row_le, dstr, per_year, spearman, pctl_text, nan_or, jyear = NI.day_i, NI.row_le, NI.dstr, NI.per_year, NI.spearman, NI.pctl_text, NI.nan_or, DV.jyear

TS = pd.Timestamp
THIS = sys.modules[__name__]
OUT_DEFAULT = r"C:\EdgeLog\_anatomy_cache\rocfrontier\shortint_r1"
OUT = os.environ.get("EDGELOG_SHORTINT_R1", OUT_DEFAULT)                                                  # results, outside git
PREREG = os.path.join(HERE, "PREREG_SHORTINT_R1.txt")
PREREG_SHA = "56a4bd401eda4e16b236e9bde6978d6a8352fb71edac93e3cdabadcfa5f8d0f1"                      # canonical (LF) sha256 of the pre-registration: DRAFT v1 + PRE-DATA ADDENDA 1-3 (addendum 3 = the lead's review of this harness); if more edits land the lead updates it before the real run
WF0, PRE_END, LB0, LB1 = TS("2018-08-01"), M17.PRE_END, M17.LB0, M17.LB1  # THIS family's WF = positions EXITED 2018-08-01 .. 2025-06-29 (the house WF starts 2016-07-01; the archive starts 2018-06); LB = exits 2025-06-30 .. 2026-06-30 INCLUSIVE; cuts: S.LB0 / S.END
BOOK_WF, BOOK_LB, DEEPEST_WF = M17.BOOK_WF, M17.BOOK_LB, M17.DEEPEST_WF
NREP, SEED = 500, 20261018                                               # the registered null: 500 draws of random names from each rebalance's eligible SCORED pool (funds out)
CELLS = ("D1", "S1")                                                     # the family: 2 cells
YEARS = tuple(range(2018, 2025))                                         # the seven July-June WF years 2018-19 .. 2024-25 (2018-19 starts 2018-08-01)
A2_YEARS = 2                                                             # A2 (a REPORT): c by volatility over the cell's first two years of the stretch, 2018-08-01 .. 2020-07-31 (25% of #463's daily std / the cell's)
A2_TARGET, A2_REPORT = M17.A2_TARGET, M17.A2_REPORT                      # 25% of #463's std; the book at 0.5c and 2c is reported
COST_BPS, STRESS_BPS, BORROW, BORROW_STRESS = M17.COST_BPS, M17.STRESS_BPS, M17.BORROW, M17.BORROW_STRESS     # 5 bps a side (stress 10, 20); 0.25% a year on short notional (stress 1% and 3% on k_t > 1.5 sessions)
BORROW_FLAT = 0.03                                                       # Stage A (b): the BINDING flat borrow stress, 3% a year on every short every day (CHOICE: the total rate - it replaces the 0.25% base, it is not added to it)
BORROW_CURVE = (0.0, 0.0025, 0.01, 0.03, 0.05, 0.10, 0.20)               # the BORROW CURVE: net at each flat rate on every short, and the break-even fee
AUDIT_N = 50                                                             # (f) the largest single-name contributors audited by hand
SQUEEZE_N = 20                                                           # the 20 largest name-month gains AND losses
LN1000 = math.log(1000.0)                                                # S1's scale-error rule
BETA_CAP = NI.BETA_CAP                                                   # a cell with |realised beta| above it (per $ of one side's notional) is never credited
SUBPERIODS = (("2018-08-01 .. 2021-12-31", TS("2018-08-01"), TS("2021-12-31")), ("2022-01-01 .. 2025-06-29", TS("2022-01-01"), TS("2025-06-29")))     # the regime halves
CRASH_JAN21 = (TS("2021-01-01"), TS("2021-01-31"))                       # the squeeze month printed in full
SPEC = {"min_scored": 150, "min_side": 20,          # fewer than 150 scored names: the bottom / top THIRD (n // 3), at least 20 a side, else nothing (counted)
        "lag": 12,                                  # [K] / [A3] a settlement is disseminated s + 12 SESSIONS after it, or on the photographed release date if that is later; usable from the first session AFTER that
        "adv_n": 20, "adv_min": 15,                 # D1: ADV = the mean RAW daily share volume of the cache over the 20 sessions ending at s*, at least 15 of them present
        "stale": 200, "old": 100,                   # S1: the share count's as-of date at most 200 days before s*; [A5] the share of counts more than 100 days old is printed
        "cover": 0.90, "min_reb": 60,               # [A2] a rank whose latest usable file covers less than 90% of its universe trades nothing; fewer than 60 rebalances = NOT JUDGEABLE
        "hedge_win": 252, "hedge_min": 230}         # the ES hedge ratio (the twin, NETISS [A6]'s rule)
FUND_TITLE_TOKENS = ("Physical", "Fund", "Municipal", "Term Trust", "Income Trust", "Capital Securities", "Certificates")      # [A1] an asset-list title that contains one of them (CHOICE: a literal, case-sensitive substring): out of the universe AND the null's pool
FUND_NAME_TOKENS = ("ETF", "ETN", "Fund", "Index")                       # [A1] a FINRA issue name that contains one of them (CHOICE: literal, case-sensitive substring): the same
QUARANTINED = ("shrt20250613.csv",)                                      # [A8] the sealed-year file: never in the flat file, never read
MARKETS = ("NYSE", "NNM", "ARCA", "SC", "BZX", "AMEX", "IEX", "OTC", "OTCBB")      # FINRA's market codes as found in the pull (printed in this order; any other code is counted apart)
FINRA_DIR = os.environ.get("EDGELOG_FINRA_DIR", r"C:\EdgeLog\_research_cache\finra_shortint")
FILES = {"flat": os.path.join(FINRA_DIR, "finra_shortint_flat.csv"), "manifest": os.path.join(FINRA_DIR, "finra_shortint_manifest.json"), "schedule": os.path.join(FINRA_DIR, "finra_schedule_2018_2025.csv"),
         "provenance": os.path.join(FINRA_DIR, "finra_shortint_provenance.json"), "probe": os.path.join(FINRA_DIR, "probe_settlement_dates.json")}      # the asset list is S.path_of('assets.csv') (assets_path)
FILE_SHA = {"flat": "9c72cc2712270aa7516a5bdb2b1c18c7aa04870242956fb0b5d2d58e1871bb4a", "manifest": "a99fe890829751fefece7742e63303d6307cde9e893659fc9e8ae817202337f6", "schedule": "ff4005d01e2807da7ec12cd49804c039706a29f5194f7852372ff7a7beaa1948",
            "provenance": "5d306bcc1ba45c29c6df48f8c0772ca6446b88d305b93ee2af9462bce8b997f0", "probe": "80f673344b0e3600c01a597e75d348e4d6df56d6b9d22d454f239946e788282c", "assets": "b85928ff655a883dd3eb44d8d96b3b745ffe2f5f0e0ca0991485895f5e960991"}
FILE_LABEL = {"flat": "FINRA short-interest flat file (finra_shortint_flat.csv)", "manifest": "FINRA flat file's manifest", "schedule": "photographed FINRA release schedule", "provenance": "FINRA per-file provenance", "probe": "FINRA settlement-date probe",
              "assets": "SIPORB asset list (assets.csv)"}
FINRA_KEYS = ("flat", "manifest", "schedule", "provenance", "probe")
FLAT_COLS = ("settlement_date", "symbol", "issue_name", "exchange_code", "market_code", "short_interest", "prev_short_interest", "split_flag", "avg_daily_volume", "days_to_cover", "revision_flag", "source_file")
FLAT_NUM = ("short_interest", "prev_short_interest", "avg_daily_volume", "days_to_cover")
LB_FINRA = None          # Stage B: the lockbox year's FINRA files (settlements 2025-06-13 .. 2026-06-30) are NOT in the pinned pull (it stops at 2025-05-30 and shrt20250613.csv is quarantined): a dated addendum must pin a second extract by sha256 here ({key: (path, sha256)} for the five FINRA files) before Stage B can read one row of the sealed year; None = Stage B refuses (CHOICE: the prereg says 'as RESMOM' and the pinned pull holds no sealed-year row, so Stage B cannot run without that addendum)
CHECK_BOOK = True        # refuse to judge if the #463 records / the DD structure / the cache manifest / the reference / the cache's first session do not reproduce the registered facts; a real run always checks (only smoke() may switch it)
CACHE_FIRST_SESSION = NI.CACHE_FIRST_SESSION
HYG = M17.HYG            # the four data-hygiene reasons [T2]
AUD = M17.AUD            # the tag of this harness's rows in World.aud_hit (r17_resmom's: its unused_audit_rows reads it)
GO_FLAG, READ_FLAG = "shortint_stageB_GO.flag", "shortint_stageB_READ.flag"     # Stage B needs the lead's go-flag; the one-shot read flag is written (exclusively) after every load and check
RULES = M17.RULES        # Stage A (a) - (e) and Stage B's leg veto are r17_resmom's own (the booleans are switches only smoke() ever turns off)
TAIL = "(nothing computed, lockbox NOT read)"
# the reasons a name has no score at a rank, by the FIRST rule that fails (the order below is the order of the rules): the funds / FINRA-row rules are common to both cells, then each cell's own
(R_SCORED, R_FUND_TITLE, R_TICKER_UNKNOWN, R_TICKER_SHARED, R_NO_ROW, R_DUP_ROWS, R_FUND_NAME, R_REVISED, R_SI_MISSING,
 R_ADV_FEW, R_SPLIT_WINDOW, R_ADV_ZERO,
 R_MULTI_CLASS, R_NOT_IN_MAP, R_MAP_MISMATCH, R_MAP_AMBIGUOUS, R_MAP_UNMAPPED, R_MAP_NONCOMMON, R_MAP_OTHER, R_NO_FACTS, R_FOREIGN, R_NO_FACT, R_NOT_POS, R_STALE, R_NO_FACTOR, R_SPLIT_C, R_SPLIT_F, R_SCALE, R_NO_FILE) = range(29)
REASONS = ("scored", "fund_asset_title", "ticker_history_unknown", "ticker_shared", "no_finra_row", "duplicate_finra_rows", "fund_finra_name", "revised_row", "si_missing_or_negative",
           "adv_under_15_sessions", "split_in_volume_window", "adv_not_positive",
           "multi_class_cik", "not_in_map", "map_mismatch", "map_ambiguous", "map_unmapped", "map_non_common", "map_other", "no_facts_for_cik", "foreign_filer", "no_share_fact_at_s", "value_not_positive", "share_count_over_200_days",
           "no_split_factor", "split_calendar_not_in_F", "split_F_not_in_calendar", "scale_error", "no_usable_file")
REASON_TEXT = {"scored": "scored", "fund_asset_title": "[A1] fund by its asset-list title", "ticker_history_unknown": "ticker unknown (an ambiguous rename chain)", "ticker_shared": "ticker held by two cache names on overlapping dates", "no_finra_row": "no FINRA row for the ticker at s*",
               "duplicate_finra_rows": "the ticker is listed twice in the file", "fund_finra_name": "[A1] fund by FINRA's issue name", "revised_row": "[A11] FINRA-revised row (revision flag R)", "si_missing_or_negative": "short interest missing or negative",
               "adv_under_15_sessions": "D1: fewer than 15 of the 20 sessions have a volume", "split_in_volume_window": "D1: a split (calendar or F) inside the 20 sessions", "adv_not_positive": "D1: ADV not positive",
               "multi_class_cik": "S1: the CIK carries two or more symbols (a firm's share count against a class's short interest)", "not_in_map": "S1: symbol not in the CIK map", "map_mismatch": "S1: map: current ticker, name does not agree", "map_ambiguous": "S1: map: name ambiguous",
               "map_unmapped": "S1: map: unmapped", "map_non_common": "S1: map: debenture / preferred / unit", "map_other": "S1: map: another method", "no_facts_for_cik": "S1: CIK with no share fact", "foreign_filer": "S1: foreign filer (20-F / 40-F / 6-K only)",
               "no_share_fact_at_s": "S1: no usable share fact at s*", "value_not_positive": "S1: share count not positive", "share_count_over_200_days": "S1: share count's as-of date more than 200 days before s*", "no_split_factor": "S1: no split factor on a date",
               "split_calendar_not_in_F": "S1: [A3] a calendar split F does not show (a to s*)", "split_F_not_in_calendar": "S1: [A3] an F change the calendar does not show (a to s*)", "scale_error": "S1: |ln(S1 / the rank's median)| > ln(1000)", "no_usable_file": "no usable settlement at the rank"}
SHARED_REASONS = tuple(range(R_FUND_TITLE, R_SI_MISSING + 1))
D1_REASONS = (R_ADV_FEW, R_SPLIT_WINDOW, R_ADV_ZERO)
S1_REASONS = tuple(range(R_MULTI_CLASS, R_SCALE + 1))
CELL_REASONS = {"D1": SHARED_REASONS + D1_REASONS + (R_NO_FILE,), "S1": SHARED_REASONS + S1_REASONS + (R_NO_FILE,)}
STATIC_OF = {"not_in_map": R_NOT_IN_MAP, "map_mismatch": R_MAP_MISMATCH, "map_ambiguous": R_MAP_AMBIGUOUS, "map_unmapped": R_MAP_UNMAPPED, "map_non_common": R_MAP_NONCOMMON, "map_other": R_MAP_OTHER, "no_facts_for_cik": R_NO_FACTS, "foreign_filer": R_FOREIGN}
M_OK, M_UNKNOWN, M_SHARED, M_NO_ROW, M_DUP = range(5)                    # a ticker's match at one settlement
M_REASON = {M_UNKNOWN: R_TICKER_UNKNOWN, M_SHARED: R_TICKER_SHARED, M_NO_ROW: R_NO_ROW, M_DUP: R_DUP_ROWS}
MODES = ("top", "third", "none", "uncovered", "nofile")                  # what a rank trades: the top 50 a side, the thirds, nothing (too few scored), nothing (under 90% coverage), nothing (no usable settlement)
REV_MODES = ("drop", "asis")                                             # [A11] the registered reading drops FINRA-revised rows; the REPORTED twin scores them as they stand


# ------------------------------------------------------------------ guards: the prereg, the stamp, the cut, the files
def refuse(msg):
    raise SystemExit(msg)


assert_cut, peak_mb, patched, ceil_pct = A13.assert_cut, A13.peak_mb, A13.patched, A13.ceil_pct
file_sha, manifest_sha, book_checks = M17.file_sha, M17.manifest_sha, M17.book_checks      # module-level names, so a test can stub them


def prereg_ok():
    """the frozen spec this file implements must still be the registered one (a changed spec = a new file, r2): a missing or changed file refuses every stage. Also checked against the committed blob when there is one
    (r15_ddw.committed_state, pointed at this file's names for the call); until it is committed that is printed (the lead commits before the real run) and recorded in the Stage A file"""
    if not os.path.exists(PREREG):
        refuse("refused: PREREG_SHORTINT_R1.txt is not next to this file - the spec cannot be verified " + TAIL)
    if R11.sha_lf(PREREG) != PREREG_SHA:
        refuse("refused: PREREG_SHORTINT_R1.txt DIFFERS from the registered one - a changed spec is a new file, r2 " + TAIL)
    with patched(D15, PREREG=PREREG, PREREG_SHA=PREREG_SHA):
        st = D15.committed_state()
    if st == "differs":
        refuse("refused: the COMMITTED PREREG_SHORTINT_R1.txt differs from the registered sha - the file on disk is not the file in git " + TAIL)
    print("prereg check: PREREG_SHORTINT_R1.txt sha256 matches the registered one; committed blob: " + {"match": "matches too", "untracked": "NOT COMMITTED YET - commit it before the real run",
                                                                                                      "unknown": "git not available here (not checked)"}[st])
    return {"verified": True, "committed": st}


def stamp():
    """the version a stage ran with: this file's LF sha256 + r21_netiss's (which carries r17's, r18's and every harness they import, the pinned wide calendar's sha and the four pinned XBRL / map files' shas) + the six pinned FINRA / asset files' shas;
    Stage B refuses on any change, so a change to any of them after Stage A sends it through Stage A again"""
    ni = NI.stamp()
    return {"harness_sha256": R11.sha_lf(os.path.abspath(__file__)), "r21_sha256": ni["harness_sha256"], **{k: v for k, v in ni.items() if k != "harness_sha256"},
            **{f"finra_{k}_sha256": FILE_SHA[k] for k in FINRA_KEYS}, "assets_sha256": FILE_SHA["assets"]}


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


def assets_path():
    """the SIPORB asset list: the cache's own (S.path_of, so the smoke's synthetic cache points elsewhere)"""
    return S.path_of("assets.csv")


def pinned_path(key):
    return assets_path() if key == "assets" else FILES[key]


def check_pinned(key):
    """the sha256 (of the BYTES) of one pinned file [A7] / [A1]: refuses - nothing computed, lockbox NOT read - when it is not on file or is another file than the registered one"""
    p = pinned_path(key)
    if not os.path.exists(p):
        refuse(f"refused: the pinned {FILE_LABEL[key]} {p} is not on file {TAIL}")
    got = M17.sha_raw(p)
    if got != FILE_SHA[key]:
        refuse(f"refused: {os.path.basename(p)} (sha256 {got}) is not the registered {FILE_LABEL[key]} ({FILE_SHA[key]}) - the file changed after it was registered {TAIL}")
    return got


# ------------------------------------------------------------------ [A7] / [A1] the pinned files: the sha gate, the flat file read as ONE table (chunked), the manifest / schedule / provenance / probe cross-checked, the asset list; all cut at read
def src_day(name):
    """'shrt20250530.csv' -> '2025-05-30' (None when the name is not a FINRA short-interest file name)"""
    m = re.fullmatch(r"shrt(\d{4})(\d{2})(\d{2})\.csv", str(name).strip())
    return None if m is None else f"{m.group(1)}-{m.group(2)}-{m.group(3)}"


def read_json(key):
    """one of the two pinned json files (the manifest, the provenance, the probe) as a dict; an unreadable one refuses"""
    p = FILES[key]
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError) as e:
        refuse(f"refused: the {FILE_LABEL[key]} {os.path.basename(p)} cannot be read as json ({type(e).__name__}) {TAIL}")


def read_schedule(cut):
    """[A9] the photographed schedule (settlement, due, release, release_column, page, pages_disagree) cut at READ time: a row whose settlement or release date is on / after the cut is dropped and counted (the page also lists the year ahead), an unreadable settlement
    date is dropped and counted, and the table is asserted to hold none; a settlement twice refuses. -> ({settlement day number: release day number or -1}, the counts)"""
    cutt = TS(cut)
    df = pd.read_csv(FILES["schedule"], dtype=str, keep_default_na=False)
    miss = [c for c in ("settlement", "release") if c not in df.columns]
    if miss:
        refuse(f"refused: the {FILE_LABEL['schedule']} lacks the column(s) {miss} {TAIL}")
    rs = df["release"].str.strip()
    st = pd.to_datetime(df["settlement"].str.strip(), format="%Y-%m-%d", errors="coerce")
    rl = pd.to_datetime(rs.where(rs != ""), format="%Y-%m-%d", errors="coerce")
    late = ((st >= cutt) | (rl >= cutt)).to_numpy()
    bad = st.isna().to_numpy()
    keep = ~late & ~bad
    d = pd.DataFrame({"settlement": st[keep].to_numpy(), "release": rl[keep].to_numpy()})
    if d["settlement"].duplicated().any():
        refuse(f"refused: the {FILE_LABEL['schedule']} lists a settlement date more than once {TAIL}")
    assert_cut("FINRA schedule (settlement)", pd.DatetimeIndex(d["settlement"]), cut)
    assert_cut("FINRA schedule (release)", pd.DatetimeIndex(d["release"].dropna()), cut)
    dis = df.loc[keep, "pages_disagree"].str.strip().str.lower() == "true" if "pages_disagree" in df.columns else pd.Series(False, index=df.index[keep])
    col = df.loc[keep, "release_column"].str.strip() if "release_column" in df.columns else pd.Series("", index=df.index[keep])
    info = {"rows_on_file": int(len(df)), "rows_dropped_at_the_cut": int(late.sum()), "rows_unreadable_settlement": int(bad.sum()), "rows_read": int(len(d)), "rows_with_a_release_date": int(d["release"].notna().sum()),
            "pages_disagree_settlements": [f"{t:%Y-%m-%d}" for t in d["settlement"][dis.to_numpy()]], "by_release_column": {k: int(v) for k, v in col.value_counts().items()}}
    out = {int(day_i(s)): (int(day_i(r)) if pd.notna(r) else -1) for s, r in zip(d["settlement"], d["release"])}
    return out, info


def read_flat(cut, chunk=400_000):
    """[A7] the flat file (columns settlement_date, symbol, issue_name, exchange_code, market_code, short_interest, prev_short_interest, split_flag, avg_daily_volume, days_to_cover, revision_flag, source_file) read ONCE in chunks into compact arrays, cut at READ time: the pinned file
    holds no settlement on / after the cut and none of the quarantined files [A8] (either refuses - it is not the registered file); a row with an unreadable settlement date refuses; a row without a symbol is dropped and counted. Per row: its settlement date (day number), symbol (code into
    a table), market code (an index into MARKETS, len(MARKETS) = another code), the four numbers (a missing / unreadable one is NaN), FINRA's split flag 'S', revision flag 'R', the [A1] fund test on the issue name (a literal, case-sensitive token) and the file it came from. The issue
    names themselves are not kept (only the symbols whose name carries a fund token, with the names). Rows are ordered by settlement date (stable). -> (the table, the counts)"""
    p = FILES["flat"]
    hdr = pd.read_csv(p, nrows=0)
    miss = [c for c in FLAT_COLS if c not in hdr.columns]
    if miss:
        refuse(f"refused: the {FILE_LABEL['flat']} lacks the column(s) {miss} {TAIL}")
    cutt = TS(cut)
    pat = "|".join(re.escape(t) for t in FUND_NAME_TOKENS)
    lut, symtab, srcs, src_ix = {}, [], [], {}
    parts = defaultdict(list)
    n_all = n_nosym = n_si_bad = n_si_missing = 0
    rev_vals, spl_vals, mkt_other = Counter(), Counter(), Counter()
    pairs = defaultdict(set)
    num = lambda s: pd.to_numeric(s.str.strip().str.replace(",", "", regex=False).where(lambda t: t != ""), errors="coerce").to_numpy(float)
    for ch in pd.read_csv(p, dtype=str, keep_default_na=False, usecols=list(FLAT_COLS), chunksize=chunk):
        n_all += len(ch)
        sd = pd.to_datetime(ch["settlement_date"].str.strip(), format="%Y-%m-%d", errors="coerce")
        if sd.isna().any():
            refuse(f"refused: the {FILE_LABEL['flat']} has {int(sd.isna().sum())} row(s) with an unreadable settlement date {TAIL}")
        if (sd >= cutt).any():
            refuse(f"refused: {int((sd >= cutt).sum()):,} row(s) of the {FILE_LABEL['flat']} are settled on / after the cut {cutt:%Y-%m-%d} - the extract must hold none (the sealed year) {TAIL}")
        sym = ch["symbol"].str.strip()
        src = ch["source_file"].str.strip()
        if src.isin(QUARANTINED).any():
            refuse(f"refused: the {FILE_LABEL['flat']} holds rows of the quarantined file(s) {sorted(set(src[src.isin(QUARANTINED)]))} [A8] {TAIL}")
        ok = (sym != "").to_numpy()
        n_nosym += int((~ok).sum())
        ch, sd, sym, src = ch[ok], sd[ok], sym[ok], src[ok]
        mk = ch["market_code"].str.strip()
        mi = mk.map({m: i for i, m in enumerate(MARKETS)}).fillna(len(MARKETS)).to_numpy(np.int8)
        for m_, n_ in mk[mi == len(MARKETS)].value_counts().items():
            mkt_other[m_] += int(n_)
        si, psi, adv, dtc = num(ch["short_interest"]), num(ch["prev_short_interest"]), num(ch["avg_daily_volume"]), num(ch["days_to_cover"])
        raw_si = ch["short_interest"].str.strip()
        n_si_missing += int((raw_si == "").sum())
        n_si_bad += int((~np.isfinite(si) & (raw_si != "").to_numpy()).sum())
        rv, sp = ch["revision_flag"].str.strip().str.upper(), ch["split_flag"].str.strip().str.upper()
        rev_vals.update(rv.value_counts().to_dict())
        spl_vals.update(sp.value_counts().to_dict())
        fnd = ch["issue_name"].str.contains(pat, regex=True).to_numpy()
        for s_, n_ in zip(sym[fnd], ch["issue_name"][fnd]):
            pairs[str(s_)].add(str(n_))
        codes, uniq = pd.factorize(sym)
        glob = np.empty(len(uniq), np.int64)
        for i, u in enumerate(uniq):
            g = lut.get(u)
            if g is None:
                g = lut[u] = len(symtab)
                symtab.append(u)
            glob[i] = g
        sc, su = pd.factorize(src)
        gs = np.empty(len(su), np.int64)
        for i, u in enumerate(su):
            g = src_ix.get(u)
            if g is None:
                g = src_ix[u] = len(srcs)
                srcs.append(u)
            gs[i] = g
        parts["kd"].append(day_i(sd.to_numpy()).astype(np.int32))
        parts["symc"].append(glob[codes].astype(np.int32))
        parts["mkt"].append(mi)
        parts["si"].append(si)
        parts["psi"].append(psi)
        parts["adv"].append(adv)
        parts["dtc"].append(dtc)
        parts["spl"].append((sp == "S").to_numpy())
        parts["rev"].append((rv == "R").to_numpy())
        parts["fnd"].append(fnd)
        parts["srcc"].append(gs[sc].astype(np.int16))
    cat = lambda k: np.concatenate(parts[k]) if parts[k] else np.zeros(0)
    arr = {k: cat(k) for k in ("kd", "symc", "mkt", "si", "psi", "adv", "dtc", "spl", "rev", "fnd", "srcc")}
    o = np.argsort(arr["kd"], kind="stable")
    arr = {k: v[o] for k, v in arr.items()}
    ks = np.unique(arr["kd"]).astype(np.int64)
    off = np.r_[np.searchsorted(arr["kd"], ks, side="left"), len(arr["kd"])].astype(np.int64)                 # rows of settlement k = off[k] .. off[k + 1]
    fin = SimpleNamespace(**arr, symtab=np.array(symtab, dtype=object), srcs=list(srcs), ks=ks, off=off, n=int(len(arr["kd"])), fund_pairs={k: sorted(v) for k, v in pairs.items()})
    bad_src = [s_ for s_ in srcs if src_day(s_) is None]
    if bad_src:
        refuse(f"refused: the {FILE_LABEL['flat']} names a source file that is not a FINRA short-interest file name ({bad_src[:3]}) {TAIL}")
    sday = day_i(np.array([src_day(s_) for s_ in srcs], dtype="datetime64[D]"))
    if not np.array_equal(sday[fin.srcc.astype(np.int64)], fin.kd.astype(np.int64)):
        refuse(f"refused: a row of the {FILE_LABEL['flat']} carries a settlement date that is not the date in its source file's name {TAIL}")
    assert_cut("FINRA flat file (settlement)", pd.DatetimeIndex(fin.ks.astype("datetime64[D]")), cut)
    bf = np.bincount(fin.srcc.astype(np.int64) * (len(MARKETS) + 1) + fin.mkt.astype(np.int64), minlength=len(srcs) * (len(MARKETS) + 1)).reshape(len(srcs), len(MARKETS) + 1)
    by_file = {srcs[i]: {(MARKETS[j] if j < len(MARKETS) else "other"): int(bf[i, j]) for j in range(len(MARKETS) + 1) if bf[i, j]} for i in range(len(srcs))}
    info = {"rows_read": int(n_all), "rows_without_a_symbol": int(n_nosym), "rows": int(fin.n), "files": int(len(srcs)), "settlements": int(len(ks)), "first": f"{np.datetime64(int(ks[0]), 'D')}" if len(ks) else None,
            "last": f"{np.datetime64(int(ks[-1]), 'D')}" if len(ks) else None, "short_interest_blank": int(n_si_missing), "short_interest_unreadable": int(n_si_bad), "short_interest_negative": int((fin.si < 0).sum()),
            "revision_flag_values": dict(rev_vals), "split_flag_values": dict(spl_vals), "market_codes_other": dict(mkt_other), "rows_by_file_and_market": by_file, "fund_named_rows": int(fin.fnd.sum()), "fund_named_symbols": int(len(pairs))}
    return fin, info


def load_finra(cut):
    """[A7] / [A8] / [A9] the five pinned FINRA files, each refused if its sha256 (of its BYTES) differs; the flat file read as ONE table; and the cross-checks no registered file may fail: the manifest's sha, row count, file count, first / last file, quarantine list and rows by file and
    market equal what was read; the manifest's release date of every file equals the photographed schedule's; every file has a provenance entry (url, size, sha256) and the quarantined file's is on record, unread; the date probe's status-200 settlements before the cut are all in the flat
    file but the quarantined one (any other is printed as MISSING). Cut at READ time (the schedule lists the year ahead: those rows are dropped and counted). -> (fin: the table + release day per settlement, the counts)"""
    shas = {k: check_pinned(k) for k in FINRA_KEYS}
    fin, info = read_flat(cut)
    mj = read_json("manifest")
    sched, sinfo = read_schedule(cut)
    pv, pr = read_json("provenance"), read_json("probe")
    if not isinstance(mj, dict) or not isinstance(pv, dict) or not isinstance(pr, dict):
        refuse(f"refused: the manifest / provenance / probe are not json objects {TAIL}")
    bad = []
    if mj.get("out_sha256") != FILE_SHA["flat"]:
        bad.append("its sha256 of the flat file is not the registered one")
    if mj.get("rows") != info["rows_read"]:
        bad.append(f"its row count {mj.get('rows')} is not the {info['rows_read']:,} read")
    if mj.get("files") != info["files"]:
        bad.append(f"its file count {mj.get('files')} is not the {info['files']} read")
    names = sorted(fin.srcs)
    if names and (mj.get("first") != names[0] or mj.get("last") != names[-1]):
        bad.append(f"its first / last file {mj.get('first')} / {mj.get('last')} are not {names[0]} / {names[-1]}")
    if set((mj.get("quarantined") or {})) != set(QUARANTINED):
        bad.append(f"its quarantine list {sorted(mj.get('quarantined') or {})} is not {list(QUARANTINED)}")
    rbm = {}
    for f_, v in (mj.get("rows_by_file_and_market") or {}).items():                    # the manifest's codes read the way the loader reads them: a code outside the nine is 'other'
        c_ = Counter()
        for k_, n_ in dict(v).items():
            c_["other" if k_ not in MARKETS else k_] += int(n_)
        rbm[f_] = {k_: n_ for k_, n_ in c_.items() if n_}
    if rbm != info["rows_by_file_and_market"]:
        bad.append("its rows by file and market code are not the ones read")
    rbf = mj.get("release_by_file") or {}
    for s_ in fin.srcs:
        e = rbf.get(s_)
        want = sched.get(int(day_i(np.datetime64(src_day(s_)))), -1)
        got = (int(day_i(np.datetime64(e["release"]))) if isinstance(e, dict) and e.get("release") else -1) if isinstance(e, dict) else None
        if got is None or got != want or (isinstance(e, dict) and e.get("settlement") != src_day(s_)):
            bad.append(f"the release date of {s_} ({None if e is None else e.get('release')}) is not the photographed schedule's")
            break
    if bad:
        refuse(f"refused: the FINRA manifest disagrees with the files it describes: {'; '.join(bad)} {TAIL}")
    norm = {str(k).replace("\\", "/"): v for k, v in pv.items()}
    nprov = sum(1 for s_ in fin.srcs if isinstance(norm.get("files/" + s_), dict) and re.fullmatch(r"[0-9a-f]{64}", str(norm["files/" + s_].get("sha256", ""))) is not None)
    if nprov != len(fin.srcs):
        refuse(f"refused: the FINRA provenance has a url / size / sha256 entry for {nprov} of the {len(fin.srcs)} files read {TAIL}")
    quar = {q: ("files/" + q) in norm for q in QUARANTINED}
    ok_dates = sorted(f"{k[:4]}-{k[4:6]}-{k[6:]}" for k, v in pr.items() if isinstance(v, dict) and v.get("status") == 200 and re.fullmatch(r"\d{8}", str(k)))
    flat_days = {f"{np.datetime64(int(k), 'D')}" for k in fin.ks}
    quar_days = {src_day(q) for q in QUARANTINED}
    missing = [d for d in ok_dates if d < f"{TS(cut):%Y-%m-%d}" and d not in flat_days and d not in quar_days]
    fin.release = np.array([sched.get(int(k), -1) for k in fin.ks], np.int64)
    info.update({"sha256": shas, "schedule": sinfo, "manifest_rows": mj.get("rows"), "manifest_built_at_utc": mj.get("built_at_utc"), "provenance_entries": int(len(pv)), "provenance_file_entries_for_the_files_read": int(nprov),
                 "provenance_rebuilt_from_disk": int(sum(1 for s_ in fin.srcs if "rebuilt" in json.dumps(norm["files/" + s_]).lower())), "quarantined_on_record_in_provenance": quar, "probe_status_200_before_the_cut": int(sum(1 for d in ok_dates if d < f"{TS(cut):%Y-%m-%d}")),
                 "missing_settlement_dates": missing, "settlements_with_a_release_date": int((fin.release >= 0).sum())})
    return fin, info


def load_assets():
    """[A1] the SIPORB asset list (symbol, name, exchange, status ...), refused if its sha256 is not the registered one: a name whose asset-list TITLE contains one of the literal tokens in FUND_TITLE_TOKENS (case-sensitive, a substring) is a fund - out of the universe and the null's pool.
    A symbol listed twice keeps its first row's title for display and is a fund when ANY of its rows' titles carries a token (counted). -> SimpleNamespace(title = {symbol: title}, tok = {symbol: [tokens in a title]}, info)"""
    sha = check_pinned("assets")
    a = pd.read_csv(assets_path(), dtype=str, keep_default_na=False)
    miss = [c for c in ("symbol", "name", "status") if c not in a.columns]
    if miss:
        refuse(f"refused: the {FILE_LABEL['assets']} lacks the column(s) {miss} {TAIL}")
    a["symbol"] = a["symbol"].str.strip()
    dup = a["symbol"].duplicated(keep=False)
    title, tok = {}, {}
    for s_, n_ in zip(a["symbol"], a["name"]):
        title.setdefault(s_, n_)                                                               # a symbol twice (an active and an inactive asset of one ticker): the first row's title is the one shown ...
        hit = [t for t in FUND_TITLE_TOKENS if t in n_]
        if hit:
            tok[s_] = sorted(set(tok.get(s_, [])) | set(hit))                                  # ... CHOICE: and a token in ANY of its rows' titles makes it a fund (the conservative side: the name gets no score)
    first_tok = {s_: any(t in n_ for t in FUND_TITLE_TOKENS) for s_, n_ in zip(a["symbol"][~a["symbol"].duplicated()], a["name"][~a["symbol"].duplicated()])}
    by_tok = Counter(t for v in tok.values() for t in v)
    info = {"sha256": sha, "rows": int(len(a)), "symbols": int(len(title)), "duplicate_symbol_rows": int(dup.sum()), "fund_title_symbols": int(len(tok)), "fund_title_symbols_by_first_row_only": int(sum(first_tok.values())),
            "by_token": {t: int(by_tok.get(t, 0)) for t in FUND_TITLE_TOKENS}, "by_status": {k: int(v) for k, v in a["status"].value_counts().items()}}
    return SimpleNamespace(title=title, tok=tok, info=info)


def load_name_changes(cut, csv=None):
    """[SYMBOLS] the wide calendar's name_change rows (old_symbol -> new_symbol at the PROCESS date; CHOICE: the ex-date when that is blank), which r17_resmom's wide_load counts and does not keep. Read from the calendar r17_resmom has just sha-checked (stages) or from the file at hand (dryload,
    smoke), cut at READ time: a row dated on / after the cut (either date) is dropped and counted and the table is asserted to hold none; a row without a date or with an empty / unchanged symbol is dropped and counted; the same change twice is one. -> (frame old, new, day; the counts)"""
    csv = csv or M17.wide_paths()["csv"]
    cutt = TS(cut)
    empty = pd.DataFrame({"old": [], "new": [], "day": np.zeros(0, np.int64)})
    if not os.path.exists(csv):
        return empty, {"present": False, "rows": 0}
    need = ["type", "old_symbol", "new_symbol", "ex_date", "process_date"]
    hdr = pd.read_csv(csv, nrows=0)
    miss = [c for c in need if c not in hdr.columns]
    if miss:
        refuse(f"refused: the wide calendar lacks the column(s) {miss} of r16_xgap's flat CSV {TAIL}")
    df = pd.read_csv(csv, dtype=str, keep_default_na=False, usecols=need)
    d = df[df["type"].str.strip() == "name_change"]
    ps, es_ = d["process_date"].str.strip(), d["ex_date"].str.strip()
    pdt = pd.to_datetime(ps.where(ps != ""), errors="coerce")
    exd = pd.to_datetime(es_.where(es_ != ""), errors="coerce")
    ev = pdt.fillna(exd)
    late = ((ev >= cutt) | (exd >= cutt) | (pdt >= cutt)).to_numpy()
    undated = ev.isna().to_numpy()
    old, new = d["old_symbol"].str.strip(), d["new_symbol"].str.strip()
    junk = ((old == "") | (new == "") | (old == new)).to_numpy()
    keep = ~late & ~undated & ~junk
    out = pd.DataFrame({"old": old[keep].to_numpy(), "new": new[keep].to_numpy(), "day": day_i(ev[keep].to_numpy())}).drop_duplicates().sort_values(["day", "new", "old"], kind="mergesort").reset_index(drop=True)
    if len(out):
        assert_cut("wide calendar name changes", pd.DatetimeIndex(out["day"].to_numpy().astype("datetime64[D]")), cut)
    info = {"present": True, "rows": int(len(d)), "dropped_at_the_cut": int(late.sum()), "undated": int((undated & ~late).sum()), "empty_or_unchanged_symbol": int((junk & ~late & ~undated).sum()), "kept": int(len(out)),
            "duplicates_merged": int((keep.sum()) - len(out))}
    return out, info


def exist_spans(D):
    """the span of every cached name: its first and last session with an OPEN print (day numbers) - what 'a cache name held a ticker on a date' is limited to (a name that has not started trading, or has stopped, holds nothing). Read from r5_siporb.Data before it is released"""
    fin = np.isfinite(np.asarray(D.Od))
    T = fin.shape[0]
    di = day_i(D.days)
    any_ = fin.any(axis=0)
    first, last = fin.argmax(axis=0), T - 1 - fin[::-1].argmax(axis=0)
    return {str(s): (int(di[first[j]]), int(di[last[j]])) for j, s in enumerate(D.syms) if any_[j]}


# ------------------------------------------------------------------ [SYMBOLS] the ticker of a cache name on a settlement date: the calendar's name changes walked BACKWARD from the cache's ticker
def ticker_chain(name, by_new, limit=40):
    """the ticker history of the cache name `name` (its cache ticker is the CURRENT one), walked backward through the name changes: the latest change INTO the ticker (the latest process date) gives the date it took it and the ticker it had before; that ticker is looked up the same
    way among the changes strictly before that date. CHOICE: two changes into one ticker on the SAME latest date with different old tickers, or a cycle, end the walk with the history before that date UNKNOWN. -> ([(first day the ticker was held or None = from the beginning, ticker)] newest
    first, known: False when the walk ended in an ambiguity)"""
    segs, cur, bound, seen = [], name, None, set()
    for _ in range(limit):
        cands = [(d, o) for d, o in by_new.get(cur, ()) if bound is None or d < bound]
        if not cands:
            segs.append((None, cur))
            return segs, True
        dmax = max(d for d, _o in cands)
        olds = {o for d, o in cands if d == dmax}
        segs.append((dmax, cur))
        if len(olds) != 1 or (dmax, cur) in seen:
            return segs, False
        seen.add((dmax, cur))
        cur, bound = next(iter(olds)), dmax
    return segs, False


def build_tickers(names, nc, exist, cal_start=None):
    """the ticker histories of the cache names `names` (and the holders of every ticker among ALL cache names in `exist`) -> SimpleNamespace(segs {name: [(start, ticker)]}, known {name: bool}, exist, holders {ticker: [(name, d0, d1)]} only for tickers held by two or more
    names, cal_start_i). A name HOLDS a ticker on the days of its segment that are inside its own span in the cache (exist); 'shared' = two cache names hold one ticker on a common day [SYMBOLS]"""
    by_new = defaultdict(list)
    for o, n, d in zip(nc["old"], nc["new"], nc["day"]):
        by_new[str(n)].append((int(d), str(o)))
    segs, known = {}, {}
    allnames = sorted(set(exist) | set(map(str, names)))
    for nm in allnames:
        segs[nm], known[nm] = ticker_chain(nm, by_new)
    held = defaultdict(list)
    for nm in allnames:
        e0, e1 = exist.get(nm, (None, None))
        if e0 is None:
            continue
        sg = segs[nm]
        for q, (start, tk) in enumerate(sg):
            end = (sg[q - 1][0] - 1) if q > 0 else e1                                  # the next NEWER segment's first day - 1
            d0 = e0 if start is None else max(start, e0)
            d1 = min(end, e1)
            if d0 <= d1:
                held[tk].append((nm, d0, d1))
    holders = {tk: v for tk, v in held.items() if len({n for n, _a, _b in v}) >= 2}
    return SimpleNamespace(segs=segs, known=known, exist=exist, holders=holders, cal_start_i=(None if cal_start is None else int(day_i(cal_start))))


def ticker_at(th, name, day):
    """the ticker of the cache name on the day number `day`: (ticker or None, 'ok' | 'unknown' | 'not_alive'). Outside the name's span in the cache it holds nothing (not_alive); before the calendar's start the renames are not visible (unknown - vacuous for FINRA's 2018+ dates, written as
    the prereg writes it); a walk that ended in an ambiguity is unknown before the date it could not resolve"""
    e = th.exist.get(name)
    if e is None or day < e[0] or day > e[1]:
        return None, "not_alive"
    if th.cal_start_i is not None and day < th.cal_start_i:
        return None, "unknown"
    for start, tk in th.segs[name]:
        if start is None or day >= start:
            return tk, "ok"
    return None, "unknown"


def shared_at(th, name, tk, day):
    """True when another cache name holds the ticker `tk` on `day` (the registered 'held on overlapping dates' rule, on the day of the settlement)"""
    hs = th.holders.get(tk)
    return bool(hs) and any(n != name and a <= day <= b for n, a, b in hs)


# ------------------------------------------------------------------ [K] / [A3] / [A9] the known-at row of every settlement
def settle_table(days_i, fin, lag=None):
    """for every settlement s: row_s = the last session on or before s; u12 = the first session AFTER s + `lag` SESSIONS (row_s + lag + 1); uph = the first session after the photographed release date (0 when there is none); u = the LATER of the two - the first rank row at which the file is
    usable ([A3]: never earlier than a photographed date); a settlement before the first session or whose usable row is past the data's last session is never usable in the data (u = a huge row). binding = which of the two sets u ('s+12' | 'photographed' | 'equal' | 'none')"""
    lag = SPEC["lag"] if lag is None else lag
    T = len(days_i)
    row_s = row_le(days_i, fin.ks)
    u12 = np.where(row_s >= 0, row_s + lag + 1, 10 ** 9)
    uph = np.where(fin.release >= 0, np.searchsorted(days_i, np.where(fin.release >= 0, fin.release, 0), side="right"), 0)
    u = np.maximum(u12, uph)
    u = np.where(u >= T, 10 ** 9, u)
    binding = np.where(u12 > uph, "s+12", np.where(uph > u12, "photographed", "equal"))
    return SimpleNamespace(row_s=row_s, u12=u12, uph=uph, u=u, binding=binding)


def latest_usable(tab, r):
    """the index of the latest settlement usable at the rank close row r (its usable row is on or before r), -1 when none is"""
    ok = np.flatnonzero(tab.u <= r)
    return int(ok.max()) if len(ok) else -1


# ------------------------------------------------------------------ the World's SHORTINT arrays: the FINRA join, the split rows, the share-count machinery of NETISS
def cal_split_rows(W, cal):
    """the calendar's splits (forward / reverse / unit) placed on the World's grid (T, S) bool: the ex-date's session (a date that is not a session moves to the next one; past the data: not placed) - the placement NETISS's split_arrays uses for [A3]'s calendar side"""
    calrow = np.zeros((W.T, W.S), bool)
    sp = None if cal is None else getattr(cal, "split", None)
    if sp is not None and len(sp):
        ci = pd.Index(np.asarray(W.syms).astype(str)).get_indexer(sp["symbol"].astype(str))
        ri = np.searchsorted(day_i(W.days), day_i(pd.DatetimeIndex(sp["ex"])), side="left")
        ok = (ci >= 0) & (ri < W.T)
        calrow[ri[ok], ci[ok]] = True
    return calrow


def f_change_rows(W):
    """the sessions on which the cache's split factor F moves by more than 1% from the previous session's (both finite) - the price side of [A3]"""
    F = np.asarray(W.F, float)
    prev = np.vstack([np.full((1, W.S), np.nan), F[:-1]])
    with np.errstate(invalid="ignore", divide="ignore"):
        ratio = F / prev - 1.0
    return np.isfinite(ratio) & (np.abs(ratio) > NI.SPLIT_TOL)


def attach_shortint(W, fin, assets, nc, exist, fx, mp, cal):
    """everything the scores read besides the World's own arrays -> W.si (and W.ni, NETISS's: the entry tables bound to the sessions, the names' CIKs and static reasons, the [A3] running counts, the calendar's first date): the FINRA table, the asset list's fund tokens (the static [A1] title
    flag), the ticker histories and the holders of every ticker, the settlements' known-at table, every name's span in the cache, the [A3] split rows of the volume window (a calendar split OR an F change: a running count), the CIKs that carry two or more usable map symbols (S1's
    multi-class refusal) and the caches of the join and of the scores"""
    ni = NI.attach_netiss(W, fx, mp, cal)
    di = ni.days_i
    syms = np.asarray(W.syms).astype(str)
    th = build_tickers(syms, nc, exist, ni.cal_start)
    e0 = np.array([th.exist.get(s, (1, 0))[0] for s in syms], np.int64)
    e1 = np.array([th.exist.get(s, (1, 0))[1] for s in syms], np.int64)
    plain = np.array([len(th.segs[s]) == 1 and th.segs[s][0][0] is None for s in syms], bool)
    usable = mp.df[mp.df["usable"]]
    cs = usable.groupby("cik")["symbol"].nunique()
    multi_ciks = set(cs.index[cs > 1])
    cik_of = dict(zip(usable["symbol"], usable["cik"]))
    calrow, fchg = cal_split_rows(W, cal), f_change_rows(W)
    cs_split = np.vstack([np.zeros((1, W.S), np.int32), np.cumsum(calrow | fchg, axis=0, dtype=np.int32)])
    W.si = SimpleNamespace(fin=fin, assets=assets, th=th, tab=settle_table(di, fin), days_i=di, syms=syms, e0=e0, e1=e1, plain=plain, chg_cols=np.flatnonzero(~plain), fund_title=np.array([s in assets.tok for s in syms], bool),
                           multi=np.array([cik_of.get(s, "") in multi_ciks for s in syms], bool), n_multi_ciks=int(len(multi_ciks)), calrow=calrow, fchg=fchg, cs_split=cs_split, mcache={}, scache={}, rcache={})
    return W.si


# ------------------------------------------------------------------ [SYMBOLS] the join: FINRA's symbol at the settlement date against each cache name's ticker on that date
def match_settlement(W, k):
    """settlement k against every column of the World: the ticker of each name on the settlement date (ticker_at; a name outside its span in the cache or with an unresolved history is 'unknown'), then FINRA's rows of that file by symbol. Per name the code M_OK (exactly one row: frow
    = its row in the FINRA table), M_UNKNOWN, M_SHARED (another cache name holds the same ticker on that day - no score), M_NO_ROW, M_DUP (the ticker is listed twice in the file: no row is used - CHOICE: the prereg is silent on a repeated symbol; it counts as 'has a row' for the coverage). -> SimpleNamespace(mcode (S,) int8, frow (S,) int64 (-1 = none), tk (S,) the tickers)"""
    si = W.si
    got = si.mcache.get(k)
    if got is not None:
        return got
    fin, th, S_ = si.fin, si.th, W.S
    s_day = int(fin.ks[k])
    a, b = int(fin.off[k]), int(fin.off[k + 1])
    alive = (si.e0 <= s_day) & (s_day <= si.e1)
    tk = np.where(alive, si.syms, "\x00").astype(object)
    unknown = np.zeros(S_, bool)
    if th.cal_start_i is not None and s_day < th.cal_start_i:
        unknown[alive] = True
    else:
        for j in si.chg_cols:
            if alive[j]:
                t_, st = ticker_at(th, str(si.syms[j]), s_day)
                if t_ is None:
                    unknown[j] = True
                else:
                    tk[j] = t_
    cand = alive & ~unknown
    syms_k = fin.symtab[fin.symc[a:b]]
    rows_k = np.arange(a, b)
    dupm = pd.Series(syms_k).duplicated(keep=False).to_numpy() if b > a else np.zeros(0, bool)
    uix = pd.Index(syms_k[~dupm])
    pos = uix.get_indexer(np.where(cand, tk, "\x00"))
    mcode = np.full(S_, M_NO_ROW, np.int8)
    mcode[~alive | unknown] = M_UNKNOWN
    frow = np.full(S_, -1, np.int64)
    hit = cand & (pos >= 0)
    mcode[hit] = M_OK
    frow[hit] = rows_k[~dupm][pos[hit]]
    if dupm.any():
        isdup = cand & np.isin(tk, np.array(sorted(set(syms_k[dupm].tolist())), dtype=object))
        mcode[isdup] = M_DUP
        frow[isdup] = -1
    if th.holders:
        for j in np.flatnonzero(cand & np.isin(tk, np.array(sorted(th.holders), dtype=object))):
            if shared_at(th, str(si.syms[j]), tk[j], s_day):
                mcode[j] = M_SHARED
                frow[j] = -1
    out = SimpleNamespace(mcode=mcode, frow=frow, tk=tk)
    si.mcache[k] = out
    return out


# ------------------------------------------------------------------ S(s*): the point-in-time share count of NETISS's rules, read at the settlement date
def latest_entry(ent, r, cn):
    """per name (cn = a CIK index, -1 = none): the index of the USABLE entry of one concept with the latest as-of date known at row r (an entry is usable at r when its first filed date's next session is on or before r: ent.urow <= r; an ambiguous / missing / typo-year one is never
    a candidate) - NETISS's S(r) of pairs_for_concept without its S' - or -1"""
    s = np.full(len(cn), -1, np.int64)
    ui = np.flatnonzero(ent.ok & (ent.urow <= r))
    if not len(ui) or not (cn >= 0).any():
        return s
    ck = ent.ck[ui]
    last = np.r_[ck[1:] != ck[:-1], True]
    s_of = np.full(int(ck.max()) + 1, -1, np.int64)
    s_of[ck[last]] = ui[last]
    has_c = (cn >= 0) & (cn <= int(ck.max()))
    return np.where(has_c, s_of[np.where(has_c, cn, 0)], -1)


# ------------------------------------------------------------------ the scores of one settlement: D1 and S1 of every column, the first reason a name has none
def settlement_scores(W, k, rev_mode="drop"):
    """the two scores of every column of the World at the settlement s = fin.ks[k], read at the session of s (the information set at s*: S(s*) is the share count known then). The FIRST failing rule is the name's no-score reason, in this order. Shared: the asset-list fund title [A1],
    the join (ticker unknown / shared / no row / listed twice), the FINRA issue name's fund tokens [A1], FINRA's revision flag [A11] (rev_mode 'drop' = the registered reading; 'asis' = the REPORTED twin scores those rows as they stand), short interest missing or negative (SI = 0 is a score).
    D1 = SI / ADV: ADV = the mean RAW daily share volume of the SPEC['adv_n'] sessions ending at s with at least SPEC['adv_min'] present; a split (the calendar's or an F change - a running count) on any of those sessions, FIRST session included (CHOICE: inclusive), gives no score;
    ADV not positive none. S1 = SI / (S x F(a) / F(s)): the static map reasons, a CIK that carries two or more map symbols (CHOICE: a firm's share count against ONE class's short interest), no share fact known at s (the cover page, else the balance sheet - NETISS's concept order; the
    concept stands when it has any usable entry), the count not positive, its as-of date a more than SPEC['stale'] days before s, no split factor on a date, [A3]'s two-way split check between a and s (where the calendar covers a). The scale rule is the RANK's (score_rank). Cached by (k, rev_mode)"""
    si = W.si
    key = (k, rev_mode)
    got = si.scache.get(key)
    if got is not None:
        return got
    fin, ni, S_ = si.fin, W.ni, W.S
    m = match_settlement(W, k)
    isr, s_day = int(si.tab.row_s[k]), int(fin.ks[k])
    j_ = np.arange(S_)
    fr = np.maximum(m.frow, 0)
    has = m.frow >= 0
    fund_name = has & fin.fnd[fr]
    rev = has & fin.rev[fr]
    sival = np.where(has, fin.si[fr], np.nan)
    code0, alive0 = np.zeros(S_, np.int8), np.ones(S_, bool)

    def drop(code, alive, mask, reason):
        hit = alive & mask
        code[hit] = reason
        alive[hit] = False
    drop(code0, alive0, si.fund_title, R_FUND_TITLE)
    drop(code0, alive0, m.mcode == M_UNKNOWN, R_TICKER_UNKNOWN)
    drop(code0, alive0, m.mcode == M_SHARED, R_TICKER_SHARED)
    drop(code0, alive0, m.mcode == M_NO_ROW, R_NO_ROW)
    drop(code0, alive0, m.mcode == M_DUP, R_DUP_ROWS)
    drop(code0, alive0, fund_name, R_FUND_NAME)
    if rev_mode == "drop":
        drop(code0, alive0, rev, R_REVISED)
    with np.errstate(invalid="ignore"):
        drop(code0, alive0, ~(sival >= 0), R_SI_MISSING)
    # D1
    lo_r = max(isr - SPEC["adv_n"] + 1, 0)
    win = np.asarray(W.Vv, float)[lo_r:isr + 1]
    fw = np.isfinite(win)
    n_pres = fw.sum(axis=0)
    with np.errstate(invalid="ignore", divide="ignore"):
        adv = np.where(n_pres >= SPEC["adv_min"], np.where(fw, win, 0.0).sum(axis=0) / np.maximum(n_pres, 1), np.nan)               # ADV is defined only on at least adv_min sessions (it is also the tie-break of both cells)
    split_win = (si.cs_split[isr + 1] - si.cs_split[lo_r]) > 0
    code1, alive1 = code0.copy(), alive0.copy()
    drop(code1, alive1, n_pres < SPEC["adv_min"], R_ADV_FEW)
    drop(code1, alive1, split_win, R_SPLIT_WINDOW)
    with np.errstate(invalid="ignore", divide="ignore"):
        drop(code1, alive1, ~(adv > 0), R_ADV_ZERO)
        d1 = np.where(alive1, sival / adv, np.nan)
    # S1
    code2, alive2 = code0.copy(), alive0.copy()
    for nm, mine in STATIC_OF.items():
        drop(code2, alive2, ni.static == NI.REASONS.index(nm), mine)
    drop(code2, alive2, si.multi, R_MULTI_CLASS)
    cnn = np.where(alive2, ni.cik_ix, -1)
    s_d, s_g = latest_entry(ni.dei, isr, cnn), latest_entry(ni.gaap, isr, cnn)
    sg = np.where(s_d >= 0, s_d + ni.off["dei"], np.where(s_g >= 0, s_g + ni.off["gaap"], -1))
    drop(code2, alive2, sg < 0, R_NO_FACT)
    sgc = np.maximum(sg, 0)
    Sv, a_day = ni.E_val[sgc], ni.E_end[sgc]
    with np.errstate(invalid="ignore"):
        drop(code2, alive2, ~(Sv > 0), R_NOT_POS)
    age_s = s_day - a_day
    drop(code2, alive2, age_s > SPEC["stale"], R_STALE)
    ia = row_le(si.days_i, a_day)
    ia0 = np.maximum(ia, 0)
    F = np.asarray(W.F, float)
    fa, fs = F[ia0, j_], F[isr]
    with np.errstate(invalid="ignore"):
        drop(code2, alive2, ~(np.isfinite(fa) & np.isfinite(fs) & (fa > 0) & (fs > 0) & (ia >= 0)), R_NO_FACTOR)
    covered = (ni.cal_start_i is not None) & (a_day >= (ni.cal_start_i if ni.cal_start_i is not None else 0))
    unC, unF = ni.cs_unC[isr + 1] - ni.cs_unC[ia0 + 1, j_], ni.cs_unF[isr + 1] - ni.cs_unF[ia0 + 1, j_]
    drop(code2, alive2, covered & (unC > 0), R_SPLIT_C)
    drop(code2, alive2, covered & (unF > 0), R_SPLIT_F)
    with np.errstate(invalid="ignore", divide="ignore"):
        Scar = Sv * fa / fs
        s1 = np.where(alive2, sival / Scar, np.nan)
    out = SimpleNamespace(k=k, s_day=s_day, row_s=isr, mcode=m.mcode, frow=m.frow, tk=m.tk, fund_name=fund_name, rev=rev, si=sival, adv=adv, n_pres=n_pres, split_win=split_win, d1=d1, d1_code=code1, s1=s1, s1_code=code2, sg=sg, a_day=a_day, age_s=age_s, fa=fa, fs=fs, Scar=Scar,
                          zero_si=has & (sival == 0), spl_flag=has & fin.spl[fr], fin_dtc=np.where(has, fin.dtc[fr], np.nan), fin_adv=np.where(has, fin.adv[fr], np.nan), fin_psi=np.where(has, fin.psi[fr], np.nan), covered_a3=covered)
    si.scache[key] = out
    return out


# ------------------------------------------------------------------ one rank: the latest usable settlement, the universe (funds out), the coverage [A2], the scale rule, the two score vectors
def score_rank(W, r, rev_mode="drop"):
    """the SHORTINT score of every column at the rank close row r. s* = the LATEST settlement usable at r ([K] / [A3]: the later of s + 12 sessions and the photographed date, then the next session); none = every name has the no-score reason 'no usable file' and the rank trades nothing.
    The rank's UNIVERSE = the fill session's universe less the asset-list funds [A1] and, among the names that have a FINRA row, those whose issue name carries a fund token [A1] (out of the universe, the coverage and the null's pool). COVERAGE [A2] = the share of that universe that has a
    FINRA row in the file (CHOICE: the join's M_OK or M_DUP - a name whose ticker is unknown / shared / absent has none); a rank below SPEC['cover'] trades nothing (covered False). The S1 SCALE RULE: |ln(S1 / the median S1 of the rank)| > ln(1000) gives no score (CHOICE: the median is over the universe names with S1 > 0 before this rule; S1 = 0 is exempt,
    SI = 0 being a score). -> SimpleNamespace(r, f, k, s_day, age (sessions), uni, in_uni, n_uni0, n_title, n_name, mc (counts of the join among the universe less the title funds), n_cov, cov, covered, d1, d1_code, s1, s1_code, adv, + the settlement's own arrays)"""
    si = W.si
    key = (r, rev_mode)
    got = si.rcache.get(key)
    if got is not None:
        return got
    S_, f = W.S, r + 1
    uni0 = np.flatnonzero(W.U[f]) if f < W.T else np.zeros(0, np.int64)
    k = latest_usable(si.tab, r)
    title = si.fund_title[uni0]
    out = SimpleNamespace(r=r, f=f, k=k, s_day=-1, age=-1, n_uni0=int(len(uni0)), n_title=int(title.sum()), n_name=0, mc={}, n_cov=0, cov=float("nan"), covered=False, n_uni=0, s1_median=float("nan"))
    in_uni = np.zeros(S_, bool)
    if k < 0:
        in_uni[uni0] = ~title
        z = np.full(S_, np.nan)
        code = np.full(S_, R_NO_FILE, np.int8)
        code[si.fund_title] = R_FUND_TITLE
        out.__dict__.update(in_uni=in_uni, uni=np.flatnonzero(in_uni), n_uni=int(in_uni.sum()), d1=z, d1_code=code, s1=z, s1_code=code.copy(), adv=z, sc=None, zero_si=np.zeros(S_, bool), n_pres=np.zeros(S_, int), a_day=np.zeros(S_, np.int64), age_s=np.zeros(S_, np.int64))
        si.rcache[key] = out
        return out
    sc = settlement_scores(W, k, rev_mode)
    nm = sc.fund_name & (sc.mcode == M_OK)
    in_uni[uni0] = (~title & ~nm[uni0])
    uni = np.flatnonzero(in_uni)
    after_title = uni0[~title]
    out.mc = {c: int((sc.mcode[after_title] == q).sum()) for c, q in (("ok", M_OK), ("unknown", M_UNKNOWN), ("shared", M_SHARED), ("no_row", M_NO_ROW), ("duplicate", M_DUP))}
    out.n_name = int(nm[after_title].sum())
    covd = np.isin(sc.mcode[uni], (M_OK, M_DUP))
    out.n_cov, out.n_uni = int(covd.sum()), int(len(uni))
    out.cov = out.n_cov / out.n_uni if out.n_uni else float("nan")
    out.covered = bool(out.n_uni > 0 and out.cov >= SPEC["cover"] - 1e-12)
    s1c, s1 = sc.s1_code.copy(), sc.s1.copy()
    pos_ = uni[(s1c[uni] == R_SCORED) & (s1[uni] > 0)]
    if len(pos_):
        out.s1_median = float(np.median(s1[pos_]))
        with np.errstate(invalid="ignore", divide="ignore"):
            err = np.abs(np.log(s1[pos_] / out.s1_median)) > LN1000
        s1c[pos_[err]] = R_SCALE
        s1[pos_[err]] = np.nan
    out.__dict__.update(s_day=sc.s_day, age=int(r - sc.row_s), in_uni=in_uni, uni=uni, d1=sc.d1, d1_code=sc.d1_code, s1=s1, s1_code=s1c, adv=sc.adv, n_pres=sc.n_pres, zero_si=sc.zero_si, a_day=sc.a_day, age_s=sc.age_s, sc=sc)
    si.rcache[key] = out
    return out


def cell_score(sc, cell):
    """the cell's score vector and reason codes of a rank record (D1 / S1)"""
    return (sc.d1, sc.d1_code) if cell == "D1" else (sc.s1, sc.s1_code)


# ------------------------------------------------------------------ the sides: the 50 lowest D1 / S1 long, the 50 highest short; fewer than 150 scored names -> the bottom / top third, at least 20 a side, else nothing
def side_n(n):
    """the number of names a side holds when n names are scored: 50 at 150 or more; fewer: the top / bottom THIRD (CHOICE, NETISS's reading: n // 3 a side, so the sides never touch) when that is at least 20, else nothing -> (names a side, 'top' | 'third' | 'none')"""
    if n >= SPEC["min_scored"]:
        return M17.SPEC["n_side"], "top"
    k = n // 3
    return (k, "third") if k >= SPEC["min_side"] else (0, "none")


def pick_sides(cols, score, adv, k):
    """the k longs and k shorts among the scored names (positions into the arrays given): the shorts the k HIGHEST scores, the longs the k LOWEST; ties at a cut are broken by the name's ADV, HIGHEST first (the cheapest to trade; a name without a positive ADV last), then by the lower
    World column (CHOICE: symbol order - the prereg stops at ADV). CHOICE: the short side is picked first and the long side among the names it left, so the sides never share a name (they cannot when 2k <= n unless every score ties). -> (long positions, short positions)"""
    cols, sc = np.asarray(cols), np.asarray(score, float)
    ad = np.where(np.isfinite(adv) & (np.asarray(adv, float) > 0), np.asarray(adv, float), -np.inf)
    shorts = np.lexsort((cols, -ad, -sc))[:k]
    rest = np.setdiff1d(np.arange(len(sc)), shorts)
    longs = rest[np.lexsort((cols[rest], -ad[rest], sc[rest]))][:k]
    return longs, shorts


def cell0():
    """an empty cell record of a rebalance: idx = the scored names among the pool (positions into rec.pool), score / adv = their score and ADV, k / mode = the side size and what the month trades (MODES), long / short = the picks (positions into idx), U = the unit paths of the scored names"""
    z = np.zeros(0, np.int64)
    return SimpleNamespace(idx=z, score=np.zeros(0), adv=np.zeros(0), n=0, k=0, mode="none", traded=False, long=z, short=z, U=None)


# ------------------------------------------------------------------ one rebalance: RESMOM's pool (as NETISS's), the SHORTINT scores, the picks
def si_one(W, r, f, x, post_mode, rev_mode="drop", units=True, counts_only=False):
    """one rebalance: the universe at the fill session f (sessions < f only) less the [A1] funds, and the pool of r17_resmom's rm_one - the same removals in the same order (short history, no ES pairs, no fill, the pre / old / post hygiene windows, the [D2] spin-offs, the hand audit;
    CHOICE (NETISS's): RESMOM's 'no score' is gone - a name's score exists per cell, so the pool is common to both cells and each cell's scored names are the pool names with a score). A rank with no usable settlement ('nofile') or whose universe is covered under 90% by it ('uncovered')
    trades nothing in either cell; otherwise both sides are 50 names at 150 or more scored names, else the bottom / top third (at least 20 a side) or nothing (side_n); the 50 LOWEST are the longs, the 50 HIGHEST the shorts, ties by ADV (pick_sides). post_mode as r17_resmom's ('remove' = the
    registered reading, 'naive' = the look-ahead one); rev_mode 'drop' / 'asis' as settlement_scores. counts_only: no unit path, no pick - the pools and the scored sets are counted (the dryload)"""
    s = M17.SPEC
    sc = score_rank(W, r, rev_mode)
    uni = sc.uni
    rec = SimpleNamespace(r=r, f=f, x=x, nu=len(uni), nfull=0, traded=False, pool=np.zeros(0, np.int64), naive=np.zeros(0, bool), spin_win=np.zeros(0, np.int64), spin_hold=np.zeros(0, bool), cell={c: cell0() for c in CELLS}, sc=sc, U=None)
    cnt = Counter()
    cnt["rebalances"] += 1
    cnt["universe"] += len(uni)
    cnt["funds_title"] += sc.n_title
    cnt["funds_name"] += sc.n_name
    cnt["rank_" + ("nofile" if sc.k < 0 else "covered" if sc.covered else "uncovered")] += 1
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
    win = (W.SPN[a:r + 1][:, uni] & np.isfinite(W.Rn[a:r + 1][:, uni])).sum(axis=0)
    pre_any, old_any, post_any = pre.any(axis=0), old.any(axis=0), post.any(axis=0) | post_sp
    aud = W.aud1[f, uni]
    W.aud_hit.update((AUD, f, int(c)) for c in uni[aud])
    reasons = [("short_history", short_hist), ("no_es_pairs", no_es), ("no_fill", ~m_fill)]
    reasons += [(f"pre_{h}", pre[q]) for q, h in enumerate(HYG)] + [(f"old_{h}", old[q]) for q, h in enumerate(HYG[1:])]
    if post_mode == "remove":
        reasons += [(f"post_{h}", post[q]) for q, h in enumerate(HYG)] + [("post_spin", post_sp)]
    D15.tally(cnt, reasons + [("audit", aud)], D15.attribute(reasons + [("audit", aud)], len(uni)))
    cnt["spin_window_names"] += int((win > 0).sum())
    cnt["spin_window_sessions"] += int(win.sum())
    cnt["spin_hold_names"] += int(post_sp.sum())
    pool_k = ~short_hist & ~no_es & m_fill & ~pre_any & ~old_any & ~aud
    pool = (pool_k & ~post_any) if post_mode == "remove" else pool_k
    if post_mode == "naive":
        cnt["kept_naive"] += int((pool & post_any).sum())
    pidx = np.flatnonzero(pool)
    cols = uni[pidx]
    rec.pool = cols
    rec.naive = post_any[pidx] if post_mode == "naive" else np.zeros(len(pidx), bool)
    rec.spin_win, rec.spin_hold = win[pidx], post_sp[pidx]
    stop = "nofile" if sc.k < 0 else (None if sc.covered else "uncovered")
    for c in CELLS:
        cc = rec.cell[c]
        if not len(cols):
            cnt[f"mode_{c}_none"] += 1                                          # an empty pool trades nothing (counted with the other fallback months)
            continue
        score, code = cell_score(sc, c)
        sv = score[cols]
        idx = np.flatnonzero(np.isfinite(sv))
        cc.idx, cc.n, cc.score, cc.adv = idx, int(len(idx)), sv[idx], np.asarray(sc.adv, float)[cols][idx]
        cnt[f"scored_{c}"] += cc.n
        cnt[f"no_score_{c}"] += int(len(cols) - cc.n)
        for q in range(1, len(REASONS)):
            cnt[f"ns_{c}_{REASONS[q]}"] += int((code[cols] == q).sum())
        cc.k, cc.mode = (0, stop) if stop is not None else side_n(cc.n)
        cnt[f"mode_{c}_{cc.mode}"] += 1
        if counts_only:
            cc.traded = cc.k > 0
            continue
        if cc.k > 0:
            cc.long, cc.short = pick_sides(cols[idx], cc.score, cc.adv, cc.k)       # the k lowest are the longs, the k highest the shorts
            cc.traded = True
    rec.traded = any(rec.cell[c].traded for c in CELLS)
    if units and len(cols) and any(rec.cell[c].traded for c in CELLS):
        rec.U = M17.rm_units(W, f, x, rec.pool, rec.naive)
        for c in CELLS:
            if rec.cell[c].traded:
                rec.cell[c].U = NI.slice_units(rec.U, rec.cell[c].idx)
    return rec, cnt


def si_build(W, lo, hi, post_mode="remove", rev_mode="drop", units=True, counts_only=False):
    """every rebalance whose position EXITS inside [lo, hi] with a full 252-session window (r17_resmom.rm_build's rules: the stretch by exit session, warm-up counted, a position whose exit is past the stage's data unresolved - out of the cell AND the null) -> Leg(kind, recs, cnt by fill year)"""
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
        rec, c = si_one(W, r, f, x, post_mode, rev_mode, units, counts_only)
        recs.append(rec)
        cnt[y].update(c)
    return SimpleNamespace(kind="SI", recs=recs, cnt=cnt)


cell_leg = NI.cell_leg                                                         # one cell's view of a Leg in the shape r15's L1 engine reads (NETISS's: sig = the score on ITS scored pool)
built_ranks = NI.built_ranks                                                   # every rebalance whose position exits inside [lo, hi] with a full window -> [(r, f, x)]


def si_null(W, L, nreps, vcode=0):
    """the family-aware null [prereg NULL]: NETISS's ni_null on this family's cells and seed - per draw and per rebalance the cell traded, its k longs and k shorts are replaced by the same number of names drawn uniformly without replacement from that rebalance's eligible SCORED pool
    (the universe less the funds [A1], the pool's hygiene, the cell's own scored names; the same sizing, fills, costs, borrow); each cell has its own random stream (seeds [20261018, cell, vcode]), so the MAX over the 2 cells is the better of two independent random books"""
    with patched(NI, CELLS=CELLS, SEED=SEED):
        return NI.ni_null(W, L, nreps, vcode)


def null_summary(per_cell, per_cell_do=None):
    """per_cell {cell: ROC @ $30k of every draw} -> the statistic = the MAX over the 2 cells per draw -> p5 / p50 / p95 (and each cell's own); per_cell_do the same for the DO against the REFERENCE book's drawdown days (MANAGER #70's gate basis)"""
    with patched(NI, CELLS=CELLS):
        return NI.null_summary(per_cell, per_cell_do, SEED)


# ------------------------------------------------------------------ the stretch: starts at the first rank at or above 90% coverage [A2]; every book number is computed on THIS stretch
def coverage_rows(W, ranks, rev_mode="drop"):
    """per built rank (r, f, x): the rank record's coverage facts [A2] - the date, the latest usable settlement and its age in sessions, the universe less the funds, the names with a FINRA row, the share, whether the rank is at or above SPEC['cover'] -> [dict]"""
    rows = []
    for r, f, x in ranks:
        sc = score_rank(W, r, rev_mode)
        rows.append({"rank": f"{W.days[r]:%Y-%m-%d}", "year": int(W.days[f].year), "fill": f"{W.days[f]:%Y-%m-%d}", "k": int(sc.k), "settlement": ("-" if sc.k < 0 else f"{np.datetime64(int(sc.s_day), 'D')}"), "age_sessions": int(sc.age),
                     "universe_before_funds": int(sc.n_uni0), "funds_by_title": int(sc.n_title), "funds_by_finra_name": int(sc.n_name), "universe": int(sc.n_uni), "with_a_row": int(sc.n_cov), "coverage": float(sc.cov), "covered": bool(sc.covered), "join": dict(sc.mc)})
    return rows


def wf_start(W, ranks, rev_mode="drop"):
    """[A2] the walk-forward starts at the FIRST rank at or above 90% (printed): -> (the rank's row r or None, the stretch's first row lo = the date of its FILL session, never before WF0, or None). A rank below 90% AFTER that start stays in the stretch, trades nothing and is listed
    (CHOICE: the stretch is contiguous from its start)"""
    for r, f, x in ranks:
        if score_rank(W, r, rev_mode).covered:
            return r, max(W.days[f], WF0)
    return None, None


def restretch(B, ref, lo, hi):
    """the reference book L on the stretch [lo, hi] (a sub-stretch of its registered WF): the same raw series, r12_mdl.Stretch (drawdown episodes with the peak starting at 0 at the stretch's start, the DD days of the qualifying ones), r11_risk.stats, the structure - what 'EVERY book number is
    computed on THIS stretch' needs. The registered full-WF numbers are checked on the full WF by r18_divrun.ref_load before this runs"""
    k = np.flatnonzero(B.mask(lo, hi))
    S_ = M12.Stretch(ref.raw, B.index, None, lo, hi)
    d = dict(ref.__dict__)
    d.update(S=S_, stats=R11.stats(np.asarray(ref.raw, float)[k], B.index[k]), structure=DV.ref_structure(S_), rows=k, lo=lo, hi=hi)
    return SimpleNamespace(**d)


def make_ctx(B, S12_full, ref, lo, hi=None):
    """what one stage needs about the stretch: lo / hi, #463's Stretch on it (S12), L's re-stretched record (ref; ref_full = the registered WF's), the years of the July-June breadth"""
    hi = PRE_END if hi is None else hi
    return SimpleNamespace(lo=lo, hi=hi, S12=M12.Stretch(B.raw, B.index, None, lo, hi), S12_full=S12_full, ref=restretch(B, ref, lo, hi), ref_full=ref, years=YEARS, n_years=len(YEARS))


def stat_run(B, rows, run, lo, hi):
    """r15's cell statistics on the stretch [lo, hi] of a run's daily series, the seven July-June years -> (stats, the series on #463's index, the positions held per row)"""
    xB, cB = D15.to_B(run.x, rows, B.n), D15.to_B(run.cnt, rows, B.n)
    return D15.cell_stats(B, xB, cB, lo, hi, run, years=YEARS), xB, cB


def years_held(B, cB, lo, hi):
    """the July-June WF years in which the cell holds a position on at least one day"""
    k = B.mask(lo, hi)
    c = np.asarray(cB)[k]
    return sorted({int(y) for y, v in zip(jyear(B.index[k]), c) if v > 0})


def judge_cell(st, net10, net3, nul, n_years):
    """(a) >= 60 monthly rebalances; (b) WF ROC @ $30k >= 15, net > 0 at 5 AND at 10 bps a side AND with the flat 3%/yr borrow on every short; (c) WF ROC above the null's 95th percentile (the max over the 2 cells); (d) positive in at least TWO THIRDS of the n_years July-June WF years, rounded
    up (5 of the 7), and net > 0 without Feb 15 - Apr 30 2020; (e) profitable without its best 1% of days AND without its best 1% of name-months. (f), the hand audit, is separate (the lead's). A NaN fails every comparison it enters"""
    R = RULES
    need = -(-2 * int(n_years) // 3)
    chk = {f"rebalances>={R['reb']}": st["n_units"] >= R["reb"], f"ROC>={R['roc']:g}": st["roc"] >= R["roc"], "net>0 at 5 bps": (st["net"] > 0) if R["net_pos"] else True,
           "net>0 at 10 bps": (net10 > 0) if R["stress"] else True, "net>0 with the flat 3% borrow": (net3 > 0) if R["stress"] else True, "ROC>null p95": (st["roc"] > nul["roc_max"]["p95"]) if R["null"] else True,
           f"positive in >={need} of {int(n_years)} July-June years": st["years_pos"] >= need, "net>0 without Feb 15 - Apr 30 2020": (st["net_ex2020"] > 0) if R["ex2020"] else True,
           "profitable without its best 1% of days": (st["net_ex_best_days"] > 0) if R["exbest"] else True,
           "profitable without its best 1% of name-months": (st["net_ex_best_pos"] > 0) if R["exbest"] else True}
    return {k: bool(v) for k, v in chk.items()}


def a2_window(lo):
    """A2's window for c: the cell's first two years of the stretch, lo .. lo + 2 years - 1 day (2018-08-01 .. 2020-07-31 when the stretch starts 2018-08-01; CHOICE: it moves with the stretch's start)"""
    return lo, lo + pd.DateOffset(years=A2_YEARS) - pd.Timedelta(days=1)


def a2_report(B, xB, ref, lo, hi):
    """STAGE A2 (WF) - a REPORT, never a pass route: the REFERENCE book L (#463 + 0.264 x RES) + c x the cell against L ON THIS STRETCH, c by VOLATILITY on the cell's first two years (25% of #463's daily std over those rows / the cell's), 0.5c and 2c reported, the plain #463 + c x the cell a
    reported row; an incremental pass = ROC @ $30k and Sortino both strictly above L's on the stretch. r18_divrun's a2_report with its window, its ROC / Sortino reads and r15's a2_cell pointed at the stretch (module globals patched for the call and restored); the dollars a year (net / years)
    beside every ROC"""
    win = a2_window(lo)
    at_fn = DV.ref_at
    at_s = lambda B_, ref_, xB_, c_, lo_=lo, hi_=hi: at_fn(B_, ref_, xB_, c_, lo_, hi_)
    with patched(D15, WF0=lo, PRE_END=hi), patched(DV, A2_WIN=win, A2_TARGET=A2_TARGET, A2_REPORT=A2_REPORT, ref_at=at_s):
        a = DV.a2_report(B, xB, ref)
    yrs = float(ref.stats["years"])
    a["reference"]["usd_year"] = NI.per_year(a["reference"]["net"], yrs)
    for key in ("at_half_c", "at_double_c"):
        if a.get(key):
            a[key]["usd_year"] = NI.per_year(a[key]["net"], yrs)
    if np.isfinite(a.get("net", float("nan"))):
        a["usd_year"] = NI.per_year(a["net"], yrs)
    pl = a.get("plain_463") or {}
    if np.isfinite(pl.get("net", float("nan"))):
        pl["usd_year"] = NI.per_year(pl["net"], yrs)
    return a


def plain_a2(B, xB, lo, hi):
    """the registered volatility rule for c (r18_divrun's plain_a2) on the cell's window of the stretch; Stage B recomputes the frozen c with it"""
    with patched(D15, WF0=lo, PRE_END=hi), patched(DV, A2_WIN=a2_window(lo), A2_TARGET=A2_TARGET, A2_REPORT=A2_REPORT):
        return DV.plain_a2(B, xB)


def beta_credit(B, ctx, W, rows, xB):
    """the cell's realised beta to ES (its daily $ P&L on ES's daily return, per $ of ONE SIDE's notional = n_side x slot) on L's drawdown days (R's days: the reference book's drawdown set on this stretch) and on every day of the stretch, and whether the cell may be CREDITED: BOTH betas
    within +-0.20 (NETISS's reading of 'a cell with |realised beta| > 0.20'); a beta that cannot be computed refuses the credit. A cell without credit has its drawdown-day profile REPORTED but gets no incremental A2 pass, no gate, no line. r21_netiss's rule on L's Stretch"""
    return NI.beta_credit(B, ctx.ref.S, W, rows, xB)


def breakeven_fee(net0, net_hi, rate_hi):
    """the flat borrow rate at which the cell's net is zero: net is exactly linear in the flat rate (the borrow is rate / 252 x the prior close's mark on every short session), so the line through (0, net0) and (rate_hi, net_hi) crosses zero at rate_hi x net0 / (net0 - net_hi); NaN when the borrow does
    not reduce net (no short session) and 0.0 when the cell already loses with no borrow"""
    if not (np.isfinite(net0) and np.isfinite(net_hi)):
        return float("nan")
    if net0 <= 0:
        return 0.0
    return float(rate_hi * net0 / (net0 - net_hi)) if net0 > net_hi else float("nan")


def pick_candidate(cells, passing):
    """CHOICE (NETISS's): the passing cell with the higher WF standalone ROC @ $30k goes to Stage B (ties: D1 first); the other is reported"""
    return max(passing, key=lambda c: (cells[c]["base"]["roc"], -CELLS.index(c))) if passing else None


def stage_a_flow(cells):
    """Stage A's bookkeeping, pure: passing = the cells that clear (a) - (e); the candidate = pick_candidate(passing). (f), the hand audit, is NEVER decided here - every passing cell 'awaits the hand audit', and Stage B needs the lead's go-flag"""
    passing = [c for c in CELLS if cells[c]["PASS"]]
    return passing, pick_candidate(cells, passing)


# ------------------------------------------------------------------ one reading of Stage A: legs -> the NULL FIRST [A6] -> cells -> stress rows -> checks -> A2
def evaluate(W, B, rows, ctx, post_mode, nreps, vcode=0, full=False, rev_mode="drop", announce=None):
    """one reading of Stage A on the stretch ctx.lo .. ctx.hi. post_mode 'remove' = the REGISTERED reading (a hygiene flag inside the hold removes the position before the ranking), 'naive' = the look-ahead one; rev_mode 'drop' = the registered reading of FINRA's revised rows, 'asis' = the
    REPORTED twin. nreps > 0 draws the registered null (random names from the scored pool; vcode picks its random streams) BEFORE any cell's P&L is computed and hands it to `announce` (the power line is printed first [A6]), then judges (a) - (e); full = also the reports' rows (the sides apart,
    k > 1.5 borrow stress, -100% / shorts at zero, the regime halves, the ES-hedged twin). -> (summary, objects: the leg, each cell's leg view / base run / series / side series)"""
    lo, hi = ctx.lo, ctx.hi
    L = si_build(W, WF0, PRE_END, post_mode, rev_mode)
    legs = {c: cell_leg(L, c) for c in CELLS}
    nul = None
    if nreps:
        acc = si_null(W, L, nreps, vcode)
        pc, pdo = {}, {}
        for cell in CELLS:
            pc[cell], pdo[cell] = DV.null_stats(ctx.S12, ctx.ref.S, acc[cell], rows, B.n)
        nul = null_summary(pc, pdo)
        if announce is not None:
            announce(nul, L)
    runs, series, side_x, summ = {}, {}, {}, {}
    for cell in CELLS:
        CL = legs[cell]
        base = M17.run_cell(W, CL, D15.l1_cfg(), pos=True)
        st, xB, cB = stat_run(B, rows, base, lo, hi)
        runs[cell], series[cell] = base, (xB, cB)
        at = lambda cfg, CL=CL, **kw: stat_run(B, rows, M17.run_cell(W, CL, cfg, **kw), lo, hi)[0]
        curve = {r_: at(D15.l1_cfg(borrow=(r_, None))) for r_ in BORROW_CURVE}
        c = {"base": st, "cost0": at(D15.l1_cfg(bps=0.0)), "stress": {f"{b:g} bps": at(D15.l1_cfg(bps=b)) for b in STRESS_BPS}, "borrow_flat": curve[BORROW_FLAT], "borrow_curve": {f"{r_:g}": v for r_, v in curve.items()},
             "breakeven_fee": breakeven_fee(curve[0.0]["net"], curve[BORROW_FLAT]["net"], BORROW_FLAT), "seat": D15.seat_measure(ctx.S12, xB), "seat_ref": D15.seat_measure(ctx.ref.S, xB), "years_held": years_held(B, cB, lo, hi),
             "A2": a2_report(B, xB, ctx.ref, lo, hi), "beta": beta_credit(B, ctx, W, rows, xB)}
        c["usd_year"] = NI.per_year(st["net"], st["years"])
        c["episode_pnl"] = [float(e["cell_pnl"]) for e in D15.episodes_table(ctx.ref.S, xB)]
        c["A2"]["credited"] = bool(c["beta"]["within_cap"])
        c["A2"]["incremental_credit"] = bool(c["A2"]["incremental_pass"] and c["beta"]["within_cap"])
        if full:
            c["sides"] = {}
            for nm, sd in (("long side only", 1), ("short side only", -1)):
                s_, sx, _ = stat_run(B, rows, M17.run_cell(W, CL, D15.l1_cfg(), side=sd), lo, hi)
                c["sides"][nm] = s_
                side_x.setdefault(cell, {})[sd] = sx
            ex = {f"borrow {BORROW_STRESS[0]:.0%} on k>1.5 sessions": D15.l1_cfg(borrow=(BORROW, BORROW_STRESS[0])), f"borrow {BORROW_STRESS[1]:.0%} on k>1.5 sessions": D15.l1_cfg(borrow=(BORROW, BORROW_STRESS[1])),
                  "longs that stop printing valued at -100%": D15.l1_cfg(lose100=True)}
            c["extra"] = {nm: at(cfg) for nm, cfg in ex.items()}
            z0 = {**D15.l1_cfg(), "short0": True}                                         # [R2] r17_resmom's row: a short in a name that stops printing valued at zero
            c["sides"][M17.R2_SIDE] = at(z0, side=-1)
            c["extra"][M17.R2_CELL] = at(z0)
            c["short_stopped"] = {"positions": int(sum(int(rec.cell[cell].U.st[rec.cell[cell].short].sum()) for rec in L.recs if rec.cell[cell].traded)), "short_positions": int(sum(rec.cell[cell].k for rec in L.recs if rec.cell[cell].traded))}
            c["sub"] = {lab: stat_run(B, rows, NI.sub_run(W, L, base, max(a, lo), b), max(a, lo), b)[0] for lab, a, b in SUBPERIODS}
            xh, br = NI.hedged_series(W, base.x, L, cell)                                   # the ES-hedged twin of the cell (NETISS [A6]'s rule: ex-ante OLS beta over the 252 sessions before the rank, zero before 252 exist)
            xhB = D15.to_B(xh, rows, B.n)
            sth = D15.cell_stats(B, xhB, cB, lo, hi, base, years=YEARS)
            c["hedged"] = {"base": sth, "usd_year": NI.per_year(sth["net"], sth["years"]), "ratios_nonzero": int(sum(1 for v in br.values() if v != 0.0)), "ratios": int(len(br)), "beta": beta_credit(B, ctx, W, rows, xhB)}
        summ[cell] = c
    for cell in CELLS:
        c = summ[cell]
        if nul is not None:
            c["checks"] = judge_cell(c["base"], c["stress"]["10 bps"]["net"], c["borrow_flat"]["net"], nul, ctx.n_years)
            c["PASS"] = bool(all(c["checks"].values()))
        c["gate70"] = NI.gate70(c, ctx.ref, nul)
    return {"variant": post_mode, "revised": rev_mode, "cells": summ, "null": nul}, SimpleNamespace(legs=L, cell_legs=legs, runs=runs, series=series, side_x=side_x)


# ------------------------------------------------------------------ the hand audit's rows (f): every contributor with its short-interest rows, files and volume
def si_fields(W, rec, cell, col):
    """the facts behind one name's score at its rank, the columns of the hand audit's file (f): the settlement s* and the FINRA file the row came from, the row's short interest, previous short interest, FINRA's split / revision flags, FINRA's own reported ADV and days to cover, the cache's ADV
    (and the sessions it rests on), D1, and for S1 the share count (as-of date, form, first filed date, accession) with F on both dates and S1; plus the short interest the same ticker had in the two settlements before (the rows that made the signal move)"""
    si, sc = W.si, rec.sc
    out = {"rank_date": f"{W.days[rec.r]:%Y-%m-%d}", "settlement": "", "source_file": "", "ticker": "", "si": float("nan"), "prev_si_reported": float("nan"), "split_flag": False, "revision_flag": False, "finra_adv": float("nan"), "finra_dtc": float("nan"),
           "cache_adv": float("nan"), "cache_adv_sessions": 0, "d1": float("nan"), "s1": float("nan"), "shares": float("nan"), "shares_asof": "", "shares_form": "", "shares_first_filed": "", "shares_accn": "", "F_asof": float("nan"), "F_s": float("nan"),
           "si_1_settlement_earlier": float("nan"), "si_2_settlements_earlier": float("nan"), "age_sessions": int(sc.age)}
    ss = sc.sc
    if ss is None:
        return out
    fin, ni = si.fin, W.ni
    fr = int(ss.frow[col])
    out.update({"settlement": f"{np.datetime64(int(ss.s_day), 'D')}", "ticker": str(ss.tk[col]), "cache_adv": float(ss.adv[col]), "cache_adv_sessions": int(ss.n_pres[col]), "d1": float(sc.d1[col]), "s1": float(sc.s1[col])})
    if fr >= 0:
        out.update({"source_file": fin.srcs[int(fin.srcc[fr])], "si": float(fin.si[fr]), "prev_si_reported": float(fin.psi[fr]), "split_flag": bool(fin.spl[fr]), "revision_flag": bool(fin.rev[fr]), "finra_adv": float(fin.adv[fr]), "finra_dtc": float(fin.dtc[fr])})
    g = int(ss.sg[col])
    if g >= 0 and cell == "S1":
        out.update({"shares": float(ni.E_val[g]), "shares_asof": ni_date(ni.E_end[g]), "shares_form": str(ni.E_form[g]), "shares_first_filed": ni_date(ni.E_f1[g]), "shares_accn": str(ni.E_accn[g]), "F_asof": float(ss.fa[col]), "F_s": float(ss.fs[col])})
    for q, key in ((1, "si_1_settlement_earlier"), (2, "si_2_settlements_earlier")):
        if sc.k - q >= 0:
            m = match_settlement(W, sc.k - q)
            fr_q = int(m.frow[col])
            if fr_q >= 0:
                out[key] = float(fin.si[fr_q])
    return out


def ni_date(d):
    """a day number -> 'YYYY-MM-DD'"""
    return NI.dstr(d)


def si_candidate_rows(W, L, cell, run, tbis_df, status, n=AUDIT_N):
    """the n largest single-name contributors of a cell for the hand audit (r17_resmom.rm_candidate_rows' rows: the largest GAINS with the fill date - the key shortint_audit.csv uses -, exit, side, $, the score, the split factor's ratio, the largest raw overnight move, TBIS's rows, the asset
    status, the hygiene reasons, the dividends; its two formation-window moves are RESMOM's and are left out) + this family's: the rank date, the settlement and its FINRA file, the short interest rows, the volume / share-count facts (si_fields)"""
    rows = M17.rm_candidate_rows(W, L, cell, run, tbis_df, status, n)
    p = run.pos
    if not rows:
        return rows
    sel = np.argsort(-np.asarray(p.pnl, float), kind="stable")[:n]
    for row, i in zip(rows, sel):
        rec, col = L.recs[int(p.rec[i])], int(p.col[i])
        for k_ in ("raw_move_formation", "adj_move_formation"):
            row.pop(k_, None)
        row.update(si_fields(W, rec, cell, col))
    return rows


def name_month_extremes(W, L, cell, run, n=SQUEEZE_N):
    """the n largest name-month GAINS and the n largest LOSSES of a cell (the squeeze list): per position its symbol, fill / exit date, side, $ P&L and score, with the settlement's short interest facts -> (gains, losses)"""
    p = run.pos
    if p is None or not len(p.pnl):
        return [], []
    pn = np.asarray(p.pnl, float)

    def rowof(i):
        rec, col = L.recs[int(p.rec[i])], int(p.col[i])
        d = {"cell": cell, "symbol": str(W.syms[col]), "date": f"{W.days[rec.f]:%Y-%m-%d}", "exit": f"{W.days[rec.x]:%Y-%m-%d}", "side": "long" if p.side[i] > 0 else "short", "pnl": float(pn[i]), "score": float(p.sig[i])}
        d.update(si_fields(W, rec, cell, col))
        return d
    return [rowof(i) for i in np.argsort(-pn, kind="stable")[:n]], [rowof(i) for i in np.argsort(pn, kind="stable")[:n]]


def month_in_full(W, L, cell, run, B, rows, xB, lo_d, hi_d, top=10):
    """one calendar month of a cell in full (the January 2021 squeeze month): its daily P&L, the positions held in it (the rebalance whose hold covers it) - every long and short with its P&L, the `top` worst and best - and the month's net by side"""
    k = np.flatnonzero(B.mask(lo_d, hi_d))
    daily = [(f"{B.index[i]:%Y-%m-%d}", float(xB[i])) for i in k]
    p = run.pos
    out = {"daily": daily, "net": float(sum(v for _d, v in daily)), "positions": []}
    if p is None or not len(p.pnl):
        return out
    for i in range(len(p.pnl)):
        rec = L.recs[int(p.rec[i])]
        if W.days[rec.f] <= hi_d and W.days[rec.x] >= lo_d:
            out["positions"].append({"symbol": str(W.syms[int(p.col[i])]), "side": "long" if p.side[i] > 0 else "short", "fill": f"{W.days[rec.f]:%Y-%m-%d}", "exit": f"{W.days[rec.x]:%Y-%m-%d}", "pnl": float(p.pnl[i]), "score": float(p.sig[i])})
    pos = sorted(out["positions"], key=lambda d: d["pnl"])
    out["worst"], out["best"] = pos[:top], pos[::-1][:top]
    out["net_long_positions"] = float(sum(d["pnl"] for d in pos if d["side"] == "long"))
    out["net_short_positions"] = float(sum(d["pnl"] for d in pos if d["side"] == "short"))
    return out


# ------------------------------------------------------------------ what is printed BEFORE any P&L: files, market codes, the known-at table, funds, the join and coverage, scored names, the no-score reasons, ages, the FINRA cross-checks
def known_at_rows(W):
    """[K] / [A3] / [A9] per settlement: the settlement date, the photographed release date (or none), the date of s + 12 sessions on the World's calendar, the first session after the LATER of the two (the usable row's date) and which one binds -> [dict]"""
    fin, tab = W.si.fin, W.si.tab
    T = W.T
    dn = lambda i: ("never in the data" if i >= T else f"{W.days[int(i)]:%Y-%m-%d}")
    out = []
    for k, s in enumerate(fin.ks):
        t12 = int(tab.row_s[k]) + SPEC["lag"] if tab.row_s[k] >= 0 else -1
        out.append({"settlement": f"{np.datetime64(int(s), 'D')}", "release": ("-" if fin.release[k] < 0 else f"{np.datetime64(int(fin.release[k]), 'D')}"), "s_plus_12_sessions": ("-" if t12 < 0 or t12 >= T else f"{W.days[t12]:%Y-%m-%d}"),
                    "usable_from": ("-" if tab.u[k] >= 10 ** 9 else dn(tab.u[k])), "binding": str(tab.binding[k])})
    return out


def score_report(W, ranks, values=True, rev_mode="drop"):
    """the pre-P&L record of every rank: the universe at the fill session less the funds, the latest usable settlement and its age in sessions, the join and the coverage [A2], per cell the scored names and the names lost to each rule, the names with SI = 0 (values only), FINRA's revised rows and
    split flags among the universe [A11], S1's as-of age buckets and the share of counts more than 100 days old [A5]; values=True also keeps the scored D1 / S1 values (for the per-year median and 5th / 95th percentiles - Stage A prints them, the dryload never does) and FINRA's days to cover
    against D1 (rank correlation). -> [one dict per rank]"""
    rows = []
    for r, f, x in ranks:
        sc = score_rank(W, r, rev_mode)
        uni = sc.uni
        rec = {"rank": f"{W.days[r]:%Y-%m-%d}", "year": int(W.days[f].year), "k": int(sc.k), "settlement": ("-" if sc.k < 0 else f"{np.datetime64(int(sc.s_day), 'D')}"), "age_sessions": int(sc.age), "universe_before_funds": int(sc.n_uni0), "funds_by_title": int(sc.n_title),
               "funds_by_finra_name": int(sc.n_name), "universe": int(sc.n_uni), "join": dict(sc.mc), "with_a_row": int(sc.n_cov), "coverage": float(sc.cov), "covered": bool(sc.covered), "cells": {}}
        ss = sc.sc
        if ss is not None:
            rec["revised_rows"] = int((ss.rev & sc.in_uni).sum())
            rec["finra_split_flag_rows"] = int((ss.spl_flag & sc.in_uni).sum())
            rec["finra_split_flag_and_our_window_split"] = int((ss.spl_flag & sc.in_uni & ss.split_win).sum())
            rec["our_window_split_without_the_flag"] = int((~ss.spl_flag & sc.in_uni & ss.split_win & (ss.mcode == M_OK)).sum())
        for cell in CELLS:
            score, code = cell_score(sc, cell)
            cnt = np.bincount(code[uni].astype(np.int64), minlength=len(REASONS)) if len(uni) else np.zeros(len(REASONS), np.int64)
            ok = np.isfinite(score[uni])
            c = {"scored": int(cnt[0]), "reasons": {REASONS[q]: int(cnt[q]) for q in range(1, len(REASONS))}}
            if values:
                c["values"] = np.zeros(0)                                                         # a rank with no usable file has no value (the key is there: the per-year percentiles pool every rank)
            if ss is not None:
                c["zero_si"] = int((ss.zero_si[uni] & ok).sum())
                if cell == "S1":
                    ag = sc.age_s[uni][ok]
                    c["s_age_days"] = {"le30": int((ag <= 30).sum()), "d31_60": int(((ag > 30) & (ag <= 60)).sum()), "d61_100": int(((ag > 60) & (ag <= SPEC["old"])).sum()), "d101_200": int(((ag > SPEC["old"]) & (ag <= SPEC["stale"])).sum())}
                    c["old_counts"] = int((ag > SPEC["old"]).sum())
                if values:
                    c["values"] = np.asarray(score[uni][ok], float)
                    if cell == "D1":
                        c["finra_dtc_spearman"] = NI.spearman(ss.fin_dtc[uni][ok], score[uni][ok])
            rec["cells"][cell] = c
        rows.append(rec)
    return rows


def unscored_by_name(W, ranks, rev_mode="drop"):
    """the names that get no score at a rank for a reason that is a property of the NAME (the ticker join, the funds, the map) - counted BY NAME: the number of ranks each is in the universe at (before the fund rules) -> {cell: {reason: {symbol: ranks}}} for the join reasons and S1's static ones"""
    out = {c: defaultdict(Counter) for c in CELLS}
    keep = {R_FUND_TITLE, R_TICKER_UNKNOWN, R_TICKER_SHARED, R_NO_ROW, R_DUP_ROWS, R_FUND_NAME, R_MULTI_CLASS, R_NOT_IN_MAP, R_MAP_MISMATCH, R_MAP_AMBIGUOUS, R_MAP_UNMAPPED, R_MAP_NONCOMMON, R_MAP_OTHER, R_NO_FACTS, R_FOREIGN}
    syms = np.asarray(W.syms).astype(str)
    for r, f, _x in ranks:
        sc = score_rank(W, r, rev_mode)
        uni0 = np.flatnonzero(W.U[f])
        for cell in CELLS:
            code = cell_score(sc, cell)[1]
            for q in keep:
                for s_ in syms[uni0[code[uni0] == q]]:
                    out[cell][REASONS[q]][str(s_)] += 1
    return {c: {k: dict(v) for k, v in d.items()} for c, d in out.items()}


def funds_out_rows(W, ranks, rev_mode="drop"):
    """[A1] the list of every name the fund rules take out of a rank's universe, for the hand check before any score: symbol, by (asset-list title | FINRA issue name | both), the tokens, the asset-list title, FINRA's issue name(s) with a token, the number of ranks it is in the fill universe at and its first and last"""
    si, fin = W.si, W.si.fin
    seen = defaultdict(lambda: {"title": False, "name": False, "ranks": []})
    for r, f, _x in ranks:
        sc = score_rank(W, r, rev_mode)
        uni0 = np.flatnonzero(W.U[f])
        nm = (sc.sc.fund_name & (sc.sc.mcode == M_OK)) if sc.sc is not None else np.zeros(W.S, bool)
        for j in uni0:
            if si.fund_title[j] or nm[j]:
                d = seen[str(W.syms[j])]
                d["title"] |= bool(si.fund_title[j])
                d["name"] |= bool(nm[j])
                d["ranks"].append(f"{W.days[r]:%Y-%m-%d}")
    out = []
    for sym in sorted(seen):
        d = seen[sym]
        out.append({"symbol": sym, "by": ("title and FINRA name" if d["title"] and d["name"] else "asset-list title" if d["title"] else "FINRA issue name"), "title_tokens": "+".join(si.assets.tok.get(sym, [])), "asset_title": si.assets.title.get(sym, ""),
                    "finra_names_with_a_token": " | ".join(fin.fund_pairs.get(sym, [])[:3]), "ranks": len(d["ranks"]), "first_rank": d["ranks"][0], "last_rank": d["ranks"][-1]})
    return out


def pctl_row(a):
    """the 5th / 50th / 95th percentiles of an array (NaN when empty)"""
    return NI.pctl_text(a)


def percentiles_by_year(srows):
    """the 5th / 50th / 95th percentile of the scored D1 / S1 values of each fill year, pooled over the year's ranks (score_report with values=True; a rank with no usable file adds none; a year with no value: NaNs) -> {cell: {year: [p5, p50, p95]}}"""
    return {c: {int(y): pctl_row(np.concatenate([r_["cells"][c]["values"] for r_ in srows if r_["year"] == y])) for y in sorted({r_["year"] for r_ in srows})} for c in CELLS}


def print_files_block(fin, finfo, assets, nc, ncinfo, mp_info=None):
    """[A7] / [A8] / [A9] the pinned FINRA pull as READ: the five files (each refused if its sha256 differs) and the asset list, the flat file's rows / files / settlements, the files per year and any missing settlement date, the quarantined file, the revision and split flags by year, the rows with a fund-token
    issue name, the schedule's rows (the page lists the year ahead: those are dropped at the cut), the provenance and the probe, the name changes read from the wide calendar - COUNTS only"""
    sh = lambda k: FILE_SHA[k][:12] + "..."
    print(f"[A7] pinned FINRA files (each refused if its sha256 differs): flat {sh('flat')} manifest {sh('manifest')} schedule {sh('schedule')} provenance {sh('provenance')} probe {sh('probe')}; SIPORB asset list {sh('assets')}")
    ks = fin.ks
    ys = Counter(int(np.datetime64(int(k), 'D').astype('datetime64[Y]').astype(int)) + 1970 for k in ks)
    print(f"  flat file: {finfo['rows']:,} rows kept of {finfo['rows_read']:,} read ({finfo['rows_without_a_symbol']:,} without a symbol dropped) from {finfo['files']} files = {finfo['settlements']} settlement dates {finfo['first']} .. {finfo['last']} (none on / after the cut, none of the quarantined {list(QUARANTINED)}); "
          f"the manifest's sha256, rows, files, first / last file, quarantine list, rows by file and market code and release dates all equal what was read")
    print("  files read per year: " + ", ".join(f"{y}: {n}" for y, n in sorted(ys.items())) + "; settlement dates the probe lists (status 200) that are not in the flat file and not quarantined (MISSING): " + (", ".join(finfo["missing_settlement_dates"]) if finfo["missing_settlement_dates"] else "none"))
    print(f"  short interest: blank {finfo['short_interest_blank']:,}, unreadable {finfo['short_interest_unreadable']:,}, negative {finfo['short_interest_negative']:,} rows; flags: revision {finfo['revision_flag_values']}, split {finfo['split_flag_values']}; market codes outside the nine known: {finfo['market_codes_other'] or 'none'}")
    ry, sy = Counter(), Counter()
    for k in range(len(ks)):
        a, b = int(fin.off[k]), int(fin.off[k + 1])
        y = int(np.datetime64(int(ks[k]), 'D').astype('datetime64[Y]').astype(int)) + 1970
        ry[y] += int(fin.rev[a:b].sum())
        sy[y] += int(fin.spl[a:b].sum())
    print("  rows with FINRA's revision flag 'R' by year [A11]: " + ", ".join(f"{y}: {n:,}" for y, n in sorted(ry.items())) + " (total " + f"{sum(ry.values()):,}); rows with its split flag 'S' by year: " + ", ".join(f"{y}: {n:,}" for y, n in sorted(sy.items())) + f" (total {sum(sy.values()):,})")
    sc = finfo["schedule"]
    print(f"  photographed schedule [A9]: {sc['rows_on_file']} rows on file, {sc['rows_dropped_at_the_cut']} dropped at the cut (the page lists the year ahead), {sc['rows_read']} read, {sc['rows_with_a_release_date']} with a release date, by column {sc['by_release_column']}, pages disagree on {sc['pages_disagree_settlements']}; "
          f"{finfo['settlements_with_a_release_date']} of the {finfo['settlements']} settlements have a release date; provenance: {finfo['provenance_file_entries_for_the_files_read']} of the {finfo['files']} files have a url / size / sha256 entry ({finfo['provenance_rebuilt_from_disk']} rebuilt from disk), "
          f"the quarantined file's entry on record {finfo['quarantined_on_record_in_provenance']}, never read; probe: {finfo['probe_status_200_before_the_cut']} dates with status 200 before the cut")
    print(f"  [A1] asset list: {assets.info['rows']:,} rows on {assets.info['symbols']:,} symbols ({assets.info['duplicate_symbol_rows']} rows share a symbol; by status {assets.info['by_status']}); titles with a fund token: {assets.info['fund_title_symbols']} symbols ({assets.info['fund_title_symbols_by_first_row_only']} by their first row alone), by token {assets.info['by_token']}; FINRA issue names with a fund token: {finfo['fund_named_rows']:,} rows on {finfo['fund_named_symbols']:,} symbols")
    if ncinfo.get("present"):
        print(f"  name changes read from the wide calendar [SYMBOLS]: {ncinfo['rows']:,} rows, {ncinfo['dropped_at_the_cut']} dropped at the cut, {ncinfo['undated']} undated, {ncinfo['empty_or_unchanged_symbol']} with an empty / unchanged symbol, {ncinfo['kept']:,} kept")
    else:
        print("  name changes: the wide calendar is not on file - every ticker is the cache's own (no rename is known)")


def print_market_codes(fin, finfo):
    """[A2] BEFORE any score: per FINRA file its rows by market code (NYSE, NNM = Nasdaq, ARCA, SC = Nasdaq Capital, BZX, AMEX = NYSE American, IEX, OTC, OTCBB) and the totals"""
    by = finfo["rows_by_file_and_market"]
    cols = list(MARKETS) + ["other"]
    print("[A2] FINRA'S MARKET CODES, per file (rows by market code: " + " / ".join(cols) + "):")
    tot = Counter()
    for k in range(len(fin.ks)):
        names = [s_ for s_ in fin.srcs if src_day(s_) == f"{np.datetime64(int(fin.ks[k]), 'D')}"]
        for s_ in names:
            d = by.get(s_, {})
            tot.update(d)
            print(f"    {src_day(s_)}: " + " ".join(f"{d.get(c, 0)}" for c in cols))
    print("  total rows by market code: " + ", ".join(f"{c} {tot.get(c, 0):,}" for c in cols))


def print_known_at(rows):
    """[K] / [A3] / [A9] per settlement: the photographed release date, s + 12 sessions, the first session after the later of the two, and which binds"""
    b = Counter(r["binding"] for r in rows)
    print(f"[K] / [A3] KNOWN AT: a settlement s is usable at a rank close from the first session after the LATER of s + {SPEC['lag']} sessions and FINRA's photographed release date; binding: {dict(b)} ({len(rows)} settlements)")
    print("  settlement: release | s + 12 sessions | usable from | binds")
    for r in rows:
        print(f"    {r['settlement']}: {r['release']} | {r['s_plus_12_sessions']} | {r['usable_from']} | {r['binding']}")


def print_coverage(crows, start_rank, lo):
    """[A2] per rank: the latest usable settlement and its age in sessions, the universe less the funds, the names with a FINRA row, the share, trades or not; then the walk-forward's start"""
    print("[A2] COVERAGE per rank (rank: settlement s*, age in sessions | universe at the fill session / less the asset-list funds / less the FINRA-name funds = the rank's universe | with a FINRA row | coverage | rank trades?):")
    for c in crows:
        print(f"    {c['rank']}: " + (f"{c['settlement']}, {c['age_sessions']}" if c["k"] >= 0 else "no usable file") + f" | {c['universe_before_funds']} / -{c['funds_by_title']} / -{c['funds_by_finra_name']} = {c['universe']} | {c['with_a_row']} | "
              + (f"{c['coverage']:.1%}" if np.isfinite(c["coverage"]) else "n/a") + " | " + ("yes" if c["covered"] else f"NO ({'no usable file' if c['k'] < 0 else 'under ' + format(SPEC['cover'], '.0%')})"))
    n_cov = sum(1 for c in crows if c["covered"])
    print(f"  the walk-forward STARTS at the first rank at or above {SPEC['cover']:.0%}: " + ("NONE (no rank qualifies)" if start_rank is None else f"rank {start_rank} (positions from {lo:%Y-%m-%d}); {n_cov} of the {len(crows)} built ranks are covered, "
                                                                                                f"{sum(1 for c in crows if not c['covered'] and c['rank'] >= start_rank)} after the start are not (they trade nothing and stay in the stretch)"))


def print_join(crows):
    """[SYMBOLS] per rank: the universe names (before the FINRA-name fund rule, less the asset-list funds) by the join's outcome - a FINRA row / ticker unknown / ticker shared / no row in the file / the ticker listed twice - and the FINRA-name funds taken out"""
    print("[SYMBOLS] the ticker join, per rank (universe less the asset-list funds: matched / ticker unknown / ticker shared by two cache names / no FINRA row / ticker listed twice | of the matched, funds by FINRA issue name):")
    for c in crows:
        j = c["join"]
        if c["k"] < 0:
            print(f"    {c['rank']}: no usable file")
        else:
            print(f"    {c['rank']}: {j['ok']} / {j['unknown']} / {j['shared']} / {j['no_row']} / {j['duplicate']} | {c['funds_by_finra_name']}")


def print_score_report(rows, names=None, values=True):
    """BEFORE ANY P&L, in the prereg's order: the scored names per rank and per cell with the settlement and the age of s*; the names lost to each rule per rank; the median and the 5th / 95th percentiles of D1 and S1 per year and the share of names with SI = 0 (values only: the dryload keeps no value); S1's as-of age
    buckets and the share of counts more than 100 days old per rank and per year [A5]; the revised rows [A11] and FINRA's split flags beside D1's split rule per year"""
    print("BEFORE ANY P&L - the short-interest scores: the scored names of each cell (D1 / S1), by rank")
    for c in CELLS:
        print(f"  {c} per rank (rank date: universe / scored | s* and its age in sessions" + (" | zero-SI names" if values else "") + (" | S1 counts over 100 days old" if c == "S1" else "") + "):")
        for rec in rows:
            x = rec["cells"][c]
            ex = ""
            if values:
                ex += f" | {x.get('zero_si', 0)}"
            if c == "S1":
                ex += f" | {x.get('old_counts', 0)}"
            print(f"    {rec['rank']}: {rec['universe']} / {x['scored']} | {rec['settlement']}, {rec['age_sessions']}" + ex)
    print("  names lost to each rule, by rank (counts of universe names, the first reason of each):")
    for c in CELLS:
        print(f"  {c}: " + "; ".join(f"{rec['rank']}: " + ", ".join(f"{k} {v}" for k, v in rec["cells"][c]["reasons"].items() if v) for rec in rows))
    if values and rows and all("values" in r_["cells"][c_] for r_ in rows for c_ in CELLS):
        for c in CELLS:
            byy = defaultdict(list)
            for rec in rows:
                byy[rec["year"]].append(rec["cells"][c]["values"])
            print(f"  {c} per fill year (scored names pooled over the year's ranks: n, 5th / median / 95th percentile): " + "; ".join(
                f"{y}: {sum(len(v) for v in vs):,}, " + " / ".join(f"{q:.4g}" for q in pctl_row(np.concatenate(vs))) for y, vs in sorted(byy.items()) if vs))
        tot = lambda c, k: sum(rec["cells"][c].get(k, 0) for rec in rows)
        for c in CELLS:
            n = max(tot(c, "scored"), 1)
            print(f"  {c}: {tot(c, 'scored'):,} scored name-ranks over every rank; SI = 0 for {tot(c, 'zero_si'):,} of them ({tot(c, 'zero_si') / n:.1%})")
        sp = [rec["cells"]["D1"].get("finra_dtc_spearman", float("nan")) for rec in rows]
        sp = [v for v in sp if np.isfinite(v)]
        if sp:
            print(f"  FINRA's own days to cover against D1: rank correlation per rank - mean {np.mean(sp):.3f}, min {np.min(sp):.3f}, max {np.max(sp):.3f} over {len(sp)} ranks (a cross-check, never an input)")
    n1 = max(sum(r["cells"]["S1"]["scored"] for r in rows), 1)
    byy = defaultdict(lambda: [0, 0, 0, 0, 0])
    for rec in rows:
        a = rec["cells"]["S1"].get("s_age_days") or {}
        v = byy[rec["year"]]
        v[0] += rec["cells"]["S1"]["scored"]
        v[1] += rec["cells"]["S1"].get("old_counts", 0)
        v[2] += a.get("le30", 0) + a.get("d31_60", 0)
        v[3] += a.get("d61_100", 0)
        v[4] += a.get("d101_200", 0)
    print(f"  [A5] S1's share counts by age at s* (scored name-ranks: up to 60 days / 61-100 / 101-{SPEC['stale']}), per year, and the share more than {SPEC['old']} days old: " + "; ".join(
        f"{y}: {v[2]:,} / {v[3]:,} / {v[4]:,}, {v[1] / max(v[0], 1):.1%}" for y, v in sorted(byy.items())) + f"; over every rank {sum(v[1] for v in byy.values()) / n1:.1%}")
    ry = defaultdict(lambda: [0, 0, 0, 0])
    for rec in rows:
        v = ry[rec["year"]]
        v[0] += rec.get("revised_rows", 0)
        v[1] += rec.get("finra_split_flag_rows", 0)
        v[2] += rec.get("finra_split_flag_and_our_window_split", 0)
        v[3] += rec.get("our_window_split_without_the_flag", 0)
    print("  [A11] FINRA-revised rows among the universe (no score at that rank), by fill year: " + ", ".join(f"{y}: {v[0]:,}" for y, v in sorted(ry.items())) + f" (total {sum(v[0] for v in ry.values()):,})")
    print("  FINRA's split flag 'S' beside D1's split rule (a split in the 20-session volume window = no score), by fill year (universe rows with the flag / of them with a split in our window / our window splits without the flag): "
          + "; ".join(f"{y}: {v[1]:,} / {v[2]:,} / {v[3]:,}" for y, v in sorted(ry.items())) + " - printed as a cross-check, never a replacement")


def print_unscored_by_name(by):
    """the names that have no score for a reason that is a property of the name (the join, the funds, the map), LISTED by name per cell: symbol x the ranks it is in the fill universe at"""
    print("  names with no score for a reason about the NAME, LISTED (symbol x the ranks it is in the fill universe at):")
    for c in CELLS:
        for reason in REASONS[1:]:
            d = by.get(c, {}).get(reason)
            if d and (c == "S1" or reason in REASONS[R_FUND_TITLE:R_FUND_NAME + 1]):
                if c == "S1" and reason in REASONS[R_FUND_TITLE:R_FUND_NAME + 1]:
                    continue                                                                   # the shared reasons are listed once, under D1
                print(f"    {c} {REASON_TEXT[reason]} - {len(d)} names: " + ", ".join(f"{s} x{n}" for s, n in sorted(d.items())))


# ------------------------------------------------------------------ the reports (never a pass route)
Q21_DAILY = os.environ.get("EDGELOG_Q21_DAILY")      # [A4] FRONTIER's Q21 stock BAB seat's daily P&L (columns date, pnl) once it has run - the correlation is computed when the file is on file; otherwise it is reported as not run (CHOICE: the prereg does not say where Q21 writes - an environment variable names the file)


def q21_overlap(B, xB, lo, hi):
    """[A4] the overlap with FRONTIER's Q21 stock BAB seat: the correlation of the daily P&L once both have run (the share of common names per rank needs Q21's picks and is not computed here). Reads Q21_DAILY (date, pnl) cut at the lockbox; reported as 'not on file' when there is none"""
    p = Q21_DAILY
    if not p or not os.path.exists(p):
        return {"on_file": False, "note": "Q21's daily P&L is not on file (set EDGELOG_Q21_DAILY): the correlation and the common-names share are NOT computed - printed as not run"}
    df = pd.read_csv(p)
    if not {"date", "pnl"} <= set(df.columns):
        return {"on_file": False, "note": f"{os.path.basename(p)} lacks the columns date, pnl"}
    d = pd.to_datetime(df["date"].astype(str).str[:10], errors="coerce")
    ok = d.notna() & (d < LB0)
    s = pd.Series(df.loc[ok, "pnl"].to_numpy(float), index=pd.DatetimeIndex(d[ok]))
    k = np.flatnonzero(B.mask(lo, hi))
    q = s.reindex(B.index[k])
    m = q.notna().to_numpy()
    x = np.asarray(xB, float)[k][m]
    r = float(np.corrcoef(x, q.to_numpy(float)[m])[0, 1]) if m.sum() > 2 and np.ptp(x) > 0 and np.ptp(q.to_numpy(float)[m]) > 0 else float("nan")
    return {"on_file": True, "rows": int(m.sum()), "daily_pnl_correlation": r, "share_of_common_names": "not computed (Q21's picks are not on file)"}


def reports(W, B, rows, ctx, obj, summ, tbis_df, status, legs_meta, post_mode="remove"):
    """everything the prereg's DIAGNOSTICS paragraph and [A4] list, for the registered reading: each cell's realised beta to ES (and each SIDE's, per $ of its own notional) on L's drawdown days, #463's and every day of the stretch, L's drawdown-episode table with the cell's $ inside each, its place on
    the MDL map, the correlation of its daily P&L with RES's registered line and the overlap of its picks with RESMOM's, the score's persistence and the turnover, the 50 largest gains (the hand audit's rows), the 20 largest name-month gains AND losses (the squeeze list), the January 2021 month in
    full, the dividend flows, survivorship, the overlap with Q21's BAB seat. The ES-hedged twin is in summ"""
    L, lo, hi = obj.legs, ctx.lo, ctx.hi
    rep = {"beta_to_es": {}, "beta_sides": {}, "episodes": {}, "ref_episodes": {}, "map_point": {}, "corr_with_legs": {}, "corr_with_res": {}, "pick_overlap_with_res": {}, "top20_gains": {}, "top20_losses": {}, "jan2021": {}, "months": {}, "turnover": {}, "survivorship": {},
           "dividend_flows": {}, "q21": {}}
    cands = {}
    kw = np.flatnonzero(B.mask(lo, hi))
    resL = M17.rm_build(W, lo, hi, post_mode, units=False)                          # RESMOM's own legs at the same rebalances: its 50 / 50 picks
    res_by_r = {rec.r: rec for rec in resL.recs if rec.traded}
    side = M17.SPEC["n_side"] * M17.SPEC["slot"]
    for cell in CELLS:
        xB = obj.series[cell][0]
        with np.errstate(all="ignore"):
            rep["beta_to_es"][cell] = {"book": D15.es_beta(B, ctx.S12, W, rows, xB), "L": D15.es_beta(B, ctx.ref.S, W, rows, xB)}
            rep["beta_sides"][cell] = {}
            for sd, nm in ((1, "long"), (-1, "short")):
                sx = obj.side_x.get(cell, {}).get(sd)
                if sx is not None:
                    e = D15.es_beta(B, ctx.ref.S, W, rows, sx)
                    rep["beta_sides"][cell][nm] = {"dd_days_L": e["DD days"]["usd_per_1.00_es"] / side, "all_days": e["all WF days"]["usd_per_1.00_es"] / side}
            rc = float(np.corrcoef(xB[kw], ctx.ref.res[kw])[0, 1]) if np.ptp(xB[kw]) > 0 and np.ptp(ctx.ref.res[kw]) > 0 else float("nan")
        rep["episodes"][cell] = D15.episodes_table(ctx.S12, xB)
        rep["ref_episodes"][cell] = D15.episodes_table(ctx.ref.S, xB)
        c = summ[cell]
        rep["map_point"][cell] = {"standalone_roc_30k": c["base"]["roc"], "rho_dd": c["seat_ref"]["rho_dd"], "DO": c["seat_ref"]["DO"], "rho_dd_book": c["seat"]["rho_dd"], "DO_book": c["seat"]["DO"]}
        rep["corr_with_legs"][cell] = A13.corrs(B, xB, legs_meta, lo, hi)
        rep["corr_with_res"][cell] = rc
        cands[cell] = si_candidate_rows(W, L, cell, obj.runs[cell], tbis_df, status)
        rep["top20_gains"][cell], rep["top20_losses"][cell] = name_month_extremes(W, L, cell, obj.runs[cell])
        rep["jan2021"][cell] = month_in_full(W, L, cell, obj.runs[cell], B, rows, xB, *CRASH_JAN21) if lo <= CRASH_JAN21[1] else None
        rep["months"][cell] = M17.month_nets(B, xB, lo, hi)
        rep["turnover"][cell] = NI.ni_turnover(L, cell)
        rep["survivorship"][cell] = D15.survivorship(W, obj.cell_legs[cell], status)
        rep["dividend_flows"][cell] = NI.ni_div_flows(L, cell)
        rep["q21"][cell] = q21_overlap(B, xB, lo, hi)
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
def print_book_line(B, ctx, bk):
    """#463's and L's numbers on THIS stretch beside their registered full-WF numbers (EVERY book number of this family is computed on the stretch)"""
    k = B.mask(ctx.lo, ctx.hi)
    b = R11.stats(np.asarray(B.raw, float)[k], B.index[k])
    ref, rf = ctx.ref, ctx.ref_full
    g, gf = ref.structure, rf.structure
    print(f"THE STRETCH {ctx.lo:%Y-%m-%d} .. {ctx.hi:%Y-%m-%d} ({int(k.sum()):,} #463 rows): #463 ROC@30k {b['roc']:.2f} Sortino {b['sort']:.3f} maxDD ${b['max_dd']:,.0f} (${NI.per_year(b['net'], b['years']):,.0f} a year; full WF {bk['roc']:.2f} / {bk['sortino']:.3f}); "
          f"L = #463 + {DV.REF_W} x RES ROC@30k {ref.stats['roc']:.2f} Sortino {ref.stats['sort']:.3f} maxDD ${ref.stats['max_dd']:,.0f} (${NI.per_year(ref.stats['net'], ref.stats['years']):,.0f} a year; full WF {rf.facts['roc']:.2f} / {rf.facts['sortino']:.3f} / ${rf.facts['max_dd']:,.0f})")
    print(f"  L's drawdown structure on the stretch (MDL r1's rule): {g['episodes']} qualifying episodes, {g['days']} DD days, {g['weeks']} DD weeks (the full WF: {gf['episodes']} episodes, {gf['days']} DD days) - the basis of the DO, the beta credit and the #70 gate")


def print_power(nul):
    """[A6] the power line: the random-name null's p5 / p50 / p95 of the MAX over the 2 cells' WF ROC @ $30k and each cell's own p50 / p95 - printed BEFORE any cell's number"""
    print(f"POWER LINE [A6] - printed before any cell's P&L: the random-name null ({nul['draws']} draws, seed {nul['seed']}, the MAX over the 2 cells), ROC@30k p5 {nul['roc_max']['p5']:.1f} p50 {nul['roc_max']['p50']:.1f} p95 {nul['roc_max']['p95']:.1f}; each cell alone p50 / p95: "
          + ", ".join(f"{c} {nul['by_cell'][c]['p50']:.1f} / {nul['by_cell'][c]['p95']:.1f}" for c in CELLS) + f"; the DO null on L's drawdown days (the MAX over the 2 cells) p50 {nul['do_ref_max']['p50']:+.3f} p95 {nul['do_ref_max']['p95']:+.3f}")


def print_cells(res, audit_st=None):
    for cell in CELLS:
        c = res["cells"][cell]
        fails = [k for k, v in c["checks"].items() if not v]
        s2 = ", ".join(f"{k} net ${v['net']:,.0f}" for k, v in c["stress"].items())
        print("  " + NI.row(cell, c))
        print(f"        stress: {s2}; the flat {BORROW_FLAT:.0%} borrow on every short net ${c['borrow_flat']['net']:,.0f} (ROC@30k {c['borrow_flat']['roc']:.1f}); by July-June year: " + " ".join(f"{y}-{(y + 1) % 100:02d}:{v:+,.0f}" for y, v in c["base"]["by_year"].items())
              + f"; years with a position: {len(c['years_held'])}")
        b = c["beta"]
        print(f"        realised beta to ES (the cell's daily $ P&L on ES's daily return per $ of one side's notional ${b['side_notional']:,.0f}): L's DD days {b['beta_dd_days']:+.3f}, all stretch days {b['beta_all_days']:+.3f} - the credit cap is |beta| <= {b['cap']:.2f} on BOTH -> "
              + ("the drawdown-day profile may be credited" if b["within_cap"] else "NOT CREDITED: the profile is reported, no incremental A2 pass, no gate, no line"))
        a2 = c["A2"]
        if a2.get("at_half_c"):
            rf, pl = a2["reference"], a2["plain_463"]
            a2s = (f"c x{a2['c']:.4g} (cell daily std ${a2['std_cell']:,.0f} vs #463's ${a2['std_book']:,.0f} over {a2['window'][0]} .. {a2['window'][1]}): L + c x cell ROC@30k {a2['roc']:.2f} (${a2['usd_year']:,.0f} a year) Sortino {a2['sortino']:.3f} against L's "
                   f"{rf['roc']:.2f} (${rf['usd_year']:,.0f} a year) / {rf['sortino']:.3f} -> " + ("INCREMENTAL PASS (both above): MANAGER #70's gate follows, then at most one forward book line" if a2["incremental_credit"] else
                                                                                                    ("incremental numbers pass but the beta rule refuses the credit: no line" if a2["incremental_pass"] else "no incremental pass (it needs both above)"))
                   + f"; at 0.5c ROC {a2['at_half_c']['roc']:.2f} (${a2['at_half_c']['usd_year']:,.0f} a year) / Sortino {a2['at_half_c']['sortino']:.3f}, at 2c ROC {a2['at_double_c']['roc']:.2f} (${a2['at_double_c']['usd_year']:,.0f} a year) / Sortino "
                   f"{a2['at_double_c']['sortino']:.3f}; the plain #463 + c x cell book (a reported row): ROC {pl['roc']:.2f} (${pl.get('usd_year', float('nan')):,.0f} a year) / Sortino {pl['sortino']:.3f}")
        else:
            a2s = f"{a2.get('error', 'no c')} -> no incremental pass"
        au = None if audit_st is None else audit_st[cell]
        print(f"        Stage A (a)-(e) {'PASS' if c['PASS'] else 'FAIL (' + ', '.join(fails) + ')'}" + ("" if au is None else f"; hand audit (f) {au['audited']}/{au['listed']} of the top-{AUDIT_N} listed -> {'COMPLETE' if au['audit_complete'] else 'incomplete'}"))
        print(f"        A2 (a report): {a2s}")
        g = c["gate70"]
        print(f"        #70 gate basis (L's {g['episodes']} drawdown episodes, {g['dd_days']} DD days on the stretch): the cell's DO {g['DO']:+.3f}, rho_dd {g['rho_dd']:+.3f}" + (
              f"; its null's DO (random names, the MAX over the 2 cells) p5 {g['null_do_p5']:+.3f} p50 {g['null_do_p50']:+.3f} p95 {g['null_do_p95']:+.3f} -> the cell's DO is {'above' if g['DO_above_null_p95'] else 'not above'} the null's p95" if "null_do_p95" in g else "")
              + (f"; its P&L inside those episodes ${sum(g['episode_pnl']):,.0f} (${g['pnl_without_best_episode']:,.0f} without the best one; it helps {g['episodes_helped']} of {len(g['episode_pnl'])})" if g.get("episode_pnl") else "")
              + ("" if g["credited"] else "; the beta rule: NOT credited"))


def print_borrow(res):
    """the BORROW CURVE: net at each flat rate on every short and the break-even fee"""
    print("BORROW CURVE - net $ at a flat annual rate on every short every day (the rate replaces the 0.25% base; ROC@30k in brackets), and the break-even fee (the rate at which net is zero)")
    print("  " + " " * 8 + "".join(f"{r_:>16.2%}" for r_ in BORROW_CURVE) + f"{'break-even':>14}")
    for cell in CELLS:
        c = res["cells"][cell]
        print(f"  {cell:<8}" + "".join(f"{c['borrow_curve'][f'{r_:g}']['net']:>10,.0f} ({c['borrow_curve'][f'{r_:g}']['roc']:>4.0f})" for r_ in BORROW_CURVE) + (f"{c['breakeven_fee']:>13.2%}" if np.isfinite(c["breakeven_fee"]) else f"{'n/a':>14}"))


def print_twins(res, rev=None):
    """the ES-hedged twin of each cell [NETISS [A6]'s rule] and the REVISED-ROWS twin [A11] (FINRA-revised rows scored as they stand), beside the cell: net $, ROC @ $30k, $ a year"""
    print("TWINS - REPORTED beside each cell, never a pass route")
    for c in CELLS:
        x = res["cells"][c]
        k, h = x["base"], x["hedged"]
        print(f"  {c}: the cell net ${k['net']:,.0f} ROC@30k {k['roc']:.1f} (${x['usd_year']:,.0f} a year); ES-hedged twin (an ES overlay sized ex ante by the OLS beta of the cell's own daily P&L on ES over the 252 sessions before each rank, zero before 252 sessions exist; "
              f"{h['ratios_nonzero']} of {h['ratios']} rebalances hedged) net ${h['base']['net']:,.0f} ROC@30k {h['base']['roc']:.1f} (${h['usd_year']:,.0f} a year), its realised beta L's DD days {h['beta']['beta_dd_days']:+.3f} / all days {h['beta']['beta_all_days']:+.3f}")
    if rev is not None:
        for c in CELLS:
            k, v = res["cells"][c]["base"], rev["cells"][c]["base"]
            print(f"  {c} [A11] revised-rows twin (the rows FINRA re-uploaded scored as they stand): net ${v['net']:,.0f} ROC@30k {v['roc']:.1f} (${NI.per_year(v['net'], v['years']):,.0f} a year), {v['n_units']} rebalances, {v['n_pos']:,} positions; "
                  f"the registered reading (a revised row gives no score) net ${k['net']:,.0f} ROC@30k {k['roc']:.1f}")


def print_scored(label, cnt):
    """the scored names and the sides by fill year: per cell the pool's scored names (summed over the year's rebalances), the pool names with no score, and the rebalances that trade the top 50 / the third / nothing / nothing for want of 90% coverage / no usable file; then the no-score reasons"""
    print(f"  {label} scored names by fill year (per cell: scored / pool names with no score; rebalances trading the top {M17.SPEC['n_side']} a side | the top-bottom third | nothing | uncovered | no file)")
    for y, c in sorted(cnt.items()):
        if c.get("rebalances", 0):
            print(f"    {y}: " + "; ".join(f"{cl} {c.get(f'scored_{cl}', 0):,} / {c.get(f'no_score_{cl}', 0):,}, {c.get(f'mode_{cl}_top', 0)} | {c.get(f'mode_{cl}_third', 0)} | {c.get(f'mode_{cl}_none', 0)} | {c.get(f'mode_{cl}_uncovered', 0)} | {c.get(f'mode_{cl}_nofile', 0)}" for cl in CELLS))
    for cl in CELLS:
        print(f"  {label} {cl} pool names with no score by the first reason, by fill year (" + ", ".join(CELL_REASON_NAMES[cl]) + "):")
        for y, c in sorted(cnt.items()):
            if c.get("rebalances", 0):
                print(f"    {cl} {y}: " + " ".join(f"{c.get(f'ns_{cl}_{rs}', 0)}" for rs in CELL_REASON_NAMES[cl]))


CELL_REASON_NAMES = {c: [REASONS[q] for q in CELL_REASONS[c]] for c in CELLS}


def print_reports(rep, summ):
    b = rep["beta_to_es"]
    print("  realised beta to ES (the cell's daily $ P&L on ES's daily return, $ per 1% ES move; on L's DD days / #463's DD days / all days of the stretch) - FIRST: " + "; ".join(
        f"{c} {b[c]['L']['DD days']['usd_per_1pct_es']:+,.0f} / {b[c]['book']['DD days']['usd_per_1pct_es']:+,.0f} / {b[c]['L']['all WF days']['usd_per_1pct_es']:+,.0f}" for c in CELLS))
    for c in CELLS:
        sd = rep["beta_sides"][c]
        print(f"  {c} [A4] each SIDE's realised beta to ES (per $ of its own notional, L's DD days / all days): " + "; ".join(f"{k} {v['dd_days_L']:+.3f} / {v['all_days']:+.3f}" for k, v in sd.items()) + " (the long side is probably a quality / low-beta sort)")
    for c in CELLS:
        e = rep["ref_episodes"][c]
        print(f"  {c}: P&L inside L's {len(e)} qualifying drawdowns on the stretch: net ${sum(x['cell_pnl'] for x in e):,.0f} over {sum(x['dd_days'] for x in e)} DD days (L's ${sum(x['book_pnl'] for x in e):,.0f}); "
              f"MDL map point: ROC@30k {rep['map_point'][c]['standalone_roc_30k']:.1f}, rho_dd {rep['map_point'][c]['rho_dd']:+.3f}, DO {rep['map_point'][c]['DO']:+.3f}")
    for c in CELLS:
        ov, t = rep["pick_overlap_with_res"][c], rep["turnover"][c]
        print(f"  {c} against RES: daily P&L correlation {rep['corr_with_res'][c]:+.3f} (stretch days; RES's registered line); pick overlap over {ov['rebalances']} rebalances - longs that are RES longs {ov['long_in_res_long']:.0%} / RES shorts {ov['long_in_res_short']:.0%}, "
              f"shorts that are RES shorts {ov['short_in_res_short']:.0%} / RES longs {ov['short_in_res_long']:.0%}")
        q = rep["q21"][c]
        print(f"  {c} against FRONTIER's Q21 stock BAB seat [A4]: " + (f"daily P&L correlation {q['daily_pnl_correlation']:+.3f} over {q['rows']} days; common names: {q['share_of_common_names']}" if q["on_file"] else q["note"]) + " (if both pass they are one finding, counted once)")
        if t.get("transitions"):
            print(f"  {c} persistence: {t['persistence_mean']:.0%} of the names are still in the same tail one rebalance later (long tail {t['persistence_long_mean']:.0%}, short tail {t['persistence_short_mean']:.0%}); turnover: {t['replaced_mean']:.0%} of the names replaced per rebalance on average "
                  f"(median {t['replaced_median']:.0%}, range {t['replaced_min']:.0%} .. {t['replaced_max']:.0%}); if only the changes were traded: ${t['cost_saved_if_only_changes_traded_usd_estimate']:,.0f} less in total (estimate, not judged)")
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
    for c in CELLS:
        print(f"  {c} the 20 largest name-month GAINS (the 3 largest here, the 20 in the Stage A file): " + "; ".join(f"{x['symbol']} {x['side']} {x['date']} ${x['pnl']:,.0f}" for x in rep["top20_gains"][c][:3]))
        print(f"  {c} the SQUEEZE LIST - the 20 largest name-month LOSSES: " + "; ".join(f"{x['symbol']} {x['side']} {x['date']} ${x['pnl']:,.0f}" for x in rep["top20_losses"][c][:20]))
        j = rep["jan2021"][c]
        if j is not None:
            print(f"  {c} JANUARY 2021 in full: net ${j['net']:,.0f} over {len(j['daily'])} sessions (long positions ${j['net_long_positions']:,.0f}, short positions ${j['net_short_positions']:,.0f} over the whole holds that touch the month); daily: "
                  + " ".join(f"{d[5:]}:{v:+,.0f}" for d, v in j["daily"]) + "; worst positions: " + "; ".join(f"{x['symbol']} {x['side']} ${x['pnl']:,.0f}" for x in j["worst"]) + "; best: " + "; ".join(f"{x['symbol']} {x['side']} ${x['pnl']:,.0f}" for x in j["best"]))


DIAG_LW, DIAG_CW = NI.DIAG_LW, NI.DIAG_CW


def print_diagnostics(res, rep, ctx):
    """DEEPER DIAGNOSTICS of the registered reading, D1 and S1 side by side: the cost curve at 0 / 5 / 10 / 20 bps a side, a row per July-June year, the two regime halves, a row per drawdown episode of L on the stretch (the cell's P&L inside it), the LONG and SHORT sides apart and the #70 gate's basis;
    the dollars a year beside every ROC. None of it is a pass route"""
    cells = res["cells"]
    each = lambda f: [f(cells[c], c) for c in CELLS]
    nr = lambda s: f"{s['net']:+,.0f} / {s['roc']:.1f} / {NI.per_year(s['net'], s['years']):+,.0f}"
    print("DIAGNOSTICS - the registered reading, the stretch, D1 and S1 side by side; none of this is a pass route (cells: net $ / ROC@30k / $ a year)")
    print(NI.diag_line("", list(CELLS)))
    print("  COST CURVE - the cost a side")
    for lab, get in (("0 bps", lambda c: c["cost0"]), ("5 bps (the base)", lambda c: c["base"]), ("10 bps", lambda c: c["stress"]["10 bps"]), ("20 bps", lambda c: c["stress"]["20 bps"])):
        print(NI.diag_line(f"  {lab}", each(lambda c, k: nr(get(c)))))
    print("  BY JULY-JUNE YEAR - net $ of the daily series (long side | short side)")
    for y in YEARS:
        print(NI.diag_line(f"  {y}-{(y + 1) % 100:02d}", each(lambda c, k: f"{c['base']['by_year'][y]:+,.0f} ({c['sides']['long side only']['by_year'][y]:+,.0f} | {c['sides']['short side only']['by_year'][y]:+,.0f})")))
    print("  THE TWO REGIME HALVES - then the positions that exited in the half")
    for lab, _a, _b in SUBPERIODS:
        print(NI.diag_line(f"  {lab}", each(lambda c, k: nr(c["sub"][lab]))))
        print(NI.diag_line("    positions", each(lambda c, k: f"{c['sub'][lab]['n_pos']:,}")))
    g = ctx.ref.structure
    print(f"  L'S DRAWDOWN EPISODES on the stretch ({g['episodes']} qualifying, {g['days']} DD days; MDL r1's rule) - the cell's P&L inside each (the DD days: the day after the peak .. the trough) and the episodes it helps")
    for q, e in enumerate(rep["ref_episodes"][CELLS[0]]):
        print(NI.diag_line(f"  {e['first_dd_day']} .. {e['trough']} ${e['depth']:,.0f} ({e['dd_days']} d, L {e['book_pnl']:+,.0f})", [f"{rep['ref_episodes'][c][q]['cell_pnl']:+,.0f}" for c in CELLS]))
    print(NI.diag_line("  all the episodes (the cell's P&L over the DD days)", [f"{sum(x['cell_pnl'] for x in rep['ref_episodes'][c]):+,.0f}" for c in CELLS]))
    print(NI.diag_line("  the episodes the cell helps (cell P&L > 0) of the total", [f"{sum(1 for x in rep['ref_episodes'][c] if x['cell_pnl'] > 0)} of {len(rep['ref_episodes'][c])}" for c in CELLS]))
    print("  THE LONG AND SHORT SIDES APART (net $ / ROC@30k / maxDD)")
    for lab in ("long side only", "short side only"):
        print(NI.diag_line(f"  {lab}", each(lambda c, k: f"{c['sides'][lab]['net']:+,.0f} / {c['sides'][lab]['roc']:.1f} / {c['sides'][lab]['max_dd']:,.0f}")))
    print(f"  #70 GATE BASIS - the cell's DO against L's {g['episodes']} drawdown episodes / {g['days']} DD days on the stretch, beside its random-name null's (the MAX over the 2 cells)")
    print(NI.diag_line("  DO (cell P&L over the DD days / L's loss)", each(lambda c, k: f"{c['gate70']['DO']:+.3f}")))
    print(NI.diag_line("  the null's DO p95", each(lambda c, k: f"{c['gate70']['null_do_p95']:+.3f}" if "null_do_p95" in c["gate70"] else "-")))
    print(NI.diag_line("  the cell's DO above the null's p95", each(lambda c, k: ("yes" if c["gate70"]["DO_above_null_p95"] else "no") if "null_do_p95" in c["gate70"] else "-")))
    print(NI.diag_line("  positive without the best episode", each(lambda c, k: ("yes" if c["gate70"]["positive_without_best_episode"] else "no") if "positive_without_best_episode" in c["gate70"] else "-")))
    print(NI.diag_line("  credited by the beta rule (both betas within 0.20)", each(lambda c, k: "yes" if c["beta"]["within_cap"] else "no")))


# ------------------------------------------------------------------ the hand audit (f): read, apply
def read_audit(path=None):
    """OUT\\shortint_audit.csv (symbol, date, cell, verdict in {keep, data_event}, note) -> a frame, or None when there is no file yet. A data_event row removes that name-month from BOTH cells AND both nulls before anything is computed [(f)]. CHOICE (r17's / NETISS's): the date is the position's
    FILL date - exactly the 'date' of shortint_audit_candidates.csv; a data event belongs to the name-month, so a row covers both cells' listing of it. Refuses a verdict / cell / date it cannot read (a mistyped row must not silently do nothing)"""
    p = path or os.path.join(OUT, "shortint_audit.csv")
    if not os.path.exists(p):
        return None
    df = pd.read_csv(p, dtype=str, keep_default_na=False)
    miss = [c for c in ("symbol", "date", "cell", "verdict") if c not in df.columns]
    if miss:
        refuse(f"refused: shortint_audit.csv lacks the column(s) {miss} (columns: symbol, date, cell, verdict, note) - nothing computed")
    df["symbol"], df["cell"], df["verdict"] = df["symbol"].str.strip(), df["cell"].str.strip().str.upper(), df["verdict"].str.strip().str.lower()
    df["date"] = pd.to_datetime(df["date"].str.strip(), errors="coerce")
    bad = df[~df["verdict"].isin(("keep", "data_event")) | ~df["cell"].isin(CELLS) | df["date"].isna() | (df["symbol"] == "")]
    if len(bad):
        refuse(f"refused: shortint_audit.csv line(s) {[int(i) + 2 for i in bad.index][:10]} have an unreadable date / symbol, a verdict outside keep | data_event, or a cell outside {list(CELLS)} (nothing computed)")
    return df


apply_audit = M17.apply_audit                                                  # r17_resmom's: the data_event rows put on the World as removals (the key is symbol + FILL date); a row that matches no session or no name refuses
unused_audit_rows = M17.unused_audit_rows                                      # r17_resmom's: a data_event row that removed nothing is reported, so a wrong date cannot pass unnoticed
cut_checks = DV.cut_checks                                                     # r18_divrun's: nothing on / after the stage's cut in the World's sessions or the calendar's rows
div_mode = M17.div_mode                                                        # [R1] the cash dividends in / out of the daily return


# ------------------------------------------------------------------ the inputs, loaded once: the pinned files (cut at read), the World, the SHORTINT arrays
def load_sources(cut):
    """the pinned inputs of a stage, each refused if its sha256 differs (nothing computed, lockbox NOT read): NETISS's symbol -> CIK map and share-count facts (read as ONE table each), the five FINRA files [A7] and the asset list [A1], the wide calendar's name changes; every one cut at READ time"""
    mp = NI.load_map()
    d, xinfo = NI.load_facts(cut)
    fx = NI.build_facts(d)
    del d
    fin, finfo = load_finra(cut)
    assets = load_assets()
    nc, ncinfo = load_name_changes(cut)
    return SimpleNamespace(mp=mp, fx=fx, xinfo=xinfo, fin=fin, finfo=finfo, assets=assets, nc=nc, ncinfo=ncinfo)


def load_world(cut, cal, src, need_cal=True):
    """the World through r17_resmom's loaders (every input cut at `cut` inside the calls), the cache's spans before r5_siporb.Data is released, TBIS and ES, and the SHORTINT arrays attached -> (W, D's name count, TBIS rows, TBIS matched, ES meta)"""
    D = M17.load_data(cut)
    nfull = len(D.syms)
    exist = exist_spans(D)
    tbis = D15.load_tbis(cut)
    es_frames, es_meta = D15.load_es(cut)
    full_match = D15.tbis_array(D.days, D.syms, tbis)[1]
    W = M17.build_world(D, cut, es_frames, tbis, cal)
    D15.release(D)
    cut_checks(W, cal, cut)
    attach_shortint(W, src.fin, src.assets, src.nc, exist, src.fx, src.mp, cal)
    return W, nfull, tbis, full_match, es_meta


# ------------------------------------------------------------------ dryload: counts only
def scored_stats(L):
    """COUNTS over a leg's rebalances: per cell the scored names per rebalance (min / median / max, over the rebalances whose pool was not empty) and the rebalances by what they trade (top 50 / the thirds / nothing / uncovered / no file)"""
    out = {}
    for c in CELLS:
        ns = np.array([rec.cell[c].n for rec in L.recs if len(rec.pool)], int)
        out[c] = {"rebalances": int(len(L.recs)), "with_a_pool": int(len(ns)), "min": int(ns.min()) if len(ns) else 0, "median": float(np.median(ns)) if len(ns) else 0.0, "max": int(ns.max()) if len(ns) else 0,
                  "modes": dict(Counter(rec.cell[c].mode for rec in L.recs if len(rec.pool))), "no_pool": int(sum(1 for rec in L.recs if not len(rec.pool))), "traded": int(sum(rec.cell[c].traded for rec in L.recs))}
    return out


def print_scored_stats(label, L, W):
    st = scored_stats(L)
    print(f"  {label} scored names per rebalance (min / median / max over the {st[CELLS[0]]['with_a_pool']} rebalances with a pool of {st[CELLS[0]]['rebalances']}; rebalances trading the top {M17.SPEC['n_side']} a side / the third / nothing / uncovered / no file): "
          + "; ".join(f"{c} {st[c]['min']} / {st[c]['median']:.0f} / {st[c]['max']}, " + " / ".join(f"{st[c]['modes'].get(m, 0)}" for m in MODES) for c in CELLS))
    byy = {c: defaultdict(list) for c in CELLS}
    for rec in L.recs:
        if len(rec.pool):
            for c in CELLS:
                byy[c][int(W.days[rec.f].year)].append(rec.cell[c].n)
    for c in CELLS:
        print(f"    {c} by fill year (rebalances: min / median / max scored): " + "; ".join(f"{y}: {len(v)}: {min(v)} / {np.median(v):.0f} / {max(v)}" for y, v in sorted(byy[c].items())))
    return st


def print_traded(L, W, start_rank):
    """the TRADED rebalances per cell from the walk-forward's start (counts only): how many, by what they trade, by fill year, and the first traded rank of each cell"""
    for c in CELLS:
        tr = [rec for rec in L.recs if rec.cell[c].traded]
        by = Counter(int(W.days[rec.f].year) for rec in tr)
        md = Counter(rec.cell[c].mode for rec in tr)
        print(f"  {c}: {len(tr)} TRADED rebalances (top {M17.SPEC['n_side']} a side {md.get('top', 0)}, the third {md.get('third', 0)}), first traded rank " + (f"{W.days[tr[0].r]:%Y-%m-%d} (filled {W.days[tr[0].f]:%Y-%m-%d})" if tr else "none")
              + "; by fill year: " + ", ".join(f"{y}: {n}" for y, n in sorted(by.items())) + f"; of the {len(L.recs)} rebalances in the registered stretch {sum(1 for rec in L.recs if rec.sc.k < 0)} have no usable file and "
              f"{sum(1 for rec in L.recs if rec.sc.k >= 0 and not rec.sc.covered)} are under {SPEC['cover']:.0%} coverage")


def print_sources_counts(src, W):
    """the pinned FINRA / asset / name-change files as read, and NETISS's map and share-count files (its print), COUNTS only"""
    print_files_block(src.fin, src.finfo, src.assets, src.nc, src.ncinfo)
    NI.print_data_counts(src.mp, src.xinfo, src.fx, W)
    print(f"  S1's multi-class refusal: {W.si.n_multi_ciks} CIKs carry two or more usable map symbols (a firm's share count against one class's short interest: no S1 score for any of their symbols); {int(W.si.multi.sum())} of the {W.S:,} names ever in the universe are among them")
    th = W.si.th
    nchg = int((~W.si.plain).sum())
    print(f"  [SYMBOLS] ticker histories: {len(th.segs):,} cache names; {nchg} of the {W.S:,} names ever in the universe have a ticker other than their cache ticker at some date or an unresolved chain "
          f"({sum(1 for s in W.si.syms if not th.known[s])} unresolved); tickers held by two or more cache names on overlapping dates: {len(th.holders)}")


def dryload():
    """the WF inputs through every loader (cut at 2025-06-30) and COUNTS only: the pinned FINRA files as read, the files and their market codes, the known-at table, the funds, the join and the coverage per rank, the walk-forward's start under the 90% rule, the scored names per rank and cell and every
    no-score reason by year, the revised-row counts, the pool and the sides by what they trade (both readings), the traded rebalances per cell, TBIS rows, ES coverage. NO short interest, ADV, share count, score value, return, P&L or Stage A statistic is printed: the scores are computed in memory only
    to COUNT the names each rule removes, no unit path is built"""
    prereg_ok()
    t0 = time.time()
    src = load_sources(S.LB0)
    cal, winfo = M17.wide_load(S.LB0, need=False, enforce=False)                              # CHOICE (r18's / NETISS's): the dryload counts on the calendar when it exists and REPORTS its sha status (only Stage A / B refuse an unregistered one)
    W, nfull, tbis, full_match, es_meta = load_world(S.LB0, cal, src)
    print(f"dryload: inputs ready ({time.time() - t0:.0f}s); every input cut to dates < {S.LB0:%Y-%m-%d}; ES masters {es_meta['raw']['filename']} / {es_meta['adj']['filename']}")
    wf = (W.days >= WF0) & (W.days <= PRE_END)
    print(f"sessions: {W.T:,} on the market calendar ({W.days[0]:%Y-%m-%d} .. {W.days[-1]:%Y-%m-%d}; the cache's first session is {CACHE_FIRST_SESSION:%Y-%m-%d}), {int(wf.sum()):,} inside the WF stretch (positions exited {WF0:%Y-%m-%d} .. {PRE_END:%Y-%m-%d}); "
          f"symbols: {nfull:,} in the cache after SIPORB's price / volume floor, {W.S:,} ever in the universe")
    usz, yrs = W.U.sum(axis=1), W.days.year.to_numpy()
    print("universe size per session by year (sessions with a universe: min / median / max): " + "; ".join(
        f"{y}: {int((m := (yrs == y) & (usz > 0)).sum())} sessions {int(usz[m].min())} / {int(np.median(usz[m]))} / {int(usz[m].max())}" for y in sorted(set(yrs)) if ((yrs == y) & (usz > 0)).any()))
    print_sources_counts(src, W)
    print_market_codes(src.fin, src.finfo)
    print_known_at(known_at_rows(W))
    ranks = built_ranks(W, WF0, PRE_END)
    fo = funds_out_rows(W, ranks)
    print(f"[A1] FUNDS out of the universe and the null's pool, the list for the hand check ({len(fo)} names at some rank; by asset-list title {sum(1 for f_ in fo if f_['by'] != 'FINRA issue name')}, by FINRA issue name only {sum(1 for f_ in fo if f_['by'] == 'FINRA issue name')}): "
          + "; ".join(f"{f_['symbol']} ({f_['by']}{'; ' + f_['title_tokens'] if f_['title_tokens'] else ''}; {f_['ranks']} ranks)" for f_ in fo))
    crows = coverage_rows(W, ranks)
    start_rank, lo = wf_start(W, ranks)
    start_s = None if start_rank is None else f"{W.days[start_rank]:%Y-%m-%d}"
    print_join(crows)
    print_coverage(crows, start_s, lo)
    srows = score_report(W, ranks, values=False)
    print_score_report(srows, values=False)
    Lr, Lk = si_build(W, WF0, PRE_END, "remove", "drop", units=False, counts_only=True), si_build(W, WF0, PRE_END, "naive", "drop", units=False, counts_only=True)
    Lv = si_build(W, WF0, PRE_END, "remove", "asis", units=False, counts_only=True)
    r_all, f_all, x_all = M17.rm_schedule(W.days)
    inwf = [(r, f, x) for r, f, x in zip(r_all.tolist(), f_all.tolist(), x_all.tolist()) if x >= 0 and WF0 <= W.days[x] <= PRE_END]
    first_full = min((r for r, f, x in inwf if r >= M17.SPEC["win"] - 1), default=None)
    print(f"rebalances: {len(Lr.recs)} in WF (positions that exit {WF0:%Y-%m-%d} .. {PRE_END:%Y-%m-%d} with a full {M17.SPEC['win']}-session window)"
          + (f"; the first rank session with a full window is {W.days[first_full]:%Y-%m-%d} (filled {W.days[first_full + 1]:%Y-%m-%d})" if first_full is not None else "")
          + f"; {sum(1 for r, f, x in inwf if r < M17.SPEC['win'] - 1)} earlier ranks are warm-up; the stage's last rank has no next fill: unresolved, out")
    by = defaultdict(list)
    for rec in Lr.recs:
        by[int(W.days[rec.f].year)].append((rec.nu, rec.nfull, len(rec.pool)))
    print("names with a full window (>= 230 own returns and >= 230 ES pairs) per rebalance, by fill year (universe less the funds / full window / eligible pool: min - mean - max): " + "; ".join(
        f"{y}: {len(v)} rebalances, universe {min(a for a, b, c in v)}-{np.mean([a for a, b, c in v]):.0f}-{max(a for a, b, c in v)}, full {min(b for a, b, c in v)}-{np.mean([b for a, b, c in v]):.0f}-{max(b for a, b, c in v)}, "
        f"pool {min(c for a, b, c in v)}-{np.mean([c for a, b, c in v]):.0f}-{max(c for a, b, c in v)}" for y, v in sorted(by.items())))
    print_scored_stats("registered (a flag inside the hold removes the name)", Lr, W)
    print_scored(f"registered (the fallback rule: {SPEC['min_scored']} scored names or more -> {M17.SPEC['n_side']} a side, fewer -> the top / bottom third, at least {SPEC['min_side']} a side, else nothing; under {SPEC['cover']:.0%} coverage or no usable file -> nothing)", Lr.cnt)
    print_scored_stats("look-ahead (names flagged inside the hold stay)", Lk, W)
    print_scored_stats("[A11] revised-rows twin (FINRA's revised rows scored as they stand)", Lv, W)
    NI.print_counts("registered (a flag inside the hold removes the name)", Lr.cnt)
    NI.print_counts("look-ahead (names flagged inside the hold stay, on their naive raw path)", Lk.cnt)
    M17.print_spin_counts("registered", Lr.cnt)
    print(f"TRADED REBALANCES from the walk-forward's start {start_s} (counts only):")
    print_traded(Lr, W, start_s)
    print(f"TBIS flags: {len(tbis):,} symbol-days listed before the cut, {full_match:,} match a session and a cached name, {W.tbis_rows[1]:,} a name that is ever in the universe; every listed row is a flag")
    if W.ca is not None:
        M17.print_wide(W.ca)
    else:
        print(f"wide corporate-actions calendar [R1]: not on file yet ({winfo['path']}) - Stage A refuses until it is on file and WIDE_CA_SHA is set; this dryload ran without dividends, without name changes and without [A3]'s calendar side")
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
    if os.path.exists(os.path.join(OUT, READ_FLAG)):                                       # CHOICE (r17's / r18's / NETISS's): once the lockbox has been read Stage A is frozen (a re-run could change the cell or c after the fact)
        refuse(f"Stage A refused: Stage B has already read the lockbox - Stage A is frozen ({READ_FLAG})")
    pok = prereg_ok()
    cal, winfo = M17.wide_load(S.LB0)                                                      # [R1] refuses (nothing computed) when the wide calendar is not on file / not registered / not the registered file
    src = load_sources(S.LB0)                                                              # [A1] / [A7] / [A8] refuse (nothing computed) when a pinned file is not on file / not the registered file / disagrees with its manifest
    B, legs_meta = A13.load_463()                                                          # the book first: cheap, and a book that does not reproduce stops everything
    bk, dd, S12 = book_checks(B)
    print(f"BOOK #463 WF check (must be {BOOK_WF[0]} / {BOOK_WF[1]}): ROC@30k {bk['roc']:.2f} Sortino {bk['sortino']:.3f}; deepest drawdown ${dd['deepest']:,.0f} (must be ${DEEPEST_WF:,.0f}), "
          f"{dd['episodes']} qualifying episodes, {dd['days']} DD days, {dd['weeks']} DD weeks, by year {dd['by_year']}, the 2020-03-03 .. 03-27 episode {'found' if dd['episode_2020'] else 'NOT FOUND'} (the full 2016-07-01 .. 2025-06-29 WF: this family's own stretch is shorter and printed below)")
    if CHECK_BOOK and not (bk["ok"] and dd["ok"]):
        refuse("Stage A refused: the #463 records do not reproduce the registered WF numbers / drawdown structure (the prereg's [T5] facts) - fix the input first (nothing computed)")
    ref = DV.ref_load(B, check_facts=CHECK_BOOK)                                           # RESMOM's WF line -> the REFERENCE book L: refuses (nothing computed) unless the file is the registered one and L reproduces its registered numbers (on the FULL WF)
    DV.print_reference(ref)
    msha = manifest_sha()
    print(f"SIPORB cache manifest sha256: {msha} (registered: {D15.MANIFEST_PREFIX}...)")
    if CHECK_BOOK and not (msha and msha.startswith(D15.MANIFEST_PREFIX)):
        refuse("Stage A refused: the SIPORB cache manifest is missing or is not the registered photograph of the vendor (a re-pull must never be mixed in) - nothing computed")
    t0 = time.time()
    audit = read_audit()
    W, nfull, tbis, _fm, es_meta = load_world(S.LB0, cal, src)                             # every input is cut to dates < 2025-06-30 inside these calls, before anything is computed
    if CHECK_BOOK and W.days[0] != CACHE_FIRST_SESSION:                                    # F is unknown before the cache's first session: the rules are written for a World that starts there
        refuse(f"Stage A refused: the World starts {W.days[0]:%Y-%m-%d}, not at the cache's registered first session {CACHE_FIRST_SESSION:%Y-%m-%d} (nothing computed)")
    wf = (W.days >= WF0) & (W.days <= PRE_END)
    kmiss = int((~np.isfinite(W.k[wf])).sum())
    print(f"world ready ({time.time() - t0:.0f}s): {int(wf.sum()):,} sessions in the registered WF {WF0:%Y-%m-%d} .. {PRE_END:%Y-%m-%d}, {W.S:,} names ever in the universe, k_t (read only by the borrow stress rows) undefined on {kmiss} WF sessions; ES masters "
          f"{es_meta['raw']['filename']} / {es_meta['adj']['filename']}", flush=True)
    es_txt, es_rec = M17.es_report(W)
    print(es_txt)
    M17.print_wide(W.ca)
    out = {"prereg_sha256_lf": PREREG_SHA, "prereg_verified": pok["verified"], "prereg_committed": pok["committed"], **stamp(), "judged": False, "not_judgeable": False, "stageA": None, "candidate": None, "pending_hand_audit": None,
           "book_check": bk, "dd_structure": dd, "reference": DV.ref_record(ref), "manifest_sha256": msha, "es_return": es_rec, "wide_calendar": W.ca, "k_undefined_wf_sessions": kmiss, "files": {k: FILE_SHA[k] for k in FILE_SHA},
           "finra": {k: v for k, v in src.finfo.items() if k not in ("rows_by_file_and_market", "sha256")}, "assets": src.assets.info, "name_changes": src.ncinfo, "facts": {k: v for k, v in src.xinfo.items() if k != "sha256"}, "map": {k: v for k, v in src.mp.info.items() if k != "sha256"}}
    aud_n = apply_audit(W, audit)
    asha = file_sha(os.path.join(OUT, "shortint_audit.csv"))
    print("audit file: " + ("none yet" if audit is None else f"{aud_n['rows']} rows ({aud_n['keep']} keep, {aud_n['data_event']} data_event: removed from the cells AND the nulls)"))
    rows = A13.book_rows(B, W)
    # ---- BEFORE ANY P&L: the files, the known-at table, the funds, the join and the coverage, the scores' counts and facts (the leg is never built, nothing is costed)
    ranks = built_ranks(W, WF0, PRE_END)
    print_sources_counts(src, W)
    print_market_codes(src.fin, src.finfo)
    kar = known_at_rows(W)
    print_known_at(kar)
    fo = funds_out_rows(W, ranks)
    os.makedirs(OUT, exist_ok=True)
    pd.DataFrame(fo).to_csv(os.path.join(OUT, "shortint_funds_out.csv"), index=False)
    print(f"[A1] FUNDS out of the universe and the null's pool: {len(fo)} names at some rank (the list is written to shortint_funds_out.csv for the hand check before any score): " + "; ".join(f"{f_['symbol']} ({f_['by']}; {f_['ranks']} ranks)" for f_ in fo))
    crows = coverage_rows(W, ranks)
    start_rank, lo = wf_start(W, ranks)
    start_s = None if start_rank is None else f"{W.days[start_rank]:%Y-%m-%d}"
    print_join(crows)
    print_coverage(crows, start_s, lo)
    srows = score_report(W, ranks, values=True)
    unsc = unscored_by_name(W, ranks)
    print_score_report(srows, values=True)
    print_unscored_by_name(unsc)
    n_reb = sum(1 for c in crows if start_s is not None and c["covered"] and c["rank"] >= start_s)
    out.update({"known_at": kar, "coverage_by_rank": crows, "start_rank": start_s, "stretch_lo": None if lo is None else f"{lo:%Y-%m-%d}", "covered_rebalances": n_reb, "funds_out": fo, "unscored_by_name": unsc,
                "score_by_rank": [{k: v for k, v in r_.items() if k != "cells"} | {"cells": {c: {k: v for k, v in x.items() if k != "values"} for c, x in r_["cells"].items()}} for r_ in srows],
                "percentiles_by_year": percentiles_by_year(srows)})
    if start_rank is None or n_reb < SPEC["min_reb"]:                                       # [A2] NOT JUDGEABLE: stops BEFORE any return is computed - MANAGER decides (CHOICE: 'rebalances' = the covered ranks from the start rank; a rank under 90% after it is not counted)
        msg = ("SHORTINT r1 is NOT JUDGEABLE [A2]: " + ("no rank reaches 90% coverage" if start_rank is None else f"{n_reb} covered rebalances from the start rank {start_s} (fewer than {SPEC['min_reb']})")
               + " - Stage A stops here, before any return is computed; MANAGER decides.")
        print(msg)
        out.update({"not_judgeable": True, "not_judgeable_reason": msg})
        dump(out, "shortint_stageA.json")
        return out
    ctx = make_ctx(B, S12, ref, lo)
    print_book_line(B, ctx, bk)
    t1 = time.time()
    resR, objR = evaluate(W, B, rows, ctx, "remove", NREP, 0, full=True, rev_mode="drop", announce=lambda nul, L: print_power(nul))
    print(f"registered reading done ({time.time() - t1:.0f}s: the leg, the {NREP} random-name draws per cell FIRST, the cells, the stress rows, the borrow curve, the twins)", flush=True)
    unused = unused_audit_rows(W, audit)
    if unused:
        print(f"  NOTE: {len(unused)} audit data_event row(s) removed nothing (the name was not in that fill session's universe): {unused[:5]}")
    t1 = time.time()
    resV, objV = evaluate(W, B, rows, ctx, "remove", 0, 0, full=False, rev_mode="asis")
    resK, objK = evaluate(W, B, rows, ctx, "naive", 0, 0, full=False, rev_mode="drop")
    with div_mode(W, False):                                                               # [R1] the no-dividend version of both cells (the picks stay; the P&L without the cash dividends): a REPORTED row, never the verdict
        resD = evaluate(W, B, rows, ctx, "remove", 0, 0, full=False, rev_mode="drop")[0]
    print(f"revised-rows twin, look-ahead and no-dividend readings done ({time.time() - t1:.0f}s)", flush=True)
    spin = {"registered_reading": {c: NI.ni_spin_counts(objR.legs, c) for c in CELLS}, "look_ahead_reading_kept_at_naive_price_pnl": {c: NI.ni_spin_counts(objK.legs, c) for c in CELLS}}
    rep, cands = reports(W, B, rows, ctx, objR, resR["cells"], tbis, D15.asset_status(), legs_meta)
    cells = resR["cells"]
    passing, cand = stage_a_flow(cells)
    ast = M17.audit_status(cands, audit)
    pd.DataFrame([r_ for c in CELLS for r_ in cands[c]]).to_csv(os.path.join(OUT, "shortint_audit_candidates.csv"), index=False)
    pd.DataFrame([r_ for c in CELLS for r_ in rep["top20_gains"][c] + rep["top20_losses"][c]]).to_csv(os.path.join(OUT, "shortint_name_month_extremes.csv"), index=False)
    print(f"WF {ctx.lo:%Y-%m-%d} -> {ctx.hi:%Y-%m-%d} ({int(((W.days >= ctx.lo) & (W.days <= ctx.hi)).sum()):,} sessions) - the REGISTERED reading (a hygiene flag inside the hold removes the position; FINRA-revised rows give no score)")
    print_cells(resR, ast)
    print_borrow(resR)
    print("  look-ahead reading (positions with a flag INSIDE the hold kept at naive raw P&L) [O3] (reported, no null): " + "; ".join(f"{c}: {NI.row(c, resK['cells'][c])[4:]}" for c in CELLS))
    print("  no-dividend version [R1] (the cash dividends left out of the P&L; REPORTED, never the verdict): " + "; ".join(
        f"{c}: net ${resD['cells'][c]['base']['net']:,.0f} ROC@30k {resD['cells'][c]['base']['roc']:.1f} (the dividends {'add' if cells[c]['base']['net'] >= resD['cells'][c]['base']['net'] else 'cost'} ${abs(cells[c]['base']['net'] - resD['cells'][c]['base']['net']):,.0f})" for c in CELLS))
    with patched(NI, CELLS=CELLS):
        NI.print_spin_picks(spin)
    print_twins(resR, resV)
    print_reports(rep, cells)
    print_diagnostics(resR, rep, ctx)
    NI.print_counts("L (registered)", objR.legs.cnt)
    NI.print_counts("L (look-ahead)", objK.legs.cnt)
    print_scored("L (registered)", objR.legs.cnt)
    M17.print_spin_counts("L (registered)", objR.legs.cnt)
    print(f"  audit candidates (the {AUDIT_N} largest gains per cell, with the settlement, its FINRA file, the short-interest rows, FINRA's ADV / days to cover, our ADV and the share-count facts) -> {os.path.join(OUT, 'shortint_audit_candidates.csv')}; the 20 largest name-month gains AND losses "
          f"-> shortint_name_month_extremes.csv; the hand audit (f) is the lead's (a data event found: a row symbol, date, cell, data_event in shortint_audit.csv and run stage_a again); audit rows found per list: " + ", ".join(f"{k} top-{AUDIT_N} {v['audited']}/{v['listed']}" for k, v in ast.items()))
    out.update({"judged": True, "pending_hand_audit": passing, "stretch": {"lo": f"{ctx.lo:%Y-%m-%d}", "hi": f"{ctx.hi:%Y-%m-%d}", "book463": R11.stats(np.asarray(B.raw, float)[B.mask(ctx.lo, ctx.hi)], B.index[B.mask(ctx.lo, ctx.hi)]),
                                                                                  "L": ctx.ref.stats, "L_structure": ctx.ref.structure},
                "stageA": {"cells": cells, "null": resR["null"], "pass_cells": passing},
                "candidate": ({"cell": cand, "c": cells[cand]["A2"]["c"], "std_book": cells[cand]["A2"]["std_book"], "std_cell": cells[cand]["A2"]["std_cell"], "window": cells[cand]["A2"]["window"], "a2_book_roc": cells[cand]["A2"]["roc"],
                               "a2_reference_roc": cells[cand]["A2"]["reference"]["roc"], "incremental_pass": cells[cand]["A2"]["incremental_pass"], "incremental_credit": cells[cand]["A2"]["incremental_credit"],
                               "book_shadow_line": cells[cand]["A2"]["incremental_credit"], "beta_within_cap": cells[cand]["beta"]["within_cap"], "also_passes": [c for c in passing if c != cand]} if cand else None),
                "parity": {c: {"net": cells[c]["base"]["net"], "n_pos": cells[c]["base"]["n_pos"], "n_units": cells[c]["base"]["n_units"]} for c in CELLS},
                "audit": aud_n, "audit_sha256": asha, "audit_status": ast, "spin_counts": spin,
                "revised_rows_twin": {"cells": {c: {k: resV["cells"][c][k] for k in ("base", "stress", "seat", "A2")} for c in CELLS}},
                "no_dividend_reading": {"cells": {c: {k: resD["cells"][c][k] for k in ("base", "stress", "seat", "A2")} for c in CELLS}, "dividends_add_net": {c: cells[c]["base"]["net"] - resD["cells"][c]["base"]["net"] for c in CELLS}},
                "kept_naive_reading": {"cells": {c: {k: resK["cells"][c][k] for k in ("base", "seat", "A2")} for c in CELLS}},
                "hygiene_counts_by_year": {"registered": {y: dict(c) for y, c in sorted(objR.legs.cnt.items())}, "look_ahead": {y: dict(c) for y, c in sorted(objK.legs.cnt.items())}},
                "reports": rep, "es_masters": es_meta})
    dump(out, "shortint_stageA.json")
    for c in passing:
        a2 = cells[c]["A2"]
        print(f"Stage A (a)-(e) pass, (f) awaits the hand audit - cell {c}; WF ROC@30k {cells[c]['base']['roc']:.1f} (${cells[c]['usd_year']:,.0f} a year); A2 (a report): c x{a2['c']:.4g} set by volatility, L + c x cell ROC@30k {a2['roc']:.2f} / Sortino {a2['sortino']:.3f} against L's "
              f"{a2['reference']['roc']:.2f} / {a2['reference']['sortino']:.3f} -> " + ("an INCREMENTAL PASS: MANAGER #70's gate follows (the cell's DO and its null's on L's drawdown days), then at most one forward book line"
                                                                                             if a2["incremental_credit"] else "no credited incremental pass: no book line" + (" (the numbers pass, the beta rule refuses the credit)" if a2["incremental_pass"] else "")))
    if passing:
        print(f"SHORTINT Stage A: (a)-(e) pass for {passing}; (f) AWAITS THE HAND AUDIT of the {AUDIT_N} largest contributors (the harness never decides it); candidate {cand}. Stage B needs the lead's go-flag {GO_FLAG} (written after the hand audit, on the stock families' one sealed-year day) "
              "and the lockbox year's FINRA files pinned (LB_FINRA: a second extract, pinned by sha256 in a dated addendum).")
    else:
        print("SHORTINT Stage A: FAIL - no cell passes (a)-(e) (" + "; ".join(f"{c}: " + ", ".join(k for k, v in cells[c]['checks'].items() if not v) for c in CELLS) +
              ") - SHORTINT r1 is dead; no other horizons, thresholds or scores are tried; the lockbox stays sealed.")
    pm = peak_mb()
    print(f"stage_a took {time.time() - t0:.0f}s" + (f", peak memory {pm:,.0f} MB" if pm else ""))
    return out


# ------------------------------------------------------------------ Stage B: the one read (refuses unless the lead's go-flag is on file)
def stage_b():
    """STAGE B (LB, once, on the stock families' one sealed-year day): REFUSES unless the lead's go-flag shortint_stageB_GO.flag is on file (the lead writes it after the hand audit (f) and only on that day; CHOICE (r18's / NETISS's): its EXISTENCE is the sign-off - its text is stored with the read and never
    parsed), a Stage A candidate is on file AND the lockbox year's FINRA files are pinned (LB_FINRA: the pinned pull stops at the settlement of 2025-05-30 and shrt20250613.csv is quarantined [A8], so the sealed year's short interest needs a SECOND extract, pinned by sha256 in a dated addendum before
    Stage B can read one row of it; None = refuse; a S1 candidate also needs NETISS's LB_FACTS). The sealed year is the LEG's standalone veto (r17_resmom's: >= 10 monthly rebalances, net > 0, net > 0 without its top name-month). The book add (#463 + c x the cell at Stage A's frozen c) is computed,
    printed and stored as book_add_reported - NEVER part of the pass. Every refusal is before the read flag; the flag is written (exclusively) only after every load, every check and the whole result are in hand"""
    go, flag = os.path.join(OUT, GO_FLAG), os.path.join(OUT, READ_FLAG)
    if not os.path.exists(go):
        refuse(f"Stage B refused: the lead's go-flag {GO_FLAG} is not on file - the hand audit (f) and the sealed-year day are the lead's call; the lockbox stays sealed {TAIL}")
    if os.path.exists(flag):
        refuse(f"Stage B refused: the lockbox was already read once ({READ_FLAG})")
    pa = os.path.join(OUT, "shortint_stageA.json")
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
    if sa.get("audit_sha256") != file_sha(os.path.join(OUT, "shortint_audit.csv")):
        refuse("Stage B refused: shortint_audit.csv is not the file Stage A ran with (it changed, or went missing) - run stage_a again (lockbox NOT read)")
    cell = cand["cell"]
    try:
        c = float(cand["c"])
    except (TypeError, ValueError):
        c = float("nan")
    if cell not in CELLS or not (math.isfinite(c) and c > 0):                                  # c is a volatility ratio: any positive number is a frozen size, but NaN / 0 / missing is a broken file
        refuse(f"Stage B refused: the frozen cell {cand.get('cell')} / size c {cand.get('c')} is not one of {CELLS} / a positive number (lockbox NOT read)")
    if not (isinstance(LB_FINRA, dict) and set(LB_FINRA) == set(FINRA_KEYS)):
        refuse("Stage B refused: the lockbox year's FINRA files are not pinned (LB_FINRA is None: the pinned pull stops at the settlement of 2025-05-30 and shrt20250613.csv is quarantined [A8] - the sealed year's short interest comes from a SECOND extract, and a dated pre-data addendum "
               "must pin its five files by sha256 before Stage B can read one row of the sealed year) - lockbox NOT read")
    if cell == "S1" and not (isinstance(NI.LB_FACTS, dict) and set(NI.LB_FACTS) == {"facts", "facts_add"}):
        refuse("Stage B refused: the S1 candidate needs the lockbox year's share facts and they are not pinned (r21_netiss.LB_FACTS is None - a dated addendum pins that second extract) - lockbox NOT read")
    go_text = open(go).read()[:500]
    lb_files, lb_shas = {**FILES, **{k: v[0] for k, v in LB_FINRA.items()}}, {**FILE_SHA, **{k: v[1] for k, v in LB_FINRA.items()}}
    B, legs_meta = A13.load_463()                                                              # every input is loaded and checked BEFORE the flag: a bad file cannot burn the lockbox
    bk = A13.book_check(B, LB0, LB1, BOOK_LB)
    print(f"BOOK #463 LB check (must be {BOOK_LB[0]} / {BOOK_LB[1]}): ROC@30k {bk['roc']:.2f} Sortino {bk['sortino']:.3f}")
    if CHECK_BOOK and not bk["ok"]:
        refuse("Stage B refused: the #463 records do not reproduce its LB numbers - settle the end-date convention first (lockbox NOT read)")
    msha = manifest_sha()
    if CHECK_BOOK and not (msha and msha.startswith(D15.MANIFEST_PREFIX) and msha == sa.get("manifest_sha256")):
        refuse("Stage B refused: the SIPORB cache manifest is not the one Stage A ran on (a re-pull must never be mixed in) - lockbox NOT read")
    cal, winfo = M17.wide_load(S.END)                                                          # the same registered calendar, cut at the lockbox's end
    with patched(THIS, FILES=lb_files, FILE_SHA=lb_shas, QUARANTINED=()), contextlib.ExitStack() as es:      # the lockbox year's extract is read through the same loaders, under its own pinned shas (CHOICE: the second extract's own addendum decides what is quarantined in it - the first pull's quarantine [A8] does not apply to it)
        if cell == "S1":
            es.enter_context(patched(NI, FILES={**NI.FILES, **{k: v[0] for k, v in NI.LB_FACTS.items()}}, FILE_SHA={**NI.FILE_SHA, **{k: v[1] for k, v in NI.LB_FACTS.items()}}))
        src = load_sources(S.END)
    audit = read_audit()
    W, nfull, tbis, _fm, es_meta = load_world(S.END, cal, src)
    apply_audit(W, audit)
    rows = A13.book_rows(B, W)
    hole_txt, hole_rec = M17.es_report(W, LB0, LB1)                                            # the ES holes that reach the lockbox: printed and stored with the read
    ctx_lo = TS(sa["stretch"]["lo"])                                                           # the stretch Stage A ran on (it starts at the first rank at or above 90% coverage)
    Lw = si_build(W, WF0, PRE_END)                                                             # Stage A's WF numbers (and the frozen c) must reproduce on Stage B's data (a cache or code drift stops it BEFORE the read)
    run = M17.run_cell(W, cell_leg(Lw, cell), D15.l1_cfg())                                    # CHOICE: only the candidate cell is re-read (it is the only one Stage B reads)
    xw = D15.to_B(run.x, rows, B.n)
    st, ref = D15.cell_stats(B, xw, D15.to_B(run.cnt, rows, B.n), ctx_lo, PRE_END, run, years=YEARS), sa["parity"][cell]
    print(f"WF re-read on Stage B's data: {cell} positions {st['n_pos']:,} (Stage A {ref['n_pos']:,}), net ${st['net']:,.0f} (Stage A ${ref['net']:,.0f})")
    if st["n_pos"] != ref["n_pos"] or st["n_units"] != ref["n_units"] or abs(st["net"] - ref["net"]) > max(1.0, 1e-6 * abs(ref["net"])):
        refuse(f"Stage B refused: the WF numbers of {cell} do not reproduce on Stage B's data - the cache or the code changed since Stage A (lockbox NOT read)")
    c2 = plain_a2(B, xw, ctx_lo, PRE_END)["c"]
    w2 = a2_window(ctx_lo)
    print(f"  frozen size {cell}: c x{c:.6g} (Stage A) vs x{c2:.6g} recomputed from {w2[0]:%Y-%m-%d} .. {w2[1]:%Y-%m-%d} on Stage B's data")
    if not (math.isfinite(c2) and abs(c2 - c) <= 1e-9 * c):
        refuse(f"Stage B refused: the volatility-set size c of {cell} does not reproduce on Stage B's data - the cache or the code changed since Stage A (lockbox NOT read)")
    L = si_build(W, LB0, LB1)                                                                  # CHOICE (r15's order): the whole LB result is computed, nothing shown, BEFORE the flag
    run = M17.run_cell(W, cell_leg(L, cell), D15.l1_cfg(), pos=True)
    xB, cB = D15.to_B(run.x, rows, B.n), D15.to_B(run.cnt, rows, B.n)
    leg = D15.cell_stats(B, xB, cB, LB0, LB1, run, years=YEARS)
    r = D15.book_at(B, xB, c, LB0, LB1)                                                        # the book add at the FROZEN c - c is never re-set on the sealed year
    would = M17.book_add_would_clear(r)                                                        # the old sealed-year bar (#463's own LB numbers, 155.54 / 4.150): reported, never judged
    chk = M17.b_checks(leg)
    ok = all(chk.values())                                                                     # the pass is the LEG's veto - the book add below is a report and is not in this line
    add = {"c": c, "roc": r["roc"], "sortino": r["sortino"], "net": r["net"], "max_dd": r["max_dd"], "reference": {"roc": RULES["b_roc"], "sortino": RULES["b_sort"]}, "would_have_cleared": would,
           "note": "reported, never a pass (MANAGER #48): the forward record decides any book add (owner call)"}
    cnt = {y: dict(v) for y, v in sorted(L.cnt.items())}
    cands = si_candidate_rows(W, L, cell, run, tbis, D15.asset_status(), 20)
    text = json.dumps({"cell": cell, "c": c, "go_flag": go_text, "book_check": bk, "es_masters": es_meta, "leg": leg, "checks": chk, "pass": bool(ok), "book_add_reported": add, "es_return_lb": hole_rec, "wide_calendar": W.ca,
                       "lockbox_finra": {k: lb_shas[k] for k in FINRA_KEYS}, "lockbox_finra_counts": {k: v for k, v in src.finfo.items() if k not in ("rows_by_file_and_market", "sha256")}, "hygiene_counts_by_year": cnt, "top_name_months": cands, **stamp(), "prereg_sha256_lf": PREREG_SHA},
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
        print("SHORTINT Stage B: " + ("PASS - the leg survives its sealed year: it goes to a computed no-order FORWARD SHADOW (Stage C) with its own bar, logged by research id; the book add above is a report - "
                                      "the forward record decides any book add, and opening any account is the owner's decision (owner call)." if ok else
                                      "FAIL - the leg is vetoed by its sealed year: SHORTINT r1 is dead; ledger + memory."))
    with open(flag, "x") as f:                                                                 # exclusive create: the one read starts here - what is left is two writes and a print
        f.write(pd.Timestamp.now().isoformat())
    with open(os.path.join(OUT, "shortint_stageB.json"), "w") as f:
        f.write(text)
    print(buf.getvalue().rstrip())
    pm = peak_mb()
    if pm:
        print(f"peak memory {pm:,.0f} MB")
    return ok


# ------------------------------------------------------------------ test support: hand-made FINRA pulls, hand-made worlds with hand-made short interest, and plain-python recounts of every join, score, pool, pick and path (independent of the vectorised code)
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


def frow(s, sym, si, name=None, mkt="NNM", psi=None, split="", adv=100000, dtc=1.0, rev="", src=None, exch="Q"):
    """one hand-made FINRA row (the flat file's twelve columns, as text): settlement s, symbol, short interest (None = blank, a string is written as given), issue name (default 'SYM Common Stock'), market code, FINRA's own previous short interest / split flag / ADV /
    days to cover / revision flag and the source file (default shrtYYYYMMDD.csv)"""
    d = f"{TS(s):%Y-%m-%d}"
    sv = "" if si is None else str(si)
    return (d, sym, (sym + " Common Stock") if name is None else name, exch, mkt, sv, ("" if si is None else str(si if psi is None else psi)), split, str(adv), str(dtc), rev, src or f"shrt{d.replace('-', '')}.csv")


def write_flat(path, rows, crlf=False):
    """a flat file in the registered layout (12 columns, the header first); returns its sha256 (of the bytes)"""
    import csv
    with open(path, "w", newline="") as f:
        w = csv.writer(f, lineterminator="\r\n" if crlf else "\n")
        w.writerow(FLAT_COLS)
        for r in rows:
            w.writerow(r)
    return M17.sha_raw(path)


def fake_pull(root, rows, release=None, quarantine=QUARANTINED, schedule_extra=(), name="finra", probe_extra=()):
    """the five FINRA files of a synthetic pull, laid out as the real ones (folder `name` under root): the flat file; the manifest (out_sha256, rows, files, first, last, the quarantine list, rows by file and market code, the release date of every file); the schedule CSV (one row per
    settlement in `release` {settlement 'YYYY-MM-DD': release 'YYYY-MM-DD' | None = no row} + schedule_extra rows (settlement, release) - the page lists the year ahead); the provenance (a url / size / sha256 entry per file read and one for each quarantined file, never read); the date probe (status 200 for
    every settlement and quarantined date, 403 elsewhere). -> SimpleNamespace(files, shas (each file's sha256 of its bytes), dir, manifest)"""
    d = os.path.join(root, name)
    os.makedirs(os.path.join(d, "files"), exist_ok=True)
    flat = os.path.join(d, "finra_shortint_flat.csv")
    sha_flat = write_flat(flat, rows)
    srcs = sorted({r[11] for r in rows})
    by = defaultdict(Counter)
    for r in rows:
        if str(r[1]).strip():                                                           # the manifest counts the rows that carry a symbol (the loader drops, and counts, the others)
            by[r[11]][r[4]] += 1
    rel = release or {}
    day_of = lambda s_: src_day(s_)
    rbf = {s_: {"settlement": day_of(s_), "release": rel.get(day_of(s_)), "release_column": ("publication" if rel.get(day_of(s_)) else None), "cdn_last_modified": "Thu, 27 Jul 2023 01:26:06 GMT"} for s_ in srcs}
    man = {"built_at_utc": "2026-10-06T03:21:27Z", "rows": len(rows), "files": len(srcs), "first": srcs[0] if srcs else None, "last": srcs[-1] if srcs else None, "out": flat, "out_sha256": sha_flat,
           "quarantined": {q: "CDN copy modified after the cut; not read" for q in quarantine}, "schedule_rows": len(rel), "files_with_release_date": sum(1 for v in rbf.values() if v["release"]), "release_by_file": rbf,
           "market_codes_total": dict(sum((c for c in by.values()), Counter())), "rows_by_file_and_market": {k: dict(v) for k, v in by.items()}, "source_shas": {}}
    man_p, sch_p, prov_p, probe_p = (os.path.join(d, n) for n in ("finra_shortint_manifest.json", "finra_schedule_2018_2025.csv", "finra_shortint_provenance.json", "probe_settlement_dates.json"))
    with open(man_p, "w") as f:
        json.dump(man, f, indent=1)
    with open(sch_p, "w", newline="") as f:
        f.write("settlement,due,release,release_column,page,pages_disagree\n")
        for s_, r_ in sorted(rel.items()):
            if r_:
                f.write(f"{s_},{s_},{r_},publication,wayback_x.html,False\n")
        for s_, r_ in schedule_extra:
            f.write(f"{s_},{s_},{r_},publication,short-interest_page.html,False\n")
    prov = {f"files/{s_}": {"url": f"https://cdn.finra.org/equity/otcmarket/biweekly/{s_}", "fetched_at_utc": "2026-10-06T03:08:37Z", "bytes": 1000 + i, "sha256": hashlib.sha256(s_.encode()).hexdigest(), "last_modified": "Thu, 27 Jul 2023 01:26:06 GMT"} for i, s_ in enumerate(srcs)}
    for q in quarantine:
        prov[f"files/{q}"] = {"url": "https://cdn.finra.org/x/" + q, "fetched_at_utc": "2026-10-06T03:08:37Z", "bytes": 5, "sha256": hashlib.sha256(q.encode()).hexdigest(), "last_modified": "Mon, 30 Jun 2025 10:00:00 GMT"}
    prov["schedule/wayback_x.html"] = {"url": "http://web.archive.org/x", "fetched_at_utc": "2026-10-06T03:08:37Z", "bytes": 10, "sha256": hashlib.sha256(b"sched").hexdigest(), "asked": "20180901"}
    with open(prov_p, "w") as f:
        json.dump(prov, f, indent=1)
    probe = {s_[4:12]: {"status": 200} for s_ in srcs}
    probe.update({src_day(q).replace("-", ""): {"status": 200} for q in quarantine})
    probe.update({"20180608": {"status": 403}})
    probe.update({k: {"status": 200} for k in probe_extra})
    with open(probe_p, "w") as f:
        json.dump(probe, f)
    files = {"flat": flat, "manifest": man_p, "schedule": sch_p, "provenance": prov_p, "probe": probe_p}
    return SimpleNamespace(files=files, shas={k: M17.sha_raw(p) for k, p in files.items()}, dir=d, manifest=man)


def fake_assets(root, titles, name="cache"):
    """the SIPORB asset list of a synthetic cache (root/name/siporb/assets.csv): symbol, name, exchange, status, tradable, shortable, easy_to_borrow; titles = {symbol: asset-list title} -> (the cache folder, the file's sha256)"""
    d = os.path.join(root, name)
    os.makedirs(os.path.join(d, "siporb"), exist_ok=True)
    p = os.path.join(d, "siporb", "assets.csv")
    with open(p, "w", newline="") as f:
        f.write("symbol,name,exchange,status,tradable,shortable,easy_to_borrow\n")
        for s_, t_ in titles.items():
            f.write(f'{s_},"{t_}",NASDAQ,active,True,True,True\n')
    return d, M17.sha_raw(p)


@contextlib.contextmanager
def pulled(pull, cache=None, cache_sha=None):
    """the harness pointed at a synthetic pull (and asset list): FILES / FILE_SHA of the five FINRA files, and r5_siporb's CACHE for the asset list; restored on exit"""
    with contextlib.ExitStack() as es:
        es.enter_context(patched(THIS, FILES={**FILES, **pull.files}, FILE_SHA={**FILE_SHA, **pull.shas, **({} if cache_sha is None else {"assets": cache_sha})}))
        if cache is not None:
            es.enter_context(patched(S, CACHE=cache))
        yield


# ------------------------------------------------------------------ the toy: r21_netiss's toy world (r17_resmom's 20 names, hand-made filings) with hand-made short interest
TOY_PLAN = {"rename": [("O05", "N05", "2024-12-02"), ("P07", "Q07", "2024-06-03"), ("Q07", "N07", "2025-02-03"), ("O09", "N09", "2025-04-01")],
            "cache_only": {"O09": ("2024-01-01", "2025-03-14")},                       # a cache name that held N09's old ticker O09 until 2025-03-14: N09's ticker is shared until it stopped
            "drop": {("N17", "2025-02-14"), ("N17", "2025-02-28"), ("N17", "2025-03-14"), ("N17", "2025-03-31"), ("N01", "2025-08-29"), ("N02", "2025-08-29"), ("N03", "2025-08-29"), ("N06", "2025-08-29")},     # no FINRA row for these: N17 four times, four names at once on 2025-08-29 (coverage under 90%)
            "dup": {("N12", "2025-06-30")},                                            # N12 is listed twice in this file
            "blank": {("N18", "2025-02-14")}, "negative": {("N19", "2025-02-28")}, "zero": {("N14", "2025-03-31"), ("N14", "2025-04-15")},
            "revised": {("N08", "2025-03-31")}, "x5000": {("N11", "2025-04-30")}, "split_flag": {("N00", "2025-03-14"), ("N00", "2025-03-31")},
            "fund_title": {"N15": "N15 Growth Fund Inc"}, "fund_name": {"N16": "N16 Trust ETF"}}


def toy_settlements(days, first="2024-01-15"):
    """the toy's settlement dates: the 15th (the weekday on or before it) and the month's last weekday, from `first` to the World's last session"""
    out = []
    for ym in pd.period_range(days[0], days[-1], freq="M"):
        mid = TS(f"{ym.year}-{ym.month:02d}-15")
        while mid.dayofweek >= 5:
            mid -= pd.Timedelta(days=1)
        last = days[(days.year == ym.year) & (days.month == ym.month)][-1]
        out += [mid, last]
    return [d for d in sorted(set(out)) if TS(first) <= d <= days[-1]]


def toy_symbol(j, s, sym):
    """the symbol FINRA lists for the toy name `sym` on the settlement date s (the renames of TOY_PLAN: a ticker before the change, the cache's after)"""
    s = TS(s)
    for old, new, d in TOY_PLAN["rename"]:
        if sym == new and s < TS(d):
            sym2 = old
            for o2, n2, d2 in TOY_PLAN["rename"]:                                       # a two-step chain: P07 -> Q07 -> N07
                if n2 == old and s < TS(d2):
                    sym2 = o2
            return sym2
    return sym


def si_toy(seed=1, T=620, Sn=20, plant=True, release_lag=10, first="2024-01-15"):
    """the SHORTINT toy: r21_netiss's toy world (r17_resmom's names N00 .. N{Sn-1} on T sessions from 2024-01-01 with the registered windows, the planted hygiene / dividend / spin-off / stopped-print cases, hand-made filings for S1) + FINRA rows twice a month with hand-made short interest (the clear
    short N13 has the highest; a persistent ratio per name) and the planted cases of TOY_PLAN: renames (a one-step and a two-step chain), a ticker shared with a cache-only name, missing / duplicate / blank / negative / zero short interest, a revised row, an x5000 value (S1's scale rule), FINRA's split flag, a fund
    by asset-list title (N15) and one by FINRA issue name (N16), OTC and ETF rows that match nothing. -> SimpleNamespace(W, frame, mrows, cal, cik_of, rows (FINRA rows as text), settle (Timestamps), nc (DataFrame), exist, titles, release {settlement: release 'YYYY-MM-DD'}, level)"""
    tt = NI.ni_toy(seed=seed, T=T, Sn=Sn)
    W = tt.W
    days = W.days
    rng = np.random.default_rng(seed + 100)
    syms = [str(s) for s in W.syms]
    level = np.linspace(0.02, 0.12, Sn)[rng.permutation(Sn)] * 2e8
    if Sn > 13:
        level[13] = 0.30 * 2e8
    settle = [s for s in toy_settlements(days, first) if f"{s:%Y-%m-%d}" != "2025-06-13"]                 # the real pull has no 2025-06-13 either: that file is quarantined [A8]
    P = TOY_PLAN
    rows = []
    for k, s in enumerate(settle):
        sd = f"{s:%Y-%m-%d}"
        for j, sym in enumerate(syms):
            if plant and (sym, sd) in P["drop"]:
                continue
            tk = toy_symbol(j, s, sym) if plant else sym
            si = int(round(level[j] * (1.0 + 0.10 * math.sin(0.9 * k + j))))
            adv, nm = int(2e6 + 1e5 * j), None
            kw = {}
            if plant:
                if (sym, sd) in P["blank"]:
                    si = None
                if (sym, sd) in P["negative"]:
                    si = -5
                if (sym, sd) in P["zero"]:
                    si = 0
                if (sym, sd) in P["x5000"]:
                    si *= 5000
                if (sym, sd) in P["revised"]:
                    kw["rev"] = "R"
                if (sym, sd) in P["split_flag"]:
                    kw["split"] = "S"
                if sym in P["fund_name"]:
                    nm = P["fund_name"][sym]
            rows.append(frow(s, tk, si, name=nm, adv=adv, dtc=round((si or 0) / adv, 2), **kw))
            if plant and (sym, sd) in P["dup"]:
                rows.append(frow(s, tk, si, name=nm, adv=adv, dtc=1.0, mkt="OTC"))
        for z in range(3):
            rows.append(frow(s, f"ZZ{z:02d}", 1000 * (z + 1), mkt="OTC", exch="U"))
        rows.append(frow(s, "QQQX", 5000, name="Fake Index ETF Trust", mkt="ARCA", exch="P"))
    nc = pd.DataFrame({"old": [o for o, n, d in P["rename"]], "new": [n for o, n, d in P["rename"]], "day": [int(day_i(TS(d))) for o, n, d in P["rename"]]}) if plant else pd.DataFrame({"old": [], "new": [], "day": np.zeros(0, np.int64)})
    exist = {}
    fin_ = np.isfinite(np.asarray(W.Od, float))
    for j, sym in enumerate(syms):
        if fin_[:, j].any():
            exist[sym] = (int(day_i(days[int(np.argmax(fin_[:, j]))])), int(day_i(days[int(len(days) - 1 - np.argmax(fin_[::-1, j]))])))
    if plant:
        for sym, (a, b) in P["cache_only"].items():
            exist[sym] = (int(day_i(TS(a))), int(day_i(TS(b))))
    titles = {s: f"{s} Common Stock" for s in syms}
    if plant:
        titles.update(P["fund_title"])
    release = {f"{s:%Y-%m-%d}": f"{s + pd.Timedelta(days=release_lag):%Y-%m-%d}" for k, s in enumerate(settle) if k >= 3}
    if plant:
        release[f"{settle[10]:%Y-%m-%d}"] = f"{settle[10] + pd.Timedelta(days=40):%Y-%m-%d}"          # one release the photographed schedule puts far later than s + 12 sessions: it binds
    return SimpleNamespace(W=W, frame=tt.frame, mrows=tt.mrows, cal=tt.cal, cik_of=tt.cik_of, rows=rows, settle=settle, nc=nc, exist=exist, titles=titles, release=release, level=level, syms=syms)


def toy_ready_si(toy, tmp, rev=None):
    """the toy through the REAL loaders: its FINRA rows written as a synthetic pull and read by load_finra, its asset list written and read by load_assets, its filings and map attached as NETISS's -> (src: the loaded sources, the pull) with W.si attached (the caller holds the shrunk SPEC)"""
    pull = fake_pull(tmp, toy.rows, release=toy.release)
    cache, csha = fake_assets(tmp, toy.titles)
    cut = TS("2030-01-01")
    with pulled(pull, cache, csha):
        fin, finfo = load_finra(cut)
        assets = load_assets()
    W = toy.W
    mp = NI.mp_of(toy.mrows)
    fx = NI.build_facts(toy.frame)
    attach_shortint(W, fin, assets, toy.nc, toy.exist, fx, mp, toy.cal)
    return SimpleNamespace(fin=fin, finfo=finfo, assets=assets, mp=mp, fx=fx), pull


# ------------------------------------------------------------------ plain-python recounts: the known-at row, the ticker walk, the join, D1 / S1, the rank, the pool, the sides, the picks (loops and sorts, none of the vectorised arrays)
def ts_of(dn):
    """a day number -> Timestamp"""
    return TS(np.datetime64(int(dn), "D"))


def truth_of(toy, rev_cache=None):
    """what the recounts read of a toy: the settlements, the FINRA rows by settlement, the renames, the cache spans, the asset titles, the release dates, the filings and the map, the calendar - plain python containers"""
    by = defaultdict(list)
    for r in toy.rows:
        by[r[0]].append(r)
    nc = [(str(o), str(n), ts_of(d)) for o, n, d in zip(toy.nc["old"], toy.nc["new"], toy.nc["day"])]
    usable = [(s, c) for s, c, m in toy.mrows if c != "" and m in NI.ALLOWED_METHODS + NI.ADD_METHODS]
    cnt = Counter(c for s, c in usable)
    return SimpleNamespace(settle=toy.settle, by_settle=by, nc=nc, exist={k: (ts_of(a), ts_of(b)) for k, (a, b) in toy.exist.items()}, titles=toy.titles, release=toy.release, frame=toy.frame, cik_of=toy.cik_of, cal=toy.cal,
                           multi={s for s, c in usable if cnt[c] > 1}, fund_titles={s for s, t in toy.titles.items() if any(tok in t for tok in FUND_TITLE_TOKENS)})


def brute_urow(W, s, release):
    """plain python [K] / [A3]: the first session after the LATER of s + 12 sessions and the photographed release date, as a row (None = never in the data)"""
    dl = NI.dlist(W)
    i = bisect.bisect_right(dl, s) - 1
    if i < 0:
        return None
    u = i + SPEC["lag"] + 1
    if release is not None:
        u = max(u, bisect.bisect_right(dl, TS(release)))
    return u if u < len(dl) else None


def brute_latest_k(W, truth, r):
    """the latest settlement usable at the rank row r (an index into truth.settle), None when there is none"""
    best = None
    for k, s in enumerate(truth.settle):
        u = brute_urow(W, s, truth.release.get(f"{s:%Y-%m-%d}"))
        if u is not None and u <= r:
            best = k
    return best


def brute_walk(nc, name, day, bound=None):
    """plain python (a recursion, not the iterative walk): the ticker the cache name `name` had on `day` - the latest change INTO it before `bound`; on / after its date the name itself; before it the recursion on the old ticker; two different olds on the latest date: None"""
    c = [(d, o) for o, n, d in nc if n == name and (bound is None or d < bound)]
    if not c:
        return name
    dmax = max(d for d, _o in c)
    olds = {o for d, o in c if d == dmax}
    if day >= dmax:
        return name
    return brute_walk(nc, next(iter(olds)), day, dmax) if len(olds) == 1 else None


def brute_alive(truth, name, day):
    e = truth.exist.get(name)
    return e is not None and e[0] <= day <= e[1]


def brute_match(truth, sym, s, rows_s):
    """plain python: (join code, the FINRA row or None) of the cache name `sym` at the settlement s"""
    if not brute_alive(truth, sym, s):
        return M_UNKNOWN, None
    tk = brute_walk(truth.nc, sym, s)
    if tk is None:
        return M_UNKNOWN, None
    if any(n != sym and brute_alive(truth, n, s) and brute_walk(truth.nc, n, s) == tk for n in truth.exist):
        return M_SHARED, None
    hit = [r for r in rows_s if r[1] == tk]
    return (M_NO_ROW, None) if not hit else ((M_OK, hit[0]) if len(hit) == 1 else (M_DUP, None))


def brute_num(x):
    try:
        return float(str(x).replace(",", ""))
    except ValueError:
        return float("nan")


def brute_ent(truth, cik, con):
    """NETISS's plain-python entries of one CIK and concept (a loop over the whole filings frame), kept on the truth object: the recount reads the same frame for every name at every rank, and the frame never changes"""
    c = truth.__dict__.setdefault("_ent", {})
    if (cik, con) not in c:
        c[(cik, con)] = NI.brute_entries(truth.frame, cik, con)
    return c[(cik, con)]


def brute_scores(W, truth, j, k, rev_mode="drop"):
    """plain python: the D1 / S1 outcome of the World column j at settlement k, the first failing rule in the registered order -> SimpleNamespace(c1, d1, c2, s1, adv, n_pres, split_win, mcode, row)"""
    nan = float("nan")
    sym, s = str(W.syms[j]), truth.settle[k]
    out = SimpleNamespace(c1=R_SCORED, c2=R_SCORED, d1=nan, s1=nan, adv=nan, n_pres=0, split_win=False, mcode=M_OK, row=None, si=nan)
    dl = NI.dlist(W)
    isr = bisect.bisect_right(dl, s) - 1
    sh, si = None, nan
    if sym in truth.fund_titles:
        sh = R_FUND_TITLE
        out.mcode = brute_match(truth, sym, s, truth.by_settle[f"{s:%Y-%m-%d}"])[0]
    else:
        code, row = brute_match(truth, sym, s, truth.by_settle[f"{s:%Y-%m-%d}"])
        out.mcode, out.row = code, row
        if code != M_OK:
            sh = {M_UNKNOWN: R_TICKER_UNKNOWN, M_SHARED: R_TICKER_SHARED, M_NO_ROW: R_NO_ROW, M_DUP: R_DUP_ROWS}[code]
        elif any(tok in row[2] for tok in FUND_NAME_TOKENS):
            sh = R_FUND_NAME
        elif rev_mode == "drop" and row[10].strip().upper() == "R":
            sh = R_REVISED
        else:
            si = brute_num(row[5])
            out.si = si
            if not (si >= 0):
                sh = R_SI_MISSING
    lo_r = max(isr - 19, 0)
    vols = [float(W.Vv[t, j]) for t in range(lo_r, isr + 1)]
    fv = [v for v in vols if math.isfinite(v)]
    out.n_pres, out.adv = len(fv), (sum(fv) / len(fv) if len(fv) >= SPEC["adv_min"] else nan)
    fch, crow = NI.brute_fchg(W, j), NI.brute_calrows(W, truth.cal, j)
    out.split_win = any((t in fch) or (t in crow) for t in range(lo_r, isr + 1))
    if sh is not None:
        out.c1 = out.c2 = sh
        return out
    if out.n_pres < SPEC["adv_min"]:
        out.c1 = R_ADV_FEW
    elif out.split_win:
        out.c1 = R_SPLIT_WINDOW
    elif not out.adv > 0:
        out.c1 = R_ADV_ZERO
    else:
        out.d1 = si / out.adv
    st = int(W.ni.static[j])
    if st != 0:
        out.c2 = STATIC_OF[NI.REASONS[st]]
        return out
    if sym in truth.multi:
        out.c2 = R_MULTI_CLASS
        return out
    cik = truth.cik_of.get(sym, "")
    cands = []
    for con in (NI.DEI, NI.GAAP):
        ent = brute_ent(truth, cik, con)
        use = {end: v for end, (f1, v, ok) in ent.items() if ok and bisect.bisect_right(dl, f1) < len(dl) and bisect.bisect_right(dl, f1) <= isr}
        cands.append((max(use), use[max(use)]) if use else None)
    pick = next((c for c in cands if c is not None), None)
    if pick is None:
        out.c2 = R_NO_FACT
        return out
    a, sv = pick
    if not sv > 0:
        out.c2 = R_NOT_POS
        return out
    if (s - a).days > SPEC["stale"]:
        out.c2 = R_STALE
        return out
    ia = bisect.bisect_right(dl, a) - 1
    fa, fs = float(W.F[ia, j]) if ia >= 0 else nan, float(W.F[isr, j])
    if ia < 0 or not (math.isfinite(fa) and math.isfinite(fs) and fa > 0 and fs > 0):
        out.c2 = R_NO_FACTOR
        return out
    cs = NI.cal_start_of(truth.cal)
    covered = cs is not None and a >= cs
    near = lambda t, ts_: any(abs(t - u) <= NI.SPLIT_NEAR for u in ts_)
    un_f = [t for t in fch if ia < t <= isr and not near(t, crow)]
    un_c = [t for t in crow if ia < t <= isr and not near(t, fch)]
    if covered and un_c:
        out.c2 = R_SPLIT_C
    elif covered and un_f:
        out.c2 = R_SPLIT_F
    else:
        out.s1 = si / (sv * fa / fs)
    return out


def brute_rank(W, truth, r, rev_mode="drop", cache=None):
    """plain python: the rank r's universe (the fill session's less the funds), the coverage, the scores of every universe name in both cells with the S1 scale rule applied, the usable settlement -> SimpleNamespace(k, uni, n_title, n_name, cov, covered, c1 {col: code}, d1 {col: value}, c2, s1, adv, mcode)"""
    cache = {} if cache is None else cache
    key = (r, rev_mode)
    if key in cache:
        return cache[key]
    f = r + 1
    k = brute_latest_k(W, truth, r)
    uni0 = [j for j in range(W.S) if W.U[f, j]]
    out = SimpleNamespace(k=k, uni=[], n_title=0, n_name=0, cov=float("nan"), covered=False, c1={}, d1={}, c2={}, s1={}, adv={}, mcode={}, n_uni0=len(uni0))
    title = [j for j in uni0 if str(W.syms[j]) in truth.fund_titles]
    out.n_title = len(title)
    if k is None:
        out.uni = [j for j in uni0 if j not in title]
        for j in uni0:
            code = R_FUND_TITLE if j in title else R_NO_FILE
            out.c1[j] = out.c2[j] = code
            out.d1[j] = out.s1[j] = float("nan")
        cache[key] = out
        return out
    sc = {j: brute_scores(W, truth, j, k, rev_mode) for j in uni0}
    names = [j for j in uni0 if j not in title and sc[j].c1 == R_FUND_NAME]
    out.n_name = len(names)
    out.uni = [j for j in uni0 if j not in title and j not in names]
    for j in uni0:
        out.c1[j], out.c2[j], out.d1[j], out.s1[j], out.adv[j], out.mcode[j] = sc[j].c1, sc[j].c2, sc[j].d1, sc[j].s1, sc[j].adv, sc[j].mcode
    out.after_title = [j for j in uni0 if j not in title]
    n_row = sum(1 for j in out.uni if sc[j].mcode in (M_OK, M_DUP))
    out.cov = n_row / len(out.uni) if out.uni else float("nan")
    out.covered = bool(out.uni and n_row * 10 >= 9 * len(out.uni))
    pos = [j for j in out.uni if out.c2[j] == R_SCORED and out.s1[j] > 0]
    if pos:
        med = float(np.median([out.s1[j] for j in pos]))
        for j in pos:
            if abs(math.log(out.s1[j] / med)) > LN1000:
                out.c2[j], out.s1[j] = R_SCALE, float("nan")
    cache[key] = out
    return out


def brute_side(n):
    """plain python: (names a side, mode) for n scored names"""
    if n >= SPEC["min_scored"]:
        return M17.SPEC["n_side"], "top"
    k = n // 3
    return (k, "third") if k >= SPEC["min_side"] else (0, "none")


def brute_pool(W, r, f, x, post_mode, uni):
    """plain python: the pool of r17_resmom's rm_one on the universe names `uni` (>= 230 own returns and ES pairs, an open at the fill, the pre / old / post hygiene windows, the [D2] spin-offs, the audit) -> {col: (naive, window spins, hold spin)}, the counts"""
    sp = M17.SPEC
    Sp = getattr(W, "Sp_in", None)
    a, lo_pre = M17.windows(r)[0], r - sp["skip"] - sp["hyg_lead"] + 1
    pool, n_hold, n_wnames, n_wsess = {}, 0, 0, 0
    for j in uni:
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
        if pre or old or W.aud1[f, j] or (post and post_mode == "remove"):
            continue
        pool[j] = (bool(post and post_mode == "naive"), win, hold)
    return pool, (n_hold, n_wnames, n_wsess)


def brute_si(W, truth, lo, hi, post_mode="remove", rev_mode="drop"):
    """every rebalance whose position exits in [lo, hi], plain python end to end - the schedule from the months of consecutive sessions, the universe from W.U less the funds, the join and the coverage by brute_rank, the pool re-implemented with loops, each cell's scores by brute_scores, the sides by
    brute_side, the picks by plain sorts (shorts the highest scores, ties by the higher ADV then the lower column; longs the lowest among the rest): [{r, f, x, k, covered, cov, pool, cell: {c: {...}}, counts}]"""
    sp = M17.SPEC
    key = [(W.days[i].year, W.days[i].month) for i in range(W.T)]
    ranks = [i for i in range(W.T - 1) if key[i] != key[i + 1]]
    cache, recs = {}, []
    for q, r in enumerate(ranks):
        f, x = r + 1, (ranks[q + 1] + 1 if q + 1 < len(ranks) else -1)
        if x < 0 or not (lo <= W.days[x] <= hi) or r < sp["win"] - 1:
            continue
        br = brute_rank(W, truth, r, rev_mode, cache)
        pool, spins = brute_pool(W, r, f, x, post_mode, br.uni)
        rec = {"r": r, "f": f, "x": x, "k": br.k, "covered": br.covered, "cov": br.cov, "br": br, "pool": pool, "spins": spins, "cell": {}}
        for c in CELLS:
            sc_, cd_, ad_ = (br.d1, br.c1, br.adv) if c == "D1" else (br.s1, br.c2, br.adv)
            scored = {j: sc_[j] for j in pool if cd_[j] == R_SCORED}
            adv = {j: (ad_[j] if (math.isfinite(ad_.get(j, float("nan"))) and ad_[j] > 0) else -math.inf) for j in scored}
            if br.k is None:
                k_side, mode = 0, "nofile"
            elif not br.covered:
                k_side, mode = 0, "uncovered"
            else:
                k_side, mode = brute_side(len(scored))
            o = {"scored": scored, "codes": {j: cd_[j] for j in pool}, "k": k_side, "mode": mode, "long": [], "short": [], "adv": adv}
            if k_side > 0:
                o["short"] = sorted(scored, key=lambda j: (-scored[j], -adv[j], j))[:k_side]
                rest = [j for j in scored if j not in o["short"]]
                o["long"] = sorted(rest, key=lambda j: (scored[j], -adv[j], j))[:k_side]
            rec["cell"][c] = o
        recs.append(rec)
    return recs


def compare_si(W, L, Bz, tag):
    """the vectorised build against the plain-python recount: the schedule, the rank's settlement and coverage, every pool (names, naive flags, [D2] counts), per cell every scored name with its score and ADV, the first reason of every pool name, the mode and side size, the picks, the counts, and the daily path of EVERY
    scored name under four costings (base, 10 bps, the flat 3% borrow, longs at -100%) -> the number of paths checked"""
    assert len(L.recs) == len(Bz), (tag, len(L.recs), len(Bz))
    cfgs = (("base", D15.l1_cfg(), {}), ("10 bps", D15.l1_cfg(bps=10.0), {"bps": 10.0}), ("flat 3%", D15.l1_cfg(borrow=(BORROW_FLAT, None)), {"borrow": (BORROW_FLAT, None)}), ("lose100", D15.l1_cfg(lose100=True), {"lose100": True}))
    n_paths = 0
    want_cnt = defaultdict(Counter)
    for rec, b in zip(L.recs, Bz):
        assert (rec.r, rec.f, rec.x) == (b["r"], b["f"], b["x"]), tag
        br = b["br"]
        assert (rec.sc.k if rec.sc.k >= 0 else None) == b["k"] and rec.sc.covered is b["covered"], (tag, rec.r, rec.sc.k, b["k"], rec.sc.covered, b["covered"])
        assert (math.isnan(rec.sc.cov) and math.isnan(b["cov"])) or abs(rec.sc.cov - b["cov"]) < 1e-12, (tag, rec.r, rec.sc.cov, b["cov"])
        assert rec.sc.uni.tolist() == sorted(br.uni) and rec.sc.n_title == br.n_title and rec.sc.n_name == br.n_name, (tag, rec.r, "the universe less the funds")
        assert rec.pool.tolist() == sorted(b["pool"]), (tag, rec.r, rec.pool.tolist(), sorted(b["pool"]))
        assert rec.naive.tolist() == [b["pool"][j][0] for j in rec.pool], (tag, rec.r)
        assert rec.spin_win.tolist() == [b["pool"][j][1] for j in rec.pool] and rec.spin_hold.tolist() == [b["pool"][j][2] for j in rec.pool], (tag, rec.r, "the [D2] counts per pool name")
        y = int(W.days[b["f"]].year)
        want_cnt[y]["rebalances"] += 1
        want_cnt[y]["universe"] += len(br.uni)
        want_cnt[y]["funds_title"] += br.n_title
        want_cnt[y]["funds_name"] += br.n_name
        for c in CELLS:
            cc, bc = rec.cell[c], b["cell"][c]
            cols = rec.pool[cc.idx]
            assert cols.tolist() == sorted(bc["scored"]), (tag, rec.r, c, cols.tolist(), sorted(bc["scored"]))
            assert close(cc.score, [bc["scored"][j] for j in cols]), (tag, rec.r, c, "scores")
            assert (cc.k, cc.mode, cc.n) == (bc["k"], bc["mode"], len(bc["scored"])) and cc.traded == (bc["k"] > 0), (tag, rec.r, c, cc.k, cc.mode, cc.n, bc["k"], bc["mode"])
            want_adv = [bc["adv"][j] for j in cols]
            eff = lambda a: float(a) if (np.isfinite(a) and a > 0) else -math.inf
            assert all((eff(a) == w) or (math.isfinite(w) and abs(eff(a) - w) <= 1e-9 * abs(w)) for a, w in zip(cc.adv, want_adv)), (tag, rec.r, c, "the ADVs", cc.adv, want_adv)
            want_cnt[y][f"scored_{c}"] += len(bc["scored"])
            want_cnt[y][f"no_score_{c}"] += len(b["pool"]) - len(bc["scored"])
            want_cnt[y][f"mode_{c}_{bc['mode']}" if len(b["pool"]) else f"mode_{c}_none"] += 1
            for j, code in bc["codes"].items():
                if code != R_SCORED:
                    want_cnt[y][f"ns_{c}_{REASONS[code]}"] += 1
            if not cc.traded:
                continue
            assert cols[cc.long].tolist() == bc["long"] and cols[cc.short].tolist() == bc["short"], (tag, rec.r, c, "the picks", cols[cc.long].tolist(), bc["long"], cols[cc.short].tolist(), bc["short"])
            assert not set(bc["long"]) & set(bc["short"]), "a name is never on both sides"
            kt = W.k[rec.f:rec.x + 1]
            idx = np.arange(cc.n)
            for nm, cfg, kw in cfgs:
                for sd in (1, -1):
                    P = D15.l1_pnl(cc.U, idx, sd, cfg, kt)
                    for i, j in enumerate(cols):
                        want, _ = M17.brute_path(W, rec.f, rec.x, int(j), sd, bool(rec.naive[cc.idx[i]]), bps=kw.get("bps", COST_BPS), borrow=kw.get("borrow", (BORROW, None)), kt=None, lose100=kw.get("lose100", False))
                        assert close(P[i], want), (tag, nm, rec.r, c, int(j), sd)
                        n_paths += 1
    for y, w in want_cnt.items():
        for k_, v in w.items():
            assert L.cnt[y][k_] == v, (tag, y, k_, L.cnt[y][k_], v)
    return n_paths


def series_check_si(W, L, Bz):
    """each cell's daily series (run_cell on r15's L1 engine, $4,000 a name) equals the sum of the recount's position paths booked on rows f .. x"""
    for cell in CELLS:
        x0 = np.zeros(W.T)
        for b in Bz:
            bc = b["cell"][cell]
            if bc["k"] == 0:
                continue
            for sd, js in ((1, bc["long"]), (-1, bc["short"])):
                for j in js:
                    x0[b["f"]:b["x"] + 1] += M17.SPEC["slot"] * np.array(M17.brute_path(W, b["f"], b["x"], j, sd, b["pool"][j][0])[0])
        assert close(M17.run_cell(W, cell_leg(L, cell), D15.l1_cfg()).x, x0), f"{cell} series"


# ------------------------------------------------------------------ selftest: hand-made worlds and hand-made FINRA files - no real file is read, nothing is written outside a temp dir
def tmp():
    return tempfile.mkdtemp(prefix="shortint_selftest_")


def mutate(pull, key, fn):
    """rewrite one file of a synthetic pull with its text passed through fn and return the shas with that file's new one (a test registers the variant by its own sha, so every check below is the one under test and not the sha gate)"""
    p = pull.files[key]
    with open(p, newline="") as f:
        txt = f.read()
    with open(p, "w", newline="") as f:
        f.write(fn(txt))
    return {**pull.shas, key: M17.sha_raw(p)}


def jmut(fn):
    """a text transform that edits a json file's dict in place (fn(dict)) and writes it back"""
    def go(txt):
        d = json.loads(txt)
        fn(d)
        return json.dumps(d, indent=1)
    return go


def t_constants():
    assert (NREP, SEED, CELLS, AUDIT_N, SQUEEZE_N, A2_YEARS) == (500, 20261018, ("D1", "S1"), 50, 20, 2) and YEARS == tuple(range(2018, 2025))
    assert (WF0, PRE_END, LB0, LB1) == (TS("2018-08-01"), TS("2025-06-29"), TS("2025-06-30"), TS("2026-06-30")) and (S.LB0, S.END) == (LB0, R11.LBX) and CACHE_FIRST_SESSION == TS("2016-01-04")
    assert (BOOK_WF, BOOK_LB, DEEPEST_WF) == ((93.81, 3.816), (155.54, 4.15), 44849.0) and DV.REF_W == 0.264 and DV.REF_FACTS == {"roc": 120.82, "sortino": 3.916, "max_dd": 36526.0}
    assert (COST_BPS, STRESS_BPS, BORROW, BORROW_STRESS, BORROW_FLAT) == (5.0, (10.0, 20.0), 0.0025, (0.01, 0.03), 0.03) and BORROW_CURVE == (0.0, 0.0025, 0.01, 0.03, 0.05, 0.10, 0.20)
    assert M17.SPEC == {"win": 252, "form_n": 231, "skip": 21, "min_n": 230, "n_side": 50, "slot": 4000.0, "hyg_lead": 5} and (A2_TARGET, A2_REPORT) == (0.25, (0.5, 2.0)) == (M17.A2_TARGET, M17.A2_REPORT)
    assert SPEC == {"min_scored": 150, "min_side": 20, "lag": 12, "adv_n": 20, "adv_min": 15, "stale": 200, "old": 100, "cover": 0.90, "min_reb": 60, "hedge_win": 252, "hedge_min": 230}
    assert NI.SPEC["hedge_win"] == SPEC["hedge_win"] and NI.SPEC["hedge_min"] == SPEC["hedge_min"], "the ES-hedged twin is NETISS's own and reads NETISS's windows: they are the registered ones here too"
    assert LN1000 == math.log(1000.0) and BETA_CAP == 0.20 and SUBPERIODS[0][1:] == (TS("2018-08-01"), TS("2021-12-31")) and SUBPERIODS[1][1:] == (TS("2022-01-01"), TS("2025-06-29")) and CRASH_JAN21 == (TS("2021-01-01"), TS("2021-01-31"))
    assert FUND_TITLE_TOKENS == ("Physical", "Fund", "Municipal", "Term Trust", "Income Trust", "Capital Securities", "Certificates") and FUND_NAME_TOKENS == ("ETF", "ETN", "Fund", "Index") and QUARANTINED == ("shrt20250613.csv",)
    assert MARKETS == ("NYSE", "NNM", "ARCA", "SC", "BZX", "AMEX", "IEX", "OTC", "OTCBB") and FINRA_KEYS == ("flat", "manifest", "schedule", "provenance", "probe") and (GO_FLAG, READ_FLAG) == ("shortint_stageB_GO.flag", "shortint_stageB_READ.flag")
    assert FILE_SHA == {"flat": "9c72cc2712270aa7516a5bdb2b1c18c7aa04870242956fb0b5d2d58e1871bb4a", "manifest": "a99fe890829751fefece7742e63303d6307cde9e893659fc9e8ae817202337f6", "schedule": "ff4005d01e2807da7ec12cd49804c039706a29f5194f7852372ff7a7beaa1948",
                        "provenance": "5d306bcc1ba45c29c6df48f8c0772ca6446b88d305b93ee2af9462bce8b997f0", "probe": "80f673344b0e3600c01a597e75d348e4d6df56d6b9d22d454f239946e788282c", "assets": "b85928ff655a883dd3eb44d8d96b3b745ffe2f5f0e0ca0991485895f5e960991"}
    assert FLAT_COLS == ("settlement_date", "symbol", "issue_name", "exchange_code", "market_code", "short_interest", "prev_short_interest", "split_flag", "avg_daily_volume", "days_to_cover", "revision_flag", "source_file")
    assert RULES is M17.RULES and CHECK_BOOK is True and LB_FINRA is None and set(MODES) == {"top", "third", "none", "uncovered", "nofile"} and REV_MODES == ("drop", "asis")
    assert REASONS == ("scored", "fund_asset_title", "ticker_history_unknown", "ticker_shared", "no_finra_row", "duplicate_finra_rows", "fund_finra_name", "revised_row", "si_missing_or_negative", "adv_under_15_sessions", "split_in_volume_window", "adv_not_positive",
                       "multi_class_cik", "not_in_map", "map_mismatch", "map_ambiguous", "map_unmapped", "map_non_common", "map_other", "no_facts_for_cik", "foreign_filer", "no_share_fact_at_s", "value_not_positive", "share_count_over_200_days",
                       "no_split_factor", "split_calendar_not_in_F", "split_F_not_in_calendar", "scale_error", "no_usable_file")
    assert [R_SCORED, R_FUND_TITLE, R_TICKER_UNKNOWN, R_TICKER_SHARED, R_NO_ROW, R_DUP_ROWS, R_FUND_NAME, R_REVISED, R_SI_MISSING, R_ADV_FEW, R_SPLIT_WINDOW, R_ADV_ZERO, R_MULTI_CLASS, R_NOT_IN_MAP, R_NO_FILE] == [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 28]
    assert len(REASONS) == len(REASON_TEXT) == 29 and set(REASONS) == set(REASON_TEXT) and REASONS[0] == "scored" and REASONS[-1] == "no_usable_file" and all(nm in NI.REASONS for nm in STATIC_OF), "every static reason is one of NETISS's names"
    assert SHARED_REASONS == tuple(range(1, 9)) and D1_REASONS == (9, 10, 11) and S1_REASONS == tuple(range(12, 28)) and CELL_REASONS["D1"] == SHARED_REASONS + D1_REASONS + (28,) and CELL_REASONS["S1"] == SHARED_REASONS + S1_REASONS + (28,)
    assert set(CELL_REASONS["D1"]) | set(CELL_REASONS["S1"]) | {0} == set(range(29)), "every reason is some cell's"
    assert OUT_DEFAULT == "C:" + chr(92) + "EdgeLog" + chr(92) + "_anatomy_cache" + chr(92) + "rocfrontier" + chr(92) + "shortint_r1", "the default results folder (outside git); a test run never touches it: selftest() points OUT at a temp dir"
    txt = open(PREREG, encoding="utf-8").read()                                                             # the registered text carries every number this file hard-codes
    for frag in ("500 draws, seed 20261018", "ln(1000)", "more than 200", "fewer than 15 sessions", "fewer than 150 scored names", "at least 20 a side", "covers less than 90% of its universe trades nothing", "fewer than 60 rebalances", "NOT JUDGEABLE", "the LATER of s + 12",
                 "20 sessions ending at s*", "otherwise s + 12 sessions", "2018-08-01", "2020-07-31", "25% of #463's daily std", "0.25%/yr on short notional base", "stress 1% and 3%/yr", "flat stress of 3%/yr on every short every day", "net at 0, 0.25, 1, 3, 5, 10 and 20%/yr flat on every short",
                 ">= 5 of the 7 July-June WF years (two thirds, rounded up)", "2020-02-15", "2020-04-30", "|realised beta| > 0.20", "2018-08 .. 2021-12 and 2022-01 .. 2025-06", "bed7bf8b", "120.82 / 3.916 / $36,526", "93.81 / 3.816 / $44,849", "380b05f2", "e5bc8487", "02387a4f + d10626d8",
                 "'Physical', 'Fund', 'Municipal', 'Term Trust', 'Income Trust', 'Capital Securities' or 'Certificates'", "'ETF', 'ETN', 'Fund' or 'Index'", "shrt20250613.csv", "22,644 rows (0.7%)", "3,136,392 rows from 168",
                 FILE_SHA["flat"], FILE_SHA["manifest"], FILE_SHA["schedule"], FILE_SHA["provenance"], FILE_SHA["probe"], FILE_SHA["assets"][:8]):
        assert frag in txt, frag
    with quiet():
        assert prereg_ok()["verified"] is True
    st = stamp()
    assert len(st["harness_sha256"]) == 64 and st["finra_flat_sha256"] == FILE_SHA["flat"] and st["assets_sha256"] == FILE_SHA["assets"] and all(st[f"finra_{k}_sha256"] == FILE_SHA[k] for k in FINRA_KEYS)
    assert set(st) >= {"r17_sha256", "r18_sha256", "r15_sha256", "r11_sha256", "r12_sha256", "r13_sha256", "wide_ca_sha256", "early_close", "facts_sha256", "map_sha256", "r21_sha256"}
    assert st["r21_sha256"] == R11.sha_lf(NI.__file__) and st["harness_sha256"] == R11.sha_lf(os.path.abspath(__file__)) and st["r17_sha256"] == R11.sha_lf(M17.__file__) and st["r18_sha256"] == R11.sha_lf(DV.__file__)
    assert src_day("shrt20250530.csv") == "2025-05-30" and src_day(" shrt20180615.csv ") == "2018-06-15" and src_day("shrt2025053.csv") is None and src_day("foo.csv") is None and src_day("shrt20250530.csv.bak") is None
    assert refused(lambda: refuse("x"), "x") == "x"
    assert all(os.path.dirname(FILES[k]) == FINRA_DIR for k in FILES), "the five pinned FINRA files sit in the one pinned folder"


def t_known_at():
    """[K] / [A3] / [A9] the known-at row of a settlement on hand-made sessions (Monday-Friday, 65 of them from 2024-01-01), judged by hand: usable from the first session AFTER the LATER of s + 12 sessions and the photographed release date; a release before s + 12 sessions never
    moves it earlier, a later one binds, an equal one is 'equal', a weekend release moves to the next session, a settlement before the first session or whose usable row is past the data is never usable; the latest usable settlement at a rank"""
    days = pd.bdate_range("2024-01-01", "2024-03-29")
    di = day_i(days)
    row = lambda s: int(days.get_loc(TS(s)))
    assert len(days) == 65 and row("2024-01-12") == 9 and row("2024-01-31") == 22
    sd = ["2023-12-29", "2024-01-12", "2024-01-26", "2024-02-09", "2024-02-10", "2024-02-23", "2024-03-15", "2024-03-29"]
    rel = {"2024-01-12": "2024-01-22", "2024-01-26": "2024-02-22", "2024-02-09": "2024-02-27", "2024-02-23": "2024-03-02", "2024-03-15": "2024-04-10"}
    fin = SimpleNamespace(ks=day_i(pd.DatetimeIndex(sd)), release=np.array([int(day_i(TS(rel[s]))) if s in rel else -1 for s in sd], np.int64))
    tab = settle_table(di, fin)
    never = 10 ** 9
    assert tab.row_s.tolist() == [-1, 9, 19, 29, 29, 39, 54, 64], "the last session on or before s (a Saturday's is the Friday's)"
    assert tab.u12.tolist() == [never, 22, 32, 42, 42, 52, 67, 77]
    assert tab.u.tolist() == [never, 22, 39, 42, 42, 52, never, never] and tab.binding.tolist() == ["s+12", "s+12", "photographed", "equal", "s+12", "s+12", "s+12", "s+12"], (tab.u.tolist(), tab.binding.tolist())
    assert tab.uph.tolist() == [0, 16, 39, 42, 0, 45, 65, 0], "the first session strictly after the photographed date (a Saturday's: the Monday); 65 = past the data"
    assert [days[u].strftime("%Y-%m-%d") for u in tab.u if u < never] == ["2024-01-31", "2024-02-23", "2024-02-28", "2024-02-28", "2024-03-13"], "s + 12 sessions then the next session; the photographed date (2024-02-22) binds the second"
    for k, s in enumerate(sd):                                                                                # the plain-python rule agrees on every settlement
        u = brute_urow(SimpleNamespace(days=days), TS(s), rel.get(s))
        assert tab.u[k] == (never if u is None else u), (s, tab.u[k], u)
    for r_, want in ((21, -1), (22, 1), (38, 1), (39, 2), (41, 2), (42, 4), (51, 4), (52, 5), (64, 5)):
        assert latest_usable(tab, r_) == want, (r_, latest_usable(tab, r_), want)
    assert latest_usable(settle_table(di, SimpleNamespace(ks=di[:0], release=np.zeros(0, np.int64))), 30) == -1
    t5 = settle_table(di, fin, lag=5)
    assert t5.u12.tolist() == [never, 15, 25, 35, 35, 45, 60, 70] and t5.u.tolist() == [never, 16, 39, 42, 35, 45, never, never], (t5.u.tolist(), "lag is a parameter; the photographed dates still bind")
    with spec(lag=3):
        assert settle_table(di, fin).u12.tolist()[1] == 13, "SPEC['lag'] is read at call time"
    # the printed table (known_at_rows) on a stub World
    W = SimpleNamespace(si=SimpleNamespace(fin=fin, tab=tab), T=len(days), days=days)
    rows = known_at_rows(W)
    assert rows[2] == {"settlement": "2024-01-26", "release": "2024-02-22", "s_plus_12_sessions": "2024-02-13", "usable_from": "2024-02-23", "binding": "photographed"}, rows[2]
    assert rows[0] == {"settlement": "2023-12-29", "release": "-", "s_plus_12_sessions": "-", "usable_from": "-", "binding": "s+12"} and rows[6]["usable_from"] == "-" and rows[6]["s_plus_12_sessions"] == "-" and rows[1]["usable_from"] == "2024-01-31"
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        print_known_at(rows)
    txt = buf.getvalue()
    assert "KNOWN AT" in txt and "(8 settlements)" in txt and "2024-01-26: 2024-02-22 | 2024-02-13 | 2024-02-23 | photographed" in txt and "'photographed': 1" in txt and "binding: {'s+12': 6, 'photographed': 1, 'equal': 1}" in txt, txt


def t_tickers():
    """[SYMBOLS] the ticker of a cache name on a settlement date: the calendar's name changes walked BACKWARD from the cache's ticker (a one-step change, a two-step chain, two changes into one ticker on the SAME date = unknown before it, a chain longer than the limit = unknown), the span a name
    holds a ticker in (inside its own span in the cache only), before the calendar's start = unknown, the ticker two cache names held on overlapping dates = shared on those days only; every (name, day) against the plain-python recursion"""
    nc = pd.DataFrame({"old": ["OLD1", "A", "B", "X1", "X2", "S5"], "new": ["NEW1", "B", "C", "Z", "Z", "T5"], "day": [100, 50, 80, 70, 70, 40]})
    by_new = defaultdict(list)
    for o, n, d in zip(nc["old"], nc["new"], nc["day"]):
        by_new[n].append((int(d), o))
    assert ticker_chain("NEW1", by_new) == ([(100, "NEW1"), (None, "OLD1")], True) and ticker_chain("QQ", by_new) == ([(None, "QQ")], True)
    assert ticker_chain("C", by_new) == ([(80, "C"), (50, "B"), (None, "A")], True), "a two-step chain: C was B from day 50 and A before it"
    assert ticker_chain("Z", by_new) == ([(70, "Z")], False), "two different old tickers on the same latest date: the history before it is unknown"
    long_ = defaultdict(list)
    for i in range(1, 46):
        long_[f"N{i}"].append((i, f"N{i - 1}"))
    segs, known = ticker_chain("N45", long_)
    assert len(segs) == 40 and known is False and segs[0] == (45, "N45") and segs[-1] == (6, "N6"), "a chain longer than the limit ends unresolved"
    sw = defaultdict(list)                                                                                    # a swap on one day: P -> Q and Q -> P at day 10
    for o, n, d in (("P", "Q", 10), ("Q", "P", 10)):
        sw[n].append((d, o))
    assert ticker_chain("P", sw) == ([(10, "P"), (None, "Q")], True) and ticker_chain("Q", sw) == ([(10, "Q"), (None, "P")], True), "two names that swapped tickers on one day"
    names = ["NEW1", "C", "Z", "QQ", "T5", "OTHER"]
    exist = {n: (0, 200) for n in names}
    exist["OLD1"] = (0, 120)                                                                                  # a cache name that held NEW1's old ticker until day 120
    th = build_tickers(names, nc, exist, cal_start=None)
    assert set(th.segs) == set(names) | {"OLD1"} and th.known["Z"] is False and th.known["C"] is True and th.cal_start_i is None
    assert th.holders == {"OLD1": [("NEW1", 0, 99), ("OLD1", 0, 120)]}, th.holders
    assert ticker_at(th, "NEW1", 50) == ("OLD1", "ok") and ticker_at(th, "NEW1", 99) == ("OLD1", "ok") and ticker_at(th, "NEW1", 100) == ("NEW1", "ok") and ticker_at(th, "C", 49) == ("A", "ok") and ticker_at(th, "C", 50) == ("B", "ok") and ticker_at(th, "C", 80) == ("C", "ok")
    assert ticker_at(th, "NEW1", 201) == (None, "not_alive") and ticker_at(th, "NEW1", -1) == (None, "not_alive") and ticker_at(th, "GONE", 5) == (None, "not_alive") and ticker_at(th, "OLD1", 121) == (None, "not_alive"), "a name holds nothing outside its own span in the cache"
    assert ticker_at(th, "Z", 10) == (None, "unknown") and ticker_at(th, "Z", 70) == ("Z", "ok"), "an unresolved history is unknown before the date it could not resolve"
    assert shared_at(th, "OLD1", "OLD1", 50) is True and shared_at(th, "NEW1", "OLD1", 50) is True and shared_at(th, "OLD1", "OLD1", 99) is True and shared_at(th, "OLD1", "OLD1", 100) is False and shared_at(th, "OLD1", "OLD1", 110) is False and shared_at(th, "NEW1", "NEW1", 150) is False, "shared only on the days both held it"
    assert shared_at(th, "C", "ZZZ", 5) is False
    thc = build_tickers(names, nc, exist, cal_start=TS("1970-01-06"))
    assert thc.cal_start_i == int(day_i(TS("1970-01-06"))) == 5 and ticker_at(thc, "QQ", 3) == (None, "unknown") and ticker_at(thc, "QQ", 5) == ("QQ", "ok") and ticker_at(thc, "OLD1", 5)[1] == "ok", "before the calendar's start the renames are not visible: unknown"
    ncl = [(str(o), str(n), int(d)) for o, n, d in zip(nc["old"], nc["new"], nc["day"])]                       # every (name, day) against the plain-python recursion
    n_chk = 0
    for nm in names + ["OLD1"]:
        for d in range(0, 201, 3):
            tk, st = ticker_at(th, nm, d)
            if not (exist[nm][0] <= d <= exist[nm][1]):
                assert st == "not_alive"
                continue
            want = brute_walk(ncl, nm, d)
            assert (st == "unknown" and want is None) or (st == "ok" and tk == want), (nm, d, tk, st, want)
            n_chk += 1
    assert n_chk > 300
    # the spans of the cache's names: first and last session with an OPEN print
    Dd = SimpleNamespace(Od=np.array([[np.nan, 1.0, np.nan], [2.0, 3.0, np.nan], [np.nan, 4.0, np.nan], [np.nan, np.nan, np.nan]]), days=pd.DatetimeIndex(["2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05"]), syms=np.array(["A", "B", "C"]))
    ex = exist_spans(Dd)
    assert ex == {"A": (int(day_i(TS("2024-01-03"))), int(day_i(TS("2024-01-03")))), "B": (int(day_i(TS("2024-01-02"))), int(day_i(TS("2024-01-04"))))}, ex


def sample_pull(root, name="finra", **kw):
    """the hand-made pull of t_files: three settlements (2024-01-12, 01-31, 02-15) of 11 / 7 / 2 rows with one planted case each - thousands commas, a blank / negative / unreadable short interest, a revised row, a split flag in either case, a fund name by each of the four tokens and look-alikes
    of them, every market code and an unknown one, a row without a symbol - written in a shuffled order; releases for the first two settlements -> (the pull, its rows)"""
    s1, s2, s3 = "2024-01-12", "2024-01-31", "2024-02-15"
    rows = [frow(s1, "AAA", 1000, mkt="NYSE", dtc=2.5, adv=400), frow(s1, "BBB", "2,000", mkt="NNM"), frow(s1, "CCC", 300, mkt="ARCA", name="CCC S&P Index ETF"), frow(s1, "DDD", None, mkt="SC"), frow(s1, "EEE", -5, mkt="BZX"), frow(s1, "FFF", 70, mkt="AMEX", rev="R"),
            frow(s1, "GGG", 80, mkt="IEX", split="S"), frow(s1, "HHH", 90, mkt="OTC"), frow(s1, "III", 10, mkt="OTCBB"), frow(s1, "JJJ", 11, mkt="WEIRD"), frow(s1, "KKK", "abc", mkt="NYSE"), frow(s1, " ", 5, mkt="NYSE"),
            frow(s2, "AAA", 1100, mkt="NYSE"), frow(s2, "BBB", 2100, mkt="NNM", rev="r"), frow(s2, "GGG", 85, mkt="IEX", split="s"), frow(s2, "LLL", 5, name="LLL Dividend Fund Inc"), frow(s2, "MMM", 6, name="MMM Etf Corp"), frow(s2, "NNN", 7, name="NNN INDEX Corp"),
            frow(s2, "OOO", 8, name="OOO Index Holdings"), frow(s3, "AAA", 1200, mkt="NYSE"), frow(s3, "BBB", 2200, mkt="NNM")]
    order = np.random.default_rng(3).permutation(len(rows))
    shuffled = [rows[i] for i in order]
    opts = dict(release={s1: "2024-01-22", s2: "2024-02-12"}, schedule_extra=[("2025-06-27", "2025-07-08"), ("2025-12-15", "2026-01-05"), ("2024-03-15", "2024-03-25")], probe_extra=["20240229"])
    opts.update(kw)
    return fake_pull(root, shuffled, name=name, **opts), rows


def t_files():
    """[A7] / [A8] / [A9] / [A1] the pinned FINRA files on hand-made copies: the flat file read as ONE table (every column, the cut at read, the quarantined file, the symbol and market code, the flags in either case, the fund tokens as literal case-sensitive substrings, a row without a
    symbol dropped and counted), the manifest / schedule / provenance / probe cross-checked against it, each file refused when its sha256 differs or it is not on file, every refusal the loader has (nothing computed, lockbox NOT read), the asset list's fund titles, the wide calendar's name changes"""
    cut = S.LB0
    root = tmp()
    try:
        pull, rows = sample_pull(root)
        with pulled(pull):
            fin, fi = load_finra(cut)
        s_ = {k: int(day_i(TS(k))) for k in ("2024-01-12", "2024-01-31", "2024-02-15")}
        assert fi["rows_read"] == 21 and fi["rows"] == 20 and fi["rows_without_a_symbol"] == 1 and fi["files"] == 3 and fi["settlements"] == 3 and fi["first"] == "2024-01-12" and fi["last"] == "2024-02-15", fi
        assert fin.ks.tolist() == list(s_.values()) and fin.off.tolist() == [0, 11, 18, 20] and fin.n == 20, "rows ordered by settlement date (the file was shuffled): 11 / 7 / 2 rows with a symbol"
        assert fin.srcs and sorted(fin.srcs) == ["shrt20240112.csv", "shrt20240131.csv", "shrt20240215.csv"] and fin.release.tolist() == [int(day_i(TS("2024-01-22"))), int(day_i(TS("2024-02-12"))), -1], "the photographed release dates; none for the third"
        sym_at = lambda k: [str(x) for x in fin.symtab[fin.symc[fin.off[k]:fin.off[k + 1]]]]
        assert sorted(sym_at(0)) == ["AAA", "BBB", "CCC", "DDD", "EEE", "FFF", "GGG", "HHH", "III", "JJJ", "KKK"] and sorted(sym_at(1)) == ["AAA", "BBB", "GGG", "LLL", "MMM", "NNN", "OOO"] and sorted(sym_at(2)) == ["AAA", "BBB"]
        si_of = lambda k, sym: float(fin.si[fin.off[k] + sym_at(k).index(sym)])
        assert si_of(0, "AAA") == 1000.0 and si_of(0, "BBB") == 2000.0 and math.isnan(si_of(0, "DDD")) and si_of(0, "EEE") == -5.0 and math.isnan(si_of(0, "KKK")), "a thousands comma is read; blank and unreadable are NaN; a negative stays (the score refuses it)"
        assert fi["short_interest_blank"] == 1 and fi["short_interest_unreadable"] == 1 and fi["short_interest_negative"] == 1, fi
        assert int(fin.rev.sum()) == 2 and int(fin.spl.sum()) == 2 and fi["revision_flag_values"].get("R") == 2 and fi["split_flag_values"].get("S") == 2, "the flags are read in either case"
        assert fi["market_codes_other"] == {"WEIRD": 1} and fi["rows_by_file_and_market"]["shrt20240112.csv"] == {"NYSE": 2, "NNM": 1, "ARCA": 1, "SC": 1, "BZX": 1, "AMEX": 1, "IEX": 1, "OTC": 1, "OTCBB": 1, "other": 1}, fi["rows_by_file_and_market"]
        assert fi["fund_named_rows"] == 3 and fi["fund_named_symbols"] == 3 and sorted(fin.fund_pairs) == ["CCC", "LLL", "OOO"], "ETF / Index / Fund / Index are tokens; 'Etf' and 'INDEX' are not (literal, case-sensitive)"
        assert [bool(fin.fnd[fin.off[1] + sym_at(1).index(x)]) for x in ("LLL", "MMM", "NNN", "OOO")] == [True, False, False, True]
        assert fi["schedule"]["rows_on_file"] == 5 and fi["schedule"]["rows_dropped_at_the_cut"] == 2 and fi["schedule"]["rows_read"] == 3 and fi["schedule"]["rows_with_a_release_date"] == 3 and fi["schedule"]["pages_disagree_settlements"] == [], fi["schedule"]
        assert fi["missing_settlement_dates"] == ["2024-02-29"] and fi["settlements_with_a_release_date"] == 2 and fi["probe_status_200_before_the_cut"] == 5 and fi["provenance_file_entries_for_the_files_read"] == 3 and fi["provenance_entries"] == 5, fi
        assert fi["quarantined_on_record_in_provenance"] == {"shrt20250613.csv": True} and fi["provenance_rebuilt_from_disk"] == 0 and fi["sha256"] == pull.shas and fi["manifest_rows"] == 21
        assert (fin.ks < int(day_i(cut))).all() and fin.release.max() < int(day_i(cut)) and all(r_[11] != "shrt20250613.csv" for r_ in rows)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            print_market_codes(fin, fi)
        assert "[A2] FINRA'S MARKET CODES" in buf.getvalue() and "2024-01-12: 2 1 1 1 1 1 1 1 1 1" in buf.getvalue() and "total rows by market code: NYSE 4, NNM 7, ARCA 1" in buf.getvalue(), buf.getvalue()
        pull_crlf, _r = sample_pull(root, name="crlf")                                                        # a CRLF copy of the flat file is another file (the pin is of the bytes); the loader reads either
        sha_crlf = write_flat(pull_crlf.files["flat"], rows, crlf=True)
        assert sha_crlf != pull_crlf.shas["flat"]
        shas_crlf = {**mutate(pull_crlf, "manifest", jmut(lambda d: d.update(out_sha256=sha_crlf))), "flat": sha_crlf}
        with pulled(SimpleNamespace(files=pull_crlf.files, shas=shas_crlf)):
            f2, i2 = load_finra(cut)
        assert f2.n == 20 and i2["short_interest_blank"] == 1 and f2.ks.tolist() == fin.ks.tolist(), "a CRLF file is read the same"
        # ---- every refusal: the sha of each pinned file, absent files, then the contents
        tail = "(nothing computed, lockbox NOT read)"
        for key in FINRA_KEYS:
            with pulled(pull), patched(THIS, FILE_SHA={**FILE_SHA, **pull.shas, key: "0" * 64}):
                refused(lambda: load_finra(cut), "is not the registered", FILE_LABEL[key], tail)
            with pulled(pull), patched(THIS, FILES={**FILES, **pull.files, key: pull.files[key] + ".absent"}):
                refused(lambda: load_finra(cut), "is not on file", FILE_LABEL[key], tail)
        n = [0]                                                                                               # (each variant below is a fresh pull: the files above stay the originals)

        def variant(**kw):
            n[0] += 1
            return sample_pull(root, name=f"v{n[0]}", **kw)[0]

        def refuses(pl, shas, *frag):
            with pulled(SimpleNamespace(files=pl.files, shas=shas)):
                return refused(lambda: load_finra(cut), *frag, tail)
        p_ = variant()
        refuses(p_, mutate(p_, "flat", lambda t: t + "2025-06-30,ZZZ,ZZZ Inc,Q,NNM,5,5,,1,1,,shrt20250630.csv\n"), "settled on / after the cut", "sealed year")
        p_ = variant()
        refuses(p_, mutate(p_, "flat", lambda t: t + "2025-06-13,ZZZ,ZZZ Inc,Q,NNM,5,5,,1,1,,shrt20250613.csv\n"), "quarantined", "shrt20250613.csv", "[A8]")
        p_ = variant()
        refuses(p_, mutate(p_, "flat", lambda t: t + "not-a-date,ZZZ,ZZZ Inc,Q,NNM,5,5,,1,1,,shrt20240112.csv\n"), "unreadable settlement date")
        p_ = variant()
        refuses(p_, mutate(p_, "flat", lambda t: t.replace("market_code", "market", 1)), "lacks the column", "market_code")
        p_ = variant()
        refuses(p_, mutate(p_, "flat", lambda t: t + "2024-01-12,ZZZ,ZZZ Inc,Q,NNM,5,5,,1,1,,foo.csv\n"), "not a FINRA short-interest file name")
        p_ = variant()
        refuses(p_, mutate(p_, "flat", lambda t: t + "2024-01-31,ZZZ,ZZZ Inc,Q,NNM,5,5,,1,1,,shrt20240112.csv\n"), "not the date in its source file's name")
        for what, edit, frag in (("sha of the flat file", lambda d: d.update(out_sha256="0" * 64), "its sha256 of the flat file"), ("rows", lambda d: d.update(rows=d["rows"] + 1), "its row count"), ("files", lambda d: d.update(files=d["files"] + 1), "its file count"),
                                 ("first", lambda d: d.update(first="shrt20240101.csv"), "its first / last file"), ("last", lambda d: d.update(last="shrt20240229.csv"), "its first / last file"), ("quarantine list", lambda d: d.update(quarantined={}), "its quarantine list"),
                                 ("quarantine extra", lambda d: d["quarantined"].update({"shrt20250530.csv": "x"}), "its quarantine list"), ("rows by market", lambda d: d["rows_by_file_and_market"]["shrt20240112.csv"].update(NYSE=99), "its rows by file and market code"),
                                 ("a release date", lambda d: d["release_by_file"]["shrt20240112.csv"].update(release="2024-01-23"), "the release date of shrt20240112.csv"), ("a missing entry", lambda d: d["release_by_file"].pop("shrt20240131.csv"), "the release date of shrt20240131.csv"),
                                 ("an invented release", lambda d: d["release_by_file"]["shrt20240215.csv"].update(release="2024-02-26"), "the release date of shrt20240215.csv")):
            p_ = variant()
            refuses(p_, mutate(p_, "manifest", jmut(edit)), "manifest disagrees with the files it describes", frag)
        p_ = variant()
        refuses(p_, mutate(p_, "manifest", lambda t: "this is not json"), "cannot be read as json", "manifest")
        p_ = variant()
        refuses(p_, mutate(p_, "manifest", lambda t: "[1, 2]"), "not json objects")
        p_ = variant()
        refuses(p_, mutate(p_, "provenance", jmut(lambda d: d.pop("files/shrt20240131.csv"))), "provenance has a url / size / sha256 entry for 2 of the 3 files")
        p_ = variant()
        refuses(p_, mutate(p_, "provenance", jmut(lambda d: d["files/shrt20240215.csv"].update(sha256="xyz"))), "provenance has a url / size / sha256 entry for 2 of the 3 files")
        p_ = variant()
        refuses(p_, mutate(p_, "schedule", lambda t: t + "2024-01-12,2024-01-12,2024-01-22,publication,x.html,False\n"), "lists a settlement date more than once")
        p_ = variant()
        refuses(p_, mutate(p_, "schedule", lambda t: t.replace("release,", "relx,", 1)), "lacks the column", "release")
        # ---- the variants that load: rebuilt provenance entries counted, a pages-disagree row listed, an unreadable schedule settlement dropped, a probe date the flat file lacks reported (not a refusal)
        p_ = variant()
        sh_p = mutate(p_, "provenance", jmut(lambda d: [d["files/shrt20240112.csv"].update(note="rebuilt from the saved file"), d["files/shrt20240131.csv"].update(note="Rebuilt from disk")]))
        sh_s = mutate(p_, "schedule", lambda t: t.replace("False\n", "True\n", 1) + "garbage,x,2024-01-01,publication,x.html,False\n")
        with pulled(SimpleNamespace(files=p_.files, shas={**p_.shas, "provenance": sh_p["provenance"], "schedule": sh_s["schedule"]})):
            f3, i3 = load_finra(cut)
        assert i3["provenance_rebuilt_from_disk"] == 2 and i3["schedule"]["rows_unreadable_settlement"] == 1 and len(i3["schedule"]["pages_disagree_settlements"]) == 1, i3["schedule"]
        # ---- the pull with nothing wrong in the flat file but an extra status-200 probe date is not refused; a pull with no row at all reads as empty-handed (and says so)
        p0 = fake_pull(root, [], name="empty")
        with pulled(p0):
            e1, ei = load_finra(cut)
        assert e1.n == 0 and ei["rows"] == 0 and ei["files"] == 0 and ei["first"] is None and e1.release.tolist() == []
        # ---- [A1] the asset list: fund tokens are literal, case-sensitive substrings of the TITLE (Index is a FINRA-name token only); a symbol listed twice keeps its first title and is a fund when any row's title carries a token
        titles = {"AAA": "AAA Common Stock", "FUN1": "Growth Fund Inc", "FUN2": "growth fund inc", "MUN1": "Municipal Bond Holdings", "PHY1": "Sprott Physical Gold Trust", "TT1": "XX Term Trust", "IT1": "YY Income Trust", "CS1": "ZZ Capital Securities", "CE1": "Cert Certificates Corp",
                  "IDX": "Nasdaq Index Corp", "FND": "Fundamental Holdings", "TRU": "Plain Trust", "ETFX": "ETF Holdings"}
        cache, csha = fake_assets(root, titles)
        with pulled(pull, cache, csha):
            a = load_assets()
        want_fund = {"FUN1", "MUN1", "PHY1", "TT1", "IT1", "CS1", "CE1", "FND"}
        assert set(a.tok) == want_fund and a.tok["PHY1"] == ["Physical"] and a.tok["FND"] == ["Fund"] and a.title["FUN2"] == "growth fund inc" and a.info["rows"] == 13 and a.info["symbols"] == 13 and a.info["duplicate_symbol_rows"] == 0, (sorted(a.tok), a.info)
        assert a.info["fund_title_symbols"] == 8 and a.info["by_token"] == {"Physical": 1, "Fund": 2, "Municipal": 1, "Term Trust": 1, "Income Trust": 1, "Capital Securities": 1, "Certificates": 1} and a.info["by_status"] == {"active": 13} and a.info["sha256"] == csha, a.info
        d2 = os.path.join(root, "cache2", "siporb")
        os.makedirs(d2)
        with open(os.path.join(d2, "assets.csv"), "w", newline="") as f:
            f.write('symbol,name,exchange,status,tradable,shortable,easy_to_borrow\nDUP,"DUP Common Stock",NYSE,active,True,True,True\nDUP,"DUP Municipal Trust",NYSE,inactive,False,True,True\nAAA,"AAA Common Stock",NYSE,active,True,True,True\n')
        c2 = M17.sha_raw(os.path.join(d2, "assets.csv"))
        with patched(THIS, FILE_SHA={**FILE_SHA, "assets": c2}), patched(S, CACHE=os.path.join(root, "cache2")):
            a2 = load_assets()
        assert a2.title["DUP"] == "DUP Common Stock" and set(a2.tok) == {"DUP"} and a2.info["duplicate_symbol_rows"] == 2 and a2.info["symbols"] == 2 and a2.info["rows"] == 3 and a2.info["fund_title_symbols"] == 1 and a2.info["fund_title_symbols_by_first_row_only"] == 0, a2.info
        with pulled(pull, cache, csha), patched(THIS, FILE_SHA={**FILE_SHA, "assets": "0" * 64}):
            refused(load_assets, "is not the registered", "SIPORB asset list", tail)
        with patched(THIS, FILE_SHA={**FILE_SHA, "assets": csha}), patched(S, CACHE=os.path.join(root, "nowhere")):
            refused(load_assets, "is not on file", "SIPORB asset list")
        with open(os.path.join(d2, "assets.csv"), "w", newline="") as f:
            f.write("sym,name,status\nA,B,C\n")
        with patched(THIS, FILE_SHA={**FILE_SHA, "assets": M17.sha_raw(os.path.join(d2, "assets.csv"))}), patched(S, CACHE=os.path.join(root, "cache2")):
            refused(load_assets, "lacks the column", "symbol")
        # ---- [SYMBOLS] the wide calendar's name changes: process date (the ex-date when blank), cut at read, undated / empty / unchanged dropped and counted, the same change twice is one, sorted
        hdr = ",".join(M17.CA_COLS)
        nrows = ["name_change,,OLD1,NEW1,,2020-05-04,,,,,,,", "name_change,,OLD2,NEW2,2021-01-04,2021-01-06,,,,,,,", "name_change,,OLD3,NEW3,2022-03-01,,,,,,,,", "name_change,,OLD4,NEW4,,2025-07-01,,,,,,,", "name_change,,OLD5,NEW5,2025-07-02,2025-06-20,,,,,,,",
                 "name_change,,OLD6,NEW6,,,,,,,,,", "name_change,,,NEW7,,2020-01-01,,,,,,,", "name_change,,OLD8,OLD8,,2020-01-01,,,,,,,", "name_change,,OLD1,NEW1,,2020-05-04,,,,,,,", "cash_dividend,AAA,,,2024-01-10,2024-01-10,,,0.25,,,,False",
                 "name_change,,OLD9,NEW9,,2025-06-29,,,,,,,"]
        cp = os.path.join(root, "ca.csv")
        with open(cp, "w", newline="\n") as f:
            f.write("\n".join([hdr] + nrows) + "\n")
        ncf, nci = load_name_changes(cut, csv=cp)
        assert nci == {"present": True, "rows": 10, "dropped_at_the_cut": 2, "undated": 1, "empty_or_unchanged_symbol": 2, "kept": 4, "duplicates_merged": 1}, nci
        assert ncf.values.tolist() == [["OLD1", "NEW1", int(day_i(TS("2020-05-04")))], ["OLD2", "NEW2", int(day_i(TS("2021-01-06")))], ["OLD3", "NEW3", int(day_i(TS("2022-03-01")))], ["OLD9", "NEW9", int(day_i(TS("2025-06-29")))]], ncf.values.tolist()
        assert list(ncf.columns) == ["old", "new", "day"] and int(ncf["day"].max()) < int(day_i(cut)), "asserted free of the sealed year"
        e2, ei2 = load_name_changes(cut, csv=os.path.join(root, "absent.csv"))
        assert ei2 == {"present": False, "rows": 0} and len(e2) == 0
        with open(cp, "w", newline="\n") as f:
            f.write(",".join(c for c in M17.CA_COLS if c != "old_symbol") + "\nname_change,,NEW1,,2020-05-04,,,,,,,\n")
        refused(lambda: load_name_changes(cut, csv=cp), "lacks the column", "old_symbol")
    finally:
        shutil.rmtree(root, ignore_errors=True)


def hand_world(root, names, days, finra, titles=None, filings=(), mrows=None, F=None, Vv=None, splits=(), release=None, cal_start="2016-06-01", name="hw", nc=None):
    """a hand-made World for the scores alone (every name in the universe at every session, r21's score world): its FINRA rows written as a synthetic pull and read by the REAL loaders, its asset titles the same, its filings and symbol -> CIK map as NETISS's score worlds, the calendar's splits and the
    split factor F as given -> (W with W.si attached, the FINRA table)"""
    pull = fake_pull(root, finra, release=release, name=name)
    cache, csha = fake_assets(root, titles if titles is not None else {n: f"{n} Common Stock" for n in names}, name=name + "_cache")
    with pulled(pull, cache, csha):
        fin, _fi = load_finra(S.LB0)
        assets = load_assets()
    W = NI.score_world(days, names, F=F, Vv=Vv)
    mp = NI.mp_of(mrows if mrows is not None else [(n, f"C{i}", "current_ticker") for i, n in enumerate(names)])
    fx = NI.build_facts(NI.fr(list(filings) or [("C0", NI.DEI, 1.0, "2000-01-01", "2000-01-02")]))
    exist = {n: (int(day_i(days[0])), int(day_i(days[-1]))) for n in names}
    attach_shortint(W, fin, assets, pd.DataFrame({"old": [], "new": [], "day": np.zeros(0, np.int64)}) if nc is None else nc, exist, fx, mp, NI.cal_of(splits, cal_start))
    return W, fin


def code_of(sc, cell, j):
    return REASONS[int(cell_score(sc, cell)[1][j])]


def t_scores():
    """D1 and S1 on a hand-made world of 30 names with one planted case each, the exact numbers written out: D1 = SI / the mean RAW volume of the 20 sessions ending at s* (15 of 20 present is enough, 14 is not, a split on any of the 20 - the first included, the one before it not -
    from the calendar OR from F is none, SI = 0 is a score, a zero ADV is none); S1 = SI / (S x F(a) / F(s*)) (the carry by F, a count first filed ON s* is not yet known, 200 days old stands and 201 is stale, a foreign filer / a name outside the map / a CIK with two symbols / a zero
    count / no split factor, [A3]'s two-way check, the rank's ln(1000) scale rule with S1 = 0 exempt); the join rules (no row, a ticker listed twice), the funds (asset-list title, FINRA issue name), FINRA's revised row (dropped, scored in the twin), the latest USABLE file (the earlier file at
    the rank before the later one is known, no file before any is), the coverage and the report's counts - every one on the real loaders and the real score"""
    root = tmp()
    try:
        days = pd.bdate_range("2018-01-01", "2019-03-29")
        T = len(days)
        names = ["AAA", "BBB", "CCC", "DDD", "EEE", "FFF", "GGG", "HHH", "III", "JJJ", "KKK", "LLL", "MMM", "NNN", "OOO", "PPP", "QQQ", "RRR", "SSS", "TTT", "UUU", "VVV", "WWW", "XXX", "YYY", "ZZ1", "ZZ2", "ZZ3", "ZZ4", "ZZ5"]
        ix = {n: i for i, n in enumerate(names)}
        di = lambda s_: int(days.get_loc(TS(s_)))
        s_prev, s = "2018-11-30", "2018-12-14"
        isr = di(s)
        r = isr + 13
        S_ = len(names)
        rows = [frow(s_prev, n, 1_000_000) for n in names]
        si = {n: 4_000_000 for n in names}
        si.update(GGG=0, LLL=20_000_000_000, III=None, JJJ=-5)
        for n in names:
            if n == "VVV":
                continue                                                                                      # VVV has no row in the later file
            kw = {"rev": "R"} if n == "HHH" else {"split": "S"} if n in ("AAA", "DDD") else {}
            rows.append(frow(s, n, si[n], name=("XXX Core ETF" if n == "XXX" else None), **kw))
        rows.append(frow(s, "WWW", 4_000_000, mkt="OTC"))                                                     # WWW is listed twice in that file
        Vv = np.full((T, S_), 2e6)
        Vv[isr - 19:isr - 13, ix["BBB"]] = np.nan                                                             # 6 of the 20 sessions without a volume: 14 present
        Vv[:, ix["CCC"]] = 3e6
        Vv[isr - 19:isr - 14, ix["CCC"]] = np.nan                                                             # 5 missing: 15 present - enough
        Vv[:, ix["KKK"]] = 0.0
        Vv[isr + 1:, :] = 9e9                                                                                 # nothing after s* is ever read
        F = np.ones((T, S_))
        F[:isr - 5, ix["DDD"]] = 2.0                                                                          # a 2-for-1 on session s* - 5: inside the window
        F[:isr - 19, ix["EEE"]] = 2.0                                                                         # ... on the window's FIRST session
        F[:isr - 20, ix["FFF"]] = 2.0                                                                         # ... on the session before it
        F[:di("2018-10-22"), ix["ZZ2"]] = 2.0                                                                 # an F change the calendar does not show (before the window)
        F[di("2018-09-28"), ix["ZZ3"]] = np.nan                                                               # no factor on the as-of session
        F[:isr - 8, ix["ZZ5"]] = 2.0                                                                          # an F change the calendar does not show, inside the window
        splits = [("DDD", days[isr - 5], "forward_split"), ("EEE", days[isr - 19], "forward_split"), ("FFF", days[isr - 20], "forward_split"), ("ZZ1", days[di("2018-10-15")], "forward_split"), ("ZZ4", days[isr - 8], "forward_split")]
        filings = []
        for n in names:
            if n in ("RRR", "SSS", "TTT", "MMM", "NNN", "OOO", "UUU"):
                continue
            filings.append((("CQ" if n == "QQQ" else f"C{ix[n]}"), NI.DEI, 100e6, "2018-09-30", "2018-11-01"))
        filings += [("C" + str(ix["MMM"]), NI.DEI, 100e6, "2018-05-28", "2018-06-27"), ("C" + str(ix["NNN"]), NI.DEI, 100e6, "2018-05-27", "2018-06-27"), ("C" + str(ix["OOO"]), NI.DEI, 100e6, "2018-09-30", "2018-11-01", None, "20-F"),
                    ("C" + str(ix["SSS"]), NI.DEI, 100e6, "2018-11-30", "2018-12-14"), ("C" + str(ix["TTT"]), NI.DEI, 80e6, "2018-11-30", "2018-12-13"), ("C" + str(ix["UUU"]), NI.DEI, 0.0, "2018-09-30", "2018-11-01")]
        mrows = [(n, "CQ" if n in ("QQQ", "RRR") else f"C{ix[n]}", "current_ticker") for n in names if n != "PPP"]
        titles = {n: f"{n} Common Stock" for n in names}
        titles["YYY"] = "YYY Growth Fund"
        W, fin = hand_world(root, names, days, rows, titles=titles, filings=filings, mrows=mrows, F=F, Vv=Vv, splits=splits)
        sc = score_rank(W, r)
        assert (sc.k, sc.s_day, sc.age, sc.r, sc.f) == (1, int(day_i(TS(s))), 13, r, r + 1) and sc.n_uni0 == 30 and sc.n_title == 1 and sc.n_name == 1 and sc.n_uni == 28 and sc.n_cov == 27 and abs(sc.cov - 27 / 28) < 1e-12 and sc.covered is True, (sc.k, sc.age, sc.n_uni, sc.n_cov)
        assert sc.mc == {"ok": 27, "unknown": 0, "shared": 0, "no_row": 1, "duplicate": 1}, sc.mc
        assert sc.in_uni.sum() == 28 and not sc.in_uni[ix["XXX"]] and not sc.in_uni[ix["YYY"]] and sc.in_uni[ix["VVV"]] and sc.in_uni[ix["WWW"]], "funds are out of the universe; a name with no row stays in it (and counts against the coverage)"
        want = {"AAA": (2.0, 0.04), "BBB": ("adv_under_15_sessions", 0.04), "CCC": (4.0 / 3.0, 0.04), "DDD": ("split_in_volume_window", 0.02), "EEE": ("split_in_volume_window", 0.02), "FFF": (2.0, 0.02), "GGG": (0.0, 0.0),
                "HHH": ("revised_row", "revised_row"), "III": ("si_missing_or_negative", "si_missing_or_negative"), "JJJ": ("si_missing_or_negative", "si_missing_or_negative"), "KKK": ("adv_not_positive", 0.04), "LLL": (10000.0, "scale_error"),
                "MMM": (2.0, 0.04), "NNN": (2.0, "share_count_over_200_days"), "OOO": (2.0, "foreign_filer"), "PPP": (2.0, "not_in_map"), "QQQ": (2.0, "multi_class_cik"), "RRR": (2.0, "multi_class_cik"), "SSS": (2.0, "no_share_fact_at_s"),
                "TTT": (2.0, 0.05), "UUU": (2.0, "value_not_positive"), "VVV": ("no_finra_row", "no_finra_row"), "WWW": ("duplicate_finra_rows", "duplicate_finra_rows"), "XXX": ("fund_finra_name", "fund_finra_name"),
                "YYY": ("fund_asset_title", "fund_asset_title"), "ZZ1": (2.0, "split_calendar_not_in_F"), "ZZ2": (2.0, "split_F_not_in_calendar"), "ZZ3": (2.0, "no_split_factor"), "ZZ4": ("split_in_volume_window", "split_calendar_not_in_F"),
                "ZZ5": ("split_in_volume_window", "split_F_not_in_calendar")}
        assert set(want) == set(names)

        def check(sc_, want_, tag):
            for n, w in want_.items():
                for c, wv in zip(CELLS, w):
                    val, code = cell_score(sc_, c)[0][ix[n]], code_of(sc_, c, ix[n])
                    if isinstance(wv, str):
                        assert code == wv and math.isnan(val), (tag, n, c, code, val, wv)
                    else:
                        assert code == "scored" and abs(val - wv) <= 1e-12 * max(1.0, abs(wv)), (tag, n, c, code, val, wv)
        check(sc, want, "registered")
        assert abs(sc.s1_median - 0.04) < 1e-12, "the median of the scored S1 > 0 before the scale rule: 3 x 0.02, 4 x 0.04, 0.05, 200"
        assert sc.adv[ix["AAA"]] == 2e6 and sc.adv[ix["CCC"]] == 3e6 and sc.n_pres[ix["CCC"]] == 15 and sc.n_pres[ix["BBB"]] == 14 and math.isnan(sc.adv[ix["BBB"]]) and sc.adv[ix["KKK"]] == 0.0, "the ADV is the mean of the PRESENT sessions, defined from 15 of them; after s* nothing is read"
        ss = sc.sc
        assert ss.zero_si[ix["GGG"]] and ss.zero_si.sum() == 1 and ss.rev[ix["HHH"]] and ss.rev.sum() == 1 and ss.spl_flag[ix["DDD"]] and ss.spl_flag[ix["AAA"]] and ss.spl_flag.sum() == 2 and ss.fund_name[ix["XXX"]] and ss.fund_name.sum() == 1
        assert ss.age_s[ix["MMM"]] == 200 and ss.age_s[ix["NNN"]] == 201 and ss.age_s[ix["TTT"]] == 14 and ss.age_s[ix["AAA"]] == 75 and abs(float(ss.Scar[ix["DDD"]]) - 200e6) < 1 and abs(float(ss.Scar[ix["FFF"]]) - 200e6) < 1 and abs(float(ss.Scar[ix["AAA"]]) - 100e6) < 1, "S x F(a) / F(s*)"
        # the twin: FINRA's revised row scored as it stands
        sa = score_rank(W, r, "asis")
        check(sa, {**want, "HHH": (2.0, 0.04)}, "asis")
        assert score_rank(W, r) is sc and score_rank(W, r, "asis") is sa and sa is not sc, "cached per (rank, reading)"
        # the latest USABLE file: the earlier one at the rank before the later one is known, none before any is
        r_prev = di(s_prev) + 13
        sp = score_rank(W, r_prev)
        assert sp.k == 0 and sp.age == 13 and abs(cell_score(sp, "D1")[0][ix["AAA"]] - 0.5) < 1e-12 and abs(cell_score(sp, "S1")[0][ix["AAA"]] - 0.01) < 1e-12, "the file of 2018-11-30: SI 1,000,000 over the same 2,000,000 ADV"
        assert score_rank(W, isr + 12).k == 0 and score_rank(W, isr + 13).k == 1, "the later file is known from s* + 13 sessions (the first session after s* + 12)"
        s0 = score_rank(W, di(s_prev) + 12)
        assert s0.k == -1 and s0.covered is False and s0.n_uni == 29 and s0.n_title == 1 and s0.s_day == -1 and s0.sc is None and set(np.unique(s0.d1_code)) == {R_NO_FILE, R_FUND_TITLE} and int(s0.d1_code[ix["YYY"]]) == R_FUND_TITLE and np.isnan(s0.d1).all() and np.isnan(s0.s1).all()
        rn_ = (di(s_prev) + 12, di(s_prev) + 13, di(s_prev) + 33)                                            # the same rank in the report: no usable file -> no value, but the key is there (Stage A pools every rank's values per year)
        rn = score_report(W, [rn_], values=True)[0]
        assert rn["k"] == -1 and rn["settlement"] == "-" and rn["covered"] is False and rn["universe"] == 29 and rn["cells"]["D1"]["scored"] == 0 and len(rn["cells"]["D1"]["values"]) == 0 and len(rn["cells"]["S1"]["values"]) == 0 and "zero_si" not in rn["cells"]["D1"], rn
        assert (s0.s1_code == s0.d1_code).all() and int(s0.d1_code[ix["AAA"]]) == R_NO_FILE
        # the report and the lists, before any P&L: counts, by reason, per cell
        ranks = [(r, r + 1, r + 21)]
        rep = score_report(W, ranks, values=True)[0]
        assert rep["universe"] == 28 and rep["with_a_row"] == 27 and rep["covered"] is True and rep["funds_by_title"] == 1 and rep["funds_by_finra_name"] == 1 and rep["settlement"] == s and rep["age_sessions"] == 13 and rep["k"] == 1
        assert rep["revised_rows"] == 1 and rep["finra_split_flag_rows"] == 2 and rep["finra_split_flag_and_our_window_split"] == 1 and rep["our_window_split_without_the_flag"] == 3, "DDD carries the flag and a split in our window; EEE / ZZ4 / ZZ5 have a split in our window and no flag; AAA a flag and none"
        d1, s1 = rep["cells"]["D1"], rep["cells"]["S1"]
        assert d1["scored"] == 17 and s1["scored"] == 10 and d1["zero_si"] == 1 and s1["zero_si"] == 1
        assert {k: v for k, v in d1["reasons"].items() if v} == {"duplicate_finra_rows": 1, "no_finra_row": 1, "revised_row": 1, "si_missing_or_negative": 2, "adv_under_15_sessions": 1, "split_in_volume_window": 4, "adv_not_positive": 1}, d1["reasons"]
        assert {k: v for k, v in s1["reasons"].items() if v} == {"duplicate_finra_rows": 1, "no_finra_row": 1, "revised_row": 1, "si_missing_or_negative": 2, "multi_class_cik": 2, "not_in_map": 1, "foreign_filer": 1, "no_share_fact_at_s": 1, "value_not_positive": 1,
                                                                "share_count_over_200_days": 1, "split_calendar_not_in_F": 2, "split_F_not_in_calendar": 2, "no_split_factor": 1, "scale_error": 1}, s1["reasons"]
        assert s1["s_age_days"] == {"le30": 1, "d31_60": 0, "d61_100": 8, "d101_200": 1} and s1["old_counts"] == 1 and sum(d1["reasons"].values()) + d1["scored"] == 28 and sum(s1["reasons"].values()) + s1["scored"] == 28
        assert sorted(d1["values"].tolist()) == sorted([2.0] * 14 + [4.0 / 3.0, 0.0, 10000.0]) and len(s1["values"]) == 10 and abs(np.median(s1["values"]) - 0.04) < 1e-12
        assert -1.0 <= d1["finra_dtc_spearman"] <= 1.0 or math.isnan(d1["finra_dtc_spearman"])
        rows2 = score_report(W, [rn_] + ranks, values=True)                                                  # a no-file rank FIRST (the real stretch starts with three): the per-year block and Stage A's percentiles still pool the covered rank's values
        pby = percentiles_by_year(rows2)
        assert set(pby) == set(CELLS) and set(pby["D1"]) == {r_["year"] for r_ in rows2} and all(len(v) == 3 for c_ in CELLS for v in pby[c_].values()), pby
        assert pby["D1"][rep["year"]] == NI.pctl_text(d1["values"]) and pby["S1"][rep["year"]] == NI.pctl_text(s1["values"]), "the year's percentiles are the covered rank's (the no-file rank adds none)"
        yr0 = rows2[0]["year"]
        if yr0 != rep["year"]:
            assert all(math.isnan(q) for q in pby["D1"][yr0]), "a year with no scored value: NaNs"
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            print_score_report(rows2, values=True)
        assert "per fill year (scored names pooled over the year's ranks" in buf.getvalue() and "scored name-ranks over every rank" in buf.getvalue(), "the value block is printed when the first rank has no file"
        nov = score_report(W, ranks, values=False)[0]["cells"]["D1"]
        assert "values" not in nov and "finra_dtc_spearman" not in nov and "zero_si" in nov, "the dryload's report carries no value"
        by = unscored_by_name(W, ranks)
        assert by["D1"] == {"fund_asset_title": {"YYY": 1}, "fund_finra_name": {"XXX": 1}, "no_finra_row": {"VVV": 1}, "duplicate_finra_rows": {"WWW": 1}}, by["D1"]
        assert by["S1"] == {**by["D1"], "not_in_map": {"PPP": 1}, "multi_class_cik": {"QQQ": 1, "RRR": 1}, "foreign_filer": {"OOO": 1}}, by["S1"]
        fo = funds_out_rows(W, ranks)
        assert [(f_["symbol"], f_["by"], f_["title_tokens"], f_["ranks"]) for f_ in fo] == [("XXX", "FINRA issue name", "", 1), ("YYY", "asset-list title", "Fund", 1)] and fo[1]["asset_title"] == "YYY Growth Fund" and fo[0]["finra_names_with_a_token"] == "XXX Core ETF", fo
        cr = coverage_rows(W, ranks)[0]
        assert cr["settlement"] == s and cr["universe_before_funds"] == 30 and cr["funds_by_title"] == 1 and cr["funds_by_finra_name"] == 1 and cr["universe"] == 28 and cr["with_a_row"] == 27 and cr["covered"] is True and cr["join"] == sc.mc
        # the facts behind one name (the hand audit's columns)
        rec = SimpleNamespace(r=r, sc=sc)
        fl = si_fields(W, rec, "D1", ix["AAA"])
        assert fl["settlement"] == s and fl["source_file"] == "shrt20181214.csv" and fl["si"] == 4e6 and fl["prev_si_reported"] == 4e6 and fl["split_flag"] is True and fl["revision_flag"] is False and fl["cache_adv"] == 2e6 and fl["cache_adv_sessions"] == 20 and fl["d1"] == 2.0
        assert fl["si_1_settlement_earlier"] == 1e6 and math.isnan(fl["si_2_settlements_earlier"]) and fl["age_sessions"] == 13 and fl["ticker"] == "AAA", fl
        f1 = si_fields(W, rec, "S1", ix["TTT"])
        assert f1["shares"] == 80e6 and f1["shares_asof"] == "2018-11-30" and f1["shares_first_filed"] == "2018-12-13" and f1["F_asof"] == 1.0 and f1["F_s"] == 1.0 and abs(f1["s1"] - 0.05) < 1e-12 and f1["shares_form"] == "10-Q", f1
    finally:
        shutil.rmtree(root, ignore_errors=True)


def t_coverage():
    """[A2] the 90% rule exactly: a rank whose universe (the fill session's names less the funds) has a row in the latest usable file for 9 of 10 trades, 8 of 10 does not; the funds are out of the count (both kinds); a universe with nothing but funds has no coverage and never trades; the walk-forward starts at the first rank at or above 90%
    and never before 2018-08-01; the join's outcome per rank; a rank after the start that falls under 90% stays in the stretch"""
    root = tmp()
    try:
        days = pd.bdate_range("2018-01-01", "2018-12-31")
        names = [f"A{i}" for i in range(1, 11)] + ["F1", "F2"]
        s1, s2 = "2018-06-15", "2018-07-31"
        di = lambda s_: int(days.get_loc(TS(s_)))
        titles = {n: f"{n} Common Stock" for n in names}
        titles["F1"] = "F1 Municipal Income Fund"

        def world(n_rows_a, n_rows_b, tag):
            rows = []
            for s_, k in ((s1, n_rows_a), (s2, n_rows_b)):
                rows += [frow(s_, f"A{i}", 1000 * i) for i in range(1, k + 1)] + [frow(s_, "F1", 10), frow(s_, "F2", 10, name="F2 Total Index ETF")]
            return hand_world(root, names, days, rows, titles=titles, name=tag)[0]
        ra, rb = di(s1) + 13, di(s2) + 13
        ranks = [(ra, ra + 1, ra + 21), (rb, rb + 1, rb + 21)]
        W = world(9, 8, "w98")
        crows = coverage_rows(W, ranks)
        assert [(c["universe"], c["with_a_row"], c["covered"]) for c in crows] == [(10, 9, True), (10, 8, False)] and crows[0]["funds_by_title"] == 1 and crows[0]["funds_by_finra_name"] == 1 and crows[0]["universe_before_funds"] == 12
        assert abs(crows[0]["coverage"] - 0.9) < 1e-15 and abs(crows[1]["coverage"] - 0.8) < 1e-15 and crows[1]["join"] == {"ok": 8 + 1, "unknown": 0, "shared": 0, "no_row": 2, "duplicate": 0} and crows[0]["join"]["no_row"] == 1, (crows[0]["join"], crows[1]["join"])
        r_, lo_ = wf_start(W, ranks)
        assert r_ == ra and lo_ == WF0 == max(W.days[ra + 1], WF0), "the first rank at or above 90%; the stretch never starts before 2018-08-01 (the fill of this rank is 2018-07-03)"
        r2, lo2 = wf_start(world(8, 9, "w89"), ranks)
        assert r2 == rb and lo2 == W.days[rb + 1], "the first rank is under 90%: the walk-forward starts at the next one that is at or above"
        assert wf_start(world(7, 8, "w78"), ranks) == (None, None), "no rank qualifies: no start (NOT JUDGEABLE)"
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            print_coverage(coverage_rows(W, ranks), f"{W.days[ra]:%Y-%m-%d}", lo_)
            print_join(coverage_rows(W, ranks))
        txt = buf.getvalue()
        assert "[A2] COVERAGE per rank" in txt and "90.0% | yes" in txt and "80.0% | NO (under 90%)" in txt and "[SYMBOLS] the ticker join" in txt, txt
        assert f"the walk-forward STARTS at the first rank at or above 90%: rank {W.days[ra]:%Y-%m-%d} (positions from 2018-08-01); 1 of the 2 built ranks are covered, 1 after the start are not (they trade nothing and stay in the stretch)" in txt, txt
        # a universe of funds only: no coverage, no trade, never an exception (a world long enough for rebalances with a full window: every one has an empty universe)
        d2 = pd.bdate_range("2017-01-02", "2018-12-31")
        wf = hand_world(root, ["F1", "F2"], d2, [frow("2017-03-15", "F1", 10), frow("2017-03-15", "F2", 10, name="F2 Total Index ETF")], titles={"F1": "F1 Municipal Income Fund", "F2": "F2 Common Stock"}, name="wf")[0]
        rf_ = int(d2.get_loc(TS("2018-06-29")))
        cf = coverage_rows(wf, [(rf_, rf_ + 1, rf_ + 21)])[0]
        assert cf["universe"] == 0 and math.isnan(cf["coverage"]) and cf["covered"] is False and wf_start(wf, [(rf_, rf_ + 1, rf_ + 21)]) == (None, None)
        L = si_build(wf, d2[0], d2[-1], counts_only=True)
        assert len(L.recs) >= 10 and all(not rec.traded and rec.nu == 0 for rec in L.recs) and sum(c["empty"] for c in L.cnt.values()) == len(L.recs), "an empty universe is counted and trades nothing"
    finally:
        shutil.rmtree(root, ignore_errors=True)


def t_sides():
    """the sides: 50 a side at 150 scored names or more, below that the bottom / top THIRD (n // 3) when it is at least 20, else nothing; the 50 LOWEST are the longs and the 50 HIGHEST the shorts, ties at a cut broken by the name's ADV (highest first, no ADV last, then the lower column), the short
    side picked first and the sides never share a name - against plain sorts on random data full of ties"""
    assert [side_n(n) for n in (150, 400, 149, 100, 63, 60, 59, 5, 0)] == [(50, "top"), (50, "top"), (49, "third"), (33, "third"), (21, "third"), (20, "third"), (0, "none"), (0, "none"), (0, "none")]
    with spec(min_scored=8, min_side=2, n_side=3):
        assert [side_n(n) for n in (8, 20, 7, 6, 5)] == [(3, "top"), (3, "top"), (2, "third"), (2, "third"), (0, "none")]
    cols = np.arange(10, 20)
    longs, shorts = pick_sides(cols, [1, 1, 1, 2, 2, 3, 3, 3, 4, 5], np.array([5.0, 4.0, 3.0, 1.0, 2.0, 9.0, 8.0, 7.0, 1.0, 1.0]), 3)
    assert shorts.tolist() == [9, 8, 5] and longs.tolist() == [0, 1, 2], "shorts: 5, 4, then the highest-ADV of the three 3s (ADV 9); longs: the three 1s"
    longs, shorts = pick_sides(cols, [1, 1, 1, 2, 2, 3, 3, 3, 4, 5], np.array([5.0, 4.0, 3.0, 1.0, 2.0, 9.0, 8.0, 7.0, 1.0, 1.0]), 4)
    assert shorts.tolist() == [9, 8, 5, 6] and longs.tolist() == [0, 1, 2, 4], "the 4th long: the 2s tie, the higher ADV (2.0) first"
    longs, shorts = pick_sides(np.arange(6), [7.0] * 6, np.array([1.0, np.nan, 3.0, 3.0, 0.0, -1.0]), 3)
    assert shorts.tolist() == [2, 3, 0] and longs.tolist() == [1, 4, 5], "every score tied: the shorts by ADV (3.0, 3.0 -> the lower column, then 1.0), then the rest by column; a missing / non-positive ADV last"
    rng = np.random.default_rng(11)
    for trial in range(400):
        n = int(rng.integers(8, 40))
        k = int(rng.integers(1, n // 2 + 1))
        sc_ = rng.integers(0, 6, n).astype(float)
        adv = np.where(rng.random(n) < 0.15, np.nan, rng.integers(0, 5, n).astype(float))
        cl = np.sort(rng.choice(1000, n, replace=False))
        lg, sh = pick_sides(cl, sc_, adv, k)
        ad = [float(a) if (np.isfinite(a) and a > 0) else -math.inf for a in adv]
        want_sh = sorted(range(n), key=lambda i: (-sc_[i], -ad[i], cl[i]))[:k]
        rest = [i for i in range(n) if i not in want_sh]
        want_lg = sorted(rest, key=lambda i: (sc_[i], -ad[i], cl[i]))[:k]
        assert sh.tolist() == want_sh and lg.tolist() == want_lg and not set(sh.tolist()) & set(lg.tolist()) and len(sh) == len(lg) == k, trial
    # NaN scores never reach here (only scored names do); the ADV and the tie-break through the whole build are in t_pipeline


def t_pipeline():
    """the vectorised build against the plain-python recount (every join, score, pool, side, pick and daily path) on the toy world with the REGISTERED windows (252 / 230), in the registered reading, the look-ahead one and the revised-rows twin, 3 names a side (the 150 / thirds / 20 rule shrunk to 8 / 2); the planted cases
    of the toy by hand (a rename and a two-step chain walked back, a ticker two cache names held, a missing / duplicate / blank / negative / zero / x5000 short interest, a revised row, FINRA's split flag, a fund by asset title and one by FINRA name, a rank under 90% coverage, ranks before any file is known);
    a counts-only build; the walk-forward's start"""
    root, root2 = tmp(), tmp()
    try:
        with spec(n_side=3, min_scored=8, min_side=2), D15.spec(univ=20):
            toy = si_toy()
            W = toy.W
            src, pull = toy_ready_si(toy, root)
            truth = truth_of(toy)
            lo, hi = W.days[0], W.days[-1]
            ix = {str(n): j for j, n in enumerate(W.syms)}
            built, n_paths = {}, 0
            for pm, rm in (("remove", "drop"), ("naive", "drop"), ("remove", "asis")):
                L = si_build(W, lo, hi, pm, rm)
                Bz = brute_si(W, truth, lo, hi, pm, rm)
                n_paths += compare_si(W, L, Bz, f"toy {pm} {rm}")
                if (pm, rm) == ("remove", "drop"):
                    series_check_si(W, L, Bz)
                built[(pm, rm)] = (L, Bz)
            Lr = built[("remove", "drop")][0]
            assert n_paths > 5000 and len(Lr.recs) == 16, n_paths
            rk = lambda d: int(W.days.get_loc(TS(d)))
            sc_at = lambda d, rm="drop": score_rank(W, rk(d), rm)
            cds = lambda d, c, n, rm="drop": code_of(sc_at(d, rm), c, ix[n])
            val = lambda d, c, n, rm="drop": float(cell_score(sc_at(d, rm), c)[0][ix[n]])
            ranks = built_ranks(W, lo, hi)
            crows = coverage_rows(W, ranks)
            assert [c["covered"] for c in crows] == [True, True, True, False, True, True, True, True, True, False, True, True, True, True, True, True], [c["covered"] for c in crows]
            assert crows[3]["rank"] == "2025-03-31" and crows[3]["settlement"] == "2025-02-28" and crows[3]["universe"] == 15 and crows[3]["with_a_row"] == 13 and crows[9]["rank"] == "2025-09-30" and crows[9]["with_a_row"] == 12 and crows[9]["universe"] == 16
            assert crows[0]["universe_before_funds"] == 20 and crows[0]["funds_by_title"] == 1 and crows[0]["funds_by_finra_name"] == 1 and all(c["age_sessions"] in range(20, 24) for c in crows), "N15 is a fund by its asset title, N16 by FINRA's issue name; s* is 20-23 sessions old at a month-end rank"
            r_start, lo_s = wf_start(W, ranks)
            assert r_start == rk("2024-12-31") and lo_s == W.days[r_start + 1]
            # the planted cases, rank by rank (s* is the month-end file of the month before)
            for c in CELLS:
                assert cds("2025-03-31", c, "N17") == "no_finra_row" and cds("2025-03-31", c, "N19") == "si_missing_or_negative" and cds("2025-03-31", c, "N09") == "ticker_shared", c
                assert cds("2025-03-31", c, "N15") == "fund_asset_title" and cds("2025-03-31", c, "N16") == "fund_finra_name" and cds("2025-07-31", c, "N12") == "duplicate_finra_rows" and cds("2025-04-30", c, "N08") == "revised_row", c
                assert cds("2025-04-30", c, "N08", "asis") != "revised_row", "the twin scores the revised row"
                assert [cds("2025-09-30", c, n) for n in ("N01", "N02", "N03", "N06")] == ["no_finra_row"] * 4, c
            assert val("2025-04-30", "D1", "N14") == 0.0 and cds("2025-04-30", "D1", "N14") == "scored" and val("2025-04-30", "S1", "N14") == 0.0 and cds("2025-04-30", "S1", "N14") == "scored" and sc_at("2025-04-30").sc.zero_si[ix["N14"]], "SI = 0 is a score"
            assert cds("2025-04-30", "D1", "N00") == "split_in_volume_window" and cds("2025-04-30", "S1", "N00") == "scored", "N00's 2-for-1 of 2025-03-14 is inside the 20 sessions ending 2025-03-31: no D1; S1 carries it by F"
            assert cds("2025-05-30", "S1", "N11") == "scale_error" and cds("2025-05-30", "D1", "N11") == "scored" and val("2025-05-30", "D1", "N11") > 100 * val("2025-05-30", "D1", "N10"), "the x5000 short interest: S1's scale rule, D1 has none"
            assert bool(sc_at("2025-04-30").sc.spl_flag[ix["N00"]]) and bool(sc_at("2025-04-30").sc.split_win[ix["N00"]]), "FINRA's split flag and our window agree for N00"
            assert str(sc_at("2024-12-31").sc.tk[ix["N05"]]) == "O05" and str(sc_at("2025-01-31").sc.tk[ix["N05"]]) == "N05", "N05 was O05 until 2024-12-02: the file of 2024-11-29 lists O05"
            assert [str(sc_at(d).sc.tk[ix["N07"]]) for d in ("2024-12-31", "2025-02-28", "2025-03-31")] == ["Q07", "Q07", "N07"], "N07: P07 -> Q07 (2024-06-03) -> N07 (2025-02-03); the file of 2025-02-28 lists N07"
            assert sc_at("2025-04-30").sc.mcode[ix["N09"]] == M_OK and sc_at("2025-03-31").sc.mcode[ix["N09"]] == M_SHARED and sc_at("2025-03-31").sc.mcode[ix["N17"]] == M_NO_ROW and sc_at("2025-07-31").sc.mcode[ix["N12"]] == M_DUP, "N09's old ticker O09 was held by a cache-only name until 2025-03-14"
            tbl = W.si.tab
            assert Counter(map(str, tbl.binding)) == Counter({"s+12": 55, "photographed": 1}) and tbl.binding[10] == "photographed", "one release the photographed schedule puts far later than s + 12 sessions binds"
            # the modes and the traded rebalances
            modes = {c: Counter(rec.cell[c].mode for rec in Lr.recs) for c in CELLS}
            assert modes["D1"] == {"top": 14, "uncovered": 2} and modes["S1"] == {"top": 14, "uncovered": 2}, modes
            assert all(not rec.cell[c].traded for rec in Lr.recs if not rec.sc.covered for c in CELLS) and all(rec.cell[c].k == 3 for rec in Lr.recs for c in CELLS if rec.cell[c].traded)
            st = scored_stats(Lr)
            assert st["D1"]["traded"] == st["S1"]["traded"] == 14 and st["D1"]["rebalances"] == 16 and st["D1"]["modes"] == {"top": 14, "uncovered": 2} and st["D1"]["min"] >= 10, st
            Lk, Lv = built[("naive", "drop")][0], built[("remove", "asis")][0]
            for a_, b_ in zip(Lr.recs, Lk.recs):
                assert set(a_.pool.tolist()) <= set(b_.pool.tolist()), "the look-ahead reading keeps the names the registered one removes inside the hold"
            assert sum(c["ns_D1_revised_row"] for c in Lr.cnt.values()) >= 1 and sum(c.get("ns_D1_revised_row", 0) for c in Lv.cnt.values()) == 0, "the twin has no revised-row reason"
            # a counts-only build keeps no unit path and no pick but counts the same
            Lc = si_build(W, lo, hi, "remove", "drop", units=False, counts_only=True)
            assert [rec.pool.tolist() for rec in Lc.recs] == [rec.pool.tolist() for rec in Lr.recs] and all(rec.U is None and not len(rec.cell["D1"].long) for rec in Lc.recs)
            for y, c in Lr.cnt.items():
                for k_ in [k2 for k2 in c if k2.startswith(("scored_", "no_score_", "mode_", "ns_", "rank_")) or k2 in ("universe", "funds_title", "funds_name", "rebalances")]:
                    assert Lc.cnt[y][k_] == c[k_], (y, k_)
            assert sum(rec.cell[c].traded for rec in Lc.recs for c in CELLS) == sum(rec.cell[c].traded for rec in Lr.recs for c in CELLS)
            assert sum(c["rank_covered"] for c in Lr.cnt.values()) == 14 and sum(c["rank_uncovered"] for c in Lr.cnt.values()) == 2 and sum(c["rank_nofile"] for c in Lr.cnt.values()) == 0
            # a data event of the hand audit removes the name-month from the pool, both cells
            rec = next(r_ for r_ in Lr.recs if W.days[r_.r] == TS("2025-05-30"))
            j = int(rec.pool[rec.cell["D1"].idx[rec.cell["D1"].long[0]]])
            W.aud1[rec.f, j] = True
            L1 = si_build(W, lo, hi)
            r1 = next(r_ for r_ in L1.recs if r_.r == rec.r)
            assert j in rec.pool.tolist() and j not in r1.pool.tolist() and all(j not in r1.pool[r1.cell[c].idx].tolist() for c in CELLS) and (AUD, rec.f, j) in W.aud_hit and L1.cnt[2025]["audit"] >= 1
            W.aud1[:] = False
            W.aud_hit.clear()
            # ---- ranks before any file is known: the toy's first file is 2025-01-15 (usable from 2025-02-03): the 2024-12-31 and 2025-01-31 ranks have no usable file
            toy2 = si_toy(first="2025-01-15")
            W2 = toy2.W
            src2, pull2 = toy_ready_si(toy2, root2)
            truth2 = truth_of(toy2)
            L2 = si_build(W2, W2.days[0], W2.days[-1])
            Bz2 = brute_si(W2, truth2, W2.days[0], W2.days[-1])
            n2 = compare_si(W2, L2, Bz2, "toy nofile")
            series_check_si(W2, L2, Bz2)
            m2 = {c: [rec.cell[c].mode for rec in L2.recs] for c in CELLS}
            assert all(m[:2] == ["nofile", "nofile"] and "nofile" not in m[2:] for m in m2.values()) and all(rec.sc.k < 0 and not rec.sc.covered for rec in L2.recs[:2]) and L2.recs[2].sc.k >= 0, m2
            assert all(code_of(L2.recs[0].sc, c, ix["N00"]) == "no_usable_file" for c in CELLS) and code_of(L2.recs[0].sc, "D1", ix["N15"]) == "fund_asset_title", "no usable file: every name has that reason but a fund by its title"
            assert sum(c["rank_nofile"] for c in L2.cnt.values()) == 2 and sum(c.get("mode_D1_nofile", 0) for c in L2.cnt.values()) == 2
            ranks2 = built_ranks(W2, W2.days[0], W2.days[-1])
            cr2 = coverage_rows(W2, ranks2)
            r_s2, _lo2 = wf_start(W2, ranks2)
            assert [c["k"] < 0 for c in cr2[:3]] == [True, True, False] and cr2[0]["settlement"] == "-" and cr2[0]["age_sessions"] == -1 and r_s2 == ranks2[2][0], "the walk-forward starts at the first rank with a usable file and 90% coverage"
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                print_coverage(cr2, f"{W2.days[r_s2]:%Y-%m-%d}", W2.days[r_s2 + 1])
                print_join(cr2)
            assert "no usable file" in buf.getvalue() and "NO (no usable file)" in buf.getvalue()
    finally:
        shutil.rmtree(root, ignore_errors=True)
        shutil.rmtree(root2, ignore_errors=True)
    return n_paths + n2


def t_nulls():
    """the family-aware null: 500 uniform draws per rebalance of as many names as the cell holds from the same eligible SCORED pool (here 3 a side), seeded, one stream per cell (and per reading), longs and shorts disjoint, no P&L before the first fill, nothing drawn for a rank that trades nothing
    (under 90% coverage), the mean over the draws equal to the pool's mean path, three whole draws recounted by plain python (the draw's names from the same stream, every path and the sizing recomputed), the statistic = the MAX over the 2 cells per draw -> p5 / p50 / p95, and the DO of every draw
    against the reference's drawdown days"""
    root = tmp()
    try:
        with spec(n_side=3, min_scored=8, min_side=2), D15.spec(univ=20):
            toy = si_toy()
            W = toy.W
            toy_ready_si(toy, root)
            L = si_build(W, W.days[0], W.days[-1])
            assert sum(not rec.cell["D1"].traded for rec in L.recs) == 2, "two ranks are under 90% coverage: they trade nothing, so the null draws nothing for them"
            acc = si_null(W, L, 400, 0)
            assert set(acc) == set(CELLS) and all(a.shape == (400, W.T) for a in acc.values())
            kz0 = W.kz.copy()
            W.kz[:] = 2.5                                                                       # the volatility lean of r15's S cells: this family has none - k_t is read only by the borrow stress
            assert all((si_null(W, L, 400, 0)[c] == acc[c]).all() for c in CELLS)
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
                for rec in L.recs:
                    if not rec.cell[cell].traded:
                        assert (acc[cell][:, rec.f + 1:rec.x] == 0).all(), "a rank that trades nothing has no random book either (its first and last rows belong to the neighbouring holds)"
            again = si_null(W, L, 400, 0)
            assert all((again[c] == acc[c]).all() for c in CELLS), "seeded"
            assert not (si_null(W, L, 400, 1)["D1"] == acc["D1"]).all(), "the other reading draws a different stream"
            assert not (acc["D1"] == acc["S1"]).all(), "own stream per cell"
            for q, cell in enumerate(CELLS):                                                    # three whole draws recounted: the stream's names for each traded rebalance in order, every path by plain python
                rng = np.random.default_rng([SEED, q, 0])
                draws = []
                for rec in L.recs:
                    cc = rec.cell[cell]
                    if cc.traded:
                        draws.append((rec, D15.draw_order(rng, 400, cc.n, 2 * cc.k)))
                assert len(draws) == 14
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
    finally:
        shutil.rmtree(root, ignore_errors=True)
    # the statistic: the max over the 2 cells per draw, then p5 / p50 / p95; the DO the same way
    ix = pd.bdate_range("2018-08-01", "2025-06-27")
    rng = np.random.default_rng(2)
    book = rng.normal(35.0, 650.0, len(ix))
    S12 = M12.Stretch(book, ix, None, WF0, PRE_END)
    pc = {c: D15.null_cell(S12, rng.normal(5, 100, (40, len(ix))), np.arange(len(ix)), len(ix))[0] for c in CELLS}
    pdo = {c: rng.normal(0.0, 0.2, 40) for c in CELLS}
    ns = null_summary(pc, pdo)
    mx = np.max(np.vstack([pc[c] for c in CELLS]), axis=0)
    mdo = np.max(np.vstack([pdo[c] for c in CELLS]), axis=0)
    assert ns["draws"] == 40 and ns["seed"] == SEED and all(abs(ns["roc_max"][k] - np.percentile(mx, v)) < 1e-9 for k, v in (("p5", 5), ("p50", 50), ("p95", 95)))
    assert all(abs(ns["do_ref_max"][k] - np.percentile(mdo, v)) < 1e-9 for k, v in (("p5", 5), ("p50", 50), ("p95", 95))) and set(ns["do_ref_by_cell"]) == set(CELLS) and ns["roc_max"]["p95"] >= max(ns["by_cell"][c]["p95"] for c in CELLS) - 1e-9
    assert "do_ref_max" not in null_summary(pc) and null_summary(pc)["seed"] == SEED
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        print_power(ns)
    assert buf.getvalue().startswith("POWER LINE [A6] - printed before any cell's P&L: the random-name null (40 draws, seed 20261018, the MAX over the 2 cells), ROC@30k p5 ") and "each cell alone p50 / p95: D1 " in buf.getvalue() and "S1 " in buf.getvalue(), buf.getvalue()


def t_audit():
    """the hand audit's file (f): read and checked (a mistyped row refuses, it never silently does nothing), a data_event removes that name-month - the key is the FILL date - from the pool, so from both cells and the nulls; a keep changes nothing; a data_event that removed nothing is reported;
    the audit status of the listed top-50"""
    root = tmp()
    try:
        with spec(n_side=3, min_scored=8, min_side=2), D15.spec(univ=20):
            toy = si_toy()
            W = toy.W
            toy_ready_si(toy, root)
            ap = os.path.join(root, "shortint_audit.csv")
            assert read_audit(ap) is None
            with open(ap, "w") as f:
                f.write(f"symbol,date,cell,verdict,note\nN08,{W.days[270]:%Y-%m-%d},D1,data_event,split\nN01,{W.days[280]:%Y-%m-%d},s1,KEEP,fine\nN09,{W.days[300]:%Y-%m-%d},S1,data_event,bad row\n")
            au = read_audit(ap)
            assert au["verdict"].tolist() == ["data_event", "keep", "data_event"] and au["cell"].tolist() == ["D1", "S1", "S1"]
            cnt = apply_audit(W, au)
            assert cnt == {"rows": 3, "keep": 1, "data_event": 2} and W.aud1[270, 8] and W.aud1[300, 9] and W.aud1.sum() == 2
            assert apply_audit(W, None)["rows"] == 0 and not W.aud1.any()
            for bad in (f"N08,{W.days[270]:%Y-%m-%d},D1,maybe,x\n", "N08,not-a-date,D1,keep,x\n", f"N08,{W.days[270]:%Y-%m-%d},RES,keep,x\n", f",{W.days[270]:%Y-%m-%d},D1,keep,x\n", f"N08,{W.days[270]:%Y-%m-%d},N12,keep,x\n"):
                with open(ap, "w") as f:
                    f.write("symbol,date,cell,verdict,note\n" + bad)
                refused(lambda: read_audit(ap), "line(s) [2]")
            with open(ap, "w") as f:
                f.write("symbol,date\nN08,2024-01-01\n")
            refused(lambda: read_audit(ap), "lacks the column")
            for sym, d_ in (("ZZZ", W.days[270]), ("N08", pd.Timestamp("2025-01-04"))):
                with open(ap, "w") as f:
                    f.write(f"symbol,date,cell,verdict,note\n{sym},{d_:%Y-%m-%d},D1,data_event,x\n")
                refused(lambda: apply_audit(W, read_audit(ap)), "match no session or no name")
            L0 = si_build(W, W.days[0], W.days[-1])
            rec = next(r_ for r_ in L0.recs if W.days[r_.r] == TS("2025-05-30"))
            d0 = f"{W.days[rec.f]:%Y-%m-%d}"
            ap2 = os.path.join(root, "a2.csv")
            with open(ap2, "w") as f:
                f.write(f"symbol,date,cell,verdict,note\nN08,{d0},D1,data_event,x\nN05,{d0},D1,data_event,x\nN03,{d0},S1,keep,fine\n")
            au2 = read_audit(ap2)
            apply_audit(W, au2)
            assert unused_audit_rows(W, au2) == [f"N08 {d0} D1", f"N05 {d0} D1"], "before any build both removed nothing"
            L1 = si_build(W, W.days[0], W.days[-1])
            r1 = next(r_ for r_ in L1.recs if r_.r == rec.r)
            gone = [j for j in (8, 5) if j in rec.pool.tolist() and j not in r1.pool.tolist()]
            assert len(gone) >= 1 and all((AUD, rec.f, j) in W.aud_hit for j in gone), gone
            left = [f"{'N%02d' % j} {d0} D1" for j in (8, 5) if j not in gone]
            assert unused_audit_rows(W, au2) == left, (unused_audit_rows(W, au2), left)
            for j in gone:
                assert all(j not in r1.pool[r1.cell[c].idx].tolist() for c in CELLS) and L1.cnt[2025]["audit"] >= len(gone), "the name-month is out of both cells' scored names"
            acc = si_null(W, L1, 12, 0)
            assert all(a.shape == (12, W.T) for a in acc.values()), "the nulls are drawn from the pool the audit left"
            W.aud1[:] = False
            W.aud_hit.clear()
            cands = {"D1": [{"symbol": "N08", "date": d0}], "S1": [{"symbol": "N08", "date": d0}, {"symbol": "N05", "date": "2024-01-01"}]}
            st = M17.audit_status(cands, au2)
            assert st == {"D1": {"listed": 1, "audited": 1, "audit_complete": True}, "S1": {"listed": 2, "audited": 1, "audit_complete": False}}, st
            assert M17.audit_status({"D1": []}, None) == {"D1": {"listed": 0, "audited": 0, "audit_complete": False}}
    finally:
        shutil.rmtree(root, ignore_errors=True)


def t_judge():
    """Stage A's (a)-(e) as r17_resmom's with this family's years and its binding borrow stress: >= 60 rebalances, ROC >= 15, net > 0 at 5 / 10 bps AND with the flat 3% borrow on every short, ROC above the null's p95 (the max over the 2 cells), positive in two thirds of the July-June years rounded up (7 -> 5,
    6 -> 4, 9 -> 6, 3 -> 2, 1 -> 1), net > 0 without Feb 15 - Apr 30 2020, profitable without its best 1% of days and of name-months; a NaN never passes; the tie-break between two passing cells; the beta credit on hand betas; the break-even borrow fee (net is exactly linear in the flat rate);
    A2's window; the years a cell holds a position in"""
    R = RULES
    st0 = {"n_units": 100, "roc": 20.0, "net": 1000.0, "years_pos": 7, "net_ex2020": 500.0, "net_ex_best_days": 100.0, "net_ex_best_pos": 100.0}
    nul0 = {"roc_max": {"p95": 10.0}}
    ck = judge_cell(st0, 50.0, 40.0, nul0, 7)
    names = [f"rebalances>={R['reb']}", f"ROC>={R['roc']:g}", "net>0 at 5 bps", "net>0 at 10 bps", "net>0 with the flat 3% borrow", "ROC>null p95", "positive in >=5 of 7 July-June years", "net>0 without Feb 15 - Apr 30 2020", "profitable without its best 1% of days",
             "profitable without its best 1% of name-months"]
    assert list(ck) == names and all(ck.values()) and all(isinstance(v, bool) for v in ck.values()), ck
    nan = float("nan")

    def broken(n_years=7, **kw):
        st, net10, net3, nul = dict(st0), 50.0, 40.0, nul0
        for k, v in kw.items():
            if k == "net10":
                net10 = v
            elif k == "net3":
                net3 = v
            elif k == "p95":
                nul = {"roc_max": {"p95": v}}
            else:
                st[k] = v
        return {k for k, v in judge_cell(st, net10, net3, nul, n_years).items() if not v}
    assert broken(n_units=59) == {names[0]} and broken(n_units=60) == set() and broken(roc=14.99) == {names[1]} and broken(roc=15.0) == set() and broken(roc=15.0, p95=15.0) == {names[5]} and broken(roc=15.0, p95=14.99) == set()
    assert broken(net=0.0) == {names[2]} and broken(net10=0.0) == {names[3]} and broken(net3=0.0) == {names[4]} and broken(net3=-1.0) == {names[4]} and broken(net_ex2020=0.0) == {names[7]} and broken(net_ex_best_days=0.0) == {names[8]} and broken(net_ex_best_pos=0.0) == {names[9]}
    assert broken(years_pos=4) == {names[6]} and broken(years_pos=5) == set(), "7 years: at least 5 positive, inclusive"
    assert broken(roc=nan) == {names[1], names[5]} and broken(net=nan) == {names[2]} and broken(net10=nan) == {names[3]} and broken(net3=nan) == {names[4]} and broken(years_pos=nan) == {names[6]} and broken(net_ex_best_pos=nan) == {names[9]}, "a NaN never passes"
    for n, need in ((9, 6), (8, 6), (7, 5), (6, 4), (3, 2), (2, 2), (1, 1)):
        lab = f"positive in >={need} of {n} July-June years"
        assert lab in judge_cell(st0, 50.0, 40.0, nul0, n), (n, need, list(judge_cell(st0, 50.0, 40.0, nul0, n)))
        assert broken(n, years_pos=need - 1) == {lab} and broken(n, years_pos=need) == set() and broken(n, years_pos=n) == set(), (n, need)
    # the tie-break and Stage A's bookkeeping
    mk = lambda v1, v2, roc=(20.0, 30.0): {"D1": {"PASS": v1, "base": {"roc": roc[0]}}, "S1": {"PASS": v2, "base": {"roc": roc[1]}}}
    assert stage_a_flow(mk(True, True)) == (["D1", "S1"], "S1") and stage_a_flow(mk(True, True, roc=(30.0, 30.0)))[1] == "D1" and stage_a_flow(mk(True, False, roc=(16.0, 90.0))) == (["D1"], "D1") and stage_a_flow(mk(False, False)) == ([], None)
    assert pick_candidate({"D1": {"base": {"roc": 5.0}}, "S1": {"base": {"roc": 5.0}}}, ["D1", "S1"]) == "D1" and pick_candidate({}, []) is None
    # the beta credit: BOTH betas within 0.20 of one side's notional ($200,000 = 50 x $4,000), on L's Stretch for the stretch
    seen = []

    def with_betas(dd, al):
        def stub(B_, S12_, W_, rows_, xB_):
            seen.append(S12_)
            return {"DD days": {"usd_per_1.00_es": dd}, "all WF days": {"usd_per_1.00_es": al}}
        with patched(D15, es_beta=stub):
            return beta_credit(None, SimpleNamespace(ref=SimpleNamespace(S="L's stretch")), None, None, None)
    side = M17.SPEC["n_side"] * M17.SPEC["slot"]
    b = with_betas(30000.0, 20000.0)
    assert b["side_notional"] == side == 200000.0 and abs(b["beta_dd_days"] - 0.15) < 1e-12 and abs(b["beta_all_days"] - 0.10) < 1e-12 and b["within_cap"] is True and b["cap"] == 0.20 and seen == ["L's stretch"]
    assert with_betas(40000.0, 0.0)["within_cap"] is True and with_betas(-40000.0, 0.0)["within_cap"] is True, "|beta| = 0.20 exactly is within the cap"
    assert with_betas(40001.0, 0.0)["within_cap"] is False and with_betas(0.0, -41000.0)["within_cap"] is False and with_betas(nan, 0.0)["within_cap"] is False and with_betas(0.0, nan)["within_cap"] is False, "either beta over 0.20, or one that cannot be computed: no credit"
    # the break-even borrow fee: net is linear in the flat rate; the line through (0, net0) and (rate, net_hi)
    assert abs(breakeven_fee(1000.0, 400.0, 0.03) - 0.05) < 1e-12 and abs(breakeven_fee(300.0, -300.0, 0.03) - 0.015) < 1e-12 and breakeven_fee(0.0, -50.0, 0.03) == 0.0 and breakeven_fee(-10.0, -60.0, 0.03) == 0.0
    assert math.isnan(breakeven_fee(100.0, 100.0, 0.03)) and math.isnan(breakeven_fee(100.0, 120.0, 0.03)) and math.isnan(breakeven_fee(nan, 1.0, 0.03)) and math.isnan(breakeven_fee(1.0, nan, 0.03))
    # A2's window: the cell's first two years of the stretch
    assert a2_window(TS("2018-08-01")) == (TS("2018-08-01"), TS("2020-07-31")) and a2_window(TS("2018-09-04")) == (TS("2018-09-04"), TS("2020-09-03")) and a2_window(TS("2019-02-28"))[1] == TS("2021-02-27")
    # dollars a year = net / years; NaN where there are none
    assert per_year(1000.0, 4.0) == 250.0 and not math.isfinite(per_year(1000.0, 0.0)) and not math.isfinite(per_year(1000.0, nan)) and per_year(-30.0, 3.0) == -10.0
    # years_held: the July-June years in which the cell holds a position on at least one day of the stretch
    ix = pd.bdate_range("2018-08-01", "2025-06-27")
    Bq = SimpleNamespace(index=ix, n=len(ix), mask=lambda a, b_: np.asarray((ix >= a) & (ix <= b_)))
    cnt = np.zeros(len(ix))
    cnt[(ix >= "2018-09-03") & (ix <= "2018-09-28")] = 5
    cnt[(ix >= "2020-07-01") & (ix <= "2020-07-31")] = 5
    assert years_held(Bq, cnt, TS("2018-08-01"), TS("2025-06-29")) == [2018, 2020], "September 2018 is the 2018-19 year, July 2020 the 2020-21 year"
    assert years_held(Bq, np.zeros(len(ix)), TS("2018-08-01"), TS("2025-06-29")) == []


def t_reference():
    """[X1] on the SHORTER stretch: L = #463 + 0.264 x RES and every book number of this family are computed on [stretch start, 2025-06-29] (restretch / make_ctx: the same series, r12_mdl's Stretch with the episodes of the stretch, r11_risk's statistics); A2 is L + c x the cell against L on that stretch with c by the registered
    volatility rule on the cell's first two years of it (25% of #463's daily std / the cell's), 0.5c and 2c reported, the plain #463 + c x cell a reported row, the dollars a year (net / the STRETCH's years) beside every ROC, an incremental pass needs ROC and Sortino both strictly above L's on the stretch"""
    B, S12 = M17.synth_book(seed=3, hi="2026-06-30")
    ref = DV.mk_ref(B)
    g0 = (DV.A2_WIN, DV.A2_TARGET, DV.A2_REPORT, DV.ref_at, D15.WF0, D15.PRE_END)
    for lo in (TS("2018-08-01"), TS("2019-03-01")):
        hi = PRE_END
        k = np.flatnonzero(B.mask(lo, hi))
        ctx = make_ctx(B, S12, ref, lo)
        assert ctx.lo == lo and ctx.hi == PRE_END and ctx.n_years == 7 and ctx.years == YEARS and ctx.ref_full is ref and ctx.ref is not ref
        rs = ctx.ref
        want = R11.stats(np.asarray(ref.raw, float)[k], B.index[k])
        assert all(abs(rs.stats[f] - want[f]) <= 1e-9 * max(1.0, abs(want[f])) for f in ("roc", "sort", "net", "max_dd", "years")) and rs.rows.tolist() == k.tolist() and rs.lo == lo and rs.hi == hi, "L's numbers on the stretch"
        assert rs.facts == ref.facts and ref.stats is not rs.stats and rs.structure == DV.ref_structure(M12.Stretch(ref.raw, B.index, None, lo, hi)) and rs.S.n_dd_days == rs.structure["days"], "the registered full-WF facts stay; the structure is the stretch's"
        rng = np.random.default_rng(8)
        w0, w1 = a2_window(lo)
        mw = B.mask(w0, w1)
        assert int(mw.sum()) > 400 and B.index[mw][0] >= w0 and B.index[mw][-1] <= w1
        for lab, xB in (("profitable and quiet", 40.0 + rng.normal(0.0, 50.0, B.n)), ("losing", -30.0 + rng.normal(0.0, 300.0, B.n)), ("noise", rng.normal(5.0, 300.0, B.n))):
            a2 = a2_report(B, xB, rs, lo, hi)
            sb, sc = float(np.std(B.raw[mw], ddof=1)), float(np.std(xB[mw], ddof=1))
            c_ = 0.25 * sb / sc
            assert a2["window"] == [f"{w0:%Y-%m-%d}", f"{w1:%Y-%m-%d}"] and a2["rows"] == int(mw.sum()) and a2["target"] == 0.25 and abs(a2["c"] - c_) <= 1e-9 * c_ and abs(a2["std_book"] - sb) <= 1e-9 * sb and abs(a2["std_cell"] - sc) <= 1e-9 * sc, (lab, a2["window"], a2["c"], c_)
            assert a2["at_half_c"]["c"] == 0.5 * a2["c"] and a2["at_double_c"]["c"] == 2.0 * a2["c"] and a2["book_shadow_line"] is a2["incremental_pass"]
            yrs = float(rs.stats["years"])
            ref_s = DV.plain_stats(np.asarray(ref.raw, float)[k], B.index[k])
            assert abs(a2["reference"]["roc"] - ref_s["roc"]) < 1e-5 and abs(a2["reference"]["usd_year"] - ref_s["net"] / yrs) < 1e-6 and a2["reference"]["weight_of_RES"] == 0.264, "L's row is L on the STRETCH, in dollars a year of the stretch's years"
            for got, mult in ((a2, 1.0), (a2["at_half_c"], 0.5), (a2["at_double_c"], 2.0)):
                w_ = DV.plain_stats((np.asarray(ref.raw, float) + mult * c_ * xB)[k], B.index[k])
                assert abs(got["roc"] - w_["roc"]) < 1e-5 and abs(got["sortino"] - w_["sortino"]) < 1e-7 and abs(got["net"] - w_["net"]) < 1e-3 and abs(got["usd_year"] - w_["net"] / yrs) < 1e-6, (lab, mult)
            wp_ = DV.plain_stats((np.asarray(B.raw, float) + c_ * xB)[k], B.index[k])
            assert abs(a2["plain_463"]["roc"] - wp_["roc"]) < 1e-5 and abs(a2["plain_463"]["usd_year"] - wp_["net"] / yrs) < 1e-6, "the plain #463 + c x cell book is a reported row with its dollars a year"
            assert a2["incremental_pass"] is bool(a2["roc"] > a2["reference"]["roc"] and a2["sortino"] > a2["reference"]["sortino"]), lab
            if lab == "profitable and quiet":
                assert a2["incremental_pass"] is True and a2["roc_gain"] > 0 and a2["sortino_gain"] > 0
            if lab == "losing":
                assert a2["incremental_pass"] is False and a2["roc_gain"] < 0
            pa = plain_a2(B, xB, lo, hi)
            assert pa["c"] == a2["c"] and pa["window"] == a2["window"], "Stage B recomputes the frozen c on the cell's window of the stretch"
        ax = a2_report(B, np.zeros(B.n), rs, lo, hi)
        assert ax["incremental_pass"] is False and "error" in ax and ax["at_half_c"] is None, "a cell with no spread over the window has no c: no incremental pass, never an exception"
    assert a2_window(TS("2018-08-01")) != a2_window(TS("2019-03-01")), "the window moves with the stretch's start"
    assert (DV.A2_WIN, DV.A2_TARGET, DV.A2_REPORT, DV.ref_at, D15.WF0, D15.PRE_END) == g0, "the module globals the calls patch are put back"


def t_integration():
    """evaluate / reports / candidate rows on the toy world, a synthetic #463 and a synthetic reference (no files), the stretch moved onto the toy's own days (it starts at the first rank at or above 90% coverage): the power line is announced BEFORE any cell's P&L, every statistic is the independent
    sum of the recount's paths, the cost curve and the sides add up, the BORROW CURVE is exactly linear in the flat rate and the flat 3% row equals the recount, the break-even fee, A2 over the reference on the stretch with the cell's own window, the beta rule / the #70 gate / the hedged twin are on the cell,
    the revised-rows twin and the look-ahead reading, the squeeze list and the month in full, the Q21 overlap read from a file (cut at the lockbox), every print block carries its heading, everything is JSON-serialisable"""
    root = tmp()
    wf = (TS("2024-01-02"), TS("2026-06-30"))
    try:
        B, _s = M17.synth_book(seed=15, lo="2024-01-01", hi="2026-06-30", deep=False)
        with spec(n_side=3, min_scored=8, min_side=2), D15.spec(univ=20), patched(THIS, WF0=wf[0], PRE_END=wf[1], YEARS=(2024, 2025)), patched(D15, WF0=wf[0], PRE_END=wf[1]), patched(DV, WF0=wf[0], PRE_END=wf[1]):
            S12 = M12.Stretch(B.raw, B.index, None, wf[0], wf[1])
            ref = DV.mk_ref(B)
            toy = si_toy()
            W = toy.W
            toy_ready_si(toy, root)
            truth = truth_of(toy)
            rows = A13.book_rows(B, W)
            ranks = built_ranks(W, wf[0], wf[1])
            r_start, lo = wf_start(W, ranks)
            assert lo == W.days[r_start + 1] and W.days[r_start] == TS("2024-12-31")
            ctx = make_ctx(B, S12, ref, lo, wf[1])
            assert ctx.lo == lo and ctx.hi == wf[1] and ctx.n_years == 2 and ctx.ref.lo == lo
            spy, real_judge, order, real_run = [], judge_cell, [], M17.run_cell

            def judge_spy(st, net10, net3, nul, n_years):
                spy.append((st, net10, net3, nul, n_years))
                return real_judge(st, net10, net3, nul, n_years)

            def run_spy(*a, **k):
                order.append("run")
                return real_run(*a, **k)
            with patched(THIS, judge_cell=judge_spy), patched(M17, run_cell=run_spy):
                res, obj = evaluate(W, B, rows, ctx, "remove", 40, 0, full=True, announce=lambda nul, L_: order.append("announce"))
            assert order[0] == "announce" and order.count("announce") == 1 and "run" in order[1:] and order.count("run") >= 4, "the null is drawn and announced before the first cell's P&L is computed"
            assert [(a_[0], a_[1], a_[2], a_[4]) for a_ in spy] == [(res["cells"][c]["base"], res["cells"][c]["stress"]["10 bps"]["net"], res["cells"][c]["borrow_flat"]["net"], 2) for c in CELLS] and all(a_[3] is res["null"] for a_ in spy), "judge_cell reads each cell's own base, 10 bps net, flat-borrow net and the registered null"
            resK, objK = evaluate(W, B, rows, ctx, "naive", 0, 1, full=False)
            resV, objV = evaluate(W, B, rows, ctx, "remove", 0, 2, full=False, rev_mode="asis")
            with div_mode(W, False):
                resD = evaluate(W, B, rows, ctx, "remove", 0, 3, full=False)[0]
            assert resK["null"] is None and resV["null"] is None and resV["revised"] == "asis" and resK["variant"] == "naive" and res["variant"] == "remove" and res["revised"] == "drop" and "checks" not in resK["cells"]["D1"]
            Bz = brute_si(W, truth, wf[0], wf[1], "remove", "drop")
            slot = M17.SPEC["slot"]
            for cell in CELLS:
                c = res["cells"][cell]
                paths = {}
                for tag, kw in (("base", {}), ("10 bps", {"bps": 10.0}), ("flat", {"borrow": (BORROW_FLAT, None)}), ("0.25", {"borrow": (BORROW, None)}), ("0.01", {"borrow": (0.01, None)}), ("0", {"borrow": (0.0, None)}), ("0.05", {"borrow": (0.05, None)})):
                    x0, n_pos = np.zeros(W.T), 0
                    for b in Bz:
                        bc = b["cell"][cell]
                        for sd, js in ((1, bc["long"]), (-1, bc["short"])):
                            for j in js:
                                x0[b["f"]:b["x"] + 1] += slot * np.array(M17.brute_path(W, b["f"], b["x"], j, sd, b["pool"][j][0], bps=kw.get("bps", COST_BPS), borrow=kw.get("borrow", (BORROW, None)))[0])
                                n_pos += 1
                    paths[tag] = x0
                traded = [b for b in Bz if b["cell"][cell]["k"] > 0]
                assert len(traded) == 14 and c["base"]["n_units"] == 14 and c["base"]["n_pos"] == n_pos == 84 and abs(c["base"]["net"] - paths["base"].sum()) < 1e-6 and abs(c["usd_year"] - c["base"]["net"] / c["base"]["years"]) < 1e-9, (cell, c["base"]["net"], paths["base"].sum())
                assert abs(c["stress"]["10 bps"]["net"] - paths["10 bps"].sum()) < 1e-6 and abs(c["borrow_flat"]["net"] - paths["flat"].sum()) < 1e-6 and c["borrow_flat"] is c["borrow_curve"]["0.03"], "the stress rows are the recount's"
                assert set(c["stress"]) == {"10 bps", "20 bps"} and c["cost0"]["net"] > c["base"]["net"] > c["stress"]["10 bps"]["net"] > c["stress"]["20 bps"]["net"], "the cost curve: more cost, less P&L"
                cur = {r_: c["borrow_curve"][f"{r_:g}"]["net"] for r_ in BORROW_CURVE}
                assert list(c["borrow_curve"]) == ["0", "0.0025", "0.01", "0.03", "0.05", "0.1", "0.2"] and abs(cur[0.0025] - c["base"]["net"]) < 1e-6 and abs(cur[0.0] - paths["0"].sum()) < 1e-6 and abs(cur[0.01] - paths["0.01"].sum()) < 1e-6 and abs(cur[0.05] - paths["0.05"].sum()) < 1e-6
                slope = (cur[0.03] - cur[0.0]) / 0.03
                assert all(abs(cur[r_] - (cur[0.0] + slope * r_)) < 1e-6 * max(1.0, abs(cur[0.0])) + 1e-6 for r_ in BORROW_CURVE) and slope < 0, "net is exactly linear in the flat rate and falls with it (every short pays)"
                assert (c["breakeven_fee"] == 0.0) if cur[0.0] <= 0 else abs(c["breakeven_fee"] - (-cur[0.0] / slope)) < 1e-9, (cell, c["breakeven_fee"], cur[0.0], slope)
                assert abs((c["sides"]["long side only"]["net"] + c["sides"]["short side only"]["net"]) - c["base"]["net"]) < 1e-6
                assert set(c["extra"]) == {"borrow 1% on k>1.5 sessions", "borrow 3% on k>1.5 sessions", "longs that stop printing valued at -100%", M17.R2_CELL} and c["extra"]["borrow 3% on k>1.5 sessions"]["net"] <= c["extra"]["borrow 1% on k>1.5 sessions"]["net"] + 1e-9 <= c["base"]["net"] + 1e-9
                assert set(c["sub"]) == {s_[0] for s_ in SUBPERIODS} and sum(v["n_pos"] for v in c["sub"].values()) <= c["base"]["n_pos"] and c["years_held"] == [2024, 2025]
                assert set(c["checks"]) == set(real_judge(c["base"], 1.0, 1.0, res["null"], 2)) and c["PASS"] is False, "the toy world cannot clear the bars (14 rebalances)"
                a2 = c["A2"]
                w0, w1 = a2_window(lo)
                assert a2["window"] == [f"{w0:%Y-%m-%d}", f"{w1:%Y-%m-%d}"] and math.isfinite(a2["c"]) and abs(a2["c"] * a2["std_cell"] - 0.25 * a2["std_book"]) <= 1e-9 * a2["std_book"] and "reference" in a2 and "plain_463" in a2 and "usd_year" in a2["reference"]
                assert a2["credited"] is c["beta"]["within_cap"] and a2["incremental_credit"] is bool(a2["incremental_pass"] and c["beta"]["within_cap"])
                assert abs(a2["reference"]["roc"] - DV.plain_stats(np.asarray(ref.raw, float)[np.flatnonzero(B.mask(lo, wf[1]))], B.index[np.flatnonzero(B.mask(lo, wf[1]))])["roc"]) < 1e-5, "L's row is L on the stretch"
                assert c["seat_ref"]["dd_days"] == ctx.ref.structure["days"] and len(c["episode_pnl"]) == len(ctx.ref.S.qual) and c["gate70"]["DO"] == c["seat_ref"]["DO"] and c["gate70"]["episodes"] == ctx.ref.structure["episodes"] and c["gate70"]["credited"] is c["beta"]["within_cap"]
                assert c["gate70"]["null_do_p95"] == res["null"]["do_ref_max"]["p95"] and c["gate70"]["DO_above_null_p95"] is bool(c["seat_ref"]["DO"] > res["null"]["do_ref_max"]["p95"])
                assert set(c["beta"]) == {"side_notional", "beta_dd_days", "beta_all_days", "cap", "within_cap", "es_beta"} and c["beta"]["side_notional"] == 3 * 4000.0 and isinstance(c["beta"]["within_cap"], bool)
                hd = c["hedged"]
                trd = [r_ for r_ in obj.legs.recs if r_.cell[cell].traded]
                f0 = min(r_.f for r_ in trd)
                assert hd["ratios"] == c["base"]["n_units"] and hd["ratios_nonzero"] == sum(1 for r_ in trd if r_.r >= f0 + 251) and 0 < hd["ratios_nonzero"] < hd["ratios"], "the ES hedge is zero until 252 sessions of the cell's own P&L exist before the rank (the first fill is f0: ranks from f0 + 251 on)"
                assert abs(hd["usd_year"] - hd["base"]["net"] / hd["base"]["years"]) < 1e-6 and set(hd["beta"]) == set(c["beta"]) and hd["base"]["net"] != c["base"]["net"], "the twin has its own numbers and its own realised beta"
                assert c["short_stopped"]["short_positions"] == sum(r.cell[cell].k for r in obj.legs.recs if r.cell[cell].traded) == 42
            assert res["null"]["draws"] == 40 and res["null"]["seed"] == SEED and set(res["null"]["by_cell"]) == set(CELLS) and res["null"]["do_ref_max"]["finite"] == 40
            assert any(abs(res["cells"][c]["base"]["net"] - resD["cells"][c]["base"]["net"]) > 1e-6 for c in CELLS), "the dividends move the P&L in the toy world"
            assert all(resV["cells"][c]["base"]["n_units"] == 14 for c in CELLS) and all(resK["cells"][c]["base"]["n_units"] == 14 for c in CELLS)
            # the reports: the squeeze list, the month in full, the overlap with RES and Q21, the turnover, the hand audit's rows
            rep, cands = reports(W, B, rows, ctx, obj, res["cells"], None, {}, {})
            for key in ("beta_to_es", "beta_sides", "episodes", "ref_episodes", "map_point", "corr_with_legs", "corr_with_res", "pick_overlap_with_res", "top20_gains", "top20_losses", "jan2021", "months", "turnover", "survivorship", "dividend_flows", "q21", "manifest_sha256"):
                assert key in rep, key
            assert list(rep["beta_to_es"]["D1"]) == ["book", "L"] and rep["map_point"]["S1"]["standalone_roc_30k"] == res["cells"]["S1"]["base"]["roc"] and set(rep["beta_sides"]["D1"]) == {"long", "short"}
            for cell in CELLS:
                xs = obj.series[cell][0]
                kw = np.flatnonzero(B.mask(lo, wf[1]))
                assert abs(rep["corr_with_res"][cell] - float(np.corrcoef(xs[kw], ctx.ref.res[kw])[0, 1])) < 1e-12 and len(rep["ref_episodes"][cell]) == len(ctx.ref.S.qual)
                ov = rep["pick_overlap_with_res"][cell]
                assert 0.0 <= ov["long_in_res_long"] <= 1.0 and 0.0 <= ov["short_in_res_short"] <= 1.0 and ov["rebalances"] >= 1
                assert abs(sum(rep["months"][cell].values()) - res["cells"][cell]["base"]["net"]) < 1e-6 and rep["turnover"][cell]["traded_rebalances"] == res["cells"][cell]["base"]["n_units"] and rep["jan2021"][cell] is None
                pn = np.asarray(obj.runs[cell].pos.pnl, float)
                g, l_ = rep["top20_gains"][cell], rep["top20_losses"][cell]
                assert len(g) == 20 and len(l_) == 20 and abs(g[0]["pnl"] - pn.max()) < 1e-6 and abs(l_[0]["pnl"] - pn.min()) < 1e-6 and [x["pnl"] for x in g] == sorted([x["pnl"] for x in g], reverse=True) and [x["pnl"] for x in l_] == sorted([x["pnl"] for x in l_])
                assert {"symbol", "date", "exit", "side", "pnl", "score", "settlement", "source_file", "si", "cache_adv", "d1", "s1", "age_sessions"} <= set(g[0]) and g[0]["source_file"].startswith("shrt") and g[0]["settlement"] < g[0]["date"]
                cd = cands[cell]
                assert len(cd) == min(50, len(pn)) and "raw_move_formation" not in cd[0] and {"symbol", "date", "exit", "side", "pnl", "rank_date", "settlement", "source_file", "si", "prev_si_reported", "split_flag", "revision_flag", "finra_adv", "finra_dtc", "cache_adv", "d1", "s1"} <= set(cd[0]), list(cd[0])
                assert abs(cd[0]["pnl"] - pn.max()) < 1e-6 and cd[0]["rank_date"] < cd[0]["date"] and cd[0]["settlement"] <= cd[0]["rank_date"]
            xb0 = obj.series["D1"][0]
            mf = month_in_full(W, obj.legs, "D1", obj.runs["D1"], B, rows, xb0, TS("2025-03-01"), TS("2025-03-31"))
            assert abs(mf["net"] - sum(v for _d, v in mf["daily"])) < 1e-9 and len(mf["daily"]) == 21 and mf["positions"] and abs(mf["net_long_positions"] + mf["net_short_positions"] - sum(p_["pnl"] for p_ in mf["positions"])) < 1e-6
            assert [p_["pnl"] for p_ in mf["worst"]] == sorted(p_["pnl"] for p_ in mf["positions"])[:10] and all(p_["fill"] <= "2025-03-31" and p_["exit"] >= "2025-03-01" for p_ in mf["positions"])
            gains, losses = name_month_extremes(W, obj.legs, "S1", obj.runs["S1"], 5)
            assert len(gains) == len(losses) == 5 and gains[0]["cell"] == "S1" and gains[0]["pnl"] >= gains[1]["pnl"] and losses[0]["pnl"] <= losses[1]["pnl"]
            # the Q21 overlap: not on file -> reported as not run; a file -> the correlation of the daily P&L (rows dated on / after the cut are dropped at read)
            q0 = q21_overlap(B, xb0, lo, wf[1])
            assert q0["on_file"] is False and "NOT computed" in q0["note"]
            qp = os.path.join(root, "q21.csv")
            pd.DataFrame({"date": [f"{d:%Y-%m-%d}" for d in B.index], "pnl": 2.0 * np.asarray(xb0, float) + 5.0}).to_csv(qp, index=False)
            with patched(THIS, Q21_DAILY=qp):
                q1 = q21_overlap(B, xb0, lo, wf[1])
            m_ = (B.index >= lo) & (B.index < LB0)
            assert q1["on_file"] is True and q1["rows"] == int(m_.sum()) and abs(q1["daily_pnl_correlation"] - 1.0) < 1e-9 and "not computed" in q1["share_of_common_names"]
            with open(qp, "w") as f:
                f.write("a,b\n1,2\n")
            with patched(THIS, Q21_DAILY=qp):
                assert q21_overlap(B, xb0, lo, wf[1])["on_file"] is False
            assert json.loads(json.dumps({"res": res, "rep": rep, "resV": resV, "resK": resK}, default=R11.js)) is not None
            # the prints: every block has its heading and no outcome is printed before the cells'
            ast = {c: {"listed": 5, "audited": 0, "audit_complete": False} for c in CELLS}
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                print_power(res["null"])
                print_book_line(B, ctx, {"roc": 93.81, "sortino": 3.816})
                print_cells(res, ast)
                print_borrow(res)
                print_twins(res, resV)
                print_reports(rep, res["cells"])
                print_diagnostics(res, rep, ctx)
                print_scored("registered", obj.legs.cnt)
                NI.print_counts("registered", obj.legs.cnt)
            txt = buf.getvalue()
            for frag in ("POWER LINE [A6] - printed before any cell's P&L", f"THE STRETCH {lo:%Y-%m-%d} .. 2026-06-30", "L = #463 + 0.264 x RES", "Stage A (a)-(e) FAIL", "hand audit (f) 0/5 of the top-50 listed -> incomplete", "A2 (a report): c x", "realised beta to ES (the cell's daily $ P&L",
                         "#70 gate basis", "BORROW CURVE", "break-even", "TWINS - REPORTED", "ES-hedged twin", "[A11] revised-rows twin", "DIAGNOSTICS", "COST CURVE", "BY JULY-JUNE YEAR", "THE TWO REGIME HALVES", "L'S DRAWDOWN EPISODES on the stretch", "THE LONG AND SHORT SIDES APART", "the episodes the cell helps",
                         "credited by the beta rule", "[A4] each SIDE's realised beta", "against RES: daily P&L correlation", "against FRONTIER's Q21 stock BAB seat [A4]", "dividends [R1]", "short leg [R2]", "survivorship:", "the SQUEEZE LIST", "persistence:", "scored names by fill year", "pool names with no score by the first reason"):
                assert frag in txt, frag
            assert txt.index("POWER LINE") < txt.index("Stage A (a)-(e)"), "the power line comes first"
            assert stage_a_flow(res["cells"]) == ([], None)
    finally:
        shutil.rmtree(root, ignore_errors=True)


def t_stage_b_refusals():
    """every Stage B refusal that needs no data, none of which may write the read flag: the lead's go-flag FIRST (nothing computed), then no Stage A candidate (each broken piece), the flag already there, a changed spec / harness / audit, a broken frozen size, and the lockbox year's FINRA files not pinned
    (LB_FINRA is None: the pinned pull stops at the settlement of 2025-05-30 and shrt20250613.csv is quarantined, so Stage B cannot read one row of the sealed year until a dated addendum pins a second extract) and, for S1, its share facts; with everything in order the next thing Stage B does is
    load the book - the flag is still not written"""
    root = tmp()
    try:
        out = os.path.join(root, "out")
        os.makedirs(out)
        go, flag, sap, aud = os.path.join(out, GO_FLAG), os.path.join(out, READ_FLAG), os.path.join(out, "shortint_stageA.json"), os.path.join(out, "shortint_audit.csv")
        good = {"judged": True, "prereg_sha256_lf": PREREG_SHA, **stamp(), "audit_sha256": None, "candidate": {"cell": "S1", "c": 0.8317}, "stageA": {"cells": {"S1": {"PASS": True}}, "pass_cells": ["S1"]}, "parity": {}, "stretch": {"lo": "2018-08-01", "hi": "2025-06-29"}}

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
                       ("cell not a pass cell", mut(lambda d: d["stageA"].update(pass_cells=["D1"]))), ("no pass cells", mut(lambda d: d["stageA"].update(pass_cells=[]))), ("no stageA", mut(lambda d: d.update(stageA=None)))):
            must("no Stage A candidate", sa)
        open(flag, "w").write("x")
        must("already read", good)
        os.remove(flag)
        must("DIFFERS", good, PREREG_SHA="0" * 64)
        must("another pre-registration", mut(lambda d: d.update(prereg_sha256_lf="0" * 64)))
        for nm, edit in (("harness", lambda d: d.update(harness_sha256="0" * 64)), ("r17", lambda d: d.update(r17_sha256="0" * 64)), ("r18", lambda d: d.update(r18_sha256="0" * 64)), ("r21", lambda d: d.update(r21_sha256="0" * 64)), ("early close", lambda d: d.update(early_close=d["early_close"][1:])),
                         ("r15", lambda d: d.update(r15_sha256="0" * 64)), ("r13", lambda d: d.pop("r13_sha256")), ("the facts file", lambda d: d.update(facts_sha256="0" * 64)), ("the map", lambda d: d.update(map_sha256="0" * 64)), ("the wide calendar", lambda d: d.update(wide_ca_sha256="0" * 64)),
                         ("the FINRA flat file", lambda d: d.update(finra_flat_sha256="0" * 64)), ("the FINRA manifest", lambda d: d.update(finra_manifest_sha256="0" * 64)), ("the FINRA schedule", lambda d: d.update(finra_schedule_sha256="0" * 64)),
                         ("the FINRA provenance", lambda d: d.update(finra_provenance_sha256="0" * 64)), ("the FINRA probe", lambda d: d.update(finra_probe_sha256="0" * 64)), ("the asset list", lambda d: d.update(assets_sha256="0" * 64)),
                         ("no stamp", lambda d: [d.pop(k) for k in stamp()])):
            must("different harness version", mut(edit))
        must("not the file Stage A ran with", mut(lambda d: d.update(audit_sha256="0" * 64)))
        with open(aud, "w") as f:
            f.write("symbol,date,cell,verdict,note\n")
        sha = file_sha(aud)
        for badc in (0.0, -1.0, None, "abc", float("nan"), float("inf")):                      # c is a volatility ratio: any positive number is a frozen size; NaN / 0 / negative / missing / text is a broken file
            must("positive number", mut(lambda d, b=badc: d.update(audit_sha256=sha, candidate={"cell": "S1", "c": b})))
        must("not one of", mut(lambda d: d.update(audit_sha256=sha, candidate={"cell": "N99", "c": 0.8317}, stageA={"cells": {"N99": {"PASS": True}}, "pass_cells": ["N99"]})))
        ok = mut(lambda d: d.update(audit_sha256=sha))
        must("the lockbox year's FINRA files are not pinned", ok)                               # everything else is in order: the sealed year's FINRA files are the one thing missing
        must("the lockbox year's FINRA files are not pinned", ok, LB_FINRA={"flat": ("a", "b")})
        must("the lockbox year's FINRA files are not pinned", ok, LB_FINRA={k: ("a", "b") for k in FINRA_KEYS[:-1]})
        full = {k: ("a", "b") for k in FINRA_KEYS}
        must("the S1 candidate needs the lockbox year's share facts", ok, LB_FINRA=full)       # S1 also needs NETISS's second extract
        with patched(NI, LB_FACTS={"facts": ("a", "b")}):
            must("the S1 candidate needs the lockbox year's share facts", ok, LB_FINRA=full)
        assert LB_FINRA is None and NI.LB_FACTS is None and not os.path.exists(flag), "no refusal wrote the flag, and nothing pinned a second extract"
        # a D1 candidate with the lockbox year's files pinned (here: fake paths) goes on to load the book - a sentinel stands in for it: every refusal above was before it, the flag is still not written
        d1 = mut(lambda d: d.update(audit_sha256=sha, candidate={"cell": "D1", "c": 0.8317}, stageA={"cells": {"D1": {"PASS": True}}, "pass_cells": ["D1"]}))
        with open(sap, "w") as f:
            json.dump(d1, f)

        class Sentinel(Exception):
            pass

        def boom():
            raise Sentinel("the book is the next thing Stage B loads")
        try:
            with contextlib.redirect_stdout(io.StringIO()), patched(THIS, OUT=out, LB_FINRA=full), patched(A13, load_463=boom):
                stage_b()
            raise AssertionError("the sentinel must be reached")
        except Sentinel:
            pass
        assert not os.path.exists(flag), "the book is loaded before the flag, and so is everything else: a failure there cannot burn the lockbox"
    finally:
        shutil.rmtree(root, ignore_errors=True)


def t_cut():
    """Stage A asks for data cut at 2025-06-30 and refuses a session on / after it (the loaders and the book are stubbed; nothing real is read); a changed pre-registration, an unreadable FINRA file, the manifest, the book and the reference gates all refuse before any data is asked for; the World's cut;
    every table the score reads - the FINRA flat file's settlement dates, the schedule's rows, the wide calendar's name changes - holds nothing on / after the cut at read time (an earlier cut drops them); Stage A is frozen once the lockbox was read"""
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
    ok_src = lambda cut: SimpleNamespace()
    root = tmp()
    out = os.path.join(root, "out")
    os.makedirs(out)

    def bad_ref(B, check_facts=None):
        refuse("refused: the RESMOM line file x is not the registered y (nothing computed, lockbox NOT read)")

    def must(frag, **kw):
        seen.clear()
        with devnull(), patched(THIS, **kw):
            refused(stage_a, frag)
        assert not os.path.exists(os.path.join(out, "shortint_stageA.json")) and not os.path.exists(os.path.join(out, READ_FLAG)), "a refusal writes nothing"
        return dict(seen)
    try:
        with patched(S, Data=stub), patched(A13, load_463=lambda: (Bs, [])), patched(M17, wide_load=no_wide), patched(DV, ref_load=lambda B, check_facts=None: ref0), patched(THIS, book_checks=lambda B: okbk, manifest_sha=lambda: D15.MANIFEST_PREFIX + "0" * 56, OUT=out, load_sources=ok_src):
            assert "t" not in must("DIFFERS", PREREG_SHA="0" * 64), "a changed pre-registration refuses before any data is asked for"
            assert "t" not in must("FINRA short-interest flat file", load_sources=lambda cut: refuse("refused: the pinned FINRA short-interest flat file (finra_shortint_flat.csv) x is not on file (nothing computed, lockbox NOT read)")), "an unreadable FINRA file refuses before any data is asked for"
            assert "t" not in must("is not the registered", load_sources=lambda cut: refuse("refused: finra_shortint_flat.csv (sha256 x) is not the registered FINRA short-interest flat file (y) - the file changed after it was registered (nothing computed, lockbox NOT read)"))
            with patched(M17, wide_load=lambda *a, **k: refuse("refused: x is not the registered wide calendar (nothing computed, lockbox NOT read)")):
                assert "t" not in must("is not the registered wide calendar")
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
    # the sealed year in the FINRA pull: every table the score reads is cut at READ time - an earlier cut refuses the flat file (it holds later settlements) and drops the schedule's later rows
    root = tmp()
    try:
        pull, rows = sample_pull(root)
        with pulled(pull):
            refused(lambda: load_finra(TS("2024-01-31")), "settled on / after the cut", "sealed year")
            sched, si_ = read_schedule(TS("2024-02-01"))
            assert si_["rows_on_file"] == 5 and si_["rows_read"] == 1 and si_["rows_dropped_at_the_cut"] == 4 and list(sched) == [int(day_i(TS("2024-01-12")))], si_
            sched, si_ = read_schedule(S.LB0)
            assert si_["rows_read"] == 3 and si_["rows_dropped_at_the_cut"] == 2 and max(sched) < int(day_i(S.LB0)) and max(sched.values()) < int(day_i(S.LB0)), "no settlement and no release date on / after the cut"
            fin, fi = load_finra(S.LB0)
            assert fin.ks.max() < int(day_i(S.LB0)) and fin.release.max() < int(day_i(S.LB0)) and fi["last"] < "2025-06-30"
    finally:
        shutil.rmtree(root, ignore_errors=True)
    # book_checks on a synthetic book that does not match the registered structure: ok False, with the numbers
    B, _ = M17.synth_book(seed=2, hi="2025-06-27", deep=False)
    bk, dd, S12b = D15.book_checks(B)
    assert bk["ok"] is False and dd["ok"] is False and dd["days"] == S12b.n_dd_days and dd["episodes"] == len(S12b.qual)


# ------------------------------------------------------------------ smoke: offline end to end on SYNTHETIC worlds (NETISS's synthetic market + a fake FINRA pull whose short interest carries a planted effect)
SMOKE_THETA = 0.06                                     # the planted effect: a daily drift of -theta x q / 252 in the PLANTED world only (q = the name's short-interest tilt of that calendar year); the NULL world has the same short interest and no drift
SMOKE_SPEC = dict(NI.SMOKE_SPEC)                       # the synthetic market has ~65 scored names a month, not the 150 .. 500 of the real one: 15 a side (the top / bottom third below 45 scored names, at least 10 a side)
SMOKE_NAMES = NI.SMOKE_NAMES
SI_MULT = {"SPL": [("2024-03-15", 2.0)], "RVS": [("2016-02-17", 0.2)], "S20": [("2023-03-15", 3.0)], "S18": [("2024-04-22", 0.25)], "S12": [("2021-03-15", 2.0)]}      # the raw share count's splits (NETISS's smoke_filings): the short interest is a count of RAW shares
SMOKE_CASES = {"rename": ("S09", "OLD09", "2019-03-04"),                     # FINRA lists S09's data under OLD09 until the name change (a row of the wide calendar)
               "shared": ("S10", "S11", "2020-01-02"),                       # S10 held the ticker S11 until then - and S11 is another cache name: no score for either on those dates
               "no_row": "D20", "dup": ("D21", (2022, 2023)), "revised": ("S14", (2021,)), "blank": ("S15", (2020,)), "negative": ("S16", (2022,)), "zero": ("S17", (2019, 2020)), "x5000": ("S19", (2023,)), "fund_name": "D22", "fund_title": "D23"}
SMOKE_FIRST = "2018-06-15"                                                    # the first settlement (the real archive's first)


def smoke_refusal(root):
    """NETISS's guards (the dir is wiped: a 'smoke' name, never OUT / CACHE / the repo / this harness / the working directory / C:\\EdgeLog, the other families' OUTs, the #463 records) + this harness's OUT"""
    why = NI.smoke_refusal(root)
    if why:
        return why
    real = lambda p: os.path.normcase(os.path.realpath(p))
    for q in (OUT_DEFAULT, OUT):
        try:
            if os.path.commonpath([real(root), real(q)]) == real(root):
                return f"smoke refused: {root} is or holds SHORTINT OUT"
        except ValueError:
            pass
    return None


def smoke_q(seed=77):
    """the planted short-interest tilt of every name and calendar year: a persistent level (sd 1) and a yearly wobble (sd 0.5). The name's short interest at every settlement of the year is 4% of its shares x exp(0.9 q) (x exp(0.2 e), a settlement's noise); the PLANTED world drifts it by -theta x q / 252 a session"""
    rng = np.random.default_rng(seed)
    N = len(SMOKE_NAMES)
    base = rng.normal(0.0, 1.0, N)
    return SimpleNamespace(base=base, y={k: {yr: float(base[k] + rng.normal(0.0, 0.5)) for yr in range(2014, 2027)} for k in range(N)})


def si_drift(days, sh, theta):
    """the planted drift of every name-session, (D, N): -theta x q (of that calendar year) / 252 - installed in NETISS's smoke_env in place of its issuance drift (same signature)"""
    q = smoke_q()
    return np.array([[-theta * q.y[k][int(yr)] / 252.0 for k in range(len(SMOKE_NAMES))] for yr in days.year])


NI_SMOKE_FILINGS = NI.smoke_filings                      # NETISS's synthetic filings (the callers below wrap them)


def si_filings(sh, seed=53):
    """NETISS's synthetic filings with ONE change: S20's filings of 2023-03-15 .. 2023-05-05 are filed on 2023-05-12 instead (their as-of dates stand). S20's 3-for-1 on 2023-03-15 shows in the price factor F and not in the calendar; with its first-quarter filing late, its latest share count at the
    settlements of 2023-03-31 and 2023-04-28 predates the split - so [A3]'s F side (a split F shows and the calendar does not, between the count's date and s*) fires in the synthetic market - installed through patched(NI, smoke_filings=si_filings) -> rows as NETISS's"""
    cik = NI.smoke_cik("S20")
    out = []
    for r in NI_SMOKE_FILINGS(sh, seed):
        if r[0] == cik and "2023-03-15" <= r[4] <= "2023-05-05":
            r = (r[0], r[1], r[2], r[3], "2023-05-12") + tuple(r[5:])
        out.append(r)
    return out


def smoke_finra_rows(env, settle):
    """the FINRA rows of the synthetic market at every settlement in `settle` (Timestamps): per cache name its short interest (raw shares: 4% of the raw share count x exp(0.9 q + 0.2 e)), FINRA's own ADV and days to cover, a market code by name; the planted cases of SMOKE_CASES (a rename, a ticker two names held,
    a name with no row, one listed twice, revised / blank / negative / zero / x5000 rows by year, a fund by FINRA's issue name), three OTC rows and an ETF in every file -> [row]"""
    fk, q, sh = env.fk["plant"], smoke_q(), env.sh
    e = np.random.default_rng(79).normal(0.0, 1.0, (len(SMOKE_NAMES), len(settle)))
    C = SMOKE_CASES
    rows = []
    for ks, s in enumerate(settle):
        yr = s.year
        for k, nm in enumerate(SMOKE_NAMES):
            if nm == C["no_row"]:
                continue
            sym = C["rename"][1] if (nm == C["rename"][0] and s < TS(C["rename"][2])) else nm
            if nm == C["shared"][0] and s < TS(C["shared"][2]):
                continue                                                                       # S10's data of those years is under S11's ticker: the row there is the other name's own
            shares = math.exp(NI.log_shares(sh, k, s)) * math.prod(m for d_, m in SI_MULT.get(nm, []) if TS(d_) <= s)
            si = int(round(0.04 * math.exp(0.9 * q.y[k][yr] + 0.2 * e[k, ks]) * shares))
            val = None if (nm == C["blank"][0] and yr in C["blank"][1]) else -5 if (nm == C["negative"][0] and yr in C["negative"][1]) else 0 if (nm == C["zero"][0] and yr in C["zero"][1]) \
                else si * 5000 if (nm == C["x5000"][0] and yr in C["x5000"][1]) else si
            adv = int(fk.vol[k])
            kw = {"rev": "R"} if (nm == C["revised"][0] and yr in C["revised"][1]) else {}
            rows.append(frow(s, sym, val, name=(f"{nm} Dynamic Index Fund" if nm == C["fund_name"] else None), mkt=("NYSE" if k % 2 == 0 else "NNM"), adv=adv, dtc=round((val or 0) / adv, 2), **kw))
            if nm == C["dup"][0] and yr in C["dup"][1]:
                rows.append(frow(s, sym, val, mkt="OTC", adv=adv))
        for z in range(3):
            rows.append(frow(s, f"ZZ{z:02d}", 1000 * (z + 1), mkt="OTC", exch="U"))
        rows.append(frow(s, "SPYX", 5000, name="Fake S&P 500 ETF Trust", mkt="ARCA", exch="P"))
    return rows


def smoke_prepare(env, root):
    """everything the SHORTINT part of the smoke adds to NETISS's synthetic market, written inside the smoke dir: the base FINRA pull (settlements 2018-06-15 .. 2025-05-30; 2025-06-13 is the quarantined file: on record, not in the flat file) and the FULL pull (to 2025-09-30, no quarantine: the second
    extract Stage B would pin), the asset lists of both caches with D23 retitled a fund, and the wide calendars with the two name changes -> namespace (pull, full, settle_all, settle, release, rows, rows_base, titles, assets_sha, wide_sha)"""
    days, C = env.days, SMOKE_CASES
    settle_all = toy_settlements(days, SMOKE_FIRST)
    rel_all = {f"{s:%Y-%m-%d}": f"{s + pd.Timedelta(days=10):%Y-%m-%d}" for k, s in enumerate(settle_all) if k >= 9}
    rel_all[f"{settle_all[20]:%Y-%m-%d}"] = f"{settle_all[20] + pd.Timedelta(days=40):%Y-%m-%d}"            # one release the photographed schedule puts far later than s + 12 sessions
    rows = smoke_finra_rows(env, settle_all)
    in_base = lambda r: TS(r[0]) < LB0 and r[11] != "shrt20250613.csv"
    rows_base = [r for r in rows if in_base(r)]
    rel_base = {d: v for d, v in rel_all.items() if TS(d) < LB0}
    pull = fake_pull(root, rows_base, release=rel_base, name="finra")
    full = fake_pull(root, rows, release=rel_all, quarantine=(), name="finra_full")
    titles = {n: f"{n} Inc" for n in SMOKE_NAMES}
    titles[C["fund_title"]] = f"{C['fund_title']} Municipal Income Trust"
    shas = set()
    for world, cache in env.cache.items():                                                    # the same asset list in both caches, D23 retitled
        p = os.path.join(cache, "siporb", "assets.csv")
        a = pd.read_csv(p, dtype=str, keep_default_na=False)
        a.loc[a["symbol"] == C["fund_title"], "name"] = titles[C["fund_title"]]
        a.to_csv(p, index=False)
        shas.add(M17.sha_raw(p))
    assert len(shas) == 1, "the two caches' asset lists are one file"
    new_sha = None
    for world, (csv_p, man_p) in env.wide_files.items():                                      # the wide calendars of both worlds gain the two name changes (re-registered by sha)
        with open(csv_p, newline="") as f:
            txt = f.read()
        txt = txt.rstrip("\n") + "\n" + "\n".join([f"name_change,,{C['rename'][1]},{C['rename'][0]},,{C['rename'][2]},,,,,,,", f"name_change,,{C['shared'][1]},{C['shared'][0]},,{C['shared'][2]},,,,,,,"]) + "\n"
        with open(csv_p, "w", newline="\n") as f:
            f.write(txt)
        sha = M17.sha_raw(csv_p)
        mj = json.load(open(man_p))
        mj["rows"] = int(mj["rows"]) + 2
        mj["sha256"] = {M17.WIDE_NAME + ".csv": sha}
        with open(man_p, "w") as f:
            json.dump(mj, f)
        assert new_sha in (None, sha), "the two worlds' calendars are one file"
        new_sha = sha
    M17.WIDE_CA_SHA = new_sha                                                                 # smoke_env restores the registered one on exit
    return SimpleNamespace(pull=pull, full=full, settle_all=settle_all, settle=[s for s in settle_all if TS(f"{s:%Y-%m-%d}") < LB0 and f"{s:%Y-%m-%d}" != "2025-06-13"], release=rel_base, release_all=rel_all, rows=rows, rows_base=rows_base,
                           titles=titles, assets_sha=shas.pop(), wide_sha=new_sha)


def smoke_truth(W, src, cal, sm):
    """what the plain-python recounts read of the synthetic market: the settlements, the rows by settlement, the renames (the two the calendar holds), the cache's spans, the asset titles, the release dates, the filings and the map, the calendar - from the generator's own data (the spans from the loader
    r5_siporb's Data gave, which t_tickers tests)"""
    by = defaultdict(list)
    for r in sm.rows_base:
        by[r[0]].append(r)
    C = SMOKE_CASES
    usable = src.mp.df[src.mp.df["usable"]]
    cnt = usable.groupby("cik")["symbol"].nunique()
    return SimpleNamespace(settle=sm.settle, by_settle=by, nc=[(C["rename"][1], C["rename"][0], TS(C["rename"][2])), (C["shared"][1], C["shared"][0], TS(C["shared"][2]))], exist={k: (ts_of(a), ts_of(b)) for k, (a, b) in W.si.th.exist.items()},
                           titles=sm.titles, release=sm.release, frame=NI.load_facts(S.LB0)[0], cik_of=dict(zip(usable["symbol"], usable["cik"])), cal=cal, multi=set(usable.loc[usable["cik"].isin(cnt.index[cnt > 1]), "symbol"]),
                           fund_titles={s: t for s, t in sm.titles.items() if any(tok in t for tok in FUND_TITLE_TOKENS)})


def dryload_text_checks(txt):
    """the dryload's printout is COUNTS: no short interest, ADV, share count, score value, price, return, P&L or statistic (nothing like a dollar amount, ROC, Sortino, a drawdown, a signed three-decimal number), no date on / after the cut but the line that names the cut, the count lines it promises"""
    body = "\n".join(l for l in txt.splitlines() if "BEFORE ANY P&L" not in l)                         # (the score block's own heading says 'before any P&L')
    outcome = re.search(r"[$]\s*-?\d|ROC|Sortino|P&L|net [$]|drawdown|Stage A \(|[+-]\d\.\d{3}\b|spearman|median [0-9.]+ /|5th / median", body)
    assert not outcome, ("the dryload printed an outcome", body[max(outcome.start() - 80, 0):outcome.end() + 80])
    dates = [d for l in txt.splitlines() if "cut to dates <" not in l for d in re.findall(r"\b20\d\d-\d\d-\d\d\b", l)]
    assert dates and all(d < "2025-06-30" for d in dates), [d for d in dates if d >= "2025-06-30"][:5]
    for frag in ("universe size per session by year", "[A7] pinned FINRA files", "flat file:", "files read per year", "photographed schedule [A9]", "[A1] asset list", "name changes read from the wide calendar", "[A1] / [A8] pinned files", "map:", "facts:", "S1's multi-class refusal", "[SYMBOLS] ticker histories",
                 "[A2] FINRA'S MARKET CODES", "[K] / [A3] KNOWN AT", "[A1] FUNDS out of the universe", "[SYMBOLS] the ticker join", "[A2] COVERAGE per rank", "the walk-forward STARTS at the first rank at or above 90%", "BEFORE ANY P&L", "names lost to each rule", "[A5] S1's share counts by age",
                 "[A11] FINRA-revised rows among the universe", "FINRA's split flag 'S' beside D1's split rule", "scored names per rebalance", "registered (a flag inside the hold removes the name)", "look-ahead (names flagged inside the hold stay)", "[A11] revised-rows twin", "TRADED REBALANCES from the walk-forward's start",
                 "TBIS flags:", "ES prints on the", "cache manifest sha256", "prereg check:", "rebalances:", "names with a full window", "the fallback rule", "pool names with no score by the first reason"):
        assert frag in txt, frag


SMOKE_RANK_MONTHS = ("2018-08", "2018-12", "2019-06", "2019-09", "2020-06", "2021-06", "2022-06", "2023-04", "2023-06", "2024-04", "2024-06", "2025-03")      # the ranks whose scores the smoke recounts name by name, every planted case among them


def smoke_world(env, sm, world):
    """the World a stage reads, built through the REAL loaders with the calls stage_a makes (every input cut at 2025-06-30 at read time): (W, src, cal, tbis); the raw dividend / spin-off inputs are placed again by plain python from the csv rows (W.Dr_in / W.Sp_in) for the recounts"""
    env.switch(world)
    with quiet():
        src = load_sources(S.LB0)
        cal, _winfo = M17.wide_load(S.LB0)
        W, _nfull, tbis, _fm, _es = load_world(S.LB0, cal, src)
    csv_path = M17.wide_paths()["csv"]
    W.Dr_in = M17.brute_div_matrix(csv_path, W.days, W.syms, S.LB0)
    W.Sp_in = M17.brute_spin_matrix(csv_path, W.days, W.syms, S.LB0)
    return W, src, cal, tbis


def smoke_plant_checks(W, src, cal, sm):
    """the planted cases through the REAL loaders and the REAL score, rank by rank and across every rank: the cut and the quarantined file, the rename walked back, the ticker two names held, the join's refusals, the short-interest oddities by year, the funds, the splits (the calendar's, the factor's, both),
    S1's static reasons and the dual share class; then the score of EVERY name at 12 ranks against the plain-python recount (both cells) -> (ranks, the recount's truth)"""
    ix = {str(n): j for j, n in enumerate(W.syms)}
    fin, fi = src.fin, src.finfo
    assert W.days.max() < S.LB0 and fin.ks.max() < int(day_i(S.LB0)) and fin.release.max() < int(day_i(S.LB0)) and fi["rows"] == len(sm.rows_base) and fi["files"] == len(sm.settle) == fi["settlements"] and fi["missing_settlement_dates"] == [], fi
    assert "shrt20250613.csv" not in fin.srcs and fi["quarantined_on_record_in_provenance"] == {"shrt20250613.csv": True} and max(sm.settle_all) > LB0 and fi["last"] == "2025-05-30" and fi["first"] == SMOKE_FIRST, "nothing of the sealed year, nothing of the quarantined file"
    ranks = built_ranks(W, WF0, PRE_END)
    by_month = {f"{W.days[r]:%Y-%m}": r for r, _f, _x in ranks}
    assert len(ranks) >= 80, len(ranks)
    sc = lambda m: score_rank(W, by_month[m])
    code = lambda m, c, n: code_of(sc(m), c, ix[n])
    val = lambda m, c, n: float(cell_score(sc(m), c)[0][ix[n]])
    seen = defaultdict(set)
    for m in by_month:
        s_ = sc(m)
        for c in CELLS:
            for n in ix:
                seen[(c, n)].add(code_of(s_, c, ix[n]))
    C = SMOKE_CASES
    assert all(code(m, c, C["no_row"]) in ("no_finra_row", "no_usable_file") for m in by_month for c in CELLS) and seen[("D1", C["no_row"])] == {"no_finra_row", "no_usable_file"}, seen[("D1", C["no_row"])]
    assert str(sc("2018-12").sc.tk[ix["S09"]]) == "OLD09" and sc("2018-12").sc.mcode[ix["S09"]] == M_OK and str(sc("2019-06").sc.tk[ix["S09"]]) == "S09", "S09 was OLD09 until 2019-03-04: the file of 2018-11-30 lists OLD09 and the walk-back joins it"
    assert all(code("2019-09", c, n) == "ticker_shared" for c in CELLS for n in ("S10", "S11")) and sc("2020-06").sc.mcode[ix["S10"]] == M_OK and sc("2020-06").sc.mcode[ix["S11"]] == M_OK, "S10 held S11's ticker until 2020-01-02: neither scores on those dates; after it both do"
    assert code("2022-06", "D1", "D21") == "duplicate_finra_rows" and code("2021-06", "D1", "D21") != "duplicate_finra_rows" and code("2021-06", "D1", "S14") == "revised_row" and code("2022-06", "D1", "S14") != "revised_row", "listed twice in 2022-23; revised in 2021"
    assert code("2020-06", "D1", "S15") == "si_missing_or_negative" and code("2022-06", "D1", "S16") == "si_missing_or_negative" and code("2019-06", "D1", "S17") == "scored" and val("2019-06", "D1", "S17") == 0.0 and sc("2019-06").sc.zero_si[ix["S17"]], "blank / negative short interest: no score; zero: a score of 0"
    assert code("2023-06", "S1", "S19") == "scale_error" and code("2023-06", "D1", "S19") == "scored" and val("2023-06", "D1", "S19") > 100 * val("2023-06", "D1", "S01"), "the x5000 short interest: S1's scale rule only"
    assert all(code(m, c, C["fund_name"]) == "fund_finra_name" for m in by_month if sc(m).k >= 0 for c in CELLS) and all(code(m, c, C["fund_title"]) == "fund_asset_title" for m in by_month for c in CELLS), "funds by FINRA's issue name and by the asset-list title"
    assert all(sc(m).n_title == 1 for m in by_month) and all(sc(m).n_name == 1 for m in by_month if sc(m).k >= 0), "one fund of each kind in the universe at every rank (D22 / D23 are in it every month)"
    assert "split_in_volume_window" in seen[("D1", "SPL")] and "split_in_volume_window" in seen[("D1", "S18")] and "split_calendar_not_in_F" in seen[("S1", "S18")] and "split_F_not_in_calendar" in seen[("S1", "S20")] and "scored" in seen[("S1", "SPL")], \
        (seen[("D1", "SPL")], seen[("D1", "S18")], seen[("S1", "S18")], seen[("S1", "S20")], seen[("S1", "SPL")])
    st = {n: [k for (c, n_), k in seen.items() if c == "S1" and n_ == n][0] for n in ("S02", "S03", "S04", "S05", "S06", "S07", "S08")}
    assert st["S02"] >= {"foreign_filer"} and st["S03"] >= {"not_in_map"} and st["S04"] >= {"map_ambiguous"} and st["S05"] >= {"map_unmapped"} and st["S06"] >= {"map_mismatch"} and st["S07"] >= {"map_non_common"} and st["S08"] >= {"no_facts_for_cik"}, st
    assert seen[("S1", "D04")] >= {"multi_class_cik"} and seen[("S1", "D11")] >= {"multi_class_cik"} and "scored" in seen[("D1", "D04")] and "scored" in seen[("D1", "D11")] and W.si.n_multi_ciks == 1, "the dual share class has no S1 (a firm's count against a class's short interest); D1 scores both"
    ds = {c: [REASONS[q] for q in range(len(REASONS)) if any(REASONS[q] in v for (c_, n), v in seen.items() if c_ == c)] for c in CELLS}
    assert set(ds["D1"]) >= {"scored", "fund_asset_title", "ticker_shared", "no_finra_row", "duplicate_finra_rows", "fund_finra_name", "revised_row", "si_missing_or_negative", "split_in_volume_window", "no_usable_file"}, ds["D1"]
    assert set(ds["S1"]) >= {"scored", "multi_class_cik", "not_in_map", "foreign_filer", "scale_error", "split_calendar_not_in_F", "split_F_not_in_calendar", "no_facts_for_cik", "map_ambiguous"}, ds["S1"]
    truth = smoke_truth(W, src, cal, sm)
    t0 = time.time()
    n_score = 0
    cache = {}
    for m in SMOKE_RANK_MONTHS:
        r = by_month[m]
        for rm in ("drop", "asis"):
            br = brute_rank(W, truth, r, rm, cache)
            s_ = score_rank(W, r, rm)
            assert (s_.k if s_.k >= 0 else None) == br.k and s_.covered is br.covered and s_.n_title == br.n_title and s_.n_name == br.n_name and s_.uni.tolist() == sorted(br.uni), (m, rm)
            for j in sorted(br.c1):
                assert int(s_.d1_code[j]) == br.c1[j] and int(s_.s1_code[j]) == br.c2[j], (m, rm, W.syms[j], REASONS[int(s_.d1_code[j])], REASONS[br.c1[j]], REASONS[int(s_.s1_code[j])], REASONS[br.c2[j]])
                for mine, theirs in ((s_.d1[j], br.d1[j]), (s_.s1[j], br.s1[j])):
                    assert (math.isnan(mine) and math.isnan(theirs)) or abs(mine - theirs) <= 1e-9 * max(1.0, abs(theirs)), (m, rm, W.syms[j], mine, theirs)
                n_score += 2
    print(f"planted cases ok through the real loaders (the cut at read, the quarantined file, the rename walked back, the ticker two names held, no row / twice / revised / blank / negative / zero / x5000, the funds, the splits, S1's static reasons, the dual class); against the plain-python recount: the score of every name "
          f"at {len(SMOKE_RANK_MONTHS)} ranks x 2 readings x 2 cells ({n_score:,} scores, {time.time() - t0:.0f}s)")
    return ranks, truth, by_month


def smoke(*a):
    """python r22_shortint.py smoke DIR [stage_b]: offline, on SYNTHETIC worlds (nothing real is read or written; DIR is wiped and its name must contain 'smoke'). Order: the selftest on the real constants; NETISS's synthetic market (80 names, 10 years, through r5_siporb's own pulls) with a fake FINRA pull whose short interest carries a planted
    effect and the cases of SMOKE_CASES; the planted world through the real loaders against plain-python recounts (every score at 12 ranks, then every pool, pick and daily path over two stretches in both readings); the dryload (counts only); Stage A's refusal paths (every pinned file, the quarantined file, a row of the sealed
    year, a manifest that disagrees); Stage A on the NULL world (must FAIL: the same short interest and random numbers, no effect), on the PLANTED world (the effect must be found: (a)-(e) pass for a cell, (f) awaits the hand audit; the score block prints before any P&L) and on a pull too short to judge (NOT JUDGEABLE
    stops before any return); the hand audit; Stage B's refusal paths; with the argument stage_b also the one read on the synthetic lockbox days"""
    root = os.path.abspath(a[0] if a else os.path.join(tempfile.gettempdir(), "shortint_smoke"))
    with_b = "stage_b" in a[1:]
    why = smoke_refusal(root)
    if why:
        raise SystemExit(why)
    if "noselftest" not in a[1:]:                                                          # (a development switch: the registered run starts with the selftest)
        selftest()                                                                         # the hand-made checks first, on the real constants (before anything below is patched)
    t_start = time.time()
    with contextlib.ExitStack() as stack:
        stack.enter_context(patched(NI, smoke_drift=si_drift, SMOKE_THETA=SMOKE_THETA, smoke_filings=si_filings))     # the planted effect of THIS family's synthetic market is a short-interest one
        env = stack.enter_context(NI.smoke_env(root, nrep=100, build=("plant", "null")))
        stack.enter_context(patched(THIS, OUT=os.path.join(root, "out"), CHECK_BOOK=False, NREP=100))
        stack.enter_context(spec(**SMOKE_SPEC))
        os.makedirs(OUT, exist_ok=True)
        sm = smoke_prepare(env, root)
        stack.enter_context(patched(THIS, FILES={**FILES, **sm.pull.files}, FILE_SHA={**FILE_SHA, **sm.pull.shas, "assets": sm.assets_sha}))
        n_names = len(env.fk["plant"].names)
        print(f"synthetic market: {n_names} names x {len(env.days):,} business days ({env.days[0]:%Y-%m-%d} .. {env.days[-1]:%Y-%m-%d}) through r5_siporb's own pulls ({env.build_seconds:.0f}s); a fake FINRA pull of {len(sm.settle)} settlements ({len(sm.rows_base):,} rows, the quarantined 2025-06-13 on record only) "
              f"whose short interest is 4% of the raw share count x exp(0.9 q + noise) with a planted tilt q per name and year; the PLANTED world drifts every name by -{SMOKE_THETA:g} x q a year, the NULL world does not; the cases of SMOKE_CASES; SPEC shrunk to {SMOKE_SPEC}")
        # ---- 1. the planted world through the REAL loaders: the cut, the planted cases and the score against plain-python recounts
        W, src, cal, tbis = smoke_world(env, sm, "plant")
        ranks, truth, by_month = smoke_plant_checks(W, src, cal, sm)
        t0 = time.time()
        n_paths = 0
        for lo_, hi_ in ((TS("2018-06-01"), TS("2019-06-30")), (TS("2023-06-01"), TS("2024-08-31"))):
            Bz_r, Bz_k = brute_si(W, truth, lo_, hi_, "remove"), brute_si(W, truth, lo_, hi_, "naive")
            Lr, Lk = si_build(W, lo_, hi_, "remove"), si_build(W, lo_, hi_, "naive")
            n_paths += compare_si(W, Lr, Bz_r, f"smoke remove {lo_:%Y-%m}") + compare_si(W, Lk, Bz_k, f"smoke naive {lo_:%Y-%m}")
            series_check_si(W, Lr, Bz_r)
            modes = {c: Counter(r_.cell[c].mode for r_ in Lr.recs) for c in CELLS}
            print(f"  {len(Bz_r)} rebalances ({lo_:%Y-%m-%d} .. {hi_:%Y-%m-%d}) in both readings against the recount ({time.time() - t0:.0f}s so far): every pool, score, mode, pick, count and the daily paths of every scored name; rebalances trading the top {M17.SPEC['n_side']} / the third / nothing / "
                  f"under 90% / no file: " + "; ".join(f"{c} " + " / ".join(str(modes[c].get(m_, 0)) for m_ in MODES) for c in CELLS))
            if lo_.year == 2018:
                assert modes["D1"].get("nofile", 0) >= 1 and modes["D1"].get("top", 0) >= 3, modes
        print(f"  {n_paths:,} pick paths in all")
        # ---- 2. the dryload: COUNTS only, nothing written
        before = sorted(os.listdir(OUT))
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            dryload()
        td = buf.getvalue()
        assert sorted(os.listdir(OUT)) == before, "the dryload writes nothing"
        dryload_text_checks(td)
        fr_ = io.StringIO()
        with contextlib.redirect_stdout(fr_):
            print_score_report(score_report(W, ranks, values=False), values=False)
        assert fr_.getvalue() in td and "scored name-ranks over every rank" not in td and "per fill year (scored names pooled" not in td, "the dryload's score block is the report without a value (no per-year percentiles, no SI = 0 share)"
        Lc = si_build(W, WF0, PRE_END, "remove", "drop", units=False, counts_only=True)
        fc = io.StringIO()
        with contextlib.redirect_stdout(fc):
            print_scored_stats("registered (a flag inside the hold removes the name)", Lc, W)
        assert fc.getvalue() in td, "the dryload's scored-names-per-rebalance lines are the recount's"
        fk_ = io.StringIO()
        with contextlib.redirect_stdout(fk_):
            print_files_block(src.fin, src.finfo, src.assets, src.nc, src.ncinfo)
        assert fk_.getvalue() in td, "the dryload's file lines are the loader's"
        with contextlib.redirect_stdout(io.StringIO()), patched(M17, WIDE_CA_SHA="0" * 64):
            buf2 = io.StringIO()
            with contextlib.redirect_stdout(buf2):
                dryload()
        assert "DIFFERS from the registered one" in buf2.getvalue() or "the wide calendar" in buf2.getvalue(), "the dryload reports an unregistered calendar (and counts on it)"
        dryload_text_checks(buf2.getvalue())
        print("dryload ok on the synthetic world: counts only (no short interest, ADV, share count, score value, return, P&L or statistic), no lockbox date, nothing written, its file / score / scored-names lines equal the full computation's")
        # ---- 3. Stage A's refusal paths, the pulls too thin to judge, the NULL and the PLANTED world, the hand audit, Stage B
        smoke_stage_a_refusals(env, sm, root)
        smoke_not_judgeable(env, sm, root)
        B, _legs = A13.load_463()
        rowsB = A13.book_rows(B, W)
        out, _txt = smoke_stage_a_runs(env, sm, W, B, rowsB)
        smoke_stage_b(env, sm, root, out, B, with_b)
        try:                                                                                   # the commands that never touch data
            main(["bogus"])
        except SystemExit:
            pass
        pm = peak_mb()
        print(f"SMOKE OK ({time.time() - t_start:.0f}s" + (f", peak memory {pm:,.0f} MB" if pm else "") + ") - synthetic numbers mean nothing; every command ran end to end offline"
              + ("" if with_b else " (Stage B's read was not run: `smoke DIR stage_b` runs it on the synthetic lockbox days)"))


# ------------------------------------------------------------------ smoke, parts 3 - 8: Stage A's refusals, the pulls too thin to judge, the NULL and the PLANTED world, the hand audit, Stage B
def smoke_dates(txt):
    """every date a printout names (a line that names the cut itself - 'cut to dates <' - is not one)"""
    return [d for l in txt.splitlines() if "cut to dates <" not in l for d in re.findall(r"\b20\d\d-\d\d-\d\d\b", l)]


def smoke_stage_a_refusals(env, sm, root):
    """Stage A refuses - nothing computed, nothing written, no read flag - on: a changed pre-registration, an unregistered wide calendar, every pinned file (the five FINRA files, the asset list, the four XBRL / map files of NETISS) with another sha or absent, a flat file holding a settlement of the sealed year or a row of the
    quarantined file, a manifest that disagrees with its files (the row count, a release date), a book that does not reproduce #463, a RESMOM line file that is absent / not the registered one"""
    sa_path, rd = os.path.join(OUT, "shortint_stageA.json"), os.path.join(OUT, READ_FLAG)
    env.switch("plant")

    def must(frag, ni=None, **kw):
        with quiet(), patched(THIS, **kw), (patched(NI, **ni) if ni else contextlib.nullcontext()):
            msg = refused(stage_a, frag)
        assert not os.path.exists(sa_path) and not os.path.exists(rd), "a refusal writes no stage file and burns nothing"
        return msg
    must("DIFFERS", PREREG_SHA="0" * 64)
    with patched(M17, WIDE_CA_SHA="0" * 64):
        must("is not the registered wide calendar")
    for key in FINRA_KEYS:
        must("is not the registered", FILE_SHA={**FILE_SHA, key: "0" * 64})
        must("is not on file", FILES={**FILES, key: os.path.join(root, "finra", "absent_" + key)})
    must("is not the registered", FILE_SHA={**FILE_SHA, "assets": "0" * 64})
    for key in NI.FILES:
        must("is not the registered", ni={"FILE_SHA": {**NI.FILE_SHA, key: "0" * 64}})
        must("is not on file", ni={"FILES": {**NI.FILES, key: os.path.join(root, "xbrl", "absent_" + key)}})
    nv = [0]

    def variant(rows=None, **kw):
        nv[0] += 1
        return fake_pull(root, sm.rows_base if rows is None else rows, release=sm.release, name=f"v{nv[0]}", **kw)

    def must_pull(pl, frag, shas=None):
        return must(frag, FILES={**FILES, **pl.files}, FILE_SHA={**FILE_SHA, **(pl.shas if shas is None else shas)})
    must_pull(variant(sm.rows_base + [frow("2025-07-15", "S01", 5)]), "settled on / after the cut")
    must_pull(variant(sm.rows_base + [frow("2025-06-13", "S01", 5)]), "quarantined")
    p_ = variant()
    must_pull(p_, "manifest disagrees with the files it describes", mutate(p_, "manifest", jmut(lambda d: d.update(rows=d["rows"] + 1))))
    p_ = variant()
    must_pull(p_, "the release date of shrt20240315.csv", mutate(p_, "manifest", jmut(lambda d: d["release_by_file"]["shrt20240315.csv"].update(release="2024-03-29"))))
    must("do not reproduce", CHECK_BOOK=True)
    with patched(DV, REF_SHA="0" * 64):
        must("RESMOM line file")
    with patched(DV, REF_CSV=os.path.join(root, "resmom", "absent.csv")):
        must("is not on file - the REFERENCE book")
    print("Stage A refuses (and writes nothing) on: a changed pre-registration, an unregistered wide calendar, every pinned file with another sha or absent (the five FINRA files, the asset list, NETISS's four XBRL / map files), a flat file with a settlement of the sealed year, "
          "one with a row of the quarantined file, a manifest that disagrees with its files (the row count; a release date), a book that does not reproduce #463, a RESMOM line file that is absent / not the registered one")


def smoke_not_judgeable(env, sm, root):
    """[A2] a pull that starts too late (its first settlement 2022-01-14: under 60 covered rebalances) and a pull that covers a tenth of the universe (no rank reaches 90%): Stage A prints everything that is counted, says NOT JUDGEABLE and stops BEFORE any return - no power line, no stretch, no cell; the stage file records it; Stage B has no candidate"""
    sa_path, go = os.path.join(OUT, "shortint_stageA.json"), os.path.join(OUT, GO_FLAG)
    env.switch("plant")
    late = fake_pull(root, [r for r in sm.rows_base if r[0] >= "2022-01-14"], release={d: v for d, v in sm.release.items() if d >= "2022-01-14"}, name="late")
    names = set(SMOKE_NAMES[:8])
    thin = fake_pull(root, [r for r in sm.rows_base if r[1] in names or r[1].startswith("ZZ") or r[1] == "SPYX"], release=sm.release, name="thin")
    res = {}
    for tag, pl in (("late", late), ("thin", thin)):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), patched(THIS, FILES={**FILES, **pl.files}, FILE_SHA={**FILE_SHA, **pl.shas}):
            out = stage_a()
        txt = buf.getvalue()
        assert out["not_judgeable"] is True and out["judged"] is False and out["stageA"] is None and out["candidate"] is None and os.path.exists(sa_path), tag
        assert "is NOT JUDGEABLE [A2]" in txt and "before any return is computed" in txt, tag
        assert not any(frag in txt for frag in ("POWER LINE", "THE STRETCH", "registered reading done", "Stage A (a)-(e)", "SHORTINT Stage A:")) and all(d < "2025-06-30" for d in smoke_dates(txt)), (tag, "nothing past the score block")
        saved = json.load(open(sa_path))
        assert saved["not_judgeable"] is True and saved["stageA"] is None and saved["not_judgeable_reason"] in txt, tag
        res[tag] = (out["start_rank"], out["covered_rebalances"])
        with open(go, "w") as f:
            f.write("smoke: a go-flag")
        refused(stage_b, "no Stage A candidate")
        os.remove(go)
        os.remove(sa_path)
    assert res["late"][0] is not None and 0 < res["late"][1] < SPEC["min_reb"], res
    assert res["thin"][0] is None and res["thin"][1] == 0, res
    print(f"NOT JUDGEABLE [A2], both ways, stops before any return (no power line, no stretch, no cell): a pull that starts 2022-01-14 (first covered rank {res['late'][0]}, {res['late'][1]} covered rebalances, fewer than {SPEC['min_reb']}) and a pull that covers a tenth of the universe (no rank at 90%); "
          "the stage file records it, Stage B finds no candidate")


def smoke_stage_a_runs(env, sm, W, B, rowsB):
    """Stage A on the NULL world (the same short interest and random numbers, no effect: must FAIL) and on the PLANTED world (the effect must be found: (a)-(e) pass for a cell, (f) awaits the hand audit; the score block prints before the power line and the power line before any cell's P&L), every number of the
    planted run recomputed from fresh legs, the stress rows, the cost curve, the flat borrow, A2 over the reference on the stretch, the beta rule, the twins, the reports, the files; the hand audit ('keep' changes no number; a data_event removes the name-month from both cells and both nulls, recounted)
    -> (the planted run's Stage A record, its text)"""
    sa_path = os.path.join(OUT, "shortint_stageA.json")

    def run_stage_a(world):
        env.switch(world)
        b_ = io.StringIO()
        with contextlib.redirect_stdout(b_):
            o_ = stage_a()
        return o_, b_.getvalue()
    # ---- the NULL world
    t0 = time.time()
    out_n, txt_n = run_stage_a("null")
    cells_n, nul_n = out_n["stageA"]["cells"], out_n["stageA"]["null"]
    assert out_n["judged"] is True and out_n["stageA"]["pass_cells"] == [] and out_n["candidate"] is None and out_n["pending_hand_audit"] == [] and nul_n["draws"] == NREP == 100, (out_n["stageA"]["pass_cells"], out_n["candidate"])
    assert "SHORTINT Stage A: FAIL - no cell passes (a)-(e)" in txt_n and "Stage A (a)-(e) pass" not in txt_n and all(d < "2025-06-30" for d in smoke_dates(txt_n)), "the null world fails and prints no lockbox date"
    assert all(not c["PASS"] for c in cells_n.values()), {k: (c["base"]["roc"], [q for q, v in c["checks"].items() if not v]) for k, c in cells_n.items()}
    os.remove(sa_path)
    refused(stage_b, "go-flag")
    assert not os.path.exists(os.path.join(OUT, READ_FLAG))
    print(f"Stage A on the NULL world ({time.time() - t0:.0f}s): FAIL as it must - WF ROC@30k " + ", ".join(f"{c} {cells_n[c]['base']['roc']:.1f} (${cells_n[c]['usd_year']:,.0f} a year)" for c in CELLS) + f"; the null's p95 {nul_n['roc_max']['p95']:.1f}; checks failed: "
          + "; ".join(f"{c} " + ", ".join(q for q, v in cells_n[c]["checks"].items() if not v) for c in CELLS))
    # ---- the PLANTED world
    t0 = time.time()
    out, txt = run_stage_a("plant")
    cells = out["stageA"]["cells"]
    passing, cand = stage_a_flow(cells)
    assert out["judged"] is True and out["not_judgeable"] is False and out["stageA"]["pass_cells"] == passing and len(passing) >= 1 and out["candidate"]["cell"] == cand and out["pending_hand_audit"] == passing, \
        (passing, cand, {c: (cells[c]["base"]["roc"], [k for k, v in cells[c]["checks"].items() if not v]) for c in CELLS})
    assert cand == max(passing, key=lambda c: (cells[c]["base"]["roc"], -CELLS.index(c))) and out["candidate"]["also_passes"] == [c for c in passing if c != cand]
    for c in passing:
        assert f"Stage A (a)-(e) pass, (f) awaits the hand audit - cell {c}" in txt and all(cells[c]["checks"].values()), c
    assert "AWAITS THE HAND AUDIT" in txt and "SHORTINT Stage A: (a)-(e) pass" in txt and "audit complete" not in txt.lower() and all(d < "2025-06-30" for d in smoke_dates(txt)), "the harness never decides (f); no lockbox date"
    assert out["prereg_sha256_lf"] == PREREG_SHA and {k: out.get(k) for k in stamp()} == stamp() and out["manifest_sha256"] == D15.MANIFEST_PREFIX + "0" * 56 and out["stageA"]["null"]["draws"] == NREP
    # the score block prints BEFORE any cell's P&L, in the prereg's order; the power line before the first cell
    order = ("REFERENCE book [X1]", "[A7] pinned FINRA files", "[A2] FINRA'S MARKET CODES", "[K] / [A3] KNOWN AT", "[A1] FUNDS out of the universe", "[SYMBOLS] the ticker join, per rank", "[A2] COVERAGE per rank", "the walk-forward STARTS at the first rank at or above 90%",
             "BEFORE ANY P&L - the short-interest scores", "names lost to each rule, by rank", "[A5] S1's share counts by age", "[A11] FINRA-revised rows among the universe", "FINRA's split flag 'S' beside D1's split rule", "names with no score for a reason about the NAME, LISTED",
             "THE STRETCH", "POWER LINE [A6] - printed before any cell's P&L", "registered reading done")
    seq = [txt.index(s_) for s_ in order]
    i_pl = txt.index("the REGISTERED reading (a hygiene flag inside the hold removes the position")                # the first line that carries a cell's P&L
    i_blk, i_str = txt.index("BEFORE ANY P&L - the short-interest scores"), txt.index("THE STRETCH")
    assert seq == sorted(seq) and seq[-1] < i_pl, ("the score block is out of the prereg's order", seq)
    outcome = re.search(r"[$]\s*-?\d|ROC|Sortino|net [$]|drawdown", txt[i_blk:i_str])
    assert not outcome, ("a P&L figure was printed before the stretch's line", txt[max(i_blk + outcome.start() - 80, 0):i_blk + outcome.end() + 80])
    outcome = re.search(r"net [$]", txt[:txt.index("POWER LINE [A6]")].split("THE STRETCH")[1])
    assert not outcome, "no cell's net before the power line"
    for frag in ("D22 (FINRA issue name", "D23 (asset-list title"):
        assert frag in txt[txt.index("[A1] FUNDS out of the universe"):].split("\n")[0], frag
    a4 = txt[txt.index("names with no score for a reason about the NAME, LISTED"):i_str]
    for frag in ("D20 x", "S10 x", "S11 x", "D21 x", "D22 x", "D23 x", "S02 x", "S03 x", "S04 x", "S05 x", "S06 x", "S07 x", "S08 x", "D04 x", "D11 x", "foreign filer", "symbol not in the CIK map", "CIK with no share fact", "no FINRA row for the ticker", "ticker held by two cache names", "the ticker is listed twice",
                 "fund by FINRA's issue name", "fund by its asset-list title", "the CIK carries two or more symbols"):
        assert frag in a4, ("the list of names", frag)
    ub = out["unscored_by_name"]
    assert "D20" in ub["D1"]["no_finra_row"] and {"S10", "S11"} <= set(ub["D1"]["ticker_shared"]) and "D21" in ub["D1"]["duplicate_finra_rows"] and "D22" in ub["D1"]["fund_finra_name"] and "D23" in ub["D1"]["fund_asset_title"] and {"D04", "D11"} <= set(ub["S1"]["multi_class_cik"]) \
        and set(ub["S1"]["foreign_filer"]) == {"S02"} and set(ub["S1"]["not_in_map"]) == {"S03"} and set(ub["S1"]["no_facts_for_cik"]) == {"S08"}, ub
    assert out["start_rank"] is not None and out["stretch_lo"] >= "2018-08-01" and out["covered_rebalances"] >= SPEC["min_reb"] and len(out["coverage_by_rank"]) == len(out["score_by_rank"]) and out["known_at"] and out["funds_out"], (out["start_rank"], out["covered_rebalances"])
    assert {f_["symbol"] for f_ in out["funds_out"]} == {"D22", "D23"} and out["finra"]["rows"] == len(sm.rows_base) and out["finra"]["quarantined_on_record_in_provenance"] == {"shrt20250613.csv": True}, out["funds_out"]
    fo = pd.read_csv(os.path.join(OUT, "shortint_funds_out.csv"))
    assert set(fo["symbol"]) == {"D22", "D23"} and {"symbol", "by", "title_tokens", "asset_title", "finra_names_with_a_token", "ranks", "first_rank", "last_rank"} <= set(fo.columns), fo
    cov = {c_["rank"]: c_ for c_ in out["coverage_by_rank"]}
    assert cov[out["start_rank"]]["covered"] and all(not c_["covered"] for r_, c_ in cov.items() if r_ < out["start_rank"]), "the stretch starts at the first covered rank"
    # the effect: the planted world's cells beat the random-name null and the null world's do not
    nul_p = out["stageA"]["null"]
    assert all(cells[c]["base"]["roc"] > nul_p["roc_max"]["p95"] for c in passing) and all(cells_n[c]["base"]["roc"] < cells[c]["base"]["roc"] for c in CELLS), (cells_n["D1"]["base"]["roc"], cells["D1"]["base"]["roc"], cells_n["S1"]["base"]["roc"], cells["S1"]["base"]["roc"])
    print(f"Stage A on the PLANTED world ({time.time() - t0:.0f}s): the effect is found - " + ", ".join(f"{c} ROC@30k {cells[c]['base']['roc']:.0f} (${cells[c]['usd_year']:,.0f} a year, {cells[c]['base']['n_pos']:,} positions, {cells[c]['base']['n_units']} rebalances) against the NULL world's {cells_n[c]['base']['roc']:.0f}" for c in CELLS)
          + f"; the null's p95 {nul_p['roc_max']['p95']:.1f}; (a)-(e) pass for {passing}, candidate {cand}, (f) awaits the hand audit; the walk-forward starts at rank {out['start_rank']} ({out['covered_rebalances']} covered rebalances)")
    # every cell's WF numbers recomputed from fresh legs: the stress rows, the cost curve, the flat borrow, the dollars a year, A2 over the reference, the beta rule
    lo = TS(out["stretch_lo"])
    ref_ = DV.ref_load(B, check_facts=False)
    ctx = make_ctx(B, None, ref_, lo)
    Lw = si_build(W, WF0, PRE_END, "remove")
    for cell in CELLS:
        run_ = M17.run_cell(W, cell_leg(Lw, cell), D15.l1_cfg(), pos=True)
        st, xb_, _cb = stat_run(B, rowsB, run_, lo, PRE_END)
        got = cells[cell]["base"]
        assert st["n_pos"] == got["n_pos"] == out["parity"][cell]["n_pos"] and st["n_units"] == got["n_units"] == out["parity"][cell]["n_units"] and abs(st["net"] - got["net"]) < 1e-6 and abs(st["roc"] - got["roc"]) < 1e-9 and abs(st["max_dd"] - got["max_dd"]) < 1e-9, cell
        assert abs(cells[cell]["usd_year"] - got["net"] / got["years"]) < 1e-6 and got["years"] > 6.5, "[A12] dollars a year beside the ROC"
        for b_, got_ in ((0.0, cells[cell]["cost0"]), (10.0, cells[cell]["stress"]["10 bps"]), (20.0, cells[cell]["stress"]["20 bps"])):
            want_ = stat_run(B, rowsB, M17.run_cell(W, cell_leg(Lw, cell), D15.l1_cfg(bps=b_)), lo, PRE_END)[0]
            assert abs(got_["net"] - want_["net"]) < 1e-6 and abs(got_["roc"] - want_["roc"]) < 1e-9, (cell, b_)
        assert cells[cell]["cost0"]["net"] > got["net"] > cells[cell]["stress"]["10 bps"]["net"] > cells[cell]["stress"]["20 bps"]["net"]
        cur = {r_: stat_run(B, rowsB, M17.run_cell(W, cell_leg(Lw, cell), D15.l1_cfg(borrow=(r_, None))), lo, PRE_END)[0]["net"] for r_ in (0.0, BORROW_FLAT)}
        assert abs(cells[cell]["borrow_flat"]["net"] - cur[BORROW_FLAT]) < 1e-6 and abs(cells[cell]["borrow_curve"]["0"]["net"] - cur[0.0]) < 1e-6 and cur[BORROW_FLAT] < cur[0.0], "the flat 3% borrow row and the curve's zero are the recount's, and every short pays"
        assert abs(cells[cell]["breakeven_fee"] - breakeven_fee(cur[0.0], cur[BORROW_FLAT], BORROW_FLAT)) < 1e-12
        a2, w0w1 = cells[cell]["A2"], a2_window(lo)
        mw = B.mask(*w0w1)
        sb_, sc_ = float(np.std(B.raw[mw], ddof=1)), float(np.std(xb_[mw], ddof=1))
        assert a2["window"] == [f"{w0w1[0]:%Y-%m-%d}", f"{w0w1[1]:%Y-%m-%d}"] and a2["rows"] == int(mw.sum()) and abs(a2["c"] - A2_TARGET * sb_ / sc_) <= 1e-9 * a2["c"], (cell, a2["window"], a2["rows"], int(mw.sum()))
        assert a2["incremental_pass"] is bool(a2["roc"] > a2["reference"]["roc"] and a2["sortino"] > a2["reference"]["sortino"]) and a2["incremental_credit"] is bool(a2["incremental_pass"] and cells[cell]["beta"]["within_cap"]) and a2["credited"] is cells[cell]["beta"]["within_cap"], cell
        yrs = float(ctx.ref.stats["years"])
        assert abs(a2["usd_year"] - a2["net"] / yrs) < 1e-6 and abs(a2["reference"]["usd_year"] - a2["reference"]["net"] / yrs) < 1e-6 and abs(a2["at_half_c"]["usd_year"] - a2["at_half_c"]["net"] / yrs) < 1e-6 and abs(a2["at_double_c"]["usd_year"] - a2["at_double_c"]["net"] / yrs) < 1e-6 \
            and abs(a2["plain_463"]["usd_year"] - a2["plain_463"]["net"] / yrs) < 1e-6, "[A12] the dollars a year beside every ROC of A2"
        bt = cells[cell]["beta"]
        assert bt["side_notional"] == M17.SPEC["n_side"] * M17.SPEC["slot"] and bt["cap"] == BETA_CAP and bt["within_cap"] is bool(abs(bt["beta_dd_days"]) <= BETA_CAP and abs(bt["beta_all_days"]) <= BETA_CAP), bt
        g70 = cells[cell]["gate70"]
        assert g70["credited"] is bt["within_cap"] and g70["episodes"] == ctx.ref.structure["episodes"] and len(cells[cell]["episode_pnl"]) == len(ctx.ref.S.qual) and abs(sum(cells[cell]["episode_pnl"]) - sum(e_["cell_pnl"] for e_ in out["reports"]["ref_episodes"][cell])) < 1e-6, "the reference's episode table"
    assert out["reference"]["sha256"] == env.ref_sha == out["reference"]["pinned_sha256"] and out["reference"]["rows"] == ref_.n_rows, "the reference is the registered file"
    ca2 = cells[cand]["A2"]
    assert out["candidate"] == {"cell": cand, "c": ca2["c"], "std_book": ca2["std_book"], "std_cell": ca2["std_cell"], "window": ca2["window"], "a2_book_roc": ca2["roc"], "a2_reference_roc": ca2["reference"]["roc"], "incremental_pass": ca2["incremental_pass"],
                                "incremental_credit": ca2["incremental_credit"], "book_shadow_line": ca2["incremental_credit"], "beta_within_cap": cells[cand]["beta"]["within_cap"], "also_passes": out["candidate"]["also_passes"]} and ca2["c"] > 0, "the frozen size travels with its two stds and the window"
    for key in ("sides", "extra", "sub", "gate70", "seat_ref", "episode_pnl", "hedged", "beta", "years_held", "breakeven_fee", "borrow_curve"):
        assert all(key in cells[c] for c in CELLS), key
    for c in CELLS:
        hg = cells[c]["hedged"]
        assert hg["ratios"] == cells[c]["base"]["n_units"] and 0 < hg["ratios_nonzero"] < hg["ratios"] and abs(hg["usd_year"] - hg["base"]["net"] / hg["base"]["years"]) < 1e-6 and np.isfinite(hg["beta"]["beta_all_days"]), (c, hg["ratios"], hg["ratios_nonzero"])
        assert abs((cells[c]["sides"]["long side only"]["net"] + cells[c]["sides"]["short side only"]["net"]) - cells[c]["base"]["net"]) < 1e-6, "the two sides add up to the cell"
    rp = out["reports"]
    for c in CELLS:
        t_ = rp["turnover"][c]
        assert t_["transitions"] > 50 and 0.0 < t_["persistence_mean"] < 1.0 and rp["pick_overlap_with_res"][c]["rebalances"] > 50, (c, t_)
        assert len(rp["top20_gains"][c]) == 20 and len(rp["top20_losses"][c]) == 20 and np.isfinite(rp["corr_with_res"][c]) and rp["jan2021"][c] is not None and rp["q21"][c]["on_file"] is False, c
        assert abs(sum(rp["months"][c].values()) - cells[c]["base"]["net"]) < 1e-6
    for frag in ("DIAGNOSTICS", "COST CURVE", "BY JULY-JUNE YEAR", "THE TWO REGIME HALVES", "THE LONG AND SHORT SIDES APART", "BORROW CURVE", "break-even", "TWINS - REPORTED", "ES-hedged twin", "[A11] revised-rows twin", "no-dividend version [R1]", "look-ahead reading", "#70 gate basis", "realised beta to ES (the cell's daily $ P&L",
                 "[A4] each SIDE's realised beta", "against RES: daily P&L correlation", "against FRONTIER's Q21 stock BAB seat [A4]", "dividends [R1]", "short leg [R2]", "survivorship:", "the SQUEEZE LIST", "JANUARY 2021 in full", "persistence:", "audit candidates (the 50 largest gains per cell"):
        assert frag in txt, frag
    # the files: the 50 largest contributors per cell with their short-interest facts, and the squeeze lists
    cd = pd.read_csv(os.path.join(OUT, "shortint_audit_candidates.csv"))
    need = {"cell", "symbol", "date", "exit", "side", "pnl", "rank_date", "settlement", "source_file", "ticker", "si", "prev_si_reported", "split_flag", "revision_flag", "finra_adv", "finra_dtc", "cache_adv", "cache_adv_sessions", "d1", "s1", "shares", "shares_asof", "shares_form", "shares_first_filed", "shares_accn", "F_asof", "F_s",
            "si_1_settlement_earlier", "si_2_settlements_earlier", "age_sessions"}
    assert need <= set(cd.columns) and set(cd["cell"]) == set(CELLS) and cd.groupby("cell").size().max() == AUDIT_N and cd["exit"].max() < "2025-06-30" and cd["rank_date"].max() < "2025-06-30" and cd["settlement"].max() < "2025-06-30", list(cd.columns)
    for cell, g in cd.groupby("cell"):
        assert (g["pnl"].diff().dropna() <= 1e-9).all() and (g["settlement"] <= g["rank_date"]).all() and (g["rank_date"] < g["date"]).all() and g["source_file"].str.startswith("shrt").all() and (g["si"] >= 0).all(), "largest gains first; the settlement is known at the rank"
        assert (g["shares"].notna().all() and (g["shares"] > 0).all()) if cell == "S1" else g["shares"].isna().all(), "S1's rows carry the share count behind the score, D1's do not"
    ex = pd.read_csv(os.path.join(OUT, "shortint_name_month_extremes.csv"))
    assert len(ex) == 2 * SQUEEZE_N * len(CELLS) and set(ex["cell"]) == set(CELLS) and ex["exit"].max() < "2025-06-30" and {"settlement", "source_file", "si", "d1", "s1"} <= set(ex.columns), (len(ex), list(ex.columns))
    pm = peak_mb()
    print(f"audit candidates: the {AUDIT_N} largest gains per cell with the settlement, its FINRA file, the short-interest rows, FINRA's ADV / days to cover, our ADV and the share-count facts -> shortint_audit_candidates.csv; the 20 largest name-month gains and losses -> shortint_name_month_extremes.csv" + (f"; peak memory {pm:,.0f} MB" if pm else ""))
    # ---- the hand audit: every listed contributor 'keep' -> the same numbers, the audit counted; a data_event on the candidate's largest gain -> out of both cells and both nulls, recounted by apply_audit on a fresh world
    ap = os.path.join(OUT, "shortint_audit.csv")
    keys = cd[["symbol", "date", "cell"]].drop_duplicates().reset_index(drop=True)
    keys.assign(verdict="keep", note="smoke: nothing found").to_csv(ap, index=False)
    out2, _txt2 = run_stage_a("plant")
    assert out2["audit"]["rows"] == len(keys) and out2["audit"]["keep"] == len(keys) and out2["audit"]["data_event"] == 0 and out2["audit_sha256"] == file_sha(ap) != out["audit_sha256"], out2["audit"]
    assert all(v["audited"] == v["listed"] == AUDIT_N and v["audit_complete"] for v in out2["audit_status"].values()), out2["audit_status"]
    assert out2["stageA"]["pass_cells"] == passing and out2["candidate"] == out["candidate"] and all(out2["stageA"]["cells"][c]["base"][k] == cells[c]["base"][k] for c in CELLS for k in ("n_pos", "net", "roc", "max_dd", "sortino")), "a keep changes no number"
    top = cd[cd["cell"] == cand].iloc[0]
    au = pd.read_csv(ap)
    au.loc[(au["symbol"] == top["symbol"]) & (au["date"] == top["date"]), "verdict"] = "data_event"
    au.to_csv(ap, index=False)
    out3, _txt3 = run_stage_a("plant")
    cd3 = pd.read_csv(os.path.join(OUT, "shortint_audit_candidates.csv"))
    assert out3["audit"]["data_event"] >= 1 and not ((cd3["symbol"] == top["symbol"]) & (cd3["date"] == top["date"])).any() and out3["audit_sha256"] != out2["audit_sha256"], "the name-month is gone from every list"
    n3, n0 = out3["stageA"]["cells"][cand]["base"], cells[cand]["base"]
    assert n3["net"] != n0["net"] and n3["n_pos"] == n0["n_pos"] and out3["parity"][cand]["n_pos"] == n3["n_pos"], "the slot goes to the next name in the order: the same number of positions, another P&L"
    assert out3["stageA"]["null"]["draws"] == NREP and out3["stageA"]["null"]["roc_max"]["p95"] != out2["stageA"]["null"]["roc_max"]["p95"], "the name-month is out of both nulls too"
    au_df = read_audit(ap)
    cnt_au = apply_audit(W, au_df)
    try:
        L3 = si_build(W, WF0, PRE_END, "remove")
        run3 = M17.run_cell(W, cell_leg(L3, cand), D15.l1_cfg(), pos=True)
        st3 = stat_run(B, rowsB, run3, lo, PRE_END)[0]
        assert abs(st3["net"] - n3["net"]) < 1e-6 and st3["n_pos"] == n3["n_pos"] and cnt_au["data_event"] == out3["audit"]["data_event"], "apply_audit on a fresh world is Stage A's removal"
        assert int(W.aud1.sum()) >= 1, "the removal is on the World"
    finally:
        W.aud1[:] = False
        W.aud_hit.clear()
    print(f"hand audit: {len(keys)} rows 'keep' (the {AUDIT_N} largest contributors per cell) -> the same numbers, audit counted {AUDIT_N}/{AUDIT_N}; a data_event on {top['symbol']} {top['date']} ({cand}'s largest gain, ${top['pnl']:,.0f}) -> out of both cells and both nulls "
          f"(the slot goes to the next name: {n3['n_pos']:,} positions either way): {cand} net ${n0['net']:,.0f} -> ${n3['net']:,.0f}, null p95 {out2['stageA']['null']['roc_max']['p95']:.2f} -> {out3['stageA']['null']['roc_max']['p95']:.2f}; apply_audit on a fresh world gives the same net")
    return out3, txt


def smoke_stage_b(env, sm, root, out, B, with_b):
    """Stage B's refusal paths (the lead's go-flag first, then the stage file, the stamps, the audit file, the frozen size, the lockbox year's FINRA extract and, for S1, its share facts, the book, the manifest, the calendar, a bad extract, drifted WF numbers or size c; none may write the read flag); with
    `stage_b` also the one read on the synthetic lockbox days: the flag after the load and the checks, the verdict is the LEG's veto alone (forced both ways), a second read refused, Stage A frozen"""
    sa_path, go, rd, ap = os.path.join(OUT, "shortint_stageA.json"), os.path.join(OUT, GO_FLAG), os.path.join(OUT, READ_FLAG), os.path.join(OUT, "shortint_audit.csv")
    cand, c_frozen = out["candidate"]["cell"], out["candidate"]["c"]
    full_pins = {k: (sm.full.files[k], sm.full.shas[k]) for k in FINRA_KEYS}                                   # the second extract a dated addendum would pin (LB_FINRA)
    print("--- Stage B refusal paths: no go-flag / not pinned lockbox extract / not judged / no candidate / a stale stamp / a changed audit file / a broken size / the S1 share facts not pinned / a drifted calendar, manifest, book, WF numbers or size c / a bad lockbox extract; none may write the flag")
    env.switch("plant")

    def must_b(frag, ni=None, **kw):
        with quiet(), patched(THIS, **kw), (patched(NI, **ni) if ni else contextlib.nullcontext()):
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
    must_b("the lockbox year's FINRA files are not pinned")                                                  # a valid stage file, the lead's flag - and no second extract pinned: the sealed year's short interest cannot be read
    must_b("the lockbox year's FINRA files are not pinned", LB_FINRA={"flat": full_pins["flat"]})
    must_b("the lockbox year's FINRA files are not pinned", LB_FINRA={k: v for k, v in full_pins.items() if k != "probe"})
    jS = json.loads(js0)                                                                                     # an S1 candidate also needs NETISS's second extract of the share facts
    jS["candidate"]["cell"], jS["stageA"]["pass_cells"] = "S1", ["S1"]
    open(sa_path, "w").write(json.dumps(jS))
    must_b("the S1 candidate needs the lockbox year's share facts", LB_FINRA=full_pins)
    must_b("the S1 candidate needs the lockbox year's share facts", LB_FINRA=full_pins, ni={"LB_FACTS": {"facts": env.lb_facts["facts"]}})
    open(sa_path, "w").write(js0)
    must_b("DIFFERS", PREREG_SHA="0" * 64, LB_FINRA=full_pins)
    with patched(M17, WIDE_CA_SHA="0" * 64):
        must_b("different harness version", LB_FINRA=full_pins)                                              # the pinned calendar is in Stage A's stamp: another pinned sha stops it at the stamp
    for key in FILES:
        must_b("different harness version", LB_FINRA=full_pins, FILE_SHA={**FILE_SHA, key: "0" * 64})       # so is every pinned FINRA file, the asset list and each of NETISS's files
    must_b("different harness version", LB_FINRA=full_pins, FILE_SHA={**FILE_SHA, "assets": "0" * 64})
    for key in NI.FILES:
        must_b("different harness version", LB_FINRA=full_pins, ni={"FILE_SHA": {**NI.FILE_SHA, key: "0" * 64}})
    au0 = open(ap).read()
    open(ap, "a").write("ZZZ,2018-09-04,D1,keep,a changed audit file\n")
    must_b("not the file Stage A ran with", LB_FINRA=full_pins)
    open(ap, "w").write(au0)
    must_b("do not reproduce its LB numbers", CHECK_BOOK=True, LB_FINRA=full_pins, ni={"LB_FACTS": env.lb_facts})                  # the book's LB numbers (the synthetic one cannot reproduce them)
    okbk = lambda B_, lo_, hi_, ref: {"roc": 0.0, "sortino": 0.0, "ref": list(ref), "ok": True}
    with patched(A13, book_check=okbk):
        must_b("not the one Stage A ran on", CHECK_BOOK=True, LB_FINRA=full_pins, manifest_sha=lambda: "ffffffff" + "0" * 56, ni={"LB_FACTS": env.lb_facts})
    csv0 = open(env.wide_csv, "rb").read()
    with open(env.wide_csv, "ab") as f_:
        f_.write(b"cash_dividend,S01,,,2024-02-09,2024-02-09,,,0.01,,,,False\n")
    must_b("is not the registered wide calendar", LB_FINRA=full_pins, ni={"LB_FACTS": env.lb_facts})        # the file changed after it was registered: refused before the flag
    open(env.wide_csv, "wb").write(csv0)
    assert M17.sha_raw(env.wide_csv) == M17.WIDE_CA_SHA, "the calendar is back to the registered file"
    bad_lb = {k: (v[0], "0" * 64) for k, v in full_pins.items()}
    must_b("is not the registered", LB_FINRA=bad_lb, ni={"LB_FACTS": env.lb_facts})                         # the lockbox extract is not the file the addendum pinned
    late = fake_pull(root, sm.rows + [frow("2026-07-15", "S01", 5)], release=sm.release_all, quarantine=(), name="lb_late")
    must_b("settled on / after the cut", LB_FINRA={k: (late.files[k], late.shas[k]) for k in FINRA_KEYS}, ni={"LB_FACTS": env.lb_facts})   # a settlement after the lockbox's own end is refused
    j = json.loads(js0)
    j["parity"][cand]["net"] += 1e6
    open(sa_path, "w").write(json.dumps(j))
    must_b("do not reproduce on Stage B's data", LB_FINRA=full_pins, ni={"LB_FACTS": env.lb_facts})        # the WF numbers drifted since Stage A
    j = json.loads(js0)
    j["parity"][cand]["n_pos"] += 1
    open(sa_path, "w").write(json.dumps(j))
    must_b("do not reproduce on Stage B's data", LB_FINRA=full_pins, ni={"LB_FACTS": env.lb_facts})
    j = json.loads(js0)
    j["candidate"]["c"] *= 1.0001
    open(sa_path, "w").write(json.dumps(j))
    must_b("volatility-set size c", LB_FINRA=full_pins, ni={"LB_FACTS": env.lb_facts})                    # the frozen size is recomputed on the cell's own window on Stage B's data: a drift of 1 in 10,000 stops it
    open(sa_path, "w").write(js0)
    print("Stage B refused before the flag in every case above (the flag was never written)")
    if not with_b:
        os.remove(go)
        return
    # ---- the one read (synthetic lockbox days only): the flag after the load and the checks, the verdict is the LEG's veto alone, a second read refused, Stage A frozen
    print("--- Stage B, the one read on the synthetic lockbox days: the flag after the load and the checks, the verdict, a second read refused")
    cap, real_cs = {}, D15.cell_stats

    def tap(Bk, xk, ck, lo_, hi_, run_, *a_, **k_):                                                          # sees the lockbox call of the one read: keeps the cell's daily series, to recompute the book add independently
        st_ = real_cs(Bk, xk, ck, lo_, hi_, run_, *a_, **k_)
        if lo_ == LB0:
            cap["x"] = np.array(xk)
        return st_
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf), patched(D15, cell_stats=tap), patched(THIS, LB_FINRA=full_pins), patched(NI, LB_FACTS=env.lb_facts):
        ok = stage_b()
    txt_b = buf.getvalue()
    print(txt_b.rstrip())
    sb = json.load(open(os.path.join(OUT, "shortint_stageB.json")))
    assert os.path.exists(rd) and sb["pass"] == ok and sb["cell"] == cand and sb["c"] == c_frozen and sb["leg"]["n_pos"] > 0 and {k: sb.get(k) for k in stamp()} == stamp() and sb["prereg_sha256_lf"] == PREREG_SHA
    assert set(sb["checks"]) == {f"leg monthly rebalances>={RULES['b_reb']}", "leg net>0", "leg net>0 without its top name-month"} and ok is all(sb["checks"].values()), "the pass is the LEG's veto: three checks, no book"
    assert sb["es_return_lb"]["stretch"] == ["2025-06-30", "2026-06-30"] and sb["go_flag"].startswith("smoke: the lead's go-flag")
    assert sb["lockbox_finra"] == {k: sm.full.shas[k] for k in FINRA_KEYS} and sb["lockbox_finra_counts"]["rows"] > out["finra"]["rows"] and sb["lockbox_finra_counts"]["last"] > "2025-06-30", "Stage B read the pinned lockbox extract (the second pull)"
    assert all(r_["exit"] >= "2025-06-30" for r_ in sb["top_name_months"]), "the lockbox year's name-months"
    add, mb_ = sb["book_add_reported"], B.mask(LB0, LB1)                                                     # the book add on the lockbox at the FROZEN c: reported, recomputed from the book file and the captured series
    want = R11.stats((B.raw + c_frozen * cap["x"])[mb_], B.index[mb_])
    assert add["c"] == c_frozen and abs(add["roc"] - want["roc"]) < 1e-9 and abs(add["sortino"] - want["sort"]) < 1e-9 and abs(add["net"] - want["net"]) < 1e-6, add
    assert add["reference"] == {"roc": RULES["b_roc"], "sortino": RULES["b_sort"]} and add["would_have_cleared"] is bool(want["roc"] >= RULES["b_roc"] and want["sort"] >= RULES["b_sort"]) and "never a pass" in add["note"]
    assert "book add, REPORTED and never part of the pass" in txt_b and ("PASS - the leg survives" in txt_b) is ok and ("FAIL - the leg is vetoed" in txt_b) is not ok

    def reread(leg_ok, book_ok):                                                                              # the pass is the leg's veto ALONE: the leg forced to pass with the book add's bar forced to miss, then the leg forced to fail with the bar forced to clear
        os.remove(rd)
        os.remove(os.path.join(OUT, "shortint_stageB.json"))

        def forced(Bk, xk, ck, lo_, hi_, run_, *a_, **k_):
            st_ = real_cs(Bk, xk, ck, lo_, hi_, run_, *a_, **k_)
            if lo_ == LB0:
                st_ = {**st_, "n_units": 10 ** 6 if leg_ok else 0, "net": 1e6 if leg_ok else -1e6, "net_ex_top_pos": 1e6 if leg_ok else -1e6}
            return st_
        keep_bar = (RULES["b_roc"], RULES["b_sort"])
        RULES["b_roc"], RULES["b_sort"] = (-1e9, -1e9) if book_ok else (1e9, 1e9)
        b_ = io.StringIO()
        try:
            with contextlib.redirect_stdout(b_), patched(D15, cell_stats=forced), patched(THIS, LB_FINRA=full_pins), patched(NI, LB_FACTS=env.lb_facts):
                ok_ = stage_b()
        finally:
            RULES["b_roc"], RULES["b_sort"] = keep_bar
        return ok_, json.load(open(os.path.join(OUT, "shortint_stageB.json"))), b_.getvalue()
    for leg_ok, book_ok in ((True, False), (False, True)):
        ok2, sb2, t2 = reread(leg_ok, book_ok)
        assert ok2 is leg_ok and sb2["pass"] is leg_ok and all(sb2["checks"].values()) is leg_ok and sb2["book_add_reported"]["would_have_cleared"] is book_ok and os.path.exists(rd), (leg_ok, book_ok, sb2["checks"])
        assert abs(sb2["book_add_reported"]["roc"] - add["roc"]) < 1e-9 and sb2["book_add_reported"]["c"] == c_frozen, "the book add is the same sum whatever the verdict"
        assert ("PASS - the leg survives" in t2) is leg_ok and ("FAIL - the leg is vetoed" in t2) is not leg_ok and ("FORWARD SHADOW" in t2) is leg_ok
        print(f"  leg forced {'to pass' if leg_ok else 'to fail'}, book-add bar forced {'to clear' if book_ok else 'to miss'}: Stage B {'PASS' if ok2 else 'FAIL'}, would_have_cleared {sb2['book_add_reported']['would_have_cleared']} - the verdict is the leg's")
    with patched(THIS, LB_FINRA=full_pins), patched(NI, LB_FACTS=env.lb_facts):
        refused(stage_b, "already read")
        refused(stage_a, "Stage A is frozen")
    print("Stage B wrote the flag only after the load and the checks, refused a second read, and Stage A is frozen once the lockbox has been read")


# ------------------------------------------------------------------ the commands
TESTS = ("t_constants", "t_known_at", "t_tickers", "t_files", "t_scores", "t_coverage", "t_sides", "t_pipeline", "t_nulls", "t_audit", "t_judge", "t_reference", "t_integration", "t_stage_b_refusals", "t_cut")


def selftest(*only):
    """hand-made worlds and hand-made FINRA files, no real file, no data, no network: every group of tests prints one line, the last line says how many ran (`selftest t_files t_judge` runs only those groups)"""
    unknown = [t for t in only if t not in TESTS]
    if unknown:
        raise SystemExit(f"selftest: unknown group(s) {unknown}; the groups are {', '.join(TESTS)}")
    t0 = time.time()
    names = [t for t in TESTS if not only or t in only]
    with tempfile.TemporaryDirectory() as td, patched(THIS, OUT=os.path.join(td, "out")), patched(DV, REF_CSV=os.path.join(td, "no_such_dir", "resmom_cells_daily_wf.csv")):
        for name in names:                                       # the real FINRA files / asset list / wide calendar / RESMOM line file / OUT are never read or written by a test: a read that is not stubbed lands in a temp dir and refuses
            t1 = time.time()
            globals()[name]()
            print(f"  {name} ok ({time.time() - t1:.1f}s)", flush=True)
    print(f"selftest ok: {len(names)} groups ({', '.join(t[2:] for t in names)}) in {time.time() - t0:.0f}s")


def main(argv):
    cmd, args = (argv[0], argv[1:]) if argv else ("", [])
    fn = {"selftest": selftest, "smoke": smoke, "dryload": dryload, "stage_a": stage_a, "stage_b": stage_b}.get(cmd)
    if fn is None:
        print("usage: r22_shortint.py selftest [group ...] | smoke DIR [stage_b] [noselftest] | dryload | stage_a | stage_b   (dryload: counts only; stage_a after the registered pre-registration is committed; stage_b only on the stock families' one sealed-year day, "
              "with the lead's shortint_stageB_GO.flag on file and the lockbox year's FINRA files pinned)")
        return
    if cmd in ("stage_a", "stage_b"):
        os.makedirs(OUT, exist_ok=True)
    fn(*args)


if __name__ == "__main__":
    main(sys.argv[1:])
