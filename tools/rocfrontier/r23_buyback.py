# BUYBACK r1 - SHAREHOLDER PAYOUT YIELD in US large caps, rebalanced MONTHLY, dollar-neutral: cells P (net payout yield = (REP + DIV - ISS) / MV, Boudoukh et al. 2007) and R (net repurchase yield = (REP - ISS) / MV) - the CASH a firm paid
# to (or raised from) its shareholders over the last four quarters, read from the cash-flow statements of its SEC filings AS FILED (the first filed value of every fact, usable from the first session after its first filing), over its
# market value (the raw close x NETISS r1's point-in-time share count S, the split factor carrying a split between S's as-of date and the rank); at each month-end rank close long the 50 HIGHEST (the biggest net payers), short the
# 50 LOWEST (the biggest net raisers). A leg for BOOK #463 that must clear the STANDALONE bars (MANAGER #56), reported INCREMENTALLY over the S1-RESTATED reference L = #463 + 0.264 x RES [B14]. Pre-registered:
# tools/rocfrontier/PREREG_BUYBACK_R1.txt (canonical LF sha256 d161a334...fbd8 = DRAFT v1 + PRE-DATA ADDENDUM 1 ([B1] the fiscal-year change guard, [B2] the 120-day staleness print, [B3] the tag blind spot, [B4] accession numbers, [B5]
# memory) + PRE-DATA ADDENDUM 2 ([B6] the extract pinned, [B7] issuance read from seven concepts before the zero rule, [B8] the tax-withholding twin, [B9] the zero-rule share of the picks, [B10] the judged reading, [B11] DD5 beside every
# ROC, [B12] the restated L) + PRE-DATA ADDENDUM 3 ([B13] MANAGER's hygiene edit S1: the judged reading is r17_resmom's post_mode 'close', [B10]'s 'keep' reading a report; [B14] the S1-restated L; [B15] the harness's CHOICEs (1) - (18)
# fixed as built and (9)'s discrete-quarter label; [B16] the memory rule) + PRE-DATA ADDENDUM 4 ([B17] S point in time at its first-filed value and within 15 months
# of the rank, else 'stale S') + PRE-DATA ADDENDUM 5 ([B18] the CHOICEs 19 - 26 fixed as built, [B19] the picked positions with a calendar split the vendor's factor does not
# show, listed before any P&L and sent to the hand audit as data-event candidates)). Every rule, threshold, window and cost below is that file; where it is silent the choice is marked CHOICE (each one is listed in the commit report for the lead).
# BUYBACK is NETISS r1's sibling on the same SEC photograph: r17_resmom.py (the loaders, the calendar, the schedule, fills / holds / costs / borrow, the close-before-the-ex-date paths, the cell engine, the statistics, the hygiene windows, the
# audit rows), r18_divrun.py (the REFERENCE book, the incremental A2, the null statistics) and r21_netiss.py (the symbol -> CIK map, the share-count facts and S(r), the split factor and [A3]'s two-way split check, the foreign filers [A4], ONE
# share class per firm [A13], the null's draw, the beta credit rule, the hedged twin, the deciles, the gate, DD5) are imported, never copied and never edited. Importing r21_netiss also points r18_divrun's reference loader at the S1-restated
# L [B14] (resmom_cells_daily_wf_close.csv, sha256 e204dd53...) - this file keeps it so (t_constants checks it). In this file [D2] names the AS-FILED SHARE COUNTS (the prereg's label); RESMOM's spin-off / stock-dividend ex-dates are
# written out in full, never as [D2] ([B13]).
# What this file adds is the CASH: the two pinned cash-flow extracts read as ONE table, the first-filed rule per (concept, start, end), the period types, the trailing four quarters (a FY, else YTD + FY_prev - YTD_prev with the same start and
# [B1]'s guard), the components (the zero rule after [B7]'s seven issuance concepts), the market value, the two scores and their no-score rules, the picks, the twins ([B8], the dividend-only twin, the FLAT twin), the deciles, the
# NETISS question, the hand audit's groups by filing [B4] and the reports.
#   python r23_buyback.py selftest    hand-made worlds + hand-made filings, no data: the first-filed rule and amendments, the cut, the period types, the TTM (a FY, YTD differencing with the same start, [B1]'s fiscal-year change, a missing
#                                     FY_prev / YTD_prev, [B15](9)'s discrete quarter, staleness), the components (first / fallback / mixed, the zero rule against [B7]'s alternatives and the same-value dedupe, a negative fact), the market
#                                     value (a split through F, [A3] both ways), the scale rule, the 0.15 flag, the sides and ties, [B13]'s closes before a spin-off / stock-dividend ex-date, the null, the deciles, the twins, the refusals
#                                     (every pinned file), every TTM / score / pool / pick / path against a plain-python recount
#   python r23_buyback.py smoke DIR   offline end-to-end on SYNTHETIC worlds (NETISS's synthetic market and share counts + synthetic cash-flow extracts with a planted payout effect): Stage A must find it in the planted world and not in the
#                                     null world; DIR's name must contain 'smoke'; `smoke DIR stage_b` also runs Stage B's one read on the synthetic lockbox days
#   python r23_buyback.py dryload     WF inputs only (every input cut to dates < 2025-06-30): prints COUNTS - the files and their concepts, the entries, scored names per rank and cell, every no-score reason, the TTM's formula, the
#                                     concept used, the ZERO shares, the staleness buckets, [B2], [B3] - never a cash amount, score, return or P&L
#   python r23_buyback.py stage_a     WF Stage A: the BEFORE-ANY-P&L block (and [B3]'s refusal above 10%), [B9] after the picks, the POWER LINE before any cell P&L, the cells, A2 over the reference, [B10]'s 'keep' reading beside the
#                                     judged one (a report [B13]), the twins, the NETISS question, the reports, the diagnostics -> buyback_stageA.json (+ buyback_audit_candidates.csv, buyback_flags.csv), PRE-LOCKBOX ONLY
#   python r23_buyback.py stage_b     Stage B (lockbox, ONCE): refuses unless the lead's go-flag buyback_stageB_GO.flag, a Stage A candidate and the lockbox year's pinned extracts (cash flows AND NETISS's share counts) are on file
# Reads (never writes) the SIPORB cache, the ES masters, the #463 book, the sha-pinned wide calendar, the S1-RESTATED RESMOM line file [B14], NETISS's four sha-pinned XBRL / map files and the two sha-pinned cash-flow extracts, every one cut
# at read.
# Results go to OUT (outside git). Nothing here pulls, commits, pushes or writes anywhere else, and nothing here makes a network call.
import bisect, contextlib, io, json, math, os, re, shutil, sys, tempfile, time
from collections import Counter, defaultdict
from types import SimpleNamespace
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import numpy as np, pandas as pd
import r17_resmom as M17            # the sibling harness (RESMOM r1): loaders, calendar, schedule, engine, statistics, audit rows
import r18_divrun as DV             # the sibling harness (DIVRUN r1): the REFERENCE book, the incremental A2, the null statistics
import r21_netiss as NI             # the sibling harness (NETISS r1): the map, the share counts, the split check, [A4] / [A13], the null's draw, the beta rule, the hedged twin, the deciles (importing it sets the S1-restated L [B14])
D15, S, R11, M12, A13 = M17.D15, M17.S, M17.R11, M17.M12, M17.A13       # r15_ddw, r5_siporb, r11_risk, r12_mdl, r13_attn - through r17's own imports
day_i, row_le, dstr, per_year, pctl_text, nan_or, years_back = NI.day_i, NI.row_le, NI.dstr, NI.per_year, NI.pctl_text, NI.nan_or, NI.years_back
jyear = DV.jyear

TS = pd.Timestamp
THIS = sys.modules[__name__]
OUT_DEFAULT = r"C:\EdgeLog\_anatomy_cache\rocfrontier\buyback_r1"
OUT = os.environ.get("EDGELOG_BUYBACK_R1", OUT_DEFAULT)                                                   # results, outside git
PREREG = os.path.join(HERE, "PREREG_BUYBACK_R1.txt")
PREREG_SHA = "d161a33414d6b29d8bb1e20d8a867aa58aa42617781fc15ddc11faaee3c1fbd8"                      # canonical (LF) sha256 of the pre-registration: DRAFT v1 + PRE-DATA ADDENDUM 1 ([B1]-[B5]) + PRE-DATA ADDENDUM 2 ([B6]-[B12]) + PRE-DATA ADDENDUM 3 ([B13] hygiene edit S1, [B14] the S1-restated L, [B15] the harness's CHOICEs, [B16] the memory rule) + PRE-DATA ADDENDUM 4 ([B17] stale S) + PRE-DATA ADDENDUM 5 ([B18] CHOICEs 19-26, [B19] no-factor-move splits); supersedes 0603965f (draft + addenda 1-4), 9d26bcfd (draft + addenda 1-3), 9a99203b (draft + addenda 1-2), 97244872 (draft + addendum 1) and 2b2438af (draft)
WF0, PRE_END, LB0, LB1 = M17.WF0, M17.PRE_END, M17.LB0, M17.LB1          # WF = positions EXITED 2016-07-01 .. 2025-06-29; LB = exits 2025-06-30 .. 2026-06-30 INCLUSIVE; cuts: S.LB0 / S.END
BOOK_WF, BOOK_LB, DEEPEST_WF = M17.BOOK_WF, M17.BOOK_LB, M17.DEEPEST_WF
NREP, SEED = 500, 20261024                                               # the registered null: 500 draws of random names from each rebalance's eligible SCORED pool
CELLS = ("P", "R")                                                       # the family: 2 cells
TWINS = ("DIV", "P8", "R8", "FLAT")                                      # REPORTED twins: the dividend-only twin (DIV / MV on P's scored names), [B8] the tax-withholding twins of both cells, the FLAT twin (R among NETISS's flat share counts)
DECK = "REPY"                                                            # the gross repurchase yield (REP / MV) deciles: a decile-only view, never traded
KEYS = CELLS + TWINS + (DECK,)
TWIN_TEXT = {"DIV": "DIVIDEND-ONLY twin (DIV / MV, P's scored names, the same picks rule)", "P8": "[B8] P with the tax-withholding payments added to REPURCHASES", "R8": "[B8] R with the tax-withholding payments added to REPURCHASES",
             "FLAT": "FLAT twin (R among the scored names whose NETISS one-year share change is within +-2%: thirds, at least 20 a side)"}
YEARS = D15.YEARS                                                        # the nine July-June WF years 2016-17 .. 2024-25
SUBPERIODS = DV.SUBPERIODS                                               # the regime halves 2016-07-01 .. 2021-12-31 and 2022-01-01 .. 2025-06-29
A2_TARGET, A2_REPORT = M17.A2_TARGET, M17.A2_REPORT                      # 25% of #463's std; the book at 0.5c and 2c is reported
A2_MONTHS = 24                                                           # A2's c by volatility over the cell's first 24 months of traded fills (CHOICE: the calendar window first traded fill .. + 24 months - 1 day; printed)
COST_BPS, STRESS_BPS, BORROW, BORROW_STRESS = M17.COST_BPS, M17.STRESS_BPS, M17.BORROW, M17.BORROW_STRESS     # 5 bps a side (stress 10, 20); 0.25% a year on short notional (stress 1% and 3% on k_t > 1.5 sessions)
AUDIT_N = 50                                                             # (f) the 50 largest contributors of each cell are audited by hand
STALE_DAYS = 200                                                         # e more than 200 days before r: no score (a firm that stopped filing)
S_MONTHS = 15                                                            # [B17] S's period end (the dei as-of date, else the balance sheet's period end) within 15 calendar months before the rank, else 'stale S' (unscored)
STALE_PRINT = 120                                                        # [B2] the share of scored names whose statement period ended more than 120 days before the rank close, per year (a print)
STALE_BUCKETS = (60, 120, 200)                                           # the days from e to r per year, counted in buckets (0-60, 61-120, 121-200, over 200)
SCORE_MAX = 0.50                                                         # |score| > 0.50: no score (half the firm's value in a year), counted and LISTED by name
FLAG = 0.15                                                              # (f) |score| > 0.15: the audit flag, listed per rank, never a filter
BLIND_MAX = 0.10                                                         # [B3] above 10% of the universe names in any year reading ZERO on all three components: Stage A waits for MANAGER's ruling
B3_RULING = None                                                         # [B3] MANAGER's ruling, if one is ever needed, comes in a dated addendum (a new prereg sha and this constant); None = Stage A refuses above 10%
FY_GAP = 14                                                              # FY_prev ends within 14 days before s ([B1]: s within 14 days of FY_prev's end + 1 day)
YTD_GAP = 14                                                             # YTD_prev ends within 14 days of e - 1 year
FLAT_LO, FLAT_HI = math.log(0.98), math.log(1.02)                        # the FLAT twin: NETISS's one-year ISS within +-2% (CHOICE: the share count's change S F(a) / (S' F(a')) - 1 within +-2%, i.e. ln 0.98 <= ISS_1 <= ln 1.02)
BETA_CAP = NI.BETA_CAP                                                   # NETISS [A6]: a cell with |realised beta| above 0.20 (per $ of one side's notional) is never credited
CACHE_FIRST_SESSION = NI.CACHE_FIRST_SESSION
T_OTHER, T_Q, T_H, T_9M, T_FY = range(5)
PTYPES = ((T_Q, "Q", 77, 105), (T_H, "H", 168, 196), (T_9M, "9M", 259, 287), (T_FY, "FY", 350, 380))      # period types by length in days (end - start: CHOICE, NETISS's annual weighted-average filter's reading)
PT_NAME = {T_OTHER: "other", T_Q: "Q", T_H: "H", T_9M: "9M", T_FY: "FY"}
G = "us-gaap:"
C_ST = (G + "NetCashProvidedByUsedInFinancingActivities", G + "NetCashProvidedByUsedInFinancingActivitiesContinuingOperations")          # STATEMENT (proves a cash-flow statement exists for the period)
C_REP = (G + "PaymentsForRepurchaseOfCommonStock", G + "PaymentsForRepurchaseOfEquity")                                               # REPURCHASES, else its fallback
C_DIV = (G + "PaymentsOfDividendsCommonStock", G + "PaymentsOfDividends")                                                             # DIVIDENDS, else its fallback
C_ISS = (G + "ProceedsFromIssuanceOfCommonStock", G + "ProceedsFromIssuanceOrSaleOfEquity", G + "ProceedsFromIssuanceInitialPublicOffering")    # [B7] ISSUANCE: the first present of these three ...
C_PLAN = (G + "ProceedsFromStockOptionsExercised", G + "ProceedsFromIssuanceOfSharesUnderIncentiveAndShareBasedCompensationPlansIncludingStockOptions",
          G + "ProceedsFromIssuanceOfSharesUnderIncentiveAndShareBasedCompensationPlans", G + "ProceedsFromStockPlans")                # ... PLUS the stock-plan proceeds, summed over the distinct concepts present
C_TW = (G + "PaymentsRelatedToTaxWithholdingForShareBasedCompensation",)                                                              # [B8] the twin's addition to REPURCHASES
CONCEPTS = C_ST + C_REP + C_DIV + C_ISS + C_PLAN + C_TW                                                                               # the 14 columns of the period table, in this order
CIX = {c: i for i, c in enumerate(CONCEPTS)}
IS_ST = np.array([c in C_ST for c in CONCEPTS])
FILE_CONCEPTS = {"cf": C_REP + C_DIV + C_ISS[:1] + C_ST, "cf_alt": C_ISS[1:] + C_PLAN + C_TW}                                        # what TV's two extracts hold (the manifests' lists; counted, never a gate: the two are read as ONE table)
XBRL_DIR = NI.XBRL_DIR
CF_KEYS = ("cf", "cf_alt")
FILES = {"cf": os.path.join(XBRL_DIR, "cashflow_asfiled_wide.csv"), "cf_alt": os.path.join(XBRL_DIR, "cashflow_alt_asfiled_wide.csv")}
FILE_SHA = {"cf": "6fe4ca5de4610072cd09ee17bb0454bdfa9888f79560d92052671fc224df1632", "cf_alt": "3edfacc7473d04e51ba3a92b97bd633a15c24723e88db28a66b1c463ede82162"}
FILE_LABEL = {"cf": "cash-flow extract (cashflow_asfiled_wide.csv) [B6]", "cf_alt": "alternative cash-flow extract (cashflow_alt_asfiled_wide.csv) [B7]"}
CF_COLS = ("cik", "concept", "unit", "val", "start", "end", "accn", "form", "filed")                                                 # the columns this harness reads (symbols, fy, fp, frame are not)
CF_HDR = ("cik", "symbols", "concept", "unit", "val", "start", "end", "accn", "fy", "fp", "form", "filed", "frame")                 # the extract's layout (tools/extract_companyfacts.py)
LB_CASHFLOW = None       # Stage B: the lockbox year's cash-flow facts (filed 2025-06-30 .. 2026-06-30) are NOT in the pinned extracts (cut at filed 2025-06-30): they come from the same photographed zip (db35d36b), extracted by TV after a Stage A
                         # pass and pinned by sha256 in a dated addendum ({key: (path, sha256)} for both extracts; NETISS's LB_FACTS for the share counts too) before Stage B reads one fact; None = Stage B refuses
CHECK_BOOK = True        # refuse to judge if the #463 records / the DD structure / the cache manifest / the reference / the cache's first session do not reproduce the registered facts; a real run always checks (only smoke() may switch it)
HYG = M17.HYG
AUD = M17.AUD
JUDGED = NI.JUDGED       # [B13] MANAGER's HYGIENE EDIT S1 (#127): the judged reading and its null are r17_resmom's post_mode 'close' (NETISS's judged reading, r21_netiss [A22]; prereg_ok refuses any other) - NO in-hold event removes a name
                         # (flagged names and registered / calendar splits stay on the split-safe path) and a spin-off / stock-dividend ex-date e inside the hold (f < e <= x) CLOSES the position at the official close of e-1; the null draws from
                         # the same pool with the same cut paths. [B10]'s removal reading ('keep') is REPORTED beside it, null-less, with its count of removed name-months (bb_one branches on post_mode exactly as r21's ni_one does)
LAB_J = f"judged [B13] (post_mode '{JUDGED}': no in-hold removal - flagged names and splits on the split-safe path; a spin-off / stock-dividend ex-date inside the hold closes the position at the close before it)"
LAB_A = "[B10]'s removal reading ('keep': an announced split or a spin-off / stock-dividend ex-date inside the hold removed the name at the rank; REPORTED, never the verdict) [B13]"
TRANSITION_FORMS = ("10-KT", "10-QT", "10-KT/A", "10-QT/A")                # [B15](9) a TRANSITION REPORT's forms: a fact first filed on one is the evidence of a fiscal-year change (CHOICE)
GO_FLAG, READ_FLAG = "buyback_stageB_GO.flag", "buyback_stageB_READ.flag"
RULES = M17.RULES        # Stage A (a) - (e) and Stage B's leg veto are r17_resmom's own (the booleans are switches only smoke() ever turns off)
SPEC = {"min_scored": 150, "min_side": 20,          # fewer than 150 scored names: the bottom / top THIRD (n // 3 a side), at least 20 a side, else nothing (counted)
        "flat_min": 20,                             # the FLAT twin: the top / bottom third, at least 20 a side, else nothing
        "dec_n": 10, "dec_min": 10}                 # ten equal-count score deciles per rank (a rank with fewer than 10 scored names has none, counted)
TAIL = "(nothing computed, lockbox NOT read)"
DAY0, KEYMUL, D1 = NI.DAY0, NI.KEYMUL, 100000
BIG = np.iinfo(np.int32).max
# the reasons a name has no score at a rank, by the FIRST rule that fails, in the prereg's order: the map / [A4] / the cash table, then no usable statement, no TTM ([B1] / [B15](9)'s discrete quarter / FY_prev / YTD_prev), stale, a negative
# TTM component (CHOICE), the market value (no share fact / no S / [B17] stale S / S not positive / no factor or close / [A3] both ways), |score| > 0.50; the second share class is [A13]'s POOL-level reason (bb_one counts it, score_rank never assigns it).
# [B15](9): the DISCRETE QUARTER is [B1]'s failure split off under its own label - the same slot, no TTM either way (a label only: no score changes)
(R_SCORED, R_NOT_IN_MAP, R_MAP_MISMATCH, R_MAP_AMBIGUOUS, R_MAP_UNMAPPED, R_MAP_NONCOMMON, R_MAP_OTHER, R_FOREIGN, R_NO_CF, R_NO_STATEMENT, R_FY_CHANGE, R_DISCRETE_Q, R_NO_FY_PREV, R_NO_YTD_PREV, R_STALE, R_NEG_TTM, R_NO_SHARES,
 R_NO_S, R_STALE_S, R_S_NOT_POS, R_NO_FACTOR, R_SPLIT_C, R_SPLIT_F, R_OVER50, R_SECOND_CLASS) = range(25)
REASONS = ("scored", "not_in_map", "map_mismatch", "map_ambiguous", "map_unmapped", "map_non_common", "map_other", "foreign_filer", "no_cashflow_fact_for_cik", "no_usable_statement", "fiscal_year_change", "discrete_quarter", "no_fy_prev",
           "no_ytd_prev", "stale_over_200_days", "negative_ttm_component", "no_share_fact_for_cik", "no_share_count_at_r", "stale_s", "share_count_not_positive", "no_split_factor_or_close", "split_calendar_not_in_F", "split_F_not_in_calendar",
           "score_over_0.50", "second_share_class")
REASON_TEXT = {"scored": "scored", "not_in_map": "symbol not in the map", "map_mismatch": "map: current ticker, name does not agree", "map_ambiguous": "map: name ambiguous", "map_unmapped": "map: unmapped",
               "map_non_common": "map: debenture / preferred / unit", "map_other": "map: another method", "foreign_filer": "NETISS [A4] foreign filer (20-F / 40-F / 6-K only)", "no_cashflow_fact_for_cik": "CIK with no cash-flow fact",
               "no_usable_statement": "no usable statement (a FY or a year-to-date period with a STATEMENT fact)", "fiscal_year_change": "[B1] fiscal-year change (s not within 14 days of FY_prev's end + 1, not [B15](9)'s discrete quarter): no TTM",
               "discrete_quarter": "[B15](9) a discrete quarter (a statement quarter that does not start at its fiscal year's start: 3 / 6 / 9 months after FY_prev's end + 1, no transition report on file): no TTM, a label apart from [B1]",
               "no_fy_prev": "no TTM: no usable FY_prev", "no_ytd_prev": "no TTM: no usable YTD_prev", "stale_over_200_days": "stale: e more than 200 days before r", "negative_ttm_component": "a component's TTM is negative (CHOICE)",
               "no_share_fact_for_cik": "MV: CIK with no share fact", "no_share_count_at_r": "MV: no usable share count at r", "stale_s": "MV: [B17] stale S (its as-of date - the cover page's, else the balance sheet's period end - more than 15 calendar months before r)", "share_count_not_positive": "MV: share count not positive", "no_split_factor_or_close": "MV: no split factor or close",
               "split_calendar_not_in_F": "MV: [A3] a calendar split F does not show (a .. r)", "split_F_not_in_calendar": "MV: [A3] an F change the calendar does not show (a .. r)", "score_over_0.50": "|score| > 0.50 (LISTED by name)",
               "second_share_class": "NETISS [A13] second share class of a CIK (the other class has the larger dollar volume)"}
NI_STATIC = {NI.R_NOT_IN_MAP: R_NOT_IN_MAP, NI.R_MAP_MISMATCH: R_MAP_MISMATCH, NI.R_MAP_AMBIGUOUS: R_MAP_AMBIGUOUS, NI.R_MAP_UNMAPPED: R_MAP_UNMAPPED, NI.R_MAP_NONCOMMON: R_MAP_NONCOMMON, NI.R_MAP_OTHER: R_MAP_OTHER,
             NI.R_FOREIGN: R_FOREIGN}                                    # NETISS's static reasons; its 'CIK with no share fact' is a MARKET VALUE reason here (attributed after the cash-flow rules, the prereg's order)
STATIC_CODES = (R_NOT_IN_MAP, R_MAP_MISMATCH, R_MAP_AMBIGUOUS, R_MAP_UNMAPPED, R_MAP_NONCOMMON, R_MAP_OTHER, R_FOREIGN, R_NO_CF, R_NO_SHARES)
CODE_KEYS = ("P", "R", "P8", "R8")                                       # the score vectors with their own no-score codes (the DIV twin and REP / MV are read on P's / R's scored names)


# ------------------------------------------------------------------ guards: the prereg, the stamp, the files
def refuse(msg):
    raise SystemExit(msg)


assert_cut, peak_mb, patched, ceil_pct = A13.assert_cut, A13.peak_mb, A13.patched, A13.ceil_pct
file_sha, manifest_sha, book_checks = M17.file_sha, M17.manifest_sha, M17.book_checks      # module-level names, so a test can stub them


def prereg_ok():
    """the frozen spec this file implements must still be the registered one (a changed spec = a new file, r2): a missing or changed file refuses every stage. Also checked against the committed blob (r15_ddw.committed_state, pointed
    at this file's names for the call); until it is committed that is printed (the lead commits before the real run) and recorded in the Stage A file"""
    if not os.path.exists(PREREG):
        refuse("refused: PREREG_BUYBACK_R1.txt is not next to this file - the spec cannot be verified " + TAIL)
    if R11.sha_lf(PREREG) != PREREG_SHA:
        refuse("refused: PREREG_BUYBACK_R1.txt DIFFERS from the registered one - a changed spec is a new file, r2 " + TAIL)
    with patched(D15, PREREG=PREREG, PREREG_SHA=PREREG_SHA):
        st = D15.committed_state()
    if st == "differs":
        refuse("refused: the COMMITTED PREREG_BUYBACK_R1.txt differs from the registered sha - the file on disk is not the file in git " + TAIL)
    if JUDGED != "close" or "close" not in M17.POST_MODES:                                    # [B13]: the judged reading is r17_resmom's post_mode 'close' (read through r21_netiss.JUDGED) - anything else is not the registered reading
        refuse(f"refused: the judged reading is post_mode {JUDGED!r}, not [B13]'s 'close' (r21_netiss.JUDGED / r17_resmom.POST_MODES changed) " + TAIL)
    print("prereg check: PREREG_BUYBACK_R1.txt sha256 matches the registered one; committed blob: " + {"match": "matches too", "untracked": "NOT COMMITTED YET - commit it before the real run",
                                                                                                     "unknown": "git not available here (not checked)"}[st])
    return {"verified": True, "committed": st}


def stamp():
    """the version a stage ran with: this file's LF sha256 + r21_netiss's stamp (its own sha, r17's, r18's and every harness they import, the pinned wide calendar's sha and NETISS's four pinned XBRL / map files) + the two pinned
    cash-flow extracts' shas; Stage B refuses on any change"""
    ni = NI.stamp()
    return {"harness_sha256": R11.sha_lf(os.path.abspath(__file__)), "r21_sha256": ni["harness_sha256"], **{k: v for k, v in ni.items() if k != "harness_sha256"}, **{f"{k}_sha256": FILE_SHA[k] for k in CF_KEYS}}


@contextlib.contextmanager
def spec(**kw):
    """swap SPEC entries (this file's), r21_netiss.SPEC's (the keys the two share: NETISS's cells in the NETISS question run on the same rule) and r17_resmom.SPEC's (the windows, the sides, the size) for a block and put them back (the
    self-tests and the smoke shrink them; nothing stays patched)"""
    mine, theirs = {k: v for k, v in kw.items() if k in SPEC}, {k: v for k, v in kw.items() if k not in SPEC or k in NI.SPEC}
    old = dict(SPEC)
    SPEC.update(mine)
    try:
        with NI.spec(**theirs):
            yield
    finally:
        SPEC.clear()
        SPEC.update(old)


def dump(obj, name):
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, name), "w") as f:
        json.dump(obj, f, indent=1, default=R11.js)


def check_pinned(key):
    """the sha256 (of the BYTES) of one pinned extract: refuses - nothing computed, lockbox NOT read - when it is not on file or is another file than the registered one"""
    p = FILES[key]
    if not os.path.exists(p):
        refuse(f"refused: the pinned {FILE_LABEL[key]} {p} is not on file {TAIL}")
    got = M17.sha_raw(p)
    if got != FILE_SHA[key]:
        refuse(f"refused: {os.path.basename(p)} (sha256 {got}) is not the registered {FILE_LABEL[key]} ({FILE_SHA[key]}) - the file changed after it was registered {TAIL}")
    return got


# ------------------------------------------------------------------ [B6] / [B7] the two pinned extracts read as ONE table, in chunks into compact arrays, cut at READ
class Intern:
    """strings -> dense integer codes (in the order first seen), shared across the chunks of a read"""
    def __init__(self):
        self.ix, self.vals = {}, []

    def codes(self, s):
        c, u = pd.factorize(pd.Series(s, dtype=object))
        g = np.empty(len(u), np.int64)
        for i, v in enumerate(u):
            k = self.ix.get(v)
            if k is None:
                k = self.ix[v] = len(self.vals)
                self.vals.append(v)
            g[i] = k
        return g[c] if len(c) else np.zeros(0, np.int64)


DROP_KEYS = ("rows_other_concept", "rows_unit_not_usd", "rows_unreadable_date", "rows_start_after_end", "rows_filed_on_or_after_the_cut", "rows_end_on_or_after_the_cut")


def cf_chunk(ch, cutt, src, I, cnt):
    """one chunk of an extract (string columns) -> the typed arrays of the rows kept. Dropped and counted, each row at its FIRST reason: a concept other than the 14, a unit other than USD, an unreadable start / end / filed date, a start after
    its end, a row FILED on / after the cut (the sealed year: TV's extract holds none - cut again at read [B6]), a row whose period ENDS on / after the cut (a typo year). An unreadable value is kept as NaN (the first-filed rule makes
    that entry unusable) and counted"""
    con = ch["concept"].astype(str).str.strip()
    ci = con.map(CIX)
    bad_con = ci.isna().to_numpy()
    bad_unit = (ch["unit"].astype(str).str.strip() != "USD").to_numpy()
    dt = lambda c: pd.to_datetime(ch[c].astype(str).str.strip(), format="%Y-%m-%d", errors="coerce")
    st, en, fl = dt("start"), dt("end"), dt("filed")
    bad_date = (st.isna() | en.isna() | fl.isna()).to_numpy()
    with np.errstate(invalid="ignore"):
        order = ~bad_date & (st > en).to_numpy()
        late = ~bad_date & (fl >= cutt).to_numpy()
        late_end = ~bad_date & ~late & (en >= cutt).to_numpy()
    seen = np.zeros(len(ch), bool)
    for key, m in zip(DROP_KEYS, (bad_con, bad_unit, bad_date, order, late, late_end)):
        cnt[key] += int((m & ~seen).sum())
        seen |= m
    k = np.flatnonzero(~seen)
    val = pd.to_numeric(ch["val"].astype(str).str.strip().where(lambda t: t != ""), errors="coerce").to_numpy(float)[k]
    cnt["rows_value_missing"] += int((~np.isfinite(val)).sum())
    sub = lambda c: ch[c].astype(str).str.strip().to_numpy(object)[k]
    return {"ck": I["cik"].codes(sub("cik")).astype(np.int32), "con": ci.to_numpy()[k].astype(np.int8), "val": val, "start": day_i(st.to_numpy()[k]).astype(np.int32), "end": day_i(en.to_numpy()[k]).astype(np.int32),
            "filed": day_i(fl.to_numpy()[k]).astype(np.int32), "accn": I["accn"].codes(sub("accn")).astype(np.int32), "form": I["form"].codes(np.char.upper(sub("form").astype(str))).astype(np.int16),
            "src": np.full(len(k), src, np.int8)}


def cf_finish(parts, I):
    """the kept rows of every chunk -> ONE table (SimpleNamespace of arrays; accn codes renumbered in the accession numbers' string order, so 'the smallest accession' is the smallest code)"""
    cat = lambda k, dt: np.concatenate([p[k] for p in parts]).astype(dt) if parts else np.zeros(0, dt)
    accns = np.array(I["accn"].vals, dtype=str) if I["accn"].vals else np.zeros(0, dtype=str)
    o = np.argsort(accns, kind="stable")
    rank = np.empty(len(accns), np.int64)
    rank[o] = np.arange(len(accns))
    ac = cat("accn", np.int64)
    return SimpleNamespace(ck=cat("ck", np.int32), con=cat("con", np.int8), val=cat("val", float), start=cat("start", np.int32), end=cat("end", np.int32), filed=cat("filed", np.int32), accn=(rank[ac] if len(ac) else ac).astype(np.int32),
                           form=cat("form", np.int16), src=cat("src", np.int8), ciks=np.array(I["cik"].vals, dtype=str), accns=accns[o], forms=list(I["form"].vals), n=int(sum(len(p["ck"]) for p in parts)))


def new_interns():
    return {"cik": Intern(), "accn": Intern(), "form": Intern()}


def load_cashflow(cut, chunk=250_000):
    """[B6] / [B7] the two pinned extracts (cashflow_asfiled_wide.csv sha 6fe4ca5d, cashflow_alt_asfiled_wide.csv sha 3edfacc7) read as ONE table, each refused - nothing computed - if it is absent or its sha256 differs, and a
    FACT present in both (the same cik, concept, start, end and accession) refused (no silent overlap). Read ONCE in chunks, only the columns used, into compact arrays (cik / accession / form as codes, dates as day numbers). Cut at
    READ: rows filed on / after the cut dropped and counted (the extract holds none) and the table asserted free of the cut afterwards (filed and end). -> (cf, info: the counts per file, per concept, the drops, the forms)"""
    shas = {k: check_pinned(k) for k in CF_KEYS}
    cutt = TS(cut)
    I, parts, cnt = new_interns(), [], Counter()
    info = {"sha256": shas, "files": {}}
    for q, key in enumerate(CF_KEYS):
        hdr = pd.read_csv(FILES[key], nrows=0)
        miss = [c for c in CF_COLS if c not in hdr.columns]
        if miss:
            refuse(f"refused: the {FILE_LABEL[key]} lacks the column(s) {miss} {TAIL}")
        n = 0
        for ch in pd.read_csv(FILES[key], usecols=list(CF_COLS), dtype=str, keep_default_na=False, chunksize=chunk):
            n += len(ch)
            parts.append(cf_chunk(ch, cutt, q, I, cnt))
        info["files"][key] = int(n)
    cf = cf_finish(parts, I)
    del parts
    overlap_check(cf)
    assert_cut("cash-flow facts (filed)", pd.DatetimeIndex(cf.filed.astype("datetime64[D]")), cut)
    assert_cut("cash-flow facts (period end)", pd.DatetimeIndex(cf.end.astype("datetime64[D]")), cut)
    info.update(cf_counts(cf), **{k: int(cnt[k]) for k in DROP_KEYS + ("rows_value_missing",)}, rows_read=int(sum(info["files"].values())), cut=f"{cutt:%Y-%m-%d}")
    return cf, info


def overlap_check(cf):
    """[B7] 'a fact present in both is refused': the same (cik, concept, start, end, accession) in both extracts refuses (the two hold disjoint concepts by TV's manifests; only a concept found in both is checked row by row)"""
    both = sorted(set(cf.con[cf.src == 0].tolist()) & set(cf.con[cf.src == 1].tolist()))
    if not both:
        return
    m = np.isin(cf.con, both)
    df = pd.DataFrame({"ck": cf.ck[m], "con": cf.con[m], "s": cf.start[m], "e": cf.end[m], "a": cf.accn[m], "src": cf.src[m]})
    g = df.groupby(["ck", "con", "s", "e", "a"])["src"].nunique()
    if (g > 1).any():
        ck, con, s, e, a = g[g > 1].index[0]
        refuse(f"refused: {int((g > 1).sum()):,} fact(s) are in BOTH cash-flow extracts (e.g. CIK {cf.ciks[ck]}, {CONCEPTS[con]}, {dstr(s)} .. {dstr(e)}, accession {cf.accns[a]}) - no silent overlap {TAIL}")


def cf_counts(cf):
    """counts of the table as read (never a value): rows and CIKs per concept (the exact concept names present), rows per extract, the forms, the filed range"""
    con = pd.Series(cf.con)
    by = {CONCEPTS[int(k)]: int(v) for k, v in con.value_counts().sort_index().items()}
    ck = pd.DataFrame({"con": cf.con, "ck": cf.ck}).drop_duplicates().groupby("con").size() if cf.n else pd.Series(dtype=int)
    fm = Counter(cf.forms[int(i)] for i in cf.form) if cf.n < 50 else {cf.forms[int(k)]: int(v) for k, v in pd.Series(cf.form).value_counts().items()}
    return {"rows": int(cf.n), "rows_by_concept": by, "ciks_by_concept": {CONCEPTS[int(k)]: int(v) for k, v in ck.items()}, "rows_by_extract": {k: int((cf.src == q).sum()) for q, k in enumerate(CF_KEYS)},
            "rows_by_form": dict(sorted(((k, int(v)) for k, v in fm.items()), key=lambda kv: -kv[1])[:15]), "ciks": int(len(np.unique(cf.ck))) if cf.n else 0,
            "filed_range": [dstr(int(cf.filed.min())), dstr(int(cf.filed.max()))] if cf.n else None}


# ------------------------------------------------------------------ the CASH KNOWN AT A RANK CLOSE: entries by the first-filed rule, the period table
def build_cash(cf):
    """the table -> the ENTRIES, one per (cik, concept, start, end): the value of its FIRST filed row (the earliest `filed`; amendments, restatements and later comparatives never replace it), f1 = that date, the accession and form of that
    row (two rows on the first day: the smallest accession; CHOICE (NETISS [A2]'s reading): more than one distinct value among them = AMBIGUOUS, unusable). Unusable as well: a missing value, a period ending after its own first filing,
    a NEGATIVE value of a component concept ('a negative fact is unusable'; CHOICE: an unusable fact is as if absent - its fallback / the zero rule read the period; the STATEMENT's sign is free: it only proves the statement exists).
    The PERIOD TABLE: one row per (cik, start, end) sorted by (cik, end, length) - the last of a CIK's candidates is the latest end, the longest period on a tie - with its type by length and FACT (P, 14) = the entry of each concept
    (-1 = none) -> SimpleNamespace(entries E_*, periods p*, FACT, counts)"""
    n = cf.n
    z = lambda dt=np.int32: np.zeros(0, dt)
    if n:
        o = np.lexsort((cf.accn, cf.filed, cf.end, cf.start, cf.con, cf.ck))
        ck, con, st, en, fl, ac, val, fm = (a[o] for a in (cf.ck, cf.con, cf.start, cf.end, cf.filed, cf.accn, cf.val, cf.form))
        new = np.r_[True, (ck[1:] != ck[:-1]) | (con[1:] != con[:-1]) | (st[1:] != st[:-1]) | (en[1:] != en[:-1])]
        g0 = np.flatnonzero(new)
        gid = np.cumsum(new) - 1
        f1 = fl[g0]
        at = fl == f1[gid]
        with np.errstate(invalid="ignore"):
            vat = np.where(at, val, np.nan)
            lo, hi = np.fmin.reduceat(vat, g0), np.fmax.reduceat(vat, g0)
            alo, ahi = np.fmin.reduceat(val, g0), np.fmax.reduceat(val, g0)
        E = SimpleNamespace(ck=ck[g0], con=con[g0], start=st[g0], end=en[g0], f1=f1, val=val[g0], accn=ac[g0], form=fm[g0])
        amb = np.isfinite(lo) & (lo != hi)
        other = np.isfinite(alo) & (alo != ahi)
        nrows = np.diff(np.r_[g0, n])
    else:
        E = SimpleNamespace(ck=z(), con=z(np.int8), start=z(), end=z(), f1=z(), val=z(float), accn=z(), form=z(np.int16))
        amb = other = z(bool)
        nrows = z(np.int64)
    miss = ~np.isfinite(E.val)
    after = E.end > E.f1
    with np.errstate(invalid="ignore"):
        neg = ~miss & (E.val < 0) & ~IS_ST[E.con.astype(np.int64)] if len(E.con) else z(bool)
    ok = ~(amb | after | miss | neg)
    nE = len(E.ck)
    if nE:
        po = np.lexsort((-E.start.astype(np.int64), E.end, E.ck))
        pc, pe, ps = E.ck[po], E.end[po], E.start[po]
        newp = np.r_[True, (pc[1:] != pc[:-1]) | (pe[1:] != pe[:-1]) | (ps[1:] != ps[:-1])]
        pid = np.empty(nE, np.int64)
        pid[po] = np.cumsum(newp) - 1
        pck, pstart, pend = pc[newp], ps[newp], pe[newp]
    else:
        pid, pck, pstart, pend = z(np.int64), z(), z(), z()
    plen = (pend - pstart).astype(np.int64)
    ptype = np.zeros(len(pck), np.int8)
    for t, _nm, a, b in PTYPES:
        ptype[(plen >= a) & (plen <= b)] = t
    FACT = np.full((len(pck), len(CONCEPTS)), -1, np.int32)
    if nE:
        FACT[pid, E.con.astype(np.int64)] = np.arange(nE, dtype=np.int32)
    ciks = cf.ciks
    info = {"entries": int(nE), "ambiguous": int(amb.sum()), "end_after_filed": int(after.sum()), "value_missing": int(miss.sum()), "negative_component_value": int(neg.sum()), "usable": int(ok.sum()),
            "later_filing_carries_another_value": int(other.sum()), "entries_with_two_or_more_rows": int((nrows > 1).sum()), "periods": int(len(pck)),
            "periods_by_type": {PT_NAME[t]: int((ptype == t).sum()) for t in (T_Q, T_H, T_9M, T_FY, T_OTHER)},
            "entries_by_concept": {CONCEPTS[k]: int((E.con == k).sum()) for k in range(len(CONCEPTS))}, "ciks": int(len(np.unique(E.ck))) if nE else 0}
    return SimpleNamespace(E_ck=E.ck, E_con=E.con, E_start=E.start, E_end=E.end, E_f1=E.f1, E_val=E.val, E_accn=E.accn, E_form=E.form, E_ok=ok, E_amb=amb, E_neg=neg, pck=pck, pstart=pstart, pend=pend, plen=plen, ptype=ptype, FACT=FACT,
                           ciks=ciks, cix={c: i for i, c in enumerate(ciks)}, nck=int(len(ciks)), accns=cf.accns, forms=cf.forms, info=info)


# ------------------------------------------------------------------ the World's BUYBACK arrays: NETISS's (W.ni) + the cash table bound to the sessions + the names' cash CIKs and static reasons
def attach_buyback(W, cash, fx, mp, cal):
    """NETISS's arrays first (r21's attach_netiss: the share-count entries bound to the sessions, the names' share CIKs and static reasons, [A3]'s running counts, the calendar's splits for the judged reading, [A13]'s dollar volume),
    then the cash table bound to the sessions: urow = the first session STRICTLY AFTER an entry's first filed date (usable at r iff urow <= r - NETISS [A2]); URW (P, 14) = that row for each period's usable fact of each concept (BIG where
    the period has no usable fact of it). The names' cash CIKs come from the same map row NETISS reads; the static reasons: NETISS's map / [A4] foreign-filer codes, then 'no cash-flow fact for the CIK' -> W.bb"""
    ni = NI.attach_netiss(W, fx, mp, cal)
    di = ni.days_i
    urow = np.searchsorted(di, cash.E_f1, side="right").astype(np.int64)
    F = cash.FACT
    Fz = np.maximum(F, 0)
    URW = np.where((F >= 0) & cash.E_ok[Fz], np.minimum(urow[Fz], BIG), BIG).astype(np.int32) if F.size else np.zeros(F.shape, np.int32)
    syms = np.asarray(W.syms).astype(str)
    df = mp.df
    ix = pd.Index(df["symbol"]).get_indexer(syms)
    take = np.maximum(ix, 0)
    usable, cik = df["usable"].to_numpy(bool)[take] & (ix >= 0), df["cik"].to_numpy(object)[take]
    static = np.zeros(W.S, np.int8)
    for j in range(W.S):
        static[j] = NI_STATIC.get(int(ni.static[j]), R_SCORED)
    cn = np.full(W.S, -1, np.int64)
    for j in np.flatnonzero(usable & (static == R_SCORED)):
        cn[j] = cash.cix.get(str(cik[j]), -1)
        if cn[j] < 0:
            static[j] = R_NO_CF
    trans = np.isin(cash.E_form, [i for i, fm in enumerate(cash.forms) if fm in TRANSITION_FORMS]) if len(cash.E_form) else np.zeros(0, bool)      # [B15](9) the entries first filed on a transition report
    W.bb = SimpleNamespace(cash=cash, urow=urow, URW=URW, cn=cn, static=static, no_shares=(np.asarray(ni.static) == NI.R_NO_FACTS), trans=trans, cache={})
    return W.bb


def latest_entry(ent, r, cn):
    """per name (cn = a share CIK index, -1 = none): the USABLE entry of one share concept with the latest as-of date at row r (NETISS's S(r) without its S'; ent.urow <= r) or -1"""
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


def comp_at(cs, U, pp):
    """the components read on the periods pp (period rows, -1 = none), period by period: REP / DIV = the first concept that has a usable fact for the period, else its fallback, else ZERO (src 1 / 2 / 0); TW the same with one concept;
    ISS [B7] = the first present of the three primary concepts (prim 1 / 2 / 3, 0 = none) PLUS the stock-plan proceeds summed over the distinct concepts present, where an item (the primary or a plan concept) carrying the SAME value
    in the SAME filing as an earlier item counts once (CHOICE: the dedupe runs over all the items summed, the primary included, and 'one filing' = the same first-filed accession; items first filed in different filings are summed);
    a period with none of the seven reads ZERO. Only periods with a STATEMENT fact are ever read here (the TTM's periods), so 'absent' = ZERO. -> dict of (n,) arrays"""
    n = len(pp)
    ok = pp >= 0
    pz = np.maximum(pp, 0)
    Ux = U[pz] & ok[:, None] if n else np.zeros((0, len(CONCEPTS)), bool)
    Fz = np.maximum(cs.FACT[pz], 0) if n else np.zeros((0, len(CONCEPTS)), np.int64)
    V = np.where(Ux, cs.E_val[Fz], 0.0)
    A = np.where(Ux, cs.E_accn[Fz], -1)
    out = {}
    for nm, cols in (("rep", C_REP), ("div", C_DIV)):
        a, b = CIX[cols[0]], CIX[cols[1]]
        src = np.where(Ux[:, a], 1, np.where(Ux[:, b], 2, 0)).astype(np.int8)
        out[nm] = np.where(src == 1, V[:, a], np.where(src == 2, V[:, b], 0.0))
        out[nm + "_src"] = np.where(ok, src, -1).astype(np.int8)
    t = CIX[C_TW[0]]
    out["tw"], out["tw_src"] = np.where(Ux[:, t], V[:, t], 0.0), np.where(ok, Ux[:, t].astype(np.int8), -1).astype(np.int8)
    pc = [CIX[c] for c in C_ISS]
    prim = np.where(Ux[:, pc[0]], 1, np.where(Ux[:, pc[1]], 2, np.where(Ux[:, pc[2]], 3, 0))).astype(np.int8)
    pcol = np.array(pc)[np.maximum(prim - 1, 0)]
    r_ = np.arange(n)
    items = [(prim > 0, np.where(prim > 0, V[r_, pcol], 0.0), np.where(prim > 0, A[r_, pcol], -1))] + [(Ux[:, CIX[c]], V[:, CIX[c]], A[:, CIX[c]]) for c in C_PLAN]
    tot, nplan, ndup = np.zeros(n), np.zeros(n, np.int8), np.zeros(n, np.int8)
    for i, (pi, vi, ai) in enumerate(items):
        dup = np.zeros(n, bool)
        for j in range(i):
            pj, vj, aj = items[j]
            dup |= pj & (aj == ai) & (vj == vi)
        take = pi & ~dup
        tot += np.where(take, vi, 0.0)
        ndup += (pi & dup).astype(np.int8)
        if i:
            nplan += take.astype(np.int8)
    any7 = np.zeros(n, bool)
    for pi, _v, _a in items:
        any7 |= pi
    out.update(iss=tot, iss_prim=np.where(ok, prim, -1).astype(np.int8), iss_plan=nplan, iss_dup=ndup, iss_any=any7 & ok)
    st = np.where(Ux[:, 0], 1, np.where(Ux[:, 1], 2, 0)).astype(np.int8)
    out["st_src"] = np.where(ok, st, -1).astype(np.int8)
    return out


def on_quarter_grid(s, e0):
    """[B15](9) CHOICE: day s lies within 14 days of e0 + 1 day + 3, 6 or 9 months + a whole number of years (pandas' month arithmetic: the day clipped to the month's length) - a QUARTER start of the fiscal calendar that a fiscal year
    ending on day e0 implies, not its year start"""
    base = TS(np.datetime64(int(e0) + 1, "D"))
    q = 1
    while True:
        g = dnum(base + pd.DateOffset(months=3 * q))
        if g > s + FY_GAP:
            return False
        if q % 4 and abs(s - g) <= FY_GAP:
            return True
        q += 1


def discrete_quarter(bb, c, s, ty, e0, r):
    """[B15](9) CHOICE: a statement period that fails [B1]'s 14-day test (it starts more than 14 days after FY_prev's end e0 + 1 day) is a DISCRETE QUARTER - a period that does not start at its fiscal year's start - when it is a quarter
    (77-105 days long) that starts on the fiscal calendar FY_prev implies (on_quarter_grid) and no TRANSITION REPORT of the CIK c is on file: no usable fact first filed on a 10-KT / 10-QT (amendments included) usable at the rank r ends
    after e0 (a transition period filed = the fiscal year moved: [B1]'s fiscal-year change). Everything else that fails [B1] stays the fiscal-year change. A label only: no TTM either way, no score changes"""
    if ty != T_Q or not on_quarter_grid(s, e0):
        return False
    cs = bb.cash
    lo, hi = int(np.searchsorted(cs.E_ck, c, "left")), int(np.searchsorted(cs.E_ck, c, "right"))       # the CIK's entries (sorted by CIK)
    return not bool((bb.trans[lo:hi] & cs.E_ok[lo:hi] & (bb.urow[lo:hi] <= r) & (cs.E_end[lo:hi] > e0)).any())


def score_rank(W, r):
    """the BUYBACK scores of every name of the World at the rank close r (universe-wide and pool-blind; [A13] is decided later, among the pool's scored names). Per name, in the prereg's order:
    the static reasons (map / NETISS [A4] / no cash-flow fact); the STATEMENT = the latest usable period ending e that is a FY or a Q / H / 9M period with a usable STATEMENT fact (CHOICE: on a tie of e the longest; a Q / H / 9M period is
    read as a year-to-date one - cash-flow facts in 10-Qs are YTD [B6] - and a period that is not (a discrete quarter) fails the FY_prev test below, counted under [B15](9)'s own label); the TTM: a FY -> its own value; else YTD(s .. e) +
    FY_prev - YTD_prev, FY_prev = the latest usable FY (with its STATEMENT fact) ending before s - none -> 'no FY_prev', one that ends more than 14 days before s -> [B1] 'fiscal-year change' (s not within 14 days of its end + 1 day; CHOICE:
    the draft's 'ending within 14 days before s' read as s - end <= 14, so [B1]'s guard holds whenever FY_prev exists), or [B15](9)'s 'discrete quarter' (discrete_quarter: the same slot, a label apart) - and YTD_prev = the usable period
    of the same type with the SAME START as FY_prev ending within 14 days of e - 1 year (the closest; a tie to the
    earlier); stale (e more than 200 days before r); a negative component TTM (CHOICE: no score in the cell that reads it; 'all >= 0'); the market value MV = raw close(r) x S x F(a) / F(r) with S = NETISS's share count (the latest
    usable cover-page value, else the balance sheet's: CHOICE, SHORTINT's S1 reading of 'NETISS's S(r)'; [B17] point in time - NETISS's entries carry the FIRST-FILED value of each (cik, concept, as-of date), a restatement filed later never
    replaces it, and an entry is usable only from the first session strictly after its first filing; the as-of date a of the S so chosen must lie within 15 calendar months before r, else 'stale S' - CHOICE: the order picks S first and then
    tests it, a stale cover-page count never falls back to a fresher balance-sheet count), [A3]'s two-way split check on (a, r] where the calendar covers a; |score| > 0.50. Cached by r.
    -> SimpleNamespace: per name the TTM's periods (p0, p1, p2), kind (1 FY / 2 YTD), e, s, the TTMs rep / div / iss / tw, per period the components' sources and ZERO flags (3, S), the share-count inputs, mv, and per key in
    CODE_KEYS + ('DIV', 'REPY') the code / score / scored / flag vectors"""
    bb = W.bb
    got = bb.cache.get(r)
    if got is not None:
        return got
    cs, ni, S_ = bb.cash, W.ni, W.S
    U = bb.URW <= r
    stp = U[:, 0] | U[:, 1]
    cand = stp & (cs.ptype > 0)
    ui = np.flatnonzero(cand)
    cn = bb.cn
    has = cn >= 0
    code = bb.static.astype(np.int64).copy()
    alive = code == R_SCORED

    def drop(mask, reason):
        hit = alive & mask
        code[hit] = reason
        alive[hit] = False
    p0 = np.full(S_, -1, np.int64)
    if len(ui):
        ck = cs.pck[ui]
        last = np.r_[ck[1:] != ck[:-1], True]
        st_of = np.full(cs.nck, -1, np.int64)
        st_of[ck[last]] = ui[last]
        p0 = np.where(has, st_of[np.where(has, cn, 0)], -1)
    drop(p0 < 0, R_NO_STATEMENT)
    p0 = np.where(alive, p0, -1)
    pz = np.maximum(p0, 0)
    s, e, ty = cs.pstart[pz].astype(np.int64), cs.pend[pz].astype(np.int64), cs.ptype[pz].astype(np.int64)
    ytd = (p0 >= 0) & (ty != T_FY)
    p1 = np.full(S_, -1, np.int64)
    fyi = ui[cs.ptype[ui] == T_FY]
    if len(fyi) and ytd.any():
        key = cs.pck[fyi].astype(np.int64) * KEYMUL + (cs.pend[fyi].astype(np.int64) - DAY0)
        q = np.where(ytd, cn, 0) * KEYMUL + (s - 1 - DAY0)
        pos = np.searchsorted(key, q, side="right") - 1
        pc_ = np.clip(pos, 0, len(fyi) - 1)
        p1 = np.where(ytd & (pos >= 0) & (cs.pck[fyi[pc_]] == np.where(ytd, cn, -1)), fyi[pc_], -1)
    gap = s - cs.pend[np.maximum(p1, 0)].astype(np.int64)
    fyc = ytd & (p1 >= 0) & (gap > FY_GAP)                                     # [B1] s more than 14 days after FY_prev's end + 1: no TTM
    dq = np.zeros(S_, bool)
    for j in np.flatnonzero(alive & fyc):                                      # [B15](9) the discrete quarters among them, under their own label (a few names a rank: a loop)
        dq[j] = discrete_quarter(bb, int(cn[j]), int(s[j]), int(ty[j]), int(cs.pend[p1[j]]), r)
    drop(dq, R_DISCRETE_Q)
    drop(fyc, R_FY_CHANGE)
    drop(ytd & (p1 < 0), R_NO_FY_PREV)
    p1 = np.where(alive & ytd, p1, -1)
    p2 = np.full(S_, -1, np.int64)
    need = alive & ytd & (p1 >= 0)
    yi = ui[(cs.ptype[ui] != T_FY)]
    if len(yi) and need.any():
        k2 = ((cs.pck[yi].astype(np.int64) * 8 + cs.ptype[yi]) * D1 + (cs.pstart[yi].astype(np.int64) - DAY0)) * D1 + (cs.pend[yi].astype(np.int64) - DAY0)
        o2 = np.argsort(k2, kind="stable")
        k2s, y2 = k2[o2], yi[o2]
        tgt = years_back(e, 1)
        pre = (np.where(need, cn, 0) * 8 + ty) * D1 + (cs.pstart[np.maximum(p1, 0)].astype(np.int64) - DAY0)
        pos = np.searchsorted(k2s, pre * D1 + (tgt - DAY0))
        m = len(k2s)
        li, ri = np.clip(pos - 1, 0, m - 1), np.clip(pos, 0, m - 1)
        far = 10 ** 9
        dl = np.where((pos - 1 >= 0) & (k2s[li] // D1 == pre), tgt - cs.pend[y2[li]].astype(np.int64), far)
        dr = np.where((pos < m) & (k2s[ri] // D1 == pre), cs.pend[y2[ri]].astype(np.int64) - tgt, far)
        left = dl <= dr
        best, bi = np.where(left, dl, dr), np.where(left, li, ri)
        p2 = np.where(need & (best <= YTD_GAP), y2[bi], -1)
    drop(need & (p2 < 0), R_NO_YTD_PREV)
    kind = np.where(alive, np.where(ytd, 2, 1), 0).astype(np.int8)
    pp = np.vstack([np.where(alive, p0, -1), np.where(alive & ytd, p1, -1), np.where(alive & ytd, p2, -1)])
    comps = [comp_at(cs, U, pp[q]) for q in range(3)]
    sign = (1.0, 1.0, -1.0)
    ttm = {nm: np.where(alive, sum(sign[q] * comps[q][nm] for q in range(3)), np.nan) for nm in ("rep", "div", "iss", "tw")}
    has_ttm = alive.copy()
    dr_i = int(ni.days_i[r])
    drop((dr_i - e) > STALE_DAYS, R_STALE)
    # the market value: NETISS's share count S at r, its as-of date a, F(a) / F(r), the raw close; [A3] both ways on (a, r] where the calendar covers a
    j_ = np.arange(S_)
    cnn = np.asarray(ni.cik_ix)
    sd_, sg_ = latest_entry(ni.dei, r, cnn), latest_entry(ni.gaap, r, cnn)
    sg = np.where(sd_ >= 0, sd_ + ni.off["dei"], np.where(sg_ >= 0, sg_ + ni.off["gaap"], -1))
    sgc = np.maximum(sg, 0)
    Sv, a = np.where(sg >= 0, ni.E_val[sgc], np.nan), np.where(sg >= 0, ni.E_end[sgc], 0).astype(np.int64)
    ia = np.where(sg >= 0, row_le(ni.days_i, a), -1)
    ia0 = np.maximum(ia, 0)
    Fm = np.asarray(W.F, float)
    fa, fr, cl = Fm[ia0, j_], Fm[r], np.asarray(W.Cl, float)[r]
    with np.errstate(invalid="ignore"):
        no_f = ~(np.isfinite(fa) & np.isfinite(fr) & np.isfinite(cl) & (fa > 0) & (fr > 0) & (cl > 0) & (ia >= 0))
        s_np = ~(Sv > 0)
    covered = (sg >= 0) & (ni.cal_start_i is not None) & (a >= (ni.cal_start_i if ni.cal_start_i is not None else 0))
    unC, unF = ni.cs_unC[r + 1] - ni.cs_unC[ia0 + 1, j_], ni.cs_unF[r + 1] - ni.cs_unF[ia0 + 1, j_]
    a3c, a3f = covered & (unC > 0), covered & (unF > 0)
    with np.errstate(invalid="ignore", divide="ignore"):
        mv = cl * Sv * fa / fr
    lim = dnum(W.days[r] - pd.DateOffset(months=S_MONTHS))                    # [B17] the oldest as-of date S may carry at r: 15 calendar months before the rank close (pandas' month arithmetic, the day clipped; that day itself is within)
    stale_s = (sg >= 0) & (a < lim)
    mv_fail = [(bb.no_shares, R_NO_SHARES), (sg < 0, R_NO_S), (stale_s, R_STALE_S), (s_np, R_S_NOT_POS), (no_f, R_NO_FACTOR), (a3c, R_SPLIT_C), (a3f, R_SPLIT_F)]
    rep, div, iss, tw = ttm["rep"], ttm["div"], ttm["iss"], ttm["tw"]
    with np.errstate(invalid="ignore", divide="ignore"):
        num = {"P": rep + div - iss, "R": rep - iss, "P8": rep + tw + div - iss, "R8": rep + tw - iss}
        neg = {"P": (rep < 0) | (div < 0) | (iss < 0), "R": (rep < 0) | (iss < 0)}
        neg["P8"], neg["R8"] = neg["P"] | (tw < 0), neg["R"] | (tw < 0)
    out = SimpleNamespace(r=r, p0=pp[0], p1=pp[1], p2=pp[2], kind=kind, e=np.where(kind > 0, e, -1), s=np.where(kind > 0, s, -1), has_ttm=has_ttm, rep=rep, div=div, iss=iss, tw=tw, comps=comps, sg=sg, Sv=Sv, a=a, fa=fa, fr=fr, cl=cl,
                          mv=mv, a3c=a3c, a3f=a3f, f_alone=(sg >= 0) & ~covered, stale_s=stale_s, stale_days=np.where(kind > 0, dr_i - e, -1), code={}, score={}, scored={}, flag={}, base_code=code.copy())
    for k in CODE_KEYS:
        c_, al = code.copy(), alive.copy()
        for msk, rs in [(neg[k], R_NEG_TTM)] + mv_fail:
            hit = al & msk
            c_[hit] = rs
            al[hit] = False
        with np.errstate(invalid="ignore", divide="ignore"):
            sc = num[k] / mv
            big = al & ~(np.abs(sc) <= SCORE_MAX)
        c_[big] = R_OVER50
        al[big] = False
        out.code[k], out.scored[k] = c_.astype(np.int8), al
        out.score[k] = np.where(al, sc, np.nan)
        with np.errstate(invalid="ignore"):
            out.flag[k] = al & (np.abs(np.where(al, sc, 0.0)) > FLAG)
    with np.errstate(invalid="ignore", divide="ignore"):
        out.score["DIV"] = np.where(out.scored["P"], div / mv, np.nan)                    # CHOICE: the dividend-only twin sorts P's scored names by DIV / MV (so it differs from P only by the sort)
        out.score["REPY"] = np.where(out.scored["R"], rep / mv, np.nan)                   # CHOICE: the gross repurchase yield deciles cut R's scored names by REP / MV
    bb.cache[r] = out
    return out


# ------------------------------------------------------------------ BEFORE ANY P&L: the score's counts and facts per rank, [B2] staleness, [B3] the tag blind spot, [B9] the zero rule among the picks
built_ranks = NI.built_ranks
SRC_KEYS = ("rep", "div", "tw")


def comp_use(sc, cols):
    """per name of `cols` (World columns with a TTM at the rank): what each component read over the TTM's periods (one for a FY, three for the year-to-date formula) -> {component: per-name bool arrays + the period counts}. REP / DIV / TW: 'first' = only
    the first concept on the periods that have a line, 'fallback' = only the fallback, 'mixed' = both across one TTM's periods, 'zero_all' = no line on any period (the zero rule everywhere), 'zero_any' = the zero rule on at least one period;
    ISS [B7]: the primary concept used ('first' / 'second' / 'third' alone, 'mixed' across the periods, 'plan_only' = the stock-plan concepts alone), 'plan' = a stock-plan concept summed, 'dedup' = the same-value rule fired, 'zero_all' / 'zero_any' =
    none of the seven on every / on some period"""
    out = {}
    valid = np.vstack([sc.comps[q]["rep_src"][cols] >= 0 for q in range(3)]) if len(cols) else np.zeros((3, 0), bool)
    for nm in SRC_KEYS:
        s_ = np.vstack([sc.comps[q][nm + "_src"][cols] for q in range(3)]) if len(cols) else np.zeros((3, 0), np.int8)
        h1, h2 = ((s_ == 1) & valid).any(axis=0), ((s_ == 2) & valid).any(axis=0)
        z = (s_ == 0) & valid
        out[nm] = {"first": h1 & ~h2, "fallback": h2 & ~h1, "mixed": h1 & h2, "zero_all": ~h1 & ~h2, "zero_any": z.any(axis=0), "periods": int(valid.sum()), "zero_periods": int(z.sum())}
    st = lambda key: np.vstack([sc.comps[q][key][cols] for q in range(3)]) if len(cols) else np.zeros((3, 0))
    pr, an, pl, dp = st("iss_prim"), st("iss_any").astype(bool), st("iss_plan"), st("iss_dup")
    used = [((pr == q_) & valid).any(axis=0) for q_ in (1, 2, 3)]
    nused = used[0].astype(int) + used[1].astype(int) + used[2].astype(int)
    z = valid & ~an
    out["iss"] = {"first": used[0] & (nused == 1), "second": used[1] & (nused == 1), "third": used[2] & (nused == 1), "mixed": nused > 1, "plan_only": (nused == 0) & (an & valid).any(axis=0), "plan": ((pl > 0) & valid).any(axis=0),
                  "dedup": ((dp > 0) & valid).any(axis=0), "zero_all": ~(an & valid).any(axis=0), "zero_any": z.any(axis=0), "periods": int(valid.sum()), "zero_periods": int(z.sum())}
    return out


def zero_any(sc, cols):
    """[B9] per name of `cols`: its ISSUANCE or its REPURCHASES came from the ZERO rule on any period of its TTM -> (either, REP, ISS) bool arrays"""
    cu = comp_use(sc, cols)
    return cu["rep"]["zero_any"] | cu["iss"]["zero_any"], cu["rep"]["zero_any"], cu["iss"]["zero_any"]


def score_report(W, ranks, values=True):
    """the pre-P&L record of every rank - the UNIVERSE at the fill session, before the pool and before [A13] (a second share class is a POOL-level reason, counted from the pool): per key of CODE_KEYS the scored names, the names lost to each
    no-score rule (the first reason), the |score| > 0.15 flags, the names with no score at |score| > 0.50 (LISTED by symbol), [B2] the scored names whose statement period ended more than 120 days before the rank, the scored names with a score > 0;
    the names with a TTM, built from a FY or by the year-to-date formula; per component the concept used and the periods read as ZERO (comp_use, over the names with a TTM - CHOICE: stale ones included, the prereg's 'STATEMENT fact'
    basis); the days from e to r of every name with a TTM, bucketed; [B3] the names with a TTM that read ZERO on all three components (the seven issuance concepts counted), by symbol. values=True also keeps the scored P / R values (the
    per-year percentiles: Stage A prints them, the dryload never does) -> [one dict per rank]"""
    rows = []
    syms = np.asarray(W.syms).astype(str)
    for r, f, _x in ranks:
        uni = np.flatnonzero(W.U[f])
        sc = score_rank(W, r)
        ht = uni[sc.has_ttm[uni]]
        cu = comp_use(sc, ht)
        blind = cu["rep"]["zero_all"] & cu["div"]["zero_all"] & cu["iss"]["zero_all"]
        sd = sc.stale_days[ht]
        b = STALE_BUCKETS
        rec = {"rank": f"{W.days[r]:%Y-%m-%d}", "year": int(W.days[f].year), "universe": int(len(uni)), "ttm": int(len(ht)), "ttm_fy": int((sc.kind[ht] == 1).sum()), "ttm_ytd": int((sc.kind[ht] == 2).sum()),
               "stale_buckets": [int((sd <= b[0]).sum())] + [int(((sd > lo) & (sd <= hi)).sum()) for lo, hi in zip(b[:-1], b[1:])] + [int((sd > b[-1]).sum())],
               "comp": {nm: {k: (int(v.sum()) if isinstance(v, np.ndarray) else v) for k, v in d.items()} for nm, d in cu.items()}, "blind_names": [str(q) for q in syms[ht[blind]]], "cells": {}}
        for k in CODE_KEYS:
            cd = sc.code[k][uni]
            cnt = np.bincount(cd.astype(np.int64), minlength=len(REASONS))
            s = sc.scored[k][uni]
            with np.errstate(invalid="ignore"):
                c = {"scored": int(cnt[0]), "reasons": {REASONS[q]: int(cnt[q]) for q in range(1, R_SECOND_CLASS)}, "flags": int(sc.flag[k][uni].sum()), "over50_names": [str(q) for q in syms[uni[cd == R_OVER50]]],
                     "stale120": int((s & (sc.stale_days[uni] > STALE_PRINT)).sum()), "positive": int((s & (np.nan_to_num(sc.score[k][uni]) > 0)).sum())}
            if values and k in CELLS:
                c["values"] = sc.score[k][uni][s]
            rec["cells"][k] = c
        rows.append(rec)
    return rows


def blind_spot(rows):
    """[B3] THE TAG BLIND SPOT per fill year from score_report's rows: the universe name-ranks with a TTM (CHOICE: the prereg's 'names that have a STATEMENT fact' read as the names whose TTM is built - the four quarters exist; the ranks of a year
    pooled), those reading ZERO on all three components over the TTM's periods, the share, whether it is above 10% and the names (symbol x ranks) -> {year: {...}}"""
    by = {}
    for rec in rows:
        d = by.setdefault(rec["year"], {"with_ttm": 0, "blind": 0, "names": Counter()})
        d["with_ttm"] += rec["ttm"]
        d["blind"] += len(rec["blind_names"])
        d["names"].update(rec["blind_names"])
    out = {}
    for y, d in sorted(by.items()):
        sh = d["blind"] / d["with_ttm"] if d["with_ttm"] else 0.0
        out[int(y)] = {"name_ranks_with_a_ttm": int(d["with_ttm"]), "blind_name_ranks": int(d["blind"]), "share": float(sh), "above": bool(sh > BLIND_MAX), "names": dict(sorted(d["names"].items()))}
    return out


def unscored_by_name(W, ranks):
    """the names with no score for a reason that is not about the rank - the map, NETISS's [A4] foreign filers, no cash-flow fact for the CIK, no share fact for the CIK - counted BY NAME (the ranks it is in the universe at; P's first reason, the same in every cell)
    -> {reason: {symbol: ranks}}"""
    out = defaultdict(Counter)
    syms = np.asarray(W.syms).astype(str)
    for r, f, _x in ranks:
        uni = np.flatnonzero(W.U[f])
        cd = score_rank(W, r).code["P"][uni]
        for q in STATIC_CODES:
            for s_ in syms[uni[cd == q]]:
                out[REASONS[q]][str(s_)] += 1
    return {k: dict(v) for k, v in out.items()}


def print_unscored_by_name(by):
    print("  names with no score whatever the rank, LISTED by name (symbol x the ranks it is in the universe at; the same in every cell):")
    for reason in REASONS[1:]:
        if reason in by:
            print(f"    {REASON_TEXT[reason]} - {len(by[reason])} names: " + ", ".join(f"{s} x{n}" for s, n in sorted(by[reason].items())))


def lst_names(L, names=True):
    """failing name-ranks [(symbol, rank)] counted and - with names - LISTED BY NAME: every name once with the ranks it fails and its first and last one"""
    by = defaultdict(list)
    for q, d in sorted(L):
        by[q].append(d)
    head = f"{len(L)} name-ranks on {len(by)} names"
    if not L or not names:
        return head
    return head + " - " + "; ".join(f"{q} x{len(ds)} ({ds[0]}" + (f" .. {ds[-1]})" if len(ds) > 1 else ")") for q, ds in sorted(by.items()))


def print_score_report(rows, names=True):
    """BEFORE ANY P&L, in the prereg's order: the scored names per rank and cell, the names lost to each no-score rule, the |score| > 0.50 names (LISTED with names=True, counted otherwise), the TTMs built from a FY vs the year-to-date formula per year, per
    component the concept used and the share of periods read as ZERO, the median and 5th / 95th percentiles of P and R per year and the share with R > 0 (only when the values are kept: the dryload keeps none), the |score| > 0.15 flags per rank,
    the days from e to r per year and [B2]'s 120-day share; [B3] is printed by print_blind_spot"""
    print("BEFORE ANY P&L - the payout score: the universe at the fill session, the names with a TTM and the scored names of each cell (P / R, and [B8]'s twins P8 / R8), by rank")
    for k in CELLS:
        first = next((rec["rank"] for rec in rows if rec["cells"][k]["scored"] > 0), None)
        print(f"  {k} coverage: the first rank with any scored name {first}")
    print("  per rank (rank date: universe / with a TTM (from a FY + by the year-to-date formula) / scored P / R / P8 / R8 | |score| > 0.15 flags P / R / P8 / R8, listed for the hand audit, never a filter):")
    for rec in rows:
        print(f"    {rec['rank']}: {rec['universe']} / {rec['ttm']} ({rec['ttm_fy']} + {rec['ttm_ytd']}) / " + " / ".join(str(rec["cells"][k]["scored"]) for k in CODE_KEYS) + " | " + " / ".join(str(rec["cells"][k]["flags"]) for k in CODE_KEYS))
    print("  names lost to each no-score rule, by rank (counts of universe names, the first reason of each; the map / foreign / no-cash-flow reasons are static - every rank's):")
    for k in CODE_KEYS:
        print(f"  {k}: " + "; ".join(f"{rec['rank']}: " + ", ".join(f"{q} {v}" for q, v in rec["cells"][k]["reasons"].items() if v) for rec in rows))
    for k in CODE_KEYS:
        o50 = sorted({(q, rec["rank"]) for rec in rows for q in rec["cells"][k]["over50_names"]})
        print(f"  {k} no score at |score| > {SCORE_MAX:.2f} (half the firm's value in a year: a unit / scale error or a deal) and {'LISTED' if names else 'counted'}: {lst_names(o50, names)}")
    byy = defaultdict(list)
    for rec in rows:
        byy[rec["year"]].append(rec)
    print("  the TTMs built per fill year (name-ranks with a TTM: from a FY / by the year-to-date formula YTD + FY_prev - YTD_prev): " + "; ".join(f"{y}: {sum(r_['ttm_fy'] for r_ in v):,} / {sum(r_['ttm_ytd'] for r_ in v):,}" for y, v in sorted(byy.items())))
    for nm, lab, kk in (("rep", "REPURCHASES (first / fallback / the two mixed across one TTM's periods / no line on any period)", ("first", "fallback", "mixed", "zero_all")), ("div", "DIVIDENDS (first / fallback / mixed / no line)", ("first", "fallback", "mixed", "zero_all")),
                        ("iss", "ISSUANCE [B7] (primary used: first / second / third / mixed / stock-plan concepts alone / none of the seven; names with a stock-plan concept summed / with the same-value rule fired)", ("first", "second", "third", "mixed", "plan_only", "zero_all", "plan", "dedup")),
                        ("tw", "[B8] TAX WITHHOLDING, the twins' addition (present / no line)", ("first", "zero_all"))):
        print(f"  concept used, {lab}, per fill year, name-ranks with a TTM; and the share of the TTM's periods read as ZERO: " + "; ".join(
            f"{y}: " + " / ".join(f"{sum(r_['comp'][nm][k_] for r_ in v):,}" for k_ in kk) + f", ZERO periods {sum(r_['comp'][nm]['zero_periods'] for r_ in v) / max(sum(r_['comp'][nm]['periods'] for r_ in v), 1):.1%}" for y, v in sorted(byy.items())))
    if rows and "values" in rows[0]["cells"][CELLS[0]]:
        for k in CELLS:
            print(f"  {k} per fill year (scored names pooled over the year's ranks: n, 5th / median / 95th percentile; the share with a score > 0" + (" - R > 0: net repurchasers" if k == "R" else "") + "): " + "; ".join(
                f"{y}: {sum(len(r_['cells'][k]['values']) for r_ in v):,}, " + " / ".join(f"{q:+.4f}" for q in pctl_text(np.concatenate([r_["cells"][k]["values"] for r_ in v]))) + f", {sum(r_['cells'][k]['positive'] for r_ in v) / max(sum(r_['cells'][k]['scored'] for r_ in v), 1):.0%}"
                for y, v in sorted(byy.items()) if sum(len(r_["cells"][k]["values"]) for r_ in v)))
    for k in CODE_KEYS:
        tot = sum(rec["cells"][k]["scored"] for rec in rows)
        print(f"  {k} over every rank: {tot:,} scored name-ranks; {sum(rec['cells'][k]['flags'] for rec in rows):,} |score| > 0.15 flags (the audit flag: listed per rank, never a filter)")
    b = STALE_BUCKETS
    print(f"  STALENESS - the days from the statement period's end e to the rank close r, per fill year (name-ranks with a TTM: up to {b[0]} / {b[0] + 1}-{b[1]} / {b[1] + 1}-{b[2]} / over {b[2]} days - the last is the no-score rule): " + "; ".join(
        f"{y}: " + " / ".join(f"{sum(r_['stale_buckets'][q] for r_ in v):,}" for q in range(len(b) + 1)) for y, v in sorted(byy.items())))
    print(f"  [B2] the share of SCORED names whose statement period ended more than {STALE_PRINT} days before the rank close (a quarterly filer's normal ceiling), per fill year: " + "; ".join(
        f"{y}: " + " / ".join(f"{k} {sum(r_['cells'][k]['stale120'] for r_ in v) / max(sum(r_['cells'][k]['scored'] for r_ in v), 1):.1%}" for k in CELLS) for y, v in sorted(byy.items())))
    print(f"  [B17] STALE S - the names whose share count S (the latest usable cover-page count, else the balance sheet's, at its first-filed value) is as of more than {S_MONTHS} calendar months before the rank close: UNSCORED, "
          "per fill year (name-ranks whose first no-score reason it is, P / R, of the universe name-ranks; per rank in the reason counts above): " + "; ".join(
        f"{y}: {sum(r_['cells']['P']['reasons']['stale_s'] for r_ in v):,} / {sum(r_['cells']['R']['reasons']['stale_s'] for r_ in v):,} of {sum(r_['universe'] for r_ in v):,}" for y, v in sorted(byy.items())))


def print_blind_spot(b3):
    """[B3] per fill year: the name-ranks with a TTM that read ZERO on all three components (the seven issuance concepts counted) and the share; a year above 10% is named with its names (symbols only)"""
    print("  [B3] THE TAG BLIND SPOT per fill year (universe name-ranks with a TTM that read ZERO on all three components over the TTM's periods - none of the two repurchase, two dividend and seven issuance concepts on any period - / the name-ranks with a TTM): "
          + "; ".join(f"{y}: {d['blind_name_ranks']:,} / {d['name_ranks_with_a_ttm']:,} ({d['share']:.1%})" for y, d in b3.items()) + f"; above {BLIND_MAX:.0%} in: " + (", ".join(str(y) for y, d in b3.items() if d["above"]) or "no year"))
    for y, d in b3.items():
        if d["above"]:
            print(f"  [B3] {y}: {d['share']:.1%} of the name-ranks with a TTM read ZERO everywhere - ABOVE {BLIND_MAX:.0%}: the zero-reading rule is suspect and Stage A waits for MANAGER's ruling; that year's {len(d['names'])} names: "
                  + ", ".join(f"{s} x{n}" for s, n in d["names"].items()))


def b9_rows(W, L):
    """[B9] per rank and cell: the PICKED names (both sides) and those whose ISSUANCE or REPURCHASES on any period of the TTM came from the zero rule (and of them ISS / REP)"""
    rows = []
    for rec in L.recs:
        ent = {"rank": f"{W.days[rec.r]:%Y-%m-%d}", "cells": {}}
        for c in CELLS:
            cc = rec.cell[c]
            if not cc.traded:
                ent["cells"][c] = None
                continue
            cols = rec.pool[cc.idx[np.r_[cc.long, cc.short]]]
            z, zr, zi = zero_any(rec.sc, cols)
            ent["cells"][c] = {"picked": int(len(cols)), "zero": int(z.sum()), "zero_rep": int(zr.sum()), "zero_iss": int(zi.sum())}
        rows.append(ent)
    return rows


def split_no_factor_move(W, f, x, j):
    """[B19] r17_resmom_restate.no_factor_move for one name, with its sessions: the calendar split ex-dates t in f < t <= x on which the vendor's split factor does not move (no registered split flag and |F_t / F_(t-1) - 1| <= 1%, a
    missing factor included) - a split the split-safe series may carry as a move -> [(t, F_t / F_(t-1))]"""
    out = []
    for t in (np.flatnonzero(np.asarray(W.CSPL[f + 1:x + 1, j])) + f + 1).tolist():
        with np.errstate(invalid="ignore", divide="ignore"):
            mv = float(W.F[t, j] / W.F[t - 1, j])
        if not (bool(W.chg[t, j]) or bool(abs(mv - 1.0) > 0.01)):
            out.append((int(t), mv))
    return out


def b19_rows(W, L):
    """[B19] BEFORE ANY P&L (after the picks): every PICKED position - the cells' and the twins' picks (P, R, DIV, P8, R8, FLAT) - with a calendar split inside its hold that the vendor's factor does not show (split_no_factor_move), one row per
    name-month and ex-date: symbol, rank, fill (the audit file's key), exit, ex-date, the calendar's split ratio (new : old, W.bb.split_ratio; 'n/a' where the calendar row is not at hand), the factor's move F_t / F_(t-1) on the ex-date, the
    keys / sides that picked it"""
    ratio = getattr(W.bb, "split_ratio", None) or {}
    rows = []
    for rec in L.recs:
        by = defaultdict(list)
        for k in TRADED:
            cc = rec.cell[k]
            if cc.traded:
                for sd, sel in (("long", cc.long), ("short", cc.short)):
                    for j in rec.pool[cc.idx[sel]].tolist():
                        by[int(j)].append(f"{k} {sd}")
        for j in sorted(by):
            for t, mv in split_no_factor_move(W, rec.f, rec.x, j):
                sym, ex = str(W.syms[j]), f"{W.days[t]:%Y-%m-%d}"
                rows.append({"symbol": sym, "rank": f"{W.days[rec.r]:%Y-%m-%d}", "fill": f"{W.days[rec.f]:%Y-%m-%d}", "exit": f"{W.days[rec.x]:%Y-%m-%d}", "ex_date": ex, "split_ratio": ratio.get((sym, ex), "n/a"),
                             "factor_move": mv, "picked_by": by[j]})
    return rows


def print_b19(rows):
    print("[B19] BEFORE ANY P&L - every PICKED position (the cells' and the twins' picks) with a calendar split inside its hold that the vendor's split factor does not show (no registered split and |F_t / F_(t-1) - 1| <= 1% on the ex-date: the "
          "split-safe path may carry it as a move; each goes to the hand audit (f) as a data-event candidate): " + (f"{len(rows)} position(s)" if rows else "none"))
    for r_ in rows:
        print(f"  {r_['symbol']} rank {r_['rank']} (fill {r_['fill']}, exit {r_['exit']}): calendar split ex-date {r_['ex_date']}, ratio {r_['split_ratio']}, the factor's move F_t / F_(t-1) = {r_['factor_move']:.4f}; picked by "
              + ", ".join(r_["picked_by"]))


def b19_candidate_rows(W, L, rows):
    """[B19] the listed positions as rows of buyback_audit_candidates.csv - list 'b19_split_no_factor_move', data_event_candidate True, the cell = the first picking key's cell (the twins' parents: DIV / P8 -> P, R8 / FLAT -> R; a cell is a
    label - a data event belongs to the name-month and its group), the key of the audit file (symbol + FILL date) and bb_fields"""
    parent = {"P": "P", "DIV": "P", "P8": "P", "R": "R", "R8": "R", "FLAT": "R"}
    by_r = {f"{W.days[rec.r]:%Y-%m-%d}": rec for rec in L.recs}
    out = []
    for r_ in rows:
        rec = by_r[r_["rank"]]
        cell = parent[r_["picked_by"][0].split()[0]]
        out.append({"list": "b19_split_no_factor_move", "data_event_candidate": True, "symbol": r_["symbol"], "date": r_["fill"], "exit": r_["exit"], "cell": cell, "side": r_["picked_by"][0].split()[1], "ex_date": r_["ex_date"],
                    "split_ratio": r_["split_ratio"], "factor_move": r_["factor_move"], "picked_by": "; ".join(r_["picked_by"]), **bb_fields(W, rec.r, int(pd.Index(W.syms).get_loc(r_["symbol"])), cell)})
    return out


def split_ratios(path, sha, cut):
    """[B19] the calendar's split ratios (new_rate : old_rate of r16_xgap's flat CSV - r17_resmom's loader keeps only symbol / ex-date / type) from the registered wide calendar wide_load has just checked (refused unless its sha256 is still
    the one given): {(symbol, 'YYYY-MM-DD'): 'new:old'} for the forward / reverse / unit split rows with an ex-date before the cut"""
    if M17.sha_raw(path) != sha:
        refuse(f"refused: {os.path.basename(path)} changed after wide_load checked it {TAIL}")
    df = pd.read_csv(path, dtype=str, keep_default_na=False, usecols=["type", "symbol", "ex_date", "new_rate", "old_rate"])
    df = df[df["type"].str.strip().isin(M17.SPLIT_TYPES)]
    ex = pd.to_datetime(df["ex_date"].str.strip().replace("", np.nan), errors="coerce")
    k = (ex.notna() & (ex < TS(cut))).to_numpy()
    return {(s_.strip(), f"{e_:%Y-%m-%d}"): f"{n_.strip()}:{o_.strip()}" for s_, e_, n_, o_ in zip(df["symbol"][k], ex[k], df["new_rate"][k], df["old_rate"][k])}


def print_b9(rows):
    print("[B9] BEFORE ANY RETURN - the share of the PICKED names (longs and shorts) whose ISSUANCE or REPURCHASES on any period of the TTM came from the zero rule, per rank (rank: share (names picked; of them ISSUANCE zero / REPURCHASES zero)):")
    for c in CELLS:
        xs = [(e["rank"], e["cells"][c]) for e in rows if e["cells"][c]]
        tot, z = sum(x["picked"] for _r, x in xs), sum(x["zero"] for _r, x in xs)
        print(f"  {c}: " + ("; ".join(f"{r_}: {x['zero'] / x['picked']:.0%} ({x['picked']}; {x['zero_iss']} / {x['zero_rep']})" for r_, x in xs) if xs else "no traded rank") + (f" - over every traded rank {z / tot:.1%} of {tot:,} picked name-ranks" if tot else ""))


def print_data_counts(src, W=None):
    """[B6] / [B7] COUNTS of the two pinned cash-flow extracts as read - the rows per extract and per concept (the exact us-gaap names present, rows and CIKs), the drops, the forms, the entries and the periods - then NETISS's pinned map and share-count files
    (r21_netiss's print) and, with a World, the names by their static reason; no cash amount, share count or value of any kind"""
    fi, ci = src.cinfo, src.cash.info
    print(f"[B6] / [B7] the two pinned cash-flow extracts (each refused if its sha256 differs; read as ONE table, a fact present in both refused): {FILE_SHA['cf'][:16]}... ({fi['files']['cf']:,} rows) + {FILE_SHA['cf_alt'][:16]}... ({fi['files']['cf_alt']:,} rows)")
    print(f"  cash-flow rows read {fi['rows_read']:,}; dropped at their first reason: another concept {fi['rows_other_concept']:,}, unit not USD {fi['rows_unit_not_usd']:,}, unreadable date {fi['rows_unreadable_date']:,}, start after end {fi['rows_start_after_end']:,}, "
          f"filed on / after the cut {fi['rows_filed_on_or_after_the_cut']:,} (the extracts hold none), period end on / after the cut {fi['rows_end_on_or_after_the_cut']:,}; value missing {fi['rows_value_missing']:,} (kept: the entry is unusable); kept {fi['rows']:,} "
          f"(by extract {fi['rows_by_extract']}) on {fi['ciks']:,} CIKs, filed {fi['filed_range']}")
    print("  the concepts as read (rows / CIKs; the exact names - a concept the harness reads that the extracts do not hold shows 0):")
    for con in CONCEPTS:
        print(f"    {con}: {fi['rows_by_concept'].get(con, 0):,} / {fi['ciks_by_concept'].get(con, 0):,}")
    print(f"  forms (the 15 largest): {fi['rows_by_form']}")
    print(f"  entries (cik, concept, start, end; the first filed row's value): {ci['entries']:,}; ambiguous at the first filed date {ci['ambiguous']:,}; period ending after its own first filing {ci['end_after_filed']:,}; value missing {ci['value_missing']:,}; "
          f"a NEGATIVE component value (unusable) {ci['negative_component_value']:,}; usable {ci['usable']:,}; with two or more rows {ci['entries_with_two_or_more_rows']:,}, of them a later filing carries another value {ci['later_filing_carries_another_value']:,} (the first filed stands)")
    print(f"  periods (cik, start, end): {ci['periods']:,} by type (length end - start: Q 77-105, H 168-196, 9M 259-287, FY 350-380 days) {ci['periods_by_type']}; CIKs with a cash-flow entry {ci['ciks']:,}")
    NI.print_data_counts(src.mp, src.xinfo, src.fx, None)
    if W is not None:
        st = Counter(REASONS[int(c)] for c in W.bb.static)
        print(f"  the {W.S:,} names ever in the universe by their static reason (the map, NETISS's [A4] foreign filers, no cash-flow fact for the CIK; a CIK without a share fact is a market-value reason, attributed at the rank): "
              + ", ".join(f"{k} {v:,}" for k, v in sorted(st.items(), key=lambda kv: -kv[1])) + f"; mapped CIKs without a share fact {int(W.bb.no_shares.sum()):,}")


# ------------------------------------------------------------------ the sides: the 50 HIGHEST long, the 50 LOWEST short; fewer than 150 scored names -> the top / bottom third, at least 20 a side, else nothing
TRADED = CELLS + TWINS                       # every key that picks sides (REPY's deciles never trade)
DEC_KEYS = CELLS + (DECK,)                   # the keys cut into ten score deciles each rank


def side_n(n):
    """the names a side when n names are scored (after [A13]): 50 at 150 or more; fewer: the top / bottom THIRD (n // 3 a side, so the sides never touch - NETISS [A15]'s reading of 'the top / bottom third') when that is at least 20, else
    nothing -> (names a side, 'top' | 'third' | 'none')"""
    if n >= SPEC["min_scored"]:
        return M17.SPEC["n_side"], "top"
    k = n // 3
    return (k, "third") if k >= SPEC["min_side"] else (0, "none")


def flat_n(n):
    """the FLAT twin's side size: the top / bottom THIRD of its names (n // 3 a side; CHOICE: always the thirds, the prereg's 'top / bottom third', never the 50 of the cells), at least 20 a side, else nothing"""
    k = n // 3
    return (k, "third") if k >= SPEC["flat_min"] else (0, "none")


def pick_sides(cols, score, k):
    """RESMOM's tie convention (r17_resmom.rm_one): one ascending order by (score, symbol order); the shorts are its first k (the k LOWEST - the biggest net raisers; a tie goes to the lower symbol), the longs its last k (the k HIGHEST - the biggest
    net payers; a tie goes to the higher symbol); disjoint when 2k <= n -> (long positions, short positions) into the arrays given"""
    o = np.lexsort((np.asarray(cols), np.asarray(score, float)))
    return o[::-1][:k], o[:k]


decile_labels = NI.decile_labels             # ten equal-count deciles, 0 = the lowest score (the biggest net raisers) .. 9 = the highest (the biggest net payers); ties by symbol order; the remainder to the first deciles


# ------------------------------------------------------------------ one rebalance: RESMOM's pool (NETISS's judged reading), the BUYBACK scores, the picks of the cells and the twins
def pool_units(W, f, x, pool, naive, close=None):
    """the unit paths of the whole pool: r17_resmom.rm_units (r15's split-safe paths, the names flagged `naive` on the raw series, + [R1] the cash dividends) and [B13] the close rows (bb_one's rec.close, -1 = held to the exit): a pool
    name with a spin-off / stock-dividend ex-date e in f < e <= x is CLOSED at the official close of e-1 (r17_resmom.close_units: no mark, no dividend whose ex-date is e or later and no borrow after it; the exit value that close - none
    on e-1: the last mark, stopped printing there; U.xc = the exit column, where r17_resmom.l1_pnl_x books the exit cost). The recount's twins are brute_pos / brute_rec"""
    return M17.rm_units(W, f, x, pool, naive, close)


def bb_one(W, r, f, x, post_mode, units=True, counts_only=False):
    """one rebalance: the universe at the fill session f (sessions < f only) and the pool of r21_netiss's ni_one - the same removals in the same order and the SAME post_mode branches (short history, no ES pairs, no fill, the pre / old / post
    hygiene windows, the spin-off / stock-dividend ex-dates, the hand audit; 'remove' = the leaky reading, 'naive' = the look-ahead one, 'keep' = [B10]'s removal reading, REPORTED since [B13] (a name flagged inside the hold stays on the
    split-safe path, an announced (calendar) split or a spin-off / stock-dividend ex-date in f < t <= x removes it), 'close' = [B13] the JUDGED reading, MANAGER's hygiene edit S1 (r17_resmom's post_mode 'close', r21's [A22]): no in-hold
    event removes a name - flagged names and splits stay on the split-safe path - and a spin-off / stock-dividend ex-date e in f < e <= x closes the position at the official close of e-1 (rec.close = that row per pool name, -1 = held to the
    exit; pool_units cuts the path; counted: kept_<reason>, kept_flagged, kept_calendar_split, closed_spin); another post_mode is refused) - one pool for every cell, twin and null. Per score (P, R, [B8] P8 / R8) its scored names are
    the pool names with a score, [A13] less the second share classes (NETISS's share_classes: of two names on one CIK only the more liquid keeps its score, per score and rank); the sides by side_n, the 50 HIGHEST long and the 50 LOWEST short;
    the dividend-only twin on P's scored names by DIV / MV (CHOICE); the FLAT twin on R's scored names whose NETISS one-year ISS (N12's, the same rank close) is within +-2% (CHOICE: ln 0.98 <= ISS_1 <= ln 1.02), the thirds, at least 20 a
    side; the deciles of P, R and REP / MV (CHOICE: on R's scored names). counts_only: no unit path, no pick (the dryload)"""
    if post_mode not in M17.POST_MODES:
        raise ValueError(f"post_mode {post_mode!r}: one of {M17.POST_MODES}")
    s = M17.SPEC
    uni = np.flatnonzero(W.U[f])
    rec = SimpleNamespace(r=r, f=f, x=x, nu=len(uni), nfull=0, traded=False, pool=np.zeros(0, np.int64), naive=np.zeros(0, bool), spin_win=np.zeros(0, np.int64), spin_hold=np.zeros(0, bool), cell={k: NI.cell0() for k in KEYS}, sc=None, U=None,
                          close=np.zeros(0, np.int64))
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
    pre = W.hyg(lo_pre, r, uni)                                                 # all four reasons, sessions r-25 .. r
    old = W.hyg(a, lo_pre - 1, uni)[1:]                                         # gap, tbis, jump on sessions r-251 .. r-26
    post = W.hyg(r + 1, x, uni)                                                 # all four, inside the hold
    post_sp = M17.spn_hit(W, f + 1, x, uni)                                     # a spin-off / stock-dividend ex-date in f < t <= x (the fill session's own is bought ex; the exit session's is inside)
    post_cs = M17.csplit_hit(W, f + 1, x, uni) if post_mode == "keep" or (post_mode == "close" and getattr(W, "cscs", None) is not None) else np.zeros(len(uni), bool)     # [B10] an announced (calendar) split ex-date in f < t <= x ([B13]: counted, never a removal)
    win = (W.SPN[a:r + 1][:, uni] & np.isfinite(W.Rn[a:r + 1][:, uni])).sum(axis=0)
    pre_any, old_any, post_any = pre.any(axis=0), old.any(axis=0), post.any(axis=0) | post_sp
    aud = W.aud1[f, uni]
    W.aud_hit.update((AUD, f, int(c)) for c in uni[aud])
    reasons = [("short_history", short_hist), ("no_es_pairs", no_es), ("no_fill", ~m_fill)]
    reasons += [(f"pre_{h}", pre[q]) for q, h in enumerate(HYG)] + [(f"old_{h}", old[q]) for q, h in enumerate(HYG[1:])]
    if post_mode == "remove":
        reasons += [(f"post_{h}", post[q]) for q, h in enumerate(HYG)] + [("post_spin", post_sp)]
    elif post_mode == "keep":                                                   # [B10]'s removal reading (a report since [B13]): an announced split or a spin-off / stock-dividend ex-date inside the hold removes a name
        reasons += [("post_calendar_split", post_cs), ("post_spin", post_sp)]
    D15.tally(cnt, reasons + [("audit", aud)], D15.attribute(reasons + [("audit", aud)], len(uni)))
    cnt["spin_window_names"] += int((win > 0).sum())
    cnt["spin_window_sessions"] += int(win.sum())
    cnt["spin_hold_names"] += int(post_sp.sum())
    pool_k = ~short_hist & ~no_es & m_fill & ~pre_any & ~old_any & ~aud
    pool = (pool_k & ~post_any) if post_mode == "remove" else (pool_k & ~post_cs & ~post_sp) if post_mode == "keep" else pool_k
    if post_mode == "naive":
        cnt["kept_naive"] += int((pool & post_any).sum())
    if post_mode in ("keep", "close"):                                          # [B10] / [B13] the names flagged inside the hold that stay, on the split-safe path, per reason
        for q, h in enumerate(HYG):
            cnt[f"kept_{h}"] += int((pool & post[q]).sum())
        cnt["kept_flagged"] += int((pool & post.any(axis=0)).sum())
    if post_mode == "close":                                                    # [B13] the calendar's splits ride the split-safe path; a spin-off / stock-dividend ex-date inside the hold closes the position at the close before it
        cnt["kept_calendar_split"] += int((pool & post_cs).sum())
        cnt["closed_spin"] += int((pool & post_sp).sum())
    pidx = np.flatnonzero(pool)
    cols = uni[pidx]
    rec.pool = cols
    rec.naive = post_any[pidx] if post_mode == "naive" else np.zeros(len(pidx), bool)
    rec.spin_win, rec.spin_hold = win[pidx], post_sp[pidx]
    rec.close = np.full(len(pidx), -1, np.int64)                                 # [B13] the row each pool name closes on: the session before its first spin-off / stock-dividend ex-date in f < e <= x (-1 = held to the exit session)
    if post_mode == "close" and x > f and len(pidx):
        sp_h = W.SPN[f + 1:x + 1][:, cols]
        rec.close = np.where(sp_h.any(axis=0), f + sp_h.argmax(axis=0), -1).astype(np.int64)
    rec.sc = sc = score_rank(W, r)
    if not len(cols):
        for k in TRADED:
            cnt[f"mode_{k}_none"] += 1                                          # an empty pool trades nothing (counted with the other fallback months)
        return rec, cnt
    for k in CODE_KEYS:
        cc = rec.cell[k]
        idx0 = np.flatnonzero(sc.scored[k][cols])
        keep, cc.second, cc.kept, nan_dv = NI.share_classes(W, f, cols, idx0)   # [A13] one share class per firm: among the pool names WITH this score only the more liquid class keeps it
        idx = idx0[keep]
        cc.n_pre, cc.idx, cc.n, cc.score = int(len(idx0)), idx, int(len(idx)), sc.score[k][cols][idx]
        cnt[f"scored_{k}"] += cc.n
        cnt[f"no_score_{k}"] += int(len(cols) - cc.n)
        cd = sc.code[k][cols]
        for q in range(1, R_SECOND_CLASS):
            cnt[f"ns_{k}_{REASONS[q]}"] += int((cd == q).sum())
        cnt[f"ns_{k}_{REASONS[R_SECOND_CLASS]}"] += int(len(cc.second))
        cnt[f"nan_dv_{k}"] += nan_dv
        cc.k, cc.mode = side_n(cc.n)
    P, R = rec.cell["P"], rec.cell["R"]
    for k, base in (("DIV", P), (DECK, R)):                                      # CHOICE: the dividend-only twin sorts P's scored names by DIV / MV; the gross repurchase yield deciles cut R's by REP / MV
        cc = rec.cell[k]
        cc.idx, cc.n, cc.n_pre, cc.score = base.idx, base.n, base.n, sc.score[k][cols][base.idx]
        cc.k, cc.mode = side_n(cc.n) if k == "DIV" else (0, "none")
    iss1 = NI.score_rank(W, r)["N12"].iss[cols][R.idx]                          # the FLAT twin: NETISS's one-year ISS at the same rank close (NaN where NETISS has no score)
    with np.errstate(invalid="ignore"):
        flat = (iss1 >= FLAT_LO) & (iss1 <= FLAT_HI)
    cc = rec.cell["FLAT"]
    cc.idx, cc.score = R.idx[flat], R.score[flat]
    cc.n = cc.n_pre = int(len(cc.idx))
    cc.k, cc.mode = flat_n(cc.n)
    cnt["scored_FLAT"] += cc.n
    for k in TRADED:
        cnt[f"mode_{k}_{rec.cell[k].mode}"] += 1
    for k in DEC_KEYS:
        cc = rec.cell[k]
        if cc.n >= SPEC["dec_min"]:
            cnt[f"dec_{k}"] += 1
            if not counts_only:
                cc.dec = decile_labels(cols[cc.idx], cc.score)
        else:
            cnt[f"dec_none_{k}"] += 1
    if counts_only:
        for k in TRADED:
            rec.cell[k].traded = rec.cell[k].k > 0
        rec.traded = any(rec.cell[c].traded for c in CELLS)
        return rec, cnt
    for k in TRADED:
        cc = rec.cell[k]
        if cc.k > 0:
            cc.long, cc.short = pick_sides(cols[cc.idx], cc.score, cc.k)      # the k HIGHEST are the longs, the k LOWEST the shorts
            cc.traded = True
    rec.traded = any(rec.cell[c].traded for c in CELLS)
    if units and any(cc.traded or cc.dec is not None for cc in rec.cell.values()):
        rec.U = pool_units(W, f, x, rec.pool, rec.naive, rec.close)
        for cc in rec.cell.values():
            if cc.traded or cc.dec is not None:
                cc.U = NI.slice_units(rec.U, cc.idx)                            # (r21_netiss's slice carries U.xc: every cut path of the cells, the twins, the deciles and the null exits on its close's row)
    return rec, cnt


def bb_build(W, lo, hi, post_mode=JUDGED, units=True, counts_only=False):
    """every rebalance whose position EXITS inside [lo, hi] with a full 252-session window (r17_resmom.rm_build's rules: the stretch by exit session, warm-up counted, a position whose exit is past the stage's data unresolved - out of the cells AND
    the null) -> Leg(kind, recs, cnt by fill year)"""
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
        rec, c = bb_one(W, r, f, x, post_mode, units, counts_only)
        recs.append(rec)
        cnt[y].update(c)
    return SimpleNamespace(kind="BB", recs=recs, cnt=cnt)


cell_leg = NI.cell_leg                       # one key's view of a Leg in the shape r15's L1 engine and r17_resmom.run_cell read


def second_classes(L, W):
    """[A13] NETISS's count of what the one-share-class rule did, on this family's two cells"""
    with patched(NI, CELLS=CELLS):
        return NI.second_class_summary(L, W)


def print_second_classes(sm):
    with patched(NI, CELLS=CELLS):
        NI.print_second_classes(sm)


# ------------------------------------------------------------------ the null: RANDOM NAMES from each rebalance's eligible SCORED pool (r21_netiss's draw, this family's seed and cells)
def bb_null(W, L, nreps, vcode=0):
    """the registered null [prereg NULL]: r21_netiss.ni_null on this family's two cells and seed - per draw and per rebalance a cell traded, its k longs and k shorts are replaced by the same number of names drawn uniformly without replacement
    from that rebalance's eligible SCORED pool (the cell's scored names, [A13]'s second classes out; the same hygiene, sizing, fills, costs, borrow), one random stream per cell ([20261024, cell, vcode]). [B13]: the same pool with the same
    cut paths - the cells' unit paths (U.xc carried by the slice) through r17_resmom.l1_pnl_x, so a drawn name closed before its ex-date exits on its close's row -> {cell: (nreps, T)}"""
    with patched(NI, CELLS=CELLS, SEED=SEED):
        return NI.ni_null(W, L, nreps, vcode)


def null_summary(pc, pdo=None):
    """per cell the ROC @ $30k (and the DO against the REFERENCE book's drawdown days) of every draw -> the statistic = the MAX over the 2 cells per draw -> p5 / p50 / p95 (r21_netiss's)"""
    with patched(NI, CELLS=CELLS):
        return NI.null_summary(pc, pdo, SEED)


# ------------------------------------------------------------------ the statistics, the judge, A2 over the reference, the gate, the beta credit rule, dollars a year, DD5
stat_run, years_held, dd5_rec, dd5_txt, beta_credit, gate70 = NI.stat_run, NI.years_held, NI.dd5_rec, NI.dd5_txt, NI.beta_credit, NI.gate70


def judge_cell(st, net10, nul, n_years):
    """(a) >= 60 monthly rebalances traded; (b) WF ROC @ $30k >= 15 and net > 0 at 5 AND at 10 bps a side; (c) WF ROC above the null's 95th percentile (the MAX over the 2 cells); (d) positive in at least TWO THIRDS, rounded up, of the
    July-June WF years the cell holds positions in (NETISS [A15]'s reading) and net > 0 without Feb 15 - Apr 30 2020; (e) profitable without its best 1% of days AND without its best 1% of name-months. (f), the hand audit, is separate (the
    lead's). A NaN fails every comparison it enters"""
    R = RULES
    need = -(-2 * int(n_years) // 3)
    chk = {f"rebalances>={R['reb']}": st["n_units"] >= R["reb"], f"ROC>={R['roc']:g}": st["roc"] >= R["roc"], "net>0 at 5 bps": (st["net"] > 0) if R["net_pos"] else True,
           "net>0 at 10 bps": (net10 > 0) if R["stress"] else True, "ROC>null p95": (st["roc"] > nul["roc_max"]["p95"]) if R["null"] else True,
           f"positive in >={need} of {int(n_years)} July-June years": st["years_pos"] >= need, "net>0 without Feb 15 - Apr 30 2020": (st["net_ex2020"] > 0) if R["ex2020"] else True,
           "profitable without its best 1% of days": (st["net_ex_best_days"] > 0) if R["exbest"] else True,
           "profitable without its best 1% of name-months": (st["net_ex_best_pos"] > 0) if R["exbest"] else True}
    return {k: bool(v) for k, v in chk.items()}


def first_fill(W, L, key):
    """the first TRADED fill session of a key in a leg (a Timestamp), None when it never trades"""
    f = [rec.f for rec in L.recs if rec.cell[key].traded]
    return W.days[min(f)] if f else None


def first_scored(W, L, key):
    """the first rank with a scored name of a key in a leg ('YYYY-MM-DD'), None when there is none"""
    r = [rec.r for rec in L.recs if rec.cell[key].n > 0]
    return f"{W.days[min(r)]:%Y-%m-%d}" if r else None


def a2_window(d0):
    """A2's window for c: 'the cell's first 24 months of traded fills' = its first traded fill's date .. + 24 months - 1 day (CHOICE: calendar months, the rows of #463's index in it; never before the WF's start; a cell that never trades gets the
    WF's first 24 months - it holds nothing there, so it has no c)"""
    lo = WF0 if d0 is None else max(TS(d0).normalize(), WF0)
    return lo, lo + pd.DateOffset(months=A2_MONTHS) - pd.Timedelta(days=1)


def a2_report(B, xB, ref, win):
    """STAGE A2 (WF) - a REPORT, never a pass route: the REFERENCE book L = #463 + 0.264 x RES (the S1-restated line [B14]; no NETISS line joins it - NETISS r1 is dead under S1, which settles [B12]'s 'NETISS first' rule) + c x the cell
    against L, c by VOLATILITY over the cell's window (25% of #463's daily std over those rows / the cell's),
    0.5c and 2c reported, the plain #463 + c x the cell a reported row; an incremental pass = ROC @ $30k and Sortino both strictly above L's. r18_divrun's a2_report with the window; the dollars a year beside every ROC and [B11] DD5 beside
    every ROC - L's, L + c x the cell at c / 0.5c / 2c, the plain book (r21_netiss's a2_report, pointed at this window)"""
    with patched(DV, A2_WIN=win, A2_TARGET=A2_TARGET, A2_REPORT=A2_REPORT):
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
    raw, xb = np.asarray(ref.raw, float), np.asarray(xB, float)
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


def plain_a2(B, xB, win):
    """the registered volatility rule for c (r18_divrun's plain_a2) on the cell's window; Stage B recomputes the frozen c with it"""
    with patched(DV, A2_WIN=win, A2_TARGET=A2_TARGET, A2_REPORT=A2_REPORT):
        return DV.plain_a2(B, xB)


def pick_candidate(cells, passing):
    """the prereg: two passing cells send the HIGHER WF ROC @ $30k to Stage B, a tie to P"""
    return max(passing, key=lambda c: (cells[c]["base"]["roc"], -CELLS.index(c))) if passing else None


def stage_a_flow(cells):
    """Stage A's bookkeeping, pure: passing = the cells that clear (a) - (e); the candidate = pick_candidate(passing). (f), the hand audit, is NEVER decided here - every passing cell 'awaits the hand audit', and Stage B needs the lead's go-flag"""
    passing = [c for c in CELLS if cells[c]["PASS"]]
    return passing, pick_candidate(cells, passing)


def overlap(L, a, b):
    """the share of key a's longs that are key b's longs and of its shorts that are b's shorts, over the rebalances where both trade (the means)"""
    ov = defaultdict(list)
    for rec in L.recs:
        ca, cb = rec.cell[a], rec.cell[b]
        if ca.traded and cb.traded:
            la, sa = set(rec.pool[ca.idx[ca.long]].tolist()), set(rec.pool[ca.idx[ca.short]].tolist())
            lb, sb = set(rec.pool[cb.idx[cb.long]].tolist()), set(rec.pool[cb.idx[cb.short]].tolist())
            ov["long"].append(len(la & lb) / len(la))
            ov["short"].append(len(sa & sb) / len(sa))
    return {k: (float(np.mean(ov[k])) if ov[k] else float("nan")) for k in ("long", "short")} | {"rebalances": len(ov["long"])}


# ------------------------------------------------------------------ one reading of Stage A: the leg -> [B9] -> the NULL FIRST (the power line) -> the cells -> the stress rows -> the checks -> A2 -> the twins
def evaluate(W, B, S12, ref, rows, post_mode, nreps, vcode=0, full=False, announce=None, b9=None):
    """one reading of Stage A on the WF stretch: the leg (the pool, the scores, the picks of the cells and twins), then b9(L) - [B9] the zero-rule share of the PICKED names, printed right after the picks, before any return -, then the registered null
    (nreps draws per cell from the scored pool; vcode picks its random streams) BEFORE any cell's P&L, handed to `announce` (the power line, SHORTINT [A6]), then each cell: its run, the cost curve (0 / 5 / 10 / 20 bps), the seat on #463 and on the
    reference, the July-June years it holds positions in, A2 over the reference on its own window (the first 24 months of its traded fills), the beta credit rule, the dollars a year, DD5, the reference's episodes, the checks (a) - (e) and the gate's
    basis; full = also the sides apart, the borrow / -100% / shorts-at-zero rows, the regime halves, the deciles, the ES-hedged twin, and the REPORTED twins: the dividend-only twin, [B8]'s P8 / R8, the FLAT twin, the REP / MV deciles. -> (summary,
    objects: the leg, the key views, the base runs, the series, the side series)"""
    lo, hi = WF0, PRE_END
    L = bb_build(W, lo, hi, post_mode)
    if b9 is not None:
        b9(L)
    legs = {k: cell_leg(L, k) for k in TRADED}
    nul = None
    if nreps:
        acc = bb_null(W, L, nreps, vcode)
        pc, pdo = {}, {}
        for cell in CELLS:
            pc[cell], pdo[cell] = DV.null_stats(S12, ref.S, acc[cell], rows, B.n)
        del acc
        nul = null_summary(pc, pdo)
        if announce is not None:
            announce(nul, L)
    runs, series, side_x, summ = {}, {}, {}, {}
    for cell in CELLS:
        CL = legs[cell]
        base = M17.run_cell(W, CL, D15.l1_cfg(), pos=True)
        st, xB, cB = stat_run(B, rows, base)
        runs[cell], series[cell] = base, (xB, cB)
        at = lambda cfg, CL=CL, **kw: stat_run(B, rows, M17.run_cell(W, CL, cfg, **kw))[0]
        d0 = first_fill(W, L, cell)
        win = a2_window(d0)
        c = {"base": st, "cost0": at(D15.l1_cfg(bps=0.0)), "stress": {f"{b:g} bps": at(D15.l1_cfg(bps=b)) for b in STRESS_BPS}, "seat": D15.seat_measure(S12, xB), "seat_ref": D15.seat_measure(ref.S, xB), "years_held": years_held(B, cB),
             "first_rank_with_a_score": first_scored(W, L, cell), "first_traded_fill": None if d0 is None else f"{d0:%Y-%m-%d}", "A2": a2_report(B, xB, ref, win), "beta": beta_credit(B, S12, W, rows, xB)}
        c["usd_year"] = per_year(st["net"], st["years"])
        c["dd5"] = dd5_rec(B, xB)                                                          # [B11] DD5 beside the cell's ROC @ $30k
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
            c["sub"] = {lab: stat_run(B, rows, NI.sub_run(W, L, base, a, b), a, b)[0] for lab, a, b in SUBPERIODS}
            c["deciles"] = NI.decile_stats(B, rows, W, L, cell)
            xh, br = NI.hedged_series(W, base.x, L, cell)                                   # the ES-hedged twin of the cell (NETISS [A6]'s rule: an ex-ante OLS beta over the 252 sessions before the rank, zero before 252 exist; 0.5 bps a side)
            xhB = D15.to_B(xh, rows, B.n)
            sth = D15.cell_stats(B, xhB, cB, lo, hi, base)
            c["hedged"] = {"base": sth, "usd_year": per_year(sth["net"], sth["years"]), "dd5": dd5_rec(B, xhB), "ratios_nonzero": int(sum(1 for v in br.values() if v != 0.0)), "ratios": int(len(br)), "beta": beta_credit(B, S12, W, rows, xhB)}
        summ[cell] = c
    twins = {}
    if full:
        for t in TWINS:                                                                    # the REPORTED twins, never a pass route (no null, no checks)
            run_t = M17.run_cell(W, legs[t], D15.l1_cfg(), pos=True)
            st_t, xt, ct = stat_run(B, rows, run_t)
            series[t], runs[t] = (xt, ct), run_t
            par = "R" if t in ("R8", "FLAT") else "P"
            md = Counter(rec.cell[t].mode for rec in L.recs if len(rec.pool))
            twins[t] = {"text": TWIN_TEXT[t], "parent": par, "base": st_t, "usd_year": per_year(st_t["net"], st_t["years"]), "dd5": dd5_rec(B, xt), "modes": dict(md), "names_mean": float(np.mean([rec.cell[t].n for rec in L.recs])) if L.recs else 0.0,
                        "pick_overlap_with_parent": overlap(L, t, par), "corr_with_parent": float(np.corrcoef(xt[B.mask(lo, hi)], series[par][0][B.mask(lo, hi)])[0, 1]) if np.ptp(xt[B.mask(lo, hi)]) > 0 and np.ptp(series[par][0][B.mask(lo, hi)]) > 0 else float("nan")}
        twins[DECK] = NI.decile_stats(B, rows, W, L, DECK)
    for cell in CELLS:
        c = summ[cell]
        if nul is not None:
            c["checks"] = judge_cell(c["base"], c["stress"]["10 bps"]["net"], nul, len(c["years_held"]))
            c["PASS"] = bool(all(c["checks"].values()))
        c["gate70"] = gate70(c, ref, nul)
    return {"variant": post_mode, "cells": summ, "twins": twins, "null": nul}, SimpleNamespace(legs=L, cell_legs=legs, runs=runs, series=series, side_x=side_x)


# ------------------------------------------------------------------ THE NETISS QUESTION (reported, never a pass route)
def netiss_question(W, B, rows, L, obj, ref):
    """NETISS r1's two cells computed IN-PROCESS on the same World (r21_netiss.ni_build with its judged reading r21_netiss.JUDGED + r17_resmom.run_cell: its registered picks, sizing and costs): each BUYBACK cell's daily P&L correlation with N12,
    N24 and with RESMOM's RES (the S1-restated line's RES column, [B14]) over the WF days, and per rank the overlap of the picks - the share of this cell's longs among each NETISS cell's longs and of its shorts among its shorts (and the cross
    shares). The FLAT twin is in evaluate's twins -> {cell: {corr, corr_RES, overlap: {N12, N24}}, netiss: {N12, N24: net / ROC / $ a year / DD5 / rebalances}}"""
    Ln = NI.ni_build(W, WF0, PRE_END, NI.JUDGED)
    kw = np.flatnonzero(B.mask(WF0, PRE_END))
    cor = lambda a, b: float(np.corrcoef(a[kw], b[kw])[0, 1]) if len(kw) > 2 and np.ptp(a[kw]) > 0 and np.ptp(b[kw]) > 0 else float("nan")
    xn, out = {}, {"netiss": {}}
    for n in NI.CELLS:
        run = M17.run_cell(W, NI.cell_leg(Ln, n), D15.l1_cfg())
        st, xb, _cb = stat_run(B, rows, run)
        xn[n] = xb
        out["netiss"][n] = {"net": st["net"], "roc": st["roc"], "n_units": st["n_units"], "usd_year": per_year(st["net"], st["years"]), "dd5": dd5_rec(B, xb)}
    by_r = {rec.r: rec for rec in Ln.recs}
    res = np.asarray(ref.res, float)
    for cell in CELLS:
        xb = obj.series[cell][0]
        ov = {n: [] for n in NI.CELLS}
        for rec in L.recs:
            cc, rn = rec.cell[cell], by_r.get(rec.r)
            if not cc.traded or rn is None:
                continue
            lg, sh = set(rec.pool[cc.idx[cc.long]].tolist()), set(rec.pool[cc.idx[cc.short]].tolist())
            for n in NI.CELLS:
                nc = rn.cell[n]
                if nc.traded:
                    nl, ns = set(rn.pool[nc.idx[nc.long]].tolist()), set(rn.pool[nc.idx[nc.short]].tolist())
                    ov[n].append({"rank": f"{W.days[rec.r]:%Y-%m-%d}", "long_in_long": len(lg & nl) / len(lg), "short_in_short": len(sh & ns) / len(sh), "long_in_short": len(lg & ns) / len(lg), "short_in_long": len(sh & nl) / len(sh)})
        mean = lambda v, k: float(np.mean([q[k] for q in v])) if v else float("nan")
        out[cell] = {"corr": {n: cor(xb, xn[n]) for n in NI.CELLS}, "corr_RES": cor(xb, res),
                     "overlap": {n: {"rebalances": len(v), **{k: mean(v, k) for k in ("long_in_long", "short_in_short", "long_in_short", "short_in_long")}, "by_rank": v} for n, v in ov.items()}}
    return out


# ------------------------------------------------------------------ the reports (never a pass route)
def reports(W, B, S12, ref, rows, obj, summ, tbis_df, status, legs_meta):
    """the prereg's DIAGNOSTICS and the addenda's lists for the judged reading: the realised beta to ES on #463's drawdown days and all WF days, each cell's $ inside every qualifying #463 drawdown and inside every drawdown episode of the REFERENCE
    book (the cell's P&L inside each and which episodes it helps), its place on the MDL map, the correlation of its daily P&L with the house legs and with RES, the persistence and the turnover, the 20 largest name-month gains, the months, the
    dividend flows, survivorship; the deciles, the twins and the hedged twin are in summ -> (rep, the audit candidates per cell)"""
    L, lo, hi = obj.legs, WF0, PRE_END
    rep = {"beta_to_es": {}, "episodes": {}, "ref_episodes": {}, "map_point": {}, "corr_with_legs": {}, "corr_with_res": {}, "top20_gains": {}, "months": {}, "turnover": {}, "survivorship": {}, "dividend_flows": {}}
    cands = {}
    kw = np.flatnonzero(B.mask(lo, hi))
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
        cands[cell] = bb_candidate_rows(W, L, cell, obj.runs[cell], tbis_df, status)
        rep["top20_gains"][cell] = cands[cell][:20]
        rep["months"][cell] = M17.month_nets(B, xB, lo, hi)
        rep["turnover"][cell] = NI.ni_turnover(L, cell)
        rep["survivorship"][cell] = D15.survivorship(W, obj.cell_legs[cell], status)
        rep["dividend_flows"][cell] = NI.ni_div_flows(L, cell)
    rep["manifest_sha256"] = manifest_sha()
    return rep, cands


# ------------------------------------------------------------------ the hand audit's rows (f) / [B4]: every contributor and every flagged name-rank with its component facts, their filings (accession numbers) and the market value's inputs
def short_con(c):
    return c.split(":", 1)[-1]


def facts_used(W, r, col):
    """the facts behind one name's TTM at the rank close r: per period of the TTM (the statement period 'ttm' (+), FY_prev (+), YTD_prev (-)) the STATEMENT concept used, the REP / DIV concept used (none: the zero rule), every ISSUANCE item summed ([B7]:
    the primary and the stock-plan concepts; an item with the same value in the same filing as an earlier one is counted once and noted), the [B8] withholding; each with its value, FIRST filed date, accession number [B4] and form -> [dict]"""
    sc = score_rank(W, r)
    cs, out = W.bb.cash, []
    if sc.kind[col] == 0:
        return out
    for tag, p in (("ttm", int(sc.p0[col])), ("fy_prev", int(sc.p1[col])), ("ytd_prev", int(sc.p2[col]))):
        if p < 0:
            continue
        u, fact = W.bb.URW[p] <= r, cs.FACT[p]

        def put(role, ci, note=""):
            e = int(fact[ci])
            out.append({"period": tag, "start": dstr(cs.pstart[p]), "end": dstr(cs.pend[p]), "role": role, "concept": CONCEPTS[ci], "value": float(cs.E_val[e]), "first_filed": dstr(cs.E_f1[e]), "accn": str(cs.accns[cs.E_accn[e]]),
                        "form": str(cs.forms[int(cs.E_form[e])]), "note": note})
        put("STATEMENT", CIX[C_ST[0]] if u[CIX[C_ST[0]]] else CIX[C_ST[1]])
        for role, cons in (("REP", C_REP), ("DIV", C_DIV)):
            for q, c_ in enumerate(cons):
                if u[CIX[c_]]:
                    put(role, CIX[c_], "the fallback concept" if q else "")
                    break
        prim = next((CIX[c_] for c_ in C_ISS if u[CIX[c_]]), None)
        seen = []
        for ci in ([prim] if prim is not None else []) + [CIX[c_] for c_ in C_PLAN if u[CIX[c_]]]:
            e = int(fact[ci])
            key = (int(cs.E_accn[e]), float(cs.E_val[e]))
            put("ISS", ci, "the same value in the same filing as an earlier item: counted once [B7]" if key in seen else "")
            seen.append(key)
        if u[CIX[C_TW[0]]]:
            put("TW [B8]", CIX[C_TW[0]])
    return out


def group_key(W, r, col):
    """(f) / [B4] the GROUP of a name-rank: the symbol and the accession numbers of every fact behind its score - the statements and the components of P's TTM on its periods (REP, DIV, every ISSUANCE item) and the share count S of its market value
    - 'symbol|accn+accn+...' (sorted). CHOICE: one key for both cells (P reads R's facts plus DIV), so ONE audit row covers every rank and cell that uses the same filings; '' where the name has no TTM or no share count at that rank"""
    sc = score_rank(W, r)
    if sc.kind[col] == 0 or sc.sg[col] < 0:
        return ""
    acc = {f["accn"] for f in facts_used(W, r, col) if not f["role"].startswith("TW")}
    acc.add(str(W.ni.E_accn[int(sc.sg[col])]))
    return f"{W.syms[col]}|" + "+".join(sorted(acc))


def bb_fields(W, r, col, cell=None):
    """the hand audit's columns for one name at the rank close r: the cash CIK, the TTM's formula, its periods and the statement's end e, the days from e to r, the TTMs of REP / DIV / ISS / TW, which components the zero rule read on which periods,
    the market value's inputs (the raw close, S with its as-of date, concept, first filed date and accession, F(a), F(r)), every score and the 0.15 flag, every fact used with its filing [B4], and the group"""
    sc = score_rank(W, r)
    cs, ni = W.bb.cash, W.ni
    cn, sg, kind = int(W.bb.cn[col]), int(sc.sg[col]), int(sc.kind[col])
    fl = facts_used(W, r, col)
    nan = float("nan")
    zr = []
    if kind:
        cu = comp_use(sc, np.array([col]))
        zr = [f"{nm.upper()} zero on {int(sum((sc.comps[q][nm + '_src'][col] == 0) for q in range(3)))} period(s)" for nm in ("rep", "div") if cu[nm]["zero_any"][0]]
        if cu["iss"]["zero_any"][0]:
            zr.append(f"ISS zero on {int(sum((sc.comps[q]['rep_src'][col] >= 0) and not sc.comps[q]['iss_any'][col] for q in range(3)))} period(s)")
    out = {"rank_date": f"{W.days[r]:%Y-%m-%d}", "cik": str(cs.ciks[cn]) if cn >= 0 else "", "ttm": {0: "", 1: "FY", 2: "YTD + FY_prev - YTD_prev"}[kind], "statement_end": dstr(sc.e[col]) if kind else "", "fy_start": dstr(sc.s[col]) if kind else "",
           "days_e_to_r": int(sc.stale_days[col]), "rep_ttm": float(sc.rep[col]), "div_ttm": float(sc.div[col]), "iss_ttm": float(sc.iss[col]), "tw_ttm": float(sc.tw[col]), "zero_rule": "; ".join(zr),
           "mv": float(sc.mv[col]) if sg >= 0 else nan, "close": float(sc.cl[col]), "shares": float(sc.Sv[col]) if sg >= 0 else nan, "shares_asof": dstr(sc.a[col]) if sg >= 0 else "", "shares_concept": ("dei" if sg < ni.dei.n else "us-gaap") if sg >= 0 else "",
           "shares_first_filed": dstr(ni.E_f1[sg]) if sg >= 0 else "", "shares_accn": str(ni.E_accn[sg]) if sg >= 0 else "", "F_asof": float(sc.fa[col]) if sg >= 0 else nan, "F_rank": float(sc.fr[col]),
           **{f"score_{k}": float(sc.score[k][col]) for k in CODE_KEYS + ("DIV", DECK)}, "flag_over_0.15": bool(sc.flag[cell][col]) if cell in CODE_KEYS else False,
           "facts": "; ".join(f"{f['period']} {f['start']}..{f['end']} {f['role']} {short_con(f['concept'])}={f['value']:,.0f} ({f['accn']} {f['form']} filed {f['first_filed']}{', ' + f['note'] if f['note'] else ''})" for f in fl),
           "group": group_key(W, r, col)}
    return out


def bb_candidate_rows(W, L, cell, run, tbis_df, status, n=AUDIT_N):
    """the n largest single-name contributors of a cell for the hand audit (r17_resmom.rm_candidate_rows' rows: the largest GAINS with the FILL date - the key buyback_audit.csv uses -, exit, side, $, the score, the split factor's ratio, the raw
    overnight moves, TBIS's rows, the asset status, the hygiene reasons, the dividends; its two formation-window moves are RESMOM's and are left out) + bb_fields"""
    rows = M17.rm_candidate_rows(W, L, cell, run, tbis_df, status, n)
    if not rows:
        return rows
    p = run.pos
    sel = np.argsort(-np.asarray(p.pnl, float), kind="stable")[:n]
    for row, i in zip(rows, sel):
        rec, col = L.recs[int(p.rec[i])], int(p.col[i])
        for k_ in ("raw_move_formation", "adj_move_formation"):
            row.pop(k_, None)
        row.update(bb_fields(W, rec.r, col, cell))
    return rows


def picks_by_name_month(L):
    """the REGISTERED picks of a leg by name-month: {(fill row, World column): ['P/long', 'R/short', ...]} - the cells' picks (the twins, the deciles and the null's draws are not picks)"""
    out = defaultdict(list)
    for rec in L.recs:
        for c in CELLS:
            cc = rec.cell[c]
            if cc.traded:
                cols = rec.pool[cc.idx]
                for sd, sel in (("long", cc.long), ("short", cc.short)):
                    for j in cols[sel]:
                        out[(rec.f, int(j))].append(f"{c}/{sd}")
    return out


def flag15_rows(W, ranks, L):
    """(f) every scored name-rank with |score| > 0.15 among the universe names of each rank, per cell, with the key of the audit file (symbol + the FILL date), whether it is PICKED (the cell / side of every pick of that name-month in the registered leg L,
    either cell) and bb_fields (the group among them): ALL of them are listed in buyback_flags.csv; the hand audit (f) covers the PICKED ones, grouped by their filings (never a filter)"""
    pk = picks_by_name_month(L)
    rows = []
    for r, f, _x in ranks:
        uni = np.flatnonzero(W.U[f])
        sc = score_rank(W, r)
        for cell in CELLS:
            for col in uni[sc.flag[cell][uni]]:
                rows.append({"cell": cell, "symbol": str(W.syms[col]), "date": f"{W.days[f]:%Y-%m-%d}", "picked": ", ".join(pk.get((f, int(col)), [])), "score": float(sc.score[cell][col]), **bb_fields(W, r, int(col), cell)})
    return rows


fill_ranks = NI.fill_ranks


def name_month_keys(W, f, col):
    """the group key of one name-month (fill row f, World column col) - one for both cells (group_key's CHOICE); empty when f is not the fill session of a rebalance the builders use or the name has no TTM / share count at the rank"""
    if (f - 1, f) not in set(fill_ranks(W)):
        return set()
    k = group_key(W, f - 1, col)
    return {k} if k else set()


def group_members(W, col, keys):
    """the fill rows of every name-month of the World column `col` whose group is one of `keys` (one scan over the rebalances: 'every rank that uses the same filings')"""
    return [f for r, f in fill_ranks(W) if group_key(W, r, col) in keys]


def audit_keys(W, audit):
    """the group keys the audit file's rows cover (every row, keep or data_event): the union of their name-months' keys (a row's cell is a label: a data event belongs to the name-month)"""
    out = set()
    if audit is None:
        return out
    ci = pd.Index(W.syms).get_indexer(audit["symbol"])
    di = W.days.get_indexer(pd.DatetimeIndex(audit["date"]))
    for c_, d_ in zip(ci.tolist(), di.tolist()):
        if c_ >= 0 and d_ >= 0:
            out |= name_month_keys(W, d_, c_)
    return out


def audit_status(W, cands, flags, audit):
    """the hand audit's bookkeeping, REPORTED only (the harness never decides (f)): an audit row covers its own name-month AND every other name-month on the same filings (the same group). Per cell: listed / audited = the top-50 contributors
    and how many are covered, groups = the distinct groups among them; flagged = the |score| > 0.15 name-ranks, picked = those PICKED, flag_listed / flag_audited = the distinct picked GROUPS and how many are covered -> {cell: {...}}"""
    have = set() if audit is None else set(zip(audit["symbol"], audit["date"].dt.strftime("%Y-%m-%d")))
    cov = audit_keys(W, audit)
    out = {}
    for cell in CELLS:
        rows = cands.get(cell, [])
        n = sum(((r["symbol"], r["date"]) in have) or (r.get("group", "") != "" and r["group"] in cov) for r in rows)
        fl = [r for r in flags if r["cell"] == cell]
        members = defaultdict(list)
        for r in fl:
            members[r.get("group") or f"{r['symbol']}|{r['date']}"].append((r["symbol"], r["date"]))
        pg = {(r.get("group") or f"{r['symbol']}|{r['date']}") for r in fl if r.get("picked")}
        n_a = sum((g in cov) or any(m in have for m in members[g]) for g in pg)
        out[cell] = {"listed": len(rows), "audited": int(n), "audit_complete": bool(len(rows) > 0 and n == len(rows)), "groups": len({r["group"] for r in rows if r.get("group")}), "flagged": len(fl),
                     "flagged_picked": int(sum(1 for r in fl if r.get("picked"))), "flag_listed": int(len(pg)), "flag_audited": int(n_a), "flag_complete": bool(n_a == len(pg))}
    return out


def read_audit(path=None):
    """OUT\\buyback_audit.csv (symbol, date, cell, verdict in {keep, data_event}, note) -> a frame, or None when there is no file yet. A data_event row removes that name-month from BOTH cells AND the nulls before anything is computed [(f)];
    the date is the position's FILL date (the 'date' of buyback_audit_candidates.csv and buyback_flags.csv). ONE ROW COVERS A GROUP: every other name-month of the same symbol on the same filings - a data_event row removes all of them, a keep
    row counts them all as audited. Refuses a verdict / cell / date it cannot read (a mistyped row must not silently do nothing)"""
    p = path or os.path.join(OUT, "buyback_audit.csv")
    if not os.path.exists(p):
        return None
    df = pd.read_csv(p, dtype=str, keep_default_na=False)
    miss = [c for c in ("symbol", "date", "cell", "verdict") if c not in df.columns]
    if miss:
        refuse(f"refused: buyback_audit.csv lacks the column(s) {miss} (columns: symbol, date, cell, verdict, note) - nothing computed")
    df["symbol"], df["cell"], df["verdict"] = df["symbol"].str.strip(), df["cell"].str.strip().str.upper(), df["verdict"].str.strip().str.lower()
    df["date"] = pd.to_datetime(df["date"].str.strip(), errors="coerce")
    bad = df[~df["verdict"].isin(("keep", "data_event")) | ~df["cell"].isin(CELLS) | df["date"].isna() | (df["symbol"] == "")]
    if len(bad):
        refuse(f"refused: buyback_audit.csv line(s) {[int(i) + 2 for i in bad.index][:10]} have an unreadable date / symbol, a verdict outside keep | data_event, or a cell outside {list(CELLS)} (nothing computed)")
    return df


unused_audit_rows = M17.unused_audit_rows


def apply_audit(W, audit):
    """the audit file's data_event rows put on the World as removals before anything is built: r17_resmom's own (the key is symbol + FILL date; the name-month leaves the pool - cells AND nulls; a row that matches no session or no name refuses)
    PLUS the groups: a data_event row also removes every other name-month on the same filings (group_members). Needs W.bb (attach_buyback first) -> {rows, keep, data_event, group_name_months}"""
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


cut_checks = DV.cut_checks


# ------------------------------------------------------------------ printing
row = NI.row


def print_power(nul, L=None):
    """the power line (SHORTINT [A6]): the random-name null's p5 / p50 / p95 of the MAX over the 2 cells' WF ROC @ $30k and each cell's own p50 / p95 - printed BEFORE any cell's number"""
    print(f"POWER LINE - printed before any cell's P&L: the random-name null ({nul['draws']} draws, seed {nul['seed']}, from each rebalance's eligible SCORED pool, the MAX over the 2 cells), ROC@30k p5 {nul['roc_max']['p5']:.1f} p50 {nul['roc_max']['p50']:.1f} "
          f"p95 {nul['roc_max']['p95']:.1f}; each cell alone p50 / p95: " + ", ".join(f"{c} {nul['by_cell'][c]['p50']:.1f} / {nul['by_cell'][c]['p95']:.1f}" for c in CELLS)
          + f"; the DO null on the reference's drawdown days (the MAX over the 2 cells) p50 {nul['do_ref_max']['p50']:+.3f} p95 {nul['do_ref_max']['p95']:+.3f}")


def print_cells(res, audit_st=None):
    for cell in CELLS:
        c = res["cells"][cell]
        fails = [k for k, v in c["checks"].items() if not v]
        s2 = ", ".join(f"{k} net ${v['net']:,.0f}" for k, v in c["stress"].items())
        print("  " + row(cell, c))
        print(f"        first rank with a score {c['first_rank_with_a_score']}, first traded fill {c['first_traded_fill']}; stress: {s2}; by July-June year: " + " ".join(f"{y}-{(y + 1) % 100:02d}:{v:+,.0f}" for y, v in c["base"]["by_year"].items())
              + f"; years with a position: {len(c['years_held'])}")
        b = c["beta"]
        print(f"        realised beta to ES (the cell's daily $ P&L on ES's daily return per $ of one side's notional ${b['side_notional']:,.0f}): #463's DD days {b['beta_dd_days']:+.3f}, all WF days {b['beta_all_days']:+.3f} - the credit cap is |beta| <= {b['cap']:.2f} on BOTH -> "
              + ("the drawdown-day profile may be credited" if b["within_cap"] else "NOT CREDITED: the profile is reported, no incremental A2 pass, no gate, no line"))
        a2 = c["A2"]
        if a2.get("at_half_c"):
            rf, pl = a2["reference"], a2["plain_463"]
            a2s = (f"c x{a2['c']:.4g} (cell daily std ${a2['std_cell']:,.0f} vs #463's ${a2['std_book']:,.0f} over the cell's first {A2_MONTHS} months of traded fills {a2['window'][0]} .. {a2['window'][1]}): REFERENCE + c x cell ROC@30k {a2['roc']:.2f} / {dd5_txt(a2['dd5'])} "
                   f"(${a2['usd_year']:,.0f} a year) Sortino {a2['sortino']:.3f} against the reference's {rf['roc']:.2f} / {dd5_txt(rf['dd5'])} (${rf['usd_year']:,.0f} a year) / {rf['sortino']:.3f} -> "
                   + ("INCREMENTAL PASS (both above): MANAGER #70's gate follows, then at most one forward book line" if a2["incremental_credit"] else
                      ("incremental numbers pass but the beta rule refuses the credit: no line" if a2["incremental_pass"] else "no incremental pass (it needs both above)"))
                   + f"; at 0.5c ROC {a2['at_half_c']['roc']:.2f} / {dd5_txt(a2['at_half_c']['dd5'])} (${a2['at_half_c']['usd_year']:,.0f} a year) / Sortino {a2['at_half_c']['sortino']:.3f}, at 2c ROC {a2['at_double_c']['roc']:.2f} / {dd5_txt(a2['at_double_c']['dd5'])} "
                   f"(${a2['at_double_c']['usd_year']:,.0f} a year) / Sortino {a2['at_double_c']['sortino']:.3f}; the plain #463 + c x cell book (a reported row): ROC {pl['roc']:.2f} / {dd5_txt(pl['dd5'])} (${pl.get('usd_year', float('nan')):,.0f} a year) / Sortino {pl['sortino']:.3f}")
        else:
            a2s = f"{a2.get('error', 'no c')} (window {a2['window'][0]} .. {a2['window'][1]}) -> no incremental pass"
        au = None if audit_st is None else audit_st[cell]
        print(f"        Stage A (a)-(e) {'PASS' if c['PASS'] else 'FAIL (' + ', '.join(fails) + ')'}" + ("" if au is None else
              f"; hand audit (f) {au['audited']}/{au['listed']} of the top-{AUDIT_N} listed ({au['groups']} groups), {au['flag_audited']}/{au['flag_listed']} of the picked |score| > 0.15 groups ({au['flagged_picked']} picked of {au['flagged']} flagged name-ranks) -> "
              f"top-50 {'COMPLETE' if au['audit_complete'] else 'incomplete'}, picked groups {'COMPLETE' if au['flag_complete'] else 'incomplete'}"))
        print(f"        A2 (a report): {a2s}")
        g = c["gate70"]
        print(f"        #70 gate basis (the REFERENCE book's {g['episodes']} drawdown episodes, {g['dd_days']} DD days): the cell's DO {g['DO']:+.3f}, rho_dd {g['rho_dd']:+.3f}" + (
              f"; its null's DO (random names, the MAX over the 2 cells) p5 {g['null_do_p5']:+.3f} p50 {g['null_do_p50']:+.3f} p95 {g['null_do_p95']:+.3f} -> the cell's DO is {'above' if g['DO_above_null_p95'] else 'not above'} the null's p95" if "null_do_p95" in g else "")
              + (f"; its P&L inside those episodes ${sum(g['episode_pnl']):,.0f} (${g['pnl_without_best_episode']:,.0f} without the best one; it helps {g['episodes_helped']} of {len(g['episode_pnl'])})" if g.get("episode_pnl") else "")
              + ("" if g["credited"] else "; the beta rule: NOT credited"))


def print_deciles(res):
    """ten equal-count score deciles per rank of P, R and the gross repurchase yield REP / MV, each an equal-weight LONG-ONLY basket at $4,000 a name: WF net, ROC @ $30k, dollars a year, and the same for its spread over ES"""
    print("DECILES - the scored names cut into ten equal-count deciles at every rank (1 = the lowest score, the biggest net raisers .. 10 = the highest, the biggest net payers), each an equal-weight LONG-ONLY basket at $4,000 a name marked like the cells; "
          "the spread = the basket less an ES position of the same notional (reported, never a pass route; a crowded payer tail shows here)")
    for c, d in [(c, res["cells"][c]["deciles"]) for c in CELLS] + [(f"{DECK} (gross repurchase yield REP / MV, R's scored names)", res["twins"][DECK])]:
        print(f"  {c} ({d['ranks_cut']} ranks cut) decile: name-months | net $ / ROC@30k / $ a year | spread over ES net $ / ROC@30k / $ a year")
        for q in d["deciles"]:
            print(f"    {q['decile']:>2}: {q['name_months']:>7,} | {q['net']:>+11,.0f} / {q['roc']:>8.1f} / {q['usd_year']:>+9,.0f} | {q['spread_net']:>+11,.0f} / {q['spread_roc']:>8.1f} / {q['spread_usd_year']:>+9,.0f}")


def print_twins(res):
    """the REPORTED twins beside the cells: the ES-hedged twin of each cell, the dividend-only twin, [B8]'s withholding twins, the FLAT twin - net $, ROC @ $30k, $ a year, DD5, the rebalances traded, the picks' overlap with the parent cell"""
    print("TWINS - REPORTED beside the cells, never a pass route")
    for c in CELLS:
        x = res["cells"][c]
        h = x["hedged"]
        print(f"  {c}: the cell net ${x['base']['net']:,.0f} ROC@30k {x['base']['roc']:.1f} / {dd5_txt(x['dd5'])} (${x['usd_year']:,.0f} a year); ES-hedged twin (an ES overlay sized ex ante by the OLS beta of the cell's own daily P&L on ES over the 252 sessions before each rank, "
              f"zero before 252 sessions exist; {h['ratios_nonzero']} of {h['ratios']} rebalances hedged) net ${h['base']['net']:,.0f} ROC@30k {h['base']['roc']:.1f} / {dd5_txt(h['dd5'])} (${h['usd_year']:,.0f} a year), its realised beta DD days {h['beta']['beta_dd_days']:+.3f} / all days {h['beta']['beta_all_days']:+.3f}")
    for t in TWINS:
        x = res["twins"][t]
        ov = x["pick_overlap_with_parent"]
        print(f"  {t} - {x['text']}: net ${x['base']['net']:,.0f} ROC@30k {x['base']['roc']:.1f} / {dd5_txt(x['dd5'])} (${x['usd_year']:,.0f} a year), {x['base']['n_units']} rebalances traded (top / third / nothing: {x['modes'].get('top', 0)} / {x['modes'].get('third', 0)} / "
              f"{x['modes'].get('none', 0)}; {x['names_mean']:.0f} names a rank on average); its picks share {nan_or(ov['long'], '.0%')} of the longs / {nan_or(ov['short'], '.0%')} of the shorts with {x['parent']}'s over {ov['rebalances']} rebalances; daily P&L correlation with {x['parent']} {nan_or(x['corr_with_parent'], '+.2f')}")


def print_netiss_question(nq, res):
    """THE NETISS QUESTION, reported: the correlations, the pick overlaps per rank (means; per rank in the Stage A file) and the FLAT twin beside them"""
    print("THE NETISS QUESTION (reported, never a pass route) - NETISS r1's two cells computed in-process on this World (its judged reading, its picks, sizing and costs): " + "; ".join(
        f"{n} net ${v['net']:,.0f} ROC@30k {v['roc']:.1f} / {dd5_txt(v['dd5'])} (${v['usd_year']:,.0f} a year), {v['n_units']} rebalances" for n, v in nq["netiss"].items()))
    for c in CELLS:
        q = nq[c]
        print(f"  {c}: daily P&L correlation with N12 {nan_or(q['corr']['N12'], '+.3f')}, N24 {nan_or(q['corr']['N24'], '+.3f')}, RES {nan_or(q['corr_RES'], '+.3f')}; pick overlap per rank (means): " + "; ".join(
            f"{n} over {o['rebalances']} rebalances - longs that are its longs {nan_or(o['long_in_long'], '.0%')}, shorts that are its shorts {nan_or(o['short_in_short'], '.0%')} (longs that are its shorts {nan_or(o['long_in_short'], '.0%')}, shorts that are its longs {nan_or(o['short_in_long'], '.0%')})"
            for n, o in q["overlap"].items()))
    f = res["twins"].get("FLAT")
    if f:
        print(f"  the FLAT twin (R among the names whose NETISS one-year share change is within +-2%: does the CASH measure carry anything the share count does not?): net ${f['base']['net']:,.0f} ROC@30k {f['base']['roc']:.1f} / {dd5_txt(f['dd5'])} (${f['usd_year']:,.0f} a year), "
              f"{f['base']['n_units']} rebalances traded, {f['names_mean']:.0f} flat names a rank on average")


def print_reports(rep, summ):
    b = rep["beta_to_es"]
    print("  realised beta to ES (the cell's daily $ P&L on ES's daily return, $ per 1% ES move; #463's DD days / DD weeks / all WF days): " + "; ".join(
        f"{c} {b[c]['DD days']['usd_per_1pct_es']:+,.0f} / {b[c]['DD weeks (every day of them)']['usd_per_1pct_es']:+,.0f} / {b[c]['all WF days']['usd_per_1pct_es']:+,.0f}" for c in CELLS))
    for c in CELLS:
        e = rep["episodes"][c]
        print(f"  {c}: P&L inside #463's {len(e)} qualifying drawdowns: net ${sum(x['cell_pnl'] for x in e):,.0f} over {sum(x['dd_days'] for x in e)} DD days (#463's ${sum(x['book_pnl'] for x in e):,.0f}); "
              f"MDL map point: ROC@30k {rep['map_point'][c]['standalone_roc_30k']:.1f}, rho_dd {rep['map_point'][c]['rho_dd']:+.3f}, DO {rep['map_point'][c]['DO']:+.3f}; daily P&L correlation with RES {nan_or(rep['corr_with_res'][c], '+.3f')}")
    for c in CELLS:
        t = rep["turnover"][c]
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
        print(f"  {c} the 20 largest name-month gains (with their facts and filings in the Stage A file): " + "; ".join(f"{x['symbol']} {x['side']} {x['date']} ${x['pnl']:,.0f} ({x['ttm']}, score {x['score_' + c]:+.3f})" for x in rep["top20_gains"][c]))


DIAG_LW, DIAG_CW = NI.DIAG_LW, NI.DIAG_CW
diag_line = NI.diag_line


def print_diagnostics(res, rep, ref):
    """DIAGNOSTICS (owner standing order addendum 2), P and R side by side: the cost curve at 0 / 5 / 10 / 20 bps a side, a row per July-June year (and the sides), the regime halves, a row per qualifying drawdown episode of the REFERENCE book
    (the cell's P&L inside it), the LONG and SHORT sides apart, the #70 gate's basis; the dollars a year beside every ROC. None of it is a pass route"""
    cells = res["cells"]
    each = lambda f: [f(cells[c], c) for c in CELLS]
    nr = lambda s: f"{s['net']:+,.0f} / {s['roc']:.1f} / {per_year(s['net'], s['years']):+,.0f}"
    print("DIAGNOSTICS - the judged reading, the WF stretch, P and R side by side; none of this is a pass route (cells: net $ / ROC@30k / $ a year)")
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
    print(f"  THE REFERENCE BOOK'S DRAWDOWN EPISODES ({g['episodes']} qualifying, {g['days']} DD days; MDL r1's rule) - the cell's P&L inside each (the DD days: the day after the peak .. the trough) and the episodes it helps")
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
    print(diag_line("  credited by the beta rule (both betas within 0.20)", each(lambda c, k: "yes" if c["beta"]["within_cap"] else "no")))


def scored_stats(L):
    """COUNTS over a leg's rebalances: per key the scored names per rebalance (min / median / max over the rebalances whose pool was not empty) and the rebalances by what they trade (top 50 / the thirds / nothing)"""
    out = {}
    for c in TRADED:
        ns = np.array([rec.cell[c].n for rec in L.recs if len(rec.pool)], int)
        out[c] = {"rebalances": int(len(L.recs)), "with_a_pool": int(len(ns)), "min": int(ns.min()) if len(ns) else 0, "median": float(np.median(ns)) if len(ns) else 0.0, "max": int(ns.max()) if len(ns) else 0,
                  "modes": dict(Counter(rec.cell[c].mode for rec in L.recs if len(rec.pool))), "traded": int(sum(rec.cell[c].traded for rec in L.recs))}
    return out


def print_scored_stats(label, L, W):
    st = scored_stats(L)
    print(f"  {label} scored names per rebalance (min / median / max over the {st[CELLS[0]]['with_a_pool']} rebalances with a pool of {st[CELLS[0]]['rebalances']}; rebalances trading the top {M17.SPEC['n_side']} a side / the top-bottom third / nothing): "
          + "; ".join(f"{c} {st[c]['min']} / {st[c]['median']:.0f} / {st[c]['max']}, {st[c]['modes'].get('top', 0)} / {st[c]['modes'].get('third', 0)} / {st[c]['modes'].get('none', 0)}" for c in TRADED))
    byy = {c: defaultdict(list) for c in CELLS}
    for rec in L.recs:
        if len(rec.pool):
            for c in CELLS:
                byy[c][int(W.days[rec.f].year)].append(rec.cell[c].n)
    for c in CELLS:
        print(f"    {c} by fill year (rebalances: min / median / max scored): " + "; ".join(f"{y}: {len(v)}: {min(v)} / {np.median(v):.0f} / {max(v)}" for y, v in sorted(byy[c].items())))
    return st


def print_scored(label, cnt):
    """the scored names and the sides by fill year: per cell the pool's scored names (summed over the year's rebalances) and the pool names with no score; the rebalances that trade the top 50 / the third / nothing; then the pool's no-score names by
    the first reason ([A13]'s second class included)"""
    print(f"  {label} scored names by fill year (per cell: scored / pool names with no score; rebalances trading the top {M17.SPEC['n_side']} a side | the top-bottom third | nothing)")
    for y, c in sorted(cnt.items()):
        if c.get("rebalances", 0):
            print(f"    {y}: " + "; ".join(f"{cl} {c.get(f'scored_{cl}', 0):,} / {c.get(f'no_score_{cl}', 0):,}, {c.get(f'mode_{cl}_top', 0)} | {c.get(f'mode_{cl}_third', 0)} | {c.get(f'mode_{cl}_none', 0)}" for cl in CODE_KEYS))
    print(f"  {label} the pool's no-score names by the first reason, by fill year (" + ", ".join(REASONS[1:]) + "):")
    for cl in CELLS:
        for y, c in sorted(cnt.items()):
            if c.get("rebalances", 0):
                print(f"    {cl} {y}: " + " ".join(f"{c.get(f'ns_{cl}_{rs}', 0)}" for rs in REASONS[1:]))


def print_counts(label, cnt):
    """the pool's removals by fill year, each name at its FIRST reason (r21_netiss's columns, NI.COUNT_KEYS), and the names with an in-hold event that STAY in the pool (NI.KEPT_KEYS: under [B10]'s 'keep' the flagged ones, under the judged
    reading [B13] also the calendar splits on the split-safe path and the positions closed before a spin-off / stock-dividend ex-date) - this family's labels on r21_netiss.print_counts' layout"""
    keys = [k for k in NI.COUNT_KEYS if any(k in c for c in cnt.values())]
    print(f"  {label} name-removals by fill year, each name counted once at its FIRST reason (columns: " + " / ".join(keys) + ")")
    for y, c in sorted(cnt.items()):
        print(f"    {y}: " + " ".join(f"{c.get(k, 0)}" for k in keys) + f"   [rebalances {c.get('rebalances', 0)}, unresolved {c.get('unresolved', 0)}, warm-up {c.get('warmup', 0)}, empty {c.get('empty', 0)}]")
    if any(c.get(k, 0) for c in cnt.values() for k in NI.KEPT_KEYS):
        print(f"  {label}: names with an in-hold event that STAY in the pool [B13] (flagged / a calendar split: on the split-safe path; closed_spin: closed at the close before a spin-off / stock-dividend ex-date inside the hold), by fill year "
              "(columns: " + " / ".join(NI.KEPT_KEYS) + ")")
        for y, c in sorted(cnt.items()):
            print(f"    {y}: " + " ".join(f"{c.get(k, 0)}" for k in NI.KEPT_KEYS))


def print_spin_counts(label, cnt):
    """the spin-off / stock-dividend ex-dates (the calendar's rows RESMOM calls [D2] - in this file [D2] is the share counts, so never that label here) by fill year over the universe names of every rebalance: the names with a return left
    out of their 252-session window (names / sessions) and the names with an ex-date inside the hold (r17_resmom.print_spin_counts' numbers)"""
    print(f"  {label} spin-off / stock-dividend ex-dates by fill year (names with a return left out of their 252-session window: names / sessions; names with an ex-date inside the hold): " + "; ".join(
        f"{y}: {c.get('spin_window_names', 0):,} / {c.get('spin_window_sessions', 0):,} / {c.get('spin_hold_names', 0):,}" for y, c in sorted(cnt.items()) if c.get("rebalances", 0)))


def print_wide(ca):
    """r17_resmom.print_wide (the wide calendar's counts) with RESMOM's '[D2]' label left off its spin-off / stock-dividend line: in this file [D2] names the share counts ([B13])"""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        M17.print_wide(ca)
    print(buf.getvalue().replace("spin-offs / stock dividends [D2] (", "spin-offs / stock dividends (the spin-off / stock-dividend ex-dates; ").rstrip("\n"))


def b10_removed(cnt):
    """[B13] the pool name-months [B10]'s 'keep' reading removed for an in-hold event, from its counts by fill year (the first-reason counts post_calendar_split / post_spin)"""
    tot = sum((Counter(c_) for c_ in cnt.values()), Counter())
    return {"calendar_split": int(tot.get("post_calendar_split", 0)), "spin_off_or_stock_dividend": int(tot.get("post_spin", 0))}


def print_b10_reading(resA, removed, cnt_judged, cells):
    """[B13] [B10]'s removal reading printed beside the judged one as a REPORT (no null): its count of removed name-months, then per cell its row and net against the judged cell's"""
    cj = sum((Counter(c_) for c_ in cnt_judged.values()), Counter())
    print(f"  {LAB_A}, no null - it removed {removed['calendar_split']:,} pool name-months for a calendar split and {removed['spin_off_or_stock_dividend']:,} for a spin-off / stock-dividend ex-date inside the hold (the judged reading "
          f"keeps them: {cj.get('kept_calendar_split', 0):,} calendar splits on the split-safe path, {cj.get('closed_spin', 0):,} positions closed at the close before the ex-date):")
    for cell in CELLS:
        k = resA["cells"][cell]
        print(f"    {cell}: {row(cell, k)[4:]} | the judged net ${cells[cell]['base']['net']:,.0f} against this reading's ${k['base']['net']:,.0f}")


def print_spin_picks(spin):
    """per reading and cell, the PICKED positions with a spin-off / stock-dividend ex-date in the window (a return left out) or inside the hold (the judged reading closes them at the close before it) - r21_netiss.ni_spin_counts' numbers"""
    for reading, per in spin.items():
        for cell in CELLS:
            c = per[cell]
            print(f"  {reading} {cell} picks (long / short) and the spin-off / stock-dividend ex-dates: positions {c['long']['positions']:,} / {c['short']['positions']:,}; window (a return left out of the name's own series) "
                  f"{c['long']['window_positions']:,} / {c['short']['window_positions']:,} positions ({c['long']['window_sessions']:,} / {c['short']['window_sessions']:,} sessions left out); hold (an ex-date inside it) "
                  f"{c['long']['hold_positions']:,} / {c['short']['hold_positions']:,}")


# ------------------------------------------------------------------ the inputs, loaded once: the pinned files (cut at read), the World, the BUYBACK arrays
def load_sources(cut):
    """the pinned inputs of a stage, each refused if its sha256 differs (nothing computed, lockbox NOT read): NETISS's symbol -> CIK map and share-count facts (r21_netiss's loaders, read as ONE table each) and the two cash-flow extracts read as
    ONE table [B6] / [B7]; every one cut at READ time. The raw cash rows are released once the entries are built"""
    mp = NI.load_map()
    d, xinfo = NI.load_facts(cut)
    fx = NI.build_facts(d)
    del d
    cf, cinfo = load_cashflow(cut)
    cash = build_cash(cf)
    del cf
    assert_cut("cash-flow entries (first filed)", pd.DatetimeIndex(cash.E_f1.astype("datetime64[D]")), cut)
    return SimpleNamespace(mp=mp, fx=fx, xinfo=xinfo, cinfo=cinfo, cash=cash)


def load_world(cut, cal, src):
    """the World through r17_resmom's loaders (every input cut at `cut` inside the calls), TBIS and ES, NETISS's arrays and this family's attached -> (W, D's name count, TBIS rows, TBIS matched, ES meta)"""
    D = M17.load_data(cut)
    nfull = len(D.syms)
    tbis = D15.load_tbis(cut)
    es_frames, es_meta = D15.load_es(cut)
    full_match = D15.tbis_array(D.days, D.syms, tbis)[1]
    W = M17.build_world(D, cut, es_frames, tbis, cal)
    D15.release(D)
    cut_checks(W, cal, cut)
    attach_buyback(W, src.cash, src.fx, src.mp, cal)
    return W, nfull, tbis, full_match, es_meta


# ------------------------------------------------------------------ dryload: counts only
def dryload():
    """the WF inputs through every loader (cut at 2025-06-30) and COUNTS only: the pinned files as read (the cash-flow concepts' exact names, rows and CIKs; the drops; the entries; the periods), sessions, symbols, universe sizes, the names with a
    TTM and the scored names per rank and cell, every no-score reason, the TTM's formula, the concept used per component and the ZERO shares, the staleness buckets, [B2], [B3] (with the names of a year above 10%), [A13]'s second share classes,
    the rebalances and the pool / scored names per rebalance, the hygiene removals, TBIS rows, ES coverage. NO cash amount, share count, score value, return, P&L or Stage A statistic is printed: the scores are computed in memory only to COUNT
    the names each rule removes, no unit path is built"""
    prereg_ok()
    t0 = time.time()
    src = load_sources(S.LB0)
    cal, winfo = M17.wide_load(S.LB0, need=False, enforce=False)                              # CHOICE (r18's / NETISS's): the dryload counts on the calendar when it exists and REPORTS its sha status (only Stage A / B refuse an unregistered one)
    W, nfull, tbis, full_match, es_meta = load_world(S.LB0, cal, src)
    print(f"dryload: inputs ready ({time.time() - t0:.0f}s); every input cut to dates < {S.LB0:%Y-%m-%d}; ES masters {es_meta['raw']['filename']} / {es_meta['adj']['filename']}")
    wf = (W.days >= WF0) & (W.days <= PRE_END)
    print(f"sessions: {W.T:,} on the market calendar ({W.days[0]:%Y-%m-%d} .. {W.days[-1]:%Y-%m-%d}; the cache's first session is {CACHE_FIRST_SESSION:%Y-%m-%d}), {int(wf.sum()):,} inside the WF stretch; symbols: {nfull:,} in the cache after SIPORB's price / volume floor, {W.S:,} ever in the universe")
    usz, yrs = W.U.sum(axis=1), W.days.year.to_numpy()
    print("universe size per session by year (sessions with a universe: min / median / max): " + "; ".join(
        f"{y}: {int((m := (yrs == y) & (usz > 0)).sum())} sessions {int(usz[m].min())} / {int(np.median(usz[m]))} / {int(usz[m].max())}" for y in sorted(set(yrs)) if ((yrs == y) & (usz > 0)).any()))
    print_data_counts(src, W)
    print(f"  the calendar's start (the first date [A3]'s cross-check covers): {W.ni.cal_start if W.ni.cal_start is None else f'{W.ni.cal_start:%Y-%m-%d}'}")
    ranks = built_ranks(W, WF0, PRE_END)
    srows = score_report(W, ranks, values=False)
    print_score_report(srows, names=False)
    print_blind_spot(blind_spot(srows))
    Lc = bb_build(W, WF0, PRE_END, JUDGED, units=False, counts_only=True)
    print_second_classes(second_classes(Lc, W))
    r_all, f_all, x_all = M17.rm_schedule(W.days)
    inwf = [(r, f, x) for r, f, x in zip(r_all.tolist(), f_all.tolist(), x_all.tolist()) if x >= 0 and WF0 <= W.days[x] <= PRE_END]
    first_full = min((r for r, f, x in inwf if r >= M17.SPEC["win"] - 1), default=None)
    print(f"rebalances: {len(Lc.recs)} in WF (positions that exit {WF0:%Y-%m-%d} .. {PRE_END:%Y-%m-%d} with a full {M17.SPEC['win']}-session window)"
          + (f"; the first rank session with a full window is {W.days[first_full]:%Y-%m-%d} (filled {W.days[first_full + 1]:%Y-%m-%d})" if first_full is not None else "")
          + f"; {sum(1 for r, f, x in inwf if r < M17.SPEC['win'] - 1)} earlier ranks are warm-up; the stage's last rank has no next fill: unresolved, out")
    by = defaultdict(list)
    for rec in Lc.recs:
        by[int(W.days[rec.f].year)].append((rec.nu, rec.nfull, len(rec.pool)))
    print("names with a full window (>= 230 own returns and >= 230 ES pairs) per rebalance, by fill year (universe / full window / eligible pool: min - mean - max): " + "; ".join(
        f"{y}: {len(v)} rebalances, universe {min(a for a, b, c in v)}-{np.mean([a for a, b, c in v]):.0f}-{max(a for a, b, c in v)}, full {min(b for a, b, c in v)}-{np.mean([b for a, b, c in v]):.0f}-{max(b for a, b, c in v)}, "
        f"pool {min(c for a, b, c in v)}-{np.mean([c for a, b, c in v]):.0f}-{max(c for a, b, c in v)}" for y, v in sorted(by.items())))
    print_scored_stats(LAB_J, Lc, W)
    print_scored(f"judged [B13] (the fallback rule: {SPEC['min_scored']} scored names or more -> {M17.SPEC['n_side']} a side, fewer -> the top / bottom third, at least {SPEC['min_side']} a side, else nothing)", Lc.cnt)
    print_counts(LAB_J, Lc.cnt)
    La = bb_build(W, WF0, PRE_END, "keep", units=False, counts_only=True)                     # [B13] [B10]'s removal reading, reported: its pool counts beside the judged one's
    print_counts(LAB_A, La.cnt)
    print_spin_counts("judged [B13]", Lc.cnt)
    print(f"TBIS flags: {len(tbis):,} symbol-days listed before the cut, {full_match:,} match a session and a cached name, {W.tbis_rows[1]:,} a name that is ever in the universe; every listed row is a flag")
    if W.ca is not None:
        print_wide(W.ca)
    else:
        print(f"wide corporate-actions calendar [R1]: not on file yet ({winfo['path']}) - Stage A refuses until it is on file and WIDE_CA_SHA is set; this dryload ran without dividends and without [A3]'s calendar side")
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
def b3_gate(b3):
    """[B3]: a year above 10% of the universe names with a TTM reading ZERO everywhere makes the zero-reading rule suspect - Stage A REFUSES (no return computed, nothing written) until MANAGER's ruling is registered (a dated addendum: a new prereg
    sha and B3_RULING); the years and their names were printed just before -> the years above (none: Stage A goes on)"""
    above = [y for y, d in b3.items() if d["above"]]
    if above and B3_RULING is None:
        refuse(f"Stage A refused: [B3] the tag blind spot is above {BLIND_MAX:.0%} of the universe names with a TTM in {above} - the zero-reading rule is suspect; Stage A waits for MANAGER's ruling (a dated addendum and B3_RULING) - no return computed, "
               "nothing written")
    return above


def stage_a():
    if os.path.exists(os.path.join(OUT, READ_FLAG)):                                       # CHOICE (r17's / r18's / NETISS's): once the lockbox has been read Stage A is frozen (a re-run could change the cell or c after the fact)
        refuse(f"Stage A refused: Stage B has already read the lockbox - Stage A is frozen ({READ_FLAG})")
    pok = prereg_ok()
    cal, winfo = M17.wide_load(S.LB0)                                                      # [R1] refuses (nothing computed) when the wide calendar is not on file / not registered / not the registered file
    src = load_sources(S.LB0)                                                              # [B6] / [B7] / NETISS's files: refuse (nothing computed) when a pinned file is not on file / not the registered file / overlaps
    B, legs_meta = A13.load_463()                                                          # the book first: cheap, and a book that does not reproduce stops everything
    bk, dd, S12 = book_checks(B)
    print(f"BOOK #463 WF check (must be {BOOK_WF[0]} / {BOOK_WF[1]}): ROC@30k {bk['roc']:.2f} Sortino {bk['sortino']:.3f}; deepest drawdown ${dd['deepest']:,.0f} (must be ${DEEPEST_WF:,.0f}), "
          f"{dd['episodes']} qualifying episodes, {dd['days']} DD days, {dd['weeks']} DD weeks, by year {dd['by_year']}, the 2020-03-03 .. 03-27 episode {'found' if dd['episode_2020'] else 'NOT FOUND'}")
    if CHECK_BOOK and not (bk["ok"] and dd["ok"]):
        refuse("Stage A refused: the #463 records do not reproduce the registered WF numbers / drawdown structure (the prereg's [T5] facts) - fix the input first (nothing computed)")
    ref = DV.ref_load(B, check_facts=CHECK_BOOK)                                           # [B14] the S1-restated line -> the REFERENCE book L: refuses (nothing computed) unless the file is resmom_cells_daily_wf_close.csv (e204dd53) and L reproduces 121.06 / 3.926 / $36,526
    DV.print_reference(ref)
    print(f"  [B14] L is the S1-restated line ({os.path.basename(DV.REF_CSV_PINNED)}: the RESMOM restatement under MANAGER's hygiene edit S1); [B12]'s 'NETISS first' rule is settled - NETISS r1 is DEAD under S1, so NO NETISS line "
          "joins the reference")                                                           # [B12] / [B14]: this is where a NETISS forward line would have joined L - none does
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
    W.bb.split_ratio = split_ratios(winfo["path"], winfo["csv_sha256"], S.LB0)               # [B19] the split ratios the listing prints
    print(f"world ready ({time.time() - t0:.0f}s): {int(wf.sum()):,} WF sessions, {W.S:,} names ever in the universe, k_t (read only by the borrow stress rows) undefined on {kmiss} WF sessions; ES masters "
          f"{es_meta['raw']['filename']} / {es_meta['adj']['filename']}", flush=True)
    es_txt, es_rec = M17.es_report(W)
    print(es_txt)
    print_wide(W.ca)
    out = {"prereg_sha256_lf": PREREG_SHA, "prereg_verified": pok["verified"], "prereg_committed": pok["committed"], **stamp(), "judged": False, "stageA": None, "candidate": None, "pending_hand_audit": None, "judged_post_mode": JUDGED,
           "book_check": bk, "dd_structure": dd, "reference": DV.ref_record(ref), "manifest_sha256": msha, "es_return": es_rec, "wide_calendar": W.ca, "k_undefined_wf_sessions": kmiss, "files": {k: FILE_SHA[k] for k in FILE_SHA},
           "netiss_files": dict(NI.FILE_SHA), "cash_flow": {k: v for k, v in src.cinfo.items() if k != "sha256"}, "cash_entries": src.cash.info, "facts": {k: v for k, v in src.xinfo.items() if k != "sha256"},
           "map": {k: v for k, v in src.mp.info.items() if k != "sha256"}, "share_entries": src.fx.info}
    aud_n = apply_audit(W, audit)
    asha = file_sha(os.path.join(OUT, "buyback_audit.csv"))
    print("audit file: " + ("none yet" if audit is None else f"{aud_n['rows']} rows ({aud_n['keep']} keep, {aud_n['data_event']} data_event: removed from the cells AND the nulls, and with them {aud_n['group_name_months']} more name-month(s) of the same groups - the same symbol on the same filings)"))
    rows = A13.book_rows(B, W)
    # ---- BEFORE ANY P&L: the files, the score's counts and facts, [B2], [B3] (the leg is never built, nothing is costed)
    ranks = built_ranks(W, WF0, PRE_END)
    print_data_counts(src, W)
    srows = score_report(W, ranks, values=True)
    print_score_report(srows, names=True)
    unsc = unscored_by_name(W, ranks)
    print_unscored_by_name(unsc)
    sc2 = second_classes(bb_build(W, WF0, PRE_END, JUDGED, units=False, counts_only=True), W)        # [A13] counts only: the pool and the scored names, no unit path, no pick
    print_second_classes(sc2)
    b3 = blind_spot(srows)
    print_blind_spot(b3)
    out.update({"score_by_rank": [{k: v for k, v in r_.items() if k != "cells"} | {"cells": {c: {k: v for k, v in x.items() if k != "values"} for c, x in r_["cells"].items()}} for r_ in srows],
                "percentiles_by_year": {c: {int(y): pctl_text(np.concatenate([r_["cells"][c]["values"] for r_ in srows if r_["year"] == y])) for y in sorted({r_["year"] for r_ in srows})} for c in CELLS},
                "unscored_by_name": unsc, "second_share_class": sc2, "blind_spot_b3": b3})
    b3_gate(b3)                                                                            # [B3] above 10% of the names in any year: Stage A waits for MANAGER's ruling - nothing is computed after this
    # ---- the leg and its picks -> [B9] -> the null FIRST (the power line) -> the cells
    t1 = time.time()
    b9_box = {}

    def b9_print(L):
        b9_box["rows"] = b9_rows(W, L)
        print_b9(b9_box["rows"])
        b9_box["b19"] = b19_rows(W, L)                                                     # [B19] the picked positions with a calendar split the factor does not show - before any P&L
        print_b19(b9_box["b19"])
    resR, objR = evaluate(W, B, S12, ref, rows, JUDGED, NREP, 0, full=True, announce=print_power, b9=b9_print)
    print(f"judged reading [B13] done ({time.time() - t1:.0f}s: the leg, [B9], the {NREP} random-name draws per cell from the same SCORED pool with the same cut paths FIRST, the cells, the stress rows, the deciles, the twins)", flush=True)
    unused = unused_audit_rows(W, audit)
    if unused:
        print(f"  NOTE: {len(unused)} audit data_event row(s) removed nothing (the name was not in that fill session's universe): {unused[:5]}")
    t1 = time.time()
    resA, objA = evaluate(W, B, S12, ref, rows, "keep", 0, 3, full=False)                 # [B13] [B10]'s removal reading: a REPORT beside the judged one, with its count of removed name-months, without a null (r21_netiss's resA)
    cntA, spinA = {y: dict(c) for y, c in sorted(objA.legs.cnt.items())}, {c: NI.ni_spin_counts(objA.legs, c) for c in CELLS}
    del objA                                                                               # (its leg's unit paths are not read again)
    print(f"[B10]'s removal reading done ({time.time() - t1:.0f}s)", flush=True)
    t1 = time.time()
    nq = netiss_question(W, B, rows, objR.legs, objR, ref)
    print(f"the NETISS question done ({time.time() - t1:.0f}s: NETISS's two cells in-process on this World)", flush=True)
    spin = {"judged_reading": {c: NI.ni_spin_counts(objR.legs, c) for c in CELLS}, "b10_removal_reading": spinA}
    rep, cands = reports(W, B, S12, ref, rows, objR, resR["cells"], tbis, D15.asset_status(), legs_meta)
    cells = resR["cells"]
    passing, cand = stage_a_flow(cells)
    flags = flag15_rows(W, ranks, objR.legs)                                               # (f) every flagged name-rank, with whether the registered leg PICKED it (so after the leg)
    ast = audit_status(W, cands, flags, audit)
    os.makedirs(OUT, exist_ok=True)
    b19c = b19_candidate_rows(W, objR.legs, b9_box["b19"])                                  # [B19] the listed positions join the hand audit's candidates as data-event candidates
    pd.DataFrame([{"list": "top_contributor", "data_event_candidate": False, **r_} for c in CELLS for r_ in cands[c]] + b19c).to_csv(os.path.join(OUT, "buyback_audit_candidates.csv"), index=False)
    pd.DataFrame(flags).to_csv(os.path.join(OUT, "buyback_flags.csv"), index=False)
    print(f"WF {WF0:%Y-%m-%d} -> {PRE_END:%Y-%m-%d} ({int(wf.sum()):,} sessions) - {LAB_J}; the null draws from the same SCORED pool with the same cut paths")
    print_cells(resR, ast)
    removedA = b10_removed(cntA)
    print_b10_reading(resA, removedA, objR.legs.cnt, cells)
    print_spin_picks(spin)
    print_twins(resR)
    print_netiss_question(nq, resR)
    print_deciles(resR)
    print_reports(rep, cells)
    print_diagnostics(resR, rep, ref)
    print_counts("L (judged [B13])", objR.legs.cnt)
    print_counts("L ([B10]'s removal reading, reported)", cntA)
    print_scored("L (judged [B13])", objR.legs.cnt)
    print_spin_counts("L (judged [B13])", objR.legs.cnt)
    print(f"  audit candidates (the {AUDIT_N} largest gains per cell, with every component fact, its filing (accession number [B4]), the market value's inputs and the group) -> {os.path.join(OUT, 'buyback_audit_candidates.csv')}; every |score| > 0.15 name-rank "
          f"({len(flags):,}; picked: {sum(1 for r_ in flags if r_['picked']):,}, in {len({r_['group'] for r_ in flags if r_['picked']}):,} groups) with the cell / side that picked it and its group -> {os.path.join(OUT, 'buyback_flags.csv')}; the hand audit (f) covers the "
          f"{AUDIT_N} largest contributors per cell and every PICKED flagged name-rank, grouped by (symbol, the filings used): ONE row covers every rank on the same filings, a data_event row removes them all; the hand audit is the lead's (a data event found: "
          "a row symbol, date, cell, data_event in buyback_audit.csv and run stage_a again); audit rows found per list: " + ", ".join(f"{k} top-{AUDIT_N} {v['audited']}/{v['listed']}, picked flagged groups {v['flag_audited']}/{v['flag_listed']}" for k, v in ast.items()))
    out.update({"judged": True, "pending_hand_audit": passing, "b9_by_rank": b9_box.get("rows"),
                "stageA": {"cells": cells, "twins": resR["twins"], "null": resR["null"], "pass_cells": passing},
                "candidate": ({"cell": cand, "c": cells[cand]["A2"]["c"], "std_book": cells[cand]["A2"]["std_book"], "std_cell": cells[cand]["A2"]["std_cell"], "window": cells[cand]["A2"]["window"], "a2_book_roc": cells[cand]["A2"]["roc"],
                               "a2_reference_roc": cells[cand]["A2"]["reference"]["roc"], "incremental_pass": cells[cand]["A2"]["incremental_pass"], "incremental_credit": cells[cand]["A2"]["incremental_credit"],
                               "book_shadow_line": cells[cand]["A2"]["incremental_credit"], "beta_within_cap": cells[cand]["beta"]["within_cap"], "first_traded_fill": cells[cand]["first_traded_fill"], "also_passes": [c for c in passing if c != cand]} if cand else None),
                "parity": {c: {"net": cells[c]["base"]["net"], "n_pos": cells[c]["base"]["n_pos"], "n_units": cells[c]["base"]["n_units"], "first_traded_fill": cells[c]["first_traded_fill"]} for c in CELLS},
                "b19_split_no_factor_move": b9_box["b19"], "audit": aud_n, "audit_sha256": asha, "audit_status": ast, "flags": len(flags), "flags_picked": int(sum(1 for r_ in flags if r_["picked"])), "flags_picked_groups": int(len({r_["group"] for r_ in flags if r_["picked"]})),
                "spin_counts": spin, "netiss_question": nq, "calendar_splits_on_grid": W.ni.csplit,
                "b10_removal_reading": {"post_mode": "keep", "null": resA["null"], "removed_name_months": removedA, "cells": {c: {k: resA["cells"][c][k] for k in ("base", "seat", "A2", "usd_year", "dd5")} for c in CELLS}},
                "hygiene_counts_by_year": {"judged": {y: dict(c) for y, c in sorted(objR.legs.cnt.items())}, "b10_removal": cntA}, "reports": rep, "es_masters": es_meta})
    dump(out, "buyback_stageA.json")
    for c in passing:
        a2 = cells[c]["A2"]
        print(f"Stage A (a)-(e) pass, (f) awaits the hand audit - cell {c}; WF ROC@30k {cells[c]['base']['roc']:.1f} / {dd5_txt(cells[c]['dd5'])} (${cells[c]['usd_year']:,.0f} a year); A2 (a report): c x{a2['c']:.4g} set by volatility, REFERENCE + c x cell ROC@30k "
              f"{a2['roc']:.2f} / Sortino {a2['sortino']:.3f} against the reference's {a2['reference']['roc']:.2f} / {a2['reference']['sortino']:.3f} -> " + ("an INCREMENTAL PASS: MANAGER #70's gate follows (the cell's DO and its null's on the reference's drawdown days), then at most one forward book line"
                                                                                                                     if a2["incremental_credit"] else "no credited incremental pass: no book line" + (" (the numbers pass, the beta rule refuses the credit)" if a2["incremental_pass"] else "")))
    if passing:
        print(f"BUYBACK Stage A: (a)-(e) pass for {passing}; (f) AWAITS THE HAND AUDIT of the {AUDIT_N} largest contributors and the picked |score| > 0.15 name-ranks, grouped by their filings [B4] (the harness never decides it); candidate {cand}. Stage B needs the lead's "
              f"go-flag {GO_FLAG} (written after the hand audit, on the stock families' one sealed-year day) and the lockbox year's pinned extracts (LB_CASHFLOW and NETISS's LB_FACTS: the same photographed zip, extracted by TV, pinned by sha256 in a dated addendum).")
    else:
        print("BUYBACK Stage A: FAIL - no cell passes (a)-(e) (" + "; ".join(f"{c}: " + ", ".join(k for k, v in cells[c]['checks'].items() if not v) for c in CELLS) +
              ") - BUYBACK r1 is dead; no other yields, horizons, concepts or thresholds are tried; the lockbox stays sealed.")
    pm = peak_mb()
    print(f"stage_a took {time.time() - t0:.0f}s" + (f", peak memory {pm:,.0f} MB" if pm else ""))
    return out


# ------------------------------------------------------------------ Stage B: the one read (refuses unless the lead's go-flag is on file)
def lb_pinned():
    """the lockbox year's two pinned extracts: this family's cash flows (LB_CASHFLOW, both files) AND NETISS's share counts (r21_netiss.LB_FACTS) - the market value needs both"""
    return isinstance(LB_CASHFLOW, dict) and set(LB_CASHFLOW) == set(CF_KEYS) and isinstance(NI.LB_FACTS, dict) and set(NI.LB_FACTS) == {"facts", "facts_add"}


def stage_b():
    """STAGE B (LB, once, on the stock families' one sealed-year day): REFUSES unless the lead's go-flag buyback_stageB_GO.flag is on file (its EXISTENCE is the sign-off - its text is stored with the read, never parsed), a Stage A candidate is on
    file AND the lockbox year's facts are pinned - the cash flows (LB_CASHFLOW) and NETISS's share counts (r21_netiss.LB_FACTS): the pinned extracts stop at filed 2025-06-27, so the sealed year's facts come from the same photographed zip,
    extracted by TV only after a Stage A pass and pinned by sha256 in a dated addendum before one is read (NETISS [A17]); None = refuse. The sealed year is the LEG's standalone veto (r17_resmom's: >= 10 monthly rebalances, net > 0, net > 0
    without its top name-month); the book add (#463 + c x the cell at Stage A's frozen c) is computed, printed and stored as book_add_reported - NEVER part of the pass. Every refusal is before the read flag; the flag is written (exclusively)
    only after every load, every check and the whole result are in hand"""
    go, flag = os.path.join(OUT, GO_FLAG), os.path.join(OUT, READ_FLAG)
    if not os.path.exists(go):
        refuse(f"Stage B refused: the lead's go-flag {GO_FLAG} is not on file - the hand audit (f) and the sealed-year day are the lead's call; the lockbox stays sealed {TAIL}")
    if os.path.exists(flag):
        refuse(f"Stage B refused: the lockbox was already read once ({READ_FLAG})")
    pa = os.path.join(OUT, "buyback_stageA.json")
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
    if sa.get("audit_sha256") != file_sha(os.path.join(OUT, "buyback_audit.csv")):
        refuse("Stage B refused: buyback_audit.csv is not the file Stage A ran with (it changed, or went missing) - run stage_a again (lockbox NOT read)")
    cell = cand["cell"]
    try:
        c = float(cand["c"])
    except (TypeError, ValueError):
        c = float("nan")
    if cell not in CELLS or not (math.isfinite(c) and c > 0):                                  # c is a volatility ratio: any positive number is a frozen size, but NaN / 0 / missing is a broken file
        refuse(f"Stage B refused: the frozen cell {cand.get('cell')} / size c {cand.get('c')} is not one of {CELLS} / a positive number (lockbox NOT read)")
    try:
        win = tuple(TS(d) for d in cand["window"])
        assert len(win) == 2 and win[0] <= win[1]
    except (TypeError, ValueError, KeyError, AssertionError):
        refuse(f"Stage B refused: the frozen size's window {cand.get('window')} is not two readable dates (lockbox NOT read)")
    if not lb_pinned():
        refuse("Stage B refused: the lockbox year's facts are not pinned (LB_CASHFLOW and r21_netiss.LB_FACTS: the pinned extracts stop at filed 2025-06-27 - the sealed year's cash-flow and share-count facts come from the same photographed zip (db35d36b), extracted by TV "
               "with the same tool after a Stage A pass, and a dated pre-data addendum must pin both extracts by sha256, filed through 2026-06-30, before Stage B can read one fact of the sealed year) - lockbox NOT read")
    go_text = open(go).read()[:500]
    lb_files, lb_shas = {**FILES, **{k: v[0] for k, v in LB_CASHFLOW.items()}}, {**FILE_SHA, **{k: v[1] for k, v in LB_CASHFLOW.items()}}
    B, legs_meta = A13.load_463()                                                              # every input is loaded and checked BEFORE the flag: a bad file cannot burn the lockbox
    bk = A13.book_check(B, LB0, LB1, BOOK_LB)
    print(f"BOOK #463 LB check (must be {BOOK_LB[0]} / {BOOK_LB[1]}): ROC@30k {bk['roc']:.2f} Sortino {bk['sortino']:.3f}")
    if CHECK_BOOK and not bk["ok"]:
        refuse("Stage B refused: the #463 records do not reproduce its LB numbers - settle the end-date convention first (lockbox NOT read)")
    msha = manifest_sha()
    if CHECK_BOOK and not (msha and msha.startswith(D15.MANIFEST_PREFIX) and msha == sa.get("manifest_sha256")):
        refuse("Stage B refused: the SIPORB cache manifest is not the one Stage A ran on (a re-pull must never be mixed in) - lockbox NOT read")
    cal, winfo = M17.wide_load(S.END)                                                          # the same registered calendar, cut at the lockbox's end
    with patched(THIS, FILES=lb_files, FILE_SHA=lb_shas), patched(NI, FILES={**NI.FILES, **{k: v[0] for k, v in NI.LB_FACTS.items()}}, FILE_SHA={**NI.FILE_SHA, **{k: v[1] for k, v in NI.LB_FACTS.items()}}):
        src = load_sources(S.END)                                                              # the lockbox year's extracts read through the same loaders, under their own pinned shas
    audit = read_audit()
    W, nfull, tbis, _fm, es_meta = load_world(S.END, cal, src)
    apply_audit(W, audit)
    rows = A13.book_rows(B, W)
    hole_txt, hole_rec = M17.es_report(W, LB0, LB1)                                            # the ES holes that reach the lockbox: printed and stored with the read
    Lw = bb_build(W, WF0, PRE_END, JUDGED)                                                     # Stage A's WF numbers (and the frozen c) must reproduce on Stage B's data (a cache or code drift stops it BEFORE the read)
    run = M17.run_cell(W, cell_leg(Lw, cell), D15.l1_cfg())                                    # CHOICE: only the candidate cell is re-read (it is the only one Stage B reads)
    xw = D15.to_B(run.x, rows, B.n)
    st, ref = D15.cell_stats(B, xw, D15.to_B(run.cnt, rows, B.n), WF0, PRE_END, run), sa["parity"][cell]
    print(f"WF re-read on Stage B's data: {cell} positions {st['n_pos']:,} (Stage A {ref['n_pos']:,}), net ${st['net']:,.0f} (Stage A ${ref['net']:,.0f})")
    d0 = first_fill(W, Lw, cell)
    if st["n_pos"] != ref["n_pos"] or st["n_units"] != ref["n_units"] or abs(st["net"] - ref["net"]) > max(1.0, 1e-6 * abs(ref["net"])) or (None if d0 is None else f"{d0:%Y-%m-%d}") != ref.get("first_traded_fill"):
        refuse(f"Stage B refused: the WF numbers of {cell} do not reproduce on Stage B's data - the cache or the code changed since Stage A (lockbox NOT read)")
    c2 = plain_a2(B, xw, win)["c"]
    print(f"  frozen size {cell}: c x{c:.6g} (Stage A) vs x{c2:.6g} recomputed from {win[0]:%Y-%m-%d} .. {win[1]:%Y-%m-%d} on Stage B's data")
    if not (math.isfinite(c2) and abs(c2 - c) <= 1e-9 * c) or a2_window(d0) != win:
        refuse(f"Stage B refused: the volatility-set size c of {cell} does not reproduce on Stage B's data - the cache or the code changed since Stage A (lockbox NOT read)")
    L = bb_build(W, LB0, LB1, JUDGED)                                                          # CHOICE (r15's order): the whole LB result is computed, nothing shown, BEFORE the flag
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
    cands = bb_candidate_rows(W, L, cell, run, tbis, D15.asset_status(), 20)
    text = json.dumps({"cell": cell, "c": c, "window": [f"{win[0]:%Y-%m-%d}", f"{win[1]:%Y-%m-%d}"], "go_flag": go_text, "book_check": bk, "es_masters": es_meta, "leg": leg, "checks": chk, "pass": bool(ok), "book_add_reported": add, "es_return_lb": hole_rec,
                       "wide_calendar": W.ca, "lockbox_cash_flow": {k: v for k, v in src.cinfo.items() if k != "sha256"}, "lockbox_cash_flow_sha256": {k: lb_shas[k] for k in CF_KEYS}, "lockbox_facts_sha256": {k: v[1] for k, v in NI.LB_FACTS.items()},
                       "lockbox_facts": {k: v for k, v in src.xinfo.items() if k != "sha256"}, "hygiene_counts_by_year": cnt, "top_name_months": cands, **stamp(), "prereg_sha256_lf": PREREG_SHA}, indent=1, default=R11.js)
    buf = io.StringIO()                                                                        # the whole printout is built here, before the flag: a formatting error cannot burn the lockbox
    with contextlib.redirect_stdout(buf):
        print("Stage B (lockbox, read once) - the sealed year is the LEG's standalone veto")
        print(f"  {cell}: positions {leg['n_pos']:,}, monthly rebalances {leg['n_units']:,}, net ${leg['net']:,.0f}, ROC@30k {leg['roc']:.1f}, Sortino {leg['sortino']:.2f}; its top name-month ${leg['top_pos']:,.0f}, net without it ${leg['net_ex_top_pos']:,.0f}")
        print("  " + hole_txt)
        print("  Stage B checks: " + ", ".join(k + (" ok" if v else " FAIL") for k, v in chk.items()) + f" -> {'PASS' if ok else 'FAIL'}")
        print(f"  book add, REPORTED and never part of the pass: #463 + {cell} x{c:.4g} (frozen): LB ROC@30k {r['roc']:.2f} Sortino {r['sortino']:.3f} net ${r['net']:,.0f} -> would {'have' if would else 'NOT have'} cleared {RULES['b_roc']:g} / {RULES['b_sort']:g}")
        print("BUYBACK Stage B: " + ("PASS - the leg survives its sealed year: it goes to a computed no-order FORWARD SHADOW (Stage C) with its own bar, logged by research id; the book add above is a report - "
                                     "the forward record decides any book add, and opening any account is the owner's decision (owner call)." if ok else
                                     "FAIL - the leg is vetoed by its sealed year: BUYBACK r1 is dead; ledger + memory."))
    with open(flag, "x") as f:                                                                 # exclusive create: the one read starts here - what is left is two writes and a print
        f.write(pd.Timestamp.now().isoformat())
    with open(os.path.join(OUT, "buyback_stageB.json"), "w") as f:
        f.write(text)
    print(buf.getvalue().rstrip())
    pm = peak_mb()
    if pm:
        print(f"peak memory {pm:,.0f} MB")
    return ok


# ------------------------------------------------------------------ test support: hand-made cash-flow filings, hand-made worlds, and plain-python recounts of every entry, TTM, score, pool, pick and path (independent of the vectorised code)
quiet, refused, close = NI.quiet, NI.refused, NI.close
DEI, GAAP = NI.DEI, NI.GAAP
AL = {"ST": C_ST[0], "STC": C_ST[1], "REP": C_REP[0], "REPE": C_REP[1], "DIV": C_DIV[0], "DIVA": C_DIV[1], "ISS": C_ISS[0], "ISSE": C_ISS[1], "IPO": C_ISS[2], "OPT": C_PLAN[0], "PLNO": C_PLAN[1], "PLN": C_PLAN[2], "PLAN": C_PLAN[3], "TW": C_TW[0]}
CUT_ALL = "2030-01-01"                       # a cut past every hand-made date (the tests that are not about the cut)


def dnum(d):
    """a date -> its day number (days since 1970-01-01)"""
    return int(np.datetime64(TS(d).date(), "D").astype(np.int64))


def cf_frame(rows):
    """hand-made cash-flow rows -> the extract's layout, every column a string (as the loader reads it). A row = (cik, concept, val, start, end, filed[, accn[, form[, unit]]]); the concept may be a short name of AL; the accession defaults to one per
    (cik, end, filed) - one filing - and the form to 10-Q; val None = an empty cell"""
    out = []
    for r in rows:
        cik, con, val, start, end, filed = r[:6]
        accn = r[6] if len(r) > 6 and r[6] is not None else f"{cik}-{end}-{filed}"
        form = r[7] if len(r) > 7 and r[7] is not None else "10-Q"
        unit = r[8] if len(r) > 8 and r[8] is not None else "USD"
        out.append({"cik": cik, "symbols": "S;T", "concept": AL.get(con, con), "unit": unit, "val": "" if val is None else repr(float(val)) if isinstance(val, (int, float)) else str(val), "start": start, "end": end, "accn": accn,
                    "fy": "", "fp": "", "form": form, "filed": filed, "frame": ""})
    return pd.DataFrame(out, columns=list(CF_HDR)).astype(str)


def cf_of(rows, cut=CUT_ALL):
    """hand-made rows -> the cash table through the loader's own parser (cf_chunk / cf_finish), as if read from one extract"""
    I, cnt = new_interns(), Counter()
    parts = [cf_chunk(cf_frame(rows), TS(cut), 0, I, cnt)] if rows else []
    return cf_finish(parts, I)


def write_cf(path, rows, header=CF_HDR, crlf=False):
    """a cash-flow extract in the registered layout (13 columns) from hand-made rows -> its sha256 (of the bytes)"""
    df = cf_frame(rows)
    lines = [",".join(header)] + [",".join(str(rec.get(c, "")) for c in header) for rec in df.to_dict("records")]
    with open(path, "w", newline="") as f:
        f.write(("\r\n" if crlf else "\n").join(lines) + ("\r\n" if crlf else "\n"))
    return M17.sha_raw(path)


def brute_cash(rows, cut=CUT_ALL):
    """plain python over hand-made rows: the rows the loader keeps (a registered concept, USD, readable dates, start <= end, filed and end before the cut), then per (cik, concept, start, end) the FIRST filed row (ties: the smallest accession string)
    -> {(cik, concept, start day, end day): (f1 day, value, usable, accn, form)}; AMBIGUOUS when the first day's rows carry more than one distinct finite value; unusable when ambiguous, missing, the end after f1, or a negative component value"""
    by = defaultdict(list)
    cd = dnum(cut)
    for r in cf_frame(rows).to_dict("records"):
        con = r["concept"].strip()
        try:
            s, e, f = dnum(r["start"]), dnum(r["end"]), dnum(r["filed"])
        except (ValueError, TypeError):
            continue
        if con not in CIX or r["unit"].strip() != "USD" or s > e or f >= cd or e >= cd:
            continue
        try:
            v = float(r["val"]) if r["val"].strip() != "" else float("nan")
        except ValueError:
            v = float("nan")
        by[(r["cik"].strip(), con, s, e)].append((f, r["accn"].strip(), v, r["form"].strip().upper()))
    out = {}
    for key, lst in by.items():
        f1 = min(x[0] for x in lst)
        at = sorted(((a, v, fm) for f, a, v, fm in lst if f == f1), key=lambda t: t[0])          # the smallest accession (a stable sort: one accession twice keeps the file's order, as the loader's lexsort does)
        vals = {v for _a, v, _fm in at if math.isfinite(v)}
        v0 = at[0][1]
        ok = len(vals) <= 1 and math.isfinite(v0) and not key[3] > f1 and not (v0 < 0 and key[1] not in C_ST)
        out[key] = (f1, v0, ok, at[0][0], at[0][2])
    return out


def ptype_py(s, e):
    return next((t for t, _nm, a, b in PTYPES if a <= e - s <= b), T_OTHER)


def brute_grid(s, e0):
    """plain python [B15](9): is day s within 14 days of e0 + 1 day + 3q months for some q that is not a multiple of 4 (the month arithmetic by hand: the day clipped to the target month's length)"""
    epoch = TS("1970-01-01")
    b = epoch + pd.Timedelta(days=int(e0) + 1)
    q = 1
    while True:
        y, m = divmod(b.month - 1 + 3 * q, 12)
        Y, M = b.year + y, m + 1
        last = (TS(year=Y + (M == 12), month=M % 12 + 1, day=1) - pd.Timedelta(days=1)).day
        g = (TS(year=Y, month=M, day=min(b.day, last)) - epoch).days
        if g > s + FY_GAP:
            return False
        if q % 4 and abs(s - g) <= FY_GAP:
            return True
        q += 1


def brute_discrete(use, p0, e0):
    """plain python [B15](9): the statement p0 is a quarter on FY_prev's quarter grid and no usable entry of the CIK first filed on a transition report (10-KT / 10-QT, amendments included) ends after FY_prev's end e0"""
    return ptype_py(*p0) == T_Q and brute_grid(p0[0], e0) and not any(v[4] in TRANSITION_FORMS and k[3] > e0 for k, v in use.items())


def brute_ttm(ent, cik, r, dl_i):
    """plain python TTM of one cash CIK at rank row r: the usable entries (the first session strictly after the first filed date on or before r), the candidates (a typed period with a usable STATEMENT fact), the statement = the latest end (the
    longest on a tie), a FY -> itself; else FY_prev = the latest FY candidate ending on / before s - 1 (none: no FY_prev; ending more than 14 days before s: [B1], or [B15](9)'s discrete quarter by brute_discrete), YTD_prev = the candidate of
    the statement's type with FY_prev's start whose end is
    within 14 days of e - 1 year (the closest, a tie to the earlier) -> (code or None, kind, [(period, sign)], e, s, the usable entries)"""
    use = {k: v for k, v in ent.items() if k[0] == cik and v[2] and bisect.bisect_right(dl_i, v[0]) <= r}
    periods = {(k[2], k[3]) for k in use}
    cands = [p for p in periods if ptype_py(*p) > 0 and any((cik, c, p[0], p[1]) in use for c in C_ST)]
    if not cands:
        return R_NO_STATEMENT, 0, [], -1, -1, use
    p0 = max(cands, key=lambda p: (p[1], p[1] - p[0]))
    s, e = p0
    if ptype_py(*p0) == T_FY:
        return None, 1, [(p0, 1.0)], e, s, use
    fys = [p for p in cands if ptype_py(*p) == T_FY and p[1] <= s - 1]
    if not fys:
        return R_NO_FY_PREV, 2, [], e, s, use
    p1 = max(fys, key=lambda p: (p[1], p[1] - p[0]))
    if s - p1[1] > FY_GAP:
        return (R_DISCRETE_Q if brute_discrete(use, p0, p1[1]) else R_FY_CHANGE), 2, [], e, s, use
    tgt = dnum(NI.years_back_py(TS(np.datetime64(e, "D")), 1))
    ys = [p for p in cands if ptype_py(*p) == ptype_py(*p0) and p[0] == p1[0] and abs(p[1] - tgt) <= YTD_GAP]
    if not ys:
        return R_NO_YTD_PREV, 2, [], e, s, use
    p2 = min(ys, key=lambda p: (abs(p[1] - tgt), p[1]))
    return None, 2, [(p0, 1.0), (p1, 1.0), (p2, -1.0)], e, s, use


def brute_comp(use, cik, p):
    """plain python components of one period: REP / DIV the first concept with a usable fact, else the fallback, else ZERO; TW likewise; ISS the first present primary + every stock-plan concept present, an item with the same (accession, value)
    as an earlier one counted once [B7]; none of the seven = ZERO"""
    get = lambda c: use.get((cik, c, p[0], p[1]))
    out = {}
    for nm, cons in (("rep", C_REP), ("div", C_DIV), ("tw", C_TW)):
        e = next((get(c) for c in cons if get(c) is not None), None)
        out[nm] = e[1] if e else 0.0
        out[nm + "_zero"] = e is None
    prim = next((get(c) for c in C_ISS if get(c) is not None), None)
    items = ([prim] if prim else []) + [get(c) for c in C_PLAN if get(c) is not None]
    tot, seen = 0.0, []
    for it in items:
        if (it[3], it[1]) not in seen:
            tot += it[1]
        seen.append((it[3], it[1]))
    out["iss"], out["iss_zero"] = tot, not items
    return out


def brute_share(W, sh_frame, cik, r, cache):
    """plain python S(r): the usable cover-page entry with the latest as-of date, else the balance sheet's (r21_netiss.brute_entries' first-filed rule, usable from the first session strictly after the first filed date) -> (as-of Timestamp, value,
    concept) or None"""
    dl = NI.dlist(W)
    for con in (DEI, GAAP):
        if (cik, con) not in cache:
            cache[(cik, con)] = NI.brute_entries(sh_frame, cik, con)
        use = {end: v for end, v in cache[(cik, con)].items() if v[2] and bisect.bisect_right(dl, v[0]) < len(dl) and bisect.bisect_right(dl, v[0]) <= r}
        if use:
            a = max(use)
            return a, use[a][1], con
    return None


def brute_s_stale(a, rd):
    """plain python [B17]: is S's as-of date a more than 15 calendar months before the rank date rd (the month arithmetic by hand: rd's day clipped to the target month's length; that day itself is within)"""
    y, m = divmod(rd.year * 12 + rd.month - 1 - S_MONTHS, 12)
    M = m + 1
    last = (TS(year=y + (M == 12), month=M % 12 + 1, day=1) - pd.Timedelta(days=1)).day
    return TS(a) < TS(year=y, month=M, day=min(rd.day, last))


def brute_score(W, ent, sh_frame, cal, j, r, cache):
    """plain python BUYBACK scores of name j at rank row r -> SimpleNamespace(code {key}, score {key} (NaN unless scored), kind, e, rep / div / iss / tw, mv, flag {key}, zero (REP / ISS read zero on some period)): the static reasons (NETISS's map /
    [A4]; no cash-flow fact for the CIK), brute_ttm, stale (e more than 200 days before r), a negative component TTM (per score), the market value (no share fact for the CIK, no S, S not positive, no factor / close, [A3] both ways on (a, r] where the
    calendar covers a), |score| > 0.50"""
    nan = float("nan")
    out = SimpleNamespace(code={k: R_SCORED for k in CODE_KEYS}, score={k: nan for k in CODE_KEYS + ("DIV", DECK)}, flag={k: False for k in CODE_KEYS}, kind=0, e=-1, rep=nan, div=nan, iss=nan, tw=nan, mv=nan, zero=(False, False),
                          has_ttm=False, zero_all=(False, False, False), periods=[], cik="", share=None)
    setc = lambda c: out.code.update({k: c for k in CODE_KEYS})
    st = NI_STATIC.get(int(W.ni.static[j]), R_SCORED)
    mp = W.ni.mp.df
    row = mp[mp["symbol"] == str(W.syms[j])]
    cik = str(row["cik"].iloc[0]) if len(row) else ""
    out.cik = cik
    idx = cache.get("__ent_by_cik__")
    if idx is None or idx[0] is not ent:                                     # the entries of each CIK, indexed once per recount (a plain dict of dicts)
        by = defaultdict(dict)
        for k_, v_ in ent.items():
            by[k_[0]][k_] = v_
        idx = cache["__ent_by_cik__"] = (ent, dict(by))
    ent_c = idx[1].get(cik, {})
    if st == R_SCORED and not ent_c:
        st = R_NO_CF
    if st != R_SCORED:
        setc(st)
        return out
    dl_i = cache.get("__dl_i__")
    if dl_i is None:
        dl_i = cache["__dl_i__"] = [int(v) for v in W.ni.days_i]
    code, kind, plist, e, s, use = brute_ttm(ent_c, cik, r, dl_i)
    out.kind, out.e = kind, e
    if code is not None:
        setc(code)
        return out
    comps = [(brute_comp(use, cik, p), sg) for p, sg in plist]
    for nm in ("rep", "div", "iss", "tw"):
        setattr(out, nm, sum(sg * c[nm] for c, sg in comps))
    out.zero = (any(c["rep_zero"] for c, _sg in comps), any(c["iss_zero"] for c, _sg in comps))
    out.zero_all = tuple(all(c[f"{nm}_zero"] for c, _sg in comps) for nm in ("rep", "div", "iss"))
    out.has_ttm, out.periods, out.use = True, [p for p, _sg in plist], use
    sh = None if int(W.ni.static[j]) == NI.R_NO_FACTS else brute_share(W, sh_frame, cik, r, cache)
    out.share = sh                                                            # (S at r is read for a stale name too: the audit group of a name-rank lists it)
    if dl_i[r] - e > STALE_DAYS:
        setc(R_STALE)
        return out
    mv_code = None
    if int(W.ni.static[j]) == NI.R_NO_FACTS:
        mv_code = R_NO_SHARES
    elif sh is None:
        mv_code = R_NO_S
    elif brute_s_stale(sh[0], W.days[r]):
        mv_code = R_STALE_S
    elif not sh[1] > 0:
        mv_code = R_S_NOT_POS
    else:
        a, Sv, _con = sh
        dl = NI.dlist(W)
        ia = bisect.bisect_right(dl, a) - 1
        fa, fr, cl = (float(W.F[ia, j]) if ia >= 0 else nan), float(W.F[r, j]), float(W.Cl[r, j])
        if not (ia >= 0 and all(math.isfinite(v) and v > 0 for v in (fa, fr, cl))):
            mv_code = R_NO_FACTOR
        else:
            cs0 = NI.cal_start_of(cal)
            covered = cs0 is not None and a >= cs0
            fch, crow = NI.brute_fchg(W, j), NI.brute_calrows(W, cal, j)
            near = lambda q, qs: any(abs(q - t) <= NI.SPLIT_NEAR for t in qs)
            un_c = [q for q in crow if ia < q <= r and not near(q, fch)]
            un_f = [q for q in fch if ia < q <= r and not near(q, crow)]
            if covered and un_c:
                mv_code = R_SPLIT_C
            elif covered and un_f:
                mv_code = R_SPLIT_F
            else:
                out.mv = cl * Sv * fa / fr
    rep, div, iss, tw = out.rep, out.div, out.iss, out.tw
    num = {"P": rep + div - iss, "R": rep - iss, "P8": rep + tw + div - iss, "R8": rep + tw - iss}
    neg = {"P": rep < 0 or div < 0 or iss < 0, "R": rep < 0 or iss < 0}
    neg["P8"], neg["R8"] = neg["P"] or tw < 0, neg["R"] or tw < 0
    for k in CODE_KEYS:
        if neg[k]:
            out.code[k] = R_NEG_TTM
        elif mv_code is not None:
            out.code[k] = mv_code
        else:
            sc = num[k] / out.mv
            if abs(sc) > SCORE_MAX:
                out.code[k] = R_OVER50
            else:
                out.score[k], out.flag[k] = sc, abs(sc) > FLAG
    if out.code["P"] == R_SCORED:
        out.score["DIV"] = div / out.mv
    if out.code["R"] == R_SCORED:
        out.score[DECK] = rep / out.mv
    return out


def compare_scores(W, ent, sh_frame, cal, ranks, cols=None):
    """the vectorised score_rank against brute_score: every name (or `cols`) at every rank, every key's code, score and flag, the TTM's kind and e, the TTMs and the market value of the scored -> the number of name-ranks checked"""
    n = 0
    cache = {}
    cols = range(W.S) if cols is None else cols
    for r in ranks:
        sc = score_rank(W, r)
        for j in cols:
            b = brute_score(W, ent, sh_frame, cal, j, r, cache)
            tag = (str(W.syms[j]), f"{W.days[r]:%Y-%m-%d}")
            for k in CODE_KEYS:
                assert int(sc.code[k][j]) == b.code[k], (tag, k, REASONS[int(sc.code[k][j])], REASONS[b.code[k]])
                assert (sc.scored[k][j] and close(sc.score[k][j], b.score[k], 1e-9)) or (not sc.scored[k][j] and math.isnan(b.score[k])), (tag, k, sc.score[k][j], b.score[k])
                assert bool(sc.flag[k][j]) == b.flag[k], (tag, k, "flag")
            for k in ("DIV", DECK):
                assert (math.isnan(b.score[k]) and math.isnan(sc.score[k][j])) or close(sc.score[k][j], b.score[k], 1e-9), (tag, k)
            if b.kind and b.code["P"] not in (R_NO_STATEMENT, R_NO_FY_PREV, R_FY_CHANGE, R_DISCRETE_Q, R_NO_YTD_PREV):
                assert int(sc.kind[j]) == b.kind and int(sc.e[j]) == b.e, (tag, int(sc.kind[j]), b.kind, int(sc.e[j]), b.e)
                for nm in ("rep", "div", "iss", "tw"):
                    assert close(getattr(sc, nm)[j], getattr(b, nm), 1e-6), (tag, nm, getattr(sc, nm)[j], getattr(b, nm))
            if b.code["P"] == R_SCORED:
                assert close(sc.mv[j], b.mv, 1e-9) and tuple(bool(v[0]) for v in zero_any(sc, np.array([j]))[1:]) == b.zero, (tag, "mv / zero")
            n += 1
    return n


def brute_pos(W, b, j, sd, **kw):
    """one recount position's daily path (r21_netiss.brute_pos_ni's rule): CLOSED at the close before its first spin-off / stock-dividend ex-date inside the hold [B13] (b['pool'][j][3], the recount's own ex-date; -1 = none) by
    r17_resmom.brute_close_path, else held to the exit by r17_resmom.brute_path on the path its naive flag says; kw = the costing (bps, borrow, kt, lose100)"""
    ex = b["pool"][j][3]
    return M17.brute_close_path(W, b["f"], b["x"], j, sd, ex, **kw)[0] if ex >= 0 else M17.brute_path(W, b["f"], b["x"], j, sd, b["pool"][j][0], **kw)[0]


def brute_rec(W, rec, p, j, sd, **kw):
    """the same from a built rebalance (r21_netiss.brute_rec_ni): its pool position p - the close row compare_bb checked against the recount, the naive flag - World column j"""
    e = int(rec.close[p]) + 1 if int(rec.close[p]) >= 0 else -1
    return M17.brute_close_path(W, rec.f, rec.x, j, sd, e, **kw)[0] if e >= 0 else M17.brute_path(W, rec.f, rec.x, j, sd, bool(rec.naive[p]), **kw)[0]


def brute_side(n):
    if n >= SPEC["min_scored"]:
        return M17.SPEC["n_side"], "top"
    k = n // 3
    return (k, "third") if k >= SPEC["min_side"] else (0, "none")


def brute_flat_side(n):
    k = n // 3
    return (k, "third") if k >= SPEC["flat_min"] else (0, "none")


def brute_dec(sc):
    """plain python deciles: sorted by (score, column), sizes n // 10 (+1 for the first n % 10)"""
    order = sorted(sc, key=lambda j: (sc[j], j))
    sizes = [len(sc) // SPEC["dec_n"] + (1 if d < len(sc) % SPEC["dec_n"] else 0) for d in range(SPEC["dec_n"])]
    out, pos = {}, 0
    for d, sz in enumerate(sizes):
        for j in order[pos:pos + sz]:
            out[j] = d
        pos += sz
    return out


def brute_bb(W, ent, sh_frame, cal, cik_of, lo, hi, post_mode=JUDGED):
    """every rebalance whose position exits in [lo, hi], plain python end to end: the schedule from the months of consecutive sessions, the universe from W.U, the pool re-implemented with loops (r21_netiss.brute_ni's: >= 230 own returns and ES pairs,
    an open at the fill, the pre / old / post hygiene windows and the spin-off / stock-dividend ex-dates in the four readings, the calendar splits inside the hold under 'keep', the audit), every pool name's scores by brute_score, [A13] by
    r21_netiss.brute_second per score, the sides by brute_side, the picks by plain sorts (the HIGHEST long), the twins (DIV on P's names, the FLAT names by NETISS's own recount of ISS_1, REP / MV on R's), the deciles -> [{r, f, x, pool: {col:
    (naive, window ex-dates, hold ex-date, [B13] the first ex-date inside the hold under 'close' or -1)}, cell: {key: {...}}, counts}]"""
    sp = M17.SPEC
    Sp = getattr(W, "Sp_in", None)
    key = [(W.days[i].year, W.days[i].month) for i in range(W.T)]
    ranks = [i for i in range(W.T - 1) if key[i] != key[i + 1]]
    cache, ncache, recs = {}, {}, []
    mp = W.ni.mp.df
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
            known = hold or (Cs is not None and any(bool(Cs[s, j]) for s in range(f + 1, x + 1)))
            if pre or old or W.aud1[f, j] or (post and post_mode == "remove") or (known and post_mode == "keep"):
                continue
            ex = next((t for t in range(f + 1, x + 1) if Sp is not None and Sp[t, j]), -1) if post_mode == "close" else -1      # [B13] the first spin-off / stock-dividend ex-date inside the hold: closed at the close before it
            pool[j] = (bool(post and post_mode == "naive"), win, hold, ex)
        rec = {"r": r, "f": f, "x": x, "pool": pool, "cell": {}, "n_hold_names": n_hold, "n_win_names": n_wnames, "n_win_sessions": n_wsess}
        bs = {j: brute_score(W, ent, sh_frame, cal, j, r, cache) for j in pool}
        for kk in CODE_KEYS:
            sc = {j: b.score[kk] for j, b in bs.items() if b.code[kk] == R_SCORED}
            n_pre, second = len(sc), NI.brute_second(W, f, sc, cik_of)
            for j in second:
                del sc[j]
            codes = {j: (R_SECOND_CLASS if j in second else b.code[kk]) for j, b in bs.items()}
            k_side, mode = brute_side(len(sc))
            rec["cell"][kk] = {"scored": sc, "codes": codes, "second": second, "n_pre": n_pre, "k": k_side, "mode": mode}
        P, R = rec["cell"]["P"], rec["cell"]["R"]
        rec["cell"]["DIV"] = {"scored": {j: bs[j].score["DIV"] for j in P["scored"]}, "k": P["k"], "mode": P["mode"]}
        rec["cell"][DECK] = {"scored": {j: bs[j].score[DECK] for j in R["scored"]}, "k": 0, "mode": "none"}
        flat = {}
        for j in R["scored"]:
            row = mp[mp["symbol"] == str(W.syms[j])]
            nb = NI.brute_score(W, sh_frame, cal, j, str(row["cik"].iloc[0]) if len(row) else "", int(W.ni.static[j]), r, 1, ncache)
            if nb.code == NI.R_SCORED and FLAT_LO <= nb.iss <= FLAT_HI:
                flat[j] = R["scored"][j]
        kf, mf = brute_flat_side(len(flat))
        rec["cell"]["FLAT"] = {"scored": flat, "k": kf, "mode": mf}
        for kk in KEYS:
            o = rec["cell"][kk]
            sc = o["scored"]
            o["long"] = sorted(sc, key=lambda j: (-sc[j], -j))[:o["k"]] if o["k"] else []
            o["short"] = sorted(sc, key=lambda j: (sc[j], j))[:o["k"]] if o["k"] else []
            o["dec"] = brute_dec(sc) if kk in DEC_KEYS and len(sc) >= SPEC["dec_min"] else {}
        recs.append(rec)
    return recs


COSTINGS = (("base", D15.l1_cfg(), {}), ("10 bps", D15.l1_cfg(bps=10.0), {"bps": 10.0}), ("borrow 3%", D15.l1_cfg(borrow=(BORROW, 0.03)), {"borrow": (BORROW, 0.03), "k": True}), ("lose100", D15.l1_cfg(lose100=True), {"lose100": True}))


def compare_bb(W, L, Bz, tag, paths=True):
    """the vectorised build against the plain-python recount: the schedule, every pool (names, naive flags, the spin-off / stock-dividend ex-date counts, [B13] the close rows), per key every scored name with its score, the mode and side size,
    the picks, [A13]'s second classes, the deciles, the first-reason counts, the closed positions' count, and the daily path of EVERY scored name of the two cells under four costings (r21_netiss.compare_ni's: base, 10 bps, the 3% borrow
    stress with k_t, longs at -100%; r17_resmom.l1_pnl_x against brute_pos - a closed position by r17_resmom.brute_close_path) and of every pick of the twins (base) -> the number of paths checked"""
    assert len(L.recs) == len(Bz), (tag, len(L.recs), len(Bz))
    n_paths = 0
    want_cnt = defaultdict(Counter)
    for rec, b in zip(L.recs, Bz):
        assert (rec.r, rec.f, rec.x) == (b["r"], b["f"], b["x"]), tag
        assert rec.pool.tolist() == sorted(b["pool"]), (tag, rec.r, rec.pool.tolist(), sorted(b["pool"]))
        assert rec.naive.tolist() == [b["pool"][j][0] for j in rec.pool], (tag, rec.r)
        assert rec.spin_win.tolist() == [b["pool"][j][1] for j in rec.pool] and rec.spin_hold.tolist() == [b["pool"][j][2] for j in rec.pool], (tag, rec.r)
        assert rec.close.tolist() == [(b["pool"][j][3] - 1 if b["pool"][j][3] >= 0 else -1) for j in rec.pool], (tag, rec.r, "[B13] the close rows")
        y = int(W.days[b["f"]].year)
        for kk in KEYS:
            cc, bc = rec.cell[kk], b["cell"][kk]
            cols = rec.pool[cc.idx]
            assert cols.tolist() == sorted(bc["scored"]), (tag, rec.r, kk, cols.tolist(), sorted(bc["scored"]))
            assert close(cc.score, [bc["scored"][j] for j in cols], 1e-9), (tag, rec.r, kk, "scores")
            if not len(b["pool"]):
                continue
            assert (cc.k, cc.mode, cc.n) == (bc["k"], bc["mode"], len(bc["scored"])) and cc.traded == (bc["k"] > 0 and kk in TRADED), (tag, rec.r, kk, cc.k, cc.mode, cc.n, bc["k"], bc["mode"])
            if kk in CODE_KEYS:
                assert dict(zip(cc.second.tolist(), cc.kept.tolist())) == bc["second"] and cc.n_pre == bc["n_pre"], (tag, rec.r, kk, "[A13]")
                want_cnt[y][f"scored_{kk}"] += len(bc["scored"])
                want_cnt[y][f"no_score_{kk}"] += len(b["pool"]) - len(bc["scored"])
                for j, code in bc["codes"].items():
                    if code != R_SCORED:
                        want_cnt[y][f"ns_{kk}_{REASONS[code]}"] += 1
            if kk in TRADED:
                want_cnt[y][f"mode_{kk}_{bc['mode']}"] += 1
            if kk in DEC_KEYS:
                if len(bc["scored"]) >= SPEC["dec_min"]:
                    assert cc.dec.tolist() == [bc["dec"][j] for j in cols], (tag, rec.r, kk, "deciles")
                    want_cnt[y][f"dec_{kk}"] += 1
                else:
                    assert cc.dec is None
                    want_cnt[y][f"dec_none_{kk}"] += 1
            if not cc.traded:
                continue
            assert cols[cc.long].tolist() == bc["long"] and cols[cc.short].tolist() == bc["short"], (tag, rec.r, kk, "the picks", cols[cc.long].tolist(), bc["long"])
            assert not set(bc["long"]) & set(bc["short"]) and sorted(cc.score[cc.long]) == sorted(cc.score)[-cc.k:] and sorted(cc.score[cc.short]) == sorted(cc.score)[:cc.k], "the longs are the k HIGHEST, the shorts the k LOWEST"
            if not paths:
                continue
            kt = W.k[rec.f:rec.x + 1]
            for nm, cfg, kw in COSTINGS:
                kw2 = {"bps": kw.get("bps", COST_BPS), "borrow": kw.get("borrow", (BORROW, None)), "kt": kt if kw.get("k") else None, "lose100": kw.get("lose100", False)}
                for sd, sel in ((1, cc.long), (-1, cc.short)):
                    idx = np.arange(cc.n) if kk in CELLS else np.asarray(sel)
                    P = M17.l1_pnl_x(cc.U, idx, sd, cfg, kt)
                    for i_, i in enumerate(idx.tolist()):
                        want = brute_pos(W, b, int(cols[i]), sd, **kw2)
                        assert close(P[i_], want), (tag, nm, rec.r, kk, int(cols[i]), sd)
                        n_paths += 1
                if kk not in CELLS:
                    break
    for key, bk in (("spin_window_names", "n_win_names"), ("spin_window_sessions", "n_win_sessions"), ("spin_hold_names", "n_hold_names")):
        assert sum(c.get(key, 0) for c in L.cnt.values()) == sum(b[bk] for b in Bz), (tag, key)
    n_close = sum(1 for b in Bz for j in b["pool"] if b["pool"][j][3] >= 0)                                 # [B13] the pool names closed before an ex-date (scored or not)
    assert sum(c.get("closed_spin", 0) for c in L.cnt.values()) == n_close, (tag, "closed_spin", n_close)
    for y, w in want_cnt.items():
        for k_, v in w.items():
            assert L.cnt[y][k_] == v, (tag, y, k_, L.cnt[y][k_], v)
    return n_paths


def series_check(W, L, Bz):
    """each traded key's daily series (run_cell on r15's L1 engine with r17_resmom's l1_pnl_x, $4,000 a name) equals the sum of the recount's position paths (brute_pos: [B13]'s closed ones cut) booked on rows f .. x"""
    for kk in TRADED:
        x0 = np.zeros(W.T)
        for b in Bz:
            bc = b["cell"][kk]
            if bc["k"] == 0:
                continue
            for sd, js in ((1, bc["long"]), (-1, bc["short"])):
                for j in js:
                    x0[b["f"]:b["x"] + 1] += M17.SPEC["slot"] * np.array(brute_pos(W, b, j, sd))
        assert close(M17.run_cell(W, cell_leg(L, kk), D15.l1_cfg()).x, x0), f"{kk} series"


# ------------------------------------------------------------------ hand-made filings: fiscal years, year-to-date periods, comparatives
def month_end(d):
    d = TS(d)
    return (d + pd.offsets.MonthEnd(0)).normalize()


def fiscal_periods(fye, y0, y1):
    """the fiscal years ending in month fye of the years y0 .. y1 -> [(year, type, start, end, months)]: Q1, H, 9M (10-Q, year-to-date from the year's start) and FY (10-K)"""
    out = []
    for Y in range(y0, y1 + 1):
        e_fy = month_end(TS(f"{Y}-{fye:02d}-01"))
        s = (e_fy - pd.DateOffset(years=1)) + pd.Timedelta(days=1)
        for m, t in ((3, "Q"), (6, "H"), (9, "9M"), (12, "FY")):
            out.append((Y, t, s, month_end(s + pd.DateOffset(months=m) - pd.Timedelta(days=1)), m))
    return out


class CashGen:
    """hand-made cash-flow filings of one CIK: the value of every (concept, start, end) is fixed once (a restated comparative is another value, written in a later filing - the first filed stands), every filing an accession of its own; rows ->
    (cik, concept, val, start, end, filed, accn, form)"""
    def __init__(self, cik, rng):
        self.cik, self.rng, self.rows, self.n, self.vals = cik, rng, [], 0, {}

    def filing(self, filed, form, facts, accn=None):
        """facts = [(concept, start, end, value)] in one filing"""
        self.n += 1
        a = accn or f"{self.cik}-{TS(filed):%y%m%d}-{self.n:04d}"
        for con, s, e, v in facts:
            self.rows.append((self.cik, con, v, f"{TS(s):%Y-%m-%d}", f"{TS(e):%Y-%m-%d}", f"{TS(filed):%Y-%m-%d}", a, form))
        return a


def hand_world(names, cash_rows, days=None, share_rows=None, F=None, Cl=None, splits=(), cal_start="2016-06-01", ciks=None, methods=None, no_shares=()):
    """a minimal World for the score alone (r21_netiss.score_world: every name in the universe, raw close $100, F = 1 unless given) with hand-made cash-flow filings, NETISS's share counts (default: a cover-page value of 1e9 at every quarter end,
    filed 5 days later, for every CIK not in `no_shares`), the map (name i -> CIK 'C{i}', current_ticker) and the calendar's splits; W.bb attached. W.sh_frame / W.cash_rows / W.cal keep the inputs for the recounts"""
    days = pd.bdate_range("2022-01-03", "2025-06-27") if days is None else pd.DatetimeIndex(days)
    W = NI.score_world(days, names, F)
    if Cl is not None:
        W.Cl = np.array(Cl, float)
    ciks = ciks or [f"C{i}" for i in range(len(names))]
    if share_rows is None:
        qe = [month_end(TS(f"{y}-{m:02d}-01")) for y in range(days[0].year - 1, days[-1].year + 1) for m in (3, 6, 9, 12)]
        share_rows = [(c, DEI, 1e9, f"{q:%Y-%m-%d}", f"{q + pd.Timedelta(days=5):%Y-%m-%d}") for c in sorted(set(ciks)) if c not in no_shares for q in qe if q + pd.Timedelta(days=5) < days[-1]]
    frame = NI.fr(share_rows)
    mrows = [(s, ciks[i], (methods[i] if methods else "current_ticker")) for i, s in enumerate(names)]
    cal = NI.cal_of(splits, cal_start)
    attach_buyback(W, build_cash(cf_of(cash_rows)), NI.build_facts(frame), NI.mp_of(mrows), cal)
    W.sh_frame, W.cash_rows, W.cal = frame, list(cash_rows), cal
    return W


def fy_rows(cik, start, end, filed, form="10-K", accn=None, **vals):
    """one filing's facts of one period: vals = {short concept: value}; ST defaults to -(REP + DIV - ISS) - 1 (a statement always exists unless ST=None)"""
    st = vals.pop("ST", "auto")
    out = []
    if st == "auto":
        st = -((vals.get("REP") or 0) + (vals.get("DIV") or 0) - (vals.get("ISS") or 0)) - 1.0
    if st is not None:
        out.append((cik, "ST", st, start, end, filed, accn, form))
    for c, v in vals.items():
        out.append((cik, c, v, start, end, filed, accn, form))
    return out


def rr(W, d):
    return W.days.get_loc(TS(d))


# ------------------------------------------------------------------ selftest: hand-made worlds and hand-made filings, no files, no data
def t_constants():
    """the registered constants, the prereg's own words for them, the file pins, the reasons, the stamp"""
    assert (NREP, SEED, CELLS, TWINS, DECK, AUDIT_N) == (500, 20261024, ("P", "R"), ("DIV", "P8", "R8", "FLAT"), "REPY", 50)
    assert (STALE_DAYS, STALE_PRINT, SCORE_MAX, FLAG, BLIND_MAX, FY_GAP, YTD_GAP, A2_MONTHS) == (200, 120, 0.50, 0.15, 0.10, 14, 14, 24) and B3_RULING is None and LB_CASHFLOW is None
    assert [(nm, a, b) for _t, nm, a, b in PTYPES] == [("Q", 77, 105), ("H", 168, 196), ("9M", 259, 287), ("FY", 350, 380)] and abs(math.exp(FLAT_LO) - 0.98) < 1e-12 and abs(math.exp(FLAT_HI) - 1.02) < 1e-12
    assert len(CONCEPTS) == 14 == len(set(CONCEPTS)) and all(c.startswith("us-gaap:") for c in CONCEPTS) and set(FILE_CONCEPTS["cf"]) | set(FILE_CONCEPTS["cf_alt"]) == set(CONCEPTS) and not set(FILE_CONCEPTS["cf"]) & set(FILE_CONCEPTS["cf_alt"])
    assert [short_con(c) for c in C_REP + C_DIV + C_ISS + C_PLAN + C_TW + C_ST] == ["PaymentsForRepurchaseOfCommonStock", "PaymentsForRepurchaseOfEquity", "PaymentsOfDividendsCommonStock", "PaymentsOfDividends", "ProceedsFromIssuanceOfCommonStock",
                                                                                 "ProceedsFromIssuanceOrSaleOfEquity", "ProceedsFromIssuanceInitialPublicOffering", "ProceedsFromStockOptionsExercised",
                                                                                 "ProceedsFromIssuanceOfSharesUnderIncentiveAndShareBasedCompensationPlansIncludingStockOptions", "ProceedsFromIssuanceOfSharesUnderIncentiveAndShareBasedCompensationPlans",
                                                                                 "ProceedsFromStockPlans", "PaymentsRelatedToTaxWithholdingForShareBasedCompensation", "NetCashProvidedByUsedInFinancingActivities", "NetCashProvidedByUsedInFinancingActivitiesContinuingOperations"]
    assert FILE_SHA == {"cf": "6fe4ca5de4610072cd09ee17bb0454bdfa9888f79560d92052671fc224df1632", "cf_alt": "3edfacc7473d04e51ba3a92b97bd633a15c24723e88db28a66b1c463ede82162"} and os.path.basename(FILES["cf"]) == "cashflow_asfiled_wide.csv" and os.path.basename(FILES["cf_alt"]) == "cashflow_alt_asfiled_wide.csv"
    assert (WF0, PRE_END, LB0, LB1) == (TS("2016-07-01"), TS("2025-06-29"), TS("2025-06-30"), TS("2026-06-30")) and (S.LB0, S.END) == (LB0, R11.LBX) and YEARS == tuple(range(2016, 2025))
    assert JUDGED == NI.JUDGED == "close" and "close" in M17.POST_MODES and SPEC == {"min_scored": 150, "min_side": 20, "flat_min": 20, "dec_n": 10, "dec_min": 10} and (M17.SPEC["n_side"], M17.SPEC["slot"]) == (50, 4000.0) and (COST_BPS, STRESS_BPS) == (5.0, (10.0, 20.0))
    assert (A2_TARGET, A2_REPORT) == (0.25, (0.5, 2.0)) and BETA_CAP == 0.20 and DV.REF_W == 0.264, "A2's registered size"
    assert DV.REF_SHA == "e204dd53419a22bcc69045cc5d17ff42c86203fb06b58fa538b10beb7ba25d18" and DV.REF_FACTS == {"roc": 121.06, "sortino": 3.926, "max_dd": 36526.0} and DV.REF_CSV_PINNED.endswith("resmom_cells_daily_wf_close.csv"), "[B14] the S1-restated L"
    assert len(REASONS) == R_SECOND_CLASS + 1 and set(REASON_TEXT) == set(REASONS) and REASONS[R_OVER50] == "score_over_0.50" and set(NI_STATIC.values()) == {R_NOT_IN_MAP, R_MAP_MISMATCH, R_MAP_AMBIGUOUS, R_MAP_UNMAPPED, R_MAP_NONCOMMON, R_MAP_OTHER, R_FOREIGN}
    assert (REASONS[R_FY_CHANGE], REASONS[R_DISCRETE_Q], REASONS[R_NO_FY_PREV]) == ("fiscal_year_change", "discrete_quarter", "no_fy_prev") and TRANSITION_FORMS == ("10-KT", "10-QT", "10-KT/A", "10-QT/A"), "[B15](9) the label apart"
    assert S_MONTHS == 15 and (REASONS[R_NO_S], REASONS[R_STALE_S], REASONS[R_S_NOT_POS]) == ("no_share_count_at_r", "stale_s", "share_count_not_positive"), "[B17] stale S, a market-value reason"
    assert R11.sha_lf(PREREG) == PREREG_SHA, "the pre-registration on disk is the registered one (LF sha256)"
    norm = " ".join(open(PREREG, encoding="utf-8").read().split())
    for frag in ("500 draws, seed 20261024", "Q 77-105 days, H 168-196, 9M 259-287, FY 350-380", "e more than 200 days before r", "|score| > 0.50", "|score| > 0.15", "more than 120 days before the rank close", "Above 10% of names in any year",
                 "within 14 days of FY_prev's end + 1 day", "ending within 14 days of e - 1 year", "ISS is within +-2%", "first 24 months of traded fills", "long the 50 HIGHEST", "short the 50 LOWEST", "fewer than 150 scored names trades the top / bottom third (n // 3 a side, at least 20)",
                 FILE_SHA["cf"], FILE_SHA["cf_alt"], "PaymentsRelatedToTaxWithholdingForShareBasedCompensation", "Two passing cells send the higher WF ROC to Stage B (a tie: P)",
                 "This is r17_resmom's post_mode 'close'", "CLOSES the position at the official close of the session before it, e-1", "The null draws from the same pool with the same cut paths",
                 "[B10]'s removal reading ('keep': an announced split or a spin-off / stock-dividend ex-date inside the hold removes the name) is printed beside the judged one as a REPORT with its count of removed name-months, without a null",
                 "L = #463 + 0.264 x RES = WF ROC @ $30k 121.06 / DD5 $34,392, Sortino 3.926, worst drawdown $36,526", "resmom_cells_daily_wf_close.csv (sha256 e204dd53...)", "so no NETISS line joins the reference",
                 "counts a period that does not start at its fiscal year's start (a discrete quarter) apart from a fiscal-year change (no score either way - a label only)",
                 "always at its FIRST-FILED value, never a later restated one", "must lie within 15 calendar months before the rank; otherwise the name is UNSCORED with the no-score reason 'stale S'",
                 "The latest such usable cover-page (dei) count still comes first, else the balance-sheet (us-gaap) count",
                 "PICKED position with a calendar split inside its hold and no matching factor move is LISTED before any P&L (symbol, rank, ex-date, split ratio, the factor's move)", "None listed = said so"):
        assert frag in norm, frag
    with quiet():
        pk = prereg_ok()
    assert pk["verified"] is True and pk["committed"] in ("match", "untracked", "unknown")
    st = stamp()
    assert st["cf_sha256"] == FILE_SHA["cf"] and st["cf_alt_sha256"] == FILE_SHA["cf_alt"] and st["harness_sha256"] == R11.sha_lf(os.path.abspath(__file__)) and st["r21_sha256"] == R11.sha_lf(NI.__file__)
    assert {"r17_sha256", "r18_sha256", "r15_sha256", "facts_sha256", "map_sha256", "wide_ca_sha256", "early_close"} <= set(st)
    with patched(THIS, PREREG_SHA="0" * 64), quiet():
        refused(prereg_ok, "DIFFERS", TAIL)
    with patched(THIS, PREREG=os.path.join(HERE, "no_such_prereg.txt")), quiet():
        refused(prereg_ok, "is not next to this file")
    with patched(D15, committed_state=lambda: "differs"), quiet():
        refused(prereg_ok, "COMMITTED")
    for bad in ("keep", "remove", "s1"):
        with patched(THIS, JUDGED=bad), quiet():
            refused(prereg_ok, "not [B13]'s 'close'", TAIL)


def t_files():
    """[B6] / [B7] the two pinned extracts on hand-made copies: each refused if absent / another sha / without a registered column; read as ONE table in chunks (the same table whatever the chunk size); a FACT present in both (the same cik,
    concept, start, end and accession) refused, the same concept in both files from another filing read; the cut at READ (a row filed on / after it dropped and counted, a period ending on / after it dropped and counted, the table asserted
    free of the sealed year); a concept other than the 14, a unit other than USD, an unreadable date, a start after its end dropped and counted at their first reason; a missing / unreadable value kept (the first-filed rule makes the entry
    unusable); a CRLF copy is another file (the pin is of the bytes) the loader reads the same; empty extracts give an empty table"""
    root = tempfile.mkdtemp(prefix="buyback_selftest_")
    try:
        p = lambda n: os.path.join(root, n)
        files = {"cf": p("cashflow_asfiled_wide.csv"), "cf_alt": p("cashflow_alt_asfiled_wide.csv")}
        base = fy_rows("0000000001", "2023-01-01", "2023-12-31", "2024-02-20", accn="A1", REP=30, DIV=10, ISS=5) + fy_rows("0000000002", "2024-01-01", "2024-03-31", "2024-05-02", "10-Q", "B1", REPE=4)
        alt = [("0000000001", "OPT", 2, "2023-01-01", "2023-12-31", "2024-02-20", "A1", "10-K"), ("0000000002", "TW", 1, "2024-01-01", "2024-03-31", "2024-05-02", "B1")]

        def pin(b=base, a=alt, **kw):
            shas = {"cf": write_cf(files["cf"], b, **kw), "cf_alt": write_cf(files["cf_alt"], a)}
            return patched(THIS, FILES=dict(files), FILE_SHA=shas)
        with pin():
            cf, info = load_cashflow(S.LB0)
            assert cf.n == 8 and info["files"] == {"cf": 6, "cf_alt": 2} and info["rows_read"] == 8 and info["rows"] == 8 and info["rows_by_extract"] == {"cf": 6, "cf_alt": 2} and info["ciks"] == 2, info
            assert info["rows_by_concept"] == {C_ST[0]: 2, C_REP[0]: 1, C_REP[1]: 1, C_DIV[0]: 1, C_ISS[0]: 1, C_PLAN[0]: 1, C_TW[0]: 1} and info["ciks_by_concept"][C_ST[0]] == 2 and all(info[k] == 0 for k in DROP_KEYS + ("rows_value_missing",))
            assert info["sha256"] == {k: M17.sha_raw(files[k]) for k in CF_KEYS} and info["rows_by_form"] == {"10-K": 5, "10-Q": 3} and info["filed_range"] == ["2024-02-20", "2024-05-02"]
            assert cf.accns.tolist() == ["A1", "B1"] and sorted(cf.ciks.tolist()) == ["0000000001", "0000000002"] and set(cf.src.tolist()) == {0, 1} and (cf.src[cf.con == CIX[C_TW[0]]] == 1).all()
            cf2, _ = load_cashflow(S.LB0, chunk=3)
            assert all((getattr(cf, k) == getattr(cf2, k)).all() for k in ("ck", "con", "val", "start", "end", "filed", "accn", "form", "src")) and cf.ciks.tolist() == cf2.ciks.tolist() and cf.accns.tolist() == cf2.accns.tolist(), "the chunk size changes nothing"
            assert check_pinned("cf") == FILE_SHA["cf"] == M17.sha_raw(files["cf"])
        junk = [("0000000003", "us-gaap:Foo", 1, "2023-01-01", "2023-12-31", "2024-02-20"), ("0000000003", "ST", 1, "2023-01-01", "2023-12-31", "2024-02-20", None, None, "EUR"), ("0000000003", "ST", 1, "2023-01-01", "not-a-date", "2024-02-20"),
                ("0000000003", "ST", 1, "2023-12-31", "2023-01-01", "2024-02-20"), ("0000000003", "ST", 1, "2024-01-01", "2024-12-31", "2025-06-30"), ("0000000003", "ST", 1, "2025-04-01", "2025-06-30", "2025-06-27"),
                ("0000000003", "REP", None, "2024-01-01", "2024-03-31", "2024-05-02"), ("0000000003", "REP", "abc", "2024-04-01", "2024-06-30", "2024-08-02"), ("0000000003", "ST", 1, "2024-01-01", "2024-12-31", "2025-06-29")]
        with pin(b=base + junk):
            cf, info = load_cashflow(S.LB0)
            assert (info["rows_other_concept"], info["rows_unit_not_usd"], info["rows_unreadable_date"], info["rows_start_after_end"], info["rows_filed_on_or_after_the_cut"], info["rows_end_on_or_after_the_cut"]) == (1, 1, 1, 1, 1, 1), info
            assert info["rows_value_missing"] == 2 and cf.n == 8 + 3 and info["rows_read"] == 8 + 9 and cf.filed.max() < dnum(S.LB0) and cf.end.max() < dnum(S.LB0), "the row filed the day before the cut stays; the cut's own day goes"
            cash = build_cash(cf)
            assert cash.info["value_missing"] == 2 and not cash.E_ok[~np.isfinite(cash.E_val)].any()
        with pin(a=alt + [base[1]]):
            refused(lambda: load_cashflow(S.LB0), "in BOTH cash-flow extracts", "no silent overlap", TAIL)
        with pin(a=alt + [("0000000001", "REP", 31, "2023-01-01", "2023-12-31", "2025-02-20", "A9", "10-K")]):
            assert load_cashflow(S.LB0)[0].n == 9, "the same concept in both files from ANOTHER filing is no fact in both: read (the first filed stands)"
        for key in CF_KEYS:
            with pin():
                with patched(THIS, FILE_SHA={**FILE_SHA, key: "0" * 64}):
                    refused(lambda: load_cashflow(S.LB0), "is not the registered", FILE_LABEL[key], TAIL)
                with patched(THIS, FILES={**FILES, key: p("absent.csv")}):
                    refused(lambda: load_cashflow(S.LB0), "is not on file", FILE_LABEL[key], TAIL)
        with pin(header=[c for c in CF_HDR if c != "accn"]):
            refused(lambda: load_cashflow(S.LB0), "lacks the column", "accn")
        with pin(crlf=True):
            assert FILE_SHA["cf"] != write_cf(p("x.csv"), base) and load_cashflow(S.LB0)[0].n == 8
        with pin(b=[], a=[]):
            cf, info = load_cashflow(S.LB0)
            assert cf.n == 0 and info["rows"] == 0 and build_cash(cf).info["entries"] == 0, "empty extracts: an empty table, no exception"
    finally:
        shutil.rmtree(root, ignore_errors=True)


def t_cash():
    """the CASH KNOWN AT A RANK CLOSE (NETISS [A2]'s first-filed rule) on hand-made rows: the first filed value stands (a later comparative / amendment with another value never replaces it, counted); two accessions on the first day with two values
    = AMBIGUOUS (unusable), with one value = the smaller accession; a period ending after its own first filing, a missing value and a NEGATIVE component value are unusable, a negative STATEMENT is usable; the period types by length at every
    boundary; the period table (cik, end, length) with FACT; and build_cash against the plain-python recount on random rows"""
    rows = [("C1", "REP", 10, "2023-01-01", "2023-03-31", "2023-05-01", "A2"), ("C1", "REP", 12, "2023-01-01", "2023-03-31", "2024-05-01", "A5"), ("C1", "ST", -5, "2023-01-01", "2023-03-31", "2023-05-01", "A2"),
            ("C1", "DIV", 3, "2023-01-01", "2023-06-30", "2023-08-01", "B2"), ("C1", "DIV", 4, "2023-01-01", "2023-06-30", "2023-08-01", "B1"), ("C1", "ISS", 2, "2023-01-01", "2023-06-30", "2023-08-01", "B2"),
            ("C1", "ISS", 2, "2023-01-01", "2023-06-30", "2023-08-01", "B1"), ("C1", "REP", 7, "2023-01-01", "2023-09-30", "2023-09-15", "C1"), ("C1", "REP", None, "2022-01-01", "2022-12-31", "2023-02-20", "D1"),
            ("C1", "REP", -4, "2022-01-01", "2022-06-30", "2022-08-01", "E1"), ("C1", "ST", -4, "2022-01-01", "2022-06-30", "2022-08-01", "E1")]
    cash = build_cash(cf_of(rows))
    ent = {(short_con(CONCEPTS[int(con)]), dstr(s), dstr(e)): (dstr(f1), float(v), bool(ok), str(cash.accns[a]), bool(amb)) for con, s, e, f1, v, ok, a, amb in
           zip(cash.E_con, cash.E_start, cash.E_end, cash.E_f1, cash.E_val, cash.E_ok, cash.E_accn, cash.E_amb)}
    R_, D_, I_, S_ = short_con(C_REP[0]), short_con(C_DIV[0]), short_con(C_ISS[0]), short_con(C_ST[0])
    assert ent[(R_, "2023-01-01", "2023-03-31")] == ("2023-05-01", 10.0, True, "A2", False), "the first filed value stands"
    assert ent[(D_, "2023-01-01", "2023-06-30")][2:] == (False, "B1", True), "two values on the first day: ambiguous, unusable"
    assert ent[(I_, "2023-01-01", "2023-06-30")] == ("2023-08-01", 2.0, True, "B1", False), "one value twice on the first day: the smaller accession, usable"
    assert not ent[(R_, "2023-01-01", "2023-09-30")][2] and not ent[(R_, "2022-01-01", "2022-12-31")][2] and not ent[(R_, "2022-01-01", "2022-06-30")][2] and ent[(S_, "2022-01-01", "2022-06-30")][2], "end after filed / missing / negative component unusable; negative statement usable"
    i = cash.info
    assert (i["entries"], i["ambiguous"], i["end_after_filed"], i["value_missing"], i["negative_component_value"], i["later_filing_carries_another_value"], i["entries_with_two_or_more_rows"]) == (8, 1, 1, 1, 1, 2, 3), i
    # the period types at every boundary, and the table's order: by (cik, end, length) - the last of a CIK's rows with one end is its longest period
    lens = (76, 77, 105, 106, 167, 168, 196, 197, 258, 259, 287, 288, 349, 350, 380, 381)
    want = (T_OTHER, T_Q, T_Q, T_OTHER, T_OTHER, T_H, T_H, T_OTHER, T_OTHER, T_9M, T_9M, T_OTHER, T_OTHER, T_FY, T_FY, T_OTHER)
    e0 = TS("2023-12-31")
    c2 = build_cash(cf_of([("C2", "ST", 1, f"{e0 - pd.Timedelta(days=n):%Y-%m-%d}", f"{e0:%Y-%m-%d}", "2024-02-20") for n in lens] + [("C2", "ST", 1, "2023-01-01", "2023-03-31", "2023-05-01"), ("C3", "ST", 1, "2023-01-01", "2023-03-31", "2023-05-01")]))
    tab = {(str(c2.ciks[c]), int(n)): int(t) for c, n, t in zip(c2.pck, c2.plen, c2.ptype)}
    assert all(tab[("C2", n)] == t for n, t in zip(lens, want)), [(n, tab[("C2", n)]) for n in lens]
    key = list(zip(c2.pck.tolist(), c2.pend.tolist(), c2.plen.tolist()))
    assert key == sorted(key) and (c2.FACT[:, CIX[C_ST[0]]] >= 0).all() and (c2.FACT[:, 1:] < 0).all(), "periods sorted by (cik, end, length); FACT points at each concept's entry"
    # build_cash against the plain-python recount on random rows (amendments, ambiguous days, missing / negative values, ends after the filing, odd lengths)
    rng = np.random.default_rng(7)
    rows = []
    shorts = list(AL)
    for n in range(1500):
        cik = f"C{int(rng.integers(0, 6))}"
        e = TS("2022-03-31") + pd.DateOffset(months=3 * int(rng.integers(0, 12)))
        e = month_end(e)
        ln = int(rng.choice([90, 181, 273, 364, 120, 365, 89]))
        s = e - pd.Timedelta(days=ln)
        f = e + pd.Timedelta(days=int(rng.choice([-5, 30, 30, 45, 60, 365])))         # few filing days: two accessions of one fact on one day happen
        v = None if rng.random() < 0.03 else float(rng.choice([-1.0, 1.0], p=[0.06, 0.94]) * rng.integers(1, 6) * 1e8)
        rows.append((cik, shorts[int(rng.integers(0, len(shorts)))], v, f"{s:%Y-%m-%d}", f"{e:%Y-%m-%d}", f"{f:%Y-%m-%d}", f"Z{int(rng.integers(0, 40)):03d}", str(rng.choice(["10-Q", "10-K", "10-Q/A"]))))
    cash = build_cash(cf_of(rows))
    want = brute_cash(rows)
    got = {(str(cash.ciks[ck]), CONCEPTS[int(con)], int(s), int(e)): (int(f1), float(v), bool(ok), str(cash.accns[a]), str(cash.forms[int(fm)])) for ck, con, s, e, f1, v, ok, a, fm in
           zip(cash.E_ck, cash.E_con, cash.E_start, cash.E_end, cash.E_f1, cash.E_val, cash.E_ok, cash.E_accn, cash.E_form)}
    assert set(got) == set(want) and len(got) > 500, (len(got), len(want))
    for k, w in want.items():
        g = got[k]
        assert g[0] == w[0] and g[2] == w[2] and g[3] == w[3] and g[4] == w[4] and ((math.isnan(g[1]) and math.isnan(w[1])) or g[1] == w[1]), (k, g, w)
    assert cash.info["ambiguous"] > 5 and cash.info["negative_component_value"] > 5 and cash.info["end_after_filed"] > 5 and cash.info["value_missing"] > 5, cash.info


def t_ttm():
    """the TRAILING FOUR QUARTERS on hand-made filings (MV = $100 x 1e9 shares = 1e11, so a score is the cash / 1e11): a FY's own value; YTD + FY_prev - YTD_prev for Q1 / H / 9M; a fact usable only from the first session STRICTLY after its first
    filing (filed on a rank close: not yet); no YTD_prev; [B1] the fiscal-year change (a transition quarter reads, the first quarter of the new year does not); FY_prev 14 days before s (kept) and 15 (a change); YTD_prev 14 days off e - 1 year
    (kept) and 15 (none), two equidistant -> the earlier; staleness at 200 days; no FY_prev at all; a discrete quarter that is not year-to-date reads as a change"""
    A = []
    for s, e, f, vals in (("2022-01-01", "2022-12-31", "2023-02-20", dict(REP=6e9, DIV=2e9, ISS=1e9)), ("2023-01-01", "2023-03-31", "2023-05-02", dict(REP=1.5e9, DIV=0.7e9, ISS=0.2e9)),
                          ("2023-01-01", "2023-06-30", "2023-08-02", dict(REP=4e9, DIV=1.5e9, ISS=0.5e9)), ("2023-01-01", "2023-09-30", "2023-11-02", dict(REP=6e9, DIV=2.2e9, ISS=0.8e9)),
                          ("2023-01-01", "2023-12-31", "2024-02-20", dict(REP=8e9, DIV=3e9, ISS=1e9)), ("2024-01-01", "2024-03-31", "2024-05-02", dict(REP=2.5e9, DIV=0.8e9, ISS=0.3e9)),
                          ("2024-01-01", "2024-06-30", "2024-08-02", dict(REP=5e9, DIV=1.6e9, ISS=0.4e9)), ("2024-01-01", "2024-09-30", "2024-11-04", dict(REP=7e9, DIV=2.4e9, ISS=0.6e9)),
                          ("2024-01-01", "2024-12-31", "2025-02-20", dict(REP=9e9, DIV=3.2e9, ISS=0.9e9)), ("2025-01-01", "2025-03-31", "2025-05-30", dict(REP=2e9, DIV=0.9e9, ISS=0.25e9))):
        A += fy_rows("C0", s, e, f, "10-K" if e.endswith("12-31") else "10-Q", **vals)
    B_ = (fy_rows("C1", "2023-01-01", "2023-12-31", "2024-02-20", REP=4e9) + fy_rows("C1", "2023-01-01", "2023-03-31", "2023-05-02", "10-Q", REP=0.8e9) + fy_rows("C1", "2024-01-01", "2024-03-31", "2024-05-10", "10-KT", REP=1e9)
          + fy_rows("C1", "2024-04-01", "2024-06-30", "2024-08-09", "10-Q", REP=1.2e9))
    C_ = (fy_rows("C2", "2022-12-19", "2023-12-17", "2024-01-20", REP=5e9) + fy_rows("C2", "2022-12-19", "2023-03-19", "2023-04-20", "10-Q", REP=1e9) + fy_rows("C2", "2023-12-31", "2024-03-30", "2024-04-25", "10-Q", REP=2e9))
    D_ = (fy_rows("C3", "2022-12-18", "2023-12-16", "2024-01-20", REP=5e9) + fy_rows("C3", "2022-12-18", "2023-03-19", "2023-04-20", "10-Q", REP=1e9) + fy_rows("C3", "2023-12-31", "2024-03-30", "2024-04-25", "10-Q", REP=2e9))
    E_ = (fy_rows("C4", "2023-01-01", "2023-12-31", "2024-02-20", REP=5e9) + fy_rows("C4", "2023-01-01", "2023-03-24", "2023-04-20", "10-Q", REP=1e9) + fy_rows("C4", "2023-01-01", "2023-04-07", "2023-05-01", "10-Q", REP=3e9)
          + fy_rows("C4", "2024-01-01", "2024-03-31", "2024-04-25", "10-Q", REP=2e9))
    F_ = (fy_rows("C5", "2023-01-01", "2023-12-31", "2024-02-20", REP=5e9) + fy_rows("C5", "2023-01-01", "2023-04-15", "2023-05-20", "10-Q", REP=1e9) + fy_rows("C5", "2024-01-01", "2024-03-31", "2024-04-25", "10-Q", REP=2e9))
    G_ = fy_rows("C6", "2024-01-01", "2024-03-31", "2024-04-25", "10-Q", REP=2e9) + fy_rows("C6", "2023-01-01", "2023-03-31", "2023-04-25", "10-Q", REP=1e9)
    H_ = fy_rows("C7", "2023-01-01", "2023-12-31", "2024-02-20", REP=4e9) + fy_rows("C7", "2024-04-01", "2024-06-30", "2024-08-05", "10-Q", REP=1e9) + fy_rows("C7", "2023-04-01", "2023-06-30", "2023-08-05", "10-Q", REP=1e9)
    # [B15](9): III the same discrete Apr-Jun quarter after a TRANSITION REPORT on a 10-QT (Jan-Mar 2024: the fiscal year moved - [B1]'s change); JJJ the first quarter of a year whose FY_prev is two years old (it starts at its fiscal year's
    # start: [B1]); KKK a 52/53-week filer's discrete second quarter (FY to Sat 2023-12-30, Q 2024-03-31 .. 06-29: on the grid within 14 days); LLL a discrete HALF (Apr-Sep: not a quarter - [B1])
    I_ = (fy_rows("C8", "2023-01-01", "2023-12-31", "2024-02-20", REP=4e9) + fy_rows("C8", "2024-01-01", "2024-03-31", "2024-05-10", "10-QT", REP=1e9)
          + fy_rows("C8", "2024-04-01", "2024-06-30", "2024-08-05", "10-Q", REP=1e9))
    J_ = fy_rows("C9", "2022-01-01", "2022-12-31", "2023-02-20", REP=4e9) + fy_rows("C9", "2024-01-01", "2024-03-31", "2024-04-25", "10-Q", REP=1e9)
    K_ = fy_rows("C10", "2023-01-01", "2023-12-30", "2024-02-20", REP=4e9) + fy_rows("C10", "2024-03-31", "2024-06-29", "2024-08-05", "10-Q", REP=1e9)
    L_ = fy_rows("C11", "2023-01-01", "2023-12-31", "2024-02-20", REP=4e9) + fy_rows("C11", "2024-04-01", "2024-09-30", "2024-11-04", "10-Q", REP=1e9)
    names = ["AAA", "BBB", "CCC", "DDD", "EEE", "FFF", "GGG", "HHH", "III", "JJJ", "KKK", "LLL"]
    W = hand_world(names, A + B_ + C_ + D_ + E_ + F_ + G_ + H_ + I_ + J_ + K_ + L_)
    at = lambda d: score_rank(W, rr(W, d))
    sc = at("2024-01-31")
    assert REASONS[sc.code["P"][0]] == "no_ytd_prev" and sc.kind[0] == 0, "9M 2023 is the statement; its YTD_prev (9M 2022) is not on file"
    sc = at("2024-02-29")
    assert sc.kind[0] == 1 and close(sc.rep[0], 8e9) and close(sc.score["P"][0], 0.10) and close(sc.score["R"][0], 0.07) and close(sc.score["DIV"][0], 0.03) and close(sc.score[DECK][0], 0.08), "a FY reads its own value"
    sc = at("2024-05-31")
    assert sc.kind[0] == 2 and close(sc.rep[0], 9e9) and close(sc.div[0], 3.1e9) and close(sc.iss[0], 1.1e9) and close(sc.score["P"][0], 0.11) and dstr(sc.s[0]) == "2024-01-01" and dstr(sc.e[0]) == "2024-03-31", "Q1: 2.5 + 8 - 1.5"
    sc = at("2024-08-30")
    assert close(sc.rep[0], 9e9) and close(sc.div[0], 3.1e9) and close(sc.iss[0], 0.9e9) and close(sc.score["R"][0], 0.081), "H: 5 + 8 - 4"
    sc = at("2024-11-29")
    assert close(sc.rep[0], 9e9) and close(sc.div[0], 3.2e9) and close(sc.iss[0], 0.8e9) and close(sc.score["P"][0], 0.114), "9M: 7 + 8 - 6"
    sc = at("2025-05-30")
    assert sc.kind[0] == 1 and close(sc.rep[0], 9e9), "Q1 2025 is filed ON the rank close 2025-05-30: usable from the next session, not at this rank"
    assert close(at("2025-06-27").rep[0], 2e9 + 9e9 - 2.5e9), "usable from the next session on"
    # [B1]: BBB's transition quarter (Jan-Mar 2024, a 10-KT) reads with FY 2023 and Q1 2023; the first quarter of its new April year has no FY_prev within 14 days of its start
    sc = at("2024-05-31")
    assert sc.kind[1] == 2 and close(sc.rep[1], 1e9 + 4e9 - 0.8e9) and dstr(sc.s[1]) == "2024-01-01"
    assert REASONS[at("2024-08-30").code["P"][1]] == "fiscal_year_change"
    # FY_prev 14 days before s (CCC: kept) and 15 days (DDD: a change); YTD_prev within 14 days of e - 1 year
    sc = at("2024-04-30")
    assert sc.kind[2] == 2 and close(sc.rep[2], 2e9 + 5e9 - 1e9), ("s - FY_prev's end = 14: kept", REASONS[sc.code["P"][2]])
    assert REASONS[sc.code["P"][3]] == "fiscal_year_change", "15 days: a change"
    assert sc.kind[4] == 2 and close(sc.rep[4], 2e9 + 5e9 - 1e9), "two YTD_prev 7 days either side of e - 1 year: the earlier"
    assert REASONS[sc.code["P"][5]] == "no_ytd_prev", "YTD_prev 15 days off e - 1 year: none"
    assert REASONS[sc.code["P"][6]] == "no_fy_prev", "no FY before s at all"
    sc = at("2024-08-30")
    assert REASONS[sc.code["P"][7]] == "discrete_quarter" and sc.kind[7] == 0, "[B15](9) a discrete quarter (Apr-Jun) that is not year-to-date: it starts 3 months, not a year, after FY_prev's end + 1 - its own label, no TTM"
    assert REASONS[sc.code["P"][8]] == "fiscal_year_change", "the same quarter after a transition report (10-QT): the fiscal year moved - [B1]"
    assert REASONS[sc.code["P"][10]] == "discrete_quarter", "a 52/53-week filer's second quarter: on the grid within 14 days"
    assert REASONS[at("2024-04-30").code["P"][9]] == "fiscal_year_change" and REASONS[at("2024-11-29").code["P"][11]] == "fiscal_year_change", "a first quarter with a two-year-old FY_prev starts at its year's start; a discrete half is no quarter: [B1]"
    assert all(REASONS[sc.code[k][7]] == "discrete_quarter" and not sc.scored[k][7] for k in CODE_KEYS), "a label only: no score in any key"
    assert on_quarter_grid(dnum("2024-04-01"), dnum("2023-12-31")) and on_quarter_grid(dnum("2024-10-14"), dnum("2023-12-31")) and not on_quarter_grid(dnum("2024-10-16"), dnum("2023-12-31"))
    assert not on_quarter_grid(dnum("2025-01-01"), dnum("2023-12-31")) and on_quarter_grid(dnum("2025-04-01"), dnum("2023-12-31")) and on_quarter_grid(dnum("2024-05-01"), dnum("2024-01-30")), "a whole year is no quarter; the day clips to the month"
    for s_, e_ in (("2024-04-01", "2023-12-31"), ("2024-10-14", "2023-12-31"), ("2024-10-16", "2023-12-31"), ("2025-01-01", "2023-12-31"), ("2025-04-01", "2023-12-31"), ("2024-05-01", "2024-01-30"), ("2024-03-31", "2023-12-30"),
                   ("2023-02-28", "2022-11-30"), ("2024-02-29", "2023-11-30"), ("2024-08-31", "2024-02-29")):
        assert on_quarter_grid(dnum(s_), dnum(e_)) == brute_grid(dnum(s_), dnum(e_)), (s_, e_)
    # staleness: AAA's last statement period ends 2025-03-31; a world that ends later sees it go stale after 200 days
    W2 = hand_world(["AAA"], A, days=pd.bdate_range("2022-01-03", "2025-12-31"))
    assert REASONS[score_rank(W2, rr(W2, "2025-09-30")).code["P"][0]] == "scored" and REASONS[score_rank(W2, rr(W2, "2025-10-31")).code["P"][0]] == "stale_over_200_days" and score_rank(W2, rr(W2, "2025-10-31")).stale_days[0] == 214
    n = compare_scores(W, brute_cash(W.cash_rows), W.sh_frame, W.cal, [rr(W, d) for d in ("2023-03-31", "2024-01-31", "2024-02-29", "2024-04-30", "2024-05-31", "2024-08-30", "2024-11-29", "2025-05-30", "2025-06-27")])
    assert n == 9 * len(names)


def t_components():
    """the components on hand-made filings (one FY each, MV 1e11): REP / DIV the first concept, else the fallback, else ZERO (the zero rule only after both are absent); [B7] ISSUANCE = the first present primary (a second primary present is NOT added)
    + every stock-plan concept present, two items with the same value in the same filing counted once (CHOICE: the primary included), the same value from two filings summed; none of the seven = ZERO; a negative fact is unusable (its
    fallback reads; none -> ZERO), a negative STATEMENT still proves the statement; [B8] the withholding twin; a TTM whose periods read REP from both concepts is 'mixed'; comp_use's flags and the zero-rule flags of [B9]"""
    f = lambda cik, **v: fy_rows(cik, "2023-01-01", "2023-12-31", "2024-02-20", **v)
    rows = (f("C0", REP=8e9, REPE=5e9) + f("C1", REPE=5e9) + f("C2") + f("C3", ISS=1e9, OPT=0.5e9, PLAN=0.5e9) + f("C4", ISSE=2e9, IPO=3e9, PLN=0.4e9) + f("C5", IPO=3e9) + f("C6", OPT=1e9)
            + f("C7", OPT=1e9) + [("C7", "PLAN", 1e9, "2023-01-01", "2023-12-31", "2024-02-21", "LATER", "10-K/A")] + f("C8", REP=-8e9, REPE=5e9, ST=-3e9) + f("C9", REP=-8e9, ST=-2e9) + f("C10", ISS=1e9, OPT=1e9)
            + f("C11", REP=2e9, TW=0.6e9, DIV=1e9, ISS=0.5e9) + f("C12", DIVA=2e9, DIV=None))
    rows += (fy_rows("C13", "2023-01-01", "2023-03-31", "2023-05-02", "10-Q", REPE=1e9) + fy_rows("C13", "2023-01-01", "2023-12-31", "2024-02-20", REP=5e9) + fy_rows("C13", "2024-01-01", "2024-03-31", "2024-05-02", "10-Q", REPE=2e9))
    names = [f"A{i:02d}" for i in range(14)]
    W = hand_world(names, rows)
    sc = score_rank(W, rr(W, "2024-02-29"))
    c0 = sc.comps[0]
    v = lambda nm, j: float(getattr(sc, nm)[j])
    assert v("rep", 0) == 8e9 and c0["rep_src"][0] == 1 and v("rep", 1) == 5e9 and c0["rep_src"][1] == 2 and v("rep", 2) == 0.0 and c0["rep_src"][2] == 0, "first / fallback / zero"
    assert v("div", 0) == 0.0 and c0["div_src"][0] == 0 and v("iss", 2) == 0.0 and not c0["iss_any"][2] and REASONS[sc.code["P"][2]] == "scored" and sc.score["P"][2] == 0.0, "no line on the statement reads ZERO: a score of zero"
    assert v("iss", 3) == 1.5e9 and c0["iss_prim"][3] == 1 and c0["iss_plan"][3] == 1 and c0["iss_dup"][3] == 1, "ISS 1 + OPT 0.5 (+ PLAN 0.5: the same value in the same filing, once)"
    assert v("iss", 4) == 2.4e9 and c0["iss_prim"][4] == 2 and v("iss", 5) == 3e9 and c0["iss_prim"][5] == 3, "the FIRST present primary only (a second primary is not added) + the stock-plan concepts"
    assert v("iss", 6) == 1e9 and c0["iss_prim"][6] == 0 and c0["iss_any"][6] and v("iss", 7) == 2e9 and c0["iss_dup"][7] == 0, "the stock-plan concepts alone; the same value from two filings: summed"
    assert v("rep", 8) == 5e9 and c0["rep_src"][8] == 2 and v("rep", 9) == 0.0 and c0["rep_src"][9] == 0 and REASONS[sc.code["P"][9]] == "scored", "a negative fact is unusable: the fallback, else ZERO; a negative statement proves the statement"
    assert v("iss", 10) == 1e9 and c0["iss_dup"][10] == 1, "CHOICE: the primary and a stock-plan item with the same value in one filing count once"
    assert close(sc.score["P8"][11], (2e9 + 0.6e9 + 1e9 - 0.5e9) / 1e11) and close(sc.score["R8"][11], (2e9 + 0.6e9 - 0.5e9) / 1e11) and close(sc.score["P"][11], (2e9 + 1e9 - 0.5e9) / 1e11) and v("tw", 11) == 0.6e9, "[B8] the withholding twin"
    assert v("div", 12) == 2e9 and c0["div_src"][12] == 2, "a missing value is unusable: the fallback reads"
    cu = comp_use(sc, np.arange(14))
    assert cu["rep"]["first"].tolist()[:3] == [True, False, False] and cu["rep"]["fallback"][1] and cu["rep"]["zero_all"][2] and cu["iss"]["dedup"][3] and cu["iss"]["second"][4] and cu["iss"]["third"][5] and cu["iss"]["plan_only"][6] and cu["iss"]["zero_all"][2]
    z, zr, zi = zero_any(sc, np.array([0, 1, 2, 3, 6]))
    assert zr.tolist() == [False, False, True, True, True] and zi.tolist() == [True, True, True, False, False] and z.tolist() == [True, True, True, True, True], "[B9] REP or ISS from the zero rule on some period"
    sc = score_rank(W, rr(W, "2024-05-31"))
    cu = comp_use(sc, np.array([13]))
    assert sc.kind[13] == 2 and close(sc.rep[13], 2e9 + 5e9 - 1e9) and cu["rep"]["mixed"][0], "the fallback on the year-to-date periods, the first concept on the FY: mixed across one TTM"
    n = compare_scores(W, brute_cash(W.cash_rows), W.sh_frame, W.cal, [rr(W, "2024-02-29"), rr(W, "2024-05-31")])
    assert n == 2 * 14


def t_mv():
    """the MARKET VALUE MV = raw close(r) x S x F(a) / F(r) (S = NETISS's share count: the latest usable cover-page value, else the balance sheet's; a = its as-of date) and [A3]'s two-way split check on (a, r]: a 2-for-1 that F and the calendar both show
    (the count before the split is doubled by F(a) / F(r)), a calendar split F does not show and an F change the calendar does not show (no score until a passes the split), a window that starts before the calendar (F alone stands); no share fact for
    the CIK, no usable S at r, S zero, no factor; the scale rule |score| > 0.50 (no score, LISTED) and the 0.15 flag; a negative component TTM (no score in the cells that read it - CHOICE); [B17] S point in time and fresh: an S as of 16
    months before the rank is 'stale S', 14 months scores, exactly 15 (the clipped day) is within; a restated S filed later never replaces the first-filed value; a stale cover-page count does not fall back to a fresh balance-sheet one (CHOICE)"""
    days = pd.bdate_range("2023-01-02", "2025-06-27")
    T, n = len(days), 17
    sp = days.get_loc(TS("2024-06-14"))
    F, Cl = np.ones((T, n)), np.full((T, n), 100.0)
    F[:sp, 0], Cl[:sp, 0] = 2.0, 200.0
    F[:sp, 2], Cl[:sp, 2] = 2.0, 200.0
    Fy = lambda cik, **v: fy_rows(cik, "2023-01-01", "2023-12-31", "2024-02-20", **v)
    rows = sum((Fy(f"C{i}", REP=3e9, DIV=1e9, ISS=0.5e9) for i in list(range(9)) + [13, 14, 15, 16]), []) + Fy("C9", REP=60e9) + Fy("C10", REP=20e9)
    rows += fy_rows("C11", "2023-01-01", "2023-12-31", "2024-02-20", REP=1e9, DIV=1e9) + fy_rows("C11", "2023-01-01", "2023-03-31", "2023-05-02", "10-Q", REP=3e9, DIV=0.1e9) + fy_rows("C11", "2024-01-01", "2024-03-31", "2024-05-02", "10-Q", REP=1e9, DIV=0.2e9)
    rows += fy_rows("C12", "2023-01-01", "2023-12-31", "2024-02-20", REP=4e9, DIV=1e9) + fy_rows("C12", "2023-01-01", "2023-03-31", "2023-05-02", "10-Q", REP=1e9, DIV=3e9) + fy_rows("C12", "2024-01-01", "2024-03-31", "2024-05-02", "10-Q", REP=1e9, DIV=1e9)
    qe = [month_end(TS(f"{y}-{m:02d}-01")) for y in (2022, 2023, 2024, 2025) for m in (3, 6, 9, 12)]
    sh = []
    for i in range(13):
        cik = f"C{i}"
        for q in qe:
            fd = q + pd.Timedelta(days=5)
            if fd >= days[-1] or i == 4:
                continue
            if i == 7 and q < TS("2024-09-30"):
                continue
            con = GAAP if i == 6 else DEI
            val = 0.0 if i == 5 else (2e9 if i == 0 and q >= TS("2024-06-30") else 1e9)
            sh.append((cik, con, val, f"{q:%Y-%m-%d}", f"{fd:%Y-%m-%d}"))
    sh += [("C13", DEI, 1e9, "2023-02-28", "2023-03-05"), ("C14", DEI, 1e9, "2023-04-28", "2023-05-03"),                                                  # [B17] one cover-page count each: as of 16 / 14 months before 2024-06-28
           ("C15", DEI, 1e9, "2024-03-31", "2024-04-05"), ("C15", DEI, 3e9, "2024-03-31", "2024-05-15", "C15-RESTATED", "10-Q/A"),                           # a restated S of the same as-of date, filed later
           ("C16", DEI, 1e9, "2023-02-28", "2023-03-05"), ("C16", GAAP, 1e9, "2024-03-31", "2024-04-05")]                                                 # a stale cover page beside a fresh balance sheet
    names = [f"M{i:02d}" for i in range(n)]
    W = hand_world(names, rows, days=days, share_rows=sh, F=F, Cl=Cl, splits=[("M00", "2024-06-14", "forward_split"), ("M01", "2024-06-14", "forward_split")], cal_start="2016-06-01")
    W.F[rr(W, "2024-06-28"), 8] = np.nan
    W.bb.cache.clear()
    sc = score_rank(W, rr(W, "2024-06-28"))
    cd = lambda j, k="P": REASONS[int(sc.code[k][j])]
    assert cd(0) == "scored" and close(sc.mv[0], 100.0 * 1e9 * 2.0) and dstr(sc.a[0]) == "2024-03-31" and sc.fa[0] == 2.0 and sc.fr[0] == 1.0, "a 2-for-1 both show: the count before it is doubled by F(a) / F(r)"
    assert cd(1) == "split_calendar_not_in_F" and cd(2) == "split_F_not_in_calendar" and sc.a3c[1] and sc.a3f[2]
    assert cd(3) == "scored" and cd(4) == "no_share_fact_for_cik" and cd(5) == "share_count_not_positive" and cd(6) == "scored" and sc.sg[6] >= W.ni.dei.n and cd(7) == "no_share_count_at_r" and cd(8) == "no_split_factor_or_close"
    assert all(cd(9, k) == "score_over_0.50" for k in CODE_KEYS) and np.isnan(sc.score["P"][9]) and cd(10) == "scored" and sc.flag["P"][10] and sc.flag["R"][10] and not sc.flag["P"][3] and close(sc.score["P"][10], 0.2)
    sc5 = score_rank(W, rr(W, "2024-05-31"))
    assert all(REASONS[int(sc5.code[k][11])] == "negative_ttm_component" for k in CODE_KEYS) and close(sc5.rep[11], 1e9 + 1e9 - 3e9), "REP's TTM negative: no score in any cell"
    assert REASONS[int(sc5.code["P"][12])] == "negative_ttm_component" and REASONS[int(sc5.code["R"][12])] == "scored" and close(sc5.div[12], 1e9 + 1e9 - 3e9), "only DIV's TTM negative: P (which reads it) has no score, R has one - CHOICE"
    # [B17]: point in time and fresh (as of 2024-06-28: 15 calendar months back is 2023-03-28)
    assert cd(13) == "stale_s" and all(cd(13, k) == "stale_s" for k in CODE_KEYS) and sc.stale_s[13] and dstr(sc.a[13]) == "2023-02-28", "an S 16 months old: stale S, unscored"
    assert cd(14) == "scored" and not sc.stale_s[14] and close(sc.mv[14], 100.0 * 1e9), "an S 14 months old scores"
    assert cd(15) == "scored" and sc.Sv[15] == 1e9 and close(sc.mv[15], 100.0 * 1e9) and close(sc.score["R"][15], (3e9 - 0.5e9) / 1e11), "a restated S (3e9, filed later) never replaces the first-filed value"
    assert cd(16) == "stale_s" and sc.sg[16] < W.ni.dei.n, "CHOICE: the cover page comes first and is then tested - a stale one does not fall back to the fresh balance sheet"
    sb = score_rank(W, rr(W, "2024-05-31"))
    assert REASONS[int(sb.code["P"][13])] == "scored" and dstr(sb.a[13]) == "2023-02-28", "2024-05-31 less 15 months is 2023-02-28 (the 31st clipped): that day itself is within"
    assert not brute_s_stale(TS("2023-02-28"), TS("2024-05-31")) and brute_s_stale(TS("2023-02-27"), TS("2024-05-31")) and brute_s_stale(TS("2023-03-27"), TS("2024-06-28")) and not brute_s_stale(TS("2023-03-28"), TS("2024-06-28"))
    sc7 = score_rank(W, rr(W, "2024-07-15"))                                                  # (197 days after FY 2023's end: not stale yet)
    assert REASONS[int(sc7.code["P"][1])] == "scored" and REASONS[int(sc7.code["P"][2])] == "scored" and close(sc7.mv[0], 100.0 * 2e9), "once a passes the split the check has nothing to say"
    # a window that starts before the calendar: F alone stands (counted), no [A3] failure
    W2 = hand_world(names[:3], rows[:sum(1 for r in rows if r[0] in ("C0", "C1", "C2"))], days=days, share_rows=[r for r in sh if r[0] in ("C0", "C1", "C2")], F=F[:, :3], Cl=Cl[:, :3], cal_start="2024-05-01")
    s2 = score_rank(W2, rr(W2, "2024-06-28"))
    assert REASONS[int(s2.code["P"][2])] == "scored" and s2.f_alone[2] and close(s2.mv[2], 100.0 * 1e9 * 2.0), "a before the calendar's start: F alone stands"
    n = compare_scores(W, brute_cash(W.cash_rows), W.sh_frame, W.cal, [rr(W, d) for d in ("2024-02-29", "2024-05-31", "2024-06-28", "2024-07-15", "2024-07-31", "2025-01-31")])
    assert n == 6 * 17


def random_cash_world(seed):
    """a random hand world for the recount: 12 names on 9 CIKs (two names share a CIK; one CIK has no share fact, one no cash fact), random fiscal-year ends, Q1 / H / 9M / FY periods with random lags (a few before the period's end), comparatives,
    amendments and restatements, ambiguous days, missing and negative values, odd-length periods, a few fiscal-year changes; random share counts (some zero, some balance sheet only); a 2-for-1 that F and the calendar show, one only F shows, one
    only the calendar shows"""
    rng = np.random.default_rng(seed)
    days = pd.bdate_range("2021-01-04", "2025-06-27")
    T, n = len(days), 12
    ciks = [f"R{i}" for i in range(9)] + ["R0", "R1", "R8"]
    rows = []
    for i in range(9):
        if i == 7:
            continue
        g = CashGen(f"R{i}", rng)
        fye = int(rng.choice([3, 6, 9, 12]))
        per = fiscal_periods(fye, 2020, 2025)
        if i == 5:                                                       # a fiscal-year change in 2023
            per = [p for p in per if p[3] < TS("2023-01-01")] + [(2023, "Q", TS("2023-01-01"), TS("2023-03-31"), 3)] + [p for p in fiscal_periods(3, 2024, 2025)]
        vals = {}
        for (Y, t, s, e, m) in per:
            lag = int(rng.integers(25, 75)) if rng.random() > 0.03 else -int(rng.integers(1, 20))
            filed = e + pd.Timedelta(days=lag)
            if filed > days[-1] + pd.Timedelta(days=30):
                continue
            facts = []
            for c in ("ST", "REP", "REPE", "DIV", "DIVA", "ISS", "ISSE", "IPO", "OPT", "PLAN", "TW"):
                if c != "ST" and rng.random() < 0.45:
                    continue
                key = (c, s, e)
                if key not in vals:
                    vals[key] = None if rng.random() < 0.02 else float(rng.choice([-1.0, 1.0], p=[0.04, 0.96]) * round(rng.uniform(0.1, 3.0), 2) * 1e9 * m / 12)
                facts.append((AL[c], s, e, vals[key]))
            if rng.random() < 0.15 and facts:                             # a same-value pair in one filing
                c0 = facts[-1]
                facts.append((AL["PLN"], c0[1], c0[2], c0[3]))
            g.filing(filed, "10-K" if t == "FY" else "10-Q", facts)
            if rng.random() < 0.1:
                g.filing(filed + pd.Timedelta(days=int(rng.integers(5, 60))), "10-Q/A", [(c, s_, e_, (v * 1.3 if v is not None else 1.0)) for c, s_, e_, v in facts])
            if rng.random() < 0.05:
                g.filing(filed, "10-Q", [(c, s_, e_, (v * 0.7 if v is not None else 2.0)) for c, s_, e_, v in facts[:2]], accn=f"R{i}-SAMEDAY-{len(g.rows)}")
        if rng.random() < 0.5:
            g.filing(TS("2024-03-01"), "8-K", [(AL["ST"], TS("2023-07-01"), TS("2023-10-28"), -1e9)])          # an odd length (119 days): no type
        rows += g.rows
    sh = []
    qe = [month_end(TS(f"{y}-{m:02d}-01")) for y in range(2020, 2026) for m in (3, 6, 9, 12)]
    for i in range(9):
        if i == 6:
            continue
        for q in qe:
            fd = q + pd.Timedelta(days=int(rng.integers(3, 40)))
            if fd >= days[-1] or rng.random() < 0.08:
                continue
            sh.append((f"R{i}", GAAP if i == 4 else DEI, 0.0 if (i == 3 and q.year == 2023) else float(rng.uniform(2e8, 2e9)), f"{q:%Y-%m-%d}", f"{fd:%Y-%m-%d}"))
    F = np.ones((T, n))
    Cl = np.full((T, n), 100.0) * np.exp(np.cumsum(rng.normal(0, 0.01, (T, n)), axis=0))
    for j, d in ((0, "2023-05-15"), (1, "2022-08-15")):
        k = days.get_loc(TS(d))
        F[:k, j] = 2.0
        Cl[:k, j] *= 2.0
    names = [f"X{i:02d}" for i in range(n)]
    W = hand_world(names, rows, days=days, share_rows=sh, F=F, Cl=Cl, splits=[("X00", "2023-05-15", "forward_split"), ("X02", "2024-02-15", "forward_split")], cal_start="2016-06-01", ciks=ciks)
    return W


def t_random():
    """every score of every name at random ranks of three random hand worlds (random_cash_world) against the plain-python recount: the codes in the registered order, the scores, the flags, the TTMs, the market value, the zero-rule flags"""
    n = 0
    for seed in (11, 12, 13):
        W = random_cash_world(seed)
        rng = np.random.default_rng(seed)
        ranks = sorted(set(rng.integers(300, W.T, 14).tolist()))
        n += compare_scores(W, brute_cash(W.cash_rows), W.sh_frame, W.cal, ranks)
        codes = Counter(REASONS[int(c)] for r in ranks for c in score_rank(W, r).code["P"])
        assert codes["scored"] > 10 and sum(codes.values()) == len(ranks) * W.S, codes
    assert n > 300


def t_sides():
    """the sides: 150 scored names or more -> 50 a side, fewer -> the top / bottom THIRD (n // 3) when that is at least 20, else nothing; the FLAT twin always the thirds (at least 20); the longs are the k HIGHEST and the shorts the k LOWEST (ties:
    the short takes the lower symbol, the long the higher - RESMOM's convention), the sides never share a name"""
    assert [side_n(n) for n in (500, 150, 149, 100, 61, 60, 59, 20, 1, 0)] == [(50, "top"), (50, "top"), (49, "third"), (33, "third"), (20, "third"), (20, "third"), (0, "none"), (0, "none"), (0, "none"), (0, "none")]
    assert [flat_n(n) for n in (500, 150, 60, 59, 0)] == [(166, "third"), (50, "third"), (20, "third"), (0, "none"), (0, "none")]
    with spec(n_side=15, min_scored=45, min_side=10, flat_min=3):
        assert [side_n(n) for n in (100, 45, 44, 30, 29)] == [(15, "top"), (15, "top"), (14, "third"), (10, "third"), (0, "none")] and flat_n(9) == (3, "third") and flat_n(8) == (0, "none")
        assert NI.SPEC["min_scored"] == 45 and NI.SPEC["min_side"] == 10, "NETISS's cells run on the same shrunk rule (the NETISS question)"
    assert NI.SPEC["min_scored"] == 150 and SPEC["flat_min"] == 20 and M17.SPEC["n_side"] == 50, "nothing stays patched"
    cols = np.array([10, 11, 12, 13, 14, 15])
    score = np.array([0.1, 0.1, 0.5, 0.5, -0.2, -0.2])
    lg, sh = pick_sides(cols, score, 2)
    assert sorted(lg.tolist()) == [2, 3] and sorted(sh.tolist()) == [4, 5], "the 2 highest are the longs, the 2 lowest the shorts"
    lg, sh = pick_sides(cols, score, 1)
    assert lg.tolist() == [3] and sh.tolist() == [4], "a tie: the long takes the HIGHER symbol, the short the LOWER (RESMOM's order)"
    rng = np.random.default_rng(3)
    for n, k in ((30, 10), (47, 15), (150, 50), (151, 50), (20, 10)):
        sc_ = np.round(rng.normal(0.0, 0.05, n), 2)
        cs_ = np.sort(rng.choice(np.arange(1000), n, replace=False))
        lg, sh = pick_sides(cs_, sc_, k)
        assert lg.tolist() == sorted(range(n), key=lambda i: (-sc_[i], -cs_[i]))[:k] and sh.tolist() == sorted(range(n), key=lambda i: (sc_[i], cs_[i]))[:k] and not set(lg.tolist()) & set(sh.tolist()), (n, k)
    for n in (10, 23, 99):
        sc_ = np.round(rng.normal(0.0, 0.05, n), 3)
        cs_ = np.sort(rng.choice(np.arange(1000), n, replace=False))
        lab = decile_labels(cs_, sc_)
        assert lab.tolist() == [brute_dec(dict(zip(range(n), sc_)))[i] for i in range(n)], "ten equal-count deciles, ties by symbol order (the columns are sorted)"
        assert all(sc_[lab == d].max() <= sc_[lab == d + 1].min() for d in range(9)), "deciles are ordered: 1 = the lowest score (the biggest net raisers)"


# ------------------------------------------------------------------ the toy world: r21_netiss's (r17_resmom's 14 names and NETISS's share counts) + hand-made cash-flow filings
def bb_toy(seed=1, T=620, Sn=14):
    """r21_netiss.ni_toy (r17_resmom's toy world: 14 names from 2024-01-01 with every hygiene / dividend / spin-off / stopped-print case; NETISS's share-count filings with its planted cases - N00's 2-for-1 on 2025-03-14 that F and the calendar show,
    N02 a foreign filer, N03 not in the map, N04 no share filing ...) with hand-made CASH-FLOW filings 2022 .. 2026: a net payout rate per name (N13 the biggest raiser), the cash = the rate x a reference market value x the months, 10-Q
    year-to-date periods and 10-K years each with the prior year's comparative; the planted cash cases: N00 a x100 repurchase in its Q1 2025 10-Q (|score| > 0.50), N01 a June fiscal year, N05 the repurchase fallback concept and the
    withholding twin, N06 the fallback in 10-Qs and the first concept in 10-Ks (mixed across one TTM), N07 a fiscal-year change (a Jan - Mar 2025 transition quarter, a 10-KT, then April years: [B1]), N08 issuance from the second primary
    + options exercised + a stock-plan total of the same value in its 10-Qs (counted once), N09 a 10-Q/A after every 10-Q with other values (the first filed stands) and a calendar split on 2025-06-16 that F does not show ([A3]; inside the
    2025-05-30 rank's hold: the judged reading removes it), N10 a sign error in FY 2024's 10-K repurchases (unusable) and smaller 2025 repurchases (a negative TTM), N11 no filing after the 2024-06-30 quarter (stale from the 2025-01 ranks),
    N12 10-K only (and the withholding twin); every third name pays no dividend (the zero rule) -> SimpleNamespace(W, frame (NETISS's share facts), mrows, cal, cik_of, cash_rows, q)"""
    tt = NI.ni_toy(seed, T=T, Sn=Sn)
    W = tt.W
    rng = np.random.default_rng(seed + 70)
    q = np.linspace(-0.06, 0.08, Sn)[np.random.default_rng(seed + 3).permutation(Sn)]
    q[0], q[5], q[6], q[8], q[9], q[10] = 0.05, 0.03, 0.035, 0.02, 0.025, 0.04                         # the planted names repurchase every period (a positive REP to misfile)
    q[7], q[13] = 0.20, -0.30                                                                          # N07 the heavy payer, N13 the heavy issuer: |score| > 0.15 flags that the cells pick
    dv = np.where(np.arange(Sn) % 3 == 0, 0.0, 0.01 + 0.001 * np.arange(Sn))
    pb = 0.004 + 0.0004 * np.arange(Sn)
    fr_ = tt.frame
    mvref = np.zeros(Sn)
    for j in range(Sn):
        d = fr_[(fr_["cik"] == f"K{j}") & (fr_["concept"] == DEI)].sort_values("end")
        mvref[j] = float(np.nanmean(W.Cl[150:250, j])) * (float(d["val"].iloc[0]) if len(d) else 2e8)
    rows = []
    for j in range(Sn):
        g = CashGen(f"K{j}", rng)
        vals = {}
        per = fiscal_periods(6 if j == 1 else 12, 2022, 2026)
        if j == 7:
            per = fiscal_periods(12, 2022, 2024) + [(2025, "Q", TS("2025-01-01"), TS("2025-03-31"), 3)] + fiscal_periods(3, 2026, 2026)
        if j == 11:
            per = [p for p in per if p[3] <= TS("2024-06-30")]
        if j == 12:
            per = [p for p in per if p[1] == "FY"]
        pset = {(p[2], p[3]): p[4] for p in per}

        def facts(s, e, m, form, j=j, vals=vals):
            if (s, e) not in vals:
                yq = q[j] + 0.01 * math.sin(e.year + j)
                X = mvref[j] * m / 12.0
                rep = max(yq - dv[j] + pb[j], 0.0) * X
                vals[(s, e)] = {"REP": rep * (1.0 + 0.03 * float(rng.normal())), "DIV": dv[j] * X, "ISS": max(rep + dv[j] * X - yq * X, 0.0), "TW": 0.3 * pb[j] * X}
            v = vals[(s, e)]
            rep, div, iss = v["REP"], v["DIV"], v["ISS"]
            if j == 0 and s == TS("2025-01-01") and e == TS("2025-03-31"):
                rep *= 100.0
            if j == 10 and e == TS("2024-12-31") and m == 12:
                rep = -rep
            if j == 10 and e.year == 2025:
                rep *= 0.4
            out = [(C_ST[0], s, e, -(rep + div - iss) - 1e6)]
            if rep != 0.0:
                out.append((C_REP[1] if (j == 5 or (j == 6 and form != "10-K")) else C_REP[0], s, e, rep))
            if div > 0:
                out.append((C_DIV[0], s, e, div))
            if j == 8:
                out += [(C_ISS[1], s, e, 0.6 * iss), (C_PLAN[0], s, e, 0.4 * iss)] + ([(C_PLAN[3], s, e, 0.4 * iss)] if form != "10-K" else [])
            elif iss > 0:
                out.append((C_ISS[0], s, e, iss))
            if j in (5, 12):
                out.append((C_TW[0], s, e, v["TW"]))
            return out
        for (_Y, t, s, e, m) in per:
            form = "10-K" if t == "FY" else "10-Q"
            filed = e + pd.Timedelta(days=56 if t == "FY" else 36)
            if j == 7 and t == "Q" and s == TS("2025-01-01"):
                form, filed = "10-KT", TS("2025-05-20")
            fl = facts(s, e, m, form)
            ps, pe = s - pd.DateOffset(years=1), month_end(e - pd.DateOffset(years=1))
            if (ps, pe) in pset:
                fl += facts(ps, pe, pset[(ps, pe)], form)
            g.filing(filed, form, fl)
            if j == 9 and form == "10-Q":
                g.filing(filed + pd.Timedelta(days=20), "10-Q/A", [(c, s_, e_, v * 1.25) for c, s_, e_, v in fl])
        rows += g.rows
    cal = NI.cal_of([("N00", "2025-03-14", "forward_split"), ("N09", "2025-06-16", "forward_split")], start="2024-01-01")
    return SimpleNamespace(W=W, frame=tt.frame, mrows=tt.mrows, cal=cal, cik_of=tt.cik_of, cash_rows=rows, q=q)


def bb_ready(**kw):
    """the toy world with its share and cash filings attached, built under the shrunk SPEC the callers hold"""
    tt = bb_toy(**kw)
    attach_buyback(tt.W, build_cash(cf_of(tt.cash_rows)), NI.build_facts(tt.frame), NI.mp_of(tt.mrows), tt.cal)
    tt.ent = brute_cash(tt.cash_rows)
    return tt


TOY_SPEC = dict(n_side=3, min_scored=8, min_side=2, dec_min=7, flat_min=1)     # the toy has 4 - 9 scored names a rank: 3 a side (the 150 / thirds / 20 rule shrunk to 8 / 2), deciles from 7 names, the FLAT twin's thirds from 1 a side


def t_pipeline():
    """the vectorised build against the plain-python recount on the toy world with the REGISTERED windows (252 / 230), in the four readings ('remove' / 'naive' / 'keep' = [B10]'s removal reading, a report / 'close' = the judged one [B13]):
    every pool (the 'keep' reading removes N09 for its calendar split inside the 2025-05-30 rank's hold, the judged one keeps it on the split-safe path), the close rows, every score, [A13], the sides, the picks of the cells and the twins, the
    deciles, the counts and the daily path of every scored name under four costings; then the planted cases one by one"""
    with spec(**TOY_SPEC), D15.spec(univ=14):
        tt = bb_ready()
        W = tt.W
        W.aud1[W.days.get_loc(TS("2025-02-03")), 8] = True                                  # N08: a hand-audit data event at fill session 2025-02-03 (the rebalance ranked 2025-01-31)
        lo, hi = W.days[0], W.days[-1]
        out, n = {}, 0
        for pm in ("remove", "naive", "keep", "close"):
            L = bb_build(W, lo, hi, pm)
            Bz = brute_bb(W, tt.ent, tt.frame, tt.cal, tt.cik_of, lo, hi, pm)
            n += compare_bb(W, L, Bz, f"toy {pm}")
            out[pm] = (L, Bz)
            if pm in ("remove", "close"):
                series_check(W, L, Bz)
        Lr, Lk, LK, LC = out["remove"][0], out["naive"][0], out["keep"][0], out["close"][0]
        assert JUDGED == "close"
        by = lambda L_, d: next(r_ for r_ in L_.recs if W.days[r_.r] == TS(d))
        modes = Counter((c, rec.cell[c].mode) for rec in LC.recs for c in CELLS if len(rec.pool))
        assert modes[("P", "top")] >= 2 and modes[("P", "third")] + modes[("P", "none")] >= 1 and sum(rec.cell["P"].traded for rec in LC.recs) >= 8, modes
        # the planted cases through the whole pipeline
        at = lambda d: score_rank(W, rr(W, d))
        cd = lambda sc_, j, k="P": REASONS[int(sc_.code[k][j])]
        s5 = at("2025-05-30")
        assert cd(s5, 2) == "foreign_filer" and cd(s5, 3) == "not_in_map" and cd(s5, 4) == "no_share_fact_for_cik" and cd(s5, 0) == "score_over_0.50" and cd(s5, 11) == "stale_over_200_days" and cd(s5, 10) == "negative_ttm_component", [cd(s5, j) for j in range(14)]
        assert cd(at("2024-12-31"), 11) != "stale_over_200_days" and cd(at("2025-01-31"), 11) == "stale_over_200_days" and cd(at("2024-12-31"), 12) == "stale_over_200_days" and at("2025-03-31").kind[12] == 1 and cd(at("2025-03-31"), 12) == "scored"
        s6 = at("2025-06-30")
        assert s6.kind[7] == 2 and dstr(s6.s[7]) == "2025-01-01" and cd(at("2025-08-29"), 7) == "fiscal_year_change", "[B1]: the transition quarter reads, the first quarter of the new year does not"
        assert any(cd(at(d), 9) == "split_calendar_not_in_F" for d in ("2025-06-30", "2025-07-31", "2025-08-29")), "N09's calendar split that F does not show: no market value while the share count's as-of date is before it"
        s2, s4 = at("2025-02-28"), at("2025-04-30")
        assert cd(s2, 0) == "scored" and cd(s4, 0) == "scored" and s2.fr[0] == 2.0 and s4.fr[0] == 1.0 and 0.6 < s4.mv[0] / s2.mv[0] < 1.6, "N00's 2-for-1 (F and the calendar both show it): the market value does not jump"
        cu = comp_use(s5, np.array([5, 6, 8]))
        assert cu["rep"]["fallback"][0] and cu["rep"]["mixed"][1] and cu["iss"]["second"][2] and cu["iss"]["dedup"][2], "N05 the fallback, N06 mixed, N08 [B7]"
        # the readings: the leaky one removes in-hold flags, the naive keeps them on the raw path, [B10]'s 'keep' removes the announced events (N09's calendar split in the 2025-05-30 hold), the judged one [B13] removes nothing
        assert 9 not in by(LK, "2025-05-30").pool.tolist() and 9 in by(Lk, "2025-05-30").pool.tolist() and 9 in by(LC, "2025-05-30").pool.tolist() and sum(c.get("post_calendar_split", 0) for c in LK.cnt.values()) >= 1
        for a_, b_ in zip(Lr.recs, Lk.recs):
            assert set(a_.pool.tolist()) <= set(b_.pool.tolist())
        for b_, k_ in zip(Lk.recs, LK.recs):
            known = set(np.flatnonzero(np.asarray(W.CSPL[k_.f + 1:k_.x + 1]).any(axis=0)).tolist()) | {int(j) for j in b_.pool[b_.spin_hold]}
            assert set(k_.pool.tolist()) == set(b_.pool.tolist()) - known and not k_.naive.any(), (W.days[k_.r], k_.pool.tolist(), b_.pool.tolist(), sorted(known))
        # [B13] the judged 'close' reading = the look-ahead pool itself (no in-hold removal), never on the raw path; a name with a spin-off / stock-dividend ex-date inside the hold closes at the close before it (r21_netiss's t_pipeline)
        n_cl, n_cs = 0, 0
        for b_, c_ in zip(Lk.recs, LC.recs):
            assert c_.pool.tolist() == b_.pool.tolist() and not c_.naive.any(), (W.days[c_.r], c_.pool.tolist(), b_.pool.tolist())
            assert ((c_.close >= 0) == c_.spin_hold).all() and all(not W.SPN[c_.f + 1:e_ + 1, j_].any() and W.SPN[e_ + 1, j_] for j_, e_ in zip(c_.pool.tolist(), c_.close.tolist()) if e_ >= 0)
            n_cl += int((c_.close >= 0).sum())
            n_cs += int(np.asarray(W.CSPL[c_.f + 1:c_.x + 1][:, c_.pool]).any(axis=0).sum())
        cC = sum((Counter(c_) for c_ in LC.cnt.values()), Counter())
        assert cC["closed_spin"] == n_cl >= 1 and cC["kept_calendar_split"] == n_cs >= 1 and cC["post_spin"] + cC["post_calendar_split"] == 0 and cC["kept_flagged"] >= 1, dict(cC)
        for L_ in (Lr, LK, LC):
            for y, c in L_.cnt.items():
                assert c["universe"] == sum(c[k_] for k_ in NI.COUNT_KEYS[1:]), (y, dict(c))
        assert 8 not in by(LC, "2025-01-31").pool.tolist() and 8 not in by(LK, "2025-01-31").pool.tolist() and LC.cnt[2025]["audit"] >= 1 and (AUD, int(W.days.get_loc(TS("2025-02-03"))), 8) in W.aud_hit, "the audit's data event"
        # a counts-only build keeps no unit path and no pick but counts the same
        Lc = bb_build(W, lo, hi, JUDGED, units=False, counts_only=True)
        assert [rec.pool.tolist() for rec in Lc.recs] == [rec.pool.tolist() for rec in LC.recs] and all(rec.U is None and not len(rec.cell["P"].long) for rec in Lc.recs)
        assert [rec.close.tolist() for rec in Lc.recs] == [rec.close.tolist() for rec in LC.recs]
        for y, c in LC.cnt.items():
            for k_ in [k2 for k2 in c if k2.startswith(("scored_", "no_score_", "mode_", "ns_", "dec_", "kept_", "closed_"))]:
                assert Lc.cnt[y][k_] == c[k_], (y, k_)
        assert [rec.cell[k].traded for rec in Lc.recs for k in TRADED] == [rec.cell[k].traded for rec in LC.recs for k in TRADED]
        # the mode is called 'close' ([B13]): any other name - 's1' included - is refused
        for bad in ("s1", "judged", ""):
            try:
                bb_one(W, LC.recs[0].r, LC.recs[0].f, LC.recs[0].x, bad, units=False)
                raise AssertionError(f"post_mode {bad!r} must be refused")
            except ValueError:
                pass
        W.aud1[:] = False
    return n


def null_replica(W, L, q, cell, nreps, vcode, pnl):
    """r21_netiss.ni_null's draws for one cell replayed with a given P&L function (the same seeds, the same draw order) -> (the P&L (nreps, T), {rebalance index: its draw order}) - the test that the null reads [B13]'s exit column"""
    rng = np.random.default_rng([SEED, q, vcode])
    acc, slot, cfg, orders = np.zeros((nreps, W.T)), M17.SPEC["slot"], D15.l1_cfg(), {}
    for i, rec in enumerate(L.recs):
        cc = rec.cell[cell]
        if not cc.traded:
            continue
        idx, kt = np.arange(cc.n), W.k[rec.f:rec.x + 1]
        PL, PS = pnl(cc.U, idx, 1, cfg, kt), pnl(cc.U, idx, -1, cfg, kt)
        o = orders[i] = D15.draw_order(rng, nreps, cc.n, 2 * cc.k)
        acc[:, rec.f:rec.x + 1] += slot * (PL[o[:, :cc.k]].sum(axis=1) + PS[o[:, cc.k:]].sum(axis=1))
    return acc, orders


def t_close():
    """[B13] MANAGER's hygiene edit S1 (#127) - the judged reading is r17_resmom's post_mode 'close' - on the BUYBACK toy, the 2025-02-28 rank (f = 03-03, x = 04-01) case by case, each against plain python: NO in-hold event removes a
    name (the pool is the look-ahead reading's, every name on the split-safe path): N00, FLAGGED inside the hold (its registered 2-for-1 on 03-14) and with the CALENDAR's split there, is held on the split-safe path ([B10]'s 'keep'
    removed it), and N09's calendar split inside the 05-30 rank's hold (F does not show it) keeps it too; a spin-off / stock-dividend ex-date e in f < e <= x CLOSES the position at the close of e-1 - N12's stock dividend on 03-12
    (closed 03-11: no mark, no dividend, no borrow after it, the exit cost on that row; its dividend of 03-21 is the buyer's) and N10's spin-off ON the exit session (inside: closed 03-31; its dividend of 03-21 kept), while N09's ex-date
    on the FILL session is bought ex (held to the exit); every pool name's path under four costings and both sides recounted by plain python (brute_pos: r17_resmom.brute_close_path for the closed ones); N12 with NO close on e-1
    exits at its last mark and has stopped printing there (the -100% long, the short at zero [R2]); the counts (closed_spin = the names [B10]'s 'keep' removed for an ex-date, kept_calendar_split = the ones it removed for a calendar
    split); the null draws the same pool with the same cut paths: replayed with r17_resmom's l1_pnl_x (never r15's l1_pnl) and every draw holding a closed name recounted by plain python"""
    with spec(**TOY_SPEC), D15.spec(univ=14):
        tt = bb_ready()
        W = tt.W
        lo, hi = W.days[0], W.days[-1]
        Lc, Bc = bb_build(W, lo, hi, "close"), brute_bb(W, tt.ent, tt.frame, tt.cal, tt.cik_of, lo, hi, "close")
        Ln, LK = bb_build(W, lo, hi, "naive"), bb_build(W, lo, hi, "keep")
        assert len(Lc.recs) == len(Bc) == len(Ln.recs) == len(LK.recs) and all(r_.r == b_["r"] for r_, b_ in zip(Lc.recs, Bc))
        ri = next(i for i, r_ in enumerate(Lc.recs) if W.days[r_.r] == TS("2025-02-28"))
        rec, b, f, x = Lc.recs[ri], Bc[ri], Lc.recs[ri].f, Lc.recs[ri].x
        assert (W.days[f], W.days[x]) == (TS("2025-03-03"), TS("2025-04-01")) and rec.traded
        assert rec.pool.tolist() == Ln.recs[ri].pool.tolist() and not rec.naive.any(), "no in-hold event removes a name: the look-ahead reading's pool, on the split-safe path"
        pos = {int(j): i for i, j in enumerate(rec.pool)}
        assert {0, 9, 10, 12} <= set(pos) and {10, 12} <= set(rec.pool[rec.cell["P"].idx].tolist()), sorted(pos)
        e12, e10 = rr(W, "2025-03-12"), rr(W, "2025-04-01")
        # (1) the close rows - N12 03-11, N10 03-31 (its ex-date is the EXIT session: inside), N09 none (its ex-date is the FILL session: bought ex); N09 closes in the 01-31 rank's hold, whose exit session is its ex-date
        assert rec.close[pos[12]] == e12 - 1 and rec.close[pos[10]] == e10 - 1 == x - 1 and rec.close[pos[9]] == -1 and rec.close[pos[0]] == -1 and int((rec.close >= 0).sum()) == 2, rec.close.tolist()
        assert [b["pool"][j][3] for j in (12, 10, 9, 0)] == [e12, e10, -1, -1], "the recount's own ex-dates"
        r1 = Lc.recs[ri - 1]
        assert W.days[r1.r] == TS("2025-01-31") and r1.x == f and r1.close[r1.pool.tolist().index(9)] == f - 1, "N09's ex-date on the 01-31 rank's exit session: closed at the close before it"
        # (2) the cut paths: nothing after the close row (no mark, no dividend, no borrow), the exit value the split-safe close of e-1 over the entry open
        H, U = x - f + 1, rec.U
        for j, e in ((12, e12), (10, e10)):
            i, xc = pos[j], e - 1 - f
            assert U.xc[i] == xc and (U.G[i, xc + 1:] == 0).all() and (U.mk[i, xc + 1:] == 0).all() and (U.div[i, xc:] == 0).all(), j
            assert abs(U.ve[i] - W.Ac[e - 1, j] / W.Ao[f, j]) < 1e-15 and not U.st[i] and abs(U.G[i].sum() - (U.ve[i] - 1.0 + U.div[i].sum())) < 1e-12, j
        assert U.xc[pos[9]] == U.xc[pos[0]] == H - 1
        U0 = M17.rm_units(W, f, x, rec.pool, None)                                          # the same pool held to the exit session
        assert U0.div[pos[12]].any() and not U.div[pos[12]].any(), "N12's dividend (ex-date after its close) belongs to the buyer at the close of e-1: cut"
        assert U.div[pos[10]].any() and np.array_equal(U.div[pos[10]], U0.div[pos[10]]), "N10's dividend (ex-date before its close) is kept"
        # (3) every pool name's path, four costings, both sides: the harness (r17_resmom.l1_pnl_x on the pool's units) against plain python (brute_pos on the recount's own ex-dates)
        kt, n = W.k[f:x + 1], 0
        for nm, cfg, kw in COSTINGS:
            kw2 = {"bps": kw.get("bps", COST_BPS), "borrow": kw.get("borrow", (BORROW, None)), "kt": kt if kw.get("k") else None, "lose100": kw.get("lose100", False)}
            for sd in (1, -1):
                P = M17.l1_pnl_x(U, np.arange(len(rec.pool)), sd, cfg, kt)
                for i, j in enumerate(rec.pool.tolist()):
                    assert close(P[i], brute_pos(W, b, j, sd, **kw2)), (nm, j, sd)
                    n += 1
        # (4) a closed position by hand: the exit cost on the close's row, nothing after it; a short pays borrow only on the nights before rows f+1 .. e-1
        c0, i, xc = COST_BPS * 1e-4, pos[12], e12 - 1 - f
        gsum = U.ve[i] - 1.0 + U.div[i].sum()
        PL = M17.l1_pnl_x(U, np.array([i]), 1, D15.l1_cfg(), kt)[0]
        assert (PL[xc + 1:] == 0).all() and abs(PL.sum() - (gsum - c0 - c0 * U.ve[i])) < 1e-12 and abs(PL[xc] - (U.G[i, xc] - c0 * U.ve[i])) < 1e-15
        PS = M17.l1_pnl_x(U, np.array([i]), -1, D15.l1_cfg(), kt)[0]
        assert (PS[xc + 1:] == 0).all() and abs(PS.sum() - (-gsum - c0 - c0 * U.ve[i] - BORROW / 252.0 * U.mk[i, 1:xc + 1].sum())) < 1e-12
        assert D15.l1_pnl(U, np.array([i]), 1, D15.l1_cfg(), kt)[0][-1] != 0.0, "r15's own l1_pnl books the exit cost on the last column - l1_pnl_x moves it"
        # (5) kept on the split-safe path: N00 (a hygiene flag and a calendar split inside the hold) and N09 at the 05-30 rank (a calendar split F does not show)
        q_split = HYG.index("split")
        assert W.hyg(rec.r + 1, x, np.array([0]))[q_split][0] and np.asarray(W.CSPL[f + 1:x + 1, 0]).any() and 0 not in LK.recs[ri].pool.tolist() and Ln.recs[ri].naive[Ln.recs[ri].pool.tolist().index(0)], "N00"
        ua, ur = M17.rm_units(W, f, x, np.array([0]), None), M17.rm_units(W, f, x, np.array([0]), np.array([True]))
        assert np.array_equal(U.G[pos[0]], ua.G[0]) and ur.G[0].min() < -0.4 and ua.G[0].min() > -0.2, "N00 is held on the split-safe path: the raw path's halving on 03-14 is no loss here"
        r5 = next(i_ for i_, r_ in enumerate(Lc.recs) if W.days[r_.r] == TS("2025-05-30"))
        c5 = Lc.recs[r5]
        p9 = c5.pool.tolist().index(9)
        assert np.asarray(W.CSPL[c5.f + 1:c5.x + 1, 9]).any() and 9 not in LK.recs[r5].pool.tolist() and c5.close[p9] == -1 and not c5.naive[p9] and getattr(c5.U, "xc", None) is None, "N09's calendar split inside the 05-30 hold: kept, held to the exit (no close row in that rebalance: no exit column)"
        # (6) the counts: closed, never removed; the names [B10]'s 'keep' removed are the ones the judged reading closes / keeps on the split-safe path
        cC, cK = (sum((Counter(c_) for c_ in L_.cnt.values()), Counter()) for L_ in (Lc, LK))
        assert cC["closed_spin"] == sum(1 for b_ in Bc for j_ in b_["pool"] if b_["pool"][j_][3] >= 0) == cK["post_spin"] == 3 and cC["kept_calendar_split"] == cK["post_calendar_split"] == 2, (dict(cC), dict(cK))
        assert cC["post_spin"] == cC["post_calendar_split"] == 0 and cC["kept_split"] >= 1 and cC["kept_flagged"] == cK["kept_flagged"] + 1, "N00's split flag is kept by the judged reading only"
        # (7) no close on e-1: N12 exits at its last mark and has stopped printing there - the -100% long and the short at zero [R2] on the close's row; the harness against plain python
        Ac0, Cl0 = W.Ac.copy(), W.Cl.copy()
        try:
            W.Ac[e12 - 1, 12] = W.Cl[e12 - 1, 12] = np.nan
            rs = bb_one(W, rec.r, f, x, "close")[0]
            ps, Us = rs.pool.tolist().index(12), rs.U
            assert rs.close[ps] == e12 - 1 and Us.st[ps] and Us.ve[ps] == Us.mk[ps, xc] and (Us.G[ps, xc + 1:] == 0).all() and Us.xc[ps] == xc
            for nm, cfg, kw in COSTINGS:
                kw2 = {"bps": kw.get("bps", COST_BPS), "borrow": kw.get("borrow", (BORROW, None)), "kt": kt if kw.get("k") else None, "lose100": kw.get("lose100", False)}
                for sd in (1, -1):
                    got = M17.l1_pnl_x(Us, np.array([ps]), sd, cfg, kt)[0]
                    want, stopped = M17.brute_close_path(W, f, x, 12, sd, e12, **kw2)
                    assert stopped and close(got, want), (nm, sd)
            p100 = M17.l1_pnl_x(Us, np.array([ps]), 1, D15.l1_cfg(lose100=True), kt)[0]
            assert p100[xc] == -Us.mk[ps, xc] and (p100[xc + 1:] == 0).all(), "the long valued at -100% on the close's row"
            z0 = M17.l1_pnl_x(Us, np.array([ps]), -1, {**D15.l1_cfg(), "short0": True}, kt)[0]
            assert abs(z0.sum() - (1.0 - Us.div[ps].sum() - c0 - BORROW / 252.0 * Us.mk[ps, 1:xc + 1].sum())) < 1e-12 and (z0[xc + 1:] == 0).all(), "[R2] the short at zero keeps its full gain, on the close's row"
        finally:
            W.Ac[:], W.Cl[:] = Ac0, Cl0
        # (8) the null: the same pool, the same cut paths - replayed with l1_pnl_x (r15's l1_pnl would book the closed names' exit cost on the exit row); every draw that holds a closed name at the 02-28 rank recounted by plain python
        acc, slot = bb_null(W, Lc, 60, 0), M17.SPEC["slot"]
        for q, cell in enumerate(CELLS):
            rep_x, orders = null_replica(W, Lc, q, cell, 60, 0, M17.l1_pnl_x)
            assert np.allclose(acc[cell], rep_x, rtol=0, atol=1e-9), cell
            assert not np.allclose(acc[cell], null_replica(W, Lc, q, cell, 60, 0, D15.l1_pnl)[0], rtol=0, atol=1e-12), cell
            cc = rec.cell[cell]
            shut = {k_ for k_, p_ in enumerate(cc.idx.tolist()) if rec.close[p_] >= 0}
            ds = [d for d in range(60) if set(orders[ri][d].tolist()) & shut][:3]
            assert len(ds) == 3, (cell, ds)
            for d in ds:
                x0 = np.zeros(W.T)
                for i2, rec2 in enumerate(Lc.recs):
                    c2 = rec2.cell[cell]
                    if not c2.traded:
                        continue
                    names, cols2 = orders[i2][d], rec2.pool[c2.idx]
                    for sd, sel in ((1, names[:c2.k]), (-1, names[c2.k:])):
                        for i3 in sel:
                            x0[rec2.f:rec2.x + 1] += slot * np.array(brute_pos(W, Bc[i2], int(cols2[i3]), sd))
                assert close(acc[cell][d], x0), (cell, d)
    # (9) [B19] a PICKED position with a calendar split its factor does not show is LISTED before any P&L, with the calendar's ratio and the factor's move, and joins the hand audit's candidates as a data-event candidate; N00's split
    # on 03-14 (F and the registered flag show it) is not listed; every listed row recounted by plain python over every pick of every key
    with spec(**TOY_SPEC), D15.spec(univ=14):
        tt2 = bb_ready()
        W2 = tt2.W
        M17.attach_calendar_splits(W2, NI.cal_of([("N00", "2025-03-14", "forward_split"), ("N09", "2025-06-16", "forward_split"), ("N07", "2025-03-20", "forward_split")], start="2024-01-01"))
        root = tempfile.mkdtemp(prefix="buyback_selftest_")
        try:
            pth = os.path.join(root, "ca_wide.csv")
            with open(pth, "w", newline="\n") as fh:
                fh.write(",".join(M17.CA_COLS) + "\n" + "\n".join(["forward_split,N07,,,2025-03-20,2025-03-20,,,,2,1,,", "reverse_split,N09,,,2025-06-16,2025-06-16,,,,1,4,,", "cash_dividend,N07,,,2025-03-21,2025-03-21,,,0.2,,,,False",
                                                                     "forward_split,N07,,,2026-01-05,2026-01-05,,,,3,1,,"]) + "\n")
            ratios = split_ratios(pth, M17.sha_raw(pth), "2025-12-31")
            assert ratios == {("N07", "2025-03-20"): "2:1", ("N09", "2025-06-16"): "1:4"}, ratios
            refused(lambda: split_ratios(pth, "0" * 64, "2025-12-31"), "changed after wide_load checked it")
        finally:
            shutil.rmtree(root, ignore_errors=True)
        W2.bb.split_ratio = ratios
        L2 = bb_build(W2, W2.days[0], W2.days[-1], "close", units=False)
        rows = b19_rows(W2, L2)
        want = []
        for rec2 in L2.recs:
            picks = sorted({int(j) for k in TRADED if rec2.cell[k].traded for j in rec2.pool[rec2.cell[k].idx[np.r_[rec2.cell[k].long, rec2.cell[k].short]]].tolist()})
            for j in picks:
                for t in range(rec2.f + 1, rec2.x + 1):
                    if W2.CSPL[t, j] and not W2.chg[t, j] and not abs(W2.F[t, j] / W2.F[t - 1, j] - 1.0) > 0.01:
                        want.append((str(W2.syms[j]), f"{W2.days[rec2.r]:%Y-%m-%d}", f"{W2.days[t]:%Y-%m-%d}"))
        assert [(r_["symbol"], r_["rank"], r_["ex_date"]) for r_ in rows] == want, (rows, want)
        n7 = [r_ for r_ in rows if r_["symbol"] == "N07" and r_["rank"] == "2025-02-28"]
        assert len(n7) == 1 and n7[0]["ex_date"] == "2025-03-20" and n7[0]["split_ratio"] == "2:1" and n7[0]["factor_move"] == 1.0 and (n7[0]["fill"], n7[0]["exit"]) == ("2025-03-03", "2025-04-01") and "P long" in n7[0]["picked_by"], n7
        assert not any(r_["symbol"] == "N00" for r_ in rows) and np.asarray(W2.CSPL[rr(W2, "2025-03-14"), 0]) and W2.chg[rr(W2, "2025-03-14"), 0], "N00's calendar split IS in its factor: not listed"
        assert all(abs(r_["factor_move"] - 1.0) <= 0.01 or not np.isfinite(r_["factor_move"]) for r_ in rows)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            print_b19(rows)
            print_b19([])
        txt = buf.getvalue()
        assert "[B19] BEFORE ANY P&L" in txt and "N07 rank 2025-02-28 (fill 2025-03-03, exit 2025-04-01): calendar split ex-date 2025-03-20, ratio 2:1, the factor's move F_t / F_(t-1) = 1.0000; picked by P long" in txt and txt.rstrip().endswith("data-event candidate): none")
        cand = b19_candidate_rows(W2, L2, rows)
        c7 = next(c_ for c_ in cand if c_["symbol"] == "N07" and c_["date"] == "2025-03-03")
        assert len(cand) == len(rows) and c7["list"] == "b19_split_no_factor_move" and c7["data_event_candidate"] is True and c7["cell"] == "P" and c7["group"].split("|")[0] == "N07" and c7["rank_date"] == "2025-02-28"
        assert json.loads(json.dumps(rows, default=R11.js)) is not None
    return n


def t_nulls():
    """the family-aware null (r21_netiss's draw on this family's cells and seed): uniform draws per rebalance of as many names as the cell holds from the same eligible SCORED pool, seeded ([20261024, cell, vcode]), one stream per cell, longs and
    shorts disjoint, no P&L before the first fill, the mean over the draws equal to the pool's mean path, three whole draws recounted by plain python; the statistic = the MAX over the 2 cells per draw -> p5 / p50 / p95 and the DO's"""
    with spec(**TOY_SPEC), D15.spec(univ=14):
        tt = bb_ready()
        W = tt.W
        L = bb_build(W, W.days[0], W.days[-1])
        acc = bb_null(W, L, 400, 0)
        assert set(acc) == set(CELLS) and all(a.shape == (400, W.T) for a in acc.values()) and NI.CELLS == ("N12", "N24") and NI.SEED == 20261008, "r21_netiss is restored"
        cfg, slot = D15.l1_cfg(), M17.SPEC["slot"]
        first_fill = min(rec.f for rec in L.recs if any(rec.cell[c].traded for c in CELLS))
        for cell in CELLS:
            exp = 0.0
            for rec in L.recs:
                cc = rec.cell[cell]
                if cc.traded:
                    idx, kt = np.arange(cc.n), W.k[rec.f:rec.x + 1]
                    exp += slot * cc.k * float(M17.l1_pnl_x(cc.U, idx, 1, cfg, kt).mean(axis=0).sum() + M17.l1_pnl_x(cc.U, idx, -1, cfg, kt).mean(axis=0).sum())
            tot = acc[cell].sum(axis=1)
            assert abs(tot.mean() - exp) < 4.5 * tot.std() / math.sqrt(len(tot)), (cell, tot.mean(), exp, tot.std())
            assert (acc[cell][:, :first_fill] == 0).all(), "no P&L before the first fill"
        again = bb_null(W, L, 400, 0)
        assert all((again[c] == acc[c]).all() for c in CELLS) and not (bb_null(W, L, 400, 1)["P"] == acc["P"]).all() and not (acc["P"] == acc["R"]).all()
        for q, cell in enumerate(CELLS):
            rng = np.random.default_rng([SEED, q, 0])
            draws = [(rec, D15.draw_order(rng, 400, rec.cell[cell].n, 2 * rec.cell[cell].k)) for rec in L.recs if rec.cell[cell].traded]
            for d in (0, 1, 399):
                x0 = np.zeros(W.T)
                for rec, o in draws:
                    cc = rec.cell[cell]
                    cols = rec.pool[cc.idx]
                    names = o[d]
                    assert len(set(names.tolist())) == 2 * cc.k and not set(names[:cc.k].tolist()) & set(names[cc.k:].tolist())
                    for sd, sel in ((1, names[:cc.k]), (-1, names[cc.k:])):
                        for i in sel:
                            x0[rec.f:rec.x + 1] += slot * np.array(brute_rec(W, rec, cc.idx[i], int(cols[i]), sd))
                assert close(acc[cell][d], x0), (cell, d)
    ix = pd.bdate_range("2016-07-01", "2025-06-27")
    rng = np.random.default_rng(2)
    S12 = M12.Stretch(rng.normal(35.0, 650.0, len(ix)), ix, None, WF0, PRE_END)
    pc = {c: D15.null_cell(S12, rng.normal(5, 100, (40, len(ix))), np.arange(len(ix)), len(ix))[0] for c in CELLS}
    pdo = {c: rng.normal(0.0, 0.2, 40) for c in CELLS}
    ns = null_summary(pc, pdo)
    mx, mdo = np.max(np.vstack([pc[c] for c in CELLS]), axis=0), np.max(np.vstack([pdo[c] for c in CELLS]), axis=0)
    assert ns["draws"] == 40 and ns["seed"] == SEED and set(ns["by_cell"]) == set(CELLS) and all(abs(ns["roc_max"][k] - np.percentile(mx, v)) < 1e-9 and abs(ns["do_ref_max"][k] - np.percentile(mdo, v)) < 1e-9 for k, v in (("p5", 5), ("p50", 50), ("p95", 95)))


def t_twins():
    """the REPORTED twins on the toy: the FLAT twin's names = R's scored names whose NETISS one-year ISS (N12's own score) is within the band (a wide band here: the toy's share counts are rarely flat), the thirds; the dividend-only twin = P's
    scored names sorted by DIV / MV; the REP / MV deciles on R's names, never traded; the decile baskets' daily P&L recounted by plain python; the pick overlap"""
    with spec(**TOY_SPEC), D15.spec(univ=14):
        tt = bb_ready()
        W = tt.W
        band = (math.log(0.5), math.log(2.0))
        with patched(THIS, FLAT_LO=band[0], FLAT_HI=band[1]):
            L = bb_build(W, W.days[0], W.days[-1])
        n_flat = 0
        for rec in L.recs:
            cc = rec.cell
            iss1 = NI.score_rank(W, rec.r)["N12"].iss
            cols = rec.pool
            want = [int(j) for j in cols[cc["R"].idx] if np.isfinite(iss1[j]) and band[0] <= iss1[j] <= band[1]]
            assert cols[cc["FLAT"].idx].tolist() == want and (cc["FLAT"].k, cc["FLAT"].mode) == flat_n(len(want)) and close(cc["FLAT"].score, rec.sc.score["R"][want])
            assert cc["DIV"].idx.tolist() == cc["P"].idx.tolist() and close(cc["DIV"].score, rec.sc.score["DIV"][cols[cc["P"].idx]]) and (cc["DIV"].k, cc["DIV"].mode) == (cc["P"].k, cc["P"].mode)
            assert cc[DECK].idx.tolist() == cc["R"].idx.tolist() and not cc[DECK].traded and (cc[DECK].dec is None) == (cc[DECK].n < SPEC["dec_min"])
            n_flat += cc["FLAT"].traded
        assert n_flat >= 2 and any(rec.cell[DECK].dec is not None for rec in L.recs)
        x, sp, nn, nr = NI.decile_series(W, L, DECK)
        slot, esr = M17.SPEC["slot"], np.nan_to_num(np.asarray(W.es.ret, float))
        x0, sp0 = np.zeros_like(x), np.zeros_like(sp)
        for rec in L.recs:
            cc = rec.cell[DECK]
            if cc.dec is None:
                continue
            cols = rec.pool[cc.idx]
            for i, d in enumerate(cc.dec.tolist()):
                p_ = slot * np.array(brute_rec(W, rec, cc.idx[i], int(cols[i]), 1))
                x0[d, rec.f:rec.x + 1] += p_
                sp0[d, rec.f:rec.x + 1] += p_ - slot * esr[rec.f:rec.x + 1]
        assert close(x, x0) and close(sp, sp0) and nr == sum(rec.cell[DECK].dec is not None for rec in L.recs), "the REP / MV deciles: equal-weight long-only baskets, recounted"
        ov = overlap(L, "DIV", "P")
        want = defaultdict(list)
        for rec in L.recs:
            a_, b_ = rec.cell["DIV"], rec.cell["P"]
            if a_.traded and b_.traded:
                want["long"].append(len(set(rec.pool[a_.idx[a_.long]].tolist()) & set(rec.pool[b_.idx[b_.long]].tolist())) / a_.k)
        assert ov["rebalances"] == len(want["long"]) > 0 and close(ov["long"], float(np.mean(want["long"])))


def t_judge():
    """(a) - (e) per cell: (d) needs TWO THIRDS, rounded up, of the July-June years the cell holds positions in (9 -> 6, 8 -> 6, 7 -> 5); every check fails on its own; a NaN fails; the candidate is the higher ROC (a tie: P); Stage A's bookkeeping"""
    assert [-(-2 * n // 3) for n in (9, 8, 7, 6, 3, 2, 1)] == [6, 6, 5, 4, 2, 2, 1]
    base = {"n_units": 100, "roc": 20.0, "net": 1000.0, "years_pos": 6, "net_ex2020": 10.0, "net_ex_best_days": 5.0, "net_ex_best_pos": 5.0}
    nul = {"roc_max": {"p95": 18.0}}
    ok = judge_cell(base, 50.0, nul, 9)
    assert all(ok.values()) and len(ok) == 9 and "positive in >=6 of 9 July-June years" in ok and judge_cell(base, 50.0, nul, 8)["positive in >=6 of 8 July-June years"]
    assert not judge_cell({**base, "years_pos": 4}, 50.0, nul, 7)["positive in >=5 of 7 July-June years"] and judge_cell({**base, "years_pos": 5}, 50.0, nul, 7)["positive in >=5 of 7 July-June years"]
    for k, v, key in (("n_units", 59, "rebalances>=60"), ("roc", 14.99, "ROC>=15"), ("net", -1.0, "net>0 at 5 bps"), ("roc", 17.0, "ROC>null p95"), ("net_ex2020", -1.0, "net>0 without Feb 15 - Apr 30 2020"),
                      ("net_ex_best_days", 0.0, "profitable without its best 1% of days"), ("net_ex_best_pos", -2.0, "profitable without its best 1% of name-months"), ("roc", float("nan"), "ROC>=15")):
        chk = judge_cell({**base, k: v}, 50.0, nul, 9)
        assert not chk[key] and sum(not x for x in chk.values()) >= 1, (k, v, key)
    assert not judge_cell(base, -1.0, nul, 9)["net>0 at 10 bps"]
    cells = {"P": {"base": {"roc": 30.0}, "PASS": True}, "R": {"base": {"roc": 30.0}, "PASS": True}}
    assert stage_a_flow(cells) == (["P", "R"], "P"), "a tie: P"
    cells["R"]["base"]["roc"] = 31.0
    assert stage_a_flow(cells) == (["P", "R"], "R") and pick_candidate(cells, []) is None
    cells["R"]["PASS"] = False
    assert stage_a_flow(cells) == (["P"], "P")


def t_reference():
    """A2 over the REFERENCE (the restated L, a synthetic stand-in here): c by the registered volatility rule over the cell's first 24 months of traded fills (its first traded fill .. + 24 months - 1 day; never before the WF's start), 0.5c and
    2c, the plain #463 + c x cell row, the dollars a year and DD5 beside every ROC - recounted; an incremental pass needs ROC and Sortino both above L's; no spread over the window -> no c, never an exception"""
    B, _S12 = M17.synth_book(seed=3, hi="2026-06-30")
    k = np.flatnonzero(B.mask(WF0, PRE_END))
    ref = DV.mk_ref(B)
    assert a2_window(TS("2017-01-03")) == (TS("2017-01-03"), TS("2019-01-02")) and a2_window(TS("2016-06-01")) == (WF0, TS("2018-06-30")) and a2_window(None) == (WF0, TS("2018-06-30")) and a2_window(TS("2017-03-01 00:00")) == (TS("2017-03-01"), TS("2019-02-28"))
    rng = np.random.default_rng(8)
    for d0 in ("2017-01-03", "2018-03-01"):
        win = a2_window(TS(d0))
        mw = B.mask(*win)
        for lab, xB in (("profitable and quiet", 40.0 + rng.normal(0.0, 50.0, B.n)), ("losing", -30.0 + rng.normal(0.0, 300.0, B.n))):
            a2 = a2_report(B, xB, ref, win)
            sb, sc = float(np.std(B.raw[mw], ddof=1)), float(np.std(xB[mw], ddof=1))
            c_ = 0.25 * sb / sc
            assert a2["window"] == [f"{win[0]:%Y-%m-%d}", f"{win[1]:%Y-%m-%d}"] and a2["rows"] == int(mw.sum()) and abs(a2["c"] - c_) <= 1e-9 * c_, (d0, lab)
            yrs = float(ref.stats["years"])
            dd_eq = lambda a_, b_: abs(a_["dd5"] - b_["dd5"]) < 1e-6 and abs(a_["max_dd"] - b_["max_dd"]) < 1e-6 and a_["n"] == b_["n"] and a_["one_episode"] == b_["one_episode"]
            for got, mult in ((a2, 1.0), (a2["at_half_c"], 0.5), (a2["at_double_c"], 2.0)):
                w_ = DV.plain_stats((ref.raw + mult * c_ * xB)[k], B.index[k])
                assert abs(got["roc"] - w_["roc"]) < 1e-5 and abs(got["usd_year"] - w_["net"] / yrs) < 1e-6 and dd_eq(got["dd5"], dd5_rec(B, ref.raw + mult * c_ * xB)), (d0, lab, mult)
            assert dd_eq(a2["reference"]["dd5"], dd5_rec(B, ref.raw)) and dd_eq(a2["plain_463"]["dd5"], dd5_rec(B, B.raw + c_ * xB)) and abs(a2["plain_463"]["usd_year"] - DV.plain_stats((B.raw + c_ * xB)[k], B.index[k])["net"] / yrs) < 1e-6
            assert a2["incremental_pass"] is bool(a2["roc"] > a2["reference"]["roc"] and a2["sortino"] > a2["reference"]["sortino"]) and (a2["incremental_pass"] if lab.startswith("profitable") else not a2["incremental_pass"])
            assert plain_a2(B, xB, win)["c"] == a2["c"]
        ax = a2_report(B, np.zeros(B.n), ref, win)
        assert ax["incremental_pass"] is False and "error" in ax and ax["at_half_c"] is None


def brute_group_key(W, b, j):
    """plain python: the audit group of a name-rank from brute_score's record - the symbol and the accession numbers of the statement, the REP / DIV concept used, every ISSUANCE item on each period of the TTM and of the share count S"""
    if not b.has_ttm or b.share is None:
        return ""
    acc = set()
    for p in b.periods:
        g_ = lambda c, p=p: b.use.get((b.cik, c, p[0], p[1]))
        st = g_(C_ST[0]) or g_(C_ST[1])
        acc.add(st[3])
        for cons in (C_REP, C_DIV):
            e = next((g_(c) for c in cons if g_(c) is not None), None)
            if e:
                acc.add(e[3])
        prim = next((g_(c) for c in C_ISS if g_(c) is not None), None)
        for it in ([prim] if prim else []) + [g_(c) for c in C_PLAN if g_(c) is not None]:
            acc.add(it[3])
    a, _v, con = b.share
    f = W.sh_frame
    sub = f[(f["cik"] == b.cik) & (f["concept"] == con) & (f["end"] == a)]
    acc.add(sorted(sub[sub["filed"] == sub["filed"].min()]["accn"].tolist())[0])
    return f"{W.syms[j]}|" + "+".join(sorted(acc))


def t_rows():
    """the hand audit's rows: the candidates (the largest gains, their component facts with the filings [B4], the market value's inputs) and every |score| > 0.15 name-rank with whether the registered leg PICKED it; the GROUP of every name-rank
    recounted by plain python (the symbol + the accession numbers of every fact behind the score); the audit file read and checked; a data_event row removes its name-month AND every other name-month of its group, from both cells and the
    nulls; the bookkeeping of what is audited"""
    with spec(**TOY_SPEC), D15.spec(univ=14):
        tt = bb_ready()
        W = tt.W
        W.sh_frame = tt.frame
        L = bb_build(W, W.days[0], W.days[-1])
        ranks = built_ranks(W, W.days[0], W.days[-1])
        cache = {}
        for r, f, _x in ranks:                                                              # every name-rank's group against the recount
            for j in range(W.S):
                b = brute_score(W, tt.ent, tt.frame, tt.cal, j, r, cache)
                assert group_key(W, r, j) == brute_group_key(W, b, j), (str(W.syms[j]), f"{W.days[r]:%Y-%m-%d}", group_key(W, r, j), brute_group_key(W, b, j))
        run = M17.run_cell(W, cell_leg(L, "P"), D15.l1_cfg(), pos=True)
        rows = bb_candidate_rows(W, L, "P", run, None, {}, 8)
        assert len(rows) == 8 and all(rows[i]["pnl"] >= rows[i + 1]["pnl"] for i in range(7)) and abs(rows[0]["pnl"] - float(np.max(run.pos.pnl))) < 1e-9
        for row in rows:
            assert {"symbol", "date", "exit", "side", "pnl", "rank_date", "cik", "ttm", "statement_end", "rep_ttm", "div_ttm", "iss_ttm", "mv", "shares", "shares_accn", "F_asof", "F_rank", "facts", "group", "score_P", "zero_rule"} <= set(row) and "raw_move_formation" not in row
            assert row["group"].startswith(row["symbol"] + "|") and all(a_ in row["facts"] for a_ in row["group"].split("|", 1)[1].split("+") if a_ != row["shares_accn"]) and "STATEMENT" in row["facts"], row["facts"]
        fl = flag15_rows(W, ranks, L)
        pk = picks_by_name_month(L)
        n_fl = sum(int(score_rank(W, r).flag[c][np.flatnonzero(W.U[f])].sum()) for r, f, _x in ranks for c in CELLS)
        assert len(fl) == n_fl > 0 and all(abs(x["score"]) > FLAG for x in fl) and all(x["picked"] == ", ".join(pk.get((W.days.get_loc(TS(x["date"])), list(W.syms).index(x["symbol"])), [])) for x in fl)
        assert any(x["picked"] for x in fl), "some flagged name-ranks are picked in the toy"
        # the audit file
        root = tempfile.mkdtemp(prefix="buyback_selftest_")
        try:
            ap = os.path.join(root, "buyback_audit.csv")
            assert read_audit(ap) is None
            top = rows[0]
            j0, f0 = list(W.syms).index(top["symbol"]), W.days.get_loc(TS(top["date"]))
            open(ap, "w").write(f"symbol,date,cell,verdict,note\n{top['symbol']},{top['date']},p,DATA_EVENT,x\nN01,{W.days[280]:%Y-%m-%d},R,keep,fine\n")
            au = read_audit(ap)
            assert au["verdict"].tolist() == ["data_event", "keep"] and au["cell"].tolist() == ["P", "R"]
            cnt = apply_audit(W, au)
            mem = [f_ for r_, f_ in fill_ranks(W) if group_key(W, r_, j0) == top["group"]]
            assert f0 in mem and cnt["data_event"] == 1 and cnt["group_name_months"] == len(set(mem) - {f0}) and all(W.aud1[f_, j0] for f_ in mem) and int(W.aud1.sum()) == len(mem), (mem, cnt)
            L1 = bb_build(W, W.days[0], W.days[-1])
            assert all(j0 not in rec.pool.tolist() for rec in L1.recs if rec.f in mem), "the name-month and its group are out of the pool: both cells, the twins and the nulls"
            st = audit_status(W, {"P": rows, "R": []}, fl, au)
            assert st["P"]["listed"] == 8 and st["P"]["audited"] >= 1 and st["R"]["listed"] == 0 and not st["R"]["audit_complete"]
            for bad in (f"N08,{W.days[270]:%Y-%m-%d},P,maybe,x\n", "N08,not-a-date,P,keep,x\n", f"N08,{W.days[270]:%Y-%m-%d},N12,keep,x\n", f",{W.days[270]:%Y-%m-%d},P,keep,x\n"):
                open(ap, "w").write("symbol,date,cell,verdict,note\n" + bad)
                refused(lambda: read_audit(ap), "line(s) [2]")
            open(ap, "w").write("symbol,date\nN08,2024-01-01\n")
            refused(lambda: read_audit(ap), "lacks the column")
            open(ap, "w").write(f"symbol,date,cell,verdict,note\nZZZ,{W.days[270]:%Y-%m-%d},P,data_event,x\n")
            refused(lambda: apply_audit(W, read_audit(ap)), "match no session or no name")
            assert apply_audit(W, None)["rows"] == 0 and not W.aud1.any()
            hand = [{"cell": "P", "symbol": "N08", "date": "2025-03-03", "picked": "P/long", "group": "N08|a+b"}, {"cell": "P", "symbol": "N08", "date": "2025-04-01", "picked": "", "group": "N08|a+b"},
                    {"cell": "P", "symbol": "N05", "date": "2025-03-03", "picked": "P/short", "group": "N05|c"}, {"cell": "R", "symbol": "N05", "date": "2025-03-03", "picked": "", "group": "N05|c"}]
            au2 = pd.DataFrame({"symbol": ["N08"], "date": pd.to_datetime(["2025-04-01"]), "cell": ["P"], "verdict": ["keep"]})
            st2 = audit_status(W, {"P": [{"symbol": "N08", "date": "2025-04-01", "group": "N08|a+b"}], "R": []}, hand, au2)
            assert st2["P"] == {"listed": 1, "audited": 1, "audit_complete": True, "groups": 1, "flagged": 3, "flagged_picked": 2, "flag_listed": 2, "flag_audited": 1, "flag_complete": False}, st2["P"]
            assert st2["R"] == {"listed": 0, "audited": 0, "audit_complete": False, "groups": 0, "flagged": 1, "flagged_picked": 0, "flag_listed": 0, "flag_audited": 0, "flag_complete": True}, st2["R"]
        finally:
            shutil.rmtree(root, ignore_errors=True)
        W.aud1[:] = False


def dryload_text_checks(txt):
    """a dryload's printout is COUNTS: no cash amount, share count, score value, price, return, P&L or statistic (nothing like a dollar amount, ROC, Sortino, a drawdown, a signed decimal number - the shape every score is printed in), no date on / after
    the cut but the one line that names the cut, and the count lines it promises"""
    body = "\n".join(l for l in txt.splitlines() if "BEFORE ANY P&L" not in l)
    outcome = re.search(r"[$]\s*-?\d|ROC|Sortino|P&L|net [$]|drawdown|Stage A \(|[+-]\d+\.\d{2,}\b|per fill year \(scored names pooled", body)
    assert not outcome, ("the dryload printed an outcome", body[max(outcome.start() - 80, 0):outcome.end() + 80])
    dates = [d for l in txt.splitlines() if "cut to dates <" not in l for d in re.findall(r"\b20\d\d-\d\d-\d\d\b", l)]
    assert dates and all(d < "2025-06-30" for d in dates), [d for d in dates if d >= "2025-06-30"][:5]
    for frag in ("universe size per session by year", "[B6] / [B7] the two pinned cash-flow extracts", "the concepts as read", "entries (cik, concept, start, end", "periods (cik, start, end)", "[A1] / [A8] pinned files", "BEFORE ANY P&L", "names lost to each no-score rule",
                 "no score at |score| > 0.50", "the TTMs built per fill year", "concept used, REPURCHASES", "concept used, ISSUANCE [B7]", "STALENESS", "[B2] the share of SCORED names", "[B17] STALE S", "[B3] THE TAG BLIND SPOT", "[A13] ONE SHARE CLASS PER FIRM",
                 "scored names per rebalance", LAB_J, LAB_A, "TBIS flags:", "ES prints on the", "cache manifest sha256", "prereg check:", "rebalances:", "names with a full window", "the fallback rule"):
        assert frag in txt, frag
    assert "[D2]" not in txt, "[B13]: the spin-off / stock-dividend ex-dates are never labelled [D2] here (the share counts' label)"


def t_report():
    """BEFORE ANY P&L on the toy, recounted name by name by plain python: per rank the universe, the names with a TTM (FY / year-to-date), per score the scored names and the first reason of every other one, the flags, the |score| > 0.50 names, [B2]'s
    120-day count, the staleness buckets, the components' concepts and ZERO periods, [B3]'s names; [B3]'s per-year shares and its gate (above 10% -> Stage A refuses until MANAGER's ruling, at 10% it does not); [B9]'s zero-rule share of the picks;
    the counts-only prints carry no outcome"""
    with spec(**TOY_SPEC), D15.spec(univ=14):
        tt = bb_ready()
        W = tt.W
        ranks = built_ranks(W, W.days[0], W.days[-1])
        srows = score_report(W, ranks, values=True)
        cache = {}
        for (r, f, _x), rec in zip(ranks, srows):
            uni = np.flatnonzero(W.U[f])
            bs = {int(j): brute_score(W, tt.ent, tt.frame, tt.cal, int(j), r, cache) for j in uni}
            ht = [j for j, b in bs.items() if b.has_ttm]
            assert rec["universe"] == len(uni) and rec["ttm"] == len(ht) and rec["ttm_fy"] == sum(bs[j].kind == 1 for j in ht) and rec["ttm_ytd"] == sum(bs[j].kind == 2 for j in ht)
            dd = [int(W.ni.days_i[r]) - bs[j].e for j in ht]
            assert rec["stale_buckets"] == [sum(d <= 60 for d in dd), sum(60 < d <= 120 for d in dd), sum(120 < d <= 200 for d in dd), sum(d > 200 for d in dd)]
            assert sorted(rec["blind_names"]) == sorted(str(W.syms[j]) for j in ht if all(bs[j].zero_all))
            for k in CODE_KEYS:
                c = rec["cells"][k]
                want = Counter(REASONS[b.code[k]] for b in bs.values())
                assert c["scored"] == want.get("scored", 0) and all(c["reasons"][q] == want.get(q, 0) for q in REASONS[1:R_SECOND_CLASS]) and c["scored"] + sum(c["reasons"].values()) == rec["universe"], (rec["rank"], k)
                assert c["flags"] == sum(b.flag[k] for b in bs.values()) and sorted(c["over50_names"]) == sorted(str(W.syms[j]) for j, b in bs.items() if b.code[k] == R_OVER50)
                assert c["stale120"] == sum(b.code[k] == R_SCORED and int(W.ni.days_i[r]) - b.e > STALE_PRINT for b in bs.values()) and c["positive"] == sum(b.code[k] == R_SCORED and b.score[k] > 0 for b in bs.values())
                if k in CELLS:
                    assert close(np.sort(c["values"]), np.sort([b.score[k] for b in bs.values() if b.code[k] == R_SCORED]))
            assert rec["comp"]["rep"]["first"] + rec["comp"]["rep"]["fallback"] + rec["comp"]["rep"]["mixed"] + rec["comp"]["rep"]["zero_all"] == rec["ttm"]
        assert sum(r_["cells"]["P"]["scored"] for r_ in srows) > 50 and any(r_["cells"]["P"]["over50_names"] for r_ in srows) and sum(r_["comp"]["iss"]["dedup"] for r_ in srows) > 0 and sum(r_["comp"]["rep"]["mixed"] for r_ in srows) > 0
        # [B3]: the shares per year and the gate
        hand = [{"year": 2020, "ttm": 100, "blind_names": ["A"] * 6 + ["B"] * 5}, {"year": 2020, "ttm": 10, "blind_names": []}, {"year": 2021, "ttm": 50, "blind_names": ["C"] * 5}]
        b3 = blind_spot(hand)
        assert b3[2020] == {"name_ranks_with_a_ttm": 110, "blind_name_ranks": 11, "share": 0.1, "above": False, "names": {"A": 6, "B": 5}} and b3[2021]["above"] is False, "exactly 10% is not above"
        b3 = blind_spot(hand + [{"year": 2021, "ttm": 0, "blind_names": ["D"]}])
        assert b3[2021]["above"] is True and abs(b3[2021]["share"] - 6 / 50) < 1e-12
        refused(lambda: b3_gate(b3), "[B3]", "2021", "MANAGER's ruling")
        assert b3_gate(blind_spot(hand)) == [] and blind_spot(srows) and all(not d["above"] for d in blind_spot(srows).values())
        with patched(THIS, B3_RULING="dated addendum"):
            assert b3_gate(b3) == [2021], "a registered ruling lets Stage A go on (it says what the rule becomes)"
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            print_blind_spot(b3)
        assert "ABOVE 10%" in buf.getvalue() and "D x1" in buf.getvalue() and "C x5" in buf.getvalue()
        # [B9]: the picked names whose REP or ISS came from the zero rule on some period
        L = bb_build(W, W.days[0], W.days[-1])
        b9 = b9_rows(W, L)
        for rec, e in zip(L.recs, b9):
            for c in CELLS:
                cc = rec.cell[c]
                if not cc.traded:
                    assert e["cells"][c] is None
                    continue
                cols = rec.pool[cc.idx[np.r_[cc.long, cc.short]]]
                z = [brute_score(W, tt.ent, tt.frame, tt.cal, int(j), rec.r, cache).zero for j in cols]
                assert e["cells"][c] == {"picked": len(cols), "zero": sum(a_ or b_ for a_, b_ in z), "zero_rep": sum(a_ for a_, _b in z), "zero_iss": sum(b_ for _a, b_ in z)}, (e["rank"], c)
        assert sum(e["cells"]["P"]["zero"] for e in b9 if e["cells"]["P"]) > 0
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            print_b9(b9)
            print_score_report(score_report(W, ranks, values=False), names=False)
        txt = buf.getvalue()
        assert "[B9] BEFORE ANY RETURN" in txt and not re.search(r"[$]\s*-?\d|ROC|Sortino|net [$]|drawdown|[+-]\d+\.\d{2,}\b", "\n".join(l for l in txt.splitlines() if "BEFORE ANY" not in l)), "the counts-only prints carry no outcome"
        assert "LISTED" not in txt and "counted:" in txt


def t_integration():
    """evaluate / reports / the NETISS question / candidate rows on the toy world, a synthetic #463 and a synthetic reference (no files), the stretch moved onto the toy's own days so the cells trade inside it: [B9] is handed the leg right after
    the picks and the power line the null BEFORE any cell is costed; every statistic is the independent sum of the recount's paths; the cost curve and the sides add up; A2 is incremental over the reference on the cell's own window (its first
    traded fill + 24 months); the twins, the deciles, the hedged twin, the beta rule, #70's gate basis and the diagnostics carry every row; NETISS's cells run in-process; everything is JSON-serialisable and prints"""
    wf = (TS("2024-01-02"), TS("2026-06-30"))
    B, _s = M17.synth_book(seed=15, lo="2024-01-01", hi="2026-06-30", deep=False)
    ref_at0 = DV.ref_at
    ref_at_toy = lambda B_, ref_, xB_, c_, lo=wf[0], hi=wf[1]: ref_at0(B_, ref_, xB_, c_, lo, hi)
    with spec(**TOY_SPEC), D15.spec(univ=14), patched(THIS, WF0=wf[0], PRE_END=wf[1]), patched(NI, WF0=wf[0], PRE_END=wf[1]), patched(D15, WF0=wf[0], PRE_END=wf[1]), patched(DV, WF0=wf[0], PRE_END=wf[1], ref_at=ref_at_toy):
        S12 = M12.Stretch(B.raw, B.index, None, wf[0], wf[1])
        ref = DV.mk_ref(B)
        tt = bb_ready()
        W = tt.W
        rows = A13.book_rows(B, W)
        order, real_run = [], M17.run_cell

        def run_spy(*a, **k):
            order.append("run")
            return real_run(*a, **k)
        with patched(M17, run_cell=run_spy):
            res, obj = evaluate(W, B, S12, ref, rows, JUDGED, 40, 0, full=True, announce=lambda nul, L: order.append("power"), b9=lambda L: order.append("b9"))
        assert order[:2] == ["b9", "power"] and order[2] == "run" and order.count("power") == 1 and order.count("b9") == 1, "[B9] after the picks, the power line before any cell P&L"
        Bz = brute_bb(W, tt.ent, tt.frame, tt.cal, tt.cik_of, wf[0], wf[1], JUDGED)
        slot = M17.SPEC["slot"]
        for cell in CELLS + TWINS:
            c = res["cells"][cell] if cell in CELLS else res["twins"][cell]
            x0, n_pos = np.zeros(W.T), 0
            for b in Bz:
                bc = b["cell"][cell]
                for sd, js in ((1, bc["long"]), (-1, bc["short"])):
                    for j in js:
                        x0[b["f"]:b["x"] + 1] += slot * np.array(brute_pos(W, b, j, sd))
                        n_pos += 1
            assert abs(c["base"]["net"] - x0.sum()) < 1e-6 and c["base"]["n_pos"] == n_pos and abs(c["usd_year"] - c["base"]["net"] / c["base"]["years"]) < 1e-9, (cell, c["base"]["net"], x0.sum())
        for cell in CELLS:
            c = res["cells"][cell]
            assert c["cost0"]["net"] > c["base"]["net"] > c["stress"]["10 bps"]["net"] > c["stress"]["20 bps"]["net"] and abs(c["sides"]["long side only"]["net"] + c["sides"]["short side only"]["net"] - c["base"]["net"]) < 1e-6
            ff = first_fill(W, obj.legs, cell)
            assert c["first_traded_fill"] == f"{ff:%Y-%m-%d}" and c["A2"]["window"] == [f"{d:%Y-%m-%d}" for d in a2_window(ff)] and c["first_rank_with_a_score"] is not None
            assert set(c["checks"]) == set(judge_cell(c["base"], 1.0, res["null"], len(c["years_held"]))) and c["PASS"] is False and c["gate70"]["credited"] is c["beta"]["within_cap"] and c["dd5"] == dd5_rec(B, obj.series[cell][0])
            assert set(c["A2"]["reference"]) >= {"roc", "sortino", "net", "usd_year", "dd5"} and c["hedged"]["ratios"] == c["base"]["n_units"] and [q["decile"] for q in c["deciles"]["deciles"]] == list(range(1, 11))
        assert set(res["twins"]) == set(TWINS) | {DECK} and res["twins"]["FLAT"]["parent"] == "R" and res["twins"]["DIV"]["parent"] == "P" and [q["decile"] for q in res["twins"][DECK]["deciles"]] == list(range(1, 11))
        assert res["null"]["draws"] == 40 and res["null"]["seed"] == SEED and res["variant"] == JUDGED == "close"
        # [B13] [B10]'s removal reading beside the judged one: a report, no null; its removed name-months recounted from the pools; its cells the sum of the recount's 'keep' paths
        resA, objA = evaluate(W, B, S12, ref, rows, "keep", 0, 3, full=False)
        BzA = brute_bb(W, tt.ent, tt.frame, tt.cal, tt.cik_of, wf[0], wf[1], "keep")
        assert resA["null"] is None and resA["variant"] == "keep" and all("checks" not in resA["cells"][c] and "PASS" not in resA["cells"][c] for c in CELLS) and resA["twins"] == {}
        remA = b10_removed(objA.legs.cnt)
        cs_of = lambda r_: np.asarray(W.CSPL[r_.f + 1:r_.x + 1][:, r_.pool]).any(axis=0)                      # the judged pool's names with a calendar split inside the hold (the first reason of the two)
        want_cs, want_sp = sum(int(cs_of(r_).sum()) for r_ in obj.legs.recs), sum(int((r_.spin_hold & ~cs_of(r_)).sum()) for r_ in obj.legs.recs)
        assert remA == {"calendar_split": want_cs, "spin_off_or_stock_dividend": want_sp} and want_cs >= 1 and want_sp >= 1, (remA, want_cs, want_sp)
        assert [sorted(set(rj.pool.tolist()) - set(ra.pool.tolist())) for rj, ra in zip(obj.legs.recs, objA.legs.recs)] == [sorted(rj.pool[cs_of(rj) | rj.spin_hold].tolist()) for rj in obj.legs.recs], "'keep' = the judged pool less those names"
        for cell in CELLS:
            xA = np.zeros(W.T)
            for b in BzA:
                for sd, js in ((1, b["cell"][cell]["long"]), (-1, b["cell"][cell]["short"])):
                    for j in js:
                        xA[b["f"]:b["x"] + 1] += slot * np.array(brute_pos(W, b, j, sd))
            assert abs(resA["cells"][cell]["base"]["net"] - xA.sum()) < 1e-6, cell
        nq = netiss_question(W, B, rows, obj.legs, obj, ref)
        Ln = NI.ni_build(W, wf[0], wf[1], NI.JUDGED)
        for cell in CELLS:
            q = nq[cell]
            assert set(q["corr"]) == {"N12", "N24"} and all(0.0 <= v_ <= 1.0 for o in q["overlap"].values() for k_, v_ in o.items() if k_ not in ("rebalances", "by_rank") and np.isfinite(v_))
            o = q["overlap"]["N12"]
            want = [len(set(rec.pool[rec.cell[cell].idx[rec.cell[cell].long]].tolist()) & set(rn.pool[rn.cell["N12"].idx[rn.cell["N12"].long]].tolist())) / rec.cell[cell].k
                    for rec, rn in zip(obj.legs.recs, Ln.recs) if rec.cell[cell].traded and rn.cell["N12"].traded]
            assert o["rebalances"] == len(want) and (not want or close(o["long_in_long"], float(np.mean(want))))
        srows = score_report(W, built_ranks(W, wf[0], wf[1]), values=True)
        rep, cands = reports(W, B, S12, ref, rows, obj, res["cells"], None, {}, [])
        for key in ("beta_to_es", "episodes", "ref_episodes", "map_point", "corr_with_legs", "corr_with_res", "top20_gains", "months", "turnover", "survivorship", "dividend_flows", "manifest_sha256"):
            assert key in rep, key
        for cell in CELLS:
            assert abs(sum(rep["months"][cell].values()) - res["cells"][cell]["base"]["net"]) < 1e-6 and rep["turnover"][cell]["traded_rebalances"] == res["cells"][cell]["base"]["n_units"] and len(rep["ref_episodes"][cell]) == len(ref.S.qual)
        assert json.loads(json.dumps({"res": res, "rep": rep, "nq": nq, "b3": blind_spot(srows), "srows": [{k: v for k, v in r_.items() if k != "cells"} for r_ in srows]}, default=R11.js)) is not None
        ast = {c: {"listed": 5, "audited": 0, "audit_complete": False, "groups": 4, "flagged": 9, "flagged_picked": 6, "flag_listed": 3, "flag_audited": 1, "flag_complete": False} for c in CELLS}
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            print_power(res["null"])
            print_score_report(srows, names=True)
            print_cells(res, ast)
            print_twins(res)
            print_netiss_question(nq, res)
            print_deciles(res)
            print_reports(rep, res["cells"])
            print_diagnostics(res, rep, ref)
            print_counts("registered", obj.legs.cnt)
            print_counts("reported", objA.legs.cnt)
            print_b10_reading(resA, remA, obj.legs.cnt, res["cells"])
            print_spin_picks({"judged_reading": {c: NI.ni_spin_counts(obj.legs, c) for c in CELLS}, "b10_removal_reading": {c: NI.ni_spin_counts(objA.legs, c) for c in CELLS}})
            print_spin_counts("registered", obj.legs.cnt)
            print_scored("registered", obj.legs.cnt)
            print_scored_stats(LAB_J, obj.legs, W)
        txt = buf.getvalue()
        for frag in ("POWER LINE - printed before any cell's P&L", "seed 20261024", "BEFORE ANY P&L", "#70 gate basis", "DIAGNOSTICS", "COST CURVE", "BY JULY-JUNE YEAR", "THE TWO REGIME HALVES", "THE LONG AND SHORT SIDES APART", "A2 (a report)", "first 24 months of traded fills",
                     "TWINS - REPORTED", "ES-hedged twin", "DIVIDEND-ONLY twin", "[B8] P with the tax-withholding", "FLAT twin", "THE NETISS QUESTION", "daily P&L correlation with N12", "DECILES", "REPY (gross repurchase yield", "persistence", "dividends [R1]", "short leg [R2]",
                     "survivorship", "a year)", "DD5 $", "THE REFERENCE BOOK'S DRAWDOWN EPISODES", "the episodes the cell helps", "hand audit (f) 0/5 of the top-50 listed (4 groups), 1/3 of the picked |score| > 0.15 groups (6 picked of 9 flagged name-ranks)",
                     f"{LAB_A}, no null - it removed {remA['calendar_split']:,} pool name-months for a calendar split and {remA['spin_off_or_stock_dividend']:,} for a spin-off / stock-dividend ex-date inside the hold", "closed_spin",
                     "names with an in-hold event that STAY in the pool [B13]", "b10_removal_reading P picks (long / short) and the spin-off / stock-dividend ex-dates", "registered spin-off / stock-dividend ex-dates by fill year"):
            assert frag in txt, frag
        assert "[D2]" not in txt and "[A18]" not in txt and "[A22]" not in txt, "[B13]: this file's prints never label the ex-dates [D2] (the share counts here) nor with NETISS's addendum labels"


def t_stage_b_refusals():
    """every Stage B refusal that needs no data, none of which may write the read flag: the lead's go-flag FIRST, then no Stage A candidate (each broken piece), the flag already there, a changed spec / harness / pinned file / audit, a broken frozen size
    or window, and the lockbox year's facts not pinned (LB_CASHFLOW and r21_netiss.LB_FACTS: both are needed - the market value reads the share counts)"""
    root = tempfile.mkdtemp(prefix="buyback_selftest_")
    try:
        out = os.path.join(root, "out")
        os.makedirs(out)
        go, flag, sap, aud = os.path.join(out, GO_FLAG), os.path.join(out, READ_FLAG), os.path.join(out, "buyback_stageA.json"), os.path.join(out, "buyback_audit.csv")
        good = {"judged": True, "prereg_sha256_lf": PREREG_SHA, **stamp(), "audit_sha256": None, "candidate": {"cell": "R", "c": 0.8317, "window": ["2017-01-03", "2019-01-02"]}, "stageA": {"cells": {"R": {"PASS": True}}, "pass_cells": ["R"]}, "parity": {}}

        def must(frag, sa=None, **kw):
            with open(sap, "w") as f:
                json.dump(good if sa is None else sa, f)
            with quiet(), patched(THIS, OUT=out, **kw):
                refused(stage_b, frag)
            assert not os.path.exists(flag) or frag == "already read", "a refused Stage B must not burn the lockbox"
        with patched(THIS, OUT=out), quiet():
            refused(stage_b, GO_FLAG, "go-flag", TAIL)
        with open(sap, "w") as f:
            json.dump(good, f)
        with patched(THIS, OUT=out), quiet():
            refused(stage_b, "go-flag")
        with open(go, "w") as f:
            f.write("the lead's go-flag: hand audit done")
        os.remove(sap)
        with patched(THIS, OUT=out), quiet():
            refused(stage_b, "no Stage A candidate")
        mut = lambda f: (lambda d: (f(d), d)[1])(json.loads(json.dumps(good)))
        for sa in (mut(lambda d: d.update(judged=False)), mut(lambda d: d.update(candidate=None)), mut(lambda d: d["stageA"].update(pass_cells=["P"])), mut(lambda d: d["stageA"].update(pass_cells=[])), mut(lambda d: d.update(stageA=None))):
            must("no Stage A candidate", sa)
        open(flag, "w").write("x")
        must("already read", good)
        os.remove(flag)
        must("DIFFERS", good, PREREG_SHA="0" * 64)
        must("another pre-registration", mut(lambda d: d.update(prereg_sha256_lf="0" * 64)))
        for edit in (lambda d: d.update(harness_sha256="0" * 64), lambda d: d.update(r21_sha256="0" * 64), lambda d: d.update(r17_sha256="0" * 64), lambda d: d.update(early_close=d["early_close"][1:]), lambda d: d.update(cf_sha256="0" * 64),
                     lambda d: d.update(cf_alt_sha256="0" * 64), lambda d: d.update(facts_sha256="0" * 64), lambda d: d.update(map_sha256="0" * 64), lambda d: d.update(wide_ca_sha256="0" * 64), lambda d: [d.pop(k) for k in stamp()]):
            must("different harness version", mut(edit))
        must("not the file Stage A ran with", mut(lambda d: d.update(audit_sha256="0" * 64)))
        with open(aud, "w") as f:
            f.write("symbol,date,cell,verdict,note\n")
        sha = file_sha(aud)
        for badc in (0.0, -1.0, None, "abc", float("nan"), float("inf")):
            must("positive number", mut(lambda d, b=badc: d.update(audit_sha256=sha, candidate={**good["candidate"], "c": b})))
        must("not one of", mut(lambda d: d.update(audit_sha256=sha, candidate={**good["candidate"], "cell": "N12"}, stageA={"cells": {"N12": {"PASS": True}}, "pass_cells": ["N12"]})))
        for badw in (None, ["2019-01-02", "2017-01-03"], ["x", "y"], ["2017-01-03"]):
            must("window", mut(lambda d, w=badw: d.update(audit_sha256=sha, candidate={**good["candidate"], "window": w})))
        ok = mut(lambda d: d.update(audit_sha256=sha))
        must("the lockbox year's facts are not pinned", ok)
        must("the lockbox year's facts are not pinned", ok, LB_CASHFLOW={"cf": ("a", "b"), "cf_alt": ("c", "d")})
        with patched(NI, LB_FACTS={"facts": ("a", "b"), "facts_add": ("c", "d")}):
            must("the lockbox year's facts are not pinned", ok)
            must("the lockbox year's facts are not pinned", ok, LB_CASHFLOW={"cf": ("a", "b")})
        assert LB_CASHFLOW is None and NI.LB_FACTS is None and not os.path.exists(flag), "no refusal wrote the flag"
    finally:
        shutil.rmtree(root, ignore_errors=True)


def t_cut():
    """Stage A asks for data cut at 2025-06-30 and refuses a session on / after it (the loaders and the book are stubbed; nothing real is read); a changed pre-registration, a pinned file that refuses, the manifest, the book and the reference gates
    all refuse before any data is asked for; the cash table, its entries and the World hold nothing on / after the cut (a row filed on the cut's day or ending on it is dropped at read; load_sources asserts it again); Stage A is frozen once the
    lockbox was read"""
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
    no_wide = lambda *a, **k: (SimpleNamespace(div=None, split=None, info={}), {})
    ok_src = lambda cut: SimpleNamespace(mp=None, fx=None, xinfo={}, cinfo={}, cash=None)
    root = tempfile.mkdtemp(prefix="buyback_selftest_")
    out = os.path.join(root, "out")
    os.makedirs(out)

    def must(frag, **kw):
        seen.clear()
        with devnull(), patched(THIS, **kw):
            refused(stage_a, frag)
        assert not os.path.exists(os.path.join(out, "buyback_stageA.json")) and not os.path.exists(os.path.join(out, READ_FLAG)), "a refusal writes nothing"
        return dict(seen)
    try:
        with patched(S, Data=stub), patched(A13, load_463=lambda: (Bs, [])), patched(M17, wide_load=no_wide), patched(DV, ref_load=lambda B, check_facts=None: ref0), patched(THIS, book_checks=lambda B: okbk, manifest_sha=lambda: D15.MANIFEST_PREFIX + "0" * 56, OUT=out, load_sources=ok_src):
            assert "t" not in must("DIFFERS", PREREG_SHA="0" * 64)
            assert "t" not in must("cash-flow extract", load_sources=lambda cut: refuse("refused: the pinned cash-flow extract (cashflow_asfiled_wide.csv) [B6] x is not on file (nothing computed, lockbox NOT read)"))
            seen.clear()
            with devnull():
                refused(stage_a, "on/after the cut")
            assert seen["t"] == S.LB0 and seen["open5"] is False
            for mf, frag in ((lambda: None, "manifest is missing"), (lambda: "ffff" + "0" * 60, "not the registered photograph")):
                assert "t" not in must(frag, manifest_sha=mf)
            assert "t" not in must("do not reproduce", book_checks=lambda B: ({"roc": 1.0, "sortino": 1.0, "ref": [0, 0], "ok": False}, okbk[1], S12))
            with patched(DV, ref_load=lambda B, check_facts=None: refuse("refused: the RESMOM line file x is not the registered y (nothing computed, lockbox NOT read)")):
                assert "t" not in must("RESMOM line file")
            with open(os.path.join(out, READ_FLAG), "w") as f:
                f.write("x")
            refused(stage_a, "Stage A is frozen")
    finally:
        shutil.rmtree(root, ignore_errors=True)
    cut_checks(SimpleNamespace(days=pd.DatetimeIndex(["2025-06-26", "2025-06-27"])), None, S.LB0)
    refused(lambda: cut_checks(SimpleNamespace(days=pd.DatetimeIndex(["2025-06-27", "2025-06-30"])), None, S.LB0), "on/after the cut")
    # the sealed year in the cash extracts: dropped at read and counted, the table and the entries free of it
    root = tempfile.mkdtemp(prefix="buyback_selftest_")
    try:
        files = {"cf": os.path.join(root, "a.csv"), "cf_alt": os.path.join(root, "b.csv")}
        rows = (fy_rows("1", "2025-01-01", "2025-03-31", "2025-05-02", "10-Q", REP=1.0) + fy_rows("1", "2024-01-01", "2024-12-31", "2025-06-29", REP=2.0) + fy_rows("1", "2025-01-01", "2025-06-30", "2025-06-27", "10-Q", REP=3.0)
                + fy_rows("1", "2025-01-01", "2025-06-30", "2025-08-01", "10-Q", REP=4.0) + fy_rows("1", "2024-07-01", "2025-06-29", "2025-06-30", REP=5.0))
        shas = {"cf": write_cf(files["cf"], rows), "cf_alt": write_cf(files["cf_alt"], [])}
        with patched(THIS, FILES=files, FILE_SHA=shas):
            cf, info = load_cashflow(S.LB0)
            assert info["rows_filed_on_or_after_the_cut"] == 4 and info["rows_end_on_or_after_the_cut"] == 2 and cf.n == 4 and cf.filed.max() < dnum(S.LB0) and cf.end.max() < dnum(S.LB0), info
            assert sorted({dstr(d) for d in cf.filed}) == ["2025-05-02", "2025-06-29"], "filed the day before the cut stays; on / after it, or ending on it, goes"
            cash = build_cash(cf)
            assert cash.E_f1.max() < dnum(S.LB0) and cash.pend.max() < dnum(S.LB0)
            cf2, info2 = load_cashflow(S.END)
            assert cf2.n == 10 and info2["rows_filed_on_or_after_the_cut"] == 0, "Stage B's cut (2026-07-01) keeps the sealed year's rows of a lockbox extract"
    finally:
        shutil.rmtree(root, ignore_errors=True)


# ------------------------------------------------------------------ smoke: an offline end-to-end run on SYNTHETIC worlds (every number means nothing)
SMOKE_THETA = 1.5                                   # the planted effect: a daily drift of +theta x (the name's annual NET PAYOUT rate) / 252 - in the PLANTED world only; the NULL world has the same filings and no drift
SMOKE_SPEC = {"n_side": 15, "min_scored": 45, "min_side": 10, "flat_min": 3}          # the synthetic market has ~60 scored names a month: 15 a side (the thirds below 45, at least 10 a side); the FLAT twin's thirds from 3 a side
SMOKE_NOCASH = ("S30", NI.SMOKE_DUAL[1], "LOWP", "LOWV", "LOWA", "S04", "S05")        # no cash-flow filing of their own: S30 (the planted 'no cash-flow fact'), the second class of the dual pair (it reads the first's CIK), the names under the filters, the unmapped
SMOKE_MULT = {"SPL": [("2024-03-15", 2.0)], "RVS": [("2016-02-17", 0.2)], "S20": [("2023-03-15", 3.0)], "S18": [("2024-04-22", 0.25)], "S12": [("2021-03-15", 2.0)]}      # NETISS's synthetic share counts' splits and jump (r21_netiss.smoke_filings)
SMOKE_PAYOUT = {"S24": 0.06, "S28": 0.05, "S29": 0.05, "S13": 0.04, "S32": 0.18, "S21": -0.17}                     # planted payout rates: S32 the heavy repurchaser and S21 the heavy issuer (the |score| > 0.15 flags), the others repurchase (a REP fact to misfile)
SMOKE_RANK_MONTHS = ("2016-11", "2017-06", "2018-06", "2019-03", "2019-06", "2019-09", "2020-03", "2020-06", "2020-09", "2021-03", "2021-09", "2021-12", "2022-03", "2022-09", "2023-03", "2024-04", "2024-05", "2025-03")


def smoke_refusal(root):
    """r21_netiss's guards (r17_resmom's / r15's: a 'smoke' name, never an OUT / the cache / the repo / this harness / C:\\EdgeLog / the #463 records) + this harness's OUT"""
    why = NI.smoke_refusal(root)
    if why:
        return why
    real = lambda p: os.path.normcase(os.path.realpath(p))
    try:
        if os.path.commonpath([real(root), real(OUT)]) == real(root):
            return f"smoke refused: {root} is or holds BUYBACK OUT"
    except ValueError:
        pass
    return None


def smoke_payout(seed=61):
    """the synthetic payout world: per name a persistent annual NET PAYOUT rate in -10% .. +12% (+ a yearly noise of 1%; the planted names' rates fixed), a dividend rate (none for a third of the names), a stock-plan issuance rate; the second class of the dual pair
    is the same firm (the first's numbers)"""
    rng = np.random.default_rng(seed)
    names = NI.SMOKE_NAMES
    N = len(names)
    base = rng.uniform(-0.10, 0.12, N)
    for nm, b in SMOKE_PAYOUT.items():
        base[names.index(nm)] = b
    q = {k: {y: float(base[k] + rng.normal(0.0, 0.01)) for y in range(2012, 2028)} for k in range(N)}
    dv = np.where(rng.random(N) < 1.0 / 3.0, 0.0, rng.uniform(0.005, 0.03, N))
    pb = rng.uniform(0.002, 0.012, N)
    a, b = names.index(NI.SMOKE_DUAL[0]), names.index(NI.SMOKE_DUAL[1])
    q[b], dv[b], pb[b], base[b] = q[a], dv[a], pb[a], base[a]
    return SimpleNamespace(base=base, q=q, dv=dv, pb=pb)


def smoke_drift(days, sh, theta):
    """the planted drift of every name-session: +theta x (the name's net payout rate in that calendar year) / 252 (r21_netiss.smoke_env's hook: its share-count world `sh` is not read)"""
    pw = smoke_payout()
    yrs = np.asarray(pd.DatetimeIndex(days).year)
    tab = {y: np.array([pw.q[k][int(y)] for k in range(len(NI.SMOKE_NAMES))]) for y in sorted(set(yrs.tolist()))}
    return theta * np.vstack([tab[int(y)] for y in yrs]) / 252.0


def smoke_cash(W, sh, pw, seed=67):
    """the synthetic cash-flow filings of every name with a CIK (SMOKE_NOCASH has none): fiscal years ending in Dec / Mar / Jun / Sep, a 10-Q per year-to-date period (Q1 / H / 9M, filed 25 - 44 days after) and a 10-K per year (50 - 75 days after), each with the prior year's
    comparative; the cash = the year's net payout rate x the market value at the period's end (the PLANTED world's raw close x NETISS's synthetic share count) x the months: REP = max(rate - dividend + plan, 0), DIV, ISS = REP + DIV - rate (the stock plans);
    some names file the fallback concepts, the second primary and the stock-plan concepts, the withholding twin. The planted cases: S24 a x100 repurchase in its Q1 2020 10-Q (|score| > 0.50), S25 a fiscal-year change (a Jan - Jun 2021 transition 10-KT, then June
    years: [B1]), S26 10-K only (stale from August), S27 no filing after 2019 (stale), S28 the fallback repurchase concept + issuance from the second primary + options + a stock-plan total of the same value ([B7]), S29 a sign error in FY 2019's repurchases and smaller
    2020 ones (a negative TTM), S31 the statement alone (zero on every component: [B3]'s blind spot), S32 a 10-Q/A after every 10-Q (the first filed stands), S13 two accessions of one day with two repurchase values (ambiguous), S14 the withholding twin, S30 none at all
    -> rows (cik, concept, val, start, end, filed, accn, form)"""
    rng = np.random.default_rng(seed)
    names = NI.SMOKE_NAMES
    syms = [str(s) for s in W.syms]
    days = W.days
    Cl = np.asarray(W.Cl, float)
    rows = []
    for k, nm in enumerate(names):
        if nm in SMOKE_NOCASH:
            continue
        cik = NI.smoke_cik(nm)
        c = pd.Series(Cl[:, syms.index(nm)], index=days).ffill().bfill() if nm in syms else None
        c = c if c is not None and c.notna().any() else None

        def mv(e, k=k, nm=nm, c=c):
            px = 200.0 if c is None else float(c.iloc[max(int(days.searchsorted(e, side="right")) - 1, 0)])
            return px * math.exp(NI.log_shares(sh, k, e)) * math.prod(m for d_, m in SMOKE_MULT.get(nm, []) if TS(d_) <= TS(e))
        fye = 12 if nm in ("S24", "S25", "S26", "S27", "S28", "S29", "S13", "S32") else (12, 12, 3, 6, 9, 12)[k % 6]
        per = fiscal_periods(fye, 2013, 2026)
        if nm == "S25":
            per = fiscal_periods(12, 2013, 2020) + [(2021, "H", TS("2021-01-01"), TS("2021-06-30"), 6)] + fiscal_periods(6, 2022, 2026)
        if nm == "S26":
            per = [p for p in per if p[1] == "FY"]
        if nm == "S27":
            per = [p for p in per if p[3] <= TS("2019-12-31")]
        pset = {(p[2], p[3]) for p in per}
        g = CashGen(cik, rng)
        vals = {}

        def facts(s, e, m, form, k=k, nm=nm, vals=vals, mv=mv):
            if (s, e) not in vals:
                yq, X = pw.q[k][e.year], mv(e) * m / 12.0
                rep0 = max(yq - pw.dv[k] + pw.pb[k], 0.0) * X
                vals[(s, e)] = {"REP": rep0 * (1.0 + 0.02 * float(rng.normal())), "DIV": pw.dv[k] * X, "ISS": max(rep0 + pw.dv[k] * X - yq * X, 0.0), "TW": 0.25 * pw.pb[k] * X}
            v = dict(vals[(s, e)])
            if nm == "S24" and s == TS("2020-01-01") and e == TS("2020-03-31"):
                v["REP"] *= 100.0
            if nm == "S29" and e == TS("2019-12-31") and m == 12:
                v["REP"] = -v["REP"]
            if nm == "S29" and e.year == 2020:
                v["REP"] *= 0.3
            out = [(C_ST[0] if k % 9 else C_ST[1], s, e, -(v["REP"] + v["DIV"] - v["ISS"]) - 1e6)]
            if nm == "S31":
                return out
            if v["REP"] != 0.0:
                rc = C_REP[1] if (nm == "S28" or k % 7 == 3 or (k % 13 == 6 and form != "10-K")) else C_REP[0]
                out.append((rc, s, e, v["REP"]))
            if v["DIV"] > 0:
                out.append((C_DIV[1] if k % 11 == 5 else C_DIV[0], s, e, v["DIV"]))
            if nm == "S28":
                out += [(C_ISS[1], s, e, 0.6 * v["ISS"]), (C_PLAN[0], s, e, 0.4 * v["ISS"])] + ([(C_PLAN[3], s, e, 0.4 * v["ISS"])] if form != "10-K" else [])
            elif v["ISS"] > 0:
                if nm == "S33" and e.year <= 2016:
                    out.append((C_ISS[2], s, e, v["ISS"]))                                              # S33's IPO proceeds (it starts trading in 2016)
                elif nm == "S34":
                    out.append((C_PLAN[2], s, e, v["ISS"]))                                             # S34 files its issuance under a stock-plan concept alone
                elif k % 5 == 2:
                    out += [(C_ISS[1], s, e, 0.7 * v["ISS"]), (C_PLAN[1] if k % 10 == 7 else C_PLAN[0], s, e, 0.3 * v["ISS"])]
                else:
                    out.append((C_ISS[0], s, e, v["ISS"]))
            if nm == "S14" or k % 4 == 1:
                out.append((C_TW[0], s, e, v["TW"]))
            return out
        for (_Y, t, s, e, m) in per:
            tenk = t == "FY" or (nm == "S25" and s == TS("2021-01-01"))
            form = ("10-KT" if t != "FY" else "10-K") if tenk else "10-Q"
            filed = e + pd.Timedelta(days=int(rng.integers(50, 76)) if tenk else int(rng.integers(25, 45)))
            fl = facts(s, e, m, form)
            ps, pe = s - pd.DateOffset(years=1), month_end(e - pd.DateOffset(years=1))
            if (ps, pe) in pset:
                fl += facts(ps, pe, m, form)
            g.filing(filed, form, fl)
            if nm == "S32" and form == "10-Q":
                g.filing(filed + pd.Timedelta(days=20), "10-Q/A", [(c_, s_, e_, v_ * 1.3) for c_, s_, e_, v_ in fl])
            if nm == "S13" and s == TS("2019-01-01") and e == TS("2019-03-31"):
                g.filing(filed, "10-Q", [(c_, s_, e_, v_ * 1.1) for c_, s_, e_, v_ in fl if c_ in C_REP and s_ == s], accn=f"{cik}-AMBIG-0001")
        rows += g.rows
    return rows


def smoke_cash_files(root, rows, tag=""):
    """the two pinned extracts as TV lays them out (the concepts split by FILE_CONCEPTS), cut at filed 2025-06-30, and the sealed-year-extended twins Stage B would pin (filed before 2026-07-01) -> namespace (files, shas, full_files, full_shas, rows_cut)"""
    d = os.path.join(root, "xbrl")
    os.makedirs(d, exist_ok=True)
    cut, end = f"{S.LB0:%Y-%m-%d}", f"{S.END:%Y-%m-%d}"
    of = lambda key, rs: [r for r in rs if r[1] in FILE_CONCEPTS[key]]
    before = lambda rs, day: [r for r in rs if r[5] < day]
    files = {k: os.path.join(d, f"{tag}{os.path.basename(FILES[k])}") for k in CF_KEYS}
    full = {k: os.path.join(d, f"{tag}{os.path.basename(FILES[k])[:-4]}_to_2026-06-30.csv") for k in CF_KEYS}
    shas = {k: write_cf(files[k], of(k, before(rows, cut))) for k in CF_KEYS}
    full_shas = {k: write_cf(full[k], of(k, before(rows, end))) for k in CF_KEYS}
    return SimpleNamespace(files=files, shas=shas, full_files=full, full_shas=full_shas, rows_cut=before(rows, cut), rows_all=rows, dir=d)


def smoke_plant_checks(W, src, frame, cal, cx, env):
    """the planted world through the REAL loaders: the cut, the two cash extracts read as ONE table, the planted cases, the score of EVERY name at the chosen ranks (every key) against the plain-python recount -> (srows, ranks, cik_of, ent)"""
    ix = list(W.syms)
    j = lambda n_: ix.index(n_)
    ci, xi = src.cinfo, src.cash.info
    assert W.days.max() < S.LB0 and ci["filed_range"][1] < "2025-06-30" and ci["rows_filed_on_or_after_the_cut"] == 0 and ci["rows_end_on_or_after_the_cut"] == 0, ("nothing on / after the cut", ci["filed_range"])
    assert ci["files"]["cf"] + ci["files"]["cf_alt"] == ci["rows_read"] == ci["rows"] == len(cx.rows_cut) and ci["files"]["cf_alt"] == sum(1 for r in cx.rows_cut if r[1] in FILE_CONCEPTS["cf_alt"]) > 0, ci
    assert set(ci["rows_by_concept"]) == set(CONCEPTS) and all(ci[k] == 0 for k in DROP_KEYS + ("rows_value_missing",)) and max(r[5] for r in cx.rows_all) > "2025-09-01", "every concept arrives; the synthetic world holds filings of the sealed year and the pinned files hold none"
    assert xi["ambiguous"] >= 1 and xi["negative_component_value"] >= 1 and xi["later_filing_carries_another_value"] >= 10 and xi["periods_by_type"]["FY"] > 300, xi
    cik_of = dict(zip(src.mp.df["symbol"], src.mp.df["cik"]))
    ent = brute_cash(cx.rows_cut)
    ranks = built_ranks(W, WF0, PRE_END)
    by_month = {f"{W.days[r]:%Y-%m}": r for r, _f, _x in ranks}
    chosen = [by_month[m_] for m_ in SMOKE_RANK_MONTHS]
    t0 = time.time()
    n_score = compare_scores(W, ent, frame, cal, chosen)
    assert n_score == len(chosen) * W.S, n_score
    at = lambda m_: score_rank(W, by_month[m_])
    cd = lambda sc_, n_, k_="P": REASONS[int(sc_.code[k_][j(n_)])]
    for m_ in ("2017-06", "2020-06", "2023-03"):
        sc = at(m_)
        assert (cd(sc, "S02"), cd(sc, "S03"), cd(sc, "S30"), cd(sc, "S08"), cd(sc, "S04")) == ("foreign_filer", "not_in_map", "no_cashflow_fact_for_cik", "no_share_fact_for_cik", "map_ambiguous"), m_
    assert cd(at("2020-06"), "S24") == "score_over_0.50" and cd(at("2019-06"), "S24") == "scored", "S24's x100 repurchase: no score while its quarter is in the TTM, LISTED"
    assert cd(at("2021-09"), "S25") == "scored" and cd(at("2021-12"), "S25") == "fiscal_year_change" and cd(at("2022-03"), "S25") == "fiscal_year_change" and cd(at("2022-09"), "S25") == "scored", "[B1] S25's change of fiscal year"
    assert cd(at("2019-09"), "S26") == "stale_over_200_days" and any(cd(at(m_), "S26") == "scored" for m_ in ("2019-03", "2019-06", "2020-03", "2020-06")) and cd(at("2020-09"), "S27") == "stale_over_200_days" and cd(at("2019-06"), "S27") == "scored"
    assert cd(at("2020-06"), "S29") == "negative_ttm_component", "S29's sign error makes FY 2019's repurchases unusable: a negative TTM"
    sc = at("2019-06")
    cu = comp_use(sc, np.array([j("S28"), j("S13")]))
    assert cu["rep"]["fallback"][0] and cu["iss"]["second"][0] and cu["iss"]["dedup"][0] and cu["rep"]["zero_any"][1], "S28: the fallback concept, the second primary, [B7]'s same-value rule; S13: the ambiguous quarter reads ZERO"
    srows = score_report(W, ranks, values=True)
    b3 = blind_spot(srows)
    assert all(not d_["above"] for d_ in b3.values()) and all("S31" in d_["names"] for y_, d_ in b3.items() if 2017 <= y_ <= 2024), "[B3]: S31 reads zero everywhere, the year's share is far below 10%"
    o50 = {n_ for r_ in srows for n_ in r_["cells"]["P"]["over50_names"]}
    assert o50 == {"S24"}, o50
    tot = lambda k_, key: sum(r_["cells"][k_][key] for r_ in srows)
    assert all(tot(k_, "scored") > 4000 and tot(k_, "flags") > 50 for k_ in CODE_KEYS) and sum(r_["comp"]["iss"]["dedup"] for r_ in srows) > 50 and sum(r_["comp"]["rep"]["mixed"] for r_ in srows) > 50, {k_: (tot(k_, "scored"), tot(k_, "flags")) for k_ in CODE_KEYS}
    print(f"planted cases ok through the real loaders (the cut at read, the two cash extracts as ONE table, the NETISS share counts, S24 / S25 / S26 / S27 / S28 / S29 / S30 / S31 / S13 / S08 / S02 / S03); against the plain-python recount: the score of every name at "
          f"{len(chosen)} ranks x {len(CODE_KEYS)} keys ({n_score:,} name-ranks, {time.time() - t0:.0f}s)")
    return srows, ranks, cik_of, ent


def smoke(*a):
    """python r23_buyback.py smoke DIR [stage_b]: offline, on SYNTHETIC worlds (nothing real is read or written; DIR is wiped and its name must contain 'smoke'). r21_netiss's synthetic market and share counts (smoke_env) with this family's synthetic cash-flow extracts and a
    planted PAYOUT effect. Order: the selftest on the real constants; the planted world through the real loaders against plain-python recounts (every score at 18 ranks, then every pool, close row, score, pick, decile and daily path over the
    rebalances of 2023-06 .. 2024-08 in the judged reading [B13], [B10]'s 'keep' report and the leaky reading, and the first rebalances); the dryload (counts only); Stage A's refusal paths (every pinned file: another sha, absent, a fact in
    both extracts, a column missing; [B3] above 10%; the book; the RESMOM line file); Stage A on the NULL world (must FAIL) and on the PLANTED world (the effect must be found: (a) - (e) pass, (f) awaits the hand audit; BEFORE ANY P&L,
    [B3], [B9] and the power line print before any cell's P&L; [B13]'s closes and the 'keep' report with its count); the hand audit by groups (keep / data_event); Stage B's refusal paths; with the argument stage_b the
    one read of Stage B on the synthetic lockbox days, the verdict = the leg's veto alone, a second read refused, Stage A frozen"""
    root = os.path.abspath(a[0] if a else os.path.join(tempfile.gettempdir(), "buyback_smoke"))
    with_b = "stage_b" in a[1:]
    why = smoke_refusal(root)
    if why:
        raise SystemExit(why)
    selftest()                                                                             # the hand-made checks first, on the real constants (before anything below is patched)
    t_start = time.time()
    dates_of = lambda txt: re.findall(r"\b20\d\d-\d\d-\d\d\b", txt)
    with patched(NI, smoke_drift=smoke_drift, SMOKE_THETA=SMOKE_THETA), NI.smoke_env(root, nrep=100) as env, patched(THIS, OUT=os.path.join(root, "bb_out"), CHECK_BOOK=False, NREP=100), spec(**SMOKE_SPEC):
        os.makedirs(OUT)
        sa_path, go, rd = os.path.join(OUT, "buyback_stageA.json"), os.path.join(OUT, GO_FLAG), os.path.join(OUT, READ_FLAG)
        # ---- 1. the planted world through the REAL loaders, its cash-flow filings, every pipeline step against plain-python recounts
        W, cal, winfo, tbis = NI.smoke_world(env, "plant")
        pw = smoke_payout()
        t0 = time.time()
        rows_cf = smoke_cash(W, env.sh, pw)
        cx = smoke_cash_files(root, rows_cf)
        assert all(os.path.commonpath([os.path.realpath(p), os.path.realpath(root)]) == os.path.realpath(root) for p in list(cx.files.values()) + list(cx.full_files.values())), "the synthetic extracts are inside the smoke dir"
        lb_cash = {k: (cx.full_files[k], cx.full_shas[k]) for k in CF_KEYS}
        print(f"synthetic market: r21_netiss's {len(env.fk['plant'].names)} names x {len(env.days):,} business days and its share counts; cash flows: {len(rows_cf):,} filing rows ({len(cx.rows_cut):,} filed before the cut, the rest in the sealed year) from a persistent net payout rate "
              f"in -10% .. +12% a name (S32 +18%, S21 -17%) x the market value, the planted cases S24 / S25 / S26 / S27 / S28 / S29 / S30 / S31 / S32 / S13 / S14; the PLANTED world drifts every name by +{SMOKE_THETA:g} x its payout rate a year, the NULL world does not "
              f"({env.build_seconds:.0f}s + {time.time() - t0:.0f}s); SPEC shrunk to {SMOKE_SPEC}")
        with patched(THIS, FILES=dict(cx.files), FILE_SHA=dict(cx.shas)):
            src = load_sources(S.LB0)
            frame, _fi = NI.load_facts(S.LB0)
            attach_buyback(W, src.cash, src.fx, src.mp, cal)
            srows, ranks, cik_of, ent = smoke_plant_checks(W, src, frame, cal, cx, env)
            ix = list(W.syms)
            lo_, hi_ = TS("2023-06-01"), TS("2024-08-31")
            t0 = time.time()
            n_paths, legs = 0, {}
            for pm in (JUDGED, "keep", "remove"):                                       # [B13] the judged reading ('close'), [B10]'s 'keep' report and the leaky one, each against the recount
                Bz = brute_bb(W, ent, frame, cal, cik_of, lo_, hi_, pm)
                L_ = bb_build(W, lo_, hi_, pm)
                n_paths += compare_bb(W, L_, Bz, f"smoke {pm}")
                series_check(W, L_, Bz)
                legs[pm] = L_
            Lj = legs[JUDGED]
            modes = {c: Counter(r_.cell[c].mode for r_ in Lj.recs) for c in CELLS}
            assert len(Lj.recs) >= 12 and all(sum(r_.cell[c].traded for r_ in Lj.recs) >= 12 and all(r_.cell[c].n >= 30 for r_ in Lj.recs) for c in CELLS) and sum(modes[c].get("top", 0) for c in CELLS) >= 8, (modes, [r_.cell["P"].n for r_ in Lj.recs])
            j1_, j2_ = ix.index(NI.SMOKE_DUAL[0]), ix.index(NI.SMOKE_DUAL[1])
            n_dual = sum(len(r_.cell[c].second) for r_ in Lj.recs for c in CELLS)
            assert n_dual >= 10 and all(not {j1_, j2_} <= set(r_.pool[r_.cell[c].idx].tolist()) for r_ in Lj.recs for c in CELLS), ("[A13] one class of the dual pair is scored, never both", n_dual)
            assert all(r_.cell[k].dec is not None for r_ in Lj.recs for k in DEC_KEYS) and sum(r_.cell["FLAT"].n for r_ in Lj.recs) > 0
            lo2, hi2 = TS("2016-11-01"), TS("2017-03-31")
            Bz_e, Le = brute_bb(W, ent, frame, cal, cik_of, lo2, hi2, JUDGED), bb_build(W, lo2, hi2, JUDGED)
            n_early = compare_bb(W, Le, Bz_e, "smoke early")
            n_cl = {pm: sum(c_.get("closed_spin", 0) for c_ in L_.cnt.values()) for pm, L_ in legs.items()}
            print(f"  {len(Lj.recs)} rebalances ({lo_:%Y-%m-%d} .. {hi_:%Y-%m-%d}) in the judged reading [B13], [B10]'s 'keep' report and the leaky one against the recount ({time.time() - t0:.0f}s): every pool, close row "
                  f"({n_cl[JUDGED]} positions closed before a spin-off / stock-dividend ex-date), score, [A13] decision ({n_dual} second-class name-ranks of the dual pair), mode, pick, twin, decile, first-reason count and {n_paths:,} paths "
                  f"under four costings; the first {len(Le.recs)} rebalances too ({n_early:,} paths)")
            B, legs_meta = A13.load_463()
            rowsB = A13.book_rows(B, W)
            # ---- 2. the dryload: COUNTS only
            before = sorted(os.listdir(OUT))
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                dryload()
            td = buf.getvalue()
            assert sorted(os.listdir(OUT)) == before, "the dryload writes nothing"
            dryload_text_checks(td)
            Lc = bb_build(W, WF0, PRE_END, JUDGED, units=False, counts_only=True)
            for nm_, fn_ in (("the file counts", lambda: print_data_counts(src, W)), ("the score block", lambda: print_score_report(score_report(W, ranks, values=False), names=False)), ("[B3]", lambda: print_blind_spot(blind_spot(srows))),
                             ("the scored names per rebalance", lambda: print_scored_stats(LAB_J, Lc, W)), ("[A13]", lambda: print_second_classes(second_classes(Lc, W)))):
                fb = io.StringIO()
                with contextlib.redirect_stdout(fb):
                    fn_()
                assert fb.getvalue() in td, f"the dryload's {nm_} lines are the full computation's"
            print("dryload ok on the synthetic world: counts only (no cash amount, score value, price, return, P&L or statistic), no lockbox date, nothing written, its lines equal the full computation's")
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
            for key in CF_KEYS:
                must("is not the registered", FILE_SHA={**FILE_SHA, key: "0" * 64})
                must("is not on file", FILES={**FILES, key: os.path.join(root, "xbrl", "absent.csv")})
            for key in NI.FILES:
                with patched(NI, FILE_SHA={**NI.FILE_SHA, key: "0" * 64}):
                    must("is not the registered")
            xd = os.path.join(root, "xbrl_bad")
            os.makedirs(xd)
            lines = {k: [l_ for l_ in open(cx.files[k], newline="").read().split("\n") if l_] for k in CF_KEYS}
            rep_line = next(l_ for l_ in lines["cf"][1:] if f",{C_REP[0]}," in l_)
            p1 = os.path.join(xd, "cf_alt_overlap.csv")
            open(p1, "w", newline="\n").write("\n".join(lines["cf_alt"] + [rep_line]) + "\n")
            must("in BOTH cash-flow extracts", FILES={**FILES, "cf_alt": p1}, FILE_SHA={**FILE_SHA, "cf_alt": M17.sha_raw(p1)})
            p2 = os.path.join(xd, "cf_nocol.csv")
            open(p2, "w", newline="\n").write("\n".join([lines["cf"][0].replace(",accn,", ",accession,")] + lines["cf"][1:]) + "\n")
            must("lacks the column", FILES={**FILES, "cf": p2}, FILE_SHA={**FILE_SHA, "cf": M17.sha_raw(p2)})
            blind = {NI.smoke_cik(n_) for k_, n_ in enumerate(NI.SMOKE_NAMES) if k_ % 6 == 0}            # [B3]: a sixth of the firms lose every component line of the periods ending in 2021 - 2022 (the zero rule reads them all as zero)
            rows_b3 = [r for r in rows_cf if not (r[0] in blind and r[1] not in C_ST and "2021-01-01" <= r[4] <= "2022-12-31")]
            cb = smoke_cash_files(root, rows_b3, tag="b3_")
            msg = must("[B3]", FILES=dict(cb.files), FILE_SHA=dict(cb.shas))
            assert "MANAGER's ruling" in msg and "2022" in msg, msg
            must("do not reproduce", CHECK_BOOK=True)
            with patched(DV, REF_SHA="0" * 64):
                must("RESMOM line file")
            with patched(DV, REF_CSV=os.path.join(root, "resmom", "absent.csv")):
                must("is not on file - the REFERENCE book")
            print("Stage A refuses (and writes nothing) on: a changed pre-registration, an unregistered wide calendar, each cash-flow extract and each NETISS file with another sha, an absent extract, a fact in both extracts, an extract without its columns, [B3] above 10% "
                  "(MANAGER's ruling), a book that does not reproduce #463, a RESMOM line file that is absent / not the registered one")

            def run_stage_a(world):
                env.switch(world)
                b_ = io.StringIO()
                with contextlib.redirect_stdout(b_):
                    o_ = stage_a()
                return o_, b_.getvalue()
            # ---- 4. Stage A on the NULL world: the same filings and random numbers without the payout effect must FAIL
            t0 = time.time()
            out_n, txt_n = run_stage_a("null")
            cells_n = out_n["stageA"]["cells"]
            assert out_n["judged"] is True and out_n["stageA"]["pass_cells"] == [] and out_n["candidate"] is None and out_n["stageA"]["null"]["draws"] == NREP == 100, (out_n["stageA"]["pass_cells"], out_n["candidate"])
            assert "BUYBACK Stage A: FAIL - no cell passes (a)-(e)" in txt_n and "Stage A (a)-(e) pass" not in txt_n and all(d < "2025-06-30" for d in dates_of(txt_n)), "the null world fails and prints no lockbox date"
            dn = {c: [q["net"] for q in cells_n[c]["deciles"]["deciles"]] for c in CELLS}
            sn = {c: float(np.corrcoef(np.arange(10), dn[c])[0, 1]) for c in CELLS}
            os.remove(sa_path)
            print(f"Stage A on the NULL world ({time.time() - t0:.0f}s): FAIL as it must - WF ROC@30k " + ", ".join(f"{c} {cells_n[c]['base']['roc']:.1f}" for c in CELLS) + f"; null p95 {out_n['stageA']['null']['roc_max']['p95']:.1f}; rank correlation of the decile nets with the decile "
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
            assert "(f) AWAITS THE HAND AUDIT" in txt and "BUYBACK Stage A: (a)-(e) pass" in txt and "audit complete" not in txt.lower() and all(d < "2025-06-30" for d in dates_of(txt)), "the harness never decides (f); no lockbox date"
            assert out["prereg_sha256_lf"] == PREREG_SHA and {k: out.get(k) for k in stamp()} == stamp() and out["manifest_sha256"] == D15.MANIFEST_PREFIX + "0" * 56 and out["stageA"]["null"]["draws"] == NREP and out["judged_post_mode"] == JUDGED == "close"
            # [B13] the judged reading closes, never removes; [B10]'s 'keep' reading is in the file as a report (no null) with its removed name-months, printed beside the judged cells; no '[D2]' for the ex-dates in any print
            b10, hj, ha = out["b10_removal_reading"], out["hygiene_counts_by_year"]["judged"], out["hygiene_counts_by_year"]["b10_removal"]
            tot = lambda h_, k_: sum(v_.get(k_, 0) for v_ in h_.values())
            rm_ = b10["removed_name_months"]
            assert b10["post_mode"] == "keep" and b10["null"] is None and set(b10["cells"]) == set(CELLS) and rm_ == b10_removed(ha) and tot(hj, "post_spin") == tot(hj, "post_calendar_split") == 0, rm_
            assert tot(hj, "kept_calendar_split") == rm_["calendar_split"] and tot(hj, "closed_spin") >= rm_["spin_off_or_stock_dividend"] >= 1 and tot(hj, "kept_flagged") >= 1, (rm_, tot(hj, "closed_spin"), tot(hj, "kept_calendar_split"))
            assert f"{LAB_A}, no null - it removed {rm_['calendar_split']:,} pool name-months" in txt and "[D2]" not in txt and "[D2]" not in txt_n, "the report and its count are printed; no [D2] label for the ex-dates"
            assert all(b10["cells"][c]["base"]["net"] != cells[c]["base"]["net"] for c in CELLS), "the judged reading and the 'keep' report differ (the closed positions, the kept splits)"
            print(f"  [B13] the judged reading closed {tot(hj, 'closed_spin'):,} pool positions at the close before a spin-off / stock-dividend ex-date and kept {tot(hj, 'kept_calendar_split'):,} calendar splits and {tot(hj, 'kept_flagged'):,} "
                  f"flagged names on the split-safe path; [B10]'s 'keep' report (no null) removed {rm_['spin_off_or_stock_dividend']:,} + {rm_['calendar_split']:,} name-months: P net ${b10['cells']['P']['base']['net']:,.0f} / R ${b10['cells']['R']['base']['net']:,.0f} "
                  f"against the judged ${cells['P']['base']['net']:,.0f} / ${cells['R']['base']['net']:,.0f}")
            # BEFORE ANY P&L, [B3], [B9] and the power line print before any cell's P&L, in that order
            order = ("[B6] / [B7] the two pinned cash-flow extracts", "BEFORE ANY P&L - the payout score", "names lost to each no-score rule", "no score at |score| > 0.50", "the TTMs built per fill year", "concept used, ISSUANCE [B7]", "STALENESS", "[B2] the share of SCORED names",
                     "[B17] STALE S", "names with no score whatever the rank, LISTED by name", "[A13] ONE SHARE CLASS PER FIRM", "[B3] THE TAG BLIND SPOT", "[B9] BEFORE ANY RETURN", "[B19] BEFORE ANY P&L", "POWER LINE - printed before any cell's P&L", f"WF {WF0:%Y-%m-%d} -> ")
            seq = [txt.index(s_) for s_ in order]
            assert seq == sorted(seq), ("the pre-P&L blocks are out of order", seq)
            outcome = re.search(r"[$]\s*-?\d|ROC|Sortino|net [$]|drawdown", txt[seq[1]:seq[-2]])
            assert not outcome, ("a P&L figure was printed before the power line", txt[max(seq[1] + outcome.start() - 80, 0):seq[1] + outcome.end() + 80])
            assert out["unscored_by_name"]["foreign_filer"].keys() == {"S02"} and out["unscored_by_name"]["not_in_map"].keys() == {"S03"} and out["unscored_by_name"]["no_cashflow_fact_for_cik"].keys() == {"S30"} and out["unscored_by_name"]["no_share_fact_for_cik"].keys() == {"S08"}, out["unscored_by_name"]
            lst50 = txt[txt.index("P no score at |score| > 0.50"):].split("\n")[0]
            assert "LISTED" in lst50 and "S24 x" in lst50, "S24's x100 repurchase is LISTED by name before any P&L"
            assert all(not d_["above"] for d_ in out["blind_spot_b3"].values()) and len(out["b9_by_rank"]) == len(out["score_by_rank"]) and all(e_["cells"][c] is None or (e_["cells"][c]["picked"] > 0 and e_["cells"][c]["picked"] % 2 == 0) for e_ in out["b9_by_rank"] for c in CELLS)
            assert sum(e_["cells"]["P"]["zero"] for e_ in out["b9_by_rank"] if e_["cells"]["P"]) > 0, "[B9]: the zero rule reads some picked name's components (the issuers repurchase nothing)"
            b9l = txt[txt.index("[B9] BEFORE ANY RETURN"):txt.index("POWER LINE")]
            assert all(f"  {c}: " in b9l and "over every traded rank" in b9l for c in CELLS) and not re.search(r"[$]\s*-?\d|ROC|net [$]", b9l), "[B9]: the zero-rule share of the picks, counts only"
            # the effect: the planted world's P deciles rise from the biggest raisers to the biggest payers; the null world's do not
            dp = {c: [q["net"] for q in cells[c]["deciles"]["deciles"]] for c in CELLS}
            sp = {c: float(np.corrcoef(np.arange(10), dp[c])[0, 1]) for c in CELLS}
            assert sp["P"] > 0.7 and dp["P"][9] > dp["P"][0] and all(cells[c]["deciles"]["ranks_cut"] > 50 for c in CELLS), (sp, sn)
            print(f"Stage A on the PLANTED world ({time.time() - t0:.0f}s): the effect is found - the deciles rise from the biggest raisers to the biggest payers (rank correlation of the net with the decile " + ", ".join(f"{c} {sp[c]:+.2f}" for c in CELLS)
                  + f", the null world {sn['P']:+.2f} / {sn['R']:+.2f}); " + ", ".join(f"{c} ROC@30k {cells[c]['base']['roc']:.0f} (${cells[c]['usd_year']:,.0f} a year, {cells[c]['base']['n_pos']:,} positions, {cells[c]['base']['n_units']} rebalances)" for c in CELLS)
                  + f"; (a)-(e) pass for {passing}, candidate {cand}, (f) awaits the hand audit")
            # every cell's WF numbers recomputed from a fresh leg, the cost curve, the dollars a year, A2 over the reference on the cell's own window, the beta rule, the twins
            Lw = bb_build(W, WF0, PRE_END, JUDGED)
            ref_ = DV.ref_load(B, check_facts=False)
            for cell in CELLS:
                run_ = M17.run_cell(W, cell_leg(Lw, cell), D15.l1_cfg(), pos=True)
                st, xb_, _cb = stat_run(B, rowsB, run_)
                got = cells[cell]["base"]
                assert st["n_pos"] == got["n_pos"] == out["parity"][cell]["n_pos"] and abs(st["net"] - got["net"]) < 1e-6 and abs(st["roc"] - got["roc"]) < 1e-9, cell
                for b_, got_ in ((0.0, cells[cell]["cost0"]), (10.0, cells[cell]["stress"]["10 bps"]), (20.0, cells[cell]["stress"]["20 bps"])):
                    assert abs(got_["net"] - stat_run(B, rowsB, M17.run_cell(W, cell_leg(Lw, cell), D15.l1_cfg(bps=b_)))[0]["net"]) < 1e-6, (cell, b_)
                ff = first_fill(W, Lw, cell)
                win = a2_window(ff)
                mw = B.mask(*win)
                a2 = cells[cell]["A2"]
                assert cells[cell]["first_traded_fill"] == f"{ff:%Y-%m-%d}" and a2["window"] == [f"{win[0]:%Y-%m-%d}", f"{win[1]:%Y-%m-%d}"] and a2["rows"] == int(mw.sum()) and abs(a2["c"] - A2_TARGET * float(np.std(B.raw[mw], ddof=1)) / float(np.std(xb_[mw], ddof=1))) <= 1e-9 * a2["c"], (cell, a2["window"])
                assert a2["incremental_pass"] is bool(a2["roc"] > a2["reference"]["roc"] and a2["sortino"] > a2["reference"]["sortino"]) and a2["incremental_credit"] is bool(a2["incremental_pass"] and cells[cell]["beta"]["within_cap"]) and "dd5" in a2 and "dd5" in a2["reference"]
                assert abs(cells[cell]["usd_year"] - got["net"] / got["years"]) < 1e-6 and got["years"] > 8.0 and cells[cell]["dd5"]["n"] >= 1
            assert out["reference"]["sha256"] == env.ref_sha == out["reference"]["pinned_sha256"] and out["reference"]["rows"] == ref_.n_rows and set(out["stageA"]["twins"]) == set(TWINS) | {DECK} and all(out["stageA"]["twins"][t]["base"]["n_pos"] > 0 for t in ("DIV", "P8", "R8"))
            for frag in ("COST CURVE", "BY JULY-JUNE YEAR", "THE TWO REGIME HALVES", "THE REFERENCE BOOK'S DRAWDOWN EPISODES", "THE LONG AND SHORT SIDES APART", "realised beta to ES", "persistence:", "short leg [R2]", "survivorship:", "a year)", "THE NETISS QUESTION", "TWINS - REPORTED",
                         "DIVIDEND-ONLY twin", "[B8] P with the tax-withholding", "FLAT twin", "REPY (gross repurchase yield", "DD5 $", "A2 (a report)", "first 24 months of traded fills"):
                assert frag in txt, frag
            nq = out["netiss_question"]
            assert all(set(nq[c]["corr"]) == {"N12", "N24"} and nq[c]["overlap"]["N12"]["rebalances"] > 50 for c in CELLS) and set(nq["netiss"]) == {"N12", "N24"}, "the NETISS question: NETISS's two cells in-process on this World"
            ca2 = cells[cand]["A2"]
            assert out["candidate"]["c"] == ca2["c"] > 0 and out["candidate"]["window"] == ca2["window"] and out["candidate"]["first_traded_fill"] == cells[cand]["first_traded_fill"], "the frozen size travels with its window"
            cd = pd.read_csv(os.path.join(OUT, "buyback_audit_candidates.csv"))
            fl = pd.read_csv(os.path.join(OUT, "buyback_flags.csv"))
            fl["picked"] = fl["picked"].fillna("")
            assert {"symbol", "date", "exit", "side", "pnl", "cell", "rank_date", "cik", "ttm", "statement_end", "rep_ttm", "div_ttm", "iss_ttm", "mv", "shares", "shares_accn", "facts", "group", "zero_rule"} <= set(cd.columns), list(cd.columns)
            assert {"cell", "symbol", "date", "picked", "score", "rank_date", "facts", "group"} <= set(fl.columns) and len(fl) == out["flags"] > 0 and (fl["score"].abs() > FLAG).all() and int((fl["picked"] != "").sum()) == out["flags_picked"] > 0
            top_ = cd[cd["list"] == "top_contributor"]
            b19_, cb_ = out["b19_split_no_factor_move"], cd[cd["list"] == "b19_split_no_factor_move"]
            assert len(cb_) == len(b19_) and bool(cb_["data_event_candidate"].all()) and not bool(top_["data_event_candidate"].any()) and list(zip(cb_["symbol"], cb_["date"])) == [(r_["symbol"], r_["fill"]) for r_ in b19_], "[B19] the listed positions are the data-event candidates"
            assert all(abs(r_["factor_move"] - 1.0) <= 0.01 and r_["split_ratio"] != "n/a" for r_ in b19_ if np.isfinite(r_["factor_move"])) and ("none" in txt[txt.index("[B19] BEFORE ANY P&L"):].split("\n")[0]) == (not b19_)
            print(f"  [B19] picked positions with a calendar split the vendor's factor does not show, listed before any P&L and sent to the hand audit as data-event candidates: {len(b19_)}" + (" - " + "; ".join(
                f"{r_['symbol']} {r_['rank']} ex {r_['ex_date']} {r_['split_ratio']} F move {r_['factor_move']:.4f} ({', '.join(r_['picked_by'])})" for r_ in b19_[:5]) if b19_ else ""))
            assert set(top_["cell"]) == set(CELLS) and top_.groupby("cell").size().max() == AUDIT_N and cd["exit"].max() < "2025-06-30" and fl["date"].max() < "2025-06-30" and (cd["group"].str.split("|").str[0] == cd["symbol"]).all()
            pkw, ixw = picks_by_name_month(Lw), {n_: i_ for i_, n_ in enumerate(W.syms)}
            assert all(r_["picked"] == ", ".join(pkw.get((W.days.get_loc(TS(r_["date"])), ixw[r_["symbol"]]), [])) for r_ in fl.to_dict("records")), "every flagged name-rank's picked column is the registered leg's picks"
            assert fl.loc[fl["picked"] != "", "group"].nunique() == out["flags_picked_groups"] <= out["flags_picked"]
            pm = peak_mb()
            print(f"audit candidates: the {AUDIT_N} largest gains per cell with every component fact, its filing and the market value's inputs -> buyback_audit_candidates.csv; every |score| > 0.15 name-rank ({len(fl)}, {out['flags_picked']} picked in {out['flags_picked_groups']} groups) -> "
                  "buyback_flags.csv" + (f"; peak memory {pm:,.0f} MB" if pm else ""))
            # ---- 6. the hand audit by groups: every listed contributor and ONE row per picked flagged group 'keep' -> the same numbers; a data_event on the candidate's largest gain -> out of both cells and the nulls, with its group
            ap = os.path.join(OUT, "buyback_audit.csv")
            one_per_group = fl[fl["picked"] != ""].drop_duplicates("group")
            keys = pd.concat([cd[["symbol", "date", "cell"]], one_per_group[["symbol", "date", "cell"]]]).drop_duplicates().reset_index(drop=True)
            keys.assign(verdict="keep", note="smoke: nothing found").to_csv(ap, index=False)
            out2, _txt2 = run_stage_a("plant")
            assert out2["audit"]["rows"] == len(keys) == out2["audit"]["keep"] and out2["audit"]["data_event"] == 0 and out2["audit"]["group_name_months"] == 0 and out2["audit_sha256"] == file_sha(ap) != out["audit_sha256"], out2["audit"]
            assert all(v["audited"] == v["listed"] == AUDIT_N and v["audit_complete"] and v["flag_audited"] == v["flag_listed"] and v["flag_complete"] for v in out2["audit_status"].values()), out2["audit_status"]
            assert out2["stageA"]["pass_cells"] == passing and out2["candidate"] == out["candidate"] and all(out2["stageA"]["cells"][c]["base"][k] == cells[c]["base"][k] for c in CELLS for k in ("n_pos", "net", "roc", "max_dd", "sortino")), "a keep changes no number"
            top = cd[cd["cell"] == cand].iloc[0]
            au = pd.read_csv(ap)
            hit = (au["symbol"] == top["symbol"]) & (au["date"] == top["date"])                          # the name-month's rows (one per cell that lists it): all of them data_event
            au.loc[hit, "verdict"] = "data_event"
            au.to_csv(ap, index=False)
            out3, _txt3 = run_stage_a("plant")
            cd3 = pd.read_csv(os.path.join(OUT, "buyback_audit_candidates.csv"))
            jtop, ftop = ix.index(top["symbol"]), W.days.get_loc(TS(top["date"]))
            mem = group_members(W, jtop, name_month_keys(W, ftop, jtop))
            mem_dates = {f"{W.days[f_]:%Y-%m-%d}" for f_ in mem}
            assert ftop in mem and out3["audit"]["group_name_months"] == len(set(mem) - {ftop}) and out3["audit"]["data_event"] == int(hit.sum()) >= 1, (len(mem), int(hit.sum()), out3["audit"])
            assert not ((cd3["symbol"] == top["symbol"]) & cd3["date"].isin(mem_dates)).any() and out3["audit_sha256"] != out2["audit_sha256"], "the name-month and every other name-month of its group are gone from every list"
            n3 = out3["stageA"]["cells"][cand]["base"]
            assert n3["net"] != cells[cand]["base"]["net"] and n3["n_pos"] == cells[cand]["base"]["n_pos"] and out3["stageA"]["null"]["roc_max"]["p95"] != out2["stageA"]["null"]["roc_max"]["p95"], "the slot goes to the next name; the name-month is out of the nulls too"
            print(f"hand audit by groups [B4]: {len(keys)} rows 'keep' (the {AUDIT_N} largest contributors per cell + ONE row per picked flagged group: {len(one_per_group)} groups cover {out['flags_picked']} picked flagged name-ranks) -> the same numbers, audit counted; "
                  f"a data_event on {top['symbol']} {top['date']} ({cand}'s largest gain) -> out of both cells and both nulls with {out3['audit']['group_name_months']} more name-month(s) of its group: {cand} net ${cells[cand]['base']['net']:,.0f} -> ${n3['net']:,.0f}")
            out, cells = out3, out3["stageA"]["cells"]
            cand, c_frozen = out["candidate"]["cell"], out["candidate"]["c"]
            # ---- 7. Stage B's refusal paths: none may write the read flag
            print("--- Stage B refusal paths: no go-flag / not judged / no candidate / a stale stamp / a broken size or window / the lockbox year's extracts not pinned / a changed audit file / a drifted calendar, manifest, book, WF numbers or size c / a bad lockbox extract")
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
                j_ = json.loads(js0)
                j_[k] = ["x"] if isinstance(st0[k], list) else "0" * 64
                open(sa_path, "w").write(json.dumps(j_))
                must_b("different harness version")
            for edit in (lambda j: j.update(prereg_sha256_lf="0" * 64),):
                j_ = json.loads(js0)
                edit(j_)
                open(sa_path, "w").write(json.dumps(j_))
                must_b("another pre-registration")
            for edit in (lambda j: j.update(judged=False), lambda j: j.update(candidate=None), lambda j: j["stageA"].update(pass_cells=[]), lambda j: j["stageA"].update(pass_cells=[c for c in CELLS if c != j["candidate"]["cell"]])):
                j_ = json.loads(js0)
                edit(j_)
                open(sa_path, "w").write(json.dumps(j_))
                must_b("no Stage A candidate")
            for badc in (0.0, -1.0, float("nan"), None):
                j_ = json.loads(js0)
                j_["candidate"]["c"] = badc
                open(sa_path, "w").write(json.dumps(j_))
                must_b("positive number")
            j_ = json.loads(js0)
            j_["candidate"]["window"] = ["2019-01-01", "2017-01-01"]
            open(sa_path, "w").write(json.dumps(j_))
            must_b("window")
            open(sa_path, "w").write(js0)
            with patched(NI, LB_FACTS=None):
                must_b("the lockbox year's facts are not pinned")
                must_b("the lockbox year's facts are not pinned", LB_CASHFLOW=lb_cash)
            with patched(NI, LB_FACTS=env.lb_facts):
                must_b("the lockbox year's facts are not pinned")
                must_b("the lockbox year's facts are not pinned", LB_CASHFLOW={"cf": lb_cash["cf"]})
                must_b("DIFFERS", PREREG_SHA="0" * 64, LB_CASHFLOW=lb_cash)
                with patched(M17, WIDE_CA_SHA="0" * 64):
                    must_b("different harness version", LB_CASHFLOW=lb_cash)
                for key in CF_KEYS:
                    must_b("different harness version", LB_CASHFLOW=lb_cash, FILE_SHA={**FILE_SHA, key: "0" * 64})
                au0 = open(ap).read()
                open(ap, "a").write("ZZZ,2016-11-01,P,keep,a changed audit file\n")
                must_b("not the file Stage A ran with", LB_CASHFLOW=lb_cash)
                open(ap, "w").write(au0)
                must_b("do not reproduce its LB numbers", CHECK_BOOK=True, LB_CASHFLOW=lb_cash)
                okbk = lambda B_, lo_, hi_, ref: {"roc": 0.0, "sortino": 0.0, "ref": list(ref), "ok": True}
                with patched(A13, book_check=okbk):
                    must_b("not the one Stage A ran on", CHECK_BOOK=True, LB_CASHFLOW=lb_cash, manifest_sha=lambda: "ffffffff" + "0" * 56)
                csv0 = open(env.wide_csv, "rb").read()
                with open(env.wide_csv, "ab") as f_:
                    f_.write(b"cash_dividend,S01,,,2024-02-09,2024-02-09,,,0.01,,,,False\n")
                must_b("is not the registered wide calendar", LB_CASHFLOW=lb_cash)
                open(env.wide_csv, "wb").write(csv0)
                assert M17.sha_raw(env.wide_csv) == env.wide_sha
                must_b("is not the registered", LB_CASHFLOW={k: (v[0], "0" * 64) for k, v in lb_cash.items()})                   # the lockbox extract is not the file the addendum pinned
                with patched(NI, LB_FACTS={k: (v[0], "0" * 64) for k, v in env.lb_facts.items()}):
                    must_b("is not the registered", LB_CASHFLOW=lb_cash)                                                             # NETISS's lockbox share counts likewise
                for edit, frag in ((lambda j: j["parity"][cand].update(net=j["parity"][cand]["net"] + 1e6), "do not reproduce on Stage B's data"), (lambda j: j["parity"][cand].update(n_pos=j["parity"][cand]["n_pos"] + 1), "do not reproduce on Stage B's data"),
                                   (lambda j: j["candidate"].update(c=j["candidate"]["c"] * 1.0001), "volatility-set size c"), (lambda j: j["candidate"].update(window=[j["candidate"]["window"][0], "2030-01-01"]), "volatility-set size c")):
                    j_ = json.loads(js0)
                    edit(j_)
                    open(sa_path, "w").write(json.dumps(j_))
                    must_b(frag, LB_CASHFLOW=lb_cash)
                open(sa_path, "w").write(js0)
            print("Stage B refused before the flag in every case above (the flag was never written)")
            if not with_b:
                os.remove(go)
            else:
                # ---- 8. Stage B, the one read (synthetic lockbox days only): the flag after the load and the checks, the verdict is the LEG's veto alone, a second read refused, Stage A frozen
                print("--- Stage B, the one read on the synthetic lockbox days: the flag after the load and the checks, the verdict, a second read refused")
                cap, real_cs = {}, D15.cell_stats

                def tap(Bk, xk, ck, lo_, hi_, run_, *a_, **k_):
                    st_ = real_cs(Bk, xk, ck, lo_, hi_, run_, *a_, **k_)
                    if lo_ == LB0:
                        cap["x"] = np.array(xk)
                    return st_
                buf = io.StringIO()
                with contextlib.redirect_stdout(buf), patched(D15, cell_stats=tap), patched(THIS, LB_CASHFLOW=lb_cash), patched(NI, LB_FACTS=env.lb_facts):
                    ok = stage_b()
                txt_b = buf.getvalue()
                print(txt_b.rstrip())
                sb = json.load(open(os.path.join(OUT, "buyback_stageB.json")))
                assert os.path.exists(rd) and sb["pass"] == ok and sb["cell"] == cand and sb["c"] == c_frozen and sb["leg"]["n_pos"] > 0 and {k: sb.get(k) for k in stamp()} == stamp() and sb["prereg_sha256_lf"] == PREREG_SHA
                assert set(sb["checks"]) == {f"leg monthly rebalances>={RULES['b_reb']}", "leg net>0", "leg net>0 without its top name-month"} and ok is all(sb["checks"].values()), "the pass is the LEG's veto: three checks, no book"
                assert sb["lockbox_cash_flow_sha256"] == {k: lb_cash[k][1] for k in CF_KEYS} and sb["lockbox_cash_flow"]["rows"] > src.cinfo["rows"] and sb["lockbox_facts_sha256"] == {k: env.lb_facts[k][1] for k in ("facts", "facts_add")}, "Stage B read the pinned lockbox extracts"
                assert sb["es_return_lb"]["stretch"] == ["2025-06-30", "2026-06-30"] and sb["go_flag"].startswith("smoke: the lead's go-flag") and sb["window"] == out["candidate"]["window"]
                add, mb_ = sb["book_add_reported"], B.mask(LB0, LB1)
                want = R11.stats((B.raw + c_frozen * cap["x"])[mb_], B.index[mb_])
                assert add["c"] == c_frozen and abs(add["roc"] - want["roc"]) < 1e-9 and abs(add["net"] - want["net"]) < 1e-6 and "never a pass" in add["note"], add
                assert "book add, REPORTED and never part of the pass" in txt_b and ("PASS - the leg survives" in txt_b) is ok and ("FAIL - the leg is vetoed" in txt_b) is not ok

                def reread(leg_ok, book_ok):
                    os.remove(rd)
                    os.remove(os.path.join(OUT, "buyback_stageB.json"))

                    def forced(Bk, xk, ck, lo_, hi_, run_, *a_, **k_):
                        st_ = real_cs(Bk, xk, ck, lo_, hi_, run_, *a_, **k_)
                        if lo_ == LB0:
                            st_ = {**st_, "n_units": 10 ** 6 if leg_ok else 0, "net": 1e6 if leg_ok else -1e6, "net_ex_top_pos": 1e6 if leg_ok else -1e6}
                        return st_
                    keep_bar = (RULES["b_roc"], RULES["b_sort"])
                    RULES["b_roc"], RULES["b_sort"] = (-1e9, -1e9) if book_ok else (1e9, 1e9)
                    b_ = io.StringIO()
                    try:
                        with contextlib.redirect_stdout(b_), patched(D15, cell_stats=forced), patched(THIS, LB_CASHFLOW=lb_cash), patched(NI, LB_FACTS=env.lb_facts):
                            ok_ = stage_b()
                    finally:
                        RULES["b_roc"], RULES["b_sort"] = keep_bar
                    return ok_, json.load(open(os.path.join(OUT, "buyback_stageB.json"))), b_.getvalue()
                for leg_ok, book_ok in ((True, False), (False, True)):
                    ok2, sb2, t2 = reread(leg_ok, book_ok)
                    assert ok2 is leg_ok and sb2["pass"] is leg_ok and sb2["book_add_reported"]["would_have_cleared"] is book_ok and os.path.exists(rd) and abs(sb2["book_add_reported"]["roc"] - add["roc"]) < 1e-9, (leg_ok, book_ok, sb2["checks"])
                    assert ("PASS - the leg survives" in t2) is leg_ok and ("FORWARD SHADOW" in t2) is leg_ok
                    print(f"  leg forced {'to pass' if leg_ok else 'to fail'}, book-add bar forced {'to clear' if book_ok else 'to miss'}: Stage B {'PASS' if ok2 else 'FAIL'}, would_have_cleared {sb2['book_add_reported']['would_have_cleared']} - the verdict is the leg's")
                with patched(THIS, LB_CASHFLOW=lb_cash), patched(NI, LB_FACTS=env.lb_facts):
                    refused(stage_b, "already read")
                    refused(stage_a, "Stage A is frozen")
                print("Stage B wrote the flag only after the load and the checks, refused a second read, and Stage A is frozen once the lockbox has been read")
        try:                                                                                   # the commands that never touch data
            main(["bogus"])
        except SystemExit:
            pass
        pm = peak_mb()
        print(f"SMOKE OK ({time.time() - t_start:.0f}s" + (f", peak memory {pm:,.0f} MB" if pm else "") + ") - synthetic numbers mean nothing; every command ran end to end offline"
              + ("" if with_b else " (Stage B's read was not run: `smoke DIR stage_b` runs it on the synthetic lockbox days)"))


# ------------------------------------------------------------------ the commands
TESTS = ("t_constants", "t_files", "t_cash", "t_ttm", "t_components", "t_mv", "t_random", "t_sides", "t_pipeline", "t_close", "t_nulls", "t_twins", "t_judge", "t_reference", "t_rows", "t_report", "t_integration", "t_stage_b_refusals",
         "t_cut")


def selftest(*only):
    """hand-made worlds and filings, no files, no data, no network: every group of tests prints one line, the last line says how many ran (selftest NAME ... runs the groups named)"""
    t0 = time.time()
    names = [t for t in TESTS if not only or t in only or t[2:] in only]
    with tempfile.TemporaryDirectory() as td, patched(THIS, OUT=os.path.join(td, "out")), patched(DV, REF_CSV=os.path.join(td, "no_such_dir", "resmom_cells_daily_wf.csv")):
        for name in names:                                       # the real extracts / wide calendar / RESMOM line file / OUT are never read or written by a test: a read that is not stubbed lands in the temp dir and refuses
            t1 = time.time()
            globals()[name]()
            print(f"  {name} ok ({time.time() - t1:.1f}s)", flush=True)
    pm = peak_mb()
    print(f"selftest ok: {len(names)} groups ({', '.join(t[2:] for t in names)}) in {time.time() - t0:.0f}s" + (f", peak memory {pm:,.0f} MB" if pm else ""))


def main(argv):
    cmd, args = (argv[0], argv[1:]) if argv else ("", [])
    fn = {"selftest": selftest, "smoke": smoke, "dryload": dryload, "stage_a": stage_a, "stage_b": stage_b}.get(cmd)
    if fn is None:
        print("usage: r23_buyback.py selftest | smoke DIR [stage_b] | dryload | stage_a | stage_b   (dryload: counts only; stage_a after the registered pre-registration is committed; stage_b only on the stock families' one sealed-year day, "
              "with the lead's buyback_stageB_GO.flag on file and the lockbox year's cash-flow and share-count extracts pinned)")
        return
    if cmd in ("stage_a", "stage_b"):
        os.makedirs(OUT, exist_ok=True)
    fn(*args)


if __name__ == "__main__":
    main(sys.argv[1:])
